# Phân biệt Stream tuần tự, Stream song song và lập trình phản ứng

Khi xử lý dữ liệu trong Java, ba khái niệm **Stream tuần tự** (sequential stream), **Stream song song** (parallel stream) và **lập trình phản ứng** (reactive programming) dễ bị nhầm lẫn vì đều có thể mô tả một chuỗi biến đổi dữ liệu. Tuy nhiên, chúng giải quyết những nhu cầu khác nhau:

- **Stream tuần tự**: mô tả cách xử lý một nguồn dữ liệu qua pipeline, thường thực hiện trên một luồng thực thi.
- **Stream song song**: vẫn sử dụng Java Stream API nhưng cho phép chia công việc giữa nhiều luồng để khai thác nhiều lõi CPU.
- **Lập trình phản ứng**: mô hình xử lý các giá trị/sự kiện xuất hiện theo thời gian, thường dùng trong hệ thống bất đồng bộ; có thể hỗ trợ cơ chế điều tiết tốc độ phát và nhận dữ liệu (*backpressure*).

Bài học thuộc chương **Tổng quan Stream API** của module **JAVA_STREAM_API**. Mục tiêu là nhận biết mô hình thực thi và giới hạn của mỗi cách tiếp cận trước khi sử dụng các thao tác `filter`, `map`, `reduce`, `collect`, collector tùy chỉnh, `Spliterator` hoặc xử lý song song trong Java. Khái niệm *Stream* dưới đây chủ yếu chỉ `java.util.stream.Stream`, không phải `java.io.InputStream`.

## 1. Java Stream API: cùng một pipeline, hai chế độ thực thi

Java Stream API (từ Java 8) cung cấp cách **khai báo phép biến đổi dữ liệu**: nói *cần tính gì* thay vì viết trực tiếp mọi vòng lặp và bộ tích lũy. Một pipeline thường có ba thành phần:

1. **Nguồn**: `List`, mảng, `IntStream.range(...)`, nguồn do `Spliterator` cung cấp, v.v.
2. **Thao tác trung gian**: `filter`, `map`, `distinct`, `sorted`, `limit`, ...; thường *lazy*, chưa duyệt dữ liệu ngay.
3. **Thao tác kết thúc**: `sum`, `count`, `reduce`, `collect`, `forEach`, ...; khởi động việc duyệt và tạo kết quả hoặc hiệu ứng.

```text
Nguồn dữ liệu -> filter -> map -> ... -> thao tác kết thúc
                  |       |
          thao tác trung gian lazy
```

Chế độ **tuần tự/song song** là một thuộc tính của pipeline. Phần lớn thao tác được viết giống nhau; khác biệt chính là cách runtime tổ chức việc duyệt, chia việc và kết hợp kết quả khi thao tác kết thúc chạy.

### Ví dụ 1: Một phép tính, hai chế độ

```java
import java.util.Arrays;
import java.util.List;

public class StreamModes {
    public static void main(String[] args) {
        List<Integer> scores = Arrays.asList(10, -3, 7, 12, 0, 4);

        int sequentialTotal = scores.stream()       // tuần tự
                .filter(score -> score > 0)
                .mapToInt(score -> score * 2)
                .sum();

        int parallelTotal = scores.parallelStream() // song song
                .filter(score -> score > 0)
                .mapToInt(score -> score * 2)
                .sum();

        System.out.println(sequentialTotal); // 66
        System.out.println(parallelTotal);   // 66
    }
}
```

Hai phiên bản có **cùng ý nghĩa nghiệp vụ**: lọc điểm dương, nhân đôi và tính tổng. Phép cộng trong ví dụ thích hợp để kết hợp từng phần, nên hai kết quả bằng nhau. Điều này **không** có nghĩa bản song song luôn nhanh hơn; trên sáu phần tử, chi phí chia việc thường lớn hơn lợi ích.

Có thể chuyển một pipeline giữa hai chế độ bằng `stream.parallel()` và `stream.sequential()`. Với một pipeline, cấu hình tuần tự/song song có hiệu lực khi chạy thao tác kết thúc; không nên hình dung `parallel()` là một thao tác trung gian tự tạo kết quả mới.

## 2. So sánh trực diện

| Khía cạnh | Stream tuần tự | Stream song song | Lập trình phản ứng |
|---|---|---|---|
| API điển hình | `collection.stream()` | `collection.parallelStream()`, `stream.parallel()` | `Flow.Publisher`/`Subscriber` (Java 9+), Reactor `Flux`, RxJava |
| Bài toán phù hợp | Biến đổi, tổng hợp dữ liệu theo pipeline | Tính toán có thể chia nhỏ, độc lập và đủ lớn | Nhận và xử lý dữ liệu/sự kiện đến theo thời gian |
| Tổ chức thực thi | Pipeline được duyệt tuần tự | Công việc có thể chia giữa nhiều worker, rồi kết hợp | Do publisher, subscriber và bộ lập lịch của thư viện/quy trình quyết định |
| Tính bất đồng bộ | Thao tác kết thúc thông thường chạy đồng bộ | Thao tác kết thúc thông thường vẫn đợi kết quả dù có worker song song | Thường có luồng dữ liệu bất đồng bộ; không mặc định mọi pipeline đều chạy khác luồng |
| Dữ liệu đầu vào | Hữu hạn hoặc có thể vô hạn nếu tự tạo nguồn | Tương tự Stream tuần tự | Có thể là dãy hữu hạn hoặc sự kiện kéo dài liên tục |
| Kiểm soát tốc độ | Duyệt theo nhu cầu của thao tác kết thúc, không có giao thức `request(n)` bất đồng bộ | Tương tự; chia việc không phải backpressure | Reactive Streams/`Flow` có `request(n)` để biểu thị nhu cầu nhận |
| Thứ tự | Có thể giữ *encounter order* nếu nguồn có thứ tự | Có thể giữ thứ tự nhưng một số thao tác tốn thêm chi phí; `forEach` không bảo đảm thứ tự | Phụ thuộc hợp đồng publisher, các toán tử và mô hình đồng thời |
| Xử lý lỗi | Exception thường thoát khỏi thao tác kết thúc | Exception có thể xuất hiện khi thực thi phần việc; vẫn phải được xử lý tại lời gọi kết thúc | Thường có tín hiệu lỗi cuối luồng như `onError` |
| Kết thúc | Kết thúc sau terminal operation; Stream không thể dùng lại | Tương tự | Có thể phát `onComplete`, `onError` hoặc bị hủy; một số nguồn chạy lâu dài |

**Điểm phân biệt quan trọng:** `parallelStream()` không biến pipeline thành Reactive Streams. Chạy nhiều luồng để tăng tốc một phép tính và xử lý dòng sự kiện với tín hiệu nhu cầu `request(n)` là hai vấn đề khác nhau.

## 3. Stream tuần tự: ưu tiên cho xử lý dữ liệu thông thường

Ở chế độ tuần tự, các phần tử đi qua pipeline theo cách duyệt tuần tự. Các thao tác trung gian lazy giúp Java có thể xử lý từng phần tử qua nhiều bước mà không buộc phải tạo bộ sưu tập tạm cho mỗi bước.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> names = Arrays.asList("An", "Bình", "Anh", "Chi");

List<String> result = names.stream()
        .filter(name -> name.startsWith("A"))
        .map(String::toUpperCase)
        .collect(Collectors.toList());

System.out.println(result); // [AN, ANH]
```

Việc gọi `filter` hoặc `map` riêng lẻ chưa chạy toàn bộ phép tính; `collect` mới là thao tác kết thúc. Lưu ý `Stream` thường **chỉ tiêu thụ một lần**: muốn tính lại, tạo pipeline mới từ nguồn.

Stream tuần tự thường thích hợp khi dữ liệu vừa hoặc nhỏ, mỗi phần tử xử lý nhanh, yêu cầu dễ đọc/dễ kiểm thử, hoặc thứ tự gặp phần tử có ý nghĩa. Sử dụng tuần tự cũng tránh chi phí điều phối song song không cần thiết.

## 4. Stream song song: tăng thông lượng tính toán khi đủ điều kiện

Khi một Stream được đặt ở chế độ song song, Java có thể dùng cơ chế chia nguồn (gắn với `Spliterator`), cho worker xử lý các phần dữ liệu và gộp kết quả. Các parallel stream thường dùng `ForkJoinPool.commonPool()`, vì vậy công việc chặn luồng hoặc tác vụ khác dùng chung pool có thể ảnh hưởng thông lượng.

```text
                Nguồn dữ liệu lớn
                  /     |     \
              phần A  phần B  phần C
                 \      |      /
                kết hợp kết quả
```

Hiệu quả phụ thuộc vào **khả năng chia nguồn**, **số lượng phần tử**, **chi phí xử lý mỗi phần tử**, **chi phí gộp kết quả** và **phần công việc phải giữ thứ tự/trạng thái**. Mảng và `ArrayList` thường dễ chia hơn nguồn phải duyệt tuần tự hoặc nguồn I/O chậm.

### 4.1. Phép gộp cần phù hợp với xử lý song song

Một phép `reduce` có thể chia việc an toàn khi có giá trị đồng nhất (*identity*) thích hợp và phép kết hợp (*accumulator/combiner*) tuân theo yêu cầu kết hợp nhóm (*associativity*). Phép cộng số nguyên là ví dụ quen thuộc:

```java
int total = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, Integer::sum); // 10
```

**Không dùng phép trừ tùy ý như phép gộp song song:**

```java
int unstable = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, (left, right) -> left - right);
// Không được coi đây là phép reduce song song hợp lệ:
// (a - b) - c khác a - (b - c).
```

Ngoài tính kết hợp nhóm, các hàm trong pipeline nên **không can thiệp vào nguồn** (*non-interfering*) và, trong đa số trường hợp, **không có trạng thái dùng chung** (*stateless*). Không được phụ thuộc vào thứ tự hoàn thành của từng worker.

### 4.2. Tránh sửa bộ sưu tập dùng chung từ `forEach`

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> source = Arrays.asList(1, 2, 3, 4, 5, 6);

// SAI: nhiều worker cùng thay đổi một ArrayList không thread-safe.
List<Integer> unsafe = new ArrayList<>();
source.parallelStream().forEach(unsafe::add);

// ĐÚNG: để collect phối hợp bộ tích lũy và phép kết hợp.
List<Integer> safe = source.parallelStream()
        .filter(number -> number % 2 == 0)
        .collect(Collectors.toList());
```

`Collectors.toList()` không cam kết trả về đúng một kiểu `List` cụ thể; quan trọng là quá trình `collect` được Stream API điều phối theo hợp đồng của collector. Không suy ra rằng có thể chia sẻ và sửa cùng một `ArrayList` từ nhiều worker.

### 4.3. Thứ tự, trạng thái và hiệu năng

```java
List<Integer> values = Arrays.asList(1, 2, 3, 4, 5);

values.parallelStream().forEach(System.out::println);
// Thứ tự in ra có thể khác 1, 2, 3, 4, 5.

values.parallelStream().forEachOrdered(System.out::println);
// Với nguồn List có thứ tự, in theo encounter order.
```

`forEachOrdered` giúp giữ thứ tự quan sát được, nhưng việc áp đặt thứ tự có thể giảm lợi ích song song. Các thao tác có trạng thái như `sorted`, `distinct`, `limit` trên nguồn có thứ tự hoặc việc nhóm dữ liệu cũng có thể tăng chi phí điều phối. `findAny` cho phép tự do chọn một phần tử phù hợp; `findFirst` phải tôn trọng phần tử đầu tiên theo encounter order khi thứ tự tồn tại.

Không nên dùng parallel stream cho lời gọi HTTP, truy vấn cơ sở dữ liệu hoặc I/O chặn luồng theo thói quen: worker của pool có thể phải chờ mạng thay vì làm việc CPU. Tính nhanh/chậm cần đo trên dữ liệu và môi trường thực tế; nếu benchmark Java nghiêm túc, dùng công cụ như JMH, có warm-up và kiểm soát kích thước đầu vào.

## 5. Lập trình phản ứng: xử lý sự kiện theo thời gian

Lập trình phản ứng mô hình hóa những giá trị đến **theo thời gian**: tín hiệu cảm biến, thông báo giao dịch, dữ liệu WebSocket, sự kiện giao diện, phản hồi HTTP bất đồng bộ. Một pipeline phản ứng có thể biến đổi, kết hợp, lọc hoặc gom các sự kiện; đồng thời quan tâm đến thời điểm phát, hủy đăng ký, lỗi và khả năng người nhận xử lý kịp.

Trong Java, `java.util.concurrent.Flow` (Java 9+) định nghĩa các vai trò nền tảng tương thích về ý tưởng với đặc tả Reactive Streams:

- **`Flow.Publisher<T>`**: nguồn cung cấp phần tử.
- **`Flow.Subscriber<T>`**: bên nhận tín hiệu `onSubscribe`, `onNext`, `onError`, `onComplete`.
- **`Flow.Subscription`**: đăng ký mà subscriber dùng để `request(n)` hoặc `cancel()`.
- **`Flow.Processor<T, R>`**: vừa là subscriber ở đầu vào, vừa là publisher ở đầu ra.

```text
Publisher  -- onNext(item) / onError / onComplete --> Subscriber
Publisher  <-- request(n) / cancel() --------------- Subscription (Subscriber giữ)
```

Với `Flow`/Reactive Streams, một subscriber cần báo **nhu cầu nhận** bằng `request(n)` trước khi publisher được phép phát tối đa số phần tử tương ứng theo đăng ký. Cơ chế này gọi là *backpressure*: người nhận biểu thị khả năng tiếp nhận để nguồn có thể điều tiết. Nó không tự động làm mọi nguồn dữ liệu trở nên an toàn vô hạn; chiến lược hàng đợi, bộ đệm, thất thoát dữ liệu hoặc chặn producer vẫn phụ thuộc triển khai.

### Ví dụ 2: Publisher và subscriber có điều tiết nhu cầu

Ví dụ dưới đây chỉ dùng JDK (Java 9+), với `SubmissionPublisher` để phát một dãy sự kiện. Subscriber yêu cầu từng phần tử một.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class FlowExample {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>()) {

            publisher.subscribe(new Flow.Subscriber<Integer>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    s.request(1); // Cho phép gửi 1 phần tử đầu tiên.
                }

                @Override
                public void onNext(Integer item) {
                    System.out.println("Nhận sự kiện: " + item);
                    subscription.request(1); // Xử lý xong mới yêu cầu tiếp.
                }

                @Override
                public void onError(Throwable error) {
                    error.printStackTrace();
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    finished.countDown();
                }
            });

            for (int value = 1; value <= 5; value++) {
                publisher.submit(value);
            }
            // Đóng publisher khi ra khỏi khối try; phát onComplete.
        }

        finished.await(); // Chờ subscriber nhận tín hiệu kết thúc.
    }
}
```

Trong ví dụ này, `submit` đưa dữ liệu vào cơ chế phát bất đồng bộ của `SubmissionPublisher`; `onNext` thường được gọi trên worker riêng của executor. `request(1)` là tín hiệu nhu cầu, **không** đồng nghĩa publisher chỉ có thể lưu đúng một phần tử trong bộ đệm. `SubmissionPublisher.submit` có thể phải chờ khi bộ đệm đầy. Vì vậy, demo thể hiện hợp đồng nhận/phát và hoàn tất, chưa phải giải pháp I/O phi chặn hoặc pipeline sản xuất hoàn chỉnh.

Các thư viện như Project Reactor (ví dụ `Flux`) hoặc RxJava cung cấp nhiều toán tử biến đổi/phối hợp sự kiện hơn giao diện `Flow` có sẵn. Tuy nhiên, chỉ dùng một API phản ứng **không tự động tạo bất đồng bộ**: cách lập lịch, nguồn dữ liệu và toán tử cụ thể mới quyết định luồng nào thực thi.

## 6. Lazy, đa luồng và backpressure là ba thuộc tính khác nhau

Vì tên gọi có chữ “stream”, người học thường gộp ba ý tưởng sau thành một:

**Lazy evaluation** nghĩa là trì hoãn xử lý đến khi có nhu cầu. Với Java Stream, nhiều thao tác trung gian chỉ thực hiện khi có terminal operation. Trong thư viện phản ứng, nhiều publisher chỉ bắt đầu phát khi có đăng ký, nhưng việc này phụ thuộc loại publisher (nguồn *cold* hay *hot*).

**Parallelism** nghĩa là nhiều công việc có thể thực thi đồng thời trên các tài nguyên xử lý khác nhau. `parallelStream()` yêu cầu runtime khai thác khả năng này khi duyệt pipeline; lời gọi terminal operation thông thường vẫn **đồng bộ đối với bên gọi**: phương thức chỉ trả kết quả sau khi tính xong.

**Asynchrony và backpressure** liên quan đến giao tiếp giữa bên phát và bên nhận theo thời gian. Một API phản ứng có thể truyền các tín hiệu mà không buộc bên gọi chờ hoàn tất toàn bộ dãy sự kiện. `request(n)` của `Flow`/Reactive Streams điều tiết số phần tử phát theo từng subscription. Không có giao thức `request(n)` tương đương trong `java.util.stream.Stream`; thao tác duyệt đồng bộ của Stream tự kéo dữ liệu từ nguồn khi cần.

Chẳng hạn, chuyển `orders.stream()` thành `orders.parallelStream()` **không** khiến nó có `subscribe()`, `onNext()` hay `cancel()`. Ngược lại, một `Flux` không gắn scheduler vẫn có thể xử lý toán tử đồng bộ trên luồng gọi `subscribe()`.

## 7. Khi nào chọn cách nào?

| Tình huống | Cách phù hợp | Lý do |
|---|---|---|
| Lọc danh sách sản phẩm, tính tổng hóa đơn, tạo báo cáo nhỏ | Stream tuần tự | Pipeline ngắn gọn, ít chi phí tổ chức thực thi |
| Tính một hàm CPU tốn kém trên hàng triệu phần tử độc lập của mảng | Cân nhắc Stream song song, sau khi đo | Có thể chia nguồn và kết hợp các kết quả |
| Nhận giá cổ phiếu hoặc sự kiện WebSocket liên tục | Reactive programming | Theo dõi sự kiện, hủy đăng ký, điều tiết khi consumer chậm |
| Thực hiện nhiều yêu cầu HTTP chờ mạng | Client bất đồng bộ, `CompletableFuture` hoặc thư viện phản ứng có I/O phù hợp | Chờ I/O là vấn đề khác với chia phép tính CPU trên Stream |
| Tính kết quả yêu cầu cập nhật biến mutable chung hoặc giữ thứ tự nghiêm ngặt ở mọi bước | Thường bắt đầu bằng Stream tuần tự hoặc thiết kế lại phép tổng hợp | Tránh race condition và chi phí điều phối thứ tự |

Quy trình lựa chọn thực tế:

1. **Dữ liệu đã có trong bộ nhớ và cần một kết quả kết thúc?** Bắt đầu bằng Stream tuần tự.
2. **Công việc chủ yếu dùng CPU, các phần tử độc lập, dữ liệu lớn và dễ chia?** Kiểm tra tính đúng của phép gộp, thử `parallel()` rồi đo hiệu năng.
3. **Dữ liệu xuất hiện dần, cần nhận nhiều sự kiện, điều khiển tốc độ hoặc hủy đăng ký?** Xem xét `Flow`/Reactive Streams và thư viện phản ứng phù hợp.
4. **Chỉ cần kết quả bất đồng bộ từ một tác vụ?** `CompletableFuture` có thể đơn giản hơn một pipeline phản ứng nhiều phần tử.

## 8. Những nhầm lẫn cần tránh

| Nhận định dễ nhầm | Cách hiểu chính xác hơn |
|---|---|
| “`parallelStream()` luôn nhanh hơn `stream()`.” | Song song có chi phí chia việc, chuyển giao và gộp kết quả; dữ liệu ít hoặc tác vụ nhẹ thường không có lợi. |
| “Stream tuần tự và song song luôn trả cùng thứ tự.” | Phép tính đúng có thể cho cùng kết quả, nhưng `forEach` song song không bảo đảm thứ tự; `forEachOrdered` có ràng buộc khác. |
| “`reduce` nào cũng có thể chạy song song.” | Phải có identity đúng và phép kết hợp tuân thủ tính kết hợp nhóm; side effect có thể phá tính đúng đắn. |
| “Stream API là Reactive Streams.” | `java.util.stream` xử lý pipeline theo thao tác kết thúc; `Flow`/Reactive Streams mô tả giao thức publisher–subscriber có nhu cầu `request(n)`. |
| “Reactive đồng nghĩa với đa luồng hoặc phi chặn trong mọi trường hợp.” | Phụ thuộc nguồn, executor, scheduler và toán tử; một đoạn xử lý phản ứng vẫn có thể đồng bộ hoặc chặn. |
| “Có backpressure là không bao giờ đầy bộ nhớ.” | Vẫn phải lựa chọn chính sách bộ đệm và cách ứng xử khi producer nhanh hơn consumer. |
| “Đặt side effect trong `map`/`peek` để sửa biến chung là ổn.” | Stream có thể thực thi lazy, khác thứ tự hoặc trên nhiều worker; nên dùng hàm không trạng thái và collector thích hợp. |

## 9. Tự kiểm tra

1. Có 500 bản ghi đang nằm trong `List` và cần lọc theo trạng thái rồi đếm. **Chọn gì?** Bắt đầu bằng Stream tuần tự; không có cơ sở để thêm chi phí song song.
2. Có 10 triệu phần tử mảng, mỗi phần tử cần tính độc lập một hàm toán học nặng, kết quả gộp bằng phép kết hợp hợp lệ. **Chọn gì?** Stream song song là ứng viên đáng thử; đo so với tuần tự và xác nhận kết quả.
3. Một dashboard nhận liên tục dữ liệu cảm biến, có thể cần tạm ngừng hoặc hủy đăng ký nếu người dùng rời màn hình. **Chọn gì?** Mô hình phản ứng phù hợp hơn pipeline Stream dùng một lần; cần kiểm tra khả năng backpressure của toàn bộ hệ thống.

Từ các ví dụ trên, tiêu chí quyết định không phải pipeline có dùng `filter`/`map` hay không, mà là **dữ liệu đến như thế nào, công việc có chia độc lập được không, có cần xử lý bất đồng bộ và điều tiết nhu cầu nhận không**. Nắm được ranh giới này giúp sử dụng đúng Java Stream API và xác định khi nào cần chuyển sang mô hình xử lý sự kiện.
