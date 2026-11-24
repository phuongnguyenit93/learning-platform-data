# Đã hết thời gian OPEN nhưng chưa có lời gọi thăm dò

Trong Resilience4j, Circuit Breaker không tự gửi request đến dịch vụ phụ thuộc chỉ vì thời gian OPEN đã hết. **waitDurationInOpenState** xác định khoảng thời gian bộ ngắt ở trạng thái OPEN trước khi có thể chuyển sang HALF_OPEN. Một lời gọi thực tế từ ứng dụng mới là thứ được cấp quyền làm probe để kiểm tra dependency đã phục hồi hay chưa.

Đây là nguyên nhân phổ biến khiến nhóm vận hành thấy thời gian OPEN đã trôi qua nhưng không thấy request thăm dò. Thuộc tính **automaticTransitionFromOpenToHalfOpenEnabled** chỉ điều khiển việc chuyển trạng thái tự động bằng scheduler; nó không tạo request kiểm tra sức khỏe. Muốn chẩn đoán đúng, cần phân biệt thời điểm hết thời gian chờ, thời điểm state chuyển HALF_OPEN và thời điểm một request thực sự được cho phép đi đến dependency.

## 1. Hết thời gian OPEN không đồng nghĩa đã có probe

State machine của Circuit Breaker có ba trạng thái hoạt động chính:

- **CLOSED:** lời gọi được cho phép và kết quả được ghi nhận vào sliding window.
- **OPEN:** lời gọi mới bị từ chối ngay, không chạy supplier gọi dependency.
- **HALF_OPEN:** chỉ một số lượng lời gọi giới hạn được phép đi qua để kiểm tra khả năng phục hồi.

Khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng, bộ ngắt chuyển từ CLOSED sang OPEN. Trong thời gian OPEN, request mới bị từ chối. Sau khi **waitDurationInOpenState** hết hạn, bộ ngắt có thể chuyển sang HALF_OPEN theo cơ chế cấu hình.

Tuy nhiên, Circuit Breaker không tự tạo một HTTP request, gọi một endpoint health check hoặc gửi một thông điệp đến dependency. Probe là một lời gọi nghiệp vụ thực tế được ứng dụng gửi qua cùng Circuit Breaker sau khi bộ ngắt cho phép. Nếu không có request mới, không có probe để quan sát.

| Mốc | Ý nghĩa | Có gọi dependency không? |
|---|---|---|
| Vừa chuyển OPEN | Bộ ngắt bắt đầu từ chối lời gọi mới | Không |
| Chưa hết wait duration | Vẫn trong thời gian bảo vệ | Không |
| Đã hết wait duration, tự động chuyển trạng thái tắt | Vẫn có thể hiển thị OPEN cho đến khi có lời gọi tiếp theo | Chưa |
| Đã hết wait duration, tự động chuyển trạng thái bật | State có thể chuyển sang HALF_OPEN bằng scheduler | Chưa, nếu không có request |
| Request mới được cấp quyền trong HALF_OPEN | Một probe thực tế được thực thi | Có |
| Đủ kết quả probe | Bộ ngắt quyết định CLOSED hoặc OPEN theo cấu hình | Các probe đã được gửi |

Vì vậy, câu hỏi chẩn đoán đầu tiên không phải chỉ là “đã hết bao lâu?”, mà là “sau thời điểm đó có request nào đi qua đúng Circuit Breaker instance hay chưa?”.

## 2. Cơ chế mặc định: chuyển sang HALF_OPEN khi có lời gọi tiếp theo

Thuộc tính **automaticTransitionFromOpenToHalfOpenEnabled** của Resilience4j mặc định thường là **false**. Khi tắt cơ chế tự động, không có thread nền chuyển trạng thái ngay lúc wait duration kết thúc. Bộ ngắt chuyển từ OPEN sang HALF_OPEN khi một lời gọi mới đến sau khi thời gian chờ đã hết.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        automaticTransitionFromOpenToHalfOpenEnabled: false
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Với cấu hình trên:

1. Circuit Breaker chuyển OPEN và bắt đầu thời gian chờ 15 giây.
2. Trong 15 giây, lời gọi mới bị từ chối.
3. Sau 15 giây, state có thể vẫn được báo là OPEN nếu chưa có request tiếp theo.
4. Request kế tiếp đi qua factory với ID **inventory** kích hoạt kiểm tra thời gian và có thể được cấp quyền trong HALF_OPEN.
5. Tối đa ba lời gọi thăm dò được cho phép theo cấu hình.
6. Kết quả các probe quyết định bộ ngắt đóng lại hay mở lại.

Nếu hệ thống ít traffic, trạng thái OPEN có thể tồn tại lâu hơn thời gian cấu hình trên dashboard. Điều đó không nhất thiết là lỗi timer; có thể chưa có lời gọi nào kích hoạt chuyển trạng thái theo cơ chế mặc định.

## 3. Bật automaticTransitionFromOpenToHalfOpenEnabled

Nếu muốn state tự chuyển sang HALF_OPEN sau khi hết thời gian OPEN ngay cả khi chưa có request, có thể bật **automaticTransitionFromOpenToHalfOpenEnabled**:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        automaticTransitionFromOpenToHalfOpenEnabled: true
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Khi bật thuộc tính này, Resilience4j sử dụng cơ chế scheduler để chuyển state từ OPEN sang HALF_OPEN sau thời gian chờ. Điều đó giúp state không phải đợi một request mới chỉ để thực hiện bước chuyển trạng thái.

Nhưng cần hiểu rõ giới hạn: scheduler chỉ chuyển state. Nó không gọi **inventoryClient**, không gửi HTTP request và không tự kiểm tra endpoint. Nếu không có request đi qua Circuit Breaker sau khi state đã là HALF_OPEN, bộ ngắt vẫn không có kết quả probe để đánh giá phục hồi.

| Cấu hình | Hành vi sau khi hết wait duration | Điều kiện để có probe |
|---|---|---|
| **automaticTransitionFromOpenToHalfOpenEnabled: false** | Chuyển state khi có lời gọi tiếp theo | Phải có request mới đi qua breaker |
| **automaticTransitionFromOpenToHalfOpenEnabled: true** | Scheduler chuyển state sang HALF_OPEN | Vẫn phải có request mới được cấp quyền |

Bật tự động chuyển trạng thái phù hợp khi cần state transition độc lập với traffic. Không nên bật với kỳ vọng hệ thống sẽ chủ động ping dependency. Nếu yêu cầu vận hành là kiểm tra sức khỏe chủ động, cần thiết kế một health checker riêng với timeout, giới hạn đồng thời và chính sách an toàn; không nên nhầm nó với probe do Circuit Breaker cấp cho request ứng dụng.

## 4. permittedNumberOfCallsInHalfOpenState chỉ giới hạn số probe được cấp

Khi HALF_OPEN, **permittedNumberOfCallsInHalfOpenState** xác định số lời gọi được phép thực thi để đánh giá dependency. Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        waitDurationInOpenState: 10s
        automaticTransitionFromOpenToHalfOpenEnabled: true
        permittedNumberOfCallsInHalfOpenState: 2
        failureRateThreshold: 50
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
~~~

Khi state chuyển HALF_OPEN, tối đa hai lời gọi được cấp quyền làm probe theo chính sách này. Nếu không có traffic, số probe thực tế vẫn là 0. Nếu chỉ có một request, chỉ một probe được thực hiện; bộ ngắt cần nhận đủ kết quả theo cơ chế và cấu hình của phiên bản đang dùng trước khi quyết định state tiếp theo.

Không nên đặt số probe quá lớn vì mục tiêu của HALF_OPEN là kiểm tra khả năng phục hồi mà không tạo tải đột ngột lên dependency. Cũng không nên đặt quá nhỏ nếu kết quả đơn lẻ dễ bị nhiễu bởi lỗi mạng nhất thời. Chọn số lượng dựa trên lưu lượng, độ ổn định và khả năng chịu tải của dịch vụ phụ thuộc.

Nếu request được Retry, cần chú ý thứ tự phối hợp. Retry nằm ngoài Circuit Breaker có thể khiến từng attempt đi qua bộ ngắt và tiêu thụ nhiều lượt probe. Circuit Breaker nằm ngoài Retry có thể chỉ cấp một quyền cho toàn bộ operation logic trong khi Retry thực hiện nhiều lần gọi bên trong. Cần tính số request thực tế đến dependency, không chỉ số request nghiệp vụ.

## 5. Kiểm tra request có đi qua đúng Circuit Breaker ID hay không

Một nguyên nhân thường gặp khác là ứng dụng đang gửi traffic nhưng request không đi qua instance mà nhóm đang theo dõi. Ví dụ code gọi:

~~~java
return circuitBreakerFactory.create("inventory-read").run(
    () -> inventoryClient.getStock(sku),
    error -> Stock.unavailable(sku)
);
~~~

Trong khi cấu hình Resilience4j lại khai báo:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        waitDurationInOpenState: 15s
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

Ở đây, code dùng ID **inventory-read**, còn properties chỉ cấu hình instance **inventory**. Nhóm có thể đang xem metric của **inventory** trong khi request thực tế dùng **inventory-read**. Cần giữ tên nhất quán giữa factory, cấu hình instance, log và dashboard.

Với Spring Cloud Gateway, kiểm tra thêm tên trong filter:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory-route
          uri: lb://INVENTORY-SERVICE
          predicates:
            - Path=/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventory
                fallbackUri: forward:/fallback/inventory
~~~

Tên **args.name** là Circuit Breaker ID của filter. Route ID là **inventory-route**, không phải tên instance. Nếu dashboard theo dõi **inventory-read** nhưng Gateway dùng **inventory**, hai bộ ngắt là hai phạm vi khác nhau.

Hãy kiểm tra:

- Tên trong **CircuitBreakerFactory.create(id)** hoặc filter **args.name**.
- Tên instance trong **resilience4j.circuitbreaker.instances**.
- Tên xuất hiện trong metric và event.
- Route hoặc service thực sự được request gọi đến.
- Request có bị cache, filter khác hoặc fallback xử lý trước khi đi qua Circuit Breaker hay không.

## 6. Lưu ý khi ứng dụng chạy nhiều replica hoặc pod

Resilience4j Circuit Breaker thông thường lưu state trong bộ nhớ của tiến trình. Mỗi JVM hoặc pod có registry và state riêng. Cùng một tên **inventory** trên sáu pod không có nghĩa là có một state machine dùng chung toàn cụm.

Ví dụ:

| Pod | State cục bộ | Thời điểm OPEN |
|---|---|---|
| app-1 | OPEN | 10:00:00 |
| app-2 | CLOSED | Chưa mở |
| app-3 | OPEN | 10:00:04 |
| app-4 | CLOSED | Chưa mở |

Khi wait duration của **app-1** kết thúc, request tiếp theo có thể được load balancer gửi đến **app-2**. Pod **app-2** đang CLOSED nên lời gọi được thực hiện như bình thường; đó không phải probe của **app-1**. Ngược lại, request có thể đến **app-1** và trở thành probe nếu state của pod đó đã sẵn sàng HALF_OPEN.

Điều này khiến dashboard tổng hợp toàn cụm dễ gây hiểu nhầm. Một số pod có thể OPEN, một số pod vẫn CLOSED, và số probe khác nhau theo traffic từng pod. Cần xem metric theo instance/pod và log có thông tin định danh tiến trình.

Không giả định Circuit Breaker Resilience4j tự đồng bộ state giữa các pod. Nếu yêu cầu là một breaker dùng chung toàn cụm, cần một thiết kế phân tán riêng hoặc một cơ chế admission control ở tầng chung. Cân nhắc độ trễ, tính sẵn sàng và rủi ro khi state store phân tán gặp sự cố trước khi chọn giải pháp.

## 7. Các nguyên nhân khác khiến không thấy probe

Ngoài việc không có traffic, cần kiểm tra các tình huống sau:

| Nguyên nhân | Dấu hiệu | Cách xác minh |
|---|---|---|
| Request không đến service hoặc route được bảo vệ | Không có log vào gateway/service | Kiểm tra route predicate, ingress, auth và traffic |
| Request đi qua Circuit Breaker ID khác | Metric của instance đang xem không đổi | Đối chiếu factory ID, filter name và properties |
| Traffic bị cache hoặc trả fallback ở lớp trước | Caller có response nhưng dependency không nhận request | Theo dõi thứ tự filter và log tại client |
| State cục bộ ở pod khác | Metric từng pod khác nhau | Phân tách dashboard theo pod/instance |
| Circuit Breaker bị đặt FORCED_OPEN | Request luôn bị từ chối dù wait duration đã qua | Kiểm tra thao tác quản trị hoặc cấu hình state |
| HALF_OPEN đã dùng hết lượt probe | Có một số probe nhưng request tiếp theo bị từ chối | Kiểm tra số lượt được phép và kết quả từng probe |
| Probe đang chạy rất lâu | HALF_OPEN chưa có đủ kết quả | Kiểm tra timeout, latency và in-flight request |
| Cấu hình không được bind | State transition không theo giá trị mong đợi | Kiểm tra startup log, profile và tên property |

Resilience4j còn có các trạng thái quản trị như **FORCED_OPEN**, **DISABLED** hoặc **METRICS_ONLY**. Nếu bộ ngắt bị chuyển thủ công sang FORCED_OPEN, không nên kỳ vọng timer OPEN thông thường sẽ tự đưa nó về HALF_OPEN. Cần xác định ai hoặc thành phần nào đã thay đổi state và khôi phục theo quy trình quản trị phù hợp.

Nếu HALF_OPEN có probe nhưng chúng không hoàn tất, hãy kiểm tra timeout của HTTP client, TimeLimiter, Bulkhead và tài nguyên executor. State không thể đánh giá kết quả khi các lời gọi thăm dò vẫn đang treo.

## 8. Quan sát state transition và số probe

Không nên chỉ dựa vào một dòng log OPEN hoặc HALF_OPEN. Hãy theo dõi cả chuyển trạng thái và số lời gọi thực sự đi qua dependency.

Có thể đăng ký event listener trên Resilience4j Circuit Breaker để ghi nhận state transition:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerObservationConfiguration {

    @Bean
    ApplicationRunner observeInventoryBreaker(
            CircuitBreakerRegistry registry) {
        return args -> {
            var breaker = registry.circuitBreaker("inventory");

            breaker.getEventPublisher()
                .onStateTransition(event ->
                    log.info(
                        "Circuit Breaker inventory: {}",
                        event.getStateTransition()
                    )
                )
                .onCallNotPermitted(event ->
                    log.warn("Circuit Breaker inventory từ chối lời gọi")
                )
                .onSuccess(event ->
                    log.debug("Inventory probe/lời gọi thành công")
                )
                .onError(event ->
                    log.warn("Inventory probe/lời gọi thất bại", event.getThrowable())
                );
        };
    }
}
~~~

Ví dụ minh họa việc quan sát event trên Resilience4j registry khi registry được cung cấp bởi starter đang sử dụng. Hãy xác minh đúng bean và API theo phiên bản dependency của dự án.

Kết hợp các tín hiệu:

- State hiện tại của từng Circuit Breaker instance.
- Thời điểm chuyển OPEN và HALF_OPEN.
- Số lời gọi được cấp quyền trong HALF_OPEN.
- Số lời gọi bị từ chối (not permitted).
- Số request thực sự đến HTTP client hoặc dependency.
- Latency và kết quả của từng probe.
- Pod/instance xử lý request.

Nếu bật Actuator hoặc Micrometer, có thể dùng endpoint và metric tương ứng để quan sát state cùng số lời gọi. Chỉ mở endpoint quản trị theo chính sách bảo mật của môi trường; không công khai endpoint thay đổi state ra bên ngoài.

## 9. Kiểm tra cấu hình và hành vi bằng một quy trình chẩn đoán

Khi hết thời gian OPEN mà không thấy probe, thực hiện lần lượt:

1. **Xác định instance:** lấy chính xác Circuit Breaker ID từ code hoặc Gateway filter.
2. **Xác minh cấu hình:** kiểm tra **waitDurationInOpenState**, **automaticTransitionFromOpenToHalfOpenEnabled** và **permittedNumberOfCallsInHalfOpenState** thuộc đúng instance.
3. **Kiểm tra state theo pod:** xác định pod nào đang OPEN, HALF_OPEN hoặc CLOSED.
4. **Đối chiếu thời gian:** xác nhận thời điểm bắt đầu OPEN và thời gian chờ thực tế, không chỉ thời gian triển khai hoặc thời điểm xem dashboard.
5. **Kiểm tra traffic:** xác nhận có request mới đi qua đúng route/service sau khi wait duration kết thúc.
6. **Kiểm tra filter và cache:** xác nhận request không được xử lý ở lớp khác trước Circuit Breaker.
7. **Kiểm tra quyền probe:** xem số probe đã được cấp và có probe nào đang in-flight hay không.
8. **Kiểm tra state quản trị:** loại trừ FORCED_OPEN hoặc một cơ chế quản trị giữ state.
9. **Kiểm tra kết quả:** xem dependency trả thành công, lỗi hay timeout; đối chiếu với ngưỡng và exception policy.
10. **Xác nhận metrics:** phân biệt state transition với request thực sự được gửi đến dependency.

Nếu **automaticTransitionFromOpenToHalfOpenEnabled** là **false** và không có traffic sau thời gian chờ, việc chưa thấy HALF_OPEN có thể là hành vi đúng. Nếu bật **true** nhưng state đã HALF_OPEN mà không thấy HTTP request, hãy kiểm tra traffic và request routing; scheduler không tạo request.

## 10. Kiểm thử có kiểm soát cho tình huống không có probe

Có thể tạo một integration test với thời gian OPEN ngắn để kiểm chứng hai chế độ. Không dùng thời gian chờ dài trong test hoặc phụ thuộc vào traffic production.

### Trường hợp A: automatic transition tắt

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 500ms
        automaticTransitionFromOpenToHalfOpenEnabled: false
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Tạo đủ số lỗi để bộ ngắt chuyển OPEN. Chờ quá 500 ms nhưng chưa gửi request mới. Có thể state vẫn được báo OPEN. Gửi một request tiếp theo qua đúng instance; lúc này bộ ngắt kiểm tra thời gian và cho phép quá trình HALF_OPEN.

### Trường hợp B: automatic transition bật

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 500ms
        automaticTransitionFromOpenToHalfOpenEnabled: true
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Tạo đủ lỗi để mở mạch rồi chờ quá 500 ms. State có thể tự chuyển HALF_OPEN dù chưa có request. Tuy nhiên, số lần gọi dependency vẫn bằng 0 cho đến khi test gửi request qua breaker.

Trong cả hai trường hợp, gửi probe thành công để xác nhận state trở lại CLOSED theo chính sách. Gửi probe thất bại để xác nhận bộ ngắt chuyển OPEN trở lại. Dùng assertion có timeout hoặc polling có giới hạn để chờ state transition; không dùng một khoảng sleep dài và không kiểm tra chỉ bằng log.

## 11. Cẩn trọng khi dùng health check chủ động

Nếu nghiệp vụ yêu cầu hệ thống kiểm tra dependency ngay cả khi không có user traffic, hãy triển khai một health checker riêng thay vì kỳ vọng Circuit Breaker tự ping.

Health checker cần có:

- Endpoint kiểm tra nhẹ và đại diện cho khả năng phục vụ thực tế.
- Chu kỳ kiểm tra có giới hạn, không tạo tải liên tục.
- Timeout và giới hạn đồng thời riêng.
- Xử lý lỗi, backoff và jitter khi dependency không khỏe.
- Quy tắc xác định kết quả health check có được phép mở/đóng Circuit Breaker hay chỉ dùng cho dashboard.
- Cơ chế tránh tất cả pod cùng ping dependency đồng thời sau khi phục hồi.

Không nên để health check tự ý gọi cùng Circuit Breaker như một probe đặc quyền nếu chưa xác định tác động lên **permittedNumberOfCallsInHalfOpenState**. Một health check có thể tiêu thụ slot thăm dò và ảnh hưởng đến request thật. Nếu muốn health checker tham gia quyết định state, hãy thiết kế rõ cách phối hợp, giới hạn tải và semantics của kết quả.

Với dependency có endpoint health riêng, trạng thái endpoint đó cũng không luôn đồng nghĩa các operation nghiệp vụ hoạt động tốt. Một endpoint **/health** có thể trả OK trong khi truy vấn Catalog hoặc giao dịch Inventory vẫn lỗi. Probe nghiệp vụ cần nhẹ, an toàn và đủ đại diện cho thao tác mà Circuit Breaker đang bảo vệ.

## 12. Những lỗi thường gặp

1. **Cho rằng hết waitDurationInOpenState sẽ tự gửi request.** Thời gian chờ chỉ cho phép chuyển state; Circuit Breaker không tạo traffic.
2. **Nhầm automatic transition với active health check.** Scheduler chỉ chuyển OPEN sang HALF_OPEN, không gọi dependency.
3. **Không có request sau khi hết thời gian chờ.** Không có traffic thì không có probe thực tế.
4. **Theo dõi nhầm Circuit Breaker ID.** Code, Gateway filter và Resilience4j properties dùng tên khác nhau.
5. **Gộp metric của nhiều pod.** State cục bộ khác nhau khiến số probe không đồng nhất giữa replica.
6. **Bỏ qua trạng thái FORCED_OPEN.** State bị quản trị ép mở không tuân theo chu kỳ OPEN thông thường.
7. **Đặt quá ít probe hoặc để probe treo.** HALF_OPEN không có đủ kết quả để đánh giá phục hồi.
8. **Retry tiêu thụ nhiều probe.** Thứ tự Retry và Circuit Breaker có thể làm số attempt khác số request logic.
9. **Cache hoặc filter trả response trước bộ ngắt.** Caller có traffic nhưng dependency không nhận lời gọi.
10. **Dùng health check quá dày.** Các pod có thể tạo đợt tải đồng loạt đúng lúc backend đang phục hồi.

## 13. Tình huống thực hành

Một ứng dụng Spring Boot có ba pod gọi dịch vụ Inventory. Mỗi pod có Circuit Breaker instance tên **inventory**, cấu hình OPEN trong 15 giây và cho phép hai probe ở HALF_OPEN.

Pod **app-1** mở Circuit Breaker lúc 10:00:00. Pod **app-2** và **app-3** vẫn CLOSED. Sau 15 giây:

- Nếu automatic transition tắt, **app-1** có thể vẫn hiển thị OPEN cho đến khi nhận request tiếp theo.
- Nếu automatic transition bật, scheduler của **app-1** chuyển state sang HALF_OPEN, nhưng không gửi request.
- Nếu không có traffic đến **app-1**, số probe vẫn bằng 0.
- Nếu load balancer gửi request đến **app-2**, lời gọi đó đi qua breaker CLOSED của **app-2**, không phải probe của **app-1**.
- Khi request đến **app-1**, breaker có thể cấp một trong hai lượt probe.
- Nếu probe thành công theo chính sách, **app-1** trở lại CLOSED; nếu thất bại, nó chuyển OPEN lại.

Khi điều tra, hãy xem dashboard theo pod thay vì chỉ xem một metric tổng hợp. Đối chiếu state transition với request count của HTTP client để xác nhận probe đã thực sự đến dependency.

Sau khi thực hành, cần trả lời được:

- Wait duration kết thúc ở thời điểm nào?
- Automatic transition đang bật hay tắt?
- State của từng pod là gì?
- Có request mới đi qua đúng Circuit Breaker ID không?
- Probe được cấp bao nhiêu lượt và kết quả ra sao?
- Có retry, cache hoặc filter nào làm thay đổi số request đến dependency không?

## Kết luận

Khi hết thời gian OPEN mà chưa thấy probe, nguyên nhân thường là Circuit Breaker không tự tạo request thăm dò. Với **automaticTransitionFromOpenToHalfOpenEnabled: false**, state có thể đợi lời gọi tiếp theo mới chuyển HALF_OPEN; khi bật **true**, scheduler chỉ chuyển state và vẫn cần traffic để có probe. Hãy xác minh đúng Circuit Breaker ID, cấu hình, request routing và state theo từng pod; kiểm tra số probe được cấp, retry, timeout và trạng thái quản trị. Nếu cần kiểm tra chủ động khi không có user traffic, hãy thiết kế health checker riêng với giới hạn tải và quy tắc phối hợp rõ ràng.
