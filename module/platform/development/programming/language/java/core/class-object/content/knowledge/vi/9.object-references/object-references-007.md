# Các tình huống gây `NullPointerException` và cách phòng tránh trong Java

Trong Java, một **biến tham chiếu** có thể chứa tham chiếu đến object hoặc giá trị đặc biệt `null`. Khi chương trình cố sử dụng `null` ở nơi bắt buộc phải có object — chẳng hạn đọc field, gọi instance method, truy cập phần tử mảng hoặc tự động chuyển wrapper thành primitive — Java có thể ném **`NullPointerException` (NPE)**.

Ví dụ:

~~~java
String title = null;
System.out.println(title.length()); // NullPointerException.
~~~

`title` là biến tham chiếu kiểu `String`, nhưng tại thời điểm gọi `length()` nó **không tham chiếu String object nào**. Không có instance để thực hiện lời gọi. Lỗi phát sinh khi **sử dụng** giá trị null theo cách không hợp lệ, chứ không phải đơn giản vì biến được khai báo hoặc gán null.

**Mục tiêu:** Sau bài này, bạn có thể xác định nguồn gốc null, phân biệt các kiểu thao tác gây NPE, dùng điều kiện kiểm tra và API phù hợp để phòng tránh, lựa chọn chính sách đầu vào, đọc stack trace, kiểm thử trường hợp thiếu dữ liệu và thiết kế class ít tạo ra NPE bất ngờ.

Bài sử dụng **Java 17 trở lên**; các chương trình hoàn chỉnh có tên tệp, lệnh `javac`/`java` và stdout đối chiếu. Những đoạn **cố ý gây lỗi** được chỉ rõ để người học không nhầm chúng với mã nên áp dụng trong sản phẩm.

## 1. Từ null tới vị trí ném lỗi: tư duy chẩn đoán NPE

`null` là reference value **không trỏ object**. Với việc phòng tránh `NullPointerException`, câu hỏi cụ thể hơn là: **bước nào trong biểu thức đang đòi một object nhưng nhận null?**

~~~java
String missing = null;
System.out.println(missing == null); // true, không lỗi
// System.out.println(missing.length()); // NPE nếu thực thi
~~~

So sánh giá trị reference không cần object, nhưng gọi `length()` cần String receiver. Tương tự, `Integer boxed = null; int value = boxed;` có thể ném NPE do **auto-unboxing**, dù source không gọi method tường minh.

Khi đọc stack trace, lần theo **nguồn null → thao tác dereference → hợp đồng nullable → nơi validate/xử lý**. Bài này ưu tiên debugging và thiết kế phòng ngừa, không dạy lại toàn bộ bảng phân biệt `null` với chuỗi rỗng hay mảng rỗng.

## 2. Tìm nguồn null, đừng chỉ che chỗ phát nổ

Nguồn null thường gặp là field reference chưa khởi tạo, slot `new String[3]`, parameter do caller truyền, một API trả null, `Map.get(key)`, dữ liệu JSON/DB/config hoặc reference bị reset. Với `order.getCustomer().getAddress().city()`, cần xét lần lượt `order`, `getCustomer()` và `getAddress()`; guard ở **ranh giới sở hữu hợp đồng** thường dễ hiểu hơn việc catch NPE sau khi xảy ra.

**Sửa một hiểu lầm quan trọng:** Java không tự trả `null` khi một method có non-void return type “quên lệnh return”. Nếu compiler thấy đường kết thúc bình thường mà không trả value, đó là **lỗi biên dịch**. Method chỉ trả null nếu statement/expression được return có giá trị null (hoặc branch chủ đích return null).

Phân biệt field với local:

~~~java
class Holder {
    String name;                   // instance field mặc định null
    String[] tags = new String[2]; // array khác null, elements mặc định null
}
~~~

Đây là snippet class. Ngược lại, biến local chỉ khai báo `String value;` không được đọc cho đến khi compiler xác nhận **definite assignment**. Khi debug, tìm đúng **nguồn dữ liệu null** và sửa chính sách nullable sẽ bền hơn một loạt kiểm tra rải rác.

## 3. Ví dụ chạy: nhận diện giá trị null trước khi dereference

Lưu tệp **`NullSourcesDemo.java`**:

~~~java
public class NullSourcesDemo {
    static final class Holder {
        String name;
        String[] tags = new String[2];
    }

    public static void main(String[] args) {
        Holder holder = new Holder();

        System.out.println("name null: " + (holder.name == null));
        System.out.println("tags null: " + (holder.tags == null));
        System.out.println("first tag null: " + (holder.tags[0] == null));
        System.out.println("tags length: " + holder.tags.length);

        String missing = null;
        String empty = "";

        System.out.println("missing null: " + (missing == null));
        System.out.println("empty length: " + empty.length());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NullSourcesDemo.java
java NullSourcesDemo
~~~

Stdout:

~~~text
name null: true
tags null: false
first tag null: true
tags length: 2
missing null: true
empty length: 0
~~~

Ở đây **không có NPE** vì chương trình chỉ so sánh reference với null hoặc dùng receiver chắc chắn là object. Dù `tags[0]` null, biểu thức `tags[0] == null` vẫn hợp lệ. Nếu gọi `holder.tags[0].length()`, chương trình mới dereference phần tử null và ném NPE.

## 4. Những thao tác phổ biến gây `NullPointerException`

| Thao tác | Ví dụ nguy hiểm | Vì sao xảy ra NPE? |
| --- | --- | --- |
| Gọi instance method | `text.length()` với `text == null` | Không có receiver object |
| Đọc instance field | `person.name` với `person == null` | Không có instance chứa field |
| Ghi instance field | `person.name = "Mai"` với `person == null` | Không có object để cập nhật |
| Đọc độ dài array | `items.length` với `items == null` | Không có array object |
| Đọc/ghi phần tử array | `items[0]` hoặc `items[0] = value` khi array null | Không có array để truy cập |
| Enhanced for | `for (String s : items)` với array/list null | Cần array length hoặc iterator từ receiver null |
| Auto-unboxing | `int n = boxed;` với `boxed == null` | Cần giá trị primitive từ wrapper object |
| `throw null;` | Ném giá trị null thay Throwable object | JVM ném NPE |
| `synchronized (lock)` | `lock == null` | Monitor cần một object thực |
| `switch` với selector null | `switch (name)`, Java 17 bình thường | Switch trên `String`/enum không hỗ trợ null theo dạng thông thường |
| Bound method reference | `text::trim` khi `text == null` | Receiver của bound method reference cần object |
| Contract check chủ động | `Objects.requireNonNull(value)` | API cố ý ném NPE khi null |

NPE là unchecked exception thuộc `RuntimeException`. Compiler không bắt buộc method phải khai báo `throws NullPointerException`. Nhưng sự thiếu yêu cầu khai báo **không đồng nghĩa null an toàn**.

Một method được gọi trên object thật có thể **tự** ném NPE bên trong thân vì field riêng của object bị null; NPE không nhất thiết nằm ngay chỗ caller gọi method. Vì thế phải đọc stack trace và xem chuỗi dereference.

## 5. Ví dụ tổng hợp nhiều nguyên nhân NPE

Lưu file **`NpeTriggersDemo.java`**:

~~~java
public class NpeTriggersDemo {
    static final class Box {
        int value;
    }

    static void report(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + " -> completed");
        } catch (NullPointerException ex) {
            System.out.println(label + " -> NullPointerException");
        }
    }

    public static void main(String[] args) {
        String text = null;
        Box box = null;
        int[] numbers = null;
        String[] words = null;
        Integer boxed = null;
        Object lock = null;

        report("method", () -> {
            System.out.println(text.length());
        });

        report("field", () -> {
            int value = box.value;
        });

        report("array length", () -> {
            int length = numbers.length;
        });

        report("array element", () -> {
            int first = numbers[0];
        });

        report("unboxing", () -> {
            int value = boxed;
        });

        report("foreach", () -> {
            for (String item : words) {
                System.out.println(item);
            }
        });

        report("synchronized", () -> {
            synchronized (lock) {
                System.out.println("inside");
            }
        });

        report("throw null", () -> {
            throw null;
        });

        report("switch", () -> {
            String code = null;
            switch (code) {
                case "A" -> System.out.println("A");
                default -> System.out.println("other");
            }
        });
    }
}
~~~

~~~bash
javac -encoding UTF-8 NpeTriggersDemo.java
java NpeTriggersDemo
~~~

Stdout:

~~~text
method -> NullPointerException
field -> NullPointerException
array length -> NullPointerException
array element -> NullPointerException
unboxing -> NullPointerException
foreach -> NullPointerException
synchronized -> NullPointerException
throw null -> NullPointerException
switch -> NullPointerException
~~~

Đây là **chương trình cố tình phát sinh lỗi** để nhận diện cơ chế, không phải cách triển khai nghiệp vụ. Helper `report` bắt từng `NullPointerException` và chỉ in tên nhãn, tránh phụ thuộc vào văn bản lỗi do JVM tạo.

Phân tích:

- `text.length()` cần một `String` object; `text` null nên NPE.
- `box.value` cần một Box instance; `box` null nên không có field để đọc.
- `numbers.length` và `numbers[0]` cùng yêu cầu mảng tồn tại. Nếu mảng **khác null nhưng rỗng**, truy cập phần tử `[0]` sẽ là `ArrayIndexOutOfBoundsException`, **không phải NPE**.
- `int value = boxed;` yêu cầu auto-unboxing `Integer`; không thể unbox null.
- Enhanced for trên null array cần độ dài mảng, dẫn tới NPE. Với collection null, việc lấy iterator cũng cần receiver hợp lệ.
- `synchronized (lock)` cần monitor object, nhưng `lock` null.
- `throw null` được Java xử lý bằng cách ném `NullPointerException` chứ không ném một “Throwable null” có ý nghĩa.
- `switch` với chuỗi selector null trong Java 17 thông thường ném NPE.

**Không catch NPE chỉ để lờ lỗi.** Trong ứng dụng thực, hãy loại bỏ trạng thái không hợp lệ hoặc kiểm tra có chủ đích ở ranh giới phù hợp.

## 6. Một câu lệnh có nhiều dấu chấm: xác định chính xác mắt xích null

Xét:

~~~java
String city = order.getCustomer().getAddress().getCity();
~~~

Các receiver có thể null:

1. `order` null → không gọi được `getCustomer()`.
2. `order.getCustomer()` trả null → không gọi được `getAddress()`.
3. `getAddress()` trả null → không gọi được `getCity()`.
4. `getCity()` trả null → **bản thân phép gán `String city = ...` vẫn hợp lệ** vì reference String có thể null. NPE có thể xảy ra **sau này** nếu dùng `city.length()`.

Khác biệt ở bước 4 rất quan trọng: **Một method trả null không luôn ném NPE ngay**. NPE xảy ra khi mã tiếp tục **dùng null ở vị trí cần object**.

### Cách viết dễ tìm lỗi hơn

~~~java
Customer customer = order.getCustomer();
Address address = customer.getAddress();
String city = address.getCity();
~~~

Đây là **mã minh họa**, cần có kiểu `Order`, `Customer`, `Address` và object hợp lệ. Tách biến giúp xác định receiver ở từng bước, nhưng **tự nó không ngăn NPE**. Muốn an toàn cần validation, guard clauses hoặc dữ liệu domain đảm bảo bất biến.

### Phân biệt null với ngoại lệ khác

Nếu `order` không null nhưng `getCustomer()` tự ném `IllegalStateException`, lỗi đó **không phải NPE chỉ vì nằm trong chuỗi chấm**. Hãy xác định loại exception thực tế và frame gây lỗi, không thay tất cả bằng những nhánh catch null.

## 7. Guard clause: từ chối hoặc xử lý null ngay tại điểm hợp lý

Guard clause là điều kiện ở đầu method để loại trường hợp đầu vào không hợp lệ hoặc xử lý trường hợp thiếu dữ liệu trước khi phần xử lý chính bắt đầu.

Ví dụ từ chối:

~~~java
static int displayNameLength(String name) {
    if (name == null) {
        throw new IllegalArgumentException("name is required");
    }
    return name.length();
}
~~~

Ví dụ chấp nhận null như một giá trị vắng mặt:

~~~java
static String displayName(String name) {
    if (name == null || name.isBlank()) {
        return "(anonymous)";
    }
    return name.strip();
}
~~~

Đây là **các method minh họa** có thể đặt trong class phù hợp. Hai chính sách khác nhau:

- `displayNameLength` xem null là lỗi dữ liệu.
- `displayName` xem null là một trạng thái có thể xử lý bằng mặc định.

**Không trộn hai chính sách một cách ngẫu nhiên.** Nếu tên bắt buộc trong domain model, thường nên từ chối khi tạo object. Nếu field tùy chọn, đặt giá trị mặc định hoặc trả trạng thái thiếu rõ ràng tại nơi sử dụng.

### Tại sao điều kiện `name == null || name.isBlank()` an toàn?

`||` trong Java **short-circuit** từ trái sang phải:

- Nếu `name == null` là true, biểu thức bên phải `name.isBlank()` **không được đánh giá**.
- Nếu false, `name` có receiver khác null trong biểu thức này, nên có thể gọi `isBlank()`.

Sai lầm thường gặp:

~~~java
if (name.isBlank() || name == null) {
    // Dòng này có thể NPE trước khi kiểm tra null!
}
~~~

Với `&&` cũng vậy: `name != null && !name.isBlank()` an toàn vì vế phải chỉ chạy khi `name != null`.

## 8. Ví dụ chạy: chính sách guard clause rõ ràng

Tạo file **`NullGuardDemo.java`**:

~~~java
public class NullGuardDemo {
    static String normalizeDisplayName(String name) {
        if (name == null || name.isBlank()) {
            return "(anonymous)";
        }
        return name.strip();
    }

    static int requiredLength(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value is required");
        }
        return value.length();
    }

    public static void main(String[] args) {
        System.out.println(normalizeDisplayName(null));
        System.out.println(normalizeDisplayName("   "));
        System.out.println(normalizeDisplayName("  Mai  "));
        System.out.println("length=" + requiredLength("Java"));

        try {
            requiredLength(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullGuardDemo.java
java NullGuardDemo
~~~

Stdout:

~~~text
(anonymous)
(anonymous)
Mai
length=4
rejected: value is required
~~~

Hai đường xử lý đầu vào đều **chủ động**. NPE không được dùng như một cơ chế thông báo rằng giá trị bắt buộc thiếu ở caller; thay vào đó API định nghĩa `IllegalArgumentException` và thông điệp có nghĩa. Với đầu vào tùy chọn, method đưa ra mặc định theo yêu cầu nghiệp vụ.

`isBlank()` và `strip()` là các method của `String` có trong Java 11+, dùng được trên Java 17. Đối với mật khẩu, định danh cần giữ dấu cách hay dữ liệu ký số, không tự động strip/normalize nếu hợp đồng không cho phép.

## 9. `Objects.requireNonNull`: kiểm tra hợp đồng ngay tại ranh giới

`java.util.Objects.requireNonNull(value, "message")` nhận reference và:

- **Nếu khác null:** trả lại **chính reference đó**.
- **Nếu null:** ném `NullPointerException` với message chỉ định.
- **Không tạo một bản sao object**, không tự khởi tạo value mặc định.

Ví dụ:

~~~java
class Product {
    private final String id;

    Product(String id) {
        this.id = java.util.Objects.requireNonNull(id, "id");
    }
}
~~~

Đây là class minh họa. `new Product(null)` ném NPE có message `id` theo hợp đồng `requireNonNull`. Điều đó có thể phù hợp với một API quy định null là lỗi lập trình.

### Khi dùng `IllegalArgumentException` thay vì NPE?

Hai cách đều tồn tại:

~~~java
if (id == null) {
    throw new IllegalArgumentException("id is required");
}
~~~

hoặc:

~~~java
this.id = java.util.Objects.requireNonNull(id, "id");
~~~

Java không buộc **mọi đầu vào null** phải được báo bằng đúng một loại exception. Quan trọng là:

1. API công khai có chính sách nhất quán.
2. Message chỉ ra biến hoặc quy tắc vi phạm.
3. Các caller biết phải cung cấp dữ liệu hợp lệ hay xử lý trường hợp thiếu.
4. Validation không bị lặp tùy tiện ở nhiều tầng với các chính sách trái ngược.

**Không bắt `NullPointerException` rộng khắp chỉ để biến tất cả lỗi thành “không có dữ liệu”.** NPE cũng có thể phản ánh một bug trong code vốn phải được sửa.

### `Objects.requireNonNullElse`

Java có `Objects.requireNonNullElse(value, defaultValue)`. Method này trả `value` nếu không null, hoặc trả `defaultValue` nếu value null; **defaultValue cũng phải không null**.

~~~java
String label = java.util.Objects.requireNonNullElse(name, "(unknown)");
~~~

Nếu default cũng null, method ném NPE. Dùng kiểu API này khi một giá trị thay thế **thật sự được phép theo contract**, không phải để che mất một ID bắt buộc.

## 10. So sánh chuỗi và object khi có khả năng null

Một lỗi rất phổ biến:

~~~java
String status = null;
// if (status.equals("READY")) { ... } // Có thể NPE.
~~~

Có hai cách an toàn thường dùng:

~~~java
if ("READY".equals(status)) {
    // String literal không null, kiểm tra nội dung.
}
~~~

hoặc:

~~~java
if (java.util.Objects.equals(status, "READY")) {
    // So sánh an toàn với null.
}
~~~

`Objects.equals(a, b)` xử lý cả trường hợp null theo hợp đồng equality. Nếu cả hai đều null, kết quả là true; nếu chỉ một bên null, false; còn lại chuyển đến `a.equals(b)`.

### Không dùng `==` để so sánh nội dung chuỗi

~~~java
String left = new String("Java");
String right = new String("Java");
System.out.println(left == right);      // false
System.out.println(left.equals(right)); // true
~~~

Với `String`, `==` so sánh identity của hai tham chiếu; `equals` so sánh nội dung. Đôi khi hai String literals dùng chung interned instance nên `==` tình cờ true, nhưng không được dựa vào điều đó để so sánh giá trị.

### Ví dụ hoàn chỉnh dùng API null-safe

Lưu **`NullSafeComparisonsDemo.java`**:

~~~java
import java.util.Objects;
import java.util.Optional;

public class NullSafeComparisonsDemo {
    public static void main(String[] args) {
        String status = null;

        System.out.println("ready=" + "READY".equals(status));
        System.out.println("both null=" + Objects.equals(null, null));
        System.out.println("same text=" + Objects.equals("Java", "Java"));
        System.out.println("description=" +
                Objects.toString(status, "(missing)"));

        String display = Optional.ofNullable(status)
                .map(String::strip)
                .filter(value -> !value.isEmpty())
                .orElse("(unknown)");

        System.out.println("display=" + display);
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullSafeComparisonsDemo.java
java NullSafeComparisonsDemo
~~~

Stdout:

~~~text
ready=false
both null=true
same text=true
description=(missing)
display=(unknown)
~~~

`Objects.toString(status, "(missing)")` cho nội dung thay thế khi reference null. Nếu chỉ dùng `String.valueOf(status)`, kết quả là chuỗi ký tự `"null"`, khác với một placeholder nghiệp vụ có chủ ý.

## 11. Chuỗi dereference với object lồng nhau: ví dụ có kiểm tra từng tầng

Một Customer có thể không có Address, và Address có thể không có City. Thay vì gọi liên tiếp các getter mà không xác minh trạng thái, định nghĩa chính sách hiển thị rõ.

Lưu file **`NestedNullGuardDemo.java`**:

~~~java
public class NestedNullGuardDemo {
    record Address(String city) {}
    record Customer(String name, Address address) {}

    static String cityLabel(Customer customer) {
        if (customer == null) {
            return "(no customer)";
        }

        Address address = customer.address();
        if (address == null) {
            return "(no address)";
        }

        String city = address.city();
        if (city == null || city.isBlank()) {
            return "(no city)";
        }

        return city;
    }

    public static void main(String[] args) {
        Customer absent = null;
        Customer noAddress = new Customer("Mai", null);
        Customer noCity = new Customer(
                "An", new Address(null));
        Customer complete = new Customer(
                "Binh", new Address("Ha Noi"));

        System.out.println(cityLabel(absent));
        System.out.println(cityLabel(noAddress));
        System.out.println(cityLabel(noCity));
        System.out.println(cityLabel(complete));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NestedNullGuardDemo.java
java NestedNullGuardDemo
~~~

Stdout:

~~~text
(no customer)
(no address)
(no city)
Ha Noi
~~~

Ở đây các record cho phép null để **mô phỏng dữ liệu chưa đầy đủ**. Chúng không nên được xem là value objects đã có invariant mạnh. Nếu nghiệp vụ yêu cầu Customer **luôn có Address**, một thiết kế tốt hơn là **kiểm tra ngay trong constructor** và không cho tạo Customer thiếu Address. Chỉ thêm null guard tại màn hình hiển thị không giải quyết invariant bị phá ở nguồn dữ liệu.

### Java có toán tử `?.` như một số ngôn ngữ khác không?

Java 17 **không có** toán tử safe-navigation tổng quát như `customer?.address?.city`. Bạn phải sử dụng điều kiện, guard clauses, kiểu có invariant, hoặc API như `Optional` khi phù hợp.

Đừng viết Java theo cú pháp của Kotlin, C# hoặc JavaScript rồi kỳ vọng compiler tự hiểu.

## 12. `Optional` có thể diễn đạt “có hoặc không có kết quả”

`java.util.Optional<T>` là một container API để mô tả giá trị có thể hiện diện hoặc vắng mặt, đặc biệt hữu ích với **kiểu trả về** của phương thức tìm kiếm.

~~~java
static java.util.Optional<String> findNickname(String id) {
    if ("A".equals(id)) {
        return java.util.Optional.of("Mai");
    }
    return java.util.Optional.empty();
}
~~~

Đây là method minh họa. Caller có thể viết:

~~~java
String nickname = findNickname("X").orElse("(unknown)");
~~~

Không cần gán trực tiếp null như trường hợp `String findNickname(...)` có thể trả null.

**Các factory của Optional:**

- `Optional.of(value)` yêu cầu value khác null; truyền null gây NPE.
- `Optional.ofNullable(value)` tạo Optional rỗng nếu value null.
- `Optional.empty()` biểu diễn không có giá trị.
- `optional.orElse(defaultValue)` lấy nội dung nếu có, nếu không lấy default.
- `optional.orElseGet(supplier)` tính fallback bằng supplier khi Optional rỗng.
- `optional.map(transformer)` ánh xạ khi có giá trị; nếu mapper trả null, Optional kết quả rỗng.
- `optional.orElseThrow()` báo lỗi nếu rỗng; dùng khi vắng mặt thật sự là lỗi.

### Optional không phải “lá chắn cho mọi null”

~~~java
java.util.Optional<String> optional = null;
// optional.orElse("default"); // NPE vì chính biến optional là null.
~~~

Một API khai báo trả `Optional<String>` nên có hợp đồng **không trả null Optional**, mà trả `Optional.empty()` khi thiếu. Không mặc định dùng `Optional` cho mọi field và mọi tham số: nó cũng là object, có chi phí và có thể khiến chữ ký phức tạp hơn. Trong nhiều trường hợp, **validation tại constructor** và **kiểu domain rõ ràng** tốt hơn.

## 13. Ví dụ chạy: tra cứu với `Optional` và `Map`

Lưu **`OptionalLookupDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public class OptionalLookupDemo {
    static Optional<String> find(Map<String, String> users, String id) {
        if (users == null) {
            throw new IllegalArgumentException("users is required");
        }
        if (id == null) {
            throw new IllegalArgumentException("id is required");
        }
        return Optional.ofNullable(users.get(id));
    }

    public static void main(String[] args) {
        Map<String, String> users = new HashMap<>();
        users.put("A", "Mai");
        users.put("B", null);

        System.out.println(find(users, "A").orElse("(missing)"));
        System.out.println(find(users, "B").orElse("(missing)"));
        System.out.println(find(users, "X").orElse("(missing)"));
        System.out.println("has B=" + users.containsKey("B"));
        System.out.println("has X=" + users.containsKey("X"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OptionalLookupDemo.java
java OptionalLookupDemo
~~~

Stdout:

~~~text
Mai
(missing)
(missing)
has B=true
has X=false
~~~

`HashMap` cho phép giá trị null. Vì vậy:

- `users.get("B")` trả null do **khóa B tồn tại nhưng ánh xạ tới null**.
- `users.get("X")` cũng trả null nhưng vì **không có khóa X**.
- `Optional.ofNullable(users.get(id))` không phân biệt hai trạng thái trên.
- `containsKey` giúp phân biệt “khóa hiện diện” với “khóa vắng mặt” khi ứng dụng cần biết.

Với `Map.of(...)` hay một số implementation khác, null keys/values có thể bị từ chối. **Không áp một quy tắc null cho mọi loại Map**. Hãy đọc contract của implementation đang dùng.

Nếu hệ thống cần ba trạng thái **không có bản ghi / có bản ghi nhưng thiếu dữ liệu / có bản ghi và dữ liệu hợp lệ**, một kiểu kết quả cụ thể có thể phù hợp hơn `Optional<String>` đơn lẻ.

## 14. Null trong array và collection: phải phân biệt container với phần tử

Hai khả năng độc lập:

~~~java
String[] names = null;       // Chưa có array object.
String[] names2 = new String[2]; // Có array; hai phần tử null.
~~~

Với `names`, `names.length` ném NPE; với `names2`, `names2.length == 2` hợp lệ. Nhưng `names2[0].length()` ném NPE vì **phần tử đầu** null.

Tương tự với collection:

~~~java
java.util.List<String> list = null;             // Không có List object.
java.util.List<String> empty = java.util.List.of(); // Có List rỗng.
~~~

`empty.size()` cho 0, còn `list.size()` ném NPE. `List.of("A", null)` ném NPE **ngay khi tạo List** vì factory này không cho phép null elements.

### Vòng lặp for-each

~~~java
for (String name : names2) {
    System.out.println(name);
}
~~~

Lệnh trên **không nhất thiết gây NPE**: body chỉ in tham chiếu String null nên có thể in `null`. Nhưng nếu body đổi thành `System.out.println(name.length());`, nó sẽ ném NPE tại phần tử null. Với `names` là mảng null, enhanced for phát sinh NPE trước khi duyệt phần tử.

### Ví dụ chạy độc lập phân biệt các tầng

Lưu file **`NullArrayLevelsDemo.java`**:

~~~java
import java.util.Arrays;

public class NullArrayLevelsDemo {
    public static void main(String[] args) {
        String[] missing = null;
        String[] empty = new String[0];
        String[] containsNull = new String[2];
        containsNull[1] = "Java";

        System.out.println("missing array=" + (missing == null));
        System.out.println("empty length=" + empty.length);
        System.out.println("contents=" + Arrays.toString(containsNull));
        System.out.println("first missing=" + (containsNull[0] == null));

        for (String value : containsNull) {
            System.out.println("value=" + value);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullArrayLevelsDemo.java
java NullArrayLevelsDemo
~~~

Stdout:

~~~text
missing array=true
empty length=0
contents=[null, Java]
first missing=true
value=null
value=Java
~~~

Lợi ích của phân biệt này là không “sửa” một mảng có phần tử null bằng cách chỉ kiểm tra array reference khác null. Phải nêu rõ container có được null không **và** elements có được null không.

## 15. Auto-unboxing: NPE mà không có dấu chấm trong code

Nhiều NPE làm người mới học ngạc nhiên vì câu lệnh không có `.method()`:

~~~java
Integer boxed = null;
int number = boxed; // Auto-unboxing null -> NPE.
~~~

Khi cần `int`, Java có thể chuyển `Integer` sang primitive bằng unboxing. Nếu reference wrapper null, không có giá trị primitive để lấy.

Các ví dụ tương tự:

~~~java
Boolean flag = null;
// if (flag) { ... }  // NPE do unboxing Boolean -> boolean.

Integer points = null;
// int doubled = points * 2;  // NPE do unboxing Integer -> int.
~~~

Mỗi đoạn được **comment ở thao tác nguy hiểm** để minh họa, không phải chương trình chạy riêng. Hãy cẩn thận với return values từ `Map<String, Integer>`, DTO fields kiểu wrapper và kết quả query database.

### Phòng tránh auto-unboxing null

Một lựa chọn rõ ràng:

~~~java
static int pointsOrZero(Integer points) {
    return points == null ? 0 : points;
}
~~~

Nếu null **không hợp lệ**, không nên tự mặc định về 0. Dùng validation để báo lỗi:

~~~java
static int requiredPoints(Integer points) {
    if (points == null) {
        throw new IllegalArgumentException("points is required");
    }
    return points;
}
~~~

Trong trường hợp thứ hai, unboxing chỉ diễn ra ở dòng `return points;` **sau khi kiểm tra**, nên không gặp null.

### Ví dụ chạy không có NPE

Tạo file **`SafeUnboxingDemo.java`**:

~~~java
public class SafeUnboxingDemo {
    static int pointsOrZero(Integer value) {
        return value == null ? 0 : value;
    }

    static int requiredPoints(Integer value) {
        if (value == null) {
            throw new IllegalArgumentException("points is required");
        }
        return value;
    }

    public static void main(String[] args) {
        Integer missing = null;
        Integer present = 7;

        System.out.println("default=" + pointsOrZero(missing));
        System.out.println("present=" + pointsOrZero(present));
        System.out.println("required=" + requiredPoints(present));

        try {
            requiredPoints(missing);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected missing points");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeUnboxingDemo.java
java SafeUnboxingDemo
~~~

Stdout:

~~~text
default=0
present=7
required=7
rejected missing points
~~~

Nếu miền nghiệp vụ **luôn có số nguyên**, cân nhắc dùng `int` ngay từ ranh giới đã kiểm tra thay vì truyền `Integer` nullable qua nhiều tầng. Khi cần biểu diễn không có số, hãy xác định cơ chế biểu diễn phù hợp.

## 16. Method invocation: null receiver và thứ tự đánh giá đối số

Một tình huống nâng cao có thể khiến bạn đọc log sai: trong lời gọi instance method, Java đánh giá **biểu thức receiver**, rồi các **biểu thức đối số theo thứ tự trái sang phải**. Nếu receiver được đánh giá thành null mà một đối số vẫn có side effect, side effect đó có thể xảy ra **trước** khi NPE được ném do không có instance để gọi.

Tạo file **`NullReceiverEvaluationDemo.java`**:

~~~java
public class NullReceiverEvaluationDemo {
    static class Service {
        void accept(int number) {
            System.out.println("body=" + number);
        }
    }

    static int prepareArgument() {
        System.out.println("argument prepared");
        return 5;
    }

    public static void main(String[] args) {
        Service service = null;

        try {
            service.accept(prepareArgument());
        } catch (NullPointerException ex) {
            System.out.println("receiver was null");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullReceiverEvaluationDemo.java
java NullReceiverEvaluationDemo
~~~

Stdout:

~~~text
argument prepared
receiver was null
~~~

`prepareArgument()` được thực thi và in log. Sau khi chuẩn bị đối số, lời gọi `Service.accept` không có receiver object nên NPE. Thân `accept` **không chạy**, vì vậy không có dòng `body=...`.

**Phân biệt:** Nếu chính **receiver expression** ném exception trong lúc đánh giá, các đối số phía sau có thể không được đánh giá. Nếu một **đối số** ném exception trước khi lời gọi instance được thực hiện, exception đó có thể xuất hiện thay vì NPE vì receiver null. Đừng dựa vào ngoại lệ để kiểm soát side effect; tốt hơn kiểm tra receiver trước khi chuẩn bị tác vụ có tác động ngoài.

## 17. Bound method reference và null

Trong Java, method reference dạng `reference::instanceMethod` được **gắn với receiver**. Nếu receiver null, việc tạo **bound method reference** có thể gây NPE ngay lúc biểu thức reference được đánh giá, chưa cần gọi functional interface method.

Ví dụ **cố ý gây NPE**:

~~~java
String text = null;
// java.util.function.Supplier<String> trim = text::trim;
~~~

Nếu bỏ comment dòng thứ hai, chương trình có thể ném NPE khi đánh giá `text::trim`. Đây không giống `String::trim`, là **unbound instance method reference** được gắn với một tham số receiver ở lần gọi sau, hoặc lambda `() -> text.trim()` mà phần dereference thực sự nằm trong thân lambda lúc chạy.

Trong ví dụ sử dụng an toàn, có thể kiểm tra receiver trước khi tạo bound reference:

~~~java
if (text != null) {
    java.util.function.Supplier<String> trim = text::trim;
    System.out.println(trim.get());
}
~~~

Đây là đoạn minh họa đặt trong method; không phải chương trình độc lập. Phân biệt **thời điểm tạo callback** và **thời điểm callback được gọi** sẽ giúp tìm NPE trong code xử lý bất đồng bộ.

## 18. Constructor nên thiết lập invariant để hạn chế null lan khắp hệ thống

Nếu class `Customer` yêu cầu email bắt buộc, không nên cho phép tạo object thiếu email rồi để mọi method khác đều phải kiểm tra null.

~~~java
class Customer {
    private final String email;

    Customer(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("email is required");
        }
        this.email = email.strip();
    }

    String email() {
        return email;
    }
}
~~~

Đây là class minh họa. Sau khi `new Customer(...)` **hoàn tất thành công**, instance có email không null và không blank theo kiểm tra. Nếu class không cho sửa email thành null về sau, các method nội bộ có thể dựa vào invariant đó.

### Kiểm tra ở đâu?

- **Ranh giới vào hệ thống:** validate payload/request/database mapping phù hợp.
- **Constructor/value object:** bảo vệ những điều kiện luôn đúng của một instance hợp lệ.
- **Method nhận argument:** validate những tham số bắt buộc của hành vi cụ thể.
- **Adapter/library boundary:** xác minh contract của dữ liệu bên ngoài.
- **Điểm hiển thị:** chỉ dùng fallback nếu thiếu dữ liệu là trạng thái hợp lệ, không mặc định “chữa” một object sai invariant.

Điều này không có nghĩa phải rải `if (x == null)` khắp mọi dòng. Validation có chủ đích giúp **giảm những nơi cần kiểm tra**, thay vì tăng chúng không giới hạn.

### Record cũng cần validation

~~~java
record CustomerId(String value) {
    CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("CustomerId is required");
        }
    }
}
~~~

Java record có các component fields cuối cùng theo thiết kế, nhưng record **không tự kiểm tra null**. Compact constructor là nơi hợp lệ để đặt invariant. Một record chứa reference mutable cũng không tự trở thành bất biến sâu.

## 19. Chọn mặc định, empty object hay từ chối null?

Không có một chính sách phù hợp mọi miền dữ liệu.

| Tình huống | Hướng xử lý thường phù hợp | Vì sao? |
| --- | --- | --- |
| Mã định danh bắt buộc | Từ chối null bằng validation | Null không phải ID hợp lệ |
| Danh sách kết quả tìm kiếm không có phần tử | Trả collection rỗng khi hợp đồng cho phép | Caller duyệt được mà không cần xử lý null |
| Không tìm thấy một object đơn lẻ | `Optional<T>` hoặc nullable theo hợp đồng | Biểu diễn có/không có kết quả |
| Tên hiển thị không bắt buộc | Placeholder có chủ ý | UI cần hiển thị ổn định |
| Số tiền hoặc số lượng bắt buộc | Không đổi null thành 0 tùy tiện | 0 là một **giá trị nghiệp vụ**, không giống thiếu |
| Config chưa tải được | Báo lỗi hoặc mô hình trạng thái rõ | Default âm thầm có thể che vấn đề |
| Collection có phần tử null | Từ chối hoặc xử lý null element theo contract | Kiểm tra chỉ container không đủ |

**Empty Object pattern** có thể dùng khi một object rỗng có **nghĩa nghiệp vụ hợp lệ**, chẳng hạn một giỏ hàng có 0 sản phẩm. Nhưng không nên tạo object giả vô nghĩa chỉ để mọi reference khác null.

### Một danh sách rỗng không đồng nghĩa không tải được dữ liệu

Ví dụ `List<Order> orders = List.of();` có thể nghĩa là truy vấn thành công và không có đơn nào. Một lỗi kết nối tới database cần được thể hiện bằng lỗi/kiểu kết quả tương ứng, chứ không nên biến thành danh sách rỗng và tạo ấn tượng truy vấn thành công.

## 20. Annotation về nullability và công cụ phân tích tĩnh

Một số dự án dùng annotation như `@Nullable`, `@NonNull`, `@NotNull` cùng các công cụ IDE, checker, build plugin hoặc framework. Chúng giúp diễn đạt hợp đồng “tham số/field/result có thể null hay không”.

Tuy nhiên:

- Java 17 **không có một annotation `@NonNull` duy nhất mặc định được compiler Java áp dụng cho mọi code**.
- Ý nghĩa và khả năng kiểm tra phụ thuộc thư viện annotation, toolchain và cấu hình dự án.
- Annotation không tự ngăn một caller dùng reflection hoặc một thư viện bên ngoài để truyền null trong mọi tình huống.
- Runtime validation vẫn cần khi dữ liệu đến từ nguồn không đáng tin hoặc contract bắt buộc fail fast.

Khi làm việc theo nhóm, hãy chọn **một hệ thống nullability nhất quán** để các thành phần hiểu như nhau. Đừng chỉ trang trí annotation mà không bật kiểm tra, không viết test và không giữ invariant.

### IDE cảnh báo có thay thế kiểm thử không?

Không. Static analysis có thể nhận ra các đường null rõ ràng, nhưng có thể không hiểu đầy đủ dữ liệu runtime, database, reflection hoặc hợp đồng library. Kết hợp **kiểu dữ liệu rõ**, **validation**, **tooling** và **kiểm thử ca thiếu dữ liệu** sẽ đáng tin hơn một phương pháp đơn lẻ.

## 21. Đọc stack trace và enhanced NPE message

Khi NPE không được xử lý, JVM thường in thông tin exception ra **stderr**, kèm stack trace về các lời gọi liên quan.

Ví dụ một thông báo minh họa có thể nói rõ reference nào null khi gọi method:

~~~text
Exception in thread "main" java.lang.NullPointerException:
Cannot invoke "String.length()" because "name" is null
    at Example.main(Example.java:...)
~~~

Đây là **định dạng minh họa**, không phải output cố định: số dòng, tên biến, cách diễn đạt chi tiết và việc có enhanced NPE messages phụ thuộc JVM, tùy chọn chạy và mã biên dịch. Trên nhiều JVM hiện đại, thông báo NPE có thể giúp chỉ ra biểu thức null chính xác hơn, nhưng **đừng phụ thuộc vào một câu chữ duy nhất của exception message** để viết logic nghiệp vụ hay test.

### Quy trình điều tra

1. Đọc **exception class**: thật sự là `NullPointerException` hay một lỗi khác?
2. Tìm **frame mã ứng dụng** gần vị trí lỗi, kiểm tra file và line number.
3. Đọc toàn bộ biểu thức có nhiều dereference ở dòng đó.
4. Xác định giá trị reference nào có thể null, và **nó được tạo/trả/gán ở đâu**.
5. Đi ngược call stack về caller và dữ liệu đầu vào để tìm nguồn null.
6. Quyết định null là **đầu vào sai** hay **trạng thái vắng mặt hợp lệ**.
7. Sửa **hợp đồng/invariant/logic xử lý**, sau đó bổ sung test ngăn tái phát.

Một lỗi thường thấy là bắt NPE rồi trả dữ liệu rỗng mà **không xác định nguồn null**. Cách đó có thể che lỗi trong object state, dẫn đến dữ liệu sai âm thầm.

### Không dùng exception message để quyết định nhánh

Đừng viết `if (ex.getMessage().contains("name"))` để suy ra thiếu trường name: message có thể thay đổi. Nên kiểm tra dữ liệu **trước khi dereference** và ném exception rõ loại ở ranh giới hợp đồng.

## 22. Vì sao `catch (NullPointerException)` thường không phải cách phòng tránh?

Đoạn code:

~~~java
try {
    return order.getCustomer().getName();
} catch (NullPointerException ex) {
    return "(unknown)";
}
~~~

là một **method-body minh họa**. Nó có thể giấu nhiều vấn đề khác nhau:

- `order` null;
- `getCustomer()` trả null;
- `getName()` tự ném NPE **bên trong method** vì một lỗi khác.

Cả ba bị gom thành một kết quả `"(unknown)"`, làm mất khả năng xác định vấn đề gốc. Đặc biệt nếu method có side effect trước NPE, `catch` không tự rollback side effect.

Cách tốt hơn là kiểm tra chính xác các giá trị được phép thiếu:

~~~java
if (order == null) {
    throw new IllegalArgumentException("order is required");
}

Customer customer = order.getCustomer();
if (customer == null) {
    return "(no customer)";
}

String name = customer.getName();
return name == null ? "(unnamed customer)" : name;
~~~

Đây cũng là **mảnh mã minh họa**, cần có class và method cụ thể. Nó phân biệt **order bắt buộc**, **customer tùy chọn**, **name tùy chọn** theo một hợp đồng đã được chọn.

Có ngoại lệ: ở một ranh giới kỹ thuật thực sự cần chuyển một exception runtime sang kiểu lỗi cao hơn, mã có thể catch NPE với lý do rõ và giữ cause. Nhưng **không nên dùng catch NPE làm “null-safe operator” thay cho thiết kế dữ liệu đúng**.

## 23. Kiểm thử NPE: không chỉ chạy happy path

Các ca thử nên bao phủ:

- **Input bắt buộc null** → API từ chối bằng loại exception đã cam kết.
- **Input tùy chọn null** → API trả fallback/Optional.empty đúng nghĩa.
- **Field bắt buộc sau khởi tạo** → invariant luôn đúng.
- **Nested references** → thiếu object ở từng tầng có cách xử lý riêng.
- **Array/collection** → container null, rỗng, có null element là những ca khác nhau.
- **Wrapper** → kiểm tra unboxing khi null.
- **Boundary/side effect** → lỗi được phát hiện trước khi trạng thái thay đổi không mong muốn.
- **Regression** → test đúng lỗi null từng được tìm thấy trong sản phẩm.

### Ví dụ test tự chạy không cần JUnit

Lưu file **`NullContractTestDemo.java`**:

~~~java
import java.util.Objects;

public class NullContractTestDemo {
    static final class Username {
        private final String value;

        Username(String value) {
            Objects.requireNonNull(value, "value");
            if (value.isBlank()) {
                throw new IllegalArgumentException("username must not be blank");
            }
            this.value = value.strip();
        }

        String value() {
            return value;
        }
    }

    static void assertEquals(String expected, String actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "expected=" + expected + ", actual=" + actual);
        }
    }

    static void expectNullRejected(Runnable operation) {
        try {
            operation.run();
        } catch (NullPointerException expected) {
            System.out.println("null rejected");
            return;
        }
        throw new AssertionError("Expected NullPointerException");
    }

    public static void main(String[] args) {
        Username valid = new Username("  Mai  ");
        assertEquals("Mai", valid.value());

        expectNullRejected(() -> new Username(null));

        System.out.println("All checks passed");
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullContractTestDemo.java
java NullContractTestDemo
~~~

Stdout:

~~~text
null rejected
All checks passed
~~~

Đây là test của **hợp đồng cố ý từ chối null bằng `Objects.requireNonNull`**, không phải test xem code có dereference null ngoài ý định hay không. Trong dự án thật, JUnit có `assertThrows` và những công cụ tổ chức test thuận tiện hơn. Với `Username("")`, constructor ném `IllegalArgumentException` sau kiểm tra `isBlank()`; đó là một ca cần bổ sung khi kiểm thử đầy đủ.

### Lưu ý về message trong test

Nếu API cam kết một message cụ thể, có thể kiểm tra nó. Nhưng enhanced NPE message tự động từ JVM **không nên được xem như hợp đồng văn bản cố định**. Test nên xác nhận hành vi nghiệp vụ và loại lỗi do chính API xác định.

## 24. Những lỗi phòng tránh null tưởng đúng nhưng chưa đủ

| Cách viết/quan niệm | Vấn đề | Cải thiện |
| --- | --- | --- |
| `value.equals("OK")` | `value` có thể null | `"OK".equals(value)` hoặc `Objects.equals` |
| `name.isBlank() || name == null` | Dereference trước khi kiểm tra null | `name == null || name.isBlank()` |
| `list != null` rồi gọi `list.get(0)` | List có thể rỗng | Kiểm tra size/isEmpty; phân biệt NPE với `IndexOutOfBoundsException` |
| `array != null` rồi gọi `array[0].length()` | Phần tử `array[0]` có thể null | Kiểm tra bounds và element |
| `Integer n = map.get(key); int x = n;` | Map trả null, unboxing gây NPE | Xác định default hay báo thiếu |
| `if (user != null) user.getAddress().city()` | `getAddress()` vẫn có thể null | Guard từng tầng hoặc invariant |
| `Optional.of(value)` với giá trị nullable | `of` ném NPE | `Optional.ofNullable` |
| `optional.orElse("x")` khi chính `optional` null | Optional reference cũng có thể null | API phải trả Optional không null |
| `List.of(value)` với null | Factory không nhận null element | Validate hoặc dùng cấu trúc cho phép null |
| `try { ... } catch (NPE) { return null; }` | Che bug và khó debug | Xác định receiver thiếu, xử lý theo contract |
| `Objects.requireNonNull` cho mọi field kể cả optional | Biến trạng thái thiếu hợp lệ thành exception | Phân biệt required và optional |
| `null` luôn thay được bằng 0 hoặc chuỗi rỗng | 0/empty có ý nghĩa khác “không có” | Chọn fallback theo nghiệp vụ |
| Annotation `@NonNull` là đủ | Tooling không nhất thiết enforce runtime | Validation và test ở boundary |
| `System.gc()` xử lý NPE | NPE không phải vấn đề GC | Sửa logic reference/null |
| Thấy dấu chấm thì NPE chắc chắn ở object đầu | Một receiver trung gian mới có thể null | Xem từng dereference và stack trace |

## 25. Tình huống thực tế: API dữ liệu khách hàng

Một ứng dụng nhận tên và danh sách vai trò từ dữ liệu bên ngoài. Yêu cầu:
- Tên bắt buộc, không thể null/blank.
- Vai trò có thể vắng mặt, khi đó mặc định **danh sách rỗng**.
- Danh sách không được chứa phần tử null.
- Object hoàn tất khởi tạo không cho caller sửa nội dung vai trò qua alias.

Tạo file **`CustomerNullBoundaryDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;

public class CustomerNullBoundaryDemo {
    static final class Customer {
        private final String name;
        private final List<String> roles;

        Customer(String name, List<String> roles) {
            Objects.requireNonNull(name, "name");

            String normalized = name.strip();
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("name must not be blank");
            }

            this.name = normalized;
            this.roles = roles == null ? List.of() : List.copyOf(roles);
        }

        String summary() {
            return name + " roles=" + roles.size();
        }

        List<String> roles() {
            return roles;
        }
    }

    public static void main(String[] args) {
        Customer first = new Customer("  Mai  ", null);
        Customer second = new Customer("An", List.of("READER"));

        System.out.println(first.summary());
        System.out.println(second.summary());

        try {
            new Customer(null, List.of());
        } catch (NullPointerException ex) {
            System.out.println("name is required");
        }

        try {
            new Customer("Binh", java.util.Arrays.asList("READER", null));
        } catch (NullPointerException ex) {
            System.out.println("null role rejected");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CustomerNullBoundaryDemo.java
java CustomerNullBoundaryDemo
~~~

Stdout:

~~~text
Mai roles=0
An roles=1
name is required
null role rejected
~~~

Phân tích:

- `Objects.requireNonNull(name)` xác định name là trường **bắt buộc**.
- `name.strip()` chỉ chạy sau khi đã loại trừ null.
- `roles == null ? List.of() : List.copyOf(roles)` áp dụng chính sách **roles tùy chọn**.
- `List.of()` tạo danh sách rỗng không sửa được, khác với tham chiếu null.
- `List.copyOf(roles)` từ chối phần tử null và bảo vệ cấu trúc list khỏi bị thay đổi từ bên ngoài theo cách thông thường.
- Vì phần tử role là `String` immutable, ví dụ này không có nguy cơ sửa trạng thái phần tử qua mutable alias. Nếu là list object mutable thì cần xét defensive copy sâu phù hợp.

**Thiết kế khác cũng có thể đúng:** Nếu roles bắt buộc, hãy thay fallback bằng `Objects.requireNonNull(roles, "roles")`. Đừng máy móc chọn empty list khi chưa xác định ý nghĩa của thiếu dữ liệu.

## 26. Câu hỏi thường gặp

### 26.1. `String.valueOf(null)` có ném NPE không?

Khi gọi overload có tham số tham chiếu `Object` phù hợp một cách tường minh, `String.valueOf((Object) null)` trả chuỗi `"null"`. Với lời gọi literal `String.valueOf(null)`, compiler có thể chọn overload nhận `char[]` cụ thể hơn `Object`/`String` theo các overload hiện có; xử lý `char[]` null có thể ném NPE. Vì thế **không nên coi mọi cách gọi `String.valueOf(null)` là an toàn**, đặc biệt khi literal null gặp overloading. Hãy dùng:

~~~java
String text = String.valueOf((Object) null); // "null"
~~~

hoặc một fallback có chủ đích:

~~~java
String text = java.util.Objects.toString(null, "(missing)");
~~~

Đây là những mảnh mã minh họa trong method. Trường hợp này minh họa một lỗi quan trọng: **overload resolution** xảy ra ở compile time và kiểu biểu thức argument có thể làm thay đổi method được gọi.

### 26.2. `Objects.toString(null)` có ném NPE không?

`Objects.toString((Object) null)` trả chuỗi `"null"` theo API; `Objects.toString(value, defaultValue)` cho phép quy định fallback. Khác với gọi `value.toString()` trực tiếp trên biến null.

### 26.3. `new Customer(...)` có trả null nếu constructor thất bại không?

Không. Nếu constructor hoặc initializer ném exception mà không được xử lý trong quá trình tạo, biểu thức `new` **kết thúc bất thường** và không cung cấp reference thành công. Nó không tự “trả null để báo lỗi”. Caller cần xử lý exception theo hợp đồng. Một factory method hoặc lookup method **có thể tự chọn** trả null, nhưng đó là chuyện của method, không phải quy tắc `new`.

### 26.4. `null.equals(value)` hợp lệ không?

Không thể dùng literal `null` như receiver có kiểu phù hợp để gọi method theo cách thông thường; việc gọi instance method trên một **biến** đang null sẽ dẫn đến NPE. Cách đúng để so sánh có xử lý null là `Objects.equals(a, b)` hoặc receiver chắc chắn khác null.

### 26.5. Thấy NPE ở `list.get(0).length()` thì list có chắc chắn null không?

Không. `list` có thể khác null, `get(0)` thành công và **trả phần tử null**, rồi `length()` mới gây NPE. Nếu list rỗng, `get(0)` thường gây `IndexOutOfBoundsException`. Cần phân tích các mắt xích và loại lỗi thực tế.

### 26.6. Có nên trả null từ getter không?

Phụ thuộc hợp đồng. Getter của trường bắt buộc không nên trả null khi object ở trạng thái hợp lệ. Với giá trị tùy chọn, có thể trả nullable và ghi rõ hợp đồng hoặc dùng `Optional<T>` ở một số API. Không mặc định mọi getter cần Optional; cân nhắc sự rõ ràng, hiệu năng, công cụ phân tích và chính sách dự án.

### 26.7. Vì sao đổi mọi field sang `Optional<T>` chưa chắc tốt?

Optional vẫn là reference type có thể bị gán null, không tự tạo invariant trong constructor; việc thêm Optional vào mọi field có thể làm mô hình và serialization trở nên rườm rà. Quan trọng hơn là **định nghĩa trạng thái hợp lệ và ranh giới dữ liệu**.

### 26.8. `Optional.ofNullable(null).orElse(...)` có luôn an toàn không?

`Optional.ofNullable(null)` trả Optional rỗng; `orElse` lấy fallback. Nhưng biểu thức tính fallback có thể có side effect hoặc ném exception **trước khi `orElse` được gọi** vì Java đánh giá arguments. Nếu fallback cần tính toán tốn kém, dùng `orElseGet(() -> computeFallback())` khi thích hợp.

## 27. Bài tập dự đoán trước khi chạy

### Bài 1 — Null xuất phát từ tầng nào?

~~~java
String city = customer.getAddress().getCity();
~~~

Hãy liệt kê các trường hợp NPE. Đáp án: `customer` có thể null; `getAddress()` có thể trả null; bản thân `getAddress()` hoặc `getCity()` cũng có thể ném NPE do logic bên trong. Nếu `getCity()` chỉ trả null thì phép gán `String city = null` vẫn hợp lệ; NPE có thể xảy ra ở lần dereference `city` sau đó.

### Bài 2 — Short-circuit

Dự đoán với `String s = null;`:

~~~java
boolean a = s == null || s.isBlank();
boolean b = s != null && !s.isBlank();
~~~

Kết quả: `a == true`, `b == false`, không NPE. Với thứ tự `s.isBlank() || s == null` sẽ NPE.

### Bài 3 — Null wrapper

~~~java
Integer score = null;
// int doubled = score * 2;
~~~

Nếu bỏ comment dòng hai sẽ xảy ra **NPE do unboxing**. Hãy viết một phiên bản từ chối null bằng `IllegalArgumentException`, và một phiên bản chấp nhận null như giá trị thiếu rồi trả kết quả mặc định theo yêu cầu riêng.

### Bài 4 — Container khác phần tử

~~~java
String[] a = null;
String[] b = new String[1];
String[] c = new String[0];
~~~

- `a.length` → NPE.
- `b.length` → 1.
- `b[0] == null` → true.
- `b[0].length()` → NPE.
- `c.length` → 0.
- `c[0]` → `ArrayIndexOutOfBoundsException`, không phải NPE.

### Bài 5 — Chọn chính sách ở constructor

Một class `Invoice` yêu cầu `invoiceId` bắt buộc và `description` tùy chọn. Hãy thiết kế constructor sao cho:
- `invoiceId == null` hoặc blank bị từ chối.
- `description == null` có thể được chuẩn hóa thành `""` nếu nghiệp vụ cho phép.
- Mọi object tạo thành công luôn có một ID hợp lệ.
- Getter không trả null cho ID bắt buộc.

### Bài 6 — Xử lý một nguồn Map nullable

Cho `Map<String,Integer> scores` có thể không chứa khóa. Viết method `int getScoreOrZero(String id)`, nhưng chỉ dùng giá trị 0 nếu **thiếu khóa** thực sự tương đương 0 theo nghiệp vụ. Viết thêm method từ chối khi thiếu với message chứa tên tham số an toàn. Nếu Map cho phép mapped value null, dùng `containsKey` khi cần phân biệt null value và absent key.

## 28. Checklist tự đánh giá

- [ ] Tôi phân biệt null với chuỗi rỗng, mảng rỗng và collection rỗng.
- [ ] Tôi biết field reference mặc định null nhưng local variable chưa gán không được đọc.
- [ ] Tôi xác định được receiver nào null trong một chuỗi nhiều dấu chấm.
- [ ] Tôi hiểu NPE có thể xảy ra khi đọc field, gọi method, dùng array, foreach, synchronized, throw null hoặc auto-unboxing.
- [ ] Tôi phân biệt NPE với `ArrayIndexOutOfBoundsException` và các exception khác.
- [ ] Tôi biết `a == null` an toàn, trong khi `a.method()` cần receiver object.
- [ ] Tôi sử dụng `||`/`&&` short-circuit theo đúng thứ tự.
- [ ] Tôi đặt guard clause khi null không hợp lệ hoặc cần fallback theo hợp đồng.
- [ ] Tôi biết `Objects.requireNonNull` cố ý ném NPE, còn `Objects.equals` xử lý null an toàn.
- [ ] Tôi biết `Optional.of` khác `Optional.ofNullable` và không dùng null Optional.
- [ ] Tôi biết `Map.get` có thể trả null vì khóa vắng mặt hoặc mapped value null.
- [ ] Tôi kiểm tra cả container null và null elements khi cần.
- [ ] Tôi hiểu `Integer`/`Boolean` null có thể gây NPE khi unboxing.
- [ ] Tôi biết constructor/value object có thể bảo vệ invariant để giảm NPE lan truyền.
- [ ] Tôi không dùng catch NPE để âm thầm che lỗi lập trình.
- [ ] Tôi biết enhanced NPE message và stack trace hữu ích để debug nhưng không phải hợp đồng văn bản cố định.
- [ ] Tôi có test cho input bắt buộc null, input tùy chọn null, chuỗi dereference và collection/array.
- [ ] Tôi chạy và giải thích được stdout của các ví dụ Java 17+ trong bài.

**Kết luận:** `NullPointerException` không đơn thuần là một “lỗi vì biến bằng null”; nó cho biết code đã **dùng giá trị null ở nơi cần object hợp lệ** hoặc cố ý kiểm tra hợp đồng bằng cách ném NPE. Cách phòng tránh bền vững là **xác định dữ liệu nào bắt buộc, dữ liệu nào được phép vắng mặt; thiết lập invariant ngay từ ranh giới tạo/nhận dữ liệu; kiểm tra đúng điểm; và kiểm thử các đường null**. Khi biết chính xác reference nào có thể null và người gọi cần làm gì khi thiếu giá trị, Java code sẽ rõ nghĩa và ít gặp NPE bất ngờ hơn.
