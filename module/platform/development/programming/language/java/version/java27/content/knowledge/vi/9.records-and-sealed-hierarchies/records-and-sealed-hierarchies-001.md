# Record, component và các thành viên được sinh tự động

> Phạm vi: Java 27, chương “Records và hệ phân cấp sealed”. Bài học tập trung vào cú pháp `record`, ý nghĩa của record component, các field/phương thức/constructor do trình biên dịch cung cấp và cách tùy chỉnh đúng hợp đồng. Record là tính năng chính thức từ Java 16 (JEP 395) và tiếp tục được hỗ trợ trong Java 27; các ví dụ dưới đây không cần bật preview.

## 1. Record giải quyết vấn đề gì?

Trong Java, nhiều kiểu dữ liệu chỉ cần mang một nhóm giá trị có tên: tọa độ, khoảng thời gian, kết quả tìm kiếm, yêu cầu đầu vào hoặc kết quả của một phép tính. Với lớp thông thường, lập trình viên phải lặp lại nhiều khai báo như field, constructor, accessor, `equals`, `hashCode` và `toString`.

`record` cho phép mô tả trực tiếp **dữ liệu cấu thành trạng thái** trong phần header. Trình biên dịch tạo các thành viên cần thiết theo một hợp đồng thống nhất:

~~~java
public record Point(int x, int y) {}
~~~

Sử dụng:

~~~java
Point first = new Point(3, 5);
Point second = new Point(3, 5);

System.out.println(first.x());        // 3
System.out.println(first.y());        // 5
System.out.println(first.equals(second)); // true
System.out.println(first);            // dạng như Point[x=3, y=5]
~~~

Hai instance khác nhau vẫn có thể bằng nhau theo **giá trị các component**. Đây là hành vi khác với `equals` mặc định dựa trên identity của một lớp thông thường không tự override phương thức này.

Record phù hợp khi toàn bộ trạng thái của đối tượng được mô tả công khai bởi các component và đối tượng nên có ngữ nghĩa giá trị. Record không phải cơ chế tự động biến mọi đối tượng thành bất biến sâu; phần đó sẽ được làm rõ bên dưới.

## 2. Cú pháp và record component

Cú pháp tổng quát của một record:

~~~java
[modifiers] record Name<TypeParameters>(
        ComponentType component1,
        ComponentType component2
) implements SomeInterface {
    // constructor, method, static member nếu cần
}
~~~

Ví dụ với mô hình dữ liệu thực tế:

~~~java
import java.time.Instant;

public record AuditEvent(
        String eventId,
        Instant occurredAt,
        String actor,
        boolean successful
) {}
~~~

Mỗi khai báo trong cặp ngoặc sau tên record là một **record component**. Một component có:

- **Kiểu**: primitive như `int`, `boolean` hoặc kiểu tham chiếu như `String`, `Instant`, `List<String>`.
- **Tên**: dùng để xác định field, tên accessor và tên tham số tương ứng của canonical constructor.
- **Vị trí**: thứ tự khai báo ảnh hưởng thứ tự tham số constructor và thông tin thành phần phản ánh qua reflection.
- **Annotation**, nếu có: có thể gắn lên component và, tùy `@Target`, được áp dụng cho field, accessor, tham số constructor hoặc kiểu sử dụng.
- **Varargs** ở component cuối cùng, nếu cần; bản chất kiểu lưu trữ vẫn là mảng.

Ví dụ record generic và record không có component:

~~~java
record Pair<L, R>(L left, R right) {}

record Empty() {}
~~~

Một record được phép có **0 component**. Hãy chỉ dùng dạng này khi mô hình nghiệp vụ thực sự cần một giá trị đánh dấu không chứa dữ liệu.

### 2.1. Component khác với field khai báo thủ công

Khai báo `record Point(int x, int y) {}` cho trình biên dịch đủ thông tin để tạo các thành viên tương tự bảng sau:

| Khai báo trong header | Thành viên được cung cấp | Cách sử dụng |
| --- | --- | --- |
| `int x` | Field instance `private final int x` | Chỉ đọc nội bộ record |
| `int x` | Accessor `public int x()` | `point.x()` |
| `int y` | Field instance `private final int y` | Chỉ đọc nội bộ record |
| `int y` | Accessor `public int y()` | `point.y()` |
| Danh sách `(int x, int y)` | Canonical constructor tương ứng | `new Point(3, 5)` |
| Toàn bộ component | `equals`, `hashCode`, `toString` | So sánh, băm, hiển thị |

Đây là **diễn giải về thành viên và hành vi**, không phải gợi ý tự viết lại toàn bộ các field bên trong record. Các field component do compiler khai báo ngầm; bạn không được khai báo trùng chúng trong phần thân.

Một record component không phải là một field do người dùng tự khai báo, cũng không phải là một constructor parameter được viết trong record body. Nó là thành phần của **record descriptor**; từ descriptor đó, Java suy ra các thành viên liên quan.

### 2.2. Quy tắc tên và vị trí

Tên component không được trùng nhau; một số tên trùng với phương thức không tham số của `Object` như `hashCode`, `toString`, `getClass`, `wait`, `notify` cũng không hợp lệ.

Component kiểu varargs chỉ được phép ở vị trí cuối cùng:

~~~java
record Command(String name, String... arguments) {}
~~~

`arguments` có kiểu thực tế `String[]`. Có thể gọi `new Command("copy", "a.txt", "b.txt")`, nhưng mảng là mutable và cần bảo vệ nếu muốn đối tượng thực sự bất biến.

## 3. Canonical constructor được sinh tự động

Một record luôn có một **canonical constructor** dùng để khởi tạo toàn bộ các component. Nếu bạn không tự khai báo, compiler cung cấp constructor với tham số tương ứng **đúng kiểu và đúng thứ tự** trong header:

~~~java
public record Point(int x, int y) {}
~~~

Về mặt hành vi khởi tạo, constructor ngầm tương đương với:

~~~java
public Point(int x, int y) {
    this.x = x;
    this.y = y;
}
~~~

Đoạn thứ hai chỉ minh họa phần thân của canonical constructor nếu được viết tường minh bên trong `Point`; không đặt nó thành constructor tự do ngoài record.

Với record public, canonical constructor cần có mức truy cập public; với record không có modifier truy cập ở top level, constructor được sinh có package access. Nếu khai báo constructor một cách tường minh, mức truy cập của nó phải ít nhất rộng bằng record theo quy tắc JLS.

### 3.1. Thêm kiểm tra đầu vào bằng compact canonical constructor

Khi cần bảo đảm invariant, thường dùng **compact constructor**:

~~~java
import java.util.Objects;

public record UserProfile(String username, int age) {
    public UserProfile {
        Objects.requireNonNull(username, "username");
        if (username.isBlank()) {
            throw new IllegalArgumentException(
                    "username must not be blank");
        }
        if (age < 0) {
            throw new IllegalArgumentException(
                    "age must not be negative");
        }
    }
}
~~~

Trong cú pháp `public UserProfile { ... }`:

1. Java ngầm cung cấp các tham số có cùng tên và kiểu với component.
2. Bạn kiểm tra hoặc chuẩn hóa **tham số** trong phần thân.
3. Nếu constructor kết thúc bình thường, compiler tự gán giá trị cuối cùng của từng tham số vào field tương ứng, theo thứ tự component.

Bạn không cần viết `this.username = username;` trong compact constructor và không được gán trực tiếp vào field component trong phần thân compact constructor.

### 3.2. Chuẩn hóa component trước khi gán

Compact constructor cho phép thay đổi giá trị tham số trước khi lưu:

~~~java
import java.util.Locale;
import java.util.Objects;

public record AccountCode(String value) {
    public AccountCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Empty account code");
        }
    }
}
~~~

Với `new AccountCode("  ab-12  ")`, `value()` trả về `"AB-12"`. Việc chuẩn hóa diễn ra **trước khi** dữ liệu được lưu trong field.

Điều kiện phải kiểm tra cần xuất phát từ nghiệp vụ. Chẳng hạn, việc ép chữ hoa chỉ phù hợp nếu mã tài khoản có quy tắc so sánh không phân biệt hoa/thường; không áp dụng cho mật khẩu, token hay dữ liệu phân biệt chữ hoa và chữ thường.

### 3.3. Canonical constructor đầy đủ

Bạn cũng có thể viết đầy đủ tham số và gán field khi cần kiểm soát trình tự khởi tạo:

~~~java
public record Rectangle(int width, int height) {
    public Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException(
                    "Dimensions must be positive");
        }
        this.width = width;
        this.height = height;
    }
}
~~~

Canonical constructor đầy đủ cần khớp với descriptor của record, tuân thủ các hạn chế của canonical constructor như không generic, không có `throws` clause và không gọi constructor khác một cách tường minh.

Chỉ được có **một** canonical constructor: chọn phiên bản ngầm, compact hoặc tường minh. Không khai báo đồng thời compact và một constructor đầy đủ cùng chữ ký.

### 3.4. Constructor bổ sung phải chuyển tiếp đến canonical constructor

Record có thể có constructor overload nhằm cung cấp giá trị mặc định:

~~~java
public record RetryPolicy(int maxAttempts, long delayMillis) {
    public RetryPolicy {
        if (maxAttempts < 1 || delayMillis < 0) {
            throw new IllegalArgumentException("Invalid retry policy");
        }
    }

    public RetryPolicy(int maxAttempts) {
        this(maxAttempts, 1_000L);
    }
}
~~~

Một constructor không phải canonical phải gọi constructor khác của chính record bằng `this(...)`, cuối cùng đi qua canonical constructor. Như vậy mọi đường khởi tạo đều chịu cùng một hợp đồng và bước kiểm tra.

## 4. Accessor được sinh tự động

Với component `name` kiểu `String`, Java sinh accessor `public String name()`; với `active` kiểu `boolean`, accessor là `active()`.

~~~java
record Member(String name, boolean active) {}

var member = new Member("Lan", true);
System.out.println(member.name());   // Lan
System.out.println(member.active()); // true
~~~

Record không tự sinh các phương thức kiểu JavaBeans như `getName()` hay `isActive()`. Nếu một framework cần JavaBeans convention, cần kiểm tra khả năng hỗ trợ record của framework đó hoặc cấu hình mapping tương ứng.

Accessor ngầm trả về **giá trị của field component**, không thực hiện defensive copy. Với reference component, nó trả cùng tham chiếu đã lưu. Đối với `String` hoặc `LocalDate`, cách này thường ổn vì các kiểu đó bất biến. Với mảng hoặc collection mutable, cần đánh giá thêm.

### 4.1. Ghi đè accessor và phép so sánh khi dữ liệu mutable

Ví dụ record chứa `byte[]`:

~~~java
import java.util.Arrays;
import java.util.Objects;

public record Payload(byte[] bytes) {
    public Payload {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Payload p
                && Arrays.equals(bytes, p.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }

    @Override
    public String toString() {
        return "Payload[size=" + bytes.length + "]";
    }
}
~~~

Constructor sao chép đầu vào; accessor trả bản sao ở đầu ra. Hai bước chặn việc caller thay đổi trạng thái qua mảng được chia sẻ. Trong ví dụ này, `equals` và `hashCode` cũng được viết tường minh theo **nội dung byte** để giữ hợp đồng giá trị của record khi tái tạo đối tượng từ accessor. `toString` chỉ cung cấp kích thước mà không in toàn bộ byte.

Nếu bỏ hai phương thức so sánh tùy chỉnh, record có mảng sẽ dùng `equals`/`hashCode` mặc định theo **identity của mảng**: một record được tạo lại từ `bytes()` sẽ chứa một mảng sao chép khác và không còn bằng record gốc. Vì vậy, defensive copy đơn thuần chưa đủ trong trường hợp này. Khi có thể, hãy ưu tiên kiểu component bất biến vốn đã có value equality phù hợp để không phải tự viết lại các phương thức này.

### 4.2. Ràng buộc đối với accessor viết tường minh

Accessor tự viết phải là phương thức instance `public`, không tham số, có kiểu trả về đúng với component. Nó không được là generic method và không được có `throws` clause.

Khi tự viết accessor, hãy giữ **tính minh bạch của record**: accessor phải biểu diễn chính xác component đã dùng để tạo đối tượng. Không âm thầm trả một giá trị khác với field, như cắt ngưỡng, ẩn dữ liệu hoặc thay đổi ý nghĩa của component. Nếu cần một góc nhìn biến đổi, hãy đặt tên phương thức khác như `displayName()` hay `maskedId()`.

## 5. equals(Object) được sinh theo component

Nếu không override, compiler cung cấp `equals(Object)` để so sánh hai instance của **cùng một record class** theo các component tương ứng.

~~~java
record ProductKey(String sku, int version) {}

var a = new ProductKey("SKU-01", 2);
var b = new ProductKey("SKU-01", 2);
var c = new ProductKey("SKU-01", 3);

System.out.println(a == b);      // false: hai object khác nhau
System.out.println(a.equals(b)); // true: component giống nhau
System.out.println(a.equals(c)); // false
~~~

Quy tắc ở mức khái niệm:

- Với component tham chiếu, dùng ngữ nghĩa so sánh của `equals` tương ứng (có xử lý null).
- Với primitive, áp dụng ngữ nghĩa so sánh của wrapper tương ứng, kể cả trường hợp `float` và `double`.
- Việc so sánh dùng giá trị **field component**, không gọi accessor tùy chỉnh để lấy giá trị so sánh.

### 5.1. Hai trường hợp dấu phẩy động đáng chú ý

Đối với `double` và `float`, ngữ nghĩa sinh tự động giống `Double.compare`/`Float.compare` hơn là toán tử `==`:

~~~java
record Reading(double value) {}

System.out.println(
        new Reading(Double.NaN).equals(new Reading(Double.NaN))
); // true

System.out.println(
        new Reading(+0.0).equals(new Reading(-0.0))
); // false
~~~

NaN được coi bằng NaN theo hợp đồng `Double.compare`; `+0.0` và `-0.0` là các giá trị biểu diễn khác nhau nên không bằng nhau theo `equals` mặc định của record. Điều này giúp hợp đồng `equals`/`hashCode` nhất quán, ngay cả khi cách so sánh không giống `doubleValue1 == doubleValue2`.

### 5.2. Mảng so sánh theo identity

~~~java
record Blob(byte[] data) {}

var one = new Blob(new byte[] {1, 2});
var two = new Blob(new byte[] {1, 2});

System.out.println(one.equals(two)); // false
~~~

Mỗi mảng là một đối tượng khác nhau; `byte[]` không tự override `Object.equals` để so sánh nội dung. Tương tự, `hashCode` dựa trên hash của mảng, không tự gọi `Arrays.hashCode`. Nếu dùng record làm key, hãy ưu tiên component có hợp đồng `equals`/`hashCode` theo giá trị và có trạng thái bất biến.

## 6. hashCode() được sinh theo component

Trình biên dịch cung cấp `hashCode()` dựa trên các component sao cho hai record bằng nhau phải có hash code bằng nhau. Ví dụ:

~~~java
record Coordinate(int x, int y) {}

var p1 = new Coordinate(8, 13);
var p2 = new Coordinate(8, 13);

System.out.println(p1.equals(p2));           // true
System.out.println(p1.hashCode() == p2.hashCode()); // true
~~~

JLS không bảo đảm một **giá trị hash cụ thể** hoặc thuật toán phối hợp hash cố định để bạn lưu vào database hay truyền qua giao thức. Vì vậy:

- Không hard-code một giá trị hash mong đợi trong test.
- Không dùng `hashCode()` làm mã định danh lâu dài hoặc checksum.
- Không dựa vào hash code giữa các lần chạy/JDK khác nhau nếu tài liệu không cam kết.
- Không thay đổi các đối tượng mutable được dùng trong component của record đang là key `HashMap`/`HashSet`.

Nếu override `equals`, cần override `hashCode` theo cùng cách hiểu về bình đẳng; nếu không, key có thể hoạt động sai trong cấu trúc hash-based.

## 7. toString() được sinh theo cấu trúc record

`toString()` mặc định chứa tên record, tên component và biểu diễn giá trị của chúng:

~~~java
record Coordinate(int x, int y) {}

System.out.println(new Coordinate(8, 13));
// Dạng thường thấy: Coordinate[x=8, y=13]
~~~

Đây là biểu diễn tiện cho đọc log, debug và test thăm dò. **Không coi định dạng chuỗi của `toString` là giao thức serialization**: đặc tả cho phép chi tiết định dạng thay đổi, nên không parse chuỗi này để khôi phục dữ liệu. Dùng JSON mapper, định dạng nhị phân hoặc API encoding có hợp đồng khi cần giao tiếp giữa hệ thống.

Nếu record mang mật khẩu, access token, số thẻ hoặc dữ liệu riêng tư, `toString()` mặc định có thể đưa giá trị component vào log. Trong trường hợp này, cân nhắc dùng lớp có mô hình dữ liệu phù hợp hơn, hoặc tự override `toString` để che/loại bỏ dữ liệu nhạy cảm. Hợp đồng `equals` và cấu trúc component vẫn cần được giữ nhất quán.

## 8. Các thành viên nào có thể viết thêm trong record?

Record là một dạng class có quy tắc riêng. Bên cạnh các thành viên bắt buộc từ component, bạn có thể khai báo:

- Phương thức instance bổ sung để biểu diễn tính toán **không thay đổi** record.
- Phương thức `static` như factory, parser hoặc bộ kiểm tra.
- Field `static` và khối khởi tạo `static` khi thực sự cần.
- Các nested type và việc implement interface phù hợp.
- Canonical constructor/constructor overload theo các quy tắc đã nêu.
- Implement riêng `equals`, `hashCode`, `toString` và accessor khi có nhu cầu, nhưng phải giữ hợp đồng của record.

Ví dụ:

~~~java
public record Money(long cents) {
    public Money {
        if (cents < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
    }

    public Money plus(Money other) {
        return new Money(Math.addExact(
                cents, java.util.Objects.requireNonNull(other).cents()
        ));
    }

    public static Money zero() {
        return new Money(0);
    }
}
~~~

`plus` tạo một record mới, không sửa instance ban đầu. `Math.addExact` ngăn phép cộng số nguyên âm thầm tràn; điều đó quan trọng khi tiền đang được lưu theo đơn vị nhỏ nhất.

### 8.1. Các giới hạn cần nhớ

Record:

- Ngầm là `final`; không thể được subclass.
- Trực tiếp kế thừa `java.lang.Record` và không được viết `extends` để chọn superclass khác.
- Có thể `implements` một hoặc nhiều interface.
- Không được khai báo field instance bổ sung (non-static), instance initializer, hoặc phương thức `abstract`/`native` trong body.
- Không thể khai báo thành `abstract`, `sealed` hay `non-sealed`.
- Không có setter mặc định và không gán lại được các field component `final` sau khi khởi tạo.

Bảng phân biệt:

| Mục đích | Record | Class thông thường |
| --- | --- | --- |
| Mô hình dữ liệu có cấu trúc và hợp đồng theo giá trị | Rất phù hợp | Có thể nhưng viết nhiều thành viên |
| Cần nhiều field instance ẩn không nằm trong hợp đồng dữ liệu | Không phù hợp | Phù hợp |
| Cần kế thừa class hoặc thay đổi trạng thái thường xuyên | Không phù hợp | Phù hợp |
| Implement interface | Có | Có |
| Tham gia một sealed hierarchy với vai trò nhánh cuối | Có, vì record ngầm final | Có, theo quy tắc permits |
| Cần giữ state mutable trong component | Cần cân nhắc kỹ | Cũng cần kiểm soát ownership |

## 9. Record không đồng nghĩa với bất biến sâu

Các field tương ứng với component luôn là `private final`, nhưng nếu kiểu component là mảng, collection mutable hoặc một đối tượng có setter, dữ liệu bên trong vẫn có thể thay đổi:

~~~java
import java.util.List;

record BadCart(List<String> items) {}

var items = new java.util.ArrayList<String>();
items.add("book");
var cart = new BadCart(items);

items.add("pen");
System.out.println(cart.items()); // [book, pen]
~~~

Giải pháp với collection chứa phần tử immutable là sao chép cấu trúc tại constructor:

~~~java
import java.util.List;
import java.util.Objects;

public record Cart(List<String> items) {
    public Cart {
        items = List.copyOf(
                Objects.requireNonNull(items, "items")
        );
    }
}
~~~

`List.copyOf` tạo snapshot không cho phép thay đổi cấu trúc danh sách. Với `List<String>`, phần tử `String` bất biến nên đối tượng đủ ổn định trong trường hợp này. Với `List<MutableItem>`, `List.copyOf` chỉ sao chép nông; cần xử lý từng phần tử.

**Đặc biệt:** việc ghi đè accessor để trả một bản sao không thay đổi ngữ nghĩa `equals`/`hashCode` mặc định: chúng vẫn dựa trên field component gốc. Hãy thiết kế rõ liệu record có ngữ nghĩa theo identity, theo nội dung hay có kiểu component phù hợp hơn.

## 10. Hợp đồng tính minh bạch của record

Theo tài liệu `java.lang.Record`, một record là carrier có thể quan sát được các component. Một bất biến quan trọng là:

~~~java
R copy = new R(original.c1(), original.c2(), /* ... */);
boolean same = original.equals(copy); // phải true
~~~

Đây là cách diễn đạt tổng quát; `R`, `c1`, `c2` là tên tượng trưng, không phải một đoạn chương trình Java có thể biên dịch nguyên xi.

Ví dụ **thiết kế sai**:

~~~java
record Score(int value) {
    public int value() {
        return Math.min(value, 100);
    }
}

var original = new Score(130);
var copied = new Score(original.value());
System.out.println(original.equals(copied)); // false
~~~

Accessor `value()` âm thầm cắt giá trị 130 thành 100, làm vi phạm kỳ vọng tái tạo record từ component. Cách tốt hơn là chuẩn hóa ngay tại constructor nếu miền dữ liệu chấp nhận:

~~~java
record Score(int value) {
    Score {
        value = Math.min(Math.max(value, 0), 100);
    }
}
~~~

Hoặc giữ nguyên component và cung cấp phương thức `displayValue()` nếu muốn hiện giá trị khác trong UI.

Một record phù hợp khi header thực sự là **mô tả dữ liệu công khai** của kiểu. Nếu cần giấu phần lớn state, duy trì invariant phụ thuộc vào state nội bộ khác, hay cung cấp identity khác với component, class thông thường có thể là mô hình rõ ràng hơn.

## 11. Record generic, nested và local

Record hỗ trợ tham số kiểu:

~~~java
public record ApiResponse<T>(
        int statusCode,
        T body
) {}
~~~

Sử dụng:

~~~java
ApiResponse<String> response = new ApiResponse<>(200, "OK");
System.out.println(response.body()); // OK
~~~

Record cũng có thể là member type hoặc local type. Member record và local record ngầm là `static` về mặt ngữ nghĩa; chúng không giữ enclosing instance như inner class thông thường.

~~~java
public final class Geometry {
    public record Point(int x, int y) {}

    public static int distanceSquared(Point a, Point b) {
        int dx = Math.subtractExact(a.x(), b.x());
        int dy = Math.subtractExact(a.y(), b.y());
        return Math.addExact(
                Math.multiplyExact(dx, dx),
                Math.multiplyExact(dy, dy)
        );
    }
}
~~~

Trong ví dụ này, `Point` là member record. Nếu độ lớn tọa độ có thể vượt giới hạn `int` khi bình phương, cần mở rộng thiết kế kết quả; các phép `Math.*Exact` chủ động báo lỗi tràn thay vì trả giá trị sai.

## 12. Record trong sealed hierarchy

Một record có thể implement interface sealed và trở thành nhánh cuối của hệ phân cấp vì bản thân nó ngầm `final`:

~~~java
sealed interface PaymentResult
        permits Success, Failure {}

record Success(String receiptId) implements PaymentResult {}

record Failure(String reason) implements PaymentResult {}
~~~

Trong mô hình này:

- `PaymentResult` xác định tập nhánh được phép.
- `Success` và `Failure` mô tả dữ liệu riêng cho từng trường hợp.
- `Success` và `Failure` có các thành viên record được sinh như bình thường.
- Khi bổ sung trường hợp mới, cần xem xét các nhánh sử dụng polymorphism/pattern matching.

Record không được tuyên bố là `sealed` vì bản thân record ngầm final. Sealed hierarchy có thể chứa nhiều loại nhánh khác nhau, và record là lựa chọn tự nhiên cho các trường hợp chỉ mang dữ liệu.

## 13. Annotation trên record component

Bạn có thể gắn annotation cho component. Đích áp dụng (`@Target`) quyết định annotation có thể tồn tại tại component và có được truyền sang field, accessor, hoặc tham số canonical constructor được sinh hay không.

Ví dụ định nghĩa annotation dành cho record component:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface Label {
    String value();
}

record Profile(@Label("display-name") String name) {}
~~~

Annotation ở đây có thể được đọc bằng `Class.getRecordComponents()` và `RecordComponent.getAnnotation(...)`. Nó không tự động trở thành annotation của field hoặc accessor chỉ vì cùng mô tả một component: điều này còn phụ thuộc target. Nếu accessor được khai báo **tường minh**, annotation trên component cũng không tự động được truyền sang accessor tường minh.

Điều này quan trọng khi dùng validation, serialization hoặc API documentation frameworks: không nên giả định mọi framework quét cùng vị trí annotation. Hãy kiểm tra phiên bản framework hiện tại và vị trí annotation mà nó hỗ trợ.

## 14. Dùng reflection để đọc cấu trúc record

Java cung cấp API reflection cho record:

- `Class.isRecord()`: xác định một class là record.
- `Class.getRecordComponents()`: lấy các component theo thứ tự khai báo.
- `RecordComponent.getName()`, `getType()`, `getGenericType()`: lấy metadata về tên và kiểu.
- `RecordComponent.getAccessor()`: lấy đối tượng `Method` tương ứng accessor.
- `RecordComponent.getAnnotation(...)`: tra annotation tại component.

Ví dụ đọc metadata:

~~~java
import java.lang.reflect.RecordComponent;

public class RecordInspector {
    record Task(String title, int priority) {}

    public static void main(String[] args) {
        Class<?> type = Task.class;
        System.out.println(type.isRecord()); // true

        for (RecordComponent component : type.getRecordComponents()) {
            System.out.printf("%s: %s%n",
                    component.getName(),
                    component.getType().getSimpleName());
        }
        // title: String
        // priority: int
    }
}
~~~

`getRecordComponents()` trả về `null` nếu class không phải record, vì vậy nên kiểm tra `isRecord()` trước trong code tổng quát. Phản ánh được cấu trúc không có nghĩa là nên vượt qua encapsulation để sửa field final; dùng accessor và constructor công khai theo hợp đồng là hướng phù hợp.

## 15. Record, serialization và thay đổi API

Record là cấu trúc dữ liệu có **descriptor công khai**. Khi thêm, đổi tên hoặc đổi kiểu component, bạn đang thay đổi canonical constructor, accessor và ngữ nghĩa `equals`/`hashCode`/`toString`.

Vì vậy, một thay đổi tưởng nhỏ như:

~~~java
record OrderSummary(String id, long totalCents) {}
// Sau đó thêm component:
// record OrderSummary(String id, long totalCents, String currency) {}
~~~

có thể khiến caller cũ dùng constructor hai tham số không biên dịch. Nếu cần giữ source compatibility, có thể viết constructor overload chuyển tiếp đến canonical constructor mới:

~~~java
record OrderSummary(String id, long totalCents, String currency) {
    OrderSummary {
        java.util.Objects.requireNonNull(id);
        java.util.Objects.requireNonNull(currency);
    }

    OrderSummary(String id, long totalCents) {
        this(id, totalCents, "VND");
    }
}
~~~

Dù có overload, hợp đồng giá trị và cấu trúc serialized vẫn cần được xem xét khi đổi component.

Record chỉ tham gia Java Object Serialization khi nó implement `Serializable`. Nếu dùng cơ chế này, Java xử lý record khác lớp thông thường và gọi canonical constructor khi deserialize. Với ứng dụng mới, hãy chọn định dạng giao tiếp có hợp đồng, schema và quản lý version phù hợp; không dùng chi tiết `toString()` như một định dạng lưu trữ.

## 16. Những lỗi thường gặp

| Nhầm lẫn | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Record tự tạo getter `getX()` | Gọi sai tên accessor | Dùng `x()` hoặc cấu hình mapper nếu framework cần |
| Record tự động bất biến sâu | Component mảng/collection có thể bị sửa | Defensive copy và kiểm soát phần tử mutable |
| `final` trên component nghĩa là nội dung object bất biến | Reference không đổi nhưng object con mutable | Chọn kiểu immutable hoặc sao chép phù hợp |
| Record có thể khai báo field instance tùy ý | Lỗi biên dịch | Đặt trạng thái của record trong component; dùng class nếu cần state ẩn |
| Compact constructor tự gán `this.x = x` | Lỗi biên dịch | Chỉ validate/normalize tham số; compiler sẽ gán field |
| Accessor record là nơi biến đổi dữ liệu hiển thị | Vi phạm tính minh bạch/tái tạo | Giữ accessor phản ánh component, tạo phương thức riêng |
| `equals` của record dùng `Arrays.equals` cho mảng | Hai mảng bằng nội dung vẫn không bằng nhau | Chọn kiểu component có value equality hoặc override đúng hợp đồng |
| `toString` có định dạng cố định để parse | Phụ thuộc chi tiết không được cam kết | Dùng serialization/API có định dạng rõ |
| Đổi tên/thứ tự component mà không kiểm tra caller | Phá vỡ constructor, accessor, equality | Review record descriptor như public API |
| Dùng `hashCode` làm ID ổn định | Hash không được bảo đảm cố định | Dùng ID nghiệp vụ hoặc digest được định nghĩa riêng |

## 17. Checklist khi thiết kế và review record

- [ ] Record thực sự là carrier có các component mô tả đầy đủ trạng thái quan sát được.
- [ ] Tên, kiểu và thứ tự component phản ánh đúng hợp đồng API.
- [ ] Chọn `record` vì cần value semantics và tính minh bạch, không chỉ để giảm số dòng code.
- [ ] Đã hiểu canonical constructor được sinh và khi nào cần viết compact constructor.
- [ ] Đã validate null, miền giá trị và quan hệ giữa các component trong constructor.
- [ ] Constructor bổ sung đều chuyển tiếp về canonical constructor.
- [ ] Accessor được gọi bằng đúng tên component và không làm sai lệch dữ liệu.
- [ ] Component mutable được bảo vệ; collection lồng nhau được đánh giá về shallow/deep copy.
- [ ] `equals`/`hashCode` phản ánh đúng value semantics, đặc biệt với mảng và `float`/`double`.
- [ ] Không dùng định dạng `toString` làm giao thức hoặc log thông tin nhạy cảm.
- [ ] Nếu dùng annotation, đã kiểm tra `@Target` và cách framework đọc component.
- [ ] Nếu dùng reflection, đã phân biệt record và non-record trước khi gọi `getRecordComponents()`.
- [ ] Thay đổi component được review như thay đổi API/serialization schema.
- [ ] Đã kiểm tra record phù hợp khi kết hợp sealed interface hoặc sealed hierarchy.

## 18. Nguồn tài liệu chính thức

- [JLS 27 — Record Classes, §8.10](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.10) — định nghĩa record, component, field, accessor, constructor và các giới hạn.
- [JLS 27 — Record Components, §8.10.1](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.10.1) — cú pháp, kiểu, tên, varargs và annotation.
- [JLS 27 — Record Members, §8.10.3](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.10.3) — field, accessor, `equals`, `hashCode`, `toString`.
- [JLS 27 — Record Constructor Declarations, §8.10.4](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.10.4) — canonical constructor và compact constructor.
- [Java SE 27 API — java.lang.Record](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Record.html) — hợp đồng giá trị, thành viên bắt buộc và tính minh bạch.
- [Java SE 27 API — java.lang.reflect.RecordComponent](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/RecordComponent.html) — reflection với component, kiểu, accessor và annotation.
- [Java SE 27 API — Class](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Class.html) — `isRecord()` và `getRecordComponents()`.
- [JEP 395 — Records](https://openjdk.org/jeps/395) — cơ sở thiết kế và mốc records trở thành tính năng chính thức từ Java 16.

Record giúp Java mô hình hóa dữ liệu ngắn gọn mà vẫn giữ một hợp đồng giá trị có ý nghĩa. Lợi ích lớn nhất đến từ việc chọn component đúng, kiểm soát tính bất biến của dữ liệu được tham chiếu và để trình biên dịch cung cấp các thành viên nhất quán với descriptor của record.
