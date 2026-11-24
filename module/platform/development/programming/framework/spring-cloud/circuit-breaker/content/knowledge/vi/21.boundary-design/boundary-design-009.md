# Giới hạn Circuit Breaker cục bộ so với bảo vệ toàn hệ thống

Circuit breaker trong Spring Cloud thường bảo vệ một lời gọi từ một ứng dụng tới một dependency cụ thể. Với Resilience4j, trạng thái và sliding window được giữ trong instance circuit breaker của tiến trình đang chạy. Khi ứng dụng được triển khai thành nhiều pod hoặc nhiều máy, mỗi tiến trình thường có breaker và thống kê riêng. Vì vậy, một breaker chuyển sang `OPEN` chỉ chặn các lời gọi đi qua instance đó; nó không tự động mở breaker ở các replica khác và cũng không tạo ra một chính sách bảo vệ toàn hệ thống.

Phân biệt phạm vi này rất quan trọng khi thiết kế hệ thống phân tán. Circuit breaker cục bộ giúp một caller ngừng tiếp tục gây áp lực lên dependency mà nó đang quan sát thấy lỗi. Bảo vệ toàn hệ thống cần thêm những cơ chế có phạm vi rộng hơn như giới hạn lưu lượng, admission control, load shedding, quota dùng chung, chính sách tại gateway hoặc service mesh và giới hạn tài nguyên ở chính dependency.

## 1. Circuit breaker bảo vệ một ranh giới lời gọi

Hãy xem Order Service gọi Inventory Service. Ở phía Order Service, circuit breaker thường bọc lời gọi HTTP hoặc RPC tới Inventory Service. Breaker ghi nhận kết quả của lời gọi đó, tính failure rate và slow-call rate trong sliding window, rồi quyết định có cho phép lời gọi tiếp theo đi qua hay không.

```text
Order Service
  └── InventoryClient
        └── CircuitBreaker("inventory")
              └── HTTP/RPC request
                    └── Inventory Service
```

Phạm vi bảo vệ là đường gọi từ Order Service tới Inventory Service. Breaker không tự bảo vệ các đường gọi khác như Order Service tới Payment Service, cũng không tự quản lý request trực tiếp từ một ứng dụng khác tới Inventory Service.

Trong ứng dụng có nhiều dependency, nên tạo breaker riêng cho từng ranh giới cần bảo vệ. Ví dụ `inventory`, `payment` và `shipping` có lưu lượng, độ trễ, mức độ quan trọng và chính sách fallback khác nhau. Dùng một breaker chung cho tất cả dependency có thể khiến lỗi của một hệ thống ảnh hưởng quyết định cho các hệ thống còn lại.

## 2. Trạng thái của Resilience4j thường nằm trong từng tiến trình

Với cấu hình Resilience4j trong Spring Boot, registry quản lý các breaker trong bộ nhớ của ứng dụng. Ví dụ:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

Mỗi tiến trình Spring Boot nạp cấu hình và tạo breaker `inventory` của riêng nó. Cấu hình có thể giống nhau giữa các pod, nhưng lịch sử lời gọi, trạng thái hiện tại và số liệu cửa sổ không tự chia sẻ giữa các pod.

Ví dụ một deployment có ba replica:

```text
                 Order Service
          +-----------+-----------+
          |           |           |
       Pod A        Pod B        Pod C
       breaker      breaker      breaker
      inventory    inventory    inventory
       CLOSED        OPEN        CLOSED
          |           X           |
          +-----------+-----------+
                      |
                      v
               Inventory Service
```

Nếu Pod B quan sát thấy lỗi đủ ngưỡng, breaker của Pod B chuyển sang `OPEN`. Pod A và Pod C vẫn có thể ở `CLOSED` và tiếp tục gửi request. Đây là hành vi bình thường của circuit breaker cục bộ, không phải lỗi đồng bộ trạng thái.

Có thể lấy breaker từ registry được Spring quản lý:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryProtection {

    private final CircuitBreaker inventoryBreaker;

    public InventoryProtection(CircuitBreakerRegistry registry) {
        this.inventoryBreaker = registry.circuitBreaker("inventory");
    }

    public CircuitBreaker.State state() {
        return inventoryBreaker.getState();
    }
}
```

Registry này thuộc application context của tiến trình hiện tại. Không nên tạo một registry mới trong mỗi request hoặc cho rằng cùng tên breaker có nghĩa là cùng trạng thái trên mọi máy.

## 3. Vì sao breaker cục bộ vẫn có ích?

Dù không điều khiển toàn bộ cluster, breaker cục bộ vẫn giảm áp lực đáng kể:

- Một replica phát hiện dependency lỗi có thể ngừng gửi thêm request từ replica đó.
- Thread, connection và thời gian xử lý của caller được giải phóng nhanh hơn khi breaker từ chối lời gọi mới.
- Fallback có thể giữ một phần chức năng đọc hoặc trả lỗi có kiểm soát.
- Khi dependency phục hồi, `HALF_OPEN` cho phép một số probe từ caller đó trước khi gửi lại toàn bộ lưu lượng.
- Số liệu theo từng instance giúp xác định replica nào quan sát thấy lỗi và thời điểm breaker chuyển trạng thái.

Breaker cục bộ hoạt động tốt nhất khi đặt ngay tại ranh giới gọi dependency và kết hợp timeout, bulkhead cùng chính sách retry phù hợp. Nó không thay thế giới hạn lưu lượng hoặc khả năng chịu tải của dependency.

## 4. Tác động khi hệ thống có nhiều replica

Giả sử Order Service có 10 pod, mỗi pod cho phép tối đa ba probe trong `HALF_OPEN`. Nếu cả 10 breaker cùng chuyển sang `HALF_OPEN` gần như đồng thời, hệ thống có thể phát sinh tối đa khoảng 30 probe trong một đợt, tùy cách phân phối request và thời điểm chuyển trạng thái.

Điều đó có thể phù hợp với dependency có đủ năng lực, nhưng cũng có thể tạo một đợt tải tăng đột ngột khi dịch vụ vừa phục hồi. `permittedNumberOfCallsInHalfOpenState` là giới hạn ở từng breaker instance, không mặc nhiên là giới hạn tổng cho toàn bộ deployment.

Một số hệ quả cần tính đến:

| Tình huống | Hệ quả của trạng thái cục bộ | Cách xử lý bổ sung |
| --- | --- | --- |
| Một pod gặp lỗi mạng riêng | Chỉ pod đó có thể mở breaker; pod khác vẫn gọi được | Theo dõi metric theo instance và kiểm tra network/pod health |
| Dependency lỗi trên toàn cluster | Các pod sẽ mở breaker theo số liệu và thời điểm riêng | Kết hợp giới hạn lưu lượng ở gateway, mesh hoặc dependency |
| Nhiều pod chuyển sang `HALF_OPEN` cùng lúc | Tổng số probe có thể bằng tổng permit của các pod | Dùng giới hạn tải tại dependency, rollout phục hồi có kiểm soát hoặc probe policy ở lớp rộng hơn |
| Một pod mới khởi động | Breaker mới thường chưa có lịch sử lỗi | Không xem trạng thái `CLOSED` của pod mới là bằng chứng dependency khỏe |
| Pod bị thay thế hoặc restart | Trạng thái và cửa sổ trong bộ nhớ bị tạo lại | Dùng metric/log tập trung để giữ lịch sử vận hành ngoài vòng đời pod |

Không nên chỉ tăng `waitDurationInOpenState` để xử lý mọi vấn đề nhiều replica. Thời gian mở dài có thể giảm tần suất probe nhưng cũng kéo dài thời gian một pod không thử lại dependency sau khi nó đã phục hồi. Cần chọn giá trị dựa trên thời gian phục hồi và khả năng chịu probe của hệ thống.

## 5. Bảo vệ toàn hệ thống cần nhiều lớp

Một hệ thống có thể phối hợp nhiều cơ chế ở các ranh giới khác nhau:

```text
Client
  |
  v
API Gateway
  - Authentication / quota
  - Rate limit / admission control
  - Load shedding
  |
  v
Order Service replicas
  - Local Bulkhead
  - Local Circuit Breaker
  - Local Timeout / Retry policy
  |
  v
Service Mesh / Load Balancer
  - Routing / outlier detection
  - Connection and request limits
  |
  v
Inventory Service
  - Server-side concurrency limit
  - Queue and thread-pool bounds
  - Database connection pool limits
  - Load shedding / overload response
```

Mỗi lớp giải quyết một phạm vi:

- **Gateway:** kiểm soát lưu lượng từ client hoặc tenant trước khi request đi sâu vào hệ thống.
- **Circuit breaker ở caller:** ngừng gọi một dependency từ một tiến trình khi dependency có dấu hiệu suy giảm.
- **Bulkhead ở caller:** giới hạn số tác vụ đồng thời mà một dependency có thể chiếm trong tiến trình.
- **Service mesh hoặc load balancer:** áp dụng routing, health/outlier policy và giới hạn kết nối hoặc request tại lớp proxy. Phạm vi và cách tính giới hạn phụ thuộc implementation; không mặc định mọi mesh policy đều là quota toàn cluster.
- **Giới hạn tại dependency:** bảo vệ thread pool, queue, connection pool, CPU và các tài nguyên mà chính dịch vụ sử dụng.
- **Quota hoặc rate limiter phân tán:** giới hạn tổng lưu lượng theo tenant, API hoặc tài nguyên trên nhiều replica khi chính sách cần một bộ đếm dùng chung.

Một lớp không thể thay thế mọi lớp còn lại. Ví dụ gateway rate limit kiểm soát tốc độ request từ client nhưng không nhất thiết ngăn một service nội bộ tạo quá nhiều request tới database. Local circuit breaker giảm request từ caller đang gặp lỗi nhưng không chặn request từ những caller khác.

## 6. Phân biệt circuit breaker với rate limit và quota dùng chung

Circuit breaker và rate limiter có mục tiêu khác nhau:

| Cơ chế | Quyết định dựa trên | Phạm vi điển hình | Mục tiêu |
| --- | --- | --- | --- |
| Circuit breaker | Tỷ lệ lỗi, tỷ lệ lời gọi chậm và sliding window | Một ranh giới gọi trong một tiến trình hoặc proxy | Ngừng gọi dependency đang suy giảm |
| Local rate limiter | Số request trong khoảng thời gian | Một tiến trình | Giới hạn tốc độ tại caller đó |
| Distributed rate limiter | Bộ đếm hoặc token được chia sẻ giữa nhiều replica | Nhiều tiến trình/cluster hoặc tenant | Giới hạn tổng tốc độ theo chính sách chung |
| Bulkhead | Số tác vụ đồng thời, thread hoặc queue | Một pool hoặc tiến trình; có thể có giới hạn phía server | Ngăn một dependency chiếm hết tài nguyên |
| Admission control/load shedding | Tải hiện tại và năng lực còn lại | Thường ở gateway hoặc server | Từ chối sớm để giữ hệ thống ổn định |

Ví dụ, một tenant được phép gửi tối đa 500 request mỗi phút trên toàn bộ cluster. Nếu mỗi pod có local rate limiter 500 request/phút và có 10 pod, tổng lưu lượng có thể lên tới 5.000 request/phút. Để thực thi quota 500 request/phút dùng chung, cần một cơ chế phối hợp hoặc bộ đếm phân tán có semantics phù hợp; local limiter đơn lẻ không đủ.

Ngược lại, nếu mục tiêu là khi Inventory Service bắt đầu timeout thì Order Service ngừng gọi nó trong một khoảng thời gian, circuit breaker là cơ chế phù hợp hơn. Một rate limiter không tự nhận biết dependency đang lỗi; nó chỉ giới hạn số lượng request theo quy tắc tốc độ.

## 7. Có nên chia sẻ trạng thái circuit breaker giữa các máy?

Resilience4j CircuitBreaker thông thường là cơ chế trong bộ nhớ và không tự đồng bộ trạng thái giữa các JVM. Có thể nghĩ đến việc đưa trạng thái vào một kho dữ liệu dùng chung, nhưng việc này tạo ra nhiều vấn đề:

- Mỗi lời gọi phải đọc hoặc cập nhật trạng thái qua mạng, làm tăng độ trễ ở chính đường bảo vệ.
- Nhiều caller có thể đồng thời chuyển trạng thái; cần định nghĩa tính nguyên tử và thứ tự sự kiện.
- Khi kho dữ liệu hoặc mạng giữa caller và kho dữ liệu bị lỗi, cơ chế bảo vệ cũng có thể không hoạt động.
- Một trạng thái `OPEN` dùng chung có thể chặn cả caller đang kết nối tốt tới dependency trong khi chỉ một vùng mạng bị lỗi.
- Việc đồng bộ `HALF_OPEN` cần điều phối probe toàn cluster, nếu không nhiều node vẫn có thể thử cùng lúc.

Vì vậy, không nên biến circuit breaker cục bộ thành một dịch vụ trạng thái phân tán chỉ để mọi pod có cùng một giá trị `OPEN`/`CLOSED`. Nếu cần chính sách chung, thường nên đặt nó ở lớp có đúng phạm vi như gateway, service mesh hoặc distributed rate limiter/admission control. Local breaker vẫn có thể giữ vai trò bảo vệ nhanh tại caller.

Chỉ cân nhắc chia sẻ trạng thái khi có yêu cầu nghiệp vụ cụ thể, có mô hình nhất quán và xử lý lỗi của kho trạng thái rõ ràng. Phải đo chi phí truy cập, hành vi khi network partition và ảnh hưởng của một quyết định chung tới các caller ở vùng mạng khác nhau.

## 8. Cấu hình local breaker theo dependency

Một cấu hình điển hình cho hai dependency có đặc tính khác nhau:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
      payment:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 20
        failureRateThreshold: 30
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 40
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 1
```

Hai instance có ngưỡng và cửa sổ riêng vì inventory và payment có thể khác nhau về lưu lượng, độ trễ, hậu quả của lỗi và khả năng phục hồi. Các giá trị trên chỉ minh họa cấu trúc. Trong môi trường thật, cần chọn theo số request thực tế, timeout của client, SLO và khả năng chịu tải của dependency.

Mỗi replica sẽ nạp các giá trị này và duy trì thống kê cục bộ. Cấu hình giống nhau không đồng nghĩa thống kê giống nhau. Khi cần so sánh, xuất metric kèm nhãn instance/pod và tổng hợp ở hệ thống quan sát; không dùng một giá trị tổng hợp để giả định trạng thái từng breaker.

## 9. Theo dõi trạng thái theo instance và toàn cluster

Dashboard nên có cả góc nhìn chi tiết lẫn tổng hợp:

| Góc nhìn | Nên hiển thị | Lý do |
| --- | --- | --- |
| Theo pod/instance | Breaker state, failure rate, slow-call rate, số lần bị từ chối | Phát hiện một replica hoặc một vùng mạng có vấn đề riêng |
| Theo dependency toàn cluster | Request rate, lỗi, độ trễ, tổng số lần bị từ chối và số pod đang `OPEN` | Nhận biết tác động tổng thể lên dependency |
| Theo caller service | Tỷ lệ fallback, lỗi API và latency đầu-cuối | Đánh giá trải nghiệm người dùng và khả năng duy trì dịch vụ |
| Phía dependency | Inbound request rate, queue, thread, connection pool, CPU và overload response | Xác nhận hệ thống nhận request có đang quá tải hay không |

Metric Resilience4j thường gắn tên instance breaker, nhưng cần bổ sung nhãn triển khai như application, environment và pod từ Micrometer hoặc nền tảng scrape. Giữ cardinality hợp lý; không đưa request ID, user ID hoặc exception message vào nhãn.

Một pod ở `OPEN` trong khi các pod khác ở `CLOSED` có thể là dấu hiệu lỗi cục bộ. Nếu mọi pod lần lượt mở breaker cùng lúc và metric phía dependency cũng cho thấy độ trễ tăng, khả năng cao dependency gặp sự cố rộng hơn. Cần đối chiếu với trace, log và metric mạng trước khi kết luận.

## 10. Kiểm thử hành vi khi scale nhiều replica

Kiểm thử chỉ với một instance không thể chứng minh giới hạn phạm vi trong deployment nhiều replica. Có thể thiết kế một integration test hoặc môi trường staging với hai hoặc ba instance của cùng service:

1. Khởi động các replica với cùng cấu hình breaker `inventory`.
2. Gửi request qua một replica và mô phỏng lỗi dependency chỉ trên đường mạng của replica đó.
3. Xác nhận breaker của replica bị ảnh hưởng chuyển sang `OPEN` và supplier của nó không tiếp tục gọi dependency.
4. Gửi request qua replica khác có kết nối khỏe; xác nhận breaker của replica đó vẫn có thể ở `CLOSED` và lời gọi được thực hiện.
5. Khôi phục dependency và quan sát số probe `HALF_OPEN` phát sinh trên từng replica.
6. Đối chiếu tổng probe với giới hạn ở từng replica và giới hạn năng lực thực tế của dependency.

Kết quả mong đợi cho thấy trạng thái breaker là cục bộ. Nếu muốn tổng số probe hoặc tổng concurrency không vượt một giới hạn chung, cần thêm cơ chế giới hạn ở lớp rộng hơn hoặc ở phía dependency.

Kiểm thử bổ sung nên mô phỏng pod restart để xác nhận breaker mới khởi động không giữ lại sliding window trong bộ nhớ của pod cũ. Lịch sử trước restart cần được truy vết qua log và metric tập trung, không dựa vào trạng thái runtime của instance đã bị thay thế.

## 11. Các lỗi thiết kế thường gặp

- **Cho rằng một breaker mở sẽ mở toàn cluster:** các replica khác thường có state riêng và vẫn có thể gửi request.
- **Dùng local rate limiter để thực thi quota toàn cluster:** tổng quota có thể tăng theo số replica.
- **Cộng số probe theo một pod duy nhất:** số probe toàn cluster có thể bằng tổng permit của các breaker instance.
- **Dùng một breaker cho nhiều dependency:** lỗi và độ trễ của dependency này làm ảnh hưởng quyết định bảo vệ dependency khác.
- **Dùng metric tổng hợp để suy ra trạng thái từng pod:** cần giữ nhãn instance để xác định node đang gặp sự cố.
- **Đồng bộ trạng thái bằng kho dùng chung mà không tính lỗi của kho đó:** đường bảo vệ mới có thể trở thành một dependency quan trọng khác.
- **Chỉ bảo vệ ở caller:** dependency vẫn cần giới hạn thread, queue, connection và khả năng từ chối tải vượt năng lực.
- **Đóng breaker trên mọi replica cùng lúc:** lưu lượng có thể dồn về dependency ngay khi nó chưa sẵn sàng nhận toàn bộ tải.

## 12. Quy tắc chọn phạm vi bảo vệ

- Đặt Resilience4j CircuitBreaker tại từng ranh giới gọi dependency trong mỗi caller process.
- Dùng breaker riêng cho từng dependency có hành vi và chính sách lỗi khác nhau.
- Hiểu `minimumNumberOfCalls`, sliding window và số probe `HALF_OPEN` là giới hạn cục bộ của instance.
- Kết hợp timeout và bulkhead để giới hạn thời gian chờ và tài nguyên trong từng tiến trình.
- Dùng gateway, service mesh, distributed rate limiter hoặc admission control khi cần chính sách có phạm vi rộng hơn; xác minh rõ giới hạn thực tế là per-proxy, per-node hay global.
- Bảo vệ tài nguyên ở phía dependency bằng queue, thread pool và connection pool có giới hạn.
- Theo dõi metric theo pod đồng thời tổng hợp theo dependency để phân biệt lỗi cục bộ và sự cố diện rộng.
- Kiểm thử nhiều replica, pod restart và đợt probe phục hồi để đánh giá tải tổng thể.

Circuit breaker cục bộ là một lớp bảo vệ nhanh tại nơi phát sinh lời gọi. Nó giúp caller tự ngừng tạo thêm tải khi dependency có dấu hiệu suy giảm, nhưng không điều phối toàn bộ replica. Thiết kế đáng tin cậy cần phối hợp local breaker với giới hạn lưu lượng và tài nguyên ở gateway, proxy và dependency, đồng thời quan sát cả trạng thái từng instance lẫn tác động trên toàn hệ thống Spring Cloud.
