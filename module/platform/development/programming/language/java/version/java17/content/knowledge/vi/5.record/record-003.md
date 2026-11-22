# Canonical constructor và compact constructor trong Java 17

Trong Java 17, **record** là cách khai báo một kiểu dữ liệu chủ yếu dùng để biểu diễn một nhóm giá trị cố định. Khi tạo đối tượng record, Java cần nhận các giá trị cho những **record component** được khai báo trong phần header. Constructor nhận đúng tập component đó được gọi là **canonical constructor**.

Java hỗ trợ hai cách viết canonical constructor: **dạng đầy đủ (normal/explicit canonical constructor)** và **dạng rút gọn (compact constructor)**. Ngoài ra, nếu bạn không tự viết canonical constructor, compiler sẽ **tự sinh** một constructor tương ứng.

Hiểu ba trường hợp này giúp bạn xác thực dữ liệu, chuẩn hóa đầu vào và giữ cho record luôn ở trạng thái hợp lệ mà không viết các phép gán lặp lại.

> **Phiên bản:** Record đã là tính năng chính thức từ Java 16 (JEP 395), vì vậy toàn bộ cú pháp trong bài hoạt động trên **Java 17** mà không cần `--enable-preview`. Bài tập trung vào các quy tắc còn áp dụng trong Java hiện đại, không dùng cú pháp preview cũ.

## 1. Record component tạo ra hợp đồng khởi tạo như thế nào?

Xét khai báo:

~~~java
record Point(int x, int y) {
}
~~~

Các thành phần `int x` và `int y` trong header gọi là **record components**. Với khai báo trên, Java tạo ra những thành phần cốt lõi tương ứng:

- Hai field lưu trạng thái: `private final int x` và `private final int y`.
- Hai accessor: `x()` và `y()`.
- Các phương thức `equals(Object)`, `hashCode()` và `toString()` thích hợp.
- Một canonical constructor có tham số `(int x, int y)` để khởi tạo hai component.

Bạn có thể viết:

~~~java
Point p = new Point(3, 7);

System.out.println(p.x()); // 3
System.out.println(p.y()); // 7
System.out.println(p);     // Point[x=3, y=7]
~~~

Record **không** tự sinh constructor rỗng `Point()`, bởi cả `x` lẫn `y` đều phải được khởi tạo theo hợp đồng của header.

Nhìn từ bên ngoài, việc `new Point(3, 7)` có vẻ giống gọi constructor truyền thống. Khác biệt nằm ở việc **record header đã quy định trước hình dạng canonical constructor**: tên, kiểu và thứ tự của từng component.

### Ba trường hợp thường gặp

| Trường hợp | Bạn viết gì? | Ai gán giá trị cho các field component? | Khi nên dùng |
|---|---|---|---|
| **Canonical constructor ngầm định** | Chỉ viết record header, không khai báo canonical constructor | Compiler tự sinh constructor và phép gán | Dữ liệu không cần xác thực hoặc chuẩn hóa thêm |
| **Canonical constructor tường minh, dạng đầy đủ** | Viết constructor có danh sách tham số khớp header | **Bạn tự gán** tất cả field component | Cần kiểm soát trực tiếp cách khởi tạo hoặc logic gán |
| **Compact constructor** | Viết tên record và thân constructor, **không có danh sách tham số** | Compiler tự gán field sau khi chạy thân constructor thành công | Cần xác thực/chuẩn hóa tham số nhưng muốn mã ngắn, ít lỗi |

**Điểm rất dễ nhầm:** *Compact constructor cũng là một cách khai báo canonical constructor*. Nó không phải loại constructor có tập tham số khác.

## 2. Canonical constructor ngầm định: không cần tự viết

Ví dụ đơn giản nhất:

~~~java
record Size(int width, int height) {
}
~~~

Nếu không có canonical constructor tường minh, compiler tạo một constructor có nhiệm vụ tương đương:

~~~java
// Minh họa ý nghĩa của constructor do compiler sinh:
Size(int width, int height) {
    this.width = width;
    this.height = height;
}
~~~

Trong ví dụ này, `Size` có quyền truy cập package-private, nên constructor được sinh cũng có cùng mức truy cập. Nếu record là `public`, constructor ngầm định cũng là `public`.

Khi không cần kiểm tra dữ liệu, đây là lựa chọn ngắn gọn:

~~~java
Size size = new Size(1920, 1080);
System.out.println(size.width());  // 1920
System.out.println(size.height()); // 1080
~~~

Lưu ý: compiler không tự suy ra rằng kích thước phải dương. `new Size(-1, 0)` vẫn hợp lệ theo khai báo trên. Muốn áp dụng bất biến nghiệp vụ, bạn cần viết canonical constructor để kiểm tra.

## 3. Canonical constructor tường minh, dạng đầy đủ

Đây là constructor ghi rõ **danh sách tham số** khớp với record header về **số lượng, tên, kiểu và thứ tự** component.

~~~java
record Rectangle(int width, int height) {

    public Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException(
                    "Chiều rộng và chiều cao phải lớn hơn 0");
        }

        this.width = width;
        this.height = height;
    }
}
~~~

Ở đây, constructor nhận đúng `int width, int height` như trong header và làm hai việc:

1. Kiểm tra tính hợp lệ của dữ liệu trước khi khởi tạo.
2. **Tự gán** các field `this.width` và `this.height`.

Khi đã tự khai báo canonical constructor dạng đầy đủ, compiler **không** thêm một canonical constructor ngầm định khác để gán field thay bạn. Vì các field component là `final`, mọi đường chạy bình thường của constructor phải khởi tạo đầy đủ chúng.

Ví dụ gọi:

~~~java
Rectangle ok = new Rectangle(8, 5);
System.out.println(ok); // Rectangle[width=8, height=5]

// Ném IllegalArgumentException theo quy tắc do ta đặt ra:
new Rectangle(-2, 5);
~~~

### 3.1. Không thể đổi tên/thứ tự/kiểu tham số của canonical constructor

Với `record Rectangle(int width, int height)`, constructor sau **không phải** canonical constructor tương ứng:

~~~java
record Rectangle(int width, int height) {
    // Đây là constructor khác tham số; nó không tự thay thế canonical constructor.
    // Nếu khai báo overload, constructor này phải chuyển tiếp bằng this(...).
    public Rectangle(int width) {
        this(width, width);
    }
}
~~~

`Rectangle(int width)` là **overloaded constructor**: nó chỉ nhận một tham số và chuyển tiếp tới canonical constructor nhận hai tham số. Vì canonical constructor không được khai báo tường minh trong ví dụ này, Java vẫn tự sinh constructor `Rectangle(int width, int height)`.

Không thể “đổi tên” tham số canonical thành `(int w, int h)` rồi mong compiler tự xem nó là cùng signature của record. Quy tắc canonical constructor nghiêm ngặt hơn constructor thông thường: tên tham số phải tương ứng với các record component.

### 3.2. Tự gán đầy đủ các component

Ví dụ lỗi:

~~~java
// VÍ DỤ SAI: thiếu khởi tạo field y.
record Position(int x, int y) {
    public Position(int x, int y) {
        this.x = x;
        // this.y chưa được gán.
    }
}
~~~

Compiler báo lỗi vì `y` chưa được khởi tạo. Không có phép gán tự động ở cuối **canonical constructor dạng đầy đủ**.

Khi xử lý nhiều component với logic dài, bạn có thể tính toán và kiểm tra trước rồi mới gán:

~~~java
import java.util.Objects;

record PersonName(String givenName, String familyName) {
    public PersonName(String givenName, String familyName) {
        Objects.requireNonNull(givenName, "givenName");
        Objects.requireNonNull(familyName, "familyName");

        String normalizedGiven = givenName.strip();
        String normalizedFamily = familyName.strip();

        if (normalizedGiven.isEmpty() || normalizedFamily.isEmpty()) {
            throw new IllegalArgumentException("Họ và tên không được rỗng");
        }

        this.givenName = normalizedGiven;
        this.familyName = normalizedFamily;
    }
}
~~~

Sau khi khởi tạo thành công, các accessor `givenName()` và `familyName()` trả về giá trị đã được chuẩn hóa. Việc chuẩn hóa là một phần của **hợp đồng tạo đối tượng**, không yêu cầu người gọi nhớ tự xử lý trước.

## 4. Compact constructor: kiểm tra và chuẩn hóa, Java tự gán field

Compact constructor có cú pháp khác biệt:

~~~java
record Percentage(int value) {

    public Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "Phần trăm phải nằm trong khoảng 0..100");
        }
    }
}
~~~

Hãy chú ý:

- Viết `public Percentage { ... }`, **không viết** `Percentage(int value)`.
- Tham số `value` vẫn **tồn tại ngầm định**, lấy từ record header.
- Bạn có thể đọc, kiểm tra và **gán lại biến tham số** `value` trong thân constructor.
- Nếu thân constructor kết thúc bình thường, compiler tự gán giá trị cuối cùng của `value` vào field `this.value`.

Về mặt ý nghĩa, trường hợp trên tương đương một canonical constructor đầy đủ kiểu:

~~~java
record Percentage(int value) {
    public Percentage(int value) {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "Phần trăm phải nằm trong khoảng 0..100");
        }
        this.value = value;
    }
}
~~~

Bạn chỉ dùng **một trong hai cách** trên cho một record; không khai báo đồng thời hai canonical constructor.

### 4.1. Chuẩn hóa tham số ngay trong compact constructor

Một trường hợp sử dụng rất phổ biến là loại bỏ khoảng trắng và chuẩn hóa chữ hoa/chữ thường:

~~~java
import java.util.Locale;
import java.util.Objects;

record CourseCode(String value) {

    public CourseCode {
        Objects.requireNonNull(value, "value");

        value = value.strip().toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{2,5}-[0-9]{3}")) {
            throw new IllegalArgumentException(
                    "Mã môn học phải có dạng JAVA-017");
        }
    }
}
~~~

Gọi:

~~~java
CourseCode code = new CourseCode("  java-017  ");

System.out.println(code.value()); // JAVA-017
System.out.println(code);         // CourseCode[value=JAVA-017]
~~~

Diễn tiến khởi tạo:

~~~text
new CourseCode("  java-017  ")
             |
             v
Tham số value = "  java-017  "
             |
             v
Chạy thân compact constructor:
  - kiểm tra null
  - value = "JAVA-017"
  - kiểm tra định dạng
             |
             v
Thân constructor kết thúc bình thường
             |
             v
Compiler gán this.value = value
             |
             v
Record hoàn chỉnh: CourseCode[value=JAVA-017]
~~~

Phép gán cuối là trách nhiệm của compiler, vì vậy mã ngắn và tránh việc quên gán một field khi record có nhiều component.

### 4.2. Không được tự gán field component trong compact constructor

Đoạn sau **không hợp lệ**:

~~~java
record Score(int value) {

    public Score {
        if (value < 0) {
            throw new IllegalArgumentException();
        }

        // LỖI: không được gán trực tiếp vào field component
        // trong thân compact constructor.
        this.value = value;
    }
}
~~~

Cách đúng:

~~~java
record Score(int value) {

    public Score {
        if (value < 0) {
            throw new IllegalArgumentException("Điểm không được âm");
        }
        // Không cần gán this.value.
    }
}
~~~

Khi chuẩn hóa, hãy **gán lại tham số**, chẳng hạn `value = Math.max(0, value)` nếu việc tự động điều chỉnh điểm âm thực sự phù hợp với yêu cầu nghiệp vụ. Nếu dữ liệu âm là lỗi, ném ngoại lệ thường rõ nghĩa hơn.

### 4.3. Compact constructor có thể dùng nhiều component

~~~java
import java.time.LocalDate;
import java.util.Objects;

record DateRange(LocalDate start, LocalDate end) {

    public DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "Ngày kết thúc không được trước ngày bắt đầu");
        }
    }
}
~~~

Java tự gán **cả hai** field `start` và `end` sau khi thân constructor hoàn tất thành công. Nếu validation ném ngoại lệ, đối tượng không được trả về cho người gọi.

## 5. Ví dụ đối chiếu ba cách khởi tạo trong một chương trình

Tạo file **`RecordConstructorDemo.java`**:

~~~java
import java.util.Objects;

// 1. Không tự viết constructor: compiler sinh canonical constructor.
record Point(int x, int y) {
}

// 2. Canonical constructor dạng đầy đủ: tự gán field.
record FullName(String first, String last) {

    public FullName(String first, String last) {
        this.first = requireNonBlank(first, "first");
        this.last = requireNonBlank(last, "last");
    }

    private static String requireNonBlank(String value, String label) {
        Objects.requireNonNull(value, label);

        String normalized = value.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(label + " không được rỗng");
        }

        return normalized;
    }
}

// 3. Compact constructor: compiler gán field sau khi kiểm tra.
record Percentage(int value) {

    public Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "Giá trị phải thuộc khoảng 0..100");
        }
    }
}

public class RecordConstructorDemo {
    public static void main(String[] args) {
        Point point = new Point(2, 5);
        FullName name = new FullName("  An  ", "  Nguyen ");
        Percentage percentage = new Percentage(75);

        System.out.println(point);
        System.out.println(name);
        System.out.println(percentage);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 RecordConstructorDemo.java
java RecordConstructorDemo
~~~

Kết quả:

~~~text
Point[x=2, y=5]
FullName[first=An, last=Nguyen]
Percentage[value=75]
~~~

Bài học từ ví dụ: **cả ba record đều có canonical constructor**, nhưng chỉ hai record cuối khai báo constructor tường minh. Khác nhau chủ yếu nằm ở **nơi thực hiện phép gán vào field**.

## 6. Quy tắc cú pháp và khả năng truy cập

### 6.1. Tên và thành phần của canonical constructor phải khớp record header

Với khai báo:

~~~java
record Coordinate(double latitude, double longitude) {
}
~~~

Canonical constructor dạng đầy đủ phải nhận đúng `double latitude, double longitude` theo thứ tự đó. Compact constructor không viết danh sách tham số nhưng vẫn có hai tham số ngầm định tương ứng.

Một constructor nhận tập tham số khác là constructor quá tải (*overload*) và phải tuân theo quy tắc chuyển tiếp về canonical constructor.

### 6.2. Access modifier phải phù hợp mức truy cập của record

Canonical constructor tường minh không được có mức truy cập **hẹp hơn** record chứa nó.

Ví dụ, record `public` phải có canonical constructor tường minh được công khai:

~~~java
// File CustomerId.java
public record CustomerId(long value) {

    public CustomerId {
        if (value <= 0) {
            throw new IllegalArgumentException("ID phải dương");
        }
    }
}
~~~

Nếu khai báo một canonical constructor tường minh dạng package-private hoặc `private` cho một `public record`, trình biên dịch sẽ từ chối.

Với record package-private, canonical constructor không nhất thiết phải `public`; nhưng ví dụ trong bài thường ghi `public` để ý định truy cập dễ đọc. Khi không có canonical constructor tường minh, compiler tự sinh constructor với quyền truy cập tương ứng record.

### 6.3. Những hạn chế của canonical constructor

Dù viết đầy đủ hay compact, canonical constructor:

- Không khai báo tham số kiểu riêng (constructor generic).
- Không được khai báo mệnh đề `throws`.
- Không thể gọi constructor khác bằng lời gọi tường minh `this(...)` hoặc `super(...)` trong thân canonical constructor.
- Phải duy trì khởi tạo đúng tất cả record components.

Riêng **compact constructor** còn có các quy tắc:

- Không có danh sách tham số trong khai báo.
- Không cho phép gán trực tiếp vào các field tương ứng với record component.
- Không được dùng câu lệnh `return` để thoát thân constructor.

Nếu cần validation có thể ném ngoại lệ checked, hãy thiết kế cách biểu diễn lỗi khác phù hợp với API, chẳng hạn chuyển đổi sang ngoại lệ unchecked có ý nghĩa khi dữ liệu không hợp lệ. Không viết `throws IOException` trên canonical constructor.

### 6.4. Không thể tự thêm instance field cho record

Record gắn trạng thái chính thức với danh sách component trong header. Do đó, khai báo thêm instance field như sau là không hợp lệ:

~~~java
record Rectangle(int width, int height) {
    // Không hợp lệ: record không cho khai báo thêm instance field.
    // private final int area;
}
~~~

Nếu muốn tính diện tích, hãy dùng phương thức:

~~~java
record Rectangle(int width, int height) {

    public Rectangle {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException();
        }
    }

    public long area() {
        return (long) width * height;
    }
}
~~~

Record vẫn có thể khai báo **static field**, static method và các method riêng, miễn tuân theo những quy tắc của ngôn ngữ.

## 7. Overloaded constructor phải ủy quyền về canonical constructor

Record vẫn hỗ trợ constructor quá tải để đưa ra những cách tạo đối tượng tiện lợi. Tuy nhiên, **mỗi non-canonical constructor phải bắt đầu bằng lời gọi `this(...)`** chuyển tiếp sang một constructor khác của chính record, cuối cùng đến canonical constructor.

Ví dụ: một khoảng ngày có thể được tạo bằng hai ngày hoặc bằng một ngày duy nhất.

~~~java
import java.time.LocalDate;
import java.util.Objects;

record DateRange(LocalDate start, LocalDate end) {

    // Canonical constructor dạng compact:
    public DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException("Khoảng ngày không hợp lệ");
        }
    }

    // Constructor quá tải: ủy quyền về canonical constructor.
    public DateRange(LocalDate singleDay) {
        this(singleDay, singleDay);
    }
}
~~~

Ví dụ gọi:

~~~java
LocalDate today = LocalDate.of(2026, 11, 15);

DateRange oneDay = new DateRange(today);
DateRange severalDays = new DateRange(today, today.plusDays(7));

System.out.println(oneDay.start());      // 2026-11-15
System.out.println(severalDays.end());   // 2026-11-22
~~~

Cả hai đường tạo đối tượng đều đi qua compact canonical constructor, nên đều được kiểm tra null và thứ tự ngày.

Đoạn sau không hợp lệ:

~~~java
record NumberBox(int value) {
    // Constructor quá tải sai: không gọi this(...) trước tiên.
    public NumberBox(String text) {
        // int parsed = Integer.parseInt(text);
        // this(parsed);
    }
}
~~~

Cách sửa:

~~~java
record NumberBox(int value) {
    public NumberBox(String text) {
        this(Integer.parseInt(text));
    }
}
~~~

Nếu cần biến đổi dữ liệu trước khi gọi constructor, bạn có thể sử dụng một static helper method trong biểu thức tham số của `this(...)`.

Trong nhiều trường hợp, **static factory method** có tên mô tả ý nghĩa như `of(...)`, `fromText(...)` hoặc `fromCelsius(...)` giúp API dễ đọc hơn việc tạo quá nhiều constructor quá tải.

## 8. Chọn canonical dạng đầy đủ hay compact trong dự án thực tế?

Hai cách đều có thể xác thực và chuẩn hóa. Chọn cách nào phụ thuộc vào mức độ cần kiểm soát chi tiết của quá trình khởi tạo.

| Nhu cầu | Nên chọn | Ví dụ |
|---|---|---|
| Không cần kiểm tra, dữ liệu chỉ là một nhóm giá trị | Constructor ngầm định | `record Point(int x, int y) {}` |
| Kiểm tra range, null, quan hệ giữa các component | Compact constructor | `start` không được sau `end` |
| Chuẩn hóa khoảng trắng, đổi kiểu biểu diễn đầu vào mà giữ nguyên record components | Compact constructor | `code = code.strip().toUpperCase(Locale.ROOT)` |
| Muốn viết tường minh các phép gán component sau khi tính toán hoặc kiểm soát riêng từng bước khởi tạo | Canonical dạng đầy đủ | `this.first = normalize(first)` |
| Muốn hỗ trợ thêm cách khởi tạo với bộ tham số khác | Constructor quá tải chuyển tiếp vào canonical | `new DateRange(singleDay)` |
| Muốn biểu đạt ý nghĩa của nhiều cách tạo đối tượng | Static factory method | `DateRange.oneDay(date)` |

**Khuyến nghị thực hành:** Khi chỉ cần xác thực hoặc chuẩn hóa tham số, compact constructor thường dễ bảo trì vì bạn không phải lặp lại việc gán field. Dùng canonical dạng đầy đủ khi chính việc gán các component cần được trình bày và kiểm soát tường minh.

### 8.1. Compact constructor phù hợp để tạo defensive copy

Record component là `private final`, nhưng **`final` chỉ ngăn thay đổi tham chiếu field**, không làm đối tượng được tham chiếu trở nên bất biến. Nếu component là một collection có thể thay đổi, việc giữ nguyên tham chiếu đầu vào có thể khiến trạng thái quan sát được của record thay đổi từ bên ngoài.

Ví dụ nên tránh:

~~~java
import java.util.List;

record Team(List<String> members) {
    // Constructor ngầm định giữ đúng tham chiếu List đầu vào.
}
~~~

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>(List.of("An", "Binh"));
Team team = new Team(names);

names.add("Chi");
System.out.println(team.members()); // [An, Binh, Chi]
~~~

Nếu muốn lưu danh sách không thể sửa qua API của `List`, hãy sao chép ở constructor:

~~~java
import java.util.List;
import java.util.Objects;

record Team(List<String> members) {

    public Team {
        Objects.requireNonNull(members, "members");
        members = List.copyOf(members);
    }
}
~~~

Sau đó, thay đổi danh sách gốc không làm thay đổi danh sách đã lưu trong record; `team.members().add("Chi")` sẽ ném `UnsupportedOperationException`.

**Giới hạn cần nhớ:** `List.copyOf` tạo bản sao không thể sửa của cấu trúc danh sách, nhưng **không deep-copy các object phần tử**. Nếu phần tử là object có trạng thái thay đổi được, trạng thái quan sát qua collection vẫn có thể thay đổi. Với mảng, chỉ dùng field `final` càng không đủ: phải cân nhắc sao chép mảng lúc nhận vào và khi trả ra từ accessor. Ngoài ra, `equals`/`hashCode` được sinh cho record chứa mảng áp dụng ngữ nghĩa tham chiếu của mảng, nên collection thường phù hợp hơn khi muốn so sánh theo nội dung.

### 8.2. Canonical constructor là nơi tập trung các bất biến

Một bất biến (*invariant*) là điều kiện phải đúng với mọi đối tượng đã được tạo thành công. Ví dụ `DateRange` yêu cầu `start <= end`. Đặt kiểm tra vào canonical constructor có hai lợi ích:

1. Người gọi không thể bỏ qua kiểm tra bằng cách chọn constructor khác, miễn mọi constructor quá tải đều ủy quyền hợp lệ về canonical constructor.
2. Các phép tạo đối tượng thường dùng cú pháp `new` sẽ nhận cùng một quy tắc; API không cần lặp lại validation ở từng nơi gọi.

Quy tắc này đặc biệt hữu ích khi record đại diện **value object** có yêu cầu hợp lệ rõ ràng: mã tiền tệ, ID nghiệp vụ, khoảng ngày, tỉ lệ, tọa độ, v.v.

## 9. Sai lầm thường gặp

### 9.1. Nhầm compact constructor với constructor không tham số

~~~java
record Price(int amount) {
    public Price {
        if (amount < 0) {
            throw new IllegalArgumentException();
        }
    }
}
~~~

`Price { ... }` **không phải** constructor không tham số. Nó vẫn nhận tham số `int amount` từ record header:

~~~java
new Price(100); // Hợp lệ.
// new Price(); // Không hợp lệ nếu không khai báo thêm overload riêng.
~~~

### 9.2. Tự gán field trong compact constructor

~~~java
// Sai trong compact constructor:
// this.amount = amount;
~~~

Hãy kiểm tra hoặc gán lại **biến tham số** `amount`. Compiler sẽ làm phép gán field sau khi thân compact kết thúc bình thường.

### 9.3. Quên gán component trong canonical dạng đầy đủ

~~~java
record Pair(int left, int right) {
    public Pair(int left, int right) {
        this.left = left;
        // Thiếu this.right = right;
    }
}
~~~

Dùng canonical dạng đầy đủ thì phải gán tất cả component. Đây là một lý do compact constructor hữu ích khi phần logic chỉ là validation.

### 9.4. Viết \`throws\` lên canonical constructor

~~~java
// Ví dụ sai: canonical constructor không có throws clause.
record Payload(String text) {
    // public Payload(String text) throws Exception {
    //     this.text = text;
    // }
}
~~~

Nếu validation đơn thuần từ chối dữ liệu, ngoại lệ unchecked như `IllegalArgumentException` hoặc `NullPointerException` thường thích hợp. Khi API cần xử lý lỗi có thể phục hồi, có thể cân nhắc static factory method hoặc một phương thức parse riêng với hợp đồng lỗi rõ ràng.

### 9.5. Mong có thể sửa component bằng setter sau khi tạo

~~~java
record AccountId(long value) {
}
~~~

Record không cho bạn viết setter kiểu `this.value = newValue` để thay field component sau khởi tạo. Nếu cần một giá trị khác, hãy tạo record mới:

~~~java
AccountId first = new AccountId(10);
AccountId second = new AccountId(20);
~~~

Nếu bài toán cần đối tượng có trạng thái thay đổi liên tục, một class thông thường có thể phù hợp hơn record.

### 9.6. Quên rằng validation sau chuẩn hóa mới là dữ liệu được lưu

Xét:

~~~java
record Label(String value) {
    public Label {
        value = value.strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("Nhãn không được rỗng");
        }
    }
}
~~~

Nếu đầu vào chỉ gồm khoảng trắng, `strip()` tạo chuỗi rỗng và validation ném lỗi. Nếu đầu vào là `"  Java  "`, giá trị lưu lại là `"Java"`. Việc validate trên dạng đã chuẩn hóa thường có ý nghĩa hơn việc chỉ kiểm tra chuỗi gốc.

Lưu ý cần kiểm tra null trước khi gọi `strip()` nếu API có thể nhận null.

## 10. Bài tập thực hành

### Bài 1: Chuyển từ canonical dạng đầy đủ sang compact

Cho code:

~~~java
record Age(int years) {

    public Age(int years) {
        if (years < 0 || years > 150) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
        this.years = years;
    }
}
~~~

Hãy viết lại bằng compact constructor và giải thích vì sao có thể bỏ `this.years = years`.

**Đáp án gợi ý:**

~~~java
record Age(int years) {

    public Age {
        if (years < 0 || years > 150) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
    }
}
~~~

Compiler tự thực hiện phép gán `this.years = years` sau khi thân compact constructor kết thúc bình thường.

### Bài 2: Chuẩn hóa mã sản phẩm

Hãy tạo `record ProductCode(String value)` sao cho:

- Null không được chấp nhận.
- Khoảng trắng đầu/cuối bị loại bỏ.
- Chữ cái được chuyển thành chữ hoa theo `Locale.ROOT`.
- Kết quả không được rỗng.

**Đáp án tham khảo:**

~~~java
import java.util.Locale;
import java.util.Objects;

record ProductCode(String value) {

    public ProductCode {
        Objects.requireNonNull(value, "value");
        value = value.strip().toUpperCase(Locale.ROOT);

        if (value.isEmpty()) {
            throw new IllegalArgumentException("Mã sản phẩm rỗng");
        }
    }
}
~~~

### Bài 3: Phát hiện lỗi khi khai báo constructor

Xét:

~~~java
record Interval(int start, int end) {

    public Interval {
        if (start > end) {
            throw new IllegalArgumentException("Khoảng sai");
        }
        // this.start = start;
        // this.end = end;
    }
}
~~~

Nếu bỏ dấu comment ở hai câu lệnh `this.start = start` và `this.end = end`, chuyện gì xảy ra?

**Đáp án:** Compiler báo lỗi vì compact constructor không cho gán trực tiếp vào các field của record components. Giữ chúng ở dạng comment hoặc xóa hoàn toàn.

### Bài 4: Viết overloaded constructor đúng quy tắc

Bổ sung constructor `Interval(int end)` để tạo một khoảng từ `0` đến `end` và vẫn dùng chung validation.

**Đáp án:**

~~~java
record Interval(int start, int end) {

    public Interval {
        if (start > end) {
            throw new IllegalArgumentException("Khoảng sai");
        }
    }

    public Interval(int end) {
        this(0, end);
    }
}
~~~

`new Interval(5)` hợp lệ, trong khi `new Interval(-5)` sẽ bị canonical constructor từ chối vì `0 > -5`.

## 11. Tổng kết khái niệm

Hãy ghi nhớ một mô hình đơn giản:

~~~text
Record header xác định components
          |
          v
  Canonical constructor
          |
          +-- Không khai báo   -> Compiler sinh constructor và gán field
          |
          +-- Dạng đầy đủ     -> Bạn khai báo tham số, kiểm tra và tự gán field
          |
          +-- Compact         -> Bạn kiểm tra/chuẩn hóa tham số,
                                 compiler gán field sau khi thân chạy xong

Constructor quá tải -> phải chuyển tiếp bằng this(...) về canonical constructor
~~~

Khi nhìn thấy `public MyRecord { ... }`, hãy hiểu đó là **compact canonical constructor** nhận các component đã có trong header. Khi nhìn thấy `public MyRecord(Type a, Type b) { ... }` khớp header, hãy nhớ đây là **canonical constructor dạng đầy đủ**, phải gán các field component rõ ràng.

Với nhu cầu **xác thực và chuẩn hóa dữ liệu trong Java 17**, compact constructor thường là cách diễn đạt ngắn và dễ duy trì nhất. Canonical dạng đầy đủ vẫn hữu ích khi cần kiểm soát trực tiếp chi tiết gán dữ liệu.

## 12. Tài liệu tham khảo

- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): trạng thái chính thức của record và mô tả compact constructor.
- [Java Language Specification, Java SE 17 — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): quy tắc record, components, thành viên và constructors.
- [Java Language Specification, Java SE 17 — `8.10.4 Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): đặc tả canonical, compact và overloaded constructors.
- [Oracle Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): tài liệu hướng dẫn record trên Java 17.

