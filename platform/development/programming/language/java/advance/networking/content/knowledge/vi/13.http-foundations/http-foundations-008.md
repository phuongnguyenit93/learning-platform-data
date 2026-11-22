# HTTP/3: QUIC, vận chuyển qua UDP và điều kiện hỗ trợ

## 1. Mục tiêu và ý tưởng cốt lõi

HTTP/3 là phiên bản ánh xạ các ngữ nghĩa HTTP (method, URI, status, header, body) lên **QUIC**, thay vì dùng kết nối TCP như HTTP/1.1 và HTTP/2 truyền thống. QUIC phiên bản 1 được chuẩn hóa bởi RFC 9000, chạy trên **UDP**, cung cấp các cơ chế riêng để tạo kết nối bảo mật, truyền các luồng dữ liệu đáng tin cậy theo thứ tự, điều khiển luồng và điều khiển tắc nghẽn. HTTP/3 được chuẩn hóa trong RFC 9114; phần bảo mật QUIC dùng TLS 1.3 theo RFC 9001.

Điều dễ nhầm là **“HTTP/3 dùng UDP” không đồng nghĩa “HTTP/3 mất dữ liệu giống ứng dụng UDP thuần”**. UDP là lớp chuyển datagram cơ sở; **QUIC tự xây dựng độ tin cậy, stream và bảo mật** bên trên. Đồng thời, không phải cứ có UDP là có HTTP/3: client, server, network, TLS, ALPN, discovery và cấu hình triển khai đều phải phối hợp.

Kết thúc bài, bạn cần:
1. Phân biệt chính xác HTTP/1.1, HTTP/2, HTTP/3 và vai trò của TCP, UDP, QUIC, TLS.
2. Giải thích QUIC cung cấp **streams đáng tin cậy** trong khi UDP không có cơ chế retransmission hay thứ tự mặc định.
3. Hiểu lợi ích hạn chế **head-of-line blocking giữa các QUIC streams** và những giới hạn còn lại.
4. Mô tả TLS 1.3 tích hợp vào QUIC, ALPN `h3`, bắt tay 1-RTT/0-RTT và rủi ro replay.
5. Trình bày cách client biết server có HTTP/3 qua **Alt-Svc**, DNS **HTTPS/SVCB** hoặc cấu hình chủ động.
6. Liệt kê điều kiện hỗ trợ tại client, server, load balancer/CDN, UDP path, certificate và Java runtime.
7. Kiểm chứng khả năng bằng công cụ thực tế mà không nhầm “server có header Alt-Svc” hoặc “máy mở UDP port” với một phiên HTTP/3 thành công.

## 2. Đặt HTTP/3 vào stack giao thức

```text
               HTTPS ứng dụng: GET /api/items
                           │
           ┌───────────────┴────────────────┐
           │                                │
     HTTP/1.1 / HTTP/2                    HTTP/3
           │                           HEADERS / DATA
      TLS trên TCP                          │
           │                          QUIC streams
         TCP                        + TLS 1.3 tích hợp
           │                     + recovery / flow control
           │                                │
           │                               UDP
           └───────────────┬────────────────┘
                           IP
                           │
                        Network

URL ngoài trình duyệt vẫn có thể là:
https://api.example.com/items
Vì URL là 'https', không ghi rõ phiên bản HTTP trên đường truyền.
```

Với HTTPS thông thường:
- **HTTP/1.1:** mỗi request/response dùng cú pháp HTTP/1.1; trên HTTPS thông thường truyền qua TLS/TCP.
- **HTTP/2:** biểu diễn HTTP thành binary frames và nhiều streams trên **một kết nối TCP** được TLS bảo vệ trong phần lớn triển khai web.
- **HTTP/3:** biểu diễn HTTP thành frames trên **QUIC streams**, truyền qua **UDP**, bảo mật tích hợp TLS 1.3.

Không có khái niệm “HTTP/3 là HTTP/2 frames chỉ thay TCP bằng UDP”. HTTP/3 có cách ánh xạ streams, control streams, QPACK và error codes riêng. Tuy giữ nguyên mục đích HTTP (request/response), **định dạng trên wire không tương thích trực tiếp** với HTTP/2.

Một HTTP/3 client cần **QUIC implementation + HTTP/3 implementation**. Chỉ có thư viện socket UDP hay TLS-over-TCP chưa đủ.

## 3. So sánh HTTP/1.1, HTTP/2 và HTTP/3

| Khía cạnh | HTTP/1.1 thông thường | HTTP/2 thông thường | HTTP/3 |
| --- | --- | --- | --- |
| Transport qua Internet | TCP | TCP | **QUIC chạy trên UDP** |
| Bảo mật HTTPS | TLS trên TCP | TLS trên TCP | **TLS 1.3 tích hợp trong QUIC** |
| Đơn vị multiplex | Kết nối; ứng dụng thường tái sử dụng/giới hạn pool | HTTP/2 streams trên một TCP connection | **QUIC streams**, một request thường dùng một bidirectional stream |
| Header compression | Không bắt buộc cơ chế chung kiểu HPACK | HPACK | **QPACK** |
| Stream độc lập khi mất dữ liệu mạng | TCP byte stream làm chậm dữ liệu đứng sau byte thiếu | TCP-level head-of-line có thể ảnh hưởng nhiều HTTP/2 streams chung kết nối | QUIC stream khác có thể tiếp tục được giao dù một stream thiếu byte |
| Reliability | TCP | TCP | QUIC stream reliability và recovery |
| Connection establishment | TCP + TLS nếu HTTPS | TCP + TLS nếu HTTPS | QUIC/TLS tích hợp; có thể giảm số RTT |
| ALPN điển hình | `http/1.1` | `h2` | **`h3`** |
| UDP 443 bắt buộc? | Không | Không | Phải có đường UDP đến **cổng QUIC được công bố**, thường UDP/443 |
| Khi đường UDP không hoạt động | Không ảnh hưởng riêng vì dùng TCP | Không ảnh hưởng riêng vì dùng TCP | Client phù hợp nên thử lại qua HTTP/TCP khi được phép |

Bảng mang tính so sánh kiến trúc phổ biến. HTTP/1.1 cũng có thể tồn tại ở các hệ thống không dùng HTTPS; HTTP/2 có một số hình thức triển khai khác; **HTTP/3 tới origin theo RFC 9114 gắn với HTTPS**, không trực tiếp dùng `http://` plaintext.

### Điều gì không thay đổi về ứng dụng?

HTTP methods như `GET`, `POST`, `PUT`, status `200`, `404`, semantics caching và URI vẫn phải tuân theo HTTP Semantics. Backend nghiệp vụ có thể tiếp tục nhận cùng request logic; một reverse proxy/CDN có thể **nhận HTTP/3 phía client rồi chuyển HTTP/2 hoặc HTTP/1.1 tới origin**. Bởi vậy, “client negotiated h3” không tự suy ra end-to-end toàn bộ mọi hop là HTTP/3.

## 4. QUIC là gì: UDP ở dưới, transport đáng tin cậy ở trên

UDP cung cấp thông điệp kiểu datagram giữa địa chỉ IP và port. UDP **không tự bảo đảm** nhận đủ, nhận đúng thứ tự, không trùng lặp hoặc có kết nối. QUIC sử dụng UDP như phương tiện mang **QUIC packets**, rồi triển khai một transport protocol khác với TCP.

Một QUIC connection có thể có:
- **Connection IDs** để định danh kết nối tách khỏi một bộ IP:port cố định trong những tình huống hỗ trợ migration/NAT rebinding.
- **Packet numbers** cho các packet number spaces, phục vụ phát hiện mất và bảo mật; packet số cũ không đơn giản được gửi lại nguyên xi.
- **ACK frames, loss detection và retransmission của thông tin cần thiết**, giúp các byte QUIC STREAM được nhận đáng tin cậy.
- **Congestion control, pacing và flow control**, tránh gửi vô hạn chỉ vì UDP không có TCP congestion control.
- **Multiple unidirectional/bidirectional streams** trong cùng connection, mỗi stream có offset và thứ tự byte riêng.
- **TLS 1.3 tích hợp** để tạo secret/keys, xác thực peer và bảo vệ dữ liệu.
- **Connection/path validation**, cơ chế xử lý thay đổi địa chỉ mạng và giới hạn amplification khi peer chưa được xác nhận.

Điều quan trọng: **QUIC không phải một giao thức tùy ý gửi HTTP plaintext trong UDP datagram**. Nó có header, packet types, protected payload, stream frames, flow control và state machine phức tạp. Khi quan sát một UDP packet tới port 443, không thể đọc HTTP status, path và body như một datagram UDP dạng chuỗi bình thường.

### Tính tin cậy ở đâu?

```text
Ứng dụng HTTP/3 tạo:
  stream #0: request A bytes [0..N]
  stream #4: request B bytes [0..M]

QUIC phân các byte thành STREAM frames
  + gửi trong QUIC packets trên UDP
  + ACK, loss detection, retransmit stream data cần thiết
  + tái lập đúng offset của TỪNG stream

UDP datagram có thể mất/đảo thứ tự:
  datagram 1 có bytes A[0..20] -> đến
  datagram 2 có bytes A[21..40] -> mất
  datagram 3 có bytes B[0..15] -> đến

QUIC:
  A chờ byte còn thiếu để trình bày byte stream A đúng thứ tự
  B có thể tiếp tục nhận dữ liệu đã đủ của stream B
```

Mô tả này minh họa **stream-level ordering**. Mức độ thực tế phụ thuộc QUIC flow control, congestion control, các frame được gói chung trong packets và khả năng parser ứng dụng. Không nên diễn giải thành “mất UDP datagram không hề ảnh hưởng HTTP/3”.

## 5. UDP datagram, QUIC packet và HTTP request là ba đơn vị khác nhau

Hãy phân biệt rõ:

1. **UDP datagram:** đơn vị dữ liệu mà `DatagramSocket` hoặc hệ điều hành gửi/nhận qua UDP; có UDP header/length/checksum.
2. **QUIC packet:** đơn vị QUIC có QUIC header và payload của các QUIC frames; một UDP datagram có thể mang **một hoặc nhiều QUIC packets** theo các quy tắc coalescing của QUIC.
3. **QUIC STREAM frame:** chứa một đoạn byte của **một stream**, cùng stream ID và offset; không nhất thiết bằng một HTTP request hoặc một HTTP/3 DATA frame.
4. **HTTP/3 frame:** đơn vị mã hóa tại tầng HTTP/3, ví dụ `HEADERS` hoặc `DATA` bên trong QUIC stream phù hợp.
5. **HTTP request:** ngữ nghĩa ứng dụng gồm method, URL/authority, headers và optional body; HTTP/3 request thường được gửi trên **một client-initiated bidirectional QUIC stream**.

```text
HTTP request #A         HTTP request #B
      │                       │
HEADERS + DATA           HEADERS + DATA
      │                       │
 QUIC stream A            QUIC stream B
      └──────────┬────────────┘
         QUIC packetizer: STREAM frames + control frames
                 │
          QUIC packets/keys
                 │
             UDP datagrams
                 │
                IP
```

**Không đúng:** “Mỗi request HTTP/3 tương ứng một UDP datagram”. Một request lớn có thể đi qua rất nhiều UDP datagrams; một UDP datagram cũng có thể mang thông tin từ nhiều streams và QUIC control frames. Ứng dụng HTTP phải xử lý theo QUIC stream/framing, **không** theo lần `DatagramSocket.receive`.

## 6. Multiplexing và head-of-line blocking

Trong HTTP/2, nhiều request streams chia sẻ **một TCP byte stream**. Nếu byte ở đầu TCP stream bị mất, TCP phải đợi phục hồi byte đó để giao các byte tiếp theo theo thứ tự, ngay cả khi chúng chứa HTTP/2 frames của request khác. Đây là **TCP-level head-of-line blocking**.

QUIC tạo nhiều **streams có thứ tự byte độc lập**. Nếu một packet mang dữ liệu stream A bị mất, QUIC có thể vẫn giao các byte stream B đã nhận đủ tới ứng dụng, thay vì bắt B chờ một byte bị thiếu của A.

```text
HTTP/2 trên một TCP stream:
  TCP byte bị mất ──► giao byte phía sau bị giữ lại
                       └── có thể ảnh hưởng nhiều HTTP/2 streams

HTTP/3 trên QUIC:
  Mất phần stream A ──► stream A chờ phục hồi
  Stream B có dữ liệu đủ ──► vẫn có thể tiến lên
```

**Lợi ích:** giảm ảnh hưởng của mất packet lên các HTTP requests khác nhau cùng connection.

**Giới hạn:**
- **Trong chính một QUIC stream**, dữ liệu vẫn phải được trình bày có thứ tự; packet loss có thể chặn phần byte phía sau của **stream đó**.
- QUIC có **congestion control chung ở cấp connection**. Mất gói có thể làm giảm tốc độ gửi của **nhiều streams**, dù stream B không bị chặn bởi offset của A.
- Nếu HTTP header dùng **QPACK dynamic table** và chờ một update cần thiết, header của một stream vẫn có thể bị trì hoãn; QPACK giảm nhưng không loại mọi dependency.
- CPU, network bandwidth, flow-control windows và server scheduling cũng có thể gây chậm.

Vì thế diễn đạt chính xác là: **HTTP/3 loại bỏ TCP-level head-of-line blocking giữa QUIC streams ở tầng transport**, chứ **không loại bỏ tất cả latency hay blocking**.

## 7. TLS 1.3 là một phần của QUIC, không phải SSL/TLS-over-TCP thông thường

Trong HTTPS truyền thống:

```text
HTTP/2 ──► TLS records ──► TCP ──► IP
```

Với HTTP/3:

```text
HTTP/3 ──► QUIC (TLS 1.3 keys/handshake) ──► UDP ──► IP
```

QUIC dùng **TLS 1.3 handshake** để xác thực peer và tạo traffic secrets, nhưng bản ghi TLS không được chuyên chở giống TLS-over-TCP thông thường. QUIC đặt handshake data trong CRYPTO frames, tự thực hiện packet protection và quản lý keys theo quy định RFC 9001. **Không** dùng `SSLSocket` rồi đặt `DatagramSocket` bên dưới để tạo HTTP/3.

Server vẫn cần:
- TLS certificate hợp lệ cho hostname (chứng chỉ X.509 thường dùng).
- Private key tương ứng.
- Trust chain/CA đáng tin với client.
- TLS 1.3 và QUIC stack tương thích.
- Chính sách kiểm tra danh tính endpoint đúng, không tắt xác minh certificate.

**QUIC không làm HTTPS kém an toàn chỉ vì dùng UDP.** Mã hóa và integrity là thuộc tính của QUIC/TLS. Tuy nhiên metadata như IP, port và một số trường packet routing vẫn có thể quan sát được; Initial packet protection không có mục tiêu che giấu toàn bộ bắt tay khỏi kẻ nghe lén vì các khóa Initial có thể được dẫn xuất công khai theo quy tắc protocol. Không suy ra rằng mọi metadata mạng đều bí mật.

## 8. Handshake, 1-RTT, 0-RTT và rủi ro replay

Trong tình huống mới, QUIC tích hợp TLS 1.3 giúp thiết lập connection và bảo mật mà không cần **một vòng TCP handshake rồi thêm một vòng TLS** như HTTPS-over-TCP thông thường. Trong điều kiện phù hợp, quá trình TLS/QUIC có thể hoàn tất trong khoảng **1 round trip**; 0-RTT có thể cho phép gửi early application data khi resuming connection đã có thông tin trước đó.

```text
Kết nối QUIC mới, mô hình khái quát:

Client  ── Initial/ClientHello ───────► Server
Client  ◄─ handshake responses ─────── Server
Client  ── Finished/1-RTT data ──────► Server
            (cấu trúc thực tế phụ thuộc handshake)

Kết nối quay lại có thông tin resumption phù hợp:

Client  ── Initial + 0-RTT early data ► Server
Client  ◄─ handshake responses ─────── Server

Early data có rủi ro REPLAY, không phải kết quả của một
request đã được xác nhận exactly-once.
```

Điểm cần hiểu:
- **1-RTT không có nghĩa “một request mất đúng 1 RTT”**; đó là mô tả lớp handshake trong điều kiện không có loss và policy phù hợp. DNS, path validation, congestion và server processing vẫn tạo độ trễ.
- **0-RTT không phải mặc định bật với mọi client/server**. Cần session resumption và các giới hạn/cấu hình tương thích.
- **0-RTT early data có thể bị replay**. Ứng dụng không được đặt thao tác gây tác động không mong muốn (thanh toán, thay đổi trạng thái, thực hiện công việc không idempotent) vào early data nếu không có biện pháp bảo vệ riêng.
- HTTP có cơ chế liên quan như response `425 Too Early` để xử lý yêu cầu tới quá sớm trong một số kịch bản. Việc chấp nhận/rút lại/retry early data phải do HTTP client và server triển khai đúng policy.
- TLS handshake thành công **không** tự chứng minh business request được xử lý đúng một lần. Retry cần idempotency key, request ID và semantics ở tầng ứng dụng.

Theo RFC 9001, server và client phải quản lý rủi ro replay 0-RTT. Trong hệ thống mới, an toàn nhất là **không giả định 0-RTT được dùng** khi đánh giá hiệu năng hoặc tính đúng của request.

## 9. HTTP/3 frames và streams: cấu trúc đặc thù

HTTP/3 có framing riêng trên QUIC streams:

- Một request bình thường được gửi trên **client-initiated bidirectional QUIC stream**.
- Request và response có `HEADERS`, `DATA` và có thể các frames khác theo grammar HTTP/3. Response dùng **cùng request stream** tương ứng.
- Mỗi endpoint mở **một control stream** unidirectional và gửi `SETTINGS` làm frame đầu tiên theo RFC 9114; đó là cấu hình **cấp connection**, không phải mỗi request.
- Có các unidirectional streams phục vụ **QPACK encoder/decoder instructions**.
- Server push là **tính năng tùy chọn** của HTTP/3; không nên giả định được bật trong mọi client/server.

Một ví dụ logic:

```text
QUIC connection (ALPN = h3)
│
├── client control stream (SETTINGS, ...)
├── server control stream (SETTINGS, ...)
├── QPACK encoder/decoder instruction streams (khi cần)
│
├── request stream A (bidirectional)
│     HEADERS(:method=GET, :path=/a, ...)
│     DATA(response body chunks...)
│
└── request stream B (bidirectional)
      HEADERS(:method=GET, :path=/b, ...)
      DATA(...)
```

Sơ đồ chỉ diễn đạt cấu trúc logic, **không phải dump bytes trên wire**. Không có một TCP connection riêng cho mỗi request. QUIC transport stream IDs/offsets làm nhiệm vụ sắp xếp byte, HTTP/3 layer giải mã header/body.

### QPACK thay HPACK

HTTP/2 dùng **HPACK**, còn HTTP/3 dùng **QPACK** (RFC 9204) để nén header hiệu quả khi các QUIC streams có thể được giao độc lập. QPACK hỗ trợ static/dynamic tables và các instruction streams; nó giới hạn vấn đề blocking do phụ thuộc vào dynamic table theo cấu hình/limits, nhưng không phải “không bao giờ block”.

Ứng dụng Java thông thường không trực tiếp viết QPACK: HTTP/3 library sẽ chịu trách nhiệm. Nếu tự viết HTTP/3 từ `DatagramSocket`, bạn phải làm đầy đủ QUIC transport, QPACK, HTTP/3 control streams, error handling, SETTINGS và các yêu cầu bảo mật; đây không phải ví dụ nhập môn thực tế.

## 10. ALPN h3: thương lượng giao thức ứng dụng

**ALPN (Application-Layer Protocol Negotiation)** cho client và server biết protocol ứng dụng được hỗ trợ. Với HTTP/3 chuẩn hóa, token ALPN phổ biến là **`h3`**. Với HTTP/2 over TLS, token thường là `h2`; với HTTP/1.1 là `http/1.1`.

```text
TCP/TLS pathway:
  ALPN client offers h2, http/1.1
  server selects h2 hoặc http/1.1 theo cấu hình

QUIC/TLS pathway:
  QUIC client offers h3 (trong TLS handshake tích hợp)
  QUIC server selects h3
  HTTP/3 stream protocol bắt đầu sau khi điều kiện phù hợp
```

**Không thể** chỉ thêm `"h3"` vào `SSLSocket` hay `HttpClient` của Java 17 rồi hy vọng chuyển TCP thành QUIC. Tầng transport và handshake của QUIC phải thực sự tồn tại.

Cũng không thể suy ra HTTP/3 hỗ trợ chỉ từ:
- Máy chủ có **TLS 1.3 trên TCP**: cần QUIC/TLS 1.3 trên **UDP**.
- Server trả `Alt-Svc: h3=...`: đây là **quảng bá**, chưa chứng minh client đã kết nối được.
- Port TCP/443 mở: HTTP/3 thường cần **UDP/443** riêng.
- Trình duyệt có HTTP/3: một Java HTTP client khác có thể **không** có HTTP/3.

Nếu ALPN chọn protocol khác hoặc handshake/transport thất bại, client phải xử lý theo khả năng/fallback policy. Không dùng HTTP/3 frames trên kết nối mà thực tế chỉ thương lượng HTTP/2.

## 11. Khám phá HTTP/3 bằng Alt-Svc

Một client có thể tới origin bằng HTTPS qua TCP/HTTP/2 hoặc HTTP/1.1 trước. Server trả header **Alt-Svc** để quảng bá endpoint hỗ trợ giao thức khác. Ví dụ:

```http
HTTP/2 200
alt-svc: h3=":443"; ma=86400
content-type: text/html
```

Ý nghĩa:
- `h3` là protocol ID của HTTP/3.
- `":443"` đề xuất **cùng hostname** với origin, trên port **443** (với HTTP/3 là đường QUIC/UDP).
- `ma=86400` mô tả thời gian cache advertisement (giây) theo ngữ nghĩa Alt-Svc.
- Client có thể **thử** kết nối HTTP/3 ở lần truy cập thích hợp, nhưng không bắt buộc chọn nó.

Alt-Svc cũng có thể quảng bá **host/port khác**, ví dụ `Alt-Svc: h3="alt.example.com:8443"; ma=3600`. Client vẫn phải xác minh endpoint thay thế có quyền phục vụ **origin ban đầu**, bao gồm certificate validation và quy tắc authority thích hợp. Alt-Svc **không** cho phép bỏ kiểm tra TLS identity hoặc thay đổi ý nghĩa origin tuỳ tiện.

Lưu ý thiết yếu:
- Alt-Svc có thể xuất hiện trên **HTTP/1.1 hoặc HTTP/2** response; nó không tự chứng minh response đang dùng HTTP/3.
- Client có thể lưu cache Alt-Svc và nâng cấp ở request sau; vì vậy một request đầu tiên không dùng HTTP/3 **không** chứng minh hạ tầng không hỗ trợ.
- Client có thể bỏ qua Alt-Svc do không hỗ trợ HTTP/3, chính sách quản trị, port bị chặn hoặc kiểm tra bảo mật thất bại.
- Quảng bá HTTP/3 khi listener UDP chưa chạy chỉ làm client tốn thời gian thử rồi fallback; tốt nhất chỉ publish sau khi kiểm thử end-to-end.

RFC 9114 `3.1.1` giải thích HTTP alternative services qua `Alt-Svc` hoặc HTTP/2 `ALTSVC` frame.

## 12. DNS HTTPS/SVCB records là một cơ chế discovery khác

RFC 9460 mô tả **HTTPS** và **SVCB** DNS resource records. HTTPS record có thể công bố alternative endpoints, ALPN protocols và service parameters (ví dụ port). Nhờ vậy client có thể biết lựa chọn HTTP/3 **trước khi** có response Alt-Svc từ origin.

Ví dụ bản ghi **minh họa cú pháp** (không phải dữ liệu DNS thực của một domain):

```dns
example.com.  300  IN HTTPS 1 . alpn=h3,h2
```

Ý tưởng: dịch vụ HTTPS cho origin có thể hỗ trợ `h3` và `h2`. Khi sử dụng record thật, client phải theo quy tắc RFC 9460 về TargetName, ServiceMode/AliasMode, mandatory keys, port, alpn và bảo mật DNS/transport. Không chỉ grep chữ `h3` rồi kết luận chắc chắn request đã dùng HTTP/3.

Đừng nhầm:
- **DNS A/AAAA:** tìm IP address, không tự khai báo HTTP/3.
- **DNS HTTPS RR:** mô tả thông số kết nối/phương án alternative service; client hỗ trợ có thể sử dụng.
- **Alt-Svc:** quảng bá HTTP alternative services bằng HTTP layer.
- **ALPN negotiation:** protocol thực sự được chọn **trên một TLS/QUIC connection cụ thể**.
- **Response protocol version:** bằng chứng thực tế rằng request đã được phục vụ bằng HTTP/3 hay không.

Một công cụ chẩn đoán DNS nếu có `dig`:

```bash
dig HTTPS example.com
```

Đây là lệnh tra cứu **DNS metadata**, không phải test kết nối QUIC. Bản ghi có thể không tồn tại và không nên giả định `example.com` có HTTP/3. Các client khác nhau có chính sách discovery và precedence khác nhau; hãy kiểm tra tài liệu cụ thể của client/runtime.

## 13. Điều kiện hỗ trợ: không chỉ server có flag HTTP/3

Để một request HTTP/3 thực sự thành công, toàn bộ các mắt xích cần tương thích:

| Thành phần | Điều kiện cần | Nếu không đáp ứng |
| --- | --- | --- |
| **Client** | Có QUIC v1 + HTTP/3 implementation; hỗ trợ ALPN `h3`, TLS/QUIC phù hợp, trust store | Dù server hỗ trợ, client không thể tạo HTTP/3 |
| **Server / edge** | Lắng nghe QUIC/UDP trên port quảng bá, có HTTP/3 stack, certificate/key, ALPN `h3` | UDP tới server nhưng không có QUIC HTTP/3 handler |
| **Transport path** | UDP outbound/inbound tới địa chỉ/port đúng; firewall/NAT/LB cho traffic và phản hồi | Handshake timeout; có thể phải dùng TCP fallback |
| **TLS** | TLS 1.3 tích hợp QUIC, certificate hợp lệ cho origin, hostname validation đúng | QUIC/TLS handshake hoặc authority validation fail |
| **HTTP/3 protocol** | SETTINGS, request/control streams, QPACK, frames được triển khai theo RFC | Transport có thể lên nhưng HTTP/3 protocol vẫn lỗi |
| **Discovery/policy** | Client biết nên thử h3 (Alt-Svc, HTTPS RR hoặc direct config), không bị tắt bởi enterprise policy | Có thể tiếp tục H2/H1 dù H3 endpoint hoạt động |
| **Reverse proxy/CDN/LB** | Hỗ trợ hoặc pass-through QUIC/UDP đúng và chuyển HTTP tới upstream phù hợp | Edge có thể chặn UDP hoặc chỉ terminate TLS-over-TCP |
| **Ứng dụng Java** | HTTP client/runtime hoặc thư viện **thực sự có HTTP/3**, không chỉ `DatagramSocket` | Không thể yêu cầu HTTP/3 bằng option không tồn tại |

**Kết luận:** chỉ cần **một** mắt xích thiếu là HTTP/3 end-to-end của request đó có thể thất bại. Phải kiểm tra cả transport và protocol thực sự được thương lượng, không chỉ “HTTP/3 đã bật trong cấu hình”.

### Port thường dùng

Với URL `https://api.example.com/` không khai port, HTTPS origin mặc định là **443**. Nhiều triển khai mở **TCP/443** cho HTTP/2/HTTP/1.1 và **UDP/443** cho HTTP/3 cùng lúc. HTTP/3 cũng có thể chạy trên **UDP port khác**, khi endpoint/port được quảng bá hợp lệ.

Không bắt buộc mọi H3 deployment dùng UDP/443; RFC 9114 cho phép server trên UDP port khác. Tuy nhiên thiết lập UDP/443 hợp với HTTPS origin phổ biến và firewall policy dễ hiểu hơn.

## 14. Cùng một HTTPS URL, nhiều đường vận chuyển

```text
Client gửi GET https://api.example.com/items
                     │
             HTTP stack chọn protocol
                     │
     ┌───────────────┴──────────────────┐
     ▼                                  ▼
 Thử HTTP/3                       HTTP/2 hoặc HTTP/1.1
 QUIC/TLS 1.3                     TLS + TCP
 UDP:443 (phổ biến)               TCP:443
     │                                  │
     ▼                                  ▼
 Edge / CDN / origin               Edge / CDN / origin
     │                                  │
     └────────────► HTTP service ◄──────┘
                        │
                 JSON/response
```

Cả hai đường đều có thể phục vụ **cùng URI** với cùng HTTP semantics. Các khác biệt thuộc tầng transport, framing và cách thiết lập kết nối; routing, authentication và business logic vẫn phải tuân theo origin/request semantics.

Một CDN có thể dùng:
- **Client → CDN:** HTTP/3 over QUIC/UDP.
- **CDN → origin:** HTTP/2 over TLS/TCP.
- **Origin application:** framework HTTP truyền thống.

Khi quan sát log origin báo `HTTP/2`, điều đó **không bác bỏ** việc người dùng phía ngoài đã dùng HTTP/3 với CDN. Muốn chứng minh hãy đo **đúng hop**: browser/network/client trace, edge access logs và thông tin negotiated protocol từng hop.

## 15. Fallback khi UDP/QUIC không thể kết nối

Một hệ thống sản xuất phải xét trường hợp:
- Firewall chặn UDP outbound hoặc return path.
- Mạng doanh nghiệp/proxy chỉ cho TCP/TLS.
- NAT hoặc connection tracking làm rơi UDP packets.
- UDP/443 không được routing tới listener.
- Middlebox làm QUIC handshake thất bại.
- Server chỉ bật HTTP/2/TCP hoặc chưa support ALPN `h3`.
- Certificate/hostname không hợp lệ trên QUIC listener.
- UDP path MTU/fragmentation làm rơi packet kích thước lớn.

RFC 9114 khuyến nghị clients **thử HTTP các phiên bản dùng TCP** khi QUIC connectivity thất bại. Một client hỗ trợ fallback có thể quay về HTTP/2 hoặc HTTP/1.1 **qua HTTPS/TCP**. Đây không phải “downgrade sang plaintext HTTP”.

```text
H3-capable client
  │
  ├─ QUIC/UDP + ALPN h3 thành công ──► dùng HTTP/3
  │
  └─ QUIC thất bại / policy không cho ─► HTTPS/TCP
                                          │
                                          ├─ ALPN h2 -> HTTP/2
                                          └─ http/1.1 -> HTTP/1.1
```

**Không được phát biểu “HTTP/3 bắt buộc dùng được vì TCP/443 đang thông”**. TCP và UDP là hai giao thức transport khác nhau, có firewall/NAT/LB rules khác nhau. Kiểm thử phải thử **UDP** tới đúng endpoint và một handshake HTTP/3 thật.

### Fallback cũng cần kiểm soát

- Client **H3-only** có thể chọn fail thay vì fallback theo yêu cầu đo kiểm.
- Client thông thường có thể thử song song hoặc trì hoãn một transport để tối ưu trải nghiệm, tùy implementation.
- Nếu yêu cầu nghiệp vụ có tác động (POST tạo đơn hàng, thanh toán), fallback/retry phải theo chính sách idempotency/duplicate handling; transport retry không tạo exactly-once semantics.
- Nếu QUIC certificate **không hợp lệ**, không nên diễn giải lỗi bảo mật thành lý do để bỏ xác minh certificate cho TCP.
- Chặn UDP có thể khiến HTTP/3 không dùng được nhưng **HTTPS an toàn trên HTTP/2 vẫn hoạt động** nếu đường TCP và TLS đúng.

## 16. Bắt tay và timeout khi thử HTTP/3

Các timeout cần nghĩ đến:
1. **DNS resolution** và HTTPS RR lookup.
2. **UDP path establishment:** có phản hồi cho QUIC Initial hay không?
3. **TLS/QUIC handshake timeout:** QUIC nhận được packets nhưng không thể xác thực/hoàn tất.
4. **HTTP/3 control stream/SETTINGS readiness:** transport lên chưa có nghĩa HTTP/3 connection sẵn sàng xử lý request.
5. **Response header/body timeout:** ứng dụng phía server có thể chậm dù QUIC hoạt động.
6. **Idle timeout:** peer hoặc NAT có thể hết trạng thái khi connection rảnh.

Không nên tối ưu bằng cách retry ồ ạt hàng trăm request khi H3 thất bại. Client cần giới hạn attempts/deadlines và cache tình trạng Alt-Svc theo chuẩn để tránh lặp lại timeout trên mạng không hỗ trợ UDP.

QUIC **Initial datagram** của client theo RFC 9000 có những yêu cầu kích thước tối thiểu (UDP datagram mang Initial cần payload ít nhất 1200 byte) để hỗ trợ kiểm tra đường và giới hạn anti-amplification. Vì vậy “một UDP ping vài byte trả lời thành công” không đủ chứng minh QUIC handshake packets đi qua mạng.

## 17. Điều kiện hạ tầng: firewall, NAT, load balancer, CDN và MTU

### Firewall và UDP/443

Nếu server quảng bá `h3=":443"`:
- Cho inbound **UDP/443** từ client tới H3 endpoint.
- Cho response UDP quay về, stateful firewall/NAT tương ứng.
- Giữ **TCP/443** khi muốn fallback HTTPS bình thường.
- Nếu CDN terminate QUIC, rule UDP đúng tại edge; origin có thể không cần UDP/443.

Chỉ mở TCP/443 không mở được QUIC/UDP. Chỉ mở UDP inbound nhưng outbound return path không đúng cũng không đủ.

### Load balancing

QUIC có connection IDs và có thể survive thay đổi network path theo những giới hạn protocol. Load balancer phải:
- Hỗ trợ/forward UDP phù hợp, không giả định một QUIC connection là TCP 5-tuple cố định trong mọi tình huống.
- Giữ routing hợp lý tới QUIC connection state hoặc dùng kiến trúc có khả năng xử lý connection IDs.
- Quản lý idle timeouts, retry/address validation tokens và connection draining.
- Không tráo dữ liệu của nhiều connections khi source address thay đổi.

Không phải mọi layer-7 reverse proxy có HTTP/2 đồng nghĩa hỗ trợ HTTP/3. Kiểm tra **version/build/feature flags** của proxy hoặc CDN cụ thể, **port/protocol listener** và cấu hình advertise Alt-Svc.

### MTU và mất UDP

Một UDP datagram có thể vượt path MTU và phải fragment ở IP layer hoặc bị drop. Mất một fragment có thể làm cả datagram không đến QUIC. QUIC có các yêu cầu về UDP datagram size và PMTU discovery; transport/path cần cho phép packets cần thiết và xử lý black-hole scenarios.

Trong network nhiều VPN/tunnel, MTU thấp, ping/traceroute TCP hợp lệ không chứng minh traffic QUIC kích thước phù hợp có thể đi qua. Hãy đo handshake và response thật, xem loss, ICMP packet-too-big/PMTU, QUIC traces nếu có.

## 18. QUIC connection ID, NAT rebinding và connection migration

Một khác biệt với TCP là QUIC connection có **Connection IDs**, cho phép endpoint trong một số tình huống giữ connection khi địa chỉ IP/port thay đổi (ví dụ NAT rebinding, chuyển Wi-Fi sang mobile network), thay vì ràng buộc hoàn toàn vào TCP 4-tuple.

Tuy nhiên:
- Migration **không phải** lời hứa “mọi connection HTTP/3 tự chuyển mạng thành công”. Phải có triển khai, policy và đường mới hợp lệ.
- QUIC có cơ chế **path validation** và có thể cần challenge/response, tránh gửi lượng dữ liệu lớn tới địa chỉ spoofed.
- Server phải chú ý **anti-amplification**. Theo RFC 9000, trước khi validate địa chỉ peer, việc gửi tới địa chỉ chưa xác thực bị giới hạn theo quy tắc khoảng **3 lần số byte đã nhận** từ địa chỉ đó.
- Load balancer/CDN phải xử lý connection IDs và routing nhất quán với migration.
- IP/port thay đổi không được phép biến thành bỏ kiểm tra TLS identity hoặc ownership của origin.

Connection ID cũng có giới hạn về privacy: dùng ID không hợp lý có thể giúp theo dõi kết nối. Các triển khai phải tuân thủ cơ chế rotation/privacy tương ứng, không dùng connection ID như một user identifier bất biến.

## 19. Java 17: HttpClient có hỗ trợ HTTP/3 dựng sẵn không?

**Trong API Java SE 17**, enum `java.net.http.HttpClient.Version` chỉ có:
- `HTTP_1_1`.
- `HTTP_2`.

Không có `HTTP_3` trong enum đó. Do vậy Java 17 `java.net.http.HttpClient` **không cung cấp một lựa chọn HTTP/3 built-in** qua API `HttpClient.Version`. Cấu hình:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

là **ưu tiên HTTP/2**, **không** phải HTTP/3. Tùy server/proxy/implementation, một request thực có thể được phục vụ bằng HTTP/1.1 nếu không thương lượng được HTTP/2. `client.version()` cho biết **preferred version**, không tự chứng minh protocol thực sự của một network response. `HttpResponse.version()` mới cung cấp protocol được dùng cho response đó.

Đối với H3 trong Java, bạn cần **chọn rõ một QUIC + HTTP/3 client/server implementation** tương thích với JDK, hệ điều hành, TLS provider và cách triển khai; xem xét tài liệu chính thức của library/version đã chọn, kể cả thành phần native nếu có. Không thể dùng `DatagramSocket` gửi chuỗi HTTP/1.1 sang UDP/443 mà gọi đó là HTTP/3.

**Cảnh báo về phiên bản:** API/khả năng có thể khác giữa các JDK mới hoặc thư viện của bên thứ ba. Bài minh họa cố định **Java SE 17**, không suy từ đó rằng mọi Java trong tương lai mãi không có H3. Khi cập nhật runtime phải tra tài liệu của phiên bản **thực sự triển khai**.

## 20. Ví dụ Java 17+ runnable: kiểm tra khả năng HTTP của JDK mà không gửi mạng

Lưu thành file **`Http3Java17Capabilities.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.util.Arrays;

public class Http3Java17Capabilities {
    public static void main(String[] args) {
        HttpClient.Version[] versions = HttpClient.Version.values();
        System.out.println("versions=" + Arrays.toString(versions));
        boolean hasHttp3 = Arrays.stream(versions)
                .anyMatch(v -> "HTTP_3".equals(v.name()));
        System.out.println("builtInHttp3=" + hasHttp3);

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .build();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/")).GET().build();
        System.out.println("preferred=" + client.version());
        System.out.println("scheme=" + request.uri().getScheme());
        System.out.println("networkRequests=0");
    }
}
```

Biên dịch trong môi trường JDK 17:

```bash
javac Http3Java17Capabilities.java
java Http3Java17Capabilities
```

Stdout khi chạy trên JDK có `HttpClient.Version` giống Java 17 API:

```text
versions=[HTTP_1_1, HTTP_2]
builtInHttp3=false
preferred=HTTP_2
scheme=https
networkRequests=0
```

Đã kiểm tra mã biên dịch bằng `javac --release 17` và chạy với kết quả trên. Chương trình **không mở kết nối HTTP**, nên luôn in `networkRequests=0`; `https` ở URI **không chứng minh** network đã dùng h3.

Giải thích:
1. `HttpClient.Version.values()` phản ánh các phiên bản **API built-in** công bố qua enum.
2. Kiểm tra chuỗi `"HTTP_3"` tránh cố dùng một enum constant không tồn tại trong Java 17.
3. `client.version()` là phiên bản **ưu tiên** được cấu hình, không phải kết quả ALPN của một request gửi mạng.
4. Không dùng `HttpClient` này để “test QUIC” vì nó không có chức năng HTTP/3 theo API Java 17.

### Một mảnh code để xem phiên bản response thực

```java
HttpRequest req = HttpRequest.newBuilder(
        URI.create("https://example.com/")).GET().build();
HttpResponse<Void> response = client.send(
        req, HttpResponse.BodyHandlers.discarding());
System.out.println(response.version());
```

Đây là **mảnh code phụ thuộc** `HttpClient client` đã cấu hình, `HttpRequest`, `HttpResponse` và `URI` imports. Nó **cần Internet**, server đáng tin và môi trường cho phép HTTPS; stdout có thể là `HTTP_2` hoặc `HTTP_1_1`, không được giả định cố định. Với Java 17 HTTP client này, mảnh code không thực hiện HTTP/3.

## 21. Kiểm thử HTTP/3 thật bằng curl: phân biệt phiên bản curl và build flags

Dùng `curl` (bản hỗ trợ HTTP/3) để kiểm tra endpoint thực tế là cách dễ quan sát protocol. **Trước khi thử request**, kiểm tra bản build:

```bash
curl --version
```

Trong dòng `Features:`, cần có **`HTTP3`** để sử dụng HTTP/3 (tên và hiển thị phụ thuộc bản build). **Số phiên bản curl mới không tự đảm bảo HTTP3 feature đã được biên dịch vào.** Một bản curl mới nhưng không có HTTP3 vẫn không thể gửi request HTTP/3.

Hai lệnh chẩn đoán (URL là **địa chỉ HTTPS công khai minh họa**; khả năng hỗ trợ h3 có thể thay đổi theo endpoint và mạng):

```bash
curl --http3-only -I -v https://www.cloudflare.com/
curl --http3 -I -v https://www.cloudflare.com/
```

- **`--http3-only`:** yêu cầu HTTP/3 **không fallback**; nếu QUIC handshake hoặc HTTP/3 không thiết lập được, lệnh thất bại. Phù hợp để chứng minh **đường h3 thực sự hoạt động** khi có kết quả thành công.
- **`--http3`:** **thử HTTP/3 nhưng có thể fallback** sang HTTP/2/HTTP/1.1 nếu H3 chậm/thất bại. Một response thành công ở lệnh này **không chứng minh** nó đã dùng HTTP/3; phải xem verbose output/protocol thực sự.
- **`-I`:** yêu cầu headers; server có thể xử lý HEAD đặc biệt. Nếu muốn kiểm tra GET thay vì HEAD, bỏ `-I` và dùng output handling phù hợp.
- **`-v`:** hiển thị quá trình kết nối/protocol, nhưng logs có thể chứa thông tin nhạy cảm; dùng trong môi trường kiểm soát.

Nếu `curl --version` không có HTTP3, **đừng kết luận server không hỗ trợ** khi lệnh `--http3-only` lỗi. Phải dùng curl có backend HTTP/3 được build đúng hoặc một H3-capable client khác.

### Kiểm tra Alt-Svc không phải kiểm tra h3 hoàn tất

```bash
curl -I https://www.cloudflare.com/
```

Nếu response có `Alt-Svc: h3=":443"` thì đó là **quảng bá**. Response đầu tiên có thể chạy bằng HTTP/2; muốn khẳng định HTTP/3 đã dùng phải xem **protocol thực tế** của lần kết nối QUIC hoặc dùng `--http3-only` trên tool có H3.

Lệnh `curl --alt-svc <cache-file> ...` có thể lưu/đọc Alt-Svc theo tài liệu curl. Tuy nhiên nó vẫn yêu cầu **HTTP/3 support trong build** nếu muốn nâng cấp lên h3; chỉ có alt-svc feature không thay thế QUIC support.

## 22. Phân biệt các loại lỗi khi chẩn đoán HTTP/3

| Quan sát | Khả năng | Bước kiểm tra |
| --- | --- | --- |
| TCP HTTPS chạy tốt, `--http3-only` timeout | UDP/443 bị chặn, QUIC listener/route lỗi, server không h3 | Kiểm tra UDP rules, H3 listener, LB, path MTU và QUIC handshake logs |
| `curl` báo option HTTP3 không hỗ trợ | Client build thiếu HTTP3 backend | `curl --version`, cài/build client có HTTP3 feature |
| `Alt-Svc: h3` xuất hiện nhưng request tiếp vẫn H2 | Client không hỗ trợ, cache/policy, UDP blocked hoặc H3 fail | Kiểm tra feature, cache, DNS/Alt-Svc, verbose request protocol |
| QUIC handshake tới server nhưng cert error | CA/hostname/certificate SAN không hợp lệ | Kiểm tra đúng origin, chain, certificate, SNI/identity policy |
| QUIC negotiation không chọn `h3` | Server/client không cùng ALPN HTTP3 | Kiểm tra phiên bản QUIC/HTTP3 stack và ALPN config |
| UDP port mở nhưng HTTP3 error | Có QUIC transport nhưng HTTP/3 SETTINGS/QPACK/streams lỗi | Dùng H3-capable client, server traces và error codes |
| H3 hoạt động ở một mạng, thất bại ở mạng khác | Firewall/NAT/VPN/MTU/proxy khác nhau | So sánh đường UDP/TCP, metrics, packet sizes, network policy |
| CDN báo H3 nhưng origin log H2 | CDN terminate H3 và kết nối origin bằng H2/TCP | Xem edge protocol log; phân biệt từng hop |
| H3 sử dụng nhiều CPU | TLS/QUIC crypto, pacing, implementation hoặc tải | Benchmark CPU/profile, tối ưu cấu hình và library |
| H3 không nhanh hơn H2 | RTT/loss thấp, workload nhỏ, cache, server bottleneck | Đo RUM/latency/loss nhiều môi trường; không kỳ vọng mặc định |
| Request thanh toán bị trùng khi retry | Retry/0-RTT hoặc network failure làm outcome mơ hồ | Idempotency key, app-level ack, không dùng unsafe 0-RTT |

**Không kết luận từ duy nhất một chỉ báo.** Phải kết hợp: client có khả năng H3, discovery, UDP path, TLS handshake/ALPN, HTTP response protocol và server/edge logs.

## 23. Cách xác minh bằng browser và observability

Trên trình duyệt hỗ trợ HTTP/3, DevTools có thể hiển thị cột **Protocol** của request (tùy phiên bản, có thể chọn qua menu Columns). Một request được đánh dấu **h3** là quan sát ở **hop browser → edge/origin** trong lần tải đó. Không phải mọi browser luôn thử HTTP/3:
- Thay đổi network policy hoặc browser flags.
- Alt-Svc cache/HTTPS RR state.
- Proxy của công ty/VPN.
- CDN response và cache.
- Nhiều request sử dụng connection đã có hoặc thử fallback.

Ở server/CDN:
- Ghi log **negotiated protocol** ở edge (h3/h2/http1).
- Đo số lần QUIC handshake, latency, failure codes, retries/fallback.
- Quan sát UDP packet loss/PMTU issues, NAT rebinding/path migration events nếu stack hỗ trợ.
- Tách metrics **client-facing** với **origin-facing**.
- Không log QUIC secrets hoặc plaintext body nhạy cảm.

Chỉ nhìn một header `Alt-Svc` trong HTTP response không tương đương “request này chạy HTTP/3”, và chỉ nhìn TCP access log ở backend không tương đương “người dùng không dùng H3”.

## 24. Kiểm thử khi bật HTTP/3 cho server thật

Một kế hoạch kiểm thử có thứ tự:

1. **Capability:** xác nhận server stack/reverse proxy/CDN **phiên bản và build** hỗ trợ H3, QUIC v1/TLS 1.3 và ALPN `h3`.
2. **Listener:** xác nhận tiến trình/edge lắng nghe **UDP port đúng** (thường 443), đồng thời TCP/443 còn hoạt động để hỗ trợ fallback.
3. **Identity:** certificate đúng origin, trust chain, SAN, TLS policy và SNI/ALPN phù hợp.
4. **Discovery:** bật Alt-Svc hoặc HTTPS DNS record **chỉ khi endpoint thật sự sẵn sàng**; cấu hình max-age có kiểm soát để giảm tác động rollout lỗi.
5. **Client test:** dùng client có HTTP3 feature, test `--http3-only` và xem negotiated protocol; dùng thêm browser nếu muốn kiểm tra discovery.
6. **Blocked UDP:** từ môi trường chặn UDP, xác nhận client fallback về HTTPS/TCP mà không gửi plaintext.
7. **Network quality:** test latency cao, loss, mạng di động, VPN, thay đổi MTU và NAT/timeout.
8. **Multiple requests:** test parallel streams, uploads lớn, downloads, streaming response và HTTP headers lớn.
9. **Application semantics:** đảm bảo auth, cookies, redirects, CORS, cache, logging, rate limits, retry/idempotency giống các phiên bản HTTP khác.
10. **0-RTT policy:** chỉ cho early data trong trường hợp an toàn; phòng replay, test `425 Too Early` nếu implementation có áp dụng.
11. **Rollout:** giám sát tỷ lệ h3 negotiation, fallback, error rate, p95 latency, CPU và per-network outcomes; giảm/quay lại khi cần.
12. **Certificate renewal:** kiểm tra cập nhật certificate/key ở cả TLS-over-TCP và QUIC listener, tránh “TCP cập nhật rồi nhưng H3 dùng cert cũ”.

Không cần tự viết QUIC transport từ đầu để thực hiện các bước này; nên dùng một implementation chuẩn hóa và công cụ hỗ trợ H3.

## 25. Ưu điểm, đánh đổi và hiệu năng thực tế

### Những lợi ích có thể có

- Giảm TCP-level HOL blocking giữa các HTTP/3 request streams.
- Thiết lập kết nối mới có thể cần ít RTT hơn so với TCP+TLS 1.3 hai giai đoạn.
- Resumption 0-RTT có thể giảm latency trong tình huống an toàn/được hỗ trợ.
- Connection IDs/path migration giúp một số kết nối thích ứng khi địa chỉ mạng thay đổi.
- UDP-based transport cho phép QUIC triển khai cơ chế congestion/loss recovery riêng thay vì gắn chặt vào TCP stack hệ điều hành.

### Chi phí/giới hạn

- Cần **hạ tầng UDP/QUIC**, quic-capable edge/proxy/CDN và các công cụ debug khác với HTTP/TCP.
- Encryption/packet processing có thể tiêu thụ thêm CPU tùy implementation.
- Một số mạng chặn UDP hoặc có path MTU issues; fallback phải hoạt động.
- Loss vẫn gây retransmission, giảm congestion window và stream-local blocking.
- Mối quan hệ performance phụ thuộc RTT, loss rate, payload, caching, server, thiết bị và edge placement.
- 0-RTT làm tăng phức tạp bảo mật do replay risk.
- Ecosystem Java/third-party stack cần tương thích đúng version và deployment environment.

**Không nói chung “HTTP/3 luôn nhanh hơn HTTP/2”.** Benchmark đúng phải có baseline và đo từ client thực:
- Time to first byte (TTFB), total response time và p95/p99.
- RTT/loss distributions và mạng Wi-Fi, mobile, VPN.
- New connection vs resumed connection.
- Số request song song, kích thước payload, các requests độc lập.
- Fallback ratio, handshake failure rate và CPU/memory chi phí.

Một hệ thống có RTT rất thấp, network ổn định và server-side bottleneck có thể không có lợi ích đáng kể; một mạng có loss cao và nhiều streams có thể cho thấy sự khác biệt rõ hơn.

## 26. Những hiểu lầm phổ biến

1. **“HTTP/3 chính là UDP truyền HTTP text.”** Sai: dùng QUIC transport bảo mật, streams và HTTP/3 framing.
2. **“UDP không tin cậy nên HTTP/3 không tin cậy.”** Sai: QUIC tạo reliable ordered streams, recovery và congestion control. UDP thuần chỉ là tầng dưới.
3. **“HTTP/3 mở TCP port 443.”** Sai khi nói về transport H3: QUIC sử dụng UDP; TCP/443 thường dành cho các phiên bản HTTPS fallback.
4. **“Mỗi datagram chứa một request.”** Sai: HTTP request ánh xạ lên QUIC streams và có thể đi qua nhiều QUIC packets/UDP datagrams.
5. **“QUIC bỏ tất cả head-of-line blocking.”** Sai: loại TCP-level cross-stream HOL nhưng còn stream-local order, congestion, QPACK dependencies và bottlenecks khác.
6. **“TLS 1.3 trên TCP là đủ để bật H3.”** Sai: cần TLS tích hợp QUIC, HTTP/3 stack và ALPN `h3`.
7. **“Alt-Svc chứng minh request đã dùng HTTP/3.”** Sai: chỉ advertise alternative; request có thể vẫn h2/h1.
8. **“DNS HTTPS RR có h3 thì QUIC chắc chắn thông.”** Sai: là metadata discovery, chưa có handshake thành công.
9. **“curl phiên bản mới chắc chắn hỗ trợ H3.”** Sai: cần build hỗ trợ HTTP3 backend; xem `curl --version`.
10. **“`HttpClient.Version.HTTP_2` trong Java 17 là đường lên HTTP3.”** Sai: enum Java 17 không có HTTP_3.
11. **“Kết nối UDP được thì HTTP/3 được.”** Sai: cần QUIC/TLS, ALPN, cert, HTTP/3 SETTINGS/streams.
12. **“QUIC 0-RTT an toàn cho POST thanh toán.”** Sai nếu thiếu biện pháp chống replay/idempotency ở tầng ứng dụng.
13. **“H3 fail thì tự chuyển về HTTP plaintext.”** Sai và không an toàn. Fallback thích hợp giữ HTTPS/TLS qua TCP.
14. **“Origin log h2 chứng minh browser dùng h2.”** Sai nếu CDN terminate HTTP3 trước origin.
15. **“Connection migration luôn xảy ra khi chuyển Wi-Fi sang 4G.”** Sai: phụ thuộc client/server, policy, path validation và hạ tầng.
16. **“Có H3 thì không cần giới hạn bộ nhớ/tốc độ.”** Sai: QUIC có flow/congestion control nhưng server vẫn cần quotas, rate limiting và phòng DoS.

## 27. Bài tập suy luận và đáp án

**Câu 1.** Một Java 17 service tạo `HttpClient.newBuilder().version(HTTP_2).build()` và dùng URI `https://api.example.com`. Có yêu cầu được HTTP/3 không?  
**Đáp án:** Không. Java 17 `HttpClient.Version` chỉ công bố HTTP_1_1/HTTP_2. HTTPS scheme không tự đồng nghĩa H3.

**Câu 2.** Server chạy HTTP/3 trên UDP/443, nhưng firewall chỉ cho TCP/443. Client hỗ trợ H3 sẽ gặp gì?  
**Đáp án:** QUIC handshake có thể thất bại/timeout. Một client phù hợp có thể fallback HTTPS trên HTTP/2 hoặc HTTP/1.1 qua TCP/443; cần đo protocol thực của response.

**Câu 3.** Server trả `Alt-Svc: h3=":443"; ma=86400`. Request nhận header đó đã chạy h3 chưa?  
**Đáp án:** Không thể suy ra. Header quảng bá endpoint H3 cho lần kết nối phù hợp, có thể được gửi qua H1/H2.

**Câu 4.** HTTP/3 có bảo đảm không mất response body nếu một UDP datagram bị mất?  
**Đáp án:** QUIC cung cấp recovery và reliable delivery cho stream khi connection hoạt động, nhưng connection có thể hết hạn/lỗi. Không thể bảo đảm request nghiệp vụ luôn hoàn thành bất chấp mọi failure.

**Câu 5.** Vì sao HTTP/3 giảm một loại head-of-line blocking so với HTTP/2?  
**Đáp án:** QUIC giao byte theo thứ tự **từng stream độc lập**, không phải mọi HTTP streams bị khóa bởi vị trí byte thiếu của **một TCP stream chung**.

**Câu 6.** H3 dùng HTTP request stream nào?  
**Đáp án:** Một request bình thường sử dụng client-initiated **bidirectional QUIC stream**; control/QPACK sử dụng các unidirectional streams khác theo protocol.

**Câu 7.** HTTPS RR chứa `alpn=h3,h2` có phải đã có TLS handshake/ALPN h3 thành công không?  
**Đáp án:** Không. Nó là DNS service metadata để client lựa chọn thử kết nối; negotiated ALPN được xác định tại connection thực.

**Câu 8.** Một client gửi POST xử lý thanh toán trong 0-RTT. Rủi ro?  
**Đáp án:** Early data có thể bị replay. Cần chính sách loại trừ unsafe operations, idempotency/replay protection và handling ở tầng HTTP/application.

**Câu 9.** CDN nhận h3 từ browser, CDN gọi origin bằng h2. Origin log h2 có hợp lý không?  
**Đáp án:** Có. Protocol version có thể khác ở hai hop; phải đo browser-to-CDN và CDN-to-origin riêng.

**Câu 10.** Chạy `curl --http3 https://example.com` trả HTTP 200 nhưng client có fallback. Có thể khẳng định h3?  
**Đáp án:** Không. Kiểm tra negotiated protocol từ verbose logs hoặc dùng `--http3-only` trên curl build hỗ trợ HTTP3.

**Câu 11.** Server bật TLS 1.3 và HTTP/2 nhưng chưa có QUIC stack; đổi Alt-Svc sang h3 là đủ chưa?  
**Đáp án:** Chưa. Cần QUIC/UDP listener, HTTP/3 mapping, ALPN h3, TLS keys/certificate và network rules.

**Câu 12.** Vì sao một UDP datagram chứa QUIC Initial 100 byte không phải kiểm tra tốt về H3?  
**Đáp án:** QUIC Initial packets chịu yêu cầu kích thước UDP datagram tối thiểu và handshake state nghiêm ngặt; gửi dữ liệu UDP tùy ý không tái hiện QUIC/HTTP3.

## 28. Tài liệu chuẩn và tham khảo

- RFC 9114 — **HTTP/3**, ánh xạ HTTP semantics lên QUIC, H3 streams, Alt-Svc, control/SETTINGS, ALPN: https://www.rfc-editor.org/rfc/rfc9114
- RFC 9000 — **QUIC: A UDP-Based Multiplexed and Secure Transport**, streams, flow control, ACK/recovery và address validation: https://www.rfc-editor.org/rfc/rfc9000
- RFC 9001 — **Using TLS to Secure QUIC**, TLS 1.3, handshake và 0-RTT replay: https://www.rfc-editor.org/rfc/rfc9001
- RFC 9002 — **QUIC Loss Detection and Congestion Control**: https://www.rfc-editor.org/rfc/rfc9002
- RFC 9204 — **QPACK: Field Compression for HTTP/3**: https://www.rfc-editor.org/rfc/rfc9204
- RFC 9460 — **SVCB and HTTPS Resource Records** để khám phá service/ALPN: https://www.rfc-editor.org/rfc/rfc9460
- RFC 7838 — **HTTP Alternative Services**, cú pháp Alt-Svc: https://www.rfc-editor.org/rfc/rfc7838
- RFC 8446 — **TLS Protocol Version 1.3**: https://www.rfc-editor.org/rfc/rfc8446
- Java 17 `HttpClient.Version` — enum chỉ có `HTTP_1_1` và `HTTP_2`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Version.html
- Java 17 `HttpClient` — version preference, gửi HTTP request: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- curl official manpage `--http3` và `--http3-only`: https://curl.se/docs/manpage.html
