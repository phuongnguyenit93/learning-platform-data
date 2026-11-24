# Các toán tử Reactor cần dùng khi xây dựng ứng dụng RSocket

## Bối cảnh: Reactor là nền tảng xử lý dữ liệu bất đồng bộ

RSocket cho phép client và server trao đổi request-response, fire-and-forget, request-stream và request-channel. Trong ứng dụng Java dùng Spring, dữ liệu của các tương tác này thường được biểu diễn bằng Reactor: **Mono** đại diện cho một kết quả có thể xuất hiện bất đồng bộ (0 hoặc 1 phần tử), còn **Flux** đại diện cho một chuỗi có thể phát ra 0 đến nhiều phần tử theo thời gian.

Reactor là một implementation của Reactive Streams. Một pipeline Reactor mô tả cách dữ liệu được tạo, biến đổi, kết hợp, xử lý lỗi và tiêu thụ. Pipeline thường chỉ bắt đầu phát dữ liệu khi có subscriber. Vì vậy, khi xây dựng ứng dụng RSocket, cần hiểu cả cách chọn toán tử lẫn thời điểm subscription, hủy subscription và yêu cầu dữ liệu.

Bài học này tập trung vào các toán tử thường gặp khi triển khai RSocket client/server bằng Spring WebFlux và Spring Messaging. Mục tiêu là chọn đúng toán tử cho từng luồng dữ liệu, giữ được thứ tự khi cần, kiểm soát tải và xử lý lỗi đúng vòng đời.

## 1. Mono, Flux và vòng đời của một pipeline

### Mono và Flux

| Kiểu | Số phần tử tối đa | Ví dụ |
|---|---:|---|
| Mono<T> | 1 | Tra cứu trạng thái thiết bị, lấy cấu hình, gửi một lệnh |
| Flux<T> | Không giới hạn cố định | Luồng telemetry, danh sách sự kiện, các lệnh gửi liên tục |

Một Mono có thể hoàn tất mà không phát phần tử nào, chẳng hạn khi không tìm thấy dữ liệu và service trả về Mono.empty(). Một Flux cũng có thể rỗng. Cả hai đều có thể kết thúc bình thường hoặc kết thúc bằng lỗi.

~~~java
Mono<DeviceStatus> status =
    statusRepository.findById("sensor-01");

Flux<Reading> readings =
    readingRepository.findRecentBySensorId("sensor-01");
~~~

Kiểu trả về cho biết hình dạng dữ liệu mà caller có thể nhận, nhưng không tự đảm bảo thao tác bên trong là non-blocking. Nếu repository dùng JDBC blocking, bọc lời gọi đó trong Mono không biến JDBC thành non-blocking.

### Pipeline chỉ chạy khi có subscription

Các toán tử thường tạo thành một pipeline khai báo. Khi subscriber đăng ký, tín hiệu subscription đi ngược về upstream; sau đó các phần tử được phát xuôi về downstream.

~~~mermaid
flowchart LR
    A["Nguồn dữ liệu"] --> B["map / filter"]
    B --> C["flatMap / concatMap"]
    C --> D["onErrorResume"]
    D --> E["subscribe hoặc RSocket runtime"]
~~~

Ví dụ:

~~~java
Flux<String> names = Flux.just("an", "binh", "chi")
    .map(String::toUpperCase)
    .filter(name -> name.startsWith("A"));
~~~

Đoạn mã trên mới mô tả pipeline. Việc khai báo biến names chưa khiến dữ liệu được tiêu thụ. Khi một thành phần của Spring RSocket runtime nhận Mono hoặc Flux làm kết quả của route, framework sẽ quản lý subscription phù hợp với tương tác. Trong mã ứng dụng thông thường, chỉ subscribe ở ranh giới thực sự sở hữu vòng đời tiêu thụ, chẳng hạn tầng giao diện hoặc một tác vụ độc lập đã được thiết kế rõ ràng.

### Ba tín hiệu chính

Reactive Streams có ba loại tín hiệu từ publisher đến subscriber:

- **onNext(value):** phát một phần tử.
- **onComplete():** kết thúc bình thường.
- **onError(error):** kết thúc do lỗi.

Sau onComplete hoặc onError, stream đã kết thúc và không phát thêm phần tử. Subscription cũng có thể bị hủy từ phía subscriber. Hủy là tín hiệu điều khiển vòng đời, không phải một phần tử dữ liệu.

## 2. Tạo nguồn dữ liệu

Các toán tử tạo nguồn giúp xây dựng Mono hoặc Flux từ giá trị có sẵn, collection, tác vụ trì hoãn hoặc một publisher khác.

| Toán tử | Mục đích | Ví dụ |
|---|---|---|
| just | Phát giá trị đã có | Mono.just(status) |
| empty | Hoàn tất không có phần tử | Mono.empty() |
| error | Kết thúc bằng lỗi | Mono.error(exception) |
| fromIterable | Phát các phần tử từ collection | Flux.fromIterable(items) |
| defer | Tạo publisher mới khi có subscriber | Mono.defer(this::loadStatus) |
| fromCallable | Chuyển một Callable thành Mono | Mono.fromCallable(this::readValue) |

### just và defer khác nhau ở thời điểm lấy giá trị

Mono.just(value) giữ giá trị ngay khi biểu thức được thực thi. Nếu giá trị cần được tính mới cho mỗi subscriber, dùng defer để trì hoãn việc tạo publisher đến thời điểm subscription.

~~~java
Mono<Instant> fixedTime = Mono.just(Instant.now());

Mono<Instant> timePerSubscription =
    Mono.defer(() -> Mono.just(Instant.now()));
~~~

fixedTime phát cùng một Instant cho mọi subscriber. timePerSubscription tạo Instant mới cho mỗi lần đăng ký. Sự khác biệt này quan trọng với route RSocket có thể được nhiều client gọi ở các thời điểm khác nhau.

### fromCallable không tự biến lời gọi blocking thành non-blocking

~~~java
Mono<DeviceStatus> status =
    Mono.fromCallable(() -> legacyJdbcRepository.loadStatus("sensor-01"))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Ví dụ trên chuyển công việc blocking sang boundedElastic để tránh chạy nó trên event loop. Đây là giải pháp tương thích cho API blocking hiện có. Với ứng dụng cần thông lượng cao, nên ưu tiên driver và client có API non-blocking phù hợp.

Không nên đưa thao tác blocking vào Mono.just(legacyCall()), vì legacyCall() sẽ chạy ngay trong lúc tạo biểu thức, trước khi subscriber đăng ký.

## 3. Biến đổi dữ liệu: map, flatMap và concatMap

Đây là nhóm toán tử được sử dụng thường xuyên nhất khi một route RSocket cần gọi service hoặc chuyển đổi payload.

### map: biến đổi một phần tử thành một giá trị khác

Dùng map khi phép biến đổi là đồng bộ và trả về trực tiếp một giá trị.

~~~java
Mono<DeviceSummary> summary =
    statusService.findStatus("sensor-01")
        .map(status -> new DeviceSummary(
            status.sensorId(),
            status.online(),
            status.temperature()
        ));
~~~

Với Flux, map áp dụng phép biến đổi cho từng phần tử và giữ nguyên số lượng phần tử nếu không có lỗi.

### flatMap: biến đổi thành publisher khác và hợp nhất kết quả

Dùng flatMap khi mỗi phần tử cần gọi một thao tác trả về Mono hoặc Flux khác, ví dụ truy vấn thêm dữ liệu hoặc gọi dịch vụ từ xa.

~~~java
Mono<DeviceView> view =
    statusService.findStatus("sensor-01")
        .flatMap(status ->
            profileService.findProfile(status.sensorId())
                .map(profile -> new DeviceView(status, profile))
        );
~~~

Với Flux, flatMap có thể đăng ký nhiều publisher con đồng thời và hợp nhất kết quả khi chúng phát ra. Vì vậy, thứ tự phần tử đầu ra không nhất thiết trùng thứ tự đầu vào.

~~~java
Flux<DeviceStatus> statuses =
    Flux.just("sensor-01", "sensor-02", "sensor-03")
        .flatMap(statusService::findStatus);
~~~

Nếu các lời gọi hoàn tất theo thứ tự khác nhau, kết quả có thể đến theo thứ tự hoàn tất. Có thể giới hạn số publisher con đồng thời:

~~~java
Flux<DeviceStatus> statuses =
    sensorIds.flatMap(statusService::findStatus, 8);
~~~

Tham số 8 giới hạn số publisher con đang được xử lý đồng thời. Giá trị phù hợp phụ thuộc vào độ trễ, giới hạn kết nối và khả năng của dịch vụ đích.

### concatMap: giữ thứ tự và xử lý tuần tự

Khi thứ tự command có ý nghĩa, dùng concatMap để chỉ xử lý publisher con kế tiếp sau khi publisher hiện tại hoàn tất.

~~~java
Flux<DeviceEvent> events =
    commands.concatMap(deviceService::handle);
~~~

Ví dụ một thiết bị nhận các lệnh START, SET_SPEED và STOP. Nếu thứ tự là một phần của nghiệp vụ, việc xử lý đồng thời các lệnh có thể khiến trạng thái thiết bị không đúng mong đợi. concatMap giữ thứ tự xử lý theo thứ tự phần tử đầu vào.

Đổi lại, concatMap có thể giảm throughput nếu mỗi thao tác chậm. Chỉ dùng nó khi thứ tự là yêu cầu thực sự.

### flatMapSequential: chạy đồng thời nhưng giữ thứ tự phát kết quả

flatMapSequential cho phép các publisher con chạy đồng thời, nhưng phát kết quả theo thứ tự publisher đầu vào. Các kết quả hoàn tất sớm có thể phải chờ trong bộ đệm để giữ thứ tự.

| Toán tử | Xử lý publisher con | Thứ tự đầu ra |
|---|---|---|
| flatMap | Có thể đồng thời | Theo thời điểm phát kết quả |
| concatMap | Tuần tự | Theo thứ tự đầu vào |
| flatMapSequential | Có thể đồng thời | Theo thứ tự publisher đầu vào |

Chọn toán tử dựa trên yêu cầu nghiệp vụ. Không dùng flatMap chỉ vì nó phổ biến nếu thứ tự command phải được bảo toàn.

## 4. Lọc và giới hạn phần tử

Các toán tử lọc giúp loại dữ liệu không cần thiết trước khi gửi qua RSocket hoặc trước khi xử lý nghiệp vụ.

~~~java
Flux<DeviceStatus> usefulStatuses =
    statusService.allStatuses()
        .filter(DeviceStatus::online)
        .distinct(DeviceStatus::sensorId)
        .take(100);
~~~

Một số toán tử thường dùng:

- **filter(predicate):** chỉ giữ phần tử thỏa điều kiện.
- **distinct():** loại phần tử trùng nhau theo equals; có thể dùng distinct(keySelector) để so sánh theo khóa.
- **take(n):** chỉ nhận tối đa n phần tử rồi hoàn tất.
- **skip(n):** bỏ qua n phần tử đầu.
- **takeUntil(predicate):** nhận đến khi điều kiện dừng được thỏa.
- **next():** lấy phần tử đầu tiên và trả về Mono.

Với luồng vô hạn, take hoặc takeUntil có thể tạo một điều kiện kết thúc hữu hạn. Tuy nhiên, nếu client cần theo dõi lâu dài, không nên tự giới hạn số phần tử khi chưa có yêu cầu nghiệp vụ.

## 5. Kết hợp nhiều nguồn dữ liệu

Một route có thể cần dữ liệu từ nhiều service hoặc kết hợp các luồng sự kiện.

### zip: đợi một phần tử từ mỗi nguồn

zip kết hợp các phần tử theo vị trí: phần tử thứ nhất của mỗi nguồn tạo thành một tuple, phần tử thứ hai tạo thành tuple tiếp theo.

~~~java
Mono<DeviceDashboard> dashboard =
    Mono.zip(
        statusService.findStatus(sensorId),
        profileService.findProfile(sensorId),
        alertService.findActiveAlert(sensorId)
    ).map(tuple -> new DeviceDashboard(
        tuple.getT1(),
        tuple.getT2(),
        tuple.getT3()
    ));
~~~

Với Mono, zip hữu ích khi cần tất cả kết quả đơn lẻ trước khi tạo response. Nếu một nguồn hoàn tất rỗng, zip có thể hoàn tất mà không tạo tuple. Nếu nghiệp vụ cho phép thiếu dữ liệu, hãy quy định giá trị mặc định bằng defaultIfEmpty hoặc switchIfEmpty trước khi zip.

### merge: hợp nhất các luồng khi dữ liệu đến

~~~java
Flux<DeviceEvent> allEvents =
    Flux.merge(
        alarmService.events(sensorId),
        statusService.events(sensorId),
        maintenanceService.events(sensorId)
    );
~~~

merge phát dữ liệu theo thời điểm các nguồn phát ra. Không có cam kết giữ thứ tự tổng thể giữa các nguồn.

### concat: nối các luồng theo thứ tự

~~~java
Flux<LogEntry> history =
    Flux.concat(
        logService.loadArchivedLogs(sensorId),
        logService.liveLogs(sensorId)
    );
~~~

concat đợi nguồn trước hoàn tất rồi mới đăng ký nguồn kế tiếp. Với nguồn live không bao giờ hoàn tất, nguồn phía sau sẽ không được đăng ký. Hãy kiểm tra vòng đời của từng nguồn trước khi nối.

### combineLatest: phát kết quả khi bất kỳ nguồn nào cập nhật

combineLatest giữ giá trị gần nhất của mỗi nguồn và tạo kết quả mới khi một nguồn phát giá trị, sau khi tất cả nguồn đã có ít nhất một giá trị. Toán tử này phù hợp để cập nhật dashboard từ nhiều trạng thái độc lập.

Khi chọn toán tử kết hợp, hãy xác định rõ liệu cần ghép theo vị trí, hợp nhất theo thời gian, nối tuần tự hay luôn dùng giá trị mới nhất. Mỗi cách có ngữ nghĩa khác nhau.

## 6. Xử lý trường hợp rỗng và lỗi

Trong một stream, không tìm thấy dữ liệu và xảy ra lỗi là hai tình huống khác nhau. Mono.empty() biểu thị không có phần tử; onError biểu thị thao tác thất bại.

### switchIfEmpty và defaultIfEmpty

Dùng defaultIfEmpty khi cần thay thế bằng một giá trị mặc định:

~~~java
Mono<DeviceStatus> status =
    statusService.findStatus(sensorId)
        .defaultIfEmpty(DeviceStatus.offline(sensorId));
~~~

Dùng switchIfEmpty khi cần chạy một publisher thay thế:

~~~java
Mono<DeviceProfile> profile =
    profileService.findProfile(sensorId)
        .switchIfEmpty(profileService.createDefaultProfile(sensorId));
~~~

Nếu publisher thay thế cần được tạo trễ, có thể đặt nó trong Mono.defer để tránh thực hiện công việc sớm.

### onErrorReturn, onErrorResume và onErrorMap

~~~java
Mono<DeviceStatus> status =
    statusService.findStatus(sensorId)
        .onErrorReturn(DeviceStatus.unknown(sensorId));
~~~

onErrorReturn thay lỗi bằng một giá trị dự phòng. Cách này chỉ phù hợp nếu giá trị dự phòng có ý nghĩa nghiệp vụ và không che giấu lỗi cần được quan sát.

~~~java
Mono<DeviceStatus> status =
    statusService.findStatus(sensorId)
        .onErrorResume(TimeoutException.class,
            error -> cacheService.findLastKnownStatus(sensorId));
~~~

onErrorResume chuyển sang một publisher khác. Có thể phân nhánh theo loại lỗi để chỉ fallback cho lỗi tạm thời hoặc lỗi đã được xác định.

~~~java
Mono<DeviceStatus> status =
    statusService.findStatus(sensorId)
        .onErrorMap(error ->
            new DeviceLookupException(sensorId, error));
~~~

onErrorMap chuyển lỗi hiện tại thành lỗi miền nghiệp vụ khác, giữ nguyên nguyên nhân để phục vụ chẩn đoán.

### doOnError không xử lý thay thế lỗi

~~~java
Mono<DeviceStatus> status =
    statusService.findStatus(sensorId)
        .doOnError(error ->
            metrics.incrementLookupFailure(sensorId));
~~~

doOnError phù hợp cho logging, metrics hoặc quan sát. Lỗi vẫn tiếp tục truyền downstream. Nếu cần fallback, dùng onErrorResume hoặc toán tử xử lý lỗi phù hợp.

### retry và retryWhen

Retry đăng ký lại upstream khi gặp lỗi. Điều này có thể hữu ích với lỗi mạng tạm thời, nhưng cũng có thể lặp lại tác dụng phụ.

~~~java
Mono<DeviceStatus> status =
    statusService.findStatus(sensorId)
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(2))
            .filter(this::isTransientFailure));
~~~

Ví dụ trên thử lại tối đa 3 lần với khoảng chờ tăng dần, chỉ khi lỗi được xem là tạm thời. Cần đặt timeout tổng thể và giới hạn retry để tránh giữ request quá lâu.

Không retry mù quáng thao tác ghi hoặc lệnh điều khiển. Nếu server đã thực hiện lệnh nhưng phản hồi bị mất, lần retry có thể thực hiện lệnh lần thứ hai. Với thao tác có tác dụng phụ, hãy thiết kế idempotency key hoặc cơ chế khử trùng lặp.

## 7. Timeout, fallback và vòng đời subscription

Một tương tác realtime có thể tồn tại lâu, nhưng một request-response thường cần giới hạn thời gian chờ.

~~~java
Mono<DeviceStatus> status =
    statusService.findStatus(sensorId)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
            error -> cacheService.findLastKnownStatus(sensorId));
~~~

timeout phát lỗi nếu nguồn không phát dữ liệu trong khoảng thời gian quy định. Với Mono, thời gian này thường áp dụng cho việc chờ kết quả. Với Flux, timeout có thể áp dụng giữa các phần tử; hãy hiểu rõ overload được chọn và đặt timeout theo yêu cầu của luồng.

Các toán tử quan sát vòng đời thường gặp:

- **doOnSubscribe:** quan sát lúc subscriber đăng ký.
- **doOnNext:** quan sát từng phần tử.
- **doOnComplete:** quan sát khi hoàn tất bình thường.
- **doOnError:** quan sát lỗi.
- **doFinally:** chạy khi kết thúc bằng complete, error hoặc cancel.

~~~java
Flux<Reading> readings =
    sensorService.readings(sensorId)
        .doOnSubscribe(subscription -> metrics.streamStarted(sensorId))
        .doOnNext(reading -> metrics.readingReceived(sensorId))
        .doOnError(error -> logger.warn("Reading stream failed", error))
        .doFinally(signal -> metrics.streamEnded(sensorId, signal));
~~~

doFinally hữu ích để ghi nhận cả trường hợp client hủy stream. Không dùng doOnNext để thay đổi dữ liệu hoặc thực hiện một tác vụ blocking kéo dài; hãy dùng toán tử biến đổi hoặc thiết kế tác vụ riêng phù hợp.

## 8. Điều tiết luồng: backpressure, buffer, window và sample

RSocket hỗ trợ flow control ở mức giao thức cho các interaction model streaming. Trong Reactor, subscriber thể hiện nhu cầu bằng request(n), còn các toán tử có thể điều chỉnh cách upstream được yêu cầu và cách dữ liệu được giữ khi downstream chậm.

Hai lớp này có liên quan nhưng không nên xem là một khái niệm duy nhất. Flow control của RSocket điều tiết việc gửi payload qua giao thức; toán tử Reactor xử lý nhu cầu và hàng đợi trong pipeline ứng dụng. Một toán tử buffer không giới hạn có thể làm tăng bộ nhớ dù kết nối có flow control.

### limitRate

limitRate chia yêu cầu downstream thành các đợt nhỏ hơn khi yêu cầu upstream. Toán tử này có thể giúp điều tiết mức yêu cầu trong một pipeline.

~~~java
Flux<Reading> readings =
    sensorService.readings(sensorId)
        .limitRate(64);
~~~

limitRate không phải giới hạn tốc độ theo số phần tử mỗi giây và cũng không thay thế việc giới hạn tài nguyên ở producer.

### onBackpressureBuffer, onBackpressureDrop và onBackpressureLatest

Các toán tử này hữu ích khi upstream không thể hoặc không tuân theo nhịp yêu cầu của downstream, chẳng hạn khi kết nối với nguồn phát nóng hoặc API callback. Chúng thường yêu cầu upstream phát không giới hạn rồi tự quản lý buffer hoặc phần tử bị bỏ ở ranh giới toán tử. Vì vậy, hãy đặt chúng đúng tại nguồn không thể tuân theo backpressure và chọn chính sách overflow có chủ đích; không thêm chúng vào mọi pipeline.

~~~java
Flux<Reading> buffered =
    hotSensorSource()
        .onBackpressureBuffer(
            500,
            dropped -> metrics.bufferOverflow()
        );
~~~

Buffer có giới hạn 500 phần tử. Khi đầy, ứng dụng phải xử lý overflow theo chính sách đã chọn; overload và hành vi cụ thể cần được kiểm tra theo phiên bản Reactor.

~~~java
Flux<Reading> latest =
    hotSensorSource().onBackpressureLatest();
~~~

onBackpressureLatest giữ giá trị mới nhất khi downstream chậm. Đây có thể là lựa chọn hợp lý cho dashboard chỉ cần trạng thái hiện tại.

~~~java
Flux<Reading> lossy =
    hotSensorSource().onBackpressureDrop(
        reading -> metrics.readingDropped()
    );
~~~

onBackpressureDrop bỏ các phần tử không thể chuyển tiếp ngay. Chỉ dùng khi nghiệp vụ cho phép mất dữ liệu và cần theo dõi số phần tử bị bỏ.

### buffer, window và sample

- **buffer(n):** gom n phần tử thành một collection rồi phát collection đó.
- **window(n):** chia luồng thành các Flux con, mỗi Flux con chứa một nhóm phần tử.
- **sample(duration):** định kỳ phát phần tử gần nhất trong khoảng thời gian.
- **debounce(duration):** chỉ phát phần tử sau khi không có phần tử mới trong khoảng thời gian quy định.

Ví dụ gộp telemetry theo lô:

~~~java
Flux<List<Reading>> batches =
    sensorService.readings(sensorId)
        .bufferTimeout(100, Duration.ofSeconds(1));
~~~

Mỗi batch được phát khi đạt 100 phần tử hoặc khi hết một giây, tùy điều kiện nào đến trước. Cách này có thể giảm chi phí ghi hoặc gửi theo lô, nhưng làm tăng độ trễ của từng phần tử.

Ví dụ dashboard chỉ cần cập nhật giá trị gần nhất mỗi 250 ms:

~~~java
Flux<Reading> displayUpdates =
    sensorService.readings(sensorId)
        .sample(Duration.ofMillis(250));
~~~

Không dùng sample hoặc drop cho dữ liệu cần kiểm toán đầy đủ như giao dịch, lệnh thanh toán hoặc nhật ký bảo mật. Chính sách điều tiết phải phù hợp với giá trị nghiệp vụ của từng sự kiện.

## 9. Scheduler và thao tác blocking

Reactor thường chạy trên các thread được quản lý bởi runtime. Trong ứng dụng Spring WebFlux và RSocket, không nên giả định mỗi request có một thread riêng. Các event loop cần được giữ thông thoáng để xử lý nhiều kết nối.

### subscribeOn và publishOn

subscribeOn ảnh hưởng scheduler dùng để thực hiện subscription và công việc upstream. publishOn chuyển các tín hiệu downstream tiếp theo sang scheduler được chỉ định.

~~~java
Mono<DeviceStatus> status =
    Mono.fromCallable(() -> legacyRepository.loadStatus(sensorId))
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::toDeviceStatus)
        .publishOn(Schedulers.parallel())
        .map(this::calculateDisplayScore);
~~~

Trong ví dụ:

- Lời gọi repository blocking được chạy trên boundedElastic.
- Các bước sau publishOn được xử lý trên scheduler parallel.
- Việc chuyển scheduler có chi phí chuyển tiếp và không nên thêm tùy tiện.

Không dùng Schedulers.parallel() để chạy JDBC blocking hoặc thao tác chờ I/O dài. Với API blocking, boundedElastic thường phù hợp hơn; giải pháp tốt hơn về lâu dài là dùng client non-blocking.

### Tránh block trong pipeline

~~~java
// Không nên trong controller hoặc pipeline reactive:
DeviceStatus status = statusService.findStatus(sensorId).block();
~~~

block() biến luồng xử lý bất đồng bộ thành chờ đồng bộ. Nếu chạy trên event loop, nó có thể làm nghẽn nhiều request hoặc gây lỗi tùy ngữ cảnh. Hãy trả Mono hoặc Flux từ controller/service và nối các thao tác bằng toán tử reactive.

Cũng không nên gọi subscribe() tùy tiện bên trong một service để “chạy nền”. Làm vậy tạo một subscription tách khỏi vòng đời request, khiến caller khó kiểm soát lỗi, hủy, timeout và tài nguyên. Hãy trả publisher cho tầng sở hữu vòng đời tiêu thụ.

## 10. Hot publisher, cold publisher và chia sẻ luồng

Cold publisher thường tạo dữ liệu riêng cho từng subscriber. Ví dụ, một Mono gọi service có thể thực hiện lại lời gọi cho mỗi subscription. Hot publisher phát dữ liệu độc lập với một subscriber cụ thể; subscriber tham gia muộn có thể bỏ lỡ các phần tử trước đó.

~~~java
Flux<Reading> cold =
    Flux.defer(() -> sensorService.readings(sensorId));
~~~

Mỗi subscriber tạo một luồng đọc mới. Điều này phù hợp khi mỗi client RSocket cần một subscription độc lập hoặc có bộ lọc riêng.

~~~java
Flux<Reading> shared =
    sensorService.readings(sensorId).share();
~~~

share() cho phép nhiều subscriber cùng chia sẻ một nguồn trong thời gian có subscriber. Hành vi kết nối lại và vòng đời chia sẻ phụ thuộc trạng thái subscriber; không nên xem share như một kho lưu trữ hoặc cơ chế phát lại bền vững.

Một số toán tử liên quan:

- **share():** chia sẻ subscription giữa nhiều subscriber đang tham gia.
- **publish().refCount(n):** chỉ kết nối nguồn khi có đủ số subscriber theo cấu hình.
- **cache():** lưu và phát lại tín hiệu đã nhận cho subscriber sau; cần chú ý thời hạn và bộ nhớ.
- **replay():** chia sẻ nguồn kèm khả năng phát lại một số phần tử đã lưu tùy cấu hình.

Với server RSocket phát telemetry cho nhiều client, cần quyết định mỗi client có được luồng riêng hay nhiều client cùng nghe một nguồn. Nếu chia sẻ nguồn, hãy xác định quyền truy cập, bộ lọc theo tenant/thiết bị, vòng đời khi subscriber cuối cùng rời đi và chính sách replay. Không dùng cache không giới hạn cho luồng vô hạn.

## 11. Reactor Context và metadata RSocket

Reactor Context là vùng dữ liệu gắn với subscriber, thường dùng để truyền thông tin xuyên qua pipeline như correlation ID, tenant hoặc thông tin phục vụ tracing. Nó khác với metadata của RSocket: metadata là dữ liệu được truyền qua giao thức giữa các peer, còn Reactor Context là ngữ cảnh trong quá trình thực thi reactive ở một phía.

~~~java
String requestId = UUID.randomUUID().toString();

Mono<DeviceStatus> status =
    Mono.deferContextual(context -> {
        String contextRequestId = context.get("requestId");
        return statusService.findStatus(sensorId)
            .doOnNext(value -> logger.debug(
                "requestId={} sensor={}",
                contextRequestId,
                value.sensorId()
            ));
    })
    .contextWrite(context -> context.put("requestId", requestId));
~~~

Ví dụ tạo requestId để minh họa cách ghi và đọc Reactor Context. Trong ứng dụng thực tế, giá trị này thường được lấy từ metadata RSocket sau khi kiểm tra và xác thực, rồi đưa vào Reactor Context để tracing xuyên suốt pipeline.

Không đưa secret hoặc dữ liệu nhạy cảm vào log. Metadata do client gửi phải được xem là đầu vào không tin cậy; server cần xác thực và phân quyền độc lập với việc một giá trị tenant hoặc user ID xuất hiện trong metadata.

## 12. Áp dụng toán tử vào bốn interaction model RSocket

Spring RSocket có thể ánh xạ route bằng @MessageMapping. Kiểu tham số và kiểu trả về reactive giúp thể hiện hình dạng tương tác.

~~~java
@Controller
class SensorController {

    private final SensorService sensorService;
    private final DeviceService deviceService;

    SensorController(
            SensorService sensorService,
            DeviceService deviceService) {
        this.sensorService = sensorService;
        this.deviceService = deviceService;
    }

    // Request-response: một query, một trạng thái.
    @MessageMapping("sensor.status")
    Mono<DeviceStatus> status(SensorQuery query) {
        return sensorService.findStatus(query.sensorId())
            .switchIfEmpty(Mono.error(
                new SensorNotFoundException(query.sensorId())
            ))
            .timeout(Duration.ofSeconds(2));
    }

    // Request-stream: một query, nhiều reading.
    @MessageMapping("sensor.readings")
    Flux<Reading> readings(SensorQuery query) {
        return sensorService.readings(query.sensorId())
            .filter(Reading::isValid)
            // Chỉ dùng nếu dashboard có thể bỏ qua giá trị trung gian.
            .onBackpressureLatest();
    }

    // Request-channel: nhận nhiều command và phát nhiều event.
    @MessageMapping("sensor.control")
    Flux<DeviceEvent> control(Flux<DeviceCommand> commands) {
        return commands
            .filter(DeviceCommand::isValid)
            .concatMap(command -> deviceService.handle(command)
                .onErrorResume(
                    DeviceCommandException.class,
                    error -> Mono.just(DeviceEvent.rejected(error.getMessage()))
                ));
    }

    // Fire-and-forget: gửi sự kiện không cần response nghiệp vụ.
    @MessageMapping("sensor.telemetry")
    Mono<Void> telemetry(Reading reading) {
        return sensorService.record(reading);
    }
}
~~~

Các điểm cần chú ý:

- Request-response thường trả Mono<T>; lỗi và trường hợp không tìm thấy dữ liệu cần có ngữ nghĩa rõ ràng.
- Request-stream thường trả Flux<T>; cần tính đến cancellation, backpressure và lỗi giữa luồng.
- Request-channel nhận một Flux<T> và có thể trả một Flux<R>; concatMap phù hợp khi thứ tự command phải được giữ.
- Fire-and-forget không trả kết quả nghiệp vụ cho caller. Mono<Void> biểu diễn việc hoàn tất xử lý phía server trong pipeline, nhưng client không nhận một response nghiệp vụ để xác nhận kết quả.

Đoạn code là ví dụ minh họa. Các DTO, service, exception và cấu hình RSocket cần được định nghĩa trong ứng dụng. Với fire-and-forget, hãy quyết định cách quan sát lỗi phía server vì client không có response nghiệp vụ để nhận lỗi xử lý.

## 13. Kiểm thử pipeline bằng StepVerifier

StepVerifier thuộc Reactor Test, giúp kiểm tra các tín hiệu mà publisher phát ra mà không cần tự subscribe và ghi nhận thủ công.

~~~java
@Test
void filtersInvalidReadings() {
    Flux<Reading> source = Flux.just(
        new Reading("sensor-01", 28.4, true),
        new Reading("sensor-01", -1.0, false),
        new Reading("sensor-01", 29.1, true)
    );

    StepVerifier.create(source.filter(Reading::isValid))
        .expectNextMatches(reading -> reading.temperature() == 28.4)
        .expectNextMatches(reading -> reading.temperature() == 29.1)
        .verifyComplete();
}
~~~

Có thể kiểm tra lỗi và fallback:

~~~java
@Test
void usesFallbackWhenLookupIsEmpty() {
    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(Mono.just("offline"));

    StepVerifier.create(result)
        .expectNext("offline")
        .verifyComplete();
}
~~~

Với publisher có delay hoặc timeout, StepVerifier.withVirtualTime có thể giúp kiểm tra thời gian mà không phải chờ thật. Với RSocket end-to-end, ngoài unit test toán tử, nên có integration test cho kết nối, route, metadata, cancellation và xử lý lỗi khi peer ngắt kết nối.

## 14. Lỗi thường gặp khi sử dụng Reactor trong ứng dụng RSocket

| Cách làm dễ gây lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng map khi hàm trả về Mono/Flux | Tạo Mono<Mono<T>> hoặc Flux<Mono<T>> | Dùng flatMap hoặc concatMap |
| Dùng flatMap cho command cần đúng thứ tự | Kết quả có thể đến không theo thứ tự đầu vào | Dùng concatMap hoặc flatMapSequential khi phù hợp |
| Gọi block() trên event loop | Chặn xử lý các kết nối khác | Giữ pipeline reactive hoặc chuyển API blocking sang boundedElastic |
| Gọi subscribe() trong service để chạy nền | Caller mất quyền quản lý lỗi và cancellation | Trả publisher cho tầng sở hữu subscription |
| Retry thao tác ghi không có idempotency | Có thể thực hiện tác dụng phụ nhiều lần | Thiết kế idempotency và giới hạn retry |
| Dùng buffer không giới hạn | Bộ nhớ có thể tăng liên tục khi consumer chậm | Dùng giới hạn và chính sách overflow rõ ràng |
| Dùng onErrorReturn cho mọi lỗi | Che giấu sự cố và tạo dữ liệu giả | Chỉ fallback cho lỗi đã xác định, ghi nhận lỗi còn lại |
| Cache một Flux vô hạn | Giữ dữ liệu và tài nguyên không giới hạn | Dùng chia sẻ phù hợp hoặc cache có giới hạn/thời hạn |
| Bỏ qua cancellation | Công việc vẫn chạy sau khi client rời stream | Propagate cancellation và giải phóng tài nguyên |
| Chạy I/O blocking trên parallel/event loop | Làm nghẽn scheduler | Dùng boundedElastic tạm thời hoặc client non-blocking |

## Kết luận

Khi xây dựng ứng dụng RSocket với Reactor, hãy bắt đầu từ hình dạng tương tác: Mono cho kết quả đơn, Flux cho chuỗi phần tử. Dùng map để biến đổi giá trị, flatMap để nối các thao tác bất đồng bộ, concatMap để bảo toàn thứ tự, và các toán tử kết hợp để phối hợp nhiều nguồn.

Sau đó thiết kế vòng đời của pipeline: xử lý dữ liệu rỗng, lỗi, timeout, retry và cancellation; điều tiết dữ liệu bằng backpressure và buffer có giới hạn; tránh block trên event loop; kiểm soát cách chia sẻ publisher giữa các client. Khi những quyết định này rõ ràng, các route request-response, fire-and-forget, request-stream và request-channel sẽ dễ vận hành và kiểm thử hơn.
