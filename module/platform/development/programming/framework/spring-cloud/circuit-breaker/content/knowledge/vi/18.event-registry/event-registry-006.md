# Quản lý dung lượng bộ đệm sự kiện và chi phí xử lý

## Mục tiêu của bài học

Circuit breaker và các cơ chế Resilience4j phát ra sự kiện khi lời gọi thành công, thất bại, bị từ chối, timeout hoặc khi trạng thái thay đổi. Sự kiện giúp đội phát triển tìm nguyên nhân sự cố và quan sát quá trình phục hồi. Tuy nhiên, lưu quá nhiều sự kiện hoặc xử lý chúng quá nặng có thể làm tăng mức dùng bộ nhớ và độ trễ của ứng dụng.

Trong Spring Cloud CircuitBreaker dùng Resilience4j, cần phân biệt bộ đệm lưu lịch sử sự kiện với sliding window dùng để tính tỷ lệ lỗi và lời gọi chậm. Hai cấu trúc này có mục đích khác nhau và phải được điều chỉnh riêng.

Sau bài học, bạn có thể:

- Mô tả vai trò của CircuitBreakerRegistry, EventConsumerRegistry và CircularEventConsumer.
- Cấu hình eventConsumerBufferSize cho lịch sử sự kiện của một instance.
- Phân biệt dung lượng bộ đệm sự kiện với slidingWindowSize.
- Ước lượng tác động bộ nhớ khi có nhiều breaker và nhiều instance ứng dụng.
- Đăng ký listener cho sự kiện mà không làm chậm luồng gọi.
- Chọn sự kiện cần ghi log, metric hoặc chuyển sang xử lý bất đồng bộ.
- Sử dụng Actuator event endpoint để điều tra sự cố và bảo vệ dữ liệu quan sát.

## 1. Sự kiện Resilience4j được phát ra khi nào?

Circuit breaker phát ra các sự kiện mô tả kết quả và trạng thái của lời gọi. Ví dụ:

| Nhóm sự kiện | Ý nghĩa | Giá trị khi vận hành |
| --- | --- | --- |
| SUCCESS | Lời gọi hoàn tất thành công. | Theo dõi hoạt động bình thường và phục hồi. |
| ERROR | Lời gọi thất bại và được ghi nhận theo cấu hình. | Tìm lỗi mạng, lỗi HTTP hoặc lỗi xử lý từ phụ thuộc. |
| IGNORED_ERROR | Lỗi được phân loại là bỏ qua. | Xác nhận exception không ảnh hưởng failure rate. |
| CALL_NOT_PERMITTED | Breaker từ chối lời gọi, thường vì đang OPEN hoặc không cho phép tại thời điểm đó. | Đo mức độ bảo vệ và số request bị chặn nhanh. |
| STATE_TRANSITION | Breaker chuyển giữa CLOSED, OPEN và HALF_OPEN. | Xác định thời điểm mở, thử phục hồi và đóng lại. |
| RESET | Breaker được reset. | Theo dõi thao tác vận hành hoặc thay đổi trạng thái có chủ đích. |

Các loại sự kiện và tên enum cụ thể có thể khác theo phiên bản Resilience4j. Hãy dùng API của phiên bản được quản lý trong dự án và chỉ đăng ký những loại sự kiện cần thiết.

Sự kiện có thể chứa tên instance, loại sự kiện, thời điểm phát sinh, thời lượng lời gọi và thông tin exception. Đây là dữ liệu phục vụ quan sát. Sự kiện không phải dữ liệu nghiệp vụ, không phải message queue bền vững và không thay thế metric tổng hợp.

Các cơ chế khác cũng phát sự kiện, chẳng hạn Retry, RateLimiter, Bulkhead và TimeLimiter. Mỗi loại có nhóm sự kiện riêng: Retry báo lần thử lại, Bulkhead báo lời gọi được cấp phép hoặc bị từ chối, TimeLimiter báo timeout. Khi triển khai quan sát, hãy giữ tên cơ chế và instance rõ ràng để không trộn lẫn các loại sự kiện.

## 2. Phân biệt registry và event consumer

Resilience4j có registry quản lý các instance của từng cơ chế. Ví dụ, CircuitBreakerRegistry quản lý các circuit breaker theo tên. Ứng dụng có thể lấy breaker inventory từ registry hoặc lắng nghe sự kiện khi instance được tạo, thay thế hay xóa.

Event consumer có vai trò nhận các sự kiện do instance phát ra. Trong tích hợp Spring Boot của Resilience4j, EventConsumerRegistry quản lý consumer gắn với tên instance. Với CircuitBreaker, consumer thường được kết nối tới một circular buffer để giữ lịch sử gần đây và cung cấp dữ liệu cho endpoint quan sát.

Có thể hình dung:

    CircuitBreakerRegistry
        |
        +-- inventory CircuitBreaker
        |       |
        |       +-- EventPublisher
        |               |
        |               +-- EventConsumerRegistry
        |                       |
        |                       +-- Circular buffer (inventory)
        |
        +-- pricing CircuitBreaker
                |
                +-- EventPublisher
                        |
                        +-- EventConsumerRegistry
                                |
                                +-- Circular buffer (pricing)

Các thành phần có trách nhiệm khác nhau:

- CircuitBreakerRegistry quản lý vòng đời các breaker instance.
- EventPublisher phát sự kiện từ một breaker cụ thể.
- EventConsumerRegistry quản lý consumer nhận sự kiện theo tên instance trong tích hợp Spring Boot.
- CircularEventConsumer giữ một số lượng sự kiện gần đây trong bộ nhớ.

EventConsumerRegistry không phải một hệ thống truyền tin phân tán. Nó không tự đồng bộ lịch sử giữa các pod, không lưu bền vững qua lần khởi động lại và không đảm bảo giao sự kiện tới một hệ thống bên ngoài. Nếu cần lưu lịch sử dài hạn hoặc gom sự kiện từ nhiều instance, hãy chuyển dữ liệu đã chọn sang logging, metrics, tracing hoặc nền tảng thu thập tập trung.

## 3. Circular buffer giữ lại những sự kiện gần nhất

CircularEventConsumer là một consumer có dung lượng cố định. Khi buffer chưa đầy, sự kiện mới được thêm vào. Khi đã đầy, sự kiện mới thay thế sự kiện cũ nhất. Vì vậy, buffer luôn giữ tối đa N sự kiện gần đây.

Ví dụ, buffer có dung lượng 4:

    Sự kiện đến: E1, E2, E3, E4
    Buffer:      [E1, E2, E3, E4]

    Sự kiện E5 đến:
    Buffer:      [E2, E3, E4, E5]

    Sự kiện E6 đến:
    Buffer:      [E3, E4, E5, E6]

Cách lưu này phù hợp để xem nhanh những gì vừa xảy ra trước khi một breaker mở hoặc sau khi một phụ thuộc phục hồi. Nó không phải hàng đợi chờ xử lý: consumer không giữ lại mọi sự kiện vô thời hạn và không đảm bảo ứng dụng có thể đọc lại toàn bộ lịch sử.

Có thể dùng trực tiếp CircularEventConsumer:

    CircularEventConsumer<CircuitBreakerEvent> recentEvents =
        new CircularEventConsumer<>(50);

    circuitBreaker.getEventPublisher().onEvent(recentEvents);

    List<CircuitBreakerEvent> snapshot =
        recentEvents.getBufferedEvents();

Ví dụ tạo buffer 50 sự kiện cho một breaker. Khi sự kiện thứ 51 đến, sự kiện cũ nhất bị thay thế. Dung lượng nên được chọn theo tốc độ phát sinh sự kiện và khoảng thời gian cần điều tra. Nếu chỉ cần xem vài sự kiện trước khi mở breaker, buffer nhỏ có thể đủ. Nếu muốn xem một khoảng thời gian dài hơn trong lúc lưu lượng cao, cần dung lượng lớn hơn hoặc chuyển dữ liệu đã chọn sang hệ thống quan sát tập trung.

## 4. Cấu hình eventConsumerBufferSize

Khi sử dụng tích hợp Spring Boot của Resilience4j, có thể cấu hình dung lượng event consumer buffer theo từng instance trong application.yml:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            eventConsumerBufferSize: 100
          pricing:
            slidingWindowType: TIME_BASED
            slidingWindowSize: 10
            minimumNumberOfCalls: 10
            failureRateThreshold: 40
            eventConsumerBufferSize: 30

Trong ví dụ:

- inventory giữ tối đa 100 sự kiện gần đây trong event consumer buffer.
- pricing giữ tối đa 30 sự kiện gần đây.
- slidingWindowSize vẫn được cấu hình riêng để tính toán trạng thái circuit breaker.

eventConsumerBufferSize là cấu hình dung lượng lịch sử sự kiện trong tích hợp Spring Boot/Actuator của Resilience4j. Nếu ứng dụng chỉ dùng Spring Cloud CircuitBreaker factory mà không có phần auto-configuration event consumer của Resilience4j Spring Boot, không nên giả định property này tự tạo ra endpoint sự kiện. Khi đó, ứng dụng có thể đăng ký consumer bằng EventPublisher hoặc tự tạo CircularEventConsumer.

Tài liệu Resilience4j mô tả endpoint event mặc định trả về các sự kiện gần đây; giá trị mặc định thường là 100 trong tích hợp Spring Boot. Hãy xác nhận giá trị thực tế theo phiên bản và cấu hình của ứng dụng. Khai báo rõ eventConsumerBufferSize cho những instance cần điều tra giúp tránh phụ thuộc vào mặc định.

## 5. Event buffer khác sliding window

Hai cấu trúc đều có kích thước, nhưng không thể thay thế cho nhau:

| Thuộc tính | eventConsumerBufferSize | slidingWindowSize |
| --- | --- | --- |
| Mục đích | Giữ lịch sử sự kiện gần đây để quan sát. | Tính failure rate và slow call rate. |
| Dữ liệu | Các event object như SUCCESS, ERROR, STATE_TRANSITION. | Kết quả lời gọi được tổng hợp theo count hoặc time bucket. |
| Khi đầy | Sự kiện cũ nhất bị thay thế trong circular buffer. | Các mẫu cũ rời khỏi sliding window theo cơ chế cửa sổ. |
| Ảnh hưởng đến quyết định OPEN | Không trực tiếp quyết định trạng thái breaker. | Là một phần dữ liệu đầu vào để đánh giá ngưỡng. |
| Nơi sử dụng | Event endpoint, chẩn đoán và listener. | Logic thống kê của CircuitBreaker. |

Ví dụ, slidingWindowSize bằng 20 có nghĩa breaker đánh giá 20 lời gọi gần nhất nếu dùng COUNT_BASED. eventConsumerBufferSize bằng 100 có nghĩa event consumer giữ tối đa 100 sự kiện. Một lời gọi có thể phát nhiều sự kiện trong vòng đời hoặc các cơ chế khác nhau cũng có buffer riêng, nên số event không bằng số sample trong sliding window.

Không tăng eventConsumerBufferSize để thay đổi thời điểm breaker mở. Muốn thay đổi quyết định mở breaker, điều chỉnh slidingWindowType, slidingWindowSize, minimumNumberOfCalls và các threshold. Muốn giữ nhiều lịch sử sự kiện hơn để điều tra, điều chỉnh eventConsumerBufferSize.

## 6. Ước lượng dung lượng bộ nhớ

Mỗi event buffer giữ một tập tham chiếu tới các đối tượng sự kiện và dữ liệu liên quan. Bộ nhớ thực tế phụ thuộc loại event, kích thước thông tin exception, implementation, JVM và số lượng instance. Vì vậy, không thể tính chính xác dung lượng chỉ bằng N.

Có thể dùng mô hình ước lượng ban đầu:

    Tổng số event slots
      = số breaker instance x eventConsumerBufferSize

    Bộ nhớ gần đúng
      = tổng số event slots x chi phí trung bình mỗi event

Ví dụ, một ứng dụng có 12 breaker và mỗi buffer giữ 100 sự kiện sẽ có tối đa khoảng 1.200 vị trí lưu event cho các breaker đó. Nếu tăng mỗi buffer lên 1.000, tổng số vị trí tăng lên khoảng 12.000. Đây chỉ là phép tính số slot, không phải số byte heap chính xác.

Khi ước lượng, cần tính:

- Số breaker instance thực tế, bao gồm các instance được tạo động.
- Số loại resilience mechanism có event buffer riêng.
- Kích thước event và exception metadata.
- Số pod hoặc JVM đang chạy.
- Bộ nhớ dành cho cache, request, response và các cấu trúc khác.

Buffer thường nằm trong bộ nhớ tiến trình. Nếu chạy 5 pod, mỗi pod giữ buffer riêng cho các breaker của nó. Tổng dung lượng ở cấp hệ thống có thể xấp xỉ tổng của tất cả pod. Lịch sử trong một pod không tự xuất hiện ở pod khác.

Không tạo hàng nghìn breaker theo request ID hoặc user ID. Việc tạo quá nhiều instance vừa làm tăng registry và metric cardinality, vừa nhân số event buffer. Hãy đặt tên breaker ổn định theo phụ thuộc hoặc thao tác có ý nghĩa vận hành.

## 7. Chọn dung lượng theo tốc độ phát sinh và mục tiêu điều tra

Dung lượng phù hợp phụ thuộc số sự kiện mỗi giây và khoảng thời gian cần xem lại. Nếu một breaker phát trung bình 20 sự kiện mỗi giây và buffer giữ 100 sự kiện, lịch sử chỉ bao phủ khoảng 5 giây. Nếu buffer có 1.000 vị trí, khoảng lịch sử lý thuyết tăng lên khoảng 50 giây ở cùng tốc độ.

Cách tính gần đúng:

    Khoảng lịch sử (giây)
      = eventConsumerBufferSize / số sự kiện mỗi giây

Đây là ước lượng. Tốc độ phát sự kiện thay đổi theo tải và loại event; một lời gọi có thể phát SUCCESS hoặc ERROR, và một chuyển trạng thái có thể tạo thêm event. Không dùng công thức này như cam kết retention chính xác.

Một số hướng chọn:

- **Lưu lượng thấp, điều tra nhanh:** buffer nhỏ hoặc theo mặc định có thể đủ.
- **Lưu lượng cao:** tăng dung lượng nếu cần giữ thêm lịch sử, nhưng kiểm tra heap và số instance.
- **Cần lưu lịch sử dài hạn:** chuyển event quan trọng sang log hoặc nền tảng quan sát tập trung; không dựa vào ring buffer trong bộ nhớ.
- **Nhiều breaker:** ưu tiên cấu hình riêng cho các instance quan trọng thay vì tăng tất cả buffer đồng loạt.
- **Môi trường test:** buffer nhỏ có thể giúp kiểm thử overwrite và thứ tự sự kiện dễ hơn.

Nếu buffer quá nhỏ, sự kiện quan trọng có thể bị ghi đè trước khi người vận hành xem endpoint. Nếu quá lớn, ứng dụng giữ nhiều đối tượng trong bộ nhớ nhưng vẫn không có lịch sử bền vững. Chọn dung lượng theo khoảng thời gian điều tra thực tế và theo dõi mức sử dụng heap sau khi triển khai.

## 8. Đăng ký listener với chi phí thấp

Resilience4j cho phép đăng ký consumer trực tiếp với EventPublisher. Với Spring Cloud CircuitBreaker, có thể gắn listener khi breaker được tạo bằng addCircuitBreakerCustomizer:

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryEventCustomizer() {
        return factory -> factory.addCircuitBreakerCustomizer(
            circuitBreaker -> circuitBreaker.getEventPublisher()
                .onStateTransition(event ->
                    logger.info(
                        "inventory breaker transition: {}",
                        event.getStateTransition()
                    )
                )
                .onCallNotPermitted(event ->
                    metrics.counter("dependency.calls.rejected",
                        "dependency", "inventory").increment()
                )
                .onError(event ->
                    metrics.counter("dependency.calls.failed",
                        "dependency", "inventory").increment()
                ),
            "inventory"
        );
    }

Ví dụ minh họa listener cho breaker tên inventory. Logger và metrics là thành phần ứng dụng đã cấu hình. Chỉ ghi thông tin cần thiết và dùng tag có cardinality giới hạn. Không đưa SKU, userId, requestId hoặc payload vào metric tag.

Listener có thể được gọi ngay trong quá trình phát sự kiện, trên thread phát sự kiện. Vì vậy, hãy coi callback là một phần của đường thực thi cần giữ nhanh. Tránh thực hiện trong callback:

- Gọi HTTP đến hệ thống logging hoặc monitoring.
- Ghi đồng bộ vào cơ sở dữ liệu.
- Chờ khóa hoặc chờ một thread khác.
- Serialize payload lớn hoặc exception graph phức tạp.
- Thực hiện phép tính tốn CPU không cần thiết.
- Ném exception ngược lại luồng phát sự kiện.

Một listener chậm có thể làm tăng thời gian của lời gọi đang được bảo vệ hoặc làm chậm luồng phát event. Mục tiêu của listener là ghi nhận nhanh, không trở thành một phụ thuộc mới trong đường xử lý.

## 9. Tách xử lý nặng khỏi callback

Nếu cần xử lý event nặng, có thể đẩy một bản ghi nhỏ vào hàng đợi nội bộ có giới hạn rồi để worker riêng xử lý. Callback chỉ nên tạo một event record nhỏ và thử enqueue không chờ:

    record ResilienceEventRecord(
        String breakerName,
        String eventType,
        Instant occurredAt
    ) {}

    void onCircuitBreakerEvent(CircuitBreakerEvent event) {
        ResilienceEventRecord record = new ResilienceEventRecord(
            event.getCircuitBreakerName(),
            event.getEventType().name(),
            event.getCreationTime()
        );

        if (!eventQueue.offer(record)) {
            droppedEventCounter.increment();
        }
    }

Đây là ví dụ minh họa. Kiểu getter và tên event có thể khác theo phiên bản Resilience4j. eventQueue nên là hàng đợi có giới hạn, chẳng hạn ArrayBlockingQueue. offer không chờ nếu hàng đợi đầy; callback tăng counter để quan sát số event bị bỏ.

Worker riêng có thể batch dữ liệu và gửi sang hệ thống quan sát. Khi thiết kế, cần quyết định rõ:

- Hàng đợi đầy thì bỏ event nào, gộp event nào hoặc ghi nhận counter nào.
- Có cần ưu tiên STATE_TRANSITION, ERROR và CALL_NOT_PERMITTED hơn SUCCESS không.
- Worker lỗi thì retry có giới hạn hay bỏ dữ liệu.
- Khi ứng dụng dừng, có cần drain một lượng event cuối cùng hay không.
- Dữ liệu gửi đi có cần loại bỏ thông tin nhạy cảm không.

Không dùng hàng đợi không giới hạn. Nếu hệ thống đích chậm, hàng đợi sẽ tăng liên tục và chuyển vấn đề từ callback sang bộ nhớ heap. Không block thread phát sự kiện để chờ hàng đợi có chỗ trống; việc đó có thể làm tăng latency của request được bảo vệ.

Với ứng dụng reactive, có thể chuyển EventPublisher thành Reactor stream và dùng scheduler phù hợp cho bước xử lý downstream. Tuy nhiên, cần quản lý subscription, backpressure và queue giới hạn. Không subscribe một stream event không kiểm soát rồi để consumer chạy vô hạn.

## 10. Chọn event để log và metric

Không phải event nào cũng cần ghi log ở mức INFO. Với lưu lượng lớn, ghi một log cho mọi SUCCESS có thể tạo lượng log vượt xa giá trị điều tra.

Một chính sách thường dễ vận hành:

| Event | Cách quan sát gợi ý |
| --- | --- |
| STATE_TRANSITION | Log ở mức phù hợp vì đây là thay đổi quan trọng trong hành vi bảo vệ. |
| ERROR | Tăng counter và log có kiểm soát; tránh ghi lặp stack trace quá nhiều. |
| CALL_NOT_PERMITTED | Tăng counter để đo số lời gọi bị breaker chặn; có thể tổng hợp theo khoảng thời gian. |
| SUCCESS | Chủ yếu dùng metric tổng hợp; không nhất thiết log từng lần gọi. |
| IGNORED_ERROR | Theo dõi riêng để phát hiện exception đang bị loại khỏi failure rate. |
| RESET | Ghi nhận thao tác vận hành và lý do nếu ứng dụng có quy trình reset. |

Sự kiện và metric có mục đích khác nhau. Event hữu ích để xem một diễn biến cụ thể; metric hữu ích để tổng hợp xu hướng theo thời gian và cảnh báo. Không nên dùng event buffer như nguồn dữ liệu duy nhất cho dashboard dài hạn vì các event cũ sẽ bị ghi đè.

Đối với metric, dùng tên breaker hoặc nhóm dịch vụ có số lượng hữu hạn. Tránh gắn message exception làm tag. Với log, có thể giữ loại exception và correlation ID theo chính sách bảo mật, nhưng không ghi token, cookie, payload nhạy cảm hoặc dữ liệu cá nhân không cần thiết.

## 11. Xem event qua Spring Boot Actuator

Khi sử dụng Resilience4j Spring Boot integration cùng Actuator, có thể có các endpoint liệt kê instance và event. Ví dụ:

- /actuator/circuitbreakers liệt kê tên các circuit breaker.
- /actuator/circuitbreakerevents trả về các sự kiện gần đây của circuit breaker.
- Các cơ chế khác có endpoint tương ứng cho Retry, RateLimiter, Bulkhead và TimeLimiter khi được tích hợp.

Có thể cấu hình expose những endpoint cần dùng:

    management:
      endpoints:
        web:
          exposure:
            include: health,metrics,circuitbreakers,circuitbreakerevents

Endpoint và tên endpoint có thể thay đổi theo phiên bản, dependency và cấu hình Actuator. Hãy kiểm tra endpoint thực tế sau khi ứng dụng khởi động. eventConsumerBufferSize điều chỉnh dung lượng buffer của event consumer trong tích hợp tương ứng; số sự kiện endpoint trả về còn phụ thuộc cách triển khai endpoint và phiên bản.

Các endpoint event có thể chứa tên instance, thời điểm, exception message và thời lượng. Hãy bảo vệ chúng bằng authentication, network policy hoặc management port riêng. Không expose endpoint quản trị công khai chỉ để tiện debug. Trong production, chỉ expose các endpoint thực sự cần thiết và kiểm tra dữ liệu event trước khi chia sẻ ra ngoài.

## 12. Kiểm tra khi nhiều instance ứng dụng cùng chạy

Mỗi JVM thường có registry và event consumer buffer riêng. Nếu order-service chạy nhiều pod, mỗi pod có thể có một breaker inventory cùng tên nhưng trạng thái và event history độc lập.

Ví dụ:

    order-pod-1: inventory buffer [E1, E2, E3]
    order-pod-2: inventory buffer [E4, E5, E6]
    order-pod-3: inventory buffer [E7, E8, E9]

Đây là các lịch sử cục bộ. Endpoint trên pod 1 không tự trả event từ pod 2 và pod 3. Khi điều tra, hãy xác định pod hoặc instance ứng dụng đang phục vụ request. Nếu cần góc nhìn toàn hệ thống, gửi log/metric/tracing từ từng pod về nền tảng tập trung.

Không dùng một EventConsumerRegistry trong bộ nhớ để thay thế event broker hoặc kho log bền vững. Nếu cần lưu sự kiện phục vụ kiểm toán hoặc điều tra dài hạn, hãy dùng hệ thống lưu trữ có retention, phân quyền và khả năng truy vấn phù hợp.

## 13. Bài thực hành: điều chỉnh buffer và đo chi phí

Tạo một ứng dụng có hai breaker inventory và pricing. Thực hiện:

1. Bật Resilience4j event integration và cấu hình eventConsumerBufferSize của inventory là 5, pricing là 20.
2. Đăng ký listener cho STATE_TRANSITION, ERROR và CALL_NOT_PERMITTED của inventory.
3. Gửi lần lượt các lời gọi thành công, thất bại và đủ lỗi để breaker chuyển OPEN.
4. Đọc CircularEventConsumer hoặc Actuator event endpoint để xem các event gần nhất.
5. Tạo nhiều hơn 5 event và xác nhận buffer inventory chỉ giữ 5 event mới nhất.
6. Thay đổi slidingWindowSize nhưng giữ nguyên eventConsumerBufferSize; xác nhận hai thay đổi có tác dụng khác nhau.
7. Tăng lưu lượng và đo thời gian phản hồi khi listener chỉ tăng metric so với listener ghi log đồng bộ.
8. Thử một consumer dùng hàng đợi có giới hạn; làm worker chậm để xác nhận callback không block và số event bị drop được đếm.
9. Chạy nhiều pod và kiểm tra event history của từng pod không tự hợp nhất.
10. Kiểm tra quyền truy cập endpoint Actuator và loại bỏ thông tin nhạy cảm khỏi event/log.

Khi hoàn thành, bạn cần giải thích được eventConsumerBufferSize giữ lịch sử để quan sát, slidingWindowSize phục vụ quyết định breaker, circular buffer ghi đè event cũ khi đầy và listener nặng có thể làm chậm request. Hãy chọn dung lượng theo số breaker, tốc độ event và khoảng thời gian điều tra; dùng metric và log tập trung cho nhu cầu lưu trữ dài hạn.

## Tài liệu tham khảo

- Resilience4j — CircuitBreaker: https://resilience4j.readme.io/docs/circuitbreaker
- Resilience4j — Getting Started và event endpoints: https://resilience4j.readme.io/docs/getting-started-3
- Spring Cloud CircuitBreaker — Resilience4J: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html

