# Trường `private final` và accessor tương ứng trong Java `record`

## 1. Mục tiêu và quy tắc cốt lõi

Một `record` khai báo dữ liệu cốt lõi ngay trên **record header** (danh sách *record components*). Với **mỗi component**, Java bảo đảm có hai thành viên tương ứng:

1. **Một trường (component field) kiểu `private final`**, cùng **tên** và **kiểu** với component, lưu dữ liệu của đối tượng.
2. **Một phương thức accessor kiểu `public`**, cùng **tên** với component, **không có tham số**, và có **kiểu trả về đúng bằng kiểu component**. Nếu không tự khai báo, trình biên dịch tạo accessor trả về giá trị của trường tương ứng.

Ví dụ:

```java
public record Person(String name, int age) {}
```

Record có hai component `name` và `age`. Ở mức khái niệm, chúng tương ứng với:

| Component trong header | Trường lưu dữ liệu | Accessor công khai |
| --- | --- | --- |
| `String name` | `private final String name;` | `public String name()` |
| `int age` | `private final int age;` | `public int age()` |

**Lưu ý:** Bảng thể hiện các thành viên Java tự cung cấp; **không chép thêm các khai báo trường này vào thân record**. Chúng đã tồn tại một cách ngầm định, và record không cho phép khai báo thêm trường instance riêng.

`record` đã là tính năng ngôn ngữ chính thức từ **Java 16**. Các quy tắc về trường `private final` và accessor ở đây vẫn áp dụng cho **Java 17, 21 và Java hiện đại**. Ví dụ chạy trong bài dùng `javac --release 17`, không cần chế độ preview hoặc cú pháp thử nghiệm.

## 2. Record header tạo những gì?

Xét record đơn giản:

```java
public record OrderLine(String productCode, int quantity) {}
```

Trình biên dịch bảo đảm record này có:

- Trường instance `private final String productCode` và `private final int quantity`.
- Phương thức `public String productCode()` và `public int quantity()`; **không tự sinh** `getProductCode()`, `getQuantity()`.
- **Canonical constructor** nhận `(String productCode, int quantity)` và khởi tạo hai trường; nếu không khai báo constructor riêng, trình biên dịch cung cấp constructor này.
- Các triển khai `equals(Object)`, `hashCode()`, `toString()` dựa trên các component, trừ khi khai báo lại phù hợp.

Đây là đoạn **minh họa ý nghĩa** hai trường và hai accessor, không phải mã phải chép vào thân record:

```java
// Minh họa cơ chế của OrderLine, KHÔNG chép vào thân record:
private final String productCode;
private final int quantity;

public String productCode() {
    return productCode;
}

public int quantity() {
    return quantity;
}
```

Hai trường đã do record cung cấp; lập trình viên bình thường chỉ cần viết record header. Record cũng là lớp **ngầm định final**, không thể có lớp con kế thừa record đó; kế thừa trực tiếp từ `java.lang.Record` được ngôn ngữ quản lý.

Ví dụ sử dụng (đoạn mã trong một phương thức):

```java
OrderLine item = new OrderLine("BOOK-01", 3);
System.out.println(item.productCode()); // BOOK-01
System.out.println(item.quantity());    // 3
```

## 3. Ý nghĩa chính xác của `private` và `final`

### 3.1. `private`: thành viên lưu dữ liệu được đóng gói

**Component field** là `private`, không trở thành trường `public` chỉ vì tên component được viết trong header. Mã ở bên ngoài không có quyền truy cập trực tiếp trường instance của record như một thành viên công khai.

```java
// File OrderLine.java
public record OrderLine(String productCode, int quantity) {}

// Đoạn mã ở một lớp độc lập:
OrderLine item = new OrderLine("BOOK-01", 3);

String code = item.productCode(); // ĐÚNG: accessor public
// String wrong = item.productCode; // SAI ở lớp độc lập: field private
```

Bên trong chính record, các phương thức có thể đọc trường bằng `productCode` hoặc `this.productCode`. Trường `private` vẫn tuân theo quy tắc truy cập thành viên của Java, bao gồm các quy tắc truy cập giữa các lớp cùng một *nest*; cách dùng từ API bên ngoài vẫn là accessor.

### 3.2. `final`: không được gán lại trường sau khi khởi tạo

Sau khi canonical constructor hoàn tất, một component field không thể được gán một giá trị mới:

```java
public record Score(int points) {
    // Minh họa lỗi: không viết phương thức sau trong record
    // public void setPoints(int value) {
    //     this.points = value; // LỖI: không được gán lại final field
    // }
}
```

Java không sinh setter cho các component. Nếu cần “thay đổi” một giá trị, có thể tạo **bản record mới**:

```java
Score oldScore = new Score(10);
Score newScore = new Score(20);
System.out.println(oldScore.points()); // 10
System.out.println(newScore.points()); // 20
```

### 3.3. `final` không đồng nghĩa bất biến sâu

Khi component là kiểu tham chiếu, `final` cố định **tham chiếu của trường**, không nhất thiết cố định dữ liệu bên trong đối tượng được tham chiếu.

```java
record Tags(java.util.List<String> values) {}

java.util.ArrayList<String> mutable = new java.util.ArrayList<>();
mutable.add("java");
Tags tags = new Tags(mutable);
mutable.add("record");
System.out.println(tags.values()); // [java, record]
```

Trường `values` vẫn là `private final`; kết quả thay đổi vì **cùng một `ArrayList` có thể sửa nội dung**. Accessor ngầm định mặc định trả đúng tham chiếu component, không tự tạo bản sao.

Với dữ liệu cần bất biến ổn định, **phải chủ động phòng vệ** ở constructor và/hoặc accessor tùy kiểu dữ liệu; phần 5 minh họa với `List.copyOf` và mảng `byte[]`. Record thường được mô tả là *shallowly immutable* (bất biến nông), không mặc định bất biến sâu.

## 4. Quy tắc của accessor tương ứng

Với `record Product(String sku, int quantity)`, chữ ký accessor tương ứng phải là:

```java
public String sku()
public int quantity()
```

Các thuộc tính bắt buộc của accessor record:

| Thuộc tính | Quy tắc |
| --- | --- |
| Tên | **Đúng bằng tên component**, ví dụ `sku()` |
| Tham số | **Không có tham số** |
| Kiểu trả về | **Đúng bằng kiểu component**, không thay tùy ý bằng kiểu khác |
| Quyền truy cập | Phải `public` |
| Loại phương thức | Phương thức instance, **không `static`** |
| Generic | Không tự khai báo tham số kiểu generic trên chính accessor |
| `throws` | **Không được có mệnh đề `throws`** trong khai báo accessor |
| Mặc định | Nếu không tự khai báo, Java sinh method trả về trường tương ứng |

**Đừng nhầm accessor với JavaBeans getter:** `product.sku()` là accessor chuẩn của record; `product.getSku()` **không được tự động sinh**. Có thể tự viết phương thức `getSku()` bổ sung nếu thực sự cần, nhưng đó là một phương thức bình thường và **không thay thế** accessor bắt buộc `sku()`.

### 4.1. Khai báo accessor tường minh

Có thể viết accessor trực tiếp trong thân record, ví dụ:

```java
public record Product(String sku, int quantity) {
    @Override
    public String sku() {
        return sku; // Trả giá trị của private final field
    }
}
```

Ví dụ này hợp lệ, nhưng với `String` bất biến nó **không thêm lợi ích thực tế** so với accessor ngầm định. Nên để trình biên dịch tạo accessor trừ khi có nhu cầu rõ ràng như tạo bản sao phòng vệ.

Không được đổi kiểu, quyền truy cập hoặc thêm `throws`:

```java
// CỐ Ý SAI: minh họa, không phải lớp chạy được
record BadAccessor(String name) {
    // private String name() { return name; }
    // LỖI: accessor phải public

    // public Object name() { return name; }
    // LỖI: phải trả đúng String, không thay bằng Object

    // public String name() throws java.io.IOException { return name; }
    // LỖI: accessor không được có throws clause
}
```

Các dòng sai đã được chú thích để đoạn minh họa không tự gây lỗi; nếu bỏ chú thích từng dòng, trình biên dịch sẽ từ chối. Một accessor tường minh phải bảo toàn ý nghĩa component; tránh tự ý biến `sku()` thành kết quả không phản ánh đúng trạng thái thành viên lưu trữ.

### 4.2. Trường hợp cần thêm phương thức khác

Record vẫn có thể khai báo phương thức instance riêng (không phải accessor), phương thức `static` và trường `static`:

```java
public record Rectangle(double width, double height) {
    public static final String UNIT = "cm"; // HỢP LỆ: static field

    public double area() {
        return width * height; // Đọc private final component fields
    }
}
```

Nhưng không thể thêm trường instance như `private int cachedArea;`. Nếu cần thêm trạng thái là một phần dữ liệu của đối tượng, cân nhắc đưa vào header như component (nếu đúng mô hình dữ liệu), tính từ component khi cần, hoặc sử dụng một lớp thường.

## 5. Constructor khởi tạo component field như thế nào?

Mỗi record có **canonical constructor** với danh sách tham số tương ứng danh sách component. Nếu không viết constructor, Java cấp constructor phù hợp và gán các tham số vào trường `private final` tương ứng.

Khi cần kiểm tra hoặc chuẩn hóa dữ liệu, có thể dùng **compact constructor**. Ví dụ:

```java
public record Person(String name, int age) {
    public Person {
        java.util.Objects.requireNonNull(name, "name");
        name = name.trim();
        if (name.isBlank()) {
            throw new IllegalArgumentException("blank name");
        }
        if (age < 0) {
            throw new IllegalArgumentException("negative age");
        }
    }
}
```

Trong compact constructor:

1. Các tên `name`, `age` trong thân constructor là **tham số ngầm định**, vì vậy có thể gán lại `name = name.trim();` để chuẩn hóa **tham số**.
2. Sau khi thân compact constructor hoàn thành bình thường, Java **tự gán** giá trị các tham số đã chuẩn hóa vào component fields tương ứng.
3. Không tự gán `this.name = name;` hoặc `this.age = age;` trong compact constructor; điều đó không hợp lệ vì việc khởi tạo trường do ngôn ngữ bảo đảm ở cuối compact constructor.
4. Khi object đã tạo xong, các trường `private final` đã có giá trị và không thể gán lại.

Do vậy, `name = name.trim()` trong constructor **không mâu thuẫn** với `private final String name`: phép gán tác động lên **tham số trước khi field được khởi tạo**, không sửa field của object đã khởi tạo.

## 6. Chương trình Java 17+ độc lập, đã kiểm tra biên dịch và kết quả

Lưu tệp với tên chính xác **`RecordMembersDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class RecordMembersDemo {
    public record Person(String name, int age) {
        public Person {
            Objects.requireNonNull(name, "name");
            name = name.trim();
            if (name.isBlank()) throw new IllegalArgumentException("blank name");
            if (age < 0) throw new IllegalArgumentException("negative age");
        }
    }

    public record Course(String code, List<String> topics) {
        public Course {
            Objects.requireNonNull(code, "code");
            topics = List.copyOf(topics);
        }
    }

    public record BinaryData(byte[] bytes) {
        public BinaryData {
            bytes = Objects.requireNonNull(bytes, "bytes").clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BinaryData data
                    && Arrays.equals(bytes, data.bytes);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(bytes);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Person person = new Person("  An  ", 23);
        System.out.println(person.name() + " / " + person.age());
        System.out.println(person);

        Field field = Person.class.getDeclaredField("name");
        System.out.println(Modifier.isPrivate(field.getModifiers())
                + " / " + Modifier.isFinal(field.getModifiers()));

        var component = Person.class.getRecordComponents()[0];
        System.out.println(component.getName() + " -> "
                + component.getAccessor().getName() + "()");

        ArrayList<String> input = new ArrayList<>(List.of("records"));
        Course course = new Course("J17", input);
        input.add("changed");
        System.out.println(course.topics());
        try {
            course.topics().add("more");
        } catch (UnsupportedOperationException ex) {
            System.out.println("List is unmodifiable");
        }

        byte[] raw = {1, 2, 3};
        BinaryData data = new BinaryData(raw);
        raw[0] = 9;
        byte[] returned = data.bytes();
        returned[1] = 8;
        System.out.println(Arrays.toString(data.bytes()));
        System.out.println(data.equals(new BinaryData(new byte[] {1, 2, 3})));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp (JDK 17 trở lên):

```bash
javac --release 17 RecordMembersDemo.java
java RecordMembersDemo
```

Kết quả chính xác:

```text
An / 23
Person[name=An, age=23]
true / true
name -> name()
[records]
List is unmodifiable
[1, 2, 3]
true
```

### Giải thích kết quả

**Các dòng 1–2:** `Person` chuẩn hóa tên trong compact constructor; `person.name()` và `person.age()` là accessor. `toString()` mặc định liệt kê tên và giá trị các component.

**Dòng 3:** Reflection qua `Person.class.getDeclaredField("name")` cho thấy component field `name` thực sự có modifier `private` và `final`. Đây là minh chứng runtime về hợp đồng ngôn ngữ, không phải lý do để truy cập trực tiếp dữ liệu từ ứng dụng thay vì accessor.

**Dòng 4:** `Person.class.getRecordComponents()[0]` lấy component đầu tiên. `getAccessor().getName()` cho `name`, xác nhận accessor có cùng tên component và được gọi dạng `name()`.

**Dòng 5:** `Course` dùng `List.copyOf(topics)` trong compact constructor. Việc thêm `"changed"` vào `input` ban đầu không thay đổi danh sách mà record giữ. Cơ chế này tạo **danh sách không sửa được**, phù hợp khi `String` bên trong cũng bất biến.

**Dòng 6:** Accessor ngầm định của `Course` trả danh sách đã không cho sửa; gọi `add` qua accessor ném `UnsupportedOperationException`. `List.copyOf` chỉ sao chép **nông**: nếu phần tử của list là object có thể thay đổi, vẫn cần cân nhắc phòng vệ ở cấp phần tử.

**Dòng 7:** `BinaryData` có component `byte[]`. Constructor tạo bản sao lúc nhận dữ liệu; accessor tường minh `bytes()` trả **bản sao mới** mỗi lần gọi, nên sửa mảng đầu vào hay mảng nhận về đều không sửa dữ liệu nội bộ.

**Dòng 8:** `equals` tường minh so sánh **nội dung mảng** bằng `Arrays.equals`, còn `hashCode` dùng `Arrays.hashCode` tương ứng. Điều này cần thiết vì record có component kiểu mảng sẽ mặc định so sánh các tham chiếu mảng khi dùng `equals` sinh tự động, chứ không tự so sánh từng phần tử. Các phương thức phải bảo toàn hợp đồng `equals`/`hashCode` và bất biến bản sao của record.

Phần này đồng thời minh họa ba trường hợp: accessor ngầm định cho immutable component, accessor ngầm định sau khi chuẩn hóa/copy component, và accessor tường minh để phòng vệ kiểu mutable.

## 7. Các lỗi thường gặp về trường và accessor

### Lỗi 1 — Khai báo lại component field trong thân record

```java
// CỐ Ý SAI — mã này sẽ không biên dịch:
record BadFields(int value) {
    private final int value = 0;
}
```

Record đã có trường `private final int value` ngầm định. Khai báo thêm trường instance trong thân record là lỗi, dù trùng tên hay dùng tên khác:

```java
// CỐ Ý SAI — mã này cũng không biên dịch:
record BadFields2(int value) {
    private final int extra = 1;
}
```

Cách sửa: bỏ các khai báo trường instance. Nếu cần dữ liệu dẫn xuất, dùng phương thức tính từ component hoặc cân nhắc loại lớp phù hợp.

### Lỗi 2 — Tưởng accessor có tên `getName()`

```java
record User(String name) {}

User user = new User("Lan");
System.out.println(user.name()); // ĐÚNG
// System.out.println(user.getName()); // LỖI nếu không tự khai báo getName()
```

Accessor sinh tự động có **chính xác tên component**; Java không tự thêm tiền tố `get`/`is` theo quy ước JavaBeans. Nếu tích hợp một framework cần quy ước getter cũ, hãy xem hỗ trợ record của framework hoặc khai báo phương thức bổ sung phù hợp thay vì giả định method tồn tại.

### Lỗi 3 — Viết accessor không đúng chữ ký

```java
// CỐ Ý SAI — mỗi trường hợp minh họa một kiểu lỗi:
record BadAccessor(String name) {
    public String name() throws java.io.IOException {
        return name;
    }
}
```

Java từ chối mệnh đề `throws` của accessor; compiler có thể báo `invalid accessor method in record` và `throws clause not allowed for accessor method`. Các biến thể `private String name()`, `public Object name()` hoặc `public static String name()` cũng không hợp lệ khi dùng làm accessor của component `String name`.

Cách sửa: giữ `public String name()`, không tham số, không `throws`, không `static`, hoặc bỏ hẳn accessor tường minh để Java tự sinh.

### Lỗi 4 — Gán lại trường `final` trong setter

```java
// CỐ Ý SAI — không viết phương thức này trong record:
public void rename(String newName) {
    this.name = newName; // LỖI: final component field
}
```

Thay vào đó, tạo record mới khi muốn thay đổi component:

```java
record User(String name) {}

User original = new User("Lan");
User renamed = new User("Minh");
```

### Lỗi 5 — Xem `final` là bất biến sâu

Ví dụ `record Bytes(byte[] bytes) {}` không tự chặn mã bên ngoài sửa mảng đầu vào hoặc mảng trả từ `bytes()`. Accessor ngầm định trả về **cùng tham chiếu mảng**. Chỉ `private final` không đủ bảo vệ nội dung.

Cách sửa: dùng kiểu component bất biến thực sự (nếu phù hợp), hoặc bảo vệ ở **cả hai hướng**: sao chép dữ liệu đầu vào trong constructor và sao chép dữ liệu khi accessor trả về. Với component mảng, nếu mong muốn so sánh giá trị, cần xem xét tự triển khai `equals`/`hashCode` theo nội dung (như ví dụ `BinaryData`).

### Lỗi 6 — Viết accessor gọi chính nó

```java
// CỐ Ý SAI VỀ LOGIC — có thể gây StackOverflowError khi gọi:
record Person(String name) {
    @Override
    public String name() {
        return name(); // Đệ quy vô hạn; không đọc trường
    }
}
```

Cách sửa: `return name;` hoặc `return this.name;` để đọc **trường**; hoặc bỏ định nghĩa accessor tường minh. Dấu ngoặc `()` phân biệt gọi method với đọc trường.

## 8. Thực hành và câu hỏi tự kiểm tra

**Câu 1:** Với `record Point(int x, int y) {}`, những thành viên nào được bảo đảm?

**Trả lời:** Hai component fields `private final int x`, `private final int y`; hai accessors `public int x()`, `public int y()`; canonical constructor nhận `(int, int)` và các phương thức tiêu chuẩn khác của record. Không tự sinh `getX()`/`getY()`.

**Câu 2:** Từ bên ngoài record, viết `p.x = 4;` có sửa được object không?

**Trả lời:** Không. Component field là `private final`; cách tạo “giá trị mới” là tạo đối tượng record mới, ví dụ `new Point(4, p.y())`.

**Câu 3:** `public record Config(java.util.List<String> flags) {}` đã an toàn trước việc người gọi thay đổi một `ArrayList` truyền vào chưa?

**Trả lời:** Chưa. `private final` bảo vệ tham chiếu, không bảo vệ nội dung danh sách. Nếu muốn bảo vệ cấu trúc list, có thể dùng compact constructor `public Config { flags = java.util.List.copyOf(flags); }`. Với list chứa phần tử mutable, còn phải xem xét các phần tử.

**Câu 4:** Khi nào nên tự định nghĩa `public byte[] bytes()`?

**Trả lời:** Khi record lưu `byte[]` nhưng muốn tránh lộ mảng nội bộ; accessor có thể trả `bytes.clone()`. Constructor cũng phải phòng vệ đầu vào; việc so sánh/hashing mảng cần được thiết kế tương thích.

**Câu 5:** `record Employee(String name) { public String getName() { return name; } }` có hợp lệ không, và accessor chuẩn tên gì?

**Trả lời:** Hợp lệ vì `getName()` là một phương thức instance bổ sung. Accessor chuẩn vẫn là `name()`, được compiler cung cấp ngầm định nếu không khai báo trực tiếp.

## 9. Checklist áp dụng trong dự án

- [ ] Mọi component xuất hiện trong record header đều có **field `private final`** và accessor `public` cùng tên, không tham số.
- [ ] API phía gọi sử dụng `component()`; không tự giả định có `getComponent()`.
- [ ] Không thêm trường instance hoặc setter gán lại component field trong thân record.
- [ ] Dùng compact/canonical constructor để kiểm tra, chuẩn hóa hoặc copy dữ liệu đầu vào khi cần.
- [ ] Với thành phần mutable, hiểu accessor mặc định trả tham chiếu; cân nhắc sao chép phòng vệ, bất biến sâu và quy ước `equals`/`hashCode`.
- [ ] Tự khai báo accessor chỉ khi cần và giữ đúng quy tắc `public`, cùng kiểu trả về, không tham số, không `throws`.
- [ ] Kiểm tra ví dụ bằng JDK hỗ trợ record chính thức, như `javac --release 17`.

## Tài liệu chính thức còn áp dụng

1. [Java Language Specification — Java SE 26, `8.10 Record Classes và `8.10.3 Record Members](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10.3) — quy định chính thức về component field `private final` và accessor tương ứng.
2. [Oracle — Record Classes (Java 17)](https://docs.oracle.com/en/java/javase/17/language/records.html) — hướng dẫn constructor, accessor, các method sinh sẵn và giới hạn của record.
3. [Java SE 26 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html) — mô tả record như bộ mang dữ liệu bất biến nông và hợp đồng sao chép/`equals`.
