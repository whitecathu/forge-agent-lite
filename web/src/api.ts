export interface StreamEvent { event: string; data: unknown }
export async function streamPost(url: string, body: unknown, receive: (event: StreamEvent) => void) {
  const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!response.ok || !response.body) throw new Error(`请求失败 (${response.status})`);
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
  for (;;) {
    const { value, done } = await reader.read(); buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.replace(/\r\n/g, '\n').split('\n\n'); buffer = frames.pop() || '';
    for (const frame of frames) { const parsed = parseFrame(frame); if (parsed) receive(parsed); }
    if (done) { if (buffer.trim()) { const parsed = parseFrame(buffer); if (parsed) receive(parsed); } break; }
  }
}
export function parseFrame(frame: string): StreamEvent | null {
  const lines = frame.split('\n'); const data = lines.filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart()).join('\n');
  if (!data) return null;
  return { event: lines.find(l => l.startsWith('event:'))?.slice(6).trim() || 'message', data: JSON.parse(data) };
}
export async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options); if (!response.ok) { let detail = ''; try { detail = (await response.json()).detail; } catch { /* no JSON */ } throw new Error(detail || `请求失败 (${response.status})`); }
  return response.status === 204 ? undefined as T : response.json();
}
export const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
