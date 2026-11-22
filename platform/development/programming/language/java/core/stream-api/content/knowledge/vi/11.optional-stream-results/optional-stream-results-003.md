# Chọn giá trị mặc định bằng orElse và orElseGet

## 1. Vì sao kết quả của Stream thường cần giá trị mặc định?

Trong chương **Optional trong kết quả Stream** của **JAVA_STREAM_API**, các phép toán kết thúc như `findFirst()`, `findAny()`, `min()`, `max()` hoặc `reduce(BinaryOperator)` có thể không tìm được phần tử nào. Vì một Stream có thể rỗng sau `filter`, Java không thể luôn trả về một đối tượng `T` hợp lệ. Những terminal operation này dùng `Optional<T>` để biểu diễn kết quả **có giá trị hoặc không có giá trị**.

Khi nghiệp vụ yêu cầu luôn nhận một giá trị để xử lý tiếp, ta phải quyết định chính sách dự phòng. Hai phương thức quen thuộc là:

- `orElse(defaultValue)`: sử dụng giá trị dự phòng **đã được tính** trước khi gọi phương thức.
- `orElseGet(supplier)`: chỉ **gọi hàm tạo giá trị dự phòng** nếu Optional thực sự rỗng.

Đây là một phần của cách lập trình khai báo với pipeline lazy, `filter`, `map`, `reduce` và `collect`: lựa chọn khi nào có thể thiếu kết quả, khi nào được phép thay thế, và khi nào việc tính giá trị thay thế gây chi phí hoặc tác dụng phụ.

~~~text
Nguồn Stream ─► filter / map / ... ─► findFirst / max / reduce ─► Optional<T>
                                                                 │
                                    ┌────────────────────────────┴────────────────────────────┐
                                    ▼                                                         ▼
                             Optional có giá trị                                      Optional.empty()
                                    │                                                         │
                           Lấy giá trị hiện có                                   Dùng giá trị dự phòng
                                    │                                                         │
                                    └────────────────────────────┬────────────────────────────┘
                                                                 ▼
                                                           T (không còn Optional)
~~~

**Điểm mấu chốt:** Với Optional có giá trị, hai phương thức thường trả về cùng giá trị. Khác biệt đáng chú ý nằm ở **thời điểm biểu thức dự phòng được thực thi**.

Các ví dụ trong bài sử dụng Java 17+, nhưng `Optional.orElse` và `Optional.orElseGet` đã có từ Java 8.

## 2. Tạo Optional từ kết quả Stream

Ví dụ tìm tên khách hàng đầu tiên thỏa điều kiện:

~~~java
import java.util.List;
import java.util.Optional;

public class FindCustomer {
    public static void main(String[] args) {
        List<String> customers = List.of("An", "Bình", "Chi");

        Optional<String> found = customers.stream()
            .filter(name -> name.startsWith("B"))
            .findFirst();

        Optional<String> missing = customers.stream()
            .filter(name -> name.startsWith("Z"))
            .findFirst();

        System.out.println(found);   // Optional[Bình]
        System.out.println(missing); // Optional.empty
    }
}
~~~

Các trường hợp thường gặp:

| Terminal operation | Kiểu kết quả | Vì sao có thể rỗng? |
| --- | --- | --- |
| `findFirst()` | `Optional<T>` | Không có phần tử, hoặc không phần tử nào qua bộ lọc. |
| `findAny()` | `Optional<T>` | Không có phần tử phù hợp. |
| `min(comparator)` | `Optional<T>` | Stream không có phần tử. |
| `max(comparator)` | `Optional<T>` | Stream không có phần tử. |
| `reduce(BinaryOperator)` | `Optional<T>` | Không có giá trị nào để gộp. |
| `IntStream.min()`, `IntStream.max()` | `OptionalInt` | Stream nguyên thủy rỗng. |
| `IntStream.average()` | `OptionalDouble` | Không có số để tính trung bình. |

Không phải mọi terminal operation đều trả Optional. Chẳng hạn `count()` trả `long` (bằng 0 nếu rỗng), `IntStream.sum()` trả `int` (bằng 0 nếu rỗng), còn `reduce(identity, accumulator)` trả trực tiếp giá trị tương ứng với identity khi Stream rỗng.

## 3. Cú pháp và khác biệt chính giữa orElse và orElseGet

Hai chữ ký phương thức trên `Optional<T>`:

~~~java
T orElse(T other);

T orElseGet(Supplier<? extends T> supplier);
~~~

`orElse` nhận **một giá trị `T`**. `orElseGet` nhận **một Supplier** có khả năng tạo ra `T` khi được gọi.

~~~java
import java.util.Optional;

Optional<String> found = Optional.of("Bình");
Optional<String> missing = Optional.empty();

String a = found.orElse("Khách vãng lai");
String b = missing.orElse("Khách vãng lai");

String c = found.orElseGet(() -> "Khách vãng lai");
String d = missing.orElseGet(() -> "Khách vãng lai");

// a = "Bình", b = "Khách vãng lai"
// c = "Bình", d = "Khách vãng lai"
~~~

Với literal đơn giản, kết quả không khác nhau. Sự khác biệt xuất hiện khi **giá trị mặc định phải được tính**:

| Điều kiện | `optional.orElse(createDefault())` | `optional.orElseGet(() -> createDefault())` |
| --- | --- | --- |
| Optional có giá trị | `createDefault()` **vẫn được gọi**; kết quả dự phòng bị bỏ | Supplier **không được gọi** |
| Optional rỗng | `createDefault()` được gọi, trả kết quả dự phòng | Supplier được gọi để tạo kết quả dự phòng |
| Fallback là literal/hằng số | Cách viết gọn, dễ hiểu | Có thể dùng nhưng không cần thiết |
| Fallback tốn CPU, I/O hoặc có tác dụng phụ | Có nguy cơ thực thi thừa | Tránh thực thi dự phòng khi đã có kết quả |

Lý do là cơ chế **đánh giá đối số của Java**: trước khi gọi `orElse(...)`, Java tính xong biểu thức được truyền vào. Với `orElseGet(...)`, đối số là một đối tượng Supplier (thường biểu diễn bằng lambda hoặc method reference); **thân hàm Supplier** chỉ được thực thi nếu Optional rỗng.

## 4. Chứng minh eager và lazy bằng ví dụ chạy được

~~~java
import java.util.Optional;

public class EagerVsLazy {
    static String buildDefault() {
        System.out.println("Đang tạo giá trị dự phòng");
        return "Khách vãng lai";
    }

    public static void main(String[] args) {
        Optional<String> found = Optional.of("An");

        String eager = found.orElse(buildDefault());
        System.out.println("orElse = " + eager);

        String lazy = found.orElseGet(EagerVsLazy::buildDefault);
        System.out.println("orElseGet = " + lazy);
    }
}
~~~

Kết quả:

~~~text
Đang tạo giá trị dự phòng
orElse = An
orElseGet = An
~~~

Mặc dù `found` đã chứa `"An"`, `buildDefault()` vẫn được gọi để chuẩn bị đối số cho `orElse`. Lần gọi `orElseGet` không chạy `buildDefault()` vì Optional có giá trị.

Đổi `found` thành `Optional.empty()`:

~~~java
Optional<String> missing = Optional.empty();

String fromElse = missing.orElse(buildDefault());
String fromGet = missing.orElseGet(EagerVsLazy::buildDefault);

// Cả hai đều nhận "Khách vãng lai".
// Hàm buildDefault được gọi một lần cho mỗi lời gọi trên Optional rỗng.
~~~

Không nên nhầm **việc tạo lambda** với **việc chạy thân lambda**: biểu thức `() -> buildDefault()` được đánh giá thành Supplier trước lời gọi phương thức, nhưng hành động `buildDefault()` chỉ xảy ra khi Optional rỗng.

### Cách viết đúng khi fallback là một method

~~~java
// Gọi ngay; kể cả Optional có giá trị:
String eager = found.orElse(buildDefault());

// Chỉ gọi khi Optional rỗng:
String lazyByLambda = found.orElseGet(() -> buildDefault());
String lazyByReference = found.orElseGet(EagerVsLazy::buildDefault);
~~~

`orElseGet(buildDefault())` **không hợp lệ** ở đây vì `buildDefault()` trả về `String`, còn `orElseGet` cần một `Supplier<? extends String>`.

## 5. Tình huống nghiệp vụ: tạo đối tượng mặc định tốn tài nguyên

Giả sử hệ thống xử lý một danh sách yêu cầu và cần tìm yêu cầu ưu tiên. Nếu không có yêu cầu phù hợp, hệ thống tạo một đối tượng mặc định. Việc tạo này có thể tốn chi phí khi gắn với tra cứu cấu hình, gọi dịch vụ ngoài hoặc tính toán nhiều bước.

Ví dụ độc lập sau dùng việc in log để cho thấy lúc nào hàm dự phòng chạy:

~~~java
import java.util.List;
import java.util.Optional;

public class RequestFallback {
    record Request(String id, int priority) {}

    static Request createDefaultRequest() {
        System.out.println("Tạo yêu cầu mặc định");
        return new Request("DEFAULT", 0);
    }

    static Request choose(List<Request> requests) {
        Optional<Request> selected = requests.stream()
            .filter(request -> request.priority() >= 5)
            .findFirst();

        return selected.orElseGet(RequestFallback::createDefaultRequest);
    }

    public static void main(String[] args) {
        List<Request> requests = List.of(
            new Request("R-01", 2),
            new Request("R-02", 9),
            new Request("R-03", 5)
        );

        System.out.println(choose(requests)); // Request[id=R-02, priority=9]
        System.out.println(choose(List.of())); // Có log tạo mặc định, rồi DEFAULT
    }
}
~~~

Khi đã tìm thấy `R-02`, hàm tạo yêu cầu mặc định **không chạy**. Khi danh sách trống, Supplier chạy để tạo đối tượng.

Nếu thay bằng:

~~~java
return selected.orElse(createDefaultRequest());
~~~

thì đối tượng dự phòng được tạo **mỗi lần phương thức `choose` chạy**, dù `selected` chứa giá trị. Trong ứng dụng thực, điều này có thể dẫn tới request mạng dư thừa, mở file không cần thiết, hoặc thậm chí ghi thêm bản ghi không mong muốn nếu hàm tạo mặc định có tác dụng phụ.

**Nguyên tắc:** Khi fallback cần gọi hàm hoặc tạo object có chi phí, `orElseGet` thường diễn đạt đúng ý định “chỉ tạo khi thiếu”.

## 6. Nhiều chính sách fallback: từ giá trị có sẵn đến nguồn dự phòng

Có nhiều mức độ dự phòng. Cần chọn dựa vào **ý nghĩa nghiệp vụ**, chứ không chỉ kiểu trả về.

### 6.1. Giá trị cố định, rẻ và bất biến

~~~java
String label = items.stream()
    .filter(text -> !text.isBlank())
    .findFirst()
    .orElse("Không có dữ liệu");
~~~

Trong ví dụ này, `items` là `List<String>` của ngữ cảnh gọi. Chuỗi literal đã có sẵn, nên `orElse` là lựa chọn đơn giản.

### 6.2. Giá trị dự phòng tính theo dữ liệu hiện tại

~~~java
import java.time.LocalDate;
import java.util.Optional;

Optional<LocalDate> latestDate = dates.stream().max(LocalDate::compareTo);

LocalDate chosen = latestDate.orElseGet(LocalDate::now);
~~~

Ví dụ giả định `dates` là `List<LocalDate>`. `LocalDate.now()` chỉ được gọi khi không có ngày nào. Với ứng dụng cần kiểm thử được hoặc phải xác định múi giờ, có thể truyền `Clock` vào lớp và dùng `LocalDate.now(clock)` trong Supplier.

### 6.3. Truy vấn lần lượt cache và cơ sở dữ liệu

Đôi khi cả hai nguồn đều có thể **không có giá trị**. `Optional.or(...)` (Java 9+) giữ kiểu Optional cho đến khi quyết định fallback cuối cùng:

~~~java
import java.util.Optional;

Optional<String> fromCache = Optional.empty();

String displayName = fromCache
    .or(() -> lookupFromDatabase())
    .orElseGet(() -> "Khách vãng lai");
~~~

`lookupFromDatabase()` trong ví dụ là phương thức trả về `Optional<String>` do ứng dụng định nghĩa. `Optional.or` chỉ gọi Supplier khi Optional trước đó rỗng; kết quả của `or(...)` vẫn là **`Optional<String>`**, trong khi `orElseGet(...)` trả thẳng **`String`**.

Không thể dùng `orElseGet(() -> lookupFromDatabase())` trực tiếp khi hàm trả về `Optional<String>`, vì Supplier của `orElseGet` phải trả về **`String`**. Nếu muốn fallback trực tiếp từ truy vấn trả Optional, có thể dùng:

~~~java
String displayName = fromCache.orElseGet(
    () -> lookupFromDatabase().orElse("Khách vãng lai")
);
~~~

Trong các hệ thống có tác dụng phụ như ghi dữ liệu, gửi request hoặc tính phí, `orElseGet` chỉ quản lý **khi nào chạy fallback**; nó **không tự đảm bảo giao dịch, idempotency hay chỉ thực thi đúng một lần giữa nhiều request khác nhau**.

## 7. Kết hợp với `findFirst`, `findAny` và `max`

### 7.1. `findFirst` khi cần phần tử đầu tiên

~~~java
import java.util.List;

List<Integer> scores = List.of(40, 75, 90, 60);

int firstHighScore = scores.stream()
    .filter(score -> score >= 70)
    .findFirst()
    .orElse(-1);

System.out.println(firstHighScore); // 75
~~~

Với nguồn có encounter order như `List`, `findFirst` lấy phần tử phù hợp đầu tiên. Nếu không có phần tử phù hợp thì trả `Optional.empty()`; `orElse(-1)` đổi nó thành giá trị sentinel theo quy ước ứng dụng.

### 7.2. `findAny` khi chọn một phần tử bất kỳ là đủ

~~~java
int anyHighScore = scores.parallelStream()
    .filter(score -> score >= 70)
    .findAny()
    .orElse(-1);
~~~

`findAny` không cam kết chọn phần tử đầu tiên, đặc biệt khi xử lý song song. Giá trị dự phòng `-1` chỉ được dùng khi **không có phần tử** thỏa điều kiện. Nếu nghiệp vụ yêu cầu chính xác “đầu tiên”, dùng `findFirst` với nguồn có thứ tự xác định.

### 7.3. `max` và fallback khi không có dữ liệu

~~~java
import java.util.Comparator;
import java.util.List;

record Product(String sku, long price) {}

List<Product> products = List.of(
    new Product("PEN", 10_000L),
    new Product("BOOK", 45_000L)
);

Product mostExpensive = products.stream()
    .max(Comparator.comparingLong(Product::price))
    .orElseGet(() -> new Product("NONE", 0L));

// Product[sku=BOOK, price=45000]
~~~

`max` trả Optional vì nguồn có thể rỗng. Cần cân nhắc kỹ trước khi đưa một sản phẩm giả vào dữ liệu nghiệp vụ: fallback hữu ích khi mô hình cho phép “không có sản phẩm”, nhưng đôi khi kết quả Optional rỗng cần được giữ lại để hệ thống hiển thị trạng thái “chưa có hàng”.

## 8. `reduce`: nhận Optional khi không có identity

`reduce(BinaryOperator<T>)` trả `Optional<T>`, khác với biến thể có identity.

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> values = List.of(10, 20, 30);

Optional<Integer> combined = values.stream()
    .reduce(Integer::sum);

int total = combined.orElse(0);
System.out.println(total); // 60

int emptyTotal = List.<Integer>of().stream()
    .reduce(Integer::sum)
    .orElse(0);

System.out.println(emptyTotal); // 0
~~~

Nếu `0` thật sự là **phần tử đơn vị** thích hợp với phép cộng, có thể dùng biến thể `reduce(identity, accumulator)`:

~~~java
int total = values.stream().reduce(0, Integer::sum);
int emptyTotal = List.<Integer>of().stream().reduce(0, Integer::sum);

// total = 60; emptyTotal = 0
~~~

Phép gộp phải tuân thủ các yêu cầu về kết hợp, identity và không can thiệp nếu muốn kết quả đúng trên parallel stream. Không tự ý dùng sentinel như `-1` với phép tính tổng nếu `-1` có thể bị hiểu là dữ liệu thật.

Trong nhiều trường hợp số học, `mapToInt(...).sum()` trực tiếp hơn `reduce` trên `Stream<Integer>` và tránh boxing.

## 9. Optional nguyên thủy: orElse và orElseGet có hoạt động không?

Có. `OptionalInt`, `OptionalLong` và `OptionalDouble` đều hỗ trợ hai cách lấy giá trị mặc định, nhưng kiểu Supplier tương ứng là **primitive functional interface**.

| Kiểu Optional | `orElse` nhận | `orElseGet` nhận | Trả về |
| --- | --- | --- | --- |
| `OptionalInt` | `int other` | `IntSupplier` | `int` |
| `OptionalLong` | `long other` | `LongSupplier` | `long` |
| `OptionalDouble` | `double other` | `DoubleSupplier` | `double` |

Ví dụ tổng hợp kết quả từ `IntStream`:

~~~java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt max = IntStream.of(10, 40, 20).max();

int value = max.orElse(0);
System.out.println(value); // 40

int missing = IntStream.empty()
    .max()
    .orElseGet(() -> -1);

System.out.println(missing); // -1
~~~

Với `OptionalDouble` do `average()` trả về:

~~~java
import java.util.stream.DoubleStream;

double avg = DoubleStream.of(2.0, 4.0, 6.0)
    .average()
    .orElse(Double.NaN); // 4.0

double defaultAvg = DoubleStream.empty()
    .average()
    .orElseGet(() -> 0.0); // 0.0
~~~

Giá trị `0.0` có thể khiến người đọc nhầm “không có quan sát” với “trung bình bằng 0”. Nếu phân biệt hai trạng thái là quan trọng, **giữ `OptionalDouble`** thay vì biến nó thành một số.

### Chi phí của fallback với primitive Optional

~~~java
static int computeDefault() {
    System.out.println("Tính giá trị int mặc định");
    return 42;
}

// Trong phương thức sử dụng:
int value = OptionalInt.of(5).orElse(computeDefault()); // Vẫn tính 42.
int lazy = OptionalInt.of(5).orElseGet(() -> computeDefault()); // Không gọi.
~~~

Đây vẫn là quy tắc đánh giá đối số Java, không phụ thuộc kiểu tham chiếu hay primitive.

## 10. orElse, orElseGet, orElseThrow và ifPresentOrElse

Các phương thức có mục đích khác nhau:

| API | Khi Optional có giá trị | Khi Optional rỗng | Kiểu kết quả |
| --- | --- | --- | --- |
| `orElse(value)` | Trả giá trị có sẵn | Trả `value` | `T` |
| `orElseGet(supplier)` | Trả giá trị có sẵn, không gọi Supplier | Gọi Supplier lấy fallback | `T` |
| `orElseThrow()` | Trả giá trị có sẵn | Ném `NoSuchElementException` | `T` |
| `orElseThrow(exceptionSupplier)` | Trả giá trị có sẵn | Gọi Supplier tạo exception và ném | `T` |
| `ifPresentOrElse(action, emptyAction)` | Thực hiện action | Thực hiện emptyAction | `void` |
| `or(optionalSupplier)` | Giữ Optional hiện tại | Lấy Optional thay thế từ Supplier | `Optional<T>` |

### Thiếu dữ liệu là lỗi: dùng orElseThrow

~~~java
import java.util.List;

List<String> ids = List.of("A100", "B200");

String required = ids.stream()
    .filter(id -> id.equals("B200"))
    .findFirst()
    .orElseThrow(
        () -> new IllegalStateException("Không tìm thấy mã bắt buộc")
    );

System.out.println(required); // B200
~~~

Nếu thay `"B200"` bằng mã không tồn tại, Supplier mới tạo exception. Không nên tạo một dữ liệu giả để che giấu vi phạm ràng buộc quan trọng: khi dữ liệu là bắt buộc, exception hoặc kiểu kết quả biểu diễn lỗi thường đúng hơn.

### Chỉ cần hành động, không cần trả về T: dùng ifPresentOrElse

~~~java
import java.util.Optional;

Optional<String> matched = Optional.empty();

matched.ifPresentOrElse(
    value -> System.out.println("Tìm thấy: " + value),
    () -> System.out.println("Không tìm thấy")
);
~~~

`ifPresentOrElse` không trả giá trị thay thế; nó điều phối hai hành động. Nếu mục tiêu là lấy `String` rồi chuyển tiếp vào pipeline hay trả về từ phương thức, `orElse` hoặc `orElseGet` phù hợp hơn.

## 11. Các sai lầm thường gặp

### 11.1. Gọi hàm tốn kém trong orElse vì nghĩ rằng nó chỉ chạy khi rỗng

~~~java
// Một hàm tạo dự phòng có tác dụng phụ vẫn chạy dù result có giá trị:
String selected = result.orElse(loadFromRemoteService());

// Chỉ gọi service khi result rỗng:
String selectedLazy = result.orElseGet(() -> loadFromRemoteService());
~~~

Trong đoạn này, `result` là `Optional<String>`, `loadFromRemoteService()` là hàm trả `String` do ứng dụng định nghĩa. Đây là sai lầm quan trọng nhất cần tránh.

### 11.2. Tính fallback bên ngoài lambda rồi nghĩ rằng orElseGet sẽ trì hoãn nó

~~~java
String fallback = loadFromRemoteService(); // Đã gọi service tại đây.
String selected = result.orElseGet(() -> fallback);
~~~

Đoạn trên vẫn gọi service mỗi lần thực thi, ngay cả khi `result` có giá trị. Để thật sự trì hoãn, đặt **lời gọi tốn kém** bên trong Supplier:

~~~java
String selected = result.orElseGet(() -> loadFromRemoteService());
~~~

### 11.3. Dùng orElse(null) rồi quên xử lý null

~~~java
import java.util.Optional;

Optional<String> missing = Optional.empty();

String name = missing.orElse(null); // name == null
~~~

`Optional.orElse(null)` hợp lệ vì `orElse` có thể trả null, nhưng nó làm mất lợi ích biểu diễn “có/không” bằng Optional và có thể dẫn tới `NullPointerException` về sau.

`orElseGet(() -> null)` cũng có thể trả null. Hai phương thức này **không có nghĩa vụ bảo đảm kết quả khác null**. Nếu cần một giá trị hợp lệ, hãy tạo fallback hợp lệ hoặc dùng `orElseThrow`.

### 11.4. Truyền Supplier null

~~~java
Optional<String> value = Optional.empty();

// Không làm: Optional rỗng cần gọi Supplier, nên sẽ ném NPE.
// String text = value.orElseGet(null);
~~~

Dù với Optional có giá trị có thể không cần dereference Supplier, truyền null là cách dùng kém rõ ràng và dễ hỏng khi dữ liệu thay đổi. Luôn truyền Supplier hợp lệ.

### 11.5. Dùng get() mà không biết Optional có giá trị hay không

~~~java
Optional<String> result = List.<String>of().stream().findFirst();

// result.get(); // Ném NoSuchElementException.
String display = result.orElse("Chưa có dữ liệu");
~~~

`get()` chỉ an toàn khi chắc chắn có giá trị, nhưng thiết kế thường tốt hơn nếu mô tả trực tiếp chiến lược thiếu dữ liệu bằng `orElse`, `orElseGet` hoặc `orElseThrow`.

### 11.6. Mặc định không phù hợp ngữ nghĩa nghiệp vụ

~~~java
double average = DoubleStream.empty()
    .average()
    .orElse(0.0);
~~~

Con số `0.0` trong ví dụ không phải một quan sát có trung bình bằng 0; nó là **quy tắc thay thế khi không có quan sát**. Hãy đặt tên và ghi nhận chính sách rõ ràng. Nếu cần phân biệt, giữ lại `OptionalDouble` cho đến bước trình bày hoặc xử lý cuối.

### 11.7. Dựa vào thứ tự của findAny trên parallel stream

~~~java
String chosen = List.of("A", "B", "C").parallelStream()
    .findAny()
    .orElse("DEFAULT");
~~~

`orElse` chỉ xử lý việc Optional rỗng; nó **không làm kết quả của `findAny` trở nên xác định theo thứ tự**. Khi yêu cầu là phần tử đầu tiên, hãy dùng `findFirst` trên một nguồn có encounter order phù hợp.

## 12. Hiểu rõ hai lớp lazy: Stream và Supplier

Một điểm quan trọng của vòng đời pipeline: **Stream lazy** và **fallback lazy** là hai việc khác nhau.

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> numbers = List.of(1, 2, 3);

Optional<Integer> match = numbers.stream()
    .filter(n -> n > 1)
    .findFirst(); // Terminal operation đã chạy.

int selected = match.orElseGet(() -> expensiveFallback());
~~~

Trong ví dụ, `expensiveFallback()` là hàm trả về `int` do ứng dụng cung cấp. `findFirst()` là terminal operation: nó đã **thực thi đủ pipeline** để tìm kết quả hoặc xác định không có kết quả. Sau đó, `orElseGet` mới quyết định có gọi fallback hay không.

~~~text
Tạo Stream
    │
    ├─ filter/map/...        (mô tả pipeline lazy)
    │
    └─ findFirst()           (chạy terminal, trả Optional)
             │
             ├─ Có giá trị ──► orElseGet(...) ──► trả giá trị có sẵn
             │                                     không chạy Supplier
             │
             └─ Rỗng ───────► orElseGet(...) ──► chạy Supplier
                                                   trả fallback
~~~

`orElseGet` **không hoãn** terminal operation đã chạy. Nếu pipeline sử dụng nguồn I/O như `Files.lines`, vẫn cần đóng Stream đúng lúc bằng `try-with-resources`. Tương tự, Supplier có thể chạm tới cơ sở dữ liệu hoặc tài nguyên khác; Stream API không tự quản lý vòng đời các tài nguyên đó.

Ngoài ra, một terminal như `findFirst` có thể dừng sớm; tránh dựa vào tác dụng phụ của `map`, `peek` hoặc `filter` để đếm chính xác mọi phần tử nguồn. Việc fallback có chạy hay không là câu chuyện riêng sau khi terminal trả Optional.

## 13. Kiểm thử: chứng minh fallback chỉ chạy khi thiếu

Đoạn sau là ví dụ độc lập, không cần thư viện kiểm thử bên ngoài. `AtomicInteger` được dùng như **bộ đếm trong thử nghiệm**, không phải một biến dùng chung trong callback của parallel Stream.

~~~java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalFallbackCheck {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        String present = Optional.of("FOUND")
            .orElseGet(() -> {
                calls.incrementAndGet();
                return "DEFAULT";
            });

        if (!present.equals("FOUND") || calls.get() != 0) {
            throw new AssertionError("Supplier không được chạy khi có giá trị");
        }

        String missing = Optional.<String>empty()
            .orElseGet(() -> {
                calls.incrementAndGet();
                return "DEFAULT";
            });

        if (!missing.equals("DEFAULT") || calls.get() != 1) {
            throw new AssertionError("Supplier phải chạy khi Optional rỗng");
        }

        String eager = Optional.of("FOUND")
            .orElse(createDefault(calls));

        if (!eager.equals("FOUND") || calls.get() != 2) {
            throw new AssertionError("Đối số orElse phải được tính trước lời gọi");
        }

        System.out.println("PASS");
    }

    private static String createDefault(AtomicInteger calls) {
        calls.incrementAndGet();
        return "DEFAULT";
    }
}
~~~

Bài kiểm tra chứng minh đúng điểm khác nhau về **thực thi fallback**, thay vì chỉ so sánh kết quả cuối. Trong ứng dụng lớn, nên tách chính sách tìm kiếm, dự phòng và side effect thành các hàm có thể kiểm thử độc lập.

## 14. Cách chọn nhanh theo yêu cầu

| Nhu cầu | Giải pháp thường phù hợp | Giải thích |
| --- | --- | --- |
| Có chuỗi mặc định cố định | `orElse("UNKNOWN")` | Rõ ràng và không có chi phí tính dự phòng đáng kể. |
| Tạo object chỉ khi thiếu | `orElseGet(MyType::new)` | Tránh tạo object không được sử dụng. |
| Gọi dịch vụ ngoài chỉ khi thiếu | `orElseGet(this::loadFallback)` | Tránh I/O dư thừa khi đã có kết quả. |
| Nguồn A và B đều trả Optional | `optionalA.or(this::lookupB)` | Giữ kết quả ở dạng Optional để ghép tiếp. |
| Không cho phép thiếu dữ liệu | `orElseThrow(...)` | Thể hiện ràng buộc, không che giấu lỗi. |
| Chỉ cần thực thi hai nhánh hành động | `ifPresentOrElse(...)` | Không cần tạo giá trị trả về. |
| Kết quả từ `IntStream.max` | `OptionalInt.orElse/orElseGet` | Trả `int` trực tiếp. |
| Không có trung bình và trung bình bằng 0 phải khác nhau | Giữ `OptionalDouble` | Tránh làm mất thông tin nghiệp vụ. |
| Không chắc nguồn kết quả có thứ tự | Cân nhắc `findFirst` và nguồn ordered | Fallback không thay đổi cách Stream chọn phần tử. |

## 15. Câu hỏi tự kiểm tra

1. **`Optional.of("A").orElse(expensive())` có gọi `expensive()` không?** Có. Đối số Java được tính trước khi gọi `orElse`.
2. **`Optional.of("A").orElseGet(() -> expensive())` có gọi `expensive()` không?** Không. Supplier chỉ chạy nếu Optional rỗng.
3. **Optional rỗng thì hai cách trả fallback có khác kết quả không?** Nếu hai cách tạo cùng giá trị, kết quả giống nhau; khác biệt là cách cung cấp và thời điểm tính giá trị dự phòng.
4. **Muốn dùng fallback đã có sẵn dưới dạng hằng số nên chọn cách nào?** Thường dùng `orElse`.
5. **`orElseGet(() -> database.find(id))` hợp lệ khi `database.find` trả `Optional<Customer>` nhưng Optional hiện tại có kiểu `Optional<Customer>` không?** Không, vì Supplier của `orElseGet` phải trả `Customer`. Nếu truy vấn dự phòng trả Optional, cân nhắc `or(...)`.
6. **`orElseGet` có khiến phép `findFirst()` chưa chạy cho đến khi cần fallback không?** Không. `findFirst` là terminal operation đã trả Optional trước khi gọi `orElseGet`.
7. **`OptionalInt` có `orElseGet` không?** Có, nhận `IntSupplier` và trả `int`.
8. **Khi thiếu bản ghi bắt buộc, có nên tạo bản ghi giả?** Thường không. Sử dụng `orElseThrow` hoặc mô hình lỗi rõ ràng theo hợp đồng nghiệp vụ.
9. **`orElseGet(() -> null)` có đảm bảo tránh null không?** Không. Supplier có thể trả null; thiết kế fallback nên kiểm soát điều đó.
10. **`findAny` trên parallel stream có làm `orElse("DEFAULT")` chọn phần tử đầu tiên không?** Không. `findAny` vốn không cam kết trả phần tử đầu tiên.

**Ghi nhớ:** `orElse` phù hợp khi **giá trị mặc định đã có hoặc rất rẻ**, còn `orElseGet` phù hợp khi **cần tính hoặc lấy giá trị mặc định chỉ lúc Optional rỗng**. Sự khác biệt đến từ cách Java đánh giá đối số và Supplier, không phải từ việc Stream có chạy tuần tự hay song song. Luôn chọn fallback phù hợp ý nghĩa nghiệp vụ, giữ lại Optional nếu trạng thái thiếu dữ liệu quan trọng, và dùng `orElseThrow` khi không được phép thiếu kết quả.
