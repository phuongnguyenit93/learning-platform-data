# Quan hệ với Service Discovery, cân bằng tải và instance bị lỗi

## Mục tiêu của bài học

Trong hệ thống nhiều instance, một lời gọi đến inventory-service thường không đi đến một máy chủ cố định. Service Discovery cung cấp danh sách instance, Spring Cloud LoadBalancer chọn một instance cho từng lần gọi, còn circuit breaker quyết định có cho phép lời gọi logic tiếp tục dựa trên kết quả gần đây.

Khi một instance bị lỗi, ba cơ chế có thể phản ứng ở những thời điểm khác nhau. Registry có thể chưa kịp loại instance; LoadBalancer có thể vẫn chọn nó; circuit breaker có thể ghi nhận lỗi sau khi request thất bại. Nếu không phân biệt phạm vi của từng cơ chế, nhóm phát triển dễ mở breaker cho cả dịch vụ chỉ vì một instance lỗi, hoặc kỳ vọng LoadBalancer tự loại instance ngay sau một response 5xx.

Sau bài học, bạn có thể:

- Mô tả đường đi của request từ client qua Service Discovery, LoadBalancer và circuit breaker đến instance được chọn.
- Phân biệt trạng thái đăng ký/health của instance với kết quả của một lời gọi từ xa.
- Hiểu phạm vi breaker theo dịch vụ hoặc thao tác và giới hạn của breaker theo instance.
- Chọn cách xử lý khi một instance lỗi, nhiều instance lỗi hoặc registry không còn instance khả dụng.
- Kết hợp health check, retry, timeout, circuit breaker và fallback mà không tạo vòng lặp tải.
- Thiết kế log, metric và bài kiểm thử để xác định đúng instance gây lỗi.

## 1. Ba cơ chế cùng tham gia một lời gọi

Giả sử order-service cần đọc tồn kho từ inventory-service. Trong môi trường triển khai, inventory-service có ba instance. Ứng dụng gọi bằng service ID thay vì địa chỉ IP cụ thể.

Đường đi logic có thể hình dung:

    order-service
        |
        v
    InventoryGateway / Feign client
        |
        v
    CircuitBreaker: inventory-read
        |
        v
    Spring Cloud LoadBalancer
        |
        v
    ServiceInstanceListSupplier
        |
        +---- chọn instance A ----> inventory-service A
        |
        +---- chọn instance B ----> inventory-service B
        |
        +---- chọn instance C ----> inventory-service C

Mỗi thành phần có trách nhiệm riêng:

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Service Discovery | Những instance nào đã được đăng ký cho service ID này? | Registry trả về A, B và C. |
| Health check / readiness | Instance nào được xem là đủ điều kiện nhận traffic? | Instance B chưa ready nên bị loại khỏi danh sách phù hợp. |
| LoadBalancer | Trong các instance có thể chọn, request này đi đến đâu? | Chọn A theo thuật toán và trạng thái hiện tại. |
| CircuitBreaker | Có nên cho phép lời gọi logic mới đến phụ thuộc không? | Từ chối nhanh lời gọi khi breaker inventory-read đang OPEN. |
| Retry | Khi một attempt thất bại, có nên thử lại và chọn đích khác không? | Thử tối đa một instance khác trong ngân sách request. |

Discovery và health check quản lý khả năng được chọn của instance. LoadBalancer chọn đích cho request. Circuit breaker bảo vệ lời gọi logic trước hoặc quanh quá trình gọi tùy cách tích hợp. Retry quyết định có thực hiện thêm attempt hay không. Không cơ chế nào tự thay thế toàn bộ các cơ chế còn lại.

## 2. Service Discovery biết instance qua đăng ký và trạng thái

Một instance thường đăng ký địa chỉ, cổng, service ID và metadata với registry khi khởi động. Registry hoặc nền tảng điều phối cập nhật trạng thái qua heartbeat, health check, đăng ký/hủy đăng ký hoặc cơ chế tương ứng.

Vòng đời điển hình:

1. Instance khởi động và đăng ký với service registry.
2. Instance hoàn tất khởi tạo, trở nên ready để nhận traffic.
3. Registry hoặc discovery client cung cấp instance cho LoadBalancer.
4. Khi instance dừng hoặc không còn khỏe, trạng thái đăng ký được cập nhật hoặc instance bị loại khỏi danh sách có thể chọn.
5. Instance phục hồi và đăng ký/được đánh dấu ready trở lại.

Việc cập nhật không phải lúc nào cũng tức thời. Registry có thể còn dữ liệu cũ trong một khoảng thời gian; heartbeat có chu kỳ; cache danh sách instance có thể chưa được làm mới. Vì vậy, một instance đã chết vẫn có thể xuất hiện trong danh sách mà LoadBalancer nhìn thấy.

Cần phân biệt ba trạng thái:

- **Registered:** registry biết địa chỉ của instance.
- **Ready/healthy:** instance đã vượt qua tiêu chí sẵn sàng để nhận traffic.
- **Request succeeded:** một lời gọi cụ thể đến instance đã hoàn tất thành công.

Một instance có thể đã đăng ký nhưng chưa sẵn sàng. Một instance có thể được đánh dấu healthy nhưng một request riêng lẻ vẫn thất bại do lỗi dữ liệu, timeout hoặc lỗi tạm thời. Ngược lại, một request thành công không chứng minh instance luôn khỏe mạnh.

Với Kubernetes, readiness probe thường quyết định Pod có được đưa vào endpoint phục vụ traffic hay không; liveness probe phục vụ phát hiện tiến trình cần được khởi động lại. Không dùng liveness thay cho readiness: một ứng dụng còn sống nhưng chưa sẵn sàng vẫn có thể gây lỗi cho request nếu được đưa vào danh sách nhận traffic.

## 3. LoadBalancer chọn instance từ danh sách có thể dùng

Spring Cloud LoadBalancer nhận danh sách ServiceInstance từ discovery client hoặc ServiceInstanceListSupplier, sau đó áp dụng chiến lược chọn instance. Tùy cấu hình, chiến lược có thể phân phối tuần tự, ngẫu nhiên hoặc dùng chính sách khác.

Điều cần nhớ:

- LoadBalancer chỉ có thể chọn từ danh sách mà supplier cung cấp.
- Nếu danh sách chứa instance đã chết, thuật toán vẫn có thể chọn instance đó.
- Nếu registry trả danh sách rỗng, lời gọi không có đích để gửi và có thể thất bại trước khi tạo được HTTP request.
- Một lần chọn instance không tự tạo ra lịch sử failure rate để quyết định ngắt mạch.
- Health check hoặc bộ lọc instance cần được cấu hình riêng nếu muốn loại các instance không khỏe khỏi danh sách.

Ví dụ cấu hình một Feign client theo service ID:

    @FeignClient(name = "inventory-service")
    public interface InventoryClient {

        @GetMapping("/inventory/{sku}")
        InventoryResponse find(@PathVariable("sku") String sku);
    }

Khi không cấu hình URL cố định, OpenFeign có thể dùng Spring Cloud LoadBalancer để chọn instance của inventory-service. Tên service ID phải khớp với tên được đăng ký trong registry.

Nếu đặt URL cụ thể trên Feign client hoặc cấu hình URL cố định cho client, đường gọi có thể bỏ qua lựa chọn instance theo service ID. Circuit breaker vẫn có thể bảo vệ lời gọi Feign, nhưng bài kiểm thử không còn xác minh được Service Discovery và LoadBalancer.

## 4. Circuit breaker thường bảo vệ lời gọi logic, không tự động bảo vệ từng IP

Trong tích hợp phổ biến, circuit breaker được tạo theo tên client hoặc thao tác, ví dụ inventory-read. LoadBalancer thực hiện lựa chọn instance bên trong lời gọi được bảo vệ. Do đó, nhiều instance có thể đóng góp kết quả vào cùng một sliding window của breaker.

Ví dụ:

    inventory-read
        |
        +-- request 1 --> instance A --> success
        +-- request 2 --> instance B --> connection error
        +-- request 3 --> instance C --> success
        +-- request 4 --> instance B --> timeout
        +-- request 5 --> instance A --> success

Breaker inventory-read nhìn thấy kết quả của lời gọi logic theo phạm vi mà integration bọc. Nó không mặc định có một trạng thái riêng cho A, B và C. Nếu B liên tục lỗi nhưng A và C khỏe, lỗi của B vẫn có thể làm tăng failure rate chung; tuy nhiên, hai instance khỏe có thể khiến tỷ lệ tổng chưa vượt ngưỡng mở.

Điều này dẫn đến hai hệ quả:

- Một breaker OPEN cho inventory-read không chứng minh tất cả instance inventory-service đều lỗi.
- Một instance lỗi không đảm bảo breaker sẽ mở ngay, vì quyết định còn phụ thuộc số mẫu, sliding window, failure rate, slow call rate và kết quả từ những instance khác.

Đừng dùng trạng thái breaker như nguồn duy nhất để quyết định instance nào cần bị loại khỏi registry. Breaker trả lời câu hỏi về lời gọi logic; health check và LoadBalancer quản lý khả năng chọn instance.

## 5. Điều gì xảy ra khi chỉ một instance bị lỗi?

Giả sử inventory-service có ba instance A, B và C. A và C khỏe mạnh, còn B từ chối kết nối.

| Tình huống | Discovery / LoadBalancer | Circuit breaker theo service |
| --- | --- | --- |
| B vẫn còn trong registry | B có thể tiếp tục được chọn. | Các request đến B thất bại và đóng góp vào thống kê chung. |
| B đã bị loại khỏi danh sách | LoadBalancer chỉ chọn A và C. | Các request mới có thể thành công; breaker dần phản ánh các kết quả mới theo sliding window. |
| B lỗi không thường xuyên | B có thể tiếp tục được chọn tùy thuật toán. | Failure rate có thể chưa đạt ngưỡng mở. |
| B lỗi liên tục, A và C vẫn khỏe | LoadBalancer vẫn có thể phân phối đến cả ba nếu không có health filter. | Breaker chung có thể mở nếu tỷ lệ lỗi tổng hợp vượt ngưỡng. |
| A, B và C đều không khả dụng | Không có đích khỏe để chọn hoặc mọi attempt đều lỗi. | Breaker có thể mở sau khi đủ mẫu; trước đó request vẫn phải chịu timeout/lỗi. |

Nếu chỉ một instance lỗi, giải pháp thường cần xử lý ở tầng health/discovery hoặc retry có giới hạn để tránh tiếp tục gửi request đến instance đó. Circuit breaker cấp dịch vụ vẫn hữu ích để bảo vệ khi phần lớn hoặc toàn bộ lời gọi đang suy giảm, nhưng không phải bộ lọc outlier per-instance tự động.

Nếu hệ thống cần phát hiện và cô lập một instance lỗi riêng, cần một cơ chế health check hoặc outlier detection có hiểu biết về instance. Không giả định rằng một lỗi HTTP 500 sẽ tự động làm registry hủy đăng ký instance.

## 6. Health check và danh sách instance có thể dùng

Spring Cloud LoadBalancer hỗ trợ mở rộng nguồn danh sách instance thông qua ServiceInstanceListSupplier. Có thể kết hợp discovery với bộ lọc hoặc health-check supplier để chỉ cung cấp instance đáp ứng điều kiện kiểm tra.

Một số điểm cần thiết kế:

- Chọn health endpoint phù hợp, thường là endpoint readiness hoặc endpoint kiểm tra khả năng phục vụ request.
- Đặt chu kỳ kiểm tra và timeout hợp lý; kiểm tra quá dày có thể tạo tải phụ.
- Xác định thời gian phát hiện instance lỗi và thời gian đưa instance trở lại danh sách.
- Tránh health check phụ thuộc vào chính dịch vụ đang được kiểm tra theo cách tạo vòng lặp.
- Không đưa instance trở lại ngay sau một lần health check thành công nếu dịch vụ vẫn chưa ổn định.
- Theo dõi số instance được discovery trả về và số instance còn lại sau bộ lọc.

Health check định kỳ có độ trễ phát hiện. Nếu một instance bắt đầu lỗi ngay sau lần kiểm tra thành công, một số request vẫn có thể được gửi đến nó trước lần kiểm tra tiếp theo. Vì vậy, health check không thay thế timeout và retry có giới hạn.

Với Kubernetes, readiness probe và endpoint service thường là cơ chế chính để điều khiển Pod có nhận traffic hay không. Với Eureka, Consul hoặc registry khác, discovery client có cách cập nhật trạng thái và cache riêng. Hãy dùng cơ chế phù hợp với nền tảng đang triển khai và kiểm tra độ trễ cập nhật thực tế.

## 7. Kết hợp retry với LoadBalancer và circuit breaker

Retry có thể hữu ích khi một instance cụ thể lỗi nhưng còn instance khác khỏe mạnh. Một attempt thất bại có thể được thử lại trên instance khác trong cùng ngân sách request.

Ví dụ luồng:

    Logical call: inventory-read
        |
        v
    Attempt 1 -> instance B -> connection failure
        |
        v
    Retry policy (còn attempt và còn deadline?)
        |
        v
    Attempt 2 -> instance C -> success
        |
        v
    Logical result: success

Nếu retry nằm bên trong ranh giới breaker, breaker có thể quan sát kết quả cuối cùng của logical call thay vì từng attempt. Khi đó, một request có một attempt lỗi nhưng retry thành công có thể được ghi nhận là thành công ở cấp breaker. Cách composition cụ thể phụ thuộc thứ tự tích hợp và phiên bản; hãy kiểm tra bằng log, event và thử nghiệm.

Khi cấu hình retry:

- Giới hạn số lần thử trên cùng instance và số lần chuyển sang instance khác.
- Giữ tổng thời gian retry trong deadline của request.
- Chỉ retry lỗi có khả năng phục hồi, chẳng hạn lỗi kết nối tạm thời.
- Không retry mọi lỗi 4xx; nhiều lỗi là kết quả nghiệp vụ hoặc xác thực.
- Cẩn trọng với request ghi dữ liệu như reserve, create hoặc payment.
- Dùng idempotency key hoặc mã thao tác khi retry có thể lặp tác dụng phụ.
- Tránh retry ở nhiều tầng cùng lúc vì số attempt có thể nhân lên.

Nếu không có instance nào trong registry, retry không thể tạo ra một đích hợp lệ. Lặp lại cùng request khi danh sách rỗng chỉ làm tăng độ trễ. Trong trường hợp đó, trả lỗi hoặc fallback theo hợp đồng nghiệp vụ và để breaker ghi nhận lỗi nếu exception được phân loại là lỗi phụ thuộc.

## 8. Phân biệt các nguyên nhân thất bại

Không phải mọi lỗi đều có cùng ý nghĩa. Khi xử lý fallback hoặc điều chỉnh breaker, hãy phân loại theo tầng:

| Nguyên nhân | Tầng phát sinh | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy instance phù hợp | Discovery / LoadBalancer | Kiểm tra registry, service ID, readiness và danh sách instance. |
| Connection refused | Kết nối đến instance | Kiểm tra tiến trình, cổng, network policy và trạng thái đăng ký. |
| HTTP 5xx | Ứng dụng instance | Kiểm tra log phía server và tỷ lệ lỗi theo instance. |
| HTTP 4xx | Hợp đồng/API hoặc nghiệp vụ | Xử lý theo status và request; không mặc định coi là lỗi sức khỏe. |
| Read timeout | HTTP client / instance chậm | Kiểm tra latency, timeout, tải và slow-call rate. |
| CallNotPermittedException | Circuit breaker | Breaker đang OPEN hoặc không cho phép lời gọi; không có attempt HTTP mới. |
| BulkheadFullException | Bulkhead | Hết permit hoặc tài nguyên concurrency; không đồng nghĩa registry không có instance. |

Với Feign, exception từ LoadBalancer hoặc HTTP client có thể được bọc trong exception khác. Hãy xem cause chain và log ở tầng client để xác định nguyên nhân. Không chỉ so khớp message vì message có thể thay đổi theo phiên bản.

Fallback nên phân biệt ít nhất các tình huống chính:

- Breaker OPEN: lời gọi mới bị chặn; có thể trả cache hoặc trạng thái unavailable.
- Không có instance: phụ thuộc không thể được định tuyến; kiểm tra discovery và phản hồi theo hợp đồng.
- Một attempt timeout nhưng retry thành công: trả kết quả chính nếu logical call đã thành công.
- Tất cả attempt thất bại: fallback hoặc truyền lỗi theo nghiệp vụ.
- Lỗi validation/authorization: truyền lỗi phù hợp, không che bằng fallback dữ liệu.

Không trả quantity = 0 hoặc xác nhận giữ hàng thành công khi hệ thống chỉ biết rằng phụ thuộc không phản hồi. Dữ liệu fallback cần biểu diễn trạng thái UNKNOWN, UNAVAILABLE hoặc PENDING rõ ràng.

## 9. Khi nào cần breaker riêng cho từng instance?

Breaker theo service/method thường là lựa chọn đơn giản và dễ vận hành. Nó giới hạn số breaker, dễ cấu hình và phản ánh sức khỏe của logical dependency. Nhưng nó không cô lập thống kê theo từng địa chỉ instance.

Nếu cần breaker per-instance, thiết kế phải lấy được danh tính instance sau khi LoadBalancer chọn đích. Khi đó, mỗi breaker cần được gắn với một instance key ổn định, ví dụ service ID kết hợp instance ID, thay vì tạo key theo request.

Thiết kế per-instance có thêm chi phí:

- Số lượng breaker thay đổi theo số instance và có thể tăng/giảm động.
- Cần xóa hoặc thu hồi breaker khi instance bị deregister để tránh giữ trạng thái cũ.
- Cần giới hạn số instance và quản lý vòng đời registry.
- Metric theo instance có thể tăng cardinality.
- Một instance mới có thể chưa đủ mẫu để breaker đánh giá.
- Cần xác định cách phối hợp breaker per-instance với retry và health check.

Spring Cloud CircuitBreaker không nên được giả định là tự động tạo breaker riêng cho từng ServiceInstance chỉ vì ứng dụng dùng LoadBalancer. Nếu cần hành vi đó, phải xây tích hợp có chủ đích quanh bước chọn instance hoặc client riêng cho từng instance và kiểm thử vòng đời đầy đủ.

Trong nhiều hệ thống, health check hoặc bộ lọc instance là nơi phù hợp hơn để loại một instance rõ ràng bị lỗi. Breaker cấp service tiếp tục bảo vệ khi lời gọi tổng thể đến dịch vụ suy giảm. Chỉ triển khai breaker per-instance khi dữ liệu vận hành chứng minh rằng việc cô lập theo instance mang lại lợi ích đáng kể.

## 10. Ví dụ bảo vệ lời gọi LoadBalanced bằng Spring Cloud CircuitBreaker

Với một ứng dụng dùng RestClient có LoadBalancer, có thể tạo builder được đánh dấu @LoadBalanced:

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder
            .baseUrl("http://inventory-service")
            .build();
    }

Tên inventory-service là service ID. LoadBalancer sẽ chọn instance khi request được thực hiện.

Có thể bọc thao tác gọi trong CircuitBreakerFactory:

    @Service
    public class InventoryGateway {

        private final RestClient inventoryClient;
        private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public InventoryGateway(
                RestClient inventoryRestClient,
                CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryRestClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public InventoryResponse find(String sku) {
            return circuitBreakerFactory.create("inventory-read").run(
                () -> inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class),
                error -> InventoryResponse.unknown(sku)
            );
        }
    }

Ví dụ này minh họa một breaker ở ranh giới logical call. RestClient được LoadBalancer chọn instance ở bên trong Supplier. InventoryResponse.unknown là kết quả do ứng dụng định nghĩa và phải được tầng nghiệp vụ hiểu là chưa xác định tồn kho.

Nếu dùng OpenFeign đã bật tích hợp CircuitBreaker tự động, không bọc cùng một Feign method thêm lần nữa bằng CircuitBreakerFactory nếu không có chủ đích rõ ràng. Tránh tạo hai lớp breaker lồng nhau vì chúng có thể ghi nhận kết quả và fallback khác nhau, làm khó chẩn đoán.

## 11. Theo dõi theo cả service ID và instance

Để hiểu một breaker mở vì một instance hay vì cả dịch vụ, cần quan sát cả logical call và instance được chọn.

Những dữ liệu nên thu thập:

- Service ID và breaker name.
- Instance ID hoặc địa chỉ đích đã được chọn, trong log hoặc trace.
- Kết quả HTTP và loại exception.
- Thời gian kết nối, thời gian phản hồi và tổng thời gian logical call.
- Số attempt, instance được chọn ở từng attempt và kết quả retry.
- Số instance registered, healthy và có thể chọn.
- Trạng thái breaker, transition, failure rate, slow call rate và số lời gọi bị từ chối.
- Số lần fallback theo nguyên nhân.

Một dashboard có thể tách hai góc nhìn:

| Góc nhìn | Chỉ số |
| --- | --- |
| Logical service | Breaker state, tổng request, failure rate, slow call rate, not-permitted, fallback. |
| Instance | Request theo instance, tỷ lệ lỗi, latency, health/readiness và số lần bị chọn sau lỗi. |

Nếu chỉ nhìn breaker inventory-read, có thể thấy tỷ lệ lỗi tăng nhưng không biết instance nào gây ra. Nếu chỉ nhìn instance health, có thể bỏ lỡ tình trạng mọi instance đều chậm ở mức chưa bị health check loại bỏ.

Không gắn request ID, SKU hoặc exception message vào metric tag. Instance ID có số lượng hữu hạn theo quy mô triển khai thường có thể dùng trong log/trace; với metric, cần cân nhắc cardinality và vòng đời instance. Dùng correlation ID để nối log của caller, LoadBalancer và server khi điều tra.

## 12. Kiểm thử các tình huống instance lỗi

Tạo inventory-service với ba instance A, B và C. Mỗi instance ghi instance ID trong log hoặc trả metadata chỉ dùng ở môi trường test. Thực hiện các trường hợp:

| Bài kiểm thử | Cách tạo tình huống | Điều cần xác nhận |
| --- | --- | --- |
| Một instance dừng đột ngột | Dừng B nhưng giữ B trong registry đủ lâu để mô phỏng dữ liệu cũ. | LoadBalancer có thể chọn B trước khi registry cập nhật; request lỗi được ghi nhận. |
| Instance chưa ready | Cho B khởi động nhưng readiness chưa đạt. | B không nên được đưa vào danh sách nhận traffic nếu discovery/health integration đã cấu hình đúng. |
| Một instance trả 5xx | Cấu hình B trả lỗi, A và C trả thành công. | Quan sát phân phối, retry, lỗi theo instance và failure rate của breaker chung. |
| Một instance phản hồi chậm | Cho B trì hoãn response vượt slow-call threshold hoặc timeout. | Đo latency, timeout và slow-call rate. |
| Tất cả instance dừng | Dừng A, B và C hoặc làm danh sách discovery rỗng. | Không có đích; kiểm tra exception, breaker và fallback. |
| Instance phục hồi | Khởi động lại B và cho readiness đạt. | B chỉ được chọn lại khi danh sách instance cập nhật theo cơ chế đã cấu hình. |
| Breaker OPEN | Tạo đủ lỗi để breaker mở. | Request bị từ chối trước khi tạo attempt mới đến instance; LoadBalancer không thể chọn đích cho lời gọi đã bị chặn. |

Trong mỗi bài kiểm thử, ghi lại service ID, instance được chọn, số attempt, exception, breaker transition và thời điểm registry cập nhật. Đừng chỉ dựa vào response cuối cùng vì retry hoặc fallback có thể che mất lỗi của attempt đầu.

## 13. Bài thực hành tổng hợp

Xây dựng order-service gọi inventory-service với Service Discovery, Spring Cloud LoadBalancer và Spring Cloud CircuitBreaker:

1. Đăng ký ít nhất ba instance inventory-service trong registry hoặc cấu hình test discovery.
2. Tạo client dùng service ID, không gắn URL cố định.
3. Bật circuit breaker ở ranh giới inventory-read và cấu hình sliding window cùng timeout.
4. Xác nhận LoadBalancer chọn nhiều instance khi tất cả đều healthy.
5. Làm một instance lỗi và giữ nó trong danh sách trong một khoảng ngắn để quan sát hành vi với registry stale.
6. Bật health/readiness integration hoặc cơ chế loại instance phù hợp; xác nhận instance lỗi bị loại khỏi lựa chọn sau khi trạng thái cập nhật.
7. Thêm retry giới hạn một lần sang instance khác và đo số attempt thực tế.
8. Tạo lỗi trên toàn bộ instance để breaker đạt ngưỡng OPEN.
9. Trong lúc OPEN, xác nhận request bị từ chối nhanh và fallback phản ánh đúng trạng thái không xác định.
10. Phục hồi các instance và quan sát HALF_OPEN, sau đó CLOSED.
11. So sánh metric logical service với log theo instance để xác định breaker đang phản ánh lỗi cục bộ hay suy giảm toàn dịch vụ.

Khi hoàn thành, bạn cần giải thích được registry quản lý danh sách instance, health check quyết định khả năng nhận traffic, LoadBalancer chọn đích và circuit breaker bảo vệ logical call. Bạn cũng cần nêu được vì sao breaker mặc định không tự cô lập từng IP, khi nào retry có ích và vì sao phải kiểm tra cả trạng thái registry lẫn kết quả request.

## Tài liệu tham khảo

- Spring Cloud LoadBalancer Reference: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-loadbalancer.html
- Spring Cloud CircuitBreaker Reference: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker.html
- Spring Cloud OpenFeign Reference: https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html

