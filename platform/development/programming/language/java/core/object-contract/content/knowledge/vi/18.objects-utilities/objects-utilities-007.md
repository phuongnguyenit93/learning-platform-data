# `Objects.requireNonNullElse()` và `Objects.requireNonNullElseGet()` trong Java

Hai phương thức tĩnh `java.util.Objects.requireNonNullElse()` và `Objects.requireNonNullElseGet()` giúp chọn **một giá trị thay thế khi giá trị chính là `null`**. Cả hai đều bảo đảm kết quả trả về **khác `null`**, nhưng khác nhau về **thời điểm tạo giá trị dự phòng**: `requireNonNullElse()` nhận sẵn một giá trị, còn `requireNonNullElseGet()` nhận một `Supplier` và chỉ gọi `get()` khi thực sự cần.

Đây là khác biệt có ý nghĩa khi việc tạo dự phòng tốn thời gian, cấp phát bộ nhớ, đọc cấu hình, gọi dịch vụ hoặc có tác dụng phụ. Hiểu đúng quy tắc đánh giá đối số và kiểm tra `null` giúp tránh lỗi khó thấy ngay cả khi giá trị chính luôn tồn tại.

Hai API có từ **Java 9** và sử dụng bình thường trên Java 17+.

## 1. Chữ ký và hợp đồng trả về

Chữ ký khái quát:

```java
public static <T> T requireNonNullElse(T obj, T defaultObj);

public static <T> T requireNonNullElseGet(
        T obj, Supplier<? extends T> supplier);
```

`Supplier` nằm trong `java.util.function.Supplier`. Cả hai phương thức trả **tham chiếu đã nhận** hoặc **tham chiếu dự phòng**, không thực hiện sao chép đối tượng và không thay đổi trạng thái của tham số chính.

| Trường hợp | `requireNonNullElse(obj, defaultObj)` | `requireNonNullElseGet(obj, supplier)` |
| --- | --- | --- |
| `obj != null` | Trả `obj` | Trả `obj`; không gọi `supplier.get()` |
| `obj == null` | Trả `defaultObj` nếu khác `null` | Gọi `supplier.get()` và trả kết quả nếu khác `null` |
| `obj == null`, dự phòng là `null` | Ném `NullPointerException` | Ném `NullPointerException` nếu supplier là `null` hoặc `get()` trả `null` |
| `obj != null`, dự phòng được truyền là `null` | Vẫn trả `obj` | Vẫn trả `obj`, kể cả khi supplier được truyền là `null` |
| Dự phòng tốn chi phí để *tạo* | Biểu thức tạo đối số được đánh giá trước khi phương thức chạy | Thân `get()` chỉ chạy nếu `obj == null` |
| Gọi lại nhiều lần khi `obj == null` | Dùng đối tượng dự phòng được truyền ở lần gọi đó | Có thể chạy lại `get()` mỗi lần gọi; không tự cache |

**Lưu ý về trường hợp dùng `null`:** Chính giá trị dự phòng không null là điều kiện bắt buộc **khi cần sử dụng nó**. Nếu `obj` đã khác `null`, cả hai phương thức đều có thể trả kết quả mà không kiểm tra tính hợp lệ của fallback không được sử dụng.

`requireNonNullElseGet()` không phải “phiên bản đồng bộ”, không phải API cache và cũng không tự xử lý `Optional`. Nó chỉ trì hoãn việc gọi `Supplier.get()`.

## 2. `requireNonNullElse()` — giá trị dự phòng có sẵn

Ví dụ đơn giản:

```java
String displayName =
        Objects.requireNonNullElse(userName, "Khách");
```

Đây là **mảnh code minh họa**, giả định `userName` là biến `String` và đã import `java.util.Objects`. Nếu `userName` khác `null`, phương thức trả chính chuỗi đó; nếu bằng `null`, trả `"Khách"`.

Cần phân biệt hai điều:

1. **Tham số `defaultObj` là một giá trị, không phải một phép tính bị hoãn.** Theo quy tắc Java, mọi biểu thức đối số của lời gọi phương thức được đánh giá trước khi phương thức bắt đầu thực thi.
2. **Việc có trả fallback hay không vẫn phụ thuộc `obj`.** Giá trị dự phòng có thể được tạo ra nhưng không được sử dụng.

Ví dụ:

```java
String value = Objects.requireNonNullElse(
        "Có sẵn", createExpensiveDefault());
```

Ở đây `createExpensiveDefault()` **vẫn chạy** để tạo đối số thứ hai, ngay cả khi kết quả `value` là `"Có sẵn"`. Nếu hàm tạo dự phòng phát sinh ngoại lệ, ngoại lệ xảy ra **trước khi** `requireNonNullElse()` có cơ hội chọn giá trị chính.

Điều này không có nghĩa truyền `"Khách"` hay một hằng số rẻ luôn là vấn đề. `requireNonNullElse()` thường là lựa chọn **đơn giản nhất** nếu fallback đã tồn tại hoặc rất rẻ.

## 3. `requireNonNullElseGet()` — tính dự phòng khi cần

Cú pháp tương ứng:

```java
String displayName = Objects.requireNonNullElseGet(
        userName, () -> createExpensiveDefault());
```

Đây cũng là **mảnh code minh họa**. Java vẫn **đánh giá biểu thức tạo `Supplier`** trước lời gọi (ví dụ tạo đối tượng lambda hoặc gọi một hàm trả về supplier); nhưng **phần thân lambda**, tức `createExpensiveDefault()`, không chạy nếu `userName != null`.

Có thể truyền method reference:

```java
String name = Objects.requireNonNullElseGet(
        userName, ConfigDefaults::loadDefaultName);
```

`ConfigDefaults::loadDefaultName` là ví dụ dạng cú pháp, giả định lớp `ConfigDefaults` có phương thức phù hợp trả `String` không null. Method reference chỉ giúp mô tả một phép gọi bị hoãn; nó không tự động cache hay xác thực kết quả cho đến khi gọi `get()`.

**Quy tắc chọn:** nếu dữ liệu dự phòng cần tính toán và có thể bỏ qua khi giá trị chính hiện diện, `requireNonNullElseGet()` thể hiện rõ ý định *lazy fallback*.

## 4. Chương trình Java 17+ chứng minh eager và lazy

Lưu toàn bộ chương trình vào **`ElseTimingDemo.java`**:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class ElseTimingDemo {
    private static String fallback(AtomicInteger calls) {
        int number = calls.incrementAndGet();
        return "fallback-" + number;
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        String eagerPresent = Objects.requireNonNullElse(
                "provided", fallback(calls));
        String lazyPresent = Objects.requireNonNullElseGet(
                "provided", () -> fallback(calls));

        System.out.println("eager present: " + eagerPresent);
        System.out.println("lazy present: " + lazyPresent);
        System.out.println("calls after present: "
                + calls.get());

        String eagerAbsent = Objects.requireNonNullElse(
                (String) null, fallback(calls));
        String lazyAbsent = Objects.requireNonNullElseGet(
                (String) null, () -> fallback(calls));

        System.out.println("eager absent: " + eagerAbsent);
        System.out.println("lazy absent: " + lazyAbsent);
        System.out.println("calls after absent: "
                + calls.get());
    }
}
```

Biên dịch và chạy:

```bash
javac ElseTimingDemo.java
java ElseTimingDemo
```

Kết quả chính xác:

```text
eager present: provided
lazy present: provided
calls after present: 1
eager absent: fallback-2
lazy absent: fallback-3
calls after absent: 3
```

**Giải thích:**

- Lần đầu, `"provided"` không null, nhưng biểu thức `fallback(calls)` của `requireNonNullElse()` vẫn chạy: bộ đếm lên `1`. Kết quả hàm vẫn là `"provided"`.
- `requireNonNullElseGet("provided", () -> fallback(calls))` không gọi `get()`, nên bộ đếm giữ nguyên.
- Khi tham số chính null, cả hai API phải có giá trị dự phòng. Lần gọi eager tính chuỗi `"fallback-2"` trước, lần gọi lazy tính `"fallback-3"` bên trong supplier.
- Mã dùng `AtomicInteger` để đếm lời gọi theo cách dễ quan sát; **đây không phải bằng chứng `Objects` tự đồng bộ việc tạo fallback**. Không có lời gọi đa luồng trong ví dụ.

Nếu chỉ truyền hằng số hoặc một biến fallback có sẵn, `requireNonNullElse()` vẫn đúng và dễ đọc. Chọn `requireNonNullElseGet()` chủ yếu vì chi phí hoặc tác dụng phụ của phép tính dự phòng, không phải vì nó mặc nhiên “hiện đại hơn”.

## 5. Kiểm tra `null`: cả hai API đều yêu cầu kết quả cuối không null

Hai phương thức có từ `requireNonNull` trong tên vì **giá trị sau lựa chọn phải khác `null`**. Những kết quả dễ nhầm:

```java
Objects.requireNonNullElse("ready", null); // Trả "ready".
Objects.requireNonNullElse(null, null);    // Ném NullPointerException.
```

Tương tự:

```java
Objects.requireNonNullElseGet("ready", null); // Trả "ready".
Objects.requireNonNullElseGet(null, null);    // Ném NullPointerException.
Objects.requireNonNullElseGet(null, () -> null); // Ném NullPointerException.
```

Các dòng trên là **những biểu thức minh họa độc lập**; một số lời gọi chỉ có literal `null` cần gán kiểu tường minh trong chương trình thực tế để tránh lỗi suy luận kiểu hoặc overload. Phần dưới dùng cast rõ ràng và bắt ngoại lệ.

### 5.1. Chương trình thử các trường hợp null

Tạo file **`NullFallbackDemo.java`**:

```java
import java.util.Objects;
import java.util.function.Supplier;

public class NullFallbackDemo {
    private static void run(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": OK");
        } catch (NullPointerException ex) {
            System.out.println(label + ": NPE");
        }
    }

    public static void main(String[] args) {
        System.out.println("unused null value: "
                + Objects.requireNonNullElse(
                        "ready", (String) null));
        System.out.println("unused null supplier: "
                + Objects.requireNonNullElseGet(
                        "ready", (Supplier<String>) null));

        run("needed null value", () -> {
            Objects.requireNonNullElse(
                    (String) null, (String) null);
        });
        run("needed null supplier", () -> {
            Objects.requireNonNullElseGet(
                    (String) null, (Supplier<String>) null);
        });
        run("supplier returned null", () -> {
            Objects.requireNonNullElseGet(
                    (String) null, () -> null);
        });
    }
}
```

Chạy:

```bash
javac NullFallbackDemo.java
java NullFallbackDemo
```

Stdout:

```text
unused null value: ready
unused null supplier: ready
needed null value: NPE
needed null supplier: NPE
supplier returned null: NPE
```

**Phân tích:** khi `"ready"` tồn tại, không cần fallback, nên cả `null` fallback lẫn `null` supplier không gây lỗi. Khi tham số chính không có, cả hai API không chấp nhận trả `null`; supplier cũng phải hiện diện và tạo ra kết quả không null.

Trên JDK hiện đại, `NullPointerException` có thể kèm thông báo chi tiết, nhưng không nên viết logic dựa trên nội dung message hoặc giả định thông điệp lỗi giống nhau ở mọi runtime. Kiểu ngoại lệ quan trọng hơn message.

**Khác với toán tử `?:` hoặc `if`:** hai API vừa chọn fallback vừa **khẳng định non-null**. Nếu ứng dụng muốn kết quả có thể tiếp tục null, hãy dùng nhánh điều kiện hoặc API có hợp đồng chấp nhận null, thay vì cố tình trả null qua `requireNonNullElseGet()`.

## 6. Khi fallback có ngoại lệ hoặc tác dụng phụ

Giả sử `loadDefaultFromNetwork()` gọi mạng, đọc file cấu hình hoặc lấy dữ liệu trong cache. Khi đó hành vi chọn phương thức ảnh hưởng trực tiếp đến chi phí và tính đúng đắn:

| Tình huống | `requireNonNullElse(value, load())` | `requireNonNullElseGet(value, () -> load())` |
| --- | --- | --- |
| `value` khác null, `load()` tốn thời gian | **Vẫn chạy** trước lời gọi | **Không chạy** phần thân supplier |
| `value` khác null, `load()` ném runtime exception | Lời gọi thất bại trước khi vào `Objects` | Không phát sinh ngoại lệ từ `load()` |
| `value` bằng null, `load()` trả hợp lệ | Dùng kết quả đã tính | Gọi `get()` rồi dùng kết quả |
| `value` bằng null, `load()` ném exception | Ngoại lệ từ `load()` lan ra | Ngoại lệ từ `get()` lan ra |
| `value` bằng null, `load()` trả null | `Objects` ném `NullPointerException` | `Objects` ném `NullPointerException` sau `get()` |
| `value` bằng null trong nhiều lời gọi | Mỗi biểu thức đối số có thể được tính lại | Mỗi lần gọi có thể gọi lại `get()` |

`Supplier.get()` không tự xử lý retry, không nuốt exception và không áp đặt chính sách timeout. Nếu fallback là I/O, nên quyết định rõ hành vi khi dịch vụ không sẵn sàng. `Supplier.get()` cũng không khai báo checked exception, nên thao tác có checked exception cần được bắt, đóng gói hoặc thiết kế API khác một cách minh bạch.

Lưu ý tinh tế: biểu thức **tạo supplier** vẫn được đánh giá dù giá trị chính không null:

```java
Supplier<String> supplier = createSupplier();
String result = Objects.requireNonNullElseGet(value, supplier);
```

Nếu `createSupplier()` tốn chi phí hoặc có tác dụng phụ, nó đã chạy **trước** `requireNonNullElseGet()`. Kỹ thuật lazy ở đây chỉ trì hoãn **lời gọi `get()`**, không có phép màu trì hoãn mọi biểu thức dùng làm đối số.

## 7. `requireNonNullElseGet()` không tự cache và không tự thread-safe

Ví dụ:

```java
String first = Objects.requireNonNullElseGet(
        null, () -> new String("fallback"));
String second = Objects.requireNonNullElseGet(
        null, () -> new String("fallback"));
```

Mỗi lời gọi có thể tạo đối tượng mới vì supplier được gọi ở **mỗi lời gọi cần fallback**. Hai kết quả có thể bằng nhau theo `equals()` nhưng không phải cùng tham chiếu. Đoạn này chỉ minh họa hành vi API, không phải kỹ thuật tạo `String` nên dùng: thông thường có thể trả literal `"fallback"`.

Nếu nhiều luồng gọi trên dữ liệu null:

- Mỗi luồng có thể gọi supplier của nó; `Objects` **không bảo đảm chỉ một lần khởi tạo trên toàn ứng dụng**.
- Mọi shared state mà supplier đọc/ghi cần cơ chế đồng bộ phù hợp. Bản thân lambda hoặc method reference không làm thao tác bên trong thread-safe.
- Nếu dữ liệu tạo mặc định phải được chia sẻ hoặc cache một lần, cần thiết kế thành phần cache/khởi tạo riêng (`synchronized`, cơ chế lazy holder, hoặc cấu trúc phù hợp), rồi supplier lấy dữ liệu từ thành phần đó.
- Không được kỳ vọng lời gọi `Objects.requireNonNullElseGet()` giải quyết race giữa một giá trị đang thay đổi và việc truy cập nó: tại thời điểm gọi, Java chỉ nhận **giá trị của biểu thức đối số**. Đồng bộ trạng thái nguồn vẫn là trách nhiệm của ứng dụng.

Khi lambda bắt biến cục bộ bên ngoài, những biến đó phải `final` hoặc **effectively final** theo quy tắc Java. Với trường đối tượng có thể thay đổi, cần tiếp tục xem xét thread safety và thời điểm quan sát trạng thái.

## 8. Quan hệ với `Objects.requireNonNull()` và `Optional`

Ba phương thức của `Objects` phục vụ ý định khác nhau:

| API | Ý định |
| --- | --- |
| `Objects.requireNonNull(value)` | **Bắt buộc chính `value` tồn tại**, nếu null thì ném `NullPointerException` |
| `Objects.requireNonNullElse(value, fallback)` | Cho phép giá trị chính null, dùng fallback **đã được đánh giá**, kết quả cuối khác null |
| `Objects.requireNonNullElseGet(value, supplier)` | Cho phép giá trị chính null, tạo fallback **khi cần**, kết quả cuối khác null |

`Optional.ofNullable(value).orElse(fallback)` và `.orElseGet(supplier)` có nét tương đồng về **eager/lazy**, nhưng không hoàn toàn thay thế:

- `Optional.orElse(...)` trả giá trị đã truyền và `Optional.orElseGet(...)` trả kết quả supplier khi optional rỗng; chúng **có thể trả null** nếu fallback là null.
- Hai phương thức `Objects.requireNonNullElse*()` **không cho phép kết quả cuối là null**.
- `Optional` phù hợp khi API đã mô hình hóa sự có/vắng mặt bằng `Optional<T>` hoặc cần các phép biến đổi khác; `Objects` gọn hơn nếu chỉ chọn giá trị thay thế cho một tham chiếu có thể null.
- `Optional.ofNullable(value).orElseGet(supplier)` cũng không tự cache; nó chỉ gọi supplier khi giá trị rỗng.

Không dùng `Objects.requireNonNullElse(value, fallback)` để biến **chuỗi rỗng**, chuỗi chỉ có khoảng trắng, danh sách rỗng hoặc số 0 thành giá trị mặc định. Những giá trị ấy **khác `null`**, nên được giữ nguyên. Nếu nghiệp vụ muốn xử lý chuỗi trống hoặc blank, cần viết điều kiện riêng.

## 9. Generic type và ví dụ thực tế với collection

Hai phương thức đều generic theo `<T>`. `requireNonNullElseGet()` nhận `Supplier<? extends T>`, cho phép supplier tạo kiểu con của kiểu kết quả mong muốn:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

List<String> existing = null;

List<String> items = Objects.requireNonNullElseGet(
        existing, ArrayList::new);
items.add("Java");
```

Đây là **mảnh code minh họa**, không phải file Java độc lập vì các câu lệnh nằm ngoài phương thức. Khi `existing` null, method reference `ArrayList::new` tạo `ArrayList<String>` phù hợp `List<String>`. Nếu `existing` không null, nó được trả lại nguyên tham chiếu.

Tuy nhiên, việc trả một `ArrayList` mutable không phải quyết định mặc định an toàn cho mọi API. Nếu caller không được phép sửa collection, dùng fallback bất biến như `List::of` (khi kiểu phù hợp), đồng thời tài liệu hóa rõ tính mutable/immutable của giá trị trả về. Nếu `existing` có thể là list mutable nhưng fallback immutable, API có thể có **hai chế độ mutability khác nhau** tùy null; cần cân nhắc hợp đồng thiết kế.

Ví dụ dùng một singleton fallback có sẵn:

```java
List<String> safeItems = Objects.requireNonNullElse(
        existing, List.of());
```

`List.of()` trả collection bất biến; mặc dù biểu thức đối số vẫn được đánh giá trước lời gọi, Java có thể dùng instance chia sẻ cho danh sách rỗng. Tính eager/lazy nói về **thời điểm đánh giá biểu thức**, không khẳng định nhất thiết có cấp phát bộ nhớ mỗi lần gọi.

## 10. Những lỗi thường gặp

1. **Dùng `requireNonNullElse(value, expensive())` rồi tưởng `expensive()` chỉ chạy khi null.** Mọi đối số của lời gọi Java được đánh giá trước; dùng supplier nếu cần trì hoãn phần tính.
2. **Tin rằng `requireNonNullElseGet()` tự đảm bảo phép tính mặc định chỉ chạy một lần.** Nó có thể gọi `get()` ở từng lần gọi, kể cả song song giữa các luồng.
3. **Cho supplier trả `null` vì tưởng API giữ nguyên null.** Khi fallback cần dùng, kết quả null bị từ chối bằng `NullPointerException`.
4. **Cho rằng supplier null luôn gây lỗi ngay.** Nếu giá trị chính không null, supplier không được sử dụng và có thể là null mà vẫn trả chính giá trị ấy.
5. **Bỏ qua tác dụng phụ của việc tạo supplier.** Thân `get()` được trì hoãn; biểu thức tạo supplier vẫn đánh giá theo quy tắc Java.
6. **Giả định lambda đồng nghĩa thread-safe.** Nội dung supplier có thể đọc/ghi trạng thái chia sẻ và vẫn cần đồng bộ.
7. **Dùng để chuẩn hóa chuỗi rỗng hoặc collection rỗng.** Hai API chỉ kiểm tra `null`, không kiểm tra trạng thái rỗng.
8. **Dùng fallback mutable mà không nói rõ.** Kết quả có thể là chính đối tượng cũ hoặc một đối tượng mutable mới; API không sao chép và không tự bảo vệ dữ liệu.
9. **Che giấu lỗi nghiệp vụ bằng default vô điều kiện.** Nếu dữ liệu bắt buộc phải có, `Objects.requireNonNull(value)` có thể đúng hơn việc âm thầm dùng fallback.
10. **Đổi từ eager sang lazy mà quên thay đổi hành vi ngoại lệ.** Nếu fallback trước đây luôn chạy và ném lỗi ngay cả khi không dùng, `requireNonNullElseGet()` sẽ bỏ qua lỗi đó khi `obj` khác null; đây là thay đổi hành vi cần chủ động đánh giá.

## 11. Checklist lựa chọn nhanh

- [ ] Có chấp nhận `value == null` không? Nếu không, dùng `requireNonNull(value)`.
- [ ] Nếu chấp nhận, fallback có được đảm bảo **khác `null`** không? Nếu không, hai `requireNonNullElse*()` không phù hợp.
- [ ] Fallback đã tồn tại hoặc tính rất rẻ? Ưu tiên `requireNonNullElse(value, fallback)`.
- [ ] Fallback tốn I/O, tính toán, cấp phát hoặc có tác dụng phụ? Ưu tiên `requireNonNullElseGet(value, () -> computeFallback())`.
- [ ] Supplier có thể ném exception, dùng shared state hoặc trả mutable object? Xác định chính sách và bảo đảm đồng bộ nếu cần.
- [ ] Có cần kết quả được cache/dùng chung hay không? Thiết kế cơ chế riêng, vì `Objects` không cache.
- [ ] Có kiểm thử các trường hợp `value != null`, `value == null`, fallback null, supplier null và supplier trả null?
- [ ] Có đang nhầm `null` với chuỗi rỗng/danh sách rỗng hoặc đang muốn một phép chuẩn hóa khác không?

**Ghi nhớ:** `Objects.requireNonNullElse(value, fallback)` dùng một **giá trị dự phòng đã được đánh giá**; `Objects.requireNonNullElseGet(value, supplier)` chỉ **gọi supplier khi `value == null`**. Cả hai bảo đảm **kết quả trả về không null** hoặc ném `NullPointerException` khi không thể tạo kết quả hợp lệ. Chọn phương thức dựa vào chi phí, tác dụng phụ và hợp đồng của fallback.
