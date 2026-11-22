# Kiểm tra, chuẩn hóa tham số trong constructor của Record — Java 17

Trong Java 17, `record` là cách khai báo một kiểu dữ liệu dùng để biểu diễn một tập giá trị cố định. Ví dụ, `record User(String name, int age)` có hai **record component** là `name` và `age`. Java tự tạo các trường `private final` tương ứng, accessor `name()` và `age()`, cùng các phương thức `equals()`, `hashCode()`, `toString()`.

Tuy nhiên, **`final` không có nghĩa dữ liệu đầu vào luôn hợp lệ**. Mã sau vẫn có thể tạo trạng thái vô nghĩa nếu không kiểm tra tham số:

```java
record User(String name, int age) {}

User a = new User(null, -5);
User b = new User("   ", 20);
```

Đối với record mang ràng buộc nghiệp vụ, constructor là nơi thích hợp để **kiểm tra (validation)** và **chuẩn hóa (normalization)** tham số trước khi lưu vào component. Nhờ vậy, mọi lời gọi constructor công khai đều tuân theo cùng một quy tắc, thay vì trông chờ người gọi tự xử lý dữ liệu.

Bài học tập trung vào cú pháp **canonical constructor** và **compact canonical constructor**, cách dùng hai dạng này để bảo vệ bất biến dữ liệu, cách xử lý collection và những lỗi dễ mắc trong Java 17.

## 1. Canonical constructor của record hoạt động thế nào?

Xét một record đơn giản:

```java
public record Student(String name, int age) {
}
```

Dòng khai báo trên xác định các component theo thứ tự `String name`, `int age`. Khi không tự khai báo canonical constructor, Java cung cấp một constructor tương ứng với danh sách component:

```java
new Student("Lan", 18);
```

Có thể hình dung tác dụng của constructor do trình biên dịch tạo ra là nhận tham số `name` và `age` rồi khởi tạo hai trường cuối cùng của record. Bản thân record cũng tự có các accessor:

```java
Student s = new Student("Lan", 18);

System.out.println(s.name()); // Lan
System.out.println(s.age());  // 18
```

Nếu muốn loại bỏ tên trống hoặc tuổi âm, ta **tự khai báo canonical constructor** để đưa các điều kiện vào quá trình khởi tạo.

Trong Java 17 có hai cách viết chính:

| Dạng | Cú pháp | Cách gán các component |
| --- | --- | --- |
| **Compact canonical constructor** | `public Student { ... }` | Trình biên dịch tự gán các tham số component vào trường tương ứng **sau khi thân constructor hoàn tất bình thường**. |
| **Explicit canonical constructor** | `public Student(String name, int age) { ... }` | Lập trình viên phải tự gán tất cả các trường component, ví dụ `this.name = ...`. |

Với yêu cầu kiểm tra và chuẩn hóa giá trị, compact constructor thường ngắn gọn và dễ đọc hơn.

## 2. Kiểm tra tham số với compact constructor

Compact constructor có cùng tên với record, **không viết danh sách tham số** và **không có dấu ngoặc `()`** sau tên:

```java
public record Student(String name, int age) {

    public Student {
        if (name == null) {
            throw new IllegalArgumentException("name không được null");
        }

        if (name.isBlank()) {
            throw new IllegalArgumentException("name không được trống");
        }

        if (age < 0 || age > 150) {
            throw new IllegalArgumentException("age phải từ 0 đến 150");
        }
    }
}
```

Trong thân compact constructor, các biến `name` và `age` là tham số được suy ra từ danh sách component. Java tự thực hiện phép gán sang các trường của record khi kết thúc thân constructor mà không phát sinh ngoại lệ.

Ví dụ gọi:

```java
Student valid = new Student("Mai", 21);
System.out.println(valid); // Student[name=Mai, age=21]

Student invalid = new Student("  ", 21);
// Ném IllegalArgumentException khi kiểm tra name.
```

**Lưu ý:** Điều kiện tuổi tối đa `150` chỉ là ràng buộc minh họa. Ứng dụng thực tế cần xác định quy tắc dựa trên miền dữ liệu của chính ứng dụng.

### Dùng `Objects.requireNonNull` cho tham số bắt buộc

Thay vì tự viết `if (value == null)` cho từng component, có thể sử dụng `Objects.requireNonNull`:

```java
import java.util.Objects;

public record Student(String name, int age) {

    public Student {
        Objects.requireNonNull(name, "name không được null");

        if (name.isBlank()) {
            throw new IllegalArgumentException("name không được trống");
        }

        if (age < 0) {
            throw new IllegalArgumentException("age không được âm");
        }
    }
}
```

`Objects.requireNonNull(name, "...")` ném `NullPointerException` với thông điệp cụ thể nếu `name == null`. Nếu không `null`, phương thức trả lại chính tham chiếu `name`. Cả hai kiểu xử lý `null` đều hợp lệ; hãy thống nhất quy ước ngoại lệ trong dự án.

## 3. Chuẩn hóa tham số trước khi Java gán trường

Kiểm tra nhằm **từ chối** giá trị không hợp lệ. Chuẩn hóa nhằm **biến đổi** một giá trị đầu vào hợp lệ về dạng thống nhất.

Ví dụ, người dùng nhập mã khóa học với khoảng trắng thừa và chữ thường:

```text
"  java-017  "
```

Ứng dụng muốn lưu mã đó thành:

```text
"JAVA-017"
```

Compact constructor cho phép **gán lại tham số component** trước khi phép gán trường tự động diễn ra:

```java
import java.util.Locale;
import java.util.Objects;

public record Course(String code, String title, int durationMinutes) {

    public Course {
        code = Objects.requireNonNull(code, "code không được null")
                      .strip()
                      .toUpperCase(Locale.ROOT);

        title = Objects.requireNonNull(title, "title không được null")
                       .strip();

        if (!code.matches("[A-Z]{2,8}-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "code phải có dạng JAVA-017 hoặc AB-123"
            );
        }

        if (title.isBlank()) {
            throw new IllegalArgumentException("title không được trống");
        }

        if (durationMinutes <= 0) {
            throw new IllegalArgumentException(
                    "durationMinutes phải lớn hơn 0"
            );
        }
    }
}
```

Sử dụng:

```java
Course course = new Course("  java-017  ", "  Học Java 17  ", 90);

System.out.println(course.code());            // JAVA-017
System.out.println(course.title());           // Học Java 17
System.out.println(course.durationMinutes()); // 90
```

Các bước diễn ra khi gọi `new Course(...)`:

```text
Tham số đầu vào
       |
       v
Kiểm tra null
       |
       v
Chuẩn hóa code/title
       |
       v
Kiểm tra định dạng, giá trị, quy tắc nghiệp vụ
       |
       +--- Lỗi ---> Ném ngoại lệ, không tạo record
       |
       v
Kết thúc thân compact constructor
       |
       v
Java gán các tham số đã chuẩn hóa vào component fields
       |
       v
Record hợp lệ được tạo
```

### Vì sao nên dùng `Locale.ROOT` trong ví dụ mã định danh?

Nếu mục tiêu là mã kỹ thuật có quy tắc viết hoa độc lập ngôn ngữ người dùng, `toUpperCase(Locale.ROOT)` tạo kết quả ổn định hơn so với cách chuyển chữ dựa vào locale mặc định của môi trường.

Nhưng **không phải chuỗi nào cũng nên viết hoa hoặc viết thường**. Tên hiển thị, chuỗi phân biệt hoa/thường, mã bí mật và các giá trị có ngữ nghĩa riêng phải được xử lý theo đúng yêu cầu nghiệp vụ. `strip()` cũng chỉ nên dùng khi khoảng trắng đầu/cuối không mang ý nghĩa.

### Thứ tự đúng: kiểm tra null rồi mới xử lý chuỗi

**Sai:**

```java
record Product(String name) {
    public Product {
        name = name.strip(); // Có thể ném NullPointerException không có thông điệp rõ ràng.
    }
}
```

**Đúng:**

```java
import java.util.Objects;

record Product(String name) {
    public Product {
        name = Objects.requireNonNull(name, "name bắt buộc").strip();

        if (name.isBlank()) {
            throw new IllegalArgumentException("name không được trống");
        }
    }
}
```

Ở đây `Objects.requireNonNull(...)` vừa xác nhận tham số vừa trả về chuỗi để gọi `strip()`.

## 4. Phân biệt `strip()`, `trim()` và `isBlank()`

Trong ví dụ Java 17, có ba phương thức thường xuất hiện:

| Phương thức | Công dụng | Điểm cần nhớ |
| --- | --- | --- |
| `strip()` | Loại bỏ khoảng trắng theo quy tắc Unicode của Java ở đầu và cuối chuỗi. | Thường phù hợp với dữ liệu văn bản hiện đại hơn `trim()`. |
| `trim()` | Loại bỏ các ký tự ở hai đầu có giá trị mã không lớn hơn `U+0020`. | Vẫn dùng được, nhưng có tiêu chí loại bỏ khác `strip()`. |
| `isBlank()` | Kiểm tra chuỗi rỗng hoặc chỉ gồm ký tự khoảng trắng theo quy tắc của Java. | Phân biệt chuỗi trống với chuỗi có nội dung. |

Ví dụ:

```java
String raw = "   Java 17   ";

System.out.println(raw.strip());          // Java 17
System.out.println("   ".isBlank());      // true
System.out.println("Java 17".isBlank());  // false
```

Hai lựa chọn chính khi thiết kế constructor:

- **Chuẩn hóa rồi kiểm tra:** `name = name.strip(); if (name.isBlank()) ...`. Cách này phù hợp khi ứng dụng được phép loại bỏ khoảng trắng thừa.
- **Kiểm tra nhưng giữ nguyên giá trị:** `if (name.isBlank()) ...`, không gán lại `name`. Cách này phù hợp khi khoảng trắng của chuỗi có thể mang ý nghĩa.

## 5. Kiểm tra quan hệ giữa nhiều component

Không phải điều kiện hợp lệ nào cũng nằm ở một tham số riêng lẻ. Một record biểu diễn khoảng ngày phải kiểm tra **mối quan hệ** giữa ngày bắt đầu và kết thúc.

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate start, LocalDate end) {

    public DateRange {
        Objects.requireNonNull(start, "start không được null");
        Objects.requireNonNull(end, "end không được null");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "end không được trước start"
            );
        }
    }

    public long inclusiveDays() {
        return java.time.temporal.ChronoUnit.DAYS.between(start, end) + 1;
    }
}
```

Gọi constructor:

```java
DateRange valid = new DateRange(
        LocalDate.of(2026, 1, 10),
        LocalDate.of(2026, 1, 12)
);
System.out.println(valid.inclusiveDays()); // 3

DateRange invalid = new DateRange(
        LocalDate.of(2026, 1, 12),
        LocalDate.of(2026, 1, 10)
);
// Ném IllegalArgumentException.
```

Trong ví dụ này, khoảng ngày **cho phép `start` bằng `end`**. Nếu nghiệp vụ yêu cầu `end` phải ở **sau** `start`, thay điều kiện bằng:

```java
if (!end.isAfter(start)) {
    throw new IllegalArgumentException("end phải sau start");
}
```

Điểm cần nhớ: kiểm tra chéo trong constructor giúp record không có trạng thái như “ngày kết thúc trước ngày bắt đầu”.

## 6. Không gán trực tiếp component field trong compact constructor

Một lỗi thường gặp là vừa khai báo compact constructor vừa cố gán vào trường final của record.

**Sai:**

```java
record Tag(String value) {
    public Tag {
        value = value.strip();
        this.value = value; // LỖI biên dịch
    }
}
```

Trong compact constructor, trình biên dịch chịu trách nhiệm gán trường. Việc tự gán `this.value` ở đây không hợp lệ.

**Đúng:**

```java
import java.util.Objects;

record Tag(String value) {
    public Tag {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isBlank()) {
            throw new IllegalArgumentException("value không được trống");
        }
    }
}
```

Lập trình viên chỉ cần thay đổi **tham số** `value`; lúc kết thúc constructor, Java tự lưu giá trị cuối cùng vào trường tương ứng.

Ngoài ra, không thể khai báo cả **compact canonical constructor** và **explicit canonical constructor** trong cùng một record, vì cả hai đại diện cho cùng một canonical constructor.

## 7. Khi nào dùng explicit canonical constructor?

Có thể viết đầy đủ tham số và tự gán từng trường:

```java
import java.util.Locale;
import java.util.Objects;

public record CourseCode(String value) {

    public CourseCode(String value) {
        String normalized = Objects.requireNonNull(value, "value")
                                   .strip()
                                   .toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z]{2,8}-[0-9]{3}")) {
            throw new IllegalArgumentException("Mã khóa học không hợp lệ");
        }

        this.value = normalized;
    }
}
```

Đây là một **explicit canonical constructor**: danh sách tham số phải tương ứng với các component của record. Mỗi component field phải được gán đúng cách trong constructor này.

Có thể viết tương đương, gọn hơn bằng compact constructor:

```java
import java.util.Locale;
import java.util.Objects;

public record CourseCode(String value) {

    public CourseCode {
        value = Objects.requireNonNull(value, "value")
                       .strip()
                       .toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{2,8}-[0-9]{3}")) {
            throw new IllegalArgumentException("Mã khóa học không hợp lệ");
        }
    }
}
```

Hai phiên bản trên nên được đặt trong **hai tệp hoặc hai lần thử riêng biệt**, vì chúng cùng khai báo record `CourseCode`.

Compact constructor rất phù hợp với validation/normalization. Explicit canonical constructor hữu ích nếu cần kiểm soát trực tiếp việc gán các trường, dù mã thường dài hơn.

### Lưu ý về mức truy cập

Canonical constructor khai báo tường minh phải có mức truy cập ít nhất bằng record. Ví dụ, với `public record CourseCode(...)`, hãy viết `public CourseCode { ... }` hoặc `public CourseCode(...) { ... }`. Viết constructor không có `public` cho một `public record` sẽ gây lỗi quyền truy cập khi biên dịch.

## 8. Constructor bổ sung cũng phải đi qua canonical constructor

Record có thể khai báo các constructor khác canonical constructor để tiện sử dụng. Nhưng một constructor bổ sung phải **ủy quyền tới constructor khác của chính record bằng lời gọi `this(...)` ở đầu thân constructor**; từ đó chuỗi lời gọi cuối cùng phải tới canonical constructor.

```java
import java.util.Objects;

public record Product(String code, int quantity) {

    public Product {
        code = Objects.requireNonNull(code, "code").strip();

        if (code.isBlank()) {
            throw new IllegalArgumentException("code không được trống");
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }
    }

    public Product(String code) {
        this(code, 1); // Chuyển sang canonical constructor.
    }
}
```

Hai cách khởi tạo đều được kiểm tra:

```java
Product p1 = new Product("  A-01  ", 2);
Product p2 = new Product("  B-02  ");

System.out.println(p1); // Product[code=A-01, quantity=2]
System.out.println(p2); // Product[code=B-02, quantity=1]
```

**Sai — constructor bổ sung cố gán trực tiếp component field:**

```java
record Product(String code, int quantity) {

    public Product(String code) {
        this.code = code; // LỖI: constructor này phải ủy quyền qua this(...)
        this.quantity = 1;
    }
}
```

Một static factory method cũng nên gọi canonical constructor (trực tiếp hoặc thông qua constructor bổ sung), thay vì cố tạo record rồi thay đổi giá trị các component:

```java
record Point(int x, int y) {
    public static Point origin() {
        return new Point(0, 0);
    }
}
```

## 9. Với collection, cần tạo bản sao phòng vệ

Các trường component của record là `final`, nghĩa là không thể gán lại tham chiếu trường sau khi khởi tạo. Nhưng nếu một component trỏ tới **đối tượng có thể thay đổi**, nội dung của đối tượng đó vẫn có thể bị sửa từ bên ngoài.

### Ví dụ có nguy cơ thay đổi dữ liệu

```java
import java.util.List;

record Playlist(String name, List<String> songs) {
}

var songs = new java.util.ArrayList<String>();
songs.add("A");
Playlist playlist = new Playlist("Favorites", songs);

songs.add("B");
System.out.println(playlist.songs()); // [A, B]
```

Dù `Playlist` là record, danh sách bên trong thay đổi theo biến `songs` của người gọi.

### Chuẩn hóa collection bằng `List.copyOf`

```java
import java.util.List;
import java.util.Objects;

public record Playlist(String name, List<String> songs) {

    public Playlist {
        name = Objects.requireNonNull(name, "name").strip();

        if (name.isBlank()) {
            throw new IllegalArgumentException("name không được trống");
        }

        songs = List.copyOf(Objects.requireNonNull(songs, "songs"));

        if (songs.isEmpty()) {
            throw new IllegalArgumentException("Playlist cần ít nhất một bài");
        }
    }
}
```

Sử dụng:

```java
import java.util.ArrayList;
import java.util.List;

var original = new ArrayList<String>(List.of("A"));
Playlist playlist = new Playlist("  Favorites  ", original);

original.add("B");

System.out.println(playlist.name());  // Favorites
System.out.println(playlist.songs()); // [A]
```

`List.copyOf(...)` tạo (hoặc tái sử dụng) một danh sách không cho sửa, giữ thứ tự phần tử và **không chấp nhận phần tử `null`**. Nhờ gán lại tham số `songs` trong compact constructor, trường record nhận danh sách phù hợp.

**Giới hạn cần biết:** `List.copyOf` chỉ tạo bản sao ở mức collection; nó **không sao chép sâu** những phần tử là đối tượng có thể thay đổi. Với dữ liệu cần bất biến sâu, hãy dùng các phần tử bất biến hoặc sao chép từng đối tượng theo quy tắc riêng.

### Trường hợp component là mảng

Mảng Java có thể thay đổi dù tham chiếu lưu trong trường `final`. Nếu record bắt buộc có component là mảng, thường phải sao chép khi **nhận vào** và khi **trả ra**:

```java
import java.util.Objects;

public record Bytes(byte[] data) {

    public Bytes {
        data = Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
```

Điều này bảo vệ mảng lưu bên trong khỏi thay đổi trực tiếp. Tuy nhiên, record có component mảng có một điểm cần cân nhắc khác: `equals()`/`hashCode()` tự sinh cho mảng dùng quy tắc so sánh của mảng theo tham chiếu, **không tự so nội dung từng phần tử**. Nếu cần so sánh theo nội dung, hãy thiết kế kiểu bao riêng với `equals()`/`hashCode()` phù hợp hoặc chọn cấu trúc dữ liệu bất biến khác thay vì kỳ vọng record tự xử lý.

## 10. Chọn loại ngoại lệ và chính sách chuẩn hóa

Constructor dùng để thiết lập **bất biến (invariant)** của record. Các lựa chọn validation nên nhất quán với nghiệp vụ và thể hiện rõ với người gọi.

| Tình huống | Phương án thông dụng | Lý do |
| --- | --- | --- |
| Tham số tham chiếu bắt buộc nhưng `null` | `Objects.requireNonNull(value, "value")` | Ném `NullPointerException` với thông điệp xác định đúng component. |
| Số âm, chuỗi rỗng, khoảng giá trị không hợp lệ | `throw new IllegalArgumentException("...")` | Cho biết giá trị được cung cấp vi phạm điều kiện của constructor. |
| Khoảng trắng ngoài tên/mã không có ý nghĩa | `strip()` rồi kiểm tra `isBlank()` | Lưu biểu diễn thống nhất thay vì giữ các biến thể thừa. |
| Mã định danh không phụ thuộc locale | `toUpperCase(Locale.ROOT)` hoặc `toLowerCase(Locale.ROOT)` | Tránh phụ thuộc locale mặc định khi chuẩn hóa mã kỹ thuật. |
| Collection cần hạn chế bị sửa | `List.copyOf`/`Set.copyOf`/`Map.copyOf` khi phù hợp | Tạo collection không cho sửa; vẫn cần xét tính thay đổi của phần tử. |
| Dữ liệu nhập thiếu nhưng có mặc định nghiệp vụ | Constructor bổ sung gọi `this(...)` hoặc factory method | Mọi đường khởi tạo đi qua canonical constructor. |

Không nên “chuẩn hóa” bằng cách âm thầm thay mọi dữ liệu sai thành một giá trị mặc định. Ví dụ, tự biến `quantity = -10` thành `0` có thể che lỗi đầu vào. Nếu yêu cầu nghiệp vụ không quy định rõ phép biến đổi đó, nên ném ngoại lệ.

### Ví dụ với tiền tệ: tránh làm tròn tùy tiện

`BigDecimal` thường được dùng cho các giá trị thập phân cần độ chính xác. Chỉ làm tròn hay thay đổi thang đo (scale) nếu hợp đồng dữ liệu cho phép. Ví dụ dưới đây yêu cầu giá trị không âm và có thể biểu diễn chính xác với hai chữ số thập phân, nên dùng `RoundingMode.UNNECESSARY` để từ chối giá trị cần làm tròn:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public record Money(BigDecimal amount) {

    public Money {
        amount = Objects.requireNonNull(amount, "amount");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount không được âm");
        }

        try {
            amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "amount chỉ được có tối đa 2 chữ số thập phân",
                    ex
            );
        }
    }
}
```

`new Money(new BigDecimal("12.5"))` được lưu với `amount()` là `12.50`; `new Money(new BigDecimal("12.345"))` bị từ chối. Quy tắc hai chữ số thập phân chỉ là **ví dụ nghiệp vụ**, không áp dụng mặc định cho mọi loại số liệu, tỷ giá hay tiền tệ.

## 11. Ví dụ tổng hợp: record có dữ liệu chuẩn hóa và bất biến rõ ràng

Giả sử một hệ thống nhận đơn hàng với mã, số lượng và danh sách nhãn (tag). Yêu cầu:

- `orderId` bắt buộc, loại bỏ khoảng trắng hai đầu và viết hoa theo locale trung tính.
- `quantity` lớn hơn 0.
- `tags` không `null`, các phần tử không `null`, danh sách không bị người gọi thay đổi sau khi tạo record.
- Mọi constructor đều phải tuân theo các điều kiện trên.

Tệp `Order.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public record Order(String orderId, int quantity, List<String> tags) {

    public Order {
        orderId = Objects.requireNonNull(orderId, "orderId")
                         .strip()
                         .toUpperCase(Locale.ROOT);

        if (orderId.isBlank()) {
            throw new IllegalArgumentException("orderId không được trống");
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải lớn hơn 0");
        }

        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
    }

    public Order(String orderId, int quantity) {
        this(orderId, quantity, List.of());
    }
}
```

Tệp `Main.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        var editableTags = new ArrayList<>(List.of("priority"));

        Order order = new Order("  ab-123  ", 2, editableTags);
        editableTags.add("changed-after-create");

        System.out.println(order.orderId());
        System.out.println(order.quantity());
        System.out.println(order.tags());

        Order simple = new Order("  cd-456  ", 1);
        System.out.println(simple);
    }
}
```

Biên dịch theo Java 17:

```bash
mkdir out
javac --release 17 -encoding UTF-8 -d out Order.java Main.java
java -cp out Main
```

Kết quả dự kiến:

```text
AB-123
2
[priority]
Order[orderId=CD-456, quantity=1, tags=[]]
```

Trong ví dụ này, `editableTags` được sửa sau khi `Order` tạo xong, nhưng bản sao bên trong record không thay đổi. Constructor bổ sung `Order(String orderId, int quantity)` cũng dùng canonical constructor, nên không có đường khởi tạo nào bỏ qua validation.

## 12. Những lỗi dễ mắc khi tự viết constructor record

### Lỗi A: Chuẩn hóa một biến tạm nhưng quên gán lại tham số

**Sai về hành vi, dù biên dịch được:**

```java
record Username(String value) {
    public Username {
        String normalized = value.strip();
        // value vẫn giữ giá trị gốc.
    }
}
```

**Đúng:**

```java
import java.util.Objects;

record Username(String value) {
    public Username {
        value = Objects.requireNonNull(value, "value").strip();
    }
}
```

Với compact constructor, phép gán ngầm ở cuối thân constructor sử dụng **tham số `value` sau cùng**. Nếu chỉ chuẩn hóa vào biến cục bộ `normalized` nhưng không gán lại, giá trị lưu vào record vẫn là dữ liệu ban đầu.

### Lỗi B: Gọi accessor để kiểm tra giá trị trước khi hoàn tất compact constructor

Không nên coi accessor `name()` là cách đọc giá trị đã được chuẩn hóa trong phần thân compact constructor. Hãy **kiểm tra tham số `name` trực tiếp**:

```java
record User(String name) {
    public User {
        name = name.strip();

        if (name.isBlank()) {
            throw new IllegalArgumentException("name không được trống");
        }
    }
}
```

Trong compact constructor, các trường record chỉ được gán ngầm **sau** thân constructor, vì vậy logic chuẩn hóa và kiểm tra phải dựa trên tham số.

### Lỗi C: Tin rằng record tự bất biến sâu

```java
import java.util.List;

record Notes(List<StringBuilder> entries) {
    public Notes {
        entries = List.copyOf(entries);
    }
}
```

`List.copyOf` giữ cho danh sách không thể thêm/xóa qua accessor, nhưng mỗi `StringBuilder` trong danh sách vẫn có thể bị thay đổi. Nếu muốn nội dung cố định, nên chuyển thành danh sách giá trị bất biến như `List<String>` sau khi tạo bản sao dữ liệu, hoặc định nghĩa kiểu bất biến thích hợp.

### Lỗi D: Dùng giá trị mặc định để che đầu vào lỗi

```java
record Quantity(int value) {
    public Quantity {
        if (value < 0) {
            value = 0; // Có thể che giấu bug nếu nghiệp vụ không cho phép.
        }
    }
}
```

Nếu số lượng âm là đầu vào bất hợp lệ, nên báo lỗi:

```java
record Quantity(int value) {
    public Quantity {
        if (value < 0) {
            throw new IllegalArgumentException("value không được âm");
        }
    }
}
```

Chỉ dùng giá trị mặc định khi yêu cầu đầu vào quy định rõ ý nghĩa của nó.

### Lỗi E: Kỳ vọng accessor tự chuẩn hóa dữ liệu ở lúc tạo record

**Không nên** chỉ sửa accessor rồi giả định dữ liệu đã được chuẩn hóa từ lúc khởi tạo:

```java
record Username(String value) {
    @Override
    public String value() {
        return value.strip();
    }
}
```

Trong ví dụ này, trường nội bộ có thể vẫn giữ khoảng trắng, còn `equals()`, `hashCode()` và `toString()` do record tự sinh làm việc với **trạng thái lưu bên trong**. Điều đó dễ gây khác biệt giữa giá trị accessor trả về và biểu diễn bên trong record.

**Đúng:** chuẩn hóa trong canonical constructor:

```java
import java.util.Objects;

record Username(String value) {
    public Username {
        value = Objects.requireNonNull(value, "value").strip();
    }
}
```

Bây giờ accessor, `equals()`, `hashCode()` và `toString()` đều dựa trên giá trị đã chuẩn hóa được lưu trong record.

## 13. Bài tập thực hành

### Bài 1: Chuẩn hóa tên hiển thị

Định nghĩa:

```java
record DisplayName(String value) {
}
```

Yêu cầu: `value` không được `null`; sau khi loại bỏ khoảng trắng hai đầu, chuỗi phải không trống. Không ép chữ hoa hay chữ thường. Hãy viết compact constructor và thử:

```java
new DisplayName("  Minh  "); // value() mong đợi: "Minh"
new DisplayName("   ");      // Ném ngoại lệ
new DisplayName(null);       // Ném ngoại lệ
```

### Bài 2: Kiểm tra khoảng số

Tạo `record IntRange(int min, int max)`. Yêu cầu `min <= max`. Thử:

```java
new IntRange(3, 8); // Hợp lệ
new IntRange(5, 5); // Hợp lệ
new IntRange(9, 2); // Ném IllegalArgumentException
```

Sau đó bổ sung constructor `IntRange(int max)` gọi `this(0, max)`, bảo đảm quy tắc vẫn được áp dụng.

### Bài 3: Sao chép collection

Tạo `record Tags(List<String> values)`. Hãy dùng `List.copyOf` trong compact constructor, sau đó:

1. Tạo một `ArrayList<String>` và truyền vào `Tags`.
2. Thêm phần tử vào `ArrayList` gốc sau khi tạo record.
3. Quan sát rằng `tags.values()` vẫn giữ danh sách ban đầu.
4. Thử sửa trực tiếp `tags.values().add(...)`; danh sách được bảo vệ khỏi thao tác thay đổi.

### Bài 4: Đối chiếu hai dạng canonical constructor

Viết cùng một bài toán chuẩn hóa `record Code(String value)` theo hai cách **ở hai phiên bản mã riêng biệt**:

- Compact constructor: gán lại tham số `value`.
- Explicit canonical constructor: tự gán trường `this.value`.

Quan sát xem khác biệt về cú pháp và trách nhiệm gán trường ảnh hưởng thế nào đến độ ngắn gọn của mỗi cách.

## 14. Ghi nhớ khi thiết kế constructor cho record

| Cần làm | Cách thực hiện trong Java 17 |
| --- | --- |
| Kiểm tra null | `Objects.requireNonNull(...)` hoặc điều kiện tường minh. |
| Kiểm tra giới hạn số, độ dài, định dạng | `if (...) throw new IllegalArgumentException(...)`. |
| Chuẩn hóa component | Trong compact constructor, **gán lại tham số component** trước khi kết thúc thân constructor. |
| Tự gán các component field | Chỉ trong **explicit canonical constructor**, bảo đảm tất cả field được khởi tạo. |
| Bảo vệ collection | Sao chép phòng vệ bằng `List.copyOf`/`Set.copyOf`/`Map.copyOf` nếu phù hợp; xem xét tính bất biến của phần tử. |
| Thêm constructor tiện lợi | Gọi `this(...)` để đi qua canonical constructor. |
| Tránh khác biệt giữa trạng thái và accessor | Đưa validation và normalization vào canonical constructor, thay vì chỉ biến đổi lúc truy cập. |
| Xác nhận tính hợp lệ | Tạo record với dữ liệu hợp lệ lẫn dữ liệu lỗi; quan sát giá trị được lưu và ngoại lệ. |

**Nguyên tắc cốt lõi:** một record nên được tạo ra trong **trạng thái hợp lệ và đã chuẩn hóa theo quy tắc nghiệp vụ**. Trong Java 17, compact canonical constructor giúp thực hiện điều đó rõ ràng: kiểm tra đầu vào, gán lại các tham số cần chuẩn hóa, và để trình biên dịch tự hoàn tất việc lưu chúng vào các component field.
