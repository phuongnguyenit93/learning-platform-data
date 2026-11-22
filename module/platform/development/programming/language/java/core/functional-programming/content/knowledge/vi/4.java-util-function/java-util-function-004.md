# Supplier<T> cho thao tác cung cấp giá trị không nhận đối số

## Mục tiêu bài học

`Supplier<T>` là một functional interface trong gói `java.util.function`, đại diện cho **hành vi cung cấp một giá trị kiểu `T` khi được yêu cầu, không nhận đối số ở thời điểm gọi**. Nó hữu ích khi cần trì hoãn việc tạo dữ liệu, chuyển trách nhiệm tạo giá trị cho nơi khác, truyền factory hoặc cấu hình cách lấy giá trị dự phòng.

Sau bài này, bạn có thể:

- Đọc hợp đồng `T get()` và viết lambda, method reference hoặc constructor reference phù hợp.
- Phân biệt việc **tạo Supplier** với việc **gọi Supplier**, cũng như thời điểm và số lần tính giá trị.
- Dùng `Supplier` với `Optional.orElseGet`, `Stream.generate`, API factory và các thao tác cấp giá trị.
- Hiểu `Supplier` không đảm bảo tính thuần, cache, tính duy nhất, thread safety hoặc kết quả luôn khác `null`.
- Chọn đúng giữa `Supplier<T>`, `Function<T,R>`, `Callable<T>`, `Runnable` và các biến thể primitive.
- Nhận diện lỗi về checked exception, tác dụng phụ, nguồn dữ liệu mutable và xử lý tài nguyên.

## 1. Hợp đồng của Supplier<T>

Định nghĩa cốt lõi của API tương đương:

```java
package java.util.function;

@FunctionalInterface
public interface Supplier<T> {
    T get();
}
```

Đây là cách **minh họa chữ ký API**, không phải đoạn cần biên dịch lại thành `java.util.function.Supplier` trong ứng dụng. `Supplier<T>` có một phương thức trừu tượng `get()`:

| Thành phần | Ý nghĩa |
| --- | --- |
| `T` | Kiểu giá trị được cung cấp, có thể là `String`, `User`, `List<Order>`, ... |
| Danh sách tham số của `get()` | **Rỗng**, ký hiệu `()` |
| Kiểu trả về | `T`; mỗi lần gọi có thể trả một đối tượng hoặc giá trị khác |
| Mệnh đề `throws` | Không khai báo checked exception |
| Function descriptor | `() -> T` |

Vì `Supplier<T>` là functional interface, có thể triển khai bằng biểu thức lambda không tham số:

```java
Supplier<String> greeting = () -> "Xin chào";
String text = greeting.get(); // "Xin chào"
```

Phải import `java.util.function.Supplier` ở đầu file hoặc dùng tên đầy đủ. Phần `()` rất quan trọng: Supplier không có tham số, vì vậy `name -> name.toUpperCase()` là lambda **một tham số** và không thể gán cho `Supplier<String>`.

Một Supplier không nhận đối số ở **lần gọi `get()`**, nhưng hàm có thể **capture** biến từ phạm vi bên ngoài hoặc tham chiếu đến đối tượng/dịch vụ. Không nên diễn giải “không nhận tham số” thành “không phụ thuộc dữ liệu ngoài” hoặc “luôn trả cùng giá trị”.

## 2. Ba cách tạo Supplier phổ biến

### 2.1. Lambda không tham số

```java
Supplier<String> constant = () -> "READY";
Supplier<Integer> answer = () -> 42;
Supplier<List<String>> emptyNames = () -> new ArrayList<>();
```

`constant.get()` cho `"READY"`; `answer.get()` cho `42` (được boxing thành `Integer`). Với `emptyNames`, **mỗi lời gọi tạo một `ArrayList` mới** vì lệnh `new` được thực thi trong body mỗi khi gọi `get()`.

Ví dụ trên là những đoạn minh họa cần import `java.util.function.Supplier`, `java.util.List`, `java.util.ArrayList` và đặt bên trong phương thức hoặc khối khởi tạo Java thích hợp.

### 2.2. Constructor reference: `ClassName::new`

Khi lớp có constructor không tham số tương thích:

```java
Supplier<StringBuilder> builderFactory = StringBuilder::new;

StringBuilder first = builderFactory.get();
StringBuilder second = builderFactory.get();
System.out.println(first == second); // false
```

`StringBuilder::new` là cách gọn để cung cấp đối tượng mới; nó tương đương về chức năng với `() -> new StringBuilder()`. Mỗi lần gọi `get()` chạy constructor lại. Constructor phải tương thích với descriptor `() -> StringBuilder`; constructor đòi tham số bắt buộc sẽ không phù hợp với `Supplier` trừ khi dùng lambda capture tham số đã biết, như `() -> new Person("An")`.

Không suy luận mọi constructor reference đều tạo mới **theo mọi cách triển khai Supplier**: ví dụ `() -> existingObject` trả cùng tham chiếu đã có, còn `StringBuilder::new` mới bảo đảm tạo instance mới trong ví dụ này.

### 2.3. Method reference không tham số

```java
java.time.Clock clock = java.time.Clock.systemUTC();
Supplier<java.time.Instant> now = clock::instant;

Supplier<Double> random = Math::random;
```

`clock::instant` là method reference đã gắn receiver `clock`; `Math::random` tham chiếu phương thức static không tham số. Cả hai tương thích với `() -> T`. Giá trị của `now.get()` phụ thuộc thời gian, còn `random.get()` phụ thuộc nguồn ngẫu nhiên; không phải hàm thuần.

Method reference dạng `String::length` **chưa gắn receiver** nên cần một `String` làm tham số đầu vào; nó phù hợp với `Function<String,Integer>` hoặc `ToIntFunction<String>`, không phù hợp với `Supplier<Integer>`. Muốn Supplier, dùng method reference đã gắn receiver: `"Java"::length`.

## 3. Tạo Supplier khác với gọi get()

Xét:

```java
Supplier<String> value = () -> expensiveLookup();
```

Về mặt ý nghĩa, bước tạo lambda cung cấp một đối tượng biểu diễn hành vi; **body `expensiveLookup()` chưa được chạy**. Chỉ khi bên sử dụng gọi `value.get()` thì hoạt động tra cứu mới diễn ra. Đây là **trì hoãn thực thi** (deferred execution). Nếu bên sử dụng không gọi `get()`, phép tra cứu trong body không xảy ra.

Ngược lại:

```java
String alreadyComputed = expensiveLookup();
Supplier<String> value = () -> alreadyComputed;
```

`expensiveLookup()` chạy **trước** khi tạo Supplier; các lần `get()` sau chỉ trả lại cùng giá trị đã tính. Khi cần trì hoãn công việc, phải đưa công việc vào body Supplier, không tính trước rồi capture kết quả.

Supplier chỉ định **cách lấy giá trị**, không quy định **khi nào, bao nhiêu lần, ở luồng nào** người nhận sẽ gọi nó. Một API có thể không gọi, gọi một lần hoặc gọi nhiều lần; cần đọc hợp đồng của API đó. Sử dụng `Supplier` tự nó không tạo memoization, không làm kết quả cố định và không tự xây cơ chế cache.

### Supplier có thể tạo mới, trả lại hoặc thay đổi kết quả

```java
Supplier<String> sameText = () -> "A";
Supplier<List<String>> fresh = ArrayList::new;

java.util.concurrent.atomic.AtomicInteger sequence =
        new java.util.concurrent.atomic.AtomicInteger(0);
Supplier<Integer> next = sequence::incrementAndGet;
```

- `sameText.get()` trả nội dung `"A"` mỗi lần.
- `fresh.get()` tạo danh sách mới mỗi lần.
- `next.get()` lần lượt cho `1`, `2`, ... vì body làm thay đổi trạng thái.
  
Do đó, tên `Supplier` không chứa lời hứa rằng mỗi lần trả cùng một giá trị, không có side effect hay luôn cấp đối tượng mới.

## 4. Chương trình Java 17: trì hoãn, fallback, constructor và nhiều lần get()

Tạo file **`SupplierDemo.java`**:

```java
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import java.util.stream.Stream;

public class SupplierDemo {
    record Ticket(String level) {
        Ticket() {
            this("Standard");
        }
    }

    static String defaultName(AtomicInteger calls) {
        calls.incrementAndGet();
        return "Khách";
    }

    static String greet(Supplier<String> nameSupplier) {
        return "Xin chào, " + nameSupplier.get();
    }

    public static void main(String[] args) {
        AtomicInteger creations = new AtomicInteger();
        Supplier<String> fallback = () -> defaultName(creations);

        System.out.println("Trước get: " + creations.get());
        System.out.println("Chào: " + greet(fallback));
        System.out.println("Sau get: " + creations.get());

        Optional<String> present = Optional.of("An");
        String eager = present.orElse(defaultName(creations));
        String lazy = present.orElseGet(fallback);
        System.out.println("orElse: " + eager);
        System.out.println("orElseGet: " + lazy);
        System.out.println("Sau hai fallback: " + creations.get());

        String missing = Optional.<String>empty().orElseGet(fallback);
        System.out.println("Thiếu tên: " + missing);
        System.out.println("Tổng lượt tạo: " + creations.get());

        Supplier<Ticket> tickets = Ticket::new;
        System.out.println("Ticket: " + tickets.get().level());

        AtomicInteger ids = new AtomicInteger(100);
        Supplier<Integer> nextId = ids::incrementAndGet;
        System.out.println("IDs: " + nextId.get() + ", " + nextId.get());

        List<String> marks = Stream.generate(() -> "A")
                .limit(3)
                .toList();
        System.out.println("Stream: " + marks);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SupplierDemo.java
java SupplierDemo
```

**Kết quả đầu ra:**

```text
Trước get: 0
Chào: Xin chào, Khách
Sau get: 1
orElse: An
orElseGet: An
Sau hai fallback: 2
Thiếu tên: Khách
Tổng lượt tạo: 3
Ticket: Standard
IDs: 101, 102
Stream: [A, A, A]
```

**Đọc lần lượt luồng thực thi:**

1. `fallback` được tạo nhưng chưa gọi `defaultName`. Vì vậy bộ đếm `creations` bắt đầu ở `0`.
2. `greet(fallback)` gọi `nameSupplier.get()` đúng một lần. Body chạy `defaultName(creations)`, trả `"Khách"` và tăng bộ đếm lên `1`.
3. `present.orElse(defaultName(creations))` phải **đánh giá đối số** `defaultName(creations)` trước khi gọi `orElse`. Dù `present` đã chứa `"An"`, bộ đếm vẫn tăng thành `2`; kết quả cuối vẫn là `"An"`.
4. `present.orElseGet(fallback)` nhận một Supplier. Vì `present` có giá trị, nó không gọi `fallback.get()` và bộ đếm vẫn bằng `2`.
5. `Optional.empty().orElseGet(fallback)` gọi Supplier vì không có giá trị, trả `"Khách"` và tăng bộ đếm thành `3`.
6. `Ticket::new` tham chiếu constructor không tham số của `Ticket`. `tickets.get()` tạo một đối tượng có `level = "Standard"`.
7. `ids::incrementAndGet` là Supplier đọc và sửa bộ đếm; hai lần gọi trả `101` và `102`.
8. `Stream.generate(() -> "A").limit(3).toList()` yêu cầu ba phần tử từ Supplier và kết thúc với danh sách `[A, A, A]`.

Ví dụ minh họa rằng cùng một interface có thể diễn đạt giá trị cố định, factory, fallback hay phép sinh có trạng thái. Tính chất thực tế đến từ **body Supplier** và cách API sử dụng nó.

## 5. Supplier với Optional.orElseGet: lazy fallback

Một trường hợp rất phổ biến là lấy giá trị dự phòng khi `Optional<T>` rỗng:

```java
String result = maybeName.orElseGet(() -> loadDefaultName());
```

Lời gọi `loadDefaultName()` chỉ chạy nếu `maybeName` là empty. So sánh:

| API | Đối số | Thời điểm tính giá trị dự phòng |
| --- | --- | --- |
| `optional.orElse(value)` | Giá trị `T` | Biểu thức đối số được tính trước khi gọi, dù Optional đã có giá trị |
| `optional.orElseGet(supplier)` | `Supplier<? extends T>` | Gọi `supplier.get()` khi Optional rỗng |
| `optional.orElseThrow(supplier)` | `Supplier<? extends X>` cho ngoại lệ | Gọi Supplier để tạo ngoại lệ khi Optional rỗng |

Nếu fallback chỉ là một hằng số rẻ như `"N/A"`, `orElse("N/A")` dễ đọc và hoàn toàn phù hợp. Nếu fallback đắt tiền hoặc có side effect có chủ đích, `orElseGet` thường là lựa chọn đúng. Không nên gán một giá trị đã tính trước vào Supplier rồi cho rằng thao tác được trì hoãn.

```java
// Sai ý định lazy: loadDefaultName() đã chạy.
String cached = loadDefaultName();
String first = optional.orElseGet(() -> cached);

// Đúng nếu muốn chỉ chạy khi thiếu giá trị.
String second = optional.orElseGet(() -> loadDefaultName());
```

Các đoạn trong mục này là **minh họa ngữ cảnh**; `optional`, `loadDefaultName` cần được định nghĩa. Một `Supplier` có thể trả `null`; trong trường hợp Optional rỗng, `orElseGet` sẽ trả kết quả của Supplier, kể cả `null`. Đừng mặc định rằng chữ ký generic `T` đồng nghĩa không bao giờ null.

`Optional.orElseThrow(() -> new IllegalArgumentException("Missing"))` cũng nhận Supplier, nhưng đây là Supplier **tạo ngoại lệ**, chỉ được gọi khi không có giá trị. Nó khác với `orElseGet` vì mục đích là ném ngoại lệ.

## 6. Factory: tách người dùng khỏi cách tạo đối tượng

Thay vì để một dịch vụ quyết định tự khởi tạo phụ thuộc, có thể truyền một Supplier:

```java
// Minh họa với hai lớp được định nghĩa trong ứng dụng:
class Processor {
    private final Supplier<Connection> connectionFactory;

    Processor(Supplier<Connection> connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    void execute() {
        Connection connection = connectionFactory.get();
        // Sử dụng connection, quản lý đóng tài nguyên theo hợp đồng.
    }
}
```

Đây là **mã minh họa kiến trúc**, không phải chương trình độc lập; kiểu `Connection` và quy trình đóng tài nguyên phụ thuộc thư viện cụ thể. Điểm chính là `Processor` chỉ biết có thể yêu cầu một `Connection` khi cần, không biết cách cấu hình/khởi tạo nó. Trong kiểm thử, truyền Supplier trả fake thay cho kết nối thật.

Nhưng cần xác định rõ **vòng đời**:

- `() -> new Service()` có thể tạo Service mới ở mỗi lần gọi.
- `() -> existingService` trả về cùng một instance.
- Một Supplier được bọc cache có thể tạo một lần rồi tái sử dụng.
- Một Supplier đọc cấu hình hoặc dữ liệu remote có thể trả giá trị khác ở các thời điểm khác nhau.

`Supplier<T>` **không nói** sản phẩm là singleton hay prototype. Nếu tài nguyên cần đóng (`AutoCloseable`), người gọi và bên cấp phát phải có hợp đồng rõ ai sở hữu nó và lúc nào đóng. Việc truyền Supplier không tự giải quyết quản lý tài nguyên.

### Constructor cần tham số thì làm sao?

Giả sử `Product` có constructor `Product(String name)`. Method reference `Product::new` với một đối số tương thích `Function<String,Product>`, **không tương thích** `Supplier<Product>`. Nếu tên đã biết tại nơi cấu hình factory, có thể capture:

```java
// Minh họa: Product(String) phải được định nghĩa trước.
String configuredName = "Book";
Supplier<Product> defaultProduct =
        () -> new Product(configuredName);
```

Hãy dùng `Function<String,Product>` nếu tên phải được quyết định **mỗi lần gọi**; dùng Supplier khi không cần truyền thêm đối số vào `get()`.

## 7. Sinh phần tử bằng Stream.generate

`Stream.generate(Supplier<? extends T>)` xây một Stream vô hạn về mặt nguồn, **sequential** và **unordered** theo API. Mỗi khi pipeline cần một phần tử, Supplier có thể được gọi để cung cấp phần tử đó. Vì nguồn không có giới hạn, cần thao tác như `limit(n)` hoặc cơ chế dừng phù hợp trước khi thu toàn bộ kết quả.

```java
List<Integer> squares = java.util.stream.Stream
        .generate(new java.util.concurrent.atomic.AtomicInteger(0)::incrementAndGet)
        .limit(4)
        .map(n -> n * n)
        .toList();
```

Đoạn trên **là cú pháp Java hợp lệ**: biểu thức `new AtomicInteger(0)::incrementAndGet` đánh giá receiver một lần khi tạo method reference, sau đó dùng cùng bộ đếm cho các lần gọi `get()`. Tuy nhiên, tách bộ đếm thành biến riêng sẽ giúp người đọc thấy rõ vòng đời và trạng thái của nó. Cách rõ ràng, có thể biên dịch là tách nguồn trạng thái:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger();
java.util.function.Supplier<Integer> next =
        counter::incrementAndGet;

java.util.List<Integer> squares = java.util.stream.Stream
        .generate(next)
        .limit(4)
        .map(n -> n * n)
        .toList(); // [1, 4, 9, 16]
```

Trong tài liệu học, nên dùng ví dụ thứ hai để rõ bộ đếm được tạo **một lần**, rồi tăng qua các lần gọi. Mẫu `Stream.generate(() -> "A").limit(3)` trong chương trình chính là nguồn cố định.

**Lưu ý:** `generate` không bảo đảm phép sinh là thuần hay an toàn khi chạy song song. Supplier thay đổi shared mutable state có thể làm kết quả phụ thuộc số lần, thứ tự và luồng thực thi. Nếu cần sinh số nguyên liên tiếp, `IntStream.rangeClosed(1, 4)` thường rõ ràng hơn một Supplier có bộ đếm. Trong ví dụ số đếm, dùng `AtomicInteger` tránh cập nhật bị mất nhưng không biến phép sinh thành thuần hàm.

Các thao tác terminal khác nhau cũng có thể yêu cầu số phần tử khác nhau; không giả định Supplier sẽ luôn được gọi đúng `n` lần trong mọi pipeline tối ưu hóa hay trong mọi kiểu xử lý. Với nguồn và pipeline minh họa tuần tự đơn giản `limit(n).toList()`, ta nhận đúng `n` phần tử.

## 8. Supplier cho giá trị mặc định và khởi tạo theo nhu cầu

Một số API Java nhận Supplier để hoãn tạo giá trị hoặc lỗi:

```java
// Optional<T>
String fallback = optional.orElseGet(() -> "Guest");

// Objects.requireNonNullElseGet: dùng Supplier nếu value == null;
// Supplier phải cung cấp một kết quả khác null, nếu không sẽ ném NPE.
String nonNull = java.util.Objects.requireNonNullElseGet(
        possiblyNull,
        () -> "Guest"
);

// Nếu Optional rỗng, tạo và ném exception.
String required = optional.orElseThrow(
        () -> new IllegalStateException("No name")
);
```

Đây là đoạn minh họa, cần khai báo `optional` và `possiblyNull` trong phạm vi sử dụng. API khác có thể chọn gọi Supplier nhiều lần, chạy ở một thread khác hoặc có điều kiện riêng. Khi lập trình với Supplier, hãy đọc rõ hợp đồng của **phương thức nhận nó**.

### Supplier và Map.computeIfAbsent không cùng chữ ký

`Map.computeIfAbsent(K, Function<? super K,? extends V>)` nhận một **Function có tham số khóa `K`**, không nhận `Supplier<V>` trực tiếp:

```java
java.util.Map<String, String> cache = new java.util.HashMap<>();
Supplier<String> defaultUser = () -> "Guest";

String user = cache.computeIfAbsent(
        "profile:42",
        key -> defaultUser.get()
);
```

Hàm mapping ở đây nhận `key` rồi quyết định gọi `Supplier.get()`. Nếu quá trình tạo giá trị thực sự phụ thuộc khóa, viết `key -> loadByKey(key)` rõ hơn việc cố ép thành Supplier. Khi xét concurrency, `HashMap` không tự bảo vệ truy cập đồng thời; `ConcurrentHashMap` có hợp đồng và hạn chế riêng cho computation, không dùng một `HashMap` thường để cache từ nhiều luồng mà thiếu đồng bộ.

### Supplier với ThreadLocal.withInitial

`ThreadLocal.withInitial(Supplier<? extends S>)` nhận cách tạo giá trị ban đầu **cho từng thread khi cần**:

```java
ThreadLocal<StringBuilder> buffer =
        ThreadLocal.withInitial(StringBuilder::new);
```

Mỗi thread có thể nhận `StringBuilder` riêng khi lần đầu gọi `buffer.get()`. Việc này giúp cô lập dữ liệu theo thread nhưng vẫn cần chú ý vòng đời, đặc biệt khi dùng thread pool: gọi `remove()` ở thời điểm phù hợp để tránh giữ trạng thái lâu hơn mong muốn.

## 9. Checked exception: Supplier.get() không khai báo throws

`Supplier<T>.get()` không có `throws IOException` hoặc checked exception nào. Do đó lambda gán cho Supplier không được để checked exception thoát ra trực tiếp:

```java
// Không biên dịch nếu readFile() khai báo throws IOException.
Supplier<String> invalid = () -> readFile();
```

Có thể thiết kế theo một trong những cách sau:

**Tách I/O khỏi chỗ cần Supplier thuần.** Đọc dữ liệu ở lớp biên rồi truyền một Supplier trả kết quả đã chuẩn hóa:

```java
// Minh họa: value đã được đọc và xác thực.
String value = readFile(); // ở phương thức có throws hoặc try/catch
Supplier<String> ready = () -> value;
```

Điều này không trì hoãn I/O; nó làm rõ trách nhiệm.

**Bắt ngoại lệ trong lambda**, xử lý fallback nếu hợp đồng nghiệp vụ cho phép, hoặc bọc thành unchecked exception và giữ nguyên cause:

```java
Supplier<String> safe = () -> {
    try {
        return readFile();
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException(e);
    }
};
```

Bọc ngoại lệ làm thay đổi cách caller nhận lỗi; cần cân nhắc chính sách retry, logging và giao dịch.

**Định nghĩa checked supplier riêng** khi cần giữ checked exception trong hợp đồng:

```java
@FunctionalInterface
interface ThrowingSupplier<T, E extends Exception> {
    T get() throws E;
}

ThrowingSupplier<String, java.io.IOException> fileSource =
        () -> readFile();
```

Không thể truyền trực tiếp `ThrowingSupplier` cho phương thức đòi `Supplier`, bởi chúng là hai interface khác nhau. Cần adapter có quy tắc xử lý lỗi phù hợp. Các đoạn trên là **minh họa** với `readFile()` được giả định là phương thức đã có và khai báo `throws IOException`.

Ngoại lệ unchecked như `IllegalStateException` vẫn có thể được ném từ Supplier và lan đến nơi gọi `get()` dù không liệt kê trong `throws`.

## 10. Supplier so với các functional interface khác

| Interface | Descriptor | Khác biệt quan trọng |
| --- | --- | --- |
| `Supplier<T>` | `() -> T` | Không tham số, có kết quả |
| `Function<T,R>` | `(T) -> R` | Có một đầu vào; biến đổi dữ liệu |
| `BiFunction<T,U,R>` | `(T,U) -> R` | Có hai đầu vào |
| `Predicate<T>` | `(T) -> boolean` | Trả điều kiện logic |
| `Consumer<T>` | `(T) -> void` | Nhận giá trị, thực hiện hành động |
| `Runnable` | `() -> void` | Không tham số, không trả kết quả |
| `Callable<T>` | `() -> T throws Exception` | Có kết quả, cho phép checked exception |
| `IntSupplier` | `() -> int` | Trả `int` nguyên thủy |
| `LongSupplier` | `() -> long` | Trả `long` nguyên thủy |
| `DoubleSupplier` | `() -> double` | Trả `double` nguyên thủy |
| `BooleanSupplier` | `() -> boolean` | Trả `boolean` nguyên thủy |

`Callable<T>` thuộc `java.util.concurrent`, thường dùng cho tác vụ có kết quả trong các cơ chế thực thi bất đồng bộ. Nó khác `Supplier<T>` ở khả năng khai báo `throws Exception`; không có nghĩa mọi `Callable` đều tự chạy trên thread khác.

Ví dụ:

```java
java.util.function.IntSupplier count = () -> 3;
java.util.function.BooleanSupplier ready = () -> true;
java.util.concurrent.Callable<String> task = () -> "done";
Runnable notification = () -> System.out.println("Done");
```

Với nhiệm vụ chỉ cần thực hiện hành động, không có kết quả, `Runnable` có thể thể hiện ý nghĩa tốt hơn `Supplier<Void>` phải trả `null`. Với phép tính sinh số lớn liên tục, primitive supplier giúp tránh boxing thường có khi dùng `Supplier<Integer>` hoặc `Supplier<Long>`.

### Supplier và API bất đồng bộ

`CompletableFuture.supplyAsync(supplier)` nhận Supplier rồi chạy hàm cung cấp giá trị trong một tác vụ bất đồng bộ (với executor mặc định hoặc executor được truyền). Lỗi runtime từ Supplier sẽ làm future hoàn thành bất thường; thời điểm chạy và thread được quyết định bởi cơ chế thực thi, không phải bởi chính interface Supplier.

```java
java.util.concurrent.CompletableFuture<Integer> future =
        java.util.concurrent.CompletableFuture.supplyAsync(() -> 40 + 2);

int result = future.join(); // 42 nếu thực thi thành công
```

Đây là ví dụ minh họa; khi áp dụng thực tế cần cân nhắc executor, hủy tác vụ, thời gian chờ và xử lý lỗi. Không được chia sẻ một Supplier có mutable state giữa nhiều tác vụ rồi mặc định nó thread-safe.

## 11. Vấn đề về null, side effect và thread safety

**Kết quả null.** Chữ ký `T get()` không tự cấm `null`. Một Supplier có thể trả `null`; API sử dụng nó có thể cho phép, cấm hoặc xử lý riêng. Ví dụ `Objects.requireNonNullElseGet` yêu cầu Supplier cung cấp giá trị khác null khi đầu vào null. Nếu không có giá trị, cân nhắc sử dụng `Optional<T>` ở ranh giới API có ý nghĩa thay vì để caller đoán.

**Side effect.** `Supplier` có thể gọi network, ghi log, tăng bộ đếm, tạo tệp hoặc phát sự kiện. Một API nhận Supplier có thể gọi lại nếu cần; do đó, thao tác **không idempotent** như thu phí, gửi email hoặc ghi đơn hàng không nên được ẩn trong `get()` nếu không có hợp đồng gọi rõ và bảo vệ chống lặp.

**Stateful Supplier.** Dùng bộ đếm hoặc `Iterator` bên trong khiến thứ tự gọi ảnh hưởng kết quả; cần nói rõ ngữ nghĩa, đặc biệt khi dùng trong Stream hoặc chương trình nhiều thread.

**Concurrency.** `Supplier<T>` không cam kết thread-safe. `AtomicInteger` chỉ bảo vệ chính bộ đếm; những object khác được capture cũng phải được xem xét. Nếu Supplier có shared mutable state, phải dùng cơ chế đồng bộ phù hợp hoặc tránh chia sẻ giữa thread.

**Memoization.** `Supplier` mặc định không cache. Nếu cần chỉ tính lần đầu rồi dùng lại, phải tự thiết kế hoặc dùng một holder/cache có hợp đồng về synchronization, xuất bản đối tượng, xử lý null và retry khi thất bại. Một Supplier cache không nhất thiết tương đương Supplier tạo mới; cần xem caller có kỳ vọng mỗi lần nhận instance riêng không.

**Quản lý tài nguyên.** `Supplier<InputStream>` có thể mở stream mới ở mỗi lần `get()`; nơi dùng phải đóng stream theo hợp đồng. Một Supplier trả lại cùng stream đã đóng ở lần trước sẽ không phù hợp nếu caller nghĩ rằng nó cấp kết nối/tài nguyên mới.

## 12. Những lỗi thường gặp và cách sửa

1. **Nhầm Supplier với Function:** `x -> x.trim()` có một tham số. Với Supplier dùng `() -> "text"`; khi muốn nhận dữ liệu lúc gọi, dùng `Function<String,String>`.
2. **Lẫn tạo Supplier và thực thi:** `Supplier<T> s = () -> expensive()` mới trì hoãn; `T x = expensive(); Supplier<T> s = () -> x` đã tính trước.
3. **Tưởng rằng `get()` chỉ chạy một lần:** kiểm tra hợp đồng nơi dùng; nếu gọi nhiều lần, body có thể chạy nhiều lần.
4. **Dùng `orElse(expensive())` mà mong lazy:** đối số vẫn được tính. Dùng `orElseGet(() -> expensive())` nếu chỉ cần fallback khi thiếu.
5. **Truyền constructor reference sai arity:** `Product::new` với constructor đòi tham số không dùng trực tiếp làm `Supplier<Product>`; capture cấu hình bằng lambda hoặc dùng `Function`.
6. **Giấu checked exception:** `Supplier.get()` không khai báo checked exception. Bắt/chuyển lỗi có chủ đích hoặc dùng checked functional interface riêng.
7. **Cho rằng Supplier luôn thuần:** Supplier có thể đọc clock, random, database và sửa state. Đánh giá cụ thể body.
8. **Lạm dụng `Stream.generate` không giới hạn:** pipeline vô hạn không nên gọi `toList()` nếu không có điều kiện dừng; dùng `limit` hoặc nguồn hữu hạn phù hợp.
9. **Không xác định vòng đời đối tượng:** một Supplier có thể trả singleton hay instance mới; viết rõ nhu cầu sở hữu/đóng tài nguyên.
10. **Cho rằng `Supplier<Integer>` luôn tối ưu cho số nguyên:** nếu áp lực boxing quan trọng, xem `IntSupplier`.
11. **Lẫn `get()` của Supplier và `get()` của Optional:** `Supplier.get()` thực thi hành vi cấp giá trị; `Optional.get()` lấy giá trị đã hiện diện hoặc ném `NoSuchElementException` khi rỗng.

## 13. Bài tập củng cố

**Bài 1 — Trì hoãn.** Viết `Supplier<String>` trả `"Hello"`. In một thông báo ở trong lambda rồi kiểm tra thông báo xuất hiện trước hay sau khi gọi `get()`.

**Bài 2 — Nhiều lần gọi.** Dùng `AtomicInteger` để viết `Supplier<Integer>` cấp số tăng dần từ `1`. Gọi ba lần, giải thích vì sao kết quả không cố định dù `get()` không nhận tham số.

**Bài 3 — Factory.** Với class `Box` có constructor không tham số, viết `Supplier<Box>` dùng constructor reference. So sánh danh tính của hai instance được lấy bằng `get()`.

**Bài 4 — Fallback.** Giả sử `Optional.of("An")` và phương thức `loadGuest()` có log. So sánh số lần log khi gọi `orElse(loadGuest())` và `orElseGet(() -> loadGuest())`.

**Bài 5 — Lựa chọn interface.** Nên chọn interface nào cho từng nhu cầu: cung cấp `long` không tham số; biến đổi một `String` thành `Integer`; chạy tác vụ không trả kết quả; tác vụ có thể ném `IOException` ở hợp đồng?

**Bài 6 — Debug.** Một ứng dụng dùng `Stream.generate(database::fetchNext).limit(10)`. Hãy xem xét khả năng source trả `null`, số lời gọi, tính hữu hạn của dữ liệu, thread safety, vòng đời kết nối và chính sách retry trước khi dùng.

**Gợi ý đáp án:** (1) `() -> "Hello"`; body chỉ chạy khi `get()` được gọi. (2) `AtomicInteger counter = new AtomicInteger(); Supplier<Integer> next = counter::incrementAndGet;` trả `1, 2, 3`. (3) `Supplier<Box> f = Box::new;`; nếu constructor tạo object mới thì hai lần `get()` trả hai tham chiếu khác nhau. (4) `orElse` đánh giá fallback ngay; `orElseGet` bỏ qua fallback khi Optional có giá trị. (5) `LongSupplier`, `Function<String,Integer>`, `Runnable`, `Callable<T>` hoặc functional interface riêng khai báo `throws IOException` tùy hợp đồng.

## 14. Tóm tắt áp dụng

Khi cần truyền **hành vi cấp giá trị không nhận đối số**, `Supplier<T>` là hợp đồng ngắn gọn: `() -> T`. Lambda `() -> ...`, constructor reference và method reference đã gắn receiver là những cách hiện thực phổ biến. Điểm mạnh của Supplier là **trì hoãn việc tạo/lấy giá trị đến khi nơi dùng thực sự gọi `get()`**, đặc biệt trong fallback hoặc factory.

Để dùng đúng, hãy xác định ai gọi, khi nào gọi, có thể gọi mấy lần, giá trị có được tạo mới hay cache, có thể null không, có side effect không, có checked exception không và có cần đồng bộ/đóng tài nguyên không. Những điều này nằm trong **hợp đồng của body Supplier và API sử dụng nó**, không được bảo đảm chỉ bởi tên `Supplier`.
