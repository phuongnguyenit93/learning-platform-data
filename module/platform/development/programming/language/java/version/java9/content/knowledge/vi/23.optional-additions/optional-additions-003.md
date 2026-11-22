# Thời điểm gọi Supplier và giới hạn trả về null trong Optional

Các phương thức nhận `Supplier` cho phép trì hoãn việc tính giá trị thay thế hoặc kết quả dự phòng cho đến khi thật sự cần. Tuy nhiên, mỗi API có hợp đồng riêng về thời điểm gọi `get()`, giá trị được phép trả về và cách xử lý `null`.

Điểm cần phân biệt trong Java hiện đại:

- `Optional.orElseGet()` chỉ gọi Supplier khi Optional rỗng; Supplier có thể trả về `null`, dù thường không nên làm vậy.
- `Optional.or()` (Java 9) chỉ lấy Optional thay thế khi Optional hiện tại rỗng; Supplier phải trả về một Optional khác null.
- `Optional.orElseThrow()` chỉ gọi Supplier khi Optional rỗng; Supplier phải tạo ra một exception khác null.
- `Objects.requireNonNullElseGet()` (Java 9) chỉ gọi Supplier khi giá trị đầu vào null; kết quả Supplier cũng phải khác null.

Các quy tắc này ảnh hưởng trực tiếp đến side effect, hiệu năng, ngoại lệ và tính đúng đắn của mã gọi.

## 1. Supplier là gì và điều gì được trì hoãn?

`Supplier<T>` là functional interface có phương thức `T get()`. Nó mô tả một thao tác cung cấp giá trị khi được gọi, không nhất thiết tính giá trị ngay khi tạo lambda hoặc method reference.

Ví dụ:

```java
Supplier<String> supplier = () -> {
    System.out.println("Computing fallback");
    return "fallback";
};
```

Khi tạo biến `supplier`, thân lambda chưa chạy. Dòng `Computing fallback` chỉ được in khi gọi `supplier.get()`.

Cần phân biệt hai thời điểm:

1. **Tạo hoặc truyền Supplier:** biểu thức tạo đối tượng Supplier được đánh giá khi lời gọi phương thức diễn ra.
2. **Gọi Supplier:** thân lambda hoặc method reference chỉ chạy khi API gọi `get()`.

Vì vậy, `orElseGet(() -> expensiveCall())` trì hoãn `expensiveCall()`; còn `orElse(expensiveCall())` thực hiện `expensiveCall()` trước khi gọi `orElse`.

## 2. `orElse()` và `orElseGet()`: eager so với lazy

### 2.1. `orElse(value)` đánh giá đối số ngay

`Optional.orElse(T other)` trả về giá trị đang có nếu Optional hiện diện, nếu không thì trả về `other`. Java phải đánh giá biểu thức đối số trước khi gọi phương thức, nên biểu thức tạo giá trị thay thế vẫn chạy kể cả khi Optional đã có giá trị.

```java
String result = Optional.of("primary")
        .orElse(loadFallback());
```

Trong ví dụ này, `loadFallback()` đã được gọi trước khi `orElse()` quyết định trả về `"primary"`. Nếu việc tạo giá trị thay thế tốn I/O, truy vấn database hoặc có side effect, công việc đó vẫn xảy ra.

### 2.2. `orElseGet(supplier)` chỉ gọi khi Optional rỗng

`Optional.orElseGet(Supplier<? extends T> supplier)` chỉ gọi `supplier.get()` khi Optional không có giá trị:

```java
String result = Optional.of("primary")
        .orElseGet(() -> loadFallback());
```

Trong trường hợp này, `loadFallback()` không chạy vì Optional đã có giá trị. Nếu Optional rỗng, Supplier được gọi đúng tại thời điểm cần lấy fallback.

| Tình huống | `orElse(value)` | `orElseGet(supplier)` |
|---|---|---|
| Optional có giá trị | Đối số `value` đã được tính; trả giá trị hiện có | Không gọi `supplier.get()`; trả giá trị hiện có |
| Optional rỗng | Trả đối số đã tính | Gọi Supplier rồi trả kết quả |
| Tạo fallback tốn kém | Vẫn tốn chi phí dù không dùng | Tránh chi phí nếu Optional có giá trị |
| Supplier ném exception | Không áp dụng Supplier | Exception chỉ phát sinh nếu Supplier được gọi |

Dùng `orElse()` khi giá trị thay thế đơn giản, rẻ và an toàn khi tính trước. Dùng `orElseGet()` khi fallback cần được tính có điều kiện hoặc có thể tốn tài nguyên.

## 3. Giới hạn null của `orElseGet()`

`orElseGet()` không bắt buộc kết quả của Supplier phải khác null. Nếu Optional rỗng và Supplier trả về null, phương thức trả về null:

```java
String result = Optional.<String>empty().orElseGet(() -> null);
System.out.println(result == null); // true
```

Điều này không làm Optional chứa null; Optional vẫn rỗng. Chính giá trị trả về của lời gọi `orElseGet()` là null. Vì vậy, nếu kết quả được gán cho biến hoặc truyền tiếp như một giá trị thông thường, người gọi phải xử lý khả năng null.

Hợp đồng về Supplier null cũng phụ thuộc vào việc Supplier có được gọi hay không:

- Optional có giá trị và Supplier là null: phương thức trả về giá trị hiện có, không dereference Supplier nên không ném NullPointerException.
- Optional rỗng và Supplier là null: phương thức cần gọi `get()`, vì vậy ném NullPointerException.
- Optional rỗng và Supplier trả về null: phương thức trả về null.

Không nên cố tình trả null từ Supplier nếu mục tiêu của chương trình là giữ quy tắc dữ liệu không null. Hãy trả về một giá trị thay thế hợp lệ hoặc dùng một API có hợp đồng bắt buộc kết quả khác null.

## 4. `Optional.or()`: Supplier phải trả về Optional khác null

Java 9 bổ sung `Optional.or(Supplier<? extends Optional<? extends T>> supplier)`. Phương thức này hữu ích khi nguồn dự phòng cũng có thể không tìm thấy dữ liệu, chẳng hạn thử cache trước rồi mới truy vấn repository.

```java
Optional<User> user = findInCache(userId)
        .or(() -> findInDatabase(userId));
```

Nếu Optional ban đầu có giá trị, Supplier không được gọi và chính Optional ban đầu được trả về. Nếu Optional ban đầu rỗng, Supplier được gọi và phải trả về một Optional khác null. Supplier có thể trả về `Optional.empty()` nếu nguồn dự phòng cũng không có kết quả.

Ví dụ:

```java
Optional<String> result = Optional.<String>empty()
        .or(() -> Optional.of("secondary"));
```

Khác với `orElseGet()`, `or()` không cho phép Supplier trả về null. Nếu Supplier trả về null, `or()` ném NullPointerException vì kết quả của phương thức luôn phải là một Optional hợp lệ.

Một chi tiết quan trọng: `or()` kiểm tra bản thân Supplier khác null ngay khi phương thức được gọi, kể cả khi Optional ban đầu đã có giá trị. Do đó:

```java
Optional.of("present").or(null); // NullPointerException
```

Đây là khác biệt so với `orElseGet(null)`, vốn không dereference Supplier nếu Optional đang có giá trị.

## 5. `orElseThrow(Supplier)`: Supplier phải tạo exception

`Optional.orElseThrow(Supplier<? extends X> exceptionSupplier)` trả về giá trị nếu Optional hiện diện. Nếu Optional rỗng, nó gọi Supplier và ném exception do Supplier tạo ra.

```java
User user = findUser(userId)
        .orElseThrow(() -> new UserNotFoundException(userId));
```

Supplier không chạy khi Optional có giá trị. Khi Optional rỗng, Supplier phải trả về một exception khác null. Nếu Supplier trả về null, thao tác ném exception không thể thực hiện và Java ném NullPointerException.

Supplier null cũng chỉ bị dereference trong nhánh Optional rỗng:

- Optional có giá trị: `orElseThrow(null)` vẫn trả về giá trị hiện có.
- Optional rỗng: `orElseThrow(null)` ném NullPointerException khi cố gọi Supplier.

Hãy chọn exception phản ánh đúng hợp đồng của lớp hoặc tầng ứng dụng. Không nên dùng một exception chung chung nếu có thể biểu diễn rõ nguyên nhân như không tìm thấy bản ghi hoặc dữ liệu không hợp lệ.

## 6. Đối chiếu với `Objects.requireNonNullElseGet()`

Java 9 bổ sung `Objects.requireNonNullElseGet(T obj, Supplier<? extends T> supplier)` để chọn giá trị mặc định cho một tham chiếu có thể null.

```java
String displayName = Objects.requireNonNullElseGet(
        configuredName,
        () -> loadDefaultName()
);
```

Nếu `configuredName` khác null, phương thức trả về ngay giá trị đó và không gọi Supplier. Nếu `configuredName` là null, Supplier được gọi để tạo giá trị thay thế.

Khác với `Optional.orElseGet()`, phương thức này yêu cầu cả Supplier được dùng và giá trị Supplier trả về đều khác null:

- `obj` khác null: Supplier không được gọi; một Supplier null không gây lỗi trong nhánh này.
- `obj` là null và Supplier null: ném NullPointerException.
- `obj` là null và Supplier trả về null: ném NullPointerException.

Nếu muốn chấp nhận kết quả null, `requireNonNullElseGet()` không phù hợp. Hãy chọn API có hợp đồng đúng với dữ liệu hoặc kiểm tra giá trị trước khi tiếp tục.

## 7. Bảng so sánh thời điểm gọi và quy tắc null

| API | Khi nào gọi Supplier? | Supplier null | Supplier trả về null |
|---|---|---|---|
| `Optional.orElseGet()` | Chỉ khi Optional rỗng | Chỉ gây lỗi nếu cần gọi | Được phép; kết quả phương thức là null |
| `Optional.or()` | Chỉ khi Optional rỗng | Bị từ chối ngay cả khi Optional có giá trị | Bị từ chối; phải trả Optional khác null |
| `Optional.orElseThrow(Supplier)` | Chỉ khi Optional rỗng | Gây lỗi khi cần gọi | Gây NullPointerException thay vì ném exception dự kiến |
| `Objects.requireNonNullElseGet()` | Chỉ khi đối số đầu vào null | Gây lỗi nếu cần gọi | Bị từ chối; kết quả phải khác null |

Bảng này phân biệt **Supplier có null** với **kết quả do Supplier tạo ra là null**. Đây là hai trường hợp khác nhau và có thể xảy ra ở những thời điểm khác nhau.

## 8. Ví dụ hoàn chỉnh kiểm chứng thời điểm gọi và null

Tệp `SupplierTimingDemo.java` sau chạy trên Java 9 trở lên. Ví dụ dùng bộ đếm để chứng minh Supplier có được gọi hay không và kiểm tra các trường hợp null quan trọng.

```java
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class SupplierTimingDemo {
    private static String fallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return "fallback";
    }

    private static Optional<String> optionalFallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return Optional.of("secondary");
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();

        String eager = Optional.of("primary").orElse(fallback(calls));
        System.out.println("orElse eager value: " + eager);
        System.out.println("orElse eager calls: " + calls.get());

        calls.set(0);
        String lazy = Optional.of("primary").orElseGet(() -> fallback(calls));
        System.out.println("orElseGet value: " + lazy);
        System.out.println("orElseGet calls: " + calls.get());

        String missing = Optional.<String>empty().orElseGet(() -> fallback(calls));
        System.out.println("orElseGet fallback: " + missing);
        System.out.println("orElseGet calls after empty: " + calls.get());

        calls.set(0);
        Optional<String> chained = Optional.<String>empty()
                .or(() -> optionalFallback(calls));
        System.out.println("or fallback: " + chained.orElse("none"));
        System.out.println("or supplier calls: " + calls.get());

        Optional<String> emptyFallback = Optional.<String>empty().or(Optional::empty);
        System.out.println("or empty fallback present: " + emptyFallback.isPresent());

        try {
            Optional.of("present").or(null);
        } catch (NullPointerException ex) {
            System.out.println("or null Supplier with present Optional: NullPointerException");
        }

        try {
            Optional.<String>empty().or(() -> null);
        } catch (NullPointerException ex) {
            System.out.println("or Supplier returning null: NullPointerException");
        }

        try {
            Optional.<String>empty().orElseThrow(() -> new IllegalStateException("missing"));
        } catch (IllegalStateException ex) {
            System.out.println("orElseThrow message: " + ex.getMessage());
        }

        try {
            Optional.<String>empty().orElseThrow(() -> null);
        } catch (NullPointerException ex) {
            System.out.println("orElseThrow Supplier returning null: NullPointerException");
        }

        String safeNullSupplier = Optional.of("present").orElseGet(null);
        System.out.println("orElseGet null Supplier with present Optional: " + safeNullSupplier);

        try {
            Optional.<String>empty().orElseGet(null);
        } catch (NullPointerException ex) {
            System.out.println("orElseGet null Supplier with empty Optional: NullPointerException");
        }

        String nullableFallback = Optional.<String>empty().orElseGet(() -> null);
        System.out.println("orElseGet Supplier returning null: " + nullableFallback);

        String safeObjectsFallback = Objects.requireNonNullElseGet("present", null);
        System.out.println("requireNonNullElseGet null Supplier with value: " + safeObjectsFallback);

        try {
            Objects.requireNonNullElseGet(null, () -> null);
        } catch (NullPointerException ex) {
            System.out.println("requireNonNullElseGet Supplier returning null: NullPointerException");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all SupplierTimingDemo.java
java SupplierTimingDemo
```

Stdout:

```text
orElse eager value: primary
orElse eager calls: 1
orElseGet value: primary
orElseGet calls: 0
orElseGet fallback: fallback
orElseGet calls after empty: 1
or fallback: secondary
or supplier calls: 1
or empty fallback present: false
or null Supplier with present Optional: NullPointerException
or Supplier returning null: NullPointerException
orElseThrow message: missing
orElseThrow Supplier returning null: NullPointerException
orElseGet null Supplier with present Optional: present
orElseGet null Supplier with empty Optional: NullPointerException
orElseGet Supplier returning null: null
requireNonNullElseGet null Supplier with value: present
requireNonNullElseGet Supplier returning null: NullPointerException
```

Các dòng đầu cho thấy `orElse()` tính fallback ngay, còn `orElseGet()` không gọi Supplier khi Optional có giá trị. Các dòng sau chứng minh `or()` kiểm tra Supplier null ngay cả ở nhánh có giá trị, đồng thời yêu cầu kết quả Supplier là Optional hợp lệ. `orElseThrow()` cần một exception khác null khi Optional rỗng. `requireNonNullElseGet()` chỉ gọi Supplier khi tham chiếu đầu vào null và yêu cầu giá trị mặc định khác null.

## 9. Lỗi thường gặp

1. **Dùng `orElse(expensiveCall())` và nghĩ lời gọi chỉ chạy khi Optional rỗng:** đối số được đánh giá trước khi vào phương thức. Dùng `orElseGet(() -> expensiveCall())` nếu cần trì hoãn.
2. **Cho rằng mọi Supplier đều có cùng hợp đồng null:** `orElseGet` cho phép trả null; `or`, `orElseThrow` và `requireNonNullElseGet` có yêu cầu khác.
3. **Cho rằng Supplier null luôn gây lỗi ngay:** thời điểm lỗi phụ thuộc API. `or()` kiểm tra Supplier ngay; `orElseGet()` chỉ dereference ở nhánh rỗng.
4. **Trả null từ Supplier của `or()`:** phương thức cần một Optional khác null. Dùng `Optional.empty()` nếu nguồn dự phòng không có dữ liệu.
5. **Trả null từ exception Supplier:** `orElseThrow` cần một exception để ném. Hãy tạo exception phù hợp.
6. **Dùng `orElseGet` nhưng quên kết quả có thể null:** nếu nghiệp vụ yêu cầu giá trị luôn khác null, kiểm tra hoặc chọn API có hợp đồng non-null.
7. **Đặt side effect trong Supplier mà không hiểu số lần gọi:** Supplier chỉ chạy ở nhánh cần thiết, nhưng nếu lời gọi API nằm trong một vòng lặp thì nó có thể được gọi nhiều lần qua nhiều lần thực thi.
8. **Nhầm tạo lambda với gọi Supplier:** thân lambda chưa chạy khi tạo; nó chỉ chạy khi API gọi `get()`.

## 10. Cách chọn API

- Cần một giá trị mặc định đơn giản, có thể tính ngay: dùng `orElse(value)`.
- Cần tính giá trị thay thế có điều kiện: dùng `orElseGet(supplier)`.
- Cần chuyển sang một nguồn tra cứu khác vẫn có thể không tìm thấy: dùng `or(supplier)` và luôn trả Optional khác null.
- Cần dừng luồng xử lý bằng một exception khi không có giá trị: dùng `orElseThrow(exceptionSupplier)`.
- Cần thay thế một tham chiếu null bằng giá trị khác null: dùng `Objects.requireNonNullElseGet(value, supplier)`.

Hãy thiết kế Supplier không có side effect không cần thiết, xác định rõ API có thể trả null hay không và chỉ dựa vào việc Supplier được gọi ở nhánh mà hợp đồng quy định. Điều này giúp tránh công việc tốn kém ngoài ý muốn, lỗi null khó truy vết và hành vi không nhất quán giữa các API.
