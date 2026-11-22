# Giới hạn của thuật toán khi thiếu thông tin tải thực tế

Spring Cloud LoadBalancer thực hiện cân bằng tải phía client: từ một **service ID**, ứng dụng lấy các `ServiceInstance` khả dụng rồi chọn một instance để gửi HTTP request. Những thuật toán đơn giản như **Round Robin** hoặc **Random** có thể chia tương đối đều số lần lựa chọn. Tuy nhiên, **phân phối đều lượt chọn không có nghĩa là phân phối đều tải thực tế**, vì các instance có thể khác nhau về năng lực, độ trễ và số request đang xử lý.

Bài thuộc chương **Thuật toán chọn đích** trong module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Khi dùng RestClient, WebClient hoặc OpenFeign để gọi service ID, cần phân biệt: service discovery và chuỗi supplier cung cấp **ứng viên**, health check phản ánh **một khía cạnh của tính khả dụng**, còn thuật toán chỉ có thể tối ưu dựa trên **dữ liệu mà nó thực sự nhìn thấy**. Bài này giải thích giới hạn đó, đưa ra ví dụ định lượng, cách quan sát và hướng cải thiện nhằm tránh quá tải, timeout và retry liên tiếp.

## 1. Thuật toán chọn đích nhìn thấy thông tin gì?

Một lần gọi `http://inventory-service/api/items/42` có thể đi theo trình tự:

~~~mermaid
flowchart LR
    A["order-service"] --> B["HTTP client có @LoadBalanced"]
    B --> C["LoadBalancer chọn đích"]
    D["ServiceInstanceListSupplier"] --> C
    E["Discovery / cache / health / filter"] --> D
    C --> F["inventory-a"]
    C --> G["inventory-b"]
    C --> H["inventory-c"]
~~~

Danh sách `ServiceInstance` thường chứa `serviceId`, `host`, `port`, `secure`, `metadata` và một số thông tin phụ thuộc vào discovery. Một supplier có thể lọc theo zone, hint, health check hoặc chính sách ứng dụng.

Nhưng một `ServiceInstance` **không mặc nhiên chứa** các số liệu động như:

- Số HTTP request hiện đang chạy trên instance, kể cả request từ những caller khác.
- Độ dài hàng đợi, số thread/connection còn trống hoặc độ bão hòa của database pool.
- CPU, memory pressure và tốc độ xử lý thực tế tại thời điểm lựa chọn.
- p95/p99 latency, error rate theo endpoint hoặc tỷ lệ timeout gần đây.
- Lượng công việc của mỗi request, ví dụ truy vấn cache nhẹ so với tác vụ ghi dài.

Nếu không có nguồn telemetry riêng, thuật toán chỉ nhìn thấy một **danh sách ứng viên**, có thể kèm metadata tĩnh, và một phần trạng thái cục bộ của client. Từ đó, nó không thể biết chắc instance nào đang có năng lực phục vụ thêm request.

### “Có mặt” khác “sẵn sàng” và “còn công suất”

| Trạng thái | Ý nghĩa | Điều chưa được bảo đảm |
|---|---|---|
| Được discovery tìm thấy | Registry biết địa chỉ instance | Instance còn chạy hay không |
| Health check thành công | Endpoint kiểm tra trả kết quả đạt yêu cầu | Endpoint nghiệp vụ đủ nhanh hay không |
| Được thuật toán chọn | Instance nằm trong tập ứng viên của policy | Instance còn capacity xử lý request mới |
| Trả HTTP 200 | Request cụ thể đã hoàn thành | Request tiếp theo cũng nhanh và thành công |

Một instance có thể trả `200 OK` cho health endpoint nhưng vẫn đang chờ connection pool của database, có hàng trăm request trong queue hoặc bị CPU throttling. Đây là lý do sức khỏe và tải thực tế cần được quan sát độc lập.

## 2. Round Robin phân phối số lượt chọn, không phân phối chi phí xử lý

`RoundRobinLoadBalancer` chọn lần lượt các instance trong danh sách. Với hai instance A và B, một chuỗi đơn giản có thể là:

~~~text
Request:     1  2  3  4  5  6  7  8
Instance:    A  B  A  B  A  B  A  B
Số lần chọn: A = 4, B = 4
~~~

Mục tiêu là phân phối **lượt chọn**, không phải thời gian CPU, số tác vụ đang chạy hay độ dài hàng đợi. Hành vi chính xác còn phụ thuộc danh sách instance có ổn định hay không, cách nhiều caller sử dụng load balancer và cấu hình phiên bản cụ thể.

### Ví dụ: cùng lượng request, concurrency rất khác

Giả sử lưu lượng ổn định **20 request/giây**, Round Robin chia gần đều:

| Instance | Độ trễ trung bình | Request/giây được giao | Số request đồng thời ước tính khi ổn định |
|---|---:|---:|---:|
| A | 50 ms | 10 | 0,5 |
| B | 500 ms | 10 | 5 |

Với quan hệ gần đúng của Little, `L = λ × W`, B phải duy trì trung bình số request đang xử lý nhiều gấp khoảng mười lần A. Con số này mang tính minh họa theo độ trễ trung bình trong trạng thái ổn định, không phải số thread đo trực tiếp. Nếu B bị giới hạn thread pool hoặc connection, hiện tượng xếp hàng có thể bắt đầu sớm hơn.

### Ví dụ: các instance có công suất khác nhau

Giả sử tại thời điểm đo, A xử lý bền vững tối đa **30 request/giây**, còn B chỉ xử lý được **6 request/giây**. Khi lưu lượng tổng là 30 request/giây:

| Instance | Công suất bền vững giả định | Lượt request nhận theo Round Robin |
|---|---:|---:|
| A | 30 request/giây | 15 request/giây |
| B | 6 request/giây | 15 request/giây |

A còn dư công suất trong khi B nhận hơn gấp đôi mức bền vững. B có thể tăng queue, p99 latency, timeout và error rate; biểu đồ “số lượt chọn đến mỗi instance” vẫn gần 50/50.

Ngay cả các instance có cấu hình CPU/RAM giống nhau vẫn có tải khác nhau khi nhận các endpoint nặng nhẹ khác nhau, dữ liệu hotspot khác nhau hoặc vừa trải qua cold start.

**Round Robin là baseline tốt** khi các instance tương đối đồng đều và request có chi phí gần nhau. Nó không tự trở thành thuật toán nhận biết tải chỉ vì danh sách instance được cung cấp qua service discovery.

## 3. Random có kỳ vọng công bằng, nhưng không bảo đảm ở cửa sổ ngắn

`RandomLoadBalancer` chọn ngẫu nhiên từ danh sách ứng viên. Với N instance và cơ chế chọn đều, xác suất kỳ vọng cho mỗi instance là khoảng `1/N`. Tuy nhiên, ở một cửa sổ ngắn, Random có thể dồn nhiều request vào cùng một instance:

~~~text
Lần chọn:  1  2  3  4  5  6
Đích:      A  A  B  A  A  A
~~~

Đây vẫn là một kết quả hoàn toàn có thể xảy ra. Random đơn giản không xem A đang bận hay B đang rảnh. Khi lưu lượng đến theo burst, việc dồn tạm thời có thể làm một instance bị quá tải trước khi tỷ lệ lựa chọn trung bình trở nên cân bằng.

Cần phân biệt **Random đồng đều** với phương án **power of two choices**: chọn ngẫu nhiên hai ứng viên rồi ưu tiên ứng viên ít tải hơn. Phương án sau yêu cầu thêm số liệu tải và logic so sánh; đó không phải mặc định của `RandomLoadBalancer`.

## 4. Weighted routing chỉ tốt khi trọng số phản ánh năng lực

Một phương án cải thiện cho các instance có công suất không đồng đều là phân phối theo trọng số. Trong hệ sinh thái Spring Cloud LoadBalancer, `WeightedServiceInstanceListSupplier` có thể giúp chuẩn bị danh sách để lựa chọn theo weight từ metadata hoặc logic tính weight theo cấu hình.

Ví dụ, giả định A có công suất gấp năm lần B, chọn trọng số:

~~~text
weight(A) = 5
weight(B) = 1

Tỷ lệ lượt chọn kỳ vọng:
A = 5/6 ≈ 83,3%
B = 1/6 ≈ 16,7%
~~~

Với 30 request/giây, ước tính A nhận 25, B nhận 5 request/giây. So với ví dụ công suất 30 và 6 request/giây ở trên, tỷ lệ này phù hợp hơn, dù vẫn cần khoảng trống công suất để hấp thụ các đợt tăng tải và độ biến thiên ngẫu nhiên.

**Trọng số tĩnh sẽ lỗi thời** nếu:

- A bị giảm CPU limit hoặc chịu tác vụ nền tốn tài nguyên.
- B được nâng cấp hoặc vừa được khởi động lại với cache chưa ấm.
- Cả A và B bị nghẽn chung ở database hoặc downstream service.
- Cơ cấu request thay đổi, khiến cùng một request rate tiêu thụ CPU khác trước.
- Trọng số dựa trên benchmark cũ và chưa được hiệu chỉnh.

Weight=5 **không** có nghĩa A chỉ được xử lý tối đa năm request đang chạy. Weighted routing điều chỉnh **tỷ lệ lựa chọn**; giới hạn concurrency cần một cơ chế khác như semaphore, bulkhead hoặc admission control.

## 5. Health check phát hiện khả dụng, không đo toàn bộ tải

`HealthCheckServiceInstanceListSupplier` có thể hạn chế chọn instance không đáp ứng health endpoint. Nhưng khi health endpoint chỉ chạy một phép kiểm tra nhẹ, nó có thể trả `200` ngay cả khi phần nghiệp vụ đang quá tải.

| Tình huống | Health check có thể phát hiện? | Tín hiệu cần bổ sung |
|---|---|---|
| Instance đã ngừng chạy | Thường có, sau một chu kỳ kiểm tra | Kết nối và timeout của client |
| CPU cao nhưng health vẫn nhanh | Có thể không | CPU utilization, throttling |
| Worker pool đã đầy | Phụ thuộc endpoint | Active workers, queue, rejected requests |
| Database pool chờ lâu | Phụ thuộc endpoint | Pool wait time, DB latency |
| p99 của endpoint nặng tăng | Có thể không | Latency phân theo operation |
| Mạng chỉ lỗi từ một caller | Có thể không kịp | Kết quả kết nối theo vùng/caller |

Cần phân biệt liveness, readiness và khả năng phục vụ một endpoint cụ thể. Không nên biến health check thành bài đo hiệu năng liên tục vì chính health request cũng có chi phí, tạo nhiễu và thậm chí gây tải bổ sung.

**Health check thành công không bảo đảm request tiếp theo thành công.** Một instance có thể lỗi ngay sau khi được kiểm tra.

## 6. Cache và độ trễ telemetry làm quyết định lỗi thời

`CachingServiceInstanceListSupplier` giúp giảm số lần hỏi discovery, nhưng danh sách cache có thể vẫn chứa instance vừa bị gỡ hoặc chưa chứa instance mới đăng ký. Ngay cả khi danh sách mới, telemetry tải có thể đã cũ so với các đợt burst lưu lượng.

~~~mermaid
sequenceDiagram
    participant D as Discovery
    participant C as Cache
    participant LB as LoadBalancer
    participant B as Instance B

    D-->>C: Danh sách A, B
    C-->>LB: A, B
    Note over B: B bắt đầu quá tải
    LB->>B: Chọn và gửi request
    B-->>LB: Response chậm hoặc timeout
    Note over C: Cache vẫn trả A, B
    LB->>B: Có thể tiếp tục chọn B
~~~

Có hai dạng thiếu thông tin:

1. **Thiếu chiều dữ liệu**: source chỉ có host/port, không có concurrency, queue, CPU hoặc latency.
2. **Thiếu tính mới**: dữ liệu có tồn tại nhưng được đo/cập nhật quá chậm so với thay đổi thực tế.

Giảm TTL của instance cache có thể giúp cập nhật registry nhanh hơn nhưng không thể tự tạo ra metric tải mà registry không cung cấp. Ngược lại, cập nhật telemetry liên tục làm tăng chi phí giám sát và có thể khiến thuật toán dao động vì nhiễu.

## 7. Client-side LoadBalancer chỉ có góc nhìn cục bộ

Một ứng dụng caller có thể biết những request nó đã gửi và nhận, nhưng **không mặc nhiên biết tải từ các caller khác**:

~~~mermaid
flowchart LR
    A["Caller A"] --> LA["LB A"]
    B["Caller B"] --> LB["LB B"]
    C["Caller C"] --> LC["LB C"]
    LA --> X["Instance X"]
    LB --> X
    LB --> Y["Instance Y"]
    LC --> X
    LC --> Y
~~~

Nếu LB A đếm “in-flight request đến X” bằng 0, điều đó không chứng minh X đang nhàn. LB B và LB C có thể đồng thời gửi hàng trăm request tới X.

Ngay cả thuật toán “chọn instance ít request đang chạy nhất” cần làm rõ nó dựa vào **in-flight của một client** hay **in-flight trên toàn bộ server**. Muốn biết tải toàn cụm, hệ thống cần telemetry tại server, hạ tầng giám sát, service mesh hoặc nguồn phản hồi bổ sung. Dữ liệu tập trung cũng có độ trễ và phải tránh quyết định quá mạnh từ snapshot lỗi thời.

Các bộ chọn Round Robin của các caller độc lập cũng không nhất thiết dùng chung bộ đếm. Mỗi caller có thể tạo ra lựa chọn riêng, khiến phân phối tổng của toàn hệ thống khác với một chuỗi Round Robin lý tưởng.

## 8. Phân phối đẹp trên dashboard vẫn có thể che quá tải

Giả sử đo một phút và thu được các số liệu sau:

| Chỉ số | inventory-a | inventory-b |
|---|---:|---:|
| Request được chọn | 900 | 900 |
| Request hoàn tất thành công | 892 | 724 |
| Timeout | 3 | 144 |
| p95 latency | 75 ms | 1.400 ms |
| CPU trung bình | 43% | 92% |
| Độ dài hàng đợi trung bình | 1 | 36 |

Round Robin đã phân phối cân bằng **số lượt chọn**. Tuy nhiên B đang bão hòa, hoàn thành ít request hơn và làm tăng timeout. Đổi sang Random không cung cấp thông tin để tránh B.

Khi quan sát, cần phân biệt:

- **Selected requests**: số lần LoadBalancer chọn một instance.
- **Started attempts**: số lần HTTP client thực sự bắt đầu gửi, kể cả retry.
- **Completed requests**: số request hoàn tất, phân loại status và độ trễ.
- **Active/in-flight**: số request đang chạy hoặc chờ tại một thời điểm.
- **Work cost**: lượng CPU, I/O và tài nguyên mà từng operation sử dụng.

Số request tổng có thể che tình trạng một instance nhận nhiều endpoint nặng. Cần phân tách theo operation hoặc route với số chiều metric được kiểm soát.

## 9. Đo gì để quyết định có cần thuật toán khác?

Trước khi phát triển chính sách nhận biết tải, thiết lập đường cơ sở:

| Dữ liệu | Câu hỏi |
|---|---|
| Request rate theo service và instance | Traffic đang đi đâu? |
| p50/p95/p99 latency | Độ trễ trung vị và phần đuôi ra sao? |
| HTTP status, timeout, connection errors | Lỗi bắt đầu từ mạng, client hay server? |
| In-flight requests, queue length | Instance có đang tích tụ công việc? |
| CPU, heap, GC, worker pool | Tài nguyên nào sắp bão hòa? |
| Database pool, downstream latency | Nghẽn nằm ở dependency nào? |
| Instance count, health/filter results | Danh sách chọn có đúng không? |
| Retry attempts và instance đã thử | Retry có khuếch đại tải không? |
| SLO, error budget | Hành vi thực tế có đáp ứng mục tiêu không? |

Spring Cloud LoadBalancer có các cơ chế vòng đời như `LoadBalancerLifecycle` để quan sát sự kiện chọn đích và kết quả; có thể kết hợp với HTTP client instrumentation, Micrometer/Actuator và metric server. Một metric chỉ thu ở LoadBalancer **không tự phản ánh** toàn bộ CPU, queue hay thời gian xử lý bên trong một instance.

Khi gắn nhãn metric theo instance ID hoặc operation, kiểm soát cardinality. Không đưa token, user ID hay dữ liệu cá nhân vào metric tag hoặc log.

## 10. Những hướng cải thiện và giới hạn của từng hướng

| Phương án | Dữ liệu cần có | Giới hạn |
|---|---|---|
| Round Robin | Danh sách ứng viên | Không biết tải; chia đều lượt chọn |
| Random | Danh sách ứng viên | Có dao động ngắn hạn và không biết tải |
| Trọng số tĩnh | Ước lượng công suất tương đối | Trọng số có thể lỗi thời |
| Zone preference | Zone/metadata | Tối ưu vị trí, không đo saturation |
| Health filtering | Health endpoint | Nhị phân, cập nhật theo chu kỳ |
| Least in-flight ở caller | Bộ đếm request đang chạy cục bộ | Không thấy tải của caller khác |
| Latency-aware / EWMA tự xây | Latency đủ mẫu, đủ mới | Nhiễu do loại request và mạng |
| Adaptive concurrency | Tín hiệu latency và bão hòa | Cần giới hạn phản ứng và tránh dao động |
| Server-side / service mesh policy | Telemetry ở nơi nhìn thấy tải tổng | Thêm chi phí, độ trễ và phụ thuộc hạ tầng |
| Scale out / tối ưu server | Đo capacity bottleneck | Có chi phí cấp tài nguyên và thời gian khởi động |

Một số chiến lược trong bảng là **hướng thiết kế hoặc tùy biến**, không phải tuyên bố Spring Cloud LoadBalancer mặc định cung cấp đầy đủ các thuật toán này. Muốn dùng dữ liệu latency hay in-flight trong bộ chọn tùy biến, phải bổ sung nơi thu thập, cơ chế truyền và cách xử lý trường hợp thiếu hoặc quá hạn số liệu.

Chính sách tốt nhất chưa chắc là phức tạp nhất. Nếu các instance có cùng năng lực và tải vừa phải, Round Robin có thể đủ hiệu quả với chi phí vận hành thấp. Nếu vấn đề do database bị nghẽn chung, thay thuật toán chọn instance không giải quyết công suất của database.

## 11. Thuật toán thích ứng có thể gây dao động tải

Giả sử bộ chọn nhìn thấy A chậm và ngay lập tức giảm mạnh traffic tới A. B nhận phần lớn request mới, rồi trở nên chậm. Bộ chọn lại chuyển nhiều traffic sang A. Nếu nhiều client độc lập cùng làm vậy dựa trên metric trễ, hệ thống có thể dao động liên tục.

~~~mermaid
flowchart LR
    A["A chậm"] --> B["Giảm traffic tới A"]
    B --> C["Dồn traffic tới B"]
    C --> D["B bão hòa"]
    D --> E["Giảm traffic tới B"]
    E --> A
~~~

Các biện pháp hạn chế dao động thường gồm:

1. **Window đo phù hợp**: không quyết định chỉ từ một vài request ngoại lệ.
2. **Hysteresis**: chỉ đổi chính sách khi chênh lệch vượt ngưỡng rõ ràng.
3. **Giới hạn tốc độ đổi weight**: không chuyển toàn bộ traffic chỉ sau một mẫu đo.
4. **Warm-up instance mới**: tránh dồn tải khi cache, JIT, connection pool chưa sẵn sàng.
5. **Theo dõi loại request**: latency tổng có thể bị thay đổi bởi sự pha trộn tác vụ nặng/nhẹ.
6. **Fallback an toàn**: khi metric mất hoặc quá hạn, không tự động loại toàn bộ instance.
7. **Kiểm thử failure mode**: đo hành vi khi một vùng mất kết nối hoặc dependency chung chậm.

Thông tin tải càng biến động, quyết định càng cần cân bằng giữa tính mới và mức nhiễu. Một thuật toán thích ứng thiếu cơ chế ổn định có thể gây hại hơn Round Robin.

## 12. Timeout, retry và giới hạn concurrency vẫn bắt buộc

Một instance đã được chọn có thể lỗi sau thời điểm lựa chọn. LoadBalancer không bảo đảm request thành công, nên HTTP client vẫn cần timeout, retry có kiểm soát và cơ chế bảo vệ tài nguyên.

Giả sử caller nhận 100 request/giây; khi lỗi, mỗi request được thử **tối đa ba lần tổng cộng**. Nếu phần lớn request tiếp tục thất bại, phía sau có thể nhận tối đa khoảng **300 lượt thử/giây** trong cùng điều kiện. Retry có thể làm tình trạng quá tải nặng hơn.

Cần phân biệt:

- **Load balancing** chọn một instance từ danh sách ứng viên.
- **Timeout** giới hạn thời gian chờ kết nối hoặc response.
- **Retry** thử lại một số lỗi theo policy có giới hạn; lần sau không đương nhiên chọn instance khác.
- **Circuit breaker** kiểm soát hoặc tạm dừng lời gọi khi dependency lỗi liên tiếp.
- **Bulkhead / concurrency limit** giới hạn tài nguyên bị chiếm dụng.
- **Load shedding** từ chối bớt request khi hệ thống không còn khả năng tiếp nhận.

Nếu thao tác có tác dụng phụ, chẳng hạn trừ tồn kho hoặc tạo đơn hàng, retry cần xem xét idempotency và idempotency key. Tránh retry chồng nhau giữa HTTP client, Spring Cloud LoadBalancer và gateway khiến số lần thử vượt ngân sách thời gian.

## 13. Thực hành: chứng minh Round Robin không nhìn thấy tải

Chuẩn bị hai instance cùng đăng ký dưới service ID `inventory-service`. Tạo endpoint thử nghiệm `GET /api/check`:

- Instance A giả lập độ trễ 40–60 ms.
- Instance B giả lập độ trễ 350–450 ms.
- Cả hai cùng healthy và có thể được khám phá từ caller.

Từ một client đã cấu hình `@LoadBalanced`, gửi request bằng service ID:

~~~java
// restClient được tạo từ @LoadBalanced RestClient.Builder
String body = restClient.get()
    .uri("http://inventory-service/api/check")
    .retrieve()
    .body(String.class);
~~~

Cho endpoint trả một mã instance trong môi trường kiểm thử để xác định đích. Không cần lộ hostname nội bộ trong response công khai.

### Bước 1: gọi tuần tự

Gửi khoảng 100 request tuần tự. Ghi instance được chọn, response time và status. Với Round Robin và danh sách ổn định, số lần A/B được chọn thường gần bằng nhau. Độ trễ khi gọi B có thể cao hơn đáng kể.

### Bước 2: gọi đồng thời có giới hạn

Tăng concurrency theo từng mức, đo p95/p99, in-flight, CPU, queue và timeout trên mỗi instance. Giữ nguyên danh sách instance; quan sát điểm B bắt đầu có hàng đợi hoặc timeout dù số lượt chọn vẫn gần 50/50.

### Bước 3: làm thay đổi năng lực của B

Giảm CPU limit hoặc tăng thời gian xử lý ở B trong môi trường thử. Nếu phân phối request không đổi theo độ trễ, có thể thấy rõ Round Robin không dùng dữ liệu công suất thực tế.

### Bước 4: so sánh trọng số

Thử weighted routing nếu phiên bản và cấu hình của ứng dụng có hỗ trợ. Đặt weight dựa trên công suất đã đo, ghi lại tỷ lệ chọn và latency, sau đó thay đổi công suất B lần nữa để quan sát nhược điểm của weight tĩnh.

Ghi kết quả:

| Kịch bản | Tỷ lệ chọn A/B | p95/p99 mỗi instance | Timeout | In-flight/queue | Điều cần kết luận |
|---|---|---|---|---|---|
| A và B tương đồng | Theo policy | So sánh | So sánh | So sánh | Baseline có đủ tốt không? |
| B chậm hơn | Có đổi không? | B tăng? | B tăng? | B tích lũy? | Lượt chọn khác chi phí xử lý |
| B giảm CPU | Có đổi không? | B tăng? | B tăng? | B bão hòa? | Không có feedback tải |
| Điều chỉnh weight | Có theo tỷ lệ? | Có cải thiện? | Có giảm? | Có dồn tải sang A? | Weight đúng trong điều kiện nào? |

Không suy diễn từ ví dụ mô phỏng thành số liệu production. Kết luận phải dựa trên phép đo tại lưu lượng, tài nguyên và dependency cụ thể.

## 14. Checklist chọn chiến lược trong hệ thống thật

Trước khi thay thuật toán, cần xác minh:

- Các instance có công suất CPU/RAM, số worker và pool connection tương đồng hay không?
- Phân phối **request hoàn tất**, p95/p99 latency, error rate và concurrency có cân bằng không?
- Tập `ServiceInstance` có đang bị cache hoặc filter loại nhầm instance không?
- Dữ liệu load/latency có đủ mới và đủ mẫu để ra quyết định không?
- Có nhiều caller độc lập khiến metric in-flight cục bộ bỏ sót phần lớn traffic không?
- Khác biệt giữa các endpoint có làm số lượt request phản ánh sai chi phí xử lý không?
- Retry, timeout, circuit breaker và concurrency limit có phối hợp thành một ngân sách thời gian thống nhất không?
- Có kịch bản thử burst, cold start, instance hỏng và database nghẽn chung chưa?
- Có quan sát được lỗi không chọn được `ServiceInstance`, lỗi kết nối và lỗi HTTP riêng biệt không?
- Thuật toán mới có được kiểm thử chống dao động hoặc dồn tải sang instance khác không?

**Nguyên tắc chính:** không thuật toán nào có thể tối ưu tải dựa trên những tín hiệu nó không nhận được. Round Robin và Random là điểm bắt đầu đơn giản; trọng số có ích khi biết trước năng lực tương đối nhưng không tự thích ứng. Nếu mục tiêu là giảm p99 latency và tránh quá tải, hãy thu thập latency, concurrency, saturation, error rate theo instance, tìm đúng điểm nghẽn, rồi mới quyết định có cần chính sách định tuyến phức tạp hơn. Spring Cloud LoadBalancer chọn `ServiceInstance`, còn chất lượng giao tiếp RestClient, WebClient và OpenFeign vẫn phụ thuộc vào toàn bộ hệ thống cùng timeout, retry và giới hạn tài nguyên.

