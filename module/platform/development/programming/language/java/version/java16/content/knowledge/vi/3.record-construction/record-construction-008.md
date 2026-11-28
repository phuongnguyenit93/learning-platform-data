# Tránh đọc accessor trước khi compact constructor hoàn tất

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — tìm hiểu những cải tiến từ Java 16 vẫn còn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này giải thích lỗi gọi accessor khi compact constructor vẫn đang chạy và component field chưa được gán.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt tham số ngầm với component field trong compact constructor.
- Giải thích vì sao accessor được gọi quá sớm có thể trả về `null`, `0` hoặc `false`.
- Nhận diện lỗi khi gọi accessor hoặc phương thức instance phụ thuộc component trước khi constructor hoàn tất.
- Dùng tham số ngầm để kiểm tra, chuẩn hóa và so sánh dữ liệu.
- Tránh gọi `toString()`, `hashCode()` hoặc công bố `this` khi record chưa khởi tạo xong.
- Tổ chức logic phức tạp bằng helper `static` hoặc canonical constructor dạng đầy đủ.

## 1. Vấn đề: accessor chưa phản ánh giá trị đầu vào

Xét record:

```java
public record Customer(String name, int age) {
    public Customer {
        name = name.strip();

        System.out.println(name);   // An
        System.out.println(name()); // null
        System.out.println(age());  // 0
    }
}
```

Khi gọi:

```java
new Customer("  An  ", 28);
```

Bạn có thể nghĩ `name()` trả về `"An"` và `age()` trả về `28`. Nhưng trong thân compact constructor, accessor được compiler sinh tự động vẫn có thể trả về `null` và `0`.

Lý do: `name` và `age` là **tham số ngầm** của compact constructor. Accessor `name()` và `age()` đọc **component field** của đối tượng. Compiler chỉ gán các field đó sau khi toàn bộ thân compact constructor kết thúc bình thường.

Vì vậy, giá trị tham số và giá trị field chưa giống nhau trong thời gian thân constructor đang chạy.

Java không tự chuyển lời gọi accessor thành việc đọc tham số ngầm. Lời gọi `name()` là một method invocation bình thường và có thể biên dịch thành công; accessor được sinh tự động vẫn đọc field. Vì thế lỗi thường chỉ bộc lộ khi chương trình chạy.

## 2. Trình tự khởi tạo

Với khai báo:

```java
public record Customer(String name, int age) {
    public Customer {
        name = name.strip();
        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }
    }
}
```

Quá trình khởi tạo diễn ra theo trình tự:

1. Java nhận đối số và khởi tạo các tham số ngầm `name`, `age`.
2. Thân compact constructor bắt đầu chạy.
3. Các câu lệnh trong thân kiểm tra hoặc gán lại tham số.
4. Nếu thân kết thúc bình thường, compiler gán giá trị cuối cùng của từng tham số vào component field tương ứng, theo thứ tự khai báo trong record header.
5. Sau khi constructor hoàn tất, accessor đọc các field đã được gán.

Ví dụ, sau bước 3, tham số `name` có thể là `"An"` trong khi field `this.name` vẫn chưa nhận giá trị đó. Khi bước 4 diễn ra, field mới nhận `"An"`.

Đây là hành vi được quy định trong Java Language Specification, mục `8.10.4.2`. Compact constructor được thiết kế để phần thân tập trung xác thực hoặc chuẩn hóa tham số; compiler đảm nhiệm việc gán component field sau đó.

## 3. Vì sao accessor trả về giá trị mặc định?

Mỗi record component tương ứng với một field. Trước khi được gán, field có giá trị mặc định theo quy tắc của Java:

| Kiểu component | Giá trị mặc định trước khi gán |
| --- | --- |
| Kiểu tham chiếu, ví dụ `String`, `List` | `null` |
| `byte`, `short`, `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `char` | `'\u0000'` |
| `boolean` | `false` |

Accessor được compiler sinh tự động trả về component field tương ứng. Do field chưa nhận giá trị từ tham số ngầm, accessor quan sát giá trị mặc định của field.

Ví dụ:

```java
public record Defaults(String text, int count, boolean enabled) {
    public Defaults {
        System.out.println(text());    // null
        System.out.println(count());   // 0
        System.out.println(enabled()); // false
    }
}
```

Lời gọi `new Defaults("ready", 5, true)` không làm cho các accessor trả về dữ liệu đầu vào ngay trong thân compact constructor. Chúng chỉ đọc field sau khi field được compiler gán ở cuối thân.

## 4. Lỗi thường gặp: dùng accessor để xác thực

Ví dụ sau có lỗi:

```java
import java.util.Objects;

public record UserName(String value) {
    public UserName {
        value = Objects.requireNonNull(value, "value").strip();

        if (value().isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
```

Lệnh `value().isEmpty()` gọi accessor `value()`. Accessor được sinh tự động đọc field `this.value`, nhưng field chưa được compiler gán. Kết quả `value()` là `null`, do đó lời gọi `isEmpty()` ném `NullPointerException`.

Cách sửa là dùng tham số ngầm `value`:

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

Ở đây, `value` là tham số đã được kiểm tra null và chuẩn hóa. Điều kiện `value.isEmpty()` kiểm tra chính giá trị sẽ được compiler gán vào field khi thân constructor kết thúc bình thường.

**Quy tắc thực hành:** trong compact constructor, hãy dùng tên component trực tiếp để đọc và xử lý giá trị. Không gọi accessor của chính record để lấy dữ liệu đầu vào.

## 5. Phương thức instance cũng có thể đọc trạng thái chưa hoàn chỉnh

Vấn đề không giới hạn ở accessor. Bất kỳ phương thức instance nào đọc component field đều có thể quan sát giá trị mặc định nếu được gọi trong thân compact constructor.

Ví dụ:

```java
public record Account(String owner, int balance) {
    public Account {
        if (isOverdrawn()) {
            throw new IllegalArgumentException("balance must not be negative");
        }
    }

    public boolean isOverdrawn() {
        return balance() < 0;
    }
}
```

`isOverdrawn()` gọi `balance()`. Trong thân compact constructor, accessor có thể trả về `0` dù tham số `balance` là số âm. Vì thế điều kiện có thể không phát hiện dữ liệu sai.

Sửa bằng cách kiểm tra trực tiếp tham số:

```java
public record Account(String owner, int balance) {
    public Account {
        if (balance < 0) {
            throw new IllegalArgumentException("balance must not be negative");
        }
    }

    public boolean isOverdrawn() {
        return balance() < 0;
    }
}
```

Sau khi đối tượng được tạo xong, phương thức `isOverdrawn()` hoạt động bình thường vì field đã được gán. Chỉ cần tránh gọi nó trong quá trình compact constructor đang chạy.

## 6. Tách logic sang helper static

Khi quy tắc kiểm tra phức tạp, có thể tách ra helper `static` và truyền các tham số cần thiết:

```java
public record DateRange(
        java.time.LocalDate start,
        java.time.LocalDate end
) {
    public DateRange {
        validate(start, end);
    }

    private static void validate(
            java.time.LocalDate start,
            java.time.LocalDate end
    ) {
        java.util.Objects.requireNonNull(start, "start");
        java.util.Objects.requireNonNull(end, "end");

        if (start.isAfter(end)) {
            throw new IllegalArgumentException(
                    "start must not be after end"
            );
        }
    }
}
```

`validate(start, end)` là phương thức static. Nó nhận dữ liệu từ tham số ngầm và không cần đọc component field thông qua `this` hoặc accessor.

Cách tổ chức này giúp:

- Không phụ thuộc trạng thái instance chưa khởi tạo.
- Kiểm thử logic xác thực độc lập.
- Tái sử dụng quy tắc ở nơi khác.
- Giữ thân compact constructor ngắn và rõ ràng.

Nếu helper cần chuẩn hóa dữ liệu và trả về kết quả, hãy gán kết quả trở lại tham số ngầm:

```java
public record ProductCode(String value) {
    public ProductCode {
        value = normalize(value);
    }

    private static String normalize(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value is required");
        }

        String normalized = value.strip().toUpperCase(java.util.Locale.ROOT);

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }

        return normalized;
    }
}
```

Sau khi `normalize(value)` trả về, tham số `value` mang giá trị chuẩn hóa. Compiler dùng giá trị cuối cùng đó để gán field ở cuối constructor.

## 7. Không gọi các phương thức biểu diễn đối tượng quá sớm

Record cung cấp các phương thức `toString()`, `equals()` và `hashCode()` dựa trên component field. Các triển khai được sinh tự động sử dụng trực tiếp giá trị field; chúng không thay thế bằng tham số ngầm trong compact constructor.

Ví dụ:

```java
public record Message(String text, int priority) {
    public Message {
        text = text.strip();

        System.out.println(this);
        System.out.println(hashCode());
    }
}
```

Trong thân constructor, `toString()` có thể biểu diễn `text=null` và `priority=0`. `hashCode()` cũng được tính từ các field chưa nhận giá trị đầu vào.

Vì vậy, không nên dùng các phương thức này để log hoặc kiểm tra trạng thái record trong compact constructor. Nếu cần ghi log dữ liệu đầu vào, hãy log tham số:

```java
public record Message(String text, int priority) {
    public Message {
        text = text.strip();

        System.out.println(
                "text=" + text + ", priority=" + priority
        );
    }
}
```

Cách này thể hiện đúng dữ liệu hiện có mà không đọc component field trước khi khởi tạo xong.

## 8. Tránh công bố this trước khi constructor hoàn tất

Một trường hợp rủi ro khác là công bố tham chiếu `this` trước khi constructor hoàn tất:

```java
// Không nên: registry có thể giữ lại đối tượng chưa khởi tạo xong.
public record EventConfig(String topic) {
    public EventConfig {
        EventRegistry.register(this);
        topic = topic.strip();
    }
}
```

Nếu `register` lưu đối tượng hoặc chuyển nó cho callback chạy ngay, mã bên ngoài có thể gọi accessor trong lúc field vẫn mang giá trị mặc định.

Hãy hoàn tất việc tạo record trước rồi mới đăng ký:

```java
public record EventConfig(String topic) {
    public EventConfig {
        topic = java.util.Objects.requireNonNull(topic, "topic").strip();

        if (topic.isEmpty()) {
            throw new IllegalArgumentException("topic is required");
        }
    }
}

// Tạo xong rồi mới công bố đối tượng.
EventConfig config = new EventConfig("orders");
EventRegistry.register(config);
```

Đây là nguyên tắc chung về an toàn khởi tạo: không để đối tượng bị quan sát từ bên ngoài trước khi trạng thái của nó hoàn chỉnh.

## 9. Khi nào canonical constructor đầy đủ có ích?

Compact constructor trì hoãn việc gán field đến cuối thân. Canonical constructor dạng đầy đủ cho phép bạn kiểm soát thứ tự gán:

```java
public record Rectangle(int width, int height) {
    public Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("dimensions must be positive");
        }

        this.width = width;
        this.height = height;

        // Field đã được gán, accessor đọc được giá trị component.
        validateArea();
    }

    private void validateArea() {
        if ((long) width() * height() > 1_000_000L) {
            throw new IllegalArgumentException("area is too large");
        }
    }
}
```

Trong ví dụ này, cả hai field được gán trước khi `validateArea()` gọi accessor. Nếu kiểm tra thất bại, constructor vẫn ném ngoại lệ và đối tượng không được trả về cho bên gọi.

Tuy nhiên, nếu chỉ cần kiểm tra đầu vào, cách đơn giản hơn vẫn là dùng trực tiếp tham số constructor hoặc helper static. Đừng chuyển sang dạng đầy đủ chỉ để gọi accessor khi một biểu thức trên tham số đã đủ rõ.

## 10. So sánh thời điểm đọc tham số và accessor

| Vị trí trong compact constructor | `name` | `name()` |
| --- | --- | --- |
| Ngay khi thân bắt đầu | Giá trị đối số được truyền vào | Đọc field chưa được gán |
| Sau `name = name.strip()` | Giá trị đã chuẩn hóa | Vẫn đọc field chưa được gán |
| Sau khi thân kết thúc bình thường và compiler gán field | Thân constructor đã kết thúc | Accessor ở mã bên ngoài đọc giá trị đã lưu |
| Nếu thân ném ngoại lệ | Có thể đã được kiểm tra/biến đổi trước khi lỗi | Không có đối tượng được tạo thành công để bên gọi truy cập |

Bảng này áp dụng cho accessor được sinh tự động. Nếu bạn khai báo accessor tường minh với logic riêng, kết quả của phương thức phụ thuộc vào phần triển khai đó; nhưng vẫn không nên gọi nó để thay thế tham số ngầm trong compact constructor.

## 11. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `name()` trong compact constructor | Có thể nhận `null` thay vì tham số đầu vào. | Dùng `name`. |
| Gọi `age()` để kiểm tra giới hạn | Có thể nhận `0` thay vì tuổi được truyền. | Dùng `age`. |
| Gọi phương thức instance đọc accessor | Phương thức có thể xử lý giá trị mặc định của field. | Dùng helper static nhận tham số. |
| Log `this` hoặc gọi `toString()` | Log có thể chứa component mặc định. | Log trực tiếp tham số. |
| Dùng `hashCode()` trước khi field được gán | Hash code được tính từ trạng thái chưa hoàn chỉnh. | Chỉ dùng sau khi constructor hoàn tất. |
| Đưa `this` vào registry hoặc callback | Mã khác có thể quan sát đối tượng chưa hoàn chỉnh. | Công bố đối tượng sau khi tạo xong. |
| Cho rằng tham số và accessor là cùng một biến | Nhầm giá trị tham số với giá trị field. | Phân biệt tên component với phương thức accessor. |
| Dùng compact constructor nhưng cần điều khiển thứ tự gán field | Compact constructor không cho phép tự gán field. | Cân nhắc canonical constructor dạng đầy đủ. |

## 12. Bài tập tự luyện

### Bài 1: Dự đoán kết quả

Cho record:

```java
public record User(String name, int age) {
    public User {
        name = name.strip();

        System.out.println(name);
        System.out.println(name());
        System.out.println(age());
    }
}
```

Khi gọi `new User("  Mai  ", 21)`, ba dòng được in ra là gì?

**Đáp án:** `Mai`, `null`, `0`. Dòng đầu đọc tham số đã chuẩn hóa; hai dòng sau gọi accessor đọc component field trước khi compiler gán.

### Bài 2: Sửa lỗi validation

```java
public record Email(String value) {
    public Email {
        value = value.strip();

        if (value().isEmpty()) {
            throw new IllegalArgumentException("email is required");
        }
    }
}
```

**Đáp án:** Thay `value().isEmpty()` bằng `value.isEmpty()`. Tham số `value` mới là giá trị cần xác thực trong thân compact constructor.

### Bài 3: Tách helper

Viết compact constructor cho `record Range(int min, int max)` và dùng helper static để từ chối `min > max`.

**Đáp án tham khảo:**

```java
public record Range(int min, int max) {
    public Range {
        validate(min, max);
    }

    private static void validate(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min must not exceed max");
        }
    }
}
```

Helper nhận trực tiếp tham số ngầm và không đọc accessor.

### Bài 4: Khi nào gọi accessor được?

Trong canonical constructor dạng đầy đủ, sau khi đã gán mọi component field, có thể gọi accessor để thực hiện một kiểm tra bổ sung không?

**Đáp án:** Có thể, vì field đã được gán trước thời điểm gọi. Dù vậy, hãy ưu tiên dùng tham số hoặc helper phù hợp nếu cách đó đơn giản hơn và không cần phụ thuộc trạng thái instance.

## Ghi nhớ

Trong compact constructor, tên component là tham số ngầm còn accessor là phương thức đọc component field. Compiler chỉ gán field sau khi thân constructor kết thúc bình thường. Vì vậy, gọi accessor hoặc phương thức instance phụ thuộc field quá sớm có thể trả về `null`, `0` hoặc `false` thay vì dữ liệu đầu vào. Hãy dùng tham số ngầm để xác thực và chuẩn hóa, tách logic phức tạp sang helper static, tránh log hoặc công bố `this` trước khi khởi tạo xong, và chỉ dùng accessor sau khi các field đã được gán.

## Tài liệu tham khảo

- [Java Language Specification — Java SE 16, `8.10.4.2 Compact Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se16/html/jls-8.html#jls-8.10.4.2).
- [Java Language Specification — Java SE 16, `4.12.5 Initial Values of Variables](https://docs.oracle.com/javase/specs/jls/se16/html/jls-4.html#jls-4.12.5).
- [Java Language Specification — Java SE 26, `8.10.4.2 Compact Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10.4.2).
- [Error Prone — RecordAccessorInCompactConstructor](https://errorprone.info/bugpattern/RecordAccessorInCompactConstructor).
- [JEP 395 — Records (được hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
