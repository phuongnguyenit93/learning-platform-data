# Tạo giá trị thay thế trì hoãn bằng `Objects.requireNonNullElseGet()`

`Objects.requireNonNullElseGet()` cung cấp một giá trị mặc định khi một tham chiếu đang là `null`. Điểm quan trọng của phương thức là giá trị thay thế được tạo thông qua `Supplier`, vì vậy supplier chỉ được gọi khi đối số chính thực sự là `null`. Nếu đối số chính đã có giá trị, chương trình nhận lại chính giá trị đó và không cần tính toán fallback.

Phương thức này được bổ sung trong Java 9 và vẫn là API hiện hành. Nó hữu ích khi tạo giá trị thay thế tốn công, cần đọc cấu hình, gọi một factory hoặc có tác dụng phụ mà chỉ nên xảy ra khi thiếu dữ liệu. Nếu fallback đơn giản và đã có sẵn, `Objects.requireNonNullElse()` có thể dễ đọc hơn.

## 1. Chữ ký và luồng xử lý

Chữ ký tổng quát:

```java
public static <T> T requireNonNullElseGet(
        T obj,
        Supplier<? extends T> supplier
);
```

- `obj`: giá trị đầu vào cần kiểm tra.
- `supplier`: đối tượng cung cấp giá trị thay thế nếu `obj` là `null`.
- Kết quả: `obj` nếu nó khác `null`; nếu không, kết quả do `supplier.get()` tạo ra.

Luồng xử lý có thể hiểu như sau:

```text
obj khác null?
  ├─ Có  -> trả về obj; không gọi supplier
  └─ Không -> gọi supplier.get()
                ├─ kết quả khác null -> trả về kết quả
                └─ kết quả null      -> ném NullPointerException
```

Việc đánh giá fallback được trì hoãn cho đến khi cần. Đây là điểm làm nên ý nghĩa của chữ `Get` trong tên phương thức: phương thức nhận một nhà cung cấp để lấy giá trị sau, thay vì nhận sẵn giá trị thay thế đã được tính trước.

## 2. Ví dụ cơ bản

```java
import java.util.Objects;

String configuredName = null;
String name = Objects.requireNonNullElseGet(
        configuredName,
        () -> "Guest"
);

System.out.println(name);
```

Vì `configuredName` là `null`, supplier được gọi và tạo ra chuỗi `Guest`. Kết quả:

```text
Guest
```

Nếu `configuredName` là `Linh`, phương thức trả về `Linh` và supplier không được gọi.

## 3. Chứng minh supplier chỉ chạy khi cần

Để thấy rõ tính trì hoãn, có thể đếm số lần supplier được gọi:

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class RequireNonNullElseGetDemo {
    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        Supplier<String> fallback = () -> {
            calls.incrementAndGet();
            return "generated";
        };

        String existing = Objects.requireNonNullElseGet("provided", fallback);
        System.out.println("Existing: " + existing);
        System.out.println("Supplier calls: " + calls.get());

        String generated = Objects.requireNonNullElseGet(null, fallback);
        System.out.println("Fallback: " + generated);
        System.out.println("Supplier calls: " + calls.get());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 RequireNonNullElseGetDemo.java
java RequireNonNullElseGetDemo
```

Kết quả stdout:

```text
Existing: provided
Supplier calls: 0
Fallback: generated
Supplier calls: 1
```

Lần gọi đầu tiên có `obj` là `provided`, do đó supplier không chạy và bộ đếm vẫn bằng `0`. Lần gọi thứ hai truyền `null`, nên supplier chạy đúng một lần và trả về `generated`.

## 4. Vì sao dùng Supplier thay cho giá trị mặc định trực tiếp?

`Objects.requireNonNullElse()` nhận một giá trị mặc định đã được tính sẵn:

```java
String name = Objects.requireNonNullElse(
        configuredName,
        createDefaultName()
);
```

Java đánh giá các đối số của lời gọi phương thức trước khi gọi phương thức. Vì vậy, `createDefaultName()` vẫn chạy ngay cả khi `configuredName` khác `null`. Đây là eager evaluation (đánh giá sớm).

Ngược lại, `requireNonNullElseGet()` nhận một lambda hoặc method reference:

```java
String name = Objects.requireNonNullElseGet(
        configuredName,
        this::createDefaultName
);
```

Method reference chỉ mô tả hành động tạo fallback. Phương thức `createDefaultName()` chỉ được gọi khi `configuredName` là `null`. Đây là lazy evaluation (đánh giá trì hoãn).

Chọn `requireNonNullElseGet()` khi việc tạo fallback tốn tài nguyên, cần đọc dữ liệu bên ngoài, hoặc chỉ nên thực hiện trong trường hợp thiếu giá trị. Nếu giá trị mặc định là hằng số hoặc biểu thức rất rẻ, `requireNonNullElse()` thường đơn giản và dễ đọc hơn.

## 5. Điều kiện null và exception

Phương thức đảm bảo kết quả trả về không phải `null`. Vì vậy:

- Nếu `obj` khác `null`, phương thức trả về `obj`; supplier không được gọi.
- Nếu `obj` là `null` nhưng `supplier` là `null`, phương thức ném `NullPointerException`.
- Nếu `obj` là `null` và `supplier.get()` trả về `null`, phương thức ném `NullPointerException`.
- Nếu `supplier.get()` ném một unchecked exception, exception đó truyền ra bên gọi; phương thức không tự chuyển nó thành giá trị mặc định khác.

Ví dụ fallback trả về `null` là không hợp lệ:

```java
String value = Objects.requireNonNullElseGet(
        null,
        () -> null
); // ném NullPointerException
```

Nếu đối số đầu vào đã khác `null`, supplier không cần được dereference. Dù vậy, trong mã ứng dụng hãy truyền supplier hợp lệ thay vì cố ý truyền `null`; điều đó giữ cho lời gọi rõ ràng và tránh lỗi khi trạng thái đầu vào thay đổi.

Supplier được gọi đồng bộ ngay trong thread gọi `requireNonNullElseGet()`. Phương thức không tự tạo thread, không chạy bất đồng bộ và không lưu cache kết quả. Nếu nhiều lần gọi với `obj == null`, supplier sẽ được gọi một lần cho mỗi lời gọi; nếu cần cache, hãy quản lý cache ở thành phần có trách nhiệm rõ ràng.

## 6. So sánh với `requireNonNullElse()` và Optional

| API | Giá trị thay thế | Khi nào tính fallback? |
| --- | --- | --- |
| `Objects.requireNonNullElse(obj, defaultObj)` | Một giá trị có sẵn | Biểu thức tạo `defaultObj` được đánh giá trước lời gọi |
| `Objects.requireNonNullElseGet(obj, supplier)` | Một `Supplier` | Chỉ gọi supplier khi `obj` là `null` |
| `optional.orElse(other)` | Một giá trị có sẵn | Biểu thức tạo `other` được đánh giá trước lời gọi |
| `optional.orElseGet(supplier)` | Một `Supplier` | Chỉ gọi supplier khi Optional rỗng |

`Objects.requireNonNullElseGet()` làm việc trực tiếp với tham chiếu có thể null. `Optional.orElseGet()` làm việc với một `Optional<T>` đã tồn tại và dùng supplier khi Optional rỗng. Hai API có ý tưởng lazy fallback tương tự nhưng đầu vào và hợp đồng khác nhau.

Ví dụ với Optional:

```java
Optional<String> optionalName = Optional.empty();
String name = optionalName.orElseGet(() -> "Guest");
```

Nếu dữ liệu vốn được mô hình hóa bằng `Optional`, hãy tiếp tục dùng API của Optional. Nếu đang nhận một tham chiếu có thể null và chỉ muốn chọn giá trị thay thế không null, `Objects.requireNonNullElseGet()` là lựa chọn trực tiếp.

## 7. Khi nào nên dùng?

**Phù hợp khi:**

- Giá trị đầu vào có thể `null` và fallback chỉ cần tạo khi đầu vào thiếu.
- Fallback tốn chi phí, chẳng hạn dựng object, đọc file cấu hình hoặc gọi một factory.
- Muốn dùng method reference để tách logic tạo giá trị mặc định thành một phương thức có tên.
- Hợp đồng của chương trình yêu cầu giá trị kết quả luôn khác `null`.

**Không nên dùng khi:**

- Giá trị đầu vào không thể `null` theo hợp đồng; khi đó không cần fallback.
- Supplier có thể trả về `null`; phương thức sẽ ném `NullPointerException`, nên cần sửa logic tạo giá trị.
- Muốn biểu diễn trạng thái vắng mặt như một phần của API; cân nhắc `Optional<T>` thay vì dùng `null` xuyên suốt.
- Cần xử lý nhiều nhánh nghiệp vụ hoặc cần kết quả có thể vắng mặt; một câu lệnh `if` hoặc chuỗi xử lý Optional có thể phù hợp hơn.

## 8. Lỗi thường gặp

- **Nhầm `ElseGet` với `Else`:** truyền `createDefault()` vào `requireNonNullElseGet` sẽ sai kiểu vì tham số thứ hai cần `Supplier`, không phải giá trị `T`. Dùng `() -> createDefault()` hoặc `this::createDefault`.
- **Tưởng fallback luôn chạy:** supplier chỉ được gọi khi đối số đầu tiên là `null`.
- **Supplier trả về `null`:** phương thức ném `NullPointerException`; hãy bảo đảm fallback tạo ra giá trị hợp lệ.
- **Cho rằng phương thức bắt exception:** exception từ supplier truyền ra ngoài; cần xử lý tại supplier hoặc nơi gọi.
- **Dùng supplier cho một hằng số đơn giản:** lambda không đem lại lợi ích đáng kể nếu fallback rẻ và có sẵn; `requireNonNullElse()` dễ đọc hơn.
- **Nhầm với Optional:** `requireNonNullElseGet()` nhận tham chiếu có thể null, còn `Optional.orElseGet()` nhận một Optional.

`Objects.requireNonNullElseGet()` là cách tạo fallback không null theo nhu cầu. Hãy dùng nó khi đầu vào có thể null và chi phí tạo giá trị thay thế chỉ nên phát sinh trong nhánh đó; chọn `requireNonNullElse()` khi đã có sẵn giá trị mặc định và việc đánh giá sớm là phù hợp.