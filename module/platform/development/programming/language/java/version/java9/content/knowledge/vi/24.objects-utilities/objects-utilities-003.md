# Quy tắc null đối với giá trị mặc định và Supplier

## 1. Bài toán chọn giá trị thay thế

Trong Java, một tham chiếu có thể mang giá trị `null`. Khi chương trình cần một giá trị dự phòng, cần xác định rõ hai điều: giá trị đầu vào có được ưu tiên hay không, và giá trị dự phòng có bắt buộc khác null hay không.

Từ Java 9, lớp `java.util.Objects` cung cấp hai phương thức liên quan:

- `Objects.requireNonNullElse(obj, defaultObj)`: nhận một giá trị mặc định đã có sẵn.
- `Objects.requireNonNullElseGet(obj, supplier)`: nhận một `Supplier` để tạo giá trị mặc định khi cần.

Cả hai đều trả về giá trị khác null nếu hoàn tất bình thường. Nếu giá trị đầu vào null và giá trị thay thế cũng không cung cấp được một giá trị khác null, phương thức ném `NullPointerException`.

## 2. Quy tắc của requireNonNullElse

Chữ ký phương thức:

```java
public static <T> T requireNonNullElse(T obj, T defaultObj)
```

Quy tắc:

1. Nếu `obj` khác null, trả về chính `obj`.
2. Nếu `obj` là null và `defaultObj` khác null, trả về `defaultObj`.
3. Nếu cả hai đều null, ném `NullPointerException`.

Giá trị mặc định có thể là hằng số, biến đã tính sẵn hoặc kết quả của một lời gọi phương thức.

```java
String configuredName = "Ada";
String displayName =
        Objects.requireNonNullElse(configuredName, "Guest");

String missingName = null;
String fallbackName =
        Objects.requireNonNullElse(missingName, "Guest");
```

Kết quả tương ứng là `"Ada"` và `"Guest"`. Trong trường hợp đầu, giá trị mặc định không được chọn. Trong trường hợp thứ hai, nó được trả về vì giá trị chính là null.

Một điểm quan trọng: Java đánh giá tất cả biểu thức đối số trước khi gọi phương thức. Vì vậy, nếu viết:

```java
String name = Objects.requireNonNullElse(
        configuredName, loadDefaultName());
```

thì `loadDefaultName()` vẫn chạy ngay cả khi `configuredName` khác null. Đây là đánh giá eager (đánh giá trước). Nếu việc tạo mặc định tốn tài nguyên hoặc có tác dụng phụ, chương trình có thể thực hiện công việc không cần thiết.

## 3. Quy tắc của requireNonNullElseGet

Chữ ký phương thức:

```java
public static <T> T requireNonNullElseGet(
        T obj, Supplier<? extends T> supplier)
```

`Supplier` là functional interface trong `java.util.function`. Phương thức `get()` không nhận đối số và trả về một giá trị. Lambda không tham số như `() -> loadDefaultName()` có thể được dùng làm Supplier.

Quy tắc:

1. Nếu `obj` khác null, trả về `obj` và không gọi supplier.
2. Nếu `obj` là null, gọi `supplier.get()` và trả về kết quả nếu kết quả khác null.
3. Nếu `obj` là null nhưng supplier là null, hoặc supplier trả về null, ném `NullPointerException`.

Ví dụ:

```java
String displayName = Objects.requireNonNullElseGet(
        configuredName,
        () -> loadDefaultName());
```

Nếu `configuredName` có giá trị, lambda không được thực thi. Nếu `configuredName` là null, lambda chạy để tạo giá trị thay thế. Đây là đánh giá lazy (chỉ đánh giá khi cần).

Supplier không tự bảo đảm kết quả khác null. Chính hợp đồng của `requireNonNullElseGet` yêu cầu kết quả supplier phải khác null khi supplier được gọi. Nếu supplier ném một unchecked exception, ngoại lệ đó được truyền ra cho bên gọi.

## 4. So sánh hai cách cung cấp giá trị mặc định

| Tiêu chí | `requireNonNullElse` | `requireNonNullElseGet` |
|---|---|---|
| Đối số thứ hai | Giá trị `T` | `Supplier<? extends T>` |
| Cách đánh giá | Biểu thức mặc định được đánh giá trước lời gọi | Supplier chỉ chạy khi `obj` là null |
| Khi `obj` khác null | Trả về `obj`; giá trị mặc định đã được tính | Trả về `obj`; supplier không được gọi |
| Khi `obj` là null | Dùng `defaultObj` | Gọi `supplier.get()` |
| Giá trị thay thế null | Ném `NullPointerException` nếu cả hai giá trị null | Ném `NullPointerException` nếu supplier null hoặc trả null khi cần |
| Trường hợp phù hợp | Mặc định đơn giản, rẻ và có sẵn | Mặc định cần tính toán, truy cập dữ liệu hoặc chỉ nên tạo khi cần |

Dùng `requireNonNullElse` khi giá trị dự phòng đã có sẵn và không gây chi phí đáng kể. Dùng `requireNonNullElseGet` khi muốn trì hoãn việc tạo giá trị, tránh I/O hoặc tránh tác dụng phụ không cần thiết.

Không nên tạo Supplier chỉ để bọc một hằng số đơn giản. Lambda không làm cho mã tốt hơn nếu không có lợi ích về đánh giá trì hoãn hoặc cách tổ chức logic.

## 5. Ví dụ chạy được: eager, lazy và các trường hợp null

Chương trình sau kiểm tra giá trị đầu vào, cách đánh giá mặc định và các trường hợp không thể tạo giá trị thay thế hợp lệ.

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class RequireDefaultSupplierDemo {
    private static String loadFallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return "Guest";
    }

    public static void main(String[] args) {
        String present = Objects.requireNonNullElse("Ada", "Guest");
        String missing = Objects.requireNonNullElse(null, "Guest");
        System.out.println("present = " + present);
        System.out.println("missing = " + missing);

        AtomicInteger eagerCalls = new AtomicInteger();
        String eager = Objects.requireNonNullElse(
                "ready", loadFallback(eagerCalls));
        System.out.println("eager result = " + eager);
        System.out.println("eager fallback calls = " + eagerCalls.get());

        AtomicInteger lazyCalls = new AtomicInteger();
        String lazy = Objects.requireNonNullElseGet(
                "ready", () -> loadFallback(lazyCalls));
        System.out.println("lazy result = " + lazy);
        System.out.println("lazy fallback calls = " + lazyCalls.get());

        String generated = Objects.requireNonNullElseGet(
                null, () -> loadFallback(lazyCalls));
        System.out.println("generated fallback = " + generated);
        System.out.println("lazy fallback calls after null = "
                + lazyCalls.get());

        try {
            Objects.requireNonNullElse(null, null);
        } catch (NullPointerException ex) {
            System.out.println("both values null = NullPointerException");
        }

        try {
            Objects.requireNonNullElseGet(null, () -> null);
        } catch (NullPointerException ex) {
            System.out.println(
                    "supplier returned null = NullPointerException");
        }
    }
}
```

Lưu mã nguồn trong `RequireDefaultSupplierDemo.java`, sau đó biên dịch và chạy bằng Java 17 trở lên:

```bash
javac --release 17 -Xlint:all RequireDefaultSupplierDemo.java
java RequireDefaultSupplierDemo
```

Kết quả:

```text
present = Ada
missing = Guest
eager result = ready
eager fallback calls = 1
lazy result = ready
lazy fallback calls = 0
generated fallback = Guest
lazy fallback calls after null = 1
both values null = NullPointerException
supplier returned null = NullPointerException
```

Bộ đếm cho thấy `loadFallback` được gọi một lần khi truyền trực tiếp vào `requireNonNullElse`, dù giá trị chính đã là `"ready"`. Với `requireNonNullElseGet`, supplier chưa được gọi khi giá trị chính khác null; nó chỉ được gọi khi đầu vào là null.

## 6. Supplier được gọi khi nào và bao nhiêu lần?

`requireNonNullElseGet` không lưu cache kết quả của supplier. Mỗi lần gọi phương thức với đối số đầu tiên là null, supplier được gọi trong lần gọi đó.

Ví dụ:

```java
Supplier<String> supplier = this::loadFromDatabase;

String first = Objects.requireNonNullElseGet(null, supplier);
String second = Objects.requireNonNullElseGet(null, supplier);
```

Nếu cả hai lời gọi đều đi vào nhánh dự phòng, `loadFromDatabase` chạy hai lần. Nếu cần tái sử dụng một giá trị đã tính, hãy lưu kết quả vào biến hoặc một cache có vòng đời được thiết kế rõ ràng.

Supplier cũng có thể chứa I/O hoặc logic có tác dụng phụ. Chỉ đặt các thao tác đó trong supplier khi chúng thực sự cần được trì hoãn và khi việc gọi lại chúng là an toàn theo thiết kế.

## 7. So sánh với Optional và requireNonNull

Có thể dùng `Optional` để biểu diễn giá trị có thể vắng mặt:

```java
String name = Optional.ofNullable(configuredName)
        .orElse("Guest");
```

`Optional.orElse(defaultValue)` cũng đánh giá biểu thức mặc định trước lời gọi. Nếu cần đánh giá trì hoãn, dùng `orElseGet(supplier)`.

Tuy nhiên, `Optional.orElse` có thể trả về null nếu Optional rỗng và giá trị mặc định là null. `Optional.orElseGet` cũng có thể trả về null nếu supplier trả null. Trong khi đó, `Objects.requireNonNullElse` và `requireNonNullElseGet` yêu cầu kết quả thay thế khác null khi cần dùng giá trị đó.

Nếu null là dữ liệu không hợp lệ và không có giá trị mặc định phù hợp, dùng `Objects.requireNonNull(value)` để ném ngoại lệ tại điểm kiểm tra. Phương thức này kiểm tra điều kiện bắt buộc khác null, không tạo giá trị thay thế.

## 8. Lỗi thường gặp và cách tránh

- **Truyền hai giá trị null:** `requireNonNullElse(null, null)` không thể chọn giá trị hợp lệ và ném `NullPointerException`.
- **Supplier trả null:** khi giá trị đầu vào null, supplier phải trả về một giá trị khác null.
- **Nhầm eager với lazy:** truyền `loadDefault()` trực tiếp vào `requireNonNullElse` không trì hoãn lời gọi; cần lambda hoặc method reference với `requireNonNullElseGet`.
- **Tạo Supplier không cần thiết:** nếu giá trị mặc định là hằng số hoặc đã có sẵn, dùng phương thức nhận giá trị trực tiếp.
- **Cho rằng Supplier được cache:** supplier có thể được gọi lại ở mỗi lần cần fallback; API không ghi nhớ kết quả.
- **Che giấu lỗi cấu hình:** nếu fallback cũng không hợp lệ, đừng dùng một giá trị giả để che lỗi. Hãy để ngoại lệ hoặc xác thực dữ liệu theo hợp đồng của ứng dụng.

## 9. Checklist lựa chọn API

1. Giá trị chính có thể null không?
2. Nếu giá trị chính null, có một fallback chắc chắn khác null không?
3. Fallback đã có sẵn hay phải tính toán?
4. Việc tạo fallback có tốn chi phí hoặc có tác dụng phụ không?
5. Nếu fallback cần trì hoãn, supplier có trả về giá trị khác null không?
6. Supplier có an toàn khi được gọi nhiều lần không?
7. Nếu không có fallback hợp lệ, ứng dụng có nên ném ngoại lệ ngay tại điểm kiểm tra không?

`Objects.requireNonNullElse` và `Objects.requireNonNullElseGet` đều là API Java 9 để chọn giá trị thay thế khác null. Khác biệt cốt lõi nằm ở cách cung cấp fallback: một bên nhận giá trị đã được đánh giá, bên kia nhận Supplier để chỉ tạo giá trị khi đầu vào thực sự null.