# filter, filterWhen và xử lý giá trị không hợp lệ

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Biến đổi dữ liệu

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Dùng `filter` của `Mono`/`Flux` để giữ phần tử theo điều kiện **đồng bộ**, hiểu rõ giá trị bị loại khỏi chuỗi sẽ trở thành tín hiệu gì.
2. Dùng `filterWhen` khi điều kiện cần một tác vụ **reactive** trả `Publisher<Boolean>`, chẳng hạn kiểm tra quyền hoặc tra cứu cấu hình từ dịch vụ khác.
3. Phân biệt bốn tình huống: **không thỏa điều kiện**, **không có dữ liệu**, **giá trị đầu vào không hợp lệ**, và **lỗi khi kiểm tra**. Mỗi tình huống có ý nghĩa nghiệp vụ và đường xử lý khác nhau.
4. Chọn hành vi phù hợp: loại phần tử, đổi thành lỗi có thông điệp, trả giá trị dự phòng hoặc giữ lại lý do từ chối.
5. Xây dựng pipeline theo đúng semantics Reactor, tránh chặn event-loop hoặc để lỗi bị nuốt; biết cách áp dụng trong Spring WebFlux.

## 1. Bộ lọc nằm ở đâu trong pipeline reactive?

Trong Reactor, `Flux<T>` là publisher có thể phát nhiều giá trị, `Mono<T>` phát tối đa một giá trị. Các toán tử như `map`, `filter` và `filterWhen` tạo một **publisher mới**. Chúng không sửa tập dữ liệu tại chỗ; khi có subscription, dữ liệu và tín hiệu đi qua các toán tử.

```text
                  onNext(v1) ─┐
Nguồn Flux<T> → onNext(v2) ───┼─→ filter / filterWhen ─→ giá trị được giữ lại
                  onNext(v3) ─┘                       └→ giá trị bị loại: không phát onNext
                    onComplete ──────────────────────→ onComplete
                         onError ────────────────────→ onError (trừ khi chủ động xử lý lỗi)
```

Ví dụ:

```java
Flux<Integer> values = Flux.just(1, 2, 3, 4, 5);
Flux<Integer> even = values.filter(number -> number % 2 == 0);
// Khi có subscriber yêu cầu đủ dữ liệu: even phát 2, 4 rồi onComplete.
```

Đây là **đoạn minh họa**, giả sử đã import `reactor.core.publisher.Flux`. Các số lẻ bị loại, không biến thành `null`, chuỗi trống hoặc lỗi. Chuỗi kết quả là `Flux<Integer>`, không phải danh sách Java được tính ngay lập tức. Muốn thu thập ở một boundary đồng bộ để thử nghiệm có thể dùng `collectList().block()`; trong handler WebFlux thường **trả về publisher**, không gọi `block()`.

Điều kiện lọc còn ảnh hưởng đến demand (backpressure). Nếu downstream yêu cầu hai phần tử **được chấp nhận** nhưng nhiều phần tử đầu bị loại, operator có thể cần yêu cầu thêm dữ liệu từ upstream để đáp ứng nhu cầu. Không suy ra một lần `request(2)` downstream tương đương đúng hai phần tử được lấy từ nguồn. Trong một pipeline lớn, `prefetch` và các operator khác cũng tác động đến số lượng request.

## 2. `filter`: điều kiện đồng bộ

Chữ ký thường gặp:

```java
Flux<T> filter(Predicate<? super T> predicate)
Mono<T> filter(Predicate<? super T> predicate)
```

`Predicate<T>` là hàm nhận một `T` và trả về `boolean`. Với mỗi `onNext(value)`:

- Trả `true` → giữ nguyên `value` và phát xuống downstream.
- Trả `false` → loại bỏ `value`, không phát tín hiệu `onNext` cho phần tử ấy.
- Predicate ném exception → thông thường tín hiệu lỗi đi xuống downstream, không được coi là một kết quả `false` bình thường. Đừng dùng exception như một “điều kiện loại” khi có thể trả `false` hoặc xử lý lỗi ở phạm vi phù hợp.

### 2.1. Lọc sau khi chuẩn hóa dữ liệu

```java
Flux<String> names = Flux.just("  An  ", " ", " Binh ", "Linh");
Flux<String> validNames = names
        .map(String::trim)
        .filter(name -> !name.isBlank())
        .filter(name -> name.length() >= 3);
// Khi tiêu thụ: "Binh", "Linh"
```

Đây là **đoạn minh họa**; `map(String::trim)` tạo dữ liệu mới trước khi áp điều kiện. Điều kiện loại chuỗi rỗng/blank và độ dài ngắn là quyết định nghiệp vụ tùy ví dụ. Chú ý thứ tự: nếu yêu cầu bỏ khoảng trắng đầu/cuối thì phải `trim` trước khi kiểm tra độ dài.

### 2.2. `Mono.filter` có thể biến Mono có giá trị thành Mono rỗng

```java
Mono<Integer> quantity = Mono.just(-5)
        .filter(value -> value > 0);
// quantity kết thúc thành công nhưng không có onNext (Mono.empty).
```

`Mono.empty()` không phải `Mono.error(...)`. Với input không đạt điều kiện, `filter` chỉ **bỏ phần tử**; không tự gửi thông báo “số lượng sai” cho client. Cần phân biệt một giá trị không hợp lệ với việc dữ liệu vốn không tồn tại.

### 2.3. Predicate nên ngắn, thuần và không chặn

`filter(item -> item.isActive())` là phép lọc tốt khi đã có đầy đủ dữ liệu tại chỗ. Ngược lại, đừng gọi HTTP, JDBC blocking, `Thread.sleep(...)` hay `block()` bên trong predicate của request WebFlux. Những lời gọi đó chạy trên thread thực thi pipeline, có thể chặn event-loop, làm giảm throughput hoặc ném lỗi vì blocking không được phép. Nếu điều kiện cần async I/O, cân nhắc `filterWhen`; nếu chỉ có API blocking, cần chiến lược cô lập scheduler/tài nguyên riêng, không làm cho tác vụ trở thành nonblocking bằng cách đơn thuần dùng `subscribe()`.

## 3. `filterWhen`: điều kiện reactive/bất đồng bộ

Chữ ký của `Flux`:

```java
Flux<T> filterWhen(Function<? super T, ? extends Publisher<Boolean>> asyncPredicate)
Flux<T> filterWhen(Function<? super T, ? extends Publisher<Boolean>> asyncPredicate,
                   int bufferSize)
```

`Mono` cũng cung cấp `filterWhen(Function<? super T, ? extends Publisher<Boolean>>)`. Lambda **trả về một publisher của Boolean**; thường là `Mono<Boolean>` từ dịch vụ reactive. Không truyền `boolean` trực tiếp vào `filterWhen`:

```java
Flux<User> permitted = users.filterWhen(user ->
        permissionService.canView(user.id())); // giả sử trả Mono<Boolean>
```

Đây là **đoạn minh họa tích hợp**: ứng dụng cần định nghĩa `User`, `users` và `permissionService`. `filterWhen` tạo và subscribe publisher kiểm tra cho từng phần tử khi pipeline được tiêu thụ.

### Chính xác nó giữ phần tử khi nào?

Với một nguồn phần tử `item`, kết quả từ test publisher quyết định:

| Test publisher phát | Kết quả của `filterWhen` |
| --- | --- |
| Giá trị Boolean đầu tiên là `true` | Giữ nguyên `item`. |
| Giá trị Boolean đầu tiên là `false` | Bỏ `item`. |
| Hoàn tất rỗng, không phát Boolean nào | Bỏ `item` (coi như không có quyết định cho phép). |
| Phát nhiều Boolean | Chỉ Boolean **đầu tiên** được xét; với test publisher không phải `Mono`, có thể bị cancel sau giá trị đầu. |
| Phát `onError` | Lỗi thường đi xuống pipeline; **không** tự được đổi thành `false`. Cần chọn chính sách xử lý lỗi chủ động. |

Đây là hợp đồng quan trọng: `Mono.empty()` từ service kiểm tra không phải “đợi thêm đến khi có câu trả lời”; nó là **kết thúc rỗng**, nên phần tử bị lọc ra. Nếu cần bắt buộc phải có quyết định, hãy đổi kết quả rỗng thành lỗi hoặc một quyết định mặc định có chủ ý ở bên trong service.

### 3.1. Kiểm tra quyền bằng nguồn reactive

```java
Flux<Document> visible = documentRepository.findAll()
        .filterWhen(document ->
                accessService.canRead(currentUserId, document.id()));
```

Đây là **đoạn minh họa**, giả sử repository trả `Flux<Document>`, `canRead` trả `Mono<Boolean>` và các thành phần được ứng dụng định nghĩa. Nếu quyền của tài liệu A trả `true`, A được giữ; tài liệu B trả `false`, B bị bỏ; một lỗi gọi authorization service phải được xử lý theo chính sách rõ ràng, không tự biến thành “không có quyền” mà không ghi nhận.

Dùng `filterWhen` đặc biệt hợp lý khi ý nghĩa nghiệp vụ là **chọn tập kết quả**: chẳng hạn chỉ hiển thị tài liệu có thể xem trong danh sách. Với endpoint truy cập **một tài liệu cụ thể**, việc loại dữ liệu có thể cần chuyển thành HTTP 403 hoặc 404 theo chính sách bảo mật, thay vì im lặng trả response rỗng.

### 3.2. Thực thi, thứ tự và buffer

Theo API Reactor, với `Flux.filterWhen`, các test publisher được tạo và subscribe **theo thứ tự tuần tự**; đây **không** phải toán tử fan-out tự động chạy hàng trăm kiểm tra song song. `bufferSize` điều chỉnh lượng phần tử có thể giữ chờ kết quả kiểm tra và kích thước request ban đầu từ upstream (chi tiết làm tròn giới hạn phụ thuộc phiên bản); nó **không** có nghĩa số tác vụ kiểm tra đang chạy đồng thời. Chọn giá trị buffer theo thực đo, để tránh giữ quá nhiều đối tượng trong bộ nhớ.

Nếu cần kiểm tra nhiều phần tử **đồng thời** và vẫn giữ thứ tự đầu ra, có thể thiết kế bằng `flatMapSequential` với concurrency giới hạn:

```java
Flux<Item> kept = items.flatMapSequential(item ->
        asynchronousTest(item)
                .filter(Boolean::booleanValue)
                .map(allowed -> item),
        8); // tối đa tám inner publisher được subscribe đồng thời
```

Đây là **đoạn minh họa**, giả sử `asynchronousTest(item)` trả `Mono<Boolean>`. Khi kết quả Boolean là `false` hoặc publisher rỗng, inner publisher không phát `Item`; khi `true`, emit `item`. `flatMapSequential` có thể xử lý inner publisher đồng thời nhưng phát kết quả theo thứ tự đầu vào; chi phí tài nguyên khác `filterWhen` và cần đánh giá giới hạn concurrency, timeout, ordering và lỗi theo tác vụ.

## 4. Ví dụ Java 17+ chạy được: cả ba kiểu quyết định

Ví dụ CLI này chạy độc lập với Spring WebFlux, dùng **Project Reactor Core 3.8.8** và **Java 17+**. `block()` chỉ xuất hiện trong `main` để trình diễn đầu ra có thứ tự; không sao chép `block()` vào WebFlux controller.

Tạo cấu trúc:

```text
reactive-filter-demo/
├── pom.xml
└── src/main/java/demo/
    └── FilterWhenDemo.java
```

### `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>reactive-filter-demo</artifactId>
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
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/java/demo/FilterWhenDemo.java`

```java
package demo;

import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class FilterWhenDemo {
    public static void main(String[] args) {
        // 1. Predicate đồng bộ: chuẩn hóa và lọc chuỗi.
        List<String> names = Flux.just(" An ", " ", " Binh ", "Linh")
                .map(String::trim)
                .filter(name -> !name.isBlank())
                .filter(name -> name.length() >= 3)
                .collectList()
                .block();
        System.out.println("filter = " + names);

        // 2. Predicate reactive: mỗi quyết định đến từ Mono.
        List<Integer> even = Flux.range(1, 5)
                .filterWhen(number ->
                        Mono.delay(Duration.ofMillis(10))
                                .map(tick -> number % 2 == 0))
                .collectList()
                .block();
        System.out.println("filterWhen = " + even);

        // 3. Test Publisher rỗng cũng loại phần tử.
        List<Integer> selected = Flux.range(1, 4)
                .filterWhen(number ->
                        number == 3
                                ? Mono.<Boolean>empty()
                                : Mono.just(number % 2 == 1))
                .collectList()
                .block();
        System.out.println("empty decision = " + selected);

        // 4. Yêu cầu xử lý hàng loạt: bỏ bản ghi parse sai,
        // nhưng tiếp tục đọc các bản ghi còn lại.
        List<Integer> parsed = Flux.just("12", "oops", "-2", "7")
                .concatMap(raw ->
                        Mono.fromCallable(() -> Integer.parseInt(raw))
                                .onErrorResume(NumberFormatException.class,
                                        error -> Mono.empty()))
                .filter(value -> value >= 0)
                .collectList()
                .block();
        System.out.println("skip invalid = " + parsed);

        // 5. Yêu cầu nghiêm ngặt: một giá trị không hợp lệ là lỗi.
        Mono<Integer> strictlyValid = Mono.just(-2)
                .filter(value -> value >= 0)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException(
                                "quantity must be >= 0")));
        try {
            strictlyValid.block();
        } catch (IllegalArgumentException error) {
            System.out.println("reject invalid = " + error.getMessage());
        }
    }
}
```

Chạy từ thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.FilterWhenDemo
```

**Stdout của chính chương trình** (không tính log công cụ Maven; `Mono.delay` làm chậm thời gian chạy chứ không thay đổi thứ tự kết quả được thu thập):

```text
filter = [Binh, Linh]
filterWhen = [2, 4]
empty decision = [1]
skip invalid = [12, 7]
reject invalid = quantity must be >= 0
```

**Giải thích:**

- Ở ví dụ (1), `" An "` thành `"An"` nhưng có độ dài 2 nên bị loại; chuỗi chỉ khoảng trắng thành `""` nên bị loại; `"Binh"` và `"Linh"` được giữ.
- Ở ví dụ (2), `Mono.delay` mô phỏng một quyết định trả muộn và tạo publisher Boolean. Mỗi số chẵn được giữ, số lẻ bị bỏ. `filterWhen` không trả các Boolean; nó trả **chính phần tử nguồn** đạt điều kiện.
- Ở ví dụ (3), `1` cho `true` nên giữ, `2` và `4` cho `false` nên bỏ, `3` cho `Mono.empty()` nên cũng bị bỏ.
- Ở ví dụ (4), việc parse từng chuỗi nằm trong **inner Mono**. Lỗi `"oops"` được xử lý ngay trong inner publisher bằng `Mono.empty()` nên `concatMap` còn tiếp tục với `"-2"` và `"7"`. `filter(value -> value >= 0)` sau đó loại `-2`. Dùng `concatMap` để giữ thứ tự dữ liệu trong ví dụ.
- Ở ví dụ (5), điều kiện lọc thất bại tạo `Mono.empty()`. `switchIfEmpty` chuyển trường hợp đó thành `Mono.error`, vì nghiệp vụ yêu cầu phải có số lượng hợp lệ. `block()` trong CLI ném lại `IllegalArgumentException` và nhánh `catch` in ra thông báo.

Với nhu cầu kiểm thử tự động, dùng `StepVerifier` của `reactor-test` để assert chuỗi giá trị, hoàn tất và lỗi thay vì phụ thuộc vào `System.out`. Điều đó đặc biệt hữu ích khi có thời gian trễ hoặc subscription/cancellation.

## 5. “Giá trị không hợp lệ” cần được định nghĩa rõ

Cụm từ “không hợp lệ” có thể chỉ những tình huống rất khác nhau. Chọn cách xử lý dựa vào **hợp đồng nghiệp vụ**, không dựa vào việc toán tử nào viết ngắn nhất.

| Tình huống | Cách biểu diễn phổ biến | Ví dụ |
| --- | --- | --- |
| Phần tử không thuộc tập kết quả cần trả | `filter` / `filterWhen` | Danh sách chỉ hiển thị sản phẩm đang bán hoặc tài liệu người dùng được phép xem. |
| Một tham số bắt buộc sai định dạng/quy tắc | `Mono.error` hoặc `switchIfEmpty(Mono.error(...))` | Tạo đơn với số lượng âm nên trả lỗi đầu vào, không âm thầm tạo đơn rỗng. |
| Không tìm thấy một tài nguyên | `Mono.empty()` từ repository rồi `switchIfEmpty` với 404 ở HTTP boundary | Tìm theo ID không có kết quả. |
| Một phép kiểm tra bất đồng bộ từ service gặp lỗi | `onError`, có thể `timeout` + xử lý đúng chính sách | Authorization service bị gián đoạn: lỗi hệ thống hoặc từ chối theo chính sách được duyệt. |
| Dữ liệu ingest hàng loạt có bản ghi hỏng và hợp đồng cho phép bỏ | Xử lý lỗi **trên từng phần tử**, giữ audit/log/metrics | Bỏ dòng CSV lỗi, tiếp tục dòng sau và ghi lý do reject. |
| Đầu vào có nhiều trường lỗi cần thông báo đồng thời | Mô hình `ValidationResult`, `Either` hoặc DTO chứa danh sách lỗi | Form có sai email và số điện thoại; cần báo cả hai để người dùng sửa. |

### 5.1. `filter` không thể giải thích tại sao phần tử bị loại

Khi `filter(x -> isValid(x))` trả `false`, phần tử biến mất khỏi output. Downstream không nhận kèm một `ValidationError` cho phần tử đó. Với danh sách sản phẩm cần lọc, đây có thể là hành vi tốt. Với nhập liệu, báo cáo lỗi hoặc xác thực bảo mật, việc im lặng loại giá trị có thể khiến API khó hiểu hoặc làm thất thoát dữ liệu.

Nếu cần **giữ lý do từ chối**, dùng kiểu kết quả rõ ràng:

```java
record ValidationResult<T>(
        T value, boolean valid, String reason) {}

Flux<ValidationResult<String>> results = Flux.just("A", "AB")
        .map(text -> text.length() >= 2
                ? new ValidationResult<>(text, true, "")
                : new ValidationResult<>(text, false, "too short"));
```

Đoạn **minh họa** dùng Java 17 records; nó giữ cả hai kết quả và lý do. Khi cần xuất báo cáo, có thể phân nhánh output hợp lệ và output lỗi. Tránh gọi `filter` trước rồi mới mong khôi phục thông tin đã bị loại.

### 5.2. Empty không phải Error; Error không phải False

Hãy nhớ ba tín hiệu khác nhau:

```text
Mono.just(value).filter(predicateFalse)  → onComplete (không có onNext)
Mono.empty()                             → onComplete (không có onNext)
Mono.error(exception)                    → onError(exception)
```

Nếu `filterWhen` nhận inner publisher `Mono.empty()`, nó bỏ phần tử đang kiểm tra. Nếu inner publisher phát `onError`, pipeline lỗi. Một điều kiện lọc không hợp lệ không tự kích hoạt `onErrorResume`, vì nó đã hoàn tất thành công nhưng **không phát giá trị**. Muốn xử lý trường hợp rỗng hãy dùng `switchIfEmpty` hoặc `defaultIfEmpty` tùy hợp đồng.

Ví dụ: `Mono.just("abc").filter(String::isBlank).defaultIfEmpty("none")` phát `"none"`; `onErrorResume` không chạy vì không có lỗi.

## 6. Xử lý lỗi đúng phạm vi: toàn chuỗi hay từng phần tử?

Đây là sai lầm đặc biệt hay gặp khi làm sạch dữ liệu.

### 6.1. Xử lý lỗi bên ngoài có thể kết thúc nguồn sớm

```java
Flux<Integer> numbers = Flux.just("1", "bad", "3")
        .map(Integer::parseInt)
        .onErrorResume(NumberFormatException.class, ex -> Flux.empty());
```

Đây là **đoạn minh họa**. Khi `"bad"` làm `map` ném `NumberFormatException`, nguồn upstream đi vào tín hiệu lỗi; `onErrorResume` chuyển phần còn lại của pipeline sang `Flux.empty()`. Bạn **không nhận lại `"3"`** của nguồn cũ; kết quả đã phát là `1` rồi hoàn tất. Không thể xem `onErrorResume` bên ngoài là “bỏ đúng một phần tử rồi tự chạy tiếp”.

### 6.2. Phạm vi inner publisher giúp bỏ từng giá trị hỏng

```java
Flux<Integer> numbers = Flux.just("1", "bad", "3")
        .concatMap(raw ->
                Mono.fromCallable(() -> Integer.parseInt(raw))
                    .onErrorResume(NumberFormatException.class,
                            ex -> Mono.empty()));
// Khi có subscriber yêu cầu đủ: 1, 3 rồi onComplete.
```

Lỗi được xử lý tại **mỗi phép parse**, trước khi đi ra `concatMap`. Nguồn lớn vẫn tiếp tục nhận các phần tử sau. Đây là cách ổn khi hợp đồng ingest cho phép bỏ bản ghi hỏng. Đối với dữ liệu quan trọng, hãy lưu một kết quả lỗi có thể truy xuất thay vì silently drop.

### 6.3. `onErrorContinue` không phải giải pháp xác thực mặc định

`onErrorContinue` có semantics đặc thù từng operator, có thể ảnh hưởng upstream và làm code khó dự đoán. Với parse/validation theo từng bản ghi, hãy tách công việc vào inner `Mono` và xử lý `onErrorResume` ở đó, hoặc dùng kiểu kết quả mang trạng thái hợp lệ. Tránh “bật `onErrorContinue` toàn chuỗi” để mặc nhiên cho rằng mọi lỗi đều được bỏ an toàn.

### 6.4. Nếu thất bại là lỗi hệ thống thì đừng giấu

Đặc biệt trong `filterWhen` dùng để phân quyền, lỗi gọi service không nhất thiết đồng nghĩa người dùng thiếu quyền. Có ba lựa chọn thường gặp, đều cần quyết định của hệ thống:

- **Truyền lỗi** để endpoint báo 5xx/503 nếu không xác minh được, tránh trả dữ liệu chưa được kiểm chứng.
- **Fail closed**: coi lỗi là không cho phép, có log/metrics, khi chính sách yêu cầu; điều này có thể làm response giống trường hợp bị từ chối dù nguồn lỗi thực sự là hạ tầng.
- **Khôi phục có điều kiện** cho một loại lỗi cụ thể, ví dụ timeout của dịch vụ phụ không ảnh hưởng tới dữ liệu công khai; không dùng fail-open để cấp quyền truy cập dữ liệu nhạy cảm.

Ví dụ fail closed cho một tác vụ tùy chọn **khi chính sách đã xác định rõ**:

```java
Flux<Item> accepted = items.filterWhen(item ->
        remoteCheck(item)
                .timeout(Duration.ofSeconds(2))
                .onErrorResume(java.util.concurrent.TimeoutException.class,
                        ex -> Mono.just(false)));
```

Đây là **đoạn minh họa**, cần định nghĩa `Item`, `items`, `remoteCheck`. Chỉ timeout được chuyển thành `false`; các lỗi khác vẫn đi theo `onError`. `Mono.just(false)` là một quyết định *từ chối*, không tương đương sửa lỗi remote service. Hãy theo dõi timeout qua metrics/log nếu cần điều tra.

## 7. Giá trị `null`, chuỗi rỗng và cấu trúc dữ liệu lỗi

**Reactor không cho phép giá trị `null` đi trong tín hiệu `onNext`.** Các thao tác như `Mono.just(null)` không phải cách biểu diễn “giá trị có nhưng không hợp lệ”; chúng có thể ném `NullPointerException` ngay khi assembly. Toán tử `map` trả `null` sẽ dẫn tới lỗi, không phải một phần tử rỗng cho `filter` xử lý tiếp.

Khi giá trị Java đầu vào có thể `null`, chuyển nó thành publisher rỗng tại boundary:

```java
String supplied = null;
Mono<String> possible = Mono.justOrEmpty(supplied);
// possible là Mono.empty(), không phát null.
```

Đây là **đoạn minh họa**. Nếu thiếu giá trị là lỗi request, ngay sau đó dùng `switchIfEmpty(Mono.error(...))` để có tín hiệu lỗi rõ ràng. Với đầu vào `String`, `isBlank()` xử lý chuỗi chứa toàn khoảng trắng nhưng không thể gọi trên `null`. Cần chuẩn hóa/kiểm tra khả năng null **trước khi** xây dựng chuỗi Reactor.

Đối với object phức tạp, việc “hợp lệ” có thể phụ thuộc nhiều trường và luật. `filter(user -> user != null)` không phải nơi sửa lỗi upstream phát null; hãy sửa tại nguồn, dùng đối tượng được xác thực hoặc kiểu kết quả riêng. Đừng dùng `filter` để ngầm bỏ exception của việc ánh xạ JSON/deserialize sai.

## 8. Ứng dụng trong Spring WebFlux

### 8.1. Lọc danh sách: điều kiện loại là bình thường

```java
@GetMapping("/products")
public Flux<ProductDto> products() {
    return productRepository.findAll()
            .filter(Product::isPublished)
            .map(productMapper::toDto);
}
```

Đây là **đoạn minh họa trong controller**. Cần định nghĩa `Product`, `ProductDto`, `productRepository` và `productMapper`. Trong danh sách công khai, loại sản phẩm chưa publish là semantics bình thường. Vì controller trả `Flux`, WebFlux sở hữu subscription cho HTTP response. Không thêm `.subscribe()` vào handler để chạy chuỗi.

### 8.2. Kiểm tra một tài nguyên: phân biệt không tìm thấy và không đủ quyền

Giả sử repository trả `Mono<Document>`; service quyền trả `Mono<Boolean>`:

```java
@GetMapping("/documents/{id}")
public Mono<Document> readDocument(@PathVariable String id) {
    return documentRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                            HttpStatus.NOT_FOUND, "Document not found")))
            .filterWhen(document ->
                    accessService.canRead(document.id()))
            .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                            HttpStatus.FORBIDDEN, "Access denied")));
}
```

Đây là **đoạn minh họa trong WebFlux controller**, cần các import của Spring và định nghĩa `Document`, `documentRepository`, `accessService`. Trình tự có ý nghĩa:

1. Repository trả empty → `switchIfEmpty` đầu chuyển thành HTTP 404.
2. Có tài liệu, nhưng service quyền trả `false` hoặc empty → `filterWhen` bỏ tài liệu, `switchIfEmpty` sau chuyển thành HTTP 403.
3. Có tài liệu và quyền `true` → controller trả tài liệu.
4. Service quyền phát `onError` → lỗi đi xuống WebFlux; không tự biến thành 403. Có thể ánh xạ loại lỗi thành 503 theo chính sách.

Trong ứng dụng thực tế, có hệ thống cố tình trả 404 thay 403 để tránh tiết lộ sự tồn tại của tài liệu. Đó là **chính sách bảo mật** phải được chọn rõ ràng, không phải hành vi tự có của `filterWhen`. Cũng cần tránh IDOR: mọi endpoint truy cập dữ liệu nhạy cảm phải kiểm tra quyền phù hợp, dù API trả một bản ghi hay danh sách.

### 8.3. Đầu vào sai nên thành HTTP 400, không biến thành rỗng không rõ nghĩa

```java
@PostMapping("/quantity")
public Mono<Integer> acceptQuantity(@RequestBody Mono<Integer> input) {
    return input
            .filter(quantity -> quantity > 0)
            .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                            HttpStatus.BAD_REQUEST,
                            "quantity must be positive")));
}
```

Đây là **đoạn minh họa trong controller**, cần các import Spring; nó chỉ kiểm tra một con số để làm rõ ý tưởng. `filter` đơn độc sẽ cho `Mono.empty()` khi số lượng không đạt; `switchIfEmpty` biến điều đó thành lỗi hợp đồng đầu vào. Các lỗi giải mã JSON, parse body hoặc binding có thể được WebFlux xử lý theo đường riêng trước khi đến predicate này.

Với DTO nhiều trường, thường dùng Bean Validation (`@Valid`/`@Validated`), constraint annotations, custom validator hoặc một kết quả xác thực có danh sách lỗi. Không dùng hàng loạt `filter` để làm mất thông tin từng trường không hợp lệ.

### 8.4. Kiểm tra bất đồng bộ phải có timeout và quản lý tài nguyên

Nếu predicate gọi database hoặc remote HTTP:

- Dùng API reactive như `WebClient` hoặc reactive repository thay cho HTTP/JDBC blocking được đặt trong `filter`.
- Chọn timeout hợp lý vì `filterWhen` sẽ chờ kết quả kiểm tra; một Mono không hoàn tất có thể giữ item chờ lâu.
- Biết rõ empty/false/error có ý nghĩa gì với hợp đồng nghiệp vụ.
- Theo dõi latency, tỷ lệ lỗi, tỷ lệ loại, kích thước buffer và cancellation; không gọi `subscribe()` thủ công để “cho phép filterWhen chạy”.
- Khi số phần tử lớn và mỗi predicate tốn I/O, đánh giá truy vấn batch, kiểm tra phía database hoặc concurrency có giới hạn; gọi service riêng cho từng bản ghi dễ sinh vấn đề N+1.

Một điểm hiệu năng thường quan trọng hơn chọn toán tử: nếu repository hỗ trợ điều kiện lọc bằng query, hãy đẩy điều kiện **an toàn và đúng quyền** xuống nguồn truy vấn để tránh tải dữ liệu thừa rồi mới lọc ở memory. Với kiểm tra phân quyền, vẫn phải bảo đảm điều kiện được áp dụng đầy đủ ở nơi phù hợp.

## 9. Backpressure, hủy và discard

Cả `filter` và `filterWhen` đều có thể **discard** phần tử không đạt điều kiện. Với đối tượng đơn giản như `String`/`Integer` điều đó thường không đáng chú ý. Nếu giá trị đang mang tài nguyên có thể cần giải phóng (buffer, pooled object), hãy xem hướng dẫn **discard support** của Reactor và nơi cần `doOnDiscard` hoặc cơ chế giải phóng tài nguyên của thư viện. Không giả định Java GC là đủ cho mọi tài nguyên native.

`filterWhen` còn có thể giữ phần tử trong hàng đợi trong khi chờ quyết định. Khi upstream báo lỗi, downstream cancel hoặc kiểm tra kéo dài, cần hiểu cách hệ thống xử lý giá trị chưa hoàn thành. Cấu hình buffer/prefetch giúp cân bằng throughput và bộ nhớ; nó không đồng nghĩa “tự động giới hạn tối đa request HTTP ngoại vi đang chạy song song”.

Vì các kết quả bị loại không được phát xuống downstream, số lượng downstream nhận ít hơn số lượng upstream phát. Nếu đo metrics, phân biệt **items seen**, **accepted**, **rejected**, **predicate error**. Nếu cần báo lý do reject, đo trực tiếp tại nơi ra quyết định hoặc giữ đối tượng kết quả thay vì chỉ dùng `filter`.

## 10. Sai lầm thường gặp

| Sai lầm | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `filter` để gọi remote service và `block()` | Chặn thread xử lý, làm giảm khả năng mở rộng, có thể lỗi trên event-loop | Dùng `filterWhen` với publisher reactive; hoặc thiết kế ranh giới cho tác vụ blocking. |
| Dùng `filterWhen(x -> Mono.empty())` và nghĩ “chưa quyết định” | Phần tử bị loại | Trả `Mono<Boolean>` có quyết định rõ, hoặc đổi empty thành lỗi nếu thiếu quyết định là bất thường. |
| Cho rằng `onError` của async predicate tương đương `false` | Pipeline có thể thất bại ngoài dự kiến | Quy định chính sách lỗi và dùng recovery ở đúng phạm vi. |
| Dùng `filter` với dữ liệu request bắt buộc rồi trả empty vô điều kiện | Client khó biết đầu vào sai | Dùng `switchIfEmpty` để tạo lỗi 400 hoặc mô hình validation có thông điệp. |
| Dùng `map(parse)` + `onErrorResume` bên ngoài để “bỏ một dòng lỗi” | Upstream chấm dứt ở phần tử đầu tiên bị lỗi, bỏ mất phần tử sau | Xử lý parse tại từng inner publisher. |
| Dùng `filter` trước khi lưu lý do reject | Không thể tổng hợp lý do từng phần tử đã bị loại | Dùng `ValidationResult` hoặc tạo audit/metrics ở chỗ ra quyết định. |
| Đưa `null` vào `Flux.just`/`Mono.just` để lọc sau | Reactor không cho phép `null` trong `onNext` | Dùng `Mono.justOrEmpty` và xử lý hợp đồng khi thiếu dữ liệu. |
| Coi `filterWhen(..., bufferSize)` là giới hạn concurrency | Tối ưu sai; vẫn có thể chậm bởi việc kiểm tra tuần tự | Hiểu buffer/request; khi cần concurrency thiết kế riêng có giới hạn. |
| Tự `subscribe()` trong WebFlux controller | Tạo nhánh tách khỏi response, lỗi và cancellation khó kiểm soát | Trả publisher đã compose cho WebFlux. |
| Tự động “fail open” khi service quyền lỗi | Nguy cơ lộ dữ liệu | Áp dụng chính sách xác thực rõ ràng, thường không cấp quyền khi chưa xác minh. |

## 11. Tình huống thực hành và câu hỏi tự kiểm tra

**Tình huống A.** `Flux.just("1", "bad", "3").map(Integer::parseInt).onErrorResume(e -> Flux.empty())` có phát `3` không?  
**Đáp án:** Không. Nguồn lỗi ở `"bad"`; `onErrorResume` bên ngoài chuyển sang publisher khác, không quay lại tiếp tục nguồn cũ. Nếu cần bỏ riêng bản ghi lỗi, dùng inner publisher cho mỗi item như `concatMap` trong ví dụ.

**Tình huống B.** `Mono.just(0).filter(n -> n > 0)` có phát `onError` không?  
**Đáp án:** Không. Nó hoàn tất rỗng. Dùng `switchIfEmpty(Mono.error(...))` nếu số 0 là lỗi đầu vào.

**Tình huống C.** `Flux.just("a", "b").filterWhen(value -> Mono.empty())` phát gì?  
**Đáp án:** Không phát phần tử nào, sau đó hoàn tất (giả sử nguồn không lỗi). Test publisher rỗng có nghĩa phần tử không qua lọc.

**Tình huống D.** Một service quyền trả `Mono.error(new RuntimeException("unavailable"))`. `filterWhen` giữ hay bỏ phần tử?  
**Đáp án:** Mặc định lỗi đi xuống pipeline và có thể làm toàn chuỗi kết thúc bằng `onError`. Việc đổi lỗi thành false, 503 hoặc retry là quyết định xử lý cần viết rõ.

**Tình huống E.** Tại sao `filterWhen` không phải mặc nhiên nhanh hơn `filter`?  
**Đáp án:** `filterWhen` có bước subscribe publisher kiểm tra và có thể chờ I/O; các test của `Flux.filterWhen` được tạo/subscribe theo thứ tự. Với điều kiện đã có tại chỗ, `filter` đồng bộ đơn giản hơn. Chỉ dùng kiểm tra reactive khi thực sự cần.

**Tình huống F.** Danh sách tài liệu chỉ hiển thị tài liệu được xem, còn endpoint một tài liệu cần trả status cụ thể nếu từ chối. Có dùng chung một `filterWhen` được không?  
**Đáp án:** Có thể dùng cùng cơ chế kiểm tra quyền, nhưng **semantics response khác nhau**. Trong danh sách, loại phần tử bị từ chối là bình thường; với tài liệu đơn, cần `switchIfEmpty`/policy để trả 403 hoặc 404, đồng thời xử lý trường hợp tài liệu không tồn tại.

## Ghi nhớ

- `filter` nhận `Predicate<T>` trả `boolean` ngay: đúng để sàng lọc theo điều kiện tại chỗ.
- `filterWhen` nhận hàm trả `Publisher<Boolean>`: đúng khi quyết định đến từ một chuỗi reactive. **Boolean đầu tiên** là quyết định; empty loại phần tử; error là đường lỗi.
- **Bị lọc không đồng nghĩa bị lỗi.** Với dữ liệu đầu vào bắt buộc, hãy biến “không đạt điều kiện” thành lỗi hoặc đối tượng validation phù hợp, thay vì để giá trị biến mất.
- Xử lý lỗi **ở phạm vi từng phần tử** khi nghiệp vụ cho phép tiếp tục sau bản ghi lỗi; xử lý lỗi toàn chuỗi khi sự cố phải dừng xử lý.
- Trong WebFlux, hãy compose và **trả lại publisher**; framework quản lý việc subscribe ở HTTP boundary. Không dùng `block()` hoặc `subscribe()` thủ công để điều khiển toán tử trong controller.

### Tài liệu tham khảo

1. [Project Reactor Core – Flux API: filter và filterWhen](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) – hợp đồng predicate, kết quả empty/false, thứ tự test và buffer.
2. [Project Reactor Core – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) – `Mono.filter`, `Mono.filterWhen` và `switchIfEmpty`.
3. [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/) – filtering, error handling, backpressure và testing.
4. [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) – hợp đồng reactive controller và HTTP request/response.
5. [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html) – xác thực đầu vào tại boundary WebFlux.
