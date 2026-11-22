# Flux biểu diễn chuỗi từ không đến nhiều phần tử (0..N) trong Spring Reactive

## 1. Hiểu đúng bản chất của `Flux<T>`

Trong **Project Reactor**, thư viện reactive được dùng phổ biến bởi **Spring WebFlux**, `Flux<T>` là một kiểu `Publisher<T>` đại diện cho **một luồng tín hiệu có thể phát ra từ 0 đến nhiều phần tử kiểu `T`** theo thời gian. Mỗi phần tử được gửi cho bên nhận (`Subscriber`) bằng tín hiệu `onNext(T)`. Luồng hữu hạn thông thường kết thúc bằng `onComplete()`; khi thất bại, nó kết thúc bằng `onError(Throwable)`.

Chữ **0..N** mô tả **số phần tử được phát ra trong một lần đăng ký (subscription)**, không phải số phần tử đã tồn tại sẵn trong bộ nhớ. `N` không có giới hạn cố định: một `Flux` có thể phát 2, 100, một triệu phần tử, hoặc phát liên tục trong thời gian rất dài. Không phải mọi `Flux` đều kết thúc; một luồng sự kiện trực tiếp có thể tiếp tục đến khi người nhận hủy.

Các trường hợp cơ bản:

| Trường hợp | Ví dụ | Chuỗi tín hiệu |
| --- | --- | --- |
| **0 phần tử, hoàn tất thành công** | `Flux.empty()` | `onSubscribe → onComplete` |
| **1 phần tử, hoàn tất thành công** | `Flux.just("A")` | `onSubscribe → onNext("A") → onComplete` |
| **N phần tử, hoàn tất thành công** | `Flux.just("A", "B", "C")` | `onSubscribe → onNext("A") → onNext("B") → onNext("C") → onComplete` |
| **Thất bại** | `Flux.error(ex)` hoặc gặp lỗi giữa chừng | `onSubscribe → onNext(...)* → onError(ex)` |
| **Luồng liên tục** | `Flux.interval(...)` không giới hạn | `onSubscribe → onNext(...)* → …`, có thể chưa có tín hiệu kết thúc |

Dấu `*` ở bảng nghĩa là 0 hoặc nhiều lần. Một subscription tuân theo quy tắc: chỉ có **một trong hai tín hiệu kết thúc** `onComplete` hoặc `onError`, không có `onNext` sau tín hiệu kết thúc. Có thể hủy subscription bằng `cancel`. `Flux.never()` là trường hợp đặc biệt: sau khi đăng ký nó không phát phần tử, không hoàn tất và không báo lỗi.

**Điểm quan trọng:** `Flux` mô tả cách cung cấp và xử lý chuỗi dữ liệu; nó **không phải** `List<T>`, mảng hoặc một tập hợp đã tải đủ. Khả năng biểu diễn nhiều phần tử không đồng nghĩa rằng tất cả phần tử luôn được lưu trong RAM.

## 2. Phân biệt Flux và Mono

Cả `Flux<T>` và `Mono<T>` đều là `Publisher` trong Reactor, nhưng có hợp đồng số lượng phần tử khác nhau.

| Thuộc tính | `Mono<T>` | `Flux<T>` |
| --- | --- | --- |
| Số phần tử `onNext` cho mỗi subscription | **0 hoặc 1** | **0 đến N** |
| Ví dụ nguồn | `Mono.just(user)`, `Mono.empty()` | `Flux.just(a, b)`, `Flux.range(1, 10)` |
| Trường hợp thường dùng | Tìm một bản ghi, một kết quả HTTP, thao tác chỉ cần báo hoàn tất | Danh sách bản ghi, nhiều sự kiện, stream dữ liệu hoặc cập nhật liên tục |
| Kết thúc | Hoàn tất hoặc lỗi; cũng có thể không phát tín hiệu kết thúc | Hoàn tất hoặc lỗi; cũng có thể không phát tín hiệu kết thúc |
| Một số toán tử đổi kiểu | `Mono<T>.flux()` tạo `Flux<T>` | `Flux<T>.next()` trả `Mono<T>`; `collectList()` trả `Mono<List<T>>` |

Ví dụ tìm **một** người dùng theo ID thường phù hợp `Mono<User>`; lấy **nhiều** người dùng theo tiêu chí thường phù hợp `Flux<User>`. Một `Flux` phát ra đúng một phần tử vẫn hợp lệ, nhưng nếu API cam kết chỉ có tối đa một kết quả thì `Mono` thể hiện hợp đồng rõ ràng hơn.

Một `Flux` có thể rỗng ngay cả khi kiểu trả về là `Flux<User>`: **không có kết quả** không nhất thiết là lỗi. Ngược lại, một `onError` là tín hiệu thất bại, không phải một phần tử dữ liệu bình thường. Nếu một phép biến đổi tạo nhiều phần tử trong phản hồi thì dùng `Flux`; nếu gom hết chúng thành một danh sách, kết quả trở thành **một** `Mono<List<T>>`, tuy danh sách đó có thể chứa nhiều phần tử.

## 3. Cơ chế phát dữ liệu theo tín hiệu và nhu cầu

Một pipeline Reactor thường có ba vai trò:

1. **Nguồn (`Publisher`)**: tạo hoặc cung cấp phần tử, như `Flux.range`, driver database reactive, hay một stream sự kiện.
2. **Toán tử (`Operator`)**: khai báo phép biến đổi như `map`, `filter`, `take`, `flatMap`. Một phép biến đổi có thể loại phần tử, tạo thêm phần tử, hoặc đổi kiểu kết quả.
3. **Bên nhận (`Subscriber`)**: đăng ký lắng nghe tín hiệu, nhận các phần tử, lỗi và hoàn tất.

Mô hình Reactive Streams gồm `onSubscribe(Subscription)`, `onNext(T)`, `onError(Throwable)` và `onComplete()`. Khi nhận `Subscription`, bên nhận có thể gọi `request(n)` để yêu cầu thêm `n` phần tử và gọi `cancel()` để dừng nhận. Cơ chế **backpressure** cho phép bên nhận điều tiết nhu cầu gửi dữ liệu, tùy nguồn và toán tử có tuân thủ hợp đồng và cách chúng đệm dữ liệu. Nó không tự động làm database nhanh hơn hay giới hạn mọi HTTP request đến server.

Một pipeline thường **lười thực thi** theo nghĩa các tín hiệu xử lý sẽ bắt đầu khi có subscription; tuy nhiên, việc tạo đối tượng hoặc tính đối số ở lúc khai báo vẫn có thể chạy ngay. Ví dụ `Flux.just(expensiveCall())` gọi `expensiveCall()` ngay khi xây dựng nguồn; `Flux.defer(() -> Flux.just(expensiveCall()))` hoãn việc gọi đến lúc subscription.

Lưu ý thêm:

- **Reactive không đồng nghĩa luôn bất đồng bộ.** `Flux.just` và `Flux.range` thường phát phần tử đồng bộ ngay khi đăng ký; `Flux.interval` dùng bộ lập lịch và phát theo thời gian.
- **Reactive không đồng nghĩa chạy song song.** Muốn điều phối thread hoặc thực hiện công việc song song cần xét scheduler, nguồn dữ liệu và các toán tử phù hợp; không suy ra từ kiểu `Flux` đơn thuần.
- **Phần tử `onNext` không được là `null`.** Không dùng `Flux.just(null)`; có thể dùng `Flux.empty()` để biểu diễn không có dữ liệu, hoặc chuyển đổi từ `Optional` với cách xử lý rõ ràng.
- **Không phải `Flux` nào cũng là luồng cold.** Với nhiều nguồn cold (như `Flux.range`), mỗi lần subscribe nhận một chuỗi mới; nguồn hot có thể chia sẻ sự kiện đang phát giữa nhiều subscriber, và subscriber đến muộn có thể bỏ lỡ sự kiện tùy cấu hình.

## 4. Các cách tạo Flux thông dụng

| Factory | Tác dụng | Ví dụ |
| --- | --- | --- |
| `Flux.empty()` | Chuỗi rỗng hoàn tất ngay | Không tìm thấy bản ghi trong tập kết quả |
| `Flux.just(a, b, c)` | Chuỗi các giá trị có sẵn, gồm 1 hoặc nhiều phần tử | Phát ba tên đã biết |
| `Flux.fromIterable(list)` | Phát các phần tử từ `Iterable` khi nguồn được đăng ký | Đọc các phần tử một `List` |
| `Flux.range(start, count)` | Phát `count` số nguyên liên tiếp từ `start` | `Flux.range(3, 4)` phát 3, 4, 5, 6 |
| `Flux.error(exception)` | Kết thúc bằng lỗi | Biểu diễn thất bại được đưa vào pipeline |
| `Flux.defer(supplier)` | Tạo publisher mới khi có subscription | Hoãn việc tính nguồn dữ liệu |
| `Flux.interval(duration)` | Phát các số `Long` theo chu kỳ, mặc định tiếp tục vô hạn | Tick 0, 1, 2,… theo thời gian |

Với `Flux.range(3, 4)`, tham số thứ hai là **số lượng** phần tử chứ không phải giá trị kết thúc; kết quả là `3, 4, 5, 6`, không phải `3, 4`. Với `Flux.interval`, nếu muốn luồng hữu hạn, có thể dùng `take(n)` để nhận `n` phần tử đầu tiên rồi dừng.

## 5. Ví dụ Java 17+ chạy được: 0 phần tử, 1 phần tử, nhiều phần tử và lỗi

Ví dụ dưới đây sử dụng trực tiếp **Reactor Core** qua Maven, không cần khởi động Spring Boot, để quan sát chính xác `onNext`, `onComplete` và `onError`. Tạo hai file theo cấu trúc:

```text
flux-demo/
├── pom.xml
└── src/main/java/FluxDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>flux-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/FluxDemo.java`:

```java
import reactor.core.publisher.Flux;

public class FluxDemo {
    private static void show(String title, Flux<Integer> source) {
        System.out.println(title);
        source.subscribe(
            item -> System.out.println("onNext " + item),
            error -> System.out.println("onError " + error.getMessage()),
            () -> System.out.println("onComplete")
        );
    }

    public static void main(String[] args) {
        show("0 items", Flux.empty());
        show("1 item", Flux.just(7));

        Flux<Integer> transformed = Flux.range(1, 6)
            .filter(number -> number % 2 == 0)
            .map(number -> number * 10);
        show("many items", transformed);

        Flux<Integer> failed = Flux.concat(
            Flux.just(5),
            Flux.<Integer>error(new IllegalStateException("boom"))
        );
        show("error", failed);
    }
}
```

Từ thư mục `flux-demo`, với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=FluxDemo
```

**Output của chương trình** (bỏ qua thông báo của Maven nếu môi trường hiển thị thêm):

```text
0 items
onComplete
1 item
onNext 7
onComplete
many items
onNext 20
onNext 40
onNext 60
onComplete
error
onNext 5
onError boom
```

Giải thích theo từng case:

- `Flux.empty()` hợp lệ khi phát **0 phần tử**: chỉ có `onComplete`.
- `Flux.just(7)` hợp lệ khi phát **1 phần tử**: có một `onNext`, rồi `onComplete`.
- `Flux.range(1, 6)` ban đầu phát các số 1 đến 6. `filter` giữ số chẵn 2, 4, 6, `map` nhân 10 nên subscriber nhận 20, 40, 60. Đây là minh họa cho **N phần tử**, trong đó N phụ thuộc vào pipeline, không nhất thiết bằng số phần tử nguồn.
- `Flux.concat` lần lượt phát 5 rồi nối sang nguồn lỗi. Subscriber nhận `onError boom` và **không** nhận `onComplete` sau đó.

Các nguồn trong ví dụ (`empty`, `just`, `range`, `error` và `concat` trên chúng) đều phát đồng bộ, nên output có thứ tự xác định. Với `Flux.interval` hoặc nguồn chạy trên scheduler khác, kết quả có thể xuất hiện muộn; chương trình `main` dùng `subscribe()` và kết thúc quá sớm có thể không đợi kịp tín hiệu bất đồng bộ. Việc đợi trong ứng dụng dòng lệnh có thể xử lý riêng bằng công cụ thích hợp; **không dùng `block()` trên event loop của WebFlux**.

## 6. Biến đổi chuỗi: số lượng phần tử có thể thay đổi

Giả sử nguồn là `Flux.just(1, 2, 3, 4, 5)`. Các toán tử có ý nghĩa khác nhau:

```java
Flux<Integer> source = Flux.just(1, 2, 3, 4, 5);

Flux<Integer> doubled = source.map(n -> n * 2);
Flux<Integer> evens = source.filter(n -> n % 2 == 0);
Flux<Integer> firstThree = source.take(3);
Mono<Integer> first = source.next();
Mono<Long> total = source.count();
Mono<java.util.List<Integer>> all = source.collectList();
```

Đoạn này là ví dụ về các biểu thức khi đã có dependency Reactor, chưa phải một chương trình `main` hoàn chỉnh. Kết quả tương ứng:

- `map`: vẫn 5 phần tử (2, 4, 6, 8, 10), thay đổi **giá trị**.
- `filter`: còn 2 phần tử (2, 4), thay đổi **số lượng**.
- `take(3)`: tối đa 3 phần tử (1, 2, 3), rồi dừng nguồn sớm nếu cần.
- `next()`: chuyển sang `Mono<Integer>` chứa phần tử đầu tiên (1) hoặc hoàn tất rỗng nếu nguồn không có dữ liệu; có thể hủy phần còn lại sau phần tử đầu.
- `count()`: `Mono<Long>` phát **một** số là 5, chỉ khi nguồn hoàn tất; luồng vô hạn thường không có kết quả đếm cuối cùng.
- `collectList()`: `Mono<List<Integer>>` phát **một** danh sách `[1, 2, 3, 4, 5]` sau khi nguồn hoàn tất; nó phải giữ các phần tử trong bộ nhớ và không phù hợp để gom một nguồn vô hạn.

Một pipeline `Flux` có thể biến đổi thành `Mono` nếu toán tử chỉ còn trả về một giá trị tổng hợp; đó là sự thay đổi **kiểu và hợp đồng kết quả**, không phải quy tắc ép mọi Flux về đúng N phần tử.

## 7. Ví dụ áp dụng với Spring WebFlux

Trong Spring WebFlux, controller có thể trả trực tiếp `Flux<T>`. Framework đăng ký/tiêu thụ publisher và mã hóa dữ liệu để gửi qua HTTP. Không cần gọi `subscribe()` thủ công bên trong controller. Ví dụ dưới đây là **một controller đặt trong dự án Spring Boot có `spring-boot-starter-webflux`**, không phải Java thuần chạy độc lập:

```java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class TickController {
    @GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> ticks() {
        return Flux.interval(Duration.ofSeconds(1))
            .take(3)
            .map(index -> "tick-" + index);
    }
}
```

Khi client mở `GET /ticks` với SSE, publisher dự kiến phát ba giá trị `tick-0`, `tick-1`, `tick-2` cách nhau khoảng một giây rồi hoàn tất. Khuôn dạng HTTP thực tế là **Server-Sent Events**, có các trường/framing SSE, nên không coi ba chuỗi đó là toàn bộ raw response body. Thời gian thực tế còn phụ thuộc scheduler và mạng. Vì `interval` là nguồn cold theo mỗi subscription, các client đăng ký độc lập nhận lịch tick riêng.

Với dữ liệu repository reactive, phương thức như `findAll()` có thể trả `Flux<Entity>` để biểu diễn một tập kết quả nhiều bản ghi; nó vẫn có thể hoàn tất rỗng khi không tìm thấy gì. Khả năng phát từng phần tử trong pipeline không đồng nghĩa HTTP client luôn thấy từng phần tử ngay lập tức: **JSON array** có thể được mã hóa và đệm tùy cấu hình/media type, còn SSE hoặc NDJSON thích hợp hơn khi mục tiêu là truyền dữ liệu theo luồng.

## 8. Các sai lầm thường gặp

1. **“Flux bắt buộc có nhiều hơn một phần tử.”** Sai. `Flux.empty()` và `Flux.just(7)` đều là Flux hợp lệ. Cụm “0..N” bao gồm 0, 1 và nhiều.
2. **“Flux luôn phát vô hạn.”** Sai. `Flux.range`, `Flux.fromIterable`, `Flux.just` thường hữu hạn; `Flux.interval` có thể vô hạn. `take(n)` là một cách giới hạn nguồn.
3. **“Khai báo Flux là dữ liệu đã được tải xong.”** Sai. Phần lớn pipeline chỉ định nghĩa quá trình tạo/tải/biến đổi; dữ liệu thường được phát khi subscribe và có thể đến theo thời gian.
4. **“Có Flux là tự động không chặn hoặc chạy song song.”** Sai. Mã đồng bộ hoặc blocking trong `map` vẫn có thể chặn thread đang thực thi. Cần dùng driver/client non-blocking và không gọi `block()` trong đường xử lý event loop.
5. **“Có thể phát null để biểu diễn không tìm thấy kết quả.”** Sai. `onNext(null)` không được phép; hãy dùng `Flux.empty()`, `Mono.empty()` hoặc mô hình dữ liệu rõ ràng hơn.
6. **“Gọi subscribe nhiều lần luôn lấy lại cùng dữ liệu đã lưu.”** Sai với nguồn cold; mỗi subscription có thể kích hoạt lại truy vấn/API, trong khi nguồn hot có cách chia sẻ khác. Kiểm tra tính chất nguồn trước khi kỳ vọng chia sẻ.
7. **“collectList() giúp stream tiết kiệm bộ nhớ.”** Sai nếu nó gom hết một luồng lớn: phải giữ các phần tử cho đến lúc hoàn tất. Nếu mục tiêu là xử lý theo dòng, nên dùng các toán tử phù hợp và kiểm soát nhu cầu/buffering.
8. **“onError chỉ là một giá trị bình thường, sau đó vẫn onComplete.”** Sai. `onError` kết thúc luồng. Muốn có hành vi phục hồi phải khai báo toán tử xử lý lỗi như `onErrorResume` theo hợp đồng nghiệp vụ.
9. **“Backpressure tự giải quyết mọi vấn đề quá tải.”** Sai. Nhu cầu `request(n)` điều tiết tín hiệu theo Reactive Streams, nhưng tài nguyên database, kết nối, queue, nguồn nóng và tốc độ client vẫn phải được thiết kế và giám sát riêng.

## 9. Tự kiểm tra kiến thức

- `Flux.empty()` phát bao nhiêu `onNext`? **0**, nhưng có thể hoàn tất thành công bằng `onComplete`.
- `Flux.range(10, 3)` phát gì? **10, 11, 12**; đối số thứ hai là số lượng phần tử.
- Một `Flux` phát `A`, `B` rồi `onError` có hợp lệ không? **Có**. Sau `onError` sẽ không có `onComplete`.
- `Flux.just("A")` có phải Mono không? **Không**; nó vẫn là `Flux<String>` phát đúng một phần tử.
- Khi cần `Mono<List<T>>` thay vì `Flux<T>`? Khi **cần một kết quả duy nhất chứa toàn bộ danh sách**, chấp nhận thời gian chờ hoàn tất và chi phí bộ nhớ.
- Tại sao một nguồn `Flux.interval` không giới hạn thường không phù hợp với `collectList()`? Vì không có tín hiệu hoàn tất tự nhiên để phát danh sách cuối cùng, đồng thời các phần tử có thể tiếp tục được giữ lại.

**Ghi nhớ:** `Flux<T>` mô tả **một chuỗi tín hiệu gồm 0, 1 hoặc nhiều phần tử** trên mỗi subscription, có thể kết thúc bằng hoàn tất/lỗi hoặc tiếp tục cho đến khi hủy. `Mono<T>` cam kết **tối đa một phần tử**. Khi dùng Spring WebFlux, hãy chọn kiểu theo số lượng kết quả nghiệp vụ, và quan sát cả tín hiệu, subscription, khả năng hủy, buffering và lỗi — không chỉ số phần tử tại thời điểm khai báo.

*Tài liệu tham khảo:* [Project Reactor — Flux, an Asynchronous Sequence of 0-N Items](https://projectreactor.io/docs/core/release/reference/coreFeatures/flux.html), [Project Reactor — Mono, an Asynchronous 0-1 Result](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html).