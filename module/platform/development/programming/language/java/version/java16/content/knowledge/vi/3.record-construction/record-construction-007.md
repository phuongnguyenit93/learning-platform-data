# Vì sao không được gán trực tiếp component field trong compact constructor

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — tìm hiểu các cải tiến từ Java 16 còn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này giải thích quy tắc ngôn ngữ cấm gán trực tiếp component field trong compact constructor và cách viết đúng khi cần kiểm tra hoặc biến đổi dữ liệu.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt tham số ngầm và component field trong compact canonical constructor.
- Nhận diện phép gán hợp lệ vào tham số và phép gán bị cấm vào field.
- Giải thích vì sao compiler trì hoãn việc gán component field đến sau thân constructor.
- Sửa lỗi `this.x = ...` bằng cách gán lại tham số ngầm.
- Chọn canonical constructor dạng đầy đủ khi cần tự điều khiển các phép gán field.
- Tránh đọc component field trước khi chúng được khởi tạo và tránh để lộ `this` quá sớm.

## 1. Hai thứ khác nhau: tham số và component field

Xét record:

```java
public record Point(int x, int y) {}
```

Từ record header, Java cung cấp hai component field `private final int x` và `private final int y`, cùng các accessor `x()` và `y()`. Record cũng có canonical constructor tương ứng với hai component.

Khi viết compact constructor:

```java
public record Point(int x, int y) {
    public Point {
        // Có thể dùng x và y ở đây.
    }
}
```

Tên `x` và `y` bên trong thân compact constructor là **các tham số ngầm** được suy ra từ header. Chúng là biến tham số của constructor, không phải field của đối tượng.

Trong khi đó:

- `x` là tham số ngầm.
- `this.x` là component field của đối tượng hiện tại.
- `y` là tham số ngầm.
- `this.y` là component field của đối tượng hiện tại.

Sự phân biệt này là nền tảng để hiểu quy tắc gán dữ liệu trong compact constructor.

## 2. Vì sao phép gán vào field bị cấm?

Đoạn mã sau không hợp lệ:

```java
// SAI: không được gán trực tiếp component field trong compact constructor.
public record Point(int x, int y) {
    public Point {
        this.x = x;
        this.y = y;
    }
}
```

Compiler báo lỗi vì **thân compact constructor không được chứa phép gán vào bất kỳ field nào tương ứng với record component**. Điều này áp dụng dù bạn gán giá trị ban đầu, gán giá trị đã chuẩn hóa hay gán một giá trị hằng.

Ví dụ sau cũng sai:

```java
public record Score(int value) {
    public Score {
        this.value = Math.max(0, value);
    }
}
```

Không thể dùng `this.value = ...` để thay đổi cách lưu giá trị trong compact constructor. Quy tắc này là một phần của ngữ nghĩa compact constructor, không phải giới hạn riêng của IDE hay một quy ước phong cách.

## 3. Lý do: compiler chịu trách nhiệm gán field sau thân constructor

Compact constructor có một cơ chế khởi tạo được định nghĩa rõ:

1. Các tham số ngầm nhận giá trị từ đối số của lời gọi constructor.
2. Thân compact constructor chạy, cho phép kiểm tra và gán lại các tham số.
3. Nếu thân kết thúc bình thường, compiler tự gán giá trị cuối cùng của từng tham số vào component field tương ứng, theo thứ tự component trong header.

Ví dụ:

```java
public record Score(int value) {
    public Score {
        value = Math.max(0, value);
    }
}
```

Khi gọi `new Score(-5)`:

- Tham số `value` ban đầu nhận `-5`.
- `Math.max(0, value)` trả về `0`.
- Câu lệnh `value = ...` gán lại tham số thành `0`.
- Thân constructor kết thúc bình thường.
- Compiler gán giá trị cuối cùng `0` vào field `this.value`.

Kết quả:

```java
Score score = new Score(-5);

System.out.println(score.value()); // 0
```

Có thể hình dung phép gán ngầm do compiler thực hiện như sau:

```java
// Minh họa ngữ nghĩa sau khi thân compact constructor chạy.
// Không chép phép gán này vào thân compact constructor.
this.value = value;
```

Với record nhiều component, compiler gán từng tham số cuối cùng vào field tương ứng theo thứ tự khai báo. Bạn không cần tự viết và cũng không được viết các phép gán đó trong compact constructor.

## 4. Cách viết đúng: gán lại tham số ngầm

Thay vì gán field, hãy thay đổi tham số ngầm. Giá trị cuối cùng của tham số sẽ được compiler lưu vào component field.

Ví dụ chuẩn hóa tọa độ:

```java
public record Coordinate(int x, int y) {
    public Coordinate {
        x = Math.max(0, x);
        y = Math.max(0, y);
    }
}
```

Hai phép gán trên hợp lệ vì chúng thay đổi biến tham số `x` và `y`, không đụng trực tiếp đến field.

Sử dụng:

```java
Coordinate point = new Coordinate(-10, 25);

System.out.println(point.x()); // 0
System.out.println(point.y()); // 25
```

Bảng sau tóm tắt sự khác nhau:

| Câu lệnh trong compact constructor | Đối tượng được tác động | Hợp lệ? |
| --- | --- | --- |
| `x = Math.max(0, x);` | Tham số ngầm `x` | Có |
| `this.x = Math.max(0, x);` | Component field `this.x` | Không |
| `int normalized = x + 1;` | Tạo biến cục bộ | Có |
| `x = normalized;` | Tham số ngầm `x` | Có |
| `this.x = normalized;` | Component field `this.x` | Không |

Hãy đọc kỹ vế trái của phép gán. Nếu vế trái là tên tham số không có `this`, đó là gán lại tham số. Nếu vế trái là `this.component`, đó là gán field và bị cấm trong compact constructor.

## 5. Không phải cứ bỏ this là gán field

Với tên trùng nhau giữa tham số và field, tên đơn giản trong thân compact constructor tham chiếu đến tham số ngầm.

Ví dụ:

```java
public record Label(String value) {
    public Label {
        value = value.strip();
    }
}
```

Câu lệnh `value = value.strip()` có thể được đọc như:

- Vế phải `value.strip()` sử dụng tham số `value` hiện tại.
- Vế trái `value` cũng là tham số `value`.
- Tham số được cập nhật bằng chuỗi đã bỏ khoảng trắng.
- Sau đó compiler dùng giá trị tham số cuối cùng để khởi tạo field.

Nếu viết `this.value`, bạn đang chỉ rõ field của đối tượng. Vì field chưa được gán ở thời điểm thân constructor chạy, việc dùng field như thể nó đã chứa giá trị đầu vào là sai về mô hình khởi tạo; phép gán trực tiếp còn bị ngôn ngữ cấm.

Đừng dựa vào tên biến để suy luận mơ hồ. Khi cần biến đổi, hãy sử dụng tham số hoặc một biến cục bộ có tên rõ nghĩa.

## 6. Ví dụ kiểm tra null và chuẩn hóa chuỗi

Một ví dụ thường gặp là từ chối null, bỏ khoảng trắng và kiểm tra chuỗi sau chuẩn hóa:

```java
import java.util.Objects;

public record UserName(String value) {
    public UserName {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
```

Cách viết sai mà nhiều người mới học dễ thử:

```java
// SAI: không được gán trực tiếp component field.
import java.util.Objects;

public record UserName(String value) {
    public UserName {
        String normalized =
                Objects.requireNonNull(value, "value").strip();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }

        this.value = normalized;
    }
}
```

Cách sửa là đưa giá trị đã chuẩn hóa trở lại tham số ngầm:

```java
import java.util.Objects;

public record UserName(String value) {
    public UserName {
        String normalized =
                Objects.requireNonNull(value, "value").strip();

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }

        value = normalized;
    }
}
```

Trong compact constructor, compiler sẽ sử dụng `value` sau cùng để gán field. Biến cục bộ `normalized` chỉ hỗ trợ xử lý, không phải nơi lưu component của record.

## 7. Không thể gán field rồi gán lại tham số để sửa chữa

Một cách viết sai khác là vừa gán field vừa gán tham số:

```java
// SAI: phép gán field vẫn bị cấm.
public record Quantity(int value) {
    public Quantity {
        this.value = value;
        value = Math.max(0, value);
    }
}
```

Gán lại tham số ở dòng sau không làm cho phép gán field ở dòng trước trở nên hợp lệ. Compiler kiểm tra quy tắc cấm assignment vào component field trong toàn bộ thân compact constructor.

Chỉ cần viết:

```java
public record Quantity(int value) {
    public Quantity {
        value = Math.max(0, value);
    }
}
```

Không có bước gán field thủ công nào cần bổ sung.

## 8. Không đọc component field trước khi compiler gán

Các component field được gán sau khi thân compact constructor kết thúc bình thường. Vì vậy, trong thân constructor, hãy dùng tham số ngầm để đọc giá trị đầu vào và giá trị đã chuẩn hóa.

Ví dụ nên viết:

```java
public record Range(int min, int max) {
    public Range {
        if (min > max) {
            throw new IllegalArgumentException("min must not exceed max");
        }

        min = Math.max(0, min);
        max = Math.max(0, max);
    }
}
```

Không dựa vào `this.min` hoặc `this.max` như thể chúng đã được khởi tạo từ tham số. Component field chưa được compiler gán trong lúc thân compact constructor đang chạy; việc đọc một field `final` chưa được khởi tạo còn vi phạm quy tắc definite assignment của Java.

Nếu cần so sánh hai component, hãy so sánh các tham số ngầm:

```java
public record DateRange(
        java.time.LocalDate start,
        java.time.LocalDate end
) {
    public DateRange {
        java.util.Objects.requireNonNull(start, "start");
        java.util.Objects.requireNonNull(end, "end");

        if (start.isAfter(end)) {
            throw new IllegalArgumentException("start must not be after end");
        }
    }
}
```

`start` và `end` trong phép so sánh là các tham số ngầm. Không cần truy cập field `this.start` hay `this.end`.

## 9. Nếu cần tự gán field, hãy dùng canonical constructor dạng đầy đủ

Java có một dạng canonical constructor khác với danh sách tham số tường minh. Trong dạng này, bạn **được phép và phải tự gán** các component field.

Ví dụ:

```java
public record Coordinate(int x, int y) {
    public Coordinate(int x, int y) {
        this.x = Math.max(0, x);
        this.y = Math.max(0, y);
    }
}
```

Ở đây, `this.x = ...` và `this.y = ...` hợp lệ vì đây là canonical constructor dạng đầy đủ, không phải compact constructor.

Phân biệt hai cách:

```java
// Compact canonical: gán lại tham số, compiler tự gán field.
public record Coordinate(int x, int y) {
    public Coordinate {
        x = Math.max(0, x);
        y = Math.max(0, y);
    }
}
```

```java
// Canonical đầy đủ: tự gán field.
public record Coordinate(int x, int y) {
    public Coordinate(int x, int y) {
        this.x = Math.max(0, x);
        this.y = Math.max(0, y);
    }
}
```

Đây là hai phiên bản thay thế nhau; không khai báo cả hai trong cùng một record vì chúng cùng là canonical constructor.

| Tiêu chí | Compact canonical | Canonical đầy đủ |
| --- | --- | --- |
| Danh sách tham số | Suy ra từ record header | Khai báo tường minh |
| Chuẩn hóa | Gán lại tham số | Gán giá trị đã xử lý vào field |
| Gán field | Compiler tự gán sau thân constructor | Người viết tự gán |
| Có được viết `this.component = ...`? | Không | Có |
| Phù hợp | Kiểm tra, chuẩn hóa ngắn gọn | Cần kiểm soát rõ phép gán từng field |

## 10. Constructor nạp chồng vẫn có thể ủy quyền bằng this(...)

Nếu cần một cách khởi tạo khác, record có thể có constructor nạp chồng. Constructor nạp chồng không phải compact canonical constructor và có thể gọi canonical constructor bằng `this(...)`.

```java
public record UserName(String value) {
    public UserName {
        value = java.util.Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }

    public UserName() {
        this("guest");
    }
}
```

Lời gọi `new UserName()` đi qua constructor không tham số, rồi ủy quyền đến canonical constructor `UserName(String value)`. Quy tắc kiểm tra và chuẩn hóa vẫn được thực hiện tập trung ở canonical constructor.

Không nhầm quy tắc này với compact constructor: lời gọi `this(...)` không được đặt trong thân compact constructor.

## 11. Điều gì xảy ra nếu compact constructor ném ngoại lệ?

Compiler chỉ thực hiện phép gán field ngầm khi thân compact constructor kết thúc bình thường. Nếu thân ném ngoại lệ, quá trình khởi tạo không tạo ra đối tượng record thành công.

```java
public record PositiveQuantity(int value) {
    public PositiveQuantity {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }

        value = Math.max(1, value);
    }
}
```

- `new PositiveQuantity(5)`: kiểm tra thành công, tham số vẫn là 5, compiler gán field sau thân constructor.
- `new PositiveQuantity(0)`: ném ngoại lệ ngay ở điều kiện, không thực hiện phép gán field ngầm.
- Không cần gán field trước khi ném ngoại lệ; đối tượng không được trả về cho bên gọi.

Đây cũng là lý do nên đặt validation trong canonical constructor: không có đối tượng hợp lệ nào được tạo ra nếu dữ liệu vi phạm điều kiện.

## 12. Tránh làm lộ this khi component field chưa được gán

Trong thân compact constructor, các component field chưa được gán bằng các tham số cuối cùng. Vì vậy, không nên chuyển `this` cho callback, đăng ký nó vào listener hoặc lưu nó vào một cấu trúc bên ngoài trước khi constructor hoàn tất.

Ví dụ ý tưởng không an toàn:

```java
// Không nên: đối tượng có thể bị quan sát trước khi component field được gán.
public record EventConfig(String name) {
    public EventConfig {
        EventRegistry.register(this);
        name = name.strip();
    }
}
```

Nếu `register` giữ lại hoặc công bố đối tượng ngay lập tức, mã khác có thể quan sát đối tượng trong khi quá trình khởi tạo chưa hoàn tất. Hãy tránh escape `this` trong constructor; chỉ công bố đối tượng sau khi việc tạo record kết thúc.

## 13. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `this.x = x;` trong compact constructor | Gán trực tiếp component field bị cấm. | Gán lại tham số `x = ...`. |
| `this.x = normalize(x);` | Dù giá trị đã chuẩn hóa, vẫn là phép gán field. | Viết `x = normalize(x);`. |
| Gán field rồi mới gán lại tham số | Phép gán field đã vi phạm quy tắc; dòng sau không sửa được lỗi. | Chỉ thay đổi tham số. |
| Dùng field `this.x` để xử lý đầu vào | Field chưa được gán tại thời điểm thân constructor chạy. | Dùng tham số ngầm `x`. |
| Nghĩ bỏ `this` sẽ luôn gán field | Tên component trong thân compact constructor là tham số ngầm. | Hiểu rõ tên tham số và field. |
| Khai báo compact constructor rồi tự thêm phép gán cuối | Compiler đã chịu trách nhiệm gán field. | Xóa phép gán field. |
| Dùng compact constructor nhưng cần tự điều khiển field | Compact constructor không cho phép điều đó. | Chọn canonical constructor dạng đầy đủ. |
| Đưa `this` ra ngoài trước khi constructor kết thúc | Đối tượng có thể bị quan sát trước khi field được gán. | Chỉ công bố đối tượng sau khi khởi tạo xong. |

## 14. Kiểm thử hành vi chuẩn hóa

Một test hữu ích cần kiểm tra giá trị accessor trả về sau khi khởi tạo, để xác nhận tham số được chuẩn hóa đúng trước khi compiler gán field.

Ví dụ với JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void clampsNegativeInputToZero() {
        Quantity quantity = new Quantity(-5);

        assertEquals(0, quantity.value());
    }

    @Test
    void preservesPositiveInput() {
        Quantity quantity = new Quantity(8);

        assertEquals(8, quantity.value());
    }
}
```

Nếu constructor chọn cách từ chối dữ liệu không hợp lệ thay vì chuẩn hóa, hãy viết test xác nhận ngoại lệ phù hợp:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PositiveQuantityTest {

    @Test
    void rejectsZero() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new PositiveQuantity(0)
        );
    }
}
```

Nên có các test cho:

- Đầu vào cần chuẩn hóa.
- Đầu vào vốn đã ở dạng chuẩn.
- Giá trị biên và ngoài biên.
- Null đối với component bắt buộc.
- Quan hệ giữa các component.
- Ngoại lệ khi validation thất bại.
- Constructor nạp chồng ủy quyền đến canonical constructor.

## 15. Bài tập tự luyện

### Bài 1: Sửa compact constructor

Đoạn mã sau không hợp lệ. Hãy sửa để giá trị âm được chuyển thành 0:

```java
public record Stock(int count) {
    public Stock {
        this.count = Math.max(0, count);
    }
}
```

**Đáp án:**

```java
public record Stock(int count) {
    public Stock {
        count = Math.max(0, count);
    }
}
```

Tham số ngầm `count` được gán lại. Compiler tự gán giá trị cuối cùng vào field `this.count` sau khi thân constructor kết thúc bình thường.

### Bài 2: Chọn câu lệnh hợp lệ

Trong compact constructor của `record Distance(int meters)`, câu lệnh nào hợp lệ?

- A. `this.meters = Math.max(0, meters);`
- B. `meters = Math.max(0, meters);`
- C. `this.meters++;`

**Đáp án:** B. A và C tác động trực tiếp đến component field, còn B chỉ thay đổi tham số ngầm.

### Bài 3: Khi nào field được gán?

Cho compact constructor:

```java
public record Tag(String value) {
    public Tag {
        value = value.strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }
    }
}
```

**Đáp án:** Field `this.value` được compiler gán sau khi thân constructor kết thúc bình thường. Nếu `value` rỗng và ngoại lệ được ném ra, phép gán ngầm không diễn ra.

### Bài 4: Khi nào dùng canonical đầy đủ?

Bạn cần viết constructor có nhiều phép gán field tường minh theo logic riêng và muốn kiểm soát chính xác từng field nhận giá trị nào.

**Đáp án:** Chọn canonical constructor dạng đầy đủ, khai báo danh sách tham số khớp record header và tự gán tất cả field `final` đúng một lần trên mọi đường chạy kết thúc bình thường.

## Ghi nhớ

Compact constructor không cho phép gán trực tiếp component field vì compiler đã đảm nhiệm việc khởi tạo các field đó sau khi thân constructor kết thúc bình thường. Bên trong thân, tên component là tham số ngầm; hãy kiểm tra và gán lại tham số để điều chỉnh giá trị sẽ được lưu. Nếu muốn tự viết `this.component = ...`, hãy dùng canonical constructor dạng đầy đủ. Hiểu đúng ranh giới giữa tham số và field giúp tránh lỗi biên dịch, giữ cho dữ liệu record nhất quán và làm rõ thời điểm khởi tạo.

## Tài liệu tham khảo

- [Java Language Specification — `8.10.4.2, Compact Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4.2).
- [Java Language Specification — `8.10.3, Record Members](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.3).
- [JEP 395 — Records (được hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
