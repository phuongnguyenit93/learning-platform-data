# Eureka bật self-preservation hoặc liên tục lỗi gia hạn

Khi Eureka Server bật self-preservation, dashboard có thể hiển thị cảnh báo số heartbeat nhận được thấp hơn ngưỡng dự kiến. Trong trạng thái này, Eureka hạn chế eviction instance hết lease để tránh xóa nhầm hàng loạt service khi mạng bị gián đoạn hoặc nhiều client tạm thời không gửi được heartbeat. Cơ chế bảo vệ này giúp tránh registry mất dữ liệu diện rộng, nhưng có thể khiến instance đã chết vẫn xuất hiện trong danh sách.

Một tình huống khác là Eureka Client liên tục lỗi renewal. Nguyên nhân có thể nằm ở URL registry, DNS, network, TLS, authentication, server quá tải, JVM pause hoặc cấu hình lease không đồng nhất. Self-preservation thường là phản ứng của server trước lượng renewal giảm; bản thân nó không nhất thiết là nguyên nhân khiến client không gia hạn được.

Bài viết này hướng dẫn đọc cảnh báo, tính ngưỡng renewal, phân biệt lỗi ở client và server, kiểm tra eviction cùng cache consumer, rồi xử lý theo thứ tự an toàn. Mục tiêu là khôi phục heartbeat và trạng thái registry chính xác mà không vô tình xóa instance khỏe.

## 1. Self-preservation bảo vệ điều gì?

Mỗi Eureka Client đã đăng ký thường gửi heartbeat/renewal định kỳ để báo rằng instance vẫn còn hoạt động. Eureka Server theo dõi số renewal nhận được trong một khoảng thời gian và so sánh với số lượng dự kiến.

Nếu số renewal thực tế giảm thấp hơn ngưỡng, server có thể bật self-preservation. Khi đó, server hạn chế xóa các instance chỉ vì lease hết hạn. Lý do là một đợt mất kết nối giữa client và server có thể làm heartbeat biến mất dù nhiều provider vẫn đang phục vụ request bình thường.

~~~mermaid
flowchart TD
    A["Eureka Client gửi renewal định kỳ"] --> B["Eureka Server đếm renewal"]
    B --> C{"Renewal thực tế có dưới ngưỡng?"}
    C -->|"Không"| D["Eviction theo lease và chu kỳ server"]
    C -->|"Có"| E["Self-preservation được kích hoạt"]
    E --> F["Hạn chế eviction hàng loạt"]
    F --> G["Instance chết có thể còn trong registry"]
    D --> H["Registry phản ánh trạng thái instance"]
    G --> H
~~~

Self-preservation không có nghĩa tất cả request đăng ký hoặc truy vấn đều bị dừng. Client vẫn có thể đăng ký, renew hoặc fetch nếu kết nối hoạt động; điểm quan trọng là server tránh eviction hàng loạt khi tín hiệu heartbeat giảm bất thường.

### Vì sao cần cơ chế này?

Giả sử có 100 instance và một sự cố mạng khiến 40 instance không thể gửi heartbeat trong vài phút. Nếu server xóa tất cả instance hết lease ngay lập tức, registry có thể loại cả những provider vẫn khỏe nhưng chỉ tạm thời mất đường tới Eureka. Khi mạng phục hồi, các client phải đăng ký lại, consumer có thể trải qua biến động lớn và tạo thêm tải.

Self-preservation ưu tiên giữ registration trong lúc chưa đủ bằng chứng rằng instance thực sự đã chết. Đổi lại, registry có thể giữ lại địa chỉ stale cho tới khi heartbeat trở lại hoặc trạng thái được xử lý bằng quy trình vận hành phù hợp.

## 2. Hiểu ngưỡng renewal

Có thể ước lượng số renewal kỳ vọng mỗi phút từ số instance đang đăng ký và chu kỳ renewal:

\[
R_{expected} \approx N \times \frac{60}{T_r}
\]

Trong đó:

- N là số instance được kỳ vọng gửi heartbeat.
- T_r là chu kỳ renewal tính bằng giây.
- R_expected là số renewal kỳ vọng trong một phút.

Ngưỡng kích hoạt self-preservation được ước lượng:

\[
R_{threshold} \approx R_{expected} \times P
\]

P là `renewal-percent-threshold`. Giá trị thường gặp mặc định là 0,85, nhưng cần kiểm tra cấu hình thực tế và phiên bản Eureka đang chạy.

Ví dụ có 100 instance, renewal mỗi 30 giây và threshold 0,85:

\[
R_{expected} = 100 \times \frac{60}{30} = 200
\]

\[
R_{threshold} \approx 200 \times 0.85 = 170
\]

Nếu server chỉ nhận khoảng 140 renewal trong phút quan sát, số thực tế thấp hơn ngưỡng dự kiến và self-preservation có thể được kích hoạt.

Đây là mô hình ước lượng để hiểu xu hướng, không thay thế thuật toán nội bộ của Eureka Server. Server còn có chu kỳ cập nhật threshold, trạng thái registry, thời điểm khởi động và các yếu tố cấu hình khác. Hãy đối chiếu dashboard, log và metric thực tế trước khi kết luận.

### Các chu kỳ liên quan

| Thuộc tính | Phía cấu hình | Vai trò |
|---|---|---|
| `lease-renewal-interval-in-seconds` | Eureka Client instance | Khoảng thời gian client gửi renewal |
| `lease-expiration-duration-in-seconds` | Eureka Client instance | Thời gian lease trước khi instance có thể bị xem là hết hạn |
| `expected-client-renewal-interval-seconds` | Eureka Server | Khoảng renewal server dùng để ước lượng |
| `renewal-percent-threshold` | Eureka Server | Tỷ lệ renewal tối thiểu so với kỳ vọng |
| `renewal-threshold-update-interval-ms` | Eureka Server | Chu kỳ cập nhật ngưỡng renewal |
| `eviction-interval-timer-in-ms` | Eureka Server | Chu kỳ chạy eviction task |
| `registry-fetch-interval-seconds` | Eureka Client | Chu kỳ consumer fetch registry |

Các giá trị phổ biến thường gặp là client renewal 30 giây, lease expiration 90 giây, eviction task 60 giây và renewal threshold 0,85. Đây không phải cam kết cho mọi release hoặc mọi ứng dụng; giá trị hiệu lực có thể bị override bằng YAML, environment variable, command-line argument hoặc cấu hình server.

## 3. Nhận biết self-preservation đang hoạt động

Trên Eureka dashboard, tìm cảnh báo liên quan tới renewal threshold hoặc self-preservation. Nội dung thường cho biết server nhận được ít renewal hơn số lượng kỳ vọng và có thể đang bảo vệ registry khỏi eviction.

Khi thấy cảnh báo:

1. Ghi lại thời điểm bắt đầu và thời gian cảnh báo kéo dài.
2. Ghi số instance hiện có trong registry.
3. Ghi renewal thực tế và threshold nếu dashboard hoặc metric cung cấp.
4. Kiểm tra log Eureka Server quanh thời điểm chuyển trạng thái.
5. So sánh số client đang chạy thực tế với số instance server đang kỳ vọng.
6. Kiểm tra nhiều client có lỗi cùng lúc hay chỉ một nhóm cụ thể.

Self-preservation kéo dài không tự chứng minh server bị lỗi. Nó cho biết server đang nhận ít heartbeat hơn mức được xem là bình thường. Cần xác định heartbeat bị mất vì client chết thật, client không thể kết nối hay server không xử lý kịp.

### Phân biệt ba trạng thái

| Quan sát | Ý nghĩa có thể có | Hành động đầu tiên |
|---|---|---|
| Self-preservation bật, provider vẫn khỏe | Đường heartbeat có thể bị gián đoạn hoặc threshold không còn phù hợp | Kiểm tra renewal transport và số instance thực tế |
| Self-preservation bật, nhiều provider đã chết | Registry có thể đang giữ registration stale | Đối chiếu từng instance với process/health thực tế |
| Self-preservation tắt nhưng instance không bị xóa | Lease chưa hết, eviction chưa tới chu kỳ, hoặc bản ghi được làm mới | Kiểm tra lease, eviction log và renewal |

## 4. Chẩn đoán renewal lỗi từ Eureka Client

Bắt đầu từ log của chính client. Cần xác định client có đăng ký thành công trước đó hay không và request renewal đang đi tới server nào.

### Kiểm tra cấu hình client

Ví dụ:

~~~yaml
spring:
  application:
    name: inventory-service

eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka.internal:8761/eureka/
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
    prefer-ip-address: true
~~~

Kiểm tra các điểm sau:

- `register-with-eureka` có bật ở provider cần đăng ký không.
- `defaultZone` có đúng scheme, hostname, port và context path không.
- DNS của client có phân giải được hostname Eureka không.
- Client có route và firewall rule tới server port không.
- Instance có bị cấu hình nhầm thành consumer-only không.
- Các profile hoặc environment variable có ghi đè URL và lease interval không.
- Client có đăng ký được lần đầu nhưng renewal về sau lại thất bại không.

Tên property và default có thể thay đổi theo phiên bản. Kiểm tra cấu hình đã bind và log khởi động, không chỉ đọc file YAML trong repository.

### Phân loại lỗi theo dấu hiệu

| Dấu hiệu trong client log | Nguyên nhân có thể | Kiểm tra tiếp |
|---|---|---|
| Connection refused | Eureka Server không listen, sai port hoặc service/network bị dừng | Kiểm tra server listener, port và route |
| Connect/read timeout | Network chậm, firewall drop, server quá tải | Đo latency, packet loss và server thread/CPU |
| UnknownHostException | DNS sai hoặc DNS chưa cập nhật | Kiểm tra phân giải hostname từ container/Pod |
| 401 hoặc 403 | Authentication/authorization từ chối request | Kiểm tra credential, proxy và security rules |
| 404 | Sai context path hoặc URL endpoint | Kiểm tra `/eureka/` và reverse proxy rewrite |
| SSLHandshakeException | Truststore, SAN, certificate hoặc TLS policy sai | Kiểm tra certificate chain và hostname |
| 5xx từ server/proxy | Server, peer hoặc gateway lỗi | Đối chiếu server log và proxy log |
| Client không có log renewal | Client chưa register, scheduler không chạy hoặc log level không hiển thị | Kiểm tra lifecycle, bean và log configuration |

Không suy luận từ một log duy nhất. Đối chiếu request ID hoặc timestamp giữa client, proxy và Eureka Server để biết request đã rời client, tới proxy và được server xử lý hay chưa.

### Kiểm tra từ đúng môi trường chạy client

Thử DNS và kết nối TCP từ chính container hoặc Pod của provider:

~~~bash
getent hosts eureka.internal
curl -v --connect-timeout 3 http://eureka.internal:8761/eureka/apps
~~~

Nếu registry dùng HTTPS hoặc authentication, dùng URL và credential của môi trường test phù hợp. Không in token hoặc password vào terminal log được chia sẻ.

Lệnh curl chỉ kiểm tra khả năng truy cập endpoint; nó không mô phỏng toàn bộ renewal protocol. Kết quả HTTP 200 ở `/eureka/apps` chưa chứng minh endpoint renew của client hoạt động đúng.

## 5. Chẩn đoán phía Eureka Server

Nếu nhiều client cùng lỗi renewal, hãy kiểm tra server trước khi sửa từng client.

Các điểm cần kiểm tra:

- Server process có ổn định không; có restart hoặc OutOfMemoryError không.
- CPU, heap, garbage collection pause và request queue có tăng bất thường không.
- HTTP connection pool hoặc thread pool có bão hòa không.
- Log có cho thấy renewal request tới server hay bị từ chối không.
- Server có nhận traffic từ proxy/load balancer đúng route không.
- Các Eureka peer có kết nối và replicate registry được không.
- Dashboard có hiển thị số renewal thực tế, expected threshold và self-preservation state không.

### Kiểm tra registry qua REST API

Ví dụ đọc danh sách ứng dụng:

~~~bash
curl -H "Accept: application/json" \
  http://eureka.internal:8761/eureka/apps
~~~

Đọc một application cụ thể:

~~~bash
curl -H "Accept: application/json" \
  http://eureka.internal:8761/eureka/apps/INVENTORY-SERVICE
~~~

Các endpoint có thể cần authentication và context path khác nếu server được triển khai sau proxy. Dùng đúng URL của môi trường và không đưa credential thật vào tài liệu hoặc log.

Đối chiếu `instanceId`, hostname, IP, port, status và metadata. Một bản ghi UP trong registry không chứng minh process đang sống; cần gọi health endpoint hoặc kiểm tra process từ host/container tương ứng.

### Kiểm tra nhiều Eureka peer

Trong cụm Eureka peer-to-peer, một server có thể nhận renewal trong khi peer khác chưa đồng bộ đúng. Kiểm tra:

- Peer URL có trỏ tới đúng server và có thể phân giải từ từng node không.
- Network giữa các peer có cho phép replication traffic không.
- Peer có đang trả 4xx/5xx hoặc timeout không.
- Dashboard/REST API của các peer có chênh lệch số instance hoặc status không.
- Reverse proxy hoặc load balancer có chuyển request tới các node theo cách gây sai lệch topology không.

Không chỉ kiểm tra một dashboard nếu production có nhiều Eureka Server. Hãy truy vấn từng peer và so sánh cùng một application/instance ID.

## 6. Kiểm tra lease và eviction

Renewal interval, lease expiration và eviction interval cùng ảnh hưởng tới thời gian một instance có thể còn tồn tại sau khi ngừng gửi heartbeat.

Ví dụ client:

~~~yaml
eureka:
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
~~~

Ví dụ server:

~~~yaml
eureka:
  server:
    enable-self-preservation: true
    renewal-percent-threshold: 0.85
    expected-client-renewal-interval-seconds: 30
    eviction-interval-timer-in-ms: 60000
~~~

Các property server minh họa tên cấu hình thường dùng trong Spring Cloud Netflix Eureka Server. Hãy xác minh property reference của release đang chạy; một số giá trị có thể do server tính hoặc cập nhật theo chu kỳ.

Khi client dừng graceful, client thường có cơ hội deregister. Khi process crash hoặc máy mất điện, deregistration không xảy ra; server phải dựa vào lease/eviction. Nếu self-preservation đang bảo vệ registry, eviction có thể bị hạn chế dù lease đã hết.

Không giảm `lease-expiration-duration-in-seconds` xuống quá thấp chỉ để xóa bản ghi nhanh. Network jitter, GC pause hoặc server quá tải có thể khiến client khỏe bị xem là mất heartbeat. Đặt lease dựa trên renewal interval, độ trễ thực tế và mức gián đoạn cần chịu đựng.

## 7. Phân biệt self-preservation với stale cache ở consumer

Có ít nhất hai lớp có thể khiến consumer tiếp tục nhìn thấy instance cũ:

1. Eureka Server vẫn giữ registration vì lease chưa hết hoặc self-preservation đang hạn chế eviction.
2. Eureka Client đã fetch snapshot cũ và chưa tải registry mới.

Ngoài ra, server có thể dùng response cache để phục vụ endpoint registry. Do đó, thời điểm một bản ghi thay đổi trong server chưa chắc trùng với thời điểm mọi consumer nhìn thấy thay đổi.

Ví dụ cấu hình fetch:

~~~yaml
eureka:
  client:
    registry-fetch-interval-seconds: 30
~~~

Khi điều tra:

1. Xác nhận instance còn tồn tại trong REST API/dashboard của từng Eureka peer.
2. Xác nhận consumer cụ thể đang nhìn thấy bao nhiêu instance qua DiscoveryClient.
3. Kiểm tra registry fetch interval và log fetch.
4. Kiểm tra cache LoadBalancer nếu ứng dụng có cấu hình cache riêng.
5. Gửi request kiểm chứng và ghi instance thực tế được chọn.

Nếu server đã xóa bản ghi nhưng consumer vẫn chọn nó, tập trung vào fetch/cache propagation. Nếu server vẫn giữ bản ghi, tập trung vào renewal, lease, self-preservation và eviction.

## 8. Nguyên nhân phổ biến khiến renewal giảm

### Network hoặc DNS

- Firewall/security group chặn client tới Eureka.
- DNS trả địa chỉ cũ sau khi server thay đổi.
- Proxy/load balancer reset kết nối hoặc rewrite sai path.
- Packet loss, latency hoặc route bất ổn khiến renewal timeout.

### Client hoặc JVM

- CPU starvation làm scheduler gửi heartbeat trễ.
- GC pause kéo dài hơn khoảng chịu đựng của lease.
- Container bị throttling hoặc node quá tải.
- Ứng dụng restart liên tục, crash-loop hoặc chưa hoàn tất registration.
- Cấu hình URL/lease bị khác nhau giữa các profile.

### Server hoặc cụm Eureka

- Server quá tải, GC pause hoặc thread pool cạn.
- Peer replication bị lỗi.
- Reverse proxy hoặc TLS termination cấu hình không đồng nhất.
- Cấu hình expected renewal interval không khớp với client.
- Số instance thay đổi mạnh sau scale/deploy nhưng threshold chưa kịp cập nhật.

### Thay đổi topology và threshold

Khi scale down hoặc triển khai rolling, số client gửi renewal thay đổi. Nếu threshold còn dựa trên số lượng trước đó trong một khoảng cập nhật, server có thể tạm thời đánh giá lượng renewal là thấp. Ngược lại, cấu hình expected interval không khớp với client có thể khiến ngưỡng dự kiến sai.

Kiểm tra thời điểm deploy/scale, số instance thực tế, số registration trong registry và chu kỳ cập nhật threshold trước khi chỉnh `renewal-percent-threshold`.

## 9. Runbook xử lý theo thứ tự

### Bước 1: Xác định phạm vi

- Một client hay nhiều client cùng lỗi?
- Một Eureka Server hay toàn bộ peer?
- Renewal lỗi liên tục hay chỉ có một khoảng ngắn?
- Provider thực tế còn healthy hay đã chết?
- Self-preservation bắt đầu đúng lúc có network/deploy event nào không?

Nếu chỉ một client lỗi, ưu tiên cấu hình và đường mạng của client đó. Nếu nhiều client ở nhiều service cùng lỗi, kiểm tra server, proxy, DNS và network dùng chung.

### Bước 2: Đối chiếu số liệu

Ghi lại:

- Số instance thực tế đang chạy.
- Số registration trong Eureka.
- Renewal thực tế trong phút gần nhất.
- Expected renewal threshold.
- Trạng thái self-preservation.
- Tỷ lệ renewal request thành công/thất bại.
- CPU, heap, GC pause và request latency của server.
- Thời điểm deploy, scale hoặc network incident.

Không thay đổi cấu hình trước khi lưu baseline; nếu không, sẽ khó xác định thay đổi nào làm hệ thống tốt hơn hoặc xấu hơn.

### Bước 3: Khôi phục luồng renewal

Ưu tiên xử lý nguyên nhân gốc:

1. Sửa DNS, route, firewall hoặc proxy nếu client không tới được server.
2. Sửa URL/context path nếu request đi sai endpoint.
3. Sửa truststore, certificate hoặc authentication nếu handshake/request bị từ chối.
4. Giảm tải server hoặc khôi phục peer nếu server không xử lý kịp.
5. Điều chỉnh scheduler/resource của client nếu JVM hoặc container bị starvation.
6. Đồng nhất expected renewal interval và client renewal interval theo cấu hình có chủ đích.

Sau khi sửa, quan sát renewal tăng trở lại và self-preservation rời trạng thái bảo vệ theo hành vi của phiên bản server.

### Bước 4: Xử lý instance stale đã được xác minh

Trước khi xóa bản ghi, đối chiếu từng instance với process, container/Pod, health endpoint và chủ sở hữu service. Chỉ xử lý bản ghi đã xác nhận không còn workload hợp lệ.

Ưu tiên:

- Khôi phục provider còn sống để nó tiếp tục renewal.
- Cho phép instance dừng graceful deregister khi có thể.
- Dùng quy trình vận hành/admin được phê duyệt để loại bản ghi stale đã xác minh.
- Theo dõi các peer và consumer sau khi thay đổi.

Eureka có REST API hỗ trợ thao tác instance, nhưng endpoint DELETE có thể gây ảnh hưởng nếu dùng sai application hoặc instance ID. Chỉ thực hiện khi đã xác định chính xác bản ghi và có quyền quản trị phù hợp; không chạy lệnh xóa hàng loạt để làm dashboard hết cảnh báo.

### Bước 5: Xác minh consumer đã hội tụ

- REST API của các peer phản ánh danh sách mong đợi.
- Consumer fetch được registry mới.
- DiscoveryClient trả danh sách instance phù hợp.
- LoadBalancer không còn chọn instance stale.
- Request kiểm chứng thành công qua provider khỏe.
- Renewal và error rate trở về baseline ổn định trong một khoảng quan sát đủ dài.

## 10. Cấu hình self-preservation: khi nào nên thay đổi?

Thông thường nên giữ self-preservation bật trong production. Nó là lớp bảo vệ khi registry không thể phân biệt một đợt mất heartbeat do network partition với việc nhiều provider chết thật.

Chỉ cân nhắc thay đổi threshold hoặc tắt self-preservation khi:

- Đã đo và hiểu rõ renewal pattern thực tế.
- Đã xác định số instance kỳ vọng và chu kỳ renewal chính xác.
- Có health check hoặc cơ chế giám sát độc lập đủ tin cậy.
- Chấp nhận rõ ràng trade-off giữa xóa stale instance nhanh và nguy cơ xóa nhầm instance khỏe.
- Thay đổi được thử trong staging và có kế hoạch rollback.

Ví dụ cấu hình:

~~~yaml
eureka:
  server:
    enable-self-preservation: true
    renewal-percent-threshold: 0.85
    renewal-threshold-update-interval-ms: 900000
~~~

Không sao chép nguyên các giá trị ví dụ nếu topology và release khác. Hãy xác minh giá trị mặc định/hiệu lực bằng configuration metadata, log startup hoặc endpoint cấu hình được bảo vệ.

### Vì sao không nên tắt self-preservation để chữa cảnh báo?

Nếu nguyên nhân là network partition, tắt self-preservation có thể khiến server xóa hàng loạt registration của các provider vẫn khỏe. Consumer khi đó mất endpoint và có thể gây outage lớn hơn cảnh báo ban đầu.

Nếu nguyên nhân là nhiều provider thực sự đã chết, self-preservation có thể giữ stale records lâu hơn. Cách xử lý đúng là xác minh trạng thái provider, khôi phục renewal cho instance còn sống và dọn những bản ghi đã xác nhận stale theo quy trình kiểm soát.

### Môi trường test

Trong một test cô lập, có thể tắt self-preservation để kiểm tra lease eviction deterministic, nhưng phải ghi rõ đây là cấu hình test. Không đưa cấu hình đó sang production mà không đánh giá lại rủi ro.

## 11. Theo dõi bằng metrics và cảnh báo

Nên thu thập các chỉ số sau nếu phiên bản và instrumentation cung cấp:

- Số renewal nhận được trong phút gần nhất.
- Expected renewals và renewal threshold.
- Trạng thái self-preservation.
- Số instance đăng ký theo application và status.
- Số eviction và thời điểm eviction.
- Tỷ lệ request renewal thành công, lỗi và timeout.
- Latency của registry API và peer replication.
- Registry fetch latency và cache age ở consumer.
- CPU, heap, GC pause, thread/connection pool của server.

Tên metric cụ thể có thể khác theo Spring Boot Actuator, Micrometer, Spring Cloud Netflix và phiên bản Eureka. Không giả định một metric name duy nhất tồn tại ở mọi bản phát hành; khám phá danh sách metric được expose và xác minh tag/aggregation trước khi tạo alert.

Alert hữu ích nên phân biệt:

| Alert | Ý nghĩa |
|---|---|
| Self-preservation active kéo dài | Renewal thấp hơn ngưỡng trong thời gian dài |
| Renewal error rate tăng | Client hoặc server đang mất heartbeat request |
| Registered instances giảm đột ngột | Có thể là outage, deploy hoặc eviction hàng loạt |
| Registry peer divergence | Các server không có cùng trạng thái |
| Stale instance selection | Consumer vẫn gửi request tới instance đã xác nhận chết |
| Fetch latency/cache age cao | Consumer chậm nhận thay đổi registry |

Không chỉ cảnh báo khi self-preservation bật. Cần kết hợp renewal error rate và stale request để biết cơ chế bảo vệ có đang giữ lại dữ liệu nguy hiểm hay không.

## 12. Bảng chẩn đoán nhanh

| Hiện tượng | Nơi cần tập trung | Hướng xử lý |
|---|---|---|
| Self-preservation bật, mọi client cùng renewal lỗi | Network, proxy, Eureka Server | Kiểm tra route, server health, peer và TLS |
| Chỉ một provider renewal lỗi | Client config/runtime | Kiểm tra URL, DNS, resource, log và credentials |
| Renewal phục hồi nhưng stale record còn | Eviction/lease/server state | Kiểm tra self-preservation, lease và eviction cycle |
| Server đã xóa instance nhưng consumer vẫn gọi | Client fetch/cache/LoadBalancer | Kiểm tra fetch interval và cache propagation |
| Instance khỏe bị xóa nhầm | Threshold/lease/network stability | Xem renewal burst, GC pause, packet loss và lease timeout |
| Self-preservation bật sau scale down | Threshold update/topology change | So sánh số instance thực tế và thời điểm cập nhật threshold |
| Eureka peers hiển thị dữ liệu khác nhau | Peer replication/network | Kiểm tra peer URL, connectivity và replication logs |
| Client nhận 401/403 hoặc TLS error | Security layer | Kiểm tra auth, truststore, certificate và proxy |

## 13. Checklist sau khi xử lý

1. Xác nhận provider nào còn sống và provider nào đã dừng.
2. Ghi nhận self-preservation state và renewal threshold.
3. Đối chiếu renewal thực tế với số instance kỳ vọng.
4. Xác minh client đăng ký và renew tới đúng Eureka Server.
5. Kiểm tra DNS, network, proxy, TLS và authentication.
6. Kiểm tra lease expiration và eviction interval có hợp lý.
7. Kiểm tra trạng thái trên mọi Eureka peer.
8. Kiểm tra fetch interval và cache phía consumer.
9. Chỉ xóa registration stale sau khi xác minh instance không còn hoạt động.
10. Xác minh LoadBalancer không còn chọn endpoint lỗi.
11. Theo dõi renewal ổn định qua nhiều chu kỳ.
12. Lưu nguyên nhân gốc, thay đổi cấu hình và số đo trước/sau.

## 14. Nguyên tắc cần nhớ

- Self-preservation là cơ chế bảo vệ registry khi renewal thực tế thấp hơn ngưỡng dự kiến.
- Khi cơ chế hoạt động, instance stale có thể tiếp tục tồn tại vì eviction bị hạn chế.
- Self-preservation thường là hệ quả của renewal giảm, không nhất thiết là nguyên nhân làm renewal lỗi.
- Tách lỗi ở client, network, proxy, server, peer replication và consumer cache.
- Tính renewal threshold từ số instance và chu kỳ gửi, nhưng xác nhận bằng dashboard/metrics thực tế.
- Không giảm lease hoặc tắt self-preservation chỉ để xóa cảnh báo.
- Xác minh instance thực sự chết trước khi deregister hoặc xóa registration.
- Sau khi renewal phục hồi, vẫn phải kiểm tra registry và consumer đã hội tụ.

Khi Eureka bật self-preservation hoặc liên tục lỗi gia hạn, hãy bắt đầu bằng việc xác định heartbeat bị mất ở đâu. Sau đó kiểm tra threshold, lease, eviction và cache theo từng lớp. Khôi phục renewal cho provider còn sống, xác minh bản ghi stale trước khi dọn và đo lại request từ consumer. Cách xử lý theo bằng chứng giúp registry giữ được instance khỏe trong sự cố mạng, đồng thời loại bỏ endpoint đã chết một cách có kiểm soát.

## Tài liệu tham khảo

- [Spring Cloud Netflix 5.1.0 — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Netflix Eureka — Server Self Preservation Mode](https://github.com/Netflix/eureka/wiki/Server-Self-Preservation-Mode)
- [Netflix Eureka — Understanding Client/Server Communication](https://github.com/Netflix/eureka/wiki/Understanding-eureka-client-server-communication)
- [Netflix Eureka — Peer-to-Peer Communication and Self-Preservation](https://github.com/Netflix/eureka/wiki/Understanding-Eureka-Peer-to-Peer-Communication)
- [Netflix Eureka — PeerAwareInstanceRegistryImpl source](https://github.com/Netflix/eureka/blob/master/eureka-core/src/main/java/com/netflix/eureka/registry/PeerAwareInstanceRegistryImpl.java)
- [Netflix Eureka — AbstractInstanceRegistry source](https://github.com/Netflix/eureka/blob/master/eureka-core/src/main/java/com/netflix/eureka/registry/AbstractInstanceRegistry.java)
