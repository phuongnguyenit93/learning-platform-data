# Header, thành phần và thân khai báo `record` (Java hiện đại)

## 1. Mục tiêu và phạm vi áp dụng

`record` là một dạng lớp trong Java dùng để biểu diễn **một tập giá trị dữ liệu có cấu trúc cố định**. Thay vì tự viết các trường, constructor, accessor, `equals`, `hashCode` và `toString` lặp đi lặp lại, ta khai báo những **thành phần dữ liệu** (record components) ngay trong **header**, rồi chỉ viết phần logic cần thiết trong **body**.

Cấu trúc mà bài này tập trung là:

~~~java
record TenRecord(Kieu1 thanhPhan1, Kieu2 thanhPhan2) {
    // Các khai báo trong body nếu cần.
}
~~~

Trong Java 14, records được giới thiệu ở dạng **preview**; tính năng được chuẩn hóa chính thức từ **Java 16 (JEP 395)** và vẫn được sử dụng trên các JDK hiện đại. Các ví dụ dưới đây sử dụng **cú pháp ổn định Java 17+**, không cần và không hướng dẫn dùng `--enable-preview`. Bài học chỉ trình bày những quy tắc còn giá trị trong Java hiện hành.

Học xong, bạn có thể:

- Đọc và viết đúng **tên record, tham số kiểu tùy chọn, header, danh sách components, `implements` và body**.
- Giải thích mỗi component trong header được Java liên kết với trường `private final`, accessor `public` và tham số của canonical constructor ra sao.
- Phân biệt member Java tự sinh với khai báo được phép viết trong body: constructor, instance method, static member, type lồng nhau.
- Chọn constructor thông thường hay **compact canonical constructor** để kiểm tra/chỉnh chuẩn dữ liệu.
- Nhận diện giới hạn của record: không tự thêm instance field, không có instance initializer, không kế thừa lớp tùy ý, và **chỉ bất biến ở mức tham chiếu (shallow immutability)**.

## 2. Cấu trúc đầy đủ: record declaration

Dạng tổng quát:

~~~java
[modifiers] record TenRecord<T...>(DanhSachComponent) implements GiaoDien1, GiaoDien2 {
    // Record body
}
~~~

Đây là **mẫu ngữ pháp minh họa**, không phải đoạn Java độc lập để biên dịch. Các phần cần hiểu:

| Thành phần | Vai trò | Bắt buộc? |
| --- | --- | --- |
| `record` | Khai báo một loại lớp record | Có |
| `TenRecord` | Tên kiểu, thường viết PascalCase | Có |
| `<T...>` | Tham số kiểu tổng quát, ví dụ `<T>` hoặc `<K, V>` | Không |
| `(...)` | **Record header** chứa các component, có thể để trống | Có |
| `Kieu ten` | **Record component**: tên và kiểu của một giá trị trong trạng thái record | Không bắt buộc có phần tử |
| `implements ...` | Khai báo interface mà record thực hiện | Không |
| `{ ... }` | **Record body**, có thể rỗng | Có |

Ví dụ tối giản:

~~~java
record Point(int x, int y) {}
record Marker() {}
record Pair<L, R>(L left, R right) {}
~~~

Ba khai báo trên là **các kiểu riêng biệt**, không cần đặt tất cả vào một tệp có `public` type. `Point` có hai component, `Marker` không có component nào, `Pair` là record generic có hai component với kiểu được chỉ định khi sử dụng.

Với record có component, **thứ tự trong header có ý nghĩa**:

~~~java
Point p = new Point(3, 7);  // x = 3, y = 7
int first = p.x();          // 3
int second = p.y();         // 7
~~~

`new Point(3, 7)` truyền giá trị theo thứ tự `x` rồi `y`. Java không tự nhận diện tham số bằng tên khi gọi constructor. Đổi thứ tự component sẽ thay đổi hợp đồng constructor, vì vậy cần cân nhắc khi thay đổi API.

## 3. Record header và các component

Với khai báo:

~~~java
public record Student(String id, String name, int age) {}
~~~

Phần **header** là toàn bộ `(String id, String name, int age)`. Mỗi cặp kiểu–tên là một **component**:

- `String id`: component `id` có kiểu `String`.
- `String name`: component `name` có kiểu `String`.
- `int age`: component `age` có kiểu `int`.

Đây là **mô tả trạng thái của record**, không chỉ là danh sách tham số của một constructor viết bằng tay. Từ header, Java cung cấp các member tương ứng:

| Khai báo thành phần | Member hoặc hành vi tương ứng |
| --- | --- |
| `String id` | Trường `private final String id` và accessor `public String id()` |
| `String name` | Trường `private final String name` và accessor `public String name()` |
| `int age` | Trường `private final int age` và accessor `public int age()` |
| Cả header | Canonical constructor nhận `(String id, String name, int age)` đúng thứ tự |
| Cả tập component | Các triển khai `equals(Object)`, `hashCode()`, `toString()` khi không được khai báo tường minh |

Những member trên là **mô hình tương đương để hiểu**, không phải mã cần chép vào body; trình biên dịch tạo phần thích hợp. Đặc biệt:

1. Accessor có tên **trùng component**, ví dụ `student.id()`, **không phải** `getId()` mặc định.
2. Component field là `private final`; mã ngoài record **không** đọc được `student.id` hay gán `student.age = 19`.
3. Với record `public`, accessor của component là `public`. Constructor chuẩn tắc (canonical constructor) phải có mức truy cập ít nhất bằng record.
4. `equals`, `hashCode` và `toString` mặc định dựa trên các component; record phù hợp với trường hợp muốn mô hình hóa giá trị hơn là danh tính đối tượng.
5. **Tên, kiểu và thứ tự** component là phần quan trọng trong hợp đồng công khai của record.

### 3.1. Kiểu component và khai báo nâng cao

Component cần khai báo kiểu cụ thể; có thể dùng kiểu nguyên thủy (`int`, `long`), kiểu tham chiếu (`String`), generic (`List<String>`), kiểu tham số (`T`) hoặc mảng. Có thể khai báo annotation áp dụng phù hợp lên component, ví dụ dùng annotation validation từ thư viện mà dự án thực sự sử dụng; bản thân `record` không tự thực thi validation.

Java cũng cho phép **varargs component ở vị trí cuối**, ví dụ `record Batch(String name, int... ids) {}`. Tuy nhiên, varargs dùng **mảng**, dẫn tới rủi ro tham chiếu mutable; cần chủ động bảo vệ dữ liệu nếu yêu cầu bất biến. Với ví dụ học tập và mô hình dữ liệu mới, chỉ cần chọn kiểu component rõ ràng trước; không cần thêm varargs khi không có nhu cầu.

### 3.2. Header khác body thế nào?

~~~java
record Rectangle(int width, int height) {   // HEADER: width, height
    int area() {                            // BODY: instance method
        return width * height;
    }
}
~~~

`width` và `height` thuộc **header** và mô tả dữ liệu record. Phương thức `area()` thuộc **body**, sử dụng các giá trị sẵn có để tính toán. `area` **không phải record component** và sẽ không trở thành trường lưu trữ mới hay phần tử bổ sung trong canonical constructor.

## 4. Record body được phép khai báo những gì?

Record body nằm giữa `{` và `}`, có thể để trống. Khi cần hành vi, bạn có thể thêm:

- **Compact canonical constructor** để kiểm tra, chuẩn hóa và bảo vệ dữ liệu component.
- **Normal canonical constructor** với danh sách tham số trùng header; hoặc **constructor bổ sung** với tham số khác, miễn tuân theo luật ủy quyền constructor.
- **Instance methods**, ví dụ `area()`, `displayName()` hoặc `withTitle(...)`.
- **Static fields/methods**, hằng số, static initializer và kiểu lồng nhau.
- Khai báo tường minh accessor hoặc `equals`/`hashCode`/`toString` khi có lý do thực sự và vẫn duy trì đúng hợp đồng giá trị.

Body **không được** khai báo thêm instance field của riêng record (ví dụ `private int counter;`), không có instance initializer `{ ... }`, và không thể thay thế cơ chế lưu giữ component bằng mutable instance state. Các phương thức `abstract` hoặc `native` cũng không được khai báo trong body.

Ví dụ về method và static field hợp lệ:

~~~java
record Product(String sku, long cents) {
    private static final String CURRENCY = "VND";

    String priceLabel() {
        return cents + " " + CURRENCY;
    }

    Product withPrice(long newCents) {
        return new Product(sku, newCents);
    }
}
~~~

`priceLabel()` là logic trên dữ liệu `sku`/`cents`; `withPrice(...)` tạo **record mới**, không thay đổi record hiện tại. `CURRENCY` là thành viên `static`, không phải trạng thái riêng của từng bản ghi và không được tính như component của `equals`.

### 4.1. Record vẫn là một lớp Java

Record ngầm kế thừa `java.lang.Record` và **ngầm là `final`**. Vì vậy không thể khai báo `record A(...) extends SomeClass` và không thể tạo lớp con của một record. Tuy nhiên, record **được phép implements interface**, như `record Entry(...) implements Comparable<Entry>` nếu có triển khai phương thức phù hợp.

Record có thể là top-level type, member type hoặc local type. **Record lồng nhau mặc nhiên là `static`**; điều này hữu ích khi đặt record mô tả dữ liệu bên trong một lớp sử dụng nó.

## 5. Ví dụ chạy được: header, components, body và constructor

Lưu nguyên chương trình sau vào tệp **`RecordStructureDemo.java`**. Mã dùng các tính năng ổn định có trong Java 17, gồm record generic, body methods, compact constructor, constructor bổ sung và kiểm tra `Class.isRecord()`.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class RecordStructureDemo {
    interface Named {
        String displayName();
    }

    public record Course(String code, String title, List<String> tags)
            implements Named {
        private static final String PREFIX = "COURSE";

        public Course {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(title, "title");
            Objects.requireNonNull(tags, "tags");

            code = code.strip().toUpperCase(Locale.ROOT);
            title = title.strip();
            if (code.isBlank() || title.isBlank()) {
                throw new IllegalArgumentException("code/title cannot be blank");
            }
            tags = List.copyOf(tags);
        }

        public Course(String code, String title) {
            this(code, title, List.of());
        }

        @Override
        public String displayName() {
            return PREFIX + ": " + code + " - " + title;
        }

        public Course withTitle(String newTitle) {
            return new Course(code, newTitle, tags);
        }
    }

    public record Pair<L, R>(L left, R right) {
    }

    public static void main(String[] args) {
        List<String> originalTags = new ArrayList<>(List.of("core", "java"));
        Course course = new Course(" java14 ", "  Record syntax  ", originalTags);
        originalTags.add("added-later");

        Course same = new Course("JAVA14", "Record syntax", List.of("core", "java"));

        System.out.println("Components: " + course.code() + " | " + course.title());
        System.out.println("Tags: " + course.tags());
        System.out.println("Display: " + course.displayName());
        System.out.println("Same value: " + course.equals(same));
        System.out.println("Default tags: " + new Course("JAVA17", "Examples").tags());
        System.out.println("Copied title: " + course.withTitle("More examples").title());
        System.out.println("Pair: " + new Pair<>(3, "ok"));
        System.out.println("Is record: " + Course.class.isRecord());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 --release 17 RecordStructureDemo.java
java RecordStructureDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
Components: JAVA14 | Record syntax
Tags: [core, java]
Display: COURSE: JAVA14 - Record syntax
Same value: true
Default tags: []
Copied title: More examples
Pair: Pair[left=3, right=ok]
Is record: true
~~~

### 5.1. Giải phẫu header `Course`

~~~java
public record Course(String code, String title, List<String> tags)
        implements Named
~~~

- `Course` là **tên record**.
- `String code`, `String title`, `List<String> tags` là **ba components**, theo đúng thứ tự.
- Vì record `public`, accessor `code()`, `title()` và `tags()` là `public`.
- `implements Named` yêu cầu `Course` có phương thức `displayName()`; body đã triển khai.
- `new Course(...)` nhận ba đối số ở canonical constructor. Constructor hai đối số trong body là **overload** do chúng ta tự định nghĩa.

### 5.2. Giải phẫu body `Course`

Body định nghĩa:

- `PREFIX`: hằng `static final`, không được đưa vào header và không phải component.
- `public Course { ... }`: **compact canonical constructor**, kiểm tra và chuẩn hóa giá trị component.
- `public Course(String code, String title)`: constructor bổ sung ủy quyền sang canonical constructor bằng `this(code, title, List.of())`.
- `displayName()`: instance method triển khai giao diện `Named`.
- `withTitle(...)`: instance method trả về bản ghi `Course` mới.

Khi `originalTags` bị thêm `"added-later"` sau khi tạo record, `course.tags()` vẫn chỉ có `[core, java]` vì compact constructor đã thực hiện `List.copyOf(tags)`. `course.equals(same)` là `true` vì dữ liệu thành phần tương ứng bằng nhau, không cần hai tham chiếu là cùng một đối tượng.

### 5.3. Record generic cũng có header theo cùng nguyên tắc

~~~java
public record Pair<L, R>(L left, R right) {}
~~~

`<L, R>` là **tham số kiểu**, còn `(L left, R right)` là **header**. Trong chương trình, `new Pair<>(3, "ok")` tạo một `Pair<Integer, String>`, và `toString` mặc định in `Pair[left=3, right=ok]`.

## 6. Canonical constructor: khai báo ngầm, tường minh và compact

Mỗi record có **canonical constructor** tương ứng với kiểu, tên và thứ tự component trong header. Có ba cách thường gặp:

### 6.1. Không khai báo: compiler tạo constructor

~~~java
record Coordinate(int x, int y) {}
~~~

Khi viết `new Coordinate(1, 2)`, constructor ngầm nhận `x = 1`, `y = 2` rồi khởi tạo hai component field. Không cần viết bất kỳ câu gán nào trong body.

### 6.2. Normal canonical constructor: khai báo đầy đủ tham số

Tệp độc lập **`ValidRange.java`**:

~~~java
public record ValidRange(int min, int max) {
    public ValidRange(int min, int max) {
        if (min > max) {
            throw new IllegalArgumentException("min > max");
        }
        this.min = min;
        this.max = max;
    }
}
~~~

Ở đây `public ValidRange(int min, int max)` là canonical constructor **tường minh**, có chữ ký cùng header. Khi dùng dạng này, mã tự gán đầy đủ các component field `final` trong constructor. Đoạn mã này cũng đã được kiểm tra biên dịch với `javac --release 17`.

### 6.3. Compact canonical constructor: không lặp lại danh sách tham số

~~~java
record Positive(int value) {
    Positive {
        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
    }
}
~~~

Cú pháp `Positive { ... }` **không có `(...)`**. Java tự tạo tham số ngầm theo header và **tự khởi tạo component field sau khi thân compact constructor hoàn tất bình thường**. Bạn chỉ cần viết kiểm tra hoặc chuẩn hóa.

Có thể **gán lại tham số ngầm** để chuẩn hóa, như ví dụ `Course`:

~~~java
public Course {
    code = code.strip().toUpperCase(Locale.ROOT);
    // Compiler sẽ gán this.code = code sau khi body kết thúc bình thường.
}
~~~

Đoạn trên là **phần trích minh họa** từ constructor `Course`; khi đặt vào chương trình đầy đủ cần có đúng record declaration và import. **Không được viết `this.code = code;` bên trong compact constructor**: Java cấm gán trực tiếp component field trong thân compact constructor. Cũng không được dùng `return;` để thoát khỏi compact constructor; nếu dữ liệu không hợp lệ, ném ngoại lệ.

Một record chỉ có **một canonical constructor**. Không thể khai báo cả normal canonical constructor và compact canonical constructor cho cùng record. Constructor **bổ sung** có danh sách tham số khác phải ủy quyền sang constructor cùng record bằng `this(...)` (trực tiếp hoặc qua chuỗi constructor), để đảm bảo canonical constructor cuối cùng khởi tạo toàn bộ component.

## 7. Những giới hạn cấu trúc cần tuân thủ

| Cách viết hoặc hành động | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `record Id(String value) {}` | Có | Header định nghĩa component |
| `record Empty() {}` | Có | Header có thể rỗng |
| `record Duo<A, B>(A a, B b) {}` | Có | Record generic |
| `record Item(String name) implements Named { ... }` | Có nếu triển khai đủ interface | Record có thể thực hiện giao diện |
| `private static final int LIMIT = 10;` trong body | Có | Static field không phải trạng thái instance |
| `int length() { return name.length(); }` trong body | Có nếu `name` tồn tại | Instance method tính toán |
| `private int extra;` trong body | **Không** | Record không cho khai báo instance field mới |
| Khối instance initializer `{ ... }` trong body | **Không** | Record không cho dùng instance initializer |
| `record Child(...) extends Parent { }` | **Không** | Record không có `extends` clause |
| `abstract record Sample(...) {}` | **Không** | Record ngầm `final`, không được là `abstract` |
| `record R(int n) { R { this.n = n; } }` | **Không** | Compact constructor không được tự gán component field |

**Một nhầm lẫn thường gặp:** Record có member fields `private final` do compiler tạo **không có nghĩa** lập trình viên được tự khai báo thêm các instance field trong body. Tập instance state của record được quyết định bởi các component trong header.

### 7.1. Record giữ dữ liệu, nhưng không phải bất biến sâu

`final` ngăn gán lại **tham chiếu trường**, chứ không ngăn sửa **đối tượng mutable** mà tham chiếu đó chỉ tới. Ví dụ:

~~~java
record Basket(List<String> items) {}

List<String> items = new ArrayList<>();
items.add("A");
Basket basket = new Basket(items);
items.add("B");                // basket.items() cũng nhìn thấy "B".
basket.items().add("C");       // Có thể sửa nếu List gốc cho phép.
~~~

Đây là **đoạn minh họa** đặt trong phạm vi có import `List`, `ArrayList`. `Basket` không tự sao chép danh sách. Vì vậy việc sử dụng record **không tự động** đem lại bất biến sâu.

Nếu muốn chặn sửa danh sách được lưu, hãy làm như `Course`: kiểm tra đầu vào và dùng `List.copyOf(items)` trong compact constructor. `List.copyOf` tạo danh sách không thể thay đổi bằng thao tác `add/remove` và không giữ nguyên một danh sách mutable đầu vào; tuy nhiên các **phần tử đối tượng** trong danh sách vẫn có thể mutable. Mảng và đối tượng lồng nhau cũng cần cơ chế sao chép/bảo vệ tương ứng, kể cả khi truy cập qua accessor.

### 7.2. Nên giữ record đại diện đúng cho dữ liệu đã công bố

Record được thiết kế như **bộ mang dữ liệu minh bạch** (transparent data carrier). Nếu khai báo accessor riêng, hãy cân nhắc quy ước: tạo lại record từ tất cả accessor của một instance cần giữ quan hệ bằng nhau về dữ liệu theo hợp đồng record. Nếu ghi đè `equals`, `hashCode` hay `toString`, phải hiểu và duy trì nhất quán ngữ nghĩa giá trị; không nên thay đổi tùy tiện chỉ để có cách trình bày khác. Những thao tác dạng `withX(...)` trả về record mới thường rõ ràng hơn nhu cầu thêm setter.

## 8. Khi nào nên đặt dữ liệu trong header, khi nào trong body?

Hãy hỏi: **“Thông tin này có phải là một phần của trạng thái giá trị công khai và tham gia định danh giá trị của bản ghi không?”**

| Nhu cầu | Đặt ở đâu? | Ví dụ |
| --- | --- | --- |
| Mã và tiêu đề của một khóa học | Header | `record Course(String code, String title)` |
| Danh sách tag là dữ liệu của khóa học | Header | `List<String> tags` |
| Chuẩn hóa mã khóa học khi xây dựng đối tượng | Body, canonical constructor | `code = code.strip().toUpperCase(...)` |
| Tính chuỗi hiển thị từ các component | Body, instance method | `displayName()` |
| Tạo bản mới với tiêu đề thay đổi | Body, instance method | `withTitle(String title)` |
| Hằng số dùng chung cho mọi đối tượng | Body, static field | `static final String PREFIX` |
| Trạng thái instance ẩn và có thể tăng/giảm độc lập | Không phù hợp cho record | Chọn class thông thường khi cần mô hình trạng thái thay đổi |

**Nguyên tắc:** Header khai báo **dữ liệu cấu thành**, body mô tả **cách khởi tạo và hành vi**. Đừng đưa giá trị tính được như `area()` vào header nếu nó luôn được suy ra từ các component khác; tránh tạo thêm thành phần dư thừa có thể không đồng bộ với nguồn.

## 9. Lỗi hay gặp và hướng sửa

### Lỗi 1 — Nhầm accessor với JavaBean getter

~~~java
record User(String username) {}
// new User("mai").getUsername(); // Sai nếu không tự khai báo getUsername().
String value = new User("mai").username();  // Đúng.
~~~

Record tự cung cấp `username()`; không tự sinh `getUsername()`.

### Lỗi 2 — Cố thay đổi component sau khi khởi tạo

~~~java
record Point(int x, int y) {}
// Point p = new Point(1, 2);
// p.x = 9; // Sai: field private và final.
~~~

Nếu cần giá trị mới, tạo `new Point(9, p.y())` hoặc định nghĩa phương thức trả bản ghi mới.

### Lỗi 3 — Thêm instance field vào body

~~~java
// Không hợp lệ:
record User(String name) {
    // private int loginCount; // Lỗi biên dịch nếu bỏ comment.
}
~~~

Nếu `loginCount` là trạng thái dữ liệu của record, thêm `int loginCount` vào header và chấp nhận nó trở thành component. Nếu bộ đếm thay đổi liên tục trong vòng đời đối tượng, cân nhắc dùng **class thường**.

### Lỗi 4 — Nhầm compact constructor với normal constructor

~~~java
record Age(int years) {
    Age {
        if (years < 0) throw new IllegalArgumentException("negative age");
    }
}
~~~

Trong compact constructor, không ghi lại `Age(int years)` và không tự gán `this.years`. Nếu muốn viết đầy đủ tham số/field, dùng **normal canonical constructor** và tự khởi tạo các fields.

### Lỗi 5 — Quên bất biến nông

`record Data(byte[] payload) {}` chỉ lưu tham chiếu tới mảng. Bên gọi có thể sửa phần tử của mảng. Để bảo vệ trạng thái, cần **sao chép mảng khi nhận vào và khi trả ra** (nếu accessor cho phép đọc mảng); với danh sách, dùng collection snapshot phù hợp như `List.copyOf` và cân nhắc mutability của các phần tử.

### Lỗi 6 — Dùng sai phiên bản biên dịch

Khai báo record hiện đại đã chính thức từ Java 16. Nếu biên dịch bằng `--release 14`, record chỉ tồn tại trong giai đoạn preview lịch sử nên không thể dùng như cú pháp thông thường. Với các ví dụ ổn định của bài này, dùng JDK 17+ và `--release 17` hoặc một phiên bản Java mới hơn được dự án hỗ trợ.

## 10. Bài tập thực hành

Viết một record `Score(String subject, int points)` theo yêu cầu:

1. Header có đúng hai component: tên môn `String subject` và điểm `int points`.
2. Compact constructor từ chối `subject == null`, tên rỗng sau `strip()` hoặc điểm không nằm trong khoảng `0..100`.
3. Chuẩn hóa `subject` bằng `strip()`.
4. Body thêm phương thức `boolean passed()` trả `true` khi điểm từ `50` trở lên.
5. Không thêm instance field.

**Lời giải tham khảo** (đặt trong tệp `Score.java`):

~~~java
import java.util.Objects;

public record Score(String subject, int points) {
    public Score {
        Objects.requireNonNull(subject, "subject");
        subject = subject.strip();
        if (subject.isEmpty()) {
            throw new IllegalArgumentException("subject is blank");
        }
        if (points < 0 || points > 100) {
            throw new IllegalArgumentException("points out of range");
        }
    }

    public boolean passed() {
        return points >= 50;
    }
}
~~~

Kiểm tra bằng cách tạo `new Score(" Java ", 90)`, gọi `subject()` và `passed()`: kết quả lần lượt là `"Java"` và `true`. `new Score("", 80)` và `new Score("Java", 120)` đều ném `IllegalArgumentException`. Bài tập cho thấy **header** định nghĩa dữ liệu, **constructor** ràng buộc dữ liệu, **body method** biểu diễn hành vi.

## 11. Ghi nhớ trọng tâm

- Cú pháp nền tảng: `record Name(ComponentType name, ...) { body }`; có thể thêm generic và `implements` nếu cần.
- Header xác định **component list**, thứ tự tham số của canonical constructor, component fields và accessors; body chỉ bổ sung validation, normalization, methods và các member Java cho phép.
- Java tạo accessor cùng tên component (`name()`), component fields `private final` và các phương thức giá trị thông dụng (`equals`/`hashCode`/`toString`).
- Compact canonical constructor là lựa chọn ngắn gọn cho validation/normalization; constructor overload phải ủy quyền để cuối cùng khởi tạo đúng toàn bộ component.
- Record ngầm `final`, kế thừa `java.lang.Record`, không có instance field ngoài header, không có instance initializer; reference `final` **không bảo đảm bất biến sâu**.
- Những quy tắc trong bài đã là tính năng **chính thức từ Java 16**, dùng ổn định trong Java 17 và các phiên bản mới hơn.

**Tài liệu chính thức để đọc sâu hơn:**
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): thiết kế và quá trình record trở thành tính năng chính thức từ Java 16.
- [Oracle Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): hướng dẫn viết record, component và constructor.
- [Java Language Specification SE 25, `8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10): quy tắc chuẩn cho header, components, body, members và constructors.
