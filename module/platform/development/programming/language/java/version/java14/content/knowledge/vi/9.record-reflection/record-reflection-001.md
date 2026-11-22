# Nhận diện record qua Class.isRecord trong Java Reflection

## 1. Mục tiêu: biết một kiểu có thực sự là record không

Trong ứng dụng cần kiểm tra cấu trúc kiểu dữ liệu lúc chạy (serialization, mapping, schema generation, kiểm thử hợp đồng, công cụ phát triển), ta có thể nhận được một đối tượng `Class<?>` mà chưa biết kiểu đó được khai báo bằng `record` hay `class` thông thường.

Từ **Java 16**, `record` là tính năng ngôn ngữ chính thức. Java cung cấp phương thức Reflection:

~~~java
boolean isRecord = SomeType.class.isRecord();
~~~

**`Class.isRecord()` trả về `true` khi và chỉ khi đối tượng `Class` biểu diễn một record class.** Với các class khác, interface, enum, kiểu nguyên thủy và kiểu mảng, nó trả `false`. Đây là câu trả lời trực tiếp cho câu hỏi *“kiểu này có phải một record class hay không?”*.

Ví dụ:

~~~java
record Point(int x, int y) {}
class PointClass {
    int x;
    int y;
}

System.out.println(Point.class.isRecord());      // true
System.out.println(PointClass.class.isRecord()); // false
~~~

Hai khai báo có thể cùng mang dữ liệu `x, y`, nhưng chỉ khai báo đầu có bản chất **record class**. Cách xác định dựa trên metadata kiểu, **không dựa trên việc class có bao nhiêu trường, có getter/setter hay có `equals/hashCode` hay không**.

Các ví dụ chính trong bài sử dụng **Java 17+** và API đã ổn định, không dựa vào cú pháp record preview của những bản phát hành cũ.

## 2. `isRecord()` là phương thức của `Class`, không phải của từng record instance

Cú pháp đầy đủ:

~~~java
public boolean isRecord()
~~~

Phương thức thuộc `java.lang.Class`. Vì vậy nó kiểm tra **một kiểu**, không phải giá trị các thành phần trong một đối tượng record:

~~~java
record User(long id, String name) {}

Class<?> type = User.class;
boolean yes = type.isRecord(); // true
~~~

Với một đối tượng đã có ở runtime:

~~~java
Object value = new User(7L, "Lan");
boolean yes = value.getClass().isRecord(); // true
~~~

**Cẩn thận với `null`:** gọi `null.getClass()` sẽ gây `NullPointerException`. Nếu API cần chấp nhận `null`, kiểm tra trước:

~~~java
static boolean isRecordInstance(Object value) {
    return value != null && value.getClass().isRecord();
}
~~~

Đây là phương thức hỗ trợ có thể đặt trong một class bất kỳ. Nó có nghĩa: *đối tượng khác null này được tạo từ một record class?*

Với đối tượng cụ thể, biểu thức `value instanceof java.lang.Record` cũng có thể nhận diện record instance, vì record class trực tiếp kế thừa `java.lang.Record`. Tuy nhiên, khi bạn đang xử lý **`Class<?>` metadata** và muốn truy vấn thành phần bằng Reflection, `Class.isRecord()` là API thích hợp và diễn đạt mục đích rõ nhất.

## 3. Các trường hợp dễ nhầm

| Đối tượng `Class<?>` | `isRecord()` | Lý do |
| --- | --- | --- |
| `Person.class` với `record Person(...)` | `true` | Đúng là record class |
| `Empty.class` với `record Empty()` | `true` | Record có thể có **0 thành phần** |
| `GenericBox.class` với `record GenericBox<T>(T value)` | `true` | Record vẫn là record khi có type parameter |
| `Regular.class` với `class Regular {...}` | `false` | Class thông thường, dù cũng bất biến và có getter |
| `State.class` với `enum State {...}` | `false` | Enum là loại khai báo khác |
| `Runnable.class` | `false` | Interface không phải record class |
| `Person[].class` | `false` | Đây là **class biểu diễn mảng**, các phần tử có thể là record |
| `int.class` | `false` | Kiểu nguyên thủy |
| `void.class` | `false` | Không phải record |
| `java.lang.Record.class` | `false` | Đây là **lớp cơ sở trừu tượng**, bản thân nó không phải record class |

Một trường hợp quan trọng: **`Person[].class.isRecord()` là `false`**, nhưng `Person.class.isRecord()` là `true`. Nếu đang có kiểu mảng và mục tiêu là nhận diện **kiểu phần tử**, bạn cần `getComponentType()`:

~~~java
Class<?> arrayType = Person[].class;
System.out.println(arrayType.isRecord());                   // false
System.out.println(arrayType.getComponentType().isRecord()); // true
~~~

`getComponentType()` chỉ có ý nghĩa khi `Class.isArray()` là `true`; với kiểu không phải mảng, nó trả `null`. Chỉ gọi tiếp `isRecord()` sau khi đã kiểm tra phù hợp.

Một record **lồng trong class**, **record cục bộ trong phương thức**, hoặc **record generic** vẫn là record class. Vị trí khai báo và tên kiểu không thay đổi kết quả `isRecord()`.

## 4. Sau khi nhận diện: dùng `getRecordComponents()`

`Class.isRecord()` trả lời câu hỏi **có phải record không**. Nếu muốn đọc cấu trúc của record, gọi:

~~~java
java.lang.reflect.RecordComponent[] parts =
        Person.class.getRecordComponents();
~~~

Hành vi được Java SE quy định:

- Nếu `Class` là record: trả **mảng không null** của các `RecordComponent`, theo **đúng thứ tự khai báo trong header**.
- Nếu record không có thành phần, ví dụ `record Empty() {}`: trả **mảng độ dài 0**, không phải `null`.
- Nếu kiểu **không phải record**: trả **`null`** (không phải mảng rỗng).

Vì vậy cách dùng an toàn là:

~~~java
static void showComponentCount(Class<?> type) {
    if (!type.isRecord()) {
        System.out.println("Not a record");
        return;
    }
    System.out.println(type.getRecordComponents().length);
}
~~~

Đoạn trên là **mảnh phương thức** cần đặt trong class thích hợp. Không viết `type.getRecordComponents().length` trước khi chắc chắn `type` biểu diễn record class; với class thường, điều đó gây `NullPointerException`.

Phân biệt **không phải record** và **record rỗng** hữu ích khi viết thư viện: hai trường hợp này có hợp đồng khác nhau, dù “số thành phần dữ liệu” nhìn qua đều có thể là 0.

## 5. Thông tin bạn nhận được từ `RecordComponent`

Mỗi `java.lang.reflect.RecordComponent` mô tả **một thành phần ghi trong header** của record. Những API thường dùng:

| API | Kết quả | Ví dụ / lưu ý |
| --- | --- | --- |
| `getName()` | Tên component | `id`, `name` |
| `getType()` | `Class<?>` của kiểu component sau khi xét erasure | `long.class` hoặc `String.class` |
| `getGenericType()` | `java.lang.reflect.Type` của kiểu khai báo, có thông tin generic | Với `T value` có thể là `TypeVariable<T>` |
| `getAccessor()` | `java.lang.reflect.Method` đại diện accessor | Record `User(long id)` có accessor `id()` |
| `getDeclaringRecord()` | `Class<?>` của record sở hữu component | Nhằm xác định component thuộc record nào |
| `getAnnotations()`, `getAnnotation(...)` | Annotation áp dụng cho **record component** | Cần khai báo target phù hợp và kiểm tra chính sách framework |
| `getAnnotatedType()` | Thông tin annotated type | Khác với annotation trên declaration khi dùng TYPE_USE |

**Đọc metadata không đồng nghĩa đọc dữ liệu từ một instance.** `getAccessor()` trả về mô tả `Method`, không tự gọi accessor hoặc lấy giá trị `id` của một đối tượng.

Nếu muốn thực sự gọi phương thức qua Reflection, có thể dùng `Method.invoke(instance)`, nhưng khi đó phải xử lý kiểm tra truy cập, exception từ accessor và giới hạn của hệ thống module. Không mặc định bật `setAccessible(true)` cho mọi kiểu: đó là một thao tác vượt mức chỉ kiểm tra cấu trúc và có thể bị Java module access rules từ chối.

### Kiểu generic: `getType()` khác `getGenericType()`

Với:

~~~java
record Box<T>(T value) {}
~~~

`getType()` của thành phần `value` là `Object.class` vì `T` không có bound cụ thể và bị xóa kiểu khi chạy (type erasure). `getGenericType()` giữ thông tin rằng kiểu khai báo là **type variable `T`**.

Ví dụ `record Tags(java.util.List<String> values) {}` có `getType() == List.class`, trong khi `getGenericType()` có thể cho thấy `List<String>` tại mức kiểu khai báo. **Không** giả định Reflection luôn biết type argument thực tế của từng instance `Box<String>`: type erasure vẫn áp dụng.

## 6. Chương trình Java 17+ đầy đủ, chạy độc lập

Tệp **`RecordInspectionDemo.java`** trình bày việc nhận diện nhiều loại `Class<?>`, phân biệt record rỗng với class thường, và dùng Reflection để in thông tin component.

~~~java
import java.lang.reflect.RecordComponent;
import java.util.List;

public class RecordInspectionDemo {

    record Person(long id, String name) {}
    record Empty() {}
    record Box<T>(T value) {}

    static class Regular {
        private final String name;
        Regular(String name) {
            this.name = name;
        }
        String name() {
            return name;
        }
    }

    enum State { NEW, DONE }

    static void inspect(Class<?> type) {
        System.out.println(type.getSimpleName() + ": " + type.isRecord());

        if (!type.isRecord()) {
            return;
        }

        RecordComponent[] components = type.getRecordComponents();
        System.out.println("  components=" + components.length);

        for (RecordComponent component : components) {
            System.out.println(
                "  " + component.getName()
                + " | raw=" + component.getType().getSimpleName()
                + " | generic=" + component.getGenericType().getTypeName()
                + " | accessor=" + component.getAccessor().getName() + "()"
            );
        }
    }

    static boolean isRecordInstance(Object value) {
        return value != null && value.getClass().isRecord();
    }

    public static void main(String[] args) {
        inspect(Person.class);
        inspect(Empty.class);
        inspect(Box.class);
        inspect(Regular.class);
        inspect(State.class);
        inspect(Person[].class);
        inspect(Record.class);
        inspect(int.class);

        System.out.println(
            "instance person=" + isRecordInstance(new Person(7L, "Lan"))
        );
        System.out.println("instance null=" + isRecordInstance(null));
        System.out.println(
            "generic instance="
                + isRecordInstance(new Box<>(List.of("a", "b")))
        );
    }
}
~~~

**Biên dịch và chạy** (lưu file UTF-8, sử dụng JDK 17 trở lên):

~~~bash
javac -encoding UTF-8 RecordInspectionDemo.java
java RecordInspectionDemo
~~~

**Kết quả dự kiến chính xác:**

~~~text
Person: true
  components=2
  id | raw=long | generic=long | accessor=id()
  name | raw=String | generic=java.lang.String | accessor=name()
Empty: true
  components=0
Box: true
  components=1
  value | raw=Object | generic=T | accessor=value()
Regular: false
State: false
Person[]: false
Record: false
int: false
instance person=true
instance null=false
generic instance=true
~~~

### Phân tích kết quả

1. `Person` là record có hai thành phần, in theo đúng thứ tự header `id` rồi `name`. Accessor có tên `id()`, `name()`, không phải getter kiểu JavaBeans như `getId()`.
2. `Empty` là record hợp lệ dù không có component, nên `isRecord() == true` và `getRecordComponents().length == 0`.
3. `Box<T>` vẫn là record. Reflection hiển thị `raw=Object` cho `T` không bound và `generic=T` cho thông tin kiểu tổng quát còn giữ trong khai báo.
4. `Regular` có trường `final` và phương thức `name()`, nhưng là class thường. Có cấu trúc trông giống record **không khiến** `isRecord()` chuyển thành `true`.
5. `State` là enum, `Person[]` là lớp mảng, `java.lang.Record` là lớp cơ sở, `int` là primitive. Tất cả không phải record class.
6. `isRecordInstance` kiểm tra giá trị runtime một cách null-safe; generic record instance vẫn là một instance của record class.

**Lưu ý về output:** chương trình chỉ in các chuỗi, boolean và tên kiểu Reflection được quy định rõ, không in giá trị hash hay identity của object nên kết quả không phụ thuộc địa chỉ bộ nhớ.

## 7. Ứng dụng: một helper kiểm tra Class cho công cụ mapping

Khi viết serializer hoặc mapper có cơ chế riêng dành cho record, nên có một điểm phân nhánh rõ:

~~~java
import java.lang.reflect.RecordComponent;
import java.util.Objects;

static String describeShape(Class<?> type) {
    Objects.requireNonNull(type, "type");

    if (!type.isRecord()) {
        return "ordinary type";
    }

    RecordComponent[] components = type.getRecordComponents();
    return "record with " + components.length + " component(s)";
}
~~~

Đây là **mảnh phương thức**, có thể đưa vào class chứa code mapping. Nhánh `isRecord()` bảo đảm `getRecordComponents()` khác null.

Nếu công cụ cần mô tả record thành một dạng schema, có thể lặp các component, đọc tên và kiểu, rồi xây dựng schema theo thứ tự header. Nếu công cụ cần tạo một đối tượng record từ dữ liệu, cần **một bước thiết kế khác**: tìm canonical constructor, kiểm tra kiểu từng giá trị đầu vào, xác thực dữ liệu và gọi constructor theo thứ tự components. Bản thân `Class.isRecord()` chỉ là **bước phân loại**, không tự khởi tạo đối tượng hay ánh xạ JSON/SQL.

Đối với thư viện xử lý **mọi** kiểu Java, tránh lạm dụng một nhánh record để thay thế logic cho class, enum, collection, array hoặc sealed type. Chúng có các hợp đồng và API phản chiếu khác nhau.

### Nhận diện kiểu phần tử của mảng một chiều

Nếu ứng dụng nhận `Person[].class` và muốn xác định mảng chứa record, helper nên nói rõ mục tiêu:

~~~java
static boolean isArrayOfRecords(Class<?> type) {
    return type != null
            && type.isArray()
            && type.getComponentType().isRecord();
}
~~~

Hàm này chỉ kiểm tra **mảng có kiểu phần tử trực tiếp là record**. Với `Person[][].class`, kiểu phần tử trực tiếp là `Person[].class` (vẫn là array class) nên hàm trả `false`. Nếu muốn nhận diện nhiều chiều, phải đi qua nhiều lần `getComponentType()` cho tới kiểu phần tử cuối cùng:

~~~java
static boolean isNestedArrayOfRecords(Class<?> type) {
    if (type == null || !type.isArray()) {
        return false;
    }
    do {
        type = type.getComponentType();
    } while (type.isArray());
    return type.isRecord();
}
~~~

Đây là hai helper minh họa độc lập. Chúng kiểm tra **khai báo kiểu phần tử**; không suy luận từ nội dung thực tế của một mảng `Object[]` có thể chứa nhiều instance record khác loại.

## 8. Nhận diện record không đồng nghĩa record được hỗ trợ tự động

Thấy `type.isRecord() == true` **không có nghĩa**:

- Một framework tự động biết constructor, tên field hoặc cú pháp JSON/SQL cần dùng.
- Record có constructor không tham số hoặc setter; record thường được tạo qua canonical constructor.
- Record luôn bất biến sâu. Component kiểu `List`, mảng hoặc object mutable vẫn cần chính sách snapshot/copy.
- Record chỉ có đúng các phương thức được sinh: record có thể khai báo thêm phương thức và ghi đè `equals`, `hashCode`, `toString` hoặc accessor theo hợp đồng Java.
- Record không bao giờ có annotation hoặc logic kiểm tra hợp lệ. Compact canonical constructor có thể chuẩn hóa/thẩm định dữ liệu.
- Bất kỳ class có cùng tên component hay khai báo `final` đều tự trở thành record.

Nếu tự viết mapper, phải xét dữ liệu nullable, primitive vs boxed, parameterized type, constructor visibility, module boundaries, annotation target và thông báo lỗi. `RecordComponent.getType()` hỗ trợ xác định kiểu ở runtime; `getGenericType()` hỗ trợ đọc kiểu khai báo nhưng không loại bỏ type erasure.

Với Spring/Jackson và các thư viện hiện đại, hãy kiểm tra **hỗ trợ record của phiên bản đang sử dụng**, cách áp dụng annotations và constructor binding theo tài liệu chính thức của chính framework. Không suy đoán khả năng tương thích chỉ dựa trên `isRecord()`.

## 9. Khác biệt với cách kiểm tra dễ gây lỗi

### 9.1. Không xác định bằng tên class

~~~java
boolean guess = type.getSimpleName().endsWith("Record");
~~~

Cách này sai vì tên kiểu tùy ý. Record có thể tên `Person`; class thường có thể tên `AuditRecord`. Chỉ `Class.isRecord()` kiểm tra bản chất kiểu.

### 9.2. Không chỉ kiểm tra có field final, constructor hoặc accessor

Một class thường có thể bất biến, có các trường `final`, constructor đủ tham số và phương thức `id()`; nó vẫn không phải record. `isRecord()` dựa trên thông tin kiểu mà Java runtime cung cấp.

### 9.3. Không tự thay thế bằng kiểm tra superclass theo thói quen

Mọi record class đều trực tiếp kế thừa `java.lang.Record`, nhưng nếu mục tiêu đơn giản là hỏi “có phải record class không?”, viết:

~~~java
boolean correct = type.isRecord();
~~~

rõ ràng và được API hỗ trợ trực tiếp hơn việc tự suy luận gián tiếp từ `getSuperclass()`. Đặc biệt, `Record.class.isRecord()` vẫn là `false`.

### 9.4. Không nhầm `getRecordComponents()` với `getDeclaredFields()`

Hai API khác mục đích:

- `getRecordComponents()` diễn đạt **hợp đồng dữ liệu trong record header**, có thứ tự khai báo, kiểu và accessor tương ứng.
- `getDeclaredFields()` phản chiếu **fields** được khai báo trong class và không đảm bảo danh sách theo thứ tự khai báo. Nó không phải cách tổng quát để tái tạo hợp đồng component của record.

Nếu tạo schema từ header record, nên bắt đầu từ `RecordComponent[]`. Nếu kiểm tra fields cho mục đích kỹ thuật đặc thù, áp dụng quy tắc `Field` riêng; đừng đồng nhất field với record component.

### 9.5. Không nhầm “record rỗng” với “không phải record”

~~~java
record Marker() {}

System.out.println(Marker.class.isRecord());                 // true
System.out.println(Marker.class.getRecordComponents().length); // 0
System.out.println(String.class.getRecordComponents() == null); // true
~~~

Record rỗng có metadata hợp lệ dạng mảng độ dài 0; class thông thường trả `null`. Đây là điểm phân biệt quan trọng khi xây công cụ kiểm tra kiểu.

## 10. Exception, quyền truy cập và chi phí phản chiếu

`isRecord()` chỉ kiểm tra metadata class và không tạo instance. `getRecordComponents()` cũng không gọi constructor hoặc accessor. Tuy nhiên, nếu tiếp tục dùng Reflection để **gọi** các phương thức hay constructor, các bước đó có thêm điều kiện:

1. `Method.invoke(...)` có thể thất bại vì quyền truy cập hoặc mã trong accessor ném exception (được bọc theo quy tắc Reflection).
2. Gọi constructor qua Reflection phải cung cấp đối số hợp lệ; compact constructor của record có thể ném `IllegalArgumentException` nếu dữ liệu không đạt yêu cầu.
3. Java module system có thể hạn chế reflective access tới các member không được công bố/mở cho module gọi. Không lấy việc đọc được tên component làm bằng chứng rằng gọi accessor/constructor tùy ý đều được phép.
4. Kiểm tra metadata trong vòng lặp rất lớn có thể được tối ưu bằng cache theo `Class<?>` nếu đo được lợi ích; tránh giữ tham chiếu class loader lâu hơn cần thiết trong hệ thống plugin/hot reload.
5. Khi dữ liệu đầu vào là tên class tùy ý, việc tải class với `Class.forName(...)` có hành vi class loading/initialization khác với chỉ dùng đối tượng `Class` sẵn có. Không nên tải class tùy ý do người dùng cung cấp nếu không có chính sách cho phép rõ ràng.

Đối với bài kiểm tra `isRecord()` thuần túy, không cần dùng `setAccessible(true)`, đọc fields riêng tư, gọi constructor hoặc duyệt toàn bộ method của class.

## 11. Kiểm thử thiết kế: trường hợp nào phải có?

Khi viết công cụ dùng `Class.isRecord()`, nên kiểm thử ít nhất:

| Input | Kỳ vọng |
| --- | --- |
| Record có nhiều component | `isRecord() == true`, đúng số lượng và thứ tự components |
| `record Empty()` | `true` và mảng components rỗng, **không null** |
| Generic record `Box<T>` | `true`; `getType` có thể là erased type, `getGenericType` giữ type variable |
| Class bất biến thông thường | `false` dù có `final` và accessor |
| Enum hoặc interface | `false` |
| `Record.class` | `false` |
| `Person[].class` | `false`; phần tử trực tiếp là record |
| `int.class` và `void.class` | `false` |
| Đối tượng `null` truyền cho helper an toàn | Trả `false`, không NPE |
| Class thường gọi `getRecordComponents()` | Trả `null` |
| Record override accessor / `equals` | Vẫn là record vì bản chất khai báo không thay đổi |

Nếu thư viện làm việc qua nhiều class loader hoặc module, hãy bổ sung test sử dụng các class thực sự trong môi trường đó để xác nhận **quyền truy cập khi invoke**. Các test đó khác với việc xác định class có là record.

## 12. Bài tập thực hành

**Bài 1 — Thay class bằng record.** Khai báo `class ProductView` với `id`, `name` bất biến, rồi khai báo `record ProductViewRecord(long id, String name) {}`. Chạy `isRecord` trên cả hai và giải thích vì sao class có API tương tự vẫn trả `false`.

**Bài 2 — Record rỗng.** Viết `record Empty() {}`. Dự đoán `Empty.class.isRecord()`, `Empty.class.getRecordComponents().length`, `String.class.getRecordComponents()`. Phân biệt ba kết quả `true`, `0` và `null`.

**Bài 3 — Mảng record hai chiều.** Dùng `Person.class`, `Person[].class`, `Person[][].class`. Thử `isRecord()` trực tiếp và helper `isNestedArrayOfRecords`; giải thích tại sao hai phép thử có mục đích khác nhau.

**Bài 4 — Generic component.** Tạo `record Pair<T>(T left, T right) {}`. In `getType()` và `getGenericType()` của từng component; giải thích type erasure, và vì sao `isRecord()` không phụ thuộc type parameter.

**Bài 5 — Tạo schema.** Viết helper nhận `Class<?>`, từ chối kiểu không phải record, rồi tạo chuỗi `name:type` theo đúng thứ tự component. Thử với `record Customer(long id, String email) {}` và `record Empty() {}`; không gọi constructor và không đọc instance.

## Tài liệu chính thức còn áp dụng

- [Java SE 25 API — Class.isRecord và Class.getRecordComponents](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#isRecord()): định nghĩa record class, cách nhận diện và cấu trúc kết quả.
- [Java SE 25 API — RecordComponent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html): tên, kiểu, generic type, accessor và metadata của component.
- [Oracle — Record Classes, Java 25](https://docs.oracle.com/en/java/javase/25/language/records.html): tính năng record và Reflection liên quan.
- [Java SE 25 API — java.lang.Record](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html): lớp cơ sở chung của record classes.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): thiết kế được chuẩn hóa trong Java 16.
