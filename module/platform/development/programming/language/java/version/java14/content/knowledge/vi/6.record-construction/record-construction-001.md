# Canonical constructor tường minh khi khởi tạo record trong Java

> **Phạm vi:** Java 14 – *Khởi tạo record* – **Canonical constructor tường minh**. `record` được giới thiệu dưới dạng preview từ Java 14, nhưng **đã trở thành tính năng chính thức từ Java 16**. Bài này sử dụng **ngữ nghĩa và cú pháp record hiện hành**, chạy với Java 17+ mà không cần `--enable-preview`. Không sử dụng quy tắc của những phiên bản preview đã thay đổi.

## 1. Canonical constructor là gì?

Một `record` mô tả một nhóm dữ liệu với các thành phần (*record components*) được khai báo trong phần đầu:

~~~java
record Point(int x, int y) {}
~~~

Ở đây, `x` và `y` là **record components**. Compiler tạo các thành phần hỗ trợ theo hợp đồng của record, bao gồm:

- Trường lưu dữ liệu `private final` tương ứng với mỗi component.
- Accessor `x()` và `y()` (không phải `getX()`/`getY()` theo quy ước JavaBean).
- Các phương thức `equals`, `hashCode` và `toString` dựa trên thành phần record.
- Một **canonical constructor** nhận **đúng một tham số cho mỗi component theo đúng thứ tự và kiểu**, ví dụ `Point(int x, int y)`.

Khi không khai báo constructor, compiler tạo canonical constructor **ngầm định**, tương đương về ý nghĩa với việc nhận các giá trị và gán cho trường tương ứng. Chẳng hạn `new Point(2, 3)` tạo một `Point` có `x() == 2`, `y() == 3`.

**Canonical constructor tường minh** (*explicit canonical constructor*, dạng thông thường hay *normal canonical constructor*) là constructor do lập trình viên viết với **đầy đủ danh sách tham số**, cho phép kiểm tra và chuẩn hóa dữ liệu, rồi **tự gán các trường final của record**.

Ví dụ tối thiểu, đặt trong một file Java cùng khai báo record:

~~~java
record Point(int x, int y) {
    Point(int x, int y) { // canonical constructor tường minh
        this.x = x;
        this.y = y;
    }
}
~~~

Điểm phân biệt cốt lõi: trong constructor **tường minh dạng đầy đủ**, Java **không tự thêm các phép gán component ở cuối thân hàm**. Người viết phải bảo đảm mỗi trường của component được khởi tạo trên mọi đường đi kết thúc constructor bình thường. Trái lại, **compact canonical constructor** có cơ chế gán tự động ở cuối; xem mục 5.

## 2. Khi nào cần tự viết canonical constructor?

Hãy viết constructor tường minh khi việc tạo record phải thỏa **bất biến dữ liệu** (*invariant*) hoặc cần quyết định giá trị nào thực sự lưu vào các trường:

1. **Kiểm tra đầu vào:** tên không null/rỗng, số lượng phải dương, khoảng giá trị hợp lệ.
2. **Chuẩn hóa:** bỏ khoảng trắng đầu/cuối, chuẩn hóa định dạng theo quy tắc miền dữ liệu.
3. **Sao chép phòng vệ:** tránh bên gọi sửa dữ liệu của record qua `List`/mảng mutable sau khi khởi tạo.
4. **Gán rõ ràng từng trường:** cần thấy rành mạch giá trị cuối cùng của từng component.
5. **Thực thi một điểm khởi tạo thống nhất:** các constructor overload phải đi qua canonical constructor, tránh tạo record không hợp lệ.

Record là kiểu phù hợp với **đối tượng dữ liệu có cấu trúc ổn định**, không tự biến một thiết kế phức tạp nhiều trạng thái thay đổi thành bất biến. Một record không được khai báo thêm trường instance thông thường ngoài những trường được sinh từ components; vẫn có thể khai báo phương thức, constructor overload, static fields/static methods và triển khai interface. Record ngầm định là `final`; không kế thừa một lớp tùy ý.

## 3. Cú pháp và các ràng buộc bắt buộc

Với record sau:

~~~java
public record Product(String sku, int quantity) {
    public Product(String sku, int quantity) {
        // Kiểm tra, chuẩn hóa...
        this.sku = sku;
        this.quantity = quantity;
    }
}
~~~

Hãy nhớ những quy tắc **đang áp dụng trong Java hiện đại**:

| Thành phần | Quy tắc của explicit canonical constructor |
| --- | --- |
| Tên | Trùng chính xác tên record, ở đây là `Product` |
| Danh sách tham số | **Tên, kiểu và thứ tự** tương ứng với toàn bộ record components: `String sku, int quantity` |
| `varargs` | Nếu component dùng `...` thì tham số canonical tương ứng cũng phải là varargs |
| Quyền truy cập | Constructor phải có mức truy cập **ít nhất bằng record**; `public record` đòi hỏi canonical constructor `public` |
| Type parameters | Constructor canonical **không được tự khai báo tham số kiểu generic**; record có thể generic |
| `throws` | Canonical constructor **không được có `throws` clause** |
| `this(...)` / `super(...)` | Thân canonical constructor **không được có explicit constructor invocation** |
| Khởi tạo trường | Mọi component field `final` phải được gán đúng quy tắc definite assignment trước khi constructor hoàn tất bình thường |
| Số lượng canonical constructor | Chỉ có thể có **một** canonical constructor; không khai báo cùng lúc bản đầy đủ và bản compact |

**Giải thích về tên tham số:** riêng canonical constructor, không thể đổi `sku` thành `code` dù cả hai là `String`. Điều kiện khớp tên là quy tắc cụ thể của record, chặt hơn phần lớn constructor của lớp thường.

**Giải thích về visibility:** với `public record Product(...)` ở trên, constructor phải là `public Product(...)`. Với record package-private, constructor canonical có thể package-private hoặc `public` nhưng không thể `private`. Tính năng records ổn định từ Java 16; không dùng quy định cũ của Java 14 preview để quyết định access modifier.

**Về ngoại lệ:** lệnh `throw new IllegalArgumentException(...)` hoặc `throw new NullPointerException(...)` **vẫn hợp lệ** trong constructor. Cấm `throws` clause không có nghĩa là không thể ném unchecked exception. Nếu phải đọc file/gọi API có checked exception, cân nhắc **static factory** bên ngoài canonical constructor (mục 7).

### Record generic vẫn có canonical constructor không generic

~~~java
record Pair<L, R>(L left, R right) {
    Pair(L left, R right) {
        this.left = left;
        this.right = right;
    }
}
~~~

Đây là đoạn khai báo record độc lập hợp lệ: `L` và `R` là **tham số kiểu của record**, không phải type parameters mới do constructor tự khai báo. Constructor có đúng hai tham số từ record header.

## 4. Chương trình hoàn chỉnh: kiểm tra, chuẩn hóa và sao chép phòng vệ

Ví dụ thực tế: record `Member` lưu tên, cấp độ và danh sách vai trò. Hợp đồng đầu vào:

- `name` không null, không chỉ chứa khoảng trắng; giá trị lưu được chuẩn hóa bằng `strip()`.
- `level >= 1`.
- `roles` không null và không bị bên gọi sửa ngầm sau khi khởi tạo.
- Constructor một tham số `Member(String name)` cấp giá trị mặc định hợp lệ bằng cách **gọi canonical constructor**.

Lưu nguyên chương trình vào **`RecordCanonicalDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class RecordCanonicalDemo {

    public record Member(String name, int level, List<String> roles) {

        // Canonical constructor TƯỜNG MINH: đủ tên/kiểu/thứ tự.
        public Member(String name, int level, List<String> roles) {
            String normalizedName =
                    Objects.requireNonNull(name, "name").strip();

            if (normalizedName.isBlank()) {
                throw new IllegalArgumentException("empty name");
            }
            if (level < 1) {
                throw new IllegalArgumentException(
                        "level must be positive");
            }

            List<String> copy = List.copyOf(
                    Objects.requireNonNull(roles, "roles"));

            // Mỗi trường final được gán đúng một lần.
            this.name = normalizedName;
            this.level = level;
            this.roles = copy;
        }

        // Constructor overload: phải ủy quyền tới canonical.
        public Member(String name) {
            this(name, 1, List.of("USER"));
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("READER"));

        Member member = new Member("  An  ", 2, source);
        source.add("WRITER"); // sửa danh sách ban đầu

        System.out.println(member);
        System.out.println(member.roles());
        System.out.println(new Member("Mai"));
        System.out.println(
                member.equals(new Member("An", 2, List.of("READER"))));

        try {
            new Member("  ", 2, List.of());
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        try {
            member.roles().add("ADMIN");
        } catch (UnsupportedOperationException ex) {
            System.out.println("immutable list");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 RecordCanonicalDemo.java
java RecordCanonicalDemo
~~~

**Stdout trong OpenJDK 17+:**

~~~text
Member[name=An, level=2, roles=[READER]]
[READER]
Member[name=Mai, level=1, roles=[USER]]
true
empty name
immutable list
~~~

**Giải thích kết quả:**

1. `"  An  "` được chuẩn hóa thành `"An"` **trước khi** lưu vào `this.name`. Accessor `name()` vì vậy trả tên đã chuẩn hóa.
2. `List.copyOf(source)` tạo/sử dụng một danh sách **không cho sửa** với snapshot nội dung ban đầu. Việc thêm `"WRITER"` vào `source` sau đó không làm thay đổi `member.roles()`.
3. Constructor overload `new Member("Mai")` gọi `this(name, 1, List.of("USER"))`, nên đi qua cùng kiểm tra và khởi tạo.
4. `equals` được compiler cung cấp cho record dựa trên các component; hai `Member` có cùng giá trị được đánh giá bằng nhau. Với `List` chứa các chuỗi, phép so sánh dựa vào nội dung danh sách.
5. Đầu vào tên chỉ có khoảng trắng gây `IllegalArgumentException`; danh sách từ `List.copyOf` gây `UnsupportedOperationException` khi cố sửa.
6. `toString` của record thường hiển thị tên record và component theo dạng trong stdout, hữu ích để debug. Không nên dùng **chuỗi kết quả của `toString`** làm định dạng lưu trữ/giao tiếp ổn định vì nó không phải schema trao đổi dữ liệu.

**Lưu ý về bất biến:** record chỉ có các trường tham chiếu `final`, điều đó **không tự làm đối tượng được tham chiếu bất biến sâu**. `List.copyOf` bảo vệ cấu trúc danh sách; nếu các phần tử là object có thể thay đổi, chúng vẫn có thể bị sửa qua tham chiếu khác. Mảng còn cần xử lý riêng: nếu component là `byte[]`, sao chép trong constructor và khi trả qua accessor nếu muốn chống sửa dữ liệu; ngoài ra, `equals` mặc định của record với component mảng không so sánh nội dung mảng như `Arrays.equals`. Ưu tiên kiểu biểu diễn phù hợp với giá trị nghiệp vụ.

## 5. So sánh ba hình thức canonical constructor

| Hình thức | Cú pháp | Ai gán component fields? | Khi nên dùng |
| --- | --- | --- | --- |
| **Ngầm định** | `record Point(int x, int y) {}` | Compiler | Chỉ cần mang giá trị, không cần xác thực/chuẩn hóa |
| **Compact tường minh** | `Point { ... }` | Compiler gán từ tham số **sau thân khối** | Validate/normalize ngắn gọn |
| **Normal tường minh** | `Point(int x, int y) { ... }` | **Lập trình viên phải tự gán** | Muốn chỉ rõ từng phép gán, luồng tạo dữ liệu và bản sao phòng vệ |

Ví dụ **compact canonical constructor**:

~~~java
import java.util.Objects;

record Label(String value) {
    Label {
        value = Objects.requireNonNull(value, "value").strip();
        if (value.isBlank()) {
            throw new IllegalArgumentException("value is blank");
        }
        // Không viết this.value = value; trong compact constructor.
    }
}
~~~

Ở cuối thân `Label { ... }`, compiler gán trường `this.value` từ tham số `value` đã được chuẩn hóa. Vì vậy, **không được gán trực tiếp vào component field trong compact constructor**. Ví dụ tương đương về ý định bằng **normal explicit canonical constructor**:

~~~java
import java.util.Objects;

record FullLabel(String value) {
    FullLabel(String value) {
        String cleaned = Objects.requireNonNull(value, "value").strip();
        if (cleaned.isBlank()) {
            throw new IllegalArgumentException("value is blank");
        }
        this.value = cleaned; // bắt buộc tự gán trong dạng đầy đủ
    }
}
~~~

Hai record trong các ví dụ có **tên khác nhau** để minh họa độc lập. Trong **cùng một record**, không được khai báo cả `Label(String value)` và `Label { ... }`: đó là hai cách khai báo cùng một canonical constructor, gây lỗi biên dịch.

Dạng compact không “kém hiện đại” hay “kém an toàn” hơn dạng đầy đủ; chọn dạng giúp thể hiện bất biến dễ đọc nhất. Mục tiêu của bài này là hiểu sâu **normal explicit canonical constructor**.

## 6. Constructor overload luôn phải đi qua canonical

Với record có các components `name`, `level`, `roles`, mọi constructor **không canonical** phải có lời gọi **`this(...)`** dẫn đến một constructor khác của cùng record, rồi cuối cùng đi đến canonical constructor:

~~~java
record Access(String code, int ttlSeconds) {

    Access(String code, int ttlSeconds) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code required");
        }
        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("ttl must be positive");
        }
        this.code = code;
        this.ttlSeconds = ttlSeconds;
    }

    Access(String code) {
        this(code, 60); // Java 17–24 cần đặt đầu; Java 25+ cho phép prologue hợp lệ trước this(...)
    }
}
~~~

Đoạn trên là khai báo record độc lập dùng được với Java 16+. `new Access("ABC")` tạo giá trị với `ttlSeconds = 60`. Không thể viết overload chỉ gán một số trường, vì các trường của record phải được khởi tạo thống nhất.

**Phân biệt hai quy tắc quan trọng:**

- Trong **canonical constructor**, không được gọi `this(...)` hay `super(...)` một cách tường minh.
- Trong **noncanonical constructor**, bắt buộc có lời gọi `this(...)` dẫn đến canonical. Đừng nhầm đó là hạn chế chung của **mọi** constructor trong record.

Cách thiết kế này tránh những đường khởi tạo bỏ qua bất biến do canonical constructor xác lập.

**Cập nhật cho Java 25+ (JEP 513 — Flexible Constructor Bodies):** Trong noncanonical record constructor, lời gọi `this(...)` vẫn **bắt buộc**, nhưng từ Java 25 nó không còn bắt buộc là câu lệnh đầu tiên. Ta được phép thực hiện các lệnh kiểm tra và chuẩn bị tham số trong *prologue* trước `this(...)`, miễn tuân thủ các hạn chế về đối tượng chưa khởi tạo (không truy cập trạng thái instance/`this` ở đó). Với Java 17–24, `this(...)` phải là câu lệnh đầu tiên như ví dụ `Access(String code)` phía trên. Ví dụ sau chỉ biên dịch với mức ngôn ngữ **Java 25 trở lên**:

~~~java
record ValidatedAccess(String code, int ttlSeconds) {
    ValidatedAccess {
        if (code == null || code.isBlank()) throw new IllegalArgumentException("code");
        if (ttlSeconds <= 0) throw new IllegalArgumentException("ttl");
    }

    ValidatedAccess(String source) {
        String clean = source == null ? "" : source.strip(); // prologue Java 25+
        this(clean, 60); // ủy quyền tới canonical constructor
    }
}
~~~

`javac --release 17` sẽ không chấp nhận prologue trước `this(...)`; muốn kiểm chứng ví dụ này, dùng JDK 25+ với `--release 25` (hoặc phiên bản sau tương ứng). Nguồn: https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html.

## 7. Xử lý dữ liệu đầu vào, checked exception và static factory

Canonical constructor không được khai báo `throws IOException`, `throws SQLException` hoặc bất kỳ `throws` clause nào. Khi nhận dữ liệu có thể gây lỗi bên ngoài, hãy cân nhắc **static factory** thực hiện I/O và chuyển kết quả vào canonical constructor để xác thực. Không biến checked exception thành unchecked chỉ để lách giới hạn mà không có hợp đồng lỗi rõ ràng.

Ví dụ **khai báo record độc lập**, dùng các import trong chú thích:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

record Config(String value) {

    Config(String value) {
        String cleaned = Objects.requireNonNull(value, "value").strip();
        if (cleaned.isBlank()) {
            throw new IllegalArgumentException("Empty configuration");
        }
        this.value = cleaned;
    }

    static Config fromFile(Path path) throws IOException {
        String content = Files.readString(
                Objects.requireNonNull(path, "path"),
                StandardCharsets.UTF_8);
        return new Config(content);
    }
}
~~~

`Config.fromFile(path)` có thể khai báo checked exception từ I/O, còn mọi đối tượng `Config` hợp lệ vẫn được tạo qua canonical constructor. `Files.readString` phù hợp với file cấu hình nhỏ; file lớn nên đọc theo dòng hoặc theo luồng để tránh giữ toàn bộ nội dung trong bộ nhớ. Static factory là **phương thức thông thường**, không bị hạn chế `throws` như canonical constructor.

Ngoại lệ trong constructor nên mang ý nghĩa rõ: `Objects.requireNonNull` biểu thị một giá trị bị thiếu trái hợp đồng; `IllegalArgumentException` biểu thị dữ liệu có giá trị nhưng vi phạm quy tắc (ví dụ chuỗi rỗng hoặc số âm). Với API công khai, hãy ghi rõ hợp đồng và lỗi có thể xảy ra.

## 8. Các lỗi biên dịch thường gặp

Những đoạn dưới **cố ý sai** để đọc quy tắc của ngôn ngữ; không phải chương trình có thể chạy.

### 8.1. Quên gán một trường

~~~java
record BadPoint(int x, int y) {
    BadPoint(int x, int y) {
        this.x = x;
        // LỖI: trường final y chưa được khởi tạo
    }
}
~~~

**Vì sao sai:** compiler không tự điền `this.y = y` cho dạng canonical đầy đủ. Mọi đường đi hoàn tất bình thường phải khởi tạo `y` đúng quy tắc. Sửa bằng cách thêm `this.y = y;` sau khi kiểm tra các điều kiện liên quan.

### 8.2. Tham số không cùng tên component

~~~java
record BadName(String name) {
    BadName(String other) {
        this.name = other;
    }
    // LỖI: tham số canonical phải tên là name
}
~~~

Chữ ký tương ứng với component `String name` nhưng **tên** formal parameter lại khác, nên không hợp lệ. Sửa thành `BadName(String name)`.

### 8.3. Visibility yếu hơn public record

~~~java
public record PublicId(String value) {
    PublicId(String value) { // LỖI: phải public
        this.value = value;
    }
}
~~~

Với record public, sửa thành `public PublicId(String value)`. Trong một file Java thực, record top-level public phải được lưu với tên tương ứng, ví dụ `PublicId.java`.

### 8.4. Khai báo `throws` trên canonical constructor

~~~java
record BadConfig(String value) {
    BadConfig(String value) throws java.io.IOException {
        this.value = value;
    }
    // LỖI: canonical constructor không được có throws clause
}
~~~

Đưa thao tác có checked exception ra phương thức factory, như ví dụ mục 7.

### 8.5. Gán trường hai lần hoặc khai báo hai canonical constructor

~~~java
record BadAssignment(int count) {
    BadAssignment(int count) {
        this.count = count;
        this.count = 10; // LỖI: final field đã được gán
    }
}
~~~

Một record cũng không được khai báo **cả** `BadAssignment(int count) { ... }` và `BadAssignment { ... }`. Giữ đúng **một** hình thức canonical constructor.

### 8.6. Quên ủy quyền trong constructor overload

~~~java
record BadOverload(String code, int ttl) {
    BadOverload(String code, int ttl) {
        this.code = code;
        this.ttl = ttl;
    }

    BadOverload(String code) {
        // LỖI: thiếu this(code, giá trị_mặc_định)
    }
}
~~~

Sửa thành `BadOverload(String code) { this(code, 60); }`. Không có constructor rỗng mặc định tự động trừ khi record không có component hoặc bạn tự định nghĩa overload hợp lệ.

## 9. Những chi tiết dễ nhầm khi thiết kế record

### 9.1. `final` là cố định tham chiếu, không phải bất biến sâu

~~~java
import java.util.List;

record UnsafeRoles(List<String> roles) {}
~~~

Nếu truyền vào `new ArrayList<>(...)` rồi sửa danh sách đó, thành phần `roles()` có thể thay đổi nội dung dù trường của record là `final`. Điều này làm `equals`, `hashCode` và hành vi quan sát thay đổi theo thời gian. Cách làm hiện đại là quyết định rõ có cần snapshot bất biến hay không, ví dụ sao chép bằng `List.copyOf` trong canonical constructor. `List.copyOf` không cho phép phần tử `null`; phải xét ràng buộc này khi thiết kế dữ liệu. Với phần tử mutable, chỉ sao chép danh sách **không tạo bản sao sâu**.

### 9.2. Validate rồi mới lưu

Trong explicit canonical constructor, dễ kiểm soát khi tạo **biến cục bộ đã chuẩn hóa**, validate mọi giá trị, sau đó mới gán các trường một lần:

~~~java
record UserName(String value) {
    UserName(String value) {
        String cleaned = java.util.Objects
                .requireNonNull(value, "value").strip();

        if (cleaned.length() < 3) {
            throw new IllegalArgumentException("Minimum length is 3");
        }
        this.value = cleaned;
    }
}
~~~

Nếu thao tác validate ném ngoại lệ, đối tượng không được tạo thành công. Tránh gán giá trị chưa hợp lệ rồi viết thêm các phép gán để “sửa lại” trường `final`, vì như vậy vi phạm definite assignment.

### 9.3. Record không thay thế mọi lớp

Record thích hợp với *value carrier* có trạng thái đại diện bằng các components. Nếu thực thể có vòng đời thay đổi thường xuyên (ví dụ một entity cần identity ổn định và cập nhật nhiều field) thì một lớp thông thường có thể phù hợp hơn. Đừng chọn record chỉ vì muốn tự động có `toString`/`equals` nếu mô hình dữ liệu cần các invariant, setter, lifecycle hoặc identity khác biệt.

### 9.4. Dùng công cụ biên dịch đúng phiên bản

Dùng **JDK 17 hoặc mới hơn** cho những ví dụ ở đây, vì record đã ổn định:

~~~bash
javac --release 17 -encoding UTF-8 RecordCanonicalDemo.java
java RecordCanonicalDemo
~~~

`--release 17` giúp compiler dùng tập API/cú pháp tương thích Java 17, nhưng bạn vẫn cần JDK có thể thực thi phiên bản class file sinh ra. Không dùng `--enable-preview`: đó không phải yêu cầu của record hiện hành. Nếu một dự án buộc dùng Java 14, record thời đó là preview; không nên trình bày bản preview ấy như một lựa chọn production hiện tại.

## 10. Checklist trước khi viết explicit canonical constructor

- [ ] Record header có đúng các components, kiểu, thứ tự và ý nghĩa dữ liệu mong muốn.
- [ ] Constructor đầy đủ có **cùng tên record**, cùng tên/kiểu/thứ tự tham số; visibility hợp lệ.
- [ ] Không có type parameters riêng, `throws` clause hay explicit `this(...)`/`super(...)` trong **canonical** constructor.
- [ ] Đầu vào cần thiết được validate/normalize theo quy tắc nghiệp vụ hiện hành.
- [ ] Từng component field `final` được gán đúng một lần trên mọi đường đi hoàn tất bình thường.
- [ ] Mọi constructor overload đều ủy quyền qua `this(...)` đến canonical constructor.
- [ ] Với `List`, mảng hoặc đối tượng mutable, đã quyết định phòng vệ dữ liệu đầu vào/đầu ra và ngữ nghĩa `equals`.
- [ ] Không khai báo cùng lúc canonical dạng đầy đủ và dạng compact.
- [ ] Các ví dụ biên dịch với Java 17+ mà không yêu cầu preview.

## 11. Bài tập thực hành

1. Tạo `record Temperature(double celsius)` với canonical constructor tường minh chỉ chấp nhận giá trị `Double.isFinite(celsius)` và cao hơn độ không tuyệt đối (`-273.15` °C). Kiểm tra các tình huống `Double.NaN`, vô cực và `-300`.
2. Tạo `record Email(String value)`; kiểm tra null, blank và chuẩn hóa khoảng trắng theo hợp đồng. Cần phân biệt **validate** với **tự đổi toàn bộ thành chữ thường**, vì phần địa chỉ email phía trước `@` có thể có ngữ nghĩa phân biệt hoa/thường theo hệ thống nhận thư.
3. Thêm overload `Member(String name)` cho record 3 components và giải thích vì sao phải gọi `this(name, 1, List.of("USER"))`.
4. Chuyển canonical constructor tường minh của `Label` thành compact constructor, rồi viết ngược lại. Chỉ ra ai chịu trách nhiệm gán `this.value` ở mỗi dạng.
5. Tạo record chứa `List<String>`, so sánh hành vi **không sao chép**, `List.copyOf` và thử chỉnh sửa danh sách gốc sau khi tạo.
6. Thử bỏ phép gán `this.y = y` trong `Point(int x, int y)` rồi đọc lỗi compiler. Thử đổi tham số `y` thành `other` và quan sát lỗi khác.
7. Viết static factory `fromFile(Path) throws IOException` cho một record; để canonical constructor chỉ validate dữ liệu đã đọc.

### Tham khảo chuẩn Java

- [Java Language Specification – Record Classes, `8.10](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10)
- [Java Language Specification – Normal Canonical Constructors, `8.10.4.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4.1)
- [Java Language Specification – Compact Canonical Constructors, `8.10.4.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4.2)

**Ghi nhớ:** canonical constructor là điểm khởi tạo chuẩn của record. Khi khai báo **tường minh dạng đầy đủ**, bạn phải giữ đúng chữ ký component, kiểm tra/chuẩn hóa dữ liệu và **tự khởi tạo đầy đủ các trường `final`**. Mọi overload phải đi qua nó; compact constructor là dạng ngắn hơn có cơ chế gán tự động.