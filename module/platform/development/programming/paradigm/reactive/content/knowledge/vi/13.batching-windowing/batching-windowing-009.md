# Nguồn vô hạn và các phép tổng hợp không thể kết thúc

Trong ứng dụng reactive, nhiều nguồn dữ liệu không có điểm kết thúc tự nhiên. Một luồng có thể nhận sự kiện từ cảm biến, message broker, WebSocket hoặc bộ đếm thời gian trong suốt vòng đời của ứng dụng. Với những nguồn như vậy, một số phép tổng hợp quen thuộc như đếm toàn bộ phần tử, thu thập thành danh sách hoặc tính kết quả cuối cùng sẽ không thể phát kết quả nếu nguồn không hoàn tất.

Để thiết kế pipeline đúng, cần phân biệt phép tổng hợp chờ kết thúc với phép tổng hợp phát kết quả tăng dần, đồng thời chọn cách chia luồng thành các batch hoặc window có ranh giới hữu hạn. Project Reactor cung cấp các toán tử như reduce, collectList, scan, bufferTimeout và windowTimeout để biểu đạt các chiến lược này.

Bài học thuộc chương **Gom và chia luồng** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; các ví dụ trong bài kết nối cách gom/chia luồng với Mono, Flux, toán tử, scheduler, xử lý lỗi và kiểm thử pipeline Java.

Các đoạn mã sử dụng Project Reactor. Những tên như eventSource, metrics hoặc Order đại diện cho thành phần của ứng dụng; cần bổ sung import và kiểu miền tương ứng khi đưa vào dự án.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một phép tổng hợp chờ tín hiệu hoàn tất sẽ không phát kết quả trên nguồn vô hạn.
- Phân biệt reduce, count, collectList với scan và các phép tổng hợp theo từng cửa sổ.
- Nhận diện nguy cơ giữ bộ nhớ không giới hạn khi thu thập dữ liệu từ luồng dài hạn.
- Chia nguồn vô hạn thành batch hoặc window bằng giới hạn số lượng và thời gian.
- Giới hạn nguồn bằng take hoặc điều kiện dừng khi cần kết quả tổng hợp cuối cùng.
- Kiểm thử nguồn vô hạn, batch theo thời gian và phép tổng hợp tăng dần bằng StepVerifier.

## 1. Nguồn vô hạn có nghĩa gì trong Reactive Streams?

Một Publisher được xem là vô hạn trong ngữ cảnh xử lý khi nó không có tín hiệu onComplete trong thời gian hoạt động mà ứng dụng quan tâm. Nguồn vẫn có thể phát dữ liệu liên tục, phát theo nhịp hoặc thỉnh thoảng mới có sự kiện.

Ví dụ phổ biến:

~~~java
Flux<Long> ticks =
    Flux.interval(Duration.ofSeconds(1));
~~~

Flux.interval tạo một giá trị theo chu kỳ và tiếp tục cho đến khi subscription bị hủy hoặc có lỗi. Một số nguồn thực tế khác:

Flux.interval là nguồn theo đồng hồ: nó không tự dời nhịp phát để chờ consumer. Nếu một tick đến khi subscriber chưa có demand tương ứng, Reactor có thể báo lỗi overflow thay vì tích lũy tick vô hạn. Vì vậy, khi dùng nguồn theo thời gian trong pipeline thật, hãy bảo đảm consumer theo kịp hoặc chọn chính sách buffer/drop phù hợp với nghiệp vụ.

- Consumer nhận thông điệp từ topic có lưu lượng liên tục.
- WebSocket chuyển tiếp dữ liệu trạng thái hoặc sự kiện người dùng.
- Cảm biến phát mẫu trong suốt thời gian thiết bị hoạt động.
- Nguồn cập nhật giá, telemetry hoặc log sự kiện.
- Một luồng theo dõi trạng thái hệ thống chạy suốt vòng đời ứng dụng.

Nguồn vô hạn không nhất thiết phát dữ liệu liên tục từng mili giây. Nó có thể tạm ngừng phát trong một khoảng thời gian rồi tiếp tục. Điểm quan trọng là ứng dụng không thể dựa vào việc nguồn sẽ tự hoàn tất để kết thúc công việc.

Reactive Streams vẫn áp dụng cùng hợp đồng: Publisher phát onNext theo demand, rồi có thể phát onError hoặc onComplete. Với nguồn vô hạn, onComplete có thể không bao giờ xảy ra trong vòng đời subscription. Subscriber vẫn có thể hủy subscription để dừng việc tiêu thụ.

## 2. Vì sao phép tổng hợp chờ hoàn tất không phát kết quả?

Nhiều phép tổng hợp cần biết đã nhận hết dữ liệu trước khi xác định kết quả cuối. Chúng thường giữ trạng thái trong lúc nguồn phát, nhưng chỉ phát kết quả khi nhận onComplete.

### count: đếm toàn bộ phần tử

~~~java
Mono<Long> total =
    eventSource().count();
~~~

count tăng bộ đếm khi nhận từng phần tử. Với nguồn hữu hạn, nó phát tổng số phần tử khi nguồn hoàn tất. Với nguồn vô hạn, bộ đếm vẫn tiếp tục tăng nhưng Mono không phát kết quả vì chưa có onComplete.

Bản thân bộ đếm có kích thước cố định, nên trạng thái tích lũy không nhất thiết tăng theo số phần tử. Tuy nhiên, việc không có kết quả cuối vẫn có thể khiến tầng gọi chờ vô thời hạn nếu nó mong đợi Mono hoàn tất.

### collectList: giữ tất cả phần tử rồi mới phát

~~~java
Mono<List<Event>> allEvents =
    eventSource().collectList();
~~~

collectList giữ các phần tử trong một danh sách và chỉ phát danh sách sau khi nguồn hoàn tất. Nếu nguồn vô hạn, danh sách tiếp tục tăng và Mono không phát kết quả. Đây vừa là vấn đề không kết thúc, vừa là nguy cơ cạn heap.

Tương tự, collectMap, collectMultimap và collectSortedList cũng cần thu thập dữ liệu trước khi tạo kết quả cuối. Nếu số phần tử hoặc số khóa không bị giới hạn, bộ nhớ có thể tăng theo thời gian.

### reduce: giữ accumulator nhưng chờ kết thúc

~~~java
Mono<Long> totalValue =
    eventSource()
        .map(Event::value)
        .reduce(0L, Long::sum);
~~~

reduce cập nhật accumulator khi mỗi phần tử đến. Trong ví dụ, accumulator chỉ là một số long nên trạng thái tích lũy có kích thước cố định. Dù vậy, reduce vẫn chỉ phát tổng cuối cùng khi nguồn hoàn tất.

Điểm cần phân biệt là **bộ nhớ tích lũy** và **thời điểm phát kết quả**. reduce với accumulator nhỏ có thể dùng bộ nhớ ổn định nhưng vẫn không bao giờ phát Mono nếu nguồn không hoàn tất. Nếu accumulator là một List hoặc Map tăng dần, nó còn có nguy cơ tăng bộ nhớ không giới hạn.

### sort và các phép cần nhìn thấy toàn bộ nguồn

~~~java
Flux<Event> sorted =
    eventSource().sort(Comparator.comparing(Event::timestamp));
~~~

Để sắp xếp toàn bộ nguồn, toán tử phải thu thập các phần tử trước khi biết thứ tự cuối cùng. Với nguồn vô hạn, nó không thể phát một dãy đã sắp xếp hoàn chỉnh và có thể giữ lượng dữ liệu ngày càng lớn.

Các phép như last hoặc collectSortedList cũng cần tín hiệu hoàn tất để xác định kết quả cuối. Khi gặp nguồn dài hạn, hãy xem xét liệu yêu cầu có thật sự cần kết quả trên toàn bộ lịch sử hay chỉ cần kết quả trong một khoảng hữu hạn.

## 3. Bảng phân biệt phép tổng hợp theo kiểu terminal và streaming

| Toán tử | Cách hoạt động | Trên nguồn vô hạn |
|---|---|---|
| count | Đếm mọi phần tử, phát một số khi nguồn hoàn tất | Không phát kết quả cuối |
| collectList | Giữ mọi phần tử rồi phát một List | Không phát và bộ nhớ tăng theo dữ liệu |
| collectMap / collectMultimap | Gom dữ liệu vào Map | Không phát; Map có thể tăng không giới hạn |
| reduce | Cập nhật một accumulator, phát kết quả khi hoàn tất | Có thể giữ bộ nhớ cố định nhưng không phát kết quả |
| collectSortedList / sort | Thu thập toàn bộ rồi sắp xếp | Không thể phát kết quả hoàn chỉnh; bộ nhớ tăng |
| last | Chỉ biết phần tử cuối khi nguồn hoàn tất | Không phát phần tử cuối |
| scan | Phát trạng thái tích lũy sau mỗi phần tử | Có thể phát liên tục nếu nguồn và downstream tiếp tục hoạt động |
| bufferTimeout | Phát batch khi đủ số lượng hoặc hết thời gian | Có thể phát batch lặp lại |
| windowTimeout | Phát Publisher con theo ranh giới số lượng hoặc thời gian | Có thể phát window lặp lại |

Các toán tử như count, collectList và reduce thường được gọi là phép tổng hợp terminal vì kết quả của chúng được phát khi nguồn kết thúc. scan và các phép gom theo cửa sổ cho phép ứng dụng quan sát kết quả từng phần trong khi nguồn vẫn hoạt động.

Không nên kết luận rằng mọi toán tử có tên tổng hợp đều không dùng được với nguồn vô hạn. Cần xem toán tử có đòi hỏi onComplete để phát kết quả hay có thể phát từng phần theo ranh giới khác.

## 4. scan: phát kết quả tích lũy sau mỗi phần tử

scan khác reduce ở thời điểm phát kết quả. scan phát trạng thái tích lũy sau mỗi phần tử, nên có thể tạo luồng kết quả liên tục từ nguồn dài hạn:

~~~java
Flux<Long> runningTotals =
    eventSource()
        .map(Event::value)
        .scan(0L, Long::sum)
        .skip(1);
~~~

scan với seed phát giá trị khởi tạo trước, sau đó phát accumulator sau mỗi phần tử. skip(1) loại bỏ seed nếu downstream chỉ cần các tổng sau khi đã nhận dữ liệu.

Ví dụ nguồn phát các giá trị 2, 3, 5:

| Phần tử đến | Tổng tích lũy được phát |
|---:|---:|
| 2 | 2 |
| 3 | 5 |
| 5 | 10 |

Với nguồn vô hạn, scan có thể tiếp tục phát tổng mới sau mỗi phần tử mà không cần chờ nguồn hoàn tất. Tuy nhiên, trạng thái accumulator vẫn phải được thiết kế cẩn thận:

- Accumulator có kích thước cố định như số đếm, tổng hoặc một vài thống kê có giới hạn thường có bộ nhớ ổn định.
- Accumulator chứa toàn bộ lịch sử, chẳng hạn nối thêm mọi phần tử vào List, vẫn tăng bộ nhớ không giới hạn.
- Một giá trị số có kích thước cố định vẫn có thể tràn số sau thời gian dài; cần chọn kiểu số và chính sách overflow phù hợp.
- scan không tự làm chậm nguồn bên ngoài. Demand và tốc độ tiêu thụ vẫn cần được quản lý theo hợp đồng và năng lực hệ thống.

scan phù hợp khi cần cập nhật trạng thái liên tục như tổng doanh số trong phiên, số sự kiện đã nhận hoặc bộ đếm lỗi. Nếu cần thống kê trên từng phút hoặc từng nhóm sự kiện, windowing thường giúp giới hạn phạm vi accumulator rõ ràng hơn.

## 5. Giới hạn nguồn trước khi dùng phép tổng hợp terminal

Nếu nghiệp vụ thực sự cần một kết quả cuối, hãy tạo ranh giới hữu hạn trước phép tổng hợp. Có thể giới hạn theo số lượng, thời gian hoặc điều kiện nghiệp vụ.

### take(n): tổng hợp một số phần tử đầu

~~~java
Mono<List<Long>> firstHundred =
    Flux.interval(Duration.ofMillis(100))
        .take(100)
        .collectList();
~~~

take(100) cho phép tối đa một trăm phần tử đi qua rồi hủy subscription upstream và hoàn tất downstream. collectList vì thế có thể phát danh sách hữu hạn.

### take(Duration): tổng hợp trong một khoảng thời gian

~~~java
Mono<Long> countForFiveSeconds =
    Flux.interval(Duration.ofMillis(100))
        .take(Duration.ofSeconds(5))
        .count();
~~~

Sau khoảng thời gian được giới hạn, take kết thúc luồng và count phát số phần tử đã nhận. Đây là một cửa sổ tổng hợp hữu hạn tính từ lúc subscription bắt đầu, không phải phép đếm toàn bộ vòng đời của nguồn.

### takeUntil(predicate): kết thúc tại sự kiện ranh giới

~~~java
Mono<List<SessionEvent>> session =
    eventSource()
        .takeUntil(event -> event.type() == EventType.SESSION_CLOSED)
        .collectList();
~~~

Khi gặp sự kiện SESSION_CLOSED, takeUntil phát cả phần tử ranh giới rồi hoàn tất. collectList có thể phát toàn bộ sự kiện trong phiên sau khi ranh giới xuất hiện.

Cách này chỉ kết thúc nếu sự kiện ranh giới thực sự đến hoặc nguồn tự hoàn tất. Nếu không có ranh giới, phép tổng hợp vẫn chờ. Trong hệ thống thực tế, cần có timeout hoặc chính sách hủy để xử lý phiên bị bỏ dở.

Giới hạn nguồn không chỉ là thủ thuật kỹ thuật. Nó cần phản ánh phạm vi nghiệp vụ: một trang kết quả, một phiên giao dịch, một khoảng quan sát hay một đợt xử lý.

## 6. bufferTimeout: chia nguồn vô hạn thành batch hữu hạn

Khi cần xử lý dữ liệu theo nhóm, bufferTimeout(maxSize, maxTime) tạo một List mới và phát batch khi đạt số lượng tối đa hoặc khi hết thời gian chờ.

~~~java
Flux<List<Long>> batches =
    Flux.interval(Duration.ofMillis(100))
        .bufferTimeout(10, Duration.ofSeconds(1));
~~~

Trong ví dụ, batch được phát khi đủ mười phần tử hoặc khi cửa sổ một giây kết thúc. Vì nguồn tiếp tục chạy, toán tử có thể phát nhiều batch trong suốt vòng đời subscription.

Hai điều kiện đóng batch có ý nghĩa khác nhau:

- **maxSize:** tránh một batch chứa quá nhiều phần tử khi nguồn phát nhanh.
- **maxTime:** tránh giữ batch quá lâu khi nguồn phát chậm hoặc thưa.

Nếu nguồn hoàn tất trước khi batch đầy, batch cuối chưa đủ phần tử có thể được phát khi kết thúc. Với nguồn vô hạn không hoàn tất, batch vẫn được phát theo điều kiện số lượng hoặc thời gian.

### Chọn kích thước batch

Batch lớn có thể giảm chi phí gọi dịch vụ hoặc ghi cơ sở dữ liệu nhiều lần, nhưng làm tăng độ trễ chờ đủ phần tử và lượng bộ nhớ giữ trong mỗi batch. Batch nhỏ phản hồi nhanh hơn nhưng có thể làm tăng overhead.

Có thể ước lượng payload của một batch:

\[
\text{Payload batch} \approx
\text{số phần tử tối đa} \times
\text{kích thước trung bình mỗi phần tử}
\]

Ví dụ, nếu batch có tối đa 100 sự kiện và mỗi sự kiện chiếm khoảng 2 KB, payload của batch vào khoảng 200 KB, chưa tính chi phí object và cấu trúc List. Khi có nhiều subscription hoặc nhiều batch đang chờ xử lý, hãy tính tổng lượng bộ nhớ có thể được giữ đồng thời.

### Xử lý từng batch

~~~java
Flux<WriteResult> writes =
    Flux.interval(Duration.ofMillis(20))
        .bufferTimeout(50, Duration.ofMillis(500))
        .concatMap(batch -> repository.saveAll(batch));
~~~

Ví dụ gom tối đa 50 sự kiện hoặc chờ tối đa 500 ms rồi gọi lưu theo batch. concatMap xử lý từng batch theo thứ tự, chỉ đăng ký xử lý batch tiếp theo sau khi Publisher của batch trước hoàn tất. Nếu dùng flatMap để xử lý nhiều batch song song, cần giới hạn concurrency và cân nhắc số batch đang chờ.

bufferTimeout tạo danh sách trong bộ nhớ. Nếu repository chậm hơn tốc độ tạo batch, các batch có thể chờ phía downstream. Cần quan sát demand, hàng đợi, độ trễ và giới hạn concurrency; việc chia batch không tự giải quyết mất cân bằng tốc độ.

maxSize giới hạn số phần tử trong từng List, không phải giới hạn tổng số batch đang chờ ở mọi tầng của pipeline. Nếu downstream liên tục chậm hơn upstream, vẫn cần giới hạn concurrency, prefetch và lượng công việc được xếp hàng.

## 7. windowTimeout: chia luồng thành các Publisher con

bufferTimeout phát từng List. windowTimeout phát các Publisher con, mỗi Publisher đại diện cho một phần của luồng. Ranh giới được đóng khi đạt số lượng hoặc thời gian tối đa:

~~~java
Flux<Flux<Long>> windows =
    Flux.interval(Duration.ofMillis(100))
        .windowTimeout(10, Duration.ofSeconds(1));
~~~

Mỗi inner Flux có vòng đời riêng. Khi window đóng, inner Publisher hoàn tất; outer Flux tiếp tục phát window tiếp theo nếu nguồn vẫn chạy.

Có thể tổng hợp riêng từng window:

~~~java
Flux<Long> sumsPerWindow =
    Flux.interval(Duration.ofMillis(100))
        .windowTimeout(10, Duration.ofSeconds(1))
        .concatMap(window ->
            window.reduce(0L, Long::sum)
        );
~~~

reduce trong mỗi window chỉ cần chờ inner Publisher hữu hạn hoàn tất. Vì window được đóng theo số lượng hoặc thời gian, mỗi phép reduce có thể phát một tổng riêng trong khi outer source vẫn vô hạn.

Điều này khác với reduce trên toàn bộ nguồn: phép reduce toàn cục chờ nguồn vô hạn hoàn tất, còn reduce bên trong từng window chỉ chờ một phần hữu hạn của nguồn.

### buffer hay window?

| Tiêu chí | bufferTimeout | windowTimeout |
|---|---|---|
| Giá trị đầu ra | List<T> | Flux<T> |
| Cách tiêu thụ | Nhận cả batch đã gom | Đăng ký và xử lý inner Flux |
| Bộ nhớ | Giữ phần tử trong List cho đến lúc phát | Chuyển phần tử qua inner Publisher; vẫn có thể có queue khi consumer chậm |
| Phù hợp | Gọi API batch, ghi nhiều bản ghi cùng lúc | Xây pipeline reactive riêng cho từng nhóm |
| Xử lý song song | Kết hợp flatMap trên List | Kết hợp flatMap/concatMap trên inner Flux |

Chọn buffer khi bước tiếp theo cần một collection hoàn chỉnh. Chọn window khi muốn giữ cách xử lý reactive cho từng nhóm, chẳng hạn lọc, biến đổi hoặc tổng hợp ngay trong từng cửa sổ.

Không nên tạo window rồi bỏ mặc inner Flux. Hãy tiêu thụ hoặc hủy các inner Publisher theo chính sách rõ ràng; nếu không, việc quản lý demand và hàng đợi ở các window có thể trở nên khó kiểm soát.

## 8. Cửa sổ theo số lượng và theo thời gian

Có hai cách phổ biến để xác định ranh giới:

- **Theo số lượng:** đóng batch/window khi nhận đủ n phần tử.
- **Theo thời gian:** đóng batch/window sau một khoảng thời gian nhất định.
- **Kết hợp:** đóng khi một trong hai giới hạn đạt trước.

Nếu chỉ dùng buffer(n) trên nguồn vô hạn, batch chỉ phát khi đủ n phần tử. Khi nguồn chậm hoặc ngừng phát tạm thời, batch chưa đầy có thể nằm chờ lâu. Nếu dùng bufferTimeout, giới hạn thời gian giúp phát batch chưa đầy để giảm độ trễ.

Nếu chỉ dùng window(n), inner Flux đóng khi đủ số phần tử. Với nguồn thưa, inner window có thể tồn tại lâu. windowTimeout đặt thêm giới hạn thời gian để mỗi window có ranh giới hữu hạn theo chính sách thời gian.

Ví dụ so sánh:

~~~java
Flux<List<Event>> byCount =
    eventSource().buffer(100);

Flux<List<Event>> byCountOrTime =
    eventSource().bufferTimeout(100, Duration.ofSeconds(2));
~~~

byCount phù hợp khi ưu tiên batch đủ kích thước và nguồn luôn có lưu lượng ổn định. byCountOrTime phù hợp khi cần giới hạn thời gian chờ ngay cả khi lưu lượng thấp.

Ranh giới thời gian dựa trên scheduler và thời điểm subscription. Nếu cần nhóm theo timestamp nghiệp vụ, chẳng hạn phút được xác định theo đồng hồ UTC hoặc múi giờ của thị trường, hãy cân nhắc xử lý timestamp và ranh giới lịch ở tầng phù hợp thay vì giả định mọi window thời gian tương đối đều khớp với phút trên đồng hồ.

## 9. Các phép kiểm tra có thể kết thúc sớm

Không phải mọi phép tổng hợp đều bắt buộc đợi nguồn hoàn tất. Một số phép có thể dừng ngay khi đã tìm thấy kết quả quyết định:

- any(predicate) có thể phát true và kết thúc khi tìm thấy phần tử đầu tiên thỏa điều kiện.
- all(predicate) có thể phát false và kết thúc khi tìm thấy phần tử đầu tiên không thỏa điều kiện.
- hasElements có thể phát true ngay khi nhận phần tử đầu tiên.
- next có thể lấy phần tử đầu tiên rồi hủy upstream.

Ví dụ:

~~~java
Mono<Boolean> hasCriticalEvent =
    eventSource()
        .any(event -> event.severity() == Severity.CRITICAL);
~~~

Nếu một sự kiện nghiêm trọng xuất hiện, any có thể phát true và kết thúc mà không cần đợi nguồn vô hạn hoàn tất. Nếu không bao giờ có sự kiện thỏa điều kiện, Mono không thể phát false vì chưa biết liệu một sự kiện phù hợp có xuất hiện về sau hay không.

Tương tự, all trên nguồn vô hạn chỉ kết thúc sớm khi tìm thấy phần tử vi phạm điều kiện. Nếu mọi phần tử đã thấy đều thỏa điều kiện nhưng nguồn không hoàn tất, all vẫn không phát true.

Có thể kiểm thử trường hợp any tìm thấy phần tử phù hợp trên một nguồn không hoàn tất:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .any(value -> value == 2L)
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(true)
    .verifyComplete();
~~~

Nguồn phát 0, 1 rồi 2 theo từng giây. Khi nhận 2, any phát true và kết thúc subscription mà không cần chờ Flux.interval hoàn tất.

Điểm này rất quan trọng khi thiết kế cảnh báo và giám sát: một điều kiện phủ định có thể được xác nhận bằng một phản ví dụ, còn khẳng định rằng mọi phần tử trong toàn bộ nguồn vô hạn đều thỏa điều kiện là điều không thể kết luận trong thời gian hữu hạn.

## 10. groupBy và nguy cơ số nhóm tăng không giới hạn

groupBy tạo một Flux con cho mỗi khóa mới xuất hiện:

~~~java
Flux<GroupedFlux<String, Event>> byDevice =
    eventSource()
        .groupBy(Event::deviceId);
~~~

Nếu nguồn chỉ có một số lượng thiết bị hữu hạn và ổn định, groupBy có thể giúp xử lý riêng dữ liệu theo từng thiết bị. Nhưng nếu khóa có cardinality không giới hạn, chẳng hạn mỗi sự kiện mang một ID duy nhất, số nhóm có thể tiếp tục tăng.

Mỗi nhóm cũng cần được tiêu thụ. Nếu outer Flux phát các GroupedFlux nhưng downstream không đăng ký và đọc chúng phù hợp, dữ liệu có thể bị giữ lại và tạo áp lực lên queue. Với nguồn vô hạn, cần kiểm soát số khóa, vòng đời nhóm và cách tiêu thụ inner Flux.

Nếu chỉ cần thống kê theo từng khoảng thời gian, windowTimeout có thể phù hợp hơn groupBy theo khóa không giới hạn. Nếu cần nhóm theo khóa nghiệp vụ, hãy có chính sách giới hạn hoặc hết hạn cho khóa và theo dõi số nhóm đang hoạt động.

## 11. Backpressure và giới hạn công việc đang chờ

Batching và windowing tạo ranh giới hữu ích, nhưng không tự động bảo đảm bộ nhớ luôn ổn định. Một pipeline có thể tạo batch nhanh hơn tốc độ lưu trữ hoặc tạo window nhanh hơn tốc độ xử lý inner Publisher.

Hãy phối hợp các cơ chế:

- Dùng request/backpressure để điều tiết nguồn hỗ trợ Reactive Streams.
- Giới hạn kích thước batch bằng maxSize.
- Giới hạn thời gian chờ bằng maxTime.
- Giới hạn số batch hoặc window được xử lý đồng thời.
- Chọn concatMap nếu cần xử lý tuần tự; chọn flatMap với concurrency hữu hạn khi có thể xử lý song song.
- Đặt chính sách timeout, retry và xử lý lỗi cho từng batch.
- Theo dõi độ sâu queue, thời gian xử lý batch, số window đang hoạt động và bộ nhớ heap.

Ví dụ giới hạn số batch được xử lý đồng thời:

~~~java
Flux<WriteResult> results =
    eventSource()
        .bufferTimeout(100, Duration.ofSeconds(1))
        .flatMap(batch -> repository.saveAll(batch), 4);
~~~

flatMap ở đây cho phép tối đa bốn Publisher lưu batch hoạt động đồng thời. Con số bốn chỉ là ví dụ; giá trị thực tế cần dựa trên connection pool, giới hạn dịch vụ và thời gian xử lý. Tăng concurrency quá cao có thể làm quá tải hệ thống phụ thuộc và tăng số batch đang chờ.

Nếu mỗi batch có thể thất bại độc lập, cần xác định chính sách lỗi: một batch lỗi có làm dừng toàn bộ pipeline hay được ghi nhận và chuyển sang xử lý khác. Không nên nuốt lỗi chỉ để luồng tiếp tục vì có thể làm mất dữ liệu mà không có dấu hiệu vận hành.

## 12. Kiểm thử nguồn vô hạn và window hữu hạn

StepVerifier hỗ trợ virtual time để kiểm thử nguồn thời gian mà không cần chờ đồng hồ thật.

### Kiểm thử phép tổng hợp toàn nguồn không phát kết quả

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .count()
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectNoEvent(Duration.ofSeconds(1))
    .thenCancel()
    .verify();
~~~

Nguồn interval vẫn phát trong suốt thời gian kiểm thử. count chưa nhận onComplete nên không phát kết quả. StepVerifier xác nhận không có tín hiệu trong khoảng quan sát rồi hủy subscription.

### Giới hạn nguồn rồi mới count

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMillis(100))
            .take(5)
            .count()
    )
    .expectSubscription()
    .thenAwait(Duration.ofMillis(500))
    .expectNext(5L)
    .verifyComplete();
~~~

take(5) làm nguồn trở nên hữu hạn đối với pipeline này. Khi năm phần tử đã được phát, count nhận hoàn tất và phát 5L.

### Kiểm thử batch theo số lượng và thời gian

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMillis(100))
            .take(5)
            .bufferTimeout(3, Duration.ofSeconds(1))
    )
    .expectSubscription()
    .thenAwait(Duration.ofMillis(500))
    .expectNext(List.of(0L, 1L, 2L))
    .expectNext(List.of(3L, 4L))
    .verifyComplete();
~~~

Batch đầu phát khi đủ ba phần tử. Batch thứ hai chỉ có hai phần tử và được phát khi nguồn hữu hạn hoàn tất. Ví dụ này kiểm tra cả batch đủ kích thước lẫn batch cuối chưa đầy.

### Kiểm thử tổng hợp riêng từng window

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMillis(100))
            .take(5)
            .windowTimeout(3, Duration.ofSeconds(1))
            .concatMap(window -> window.collectList())
    )
    .expectSubscription()
    .thenAwait(Duration.ofMillis(500))
    .expectNext(List.of(0L, 1L, 2L))
    .expectNext(List.of(3L, 4L))
    .verifyComplete();
~~~

Mỗi window được thu thập riêng sau khi đóng. Window đầu đóng khi đủ ba phần tử; window thứ hai chứa hai phần tử còn lại và hoàn tất khi nguồn bị take(5) kết thúc.

### Kiểm thử scan phát tổng tăng dần

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .scan(0L, Long::sum)
            .skip(1)
            .take(3)
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 3L)
    .verifyComplete();
~~~

scan phát tổng sau từng phần tử. take(3) giới hạn số kết quả để kiểm thử kết thúc trong thời gian hữu hạn.

Khi dùng virtual time, hãy tạo pipeline bên trong supplier của withVirtualTime để scheduler ảo được cài đặt trước khi các toán tử thời gian khởi tạo timer. Không dùng Thread.sleep để đồng bộ kiểm thử vì cách đó làm test chậm và dễ dao động theo tải máy.

## 13. Quy trình thiết kế phép tổng hợp cho nguồn dài hạn

Khi nhận một yêu cầu tổng hợp, hãy trả lời lần lượt:

1. **Nguồn có kết thúc không?** Xác định Publisher hữu hạn, vô hạn hay chỉ kết thúc khi kết nối bị đóng.
2. **Kết quả cần khi nào?** Cần một kết quả cuối, trạng thái cập nhật liên tục hay kết quả theo từng batch/window?
3. **Accumulator có tăng theo dữ liệu không?** Đếm hoặc tổng có thể dùng trạng thái cố định; danh sách và map có thể tăng không giới hạn.
4. **Ranh giới nhóm là gì?** Chọn số lượng, thời gian, sự kiện nghiệp vụ hoặc kết hợp các điều kiện.
5. **Consumer xử lý nhanh đến đâu?** Giới hạn concurrency và lượng batch/window đang chờ.
6. **Nếu không có ranh giới thì sao?** Đặt timeout, cancellation hoặc chính sách vận hành cho phiên kéo dài.
7. **Lỗi ở một nhóm ảnh hưởng thế nào?** Quyết định retry, bỏ qua có ghi nhận, lưu vào dead-letter hoặc kết thúc pipeline.

Một thiết kế tốt phải làm rõ lúc nào một kết quả được phát, bao nhiêu dữ liệu có thể được giữ trong bộ nhớ và điều gì xảy ra nếu nguồn không bao giờ hoàn tất.

## 14. Bài tập vận dụng

Một dịch vụ theo dõi giao dịch nhận sự kiện liên tục từ message broker. Mỗi giao dịch có số tiền, mã tài khoản và timestamp. Dashboard cần hiển thị tổng số tiền trong từng khoảng một phút; dịch vụ lưu trữ cần ghi mọi giao dịch theo batch tối đa 200 phần tử hoặc chờ tối đa hai giây; một cảnh báo cần phát ngay khi xuất hiện giao dịch vượt ngưỡng.

Hãy thiết kế ba nhánh xử lý:

- Nhánh dashboard dùng window theo thời gian và reduce để tính tổng từng phút.
- Nhánh lưu trữ dùng bufferTimeout và giới hạn concurrency khi ghi batch.
- Nhánh cảnh báo dùng any hoặc filter kết hợp để phản ứng ngay khi gặp giao dịch vượt ngưỡng.

Sau đó trả lời:

1. Vì sao reduce trên toàn bộ nguồn giao dịch không phát tổng cuối nếu broker không gửi tín hiệu hoàn tất?
2. Vì sao reduce bên trong từng window một phút có thể phát kết quả dù nguồn bên ngoài vẫn tiếp tục?
3. Nếu dùng collectList trên toàn bộ nguồn, bộ nhớ thay đổi ra sao theo thời gian?
4. Khi lưu batch chậm hơn tốc độ đến, những giới hạn nào cần được áp dụng?
5. Nếu một phút không có giao dịch, dashboard cần biểu diễn khoảng đó như thế nào?
6. Nếu cảnh báo đã tìm thấy giao dịch vượt ngưỡng, vì sao nhánh cảnh báo có thể kết thúc sớm mà nhánh lưu trữ vẫn tiếp tục?

Hãy viết kiểm thử StepVerifier cho ít nhất một window, một batch chưa đầy được phát khi nguồn hoàn tất và một điều kiện cảnh báo được thỏa trước khi nguồn vô hạn kết thúc.

## Kết luận

Các phép tổng hợp như count, collectList và reduce thường cần onComplete để phát kết quả cuối, nên không thể hoàn tất trên nguồn vô hạn nếu không có ranh giới dừng. scan phát trạng thái tích lũy theo từng phần tử, còn bufferTimeout và windowTimeout chia luồng thành các nhóm hữu hạn để tổng hợp riêng. Khi thiết kế pipeline dài hạn, hãy kiểm soát kích thước accumulator, batch, window và concurrency; giới hạn nguồn khi cần kết quả cuối, đồng thời kiểm thử cả demand, cancellation và hành vi khi nguồn không bao giờ hoàn tất.
