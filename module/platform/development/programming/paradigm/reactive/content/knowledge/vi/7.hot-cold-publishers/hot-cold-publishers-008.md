# Bên tiêu thụ chậm trong một luồng dùng chung

Một luồng nóng có thể phát sự kiện theo nhịp riêng, trong khi nhiều subscriber cùng nhận dữ liệu. Các subscriber không nhất thiết xử lý nhanh như nhau: một bên cập nhật giao diện gần như tức thì, một bên ghi dữ liệu xuống kho lưu trữ, còn một bên gọi dịch vụ bên ngoài và thường xuyên bị chậm. Khi tốc độ phát cao hơn tốc độ xử lý của một subscriber, dữ liệu có thể tích tụ, bị bỏ, làm chậm cả nhóm hoặc khiến subscriber đó gặp lỗi.

Đây là vấn đề quan trọng khi dùng hot publisher và multicast trong Reactive Programming. Với Java Reactor, cần hiểu nhu cầu của từng subscriber, vị trí đặt toán tử backpressure và chính sách dành cho dữ liệu đến nhanh hơn khả năng tiêu thụ. Mỗi lựa chọn có ý nghĩa khác nhau: buffer giữ lại dữ liệu, drop bỏ phần tử mới khi không có nhu cầu, latest giữ giá trị mới nhất, còn một số kiểu multicast cho phép subscriber nhanh tiếp tục trong khi subscriber chậm bỏ lỡ tín hiệu.

## 1. Vì sao subscriber trong cùng luồng có thể xử lý khác tốc độ?

Hot publisher phát dữ liệu độc lập với việc từng subscriber có đang yêu cầu dữ liệu hay không. Khi một subscriber tham gia, nó nhận các sự kiện được phát từ thời điểm tham gia trở đi; các sự kiện đã phát trước đó thường không được gửi lại, trừ khi nguồn có cơ chế replay.

Một luồng dùng chung có thể phục vụ nhiều vai trò:

- Subscriber A cập nhật số liệu trên dashboard.
- Subscriber B lưu từng sự kiện vào cơ sở dữ liệu.
- Subscriber C gửi thông báo qua một dịch vụ mạng.

Nếu nguồn phát 100 sự kiện mỗi giây, subscriber A có thể xử lý đủ 100 sự kiện, trong khi subscriber B chỉ xử lý được 40 và subscriber C chỉ xử lý được 10. Chênh lệch này tạo ra độ trễ và backlog. Nếu hệ thống không có chính sách rõ ràng, bộ nhớ có thể tăng liên tục hoặc một subscriber chậm có thể ảnh hưởng đến những subscriber còn lại.

Trong Reactive Streams, mỗi subscription có nhu cầu riêng. Subscriber biểu thị nhu cầu bằng request(n); publisher không được phát vượt quá số phần tử đã được yêu cầu trên subscription đó. Tuy nhiên, nguồn hot bên ngoài như callback API, timer hoặc event bus có thể tiếp tục phát theo nhịp riêng. Adapter và các toán tử trong pipeline phải quyết định cách xử lý những sự kiện đến khi downstream chưa có nhu cầu.

## 2. Phân biệt tốc độ phát, nhu cầu và tốc độ xử lý

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa |
|---|---|
| Tốc độ phát | Số sự kiện nguồn tạo ra trong một đơn vị thời gian |
| Nhu cầu | Số phần tử subscriber cho phép phát thêm qua request(n) |
| Tốc độ xử lý | Số sự kiện subscriber thực sự xử lý xong trong một đơn vị thời gian |

Nếu tốc độ phát cao hơn tốc độ xử lý trong một khoảng thời gian, backlog có xu hướng tăng. Với nguồn có khả năng tuân thủ backpressure, nhu cầu thấp có thể làm nguồn giảm tốc hoặc tạm dừng. Với nguồn không thể tạm dừng, hệ thống cần buffer, drop, giữ giá trị mới nhất, từ chối hoặc chuyển dữ liệu sang một nơi lưu trữ khác.

Ví dụ, một nguồn phát 100 sự kiện mỗi giây và subscriber xử lý 60 sự kiện mỗi giây. Backlog tăng khoảng 40 sự kiện mỗi giây trong thời gian chênh lệch đó. Nếu tình trạng kéo dài, buffer hữu hạn cuối cùng sẽ đầy. Tăng buffer chỉ kéo dài thời gian trước khi đầy; nó không giải quyết được chênh lệch tốc độ tồn tại liên tục.

## 3. Điều gì xảy ra trong một luồng multicast?

Multicast phân phối cùng một luồng sự kiện đến nhiều subscriber. Mỗi subscriber có subscription riêng, nhưng các subscriber cùng quan sát một nguồn phát hoặc một kết nối upstream dùng chung.

Một cách tạo luồng dùng chung trong Reactor là share():

    Flux<Event> sharedEvents = eventSource.events().share();

    sharedEvents.subscribe(this::updateDashboard);
    sharedEvents.subscribe(this::writeAuditRecord);

share() chia sẻ một subscription upstream giữa các subscriber đang tham gia. Nó kết nối khi subscriber đầu tiên đăng ký và ngắt kết nối khi không còn subscriber nào. Đây là luồng nóng trong thời gian được chia sẻ; subscriber đến muộn không tự động nhận lại các phần tử đã phát trước khi tham gia.

Điểm cần chú ý là chính sách multicast và nguồn upstream ảnh hưởng đến cách subscriber chậm tác động đến nhóm. Một số operator multicast phối hợp nhu cầu giữa các subscriber và có thể tạm dừng yêu cầu upstream khi một subscriber không có nhu cầu. Nếu nguồn không thể tạm dừng, điều đó có thể khiến adapter hoặc nguồn gặp áp lực. Một chính sách backpressure đặt riêng cho từng nhánh có thể giúp cô lập subscriber chậm.

Luồng dùng chung không đồng nghĩa mỗi subscriber có một bản sao dữ liệu được lưu vô hạn. Nếu cần lưu từng sự kiện cho consumer xử lý sau, phải thiết kế hàng đợi hoặc broker có khả năng lưu giữ phù hợp.

## 4. Bốn chính sách thường dùng cho subscriber chậm

Khi subscriber không có nhu cầu mà sự kiện vẫn đến, có một số lựa chọn. Chính sách đúng phụ thuộc vào việc dữ liệu có được phép mất hay không và subscriber cần lịch sử hay chỉ cần trạng thái hiện tại.

| Chính sách | Hành vi khi subscriber chậm | Phù hợp với |
|---|---|---|
| Buffer | Giữ các phần tử đang chờ để phát sau | Sự kiện cần xử lý đầy đủ trong một khoảng tải đột biến |
| Drop | Bỏ phần tử mới đến khi downstream chưa có nhu cầu | Số liệu lấy mẫu hoặc sự kiện không quan trọng |
| Latest | Giữ phần tử mới nhất, thay thế giá trị đang chờ | Trạng thái hiện tại, vị trí, giá trị hiển thị |
| Từ chối hoặc ngắt subscriber | Báo overflow hoặc kết thúc nhánh chậm | Subscriber không đáp ứng SLA hoặc không thể giữ backlog |

### 4.1. Buffer: giữ lại sự kiện để xử lý sau

Buffer xếp các sự kiện đến trong lúc downstream chưa sẵn sàng. Khi subscriber yêu cầu thêm dữ liệu, các phần tử đã xếp hàng được phát theo thứ tự.

Trong Reactor, onBackpressureBuffer có thể đặt sau một nguồn hot:

    Flux<Event> bufferedEvents =
        sharedEvents.onBackpressureBuffer(500);

Tham số 500 giới hạn số phần tử được giữ trong buffer của nhánh này. Khi buffer đầy, Reactor báo lỗi overflow cho nhánh đó. Hãy chọn kích thước dựa trên kích thước phần tử, thời gian chậm có thể chấp nhận và lượng tải đột biến dự kiến.

Buffer phù hợp khi cần giữ thứ tự và không muốn bỏ dữ liệu trong các đợt chậm ngắn. Tuy nhiên, buffer hữu hạn không thể hấp thụ mãi nếu producer liên tục nhanh hơn consumer. Buffer không giới hạn có thể làm ứng dụng cạn bộ nhớ; buffer có giới hạn cần một chính sách khi đầy như báo lỗi, lưu bền vững hoặc ngắt subscriber chậm.

### 4.2. Drop: bỏ sự kiện khi subscriber chưa sẵn sàng

onBackpressureDrop bỏ phần tử đến khi downstream chưa có nhu cầu. Subscriber nhận các phần tử khi nó có nhu cầu, nhưng có thể bỏ lỡ sự kiện xảy ra trong lúc không sẵn sàng.

    Flux<Event> sampledEvents =
        sharedEvents.onBackpressureDrop(
            dropped -> metrics.incrementDroppedEvents()
        );

Callback cho phép ghi nhận số phần tử bị bỏ. Drop hữu ích khi mất một số mẫu không làm sai ý nghĩa của kết quả, ví dụ dữ liệu telemetry tần suất cao. Nó không phù hợp với giao dịch, lệnh thanh toán hoặc sự kiện nghiệp vụ cần được xử lý đầy đủ.

### 4.3. Latest: chỉ giữ trạng thái mới nhất

onBackpressureLatest giữ lại phần tử mới nhất trong lúc downstream không có nhu cầu. Nếu thêm phần tử mới đến trước khi subscriber nhận phần tử đang chờ, giá trị đang chờ được thay thế.

    Flux<Position> currentPosition =
        sharedPositions.onBackpressureLatest();

Chính sách này phù hợp với dữ liệu mà giá trị mới nhất có ý nghĩa hơn lịch sử trung gian, chẳng hạn vị trí thiết bị hoặc trạng thái hiển thị. Khi subscriber sẵn sàng, nó nhận giá trị gần nhất mà operator đang giữ.

Latest không bảo đảm nhận mọi chuyển đổi trạng thái. Nếu một sự kiện trung gian quan trọng đối với nghiệp vụ, việc thay thế nó bằng giá trị mới hơn sẽ làm mất thông tin cần thiết.

### 4.4. Từ chối hoặc ngắt subscriber chậm

Một hệ thống có thể quyết định subscriber chậm không được tiếp tục tham gia nếu nó không thể theo kịp luồng. Ví dụ, buffer hữu hạn đầy có thể làm nhánh đó kết thúc bằng lỗi overflow; tầng quản lý subscription có thể ghi nhận lỗi và yêu cầu client kết nối lại hoặc chuyển sang một luồng phục hồi.

Chính sách này phù hợp khi mỗi subscriber có giới hạn độ trễ hoặc tài nguyên rõ ràng. Cần xác định cách client biết nhánh đã bị ngắt, cách retry và liệu dữ liệu bỏ lỡ có thể được đọc lại từ một nguồn lưu trữ bền vững hay không.

## 5. Cô lập chính sách giữa các subscriber

Một quyết định quan trọng là đặt toán tử backpressure trước hay sau điểm chia sẻ.

Nếu đặt chính sách trước share(), mọi subscriber nhận cùng một luồng đã được xử lý theo chính sách đó. Nếu đặt chính sách sau share(), mỗi nhánh có thể có một cách xử lý backlog riêng.

Ví dụ:

    Flux<Event> shared = eventSource.events().share();

    shared
        .onBackpressureBuffer(500)
        .subscribe(this::writeAuditRecord);

    shared
        .onBackpressureDrop(this::recordDroppedMetric)
        .subscribe(this::updateDashboard);

Nhánh audit buffer các sự kiện đang chờ và có thể báo overflow nếu vượt giới hạn. Nhánh dashboard bỏ sự kiện khi chưa có nhu cầu. Hai nhánh thể hiện hai yêu cầu nghiệp vụ khác nhau.

So sánh vị trí đặt chính sách:

| Cách đặt | Phạm vi tác động | Hệ quả |
|---|---|---|
| source.onBackpressureDrop().share() | Một chính sách chung trước multicast | Sự kiện bị bỏ ở nguồn chia sẻ sẽ mất với tất cả subscriber |
| source.share().onBackpressureDrop() | Chính sách riêng sau multicast | Mỗi subscriber có thể bỏ dữ liệu độc lập |
| source.share().onBackpressureBuffer(n) | Buffer riêng sau multicast | Một subscriber chậm có thể giữ backlog riêng trong giới hạn n |

Các operator multicast vẫn có cơ chế phối hợp nhu cầu upstream của riêng chúng. Đặt operator sau share() giúp tạo chính sách tiêu thụ riêng cho từng nhánh, nhưng không tự động biến mọi nguồn thành nguồn có thể phát vô hạn. Cần xem xét cả hành vi của nguồn, operator chia sẻ và dung lượng buffer.

## 6. Chọn kiểu multicast khi dùng Reactor Sinks

Khi ứng dụng tự phát sự kiện qua Reactor Sinks, có thể chọn kiểu multicast theo cách muốn xử lý subscriber không có nhu cầu.

### 6.1. Multicast có buffer

Sinks.many().multicast().onBackpressureBuffer() cung cấp một sink multicast có cơ chế buffer và tôn trọng nhu cầu của các subscriber. Cách này hữu ích khi cần giữ các phần tử trong lúc subscriber chưa yêu cầu, nhưng buffer có giới hạn và việc phát có thể thất bại khi vượt khả năng chứa.

    Sinks.Many<Event> eventSink =
        Sinks.many().multicast().onBackpressureBuffer();

    Sinks.EmitResult result = eventSink.tryEmitNext(event);
    if (result.isFailure()) {
        handleEmissionFailure(result);
    }

tryEmitNext trả về kết quả để ứng dụng xử lý khi không thể phát. Không nên bỏ qua EmitResult hoặc lặp thử vô hạn; cần phân biệt trường hợp không có subscriber, sink đã bị hủy, buffer đầy hoặc có phát đồng thời không hợp lệ.

### 6.2. directBestEffort: subscriber nhanh tiếp tục nhận

Sinks.many().multicast().directBestEffort() chỉ gửi phần tử cho subscriber đang có nhu cầu. Subscriber không có nhu cầu sẽ bỏ lỡ phần tử đó, còn subscriber khác có nhu cầu vẫn có thể nhận.

    Sinks.Many<Event> eventSink =
        Sinks.many().multicast().directBestEffort();

    eventSink.tryEmitNext(event);

Kiểu sink này hữu ích khi subscriber nhanh cần tiếp tục nhận dữ liệu ngay cả khi subscriber khác chậm, và việc bỏ một số sự kiện ở nhánh chậm được chấp nhận. Nếu mọi subscriber phải nhận đầy đủ mọi sự kiện, directBestEffort không phù hợp.

### 6.3. directAllOrNothing: giữ tính đồng bộ giữa các subscriber

Sinks.many().multicast().directAllOrNothing() áp dụng chính sách tất cả hoặc không: nếu có subscriber không có nhu cầu, phần tử không được gửi cho bất kỳ subscriber nào. Cách này phù hợp khi các subscriber phải quan sát cùng một tập tín hiệu và việc chỉ một số bên nhận được sự kiện sẽ làm mất tính nhất quán của luồng.

Chính sách này không làm subscriber chậm nhanh hơn. Nó có thể khiến subscriber nhanh cũng bỏ lỡ phần tử trong lúc một subscriber khác chưa sẵn sàng. Nếu cần lưu lại sự kiện để tất cả bên nhận xử lý sau, hãy chọn cơ chế buffer hoặc broker có khả năng lưu giữ.

Tóm tắt các lựa chọn:

| Sink multicast | Subscriber chậm | Subscriber đang có nhu cầu |
|---|---|---|
| onBackpressureBuffer() | Có thể nhận lại phần tử đã buffer khi có nhu cầu; có thể overflow | Nhận theo nhu cầu |
| directBestEffort() | Bỏ lỡ phần tử khi không có nhu cầu | Vẫn nhận phần tử |
| directAllOrNothing() | Không nhận phần tử | Cũng không nhận phần tử đó nếu có subscriber khác thiếu nhu cầu |

## 7. Ví dụ: một subscriber nhanh và một subscriber chậm

Ví dụ sau chia sẻ một nguồn timer. Nhánh nhanh xử lý mọi tick ngay khi nhận. Nhánh chậm dùng buffer giới hạn và chỉ yêu cầu phần tử tiếp theo sau một khoảng trễ. Phần xử lý trong hook cần ngắn; ví dụ chỉ trì hoãn việc bổ sung nhu cầu để mô phỏng consumer chậm mà không chặn thread phát timer.

    import java.time.Duration;
    import java.util.concurrent.TimeUnit;
    import org.reactivestreams.Subscription;
    import reactor.core.publisher.BaseSubscriber;
    import reactor.core.publisher.Flux;
    import reactor.core.scheduler.Schedulers;

    Flux<Long> sharedTicks =
        Flux.interval(Duration.ofMillis(100)).share();

    sharedTicks.subscribe(
        tick -> log.info("fast subscriber: {}", tick)
    );

    sharedTicks
        .onBackpressureBuffer(32)
        .subscribe(new BaseSubscriber<Long>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Long tick) {
                log.info("slow subscriber: {}", tick);
                Schedulers.parallel().schedule(
                    () -> request(1),
                    500,
                    TimeUnit.MILLISECONDS
                );
            }

            @Override
            protected void hookOnError(Throwable error) {
                log.error("slow subscriber stopped", error);
            }
        });

Nguồn phát một tick mỗi 100 ms. Nhánh chậm chỉ bổ sung một đơn vị nhu cầu sau 500 ms, vì vậy buffer giữ các tick đến trong lúc nhánh chưa sẵn sàng. Nếu buffer 32 phần tử đầy, nhánh chậm kết thúc bằng lỗi overflow theo chính sách của onBackpressureBuffer(32). Nhánh nhanh vẫn có thể tiếp tục nhận dữ liệu vì chính sách buffer được đặt trên nhánh chậm sau share().

Đoạn mã minh họa cơ chế điều tiết nhu cầu, không phải cấu hình production hoàn chỉnh. Trong ứng dụng thật, cần giữ và dispose các tác vụ hoặc subscription có vòng đời riêng, ghi nhận overflow, chọn chính sách phục hồi và bảo đảm công việc xử lý không bị chặn trên thread của nguồn.

## 8. Ước lượng buffer và giới hạn backlog

Buffer nên được chọn theo mức chênh lệch tốc độ và khoảng thời gian chậm có thể chấp nhận. Một ước lượng đơn giản cho số phần tử cần chứa trong một đợt tải:

    backlog_ước_tính =
        max(0, tốc_độ_phát - tốc_độ_xử_lý) * thời_gian_chậm

Ví dụ, nguồn phát 100 phần tử mỗi giây, subscriber xử lý 60 phần tử mỗi giây và hệ thống muốn hấp thụ đợt chậm kéo dài 5 giây:

    backlog = (100 - 60) * 5 = 200 phần tử

Buffer 200 phần tử chỉ đủ cho tình huống giả định đó. Nếu subscriber tiếp tục xử lý chậm hơn nguồn sau năm giây, backlog vẫn tăng. Kích thước phần tử cũng quan trọng: 200 đối tượng lớn có thể tốn nhiều bộ nhớ hơn đáng kể so với 200 đối tượng nhỏ.

Khi chọn giới hạn, hãy cân nhắc:

- Tốc độ phát trung bình và tốc độ phát đỉnh.
- Tốc độ xử lý thực tế của từng subscriber.
- Thời gian chậm tối đa cần hấp thụ.
- Kích thước trung bình và trường hợp xấu nhất của mỗi phần tử.
- Số subscriber đồng thời và số buffer độc lập.
- Hành vi khi buffer đầy: lỗi, drop, lưu bền vững hoặc ngắt subscriber.

Không dùng buffer vô hạn chỉ để tránh lỗi overflow. Nếu producer liên tục nhanh hơn consumer, buffer vô hạn chỉ trì hoãn sự cố và tăng nguy cơ cạn bộ nhớ.

## 9. Khi nào cần broker thay vì chỉ dùng hot Flux?

Hot Flux và Sinks phù hợp cho phân phối sự kiện trong phạm vi tiến trình hoặc khi không cần lưu giữ lâu dài. Chúng không tự cung cấp lịch sử bền vững, xác nhận xử lý, phát lại từ offset hay khả năng phục hồi sau khi tiến trình khởi động lại.

Nếu mỗi consumer phải xử lý đầy đủ mọi sự kiện, kể cả khi tạm thời offline hoặc chậm nhiều phút, hãy cân nhắc message broker hoặc log sự kiện có lưu trữ bền vững. Ví dụ, Kafka cho phép consumer theo dõi offset riêng và đọc lại dữ liệu theo chính sách lưu giữ; các broker khác có mô hình queue, acknowledgment và retry riêng.

Một kiến trúc thường gặp là:

1. Nguồn nghiệp vụ ghi sự kiện vào outbox hoặc broker.
2. Mỗi consumer đọc theo tốc độ của mình.
3. Consumer xác nhận hoặc lưu offset sau khi xử lý.
4. Khi consumer chậm, backlog tồn tại trong broker theo giới hạn lưu giữ.
5. Consumer có thể phục hồi bằng cách tiếp tục từ vị trí đã ghi nhận.

Broker không loại bỏ nhu cầu kiểm soát tải. Nó chuyển nơi lưu backlog và bổ sung khả năng phục hồi; vẫn cần theo dõi consumer lag, giới hạn tốc độ, retry, thứ tự và dung lượng lưu trữ.

## 10. Quan sát subscriber chậm trong vận hành

Để phát hiện một subscriber đang tụt lại, chỉ đo tổng throughput của nguồn là chưa đủ. Nên theo dõi từng nhánh hoặc từng nhóm consumer:

- Số phần tử đang chờ trong buffer và tỷ lệ sử dụng dung lượng.
- Số phần tử bị drop hoặc bị thay thế bởi chính sách latest.
- Số lần overflow và số subscription bị kết thúc vì quá tải.
- Độ trễ từ thời điểm sự kiện được tạo đến thời điểm subscriber xử lý xong.
- Tốc độ phát so với tốc độ xử lý của từng subscriber.
- Số lần reconnect, retry và thời gian subscriber ở trạng thái lagging.

Gắn event ID hoặc timestamp vào dữ liệu giúp đo độ trễ và phát hiện khoảng sự kiện bị bỏ lỡ. Correlation ID hữu ích khi một sự kiện đi qua nhiều thành phần. Tránh ghi toàn bộ payload nhạy cảm vào log chỉ để đo lag; metadata nhỏ thường đủ cho việc quan sát.

Khi một nhánh thường xuyên overflow, hãy xem lại năng lực xử lý, giới hạn concurrency và các lời gọi blocking trước khi chỉ tăng buffer. Nếu subscriber không thể bắt kịp theo thiết kế, cần thay đổi chính sách dữ liệu hoặc chuyển nhánh đó sang cơ chế lưu trữ bền vững.

## 11. Chọn chính sách theo ý nghĩa dữ liệu

Hãy bắt đầu từ yêu cầu nghiệp vụ:

| Yêu cầu của subscriber | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Phải xử lý mọi giao dịch | Broker bền vững hoặc buffer có giới hạn với overflow được xử lý rõ | Không được mất sự kiện nghiệp vụ |
| Chỉ cần trạng thái mới nhất | Latest | Trạng thái cũ có thể bị thay thế |
| Chấp nhận mất một số mẫu | Drop hoặc directBestEffort | Giữ độ trễ thấp và không tích tụ backlog |
| Mọi subscriber phải thấy cùng tập tín hiệu | directAllOrNothing hoặc một luồng lưu trữ có đồng bộ | Tránh subscriber nhanh nhận dữ liệu mà subscriber chậm bỏ lỡ |
| Subscriber chậm không được ảnh hưởng nhóm | Chính sách riêng sau điểm share, hoặc tách consumer qua broker | Cô lập tốc độ xử lý từng nhánh |

Không có một chính sách tối ưu cho mọi luồng. Một hệ thống có thể dùng buffer cho audit, latest cho dashboard và broker bền vững cho xử lý nghiệp vụ. Điều quan trọng là mỗi lựa chọn phải phản ánh rõ dữ liệu nào được giữ, dữ liệu nào có thể mất và điều gì xảy ra khi subscriber không theo kịp.

## 12. Checklist thiết kế luồng dùng chung

Khi thiết kế một hot publisher có nhiều subscriber, hãy trả lời:

1. Nguồn phát có hỗ trợ backpressure hay phát theo nhịp độc lập?
2. Mỗi subscriber cần toàn bộ lịch sử hay chỉ cần giá trị mới nhất?
3. Một subscriber chậm có được phép làm chậm các subscriber khác không?
4. Chính sách buffer, drop, latest hoặc overflow được đặt trước hay sau điểm multicast?
5. Buffer tối đa chứa bao nhiêu phần tử và bao nhiêu byte?
6. Khi buffer đầy, hệ thống báo lỗi, bỏ dữ liệu, lưu bền vững hay ngắt subscriber?
7. Subscriber có thể reconnect và đọc lại dữ liệu đã bỏ lỡ không?
8. Metric nào cho biết subscriber đang lag hoặc thường xuyên overflow?

Khi các câu trả lời này rõ ràng, ta có thể chọn chính sách phù hợp cho từng subscriber và dự đoán tác động của một consumer chậm lên toàn bộ luồng. Đây là điều kiện cần để dùng hot publisher an toàn khi chia sẻ sự kiện giữa nhiều thành phần trong ứng dụng reactive Java.
