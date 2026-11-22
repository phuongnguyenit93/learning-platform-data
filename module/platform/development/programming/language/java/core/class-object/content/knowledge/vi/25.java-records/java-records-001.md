# Record để biểu diễn một nhóm giá trị có tên trong Java

## Mục tiêu học tập

Sau bài học này, bạn sẽ có thể:

- Hiểu **record** trong Java 17 là một dạng class để biểu diễn **một nhóm giá trị được xác định bằng các thành phần có tên và kiểu** (*record components*).
- Giải thích vì sao `record Point(int x, int y)` giúp diễn đạt ý nghĩa tốt hơn một cặp giá trị ẩn danh hoặc một `Object[]`.
- Đọc và khai báo record header, record body, constructor, component accessors, methods, interfaces và record generic.
- Sử dụng các thành viên do Java tạo: canonical constructor, các private final component fields, public accessors, `equals`, `hashCode`, `toString`.
- Phân biệt **object identity (`==`)** và **component-based value equality (`equals`)**; biết cách dùng records làm keys/values khi components đủ ổn định.
- Đảm bảo invariant bằng **compact canonical constructor** hoặc normal canonical constructor, chuẩn hóa dữ liệu trước khi ghi vào record components.
- Hiểu record **shallow immutable về component references**, không mặc nhiên immutable sâu: component kiểu array, mutable list hay mutable object vẫn có thể thay đổi sau construction.
- Biết cách dùng `List.copyOf`, defensive copies và immutable domain components khi cần một snapshot an toàn, đồng thời nhận biết các giới hạn của shallow copies.
- Áp dụng record cho kết quả tính toán, tọa độ, khoảng thời gian, khóa tìm kiếm, kết quả parse, DTO nội bộ và trạng thái phiên bản.
- Phân biệt record với normal class, mutable entity, enum, generic pair, map, array và anonymous/local classes để chọn kiểu phù hợp.
- Biết các ràng buộc: record ngầm `final`, extends `java.lang.Record`, không tự khai thêm instance fields hay instance initializer, nhưng có thể có instance methods, static members và implement interfaces.
- Tự biên dịch/chạy ví dụ Java 17+ có stdout rõ ràng và hoàn thành bài tập kiểm tra hiểu biết.

> **Phiên bản:** Record chính thức là tính năng chuẩn từ Java 16 (JEP 395); trong Java 17 không cần `--enable-preview` để dùng record. Ví dụ độc lập trong tài liệu này có file/class name trùng khớp với lệnh `javac`/`java`. Những code fragments không phải chương trình chạy riêng sẽ được ghi rõ.

## 1. Nhóm giá trị có tên là gì?

Khi mô tả một tọa độ, ta thường cần hai số nguyên:

~~~java
int x = 4;
int y = 7;
~~~

Điều này dễ hiểu trong một method ngắn, nhưng nếu cần **truyền cả hai giá trị qua một API**, người lập trình có thể nghĩ tới array:

~~~java
int[] point = {4, 7};
~~~

Vấn đề: `point[0]` là x hay y? Ai đảm bảo array có đúng hai phần tử? Nếu caller đổi `point[0]` thì mọi nơi giữ cùng array quan sát được thay đổi.

Java record cho phép **đặt tên cho nhóm giá trị**:

~~~java
record Point(int x, int y) {
}
~~~

Bây giờ có thể viết:

~~~java
Point p = new Point(4, 7);
int horizontal = p.x();
int vertical = p.y();
~~~

`p.x()` và `p.y()` thể hiện ý nghĩa rõ hơn `point[0]` và `point[1]`. Compiler bảo đảm khi tạo `new Point(...)` phải cung cấp giá trị thích hợp cho từng component theo đúng kiểu và thứ tự.

**Tư duy quan trọng:** record là một **data carrier có danh tính kiểu**, không phải một array/list có độ dài tùy ý. Nó diễn đạt rằng **nhóm các giá trị ấy thuộc cùng một khái niệm trong domain**.

## 2. Cấu trúc một record declaration

~~~java
record Person(String name, int age) {
}
~~~

Phân tích:

| Cú pháp | Vai trò |
| --- | --- |
| `record` | Khai báo một **record class** |
| `Person` | Tên kiểu |
| `String name` | Component `name` kiểu String |
| `int age` | Component `age` kiểu int |
| `(String name, int age)` | **Record header**, danh sách components có thứ tự |
| `{ }` | Record body, có thể trống hoặc chứa constructors/methods/members hợp lệ |

Đối với record body rỗng, Java cung cấp:

- Một private final field cho mỗi component.
- Một accessor `name()` trả String, `age()` trả int (thông thường đều public).
- Một canonical constructor có parameters tương ứng components theo **đúng thứ tự header**.
- `equals(Object)`, `hashCode()`, `toString()` dựa trên record components.

Do đó:

~~~java
Person p = new Person("Lan", 20);
System.out.println(p.name());
System.out.println(p.age());
System.out.println(p);
~~~

sẽ có ý nghĩa xác định mà ta không cần viết boilerplate getter, field assignment và Object methods. Đây chỉ là snippet, chưa có enclosing `main`.

### 2.1. “Component” khác field khai báo thủ công

Khi khai `record Person(String name, int age)`, bạn đã khai **state description** trong record header. Không khai thêm:

~~~java
// private String name; // Không được tự thêm instance field này.
~~~

Các backing fields do compiler sinh ra được giữ private final. Bạn viết thêm methods, constructors hợp lệ, hoặc static members khi cần — chứ không khai trùng component fields.

## 3. Chương trình mở đầu: record Point có tên cho mỗi giá trị

Lưu **`RecordPointDemo.java`**:

~~~java
public class RecordPointDemo {
    record Point(int x, int y) {
    }

    public static void main(String[] args) {
        Point start = new Point(4, 7);
        Point end = new Point(10, 3);

        System.out.println("start=" + start);
        System.out.println("x=" + start.x());
        System.out.println("y=" + start.y());
        System.out.println("end=" + end);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RecordPointDemo.java
java RecordPointDemo
~~~

**Stdout (JDK 17):**

~~~text
start=Point[x=4, y=7]
x=4
y=7
end=Point[x=10, y=3]
~~~

Ghi nhớ:

1. `Point` được khai như một **member record** trong class demo, nên dùng `new Point(...)` từ `main`.
2. Component accessors tên `x()`/`y()`, **không phải** `getX()`/`getY()` trừ khi bạn tự thêm methods đó.
3. Dòng `start=Point[x=4, y=7]` đến từ generated `toString()` của record.
4. Hai Point objects là những instances độc lập, nhưng cùng kiểu Point và cùng quy tắc value equality.

## 4. Vì sao “nhóm giá trị có tên” có lợi hơn `Object[]`, `Map` hay generic Pair?

Hãy so sánh ba mô hình:

~~~java
Object[] request = {"Lan", 20};
java.util.Map<String, Object> data =
        java.util.Map.of("name", "Lan", "age", 20);
record Person(String name, int age) { }
Person person = new Person("Lan", 20);
~~~

Đây là fragment hợp lệ nếu nằm trong một method/block thích hợp.

### 4.1. Array

- Theo `Object[]`, compiler không biết phần tử thứ 0 đại diện name.
- Caller có thể truyền thiếu/thừa phần tử, nhầm vị trí, hoặc sai kiểu và chỉ gặp lỗi muộn.
- Các phần tử array có thể được gán lại.
- `Object[]` không tự mang tên domain `Person`.

### 4.2. Map

- Map hữu ích khi **tập keys thay đổi động**.
- Nhưng với cấu trúc cố định hai fields, string keys `"name"`/`"age"` có thể bị viết sai; values kiểu Object cần cast/validation.
- `Map.of` không cho mutate map structure, nhưng không tự biến mọi nested objects thành immutable.
- Map có thể không thể hiện “đây là một Person” rõ bằng một Java type chuyên biệt.

### 4.3. Generic Pair

Một `Pair<String,Integer>` diễn đạt **hai thứ đi cùng**, nhưng `first()/second()` hay `left()/right()` ít nghĩa hơn `name()/age()`. Record `Person` làm mô hình dữ liệu dễ tự giải thích hơn.

**Quy tắc:** Khi nhóm giá trị có **ý nghĩa nghiệp vụ ổn định và các component biết trước**, dùng record có tên cụ thể thay vì lạm dụng array/map/pair. Map vẫn tốt cho metadata động và Pair có thể hợp lý trong thuật toán cục bộ.

## 5. Chương trình: một tên kiểu ngăn truyền nhầm hai nhóm dữ liệu

Lưu **`NamedRecordTypesDemo.java`**:

~~~java
public class NamedRecordTypesDemo {
    record Coordinate(int x, int y) {
    }

    record Size(int width, int height) {
    }

    static String describe(Coordinate point, Size size) {
        return "point=" + point.x() + "," + point.y()
                + "; size=" + size.width() + "x" + size.height();
    }

    public static void main(String[] args) {
        Coordinate where = new Coordinate(2, 5);
        Size dimension = new Size(640, 480);

        System.out.println(describe(where, dimension));

        // describe(dimension, where); // Compile-time type mismatch.
    }
}
~~~

Chạy:

~~~bash
javac NamedRecordTypesDemo.java
java NamedRecordTypesDemo
~~~

Output:

~~~text
point=2,5; size=640x480
~~~

Dù `Coordinate` và `Size` đều giữ hai số nguyên, Java xem chúng là **hai kiểu khác nhau**. Compiler có thể phát hiện lời gọi method bị đảo hai loại dữ liệu, điều mà `int[]` hoặc một generic pair chung có thể khó giúp ta làm rõ.

## 6. Canonical constructor biểu diễn đầy đủ record state

Với:

~~~java
record Temperature(String unit, double value) {
}
~~~

Java tạo một canonical constructor tương ứng `Temperature(String unit, double value)`. Record header **quy định danh sách parameters và thứ tự**.

~~~java
Temperature sample = new Temperature("C", 24.5);
~~~

Không được hoán đổi arguments một cách tùy tiện. Java compile-time type checking kiểm tra types, nhưng nếu hai components cùng kiểu (như `record Period(int start,int end)`), việc đảo thứ tự vẫn có thể compile và gây bug nghiệp vụ.

### 6.1. Constructor được sinh không tự kiểm tra domain rules

`new Temperature(null, Double.NaN)` có thể hợp lệ về type trong một record body rỗng. Record không tự kết luận giá trị nào “đúng nghiệp vụ”. Nếu cần invariant, khai constructor để validate và normalize.

### 6.2. Compact canonical constructor

~~~java
record Name(String value) {
    Name {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value");
        }
        value = value.strip();
    }
}
~~~

`Name { ... }` là **compact constructor**: không viết lại parameter list, dùng parameter names của record header. Java thực hiện gán normalized parameter values vào component fields **sau body compact constructor** theo rules JLS.

Ví dụ kiểm tra input: blank → exception; `" Lan "` → `"Lan"`.

## 7. Chương trình: nhóm dữ liệu có invariant

Lưu **`RecordValidationDemo.java`**:

~~~java
import java.util.Objects;

public class RecordValidationDemo {
    record User(String username, int age) {
        User {
            Objects.requireNonNull(username, "username");
            username = username.strip();

            if (username.isEmpty()) {
                throw new IllegalArgumentException("empty username");
            }
            if (age < 0 || age > 150) {
                throw new IllegalArgumentException("invalid age");
            }
        }
    }

    public static void main(String[] args) {
        User user = new User("  Lan  ", 20);

        System.out.println("user=" + user);
        System.out.println("username=" + user.username());

        try {
            new User("  ", 20);
        } catch (IllegalArgumentException expected) {
            System.out.println("blank username rejected");
        }

        try {
            new User("Minh", -1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid age rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac RecordValidationDemo.java
java RecordValidationDemo
~~~

Output:

~~~text
user=User[username=Lan, age=20]
username=Lan
blank username rejected
invalid age rejected
~~~

Cách xử lý này làm record object hợp lệ ngay sau khi constructor hoàn thành. Nếu constructor ném exception thì creation expression **không trả** một User instance hoàn chỉnh cho caller.

**Quan trọng:** `Objects.requireNonNull` có thể ném `NullPointerException`; trong ví dụ chỉ catch hai trường hợp `IllegalArgumentException` khác. Đừng giả định null và blank cho cùng một exception type trừ khi API hợp nhất chính sách rõ ràng.

## 8. Normal canonical constructor và khác biệt với compact form

Có thể viết constructor canonical đầy đủ:

~~~java
record Range(int start, int end) {
    Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
        this.start = start;
        this.end = end;
    }
}
~~~

Trong **normal canonical constructor** bạn ghi rõ parameters và phải khởi tạo mỗi component field đúng quy tắc. Trong **compact constructor**, Java tự gán field từ parameters sau body; không viết `this.start = start` trong compact body.

Không khai đồng thời hai canonical constructors trùng signature cho một record. Chọn dạng ngắn khi việc validation/normalization gọn, còn normal canonical nếu cần logic đặc biệt có căn cứ.

### 8.1. Đừng để validation nằm ở getter

Nếu record nhận `Range(10,5)` rồi chỉ kiểm tra lúc gọi `length()`, một object không hợp lệ đã có thể đi vào collections, logs và các lớp khác. Đặt invariant của **chính nhóm dữ liệu** ngay ở constructor thường đúng hơn.

## 9. Chương trình: record cho khoảng giá trị

Lưu **`RecordRangeDemo.java`**:

~~~java
public class RecordRangeDemo {
    record Range(int start, int end) {
        Range {
            if (start > end) {
                throw new IllegalArgumentException("start > end");
            }
        }

        boolean contains(int value) {
            return value >= start && value <= end;
        }

        long length() {
            return (long) end - start + 1L;
        }
    }

    public static void main(String[] args) {
        Range range = new Range(3, 8);

        System.out.println("range=" + range);
        System.out.println("contains 5=" + range.contains(5));
        System.out.println("contains 10=" + range.contains(10));
        System.out.println("length=" + range.length());

        try {
            new Range(10, 2);
        } catch (IllegalArgumentException expected) {
            System.out.println("reversed range rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac RecordRangeDemo.java
java RecordRangeDemo
~~~

Output:

~~~text
range=Range[start=3, end=8]
contains 5=true
contains 10=false
length=6
reversed range rejected
~~~

Cast sang `long` **trước** phép trừ giúp tránh overflow trung gian của hai số nguyên int. Đây là ví dụ domain-specific instance methods dựa trên components, không cần thêm instance fields.

## 10. Generated accessors khác JavaBeans getters

Với `record Book(String title, int pages)`:

~~~java
Book book = new Book("Java", 300);
String title = book.title();
int pages = book.pages();
~~~

Compiler tạo public methods đúng **tên component**: `title()`, `pages()`. Nó không tự tạo `getTitle()`, `getPages()` hay `setTitle()`.

Nếu bạn cần tích hợp với một framework yêu cầu JavaBeans getters, hãy kiểm tra framework có hỗ trợ records hay thêm adapter/accessor method riêng nếu hợp lý. Đừng khai setter để biến component field final thành mutable.

### 10.1. Có thể tự khai method với tên khác

~~~java
record Book(String title, int pages) {
    boolean longBook() {
        return pages > 500;
    }

    String label() {
        return title + " (" + pages + " pages)";
    }
}
~~~

Record không bị hạn chế chỉ có field accessors. Nó có thể chứa các **derived methods** không thay đổi component values.

## 11. Chương trình: hành vi tính được từ record components

Lưu **`RecordDerivedMethodsDemo.java`**:

~~~java
public class RecordDerivedMethodsDemo {
    record Rectangle(int width, int height) {
        Rectangle {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("negative size");
            }
        }

        long area() {
            return (long) width * height;
        }

        long perimeter() {
            return 2L * (width + (long) height);
        }

        boolean square() {
            return width == height;
        }
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(4, 3);
        Rectangle b = new Rectangle(5, 5);

        System.out.println("a area=" + a.area());
        System.out.println("a perimeter=" + a.perimeter());
        System.out.println("a square=" + a.square());
        System.out.println("b square=" + b.square());
    }
}
~~~

Chạy:

~~~bash
javac RecordDerivedMethodsDemo.java
java RecordDerivedMethodsDemo
~~~

Output:

~~~text
a area=12
a perimeter=14
a square=false
b square=true
~~~

Các methods không lưu thêm `area`/`perimeter` instance fields. Kết quả được tính từ components; điều này giữ **record representation đúng là width + height**.

Nếu phép tính đắt đỏ và cần cache mutable per-instance, một normal class có thể phù hợp hơn, vì record không cho khai additional instance fields. Có thể dùng external cache, nhưng cần đánh giá lifecycle, equality và complexity thay vì cố lách quy tắc record.

## 12. Value equality: `equals` và `==` khác nhau

Record được dùng nhiều làm **value object**: hai instances riêng có components bằng nhau sẽ được `equals` xem là equal theo quy tắc record.

~~~java
record Point(int x, int y) {
}

Point first = new Point(2, 3);
Point second = new Point(2, 3);
~~~

- `first == second` thường là `false` vì `new` tạo hai object instances khác nhau.
- `first.equals(second)` là `true` vì cùng record type và components có values bằng nhau.
- `first.hashCode() == second.hashCode()` phải true theo hashCode contract khi equals true.
- `first.toString()` hiển thị tên record/components trong định dạng của record API.

**Không đánh đồng equals với deep structural comparison của mọi object graph**. Nếu một component là array, generated equality dùng semantics của array reference component, không tự gọi `Arrays.equals`.

### 12.1. Thứ tự component là một phần của record shape

`record Pair(int left,int right)` có generated constructor `Pair(int left,int right)`. `new Pair(2,3)` khác về value với `new Pair(3,2)`. Names và order cho code/API ý nghĩa. Khi thay thứ tự components, source callers có thể không bị compiler bắt lỗi nếu types giống nhau — cần quản lý API evolution và tests.

## 13. Chương trình: identity, equality và HashSet

Lưu **`RecordEqualityDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Set;

public class RecordEqualityDemo {
    record Key(String code, int revision) {
    }

    public static void main(String[] args) {
        Key first = new Key("A", 1);
        Key sameValue = new Key("A", 1);
        Key other = new Key("A", 2);

        System.out.println("same instance=" +
                (first == sameValue));
        System.out.println("equal values=" +
                first.equals(sameValue));
        System.out.println("different revision=" +
                first.equals(other));
        System.out.println("equal hashes=" +
                (first.hashCode() == sameValue.hashCode()));

        Set<Key> keys = new HashSet<>();
        keys.add(first);
        keys.add(sameValue);
        keys.add(other);

        System.out.println("set size=" + keys.size());
        System.out.println("contains equivalent=" +
                keys.contains(new Key("A", 1)));
    }
}
~~~

Chạy:

~~~bash
javac RecordEqualityDemo.java
java RecordEqualityDemo
~~~

Output:

~~~text
same instance=false
equal values=true
different revision=false
equal hashes=true
set size=2
contains equivalent=true
~~~

Không in raw `HashSet` để tránh phụ thuộc thứ tự iteration không được bảo đảm. `Set` loại bỏ value-duplicates vì `equals`/`hashCode` của records dựa trên components.

**Giới hạn:** nếu component mutable tham gia hash/equality có thể thay đổi sau khi lưu vào HashSet/HashMap, record đó không còn là key an toàn. Chỉ dùng làm key khi **equality-relevant state ổn định**.

## 14. Một record không tự deep immutable

Xem:

~~~java
record Picture(int[] pixels) {
}
~~~

`pixels` là một record component; backing field final chỉ ngăn thay reference bên trong object theo rules. Nhưng:

~~~java
int[] source = {1, 2};
Picture p = new Picture(source);
source[0] = 9;
System.out.println(p.pixels()[0]); // 9
~~~

Chính cùng một array object được reference bởi `source` và `p.pixels()`. Record **không tự clone array**.

Tương tự:
- `record R(List<MutableItem> items)` vẫn có thể quan sát mutation của MutableItem.
- `record R(Date date)` nếu dùng `java.util.Date` mutable, caller giữ alias có thể sửa trạng thái.
- `record R(StringBuilder text)` giữ mutable StringBuilder.
- `record R(LocalDate date)` chia sẻ `LocalDate` an toàn về mutation vì LocalDate immutable.

**Shallow immutability** khác **deep immutability**. Đây là một trong những lưu ý quan trọng nhất khi dùng record biểu diễn dữ liệu.

## 15. Chương trình phản ví dụ: record giữ cùng mutable object

Lưu **`RecordMutableComponentDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordMutableComponentDemo {
    record Basket(List<String> items) {
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket basket = new Basket(source);

        source.add("B");
        basket.items().add("C");

        System.out.println("source=" + source);
        System.out.println("basket=" + basket.items());
        System.out.println("same list=" +
                (source == basket.items()));
    }
}
~~~

Chạy:

~~~bash
javac RecordMutableComponentDemo.java
java RecordMutableComponentDemo
~~~

Output:

~~~text
source=[A, B, C]
basket=[A, B, C]
same list=true
~~~

Dù record component `items` có backing field final, accessor mặc định trả **reference tới cùng list**. Caller có thể mutate list. Vì vậy `record` không thay thế defensive copying khi API hứa snapshot.

## 16. Chọn immutable snapshot cho nhóm giá trị có tên

Khi record đại diện một **bản chụp (snapshot)**, hãy copy cấu trúc mutable đầu vào:

~~~java
record Basket(List<String> items) {
    Basket {
        items = List.copyOf(items);
    }
}
~~~

Đây là compact constructor. `List.copyOf` tạo unmodifiable representation của structure và không cho phép null elements. Vì String immutable, một `List<String>` như ví dụ thường đủ ổn định sau khi copy structure.

**Nhưng** `List.copyOf` không deep-copy custom mutable elements; `List<MutableItem>` vẫn giữ same element references. Nếu cần snapshot sâu, chuyển từng item thành immutable value record/DTO trước khi copy list.

### 16.1. Chương trình record + immutable list snapshot

Lưu **`RecordListSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordListSnapshotDemo {
    record Basket(List<String> items) {
        Basket {
            items = List.copyOf(items);
        }

        int count() {
            return items.size();
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket snapshot = new Basket(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("snapshot=" + snapshot.items());
        System.out.println("snapshot count=" + snapshot.count());

        try {
            snapshot.items().add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot cannot add");
        }
    }
}
~~~

Chạy:

~~~bash
javac RecordListSnapshotDemo.java
java RecordListSnapshotDemo
~~~

Output:

~~~text
source=[A, B]
snapshot=[A]
snapshot count=1
snapshot cannot add
~~~

Nguồn list vẫn mutable, nhưng Basket chứa snapshot structure tại thời điểm xây. Vì elements là String immutable, mutation list hoặc String values qua alias không làm snapshot thay đổi.

### 16.2. Snapshot tại ranh giới nào?

Một API nhận input mutable cần xem caller có giữ reference không. Nếu có và record hứa snapshot riêng, hãy copy ở constructor. Nếu accessor trả một immutable list đủ ổn định, có thể trả cùng list; không nhất thiết phải copy mỗi lần gọi. Với primitive arrays, thường cần copy cả khi nhập **và** xuất.

## 17. Thành phần mảng: phân biệt snapshot và ngữ nghĩa bằng nhau

Một record như `record Bytes(byte[] data) {}` **không** tự sao chép `byte[]`. Accessor mặc định `data()` trả reference tới mảng mà component field đang giữ. Nếu cần bảo vệ snapshot, một record có thể ghi rõ hai ranh giới:

~~~java
record Bytes(byte[] data) {
    Bytes {
        data = java.util.Objects.requireNonNull(data).clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
~~~

Đây là **record declaration** hợp lệ, không phải chương trình có `main`. Constructor compact thay parameter bằng clone trước khi Java gán vào field; accessor tường minh trả clone để không lộ state.

**Phân biệt hai bài toán:** defensive copy chặn mutation qua alias, nhưng generated `equals/hashCode` vẫn so component mảng theo **array reference semantics**, không tự so nội dung như `Arrays.equals`. Các trường hợp giá trị bằng nhau, hash-based collections và custom equals/hashCode nằm ở bài chuyên sâu **“equals(), hashCode(), toString() và ảnh hưởng của thành phần mảng”**. Mối quan hệ giữa shallow/deep immutability nằm ở bài **“Record chỉ bảo đảm bất biến nông”**.

## 18. Chương trình: defensive copy array và state isolation

Lưu **`RecordArrayDefensiveDemo.java`**:

~~~java
import java.util.Arrays;

public class RecordArrayDefensiveDemo {
    record Payload(int[] values) {
        Payload {
            values = values.clone();
        }

        @Override
        public int[] values() {
            return values.clone();
        }

        int total() {
            return Arrays.stream(values).sum();
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2, 3};
        Payload payload = new Payload(input);

        input[0] = 9;
        int[] outgoing = payload.values();
        outgoing[1] = 8;

        System.out.println("input=" + Arrays.toString(input));
        System.out.println("outgoing=" + Arrays.toString(outgoing));
        System.out.println("stored total=" + payload.total());
    }
}
~~~

Chạy:

~~~bash
javac RecordArrayDefensiveDemo.java
java RecordArrayDefensiveDemo
~~~

Output:

~~~text
input=[9, 2, 3]
outgoing=[1, 8, 3]
stored total=6
~~~

Tổng 6 chứng minh internal array không bị hai mutations bên ngoài tác động. **Không suy** rằng hai Payload objects có array contents bằng nhau sẽ tự `equals` true; record-generated equality cho array components dùng array reference identity semantics.

## 19. Record với nested immutable values

Một record có thể nhóm các records khác để tạo dữ liệu có cấu trúc:

~~~java
record Point(int x, int y) { }
record Segment(Point from, Point to) { }
~~~

`Point` chỉ chứa primitives, do đó có value semantics ổn định và không có mutable child. `Segment` chỉ chứa Point references, và nếu hai Points thực sự immutable, có thể **chia sẻ** Point objects mà không cần clone.

Không có “copy sâu mọi thứ” bắt buộc chỉ vì nested references tồn tại. Vấn đề là **các objects được tham chiếu có thể bị mutate hay không**.

### 19.1. Chương trình record graph bất biến

Lưu **`NestedRecordValuesDemo.java`**:

~~~java
public class NestedRecordValuesDemo {
    record Point(int x, int y) {
        Point translated(int dx, int dy) {
            return new Point(x + dx, y + dy);
        }
    }

    record Segment(Point from, Point to) {
        Segment {
            if (from == null || to == null) {
                throw new IllegalArgumentException("null endpoint");
            }
        }

        int dx() {
            return to.x() - from.x();
        }
    }

    public static void main(String[] args) {
        Point origin = new Point(1, 1);
        Segment first = new Segment(origin, new Point(4, 1));
        Segment second = new Segment(
                origin, origin.translated(0, 3));

        System.out.println("first dx=" + first.dx());
        System.out.println("second dx=" + second.dx());
        System.out.println("shared from=" +
                (first.from() == second.from()));

        Point moved = origin.translated(10, 0);
        System.out.println("old origin=" + origin);
        System.out.println("new point=" + moved);
    }
}
~~~

Chạy:

~~~bash
javac NestedRecordValuesDemo.java
java NestedRecordValuesDemo
~~~

Output:

~~~text
first dx=3
second dx=0
shared from=true
old origin=Point[x=1, y=1]
new point=Point[x=11, y=1]
~~~

Hai Segments cùng giữ origin Point reference nhưng không bị các updates gây thay đổi, vì `translated` tạo value mới. Với primitive int trong record, không có mutation setter.

## 20. Generic record: nhóm dữ liệu có tên mà vẫn giữ type safety

Record có thể khai báo type parameters riêng:

~~~java
record Response<T>(T payload, int status) {
}
~~~

Dùng:

~~~java
Response<String> text = new Response<>("OK", 200);
Response<Integer> count = new Response<>(42, 200);
~~~

Lợi ích: một **mẫu nhóm dữ liệu** có thể dùng với nhiều kiểu payload, trong khi component names vẫn có ý nghĩa `payload`/`status`.

### 20.1. Khi nào generic record là chưa đủ?

Nếu `Response<T>` cho phép bất kỳ T nào, một caller vẫn có thể đưa mutable T object vào. Record generic không tự sao chép T hoặc làm T immutable. Cần tài liệu API, type constraints, conversion sang immutable values hoặc defensive copy khi domain yêu cầu.

## 21. Chương trình: generic record có method

Lưu **`GenericRecordDemo.java`**:

~~~java
import java.util.Objects;

public class GenericRecordDemo {
    record Box<T>(T value, String label) {
        Box {
            Objects.requireNonNull(value, "value");
            Objects.requireNonNull(label, "label");
        }

        String describe() {
            return label + "=" + value;
        }
    }

    public static void main(String[] args) {
        Box<Integer> one = new Box<>(17, "version");
        Box<String> two = new Box<>("ready", "state");

        System.out.println(one.describe());
        System.out.println(two.describe());
        System.out.println("integer value=" + one.value());
    }
}
~~~

Chạy:

~~~bash
javac GenericRecordDemo.java
java GenericRecordDemo
~~~

Output:

~~~text
version=17
state=ready
integer value=17
~~~

`Box<Integer>` không biến Integer thành primitive field (generic erasure/boxing vẫn áp dụng). Record header định nghĩa components, còn `Box<T>` type parameter giữ compile-time type consistency.

## 22. Record có thể implement interface

Record ngầm extends `java.lang.Record` nên không thể tự extends một normal superclass khác, nhưng có thể `implements` interfaces:

~~~java
interface Identified {
    String id();
}

record UserId(String id) implements Identified {
}
~~~

Generated accessor `id()` thỏa contract của interface `Identified` nếu visibility/type/signature phù hợp. Đây là cách record đóng vai trò value object trong một API polymorphic.

### 22.1. Chương trình đầy đủ

Lưu **`RecordInterfaceDemo.java`**:

~~~java
public class RecordInterfaceDemo {
    interface Measurable {
        long area();
    }

    record Rectangle(int width, int height)
            implements Measurable {
        Rectangle {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("size");
            }
        }

        @Override
        public long area() {
            return (long) width * height;
        }
    }

    static void report(Measurable measure) {
        System.out.println("area=" + measure.area());
    }

    public static void main(String[] args) {
        Measurable small = new Rectangle(3, 4);
        Measurable large = new Rectangle(5, 6);

        report(small);
        report(large);
    }
}
~~~

Chạy:

~~~bash
javac RecordInterfaceDemo.java
java RecordInterfaceDemo
~~~

Output:

~~~text
area=12
area=30
~~~

Dù caller nhìn qua `Measurable`, thực thể dưới vẫn là record instances. Record là class, vì thế tích hợp được với Java polymorphism thông thường qua interfaces.

## 23. Local record: một nhóm dữ liệu riêng cho một block

Nếu nhóm dữ liệu chỉ dùng trong một method, có thể khai một **local record** (Java 17):

~~~java
void process() {
    record Entry(String key, int count) {
    }

    Entry entry = new Entry("A", 2);
    System.out.println(entry);
}
~~~

Local record có lexical scope của block; không phải member type accessible bằng `Outer.Entry` từ class ngoài. Nó **implicitly static**: không capture outer locals/instance state như local normal class.

Ví dụ sai (đã comment):

~~~java
void process(int bonus) {
    // record Entry(int score) {
    //     int total() { return score + bonus; } // Không capture bonus.
    // }
}
~~~

Cách đúng: truyền `bonus` thành component hoặc argument của method, vì record cần **explicit data flow**.

### 23.1. Chương trình runnable

Lưu **`LocalRecordDemo.java`**:

~~~java
public class LocalRecordDemo {
    static void summarize(int base, int bonus) {
        record Calculation(int base, int bonus) {
            int total() {
                return base + bonus;
            }
        }

        Calculation result = new Calculation(base, bonus);
        System.out.println("summary=" + result);
        System.out.println("total=" + result.total());
    }

    public static void main(String[] args) {
        summarize(10, 5);
    }
}
~~~

Chạy:

~~~bash
javac LocalRecordDemo.java
java LocalRecordDemo
~~~

Output:

~~~text
summary=Calculation[base=10, bonus=5]
total=15
~~~

`Calculation` là local type nhưng object của nó không bắt buộc sống chỉ trong stack frame; nếu trả qua interface/Object hoặc lưu reference ở nơi khác, record instance có thể sống lâu hơn method. “Local” là phạm vi tên source, không phải quy tắc cấp phát/GC riêng.

## 24. Member record là implicitly static nested type

Nếu một record được khai báo trong class:

~~~java
class Container {
    record Item(String name, int count) {
    }
}
~~~

Thì `Item` là **member record**, được implicitly static, không cần một enclosing Container object để khởi tạo:

~~~java
Container.Item item = new Container.Item("A", 3);
~~~

Không viết `container.new Item(...)` vì member record không phải non-static inner class. Trường hợp code ngoài cần dùng, visibility của Container/Item và constructor phải đáp ứng Java access control.

### 24.1. Chương trình nested record

Lưu **`MemberRecordDemo.java`**:

~~~java
public class MemberRecordDemo {
    static class Store {
        private final String name;

        Store(String name) {
            this.name = name;
        }

        record Item(String sku, int quantity) {
        }

        Item newItem(String sku, int quantity) {
            return new Item(sku, quantity);
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Store store = new Store("Main");
        Store.Item item = store.newItem("PEN", 3);
        Store.Item another = new Store.Item("BOOK", 2);

        System.out.println("store=" + store.name());
        System.out.println("item=" + item);
        System.out.println("another=" + another);
    }
}
~~~

Chạy:

~~~bash
javac MemberRecordDemo.java
java MemberRecordDemo
~~~

Output:

~~~text
store=Main
item=Item[sku=PEN, quantity=3]
another=Item[sku=BOOK, quantity=2]
~~~

`Store.Item` là nested record và có thể được tạo trực tiếp; việc `Store.newItem` gọi constructor chỉ là một convenience method, không cung cấp enclosing instance ngầm cho Item.

## 25. Record không phải mutable entity

Một entity thường có **identity nghiệp vụ ổn định** và trạng thái có thể thay đổi:

- Tài khoản có số dư thay đổi.
- Đơn hàng có các trạng thái NEW/PAID/SHIPPED.
- Session được làm mới.
- Một đối tượng JPA/ORM cần lifecycle/instrumentation đặc thù.

Record **không phải** sự thay thế tự động cho mọi mutable entity. Record components fields là final, record class final, không có setters để gán lại chúng.

Tuy nhiên, record có thể rất hữu ích làm:
- **Immutable snapshot** của entity tại thời điểm T.
- Value object như Money, Coordinate, DateRange.
- Response DTO cho API và event payload.
- Command parameters được validate.
- Projection khi lấy một phần dữ liệu từ query.
- Key bền ổn định cho hash collections.

### 25.1. “Update record” bằng tạo giá trị mới

Thay vì `point.setX(9)`, tạo Point mới:

~~~java
record Point(int x, int y) {
    Point withX(int nextX) {
        return new Point(nextX, y);
    }
}
~~~

Tư duy *value evolution*: object cũ vẫn giữ giá trị cũ, object mới mô tả state mới.

## 26. Chương trình: thay đổi bằng cách tạo bản mới

Lưu **`RecordWithMethodDemo.java`**:

~~~java
public class RecordWithMethodDemo {
    record Settings(String theme, int size) {
        Settings {
            if (size <= 0) {
                throw new IllegalArgumentException("size");
            }
        }

        Settings withTheme(String next) {
            return new Settings(next, size);
        }

        Settings withSize(int next) {
            return new Settings(theme, next);
        }
    }

    public static void main(String[] args) {
        Settings oldValue = new Settings("light", 12);
        Settings dark = oldValue.withTheme("dark");
        Settings larger = dark.withSize(16);

        System.out.println("old=" + oldValue);
        System.out.println("dark=" + dark);
        System.out.println("larger=" + larger);
        System.out.println("same object=" + (oldValue == dark));
    }
}
~~~

Chạy:

~~~bash
javac RecordWithMethodDemo.java
java RecordWithMethodDemo
~~~

Output:

~~~text
old=Settings[theme=light, size=12]
dark=Settings[theme=dark, size=12]
larger=Settings[theme=dark, size=16]
same object=false
~~~

`withTheme`/`withSize` **không phải generated record methods**; chúng do lập trình viên tự khai để API rõ ý nghĩa. Nếu next value bằng old value, một method có thể chọn trả `this` khi contract cho phép, nhưng code demo tạo object mới mỗi lần để minh họa semantics.

## 27. Record kết hợp enum để biểu diễn state có tên

Một record có thể giữ enum component để biểu diễn tập trạng thái hữu hạn:

~~~java
enum Status { NEW, DONE }
record Task(String title, Status status) { }
~~~

Khi đó `Task` giữ một nhóm giá trị mang ý nghĩa nghiệp vụ: title và status. Enum constants như Status.NEW được chia sẻ; nếu enum chỉ có immutable state, điều này phù hợp với record value representation.

### 27.1. Chương trình tích hợp

Lưu **`RecordWithEnumDemo.java`**:

~~~java
import java.util.Objects;

public class RecordWithEnumDemo {
    enum Status {
        NEW, DONE
    }

    record Task(String title, Status status) {
        Task {
            Objects.requireNonNull(title, "title");
            Objects.requireNonNull(status, "status");
        }

        Task completed() {
            return new Task(title, Status.DONE);
        }
    }

    public static void main(String[] args) {
        Task initial = new Task("Study", Status.NEW);
        Task finished = initial.completed();

        System.out.println("initial=" + initial);
        System.out.println("finished=" + finished);
        System.out.println("same title=" +
                initial.title().equals(finished.title()));
    }
}
~~~

Chạy:

~~~bash
javac RecordWithEnumDemo.java
java RecordWithEnumDemo
~~~

Output:

~~~text
initial=Task[title=Study, status=NEW]
finished=Task[title=Study, status=DONE]
same title=true
~~~

Đây là ví dụ record làm **snapshot value**: initial object không bị mutate khi Task được “hoàn thành”; method trả Task value mới. Nếu một domain entity cần chuyển trạng thái có side effects/transactions, record có thể làm DTO/snapshot, còn quy tắc lifecycle nằm ở service/aggregate.

## 28. Collections và record làm Map key

Khi record có immutable components, generated `equals/hashCode` khiến nó rất tự nhiên làm HashMap key:

~~~java
record Coordinate(int x, int y) { }
java.util.Map<Coordinate, String> labels = new java.util.HashMap<>();
labels.put(new Coordinate(1, 2), "A");
String value = labels.get(new Coordinate(1, 2));
~~~

Cùng value key sẽ tra được entry. Không cần giữ chính object key reference đã insert.

### 28.1. Chương trình đầy đủ

Lưu **`RecordMapKeyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RecordMapKeyDemo {
    record Coordinate(int x, int y) {
    }

    public static void main(String[] args) {
        Map<Coordinate, String> labels = new HashMap<>();
        labels.put(new Coordinate(1, 2), "Home");
        labels.put(new Coordinate(3, 4), "Office");

        System.out.println("lookup=" +
                labels.get(new Coordinate(1, 2)));
        System.out.println("size=" + labels.size());
        System.out.println("missing=" +
                labels.get(new Coordinate(9, 9)));
    }
}
~~~

Chạy:

~~~bash
javac RecordMapKeyDemo.java
java RecordMapKeyDemo
~~~

Output:

~~~text
lookup=Home
size=2
missing=null
~~~

Không dùng mutable List/array references làm equality-relevant components nếu cần key ổn định mà không bảo vệ dữ liệu tương ứng. Records không tự “đóng băng” nested objects để giữ hashCode ổn định.

## 29. Record được phép và không được phép khai báo những gì?

| Khả năng | Record Java 17 | Ghi chú |
| --- | --- | --- |
| Component header | Có | Mô tả state có tên |
| Component fields do compiler sinh | Có, private final | Không tự khai thêm trùng |
| Generated accessors | Có | `componentName()` |
| Canonical constructor | Có | Implicit, normal hoặc compact |
| Các constructors khác | Có | Phải delegate bằng `this(...)` theo rules |
| Instance methods | Có | Behavior từ components |
| Static fields/methods | Có | Không được thêm instance state tùy ý |
| Implement interfaces | Có | Gồm generic interfaces phù hợp |
| Generic type parameters | Có | `record Box<T>(T value)` |
| Member nested/local declarations | Có | Theo rules, member/local record implicitly static |
| Additional instance fields | **Không** | Record state phải mô tả qua components |
| Instance initializer block `{...}` | **Không** | Dùng constructors |
| Khai `extends SomeClass` | **Không** | Ngầm extends `java.lang.Record` |
| Kế thừa từ một record khác | **Không** | Records implicitly final |
| Abstract record | **Không** | Record không cho subclass |
| Setters cho backing final fields | **Không** | Dùng new record object |
| Custom `equals/hashCode/toString` | Có | Phải giữ contract và semantics |
| Components kiểu mutable | Có | Nhưng không tự deep immutable |

### 29.1. Các dòng sai (đã comment)

~~~java
record Invalid(int x) {
    // private int extra; // Compile-time error: instance field thêm.
    // { System.out.println("init"); } // Instance initializer không hợp lệ.
    // void setX(int n) { this.x = n; } // Final component field.
}

// record Derived(int n) extends Base { } // Record không có extends clause.
~~~

Lý do không phải “record không phải class”. Record **là class đặc biệt** với cam kết mô hình dữ liệu minh bạch theo components, nên hạn chế instance representation ngoài header.

## 30. Phân biệt record với Lombok `@Data` hoặc POJO viết tay

Một normal Java class tương đương về mặt ý tưởng có thể cần:

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

    // equals, hashCode, toString sẽ phải tự viết
    // nếu muốn component-value semantics.
}
~~~

Trong record `record Point(int x,int y) {}`, Java language/compiler sinh phần lớn boilerplate đó. So với codegen từ một library, record semantics được **định nghĩa bởi Java Language Specification** và chạy trên JDK hỗ trợ.

Tuy nhiên, record khác mutable JavaBean:
- Không có no-arg constructor + setters điền từng bước theo convention thông thường.
- Fields final, phải được khởi tạo qua constructors.
- Class final, không làm superclass cho một subclass entity.
- Kể cả cùng tên components, một normal class và một record là hai types khác nhau.
- Framework cần hỗ trợ record constructors/accessors thay vì giả định getter/setter kiểu bean.

**Không thay POJO/entity bằng record chỉ để tiết kiệm số dòng** nếu record semantics không phù hợp business lifecycle.

## 31. Custom accessor và normalization: cần giữ nhất quán

Có thể khai component accessor thủ công để thay logic trả value:

~~~java
record Name(String value) {
    Name {
        value = value.strip();
    }

    @Override
    public String value() {
        return value;
    }
}
~~~

Ở đây override không có lợi rõ rệt vì generated accessor đã trả cùng String. Trong ví dụ array, override accessor để clone có giá trị hơn. Nhưng override cần giữ **loại trả về chính xác**, quyền truy cập và record semantics.

### 31.1. Custom Object methods: rủi ro đi cùng quyền linh hoạt

Nếu tự khai `equals`/`hashCode` để có domain equality khác, chúng phải:
- Reflexive, symmetric, transitive, consistent theo equals contract.
- Có hashCode tương thích: objects equal phải có cùng hash.
- Đúng với các components và mục đích record representation.
- Không dùng mutable state thay đổi trong thời gian object làm Map key.

Thông thường, **ưu tiên generated methods**, trừ khi có lý do kỹ thuật mạnh, vì generated semantics là một lợi ích chủ yếu của record.

## 32. Multiple constructors trong record: luôn quy về canonical

Record có thể khai một constructor tiện lợi khác signature:

~~~java
record Label(String text, int priority) {
    Label(String text) {
        this(text, 0);
    }
}
~~~

Non-canonical constructor phải bắt đầu bằng explicit `this(...)` invocation tới constructor cùng record. Nó không được “tự gán” các component fields như một constructor bình thường có mutable representation.

### 32.1. Chương trình runnable

Lưu **`RecordConstructorOverloadDemo.java`**:

~~~java
public class RecordConstructorOverloadDemo {
    record Label(String text, int priority) {
        Label {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("text");
            }
        }

        Label(String text) {
            this(text, 0);
        }
    }

    public static void main(String[] args) {
        Label defaultPriority = new Label("A");
        Label urgent = new Label("B", 10);

        System.out.println("default=" + defaultPriority);
        System.out.println("urgent=" + urgent);
    }
}
~~~

Chạy:

~~~bash
javac RecordConstructorOverloadDemo.java
java RecordConstructorOverloadDemo
~~~

Output:

~~~text
default=Label[text=A, priority=0]
urgent=Label[text=B, priority=10]
~~~

Nhờ `this(text,0)`, mọi paths đi qua compact canonical constructor nên đều dùng cùng validation rule. Nếu có thêm nhiều constructors tiện lợi, cần giữ invariants nhất quán.

## 33. Record và serialization / JSON / database

Record thường phù hợp làm DTO, nhưng việc serialize/deserialize phụ thuộc framework:

- JSON thư viện cần hỗ trợ record canonical constructor/component names.
- Validation vẫn cần chạy tại boundary, không đơn giản tin dữ liệu external đúng.
- Thêm, đổi tên hoặc đổi thứ tự component có thể ảnh hưởng schema và consumers.
- Generated `toString()` **không phải JSON serializer**, không có cam kết được dùng làm giao thức ổn định.
- Java Object Serialization có xử lý riêng cho serializable records, nhưng không đồng nghĩa mọi record tự `implements Serializable` hoặc JSON representation nào cũng giống nhau.
- Nếu domain cần ORM entity tracking/proxies/mutable lifecycle, normal entity class thường phù hợp hơn record.

### 33.1. Đừng parse `toString()` thành data format

Với `new Point(1,2).toString()` có biểu diễn đọc được như `Point[x=1, y=2]`, nhưng đó là presentation/debug representation, không nên coi là public wire protocol. Dùng JSON/schema/format chuyên dụng khi cần trao đổi dữ liệu ổn định.

## 34. Khi nào **nên** dùng record biểu diễn nhóm giá trị?

Tình huống phù hợp:

1. Một kết quả tính toán có nhiều phần: `record Stats(long min,long max,double average)`.
2. Tọa độ/kích thước: `Point(x,y)`, `Size(width,height)`.
3. Khoảng giá trị có invariant: `Range(start,end)`.
4. Một khóa truy vấn: `Key(countryCode,customerId)` khi cả hai immutable.
5. Một message hoặc sự kiện: `Event(id,type,timestamp)` khi snapshot semantics đúng.
6. API response có trường rõ ràng: `Response(status,payload)`.
7. Các giá trị trung gian của thuật toán, đặc biệt local record chỉ dùng trong method.
8. Composite value object gồm nhiều immutable record components khác.

Tình huống cần cân nhắc:

- Cần thay fields tại chỗ, identity độc lập với current field values.
- Cần inheritance class hierarchy thông thường, proxies hoặc no-arg mutable construction convention.
- Phải quản lý resource lifecycle, listeners, transactions và mutable graph state.
- Components chứa mutable data mà không thể xác định ownership/snapshot.
- Có rất nhiều optional/unordered parameters, constructor call dễ đảo; cân nhắc builder/named factory và validation.

## 35. Chương trình tích hợp: record nhóm dữ liệu báo giá

Lưu **`RecordQuoteIntegrationDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;

public class RecordQuoteIntegrationDemo {
    record Item(String sku, long unitPrice, int quantity) {
        Item {
            Objects.requireNonNull(sku, "sku");
            if (unitPrice < 0 || quantity <= 0) {
                throw new IllegalArgumentException("item data");
            }
        }

        long amount() {
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    record Quote(String id, List<Item> items) {
        Quote {
            Objects.requireNonNull(id, "id");
            items = List.copyOf(items);
        }

        long total() {
            long sum = 0L;
            for (Item item : items) {
                sum = Math.addExact(sum, item.amount());
            }
            return sum;
        }
    }

    public static void main(String[] args) {
        Quote quote = new Quote("Q1", List.of(
                new Item("PEN", 10, 2),
                new Item("BOOK", 50, 1)));

        System.out.println("quote=" + quote.id());
        System.out.println("lines=" + quote.items().size());
        System.out.println("total=" + quote.total());
        System.out.println("first sku=" +
                quote.items().get(0).sku());
    }
}
~~~

Chạy:

~~~bash
javac RecordQuoteIntegrationDemo.java
java RecordQuoteIntegrationDemo
~~~

Output:

~~~text
quote=Q1
lines=2
total=70
first sku=PEN
~~~

Phân tích:

- `Item` nhóm SKU, đơn giá, số lượng vào **một kiểu có tên**, thay vì `Object[]`.
- `Item.amount()` tính derived value từ components. `Math.multiplyExact` phát hiện overflow của phép nhân long theo Java contract.
- `Quote` giữ id và danh sách lines. `List.copyOf` giúp giữ cấu trúc danh sách không bị sửa qua source list.
- Vì Item components chỉ là String/long/int, Item là một immutable value object thực tế trong ví dụ, nên chia sẻ Item references trong `Quote` không tạo mutable alias risk.
- Nếu đơn giá có currency/decimal precision/rounding, production nên có Money type/domain rules chứ không mặc định lấy long đơn vị tùy ý.

## 36. Bảng lỗi thường gặp

| Hiểu sai / sai sót | Cách hiểu đúng |
| --- | --- |
| “Record là array có tên khác.” | Record là một **class** có nhóm typed, named components. |
| “`Point(1,2)` không cần `new` vì record là value.” | Java 17 record tạo bằng `new Point(1,2)` như class instance. |
| “Record chỉ khai báo fields, không có methods.” | Có instance/static methods, constructors, interfaces. |
| “Accessors được đặt tên `getX()`.” | Generated accessor là `x()`. |
| “Record sinh setter cho mỗi component.” | Không; component fields private final. |
| “Hai `new Point(1,2)` sẽ `==` true.” | Không; thường hai instances riêng, `equals` true. |
| “Generated equals so deep mọi thứ.” | Array components so theo reference; nested mutable elements không được deep-copy. |
| “Record là deep immutable.” | Chỉ final component references; nested object vẫn có thể mutable. |
| “Final List component không thể thêm element.” | Nếu list mutable và accessor expose nó, vẫn add được. |
| “`List.copyOf` deep-clone mutable Item.” | Chỉ snapshot structure; Item references được chia sẻ. |
| “Record luôn là HashMap key an toàn.” | Chỉ khi equality/hash-relevant state ổn định. |
| “Một record có thêm instance field cache tuỳ ý.” | Không; instance state phải mô tả bằng components. |
| “Instance initializer block dùng như class thường.” | Record không cho phép instance initializer block. |
| “Record có thể extends normal superclass.” | Không; ngầm extends `java.lang.Record` và implicitly final. |
| “Record không implement interface.” | Có thể implements. |
| “Member record cần `outer.new Inner()`.” | Member record implicitly static, tạo bằng `new Outer.Record(...)`. |
| “Local record capture method variables.” | Không; truyền qua constructor/method params. |
| “Compact constructor cần gán `this.x = x`.” | Không; compiler tự gán sau body. |
| “Non-canonical constructor tự gán fields trực tiếp.” | Phải delegate bằng `this(...)`. |
| “Không cần validate record vì compiler làm hộ.” | Generated constructor chỉ tuân types; domain invariant tự kiểm. |
| “Record toString là định dạng JSON.” | Không; presentation/debug representation. |
| “Record thay thế mọi mutable ORM entity.” | Không; domain identity/lifecycle có thể yêu cầu normal class. |
| “Đổi thứ tự component cùng kiểu sẽ bị compiler chặn.” | Có thể compile và đổi nghĩa; cần tests/API evolution. |

## 37. Checklist khi thiết kế một record

- [ ] Các components có tên và kiểu thể hiện rõ **một khái niệm domain**?
- [ ] Có dùng tên field biểu đạt ý nghĩa hơn `first/second` hoặc `data1/data2` không?
- [ ] Constructor parameter order có dễ bị đảo khi hai kiểu trùng nhau không?
- [ ] Có invariant cần kiểm tra ở compact/normal canonical constructor?
- [ ] Input null, blank, âm, overflow, invalid enum values đã có policy chưa?
- [ ] Components tham chiếu tới types mutable nào?
- [ ] Có cần defensive copy ở input boundary để giữ snapshot?
- [ ] Generated accessor có làm lộ mutable internal representation không?
- [ ] Nếu dùng `List.copyOf`, các elements có immutable thật không?
- [ ] Có đang dùng array component nhưng kỳ vọng deep array equality không?
- [ ] `equals/hashCode` có ổn định nếu đưa vào `HashMap`/`HashSet` không?
- [ ] Có cần method dẫn xuất từ components thay vì một instance cache field bị cấm?
- [ ] Record có nên implement một interface có ý nghĩa không?
- [ ] Type là local/member/top-level đúng phạm vi sử dụng chưa?
- [ ] Có framework/serializer/ORM nào cần hỗ trợ đặc thù cho records?
- [ ] Có wire schema riêng, không phụ thuộc `toString()` debug representation không?
- [ ] Nếu cần update, có method `with...()` hoặc factory tạo record mới dễ hiểu?
- [ ] Nếu cần mutable identity/entity lifecycle, có nên dùng normal class thay record?
- [ ] Đã kiểm tra Java 17, compiler/lệnh chạy và exact stdout chưa?

## 38. Bài tập ôn luyện kèm đáp án

**Câu 1.** `record Point(int x,int y)` mô tả điều gì?  
**Đáp án:** Một class có hai named components, x kiểu int và y kiểu int.

**Câu 2.** Điểm khác chính so với `int[]` là gì?  
**Đáp án:** Tên kiểu và tên components mang ý nghĩa; constructor/accessors/type checking rõ ràng.

**Câu 3.** Constructor tạo Point record được gọi ra sao?  
**Đáp án:** `new Point(2,3)`.

**Câu 4.** Accessor generated của x tên gì?  
**Đáp án:** `x()`, không tự sinh `getX()`.

**Câu 5.** Có thể khai `record User(String name,int age){}` mà không khai constructor thủ công không?  
**Đáp án:** Có; compiler sinh canonical constructor.

**Câu 6.** Generated `equals` dùng để so identity hay component values?  
**Đáp án:** So theo record components; không giống `==`.

**Câu 7.** `new Point(2,3)==new Point(2,3)` thường bằng gì?  
**Đáp án:** False vì hai object identities khác nhau.

**Câu 8.** `new Point(2,3).equals(new Point(2,3))` bằng gì?  
**Đáp án:** True vì component values bằng nhau.

**Câu 9.** Có thể dùng record làm Map key không?  
**Đáp án:** Có nếu equality/hash-relevant data ổn định.

**Câu 10.** Vì sao mutable component làm record key nguy hiểm?  
**Đáp án:** Hash/equality có thể đổi sau khi key được lưu, phá lookup invariants.

**Câu 11.** Record có mặc nhiên sao chép sâu array component không?  
**Đáp án:** Không.

**Câu 12.** Muốn giữ array snapshot cần xử lý ở đâu?  
**Đáp án:** Defensive copy lúc construction và thường ở accessor khi trả mutable array.

**Câu 13.** Generated equality của array component có tự so nội dung như `Arrays.equals` không?  
**Đáp án:** Không; array reference equality semantics.

**Câu 14.** `List.copyOf` giúp điều gì trong compact constructor?  
**Đáp án:** Snapshot cấu trúc thành unmodifiable list, không deep-copy elements.

**Câu 15.** Có thể khai instance method `area()` trong record Rectangle không?  
**Đáp án:** Có, tính từ components.

**Câu 16.** Record được khai thêm một mutable instance field cache không?  
**Đáp án:** Không; record cấm additional instance fields.

**Câu 17.** Record có instance initializer block `{ ... }` không?  
**Đáp án:** Không; dùng constructor để validate/normalize.

**Câu 18.** Record extends một user superclass khác được không?  
**Đáp án:** Không; record extends `java.lang.Record` và implicitly final.

**Câu 19.** Record implements interface được không?  
**Đáp án:** Có.

**Câu 20.** `record Box<T>(T value)` có hợp lệ không?  
**Đáp án:** Có, record có generic type parameters.

**Câu 21.** Local record trong method có capture `final int base` trực tiếp không?  
**Đáp án:** Không; local record implicitly static, truyền base qua constructor/method param.

**Câu 22.** Member record cần Outer instance khi tạo không?  
**Đáp án:** Không; member record implicitly static.

**Câu 23.** Compact constructor tự gán fields khi nào?  
**Đáp án:** Sau compact body, từ canonical parameters theo rules.

**Câu 24.** Non-canonical constructor cần làm gì?  
**Đáp án:** Delegate bằng explicit `this(...)` tới constructor của record.

**Câu 25.** Để normalize username, nên làm đâu?  
**Đáp án:** Trong compact/normal canonical constructor, trước khi record hoàn thành.

**Câu 26.** `toString()` do record sinh có phải JSON chuẩn không?  
**Đáp án:** Không; không dùng làm wire protocol.

**Câu 27.** Record có phải mọi lúc thay thế mutable database entity không?  
**Đáp án:** Không; lifecycle/identity/proxy/mutation requirements có thể không phù hợp.

**Câu 28.** Record `Settings` “đổi theme” thế nào?  
**Đáp án:** Tạo instance mới bằng `new Settings(nextTheme, old.size())` hoặc một method `withTheme`.

**Câu 29.** Có thể để record chứa enum constant không?  
**Đáp án:** Có; tạo value composition và chia sẻ enum constants.

**Câu 30.** Vì sao record `Coordinate` khác record `Size` dù cùng hai int?  
**Đáp án:** Chúng có **named Java types riêng**, giúp tránh nhầm ý nghĩa khi gọi API.

**Câu 31.** Khi nào nên dùng Pair thay record có tên?  
**Đáp án:** Khi sự ghép cặp thật sự tổng quát, tạm thời và các tên không có domain meaning cụ thể.

**Câu 32.** Nếu JSON library yêu cầu no-arg mutable bean, record có tự đáp ứng không?  
**Đáp án:** Không; cần framework hỗ trợ record constructors hoặc adapter.

**Câu 33.** Giá trị `record Task(title,status)` có tự đóng băng một mutable Status object không?  
**Đáp án:** Không; chỉ final component reference. Với enum immutable status thì phù hợp.

**Câu 34.** Record cung cấp sẵn cái gì lớn nhất?  
**Đáp án:** Một **type-safe, named, transparent carrier of component values**, cùng generated constructor/accessors/equals/hashCode/toString.

## 39. Tài liệu tham khảo

- Java Language Specification Java SE 17, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): bản chất record, components, các hạn chế class-level.
- JLS 17, [`8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1): tên/kiểu/danh sách components.
- JLS 17, [`8.10.2 — Record Body Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.2): những members hợp lệ và hạn chế instance fields/blocks.
- JLS 17, [`8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): generated fields, accessors, Object methods.
- JLS 17, [`8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): canonical/non-canonical constructors.
- JLS 17, [`8.10.4.2 — Compact Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4.2): normalization/implicit component assignment.
- Oracle Java 17 Language Guide, [Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): giới thiệu record Java 17 và các ví dụ.
- OpenJDK [JEP 395 — Records](https://openjdk.org/jeps/395): tính năng được chuẩn hóa từ Java 16.
- JLS 17, [`14.3 — Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): local records implicitly static.
- Java API 17, [java.lang.Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): base class của records.
- Java API 17, [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable copy/snapshot semantics.
- Java API 17, [Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): input validation.
- Java API 17, [java.util.HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): equality/hash keys.
- JLS 17, [`17.5 — final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): final fields/JMM, không đồng nhất với deep immutability.

## Kết luận

**Record là công cụ Java 17 để diễn đạt một nhóm giá trị có tên, kiểu và ý nghĩa** bằng một Java class ngắn gọn. `record Point(int x,int y)` không chỉ rút gọn boilerplate: nó công bố một nhóm components rõ ràng để constructor, accessors và các Object methods hoạt động nhất quán với dữ liệu được mô tả.

Hãy dùng record khi bạn cần **value representation ổn định**, như tọa độ, khoảng giá trị, result DTO, snapshot, keys hay messages. Đặt domain invariants trong constructor, dùng methods dẫn xuất từ components và chọn immutable component types khi có thể. Với mutable arrays/lists/objects, record **không tự sao chép sâu**: cần xác định quyền sở hữu và defensive-copy đúng mức.

Cuối cùng, phân biệt record với mutable entity: records implicitly final, không có additional instance fields hoặc setters cho components. Nếu cần identity/lifecycle mutable phức tạp, normal class có thể phù hợp hơn. Thiết kế tốt nhất là **đặt tên đúng cho nhóm giá trị**, khai báo rõ các components, và bảo đảm equality/immutability đúng hợp đồng mà người dùng API mong đợi.
