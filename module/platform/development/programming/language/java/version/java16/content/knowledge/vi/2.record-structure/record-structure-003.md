# Khởi tạo record và đọc dữ liệu bằng accessor cùng tên component

## 1. Từ khai báo đến đối tượng có thể sử dụng

`record` là cách khai báo một lớp mang dữ liệu có cấu trúc rõ ràng. Tính năng này được hoàn thiện trong **Java 16** (JEP 395) và vẫn được hỗ trợ trong các phiên bản Java hiện đại. Khi đã khai báo record, hai thao tác cơ bản trong chương trình là:

1. **Khởi tạo** một instance bằng constructor với các giá trị tương ứng từng component.
2. **Đọc dữ liệu** qua accessor có tên trùng với component, chẳng hạn `student.name()`.

Ví dụ:

```java
record Student(String id, String name, int completedLessons) {}

Student student = new Student("ST-01", "An", 8);

System.out.println(student.id());                // ST-01
System.out.println(student.name());              // An
System.out.println(student.completedLessons());  // 8
```

Danh sách component trong header quyết định constructor chuẩn và các accessor mặc định. Với record trên, Java cung cấp constructor nhận lần lượt `String`, `String`, `int`, cùng ba phương thức `id()`, `name()` và `completedLessons()`.

Mục tiêu bài học:

- Khởi tạo record bằng canonical constructor và hiểu thứ tự đối số.
- Dùng compact canonical constructor để kiểm tra, chuẩn hóa dữ liệu khi tạo đối tượng.
- Biết khi nào cần viết canonical constructor đầy đủ hoặc constructor phụ.
- Đọc component qua accessor có tên đúng bằng component.
- Xử lý `null`, collection và dữ liệu mutable một cách có chủ đích.

## 2. Khởi tạo bằng canonical constructor mặc định

Với khai báo:

```java
record Point(int x, int y) {}
```

Trình biên dịch cung cấp canonical constructor tương đương về mặt chữ ký với:

```java
Point(int x, int y)
```

Ta tạo đối tượng bằng từ khóa `new`:

```java
Point origin = new Point(0, 0);
Point destination = new Point(12, 5);
```

Đối số được truyền theo **đúng thứ tự component trong header**. `new Point(12, 5)` có nghĩa `x = 12`, `y = 5`. Nếu hai component có cùng kiểu, trình biên dịch không thể phát hiện việc ta vô tình đảo ý nghĩa hai đối số. Vì vậy, cần đọc header trước khi gọi constructor và đặt tên biến rõ ràng ở nơi tạo record.

### Constructor chuẩn được suy ra như thế nào?

Với khai báo:

```java
record Book(String isbn, String title, int pages) {}
```

Các thành viên liên quan đến việc tạo và đọc dữ liệu có thể tóm tắt như sau:

| Thành phần | Vai trò |
| --- | --- |
| `Book(String isbn, String title, int pages)` | Canonical constructor nhận đủ giá trị component theo thứ tự khai báo. |
| `private final String isbn` | Field lưu component `isbn`, được trình biên dịch tạo. |
| `private final String title` | Field lưu component `title`, được trình biên dịch tạo. |
| `private final int pages` | Field lưu component `pages`, được trình biên dịch tạo. |
| `isbn()`, `title()`, `pages()` | Accessor công khai để đọc giá trị component. |

Với record cơ bản không khai báo constructor, Java tự tạo canonical constructor và tự gán từng tham số vào field tương ứng. Ta không cần viết lại constructor chỉ để lưu dữ liệu.

### Kiểu đối số phải tương thích với component

```java
record Product(String code, int quantity, boolean available) {}

Product item = new Product("P-100", 3, true);
```

Đối số phải tương thích với kiểu component tại vị trí tương ứng. Java cho phép các chuyển đổi kiểu hợp lệ theo quy tắc gọi phương thức/constructor, ví dụ một giá trị `int` có thể được widening sang `long` nếu component khai báo là `long`.

Primitive không thể nhận `null`; kiểu tham chiếu như `String`, `Integer`, `List<String>` có thể nhận `null` nếu constructor không kiểm tra. Không nên để hành vi này phụ thuộc vào may rủi: hãy quyết định rõ component nào bắt buộc có giá trị.

### Record generic và toán tử diamond

Record có tham số kiểu được khởi tạo như các lớp generic thông thường:

```java
record ApiResult<T>(T data, boolean successful) {}

ApiResult<String> message =
    new ApiResult<>("Created", true);

ApiResult<Integer> count =
    new ApiResult<>(42, true);
```

Toán tử diamond `<>` cho phép trình biên dịch suy luận kiểu `T` từ ngữ cảnh và đối số. Khi khai báo biến với kiểu tường minh như `ApiResult<String>`, kiểu dữ liệu đọc qua `data()` là `String`.

## 3. Đọc dữ liệu bằng accessor cùng tên component

Accessor mặc định là phương thức công khai, không tham số, có tên **trùng chính xác với component**:

```java
record Employee(String employeeCode, String fullName, int level) {}

Employee employee = new Employee("E-100", "Binh Nguyen", 4);

String code = employee.employeeCode();
String name = employee.fullName();
int level = employee.level();
```

Một số điểm cần nhớ:

- Component `employeeCode` tạo accessor `employeeCode()`.
- Component `fullName` tạo accessor `fullName()`.
- Component `level` tạo accessor `level()`.
- Accessor không có tiền tố `get`, kể cả khi ứng dụng thường dùng quy ước JavaBean.
- Gọi accessor như gọi một phương thức Java thông thường, có dấu ngoặc tròn.

```java
// Đúng: accessor trùng tên component
String name = employee.fullName();

// Sai: record không tự sinh getter JavaBean này
// String name = employee.getFullName();
```

Field component là `private final`; mã bên ngoài đọc dữ liệu qua accessor công khai. Không có setter được tạo tự động. Việc không có setter giúp ngăn gán lại field component sau khi đối tượng đã khởi tạo.

### Accessor trả về giá trị component

Với component primitive, accessor trả về giá trị primitive:

```java
record Rectangle(int width, int height) {}

Rectangle rectangle = new Rectangle(20, 10);
int width = rectangle.width();
int area = rectangle.width() * rectangle.height();
```

Với component kiểu tham chiếu, accessor trả về tham chiếu đang được lưu trong component:

```java
record Contact(String email) {}

Contact contact = new Contact("an@example.com");
String email = contact.email();
```

Đối với kiểu tham chiếu mutable, điều này có nghĩa người gọi có thể nhận được chính đối tượng mutable đó. Record không tự tạo bản sao mỗi lần gọi accessor. Phần 7 trình bày cách xử lý collection và mảng.

### Đọc component trong biểu thức và Stream

Accessor là phương thức nên có thể dùng trong biểu thức, truyền làm method reference hoặc gọi từ lambda:

```java
import java.util.List;

record Student(String name, int score) {}

List<Student> students = List.of(
    new Student("An", 85),
    new Student("Binh", 92),
    new Student("Chi", 78)
);

List<String> names = students.stream()
    .map(Student::name)
    .toList();

int totalScore = students.stream()
    .mapToInt(Student::score)
    .sum();
```

`Student::name` là method reference đến accessor `name()`. Cách dùng này đặc biệt tiện khi biến record thành dữ liệu cho các bước xử lý Stream.

## 4. Compact canonical constructor: kiểm tra dữ liệu lúc khởi tạo

Một record thường đại diện cho giá trị hợp lệ. Nếu cần từ chối dữ liệu sai hoặc chuẩn hóa dữ liệu, hãy thực hiện điều đó ngay trong constructor. Java hỗ trợ **compact canonical constructor** để viết phần thân constructor mà không lặp lại danh sách tham số.

```java
import java.util.Objects;

public record UserName(String value) {
    public UserName {
        value = Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
```

Trong compact constructor:

1. Tên `value` là tham số của canonical constructor, tương ứng với component `value`.
2. Có thể kiểm tra hoặc gán lại tham số để chuẩn hóa giá trị.
3. Sau khi phần thân constructor hoàn tất bình thường, Java tự gán giá trị cuối cùng của tham số vào field component.
4. Không viết `this.value = value` trong compact constructor; việc gán field được trình biên dịch thực hiện tự động.

Ví dụ sử dụng:

```java
UserName userName = new UserName("  Nguyen An  ");
System.out.println(userName.value()); // Nguyen An
```

Nếu truyền `null` hoặc chuỗi chỉ có khoảng trắng, constructor ném exception và instance không được tạo thành công. Đây là cách giữ invariant: mọi `UserName` đã tạo đều có `value` không rỗng và đã được loại khoảng trắng đầu/cuối.

### Compact constructor với nhiều component

```java
import java.util.Objects;

record ProductOrder(String orderId, int quantity) {
    ProductOrder {
        orderId = Objects.requireNonNull(orderId, "orderId").strip();

        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
    }
}
```

Đối số được kiểm tra cùng một điểm trước khi đối tượng được tạo. Mọi nơi gọi `new ProductOrder(...)` đều phải đi qua quy tắc này.

## 5. Viết canonical constructor đầy đủ khi cần kiểm soát phép gán

Compact constructor phù hợp với xác thực và chuẩn hóa thông thường. Nếu cần viết rõ từng phép gán field, ta có thể khai báo canonical constructor đầy đủ:

```java
import java.util.Objects;

record Account(String id, String displayName) {
    Account(String id, String displayName) {
        this.id = Objects.requireNonNull(id, "id").strip();
        this.displayName =
            Objects.requireNonNull(displayName, "displayName").strip();

        if (this.id.isEmpty() || this.displayName.isEmpty()) {
            throw new IllegalArgumentException("id and displayName are required");
        }
    }
}
```

Khác compact constructor, canonical constructor đầy đủ **phải tự gán tất cả field component**. Mỗi field cần được gán đúng một lần theo quy tắc của record; không có bước gán tự động ở cuối constructor. Dùng `this.id` và `this.displayName` để chỉ rõ field đang được khởi tạo.

Hai cách viết đều tạo ra canonical constructor có chữ ký khớp với header. Chọn compact constructor khi logic chủ yếu là kiểm tra/chuẩn hóa tham số; chọn dạng đầy đủ khi cần kiểm soát trực tiếp các phép gán.

## 6. Constructor phụ để cung cấp cách khởi tạo thuận tiện

Record có thể khai báo constructor khác canonical constructor, thường gọi là *non-canonical constructor* hoặc constructor phụ. Constructor này phải ủy quyền đến một constructor khác của cùng record bằng `this(...)` làm câu lệnh đầu tiên. Nhờ vậy, mọi đường khởi tạo đều đi qua canonical constructor và các quy tắc xác thực.

```java
record PageRequest(int page, int size) {
    PageRequest() {
        this(0, 20);
    }

    PageRequest(int size) {
        this(0, size);
    }
}
```

Sử dụng:

```java
PageRequest defaults = new PageRequest();
PageRequest firstPage = new PageRequest(50);
PageRequest custom = new PageRequest(2, 100);
```

Các lời gọi lần lượt tạo:

| Biểu thức | Giá trị `page` | Giá trị `size` |
| --- | ---: | ---: |
| `new PageRequest()` | 0 | 20 |
| `new PageRequest(50)` | 0 | 50 |
| `new PageRequest(2, 100)` | 2 | 100 |

Nếu cần kiểm tra `page` và `size`, hãy đặt kiểm tra trong canonical constructor (compact hoặc đầy đủ). Cả ba cách tạo ở trên đều đi qua điểm kiểm tra đó.

```java
record ValidPageRequest(int page, int size) {
    ValidPageRequest {
        if (page < 0) {
            throw new IllegalArgumentException("page must be non-negative");
        }
        if (size <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }
    }

    ValidPageRequest() {
        this(0, 20);
    }

    ValidPageRequest(int size) {
        this(0, size);
    }
}
```

Không viết constructor phụ bằng cách gán trực tiếp `this.page` hoặc `this.size`; constructor phụ phải ủy quyền bằng `this(...)`. Với record có component, cũng không có constructor mặc định không tham số tự sinh thêm ngoài canonical constructor. Nếu cần `new SomeRecord()`, hãy khai báo constructor phụ không tham số và ủy quyền đến canonical constructor như ví dụ trên.

## 7. Đọc component kiểu tham chiếu và bảo vệ dữ liệu mutable

Field component là `final`, nhưng `final` chỉ ngăn thay đổi tham chiếu được lưu trong field. Nó không tự ngăn đối tượng mà tham chiếu trỏ đến bị thay đổi.

Ví dụ sau cho thấy accessor trả về cùng danh sách mutable:

```java
import java.util.ArrayList;
import java.util.List;

record MutableTags(List<String> values) {}

List<String> source = new ArrayList<>(List.of("java"));
MutableTags tags = new MutableTags(source);

tags.values().add("record");
System.out.println(source); // [java, record]
```

Nếu record cần lưu snapshot danh sách, có thể sao chép phòng vệ trong compact constructor:

```java
import java.util.List;
import java.util.Objects;

record TopicSnapshot(List<String> topics) {
    TopicSnapshot {
        topics = List.copyOf(Objects.requireNonNull(topics, "topics"));
    }
}
```

Sau khi tạo `TopicSnapshot`, người gọi không thể thêm hoặc xóa phần tử qua danh sách trả về từ `topics()`, và việc sửa danh sách nguồn cũng không làm thay đổi snapshot. `List.copyOf()` không chấp nhận phần tử `null`. Đây là bản sao phòng vệ cấu trúc nông; nếu phần tử bên trong là object mutable, object đó vẫn có thể thay đổi.

### Mảng cần sao chép cả đầu vào lẫn đầu ra

Accessor mặc định của component mảng trả về tham chiếu mảng đang lưu. Nếu cần đóng gói mảng, có thể sao chép khi nhận dữ liệu và khai báo accessor tường minh để trả về bản sao:

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

Ở đây constructor sao chép mảng đầu vào; accessor `bytes()` sao chép lần nữa để người gọi không thể sửa mảng nội bộ. Tuy nhiên, `equals()` và `hashCode()` được tạo cho record vẫn xử lý component mảng theo ngữ nghĩa của mảng Java, tức là so sánh tham chiếu, không phải so sánh từng byte. Nếu cần ngữ nghĩa giá trị theo nội dung mảng, phải thiết kế rõ `equals()`/`hashCode()` hoặc dùng một kiểu dữ liệu khác phù hợp.

## 8. So sánh hai instance và hiểu dữ liệu sau khi đọc

Record mặc định định nghĩa `equals()` và `hashCode()` dựa trên component. Vì vậy, hai instance riêng biệt có cùng kiểu record và các giá trị component tương ứng sẽ bằng nhau theo `equals()`:

```java
record Coordinate(int latitude, int longitude) {}

Coordinate a = new Coordinate(10, 20);
Coordinate b = new Coordinate(10, 20);

System.out.println(a == b);       // false: hai tham chiếu khác nhau
System.out.println(a.equals(b));  // true: giá trị component bằng nhau
System.out.println(a.latitude()); // 10
```

Đọc accessor không tạo một record mới và cũng không thay đổi đối tượng. Nó chỉ cung cấp giá trị component hiện tại theo kiểu trả về. Với primitive, đó là giá trị primitive; với kiểu tham chiếu, đó là tham chiếu đến component (trừ khi accessor được tự khai báo để trả về một giá trị khác hoặc bản sao).

Không dùng `==` để kiểm tra bình đẳng giá trị giữa hai record. Hãy dùng `equals()`; nếu chỉ cần so sánh một component thì đọc accessor và so sánh giá trị tương ứng.

## 9. Ví dụ hoàn chỉnh: tạo hồ sơ học viên và đọc dữ liệu

Ví dụ dưới đây kết hợp compact constructor, constructor phụ, accessor, method reference và Stream. Lưu toàn bộ vào tệp **`Demo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class Demo {
    record Learner(String code, String name, int completedLessons) {
        Learner {
            code = Objects.requireNonNull(code, "code").strip();
            name = Objects.requireNonNull(name, "name").strip();

            if (code.isEmpty() || name.isEmpty()) {
                throw new IllegalArgumentException("code and name are required");
            }
            if (completedLessons < 0) {
                throw new IllegalArgumentException(
                    "completedLessons must be non-negative"
                );
            }
        }

        Learner(String code, String name) {
            this(code, name, 0);
        }

        boolean hasStarted() {
            return completedLessons() > 0;
        }
    }

    public static void main(String[] args) {
        Learner first = new Learner(" HV-01 ", " An ", 8);
        Learner second = new Learner("HV-02", "Binh");

        System.out.println(first.code());              // HV-01
        System.out.println(first.name());              // An
        System.out.println(first.completedLessons());  // 8
        System.out.println(second.completedLessons()); // 0
        System.out.println(first.hasStarted());        // true

        List<Learner> learners = List.of(
            first,
            second,
            new Learner("HV-03", "Chi", 12)
        );

        learners.stream()
            .map(Learner::name)
            .forEach(System.out::println);

        int totalLessons = learners.stream()
            .mapToInt(Learner::completedLessons)
            .sum();
        System.out.println("Total lessons: " + totalLessons);
    }
}
```

Biên dịch và chạy trên JDK 16 trở lên:

```bash
javac --release 16 Demo.java
java Demo
```

Điểm cần quan sát:

1. `new Learner(" HV-01 ", " An ", 8)` gọi canonical constructor; compact constructor chuẩn hóa hai chuỗi và xác thực số bài đã hoàn thành.
2. `new Learner("HV-02", "Binh")` gọi constructor phụ, constructor này ủy quyền đến canonical constructor với số bài mặc định bằng `0`.
3. `first.code()`, `first.name()` và `first.completedLessons()` đọc các component qua accessor.
4. `Learner::name` và `Learner::completedLessons` là method reference đến accessor, có thể truyền trực tiếp cho Stream.
5. `hasStarted()` là hành vi bổ sung được suy ra từ component; record vẫn có thể chứa phương thức nghiệp vụ phù hợp.

## 10. Những lỗi thường gặp

| Lỗi | Vì sao xảy ra | Cách khắc phục |
| --- | --- | --- |
| Gọi `record.getName()` | Accessor mặc định không dùng tiền tố `get`. | Gọi `record.name()`. |
| Truyền đối số sai thứ tự | Canonical constructor theo đúng thứ tự header. | Kiểm tra header; dùng biến có tên rõ nghĩa khi tạo instance. |
| Truyền `null` cho component bắt buộc | Kiểu tham chiếu có thể nhận `null` nếu không xác thực. | Dùng `Objects.requireNonNull()` trong constructor. |
| Cố gán `this.name` trong compact constructor | Compact constructor tự gán field sau phần thân. | Chuẩn hóa tham số `name`, không gán field trực tiếp. |
| Quên gán một field trong canonical constructor đầy đủ | Constructor đầy đủ phải tự gán mọi component. | Gán từng `this.component = parameter` đúng một lần. |
| Gán field trong constructor phụ | Constructor phụ phải ủy quyền đến constructor khác bằng `this(...)`. | Chuyển logic khởi tạo về canonical constructor. |
| Nghĩ rằng `final List` làm danh sách bất biến | `final` chỉ cố định tham chiếu, không cố định nội dung object. | Sao chép phòng vệ hoặc dùng kiểu bất biến. |
| Nghĩ accessor luôn tạo bản sao | Accessor mặc định trả về component đang lưu. | Tự khai báo accessor phòng vệ nếu component mutable cần được đóng gói. |
| Dùng `==` để so sánh giá trị | `==` so sánh tham chiếu object. | Dùng `equals()` để so sánh giá trị record. |

## 11. Bài tập thực hành

1. Khai báo `record Address(String street, String city, String country)`. Tạo một instance và đọc từng component bằng accessor.
2. Viết `record Percentage(int value)` có compact constructor từ chối giá trị ngoài khoảng 0 đến 100. Thử tạo một giá trị hợp lệ và một giá trị không hợp lệ.
3. Viết `record SearchRequest(String keyword, int page, int size)` với constructor phụ `SearchRequest(String keyword)` mặc định `page = 0`, `size = 20`. Đảm bảo mọi constructor đều qua kiểm tra trong canonical constructor.
4. Tạo `List<Address>` và dùng `Address::city` trong Stream để lấy danh sách thành phố.
5. Viết `record Labels(List<String> values)` và dùng `List.copyOf()` trong compact constructor. Chứng minh danh sách nguồn và danh sách trả về từ accessor không thể làm thay đổi cấu trúc snapshot.

## Ghi nhớ

Khởi tạo record đi qua canonical constructor với một giá trị cho mỗi component theo đúng thứ tự header. Compact canonical constructor là cách gọn để xác thực và chuẩn hóa tham số; canonical constructor đầy đủ cho phép kiểm soát từng phép gán; constructor phụ phải ủy quyền bằng `this(...)`. Sau khi tạo đối tượng, đọc dữ liệu qua accessor công khai **cùng tên component**, ví dụ `order.id()` hoặc `student.name()`. Accessor mặc định trả về giá trị component đang lưu và không tự sao chép object mutable. Khi thiết kế record cho dữ liệu tham chiếu, hãy quyết định rõ cách xử lý `null`, collection, mảng và sao chép phòng vệ.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java Language Specification – Constructors, mục 8.8](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.8)
- [Oracle Java – Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html)
