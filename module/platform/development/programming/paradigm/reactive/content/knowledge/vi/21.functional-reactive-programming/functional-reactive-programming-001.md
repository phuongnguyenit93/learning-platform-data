# Lập trình phản ứng hàm (FRP) và quan hệ với lập trình hàm

Một ứng dụng thường phải phản ứng với dữ liệu thay đổi theo thời gian: nhiệt độ cảm biến tăng, người dùng kéo thanh trượt, giá cổ phiếu cập nhật hoặc trạng thái kết nối chuyển từ online sang offline. Nếu viết mã theo kiểu mệnh lệnh, mỗi nơi nhận được một thay đổi có thể phải tự cập nhật nhiều biến, gọi nhiều hàm và đồng bộ nhiều thành phần. Các bước cập nhật dễ phụ thuộc thứ tự và tạo ra trạng thái không nhất quán.

Lập trình phản ứng hàm (Functional Reactive Programming – FRP) mô tả dữ liệu thay đổi theo thời gian bằng những giá trị và luồng sự kiện có thể kết hợp qua các phép biến đổi hàm. Thay vì ra lệnh cập nhật từng thành phần, ta mô tả quan hệ giữa đầu vào và kết quả. Khi đầu vào thay đổi, hệ thống tính lại những giá trị phụ thuộc theo mô hình đã khai báo.

FRP kết hợp hai ý tưởng: mô hình phản ứng với thay đổi theo thời gian và cách tổ chức chương trình của lập trình hàm. Trong hệ sinh thái Java, Reactor cung cấp các publisher như Mono và Flux, cùng những toán tử biến đổi và kết hợp luồng. Reactor hỗ trợ nhiều mẫu lập trình reactive theo kiểu hàm, nhưng Reactive Streams và Reactor không đồng nghĩa với toàn bộ mô hình FRP cổ điển. Hiểu ranh giới này giúp chọn đúng công cụ và không gán cho một pipeline những bảo đảm mà nó không cung cấp.

## 1. FRP giải quyết vấn đề gì?

Hãy xem một màn hình hiển thị cảnh báo nhiệt độ. Màn hình có hai đầu vào thay đổi độc lập:

- Cảm biến liên tục gửi nhiệt độ mới.
- Người vận hành có thể thay đổi ngưỡng cảnh báo.

Kết quả cảnh báo phụ thuộc cả hai đầu vào. Với cách viết mệnh lệnh, mỗi handler có thể phải đọc biến còn lại, tính lại trạng thái và cập nhật giao diện. Nếu có thêm một đầu vào như chế độ bảo trì, số nơi cần đồng bộ càng tăng. Một handler có thể quên cập nhật hoặc đọc trạng thái ở thời điểm không phù hợp, khiến kết quả hiển thị sai.

FRP khuyến khích mô tả trực tiếp quan hệ:

    cảnh_báo = nhiệt_độ_mới > ngưỡng_hiện_tại

Hai đầu vào là các tín hiệu thay đổi theo thời gian. Kết quả là một tín hiệu phụ thuộc vào chúng. Khi nhiệt độ hoặc ngưỡng thay đổi, biểu thức được đánh giá lại theo quy tắc kết hợp đã chọn.

Mô hình này hữu ích khi:

- Nhiều đầu vào thay đổi độc lập nhưng cùng ảnh hưởng một kết quả.
- Cần kết hợp sự kiện, trạng thái hiện tại và phép tính.
- Muốn tách logic nghiệp vụ thuần khỏi I/O và cập nhật giao diện.
- Cần mô tả pipeline có thể kiểm thử bằng dữ liệu đầu vào xác định.
- Muốn giảm việc tự quản lý các biến trạng thái và chuỗi callback phụ thuộc nhau.

FRP không tự giải quyết mọi vấn đề về đồng thời, thứ tự, lưu trữ hay lỗi. Những đặc tính đó vẫn cần được xác định trong mô hình nguồn và thư viện thực thi.

## 2. Hai khái niệm cốt lõi: Event và Behavior

Trong cách mô tả FRP phổ biến, hai loại tín hiệu quan trọng là Event và Behavior. Tên gọi và chi tiết ngữ nghĩa có thể khác nhau giữa các thư viện FRP, nhưng sự phân biệt sau là nền tảng hữu ích.

### 2.1. Event: những sự kiện xảy ra tại các thời điểm rời rạc

Event biểu diễn những lần một điều gì đó xảy ra. Một event stream có thể không phát sự kiện nào, phát một sự kiện hoặc phát nhiều sự kiện theo thời gian.

Ví dụ:

- Người dùng nhấn nút.
- Cảm biến gửi một bản tin.
- Một đơn hàng được tạo.
- Bộ hẹn giờ phát một tick.

Event thường được mô tả như một chuỗi các lần xuất hiện:

    Event<Click>
        click-1 ---- click-2 -------- click-3 ---->
        t1          t2               t3

Không có một giá trị event liên tục tồn tại giữa hai lần phát. Mỗi lần phát là một occurrence riêng.

### 2.2. Behavior: giá trị thay đổi theo thời gian

Behavior biểu diễn một giá trị có thể được quan sát tại mọi thời điểm trong miền thời gian của nó. Giá trị có thể giữ nguyên trong một khoảng rồi thay đổi khi có đầu vào mới.

Ví dụ:

- Vị trí con trỏ hiện tại.
- Ngưỡng nhiệt độ hiện tại.
- Trạng thái kết nối hiện tại.
- Giá trị âm lượng hiện tại.

Một behavior có thể hình dung như:

    Behavior<Double>
        20.0 -------- 22.5 -------- 22.5 ----- 24.0 --->
        t0            t1            t2         t3

Tại một thời điểm, behavior có một giá trị hiện tại. Khi thời gian tiến lên, giá trị đó có thể đổi.

### 2.3. Quan hệ giữa Event và Behavior

Event mô tả những thay đổi hoặc occurrence; Behavior mô tả giá trị đang có hiệu lực tại một thời điểm. Một event có thể cập nhật một behavior. Ngược lại, ta có thể lấy mẫu behavior khi một event xảy ra.

Ví dụ:

- ThresholdChanged(30) là event.
- currentThreshold là behavior giữ ngưỡng đang áp dụng.
- Mỗi TemperatureReceived là event.
- isOverLimit là một giá trị được suy ra từ nhiệt độ mới và ngưỡng hiện tại.

Không phải thư viện reactive nào cũng cung cấp kiểu Event và Behavior riêng. Trong Reactor, Flux<T> biểu diễn chuỗi tín hiệu rời rạc khá tự nhiên. Một luồng phát các bản cập nhật trạng thái có thể được dùng để mô phỏng behavior; tuy nhiên, Flux tự nó không có ngữ nghĩa “giá trị tại mọi thời điểm” như một Behavior trong FRP cổ điển.

## 3. Quan hệ với lập trình hàm

Lập trình hàm tổ chức chương trình quanh việc áp dụng hàm lên giá trị. Những đặc điểm thường gặp gồm hàm thuần, dữ liệu bất biến, hàm bậc cao và phép kết hợp hàm.

FRP sử dụng các đặc điểm đó để mô tả dữ liệu thay đổi theo thời gian:

| Ý tưởng lập trình hàm | Cách dùng trong FRP |
|---|---|
| Hàm thuần | Mô tả cách tính giá trị mới từ các đầu vào |
| Dữ liệu bất biến | Đại diện trạng thái bằng giá trị mới thay vì sửa nhiều biến dùng chung |
| Hàm bậc cao | Nhận hoặc trả về phép biến đổi tín hiệu |
| Composition | Ghép nhiều phép biến đổi nhỏ thành một luồng xử lý |
| Tách side effect | Giữ I/O, ghi log và cập nhật hệ thống ở ranh giới phù hợp |

### 3.1. Hàm thuần giúp kết quả dễ dự đoán

Một hàm thuần trả về cùng kết quả khi nhận cùng đầu vào và không thay đổi trạng thái bên ngoài:

    record Temperature(double celsius) {}
    record Threshold(double celsius) {}

    boolean isOverLimit(
        Temperature temperature,
        Threshold threshold
    ) {
        return temperature.celsius() > threshold.celsius();
    }

Kết quả của isOverLimit chỉ phụ thuộc hai tham số. Ta có thể kiểm thử hàm mà không cần tạo publisher, kết nối mạng hay đồng hồ thật.

Ngược lại, hàm đọc một biến toàn cục hoặc gọi Instant.now() bên trong có kết quả phụ thuộc môi trường:

    // Phụ thuộc trạng thái bên ngoài và thời điểm gọi.
    boolean isExpired(Instant deadline) {
        return Instant.now().isAfter(deadline);
    }

Để logic có thể kiểm thử và kết hợp tốt hơn, hãy đưa thời điểm hiện tại thành đầu vào:

    boolean isExpired(Instant now, Instant deadline) {
        return now.isAfter(deadline);
    }

Nguồn thời gian và I/O được lấy ở ranh giới ứng dụng, sau đó truyền giá trị vào hàm thuần.

### 3.2. Dữ liệu bất biến làm rõ sự thay đổi

Thay vì sửa một đối tượng dùng chung qua nhiều callback, có thể tạo một giá trị mới:

    record SensorState(
        String sensorId,
        double temperature,
        Instant observedAt
    ) {}

    SensorState withTemperature(
        SensorState previous,
        double newTemperature,
        Instant observedAt
    ) {
        return new SensorState(
            previous.sensorId(),
            newTemperature,
            observedAt
        );
    }

Mỗi state mới thể hiện kết quả của một phép biến đổi. Điều này giúp kiểm thử, ghi log và so sánh trạng thái dễ hơn. Với dữ liệu lớn hoặc yêu cầu hiệu năng đặc thù, có thể dùng cấu trúc mutable ở phạm vi được kiểm soát; nhưng không nên chia sẻ trạng thái mutable giữa các subscription mà không có đồng bộ hóa rõ ràng.

## 4. FRP mô tả quan hệ, không mô tả chuỗi lệnh cập nhật

Giả sử ứng dụng nhận giá trị nhiệt độ và ngưỡng cảnh báo. Cách mệnh lệnh có thể lưu currentTemperature, currentThreshold và alertActive, rồi cập nhật alertActive ở cả hai handler.

Mô hình hàm mô tả kết quả từ toàn bộ đầu vào:

    alertActive =
        temperature > threshold
        && !maintenanceMode

Khi một đầu vào thay đổi, kết quả được tính lại theo cùng biểu thức. Không cần viết một nhánh riêng cho “nhiệt độ đổi” và một nhánh khác cho “ngưỡng đổi” nếu thư viện tín hiệu đã cung cấp phép kết hợp phù hợp.

Trong FRP cổ điển, biểu thức này được hiểu trên các Behavior thay đổi theo thời gian. Với luồng sự kiện rời rạc, hệ thống cần quy định rõ khi nào đánh giá lại: mỗi lần một đầu vào phát event, khi một tick xảy ra, hoặc khi lấy mẫu theo chu kỳ.

## 5. Biểu diễn các phép biến đổi bằng Reactor

Reactor cung cấp Mono và Flux để biểu diễn các publisher bất đồng bộ:

- Mono<T> phát tối đa một phần tử rồi kết thúc bằng complete hoặc error.
- Flux<T> phát không, một hoặc nhiều phần tử rồi kết thúc bằng complete hoặc error.

Các toán tử như map, filter, scan, flatMap và combineLatest cho phép xây dựng phép biến đổi trên những tín hiệu đó.

Ví dụ, chuẩn hóa và lọc một luồng cảm biến:

    Flux<Temperature> validReadings =
        sensorClient.readings()
            .map(reading -> new Temperature(
                Math.round(reading.celsius() * 10.0) / 10.0
            ))
            .filter(reading ->
                Double.isFinite(reading.celsius())
            );

Phép map biến đổi mỗi giá trị, còn filter giữ lại những giá trị hợp lệ. Đây là cách dùng hàm để biến đổi chuỗi event; nó không cần sửa collection dùng chung.

### 5.1. Kết hợp hai luồng thay đổi bằng combineLatest

Khi kết quả phụ thuộc vào giá trị mới nhất của hai nguồn, Flux.combineLatest là một operator phù hợp. Nó đợi mỗi nguồn phát ít nhất một phần tử; sau đó, mỗi khi một nguồn phát giá trị mới, operator kết hợp giá trị đó với giá trị gần nhất từ nguồn còn lại.

Ví dụ mô hình cảm biến:

    record Reading(String sensorId, double celsius) {}
    record TemperatureLimit(double celsius) {}
    record Evaluation(Reading reading, TemperatureLimit limit) {}
    record Alert(String sensorId, double measured, double limit) {}

    Flux<Reading> readings = sensorClient.readings();
    Flux<TemperatureLimit> limits = settings.limitUpdates();

    Flux<Alert> alerts =
        Flux.combineLatest(
            readings,
            limits,
            Evaluation::new
        )
        .filter(evaluation ->
            evaluation.reading().celsius()
                > evaluation.limit().celsius()
        )
        .map(evaluation -> new Alert(
            evaluation.reading().sensorId(),
            evaluation.reading().celsius(),
            evaluation.limit().celsius()
        ));

Khi nhiệt độ mới đến, nó được so sánh với ngưỡng gần nhất. Khi ngưỡng thay đổi, nhiệt độ gần nhất cũng được đánh giá lại theo ngưỡng mới. Đây là cách mô tả quan hệ giữa các luồng cập nhật mà không phải tự viết hai handler cập nhật cùng một biến kết quả.

combineLatest có semantics riêng:

- Không phát kết quả cho đến khi mọi nguồn đã phát ít nhất một phần tử.
- Mỗi tín hiệu mới từ bất kỳ nguồn nào có thể tạo ra một kết quả kết hợp.
- Giá trị được kết hợp là giá trị mới nhất mà operator đã quan sát từ từng nguồn.
- Nó không khôi phục lịch sử của nguồn và không tự sắp xếp theo timestamp nghiệp vụ.

Nếu một nguồn không bao giờ phát phần tử đầu tiên, kết quả kết hợp sẽ không bắt đầu. Nếu cần giá trị ban đầu, hãy cung cấp một nguồn có giá trị khởi tạo rõ ràng hoặc mô hình hóa trạng thái ban đầu tại tầng nghiệp vụ.

### 5.2. Dùng scan để suy ra trạng thái từ event stream

Một luồng event có thể cập nhật trạng thái qua từng phần tử. scan giữ một accumulator và phát giá trị trạng thái sau mỗi bước:

    record CounterEvent(int delta) {}

    Flux<Integer> counts =
        counterEvents
            .scan(0, (current, event) ->
                current + event.delta()
            );

Mỗi event tạo một trạng thái đếm mới từ trạng thái trước. Với overload có giá trị khởi tạo, scan phát trạng thái ban đầu rồi phát các trạng thái sau từng event; khác với reduce, vốn chỉ phát kết quả tổng hợp khi nguồn hoàn tất.

Với nguồn không bao giờ hoàn tất như luồng sự kiện trực tiếp, scan phù hợp để biểu diễn chuỗi state mới. Nếu nguồn phát lại hoặc có nhiều subscriber, cần hiểu nguồn là cold hay hot và accumulator được tạo cho từng subscription theo cách nào.

## 6. Reactor hỗ trợ kiểu FRP nào và giới hạn ở đâu?

Reactor được thiết kế quanh Reactive Streams: truyền các tín hiệu rời rạc, bất đồng bộ, có backpressure và có vòng đời subscription. Đây là nền tảng rất hữu ích để xây dựng ứng dụng theo tư duy hàm và reactive.

Tuy nhiên, không nên xem Flux<T> là Behavior<T> một cách trực tiếp:

| Khía cạnh | FRP cổ điển | Reactor / Reactive Streams |
|---|---|---|
| Mô hình thời gian | Có thể mô tả giá trị liên tục theo thời gian và event rời rạc | Tập trung vào chuỗi tín hiệu rời rạc |
| Giá trị hiện tại | Behavior biểu diễn giá trị tại một thời điểm | Cần nguồn trạng thái hoặc publisher cập nhật được thiết kế rõ |
| Sự kiện | Event biểu diễn occurrence | Flux<T> thường biểu diễn chuỗi phần tử |
| Điều tiết | Tùy hệ thống FRP | Reactive Streams có request(n) và backpressure |
| Vòng đời | Tùy mô hình FRP | Subscription có complete, error và cancellation |

Reactor phù hợp với luồng dữ liệu bất đồng bộ trong backend, tích hợp mạng, xử lý sự kiện và pipeline nghiệp vụ. Với bài toán cần mô hình hóa tín hiệu liên tục, đồng bộ thời gian chính xác hoặc semantics Behavior chuyên biệt, có thể cần thư viện FRP chuyên dụng hoặc một abstraction miền riêng.

## 7. Phân biệt FRP, Reactive Programming và Reactive Streams

Ba thuật ngữ liên quan nhưng nói về các khía cạnh khác nhau:

**Functional Reactive Programming** là mô hình lập trình mô tả các giá trị và sự kiện thay đổi theo thời gian bằng phép biến đổi hàm. Trọng tâm là biểu diễn quan hệ dữ liệu và thời gian một cách khai báo.

**Reactive Programming** là cách tổ chức chương trình phản ứng với dữ liệu hoặc sự kiện đến theo thời gian. Thuật ngữ này rộng hơn và không phải mọi hệ thống reactive đều dùng mô hình hàm thuần hoặc có Behavior/Event như FRP.

**Reactive Streams** là một đặc tả giao thức cho truyền dữ liệu bất đồng bộ có backpressure giữa Publisher và Subscriber. Nó xác định các thành phần Publisher, Subscriber, Subscription, tín hiệu và quy tắc nhu cầu. Đây là hợp đồng truyền dữ liệu, không phải một ngôn ngữ lập trình hay mô hình FRP đầy đủ.

Mối quan hệ có thể tóm tắt:

    Lập trình hàm
       |  hàm thuần, bất biến, composition
       v
    FRP: mô tả giá trị và sự kiện theo thời gian
       |
       | một cách triển khai reactive có thể dùng
       v
    Reactive Programming
       |
       | có thể dùng hợp đồng truyền dữ liệu
       v
    Reactive Streams: Publisher / Subscriber / backpressure

Sơ đồ chỉ thể hiện mối liên hệ về ý tưởng, không phải thứ bậc bắt buộc. Một ứng dụng có thể dùng Reactive Streams mà không triển khai FRP cổ điển; một hệ thống FRP cũng có thể dùng cơ chế thực thi khác.

## 8. Tách logic thuần khỏi side effect

Một pipeline reactive thường có hai loại công việc:

- Phép biến đổi dữ liệu: chuẩn hóa, tính toán, lọc, kết hợp trạng thái.
- Side effect: gọi HTTP, ghi database, gửi message, cập nhật metric hoặc giao diện.

Nên giữ phép biến đổi nghiệp vụ ở dạng hàm thuần khi có thể, rồi ghép I/O ở ranh giới cần thiết:

    BiFunction<Reading, TemperatureLimit, Evaluation> evaluate =
        Evaluation::new;

    Flux<Evaluation> evaluations =
        Flux.combineLatest(readings, limits, evaluate);

    Flux<Alert> alerts =
        evaluations
            .filter(result ->
                result.reading().celsius()
                    > result.limit().celsius()
            )
            .map(result -> toAlert(result));

Trong ví dụ, mỗi Evaluation được tạo từ Reading và TemperatureLimit hiện hành. Hãy đưa cả hai đầu vào vào phép kết hợp thay vì đọc một biến mutable dùng chung trong hàm. Phần gửi cảnh báo có thể được ghép bằng flatMap để giữ side effect trong cùng pipeline:

    Flux<DeliveryReceipt> deliveries =
        alerts.flatMap(
            notificationClient::send,
            16
        );

Giới hạn concurrency giúp kiểm soát số lần gửi đồng thời. Lỗi và cancellation của các publisher gửi được quản lý trong pipeline thay vì tạo subscription rời rạc bằng subscribe() bên trong hàm tính toán.

## 9. Thời gian phải được biểu diễn rõ

Trong FRP, “giá trị hiện tại” có ý nghĩa theo thời gian. Nhưng không phải mọi timestamp đều cùng một loại:

- Event time: thời điểm sự kiện xảy ra theo nguồn.
- Processing time: thời điểm pipeline xử lý tín hiệu.
- Sampling time: thời điểm một behavior được lấy mẫu.

Nếu hàm nghiệp vụ cần biết thời gian, hãy đưa timestamp vào dữ liệu hoặc truyền nó thành tham số. Tránh gọi đồng hồ toàn cục bên trong hàm thuần.

Ví dụ:

    record PriceTick(
        String symbol,
        BigDecimal price,
        Instant occurredAt
    ) {}

    record PriceChange(
        String symbol,
        BigDecimal difference,
        Instant measuredAt
    ) {}

    Function<PriceTick, PriceChange> toChange(
        BigDecimal previousPrice,
        Instant measuredAt
    ) {
        return tick -> new PriceChange(
            tick.symbol(),
            tick.price().subtract(previousPrice),
            measuredAt
        );
    }

Hàm nhận previousPrice và measuredAt rõ ràng, nên kết quả có thể được kiểm thử với đầu vào cố định. Việc lấy thời gian thật và tìm giá trước đó thuộc về tầng điều phối hoặc stateful operator.

## 10. Backpressure và các nguồn sự kiện

FRP tập trung vào mô hình tín hiệu và quan hệ giữa các giá trị; Reactive Streams bổ sung hợp đồng nhu cầu cho việc truyền chuỗi phần tử. Khi dùng Reactor, subscriber yêu cầu dữ liệu qua request(n), và publisher tuân thủ không phát vượt quá nhu cầu đã cấp.

Tuy nhiên, một event source bên ngoài có thể không hỗ trợ tạm dừng, ví dụ callback từ thiết bị hoặc thư viện UI. Khi đó adapter cần chính sách cho sự kiện đến nhanh hơn downstream:

- Buffer có giới hạn để hấp thụ tải đột biến.
- Drop nếu một số event có thể bỏ.
- Latest nếu chỉ cần trạng thái mới nhất.
- Từ chối hoặc báo overflow khi không thể giữ thêm.
- Chuyển sang broker bền vững nếu mọi event cần được lưu và xử lý sau.

Không nên nhầm backpressure với việc thay đổi ngữ nghĩa FRP. Nó điều tiết số phần tử đi qua subscription; không tự quyết định event nào quan trọng hoặc cách tính giá trị theo thời gian.

## 11. Những lỗi thường gặp khi áp dụng tư duy FRP

**Coi Event và Behavior là một.** Event là occurrence rời rạc; Behavior là giá trị có hiệu lực theo thời gian. Dùng đúng khái niệm giúp xác định khi nào cần giữ trạng thái hiện tại.

**Xem mọi Flux là một Behavior.** Flux phát chuỗi phần tử, không tự cung cấp phép lấy mẫu giá trị hiện tại tại mọi thời điểm. Nếu cần state hiện tại, hãy thiết kế nguồn state hoặc replay phù hợp.

**Đưa side effect vào hàm biến đổi.** Hàm có log, ghi database hoặc sửa biến ngoài sẽ khó kiểm thử và có thể chạy lại khi có subscription mới. Giữ phép tính thuần và ghép I/O ở ranh giới rõ ràng.

**Dùng biến mutable dùng chung làm trạng thái tín hiệu.** Nhiều subscriber có thể đọc hoặc sửa cùng biến ở các thời điểm khác nhau. Dùng dữ liệu bất biến, state riêng cho subscription hoặc một cơ chế đồng bộ được thiết kế rõ.

**Giả định combineLatest sắp xếp theo event time.** Operator kết hợp giá trị mới nhất theo thứ tự tín hiệu nó quan sát, không sắp xếp lại theo timestamp nghiệp vụ.

**Không xác định giá trị ban đầu.** combineLatest chưa phát kết quả cho đến khi mọi nguồn có phần tử đầu tiên. Nếu nghiệp vụ cần giá trị mặc định, hãy biểu diễn nó rõ ràng.

**Nhầm Reactive Streams với FRP đầy đủ.** Reactive Streams định nghĩa giao thức truyền dữ liệu có backpressure. Nó không quy định toàn bộ semantics của Behavior, thời gian liên tục hoặc event-time window.

## 12. Kiểm thử các phép biến đổi theo kiểu hàm

Một lợi ích của cách tổ chức hàm là có thể kiểm thử phần nghiệp vụ mà không cần khởi chạy runtime reactive. Ví dụ:

    @Test
    void detectsTemperatureAboveLimit() {
        Temperature temperature = new Temperature(32.0);
        Threshold threshold = new Threshold(30.0);

        assertTrue(isOverLimit(temperature, threshold));
    }

Sau đó kiểm thử cách các publisher kết hợp bằng StepVerifier:

    Flux<Alert> alerts =
        Flux.combineLatest(
            Flux.just(new Reading("sensor-1", 32.0)),
            Flux.just(new TemperatureLimit(30.0)),
            Evaluation::new
        )
        .filter(evaluation ->
            evaluation.reading().celsius()
                > evaluation.limit().celsius()
        )
        .map(evaluation -> new Alert(
            evaluation.reading().sensorId(),
            evaluation.reading().celsius(),
            evaluation.limit().celsius()
        ));

    StepVerifier.create(alerts)
        .expectNextMatches(alert ->
            alert.sensorId().equals("sensor-1")
                && alert.measured() == 32.0
                && alert.limit() == 30.0
        )
        .verifyComplete();

Bài kiểm thử xác nhận kết quả của phép kết hợp hai nguồn. Với luồng dài hoặc hot publisher, cần kiểm tra thêm thứ tự subscribe, giá trị ban đầu, cancellation, backpressure và cách xử lý khi một nguồn lỗi hoặc không phát phần tử.

## 13. Khi nào nên dùng cách tiếp cận nào?

| Bài toán | Cách tiếp cận phù hợp |
|---|---|
| Tính kết quả từ một giá trị đầu vào | Hàm thuần, map hoặc phép biến đổi tương đương |
| Phản ứng với chuỗi sự kiện rời rạc | Event stream, thường biểu diễn bằng Flux |
| Kết hợp các bản cập nhật mới nhất từ nhiều nguồn | combineLatest hoặc operator kết hợp phù hợp |
| Tính trạng thái tích lũy từ event | scan hoặc stateful transformation |
| Lấy một kết quả bất đồng bộ tối đa một lần | Mono |
| Truyền dữ liệu có backpressure | Publisher/Subscriber theo Reactive Streams |
| Mô hình hóa tín hiệu liên tục hoặc Behavior chuyên biệt | Thư viện FRP hoặc abstraction thời gian phù hợp |

Không cần biến mọi đoạn mã thành pipeline reactive. Một hàm thuần đơn giản thường là lựa chọn tốt nhất cho một phép tính độc lập. Dùng publisher khi dữ liệu thực sự được phát bất đồng bộ, có nhiều phần tử theo thời gian hoặc cần phối hợp với các API reactive.

## 14. Checklist thiết kế theo tư duy FRP

Khi mô hình hóa một tính năng phản ứng với thay đổi, hãy xác định:

1. Đầu vào nào là event occurrence và đầu vào nào đại diện trạng thái hiện tại?
2. Kết quả phụ thuộc vào những giá trị nào?
3. Khi một nguồn thay đổi, cần tính lại kết quả vào thời điểm nào?
4. Có giá trị ban đầu cho từng nguồn hay không?
5. Phép tính có thể viết thành hàm thuần và dùng dữ liệu bất biến không?
6. Side effect nằm ở ranh giới nào của pipeline?
7. Thứ tự tín hiệu, event time và processing time có bị nhầm lẫn không?
8. Nguồn có hỗ trợ backpressure hay cần buffer/drop/latest?
9. Lỗi và cancellation của các publisher được xử lý theo chính sách nào?
10. Có thể kiểm thử phép tính độc lập và kiểm thử pipeline bằng StepVerifier không?

FRP giúp mô tả quan hệ giữa sự kiện, trạng thái và kết quả theo thời gian bằng các phép biến đổi có thể kết hợp. Lập trình hàm cung cấp công cụ để giữ các phép tính rõ ràng, ít phụ thuộc trạng thái ẩn và dễ kiểm thử. Trong Java, Reactor hỗ trợ tư duy này qua Mono, Flux và các operator kết hợp luồng; còn Reactive Streams bổ sung hợp đồng truyền dữ liệu có backpressure và cancellation. Khi phân biệt đúng các lớp khái niệm, ta có thể xây dựng pipeline phản ứng dễ hiểu mà vẫn kiểm soát được thời gian, trạng thái và vòng đời thực thi.
