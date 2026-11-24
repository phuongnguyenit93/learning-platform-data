# Quan sát trạng thái, số lần chuyển mạch và thời gian giữ OPEN

## Mục tiêu của bài học

Circuit breaker chỉ bảo vệ hệ thống hiệu quả khi nhóm vận hành biết nó đang ở trạng thái nào, chuyển trạng thái bao nhiêu lần và mỗi lần mở kéo dài bao lâu. Một dashboard chỉ hiển thị tỷ lệ lỗi hiện tại chưa đủ để trả lời các câu hỏi như: breaker có đang OPEN không, phụ thuộc đã phục hồi chưa, breaker có liên tục đóng rồi mở lại hay không, và request đang bị từ chối trong bao lâu.

Spring Cloud CircuitBreaker kết hợp Resilience4j cung cấp sự kiện và metric để theo dõi các thông tin này. Cần hiểu giới hạn của từng loại dữ liệu: metric trạng thái là ảnh chụp hiện tại, event cho biết diễn biến chuyển trạng thái, còn thời gian giữ OPEN thường cần được tính từ các mốc chuyển trạng thái.

Sau bài học, bạn có thể:

- Theo dõi các trạng thái CLOSED, OPEN và HALF_OPEN của từng breaker.
- Đếm và phân tích các lần chuyển trạng thái, kể cả hiện tượng mở/đóng liên tục.
- Phân biệt thời gian cấu hình waitDurationInOpenState với thời gian OPEN quan sát thực tế.
- Đọc các metric Resilience4j qua Spring Boot Actuator và Micrometer.
- Ghi nhận thời điểm vào OPEN, thời điểm rời OPEN và tính thời lượng cho từng chu kỳ.
- Thiết kế dashboard và cảnh báo theo trạng thái, số lần từ chối và thời gian mở.
- Phân tích dữ liệu theo từng pod mà không nhầm trạng thái cục bộ với trạng thái toàn hệ thống.

## 1. Cần quan sát những gì?

Một circuit breaker có ba trạng thái hoạt động chính:

| Trạng thái | Ý nghĩa vận hành | Điều cần quan sát |
| --- | --- | --- |
| CLOSED | Cho phép lời gọi đi qua và ghi nhận kết quả. | Failure rate, slow call rate, độ trễ và lưu lượng lời gọi. |
| OPEN | Từ chối nhanh lời gọi mới trong thời gian chờ phục hồi. | Thời điểm mở, thời gian đang OPEN, số lời gọi bị từ chối. |
| HALF_OPEN | Cho phép một số lời gọi thử nghiệm để đánh giá phụ thuộc. | Số lời gọi thử, kết quả thử và trạng thái tiếp theo. |

Resilience4j còn có các trạng thái đặc biệt như FORCED_OPEN, DISABLED và METRICS_ONLY. Khi xây dashboard, cần biết phiên bản thư viện và trạng thái nào đang được sử dụng; không gom mọi trạng thái ngoài CLOSED vào cùng một nhãn lỗi nếu chúng có ý nghĩa vận hành khác nhau.

Một bộ quan sát hữu ích thường có các nhóm dữ liệu:

- Trạng thái hiện tại của từng breaker.
- Số lần chuyển CLOSED → OPEN, OPEN → HALF_OPEN, HALF_OPEN → CLOSED và HALF_OPEN → OPEN.
- Thời lượng mỗi chu kỳ OPEN và tuổi của một trạng thái OPEN đang diễn ra.
- Số lời gọi thành công, thất bại, chậm và bị từ chối.
- Failure rate và slow call rate so với ngưỡng cấu hình.
- Độ trễ của dịch vụ phụ thuộc và tỷ lệ fallback.

Các nhóm dữ liệu này bổ sung cho nhau. Trạng thái hiện tại cho biết breaker đang ở đâu; event cho biết nó đã đi qua những trạng thái nào; metric lời gọi cho biết mức độ ảnh hưởng đến request.

## 2. Phân biệt trạng thái hiện tại và lịch sử chuyển trạng thái

Metric trạng thái thường là gauge. Nó biểu diễn trạng thái tại thời điểm hệ thống metrics thu thập dữ liệu. Với Micrometer, Resilience4j xuất metric `resilience4j.circuitbreaker.state` với tag tên breaker và trạng thái, chẳng hạn `name=inventory`, `state=open`.

Trong định dạng Prometheus, mỗi trạng thái có thể được biểu diễn bằng một chuỗi thời gian riêng; giá trị 1 biểu thị trạng thái đang hoạt động và 0 biểu thị trạng thái đó không hoạt động. Hãy đọc tag state cùng giá trị gauge, không suy luận trạng thái từ một con số không có nhãn.

Metric trạng thái phù hợp để trả lời:

- Breaker inventory có đang OPEN ngay lúc này không?
- Có pod nào đang giữ breaker ở HALF_OPEN không?
- Trạng thái hiện tại có thay đổi giữa các lần scrape không?

Metric gauge không lưu toàn bộ lịch sử. Nếu breaker mở rồi đóng giữa hai lần scrape, dashboard chỉ lấy mẫu trạng thái có thể bỏ lỡ lần chuyển đó. Muốn biết chính xác số lần chuyển trạng thái và thời điểm xảy ra, hãy thu thập event.

Event chuyển trạng thái được phát khi breaker thay đổi trạng thái. Ví dụ:

    CLOSED -> OPEN
    OPEN -> HALF_OPEN
    HALF_OPEN -> CLOSED
    HALF_OPEN -> OPEN

Event có thể được ghi vào log, buffer gần đây hoặc chuyển thành metric counter. Nhờ đó, nhóm vận hành có thể phát hiện breaker đang flapping: mở, thử phục hồi, đóng rồi lại mở nhiều lần trong thời gian ngắn.

## 3. Các metric CircuitBreaker thường dùng

Khi tích hợp Resilience4j với Micrometer, những metric phổ biến gồm:

| Metric | Loại dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `resilience4j.circuitbreaker.state` | Gauge | Trạng thái hiện tại theo breaker và state. |
| `resilience4j.circuitbreaker.calls` | Timer | Thời lượng và số lần gọi theo kết quả, ví dụ successful, failed hoặc ignored. |
| `resilience4j.circuitbreaker.failure.rate` | Gauge | Tỷ lệ lỗi hiện tại trong sliding window. |
| `resilience4j.circuitbreaker.slow.call.rate` | Gauge | Tỷ lệ lời gọi chậm trong sliding window. |
| `resilience4j.circuitbreaker.buffered.calls` | Gauge | Số kết quả thành công/thất bại đang nằm trong cửa sổ thống kê. |
| `resilience4j.circuitbreaker.not.permitted.calls` | Counter | Tổng số lời gọi bị từ chối do breaker không cho phép. |
| `resilience4j.circuitbreaker.max.buffered.calls` | Gauge | Kích thước tối đa của cửa sổ lưu kết quả theo cấu hình. |

Tên metric và tag chi tiết có thể khác theo phiên bản Resilience4j, Micrometer và định dạng exporter. Hãy truy vấn danh sách metric thực tế của ứng dụng trước khi viết dashboard hoặc alert rule.

Metric calls cho biết kết quả của những lời gọi đã đi vào breaker. not.permitted.calls cho biết số lời gọi bị chặn nhanh; các lời gọi này không thực hiện thao tác phụ thuộc nên không được hiểu là request HTTP đã gửi đến server.

Failure rate và slow call rate phản ánh dữ liệu của sliding window. Chúng không phải tỷ lệ lỗi toàn bộ hệ thống từ khi ứng dụng khởi động. Khi cửa sổ trượt, kết quả cũ rời khỏi phép tính và tỷ lệ có thể thay đổi ngay cả khi không có sự kiện chuyển trạng thái mới.

## 4. Bật Actuator và Micrometer

Trong ứng dụng Spring Boot, có thể thêm Actuator và registry Micrometer phù hợp. Ví dụ Maven:

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>

Resilience4j có module Micrometer để bind metric của các instance. Trong nhiều cấu hình Spring Boot tích hợp Resilience4j, các binder và endpoint được tự động cấu hình khi dependency phù hợp có mặt. Với ứng dụng dùng Spring Cloud CircuitBreaker factory thuần, hãy xác nhận dependency và auto-configuration đang sử dụng; không giả định mọi endpoint Resilience4j Spring Boot đều xuất hiện chỉ vì có starter Spring Cloud CircuitBreaker.

Có thể expose một số endpoint quản trị cần thiết:

    management:
      endpoints:
        web:
          exposure:
            include: health,info,metrics,prometheus,circuitbreakers,circuitbreakerevents

Các endpoint thường dùng:

- `/actuator/metrics`: liệt kê metric đã đăng ký.
- `/actuator/metrics/resilience4j.circuitbreaker.state`: đọc metric trạng thái nếu binder đã đăng ký.
- `/actuator/metrics/resilience4j.circuitbreaker.calls`: đọc dữ liệu thời lượng và số lần gọi.
- `/actuator/prometheus`: xuất metric Prometheus khi registry tương ứng đã được cấu hình.
- `/actuator/circuitbreakers` và `/actuator/circuitbreakerevents`: có thể có trong tích hợp Resilience4j Spring Boot/Actuator để xem instance và sự kiện gần đây.

Endpoint cụ thể phụ thuộc phiên bản và module tích hợp. Hãy kiểm tra danh sách endpoint đang hoạt động thay vì sao chép cấu hình từ một phiên bản khác. Bảo vệ endpoint quản trị bằng authentication, network policy hoặc management port riêng; không expose thông tin trạng thái và exception nội bộ công khai.

## 5. Đếm số lần chuyển trạng thái

Có thể đăng ký listener với EventPublisher của từng breaker. Trong Spring Cloud CircuitBreaker dùng Resilience4j, factory customizer cho phép gắn listener khi breaker được tạo:

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryTransitionListener(
            CircuitBreakerTransitionObserver observer) {
        return factory -> factory.addCircuitBreakerCustomizer(
            circuitBreaker -> circuitBreaker.getEventPublisher()
                .onStateTransition(observer::record),
            "inventory"
        );
    }

Ví dụ chỉ gắn listener cho breaker tên inventory. Nếu ứng dụng tạo breaker với id khác, hãy đăng ký đúng tên hoặc dùng cơ chế đăng ký cho toàn bộ instance theo registry đang quản lý.

Một observer có thể tăng counter theo cặp trạng thái:

    public void record(CircuitBreakerOnStateTransitionEvent event) {
        StateTransition transition = event.getStateTransition();

        Counter.builder("app.circuitbreaker.state.transitions")
            .tag("breaker", event.getCircuitBreakerName())
            .tag("from", transition.getFromState().name())
            .tag("to", transition.getToState().name())
            .register(meterRegistry)
            .increment();
    }

Metric tùy chỉnh này cho phép truy vấn số lần chuyển CLOSED → OPEN hoặc HALF_OPEN → OPEN. Các tag from và to có tập giá trị hữu hạn nên phù hợp cho metric. Không gắn exception message, request ID, SKU hoặc địa chỉ URL đầy đủ làm tag vì chúng có thể tạo cardinality rất cao.

Listener được gọi trong luồng phát sự kiện. Hãy giữ callback ngắn: tăng counter hoặc ghi một bản ghi nhỏ. Không gọi HTTP, ghi cơ sở dữ liệu đồng bộ hay chờ một queue không giới hạn trong callback. Nếu cần xử lý nặng, chuyển bản ghi tối giản vào hàng đợi có giới hạn và đo số event bị bỏ.

## 6. Đo thời gian giữ OPEN

Resilience4j cung cấp metric trạng thái hiện tại và event chuyển trạng thái, nhưng thời gian một breaker đã ở OPEN trong một chu kỳ thường cần được suy ra từ hai mốc:

1. Thời điểm breaker chuyển sang OPEN.
2. Thời điểm breaker rời OPEN, thường là chuyển sang HALF_OPEN.

Thời lượng quan sát được:

    openDuration = timeLeavingOpen - timeEnteringOpen

Đây là thời gian thực tế breaker ở OPEN trong tiến trình, không nhất thiết bằng đúng `waitDurationInOpenState`.

Ví dụ, cấu hình `waitDurationInOpenState: 10s` đặt thời gian chờ trước khi breaker có thể chuyển sang HALF_OPEN. Nếu `automaticTransitionFromOpenToHalfOpenEnabled` là false, breaker thường chỉ thực hiện chuyển trạng thái khi có lời gọi tiếp theo sau khi thời gian chờ đã qua. Nếu không có request mới, breaker có thể tiếp tục ở OPEN lâu hơn 10 giây. Khi bật automatic transition, scheduler có thể chuyển breaker sang HALF_OPEN sau thời gian chờ mà không cần request kích hoạt.

Vì vậy, dashboard nên phân biệt:

- **Configured wait:** thời gian chờ cấu hình trước khi được phép thử phục hồi.
- **Observed OPEN duration:** thời gian từ event vào OPEN đến event rời OPEN.
- **Current OPEN age:** thời gian đã trôi qua kể từ lúc breaker vào OPEN nếu nó vẫn chưa rời trạng thái.

Nếu breaker vẫn OPEN khi ứng dụng khởi động lại, lịch sử trong bộ nhớ của tiến trình cũ có thể không còn. Với nhu cầu điều tra qua lần restart, cần ghi event ra log hoặc hệ thống lưu trữ tập trung.

## 7. Ví dụ ghi nhận thời lượng OPEN bằng Micrometer

Đoạn mã minh họa dưới đây giữ thời điểm vào OPEN trong bộ nhớ và ghi Timer khi breaker rời OPEN:

    import io.github.resilience4j.circuitbreaker.event.CircuitBreakerOnStateTransitionEvent;
    import io.github.resilience4j.circuitbreaker.CircuitBreaker;
    import io.github.resilience4j.circuitbreaker.CircuitBreaker.State;
    import io.github.resilience4j.circuitbreaker.CircuitBreaker.StateTransition;
    import io.micrometer.core.instrument.MeterRegistry;
    import io.micrometer.core.instrument.Timer;
    import java.time.Duration;
    import java.time.Instant;
    import java.util.concurrent.ConcurrentHashMap;
    import java.util.concurrent.ConcurrentMap;

    public class CircuitBreakerTransitionObserver {

        private final MeterRegistry meterRegistry;
        private final ConcurrentMap<String, Instant> openedAt =
            new ConcurrentHashMap<>();

        public CircuitBreakerTransitionObserver(MeterRegistry meterRegistry) {
            this.meterRegistry = meterRegistry;
        }

        public void record(CircuitBreakerOnStateTransitionEvent event) {
            StateTransition transition = event.getStateTransition();
            String name = event.getCircuitBreakerName();
            Instant observedAt = Instant.now();

            if (transition.getToState() == State.OPEN) {
                openedAt.put(name, observedAt);
                return;
            }

            if (transition.getFromState() == State.OPEN) {
                Instant start = openedAt.remove(name);
                if (start != null) {
                    Duration duration = Duration.between(start, observedAt);

                    Timer.builder("app.circuitbreaker.open.duration")
                        .description("Observed time spent in OPEN state")
                        .tag("breaker", name)
                        .register(meterRegistry)
                        .record(duration);
                }
            }
        }
    }

Đây là ví dụ để minh họa cách tính. Hãy kiểm tra package và API event theo phiên bản Resilience4j của dự án. `Instant.now()` ghi thời điểm observer nhận callback; nếu phiên bản event cung cấp creation timestamp đáng tin cậy, có thể dùng timestamp đó để giảm sai số do callback được xử lý trễ.

Map openedAt chỉ lưu trạng thái của tiến trình hiện tại. Nếu một breaker không bao giờ rời OPEN trước khi ứng dụng dừng, Timer cho chu kỳ đó chưa được ghi. Vì vậy, nên bổ sung một gauge current OPEN age hoặc log thời điểm vào OPEN để dashboard vẫn hiển thị tuổi của trạng thái đang diễn ra.

Khi một breaker được reset hoặc chuyển sang trạng thái đặc biệt, hãy quyết định cách kết thúc hoặc hủy chu kỳ đo tương ứng. Không để một timestamp cũ tiếp tục được dùng cho một chu kỳ OPEN mới.

## 8. Theo dõi số lần mở lại và hiện tượng flapping

Một breaker mở một lần trong lúc phụ thuộc gặp sự cố có thể là hành vi đúng. Nhưng nếu breaker liên tục chuyển:

    CLOSED -> OPEN -> HALF_OPEN -> CLOSED
                         |
                         +----> OPEN -> HALF_OPEN -> ...

thì phụ thuộc hoặc ngưỡng cấu hình có thể đang dao động quanh ranh giới. Hiện tượng này thường được gọi là flapping.

Các chỉ số giúp phát hiện:

- Số lần CLOSED → OPEN trong 5 phút hoặc 15 phút.
- Số lần HALF_OPEN → OPEN sau các lần thử phục hồi.
- Khoảng cách giữa hai lần mở liên tiếp.
- Tỷ lệ lời gọi bị từ chối khi breaker OPEN.
- Failure rate và slow call rate ngay trước khi mở.
- Độ trễ phụ thuộc trước, trong và sau chu kỳ mở.

Nếu breaker mở lại liên tục, hãy kiểm tra độ ổn định của dịch vụ phụ thuộc, timeout, sliding window, minimumNumberOfCalls, failureRateThreshold và slowCallRateThreshold. Một cửa sổ quá nhỏ có thể phản ứng mạnh với một cụm lỗi ngắn; một cửa sổ quá lớn có thể phản ứng chậm khi dịch vụ bắt đầu suy giảm.

Không giải quyết flapping bằng cách tăng waitDuration một cách máy móc. Hãy xem dữ liệu chuyển trạng thái và độ trễ để xác định phụ thuộc thực sự chưa phục hồi hay ngưỡng đang không phù hợp.

## 9. Dashboard nên có những thành phần nào?

Một dashboard theo từng breaker có thể được tổ chức thành các khu vực:

| Khu vực | Biểu đồ hoặc thông tin | Câu hỏi vận hành |
| --- | --- | --- |
| Trạng thái hiện tại | State gauge theo breaker và pod | Breaker nào đang OPEN hoặc HALF_OPEN? |
| Chuyển trạng thái | Counter/rate theo cặp from → to | Breaker mở bao nhiêu lần và có flapping không? |
| Thời gian OPEN | Timer histogram và current OPEN age | Mỗi chu kỳ mở kéo dài bao lâu? Breaker nào đang OPEN quá lâu? |
| Kết quả lời gọi | Successful, failed, ignored, not permitted | Request bị ảnh hưởng ở mức nào? |
| Chất lượng phụ thuộc | Failure rate, slow call rate, p95/p99 latency | Vì sao breaker mở? |
| Fallback | Số lần và loại fallback | Người dùng đang nhận phản hồi suy giảm bao nhiêu? |

Có thể đặt bộ lọc theo service, breaker name, môi trường và pod. Không cần đưa mọi dimension vào một biểu đồ; ưu tiên hiển thị xu hướng và cung cấp drill-down đến log/trace khi cần điều tra một request cụ thể.

Với nhiều pod, state gauge của mỗi pod là trạng thái cục bộ. Dashboard nên giữ tag instance/pod để biết pod nào đang OPEN. Nếu muốn biết có ít nhất một pod OPEN, có thể dùng phép tổng hợp phù hợp như max trên gauge trạng thái OPEN. Không cộng các gauge trạng thái như thể chúng là số lần chuyển trạng thái.

## 10. Thiết kế cảnh báo có thể hành động

Cảnh báo nên chỉ ra điều người vận hành cần làm. Một số quy tắc tham khảo:

- **Breaker OPEN kéo dài:** cảnh báo khi breaker vẫn OPEN quá khoảng thời gian vận hành cho phép.
- **Tỷ lệ chuyển CLOSED → OPEN tăng:** phát hiện phụ thuộc bắt đầu mất ổn định.
- **HALF_OPEN thất bại liên tiếp:** phụ thuộc chưa phục hồi sau thời gian chờ.
- **Not permitted tăng đột biến:** request đang bị chặn nhanh với số lượng lớn.
- **Failure rate hoặc slow call rate cao:** cảnh báo sớm trước hoặc trong lúc breaker mở.
- **OPEN duration tăng qua nhiều chu kỳ:** thời gian phục hồi của phụ thuộc đang xấu đi.

Chọn ngưỡng theo SLO và mức ảnh hưởng nghiệp vụ. Ví dụ, breaker bảo vệ một dịch vụ tùy chọn có thể chỉ cần cảnh báo khi OPEN kéo dài; breaker bảo vệ bước thanh toán hoặc xác thực có thể cần mức ưu tiên cao hơn.

Tránh tạo alert chỉ vì một lần chuyển OPEN ngắn. Nếu breaker hoạt động đúng để chặn một đợt lỗi thoáng qua, cảnh báo liên tục có thể gây nhiễu. Kết hợp thời lượng, tỷ lệ request bị ảnh hưởng, fallback và số lần mở lại để quyết định mức độ.

## 11. Phân tích dữ liệu theo từng pod

Circuit breaker thường giữ trạng thái và sliding window trong bộ nhớ của từng JVM. Nếu order-service chạy ba pod, mỗi pod có breaker inventory riêng. Một pod có thể OPEN trong khi hai pod khác vẫn CLOSED.

Điều này ảnh hưởng đến cách đọc dashboard:

- Một gauge OPEN trên pod A không chứng minh toàn bộ service đã OPEN.
- Một pod có tỷ lệ lỗi cao có thể đang gọi một instance phụ thuộc khác hoặc đang có cấu hình khác.
- Tổng not-permitted trên tất cả pod cho biết tổng lượng lời gọi bị chặn, nhưng cần giữ tag pod để tìm nơi phát sinh.
- Event history của một pod không tự đồng bộ sang pod khác.

Khi cần tổng hợp toàn hệ thống, giữ nhãn breaker và pod trong dữ liệu nguồn, sau đó chọn phép tổng hợp theo câu hỏi. Ví dụ, dùng max để kiểm tra có pod nào OPEN; dùng sum cho counter số lời gọi bị từ chối; dùng histogram aggregation để tính percentile thời lượng OPEN. Không cộng trực tiếp percentile hoặc gauge trạng thái giữa các pod.

Metric tag nên có cardinality kiểm soát. Breaker name, service và pod thường là các dimension vận hành hữu ích; không thêm request ID, user ID, SKU hoặc exception message vào tag.

## 12. Bài thực hành: quan sát một chu kỳ OPEN hoàn chỉnh

Tạo order-service gọi inventory-service bằng Spring Cloud CircuitBreaker và Resilience4j. Thực hiện:

1. Bật Actuator và Micrometer registry phù hợp.
2. Xác nhận các metric state, calls, failure rate, slow call rate và not-permitted xuất hiện.
3. Đăng ký listener cho sự kiện state transition của breaker inventory.
4. Tăng tải và làm inventory-service trả lỗi hoặc phản hồi chậm cho đến khi breaker chuyển CLOSED → OPEN.
5. Ghi lại thời điểm vào OPEN và xác nhận gauge state=open được bật.
6. Gửi thêm request trong lúc OPEN; xác nhận not-permitted tăng và fallback được thực thi.
7. Chờ quá waitDurationInOpenState; kiểm tra cấu hình automaticTransitionFromOpenToHalfOpenEnabled và xác định thời điểm thực tế chuyển HALF_OPEN.
8. Cho phép lời gọi thử thành công để breaker chuyển HALF_OPEN → CLOSED.
9. Tính thời lượng OPEN từ hai event chuyển trạng thái và so sánh với waitDuration đã cấu hình.
10. Lặp lại với lời gọi thử thất bại để breaker chuyển HALF_OPEN → OPEN.
11. Chạy hai pod và quan sát trạng thái cùng event history riêng của từng pod.
12. Tạo dashboard có state hiện tại, transition rate, open duration, not-permitted và failure/slow-call rate.

Khi hoàn thành, bạn cần phân biệt được gauge trạng thái với event lịch sử, hiểu vì sao thời gian OPEN thực tế có thể dài hơn waitDurationInOpenState và biết cách tính thời lượng từ event chuyển trạng thái. Hãy dùng metric cho xu hướng, event cho diễn biến, log/trace cho ngữ cảnh request và cảnh báo dựa trên mức ảnh hưởng thực tế.

## Tài liệu tham khảo

- Resilience4j — Micrometer metrics: https://resilience4j.readme.io/docs/micrometer
- Resilience4j — CircuitBreaker state machine and configuration: https://resilience4j.readme.io/docs/circuitbreaker
- Resilience4j — Spring Boot Actuator and metrics endpoints: https://resilience4j.readme.io/docs/getting-started-3
- Spring Cloud CircuitBreaker — Resilience4J integration: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html

