# Lựa chọn record hay lớp thông thường trong Java 17+

**`record` và `class` đều định nghĩa reference types trong Java, nhưng chúng truyền tải ý định thiết kế khác nhau.** Record phù hợp khi đối tượng chủ yếu là **một bộ dữ liệu minh bạch, có components xác định và ngữ nghĩa gần với giá trị**. Lớp thông thường phù hợp khi đối tượng cần **identity, lifecycle, trạng thái nội bộ phức tạp, khả năng thay đổi có kiểm soát, che giấu representation hoặc kế thừa một class khác**.

So sánh ngắn:

~~~java
record Point(int x, int y) {}
~~~

~~~java
final class PointClass {
    private final int x;
    private final int y;

    PointClass(int x, int y) {
        this.x = x;
        this.y = y;
    }

    int x() {
        return x;
    }

    int y() {
        return y;
    }

    // Nếu cần value equality còn phải viết equals/hashCode.
}
~~~

Record ngắn hơn không chỉ vì Java tạo sẵn methods; nó còn công bố một hợp đồng: **state quan sát được của instance chính là tập record components**. Việc một kiểu chỉ có hai fields không có nghĩa nó luôn phải là record.

Bài độc lập thuộc **Java Core — Class & Object / Record**, ưu tiên **Java 17+**. Các ví dụ hoàn chỉnh có filename, lệnh `javac`/`java` và stdout dự kiến. Snippets nhằm giải thích một điểm riêng được đánh dấu rõ. Mục tiêu là chọn thiết kế đúng trước khi tối ưu cú pháp.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Nhận diện **transparent data carrier** và phân biệt với **entity có identity**.
2. Quyết định khi nào record hợp lý và khi nào ordinary class tốt hơn.
3. Giải thích compiler sinh ra constructor, accessors, `equals`, `hashCode`, `toString` cho record như thế nào.
4. Hiểu record có final component fields nhưng không mặc nhiên deep immutable.
5. Phân biệt value equality và identity equality.
6. Biết records implicitly final, implicitly extend `java.lang.Record` và không thể extend class tùy ý.
7. Hiểu class có thể mutable hoặc immutable, final hoặc extensible.
8. Biết record không khai báo additional instance fields hay instance initializer blocks.
9. Biết record vẫn có instance/static methods, static fields và implements interfaces.
10. Viết compact/canonical constructor để validation và normalization.
11. Nhận diện vấn đề shallow copy, mutable List, Map và array.
12. Hiểu vì sao array component ảnh hưởng default equals/hashCode.
13. Biết ordinary class có thể chủ động che giấu internal representation.
14. Dự đoán tác động của việc thêm, xóa hoặc đổi type record components lên API.
15. Chọn model cho DTO, value object, domain entity, service, repository và resource.
16. Biết record không tự động thích hợp với mọi ORM/entity framework.
17. Hiểu method naming `component()` khác JavaBean-style `getComponent()`.
18. Hiểu identity, version, lifecycle, concurrency, thread-safety và serializability không chỉ phụ thuộc cú pháp.
19. Chọn class khi cần inheritance/hook points hoặc mutable cache/locking.
20. Xem xét hiệu năng bằng đo đạc, không suy luận record luôn nhỏ/nhanh hơn.
21. Refactor từ class sang record và ngược lại mà vẫn kiểm tra contract.
22. Test invariants, aliasing, equality, hash stability và public API đúng mục đích.

## 2. Câu hỏi đầu tiên: “Dữ liệu này là giá trị hay một thực thể?”

Một **value object** thường được xác định chủ yếu bởi dữ liệu:

- Điểm tọa độ (x, y).
- Khoảng ngày start/end.
- Mã tiền tệ và lượng tiền.
- Kết quả tính toán.
- Snapshot cấu hình bất biến.
- Bản ghi truyền dữ liệu có components ổn định.

Hai instances mang cùng components được kỳ vọng **tương đương theo giá trị**. Đây là đối tượng ứng viên tốt cho record.

Một **entity** thường có identity riêng qua thời gian:

- Tài khoản với ID và balance biến đổi.
- Đơn hàng có trạng thái chuyển đổi và lifecycle.
- Session, socket, database transaction hoặc thread owner.
- Aggregate root phải bảo vệ state changes.
- Đối tượng có audit history hoặc optimistic locking.

Hai entities có cùng data fields **chưa chắc là cùng entity**. Ordinary class thường cho phép biểu diễn identity/lifecycle rõ hơn.

**Lưu ý:** Không có quy tắc “mọi domain entity bắt buộc class, mọi DTO bắt buộc record”. Hãy xét invariants và API của từng kiểu.

## 3. Bảng quyết định cốt lõi

| Tiêu chí | Record thường phù hợp | Lớp thông thường thường phù hợp |
| --- | --- | --- |
| Đặc trưng | Transparent value data | Identity, behavior, lifecycle, encapsulated state |
| Fields | Từ components, final | Tùy ý instance fields và mutability |
| Constructor | Canonical constructor gắn với components | Constructors linh hoạt về representation |
| Accessors | `name()`, `age()` theo components | API getter/commands tự thiết kế |
| Equality mặc định | Theo record components | Theo Object identity nếu không override |
| `hashCode` mặc định | Dựa trên components | Identity-based Object behavior nếu không override |
| `toString` mặc định | In name/components | `ClassName@...` theo Object implementation |
| Extends base class | Không được chọn superclass | Có thể extends một class không final |
| Implements interfaces | Có | Có |
| Additional instance fields | Không | Có |
| Instance initializer blocks | Không | Có |
| Deep immutable tự động | Không | Cũng không |
| Mutable business state | Thường không phù hợp | Có thể thể hiện có kiểm soát |
| Hidden internal representation | Hạn chế hơn do transparent components | Linh hoạt |
| Framework yêu cầu no-arg mutable bean | Có thể không phù hợp | Có thể phù hợp |
| Stable API qua representation changes | Cần đặc biệt cân nhắc | Có thể che giấu state |
| Reusable service/resource | Thường không nên | Thường phù hợp |

Lựa chọn thiết kế phải dựa trên **tính chất logic của đối tượng**, không chỉ số lượng dòng source.

## 4. Những thứ Java sinh ra cho record

Với:

~~~java
record Coordinate(int x, int y) {}
~~~

Java cung cấp:

- Hai private final component fields `x`, `y`.
- Accessors `x()` và `y()`.
- Canonical constructor `Coordinate(int x, int y)` nếu bạn không tự khai báo.
- `equals(Object)` với component-based equality.
- `hashCode()` dựa trên components.
- `toString()` gồm record name và tên/giá trị components.

Record type là final, kế thừa `java.lang.Record` và có thể implements interfaces. Record không có instance field tự do ngoài components.

### Những thứ record **không** sinh ra

- Validation cho null/range/format.
- Defensive copying của List, array hoặc mutable object.
- Deep immutability.
- Database persistence, JSON conversion hoặc ORM mapping.
- Builder, setter hoặc lifecycle callback.
- External stable ID cho từng instance.
- Custom business formatting hoặc privacy-safe logging policy.

Những nhu cầu đó vẫn cần thiết kế explicit.

## 5. Chương trình chạy: record tự sinh các operations

Tạo **`RecordBasicsDemo.java`**:

~~~java
public class RecordBasicsDemo {
    record Coordinate(int x, int y) {}

    public static void main(String[] args) {
        Coordinate first = new Coordinate(3, 4);
        Coordinate second = new Coordinate(3, 4);

        System.out.println("x=" + first.x());
        System.out.println("y=" + first.y());
        System.out.println("equal=" + first.equals(second));
        System.out.println("same object=" + (first == second));
        System.out.println(first);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordBasicsDemo.java
java RecordBasicsDemo
~~~

Stdout:

~~~text
x=3
y=4
equal=true
same object=false
Coordinate[x=3, y=4]
~~~

Hai reference khác nhau (`== false`) nhưng record values bằng nhau qua generated `equals`. Không dùng `==` để so sánh logical value của records do mình tạo bằng những lần `new` độc lập.

## 6. Ordinary class có thể mô phỏng record không?

Có. Một ordinary class có thể viết final fields, constructor, accessors, `equals`, `hashCode` và `toString` để có value semantics tương tự.

Điều record mang lại là:
- ít boilerplate hơn khi representation chính là data components;
- compiler kiểm tra một số structural restrictions;
- ý định value carrier hiện rõ trong declaration;
- standard reflection hỗ trợ record components.

Điều **class** vẫn mang lại:
- quyền quyết định representation ẩn;
- tự chọn constructor/API;
- mutable hoặc immutable state;
- ability to extend một suitable superclass;
- fields và internal helpers không nhất thiết expose thành record components.

Vì vậy câu hỏi không phải “Class có làm được không?” mà là “Public contract có đúng là các component values ấy không?”.

## 7. Chương trình chạy: class immutable với value equality tường minh

Tạo **`ImmutableClassDemo.java`**:

~~~java
import java.util.Objects;

public class ImmutableClassDemo {
    static final class Coordinate {
        private final int x;
        private final int y;

        Coordinate(int x, int y) {
            this.x = x;
            this.y = y;
        }

        int x() {
            return x;
        }

        int y() {
            return y;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Coordinate point)) {
                return false;
            }
            return x == point.x && y == point.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }

        @Override
        public String toString() {
            return "Coordinate[x=" + x + ", y=" + y + "]";
        }
    }

    public static void main(String[] args) {
        Coordinate a = new Coordinate(3, 4);
        Coordinate b = new Coordinate(3, 4);

        System.out.println("equal=" + a.equals(b));
        System.out.println("hash equal=" +
                (a.hashCode() == b.hashCode()));
        System.out.println(a);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ImmutableClassDemo.java
java ImmutableClassDemo
~~~

Stdout:

~~~text
equal=true
hash equal=true
Coordinate[x=3, y=4]
~~~

Như vậy record không phải lựa chọn duy nhất cho value object; nó phù hợp khi explicit components phản ánh đúng representation và API mong muốn.

## 8. So sánh value identity và domain identity

Xét:

~~~java
record CustomerSnapshot(long id, String name) {}
~~~

Hai snapshots có cùng id và name sẽ `equals` true. Nếu cùng customer id nhưng tên đổi, snapshots `equals` false. Điều đó có thể **đúng** nếu snapshot có nghĩa là “trạng thái tại thời điểm quan sát”.

Ngược lại, với domain `Customer` entity:
- id có thể xác định identity;
- name có thể thay đổi;
- persistence version, trạng thái, business operations có lifecycle;
- equality có thể theo domain identity hoặc dựa chính xác trên reference, tùy thiết kế.

Nếu record `Customer(id, name)` bị sử dụng thay entity mà business cho rằng chỉ id quan trọng, generated equality có thể sai semantics.

**Quy tắc:** Hãy phát biểu trước: “Hai instances khi nào được coi là cùng giá trị? Khi nào được coi là cùng thực thể?”

## 9. Ví dụ chạy: cùng entity ID nhưng snapshots khác nhau

Tạo **`SnapshotVsIdentityDemo.java`**:

~~~java
public class SnapshotVsIdentityDemo {
    record CustomerSnapshot(long id, String name) {}

    static final class Customer {
        private final long id;
        private String name;

        Customer(long id, String name) {
            this.id = id;
            this.name = name;
        }

        long id() {
            return id;
        }

        void rename(String newName) {
            if (newName == null || newName.isBlank()) {
                throw new IllegalArgumentException("name");
            }
            name = newName;
        }

        CustomerSnapshot snapshot() {
            return new CustomerSnapshot(id, name);
        }
    }

    public static void main(String[] args) {
        Customer customer = new Customer(7, "Mai");
        CustomerSnapshot before = customer.snapshot();

        customer.rename("Mai Anh");
        CustomerSnapshot after = customer.snapshot();

        System.out.println("same customer ID=" +
                (before.id() == after.id()));
        System.out.println("same snapshot=" + before.equals(after));
        System.out.println(after);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SnapshotVsIdentityDemo.java
java SnapshotVsIdentityDemo
~~~

Stdout:

~~~text
same customer ID=true
same snapshot=false
CustomerSnapshot[id=7, name=Mai Anh]
~~~

Đây là thiết kế kết hợp rất hữu ích: **mutable entity class** thực hiện domain commands, **record snapshot** chuyển trạng thái hiện tại sang một data value.

## 10. “Immutable record” có phải luôn đúng?

Record fields tương ứng components là `final`. Nhưng nếu component type là mutable object, Java chỉ cố định **reference** chứ không cố định nội dung object đó.

~~~java
record Team(java.util.List<String> members) {}
~~~

`members` field không thể gán sang một List khác sau construction, nhưng chính List object có thể mutate nếu caller giữ alias.

### Chương trình chạy

Tạo **`ShallowRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowRecordDemo {
    record Team(List<String> members) {}

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("Mai"));
        Team team = new Team(source);

        source.add("An");
        System.out.println(team.members());

        team.members().add("Binh");
        System.out.println(source);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ShallowRecordDemo.java
java ShallowRecordDemo
~~~

Stdout:

~~~text
[Mai, An]
[Mai, An, Binh]
~~~

Một record không có setter vẫn có thể lộ mutable component. Nếu API hứa immutable snapshot, phải defensive-copy.

## 11. Record có thể làm immutable value carrier bằng explicit validation/copy

Ví dụ:

~~~java
record Team(java.util.List<String> members) {
    Team {
        members = java.util.List.copyOf(members);
    }
}
~~~

`List.copyOf` tạo unmodifiable snapshot của list structure (có thể reuse suitable unmodifiable source), cấm null elements và không deep-copy mutable element objects.

Với `List<String>` vì String immutable, pattern thường đủ bảo vệ value semantics. Với `List<MutablePerson>`, muốn deep immutability còn phải snapshot các elements.

### Class cũng có thể làm vậy

Ordinary class không kém an toàn nếu constructor defensive-copy và accessors không lộ representation. Bảo vệ state là **design contract**, không phải “phép màu” của record.

## 12. Chương trình chạy: record có defensive copy

Tạo **`SafeTeamRecordDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeTeamRecordDemo {
    record Team(List<String> members) {
        Team {
            members = List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("Mai"));
        Team team = new Team(source);

        source.add("An");
        System.out.println("source=" + source);
        System.out.println("record=" + team.members());

        try {
            team.members().add("Binh");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SafeTeamRecordDemo.java
java SafeTeamRecordDemo
~~~

Stdout:

~~~text
source=[Mai, An]
record=[Mai]
unmodifiable
~~~

Record ổn định với structural List changes bên ngoài. Nếu không muốn `List.copyOf` cấm null elements hoặc không muốn snapshot semantics, cần thiết kế khác và document rõ.

## 13. Mảng là trường hợp cần cân nhắc đặc biệt

~~~java
record Payload(byte[] bytes) {}
~~~

Array mutable và default record accessor `bytes()` trả chính array reference. Hơn nữa, generated `equals`/`hashCode` xử lý array component dựa theo identity, **không tự so sánh byte content**.

Một record với array component muốn value semantics cần:
- copy input ở constructor;
- copy output ở accessor;
- override `equals`/`hashCode` nếu muốn element-wise equality;
- cân nhắc `toString` không in binary data quá dài hoặc nhạy cảm.

Khi những tùy chỉnh đó chiếm phần lớn implementation, ordinary immutable class có explicit `byteAt(index)`, `size()`, `copyBytes()` có thể dễ quản lý hơn.

## 14. Chương trình chạy: record array và content equality tùy chỉnh

Tạo **`RecordBytesDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class RecordBytesDemo {
    record Blob(byte[] bytes) {
        Blob {
            bytes = Objects.requireNonNull(bytes, "bytes").clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Blob blob &&
                    Arrays.equals(bytes, blob.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }

        @Override
        public String toString() {
            return "Blob[length=" + bytes.length + "]";
        }
    }

    public static void main(String[] args) {
        byte[] input = {1, 2, 3};
        Blob a = new Blob(input);
        Blob b = new Blob(new byte[]{1, 2, 3});

        input[0] = 99;

        System.out.println("equal=" + a.equals(b));
        System.out.println("first=" + a.bytes()[0]);
        System.out.println(a);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordBytesDemo.java
java RecordBytesDemo
~~~

Stdout:

~~~text
equal=true
first=1
Blob[length=3]
~~~

Khi accessor defensive-copy và equality theo bytes, record có thể ổn định. Tuy nhiên ordinary class cũng có thể diễn đạt contract tương tự; độ phức tạp representation là lý do cân nhắc class.

## 15. Phạm vi biểu diễn: record làm lộ điều gì?

Trong:

~~~java
public record Address(String city, String postalCode) {}
~~~

`city()` và `postalCode()` là public accessors, canonical constructor có component parameters đúng shape. Record thể hiện rằng hai components là **bề mặt API mang ý nghĩa dữ liệu**.

Với ordinary class:

~~~java
public final class Address {
    private final String normalizedKey;

    public Address(String city, String postalCode) {
        // Có thể lưu internal representation khác.
        normalizedKey = city + "|" + postalCode;
    }

    public String display() {
        return normalizedKey;
    }
}
~~~

Class có thể che giấu representation và chỉ expose behavior `display()`. Nếu mai sau đổi từ hai fields thành một normalized key hay chuyển backend structure, public API có thể giữ nguyên khi design cho phép.

**Chọn record khi công bố components chính là mục đích**, không chỉ vì bản đầu tiên có vài fields.

## 16. Các component names là một phần API

Ở record:

~~~java
public record Employee(String firstName, String lastName) {}
~~~

Clients dùng `employee.firstName()` và `employee.lastName()`. Đổi tên component thành `givenName` có thể làm mã gọi accessor cũ không compile.

Thêm component vào record:
- thay đổi canonical constructor signature;
- tạo accessor mới;
- có thể thay đổi `equals/hashCode/toString` generated behavior;
- ảnh hưởng deconstruction/serialization/framework bindings theo compatibility contract.

Bạn có thể cung cấp overloaded constructors hoặc compatibility methods nếu phù hợp, nhưng không có nghĩa mọi thay đổi đều binary/source compatible.

### Ordinary class cũng có API cost

Class đổi public constructor/getters cũng phá callers. Khác biệt là class có nhiều tự do hơn để giữ API **không bị buộc theo representation**.

## 17. Ví dụ chạy: constructor overload giúp giữ nguồn gọi cũ

Tạo **`RecordOverloadDemo.java`**:

~~~java
public class RecordOverloadDemo {
    record Product(String code, int quantity, String note) {
        Product {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code");
            }
            if (quantity < 0) {
                throw new IllegalArgumentException("quantity");
            }
            note = note == null ? "" : note;
        }

        Product(String code, int quantity) {
            this(code, quantity, "");
        }
    }

    public static void main(String[] args) {
        Product oldForm = new Product("A", 2);
        Product newForm = new Product("A", 2, "gift");

        System.out.println(oldForm);
        System.out.println(newForm);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordOverloadDemo.java
java RecordOverloadDemo
~~~

Stdout:

~~~text
Product[code=A, quantity=2, note=]
Product[code=A, quantity=2, note=gift]
~~~

Overload `Product(String,int)` có thể giúp source clients tiếp tục viết hai arguments. Nhưng record shape giờ là ba components và generated equality cũng xem cả `note`; đây vẫn là một semantic API change cần review.

## 18. Constructors của record: canonical và compact

Canonical constructor có parameters tương ứng record components. Dạng compact giảm boilerplate:

~~~java
record Age(int value) {
    Age {
        if (value < 0 || value > 150) {
            throw new IllegalArgumentException("age");
        }
    }
}
~~~

Nếu muốn normalize:

~~~java
record Code(String text) {
    Code {
        text = text.strip().toUpperCase(
                java.util.Locale.ROOT);
    }
}
~~~

Trong compact constructor:
- tên `value`/`text` là implicit canonical parameters;
- compiler tự gán component fields ở cuối body bình thường;
- gán `this.text = ...` trong compact constructor không hợp lệ;
- nếu invariant bị vi phạm, throw trước khi object được công bố.

Ordinary class constructor tự quyết định assignments và internal fields. Đây là ưu điểm khi cần representation phức tạp, nhưng cũng đòi viết đầy đủ.

## 19. Chương trình chạy: validation trên record và class

Tạo **`ValidationComparisonDemo.java`**:

~~~java
import java.util.Objects;

public class ValidationComparisonDemo {
    record UsernameRecord(String value) {
        UsernameRecord {
            value = Objects.requireNonNull(value, "value")
                    .strip()
                    .toLowerCase(java.util.Locale.ROOT);
            if (value.isEmpty()) {
                throw new IllegalArgumentException("blank");
            }
        }
    }

    static final class UsernameClass {
        private final String value;

        UsernameClass(String value) {
            String normalized =
                    Objects.requireNonNull(value, "value")
                            .strip()
                            .toLowerCase(java.util.Locale.ROOT);
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("blank");
            }
            this.value = normalized;
        }

        String value() {
            return value;
        }
    }

    public static void main(String[] args) {
        UsernameRecord record = new UsernameRecord("  Admin ");
        UsernameClass clazz = new UsernameClass("  Admin ");

        System.out.println(record.value());
        System.out.println(clazz.value());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ValidationComparisonDemo.java
java ValidationComparisonDemo
~~~

Stdout:

~~~text
admin
admin
~~~

Record giúp biểu đạt ít code hơn; **cả hai đều có thể bảo vệ invariant đúng**. Không chọn chỉ dựa vào khả năng validate.

## 20. Record không cho thêm instance fields tùy ý

Một record declaration không thể khai báo extra instance fields ngoài fields từ components:

~~~java
record Request(String id) {
    // private int retryCount; // Compile error.
}
~~~

Nó cũng không được viết instance initializer block kiểu class thường. Record có thể có static fields/methods, instance methods, compact/canonical/overloaded constructors, nested type declarations hợp lệ.

### Vì sao restriction có ý nghĩa?

Record tuyên bố instance state được mô tả bằng components. Nếu có thêm hidden instance fields, default structural equality và transparent data-carrier model dễ trở nên bất nhất.

Ordinary class cho phép thêm retryCount, caches, locks, lazy computation state hoặc resource handles không nằm trong public API.

## 21. Chương trình chạy: class có cache nội bộ

Tạo **`CachingClassDemo.java`**:

~~~java
public class CachingClassDemo {
    static final class Document {
        private final String text;
        private Integer cachedLength;

        Document(String text) {
            this.text = java.util.Objects.requireNonNull(text);
        }

        int length() {
            if (cachedLength == null) {
                cachedLength = text.length();
            }
            return cachedLength;
        }
    }

    public static void main(String[] args) {
        Document document = new Document("Java");

        System.out.println(document.length());
        System.out.println(document.length());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CachingClassDemo.java
java CachingClassDemo
~~~

Stdout:

~~~text
4
4
~~~

Đây chỉ là ví dụ về **hidden instance state** mà ordinary class có thể giữ. Nếu chạy đa luồng, lazy cache cần thread-safety policy; record không phải bất khả năng tính toán hay cache bên ngoài, nhưng không có thêm per-instance field tự do như class.

## 22. Record có methods, không chỉ getters

Record có thể chứa business operations thuần dựa trên components:

~~~java
record Rectangle(int width, int height) {
    Rectangle {
        if (width < 0 || height < 0) {
            throw new IllegalArgumentException("dimensions");
        }
    }

    long area() {
        return (long) width * height;
    }

    boolean isSquare() {
        return width == height;
    }
}
~~~

Methods không biến record thành ordinary class; chúng diễn giải data components.

**Tín hiệu phù hợp với record:** Method nhận state hiện tại, tính toán/tra cứu, trả kết quả mới hoặc record mới mà không mutate current record.

**Tín hiệu class:** Method điều phối vòng đời, thay đổi internal state, giữ transaction/session hoặc thay đổi identity trong thời gian dài.

## 23. Chương trình chạy: behavior có thể nằm trong record

Tạo **`RectangleRecordDemo.java`**:

~~~java
public class RectangleRecordDemo {
    record Rectangle(int width, int height) {
        Rectangle {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("size");
            }
        }

        long area() {
            return (long) width * height;
        }

        boolean isSquare() {
            return width == height;
        }
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(3, 4);
        Rectangle b = new Rectangle(5, 5);

        System.out.println("area=" + a.area());
        System.out.println("square=" + b.isSquare());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RectangleRecordDemo.java
java RectangleRecordDemo
~~~

Stdout:

~~~text
area=12
square=true
~~~

Không nên kết luận “record không được có logic”. Nó được có methods, miễn overall value-carrier contract vẫn đúng.

## 24. Mutation và domain commands

Một entity thường cần operations theo state transitions:

~~~java
final class Wallet {
    private int cents;

    Wallet(int initial) {
        if (initial < 0) {
            throw new IllegalArgumentException("initial");
        }
        cents = initial;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
        cents = Math.addExact(cents, amount);
    }

    int balance() {
        return cents;
    }
}
~~~

Nếu dùng record `Wallet(int cents)`, record field final không thể mutate bằng `deposit`. Bạn có thể thiết kế immutable value wallet với `deposit` trả record mới, nhưng nó sẽ có **khác biệt identity/lifecycle**. Chọn theo domain: một account entity cần command thay state hiện tại, hay một value state snapshot?

## 25. Chương trình chạy: class có trạng thái biến đổi

Tạo **`WalletEntityDemo.java`**:

~~~java
public class WalletEntityDemo {
    static final class Wallet {
        private int cents;

        Wallet(int initial) {
            if (initial < 0) {
                throw new IllegalArgumentException("initial");
            }
            cents = initial;
        }

        void deposit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount");
            }
            cents = Math.addExact(cents, amount);
        }

        int balance() {
            return cents;
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);

        wallet.deposit(50);
        wallet.deposit(25);

        System.out.println("balance=" + wallet.balance());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 WalletEntityDemo.java
java WalletEntityDemo
~~~

Stdout:

~~~text
balance=175
~~~

`Wallet` giữ identity của cùng object xuyên suốt hai operations. Nếu nhiều threads có thể cùng cập nhật, cần synchronization/transaction policy; bản minh họa này chưa hứa thread safety.

## 26. Nếu chọn immutable record thay vì mutable class?

Có thể thiết kế method trả **record mới**:

~~~java
record Balance(int cents) {
    Balance {
        if (cents < 0) {
            throw new IllegalArgumentException("cents");
        }
    }

    Balance deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
        return new Balance(Math.addExact(cents, amount));
    }
}
~~~

Code sử dụng phải giữ returned value:

~~~java
Balance before = new Balance(100);
Balance after = before.deposit(50);
~~~

`before` vẫn có 100. `after` chứa 150.

Đây là **functional/value-oriented update**, không phải mutating command. Trong concurrent system, thay một shared reference tới Balance vẫn cần đồng bộ riêng, ví dụ atomic update hoặc transaction.

## 27. Chương trình chạy: immutable update trả record mới

Tạo **`ImmutableBalanceDemo.java`**:

~~~java
public class ImmutableBalanceDemo {
    record Balance(int cents) {
        Balance {
            if (cents < 0) {
                throw new IllegalArgumentException("cents");
            }
        }

        Balance deposit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount");
            }
            return new Balance(Math.addExact(cents, amount));
        }
    }

    public static void main(String[] args) {
        Balance before = new Balance(100);
        Balance after = before.deposit(50);

        System.out.println("before=" + before.cents());
        System.out.println("after=" + after.cents());
        System.out.println("same object=" + (before == after));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ImmutableBalanceDemo.java
java ImmutableBalanceDemo
~~~

Stdout:

~~~text
before=100
after=150
same object=false
~~~

Nếu use case coi Balance là một **amount value** thì record hợp lý. Nếu là tài khoản sống qua transactions, class entity chứa business state và xuất Balance snapshot có thể hợp lý hơn.

## 28. Kế thừa class: record bị giới hạn có chủ ý

Mọi record implicitly extends `java.lang.Record` và implicitly final. Vì vậy:

~~~java
// record Child(...) extends Base { } // Không hợp lệ.
// class Sub extends MyRecord { }       // Không hợp lệ.
~~~

Ordinary class có thể:

~~~java
abstract class Shape {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}
~~~

Nếu thiết kế cần một base class có implementation/state common và polymorphic subclass hierarchy, ordinary classes phù hợp.

Nhưng **ưu tiên interface/composition khi có thể**; không chọn class chỉ vì có ý muốn kế thừa boilerplate nhỏ.

## 29. Record vẫn implements interfaces được

~~~java
interface Measurable {
    long area();
}

record Rectangle(int width, int height)
        implements Measurable {
    @Override
    public long area() {
        return (long) width * height;
    }
}
~~~

Record final nhưng implements interface bình thường. Một API nhận Measurable có thể chấp nhận record và class implementations.

Đây là lựa chọn quan trọng để tách **contract behavior** khỏi **representation data**:
- Record khi behavior được xác định bởi components.
- Class khi cần state/identity/lifecycle khác.
- Caller chỉ phụ thuộc interface.

## 30. Chương trình chạy: record và class cùng một interface

Tạo **`CommonInterfaceDemo.java`**:

~~~java
public class CommonInterfaceDemo {
    interface Measurable {
        long area();
    }

    record Rectangle(int width, int height)
            implements Measurable {
        @Override
        public long area() {
            return (long) width * height;
        }
    }

    static final class Square implements Measurable {
        private final int side;

        Square(int side) {
            this.side = side;
        }

        @Override
        public long area() {
            return (long) side * side;
        }
    }

    static void show(Measurable shape) {
        System.out.println("area=" + shape.area());
    }

    public static void main(String[] args) {
        show(new Rectangle(3, 4));
        show(new Square(5));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CommonInterfaceDemo.java
java CommonInterfaceDemo
~~~

Stdout:

~~~text
area=12
area=25
~~~

Một interface có thể chứa cả record và class implementations; không cần chọn một hình thức cho toàn bộ hierarchy.

## 31. Records và sealed interfaces (Java 17)

Java 17 hỗ trợ sealed interfaces để giới hạn direct implementations:

~~~java
sealed interface Outcome permits Success, Failure {}

record Success(String value) implements Outcome {}

record Failure(String message) implements Outcome {}
~~~

Records implicitly final nên là một lựa chọn tự nhiên cho những variant data values của sealed interface. Nhưng ordinary final classes cũng có thể là permitted implementations.

**Giới hạn:** Record không extends sealed **class** tùy ý, vì nó đã extends Record; nó có thể implement sealed **interface** khi được permits cho phép.

Cấu trúc sealed interface + records có ích cho finite result models; kết hợp switch/instanceof handling theo Java 17 syntax đã được hỗ trợ mà không bắt buộc preview features.

## 32. Chương trình chạy: sealed interface với hai records

Tạo **`SealedRecordResultDemo.java`**:

~~~java
public class SealedRecordResultDemo {
    sealed interface Result permits Success, Failure {}

    record Success(String value) implements Result {}

    record Failure(String message) implements Result {}

    static String describe(Result result) {
        if (result instanceof Success success) {
            return "ok:" + success.value();
        }
        if (result instanceof Failure failure) {
            return "error:" + failure.message();
        }
        throw new IllegalStateException("unknown");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("data")));
        System.out.println(describe(new Failure("missing")));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedRecordResultDemo.java
java SealedRecordResultDemo
~~~

Stdout:

~~~text
ok:data
error:missing
~~~

Java 17 hỗ trợ `instanceof` pattern matching; code không dùng record patterns hoặc pattern-matching switch vốn khác về mốc Java version.

## 33. Generic record có được không?

Có, record có thể khai báo type parameters:

~~~java
record Pair<L, R>(L left, R right) {}
~~~

Điều này khác với enum declaration (không được generic theo cách tương tự). Generic record vẫn chịu các rules về components, constructors và shallow immutability.

### Chương trình chạy

Tạo **`GenericRecordDemo.java`**:

~~~java
public class GenericRecordDemo {
    record Pair<L, R>(L left, R right) {}

    public static void main(String[] args) {
        Pair<String, Integer> item = new Pair<>("Java", 17);

        System.out.println(item.left());
        System.out.println(item.right());
        System.out.println(item);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericRecordDemo.java
java GenericRecordDemo
~~~

Stdout:

~~~text
Java
17
Pair[left=Java, right=17]
~~~

Generics tăng expressiveness nhưng không biến một generic record thành container mutable có hidden state. Nếu `L` hoặc `R` là mutable object, record field vẫn chỉ final reference.

## 34. Local record và nested record

Record có thể được khai báo như nested member type hoặc local type trong method/block theo Java 17 rules.

Một **nested record là implicitly static**; một **local record cũng implicitly static**, không capture enclosing instance hoặc method locals như ordinary local inner class:

~~~java
static int measure(int value) {
    record Data(int count) {}

    Data result = new Data(value);
    return result.count();
}
~~~

`value` được truyền qua constructor, không bị local record tự capture.

Tương tự, static nested record là một candidate tốt cho immutable result từ một service class.

### Khi cần inner class có outer instance?

Nếu type thực sự phụ thuộc enclosing outer object/lifecycle và cần captured context, ordinary inner/member/local class có semantics khác và có thể thích hợp hơn record.

## 35. Chương trình chạy: local record trong method

Tạo **`LocalRecordDemo.java`**:

~~~java
public class LocalRecordDemo {
    static String summarize(String name, int points) {
        record Score(String name, int points) {}

        Score score = new Score(name, points);
        return score.name() + "=" + score.points();
    }

    public static void main(String[] args) {
        System.out.println(summarize("Mai", 90));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 LocalRecordDemo.java
java LocalRecordDemo
~~~

Stdout:

~~~text
Mai=90
~~~

Local record giúp đóng gói data intermediary nhỏ trong một method, nhưng không buộc bạn biến mọi tuple trong method thành local record.

## 36. Persistence entity và ORM: cần xét framework contract

Nhiều ORM/entity frameworks yêu cầu những đặc điểm như:
- constructors nhất định (ví dụ no-arg accessible theo spec);
- managed identity;
- lazy-loading/proxy support;
- mutable persistent state hoặc enhancement;
- field/property access conventions;
- entity lifecycle callbacks;
- inheritance/proxy mechanisms.

Record implicitly final, components final và canonical constructor gắn với shape nên **không mặc nhiên thay thế phù hợp cho mọi persisted entity**.

Dùng ordinary class cho entity khi framework contract/lifecycle thực sự yêu cầu. Record vẫn có thể phù hợp làm:
- query projection;
- immutable DTO;
- API response;
- value snapshot;
- event payload;
- read model.

**Không khẳng định blanket rằng mọi ORM không hỗ trợ record**: khả năng DTO projection, embedding, mapping thay đổi theo framework/version/config. Cần đối chiếu documentation của stack cụ thể.

## 37. JSON, HTTP và data transfer boundaries

Record thường thuận tiện làm request/response DTO vì:
- component names là schema-like data attributes;
- ít boilerplate;
- generated `toString/equals/hashCode` có ích trong tests;
- canonical validation có thể bảo vệ minimal invariants.

Tuy nhiên JSON serialization/deserialization phụ thuộc library:
- có hỗ trợ record components không?
- nhận constructor parameters thế nào?
- tuân thủ field naming/annotations ra sao?
- xử lý missing fields/null/defaults ra sao?
- có gọi canonical constructor và validations không?
- có backward-compatibility schema requirements không?

Không mặc định chỉ vì code có record là API boundary được validate. Bean validation annotations hoặc framework-level checks có thể cần explicit activation.

### DTO vs domain object

Record DTO có thể giữ raw parsed data; domain value record có invariant nghiêm ngặt hơn. Đừng ép một type gánh quá nhiều trách nhiệm conversion, validation, persistence và business behavior.

## 38. Chương trình chạy: entity class xuất record DTO

Tạo **`EntityDtoDemo.java`**:

~~~java
public class EntityDtoDemo {
    record AccountDto(long id, String owner, int cents) {}

    static final class Account {
        private final long id;
        private final String owner;
        private int cents;

        Account(long id, String owner, int cents) {
            if (cents < 0) {
                throw new IllegalArgumentException("balance");
            }
            this.id = id;
            this.owner = java.util.Objects.requireNonNull(owner);
            this.cents = cents;
        }

        void deposit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("deposit");
            }
            cents = Math.addExact(cents, amount);
        }

        AccountDto snapshot() {
            return new AccountDto(id, owner, cents);
        }
    }

    public static void main(String[] args) {
        Account account = new Account(7, "Mai", 100);
        AccountDto before = account.snapshot();

        account.deposit(50);
        AccountDto after = account.snapshot();

        System.out.println("before=" + before.cents());
        System.out.println("after=" + after.cents());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EntityDtoDemo.java
java EntityDtoDemo
~~~

Stdout:

~~~text
before=100
after=150
~~~

Class quản lý lifecycle và mutation; record là immutable-by-field snapshot để truyền qua boundaries. Không phải mọi type của ứng dụng cần chọn cùng một syntax.

## 39. JavaBean naming và interoperability

Record component accessor có tên `name()`, không phải `getName()` tự động. Một class với JavaBeans-style API thường có `getName()` hoặc `isActive()`.

Một framework hoặc thư viện cũ chỉ introspect JavaBeans getters có thể không xử lý record accessors giống property getters nếu chưa có record-aware support.

Có thể thêm custom methods phù hợp vào record khi cần, nhưng đừng biến record thành một bản sao mutable JavaBean có setters (component fields final) chỉ để ép framework compatibility.

**Tiêu chí quyết định:** Nếu library integration chủ yếu dựa vào no-arg constructor và mutable setters, ordinary class có thể ít trở ngại hơn. Nếu library hỗ trợ Java records, record DTO có thể rất tự nhiên.

## 40. Record và serialization

Record **không tự implements Serializable**. Muốn Java serialization, cần công bố interface `Serializable` và xét object graph.

Records có Java serialization semantics đặc biệt (reconstruction thông qua canonical constructor theo serialization model); validation trong canonical constructor là một lý do đáng chú ý để cẩn trọng với dữ liệu deserialized.

Nhưng cũng phải cân nhắc:
- serialized compatibility khi thay đổi record components;
- null và missing component policies;
- mutable component graph;
- security của untrusted deserialization;
- versioning và migration.

Không dùng Java native serialization tùy tiện cho long-lived/public storage protocols. Với application contracts cần stable schema, cân nhắc explicit data format/schema management.

## 41. Record và `toString`: bảo mật thông tin

Generated `toString()` thể hiện **component names và values**, rất thuận tiện debug:

~~~java
record Request(String user, String token) {}
~~~

Nhưng nếu token là secret, logging `request.toString()` có thể làm lộ dữ liệu.

Giải pháp:
- Không đặt secrets trực tiếp trong kiểu dễ bị log nguyên object nếu không cần.
- Override `toString` để không in sensitive components.
- Không dựa riêng vào toString; thiết kế logging policy ở boundary.
- Với mutable secret arrays, còn phải giải quyết defensive copy và cleanup/lifecycle.

Cả record và class đều cần privacy-aware logging. Class mặc định không in mọi fields, nhưng nếu developer tự generate toString bằng IDE cũng có thể làm lộ secrets.

## 42. Chương trình chạy: tùy chỉnh `toString` để che dữ liệu

Tạo **`SafeToStringDemo.java`**:

~~~java
public class SafeToStringDemo {
    record Credentials(String user, String token) {
        Credentials {
            java.util.Objects.requireNonNull(user, "user");
            java.util.Objects.requireNonNull(token, "token");
        }

        @Override
        public String toString() {
            return "Credentials[user=" + user + ", token=<redacted>]";
        }
    }

    public static void main(String[] args) {
        Credentials credentials =
                new Credentials("mai", "secret-token");

        System.out.println(credentials);
        System.out.println("user=" + credentials.user());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SafeToStringDemo.java
java SafeToStringDemo
~~~

Stdout:

~~~text
Credentials[user=mai, token=<redacted>]
user=mai
~~~

Ví dụ chỉ giải quyết logging từ toString; accessor `token()` vẫn expose String token theo data-carrier API. Nếu cần mạnh hơn, thiết kế storage/ownership/lifecycle khác, thường là class chuyên trách hoặc secret wrapper.

## 43. Equality defaults: record và class khác nhau

**Record:**

~~~java
record Color(int r, int g, int b) {}
~~~

Hai Color objects cùng component values `equals` true. Hash codes tương ứng phải bằng nhau.

**Class không override:**

~~~java
class ColorClass {
    int r, g, b;

    ColorClass(int r, int g, int b) {
        this.r = r;
        this.g = g;
        this.b = b;
    }
}
~~~

Hai `new ColorClass(1,2,3)` khác nhau mặc định `equals` false vì `Object.equals` dùng reference equality.

Không nên cho rằng tất cả classes cần override equals. Entity/service identity object có thể chủ đích dùng reference equality.

## 44. Chương trình chạy: equality mặc định khác nhau

Tạo **`EqualityChoiceDemo.java`**:

~~~java
public class EqualityChoiceDemo {
    record ColorRecord(int r, int g, int b) {}

    static final class ColorClass {
        final int r, g, b;

        ColorClass(int r, int g, int b) {
            this.r = r;
            this.g = g;
            this.b = b;
        }
    }

    public static void main(String[] args) {
        ColorRecord ra = new ColorRecord(1, 2, 3);
        ColorRecord rb = new ColorRecord(1, 2, 3);

        ColorClass ca = new ColorClass(1, 2, 3);
        ColorClass cb = new ColorClass(1, 2, 3);

        System.out.println("record equal=" + ra.equals(rb));
        System.out.println("class equal=" + ca.equals(cb));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EqualityChoiceDemo.java
java EqualityChoiceDemo
~~~

Stdout:

~~~text
record equal=true
class equal=false
~~~

Nếu ColorClass là value object, phải tự thêm equals/hashCode. Nếu class biểu diễn một entity unique, reference identity có thể là một lựa chọn hợp lệ (tùy domain).

## 45. Hash-based collections đòi stable value semantics

Record là Map key tiện lợi nếu components:
- có immutable/hash-stable values;
- so sánh đúng với domain;
- không lộ mutable references làm hash đổi.

Ví dụ `record Key(String region, int number) {}` thường phù hợp.

Ngược lại, `record Key(List<String> tags) {}` lưu mutable List trực tiếp dễ phá HashMap lookup khi List thay đổi. Ordinary immutable class cũng sẽ gặp lỗi tương tự nếu equality/hash phụ thuộc mutable aliases.

**Hãy phòng vệ reference graph**: constructor copy, immutable elements, accessor policy và content equality nếu cần.

## 46. Chương trình chạy: record làm HashMap key

Tạo **`RecordHashMapDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RecordHashMapDemo {
    record Key(String region, int number) {}

    public static void main(String[] args) {
        Map<Key, String> lookup = new HashMap<>();
        lookup.put(new Key("VN", 1), "present");

        String found = lookup.get(new Key("VN", 1));
        System.out.println("found=" + found);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordHashMapDemo.java
java RecordHashMapDemo
~~~

Stdout:

~~~text
found=present
~~~

Generated equals/hashCode giúp record lookup theo value. Khi components mutable, không được dựa vào giả định record tự bảo vệ key.

## 47. Encapsulation: “getters” không phải quyết định duy nhất

Một class tốt không nhất thiết có getters cho mọi field. Ví dụ:

~~~java
final class Account {
    private int cents;

    void deposit(int amount) {
        // validate và cập nhật invariant
    }

    boolean canPay(int amount) {
        return amount >= 0 && amount <= cents;
    }
}
~~~

Một record `Account(int cents)` expose `cents()` và equality theo cents. Đó có thể là **khác contract** với object có identity và domain commands.

**Thiết kế hướng hành vi:** Khi người dùng object cần ra lệnh `pay`, `reserve`, `close` thay vì đọc/ghi arbitrary fields, class thường tự nhiên hơn.

### Nhưng record vẫn có thể che chi tiết phụ

Record có thể thêm derived methods và validate. Nó không bị giới hạn vào anemic DTO. Điều quan trọng là components thực sự mô tả logical state.

## 48. Lifecycle/resource objects nên ưu tiên class

Một resource thường cần:
- `open`/`close` hoặc `AutoCloseable`;
- trạng thái đóng/mở thay đổi;
- ownership của handles, buffers, sockets;
- cleanup khi có exception;
- concurrency coordination;
- idempotent shutdown.

Record fields final không dễ biểu đạt lifecycle state; không có arbitrary instance fields, và `equals` theo handle data có thể không đúng.

Ordinary class có thể implements AutoCloseable, giữ boolean closed, private resource fields và validate commands.

## 49. Chương trình chạy: lifecycle class thực hiện `AutoCloseable`

Tạo **`CloseableClassDemo.java`**:

~~~java
public class CloseableClassDemo {
    static final class Session implements AutoCloseable {
        private boolean closed;

        void use() {
            if (closed) {
                throw new IllegalStateException("closed");
            }
            System.out.println("using session");
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("closed");
        }
    }

    public static void main(String[] args) {
        try (Session session = new Session()) {
            session.use();
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 CloseableClassDemo.java
java CloseableClassDemo
~~~

Stdout:

~~~text
using session
closed
~~~

Session có trạng thái `closed` biến đổi và lifecycle; nó không phải một bộ components cần value equality. Đây là ví dụ hợp lý của class.

## 50. Concurrency và thread safety

Record component fields là final nhưng có thể tham chiếu mutable objects. Record chứa `List.copyOf` of Strings thường dễ share hơn record chứa một mutable map chưa copy, nhưng **keyword record không phải chứng nhận thread-safe**.

Ordinary class có thể immutable và thread-safe khi thiết kế đúng; cũng có thể mutable, lock-protected hoặc atomic.

Ví dụ:
- `record Config(String host, int port)` immutable-by-value → dễ publish.
- `record Config(Map<String,MutableValue> values)` → cần xem deep mutability.
- `class Counter` với AtomicInteger → có thể cung cấp thread-safe increments.
- `class Session` với lock/lifecycle → thiết kế synchronized ownership.

**Đừng chọn record chỉ vì hy vọng tự động tránh data race.**

## 51. Chương trình chạy: mutable class có atomic operation

Tạo **`AtomicClassDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicClassDemo {
    static final class Counter {
        private final AtomicInteger value = new AtomicInteger();

        int incrementAndGet() {
            return value.incrementAndGet();
        }

        int current() {
            return value.get();
        }
    }

    record CounterSnapshot(int value) {}

    public static void main(String[] args) {
        Counter counter = new Counter();

        counter.incrementAndGet();
        counter.incrementAndGet();

        CounterSnapshot snapshot =
                new CounterSnapshot(counter.current());

        System.out.println("current=" + counter.current());
        System.out.println("snapshot=" + snapshot.value());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 AtomicClassDemo.java
java AtomicClassDemo
~~~

Stdout:

~~~text
current=2
snapshot=2
~~~

Class sở hữu mutable atomic state; record biểu diễn snapshot. Counter và CounterSnapshot có trách nhiệm khác nhau.

## 52. Validation: record và class đều cần invariant

Record:

~~~java
record Port(int value) {
    Port {
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException("port");
        }
    }
}
~~~

Class:

~~~java
final class PortClass {
    private final int value;

    PortClass(int value) {
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException("port");
        }
        this.value = value;
    }

    int value() {
        return value;
    }
}
~~~

Cả hai bảo vệ range. Record dễ đọc hơn khi có một component là toàn bộ logical value.

### Khi class hợp lý hơn?

Khi public representation **không phải** number đơn thuần, mà là private efficient encoding, cache, derived states hoặc các operations chỉ nên expose những behaviors có ý nghĩa.

## 53. Chương trình chạy: record phân biệt parse lỗi và domain lỗi

Tạo **`RecordPortDemo.java`**:

~~~java
public class RecordPortDemo {
    record Port(int value) {
        Port {
            if (value < 1 || value > 65535) {
                throw new IllegalArgumentException("port range");
            }
        }

        static Port parse(String text) {
            return new Port(Integer.parseInt(text.strip()));
        }
    }

    public static void main(String[] args) {
        System.out.println("port=" + Port.parse(" 8080 ").value());

        try {
            Port.parse("70000");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordPortDemo.java
java RecordPortDemo
~~~

Stdout:

~~~text
port=8080
invalid=port range
~~~

Factory parsing là tiện ích hợp lệ, nhưng canonical constructor vẫn bảo vệ invariant để `new Port(70000)` không lọt qua.

## 54. Representation của dữ liệu “nhạy cảm” có nên dùng record?

Tùy policy. Record tự sinh accessors cho tất cả components và `toString()` thường hiện component values. Nếu chứa password, token, secret key hoặc personal data, phải review:
- ai có thể gọi accessor;
- logging/toString;
- retention của String hoặc arrays;
- equals/hashCode có vô tình so secrets không;
- có cần xóa/rotate/revoke/lifecycle không.

Ordinary class có thể expose **commands** như `verify(candidate)` thay vì expose raw secret. Với secrets nên dùng dedicated security abstractions và tránh nghĩ record hoặc class tự đảm bảo confidentiality.

Một record DTO nhận secrets trong thời gian ngắn không nhất thiết sai, nhưng phải có lifecycle/handling policy rõ.

## 55. Thêm component vào record có thể đổi equality

Ban đầu:

~~~java
record Product(String code, int price) {}
~~~

Hai objects `new Product("A",100)` đều equal.

Nếu nâng cấp thành:

~~~java
record Product(String code, int price, String currency) {}
~~~

generated equality xem cả currency. Đây là thay đổi **logical value semantics**, không chỉ thêm field cho đẹp.

Hãy cân nhắc:
- currency là một phần identity/value không?
- có migration/default hợp lý không?
- caller cũ khởi tạo thế nào?
- dữ liệu serialized/JSON có tương thích không?
- test và cache keys đã giả định equality trước đó ra sao?

Nếu public abstraction chỉ cần `priceInCents()` và currency conversion behavior, class có thể che giấu representation tốt hơn; nhưng cũng cần compatibility planning.

## 56. Refactor class sang record: checklist kỹ thuật

Một class có thể là candidate nếu:
1. final hoặc không cần subclassing.
2. instance state hoàn toàn mô tả bởi final components.
3. không có hidden mutable caches/resources/lock fields.
4. public contract chấp nhận expose component accessors.
5. equality theo component values là đúng.
6. constructor hình thành từ những component values.
7. validation/normalization đặt được trong canonical constructor.
8. component graph immutable hoặc defensive-copy đúng.
9. framework integration hỗ trợ record.
10. API/versioning impact chấp nhận được.

### Những gì dễ phải thay
- `getX()` → `x()` (nếu callers/frameworks quan tâm).
- Constructors/overloads.
- `equals/hashCode/toString` behavior.
- Reflection expectations.
- Serialization/deserialization binding.
- Visibility modifiers.
- Mutations/setters.
- Required extends superclass.

**Không refactor tự động khi behavior đổi** mà chưa có tests.

## 57. Chương trình chạy: ví dụ refactor class DTO sang record

Tạo **`RefactorDtoDemo.java`**:

~~~java
import java.util.Objects;

public class RefactorDtoDemo {
    static final class OldDto {
        private final String name;
        private final int score;

        OldDto(String name, int score) {
            this.name = Objects.requireNonNull(name);
            this.score = score;
        }

        String getName() {
            return name;
        }

        int getScore() {
            return score;
        }
    }

    record NewDto(String name, int score) {
        NewDto {
            Objects.requireNonNull(name);
        }
    }

    public static void main(String[] args) {
        OldDto old = new OldDto("Mai", 90);
        NewDto newer = new NewDto("Mai", 90);

        System.out.println(old.getName() + "=" + old.getScore());
        System.out.println(newer.name() + "=" + newer.score());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RefactorDtoDemo.java
java RefactorDtoDemo
~~~

Stdout:

~~~text
Mai=90
Mai=90
~~~

Output có thể tương đương, nhưng gọi getters đổi tên và equals/hashCode defaults thay đổi. Refactor chỉ hoàn tất khi public contract và tests được review.

## 58. Refactor record sang class: khi cần tiến hóa state

Giả sử ban đầu:

~~~java
record Download(int bytes) {}
~~~

Sau đó hệ thống yêu cầu:
- status lifecycle `QUEUED/RUNNING/DONE`;
- cancel;
- progress updates;
- listener registration;
- resource cleanup;
- synchronization.

Một `DownloadSession` class mới với private state thường hợp lý hơn việc nhồi toàn bộ state vào components, tạo record mới trên mỗi event và cố dùng nó làm resource owner.

Bạn có thể giữ record:

~~~java
record DownloadProgress(int completed, int total) {}
~~~

làm immutable snapshot được `DownloadSession.progress()` trả về. Đây là cách chia vai trò bền vững.

## 59. Chương trình chạy: stateful class trả progress record

Tạo **`DownloadProgressDemo.java`**:

~~~java
public class DownloadProgressDemo {
    record Progress(int completed, int total) {
        Progress {
            if (total < 0 || completed < 0 ||
                    completed > total) {
                throw new IllegalArgumentException("progress");
            }
        }
    }

    static final class Download {
        private final int total;
        private int completed;

        Download(int total) {
            if (total < 0) {
                throw new IllegalArgumentException("total");
            }
            this.total = total;
        }

        void advance(int bytes) {
            if (bytes < 0 || bytes > total - completed) {
                throw new IllegalArgumentException("bytes");
            }
            completed += bytes;
        }

        Progress progress() {
            return new Progress(completed, total);
        }
    }

    public static void main(String[] args) {
        Download download = new Download(100);

        Progress before = download.progress();
        download.advance(25);
        Progress after = download.progress();

        System.out.println(before);
        System.out.println(after);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DownloadProgressDemo.java
java DownloadProgressDemo
~~~

Stdout:

~~~text
Progress[completed=0, total=100]
Progress[completed=25, total=100]
~~~

Download là lifecycle-bearing class; Progress là value snapshot. Nếu nhiều threads update/download đồng thời, cần synchronization policy ngoài minh họa này.

## 60. Frameworks và reflection: record metadata là rõ ràng

Reflection cung cấp:
- `Class.isRecord()` để nhận diện declaring record type.
- `Class.getRecordComponents()` để lấy component descriptors.
- component names, types và accessors theo record metadata.

Một ordinary class có fields/getters/constructors nhưng không có cùng record structural contract.

### Khi cần reflection-based binding

Record metadata có thể hữu ích cho mapper và schema generation **nếu thư viện hỗ trợ đúng**. Tuy nhiên việc reflection có metadata không có nghĩa arbitrary framework có record constructor binding tự động. Kiểm tra thực tế.

## 61. Chương trình chạy: reflection cho record và class

Tạo **`RecordReflectionDemo.java`**:

~~~java
public class RecordReflectionDemo {
    record Person(String name, int age) {}

    static final class PersonClass {
        private final String name;
        private final int age;

        PersonClass(String name, int age) {
            this.name = name;
            this.age = age;
        }
    }

    public static void main(String[] args) {
        System.out.println("record=" + Person.class.isRecord());
        System.out.println("class=" + PersonClass.class.isRecord());

        for (java.lang.reflect.RecordComponent component
                : Person.class.getRecordComponents()) {
            System.out.println(component.getName() + ":" +
                    component.getType().getSimpleName());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordReflectionDemo.java
java RecordReflectionDemo
~~~

Stdout:

~~~text
record=true
class=false
name=String
age=int
~~~

Reflection xác nhận structural record components; `PersonClass` không trở thành record dù có cùng logical fields.

## 62. Records không nhất thiết nhanh hoặc nhỏ hơn classes

Không có guarantee Java specification rằng mọi record:
- chiếm ít heap memory hơn equivalent class;
- được stack allocate;
- được JVM intern;
- không cần garbage collection;
- có constructors nhanh hơn;
- có equals nhanh hơn custom class;
- được pass-by-value thay vì reference.

Records vẫn là reference objects. JVM JIT/inlining/escape analysis có thể tối ưu nhiều dạng code, bao gồm cả ordinary classes.

**Chọn theo correctness và API trước; profile bằng JFR/JMH/benchmarks nếu performance là vấn đề thực tế.**

Một record với List.copyOf hoặc deep-copy arrays có thể tốn allocations hơn class mutable cố ý share references — nhưng bảo vệ state có giá trị và phải so theo requirements tương đương, không chỉ syntax.

## 63. Dùng record cho event payloads khi data hoàn chỉnh

Một event payload thường thích hợp nếu:
- mô tả **sự kiện đã xảy ra** chứ không phải một service sống;
- components là immutable values hoặc immutable snapshots;
- không cần identity ngoại trừ event ID thuộc dữ liệu;
- publish/consume theo contract rõ;
- event schema được version khi thay đổi.

Ví dụ:

~~~java
record OrderPlaced(
        long orderId,
        java.time.Instant occurredAt,
        int totalCents) {}
~~~

`Instant` immutable, primitive values dễ serialize/bảo vệ. Record là ứng viên tự nhiên cho read-only data snapshot.

Nếu có long-lived consumer offset, retry tracker và connection lifecycle, những đối tượng đó thường là class/services tách khỏi event payload.

## 64. Chương trình chạy: immutable event data và consumer interface

Tạo **`EventRecordDemo.java`**:

~~~java
import java.time.Instant;

public class EventRecordDemo {
    record OrderPlaced(
            long orderId,
            Instant occurredAt,
            int totalCents) {
        OrderPlaced {
            if (orderId <= 0 || totalCents < 0) {
                throw new IllegalArgumentException("event");
            }
            java.util.Objects.requireNonNull(
                    occurredAt, "occurredAt");
        }
    }

    interface EventConsumer {
        void accept(OrderPlaced event);
    }

    public static void main(String[] args) {
        OrderPlaced event = new OrderPlaced(
                7L, Instant.parse("2026-10-18T00:00:00Z"), 1250);

        EventConsumer consumer = value ->
                System.out.println(
                        value.orderId() + ":" + value.totalCents());

        consumer.accept(event);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EventRecordDemo.java
java EventRecordDemo
~~~

Stdout:

~~~text
7:1250
~~~

Event data không chứa một event processing queue, database transaction hoặc mutable connection handle. Các hành vi đó thuộc services/classes riêng.

## 65. Tiêu chí “ít code hơn” nên đứng sau semantics

Sai lầm:

> “Nếu class có ba private final fields thì chuyển hết sang record.”

Phân tích đúng:

- Những fields có phải toàn bộ logical state được muốn expose không?
- Có equality theo tất cả fields không?
- Có hidden representations/caches không?
- Constructor parameters có được document ổn định không?
- Frameworks/serialization có cần JavaBeans semantics không?
- Security/logging có cho phép toString chứa mọi component không?
- Đời sống object là snapshot hay entity?
- Có cần subclassing hoặc private mutable state không?
- Thay đổi component có phá API không?

Một record dài hơn class vẫn có thể đúng, và class dài hơn record vẫn có thể đáng giá.

## 66. Bảng lựa chọn theo ví dụ

| Use case | Gợi ý | Lý do |
| --- | --- | --- |
| `Point(x,y)` | Record | Components mô tả giá trị |
| `DateRange(start,end)` | Record | Cross-field invariant, java.time immutable |
| `CurrencyAmount(currency,amount)` | Record hoặc immutable class | Giá trị; xét normalization/representation |
| `HTTP response DTO` | Record nếu mapper hỗ trợ | Transparent data transport |
| `SearchResult(title,url)` | Record | Snapshot data |
| `Customer entity` | Class | Identity, rename/lifecycle |
| `BankAccount` | Class | Transactions và state mutations |
| `Session`/`Connection` | Class | Resource ownership/close |
| `DownloadProgress` | Record | Snapshot |
| `DownloadSession` | Class | Long-lived state and commands |
| `PolicyConfig` | Record với immutable components | Input values ổn định |
| `PolicyEngine` | Class/service | Behavior và dependencies |
| `Secret credential holder` | Cân nhắc class | Access/lifecycle/logging |
| `ByteBlob(byte[])` | Tùy contract | Defensive copy + equality; class có thể che representation |
| `Value object extensible via superclass` | Class | Record không extends class |
| `Sealed Result variants` | Records | Data variants của sealed interface |
| `Plugin implementation` | Class | Constructor/DI/lifecycle |
| `JPA-style managed entity` | Thường class | ORM requirements |
| `Read-only query projection` | Record nếu hỗ trợ | Dữ liệu đọc |
| `Mutable cache` | Class | Hidden mutable state |

## 67. Decision flow theo thứ tự đúng

~~~text
Định nghĩa kiểu mới
    |
    +-- Kiểu đại diện entity/resource có identity/lifecycle?
    |       |
    |       +-- Có --> Ordinary class.
    |
    +-- Cần extends một superclass tùy ý?
    |       |
    |       +-- Có --> Ordinary class.
    |
    +-- Cần hidden mutable instance fields/cache/lock?
    |       |
    |       +-- Có --> Ordinary class.
    |
    +-- State logic được mô tả đầy đủ bởi public components?
    |       |
    |       +-- Không --> Ordinary class hoặc abstraction khác.
    |
    +-- Equality theo components là đúng?
    |       |
    |       +-- Không --> Class hoặc custom semantics có lý do rõ.
    |
    +-- Components mutable có thể bảo vệ/snapshot hợp lý?
    |       |
    |       +-- Không --> Class/representation khác.
    |
    +-- Framework/API compatibility cho phép?
            |
            +-- Không --> Class hoặc adapter DTO.
            |
            +-- Có --> Record thường là lựa chọn phù hợp.
~~~

Không phải heuristic không ngoại lệ. Ví dụ record có thể custom equals/hashCode hoặc dùng array với clone, nhưng đó là **tín hiệu cần review value semantics kỹ hơn**, không phải bằng chứng record sai.

## 68. Anti-patterns thường gặp

| Anti-pattern | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Biến mọi DTO thành record vô điều kiện | Mapper/API compatibility có thể khác | Xác minh integration contract |
| Dùng record làm mutable entity | Fields final, identity/equality không phù hợp | Class entity + record snapshot |
| Dùng `record User(id,name)` rồi coi equals chỉ theo id | Generated equals dùng cả components | Chọn class/thiết kế semantics |
| Nghĩ record deep immutable | Mutable reference components vẫn đổi | Copy/immutable elements |
| Nhét `ArrayList` trực tiếp vào record | Aliasing, hash thay đổi | List.copyOf và validation |
| Getter trả array nội bộ | External mutation | Defensive copy |
| Array clone nhưng không xem equals | Identity vs content equality | Arrays.equals/hashCode hoặc class |
| Dùng record chứa secret rồi log object | toString lộ component values | Logging/data policy |
| Dùng class chỉ vì cần vài methods | Record cũng có instance methods | Xét logical state |
| Cố dùng record extends BaseClass | Không hợp lệ | Interface/composition/class |
| Chọn class mutable cho mọi value | Boilerplate và state bugs | Record/immutable class |
| Chọn theo benchmark tưởng tượng | Không có performance guarantee | Đo thực tế |
| Đổi component name không xét clients | API break | Version/migration strategy |
| Dùng record theo framework chưa hỗ trợ | Deserialization/proxy fail | Kiểm tra version/contract |
| Coi `@NotNull` tự validate mọi `new` | Annotation không tự chạy | Constructor/framework validation |
| Cho business logic phụ thuộc generated toString | Không phải durable serialization schema | Explicit formatting/schema |
| Class với public setters cho value object | Invariant dễ bị phá | Immutable class/record |
| Không kiểm tra concurrency của captured data | Thread safety không tự đến | Synchronization/ownership |

## 69. Bài tập 1 — Điểm tọa độ

Một kiểu chỉ giữ `x`, `y` integers, không identity riêng, equality theo cả hai và có method `distanceSquared`.

**Đáp án:** Record rất phù hợp. Method tính derived value có thể đặt trong record. Dùng `long` hoặc tính toán có kiểm tra overflow khi giá trị lớn nếu domain yêu cầu.

## 70. Bài tập 2 — Tài khoản ngân hàng

Một account có ID bất biến, balance thay đổi, deposit/withdraw commands và transaction history. Hai accounts có same balance không phải same entity.

**Đáp án:** Ordinary class entity rõ hơn. Record có thể thể hiện `AccountSnapshot(id,balance)` hoặc transaction event immutable.

## 71. Bài tập 3 — Record chứa List

~~~java
record Report(java.util.List<String> tags) {}
~~~

Caller truyền ArrayList rồi mutate source. Report có thay đổi không?

**Đáp án:** Có thể, vì record mặc định giữ reference. Thêm compact constructor `tags = List.copyOf(tags);` nếu cần unmodifiable structural snapshot, rồi xét mutable elements.

## 72. Bài tập 4 — Record chứa array

~~~java
record Data(byte[] values) {}
~~~

Có ba rủi ro nổi bật nào?

**Đáp án:** Mutation qua input alias; mutation qua default accessor; generated equals/hashCode không element-wise theo array content. Copy input/output và định nghĩa equality theo domain nếu cần.

## 73. Bài tập 5 — Thêm hidden cache

Một value object muốn thêm private mutable per-instance lazy cache không nằm trong component list.

**Đáp án:** Record không cho thêm arbitrary instance fields. Dùng ordinary class, external cache hoặc tính toán không cache; cân nhắc concurrency nếu state mutable.

## 74. Bài tập 6 — Kế thừa

Một type phải `extends AbstractService` đã có logic/fields và implements `Runnable`.

**Đáp án:** Ordinary class, vì record không extends custom superclass. Record chỉ implicitly extends java.lang.Record và có thể implements interfaces.

## 75. Bài tập 7 — Equality

Hai `new PersonRecord("Mai",20)` có same components; hai `new PersonClass("Mai",20)` mà class không override equals.

**Đáp án:** Hai records equals true; hai classes dùng Object.equals nên false nếu là two distinct references. Cần custom equals/hashCode để class có value semantics.

## 76. Bài tập 8 — API thay đổi

Public record `Point(x,y)` cần thêm component `unit`. Rủi ro?

**Đáp án:** Canonical constructor, accessors, equals/hashCode/toString shape và serialization/mapping schema có thể thay đổi. Version/migration/overloads cần được kiểm tra; đừng xem như chỉ thêm private field.

## 77. Bài tập 9 — Immutable class vs record

Một ordinary final class có private final fields, defensive copies và custom equals. Có thể immutable như record không?

**Đáp án:** Có, thậm chí có thể encapsulate representation kỹ hơn. Record là lựa chọn syntax/structural contract chứ không độc quyền immutability.

## 78. Bài tập 10 — Sealed interface result

Có `sealed interface Result permits Success, Failure`; Success chỉ mang data, Failure chỉ mang error message.

**Đáp án:** Hai final records implements Result thường phù hợp trong Java 17. Nếu một variant quản lý resource lifecycle, ordinary class cũng có thể là permitted implementation theo rules.

## 79. Bài tập 11 — Framework projection

Một SQL query trả read-only columns và library mapper hỗ trợ constructor mapping cho records, không cần managed entity.

**Đáp án:** Record DTO/projection có thể tốt. Nếu phải là managed JPA-style entity theo requirements cụ thể, class thường phù hợp hơn; cần kiểm tra framework documentation.

## 80. Bài tập 12 — Chọn theo performance?

Có người bảo “record luôn rẻ hơn class và JVM đưa lên stack”.

**Đáp án:** Không có language guarantee đó. Records là reference objects; JIT optimization phụ thuộc runtime/workload. Chọn theo semantics và benchmark khi cần.

## 81. Bài tập 13 — Resource với `close()`

Một file writer cần đóng file, theo dõi closed state và ngăn write sau khi close.

**Đáp án:** Ordinary class implements AutoCloseable phù hợp hơn, vì cần lifecycle/hidden mutable state; có thể dùng record làm immutable write request parameters.

## 82. Bài tập 14 — Có logic thì không được dùng record?

Một `record Rectangle(width,height)` có `area()` và `isSquare()`.

**Đáp án:** Hoàn toàn hợp lệ. Methods derived từ components không phá value-carrier design.

## 83. Bài tập 15 — Data privacy

Một record chứa `password` trong component và bị log bằng `toString()`. Vấn đề gì?

**Đáp án:** Generated toString có thể phơi component value. Thiết kế lại security boundary/logging; override toString chỉ là một lớp phòng vệ, không đảm bảo toàn bộ secret ownership.

## 84. Bài tập 16 — Record hoặc class cho thông tin cấu hình?

Một cấu hình gồm `host` và `port`, tạo xong không đổi, cần validation và equality theo hai components.

**Đáp án:** Record thích hợp, có canonical constructor kiểm tra nonblank host/range port. Nếu config giữ live mutable connections/cache, tách `ConnectionManager` thành class.

## 85. Bài tập 17 — Domain snapshot vs same entity

Một `Customer` class đổi tên từ "Mai" sang "Mai Anh". Hai snapshots trước và sau bằng nhau không?

**Đáp án:** Không nếu record snapshot có components `(id,name)`; generated equals so cả name. Nhưng cả hai có thể trỏ tới cùng domain entity ID, nên snapshot value identity khác entity identity.

## 86. Bài tập 18 — Từ class sang record có bảo toàn hành vi?

Class `Person` có default Object.equals và getters `getName()`. Chuyển trực tiếp sang `record Person(String name)`.

**Đáp án:** Không tự bảo toàn contract: equality đổi sang component value, getter name đổi, constructor/API/serialization có thể khác. Cần compatibility strategy và tests.

## 87. Quy trình review kiến trúc

Trước khi chọn, trả lời lần lượt:

1. **Đây là value hay entity?** Viết một câu mô tả identity/equality.
2. **State đã gồm những gì?** Components có biểu diễn đầy đủ logical state không?
3. **Mutation có hợp lệ không?** Nếu có, mutate chính object hay tạo value mới?
4. **Có hidden state không?** Cache, lock, connection, audit fields, lifecycle?
5. **Cần inheritance không?** Extends class hay chỉ implements interfaces?
6. **Public API là gì?** Expose record components có đúng mong muốn không?
7. **Có mutable references không?** Defensive copies, nested objects, arrays?
8. **Equality/hash có ổn định không?** Map/Set keys có dùng không?
9. **Security/logging?** Accessors/toString có lộ dữ liệu không?
10. **Framework mapping?** No-arg constructor, getters, reflection, proxies?
11. **Versioning?** Thêm component ảnh hưởng clients/schema thế nào?
12. **Concurrency?** Có shared state hoặc atomic operations không?
13. **Performance?** Chỉ profile sau khi requirements đúng.
14. **Tests?** So behavior, equality, mutation, invariants, compatibility.

**Kết quả quyết định:** Nếu là một bộ giá trị minh bạch, ổn định, components đúng logical state, chọn record. Nếu object quản lý identity/lifecycle/representation hoặc cần extensibility/state phức tạp, chọn class.

## 88. Checklist cuối bài

- [ ] Tôi biết record và class đều là Java reference types.
- [ ] Tôi hiểu record tự sinh accessors/canonical constructor/equals/hashCode/toString.
- [ ] Tôi không nhầm record final fields với deep immutability.
- [ ] Tôi biết record implicitly final và extends java.lang.Record.
- [ ] Tôi biết record không extends custom superclass.
- [ ] Tôi biết record vẫn implements interfaces được.
- [ ] Tôi biết record có thể có methods và static members.
- [ ] Tôi biết record không có arbitrary instance fields hoặc instance initializer.
- [ ] Tôi hiểu compact/canonical constructors và validation.
- [ ] Tôi biết class immutable có thể có value equality như record.
- [ ] Tôi biết class default Object.equals là reference-based.
- [ ] Tôi tách snapshot value khỏi entity identity.
- [ ] Tôi cân nhắc Record DTO cho immutable data transfer.
- [ ] Tôi dùng class khi có mutable domain commands.
- [ ] Tôi dùng class cho resource/lifecycle/AutoCloseable owners.
- [ ] Tôi không dùng record tự động thay mọi ORM entity.
- [ ] Tôi kiểm tra mapper/framework record support.
- [ ] Tôi hiểu record component accessor `name()` khác `getName()`.
- [ ] Tôi hiểu component changes ảnh hưởng constructor/API/equality.
- [ ] Tôi biết List.copyOf chỉ là structural snapshot, không deep-copy elements.
- [ ] Tôi biết arrays cần defensive copy và xem lại equals/hashCode.
- [ ] Tôi không dùng mutable value objects làm unstable HashMap keys.
- [ ] Tôi biết record `toString` có thể lộ sensitive components.
- [ ] Tôi biết records là reference objects, không guaranteed stack-only.
- [ ] Tôi không cho rằng record luôn nhanh hơn class.
- [ ] Tôi cân nhắc sealed interface + record variants trong Java 17.
- [ ] Tôi phân biệt local record implicitly static với ordinary local class.
- [ ] Tôi xét Java serialization và external schema riêng.
- [ ] Tôi test type behavior chứ không chỉ số dòng.
- [ ] Tôi có decision flow trước khi refactor class ↔ record.
- [ ] Tôi chọn dựa trên semantics, API stability và lifecycle.

**Kết luận:** Hãy chọn **`record` khi các components công khai thực sự là toàn bộ giá trị logic của đối tượng**, equality theo components là đúng, và mutation/lifecycle phức tạp không nằm trong contract. Chọn **ordinary class khi cần identity, state transitions, che giấu representation, constructors/API không phụ thuộc trực tiếp vào components, kế thừa, caches hoặc resources**. Không phải chọn một cho toàn chương trình: kiến trúc Java 17 thường mạnh nhất khi **class quản lý hành vi và vòng đời, record truyền immutable snapshots/value data, interface định nghĩa hợp đồng chung**. Việc code ngắn hơn là lợi ích phụ, không phải tiêu chí quyết định.
