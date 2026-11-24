# Ảnh hưởng của đổi mạng, tab nền và đóng trình duyệt

RSocket chạy trong trình duyệt thường sử dụng WebSocket làm transport. Kết nối này chịu ảnh hưởng của thay đổi mạng, chính sách tiết kiệm pin, timer throttling, page lifecycle và việc người dùng đóng tab hoặc trình duyệt. Một kết nối đang hoạt động không có nghĩa nó sẽ tồn tại liên tục khi thiết bị chuyển Wi-Fi sang mạng di động, tab bị đưa xuống nền hoặc hệ điều hành tạm dừng trình duyệt.

Ứng dụng web cần coi kết nối RSocket là tài nguyên có thể gián đoạn. Khi kết nối mất, client phải xác định có thể resume phiên cũ hay phải tạo phiên mới, khôi phục các subscription cần thiết và đồng bộ trạng thái nghiệp vụ từ cursor/checkpoint. Với command có tác dụng phụ, retry phải giữ nguyên idempotency key để không thực hiện lặp.

## 1. RSocket trong trình duyệt và giới hạn transport

Ứng dụng JavaScript chạy trong browser không thể mở TCP socket tùy ý như ứng dụng Java server. Browser cung cấp WebSocket API, vì vậy RSocket client trong browser thường kết nối đến RSocket server qua WebSocket hoặc một gateway hỗ trợ WebSocket.

```text
Browser tab
  JavaScript application
       |
       v
  RSocket client library
       |
       v
  Browser WebSocket API
       |
       | WSS / TLS
       v
  WebSocket endpoint / gateway
       |
       v
  RSocket server
```

Điều này có một số hệ quả:

- Kết nối phụ thuộc WebSocket handshake, mạng TCP bên dưới và chính sách proxy/firewall.
- Trang HTTPS nên kết nối bằng `wss://`; mixed content có thể bị browser chặn.
- Browser không cho JavaScript tự đặt mọi HTTP header trong WebSocket handshake như một HTTP client tùy ý. Authentication thường cần dùng cookie được bảo vệ hoặc RSocket authentication metadata theo thiết kế của hệ thống.
- Browser và hệ điều hành quyết định khi nào tab được throttle hoặc suspend. JavaScript không thể yêu cầu hệ điều hành giữ tab luôn chạy.
- Hỗ trợ WebSocket, page lifecycle và các API quan sát mạng khác nhau giữa browser, phiên bản và nền tảng.

Không nên suy luận rằng một RSocket server hỗ trợ TCP thì browser có thể kết nối trực tiếp đến cổng TCP đó. Phía browser cần một transport mà browser hỗ trợ, phổ biến nhất là WebSocket.

## 2. Khi đổi mạng, WebSocket hiện tại có thể bị mất

Ví dụ người dùng đang mở dashboard qua Wi-Fi rồi chuyển sang mạng di động. Địa chỉ IP, route mạng, NAT mapping hoặc đường truyền có thể thay đổi. WebSocket hiện tại thường gắn với một kết nối TCP đã được thiết lập; nó không tự di chuyển sang interface mới chỉ vì thiết bị có Internet trở lại.

```text
Trước khi đổi mạng:
Browser -- Wi-Fi / TCP connection A -- WebSocket -- RSocket server

Chuyển Wi-Fi sang cellular:
Browser --X connection A không còn hoạt động ổn định
        
Sau đó:
Browser -- cellular / TCP connection B -- WebSocket mới -- server
```

Một số trường hợp kết nối cũ đóng nhanh và phát `close`; trường hợp khác có thể trở thành half-open: client hoặc server chưa nhận ra peer đã mất cho đến khi keepalive hoặc timeout phát hiện. Vì vậy, ứng dụng cần xử lý cả lỗi tức thời lẫn kết nối im lặng không còn truyền dữ liệu.

Nếu mạng đổi nhưng đường truyền cũ vẫn hoạt động, ứng dụng có thể tiếp tục dùng kết nối đó. Không cần đóng kết nối chỉ vì một API báo thay đổi loại mạng; hãy dựa vào trạng thái transport thực tế và lỗi từ RSocket runtime.

## 3. `online` và `offline` chỉ là tín hiệu tham khảo

Browser phát các sự kiện `online` và `offline`, đồng thời cung cấp `navigator.onLine`. Các tín hiệu này hữu ích để điều chỉnh trải nghiệm, nhưng không chứng minh rằng endpoint RSocket của ứng dụng có thể truy cập.

Ví dụ:

```javascript
window.addEventListener("offline", () => {
  showConnectionHint("Thiết bị đang offline");
});

window.addEventListener("online", () => {
  showConnectionHint("Mạng có vẻ đã hoạt động trở lại");
  scheduleReconnect();
});
```

`navigator.onLine === true` có thể chỉ có nghĩa browser đang có một interface mạng. DNS, VPN, captive portal, proxy hoặc server đích vẫn có thể không truy cập được. Tương tự, `offline` không cho biết chính xác kết nối RSocket đã hỏng ở thời điểm nào.

Network Information API như `navigator.connection` có thể cung cấp loại kết nối hoặc thông tin hiệu năng ước lượng ở một số browser, nhưng mức hỗ trợ không đồng đều. Không dùng API này làm điều kiện bắt buộc để ứng dụng hoạt động. Hãy coi nó là gợi ý cho UI hoặc lựa chọn chất lượng dữ liệu.

**Quy tắc:** `online` có thể kích hoạt một lần thử kết nối; chỉ khi WebSocket/RSocket handshake thành công mới đánh dấu session là connected.

## 4. Tab nền và timer throttling

Khi người dùng chuyển sang tab khác hoặc minimize browser, trang thường chuyển sang trạng thái hidden. Browser có thể giảm tần suất timer, gom các callback hoặc tạm dừng một số công việc để tiết kiệm pin và CPU.

Điều này ảnh hưởng đến ứng dụng realtime:

- Heartbeat do JavaScript quản lý có thể chạy trễ hơn dự kiến.
- Xử lý message và cập nhật UI có thể bị trì hoãn.
- Timer reconnect/backoff không chạy chính xác theo thời gian đặt trước.
- Một số browser trên mobile có thể suspend toàn bộ trang khi ứng dụng khác chiếm foreground.
- Khi trang được tiếp tục, queue callback hoặc trạng thái kết nối có thể đã lỗi thời.

Không đặt heartbeat quá ngắn với giả định timer browser luôn chính xác. Nếu server đóng kết nối vì không nhận keepalive trong một khoảng quá ngắn so với hành vi tab nền, ứng dụng có thể tạo nhiều reconnect không cần thiết.

Sử dụng Page Visibility API để nhận biết trang đang hiển thị hay ẩn:

```javascript
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    pauseExpensiveUiWork();
  } else {
    refreshVisibleData();
    verifyRSocketConnection();
  }
});
```

Không nhất thiết phải đóng RSocket mỗi khi tab chuyển hidden. Nếu kết nối vẫn hữu ích và server cho phép, có thể giữ kết nối nhưng giảm công việc UI. Khi tab trở lại visible, kiểm tra transport và đồng bộ lại dữ liệu trước khi hiển thị trạng thái realtime là mới nhất.

## 5. Mobile background và hệ điều hành suspend browser

Trên điện thoại, khi người dùng chuyển sang ứng dụng khác, khóa màn hình hoặc bật chế độ tiết kiệm pin, hệ điều hành có thể đóng băng hoặc kết thúc browser process. Trang có thể không nhận đủ thời gian để chạy cleanup, gửi close frame hoặc lưu trạng thái cuối cùng.

Không thể dựa vào JavaScript timer để bảo đảm một kết nối RSocket được duy trì liên tục khi browser ở background. Nếu sản phẩm cần nhận thông báo khi trang không hoạt động, cần cân nhắc cơ chế nền phù hợp của nền tảng như push notification; WebSocket/RSocket trong một tab bị suspend không phải dịch vụ chạy nền đáng tin cậy.

Khi browser được mở lại:

1. Kiểm tra xem connection object hiện tại còn hợp lệ không.
2. Nếu transport đã đóng hoặc không phản hồi, chuyển sang reconnect.
3. Thử resume nếu runtime và server hỗ trợ, đồng thời session vẫn còn trong retention window.
4. Nếu resume không thành công, tạo RSocket session mới.
5. Khôi phục subscription và cursor ở tầng ứng dụng.
6. Đối soát các command đang chờ kết quả bằng idempotency key.

## 6. Page lifecycle: hidden, pagehide, pageshow và freeze/resume

Các sự kiện lifecycle cung cấp tín hiệu về trạng thái document. Chúng có thể giúp ứng dụng giảm hoạt động, lưu checkpoint hoặc khôi phục UI, nhưng không phải tất cả đều được hỗ trợ giống nhau trên mọi browser.

| Sự kiện/trạng thái | Ý nghĩa | Cách dùng phù hợp |
|---|---|---|
| `visibilitychange` | Document chuyển giữa visible và hidden. | Tạm dừng polling/UI nặng; kiểm tra kết nối khi visible trở lại. |
| `pagehide` | Trang đang rời khỏi document hoặc được đưa vào back-forward cache. | Thực hiện cleanup đồng bộ, đánh dấu trạng thái local; không phụ thuộc async work dài. |
| `pageshow` | Trang được hiển thị, có thể là lần load mới hoặc khôi phục từ BFCache. | Kiểm tra `event.persisted`, xác minh connection và refresh dữ liệu. |
| `freeze` / `resume` | Một số browser phát tín hiệu trang bị đóng băng và tiếp tục. | Tạm dừng công việc nền và xác minh lại session khi resume; kiểm tra hỗ trợ browser. |
| `beforeunload` | Trang sắp unload trong một số tình huống. | Chỉ dùng cho cảnh báo rời trang khi thực sự cần; không dùng làm cơ chế cleanup mạng đáng tin cậy. |

Ví dụ dùng `pagehide` và `pageshow`:

```javascript
window.addEventListener("pagehide", (event) => {
  saveLocalCheckpoint();
  markConnectionAsPossiblyStale();

  // event.persisted cho biết trang có thể được đưa vào BFCache.
  // Không chờ một request mạng bất đồng bộ ở đây.
});

window.addEventListener("pageshow", (event) => {
  if (event.persisted) {
    verifyRSocketConnection();
    refreshVisibleData();
  }
});
```

Nếu đóng tab thông thường, `pagehide` có thể được phát; nếu browser crash, process bị kill hoặc thiết bị mất điện, không có bảo đảm handler nào chạy. Thiết kế server phải tự phát hiện connection chết bằng timeout/keepalive và cleanup session sau đó.

## 7. Vì sao không dựa vào `beforeunload` để đóng RSocket?

`beforeunload` không phải một hook đáng tin cậy cho công việc bất đồng bộ. Browser có thể không phát sự kiện trong một số tình huống kết thúc process; ngay cả khi sự kiện chạy, thời gian thực thi bị giới hạn và các thao tác mạng không được bảo đảm hoàn tất.

Không nên viết logic quan trọng theo kiểu:

```javascript
window.addEventListener("beforeunload", async () => {
  await rsocketRequester.rsocket().then(socket => socket.dispose());
});
```

Browser không chờ promise tùy ý hoàn tất trước khi đóng document. Việc gọi `dispose()` có thể hữu ích trong một luồng cleanup chủ động khi ứng dụng vẫn còn thời gian, nhưng không thể dùng `beforeunload` làm bảo đảm server luôn nhận được tín hiệu đóng.

Nếu muốn đóng connection khi người dùng chủ động đăng xuất hoặc rời một màn hình, hãy thực hiện trong handler UI khi trang còn hoạt động. Khi tab bị kill bất ngờ, để server phát hiện bằng keepalive timeout và áp dụng chính sách session cleanup.

`navigator.sendBeacon()` gửi dữ liệu HTTP nhỏ theo cơ chế best-effort; nó không gửi RSocket frame qua WebSocket và không thay thế close/resume protocol. `fetch(..., { keepalive: true })` cũng là HTTP request, không phải cách tiếp tục một WebSocket session.

## 8. Ảnh hưởng đến RSocket KEEPALIVE

RSocket có frame `KEEPALIVE` để peer kiểm tra kết nối và có thể xác nhận position đã nhận trong session có resumption. Runtime RSocket thường quản lý keepalive theo cấu hình của client/server.

Trong browser, keepalive có thể bị ảnh hưởng khi JavaScript event loop bị throttle hoặc suspend. Nếu runtime cần timer JavaScript để phát frame keepalive, frame có thể không được phát đúng lịch trong thời gian tab bị đóng băng. Phía server có thể kết luận peer đã mất sau khi timeout.

Khi chọn keepalive interval và lifetime, cân nhắc:

- Thời gian tab nền có thể bị throttle.
- Thời gian hệ điều hành có thể suspend browser trên mobile.
- Độ trễ mạng di động và các khoảng mất sóng ngắn.
- Timeout của proxy/load balancer/WebSocket gateway.
- Chi phí pin và lưu lượng nếu keepalive quá thường xuyên.

Không kéo lifetime vô hạn để che giấu connection chết. Timeout quá dài làm server giữ session và resource lâu hơn; timeout quá ngắn làm reconnect giả tăng. Cần đo trên các browser và thiết bị mục tiêu.

## 9. Resume phiên RSocket sau khi transport bị gián đoạn

Khi transport bị mất, connection mới không tự động tiếp tục session cũ. Connection resumption chỉ hoạt động nếu:

1. Client và server đều hỗ trợ, bật và thương lượng resumption.
2. Client có resume token/state cần thiết để nhận diện phiên.
3. Server vẫn giữ session và replay buffer trong thời gian cho phép.
4. Position được trao đổi cho phép phát lại phần frame còn thiếu.
5. Client runtime có thể thực hiện resume trên transport mới.

Trình tự khái quát:

```text
Browser tab                         RSocket server
    |                                      |
    | WebSocket bị mất do đổi mạng         |
    X                                      X
    |                                      |
    | tạo WebSocket mới                    |
    |                                      |
    | RESUME (token + receive position) -->|
    |                                      | tìm session và replay buffer
    |<------------- RESUME_OK -------------|
    |                                      |
    | replay frame còn thiếu                |
    |<========== session tiếp tục =========>|
```

Nếu resume thành công, runtime có thể khôi phục các stream đang hoạt động theo trạng thái giao thức. Nếu session đã hết hạn, replay buffer không còn đủ dữ liệu hoặc token không hợp lệ, resume bị từ chối và ứng dụng phải chuyển sang session mới.

Không phải mọi phiên bản RSocket JavaScript hoặc browser client đều hỗ trợ resumption theo cùng cách. Hãy kiểm tra khả năng của thư viện cụ thể, cấu hình server và hành vi khi transport reconnect; đừng suy luận từ việc giao thức RSocket có định nghĩa RESUME rằng client library đang dùng đã triển khai đầy đủ.

## 10. Resume không thay thế khôi phục trạng thái ứng dụng

Ngay cả khi RSocket resume thành công, trạng thái giao diện và dữ liệu nghiệp vụ vẫn cần được quản lý ở tầng ứng dụng. Nếu resume thất bại hoặc người dùng reload tab, client có thể cần mở lại các subscription.

Một mô hình hữu ích:

```text
Transport/session state
  - WebSocket connection
  - RSocket session / resume token
  - stream state và frame positions

Application state
  - subscription intent
  - last processed event cursor
  - pending commands + idempotency keys
  - current view/model state
```

Transport state có thể biến mất khi page reload hoặc session hết hạn. Application state quan trọng cần được lưu riêng, ví dụ trong IndexedDB hoặc server-side session store. Khi tạo session mới, client dùng cursor để yêu cầu event tiếp theo sau vị trí đã xử lý.

Ví dụ request subscription có cursor:

```javascript
const cursor = await loadLastProcessedCursor("device-42");

const subscription = await openRSocketStream({
  route: "devices.events",
  data: {
    deviceId: "device-42",
    afterCursor: cursor
  }
});
```

Đây là pseudocode minh họa hợp đồng ứng dụng; API thực tế phụ thuộc RSocket JavaScript client và codec đang sử dụng. Server cần hỗ trợ truy vấn event theo cursor hoặc một cơ chế replay nghiệp vụ tương đương.

Chỉ cập nhật cursor sau khi event đã được xử lý thành công ở phía client. Nếu lưu cursor trước khi cập nhật UI hoặc ghi dữ liệu local hoàn tất, crash có thể làm mất event chưa xử lý. Nếu lưu cursor sau xử lý, event có thể được phát lại khi crash ở giữa; consumer cần idempotent để xử lý trùng an toàn.

## 11. Reconnect với exponential backoff và jitter

Khi resume không khả dụng hoặc bị từ chối, client tạo connection/session mới. Không reconnect liên tục theo vòng lặp tức thời; điều đó có thể gây bão kết nối khi server hoặc mạng đang gặp sự cố.

Exponential backoff tăng dần thời gian chờ giữa các lần thử:

\[
delay_n = \min(maxDelay, baseDelay \times 2^n) + jitter
\]

Ví dụ cấu hình:

| Lần thử | Delay cơ sở minh họa |
|---:|---:|
| 1 | 500 ms |
| 2 | 1 s |
| 3 | 2 s |
| 4 | 4 s |
| 5+ | Tối đa 30 s |

Jitter ngẫu nhiên giúp các client không đồng loạt reconnect cùng một thời điểm sau khi mạng hoặc server phục hồi.

Một chiến lược reconnect nên:

- Giới hạn delay tối đa và số lần thử liên tiếp nếu sản phẩm cần.
- Reset backoff sau khi kết nối ổn định trong một khoảng thời gian, không chỉ sau handshake ngắn.
- Hủy timer reconnect cũ khi connection mới đã thành công.
- Dùng `online` như tín hiệu để thử sớm nhưng vẫn xác minh bằng handshake.
- Khi tab hidden, cho phép timer bị throttle và không tạo vòng lặp bù dồn dập khi tab visible trở lại.
- Phân biệt lỗi xác thực/authorization với lỗi mạng; không retry credential sai vô hạn.

## 12. Quản lý subscription sau reconnect

Khi tạo RSocket session mới, các stream của session cũ không tự động tồn tại trong session mới. Ứng dụng cần biết subscription nào phải mở lại và với tham số nào.

Lưu subscription intent thay vì lưu đối tượng subscription runtime:

```javascript
const subscriptions = new Map();

function rememberSubscription(id, request) {
  subscriptions.set(id, request);
}

async function restoreSubscriptions() {
  for (const [id, request] of subscriptions) {
    await openSubscription(id, request);
  }
}
```

Đoạn code là pseudocode về state quản lý. Trong triển khai thực tế, cần tránh mở lại subscription trùng khi resume đã khôi phục stream cũ. Chỉ chạy `restoreSubscriptions()` khi tạo session mới hoặc sau khi xác định các stream cũ không còn tồn tại.

Với mỗi stream, lưu cursor hoặc sequence number do server cấp. Nếu stream có thể phát event trùng sau reconnect, client nên deduplicate theo event ID hoặc cursor và chỉ commit cursor sau khi xử lý xong.

## 13. Pending command khi tab bị đóng

Nếu tab bị đóng khi command đang chờ, JavaScript có thể mất kết quả response. Server có thể đã thực hiện tác dụng phụ. Khi người dùng mở lại ứng dụng, client cần biết command nào chưa có kết quả.

Đối với command quan trọng:

1. Tạo idempotency key một lần khi tạo command.
2. Ghi command và key vào IndexedDB/outbox trước khi gửi.
3. Gửi command qua RSocket.
4. Khi nhận receipt, đánh dấu command hoàn tất và xóa/đóng outbox record theo chính sách.
5. Khi khởi động lại, truy vấn trạng thái hoặc gửi lại cùng command và cùng key.
6. Server deduplicate và trả kết quả đã lưu nếu command đã được xử lý.

Không dựa vào việc tab đóng để kết luận command đã bị hủy. Đóng WebSocket không rollback transaction server. Nếu người dùng cần hủy một lệnh đã gửi, thiết kế một command cancel riêng với authorization và semantics nghiệp vụ rõ ràng.

## 14. Nhiều tab và nhiều cửa sổ

Một người dùng có thể mở cùng ứng dụng trong nhiều tab. Mỗi tab thường có JavaScript context và WebSocket riêng, trừ khi ứng dụng chủ động chia sẻ kết nối qua kiến trúc như SharedWorker hoặc một service trung gian được hỗ trợ.

Hệ quả:

- Mỗi tab có thể tạo một RSocket session và subscription riêng.
- Cùng một command có thể được gửi từ hai tab nếu UI không phối hợp.
- Server phải deduplicate bằng idempotency key ở backend; không dựa vào bộ nhớ của một tab.
- Có thể dùng `BroadcastChannel` hoặc cơ chế đồng bộ phù hợp để truyền trạng thái giữa các tab, nhưng đây không phải bảo đảm giao nhận bền vững.
- Nếu dùng SharedWorker để chia sẻ WebSocket, cần kiểm tra browser support, lifecycle của worker và hành vi khi mọi tab đóng.

Không giả định `localStorage` event hoặc `BroadcastChannel` là distributed lock an toàn cho nghiệp vụ. Quyết định duy nhất cho side effect phải được thực hiện ở server/datastore dùng chung.

## 15. Trạng thái kết nối nên được biểu diễn rõ ràng

UI không nên chỉ có hai trạng thái `connected` và `disconnected`. Một state machine giúp tránh hiển thị dữ liệu cũ như dữ liệu realtime:

```text
DISCONNECTED
     |
     v
CONNECTING
     |
     +---- handshake OK ----> CONNECTED
     |                          |
     |                          | network/page interruption
     |                          v
     +<---- failure -------- RECONNECTING
                                |
                                +--> RESUMING
                                |       |
                                |       +-- success --> CONNECTED
                                |       |
                                |       +-- rejected --> CONNECTING (new session)
                                |
                                +--> AUTH_REQUIRED / FAILED
```

Các trạng thái gợi ý:

| Trạng thái | Ý nghĩa UI |
|---|---|
| `CONNECTING` | Đang thiết lập WebSocket/RSocket. |
| `CONNECTED` | Transport/session hoạt động và stream cần thiết đã sẵn sàng. |
| `RECONNECTING` | Connection bị mất, đang chờ lần thử tiếp theo. |
| `RESUMING` | Đang thử tiếp tục session cũ nếu được hỗ trợ. |
| `SYNCING` | Đã kết nối nhưng đang replay hoặc đồng bộ dữ liệu ứng dụng. |
| `AUTH_REQUIRED` | Cần đăng nhập hoặc refresh credential trước khi kết nối. |
| `FAILED` | Đã vượt chính sách retry hoặc gặp lỗi không thể tự phục hồi. |

Đừng chuyển UI sang trạng thái realtime hoàn chỉnh ngay khi WebSocket open. Cần chờ RSocket SETUP, authentication và các subscription quan trọng hoàn tất; sau reconnect có thể còn bước đồng bộ cursor.

## 16. Mẫu điều phối lifecycle và reconnect ở browser

Ví dụ sau minh họa cách kết hợp các tín hiệu browser với một lớp quản lý RSocket. Các hàm `connectRSocket`, `tryResume`, `openNewSession`, `closeRSocket` và `restoreSubscriptions` là adapter của ứng dụng, không phải API chuẩn chung của mọi RSocket JavaScript client.

```javascript
let state = "DISCONNECTED";
let reconnectTimer;
let retryAttempt = 0;
let activeConnection;

function setState(next) {
  state = next;
  renderConnectionState(next);
}

function scheduleReconnect() {
  if (reconnectTimer || state === "CONNECTING") return;

  const base = 500;
  const max = 30_000;
  const exponential = Math.min(max, base * (2 ** retryAttempt));
  const jitter = Math.random() * Math.min(1_000, exponential * 0.25);
  const delay = exponential + jitter;

  retryAttempt += 1;
  setState("RECONNECTING");

  reconnectTimer = setTimeout(async () => {
    reconnectTimer = undefined;
    await reconnect();
  }, delay);
}

async function reconnect() {
  setState("CONNECTING");

  try {
    const resumed = await tryResume(activeConnection);
    if (!resumed) {
      activeConnection = await openNewSession();
      await restoreSubscriptions();
    }

    retryAttempt = 0;
    setState("SYNCING");
    await synchronizeApplicationState();
    setState("CONNECTED");
  } catch (error) {
    if (isAuthenticationError(error)) {
      setState("AUTH_REQUIRED");
      return;
    }
    scheduleReconnect();
  }
}

window.addEventListener("online", scheduleReconnect);

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    verifyRSocketConnection().then(healthy => {
      if (!healthy) scheduleReconnect();
    });
  }
});

window.addEventListener("pagehide", () => {
  saveLocalCheckpoint();
  // Không phụ thuộc async close hoàn tất ở pagehide.
});
```

Trong triển khai thực tế, cần thêm xử lý `close`/`error` từ WebSocket hoặc RSocket client, hủy timer khi component unmount, chống reconnect đồng thời và kiểm tra connection generation để callback cũ không ghi đè state của connection mới. `tryResume(...)` chỉ dùng khi thư viện thực sự hỗ trợ resumption và có trạng thái phiên hợp lệ.

## 17. Bảo mật khi reconnect

Reconnect có thể tạo một handshake mới. Nếu token đã hết hạn, server có thể từ chối SETUP hoặc request đầu tiên. Client cần refresh credential theo flow an toàn rồi tạo connection mới.

Các nguyên tắc:

- Chỉ dùng `wss://` trong production khi trang chạy qua HTTPS.
- Không lưu password hoặc bearer token dài hạn trong localStorage chỉ để reconnect.
- Nếu dùng access token, áp dụng thời hạn ngắn và refresh qua cơ chế bảo mật của ứng dụng.
- Re-authenticate khi tạo session mới; không mặc định security context cũ còn hợp lệ.
- Kiểm tra authorization lại khi mở subscription hoặc truy vấn dữ liệu sau reconnect.
- Xác minh `Origin` ở WebSocket endpoint và áp dụng authentication độc lập; Origin không phải cơ chế xác thực user.
- Không ghi resume token, access token hoặc authentication metadata vào log.

Resume token có thể cho phép tiếp tục một session đã xác thực, vì vậy cần xem nó như dữ liệu nhạy cảm. Nếu phải lưu qua page reload, cân nhắc threat model XSS, thời gian sống ngắn và ràng buộc token với danh tính/phiên. Không lưu token trong storage lâu dài nếu thư viện hoặc thiết kế server không yêu cầu.

## 18. Khả năng tương thích giữa browser

Các browser hiện đại thường hỗ trợ WebSocket, nhưng lifecycle và hành vi background khác nhau theo browser, phiên bản và hệ điều hành. Không nên dựa vào một event lifecycle duy nhất để xác định chắc chắn trang sắp bị đóng.

| Khả năng | Cách sử dụng | Lưu ý tương thích |
|---|---|---|
| WebSocket | Transport RSocket trong browser. | Kiểm tra endpoint, TLS, proxy và browser mục tiêu. |
| `online` / `offline` | Gợi ý thay đổi trạng thái mạng. | Không chứng minh server RSocket reachable. |
| Page Visibility API | Biết tab visible/hidden. | Được hỗ trợ rộng rãi nhưng thời điểm callback vẫn chịu scheduling. |
| `pagehide` / `pageshow` | Theo dõi navigation và BFCache. | Không bảo đảm chạy khi browser/process bị kill. |
| `beforeunload` | Cảnh báo người dùng trước khi rời trang. | Không dựa vào để hoàn tất async cleanup hoặc gửi dữ liệu. |
| `navigator.connection` | Thông tin loại mạng/hiệu năng ước lượng. | Hỗ trợ hạn chế và không đồng nhất; chỉ dùng như hint. |
| `freeze` / `resume` | Tín hiệu page lifecycle ở một số browser. | Không phổ quát; luôn có fallback qua visibility và connection health. |
| SharedWorker / BroadcastChannel | Chia sẻ hoặc phối hợp giữa tab. | Hỗ trợ và lifecycle khác nhau; không thay thế backend coordination. |

Nên kiểm thử trên tổ hợp browser/OS thực tế của sản phẩm, đặc biệt Safari trên iOS, Chrome/Edge trên desktop và browser Android. Cần kiểm tra cả trường hợp tab nền lâu, khóa màn hình, chuyển mạng và quay lại sau khi browser bị suspend.

## 19. Ma trận hành vi và cách phục hồi

| Sự kiện | Tác động có thể xảy ra | Phản ứng của ứng dụng |
|---|---|---|
| Chuyển Wi-Fi sang cellular | TCP/WebSocket cũ bị reset hoặc treo. | Phát hiện close/timeout, thử resume nếu hỗ trợ, nếu không tạo session mới. |
| Mất sóng ngắn | Connection tạm thời không truyền dữ liệu. | Backoff có jitter, tránh reconnect vòng lặp. |
| Tab chuyển hidden | Timer và UI work bị throttle. | Giảm công việc UI; giữ/đóng socket theo policy sản phẩm. |
| Tab bị freeze | JavaScript và keepalive có thể dừng. | Khi resume, xác minh connection và đồng bộ lại. |
| Mobile OS suspend browser | Socket có thể bị timeout hoặc process bị kill. | Không dựa vào cleanup; server timeout và client reconnect khi mở lại. |
| Reload trang | JavaScript context và connection object cũ bị hủy. | Khởi tạo session mới hoặc resume nếu state/token được lưu và runtime hỗ trợ; phục hồi cursor. |
| Đóng tab bình thường | Browser có thể đóng WebSocket và phát lifecycle event. | Cleanup best-effort; server vẫn cần timeout fallback. |
| Browser crash / force kill | Không có callback cleanup đáng tin cậy. | Server phát hiện peer mất; client khôi phục state từ durable storage khi khởi động lại. |
| Token hết hạn khi reconnect | SETUP/authentication bị từ chối. | Refresh credential rồi tạo connection mới; không retry token cũ vô hạn. |

## 20. Kiểm thử đổi mạng, background và đóng browser

Không chỉ kiểm thử bằng cách gọi `socket.dispose()` trong một unit test. Cần mô phỏng các sự kiện ở tầng browser, transport và server.

Các kịch bản nên có:

1. **Đổi mạng:** đang có request-stream, tắt interface Wi-Fi hoặc chuyển mạng; xác minh close/timeout, reconnect và resume/fallback.
2. **Mất mạng rồi online:** phát `offline`, sau đó `online`; xác minh chỉ một reconnect được lên lịch và trạng thái chỉ thành connected sau handshake.
3. **Tab nền:** chuyển sang tab khác trong thời gian dài; xác minh timer throttle không tạo reconnect storm và dữ liệu được đồng bộ khi visible.
4. **Mobile sleep:** khóa màn hình, chờ hệ điều hành suspend, mở lại; xác minh connection được kiểm tra và subscription được khôi phục.
5. **BFCache:** điều hướng đi rồi quay lại; xác minh `pageshow` với `persisted` và không tạo hai subscription trùng.
6. **Đóng tab:** đóng tab bình thường; xác minh server cleanup sau close hoặc keepalive timeout.
7. **Force kill/crash:** kết thúc browser process; xác minh server không phụ thuộc `beforeunload`.
8. **Resume thành công:** kiểm tra runtime hỗ trợ resume, session server còn hiệu lực và frame chưa xác nhận được phục hồi.
9. **Resume thất bại:** hết retention hoặc replay buffer không đủ; xác minh client mở session mới và khôi phục cursor ứng dụng.
10. **Pending command:** ngắt kết nối sau khi gửi command nhưng trước response; khởi động lại và gửi cùng idempotency key, xác minh side effect chỉ xảy ra một lần.
11. **Authentication expiry:** token hết hạn khi tab nền; xác minh refresh và authentication mới trước khi mở subscription.
12. **Nhiều tab:** mở cùng ứng dụng trong hai tab; xác minh không giả định một connection dùng chung và server vẫn deduplicate command.

Khi kiểm thử, ghi lại thời điểm lifecycle event, WebSocket close code, RSocket error, số lần reconnect, resume result, session ID/correlation ID, thời gian đồng bộ và số event được replay. Không log credentials hoặc resume token.

## 21. Quan sát và chẩn đoán production

Các metric nên có:

| Metric | Ý nghĩa |
|---|---|
| `rsocket.browser.connect.success` | Số lần browser thiết lập session thành công. |
| `rsocket.browser.connect.failure` | Số lần handshake hoặc SETUP thất bại. |
| `rsocket.browser.disconnect` | Số lần connection bị đóng/mất. |
| `rsocket.browser.reconnect.attempt` | Số lần thử reconnect. |
| `rsocket.browser.resume.success` | Số lần resume thành công. |
| `rsocket.browser.resume.rejected` | Số lần resume bị từ chối. |
| `rsocket.browser.sync.duration` | Thời gian đồng bộ cursor/subscription sau reconnect. |
| `rsocket.browser.pending.commands` | Số command chưa có kết quả cuối cùng. |

Phân đoạn metric theo browser family/version, OS, transport endpoint và loại mạng nếu dữ liệu đó được phép thu thập. Tránh đưa IP đầy đủ hoặc dữ liệu định danh cá nhân vào metric label có cardinality cao.

Khi điều tra một kết nối chập chờn, phân biệt:

- WebSocket handshake không thành công.
- WebSocket đã mở nhưng RSocket SETUP/authentication thất bại.
- RSocket session bị timeout do keepalive.
- Resume bị từ chối vì token/session/position/buffer.
- Resume thành công nhưng application cursor/subscription phục hồi sai.
- Server đã xử lý command nhưng client mất response.

Mỗi trường hợp có hướng xử lý khác nhau; một thông báo chung “network error” không đủ để chẩn đoán.

## 22. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Coi `navigator.onLine` là server reachable | UI báo connected dù endpoint không truy cập được. | Chỉ đánh dấu connected sau WebSocket và RSocket SETUP thành công. |
| Giữ heartbeat quá ngắn | Tab nền bị throttle làm server timeout và reconnect liên tục. | Chọn interval/lifetime theo browser và hạ tầng thực tế. |
| Nghĩ WebSocket tự chuyển sang mạng mới | Connection TCP cũ có thể đã hỏng. | Reconnect transport; resume chỉ khi runtime và server hỗ trợ. |
| Dựa vào `beforeunload` để gửi close/command | Async cleanup có thể không chạy xong hoặc không chạy. | Cleanup chủ động khi UI còn hoạt động; server timeout làm fallback. |
| Nghĩ tab hidden luôn bị đóng socket | Có thể tạo reconnect không cần thiết khi người dùng đổi tab. | Dùng visibility để điều chỉnh công việc và kiểm tra health. |
| Nghĩ tab nền luôn giữ socket sống | Browser/OS có thể suspend trang. | Thiết kế reconnect và app-level resync. |
| Coi resume là khôi phục toàn bộ UI state | Resume giao thức không thay thế cursor và state nghiệp vụ. | Lưu subscription intent, cursor và pending command riêng. |
| Mở lại mọi subscription sau resume thành công | Tạo stream trùng và nhận event hai lần. | Chỉ restore khi session mới hoặc stream cũ không còn. |
| Retry command với key mới | Tác dụng phụ có thể lặp. | Lưu và dùng lại idempotency key của logical command. |
| Dùng `sendBeacon` để đóng RSocket | Beacon là HTTP, không phải WebSocket/RSocket frame. | Dùng lifecycle cleanup best-effort và server timeout. |
| Giả định mọi browser hỗ trợ `navigator.connection` hoặc freeze event | Code có thể không chạy trên browser mục tiêu. | Feature detect và có fallback. |
| Cho rằng `pagehide` luôn chạy | Browser crash/force kill có thể không phát callback. | Server phải tự phát hiện connection chết. |

## 23. Checklist thiết kế ứng dụng RSocket trên browser

Trước khi triển khai production, hãy xác định:

- Browser client dùng WebSocket transport và endpoint `wss://` phù hợp.
- `online`/`offline` chỉ là hint; trạng thái kết nối dựa trên handshake/health thật.
- Visibility và page lifecycle chỉ điều chỉnh công việc, không được coi là bảo đảm cleanup.
- Keepalive/lifetime phù hợp với timer throttling, mobile sleep và timeout proxy.
- Reconnect có exponential backoff, jitter và chống nhiều vòng reconnect đồng thời.
- Resume chỉ được dùng khi client library và server hỗ trợ, session còn hiệu lực.
- Có fallback tạo session mới và phục hồi subscription/cursor ở tầng ứng dụng.
- Pending command được lưu bền vững nếu cần sống qua reload/đóng browser.
- Command có tác dụng phụ dùng idempotency key ổn định qua retry.
- Authentication được làm mới khi reconnect; resume token và credentials được bảo vệ.
- Nhiều tab không dựa vào local state để đảm bảo uniqueness nghiệp vụ.
- Có kiểm thử trên browser/OS mục tiêu với đổi mạng, tab nền, mobile suspend và force kill.
- Có metric riêng cho WebSocket, SETUP, resume và application resync.

## Kết luận

Đổi mạng có thể làm mất WebSocket/TCP hiện tại; tab nền có thể bị throttle hoặc freeze; mobile OS và việc đóng browser có thể kết thúc trang mà không cho JavaScript đủ thời gian cleanup. `online`, `beforeunload` và các lifecycle event chỉ là tín hiệu best-effort, không phải bảo đảm kết nối hoặc gửi dữ liệu thành công. Ứng dụng RSocket trên browser cần keepalive hợp lý, reconnect có backoff/jitter, thử resume khi runtime/server hỗ trợ, và luôn có phương án tạo session mới. Cursor, subscription intent và pending command phải được quản lý ở tầng ứng dụng; idempotency key bảo vệ side effect khi retry. Kiểm thử trên browser và thiết bị thật là cách xác nhận hành vi phù hợp với môi trường triển khai.
