# Annotation target RECORD_COMPONENT và retention khi đọc metadata

Record cho phép khai báo annotation trực tiếp trên từng component trong record header. Từ Java 16, annotation có thể sử dụng `ElementType.RECORD_COMPONENT` để chỉ rõ rằng nó áp dụng cho record component. Khi cần đọc thông tin này bằng Reflection, annotation còn phải có retention phù hợp: thông thường là `RetentionPolicy.RUNTIME`.

Hai khái niệm này giải quyết hai vấn đề khác nhau:

- **Target** quy định annotation được phép xuất hiện ở đâu, đồng thời ảnh hưởng đến việc annotation trên record component có được lan truyền tới field, accessor hoặc tham số canonical constructor hay không.
- **Retention** quy định annotation được giữ lại đến giai đoạn nào. Muốn đọc annotation bằng Reflection lúc chương trình chạy, cần `RUNTIME`.

Bài học thuộc chương **Metadata record** của module **JAVA_VERSION_JAVA16**. Các API và quy tắc dưới đây là tính năng chính thức từ Java 16, vẫn dùng được trong Java hiện đại.

## 1. Record component có thể mang annotation

Ví dụ record:

```java
record Customer(
        long id,
        String name
) {}
```

Mỗi thành phần trong record header là một record component. Ta có thể gắn annotation vào component để mô tả ý nghĩa dữ liệu, ví dụ nhãn hiển thị, quy tắc kiểm tra hoặc thông tin ánh xạ:

```java
record Customer(
        @DisplayName("Mã khách hàng") long id,
        @DisplayName("Tên khách hàng") String name
) {}
```

Để annotation chỉ áp dụng cho record component, khai báo:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface DisplayName {
    String value();
}
```

`ElementType.RECORD_COMPONENT` được bổ sung trong Java 16 cùng với record. Nó cho phép trình biên dịch kiểm tra annotation được đặt đúng vị trí record component. Annotation này không tự động trở thành annotation của field hoặc accessor tương ứng.

## 2. Target và retention khác nhau thế nào?

`@Target` và `@Retention` đều là meta-annotation dùng để định nghĩa cách một annotation hoạt động, nhưng chúng có vai trò riêng.

### 2.1. `@Target` — vị trí được phép gắn annotation

`@Target` nhận các giá trị `ElementType`. Với record, các target đáng chú ý gồm:

| Target | Vị trí áp dụng |
| --- | --- |
| `RECORD_COMPONENT` | Chính record component trong record header |
| `FIELD` | Field tương ứng |
| `METHOD` | Accessor method tương ứng |
| `PARAMETER` | Tham số của canonical constructor tương ứng |
| `TYPE_USE` | Vị trí sử dụng kiểu, ví dụ kiểu component hoặc kiểu generic lồng bên trong |

Nếu annotation chỉ khai báo:

```java
@Target(ElementType.RECORD_COMPONENT)
```

thì annotation có thể đặt trên component và được đọc qua metadata của component. Nó không được áp dụng cho field, accessor hoặc tham số constructor.

Một điểm dễ nhầm: annotation **không có** target `RECORD_COMPONENT` vẫn có thể được viết tại vị trí record component nếu target của nó phù hợp với một context liên quan như `FIELD`, `METHOD`, `PARAMETER` hoặc `TYPE_USE`. Khi đó annotation áp dụng cho khai báo tương ứng hoặc kiểu, chứ không nhất thiết áp dụng cho chính record component. Ví dụ, annotation chỉ có target `FIELD` có thể được đặt trước kiểu component và được lan truyền tới field; `RecordComponent.getAnnotation(...)` không đọc được annotation này vì nó không áp dụng trong record component context.

Ví dụ ngắn với annotation chỉ dành cho field:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface FieldTag {}

record Item(@FieldTag String code) {}

// component.getAnnotation(FieldTag.class) -> null
// Item.class.getDeclaredField("code")
//         .getAnnotation(FieldTag.class) -> annotation FieldTag
```

Nếu muốn annotation cũng xuất hiện ở các thành phần được compiler sinh ra, phải khai báo các target tương ứng. Quy tắc lan truyền cụ thể còn phụ thuộc accessor và canonical constructor được khai báo tường minh hay ngầm định; xem phần 5.

Nếu không khai báo `@Target`, annotation không bị giới hạn bởi danh sách target cụ thể. Tuy nhiên, khi thiết kế annotation cho record, khai báo rõ target giúp thể hiện chủ đích và tránh sử dụng nhầm vị trí.

### 2.2. `@Retention` — annotation được giữ đến khi nào?

`@Retention` nhận một giá trị `RetentionPolicy`:

| Retention | Hành vi | Đọc được bằng Reflection lúc runtime? |
| --- | --- | :---: |
| `SOURCE` | Chỉ tồn tại trong mã nguồn; compiler loại bỏ khỏi bytecode | Không |
| `CLASS` | Được ghi vào class file nhưng không được VM yêu cầu giữ để Reflection đọc lúc runtime | Không |
| `RUNTIME` | Được giữ để có thể truy cập bằng Reflection lúc runtime | **Có** |

Nếu không khai báo `@Retention`, retention mặc định là `CLASS`. Vì vậy, annotation có thể xuất hiện trong mã nguồn và class file nhưng `RecordComponent.getAnnotation(...)` không đọc được nó lúc chạy.

Khi mục tiêu là đọc metadata bằng Reflection, khai báo tường minh:

```java
@Retention(RetentionPolicy.RUNTIME)
```

**Ghi nhớ:** `@Target(RECORD_COMPONENT)` cho phép gắn annotation lên component; `@Retention(RUNTIME)` giúp Reflection đọc annotation ở runtime. Chỉ có một trong hai là chưa đủ cho mục tiêu này.

## 3. Ví dụ hoàn chỉnh: Đọc annotation từ RecordComponent

Lưu thành tệp `RecordComponentAnnotationDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.RecordComponent;

public class RecordComponentAnnotationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    @interface DisplayName {
        String value();
    }

    public record Customer(
            @DisplayName("Mã khách hàng") long id,
            @DisplayName("Tên khách hàng") String name
    ) {}

    public static void main(String[] args) {
        for (RecordComponent component :
                Customer.class.getRecordComponents()) {
            DisplayName annotation =
                    component.getAnnotation(DisplayName.class);

            String label = annotation == null
                    ? component.getName()
                    : annotation.value();

            System.out.printf("%s -> %s%n",
                    component.getName(), label);
        }
    }
}
```

Biên dịch và chạy bằng JDK 16 trở lên:

```bash
javac RecordComponentAnnotationDemo.java
java RecordComponentAnnotationDemo
```

Kết quả:

```text
id -> Mã khách hàng
name -> Tên khách hàng
```

Điểm chính trong ví dụ:

1. `DisplayName` được giới hạn bằng `@Target(ElementType.RECORD_COMPONENT)`.
2. `@Retention(RetentionPolicy.RUNTIME)` giúp giữ annotation cho Reflection.
3. `Customer.class.getRecordComponents()` trả về metadata từng component.
4. `component.getAnnotation(DisplayName.class)` lấy annotation gắn trực tiếp trên component.
5. Nếu không có annotation, chương trình dùng tên component làm nhãn mặc định.

`RecordComponent` cung cấp các phương thức quen thuộc của `AnnotatedElement`, gồm `getAnnotation(...)`, `getAnnotations()` và `getDeclaredAnnotations()`. Với annotation đặt trực tiếp trên component, `getAnnotation(...)` là cách đọc ngắn gọn.

## 4. Phân biệt annotation trên component với annotation trên kiểu

Một annotation có thể mô tả **component declaration** hoặc mô tả **type use**. Hai vị trí này có API Reflection tương ứng khác nhau.

- Annotation có target `RECORD_COMPONENT` được đọc từ `RecordComponent`.
- Annotation có target `TYPE_USE` được đọc từ đối tượng `AnnotatedType` mà `RecordComponent.getAnnotatedType()` trả về.

Ví dụ annotation đánh dấu kiểu dữ liệu:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.RecordComponent;
import java.util.List;

public class RecordTypeUseAnnotationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface Sensitive {}

    record Contact(List<@Sensitive String> labels) {}

    public static void main(String[] args) {
        RecordComponent component =
                Contact.class.getRecordComponents()[0];

        AnnotatedType annotatedType = component.getAnnotatedType();
        AnnotatedParameterizedType parameterizedType =
                (AnnotatedParameterizedType) annotatedType;

        AnnotatedType elementType =
                parameterizedType.getAnnotatedActualTypeArguments()[0];

        System.out.println(
                elementType.getAnnotation(Sensitive.class) != null);
    }
}
```

Kết quả:

```text
true
```

Ở đây, `@Sensitive` gắn lên kiểu phần tử `String` bên trong `List`, nên cần đi từ `getAnnotatedType()` đến tham số kiểu bằng `AnnotatedParameterizedType`. Nó không phải annotation declaration của record component và không nên tìm bằng `component.getAnnotation(Sensitive.class)`.

Với component có kiểu đơn giản như `@Sensitive String name`, annotation kiểu được đọc trực tiếp từ `component.getAnnotatedType().getAnnotation(Sensitive.class)`. Khi phân tích kiểu generic lồng nhau, cần đi tiếp qua các API `AnnotatedParameterizedType`, `AnnotatedArrayType` hoặc dạng `AnnotatedType` phù hợp.

## 5. Annotation có thể được lan truyền tới field, accessor và constructor parameter

Một record component liên quan đến các thành phần mà Java tạo ra:

- Field lưu giá trị component.
- Accessor method đọc giá trị component.
- Tham số tương ứng trong canonical constructor.

Nếu annotation khai báo nhiều target thích hợp, annotation gắn trên record component có thể được compiler lan truyền đến các thành phần tương ứng. Annotation được lan truyền theo target mà nó hỗ trợ; không phải mọi annotation component đều tự động xuất hiện ở mọi vị trí.

Có ba chi tiết cần phân biệt:

- **Field:** field component được khai báo ngầm định. Annotation được lan truyền tới field nếu annotation áp dụng trong field declaration context (`FIELD`) hoặc type context thích hợp.
- **Accessor:** annotation được lan truyền tới accessor **ngầm định** nếu annotation áp dụng trong method declaration context (`METHOD`) hoặc type context thích hợp. Nếu record tự khai báo accessor tường minh, annotation trên component không được tự động lan truyền sang method đó; cần gắn annotation trực tiếp lên method nếu muốn Reflection đọc ở đó.
- **Tham số canonical constructor:** annotation được lan truyền tới các formal parameter được khai báo ngầm định, chẳng hạn khi canonical constructor được compiler sinh hoặc được viết theo dạng compact. Nếu dùng normal canonical constructor với danh sách tham số viết tường minh, annotation trên component và annotation trên tham số có thể khác nhau; hãy gắn annotation trực tiếp lên tham số nếu cần.

Ví dụ annotation chỉ dành cho component:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentLabel {
    String value();
}
```

Với `ComponentLabel`, Reflection đọc được annotation qua `RecordComponent`. Annotation này không được sao chép sang field, accessor hoặc tham số canonical constructor vì target không bao gồm `FIELD`, `METHOD` hay `PARAMETER`.

Nếu muốn annotation có mặt ở cả các vị trí đó, khai báo target tương ứng:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.RECORD_COMPONENT,
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER
})
@interface AuditTag {
    String value();
}
```

Ví dụ hoàn chỉnh đọc annotation ở từng vị trí:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.lang.reflect.RecordComponent;

public class RecordAnnotationPropagationDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target({
            ElementType.RECORD_COMPONENT,
            ElementType.FIELD,
            ElementType.METHOD,
            ElementType.PARAMETER
    })
    @interface AuditTag {
        String value();
    }

    public record Customer(@AuditTag("customer-id") long id) {}

    public static void main(String[] args) throws ReflectiveOperationException {
        RecordComponent component =
                Customer.class.getRecordComponents()[0];

        Field field = Customer.class.getDeclaredField("id");
        Method accessor = component.getAccessor();
        Parameter constructorParameter =
                Customer.class.getDeclaredConstructor(long.class)
                        .getParameters()[0];

        System.out.println(component.getAnnotation(AuditTag.class).value());
        System.out.println(field.getAnnotation(AuditTag.class).value());
        System.out.println(accessor.getAnnotation(AuditTag.class).value());
        System.out.println(
                constructorParameter.getAnnotation(AuditTag.class).value());
    }
}
```

Kết quả:

```text
customer-id
customer-id
customer-id
customer-id
```

Ví dụ cho thấy cùng một annotation được đọc tại bốn vị trí vì `@Target` liệt kê cả bốn loại declaration. Trong ứng dụng, chỉ nên khai báo những target mà annotation thực sự cần hỗ trợ. Nếu mục đích chỉ là mô tả component cho schema, target `RECORD_COMPONENT` là đủ và rõ nghĩa hơn.

Ví dụ trên dùng accessor và canonical constructor ngầm định. Nếu record tự khai báo accessor hoặc normal canonical constructor, đừng mặc định annotation sẽ được sao chép sang các khai báo tường minh đó. Hai biến thể sau được viết bên trong cùng lớp `RecordAnnotationPropagationDemo` ở ví dụ trước, nơi annotation `AuditTag` đã được khai báo. Accessor tường minh cần có annotation trên chính method:

```java
public record Customer(@AuditTag("component") long id) {
    @AuditTag("accessor")
    public long id() {
        return id;
    }
}
```

Tương tự, với normal canonical constructor tường minh, hãy ghi annotation trên formal parameter nếu muốn đọc nó qua `Parameter.getAnnotation(...)`:

```java
public record Customer(@AuditTag("component") long id) {
    public Customer(@AuditTag("constructor-parameter") long id) {
        this.id = id;
    }
}
```

Hai đoạn trên là hai biến thể riêng của record `Customer`, không khai báo đồng thời trong cùng một lớp.

## 6. Vì sao Reflection không đọc được annotation?

Nếu `component.getAnnotation(MyAnnotation.class)` trả về `null`, hãy kiểm tra các nguyên nhân sau:

| Nguyên nhân | Hệ quả | Cách kiểm tra |
| --- | --- | --- |
| Không khai báo `@Retention` | Mặc định là `CLASS` | Thêm `@Retention(RetentionPolicy.RUNTIME)` |
| Dùng `RetentionPolicy.SOURCE` | Annotation bị loại khỏi class file | Đổi thành `RUNTIME` nếu cần đọc lúc chạy |
| Dùng `RetentionPolicy.CLASS` | Annotation có trong class file nhưng không hiện diện cho runtime reflection | Đổi thành `RUNTIME` |
| Annotation không có target `RECORD_COMPONENT` | Có thể vẫn được viết tại vị trí component nếu target phù hợp với field, method, parameter hoặc type; khi đó không đọc được như annotation của component | Kiểm tra context áp dụng và đọc đúng Field, Method, Parameter hoặc AnnotatedType |
| Đọc nhầm vị trí | Annotation có thể nằm trên field, accessor, parameter hoặc type thay vì component | Dùng API reflection tương ứng với vị trí |
| Đọc nhầm kiểu annotation | Đối số của `getAnnotation(...)` không phải annotation type đã gắn | Kiểm tra đúng class annotation |

Ví dụ annotation mặc định retention:

```java
@interface InternalNote {
    String value();
}
```

Annotation này mặc định có retention `CLASS`. Dù được đặt ở vị trí hợp lệ, Reflection không thể dùng `getAnnotation(InternalNote.class)` để đọc annotation tại runtime. Khi cần runtime metadata, khai báo rõ `@Retention(RetentionPolicy.RUNTIME)`.

Một trường hợp khác là annotation có retention runtime nhưng chỉ được áp dụng cho field. Khi đó, cần đọc bằng `Field.getAnnotation(...)`; gọi `RecordComponent.getAnnotation(...)` không tìm annotation ở field thay cho component.

## 7. Chọn API Reflection đúng vị trí

| Vị trí annotation | API để đọc |
| --- | --- |
| Record component declaration | `RecordComponent.getAnnotation(...)` |
| Field tương ứng | `Field.getAnnotation(...)` |
| Accessor method | `Method.getAnnotation(...)` |
| Tham số canonical constructor | `Parameter.getAnnotation(...)` |
| Kiểu của component | `RecordComponent.getAnnotatedType()` rồi đọc `AnnotatedType` |

Ví dụ, nếu mục tiêu là lấy nhãn của component, không cần tìm field hoặc accessor:

```java
for (RecordComponent component : Customer.class.getRecordComponents()) {
    DisplayName label = component.getAnnotation(DisplayName.class);
    if (label != null) {
        System.out.println(label.value());
    }
}
```

Nếu mục tiêu là đọc annotation đã được lan truyền, hãy truy cập đúng thành phần tương ứng. Nếu mục tiêu là đọc annotation trên kiểu generic, hãy dùng `getAnnotatedType()`. Phân biệt vị trí giúp tránh nhầm lẫn giữa metadata component và metadata của các thành phần được sinh ra.

## 8. Bài tập tự kiểm tra

Cho annotation và record:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target({
        ElementType.RECORD_COMPONENT,
        ElementType.FIELD
})
@interface ColumnName {
    String value();
}

record Order(@ColumnName("order_code") String code) {}
```

Hãy trả lời:

1. Vì sao `Order.class.getRecordComponents()[0].getAnnotation(ColumnName.class)` đọc được annotation?
2. Vì sao `Order.class.getDeclaredField("code").getAnnotation(ColumnName.class)` cũng đọc được annotation?
3. Accessor `code()` có chắc chắn có annotation `ColumnName` không?
4. Nếu bỏ `@Retention(RetentionPolicy.RUNTIME)` thì Reflection có đọc được annotation không?
5. Nếu annotation chỉ có `@Target(ElementType.TYPE_USE)` thì nên dùng API nào để đọc?

**Đáp án:**

1. Vì annotation có target `RECORD_COMPONENT` và retention `RUNTIME`.
2. Vì target bao gồm `FIELD`, nên annotation được lan truyền tới field tương ứng.
3. Không. Target không có `METHOD`, nên annotation không được lan truyền tới accessor.
4. Không. Nếu bỏ `@Retention`, retention mặc định là `CLASS`.
5. Dùng `Order.class.getRecordComponents()[0].getAnnotatedType()` rồi đọc annotation trên `AnnotatedType` tương ứng.

## Ghi nhớ

**Muốn đọc annotation gắn trực tiếp lên record component bằng Reflection, cần khai báo `@Target(ElementType.RECORD_COMPONENT)` và `@Retention(RetentionPolicy.RUNTIME)`.** Target xác định vị trí annotation có thể áp dụng và các vị trí mà annotation được lan truyền; retention xác định annotation có còn hiện diện ở runtime hay không. Dùng `RecordComponent.getAnnotation(...)` cho annotation component, `getAnnotatedType()` cho annotation trên kiểu, và API của field, method hoặc parameter khi cần đọc metadata ở các vị trí đó.

## Tài liệu tham khảo

- [Oracle Java SE API — `ElementType.RECORD_COMPONENT`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html)
- [Oracle Java SE API — `Retention` và `RetentionPolicy`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Retention.html)
- [Oracle Java SE API — `RecordComponent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html)
- [Oracle Java SE API — `AnnotatedType` và `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedType.html)
- [Java Language Specification — Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.4)
- [Java Language Specification — Record Members](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.3)
- [Java Language Specification — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4)
