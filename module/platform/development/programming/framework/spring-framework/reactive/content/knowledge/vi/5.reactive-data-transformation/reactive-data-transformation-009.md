# `then`, `thenReturn` và hệ quả loại bỏ giá trị đầu vào trong Project Reactor

## 1. Mục tiêu và bối cảnh

Trong Spring WebFlux, `Mono<T>` và `Flux<T>` không chỉ chứa dữ liệu: chúng biểu diễn một quá trình bất đồng bộ có thể phát các phần tử (`onNext`), hoàn tất thành công (`onComplete`), phát lỗi (`onError`) hoặc bị hủy (`cancel`). Khi ghép nhiều thao tác, đôi khi ta **chỉ quan tâm thao tác trước đã hoàn tất thành công**, không cần giữ lại giá trị mà nó tạo ra. Project Reactor cung cấp các toán tử `then` và `thenReturn` cho trường hợp đó.

Hai ý chính:

- `then()`: chờ nguồn hoàn tất và trả về `Mono<Void>`, **bỏ qua mọi phần tử đầu vào**; chỉ truyền tiếp thành công hoặc lỗi.
- `thenReturn(value)`: chờ một **`Mono`** nguồn hoàn tất thành công, bỏ giá trị nguồn nếu có, rồi phát **một giá trị mới được cung cấp sẵn**.

Trong bài, “bỏ” hoặc “discard” nghĩa là **không chuyển phần tử đó tới subscriber downstream**. Nó không có nghĩa tác vụ nguồn chưa hề thực thi, đối tượng đã được xóa khỏi bộ nhớ hay tài nguyên đã được đóng tự động.

### Tình huống thực tế

Một dịch vụ lưu bản ghi trả về `Mono<SavedEntity>`. Endpoint chỉ cần biết lưu thành công để trả mã xác nhận cố định; không cần đưa `SavedEntity` xuống người gọi:

~~~java
Mono<String> acknowledgement =
    repository.save(entity)
              .thenReturn("SAVED");
~~~

Nếu lưu thành công, downstream nhận `"SAVED"` rồi `onComplete`. Nếu lưu lỗi, downstream nhận `onError`; giá trị `"SAVED"` **không được phát**. Nếu cần ID hoặc dữ liệu của `SavedEntity`, không nên dùng `thenReturn` vì thông tin đó đã bị bỏ qua; dùng `map(saved -> ...)` hoặc `flatMap(saved -> ...)`.

## 2. Nền tảng: tín hiệu hoàn tất khác giá trị dữ liệu

Hãy tách hai câu hỏi:

1. **Nguồn đã kết thúc thế nào?** Thành công (`onComplete`) hay lỗi (`onError`)?
2. **Nguồn tạo ra dữ liệu gì?** Không có phần tử, một phần tử, hay nhiều phần tử?

Một `Mono.just("A")` phát `onNext("A")` rồi `onComplete`; `Mono.empty()` chỉ phát `onComplete`; `Mono.error(...)` phát `onError`. Sau khi thêm `then()`:

~~~text
Nguồn ban đầu                         Sau then()
onNext("A") -> onComplete            onComplete
onComplete                            onComplete
onError(exception)                   onError(exception)
onNext("A") -> onNext("B") -> done    onComplete
~~~

Tất cả `onNext` từ upstream bị bỏ, nhưng **lỗi không bị nuốt**. Toán tử `then` không tương đương với `onErrorComplete` hoặc `onErrorResume`.

Điều quan trọng khác: `onComplete` có thể xuất hiện khi nguồn rỗng. Do đó `thenReturn("OK")` trên `Mono.empty()` vẫn tạo `"OK"`. Không được hiểu `thenReturn` là “nếu upstream có giá trị thì chuyển thành OK”; nó là “**nếu upstream hoàn tất thành công thì phát OK**”.

## 3. `then()`: chỉ giữ kết quả hoàn tất

### 3.1. `Mono<T>.then()`

Chữ ký khái niệm:

~~~java
Mono<Void> finished = sourceMono.then();
~~~

Ví dụ:

~~~java
Mono<Void> finished = Mono.just("payload")
    .doOnNext(value -> System.out.println("source=" + value))
    .then();

finished.subscribe(
    ignored -> System.out.println("Không có onNext ở đây"),
    error -> System.out.println("error=" + error.getMessage()),
    () -> System.out.println("complete")
);
~~~

Stdout:

~~~text
source=payload
complete
~~~

Giải thích:

- Upstream đã phát `"payload"`, vì vậy callback `doOnNext` **đặt trước** `then` vẫn thấy giá trị.
- `then` chủ động bỏ `"payload"`, downstream **không thấy** `onNext`.
- `Mono<Void>` báo hoàn tất thành công bằng `onComplete`, **không phát một object `Void`**.
- Khi nguồn báo lỗi, kết quả `then()` phát lỗi thay vì hoàn tất thành công.

Giá trị `Void` là cách biểu diễn **chỉ có thành công/lỗi mà không có dữ liệu**. Nó không phải tín hiệu `onNext(null)`; Reactive Streams không cho phép phát `null`.

### 3.2. `Flux<T>.then()`

Với `Flux` có nhiều phần tử, `then()` cũng tạo `Mono<Void>` và bỏ tất cả phần tử được nguồn phát:

~~~java
Mono<Void> completed = Flux.range(1, 3)
    .doOnNext(i -> System.out.println("processed=" + i))
    .then();
~~~

Khi đăng ký, các phần tử 1, 2, 3 vẫn đi qua `doOnNext`. Sau khi nguồn hoàn tất, downstream chỉ nhận `onComplete`. `then()` **không dừng ngay sau phần tử đầu tiên** như `next()` hoặc `take(1)`; nó phải chờ toàn bộ nguồn hoàn tất thành công.

Điều này có hệ quả vận hành: nếu upstream thực hiện nhiều phép biến đổi, gọi DB hoặc ghi log cho từng item thì chi phí upstream vẫn có thể phát sinh. Đừng sử dụng `then()` như một giải pháp tối ưu để “không thực hiện công việc” — nó chỉ thay đổi **dữ liệu được chuyển xuống phía sau**.

### 3.3. Không nhầm `then()` với `map` hoặc `filter`

~~~java
Mono<Integer> a = Mono.just(10).map(n -> n * 2); // phát 20
Mono<Integer> b = Mono.just(10).filter(n -> n > 5); // phát 10
Mono<Void> c = Mono.just(10).then(); // không phát số nào, chỉ hoàn tất
~~~

`map` biến đổi *giá trị* và đòi hỏi có `onNext`. `filter` chọn/bỏ phần tử theo điều kiện. `then` bỏ mọi giá trị và chỉ giữ ý nghĩa *hoàn tất*.

## 4. `thenReturn(value)`: chờ thành công, rồi trả một giá trị cố định

`Mono<T>.thenReturn(V value)` trả về `Mono<V>` và có ba đặc tính:

1. Giá trị nguồn `T` không còn xuất hiện ở downstream.
2. Nếu nguồn kết thúc thành công (dù rỗng), downstream nhận **một** `value` rồi `onComplete`.
3. Nếu nguồn lỗi, lỗi truyền qua và `value` **không được phát**.

~~~java
Mono<String> response = Mono.just(42)
    .thenReturn("OK");
response.subscribe(System.out::println);
// In: OK (không in 42)
~~~

So sánh ba nguồn:

| Upstream | `thenReturn("ACK")` tạo tín hiệu downstream | Lý do |
| --- | --- | --- |
| `Mono.just(123)` | `onNext("ACK")`, `onComplete` | Bỏ 123 rồi phát ACK |
| `Mono.empty()` | `onNext("ACK")`, `onComplete` | Hoàn tất rỗng cũng được coi là thành công |
| `Mono.error(new IllegalStateException("x"))` | `onError(error)` | Không phát ACK khi lỗi |
| `Mono.never()` | Chưa phát gì và chưa kết thúc | Vẫn chờ upstream; trừ khi bị hủy/timeout |
| Upstream bị `cancel()` trước khi hoàn tất | Không thể coi là thành công để phát ACK | Cancellation khác completion |

### 4.1. `thenReturn` không truy xuất giá trị nguồn

~~~java
Mono<User> saved = repository.save(user); // giả sử trả Mono<User>
Mono<String> fixed = saved.thenReturn("SAVED");
~~~

`"SAVED"` là một hằng xác nhận có sẵn. Nếu cần sinh nội dung từ bản ghi đã lưu:

~~~java
Mono<String> dynamic = repository.save(user)
    .map(savedUser -> "SAVED:" + savedUser.getId());
~~~

Kết quả của `map` còn phụ thuộc `savedUser`, còn `thenReturn` bỏ `savedUser` hoàn toàn. Nếu nguồn rỗng, `map` không chạy và `Mono` cuối cũng rỗng; `thenReturn` vẫn phát xác nhận, vì vậy cần xác định **ngữ nghĩa “rỗng”** trước khi chọn.

### 4.2. Đối số `thenReturn` được đánh giá ngay khi lắp ráp pipeline

Java đánh giá đối số của method trước khi gọi method:

~~~java
Mono<Void> save = saveAsync();
Mono<String> result = save.thenReturn(calculateReceipt()); 
// calculateReceipt() chạy ngay khi xây dựng result,
// dù save chưa hoàn tất hoặc chưa ai subscribe.
~~~

Nếu `calculateReceipt()` tốn công, có side effect hoặc cần chạy **sau khi lưu thành công, mỗi lần subscribe**, dùng một Mono có cơ chế tạo giá trị trì hoãn:

~~~java
Mono<String> result = save.then(
    Mono.fromSupplier(() -> calculateReceipt())
);
~~~

`thenReturn(value)` thường thích hợp cho hằng hoặc object đã có sẵn. `then(Mono.fromSupplier(...))` phù hợp hơn khi giá trị tiếp theo phải được **tính ở thời điểm subscribe vào giai đoạn sau**. Lưu ý: ngay cả với `then(Mono<V>)`, *biểu thức Java tạo đối số `Mono`* vẫn được đánh giá khi assembly; chỉ logic nằm trong `fromSupplier`/`defer` mới được trì hoãn.

### 4.3. Không dùng `null` làm giá trị thành công

`thenReturn(null)` không tạo ra “Mono chứa null” hợp lệ. Nếu muốn kết quả chỉ hoàn tất không có dữ liệu, dùng `then()`; nếu muốn một phần tử mặc định, chọn một object thực sự không-null. Nếu giá trị có thể thiếu, cân nhắc `then(Mono.justOrEmpty(nullableValue))` hoặc `then(Mono.fromSupplier(...))` cùng hợp đồng rõ ràng.

## 5. `then(Mono<V>)` và các biến thể liên quan

Cách đọc tự nhiên của `first.then(second)`: **hoàn tất `first` thành công, sau đó subscribe vào `second` và phát dữ liệu của `second`**. Mọi giá trị của `first` bị loại bỏ.

~~~java
Mono<String> workflow =
    Mono.just("ID-1")
        .doOnNext(id -> System.out.println("saved=" + id))
        .then(Mono.fromSupplier(() -> {
            System.out.println("creating receipt");
            return "receipt-ready";
        }));
~~~

Khi đăng ký, stdout là:

~~~text
saved=ID-1
creating receipt
~~~

Downstream nhận `"receipt-ready"` (nếu subscribe có consumer để in ra). Nếu `first` lỗi, `second` không được subscribe; lỗi upstream được truyền xuống. Nếu `second` lỗi, downstream nhận lỗi từ `second`. Nếu `first` rỗng nhưng thành công, `second` vẫn chạy.

| Toán tử | Giá trị upstream | Phần downstream sẽ phát | Kiểu kết quả |
| --- | --- | --- | --- |
| `mono.then()` | Bỏ | Chỉ complete/error | `Mono<Void>` |
| `flux.then()` | Bỏ tất cả | Chỉ complete/error | `Mono<Void>` |
| `mono.thenReturn(v)` | Bỏ | Một giá trị `v` nếu thành công | `Mono<V>` |
| `mono.then(otherMono)` | Bỏ | Phát tín hiệu của `otherMono` nếu upstream thành công | `Mono<V>` |
| `flux.then(otherMono)` | Bỏ | Phát tín hiệu của `otherMono` sau khi Flux thành công | `Mono<V>` |
| `mono.thenMany(otherPublisher)` | Bỏ | Phát các phần tử của `otherPublisher` sau upstream thành công | `Flux<V>` |
| `mono.thenEmpty(otherVoidPublisher)` | Bỏ | Chờ cả hai nguồn hoàn tất, không phát giá trị | `Mono<Void>` |
| `flux.thenMany(otherPublisher)` | Bỏ | Phát các phần tử của `otherPublisher` sau upstream thành công | `Flux<V>` |

Đối với `Flux`, không có `Flux.thenReturn(v)` như trên `Mono`. Nếu đầu vào là `Flux<T>` và muốn chờ toàn bộ nó rồi phát một xác nhận cố định, dùng `flux.then(Mono.just(v))` hoặc `flux.then().thenReturn(v)`.

Ví dụ trả một `Flux` sau một thao tác thiết lập:

~~~java
Flux<String> records = initializeAsync() // Mono<Void>
    .thenMany(Flux.just("A", "B", "C"));
~~~

`initializeAsync()` phải hoàn tất thành công thì `records` mới bắt đầu phát dữ liệu từ nguồn thứ hai.

### `then` khác `concatWith`

Với `Flux.just("A").concatWith(Flux.just("B"))`, downstream có thể thấy cả `"A"` và `"B"`. Với `Flux.just("A").thenMany(Flux.just("B"))`, downstream chỉ thấy `"B"` — vì `thenMany` **bỏ** các phần tử của nguồn đầu. Cả hai đều xếp giai đoạn theo thứ tự, nhưng chỉ một cách giữ dữ liệu của giai đoạn đầu.

## 6. Hệ quả của việc loại bỏ giá trị đầu vào

### 6.1. Giá trị bị bỏ ở ranh giới toán tử, không bị “hủy tính toán”

Giả sử:

~~~java
Mono<Void> finished = Flux.just("a", "b")
    .map(s -> s.toUpperCase())
    .doOnNext(s -> System.out.println("computed=" + s))
    .then();
~~~

`map` và `doOnNext` vẫn xử lý các giá trị `"A"`, `"B"` trước `then`. Bên nhận cuối chỉ thấy completion. Vì vậy:

- Công việc, ghi log hoặc hiệu ứng phụ **đã thực hiện upstream** không được hoàn tác.
- `then` không trả về bộ sưu tập giá trị và không tự giữ reference đến toàn bộ chúng để phát sau.
- Dữ liệu không được forwarded đến downstream; nếu sau `then` cần truy cập nó, pipeline đã mất kênh truyền giá trị đó.
- Các toán tử dùng buffering trước `then` vẫn có thể sử dụng bộ nhớ; `then` không giải quyết mọi vấn đề bộ nhớ hoặc I/O.

### 6.2. Dọn dẹp phần tử bị discard

Một số phần tử là object thông thường, chỉ cần để JVM thu gom rác khi không còn tham chiếu. Nhưng nếu chứa tài nguyên cần release (ví dụ bộ đệm tham chiếu đếm), việc chủ động loại bỏ giá trị có thể đòi hỏi cleanup.

Reactor cung cấp `doOnDiscard(Class<R>, Consumer<? super R>)` để đặt callback dọn dẹp với **các toán tử upstream hỗ trợ discard**. Javadoc của `then()` và `thenReturn(...)` xác nhận khả năng discard phần tử nguồn.

Ví dụ minh họa trên `String` (chỉ quan sát, không phải giải phóng tài nguyên thật):

~~~java
Mono<Void> completion = Flux.just("A", "B")
    .then()
    .doOnDiscard(String.class, discarded ->
        System.out.println("discarded=" + discarded));

completion.subscribe(
    ignored -> System.out.println("unexpected value"),
    error -> System.out.println("error=" + error.getMessage()),
    () -> System.out.println("complete")
);
~~~

Điểm đặt hook ở **sau toán tử loại bỏ** là chủ ý: `doOnDiscard` cấu hình cleanup cho các toán tử hỗ trợ nằm phía upstream. Với tài nguyên thực sự, callback phải **idempotent** và an toàn nếu gọi nhiều lần. Không phải mọi toán tử Reactor đều hỗ trợ cơ chế này; đọc phần “Discard Support” trong Javadoc của toán tử cụ thể và kiểm thử đường cancel/error.

Với tài nguyên sở hữu cả một vòng đời như file, connection hoặc transaction, ưu tiên quản lý có ràng buộc bằng `using`/`usingWhen` hoặc cơ chế của framework; `doOnDiscard` không phải vật thay thế phổ quát cho cleanup lúc hoàn tất, lỗi hay hủy. `doFinally` giúp quan sát `ON_COMPLETE`, `ON_ERROR`, `CANCEL` để đo lường vòng đời; nó **không** biến cancel thành onComplete.

### 6.3. Hủy đăng ký, lỗi và completion

~~~text
source --onNext(x)--> then --(không forward x)-->
source --onComplete--> then --------------------> downstream onComplete
source --onError(e)-> then --------------------> downstream onError(e)

source bị cancel trước khi thành công:
  downstream không thể giả định sẽ nhận onComplete hoặc thenReturn(value).
~~~

- Với `then(Mono.just("NEXT"))`, nếu `source` lỗi, `"NEXT"` không xuất hiện.
- Nếu downstream hủy trước khi source hoàn tất, cancellation có thể lan lên nguồn; các tác vụ bất đồng bộ đã khởi động có thể cần cơ chế hủy riêng. Không suy luận rằng cancel chắc chắn dừng mọi I/O tức thì.
- Nếu `source` không bao giờ hoàn tất, `then` sẽ tiếp tục đợi (cho đến khi có cancel/timeout hoặc điều kiện bên ngoài).
- Khi upstream hoàn tất rỗng, `then()` vẫn hoàn tất; `thenReturn(v)` vẫn phát `v`; `then(other)` vẫn subscribe `other`.

### 6.4. `then()` làm mất thông tin “Mono trước có dữ liệu hay không”

Cả `Mono.empty().then()` và `Mono.just("X").then()` đều nhìn giống nhau ở downstream: `Mono<Void>` hoàn tất thành công. Khi đã dùng `then`, không thể dựa vào `switchIfEmpty` đặt phía sau để hỏi “nguồn ban đầu có phát phần tử hay không”.

~~~java
Mono<String> source = findUser(); // giả sử Mono<String>

// Sai nếu mục tiêu là báo lỗi khi không tìm thấy user:
Mono<Void> wrong = source.then()
    .switchIfEmpty(Mono.error(
        new IllegalStateException("not found")));
// then() thành công luôn là Mono rỗng, nên switchIfEmpty kích hoạt
// cả khi findUser() trước đó có giá trị.
~~~

Cách đúng: kiểm tra tình trạng rỗng **trước khi** bỏ payload:

~~~java
Mono<Void> right = source
    .switchIfEmpty(Mono.error(
        new IllegalStateException("not found")))
    .then();
~~~

Chú ý quan trọng: `defaultIfEmpty` và `switchIfEmpty` trên `Mono<Void>` sau `then()` không giúp khôi phục thông tin đã bị bỏ. Trường hợp muốn biết *nguồn ban đầu có phát giá trị hay không*, phải đặt logic kiểm tra ở upstream.

## 7. Ví dụ Java 17+ hoàn chỉnh: lần lượt quan sát 6 trường hợp

Ví dụ dùng Project Reactor Core 3.8.8, Maven và một chương trình không dùng scheduler để stdout có thứ tự dễ kiểm chứng. Cấu trúc dự án:

~~~text
reactor-then-demo/
├── pom.xml
└── src/main/java/example/ThenOperatorsDemo.java
~~~

**Tệp `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-then-demo</artifactId>
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
                    <mainClass>example.ThenOperatorsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Tệp `src/main/java/example/ThenOperatorsDemo.java`:**

~~~java
package example;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ThenOperatorsDemo {

    private static <T> void observe(String name, Mono<T> source) {
        System.out.println("== " + name + " ==");
        source.subscribe(
            value -> System.out.println("next=" + value),
            error -> System.out.println("error=" + error.getMessage()),
            () -> System.out.println("complete")
        );
    }

    public static void main(String[] args) {
        observe("then", Mono.just("PAYLOAD")
            .doOnNext(value -> System.out.println("upstream=" + value))
            .then());

        observe("thenReturn", Mono.just(42)
            .doOnNext(value -> System.out.println("upstream=" + value))
            .thenReturn("ACK"));

        observe("empty thenReturn", Mono.<String>empty()
            .thenReturn("ACK_FROM_EMPTY"));

        observe("error thenReturn",
            Mono.<String>error(new IllegalStateException("FAILED"))
                .thenReturn("NEVER_EMITTED"));

        observe("then another Mono", Mono.just("FIRST")
            .doOnNext(value -> System.out.println("first=" + value))
            .then(Mono.fromSupplier(() -> {
                System.out.println("second subscribed");
                return "SECOND";
            })));

        observe("Flux then", Flux.range(1, 3)
            .doOnNext(number -> System.out.println("work=" + number))
            .then());
    }
}
~~~

Chạy từ thư mục `reactor-then-demo`:

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến:**

~~~text
== then ==
upstream=PAYLOAD
complete
== thenReturn ==
upstream=42
next=ACK
complete
== empty thenReturn ==
next=ACK_FROM_EMPTY
complete
== error thenReturn ==
error=FAILED
== then another Mono ==
first=FIRST
second subscribed
next=SECOND
complete
== Flux then ==
work=1
work=2
work=3
complete
~~~

Phân tích:

1. `then` vẫn cho upstream `doOnNext` quan sát `PAYLOAD`, nhưng downstream không nhận phần tử.
2. `thenReturn("ACK")` không chuyển 42 thành chuỗi; nó **bỏ 42** rồi phát hằng mới.
3. `Mono.empty()` hoàn tất thành công, nên `thenReturn` vẫn có một giá trị đầu ra.
4. Lỗi `FAILED` đi thẳng xuống downstream; `NEVER_EMITTED` không xuất hiện và không có `complete`.
5. Giai đoạn thứ hai bắt đầu sau khi giai đoạn thứ nhất hoàn tất; giá trị `FIRST` không đi qua.
6. `Flux.then()` đợi toàn bộ ba phần tử được upstream xử lý trước khi hoàn tất.

Ví dụ chạy đồng bộ nên thứ tự stdout có thể đối chiếu trực tiếp. Nếu thêm `subscribeOn`, `publishOn` hoặc các nguồn bất đồng bộ, luồng thực thi và thứ tự giữa những subscription độc lập có thể thay đổi.

## 8. Vận dụng trong Spring WebFlux

### 8.1. Ghép các công việc theo thứ tự mà không cần payload đầu tiên

Trong một dịch vụ, giả sử `validate(command)` trả `Mono<Void>` (chỉ hoàn tất nếu hợp lệ) và `persist(command)` trả `Mono<SavedOrder>`. Nếu HTTP response chỉ cần xác nhận đã xử lý, có thể viết:

~~~java
// Đoạn minh họa nằm trong service/controller đã có dependency Spring WebFlux.
// validate và persist là các phương thức nghiệp vụ giả định đã được định nghĩa.
Mono<ResponseEntity<String>> submit(OrderCommand command) {
    return validate(command)
        .then(persist(command))
        .thenReturn(ResponseEntity.accepted().body("accepted"));
}
~~~

Vòng đời:

1. `validate` hoàn tất thành công thì `persist` mới được subscribe.
2. `persist` hoàn tất thành công thì `thenReturn` phát response.
3. Nếu một giai đoạn lỗi thì downstream nhận lỗi, không nhận response xác nhận ở bước 2 hoặc 3.
4. Dữ liệu `SavedOrder` do `persist` tạo ra bị bỏ qua. Điều đó chỉ phù hợp nếu response không cần ID hay các trường của bản ghi.

**Ranh giới quan trọng:** HTTP 202 Accepted là quyết định nghiệp vụ, không phải mã trạng thái mà `thenReturn` tự sinh. Controller phải trả `ResponseEntity` hoặc cấu hình status phù hợp.

### 8.2. Nếu cần giá trị đã lưu, dùng `flatMap` hoặc `map`

~~~java
Mono<ResponseEntity<String>> submitWithId(OrderCommand command) {
    return validate(command)
        .then(persist(command))
        .map(saved -> ResponseEntity.ok("id=" + saved.getId()));
}
~~~

Ví dụ này vẫn dùng `then` để đảm bảo `validate` chạy trước `persist` nhưng **giữ lại** kết quả của `persist` vì `map` nằm trên Publisher trả về từ `then(persist(command))`.

Nếu `persist` hoàn tất rỗng mà không lưu gì, `map` không chạy. Nếu nghiệp vụ buộc phải có bản ghi, thêm `switchIfEmpty` trên `persist` hoặc ngay sau `then(persist(...))` trước `map` để chuyển vắng mặt thành lỗi rõ ràng.

### 8.3. Dùng `Mono<Void>` cho thao tác chỉ có completion

~~~java
Mono<Void> deleteAndAudit(String id) {
    return repository.deleteById(id)
        .then(auditService.recordDeletion(id));
}
~~~

Ở đây `deleteById` và `recordDeletion` phải trả các publisher có ngữ nghĩa hoàn tất đúng như hợp đồng. `then` đảm bảo thứ tự subscription và lan truyền lỗi; nó không tự tạo transaction xuyên hai hệ thống. Nếu cần giao dịch nguyên tử hoặc bù trừ khi lỗi, phải thiết kế riêng.

Trong handler WebFlux, **trả về publisher** để framework quản lý đăng ký, lỗi và hủy. Không gọi `subscribe()` thủ công ngay trong request handler chỉ để “kích hoạt” thao tác, vì sẽ tách vòng đời khỏi response, làm mất khả năng phối hợp cancel/error.

## 9. Khi nào chọn `then`, `thenReturn` hay toán tử khác?

| Nhu cầu | Cách phù hợp | Lưu ý |
| --- | --- | --- |
| Chờ xong, không cần dữ liệu | `source.then()` | Kiểu `Mono<Void>`; giữ lỗi |
| Chờ Mono thành công rồi trả xác nhận cố định | `source.thenReturn("OK")` | Kể cả khi nguồn rỗng |
| Chờ nguồn rồi bắt đầu Mono khác | `source.then(otherMono)` | Nếu nguồn lỗi, giai đoạn sau không chạy |
| Chờ Flux rồi trả một giá trị | `flux.then(Mono.just(value))` | `Flux` không có `thenReturn` |
| Chờ nguồn rồi phát nhiều phần tử khác | `source.thenMany(otherFlux)` | Bỏ dữ liệu nguồn đầu |
| Biến đổi chính giá trị ban đầu | `source.map(value -> ...)` | Cần upstream thực sự phát phần tử |
| Tạo giai đoạn mới dựa trên giá trị ban đầu | `source.flatMap(value -> service.call(value))` | Có thể bỏ qua với nguồn rỗng |
| Duyệt và vẫn giữ phần tử | `doOnNext(...)` | Chỉ quan sát, không thay payload |
| Báo lỗi nếu không có bản ghi | `source.switchIfEmpty(Mono.error(...))` **trước** `then` | Kiểm tra trước khi mất thông tin rỗng |
| Giá trị kết quả phải tính sau thành công | `source.then(Mono.fromSupplier(...))` | Tính tại subscribe của giai đoạn sau |
| Muốn xử lý lỗi bằng fallback | `onErrorResume(...)`, có chủ đích | `then` không nuốt lỗi |

Một quy tắc chọn nhanh: **còn cần payload không?** Nếu cần, tiếp tục dùng `map`/`flatMap`; nếu chỉ cần sự hoàn tất thành công, `then`; nếu sau khi hoàn tất muốn phát một object cố định đã có sẵn, `thenReturn`.

## 10. Lỗi phổ biến và cách tránh

**Lỗi 1 — Tưởng `thenReturn` biến đổi dữ liệu.** `Mono.just(7).thenReturn(99)` phát 99, không phải kết quả tính toán từ 7. Muốn tính từ 7 dùng `map`.

**Lỗi 2 — Cho rằng `then()` nuốt lỗi.** `Mono.error(e).then()` vẫn lỗi. Chỉ các toán tử xử lý lỗi có chủ đích mới thay đổi đường lỗi, và cần lựa chọn theo nghiệp vụ.

**Lỗi 3 — Xem nguồn rỗng là thất bại.** `Mono.empty().thenReturn("OK")` phát OK. Nếu “không có bản ghi” phải là 404 hoặc lỗi domain, hãy dùng `switchIfEmpty` **trước** `then`.

**Lỗi 4 — Dùng `then` rồi muốn đọc giá trị upstream.** Dữ liệu đã được loại ở ranh giới này; hãy thiết kế lại thứ tự toán tử để `map`/`flatMap` chạy tại nơi còn giữ payload.

**Lỗi 5 — Gọi `thenReturn(expensive())` với ý định thực hiện `expensive` sau khi source hoàn tất.** Biểu thức Java chạy khi assembly. Dùng `then(Mono.fromSupplier(...))` hoặc `Mono.defer` để trì hoãn.

**Lỗi 6 — Nhầm `Mono<Void>` với `Mono.just(null)`.** `Mono<Void>` hoàn tất bằng `onComplete` không cần phần tử; không phát `null`.

**Lỗi 7 — Cho rằng discard tự giải phóng mọi tài nguyên.** Các object có tài nguyên ngoại vi có thể cần hook cleanup, `using/usingWhen` hoặc chính sách ownership rõ ràng; chỉ bỏ tham chiếu không bảo đảm đóng tài nguyên.

**Lỗi 8 — Dùng `then()` để tối ưu một chuỗi công việc tốn kém.** Upstream vẫn được subscribe và thường vẫn thực hiện việc phát, xử lý các phần tử. Nếu mục tiêu là không làm việc không cần thiết, phải thay cấu trúc nguồn hoặc điều kiện khởi chạy.

**Lỗi 9 — Gọi subscribe trong controller rồi trả `Mono.just("OK")`.** Cách này có thể trả OK trước khi tác vụ thực sự xong và làm mất lan truyền lỗi/cancel. Dùng `return serviceCall().thenReturn("OK")` để response phụ thuộc đúng vào completion.

**Lỗi 10 — Nghĩ hủy là hoàn tất thành công.** `cancel()` không phát `onComplete`; `thenReturn` không được coi là đã thành công khi nguồn chưa hoàn tất.

## 11. Bài tập tự kiểm tra và đáp án

1. `Mono.just("X").then()` gửi gì cho downstream? **Đáp án:** Chỉ `onComplete`; không có `onNext`.
2. `Mono.empty().thenReturn("A")` có phát `"A"` không? **Có**, vì nguồn hoàn tất thành công.
3. `Mono.error(new RuntimeException("E")).thenReturn("A")` có phát `"A"` không? **Không**, downstream nhận lỗi `E`.
4. Muốn gọi `charge(savedOrder)` bằng đối tượng mà `save(order)` trả về, chọn `then` hay `flatMap`? **`flatMap(savedOrder -> charge(savedOrder))`**, vì cần payload nguồn.
5. `Flux.range(1, 3).then()` có dừng sau số 1 không? **Không**; nguồn vẫn chạy đến khi hoàn tất hoặc lỗi/hủy.
6. Đặt `switchIfEmpty` sau `Mono<Void>.then()` có xác định được nguồn ban đầu không có phần tử không? **Không**. Thao tác đó phải diễn ra trước `then()`.
7. Muốn gọi `generateReceipt()` sau khi `save` thành công **mỗi lần subscribe**, dùng `thenReturn(generateReceipt())` hay `then(Mono.fromSupplier(...))`? **`then(Mono.fromSupplier(() -> generateReceipt()))`** để trì hoãn việc tính.

## 12. Tài liệu đối chiếu

- [Project Reactor API – Mono: then, thenReturn, thenMany, thenEmpty](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): chữ ký, truyền lỗi, loại bỏ phần tử nguồn và các loại Publisher kết quả.
- [Project Reactor API – Flux: then và thenMany](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): bỏ mọi phần tử `Flux`, đợi hoàn tất và phát nguồn kế tiếp.
- [Project Reactor – Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onError` là tín hiệu terminal, cách dùng các toán tử xử lý lỗi.
- [Project Reactor Reference – Which operator do I need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html): so sánh các cách chuyển đổi, nối luồng và xử lý completion.
- [Reactive Streams Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification): quy tắc `onNext`/`onComplete`/`onError`, backpressure, cancellation.