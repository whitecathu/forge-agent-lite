import { describe, it, expect } from 'vitest';
import { parseFrame } from './api';
describe('SSE protocol', () => {
 it('parses Chinese evidence payload', () => expect(parseFrame('event: token\ndata: {"text":"证据 [1]"}')).toEqual({event:'token', data:{text:'证据 [1]'}}));
 it('ignores heartbeat', () => expect(parseFrame(': heartbeat')).toBeNull());
 it('supports default event names', () => expect(parseFrame('id: 3\ndata: {"seq":3}')?.event).toBe('message'));
});
