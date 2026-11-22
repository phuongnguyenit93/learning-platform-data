# HTTP/2: luồng đồng thời trên kết nối và điều tiết truyền dữ liệu

**HTTP/2** cho phép nhiều HTTP request/response tiến triển đồng thời trên một kết nối bằng cách phân chia thông điệp thành **frames** có **stream ID** riêng. Kết nối TCP không phải chờ toàn bộ response thứ nhất hoàn tất mới chuyển response thứ hai. Tuy nhiên các stream cùng chia sẻ băng thông, TCP connection, memory và **connection flow-control window**. Vì vậy multiplexing giúp giảm một số kiểu chặn ở tầng HTTP, **không** biến mỗi stream thành một kết nối TCP độc lập hoặc xóa toàn bộ ảnh hưởng của receiver chậm.

Bài Knowledge này tập trung vào hai vấn đề cốt lõi:

1. **Multiplexing:** request/response khác nhau được gắn stream ID, chia thành HEADERS và DATA frames và xen kẽ trên một HTTP/2 connection.
2. **Flow control:** bên nhận cấp credit theo byte ở **cả stream level và connection level**. Sender chỉ được truyền DATA khi cả hai cửa sổ còn đủ credit; receiver cấp thêm qua `WINDOW_UPDATE`. Nếu chỉ một cửa sổ đã cạn, DATA bị chặn.

Bài học bám **RFC 9113** và Java 17+. Ta sẽ mô phỏng chính xác cách hai cửa sổ tiêu thụ credit, xây chương trình Java phân biệt **HTTP/2 được ưu tiên** với **HTTP/2 thực sự được thương lượng**, cùng quy tắc streaming body và backpressure ở tầng ứng dụng.

## 1. Multiplexing: nhiều stream logic trên một HTTP/2 connection

~~~text
                       Một kết nối TCP (thường bọc TLS)
Client                                                             Server
   │                                                                   │
   │── HEADERS stream=1: GET /catalog ───────────────────────────────>│
   │── HEADERS stream=3: GET /profile ───────────────────────────────>│
   │── HEADERS stream=5: GET /thumbnail ─────────────────────────────>│
   │                                                                   │
   │<── HEADERS stream=5 ─────────────────────────────────────────────│
   │<── DATA stream=5 (một phần hoặc toàn bộ ảnh) ─────────────────────│
   │<── HEADERS stream=1 ─────────────────────────────────────────────│
   │<── DATA stream=1 (phần đầu catalog) ──────────────────────────────│
   │<── HEADERS stream=3 ─────────────────────────────────────────────│
   │<── DATA stream=3 (profile) ───────────────────────────────────────│
   │<── DATA stream=1 (phần tiếp catalog) ─────────────────────────────│
~~~

**Một stream** là cuộc trao đổi HTTP logic (request/response) với trạng thái riêng; **frame** là đơn vị truyền qua kết nối. HTTP/2 có thể xen kẽ frame giữa nhiều stream, nhưng **giữ nguyên thứ tự frame trong mỗi stream** theo protocol. Stream không đồng nhất với Java `Thread`, `CompletableFuture` hay TCP socket.

| Khái niệm | Thực chất |
| --- | --- |
| TCP connection | Luồng byte có thứ tự giữa hai endpoint; chịu TCP flow/congestion control |
| HTTP/2 connection | Nhiều stream cùng dùng một kết nối, chung SETTINGS và connection window |
| HTTP/2 stream | Request/response logic, có stream ID, lifecycle và stream window |
| HTTP/2 frame | Đơn vị trên dây chứa type/flags/stream ID/payload |
| Java `CompletableFuture` | Đại diện kết quả async, **không** được mặc nhiên xem là stream ID hoặc TCP connection |
| HTTP/2 flow-control credit | Số **octet DATA frame payload** sender hiện được phép gửi |

### 1.1. Stream ID và lifecycle

- Mỗi stream được nhận diện bằng **stream identifier 31-bit khác 0**. Trong HTTP/2, stream khởi tạo bởi client dùng **ID lẻ**, stream khởi tạo bởi server dùng **ID chẵn**. ID 0 dành cho một số điều khiển ở cấp **connection**, không phải một request stream.
- Một stream có thể ở trạng thái `idle`, `open`, `half-closed (local)`, `half-closed (remote)` và `closed`; các frame và `END_STREAM` chuyển trạng thái theo quy tắc RFC 9113.
- `END_STREAM` có thể nằm trên HEADERS hoặc DATA để chỉ bên gửi kết thúc phần của mình. Một response có thể gồm nhiều DATA frames; **không** suy từ một DATA frame rằng response hoàn tất.
- `RST_STREAM` hủy stream; trong nhiều trường hợp các stream khác trên connection vẫn tiếp tục. `GOAWAY` giúp điều phối kết thúc connection và xử lý stream IDs khi shutdown.
- Stream IDs trong cùng connection không được tái sử dụng. Khi application retry có thể tạo stream mới; retry POST không mặc định an toàn nếu server có thể đã xử lý side effects.

HTTP/1.1 có thể xử lý concurrency bằng nhiều kết nối, vì vậy nói “HTTP/1.1 không bao giờ song song” là sai. Khác biệt thiết kế của HTTP/2 là **nhiều request/response được multiplex bằng frames qua một kết nối đã thiết lập**.

### 1.2. Mối quan hệ với TLS và ALPN

Khi HTTP/2 chạy trên HTTPS, TLS ALPN thường thương lượng protocol ID **`h2`**. Nếu server/proxy không hỗ trợ hoặc chính sách TLS không cho phép, client có thể dùng HTTP/1.1. HTTP/2 cleartext `h2c` là trường hợp khác và không đồng nghĩa mọi server HTTP đều hỗ trợ upgrade. Trong Java `HttpClient.Version.HTTP_2` nghĩa là **ưu tiên** HTTP/2, không phải cưỡng ép peer.

Không đánh đồng HTTP/2 với HTTP/3: HTTP/3 sử dụng QUIC, có cơ chế stream/transport khác. **TCP-level head-of-line blocking vẫn tồn tại trong HTTP/2**, vì byte của các stream đi trên cùng một luồng TCP đã sắp thứ tự.

## 2. HTTP/2 frame và dữ liệu nào bị giới hạn bởi window?

Mỗi HTTP/2 frame có **9 byte header** (length, type, flags, stream ID) và một payload có độ dài do trường Length quyết định. Những frame quan trọng:

| Frame | Chức năng | Bị HTTP/2 flow control không? |
| --- | --- | --- |
| `HEADERS` | Headers request/response hoặc trailers | Không |
| `CONTINUATION` | Phần nối của header block | Không |
| `DATA` | Nội dung body của HTTP message | **Có** |
| `SETTINGS` | Trao đổi giới hạn/thiết lập connection | Không |
| `WINDOW_UPDATE` | Tăng stream hoặc connection window | Không |
| `PING` | Kiểm tra round-trip/liveness của HTTP/2 connection | Không |
| `RST_STREAM` | Hủy một stream | Không |
| `GOAWAY` | Thông báo kết thúc connection | Không |

Theo RFC 9113, chỉ **DATA** trong những frame type được định nghĩa sẵn chịu HTTP/2 flow control. `HEADERS` và control frames không trừ vào window, nhưng **vẫn tiêu thụ CPU, mạng, bộ nhớ**. Cần có header limits, control-frame limits và protection chống overload riêng.

**Đếm byte đúng:** toàn bộ **DATA frame payload** bị trừ khỏi stream và connection windows, **bao gồm padding và Pad Length field nếu có**; header 9 byte **không** tính.

~~~text
DATA frame:
  9-byte frame header         -> KHÔNG trừ flow control
  100-byte actual body        -> trừ 100
  1-byte Pad Length field     -> trừ 1
  7-byte Padding              -> trừ 7

Total DATA flow-control usage = 100 + 1 + 7 = 108 bytes.
~~~

Mặc định `SETTINGS_MAX_FRAME_SIZE` cho phép DATA/frame payload tối đa **16.384 bytes**, trừ khi peer công bố giá trị lớn hơn theo protocol. Đây là giới hạn **mỗi frame**, không phải giới hạn toàn bộ HTTP body hoặc stream window.

### 2.1. HTTP message được thể hiện bằng nhiều frames

Một HTTP response lớn có thể là HEADERS rồi nhiều DATA frames và cuối cùng `END_STREAM`. Một `HEADERS` frame có thể chứa header block hoặc trailer section. Header compression HPACK làm kích thước trên dây khác với header text, nhưng không chuyển HEADERS thành DATA. HTTP/2 còn dùng pseudo-headers như `:method`, `:scheme`, `:authority` và `:path`; application dùng `java.net.http.HttpClient` không phải tự viết các frames này.

Đừng đưa bừa HTTP/1.1 connection-specific headers vào HTTP/2: `Connection`, `Keep-Alive`, `Upgrade` và một số trường tương tự bị ràng buộc bởi RFC 9113. `TE` chỉ có ngoại lệ cụ thể cho `trailers`. Một HTTP/2 library đúng chuẩn xử lý framing/header rules.

## 3. Flow control ở hai cấp: stream và connection

Giả sử server gửi response DATA cho client; về mặt credit do **client nhận** quảng bá, server duy trì:

- `connectionWindow` — số byte DATA client cho phép server gửi thêm trên **toàn connection**.
- `streamWindow[streamId]` — số byte DATA client cho phép server gửi thêm trên **stream đó**.
- Giới hạn frame payload của peer.

Với DATA không padding, lượng body tối đa có thể tạo một frame trong thời điểm ấy xấp xỉ:

~~~text
allowedDataBytes = min(
    bytesWaitingToSend,
    connectionWindow,
    streamWindow[streamId],
    maxFramePayload
)
~~~

Nếu connection window = 0, **mọi stream** trên kết nối trong hướng gửi đó bị chặn DATA, cho dù từng stream window còn lớn. Nếu stream 1 window = 0 và connection window còn dương, **chỉ stream 1** bị chặn, những stream khác vẫn có thể gửi.

Ví dụ:

~~~text
Connection window còn 2.000 DATA bytes.

Stream 1 window còn 800  -> tối đa 800 nếu được gửi trước.
Stream 3 window còn 4.000 -> tối đa 2.000 nếu được gửi trước.
Stream 5 window còn 1.000 -> tối đa 1.000 nếu được gửi trước.

Nhưng tổng DATA được phép gửi trên cả ba vẫn ≤ 2.000
trước khi receiver quảng bá thêm connection credit.
~~~

Đây là **hai ngân sách lồng nhau**, không phải chia sẵn mỗi stream một phần cố định của connection window. Scheduler bên gửi quyết định stream nào dùng credit trước; RFC không cam kết mỗi stream luôn có cùng phần băng thông.

### 3.1. Giá trị mặc định 65.535 bytes

Theo RFC 9113:

- Khi connection mới được tạo, **initial connection flow-control window = 65.535 octet**.
- Khi một stream mới được tạo, **initial stream flow-control window = 65.535 octet**.
- Receiver có thể điều chỉnh stream initial window bằng `SETTINGS_INITIAL_WINDOW_SIZE`.
- **Connection window không thay đổi bằng `SETTINGS_INITIAL_WINDOW_SIZE`**; nó được mở thêm bằng `WINDOW_UPDATE` có stream ID **0**.

`65.535` chỉ là **credit ban đầu**, không phải “kích thước body HTTP/2 tối đa”. Response lớn nhiều MB hoặc GB được chia thành frames và sử dụng liên tiếp `WINDOW_UPDATE`. Bên gửi cũng chịu TCP/kernel buffers, congestion và các giới hạn ứng dụng.

### 3.2. Flow control có hướng và theo chặng

- Các windows áp dụng cho **một hướng truyền DATA**; client nhận response và server nhận upload có state riêng.
- HTTP/2 flow control là **hop-by-hop** giữa hai endpoint của **một connection**, không phải WINDOW_UPDATE được chuyển y nguyên end-to-end.
- Với client → proxy → origin, proxy phải quản lý cửa sổ riêng cho connection phía client và phía origin; nếu downstream chậm, proxy cần backpressure thật qua các tầng, không để outbound queue vô hạn.

Ví dụ:

~~~text
Browser --HTTP/2 connection A--> Proxy --HTTP/2 connection B--> Origin
          windows A riêng               windows B riêng

Proxy KHÔNG forward nguyên frame WINDOW_UPDATE A qua B.
Proxy tự điều tiết dữ liệu và memory buffer giữa hai connection.
~~~

## 4. WINDOW_UPDATE: cấp thêm credit khi receiver sẵn sàng

`WINDOW_UPDATE` (type `0x08`) có payload 4 bytes, với **Window Size Increment** 31-bit:

- `WINDOW_UPDATE(stream=0, increment=N)` tăng **connection window**.
- `WINDOW_UPDATE(stream=S, increment=N)` với `S != 0` tăng **stream S window**.
- Increment hợp lệ nằm trong **1..2.147.483.647** bytes.
- Increment bằng **0** là protocol error, không phải “no-op”.
- Flow-control window không được vượt **2^31−1**; overflow là `FLOW_CONTROL_ERROR` theo phạm vi được quy định.

Sau khi gửi một DATA frame có payload `N` bytes, sender giảm **cả stream window lẫn connection window N bytes**. Khi receiver đã xử lý/tiêu thụ và có thêm sức chứa, nó có thể gửi `WINDOW_UPDATE` tương ứng.

Ví dụ:

~~~text
Hiện tại: connectionWindow=0, stream1Window=300, stream3Window=800.

WINDOW_UPDATE(stream=1, +1.000):
  connectionWindow=0, stream1Window=1.300
  -> stream 1 VẪN KHÔNG gửi DATA vì connection=0.

WINDOW_UPDATE(stream=0, +600):
  connectionWindow=600, stream1Window=1.300
  -> stream 1 có thể gửi tối đa 600 DATA bytes.

Nếu stream 1 gửi 400:
  connectionWindow=200, stream1Window=900.
  -> stream 3 vẫn có thể dùng 200 bytes connection credit.
~~~

**WINDOW_UPDATE frames không chịu DATA flow control**, nên phải tiếp tục được xử lý khi DATA windows đã hết. Nếu implementation chỉ chuyển WINDOW_UPDATE sau khi gửi được DATA, hai phía có nguy cơ deadlock. Receiver cũng nên tránh phát vô số WINDOW_UPDATE increments 1 byte vì tốn network/CPU overhead; RFC để implementation tự quyết định thuật toán batching.

### 4.1. SETTINGS_INITIAL_WINDOW_SIZE khác WINDOW_UPDATE

`SETTINGS_INITIAL_WINDOW_SIZE` (setting ID `0x04`) thay đổi **initial window dành cho streams**, theo công thức:

~~~text
delta = newInitialStreamWindow - oldInitialStreamWindow
newWindowForEachActiveStream = oldWindowForThatStream + delta
~~~

Khi một SETTINGS thay đổi initial stream window, sender cập nhật **các active stream windows chịu ảnh hưởng**, kể cả stream đã tồn tại trước SETTINGS. Connection window **không đổi**.

Một khác biệt dễ bỏ qua: nếu SETTINGS giảm initial size mạnh, **stream window có thể âm**. Đây không mặc định là protocol error. Sender phải theo dõi giá trị âm và ngừng DATA trên stream đó tới khi đủ WINDOW_UPDATE làm window dương.

Ví dụ:

~~~text
Initial stream window = 65.535
Stream A đã tiêu thụ 60.000 -> window A = 5.535

Peer đặt SETTINGS_INITIAL_WINDOW_SIZE = 16.384
delta = 16.384 - 65.535 = -49.151
window A = 5.535 - 49.151 = -43.616

Stream A không được gửi thêm DATA cho tới khi có credit mới.
Connection window không bị SETTINGS thay đổi.
~~~

Giảm window trên receiver có thể xảy ra trong lúc sender còn dữ liệu in flight theo setting cũ. Receiver phải xử lý sự chuyển đổi theo RFC, không coi bất kỳ byte nào vừa đến sau SETTINGS giảm đều tự động là tấn công.

## 5. Ví dụ Java 17+ thứ nhất: mô hình hai cấp cửa sổ và SETTINGS âm

Đây là **mô hình toán học**, không gửi HTTP/2 frame thực. Để dễ tính, nó dùng connection window **10 bytes**, mỗi stream window **8 bytes** — cố ý nhỏ hơn 65.535 chuẩn. Hai stream được đánh ID 1 và 3; `send` giả lập lượng DATA được phép gửi theo cả hai giới hạn.

Tạo file **`Http2WindowModelDemo.java`**:

~~~java
import java.util.*;

public final class Http2WindowModelDemo {
    private static final long MAX_WINDOW = (1L << 31) - 1;
    private final Map<Integer, Long> windows =
            new LinkedHashMap<>();
    private long connection = 10;
    private int initialStream = 8;

    private void open(int id) {
        windows.put(id, (long) initialStream);
    }

    private int send(int id, int wanted) {
        long stream = windows.get(id);
        int sent = (int) Math.max(0, Math.min((long) wanted,
                Math.min(connection, stream)));
        connection -= sent;
        windows.put(id, stream - sent);
        return sent;
    }

    private void windowUpdate(int id, int increment) {
        if (increment < 1) {
            throw new IllegalArgumentException("increment");
        }
        long previous =
                id == 0 ? connection : windows.get(id);
        long next = previous + increment;
        if (next > MAX_WINDOW) {
            throw new IllegalStateException("window overflow");
        }
        if (id == 0) connection = next;
        else windows.put(id, next);
    }

    private void changeInitialStreamWindow(int newSize) {
        if (newSize < 0 || newSize > MAX_WINDOW) {
            throw new IllegalArgumentException("newSize");
        }
        long delta = (long) newSize - initialStream;
        for (int id : windows.keySet()) {
            long next = windows.get(id) + delta;
            if (next > MAX_WINDOW) {
                throw new IllegalStateException("overflow");
            }
            windows.put(id, next); // âm có thể hợp lệ
        }
        initialStream = newSize;
    }

    public static void main(String[] args) {
        Http2WindowModelDemo m = new Http2WindowModelDemo();
        m.open(1);
        m.open(3);
        System.out.println("s1 first: " + m.send(1, 7));
        System.out.println("s3 first: " + m.send(3, 6));
        System.out.println(
                "s1 blocked by connection: " + m.send(1, 4));

        m.windowUpdate(0, 6); // connection update
        System.out.println(
                "s1 after conn update: " + m.send(1, 4));
        m.windowUpdate(1, 4); // stream 1 update
        System.out.println(
                "s1 after stream update: " + m.send(1, 4));
        System.out.println("s3 last: " + m.send(3, 4));

        m.changeInitialStreamWindow(4); // 8 -> 4, delta -4
        System.out.println(
                "s1 after smaller SETTINGS: " + m.windows.get(1));
        System.out.println(
                "s3 after smaller SETTINGS: " + m.windows.get(3));
        System.out.println(
                "connection unchanged by SETTINGS: " + m.connection);
    }
}
~~~

~~~bash
javac --release 17 Http2WindowModelDemo.java
java Http2WindowModelDemo
~~~

Stdout **chính xác**, đã thử bằng JDK cục bộ:

~~~text
s1 first: 7
s3 first: 3
s1 blocked by connection: 0
s1 after conn update: 1
s1 after stream update: 4
s3 last: 1
s1 after smaller SETTINGS: -4
s3 after smaller SETTINGS: 0
connection unchanged by SETTINGS: 0
~~~

Cách tính:

1. S1 gửi 7: stream1 8→1, connection 10→3.
2. S3 muốn gửi 6 nhưng connection còn 3: chỉ gửi 3, stream3 8→5, connection 3→0.
3. S1 còn stream credit=1 nhưng connection=0: không gửi thêm DATA.
4. `WINDOW_UPDATE(stream=0,+6)` mở connection=6; S1 có thể gửi thêm **1** theo stream window.
5. `WINDOW_UPDATE(stream=1,+4)` mở stream1=4; S1 gửi 4, connection giảm 5→1.
6. S3 có stream credit=5 nhưng connection còn 1: chỉ gửi 1.
7. SETTINGS initial stream từ 8 xuống 4 (delta=-4): S1 từ 0 xuống **-4**, S3 từ 4 xuống **0**; connection vẫn **0**.

Ví dụ không mô phỏng frame payload padding, stream state machine, HPACK hay TCP. Không lấy các hàm `send` của simulator làm HTTP/2 library production.

## 6. Concurrency limit không phải window: SETTINGS_MAX_CONCURRENT_STREAMS

`SETTINGS_MAX_CONCURRENT_STREAMS` (setting ID `0x03`) giới hạn **số stream concurrent mà một endpoint cho phép endpoint kia mở**. Setting **directional**. Theo RFC 9113 ban đầu không áp một con số tối đa mặc định, và khuyến nghị giá trị do endpoint công bố không quá thấp (khuyến nghị ít nhất khoảng 100) để không vô tình bóp parallelism. **Đây không phải lời hứa tất cả server luôn cho 100 streams.**

Ví dụ server quảng bá `MAX_CONCURRENT_STREAMS=20`, client đã có 20 streams active; việc mở stream thứ 21 trên cùng connection cần tuân thủ hạn mức. Một HTTP client có thể queue request, giới hạn concurrency hoặc dùng chiến lược connection khác tùy implementation — không nên tự dự đoán.

| Cơ chế | Đơn vị | Nó giới hạn |
| --- | --- | --- |
| `SETTINGS_MAX_CONCURRENT_STREAMS` | Số stream | Số stream có thể active cùng lúc |
| `SETTINGS_INITIAL_WINDOW_SIZE` | DATA bytes | Stream-level initial credit |
| Connection `WINDOW_UPDATE` | DATA bytes | Connection-level credit |
| `SETTINGS_MAX_FRAME_SIZE` | Bytes/frame | Payload tối đa của một frame |
| App memory budget | Bytes/requests/tasks | Bộ nhớ, tài nguyên application |
| TCP congestion/receive windows | Bytes/transport | Khả năng gửi/nhận trong TCP/network |

Thay max concurrent streams không tự tăng DATA window, và tăng DATA window không tự cho phép mở thêm streams. Cần giới hạn cả **CPU, upstream workers, DB queries, heap**, không chỉ dùng một HTTP/2 setting.

## 7. HTTP/2 flow control không phải TCP congestion control

HTTP/2 flow control là **receiver-driven credit scheme** cho **DATA frame payload**. Nó không hạn chế lưu lượng HEADERS/control frames theo cùng window. Trong khi đó, TCP:
- Đảm bảo byte stream có thứ tự.
- Dùng receive window và congestion control để bảo vệ kernel/network.
- Có thể chậm do retransmission, RTT và buffer constraints.

**HTTP/2 không xóa TCP-level head-of-line blocking**. Nếu một TCP segment bị mất, bytes của những frame phía sau có thể bị giữ lại cho đến khi TCP tái truyền và giao dữ liệu theo thứ tự — kể cả khi chúng thuộc stream khác.

Một stream lớn có thể bị giới hạn vì **stream window=0**; mọi stream có thể bị giới hạn vì **connection window=0**; tất cả dữ liệu trên connection còn có thể chậm vì **TCP congestion**. Phải phân loại đúng nguyên nhân trước khi điều chỉnh tuning.

## 8. Java 17 `HttpClient`: ưu tiên HTTP/2, kiểm tra actual version

Module `java.net.http` cung cấp `HttpClient` từ Java 11. API:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

Đây là **đoạn minh họa cần `import java.net.http.HttpClient;`**. `HTTP_2` là phiên bản **ưu tiên**, không phải một lệnh bắt server nói HTTP/2. Thư viện có thể dùng HTTP/1.1 khi server/proxy/ALPN/h2c policy không hỗ trợ.

Hai phép kiểm tra khác nhau:

~~~java
client.version();   // preferred, ví dụ HTTP_2
response.version(); // actual version trên response cụ thể
~~~

Với HTTPS, ALPN `h2` là con đường phổ biến để dùng HTTP/2. Đừng tự đặt `Upgrade: h2c` hoặc đổi text `HTTP/1.1` thành `HTTP/2` để ép protocol. Java HttpClient sẽ điều phối HTTP framing, header compression, stream IDs, DATA windows và việc nhận/sinh WINDOW_UPDATE nội bộ.

### 8.1. Các request đồng thời không chứng minh cùng TCP connection

~~~java
CompletableFuture<HttpResponse<Void>> a =
        client.sendAsync(reqA, HttpResponse.BodyHandlers.discarding());
CompletableFuture<HttpResponse<Void>> b =
        client.sendAsync(reqB, HttpResponse.BodyHandlers.discarding());
~~~

Đây là **đoạn minh họa** với `client`, `reqA`, `reqB` có sẵn. Nó tạo hai HTTP requests async, có cơ hội multiplex khi:
- cùng origin và connection có thể tái sử dụng;
- TLS/ALPN hoặc h2c thực sự chọn HTTP/2;
- server cho phép số concurrent streams cần thiết;
- implementation không quyết định sử dụng connection khác.

**Hai futures chạy song song ≠ bằng chứng có hai streams trên cùng một HTTP/2 connection.** `response.version()==HTTP_2` chứng minh response dùng HTTP/2, nhưng muốn xác nhận **cùng một TCP connection** phải có tracing/metrics của HTTP stack, server/proxy hoặc packet capture được phép.

## 9. Ví dụ Java 17+ thứ hai: HTTP/2 preference fallback trên loopback

Ví dụ độc lập không dùng internet: tạo một `HttpServer` HTTP/1.1 của JDK trên loopback, sau đó dùng `HttpClient` **ưu tiên HTTP/2** gửi đồng thời hai requests. Server này chỉ nói HTTP/1.1, vì vậy phiên bản thực tế của hai responses là HTTP/1.1.

Tạo file **`Http2LocalFallbackDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.*;

public final class Http2LocalFallbackDemo {
    public static void main(String[] args) throws Exception {
        InetAddress host = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(host, 0), 0);

        server.createContext("/demo", exchange -> {
            byte[] body = "OK".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();

        try {
            URI uri = new URI("http", null,
                    host.getHostAddress(),
                    server.getAddress().getPort(),
                    "/demo", null, null);

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_2)
                    .connectTimeout(Duration.ofSeconds(5))
                    .build();

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();

            CompletableFuture<HttpResponse<String>> a =
                    client.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString());
            CompletableFuture<HttpResponse<String>> b =
                    client.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString());

            HttpResponse<String> first =
                    a.get(10, TimeUnit.SECONDS);
            HttpResponse<String> second =
                    b.get(10, TimeUnit.SECONDS);

            System.out.println("preferred: " + client.version());
            System.out.println("response 1: " + first.version());
            System.out.println("response 2: " + second.version());
            System.out.println("bodies: " + first.body() + ", " +
                    second.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac --release 17 Http2LocalFallbackDemo.java
java Http2LocalFallbackDemo
~~~

Stdout đã xác nhận trên JDK cục bộ có loopback khả dụng:

~~~text
preferred: HTTP_2
response 1: HTTP_1_1
response 2: HTTP_1_1
bodies: OK, OK
~~~

Bài học: **phiên bản client ưu tiên không nhất thiết là phiên bản response thực**. Đoạn code cũng chứng minh `sendAsync` dùng được cho hai requests, **nhưng không thể chứng minh HTTP/2 multiplexing** vì server cố tình không nói h2.

Ứng dụng tự giải phóng server trong `finally`. `com.sun.net.httpserver.HttpServer` nằm trong module `jdk.httpserver` của JDK; nó có thể không nằm trong một Java runtime image rút gọn. Nếu sandbox chặn bind loopback, việc chạy có thể lỗi I/O; đây không phải lỗi cú pháp.

## 10. Ví dụ Java 17+ thứ ba: probe hai HTTP/2 requests tới HTTPS server

Dùng khi có endpoint HTTPS **được phép thử**. Chương trình ưu tiên HTTP/2 và gửi hai GET async tới cùng một URL. Mỗi response ghi protocol actual cùng status. Chỉ dùng response body discarding vì bài này muốn quan sát phiên bản, không xử lý nội dung.

Tạo file **`Http2ConcurrentProbe.java`**:

~~~java
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.concurrent.*;

public final class Http2ConcurrentProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java Http2ConcurrentProbe <https-url>");
            return;
        }

        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null) {
            throw new IllegalArgumentException("Use a valid HTTPS URL");
        }

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(15))
                .GET().build();

        CompletableFuture<HttpResponse<Void>> first =
                client.sendAsync(request,
                        HttpResponse.BodyHandlers.discarding());
        CompletableFuture<HttpResponse<Void>> second =
                client.sendAsync(request,
                        HttpResponse.BodyHandlers.discarding());

        HttpResponse<Void> a =
                first.get(20, TimeUnit.SECONDS);
        HttpResponse<Void> b =
                second.get(20, TimeUnit.SECONDS);

        System.out.println("preferred: " + client.version());
        System.out.println("response 1: " +
                a.version() + " / " + a.statusCode());
        System.out.println("response 2: " +
                b.version() + " / " + b.statusCode());
        System.out.println("both HTTP/2: " +
                (a.version() == HttpClient.Version.HTTP_2
                        && b.version() == HttpClient.Version.HTTP_2));
    }
}
~~~

~~~bash
javac --release 17 Http2ConcurrentProbe.java
java Http2ConcurrentProbe
~~~

Chạy không tham số: **stdout chính xác**.

~~~text
Usage: java Http2ConcurrentProbe <https-url>
~~~

Với endpoint được phép kiểm thử:

~~~bash
java Http2ConcurrentProbe "https://your-approved-host.example/health"
~~~

**Không thể cam kết stdout của endpoint thật.** Nếu server chọn HTTP/2, các dòng có thể là `response 1: HTTP_2 / 200` và `response 2: HTTP_2 / 200`. Nếu server không hỗ trợ, có thể là `HTTP_1_1`, hoặc status khác. DNS, proxy, certificate, TLS handshake và timeout đều có thể gây lỗi. **Chưa thực hiện kết nối tới host thực trong quá trình kiểm tra ví dụ**; code và nhánh usage được xác nhận trên JDK cục bộ.

Không lấy `both HTTP/2: true` làm bằng chứng cả hai đã dùng *cùng một TCP connection* — chỉ đủ chứng minh cả hai responses dùng protocol HTTP/2.

## 11. Hai tầng backpressure: HTTP/2 WINDOW_UPDATE và Java Flow

`HttpClient` của Java 17 tự quản lý HTTP/2 framing, stream/connection windows và WINDOW_UPDATE. Public API **không có** `sendWindowUpdate(streamId, bytes)` cho ứng dụng. Tuy vậy application vẫn phải thiết kế xử lý **response body** không tràn bộ nhớ khi consumer chậm.

~~~text
Peer HTTP/2 DATA frames
        │
        ▼
HttpClient internal HTTP/2 parser + windows + network buffers
        │
        ▼
BodySubscriber / Flow.Subscriber<List<ByteBuffer>>
        │
        │ request(n) nghĩa là n item/onNext, KHÔNG phải n bytes
        ▼
application body consumer / parser / file / database
        │
        └── chậm -> bounded queues, controlled demand, cancel/close
~~~

**Không quy đổi `subscription.request(1)` thành một `WINDOW_UPDATE(+1 byte)`.** Java `Flow.Subscription.request(n)` đếm **items**. Mỗi item có thể là `List<ByteBuffer>` với kích thước byte tùy biến. HTTP/2 flow control lại tính **DATA frame payload bytes**. Thư viện có thể nối hai tầng này theo thuật toán của nó, không phải ánh xạ 1:1 công khai.

### 11.1. Chọn BodyHandler phù hợp độ lớn body

| API | Dữ liệu được trả | Lưu ý resource/backpressure |
| --- | --- | --- |
| `BodyHandlers.ofString()` | Toàn body dưới dạng `String` | Có thể giữ lượng lớn memory |
| `BodyHandlers.ofByteArray()` | Toàn body dạng byte[] | Không dùng vô giới hạn cho nội dung rất lớn |
| `BodyHandlers.discarding()` | Loại bỏ body sau khi tiêu thụ | Phù hợp khi chỉ cần status/headers |
| `BodyHandlers.ofInputStream()` | `InputStream` đọc tăng dần | Phải đọc hết tới EOF hoặc gọi `close()` |
| `BodyHandlers.ofFile(path)` | Ghi body xuống file | Cần giới hạn dung lượng/disk quota và cleanup file lỗi |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | Subscriber phải request/cancel đúng và có bounded processing |

Ví dụ **minh họa** xử lý body theo khối nhỏ, đặt trong phương thức Java có `client`, `request`, import `java.net.http.*`, `java.io.*` và hàm nghiệp vụ `processChunk`:

~~~java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] chunk = new byte[8192];
    int n;
    long total = 0;
    while ((n = body.read(chunk)) != -1) {
        total += n;
        if (total > 100_000_000L) {
            throw new IOException("Body too large");
        }
        processChunk(chunk, n);
    }
}
~~~

Đoạn này **không phải class runnable độc lập**, vì `processChunk` là logic ứng dụng. Nó tránh tích toàn bộ body 100MB vào một byte[]; nhưng tổng bộ nhớ ứng dụng còn phụ thuộc parser, HTTP internal buffering và downstream queue. Nếu không còn muốn tiếp tục, phải đóng stream để giải phóng tài nguyên.

Theo Javadoc, `BodySubscriber` nên request dữ liệu đến khi nhận `onComplete`/`onError`, hoặc `cancel` khi không thể xử lý. Hủy sớm có thể làm HTTP connection không được tái sử dụng tùy protocol/implementation. Không bỏ subscription treo vĩnh viễn.

### 11.2. Khi app làm proxy / HTTP gateway

Proxy nhận HTTP/2 body rồi chuyển tới upstream. Nếu upstream phản hồi hoặc downstream client tiêu thụ chậm, proxy không được lấy mọi bytes từ upstream vào queue vô hạn. Phải liên kết:
- Input/body publisher demand.
- Capacity của application queue ở mỗi chiều.
- Output consumer/readiness.
- Chính sách timeout/cancel khi peer quá chậm.
- Flow-control riêng của từng connection HTTP/2; không forward nguyên WINDOW_UPDATE giữa các chặng.

Nếu nhiều streams chung connection, giới hạn memory **per stream và global**; đừng dùng một window rộng rồi cho phép một stream chiếm toàn bộ heap.

### 11.3. Backpressure không phải request rate limiting

| Cơ chế | Giải quyết |
| --- | --- |
| HTTP/2 `WINDOW_UPDATE` | Số DATA bytes endpoint có thể nhận trên stream/connection |
| Java `Flow.Subscription.request(n)` | Số emissions/chunks downstream yêu cầu |
| `MAX_CONCURRENT_STREAMS` | Số stream active được peer cho phép |
| Application semaphore/executor cap | Số request/task backend chạy đồng thời |
| API rate limit | QPS/requests per tenant/time window |
| TCP congestion window | Khả năng gửi theo điều kiện mạng/RTT/loss |

Có thể cần **tất cả** các lớp ở một server tải lớn. Một HTTP/2 stream window dương không chứng minh CPU/DB có thể xử lý nhiều requests. Một semaphore giới hạn concurrency không thay thế credit của DATA frames.

## 12. Khi receiver chậm: phối hợp queue, scheduler và window

Một hệ thống thực có thể có pipeline:

~~~text
app upstream producer -> bounded per-stream queue -> HTTP/2 DATA scheduler
                                     │                  │
                                     │                  ├─ stream window
                                     │                  └─ connection window
                                     ▼
                             bounded connection memory
                                     │
                                     ▼
                             TLS/TCP kernel buffers -> receiver
~~~

Khi downstream tạm ngừng tiêu thụ body, cửa sổ HTTP/2 có thể giảm tới 0. Sender phải chờ WINDOW_UPDATE trước khi gửi DATA; nếu producer vẫn tạo bytes và đặt vào queue vô hạn, **flow control trên dây không cứu ứng dụng khỏi OOM**.

Checklist thiết kế server/proxy:

1. **Bounded per-stream queue** theo số byte, không chỉ số message.
2. **Global memory budget** theo connection/tenant/server, kể cả header parser, TLS buffers và producer tasks.
3. **Backpressure lên producer** khi queue/high watermark đạt ngưỡng; resume theo low watermark.
4. **Fair scheduling** để stream có response lớn không monopolize event loop.
5. **Processing of control frames** độc lập với DATA credit.
6. **Timeout và cancellation** cho stream bị kẹt lâu, cleanup on RST_STREAM/GOAWAY.
7. **Monitoring** số stream active, bytes chờ, stream/connection window, timeout và TCP retransmission.

Tăng `SETTINGS_INITIAL_WINDOW_SIZE` quá cao có thể tăng throughput khi bandwidth-delay product lớn, nhưng cũng khiến receiver phải bảo đảm memory và chính sách xử lý tương ứng. Không coi việc tăng window là cách “sửa mọi vấn đề tốc độ”.

## 13. HTTP/2 không bảo đảm công bằng tuyệt đối giữa streams

Stream 1 có body rất lớn, stream 3 có body nhỏ và urgent. Vì cả hai dùng chung connection window và một TCP connection, nếu scheduler luôn ưu tiên stream 1 cho tới khi connection window=0, stream 3 cũng phải chờ dù stream window còn đầy.

RFC cho phép các chiến lược scheduling khác nhau; một số priority mechanisms cũ của HTTP/2 đã bị deprecated trong RFC 9113. Không dựa vào một thứ tự priority cố định khi thiết kế SLA. Phía ứng dụng nên:
- Giới hạn bytes mỗi stream được producer enqueue.
- Có chính sách fairness trong scheduler được thư viện/server hỗ trợ.
- Quan sát latency của request nhỏ khi đồng thời tải object lớn.
- Dùng timeout, cancellation và flow-control metrics khi debug.
- Không khai báo một HTTP/2 stream “được bảo đảm không bao giờ bị ảnh hưởng bởi những stream khác”.

Ngoài shared connection window, **TCP HOL** vẫn tồn tại. Mất một TCP segment khiến mọi byte phía sau trong cùng connection có thể chờ retransmission, cho dù chúng thuộc streams khác nhau.

## 14. Xử lý lỗi HTTP/2 và retry đúng ngữ nghĩa

| Hiện tượng | Điều cần xem |
| --- | --- |
| Một stream dừng, streams khác tiếp tục | Stream window=0, app subscriber không request, RST_STREAM hoặc stream state |
| Nhiều response DATA đều dừng | Connection window=0, TCP congestion, blocked event loop hoặc proxy queue |
| Đã có stream WINDOW_UPDATE mà DATA vẫn không chạy | Có thể thiếu connection-level WINDOW_UPDATE |
| WINDOW_UPDATE increment 0 | Protocol error, không được coi là giữ nguyên |
| Window vượt 2^31−1 | FLOW_CONTROL_ERROR theo scope tương ứng |
| Stream window âm sau SETTINGS giảm | Được phép trong chuyển đổi; chờ đủ credit |
| Java client muốn HTTP_2 nhưng nhận HTTP_1_1 | ALPN/h2c/implementation/server/proxy không chọn HTTP/2 |
| Heap tăng theo body download | BodyHandlers.ofByteArray/ofString hoặc queue không bounded |
| Stream mới bị từ chối | MAX_CONCURRENT_STREAMS, admission hoặc server policy |
| RST_STREAM / GOAWAY | Hủy stream hoặc kết thúc connection, phải phân biệt với HTTP status |
| Nội dung HTTP/2 parser sai | HEADERS/CONTINUATION/HPACK/state/pseudo-header rules |

**`RST_STREAM`** đóng một stream chứ không nhất thiết đóng cả connection. **`GOAWAY`** dùng để phối hợp đóng connection, có thông tin về last stream ID giúp phân tích luồng nào có thể đã được xử lý. Đừng tự retry toàn bộ POST có side effect chỉ vì thấy GOAWAY hoặc timeout. Cần bảo đảm idempotency hoặc quy trình xác minh/compensation.

Ứng dụng Java `HttpClient` có thể ném `IOException`, `HttpTimeoutException`, `CompletionException` và các lỗi transport khác; không phải mọi HTTP/2 error code đều được public API trả ra như enum trực tiếp. Test retry phải bảo vệ khỏi gửi trùng side effects.

## 15. Kiểm thử HTTP/2 multiplexing và flow control

### 15.1. Bằng chứng ba tầng

1. **Preferred version**: `client.version()==HTTP_2`. Chỉ xác nhận cài đặt client.
2. **Actual version**: `response.version()==HTTP_2`. Xác nhận response này thực sự dùng HTTP/2.
3. **Multiplex trên cùng connection**: tracing cho thấy **ít nhất hai stream IDs cùng active qua một connection**. Hai Java futures hoặc hai HTTP_2 responses **chưa tự chứng minh** cùng connection.

Muốn có bằng chứng tầng 3, dùng server/proxy HTTP/2 metrics hoặc packet trace có quyền và đủ khả năng quan sát TLS/HTTP/2; không tự suy từ timings của hai futures.

### 15.2. Test slow receiver

1. Dựng server HTTPS hỗ trợ HTTP/2 và TLS ALPN `h2` trong môi trường test.
2. Mở nhiều responses lớn tới cùng origin; log stream-specific request IDs.
3. Làm một response consumer đọc chậm hoặc dừng yêu cầu chunks theo controlled test.
4. Quan sát per-stream window, connection window, queue bytes, response progress.
5. Xác minh khi stream A không còn credit, stream B vẫn tiến triển nếu **connection window và B window còn credit**.
6. Làm connection window cạn; xác minh không DATA stream nào vượt credit, nhưng WINDOW_UPDATE/control frames vẫn xử lý được.
7. Tiếp tục consumer, quan sát thêm credit và verify byte counts/hash toàn nội dung, không mất/trùng.
8. Cancel một response; xác minh release subscription, queue, stream state; test GOAWAY khi shutdown.
9. Giới hạn thời gian test và số byte; không load-test production chưa được cho phép.

### 15.3. Metrics hữu ích

| Metric | Công dụng |
| --- | --- |
| `active_http2_streams` | Phân biệt concurrency với số TCP sockets |
| `stream_window_available` | Tình trạng DATA credit per stream |
| `connection_window_available` | DATA credit chung, phát hiện mọi stream bị chặn |
| `http2_window_updates_total` | Theo dõi credit replenishment |
| `flow_control_blocked_duration` | Thời gian stream/connection đợi credit |
| `pending_response_bytes` | Buffer ở tầng ứng dụng, bảo vệ bộ nhớ |
| `response.version` histogram | Tỷ lệ HTTP_2 vs HTTP_1_1 fallback |
| `RST_STREAM` / `GOAWAY` counts | Lỗi lifecycle và shutdown |
| `request_cancel_total` | Body subscriber hủy, release resources |
| TCP RTT/retransmits | Phân biệt TCP HOL và HTTP/2-level stalls |

Không phải mọi library có sẵn tất cả metric này. Với `java.net.http.HttpClient` chuẩn Java 17, public API dễ đo nhất là **actual response.version**, status/timings và application-level pending data; internal flow-control window/stream IDs có thể cần instrument phía server/proxy hoặc implementation.

## 16. Những khẳng định sai dễ mắc

**“HTTP/2 dùng một TCP connection nhưng mỗi stream có băng thông riêng không phụ thuộc.”** Sai. Streams chia sẻ TCP, connection window, CPU/network scheduling.

**“Stream window dương thì được gửi DATA.”** Chưa đủ: connection window cũng phải đủ.

**“SETTINGS_INITIAL_WINDOW_SIZE đổi cả connection window.”** Sai: chỉ stream windows; connection tăng bằng WINDOW_UPDATE(stream=0).

**“Window âm là lỗi protocol.”** Không luôn đúng: giảm SETTINGS có thể làm stream window âm hợp lệ.

**“HTTP/2 flow control giới hạn HEADERS, PING và SETTINGS giống DATA.”** Sai: trong frame types được định nghĩa ở RFC 9113, chỉ DATA chịu flow control; tuy vậy control frames vẫn cần resource limits khác.

**“Một WINDOW_UPDATE cấp 1.000 byte cho mọi streams.”** Sai: stream-level chỉ tăng stream được chỉ định; connection-level chỉ tăng tổng credit chung.

**“HTTP/2 bỏ hoàn toàn head-of-line blocking.”** Sai: TCP-level HOL vẫn tồn tại.

**“sendAsync đồng thời là bằng chứng cả hai request multiplex trên một connection.”** Sai: cần actual HTTP_2 và tracing stream/connection.

**“BodySubscriber.request(1) chính là WINDOW_UPDATE(+1).”** Sai: Java demand tính item, HTTP/2 window tính bytes DATA payload.

**“ofByteArray() an toàn với response nhiều GB vì HTTP/2 tự điều tiết.”** Sai: flow control không thay application memory cap.

**“Có thể retry mọi POST khi thấy RST_STREAM/GOAWAY.”** Sai: phải xét request idempotency và trạng thái peer đã xử lý.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Có 8 request trên cùng HTTP/2 connection: có bắt buộc phải có 8 TCP sockets?  
**Đáp án:** Không. Nhiều stream có thể dùng chung một TCP socket.

**Câu 2.** Stream 1 window còn 2.000 bytes, connection window=0. Có được gửi DATA stream 1?  
**Đáp án:** Không, cả hai cửa sổ cần credit.

**Câu 3.** `WINDOW_UPDATE(stream=1,+500)` có tăng stream 3 không?  
**Đáp án:** Không; chỉ stream 1. Connection window chỉ tăng khi stream ID=0.

**Câu 4.** DATA frame có 100 body bytes, 1 Pad Length byte và 7 padding bytes, header 9 bytes. Credit tiêu thụ?  
**Đáp án:** 108 bytes (toàn DATA frame payload), không tính 9-byte frame header.

**Câu 5.** Cửa sổ stream giảm xuống -2.000 do SETTINGS, có nhất thiết lỗi không?  
**Đáp án:** Không. Sender giữ số âm và chờ WINDOW_UPDATE.

**Câu 6.** HTTP/2 `MAX_CONCURRENT_STREAMS=20` có nghĩa mỗi stream tối đa 20 bytes?  
**Đáp án:** Không; là số streams active, khác flow-control bytes.

**Câu 7.** Vì sao HTTP/2 vẫn có thể chậm cùng lúc nhiều streams khi TCP mất packet?  
**Đáp án:** TCP giao byte theo thứ tự và có thể chờ retransmission, dù HTTP/2 streams logic độc lập.

**Câu 8.** `HttpClient.version()==HTTP_2` nhưng `response.version()==HTTP_1_1`. Mâu thuẫn không?  
**Đáp án:** Không. HTTP_2 là preferred; HTTP_1_1 là protocol thực tế.

**Câu 9.** Hai `sendAsync` trả `HTTP_2` có chứng minh dùng chung một TCP connection không?  
**Đáp án:** Không đủ; cần tracing stream IDs và connection IDs.

**Câu 10.** `Flow.Subscription.request(1)` tương đương mở 1 byte window không?  
**Đáp án:** Không. Demand đo item emissions, không phải DATA bytes.

**Câu 11.** Khi tải response body rất lớn, ưu tiên API gì để tránh tích toàn bộ vào RAM?  
**Đáp án:** Streaming `ofInputStream`/`ofFile`/`ofPublisher` theo nhu cầu, kết hợp size limit và cleanup.

**Câu 12.** Receiver dừng đọc và sender có DATA queue lớn, chỉ tăng SETTINGS window có đủ bảo vệ heap server?  
**Đáp án:** Không. Cần backpressure application và bounded queues, timeouts, cancellation.

## 18. Checklist triển khai HTTP/2 trong Java

1. Xác định rõ **stream, frame, connection**, đừng gộp chúng với Java futures/threads.
2. Bảo đảm server/client thực hỗ trợ h2 qua TLS ALPN hoặc cơ chế HTTP/2 thích hợp.
3. So sánh **preferred** `client.version()` và **actual** `response.version()`.
4. Đếm DATA flow control theo **payload bytes**, bao gồm padding, không trừ header 9 bytes.
5. Giữ **stream và connection windows riêng**; chỉ gửi DATA khi cả hai cho phép.
6. Hiểu initial 65.535 bytes và `WINDOW_UPDATE` theo stream ID, kiểm soát 31-bit overflow.
7. Áp SETTINGS_INITIAL_WINDOW_SIZE theo delta lên active streams; chấp nhận âm và chặn DATA cho tới khi đủ credit.
8. Không nhầm `MAX_CONCURRENT_STREAMS`, `MAX_FRAME_SIZE`, flow control, TCP congestion và app queue limit.
9. Đảm bảo `WINDOW_UPDATE`, `SETTINGS`, `RST_STREAM` và control frames không bị bế tắc chỉ vì DATA window=0.
10. Dùng HTTP/2 stack được duy trì như `java.net.http.HttpClient`; không tự triển khai framing nếu không cần.
11. Chọn BodyHandler phù hợp, tránh tích body quá lớn, dùng backpressure/Flow theo **items**, không diễn giải thành byte credit.
12. Giới hạn memory/concurrency toàn app, có timeout, cancellation, retry-idempotency policy.
13. Đo metrics thật khi load test: window stalls, queue, streams active, actual protocol, TCP retransmits, RST_STREAM/GOAWAY.
14. Với proxy, backpressure **hop-by-hop**, không chuyển nguyên WINDOW_UPDATE xuyên qua nhiều connections.

## Tài liệu chính thức

- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html): cấu trúc frames, streams, multiplexing, `SETTINGS`, `WINDOW_UPDATE`, flow control.
- [RFC 9113 — Section 6.9](https://www.rfc-editor.org/rfc/rfc9113.html#section-6.9): hai cửa sổ, WINDOW_UPDATE increment/overflow, stream window âm sau SETTINGS.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `HTTP_2` preferred và `sendAsync`.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `version(HTTP_2)` và fallback behavior.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `version()` xác nhận protocol của response.
- [Java SE 17 — BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html) và [BodySubscriber](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): streaming, consumption và cancellation.
- [Java SE 17 — Flow.Subscription](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): demand theo item, không phải WINDOW_UPDATE bytes.
- [RFC 7301 — ALPN](https://www.rfc-editor.org/rfc/rfc7301): protocol ID `h2` khi HTTP/2 chạy trên TLS.

**Nguyên tắc cốt lõi:** HTTP/2 multiplex nhiều HTTP streams trong một connection, nhưng DATA chỉ được gửi khi **cả stream window và connection window** đều có credit. Java `HttpClient` quản lý frames và WINDOW_UPDATE; ứng dụng phải quản lý **body streaming, bounded memory, concurrency, cancellation** và kiểm tra phiên bản HTTP được dùng thật sự.
