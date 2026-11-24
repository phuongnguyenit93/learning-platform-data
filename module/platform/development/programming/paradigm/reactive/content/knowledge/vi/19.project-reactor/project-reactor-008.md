# transform và transformDeferred trong tái sử dụng chuỗi

Khi nhiều pipeline cần cùng một nhóm phép biến đổi, ta thường muốn đóng gói các operator thành một đơn vị có thể tái sử dụng. Ví dụ, nhiều luồng cảm biến đều cần chuẩn hóa dữ liệu, loại bản tin không hợp lệ và ghi nhận metric; nhiều luồng đơn hàng đều cần áp dụng cùng quy tắc lọc và kiểm tra. Nếu sao chép các operator vào từng pipeline, logic dễ lệch nhau và mỗi lần thay đổi phải sửa nhiều nơi.

Project Reactor cung cấp hai operator để áp dụng một phép biến đổi lên toàn bộ publisher: transform và transformDeferred. Cả hai giúp gom một chuỗi operator thành một hàm có thể tái sử dụng. Điểm khác nhau quan trọng là thời điểm hàm biến đổi được gọi: transform áp dụng hàm khi lắp ráp pipeline, còn transformDeferred áp dụng hàm cho từng subscription.

Sự khác biệt đó ảnh hưởng trực tiếp đến state được tạo bên trong hàm, cấu hình theo subscriber và khả năng cô lập giữa các lần subscribe. Hiểu đúng thời điểm áp dụng giúp tái sử dụng operator mà không vô tình chia sẻ state giữa những người tiêu thụ độc lập.

## 1. Vì sao cần đóng gói một chuỗi operator?

Một pipeline thường có nhiều bước liên tiếp:

1. Chuẩn hóa dữ liệu đầu vào.
2. Loại dữ liệu sai hoặc không phù hợp.
3. Gắn thông tin bổ sung.
4. Ghi nhận metric hoặc trace.
5. Chuyển dữ liệu đến bước nghiệp vụ tiếp theo.

Nếu nhiều nguồn cần cùng chính sách, có thể viết một hàm nhận Flux và trả về Flux đã được biến đổi:

    Function<Flux<SensorReading>, Flux<SensorReading>> validateReadings =
        flux -> flux
            .filter(reading ->
                Double.isFinite(reading.celsius())
            )
            .filter(reading ->
                reading.celsius() >= -80.0
                    && reading.celsius() <= 150.0
            );

Hàm này mô tả một chuỗi operator. Nó không subscribe, không tự chạy nguồn và không tạo một luồng dữ liệu độc lập. Nó chỉ nhận publisher hiện tại rồi trả về publisher mới có thêm các bước xử lý.

Có thể áp dụng cùng hàm cho nhiều nguồn:

    Flux<SensorReading> roomA =
        sensorClient.readings("room-A")
            .transform(validateReadings);

    Flux<SensorReading> roomB =
        sensorClient.readings("room-B")
            .transform(validateReadings);

Mỗi pipeline có cùng chính sách kiểm tra. Khi quy tắc thay đổi, chỉ cần sửa hàm biến đổi tại một nơi.

## 2. transform áp dụng hàm khi lắp ráp pipeline

transform nhận một hàm biến đổi publisher và áp dụng hàm đó ngay khi gọi operator để xây dựng pipeline. Kết quả là một publisher mới; subscription và việc phát tín hiệu vẫn diễn ra sau đó khi có subscriber đăng ký.

Ví dụ:

    AtomicInteger transformCalls = new AtomicInteger();

    Flux<String> source = Flux.just("A", "B");

    Flux<String> transformed =
        source.transform(flux -> {
            int transformationId =
                transformCalls.incrementAndGet();

            return flux.map(value ->
                transformationId + ":" + value
            );
        });

    // Hàm biến đổi đã được gọi một lần khi pipeline được lắp ráp.
    assertEquals(1, transformCalls.get());

    StepVerifier.create(transformed)
        .expectNext("1:A", "1:B")
        .verifyComplete();

    StepVerifier.create(transformed)
        .expectNext("1:A", "1:B")
        .verifyComplete();

    assertEquals(1, transformCalls.get());

Trong ví dụ, transform gọi hàm biến đổi một lần cho lần gọi transform trên publisher source. Hai lần subscribe sau đó dùng publisher đã được tạo. Chúng không gọi lại hàm biến đổi.

Điều này không có nghĩa dữ liệu được phát ngay lúc assembly. Flux.just có thể đã giữ các giá trị nguồn, nhưng operator map vẫn xử lý tín hiệu khi có subscription. Cần phân biệt hai thời điểm:

- Assembly time: các operator được nối với nhau và hàm truyền cho transform được áp dụng.
- Subscription time: subscriber đăng ký, demand được truyền và các tín hiệu bắt đầu đi qua pipeline.

transform thay đổi cấu trúc pipeline tại assembly time; nó không tự subscribe hoặc biến một publisher lazy thành eager.

## 3. transformDeferred áp dụng hàm cho từng subscription

transformDeferred trì hoãn việc áp dụng hàm biến đổi cho đến khi có subscription. Mỗi subscription nhận một lần áp dụng hàm riêng.

Ví dụ:

    AtomicInteger transformCalls = new AtomicInteger();

    Flux<String> source = Flux.just("A", "B");

    Flux<String> transformed =
        source.transformDeferred(flux -> {
            int transformationId =
                transformCalls.incrementAndGet();

            return flux.map(value ->
                transformationId + ":" + value
            );
        });

    StepVerifier.create(transformed)
        .expectNext("1:A", "1:B")
        .verifyComplete();

    StepVerifier.create(transformed)
        .expectNext("2:A", "2:B")
        .verifyComplete();

    assertEquals(2, transformCalls.get());

Ở đây hàm biến đổi được gọi một lần cho mỗi subscription. Lần subscribe thứ nhất nhận transformationId bằng 1; lần thứ hai nhận transformationId bằng 2.

transformDeferred không có nghĩa hàm biến đổi được gọi cho từng phần tử. Nó được gọi một lần cho mỗi subscription, rồi publisher được trả về xử lý các phần tử của subscription đó.

## 4. So sánh trực tiếp

| Đặc điểm | transform | transformDeferred |
|---|---|---|
| Thời điểm gọi hàm biến đổi | Khi lắp ráp pipeline | Khi từng subscription bắt đầu |
| Số lần gọi hàm | Một lần cho mỗi lần áp dụng operator vào publisher | Một lần cho mỗi subscription |
| Cấu trúc operator được tạo | Dùng chung giữa các subscription của publisher kết quả | Tạo lại theo từng subscription |
| State được tạo bên trong hàm | Có thể được chia sẻ giữa các subscriber | Có thể được cô lập theo subscriber |
| Trường hợp phù hợp | Chính sách thuần, cấu trúc operator cố định | Cấu hình hoặc state cần tạo riêng cho từng subscription |

Hãy nhớ rằng “có thể được chia sẻ” và “được cô lập” phụ thuộc vào nơi state được tạo. transformDeferred chỉ tạo phạm vi riêng khi state được khởi tạo bên trong hàm biến đổi. Nếu hàm đóng trên một đối tượng mutable bên ngoài, các subscription vẫn có thể cùng dùng đối tượng đó.

## 5. Dùng transform để tái sử dụng chính sách thuần

transform phù hợp khi hàm biến đổi chỉ mô tả cấu trúc operator và không cần tạo state riêng cho từng subscriber. Ví dụ, chuẩn hóa và lọc dữ liệu cảm biến:

    record SensorReading(
        String sensorId,
        double celsius
    ) {}

    Function<Flux<SensorReading>, Flux<SensorReading>> validReadings =
        flux -> flux
            .map(reading -> new SensorReading(
                reading.sensorId(),
                Math.round(reading.celsius() * 10.0) / 10.0
            ))
            .filter(reading ->
                Double.isFinite(reading.celsius())
            )
            .filter(reading ->
                reading.celsius() >= -80.0
                    && reading.celsius() <= 150.0
            );

    Flux<SensorReading> normalized =
        sensorClient.readings("room-A")
            .transform(validReadings);

Chính sách trên không lưu bộ đếm hay dữ liệu thay đổi giữa các lần subscribe. Hàm chỉ nối các operator map và filter vào publisher. Đây là trường hợp đơn giản và dễ tái sử dụng.

Có thể đóng gói tham số nghiệp vụ bằng một factory:

    Function<Flux<SensorReading>, Flux<SensorReading>>
    withinRange(double minimum, double maximum) {
        return flux -> flux.filter(reading ->
            reading.celsius() >= minimum
                && reading.celsius() <= maximum
        );
    }

    Flux<SensorReading> roomReadings =
        sensorClient.readings("room-A")
            .transform(withinRange(-20.0, 60.0));

Các giá trị minimum và maximum được cố định khi tạo hàm chính sách. Đây là cấu hình assembly-time phù hợp nếu các pipeline dùng cùng ngưỡng trong suốt vòng đời.

## 6. transform và state được tạo trong hàm biến đổi

Khác biệt quan trọng nhất xuất hiện khi hàm biến đổi tạo state mutable rồi đóng state đó trong operator.

Ví dụ dùng transform:

    record Sequenced<T>(long sequence, T value) {}

    Flux<SensorReading> readings =
        sensorClient.readings("room-A");

    Flux<Sequenced<SensorReading>> sharedSequence =
        readings.transform(flux -> {
            AtomicLong sequence = new AtomicLong();

            return flux.map(reading ->
                new Sequenced<>(
                    sequence.incrementAndGet(),
                    reading
                )
            );
        });

AtomicLong được tạo khi transform áp dụng hàm ở assembly time. Nếu publisher kết quả được subscribe nhiều lần, các subscription cùng sử dụng bộ đếm đó. AtomicLong giúp thao tác tăng an toàn giữa các thread, nhưng số thứ tự trở thành state chung của publisher đã lắp ráp.

Nếu hai subscriber cùng đọc một nguồn cold, subscriber thứ nhất có thể nhận các số 1, 2 còn subscriber thứ hai nhận 3, 4 nếu hai lần subscribe chạy tuần tự. Nếu chúng chạy đồng thời, số thứ tự có thể được phân bổ xen kẽ giữa hai subscriber. Đây là một kết quả khác với bộ đếm riêng cho từng người tiêu thụ.

Đừng dùng transform khi nghiệp vụ yêu cầu sequence bắt đầu lại cho từng subscription nhưng state lại được tạo bên trong hàm biến đổi tại assembly time.

## 7. transformDeferred tạo state riêng cho mỗi subscriber

Nếu mỗi subscription cần bộ đếm riêng, hãy tạo state bên trong hàm truyền cho transformDeferred:

    Flux<SensorReading> sampleReadings = Flux.just(
        new SensorReading("sensor-1", 21.5),
        new SensorReading("sensor-1", 22.0)
    );

    Flux<Sequenced<SensorReading>> perSubscriberSequence =
        sampleReadings.transformDeferred(flux -> {
            long[] sequence = {0L};

            return flux.map(reading ->
                new Sequenced<>(
                    ++sequence[0],
                    reading
                )
            );
        });

Mỗi lần subscribe, hàm biến đổi tạo một mảng sequence mới và operator map của subscription đó đóng trên mảng riêng. Tín hiệu của một subscription được tuần tự hóa theo hợp đồng, nên state local này được cập nhật theo thứ tự tín hiệu của subscriber đó.

Hai subscriber không chia sẻ mảng sequence. Mỗi người bắt đầu từ 1 và tiến độc lập:

    StepVerifier.create(perSubscriberSequence)
        .expectNextMatches(item -> item.sequence() == 1)
        .expectNextMatches(item -> item.sequence() == 2)
        .verifyComplete();

    StepVerifier.create(perSubscriberSequence)
        .expectNextMatches(item -> item.sequence() == 1)
        .expectNextMatches(item -> item.sequence() == 2)
        .verifyComplete();

Nguồn mẫu là cold và hữu hạn nên mỗi subscription nhận lại hai phần tử, bộ đếm riêng bắt đầu từ 1 và verifier xác nhận complete.

State local trong transformDeferred không cần atomic chỉ vì Reactor có nhiều scheduler. Hợp đồng tín hiệu tuần tự hóa callback trong cùng subscription. Nếu state còn được truy cập từ thread bên ngoài hoặc chia sẻ với subscription khác qua một tham chiếu khác, phải áp dụng cơ chế đồng bộ phù hợp.

## 8. transformDeferred không tự làm mọi state trở nên riêng biệt

Hãy xem ví dụ sau:

    AtomicLong sharedCounter = new AtomicLong();

    Flux<SensorReading> stillShared =
        readings.transformDeferred(flux ->
            flux.doOnNext(reading ->
                sharedCounter.incrementAndGet()
            )
        );

Mặc dù dùng transformDeferred, sharedCounter vẫn được tạo bên ngoài hàm và được mọi subscription dùng chung. Hàm biến đổi chạy riêng, nhưng closure vẫn tham chiếu cùng đối tượng bên ngoài.

Muốn cô lập state, hãy tạo state bên trong hàm:

    Flux<SensorReading> isolated =
        readings.transformDeferred(flux -> {
            AtomicLong localCounter = new AtomicLong();

            return flux.doOnNext(reading ->
                localCounter.incrementAndGet()
            );
        });

Phạm vi của state được quyết định bởi vị trí khởi tạo đối tượng và các tham chiếu giữ nó, không chỉ bởi tên operator.

## 9. Kết hợp transformDeferred với Reactor Context

Một subscriber có thể mang metadata riêng như tenant ID, correlation ID hoặc chế độ xử lý. Reactor Context được gắn với subscription, nên một phép biến đổi cần đọc Context nên được áp dụng tại thời điểm subscribe.

Ví dụ dùng transformDeferredContextual:

    Flux<EnrichedEvent> enriched =
        events.transformDeferredContextual(
            (flux, context) -> {
                String tenantId = context.get("tenantId");

                return flux.map(event ->
                    new EnrichedEvent(event, tenantId)
                );
            }
        );

    enriched.contextWrite(context ->
        context.put("tenantId", "tenant-A")
    );

transformDeferredContextual là biến thể dành cho trường hợp hàm biến đổi cần cả publisher và ContextView của subscription. Nó giúp đọc metadata theo subscriber mà không phải đưa Context vào biến toàn cục hoặc ThreadLocal.

Context không tự động biến thành state mutable thread-safe. Nếu lấy một đối tượng mutable từ Context rồi nhiều subscription cùng tham chiếu đối tượng đó, vẫn cần ownership và đồng bộ phù hợp. Ưu tiên đặt giá trị bất biến trong Context.

## 10. Đóng gói chính sách có thể tái sử dụng

Một hàm biến đổi nên có tên mô tả mục đích nghiệp vụ và có kiểu đầu vào/đầu ra rõ ràng. Ví dụ:

    static Function<Flux<Order>, Flux<Order>> eligibleOrders() {
        return flux -> flux
            .filter(Order::isValid)
            .filter(order -> order.totalCents() > 0);
    }

    Flux<Order> acceptedOrders =
        orderSource().transform(eligibleOrders());

Nếu chính sách cần cấu hình, nhận tham số ở factory:

    static Function<Flux<Order>, Flux<Order>> minimumTotal(
        long minimumCents
    ) {
        return flux -> flux.filter(order ->
            order.totalCents() >= minimumCents
        );
    }

    Flux<Order> largeOrders =
        orderSource()
            .transform(minimumTotal(500_000));

Các hàm này chỉ mô tả phép lọc, không tạo state phụ thuộc subscription. transform là lựa chọn tự nhiên vì cấu trúc operator có thể được tạo một lần và tái sử dụng cho các lần subscribe.

Nếu factory tạo state như bộ đếm, accumulator hoặc tài nguyên riêng cho từng subscriber, hãy đặt việc khởi tạo trong transformDeferred. Nếu state cần được chia sẻ giữa các subscriber theo chủ đích, hãy đặt nó ở component có ownership rõ ràng và dùng cơ chế đồng bộ phù hợp.

## 11. So sánh với việc tự gọi defer

Có thể mô phỏng một phần hành vi của transformDeferred bằng Flux.defer:

    Flux<SensorReading> deferredPipeline =
        Flux.defer(() -> {
            Function<Flux<SensorReading>, Flux<SensorReading>> policy =
                flux -> flux.filter(this::isValid);

            return readings.transform(policy);
        });

Mỗi subscription tạo lại phần thân defer, rồi áp dụng policy cho publisher. Tuy nhiên, transformDeferred diễn đạt trực tiếp ý định: áp dụng một phép biến đổi cho publisher theo từng subscription.

Hãy dùng defer khi cần trì hoãn việc tạo publisher hoặc tính toán nguồn. Dùng transform khi muốn đóng gói chuỗi operator tại assembly time. Dùng transformDeferred khi muốn tái sử dụng chuỗi operator nhưng cần tạo lại phép biến đổi theo từng subscriber.

Không cần bọc transformDeferred trong defer chỉ để đạt cùng mục tiêu; lớp trì hoãn thừa có thể làm pipeline khó đọc hơn.

## 12. transform và transformDeferred không subscribe thay bạn

Cả hai operator đều chỉ tạo publisher đã biến đổi. Chúng không gọi subscribe và không khởi chạy một subscription nền.

Ví dụ:

    Flux<String> source = Flux.just("a", "b");

    Flux<String> pipeline =
        source.transform(flux ->
            flux.map(String::toUpperCase)
        );

    // Chưa có subscriber nào chỉ vì pipeline được khai báo.

    StepVerifier.create(pipeline)
        .expectNext("A", "B")
        .verifyComplete();

Việc subscribe vẫn do framework, StepVerifier hoặc code ở ranh giới ứng dụng thực hiện. Không gọi subscribe bên trong hàm biến đổi để “kích hoạt” operator; làm vậy sẽ tạo một subscription tách rời, khó phối hợp lỗi, cancellation và backpressure với chuỗi chính.

## 13. Kiểm thử thời điểm áp dụng hàm

Có thể kiểm tra số lần hàm biến đổi được gọi bằng một counter riêng:

    AtomicInteger assemblyCalls = new AtomicInteger();

    Flux<Integer> assembled =
        Flux.just(1, 2)
            .transform(flux -> {
                assemblyCalls.incrementAndGet();
                return flux.map(value -> value * 10);
            });

    assertEquals(1, assemblyCalls.get());

    StepVerifier.create(assembled)
        .expectNext(10, 20)
        .verifyComplete();

    StepVerifier.create(assembled)
        .expectNext(10, 20)
        .verifyComplete();

    assertEquals(1, assemblyCalls.get());

Với transformDeferred:

    AtomicInteger subscriptionCalls = new AtomicInteger();

    Flux<Integer> deferred =
        Flux.just(1, 2)
            .transformDeferred(flux -> {
                subscriptionCalls.incrementAndGet();
                return flux.map(value -> value * 10);
            });

    assertEquals(0, subscriptionCalls.get());

    StepVerifier.create(deferred)
        .expectNext(10, 20)
        .verifyComplete();

    assertEquals(1, subscriptionCalls.get());

    StepVerifier.create(deferred)
        .expectNext(10, 20)
        .verifyComplete();

    assertEquals(2, subscriptionCalls.get());

Các assertion minh họa số lần áp dụng hàm, không đo số lần operator map xử lý phần tử. Trong kiểm thử JUnit, cần import assertion phù hợp và đặt các đoạn mã trong một phương thức test.

## 14. Những lỗi thiết kế thường gặp

**Nhầm assembly với subscription.** transform gọi hàm biến đổi khi lắp ráp pipeline, nhưng không phát dữ liệu ngay. Subscription vẫn là thời điểm publisher bắt đầu thực thi theo demand.

**Cho rằng transformDeferred gọi hàm cho từng phần tử.** Hàm chỉ được gọi một lần cho mỗi subscription; publisher trả về mới xử lý từng phần tử.

**Tạo state trong transform nhưng mong state riêng từng subscriber.** State được tạo trong hàm biến đổi ở assembly time có thể được chia sẻ giữa mọi subscription của publisher kết quả.

**Dùng transformDeferred nhưng vẫn đóng trên biến mutable bên ngoài.** Hàm được gọi riêng không có nghĩa đối tượng mà closure tham chiếu cũng riêng.

**Dùng atomic để che giấu sai lầm về ownership.** Atomic có thể tránh race khi state chia sẻ, nhưng không làm cho ngữ nghĩa bộ đếm chung trở thành bộ đếm riêng cho từng subscriber.

**Gọi subscribe bên trong hàm biến đổi.** Điều này tách side effect khỏi subscription chính và làm khó quản lý lỗi, cancellation và backpressure.

**Dùng transformDeferred cho mọi pipeline.** Nếu chính sách thuần và cấu trúc operator cố định, transform đơn giản hơn và tránh tạo lại cấu trúc không cần thiết cho mỗi subscription.

**Đưa tài nguyên vào closure nhưng không quản lý cleanup.** Nếu phép biến đổi tạo session, file hoặc kết nối theo subscription, hãy gắn vòng đời tài nguyên với publisher bằng using hoặc usingWhen.

## 15. Chọn operator theo mục tiêu

| Mục tiêu | Lựa chọn |
|---|---|
| Đóng gói một chuỗi operator thuần, dùng cùng cấu trúc cho nhiều subscriber | transform |
| Tạo bộ đếm hoặc accumulator riêng cho mỗi subscription | transformDeferred |
| Đọc Reactor Context của từng subscriber khi áp dụng phép biến đổi | transformDeferredContextual |
| Trì hoãn tạo nguồn hoặc publisher cho tới khi subscribe | defer |
| Chỉ biến đổi từng phần tử | map, filter và các operator phần tử |
| Tạo publisher con bất đồng bộ cho từng phần tử | flatMap hoặc operator ghép phù hợp |

Một quy tắc thực tế: chọn transform nếu hàm chỉ định nghĩa cấu trúc xử lý. Chọn transformDeferred nếu chính quá trình tạo cấu trúc xử lý cần chạy riêng cho mỗi subscription. Nếu chỉ cần trì hoãn việc tạo nguồn, dùng defer.

## 16. Checklist trước khi tái sử dụng chuỗi operator

Trước khi đóng gói một pipeline, hãy xác định:

1. Hàm biến đổi có chỉ nối các operator thuần hay có tạo state mutable?
2. State được tạo ở assembly time hay subscription time?
3. Mỗi subscriber cần state riêng hay cần chia sẻ state có chủ đích?
4. Closure có tham chiếu một đối tượng mutable bên ngoài không?
5. Hàm biến đổi có đọc Reactor Context hoặc metadata riêng của subscriber không?
6. Publisher có được subscribe nhiều lần hoặc đồng thời không?
7. Có tài nguyên cần cleanup khi complete, error hoặc cancel không?
8. Có vô tình gọi subscribe bên trong hàm biến đổi không?
9. Test đã xác nhận số lần gọi hàm và hành vi giữa nhiều subscription chưa?

transform và transformDeferred đều giúp biến một nhóm operator thành đơn vị có thể đặt tên, kiểm thử và tái sử dụng. Điểm quyết định là thời điểm hàm biến đổi được áp dụng: transform ở assembly time, transformDeferred theo từng subscription. Khi đặt state đúng phạm vi và hiểu rõ closure được chia sẻ ra sao, ta có thể tái sử dụng pipeline Reactor mà không tạo ra trạng thái dùng chung ngoài ý muốn.

Các API cùng tên cũng có trên Mono. Ý nghĩa về thời điểm áp dụng phép biến đổi vẫn tương tự; khác biệt chủ yếu là kiểu publisher được biến đổi chỉ có thể phát tối đa một phần tử thay vì một chuỗi nhiều phần tử.
