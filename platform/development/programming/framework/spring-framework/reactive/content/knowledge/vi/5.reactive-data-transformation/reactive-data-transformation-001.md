# `map` cho biến đổi đồng bộ một phần tử trong Project Reactor

## 1. `map` giải quyết bài toán gì?

Trong Spring WebFlux/Project Reactor, dữ liệu thường đi qua một **pipeline** thay vì được lấy ra rồi biến đổi trong vòng lặp truyền thống. Toán tử **`map`** nhận từng phần tử do `Flux` hoặc `Mono` phát ra, chạy **một hàm chuyển đổi đồng bộ** trên phần tử đó và đưa kết quả xuống phần tiếp theo của pipeline.

Ví dụ thực tế: chuyển số tiền từ đồng sang nghìn đồng, chuẩn hóa tên hiển thị, chuyển một entity sang DTO, tạo chuỗi mô tả từ một object, hoặc lấy thuộc tính đã tính toán sẵn. Mỗi phần tử đầu vào có **một phần tử đầu ra** nếu mapper chạy thành công. Phép biến đổi có thể giữ nguyên kiểu (`Integer -> Integer`) hoặc đổi kiểu (`User -> UserDto`, `Integer -> String`).

```java
Flux<Integer> tens = Flux.just(1, 2, 3)
        .map(number -> number * 10);
// Khi được subscribe: 10, 20, 30
```

Đây là **đoạn minh họa** dùng trong ngữ cảnh đã có import `reactor.core.publisher.Flux`; chương trình Java 17 chạy độc lập được cung cấp ở mục 5.

Cần phân biệt hai thứ:

- **Đồng bộ** mô tả hành vi của *hàm mapper*: nhận `T` và trả `R` trực tiếp, không trả một tác vụ bất đồng bộ như `Mono<R>`.
- **Reactive** mô tả cách phần tử đi qua pipeline khi có subscription và demand. `map` không tự tạo thread, không tự kích hoạt truy vấn hay chạy trước lúc subscriber kết nối.

Vì vậy, `map` vẫn dùng tốt trong chương trình reactive, nhưng không được đặt công việc chặn lâu (blocking) vào mapper rồi mặc định cho rằng nó đã trở thành bất đồng bộ.

## 2. Chữ ký API và hợp đồng một-một

Hai dạng phổ biến của Reactor:

```java
<R> Flux<R> Flux<T>.map(
        java.util.function.Function<? super T, ? extends R> mapper);

<R> Mono<R> Mono<T>.map(
        java.util.function.Function<? super T, ? extends R> mapper);
```

Đây là **chữ ký rút gọn để giải thích generic**, không phải cú pháp khai báo phương thức Java hợp lệ trong một class. Chúng nhấn mạnh các điểm:

- `T`: kiểu dữ liệu từ upstream.
- `R`: kiểu dữ liệu được biến đổi và phát tới downstream.
- `Function<T,R>`: thao tác nhận một `T`, tính toán rồi trả trực tiếp một `R`.
- Kết quả của `Flux.map(...)` là `Flux<R>`; kết quả của `Mono.map(...)` là `Mono<R>`. Pipeline tiếp tục thuộc mô hình reactive.
- Mapper **không được trả `null`** trong Reactor. Nếu trả `null`, pipeline phát lỗi `onError` thay vì gửi `onNext(null)`.

Về số lượng, `map` là phép biến đổi **1 → 1 trên từng tín hiệu `onNext`**. Tuy nhiên, điều đó không có nghĩa `Mono` luôn tạo ra một phần tử: `Mono.empty().map(...)` vẫn rỗng; `Flux.empty().map(...)` vẫn không phát giá trị. `map` không tự tạo phần tử từ nguồn rỗng.

Ví dụ giữ nguyên số phần tử nhưng đổi kiểu:

```java
Flux<String> labels = Flux.just(10, 20, 30)
        .map(n -> "Giá trị: " + n);
// "Giá trị: 10", "Giá trị: 20", "Giá trị: 30"
```

## 3. `map` chạy lúc nào và chạy theo luồng tín hiệu nào?

Reactor thường xây dựng pipeline theo hai giai đoạn logic:

1. **Assembly (khai báo):** gọi `Flux.just(...).map(...)` tạo mô tả công việc. Với nguồn cold thông thường, mapper chưa nhận dữ liệu.
2. **Subscription/execution (thực thi):** downstream đăng ký; khi upstream phát `onNext(T)` theo demand, toán tử gọi mapper, nhận `R` rồi phát `onNext(R)` xuống downstream.

```text
Upstream Flux<T>
    |
    | onNext(T) theo demand
    v
map(Function<T, R>)
    |
    | apply(T) -> R  [đồng bộ]
    v
Downstream Subscriber<R>
    |
    +-- xử lý onNext(R)
```

Luồng `onSubscribe`, `onError`, `onComplete` cũng phải được tuân thủ. `map` không biến completion thành dữ liệu; lỗi phát sinh từ upstream được chuyển xuống, còn exception phát sinh **trong mapper** sẽ làm chuỗi phát `onError` và kết thúc theo hợp đồng.

Điểm cần nhớ về threading: `map` **không tự chuyển thread**. Mapper được gọi trong ngữ cảnh phát tín hiệu của upstream, chịu ảnh hưởng của các toán tử điều phối như `subscribeOn`/`publishOn` nếu có. Một pipeline đồng bộ đơn giản như `Flux.just(...).map(...)` có thể chạy trên chính thread gọi `subscribe()`. Việc có `map` không bảo đảm chạy song song hoặc trên event loop riêng.

## 4. Cách đọc một phép biến đổi trong thực tế

### 4.1. Chuẩn hóa dữ liệu

```java
Flux<String> cleaned = Flux.just("  an  ", " binh ", "chi")
        .map(String::trim)
        .map(String::toUpperCase);
```

Với locale mặc định thích hợp cho các ví dụ ASCII trên, pipeline tạo `AN`, `BINH`, `CHI`. Trong sản phẩm cần kết quả không phụ thuộc locale máy chủ, dùng `s -> s.toUpperCase(Locale.ROOT)` và import `java.util.Locale`.

Hai lời gọi `map` là **hai bước biến đổi tuần tự trên cùng một phần tử**: mỗi tên được `trim()`, sau đó được đổi chữ hoa. Chúng không biến ba phần tử thành sáu phần tử.

### 4.2. Chuyển entity sang DTO

Với Java 17, `record` rất hợp để trình bày kiểu dữ liệu bất biến:

```java
record Product(int id, String name, long price) {}
record ProductView(int id, String label) {}

Flux<ProductView> views = Flux.just(
        new Product(1, "Pen", 12_000),
        new Product(2, "Book", 50_000))
    .map(p -> new ProductView(
        p.id(),
        p.name() + ": " + p.price() + " VND"
    ));
```

Đây là **đoạn mã cần đặt trong class/ngữ cảnh Java có import `Flux`**, không phải file độc lập. Nếu mapper tạo DTO thông thường mà không gọi I/O, `map` biểu diễn đúng ý định **chuyển `Product` thành `ProductView` cho từng phần tử**. Những phép biến đổi dạng này thường đặt ở tầng service/presentation để không lộ entity trực tiếp qua API.

### 4.3. `Mono.map` với tối đa một phần tử

```java
Mono<String> upper = Mono.just("spring")
        .map(value -> value.toUpperCase(java.util.Locale.ROOT));
// Phát "SPRING" khi có subscriber.
```

`Mono.map` cũng đồng bộ và một-một, nhưng upstream `Mono` vốn chỉ có tối đa một giá trị nên kết quả cũng có tối đa một giá trị.

## 5. Ví dụ hoàn chỉnh chạy được trên Java 17+

Ví dụ dưới đây thể hiện bốn hành vi trong **một chương trình**: mapper chỉ chạy khi subscribe; `Flux.map` đổi giá trị; chuyển record sang record; `Mono.map` đổi chuỗi; lỗi trong mapper kết thúc nguồn ban đầu và có thể được xử lý bằng `onErrorResume`.

Tạo thư mục:

```text
reactor-map-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>reactor-map-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.util.Locale;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class Main {
    record Item(int id, String name) {}
    record ItemView(int id, String name) {}

    public static void main(String[] args) {
        // 1) Chỉ tạo pipeline, chưa phát onNext.
        Flux<Integer> tens = Flux.just(1, 2, 3)
                .map(n -> {
                    System.out.println("map: " + n);
                    return n * 10;
                });

        System.out.println("assembled");

        // 2) Đăng ký kích hoạt nguồn Flux.just đồng bộ này.
        tens.subscribe(
                n -> System.out.println("next: " + n),
                e -> System.out.println("error: " + e.getMessage()),
                () -> System.out.println("complete")
        );

        // 3) Biến đổi object nguồn thành DTO mới.
        Flux<ItemView> views = Flux.just(
                new Item(1, " An "),
                new Item(2, " Binh ")
        ).map(item -> new ItemView(
                item.id(),
                item.name().trim()
        ));

        views.subscribe(view ->
                System.out.println(
                        "item: " + view.id() + "/" + view.name()
                )
        );

        // 4) Mono.map xử lý tối đa một giá trị.
        Mono<String> mono = Mono.just("reactor")
                .map(s -> s.toUpperCase(Locale.ROOT));

        mono.subscribe(s -> System.out.println("mono: " + s));

        // 5) Lỗi trong mapper chuyển thành onError.
        // onErrorResume thay phần luồng đã lỗi bằng fallback.
        Flux.just("12", "bad", "36")
                .map(Integer::parseInt)
                .onErrorResume(error -> Flux.just(-1))
                .subscribe(n -> System.out.println("safe: " + n));
    }
}
```

Đặt terminal tại `reactor-map-demo/`, có JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Stdout do chương trình in ra (không tính thông báo môi trường nếu Maven có cấu hình riêng):

```text
assembled
map: 1
next: 10
map: 2
next: 20
map: 3
next: 30
complete
item: 1/An
item: 2/Binh
mono: REACTOR
safe: 12
safe: -1
```

**Giải thích kết quả:**

- `assembled` xuất hiện trước `map: 1` vì `Flux.just` là nguồn cold đồng bộ và mapper chưa chạy trong giai đoạn tạo pipeline.
- Sau `subscribe`, từng số đi qua mapper rồi tới consumer, nên dòng `map: n` nằm trước `next: n * 10`.
- `Flux.map` tạo `ItemView` mới từ từng `Item`; kết quả gồm đúng hai DTO.
- `Mono.map` đổi một chuỗi sang chữ hoa và phát một chuỗi.
- `"12"` được parse thành `12`. Đến `"bad"`, `Integer.parseInt` ném `NumberFormatException`; Reactor gửi `onError` tại bước `map`. `onErrorResume` chuyển sang `Flux.just(-1)`, vì thế in `safe: -1`; `"36"` **không tiếp tục được xử lý** sau lỗi của nguồn trước đó.

Trong ứng dụng thật, hãy chọn fallback chỉ khi có ý nghĩa nghiệp vụ. Một lỗi chuyển đổi dữ liệu không phải lúc nào cũng nên bị biến thành giá trị giả `-1`; có trường hợp cần trả lỗi cho client hoặc ghi nhận dữ liệu đầu vào sai.

## 6. `map` tương tác với backpressure và completion thế nào?

Reactive Streams quy định mỗi tín hiệu `onNext` chỉ được gửi tới downstream khi có nhu cầu nhận (demand). `map` nhận một phần tử và tạo một kết quả nên **không tự thay đổi số phần tử do nó chuyển qua**, miễn là mapper thành công.

Ví dụ, với `Flux.range(1, 100).map(n -> n * 2)`, downstream yêu cầu hai giá trị (`request(2)`) thì nó chỉ có quyền nhận tối đa hai `onNext` ở giai đoạn đó, tức `2`, `4`; các phần tử sau cần demand tiếp. Không có nghĩa hai phần tử nhất thiết xuất hiện ngay lập tức với mọi loại nguồn, hoặc việc lấy dữ liệu bên dưới chắc chắn tương ứng đúng hai thao tác I/O: các operator khác có thể áp dụng prefetch, buffering hoặc chiến lược yêu cầu upstream riêng.

Với pipeline đơn giản:

```text
Publisher<T>
  -- onNext(t) -->
      map(t -> r)
  -- onNext(r) -->
Subscriber<R>

Upstream onComplete  -> downstream onComplete
Upstream onError     -> downstream onError
Mapper throw         -> downstream onError, chuỗi kết thúc
```

`map` không phát thêm completion signal cho từng giá trị. Một subscription hoàn tất khi **toàn bộ nguồn** hoàn tất bình thường. Việc `cancel()` từ downstream có thể dừng phần xử lý chưa diễn ra; operator không thể bảo đảm thu hồi mọi tín hiệu đã ở trạng thái in-flight trong bối cảnh bất đồng bộ.

### Nguồn rỗng và đầu vào `null`

- `Flux.empty().map(f)` không gọi `f`, chỉ hoàn thành.
- `Mono.empty().map(f)` không tạo giá trị mặc định; dùng `defaultIfEmpty` hoặc `switchIfEmpty` khi nghiệp vụ cần một nhánh thay thế.
- Reactive Streams không cho phép `null` là phần tử `onNext`. Mapper trong Reactor trả `null` sẽ gây lỗi; không dùng `null` để biểu diễn “bỏ qua phần tử”.

Nếu mục tiêu là **loại bỏ** giá trị theo điều kiện, dùng `filter`. Nếu cần phép biến đổi có thể sinh không phần tử khi trả `null` và phiên bản Reactor hỗ trợ, cân nhắc `mapNotNull`; phải hiểu rõ ý nghĩa loại bỏ giá trị, khác `map` một-một.

## 7. So sánh `map`, `filter`, `flatMap`, `concatMap` và `doOnNext`

| Toán tử | Hàm đầu vào / ý nghĩa | Số phần tử đầu ra điển hình | Khi dùng |
|---|---|---|---|
| `map` | `T -> R` đồng bộ | Một kết quả mỗi `onNext` đầu vào nếu thành công | Chuẩn hóa trường, tính giá trị, entity → DTO |
| `filter` | `T -> boolean` | 0 hoặc 1 trên mỗi đầu vào | Giữ các phần tử thỏa điều kiện |
| `flatMap` | `T -> Publisher<R>` rồi gộp các publisher con | 0, 1 hoặc nhiều trên mỗi đầu vào | Gọi dịch vụ/repository trả `Mono` hoặc `Flux`, phối hợp thao tác bất đồng bộ |
| `concatMap` | `T -> Publisher<R>`, ghép các inner publisher **theo thứ tự** | 0, 1 hoặc nhiều | Cần giữ thứ tự xử lý/phát theo nguồn |
| `doOnNext` | Hàm quan sát `Consumer<T>` | Không nhằm biến đổi giá trị | Log, đo đạc, quan sát tín hiệu; tránh dùng cho nghiệp vụ có side effect khó kiểm soát |

Ví dụ một API trả `Mono<UserDto>` cho mỗi ID:

```java
Flux<Mono<UserDto>> nested = userIds
        .map(id -> userService.findDtoById(id));
```

Đây là **mã minh họa có các biến/dịch vụ phụ thuộc ứng dụng**, không phải chương trình chạy độc lập. Nếu `findDtoById` trả `Mono<UserDto>`, dùng `map` tạo **Flux chứa các Mono** (`Flux<Mono<UserDto>>`), thường không phải dữ liệu mà client mong đợi. Khi cần gộp kết quả thành một `Flux<UserDto>` thực sự, dùng:

```java
Flux<UserDto> users = userIds
        .flatMap(id -> userService.findDtoById(id));
```

`flatMap` có thể xử lý nhiều inner publisher theo kiểu xen kẽ và không giữ thứ tự phát đầu vào trong mọi trường hợp. Khi yêu cầu **đúng thứ tự**, cân nhắc `concatMap`. Việc mapper trả lại một `Publisher` là dấu hiệu quan trọng để chọn `flatMap`/`concatMap` thay cho `map`.

Ngược lại, `user -> new UserDto(user.id(), user.name())` trả trực tiếp DTO, vậy dùng `map` là đúng. Không cần dùng `flatMap(id -> Mono.just(id * 2))` chỉ để thực hiện một phép tính đồng bộ.

## 8. Lỗi triển khai thường gặp

### 8.1. Không gán hoặc không dùng Publisher mới

```java
Flux<Integer> source = Flux.just(1, 2, 3);
source.map(n -> n * 10); // Tạo pipeline mới rồi bỏ đi.
source.subscribe(System.out::println); // Vẫn in 1, 2, 3.
```

`map` không sửa tại chỗ `source`; nó trả về Publisher mới với logic biến đổi được lắp thêm. Phải dùng pipeline trả về:

```java
Flux<Integer> mapped = source.map(n -> n * 10);
mapped.subscribe(System.out::println); // In 10, 20, 30.
```

### 8.2. Chặn luồng bên trong mapper

```java
// Phản ví dụ: không gọi I/O blocking tùy tiện trong map.
Flux<User> result = ids.map(id -> blockingClient.loadUser(id));
```

Nếu `blockingClient.loadUser` chờ mạng/database, nó có thể làm nghẽn thread xử lý tín hiệu, đặc biệt khi có event loop của WebFlux. Nếu thư viện cung cấp API non-blocking trả `Mono<User>`, thông thường chọn `flatMap`. Nếu phải tích hợp thư viện blocking, cần cân nhắc bọc công việc thành Publisher và phân lịch phù hợp, chẳng hạn `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, rồi kết hợp qua `flatMap`, đồng thời quản lý số tác vụ đồng thời và tải hệ thống. **Đừng dùng `map` để làm phép tính bất đồng bộ bằng cách trả `Mono` rồi quên giải phẳng.**

### 8.3. Mapper chứa side effect không kiểm soát

```java
Flux<Integer> results = Flux.just(1, 2)
        .map(n -> {
            auditList.add(n); // Side effect phụ thuộc subscription.
            return n * 2;
        });
```

Với một Publisher cold, mỗi lượt subscribe có thể khiến mapper chạy lại, làm side effect lặp. Đồng thời, khi pipeline đổi scheduler hoặc có nhiều subscription, trạng thái dùng chung có thể có rủi ro đồng thời. Ưu tiên mapper **thuần** (cùng đầu vào, cùng kết quả, không sửa trạng thái ngoài). Dùng `doOnNext` để quan sát/log và xử lý side effect nghiệp vụ bằng thiết kế rõ ràng về lỗi, retry, idempotency.

### 8.4. Trả `null` hoặc nuốt lỗi

```java
Flux<String> invalid = Flux.just("A", "B")
        .map(s -> s.equals("B") ? null : s);
```

Đây là **phản ví dụ**: khi đến `"B"`, mapper trả `null` và Reactor kết thúc chuỗi với lỗi. Nếu muốn bỏ `"B"`, dùng `filter(s -> !s.equals("B"))` hoặc lựa chọn toán tử lọc/chuyển đổi phù hợp, không đẩy `null` xuống downstream.

### 8.5. Nhầm `map` với `Stream.map` của Java

Cả `java.util.stream.Stream.map` và `reactor.core.publisher.Flux.map` nhận một `Function`, nhưng cơ chế thực thi khác nhau. Java Stream là API xử lý tập/luồng dữ liệu theo terminal operation của Stream; Reactor Publisher thực hiện giao thức subscription, demand, completion/error và có khả năng phối hợp nguồn bất đồng bộ. Không suy luận tất cả hành vi về threading, lỗi hay backpressure của Reactor từ `Stream.map`.

## 9. Áp dụng trong Spring WebFlux

Một controller WebFlux có thể trả `Flux` chứa giá trị đã chuyển đổi:

```java
// Đoạn minh họa bên trong ứng dụng Spring WebFlux có dependencies/imports.
@RestController
class PriceController {
    @GetMapping("/prices")
    public Flux<String> prices() {
        return Flux.just(100, 200, 300)
                .map(price -> "VND " + price);
    }
}
```

Ở ví dụ này, mapper chỉ chuyển `Integer` thành `String` một cách đồng bộ và nhanh. Spring WebFlux giữ trách nhiệm subscribe, xử lý response/error/cancellation theo ngữ cảnh HTTP. Không cần tự gọi `subscribe()` trong controller để lấy kết quả rồi trả một danh sách được thay đổi thủ công.

Trong ứng dụng có repository reactive, mẫu thường gặp là:

```java
// Minh họa phụ thuộc các kiểu UserEntity, UserDto và userRepository của dự án.
Mono<UserDto> response = userRepository.findById(id)
        .map(entity -> new UserDto(entity.getId(), entity.getName()));
```

`findById(id)` trả `Mono<UserEntity>` thì `map` trả `Mono<UserDto>` với cùng trạng thái: không có kết quả vẫn là empty, lỗi upstream vẫn là lỗi, có entity thì biến thành DTO. Mapper chuyển object trong bộ nhớ, không truy vấn dữ liệu lần hai.

## 10. Tự kiểm tra

**Câu 1.** `Flux.just(2, 4).map(n -> n + 1).map(n -> n * 3)` phát gì?

Kết quả: `9`, `15`. Với mỗi phần tử, mapper thứ nhất chạy trước mapper thứ hai; số phần tử không đổi.

**Câu 2.** `Mono.empty().map(value -> expensiveCalculation(value))` có chạy hàm `expensiveCalculation` không?

Không. Nguồn không phát `onNext` nên không có phần tử để đưa vào mapper.

**Câu 3.** `map(id -> service.fetch(id))` khác `flatMap(id -> service.fetch(id))` như thế nào khi `fetch` trả `Mono<Result>`?

`map` tạo phần tử kiểu `Mono<Result>` (ví dụ `Flux<Mono<Result>>` nếu nguồn là Flux); `flatMap` đăng ký/ghép inner Publisher để downstream trực tiếp nhận `Result` và điều phối tín hiệu/error/demand của chúng.

**Câu 4.** `map` có tự đưa tính toán lên thread khác hoặc cho phép gửi phần tử bất chấp demand không?

Không. `map` là phép biến đổi đồng bộ ở thời điểm nhận tín hiệu; nó vẫn nằm trong giao thức reactive và việc chuyển scheduler phải được cấu hình riêng khi cần.

**Ghi nhớ:** chọn **`map` khi chuyển từng `T` thành một `R` bằng thao tác nhanh, đồng bộ, không-null**; sử dụng kết quả Publisher mà `map` trả về; để nguồn và Reactor quản lý subscription/demand; dùng toán tử khác khi cần lọc, phát nhiều phần tử hoặc kết hợp tác vụ bất đồng bộ.
