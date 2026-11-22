# Tín hiệu kết thúc, hủy đăng ký và quy tắc không phát `null` trong Reactive Streams

## 1. Bối cảnh và mục tiêu

Trong Spring WebFlux, các kiểu `Mono<T>` (0 hoặc 1 phần tử) và `Flux<T>` (0 đến nhiều phần tử) của Project Reactor thực thi giao thức Reactive Streams. Giao thức này không chỉ quy định cách truyền dữ liệu mà còn quy định **khi nào một lần đăng ký kết thúc, khi nào người nhận ngừng nhận, và giá trị nào được phép đi qua luồng**.

Sau bài này, bạn cần phân biệt được:

- `onComplete()`: nguồn đã kết thúc **thành công**, có thể sau 0 phần tử.
- `onError(Throwable)`: nguồn kết thúc vì **lỗi**.
- `Subscription.cancel()`: bên nhận **không còn muốn nhận dữ liệu**; đây không phải một tín hiệu kết thúc được gửi đến `Subscriber`.
- `onNext(null)`: **vi phạm giao thức**; không dùng `null` để biểu diễn luồng rỗng.

## 2. Vòng đời một Subscription

Bốn thành phần nền tảng là `Publisher<T>` (nguồn), `Subscriber<T>` (bên nhận), `Subscription` (quan hệ đăng ký, điều khiển nhu cầu/hủy) và `Processor` (vừa nhận vừa phát). Với một lần đăng ký, trình tự hợp lệ thường là:

~~~text
Publisher.subscribe(subscriber)
           |
           v
Subscriber.onSubscribe(subscription)  [đúng một lần]
           |
           +---- subscription.request(n > 0) ----> Publisher
           |
           +<--- onNext(item)  [0..N phần tử, item không null]
           |
           +<--- onComplete()  [thành công, terminal]
           | HOẶC
           +<--- onError(error) [thất bại, terminal]

Nhánh khác: Subscriber -> subscription.cancel() -> Publisher
                                      (ngừng phát cuối cùng; không bắt buộc onComplete)
~~~

Quy tắc quan trọng:

1. `onSubscribe` phải đến trước `onNext`, `onError` hoặc `onComplete`; các tín hiệu gửi cho một `Subscriber` phải **tuần tự**, kể cả khi các luồng xử lý chạy trên nhiều thread.
2. Mỗi `request(n)` với `n > 0` bổ sung quyền nhận tối đa `n` phần tử `onNext`. Tổng `onNext` không được vượt quá tổng lượng yêu cầu chưa được đáp ứng. `request(0)` hoặc `request(n < 0)` là yêu cầu sai; `Subscription` đang hoạt động phải phát `onError(IllegalArgumentException)`.
3. `onComplete` và `onError` **không cần đợi một yêu cầu dữ liệu**: nguồn rỗng hoặc lỗi sớm vẫn có thể kết thúc ngay sau `onSubscribe`.
4. `onComplete` và `onError` là **hai khả năng loại trừ nhau**. Sau một terminal signal, không được gửi tiếp bất kỳ tín hiệu nào trên cùng quan hệ đăng ký, kể cả `onNext` hay terminal thứ hai.
5. Một publisher vô hạn có thể không tự kết thúc. Không được suy ra rằng mọi `subscribe` chắc chắn sẽ nhận `onComplete` hoặc `onError`.

| Sự kiện | Ai khởi phát? | Ý nghĩa | Có phải terminal signal gửi đến Subscriber? |
| --- | --- | --- | --- |
| `onNext(value)` | Publisher | Một phần tử không-null, tính vào nhu cầu đã yêu cầu | Không |
| `onComplete()` | Publisher | Hết dữ liệu, thành công | Có |
| `onError(error)` | Publisher | Kết thúc vì lỗi, với `Throwable` không-null | Có |
| `cancel()` | Subscriber / toán tử downstream | Không còn nhu cầu; yêu cầu upstream ngừng phát và giải phóng tài nguyên | Không |

## 3. Hai tín hiệu terminal: `onComplete` và `onError`

**`onComplete()`** không mang dữ liệu và không có nghĩa là trước đó đã phát ít nhất một phần tử:

~~~java
Flux.just("A", "B");            // onNext("A"), onNext("B"), onComplete()
Flux.<String>empty();           // onComplete(), không có onNext
Mono.<String>empty();           // onComplete(), không có onNext
~~~

**`onError(Throwable)`** báo lỗi, kết thúc luồng hiện tại, không thể phát tiếp `onComplete` trên cùng quan hệ đăng ký:

~~~java
Flux.just(1, 2)
    .concatWith(Mono.error(new IllegalStateException("boom")));
// onNext(1), onNext(2), onError(IllegalStateException)
// KHÔNG có onComplete()
~~~

Đây là các đoạn minh họa biểu thức nguồn; chương trình đầy đủ có thể biên dịch và chạy nằm ở mục 6.

Các toán tử xử lý lỗi như `onErrorResume` hoặc `onErrorReturn` **thay thế phần luồng đã lỗi bằng một đường đi dự phòng**, không hồi sinh nguồn đã kết thúc. Ví dụ:

~~~java
Mono.<String>error(new IllegalStateException("DB down"))
    .onErrorResume(error -> Mono.just("cache"));
// Subscriber ở cuối thấy onNext("cache"), onComplete().
// Nguồn trước onErrorResume vẫn đã kết thúc bằng onError.
~~~

Không nên dùng `onErrorComplete()` chỉ để làm mất dấu lỗi. Chỉ chuyển lỗi thành hoàn tất rỗng nếu nghiệp vụ thực sự coi lỗi đó là không có dữ liệu.

## 4. `cancel()` và sự khác biệt với terminal signal

Khi `Subscriber` không cần dữ liệu nữa, nó gọi `Subscription.cancel()`. `cancel()` phải an toàn khi gọi từ nhiều thread, có tính idempotent (gọi lặp lại không gây thêm tác dụng), và yêu cầu nguồn **cuối cùng phải ngừng phát** cho subscriber tương ứng. Nó không bảo đảm tất cả tác vụ đang chạy dừng tức thì: do độ trễ/asynchronous race, một vài `onNext` đã được yêu cầu và đang trên đường truyền vẫn có thể đến trong lúc cancel đang được xử lý.

**Không đồng nhất `cancel()` với `onComplete()`**:

- Với `Flux.range(1, 100).take(2)`, toán tử `take(2)` nhận đủ 2 giá trị rồi **hủy đăng ký upstream** để không lấy thêm; đồng thời nó có thể gửi **`onComplete` xuống downstream**. Kết quả quan sát phụ thuộc bạn đặt hook ở bên nào của `take`.
- Với một `BaseSubscriber` chủ động gọi `cancel()`, subscriber đó không được mong chờ nguồn phải gọi `onComplete()` sau khi đã hủy.
- Khi yêu cầu HTTP bị hủy hoặc client ngắt kết nối trong WebFlux, hủy có thể lan truyền ngược lên pipeline. Việc dọn dẹp thực tế còn phụ thuộc publisher và tài nguyên tích hợp.

Để quan sát/dọn dẹp trong Reactor:

- `doOnComplete(...)`: chỉ chạy khi nguồn hoàn tất thành công.
- `doOnError(...)`: chỉ chạy khi có lỗi.
- `doOnCancel(...)`: quan sát hành động hủy tại vị trí hook.
- `doFinally(signalType -> ...)`: quan sát **`ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`** tại vị trí đặt toán tử; phù hợp để ghi metric và xử lý cuối vòng đời.

`doFinally` là callback của Reactor sau kết thúc/hủy, **không phải tín hiệu `onComplete` của Reactive Streams**. Dùng `using`/`usingWhen` hoặc cơ chế quản lý vòng đời phù hợp khi tài nguyên (kết nối, file, transaction) cần được đóng đúng trên các đường hoàn tất, lỗi và hủy; tránh dựa vào `doOnComplete` để giải phóng tài nguyên khi cancel.

## 5. Vì sao Reactive Streams không cho phép `null`?

Một lời gọi `onNext(null)` là không hợp lệ; tham số `Subscription` của `onSubscribe` và `Throwable` của `onError` cũng không được là `null`. Giá trị `null` không phải “phần tử rỗng” hay “tín hiệu kết thúc”. Việc dành riêng `onComplete` làm tín hiệu hết luồng giúp phân biệt rõ dữ liệu, thành công và lỗi trong giao thức bất đồng bộ.

Trong Project Reactor:

| Mục đích | Cách đúng | Cách sai hoặc dễ gây nhầm |
| --- | --- | --- |
| Có đúng một giá trị | `Mono.just(valueKhôngNull)` | `Mono.just(null)`: lỗi khi tạo Mono |
| Có giá trị có thể null từ API cũ | `Mono.justOrEmpty(nullableValue)` | Đưa trực tiếp `null` vào `onNext` |
| Không có giá trị | `Mono.empty()` | `Mono.just(null)` |
| Bỏ qua phần tử khi biến đổi | `flatMap(v -> điềuKiện ? Mono.just(v) : Mono.empty())` hoặc `handle` | `map(v -> null)` |
| Có lỗi thật | `Mono.error(new IllegalStateException("..."))` | `onError(null)` |
| Chỉ cần biết thao tác hoàn tất | `Mono<Void>` hoàn tất không phát dữ liệu | Dùng `null` làm phần tử “đã xong” |

Ví dụ với giá trị từ phương thức Java truyền thống:

~~~java
String email = null; // Giả lập nguồn cũ không tìm thấy email

Mono<String> optionalEmail = Mono.justOrEmpty(email);
optionalEmail
    .defaultIfEmpty("chưa có email")
    .subscribe(System.out::println);
// In: chưa có email
~~~

Nếu muốn **bỏ qua** một giá trị cụ thể (không xem đó là lỗi), hãy trả về một publisher rỗng:

~~~java
Flux.just("A", "SKIP", "B")
    .flatMap(value -> "SKIP".equals(value)
        ? Mono.<String>empty()
        : Mono.just(value));
// Phát "A", "B", sau đó onComplete; không phát null.
~~~

Nếu cần biểu diễn một trường dữ liệu *có mặt nhưng rỗng*, có thể phát `Optional.empty()` **như một object không-null**. Điều đó khác `Mono.empty()`, vốn không phát phần tử nào. Chọn mô hình rõ nghĩa theo hợp đồng nghiệp vụ.

Trong Reactor, mapper trả về `null` thường khiến pipeline nhận `NullPointerException` qua `onError`. Đừng chữa bằng cách lọc `null` sau `map`: lỗi đã xảy ra trước khi `filter` có cơ hội chạy. Hãy dùng `flatMap`/`handle` hoặc chuẩn hóa null thành `Mono.empty()` ngay tại ranh giới tích hợp.

## 6. Ví dụ Java 17+ chạy được: hoàn tất, lỗi, hủy và nguồn rỗng

Tạo project Maven với hai tệp sau. Dùng Reactor Core `3.8.8`, một bản ổn định có trên Maven Central; phần ứng dụng chạy đồng bộ để thứ tự log dễ kiểm chứng.

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-signals-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.ReactiveSignalsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/example/ReactiveSignalsDemo.java`**

~~~java
package example;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReactiveSignalsDemo {
    public static void main(String[] args) {
        System.out.println("1. COMPLETE");
        Flux.just("A", "B").subscribe(
            value -> System.out.println("onNext: " + value),
            error -> System.out.println("onError: " + error.getMessage()),
            () -> System.out.println("onComplete")
        );

        System.out.println("2. ERROR");
        Flux.just(1, 2)
            .concatWith(Mono.error(new IllegalStateException("boom")))
            .subscribe(
                value -> System.out.println("onNext: " + value),
                error -> System.out.println("onError: " + error.getMessage()),
                () -> System.out.println("onComplete")
            );

        System.out.println("3. CANCEL");
        Flux.range(1, 5)
            .doFinally(type ->
                System.out.println("upstream finally: " + type.name()))
            .subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("onNext: " + value);
                    if (value == 2) {
                        cancel();
                    }
                }
            });

        System.out.println("4. EMPTY");
        Mono.justOrEmpty((String) null)
            .defaultIfEmpty("fallback")
            .subscribe(
                value -> System.out.println("onNext: " + value),
                error -> System.out.println("onError: " + error.getMessage()),
                () -> System.out.println("onComplete")
            );
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

**Đầu ra stdout dự kiến** (các publisher trong ví dụ đều chạy đồng bộ, không có scheduler):

~~~text
1. COMPLETE
onNext: A
onNext: B
onComplete
2. ERROR
onNext: 1
onNext: 2
onError: boom
3. CANCEL
onNext: 1
onNext: 2
upstream finally: CANCEL
4. EMPTY
onNext: fallback
onComplete
~~~

Giải thích: trường hợp 1 có hai `onNext` rồi `onComplete`; trường hợp 2 có hai `onNext` rồi `onError` và **không** `onComplete`. Ở trường hợp 3, `BaseSubscriber` chỉ yêu cầu 2 phần tử rồi `cancel()`; `doFinally` phía upstream quan sát `CANCEL`, không có `onComplete` cho subscriber đã hủy. Trường hợp 4 tạo `Mono.empty()` từ `null` nhờ `justOrEmpty`, sau đó `defaultIfEmpty` thay bằng **một giá trị không-null** rồi hoàn tất.

## 7. Áp dụng trong Spring WebFlux và các lỗi thường gặp

- **Không tìm thấy bản ghi:** Với repository trả về `Mono<User>`, dùng `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND)))` khi quy ước API yêu cầu HTTP 404. `Mono.empty()` tự nó chỉ diễn đạt không có phần tử; cách ánh xạ HTTP cần được quyết định rõ ở tầng controller/handler.
- **Client hủy / timeout:** Ghi nhận cancel và giải phóng tài nguyên; đừng mặc định `doOnComplete` sẽ chạy. Timeout ở downstream có thể dẫn đến `onError` cho downstream đồng thời hủy subscription upstream; quan sát tín hiệu phải xét **vị trí đặt hook**.
- **Callback subscribe thiếu xử lý lỗi:** Khi tự gọi `subscribe` trong ứng dụng, cung cấp error consumer hoặc xây dựng đường xử lý lỗi rõ ràng. Trong handler WebFlux thông thường, ưu tiên **trả về `Mono`/`Flux`** để framework quản lý đăng ký và vòng đời.
- **Gọi `block()` trên event-loop:** Có thể chặn thread xử lý request và làm hỏng khả năng đáp ứng; nên kết hợp publisher bằng `map`, `flatMap`, `zip`... trong luồng reactive.
- **Tin rằng `request(n)` bảo đảm đúng n phần tử:** Publisher có thể hoàn tất hoặc báo lỗi sau ít hơn n phần tử; demand là **giới hạn trên**, không phải cam kết số bản ghi.
- **Xem cancel là lỗi:** Hủy có thể là hành vi bình thường (ví dụ người dùng bỏ trang hoặc `take` đã lấy đủ); dùng metric riêng cho `CANCEL`, `ON_ERROR` và `ON_COMPLETE` để phân tích chính xác.

Tự kiểm tra kiến thức: (1) `Mono.empty()` có gọi `onNext` không? **Không**, chỉ `onComplete`. (2) Có được `onComplete` sau `onError` không? **Không**. (3) `cancel()` có đồng nghĩa downstream nhận `onComplete` không? **Không**. (4) Hàm `map` trả `null` có biểu thị dữ liệu vắng mặt hợp lệ không? **Không**; dùng toán tử cho luồng rỗng.

## 8. Tài liệu chuẩn để đối chiếu

- [Reactive Streams Specification for the JVM](https://github.com/reactive-streams/reactive-streams-jvm#specification): các quy tắc Publisher 1.1–1.9, Subscriber 2.1–2.13 và Subscription 3.5–3.12.
- [Project Reactor – Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): lỗi là terminal, các toán tử fallback thay thế luồng đã lỗi.
- [Reactor Core API – Mono](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `justOrEmpty`, `empty`, `doFinally`, `doOnCancel` và quy ước với giá trị rỗng.