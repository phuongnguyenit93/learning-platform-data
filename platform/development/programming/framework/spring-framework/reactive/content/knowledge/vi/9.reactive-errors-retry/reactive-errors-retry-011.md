# Giới hạn `onErrorContinue` và khi nào nên xử lý lỗi cục bộ trong Project Reactor

## 1. Vấn đề: một bản ghi sai có nên làm hỏng cả luồng?

Trong Spring WebFlux và Project Reactor, lỗi được biểu diễn bằng tín hiệu `onError`. Theo hợp đồng Reactive Streams, một Publisher **đã phát `onError` thì kết thúc**: nó không tiếp tục phát thêm `onNext` hay `onComplete` trên cùng subscription.

Giả sử nhận một luồng chuỗi và chuyển thành số:

```java
Flux<Integer> values = Flux.just("10", "bad", "20")
        .map(Integer::parseInt);
```

Khi có subscriber, `"10"` được chuyển thành `10`, còn `"bad"` khiến `Integer.parseInt` ném `NumberFormatException`. Không có chính sách recovery, subscriber nhận `onError`, và `"20"` **không được phát thành kết quả**.

Nếu nghiệp vụ yêu cầu “bỏ riêng bản ghi sai, xử lý tiếp bản ghi hợp lệ”, người học dễ thử:

```java
Flux<Integer> values = Flux.just("10", "bad", "20")
        .map(Integer::parseInt)
        .onErrorContinue((error, value) -> {
            System.out.println("Dropped: " + value);
        });
```

Trong trường hợp **toán tử `map` hỗ trợ cơ chế này**, luồng có thể phát `10`, bỏ `"bad"`, rồi phát `20`. Tuy nhiên, **không nên suy rộng** rằng `onErrorContinue` là “try/catch cho toàn bộ pipeline”.

**Ý chính của bài:** `onErrorContinue` là cơ chế đặc biệt và tương đối khó dự đoán, chỉ hoạt động khi các operator upstream **có hỗ trợ tiếp tục sau lỗi phát sinh trong việc xử lý một phần tử**. Khi cần bỏ qua lỗi của từng bản ghi/tác vụ, thường nên **đặt xử lý lỗi ngay trong phạm vi bản ghi/tác vụ đó** bằng `handle`, `filter` hoặc một inner `Mono` với `onErrorResume`. Cách này rõ phạm vi hơn và ít làm ảnh hưởng code upstream.

## 2. Phân biệt tín hiệu lỗi terminal và lỗi xử lý một phần tử

Trong Reactive Streams có ba loại tín hiệu quan trọng sau `onSubscribe`:

```text
onNext(T)      : một phần tử dữ liệu
onComplete()   : hoàn tất thành công, terminal
onError(error) : kết thúc vì lỗi, terminal
```

Sau `onComplete` hoặc `onError` không còn giá trị tiếp theo. `onErrorContinue` **không thay đổi quy tắc terminal đó**. Nó chỉ có thể tác động ở những vị trí operator nhận thấy lỗi **trong quá trình xử lý một `onNext`** và hỗ trợ bỏ phần tử gây lỗi trước khi chuyển lỗi thành `onError` cuối cùng.

Hai trường hợp rất khác:

**Trường hợp A — lỗi đồng bộ ở mapper của một phần tử:**

```java
Flux.just("10", "bad", "20")
        .map(Integer::parseInt)
        .onErrorContinue(NumberFormatException.class,
                (error, badValue) -> logBadValue(badValue));
```

`map` là ví dụ có thể hỗ trợ bỏ đúng phần tử `"bad"` để xử lý tiếp `"20"`. `logBadValue` là hàm minh họa do ứng dụng định nghĩa. Cơ chế continuation phải được hỗ trợ bởi operator upstream; kết quả không xuất phát từ việc “khởi động lại” một Publisher đã terminal.

**Trường hợp B — Publisher nguồn tự phát lỗi terminal:**

```java
Flux<Integer> source = Flux.concat(
        Flux.just(10),
        Flux.error(new IllegalStateException("source failed")),
        Flux.just(20)
);
```

Khi subscription đến `Flux.error(...)`, đó là **lỗi của nguồn**, không phải một phần tử đầu vào cụ thể mà operator `map` có thể bỏ đi. Gắn `onErrorContinue` vào sau nguồn **không phải cách đáng tin để biến `onError` terminal này thành `onNext(20)`**. Nếu cần tiếp tục theo chính sách của ứng dụng, phải thiết kế recovery tại boundary nguồn/nhánh phù hợp, ví dụ dùng `onErrorResume` đúng chỗ hoặc biểu diễn từng công việc thành Publisher con riêng.

## 3. `onErrorContinue` thực chất làm gì?

Phác thảo API phổ biến:

```java
Flux<T> stream = someFlux.onErrorContinue(
        (Throwable error, Object value) -> {
            // Quan sát lỗi và giá trị mà operator upstream bỏ qua.
        }
);
```

Đây là **đoạn minh họa chữ ký sử dụng**, không phải định nghĩa API đầy đủ. Reactor cũng có overload lọc theo loại exception hoặc predicate:

```java
.onErrorContinue(NumberFormatException.class,
        (error, value) -> System.out.println("Invalid: " + value))
```

Các điểm bắt buộc phải hiểu:

1. **Hướng tác động là upstream.** Mặc dù viết `.onErrorContinue(...)` ở phía cuối chain, cơ chế continuation được truyền ngược lên một số operator phía trước. Không phải mọi operator đều có khả năng bắt một lỗi và biết phần tử nào có thể bỏ qua.
2. **Cần operator hỗ trợ.** Chẳng hạn `map` thường có ngữ nghĩa rõ để bỏ phần tử gây lỗi; một Publisher đã tự gửi `onError` không còn “bản ghi lỗi” nào để tiếp tục.
3. **Không phải operator thay thế lỗi kiểu thông thường.** `onErrorResume` nhìn thấy tín hiệu lỗi và chuyển sang Publisher fallback; `onErrorContinue` tác động tới cách operator *upstream* xử lý lỗi khi nó đang xử lý một phần tử.
4. **Phạm vi có thể rò rỉ.** Tùy vị trí đặt, cấu hình continuation có thể ảnh hưởng các operator ở trước đó, kể cả operator trong library/service mà tác giả không thiết kế để bỏ qua lỗi. Vì vậy rất khó đọc code và kết luận chắc chắn phần nào đang có quyền bỏ lỗi.
5. **Không bảo đảm hành vi khi gặp operator không hỗ trợ.** Với các operator lồng nhau, ranh giới async, xử lý tài nguyên hoặc lỗi phát ra từ nguồn, đừng mặc định callback của `onErrorContinue` luôn được gọi.
6. **Callback nhận lỗi và giá trị bị bỏ.** `value` kiểu `Object`; với lỗi của mapper, nó thường là **giá trị đầu vào gây lỗi**, không nhất thiết là kiểu kết quả downstream. Không nên ép kiểu tùy tiện khi chain có nhiều bước chuyển kiểu.
7. **Callback cũng có thể ném lỗi.** Nếu handler tự ném exception, việc tiếp tục bình thường bị phá vỡ, có thể phát lỗi mới. Giữ logic ghi nhận lỗi ngắn, an toàn; không gọi dịch vụ blocking trong callback.

Quan trọng về an toàn dữ liệu: “bỏ qua bản ghi lỗi” cũng là một **quyết định nghiệp vụ**. Nếu hệ thống cần bảo đảm không mất sự kiện, không nên áp dụng continuation âm thầm. Cần định nghĩa metric, dead-letter queue, audit và chính sách retry/redrive khi phù hợp.

## 4. Ví dụ đối chiếu: `onErrorContinue` và `onErrorResume`

### 4.1. Bỏ phần tử lỗi trong `map` có hỗ trợ

```java
Flux<Integer> continued = Flux.just("10", "bad", "20")
        .map(Integer::parseInt)
        .onErrorContinue(
                NumberFormatException.class,
                (error, rejected) ->
                        System.out.println("Dropped: " + rejected)
        );
```

Khi đăng ký vào nguồn cold đồng bộ này, các giá trị thành công là `10` và `20`. Lời gọi `map` trên `"bad"` lỗi và giá trị được bỏ qua ở operator hỗ trợ continuation. **Đây là ví dụ minh họa hành vi có điều kiện**, không phải bảo đảm áp dụng cho mọi cách triển khai pipeline.

### 4.2. `onErrorResume` thay phần còn lại của luồng đã lỗi

```java
Flux<Integer> resumed = Flux.just("10", "bad", "20")
        .map(Integer::parseInt)
        .onErrorResume(NumberFormatException.class,
                error -> Flux.just(-1));
```

Kết quả là `10`, sau đó `-1`, rồi hoàn tất. **Không có `20`**: mapper lỗi làm upstream gốc kết thúc; `onErrorResume` chuyển sang Publisher fallback, chứ không quay lại giữa `Flux.just` để xử lý phần tử tiếp theo.

Đây là sự khác biệt quan trọng:

| Cách xử lý | Kết quả với `"10","bad","20"` trong ví dụ đơn giản | Phạm vi tác động |
|---|---|---|
| Không xử lý | `10`, sau đó `onError` | Lỗi terminal |
| `onErrorResume` bên ngoài `map` | `10`, rồi `-1`, sau đó complete | Thay **phần còn lại của cả chuỗi** bằng Publisher fallback |
| `onErrorContinue` sau `map` có hỗ trợ | `10`, bỏ `"bad"`, `20`, complete | Cơ chế continuation ở operator upstream tương thích |
| Recovery ở **mỗi inner Mono** | `10`, bỏ `"bad"`, `20`, complete | Một tác vụ/bản ghi riêng, dễ khoanh vùng |
| `handle` với `try/catch` | `10`, bỏ `"bad"`, `20`, complete | Kiểm tra và chuyển đổi tại một bước đồng bộ cụ thể |

Số giá trị giống nhau **không có nghĩa ngữ nghĩa và phạm vi lỗi giống nhau**.

## 5. Cách ưu tiên 1: xử lý đồng bộ tại `handle`

Nếu lỗi có thể dự đoán từ **dữ liệu đầu vào của một phép biến đổi đồng bộ**, dùng `handle` giúp biểu đạt quy tắc “một vào, không hoặc một ra” và đặt `try/catch` ngay bên cạnh phép parse:

```java
Flux<Integer> parsed = Flux.just("10", "bad", "20")
        .<Integer>handle((text, sink) -> {
            try {
                sink.next(Integer.parseInt(text));
            } catch (NumberFormatException error) {
                System.out.println("Rejected: " + text);
            }
        });
```

Ở đây:

- `sink.next(...)` chỉ được gọi khi `Integer.parseInt` thành công.
- Khi lỗi là `NumberFormatException`, handler **không gọi `sink.next`**, nên bản ghi đó không được phát.
- `handle` không buộc phải chuyển mọi lỗi thành “bỏ qua”. Có thể chọn `sink.error(error)` với lỗi nghiêm trọng để dừng pipeline, hoặc ghi nhận dữ liệu không hợp lệ vào cơ chế giám sát được phép.
- `handle` chỉ phù hợp với **thao tác đồng bộ**; không dùng nó để phát kết quả từ callback bất đồng bộ sau khi `BiConsumer` đã trả về.

Nếu không cần bắt exception, càng nên diễn đạt trực tiếp:

```java
Flux<String> cleaned = Flux.just("10", "", "20")
        .filter(s -> !s.isBlank());
```

`filter` rõ ràng hơn việc tạo exception chỉ để dùng `onErrorContinue`. Khi cần một phép biến đổi có thể không tạo giá trị mà không ném lỗi, cân nhắc `mapNotNull` (khi phiên bản Reactor và quy ước null phù hợp) hoặc `handle`.

### Ưu điểm và giới hạn của `handle`

Ưu điểm: vị trí quyết định bỏ dữ liệu nằm ngay trong code; không cấu hình continuation âm thầm cho operator ở xa; có thể xử lý từng exception theo nghiệp vụ. Giới hạn: quá nhiều logic `try/catch` phức tạp sẽ làm handler khó đọc; nên trích thành hàm parse/validate riêng và chọn loại lỗi thực sự dự kiến.

## 6. Cách ưu tiên 2: cô lập lỗi trên từng inner `Mono`

Khi mỗi phần tử có một tác vụ riêng (parse, validate, gọi API, ghi vào dịch vụ), ta có thể biến mỗi tác vụ thành **một Publisher con**, rồi đặt recovery **bên trong Publisher con ấy**:

```java
Flux<Integer> parsed = Flux.just("10", "bad", "20")
        .concatMap(text ->
                Mono.fromCallable(() -> Integer.parseInt(text))
                    .onErrorResume(NumberFormatException.class,
                            error -> Mono.empty())
        );
```

`Mono.fromCallable` trì hoãn phép parse tới subscription của từng inner Mono. Nếu parse lỗi, chỉ **inner Mono tương ứng** hoàn tất rỗng; `concatMap` tiếp tục với phần tử sau của outer Flux.

- Input `"10"` → inner Mono phát `10`.
- Input `"bad"` → inner Mono lỗi, `onErrorResume` đổi lỗi dự kiến thành `Mono.empty()`.
- Input `"20"` → inner Mono phát `20`.

Kết quả là `10`, `20`, complete, nhưng ranh giới xử lý rất rõ: **lỗi chỉ được phục hồi trong tác vụ của bản ghi đang xét**. Nếu **outer Publisher tự lỗi** thì recovery inner không tự nuốt lỗi outer; đây thường là hành vi mong muốn.

Tại sao dùng `concatMap` ở ví dụ? Nó giữ thứ tự xử lý/phát kết quả theo nguồn, thuận tiện khi cần ghi log đúng trình tự. `flatMap` có thể xử lý nhiều inner Publisher đồng thời, và trong tác vụ bất đồng bộ thứ tự hoàn thành không luôn bằng thứ tự đầu vào. Hãy chọn theo yêu cầu thứ tự, throughput và giới hạn concurrency.

### Cẩn thận với phép tính eager trong hàm tạo inner

Mẫu dưới đây không có boundary per-item tốt như tưởng tượng:

```java
// Phản ví dụ: parseInt có thể ném lỗi TRƯỚC khi Mono.just được tạo.
Flux<Integer> wrong = Flux.just("10", "bad", "20")
        .flatMap(text ->
                Mono.just(Integer.parseInt(text))
                    .onErrorResume(NumberFormatException.class,
                            error -> Mono.empty())
        );
```

`Integer.parseInt(text)` được Java đánh giá trước `Mono.just(...)`. Nếu nó ném exception, **inner Mono chưa tồn tại** để `onErrorResume` phía sau bắt lỗi đó. Sử dụng `Mono.fromCallable(() -> ...)` hoặc `Mono.defer(...)` khi cần thực sự trì hoãn logic có thể lỗi.

Ví dụ xử lý **Publisher trả từ API** nhưng phương thức tạo Publisher cũng có thể ném lỗi đồng bộ:

```java
// Mã minh họa: client.lookup(id) trả Mono<Result>.
Flux<Result> results = ids.flatMap(
        id -> Mono.defer(() -> client.lookup(id))
                .onErrorResume(RecordNotFoundException.class,
                        error -> Mono.empty()),
        8
);
```

`Mono.defer` trì hoãn việc gọi factory tạo Publisher cho đến subscription của inner; việc recovery được đặt **bên trong** scope của mỗi ID. `ids`, `client`, `Result`, `RecordNotFoundException` là thành phần giả định của dự án; đoạn này không phải chương trình biên dịch độc lập. Con số `8` là mức concurrency minh họa, phải cân nhắc giới hạn API đích.

**Lưu ý:** đừng nhầm `Mono.empty()` với thành công. Nếu mỗi bản ghi bắt buộc phải được xử lý hoặc báo cáo, có thể trả một kiểu kết quả rõ ràng, ví dụ `ValidationOutcome.Success`/`Failure` và chuyển lỗi tới hàng đợi xử lý lỗi, thay vì biến mất không có dấu vết.

## 7. Ví dụ đầy đủ Java 17+ có thể chạy

Ví dụ dưới đây cố ý giữ nguồn **cold, đồng bộ và hữu hạn** để thứ tự stdout không phụ thuộc mạng hay scheduler. Nó so sánh bốn cách xử lý cùng một dữ liệu; trường hợp `onErrorContinue` được đặt sau `map` là trường hợp operator hỗ trợ continuation. Dữ liệu và console log dùng tiếng Anh đơn giản để dễ đối chiếu.

Cấu trúc tệp:

```text
reactor-local-error-demo/
├── pom.xml
└── src/main/java/demo/Main.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-local-error-demo</artifactId>
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

public final class Main {
    public static void main(String[] args) {
        System.out.println("=== onErrorContinue ===");
        Flux.just("10", "bad", "20")
                .map(Integer::parseInt)
                .onErrorContinue(
                        NumberFormatException.class,
                        (error, value) ->
                                System.out.println("continue dropped: " + value)
                )
                .subscribe(
                        n -> System.out.println("continue next: " + n),
                        e -> System.out.println("continue error: " + e),
                        () -> System.out.println("continue complete")
                );

        System.out.println("=== onErrorResume on whole sequence ===");
        Flux.just("10", "bad", "20")
                .map(Integer::parseInt)
                .onErrorResume(NumberFormatException.class, error -> {
                    System.out.println(
                            "resume failure: " + error.getClass().getSimpleName()
                    );
                    return Flux.just(-1);
                })
                .subscribe(
                        n -> System.out.println("resume next: " + n),
                        e -> System.out.println("resume error: " + e),
                        () -> System.out.println("resume complete")
                );

        System.out.println("=== local per-item recovery ===");
        Flux.just("10", "bad", "20")
                .concatMap(raw -> {
                    Mono<Integer> item = Mono.fromCallable(
                            () -> Integer.parseInt(raw)
                    ).onErrorResume(NumberFormatException.class, error -> {
                        System.out.println("local dropped: " + raw);
                        return Mono.empty();
                    });
                    return item;
                })
                .subscribe(
                        n -> System.out.println("local next: " + n),
                        e -> System.out.println("local error: " + e),
                        () -> System.out.println("local complete")
                );

        System.out.println("=== handle for sync parsing ===");
        Flux.just("10", "bad", "20")
                .<Integer>handle((raw, sink) -> {
                    try {
                        sink.next(Integer.parseInt(raw));
                    } catch (NumberFormatException error) {
                        System.out.println("handle dropped: " + raw);
                    }
                })
                .subscribe(
                        n -> System.out.println("handle next: " + n),
                        e -> System.out.println("handle error: " + e),
                        () -> System.out.println("handle complete")
                );
    }
}
```

Từ thư mục `reactor-local-error-demo/`, cài Maven và JDK 17+, rồi chạy:

```bash
mvn -q compile exec:java
```

Stdout do chương trình tự in (không tính log của Maven nếu môi trường cấu hình khác):

```text
=== onErrorContinue ===
continue next: 10
continue dropped: bad
continue next: 20
continue complete
=== onErrorResume on whole sequence ===
resume next: 10
resume failure: NumberFormatException
resume next: -1
resume complete
=== local per-item recovery ===
local next: 10
local dropped: bad
local next: 20
local complete
=== handle for sync parsing ===
handle next: 10
handle dropped: bad
handle next: 20
handle complete
```

Giải thích trace:

- **`onErrorContinue`**: lỗi trong `map(Integer::parseInt)` ở phần tử `"bad"` được operator tương thích xử lý theo continuation; callback nhận giá trị bị bỏ, rồi `"20"` vẫn đi qua mapper.
- **`onErrorResume` ở ngoài**: map đã phát lỗi terminal, nên fallback `-1` thay đoạn còn lại. `"20"` từ nguồn gốc **không được phát**.
- **Local `concatMap`**: mỗi raw string được biến thành một `Mono<Integer>`. Inner Mono lỗi trên `"bad"` được chuyển thành `Mono.empty()` ngay tại chỗ; outer Flux vẫn xử lý `"20"`.
- **`handle`**: `try/catch` giữ quyền bỏ bản ghi tại đúng hàm parse, không dùng continuation lan ngược qua nhiều operator.

Ví dụ không dùng `.block()` trong controller, không gọi network và không giả định thread name. Vì nguồn đồng bộ đơn giản, các dòng xuất hiện theo đúng thứ tự nêu trên. Những đoạn code khác trong bài có biến tên dịch vụ giả định được đánh dấu riêng là minh họa, không phải chương trình độc lập này.

## 8. Vì sao `onErrorContinue` dễ gây tác dụng ngoài ý muốn?

### 8.1. Operator phía trước không cùng một hợp đồng continuation

Giả sử chain qua nhiều toán tử:

```java
Flux<Result> output = source
        .map(this::parse)
        .flatMap(this::remoteLookup)
        .map(this::toDto)
        .onErrorContinue((error, value) -> log(error, value));
```

Đây là **mã minh họa phụ thuộc ứng dụng**, không phải file chạy độc lập. Cách viết này không cho phép người đọc suy ra đáng tin rằng **mọi lỗi ở mọi nguồn** đều bị bỏ qua rồi pipeline tiếp tục bình thường. `remoteLookup` có thể trả Mono lỗi từ network; nguồn có thể báo terminal `onError`; một số operator không có cơ chế continuation. Ngoài ra `value` trong callback có thể thuộc **nhiều kiểu dữ liệu khác nhau** tùy vị trí lỗi.

Thay vì đặt một handler ở cuối toàn pipeline, hãy áp dụng recovery ngay ở từng boundary có ngữ nghĩa:

```java
Flux<Result> output = source.concatMap(raw -> {
    Mono<Result> one = Mono.defer(() -> parseAndLookup(raw))
            .onErrorResume(ExpectedBadRecordException.class, error -> {
                reportRejected(raw, error);
                return Mono.empty();
            });
    return one;
});
```

`parseAndLookup`, `reportRejected`, `Result`, `ExpectedBadRecordException` thuộc ứng dụng. Phần recovery chỉ ảnh hưởng **một inner Mono**, và exception không thuộc loại được chọn vẫn đi ra `onError`. Nếu cần throughput cao hơn, cân nhắc `flatMap` với giới hạn concurrency và yêu cầu thứ tự phù hợp.

### 8.2. Kết quả khác mong đợi sau `flatMap` và async boundary

Lỗi trong **inner Publisher** có lifecycle riêng. `onErrorContinue` đặt ở ngoài không phải lời hứa rằng mọi `onError` từ mỗi inner đều có thể bị chuyển thành “bỏ một record”. Một inner Mono có thể báo lỗi trực tiếp mà không biết thông tin nào là phần tử cần bỏ, và theo giao thức `onError` vẫn terminal.

Cần khoanh vùng:

```java
// service.find(id) trả Mono<Entity>; một ID không tìm thấy có thể báo lỗi.
Flux<Entity> entities = ids.flatMap(id ->
        service.find(id)
                .onErrorResume(EntityNotFoundException.class,
                        error -> Mono.empty()),
        4
);
```

Ở đây outer `ids` vẫn tiếp tục xử lý ID khác sau một lỗi **đã được phục hồi ở inner**, miễn là outer không tự lỗi và các phần khác không phát lỗi không xử lý. `flatMap` có thể thay thứ tự đầu ra khi các inner async hoàn tất khác nhau; nếu thứ tự quan trọng, dùng `concatMap` hoặc toán tử giữ thứ tự phù hợp.

### 8.3. Scope lan ngược qua code dùng chung

Thư viện mà một service gọi có thể chứa các toán tử `map` nội bộ và giả định rằng lỗi ở đó sẽ kết thúc Publisher. Một `onErrorContinue` được gắn sâu ở downstream có thể tác động ngược vào các toán tử hỗ trợ continuation trong vùng upstream **không do caller kiểm soát**. Khi ấy lỗi kỹ thuật nội bộ có nguy cơ bị biến thành dữ liệu bị loại âm thầm.

Khi phải bảo vệ một substream khỏi continuation áp dụng ở bên ngoài, Reactor có `onErrorStop()` để khôi phục cơ chế **STOP** ở phạm vi upstream tương ứng. Tuy vậy, đây là công cụ quản lý scope chuyên biệt; chính sách chính nên là **không mở rộng `onErrorContinue` qua thư viện không được thiết kế cho nó**, thay vì dựa vào vá scope sau đó.

### 8.4. Lỗi ở callback và side effect

Callback `(error, value) -> ...` nên được xem là nơi ghi nhận sự kiện đã bỏ, không phải luồng tác vụ nghiệp vụ phức tạp. Nếu callback tự ném exception, không thể mặc định rằng pipeline vẫn được tiếp tục. Nếu callback gọi API blocking trên event loop, nó còn có thể làm nghẽn thread xử lý tín hiệu.

Không dựa vào callback `onErrorContinue` để chắc chắn ghi thành công bản ghi vào dead-letter queue bên ngoài nếu việc ghi đó có thể lỗi bất đồng bộ. Trong trường hợp cần **bảo đảm ghi lại lỗi trước khi chấp nhận xử lý tiếp**, hãy đưa bước đó vào **inner Publisher** có kiểm soát, ví dụ `onErrorResume(error -> deadLetterPublisher(...).then(Mono.empty()))`, và quy định rõ xử lý khi ghi dead-letter thất bại.

## 9. Cách xử lý cục bộ cho dịch vụ WebFlux

Tình huống: một request nhận tập ID và cần truy xuất từng người dùng từ dịch vụ bên ngoài. Theo nghiệp vụ, chỉ riêng lỗi `CustomerNotFoundException` được phép bỏ qua; timeout, lỗi xác thực và lỗi 5xx phải nổi lên để client biết hệ thống gặp sự cố.

Ví dụ **bên trong ứng dụng có sẵn**, phụ thuộc các kiểu `Customer`, `CustomerView`, `customerClient`:

```java
Flux<CustomerView> fetchCustomers(Flux<Long> ids) {
    return ids.flatMap(id -> {
        Mono<CustomerView> perId = Mono.defer(
                    () -> customerClient.fetch(id)
                )
                .map(customer -> new CustomerView(
                        customer.getId(), customer.getName()))
                .onErrorResume(CustomerNotFoundException.class,
                        error -> Mono.empty());

        return perId;
    }, 8);
}
```

Diễn giải:

1. Outer `ids` đại diện cho các ID đến từ client hoặc một nguồn reactive.
2. `Mono.defer` trì hoãn lời gọi tạo Publisher, nên nếu factory ném exception dự kiến, nó được biểu diễn dưới dạng lỗi của inner Mono thay vì ném ra bên ngoài trước khi chain recovery hình thành.
3. `map` đổi dữ liệu customer thành DTO trong bộ nhớ.
4. `onErrorResume(CustomerNotFoundException.class, ...)` chỉ bắt một loại lỗi được cho phép của **một ID** và biến nó thành `Mono.empty()`.
5. Các ID khác vẫn có thể xử lý. Ngoại lệ không thuộc `CustomerNotFoundException` **không bị nuốt** và thường kết thúc kết quả, theo chính sách lỗi của `flatMap`.
6. `flatMap(..., 8)` giới hạn số inner Publisher hoạt động đồng thời trong chain này; không tự tạo giới hạn toàn hệ thống. Nếu kết quả phải giữ đúng thứ tự ID, đổi sang chiến lược tuần tự/giữ thứ tự.

Với API HTTP trả `Mono<...>`, controller thường **trả Publisher** để Spring WebFlux tự đăng ký; không tự gọi `.subscribe()` hay `.block()` rồi ghép danh sách một cách thủ công.

### Nên báo lỗi cục bộ thay vì bỏ dữ liệu khi nào?

Nếu số phần tử được yêu cầu phải khớp số phần tử kết quả (ví dụ tạo báo cáo đối soát), bỏ qua lỗi bằng `Mono.empty()` khiến mất thông tin. Thay vì `Flux<CustomerView>`, trả kiểu có thể chứa lỗi:

```java
// Minh họa kiểu API: các record/outcome và hàm thuộc ứng dụng.
Flux<FetchOutcome> results = ids.concatMap(id ->
        Mono.defer(() -> customerClient.fetch(id))
                .map(customer -> FetchOutcome.success(id, customer))
                .onErrorResume(CustomerNotFoundException.class,
                        error -> Mono.just(FetchOutcome.notFound(id)))
);
```

Với cách này, mỗi ID có một outcome có thể kiểm toán. Các lỗi hệ thống chưa được cho phép vẫn là terminal. **Phục hồi một lỗi** không nhất thiết có nghĩa phải bỏ phần tử; đôi khi nên chuyển lỗi thành dữ liệu có kiểu rõ ràng.

## 10. So sánh các toán tử xử lý lỗi phổ biến

| Toán tử/kỹ thuật | Công dụng | Có tiếp tục nguồn gốc sau phần tử lỗi không? |
|---|---|---|
| `doOnError` | Quan sát/log lỗi | Không; lỗi vẫn đi tiếp |
| `onErrorMap` | Ánh xạ `Throwable` thành lỗi khác | Không; vẫn là terminal error |
| `onErrorResume` | Khi upstream lỗi, chuyển sang Publisher dự phòng | Không tiếp tục upstream gốc; chạy fallback |
| `onErrorReturn` | Dùng một giá trị dự phòng cho lỗi phù hợp | Không; kết quả thay đoạn lỗi bằng giá trị |
| `onErrorComplete` | Chuyển lỗi phù hợp thành complete | Không; upstream gốc đã kết thúc |
| `retry` / `retryWhen` | Đăng ký lại nguồn sau lỗi theo chính sách | Không tiếp tục vị trí cũ; thường **thực thi lại** nguồn |
| `onErrorContinue` | Chỉ với operator hỗ trợ: bỏ một phần tử gây lỗi trong xử lý upstream | Có thể, **không bảo đảm** ở mọi nguồn/operator |
| `handle` + `try/catch` | Tự quyết định phát hay bỏ giá trị ở một bước đồng bộ | Có, nếu handler bắt lỗi dữ liệu dự kiến |
| Inner `Mono` + `onErrorResume` | Giới hạn lỗi và fallback vào một tác vụ/bản ghi | Có thể tiếp tục outer Publisher sau inner recovery |

Tại sao `retry` không phải giải pháp cho một record sai? Nếu nguồn cold phát `"10","bad","20"` và có `.retry(1)`, khi parse tới `"bad"` nó có thể subscribe lại từ đầu: `"10"` bị xử lý **lần nữa** và `"bad"` lại lỗi. Không có phép màu nào bảo đảm bỏ qua record lỗi; retry phải dựa trên loại lỗi và tính idempotent của thao tác, nhất là tác vụ ghi DB, gửi email hay thanh toán.

## 11. Kỷ luật thiết kế recovery để không che giấu lỗi

Nên trả lời các câu hỏi sau trước khi quyết định dùng một trong các cách bỏ lỗi:

1. **Lỗi dự kiến hay lỗi hệ thống?** Một giá trị CSV sai định dạng có thể là lỗi bản ghi; timeout database hay lỗi lập trình thường không nên bị tự động loại bỏ.
2. **Có nhận diện được bản ghi/ID gây lỗi không?** Đặt `onErrorResume` trong inner Publisher giúp giữ ID qua closure. Callback `onErrorContinue` có thể nhận `Object` khó liên hệ nghiệp vụ hơn.
3. **Có được phép mất bản ghi không?** Nếu phải đối soát, hãy phát `Success`/`Failure` thay vì `Mono.empty()`.
4. **Cần giữ thứ tự không?** `concatMap` giữ thứ tự; `flatMap` tăng độ đồng thời nhưng kết quả từ API có thể về khác thứ tự.
5. **Lỗi phía ngoài hay phía trong?** Inner recovery không chữa lỗi nguồn outer; điều này có thể hữu ích để phân biệt lỗi toàn luồng với lỗi một ID.
6. **Có retry không?** Retry có thể thực thi lại tác vụ và side effect; cần backoff, giới hạn lần thử và idempotency.
7. **Có ghi nhận dữ liệu bị bỏ không?** Metric số bản ghi lỗi, audit log, queue lỗi hoặc outcome giúp phát hiện pipeline đang âm thầm mất dữ liệu.
8. **Có giới hạn concurrency/bộ nhớ không?** Dù xử lý lỗi cục bộ tốt, quá nhiều inner Publisher đồng thời vẫn có thể gây quá tải.
9. **Có timeout và cancellation không?** Khi downstream hủy hoặc client ngắt kết nối, một số inner có thể bị hủy; recovery lỗi không có nghĩa mọi tác vụ chắc chắn hoàn thành.

Đối với việc tích hợp bên ngoài, không nên coi `.onErrorResume(e -> Mono.empty())` cho **mọi Throwable** là chuẩn mặc định. Nó có thể khiến service trả response thiếu dữ liệu mà không báo cho người dùng hoặc hệ thống giám sát.

## 12. Kiểm thử các trường hợp quan trọng

Nếu dùng `reactor-test`, `StepVerifier` có thể kiểm tra chính xác dữ liệu và terminal signals. Đoạn dưới đây là **ví dụ trong mã test** có import `reactor.test.StepVerifier`, không chạy độc lập nếu chưa thêm dependency `reactor-test` vào scope test:

```java
Flux<Integer> local = Flux.just("1", "bad", "2")
        .concatMap(raw -> Mono.fromCallable(() -> Integer.parseInt(raw))
                .onErrorResume(NumberFormatException.class,
                        error -> Mono.empty()));

StepVerifier.create(local)
        .expectNext(1, 2)
        .verifyComplete();
```

Với `onErrorResume` ở toàn chain:

```java
Flux<Integer> fallback = Flux.just("1", "bad", "2")
        .map(Integer::parseInt)
        .onErrorResume(NumberFormatException.class,
                error -> Flux.just(-1));

StepVerifier.create(fallback)
        .expectNext(1, -1)
        .verifyComplete();
```

Ngoài happy path, nên có test chứng minh **lỗi khác loại không bị nuốt**, lỗi của outer vẫn terminal, callback ghi nhận đúng ID, nguồn bất đồng bộ giữ/không giữ thứ tự như dự kiến, và các side effect không bị chạy lại ngoài ý muốn khi có retry.

Nếu muốn kiểm tra `onErrorContinue` trên một operator cụ thể, viết test trực tiếp với **đúng phiên bản Reactor và đúng chain sẽ deploy**, vì không thể coi đây là hợp đồng hỗ trợ chung cho mọi operator.

## 13. Các hiểu lầm thường gặp

**“`onErrorContinue` là một catch chung ở cuối pipeline.”** Sai. Nó tác động tới các operator upstream tương thích và không có phạm vi recovery rõ ràng giống inner `onErrorResume`.

**“Nếu một Mono HTTP trả `onError`, gắn `onErrorContinue` sẽ bỏ ID đó.”** Không có bảo đảm. Publisher có thể đã phát terminal `onError`; tốt hơn là `.onErrorResume(...)` ngay trên Mono của ID đó.

**“`onErrorResume` sẽ tiếp tục xử lý những phần tử còn lại của nguồn.”** Sai khi đặt bên ngoài nguồn đã lỗi. Nó chuyển sang fallback Publisher; để bỏ riêng lỗi của một phần tử, phục hồi bên trong Publisher con.

**“Bỏ một phần tử lỗi luôn an toàn.”** Sai. Với nghiệp vụ tài chính hoặc đồng bộ dữ liệu, bỏ một phần tử có thể gây sai tổng, thiếu bản ghi hoặc mất khả năng đối soát. Cần xác định chính sách chất lượng dữ liệu.

**“`doOnError` xử lý lỗi.”** Sai. Nó chỉ quan sát và có thể log; muốn recovery cần toán tử đúng.

**“`retry` tiếp tục từ bản ghi sau lỗi.”** Sai trong trường hợp thông thường. Retry subscribe lại nguồn, có thể chạy lại các phần tử đã xử lý.

**“Handler lỗi nên bắt `Throwable` rồi luôn complete.”** Nguy hiểm. Nó có thể che giấu lỗi lập trình, lỗi hạ tầng và tình huống cần báo cho client. Ưu tiên bắt loại lỗi nghiệp vụ dự kiến.

**“Nếu dùng `flatMap` và inner recovery thì thứ tự luôn giống nguồn.”** Sai với inner bất đồng bộ. `flatMap` có thể xen kẽ kết quả; dùng `concatMap`/kỹ thuật giữ thứ tự khi cần.

## 14. Bài tập tự kiểm tra

**Câu 1.** `Flux.just("1", "bad", "2").map(Integer::parseInt).onErrorResume(e -> Flux.just(0))` phát gì?

**Đáp án:** `1`, rồi `0`, hoàn tất. `"2"` không đi qua mapper vì nguồn ban đầu đã lỗi.

**Câu 2.** Vì sao `onErrorContinue` có thể không xử lý được `Flux.error(new IllegalStateException(...))`?

**Đáp án:** Đó là tín hiệu `onError` terminal được Publisher phát trực tiếp, không phải một phần tử trong operator tương thích có thể bỏ qua để tiếp tục.

**Câu 3.** Có thể tránh dùng `onErrorContinue` thế nào khi parse số trong một `Flux<String>`?

**Đáp án:** Dùng `handle` với `try/catch` tại bước parse để chỉ phát số hợp lệ, hoặc mỗi giá trị tạo một inner `Mono.fromCallable` và đặt `onErrorResume(NumberFormatException.class, ...)` trong inner đó.

**Câu 4.** Tại sao đặt `.onErrorResume(...)` bên trong `flatMap` khác đặt ở cuối pipeline?

**Đáp án:** Đặt trong inner chỉ phục hồi lỗi của **một công việc**; đặt ở cuối sẽ phục hồi lỗi của **toàn upstream** bằng fallback sau khi upstream terminal.

**Câu 5.** Nếu inner API trả lỗi “không tìm thấy” được phép bỏ qua, nhưng lỗi 500 không được bỏ qua, nên thiết kế gì?

**Đáp án:** Dùng `onErrorResume(NotFoundException.class, error -> Mono.empty())` tại inner Mono. Lỗi khác đi tiếp để hệ thống xử lý; cần log/metric/kiểu outcome nếu dữ liệu bị bỏ phải kiểm toán.

**Câu 6.** Khi một operator thư viện có `map` nội bộ, nguy cơ của `onErrorContinue` đặt sâu ở downstream là gì?

**Đáp án:** Cơ chế continuation có thể lan ngược tới operator upstream tương thích của thư viện, khiến lỗi nội bộ bị bỏ qua thay vì terminal như thư viện mong đợi.

**Câu 7.** Đầu ra của `Flux.just("1","bad","2").concatMap(s -> Mono.fromCallable(() -> Integer.parseInt(s)).onErrorResume(NumberFormatException.class, e -> Mono.empty()))` là gì?

**Đáp án:** `1`, `2`, complete; outer Flux tiếp tục sau inner Mono lỗi đã được chuyển thành empty.

## 15. Quy tắc lựa chọn nhanh

- **Biến đổi/kiểm tra đồng bộ một phần tử, lỗi dữ liệu có thể bỏ:** ưu tiên `filter`, `handle`, một hàm parse trả `Optional`, hoặc pipeline xử lý lỗi đúng tại điểm biến đổi.
- **Mỗi phần tử kích hoạt một Mono/Flux riêng:** ưu tiên đặt `onErrorResume` **bên trong inner Publisher**, lọc đúng loại exception; chọn `concatMap` hoặc `flatMap` theo thứ tự/concurrency.
- **Cả nguồn thất bại cần dự phòng:** dùng `onErrorResume` ở boundary thích hợp, chấp nhận rằng upstream gốc không “tiếp tục từ chỗ lỗi”.
- **Lỗi hệ thống nên báo ra:** giữ `onError` terminal, hoặc `onErrorMap` sang lỗi nghiệp vụ phù hợp; không nuốt toàn bộ lỗi.
- **Chỉ cân nhắc `onErrorContinue` khi thực sự nắm rõ operator upstream có hỗ trợ, phạm vi tác động, rủi ro discard và có test xác minh trên đúng pipeline.** Tránh coi nó là chính sách recovery mặc định của ứng dụng WebFlux.

**Ghi nhớ:** `onErrorContinue` là cơ chế đặc biệt nhằm bỏ phần tử lỗi **ở operator upstream có hỗ trợ**, không phải cách phục hồi mọi `onError` terminal. Để xử lý lỗi từng bản ghi một cách dễ đọc, dễ test và có thể kiểm toán, hãy **khoanh vùng recovery tại phần tử hoặc inner Publisher**, đồng thời giữ lỗi hệ thống nghiêm trọng đi ra theo hợp đồng Reactive Streams.
