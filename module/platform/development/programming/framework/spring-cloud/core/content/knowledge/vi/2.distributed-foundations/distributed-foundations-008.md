# Nguyên tắc quan sát và kiểm chứng hành vi phân tán

> **Chương:** Nền tảng phân tán  
> **Module:** SPRING_CLOUD_CORE  
> **Trọng tâm:** Phát hiện, giải thích và kiểm chứng hành vi thực tế của ứng dụng Spring Cloud khi nhiều dịch vụ, instance, nguồn cấu hình và mạng cùng tham gia xử lý một yêu cầu.

Một lời gọi thành công trong môi trường phát triển chỉ chứng minh rằng **một trường hợp** đã hoạt động. Khi triển khai hệ phân tán, kết quả có thể thay đổi theo vị trí instance, thời gian cập nhật registry, độ trễ mạng, timeout, thời điểm refresh cấu hình, và chính sách retry của client. Vì vậy, người học cần hai năng lực bổ sung cho nhau:

1. **Quan sát (observability):** từ log, metric, trace và trạng thái hệ thống, suy ra điều gì đã xảy ra, ở đâu, trong điều kiện nào.
2. **Kiểm chứng (verification):** xác định trước hành vi mong đợi, tạo điều kiện thử nghiệm có kiểm soát, thu thập bằng chứng và kết luận hệ thống có thỏa điều kiện đó hay không.

Đây là nền tảng để học **Spring Cloud Commons**, **Spring Cloud Context**, cấu hình bên ngoài, refresh scope, discovery, service registry, load balancing và giao tiếp dịch vụ một cách có thể kiểm tra. Các ví dụ giả định dự án đã chọn bộ **Spring Boot – Spring Cloud release train – JDK tương thích** theo tài liệu phiên bản thực tế. Tên thư viện, cơ chế instrument và endpoint quan sát có thể khác nhau giữa các đời phần mềm.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt quan sát tín hiệu, chẩn đoán nguyên nhân và kiểm chứng một giả thuyết.
- Đọc một request đi qua nhiều dịch vụ bằng **log có ngữ cảnh**, **metric tổng hợp** và **distributed trace**.
- Xây dựng tiêu chí kiểm chứng cho discovery, service registry, load balancing, externalized configuration và refresh scope.
- Thiết kế thử nghiệm với instance mất kết nối, registry trả dữ liệu cũ, độ trễ tăng, timeout, retry, thay đổi cấu hình.
- Phân biệt kết quả quan sát được với điều chưa thể kết luận; không suy ra “luôn đúng” từ vài lần gọi thành công.
- Viết báo cáo sự cố hoặc kết quả thử nghiệm có dữ liệu đối chiếu: điều kiện, hành động, quan sát, kết luận và giới hạn.

## 2. Vì sao hệ phân tán khó quan sát hơn một ứng dụng đơn?

Giả sử yêu cầu `POST /orders` đến `order-service`. Dịch vụ này kiểm tra tồn kho qua `inventory-service` rồi gọi `payment-service`. Mỗi dịch vụ có thể chạy nhiều instance. Một request bên ngoài trở thành nhiều thao tác bên trong, có thể hoàn thành vào những thời điểm khác nhau.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Client
    participant O as order-service
    participant D as Discovery
    participant I as inventory-service
    participant P as payment-service
    U->>O: POST /orders
    O->>D: Tra cứu inventory-service
    D-->>O: Danh sách instance đã biết
    O->>I: GET /stock/{sku}
    I-->>O: Còn hàng / Lỗi / Timeout
    O->>P: POST /charge
    P-->>O: Kết quả hoặc phản hồi không rõ
    O-->>U: Kết quả tổng hợp
~~~

Những câu hỏi quan sát cần trả lời:

- Request mất thời gian ở `order-service`, ở `inventory-service` hay trên đường mạng?
- Bên gọi đã chọn instance nào, dựa trên tập instance nào?
- Client có retry không; nếu có, đó là request thứ mấy?
- Một lỗi HTTP 500 bắt nguồn từ service đích hay do phía gọi chuyển đổi từ ngoại lệ khác?
- Nếu phía thanh toán đã xử lý nhưng phản hồi bị thất lạc, hệ thống tránh thu tiền lần hai bằng cách nào?
- Config được đọc từ property source nào, phiên bản nào, và bean đã nhận cấu hình mới hay chưa?

**Một log đơn lẻ không đủ trả lời toàn bộ chuỗi câu hỏi.** Mỗi instance có đồng hồ, vòng đời và kết nối riêng. Sự kiện nhìn thấy muộn không nhất thiết diễn ra muộn; log ghi ra khác thứ tự không chứng minh thứ tự nhân quả. Cần gắn ngữ cảnh và đối chiếu nhiều nguồn bằng chứng.

### 2.1. Các nguồn bất định

| Nguồn bất định | Ví dụ cụ thể | Tác động cần kiểm chứng |
| --- | --- | --- |
| **Mạng** | Gói tin trễ, kết nối bị từ chối, TCP reset, DNS không phân giải được. | Timeout và retry có được kiểm soát? |
| **Thời gian** | Request đến ngay trước khi instance bị dừng; đồng hồ hai máy lệch nhau. | Có thể kết luận thứ tự sự kiện từ timestamp hay không? |
| **Discovery** | Registry còn lưu instance đã chết; discovery client có cache. | Tập instance client nhìn thấy có còn hợp lệ? |
| **Phân tải** | Một instance quá tải, instance khác vẫn khỏe. | Request đã chọn đích nào? Chính sách lựa chọn có phù hợp? |
| **Cấu hình** | Giá trị ngoài hệ thống đổi nhưng bean chưa refresh. | Giá trị nào thực sự có hiệu lực ở thời điểm request? |
| **Lỗi từng phần** | Inventory thành công, payment timeout. | Trạng thái đơn hàng có nhất quán với kết quả giao dịch? |
| **Quan sát thiếu** | Chỉ log lỗi, không có request ID và target instance. | Có đủ bằng chứng để quy lỗi cho đúng chặng? |

Một hệ thống hoạt động đúng phải xác định cách xử lý các trường hợp bất định, không chỉ trường hợp tất cả thành phần đều khỏe.

## 3. Ba câu hỏi nền tảng: Điều gì xảy ra? Vì sao? Có đúng không?

Để tránh diễn giải mơ hồ, dùng một chuỗi điều tra cố định:

1. **Nhận diện hiện tượng:** p95 latency tăng; tỉ lệ lỗi của `order-service` tăng; endpoint readiness chuyển trạng thái.
2. **Khoanh vùng:** so sánh trước/sau theo endpoint, phiên bản triển khai, instance, dependency và thời điểm.
3. **Đặt giả thuyết có thể kiểm tra:** “lỗi tăng vì client còn chọn instance `inventory-2` đã bị dừng”.
4. **Chọn phép đo và phép thử:** xem danh sách `ServiceInstance`, instance đích trong log, trace của request lỗi; cô lập hoặc dừng một instance trong môi trường kiểm thử.
5. **Kiểm chứng:** đối chiếu quan sát với tiêu chí đã đặt ra; nếu bằng chứng mâu thuẫn, sửa giả thuyết.
6. **Ghi kết luận có giới hạn:** “trong cấu hình và khoảng thời gian thử nghiệm này, sau khoảng cập nhật cache, không còn request hướng tới instance đã dừng”; không khẳng định mọi hệ thống hoặc mọi tình huống có cùng độ trễ.

Phân biệt ba loại thông tin:

- **Tín hiệu:** “12 request trả HTTP 503 trong 1 phút”.
- **Giả thuyết:** “registry cập nhật chậm nên load balancer còn dùng endpoint cũ”.
- **Bằng chứng kiểm chứng:** “trace cho thấy 12 request này chọn instance X, trong khi log instance X ghi dừng trước đó và lookup vẫn trả về X đến thời điểm Y”.

Nếu chỉ có tín hiệu, chưa thể kết luận nguyên nhân.

## 4. Bốn nhóm tín hiệu cần thu thập

### 4.1. Logs: từng sự kiện có ngữ cảnh

Log nên cho biết **ai** thực hiện, **việc gì**, **khi nào**, **kết quả gì** và **liên quan tới request nào**. Ưu tiên log có cấu trúc, các trường tiêu biểu:

| Trường | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `timestamp` | Thời điểm phát sinh sự kiện. | Thống nhất UTC và định dạng; theo dõi sai lệch đồng hồ. |
| `service` / `instance` | Tên ứng dụng và định danh instance. | Cần để phân biệt nhiều bản sao của cùng dịch vụ. |
| `traceId` / `spanId` | Liên kết sự kiện với distributed trace. | Chỉ có nếu instrumentation/tracing đã bật và truyền context đúng. |
| `requestId` | Mã request ở mức nghiệp vụ hoặc cổng vào. | Dùng thêm khi tracing bị lấy mẫu hoặc ngắt mạch truyền context. |
| `operation` / `dependency` | Thao tác và dịch vụ phụ thuộc. | Ví dụ `inventory.lookup`, `inventory-service`. |
| `targetInstance` | Địa chỉ hoặc ID instance được chọn. | Hữu ích để kiểm tra discovery và load balancing. |
| `status` / `errorType` / `durationMs` | Kết quả, loại lỗi và thời gian. | Không chỉ ghi chuỗi “request failed”. |
| `configRevision` | Phiên bản cấu hình không nhạy cảm. | Cho phép so sánh trước/sau refresh/deploy. |

Ví dụ hai log được **minh họa**, không phải format mặc định của Spring Boot:

~~~json
{"timestamp":"2026-01-01T10:00:00Z","service":"order-service","instance":"order-1","traceId":"trace-a1","spanId":"span-o1","operation":"inventory.lookup","targetInstance":"inventory-2","attempt":1,"status":"TIMEOUT","durationMs":800}
{"timestamp":"2026-01-01T10:00:01Z","service":"order-service","instance":"order-1","traceId":"trace-a1","spanId":"span-o2","operation":"inventory.lookup","targetInstance":"inventory-1","attempt":2,"status":"OK","durationMs":42}
~~~

Có thể suy ra trong ví dụ ứng dụng đã ghi **hai lần thử** cùng trace và chọn **hai instance khác nhau**. Chỉ từ log này chưa suy ra vì sao lần đầu timeout, retry có an toàn hay kết quả nghiệp vụ cuối cùng có đúng hay không.

Không ghi password, API key, access token, toàn bộ payload nhạy cảm hoặc định danh cá nhân vào log chỉ để chẩn đoán. Với ID có độ phân tán rất lớn, cần cẩn trọng khi đưa thành nhãn metric.

### 4.2. Metrics: nhìn xu hướng và mức ảnh hưởng

Metric gom nhiều lần quan sát thành số liệu theo thời gian. Chúng giúp trả lời: có bao nhiêu request, bao nhiêu lỗi, latency ra sao, áp lực hệ thống đang tăng hay giảm.

Các đại lượng cơ bản:

| Loại metric | Câu hỏi | Ví dụ ý nghĩa |
| --- | --- | --- |
| **Request rate** | Mỗi giây/phút nhận bao nhiêu request? | Phân biệt tải tăng với sự cố khi tải không đổi. |
| **Error rate** | Tỉ lệ lỗi là bao nhiêu? | Tách lỗi 4xx do client khỏi 5xx và lỗi network tùy mục tiêu SLO. |
| **Latency** | p50/p95/p99 hoặc histogram ra sao? | Trung bình có thể che đuôi chậm của một số request. |
| **Saturation** | Pool kết nối, thread, CPU, queue có gần giới hạn? | Phát hiện nghẽn trước khi tăng lỗi. |
| **Dependency health** | Call tới inventory/payment thất bại bao nhiêu? | Phân biệt lỗi nội bộ với lỗi phụ thuộc. |
| **Discovery/instance state** | Có bao nhiêu instance được nhìn thấy, lookup rỗng bao lâu? | Tìm sự lệch giữa trạng thái registry và thực tế. |

Một cách nhìn thực tế là theo **RED** (Rate, Errors, Duration) với dịch vụ xử lý request và **USE** (Utilization, Saturation, Errors) với tài nguyên. Chúng là góc nhìn vận hành, không thay thế điều kiện đúng/sai của nghiệp vụ.

Ví dụ SLO dùng trong **bài lab**, do nhóm tự đặt:

- Trong cửa sổ quan sát xác định trước, ≥ 99,5% request `GET /orders/{id}` hợp lệ được xử lý thành công.
- p95 latency của request hợp lệ dưới 300 ms ở tải thử nghiệm đã định.
- Lỗi do phụ thuộc không được gây request treo vô hạn; mọi call bên ngoài phải có timeout.

Không lấy các ngưỡng trên làm chuẩn mặc định của Spring Cloud hay chuẩn của production. Ngưỡng đúng phụ thuộc yêu cầu và tải của hệ thống.

**Lưu ý về nhãn:** nhãn ít biến thể như `service`, `route`, `outcome` giúp tổng hợp tốt. Không dùng `traceId`, email, order ID hoặc raw URL chứa ID làm nhãn metric vì có thể tạo cardinality rất lớn.

### 4.3. Traces: đường đi của một request

Distributed trace mô tả một chuỗi thao tác (các **span**) liên kết bằng quan hệ cha/con hoặc các liên kết phù hợp. Mỗi span có khoảng thời gian, tên thao tác, ngữ cảnh dịch vụ và thuộc tính.

Ví dụ minh họa:

~~~text
trace: T-481
  POST /orders                          order-service    1040 ms
    inventory.lookup                    order-service     830 ms
      GET /stock/{sku}                  inventory-service  820 ms
    payment.charge                      order-service     150 ms
      POST /charge                      payment-service    145 ms
~~~

Trace giúp định vị phần chiếm nhiều thời gian; cần đối chiếu log/metric để lý giải vì sao span đó chậm. Sơ đồ trace không mặc nhiên bao quát tác vụ bất đồng bộ, message queue hay hệ thống không được instrument.

**Context propagation** là điều kiện quan trọng: thông tin liên kết trace phải được truyền qua HTTP/messaging bằng cơ chế tracing phù hợp, thường sử dụng chuẩn W3C Trace Context (`traceparent`, `tracestate`). Nếu có client tự tạo hoặc thread xử lý ngoài luồng mà không truyền context, trace có thể bị đứt.

Đồng hồ có thể lệch giữa các máy; ưu tiên quan hệ span và đo thời lượng thích hợp hơn suy luận nhân quả chỉ từ timestamp tuyệt đối. Sampling tiết kiệm chi phí nhưng khiến không phải mọi request đều có trace đầy đủ. Một trace vắng mặt chưa chứng minh request không từng xảy ra.

### 4.4. Trạng thái ứng dụng và hạ tầng

Ngoài logs, metrics và traces còn có các tín hiệu trạng thái:

- **Liveness:** tiến trình có còn hoạt động theo định nghĩa probe không?
- **Readiness:** instance có sẵn sàng nhận request theo định nghĩa ứng dụng và môi trường triển khai không?
- **Registry/discovery:** instance có đang được công bố và được client nhìn thấy không?
- **Deployment:** phiên bản, thời điểm rollout, restart count và biến động tài nguyên.
- **Configuration:** nguồn cấu hình, profile đang bật, revision cấu hình đã áp dụng.

**Healthy**, **ready** và **registered** là các khái niệm khác nhau. Một instance có thể còn sống nhưng chưa sẵn sàng; registry có thể vẫn chứa địa chỉ cũ; load balancer có thể nhìn thấy dữ liệu discovery chưa cập nhật. Không nên kết luận “service đang khỏe” từ một endpoint duy nhất.

## 5. Các bất biến cần kiểm chứng: đừng chỉ nhìn HTTP 200

Trong hệ phân tán, yêu cầu quan trọng thường là **bất biến nghiệp vụ** hoặc **đặc tính hệ thống** vẫn đúng ngay cả khi một phần thất bại.

| Loại yêu cầu | Cách diễn đạt có thể kiểm chứng | Bằng chứng cần thu |
| --- | --- | --- |
| **An toàn (safety)** | Một mã giao dịch idempotency key không tạo hai lần thu tiền hợp lệ. | Nhật ký quyết định giao dịch, trạng thái bền vững và số lần ghi nhận. |
| **Tính tiến triển (liveness)** | Khi dependency hồi phục và các giả định công bằng được thỏa, request mới có thể thành công trở lại. | Kết quả gọi lặp lại trong cửa sổ đã định. |
| **Giới hạn thời gian** | Call đến dependency không vượt quá timeout đã cấu hình cộng overhead được chấp nhận. | Metric và trace thời lượng, cấu hình client. |
| **Tính nhất quán** | Trạng thái đơn hàng và thanh toán thỏa quy tắc chuyển trạng thái của nghiệp vụ. | Kiểm tra dữ liệu và các sự kiện liên quan. |
| **Khả năng chịu lỗi** | Khi một instance inventory mất, hệ thống không tiếp tục phụ thuộc vĩnh viễn vào địa chỉ đó. | Lookup theo thời gian, log instance được chọn, tỉ lệ lỗi hồi phục. |
| **Quan sát đủ** | Có thể truy vết một request lỗi tới dịch vụ và dependency gây lỗi trong môi trường có instrumentation. | Trace ID, target instance, error category. |

**Safety** mô tả điều không được phép xảy ra. **Liveness** mô tả điều tốt cuối cùng sẽ xảy ra **trong các giả định cụ thể**, ví dụ dependency có phục hồi và hệ thống còn tài nguyên để xử lý. Thử một số hữu hạn trường hợp không phải là bằng chứng hình thức cho mọi lịch xen kẽ, mọi lỗi mạng hoặc mọi phân đoạn mạng.

### 5.1. Phải xác định đơn vị quan sát

Tỉ lệ lỗi có thể tính theo:

- **Request phía client:** một hành động người dùng, có thể gồm nhiều lần gọi dependency.
- **Attempt tới dependency:** mỗi lần gửi request, kể cả retry.
- **Transaction nghiệp vụ:** một đơn hàng/thanh toán có thể gồm nhiều request.

Ví dụ: 100 request người dùng, 20 request cần retry một lần; tổng cộng 120 attempt tới dependency. Nếu 20 attempt đầu lỗi nhưng 100 request người dùng cuối cùng đều thành công, **attempt error rate** là 20/120 trong khi **user-visible error rate** là 0/100. Cả hai đều hữu ích, nhưng trả lời những câu hỏi khác nhau. Khi báo cáo, luôn ghi rõ mẫu số.

## 6. Quan sát đúng từng abstraction Spring Cloud

### 6.1. Spring Cloud Commons: discovery và load balancing

Spring Cloud Commons cung cấp hợp đồng như `DiscoveryClient`, `ServiceInstance` và `ServiceRegistry`. Nguồn instance có thể là registry như Eureka/Consul, cấu hình tĩnh hoặc implementation phù hợp môi trường. Spring Cloud LoadBalancer có thể dùng danh sách instance để chọn đích thực tế.

Hãy thu thập riêng biệt:

1. **Kết quả lookup:** service ID, số instance trả về, thời điểm và nguồn discovery.
2. **Quyết định lựa chọn:** instance ID/host/port đã được chọn để gửi request.
3. **Kết quả kết nối:** kết nối có thành công không, status HTTP, timeout và thời lượng.
4. **Tình trạng registry và instance:** thời điểm instance bắt đầu/dừng, thông tin đăng ký còn hiệu lực không.

| Hiện tượng | Những giả thuyết khác nhau cần phân biệt |
| --- | --- |
| `getInstances("inventory-service")` trả rỗng. | Service ID sai, discovery chưa sẵn sàng, chưa đăng ký, mất kết nối với registry, chính sách lọc instance. |
| Có instance nhưng kết nối bị từ chối. | Process đã dừng, port sai, quy tắc mạng chặn, metadata/registry bị cũ. |
| Có instance nhưng HTTP 503. | Instance/ứng dụng từ chối xử lý, proxy trả lỗi, hay dependency bên trong nó gặp sự cố. |
| Request chỉ vào một instance. | Có thực sự nhiều instance được discover? Algorithm có phù hợp? Test có quá ít request? Có cache hoặc routing khác? |
| Một instance chết nhưng client còn gọi vào đó. | Delay registry, cache discovery, cache load balancer, quá trình shutdown/health chưa đồng bộ. |

Không giả định rằng mọi provider sẽ lập tức loại instance khỏi kết quả lookup. Cũng không giả định thuật toán phân tải luôn round-robin hoặc tỉ lệ request đến các instance sẽ hoàn hảo với một mẫu nhỏ.

**Bài kiểm chứng:** chạy hai instance của `inventory-service` có trường response `instanceId`; ghi lại tập URI trả bởi discovery client và URI thực tế được chọn cho mỗi lần gọi. Dừng một instance; đo **thời điểm bắt đầu lỗi**, **thời gian tới khi lookup ngừng trả instance đó** và **thời gian tới khi client không còn chọn instance đó**. Ba mốc này có thể không trùng nhau.

### 6.2. Spring Cloud Context: cấu hình bên ngoài và refresh scope

Cấu hình ngoài của Spring Boot có thể đến từ `application.yml`, profile, biến môi trường, tham số chạy và nguồn tích hợp khác. Spring Cloud Context có các cơ chế liên quan cấu hình và ngữ cảnh, bao gồm refresh scope khi được kích hoạt phù hợp. Thay đổi một file không tự động đảm bảo bean đang chạy nhận giá trị mới.

Để kiểm chứng refresh, phân biệt bốn bước:

1. **Nguồn thay đổi:** tệp hoặc nguồn cấu hình bên ngoài đã thực sự chứa giá trị mới.
2. **Environment cập nhật:** giá trị mới có được nạp vào các property source mà ứng dụng sử dụng?
3. **Scope/bean cập nhật:** bean thuộc `@RefreshScope` có được invalidated và tái tạo khi truy cập qua proxy không?
4. **Hành vi request:** request đến **đúng instance** có cho kết quả mới không?

Ví dụ một thuộc tính minh họa:

~~~yaml
app:
  feature:
    mode: standard
~~~

Giả sử một bean đọc `app.feature.mode` khi khởi tạo. Thí nghiệm: ghi nhận mode trước đổi; thay bằng `safe` ở nguồn cấu hình; kích hoạt quy trình refresh được hỗ trợ; kiểm tra môi trường và đáp ứng của từng instance. Nếu instance A nhận `safe` còn instance B giữ `standard`, đây là **trạng thái cấu hình khác nhau giữa instance** cần ghi nhận và xử lý theo yêu cầu hệ thống.

Không suy ra refresh lan truyền đến **mọi** instance, mọi bean hoặc mọi nguồn cấu hình. Không mặc định endpoint refresh tồn tại, được expose hay an toàn để gọi từ bên ngoài. Kiểm tra dependency, quy trình và bảo vệ quyền truy cập ở phiên bản cụ thể.

### 6.3. Giao tiếp dịch vụ: timeout, retry và phản hồi không chắc chắn

Từ góc nhìn client, kết quả thường thuộc các nhóm:

- **Nhận HTTP response:** có status và payload; thành công/lỗi phụ thuộc contract nghiệp vụ.
- **Timeout:** quá thời gian chờ; không biết chắc dịch vụ đích có xử lý request hay chưa.
- **Connection refused/reset:** không hoàn tất giao tiếp; mức độ thực hiện ở đích phụ thuộc thời điểm lỗi.
- **Không phân giải được đích:** discovery/DNS/client configuration chưa tạo ra endpoint phù hợp.

Đặc biệt, **timeout không chứng minh operation chưa thực hiện**. Nếu client gọi `POST /charge` rồi timeout, retry tự động không có idempotency key có thể dẫn đến thu tiền hai lần. Với operation có tác dụng phụ, thiết kế khóa idempotency, lưu vết xử lý và kiểm chứng trạng thái trước khi retry theo nghiệp vụ.

**Nguyên tắc khi kiểm chứng retry:** phải ghi được `requestId` hoặc idempotency key, số attempt, target instance, nguyên nhân retry và kết quả cuối cùng. Tỉ lệ thành công sau retry không đủ chứng minh an toàn.

## 7. Thiết lập quan sát tối thiểu trong hệ Spring Boot / Spring Cloud

### 7.1. Định nghĩa thiết bị đo trước khi chạy thử

Trong mini-system gồm `order-service` và `inventory-service`, trước tiên chọn:

- **Bản ghi:** service, instance, request ID, trace ID (nếu có), operation, target, duration, outcome.
- **Metric:** request count, error count, latency histogram/timer, active requests và các metric tài nguyên hữu ích.
- **Trace:** một trace xuyên qua HTTP client và HTTP server, có span cho dependency call.
- **Trạng thái:** health/liveness/readiness khi đã cấu hình, và danh sách instance do discovery trả về.

Các tín hiệu này có thể thu bằng Spring Boot Actuator, Micrometer và giải pháp logging/tracing/metrics tương ứng. **Dependency nào cần thêm, tên setting nào áp dụng và auto-instrumentation có hiệu lực không** phải kiểm tra trong tài liệu của bộ Boot/Cloud đã chọn; chỉ thêm BOM không tự bật telemetry.

Ví dụ một phần cấu hình Actuator dùng trong **lab** (phải có starter tương ứng và registry/exporter khi cần):

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      probes:
        enabled: true
~~~

Trên các phiên bản Spring Boot hỗ trợ, cấu hình trên cho phép sử dụng các endpoint thuộc Actuator đã cài tương ứng; **không khẳng định mọi environment hoặc deployment sẽ có cùng endpoint và kết quả**. Nếu dùng endpoint Prometheus, cần có registry thích hợp và chủ động expose `prometheus`. Trong production nên giới hạn mạng, quyền truy cập và dữ liệu hiển thị.

Quan sát tại local:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/health/readiness
curl -i http://localhost:8080/actuator/metrics
~~~

Nếu lệnh không trả kết quả dự kiến, kiểm tra dependency Actuator, cổng management, health probe configuration, security, expose settings và phiên bản Spring Boot. Đừng thay đổi bảo mật một cách tùy tiện chỉ để làm lệnh demo thành công.

### 7.2. Truyền context giữa các dịch vụ

Để trace xuyên qua nhiều service, dùng HTTP client nằm trong cơ chế instrumentation được framework hỗ trợ (ví dụ builder/client được Spring quản lý theo phiên bản đang sử dụng), rồi xác nhận các header trace được truyền và phía đích tạo span liên quan. Với xử lý bất đồng bộ hoặc client tự khởi tạo ngoài container, cần kiểm tra context propagation riêng.

Checklist kiểm chứng:

1. Gọi một request có ID xác định từ client.
2. Tìm log bên nhận và bên gọi; xác minh cùng trace hoặc request ID.
3. Xem trace có span outbound/inbound tương ứng.
4. Cố ý làm một call timeout và xác nhận tên dependency, loại lỗi, thời lượng, attempt xuất hiện đủ để điều tra.
5. Với sampling thấp, đối chiếu request ID ở log khi trace không được lưu; không xem thiếu trace là mất request.

Trong lab có thể tăng sampling để dễ học nhưng phải tính chi phí và thông tin được xuất; không dùng giá trị lấy mẫu toàn bộ làm cấu hình mặc định cho hệ thống nhiều tải.

### 7.3. Dấu thời gian và đồng bộ đồng hồ

Nên chuẩn hóa timestamp dạng UTC và sử dụng đồng hồ hệ thống được đồng bộ. Khi đo duration, ưu tiên timer/clock phù hợp trong process. Không đo độ trễ đầu-cuối bằng cách lấy timestamp từ hai máy khác nhau mà không xét clock skew. Quan hệ parent/child giữa span và request ID hỗ trợ suy luận, nhưng không thể thay thế mô hình nhân quả nếu có tác vụ bất đồng bộ hoặc message broker.

## 8. Thiết kế phép thử có thể lặp lại

Mỗi thử nghiệm nên có **hợp đồng kiểm chứng** trước khi bắt đầu:

| Thành phần | Câu hỏi phải trả lời |
| --- | --- |
| **Giả thuyết** | Hệ thống được cho là sẽ làm gì khi xảy ra một sự cố cụ thể? |
| **Thiết lập** | Phiên bản, topology, số instance, registry, timeout, retry, profile và tải là gì? |
| **Kích thích** | Dừng process, tạo delay, thay config, chặn network hay trả HTTP 500? |
| **Mốc thời gian** | Bắt đầu từ trạng thái nào, can thiệp lúc nào, quan sát bao lâu? |
| **Oracle (tiêu chí đúng/sai)** | Điều kiện nào đánh dấu PASS/FAIL? |
| **Tín hiệu thu thập** | Log, metric, trace, trạng thái nghiệp vụ và ảnh chụp cấu hình nào? |
| **Khôi phục** | Làm cách nào đưa hệ thống về trạng thái ban đầu sau thử? |
| **Giới hạn** | Có bao nhiêu lượt chạy; môi trường này mô phỏng được những loại lỗi nào? |

**Ví dụ hợp đồng:** “Khi một trong hai instance inventory dừng, sau khi hệ thống discovery/convergence ổn định, request mới có thể dùng instance còn sống; lỗi trung gian được ghi nhận và không có request nào treo quá timeout đã quy định.” Phải định nghĩa **cửa sổ chờ hội tụ** và **timeout** bằng cấu hình hoặc tiêu chí test, tránh dùng từ “ngay lập tức” mà không đo.

### 8.1. Test pyramid thực tế

| Cấp kiểm thử | Phương pháp | Phù hợp để chứng minh | Giới hạn |
| --- | --- | --- | --- |
| **Unit** | Mock dependency, fake clock, test quy tắc retry/fallback/idempotency. | Quyết định của code theo đầu vào cụ thể. | Không chứng minh mạng, auto-configuration hay discovery thực. |
| **Component/Spring integration** | Khởi tạo context, test binding config, giả lập HTTP server hoặc `DiscoveryClient`. | Wiring, property precedence, HTTP error mapping, một phần instrumentation. | Chưa thể đại diện đầy đủ topology production. |
| **Multi-instance integration** | Chạy order + 2 inventory instance, discovery nguồn tĩnh hoặc registry test. | Lựa chọn instance, propagation, hành vi khi instance chết. | Phụ thuộc loại runtime và cấu hình test. |
| **Failure/chaos test có kiểm soát** | Thêm latency, drop/reset kết nối, kill instance, tạm ngắt registry. | Phát hiện lỗi từng phần và kiểm tra cơ chế hồi phục. | Không thể tái hiện mọi tổ hợp lỗi; cần môi trường an toàn. |
| **Operational validation** | Xem dashboard, alert, trace, health, báo cáo sự cố giả lập. | Hệ thống có đủ dữ liệu để chẩn đoán và phản ứng. | Đầy đủ dữ liệu chưa tự chứng minh đúng nghiệp vụ. |

Ưu tiên các điều kiện kiểm chứng có thể chạy tự động. Để test ổn định, dùng fake server/clock, latch, polling có deadline hoặc công cụ fault injection kiểm soát; tránh kỳ vọng chính xác “sau `Thread.sleep(1000)` phải loại instance” vì cache, scheduler và hạ tầng có độ biến thiên.

### 8.2. Ma trận tình huống tối thiểu

| ID | Tình huống tạo ra | Tín hiệu cần thấy | Điều kiện kiểm chứng |
| --- | --- | --- | --- |
| D1 | Discovery trả 0 instance. | Số instance lookup = 0; lỗi phân giải đích. | Client trả lỗi được định nghĩa và không gửi HTTP đến URI bất kỳ. |
| D2 | Discovery trả 2 instance khỏe. | Target instance trong log/trace; số call thành công. | Request đến một instance hợp lệ; không giả định phân bố 50/50 với vài request. |
| D3 | Dừng instance đã được công bố. | Thời điểm dừng, lookup, target chọn, connection error. | Ghi được giai đoạn stale discovery và xác nhận trạng thái sau hội tụ. |
| N1 | Thêm network latency. | p95/p99 tăng, trace dependency span dài. | Timeout cắt request theo chính sách; lỗi được phân loại đúng. |
| N2 | Đích trả HTTP 500. | HTTP status, upstream service, error rate. | Client xử lý lỗi đúng contract; retry chỉ khi chính sách cho phép. |
| N3 | Mất response sau khi phía đích đã xử lý. | Request ID và trạng thái nghiệp vụ ở đích. | Không nhân đôi tác dụng phụ khi client quyết định gọi lại. |
| C1 | Thay cấu hình nhưng chưa refresh/restart. | Config revision, output của bean. | Mô tả được vì sao giá trị cũ có thể còn hiệu lực. |
| C2 | Refresh đúng quy trình trên một instance. | Revision và response trước/sau của instance đó. | Bean thuộc scope phù hợp phản ánh giá trị mới sau refresh theo hợp đồng. |
| C3 | Refresh trên một trong hai instance. | Config revision theo từng instance. | Quan sát được sự khác biệt nếu chưa phối hợp đồng bộ rollout/refresh. |
| O1 | Tracing bị ngắt giữa hai service. | Span hoặc trace ID bị tách. | Phát hiện điểm mất propagation; log/request ID còn hỗ trợ điều tra. |

**Mỗi trường hợp cần tối thiểu một assertion hành vi và một bằng chứng quan sát.** Chỉ xác minh “có log” chưa chứng minh hệ thống hoạt động đúng; chỉ xác minh HTTP 200 chưa chứng minh hệ thống quan sát được.

## 9. Ví dụ thực hành: Theo dõi instance chết và request hồi phục

### 9.1. Mô hình lab

Dùng ba tiến trình:

- `order-service`: port `8080`, gọi `inventory-service` theo service ID.
- `inventory-a`: port `8081`, trả JSON gồm `instanceId: "a"`.
- `inventory-b`: port `8082`, trả JSON gồm `instanceId: "b"`.

Trong lab đầu tiên, dùng SimpleDiscoveryClient để mô phỏng tập instance của service ID:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

**Lưu ý:** với cấu hình **tĩnh**, khi dừng một instance, danh sách URI **không tự thay đổi** vì không có registry động cập nhật danh sách. Vì vậy phép thử này kiểm tra khả năng xử lý lỗi khi target mất kết nối và giới hạn của discovery tĩnh. Nếu mục tiêu là **đo hội tụ đăng ký/huỷ đăng ký**, cần một registry/discovery implementation động tương ứng. Hai thí nghiệm phải được báo cáo riêng.

Với Spring Cloud LoadBalancer được tích hợp vào HTTP client phù hợp, `order-service` có thể gọi URL logic dạng:

~~~text
http://inventory-service/api/stock/ABC-123
~~~

Để mã minh họa hoạt động phải dùng client được cấu hình load-balanced thực sự và thêm các dependency tương ứng; một HTTP client thường **không tự hiểu** service ID `inventory-service`.

### 9.2. Thử nghiệm từng bước

1. Chạy cả ba process, ghi JDK, Spring Boot, Spring Cloud release train, dependency discovery/load-balancer và timeout đang dùng.
2. Gọi endpoint order nhiều lần; xác nhận request thành công. Thu `traceId` hoặc `requestId`, instance đích, duration và response.
3. Ghi lại danh sách URI nhìn thấy từ `DiscoveryClient` để có baseline.
4. Dừng `inventory-b` bằng cách chủ động stop process.
5. Tiếp tục gọi với **tốc độ đã xác định**; ghi rõ số request, số lỗi, timeout và instance được chọn.
6. Đối chiếu log order với trạng thái process `inventory-b`. Với simple discovery tĩnh, dự kiến danh sách vẫn có URI cũ; không đánh đồng đây là lỗi của registry động.
7. Khởi động lại `inventory-b`; chạy lại phép thử, xác minh việc khôi phục kết nối.
8. Nếu đổi sang registry động, lặp lại và đo riêng thời điểm remove/return instance trong registry, discovery cache và quá trình lựa chọn đích.

Một bản ghi kết quả **mẫu** cần tự điền khi chạy:

| Mốc | Discovery nhìn thấy | Target được chọn | HTTP outcome | Ghi chú |
| --- | --- | --- | --- | --- |
| Baseline | A, B | A | 200 | Hai process đều chạy |
| Sau dừng B | A, B (với simple tĩnh) | B | Connection error/timeout | Thông tin tĩnh còn B |
| Lần gọi sau | A, B (với simple tĩnh) | A | 200 | Thành công không chứng minh B đã bị loại |
| Sau khởi động lại B | A, B | B | 200 | Kiểm tra phục hồi |

Các giá trị target và outcome trong bảng là **tình huống minh họa**, không phải khẳng định thuật toán hay kết quả sẽ đúng theo từng dòng khi chạy thật.

### 9.3. Cách viết kết luận đúng mức

Kết luận phù hợp:

> “Trong lab dùng SimpleDiscoveryClient, dừng instance B không làm danh sách instance tĩnh tự cập nhật. Một số request được chọn vào B có thể thất bại; request chọn A vẫn có thể thành công. Chúng tôi phân biệt lỗi kết nối với việc lookup không tìm thấy service.”

Kết luận **không được phép** rút ra từ lab trên: “Spring Cloud registry tự động loại instance chết trong X giây” hoặc “load balancer chắc chắn sẽ chuyển toàn bộ request sang A”.

## 10. Ví dụ kiểm chứng có mã: quy tắc ở tầng ứng dụng

Dùng các test đơn vị để kiểm chứng quyết định trước khi chạy integration test. Ví dụ logic nghiệp vụ nên được tách khỏi HTTP client và registry để kiểm tra rõ.

Giả sử `InventoryGateway` là interface do ứng dụng tự định nghĩa:

~~~java
public interface InventoryGateway {
    StockResult lookup(String sku);
}

public record StockResult(String sku, int available) {}
~~~

Một service không cho phép đặt hàng nếu gateway báo không còn hàng:

~~~java
public class OrderDecisionService {
    private final InventoryGateway inventory;

    public OrderDecisionService(InventoryGateway inventory) {
        this.inventory = inventory;
    }

    public boolean canPlaceOrder(String sku, int requestedQuantity) {
        if (requestedQuantity <= 0) {
            return false;
        }
        StockResult stock = inventory.lookup(sku);
        return stock.available() >= requestedQuantity;
    }
}
~~~

Test JUnit 5 với fake gateway đơn giản, không cần Spring context:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class OrderDecisionServiceTest {
    @Test
    void acceptsOrderOnlyWhenStockIsSufficient() {
        InventoryGateway fake = sku -> new StockResult(sku, 3);
        OrderDecisionService service = new OrderDecisionService(fake);

        assertTrue(service.canPlaceOrder("SKU-1", 2));
        assertFalse(service.canPlaceOrder("SKU-1", 4));
        assertFalse(service.canPlaceOrder("SKU-1", 0));
    }
}
~~~

Test này xác minh **quy tắc về số lượng tồn kho**. Nó **không kiểm chứng discovery, HTTP, timeout, retry, telemetry hay khả năng chịu lỗi mạng**. Những phần đó cần integration/component test riêng:

- Giả lập discovery trả danh sách rỗng, 1 hoặc nhiều `ServiceInstance`.
- Cho HTTP server giả lập trả 200/500 hoặc phản hồi trễ.
- Xác minh chính sách retry và timeout với số attempt cụ thể.
- Nếu có giao dịch không idempotent, ghi nhận state ở phía đích để kiểm chứng không lặp tác dụng phụ.
- Xác minh instrumentation ghi được span và contextual log, nếu đó là một tiêu chí chất lượng của bài thử.

Khi tăng cấp kiểm thử, giữ một tên scenario và một định nghĩa outcome nhất quán để có thể đối chiếu kết quả giữa unit, integration và chạy nhiều instance.

## 11. Giám sát, cảnh báo và điều tra sự cố

Quan sát chỉ có ích khi giúp **phát hiện sự cố** và **quyết định bước tiếp theo**. Một bảng điều khiển cơ bản nên trình bày:

1. Lưu lượng, success/error rate và latency theo endpoint chính.
2. Latency và error rate theo dependency.
3. Tỉ lệ timeout/connection error và tổng số attempt do retry.
4. Số instance được discovery nhìn thấy so với trạng thái deployment/health khi có dữ liệu.
5. Thay đổi phiên bản ứng dụng, cấu hình và các sự kiện restart/rollout.

Khi dựng alert, ưu tiên triệu chứng ảnh hưởng người dùng và SLO thực tế. Ví dụ **error budget burn** hoặc tỉ lệ lỗi tăng liên tục trong cửa sổ đủ dài thường có ý nghĩa hơn một lần đơn lẻ bị lỗi. Cần tách lỗi test/health probe khỏi lưu lượng người dùng nếu chúng làm sai kết quả.

### Quy trình điều tra một lỗi chập chờn

- **Bước 1:** kiểm tra cửa sổ thời gian và xác nhận lỗi thật, lượng request và tỷ lệ lỗi.
- **Bước 2:** tìm request cụ thể theo trace ID hoặc request ID, so sánh request thành công và lỗi cùng endpoint.
- **Bước 3:** nhìn instance đích, thời lượng dependency span, status/exception, attempt.
- **Bước 4:** kiểm tra discovery, process/health, registry/cache, deployment và config revision cùng thời điểm.
- **Bước 5:** tái hiện trong môi trường kiểm soát với một thay đổi mỗi lần.
- **Bước 6:** đưa ra nguyên nhân có bằng chứng, tác động, giải pháp, phép test hồi quy và tín hiệu để phát hiện lần sau.

Nếu chỉ thấy HTTP 503 ở gateway, không vội kết luận inventory bị lỗi: 503 có thể do gateway, load balancer, discovery hoặc một tầng proxy trung gian trả về.

## 12. Những ngộ nhận và lỗi thực hành thường gặp

| Ngộ nhận | Điều cần kiểm tra lại |
| --- | --- |
| “HTTP 200 nghĩa là toàn bộ chuỗi nghiệp vụ đúng.” | Các tác dụng phụ, dữ liệu cuối cùng, thao tác bất đồng bộ và bất biến nghiệp vụ. |
| “Có log là đã đủ observability.” | Log có correlation/target chưa, metric cho biết mức ảnh hưởng không, trace nối xuyên service được không? |
| “Có `traceId` tức là trace hoàn chỉnh.” | Span bị thiếu do instrumentation, async, sampling hoặc context propagation. |
| “Health UP tức là chắc chắn có thể nhận request.” | Readiness, registry membership và trạng thái dependency. |
| “Timeout nghĩa là server chưa xử lý.” | Tình huống server xử lý xong nhưng response thất lạc; idempotency và reconciliation. |
| “Retry càng nhiều càng an toàn.” | Retry amplification, giới hạn attempt, backoff, deadline và tính an toàn nghiệp vụ. |
| “Registry trả instance tức là instance sống.” | Cache, heartbeat, độ trễ cập nhật, kết nối/health thực tế. |
| “Sửa file là bean lập tức nhận config mới.” | Nạp property source, `@RefreshScope`, instance được refresh, lúc bean tái tạo. |
| “Một lượt test PASS chứng minh hệ luôn chịu lỗi.” | Số mẫu, tốc độ tải, loại lỗi, topology và giả định môi trường. |
| “Đặt trace ID vào label metric sẽ dễ debug.” | Cardinality cao; dùng exemplar/log/trace linking nếu hệ quan sát hỗ trợ. |

## 13. Bài thực hành tổng hợp: lập hồ sơ bằng chứng

Với mini-system `order-service` và `inventory-service`, tạo một **hồ sơ kiểm chứng** gồm các phần sau.

### A. Sơ đồ và trạng thái baseline

Ghi topology, phiên bản, số instance, cách cấu hình discovery, các endpoint và timeout/retry. Ghi kèm thành phần quan sát đang cài: Actuator, logging, metrics, tracing. Xác định chỗ nào telemetry chưa được bật và giới hạn từ đó.

### B. Ba giả thuyết cần thử

1. **Discovery:** “khi danh sách instance rỗng, caller trả lỗi có kiểm soát mà không gọi sai URI”.
2. **Network:** “khi dependency chậm vượt timeout, caller kết thúc request theo chính sách và ghi đủ context”.
3. **Config:** “sau refresh được hỗ trợ trên instance A, bean thuộc scope phù hợp trả giá trị cấu hình mới; instance B không tự nhiên có cùng revision nếu chưa được cập nhật”.

Có thể thêm giả thuyết về registry hội tụ, nhưng chỉ khi lab sử dụng registry động.

### C. Kết quả thử nghiệm

Với từng giả thuyết, lưu:

~~~text
Scenario ID:
Versions: JDK / Spring Boot / Spring Cloud release train
Topology: service + instance + ports + discovery provider
Baseline: metric / health / config revision
Stimulus: thời điểm, cách gây lỗi hoặc thay đổi
Expected: một assertion hành vi đo được
Observed: số request, outcome, latency, instance, thời lượng
Evidence: log correlation ID, trace ID, metric window, test assertion
Result: PASS / FAIL / INCONCLUSIVE
Limitations: điều chưa đo, cache/sampling/clock skew, phạm vi môi trường
Cleanup: trạng thái sau khôi phục
~~~

Dùng **INCONCLUSIVE** khi phép đo không đủ để phân biệt các giả thuyết; không ép thành PASS chỉ vì không thấy lỗi.

### D. Tiêu chí chấm hoàn thành

- [ ] Giải thích được vai trò của logs, metrics, traces và health/readiness trong điều tra.
- [ ] Có request ID hoặc trace ID kết nối các sự kiện quan trọng, kèm bằng chứng về giới hạn sampling/propagation.
- [ ] Quan sát được danh sách `ServiceInstance` và instance đích của lời gọi.
- [ ] Phân biệt được lỗi discovery, lỗi kết nối, timeout và HTTP response lỗi.
- [ ] Có ít nhất một tình huống lỗi từng phần được tái hiện, với expected/observed rõ ràng.
- [ ] Kiểm chứng được thời điểm cấu hình có hiệu lực trước/sau refresh trên từng instance liên quan.
- [ ] Phân biệt metric theo user request với metric theo attempt khi bật retry.
- [ ] Có assertion nghiệp vụ, không chỉ assertion về tình trạng HTTP hoặc sự tồn tại của log.
- [ ] Có giới hạn thí nghiệm và cách lặp lại kết quả, không khẳng định vượt quá bằng chứng.
- [ ] Các endpoint/telemetry quan sát được giới hạn truy cập và không tiết lộ dữ liệu nhạy cảm.

## 14. Khi nào chuyển sang chủ đề tiếp theo?

Có thể bắt đầu đào sâu từng công nghệ như registry provider, Spring Cloud LoadBalancer, Spring Cloud Config, resiliency hoặc tracing backend khi đã trả lời được bốn câu hỏi về bất kỳ request liên dịch vụ nào:

1. **Đi qua đâu?** Service ID, danh sách instance đã biết, instance được chọn và đường đi request.
2. **Đã xảy ra gì?** Response/status, thời lượng, lỗi, retry và trạng thái nghiệp vụ.
3. **Vì sao tin kết luận này?** Log, metric, trace, trạng thái nguồn và thử nghiệm đối chứng.
4. **Giới hạn của bằng chứng?** Sampling, cache, clock skew, quy mô thử, phiên bản và loại lỗi chưa thử.

**Tài liệu đối chiếu khi triển khai:** hướng dẫn chính thức của Spring Boot về Actuator, Micrometer/Observability và externalized configuration; hướng dẫn Spring Cloud Commons, Context, LoadBalancer và service discovery của **release train đang dùng**; tài liệu registry/HTTP client/telemetry backend được chọn. Ưu tiên xác thực tên API và thuộc tính cấu hình theo bộ phiên bản thực tế trước khi chuyển ví dụ khái niệm thành cấu hình production.
