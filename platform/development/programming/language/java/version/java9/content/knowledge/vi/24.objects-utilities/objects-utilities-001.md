# Giá trị thay thế không null bằng Objects.requireNonNullElse

## 1. Mục đích của requireNonNullElse

Java 9 bổ sung phương thức tĩnh tổng quát `Objects.requireNonNullElse(obj, defaultObj)` trong lớp `java.util.Objects`. Phương thức này chọn một giá trị thay thế khi giá trị đầu vào là `null`, đồng thời bảo đảm kết quả trả về không phải `null`.

Quy tắc hoạt động:

- Nếu `obj` khác `null`, trả về chính `obj`.
- Nếu `obj` là `null`, trả về `defaultObj` nếu giá trị thay thế khác `null`.
- Nếu cả `obj` và `defaultObj` đều là `null`, ném `NullPointerException`.

Phương thức có dạng:

```java
public static <T> T requireNonNullElse(T obj, T defaultObj)
```

Hai tham số có cùng kiểu tổng quát `T`; kết quả có kiểu `T`. Phương thức phù hợp khi chương trình cần chọn giá trị dự phòng nhưng vẫn muốn bảo đảm kết quả cuối cùng không null.

## 2. Ví dụ cơ bản

Giả sử ứng dụng nhận tên hiển thị từ cấu hình. Nếu cấu hình không cung cấp tên, ứng dụng dùng chuỗi mặc định:

```java
import java.util.Objects;

public class RequireNonNullElseDemo {
    public static void main(String[] args) {
        String configuredName = "Ada";
        String displayName = Objects.requireNonNullElse(
                configuredName, "Guest");

        String missingName = null;
        String fallbackName = Objects.requireNonNullElse(
                missingName, "Guest");

        System.out.println(displayName);
        System.out.println(fallbackName);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac --release 17 -Xlint:all RequireNonNullElseDemo.java
java RequireNonNullElseDemo
```

Kết quả:

```text
Ada
Guest
```

Trong trường hợp đầu, phương thức trả về giá trị `"Ada"`. Trong trường hợp thứ hai, đầu vào là `null`, nên phương thức trả về `"Guest"`.

## 3. Quy tắc null chính xác

Điểm quan trọng là `defaultObj` chỉ bắt buộc khác null khi `obj` cũng null. Nếu `obj` đã có giá trị, phương thức trả về giá trị đó mà không cần dùng giá trị dự phòng.

```java
String name = Objects.requireNonNullElse("Ada", null);
System.out.println(name);
```

Kết quả:

```text
Ada
```

Ngược lại, nếu cả hai đối số là null, không có giá trị hợp lệ để trả về:

```java
Objects.requireNonNullElse(null, null);
```

Lời gọi này ném `NullPointerException`. Nếu cần kiểm tra hoặc báo lỗi khi dữ liệu bắt buộc bị thiếu, có thể dùng `Objects.requireNonNull(value)`; nếu cần một giá trị thay thế không null, dùng `requireNonNullElse`.

Không nên nhầm phương thức này với toán tử null-coalescing ở các ngôn ngữ khác. Java không có toán tử `??`; `requireNonNullElse` là một lời gọi phương thức có quy tắc kiểu và ngoại lệ rõ ràng.

## 4. Đối số mặc định được đánh giá trước khi gọi phương thức

Java đánh giá các biểu thức đối số trước khi bắt đầu thực thi phương thức. Vì vậy, biểu thức truyền vào vị trí `defaultObj` luôn được đánh giá, kể cả khi `obj` khác null và giá trị dự phòng không được trả về.

Ví dụ:

```java
String result = Objects.requireNonNullElse(
        "ready", loadDefaultValue());
```

`loadDefaultValue()` vẫn được gọi trước khi `requireNonNullElse` chạy. Điều này có thể gây công việc thừa nếu việc tạo giá trị dự phòng tốn thời gian, đọc dữ liệu hoặc có tác dụng phụ.

Nếu cần tạo giá trị dự phòng một cách trì hoãn, dùng `Objects.requireNonNullElseGet`:

```java
String result = Objects.requireNonNullElseGet(
        "ready", () -> loadDefaultValue());
```

Supplier chỉ được gọi khi giá trị đầu tiên là null. Khi giá trị đầu tiên đã có, phần thân lambda không chạy.

## 5. So sánh requireNonNullElse và requireNonNullElseGet

Cả hai phương thức đều được bổ sung từ Java 9 và đều hướng đến kết quả không null:

| Tiêu chí | `requireNonNullElse` | `requireNonNullElseGet` |
|---|---|---|
| Đối số thay thế | Một giá trị `T` | Một `Supplier<? extends T>` |
| Thời điểm tạo giá trị dự phòng | Biểu thức đối số được đánh giá trước lời gọi | Supplier chỉ được gọi khi đầu vào null |
| Phù hợp khi | Giá trị dự phòng đơn giản, có sẵn | Giá trị dự phòng tốn công tạo hoặc có tác dụng phụ |
| Nếu đầu vào null và giá trị dự phòng null | Ném `NullPointerException` | Ném `NullPointerException` nếu supplier null hoặc supplier trả null |

Ví dụ về supplier:

```java
String displayName = Objects.requireNonNullElseGet(
        configuredName,
        () -> loadNameFromProfile());
```

Nếu `configuredName` khác null, `loadNameFromProfile()` không được gọi. Nếu `configuredName` là null, supplier được gọi và kết quả của nó phải khác null.

Không cần dùng supplier nếu giá trị mặc định là hằng số hoặc đã được tính sẵn. Dùng `requireNonNullElse` trong trường hợp đó giúp mã ngắn và dễ đọc hơn.

## 6. Chương trình kiểm tra eager và lazy evaluation

Chương trình dưới đây đếm số lần phương thức tạo giá trị dự phòng được gọi. Nó cho thấy `requireNonNullElse` đánh giá biểu thức mặc định ngay cả khi giá trị đầu vào có sẵn, còn `requireNonNullElseGet` chỉ gọi supplier khi cần.

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class RequireNonNullElseDemo {
    private static String fallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return "Guest";
    }

    public static void main(String[] args) {
        String configured = "Ada";
        System.out.println("configured = "
                + Objects.requireNonNullElse(configured, "Guest"));

        String missing = null;
        System.out.println("missing = "
                + Objects.requireNonNullElse(missing, "Guest"));

        System.out.println("non-null with null fallback = "
                + Objects.requireNonNullElse("Ada", null));

        AtomicInteger calls = new AtomicInteger();
        Objects.requireNonNullElse("ready", fallback(calls));
        System.out.println("eager fallback calls = " + calls.get());

        calls.set(0);
        Objects.requireNonNullElseGet("ready", () -> fallback(calls));
        System.out.println("lazy fallback calls = " + calls.get());

        try {
            Objects.requireNonNullElse(null, null);
        } catch (NullPointerException ex) {
            System.out.println(
                    "null primary and fallback = NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -Xlint:all RequireNonNullElseDemo.java
java RequireNonNullElseDemo
```

Kết quả:

```text
configured = Ada
missing = Guest
non-null with null fallback = Ada
eager fallback calls = 1
lazy fallback calls = 0
null primary and fallback = NullPointerException
```

Kết quả `eager fallback calls = 1` xuất hiện vì `fallback(calls)` là biểu thức đối số và được đánh giá trước khi phương thức được gọi. Với supplier, `get()` không được gọi khi giá trị chính đã khác null, nên bộ đếm vẫn bằng 0.

## 7. So sánh với Optional và toán tử điều kiện

Có thể viết logic dự phòng bằng `Optional`:

```java
String displayName = Optional.ofNullable(configuredName)
        .orElse("Guest");
```

`Optional.orElse(defaultValue)` cũng đánh giá biểu thức mặc định trước khi lời gọi hoàn tất. Nếu cần trì hoãn, dùng `orElseGet(supplier)`.

Một khác biệt quan trọng là `Optional.orElse(null)` có thể trả về null khi Optional rỗng. `Objects.requireNonNullElse` bảo đảm kết quả khác null khi nó trả về bình thường; nếu giá trị chính null thì giá trị dự phòng cũng phải khác null.

Với giá trị dự phòng đơn giản, toán tử điều kiện cũng là cách rõ ràng:

```java
String displayName = configuredName != null
        ? configuredName
        : "Guest";
```

Toán tử điều kiện chỉ đánh giá nhánh được chọn, nên biểu thức mặc định trong nhánh sau chỉ chạy khi giá trị chính null. Chọn cách viết phù hợp với ý định: `requireNonNullElse` thể hiện rõ hợp đồng kết quả không null; toán tử điều kiện phù hợp khi cần logic chọn giá trị tùy chỉnh.

## 8. Những lỗi thường gặp

- Truyền `null` cho cả hai đối số và không xử lý `NullPointerException`.
- Cho rằng biểu thức mặc định chỉ chạy khi đầu vào null; điều đó không đúng với `requireNonNullElse`.
- Dùng `requireNonNullElse` khi giá trị dự phòng đắt để tạo hoặc có tác dụng phụ, dẫn đến công việc không cần thiết.
- Dùng `requireNonNullElseGet` nhưng supplier trả về null khi giá trị chính null.
- Dùng phương thức này như cách thay thế cho xác thực dữ liệu phức tạp; nó chỉ chọn một trong hai giá trị theo quy tắc null.
- Nhầm lẫn với `Objects.requireNonNull`, vốn ném ngoại lệ ngay khi đối số được kiểm tra là null và không nhận giá trị dự phòng.

## 9. Checklist khi sử dụng

1. Giá trị đầu vào có thể null không?
2. Giá trị dự phòng có chắc chắn khác null khi đầu vào null không?
3. Việc tính giá trị dự phòng có tốn công hoặc gây tác dụng phụ không?
4. Nếu cần đánh giá trì hoãn, đã dùng `requireNonNullElseGet` với supplier phù hợp chưa?
5. Có cần xử lý `NullPointerException` khi cả hai giá trị đều null không?
6. Hợp đồng API có thực sự yêu cầu một kết quả không null hay chỉ muốn giữ null như một trạng thái hợp lệ?

`Objects.requireNonNullElse` là tiện ích Java 9 để chọn giá trị thay thế và bảo đảm kết quả không null. Dùng nó khi giá trị mặc định đã có sẵn; nếu việc tạo mặc định cần trì hoãn, dùng `requireNonNullElseGet`.