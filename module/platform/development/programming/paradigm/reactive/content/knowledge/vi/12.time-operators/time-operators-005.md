# throttle và sample: lựa chọn giá trị theo nhịp thời gian

Trong một luồng sự kiện, nguồn có thể phát nhiều giá trị hơn mức mà ứng dụng cần hiển thị hoặc xử lý. Ví dụ, giao diện theo dõi giá cổ phiếu có thể nhận hàng trăm cập nhật mỗi giây nhưng chỉ cần làm mới màn hình vài lần mỗi giây. Một dịch vụ nhận thay đổi từ ô tìm kiếm có thể chỉ cần gửi truy vấn sau khi người dùng ngừng gõ. Trong những trường hợp này, ta cần chọn giá trị theo thời gian và quyết định những giá trị trung gian nào có thể bỏ qua.

Project Reactor cung cấp các toán tử sample, sampleFirst và sampleTimeout để xử lý những nhu cầu khác nhau. Trong nhiều thư viện reactive khác, các hành vi tương ứng thường được gọi là throttleLast, throttleFirst và debounce. Tên gọi giữa các thư viện không hoàn toàn thống nhất, vì vậy hãy hiểu quy tắc phát giá trị thay vì chỉ dựa vào tên.

Bài học thuộc chương **Thời gian** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; các toán tử theo thời gian trong bài được vận dụng cùng Mono, Flux, scheduler, xử lý lỗi và kiểm thử pipeline Java.

Các ví dụ sử dụng Project Reactor. Những tên như marketFeed, queryChanges, log hoặc Event đại diện cho thành phần của ứng dụng; hãy thay bằng kiểu và bean thực tế của dự án.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích cách sample chọn giá trị mới nhất theo các nhịp lấy mẫu định kỳ.
- Phân biệt sample với sampleFirst và hiểu hành vi thường được gọi là throttleLast, throttleFirst.
- Dùng sampleTimeout để chỉ phát giá trị sau một khoảng thời gian không có sự kiện mới.
- Chọn scheduler và khoảng thời gian phù hợp với mục đích xử lý.
- Giải thích vì sao các toán tử lấy mẫu làm mất một số giá trị và không thay thế backpressure.
- Kiểm thử các nhịp lấy mẫu và hành vi loại bỏ giá trị bằng StepVerifier.

## 1. Vì sao cần lấy mẫu theo thời gian?

Giả sử một nguồn phát nhiệt độ liên tục:

~~~java
Flux<Temperature> readings = sensor.readings();
~~~

Nếu cảm biến phát 100 mẫu mỗi giây nhưng giao diện chỉ cần cập nhật 2 lần mỗi giây, gửi tất cả mẫu đến giao diện có thể gây lãng phí băng thông và công việc render. Ta có thể chọn một giá trị đại diện trong mỗi khoảng thời gian:

~~~java
Flux<Temperature> displayReadings =
    readings.sample(Duration.ofMillis(500));
~~~

sample lấy giá trị mới nhất đã nhận được tại mỗi nhịp lấy mẫu. Nếu có nhiều mẫu đến trong 500 ms, các mẫu cũ hơn trong cùng khoảng bị bỏ qua và chỉ giá trị mới nhất được phát tại nhịp lấy mẫu. Nếu không có giá trị mới trong một khoảng, toán tử không tạo ra một phần tử giả.

Lấy mẫu hữu ích khi trạng thái mới nhất có giá trị hơn toàn bộ lịch sử cập nhật. Ví dụ:

- Giao diện giám sát chỉ cần trạng thái mới nhất theo chu kỳ.
- Dashboard cần giảm số lần cập nhật biểu đồ.
- Luồng telemetry có thể bỏ các mẫu trung gian khi mục tiêu là quan sát xu hướng.
- Bộ tổng hợp cần lấy một giá trị gần nhất tại các thời điểm định kỳ.

Không nên lấy mẫu nếu mọi sự kiện đều phải được xử lý, chẳng hạn giao dịch thanh toán, thay đổi số dư, sự kiện kiểm toán hoặc lệnh điều khiển thiết bị. Khi đó, bỏ một sự kiện có thể làm sai kết quả nghiệp vụ.

## 2. sample: phát giá trị mới nhất theo nhịp định kỳ

sample(Duration) lấy mẫu theo một khoảng thời gian cố định. Mỗi nhịp, toán tử phát giá trị mới nhất mà nó đã nhận được kể từ nhịp lấy mẫu trước:

~~~java
Flux<PriceUpdate> sampledPrices =
    marketFeed()
        .sample(Duration.ofMillis(250));
~~~

Với khoảng lấy mẫu 250 ms, một giây có khoảng bốn nhịp lấy mẫu. Nếu trong một khoảng có các giá trị lần lượt là 101, 102, 103, giá trị mới nhất tại nhịp là 103 sẽ được chọn. Hai giá trị trước đó không được chuyển tiếp xuống downstream.

Có thể hình dung luồng hoạt động như sau:

~~~text
Sự kiện từ nguồn:  A  B C     D E F G       H
                    |  | |     | | | |       |
Nhịp lấy mẫu:       ^          ^             ^
Giá trị được phát:  C          G             H
~~~

Sơ đồ minh họa: tại mỗi nhịp, sample lấy giá trị mới nhất đã nhận được trước nhịp đó. Vị trí thực tế của nhịp phụ thuộc scheduler và thời điểm subscription bắt đầu.

### Dùng sampler Publisher

Ngoài Duration, Reactor có thể lấy mẫu theo một Publisher phát tín hiệu nhịp:

~~~java
Flux<MetricSnapshot> snapshots =
    metricEvents()
        .sample(Flux.interval(Duration.ofSeconds(1)));
~~~

Flux.interval phát một tín hiệu mỗi giây. Mỗi tín hiệu sampler yêu cầu sample phát giá trị mới nhất đang chờ từ metricEvents, nếu có. Cách này hữu ích khi nhịp lấy mẫu đến từ một nguồn khác, chẳng hạn lịch điều phối hoặc tín hiệu đồng bộ hóa.

Sampler chỉ xác định thời điểm lấy mẫu. Nó không tạo giá trị dữ liệu thay cho nguồn chính và không làm chậm nguồn chính. Nếu nguồn phát nhanh hơn nhịp lấy mẫu, các giá trị trung gian sẽ bị bỏ theo chủ đích.

### Chọn scheduler cho nhịp lấy mẫu

Với overload nhận Duration, Reactor sử dụng scheduler mặc định dành cho các thao tác thời gian. Khi cần kiểm soát nơi phát nhịp, có thể dùng overload nhận Scheduler:

~~~java
Flux<MetricSnapshot> snapshots =
    metricEvents()
        .sample(
            Duration.ofSeconds(1),
            Schedulers.parallel()
        );
~~~

Chọn scheduler phù hợp với đặc điểm ứng dụng và cách quản lý thời gian. Trong kiểm thử, scheduler ảo của Reactor giúp điều khiển thời gian mà không phải chờ thật. Không nên dùng một scheduler bị chặn bởi công việc đồng bộ kéo dài để phát nhịp lấy mẫu, vì nhịp có thể bị trễ so với dự kiến.

## 3. sampleFirst: giữ phần tử đầu tiên trong mỗi cửa sổ

sample chọn phần tử mới nhất ở mỗi nhịp định kỳ. sampleFirst làm việc theo quy tắc khác: khi cửa sổ đang mở, phần tử đầu tiên đến được phát ngay; sau đó các phần tử tiếp theo bị bỏ cho đến khi cửa sổ thời gian kết thúc.

~~~java
Flux<ClickEvent> acceptedClicks =
    clickEvents()
        .sampleFirst(Duration.ofSeconds(1));
~~~

Đây là hành vi thường được gọi là throttleFirst. Nếu người dùng nhấp liên tục, ứng dụng nhận lần nhấp đầu tiên trong cửa sổ một giây và bỏ các lần tiếp theo trong phần thời gian còn lại của cửa sổ.

Ví dụ:

~~~text
Sự kiện đến:       A B C       D E       F G H
                   | | |       | |       | | |
Cửa sổ:            [----1s----][----1s----][--->
Giá trị được phát: A           D         F
~~~

Trong ví dụ, A mở cửa sổ đầu tiên và được phát ngay. B, C bị bỏ. Khi cửa sổ kế tiếp mở, D là phần tử đầu tiên nên được phát; E bị bỏ. F mở cửa sổ tiếp theo.

sampleFirst phù hợp khi cần giới hạn tần suất nhận một hành động nhưng muốn phản hồi ngay ở lần đầu tiên:

- Chặn các lần nhấn nút liên tục trong một khoảng ngắn.
- Giảm số lần xử lý sự kiện chuột hoặc thao tác UI.
- Chỉ nhận mẫu đầu tiên của một đợt sự kiện dày.
- Giới hạn tần suất gửi yêu cầu khi sự kiện đầu tiên cần được phản hồi ngay.

Không dùng sampleFirst nếu yêu cầu là luôn giữ trạng thái mới nhất. Khi đó sample thường phù hợp hơn.

## 4. sampleTimeout: chỉ phát sau khi luồng tạm yên

sampleTimeout áp dụng một khoảng chờ cho từng phần tử. Khi một phần tử đến, toán tử tạo một Publisher thời gian chờ tương ứng. Nếu phần tử mới đến trước khi Publisher đó phát tín hiệu, phần tử cũ bị loại. Chỉ phần tử không bị thay thế trong suốt khoảng chờ mới được phát.

~~~java
Flux<String> stableQueries =
    queryChanges()
        .sampleTimeout(
            query -> Mono.delay(Duration.ofMillis(300))
        );
~~~

Hành vi này thường được gọi là debounce hoặc throttleWithTimeout. Với ô tìm kiếm, người dùng có thể gõ liên tục: mỗi ký tự mới làm bộ đếm chờ của ký tự trước bị hủy. Khi người dùng ngừng gõ đủ 300 ms, nội dung cuối cùng mới được phát xuống bước gọi dịch vụ tìm kiếm.

~~~text
Thời điểm:     0ms   100ms  180ms            480ms
Giá trị:       "r"   "re"   "rea"             |
Bộ đếm chờ:    bắt đầu hủy   bắt đầu -------- hết hạn
Giá trị phát:                              "rea"
~~~

Trong sơ đồ, giá trị r và re bị thay thế trước khi hết thời gian chờ. rea được phát sau khi không có giá trị mới trong 300 ms.

sampleTimeout khác sample(Duration) ở chỗ khoảng chờ được tính lại theo từng phần tử. sample dùng nhịp định kỳ độc lập với thời điểm từng sự kiện đến; sampleTimeout đợi một khoảng yên lặng sau sự kiện gần nhất.

Có thể dùng một khoảng chờ thay đổi theo phần tử:

~~~java
Flux<SearchResult> stableResults =
    searchRequests()
        .sampleTimeout(request ->
            Mono.delay(
                request.isUrgent()
                    ? Duration.ofMillis(50)
                    : Duration.ofMillis(300)
            )
        )
        .flatMap(searchService::search);
~~~

Ví dụ minh họa cách chọn thời gian chờ dựa trên thuộc tính của từng yêu cầu. Hãy bảo đảm hàm tạo Publisher thời gian chờ không thực hiện I/O chặn và có thể được gọi cho từng phần tử.

## 5. So sánh sample, sampleFirst và sampleTimeout

Ba toán tử đều có thể làm giảm số lượng phần tử phát ra, nhưng thời điểm chọn giá trị khác nhau:

| Toán tử | Quy tắc chọn | Thời điểm phát | Hành vi thường gặp trong thư viện khác |
|---|---|---|---|
| sample(Duration) | Giá trị mới nhất trong khoảng lấy mẫu | Theo nhịp định kỳ | throttleLast hoặc sample |
| sampleFirst(Duration) | Giá trị đầu tiên trong cửa sổ | Ngay khi phần tử đầu tiên đến | throttleFirst |
| sampleTimeout(Function) | Giá trị không bị thay thế trong khoảng chờ | Sau khi luồng yên lặng đủ lâu | debounce hoặc throttleWithTimeout |

Ví dụ với cùng một đợt sự kiện A, B, C đến gần nhau:

- sample có thể phát C ở nhịp lấy mẫu kế tiếp.
- sampleFirst phát A ngay khi cửa sổ mở và bỏ B, C trong cửa sổ đó.
- sampleTimeout phát C sau khi không còn sự kiện mới trong khoảng chờ.

Tên throttle có thể được dùng khác nhau giữa RxJava, Reactor và các thư viện UI. Khi chuyển mã giữa thư viện, hãy so sánh chính sách chọn phần tử và thời điểm phát thay vì đổi tên toán tử một cách máy móc.

## 6. Khoảng thời gian, ranh giới và scheduler

Toán tử thời gian phụ thuộc vào scheduler và thời điểm subscription bắt đầu. Khoảng thời gian 500 ms là thời lượng theo đồng hồ mà scheduler sử dụng, không phải vị trí thời gian được lấy từ timestamp trong payload.

Điều này tạo ra một số hệ quả:

- Hai subscriber đăng ký vào cùng một Flux lạnh ở hai thời điểm khác nhau có thể có nhịp lấy mẫu bắt đầu khác nhau.
- Nếu nguồn phát một sự kiện đúng lúc nhịp lấy mẫu xảy ra, thứ tự xử lý phụ thuộc vào thứ tự tín hiệu được scheduler thực thi.
- Scheduler bận hoặc bị chặn có thể làm tín hiệu thời gian được xử lý trễ.
- Các toán tử thời gian dựa trên processing time; chúng không tự sắp xếp sự kiện theo event timestamp.
- Nếu cần cửa sổ theo thời gian sự kiện, cần xử lý timestamp và watermark ở tầng phù hợp thay vì giả định sample(Duration) tự hiểu thời gian nghiệp vụ.

Với nguồn dữ liệu có timestamp đến trễ hoặc không theo thứ tự, sample(Duration) vẫn chọn theo lúc toán tử nhận phần tử. Ví dụ một sự kiện có timestamp cũ nhưng đến muộn vẫn có thể trở thành giá trị mới nhất được sample tại nhịp kế tiếp.

### Kết hợp với publishOn

Có thể tách bước xử lý phía sau sang scheduler khác:

~~~java
Flux<PriceView> views =
    marketFeed()
        .sample(Duration.ofMillis(250))
        .publishOn(Schedulers.parallel())
        .map(this::toPriceView);
~~~

sample giảm số phần tử được chuyển tiếp theo nhịp lấy mẫu; publishOn chuyển phần xử lý phía sau sang scheduler parallel. Hai toán tử giải quyết hai việc khác nhau: một toán tử chọn dữ liệu theo thời gian, toán tử kia điều phối thực thi. Thêm publishOn có thể tạo hàng đợi và prefetch; hãy cân nhắc bộ nhớ và độ trễ khi ghép nhiều ranh giới bất đồng bộ.

## 7. Lấy mẫu và backpressure

Lấy mẫu không đồng nghĩa với backpressure. Backpressure là cơ chế Subscriber gửi demand bằng request(n) để Publisher tuân theo khả năng tiêu thụ. sample, sampleFirst và sampleTimeout chọn lọc những giá trị được chuyển tiếp theo thời gian.

Nếu nguồn có thể tuân theo demand, các toán tử Reactor phối hợp request theo hợp đồng Reactive Streams và chính sách nội bộ của toán tử. Nhưng việc bỏ bớt giá trị đầu ra không có nghĩa nguồn nóng bên ngoài đã được giảm tốc độ. Một callback hoặc thiết bị vẫn có thể tiếp tục phát dữ liệu theo nhịp riêng.

Cần phân biệt ba nhu cầu:

- **Chỉ cần trạng thái mới nhất:** sample có thể giảm số cập nhật được chuyển tiếp.
- **Chỉ chấp nhận sự kiện đầu tiên trong cửa sổ:** sampleFirst có thể bỏ các sự kiện tiếp theo trong khoảng đó.
- **Chỉ xử lý sau khi sự kiện ngừng đến:** sampleTimeout phù hợp với debounce.
- **Không được mất dữ liệu:** không dùng lấy mẫu để xử lý luồng nghiệp vụ cần đầy đủ; hãy dùng backpressure, queue có giới hạn, hoặc cơ chế lưu trữ và xác nhận ở nguồn.

Các toán tử lấy mẫu không phải là bộ đệm bảo đảm mọi sự kiện sẽ được xử lý sau. Những giá trị bị loại bỏ sẽ không xuất hiện trở lại ở downstream. Nếu mỗi sự kiện có giá trị nghiệp vụ, cần thiết kế cơ chế lưu trữ hoặc xử lý đầy đủ ở trước bước hiển thị/tổng hợp.

## 8. Xử lý hoàn tất, lỗi và hủy

Các toán tử thời gian vẫn tuân theo vòng đời Publisher–Subscriber:

- Nếu nguồn phát lỗi, lỗi được truyền xuống downstream theo pipeline.
- Nếu nguồn hoàn tất, toán tử kết thúc theo quy tắc của nó; không nên mặc định mọi giá trị đang chờ đều được phát nếu chưa kiểm tra chính sách emit cuối của overload đang dùng.
- Khi downstream hủy subscription, toán tử hủy công việc thời gian và subscription upstream mà nó quản lý.
- Nếu sampler Publisher kết thúc hoặc phát lỗi, hành vi kết thúc được truyền theo hợp đồng của toán tử sample đang dùng.

Với sample(Duration), một số overload cho phép chỉ định cách xử lý giá trị cuối khi nguồn hoàn tất. Nếu yêu cầu nghiệp vụ cần phát giá trị cuối cùng ngay cả khi nó chưa rơi vào một nhịp lấy mẫu, hãy kiểm tra overload emitLast trong phiên bản Reactor của dự án và kiểm thử trường hợp hoàn tất. Không nên dựa vào một giả định chung về giá trị cuối khi đổi overload hoặc phiên bản thư viện.

Với sampleTimeout, mỗi sự kiện có thể tạo một Publisher thời gian chờ. Khi sự kiện mới đến, bộ đếm chờ trước đó bị thay thế. Hãy kiểm tra trường hợp nguồn hoàn tất trong lúc còn một bộ đếm chờ nếu nghiệp vụ phụ thuộc vào việc phát giá trị cuối.

## 9. Kiểm thử toán tử theo thời gian

Không nên dùng Thread.sleep trong unit test để đợi khoảng thời gian thật. StepVerifier hỗ trợ virtual time để tiến đồng hồ kiểm thử nhanh và có thể lặp lại.

### Kiểm thử sample với sampler điều khiển được

Có thể dùng TestPublisher làm nguồn dữ liệu và sampler để chủ động phát nhịp:

~~~java
TestPublisher<Integer> source = TestPublisher.create();
TestPublisher<Long> clock = TestPublisher.create();

Flux<Integer> sampled =
    source.flux().sample(clock.flux());

StepVerifier.create(sampled)
    .then(() -> {
        source.next(10, 20);
        clock.next(1L);
    })
    .expectNext(20)
    .then(() -> {
        source.next(30);
        clock.next(2L);
    })
    .expectNext(30)
    .then(source::complete)
    .verifyComplete();
~~~

Hai giá trị 10 và 20 đến trước nhịp đầu tiên, nên sample phát 20. Ở nhịp thứ hai, giá trị mới nhất là 30 nên giá trị này được phát. TestPublisher giúp kiểm thử quy tắc chọn phần tử mà không phụ thuộc đồng hồ thực.

### Kiểm thử sampleFirst

~~~java
StepVerifier.create(
        Flux.range(1, 5)
            .sampleFirst(Duration.ofSeconds(1))
    )
    .expectNext(1)
    .verifyComplete();
~~~

Flux.range phát đồng bộ năm phần tử. Phần tử đầu tiên mở cửa sổ một giây và được phát; các phần tử còn lại đến trong cùng cửa sổ nên bị bỏ. Kiểm thử này xác nhận hành vi chọn phần tử đầu tiên của cửa sổ.

### Kiểm thử sampleTimeout với virtual time

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.just("r", "re", "rea")
            .concatWith(Flux.never())
            .sampleTimeout(value ->
                Mono.delay(Duration.ofSeconds(1))
            )
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext("rea")
    .thenCancel()
    .verify();
~~~

Các giá trị được phát liên tiếp đồng bộ nên bộ đếm chờ của r và re bị thay thế. concatWith(Flux.never()) giữ nguồn mở sau đợt dữ liệu; rea là giá trị cuối cùng còn chờ và được phát sau khi virtual time tiến đủ một giây. StepVerifier sau đó hủy subscription. Kiểm thử không cần đợi một giây ngoài đời thực.

Khi viết kiểm thử thời gian, hãy tạo pipeline bên trong supplier của withVirtualTime để scheduler ảo được cài đặt trước khi toán tử thời gian được khởi tạo. Tránh giữ một Flux đã tạo trước đó nếu nó đã nắm scheduler thật.

## 10. Chọn toán tử theo tình huống

| Tình huống | Lựa chọn | Lý do |
|---|---|---|
| Dashboard cần giá trị mới nhất mỗi 250 ms | sample(250 ms) | Lấy giá trị gần nhất theo nhịp định kỳ |
| Bỏ thao tác lặp, nhưng phản hồi ngay lần đầu | sampleFirst(1 s) | Phát đầu tiên rồi khóa cửa sổ trong một giây |
| Tìm kiếm khi người dùng ngừng gõ 300 ms | sampleTimeout(300 ms) | Chỉ phát giá trị sau khoảng yên lặng |
| Cần xử lý đầy đủ mọi giao dịch | Không dùng lấy mẫu | Mỗi phần tử đều có ý nghĩa nghiệp vụ |
| Cần điều tiết producer theo khả năng consumer | Backpressure/request | Lấy mẫu không yêu cầu nguồn giảm tốc độ |

Trước khi chọn, hãy trả lời:

1. Ứng dụng cần giá trị đầu tiên, giá trị mới nhất hay giá trị cuối cùng sau một khoảng yên lặng?
2. Cửa sổ thời gian bắt đầu theo nhịp cố định hay bắt đầu khi một phần tử đến?
3. Có chấp nhận bỏ các phần tử trung gian không?
4. Thời gian được tính theo lúc nhận sự kiện hay theo timestamp nghiệp vụ?
5. Nếu nguồn hoàn tất trước nhịp kế tiếp, có cần phát giá trị cuối không?
6. Khi downstream hủy, có cần hủy cả nguồn và công việc thời gian không?

## 11. Bài tập vận dụng

Một giao diện giám sát nhận cập nhật giá của một mã cổ phiếu liên tục. Nguồn có thể phát 200 cập nhật mỗi giây. Giao diện chỉ cần hiển thị giá mới nhất bốn lần mỗi giây. Một màn hình khác cần phát hiện cú nhảy giá đầu tiên trong mỗi khoảng hai giây. Một chức năng cảnh báo chỉ gửi thông báo nếu giá không thay đổi thêm trong 500 ms.

Hãy thiết kế ba pipeline:

~~~java
Flux<PriceUpdate> dashboard =
    priceFeed.sample(Duration.ofMillis(250));

Flux<PriceUpdate> firstJumpPerWindow =
    priceFeed.sampleFirst(Duration.ofSeconds(2));

Flux<PriceUpdate> stableAlerts =
    priceFeed.sampleTimeout(update ->
        Mono.delay(Duration.ofMillis(500))
    );
~~~

Sau đó trả lời:

1. Dashboard nhận giá nào nếu có 50 cập nhật trong một khoảng 250 ms?
2. firstJumpPerWindow phản hồi thế nào khi có nhiều cú nhảy liên tiếp trong hai giây?
3. stableAlerts phát giá nào nếu giá tiếp tục thay đổi mỗi 100 ms?
4. Vì sao ba pipeline trên có thể bỏ các giá trị trung gian mà không làm giảm tốc độ phát của nguồn nóng?
5. Nếu mọi cập nhật giá phải được lưu để kiểm toán, nên tách luồng lưu trữ và luồng hiển thị như thế nào?
6. Viết StepVerifier kiểm thử ít nhất một nhịp sample và một trường hợp hủy subscription.

Một thiết kế phù hợp có thể dùng cùng nguồn sự kiện cho nhiều nhánh, nhưng mỗi nhánh phải có chính sách tiêu thụ rõ ràng. Nhánh lưu trữ cần giữ đầy đủ dữ liệu; nhánh hiển thị có thể lấy mẫu để giảm số lần cập nhật; nhánh cảnh báo có thể debounce để tránh phát thông báo liên tục khi giá còn biến động.

## Kết luận

sample phát giá trị mới nhất theo nhịp định kỳ, sampleFirst phát giá trị đầu tiên trong cửa sổ rồi bỏ các giá trị tiếp theo, còn sampleTimeout đợi một khoảng yên lặng trước khi phát giá trị chưa bị thay thế. Các toán tử này hữu ích khi ứng dụng cần giảm số cập nhật và có thể chấp nhận bỏ dữ liệu trung gian. Chúng chọn lọc dữ liệu theo thời gian, còn backpressure điều tiết demand giữa Publisher và Subscriber. Hiểu rõ sự khác nhau đó giúp chọn đúng chính sách cho dashboard, sự kiện UI, telemetry và pipeline xử lý thời gian trong Reactor.
