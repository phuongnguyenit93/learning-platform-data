# orElse và orElseGet: thời điểm tính giá trị thay thế trong Java Optional

## 1. Mục tiêu bài học

`Optional<T>` đại diện cho một giá trị **có thể hiện diện hoặc vắng mặt**, nhằm làm rõ trường hợp không tìm thấy kết quả mà không phải truyền `null` một cách mơ hồ. Khi muốn chuyển một `Optional<T>` thành giá trị kiểu `T`, hai cách quen thuộc là:

- **`orElse(T other)`:** nhận sẵn **một giá trị** thay thế.
- **`orElseGet(Supplier<? extends T> supplier)`:** nhận **một hàm cung cấp giá trị**, chỉ gọi hàm khi `Optional` rỗng.

Điểm khác biệt quyết định là **thời điểm tính giá trị thay thế**. Với `orElse(computeDefault())`, Java gọi `computeDefault()` *trước* khi gọi `orElse`, ngay cả khi Optional đã có giá trị. Với `orElseGet(() -> computeDefault())`, thân lambda chỉ chạy khi Optional không có giá trị.

Sau bài học, bạn có thể giải thích và dự đoán chính xác kết quả của cả hai phương thức, chọn giải pháp khi fallback tốn chi phí/có tác dụng phụ/có thể ném exception, hiểu các tình huống `null` và sử dụng API này trong mã nghiệp vụ an toàn. `orElse` và `orElseGet` có từ Java 8 và **vẫn là API hiện hành** trong các JDK hiện đại. Các chương trình chạy hoàn chỉnh bên dưới ưu tiên Java 17+; những API mới hơn được ghi rõ phiên bản.

## 2. Khai báo và bảng hành vi

Hai phương thức của `java.util.Optional<T>` có chữ ký:

```java
T orElse(T other);
T orElseGet(Supplier<? extends T> supplier);
```

*Đây là chữ ký để đọc API, không phải chương trình Java độc lập.*

Cả hai đều trả về `T`, **không** trả `Optional<T>`. Kết quả không tự được bao trong Optional mới.

| Trường hợp | `orElse(value)` | `orElseGet(supplier)` |
| --- | --- | --- |
| Optional **có** giá trị | Trả giá trị bên trong | Trả giá trị bên trong |
| Optional **rỗng** | Trả đối số `value` | Gọi `supplier.get()` và trả kết quả |
| Thời điểm tính fallback | Biểu thức đối số được tính trước lời gọi `orElse` | Thân supplier chỉ chạy khi rỗng |
| Hình dạng đối số | Giá trị kiểu `T` | `Supplier<? extends T>` |
| Có thể trả `null`? | Có, nếu `other == null` và Optional rỗng | Có, nếu supplier trả `null` và Optional rỗng |
| Thao tác I/O hoặc tính toán đắt tiền | Có thể chạy thừa khi Optional đã có giá trị | Không chạy nếu Optional đã có giá trị |

**Lưu ý quan trọng về cách diễn đạt:** Không phải bản thân `orElse` tự chạy fallback; **Java đánh giá đối số lời gọi phương thức** trước khi vào thân `orElse`. Vì vậy một biến fallback đã được tính từ trước cũng tốn công bất kể phương thức nào bạn dùng.

`Supplier<T>` là functional interface với phương thức `T get()`. Lambda `() -> loadDefault()` và method reference `MyService::loadDefault` là hai cách truyền công việc **chưa thực thi** cho `orElseGet`.

## 3. Chứng minh bằng log: `orElse` tính sớm, `orElseGet` tính muộn

Lưu tệp `EagerLazyDemo.java`:

```java
import java.util.Optional;

public class EagerLazyDemo {
    private static String createDefault(String label) {
        System.out.println("compute " + label);
        return "generated-" + label;
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("saved");

        String eager = present.orElse(createDefault("eager"));
        System.out.println("orElse present = " + eager);

        String lazy = present.orElseGet(
                () -> createDefault("lazy"));
        System.out.println("orElseGet present = " + lazy);

        Optional<String> empty = Optional.empty();

        String emptyEager = empty.orElse(
                createDefault("empty-eager"));
        System.out.println("orElse empty = " + emptyEager);

        String emptyLazy = empty.orElseGet(
                () -> createDefault("empty-lazy"));
        System.out.println("orElseGet empty = " + emptyLazy);
    }
}
```

Biên dịch và chạy:

```bash
javac EagerLazyDemo.java
java EagerLazyDemo
```

Stdout chính xác:

```text
compute eager
orElse present = saved
orElseGet present = saved
compute empty-eager
orElse empty = generated-empty-eager
compute empty-lazy
orElseGet empty = generated-empty-lazy
```

**Giải thích theo thứ tự thực thi:**

1. `present.orElse(createDefault("eager"))`: JVM thực thi lời gọi `createDefault` trước, in `compute eager`; sau đó `orElse` nhận chuỗi mặc định đã tính nhưng trả `saved` vì giá trị đã có. Fallback bị tính **thừa**.
2. `present.orElseGet(() -> createDefault("lazy"))`: Java chuẩn bị một `Supplier`; thân lambda **không chạy** vì Optional có `saved`.
3. `empty.orElse(createDefault("empty-eager"))`: vẫn tính đối số trước; lúc này kết quả fallback thực sự được dùng.
4. `empty.orElseGet(() -> createDefault("empty-lazy"))`: chỉ khi biết Optional rỗng, `orElseGet` mới gọi `Supplier.get()` để tạo fallback.

Kết luận: **Giá trị trả về** có thể giống nhau, nhưng **chi phí và tác dụng phụ** của hai cách có thể rất khác nhau.

## 4. Vì sao đây là quy tắc Java, không chỉ là một “tối ưu” của Optional?

Xét đoạn mã minh họa:

```java
String fallback = queryRemoteService();
String value = optional.orElse(fallback);
```

*Đây là snippet: `optional` và `queryRemoteService` phải được định nghĩa trong chương trình thật.*

Hai dòng trên luôn gọi `queryRemoteService()` khi chạy đến dòng thứ nhất, **bất kể Optional có giá trị hay không**. Thay `orElse(fallback)` thành `orElseGet(() -> fallback)` ở dòng thứ hai **không hoàn tác được công việc đã thực hiện**.

Muốn thực sự trì hoãn việc tính, hãy chuyển chính công việc vào thân supplier:

```java
String value = optional.orElseGet(
        () -> queryRemoteService());
```

Nếu không cần dùng đối số, dùng method reference:

```java
String value = optional.orElseGet(
        MyService::queryRemoteService);
```

*Hai đoạn là mẫu cú pháp minh họa; `MyService.queryRemoteService` phải là static method không đối số và trả kiểu tương thích. Với instance method, có thể dùng `service::queryRemoteService`.*

**Phân biệt ba thứ:**

- `queryRemoteService()` — **gọi ngay**, trả `T` để truyền cho `orElse`.
- `() -> queryRemoteService()` — **tạo Supplier**, còn việc gọi hàm trong thân lambda chờ đến lúc `get()` được thực thi.
- `queryRemoteService` — chỉ là tên phương thức, không phải giá trị `T` hoặc `Supplier<T>` hợp lệ cho cả hai API; cần lambda/method reference đúng cú pháp.

Một chú ý khác: biểu thức tạo/capture đối tượng ở **ngoài** thân lambda có thể vẫn được đánh giá sớm. Ví dụ:

```java
RemoteClient client = new RemoteClient(expensiveConfiguration());
String value = optional.orElseGet(client::loadDefault);
```

Mẫu trên vẫn khởi tạo `client` và gọi `expensiveConfiguration()` trước, dù `loadDefault()` chỉ chạy khi Optional rỗng. Để trì hoãn *toàn bộ* công việc fallback, cần đặt đúng phần tốn chi phí bên trong supplier, cân nhắc quản lý vòng đời của client theo kiến trúc thực tế.

## 5. Khi nào chọn `orElse`, khi nào chọn `orElseGet`?

**Ưu tiên `orElse(...)`** khi giá trị mặc định đã có hoặc tạo rất rẻ và không có side effect:

```java
String label = optional.orElse("Unknown");
int retries = retryOptional.orElse(3);
String name = nameOptional.orElse(DEFAULT_NAME);
```

*Các dòng này là snippet; biến Optional/constant phải có kiểu tương thích. Với kiểu nguyên thủy dùng `OptionalInt` có `orElse(int)`.*

**Ưu tiên `orElseGet(...)`** khi giá trị mặc định cần tạo bằng công việc tốn chi phí hoặc có tác dụng phụ:

```java
String profile = profileOptional.orElseGet(
        () -> loadFromDatabase(userId));

String rendered = responseOptional.orElseGet(
        () -> renderLargeTemplate());

String token = tokenOptional.orElseGet(
        tokenService::refreshToken);
```

*Đây là các snippet minh họa; các hàm, đối tượng và biến phải được định nghĩa trong ứng dụng.*

Ví dụ tốn chi phí: truy vấn database, gọi HTTP, đọc file, dựng object lớn, tạo dữ liệu ngẫu nhiên, cập nhật counter, ghi log, gửi sự kiện. Với các tình huống này, `orElse(expensiveOperation())` có thể gây **tải không cần thiết**, **side effect không mong muốn**, hoặc **ngoại lệ dù giá trị đã có sẵn**.

Không cần thay mọi `orElse("literal")` thành `orElseGet(() -> "literal")`. Lambda không mang lợi ích đáng kể khi fallback đã là hằng số; dùng API rõ ràng và dễ đọc hơn.

## 6. Tình huống thực tế: cache rồi fallback sang hệ thống ngoài

Giả sử ứng dụng lưu tên hiển thị trong cache. Nếu có cache hit, không cần gọi nguồn dữ liệu dự phòng. Lưu `CacheFallbackDemo.java`:

```java
import java.util.Map;
import java.util.Optional;

public class CacheFallbackDemo {
    private static final Map<String, String> CACHE =
            Map.of("42", "An");

    private static String loadRemote(String id) {
        System.out.println("remote lookup: " + id);
        return "Guest-" + id;
    }

    private static String displayName(String id) {
        return Optional.ofNullable(CACHE.get(id))
                .orElseGet(() -> loadRemote(id));
    }

    public static void main(String[] args) {
        System.out.println("user42 = " + displayName("42"));
        System.out.println("user99 = " + displayName("99"));
    }
}
```

```bash
javac CacheFallbackDemo.java
java CacheFallbackDemo
```

```text
user42 = An
remote lookup: 99
user99 = Guest-99
```

Giải thích:

- `CACHE.get("42")` trả `"An"` → `Optional.ofNullable` tạo Optional có giá trị → không gọi `loadRemote("42")`.
- `CACHE.get("99")` trả `null` → Optional rỗng → `orElseGet` thực thi lambda đúng lúc → in log truy vấn dự phòng rồi trả tên `Guest-99`.
- Nếu viết `orElse(loadRemote(id))`, thao tác `loadRemote("42")` cũng sẽ chạy, dù kết quả `Guest-42` sau đó bị bỏ.

**Không coi ví dụ cache này là thiết kế cache toàn diện.** `orElseGet` không tự lưu kết quả fallback vào cache, không tự xử lý retry/timeout/circuit breaker và không tự bảo đảm rằng chỉ có một thread gọi nguồn dự phòng cho cùng khóa. Những điều đó thuộc trách nhiệm riêng của cơ chế cache/service.

`Map.of` yêu cầu Java 9+; bản thân `Optional.ofNullable` và `orElseGet` vẫn dùng được trên Java 8.

## 7. Chi phí không phải vấn đề duy nhất: tác dụng phụ và exception

Xem một hàm fallback có thể ném ngoại lệ. Lưu `ExceptionFallbackDemo.java`:

```java
import java.util.Optional;

public class ExceptionFallbackDemo {
    private static String riskyFallback() {
        System.out.println("fallback attempted");
        throw new IllegalStateException("remote unavailable");
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("ready");

        try {
            System.out.println("eager = " +
                    present.orElse(riskyFallback()));
        } catch (IllegalStateException e) {
            System.out.println("orElse failed = " + e.getMessage());
        }

        String safe = present.orElseGet(
                ExceptionFallbackDemo::riskyFallback);
        System.out.println("orElseGet present = " + safe);

        try {
            Optional.<String>empty().orElseGet(
                    ExceptionFallbackDemo::riskyFallback);
        } catch (IllegalStateException e) {
            System.out.println("orElseGet empty failed = " +
                    e.getMessage());
        }
    }
}
```

```bash
javac ExceptionFallbackDemo.java
java ExceptionFallbackDemo
```

```text
fallback attempted
orElse failed = remote unavailable
orElseGet present = ready
fallback attempted
orElseGet empty failed = remote unavailable
```

Ý nghĩa:

- `present.orElse(riskyFallback())` **không** trả `ready`, vì hàm fallback đã ném exception trước khi lời gọi `orElse` bắt đầu.
- `present.orElseGet(ExceptionFallbackDemo::riskyFallback)` trả `ready` mà không gọi hàm rủi ro.
- Khi Optional rỗng, supplier được gọi; nếu chính nó ném exception thì exception được truyền ra cho bên gọi. `orElseGet` không có cơ chế bắt lỗi hay tự thử lại.

Với giao dịch ghi database, gửi email, phát sự kiện hoặc cập nhật số liệu, tính sớm của `orElse` có thể tạo hành động ngoài ý muốn. Chọn `orElseGet` không loại bỏ side effect khi thực sự cần fallback, mà chỉ tránh thực hiện nó **khi giá trị đã có**.

## 8. Supplier không tự cache: mỗi lần thiếu có thể tính lại

`orElseGet` là cơ chế **lazy evaluation theo mỗi lời gọi**, không phải memoization. Cùng một `Optional.empty()` mà gọi `orElseGet(factory)` nhiều lần thì supplier có thể được gọi **mỗi lần**, trả các giá trị khác nhau nếu factory có trạng thái.

Lưu `SupplierReuseDemo.java`:

```java
import java.util.Optional;
import java.util.function.Supplier;

public class SupplierReuseDemo {
    private static int calls = 0;

    private static String create() {
        calls++;
        System.out.println("creating: " + calls);
        return "new-" + calls;
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("hit");
        Optional<String> empty = Optional.empty();
        Supplier<String> factory = SupplierReuseDemo::create;

        System.out.println("present = " +
                present.orElseGet(factory));
        System.out.println("calls = " + calls);

        System.out.println("first = " +
                empty.orElseGet(factory));
        System.out.println("second = " +
                empty.orElseGet(factory));

        System.out.println("eager = " +
                present.orElse(factory.get()));
        System.out.println("calls = " + calls);
    }
}
```

```bash
javac SupplierReuseDemo.java
java SupplierReuseDemo
```

```text
present = hit
calls = 0
creating: 1
first = new-1
creating: 2
second = new-2
creating: 3
eager = hit
calls = 3
```

Hai lần `empty.orElseGet(factory)` tạo `new-1` và `new-2`. Đến `present.orElse(factory.get())`, `factory.get()` vẫn chạy, tạo `new-3` rồi `orElse` bỏ kết quả và trả `hit`.

Khi cần **cache fallback một lần**, phải dùng cơ chế lưu riêng, ví dụ cache có khóa, singleton theo đúng nhu cầu, hoặc tính một lần rồi lưu vào biến sau lần dùng đầu. Đừng chọn `orElseGet` và nghĩ rằng nó bảo đảm “mỗi người dùng chỉ được tải một lần”.

Đoạn demo sử dụng biến `static` chỉ để quan sát hành vi **tuần tự**. Trong ứng dụng đa luồng, cập nhật bộ đếm dùng chung cần nguyên tắc đồng bộ/atomic thích hợp; `orElseGet` tự nó không làm supplier trở nên thread-safe.

## 9. `null`, `Optional.empty()` và chính sách fallback

`Optional.of(value)` yêu cầu `value` không `null`. Nếu giá trị đầu vào có thể `null`, dùng `Optional.ofNullable(value)`:

```java
Optional<String> a = Optional.of("ok");
Optional<String> b = Optional.ofNullable(null); // empty
Optional<String> c = Optional.empty();
```

*Các dòng là snippet với import `java.util.Optional`. `Optional.of(null)` ném `NullPointerException`.*

Một chi tiết quan trọng: dù Optional **không bao chứa một giá trị null có mặt**, hai phương thức fallback vẫn có thể **trả ra null** khi Optional rỗng:

- `Optional.<String>empty().orElse(null)` → `null`.
- `Optional.<String>empty().orElseGet(() -> null)` → `null`.

Việc trả `null` đôi khi cần để tương thích một API cũ, nhưng trong mã mới thường nên có chính sách rõ ràng hơn: default có ý nghĩa, xử lý nhánh vắng mặt, hoặc tiếp tục giữ `Optional`. Không hiểu `orElseGet` là phép “ngăn null”.

Lưu `NullFallbackDemo.java`:

```java
import java.util.Optional;

public class NullFallbackDemo {
    public static void main(String[] args) {
        Optional<String> absent = Optional.ofNullable(null);
        Optional<String> present = Optional.of("ready");

        String fromElse = absent.orElse(null);
        String fromGet = absent.orElseGet(() -> null);

        System.out.println("absent = " + absent.isEmpty());
        System.out.println("orElseNull = " + (fromElse == null));
        System.out.println("orElseGetNull = " + (fromGet == null));
        System.out.println("present = " +
                present.orElseGet(() -> null));

        try {
            Optional.<String>empty().orElseGet(null);
        } catch (NullPointerException e) {
            System.out.println("null supplier rejected");
        }
    }
}
```

```bash
javac NullFallbackDemo.java
java NullFallbackDemo
```

```text
absent = true
orElseNull = true
orElseGetNull = true
present = ready
null supplier rejected
```

`Optional.isEmpty()` có từ **Java 11**, nên chương trình dùng Java 17+. Đối với `orElseGet(null)`, Javadoc quy định `NullPointerException` **khi Optional không có giá trị** và supplier là `null`; nếu Optional có giá trị thì supplier không cần bị gọi. Tuy vậy, **không nên truyền supplier null** để khai thác chi tiết này — đó là API usage khó đọc và dễ lỗi. Trong code thông thường, luôn truyền supplier hợp lệ.

## 10. `map`, `filter` rồi `orElseGet`: fallback chỉ sau toàn pipeline

Các phép biến đổi trên Optional chỉ được áp dụng khi Optional có giá trị. `map(mapper)` có thể biến kết quả mapper là `null` thành Optional rỗng; `filter(predicate)` có thể loại một giá trị không đạt điều kiện. `orElseGet` khi đó quyết định fallback **sau kết quả cuối cùng**.

Lưu `OptionalPipelineDemo.java`:

```java
import java.util.Optional;

public class OptionalPipelineDemo {
    record Account(String id, String nickname) {}

    private static Optional<Account> findAccount(String id) {
        return switch (id) {
            case "A" -> Optional.of(new Account("A", "An"));
            case "B" -> Optional.of(new Account("B", " "));
            default -> Optional.empty();
        };
    }

    private static String fallbackName(String id) {
        System.out.println("directory lookup: " + id);
        return "unknown-" + id;
    }

    private static String label(String id) {
        return findAccount(id)
                .map(Account::nickname)
                .filter(name -> !name.isBlank())
                .orElseGet(() -> fallbackName(id));
    }

    public static void main(String[] args) {
        System.out.println("A = " + label("A"));
        System.out.println("B = " + label("B"));
        System.out.println("C = " + label("C"));
    }
}
```

```bash
javac OptionalPipelineDemo.java
java OptionalPipelineDemo
```

```text
A = An
directory lookup: B
B = unknown-B
directory lookup: C
C = unknown-C
```

Ở đây:

- `A` có account và nickname hợp lệ: fallback không chạy.
- `B` có account nhưng nickname chỉ là khoảng trắng; `filter` loại bỏ, biến kết quả thành Optional rỗng: fallback chạy.
- `C` không có account ngay từ đầu: fallback chạy.

`record` và `switch expression` là tính năng chuẩn trong Java 17; `String.isBlank()` có từ Java 11. Các phép `Optional.map`, `filter` và `orElseGet` là API Java 8, vẫn đang sử dụng.

**Phân biệt nơi đặt fallback:** đặt `orElseGet` sau `filter` sẽ coi “giá trị không đạt điều kiện” như một lần thiếu dữ liệu; nếu nghiệp vụ yêu cầu phân biệt “không tồn tại account” và “nickname không hợp lệ”, không nên gộp cả hai thành cùng fallback mà cần mô hình kết quả hoặc exception riêng.

## 11. `OptionalInt`, `OptionalLong` và `OptionalDouble` cũng có hai cách fallback

Ngoài `Optional<T>`, Java còn có ba kiểu chuyên dụng tránh boxing:

| Kiểu | Eager fallback | Lazy fallback |
| --- | --- | --- |
| `OptionalInt` | `int orElse(int other)` | `int orElseGet(IntSupplier supplier)` |
| `OptionalLong` | `long orElse(long other)` | `long orElseGet(LongSupplier supplier)` |
| `OptionalDouble` | `double orElse(double other)` | `double orElseGet(DoubleSupplier supplier)` |

Cả ba đều là API hiện hành. Quy tắc thời điểm tính **giống hệt**: giá trị truyền vào `orElse(...)` được đánh giá trước lời gọi; thân supplier của `orElseGet(...)` chỉ chạy khi không có giá trị.

Lưu `PrimitiveFallbackDemo.java`:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;

public class PrimitiveFallbackDemo {
    public static void main(String[] args) {
        int present = OptionalInt.of(7).orElseGet(() -> {
            System.out.println("int fallback not expected");
            return 99;
        });
        System.out.println("presentInt = " + present);

        int missing = OptionalInt.empty().orElseGet(() -> {
            System.out.println("compute int");
            return 99;
        });
        System.out.println("missingInt = " + missing);

        long missingLong = OptionalLong.empty()
                .orElseGet(() -> 100L);
        double presentDouble = OptionalDouble.of(1.25)
                .orElse(0.0);

        System.out.println("missingLong = " + missingLong);
        System.out.println("presentDouble = " + presentDouble);
    }
}
```

```bash
javac PrimitiveFallbackDemo.java
java PrimitiveFallbackDemo
```

```text
presentInt = 7
compute int
missingInt = 99
missingLong = 100
presentDouble = 1.25
```

`OptionalInt` thường xuất hiện sau `IntStream.findFirst()`, `min()`, `max()`; `OptionalDouble` có thể là kết quả `DoubleStream.average()`. Không cần box sang `Optional<Integer>`/`Optional<Double>` chỉ để lấy fallback. Chọn supplier chuyên dụng (`IntSupplier`/`LongSupplier`/`DoubleSupplier`) khi thao tác trên các kiểu primitive.

## 12. So sánh với `or`, `orElseThrow` và `ifPresentOrElse`

Tất cả đều còn có mặt trong JDK hiện hành, nhưng **trả kết quả hoặc thực thi hành động khác nhau**:

| API | Dùng khi nào | Kết quả |
| --- | --- | --- |
| `orElse(T other)` | Có sẵn fallback rẻ, không side effect | `T` |
| `orElseGet(Supplier<T>)` | Cần tính `T` khi thiếu | `T` |
| `or(Supplier<Optional<T>>)` | Muốn thử nguồn Optional thứ hai nhưng **tiếp tục giữ Optional** | `Optional<T>` |
| `orElseThrow()` | Thiếu giá trị là tình huống lỗi, ném `NoSuchElementException` | `T` hoặc exception |
| `orElseThrow(Supplier<? extends X>)` | Tạo exception riêng khi thiếu | `T` hoặc exception `X` |
| `ifPresentOrElse(Consumer<T>, Runnable)` | Cần thực hiện hành động ở hai nhánh, không cần giá trị trả về | `void` |

Phiên bản: `orElse`, `orElseGet` và `orElseThrow(exceptionSupplier)` có từ Java 8; `or`/`ifPresentOrElse` có từ Java 9; `orElseThrow()` không đối số có từ Java 10. `Optional.get()` vẫn tồn tại nhưng Javadoc khuyến nghị `orElseThrow()` làm cách thể hiện rõ hơn khi không có giá trị là lỗi.

Chú ý: `or(...)` và `orElseGet(...)` đều **lazy**, nhưng supplier của `or` phải trả một `Optional` không null, trong khi supplier của `orElseGet` trả **giá trị `T`**.

Lưu `OptionalOrDemo.java`:

```java
import java.util.Optional;

public class OptionalOrDemo {
    private static Optional<String> remoteLookup() {
        System.out.println("load remote");
        return Optional.of("remote");
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("cache");

        Optional<String> kept = present.or(
                OptionalOrDemo::remoteLookup);
        System.out.println("present = " + kept);

        Optional<String> fetched = Optional.<String>empty().or(
                OptionalOrDemo::remoteLookup);
        System.out.println("empty = " + fetched);

        String finalValue = Optional.<String>empty()
                .or(Optional::empty)
                .orElse("n/a");
        System.out.println("notFound = " + finalValue);
    }
}
```

```bash
javac OptionalOrDemo.java
java OptionalOrDemo
```

```text
present = Optional[cache]
load remote
empty = Optional[remote]
notFound = n/a
```

Trong dòng `present.or(remoteLookup)`, supplier không chạy vì giá trị `cache` đã có. Trong dòng `empty.or(remoteLookup)`, supplier chạy, tạo một Optional khác. `orElse("n/a")` sau đó mới chuyển Optional thành chuỗi cuối cùng. Nếu dùng `orElseGet(OptionalOrDemo::remoteLookup)` sẽ sai kiểu: `remoteLookup` trả `Optional<String>` chứ không phải `String`.

### Có nên ném exception trong fallback supplier?

Về cú pháp, lambda trong `orElseGet` có thể ném một runtime exception, nhưng khi nghiệp vụ coi Optional rỗng là lỗi, `orElseThrow(() -> new NotFoundException(...))` thường diễn đạt ý định rõ hơn. Ngoại lệ được **khởi tạo theo cách lazy** bởi supplier, tức là không tốn công tạo exception khi giá trị có sẵn. Điều này khác `orElse(createExceptionOrValue())` và giúp code review dễ nắm mục đích.

## 13. Lỗi thường gặp khi code review

### 13.1. Dùng `orElse(expensive())` dù Optional có giá trị

```java
// Sai ý định nếu muốn chỉ truy vấn khi thiếu.
String name = repository.findName(id)
        .orElse(remoteService.fetchName(id));
```

*Đoạn minh họa, cần repository/service đã định nghĩa.*

`remoteService.fetchName(id)` chạy ở bước đánh giá đối số, trước khi biết kết quả `orElse`, nên chạy kể cả khi `findName(id)` đã trả Optional có giá trị.

Sửa:

```java
String name = repository.findName(id)
        .orElseGet(() -> remoteService.fetchName(id));
```

### 13.2. Tưởng bọc một biến đã tính thành lambda là lazy

```java
String precomputed = remoteService.fetchName(id);
String name = result.orElseGet(() -> precomputed);
```

Vẫn truy vấn sớm ở dòng đầu. `Supplier` chỉ trì hoãn việc **trả biến đã có**, không thể trì hoãn biểu thức đã chạy.

### 13.3. Truyền sai hình dạng đối số

```java
// orElseGet yêu cầu Supplier, không nhận trực tiếp giá trị:
// result.orElseGet("Unknown");

// orElse yêu cầu giá trị T, không nhận Supplier<T>:
// result.orElse(() -> "Unknown");
```

Các dòng sai được **comment** để chỉ mô tả lỗi compile. Cách đúng:

```java
result.orElse("Unknown");
result.orElseGet(() -> "Unknown");
```

Nếu `result` là `Optional<String>`, cả hai biểu thức trên cùng trả `String`; với hằng số đã có, thường chọn `orElse("Unknown")`.

### 13.4. Nghĩ `orElseGet` cache dữ liệu tự động

Supplier có thể chạy mỗi khi Optional rỗng và bạn gọi `orElseGet`. Nếu fallback là cuộc gọi tốn chi phí, cân nhắc cơ chế cache hoặc lưu kết quả sau khi tìm được. Đừng viết test dựa trên giả định supplier chỉ được gọi một lần cho mọi lời gọi `orElseGet`.

### 13.5. Nghĩ `orElseGet` ngăn exception hoặc `null`

Nếu supplier ném exception thì exception truyền ra; nếu supplier trả null thì kết quả có thể là null. Nếu supplier null và Optional rỗng, `orElseGet(null)` ném `NullPointerException`. `Optional.empty()` biểu diễn sự vắng mặt trong container, không buộc mọi thao tác chuyển ra giá trị phải khác null.

### 13.6. Dùng side effect để quyết định nhánh

`orElseGet` được thiết kế cho fallback có thể tính lazy, nhưng không có nghĩa nên đặt các hành động cập nhật cơ sở dữ liệu thiếu kiểm soát trong lambda. Với mọi tác dụng phụ, phải cân nhắc transaction/idempotency/retry và quy tắc concurrency theo tầng service.

### 13.7. Biến Optional thành null quá sớm

`optional.orElse(null)` có thể hợp lệ khi tích hợp API cũ, nhưng sẽ mất lợi ích mô hình hóa “có/không có dữ liệu”. Nếu các bước tiếp theo còn làm việc với Optional, ưu tiên `map`/`flatMap`/`filter`, hoặc `or(...)` nếu cần nguồn dự phòng trả Optional.

### 13.8. So sánh độ nhanh dựa trên một đoạn benchmark không kiểm soát

Không khẳng định rằng `orElseGet` luôn nhanh hơn `orElse`. Khi fallback chỉ là hằng số, `orElse` đơn giản, thường phù hợp hơn. Với fallback tốn chi phí, hiệu quả phụ thuộc tỷ lệ Optional có giá trị, chi phí fallback và môi trường thực thi. Nếu quan tâm hiệu năng, dùng phép đo có phương pháp (chẳng hạn JMH) trên workload đại diện thay vì suy luận chỉ từ cú pháp.

## 14. Mini lab: dự đoán log và kết quả

**Bài 1.** Có `Optional.of("cached")` và hàm `generate()` vừa in log vừa trả `"fresh"`. Với `orElse(generate())` và `orElseGet(() -> generate())`, cách nào in log dù Optional đã có giá trị? Giải thích thứ tự lời gọi phương thức trong Java.

**Bài 2.** Với `Optional.<String>empty()`, gọi `orElseGet(factory)` hai lần và factory đếm lần gọi. Có chắc chỉ chạy một lần không? Vì sao?

**Bài 3.** Cache có khóa `"p1"`, không có `"p2"`. Chỉ truy vấn nguồn dự phòng cho `"p2"`. Viết mã sử dụng `Optional.ofNullable(...)` và `orElseGet(...)`. So sánh với cách dùng `orElse(...)`.

**Bài 4.** Vì sao `Optional.<String>empty().orElse(null)` không ném exception, nhưng sử dụng kết quả mà không kiểm tra null có thể gây lỗi ở bước sau? Khi nào `orElseThrow(...)` diễn đạt nghiệp vụ tốt hơn?

Lời giải chạy được, lưu `OptionalExercise.java`:

```java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class OptionalExercise {
    public static void main(String[] args) {
        Map<String, String> cache = Map.of("p1", "paid");
        AtomicInteger calls = new AtomicInteger();

        Supplier<String> fallback = () -> {
            int n = calls.incrementAndGet();
            System.out.println("fallback call " + n);
            return "default-" + n;
        };

        String first = Optional.ofNullable(cache.get("p1"))
                .orElseGet(fallback);
        String second = Optional.ofNullable(cache.get("p2"))
                .orElseGet(fallback);
        String constant = Optional.of("ok").orElse("n/a");

        System.out.println("first = " + first);
        System.out.println("second = " + second);
        System.out.println("constant = " + constant);
        System.out.println("calls = " + calls.get());
    }
}
```

```bash
javac OptionalExercise.java
java OptionalExercise
```

```text
fallback call 1
first = paid
second = default-1
constant = ok
calls = 1
```

Giải bài 1: `orElse(generate())` in log vì phải tính đối số trước khi vào method; `orElseGet(() -> generate())` không in log khi Optional đã có giá trị. Bài 2: không, mỗi lần `orElseGet` trên Optional rỗng sẽ gọi supplier lần đó; `Optional` không tự memoize. Bài 3: lời giải minh họa đúng một lần truy vấn dự phòng cho khóa thiếu. Bài 4: `orElse(null)` cho phép biểu diễn fallback null, không bảo vệ code tiêu thụ; nếu “thiếu dữ liệu” phải bị coi là lỗi, dùng `orElseThrow(...)`.

## 15. Quy tắc ngắn gọn trước khi commit

1. Tôi muốn giá trị mặc định **đã có sẵn** hay **phải tính khi cần**?
2. Nếu dùng `orElse(expensive())`, có hành vi thừa dù Optional đã có giá trị không?
3. Nếu dùng `orElseGet`, công việc tốn chi phí đã thật sự nằm **trong thân supplier**, hay đã chạy trước lúc tạo supplier?
4. Fallback có thực hiện I/O, thay đổi trạng thái, ghi log, ném exception hoặc trả null không?
5. Nguồn dữ liệu có thể trả null không? Tôi đã dùng `ofNullable` khi phù hợp?
6. Có cần **giữ Optional** để kết hợp với nguồn khác bằng `or`, hay muốn **giải nén thành T**?
7. Nếu Optional rỗng là lỗi nghiệp vụ, tôi có nên dùng `orElseThrow` hơn giá trị mặc định?
8. Nếu fallback bị gọi nhiều lần, tôi có cần cache/atomicity/idempotency hay không?
9. Code cần chạy trên Java 8 hay Java 17+? Tôi đã phân biệt `orElseGet` có từ Java 8 với `or` từ Java 9 và `isEmpty` từ Java 11?

## 16. Tài liệu API chính thức còn hiệu lực

- Oracle Java SE 26, `Optional<T>`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html
- Oracle Java SE 26, `Supplier<T>`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Supplier.html
- Oracle Java SE 26, `OptionalInt`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalInt.html
- Oracle Java SE 26, `OptionalLong`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalLong.html
- Oracle Java SE 26, `OptionalDouble`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalDouble.html

**Ghi nhớ:** `orElse(value)` nhận **giá trị đã đánh giá**, còn `orElseGet(supplier)` nhận **cách tạo giá trị** và chỉ thực thi supplier khi Optional rỗng. Khi fallback là hằng số hoặc giá trị rẻ, `orElse` thường rõ ràng hơn; khi fallback cần tính toán, I/O hoặc có tác dụng phụ, `orElseGet` giúp tránh những công việc không cần thiết và làm rõ ý định của code.