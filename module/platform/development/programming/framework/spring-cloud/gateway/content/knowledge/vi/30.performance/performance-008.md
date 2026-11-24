# Đánh giá độ trễ do TLS, DNS và thiết lập kết nối

## 1. Vấn đề: API xử lý nhanh nhưng Gateway vẫn trả chậm

Trong hệ thống microservices, **Spring Cloud Gateway** có thể tiếp nhận HTTP request, chọn tuyến qua route predicate, thực thi filter chain, biến đổi path/header, khám phá dịch vụ bằng `lb://`, xác thực, giới hạn lưu lượng, retry, circuit breaker và theo dõi request. Một endpoint backend mất 15 ms xử lý vẫn có thể khiến người dùng chờ 150 ms hoặc hơn khi phải **phân giải DNS, mở kết nối TCP, bắt tay TLS hoặc đợi connection pool**.

Giả sử một request `GET /api/catalog/items/42` đi qua:

~~~text
Mobile client -- HTTPS --> Ingress -- HTTP(S) --> Spring Cloud Gateway
                                                |
                                                | HTTPS / lb://catalog-service
                                                v
                                           Catalog backend
~~~

Ứng dụng Catalog báo thời gian xử lý 12 ms. Tuy nhiên lần gọi đầu tiên sau deployment có thể cần DNS lookup, TCP connect và TLS handshake cho đường **Gateway → Catalog**. Các lần gọi kế tiếp tái sử dụng kết nối có thể nhanh hơn đáng kể. Nếu chỉ nhìn thời gian xử lý Catalog, bạn sẽ tối ưu nhầm database, filter Java hoặc tăng số replicas mà không sửa được nguyên nhân.

Bài **“Đánh giá độ trễ do TLS, DNS và thiết lập kết nối”** thuộc chương **Hiệu năng** của module **SPRING_CLOUD_GATEWAY**. Mục tiêu không phải chỉ làm một biểu đồ latency, mà là **phân rã độ trễ theo từng hop, xác định phép đo có thật sự đo lớp mong muốn, thử có đối chứng và tối ưu mà không đánh đổi bảo mật hoặc độ tin cậy**.

### Sau bài học, bạn có thể

1. Phân biệt DNS, TCP connect, TLS handshake, chờ lấy kết nối từ pool, upstream processing và response transfer.
2. Giải thích tại sao **một request có thể có nhiều DNS lookup và nhiều TLS handshakes** trên những hop khác nhau, trong khi request tái sử dụng kết nối có thể không cần chúng.
3. Dùng `curl --write-out` để ước lượng các phase ở **client → Gateway**, đọc đúng các mốc thời gian cộng dồn và những giới hạn của phép đo.
4. Thiết kế phép đo riêng cho **Gateway → upstream** bằng metrics/tracing của HTTP client, pool và backend stub, không nhầm với client-side timings.
5. Phân biệt **DNS trong hệ điều hành/JVM/Netty**, TTL/cache và phân giải `lb://` qua service discovery.
6. Hiểu TLS 1.2/1.3, session resumption, SNI/ALPN, mTLS, connection reuse và các tác động tới cold-start latency.
7. Thiết lập một thí nghiệm **cold connection so với warm pooled connection**, có baseline, p50/p95/p99, counters và nhóm đối chứng.
8. Chẩn đoán các vấn đề như DNS timeout, TCP refused, TLS cert error, pool acquire timeout, stale keep-alive, HTTP/2 stream saturation và retry amplification.
9. Chọn những tối ưu phù hợp cho **Gateway Server WebFlux (Reactor Netty)** hoặc **Gateway Server Web MVC (Servlet/HTTP client)** theo đúng phiên bản.

> **Giới hạn phiên bản:** Ví dụ chính nói về **Spring Cloud Gateway Server WebFlux** và Reactor Netty. Khi đề cập Web MVC, chúng ta nêu riêng Servlet và outbound HTTP client. Tên starter/property/metrics cụ thể khác theo dòng Spring Boot/Spring Cloud Gateway/Reactor Netty; phải kiểm tra **dependency BOM và documentation của bản đang chạy**, không lấy cấu hình WebFlux áp nguyên sang MVC.

## 2. Bản đồ hai chiều HTTP: đo đúng hop trước khi tối ưu

Một Gateway thường vừa đóng vai **HTTP server** ở phía client, vừa là **HTTP client** ở phía backend. Nếu có ingress/service mesh, sẽ còn những chặng HTTP/TLS khác.

~~~mermaid
flowchart LR
    C["Browser / Mobile"] -->|"DNS + TCP + TLS"| I["Public ingress / LB"]
    I -->|"TCP hoặc TLS"| G["Spring Cloud Gateway"]
    G -->|"Pool acquire + DNS + TCP + TLS"| U["Catalog upstream"]
    U -->|"Response bytes"| G
    G -->|"Response"| I
    I -->|"Response"| C
~~~

### Các thành phần thường xuất hiện trên một request

| Thành phần | Diễn ra ở đâu? | Khi nào đáng kể? |
| --- | --- | --- |
| **DNS lookup** | Client resolve public host; Gateway hoặc HTTP client resolve upstream host | Cache miss, TTL hết, resolver chậm, nhiều hostname |
| **TCP connect** | Mỗi hop mở TCP connection mới | Cold connection, packet loss, SYN retransmit, cross-region RTT |
| **TLS handshake** | Hop HTTPS mới, trước khi gửi HTTP application data | Certificate chain, mTLS, RTT cao, TLS version/resumption |
| **Pool acquire** | Gateway outbound client chọn hoặc chờ connection | Pool đầy, max connections, pending queue, HTTP/2 stream limits |
| **Route/filter processing** | Gateway application | Predicate, auth, rewrite, retry, circuit breaker |
| **Service discovery** | Gateway chọn ServiceInstance cho `lb://` | Registry cache, topology, health filtering |
| **Backend application** | Service đích | DB, cache, business logic |
| **Response transfer** | Backend → Gateway → client | Payload lớn, băng thông, TCP flow control, client chậm |

**Một câu hỏi phải trả lời đầu tiên:** HTTPS từ client đến ingress có **kết thúc TLS ở ingress**, hay end-to-end tới Gateway? Nếu ingress terminate TLS rồi giao tiếp HTTP nội bộ, việc tối ưu TLS ở Gateway outbound chỉ ảnh hưởng Gateway → Catalog, **không ảnh hưởng** client → ingress. Không thể dùng một tập `curl` time measurements tại laptop để khẳng định DNS/TLS outbound của JVM đang chậm.

### Lộ trình một request có thể gồm nhiều kết nối

~~~mermaid
sequenceDiagram
    participant Client
    participant Ingress
    participant Gateway
    participant Resolver as DNS / Discovery
    participant Catalog
    Client->>Ingress: Public DNS + TCP + TLS (nếu kết nối mới)
    Ingress->>Gateway: HTTP/TLS request
    Gateway->>Resolver: Chọn service instance / resolve host (nếu cần)
    Resolver-->>Gateway: Host + IP / instance
    Gateway->>Catalog: TCP connect + TLS (nếu không có pooled connection)
    Gateway->>Catalog: GET /catalog/items/42
    Catalog-->>Gateway: 200 + body
    Gateway-->>Ingress: HTTP response
    Ingress-->>Client: Response
~~~

Trong một request **warm**, cả client/ingress/Gateway có thể tái sử dụng kết nối trên các hop tương ứng; các bước DNS/TCP/TLS **không nhất thiết chạy lại**. Ngược lại, khi Gateway gọi nhiều upstream services hoặc retry sang instance khác, một operation có thể tạo thêm các bước kết nối ở nhiều đích.

## 3. Công thức ngân sách độ trễ và giới hạn khi cộng số liệu

Để tìm bottleneck, có thể mô hình hóa độ trễ của một lần gọi qua Gateway bằng các phase:

\[
T_{\text{total}} \approx T_{\text{client-to-gateway}}
+T_{\text{gateway-route}}
+T_{\text{pool-wait}}
+T_{\text{resolve}}
+T_{\text{tcp-connect}}
+T_{\text{tls}}
+T_{\text{upstream-wait}}
+T_{\text{response-transfer}}
\]

**Đây là ngân sách khái niệm trên critical path**, không phải công thức luôn cộng độc lập được từ mọi counters. Phải làm rõ:

- `T_client-to-gateway` có thể gồm cả public DNS, TCP, TLS, ingress queue, request transfer và nhiều hop nội bộ.
- `T_pool-wait` có thể kết thúc bằng **pooled connection reuse**, lúc đó DNS/connect/TLS bằng 0 cho request này.
- `T_resolve` chỉ xuất hiện khi cần resolve một địa chỉ mà cache/resolver chưa có hoặc đã hết hạn; `lb://` discovery selection và DNS lookup **không phải cùng thao tác**.
- HTTP client có thể xử lý một số bước đồng thời hoặc bất đồng bộ; retry/fallback có thể tạo **nhiều lần đo** cho một inbound request.
- `T_response-transfer` chịu ảnh hưởng body size, streaming, băng thông và tốc độ đọc của client.

### Số liệu minh họa cho cold và warm request

| Pha | Cold request minh họa | Warm request minh họa |
| --- | ---: | ---: |
| Backend/route computation và overhead khác | 35 ms | 35 ms |
| DNS outbound | 8 ms | 0 ms |
| TCP outbound connect | 20 ms | 0 ms |
| TLS outbound handshake | 30 ms | 0 ms |
| Chờ pool / response transfer bổ sung | 7 ms | 5 ms |
| **Tổng theo giả định cộng tuần tự** | **100 ms** | **40 ms** |

Đây là **số liệu giả định cho bài học**, không phải benchmark hoặc mặc định của Spring Cloud Gateway. Nếu upstream nằm cùng availability zone, chi phí có thể khác nhiều; nếu đi cross-region qua proxy hoặc bị packet loss, chi phí có thể lớn hơn. Tối ưu một pha chỉ có giá trị nếu bạn đã chứng minh nó đáng kể trong **traffic mix thực tế**.

### Không cộng p95 của từng pha để suy ra p95 tổng

Giả sử p95 DNS là 20 ms, p95 TCP 30 ms, p95 TLS 40 ms. **Không được khẳng định** p95 tổng của ba pha là 90 ms. Các percentile đo trên những phân phối khác nhau, không nhất thiết xảy ra trong cùng request. Muốn biết p95 end-to-end, phải đo **trên phân phối thời gian toàn request**; muốn tìm nguyên nhân tail latency, hãy gắn phase timings/trace với **cùng request hoặc cùng connection attempt**.

### Throughput khác latency

Little's law cho một hệ ổn định ở trạng thái trung bình:

\[
L = \lambda W
\]

Với 500 request/giây và thời gian request trung bình 0,1 giây, số requests đang xử lý trung bình xấp xỉ 50. Nếu vì chờ kết nối và handshake mà W tăng tới 0,3 giây ở cùng arrival rate, L tăng xấp xỉ 150. Đây là **trung bình operation concurrency**, không đồng nghĩa chính xác số Servlet threads hay Reactor Netty channels. Nó cho thấy thêm latency có thể gây áp lực lên **connections, queues, memory và timeout budgets** ngay cả khi CPU backend không bận.

## 4. DNS: từ hostname đến IP và tại sao cache quyết định độ trễ

**DNS resolution** biến hostname thành địa chỉ IP hoặc các bản ghi cần thiết. Trong hệ thống Gateway có thể có nhiều lớp DNS:

~~~text
Browser/mobile resolver
    -> public DNS name of ingress
Ingress/proxy resolver
    -> hostname of Gateway service (nếu có)
Gateway outbound HTTP client resolver
    -> hostname của upstream instance
Backend resolver
    -> dependency khác, không thuộc cùng phase Gateway outbound
~~~

Ở phía Gateway:

1. Route có thể dùng một URL như `https://catalog.internal.example`; HTTP client cần địa chỉ cho hostname này khi mở connection mới.
2. Route có thể dùng `lb://catalog-service`; Spring Cloud LoadBalancer/discovery chọn ServiceInstance trước, rồi nếu instance host **không phải IP** thì HTTP client vẫn có thể phải DNS resolve.
3. Gateway hoặc proxy có thể đi qua service mesh/local DNS cache; phase DNS đo ở JVM có thể khác phase DNS ngoài hệ thống.

### DNS latency gồm những gì?

| Pha hoặc sự cố | Quan sát |
| --- | --- |
| Resolver cache hit | Gần như không cần query tới DNS upstream; chỉ lookup bộ nhớ |
| Cache miss | Resolver gửi query, có thể truy vấn recursive DNS |
| CNAME chain | Cần giải thêm tên; mức độ song song tùy resolver |
| A/AAAA resolution | Có thể hỏi IPv4/IPv6, chọn thứ tự/thử kết nối |
| NXDOMAIN/negative cache | Kết quả thất bại có thể được cache theo chính sách |
| DNS timeout/retransmission | Tail latency cao, có thể trả lỗi trước khi TCP bắt đầu |
| TTL expiration | Cần lấy thông tin mới, nhưng không nhất thiết mỗi request tạo một query |
| IP rotation | Kết nối đang mở vẫn có thể tiếp tục dùng IP cũ |

**TTL ngắn không có nghĩa DNS lookup xảy ra trên mọi request** nếu outbound connection pool còn có kết nối tái sử dụng. Ngược lại, nếu connection churn rất lớn, dù cache hiệu quả, Gateway vẫn trả giá TCP/TLS trên những lần mở kết nối mới.

### JVM DNS và Reactor Netty resolver không phải một cache duy nhất

Các phiên bản Java có chính sách name-service cache của JVM (ví dụ `networkaddress.cache.ttl` và negative TTL trong cơ chế security properties), trong khi Reactor Netty/Netty có thể sử dụng **DNS resolver, event loop và cache riêng**. Spring Cloud Gateway Server WebFlux thường dùng Reactor Netty HTTP client; Gateway Server Web MVC dùng outbound client phù hợp Servlet stack.

Vì vậy:

- Chỉnh JVM DNS TTL **không bảo đảm** Netty DNS resolver cache cũng đổi theo.
- `dig` hoặc `nslookup` chạy trên máy operator **không đo chính xác DNS cache trong process Gateway**.
- Một resolver có thể cache A và AAAA theo chính sách riêng; load balancer/service mesh có thể cache endpoints của nó.
- Thay TTL cần xem ảnh hưởng của **IP rollover, failover, lượng query DNS và negative caching**, không chỉ giảm `time_namelookup`.

Không đặt TTL bằng 0 hoặc “cache forever” để sửa p99 khi chưa xác minh hệ thống cần **khả năng cập nhật IP và khôi phục sau thay đổi topology**.

## 5. DNS và service discovery: hai lần chọn đích khác nhau

Spring Cloud Gateway có thể dùng route:

~~~yaml
# Ví dụ khái niệm cho Gateway Server WebFlux bản hỗ trợ namespace này.
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1
~~~

Trong luồng này:

1. **Gateway route matching** tìm `catalog` theo `Path`.
2. **Service discovery/LoadBalancer** chọn một `ServiceInstance` của `catalog-service`.
3. Nếu instance host là hostname, outbound client cần DNS lookup hoặc cache hit để lấy IP.
4. **Connection pool** thử chọn connection đã mở tới endpoint phù hợp; nếu không có, nó phải tạo TCP connection mới và TLS khi HTTPS.

~~~mermaid
flowchart TD
    A["Route lb://catalog-service"] --> B["Select ServiceInstance"]
    B --> C{"Có pooled connection phù hợp?"}
    C -->|Có| R["Reuse HTTP connection"]
    C -->|Không| D{"Đã có resolved address hợp lệ?"}
    D -->|Có| E["TCP connect"]
    D -->|Chưa| Q["DNS resolution / cache"]
    Q --> E
    E --> T{"HTTPS?"}
    T -->|Có| H["TLS handshake"]
    T -->|Không| N["HTTP request"]
    H --> N
    R --> N
~~~

Sơ đồ trên là **khái niệm**; trong implementation, client có thể tra resolver/cache trước khi xét pool, một pool có thể được phân vùng theo host/IP/proxy/SNI, và HTTP/2 có thể dùng nhiều streams trên một connection. Điều phải đo là **thực tế code path của phiên bản đang chạy**, không coi sơ đồ là class-level trace tuyệt đối.

### Service discovery chậm có phải DNS chậm?

Không. Một load balancer có thể chờ cập nhật registry, kiểm tra health, lọc zone hoặc cache service instances ngay cả khi DNS trả kết quả tức thì. Trong điều tra, ghi riêng:

- Thời gian chọn instance từ registry/load balancer.
- Thời gian DNS resolve hostname của instance, nếu có.
- Thời gian pool acquire/connect/TLS.
- Thời gian request/response.

Nếu tất cả được dồn vào metric `upstream latency`, sẽ khó biết cần sửa DNS resolver, registry cache, connection pool hay chính backend.

## 6. Khảo sát DNS đúng cách: resolver, TTL và địa chỉ thay đổi

Khi nghi DNS là nguyên nhân, cần trả lời **ba câu hỏi**: Có DNS lookup thật sự trong request chậm không? Nó hỏi resolver nào? Sau khi trả lời, HTTP client đã kết nối tới địa chỉ nào?

### Các công cụ đơn giản và giới hạn

~~~bash
# Tra bản ghi A từ resolver mặc định của máy đang chạy lệnh.
dig +noall +answer catalog.internal.example A

# Tra bản ghi AAAA (nếu môi trường có IPv6).
dig +noall +answer catalog.internal.example AAAA

# Ví dụ quan sát resolver có thông tin khác nhau theo thời điểm.
nslookup catalog.internal.example
~~~

Tên hostname trên là **giả định**, chỉ thay bằng hostname của môi trường test hoặc host đã được phép kiểm tra. `dig`/ `nslookup` có thể bỏ qua cache JVM/Netty của Gateway và truy vấn qua resolver khác, nên **không thể trực tiếp kết luận JVM đã chờ DNS từng ấy milliseconds**. Cột TTL của DNS answer cho biết thời gian cache còn lại theo resolver đang trả, **không phải lịch sử truy vấn của request Gateway**.

### Phân biệt DNS lỗi và connect lỗi

| Sự kiện | Điều đã xảy ra | Bằng chứng gợi ý |
| --- | --- | --- |
| DNS NXDOMAIN | Không có tên hợp lệ trong hệ thống DNS đang hỏi | DNS answer/error, chưa có đích để TCP connect |
| DNS timeout | Resolver không trả lời đúng deadline | DNS resolver timeout/error, có thể nhiều retransmissions |
| DNS trả IP cũ | Cache chưa hết TTL hoặc connection cũ còn tồn tại | Answer/cache snapshot, remote address của connection |
| DNS trả IP mới nhưng TCP refused | DNS đã thành công, đích từ chối TCP | Connect failure, SYN/RST |
| A hoạt động nhưng AAAA không đi được | Chọn/đua địa chỉ IPv4/IPv6 không tối ưu | Phân tích address family và connect attempts |
| Discovery không có instance | Chưa chọn được upstream service | LoadBalancer/discovery logs, **không phải DNS NXDOMAIN** |
| TLS hostname mismatch | Đã tới được TLS peer nhưng identity không hợp lệ | Certificate/SAN/SNI validation error |

### Kiểm thử DNS TTL và pool một cách tách biệt

Thí nghiệm mẫu trong lab:

1. Tạo hostname nội bộ test có DNS A/AAAA record và TTL có thể kiểm soát.
2. Gọi Gateway khi chưa có outbound connection; ghi DNS lookup, remote IP, connect và TLS.
3. Gọi lại nhiều lần **trong cùng Gateway process**, ghi số lần connection reuse.
4. Chuyển DNS record từ IP stub A sang IP stub B, chờ TTL theo policy test.
5. Quan sát các **connection mới** chọn địa chỉ nào và **pooled connections cũ** còn trỏ tới đâu.
6. Thay chính sách max connection lifetime/idle phù hợp, lặp lại phép đo.

Đừng kết luận “DNS không cập nhật” chỉ vì request vẫn tới stub A; có thể Gateway đang tái sử dụng TCP connection tới A. Đừng buộc đóng toàn bộ connections trên production để “làm mới DNS” nếu chưa xem hậu quả latency/reconnect storm.

### Negative caching và khôi phục

Một lỗi DNS tạm thời có thể được cache (NXDOMAIN hoặc lỗi khác tùy resolver). Khi DNS record đã được sửa, một số instances có thể vẫn báo lỗi cho tới khi negative-cache TTL hết. Trong sự cố, cần tách:

- Thời điểm authoritative DNS có bản ghi mới.
- Resolver recursive cache đang trả gì.
- Resolver JVM/Netty trong process đang giữ gì.
- Connections cũ tới IP nào.

Việc sửa DNS record không đồng nghĩa mọi JVM instance lập tức sử dụng IP mới.

## 7. TCP connect: một RTT không phải toàn bộ câu chuyện

TCP thiết lập kết nối trước khi HTTP request thông thường có thể được gửi qua TLS. Với kết nối TCP mới, **three-way handshake** điển hình:

~~~mermaid
sequenceDiagram
    participant G as Gateway HTTP client
    participant U as Upstream TCP server
    G->>U: SYN
    U-->>G: SYN-ACK
    G->>U: ACK
    Note over G,U: Kết nối TCP established
~~~

Trong điều kiện lý tưởng, phần bắt tay chiếm khoảng **một RTT** trước khi ứng dụng bắt đầu trao đổi bytes cho TLS/HTTP. Đây là mô hình gần đúng, không phải cam kết: kernel scheduling, backlog, SYN retransmit, packet loss, DNS/connection attempts qua nhiều IP, NAT, proxy và cross-region distance đều có thể làm trễ.

### Những yếu tố làm connect lâu

| Nguyên nhân | Biểu hiện | Hướng điều tra |
| --- | --- | --- |
| **RTT địa lý cao** | Connect và TLS đều tăng ở kết nối mới | Kiểm tra zone/region, network path |
| **Packet loss/retransmission** | p99 connect tăng đột biến, p50 bình thường | TCP retransmission metrics, network telemetry |
| **Không có listener** | Connect refused nhanh | Service port, readiness, LB target |
| **Firewall/security group drop** | Connect timeout dài | NetworkPolicy/firewall, test đường mạng có phép |
| **SYN backlog hoặc accept queue quá tải** | Connection establishment tăng hoặc thất bại | Server accept metrics, backlog/drop counters |
| **NAT/sidecar/proxy chậm** | Chậm chỉ trên một network path | So sánh direct vs through-proxy trong lab |
| **IPv6/IPv4 fallback** | Một số attempts rất chậm | Resolver/Happy Eyeballs behavior của client |
| **Connection pool hết chỗ** | Request chờ nhưng TCP connect metric có thể không tăng | Pool acquire time và pending queue |

**Pool acquire timeout không phải TCP connect timeout.** Nếu max connections đã được dùng hết, request có thể đứng chờ **trước** khi có một TCP attempt. Tăng connect timeout không giải quyết pool saturation; tăng maxConnections vô hạn có thể đẩy quá tải sang backend.

### Connect timeout và response timeout khác nhau

- **Connect timeout:** giới hạn thời gian thiết lập kết nối TCP tới một địa chỉ, theo API client đang dùng.
- **DNS resolution timeout:** có thể là giới hạn riêng của resolver và không tự nằm trong connect timeout của mọi implementation.
- **Pool pending acquire timeout:** giới hạn thời gian chờ lấy một connection từ pool.
- **TLS handshake timeout:** có thể được cấu hình riêng; không đồng nghĩa TCP connect timeout.
- **Response/read timeout:** liên quan thời gian chờ đọc HTTP response sau các bước trước đó, với semantics do client định nghĩa.
- **Overall operation deadline:** giới hạn tổng thời gian request có thể tiếp tục qua retries, discovery, HTTP và serialization.

Vì vậy, **đặt connect timeout bằng 500 ms không đồng nghĩa “mọi request Gateway sẽ trả trong 500 ms”**. Một operation có thể dành thời gian vào DNS, pool, TLS, backend và response transfer trước khi hết deadline tổng.

## 8. TLS handshake: thời gian an toàn kết nối, không chỉ CPU mã hóa

TLS bảo vệ tính bí mật và toàn vẹn của kết nối HTTPS. Nhưng khi mở **một kết nối TLS mới**, hai bên cần đàm phán phiên bản/cipher, xác thực chứng chỉ và thiết lập khóa trước khi trao đổi HTTP application data thông thường.

### Bắt tay TLS 1.2 và TLS 1.3 ở mức khái niệm

| Đặc điểm | TLS 1.2 full handshake (mô hình điển hình) | TLS 1.3 full handshake (mô hình điển hình) |
| --- | --- | --- |
| Số RTT bắt tay TLS trước application data | Thường khoảng **2 RTT** | Thường khoảng **1 RTT** |
| Khởi tạo trên TCP | Vẫn cần TCP connect thông thường | Vẫn cần TCP connect thông thường |
| Resumption | Có cơ chế session resumption riêng | Có PSK/session tickets, resumption |
| Certificate verification | Cần xác minh peer identity/trust | Cần xác minh peer identity/trust |
| mTLS | Có thể yêu cầu client certificate | Có thể yêu cầu client certificate |
| 0-RTT | Không theo cơ chế TLS 1.3 early data | Có thể có early data nếu được bật/hỗ trợ, với replay risk |

Các RTT này là **quy ước so sánh protocol**, không phải đo thực tế đảm bảo. DNS, TCP connect, queue, certificate verification CPU, TLS implementation, ticket/key rotation, network loss, OCSP/revocation checking theo cấu hình và proxy hops có thể làm kết quả khác.

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant U as HTTPS upstream
    Note over G,U: TCP connection đã thiết lập
    G->>U: ClientHello (SNI, ALPN, TLS parameters)
    U-->>G: ServerHello, certificates, handshake messages
    Note over G,U: Validate chain, hostname, keys; complete handshake
    G->>U: HTTP request over encrypted channel
    U-->>G: HTTP response over encrypted channel
~~~

### Phân biệt TLS CPU cost và TLS network cost

Một TLS handshake có thể tốn:

1. **RTT** trao đổi handshake messages.
2. **CPU** thực hiện cryptography, certificate chain verification và ký/kiểm tra chữ ký.
3. **Certificate/configuration checks** như CA trust, hostname/SAN, SNI, client cert khi mTLS.
4. **Transport waits** do packet loss, congestion, server overload hoặc proxy negotiation.

Nếu TLS p95 tăng mạnh trong khi RTT ổn định, xem CPU/handshake concurrency/certificate verification. Nếu cả TCP connect và TLS cùng tăng theo RTT cross-zone, **placement/network path** có thể quan trọng hơn đổi cipher. Tối ưu cipher mà không kiểm tra security policy hoặc client compatibility có thể làm hệ thống yếu đi.

### TLS ở hai hop không dùng chung phiên

~~~text
Browser --TLS A--> Public ingress --HTTP/TLS B--> Gateway
Gateway --TLS C--> Catalog
~~~

Các session, chứng chỉ, truststore và connection pools **tách biệt**. TLS session resumption giữa Browser và ingress **không rút ngắn trực tiếp** TLS handshake mới giữa Gateway và Catalog. Nếu có service mesh sidecar, có thể thêm một hop mTLS hoặc thay vị trí TLS termination; phải vẽ **topology thật** trước khi tính.

### SNI, ALPN và TLS errors

**SNI** giúp server chọn chứng chỉ theo hostname. **ALPN** giúp đàm phán application protocol, ví dụ HTTP/1.1 hoặc HTTP/2, nếu client/server hỗ trợ. Cấu hình sai SNI/hostname có thể tạo certificate mismatch; ALPN khác dự kiến có thể khiến HTTP client chọn cơ chế kết nối/stream khác.

Trong performance test, **không sử dụng `-k`/`--insecure` với curl, không dùng trust-all SSL context, không tắt hostname verification** chỉ để có một con số latency đẹp hơn. Một kết quả nhanh nhờ bỏ xác thực peer là **một kết nối không còn cùng security contract**, không phải tối ưu hợp lệ.

## 9. mTLS, session resumption và 0-RTT: hiệu năng phải đi cùng an toàn

### Mutual TLS

Với **mTLS**, upstream còn xác thực client certificate của Gateway. Điều này tăng điều kiện bắt tay và quản lý danh tính, nhưng không được bỏ mTLS chỉ để tiết kiệm vài milliseconds nếu nó là yêu cầu bảo mật service-to-service.

Những yếu tố cần đo:

- TLS handshake success/failure và duration.
- Certificate chain/trust validation behavior của hai phía.
- Certificate rotation, expiration và khả năng session resumption.
- Backend TLS accept/handshake concurrency dưới burst.
- Lỗi từ truststore/keystore hoặc SNI khác với lỗi TCP.

Không gửi private key/client certificate vào logs, tracing hoặc báo cáo latency. Nếu dùng test certificates, tách môi trường test khỏi production và kiểm tra hostname/certificate **thật**, không bypass.

### Session resumption không đồng nghĩa connection reuse

Hai khái niệm:

| Cơ chế | Hoạt động | Chi phí còn lại |
| --- | --- | --- |
| **Connection reuse/keep-alive** | Dùng lại cùng TCP+TLS connection đã mở | Không cần TCP/TLS handshake mới cho request tái sử dụng |
| **TLS session resumption** | Mở connection mới nhưng tái sử dụng thông tin phiên/PSK hợp lệ | Thường vẫn cần TCP connect và một phần TLS negotiation |

Với một route có nhiều GET ngắn, **reusing existing connection** thường có lợi rõ ràng hơn cố tối ưu full handshake ở mỗi request. Resumption hữu ích khi cần reconnect, nhưng tác dụng phụ thuộc TLS version, ticket lifetime, server/client configuration và các chính sách bảo mật.

### 0-RTT không phải nút tăng tốc vô hại

TLS 1.3 có cơ chế early data (**0-RTT**) trong một số triển khai, nhưng early data có **replay risk**. Không tự gửi POST đặt hàng/thanh toán hoặc thao tác thay đổi trạng thái trong 0-RTT khi không có bảo vệ idempotency/replay thích hợp. Gateway HTTP client và backend có thể không hỗ trợ early data hoặc không bật theo mặc định; **đừng giả định “TLS 1.3 = mọi HTTP request gửi trước handshake và nhanh hơn 1 RTT”**.

### TLS termination ở ingress có thể che latency outbound

Nếu `curl` từ laptop báo handshake 18 ms tới `api.example.test`, số đó có thể là **TLS của laptop → CDN/ingress**, trong khi Gateway → Catalog có handshake 35 ms độc lập. Muốn biết hop nào chậm, phải đo từ **Gateway outbound HTTP client** hoặc test bên trong network segment tương ứng.

## 10. HTTP keep-alive, connection reuse và HTTP/2 multiplexing

Với HTTP/1.1, các requests tuần tự có thể dùng lại **persistent TCP connection** nếu client/server không đóng nó và pool quản lý phù hợp. Với HTTP/2, một connection có thể chứa **nhiều concurrent streams**, giảm nhu cầu mở nhiều TCP+TLS connections cho cùng origin, tùy stream limits và implementation.

~~~mermaid
flowchart TD
    A["Many inbound requests"] --> P["Gateway outbound pool"]
    P --> H1["HTTP/1.1 connection A"]
    P --> H2["HTTP/1.1 connection B"]
    P --> H3["HTTP/2 connection with multiple streams"]
    H1 --> U["Catalog"]
    H2 --> U
    H3 --> U
~~~

| Mô hình | Lợi ích | Giới hạn |
| --- | --- | --- |
| Mỗi request mở connection mới | Đơn giản để benchmark cold path | DNS/TCP/TLS lặp lại, dễ tăng CPU/latency |
| HTTP/1.1 keep-alive + pool | Giảm connect/handshake, có thể phân phối request trên nhiều connections | Idle timeout, stale connections, pool wait |
| HTTP/2 multiplexing | Nhiều streams cùng connection, giảm số handshakes trong một số workload | MAX_CONCURRENT_STREAMS, TCP connection-level congestion/HoL khi mất packet |
| HTTP/2 nhiều connections | Có thể tăng capacity khi stream limits | Thêm connect/TLS, memory/socket overhead |
| HTTP/3/QUIC | Khác TCP/TLS-over-TCP, kết nối/handshake khác | Chỉ áp dụng khi hạ tầng và client/server thực sự hỗ trợ |

**Đừng khẳng định Gateway Server WebFlux hoặc Web MVC tự dùng HTTP/2 outbound cho mọi route.** Phải kiểm tra protocol negotiation, client implementation, ALPN và backend support. HTTP/3 không nên đo theo công thức TCP three-way handshake + TLS-over-TCP; đó là **transport khác**, ngoài phạm vi các ví dụ HTTP/1.1/TLS-over-TCP của bài.

### Keep-alive và stale connections

Nếu backend hoặc LB đóng kết nối sau 30 giây idle nhưng Gateway pool vẫn giữ kết nối lâu hơn, request tái sử dụng connection có thể gặp reset/broken pipe. Một retry an toàn cho GET có thể che lỗi sau đó, nhưng cũng tăng tail latency và outbound attempts. Đặt **max idle time** phù hợp với timeout phía upstream/LB và theo dõi:

- New vs reused connections.
- Idle connection eviction.
- Connection reset khi tái sử dụng.
- Retry attempts sau stale connection.
- Active/pending pool queue và connection lifetime.

**Không đặt idle timeout bằng 0 hoặc vô hạn chỉ để tăng reuse**; điều đó có thể giữ stale sockets và làm lỡ DNS rotation. Cân bằng reuse, failover và giới hạn tài nguyên bằng kết quả đo.

## 11. Connection pool: đừng đo nhầm chờ lấy connection thành TLS chậm

Khi nhiều requests đồng thời cần gọi Catalog, **outbound connection pool** giúp tái sử dụng HTTP connections nhưng cũng là một tài nguyên hữu hạn. Nếu mọi connection đang bận hoặc đạt giới hạn streams, request mới có thể phải chờ.

~~~mermaid
flowchart TD
    R["New outbound request"] --> P{"Pool có connection phù hợp?"}
    P -->|Có, còn capacity| U["Reuse connection/HTTP2 stream"]
    P -->|Không| W{"Có thể tạo connection mới?"}
    W -->|Có| H["Resolve / TCP / TLS"]
    W -->|Đạt giới hạn| Q["Pending acquire queue"]
    Q --> T{"Có capacity trước timeout?"}
    T -->|Có| U
    T -->|Không| E["Acquire timeout / fail-fast"]
    U --> S["Send HTTP request"]
    H --> S
~~~

### Các tham số và số đo chính

| Nhóm | Ý nghĩa | Dấu hiệu cấu hình chưa phù hợp |
| --- | --- | --- |
| **max connections** | Giới hạn số TCP connections pool có thể duy trì trong phạm vi áp dụng | Tăng quá cao đẩy tải lên backend, tăng TLS/FD/memory |
| **pending acquire limit** | Số requests có thể chờ connection | Queue lớn làm p99 cao, tăng memory |
| **pending acquire timeout** | Thời gian tối đa chờ pool capacity | Acquire timeout tăng ngay cả khi DNS/TCP/TLS nhanh |
| **max idle time** | Giới hạn idle lifetime của pooled connection | Quá dài: stale socket; quá ngắn: reconnect churn |
| **max life time** | Giới hạn tuổi connection dù còn hoạt động/reuse theo policy | Quá ngắn: tạo handshakes liên tục |
| **active/idle/pending** | Trạng thái pool theo thời gian | Pending tăng khi active chạm trần |
| **new connections/s** | Mức connection churn | Cao dù QPS không đổi có thể do idle, reset hoặc misconfig |
| **connection utilization / HTTP2 streams** | Capacity thật trên TCP connection | Stream saturation dù số TCP connections thấp |

Không chỉ nhìn CPU của Gateway. Một HTTP client đang **chờ pool** có thể làm throughput giảm trong khi CPU thấp; tăng `maxConnections` có thể giúp nếu backend còn capacity, nhưng cũng có thể làm **overload downstream** và tăng retry/timeout.

### Mẫu Reactor Netty cho thí nghiệm HTTP client độc lập

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

ConnectionProvider provider = ConnectionProvider.builder("catalog-lab")
        .maxConnections(100)
        .pendingAcquireMaxCount(200)
        .pendingAcquireTimeout(Duration.ofMillis(500))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .build();

HttpClient labClient = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1000)
        .responseTimeout(Duration.ofSeconds(3));

// labClient được dùng trong một benchmark/test HTTP client riêng.
// Giải phóng provider khi fixture hoặc ứng dụng thực sự đóng.
~~~

Đây là **đoạn cấu hình Reactor Netty HTTP client độc lập**, không phải bean Spring Cloud Gateway tự nhận. Không tự giả định `HttpClient.create(provider)` được Gateway Server WebFlux dùng chỉ vì bạn tạo biến `labClient` trong một class. Muốn thay đổi Gateway outbound client, dùng **đúng `HttpClientCustomizer`/configuration properties hoặc extension point của version Gateway** đã khóa; phải xác minh wiring bằng metrics/tests.

Ngoài ra:

- `responseTimeout` không tự là overall deadline của một operation nhiều retries.
- `CONNECT_TIMEOUT_MILLIS` áp cho TCP connect, không mô tả đầy đủ DNS/pool/TLS.
- Một pool có thể phân vùng theo destination/proxy/protocol; “max 100” cần diễn giải theo scope thực của implementation.
- Khi ứng dụng dừng, phải quản lý lifecycle của resources theo framework; không `dispose()` global provider đang được request khác sử dụng.

## 12. Đo lường đa lớp: HTTP metrics, pool, tracing và network

Muốn kết luận DNS/TLS/connect đang gây latency, cần số liệu có **độ phân giải đúng**. Một metric `http.server.requests` hoặc gateway route timer thường chỉ cho biết **tổng xử lý inbound**, không tự phân biệt DNS, TCP và TLS.

### Hệ thống đo khuyến nghị

| Tầng | Số đo cần có | Giới hạn |
| --- | --- | --- |
| Client/browser | DNS, connect, TLS, TTFB, total theo client | Đo tới public edge, không thấy riêng outbound Gateway |
| Gateway server | Inbound request count, duration/status, route ID | Nhiều handler/security errors có thể nằm trước route |
| Gateway route/filter | Chọn route, filter execution, fallback/retry outcome | Chỉ đo những requests thực sự đi qua filter |
| HTTP client outbound | Pool acquire, new/reused connections, connect time, TLS handshake time, response time | Tên metrics/hooks phụ thuộc Reactor Netty/client version |
| DNS resolver | Cache hits/misses, queries, duration, negative answers, timeouts | Chỉ có nếu client/resolver cung cấp hoặc được instrument |
| Service discovery | Lookup instance, cache refresh, no-instance | **Không phải DNS duration** |
| Backend | Accept/handshake, request duration, status | Không thấy chi phí DNS/TCP phía Gateway nếu chưa đo |
| OS/network | TCP RTT, retransmissions, socket states, packet loss | Thường cần quyền/agent và phân biệt process |

### Không đoán tên metric trước khi kiểm tra version

Reactor Netty/Micrometer, Spring Boot Actuator và Spring Cloud Gateway có các meter names/tags thay đổi theo release và cấu hình. Một số client metrics cần **bật đo lường** hoặc cấu hình connection provider thích hợp. Thay vì hardcode rằng một metric có tên chắc chắn `reactor.netty.http.client.*` trên mọi phiên bản:

1. Xác minh Spring Boot, Spring Cloud Gateway, Reactor Netty và Micrometer versions.
2. Kiểm tra metrics được expose trong **Actuator/Prometheus của môi trường test**.
3. Đọc tài liệu meter names/tags theo release.
4. Xác nhận **đơn vị** (s/ms), histogram buckets và có tag route ID/destination nào.
5. Gọi một request **cold** và một request **reused**, xem metric/connection counter thay đổi tương ứng.

Không bật toàn bộ Actuator endpoints lên public internet chỉ để đọc metrics. Dùng endpoint management được bảo vệ, role/scope riêng và network isolation.

### Các metric có cardinality cao cần tránh

Một số nhãn hữu ích: `routeId` hữu hạn, `upstreamService` được quản lý, `outcome`, `protocol`, `connectionReused` nếu exporter hỗ trợ. **Không đưa raw URL, query string, user ID, IP client hoặc JWT vào metric labels**, vì có thể làm nổ series và rò dữ liệu.

Với đích do load balancer chọn, hãy phân biệt `serviceId` ổn định với `instanceAddress` có thể thay đổi/chứa thông tin nhạy cảm. Chỉ xuất chi tiết địa chỉ ở telemetry hạn chế quyền khi thực sự cần.

### Distributed tracing nên phân rã theo một inbound request

~~~text
Trace R-42:
  [Inbound Gateway HTTP: total 100 ms]
    [Security + route/filter: 6 ms]
    [Service discovery selection: 4 ms]
    [Outbound attempt #1: 76 ms]
      [Pool acquire: 2 ms]
      [DNS: 8 ms]
      [TCP connect: 20 ms]
      [TLS handshake: 30 ms]
      [HTTP request/first byte/transfer: 16 ms]
    [Response/other: 14 ms]
~~~

Các con số **minh họa** và spans con chỉ xuất hiện nếu hệ thống có instrumentation thực sự. HTTP span mặc định có thể chỉ bao trùm toàn outbound call, **không tự có span con DNS/TLS**. Muốn gắn kết cụ thể, cần transport hooks hoặc tracing/metrics của HTTP client phù hợp.

Một connection có thể phục vụ **nhiều inbound requests**; DNS/connect/TLS của connection được mở từ trước có thể xảy ra **ngoài lifetime** request đang đo. Nếu phân bổ toàn chi phí tạo connection cho mỗi request tái sử dụng thì kết quả sẽ sai. Nên theo dõi **per-connection events** bên cạnh **per-request latency**.

## 13. Curl: đọc đúng DNS, TCP, TLS, TTFB và total time

`curl --write-out` là cách dễ bắt đầu với **client → Gateway/ingress**. Nó cung cấp các mốc thời gian tính từ lúc curl bắt đầu transfer, chứ không phải mọi số đều là thời lượng của một phase riêng.

### Một request HTTPS từ môi trường test có quyền

~~~bash
curl --http1.1 --noproxy '*' \
  --connect-timeout 2 --max-time 10 \
  --silent --show-error --output /dev/null \
  --write-out 'dns_end=%{time_namelookup} tcp_end=%{time_connect} tls_end=%{time_appconnect} pretransfer=%{time_pretransfer} first_byte=%{time_starttransfer} total=%{time_total} new_connections=%{num_connects} remote_ip=%{remote_ip}\n' \
  'https://gateway.lab.example.test/api/catalog/items/42'
~~~

**Đây là lệnh mẫu, không phải phép đo đã chạy.** Chỉ gọi domain lab hoặc URL được cho phép. `--noproxy '*'` cố ý không dùng HTTP proxy qua biến môi trường; nếu mục tiêu là **đo qua proxy thật**, phải bỏ tùy chọn đó và ghi rõ proxy topology. Trên Windows PowerShell 5.1, dùng `curl.exe` thay vì alias `curl` (thường trỏ tới `Invoke-WebRequest`).

### Cách diễn giải write-out

| Trường `curl` | Ý nghĩa khái niệm |
| --- | --- |
| `time_namelookup` | Mốc hoàn thành phân giải tên ban đầu |
| `time_connect` | Mốc hoàn thành kết nối tới remote peer ban đầu |
| `time_appconnect` | Mốc hoàn thành TLS/SSL hoặc handshake ứng dụng tương ứng khi có |
| `time_pretransfer` | Mốc sẵn sàng bắt đầu chuyển dữ liệu ở giao thức ứng dụng |
| `time_starttransfer` | Mốc nhận byte đầu response; gồm chờ server, proxy, backend |
| `time_total` | Toàn bộ transfer tới lúc hoàn thành theo curl |
| `num_connects` | Số kết nối mới được curl tạo cho transfer |
| `remote_ip` | Địa chỉ remote được dùng ở phía client curl nhìn thấy |

Trong một HTTPS request **mới, không redirect, không HTTP proxy phức tạp**, có thể ước lượng:

\[
\begin{aligned}
T_{\text{DNS}} &\approx t_{\text{namelookup}}\\
T_{\text{TCP}} &\approx t_{\text{connect}}-t_{\text{namelookup}}\\
T_{\text{TLS}} &\approx t_{\text{appconnect}}-t_{\text{connect}}\\
T_{\text{first-byte-after-ready}} &\approx t_{\text{starttransfer}}-t_{\text{pretransfer}}\\
T_{\text{body-after-first-byte}} &\approx t_{\text{total}}-t_{\text{starttransfer}}
\end{aligned}
\]

Đây là **ước lượng theo mốc cộng dồn**; các pha có thể phụ thuộc protocol, proxy, reuse và timing definitions của curl. Với HTTP không TLS, `time_appconnect` có thể bằng 0 và phép trừ để lấy TLS không có ý nghĩa. Với connection reuse, số lần tạo connection có thể bằng 0 và các mốc handshake không đại diện cho cold path. Không gọi `time_starttransfer - time_pretransfer` là “thời gian backend” thuần: nó chứa cả Gateway routing, network, queue và upstream.

### Hai requests trong cùng một curl process để quan sát reuse

~~~bash
curl --http1.1 --silent --show-error --output /dev/null \
  --write-out 'first new=%{num_connects} dns=%{time_namelookup} tcp=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' \
  'https://gateway.lab.example.test/api/catalog/items/42' \
  --next \
  --http1.1 --silent --show-error --output /dev/null \
  --write-out 'second new=%{num_connects} dns=%{time_namelookup} tcp=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' \
  'https://gateway.lab.example.test/api/catalog/items/42'
~~~

Hai transfers dùng chung một curl process nên **có cơ hội** tái sử dụng connection, nếu server/client cho phép keep-alive và connection còn hợp lệ. **Không khẳng định** request thứ hai chắc chắn sẽ reuse: `num_connects` và kết quả thực mới xác nhận. Chạy `curl` thành **hai process độc lập** không mô phỏng tốt connection reuse của một HTTP client pool tồn tại lâu dài.

### Curl không đo được toàn bộ outbound Gateway bằng một lệnh

Nếu curl từ laptop gọi `https://gateway.lab.example.test`, `time_appconnect` thông thường đo TLS tới **public ingress/Gateway peer curl kết nối**, **không đo** TLS giữa Gateway và Catalog. Nếu curl thấy total = 150 ms, cần metrics/tracing ở Gateway outbound để xác định bao nhiêu phần do backend DNS/TCP/TLS. Không suy luận từ một con số end-to-end.

## 14. Các phép đo phụ trợ: DNS, TLS cert, network path

### DNS answers

~~~bash
dig +noall +answer gateway.lab.example.test A
dig +noall +answer gateway.lab.example.test AAAA
~~~

Để tách phần phân giải public DNS khỏi connect/TLS trong **lab có kiểm soát**, `curl --resolve` có thể ánh xạ hostname tới IP test mà vẫn giữ hostname cho HTTP Host/SNI:

~~~bash
curl --resolve gateway.lab.example.test:443:127.0.0.1 \
  --silent --show-error --output /dev/null \
  --write-out 'dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' \
  'https://gateway.lab.example.test/api/catalog/items/42'
~~~

Lệnh này **chỉ có ý nghĩa khi máy local thực sự có HTTPS listener ở 127.0.0.1:443** với chứng chỉ hợp lệ cho `gateway.lab.example.test`; nó **không** khuyên bypass TLS verification. `--resolve` bỏ đường DNS phân giải hostname của curl, **không làm đổi DNS resolver/cache nội bộ của Gateway**, và cũng có thể đổi network path nếu IP khác đích thực. Vì vậy so sánh `--resolve` với bình thường là một **thí nghiệm có điều kiện**, không phải bằng chứng tuyệt đối DNS production gây latency.

### Xác minh TLS peer mà không tắt bảo mật

~~~bash
openssl s_client \
  -connect gateway.lab.example.test:443 \
  -servername gateway.lab.example.test \
  -verify_return_error -brief
~~~

`openssl s_client` giúp kiểm tra protocol/certificate/trust handshake ở **peer đang kết nối**; nó không tự tạo benchmark throughput tin cậy, không thay application HTTP client và không đo TLS Gateway → backend nếu chạy từ laptop tới public ingress. Trong môi trường yêu cầu client certificate, phải cấu hình test mTLS identity hợp lệ theo cách được phê duyệt; không gửi private keys vào logs/chat.

### Network RTT và TCP retransmission

Những công cụ như `ping`, `mtr`, `traceroute` hoặc TCP socket telemetry có thể giúp xác định network path, RTT và packet loss nếu tổ chức cho phép. Tuy nhiên:

- ICMP RTT không hoàn toàn là TCP/TLS handshake time.
- Một network policy có thể chặn ICMP mà HTTPS vẫn hoạt động.
- Tool chạy ngoài Pod khác network namespace/egress policy có thể có đường đi khác Gateway.
- Packet capture có thể chứa dữ liệu nhạy cảm; chỉ chạy theo quyền và chính sách thu thập được phê duyệt.

**Luôn gắn nguồn phép đo** (client laptop, Pod Gateway, sidecar, backend) và protocol/port, không đặt tất cả timings vào một cột “network latency”.

## 15. Kịch bản thí nghiệm có đối chứng: cold vs warm connection

Một benchmark hữu ích phải giữ cố định những gì không muốn đo và thay đổi có chủ đích **chỉ một biến số**.

### Các nhóm cần so sánh

| Nhóm | DNS cache | Outbound connection | Mục đích |
| --- | --- | --- | --- |
| A — Cold path | Có thể cache miss | Tạo connection mới | Chi phí mở kết nối đầy đủ trong môi trường đó |
| B — Warm pool | Có thể cache hit | Tái sử dụng connection | Độ trễ steady-state |
| C — New connection, DNS cached | Cache hit/địa chỉ đã biết | Tạo connection mới | Ước lượng TCP + TLS mà không nhầm nhiều DNS queries |
| D — New connection, TLS resumed nếu có | DNS hợp lệ | Connection mới với TLS resumption | Đánh giá riêng lợi ích resumption |

**Khó khăn:** DNS cache hit/miss và TLS resumption **không thể đảm bảo bằng việc gọi lại URL một lần**. Phải có hooks/counters chứng minh mỗi nhóm thật sự có những conditions đó; bằng không, gọi đó là **observed first-request vs steady-state** chứ không gắn nhãn cold DNS/TLS chắc chắn.

### Quy trình cơ bản trong lab

1. Khóa **Spring Boot/Gateway/Reactor Netty versions**, Java runtime, hostname, HTTP version và topology.
2. Dựng Catalog stub có response **nhỏ, cố định, không DB**; bật HTTPS bằng test CA nếu cần đo TLS.
3. Đặt Gateway và stub trên những hosts/containers/networks có thông số đã biết; ghi vùng/zone.
4. Cấu hình route/static URI và theo dõi pool active/idle/pending, new connection count, DNS queries và TLS handshakes.
5. Chạy **warm-up** rồi ghi phân phối latency steady-state; không chỉ lấy một request nhanh nhất.
6. Tạo nhóm cold path theo một cơ chế test **có kiểm soát**: HTTP client mới/pool mới, hoặc một fixture Gateway instance riêng. Không kill toàn bộ Gateway connections đang phục vụ production.
7. Lặp lại mỗi nhóm đủ lần, thu số requests, errors, p50/p95/p99, average, min/max và thời gian thử.
8. Đọc **backend request journal** để biết có retry/redirect thêm attempts không.
9. Đối chiếu `curl` client→Gateway với metrics Gateway outbound, không cộng/đổi tên phases.
10. Kết luận theo **mức cải thiện có ý nghĩa và rủi ro cấu hình**, không chỉ theo p50.

### Điều kiện phải cố định

- Cùng endpoint/method/headers/body, response payload size.
- Cùng TLS protocol/ALPN khi đang so sánh một biến khác.
- Cùng số replicas/CPU resources, GC pressure và mức độ concurrent traffic.
- Cùng service discovery route/instance selection hoặc ghi instance được chọn.
- Không chạy retry hoặc redirects ngầm nếu không phải đối tượng nghiên cứu.
- Không để HTTP cache/CDN/browser cache khiến backend HITS bằng 0 mà tưởng backend siêu nhanh.
- Không mix phép đo qua public ingress với phép đo direct Gateway rồi coi chúng cùng baseline.

### Cảnh báo về stress testing

Không dùng load test quá tải thật chỉ để phân tích TLS. Nếu tạo hàng nghìn connections mới/giây, bạn có thể gây TLS CPU spikes, exhaust file descriptors và làm ảnh hưởng các dịch vụ liên quan. Mọi test tải cần **môi trường cô lập, ngưỡng dừng, thời lượng giới hạn và người vận hành phê duyệt**.

## 16. Spring Cloud Gateway Server WebFlux: quan sát bằng GlobalFilter và HTTP client

Trong Gateway Server WebFlux, luồng request đi qua các thành phần như route predicates, GlobalFilter/GatewayFilter chain và outbound routing filter. Khi cần đánh giá TLS/DNS/connect, bạn phải phân biệt:

- **Gateway route elapsed time:** mức thời gian từ lúc filter được subscribe đến khi downstream reactive chain hoàn tất/lỗi/hủy theo vị trí filter.
- **Outbound HTTP attempt time:** thời gian từ khi HTTP client bắt đầu xử lý request đến khi nhận response/error; có thể gồm pool, DNS, TCP, TLS.
- **Transport phase timings:** thời gian pool acquire, DNS, TCP connect và TLS handshake do HTTP client/resolver ghi lại.
- **Backend server processing time:** thời gian service xử lý sau khi request tới nó; không có DNS/connect của Gateway.

### 16.1. GlobalFilter đo tổng thời gian route, không giả làm TLS timer

Ví dụ instrumentation nhỏ, dùng **Spring Cloud Gateway Server WebFlux** và Micrometer:

~~~java
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public final class RouteElapsedGlobalFilter implements GlobalFilter, Ordered {

    private final MeterRegistry meters;

    public RouteElapsedGlobalFilter(MeterRegistry meters) {
        this.meters = meters;
    }

    @Override
    public int getOrder() {
        return -1000;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain
    ) {
        return Mono.defer(() -> {
            long startedNanos = System.nanoTime();

            return chain.filter(exchange)
                    .doFinally(signal -> {
                        Route route = exchange.getAttribute(
                                ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR);
                        String routeId = route == null
                                ? "unknown" : route.getId();

                        meters.timer(
                                "demo.gateway.route.elapsed",
                                "route", routeId,
                                "terminal", signal.name()
                        ).record(
                                System.nanoTime() - startedNanos,
                                TimeUnit.NANOSECONDS);
                    });
        });
    }
}
~~~

**Cách hiểu đúng:**

1. `Mono.defer` lấy thời điểm bắt đầu **khi có subscription**, thay vì ghi thời gian lúc chỉ lắp ráp Publisher.
2. `doFinally` quan sát terminal signal: complete, error hoặc cancel; cancellation có thể đến từ client/ngữ cảnh subscription.
3. Route ID đến từ route do ứng dụng quản lý; metric dùng nhãn hữu hạn, **không dùng raw path/JWT làm tag**.
4. Filter chỉ chạy cho request đi vào **Gateway filter chain** thích hợp; 401/403 bị chặn bởi Spring Security hoặc 404 không match route có thể không đi qua filter.
5. Timer đo **downstream lifecycle tại vị trí filter**. Với retry/resubscription/filter ordering, cách đếm có thể thay đổi; không mặc định đúng một timer sample là một TCP attempt.
6. Timer **không phân biệt DNS, TCP và TLS**. Muốn kết luận TLS chậm cần thêm metric/trace ở HTTP client transport.
7. Dù reactive chain hoàn tất, điều đó không tự bảo đảm client cuối cùng đã nhận đủ body bytes, đặc biệt với stream/cancel/transport error.

Ví dụ cần **Micrometer MeterRegistry** được cấu hình trong ứng dụng; mã đo lường ở đây không phải lệnh chứng minh đã chạy. Với lưu lượng lớn, kiểm tra chi phí tạo/tra meter và cardinality; dùng metric framework built-in thay vì chồng nhiều timer nếu đã có measurements tương đương.

### 16.2. Transport instrumentation cho Reactor Netty

Để quan sát outbound connection ở Reactor Netty, cần khai thác những khả năng mà **Reactor Netty version thật đang cung cấp**:

| Điểm đo | Kỳ vọng khi tạo connection mới | Kỳ vọng khi reuse |
| --- | --- | --- |
| Pool acquire | Có thể phải chờ | Có thể lấy idle/available connection nhanh |
| Address resolution | Chỉ khi chưa có địa chỉ hợp lệ theo resolver/cache | Có thể không thực hiện lại |
| TCP connect | Có một connect attempt | Không có TCP connect mới |
| TLS handshake | Có handshake nếu HTTPS mới | Không có handshake mới trên cùng connection |
| HTTP request/response | Luôn xảy ra với request được gửi | Luôn xảy ra |

Trong Netty, cần phân biệt event **channel connected**, **TLS handshake completed** và **HTTP response received**. Thời gian giữa hai callbacks không tự là TLS duration nếu chúng bao gồm thêm queueing/handlers; sử dụng **TLS handshake event và timestamp tại SSL handler** khi version/instrumentation cung cấp, tránh suy đoán từ log “connection established”.

**Không tự bật Netty wiretap ở production** để đo thời gian: wiretap có thể ghi raw HTTP headers/body, kể cả Authorization, Cookie hoặc dữ liệu cá nhân, cùng overhead đáng kể. Ưu tiên metrics/observability hooks an toàn, chỉ sử dụng packet capture/wire logging trong lab kiểm soát dữ liệu.

### 16.3. Cấu hình connect/response timeout theo version

Một số dòng Spring Cloud Gateway Server WebFlux hỗ trợ những thuộc tính có dạng:

~~~yaml
# Minh họa cho dòng Gateway Server WebFlux hỗ trợ namespace này.
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 1000
            response-timeout: 5s
~~~

Ở những dòng cũ, chúng có thể nằm dưới `spring.cloud.gateway.httpclient.*`. Kiểm tra **configuration metadata tương ứng với dependency thật**, unit của `connect-timeout` (thường milliseconds ở các dòng phổ biến) và cách `response-timeout` nhận `Duration`. Không cho rằng một property được viết vào YAML đã được bind hoặc đang chi phối client thực.

Kể cả khi những values được nhận:

- Connect timeout **không giới hạn** pool acquire và DNS resolver trong mọi implementation.
- Response timeout **không đồng nghĩa** overall request timeout gồm TLS, retry và body transfer.
- TLS handshake timeout và pool lifetime có thể cần cấu hình bằng các API/properties khác.
- Route-specific timeouts/filter overrides có thể thay đổi chính sách ở một route.

Hãy viết negative tests chứng minh connect refused, DNS timeout, TLS failure, pool exhausted và backend slow response được xử lý **đúng deadline tổng**.

## 17. Gateway Server Web MVC: đo tại Servlet container và outbound HTTP client riêng

Với **Gateway Server Web MVC**, ứng dụng dựa trên **Servlet container/Spring MVC/WebMvc.fn**. HTTP client outbound không mặc định là Reactor Netty client của Gateway Server WebFlux; vì thế:

- **Servlet request threads/busy threads** và inbound connector pool có thể ảnh hưởng tổng latency.
- HTTP client/request factory outbound của Gateway MVC có **connection pooling, DNS resolver, TLS/HTTP stack và metrics riêng**.
- Một `GlobalFilter` reactive hoặc `Mono.defer` của WebFlux **không áp trực tiếp** lên Server MVC.
- Cấu hình `spring.cloud.gateway.server.webflux.httpclient.*` không tự điều khiển MVC HTTP client.

### Đo đúng hai phía khi dùng Servlet

| Phía | Điều cần đo | Cách tiếp cận |
| --- | --- | --- |
| Inbound client → Gateway MVC | HTTP connect, TLS, request-to-response total | JDK HttpClient/curl tới Servlet port thực |
| Trong Servlet | HandlerMapping, SecurityFilterChain, filters, busy threads | Spring MVC/Servlet metrics và tracing |
| Outbound Gateway MVC → Catalog | Pool wait, DNS, TCP/TLS, response read | Instrument **đúng HTTP client/request factory đang dùng** |
| Catalog backend | Server handling time/status và accept backlog | Backend instrumentation |

`MockMvc` rất tốt cho test route/security nhưng **không mở inbound TCP socket**, nên không đo DNS/TLS client→Gateway thực. Với HTTP integration test, dùng `@SpringBootTest(RANDOM_PORT)` và HTTP client kết nối cổng thật, cùng backend stub HTTP/HTTPS để kiểm chứng outbound.

### Servlet threads chậm có thể làm bạn đổ lỗi nhầm TLS

Nếu backend trả nhanh nhưng Servlet worker threads bị giữ bởi các calls blocking, total latency có thể tăng vì **chờ request processing**, trong khi TLS handshake thật không đổi. Đo active/busy threads, request queue và client outbound pool cùng lúc. Java virtual threads (nếu được Boot/JDK hỗ trợ) có thể giảm chi phí chờ blocking I/O, nhưng **không làm network RTT, TCP pool hay backend capacity biến mất**.

### Proxy Exchange là một con đường khác

Một ứng dụng **Proxy Exchange MVC** dùng `ProxyExchange<T>` trong controller cũng phải đo hai hops, nhưng nó không tự kế thừa Gateway Server WebFlux filter/client properties. Nếu team dùng nhiều biến thể Gateway, ghi tên **server/proxyexchange**, stack **MVC/WebFlux**, HTTP client implementation và version ngay trong báo cáo để tránh so sánh sai.

## 18. Java HTTP client: đo tổng thời gian warm-up/reuse đúng mục tiêu

Để kiểm chứng user-facing latency tới Gateway thật, có thể dùng **JDK HttpClient** trên Java 17+ trong test. Mục đích là **đo tổng HTTP request duration** và quan sát lợi ích tiềm năng của client reuse; **không** khẳng định chỉ từ đoạn code này ta tách được DNS/TCP/TLS.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class GatewayWarmConnectionProbe {

    public static void main(String[] args) throws Exception {
        // Chỉ dùng endpoint lab có quyền, trả body nhỏ và cố định.
        URI endpoint = URI.create(
                "https://gateway.lab.example.test/api/catalog/health");

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(2))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        List<Long> samplesMs = new ArrayList<>();

        for (int i = 0; i < 20; i++) {
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            long started = System.nanoTime();
            HttpResponse<Void> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.discarding());
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "Unexpected status: " + response.statusCode());
            }

            // Mẫu đầu giúp thấy hiệu ứng khởi đầu; không mặc định DNS cold.
            samplesMs.add(elapsedMs);
            System.out.println("sample=" + i + " totalMs=" + elapsedMs);
        }

        Collections.sort(samplesMs);
        System.out.println("minMs=" + samplesMs.get(0)
                + " maxMs=" + samplesMs.get(samplesMs.size() - 1));
    }
}
~~~

**Giới hạn của ví dụ:**

1. Một `HttpClient` dùng chung **cho phép** connection reuse, nhưng mỗi lần có reuse thực hay không còn tùy keep-alive, server, network, connection state và client internals.
2. `System.nanoTime()` đo toàn bộ `send()` tới khi response body được xử lý bởi `BodyHandlers.discarding()`, không tách TLS/DNS.
3. `min/max` không thay thế p50/p95/p99. Với chỉ 20 samples, **không đưa ra kết luận thống kê mạnh về p99**.
4. Request đầu **không chắc DNS cold** vì OS cache, DNS resolver hay TLS session cache của HTTP client.
5. JDK HttpClient dùng truststore theo môi trường test: HTTPS listener phải có cert hợp lệ, **không tắt verification**.
6. Nếu cần test proxy qua ingress, giữ đúng route và proxy settings; `HttpClient` có thể chọn HTTP/1.1 theo yêu cầu trong code dù production client dùng HTTP/2.
7. Không chạy chương trình để benchmark một host không được phép; backend/Catalog thực có thể bị ảnh hưởng bởi 20 calls hoặc nhiều threads nếu nhân rộng.

Để kết luận **tại sao** sample đầu chậm hơn, ghép với số liệu của server/Netty HTTP client: new connections, pool waits, DNS queries, TCP/TLS handshakes và backend response times. Đừng gọi mọi chênh lệch “TLS warmup”.

## 19. Bursts, retries và nhiều upstream làm tăng số lần bắt tay

Một inbound request có thể tạo **nhiều outbound attempts**, nhất là khi Gateway áp Retry hoặc một controller fan-out sang nhiều services.

### Đếm attempts trước khi đổ lỗi cho handshake

~~~mermaid
flowchart TD
    I["1 inbound request"] --> A["Outbound attempt 1 to Catalog A"]
    A --> X{"Response / exception?"}
    X -->|Lỗi retry được phép| B["Outbound attempt 2 to Catalog B"]
    X -->|Thành công| C["Response"]
    B --> C
    A -. "New TCP/TLS nếu pool không có" .-> N["Connection events"]
    B -. "Có thể thêm new TCP/TLS" .-> N
~~~

Nếu mỗi retry chọn một instance khác, pool có thể chưa có connection phù hợp và phải tạo **DNS/TCP/TLS** mới. Vì thế một lỗi backend có thể đồng thời tăng:

- Số outbound attempts trên một user request.
- Số connections và TLS handshakes/s.
- Pool acquire latency và queue.
- CPU TLS của cả Gateway và backend.
- p99 client-visible latency, dù từng backend attempt ngắn.

**Đừng dùng retries vô hạn để làm “tỷ lệ 200” đẹp**. Giới hạn attempts, backoff, jitter và overall deadline; chỉ retry methods/conditions an toàn theo idempotency contract. POST thanh toán/đặt hàng có thể đã được backend commit dù socket trả lỗi, nên không tự động gửi lại khi thiếu idempotency key + deduplication.

### Circuit breaker và bulkhead

- **Circuit breaker OPEN** có thể chặn outbound call; số TCP/TLS handshakes có thể giảm vì không thử kết nối.
- **Bulkhead/concurrency limit** giảm số calls đồng thời tới backend, bảo vệ pool/threads nhưng có thể tăng rejected requests.
- **Rate limiting** có thể chặn inbound trước khi Gateway route tạo HTTP calls, nhưng không giải quyết connect/TLS chậm của calls vẫn được phép.

Khi đo, đặt **count inbound requests, count outbound attempts, new connections, handshake count và fallback count cạnh nhau**. Nếu client status 200 nhờ fallback mà Catalog không nhận request, không ghi đó là “TLS latency đã cải thiện”.

### Cross-region routing và service placement

Một service ở vùng khác có RTT cao hơn dẫn tới TCP connect và TLS handshake mới đắt hơn. Tuy nhiên chuyển backend về cùng zone/region có thể có chi phí vận hành và yêu cầu resilience khác. Đánh giá **latency, availability, data residency, failover và security boundaries**, không tối ưu chỉ một RTT.

## 20. Chẩn đoán theo triệu chứng: DNS, TCP, TLS hay pool?

Một cùng biểu hiện “p99 tăng” có nhiều nguyên nhân. Nên phân loại theo **phase nào có bằng chứng chậm hoặc lỗi**.

| Triệu chứng | Giả thuyết hợp lý | Phép đo/kiểm tra ưu tiên |
| --- | --- | --- |
| Cold requests chậm, warm requests nhanh | DNS/TCP/TLS setup hoặc cold application/JIT | New/reused connection count, per-phase timing, JIT warm-up |
| DNS lookup p95 tăng | Resolver chậm, cache miss, CNAME/AAAA, timeout | Resolver query/timeout, DNS cache events |
| DNS NXDOMAIN sau deploy | Service name/namespace sai, negative cache | DNS answer tại đúng namespace và process behavior |
| DNS trả IP mới nhưng traffic vẫn tới IP cũ | Pool giữ connections cũ | Remote address của active connections, idle/lifetime policy |
| Pool pending requests cao | Connection/stream capacity thiếu hoặc upstream quá chậm | Pool active/idle/pending, acquire duration |
| Connect timeout tăng, DNS nhanh | Firewall drop, SYN loss, route mạng lỗi | TCP connect attempts, retransmission, network policy |
| Connect refused ngay | Đích không nghe port, readiness/target sai | Listener, LB target/ServiceInstance |
| TLS handshake time tăng nhưng TCP ổn | TLS CPU, certificate verification, mTLS load | TLS handshake histogram, CPU và cert validation errors |
| TLS cert/hostname mismatch | SNI/hostname/SAN/CA sai | TLS validation error, endpoint host và truststore |
| TLS/connection churn tăng sau tuning | Idle/lifetime quá ngắn, backend đóng keep-alive | New connections/s, resets, idle eviction |
| Handshake time cao chỉ ở cross-region | RTT/network distance | So sánh cùng-region và cross-region trong lab |
| HTTP/2 một số streams chờ lâu | MAX_CONCURRENT_STREAMS, connection saturation | Stream active/pending, negotiated protocol |
| DNS nhanh nhưng `lb://` route chậm | Discovery/LoadBalancer selection | Registry cache/instance selection duration |
| TTFB tăng mà connect/TLS không đổi | Backend queue/processing, Gateway filters | Backend duration, HTTP client response wait |
| HTTP status 503 tăng khi TLS lỗi | Gateway tạo 503/fallback, không phải backend trả | Upstream counter=0, TLS exception/final status |
| TCP reset sau idle | Stale pooled connection hoặc LB idle expiry | Idle age, reset type, keep-alive mismatch |
| Retry làm p99 tăng khi backend lỗi | Nhiều attempts + repeated handshakes | Inbound/outbound attempts, retry budget |
| Chỉ một Gateway replica chậm | DNS cache/pool/config/CPU khác nhau | Per-instance metrics và deployment revision |
| Curl từ laptop nhanh, user ở vùng xa chậm | Public DNS/RTT/ingress khác | Client-region RUM, edge metrics |
| MockMvc nhanh, HTTP client thật chậm | Inbound transport hoặc outbound network path | RANDOM_PORT HTTP test, TLS/pool counters |
| Sau bật TLS 1.3 latency không đổi | Đang reuse connection, backend là bottleneck | New handshake rate vs overall requests |
| TLS handshake nhanh nhưng request timeout | Response/read timeout hoặc streaming dài | TTFB/body transfer, backend queue |

### Runbook theo thứ tự ít gây xáo trộn

1. **Chốt phạm vi lỗi.** Route nào? Một backend hay nhiều backend? Tất cả Gateway replicas hay chỉ một vùng/zone?
2. **Đo client-facing latency.** Lấy p50/p95/p99 và error rates theo route, status, traffic level. Ghi rõ URL đi qua ingress hay direct.
3. **Tách requests có upstream call khỏi fallback/denied calls.** 401/403/rate-limit/circuit breaker không luôn đi tới backend.
4. **Đo outbound attempts.** Đếm inbound requests, retries, redirects, instance selection.
5. **Đo pool acquire.** Nếu pool wait cao, không đổ lỗi ngay cho DNS/TLS.
6. **Đo new/reused connections.** Nếu reuse cao và handshake count thấp, TLS setup khó là nguyên nhân chính cho mọi request.
7. **Đo DNS/connect/TLS theo connection attempt.** Ghi host/instance, protocol, IP family và outcome một cách an toàn.
8. **Đối chiếu backend.** Backend có nhận request? Server handling time/accept queue thế nào?
9. **So sánh cold/warm trong lab.** Giữ cố định HTTP version, response size, retries và network path.
10. **Chỉ thay một knob sau khi có bằng chứng**, benchmark lại và có rollback khi error rate tăng hoặc network identity bị ảnh hưởng.

Trong điều tra, một câu như “p99 TLS 90 ms” phải kèm **nó đo từ lúc nào đến lúc nào, trên những connection mới nào, ở hop nào, đơn vị và số mẫu bao nhiêu**. Một percentile TLS của 100 handshakes không thể trực tiếp đại diện cho p99 của 1 triệu HTTP requests tái sử dụng những connections đó.

## 21. Tối ưu theo nguyên nhân, không theo mẹo cấu hình

### 21.1. Nếu DNS thật sự chậm

- Kiểm tra độ ổn định của resolver và quyền mạng từ Gateway tới DNS.
- Xác định các tầng cache: JVM, Netty, sidecar, recursive resolver.
- Giảm CNAME/hostname chains không cần thiết khi kiến trúc cho phép.
- Xem lại TTL và negative caching theo yêu cầu IP rotation/failover.
- Không để mỗi request tự tạo HTTP client mới khiến cache/reuse kém.
- Nếu dựa vào service discovery, phân tách thời gian cập nhật registry khỏi DNS.

**Không đặt DNS TTL vô hạn.** Nếu backend IP thay đổi do rollout/scale, stale DNS cache có thể tiếp tục gửi traffic sai đích hoặc làm mất khả năng failover.

### 21.2. Nếu TCP connect chậm

- Ưu tiên network placement gần backend khi phù hợp availability/data policy.
- Kiểm tra firewall/NAT/proxy và packet loss/retransmissions.
- Dùng connection pooling/keep-alive, hạn chế connection churn.
- Đo IPv4/IPv6 selection và fallback behavior thay vì tắt IPv6 mù quáng.
- Xem backend accept backlog, load balancer health và capacity.
- Cấu hình connect timeout phù hợp, có overall deadline.

**Không tăng connect timeout lên vô hạn** để tránh lỗi; việc đó có thể giữ requests chờ vào network path hỏng và tích tụ queues.

### 21.3. Nếu TLS handshake chậm

- Xác minh TLS 1.3 được hai đầu hỗ trợ và **thực sự negotiated**; không chỉ đặt một config flag.
- Tận dụng keep-alive/connection pooling trước khi tối ưu từng full handshake.
- Xem khả năng TLS session resumption **khi phải reconnect**, có đo số resumed/full handshakes.
- Kiểm tra CPU TLS và concurrent handshakes ở Gateway/backend/sidecar.
- Tối ưu chain/certificate management theo policy, không bỏ hostname/CA verification.
- Giữ mTLS khi là yêu cầu danh tính service; xử lý lỗi rotation/SNI/truststore đúng cách.
- Đánh giá proxy/mesh TLS termination và RTT từng chặng.

**Không xem bật TLS 1.3/HTTP2 là giải pháp tự động** nếu bottleneck thực tế là pool wait, backend DB hay cross-zone traffic. Cần benchmark nhóm đối chứng và test compatibility.

### 21.4. Nếu pool wait hoặc resets chiếm ưu thế

- Đo max/active/idle/pending, idle ages và new connections/s.
- Tăng capacity từng bước **chỉ khi backend có khả năng nhận thêm connections/streams**.
- Đặt pending queue và acquire timeout để hạn chế tail latency vô biên.
- Điều chỉnh max idle/lifetime với backend/LB idle settings; xác minh stale socket resets giảm.
- Xem HTTP/2 stream limits thay vì chỉ đếm TCP sockets.
- Kiểm tra breaker/bulkhead và rate limiter để ngăn overload trên downstream.

**Không tăng mọi giới hạn đồng thời**, vì không thể biết knob nào có tác dụng và dễ tạo overload/connection storms.

### 21.5. Nếu tất cả handshake nhanh nhưng total chậm

Trọng tâm có thể ở:

- Spring Security/JWT validation hoặc remote introspection.
- Gateway route predicates, custom filters blocking/non-blocking.
- Service discovery, rate limiter store hoặc external authorization call.
- Backend processing, DB/cache, queue, response body serialization.
- Response transfer và client đọc chậm.

Thêm TLS tuning trong trường hợp này không sửa gốc vấn đề. Một **trace đúng các spans** thường giá trị hơn nhiều lần bật/tắt TLS.

## 22. Một ví dụ ra quyết định bằng số liệu giả định

Đội vận hành báo cáo:

> “Gateway Catalog p95 tăng từ 60 ms lên 140 ms sau một đợt triển khai; có vẻ HTTPS quá chậm.”

Giả sử hệ thống quan sát được những **số liệu tổng hợp minh họa**:

| Chỉ số | Trước triển khai | Sau triển khai |
| --- | ---: | ---: |
| Inbound requests/giây | 300 | 300 |
| New outbound connections/giây | 15 | 180 |
| TLS handshakes/giây | 15 | 180 |
| Pool idle eviction/giây | 10 | 160 |
| Backend processing p95 | 25 ms | 26 ms |
| Gateway total p95 | 60 ms | 140 ms |
| HTTP 5xx rate | 0,2% | 1,3% |

Các con số trên **không đến từ một hệ thống thật**; đây là bài phân tích.

### Giả thuyết đầu tiên

Tần suất outbound connections/TLS handshakes tăng mạnh dù traffic không đổi. Backend processing ổn định; pool idle evictions tăng. Có thể **max idle time bị giảm quá thấp**, một instance/client mới được tạo theo request, hoặc upstream/LB đã đổi idle timeout.

### Những gì vẫn chưa được chứng minh

- TLS handshakes tăng **có thể là hệ quả**, không nhất thiết là gốc; ví dụ backend chủ động reset connections hoặc Gateway upgrade làm thay đổi pool.
- p95 Gateway tăng **không được giải thích định lượng chỉ bằng số handshakes/giây**. Cần TLS handshake duration cùng request/connection attempts và pool waits.
- 5xx có thể do reset, stale connections, TLS errors hoặc backend; phải phân loại `exceptionType` và response provenance.

### Thiết kế phép thử

1. So sánh connection provider/pool/idle settings trước/sau deploy.
2. Chạy cùng tải 300 req/s trên lab, **cố định Catalog stub, HTTP version và TLS profile**.
3. Đo new connections/s, TLS handshake duration, pool pending/acquire duration và p95 Gateway.
4. Thay duy nhất maxIdleTime hoặc nguyên nhân churn đã được xác minh; benchmark lại.
5. Kiểm tra 5xx không tăng và backend accept/TLS CPU trong giới hạn.
6. Test DNS rotation và backend/LB idle timeout trước khi đưa cấu hình mới lên production.

Nếu sau tuning p95 giảm nhưng stale connection errors tăng khi backend đổi IP, **không coi đó là thành công**. Một cấu hình tốt phải cân bằng latency với failover/availability và certificate/identity correctness.

## 23. Bài thực hành: đo độ trễ TLS/DNS/connect cho một route Gateway

**Bối cảnh:** Một Gateway có route `GET /api/catalog/**` tới Catalog bằng HTTPS. Mục tiêu là phân rã latency ở client→Gateway và Gateway→Catalog, đo cold/warm traffic, thử thay đổi pooling trong lab và kết luận bằng dữ liệu.

### Phần A — Chuẩn bị topology có kiểm soát

1. Chọn **Gateway Server WebFlux** hoặc **Gateway Server Web MVC**; ghi chính xác starter/BOM/runtime. Không trộn API hai biến thể.
2. Dựng **Catalog HTTP/HTTPS stub** trong môi trường lab, trả JSON nhỏ và ổn định (ví dụ `{"id":"42"}`); log số requests và TLS connections/handshakes ở mức an toàn nếu stub hỗ trợ.
3. Với HTTPS, dùng chứng chỉ test có SAN đúng hostname, CA/truststore riêng và SNI đúng.
4. Cấu hình route static URI HTTPS hoặc `lb://catalog-service` với test discovery đã biết; **không chọn backend URL từ header/query client**.
5. Đảm bảo client có thể gọi Gateway qua một endpoint test; nếu có ingress, ghi rõ ingress terminate TLS ở đâu.
6. Bật metrics đã được phê duyệt cho HTTP server/client, DNS resolver, TLS và pool nếu khả dụng.

### Phần B — Baseline lạnh/ấm

1. Gọi một request từ curl vào public/test Gateway; ghi `time_namelookup`, `time_connect`, `time_appconnect`, `time_starttransfer` và `time_total`.
2. Gửi nhiều requests tuần tự **trong một curl process/HTTP client** để quan sát connection reuse ở **client → Gateway**; không suy từ một request.
3. Ở Gateway outbound, lấy request/connection metrics để biết Gateway→Catalog có mở **kết nối mới** hay reuse.
4. Tạo một nhóm cold outbound trong lab bằng provider/instance mới hoặc một controlled reset, **không reset production pools**.
5. So sánh backend HITS với inbound request count; nếu có retries, ghi từng attempt.
6. Thu tối thiểu số lượng mẫu đủ để nhận ra xu hướng, sau đó tăng mẫu khi cần phân tích p99; không suy p99 đáng tin chỉ từ 5–10 samples.

### Phần C — Thử từng yếu tố, không đổi cùng lúc

| Thí nghiệm | Điều kiện điều chỉnh | Quan sát kỳ vọng |
| --- | --- | --- |
| DNS cache hit/miss | Controlled DNS test records/cache | Tỷ lệ resolver queries và DNS duration thay đổi |
| TCP cold | Không có pooled connection, cùng target | Tạo TCP connect attempt mới |
| TLS cold/resumed | Cùng TLS version/cert nhưng điều kiện session khác | Full/resumed handshake count/duration |
| Pooled reuse | Kết nối còn mở, cùng upstream | New connect/TLS count giảm cho traffic steady-state |
| Short idle timeout | Pool đóng idle sớm | Connection churn và handshakes/s tăng |
| Backend/LB stale idle | Backend đóng connection trước pool | Reset/retry sau idle tăng |
| Pending pool saturation | Load bounded vượt capacity test | Pool acquire time và pending queue tăng |
| HTTP/2 vs HTTP/1.1 | Chỉ khi client/server hỗ trợ và ALPN xác nhận | TCP connection count/streams thay đổi |
| Cross-zone RTT | Network lab path khác có phê duyệt | TCP/TLS setup tăng theo network RTT |
| TLS cert invalid | HTTPS stub cert sai hoặc CA không tin | Handshake fail closed; không trả 200 |
| DNS NXDOMAIN/no instance | Stub DNS/discovery trả lỗi | Phân loại DNS error khác no-instance |

### Phần D — Fault injection an toàn

Trong test network/namespace riêng:

1. Mô phỏng DNS lookup chậm bằng test DNS proxy có giới hạn; đo DNS timeout behavior.
2. Mô phỏng TCP connect refused bằng stub không có listener trên port đã dành riêng.
3. Mô phỏng response delay bằng backend stub; chứng minh **response timeout khác TLS timeout**.
4. Dùng certificate có SAN sai trong lab; bảo đảm client từ chối và không ghi secret ra log.
5. Tạo một backend connection idle timeout ngắn để kiểm tra stale pooled connection.
6. Khi thử retry, xác minh mỗi inbound request có **số upstream attempts hữu hạn**, không làm storm.
7. Dừng fault injection và xác nhận pool/DNS cache/registry trở lại trạng thái ổn định trước bài tiếp theo.

**Không chạy các lệnh thay đổi firewall, route mạng, DNS toàn máy hoặc TLS production** để tạo sự cố. Dùng tool test proxy/network namespace có quyền, teardown rõ và ngưỡng dừng, tránh ảnh hưởng các workloads khác.

### Phần E — Điền bảng kết quả

| Chỉ số | Baseline | Cold | Warm | Sau thay đổi |
| --- | --- | --- | --- | --- |
| Gateway inbound requests | ... | ... | ... | ... |
| Outbound attempts | ... | ... | ... | ... |
| New connections | ... | ... | ... | ... |
| Reused connections | ... | ... | ... | ... |
| DNS resolver requests/cache hits | ... | ... | ... | ... |
| Pool acquire p95 | ... | ... | ... | ... |
| TCP connect p95 | ... | ... | ... | ... |
| TLS handshake p95 | ... | ... | ... | ... |
| Backend processing p95 | ... | ... | ... | ... |
| Gateway route p95 | ... | ... | ... | ... |
| Client end-to-end p95/p99 | ... | ... | ... | ... |
| HTTP 5xx, timeout, TLS errors | ... | ... | ... | ... |

Chỉ điền ô khi số đo được **instrumentation tương ứng hỗ trợ**. Nếu không đo được TLS handshake riêng, ghi **N/A — chưa có instrument** thay vì tính nó bằng cách trừ đại các p95 khác nhau.

### Phần F — Phân tích và quyết định

Hãy trả lời:

1. Cold request chậm hơn warm bao nhiêu, và **new connection counter có chứng minh không**?
2. DNS lookup thực sự chiếm bao nhiêu trên những attempts có DNS, chứ không phải trung bình mọi request?
3. TLS 1.3 đã negotiated chưa? Có full vs resumed handshakes hay không?
4. Pool acquire có chiếm thời gian lớn hơn TLS handshake dưới tải không?
5. Nếu thay idle timeout, số stale resets và khả năng DNS failover có thay đổi?
6. Gateway p95/p99 có cải thiện thật ở cùng workload, và 5xx/error rates có giữ trong SLO không?
7. Tối ưu có ảnh hưởng mTLS, certificate validation, proxy trust hoặc token forwarding không?
8. Với retry/circuit breaker, inbound requests và outbound attempts có khớp với policy không?

**Tiêu chí đạt:** Bạn có **một biểu đồ/bảng so sánh có nguồn đo**, phân biệt client-facing với outbound DNS/TCP/TLS, chứng minh connection reuse bằng counters, giữ TLS verification và có kết luận tối ưu kèm rollback. Không đủ tiêu chí nếu chỉ chạy curl một lần rồi nói “TLS mất 40 ms, nên tắt TLS”.

## 24. Checklist production và chiến lược triển khai thay đổi

Một thay đổi nhỏ về connection pool hoặc DNS cache có thể làm Gateway nhanh hơn trong benchmark nhưng gây **sự cố failover, TLS identity mismatch hoặc overload backend**. Vì vậy tối ưu network không được xem là một thay đổi không cần review.

### Trước triển khai

~~~text
[ ] Xác định biến thể Gateway: Server WebFlux hay Server Web MVC.
[ ] Khóa Spring Boot, Spring Cloud BOM, HTTP client/Netty versions.
[ ] Vẽ đúng các hop: browser/ingress/Gateway/upstream/sidecar.
[ ] Xác định hop terminate TLS và hop dùng mTLS.
[ ] Có baseline p50/p95/p99 và request/error rates theo route.
[ ] Có số đo pool acquire, new/reused connections và handshake count.
[ ] DNS resolution khác với service discovery selection được đo tách biệt.
[ ] Config HTTP client/route timeout thực sự được bind trên phiên bản chạy.
[ ] Không đưa Host/Authorization/Cookie/raw URI thành metric labels.
[ ] Có tests kết nối mới, reuse, DNS rotation và stale idle connection.
[ ] Có negative tests TLS chain/hostname/SNI và mTLS (nếu dùng).
[ ] Có timeout tổng/retry budget và không retry thao tác thiếu idempotency.
[ ] Có kế hoạch canary, SLO gate, rollback và người chịu trách nhiệm.
~~~

### Trong canary

Đo cùng lúc:

| Nhóm | Dấu hiệu cải thiện | Dấu hiệu phải dừng/rollback |
| --- | --- | --- |
| Client latency | p95/p99 giảm ở cùng traffic mix | p99 tăng hoặc lỗi client tăng |
| Outbound pool | Acquire p95 giảm, pending queue ổn | Pending/rejected tăng nhanh |
| DNS | Cache hit phù hợp, resolver timeouts giảm | IP stale/NXDOMAIN kéo dài, failover chậm |
| TCP | Connect failures/retransmits giảm | New connections/s tăng đột biến |
| TLS | Handshake time/errors giảm | Cert mismatch, trust errors, mTLS auth failures |
| Backend | Throughput/CPU/accept queue trong giới hạn | 429/503, CPU TLS tăng hoặc overload |
| Retry | Attempts/request không tăng ngoài policy | Retry storm hoặc side effects trùng |
| Security | TLS verification/mTLS/trust vẫn đúng | Phải tắt verification mới làm test pass |

**Chỉ so sánh khi điều kiện traffic tương đương**. Nếu sau deploy tỷ lệ cache hit hoặc response size thay đổi, p95 tổng có thể giảm vì business workload khác, không phải do TCP/TLS tuning. Ghi route, upstream, instance, environment và thời điểm cùng deployment revision.

### Khi có sự cố sau thay đổi

1. Tạm ngăn rollout mở rộng khi error rate/SLO xấu đi.
2. Kiểm tra connection churn, pool saturation, DNS stale records và TLS handshake errors theo replica.
3. Xác định source of truth của config: ứng dụng, Config Server, Helm/manifest, JVM flags hay sidecar.
4. Rollback **đúng config gây ra thay đổi**, không tắt TLS validation hoặc giảm security controls.
5. Xác minh Gateway nhận cấu hình cũ; với pool/DNS cache, **đang có connections cũ** có thể cần thời gian để hết lifecycle.
6. Kiểm tra failover, backend health, mTLS rotation và client error rate đã phục hồi.
7. Ghi lại nguyên nhân bằng số liệu phases, không kết luận qua một vài log lines.

### Khi không nên tối ưu thêm

Nếu p95 Gateway 45 ms, DNS/TCP/TLS chỉ chiếm một phần rất nhỏ của những request có kết nối mới và **new connection rate thấp**, việc tiếp tục chỉnh TLS handshake nhiều khi không đáng rủi ro. Hãy ưu tiên backend latency, rate limiting/fallback, caching phù hợp hoặc response transfer nếu đó mới là bottleneck.

## 25. Những hiểu lầm cần tránh khi đọc số liệu

| Nhận định sai | Điều đúng |
| --- | --- |
| “Curl `time_appconnect` chính là TLS Gateway → backend.” | Nó thường đo TLS của **curl → peer** như CDN/ingress, không nhìn thấy outbound Gateway. |
| “`time_connect` chỉ chứa TCP connect.” | Đó là **mốc cộng dồn** từ đầu transfer, cần trừ `time_namelookup` để ước lượng phần TCP trong kịch bản phù hợp. |
| “`time_starttransfer` bằng thời gian backend xử lý.” | Nó bao gồm network/Gateway/queue/processing tới byte đầu. |
| “DNS TTL hết hạn thì mỗi HTTP request phải hỏi DNS.” | Pooled connection và resolver cache có thể tránh query trên nhiều requests. |
| “`lb://` chỉ đơn giản là DNS lookup.” | Nó cần chọn ServiceInstance từ discovery/LoadBalancer; DNS có thể là bước riêng sau đó. |
| “Thay JVM DNS TTL chắc chắn đổi Netty cache TTL.” | Reactor Netty có thể dùng resolver/cache riêng. |
| “Gateway route tồn tại nghĩa là backend đã kết nối.” | Route match không đảm bảo service instance, DNS, TCP/TLS hay backend healthy. |
| “HTTP 200 chứng minh DNS/TLS nhanh.” | Có thể là pooled connection, cache, fallback hoặc backend response nhanh. |
| “Kết nối pooled luôn tránh mọi loại delay.” | Có thể chờ pool acquire, stream capacity hoặc gặp stale connection. |
| “Mỗi connection mới chắc chắn thực hiện full TLS handshake.” | Có thể có session resumption, nhưng vẫn là connection mới và thường cần TCP. |
| “TLS 1.3 tự làm mọi request thành 0-RTT.” | Full handshake vẫn cần RTT; early data tùy hỗ trợ và có replay risk. |
| “Có HTTP/2 thì chỉ còn một connection và không thể tắc.” | Stream limits, flow control và congestion vẫn gây chờ. |
| “Tăng maxConnections luôn làm latency giảm.” | Có thể overload backend, TLS CPU và file descriptors. |
| “Tăng connect timeout giải quyết pool acquire timeout.” | Hai giai đoạn khác nhau; cần đo queue/pool. |
| “Một kết quả `dig` từ máy operator là cache DNS JVM.” | Nó có thể dùng resolver/cơ chế cache khác Gateway process. |
| “Chỉ cần so p95 DNS + p95 TCP + p95 TLS là ra p95 request.” | Không được cộng percentiles của phân phối khác nhau như vậy. |
| “MockMvc đo được TLS handshake từ client.” | MockMvc không tạo inbound TCP/TLS connection thật. |
| “Mọi property `spring.cloud.gateway.httpclient.*` dùng được cho MVC.” | WebFlux và MVC có HTTP client/config khác; namespace còn tùy version. |
| “Connection reset sau idle chứng minh DNS hỏng.” | Có thể do backend/LB idle timeout hoặc stale pooled socket. |
| “Giảm TLS latency bằng cách tắt verify cert là tối ưu.” | Đó là **hạ cấp bảo mật**, không được coi là giải pháp. |
| “Chạy nhiều requests để đo sẽ không ảnh hưởng backend.” | Cold connection storm/load test có thể tiêu tốn TCP/TLS resources. |
| “HTTP request rate bằng số TLS handshakes.” | Nhiều requests có thể reuse một connection; retry có thể tạo thêm attempts. |
| “TLS cert rotation không liên quan pool.” | Existing TLS connections và new connections có thể thấy identity/keys khác; cần rollout/refresh policy. |
| “p50 nhanh chứng minh người dùng không bị ảnh hưởng.” | p99, tail retries/timeouts và errors mới phơi bày nhiều vấn đề cold path. |

## 26. Tổng kết

- Một Gateway vừa là **HTTP server** của client vừa là **HTTP client** của upstream. Phải biết **hop nào đang đo**, nơi nào terminate TLS, và request có đi qua ingress/mesh hay không.
- **DNS resolution, service discovery, TCP connect, TLS handshake, pool acquire, backend processing và response transfer** là những pha khác nhau. Chúng có thể không xuất hiện trên request tái sử dụng connection, hoặc xuất hiện nhiều lần vì retry/fan-out.
- **DNS cache/TTL và pooled connections** làm thay đổi số lần lookup. Không nhầm `lb://` ServiceInstance selection với DNS A/AAAA resolution, không dùng `dig` trên một máy khác để khẳng định cache của JVM/Netty.
- **TLS 1.3** thường giảm full-handshake RTT so với TLS 1.2, nhưng **không làm TCP setup biến mất**; session resumption khác connection reuse, và 0-RTT có replay risk.
- **Connection pooling và HTTP/2 multiplexing** giảm chi phí tạo kết nối trong nhiều workload, nhưng cần giới hạn pending queue, idle/lifetime và stream capacity để tránh stale sockets, saturation hoặc reconnect storm.
- **Curl timings là các mốc cộng dồn**: `time_connect`, `time_appconnect` và `time_starttransfer` không thể gọi là riêng TCP, TLS và backend time nếu không biết điểm bắt đầu/kết thúc cùng topology.
- **Gateway WebFlux** cần instrument Reactor Netty/HTTP client transport để đo DNS/TCP/TLS outbound; `GlobalFilter` chỉ đo lifecycle xử lý route. **Gateway Web MVC** cần instrument outbound HTTP client của Servlet stack, không lấy metric/config Netty làm mặc định.
- **Đánh giá cold/warm có đối chứng** bằng request/connection counters, metrics/traces, benchmark có warm-up và đủ số mẫu; không cộng p95 DNS + p95 TCP + p95 TLS thành p95 tổng.
- **Tối ưu an toàn** giữ nguyên TLS certificate/hostname verification, mTLS và timeout/retry budget; không dùng trust-all, vô hạn connections hoặc DNS cache forever để che lỗi.
- Khi triển khai, so sánh p95/p99, errors, new connections, pool waits, resolver behavior và backend load **trên cùng traffic mix**; có canary và rollback theo SLO.

Mục tiêu của đánh giá hiệu năng **SPRING_CLOUD_GATEWAY** không chỉ là tìm một số “TLS mất bao nhiêu milliseconds”, mà là **biết một request đã tạo kết nối nào, chi phí của mỗi pha nằm ở đâu, tại sao cold và warm khác nhau, và thay đổi nào cải thiện trải nghiệm thực tế mà vẫn giữ bảo mật và khả năng phục hồi của microservices**.

### Tài liệu nên đối chiếu với phiên bản đang dùng

- **Spring Cloud Gateway Reference:** https://docs.spring.io/spring-cloud-gateway/reference/
- **Reactor Netty Reference:** https://projectreactor.io/docs/netty/release/reference/
- **Spring Boot Actuator Metrics:** https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- **curl --write-out documentation:** https://curl.se/docs/manpage.html
- **TLS 1.3, RFC 8446:** https://www.rfc-editor.org/rfc/rfc8446
- **HTTP Semantics, RFC 9110:** https://www.rfc-editor.org/rfc/rfc9110

Đối chiếu **Spring Boot, Spring Cloud Gateway, Reactor Netty, HTTP client và TLS runtime thực tế** trước khi chép bất cứ property, meter name hay đoạn Java nào; một phép đo đúng phải đi kèm đúng phiên bản, đúng network path và đúng nguồn dữ liệu.
