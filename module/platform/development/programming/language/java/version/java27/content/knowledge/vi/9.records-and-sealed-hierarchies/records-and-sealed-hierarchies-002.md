# Canonical constructor và compact constructor của record

Trong Java 27, `record` là một dạng lớp dành cho dữ liệu được mô tả bởi một tập **record components** cố định. Ví dụ, `record Point(int x, int y)` nói rằng một điểm có hai thành phần `x` và `y`. Java tự sinh những phần thường phải viết bằng tay trong một lớp mang dữ liệu: các field `private final`, accessor, `equals`, `hashCode`, `toString` và **canonical constructor**.

Tuy nhiên, trong ứng dụng thực tế, dữ liệu đầu vào không phải lúc nào cũng hợp lệ hoặc đã ở dạng chuẩn. Một địa chỉ email có thể chứa khoảng trắng ở đầu/cuối; một khoảng số có thể có `start > end`; một danh sách truyền vào có thể bị sửa sau khi đối tượng đã tạo. Lúc này, record cần một điểm kiểm soát để **xác thực** và **chuẩn hóa** dữ liệu.

Bài học thuộc chương **Records và hệ phân cấp sealed**, trong module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Nội dung tập trung vào hai hình thức định nghĩa **canonical constructor**: dạng đầy đủ (*normal canonical constructor*) và dạng rút gọn (*compact constructor*). Đây đều là tính năng Java ổn định, tiếp tục được hỗ trợ trong Java SE 27; không cần bật preview để sử dụng.

## 1. Nhắc lại: record mô tả dữ liệu như thế nào?

Xét record đơn giản:

```java
public record Point(int x, int y) {
}
```

Trong phần đầu `(int x, int y)`, `x` và `y` là **record components**. Với mỗi component, Java cung cấp một field tương ứng có tính chất `private final` và một accessor `public` cùng tên. Do đó, mã gọi sử dụng `point.x()` và `point.y()`, không phải các getter kiểu `getX()` được tự sinh.

```java
Point point = new Point(3, 5);

System.out.println(point.x());       // 3
System.out.println(point.y());       // 5
System.out.println(point);           // Point[x=3, y=5]
System.out.println(point.equals(new Point(3, 5))); // true
```

Các field của record là `final`, không thể gán lại sau khởi tạo. Bản thân record cũng ngầm định là một lớp `final` nên không thể được subclass kế thừa. Record có thể `implements` interface, kể cả một interface `sealed` nếu được phép trong quan hệ phân cấp, nhưng điều này **không thay đổi** các quy tắc constructor đang học.

Lưu ý: tính `final` của các field không làm đối tượng có component tham chiếu như `List` hoặc array trở nên bất biến sâu. Chủ đề sao chép phòng vệ sẽ được giải thích ở mục 8.

## 2. Canonical constructor là gì?

**Canonical constructor** là constructor có tham số tương ứng với **toàn bộ record components theo đúng thứ tự**. Đây là đường khởi tạo trung tâm của record, bảo đảm mỗi component field được nhận giá trị.

Với record:

```java
record Coordinate(double latitude, double longitude) {}
```

Canonical constructor có các tham số tương ứng là `(double latitude, double longitude)`. Nếu không khai báo constructor nào, Java tự tạo canonical constructor. Xét về ý nghĩa gán dữ liệu, nó tương đương:

```java
record Coordinate(double latitude, double longitude) {
    Coordinate(double latitude, double longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }
}
```

Hai đoạn code trên là **hai phiên bản thay thế**, không viết cả hai constructor trong cùng một record.

Canonical constructor có thể tồn tại dưới ba dạng sử dụng:

1. **Implicit canonical constructor:** không viết constructor; compiler tự tạo.
2. **Explicit normal canonical constructor:** viết đầy đủ danh sách tham số và tự gán giá trị cho component fields.
3. **Compact canonical constructor:** chỉ viết tên record và body; compiler cung cấp danh sách tham số và tự gán fields sau khi body chạy xong bình thường.

Trong ba trường hợp, mục tiêu đều là tạo ra một record hoàn chỉnh từ những giá trị component đã được xác định.

## 3. Implicit canonical constructor: khi nào không cần viết gì thêm?

Nếu dữ liệu đầu vào không cần chuẩn hóa hoặc kiểm tra điều kiện nghiệp vụ, khai báo tối giản đã đủ:

```java
public record Pixel(int red, int green, int blue) {}
```

Mã gọi có thể tạo `new Pixel(256, -10, 500)` vì **record không tự đoán** các giới hạn nghiệp vụ 0–255. Compiler chỉ kiểm tra việc truyền tham số phù hợp kiểu `int`.

Điều này dẫn đến nguyên tắc:

> Không viết constructor là lựa chọn hợp lệ khi mọi giá trị của kiểu component đều được chấp nhận; nếu chỉ một phần miền giá trị hợp lệ, cần kiểm tra ở ranh giới khởi tạo.

Khi một record phải bảo vệ invariant, chẳng hạn ba kênh màu đều nằm trong 0–255, nên thêm **canonical constructor tường minh**.

## 4. Normal canonical constructor: khai báo đầy đủ

Normal canonical constructor có danh sách tham số đầy đủ và tên của mỗi tham số phải trùng tên component tương ứng:

```java
public record Pixel(int red, int green, int blue) {
    public Pixel(int red, int green, int blue) {
        requireChannel(red);
        requireChannel(green);
        requireChannel(blue);

        this.red = red;
        this.green = green;
        this.blue = blue;
    }

    private static void requireChannel(int value) {
        if (value < 0 || value > 255) {
            throw new IllegalArgumentException("Channel must be 0..255");
        }
    }
}
```

Constructor này là **canonical** vì danh sách tham số của nó khớp cả thứ tự, kiểu và tên với record header. Nó kiểm tra dữ liệu trước khi gán các component fields. Nếu một giá trị không hợp lệ, `IllegalArgumentException` được ném và đối tượng không được tạo thành công.

Đặc điểm của dạng normal:

- Viết danh sách tham số giống record header.
- Tự khởi tạo mỗi component field một lần đúng quy tắc **definite assignment**; compiler sẽ báo lỗi nếu field chưa được khởi tạo trên một nhánh có thể hoàn tất constructor.
- Có thể chuẩn hóa dữ liệu bằng cách tính toán trước rồi gán vào field, nhưng phải chủ động viết `this.component = ...`.
- Thích hợp khi cần giải thích minh bạch các bước gán, hoặc khi body khởi tạo phức tạp tới mức cú pháp gán tường minh giúp dễ đọc hơn.

Ví dụ chuẩn hóa trong normal canonical constructor:

```java
import java.util.Objects;

public record Category(String code, String title) {
    public Category(String code, String title) {
        String cleanCode = Objects.requireNonNull(code).strip();
        String cleanTitle = Objects.requireNonNull(title).strip();

        if (cleanCode.isEmpty() || cleanTitle.isEmpty()) {
            throw new IllegalArgumentException("Blank category data");
        }

        this.code = cleanCode;
        this.title = cleanTitle;
    }
}
```

Lưu ý: một normal canonical constructor **không được** khai báo `throws` clause, không được là generic constructor và không được chứa explicit constructor invocation như `this(...)` hay `super(...)`. Muốn xử lý lỗi dữ liệu, thông thường ném các exception không kiểm tra như `IllegalArgumentException`. Nếu API cần xử lý checked exception, hãy cân nhắc factory method có `throws` rõ ràng thay vì cố thêm `throws` vào canonical constructor.

## 5. Compact constructor: cú pháp rút gọn nhưng vẫn là canonical

Compact constructor bỏ phần `(tham_số)` khi khai báo, nhưng vẫn ngầm có các tham số trùng tên với record components.

```java
public record Pixel(int red, int green, int blue) {
    public Pixel {
        requireChannel(red);
        requireChannel(green);
        requireChannel(blue);
    }

    private static void requireChannel(int value) {
        if (value < 0 || value > 255) {
            throw new IllegalArgumentException("Channel must be 0..255");
        }
    }
}
```

Đây là **phiên bản thay thế** của ví dụ `Pixel` ở mục 4. Khác biệt quan trọng là trong body compact constructor **không có** các lệnh:

```java
this.red = red;
this.green = green;
this.blue = blue;
```

Các lệnh đó được compiler thực hiện một cách ngầm định **sau khi body compact constructor hoàn tất bình thường**, theo đúng thứ tự record components trong header. Vì vậy, đây là nơi thuận tiện để xác thực đầu vào trước khi dữ liệu trở thành trạng thái record.

### 5.1. Chu trình xử lý của compact constructor

```text
new Pixel(10, 20, 30)
        |
        v
Tạo các tham số ngầm định:
red=10, green=20, blue=30
        |
        v
Chạy body: kiểm tra / chuẩn hóa tham số
        |
        +-- exception --> Không tạo record thành công
        |
        v
Body hoàn tất bình thường
        |
        v
Compiler gán:
this.red = red;
this.green = green;
this.blue = blue;
        |
        v
Record được khởi tạo thành công
```

Tên `red` bên trong compact constructor chỉ **tham số ngầm định**, không phải cách truy cập trực tiếp field chưa hoàn tất khởi tạo. Đây là lý do có thể sửa tham số trước khi compiler thực hiện phép gán cuối cùng.

### 5.2. Chuẩn hóa bằng cách gán lại tham số

Ví dụ một mã sản phẩm cần bỏ khoảng trắng thừa và chuẩn hóa sang chữ hoa:

```java
import java.util.Locale;
import java.util.Objects;

public record ProductCode(String value) {
    public ProductCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z0-9_-]{3,20}")) {
            throw new IllegalArgumentException("Invalid product code");
        }
    }
}
```

Sử dụng:

```java
ProductCode code = new ProductCode(" ab-12 ");
System.out.println(code.value()); // AB-12
```

Phép gán `value = ...` chỉ gán lại **tham số**. Khi body kết thúc, compiler mới gán kết quả đã chuẩn hóa vào `this.value`. Trong dạng normal, ta phải tự viết phép gán cho field.

**Đây là điểm khác biệt trung tâm:** compact constructor viết code kiểm tra/chuẩn hóa; normal canonical constructor viết cả kiểm tra/chuẩn hóa **lẫn** các lệnh gán field.

## 6. So sánh hai cách khai báo

| Tiêu chí | Normal canonical constructor | Compact constructor |
| --- | --- | --- |
| Cú pháp | `Record(Type a, Type b) { ... }` | `Record { ... }` |
| Danh sách tham số | Viết rõ; tên và kiểu khớp components | Compiler cung cấp ngầm định |
| Kiểm tra giá trị | Được | Được |
| Chuẩn hóa giá trị | Được | Được, thường bằng gán lại tham số |
| Gán component fields | Lập trình viên tự gán đúng quy tắc | Compiler tự gán sau body |
| Gán trực tiếp `this.component` | Có thể thực hiện trong đúng quá trình khởi tạo | Bị cấm trong body compact |
| Có thể là canonical của public record | Có, nếu khai báo `public` | Có, nếu khai báo `public` |
| Trường hợp sử dụng | Muốn kiểm soát và thể hiện tường minh việc khởi tạo | Ưu tiên cho validate/normalize rõ ràng, ít lặp |

Hai dạng đều là **canonical constructor**; compact không phải constructor phụ và không tạo thêm đường khởi tạo riêng.

## 7. Các quy tắc biên dịch bắt buộc

### 7.1. Không được có đồng thời hai canonical constructors

Đoạn sau sai vì hai constructor cùng đại diện cho cùng chữ ký canonical:

```java
record Point(int x, int y) {
    Point {
        // compact canonical
    }

    // Lỗi: đã có compact canonical constructor
    // Point(int x, int y) {
    //     this.x = x;
    //     this.y = y;
    // }
}
```

Chọn **một** dạng: normal hoặc compact. Không thể kết hợp để “dùng compact kiểm tra rồi dùng normal gán field”.

### 7.2. Normal canonical phải khớp tên, kiểu, thứ tự

Với `record Person(String name, int age)`, constructor đầy đủ hợp lệ phải dùng `(String name, int age)`.

```java
record Person(String name, int age) {
    Person(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

Đổi tên tham số `name` thành `fullName` trong constructor này **không hợp lệ**. Cùng danh sách kiểu, compiler nhận ra đó là khai báo canonical nhưng yêu cầu tên các tham số phải khớp components. Thay đổi thứ tự các tham số có thể tạo một constructor có chữ ký khác (khi kiểu khác nhau), nhưng đó không còn là canonical constructor và phải tuân thủ quy tắc constructor phụ ở mục 9.

Nếu component cuối là varargs, tham số canonical tương ứng cũng phải được khai báo varargs. Ví dụ header `record Tags(String category, String... labels)` thì normal canonical constructor viết `Tags(String category, String... labels)`.

### 7.3. Compact không được tự gán component fields

Code này sai:

```java
record Point(int x, int y) {
    Point {
        // this.x = x; // Lỗi biên dịch: gán component field trong compact
        // this.y = y; // Lỗi biên dịch
    }
}
```

Compiler sẽ gán chúng tự động. Nếu muốn thay đổi giá trị, chỉ gán lại tham số `x` hoặc `y`:

```java
record NonNegativePoint(int x, int y) {
    NonNegativePoint {
        x = Math.max(0, x);
        y = Math.max(0, y);
    }
}
```

### 7.4. Không dùng `return` hay gọi constructor khác trong compact body

Compact constructor không được chứa lệnh `return`, kể cả `return;`. Khi điều kiện đầu vào sai, ném exception phù hợp thay vì thoát constructor bằng `return`.

Body compact cũng không được chứa explicit constructor invocation như `this(...)` hoặc `super(...)`. Đây là **canonical** constructor nên không thể chuyển trách nhiệm khởi tạo sang constructor khác theo cách đó.

### 7.5. Quy tắc visibility

Canonical constructor khai báo tường minh phải có mức truy cập **ít nhất rộng bằng mức truy cập của record**. Ví dụ public record phải có public canonical constructor:

```java
public record UserId(long value) {
    public UserId {
        if (value <= 0) {
            throw new IllegalArgumentException("User ID must be positive");
        }
    }
}
```

Nếu bỏ `public` trước `UserId` compact constructor trong public record, khai báo sẽ lỗi biên dịch. Với top-level record không công khai (package-private), canonical constructor không được khai báo `private`; việc dùng package-private hoặc `public` là hợp lệ. Với nested records, mức truy cập của record có thể khác, nhưng nguyên tắc không thu hẹp quyền truy cập vẫn áp dụng theo JLS.

Constructor canonical do compiler tự tạo có cùng mức truy cập với record.

### 7.6. Canonical constructor không được có `throws` clause

JLS Java SE 27 cấm `throws` clause ở normal canonical constructor; dạng compact không có vị trí cú pháp cho phần khai báo đó. Không thể viết constructor canonical `throws IOException` để đẩy checked exception cho caller.

Có thể ném `IllegalArgumentException`, `NullPointerException` hoặc các unchecked exceptions phù hợp. Nếu khởi tạo phụ thuộc I/O có thể ném checked exception, hãy thực hiện ở factory/service bên ngoài, rồi truyền dữ liệu đã xử lý vào record.

## 8. Defensive copy: bảo vệ bất biến nông của record

Field của record là `private final`, nhưng nếu component chứa object mutable thì nội dung object đó vẫn có thể bị đổi. Đây là vấn đề thực tế của nhiều record mang danh sách, map hoặc array.

### 8.1. Ví dụ sai: giữ tham chiếu danh sách từ caller

```java
import java.util.ArrayList;
import java.util.List;

record Course(String name, List<String> lessons) {}

List<String> source = new ArrayList<>(List.of("Intro"));
Course course = new Course("Java 27", source);
source.add("Records");

System.out.println(course.lessons()); // [Intro, Records]
```

Mã tạo record đã thay đổi được trạng thái quan sát qua record sau khi construction, dù `lessons` là field `final`.

### 8.2. Dùng compact constructor để tạo snapshot

```java
import java.util.List;
import java.util.Objects;

public record Course(String name, List<String> lessons) {
    public Course {
        name = Objects.requireNonNull(name, "name").strip();
        if (name.isBlank()) {
            throw new IllegalArgumentException("Course name is blank");
        }

        lessons = List.copyOf(Objects.requireNonNull(lessons, "lessons"));
    }
}
```

`List.copyOf` tạo một list không sửa đổi được, với các phần tử `String` cũng bất biến. Với một `ArrayList` mutable làm đầu vào, list của record sẽ không phản ánh các thay đổi cấu trúc tiếp theo trên `ArrayList` đó; caller cũng không thể gọi `course.lessons().add(...)` để sửa bản snapshot. `List.copyOf` không chấp nhận phần tử null.

Một ví dụ sử dụng:

```java
List<String> source = new java.util.ArrayList<>(List.of("Intro"));
Course course = new Course(" Java 27 ", source);

source.add("Extra");
System.out.println(course.name());    // Java 27
System.out.println(course.lessons()); // [Intro]
```

Lưu ý: `List.copyOf` bảo vệ **cấu trúc collection**, không deep-copy từng phần tử. Nếu phần tử thuộc một mutable class, dữ liệu bên trong phần tử đó vẫn có thể bị sửa. Cần chọn kiểu phần tử immutable hoặc sao chép sâu có chủ đích.

### 8.3. Dùng array làm record component cần đặc biệt thận trọng

Với array, không chỉ constructor mà cả accessor cũng có thể làm lộ dữ liệu:

```java
import java.util.Objects;

public record BytePayload(byte[] data) {
    public BytePayload {
        data = Objects.requireNonNull(data, "data").clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
```

Compact constructor sao chép đầu vào; accessor trả một bản sao khác, tránh mã ngoài sửa array nội bộ. Tuy nhiên, `equals` và `hashCode` được sinh cho record chứa array vẫn dựa trên giá trị component theo quy tắc Java; array mặc định so sánh theo **tham chiếu**, không tự so nội dung phần tử. Vì vậy, hai `BytePayload` chứa những mảng byte khác nhau nhưng có nội dung giống nhau không tự động `equals` nhau. Với kiểu giá trị muốn so nội dung, hãy cân nhắc một representation phù hợp hoặc cài đặt rõ chính sách so sánh (nhất quán với `hashCode` và accessor).

## 9. Constructor phụ của record: bắt buộc hướng về canonical

Record có thể có **non-canonical constructor** để cung cấp giá trị mặc định hoặc thuận tiện cho mã gọi. Constructor phụ không được tự trực tiếp thiết lập component fields như một đường khởi tạo độc lập; nó phải **ủy quyền tới constructor khác của chính record thông qua `this(...)`**, rồi cuối cùng đi tới canonical constructor.

```java
public record PageRequest(int page, int size) {
    public PageRequest {
        if (page < 0) {
            throw new IllegalArgumentException("page must be >= 0");
        }
        if (size <= 0 || size > 200) {
            throw new IllegalArgumentException("size must be 1..200");
        }
    }

    public PageRequest(int page) {
        this(page, 20); // Constructor phụ chuyển tới canonical
    }
}
```

`new PageRequest(2)` cũng trải qua mọi kiểm tra trong canonical constructor. Cách thiết kế này tránh lặp quy tắc xác thực và bảo đảm không có đường khởi tạo bỏ qua invariant.

**Lưu ý dành cho Java 27:** Các constructor body theo Java hiện hành có thể cho phép một số câu lệnh hợp lệ trước explicit constructor invocation, theo quy tắc *flexible constructor bodies*. Vì vậy, không nên diễn đạt quy tắc cho record là “`this(...)` nhất thiết phải là câu lệnh đầu tiên” trong mọi trường hợp. Điều kiện chuẩn xác của record là constructor **không phải canonical phải chứa alternate constructor invocation**, tuân thủ các quy tắc khởi tạo của JLS. Với trường hợp đơn giản, đặt `this(...)` ngay đầu như ví dụ là dễ hiểu nhất.

Không khai báo cả hai constructor canonical bằng dạng normal và compact trong cùng một record. Constructor phụ chỉ hợp lệ khi có chữ ký khác canonical.

## 10. Xác thực khác chuẩn hóa: chọn hành vi nghiệp vụ rõ ràng

**Validation** từ chối những giá trị không hợp lệ. **Normalization** biến đầu vào được phép thành một biểu diễn chuẩn. Compact constructor hỗ trợ cả hai, nhưng lựa chọn chính sách là trách nhiệm của người thiết kế.

### 10.1. Kiểm tra khoảng số

```java
public record ClosedRange(int start, int end) {
    public ClosedRange {
        if (start > end) {
            throw new IllegalArgumentException("start must be <= end");
        }
    }

    public boolean contains(int value) {
        return start <= value && value <= end;
    }
}
```

Chúng ta **từ chối** `new ClosedRange(10, 5)`. Nếu nghiệp vụ có lý do cho phép hoán đổi đầu mút, có thể chuẩn hóa thay vì ném exception, nhưng phải làm rõ quy ước đó với người sử dụng API.

### 10.2. Chuẩn hóa giá trị tiền tệ mà không dựa vào số dấu phẩy động nhị phân

```java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Objects;

public record Money(String currency, BigDecimal amount) {
    public Money {
        currency = Objects.requireNonNull(currency, "currency")
                .strip()
                .toUpperCase(Locale.ROOT);
        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Invalid currency code");
        }

        amount = Objects.requireNonNull(amount, "amount");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
    }
}
```

Đây là ví dụ tập trung vào cách constructor bảo vệ dữ liệu, **chưa phải kiểu Money hoàn chỉnh cho sản phẩm tài chính**: mã ba chữ cái chưa chứng minh thuộc danh mục tiền hợp lệ; số chữ số thập phân và chính sách rounding phải được định nghĩa theo nghiệp vụ. `BigDecimal` là kiểu immutable, phù hợp với việc giữ thành phần giá trị mà không cần defensive copy.

Nếu muốn chuẩn hóa cả thang đo (`scale`), cần quyết định có được làm tròn hay không. Không nên âm thầm gọi `setScale(2)` cho mọi đơn vị tiền tệ mà chưa có quy tắc chính thức.

### 10.3. Cân nhắc tính lặp lại (idempotence) của chuẩn hóa

Với một record được chuẩn hóa, kết quả của `new R(r.component1(), ...)` nên đại diện cùng dữ liệu với `r`. Ví dụ `strip()` thường cho kết quả ổn định khi áp dụng lại. Tránh accessor trả dữ liệu khác với component đang lưu hoặc chuẩn hóa không nhất quán khiến sao chép record tạo ra trạng thái bất ngờ.

## 11. Tương tác với `equals`, `hashCode`, `toString` và accessor

Record tự cung cấp những method này dựa trên **component fields**. Constructor ảnh hưởng đến các kết quả đó bằng cách quyết định giá trị được ghi vào component fields.

```java
public record Tag(String value) {
    public Tag {
        value = value.strip().toLowerCase(java.util.Locale.ROOT);
        if (value.isBlank()) {
            throw new IllegalArgumentException("Blank tag");
        }
    }
}
```

```java
Tag a = new Tag(" JAVA ");
Tag b = new Tag("java");

System.out.println(a.value());   // java
System.out.println(a.equals(b)); // true
```

Hai đầu vào khác nhau được chuyển về cùng biểu diễn chuẩn nên record so sánh bằng nhau. Nếu giá trị có thể null, cần kiểm tra trước khi gọi `strip()`, ví dụ bằng `Objects.requireNonNull`; bỏ qua kiểm tra sẽ ném `NullPointerException` khi null xuất hiện.

Không nên override accessor để trình bày một giá trị đã biến đổi khác component field theo cách phá vỡ kỳ vọng sao chép của record. JLS mô tả tính chất mong đợi rằng khi sao chép record bằng các accessor và gọi canonical constructor, bản sao phải tương đương về `equals` với bản gốc (với cách cài đặt phù hợp). Trường hợp có yêu cầu trình bày khác, hãy dùng method riêng thay vì thay đổi ý nghĩa của accessor.

Đừng nhầm `toString()` với một cơ chế bảo vệ dữ liệu nhạy cảm: dạng sinh tự động có thể đưa các component vào chuỗi kết quả. Không đặt secret như token hoặc mật khẩu vào một record rồi mặc nhiên log nguyên `toString()`. Cân nhắc kiểu và chính sách log riêng khi cần bảo mật.

## 12. Record và sealed hierarchy có liên quan thế nào?

`record` và `sealed` giải quyết **hai vấn đề khác nhau**:

- `record` mô tả trạng thái bằng components; canonical constructor bảo vệ quá trình tạo **một giá trị**.
- `sealed interface` hoặc `sealed class` giới hạn tập kiểu triển khai/kế thừa trực tiếp.

Chúng có thể phối hợp theo mô hình dữ liệu có tập biến thể hữu hạn:

```java
public sealed interface PaymentResult
        permits PaymentResult.Success, PaymentResult.Failure {

    record Success(String receiptId) implements PaymentResult {
        public Success {
            if (receiptId == null || receiptId.isBlank()) {
                throw new IllegalArgumentException("Blank receiptId");
            }
        }
    }

    record Failure(String reason) implements PaymentResult {
        public Failure {
            if (reason == null || reason.isBlank()) {
                throw new IllegalArgumentException("Blank reason");
            }
        }
    }
}
```

Ở đây, `PaymentResult` giới hạn các biến thể trực tiếp; canonical compact constructors của từng record bảo vệ giá trị component cho từng biến thể. Các nested records là implicitly static, và record là implicitly final, phù hợp với yêu cầu một implementation trực tiếp của sealed interface phải là `final`, `sealed` hoặc `non-sealed` theo quy tắc Java.

Đây chỉ là ví dụ liên hệ với tên chương; bài học này không yêu cầu sử dụng `sealed` để một record có canonical constructor hợp lệ.

## 13. Một ví dụ chạy được từ đầu đến cuối

Đặt nội dung sau vào file `Demo.java`. Ví dụ có một public class làm điểm chạy và một record package-private trong cùng file:

```java
import java.util.List;
import java.util.Objects;

record Enrollment(String student, List<String> subjects) {
    Enrollment {
        student = Objects.requireNonNull(student, "student").strip();
        if (student.isBlank()) {
            throw new IllegalArgumentException("Student name is blank");
        }
        subjects = List.copyOf(Objects.requireNonNull(subjects, "subjects"));
    }

    Enrollment(String student) {
        this(student, List.of());
    }
}

public class Demo {
    public static void main(String[] args) {
        Enrollment first = new Enrollment(
                "  Lan  ", List.of("Java", "SQL"));
        Enrollment second = new Enrollment("Lan");

        System.out.println(first.student());   // Lan
        System.out.println(first.subjects()); // [Java, SQL]
        System.out.println(second.subjects()); // []

        try {
            new Enrollment("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage()); // Student name is blank
        }
    }
}
```

Biên dịch và chạy bằng JDK 27:

```shell
javac Demo.java
java Demo
```

Không cần `--enable-preview`, vì record, normal canonical constructor và compact constructor đều là tính năng ổn định. Quan sát rằng cả constructor hai tham số và constructor một tham số đều dẫn về cùng đường kiểm tra của compact canonical constructor.

## 14. Những lỗi thường gặp và cách sửa

| Tình huống | Kết quả/vấn đề | Cách xử lý |
| --- | --- | --- |
| Public record nhưng canonical constructor không public | Lỗi biên dịch vì giảm visibility | Khai báo `public RecordName { ... }` hoặc `public RecordName(...)` |
| Viết cả normal và compact canonical | Lỗi trùng chữ ký constructor | Chọn một dạng canonical |
| Normal canonical dùng tên tham số khác component | Lỗi biên dịch | Dùng đúng tên và kiểu component |
| Normal canonical không gán hết component fields | Lỗi definite assignment | Khởi tạo toàn bộ fields khi constructor kết thúc bình thường |
| Compact tự gán `this.component` | Lỗi biên dịch | Gán lại tham số `component = ...` |
| Compact chứa `return` | Lỗi biên dịch | Dùng điều kiện/exception, để body hoàn tất bình thường |
| Constructor phụ không chứa `this(...)` | Lỗi biên dịch | Ủy quyền tới constructor khác của record |
| Đưa `throws IOException` vào canonical | Lỗi biên dịch | Thực hiện I/O bên ngoài; cân nhắc factory |
| Đầu vào `List` mutable được giữ nguyên | Caller sửa được dữ liệu về sau | `List.copyOf`, xét thêm kiểu phần tử |
| Component là array và chỉ copy trong constructor | Accessor mặc định còn làm lộ array | Override accessor để copy; xem xét `equals`/`hashCode` |
| Dùng `record` rồi mặc định mọi dữ liệu hợp lệ | Constructor ngầm định không kiểm tra invariant | Viết normal hoặc compact canonical để validate |
| Chuẩn hóa thiếu chính sách rõ ràng | Giá trị đầu ra gây bất ngờ, khó kiểm thử | Tài liệu hóa trường hợp được chuẩn hóa và bị từ chối |

## 15. Khi nào chọn dạng nào?

**Không khai báo constructor** khi record chỉ mô tả những giá trị có sẵn mà không cần thêm quy tắc.

**Chọn compact constructor** khi trọng tâm là kiểm tra đầu vào, chuẩn hóa chuỗi, phòng vệ đối với collection hoặc thực hiện một số bước xử lý rõ ràng trước khi gán fields. Với đa số record mang dữ liệu thông thường, đây là lựa chọn ngắn gọn và tránh lặp khai báo tham số.

**Chọn normal canonical constructor** khi cần diễn tả tường minh logic gán từng component field, hoặc cấu trúc khởi tạo được hiểu rõ hơn khi các phép gán xuất hiện trong code. Khi dùng dạng này, lập trình viên phải chịu trách nhiệm đầy đủ về việc gán các component fields.

**Chọn constructor phụ hoặc static factory** khi muốn cung cấp các cách khởi tạo tiện lợi (mặc định một phần giá trị, parse dữ liệu, hoặc thực hiện tác vụ có thể có checked exception). Constructor phụ phải đưa quá trình khởi tạo về canonical để không bỏ qua invariant.

Trước khi chốt thiết kế, hãy tự hỏi: record component có mutable không? Có cần null không? Có cần chuẩn hóa không? Các exception được ném có phù hợp cho API không? Tạo bản sao bằng accessor có còn giữ ý nghĩa `equals` không?

## 16. Tổng kết

Canonical constructor là đường khởi tạo trung tâm của mỗi Java record. Nếu không viết, compiler tự sinh để gán từng component field. Nếu muốn kiểm soát đầu vào, có thể khai báo **normal canonical constructor** với đầy đủ tham số và các lệnh `this.field = ...`, hoặc **compact constructor** chỉ chứa phần xác thực/chuẩn hóa rồi để compiler tự gán fields.

Trong Java 27, điểm cần nhớ nhất là **compact constructor vẫn là canonical constructor**, chỉ khác ở cách biểu diễn cú pháp và trách nhiệm gán field. Nó không được tự gán component fields, không được chứa `return` hay explicit constructor invocation. Normal canonical phải có đúng tên/kiểu tham số và tự khởi tạo fields. Mọi constructor phụ phải ủy quyền về canonical; nhờ đó, các quy tắc hợp lệ của record được áp dụng nhất quán.

Khi components chứa các đối tượng mutable, kết hợp constructor với **defensive copy** và cân nhắc cả accessor; `final` không đủ để có deep immutability. Chọn constructor theo nhu cầu giữ invariant và sự rõ ràng của API, thay vì theo mức độ ngắn của cú pháp.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — §8.10 Record Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10) — cấu trúc record và các thành viên được sinh.
- [Java Language Specification, Java SE 27 — §8.10.4 Record Constructor Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10.4) — canonical constructor, quyền truy cập và constructor phụ.
- [Java Language Specification, Java SE 27 — §8.10.4.1 Normal Canonical Constructors](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10.4.1) — ràng buộc tên/kiểu tham số, `throws` và cách khởi tạo fields.
- [Java Language Specification, Java SE 27 — §8.10.4.2 Compact Canonical Constructors](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10.4.2) — tham số ngầm định, quy tắc body và thời điểm gán fields.
- [Java Language Specification, Java SE 27 — §8.8.7 Constructor Body](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.8.7) — quy tắc gọi constructor trong Java 27.
- [java.lang.Record — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Record.html) — hợp đồng cơ bản của record và các method được sinh.
- [java.util.List — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) — `List.copyOf` và immutable collection.
