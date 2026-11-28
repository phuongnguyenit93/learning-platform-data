# Khai báo annotation tùy chỉnh và kiểm tra metadata

Trong Java 27, **annotation** là một cách gắn **metadata có cấu trúc** lên khai báo hoặc một vị trí sử dụng kiểu dữ liệu. Metadata có thể mô tả tên nghiệp vụ, cấu hình xử lý, vai trò, quy tắc kiểm tra hoặc thông tin dành cho công cụ tạo mã. Một annotation không tự chạy logic: **compiler, annotation processor, framework hoặc chính chương trình** phải đọc và diễn giải dữ liệu đó.

Ví dụ, thay vì duy trì một bảng ánh xạ riêng giữa tên thao tác và method, ta có thể gắn thông tin ngay trên method:

```java
@Operation(name = "create-order", priority = 10)
public void createOrder() {
    // Logic nghiệp vụ
}
```

`@Operation` ở đây là annotation do ứng dụng tự định nghĩa, không phải một annotation có sẵn trong Java. Để đoạn mã có ý nghĩa, ta phải **khai báo annotation**, xác định **nơi được gắn**, **thời gian giữ metadata**, rồi xây dựng phần **đọc và xử lý** nó.

Bài học thuộc chương **Annotation và truy cập động**, module **JAVA_VERSION_JAVA27 – Java 27 và các kiến thức liên quan**. Nội dung sử dụng các cơ chế đang được hỗ trợ trong Java SE 27: khai báo `@interface`, các meta-annotations, reflection qua `AnnotatedElement`, repeatable annotations, metadata trên record components và phân biệt đọc lúc biên dịch với đọc lúc chạy. Không dựa vào cơ chế phản chiếu truy cập trái phép hoặc công cụ cũ để xây dựng giải pháp mới.

## 1. Annotation là metadata, không phải câu lệnh thực thi

Một annotation mô tả thông tin về chương trình. Nó **không phải** một lệnh gọi method:

```java
@Deprecated
public void oldEntryPoint() {
    // Một method của ứng dụng
}
```

`@Deprecated` có ý nghĩa đặc biệt vì các công cụ Java nhận biết nó và có thể cảnh báo khi sử dụng API. Tương tự, `@Override` được compiler kiểm tra. Ngược lại, **annotation tùy chỉnh không tự động tạo ra hành vi** nếu không có thành phần đọc và áp dụng.

Chẳng hạn:

```java
@interface RequiresPermission {
    String value();
}

@RequiresPermission("orders:write")
void deleteOrder() {
    // Chưa có hệ thống nào kiểm tra quyền ở đây.
}
```

Việc gắn `@RequiresPermission` **không tự bảo vệ** `deleteOrder()`. Muốn kiểm soát truy cập, ứng dụng/framework phải kiểm tra quyền ở đúng ranh giới thực thi; trong hệ thống an toàn, không được dùng sự hiện diện của metadata để thay thế cơ chế xác thực và ủy quyền thực tế.

### 1.1. Ba giai đoạn thường gặp

```text
Khai báo annotation
        |
        v
Gắn annotation vào class / method / field / ...
        |
        +---- Công cụ lúc biên dịch ----> Sinh mã / cảnh báo / kiểm tra
        |
        +---- Reflection lúc chạy -----> Đọc metadata / cấu hình hành vi
        |
        v
Ứng dụng quyết định ý nghĩa và trách nhiệm thực thi
```

Annotation nên làm rõ **hợp đồng metadata**, còn code tiêu thụ annotation chịu trách nhiệm xác thực giá trị, xử lý lỗi và thực hiện hành vi.

## 2. Khai báo annotation tùy chỉnh bằng `@interface`

Trong Java, một **annotation interface** được khai báo bằng từ khóa `@interface`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Operation {
    String name();
    int priority() default 0;
}
```

Đặt khai báo `public @interface Operation` vào file `Operation.java` nếu dùng nó như một top-level public annotation. Những phần chính:

- `@interface Operation` định nghĩa một loại annotation mới.
- `String name();` định nghĩa **annotation element** tên `name` có kiểu `String`, **bắt buộc cung cấp** khi gắn annotation.
- `int priority() default 0;` định nghĩa element có **giá trị mặc định**; người dùng có thể bỏ qua.
- `@Target(ElementType.METHOD)` hạn chế annotation chỉ được đặt ở khai báo method.
- `@Retention(RetentionPolicy.RUNTIME)` yêu cầu metadata được lưu để có thể đọc bằng reflection lúc chạy.

Sử dụng:

```java
@Operation(name = "create-order", priority = 10)
public void createOrder() {
}

@Operation(name = "list-orders")
public void listOrders() {
}
```

Trong trường hợp thứ hai, `priority()` nhận giá trị mặc định `0`. Giá trị mặc định được khai báo trong **annotation interface**, không phải tại vị trí dùng.

Một annotation interface khác với functional interface: các khai báo `name()` và `priority()` là **elements mô tả metadata**, không phải callback methods mà ta triển khai bằng lambda. Annotation interface cũng không được khai báo generic hoặc tự chọn superinterface bằng `extends`.

## 3. Annotation elements: kiểu dữ liệu và giới hạn

Không thể đặt bất kỳ object Java nào vào một annotation. Theo Java Language Specification, kiểu của một annotation element chỉ có thể thuộc các nhóm sau:

| Nhóm hợp lệ | Ví dụ khai báo element |
| --- | --- |
| Primitive, trừ `void` | `int retries();`, `boolean enabled();` |
| `String` | `String description();` |
| `Class` hoặc dạng tham số hóa phù hợp | `Class<?> handler();` |
| Enum | `Severity level();` |
| Một annotation interface khác | `Constraint rule();` |
| Mảng **một chiều** của những kiểu trên | `String[] tags();`, `int[] codes();` |

Ví dụ một loại annotation dùng đa dạng các kiểu hợp lệ:

```java
enum Severity {
    LOW, MEDIUM, HIGH
}

@interface Constraint {
    int minimum() default 0;
}

@interface PropertyInfo {
    String name();
    Severity severity() default Severity.MEDIUM;
    Class<?> converter() default String.class;
    Constraint rule() default @Constraint(minimum = 1);
    String[] aliases() default {};
}
```

Sử dụng:

```java
@PropertyInfo(
        name = "customer-id",
        severity = Severity.HIGH,
        converter = Long.class,
        rule = @Constraint(minimum = 100),
        aliases = {"id", "customerId"})
String customerId;
```

Các kiểu **không hợp lệ** khi làm annotation element gồm `List<String>`, `Map`, object nghiệp vụ tùy ý, mảng hai chiều như `String[][]`, và phương thức nhận tham số như `String name(int index);`. Không thể khai báo một element với `throws` clause.

### 3.1. Giá trị annotation phải biểu diễn được tại thời điểm biên dịch

Annotation values không phải kết quả được tính tùy ý lúc runtime. Ví dụ:

```java
static final String PREFIX = "order";
static final String ROUTE = PREFIX + "-create";

@Operation(name = ROUTE)
void create() {}
```

Đây là giá trị hằng kiểu `String` hợp lệ. Trái lại, không thể truyền kết quả gọi method runtime:

```java
// @Operation(name = System.getenv("OPERATION_NAME"))
// void create() {} // Không hợp lệ: expression không phải giá trị annotation cho phép
```

Với kiểu `Class`, dùng **class literal** như `String.class`. Với enum, dùng **enum constant**. Với annotation lồng nhau, dùng một annotation value như `@Constraint(minimum = 2)`. Với mảng, cung cấp các giá trị hợp lệ theo cú pháp mảng dành cho annotation.

### 3.2. Annotation elements không nhận `null`

Không có giá trị annotation kiểu `null`. Nếu cần biểu diễn “không cấu hình”, hãy thiết kế một giá trị mặc định rõ nghĩa, ví dụ mảng rỗng, một enum constant `UNSPECIFIED` hoặc một sentinel kiểu `Class<?>` phù hợp:

```java
@interface OptionalHandler {
    Class<?> type() default Void.class;
}
```

Nếu sử dụng sentinel, cần giải thích cách diễn giải nó trong tài liệu API. Không suy diễn rằng mọi tên `Void.class` có nghĩa “không có” trong những annotation khác.

## 4. Ba cách viết annotation tại nơi sử dụng

Java có ba hình thức cú pháp thông dụng:

### 4.1. Marker annotation: không có element

```java
@interface Auditable {}

@Auditable
class InvoiceService {}
```

`@Auditable` là marker annotation: chỉ sự hiện diện của nó đã mang thông tin.

### 4.2. Single-element annotation: element `value()`

```java
@interface Label {
    String value();
}

@Label("backend")
class BackendService {}
```

Khi element duy nhất được truyền có tên `value`, Java cho phép viết `@Label("backend")` thay cho `@Label(value = "backend")`.

### 4.3. Normal annotation: các cặp tên–giá trị

```java
@interface RetryPolicy {
    int attempts();
    long delayMillis() default 0L;
}

@RetryPolicy(attempts = 3, delayMillis = 200L)
class JobWorker {}
```

**Lưu ý:** `@RetryPolicy` chỉ lưu metadata. Chính công cụ/ứng dụng tiêu thụ mới quyết định có retry thật không, retry những exception nào, có backoff/jitter hay không và có bảo đảm thao tác idempotent hay không.

### 4.4. Với mảng, một phần tử có thể viết ngắn gọn

```java
@interface Tags {
    String[] value();
}

@Tags({"java", "reflection"})
class MetadataTopic {}

@Tags("java")
class OneTagTopic {}
```

Hai dạng đều hợp lệ: annotation element có kiểu mảng có thể dùng một giá trị đơn lẻ thay cho phần khởi tạo mảng một phần tử theo cú pháp annotation.

## 5. `@Target`: annotation được gắn vào đâu?

Meta-annotation `@Target` dùng enum `ElementType` để kiểm soát **vị trí cú pháp** mà một annotation được phép xuất hiện.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@interface Feature {
    String value();
}
```

Annotation `@Feature` ở trên có thể gắn lên khai báo class/interface/record/enum hoặc method, nhưng không được tự ý gắn vào tham số method nếu không thêm `ElementType.PARAMETER`.

| `ElementType` | Vị trí áp dụng |
| --- | --- |
| `TYPE` | Khai báo class, interface, enum, record và annotation interface |
| `METHOD` | Khai báo method |
| `FIELD` | Khai báo field, bao gồm enum constant |
| `CONSTRUCTOR` | Khai báo constructor |
| `PARAMETER` | Khai báo tham số hình thức |
| `LOCAL_VARIABLE` | Khai báo biến cục bộ |
| `ANNOTATION_TYPE` | Khai báo annotation interface |
| `PACKAGE` | Khai báo package |
| `MODULE` | Khai báo module |
| `TYPE_PARAMETER` | Khai báo type parameter như `<T>` |
| `TYPE_USE` | Vị trí sử dụng kiểu, gồm các type arguments |
| `RECORD_COMPONENT` | Một component trong record header |

Nếu **không** có `@Target`, annotation có thể dùng tại các **declaration contexts** mà JLS cho phép, nhưng **không mặc nhiên** được dùng ở mọi `TYPE_USE` context. Đối với thư viện, nên khai báo `@Target` rõ ràng để tránh vô tình cho phép annotation xuất hiện ở nơi công cụ xử lý không hỗ trợ.

### 5.1. Phân biệt `TYPE` với `TYPE_USE`

`TYPE` mô tả **khai báo một loại kiểu**:

```java
@Target(ElementType.TYPE)
@interface Component {}

@Component
class OrderController {}
```

`TYPE_USE` mô tả **vị trí sử dụng một kiểu**:

```java
@Target(ElementType.TYPE_USE)
@interface NonBlankText {}

List<@NonBlankText String> names;
```

`@NonBlankText` **không tự thực hiện** kiểm tra giá trị `String` có trống hay không. Nó chỉ cung cấp metadata cho static analyzer hoặc một chương trình thực thi có chủ đích diễn giải nó.

## 6. `@Retention`: metadata tồn tại đến giai đoạn nào?

`@Retention` chọn một trong ba chính sách của `RetentionPolicy`:

| Chính sách | Trong source | Trong file `.class` | Đọc qua core reflection lúc chạy |
| --- | --- | --- | --- |
| `SOURCE` | Có | Không được giữ | Không |
| `CLASS` | Có | Có theo quy tắc class-file | Không |
| `RUNTIME` | Có | Có theo quy tắc class-file | **Có** |

Ví dụ:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeMarker {}
```

Với annotation để **runtime reflection** đọc, cần khai báo `RUNTIME`. Nếu không khai báo `@Retention`, chính sách mặc định là **`CLASS`**, không phải `RUNTIME`.

Điều đó giải thích lỗi rất phổ biến:

```java
@interface MyTag {} // Mặc định retention CLASS

@MyTag
class TaggedClass {}

System.out.println(
        TaggedClass.class.isAnnotationPresent(MyTag.class));
// false
```

Kết quả `false` không nói rằng annotation chưa từng xuất hiện trong source; nó cho biết metadata đó **không có sẵn để tra cứu qua reflection lúc chạy**.

**Ghi chú kỹ thuật:** Chính sách `RUNTIME` không phải bảo đảm mọi annotation trên mọi vị trí cú pháp đều đọc được thông qua cùng một API. Ví dụ, annotation trên khai báo biến cục bộ hoặc tham số lambda không có hợp đồng được lưu vào class file giống khai báo method/field theo JLS. Cần chọn đúng nguồn metadata và API cho **vị trí** được annotate.

## 7. Các meta-annotations hữu ích khác

Meta-annotation là annotation được gắn lên **khai báo một annotation interface** để mô tả chính annotation đó.

### 7.1. `@Documented`

`@Documented` đề nghị công cụ tạo tài liệu, đặc biệt là Javadoc, đưa annotation vào tài liệu của phần tử được annotate. Nó không làm annotation được thực thi hoặc cưỡng chế quy tắc nghiệp vụ.

```java
import java.lang.annotation.Documented;

@Documented
@interface PublicContract {
    String value();
}
```

### 7.2. `@Inherited`

`@Inherited` cho phép **annotation trên khai báo class** được tìm thấy khi tra trên subclass trong một số phương thức reflection, nếu subclass không khai báo giá trị riêng. Nó **không** tự lan annotation từ interface sang implementing class và không làm annotation trên method được tự động kế thừa khi override.

Chi tiết và ví dụ ở mục 11.

### 7.3. `@Repeatable`

`@Repeatable` cho phép gắn nhiều annotation cùng một loại ở một vị trí, bằng cách định nghĩa **container annotation**. Khi đọc qua reflection, ưu tiên phương thức `getAnnotationsByType(...)` hoặc `getDeclaredAnnotationsByType(...)` để có đủ các phần tử. Ví dụ ở mục 10.

## 8. Đọc annotation qua reflection: `AnnotatedElement`

`java.lang.reflect.AnnotatedElement` là giao diện chung cho nhiều đối tượng reflection, gồm `Class`, `Method`, `Field`, `Constructor`, `Parameter` và `RecordComponent`.

Những method quan trọng:

| API | Cách hiểu |
| --- | --- |
| `getAnnotation(A.class)` | Lấy một annotation kiểu `A` nếu **present**; nếu không có, trả `null` |
| `isAnnotationPresent(A.class)` | Kiểm tra xem annotation kiểu `A` có **present** hay không |
| `getDeclaredAnnotation(A.class)` | Chỉ lấy annotation **được khai báo trực tiếp** trên phần tử |
| `getAnnotations()` | Trả tất cả annotations **present** theo hợp đồng reflection |
| `getDeclaredAnnotations()` | Trả các annotations được khai báo trực tiếp |
| `getAnnotationsByType(A.class)` | Lấy các annotation kiểu `A`, hỗ trợ **repeatable container** và kế thừa có điều kiện |
| `getDeclaredAnnotationsByType(A.class)` | Lấy các annotation kiểu `A` trực tiếp hoặc qua container trên chính phần tử đó; **không** tìm ở superclass |

Các từ **directly present**, **indirectly present**, **present** và **associated** có định nghĩa kỹ thuật riêng trong `AnnotatedElement`. Đặc biệt, một annotation repeatable có thể nằm trong **container** thay vì xuất hiện trực tiếp; vì thế `getAnnotation(...)` không phải lời giải tổng quát cho mọi repeatable annotation.

### 8.1. Ví dụ đọc metadata của method

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface ApiAction {
    String value();
    int rank() default 1;
}

class Service {
    @ApiAction(value = "approve", rank = 5)
    public void approve() {}
}

Method method = Service.class.getDeclaredMethod("approve");
ApiAction action = method.getDeclaredAnnotation(ApiAction.class);

if (action != null) {
    System.out.println(action.value()); // approve
    System.out.println(action.rank());  // 5
}
```

Đây là một **đoạn minh họa**: các câu lệnh bắt đầu từ `Method method = ...` cần nằm trong method có xử lý hoặc khai báo `NoSuchMethodException`. Ở mục 16 có chương trình `Demo.java` độc lập, có thể chạy trực tiếp.

`getDeclaredMethod("approve")` tìm method **khai báo ngay trong `Service`** với tên và danh sách tham số phù hợp. Nếu method bị overload, cần truyền thêm các kiểu tham số, ví dụ `getDeclaredMethod("submit", String.class, int.class)`.

### 8.2. `getMethod` khác `getDeclaredMethod`

- `getMethod(...)` tìm **public method** tương ứng, bao gồm những public methods được kế thừa theo quy tắc Java reflection.
- `getDeclaredMethod(...)` tìm method **khai báo tại class đang xét**, bất kể access modifier, nhưng không tìm method được kế thừa.
- `getMethods()` và `getDeclaredMethods()` trả arrays, **không hứa một thứ tự cố định**. Khi in báo cáo hoặc sinh metadata cần deterministic output, hãy sắp xếp theo tiêu chí của ứng dụng.

**Quan trọng:** Tìm được `Method` và đọc annotation **không đồng nghĩa** đã có quyền gọi method đó, nhất là private member trong ứng dụng dùng Java Platform Module System (JPMS).

## 9. Element mặc định và kiểm tra khai báo metadata

Một annotation element có thể có default value:

```java
@interface ExportSettings {
    String format() default "json";
    int version() default 1;
}

@ExportSettings
class DefaultExport {}
```

Khi đọc annotation instance:

```java
ExportSettings settings =
        DefaultExport.class.getAnnotation(ExportSettings.class);
```

Nếu `@Retention(RUNTIME)` **không** được khai báo trên `ExportSettings`, `settings` là `null` tại runtime. Với mục tiêu đọc reflection, cần định nghĩa lại annotation như sau:

```java
@java.lang.annotation.Retention(
        java.lang.annotation.RetentionPolicy.RUNTIME)
@interface ExportSettings {
    String format() default "json";
    int version() default 1;
}
```

Hai khai báo `ExportSettings` phía trên là **hai phiên bản để so sánh**, không đặt cả hai trong cùng chương trình. Khi dùng phiên bản `RUNTIME`, các lời gọi `settings.format()` và `settings.version()` trả `"json"` và `1`.

### 9.1. Đọc default value ngay trên annotation interface

`Method.getDefaultValue()` trả default value của **annotation element declaration**, hoặc `null` nếu element không có default.

```java
import java.lang.reflect.Method;

Method formatElement =
        ExportSettings.class.getDeclaredMethod("format");
Method versionElement =
        ExportSettings.class.getDeclaredMethod("version");

System.out.println(formatElement.getDefaultValue());  // json
System.out.println(versionElement.getDefaultValue()); // 1
```

Phần khai báo default là **một phần của hợp đồng annotation interface**. Thay giá trị default trong bản phát hành sau có thể thay đổi cách đọc metadata của những nơi đã dùng annotation mà không truyền element đó. Cần quản lý thay đổi tương thích khi công bố annotation như một API.

### 9.2. Không chủ quan khi đọc metadata từ thư viện khác phiên bản

Nếu annotation interface thay đổi nhưng bytecode nơi sử dụng chưa được biên dịch lại, có thể phát sinh các lỗi liên quan đến metadata không đầy đủ hoặc kiểu element không phù hợp, ví dụ `IncompleteAnnotationException` khi truy cập một element mới bắt buộc nhưng thiếu trong dữ liệu cũ.

Với thư viện dùng chung, cân nhắc cung cấp default hợp lý cho element mới và có kiểm thử tương thích đa phiên bản. Không dùng default bừa bãi để che thiếu metadata thật sự bắt buộc.

## 10. Repeatable annotations: khai báo và đọc nhiều giá trị

Một method/class đôi khi cần nhiều metadata cùng loại. Ví dụ, một API có thể mang nhiều nhãn phân loại.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}

@Label("api")
@Label("internal")
class InvoiceHandler {}
```

Trong ví dụ:

- `@Repeatable(Labels.class)` chỉ định `Labels` làm **container annotation**.
- Container bắt buộc có element `value()` trả kiểu `Label[]`.
- Retention và target của container phải thỏa các ràng buộc tương thích với annotation lặp; ở đây cả hai đều là `RUNTIME` và `TYPE`.
- Java có thể biểu diễn hai `@Label` thành metadata container trong class file.

Đọc đúng:

```java
Label[] labels =
        InvoiceHandler.class.getAnnotationsByType(Label.class);

for (Label label : labels) {
    System.out.println(label.value());
}
// api
// internal
```

Không nên giả định `getAnnotation(Label.class)` luôn trả annotation đầu tiên khi khai báo lặp nhiều lần. Nó có thể trả `null` nếu chỉ có container `Labels` được trực tiếp lưu trong metadata. `getAnnotationsByType` được thiết kế để **mở container** và trả về các giá trị lặp.

### 10.1. `getDeclaredAnnotationsByType` khác `getAnnotationsByType`

`getDeclaredAnnotationsByType(Label.class)` chỉ kiểm tra metadata trên **phần tử hiện tại**, vẫn hỗ trợ mở container. `getAnnotationsByType(Label.class)` còn có quy tắc hỗ trợ kế thừa trên class nếu annotation type có `@Inherited` và không có annotation liên quan được khai báo trực tiếp.

Với mục tiêu đọc metadata **không cho phép kế thừa**, hãy ưu tiên biến thể `Declared...` để tránh vô tình lấy cấu hình từ superclass.

## 11. `@Inherited`: kế thừa annotation ở mức class

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Environment {
    String value();
}

@Environment("production")
class BaseService {}

class ReportService extends BaseService {}
```

Nếu đọc reflection:

```java
Environment inherited =
        ReportService.class.getAnnotation(Environment.class);
Environment declared =
        ReportService.class.getDeclaredAnnotation(Environment.class);

System.out.println(inherited.value()); // production
System.out.println(declared);          // null
```

`ReportService` không khai báo `@Environment` trực tiếp, nhưng `getAnnotation` thấy giá trị từ superclass bởi `@Inherited`.

**Các giới hạn bắt buộc nhớ:**

1. `@Inherited` tác động đến việc tra cứu annotation trên **khai báo class**, không làm annotation “được copy vào source” của subclass.
2. Annotation trên **interface** không tự được kế thừa sang implementing class nhờ `@Inherited`.
3. Annotation trên **method** không tự được kế thừa sang overriding method qua `@Inherited`.
4. `getDeclaredAnnotation` và `getDeclaredAnnotationsByType` không đi tìm metadata trong superclass.
5. Nếu subclass tự khai báo annotation tương ứng, các quy tắc tra cứu có thể ưu tiên metadata tại subclass.

Một framework muốn tự kế thừa metadata method hoặc interface có thể xây dựng thuật toán tra cứu riêng, nhưng đó là **quy tắc framework**, không phải hành vi mặc định của `@Inherited` trong Java reflection.

## 12. Annotation trên record components

Java 27 hỗ trợ `ElementType.RECORD_COMPONENT` và API `Class.getRecordComponents()`. Đây là nơi đọc metadata đúng nghĩa gắn trực tiếp lên component của một record.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ColumnName {
    String value();
}

record Customer(
        @ColumnName("customer_id") String id,
        @ColumnName("full_name") String name) {}
```

Đọc metadata:

```java
import java.lang.reflect.RecordComponent;

for (RecordComponent component :
        Customer.class.getRecordComponents()) {
    ColumnName column = component.getAnnotation(ColumnName.class);
    System.out.println(component.getName() + " -> " + column.value());
}
// id -> customer_id
// name -> full_name
```

`RecordComponent` là một `AnnotatedElement`, vì vậy có các API đọc annotation tương tự như `Method`/`Field`.

Không nên mặc định rằng annotation gắn trên record component sẽ xuất hiện ở mọi nơi khác, như field, accessor và constructor parameter. Sự lan truyền annotation tới các thành phần được sinh phụ thuộc **target applicability** và quy tắc của record. Với mục tiêu đọc metadata record component, hãy truy vấn **chính `RecordComponent`** thay vì suy đoán từ các thành phần được sinh.

## 13. TYPE_USE annotations: metadata trên chính vị trí sử dụng kiểu

Annotation trên **declaration** khác với annotation trên **type use**. Java cho phép gắn annotation vào generic type argument và những vị trí dùng kiểu khác khi `@Target(TYPE_USE)` cho phép.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ReviewedText {}

class MessageBatch {
    List<@ReviewedText String> messages;
}
```

`@ReviewedText` trong ví dụ gắn lên **kiểu phần tử `String`**, không phải annotation declaration thông thường của field `messages`. Vì thế, chỉ gọi `Field.getAnnotation(ReviewedText.class)` là **không đúng vị trí metadata cần đọc**.

Có thể đi qua `AnnotatedType`:

```java
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;

Field field = MessageBatch.class.getDeclaredField("messages");
AnnotatedParameterizedType parameterized =
        (AnnotatedParameterizedType) field.getAnnotatedType();

AnnotatedType elementType =
        parameterized.getAnnotatedActualTypeArguments()[0];

System.out.println(
        elementType.isAnnotationPresent(ReviewedText.class));
// true
```

Đoạn đọc reflection cần được đặt trong method khai báo/xử lý `NoSuchFieldException`. Với generic type phức tạp, hãy kiểm tra loại `AnnotatedType` trước khi ép về `AnnotatedParameterizedType`.

**Cần phân biệt:** Dù có `@Target(TYPE_USE)` và `@Retention(RUNTIME)`, annotation tùy chỉnh này **không tự khiến Java compiler kiểm tra** nội dung chuỗi. Chỉ static analyzer, type checker hoặc logic runtime được thiết kế riêng mới có thể thực thi quy tắc cụ thể.

## 14. Compile-time annotation processing khác runtime reflection

Có hai con đường xử lý metadata khác nhau trong hệ sinh thái Java:

| Khía cạnh | Annotation processing khi biên dịch | Reflection khi chạy |
| --- | --- | --- |
| Thời điểm | Compiler/build | JVM đang chạy |
| API tiêu biểu | `javax.annotation.processing`, `javax.lang.model` | `java.lang.reflect` |
| Đầu vào | Source/element model của quá trình biên dịch | Class và metadata có sẵn lúc chạy |
| Chính sách retention | Không bắt buộc `RUNTIME` | Cần `RUNTIME` để đọc annotation hiện diện qua reflection |
| Ứng dụng | Kiểm tra hợp đồng, báo lỗi build, sinh source/resource | Đăng ký handler, đọc cấu hình, dựng schema, xử lý metadata |
| Giới hạn | Không tự thực thi nghiệp vụ khi chương trình chạy | Không tự thay đổi bytecode hoặc bỏ qua access control |

### 14.1. Annotation processor

Annotation processor triển khai API của module `java.compiler`, thường dựa trên `AbstractProcessor` và làm việc với `RoundEnvironment`, `Element`, `TypeElement`, `Messager` và `Filer`. Nó có thể phát hiện annotation, kiểm tra khai báo và sinh source/resource hợp lệ trong quá trình compile.

Ý tưởng kiểm tra:

```java
// Trong một processor phù hợp:
for (Element element :
        roundEnv.getElementsAnnotatedWith(Operation.class)) {
    // Kiểm tra các giá trị/kiểu hoặc phát thông báo lỗi bằng Messager.
}
```

Đây là **mảnh minh họa**, không phải processor hoàn chỉnh. Trong dự án thực tế cần cài đặt đúng `Processor`, khai báo các annotation được hỗ trợ, phiên bản nguồn, cách đăng ký processor với công cụ build, và chỉ sử dụng các API được cho phép trong các processing rounds.

### 14.2. Runtime reflection

Với `@Retention(RUNTIME)`, ứng dụng có thể tra metadata của class/method/field có sẵn và quyết định xử lý. Việc tra cứu **không** đồng nghĩa mọi khai báo đều được phép truy cập hoặc gọi động.

Không dùng reflection để thay thế mọi đường gọi tĩnh: nếu một API có thể dùng interface hoặc method reference với kiểu rõ ràng, cách đó thường dễ bảo trì hơn. Reflection hợp lý khi metadata thật sự quyết định lựa chọn hành vi trong framework, plugin registry, mapper hoặc hệ thống tương tự.

## 15. Reflection, quyền truy cập và Java Platform Module System

Metadata `@Retention(RUNTIME)` có thể hiện diện trong class file, nhưng **việc đọc metadata** và **quyền truy cập thành viên** là hai vấn đề khác nhau.

`Class.getDeclaredMethods()` có thể mô tả cả method private được khai báo, nhưng không có nghĩa có thể gọi method private đó từ mọi module. Java 27 duy trì strong encapsulation trong Java Platform Module System (JPMS).

Ví dụ về cấu hình module:

```java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.internal to com.example.framework;
}
```

- `exports` cung cấp quyền truy cập thông thường tới các public types của package được xuất, với điều kiện các quy tắc access khác cũng thỏa.
- `opens` cho phép **deep reflection** tới package được mở ở runtime; ở đây chỉ cho module `com.example.framework`.
- `getDeclaredMethod(...)` lấy mô tả method; `Method.invoke(...)` là hành động khác và vẫn chịu kiểm tra access.
- `trySetAccessible()` có thể không thành công; `setAccessible(true)` có thể ném `InaccessibleObjectException` khi bị chặn.

**Khuyến nghị Java 27:** thiết kế public API hoặc cấu hình `opens` có giới hạn cho framework đáng tin cậy nếu deep reflection thực sự cần. Không dùng các thủ thuật mở mọi package hay thay đổi khả năng truy cập vô điều kiện chỉ để tránh thiết kế interface/module rõ ràng.

Nếu ứng dụng chỉ cần đọc annotation trên public method đã được phép truy cập, thường không cần deep reflection. Với class hoặc method riêng tư nằm trong package không mở, phải tôn trọng ranh giới truy cập đó thay vì coi annotation là “vé vượt quyền”.

## 16. Ví dụ độc lập: khai báo annotation và quét metadata method

Đặt toàn bộ mã sau vào file `Demo.java`. Chương trình khai báo annotation có metadata bắt buộc và tùy chọn, gắn nó lên hai public methods, rồi dùng reflection để quét kết quả. Việc sắp xếp methods làm đầu ra ổn định, không phụ thuộc thứ tự `getDeclaredMethods()`.

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

public class Demo {
    enum Verb {
        READ, WRITE
    }

    @Documented
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Command {
        String value();
        Verb verb() default Verb.READ;
        String[] tags() default {};
    }

    static final class OrderService {
        @Command(
                value = "/orders",
                verb = Verb.WRITE,
                tags = {"sales", "create"})
        public void create() {
        }

        @Command("/orders")
        public void list() {
        }

        public void health() {
            // Không có annotation Command.
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Method[] methods = OrderService.class.getDeclaredMethods();
        Arrays.sort(methods, Comparator.comparing(Method::getName));

        for (Method method : methods) {
            Command info = method.getDeclaredAnnotation(Command.class);
            if (info == null) {
                continue;
            }

            System.out.println(
                    method.getName()
                    + ": " + info.verb()
                    + " " + info.value()
                    + " tags=" + Arrays.toString(info.tags()));
        }

        Method verbElement = Command.class.getDeclaredMethod("verb");
        System.out.println(
                "default verb: " + verbElement.getDefaultValue());
    }
}
```

Biên dịch và chạy:

```shell
javac Demo.java
java Demo
```

Kết quả:

```text
create: WRITE /orders tags=[sales, create]
list: READ /orders tags=[]
default verb: READ
```

Điểm cần quan sát:

1. `@Command` có `RUNTIME` retention nên reflection đọc được.
2. `@Target(METHOD)` giới hạn annotation chỉ đặt ở method declarations.
3. `Command.value()` là element bắt buộc, nhưng có cú pháp rút gọn `@Command("/orders")` khi chỉ truyền `value`.
4. `verb()` và `tags()` có default values; không khai báo trong `list()` thì reflection trả về các giá trị mặc định.
5. `health()` bị bỏ qua vì không có `@Command`.
6. `Method.getDefaultValue()` đọc default khai báo tại annotation interface, không cần có một method được gắn annotation.
7. Ví dụ chỉ **đọc và in metadata**; nó không gọi `OrderService.create()` hoặc thực thi quyền nào chỉ vì có `@Command`.

Toàn bộ cú pháp trên thuộc Java SE 27 ổn định, không cần `--enable-preview` hay thư viện bên ngoài.

## 17. Những sai lầm phổ biến

| Tình huống | Vì sao sai hoặc rủi ro | Hướng xử lý |
| --- | --- | --- |
| Khai báo `@interface Tag` mà quên `@Retention(RUNTIME)`, sau đó dùng reflection | Mặc định retention là `CLASS` | Thêm `@Retention(RUNTIME)` khi API cần runtime metadata |
| Tin rằng gắn custom annotation tự gọi logic | Metadata không phải lệnh thực thi | Viết rõ processor/framework/consumer |
| Khai báo `List<String> values();` trong annotation | Annotation element không nhận object generic tùy ý | Dùng element type hợp lệ như `String[]` |
| Truyền `null` cho element | `null` không phải annotation value hợp lệ | Thiết kế default hoặc sentinel có ngữ nghĩa rõ |
| Dùng giá trị trả về từ `System.getenv()` ngay trong annotation | Không phải giá trị annotation hợp lệ khi compile | Đưa cấu hình runtime vào ứng dụng thay vì metadata tĩnh |
| Khai báo `@Target(METHOD)` rồi gắn lên field | Sai vị trí cú pháp | Chọn `ElementType` đúng |
| Dùng `Field.getAnnotation` để đọc annotation trên generic type argument | Declaration metadata khác type-use metadata | Dùng `getAnnotatedType()` và API `AnnotatedType` phù hợp |
| Dùng `getAnnotation(A.class)` để đọc nhiều `@A` repeatable | Có thể chỉ thấy container, không thấy từng annotation | Dùng `getAnnotationsByType(A.class)` |
| Dùng `@Inherited` và mong method override kế thừa annotation | `@Inherited` chỉ áp dụng class lookup | Định nghĩa rõ chiến lược kế thừa method của framework |
| Dùng `@Inherited` để lấy annotation từ interface | Không tự kế thừa qua interface | Duyệt interface/supertype có chủ đích khi cần |
| Quên phân biệt `getAnnotation` và `getDeclaredAnnotation` | Có thể vô tình dùng metadata từ superclass | Chọn đúng inherited/declared semantics |
| Giả định `getDeclaredMethods()` có thứ tự ổn định | API không bảo đảm | Sắp xếp nếu kết quả cần deterministic |
| Tìm thấy method bằng reflection rồi mặc định gọi được private method | JPMS/access checks vẫn áp dụng | Dùng public API hoặc mở package có kiểm soát |
| Dùng annotation làm bằng chứng phân quyền | Annotation không tự thực thi authorization | Kiểm tra quyền thật tại điểm thực thi |
| Thêm annotation element mới không default vào thư viện đang có bytecode cũ | Có thể gây lỗi đọc metadata ở runtime | Đánh giá tương thích và cung cấp default nếu phù hợp |
| Dùng reflection mọi nơi thay vì interface/kiểu tĩnh | Coupling động, khó phát hiện lỗi và bảo trì | Dùng reflection ở ranh giới thực sự cần metadata |

## 18. Checklist thiết kế và kiểm thử

1. **Annotation mô tả điều gì?** Metadata có ý nghĩa nghiệp vụ/kiến trúc rõ ràng hay chỉ là nhãn trang trí?
2. **Ai tiêu thụ annotation?** Compiler, annotation processor, framework hay mã reflection tự viết?
3. **Đã chọn `@Retention` đúng chưa?** `RUNTIME` chỉ khi thực sự cần kiểm tra runtime; `SOURCE` hoặc `CLASS` phù hợp với những nhu cầu khác.
4. **`@Target` có giới hạn đúng chỗ cần dùng không?** Xét riêng method, field, type, record component, parameter và type use.
5. **Các annotation elements có kiểu hợp lệ không?** Tránh arbitrary object, generic collection và multidimensional array.
6. **Element nào thực sự bắt buộc?** Cân nhắc default rõ nghĩa cho các tùy chọn.
7. **Nếu metadata có thể lặp, đã khai báo container và `@Repeatable` đúng chưa?** Đọc bằng `getAnnotationsByType`.
8. **Có kỳ vọng kế thừa không?** Hiểu rõ giới hạn `@Inherited` trên class và sự khác nhau giữa declared/present.
9. **Với record component và TYPE_USE, có đọc đúng đối tượng phản chiếu không?** Đừng nhầm annotation declaration với type-use metadata.
10. **Các element mặc định được thay đổi qua phiên bản ra sao?** Kiểm tra tương thích với bytecode cũ.
11. **Có phụ thuộc thứ tự của reflection arrays không?** Sắp xếp để bảo đảm output ổn định khi cần.
12. **Có cần truy cập private member qua module khác không?** Thiết kế `exports`/`opens` rõ, không lạm dụng `setAccessible`.
13. **Annotation có bị nhầm với thực thi quy tắc bảo mật/validation không?** Tách metadata khỏi code enforcement.
14. **Đã kiểm thử trường hợp không có annotation chưa?** `getAnnotation` có thể trả `null`; `getAnnotationsByType` có thể trả mảng rỗng.
15. **Có kiểm thử runtime với class file/phiên bản dependency thực tế không?** Đặc biệt khi metadata là public contract giữa các module.

## 19. Tổng kết

Để khai báo annotation tùy chỉnh trong Java 27, dùng `@interface` với các **annotation elements** có kiểu được JLS cho phép. `@Target` quyết định nơi annotation được viết; `@Retention` quyết định metadata tồn tại tới giai đoạn nào. Nếu cần đọc bằng runtime reflection, phải có `RetentionPolicy.RUNTIME` và dùng đúng API của `AnnotatedElement`, `Method`, `Field`, `Class`, `RecordComponent` hoặc `AnnotatedType` theo vị trí annotation.

`getAnnotation(...)` phù hợp với metadata không lặp; `getAnnotationsByType(...)` phù hợp khi annotation `@Repeatable`. Phân biệt `getDeclared...` và `get...` để tránh hiểu sai kế thừa; `@Inherited` chỉ có ảnh hưởng phù hợp trên **class annotations**, không tự lan truyền tới interface hay overriding methods.

Cuối cùng, annotation chỉ là **mô tả**, không phải cơ chế tự chạy logic, tự xác thực dữ liệu hoặc tự mở quyền truy cập. Annotation processors có thể kiểm tra/generate khi biên dịch; reflection có thể đọc metadata lúc chạy; cả hai đều phải tuân thủ hợp đồng API và ranh giới bảo mật của Java 27.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — JLS 9.6 Annotation Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.6) — khai báo annotation interface và đặc điểm cấu trúc.
- [Java Language Specification, Java SE 27 — JLS 9.6.1 Annotation Interface Elements](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.6.1) — kiểu element hợp lệ và ràng buộc khai báo.
- [Java Language Specification, Java SE 27 — JLS 9.6.2 Defaults for Annotation Interface Elements](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.6.2) — default values.
- [Java Language Specification, Java SE 27 — JLS 9.6.3 Repeatable Annotation Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.6.3) — điều kiện container và repeatable.
- [Java Language Specification, Java SE 27 — JLS 9.6.4 Predefined Annotation Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.6.4) — `@Target`, `@Retention`, `@Inherited`, `@Repeatable`.
- [Java Language Specification, Java SE 27 — JLS 9.7 Annotations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.7) — marker, single-element, normal annotations và nơi được sử dụng.
- [AnnotatedElement (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AnnotatedElement.html) — get/declared/getByType và semantics kế thừa, repeatable.
- [ElementType (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/annotation/ElementType.html) — danh sách declaration/type-use contexts và `RECORD_COMPONENT`.
- [RetentionPolicy (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/annotation/RetentionPolicy.html) — `SOURCE`, `CLASS`, `RUNTIME`.
- [Repeatable (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/annotation/Repeatable.html) — container annotation.
- [RecordComponent (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/RecordComponent.html) — truy vấn component metadata của record.
- [Method (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html) — `getDefaultValue` và metadata method.
- [Annotation Processing (Java SE 27 API)](https://docs.oracle.com/en/java/javase/27/docs/api/java.compiler/javax/annotation/processing/package-summary.html) — API annotation processing tại compile time.
