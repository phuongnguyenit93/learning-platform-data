# Ý nghĩa và thứ tự của onSubscribe, onNext, onError, onComplete

Trong lập trình reactive với Java, dữ liệu được truyền qua một chuỗi tín hiệu bất đồng bộ. Một thành phần phát dữ liệu không chỉ gửi giá trị; nó còn thông báo khi đăng ký bắt đầu, khi có giá trị mới, khi luồng kết thúc bình thường hoặc khi xảy ra lỗi. Reactive Streams chuẩn hóa những tín hiệu này để các thư viện và thành phần có thể phối hợp với nhau.

Hợp đồng tín hiệu là nền tảng của Publisher và Subscriber trong Reactive Streams, cũng là cơ sở mà Reactor sử dụng cho Mono và Flux. Khi nắm được ý nghĩa và thứ tự của onSubscribe, onNext, onError và onComplete, ta có thể đọc đúng vòng đời của một pipeline, điều khiển nhu cầu dữ liệu bằng backpressure và xử lý lỗi mà không phá vỡ hợp đồng.

## 1. Bốn tín hiệu trong một subscription

Một Publisher<T> cung cấp dữ liệu kiểu T. Khi Subscriber<T> đăng ký bằng publisher.subscribe(subscriber), publisher thiết lập một subscription và gửi các tín hiệu đến subscriber.

| Tín hiệu | Ý nghĩa | Vai trò trong vòng đời |
|---|---|---|
| onSubscribe(Subscription) | Thông báo subscription đã được thiết lập và trao quyền điều khiển nhu cầu dữ liệu | Luôn xuất hiện đầu tiên, tối đa một lần |
| onNext(T) | Gửi một phần tử dữ liệu | Có thể xuất hiện không lần nào hoặc nhiều lần |
| onError(Throwable) | Thông báo luồng kết thúc do lỗi | Tín hiệu kết thúc, tối đa một lần |
| onComplete() | Thông báo luồng kết thúc bình thường | Tín hiệu kết thúc, tối đa một lần |

Luồng tín hiệu thông thường có dạng:

    Publisher.subscribe(Subscriber)
        |
        v
    onSubscribe(Subscription)
        |
        v
    +-----------------------------+
    | Subscriber request(n)       |
    +-----------------------------+
        |
        +---- Có dữ liệu ----> onNext(item) ----+
        |                                      |
        +---- Hoàn tất ------> onComplete()     |
        |                                      |
        +---- Gặp lỗi -------> onError(error)   |
                                               |
                                         Kết thúc

Luồng có thể phát nhiều onNext trước khi kết thúc. Một subscription chỉ có một tín hiệu kết thúc: onComplete hoặc onError. Không có chuỗi hợp lệ nào tiếp tục phát dữ liệu sau một trong hai tín hiệu này.

## 2. onSubscribe: bắt tay và nhận quyền điều khiển

onSubscribe(Subscription subscription) là tín hiệu đầu tiên publisher gửi đến subscriber. Đối tượng Subscription là kênh điều khiển của một lần đăng ký cụ thể. Nó cung cấp hai thao tác:

- request(long n): yêu cầu publisher phát tối đa thêm n phần tử.
- cancel(): yêu cầu publisher ngừng phát dữ liệu cho subscription này.

Subscriber thường lưu subscription và yêu cầu dữ liệu ngay trong onSubscribe. Đây là thời điểm thích hợp để thiết lập trạng thái, chuẩn bị tài nguyên hoặc quyết định lượng dữ liệu có thể tiếp nhận.

Ví dụ về trình tự bắt tay:

1. Subscriber gọi publisher.subscribe(subscriber).
2. Publisher tạo hoặc xác định subscription tương ứng.
3. Publisher gọi subscriber.onSubscribe(subscription).
4. Subscriber gọi subscription.request(n) để biểu thị nhu cầu, hoặc cancel() nếu không muốn nhận dữ liệu.
5. Publisher phát các tín hiệu tiếp theo theo hợp đồng.

Publisher phải gọi onSubscribe trước mọi tín hiệu khác và không được gọi nó nhiều lần cho cùng một subscriber trong một lần đăng ký. Subscriber cũng cần xử lý trường hợp publisher hoàn tất hoặc báo lỗi ngay sau bước bắt tay, trước khi có bất kỳ onNext nào.

request(n) không có nghĩa publisher nhất thiết phải phát đủ n phần tử. Nguồn có thể chỉ còn ít phần tử hơn, hoặc kết thúc trước khi đáp ứng hết nhu cầu. request(Long.MAX_VALUE) thường được dùng để biểu thị nhu cầu không giới hạn.

Nếu subscriber gọi request với giá trị không dương, đó là yêu cầu không hợp lệ theo Reactive Streams; publisher phải báo lỗi bằng onError với IllegalArgumentException theo hợp đồng. Trong mã ứng dụng, hãy chỉ yêu cầu số phần tử dương và tránh tính toán khiến số lượng yêu cầu bị tràn hoặc trở thành số âm.

## 3. onNext: nhận từng phần tử dữ liệu

onNext(T item) truyền một phần tử từ publisher xuống subscriber. Một subscription có thể không phát onNext lần nào, phát một lần hoặc phát nhiều lần. Mỗi lần gọi tương ứng với một phần tử được phát trong luồng.

Có hai điều kiện quan trọng:

- Publisher không được phát nhiều phần tử hơn lượng nhu cầu subscriber đã yêu cầu cho subscription đó.
- Các lần gọi onNext phải được tuần tự hóa; publisher không được gọi đồng thời nhiều callback tín hiệu trên cùng subscriber.

Tuần tự hóa không có nghĩa toàn hệ thống chỉ dùng một thread. Publisher có thể thực thi trên nhiều thread nội bộ, nhưng phải bảo đảm các callback của cùng subscriber không chồng lấn và giữ quan hệ thứ tự cần thiết. Subscriber không nên giả định callback luôn chạy trên thread đã gọi subscribe; thread thực thi phụ thuộc publisher, scheduler và cấu hình pipeline.

Giá trị truyền qua onNext không được là null. Nếu một nguồn Java có thể trả về null, cần chuyển đổi hoặc biểu diễn trường hợp không có giá trị theo cách phù hợp trước khi đưa vào Reactive Streams. Với Reactor, Mono.just(null) không hợp lệ; có thể dùng Mono.empty() cho trường hợp không có phần tử hoặc một kiểu dữ liệu biểu diễn rõ trạng thái vắng mặt.

Subscriber nên xử lý mỗi phần tử nhanh và tránh thực hiện thao tác blocking trong callback. Nếu cần chuyển sang scheduler khác, có thể tổ chức việc chuyển luồng trong pipeline Reactor bằng publishOn hoặc dùng cơ chế phù hợp của framework. Việc callback chạy trên thread nào không thay đổi thứ tự tín hiệu mà subscriber phải quan sát.

## 4. onError: kết thúc do lỗi

onError(Throwable error) thông báo publisher không thể tiếp tục luồng theo cách bình thường. Đây là tín hiệu kết thúc, tương đương nhánh kết thúc lỗi của subscription.

Một số đặc điểm cần nhớ:

- onError chỉ xuất hiện sau onSubscribe.
- Có thể có không hoặc nhiều onNext trước onError.
- Sau onError, publisher không được gửi thêm onNext, onComplete hoặc một onError thứ hai trên cùng subscription.
- Lỗi được truyền dưới dạng Throwable, vì vậy subscriber nên ghi nhận nguyên nhân và quyết định cách xử lý phù hợp.

Một publisher có thể thất bại trước khi phát phần tử nào. Khi đó chuỗi tín hiệu là onSubscribe rồi onError. Nếu lỗi xảy ra sau một vài phần tử, các phần tử đã phát vẫn được giữ nguyên trong lịch sử tín hiệu; onError kết thúc phần còn lại của luồng.

Trong Reactor, toán tử như doOnError cho phép quan sát lỗi để ghi log hoặc cập nhật metric, nhưng bản thân nó không biến lỗi thành kết quả thành công. Nếu cần thay thế lỗi bằng một luồng khác, có thể dùng onErrorResume. Khi đó downstream quan sát các phần tử của publisher thay thế và tín hiệu kết thúc của publisher thay thế. Pipeline đã được biến đổi trước khi lỗi được truyền đến subscriber cuối cùng.

Không nên bắt lỗi rồi âm thầm bỏ qua nếu điều đó khiến trạng thái nghiệp vụ trở nên không rõ ràng. Hãy phân biệt lỗi có thể phục hồi, lỗi đầu vào và lỗi hệ thống; chọn retry, fallback hoặc truyền lỗi đến tầng chịu trách nhiệm xử lý.

## 5. onComplete: kết thúc bình thường

onComplete() thông báo publisher đã phát xong dữ liệu và kết thúc bình thường. Đây cũng là tín hiệu kết thúc của subscription.

Một chuỗi hợp lệ có thể có nhiều onNext rồi onComplete, hoặc không có onNext nào và gọi onComplete ngay sau onSubscribe. Trường hợp thứ hai thường gặp ở nguồn rỗng như Mono.empty() hoặc Flux.empty().

Sau onComplete, không còn phần tử nào được phát trên subscription đó. onComplete không mang giá trị kết quả; dữ liệu đã được chuyển qua các lần onNext trước đó. Nếu cần trả một giá trị tổng hợp, hãy dùng toán tử như collectList, reduce hoặc count để tạo kết quả trước khi subscription hoàn tất.

Không phải mọi trường hợp dừng nhận dữ liệu đều tạo ra onComplete. Khi subscriber gọi cancel(), nó yêu cầu dừng subscription; publisher không bắt buộc phải gửi onComplete để xác nhận việc hủy. Vì vậy, không dùng onComplete như tín hiệu duy nhất để giải phóng tài nguyên khi subscription có thể bị hủy. Hãy gắn việc dọn dẹp vào cơ chế lifecycle hoặc cancellation phù hợp.

## 6. Các thứ tự tín hiệu hợp lệ và không hợp lệ

Bảng sau mô tả những chuỗi thường gặp. Dấu ba chấm biểu thị có thể có thêm các lần onNext trước tín hiệu kết thúc.

| Tình huống | Chuỗi tín hiệu | Hợp lệ? |
|---|---|---|
| Luồng có dữ liệu và hoàn tất | onSubscribe → onNext → ... → onComplete | Có |
| Luồng rỗng | onSubscribe → onComplete | Có |
| Lỗi trước phần tử đầu tiên | onSubscribe → onError | Có |
| Lỗi sau một số phần tử | onSubscribe → onNext → ... → onError | Có |
| Phát dữ liệu trước khi bắt tay | onNext → onSubscribe | Không |
| Phát đồng thời hai onNext cho cùng subscriber | Hai callback onNext chồng lấn | Không |
| Gửi cả onComplete và onError | ... → onComplete → onError | Không |
| Phát dữ liệu sau tín hiệu kết thúc | ... → onError → onNext | Không |
| Gọi onSubscribe nhiều lần cho một lần đăng ký | onSubscribe → onSubscribe | Không |

Quy tắc cốt lõi là: một lần bắt tay, không hoặc nhiều phần tử, rồi tối đa một tín hiệu kết thúc. Tín hiệu kết thúc không thể bị đảo ngược hoặc tiếp nối bằng dữ liệu mới trên cùng subscription.

### 6.1. Ví dụ với các nguồn Reactor

Các nguồn Reactor đơn giản cho thấy rõ sự khác nhau giữa luồng có dữ liệu, luồng rỗng và luồng lỗi:

    Mono<String> oneValue = Mono.just("reactive");
    Mono<String> noValue = Mono.empty();
    Mono<String> failed = Mono.error(
        new IllegalStateException("Không thể tải dữ liệu")
    );

    Flux<Integer> severalValues = Flux.just(10, 20, 30);

Vòng đời mà subscriber quan sát được có dạng:

| Nguồn | Chuỗi tín hiệu |
|---|---|
| Mono.just("reactive") | onSubscribe → onNext("reactive") → onComplete |
| Mono.empty() | onSubscribe → onComplete |
| Mono.error(exception) | onSubscribe → onError(exception) |
| Flux.just(10, 20, 30) | onSubscribe → onNext(10) → onNext(20) → onNext(30) → onComplete |

Các toán tử trung gian có thể biến đổi giá trị hoặc chuyển lỗi thành một luồng thay thế, nhưng subscriber cuối cùng vẫn nhận tín hiệu theo cùng hợp đồng.

## 7. Quan hệ giữa tín hiệu và backpressure

onNext không phải một lời gọi tùy ý từ publisher. Số phần tử được phép phát phụ thuộc nhu cầu mà subscriber biểu thị qua Subscription.request(n).

Nhu cầu chưa được đáp ứng được tích lũy trong subscription. Ví dụ, nếu subscriber yêu cầu request(3), publisher có thể phát tối đa ba phần tử theo yêu cầu hiện tại. Nếu subscriber yêu cầu thêm hai phần tử trước khi nguồn kết thúc, tổng nhu cầu chưa được đáp ứng tăng tương ứng. Publisher có thể phát ít hơn số lượng đã yêu cầu nếu nguồn kết thúc sớm.

Một subscriber xử lý từng phần tử có thể yêu cầu phần tử kế tiếp sau khi hoàn tất xử lý phần tử hiện tại. Cách này tạo nhịp tiêu thụ rõ ràng:

    onSubscribe(subscription)
        └── request(1)
              └── onNext(item-1)
                    └── xử lý item-1
                          └── request(1)
                                └── onNext(item-2)
                                      └── ...

Nếu subscriber yêu cầu Long.MAX_VALUE, publisher có thể xem đó là nhu cầu không giới hạn và phát dữ liệu theo khả năng nguồn. Điều này tiện lợi nhưng không tự bảo vệ ứng dụng khỏi một nguồn rất lớn hoặc một consumer xử lý chậm. Với pipeline có tải cao, cần cân nhắc prefetch, giới hạn concurrency và chiến lược buffer/drop phù hợp.

Hủy subscription bằng cancel() yêu cầu publisher cuối cùng ngừng phát tín hiệu đến subscriber. Việc hủy có thể cạnh tranh với một tín hiệu đang được xử lý, nên không nên giả định mọi tác động dừng tức thì tại đúng thời điểm gọi cancel. Publisher cần tôn trọng yêu cầu hủy và subscriber nên thiết kế phần dọn dẹp an toàn khi có tác vụ đang diễn ra.

## 8. Thực hành quan sát tín hiệu trong Reactor

Ví dụ sau dùng BaseSubscriber để yêu cầu từng phần tử một. Subscriber nhận onSubscribe, yêu cầu một phần tử; sau mỗi onNext, nó yêu cầu phần tử tiếp theo. Khi nguồn phát hết dữ liệu, subscriber nhận onComplete.

    import org.reactivestreams.Subscription;
    import reactor.core.publisher.BaseSubscriber;
    import reactor.core.publisher.Flux;

    public class SignalOrderExample {
        public static void main(String[] args) {
            Flux.range(1, 3).subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    System.out.println("onSubscribe");
                    request(1);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("onNext: " + value);
                    request(1);
                }

                @Override
                protected void hookOnError(Throwable error) {
                    System.err.println("onError: " + error.getMessage());
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("onComplete");
                }
            });
        }
    }

Với nguồn Flux.range(1, 3), thứ tự quan sát được là:

    onSubscribe
    onNext: 1
    onNext: 2
    onNext: 3
    onComplete

Mỗi lần request(1) cho phép nguồn phát thêm tối đa một phần tử. Khi phần tử thứ ba được phát, nguồn đã hết dữ liệu nên subscriber nhận onComplete. Ví dụ minh họa cách yêu cầu theo từng phần tử; trong ứng dụng thực tế, cần chọn chiến lược request phù hợp với thông lượng và khả năng xử lý.

Có thể quan sát nhánh lỗi bằng một nguồn khác:

    Flux<String> source = Flux.just("A", "B")
        .concatWith(Flux.error(
            new IllegalStateException("Nguồn dữ liệu gặp lỗi")
        ));

    source.subscribe(
        value -> System.out.println("onNext: " + value),
        error -> System.err.println("onError: " + error.getMessage()),
        () -> System.out.println("onComplete")
    );

Subscriber đơn giản ở đây yêu cầu dữ liệu theo cách mặc định của overload subscribe. Chuỗi tín hiệu downstream quan sát được là hai lần onNext, sau đó onError. Không có onComplete, bởi lỗi đã kết thúc subscription.

## 9. Những lỗi thường gặp khi đọc hoặc triển khai hợp đồng

**Cho rằng mọi nguồn đều phải phát onNext.** Nguồn rỗng là hợp lệ. Mono.empty() phát onSubscribe rồi onComplete, không có giá trị.

**Cho rằng onError chỉ là một callback thông báo rồi luồng tiếp tục.** onError là tín hiệu kết thúc. Muốn khôi phục, hãy chuyển lỗi thành một luồng khác bằng toán tử như onErrorResume trước khi tín hiệu đến subscriber cuối cùng.

**Gọi request mà không hiểu giới hạn nhu cầu.** Yêu cầu Long.MAX_VALUE có thể khiến nguồn phát nhanh nhất có thể. Hãy chọn lượng yêu cầu và mức concurrency dựa trên năng lực xử lý downstream.

**Giả định callback luôn chạy trên một thread cụ thể.** Hợp đồng quy định thứ tự và tính tuần tự của tín hiệu, không bảo đảm một thread cố định cho mọi publisher. Dùng scheduler để kiểm soát nơi thực thi khi cần.

**Dùng onComplete làm dấu hiệu duy nhất cho mọi kiểu kết thúc.** Luồng có thể kết thúc bằng lỗi hoặc bị hủy. Cần phân biệt hoàn tất bình thường, thất bại và cancellation khi quản lý tài nguyên.

**Phát tín hiệu sau khi đã kết thúc.** Một publisher tuân thủ hợp đồng phải dừng việc phát tín hiệu sau onComplete hoặc onError. Nếu tự xây dựng publisher, cần quản lý trạng thái terminal và đồng bộ hóa việc phát tín hiệu để tránh callback chồng lấn hoặc phát thừa.

## 10. Cách kiểm tra một pipeline theo hợp đồng tín hiệu

Khi đọc hoặc thiết kế pipeline, hãy lần theo vòng đời theo thứ tự:

1. Xác định ai gọi subscribe và subscriber nhận subscription nào.
2. Kiểm tra onSubscribe có được gọi trước mọi tín hiệu khác hay không.
3. Xác định nơi gọi request(n), lượng nhu cầu có thể tồn tại và nơi gọi cancel().
4. Theo dõi các phép biến đổi tạo ra, lọc hoặc trì hoãn onNext.
5. Tìm các toán tử có thể phát sinh lỗi và xác định lỗi được truyền tiếp hay được thay bằng luồng dự phòng.
6. Xác nhận mọi đường đi kết thúc bằng đúng một tín hiệu terminal: onComplete hoặc onError, trừ trường hợp subscription bị hủy.

Trong Reactor, StepVerifier là công cụ hữu ích để kiểm tra chuỗi tín hiệu mong đợi mà không phải dựa vào log thủ công. Chẳng hạn, có thể xác nhận nguồn phát ba phần tử rồi hoàn tất:

    import reactor.core.publisher.Flux;
    import reactor.test.StepVerifier;

    StepVerifier.create(Flux.range(1, 3))
        .expectNext(1, 2, 3)
        .verifyComplete();

Với nhánh lỗi, có thể kiểm tra loại lỗi và thông điệp:

    StepVerifier.create(
            Flux.error(new IllegalArgumentException("invalid input"))
        )
        .expectErrorMessage("invalid input")
        .verify();

Các phép kiểm tra này giúp bảo đảm subscriber quan sát đúng dữ liệu và tín hiệu kết thúc. Khi kiểm tra backpressure, có thể tạo verifier với initial request bằng 0, yêu cầu từng phần tử bằng thenRequest(n) và xác nhận publisher chỉ phát theo nhu cầu.

Hợp đồng tín hiệu giúp mọi thành phần trong pipeline thống nhất về lúc bắt đầu, cách truyền dữ liệu và cách kết thúc. Khi kết hợp thứ tự tín hiệu với nhu cầu request(n), cancellation và chính sách lỗi, ta có thể xây dựng pipeline reactive có hành vi dự đoán được ngay cả khi nguồn dữ liệu và quá trình xử lý diễn ra bất đồng bộ.
