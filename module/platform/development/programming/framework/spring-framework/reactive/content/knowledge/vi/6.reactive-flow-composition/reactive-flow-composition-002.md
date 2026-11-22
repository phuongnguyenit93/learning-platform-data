# `zip` để ghép giá trị tương ứng từ nhiều nguồn trong Project Reactor

## 1. Bài toán và ý tưởng cốt lõi

Trong Spring WebFlux, một response có thể cần thông tin từ **nhiều nguồn độc lập**: hồ sơ người dùng và số đơn hàng, mã sản phẩm và tồn kho, hoặc dữ liệu từ nhiều API. Project Reactor cung cấp toán tử **`zip`** để **chờ mỗi nguồn cung cấp một giá trị**, rồi kết hợp các giá trị tương ứng thành **một kết quả**.

Với `Flux`, “tương ứng” nghĩa là **thứ tự xuất hiện trong từng luồng**, không phải thời điểm phát, khóa nghiệp vụ hay timestamp.

```text
Flux A:     A1 ------- A2 -------- A3
Flux B:          B1 -------- B2
                        |
zip(A, B): (A1, B1) -- (A2, B2) -- complete
```

Hình trên chỉ minh họa sự ghép **theo vị trí** (phần tử thứ 1 với thứ 1, thứ 2 với thứ 2), không phải lịch thực thi thực tế. Khi một nguồn hết và không còn khả năng tạo nhóm đủ phần tử, `zip` hoàn tất. Trong ví dụ, `A3` không xuất hiện ở kết quả.

`zip` thích hợp khi:

- Mỗi dữ liệu đầu ra cần **đồng thời đủ một giá trị từ mỗi nguồn**.
- Các nguồn phát dữ liệu theo **thứ tự có ý nghĩa tương ứng với nhau**, hoặc mỗi nguồn là một `Mono` (tối đa một giá trị).
- Muốn tạo `Tuple` hoặc DTO mới từ các giá trị đã có.
- Cần kết hợp các lời gọi reactive `Mono` độc lập mà không tự `block()` để lấy từng giá trị.

Điểm đặc biệt: `zip` **không phải** phép ghép dữ liệu bằng khóa (`join`), **không phải** nối hai danh sách (`concat`) và cũng **không phát ngay mỗi khi bất kỳ nguồn nào có phần tử** (`merge`, `combineLatest` có ngữ nghĩa khác).

## 2. Các hình thức sử dụng

Reactor có `Flux.zip(...)`, `Mono.zip(...)` và toán tử instance `zipWith(...)`. Có thể đọc các cách gọi sau như **đoạn mã minh họa** trong lớp Java đã import `Flux`, `Mono` và kiểu dữ liệu liên quan:

### `Flux.zip`: ghép nhiều phần tử theo chỉ số

```java
Flux<String> names = Flux.just("An", "Binh", "Chi");
Flux<Integer> ages = Flux.just(21, 25, 30);

Flux<reactor.util.function.Tuple2<String, Integer>> rows =
        Flux.zip(names, ages);
```

Khi có subscriber, các cặp kết quả là:

```text
(An, 21)
(Binh, 25)
(Chi, 30)
```

`Tuple2<String,Integer>` có hai phương thức `getT1()` và `getT2()` để đọc phần tử thứ nhất và thứ hai. Với ba nguồn, kết quả là `Tuple3<T1,T2,T3>` và có thêm `getT3()`; Reactor có các dạng Tuple lớn hơn, nhưng tên vị trí dễ kém rõ nghĩa khi business logic phức tạp.

### Truyền hàm kết hợp thay vì giữ Tuple

```java
Flux<String> labels = Flux.zip(
        Flux.just("Pen", "Book"),
        Flux.just(10, 5),
        (name, stock) -> name + ": " + stock
);
```

Kết quả là `Pen: 10` và `Book: 5`. BiFunction `(name, stock) -> ...` chỉ chạy khi toán tử đã có đủ một phần tử từ **cả hai nguồn**. Dùng combinator giúp nhận trực tiếp `Flux<R>` thay vì `Flux<Tuple2<...>>`.

### `Mono.zip`: ghép các kết quả đơn lẻ

```java
Mono<String> name = Mono.just("An");
Mono<Integer> score = Mono.just(95);

Mono<String> summary =
        Mono.zip(name, score, (n, s) -> n + " đạt " + s);
```

Nếu hai `Mono` đều phát giá trị, `summary` phát **một** chuỗi `An đạt 95` rồi hoàn tất. Nếu **một nguồn hoàn tất rỗng**, không có đủ giá trị để kết hợp nên `Mono.zip` cũng hoàn tất rỗng (không phát `onNext`). Nếu có nguồn báo lỗi trước khi kết quả được hoàn thành, toán tử zip thông thường phát lỗi.

### `zipWith`: ghép từ một Publisher hiện có

```java
Flux<String> labels = Flux.just("A", "B")
        .zipWith(Flux.just(1, 2),
                (letter, number) -> letter + number);
// A1, B2
```

`zipWith` hữu ích khi viết pipeline theo từng bước; ý nghĩa ghép theo vị trí tương đương cách gọi `Flux.zip` hai nguồn. `Mono` cũng hỗ trợ `zipWith` theo mẫu tương tự.

## 3. Cơ chế hoạt động qua các tín hiệu Reactive Streams

**Giả sử** hai nguồn `Flux` phát:

```text
Publisher P -> p1, p2, p3
Publisher Q -> q1, q2

Downstream subscribe(zip(P, Q))
   |
   +-- zip đăng ký các nguồn upstream
   +-- zip quản lý nhu cầu nhận (request/demand) và bộ đệm nội bộ
   +-- khi có đủ p1 + q1 -> onNext((p1, q1))
   +-- khi có đủ p2 + q2 -> onNext((p2, q2))
   +-- Q đã kết thúc, không thể tạo cặp thứ ba -> onComplete()
```

Các điểm kỹ thuật cần hiểu chính xác:

1. **Một lượt phát kết quả cần một phần tử từ mỗi nguồn.** Nguồn nhanh có thể phải chờ nguồn chậm; zip có thể đệm dữ liệu đang chờ ghép.
2. **Tôn trọng backpressure của downstream.** Nếu subscriber chưa yêu cầu kết quả thì zip không được phát `onNext` vượt demand. Tuy nhiên, zip có thể yêu cầu upstream theo đợt (prefetch) và giữ phần tử trong queue nội bộ; đừng suy luận `request(1)` downstream luôn bằng chính xác một lần `request(1)` ở *mỗi* nguồn.
3. **Chỉ phát tuple khi đủ giá trị.** Một giá trị của P đến trước không tự biến thành tuple; phải chờ giá trị của Q ở vị trí tương ứng.
4. **Hoàn tất khi không thể có cặp tiếp theo.** Nếu một nguồn đã kết thúc và không còn phần tử chưa ghép, zip hoàn tất và hủy các upstream không còn cần thiết. Không có chính sách tự thêm `null`/giá trị mặc định để kéo dài tới độ dài của nguồn lớn nhất.
5. **Error propagation.** Với `zip` thông thường, lỗi upstream kết thúc kết quả bằng `onError` và các nguồn khác được hủy theo cơ chế xử lý lỗi; không có tuple “một nửa”. Một số API `zipDelayError` có chính sách hoãn báo lỗi khác và cần được chọn có chủ đích.
6. **Subscription và execution:** các Publisher nguồn có thể được đăng ký và thực thi đồng thời về mặt bất đồng bộ nếu chúng sử dụng nền tảng non-blocking thích hợp; bản thân `zip` không tự tạo thread hay bảo đảm mọi nguồn chạy song song.

Lưu ý hai luồng có cùng số phần tử nhưng đến ở thời gian khác nhau vẫn ghép **đúng vị trí**, nếu các phần tử vẫn còn trong luồng theo hợp đồng của nguồn:

```text
Names:     N1 ------- N2 ------- N3
Balances:        B1 - B2 ---------------- B3
Result:    (N1,B1), (N2,B2), (N3,B3)
```

Không dùng `zip` để “khớp bản ghi gần timestamp nhất” hoặc tự phát hiện ID không trùng nhau. Với dữ liệu cần ghép theo `userId`, `orderId`, cần thiết kế join/lookup theo khóa, hoặc biến đổi nguồn để thứ tự và khóa được xác thực trước khi zip.

## 4. Khi nguồn dài ngắn khác nhau hoặc rỗng

### `Flux.zip` hoàn tất theo nguồn giới hạn

```java
Flux<String> products = Flux.just("Pen", "Book", "Bag");
Flux<Integer> prices = Flux.just(10, 20);

Flux<String> rows = Flux.zip(products, prices,
        (product, price) -> product + "=" + price);
```

Khi đăng ký, downstream nhận `Pen=10`, `Book=20`, sau đó `onComplete`. Không có dòng `Bag=...` vì không tồn tại giá tương ứng. Tuy nhiên, **không thể kết luận phần tử thứ ba chắc chắn chưa được đọc/đệm bên trong upstream**; chính sách prefetch có thể khác. Hợp đồng chỉ bảo đảm kết quả được ghép đúng.

### `Mono.zip` với một nguồn rỗng

```java
Mono<String> profile = Mono.just("An");
Mono<Integer> count = Mono.empty();

Mono<String> result = Mono.zip(
        profile, count, (p, n) -> p + ": " + n);
```

`result` hoàn tất mà **không có `onNext`**. Hàm `(p, n) -> ...` không được gọi; phép zip không tự thay `count` bằng `0`.

Nếu giá trị mặc định `0` là đúng theo nghiệp vụ, có thể chủ động áp dụng:

```java
Mono<String> result = Mono.zip(
        profile,
        count.defaultIfEmpty(0),
        (p, n) -> p + ": " + n
);
```

Khi đó kết quả là `An: 0`. Không lạm dụng default để che lỗi dữ liệu thiếu: phân biệt “không có số liệu nghĩa là 0” với “chưa tìm thấy dữ liệu nhưng cần trả 404/lỗi”.

**Chi tiết quan trọng về subscription:** nếu một nguồn `Mono` hoàn tất rỗng một cách đồng bộ, `Mono.zip` có thể chấm dứt sớm và không subscribe vào mọi nguồn còn lại. Vì vậy, các side effect được gắn vào `doOnSubscribe` trên những nguồn khác **không được bảo đảm đều chạy**. Nếu thật sự cần quan sát trạng thái của từng nguồn, hãy xét thiết kế riêng như `singleOptional()` trên mỗi Mono trước khi zip; lúc đó kết quả chứa `Optional` và phải tự xử lý trường hợp `Optional.empty()`:

```java
Mono<reactor.util.function.Tuple2<
        java.util.Optional<String>,
        java.util.Optional<Integer>>> pair =
        Mono.zip(
                Mono.just("An").singleOptional(),
                Mono.<Integer>empty().singleOptional()
        );
```

Đây là cách **thay đổi kiểu kết quả để biểu diễn sự vắng mặt**; không biến dữ liệu thiếu thành một `onNext(null)`.

### `Flux.empty` và các nguồn nóng

Nếu một `Flux` hoàn tất mà không phát phần tử nào, `Flux.zip` không thể tạo bất kỳ nhóm nào, nên kết quả hoàn tất rỗng. Với **hot Publisher**, có thể đã có giá trị phát *trước khi* zip đăng ký; những giá trị ấy có thể không được replay, tùy loại nguồn. Do đó không coi zip như cơ chế lịch sử có thể khôi phục các sự kiện đã bỏ lỡ.

## 5. Chạy thử bằng Java 17+ và Project Reactor

Ví dụ dưới đây dùng các nguồn **cold, đồng bộ, hữu hạn** nên stdout theo thứ tự ổn định. Có cả kết hợp hai nguồn với DTO, `Mono.zip`, ba nguồn với `Tuple3`, và trường hợp một `Mono` rỗng. Không cần ứng dụng Spring Boot để chạy bài minh họa.

Cấu trúc tệp:

```text
reactor-zip-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-zip-demo</artifactId>
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

Nội dung `src/main/java/demo/Main.java`:

```java
package demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class Main {
    record Inventory(String name, int stock) {}

    public static void main(String[] args) {
        // 1) Hai Flux: phần tử tương ứng -> DTO bất biến.
        Flux<Inventory> inventory = Flux.zip(
                Flux.just("Pen", "Book", "Eraser"),
                Flux.just(12, 5),
                Inventory::new
        );

        inventory.subscribe(
                item -> System.out.println(
                        "item: " + item.name() + "/" + item.stock()),
                error -> System.out.println("error: " + error.getMessage()),
                () -> System.out.println("inventory complete")
        );

        // 2) Hai Mono: một kết quả tổng hợp.
        Mono<String> summary = Mono.zip(
                Mono.just("An"),
                Mono.just(3),
                (name, orders) -> name + " has " + orders + " orders"
        );

        summary.subscribe(value -> System.out.println("mono: " + value));

        // 3) Ba nguồn: Reactor trả Tuple3.
        Flux.zip(
                Flux.just("A", "B"),
                Flux.just(1, 2),
                Flux.just(true, false)
        ).subscribe(t -> System.out.println(
                "triple: " + t.getT1() + "/" + t.getT2()
                        + "/" + t.getT3()
        ));

        // 4) Một Mono rỗng: zip hoàn tất không có onNext.
        Mono.zip(
                Mono.just("value"),
                Mono.<Integer>empty()
        ).subscribe(
                tuple -> System.out.println("unexpected tuple: " + tuple),
                error -> System.out.println("empty error: " + error),
                () -> System.out.println("empty zip complete")
        );
    }
}
```

Từ thư mục `reactor-zip-demo/`, cài JDK 17+ và Maven rồi chạy:

```bash
mvn -q compile exec:java
```

Stdout do **chương trình** in (không tính log của Maven nếu môi trường có cấu hình riêng):

```text
item: Pen/12
item: Book/5
inventory complete
mono: An has 3 orders
triple: A/1/true
triple: B/2/false
empty zip complete
```

**Đọc kết quả:**

1. `Inventory::new` kết hợp **một tên** và **một lượng tồn kho** thành một `Inventory`. Nguồn tên có ba giá trị, nguồn số lượng có hai; zip chỉ phát hai bản ghi rồi kết thúc.
2. `Mono.zip` phát đúng một chuỗi mô tả vì cả hai `Mono` đều có giá trị.
3. `Flux.zip` ba nguồn sinh `Tuple3<String,Integer,Boolean>`; vị trí `T1`, `T2`, `T3` tương ứng với thứ tự tham số khi gọi zip.
4. `Mono.empty()` khiến phép zip cuối không phát tuple; chỉ gọi callback `onComplete`.
5. Không gọi `.block()` trong pipeline và không phải tự `subscribe` từng nguồn đầu vào. `zip` chịu trách nhiệm đăng ký/ghép các publisher nguồn khi có subscription từ kết quả.

## 6. Dùng `Mono.zip` trong dịch vụ Spring WebFlux

Tình huống: một endpoint cần hồ sơ người dùng và tổng số ticket còn mở. Giả sử hai repository đã hỗ trợ API **reactive, non-blocking**:

- `profileRepository.findById(id)` trả `Mono<Profile>`.
- `ticketRepository.countOpenByUserId(id)` trả `Mono<Long>`.

Có thể ghép thành một DTO theo cách **minh họa bên trong service hiện có**:

```java
record UserDashboard(Profile profile, long openTickets) {}

Mono<UserDashboard> dashboard(long id) {
    Mono<Profile> profileMono = profileRepository.findById(id);
    Mono<Long> countMono = ticketRepository.countOpenByUserId(id);

    return Mono.zip(profileMono, countMono, UserDashboard::new);
}
```

Các kiểu `Profile`, hai repository và phương thức chứa code là **phụ thuộc ứng dụng**, nên đoạn trên không phải chương trình chạy độc lập. Ý tưởng:

1. Service tạo hai nguồn và trả một `Mono<UserDashboard>`.
2. Khi framework đăng ký kết quả, zip đăng ký/điều phối hai nguồn. Hai truy vấn có thể tiến triển đồng thời nếu các nguồn được triển khai thực sự bất đồng bộ và không bị ràng buộc phụ thuộc nhau.
3. Zip chờ `Profile` **và** `Long` rồi gọi constructor `UserDashboard::new`.
4. Nếu một nguồn lỗi, kết quả thông thường lỗi; nếu một nguồn rỗng, kết quả rỗng. Hãy định nghĩa rõ xử lý hai trạng thái này theo nghiệp vụ.
5. Spring WebFlux thường là bên đăng ký Publisher khi controller trả `Mono<UserDashboard>`. Controller/service không cần tự gọi `.subscribe()` hoặc `.block()` để lấy giá trị.

Ví dụ bổ sung nếu **profile thiếu phải là 404**, còn **count thiếu hợp lệ là 0**:

```java
Mono<Profile> profileMono = profileRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Profile not found"
                )
        ));

Mono<Long> countMono = ticketRepository.countOpenByUserId(id)
        .defaultIfEmpty(0L);

Mono<UserDashboard> result =
        Mono.zip(profileMono, countMono, UserDashboard::new);
```

Đây là mã minh họa trong ứng dụng WebFlux với import phù hợp cho `ResponseStatusException` (`org.springframework.web.server`) và `HttpStatus` (`org.springframework.http`). Nó biểu diễn chính sách dữ liệu thiếu **ở từng nguồn trước khi zip**, giúp kết quả không bị rỗng một cách khó giải thích.

**Chú ý:** `zip` chỉ điều phối các Publisher đã nhận. Nếu `profileRepository.findById` có side effect ngay khi **gọi phương thức để tạo Mono**, side effect đó không trở nên lazy chỉ nhờ `zip`; khả năng lazy phụ thuộc implementation của nguồn.

## 7. `zip` không giải quyết mọi kiểu ghép luồng

### `zip` và `merge`

```java
Flux<Integer> merged =
        Flux.merge(Flux.just(1, 2), Flux.just(10, 20));
```

`merge` phát **từng phần tử của các nguồn** vào một luồng chung; nó không tạo `(1,10)` hay `(2,20)`. Khi các nguồn bất đồng bộ, thứ tự xen kẽ có thể khác giữa các lần chạy. `zip` chỉ phát sau khi đủ phần tử tương ứng từ **mọi nguồn**.

### `zip` và `concat`

`concat` hoàn tất nguồn trước rồi mới nối tiếp nguồn sau, bảo toàn tính tuần tự theo các nguồn. Dùng khi muốn **nối chuỗi**, không muốn tạo nhóm giá trị.

### `zip` và `combineLatest`

Với các nguồn phát nhiều lần, `combineLatest` sau khi mỗi nguồn từng có ít nhất một phần tử sẽ tính lại kết quả **mỗi khi một nguồn có giá trị mới**, sử dụng giá trị *mới nhất* từ các nguồn còn lại. Trái lại, `zip` tiêu thụ một giá trị từ **mỗi nguồn cho mỗi kết quả**. Ví dụ đầu ra dạng “trạng thái dashboard mới nhất” có thể phù hợp với `combineLatest` hơn; dữ liệu thành từng cặp tương ứng theo index phù hợp với `zip`.

### `zip` và `flatMap`

`flatMap` biến **từng giá trị từ một nguồn** thành một Publisher con rồi gộp các kết quả; `zip` kết hợp **những Publisher độc lập** theo vị trí. Ví dụ mỗi ID cần gọi API chi tiết:

```java
// Minh họa: findDetails(id) trả Mono<Details>.
Flux<Details> details = ids.flatMap(id -> service.findDetails(id));
```

Nếu dùng `zip(ids, details)` một cách máy móc trong khi `flatMap` có thể đổi thứ tự hoàn thành, ID và chi tiết có nguy cơ **không đúng cặp**. Thay vào đó, giữ ID đi cùng kết quả trong từng inner Publisher hoặc dùng giải pháp bảo toàn khóa/thứ tự phù hợp.

### `zipWhen`: nguồn thứ hai phụ thuộc giá trị của nguồn đầu

Trong `Mono`, khi cần tạo **Mono thứ hai sau khi nhận kết quả thứ nhất**, có thể dùng `zipWhen`:

```java
// Minh họa: loadSettings(user.id()) trả Mono<Settings>.
Mono<UserView> view = userService.findById(id)
        .zipWhen(
                user -> settingsService.loadSettings(user.id()),
                (user, settings) -> new UserView(user, settings)
        );
```

`zipWhen` giữ một giá trị từ `Mono` ban đầu và gọi hàm tạo nguồn thứ hai dựa trên giá trị đó. Phân biệt với `Mono.zip(a, b)`: hai nguồn đã có thể được chuẩn bị độc lập; `zipWhen` thích hợp với **phụ thuộc dữ liệu**. Nếu Mono đầu rỗng, hàm tạo Mono thứ hai không được gọi.

## 8. Lỗi và những giới hạn hay gặp

| Lỗi/nhầm lẫn | Hậu quả | Cách xử lý |
|---|---|---|
| Ghép hai luồng nghiệp vụ theo index khi record phải khớp theo ID | Ghép sai người với đơn hàng nếu dữ liệu khác thứ tự hoặc thiếu phần tử | Tra cứu theo khóa, sắp xếp/kiểm tra khóa một cách có chủ đích, hoặc giữ khóa trong cùng Publisher |
| Một nguồn `Mono.empty()` nhưng tưởng zip vẫn phát DTO | Không có `onNext`, khiến nhánh ánh xạ DTO không chạy | Dùng `defaultIfEmpty`, `switchIfEmpty` hoặc mô hình `Optional` tùy nghiệp vụ |
| Một nguồn `Flux` ngắn hơn nhưng mong các phần tử dư được phát riêng | Zip hoàn tất khi không còn nhóm đủ phần tử | Chọn phép ghép khác hoặc bổ sung chính sách giá trị thiếu trước zip |
| Dùng `zip` để đồng bộ theo timestamp | Ghép theo vị trí chứ không theo thời gian | Thiết kế window/join theo key hoặc thời gian nếu cần |
| Chứa thao tác `block()` ở nguồn hay combinator | Chặn thread xử lý tín hiệu; nguy cơ nghẽn event loop WebFlux | Dùng Publisher từ I/O non-blocking, phối hợp bằng `zip`, xử lý thư viện blocking có lịch thực thi riêng phù hợp |
| Cho rằng `zip` tự tạo thread song song | Không có bảo đảm như vậy; phụ thuộc upstream, scheduler và nguồn | Đo/thiết kế execution context cụ thể, không suy luận từ tên operator |
| Giả định mỗi downstream `request(1)` tạo đúng một upstream `request(1)` | Bỏ qua prefetch và queue nội bộ | Dựa vào hợp đồng kết quả và cấu hình nhu cầu, giám sát bộ đệm khi tải cao |
| Chỉ dựa vào `doOnSubscribe` để bắt buộc mọi nguồn đều chạy | Mono rỗng đồng bộ có thể làm zip dừng trước khi subscribe hết | Tránh dựa vào side effect lúc subscribe; cân nhắc `singleOptional` hoặc thiết kế thu thập riêng |
| Không xử lý lỗi nguồn | Toàn bộ zip bình thường kết thúc bằng `onError` | Xác định lỗi cần truyền, retry có giới hạn hay fallback theo nguồn |

Một lỗi khác là tạo **lồng Publisher** bằng cách zip rồi dùng combinator trả `Mono`:

```java
// Minh họa: service.enrich(a, b) trả Mono<Result>.
Mono<Mono<Result>> nested =
        Mono.zip(sourceA, sourceB,
                (a, b) -> service.enrich(a, b));
```

Nếu downstream cần `Mono<Result>`, có thể giải phẳng:

```java
Mono<Result> flat =
        Mono.zip(sourceA, sourceB)
                .flatMap(t -> service.enrich(t.getT1(), t.getT2()));
```

Những đoạn ở đây minh họa kiểu trả về và cần biến `sourceA`, `sourceB`, `service`, `Result` trong dự án. `zip` **không tự subscribe** vào Mono được trả về từ combinator. Chọn toán tử đúng với kiểu dữ liệu mong muốn ở mỗi bước.

## 9. Bài tập tự kiểm tra

**Bài 1.** `Flux.zip(Flux.just("A", "B", "C"), Flux.just(1, 2))` phát bao nhiêu kết quả, gồm những giá trị nào?

**Đáp án:** Hai tuple: `("A", 1)` và `("B", 2)`; phần `"C"` không có đối tác nên không xuất hiện ở kết quả. Không có phần tử null được tự chèn vào.

**Bài 2.** `Mono.zip(Mono.just("ok"), Mono.empty())` có gọi `onNext` không?

**Đáp án:** Không. Không đủ hai phần tử; zip hoàn tất rỗng, không phát tuple.

**Bài 3.** Một `Flux` phát số 1 rồi số 2 rất nhanh; `Flux` khác phát `"X"` rồi `"Y"` chậm hơn. Zip ghép `1` với giá trị nào?

**Đáp án:** Với `"X"` (phần tử thứ nhất), không phụ thuộc chênh lệch thời gian. Kết quả thứ hai là `(2,"Y")` nếu cả hai nguồn phát đủ và không có lỗi/hủy.

**Bài 4.** Tại sao `zip(userIds, getDetailsViaFlatMap(userIds))` có thể nguy hiểm?

**Đáp án:** Kết quả `flatMap` có thể đến khác thứ tự ban đầu; zip ghép theo **chỉ số phần tử nhận**, không kiểm tra `userId`. Giải pháp là giữ khóa và giá trị trong cùng quá trình bất đồng bộ, hoặc ghép theo key.

**Bài 5.** Khi nào chọn `Mono.zip` thay cho `flatMap`?

**Đáp án:** Khi hai hay nhiều nguồn độc lập đã tồn tại và chỉ cần kết hợp kết quả của chúng, `Mono.zip` diễn đạt rõ mục đích. Nếu nguồn sau **phụ thuộc giá trị** từ nguồn trước, dùng `flatMap` hoặc `zipWhen` thường rõ ràng hơn.

**Ghi nhớ:** `zip` ghép **một phần tử từ mỗi Publisher theo thứ tự**, phát kết quả khi đủ giá trị, hoàn tất khi không thể có nhóm tiếp theo, và giữ hợp đồng demand/lỗi/hủy của reactive stream. Với Spring WebFlux, `Mono.zip` rất hữu ích để tổng hợp những kết quả reactive độc lập thành DTO, miễn là hiểu rõ **empty, error, tính độc lập và ý nghĩa ghép theo vị trí**.
