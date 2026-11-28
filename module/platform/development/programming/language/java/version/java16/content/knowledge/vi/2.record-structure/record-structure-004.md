# Các thành viên được sinh tự động từ record header

## 1. Record header tạo ra những gì?

Từ Java 16, `record` là tính năng chính thức để khai báo một lớp mang dữ liệu với cấu trúc được thể hiện trực tiếp trong header. Header không chỉ là danh sách tham số của một constructor: nó xác định các component của record và là cơ sở để Java khai báo ngầm những thành viên tương ứng.

Ví dụ:

```java
public record Point(int x, int y) {}
```

Chỉ với một dòng khai báo, kiểu `Point` đã có:

- Hai field component `private final int x` và `private final int y`.
- Một canonical constructor nhận `x` và `y` theo đúng thứ tự header.
- Hai accessor công khai `x()` và `y()`.
- Các phương thức `equals(Object)`, `hashCode()` và `toString()` dựa trên component.

Đây là các thành viên được **khai báo ngầm** (*implicitly declared*) theo quy tắc của ngôn ngữ. Trình biên dịch tạo phần triển khai cần thiết trong bytecode. Nếu lập trình viên tự khai báo một thành viên tương ứng được phép tùy biến, thành viên ngầm đó sẽ không được khai báo trùng thêm lần nữa.

Mục tiêu bài học:

- Nhận diện chính xác các field, constructor, accessor và phương thức được suy ra từ header.
- Hiểu hành vi mặc định của `equals()`, `hashCode()` và `toString()`.
- Biết khi nào có thể tự khai báo thành viên để thay đổi cách hoạt động.
- Kiểm tra cấu trúc record bằng reflection khi cần xây dựng công cụ tổng quát.
- Tránh nhầm lẫn giữa thành viên ngầm định của record và getter/setter kiểu JavaBean.

## 2. Bản đồ các thành viên được khai báo ngầm

Xét record:

```java
record Employee(String id, String name, int level) {}
```

Bảng sau tóm tắt những thành viên Java cung cấp:

| Thành viên | Hình thức tương ứng | Công dụng |
| --- | --- | --- |
| Field component | `private final String id`, `private final String name`, `private final int level` | Lưu giá trị của từng component. |
| Canonical constructor | `Employee(String id, String name, int level)` | Khởi tạo toàn bộ component theo thứ tự header. |
| Accessor | `public String id()`, `public String name()`, `public int level()` | Đọc giá trị component. |
| `equals(Object)` | `public boolean equals(Object other)` | So sánh giá trị component giữa hai record. |
| `hashCode()` | `public int hashCode()` | Tạo mã băm nhất quán với `equals()`. |
| `toString()` | `public String toString()` | Cung cấp biểu diễn dạng văn bản của record và component. |

Đây là mô tả chữ ký và vai trò để học cách ngôn ngữ hoạt động, không phải đoạn mã cần chép vào body. Với record cơ bản, Java đã cung cấp những thành viên đó. Không cần tự viết lại constructor, field, accessor hay ba phương thức `Object` chỉ để có hành vi mặc định.

### Thành viên ngầm định và thành viên tự khai báo

| Thành viên | Nếu không viết trong body | Nếu tự khai báo |
| --- | --- | --- |
| Field component | Java khai báo field `private final` tương ứng với mỗi component. | Không được khai báo field instance khác để thay thế hoặc bổ sung trạng thái record. |
| Canonical constructor | Java khai báo canonical constructor ngầm định. | Có thể viết compact canonical constructor hoặc canonical constructor đầy đủ. |
| Accessor component | Java khai báo accessor công khai cùng tên component. | Có thể viết accessor tường minh, miễn tuân thủ quy tắc của accessor. |
| `equals()`, `hashCode()`, `toString()` | Java cung cấp triển khai dựa trên component. | Có thể khai báo phương thức tương ứng để tùy chỉnh hành vi. |

Nếu record đã khai báo canonical constructor, Java không tạo thêm canonical constructor ngầm định. Tương tự, khi một accessor hoặc phương thức `Object` tương ứng được khai báo tường minh, triển khai ngầm tương ứng không được tạo trùng.

## 3. Field component: `private final`

Mỗi component trong header tương ứng với một field instance có tên và kiểu tương ứng. Field này có hai đặc điểm quan trọng:

- `private`: mã bên ngoài record không truy cập trực tiếp vào field.
- `final`: sau khi khởi tạo, không thể gán lại field sang một giá trị khác.

Ví dụ:

```java
record Account(String accountId, long balanceInCents) {}

Account account = new Account("A-100", 125_000);
System.out.println(account.accountId());
System.out.println(account.balanceInCents());
```

Mã bên ngoài không thể viết `account.accountId` để đọc field vì field là `private`; cũng không thể gán `account.accountId = "A-200"` vì field là `final` và không được truy cập trực tiếp. Cách đọc công khai là gọi accessor `account.accountId()`.

Không được khai báo thêm field instance trong body của record:

```java
// Không hợp lệ: record không cho thêm trạng thái instance ngoài component.
// record User(String name) {
//     private String cachedLabel;
// }
```

Quy tắc này giữ cho trạng thái instance được mô tả đầy đủ bởi header. Record vẫn có thể khai báo hằng số `static`, phương thức instance, phương thức `static`, kiểu lồng và các constructor hợp lệ:

```java
record Temperature(double celsius) {
    static final double ABSOLUTE_ZERO_C = -273.15;

    boolean isBelowFreezing() {
        return celsius < 0;
    }

    static Temperature absoluteZero() {
        return new Temperature(ABSOLUTE_ZERO_C);
    }
}
```

`final` của field không đồng nghĩa dữ liệu tham chiếu bên trong là bất biến sâu. Nếu component là `List`, mảng hoặc một object mutable, object đó vẫn có thể thay đổi. Hãy xem xét kiểu component và sao chép phòng vệ khi cần snapshot ổn định.

## 4. Canonical constructor được cung cấp từ header

Header:

```java
record Coordinate(int x, int y) {}
```

tạo ra canonical constructor nhận đủ hai component theo thứ tự:

```java
Coordinate(int x, int y)
```

Khi không khai báo constructor, canonical constructor ngầm định sẽ khởi tạo các field từ các tham số tương ứng:

```java
Coordinate origin = new Coordinate(0, 0);
Coordinate point = new Coordinate(15, 25);
```

Canonical constructor có cùng danh sách tham số component về tên, kiểu và thứ tự. Mức truy cập của canonical constructor ngầm định phù hợp với mức truy cập của record. Ví dụ record `public` có canonical constructor ngầm định `public`.

### Khi cần xác thực dữ liệu

Ta có thể thay canonical constructor ngầm định bằng compact canonical constructor:

```java
import java.util.Objects;

public record UserId(String value) {
    public UserId {
        value = Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
```

Compact constructor vẫn là canonical constructor của record. Java tự gán các tham số sau khi phần thân constructor hoàn tất bình thường; vì vậy không viết `this.value = value` trong dạng compact. Nếu khai báo canonical constructor đầy đủ, lập trình viên phải tự gán mọi field component.

Constructor phụ cũng có thể tồn tại, nhưng phải ủy quyền đến constructor khác của cùng record bằng `this(...)`. Như vậy, các quy tắc khởi tạo trong canonical constructor vẫn được áp dụng cho mọi cách tạo instance.

## 5. Accessor được sinh tự động

Với:

```java
record Student(String studentCode, String fullName, int score) {}
```

Java cung cấp ba accessor công khai:

```java
studentCode()
fullName()
score()
```

Accessor có tên **chính xác bằng tên component**, không tự thêm tiền tố `get`:

```java
Student student = new Student("S-01", "Lan", 90);

String code = student.studentCode();
String name = student.fullName();
int score = student.score();
```

Accessor không tham số và trả về kiểu tương ứng với component. Với component primitive, nó trả về giá trị primitive; với component kiểu tham chiếu, nó trả về tham chiếu đang được lưu trong field.

### Có thể tự khai báo accessor không?

Có. Một record có thể khai báo accessor tường minh để bổ sung hành vi như sao chép phòng vệ. Accessor tường minh phải là phương thức `public`, không tham số, có kiểu trả về tương ứng với kiểu component. Ví dụ:

```java
import java.util.Objects;

record Packet(byte[] bytes) {
    Packet {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }
}
```

Constructor sao chép mảng đầu vào; accessor sao chép mảng đầu ra. Nhờ vậy, người gọi không thể sửa trực tiếp mảng nội bộ qua tham chiếu đầu vào hoặc tham chiếu trả về. Accessor tường minh thay thế accessor ngầm định cho component `bytes`.

Không cần và không nên gắn `@Override` cho accessor này: accessor component không override một phương thức đã khai báo trong `java.lang.Record` hay `Object`.

Lưu ý: ví dụ trên chỉ bảo vệ việc truy cập mảng. `equals()` và `hashCode()` mặc định của record vẫn sử dụng ngữ nghĩa bình đẳng của kiểu mảng Java, tức là so sánh tham chiếu mảng, không so sánh nội dung từng phần tử. Nếu cần bình đẳng theo nội dung, phải thiết kế thêm `equals()` và `hashCode()` nhất quán hoặc chọn kiểu component khác.

## 6. `equals()` được sinh từ các component

Nếu không tự khai báo `equals(Object)`, record có triển khai mặc định so sánh theo **giá trị component**. Hai instance của cùng kiểu record được xem là bằng nhau khi các component tương ứng bằng nhau theo ngữ nghĩa của kiểu component.

```java
record Point(int x, int y) {}

Point first = new Point(3, 7);
Point second = new Point(3, 7);
Point third = new Point(3, 8);

System.out.println(first == second);       // false
System.out.println(first.equals(second));  // true
System.out.println(first.equals(third));   // false
```

`==` kiểm tra hai biến có tham chiếu đến cùng một object hay không. `equals()` do record cung cấp kiểm tra bình đẳng giá trị của record. Hai instance `first` và `second` là hai object khác nhau nhưng bằng nhau theo giá trị.

Với component kiểu tham chiếu, phép so sánh dựa trên ngữ nghĩa `equals()` của component. Điều này có nghĩa `String` thường so sánh theo nội dung, còn mảng dùng `equals()` mặc định của mảng và vì vậy so sánh theo tham chiếu.

```java
record Tags(String[] values) {}

Tags a = new Tags(new String[] {"java", "record"});
Tags b = new Tags(new String[] {"java", "record"});

System.out.println(a.equals(b)); // false: hai mảng khác tham chiếu
```

Đừng suy luận rằng record tự biến mọi component thành kiểu có bình đẳng theo nội dung. Ngữ nghĩa bình đẳng của component vẫn phụ thuộc vào chính kiểu component đó.

### Có thể tự viết `equals()` không?

Có, vì `equals(Object)` là phương thức của `Object` và record có thể khai báo triển khai riêng. Tuy nhiên, khi tùy chỉnh, lập trình viên chịu trách nhiệm duy trì hợp đồng `equals()`:

- Tính phản xạ: `x.equals(x)` phải là `true`.
- Tính đối xứng và bắc cầu.
- Tính nhất quán khi trạng thái dùng so sánh không đổi.
- `x.equals(null)` phải là `false`.
- Nếu hai object bằng nhau thì `hashCode()` của chúng phải bằng nhau.

Ví dụ record tên người dùng muốn so sánh không phân biệt chữ hoa/chữ thường:

```java
import java.util.Locale;
import java.util.Objects;

record UserName(String value) {
    UserName {
        value = Objects.requireNonNull(value, "value").strip();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof UserName that
            && value.equalsIgnoreCase(that.value);
    }

    @Override
    public int hashCode() {
        return value.toLowerCase(Locale.ROOT).hashCode();
    }
}
```

Vì `equals()` đã thay đổi quy tắc bình đẳng, `hashCode()` cũng phải thay đổi theo cùng quy tắc. Không nên override `equals()` mà giữ nguyên `hashCode()` mặc định nếu điều đó làm vi phạm hợp đồng. Trong đa số DTO và value object đơn giản, nên giữ triển khai mặc định theo component.

## 7. `hashCode()` được sinh từ các component

Khi không tự khai báo, `hashCode()` được tạo dựa trên các component. Quy tắc quan trọng nhất của Java vẫn áp dụng: hai object bằng nhau theo `equals()` phải có cùng `hashCode()`.

```java
record CustomerKey(String tenant, long customerId) {}

CustomerKey key1 = new CustomerKey("north", 101);
CustomerKey key2 = new CustomerKey("north", 101);

System.out.println(key1.equals(key2));        // true
System.out.println(key1.hashCode() == key2.hashCode()); // true
```

Điều này làm record thuận tiện khi dùng làm khóa trong `HashMap` hoặc phần tử trong `HashSet`:

```java
import java.util.HashMap;
import java.util.Map;

record ProductKey(String sku, String region) {}

Map<ProductKey, String> products = new HashMap<>();
products.put(new ProductKey("SKU-01", "VN"), "Keyboard");

String name = products.get(new ProductKey("SKU-01", "VN"));
System.out.println(name); // Keyboard
```

Tra cứu thành công vì key mới bằng key đã lưu theo `equals()` và có cùng mã băm. Không nên tự dựa vào một con số `hashCode()` cụ thể: Java không cam kết một giá trị mã băm cố định giữa các lần chạy hay phiên bản triển khai. Mã băm phục vụ cấu trúc dữ liệu, không phải định danh duy nhất hoặc checksum.

Nếu component mutable bị thay đổi sau khi object được dùng làm khóa, kết quả tra cứu có thể không còn như mong đợi. Vì vậy, key record nên chứa các component có ngữ nghĩa giá trị ổn định, bất biến hoặc được bảo vệ phòng vệ.

## 8. `toString()` được sinh từ các component

Khi không tự khai báo, `toString()` tạo biểu diễn văn bản có tên record cùng tên và giá trị các component. Ví dụ thông thường:

```java
record Range(int start, int end) {}

Range range = new Range(10, 20);
System.out.println(range);
// Thường hiển thị: Range[start=10, end=20]
```

Định dạng cụ thể của chuỗi không phải giao thức dữ liệu. Không nên phân tích chuỗi `toString()` để khôi phục object, lưu bền vững hoặc trao đổi với hệ thống khác. Nếu cần JSON, XML hay định dạng API, hãy dùng serializer và schema tương ứng.

### Tùy chỉnh biểu diễn khi cần

Có thể tự khai báo `toString()` để định dạng theo mục đích ứng dụng:

```java
record Money(String currency, long minorUnits) {
    @Override
    public String toString() {
        return currency + " " + minorUnits;
    }
}
```

Một lý do thực tế để tùy chỉnh là hạn chế dữ liệu nhạy cảm xuất hiện trong log:

```java
record AccessToken(String value) {
    @Override
    public String toString() {
        return "AccessToken[redacted]";
    }
}
```

`toString()` mặc định có thể hiển thị giá trị component, vì vậy không nên đưa mật khẩu, token, khóa bí mật hoặc dữ liệu cá nhân nhạy cảm vào log một cách vô ý. Việc ghi log cần tuân theo chính sách dữ liệu của ứng dụng.

## 9. Kiểm tra các component bằng reflection

Khi cần xây dựng công cụ tổng quát, chẳng hạn hiển thị cấu trúc DTO, tạo tài liệu hoặc ánh xạ dữ liệu, Java cung cấp API reflection cho record. Từ Java 16, có thể dùng `Class.isRecord()` và `Class.getRecordComponents()`.

```java
import java.lang.reflect.RecordComponent;

record Course(String code, String title, int lessonCount) {}

Class<?> type = Course.class;

if (type.isRecord()) {
    for (RecordComponent component : type.getRecordComponents()) {
        System.out.println("Name: " + component.getName());
        System.out.println("Type: " + component.getType().getTypeName());
        System.out.println("Accessor: " + component.getAccessor().getName());
    }
}
```

`getRecordComponents()` trả về metadata component theo thứ tự trong header. Mỗi `RecordComponent` cho phép truy vấn:

| API | Thông tin |
| --- | --- |
| `getName()` | Tên component. |
| `getType()` | Đối tượng `Class` đại diện kiểu component sau khi áp dụng quy tắc kiểu runtime. |
| `getGenericType()` | Kiểu khai báo tổng quát, hữu ích khi component dùng generic. |
| `getAccessor()` | Phương thức accessor của component. |
| `getAnnotatedType()` | Kiểu component kèm thông tin annotation trên kiểu. |

Ví dụ này chỉ đọc cấu trúc kiểu; nó không tạo instance và cũng không đọc giá trị component của một instance cụ thể. Muốn lấy giá trị từ object, gọi accessor tương ứng hoặc gọi `RecordComponent.getAccessor().invoke(instance)` khi thật sự cần reflection động. Khi dùng reflection động, cần xử lý các exception được khai báo bởi API và lưu ý quyền truy cập.

## 10. Ví dụ tổng hợp: record cho khóa học

Ví dụ sau cho thấy các thành viên ngầm định hoạt động cùng nhau. Lưu vào file **`Demo.java`**:

```java
import java.lang.reflect.RecordComponent;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class Demo {
    record Course(String code, String title, int lessonCount) {
        Course {
            code = Objects.requireNonNull(code, "code").strip();
            title = Objects.requireNonNull(title, "title").strip();

            if (code.isEmpty() || title.isEmpty()) {
                throw new IllegalArgumentException("code and title are required");
            }
            if (lessonCount < 0) {
                throw new IllegalArgumentException("lessonCount must be non-negative");
            }
        }
    }

    public static void main(String[] args) {
        Course java = new Course(" JAVA-16 ", "Records", 8);
        Course same = new Course("JAVA-16", "Records", 8);

        // Accessor được suy ra từ component.
        System.out.println(java.code());
        System.out.println(java.title());
        System.out.println(java.lessonCount());

        // equals/hashCode mặc định dựa trên component.
        System.out.println(java == same);       // false
        System.out.println(java.equals(same));  // true

        Map<Course, String> descriptions = new HashMap<>();
        descriptions.put(java, "Data carrier");
        System.out.println(descriptions.get(same)); // Data carrier

        // toString mặc định cung cấp biểu diễn record.
        System.out.println(java);

        // Reflection đọc cấu trúc component theo thứ tự header.
        for (RecordComponent component : Course.class.getRecordComponents()) {
            System.out.println(
                component.getName() + " : " + component.getType().getTypeName()
            );
        }
    }
}
```

Biên dịch và chạy trên JDK 16 trở lên:

```bash
javac --release 16 Demo.java
java Demo
```

Trong ví dụ:

1. `Course` có compact canonical constructor để chuẩn hóa và xác thực dữ liệu. Canonical constructor ngầm định không được tạo vì ta đã khai báo compact constructor.
2. Các field component và accessor vẫn được khai báo ngầm từ header.
3. `equals()`, `hashCode()` và `toString()` vẫn được cung cấp vì body không tự khai báo các phương thức này.
4. `same` là object khác `java`, nhưng bằng nhau theo component nên có thể tra cứu cùng khóa trong `HashMap`.
5. Reflection cho biết tên và kiểu các component theo thứ tự khai báo.

## 11. Khi nào giữ mặc định, khi nào tùy chỉnh?

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| DTO có component rõ ràng, bình đẳng theo giá trị tự nhiên | Giữ accessor, `equals()`, `hashCode()` và `toString()` mặc định. |
| Component cần xác thực hoặc chuẩn hóa khi tạo | Viết compact canonical constructor hoặc canonical constructor đầy đủ. |
| Component là collection/mảng và cần bảo vệ nội dung | Sao chép phòng vệ trong constructor; có thể khai báo accessor tường minh trả bản sao. |
| Cần quy tắc bình đẳng đặc biệt theo nghiệp vụ | Tự khai báo `equals()` và `hashCode()` đồng bộ, kiểm tra đủ hợp đồng Java. |
| Cần biểu diễn log riêng hoặc che dữ liệu nhạy cảm | Tự khai báo `toString()` và kiểm tra các đường log khác. |
| Cần công cụ đọc cấu trúc record tổng quát | Dùng `Class.isRecord()` và `Class.getRecordComponents()`. |

Những lỗi dễ gặp:

1. Nghĩ record tự sinh getter `getName()`: accessor là `name()`.
2. Nghĩ có thể thêm field instance để cache dữ liệu: trạng thái instance của record được giới hạn bởi các component.
3. Nghĩ `final` làm collection hoặc mảng bất biến: cần bảo vệ dữ liệu mutable.
4. Override `equals()` nhưng quên `hashCode()`: có thể làm hỏng hành vi của `HashMap` và `HashSet`.
5. Dùng chuỗi `toString()` như định dạng lưu trữ: định dạng này không phải giao thức.
6. Ghi log record chứa token hoặc dữ liệu nhạy cảm: `toString()` mặc định có thể hiển thị giá trị component.

## Ghi nhớ

Record header là nguồn mô tả các component. Từ header, Java khai báo ngầm field `private final`, canonical constructor, accessor cùng tên component và ba phương thức `equals()`, `hashCode()`, `toString()` nếu ta không tự khai báo các thành viên tương ứng. `equals()` và `hashCode()` mặc định dựa trên giá trị component; `toString()` cung cấp biểu diễn dễ đọc nhưng không phải định dạng trao đổi dữ liệu. Có thể tùy chỉnh accessor, constructor và các phương thức `Object` khi có yêu cầu rõ ràng, đồng thời phải giữ đúng hợp đồng Java. Reflection cung cấp cách đọc metadata component theo thứ tự header. Những khả năng này là phần ổn định của Java record từ Java 16 và tiếp tục áp dụng trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java API – java.lang.Record](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html)
- [Java API – java.lang.reflect.RecordComponent](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/RecordComponent.html)
