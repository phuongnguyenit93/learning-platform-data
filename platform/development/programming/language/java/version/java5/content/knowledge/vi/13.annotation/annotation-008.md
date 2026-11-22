# @Target và giới hạn vị trí sử dụng

## 1. @Target trả lời câu hỏi nào?

Một annotation cung cấp siêu dữ liệu cho chương trình. Khi thiết kế annotation, ta cần xác định nó mô tả lớp, trường, phương thức hay một vị trí sử dụng kiểu dữ liệu. Ví dụ, nhãn đánh dấu thao tác cần ghi nhận không nên được đặt nhầm lên trường dữ liệu.

`@Target` là **siêu annotation (meta-annotation)** đặt trên khai báo `@interface` để quy định những ngữ cảnh được phép sử dụng annotation đó. Trình biên dịch kiểm tra giới hạn này; dùng sai vị trí gây lỗi biên dịch, trước khi chương trình chạy. Đây vẫn là cơ chế hiện hành của Java. Các ví dụ dưới đây dùng Java 17 trở lên. [Tài liệu Target](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Target.html)

## 2. Khai báo một hay nhiều vị trí

Đoạn sau là phần khai báo annotation, chưa phải chương trình có hàm `main`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface OperationNote {
}

@Target({ElementType.FIELD, ElementType.PARAMETER})
@interface InputLabel {
    String value();
}
```

`value` của `@Target` có kiểu `ElementType[]`. Một phần tử có thể bỏ cặp ngoặc nhọn; nhiều phần tử tạo thành tập các vị trí được phép. Vì vậy `InputLabel` dùng được ở trường **hoặc** tham số, không yêu cầu đồng thời cả hai. Viết lặp một hằng `ElementType` trong cùng `@Target` là lỗi biên dịch. [Quy tắc Target](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Target.html)

### Các giá trị ElementType

| Giá trị | Vị trí được biểu diễn |
| --- | --- |
| `TYPE` | Khai báo lớp, interface, enum, record; bao gồm khai báo annotation |
| `ANNOTATION_TYPE` | Riêng khai báo annotation bằng `@interface` |
| `FIELD` | Khai báo trường, bao gồm hằng enum |
| `METHOD` | Khai báo phương thức |
| `CONSTRUCTOR` | Khai báo hàm khởi tạo |
| `PARAMETER` | Khai báo tham số hình thức, bao gồm tham số bắt ngoại lệ |
| `LOCAL_VARIABLE` | Khai báo biến cục bộ |
| `PACKAGE` | Khai báo package, thường đặt trong `package-info.java` |
| `TYPE_PARAMETER` | Khai báo tham số kiểu, như `T` trong `class Box<T>` |
| `TYPE_USE` | Vị trí sử dụng kiểu, như `String` trong `List<String>` |
| `MODULE` | Khai báo mô-đun Java trong `module-info.java` |
| `RECORD_COMPONENT` | Thành phần trong phần đầu khai báo record |

Đây là các vị trí của ngôn ngữ Java; `MODULE` trong bảng không có nghĩa là một thư mục hay dự án con Gradle. Với annotation chỉ dành cho khai báo annotation khác, chọn `ANNOTATION_TYPE`; chọn `TYPE` cho phép phạm vi rộng hơn. [Tài liệu ElementType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html)

## 3. Ví dụ chạy được: phương thức và hàm khởi tạo

Lưu toàn bộ chương trình vào **TargetDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

public class TargetDemo {
    @Target({ElementType.METHOD, ElementType.CONSTRUCTOR})
    @Retention(RetentionPolicy.RUNTIME)
    @interface LoggedAction {
    }

    static class OrderService {
        @LoggedAction
        OrderService() {
        }

        @LoggedAction
        void submit() {
        }

        String code;
    }

    public static void main(String[] args) throws Exception {
        boolean constructorMarked = OrderService.class
                .getDeclaredConstructor()
                .isAnnotationPresent(LoggedAction.class);

        boolean methodMarked = OrderService.class
                .getDeclaredMethod("submit")
                .isAnnotationPresent(LoggedAction.class);

        boolean fieldMarked = OrderService.class
                .getDeclaredField("code")
                .isAnnotationPresent(LoggedAction.class);

        System.out.println("constructor=" + constructorMarked);
        System.out.println("method=" + methodMarked);
        System.out.println("field=" + fieldMarked);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TargetDemo.java
java TargetDemo
```

Kết quả chuẩn:

```text
constructor=true
method=true
field=false
```

Hàm khởi tạo và phương thức có annotation vì cả hai vị trí được khai báo trong `@Target`. Trường `code` không được gắn annotation trong mã nguồn, nên kết quả là `false`.

Để quan sát việc kiểm tra vị trí, thử thêm dòng `@LoggedAction` ngay trước `String code;`, rồi biên dịch lại. Lần này `javac` báo lỗi vì thiếu `ElementType.FIELD`. Không chạy tệp `.class` từ lần biên dịch trước để suy luận rằng mã mới hợp lệ.

Tên `LoggedAction` chỉ là nhãn trong ví dụ; không có mã nào tự ghi nhật ký. `@Target` quyết định **được viết ở đâu**. `@Retention` quyết định **được lưu đến giai đoạn nào**; ví dụ chọn `RUNTIME` để reflection đọc được. Hai quyết định độc lập. Nếu không khai báo `@Retention`, chính sách mặc định là `CLASS`. [JLS §9.6.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.2)

## 4. Phân biệt khai báo với vị trí sử dụng kiểu

Xem hai dòng minh họa:

```java
@FieldLabel String name;
List<@TypeLabel String> names;
```

Ở dòng đầu, nếu `FieldLabel` có target `FIELD`, annotation mô tả **khai báo trường** `name`. Ở dòng thứ hai, annotation có target `TYPE_USE` mô tả **kiểu đối số** `String`, không mô tả bản thân trường `names`. Ngôn ngữ phân biệt hai ngữ cảnh dù annotation đều xuất hiện gần một tên kiểu. [JLS §9.7.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.7.4)

Lưu chương trình đầy đủ sau vào **TypeUseDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Field;
import java.util.List;

public class TypeUseDemo {
    @Target(ElementType.FIELD)
    @Retention(RetentionPolicy.RUNTIME)
    @interface FieldLabel {
    }

    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface TypeLabel {
    }

    static class Directory {
        @FieldLabel
        List<@TypeLabel String> names;
    }

    public static void main(String[] args) throws Exception {
        Field field = Directory.class.getDeclaredField("names");
        AnnotatedParameterizedType listType =
                (AnnotatedParameterizedType) field.getAnnotatedType();
        AnnotatedType elementType =
                listType.getAnnotatedActualTypeArguments()[0];

        System.out.println("fieldLabel="
                + field.isAnnotationPresent(FieldLabel.class));
        System.out.println("typeLabelOnField="
                + field.isAnnotationPresent(TypeLabel.class));
        System.out.println("typeLabelOnElement="
                + elementType.isAnnotationPresent(TypeLabel.class));
    }
}
```

Chạy bằng:

```shell
javac --release 17 -encoding UTF-8 TypeUseDemo.java
java TypeUseDemo
```

Kết quả:

```text
fieldLabel=true
typeLabelOnField=false
typeLabelOnElement=true
```

Reflection phải đi qua kiểu đã chú thích: `field.getAnnotatedType()`, rồi lấy đối số kiểu bằng `getAnnotatedActualTypeArguments()`. Tìm annotation trên chính `Field` không thay thế việc tìm trên kiểu lồng bên trong. [API AnnotatedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedType.html), [API AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)

### TYPE, TYPE_PARAMETER và TYPE_USE không đồng nghĩa

Đoạn này minh họa vị trí, không phải chương trình độc lập:

```java
@Target(ElementType.TYPE_PARAMETER)
@interface SlotLabel {
}

@Target(ElementType.TYPE_USE)
@interface ValueLabel {
}

class Box<@SlotLabel T> {
    java.util.List<@ValueLabel String> values;
}
```

`TYPE_PARAMETER` nhắm vào **khai báo** `T`; `TYPE_USE` nhắm vào **việc sử dụng** kiểu. `TYPE_USE` còn được phép trên khai báo lớp/interface và tham số kiểu theo quy tắc Java; không nên xem các tập vị trí này là hoàn toàn tách biệt. `TYPE` riêng lẻ không cho phép viết annotation bên trong `List<...>`. [Phạm vi ElementType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/ElementType.html)

Có thể chú thích kiểu phần tử hoặc kiểu mảng tại vị trí khác nhau:

```java
@ValueLabel String[] elementsMarked;
String @ValueLabel [] arrayMarked;
```

Hai dòng là các khai báo trường hợp lệ trong một lớp có định nghĩa `ValueLabel` ở trên. Dòng đầu chú thích kiểu `String`; dòng sau chú thích kiểu mảng. Vị trí dấu `[]` mang ý nghĩa, không chỉ là cách trình bày. [JLS §4.11](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.11)

Annotation mang tên `NonNull` hay `Positive` cũng không khiến JVM tự chặn giá trị sai. Muốn có kiểm tra tương ứng phải có công cụ, bộ xử lý hoặc mã thực thi đọc và diễn giải annotation đó.

## 5. Không khai báo @Target khác với @Target({})

- **Không có `@Target`:** annotation dùng được trong các ngữ cảnh khai báo theo quy tắc Java; không tự được phép trong các ngữ cảnh sử dụng kiểu như `List<@A String>`.
- **`@Target({})`:** không cho phép dùng annotation để chú thích trực tiếp một khai báo hay kiểu. Nó vẫn có thể làm giá trị annotation lồng trong annotation khác.

Ví dụ khai báo hoàn chỉnh, có thể lưu thành **NestedTargetExample.java** rồi biên dịch, không có `main`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({})
@interface MappingEntry {
    String source();
    String destination();
}

@Target(ElementType.TYPE)
@interface MappingPlan {
    MappingEntry[] value();
}

@MappingPlan({
    @MappingEntry(source = "customerId", destination = "id")
})
class NestedTargetExample {
}
```

Lệnh:

```shell
javac --release 17 -encoding UTF-8 NestedTargetExample.java
```

Thành công không in stdout. `@MappingEntry(...)` nằm trong giá trị của `@MappingPlan`, nên hợp lệ; đặt nó trực tiếp lên lớp sẽ không hợp lệ. [Target: tập vị trí rỗng](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/annotation/Target.html), [JLS: ngữ cảnh mặc định](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.6.4.1)

## 6. Record: thành phần không đồng nhất với trường hay phương thức

Record có thành phần, trường lưu trữ, phương thức truy cập và tham số hàm khởi tạo tương ứng. Các đối tượng này có vị trí annotation riêng.

Lưu vào **RecordTargetDemo.java**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.RecordComponent;

public class RecordTargetDemo {
    @Target(ElementType.RECORD_COMPONENT)
    @Retention(RetentionPolicy.RUNTIME)
    @interface PartLabel {
    }

    record Customer(@PartLabel String name) {
    }

    public static void main(String[] args) throws Exception {
        RecordComponent component =
                Customer.class.getRecordComponents()[0];

        System.out.println("component="
                + component.isAnnotationPresent(PartLabel.class));
        System.out.println("field="
                + Customer.class.getDeclaredField("name")
                    .isAnnotationPresent(PartLabel.class));
        System.out.println("accessor="
                + Customer.class.getDeclaredMethod("name")
                    .isAnnotationPresent(PartLabel.class));
        System.out.println("constructorParameter="
                + Customer.class.getDeclaredConstructor(String.class)
                    .getParameters()[0]
                    .isAnnotationPresent(PartLabel.class));
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 RecordTargetDemo.java
java RecordTargetDemo
```

Kết quả:

```text
component=true
field=false
accessor=false
constructorParameter=false
```

Ở đây annotation chỉ có target `RECORD_COMPONENT`. Với annotation đặt trên thành phần record, việc truyền sang trường, phương thức truy cập được sinh tự động hoặc tham số hàm khởi tạo chuẩn phụ thuộc các target tương ứng `FIELD`, `METHOD`, `PARAMETER` và quy tắc record. Không suy luận rằng “đã xuất hiện ở phần đầu record thì mọi đối tượng liên quan đều có annotation”. [JLS §8.10](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.3)

## 7. Chọn target và chẩn đoán lỗi

Khi thiết kế annotation, xác định thông tin mô tả đối tượng nào và công cụ tiêu thụ sẽ đọc ở đâu, rồi khai báo tập vị trí phù hợp. Ví dụ: thông tin cột dữ liệu đặt trên trường dùng `FIELD`; thông tin thao tác đặt trên phương thức dùng `METHOD`; nhãn trên kiểu đối số generic cần `TYPE_USE`. Chỉ mở thêm vị trí khi đã xác định ý nghĩa và cách xử lý của vị trí đó.

Các lỗi nên tự kiểm tra:

- Gắn annotation dành cho `METHOD` lên hàm khởi tạo: thêm `CONSTRUCTOR` nếu thiết kế thực sự cần hỗ trợ.
- Dùng `TYPE` rồi đặt vào `List<@A String>`: cần xem lại yêu cầu về `TYPE_USE`.
- Thấy biên dịch thành công nhưng reflection không tìm thấy: kiểm tra `@Retention`, rồi kiểm tra đang đọc khai báo hay kiểu lồng bên trong.
- Mở tất cả target chỉ để hết lỗi: mã có thể biên dịch nhưng bên tiêu thụ chưa có cách xử lý những vị trí mới.
- Đổi target của annotation dùng chung: biên dịch lại nơi sử dụng; thu hẹp target có thể làm mã nguồn trước đó hợp lệ bị lỗi.

### Tự thực hành

1. Trong `TargetDemo`, chuyển `@LoggedAction` từ phương thức sang trường `code`. Dự đoán kết quả biên dịch trước khi chạy.
2. Đổi `@Target` của `LoggedAction` thành chỉ `METHOD`. Vì sao annotation trên hàm khởi tạo bị từ chối?
3. Trong `TypeUseDemo`, bỏ `@TypeLabel` khỏi đối số `String`. Dự đoán ba dòng kết quả.
4. Trong `RecordTargetDemo`, thêm `FIELD` vào target của `PartLabel`, rồi chạy lại. Dòng `field` sẽ thành `true`; các dòng `accessor` và `constructorParameter` vẫn là `false`.

Bài kiểm tra quan trọng là giải thích được **annotation đang gắn với khai báo nào hoặc phần kiểu nào**, sau đó mới chọn `ElementType`.
