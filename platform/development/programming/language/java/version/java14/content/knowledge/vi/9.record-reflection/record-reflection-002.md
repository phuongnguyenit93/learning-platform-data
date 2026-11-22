# Lấy thành phần theo thứ tự bằng `getRecordComponents()`

## 1. Mục tiêu và phạm vi

Khi cần tạo giao diện dữ liệu, đọc metadata của một `record`, hoặc tìm canonical constructor bằng reflection, ta cần biết **record có những thành phần nào và chúng được khai báo theo thứ tự nào**. Java cung cấp phương thức `Class.getRecordComponents()` để giải quyết trực tiếp yêu cầu này.

Ví dụ, với:

~~~java
record Invoice(String code, int quantity, boolean paid) {}
~~~

lệnh:

~~~java
RecordComponent[] components = Invoice.class.getRecordComponents();
~~~

trả các `RecordComponent` tương ứng với `code`, `quantity`, `paid` **theo đúng thứ tự trong record header**. Mỗi phần tử mô tả một thành phần (tên, kiểu khai báo, accessor, annotation...), chứ không chứa sẵn giá trị của một `Invoice` cụ thể.

**Phiên bản quan trọng:** record và `getRecordComponents()` là API đã ổn định từ **Java 16**, được hỗ trợ trên Java 17 và các bản Java hiện đại. Đây là kiến thức còn áp dụng hiện nay. Nếu dự án buộc biên dịch với `--release 14`, không thể dùng mã ví dụ này như tính năng ổn định; những chương trình đầy đủ trong bài được kiểm tra bằng **`javac --release 17`** và không cần `--enable-preview`.

## 2. Thứ tự được bảo đảm từ record header

Một record header liệt kê các *record components* theo cú pháp kiểu và tên:

~~~java
record Purchase(String id, int units, List<String> labels) {}
~~~

Bảng metadata mà `getRecordComponents()` đại diện:

| Chỉ số mảng | Tên component | Kiểu khai báo |
| ---: | --- | --- |
| 0 | `id` | `String` |
| 1 | `units` | `int` |
| 2 | `labels` | `List<String>` |

Thứ tự này là một **bảo đảm của API**, không phải suy đoán từ thứ tự fields trong class file hay thứ tự methods mà JVM trả về. Nếu tác giả đổi header thành `record Purchase(int units, String id, List<String> labels) {}` thì thứ tự kết quả cũng đổi thành `units`, `id`, `labels`.

Một record class còn có thể chứa phương thức nghiệp vụ và `static` field. Ví dụ:

~~~java
record Product(String sku, int quantity) {
    static final String KIND = "product";
    String summary() {
        return sku + ":" + quantity;
    }
}
~~~

`getRecordComponents()` trả **hai** phần tử `sku` và `quantity`, **không** trả `KIND` hay `summary()`. Phương thức này đọc danh sách component của **record class**, không phải toàn bộ các thành viên của class.

Mỗi component thường liên quan đến một field `private final` và một accessor công khai cùng tên (ví dụ `sku()`). Tuy nhiên, `RecordComponent` là **metadata**, không phải đối tượng `Field` và cũng không phải giá trị mà accessor trả về.

## 3. Kiểm tra record trước khi lặp

Chữ ký của phương thức:

~~~java
public RecordComponent[] getRecordComponents()
~~~

Phương thức thuộc `java.lang.Class`. Ba trường hợp rất dễ nhầm:

| Class được phản chiếu | `isRecord()` | `getRecordComponents()` |
| --- | --- | --- |
| `record A(int x) {}` | `true` | Mảng độ dài 1 |
| `record Empty() {}` | `true` | **Mảng rỗng** độ dài 0 |
| `String.class`, hoặc một class thường | `false` | **`null`** |

Do đó, record **không có component** và class **không phải record** là hai trạng thái khác nhau. Không được cho rằng mọi kết quả đều là mảng rồi lập tức truy cập `.length`: nếu nhận `String.class`, thao tác đó sẽ gây `NullPointerException`.

Đoạn phương thức minh họa dưới đây thích hợp đặt trong một class tiện ích (chưa phải chương trình `main` độc lập):

~~~java
static String[] componentNames(Class<?> type) {
    if (!type.isRecord()) {
        throw new IllegalArgumentException("Expected a record class");
    }
    return java.util.Arrays.stream(type.getRecordComponents())
            .map(java.lang.reflect.RecordComponent::getName)
            .toArray(String[]::new);
}
~~~

Với `record Empty() {}`, kết quả là `String[0]`; với class thường, chương trình báo lỗi đầu vào có ý nghĩa. Có thể thay `throw` bằng cách xử lý khác nếu hợp đồng ứng dụng cần phân biệt hai loại input theo cách riêng.

Đặc biệt, `java.lang.Record.class` **không phải chính một record class**, nên `Record.class.isRecord() == false`; nó là superclass mà các record class kế thừa ngầm.

## 4. Đọc metadata trong `RecordComponent`

Lớp `java.lang.reflect.RecordComponent` cung cấp các API còn được hỗ trợ:

| API | Kiểu kết quả | Công dụng |
| --- | --- | --- |
| `getName()` | `String` | Tên đúng như khai báo trong header |
| `getType()` | `Class<?>` | Kiểu runtime; `List<String>` có `Class` là `List.class` |
| `getGenericType()` | `Type` | Kiểu generic khai báo; có thể thấy `List<java.lang.String>` |
| `getAccessor()` | `Method` | Phương thức accessor, ví dụ `quantity()` |
| `getDeclaringRecord()` | `Class<?>` | Record class khai báo component |
| `getAnnotations()`, `getAnnotation(...)` | Annotation(s) | Annotation có thể đọc qua reflection trên component |
| `getAnnotatedType()` | `AnnotatedType` | Thông tin chú thích tại vị trí sử dụng kiểu |

Ví dụ `List<String> labels`: `getType().getTypeName()` trả `java.util.List`, còn `getGenericType().getTypeName()` trả `java.util.List<java.lang.String>`. Đây là **thông tin ở mức khai báo**; nó không chứng minh các phần tử thực tế trong mỗi instance `List` đều là object có đúng runtime class `String`, cũng không loại bỏ quy tắc type erasure của Java.

`getAccessor()` trả `Method` phản chiếu accessor tương ứng. Nếu accessor được viết tường minh trong record, method đó vẫn được `getAccessor()` trả về. Khi sử dụng `Method.invoke(instance)`, Java thực sự gọi method; lúc đó phải áp dụng quy tắc quyền truy cập và ngoại lệ thông thường của reflection.

Muốn đọc một annotation ở vị trí **record component**, annotation đó phải có target áp dụng cho `ElementType.RECORD_COMPONENT` và `RetentionPolicy.RUNTIME` để sẵn có lúc chạy. Annotation trên field, method hoặc type-use là những vị trí metadata khác; không nên đánh đồng tất cả.

## 5. Chương trình Java 17+ kiểm tra thứ tự trực tiếp

Tạo tệp **`RecordComponentOrderDemo.java`**:

~~~java
import java.lang.reflect.RecordComponent;
import java.util.List;

public class RecordComponentOrderDemo {
    public record Purchase(String id, int units, List<String> labels) {
        public static final String KIND = "purchase";

        public String description() {
            return id + ":" + units;
        }
    }

    public record Empty() {}

    public static void main(String[] args) {
        Class<?> type = Purchase.class;
        System.out.println("isRecord=" + type.isRecord());

        RecordComponent[] components = type.getRecordComponents();
        for (int i = 0; i < components.length; i++) {
            RecordComponent component = components[i];
            System.out.println(i
                    + " | " + component.getName()
                    + " | raw=" + component.getType().getTypeName()
                    + " | generic=" + component.getGenericType().getTypeName()
                    + " | accessor=" + component.getAccessor().getName());
        }

        System.out.println("count=" + components.length);
        System.out.println(
                "emptyCount=" + Empty.class.getRecordComponents().length);
        System.out.println(
                "nonRecordIsNull="
                + (String.class.getRecordComponents() == null));
        System.out.println(
                "RecordSuperclassIsRecord=" + Record.class.isRecord());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 RecordComponentOrderDemo.java
java RecordComponentOrderDemo
~~~

Stdout đã kiểm tra:

~~~text
isRecord=true
0 | id | raw=java.lang.String | generic=java.lang.String | accessor=id
1 | units | raw=int | generic=int | accessor=units
2 | labels | raw=java.util.List | generic=java.util.List<java.lang.String> | accessor=labels
count=3
emptyCount=0
nonRecordIsNull=true
RecordSuperclassIsRecord=false
~~~

Giải thích:

1. `isRecord=true` xác nhận `Purchase` là record class.
2. Thứ tự của mảng là **`id` → `units` → `labels`**, không sort alphabet. Chỉ số mảng bắt đầu từ `0`.
3. `KIND` là static field, `description()` là phương thức tự viết; cả hai không xuất hiện trong `components`.
4. Với component `labels`, kiểu raw hiển thị `java.util.List`, kiểu generic giữ `java.lang.String` trong tham số.
5. Record `Empty` không có component nhưng kết quả vẫn là mảng không null, dài `0`.
6. `String.class` không phải record nên kết quả `getRecordComponents() == null` là `true`.
7. `Record.class` là superclass có tính năng đặc biệt trong Java, nhưng bản thân nó không được khai báo bằng `record` và `isRecord()` trả `false`.

Tất cả dữ liệu ở bước này là **metadata của class**, chưa đọc giá trị của một `Purchase` cụ thể.

## 6. Đọc giá trị từ một instance theo vị trí component

Nếu cần hiển thị dữ liệu của một instance record, dùng mảng metadata theo thứ tự đã biết, sau đó gọi accessor của từng component:

~~~java
RecordComponent[] parts = invoice.getClass().getRecordComponents();
for (int i = 0; i < parts.length; i++) {
    Object value = parts[i].getAccessor().invoke(invoice);
    // value ứng với vị trí i trong record header
}
~~~

Đoạn này **minh họa trong một phương thức**: cần import `RecordComponent`, có đối tượng `invoice` hợp lệ, và xử lý ngoại lệ của `Method.invoke`. `getAccessor()` trả method không có đối số. Với accessor trả kiểu primitive như `int`, `Method.invoke` boxing kết quả thành wrapper như `Integer` để trả về `Object`.

Từ metadata component, ta cũng có thể tìm **canonical constructor**. Dãy tham số của constructor này tương ứng **kiểu các component theo đúng thứ tự header**. Vì vậy, có thể dùng:

~~~java
Class<?>[] types = java.util.Arrays.stream(parts)
        .map(RecordComponent::getType)
        .toArray(Class<?>[]::new);
java.lang.reflect.Constructor<?> ctor =
        invoice.getClass().getDeclaredConstructor(types);
~~~

Đoạn trên cũng là **mã minh họa**, không có `main` riêng. `getDeclaredConstructor` nhận các `Class<?>` theo **vị trí**; đổi thứ tự các kiểu có thể khiến không tìm được constructor phù hợp hoặc chọn nhầm một overload nếu code không được thiết kế cẩn thận. Phương thức này không tự tạo instance; muốn tạo instance cần gọi `newInstance(...)` với các giá trị tương ứng.

### Chương trình đầy đủ: accessor, annotation và constructor

Tạo tệp **`RecordComponentValuesDemo.java`**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

public class RecordComponentValuesDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface ColumnLabel {
        String value();
    }

    public record Invoice(
            @ColumnLabel("Code") String code,
            int quantity,
            boolean paid) {}

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Invoice invoice = new Invoice("INV-7", 12, true);
        Class<?> type = invoice.getClass();
        RecordComponent[] parts = type.getRecordComponents();

        for (int i = 0; i < parts.length; i++) {
            RecordComponent part = parts[i];
            Object value = part.getAccessor().invoke(invoice);
            ColumnLabel label = part.getAnnotation(ColumnLabel.class);
            String display = label == null ? "-" : label.value();

            System.out.println(i + ":" + part.getName()
                    + "=" + value + "; label=" + display);
        }

        Class<?>[] constructorTypes = Arrays.stream(parts)
                .map(RecordComponent::getType)
                .toArray(Class<?>[]::new);
        Constructor<?> canonical =
                type.getDeclaredConstructor(constructorTypes);
        Object rebuilt = canonical.newInstance("INV-8", 20, false);
        System.out.println("rebuilt=" + rebuilt);
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 RecordComponentValuesDemo.java
java RecordComponentValuesDemo
~~~

Stdout đã kiểm tra:

~~~text
0:code=INV-7; label=Code
1:quantity=12; label=-
2:paid=true; label=-
rebuilt=Invoice[code=INV-8, quantity=20, paid=false]
~~~

Giải thích:

- `Invoice` có header `(String code, int quantity, boolean paid)`, nên danh sách metadata là **`code, quantity, paid`** theo thứ tự đó.
- `Method.invoke(invoice)` đọc giá trị qua accessor trong instance `invoice`, tạo các giá trị `INV-7`, `12` và `true`.
- Annotation `@ColumnLabel("Code")` có runtime retention và target RECORD_COMPONENT, nên `getAnnotation(ColumnLabel.class)` trả nhãn `Code` cho vị trí `0`; hai component còn lại không có annotation này nên in `-`.
- Dãy kiểu `String.class, int.class, boolean.class` lấy từ `getType()` được dùng với `getDeclaredConstructor(...)` để tìm canonical constructor.
- `newInstance("INV-8", 20, false)` tạo một instance mới với đúng vị trí tham số, sau đó `toString()` hiển thị record theo ví dụ.

Đây là ví dụ phản chiếu trên **một public nested record** trong class public, để minh họa đường đi thành công. Một thư viện dùng reflection trong môi trường thực cần xử lý quyền truy cập và lỗi của method/constructor: `IllegalAccessException`, `InvocationTargetException`, `InstantiationException` hoặc các lỗi constructor khác có thể xuất hiện tùy kiểu và dữ liệu.

## 7. Không dùng `getDeclaredFields()` làm nguồn thứ tự record header

Một lỗi phổ biến là suy ra thứ tự từ các API reflection thông thường:

| API | Dữ liệu được trả về | Bảo đảm thứ tự record header? |
| --- | --- | --- |
| `getRecordComponents()` | Các record component được khai báo | **Có** |
| `getDeclaredFields()` | Các field khai báo trong class (kể cả static field khác) | **Không** |
| `getDeclaredMethods()` | Method khai báo trong class (gồm accessor, method tự viết) | **Không** |
| `getMethods()` | Method public và các method được kế thừa phù hợp | **Không** |

Ngay cả khi JVM cụ thể tình cờ trả fields “đúng thứ tự”, Java API **không bảo đảm** thứ tự của `getDeclaredFields()`. Fields còn có thể chứa các field khác ngoài component, chẳng hạn `KIND` trong ví dụ. `getDeclaredMethods()` cũng không phải bảng component: nó có thể gồm `description()`, và thứ tự của methods không được bảo đảm.

Việc sort mảng `getRecordComponents()` theo tên chỉ phù hợp nếu ứng dụng **muốn một thứ tự khác** theo yêu cầu nghiệp vụ. Nếu mục tiêu là “theo thứ tự khai báo”, hãy giữ nguyên mảng API trả về.

Không nên đồng nhất “component” với “giá trị field”: `RecordComponent` mô tả một chỗ trong header; muốn lấy **giá trị hiện tại của instance**, hãy dùng accessor trên instance thích hợp.

## 8. Giới hạn và quyết định thiết kế

**Thứ tự có thể thay đổi khi định nghĩa record thay đổi.** Ví dụ:

~~~java
record Event(String id, long time) {}
~~~

và phiên bản thay thế:

~~~java
record Event(long time, String id) {}
~~~

không phải hai khai báo đặt cùng tệp/package; đây là **hai phiên bản khác nhau** của kiểu. API trả đúng thứ tự của từng phiên bản, nhưng dữ liệu được mã hóa thuần theo vị trí có thể mất tương thích sau thay đổi header. Với các định dạng lưu trữ hoặc giao tiếp dài hạn, nên dùng schema có version hoặc ánh xạ theo tên đã công bố, thay vì coi vị trí `0` vĩnh viễn là trường `id`.

**Generic metadata là thông tin khai báo.** `getGenericType()` có thể phản ánh `List<String>` hoặc biến kiểu `T`. Nó không kiểm chứng toàn bộ các giá trị runtime trong collection. Nếu cần kiểm tra giá trị, phải đọc instance và kiểm tra dữ liệu thực tế.

**Reflection chịu access control.** Với record không public hoặc nằm trong module không cho phép truy cập thích hợp, việc gọi `getAccessor().invoke(...)` hoặc `Constructor.newInstance(...)` có thể không được phép. Không xem `setAccessible(true)` như giải pháp chắc chắn; nên tôn trọng ranh giới module hoặc thiết kế API public thích hợp.

**Accessor có thể được viết tường minh.** Khi tác giả record tự khai báo accessor, gọi `getAccessor().invoke(...)` là **thực thi method**: method có thể tính toán hoặc ném ngoại lệ. Metadata record không bảo đảm rằng mọi accessor đều không có tác dụng phụ.

**Record rỗng không phải lỗi.** `record Empty() {}` có mảng component rỗng. Công cụ phản chiếu nên xử lý tự nhiên trường hợp này nếu hợp đồng cho phép, đồng thời phân biệt với class không phải record trả `null`.

**Annotation có đích và retention riêng.** `getAnnotation(...)` trên `RecordComponent` chỉ phù hợp với annotation có mặt trên chính vị trí component và được giữ đến runtime. Nếu bạn cần annotation của accessor method hoặc field, đó là đường reflection riêng, không nên lẫn vào việc xác định thứ tự component.

## 9. Checklist thực hành và lỗi thường gặp

1. **Bắt đầu bằng `Class<?>` hợp lệ:** lấy từ `MyRecord.class` hoặc `instance.getClass()`; kiểm tra `isRecord()` khi không chắc kiểu.
2. **Không nhầm `null` với mảng rỗng:** non-record → `null`; record rỗng → `RecordComponent[0]`.
3. **Chỉ lấy các component bằng API phù hợp:** `getRecordComponents()` trả thứ tự header, `getDeclaredFields()` không có bảo đảm đó.
4. **Duyệt bằng chỉ số khi cần vị trí:** `for (int i = 0; i < parts.length; i++)` giúp lưu lại vị trí `i` một cách tường minh.
5. **Đọc đúng metadata:** `getName()` cho tên, `getType()` cho runtime class, `getGenericType()` cho kiểu khai báo generic, `getAccessor()` cho method.
6. **Phân biệt schema và value:** API metadata không tự đọc giá trị; phải gọi accessor trên instance phù hợp.
7. **Nếu tìm constructor, giữ thứ tự các kiểu:** `Arrays.stream(parts).map(RecordComponent::getType)` cho dãy kiểu của canonical constructor theo thứ tự header.
8. **Nếu xây công cụ chung, xử lý lỗi reflection:** quyền truy cập, lỗi constructor và ngoại lệ phát sinh khi gọi accessor đều có thể xảy ra.
9. **Nếu lưu dữ liệu theo vị trí, quản lý thay đổi schema:** một lần đổi thứ tự header có thể đổi cách dữ liệu được diễn giải.
10. **Kiểm tra phiên bản Java:** API ổn định trên Java 16+, ví dụ bài dùng Java 17+; không dùng trong mã bắt buộc tương thích Java 14 không preview.

## 10. Tự kiểm tra nhanh

**Câu 1.** Với `record Pair(int right, int left) {}`, component tại vị trí `0` có tên gì? **`right`**, theo thứ tự header, không theo alphabet.

**Câu 2.** Với `record Empty() {}`, `getRecordComponents() == null` có đúng không? **Không**; API trả mảng độ dài `0`.

**Câu 3.** Với `String.class`, `getRecordComponents()` trả gì? **`null`**, vì `String` không phải record.

**Câu 4.** Làm sao đọc tên mà không đọc giá trị? **`RecordComponent.getName()`**. Làm sao đọc giá trị từ instance? **`getAccessor().invoke(instance)`**, khi quyền truy cập hợp lệ.

**Câu 5.** `getType()` của `List<String>` có hiển thị `String` trong tham số generic không? **Không**; muốn kiểu khai báo đầy đủ hãy dùng **`getGenericType()`**.

**Câu 6.** Có thể dùng dãy kiểu từ `getType()` theo thứ tự component để tìm canonical constructor? **Có**, vì thứ tự tham số constructor tương ứng record header.

**Câu 7.** Vì sao không dùng `getDeclaredFields()` để lấy thứ tự? Vì **không có bảo đảm thứ tự mảng** và tập field có thể gồm các field khác ngoài component.

## Tài liệu chính thức

- Oracle Java SE 17, `Class.getRecordComponents()` và `Class.isRecord()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getRecordComponents()
- Oracle Java SE 17, lớp `java.lang.reflect.RecordComponent`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html
- Java Language Specification 17, §8.10 *Record Classes* và §8.10.1 *Record Components*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10
- Oracle Java SE 17, *Record Classes*: https://docs.oracle.com/en/java/javase/17/language/records.html
- OpenJDK JEP 395, *Records* (hoàn thiện tính năng từ Java 16): https://openjdk.org/jeps/395