# Thời gian sự kiện, thời gian xử lý và vai trò của đồng hồ

Trong một pipeline reactive, một sự kiện có thể được tạo ở một thời điểm, đi qua mạng hoặc hàng đợi trong một khoảng thời gian, rồi mới được ứng dụng tiếp nhận và xử lý. Ba thời điểm này không nhất thiết trùng nhau. Nếu dùng nhầm thời gian xử lý để đại diện cho thời điểm nghiệp vụ xảy ra, hệ thống có thể xếp sai thứ tự sự kiện, tính sai độ trễ hoặc gom dữ liệu vào cửa sổ thời gian không đúng với yêu cầu.

Khi làm việc với Reactor, cần phân biệt **event time** (thời gian sự kiện xảy ra), **processing time** (thời gian hệ thống xử lý sự kiện) và thời gian tiếp nhận ở biên ứng dụng. Đồng hồ Java và Scheduler của Reactor cũng có vai trò khác nhau: đồng hồ tường phù hợp để ghi mốc thời gian có thể trao đổi giữa hệ thống, đồng hồ đơn điệu phù hợp để đo khoảng thời gian, còn Scheduler điều khiển thời điểm thực thi các toán tử theo thời gian.

## 1. Ba mốc thời gian trong vòng đời sự kiện

Một sự kiện có thể đi qua các giai đoạn sau:

1. Thiết bị hoặc dịch vụ nguồn tạo ra sự kiện.
2. Sự kiện được truyền qua mạng, broker hoặc hàng đợi.
3. Ứng dụng nhận sự kiện và đưa nó vào pipeline.
4. Một operator hoặc handler bắt đầu xử lý.
5. Kết quả được ghi xuống kho dữ liệu hoặc gửi đến hệ thống khác.

Các mốc này tạo ra những khái niệm thời gian khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event time | Thời điểm sự kiện thực sự xảy ra theo đồng hồ của nguồn | Cảm biến ghi nhận nhiệt độ lúc 10:00:02 |
| Ingestion time | Thời điểm hệ thống tiếp nhận sự kiện | API nhận bản tin lúc 10:00:05 |
| Processing time | Thời điểm một bước xử lý diễn ra | Worker bắt đầu tính toán lúc 10:00:06 |
| Completion time | Thời điểm một bước xử lý hoàn tất | Kết quả được tạo lúc 10:00:07 |

Event time trả lời câu hỏi “việc gì đã xảy ra khi nào?”. Processing time trả lời câu hỏi “hệ thống xử lý nó khi nào?”. Ingestion time nằm giữa hai mốc và hữu ích để đo thời gian truyền hoặc chờ trước khi xử lý.

Ví dụ, một thiết bị phát bản tin có occurredAt = 10:00:02, nhưng mạng bị gián đoạn nên ứng dụng chỉ nhận lúc 10:00:12. Nếu báo cáo cần thống kê số lần cảnh báo theo thời điểm sự cố, phải dựa vào event time. Nếu dashboard cần hiển thị độ trễ xử lý hiện tại, cần dùng ingestion time và processing time.

## 2. Mô hình dữ liệu nên giữ rõ event time

Đừng thay timestamp nghiệp vụ bằng thời điểm nhận dữ liệu. Hãy lưu event time trong bản tin và tạo mốc tiếp nhận riêng ở biên hệ thống.

Ví dụ một kiểu dữ liệu:

    import java.time.Instant;

    record SensorEvent(
        String sensorId,
        long sequence,
        Instant occurredAt,
        double temperature
    ) {}

    record ReceivedSensorEvent(
        SensorEvent event,
        Instant receivedAt
    ) {}

occurredAt đến từ thiết bị hoặc hệ thống phát sự kiện. receivedAt do ứng dụng tạo khi tiếp nhận. sequence giúp phân biệt thứ tự phát trong phạm vi thiết bị, đặc biệt khi hai sự kiện có cùng timestamp hoặc đồng hồ thiết bị không đủ chính xác.

Ở biên tiếp nhận, có thể dùng Clock được inject:

    import java.time.Clock;
    import java.time.Instant;
    import reactor.core.publisher.Mono;

    class SensorIngress {
        private final Clock clock;

        SensorIngress(Clock clock) {
            this.clock = clock;
        }

        Mono<ReceivedSensorEvent> receive(SensorEvent event) {
            Instant receivedAt = clock.instant();
            return Mono.just(
                new ReceivedSensorEvent(event, receivedAt)
            );
        }
    }

Trong ứng dụng Spring, Clock.systemUTC() có thể được khai báo thành bean và inject vào các thành phần cần tạo timestamp. Nhờ vậy, nguồn thời gian có thể được thay bằng đồng hồ cố định trong kiểm thử.

Không nên ghi đè occurredAt bằng clock.instant() tại tầng ingress. Nếu cần cả hai thông tin, giữ cả hai trường. Việc lưu tách biệt cho phép phân tích thời gian truyền, thời gian chờ và thời điểm nghiệp vụ mà không làm mất ngữ nghĩa ban đầu.

## 3. Đồng hồ tường và đồng hồ đơn điệu

Java có nhiều cách đọc thời gian, nhưng không phải cách nào cũng phù hợp cho mọi phép đo.

### 3.1. Đồng hồ tường: Instant và Clock

Instant biểu diễn một thời điểm trên dòng thời gian UTC. Clock là abstraction cung cấp thời điểm hiện tại và cho phép thay nguồn thời gian trong kiểm thử.

    Instant now = Instant.now();
    Instant receivedAt = clock.instant();

Đồng hồ tường phù hợp để:

- Ghi timestamp vào event, log hoặc database.
- So sánh thời điểm giữa các hệ thống khi đồng hồ đã được đồng bộ ở mức chấp nhận được.
- Tạo deadline nghiệp vụ có thể lưu và truyền qua mạng.
- Hiển thị ngày giờ cho người dùng sau khi chuyển sang múi giờ phù hợp.

Đồng hồ tường có thể được điều chỉnh bởi hệ điều hành hoặc dịch vụ đồng bộ thời gian. Vì vậy, hai lần đọc liên tiếp có thể không tăng đều; thời gian có thể nhảy tiến hoặc lùi. Đồng hồ của hai máy cũng có thể lệch nhau. Không nên dùng Instant.now() hoặc System.currentTimeMillis() để đo chính xác thời lượng của một thao tác dài.

### 3.2. Đồng hồ đơn điệu: đo khoảng thời gian

Để đo thời lượng trong cùng tiến trình, dùng System.nanoTime(). Giá trị này không phải timestamp lịch và không thể chuyển thành ngày giờ UTC; nó được thiết kế để so sánh hiệu giữa hai lần đọc.

    long startedAt = System.nanoTime();
    performWork();
    long elapsedNanos = System.nanoTime() - startedAt;

Phép trừ này cho thời lượng đã trôi qua và không bị ảnh hưởng bởi việc đồng hồ tường được chỉnh giờ. Không lưu nanoTime() như timestamp nghiệp vụ và không so sánh trực tiếp giá trị nanoTime() giữa hai máy.

Với xử lý reactive, cần bắt đầu đo ở thời điểm subscription thực sự chạy, không phải lúc lắp ráp publisher:

    Mono<Result> measured =
        Mono.defer(() -> {
            long startedAt = System.nanoTime();

            return service.process(command)
                .doFinally(signal -> {
                    long elapsed =
                        System.nanoTime() - startedAt;
                    metrics.recordProcessingNanos(elapsed, signal);
                });
        });

Mono.defer tạo mốc bắt đầu riêng cho mỗi subscription. doFinally ghi nhận thời lượng khi luồng hoàn tất, lỗi hoặc bị hủy. Nếu đặt long startedAt bên ngoài defer, thời gian chờ giữa lúc assembly và lúc subscribe cũng có thể bị tính nhầm vào thời lượng xử lý.

### 3.3. Múi giờ không phải là loại đồng hồ

Instant không mang múi giờ; nó xác định một thời điểm UTC. Múi giờ chỉ tham gia khi chuyển thời điểm đó thành ngày giờ địa phương để hiển thị hoặc áp dụng quy tắc lịch.

    ZonedDateTime localTime =
        receivedAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

Lưu timestamp dưới dạng Instant giúp dữ liệu trao đổi giữa các dịch vụ nhất quán. Chỉ chuyển sang ZonedDateTime ở nơi cần áp dụng múi giờ, chẳng hạn hiển thị lịch hoặc tính giờ làm việc tại một địa điểm.

## 4. Độ trễ: chọn đúng hai mốc để trừ

“Độ trễ” không phải một đại lượng duy nhất. Cần xác định đang đo khoảng nào:

| Chỉ số | Công thức khái quát | Ý nghĩa |
|---|---|---|
| Ingestion delay | receivedAt − occurredAt | Thời gian từ lúc sự kiện xảy ra đến lúc ứng dụng nhận |
| Queue delay | processingStartedAt − receivedAt | Thời gian sự kiện chờ trước khi xử lý |
| Processing duration | processingCompleted − processingStarted | Thời gian một bước xử lý |
| End-to-end duration | completedAt − occurredAt | Thời gian từ lúc xảy ra đến khi có kết quả |

Ingestion delay và end-to-end duration thường trừ các timestamp được tạo ở những máy khác nhau. Kết quả có thể bị ảnh hưởng bởi clock skew, tức độ lệch giữa đồng hồ nguồn và đồng hồ ứng dụng. Nếu nguồn phát sự kiện nhanh hơn đồng hồ nhận, phép trừ có thể cho kết quả âm.

Với queue delay hoặc processing duration trong cùng tiến trình, ưu tiên đo bằng System.nanoTime() để tránh điều chỉnh đồng hồ tường. Nếu cần ghi timestamp để đối chiếu giữa các dịch vụ, vẫn lưu Instant riêng và hiểu rằng độ chính xác phụ thuộc đồng bộ đồng hồ.

Ví dụ ghi nhận thời điểm xử lý:

    Mono<ProcessedEvent> process(ReceivedSensorEvent received) {
        return Mono.defer(() -> {
            long startedNanos = System.nanoTime();
            Instant processingStartedAt = clock.instant();

            return processor.process(received.event())
                .map(result -> new ProcessedEvent(
                    result,
                    received.receivedAt(),
                    processingStartedAt,
                    clock.instant()
                ))
                .doFinally(signal -> {
                    long durationNanos =
                        System.nanoTime() - startedNanos;
                    metrics.recordDuration(durationNanos, signal);
                });
        });
    }

Trong ví dụ, processingStartedAt và thời điểm hoàn tất dùng cho log hoặc truy vết. durationNanos dùng để đo chính xác hơn thời lượng trong tiến trình. Mô hình dữ liệu thực tế có thể cần thêm correlation ID, event ID và trạng thái kết thúc.

## 5. Vai trò của Scheduler trong các toán tử theo thời gian

Reactor Scheduler vừa quyết định nơi thực thi task, vừa cung cấp nguồn thời gian để lập lịch các thao tác. Các toán tử như interval, delayElements, timeout, buffer(Duration) và window(Duration) dựa vào Scheduler để xác định khi nào phát tick, trì hoãn tín hiệu hoặc đóng một cửa sổ.

Ví dụ:

    Flux<Long> ticks =
        Flux.interval(Duration.ofSeconds(1));

    Flux<Event> delayed =
        events.delayElements(Duration.ofMillis(250));

Flux.interval phát dãy số theo chu kỳ. delayElements trì hoãn từng phần tử trước khi chuyển xuống downstream. Những toán tử này không sửa event time bên trong payload; chúng điều khiển thời điểm tín hiệu được phát trong pipeline.

Có thể chỉ định Scheduler tường minh:

    Flux<Event> delayed =
        events.delayElements(
            Duration.ofMillis(250),
            Schedulers.parallel()
        );

Việc truyền Scheduler giúp kiểm soát nơi các task theo thời gian được thực thi và thuận tiện khi cấu hình hoặc kiểm thử. Nó không có nghĩa dữ liệu sự kiện được sắp xếp theo timestamp nghiệp vụ.

### 5.1. Thời gian của toán tử không phải event time

Các toán tử như window(Duration.ofSeconds(10)) và buffer(Duration.ofSeconds(10)) tạo nhóm theo nhịp thời gian của Scheduler tại vị trí toán tử. Với nguồn sự kiện đến từ mạng, đây thường là processing-time window: phần tử được đưa vào cửa sổ dựa trên lúc pipeline quan sát nó.

    Flux<List<Event>> batches =
        events.buffer(Duration.ofSeconds(10));

Ví dụ, sự kiện có occurredAt lúc 10:00:01 nhưng chỉ đến ứng dụng lúc 10:00:14 sẽ được gom theo cửa sổ mà pipeline đang mở lúc 10:00:14. Nó không tự động quay lại cửa sổ 10:00:00 chỉ vì timestamp trong payload cũ hơn.

Đây là hành vi phù hợp cho nhiều tác vụ vận hành, như gom request theo mỗi mười giây hoặc tổng hợp throughput theo thời gian hệ thống nhận. Nếu yêu cầu là thống kê theo thời điểm nghiệp vụ xảy ra, cần xây dựng logic event-time riêng hoặc dùng một hệ thống xử lý stream có hỗ trợ watermark và xử lý sự kiện đến muộn.

## 6. timestamp() và elapsed() trong Reactor

Hai toán tử hữu ích để quan sát thời gian ở vị trí một pipeline xử lý tín hiệu là timestamp() và elapsed().

### 6.1. timestamp(): gắn thời điểm quan sát

timestamp() biến mỗi phần tử thành một cặp gồm timestamp tính bằng milliseconds và giá trị gốc. Timestamp này phản ánh thời điểm Scheduler của operator quan sát phần tử, không nhất thiết là event time trong payload.

    Flux<Tuple2<Long, Event>> observed =
        events.timestamp();

    Flux<ObservedEvent> observedEvents =
        events.timestamp()
            .map(tuple -> new ObservedEvent(
                Instant.ofEpochMilli(tuple.getT1()),
                tuple.getT2()
            ));

Nếu cần giữ cả thời gian nguồn và thời gian quan sát, hãy lưu chúng ở hai trường riêng. Đặt timestamp() ngay sau nguồn nhận dữ liệu giúp đo mốc quan sát sớm; đặt sau một operator có thể làm timestamp phản ánh thời điểm phần tử đi qua vị trí muộn hơn trong pipeline.

Có thể truyền Scheduler cho timestamp để chỉ rõ nguồn thời gian:

    Flux<Tuple2<Long, Event>> observed =
        events.timestamp(Schedulers.parallel());

### 6.2. elapsed(): đo khoảng cách giữa các tín hiệu

elapsed() phát một cặp gồm số milliseconds đã trôi qua và phần tử hiện tại. Với phần tử đầu tiên, khoảng thời gian được tính từ lúc subscription bắt đầu; với các phần tử tiếp theo, khoảng thời gian được tính từ tín hiệu trước đó.

Khoảng thời gian của operator được tính theo nguồn thời gian của Scheduler mà nó sử dụng. Điều này phù hợp để quan sát nhịp tín hiệu trong pipeline và có thể kiểm soát bằng virtual time khi kiểm thử. Nếu cần phép đo thời lượng đơn điệu, độc lập với điều chỉnh đồng hồ tường, hãy đo bằng System.nanoTime() quanh thao tác cần theo dõi.

    Flux<Tuple2<Long, Event>> gaps =
        events.elapsed();

    Flux<Event> measured =
        events.elapsed()
            .doOnNext(tuple ->
                metrics.recordInterArrivalMillis(tuple.getT1())
            )
            .map(Tuple2::getT2);

Operator này hữu ích để đo khoảng cách giữa các tín hiệu mà pipeline quan sát. Nó không đo thời gian xử lý hoàn tất của từng event nếu handler xử lý bất đồng bộ ở phía sau. Để đo thời lượng xử lý, đặt phép đo quanh publisher thực hiện công việc như ví dụ Mono.defer ở phần trước.

## 7. Event time, thứ tự sự kiện và dữ liệu đến muộn

Trong hệ thống phân tán, thứ tự đến không nhất thiết là thứ tự xảy ra. Một sự kiện cũ có thể bị giữ trong mạng hoặc broker và đến sau sự kiện mới. Nếu sắp xếp chỉ theo ingestion time, báo cáo có thể phản ánh thứ tự nhận chứ không phản ánh thứ tự nghiệp vụ.

Ví dụ:

| Sự kiện | Event time | Thời điểm nhận |
|---|---|---|
| A | 10:00:01 | 10:00:02 |
| B | 10:00:03 | 10:00:04 |
| C | 10:00:02 | 10:00:09 |

Thứ tự nhận là A, B, C; thứ tự event time là A, C, B. Nếu tính tổng theo từng phút, thứ tự có thể không quan trọng. Nếu phát hiện chuyển trạng thái, tính chuỗi hành vi hoặc xử lý giao dịch phụ thuộc thứ tự, cần xác định quy tắc sắp xếp và xử lý late event.

Một timestamp đơn lẻ không luôn đủ để xác định thứ tự tuyệt đối. Có thể kết hợp:

- Sequence number do nguồn cấp trong phạm vi một thiết bị hoặc partition.
- Event ID để nhận diện và loại trùng.
- Event time để nhóm theo thời điểm nghiệp vụ.
- Quy tắc tie-breaker khi nhiều sự kiện có cùng timestamp.

Không nên giả định timestamp từ nhiều máy luôn có độ chính xác đủ để xác định thứ tự từng millisecond. Nếu thứ tự là yêu cầu nghiệp vụ nghiêm ngặt, ưu tiên sequence hoặc thứ tự được bảo đảm bởi partition/aggregate phù hợp.

### 7.1. Watermark và late event

Khi xử lý theo event time, hệ thống cần một cách ước lượng rằng phần lớn sự kiện trước một mốc đã đến. Watermark là mốc tiến độ sự kiện được hệ thống xem là đã đủ an toàn để đóng hoặc hoàn tất một cửa sổ event-time, theo chính sách cho phép dữ liệu đến muộn.

Một cách hình dung đơn giản là lấy timestamp lớn nhất đã quan sát trừ đi khoảng trễ cho phép:

    watermark = maxEventTimeSeen - allowedLateness

Nếu watermark đã vượt qua thời điểm kết thúc cửa sổ, một sự kiện đến sau nhưng có event time nằm trong cửa sổ cũ được xem là late event. Hệ thống cần chính sách rõ ràng: bỏ qua, cập nhật kết quả đã phát, phát correction hoặc đưa sự kiện sang luồng xử lý riêng.

Watermark không đơn giản là Instant.now(). Nó biểu thị tiến độ mà hệ thống suy ra từ dữ liệu và giả định về độ trễ. Reactor Core cung cấp nhiều toán tử thời gian dựa trên Scheduler, nhưng không tự động biến window(Duration) thành cửa sổ event-time có watermark. Nếu cần semantics event-time đầy đủ, phải xây dựng cơ chế theo timestamp và watermark hoặc dùng công cụ stream processing chuyên dụng.

## 8. Kiểm thử thời gian với Clock cố định

Logic nghiệp vụ tạo timestamp bằng Clock có thể được kiểm thử mà không cần chờ đồng hồ thật:

    import java.time.Clock;
    import java.time.Instant;
    import java.time.ZoneOffset;

    Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-22T03:00:00Z"),
        ZoneOffset.UTC
    );

    Instant receivedAt = fixedClock.instant();

Mỗi lần gọi instant() trên fixed clock đều trả cùng một thời điểm. Điều này hữu ích khi kiểm tra logic như xác định bản tin đến muộn, gán ingestion timestamp hoặc tính ngày nghiệp vụ.

Có thể kiểm tra việc thay clock bằng constructor injection:

    class EventStampingService {
        private final Clock clock;

        EventStampingService(Clock clock) {
            this.clock = clock;
        }

        Instant receivedAt() {
            return clock.instant();
        }
    }

Trong production truyền Clock.systemUTC(), còn trong unit test truyền Clock.fixed(...). Không cần thay đổi logic nghiệp vụ chỉ để kiểm soát thời gian.

Lưu ý: Clock.fixed chỉ cố định thời gian mà mã ứng dụng đọc từ Clock. Nó không tự thay đổi thời gian của Reactor Scheduler. Một toán tử delayElements vẫn dùng Scheduler riêng và có thể tiếp tục chờ theo thời gian thực nếu không cấu hình virtual time.

## 9. Kiểm thử toán tử thời gian bằng virtual time

Chờ thật trong kiểm thử làm test chậm và dễ không ổn định. StepVerifier hỗ trợ virtual time để tiến đồng hồ giả lập qua các khoảng thời gian mà không phải chờ tương ứng ngoài đời.

Ví dụ kiểm tra Flux.interval:

    import java.time.Duration;
    import reactor.core.publisher.Flux;
    import reactor.test.StepVerifier;

    StepVerifier.withVirtualTime(
            () -> Flux.interval(Duration.ofSeconds(1))
                .take(3)
        )
        .thenAwait(Duration.ofSeconds(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();

Publisher được tạo bên trong Supplier truyền cho withVirtualTime. Nhờ vậy, virtual scheduler được cài đặt trước khi các toán tử thời gian được lắp ráp. thenAwait tiến thời gian giả lập ba giây và verifier xác nhận ba tick cùng tín hiệu hoàn tất.

Nếu truyền một Scheduler tường minh do ứng dụng tự tạo vào operator, StepVerifier không nhất thiết thay thế Scheduler đó. Trong trường hợp này, hãy inject Scheduler vào thành phần cần kiểm thử và cung cấp virtual scheduler tương ứng trong test.

Có thể kết hợp Clock cố định và virtual time: Clock kiểm soát timestamp nghiệp vụ, còn virtual scheduler kiểm soát timer và delay của Reactor. Hai nguồn thời gian giải quyết hai nhu cầu khác nhau và cần được cấu hình độc lập.

## 10. Chọn nguồn thời gian cho từng mục đích

| Nhu cầu | Nên dùng | Tránh dùng |
|---|---|---|
| Lưu thời điểm sự kiện xảy ra | Instant do nguồn cung cấp | Thời điểm pipeline nhận thay cho event time |
| Tạo ingestion timestamp | Clock.instant() | System.nanoTime() |
| Ghi timestamp xử lý để truy vết | Clock.instant() hoặc timestamp từ Scheduler | Giá trị nanoTime như ngày giờ |
| Đo thời lượng xử lý trong một tiến trình | System.nanoTime() hoặc công cụ đo dựa trên monotonic time | Hiệu hai lần Instant.now() khi cần đo chính xác |
| Lập lịch interval, delay, timeout | Reactor Scheduler | Tự dùng Thread.sleep trong pipeline |
| Kiểm thử timer Reactor | StepVerifier virtual time và Scheduler có thể thay thế | Chờ nhiều giây trong test |
| Gom nhóm theo thời điểm nghiệp vụ | Event timestamp và logic event-time/watermark | Mặc định dùng buffer(Duration) hoặc window(Duration) |

Một nguyên tắc hữu ích là ghi rõ tên trường theo ngữ nghĩa: occurredAt, receivedAt, processingStartedAt, completedAt. Tránh một trường chung tên timestamp nếu không có quy ước rõ ràng về thời điểm nó đại diện.

## 11. Những lỗi thường gặp

**Dùng processing time làm event time.** Sự kiện đến trễ sẽ bị gán vào cửa sổ sai với thời điểm nghiệp vụ. Hãy giữ timestamp do nguồn cung cấp và tạo ingestion time riêng.

**Dùng đồng hồ tường để đo thời lượng.** Đồng hồ hệ thống có thể bị điều chỉnh. Dùng System.nanoTime() cho phép đo khoảng thời gian trong cùng tiến trình.

**Cho rằng buffer(Duration) nhóm theo timestamp trong payload.** Operator dựa trên Scheduler và thời điểm tín hiệu đi qua pipeline. Event-time window cần logic riêng.

**Cho rằng timestamp() trả lại timestamp gốc của event.** Nó gắn thời điểm operator quan sát tín hiệu. Muốn biết lúc sự kiện xảy ra, đọc trường event time trong payload.

**Đặt mốc bắt đầu đo ở assembly.** Publisher có thể được subscribe muộn hoặc nhiều lần. Dùng defer để tạo mốc đo riêng cho mỗi subscription.

**Cho rằng Clock cố định cũng điều khiển Reactor timer.** Clock và Scheduler là hai abstraction độc lập. Dùng Clock cho timestamp ứng dụng và virtual scheduler cho toán tử thời gian.

**Tin tuyệt đối vào timestamp của thiết bị.** Đồng hồ nguồn có thể lệch hoặc nhảy. Kiểm tra timestamp bất thường, giữ sequence number và xác định chính sách cho sự kiện đến muộn.

## 12. Checklist thiết kế pipeline có yếu tố thời gian

Trước khi thêm toán tử thời gian, hãy xác định:

1. Thời điểm nào là event time, ingestion time và processing time?
2. Timestamp do thành phần nào tạo ra, dùng đồng hồ nào và có thể lệch bao nhiêu?
3. Cần đo một thời điểm lịch hay đo thời lượng trôi qua?
4. Toán tử đang dùng Scheduler nào và thời gian được tính ở vị trí nào trong pipeline?
5. Cửa sổ cần theo processing time hay event time?
6. Nếu sự kiện đến muộn hoặc timestamp nằm trong tương lai, hệ thống xử lý ra sao?
7. Có cần sequence number hoặc event ID để xác định thứ tự và loại trùng không?
8. Kiểm thử đã tách Clock của nghiệp vụ khỏi Scheduler của Reactor chưa?

Khi phân biệt đúng thời gian sự kiện, thời gian tiếp nhận và thời gian xử lý, pipeline reactive có thể vừa phản ánh chính xác ngữ nghĩa nghiệp vụ vừa đo được hiệu năng vận hành. Clock, System.nanoTime() và Reactor Scheduler bổ sung cho nhau: mỗi công cụ phục vụ một loại thời gian, và việc chọn đúng công cụ giúp các toán tử thời gian hoạt động dễ dự đoán, dễ kiểm thử.
