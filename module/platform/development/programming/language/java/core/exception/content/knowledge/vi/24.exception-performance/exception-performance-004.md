# Không tạo message tốn kém khi chưa cần phát sinh lỗi

Khi một ứng dụng Java kiểm tra dữ liệu hàng triệu lần, phần lớn lời gọi thường thành công. Nếu chương trình tạo trước thông điệp chẩn đoán dài rồi mới xác định có lỗi hay không, những lời gọi **hợp lệ** vẫn phải trả chi phí định dạng chuỗi, chuyển đối tượng thành text, đọc metadata hoặc cấp phát bộ nhớ. Giải pháp là giữ nguyên phép kiểm tra bắt buộc nhưng **trì hoãn tạo message cho đến khi nhánh lỗi thực sự xảy ra**.

Đây là bài về **Hiệu năng** trong **Java Core – Exception**, áp dụng cho Java 17+. Nó giải thích việc đánh giá đối số, sử dụng `if` đúng cách, `Objects.requireNonNull` với `Supplier<String>`, `Optional.orElseThrow`, logging có điều kiện, cách bảo toàn chất lượng chẩn đoán và cách đo hiệu năng đúng.

## 1. Chi phí xuất hiện ở đâu?

Xem lời gọi sau:

```java
Objects.requireNonNull(account,
        "account không hợp lệ: " + expensiveDiagnostic());
```

Trong Java, **các biểu thức đối số được đánh giá trước khi phương thức được gọi**. Vì thế `expensiveDiagnostic()` có thể chạy cả khi `account` khác `null` và `Objects.requireNonNull` trả về thành công. Phương thức nhận một `String` đã được chuẩn bị, nên không có cách tự bỏ qua công đoạn xây chuỗi đó.

Các công việc cần tách rõ:

| Công việc | Tác dụng | Có nên làm ở happy path? |
|---|---|---|
| Kiểm tra điều kiện | Xác định đầu vào hợp lệ hay không | **Có**, nếu hợp đồng yêu cầu |
| Tạo thông điệp lỗi | Giải thích điều kiện đã thất bại | **Không**, nếu chưa phát sinh lỗi |
| Khởi tạo Throwable | Tạo đối tượng ngoại lệ và thông tin stack trace thường đi kèm | **Không**, nếu chưa phát sinh lỗi |
| Ghi log | Gửi dữ liệu tới hệ thống chẩn đoán | Theo mức log, chính sách và kết quả thực |

Phép so sánh `amount < 0` thường rẻ. Một message gọi JSON serializer, duyệt hàng nghìn item hoặc truy cập metadata động có thể đắt hơn rất nhiều. Chương trình cần trả giá tạo message trên **đường lỗi**, nhưng không nên trả cùng khoản chi đó trên **đường thành công**.

Luồng chuẩn:

```text
Nhận giá trị
    |
    v
Kiểm tra điều kiện
    | đúng                      | sai
    v                           v
Tiếp tục, không tạo message    Xây message cần thiết
                                |
                                v
                         Tạo/throw exception
```

**Đừng bỏ validation để tối ưu.** Việc không kiểm tra một giá trị có thể làm ứng dụng nhận dữ liệu sai. Chúng ta chỉ di chuyển công việc phục vụ **chẩn đoán lỗi** vào nơi thật sự cần.

## 2. Tạo message bên trong nhánh `if`

Đây là mẫu rất rõ ràng:

```java
if (quantity < 0) {
    throw new IllegalArgumentException(
            "quantity=" + quantity + ", state=" + describeState());
}
```

Đoạn mã trên là **mảnh minh họa**; `quantity` và `describeState()` phải tồn tại trong phương thức. Nếu `quantity >= 0`, `describeState()` hoàn toàn không được gọi. Điều này đúng theo **ngữ nghĩa điều khiển luồng Java**, không cần đặt cược vào tối ưu hóa JIT.

So sánh mẫu tạo sớm:

```java
String message = "quantity=" + quantity
        + ", state=" + describeState();

if (quantity < 0) {
    throw new IllegalArgumentException(message);
}
```

Ở đây message được tạo ngay cả khi `quantity` hợp lệ. Nếu validation chạy trong một vòng lặp hoặc API tần suất cao, chi phí không cần thiết có thể tích lũy.

### Chương trình độc lập: đo số lần tạo message

Tệp `LazyErrorMessageDemo.java`:

```java
public class LazyErrorMessageDemo {
    private static int builds;

    static String describe(int amount) {
        builds++;
        return "amount âm: " + amount;
    }

    static void validate(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException(describe(amount));
        }
    }

    public static void main(String[] args) {
        validate(10);
        System.out.println("valid builds = " + builds);

        try {
            validate(-3);
        } catch (IllegalArgumentException error) {
            System.out.println("error = " + error.getMessage());
        }

        System.out.println("all builds = " + builds);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac LazyErrorMessageDemo.java
java LazyErrorMessageDemo
```

Kết quả:

```text
valid builds = 0
error = amount âm: -3
all builds = 1
```

`validate(10)` vẫn kiểm tra điều kiện nhưng **không** gọi `describe`. Khi `validate(-3)` thất bại, chương trình mới tạo message rồi ném `IllegalArgumentException`.

Bộ đếm trong ví dụ chỉ giúp kiểm tra **thời điểm đánh giá**, không phải một benchmark. Nó chạy trong luồng `main`; không nên đưa biến đếm toàn cục thiếu đồng bộ vào hệ thống nhiều luồng để đo hiệu năng production.

## 3. `Objects.requireNonNull` và `Supplier<String>`

Java có hai overload đáng chú ý:

```java
static <T> T requireNonNull(T obj, String message)

static <T> T requireNonNull(
        T obj, java.util.function.Supplier<String> messageSupplier)
```

Overload đầu tiên nhận `String` đã được xây trước. Overload thứ hai nhận một **hàm sản sinh message**; nếu `obj != null`, `Supplier.get()` **không được gọi**. Nếu `obj == null`, phương thức gọi supplier để lấy message và ném `NullPointerException`.

Ví dụ:

```java
Objects.requireNonNull(user,
        () -> "Không có user, request=" + expensiveContext());
```

Đây là mảnh minh họa. `expensiveContext()` chỉ chạy khi `user` thực sự là `null`. Nếu message đã là hằng chuỗi như `"user không được null"`, overload `String` đơn giản và thường đủ tốt; không cần biến mọi hằng thành lambda.

### Chương trình độc lập: eager và lazy

Tệp `RequireNonNullMessageDemo.java`:

```java
import java.util.Objects;

public class RequireNonNullMessageDemo {
    private static int builds;

    static String message() {
        builds++;
        return "user không được null";
    }

    public static void main(String[] args) {
        String value = "Lan";

        Objects.requireNonNull(value, message());
        System.out.println("eager = " + builds);

        builds = 0;
        Objects.requireNonNull(value, () -> message());
        System.out.println("lazy valid = " + builds);

        try {
            Objects.requireNonNull(null, () -> message());
        } catch (NullPointerException error) {
            System.out.println("lazy error = " + error.getMessage());
        }
        System.out.println("lazy invalid = " + builds);
    }
}
```

Chạy:

```bash
javac RequireNonNullMessageDemo.java
java RequireNonNullMessageDemo
```

Kết quả:

```text
eager = 1
lazy valid = 0
lazy error = user không được null
lazy invalid = 1
```

Ở lời gọi eager, `message()` chạy trước `requireNonNull` dù `value` hợp lệ. Ở lời gọi lazy, lambda không thực thi cho `value` khác `null`. Với `null`, supplier chạy đúng một lần và message được gắn vào `NullPointerException`.

Một vài giới hạn quan trọng:

- `requireNonNull` dùng **`NullPointerException`**; đừng đổi sang API này nếu hợp đồng của phương thức yêu cầu `IllegalArgumentException` hoặc một exception nghiệp vụ khác.
- `Supplier.get()` có thể ném ngoại lệ. Nếu việc tạo message bị lỗi, caller có thể quan sát **lỗi từ supplier**, che mất lỗi null ban đầu.
- Supplier trả `null` sẽ tạo `NullPointerException` với message null. Không mặc định API sẽ tự tạo message hữu ích.
- Lambda có thể capture biến và đối tượng; việc tạo/capture lambda không phải lúc nào cũng có chi phí bằng không. Lợi ích rõ nhất là **không chạy tác vụ chẩn đoán tốn kém** trên đường hợp lệ.
- Tránh để supplier thực hiện I/O hoặc truy vấn mạng. Khi hệ thống đã gặp lỗi, việc tạo message phải càng đáng tin và nhanh càng tốt.

## 4. `Optional.orElseThrow`: trì hoãn cả việc tạo exception

Đôi khi không chỉ message mà **cả đối tượng ngoại lệ** cũng không cần tồn tại trên happy path. `Optional.orElseThrow(Supplier<? extends X>)` nhận một supplier **tạo exception**, chỉ gọi nó khi `Optional` rỗng.

```java
String name = maybeName.orElseThrow(
        () -> new IllegalStateException(
                "Không tìm thấy tên cho id=" + id));
```

Đây là mảnh minh họa: `maybeName` là `Optional<String>`, `id` đã khai báo. Nếu Optional có giá trị, Java trả giá trị đó, không tạo `IllegalStateException`.

### Chương trình độc lập

Tệp `OptionalThrowLazyDemo.java`:

```java
import java.util.Optional;

public class OptionalThrowLazyDemo {
    private static int exceptionsBuilt;

    static IllegalStateException missing() {
        exceptionsBuilt++;
        return new IllegalStateException("không tìm thấy hồ sơ");
    }

    public static void main(String[] args) {
        String value = Optional.of("OK")
                .orElseThrow(() -> missing());

        System.out.println("value = " + value);
        System.out.println("after present = " + exceptionsBuilt);

        try {
            Optional.<String>empty().orElseThrow(() -> missing());
        } catch (IllegalStateException error) {
            System.out.println("missing = " + error.getMessage());
        }

        System.out.println("after empty = " + exceptionsBuilt);
    }
}
```

Chạy:

```bash
javac OptionalThrowLazyDemo.java
java OptionalThrowLazyDemo
```

Đầu ra:

```text
value = OK
after present = 0
missing = không tìm thấy hồ sơ
after empty = 1
```

`Optional.orElseThrow()` **không có đối số** cũng tồn tại và ném `NoSuchElementException` khi rỗng. Dùng supplier khi muốn loại exception và message tùy biến; chọn loại lỗi phù hợp hợp đồng.

Đừng nhầm với:

```java
String value = optional.orElse(expensiveFallback());
```

`orElse` nhận **giá trị** đã được đánh giá, vì thế `expensiveFallback()` vẫn chạy khi Optional có giá trị. Nếu muốn fallback lazy, dùng:

```java
String value = optional.orElseGet(() -> expensiveFallback());
```

Hai mảnh cuối là ví dụ minh họa với `optional` kiểu `Optional<String>` và hàm `expensiveFallback()` trả `String`. `orElseGet` áp dụng cho **giá trị dự phòng**, còn `orElseThrow` áp dụng khi **thiếu giá trị là lỗi**. Điểm chung là supplier chỉ được dùng lúc cần.

## 5. `IllegalArgumentException` không có constructor nhận Supplier

Trong Java 17, constructor thông dụng là:

```java
new IllegalArgumentException(String message)
new IllegalArgumentException(String message, Throwable cause)
```

`IllegalArgumentException` không có constructor chuẩn `IllegalArgumentException(Supplier<String>)`. Việc viết:

```java
throw new IllegalArgumentException(() -> expensiveMessage());
```

là **không hợp lệ**. Nếu cần loại exception này, chỉ việc đặt phép tạo message vào nhánh sai:

```java
if (count <= 0) {
    throw new IllegalArgumentException(
            expensiveMessageFor(count));
}
```

Đây là mảnh mã minh họa. Không cần tạo lớp exception tùy chỉnh chỉ để trì hoãn tính chuỗi. Một câu `if` có thể vừa nhanh vừa dễ bảo trì.

Nếu dự án có nhiều kiểm tra cùng một hợp đồng, có thể viết tiện ích nhận supplier:

```java
static void requirePositive(
        int count, java.util.function.Supplier<String> message) {
    if (count <= 0) {
        throw new IllegalArgumentException(message.get());
    }
}
```

Đây là **phương thức hợp lệ có thể đặt trong class**. Cách sử dụng:

```java
requirePositive(itemsCount,
        () -> "Số phần tử không hợp lệ: " + itemsCount);
```

Đoạn dùng `itemsCount` là mảnh minh họa. Tiện ích chỉ có ích khi làm rõ một quy tắc dùng lại; tránh thêm abstraction phức tạp nếu chỉ có một chỗ gọi.

Đừng bỏ qua tính an toàn của supplier: nó có thể là `null`, trả `null`, hoặc ném lỗi. Cũng cần phân biệt việc trì hoãn tạo **message** với việc trì hoãn **validation**: phải đánh giá điều kiện đúng thời điểm, trên dữ liệu đúng trạng thái.

## 6. Chuỗi dài, `String.format` và `formatted(...)`

Ba cách tạo thông điệp phổ biến:

```java
"amount=" + amount

String.format("amount=%d", amount)

"amount=%d".formatted(amount)
```

`String.formatted` có từ Java 15, dùng được trên Java 17. Tất cả đều tạo chuỗi khi **biểu thức được đánh giá**. Nếu nằm bên trong nhánh lỗi, chúng không tạo message trên đường thành công:

```java
if (actual < min || actual > max) {
    throw new IllegalArgumentException(
            "actual=%d ngoài khoảng [%d, %d]"
                    .formatted(actual, min, max));
}
```

Đây là mảnh mã minh họa trong phương thức đã có `actual`, `min`, `max`.

Với chi phí nhỏ như nối hai số nguyên, **độ rõ ràng** thường quan trọng hơn tối ưu vi mô. `String.format` có chi phí định dạng và xử lý mẫu riêng; nhưng việc tranh luận `"x=" + x` so với `.formatted(x)` ít ý nghĩa khi lỗi chỉ xảy ra một lần mỗi triệu request.

Chi phí lớn hơn thường đến từ:

| Nguồn tạo message | Vì sao có thể đắt? | Lựa chọn |
|---|---|---|
| Duyệt collection lớn | Xây chuỗi dài, nhiều allocation | Chỉ lấy count hoặc vài ID an toàn |
| JSON serialization | Duyệt object graph, format | Không serialize toàn bộ trong exception |
| `toString()` của entity | Có thể duyệt quan hệ sâu hoặc lazy-load | In trường cần thiết, ổn định |
| Đọc stack/context | Thu thập cấu trúc lớn | Chỉ làm khi lỗi và khi cần |
| Lookup từ DB/network | I/O có thể treo hoặc lỗi thêm | Tránh dùng trong message |
| Format ngày/locale phức tạp | Chi phí parser/formatter | Dùng formatter phù hợp, trong nhánh lỗi |

Trong Java hiện đại, phép nối chuỗi bằng `+` được JVM tối ưu tốt trong nhiều tình huống; thay toàn bộ bằng `StringBuilder` thủ công hiếm khi là bước đầu tiên có giá trị. Hãy **loại bỏ công việc chạy không cần thiết** trước, rồi profile đường nóng để quyết định tối ưu biểu thức cụ thể.

## 7. Ví dụ xấu: serialize dữ liệu thành message trước khi kiểm tra

Giả sử chương trình phải xác minh số lượng đơn hàng. Cách dưới đây có thể làm việc vô ích:

```java
String fullDump = orders.stream()
        .map(Object::toString)
        .collect(java.util.stream.Collectors.joining(", "));

if (quantity < 0) {
    throw new IllegalArgumentException(
            "quantity sai, orders=" + fullDump);
}
```

Đây là **mảnh mã minh họa** với `orders` và `quantity` đã có trong phạm vi. Dù `quantity >= 0`, toàn bộ `orders` vẫn bị duyệt và chuyển thành text. Một message khổng lồ còn có thể gây chi phí log ingestion và rò rỉ dữ liệu.

Trong nhiều tình huống, chỉ cần:

```java
if (quantity < 0) {
    throw new IllegalArgumentException(
            "quantity âm: " + quantity
            + ", orderCount=" + orders.size());
}
```

Nếu cần đầy đủ một số phần tử để chẩn đoán, hãy giới hạn số item, bảo vệ dữ liệu nhạy cảm và chỉ thực hiện trong nhánh lỗi.

Một message có chất lượng tốt thường nêu **ràng buộc bị vi phạm, tên trường và một vài giá trị an toàn**, thay vì dump trạng thái toàn bộ ứng dụng.

## 8. Logging có điều kiện và message exception là hai cơ chế khác

Lazy logging cũng liên quan đến chủ đề hiệu năng, nhưng khác với việc tạo exception message.

Ví dụ framework logger kiểu SLF4J:

```java
logger.debug("Request {} đã hoàn thành", requestId);
```

Đây là **mảnh mã tích hợp**, không chạy độc lập nếu chưa thêm thư viện/logger. Placeholder thường giúp logger trì hoãn định dạng chuỗi khi mức log không bật. Nhưng ngữ nghĩa Java vẫn áp dụng: biểu thức làm **đối số** được đánh giá trước khi lời gọi diễn ra.

Ví dụ:

```java
logger.debug("Payload: {}", expensiveSerialize(payload));
```

Ngay cả khi log `DEBUG` bị tắt, `expensiveSerialize(payload)` vẫn được chạy để tạo đối số. Guard nếu logging API cho phép:

```java
if (logger.isDebugEnabled()) {
    logger.debug("Payload: {}", expensiveSerialize(payload));
}
```

Mã trên là ví dụ tích hợp, phụ thuộc logger và các biến đã định nghĩa. Một số API logging hiện đại có hỗ trợ supplier/lazy argument, nhưng cần tra hợp đồng **đúng phiên bản**, không giả định mọi framework hiểu Supplier.

Với **validation**, không được viết:

```java
if (logger.isDebugEnabled() && invalid) {
    throw new IllegalArgumentException("đầu vào sai");
}
```

Vì khi DEBUG tắt, điều kiện `invalid` có thể không được kiểm tra và lỗi bị bỏ qua. **Tính đúng của ứng dụng không phụ thuộc cấu hình logging.**

## 9. Message supplier phải an toàn ngay khi hệ thống đang lỗi

Một message được dựng *lazily* có thể tiết kiệm happy path nhưng vẫn gây rắc rối nghiêm trọng nếu dùng I/O hoặc thay đổi trạng thái.

Ví dụ không nên:

```java
if (user == null) {
    String accountName = remoteApi.lookupAccount();
    throw new IllegalArgumentException(
            "Không thấy user thuộc account " + accountName);
}
```

Đây là **mảnh minh họa**. Nếu `remoteApi.lookupAccount()` timeout hoặc ném ngoại lệ mới, caller có thể chỉ thấy lỗi mạng, còn lỗi null ban đầu bị che mất. Nếu hàm lookup gây side effect, chỉ việc tạo message có thể làm thay đổi dữ liệu.

Lựa chọn ổn định hơn:

```java
if (user == null) {
    throw new IllegalArgumentException(
            "user bắt buộc, requestId=" + requestId);
}
```

Cũng là mảnh minh họa, với `requestId` được chuẩn bị an toàn. Nếu bắt buộc thu thập thông tin thêm, hãy dùng hệ thống telemetry ở boundary có ngân sách thời gian và quy tắc an toàn rõ ràng.

Một số lưu ý thực tế:

- Không gọi DB hoặc HTTP chỉ để tạo chuỗi lỗi.
- Không gọi `toString()` trên object có lazy-loading ngoài dự kiến.
- Giới hạn độ dài message và bỏ dữ liệu bí mật (password, token, key, PII).
- Không dùng `Supplier.get()` có thể ném checked/unchecked exception mà không có chính sách.
- Nếu phải bọc ngoại lệ ở tầng cao, **giữ cause** bằng constructor `new IllegalStateException("...", original)` khi phù hợp.

Trì hoãn message giúp tránh công vô ích; nó không phải giấy phép biến message thành một thao tác tốn kém hoặc không đáng tin cậy.

## 10. Không tạo trước đối tượng Throwable

Ngoài message, việc tạo exception thường liên quan điền stack trace. Vì thế không nên khởi tạo một Throwable sẵn trước khi biết có lỗi:

```java
IllegalStateException cachedError =
        new IllegalStateException("không hợp lệ");

// Mãi sau mới kiểm tra:
if (invalid) {
    throw cachedError;
}
```

Đây là mảnh minh họa **không khuyến nghị**. Exception được tạo ngay cả khi `invalid` là `false`. Nếu tái sử dụng cùng exception nhiều lần, stack trace còn có thể phản ánh nơi tạo ban đầu chứ không phải vị trí phát sinh lỗi, làm việc điều tra khó hơn.

Thay bằng:

```java
if (invalid) {
    throw new IllegalStateException("không hợp lệ");
}
```

Tạo và ném exception khi điều kiện thật sự vi phạm. Tương tự, không nên dùng exception như một giá trị điều khiển thông thường trong vòng lặp nóng (ví dụ ném exception cho một kết quả dự kiến như “không tìm thấy trong cache” mỗi lần). Khi lỗi là trạng thái bình thường có tần suất cao, cân nhắc API trả `Optional`, mã trạng thái hoặc kiểu kết quả phù hợp.

Cần thận trọng với các kỹ thuật **vô hiệu hóa stack trace** để tăng tốc ngoại lệ: chúng có thể phá khả năng chẩn đoán, đặc biệt ở production. Đầu tiên hãy tối ưu **khi nào tạo lỗi** và **khi nào tạo message**, rồi mới benchmark trade-off đặc biệt nếu thực sự cần.

## 11. Ví dụ độc lập: thứ tự đánh giá không phụ thuộc tối ưu JIT

Tệp `MessageEvaluationOrderDemo.java`:

```java
import java.util.Objects;

public class MessageEvaluationOrderDemo {
    private static int calls;

    static String diagnostics() {
        calls++;
        return "diagnostic #" + calls;
    }

    static void eager(String value) {
        Objects.requireNonNull(value, diagnostics());
    }

    static void lazy(String value) {
        Objects.requireNonNull(value, () -> diagnostics());
    }

    public static void main(String[] args) {
        eager("OK");
        lazy("OK");
        System.out.println("after valid = " + calls);

        try {
            lazy(null);
        } catch (NullPointerException error) {
            System.out.println("caught = " + error.getMessage());
        }

        System.out.println("all calls = " + calls);
    }
}
```

Chạy:

```bash
javac MessageEvaluationOrderDemo.java
java MessageEvaluationOrderDemo
```

Kết quả chính xác:

```text
after valid = 1
caught = diagnostic #2
all calls = 2
```

Thân `diagnostics()` tăng bộ đếm, nên JIT không thể giả vờ không có side effect của lời gọi eager. Ví dụ làm rõ ngữ nghĩa chứ không phải cho biết lazy nhanh hơn bao nhiêu nanosecond.

Không nên dùng một bộ đếm không thread-safe như ví dụ này trong nhiều worker; nó chỉ để xác định trình tự đơn luồng.

## 12. Benchmark đúng: lazy không đồng nghĩa luôn nhanh hơn

Lợi ích của lazy message phụ thuộc **chi phí dựng message** và **tần suất lỗi**. Với một hằng chuỗi:

```java
Objects.requireNonNull(value, "value không được null");
```

không có công việc định dạng đắt đỏ cần tránh. Lambda có thể không đem lại ích lợi đo được, thậm chí khiến code rườm rà.

Một phép đo nghiêm túc nên tách các trường hợp sau:

| Kịch bản | Điều cần đo |
|---|---|
| Input hợp lệ, message eager đắt | Chi phí lãng phí trên happy path |
| Input hợp lệ, message lazy | Chi phí điều kiện và cấu trúc lambda |
| Input lỗi, message eager | Chi phí format và tạo exception |
| Input lỗi, message lazy | Chi phí gọi supplier, format và tạo exception |

Khi cần số liệu tin cậy, ưu tiên công cụ như **JMH** với warmup, nhiều fork, dữ liệu không hằng, kết quả được tiêu thụ đúng cách và tỷ lệ lỗi thực tế. Đừng lấy vài lần `System.nanoTime()` rồi kết luận chắc chắn về nanosecond/op vì JIT, escape analysis, GC, hệ điều hành và dead-code elimination đều có thể làm sai lệch phép đo.

Quan sát cả **allocation rate và GC**, không chỉ thời gian. Một message vô ích trong đường nóng có thể làm tăng áp lực bộ nhớ ngay cả khi độ trễ đơn lẻ khó phát hiện. Tuy nhiên, nếu profiling cho thấy chi phí thấp hơn việc duy trì abstraction mới, hãy ưu tiên code dễ đọc.

Nếu phần lớn giao dịch **đều lỗi**, tạo message lazy có thể không giúp được bao nhiêu. Cần sửa nguyên nhân lỗi hoặc thiết kế kết quả thông thường sao cho không lạm dụng exception.

## 13. Nguy cơ đọc dữ liệu trễ trong môi trường đa luồng

Một supplier ghi nhận đối tượng và **đọc trạng thái khi được gọi**, không nhất thiết khi lambda được tạo:

```java
Objects.requireNonNull(user,
        () -> "activeTasks=" + sharedTasks.size());
```

Đây là mảnh minh họa. Nếu `sharedTasks` thay đổi đồng thời, giá trị quan sát được phụ thuộc thời điểm `get()` chạy. Với overload `Objects.requireNonNull`, supplier được gọi ngay trong lời gọi khi giá trị null, nên khoảng thời gian thường nhỏ; nhưng các utility khác có thể **giữ supplier và gọi sau**, làm khác biệt thời gian đáng kể.

Nếu message cần snapshot nhất quán, có thể lưu các giá trị an toàn tại điểm kiểm tra hoặc dùng cơ chế synchronization hợp đồng yêu cầu. Đừng trì hoãn một phép kiểm tra bắt buộc đến khi dữ liệu đã đổi trạng thái. **Trì hoãn định dạng chẩn đoán**, không trì hoãn điều kiện bảo vệ tính đúng.

Đồng thời cân nhắc lifetime của lambda capture: supplier được giữ trong object sống lâu có thể kéo dài vòng đời của cả object graph được capture. Đừng dùng Supplier tùy tiện như cache message cho mọi request.

## 14. Những sai lầm thường gặp

### Dựng message trước khi kiểm tra

Sai:

```java
String details = expensiveDescribe(input);
if (invalid) {
    throw new IllegalArgumentException(details);
}
```

Đúng khi `details` chỉ phục vụ lỗi:

```java
if (invalid) {
    throw new IllegalArgumentException(expensiveDescribe(input));
}
```

Đây là các mảnh minh họa với biến/hàm do ứng dụng định nghĩa.

### Tưởng `Objects.requireNonNull(value, expensive())` là lazy

Không phải. Nó chọn overload nhận **String**, nên `expensive()` đã chạy trước lời gọi. Cần truyền supplier vào overload tương ứng:

```java
Objects.requireNonNull(value, () -> expensive());
```

### Nghĩ message luôn là chi phí lớn nhất

Khởi tạo Throwable thường liên quan stack trace; việc ném nhiều exception cho luồng bình thường có thể đắt hơn tối ưu biểu thức message. Tập trung vào khả năng thiết kế lại hot path trước khi tự viết formatter phức tạp.

### Dùng lazy supplier có truy vấn ngoài

Supplier chỉ chạy khi lỗi, nhưng đây là thời điểm không nên mở thêm kết nối hoặc gây lỗi mới. Giữ message đơn giản, dựa trên dữ liệu đã có.

### Chuyển mọi validation sang `Objects.requireNonNull`

Nó chỉ kiểm tra `null` và ném `NullPointerException`. Không dùng để thay điều kiện nghiệp vụ cần `IllegalArgumentException`, checked exception hoặc exception riêng.

### Dùng logger placeholder rồi vẫn serialize đối số

```java
logger.debug("Object={}", serialize(largeObject));
```

Java đánh giá `serialize` trước khi vào logger. Nếu không muốn chạy khi DEBUG tắt, dùng guard hoặc API lazy argument đúng chuẩn thư viện.

### Dùng message `toString()` vô hạn

Một object graph lớn hoặc có vòng tham chiếu có thể tạo chuỗi khổng lồ, lỗi hoặc lộ dữ liệu. Chỉ hiển thị thông tin có giá trị, kích thước giới hạn.

### Tắt stack trace để làm đẹp benchmark

Đây là đánh đổi lớn về chẩn đoán. Không tối ưu trước khi có số liệu thực tế và chính sách rõ về điều gì cần lưu trong lỗi.

### Nhầm kiểm tra với tạo message

Điều kiện bảo vệ dữ liệu vẫn phải chạy đúng lúc. Không trì hoãn validation với lập luận “thường không lỗi”; chỉ trì hoãn **công việc không cần trong trạng thái hợp lệ**.

## 15. Mẫu quyết định nhanh

| Nhu cầu | Cách dùng phù hợp |
|---|---|
| Kiểm tra một điều kiện và ném lỗi tùy chỉnh | `if (invalid) throw new ...(...)` |
| `Objects.requireNonNull` với message đắt | `Objects.requireNonNull(value, () -> message())` |
| `Optional` thiếu dữ liệu thì ném exception | `optional.orElseThrow(() -> new ...(...))` |
| `Optional` cần giá trị fallback đắt | `optional.orElseGet(() -> compute())` |
| Format nhiều trường chỉ khi điều kiện sai | Đặt format trong nhánh lỗi |
| Logging có đối số tính toán đắt khi level tắt | Guard hoặc supplier được logger hỗ trợ |
| Có lỗi dự kiến xảy ra quá thường xuyên | Xem lại API/luồng điều khiển, không lạm dụng exception |
| Muốn chứng minh nhanh hơn | Profile hoặc JMH với tỷ lệ success/failure đúng thực tế |

Để review một đoạn code, hãy hỏi: “Nếu dữ liệu **hợp lệ**, có hàm nào chỉ phục vụ lỗi vẫn được gọi không?” Nếu câu trả lời là có, dời công việc ấy vào nhánh lỗi hoặc dùng overload nhận supplier. Sau đó xác nhận loại exception và message khi **thật sự lỗi** vẫn đúng.

## 16. Checklist áp dụng trong production

- Kiểm tra input vẫn được thực hiện đúng điều kiện và thời điểm.
- Không xây `String.format`, `.formatted`, JSON, `toString()` đắt đỏ trên đường hợp lệ.
- Dùng overload `Supplier<String>` của `Objects.requireNonNull` **đúng chỗ**, không nhầm với overload `String`.
- Dùng `Optional.orElseThrow` khi thiếu dữ liệu là lỗi; đừng tạo exception trước khi biết Optional rỗng.
- Message an toàn, không có side effect nghiệp vụ, không đòi gọi mạng/DB và không tiết lộ secret.
- Loại exception, message, cause và hành vi caller khi lỗi được bảo toàn sau tối ưu.
- Không cache hoặc tái sử dụng Throwable sai ngữ cảnh.
- Log message không bị đánh giá sớm bởi đối số Java khi level tắt.
- Benchmark/monitor đủ tốt trước khi áp dụng các tối ưu phức tạp hơn.

**Ghi nhớ:** Java đánh giá đối số phương thức trước khi gọi. Vì vậy **đừng tạo thông điệp lỗi tốn kém khi đường kiểm tra còn có thể thành công**. Đặt công việc dựng message trong nhánh lỗi hoặc dùng API `Supplier` thật; giữ đầy đủ thông tin chẩn đoán khi có lỗi, và chỉ tối ưu sâu sau khi có số liệu.
