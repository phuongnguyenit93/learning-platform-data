# Mono<T>: biểu diễn kết quả từ không đến một phần tử

**Chủ đề:** Spring Framework Reactive — **Mono và Flux**.

Trong Project Reactor, `Mono<T>` là một `Publisher<T>` biểu diễn **tối đa một giá trị** và sự hoàn tất của một công việc. Một `Mono` có thể phát đúng một giá trị, hoàn tất mà không phát giá trị nào, hoặc kết thúc bằng lỗi. Từ khóa quan trọng là **0..1 phần tử**, không phải “luôn trả về một đối tượng”.

`Mono` thường xuất hiện khi một thao tác chỉ có một kết quả hợp lệ: tìm một sản phẩm theo ID, gọi HTTP để lấy một resource, xác thực token, lưu một đối tượng, hoặc chạy công việc chỉ cần biết đã hoàn tất.

## 1. Hiểu chính xác “không đến một phần tử”

`Mono<T>` tuân theo hợp đồng tín hiệu của Reactive Streams. `T` là kiểu **phần tử được phát**; nó không mô tả thời gian chạy, thread hay trạng thái lỗi. Bên nhận đăng ký (`Subscriber`) có thể quan sát các tín hiệu:

- `onSubscribe(Subscription)`: nhận subscription, cho phép yêu cầu dữ liệu và hủy.
- `onNext(T)`: xuất hiện **tối đa một lần**, mang một giá trị **khác null**.
- `onComplete()`: kết thúc bình thường, có thể sau một `onNext` hoặc không có `onNext`.
- `onError(Throwable)`: kết thúc do lỗi, không đi kèm `onComplete`.

Ba kết cục thông dụng là:

| Trường hợp | Thứ tự tín hiệu dữ liệu/kết thúc | Ý nghĩa |
|---|---|---|
| **Có một phần tử** | `onNext(value) → onComplete()` | Thành công và có một giá trị |
| **Không có phần tử** | `onComplete()` | Thành công nhưng không có giá trị để phát |
| **Lỗi** | `onError(error)` | Công việc thất bại; lỗi là tín hiệu kết thúc |

Mỗi chuỗi bên trên còn có `onSubscribe` trước đó. Không có kết quả thứ tư “`onNext(null)`”: theo Reactive Streams, `null` **không phải dữ liệu được phép phát**. Một `Mono` bình thường cũng không phát hai phần tử.

```text
Một giá trị:
subscribe → onNext("Java") → onComplete

Rỗng:
subscribe → onComplete

Lỗi:
subscribe → onError(IllegalStateException)

Không hợp lệ:
subscribe → onNext("A") → onNext("B") → onComplete
subscribe → onNext(null) → onComplete
subscribe → onNext("A") → onError(...)
```

Điểm cuối cùng rất dễ gây nhầm lẫn: **Mono đã phát một giá trị không được tiếp tục phát lỗi**; một `Mono` lỗi chỉ kết thúc với `onError`. Một số factory như `Mono.never()` có thể không phát giá trị và cũng không kết thúc; vì vậy, “0..1 phần tử” không có nghĩa mọi subscription đều sẽ kết thúc ngay hoặc luôn kết thúc trong thời gian hữu hạn. Tác vụ thực tế nên có timeout khi cần.

## 2. Mono<T> là mô tả công việc, không phải T

So sánh các kiểu:

| Kiểu | Điều được biểu diễn | Khác biệt quan trọng |
|---|---|---|
| `T` | Giá trị đã có ngay trong bộ nhớ | Không mang hợp đồng reactive về completion/error |
| `Optional<T>` | Một giá trị có thể không tồn tại, **đã được xác định** | Không tự biểu diễn công việc đang chờ hay tín hiệu lỗi bất đồng bộ |
| `CompletableFuture<T>` | Kết quả hoặc lỗi sẽ hoàn tất về sau | Thường là tác vụ đã bắt đầu; không tự bảo đảm I/O non-blocking |
| `Mono<T>` | Publisher cho **0 hoặc 1** giá trị, hoặc completion/error | Có subscription, cancellation, composition và mô hình demand của Reactive Streams |
| `Flux<T>` | Publisher cho **0 đến nhiều** giá trị | Có thể phát nhiều `onNext` trước kết thúc |

Ví dụ cùng một phép tìm kiếm:

```java
Product direct = findImmediately(id);       // có thể trả null hoặc ném exception
Optional<Product> optional = cache.find(id);
Mono<Product> result = reactiveRepo.findById(id);
```

Đây là **mã minh họa**, `Product` và các phương thức/đối tượng chưa được khai báo. Với `Mono<Product>`, không lấy được `Product` bằng phép gán thông thường: người dùng phải **compose** pipeline, hoặc để WebFlux subscribe và chuyển giá trị thành HTTP response.

**Không suy ra rằng cứ có Mono là tự chạy bất đồng bộ hoặc không chặn.** Ví dụ `Mono.just("OK")` có thể phát ngay trên luồng subscribe; `Mono.fromCallable(() -> blockingIo())` vẫn gọi I/O blocking trên luồng thực thi source, trừ khi bố trí scheduler thích hợp.

### Mono<List<T>> có phải nhiều phần tử không?

Không. Một `Mono<List<Product>>` có thể phát **một đối tượng List** (dù list có 100 phần tử bên trong), rồi hoàn tất. Ngược lại `Flux<Product>` có thể phát 100 lần `onNext(Product)`.

```java
Mono<List<Integer>> oneList = Mono.just(List.of(1, 2, 3));
Flux<Integer> threeItems = Flux.just(1, 2, 3);
```

Đây là **đoạn minh họa** trong project có Reactor và `java.util.List`. Chọn `Mono<List<T>>` khi muốn một kết quả kiểu collection trọn vẹn; chọn `Flux<T>` khi cần dòng từng item, streaming và xử lý nhiều phần tử.

## 3. Tạo Mono theo đúng ý nghĩa của dữ liệu

| Factory | Kết quả | Khi nào dùng |
|---|---|---|
| `Mono.just(value)` | Phát đúng một `value` không null | Đã có giá trị |
| `Mono.empty()` | Chỉ `onComplete`, không có `onNext` | Không tìm thấy giá trị hoặc công việc xong không có dữ liệu |
| `Mono.error(error)` | Chỉ `onError` | Báo lỗi theo hợp đồng reactive |
| `Mono.justOrEmpty(value)` | Có giá trị nếu `value != null`; nếu không thì empty | Chuyển kết quả nullable sang Mono |
| `Mono.justOrEmpty(optional)` | Phát giá trị nếu `Optional` có giá trị | Chuyển Optional sang Mono |
| `Mono.fromSupplier(supplier)` | Gọi supplier khi subscribe; phát giá trị hoặc empty nếu trả null | Tính toán/đọc dữ liệu trì hoãn |
| `Mono.fromCallable(callable)` | Gọi callable khi subscribe; lỗi được biến thành `onError`; null thành empty | Công việc có thể ném checked exception |
| `Mono.defer(() -> source)` | Chọn/tạo Mono nguồn **mới cho mỗi subscription** | Đọc trạng thái cập nhật, tạo source phụ thuộc ngữ cảnh |
| `Mono.fromFuture(future)` | Cầu nối từ `CompletableFuture` | Tích hợp API bất đồng bộ cũ |
| `Mono.delay(duration)` | Sau khoảng đợi phát một giá trị `Long` | Timer bất đồng bộ, không ngủ request thread |

Các đoạn dưới đây **là snippets**, cần đặt trong class có Reactor dependency:

```java
Mono<String> a = Mono.just("Spring");
Mono<String> b = Mono.empty();
Mono<String> c = Mono.error(new IllegalStateException("Unavailable"));

String maybeName = null;
Mono<String> d = Mono.justOrEmpty(maybeName); // empty, không phát null

Optional<String> maybeEmail = Optional.of("a@example.org");
Mono<String> e = Mono.justOrEmpty(maybeEmail); // phát một email

Mono<String> f = Mono.fromSupplier(() -> "computed");
Mono<String> g = Mono.defer(() -> Mono.just("fresh source"));
```

**Không dùng `Mono.just(null)`**: factory yêu cầu đối tượng không null và ném `NullPointerException` khi tạo. `Mono.justOrEmpty(null)` là cách chuyển một giá trị nullable thành empty. `Mono.fromCallable(() -> null)` cũng hoàn tất empty.

### Giá trị được tính khi nào?

```java
String value = loadValue();
Mono<String> eager = Mono.just(value);

Mono<String> delayed = Mono.fromCallable(() -> loadValue());
```

- Ở dòng đầu, `loadValue()` đã chạy **trước khi tạo `eager`**, bất kể có subscribe hay không.
- Ở `delayed`, `loadValue()` chạy **khi có subscription**, có thể chạy lại với subscription mới.
- `Mono.defer(() -> createMono())` trì hoãn cả việc **chọn/tạo Mono nguồn** đến lúc subscribe. Factory có thể dùng trạng thái mới nhất.
- “Tạo pipeline” thường khác “kích hoạt pipeline”, nhưng **không được khẳng định mọi Mono đều cold/lazy**: `just` chụp giá trị khi assembly; một số source hot, `Sinks` hoặc `CompletableFuture` có thể đã hoạt động trước subscription.

Nếu `loadValue()` làm I/O blocking, `fromCallable` **chỉ trì hoãn**, không tự biến I/O thành non-blocking. Cách cô lập blocking được trình bày ở mục 8.

## 4. Ví dụ Reactor chạy được trên Java 17+

Ví dụ sau tự chạy bằng Maven và Reactor Core; nó không cần Spring Boot. Mục tiêu là **nhìn đúng tín hiệu 0..1**, phân biệt một giá trị, empty, lỗi và công việc trì hoãn.

Tạo cấu trúc:

```text
mono-cardinality-demo/
├── pom.xml
└── src/main/java/demo/MonoCardinalityDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>mono-cardinality-demo</artifactId>
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
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/MonoCardinalityDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

public class MonoCardinalityDemo {
    private static <T> void show(String label, Mono<T> mono) {
        mono.subscribe(
                value -> System.out.println(label + ":onNext=" + value),
                error -> System.out.println(label + ":onError=" + error.getMessage()),
                () -> System.out.println(label + ":onComplete")
        );
    }

    public static void main(String[] args) {
        show("one", Mono.just("Java"));
        show("empty", Mono.<String>empty());
        show("error", Mono.<String>error(
                new IllegalStateException("boom")));

        show("fallback", Mono.<String>empty().defaultIfEmpty("guest"));

        AtomicInteger calls = new AtomicInteger();
        Mono<Integer> deferred = Mono.fromSupplier(calls::incrementAndGet);

        System.out.println("callsBefore=" + calls.get());
        show("deferred1", deferred);
        show("deferred2", deferred);
        System.out.println("callsAfter=" + calls.get());
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.MonoCardinalityDemo
```

**Đầu ra của chương trình** (không tính thông báo từ công cụ Maven):

```text
one:onNext=Java
one:onComplete
empty:onComplete
error:onError=boom
fallback:onNext=guest
fallback:onComplete
callsBefore=0
deferred1:onNext=1
deferred1:onComplete
deferred2:onNext=2
deferred2:onComplete
callsAfter=2
```

Tại sao thứ tự in ở đây xác định? Tất cả source trong ví dụ phát **đồng bộ khi subscribe**; không có `delay`, scheduler hay network. `show` đăng ký một source tại một thời điểm. Đầu ra minh họa:

1. `one` có một `onNext` và một `onComplete`.
2. `empty` chỉ có `onComplete`; callback `value` không chạy.
3. `error` chỉ có `onError`; không có `onComplete` sau lỗi.
4. `defaultIfEmpty("guest")` biến empty thành **một giá trị**, nên có `onNext`.
5. `Mono.fromSupplier` không tăng counter khi tạo. Hai subscription khiến supplier chạy hai lần, lần lượt tạo giá trị 1 và 2.

**Lưu ý về `subscribe()`:** cách chủ động subscribe trong `main` phù hợp cho chương trình minh họa. Trong **Spring WebFlux controller**, thông thường **trả về Mono** để framework quản lý subscription, response, lỗi và cancellation. Không gọi `subscribe()` riêng để gửi response HTTP.

## 5. Thao tác trên kết quả 0..1

### 5.1. `map`: biến đổi phần tử nếu nó tồn tại

```java
Mono<String> title = Mono.just("java")
        .map(String::toUpperCase); // phát "JAVA"

Mono<String> missing = Mono.<String>empty()
        .map(String::toUpperCase); // vẫn empty
```

`map` chỉ chạy khi có `onNext`. Khi source empty, không có gì để map; source vẫn hoàn tất empty. Khi source error, lỗi được chuyển xuống downstream. Hàm map **không được trả null**; nếu bản thân mapper trả null, Reactor coi đó là lỗi. Nếu muốn biến một giá trị thành trạng thái “không có phần tử”, dùng toán tử phù hợp như `filter` hoặc `flatMap` trả `Mono.empty()`.

### 5.2. `filter`: có thể biến một thành không

```java
Mono<Integer> positive = Mono.just(7)
        .filter(number -> number > 0); // phát 7

Mono<Integer> removed = Mono.just(-2)
        .filter(number -> number > 0); // empty
```

`filter` loại phần tử không đạt điều kiện. **Empty sau filter không phải lỗi**; là kết thúc thành công mà không có item.

### 5.3. `flatMap`: ghép thao tác cũng trả Mono

```java
Mono<String> userId = Mono.just("u1");

Mono<String> displayName = userId
        .flatMap(id -> Mono.just("User " + id)); // "User u1"
```

Dùng `map` nếu lambda trả **giá trị thường**, `flatMap` nếu lambda trả **Mono**. Nếu `userId` empty, lambda trong `flatMap` không chạy; `displayName` cũng empty.

Đừng viết:

```java
Mono<Mono<String>> nested = userId
        .map(id -> Mono.just("User " + id));
```

Khi cần `Mono<String>`, sử dụng `flatMap` để tránh `Mono<Mono<String>>`. Các snippets này không phải ứng dụng độc lập.

### 5.4. Empty fallback: `defaultIfEmpty` và `switchIfEmpty`

```java
Mono<String> primary = Mono.<String>empty();

Mono<String> withValue = primary
        .defaultIfEmpty("anonymous");

Mono<String> withBackup = primary
        .switchIfEmpty(Mono.just("backup"));
```

- `defaultIfEmpty(value)`: nếu source **hoàn tất empty**, thay bằng **một giá trị mặc định**.
- `switchIfEmpty(otherMono)`: nếu source hoàn tất empty, **subscribe một publisher dự phòng**. Đường dự phòng có thể phát giá trị, empty hoặc error.
- Cả hai **không phải xử lý lỗi**. `Mono.error(...)` không kích hoạt empty fallback.
- Khi phương án dự phòng tốn chi phí hoặc có side effect lúc **tạo source**, dùng `Mono.defer` để trì hoãn việc tạo:

```java
Mono<String> found = primary.switchIfEmpty(
        Mono.defer(() -> fetchFallbackFromCache()));
```

`fetchFallbackFromCache()` ở đây là hàm giả định **trả Mono<String>**. Dùng `defer` để chỉ tạo nguồn fallback khi thực sự cần; không thay đổi bản chất blocking của hàm nếu nó blocking.

### 5.5. Error fallback tách biệt với empty

```java
Mono<String> failed = Mono.<String>error(
        new IllegalStateException("unavailable"));

Mono<String> recovered = failed
        .onErrorResume(IllegalStateException.class,
                error -> Mono.just("temporary fallback"));
```

`onErrorResume` chạy khi gặp lỗi phù hợp, biến lỗi thành một publisher khác. Nó **không chạy chỉ vì source empty**. `onErrorReturn` cũng có thể cung cấp một giá trị dự phòng cố định khi lỗi phù hợp.

Không dùng `onErrorComplete()` một cách vô thức: nó có thể chuyển lỗi thật thành empty, khiến downstream hiểu nhầm “không tìm thấy” thay vì “dịch vụ đang hỏng”. Chọn cách xử lý theo nghĩa nghiệp vụ.

### 5.6. Phối hợp nhiều Mono cần chú ý empty

```java
Mono<String> first = Mono.just("A");
Mono<String> second = Mono.just("B");

Mono<String> combined = Mono.zip(first, second)
        .map(tuple -> tuple.getT1() + tuple.getT2()); // "AB"
```

`zip` cần **mỗi nguồn cung cấp một item** để tạo tuple. Nếu một nguồn empty, kết quả kết hợp có thể hoàn tất empty mà không gọi mapper; một số nguồn khác có thể bị hủy tùy tiến trình thực thi. `Mono<Void>` hoặc pipeline `then()` là nguồn empty về mặt dữ liệu, do đó thường không dùng để `zip` lấy giá trị.

Nếu muốn **đợi hoàn tất các công việc** mà không cần kết quả dữ liệu, hãy xem `Mono.when(...)`; nếu muốn **giữ một giá trị sau khi công việc phụ kết thúc**, xem `thenReturn(...)` hoặc phối hợp phù hợp.

## 6. Empty, null, lỗi và Optional — phân biệt theo nghiệp vụ

Ví dụ một thao tác tìm user theo ID:

| Tình huống | Cách biểu diễn thích hợp | Ý nghĩa |
|---|---|---|
| Tìm thấy user | `Mono.just(user)` hoặc publisher phát user | Thành công có dữ liệu |
| Không có user tương ứng | `Mono.empty()` | Thành công nhưng không có dữ liệu |
| CSDL mất kết nối | `Mono.error(cause)` | Lỗi hạ tầng, không phải thiếu user |
| Giá trị nullable từ API cũ | `Mono.justOrEmpty(value)` | Chuyển `null` thành empty |
| API cũ trả Optional | `Mono.justOrEmpty(optional)` | Chuyển Optional vào hợp đồng Mono |

**Không đánh đồng `Mono.empty()` với `Mono.just(Optional.empty())`.** Cái thứ nhất phát **0 item**; cái thứ hai phát **1 item** có kiểu `Optional<T>` với trạng thái empty bên trong. Tùy tầng thiết kế, `Mono<Optional<T>>` thường tạo thêm một lớp biểu diễn “không có” mà không cần thiết.

**Không phát Java `null` bằng `onNext`.** Ở ranh giới đồng bộ, `mono.block()` có thể trả `null` nếu Mono empty; đó là cách chuyển đổi từ hợp đồng reactive sang API chờ đồng bộ, **không chứng minh Mono đã phát null**. Nếu cần làm việc với Optional ở ranh giới này, Reactor có `blockOptional()`, nhưng đừng dùng các thao tác chặn này trên event-loop request thread.

## 7. Mono trong Spring WebFlux: một resource hoặc 404

WebFlux có thể dùng `Mono<ProductDto>` để trả về tối đa một product. Nhưng **Mono empty không tự có nghĩa HTTP 404** trong mọi controller. Với yêu cầu REST cụ thể, hãy mã hóa lựa chọn HTTP status một cách tường minh.

Ví dụ controller dưới đây dành cho **ứng dụng Spring Boot WebFlux đã có** `spring-boot-starter-webflux`. Đây là class Java 17 hợp lệ, không cần database: dữ liệu nằm trong `Map`; ứng dụng Spring Boot và cấu hình chạy server là phần môi trường xung quanh.

```java
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/products")
public class ProductController {
    private final Map<String, ProductDto> products = Map.of(
            "p1", new ProductDto("p1", "Keyboard"),
            "p2", new ProductDto("p2", "Mouse")
    );

    @GetMapping("/{id}")
    public Mono<ResponseEntity<ProductDto>> getOne(@PathVariable String id) {
        return Mono.defer(() -> Mono.justOrEmpty(products.get(id)))
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound()
                        .<ProductDto>build());
    }

    public record ProductDto(String id, String name) { }
}
```

Quan sát về mặt HTTP khi ứng dụng WebFlux đang chạy:

```text
GET /products/p1
→ HTTP 200, body JSON: {"id":"p1","name":"Keyboard"}

GET /products/unknown
→ HTTP 404, không có body product
```

Giải thích từng đoạn:

1. `Mono.defer` trì hoãn việc tra `Map` cho tới khi subscribe; với ví dụ nhỏ này, việc đọc `Map` nhanh và không blocking I/O.
2. `Mono.justOrEmpty(products.get(id))` phát **một `ProductDto`** nếu có; nếu không, nó phát **onComplete không có item**.
3. `map(ResponseEntity::ok)` chỉ chạy khi có product, biến item thành `ResponseEntity` với status 200.
4. `defaultIfEmpty(ResponseEntity.notFound().<ProductDto>build())` cung cấp **một `ResponseEntity` 404** nếu lookup empty.
5. Controller trả `Mono<ResponseEntity<ProductDto>>`. WebFlux subscribe và xử lý response; ứng dụng không tự gọi `subscribe` hoặc `block`.

Khác biệt giữa hai chữ ký:

- `Mono<ProductDto>`: nội dung product được cung cấp dưới dạng publisher; muốn tùy biến status theo empty/error thì cần xử lý thêm.
- `Mono<ResponseEntity<ProductDto>>`: cả response status, header và body có thể được quyết định khi Mono phát item; thuận tiện khi có cả nhánh 200/404.

Trong ứng dụng thật, thay `Map` bằng repository reactive (`Mono<Product> findById(...)`), nhưng chỉ gọi “non-blocking end-to-end” khi **driver, HTTP client và những thao tác trong pipeline** cũng không blocking.

### Ví dụ Mono<Void>: việc hoàn tất nhưng không trả item

```java
// repository là một reactive repository được khai báo ở nơi khác.
public Mono<Void> delete(String id) {
    return repository.deleteById(id);
}
```

`Mono<Void>` thường đại diện **việc cần hoàn thành, không có item dữ liệu**. Nó vẫn có thể kết thúc thành công (`onComplete`) hoặc thất bại (`onError`). `Void` **không có nghĩa “phát null”**.

Ví dụ trả về HTTP status cho tác vụ xóa:

```java
@DeleteMapping("/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable String id) {
    return repository.deleteById(id)
            .thenReturn(ResponseEntity.noContent().build());
}
```

Đây là **snippet**, cần controller, `repository` và import `DeleteMapping`, `ResponseEntity`, `Mono` thích hợp. `thenReturn` chỉ phát 204 sau khi source hoàn tất thành công; nếu source lỗi, lỗi được chuyển tiếp. **Không mặc định coi “ID không tồn tại” sẽ gây lỗi**: hành vi của `deleteById` tùy implementation/hợp đồng repository.

## 8. Mono không bảo đảm tự động bất đồng bộ hoặc non-blocking

Hai đoạn trông giống nhau nhưng đường thực thi khác nhau:

```java
Mono<String> immediate = Mono.just("OK");

Mono<String> blocking = Mono.fromCallable(
        () -> legacyClient.readFromDatabase());
```

`immediate` đã có dữ liệu; có thể phát đồng bộ trên thread subscribe. `blocking` trì hoãn gọi `legacyClient`, nhưng **worker nào thực hiện Callable vẫn phải đợi** nếu thư viện bên trong dùng blocking I/O.

Khi buộc phải tích hợp nguồn blocking trong ứng dụng WebFlux, có thể cô lập trên scheduler dành cho blocking:

```java
Mono<String> isolated = Mono
        .fromCallable(() -> legacyClient.readFromDatabase())
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là snippet cần import `reactor.core.scheduler.Schedulers` và đối tượng `legacyClient`. `boundedElastic` **không biến thư viện blocking thành non-blocking**; nó chuyển nơi thực hiện blocking và quản lý giới hạn worker/hàng đợi. Với stack end-to-end reactive, ưu tiên driver/client thực sự hỗ trợ non-blocking, như R2DBC khi phù hợp.

### Khi nào Mono thực sự chạy?

Một số source như `just` phát ngay sau subscription. Source như `WebClient` cần subscription để kích hoạt trao đổi HTTP. Source như `Mono.delay(Duration.ofMillis(100))` lập lịch phát sau khoảng thời gian đã định, không cần giữ request thread bằng `Thread.sleep`.

Đặc biệt, **không gọi `block()`/`blockOptional()`/`blockFirst()` bên trong request handler WebFlux** để lấy dữ liệu rồi trả kết quả đồng bộ. Các lời gọi đó chặn thread, và Reactor có thể từ chối blocking trên những thread được đánh dấu non-blocking. Hãy giữ `Mono` trong pipeline, rồi trả về cho framework.

## 9. Quản lý vòng đời: subscribe, cancellation và lỗi

Trong mã reactive ứng dụng:

```java
Mono<String> result = webClient.get()
        .uri("/profile/{id}", id)
        .retrieve()
        .bodyToMono(String.class);

return result
        .filter(body -> !body.isBlank())
        .switchIfEmpty(Mono.just("{}"));
```

Đây là snippet trong service/controller có `webClient` và `id`. `WebClient` tạo publisher cho body response; `filter` có thể biến kết quả thành empty, `switchIfEmpty` đưa về một chuỗi fallback. Trong thực tế, trả JSON giả `"{}"` có thể không phù hợp hợp đồng API; ví dụ dùng để làm rõ pipeline 0..1.

Về vòng đời:

1. **Assembly:** tạo pipeline. Việc tạo publisher không đồng nghĩa toàn bộ side effect đã chạy hoặc request HTTP đã gửi.
2. **Subscription:** subscriber đăng ký và đưa ra demand; source bắt đầu khi phù hợp. Mỗi subscription có thể kích hoạt source lại nếu source có tính chất cold.
3. **Signals:** có thể phát một `onNext` rồi `onComplete`; chỉ `onComplete`; hoặc `onError`.
4. **Cancellation:** subscriber có thể hủy nếu không còn cần kết quả. Hủy không bảo đảm một tác vụ bên ngoài đã khởi chạy có thể được hoàn tác; tùy API/source.
5. **Timeout:** một source không trả kết quả có thể giữ subscription rất lâu; dùng timeout và xử lý lỗi/thay thế có chủ đích khi có giới hạn thời gian nghiệp vụ.

Các hook dễ dùng để quan sát:

- `doOnNext(value -> ...)` chạy **chỉ khi có phần tử**.
- `doOnSuccess(value -> ...)` chạy khi Mono thành công, **kể cả empty**; callback nhận **null làm dấu hiệu empty**. Đây chỉ là đối số callback, **không phải `onNext(null)`**.
- `doOnError(error -> ...)` chạy khi có lỗi.
- `doOnSubscribe(subscription -> ...)` giúp quan sát đăng ký.
- `doFinally(signalType -> ...)` giúp quan sát kết thúc/hủy qua `SignalType`.

Không đặt side effect nghiệp vụ bắt buộc trong các hook quan sát nếu cần đảm bảo chính sách retry/cancellation hoặc transactional consistency; compose tác vụ dưới dạng publisher để kiểm soát luồng xử lý rõ ràng.

## 10. Những lỗi phổ biến liên quan đến cardinality 0..1

1. **“Mono luôn chứa một kết quả.”** Sai: `Mono.empty()` thành công nhưng không phát item.
2. **“Empty là lỗi.”** Sai: `onComplete` không có `onNext` khác `onError`; nghiệp vụ có thể quyết định chuyển empty thành 404 hoặc lỗi riêng.
3. **“`Mono.just(null)` biểu diễn không tìm thấy.”** Sai: nó ném `NullPointerException` khi tạo. Dùng `justOrEmpty`.
4. **“`Mono.just(expensiveCall())` hoãn lời gọi expensiveCall.”** Sai: đối số phải được tính trước khi gọi `just`. Dùng `fromCallable`/`fromSupplier`/`defer` phù hợp.
5. **“`map` sẽ chạy cả khi source empty.”** Sai: không có `onNext` thì không có dữ liệu để map.
6. **“`switchIfEmpty` giải quyết mọi lỗi.”** Sai: chỉ dùng khi **thành công rỗng**; lỗi dùng `onErrorResume`/chính sách khác.
7. **“`Mono<Void>` phát giá trị null.”** Sai: Mono<Void> đại diện completion/error, không phát đối tượng `Void`.
8. **“Một Mono phát được hai giá trị vì gọi `subscribe()` hai lần.”** Không phải trong **một subscription**. Hai subscriptions độc lập có thể mỗi lần nhận tối đa một item.
9. **“`Mono<List<T>>` là dòng nhiều item.”** Sai: nó có một item kiểu `List<T>`.
10. **“`Mono.zip(a,b)` vẫn luôn chạy mapper nếu a hoặc b empty.”** Sai: `zip` cần item của cả hai.
11. **“Cứ `return Mono` thì HTTP luôn là 200 hoặc luôn là 404 khi empty.”** Sai: HTTP status còn phụ thuộc controller/operator/response handling; mã hóa status đúng hợp đồng REST.
12. **“Mono mặc định tạo thread riêng và không chặn.”** Sai: scheduling và blocking phụ thuộc source/operator/client; `subscribeOn` chỉ điều phối thread, không đổi API blocking.

## 11. Tự kiểm tra hiểu biết

| Đoạn biểu thức | Số phần tử `onNext` của một subscription thành công | Kết quả |
|---|---:|---|
| `Mono.just("A")` | 1 | `"A"` rồi complete |
| `Mono.empty()` | 0 | Complete ngay |
| `Mono.error(new RuntimeException("x"))` | 0 | Terminate bằng error |
| `Mono.justOrEmpty((String) null)` | 0 | Complete, không phát null |
| `Mono.just("A").filter(v -> false)` | 0 | Filter loại item, rồi complete |
| `Mono.<String>empty().defaultIfEmpty("B")` | 1 | `"B"` rồi complete |
| `Mono.<String>empty().switchIfEmpty(Mono.just("B"))` | 1 | `"B"` rồi complete |
| `Mono.just(List.of(1,2,3))` | 1 | Một item là List ba phần tử |
| `Mono.just("A").then()` | 0 | Bỏ giá trị, chỉ giữ terminal signal |
| `Mono.<String>empty().map(String::toUpperCase)` | 0 | Mapper không chạy |
| `Mono.never()` | 0 cho tới khi hủy/khác | Không có tín hiệu kết thúc mặc định |

**Câu hỏi vận dụng:**

- Tìm product không tồn tại: nên trả `Mono.empty()` hay `Mono.error(...)`? → Tùy hợp đồng; “không tìm thấy” thường là empty ở tầng repository, controller quyết định có chuyển thành HTTP 404 hay không.
- CSDL bị lỗi kết nối: có nên biến thành `Mono.empty()`? → Thông thường **không**; làm vậy che giấu lỗi hạ tầng thành “không có dữ liệu”.
- Muốn kiểm tra Mono có item mà vẫn chỉ trả một Boolean: `source.hasElement()` trả `Mono<Boolean>`, phát `true` nếu có item hoặc `false` nếu empty; lỗi nguồn vẫn được chuyển tiếp.
- Muốn gọi một thao tác thứ hai **chỉ nếu thao tác thứ nhất có dữ liệu**: dùng `flatMap`. Nếu cần thực hiện công việc phụ **sau khi source hoàn thành thành công, kể cả empty**, dùng `then(otherMono)`/`thenReturn(value)` theo đúng nghiệp vụ.

**Ghi nhớ:** `Mono<T>` biểu diễn **0 hoặc 1 item `T`** và một vòng đời **thành công hoặc lỗi**. “Không có item” là một kết cục thành công hợp lệ, khác với Java `null` và khác với exception. Khi thiết kế Spring WebFlux, sự khác biệt này quyết định cách kết hợp pipeline, xử lý fallback và ánh xạ kết quả sang HTTP.

## Tài liệu tham khảo

- Project Reactor — [Mono: an Asynchronous 0–1 Result](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html).
- Project Reactor — [Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) (hợp đồng signal, factory và operators).
- Project Reactor — [FAQ: Empty Mono và zip](https://projectreactor.io/docs/core/release/reference/faq.html).
- Spring Framework — [WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [ResponseEntity trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html).
