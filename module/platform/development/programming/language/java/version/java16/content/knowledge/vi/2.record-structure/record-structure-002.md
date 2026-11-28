# Khai báo record header, component và kiểu dữ liệu của component

## 1. Bức tranh tổng quan

Trong Java 16, `record` trở thành tính năng chính thức của ngôn ngữ (JEP 395). Đây là cách khai báo lớp dùng để biểu diễn một **tập giá trị có cấu trúc xác định và công khai**. Cú pháp này vẫn là một phần ổn định của Java hiện đại, không yêu cầu `--enable-preview`.

Ví dụ, khi một API cần trả về mã khóa học, tiêu đề và số bài học:

```java
public record CourseSummary(String code, String title, int lessonCount) {}
```

Danh sách `(String code, String title, int lessonCount)` được gọi là **record header**. Mỗi cặp kiểu và tên trong danh sách là một **record component**. Các component xác định cấu trúc dữ liệu và tham gia vào API của lớp, từ constructor đến accessor và hành vi so sánh theo giá trị.

**Mục tiêu bài học:**

- Đọc và viết đúng cú pháp record header, kể cả record không có component.
- Phân biệt component, field được tạo tự động, tham số constructor và accessor.
- Chọn kiểu dữ liệu phù hợp cho component: primitive, kiểu tham chiếu, generic, collection, array.
- Hiểu thứ tự, tên component, varargs và annotation ảnh hưởng ra sao đến hợp đồng API.
- Tránh các lỗi thường gặp liên quan đến kiểu dữ liệu mutable.

## 2. Cấu trúc một khai báo record

Dạng cơ bản:

```java
[modifiers] record RecordName(Type1 component1, Type2 component2, ...) {
    // Constructor, phương thức và các thành viên hợp lệ (nếu cần)
}
```

Trong đó, `modifiers` là các bổ nghĩa cho lớp phù hợp với phạm vi khai báo, chẳng hạn `public`; `RecordName` là tên kiểu; mỗi component phải có **kiểu và tên**. Dấu ngoặc tròn luôn bắt buộc, kể cả khi không có component.

Ví dụ:

```java
record Pixel(int red, int green, int blue) {}

record EmptySignal() {}

record Event(String type, java.time.Instant occurredAt) {}
```

| Phần cú pháp | Ý nghĩa | Trong `record Event(String type, Instant occurredAt)` |
| --- | --- | --- |
| `record` | Khai báo một lớp record. | `record` |
| Tên record | Định danh kiểu dữ liệu. | `Event` |
| Record header | Danh sách component theo thứ tự cố định. | `(String type, Instant occurredAt)` |
| Kiểu của component | Quy định loại giá trị được lưu/đọc. | `String`, `Instant` |
| Tên component | Đặt tên dữ liệu và accessor. | `type`, `occurredAt` |
| Record body | Nơi khai báo logic bổ sung khi cần. | `{}` |

Nếu khai báo một record `public` ở mức top-level, đặt nó trong tệp `RecordName.java`. Có thể khai báo record ở mức package-private hoặc lồng trong lớp; ví dụ hoàn chỉnh ở cuối bài dùng record lồng để chạy tất cả trong một tệp.

### Record header là một phần của hợp đồng API

Với:

```java
record Book(String isbn, String title, int pageCount) {}
```

Java tạo ra các thành phần về mặt ngữ nghĩa tương đương với:

| Khả năng | Được suy ra từ header |
| --- | --- |
| Field lưu dữ liệu | `private final String isbn`, `private final String title`, `private final int pageCount` |
| Canonical constructor | `Book(String isbn, String title, int pageCount)` |
| Accessor công khai | `isbn()`, `title()`, `pageCount()` |
| So sánh và mô tả | `equals(Object)`, `hashCode()`, `toString()` dựa trên các component |

Đây là bảng diễn giải, không phải mã nguồn Java được chép nguyên vào body. Trình biên dịch tự khai báo field và các thành viên cần thiết. Ta không cần tự viết lại chúng cho một record cơ bản.

```java
Book book = new Book("978-01", "Java Records", 240);

System.out.println(book.isbn());       // 978-01
System.out.println(book.title());      // Java Records
System.out.println(book.pageCount());  // 240
```

Lưu ý rằng accessor mặc định có tên **trùng tên component**: `title()`, không phải `getTitle()`. Record vẫn là **reference type**; các instance được tạo bằng `new`.

## 3. Component khác field và tham số constructor thế nào?

Một *record component* là phần khai báo nằm trong header, không phải một field do người viết đặt trực tiếp trong body. Từ một component như `String email`, trình biên dịch cung cấp:

1. Một field `private final` dùng lưu giá trị.
2. Một accessor `public String email()` trả về giá trị field.
3. Một tham số tương ứng trong canonical constructor.

Vì vậy, cùng một tên `email` xuất hiện trong nhiều vai trò có liên quan, nhưng nguồn gốc của chúng là **khai báo component**.

```java
record Contact(String email) {}

Contact contact = new Contact("student@example.com");
String address = contact.email();
```

Không được khai báo thêm instance field ngoài các component:

```java
// Không hợp lệ: thêm trạng thái instance bên ngoài header
// record Contact(String email) {
//     private String nickname;
// }
```

Ngược lại, `static` field hoặc phương thức tiện ích là hợp lệ vì không tạo trạng thái riêng của mỗi instance:

```java
record Temperature(double celsius) {
    static final double FREEZING_POINT = 0.0;

    boolean isFreezing() {
        return celsius <= FREEZING_POINT;
    }
}
```

Một record ngầm là `final`, có lớp cha trực tiếp là `java.lang.Record`, không thể `extends` một lớp tùy ý; nó vẫn có thể `implements` interface.

## 4. Chọn kiểu dữ liệu cho record component

Về nguyên tắc, kiểu component là một **kiểu Java hợp lệ có thể dùng làm kiểu giá trị**, không phải `void`. Những nhóm thông dụng:

| Nhóm kiểu | Ví dụ header | Khi nào phù hợp |
| --- | --- | --- |
| Primitive | `record Size(int width, int height) {}` | Giá trị nhỏ, rõ nghĩa; không thể `null`. |
| `String` và wrapper | `record UserInfo(String name, Integer age) {}` | Text và số có thể vắng mặt theo hợp đồng (nếu `null` được cho phép). |
| Kiểu giá trị chuẩn | `record Price(java.math.BigDecimal amount) {}` | Tiền hoặc số thập phân cần độ chính xác. |
| Date/time API | `record Deadline(java.time.Instant at) {}` | Mốc thời gian. |
| Enum | `record Ticket(Status status) {}` | Trạng thái giới hạn trong một tập giá trị đã định nghĩa. |
| Record khác | `record Segment(Point start, Point end) {}` | Cấu trúc lồng nhau có ngữ nghĩa giá trị. |
| Generic collection | `record Catalog(java.util.List<String> codes) {}` | Danh sách dữ liệu, cần kiểm soát khả năng sửa đổi. |
| Array | `record RawPacket(byte[] bytes) {}` | Chấp nhận được khi đã chủ động xử lý mutable state và so sánh mảng. |

Ví dụ chọn kiểu cho dữ liệu nghiệp vụ:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

record InvoiceLine(String sku, int quantity, BigDecimal unitPrice) {}

record Enrollment(String studentId, LocalDate enrolledOn) {}
```

Các kiểu `BigDecimal`, `LocalDate` và `String` có đặc điểm hữu ích là bất biến; bản thân record không làm cho kiểu tham chiếu mutable trở thành bất biến.

### Primitive hay wrapper?

```java
record Progress(int percent) {}
record OptionalScore(Integer score) {}
```

`int` luôn có giá trị số; `Integer` có thể chứa `null`. Chỉ dùng wrapper khi mô hình dữ liệu thực sự cần biểu diễn trạng thái vắng mặt, và quy định rõ nơi kiểm tra `null`. Không nên chọn wrapper chỉ vì nghĩ rằng record yêu cầu đối tượng: record hỗ trợ primitive trực tiếp.

### Generic type trong header

Record có thể khai báo tham số kiểu giống class:

```java
record Pair<L, R>(L left, R right) {}

Pair<String, Integer> result = new Pair<>("completed", 200);

System.out.println(result.left());   // completed
System.out.println(result.right());  // 200
```

Record generic cũng dùng được giới hạn kiểu:

```java
record NumberBox<T extends Number>(T value) {}

NumberBox<Integer> one = new NumberBox<>(1);
NumberBox<Double> pi = new NumberBox<>(3.14);
```

Kiểu component có thể là `List<T>`, `Map<String, T>` hoặc một kiểu generic lồng nhau. Hãy chọn kiểu công khai đủ cụ thể để người gọi hiểu cấu trúc; hạn chế raw type như `List` vì đánh mất kiểm tra kiểu ở thời điểm biên dịch.

```java
import java.util.List;
import java.util.Map;

record ResultPage<T>(List<T> items, int total) {}
record Metrics(Map<String, Long> counts) {}
```

Các ví dụ trên chỉ cho thấy cú pháp; nếu collection đầu vào có thể thay đổi, cần bổ sung bản sao phòng vệ như trình bày ở phần 7.

## 5. Thứ tự và tên component quan trọng thế nào?

Record header **có thứ tự**, không phải một tập các cặp tên–kiểu không phân biệt vị trí.

```java
record Dimensions(int width, int height) {}

Dimensions value = new Dimensions(1920, 1080);
```

Lời gọi constructor theo đúng thứ tự `(width, height)`. Nếu đổi header thành `record Dimensions(int height, int width)`, đoạn mã gọi constructor với hai số nguyên vẫn biên dịch, nhưng ý nghĩa của dữ liệu bị đảo. Đây là loại lỗi có thể âm thầm vượt qua kiểm tra biên dịch.

Tên component cũng tạo ra accessor và xuất hiện trong thông tin cấu trúc có thể truy cập bằng reflection. Vì vậy, đổi tên, thứ tự, kiểu hoặc thêm/bớt component cần được xem là **thay đổi API**, đặc biệt với mã đã xuất bản cho module khác hoặc dùng làm DTO.

Tên component tuân theo quy tắc định danh Java; không được trùng tên nhau. Java cũng cấm một số tên trùng phương thức không tham số của `Object`, chẳng hạn `toString`, `hashCode`, `getClass`, `wait`.

```java
// Không hợp lệ: lặp tên component
// record Pair(int value, String value) {}

// Không hợp lệ: tên component xung đột phương thức Object
// record DebugValue(String toString) {}

// Không hợp lệ: component bắt buộc khai báo kiểu
// record Invalid(var count) {}

// Không hợp lệ: void không thể là kiểu component
// record InvalidReturn(void result) {}
```

Không có cú pháp để đặt **giá trị mặc định ngay trong header** như `record Options(int timeout = 30)`. Nếu muốn cung cấp một cách tạo đối tượng với giá trị mặc định, có thể bổ sung constructor phụ gọi `this(...)`:

```java
record Options(int timeoutSeconds, boolean verbose) {
    Options() {
        this(30, false);
    }
}

Options defaults = new Options();
```

## 6. Component varargs và record rỗng

Java cho phép tối đa một component dạng *variable arity* (varargs), và nếu có thì **phải nằm ở vị trí cuối cùng** trong header:

```java
record Tags(String category, String... values) {}

Tags tags = new Tags("java", "records", "generics");
System.out.println(tags.values().length); // 2
```

Tham số `String... values` cho phép truyền nhiều đối số ở vị trí cuối; **kiểu component thực chất là `String[]`**. Accessor `values()` trả về mảng, nên người gọi có thể sửa nội dung nếu không thiết kế sao chép phòng vệ.

```java
// Không hợp lệ: varargs không đứng cuối
// record Wrong(String... values, int version) {}
```

Ngoài ra, record không có component vẫn hợp lệ:

```java
record RefreshRequested() {}

RefreshRequested signal = new RefreshRequested();
```

Record rỗng có thể biểu diễn một tín hiệu không mang dữ liệu, nhưng hãy dùng khi ý nghĩa miền nghiệp vụ thật sự rõ ràng; không phải mọi lớp đều cần chuyển thành record.

## 7. Kiểu tham chiếu mutable: bẫy phổ biến nhất của component

Các field của record là `private final`, nhưng đây chỉ là **bất biến nông** (*shallow immutability*). Điều đó có nghĩa là một component giữ tham chiếu đến `ArrayList` hoặc mảng vẫn có thể quan sát trạng thái thay đổi.

```java
import java.util.ArrayList;
import java.util.List;

record UnsafeTopics(List<String> names) {}

List<String> source = new ArrayList<>(List.of("record"));
UnsafeTopics topics = new UnsafeTopics(source);
source.add("stream");

System.out.println(topics.names()); // [record, stream]
```

Để biểu diễn một snapshot đáng tin cậy khi component là danh sách các `String` bất biến, sao chép tại constructor:

```java
import java.util.List;
import java.util.Objects;

record CourseTopics(List<String> names) {
    CourseTopics {
        names = List.copyOf(Objects.requireNonNull(names, "names"));
    }
}
```

`List.copyOf()` tạo hoặc tái sử dụng danh sách không cho phép sửa cấu trúc, ngăn việc thay đổi danh sách nguồn. Nó **không sao chép sâu** các phần tử nếu chúng mutable; vì vậy bản thân kiểu component cần được lựa chọn với ý nghĩa nghiệp vụ rõ ràng.

### Vì sao mảng cần đặc biệt cẩn thận?

```java
record Bytes(byte[] data) {}

Bytes a = new Bytes(new byte[] {1, 2});
Bytes b = new Bytes(new byte[] {1, 2});

System.out.println(a.equals(b)); // false
```

Hai mảng khác nhau dù chứa cùng phần tử vẫn không bằng nhau theo `Object.equals()`. Cách so sánh component mặc định của record không tự chuyển thành `Arrays.equals()`. Bên cạnh đó, mảng có thể sửa được qua accessor. Nếu ý nghĩa nghiệp vụ đòi hỏi so sánh theo nội dung, hãy cân nhắc thiết kế kiểu giá trị chuyên biệt hoặc một collection có ngữ nghĩa giá trị thích hợp, đồng thời bảo vệ dữ liệu khỏi bị sửa.

## 8. Annotation và thông tin component qua reflection

Record header có thể đặt **annotation** lên component. Khi xây dựng công cụ mô tả schema hoặc đọc metadata, Java 16 trở lên cung cấp `Class.isRecord()` và `Class.getRecordComponents()`.

Ví dụ annotation chỉ dành cho record component:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.RECORD_COMPONENT)
@Retention(RetentionPolicy.RUNTIME)
@interface DisplayName {
    String value();
}

record Customer(@DisplayName("Mã khách hàng") String id, int points) {}
```

Khi đọc:

```java
import java.lang.reflect.RecordComponent;

for (RecordComponent component : Customer.class.getRecordComponents()) {
    DisplayName displayName = component.getAnnotation(DisplayName.class);
    String label = displayName == null
        ? component.getName()
        : displayName.value();
    System.out.println(component.getName() + " -> " + label);
}
```

Ở ví dụ này, annotation xuất hiện khi runtime nhờ `@Retention(RUNTIME)` và áp dụng được cho `RECORD_COMPONENT`. Một annotation ở header cũng có thể được trình biên dịch gắn vào field, accessor hoặc tham số constructor tương ứng **nếu** `@Target` của annotation cho phép ngữ cảnh đó. Không nên mặc định rằng mọi annotation trên component đều có mặt ở tất cả những nơi trên.

Với `getRecordComponents()`, mỗi `RecordComponent` còn cho phép lấy tên (`getName()`), kiểu (`getType()`), kiểu generic (`getGenericType()`) và phương thức accessor (`getAccessor()`). Đây là API reflection chính thức, phù hợp khi thật sự cần quan sát cấu trúc của record lúc chạy.

## 9. Ví dụ hoàn chỉnh: thiết kế header cho dữ liệu khóa học

Ví dụ sau kết hợp khai báo component có kiểu generic, kiểu ngày giờ chuẩn, collection bất biến và đọc header bằng reflection. Lưu toàn bộ vào tệp **`Demo.java`**:

```java
import java.lang.reflect.RecordComponent;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class Demo {
    record CourseCard<T>(
        String code,
        T detail,
        List<String> topics,
        LocalDate publishedAt
    ) {
        CourseCard {
            code = Objects.requireNonNull(code, "code").strip();
            detail = Objects.requireNonNull(detail, "detail");
            topics = List.copyOf(Objects.requireNonNull(topics, "topics"));
            publishedAt = Objects.requireNonNull(publishedAt, "publishedAt");

            if (code.isEmpty()) {
                throw new IllegalArgumentException("code must not be blank");
            }
        }

        boolean hasTopic(String topic) {
            return topics.contains(topic);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("record", "stream"));

        CourseCard<String> first = new CourseCard<>(
            " JAVA-16 ",
            "Các cải tiến Java 16",
            source,
            LocalDate.of(2021, 3, 1)
        );

        source.add("external-change");

        CourseCard<String> second = new CourseCard<>(
            "JAVA-16",
            "Các cải tiến Java 16",
            List.of("record", "stream"),
            LocalDate.of(2021, 3, 1)
        );

        System.out.println(first.code());        // JAVA-16
        System.out.println(first.topics());      // [record, stream]
        System.out.println(first.equals(second)); // true
        System.out.println(first.hasTopic("record")); // true
        System.out.println(CourseCard.class.isRecord()); // true

        for (RecordComponent component : CourseCard.class.getRecordComponents()) {
            System.out.println(
                component.getName() + " : " + component.getGenericType().getTypeName()
            );
        }
    }
}
```

Biên dịch và chạy trên **JDK 16 trở lên**:

```bash
javac --release 16 Demo.java
java Demo
```

Trong ví dụ này:

1. Header chứa bốn component theo thứ tự `code`, `detail`, `topics`, `publishedAt`. Vì vậy canonical constructor nhận bốn đối số tương ứng.
2. `T detail` là component generic; trong lần tạo đối tượng này `T` được chọn là `String`.
3. `List<String> topics` cần bản sao phòng vệ để giữ snapshot ổn định.
4. `LocalDate` là kiểu giá trị bất biến của Java Date/Time API.
5. `getRecordComponents()` cho phép xem các component theo thứ tự khai báo và đọc thông tin kiểu, kể cả chữ ký generic.

## 10. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `new Person("Lan", 20)` bị từ chối | Header thật sự có thứ tự hoặc kiểu khác. | Đối chiếu danh sách component và constructor. |
| Gọi `person.getName()` không biên dịch | Accessor mặc định là `name()`. | Dùng `person.name()` hoặc kiểm tra API thư viện tích hợp. |
| Viết `record R(var value)` không biên dịch | Component cần kiểu khai báo tường minh. | Chọn `String`, `int`, `List<String>`, v.v. |
| Dữ liệu trong record vẫn thay đổi | Component giữ collection/array mutable. | Bảo vệ bằng kiểu bất biến hoặc sao chép phòng vệ. |
| Hai record giữ các mảng cùng nội dung không bằng nhau | `equals()` của mảng dựa trên tham chiếu. | Thiết kế lại kiểu component/ngữ nghĩa bình đẳng theo nhu cầu. |
| Sau khi đổi thứ tự hai component cùng kiểu, kết quả sai | Constructor vẫn biên dịch nhưng ý nghĩa đối số bị đổi. | Xem header như hợp đồng API; sửa các điểm tạo record và kiểm thử tình huống thực. |
| Annotation không hiện ở runtime | `@Retention` hoặc `@Target` không phù hợp. | Kiểm tra `RUNTIME` và `RECORD_COMPONENT` cho metadata component. |

## 11. Bài tập áp dụng

1. Khai báo `record ApiResponse(int statusCode, String message)` và chỉ ra tên, kiểu, thứ tự từng component. Tạo hai instance có cùng giá trị và kiểm tra `equals()`.
2. Viết `record Pair<A, B>(A first, B second)`. Tạo một `Pair<String, Long>` và giải thích kiểu trả về của `first()` và `second()`.
3. Khai báo `record Lesson(String title, List<String> topics)`. Thêm constructor sao chép phòng vệ và chứng minh sửa danh sách nguồn không ảnh hưởng dữ liệu trong record.
4. Viết `record Tags(String category, String... names)`. Giải thích vì sao `names()` có kiểu `String[]` và những nguy cơ khi truy cập trực tiếp mảng.
5. Dùng `getRecordComponents()` in tên và kiểu của tất cả component trong một record do bạn tự chọn. Thử đổi thứ tự khai báo và quan sát kết quả.

## Ghi nhớ

**Record header là bản mô tả dữ liệu của kiểu record**, chứ không đơn thuần là cách viết tắt cho danh sách field. Mỗi component có kiểu và tên rõ ràng; từ đó Java suy ra field `private final`, accessor và tham số của canonical constructor. Thứ tự và tên component góp phần định nghĩa API, nên phải được lựa chọn ổn định. Record hỗ trợ primitive, kiểu tham chiếu, generic và varargs, nhưng **không tự làm bất biến dữ liệu bên trong collection hoặc array**. Hãy ưu tiên những kiểu component phản ánh đúng ngữ nghĩa giá trị mà ứng dụng muốn truyền đi.

**Tham khảo chính thức (các tính năng ổn định vẫn còn áp dụng):**

- [OpenJDK JEP 395 – Records (finalized in Java 16)](https://openjdk.org/jeps/395)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Javadoc java.lang.Record](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html)
- [Javadoc java.lang.reflect.RecordComponent](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/RecordComponent.html)
