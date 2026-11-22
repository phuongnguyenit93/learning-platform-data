# Annotation trên record, thành phần và kiểu thành phần

## 1. Ba vị trí dễ nhầm khi dùng annotation với record

Một record (lớp bản ghi) mô tả dữ liệu bằng **các thành phần** khai báo trong phần tiêu đề. Ví dụ:

```java
record Customer(String id, String name) {}
```

Record có thể mang annotation ở các vị trí mang ý nghĩa khác nhau:

1. **Trên chính lớp record**: annotation mô tả kiểu `Customer`, tương tự annotation trên một lớp thông thường.
2. **Trên khai báo thành phần** (record component): annotation gắn với thành phần `id` hoặc `name` trong tiêu đề record; có thể được giữ trên thành phần và/hoặc chuyển tới trường, accessor, tham số constructor tùy `@Target`.
3. **Trên kiểu dữ liệu của thành phần** (type use): annotation mô tả việc sử dụng kiểu `String`, `List<...>`, kiểu phần tử trong generic hoặc kiểu mảng. Đây là nơi dùng `ElementType.TYPE_USE`.

Điều cần nắm là: **một annotation đặt trước kiểu trong tiêu đề record có thể phục vụ nhiều ngữ cảnh**, nhưng không phải annotation nào cũng tự xuất hiện ở tất cả những nơi liên quan. Khả năng áp dụng được quyết định bởi `@Target`; việc còn đọc được bằng reflection hay không được quyết định bởi `@Retention` và đúng API reflection được gọi.

**Phạm vi phiên bản:** Record từng là tính năng thử nghiệm của Java 14 nhưng đã được chuẩn hóa từ Java 16. Bài này dùng **cú pháp record ổn định và API Java 17+**, tập trung vào quy tắc annotation vẫn áp dụng ở Java hiện đại; không yêu cầu bật preview hay hướng dẫn cú pháp thử nghiệm cũ.

## 2. `@Target` quyết định nơi áp dụng

`@Target` là annotation dùng để khai báo những vị trí mà một loại annotation được phép xuất hiện. Các giá trị liên quan trực tiếp tới record:

| `ElementType` | Nơi áp dụng | Ý nghĩa với record |
| --- | --- | --- |
| `TYPE` | Khai báo lớp, giao diện và các loại kiểu phù hợp | Annotate **lớp record**, ví dụ `@DomainModel record Order(...) {}` |
| `RECORD_COMPONENT` | Thành phần trong tiêu đề record | Đọc trực tiếp từ `RecordComponent` qua reflection, nếu được lưu ở runtime |
| `FIELD` | Trường dữ liệu | Annotation trên thành phần có thể truyền sang **trường `private final` sinh ngầm** |
| `METHOD` | Khai báo phương thức | Annotation trên thành phần có thể truyền sang **accessor sinh ngầm**, ví dụ `code()` |
| `PARAMETER` | Tham số phương thức/constructor | Annotation trên thành phần có thể truyền sang **tham số constructor chính được suy ra** |
| `TYPE_USE` | Một vị trí sử dụng kiểu | Annotation gắn với **kiểu thành phần**, kiểu tham số, kiểu trả về, đối số generic... |
| `TYPE_PARAMETER` | Khai báo tham số kiểu generic | Dùng khi annotate tham số kiểu, chẳng hạn `<@Tag T>`; khác với `TYPE_USE` trên kiểu của một thành phần |

Hai mục quan trọng nhất của bài là **`RECORD_COMPONENT` và `TYPE_USE`**:

- `RECORD_COMPONENT` đánh dấu **thành phần được khai báo**, chẳng hạn thành phần có tên `id`. Nó không đồng nghĩa với FIELD, METHOD hoặc PARAMETER.
- `TYPE_USE` đánh dấu **kiểu được sử dụng**. Ví dụ trong `record Box(List<@TypeMark String> names) {}`, `@TypeMark` gắn với kiểu `String` bên trong đối số generic; đó không phải annotation trên chính khai báo thành phần `names`.

Với annotation đặt trước `String`, ví dụ `@A String name`, `@Target` quyết định annotation đó có thể là annotation khai báo thành phần, annotation của kiểu sử dụng, hay có thể được chuyển tới thành viên liên quan. Một loại annotation cũng có thể công bố **nhiều mục tiêu** trong `@Target({ ... })`.

### Ví dụ khai báo các loại annotation

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface DomainModel {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMark {}

@DomainModel
record Customer(
    @ComponentMark @TypeMark String id,
    String name
) {}
```

Đoạn này minh họa khai báo annotation với mục tiêu rõ ràng. `@DomainModel` gắn với **lớp `Customer`**; `@ComponentMark` gắn với thành phần `id`; `@TypeMark` gắn với **kiểu `String` của `id`**. Các annotation chỉ tạo **siêu dữ liệu**; một mình chúng chưa kiểm tra dữ liệu, chưa cấm `null` và chưa chạy logic nghiệp vụ.

## 3. Annotation từ thành phần được truyền sang những nơi nào?

Mỗi thành phần record tương ứng với những cấu trúc Java khác:

- Một **trường `private final`** được sinh ngầm để lưu giá trị.
- Một **accessor** có cùng tên thành phần, ví dụ `id()`, được sinh ngầm nếu không khai báo tường minh.
- Một **tham số của constructor chính** (canonical constructor), được suy ra từ tiêu đề record nếu dùng constructor chính ngầm định hoặc compact constructor.

JLS quy định việc truyền annotation từ tiêu đề record theo **ngữ cảnh mà loại annotation được phép áp dụng**:

| Annotation đặt trên thành phần có `@Target` | Có thể xuất hiện ở đâu? | Cách quan sát phù hợp |
| --- | --- | --- |
| Chỉ `RECORD_COMPONENT` | Trên chính record component | `RecordComponent.getAnnotation(...)` |
| Chỉ `FIELD` | Trên trường thành phần sinh ngầm | `Class.getDeclaredField(...).getAnnotation(...)` |
| Chỉ `METHOD` | Trên **accessor sinh ngầm** | `Method.getAnnotation(...)` |
| Chỉ `PARAMETER` | Trên **tham số được suy ra** của canonical constructor | `Parameter.getAnnotation(...)` |
| Chỉ `TYPE_USE` | Trên các vị trí sử dụng kiểu liên quan | `getAnnotatedType()`, `getAnnotatedReturnType()`, `Parameter.getAnnotatedType()` |
| Nhiều mục tiêu, chẳng hạn `{RECORD_COMPONENT, FIELD, METHOD, PARAMETER}` | Có thể hiện diện tại nhiều nơi tương ứng | Phải kiểm tra đúng từng đối tượng reflection |

**Không phải “chuyển” nghĩa là xóa annotation tại nơi gốc.** Với `@Target({RECORD_COMPONENT, FIELD})`, annotation có thể tồn tại trên thành phần record và cũng được truyền sang trường. Nếu loại annotation chỉ cho phép FIELD, đừng mong `RecordComponent.getAnnotation(...)` trả annotation đó.

Việc truyền tự động cũng **không luôn xảy ra với những phần do lập trình viên tự khai báo**: accessor khai báo tường minh và tham số constructor chính khai báo tường minh có quy tắc riêng, được làm rõ ở phần 6.

### Minh họa nhanh: một annotation đa mục tiêu

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.RECORD_COMPONENT,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface AuditMark {}

record Account(@AuditMark String code) {}
```

Trong ví dụ này, `@AuditMark` được đặt một lần tại khai báo thành phần `code`. Với **accessor và canonical constructor ngầm định**, annotation phù hợp sẽ có mặt trên record component, trường, accessor và tham số constructor. Việc truyền này nhằm hỗ trợ các công cụ đọc metadata ở những vị trí khác nhau, nhưng bản thân `@AuditMark` vẫn không tự tạo kiểm tra hoặc ghi log.

## 4. `TYPE_USE`: annotation của kiểu thành phần và kiểu lồng nhau

Một annotation có `@Target(TYPE_USE)` mô tả **vị trí dùng kiểu**, không trực tiếp là một annotation khai báo record component. Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface CheckedType {}

record Batch(
    @CheckedType String label,
    List<@CheckedType String> names
) {}
```

- `@CheckedType String label`: annotate kiểu `String` dùng để khai báo thành phần `label`.
- `List<@CheckedType String> names`: annotate **kiểu đối số `String` nằm trong `List`**, không phải toàn bộ kiểu `List` và cũng không phải annotation khai báo `names`.
- Có thể dùng cả `@CheckedType List<...>` nếu thực sự muốn annotate **kiểu `List`**; đó là một vị trí khác.

Khi đọc metadata kiểu có annotation:

- `RecordComponent.getAnnotatedType()` trả một `AnnotatedType` mô tả kiểu đã khai báo của thành phần.
- Với kiểu generic, có thể kiểm tra các đối số bằng `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`.
- Với trường: `Field.getAnnotatedType()`.
- Với accessor: `Method.getAnnotatedReturnType()`.
- Với tham số constructor: `Parameter.getAnnotatedType()`.

**Khác biệt quan trọng:** `component.getAnnotation(CheckedType.class)` dùng để tìm annotation **trên khai báo thành phần**, còn `component.getAnnotatedType().getAnnotation(CheckedType.class)` dùng để tìm annotation **trên kiểu thành phần**. Nếu `CheckedType` chỉ có mục tiêu `TYPE_USE`, lệnh thứ nhất không phải cách đọc đúng. Reflection nhìn thấy annotation khi `@Retention(RUNTIME)` và các vị trí metadata thực sự có annotation.

## 5. Ví dụ Java 17+ hoàn chỉnh: quan sát từng vị trí bằng reflection

Lưu đoạn sau vào tệp **`RecordAnnotationsDemo.java`**. Mỗi annotation có một mục tiêu duy nhất để dễ phân biệt việc nó xuất hiện ở đâu.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;

public class RecordAnnotationsDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface OnRecord {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    @interface OnComponent {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.FIELD)
    @interface OnField {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface OnAccessor {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface OnParameter {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface OnTypeUse {}

    @OnRecord
    record Product(
        @OnComponent @OnField @OnAccessor
        @OnParameter @OnTypeUse String code,
        int quantity
    ) {}

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<Product> type = Product.class;
        RecordComponent component = type.getRecordComponents()[0];
        Field field = type.getDeclaredField("code");
        Method accessor = type.getDeclaredMethod("code");

        Constructor<Product> ctor = type.getDeclaredConstructor(
                String.class, int.class);
        Parameter parameter = ctor.getParameters()[0];

        System.out.println("record=" +
                type.isAnnotationPresent(OnRecord.class));
        System.out.println("component=" +
                component.isAnnotationPresent(OnComponent.class));
        System.out.println("field=" +
                field.isAnnotationPresent(OnField.class));
        System.out.println("accessor=" +
                accessor.isAnnotationPresent(OnAccessor.class));
        System.out.println("parameter=" +
                parameter.isAnnotationPresent(OnParameter.class));

        System.out.println("componentType=" +
                component.getAnnotatedType()
                        .isAnnotationPresent(OnTypeUse.class));
        System.out.println("fieldType=" +
                field.getAnnotatedType()
                        .isAnnotationPresent(OnTypeUse.class));
        System.out.println("accessorReturnType=" +
                accessor.getAnnotatedReturnType()
                        .isAnnotationPresent(OnTypeUse.class));
        System.out.println("parameterType=" +
                parameter.getAnnotatedType()
                        .isAnnotationPresent(OnTypeUse.class));

        System.out.println("typeUseAsComponentDeclaration=" +
                component.isAnnotationPresent(OnTypeUse.class));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 RecordAnnotationsDemo.java
java RecordAnnotationsDemo
```

Kết quả:

```text
record=true
component=true
field=true
accessor=true
parameter=true
componentType=true
fieldType=true
accessorReturnType=true
parameterType=true
typeUseAsComponentDeclaration=false
```

Giải thích theo kết quả:

1. `@OnRecord` có mục tiêu TYPE nên được tìm trên chính `Product.class`.
2. `@OnComponent` có mục tiêu RECORD_COMPONENT nên xuất hiện khi đọc `Product.class.getRecordComponents()[0]`.
3. `@OnField` có mục tiêu FIELD nên xuất hiện trên trường `code` do record tạo.
4. `@OnAccessor` có mục tiêu METHOD nên xuất hiện trên accessor `code()` **được tạo ngầm**.
5. `@OnParameter` có mục tiêu PARAMETER nên xuất hiện trên tham số `code` của constructor chính **được tạo ngầm**.
6. `@OnTypeUse` có mục tiêu TYPE_USE nên metadata của **kiểu `String`** có mặt qua `AnnotatedType` tại thành phần, trường, kiểu trả về accessor và kiểu tham số được suy ra.
7. Kết quả `typeUseAsComponentDeclaration=false` nhắc rằng một annotation chỉ có TYPE_USE **không phải** annotation khai báo thành phần RECORD_COMPONENT.

Ví dụ cố ý dùng `@Retention(RUNTIME)` để reflection đọc được. Nếu annotation có chính sách giữ lại khác, việc biên dịch và lưu trong bytecode hoặc khả năng kiểm tra tại runtime sẽ khác.

## 6. Hai ngoại lệ quan trọng khi tự viết accessor hoặc constructor

### 6.1. Accessor khai báo tường minh không tự nhận annotation từ thành phần

Với record đơn giản, Java tự tạo accessor và truyền những annotation có mục tiêu METHOD hoặc TYPE_USE phù hợp. Nhưng **khi bạn khai báo accessor thủ công**, annotation trên thành phần **không tự được sao chép sang khai báo phương thức tường minh**:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface ReadMark {}

record User(@ReadMark String name) {
    public String name() {
        return name;
    }
}
```

Đây là ví dụ Java hợp lệ; `@ReadMark` được ghi ở tiêu đề nhưng accessor `name()` do tác giả khai báo. Khi gọi `User.class.getDeclaredMethod("name").isAnnotationPresent(ReadMark.class)`, kết quả là **`false`**. Nếu một thư viện thực sự đọc annotation từ **accessor**, bạn cần khai báo annotation tại phương thức đó, ví dụ:

```java
record User(@ReadMark String name) {
    @ReadMark
    public String name() {
        return name;
    }
}
```

Hai ví dụ là **hai phiên bản thay thế của cùng record**, không đặt đồng thời trong một tệp. Chúng minh họa việc nên kiểm tra vị trí metadata mà framework đang đọc. Annotation `@ReadMark` trên record component vẫn nằm ở vị trí gốc trong mã nguồn; vì chỉ target METHOD nên không tự trở thành annotation RECORD_COMPONENT.

### 6.2. Tham số constructor chính khai báo tường minh

Với **constructor chính ngầm định** hoặc **compact constructor**, các tham số được suy ra từ tiêu đề record và nhận annotation phù hợp với PARAMETER/TYPE_USE. Ví dụ:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PARAMETER)
@interface InputMark {}

record Name(@InputMark String value) {
    Name {
        if (value == null) {
            throw new IllegalArgumentException("value is null");
        }
    }
}
```

Compact constructor `Name { ... }` không khai báo lại danh sách tham số, nên thông tin tham số được suy ra từ thành phần. Khi khai báo **normal canonical constructor** với danh sách tham số tường minh, các annotation của tham số đó phải được kiểm soát **ngay trên khai báo tham số tường minh**; Java không mặc nhiên sao chép toàn bộ annotation PARAMETER từ tiêu đề:

```java
record Name(@InputMark String value) {
    Name(String value) {
        this.value = value;
    }
}
```

Đây là phiên bản **thay thế** của `Name` ở đoạn trên. Nếu muốn `InputMark` xuất hiện trên tham số constructor này, viết `Name(@InputMark String value) { this.value = value; }`. Không giả định rằng annotation trên thành phần đồng nghĩa mọi constructor do tác giả tự viết đều nhận được nó.

**Lưu ý:** Nếu tự viết các accessor/constructor, vẫn phải tuân thủ quy tắc hợp lệ của record (chữ ký, mức truy cập, thứ tự/tham số của canonical constructor, khởi tạo trường...). Phần này chỉ phân tích ảnh hưởng **đến annotation**.

## 7. `@Retention` và việc truy vấn metadata

`@Target` nói annotation **được đặt ở đâu**, còn `@Retention` nói annotation được **giữ lại đến giai đoạn nào**:

| `RetentionPolicy` | Ý nghĩa | Reflection Java thông thường |
| --- | --- | --- |
| `SOURCE` | Chỉ tồn tại trong mã nguồn; công cụ xử lý mã có thể dùng lúc biên dịch | Không đọc được khi chương trình chạy |
| `CLASS` | Được lưu vào tệp `.class` nhưng không bắt buộc được JVM đưa ra qua reflection | Không dùng `getAnnotation` để trông đợi thấy nó lúc chạy |
| `RUNTIME` | Được lưu và cung cấp cho reflection khi hợp lệ ở vị trí tương ứng | Có thể đọc qua `Class`, `RecordComponent`, `Field`, `Method`, `Parameter`, `AnnotatedType` |

Nếu không khai báo `@Retention`, chính sách mặc định là `CLASS`, **không phải RUNTIME**. Vì vậy một annotation “đã viết trong mã nguồn” vẫn có thể không hiện ra khi gọi `getAnnotation` tại runtime. Một chương trình xử lý annotation lúc biên dịch có thể dùng SOURCE/CLASS theo thiết kế; không vì thế mà annotation sai.

Ví dụ:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface Label {
    String value();
}

record Person(@Label("Tên hiển thị") String name) {}
```

`Person.class.getRecordComponents()[0].getAnnotation(Label.class).value()` có thể trả `"Tên hiển thị"` vì annotation vừa được phép gắn với RECORD_COMPONENT, vừa được lưu ở RUNTIME. Annotation không làm `name` tự động đổi giá trị hoặc kiểm tra tính hợp lệ của tên.

## 8. Phân biệt reflection ở các lớp siêu dữ liệu

Khi đọc annotation của record, hãy xác định câu hỏi trước khi gọi API:

- **“Kiểu record có annotation gì?”** → `Product.class.getAnnotations()` hoặc `getAnnotation(...)`.
- **“Thành phần `code` có annotation khai báo gì?”** → `Product.class.getRecordComponents()`, lấy `RecordComponent` tương ứng rồi gọi `getAnnotation(...)`.
- **“Trường `code` có annotation gì?”** → `Product.class.getDeclaredField("code")`.
- **“Accessor `code()` có annotation gì?”** → `RecordComponent.getAccessor()` hoặc `Class.getDeclaredMethod("code")`.
- **“Tham số canonical constructor có annotation gì?”** → `getDeclaredConstructor(...)` rồi `getParameters()`.
- **“Kiểu của `code` được annotate thế nào?”** → `RecordComponent.getAnnotatedType()`; với generic, tiếp tục kiểm tra `AnnotatedParameterizedType` và các đối số.
- **“Kiểu trả về accessor/kiểu tham số constructor có TYPE_USE gì?”** → `Method.getAnnotatedReturnType()` hoặc `Parameter.getAnnotatedType()`.

Không nhầm `RecordComponent.getType()` (trả `Class<?>` của kiểu) với `getAnnotatedType()` (trả thông tin annotation trên vị trí sử dụng kiểu). Với generic, `getGenericType()` cung cấp thông tin kiểu tổng quát còn `getAnnotatedType()` giúp đi sâu vào các annotation kiểu. Và khi gọi `getRecordComponents()` trên **lớp không phải record**, giá trị trả về là `null`; hãy kiểm tra `Class.isRecord()` nếu xử lý kiểu đầu vào bất kỳ.

## 9. Áp dụng thực tế và các lỗi thường gặp

### Trường hợp phù hợp

- **Lập bản đồ dữ liệu / tuần tự hóa**: một thư viện có thể đánh dấu tên trường logic trên RECORD_COMPONENT, FIELD hoặc METHOD. Phải đọc hợp đồng của thư viện để biết vị trí hỗ trợ và chính sách giữ lại.
- **Ràng buộc/kiểm tra dữ liệu**: có thư viện dựa vào annotation đặt trên FIELD, METHOD, PARAMETER hoặc TYPE_USE, nhưng khả năng kiểm tra là hành vi của **thư viện cụ thể**, không phải do Java tự tạo.
- **Công cụ sinh mã hoặc phân tích mã**: có thể xử lý annotation SOURCE/CLASS trong giai đoạn biên dịch, không nhất thiết cần RUNTIME.
- **Phân tích kiểu generic và an toàn null**: annotation TYPE_USE có thể mô tả kiểu bên trong `List<...>`, nhưng Java không tự hiểu một annotation tùy ý là “không null” nếu không có trình phân tích hay runtime hỗ trợ.

### Bảng phát hiện và xử lý lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `RecordComponent.getAnnotation(...)` là `null` | Annotation chỉ target FIELD/METHOD/PARAMETER/TYPE_USE, không target RECORD_COMPONENT | Đọc đúng nơi annotation áp dụng hoặc bổ sung target đúng thiết kế |
| Không thấy annotation trên accessor sau khi viết `public String name()` | Accessor đã khai báo tường minh nên không được sao chép annotation từ thành phần | Gắn annotation trực tiếp trên accessor hoặc để accessor sinh ngầm |
| Không thấy annotation trên tham số normal canonical constructor | Tham số do tác giả khai báo tường minh | Annotate tham số ngay trong constructor |
| Annotation có trong nguồn nhưng reflection không thấy | Chính sách giữ lại `SOURCE`/`CLASS` | Dùng `RUNTIME` khi thực sự cần reflection |
| Annotation TYPE_USE không tìm được bằng `getAnnotation` của record component | Đang truy vấn declaration thay vì vị trí sử dụng kiểu | Dùng `getAnnotatedType()`, đi sâu vào cấu trúc generic nếu cần |
| Gắn `@Target(TYPE)` trên tham số thành phần | TYPE dành cho khai báo kiểu, không dành cho component | Dùng `RECORD_COMPONENT`, `TYPE_USE` hoặc mục tiêu khác đúng phạm vi |
| Tin rằng `@Label` tự kiểm tra tên/ràng buộc dữ liệu | Annotation chỉ là metadata | Thiết kế validation trong constructor hoặc sử dụng công cụ xử lý annotation |
| Một framework không nhận annotation của record | Framework đọc metadata ở nơi khác, ví dụ field thay vì component | Kiểm tra tài liệu framework về record, targets và retention |

Cách kiểm tra hiệu quả: xác định **annotation muốn mô tả đối tượng nào**, chọn `@Target` đúng, chọn `@Retention` theo thời điểm đọc, rồi viết một kiểm thử reflection ở **đúng vị trí** mà công cụ sử dụng. Đây là cách tránh phụ thuộc vào phỏng đoán rằng “annotation trên record sẽ xuất hiện ở mọi nơi”.

## 10. Tự luyện tập có đáp án

**Câu 1.** Nếu `@Target(RECORD_COMPONENT)` và `@Retention(RUNTIME)`, annotation trên `record R(@Tag String x) {}` có tự xuất hiện ở `R.class.getDeclaredField("x")` không? **Không** theo mục tiêu FIELD, vì annotation chỉ áp dụng ở RECORD_COMPONENT. Hãy đọc ở `getRecordComponents()`.

**Câu 2.** Nếu `@Target(FIELD)` trên thành phần record thì annotation có xuất hiện trong `RecordComponent.getAnnotation(...)` không? **Không**, trừ khi loại annotation còn cho phép RECORD_COMPONENT và có chính sách giữ lại thích hợp. Với FIELD, nó áp dụng cho trường sinh ngầm.

**Câu 3.** `List<@CheckedType String>` annotate phần nào? **Kiểu đối số `String`**, không phải thành phần record hay toàn bộ `List`.

**Câu 4.** Vì sao `@Retention(CLASS)` không xuất hiện qua `RecordComponent.getAnnotation(...)` lúc chạy? **Vì không có bảo đảm hiện diện ở runtime reflection**. Muốn truy vấn runtime, cần RUNTIME và đúng mục tiêu.

**Câu 5.** Một accessor được viết tường minh có tự nhận `@Target(METHOD)` từ tiêu đề record không? **Không**. Annotate trực tiếp trên phương thức nếu thư viện cần đọc ở METHOD.

**Câu 6.** Sự khác biệt của compact constructor và normal canonical constructor tường minh với annotation PARAMETER? **Compact constructor** dùng các tham số được suy ra; **normal constructor khai báo tham số tường minh** nên cần annotate trực tiếp trên các tham số theo mục đích.

**Câu 7.** Thấy `@Target(TYPE_USE)` trên `@Tag String id` có nghĩa `id` không thể `null` không? **Không**. Đây là metadata gắn với kiểu; việc thực thi ràng buộc phụ thuộc thư viện/phân tích hoặc code kiểm tra riêng.

## 11. Ghi nhớ và nguồn chuẩn

Để sử dụng annotation đúng trên record, luôn phân biệt ba câu hỏi: **annotation thuộc lớp record, thuộc khai báo thành phần hay thuộc vị trí sử dụng kiểu?** Tiếp theo là **annotation có được phép chuyển sang field/accessor/parameter không?** Cuối cùng là **công cụ đọc siêu dữ liệu lúc nào và ở đâu?**

- `@Target` quyết định nơi đặt và nơi annotation có thể được truyền.
- `@Retention` quyết định có đọc được ở runtime bằng reflection hay không.
- Annotation trên **accessor hoặc canonical constructor khai báo tường minh** cần được kiểm soát ngay tại khai báo đó.
- `TYPE_USE` và `RECORD_COMPONENT` là hai ngữ cảnh khác nhau, dù cùng xuất hiện cạnh kiểu trong tiêu đề record.
- Ngữ nghĩa này thuộc hệ thống record **đã chuẩn hóa từ Java 16 và vẫn hữu ích cho Java hiện tại**.

Tài liệu chính thức:

- [JLS Java SE 21 `8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.1): annotation trên thành phần record và nguyên tắc truyền.
- [JLS Java SE 21 `8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.3): annotation của trường và accessor sinh ngầm; accessor tường minh.
- [JLS Java SE 21 `8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4): tham số suy ra và constructor tường minh.
- [JLS Java SE 21 `9.6.4.1–2 và `9.7.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html): `@Target`, `@Retention`, vị trí annotation có hiệu lực.
- [Java SE 21 `RecordComponent` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html): các phương thức reflection trên thành phần và kiểu thành phần.
- [Oracle Java — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): mô tả annotation trên record và cơ chế truyền tới thành viên.
