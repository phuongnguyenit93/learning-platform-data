# Compact constructor và thời điểm compiler tự gán component field

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — tìm hiểu các cải tiến từ Java 16 vẫn còn hữu ích trong Java hiện đại, trong đó có `record`. Bài này giải thích chính xác thứ tự thực thi của compact constructor và thời điểm các component field được gán ngầm.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện compact canonical constructor trong khai báo record.
- Giải thích các tham số của compact constructor được suy ra từ record header.
- Xác định thời điểm phần thân constructor chạy và thời điểm trình biên dịch gán component field.
- Chuẩn hóa tham số để giá trị được lưu vào field tương ứng.
- Phân biệt việc gán lại tham số với việc gán trực tiếp field `final`.
- Tránh các lỗi như tự gán `this.component`, đọc field quá sớm hoặc làm lộ đối tượng trước khi khởi tạo xong.
- Chọn compact constructor hay canonical constructor dạng đầy đủ theo nhu cầu.

## 1. Compact constructor là gì?

Record cho phép khai báo constructor chuẩn (canonical constructor) theo hai dạng: dạng đầy đủ có danh sách tham số tường minh và dạng compact không viết danh sách tham số.

Ví dụ:

```java
public record ProductCode(String value) {
    public ProductCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value is required");
        }
    }
}
```

Phần khai báo `public ProductCode { ... }` là **compact canonical constructor**. Nó vẫn là canonical constructor của record, nhưng danh sách tham số được suy ra từ record header:

```java
public record ProductCode(String value) {
    // Tham số ngầm: String value
    public ProductCode {
        // Phần thân constructor
    }
}
```

Trong ví dụ này, tham số ngầm là `String value` vì record có một component tên `value` kiểu `String`.

Với record có nhiều component:

```java
public record OrderLine(String sku, int quantity, boolean taxable) {
    public OrderLine {
        // Có thể sử dụng sku, quantity, taxable ở đây.
    }
}
```

Compact constructor có ba tham số ngầm, theo đúng thứ tự và kiểu của header:

1. `String sku`
2. `int quantity`
3. `boolean taxable`

Bạn không viết lại danh sách tham số, nhưng vẫn có thể sử dụng tên tham số trong thân constructor như các biến tham số bình thường.

## 2. Thời điểm compiler tự gán component field

Đây là quy tắc quan trọng nhất của compact constructor:

**Phần thân compact constructor được thực thi trước. Khi phần thân kết thúc bình thường, trình biên dịch mới thực hiện các phép gán ngầm từ tham số vào component field.**

Với khai báo:

```java
public record ProductCode(String value) {
    public ProductCode {
        value = value.strip();
    }
}
```

Trình biên dịch thực hiện theo trình tự khái niệm:

1. Nhận giá trị đối số và khởi tạo tham số ngầm `value`.
2. Chạy toàn bộ câu lệnh trong thân compact constructor.
3. Khi thân kết thúc bình thường, gán giá trị cuối cùng của tham số vào field `this.value`.

Có thể hình dung phần gán được bổ sung như sau:

```java
// Minh họa ngữ nghĩa, không chép các dòng gán này
// vào bên trong compact constructor.
this.value = value;
```

Với record nhiều component:

```java
public record UserProfile(String username, int age) {
    public UserProfile {
        username = username.strip();
        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }
    }
}
```

Các phép gán ngầm tương ứng sau khi thân constructor kết thúc bình thường là:

```java
// Mô tả các phép gán do compiler thực hiện sau thân constructor.
this.username = username;
this.age = age;
```

Thứ tự gán ngầm theo thứ tự component trong record header: `username` trước, rồi `age`.

Đây là mô tả ngữ nghĩa để hiểu thời điểm khởi tạo. Bạn **không viết các phép gán `this.field = ...` trong thân compact constructor**.

## 3. Vì sao có thể chuẩn hóa tham số trong compact constructor?

Các tham số ngầm trong compact constructor không phải là component field. Chúng là biến tham số được khai báo ngầm từ record header. Bạn có thể kiểm tra hoặc gán lại chúng trong thân constructor.

Ví dụ:

```java
import java.util.Locale;

public record ProductCode(String value) {
    public ProductCode {
        value = value.strip().toUpperCase(Locale.ROOT);
    }
}
```

Nếu gọi:

```java
ProductCode code = new ProductCode("  ab-123  ");

System.out.println(code.value()); // AB-123
```

Trình tự là:

- Tham số `value` ban đầu nhận chuỗi `"  ab-123  "`.
- Câu lệnh `value = value.strip().toUpperCase()` gán lại biến tham số.
- Khi thân constructor kết thúc bình thường, compiler gán giá trị mới của tham số vào field `this.value`.

Vì vậy, accessor `value()` trả về giá trị đã chuẩn hóa.

Điểm cần nhớ: **gán lại tham số là cách compact constructor điều chỉnh giá trị sẽ được lưu vào component field**. Không cần và không được tự viết phép gán field.

## 4. Không gán trực tiếp component field trong thân compact constructor

Một lỗi thường gặp là viết compact constructor giống constructor dạng đầy đủ:

```java
// SAI: compact constructor không cho phép gán trực tiếp component field.
public record ProductCode(String value) {
    public ProductCode {
        this.value = value.strip();
    }
}
```

Lệnh `this.value = ...` bị cấm trong compact constructor. Component field sẽ được compiler gán ngầm sau khi thân constructor hoàn tất bình thường.

Cách viết đúng:

```java
public record ProductCode(String value) {
    public ProductCode {
        value = value.strip();
    }
}
```

Hãy phân biệt:

| Câu lệnh trong compact constructor | Ý nghĩa |
| --- | --- |
| `value = value.strip();` | Gán lại tham số ngầm `value`; hợp lệ. |
| `this.value = value.strip();` | Gán trực tiếp component field; không hợp lệ. |
| `String normalized = value.strip();` | Tạo biến cục bộ; hợp lệ. |
| `value = normalized;` | Đưa giá trị chuẩn hóa vào tham số ngầm; hợp lệ. |

Không cần viết phép gán field trong compact constructor, kể cả khi record có nhiều component.

## 5. Ví dụ thực tế: xác thực và chuẩn hóa dữ liệu

Compact constructor rất phù hợp khi cần kiểm tra dữ liệu và chuẩn hóa giá trị trước khi lưu.

```java
import java.util.Objects;

public record Customer(String name, int age) {

    public Customer {
        name = Objects.requireNonNull(name, "name").strip();

        if (name.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }
    }
}
```

Sử dụng:

```java
Customer customer = new Customer("  Lan  ", 30);

System.out.println(customer.name()); // Lan
System.out.println(customer.age());  // 30

// new Customer("   ", 30); // IllegalArgumentException
// new Customer("Lan", -1);  // IllegalArgumentException
// new Customer(null, 30);   // NullPointerException
```

Trong thân constructor:

- `name` là tham số ngầm, được kiểm tra null bằng `Objects.requireNonNull`.
- `strip()` loại bỏ khoảng trắng ở đầu và cuối chuỗi.
- Tham số `name` được gán lại bằng giá trị đã chuẩn hóa.
- `age` được kiểm tra nhưng không cần gán lại.
- Khi thân constructor kết thúc bình thường, compiler gán `name` và `age` vào các field tương ứng.

Bạn không cần tự gán `this.name` hoặc `this.age`.

## 6. Thân constructor chạy trước, kể cả khi có nhiều bước xử lý

Các câu lệnh trong thân compact constructor chạy theo thứ tự viết. Các phép gán field ngầm chỉ diễn ra sau khi toàn bộ thân constructor hoàn tất bình thường.

Ví dụ:

```java
import java.util.Locale;

public record Booking(String code, int seats) {

    public Booking {
        if (code == null) {
            throw new IllegalArgumentException("code is required");
        }

        code = code.strip();

        if (code.isEmpty()) {
            throw new IllegalArgumentException("code must not be blank");
        }

        if (seats <= 0) {
            throw new IllegalArgumentException("seats must be positive");
        }

        code = code.toUpperCase(Locale.ROOT);
    }
}
```

Khi gọi `new Booking("  bk-01 ", 2)`:

1. Tham số `code` nhận `"  bk-01 "` và `seats` nhận `2`.
2. Kiểm tra `code` không null.
3. Gán lại `code` thành `"bk-01"`.
4. Kiểm tra chuỗi không rỗng.
5. Kiểm tra `seats` lớn hơn 0.
6. Gán lại `code` thành `"BK-01"`.
7. Kết thúc thân constructor.
8. Compiler gán `this.code = code` và `this.seats = seats`.

Nếu một điều kiện không hợp lệ và constructor ném ngoại lệ, quá trình không đi tới bước gán field ngầm. Đối tượng không được tạo thành công.

Điều này giúp ta đặt toàn bộ quy tắc xác thực trước khi dữ liệu được lưu vào component field.

## 7. Nếu thân constructor kết thúc bất thường thì sao?

Các phép gán ngầm chỉ được thực hiện khi thân compact constructor kết thúc bình thường. Nếu thân ném ngoại lệ, các phép gán ở cuối không được thực hiện.

Ví dụ:

```java
public record PositiveNumber(int value) {
    public PositiveNumber {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
    }
}
```

Với `new PositiveNumber(10)`, thân constructor kết thúc bình thường và compiler gán `10` vào field `value`.

Với `new PositiveNumber(0)`, constructor ném `IllegalArgumentException`. Không có đối tượng `PositiveNumber` được tạo thành công và không có bước gán field ngầm sau thân constructor.

Điều này khác với constructor dạng đầy đủ, nơi người viết phải thể hiện trực tiếp các lệnh gán field. Trong compact constructor, việc gán được thực hiện tự động khi thân hoàn tất bình thường.

## 8. Dùng biến cục bộ để xử lý logic phức tạp

Không phải mọi phép xử lý đều cần gán lại tham số ngay lập tức. Bạn có thể tạo biến cục bộ, thực hiện nhiều bước rồi gán kết quả cuối cùng vào tham số ngầm.

```java
import java.util.Locale;
import java.util.Objects;

public record EmailAddress(String value) {

    public EmailAddress {
        String normalized = Objects.requireNonNull(value, "value")
                .strip()
                .toLowerCase(Locale.ROOT);

        if (!normalized.contains("@")) {
            throw new IllegalArgumentException("invalid email address");
        }

        value = normalized;
    }
}
```

Cách này giúp tách rõ:

- `normalized` là biến cục bộ phục vụ xử lý.
- `value` là tham số ngầm sẽ được dùng trong phép gán field cuối cùng.
- Compiler gán field `this.value` sau khi thân constructor kết thúc bình thường.

Nếu quy tắc chuẩn hóa phụ thuộc ngôn ngữ hoặc locale, hãy chọn locale tường minh phù hợp với hợp đồng dữ liệu. Ví dụ với mã định danh kỹ thuật cần chuyển chữ thường ổn định, có thể dùng `toLowerCase(Locale.ROOT)`.

## 9. Component có kiểu tham chiếu và sao chép phòng vệ

Compact constructor cũng hữu ích khi record chứa collection hoặc đối tượng có thể thay đổi. Field component là `final` nhưng điều đó chỉ cố định tham chiếu; nó không tự làm cho đối tượng được tham chiếu trở nên bất biến.

Ví dụ:

```java
import java.util.List;
import java.util.Objects;

public record SearchRequest(String query, List<String> tags) {

    public SearchRequest {
        query = Objects.requireNonNull(query, "query").strip();
        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));

        if (query.isEmpty()) {
            throw new IllegalArgumentException("query is required");
        }
    }
}
```

Sử dụng:

```java
import java.util.ArrayList;
import java.util.List;

List<String> inputTags = new ArrayList<>(List.of("java", "record"));

SearchRequest request = new SearchRequest("  compact constructor  ", inputTags);

inputTags.add("changed");

System.out.println(request.query()); // compact constructor
System.out.println(request.tags());  // [java, record]

// request.tags().add("new");
// UnsupportedOperationException
```

Ở đây:

- `query` được chuẩn hóa bằng `strip()`.
- `tags` được kiểm tra null và sao chép bằng `List.copyOf`.
- Hai tham số ngầm đã mang giá trị cuối cùng trước khi compiler gán component field.
- Bên gọi không thể thay đổi cấu trúc danh sách đã lưu trong record thông qua tham chiếu danh sách ban đầu hoặc accessor.

`List.copyOf` tạo danh sách không thể thay đổi qua các thao tác sửa danh sách thông thường, nhưng đây là sao chép nông. Nếu phần tử bên trong là đối tượng mutable, trạng thái của từng phần tử vẫn có thể thay đổi. Cần thiết kế thêm nếu yêu cầu bất biến sâu.

## 10. Không sử dụng field/accessor như thể phép gán đã xảy ra

Trong thân compact constructor, tham số ngầm là nguồn dữ liệu cần dùng để xác thực và chuẩn hóa. Component field chỉ được gán sau khi thân constructor kết thúc bình thường.

Vì vậy, khi cần xử lý giá trị đầu vào, hãy dùng trực tiếp tham số:

```java
public record Label(String value) {
    public Label {
        value = value.strip();

        if (value.length() > 40) {
            throw new IllegalArgumentException("label is too long");
        }
    }
}
```

Không viết logic dựa trên giả định rằng field `this.value` đã nhận giá trị mới ngay sau lệnh `value = value.strip()`. Lệnh này chỉ cập nhật tham số. Phép gán field ngầm vẫn nằm ở cuối thân constructor.

Một nguyên tắc an toàn khác là không đưa `this` ra bên ngoài hoặc để đối tượng bị quan sát trước khi quá trình khởi tạo hoàn tất. Ví dụ, tránh chuyển `this` cho callback hoặc đăng ký nó vào một nơi lưu trữ trong thân compact constructor. Tại thời điểm đó các phép gán component field ngầm chưa diễn ra; bên nhận có thể quan sát một đối tượng chưa hoàn tất khởi tạo.

## 11. Các giới hạn cú pháp của compact constructor

Compact constructor có cú pháp riêng và không phải là một block tùy ý. Một số quy tắc quan trọng:

- Không khai báo danh sách tham số sau tên constructor; tham số được suy ra từ record header.
- Không tự khai báo lại tham số có cùng tên với component trong thân constructor.
- Không gán trực tiếp component field bằng `this.component = ...`.
- Không viết câu lệnh gọi constructor tường minh `this(...)` hoặc `super(...)` trong thân compact constructor.
- Không dùng câu lệnh `return` để kết thúc compact constructor.
- Có thể ném ngoại lệ nếu dữ liệu không hợp lệ; khi constructor kết thúc bất thường thì các phép gán field ngầm ở cuối không được thực hiện.

Ví dụ sai do có `return`:

```java
// SAI: compact constructor không được chứa return statement.
public record Code(String value) {
    public Code {
        if (value == null) {
            return;
        }
    }
}
```

Hãy ném ngoại lệ nếu đầu vào không hợp lệ:

```java
public record Code(String value) {
    public Code {
        if (value == null) {
            throw new IllegalArgumentException("value is required");
        }
    }
}
```

Nếu cần điều khiển khởi tạo bằng cách ủy quyền từ constructor nạp chồng, hãy khai báo constructor nạp chồng riêng và gọi canonical constructor bằng `this(...)` từ constructor nạp chồng đó. Không đặt lời gọi này bên trong compact constructor.

## 12. So sánh compact và canonical constructor dạng đầy đủ

Hai dạng dưới đây đều là canonical constructor, nhưng cách gán field khác nhau:

| Tiêu chí | Canonical dạng đầy đủ | Compact canonical |
| --- | --- | --- |
| Danh sách tham số | Khai báo tường minh | Suy ra từ record header |
| Tham số | Tham số viết trong chữ ký | Tham số ngầm theo component |
| Kiểm tra dữ liệu | Có | Có |
| Chuẩn hóa dữ liệu | Có thể gán giá trị đã xử lý vào field | Gán lại tham số ngầm |
| Thời điểm gán field | Theo các câu lệnh gán tường minh trong thân constructor | Compiler gán sau khi thân kết thúc bình thường |
| Gán field | Phải gán đầy đủ bằng `this.field = ...` | Không được tự gán field |
| Phù hợp | Cần kiểm soát rõ từng phép gán field | Chủ yếu kiểm tra hoặc chuẩn hóa component |

Ví dụ cùng một mục tiêu xác thực:

```java
// Dạng đầy đủ
public record Age(int value) {
    public Age(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("value must not be negative");
        }
        this.value = value;
    }
}
```

```java
// Dạng compact: dùng thay cho ví dụ phía trên
public record Age(int value) {
    public Age {
        if (value < 0) {
            throw new IllegalArgumentException("value must not be negative");
        }
    }
}
```

Hai khai báo trên là hai phiên bản thay thế nhau. Dạng compact ngắn hơn vì compiler đảm nhiệm việc gán field sau phần xác thực.

## 13. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Viết `this.value = value.strip()` | Compact constructor không cho phép gán trực tiếp component field. | Gán lại tham số `value = value.strip()`. |
| Nghĩ field được gán ngay khi vào thân constructor | Field chỉ được gán ngầm sau khi thân constructor kết thúc bình thường. | Dùng tham số ngầm trong toàn bộ phần xử lý. |
| Chỉ kiểm tra tham số nhưng quên rằng compiler gán field | Không phải lỗi; đây chính là hành vi tự động của compact constructor. | Không thêm lệnh gán field; bảo đảm tham số mang giá trị cuối cùng mong muốn. |
| Gọi accessor để lấy giá trị đã chuẩn hóa trong thân constructor | Phép gán field chưa diễn ra ở thời điểm đó. | Dùng biến tham số đã được gán lại. |
| Đưa `this` cho callback trong thân constructor | Có thể làm lộ đối tượng trước khi component field được gán. | Chỉ công bố đối tượng sau khi constructor hoàn tất. |
| Viết `return;` | Compact constructor không cho phép return statement. | Để thân kết thúc bình thường hoặc ném ngoại lệ. |
| Gọi `this(...)` bên trong compact constructor | Compact constructor không chứa explicit constructor invocation. | Đặt ủy quyền trong constructor nạp chồng riêng. |
| Nghĩ field `final List` khiến danh sách bất biến | `final` chỉ cố định tham chiếu, không cố định nội dung collection. | Dùng sao chép phòng vệ phù hợp, ví dụ `List.copyOf`. |

## 14. Bài tập tự luyện

### Bài 1: Xác định giá trị được lưu

Cho record:

```java
public record ProductCode(String value) {
    public ProductCode {
        value = value.strip().toUpperCase();
    }
}
```

Khi tạo:

```java
ProductCode code = new ProductCode("  ab-10  ");
```

Giá trị của `code.value()` là gì?

**Đáp án:** `AB-10`. Thân compact constructor chuẩn hóa tham số `value` trước; sau đó compiler gán giá trị cuối cùng của tham số vào field.

### Bài 2: Sửa lỗi gán field

```java
public record Score(int value) {
    public Score {
        this.value = Math.max(0, value);
    }
}
```

**Đáp án:** Gán lại tham số thay vì field:

```java
public record Score(int value) {
    public Score {
        value = Math.max(0, value);
    }
}
```

Sau khi thân constructor kết thúc, compiler gán giá trị đã điều chỉnh vào component field `value`.

### Bài 3: Khi nào field được gán?

Cho đoạn mã:

```java
public record UserName(String value) {
    public UserName {
        System.out.println("validate");
        value = value.strip();
        System.out.println("normalized");
    }
}
```

Thứ tự nào đúng?

- A. Compiler gán field trước khi chạy `System.out.println("validate")`.
- B. Compiler gán field ngay sau `value = value.strip()`.
- C. Compiler gán field sau khi cả thân compact constructor kết thúc bình thường.

**Đáp án:** C. Tất cả câu lệnh trong thân được thực thi trước; các phép gán field ngầm diễn ra ở cuối khi thân kết thúc bình thường.

### Bài 4: Vì sao không thể dùng return?

```java
record RequiredText(String value) {
    RequiredText {
        if (value == null) {
            return;
        }
    }
}
```

**Đáp án:** Compact constructor không được chứa return statement. Nếu dữ liệu không hợp lệ, hãy ném ngoại lệ để constructor kết thúc bất thường và không tạo ra đối tượng thiếu dữ liệu.

### Bài 5: Sao chép danh sách

Viết compact constructor cho `record Tags(List<String> values)` để từ chối null và lưu một bản sao danh sách không thể sửa đổi.

**Đáp án tham khảo:**

```java
import java.util.List;
import java.util.Objects;

public record Tags(List<String> values) {
    public Tags {
        values = List.copyOf(
                Objects.requireNonNull(values, "values")
        );
    }
}
```

Compiler sẽ gán bản sao được lưu trong tham số `values` vào component field sau khi thân constructor kết thúc bình thường.

## Ghi nhớ

Compact constructor là canonical constructor có danh sách tham số được suy ra từ record header. Thân constructor chạy trước; bạn có thể kiểm tra và gán lại các tham số ngầm để chuẩn hóa dữ liệu. Khi thân kết thúc bình thường, compiler mới gán các giá trị cuối cùng của tham số vào component field theo thứ tự khai báo trong header. Vì vậy, không viết `this.component = ...` trong compact constructor và không dựa vào component field như thể chúng đã được gán ngay trong thân. Nếu xác thực thất bại, hãy ném ngoại lệ; các phép gán ngầm sẽ không diễn ra.

## Tài liệu tham khảo

- [Java Language Specification — `8.10.4.2, Compact Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4.2).
- [Java Language Specification — `8.10.4, Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4).
- [JEP 395 — Records (được hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
