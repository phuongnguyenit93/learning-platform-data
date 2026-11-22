# Ảnh hưởng của nguồn `empty` hoặc `Mono<Void>` trong `zip` (Spring WebFlux / Reactor)

## 1. Quy tắc cốt lõi: zip cần **một giá trị từ mỗi nguồn**

Trong Project Reactor, `Mono.zip(a, b)`, `a.zipWith(b)` và `a.zipWhen(...)` dùng để **kết hợp các kết quả có giá trị**. Với `Mono`, mỗi nguồn phát tối đa một phần tử qua `onNext`; `zip` chỉ tạo tuple hoặc gọi hàm kết hợp khi **tất cả các nguồn liên quan đã phát được phần tử**. Một luồng hoàn tất thành công mà **không phát `onNext`** được gọi là `empty`.

Điều đó tạo ra một điểm dễ nhầm:

- `Mono.just("A")` phát giá trị `"A"` rồi hoàn tất: có dữ liệu để `zip` ghép.
- `Mono.<String>empty()` chỉ phát `onComplete`: **không có giá trị** để `zip` ghép.
- `Mono<Void>` là kiểu dùng để thông báo **hoàn tất hoặc lỗi của một thao tác**, không có phần tử dữ liệu bình thường; trong `zip`, nó được xem như một nguồn **không có giá trị**.
- Khi một nguồn kết thúc rỗng, `zip` thông thường **hoàn tất rỗng**; nó không gọi combinator và có thể **hủy những nguồn khác** đã bắt đầu. Điều này không phải là lỗi (không tự phát `onError`).
- Nếu một nguồn báo lỗi, `zip` thông thường phát lỗi và có thể hủy những nguồn còn lại. Lỗi và empty là **hai tín hiệu khác nhau**.

Hãy tách rõ **“hoàn tất thành công”** khỏi **“hoàn tất và có giá trị”**: `zip` đòi hỏi trường hợp thứ hai ở mỗi nguồn. Đây là hợp đồng của toán tử, không phải một lỗi đặc thù của Spring WebFlux.

## 2. Ví dụ bằng tín hiệu: vì sao hàm kết hợp không chạy?

### Hai Mono đều có giá trị

~~~text
Mono.just("An")  : onNext("An") ────── onComplete
Mono.just(20)    : onNext(20) ──────── onComplete
Mono.zip(...)    : onNext(("An", 20)) ─ onComplete
~~~

Hai nguồn cùng cung cấp phần tử, vì vậy `zip` tạo được `Tuple2<String, Integer>`, hoặc có thể gọi một `BiFunction` để tạo kết quả tùy ý.

### Một Mono hoàn tất rỗng

~~~text
Mono.empty()     : onComplete  (không có onNext)
Mono.just(20)    : có thể được subscribe hoặc bị bỏ qua/hủy tùy thời điểm
Mono.zip(...)    : onComplete  (không có onNext, không tạo tuple)
~~~

Không thể tạo tuple gồm `null` và `20`: Reactive Streams không cho phép dùng `null` làm phần tử `onNext`, và `zip` không tự thay một nguồn rỗng bằng giá trị mặc định.

### Một nguồn `Mono<Void>`

~~~text
save().then()    : chạy save, chỉ báo onComplete khi thành công
getProfile()     : dự kiến trả một Profile
Mono.zip(...)    : không có tuple, vì nguồn đầu không phát phần tử
~~~

Ví dụ `Mono<Void> save = repository.save(entity).then();` vẫn có thể thực sự lưu dữ liệu; việc **bỏ giá trị** là chủ ý của `then()`. Tuy nhiên, nếu ghép `save` với một nguồn khác bằng `zip`, nguồn `save` sẽ không bao giờ cung cấp giá trị để kết hợp.

**Lưu ý về đăng ký nguồn:** sau khi một nguồn hoàn tất rỗng, một số nhánh trong `zip` — đặc biệt với nguồn rỗng đồng bộ hoặc cấu trúc `zip` lồng nhau — có thể **chưa được subscribe**. Nếu đã được subscribe, chúng có thể bị cancel. Vì thế không được dựa vào `zip` để bảo đảm mọi thao tác phụ (lưu, gửi thông báo, ghi log, gọi API) đều chạy đến cùng.

## 3. Những toán tử liên quan và nguyên nhân mất giá trị

| Biểu thức / toán tử | Dữ liệu khi hoàn tất thành công | Tác động nếu làm nguồn cho `zip` |
| --- | --- | --- |
| `Mono.just("A")` | Một giá trị `"A"` | Có thể zip với nguồn khác cũng phát giá trị |
| `Mono.empty()` | Không có giá trị | Zip hoàn tất rỗng |
| `Mono<Void>` | Không có giá trị | Zip hoàn tất rỗng |
| `mono.then()` | Bỏ `onNext` trước đó; chỉ còn hoàn tất/lỗi | Không cung cấp giá trị cho zip |
| `mono.thenEmpty(other)` | Chỉ phát tín hiệu hoàn tất/lỗi | Không cung cấp giá trị cho zip |
| `mono.ignoreElement()` hoặc `flux.ignoreElements()` | Bỏ phần tử; chỉ còn hoàn tất/lỗi | Không cung cấp giá trị cho zip |
| `Mono.when(a, b)` | `Mono<Void>` chờ các publisher hoàn tất | Dùng làm nguồn zip vẫn rỗng |
| `mono.thenReturn("done")` | Phát `"done"` sau khi mono ban đầu hoàn tất thành công | Có thể zip nếu sentinel mang ý nghĩa đúng |
| `mono.defaultIfEmpty(fallback)` | Phát fallback nếu nguồn có kiểu `T` rỗng | Có thể zip với fallback |
| `mono.singleOptional()` | Phát một `Optional<T>`, kể cả `Optional.empty()` | Cho phép zip cả trường hợp nguồn gốc rỗng |

`Mono<Void>` là điểm đặc biệt: **không có giá trị `Void` hợp lệ để phát dưới dạng `onNext`**. Vì thế `Mono<Void>.defaultIfEmpty(...)` và `switchIfEmpty(...)` không thể tự tạo ra một phần tử kiểu `Void` khác `null` để zip; `null` không hợp lệ. Nếu cần một phần tử đại diện cho hoàn tất, phải **đổi kiểu** bằng `thenReturn(sentinel)` hoặc ánh xạ sang một kết quả kiểu có giá trị.

## 4. `zipWith` và `zipWhen` cũng có bẫy empty

Giả sử bạn viết:

~~~java
// Chỉ minh họa: process trả Mono<Void>.
Mono<Void> first = service.process("A");
Mono<Void> second = service.process("B");

first.zipWith(second, (a, b) -> "done")
     .subscribe(System.out::println);
~~~

Hàm `(a, b) -> "done"` **không chạy**, vì không có `a` hay `b` được phát ra. Cả việc dùng `Mono.zip(first, second)` cũng không khắc phục được; muốn **chờ hai công việc** thì dùng `Mono.when(first, second)`.

Với `zipWhen`, tham số thứ hai là một **hàm tạo Mono kế tiếp** dựa trên phần tử bên trái. Nếu bên trái rỗng, hàm đó **không được gọi**:

~~~java
Mono<String> id = Mono.empty();

Mono<?> result = id.zipWhen(value -> service.lookup(value));
~~~

`service.lookup` trong ví dụ chỉ là tên minh họa; đoạn này không phải chương trình độc lập. Để tạo `rightGenerator`, `zipWhen` cần `value` từ `id`. Không có `onNext(value)` thì không có lời gọi `lookup`. Ngược lại, nếu bên trái có giá trị nhưng Mono được tạo bên phải hoàn tất rỗng, toàn bộ `zipWhen` cũng hoàn tất rỗng.

**Quan trọng:** `zipWhen` không có nghĩa “chạy hàm sau khi bên trái hoàn tất”; nghĩa của nó là “khi bên trái **phát một giá trị**, dùng giá trị đó để tạo Mono khác rồi zip hai giá trị”.

## 5. Ví dụ Java 17+ có thể chạy: kết quả zip empty và cách khắc phục

Ví dụ sử dụng Reactor Core trực tiếp, không cần Spring Boot. Tạo cấu trúc:

~~~text
reactor-zip-empty/
├── pom.xml
└── src/main/java/ZipEmptyDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-zip-empty</artifactId>
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
~~~

File `src/main/java/ZipEmptyDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;

public class ZipEmptyDemo {
    public static void main(String[] args) {
        // 1) Hai nguồn có giá trị: tạo được kết quả.
        var both = Mono.zip(
            Mono.just("A"), Mono.just("B"),
            (left, right) -> left + "-" + right
        );
        System.out.println("zip values = " + both.blockOptional());

        // 2) Một nguồn empty: kết quả vẫn empty, không phát tuple.
        var oneEmpty = Mono.zip(
            Mono.<String>empty(), Mono.just("B"),
            (left, right) -> left + "-" + right
        );
        System.out.println("zip empty = " + oneEmpty.blockOptional());

        // 3) Không có giá trị bên trái: zipWhen không gọi rightGenerator.
        AtomicInteger calls = new AtomicInteger();
        var dynamic = Mono.<String>empty().zipWhen(left -> {
            calls.incrementAndGet();
            return Mono.just(left.length());
        });
        System.out.println("zipWhen = " + dynamic.blockOptional());
        System.out.println("right factory calls = " + calls.get());

        // 4) Mono<Void> hoàn tất không có dữ liệu để zip.
        Mono<Void> completedWithoutValue = Mono.empty();
        var withVoid = Mono.zip(completedWithoutValue, Mono.just(7));
        System.out.println("zip Mono<Void> = " + withVoid.blockOptional());

        // 5) Nguồn String rỗng: dùng giá trị fallback rõ nghĩa.
        var withFallback = Mono.zip(
            Mono.<String>empty().defaultIfEmpty("guest"),
            Mono.just("viewer"),
            (name, role) -> name + ":" + role
        );
        System.out.println("defaultIfEmpty = " + withFallback.blockOptional());

        // 6) Nguồn hoàn tất kiểu Void: tạo một giá trị SAU khi hoàn tất.
        var withCompletionValue = Mono.zip(
            completedWithoutValue.thenReturn("saved"),
            Mono.just("viewer"),
            (status, role) -> status + ":" + role
        );
        System.out.println("thenReturn = " + withCompletionValue.blockOptional());

        // 7) Hai thao tác chỉ cần hoàn tất: when thay cho zip.
        AtomicInteger writes = new AtomicInteger();
        AtomicInteger audits = new AtomicInteger();
        Mono<Void> write = Mono.fromRunnable(() -> {
            writes.incrementAndGet();
        });
        Mono<Void> audit = Mono.fromRunnable(() -> {
            audits.incrementAndGet();
        });
        Mono.when(write, audit).block();
        System.out.println("when counts = " + writes.get() + "," + audits.get());
    }
}
~~~

Từ thư mục `reactor-zip-empty`, dùng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ZipEmptyDemo
~~~

**Output do chương trình in** (có thể có thêm log Maven tùy môi trường):

~~~text
zip values = Optional[A-B]
zip empty = Optional.empty
zipWhen = Optional.empty
right factory calls = 0
zip Mono<Void> = Optional.empty
defaultIfEmpty = Optional[guest:viewer]
thenReturn = Optional[saved:viewer]
when counts = 1,1
~~~

Các lời gọi `blockOptional()` ở ví dụ chỉ để chương trình console hiển thị rõ **“có kết quả”** (`Optional[value]`) hoặc **“hoàn tất rỗng”** (`Optional.empty`). **Không dùng `block()`/`blockOptional()` trong đường xử lý của event loop WebFlux**; ở controller/service reactive, trả về `Mono` và để framework subscribe.

Phần `Mono.when(write, audit)` bảo đảm hai `Mono<Void>` hoàn tất thành công trước khi câu lệnh in số đếm chạy. Việc sắp xếp thứ tự hai callback trong môi trường bất đồng bộ không phải mục tiêu ví dụ; nếu công việc B **phải** bắt đầu sau A, dùng `A.then(B)`.

## 6. Chọn giải pháp theo mục đích thực sự

Không có một “cách sửa zip empty” phù hợp cho mọi nghiệp vụ. Cần hỏi: **muốn ghép giá trị, đợi hoàn tất, bắt buộc mọi nguồn được chạy, hay chạy theo thứ tự?**

### Trường hợp A — Một kết quả có thể vắng mặt, nhưng cần ghép với giá trị mặc định

Nếu nguồn có kiểu dữ liệu hữu ích, ví dụ `Mono<String>` có thể rỗng:

~~~java
Mono<String> displayName = findNameById(id);
Mono<String> locale = loadLocale();

Mono<String> label = Mono.zip(
    displayName.defaultIfEmpty("Guest"),
    locale,
    (name, region) -> name + "@" + region
);
~~~

Đây là đoạn minh họa trong một service có `findNameById` và `loadLocale` được triển khai, chưa phải chương trình độc lập. Nếu `displayName` rỗng, fallback `"Guest"` được **phát thành giá trị** và `zip` có thể tạo label, miễn là `locale` cũng phát giá trị.

Có thể dùng `switchIfEmpty(Mono.just("Guest"))` khi cần fallback từ một publisher khác. Chỉ đặt fallback khi hợp đồng nghiệp vụ cho phép; **không tự chế một tên hoặc đối tượng hợp lệ giả** để che giấu dữ liệu bị thiếu. Nếu thiếu dữ liệu là lỗi, có thể chọn `switchIfEmpty(Mono.error(new IllegalArgumentException("missing name")))` để phát lỗi rõ ràng.

### Trường hợp B — Phải phân biệt “có dữ liệu” và “không có dữ liệu”

Dùng `singleOptional()` để biểu diễn cả hai tình huống bằng **một giá trị `Optional<T>`**. Khi đó bản thân mỗi nguồn mới luôn phát **một Optional**, kể cả `Optional.empty()`.

~~~java
// Ví dụ có Reactor dependency, không phải class chạy độc lập.
Mono<String> first = Mono.empty();
Mono<Integer> second = Mono.just(42);

Mono<String> combined = Mono.zip(
    first.singleOptional(),
    second.singleOptional(),
    (a, b) -> "first=" + a + ", second=" + b
);
// combined phát: "first=Optional.empty, second=Optional[42]"
~~~

`singleOptional()` đặc biệt hữu ích khi **cần tất cả nguồn được subscribe** nhưng một nguồn có thể rỗng. FAQ của Reactor lưu ý: với `zip` lồng nhau, nguồn rỗng sớm có thể khiến một số nguồn khác không được subscribe. Nếu bọc từng nguồn thành `Mono<Optional<T>>` trước khi zip, mỗi nhánh đều có thể phát giá trị Optional, nên `zip` sẽ subscribe đủ các nhánh cần để tạo kết quả.

**Cẩn thận:** được subscribe **không đồng nghĩa** mọi tác vụ đã hoàn tất thành công: lỗi, cancel chủ động, timeout hay lỗi nguồn ngoài vẫn có thể thay đổi vòng đời. `Optional` biểu diễn vắng mặt, không biến lỗi thành thành công.

### Trường hợp C — Có `Mono<Void>` và chỉ cần các tác vụ hoàn tất

Dùng `Mono.when` nếu cần **chờ tất cả nguồn hoàn tất** mà không cần tuple dữ liệu:

~~~java
Mono<Void> saved = saveOrder(order);
Mono<Void> audited = recordAudit(order);

Mono<Void> completed = Mono.when(saved, audited);
~~~

Đây là cấu trúc service minh họa. `when` đăng ký các publisher và trả `Mono<Void>` **hoàn tất khi tất cả hoàn tất thành công**; nguồn chỉ hoàn tất rỗng là tình huống bình thường. Nếu một nguồn lỗi, `when` thông thường báo lỗi sớm và có thể hủy các nguồn còn lại.

Nếu nghiệp vụ cần **đợi các nguồn kết thúc ngay cả khi có lỗi**, xem `Mono.whenDelayError(...)` và lập chính sách xử lý lỗi sau khi tất cả đã dừng; không dùng nó như cơ chế tự động bỏ qua lỗi.

Nếu thao tác B phụ thuộc kết quả hoàn tất của A, dùng:

~~~java
Mono<Void> sequence = saveOrder(order).then(recordAudit(order));
~~~

`then(other)` chỉ subscribe `other` **sau khi** nguồn đầu hoàn tất thành công; nếu đầu lỗi, bước sau không được chạy. Đây là cách thể hiện thứ tự rõ hơn `zip` hoặc `when`.

### Trường hợp D — Cần chờ một thao tác `Mono<Void>` rồi ghép một tín hiệu “đã xong”

Khi thật sự muốn kết hợp kết quả của các việc và một việc chỉ có tín hiệu hoàn tất:

~~~java
Mono<Void> save = saveOrder(order);
Mono<String> receipt = save.thenReturn("saved");

Mono<String> response = Mono.zip(
    receipt,
    loadCorrelationId(),
    (status, correlation) -> status + ":" + correlation
);
~~~

`thenReturn("saved")` chỉ phát giá trị sau khi `save` hoàn tất **thành công**; nếu `save` lỗi, lỗi lan ra và không có `"saved"`. Phần tử `"saved"` là một **giá trị mới do người lập trình định nghĩa**, không phải giá trị do `Mono<Void>` phát ra.

**Giới hạn:** vẫn phải quan tâm semantics của `zip`: nếu `loadCorrelationId()` rỗng trước khi `save` hoàn tất, việc `save` có thể bị hủy. Nếu bắt buộc lưu thành công **trước khi** lấy ID, nên nối tuần tự bằng `save.then(loadCorrelationId())`; nếu cần chờ nhiều side effect đến cùng, dùng `when` cho phần side effect rồi `then(...)` để tạo kết quả. Đừng dùng `thenReturn` như cách đảm bảo một nhánh quan trọng không bị cancel khi nhánh khác rỗng.

### Trường hợp E — Muốn trì hoãn lỗi nhưng vẫn cho các nguồn kết thúc

`Mono.zipDelayError(...)` khác `Mono.zip(...)` ở chỗ nó **trì hoãn lỗi** và, theo hợp đồng Reactor, nếu một nguồn hoàn tất rỗng, các nguồn khác vẫn được chạy đến khi kết thúc trước khi `zipDelayError` hoàn tất rỗng. Nó **không thể tạo tuple** nếu thiếu giá trị. Một hay nhiều lỗi có thể được phản ánh thành tín hiệu lỗi sau đó, không bị biến thành empty mặc định.

Chỉ chọn `zipDelayError` khi đúng yêu cầu phối hợp/thu thập lỗi; với các tác vụ chỉ có completion, `when` hoặc `whenDelayError` truyền đạt ý định rõ ràng hơn.

## 7. Bảng lựa chọn nhanh

| Mục tiêu | Nên dùng | Tránh hiểu nhầm |
| --- | --- | --- |
| Ghép các **giá trị** từ nhiều `Mono<T>` đều có dữ liệu | `Mono.zip`, `zipWith` | Một nguồn empty làm kết quả empty |
| Tính nguồn thứ hai dựa trên giá trị thứ nhất | `zipWhen` hoặc `flatMap` theo yêu cầu | Bên trái empty thì hàm tạo nguồn sau không chạy |
| Mono dữ liệu có thể vắng, cho phép fallback | `defaultIfEmpty`, `switchIfEmpty` trước `zip` | Không tự đặt sentinel sai nghĩa |
| Cần quan sát cả trường hợp empty | `singleOptional()` rồi `zip` | Kết quả chứa `Optional<T>` chứ không phải `T` |
| Chờ hoàn tất nhiều tác vụ `Mono<Void>` | `Mono.when` | Kết quả là `Mono<Void>`, không phải tuple |
| Chạy B sau khi A hoàn tất | `A.then(B)` | `when` không thể hiện phụ thuộc thứ tự |
| Cần đổi completion-only thành giá trị có nghĩa | `thenReturn(value)` | Không đảm bảo nhánh khác trong `zip` không hủy sớm |
| Chờ nhiều nguồn khi có lỗi; muốn tổng hợp lỗi | `whenDelayError` hoặc `zipDelayError` theo mục tiêu | `zipDelayError` vẫn empty nếu thiếu giá trị và không có lỗi |

## 8. Trường hợp thường gặp trong Spring WebFlux

Giả sử API có hai hành động: **ghi đơn hàng** trả `Mono<Void>`, và **ghi audit** trả `Mono<Void>`. Cách viết dưới đây dễ sai:

~~~java
// Ví dụ không phải ứng dụng Spring Boot độc lập.
// Cả hai method đều trả Mono<Void>.
Mono<Void> save = orderService.saveOrder(order);
Mono<Void> audit = auditService.record(order);

Mono<?> wrong = Mono.zip(save, audit);
~~~

Nhìn vào `wrong`, có thể tưởng zip sẽ luôn làm cả hai việc rồi phát một kết quả. Thực tế, nếu một nguồn hoàn tất rỗng sớm, zip có thể hoàn tất trước, hủy hoặc không subscribe nhánh kia. Ngoài ra **không có tuple** nào được phát vì cả hai đều `Mono<Void>`.

Chọn đúng theo nghiệp vụ:

~~~java
// Muốn cả hai thao tác được khởi chạy và chờ hoàn tất thành công:
Mono<Void> bothDone = Mono.when(
    orderService.saveOrder(order),
    auditService.record(order)
);

// Muốn ghi audit CHỈ SAU KHI lưu order hoàn tất:
Mono<Void> inOrder = orderService.saveOrder(order)
    .then(auditService.record(order));

// Muốn trả về trạng thái sau khi cả hai hoàn tất:
Mono<String> response = Mono.when(
    orderService.saveOrder(order),
    auditService.record(order)
).thenReturn("OK");
~~~

Các biểu thức này phù hợp làm service reactive hoặc giá trị trả về từ controller. Trong Spring WebFlux, **trả lại `Mono`**, để framework subscribe và quản lý cancellation theo vòng đời request; tránh gọi `block()` hoặc tự `subscribe()` trong controller chỉ để bắt các tác vụ chạy. Nếu cần bảo đảm giao dịch đã được xử lý dù client mất kết nối, thiết kế nghiệp vụ phải dùng cơ chế tin cậy (transaction, outbox, hàng đợi, retry/idempotency có kiểm soát), không dựa vào việc một nhánh `zip` tình cờ đã được subscribe.

Một lỗi phát sinh khi cố zip dữ liệu sau `then()`:

~~~java
Mono<User> user = userRepository.findById(id);
Mono<Void> logged = logAction(id);

Mono<?> bad = Mono.zip(user, logged); // logged không phát giá trị

// Nếu cần hoàn tất log trước khi trả User:
Mono<User> good = logged.then(user);
~~~

Đây là ví dụ service minh họa. Nếu `user` rỗng, `good` vẫn rỗng; sự khác biệt là **thao tác log đã được chờ hoàn tất thành công** trước khi bắt đầu truy vấn user. Nếu muốn lấy dữ liệu trước rồi chỉ log khi có user, dùng `user.flatMap(u -> logAction(id).thenReturn(u))`; trường hợp user rỗng thì `flatMap` không chạy, phù hợp nếu đây là quy tắc nghiệp vụ.

## 9. Debug và kiểm chứng behavior của empty

Khi quan sát một pipeline `zip` không chạy combinator, nên lần lượt kiểm tra:

1. **Mỗi nguồn thật sự phát `onNext` hay chỉ `onComplete`?** Dùng `doOnNext`, `doOnSuccess` (lưu ý `doOnSuccess` của `Mono` có thể nhận `null` khi hoàn tất rỗng), `doOnError` và log tín hiệu để phân biệt.
2. **Có toán tử làm mất dữ liệu trước zip?** Các ví dụ hay gặp là `then()`, `ignoreElement(s)`, `thenEmpty(...)`, `when(...)`.
3. **Kiểu thực tế là `Mono<Void>`?** Nếu chỉ biểu diễn hoàn tất, đừng chờ nó phát giá trị.
4. **Có `zipWhen` với nguồn bên trái rỗng?** Khi đó hàm dựng nguồn thứ hai không chạy.
5. **Nhánh khác không được subscribe hoặc bị cancel?** `doOnSubscribe`, `doOnCancel`, `doFinally` hỗ trợ quan sát; không suy luận chỉ từ việc gọi phương thức tạo publisher.
6. **Có xử lý empty ở đúng vị trí không?** Đặt `defaultIfEmpty`, `switchIfEmpty` hoặc `singleOptional` trên nguồn thích hợp **trước khi zip**.
7. **Có hiểu nhầm empty là error?** `switchIfEmpty` phản ứng với nguồn rỗng; `onErrorResume` phản ứng với lỗi. Hai toán tử giải quyết tình huống khác nhau.
8. **Có cần mọi side effect chạy thành công không?** Dùng `Mono.when`/chuỗi `then` cùng cơ chế bảo đảm phù hợp; không dựa vào thứ tự subscribe không được cam kết của zip.

Có thể kiểm thử trực tiếp (với dependency `reactor-test` và `StepVerifier` trong test):

~~~java
// Đoạn test minh họa; cần reactor-test trong test scope.
StepVerifier.create(Mono.zip(Mono.<String>empty(), Mono.just("B")))
    .verifyComplete(); // Không có expectNext, vì zip empty.

StepVerifier.create(
    Mono.zip(
        Mono.just("A"),
        Mono.just("B"),
        (a, b) -> a + b
    )
).expectNext("AB").verifyComplete();
~~~

Nếu cần chứng minh **nhánh có được subscribe hay không**, kiểm tra `AtomicInteger` qua `doOnSubscribe` trong test riêng; nhưng không đặt điều kiện rằng mọi cấu trúc zip, mọi thứ tự hoàn tất và mọi phiên bản Reactor bắt buộc phải subscribe đủ nguồn. Việc một nhánh bị bỏ qua khi đã biết không thể tạo kết quả là hành vi hợp lệ.

## 10. Câu hỏi tự kiểm tra

**1. `Mono.zip(Mono.just(1), Mono.empty())` trả tuple gì?** Không trả tuple nào. Kết quả hoàn tất rỗng; nguồn thứ hai không cung cấp phần tử để ghép.

**2. `Mono<Void>` hoàn tất thành công có được tính là một giá trị không?** Không. `onComplete` thông báo kết thúc, không phải `onNext`.

**3. Vì sao `source.then().zipWith(other)` không gọi combinator?** Vì `then()` chủ ý loại phần tử từ `source`, nên vế trái không còn giá trị.

**4. Nếu cần chờ cả lưu dữ liệu và gửi audit đều xong thì dùng gì?** `Mono.when(save, audit)` cho các tác vụ độc lập chỉ cần hoàn tất, hoặc `save.then(audit)` khi audit phải chờ save.

**5. Nếu `Mono<String>` có thể empty nhưng muốn vẫn zip với một giá trị mặc định thì sao?** Dùng `defaultIfEmpty("giá trị phù hợp")` trên nguồn trước zip; không áp dụng cách này trực tiếp cho `Mono<Void>`.

**6. Nếu cần phân biệt giá trị có/không tồn tại mà vẫn zip được?** Dùng `singleOptional()` rồi zip các `Mono<Optional<T>>` để `Optional.empty()` trở thành một giá trị hợp lệ.

**7. `zipDelayError` có tự sinh giá trị khi một nhánh empty không?** Không. Nó có thể đợi các nhánh khác kết thúc, nhưng nếu không có lỗi và một nguồn không phát giá trị thì kết quả vẫn empty.

**Kết luận cần nhớ:** `zip` ghép **các giá trị**, không ghép **các thông báo hoàn tất**. Một `Mono.empty()` hoặc `Mono<Void>` có thể khiến `zip` hoàn tất rỗng, combinator không chạy và những tác vụ khác bị cancel/không được subscribe. Hãy chọn `defaultIfEmpty`, `singleOptional`, `thenReturn`, `Mono.when` hoặc `then` theo **hợp đồng nghiệp vụ** cần thể hiện, thay vì cố ép mọi workflow dùng `zip`.

**Tài liệu tham khảo:** [Project Reactor FAQ — My Mono zipWith or zipWhen is never called](https://projectreactor.io/docs/core/release/reference/faq.html#faq.zip.empty); [Reactor Mono JavaDoc — zip / zipDelayError / when](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html).