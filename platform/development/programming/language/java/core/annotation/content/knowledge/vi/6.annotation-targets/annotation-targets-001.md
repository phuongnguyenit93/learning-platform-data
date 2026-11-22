# `@Target` và tập giá trị `ElementType` trong Java

## 1. Mục đích của `@Target`

Trong Java, một annotation có thể xuất hiện tại nhiều vị trí: trên class, method, field, parameter, kiểu trong generic, record component... Không phải annotation nào cũng hợp lệ ở mọi nơi. **`@Target` là meta-annotation quy định các loại vị trí được phép gắn một annotation type**. Các vị trí đó được liệt kê bằng enum `java.lang.annotation.ElementType`.

Ví dụ một annotation chỉ dành cho method:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@interface TraceCall {
}

class Service {
    @TraceCall
    void execute() {
    }
}
~~~

`@TraceCall` hợp lệ ở `execute()` vì đây là khai báo method. Đưa `@TraceCall` lên khai báo class hoặc field sẽ gây lỗi **ngay khi biên dịch** vì không thuộc target `METHOD`. `@Target` không tạo logic ghi nhật ký; `TraceCall` chỉ cung cấp metadata, và hành vi ghi log đòi hỏi chương trình hoặc framework thực sự xử lý nó.

Các package cần nhận diện:

- `java.lang.annotation.Target`: annotation được đặt **trên một khai báo `@interface`** để chỉ định vị trí sử dụng.
- `java.lang.annotation.ElementType`: enum định danh các vị trí khai báo hoặc sử dụng kiểu.
- `java.lang.annotation.Retention` và `RetentionPolicy`: quyết định annotation có tồn tại ở source, class file hay runtime. Đây là khía cạnh **khác** với nơi annotation được phép xuất hiện.

## 2. Cú pháp của `@Target`

`Target` khai báo một phần tử `value()` có kiểu `ElementType[]`. Trong Java, phần tử mang tên `value` được phép dùng cú pháp rút gọn, và một mảng chỉ gồm một phần tử có thể bỏ dấu ngoặc nhọn khi cung cấp giá trị annotation.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface FieldOnly {
}

@Target(value = ElementType.FIELD)
@interface AlsoFieldOnly {
}

@Target({ElementType.FIELD, ElementType.METHOD})
@interface FieldOrMethod {
}

@Target(value = {ElementType.FIELD, ElementType.METHOD})
@interface AlsoFieldOrMethod {
}
~~~

`FieldOnly` và `AlsoFieldOnly` có cùng tập vị trí hợp lệ; tương tự cho hai khai báo cuối. Khi một annotation được phép ở **nhiều** loại vị trí, viết các hằng trong `{...}` và phân cách bằng dấu phẩy. Tập target không có thứ tự ưu tiên.

Một giá trị `ElementType` không được lặp trong một `@Target`:

~~~java
// Mã SAI: cùng một enum constant xuất hiện hai lần.
// @Target({ElementType.FIELD, ElementType.FIELD})
// @interface Invalid {}
~~~

Sự lặp trên là lỗi của **danh sách target**, hoàn toàn khác quy tắc về việc một annotation có được gắn lặp lại trên một khai báo hay không (`@Repeatable`).

### Nếu annotation không khai báo `@Target`

~~~java
@interface GeneralMark {
}
~~~

Theo JLS Java SE 17, `GeneralMark` có thể được dùng tại **mọi declaration context** nhưng không tại **type context**. Vì vậy bỏ `@Target` không phải cách đơn giản để cho phép mọi hình thức type-use. Ví dụ `List<@GeneralMark String>` không hợp lệ nếu không có `@Target(ElementType.TYPE_USE)`.

Dùng `@Target` tường minh giúp API dễ hiểu hơn và bắt lỗi sai vị trí ngay lúc compile.

## 3. Đầy đủ 12 giá trị `ElementType` của Java 17

Java SE 17 có **12 hằng** trong `ElementType`. Mười một hằng nhận diện các loại vị trí khai báo hoặc định nghĩa đặc biệt, và `TYPE_USE` xác định các ngữ cảnh sử dụng kiểu.

| Hằng `ElementType` | Đích được mô tả | Ví dụ hoặc cách dùng |
| --- | --- | --- |
| `TYPE` | Khai báo class, interface (kể cả annotation interface), enum, record | `@Mark class User {}` |
| `FIELD` | Khai báo field, kể cả enum constant | `@Mark String id;` |
| `METHOD` | Khai báo method, gồm phương thức phần tử của annotation type | `@Mark void save() {}` |
| `PARAMETER` | Khai báo tham số hình thức (method, constructor, tham số `catch` tương ứng) | `void save(@Mark String s)` |
| `CONSTRUCTOR` | Khai báo constructor | `@Mark User() {}` |
| `LOCAL_VARIABLE` | Khai báo biến cục bộ | `@Mark String temp = "";` |
| `ANNOTATION_TYPE` | Khai báo một annotation type | `@Mark @interface Rule {}` |
| `PACKAGE` | Khai báo package | Thường khai báo annotation trong `package-info.java` |
| `TYPE_PARAMETER` | Khai báo type parameter của generic class, interface, method, constructor | `class Box<@Mark T> {}` |
| `TYPE_USE` | Các vị trí sử dụng kiểu | `List<@Mark String>`, kiểu field, kiểu cast |
| `MODULE` | Khai báo module | `module-info.java` |
| `RECORD_COMPONENT` | Khai báo record component | `record User(@Mark String name) {}` |

Lịch sử phiên bản quan trọng: `TYPE_PARAMETER` và `TYPE_USE` được thêm trong Java 8, `MODULE` trong Java 9, `RECORD_COMPONENT` trong Java 16. Chúng đều có mặt trong Java 17.

Những phân biệt thiết yếu:

- **`FIELD` khác `LOCAL_VARIABLE`**: biến thành viên là field, còn biến khai báo trong thân method là local variable; không nên gọi mọi biến Java là field.
- **`METHOD` khác `CONSTRUCTOR`**: constructor có đích riêng; không thể dùng target `METHOD` chỉ vì constructor có danh sách tham số.
- **`PARAMETER` khác `TYPE_PARAMETER`**: một cái đánh dấu biến nhận đối số khi gọi method/constructor; cái kia đánh dấu ký hiệu kiểu generic như `T`.
- **`TYPE` khác `ANNOTATION_TYPE`**: `TYPE` rộng hơn và bao gồm cả khai báo annotation interface; `ANNOTATION_TYPE` chỉ áp dụng cho khai báo `@interface`.
- **`RECORD_COMPONENT` khác `FIELD`**: component được khai báo trong header record có mô hình phản chiếu riêng, dù compiler có thể tạo field, accessor, và tham số constructor liên quan.
- **`TYPE_USE` khác `TYPE`**: một cái mô tả **kiểu được sử dụng**, cái kia chủ yếu mô tả **khai báo định nghĩa kiểu**.

## 4. Declaration annotation và type-use annotation

Đây là phân biệt quan trọng nhất khi học `@Target`.

### Annotation trên một khai báo

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.FIELD)
@interface AuditedField {
}

class Account {
    @AuditedField
    String number;
}
~~~

`@AuditedField` đánh dấu **khai báo field** `number`. Bộ xử lý có thể kiểm tra field mang metadata này. Nó không thay đổi kiểu `String`, không tự mã hóa và cũng không thực thi một hành động nào.

### Annotation trên một lần sử dụng kiểu

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_USE)
@interface TaggedType {
}

class Names {
    List<@TaggedType String> names;
}
~~~

`@TaggedType` đánh dấu **kiểu `String` làm type argument** trong `List<String>`. Đây là type-use, khác với gắn annotation lên bản thân field `names`.

`TYPE_USE` còn có thể dùng tại kiểu trả về, kiểu field, kiểu tham số, kiểu cast, kiểu trong phép `new`, phần của array hoặc generic, và nhiều vị trí sử dụng kiểu khác được JLS định nghĩa. Ví dụ `(@TaggedType String) input` chú thích kiểu đích của cast, nhưng **không khiến cast an toàn hơn** hay tự thêm validation.

Điểm cần tránh nói quá: `@Target(TYPE_USE)` cũng có thể được đặt trên **khai báo class/interface và khai báo type parameter** theo quy tắc Java. Nó không bị giới hạn đơn giản ở phần thân biểu thức. Bản chất của `TYPE_USE` là phạm vi **type contexts** của ngôn ngữ, có các quy tắc giao thoa với declaration contexts.

### `TYPE_PARAMETER` khác `TYPE_USE`

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.TYPE_PARAMETER)
@interface GenericDeclaration {
}

@Target(ElementType.TYPE_USE)
@interface TypeArgument {
}

class Box<@GenericDeclaration T> {
    List<@TypeArgument String> items;
}
~~~

`@GenericDeclaration` đánh dấu **lúc định nghĩa biến kiểu `T`**. `@TypeArgument` đánh dấu **kiểu `String` được truyền vào generic `List`**. Khi muốn hỗ trợ cả hai loại vị trí, có thể khai báo `@Target({ElementType.TYPE_PARAMETER, ElementType.TYPE_USE})` nếu điều đó phù hợp với API; nhưng cần nhớ một `TYPE_USE` cũng có những vị trí khai báo được phép theo JLS.

### Phân loại dựa trên metadata, không chỉ dựa trên dòng chữ

Ví dụ:

~~~java
@Target(ElementType.FIELD)
@interface OnField {
}

@Target(ElementType.TYPE_USE)
@interface OnType {
}

class Entry {
    @OnField
    private @OnType String key;
}
~~~

`@OnField` nhắm vào khai báo field, còn `@OnType` nhắm vào **type của field**. Tại runtime, nếu retention là `RUNTIME`, hai loại có thể được đọc qua các API khác nhau:

- `Field.getAnnotation(OnField.class)`: tìm declaration annotation của field.
- `Field.getAnnotatedType().getAnnotation(OnType.class)`: tìm type annotation của kiểu field.

Trường hợp một annotation type nhắm **cả `FIELD` và `TYPE_USE`**, JLS còn quy định cách chú thích ở một vị trí cú pháp có thể thuộc cả hai ngữ cảnh. Cần xem target và quy tắc ngôn ngữ trước khi kết luận nó chỉ là declaration hay type-use annotation.

## 5. Ví dụ Java 17 chạy độc lập

Tạo duy nhất tệp **`TargetDemo.java`** dưới đây để quan sát trực tiếp target của field, method, type-use, generic type parameter và record component.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD})
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMarker {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_PARAMETER)
@interface GenericMarker {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ComponentMarker {
}

class Storage<@GenericMarker T> {
    @Label("database-key")
    private @TypeMarker String code = "A-01";

    @Label("read")
    String read() {
        return code;
    }
}

record Item(@ComponentMarker int id) {
}

public class TargetDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Field field = Storage.class.getDeclaredField("code");
        Method method = Storage.class.getDeclaredMethod("read");

        System.out.println("Field label: "
                + field.getAnnotation(Label.class).value());
        System.out.println("Method label: "
                + method.getAnnotation(Label.class).value());
        System.out.println("Type-use on field type: "
                + field.getAnnotatedType()
                       .isAnnotationPresent(TypeMarker.class));
        System.out.println("Type parameter: "
                + Storage.class.getTypeParameters()[0]
                       .isAnnotationPresent(GenericMarker.class));
        System.out.println("Record component: "
                + Item.class.getRecordComponents()[0]
                       .isAnnotationPresent(ComponentMarker.class));
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac TargetDemo.java
java TargetDemo
~~~

Kết quả **stdout** chính xác:

~~~text
Field label: database-key
Method label: read
Type-use on field type: true
Type parameter: true
Record component: true
~~~

Lý giải:

1. `Label` có hai target `FIELD` và `METHOD`, nên `Field.getAnnotation` và `Method.getAnnotation` thấy các giá trị tương ứng.
2. `TypeMarker` có `TYPE_USE`, đặt trên kiểu `String` của field. Vì vậy truy cập qua `field.getAnnotatedType()`.
3. `GenericMarker` nhắm khai báo `T` của `Storage<T>`; `Class.getTypeParameters()[0]` trả về `TypeVariable` có thể truy cập annotation được giữ tại runtime.
4. `ComponentMarker` nhắm component `id` trong record, được đọc qua `Class.getRecordComponents()[0]`.
5. Tất cả được khai báo `@Retention(RUNTIME)` vì bài sử dụng **runtime reflection** để quan sát metadata.

Có thể tự tạo lỗi compile-time để hiểu target. Đổi `Label` thành:

~~~java
@Target(ElementType.METHOD)
@interface Label {
    String value();
}
~~~

Sau thay đổi này, `@Label("database-key")` đặt trên field `code` không còn hợp lệ. Chỉ thêm `@Retention(RUNTIME)` không thể chữa lỗi, vì retention không thay đổi tập vị trí được phép.

Tương tự, nếu đổi `GenericMarker` sang target `METHOD`, việc đặt nó trên `T` của `Storage<T>` sẽ bị compiler từ chối. Đây là lỗi **ở source/compile**, chưa cần chạy chương trình.

## 6. Hai vị trí đặc biệt: package và module

### Package: `ElementType.PACKAGE`

Annotation gắn lên khai báo package thường nằm trong **`package-info.java`**. Ví dụ nhiều tệp sau chỉ mô tả cấu trúc dự án, không phải một chương trình độc lập.

Tệp `src/example/library/PackageTag.java`:

~~~java
package example.library;

import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.PACKAGE)
public @interface PackageTag {
}
~~~

Tệp `src/example/library/package-info.java`:

~~~java
@PackageTag
package example.library;
~~~

`@PackageTag` đánh dấu **package `example.library`**, không tự động biến mọi class trong package thành class được gắn `@PackageTag`.

### Module: `ElementType.MODULE`

Trong dự án dùng Java Platform Module System, annotation nhắm `MODULE` được dùng trên khai báo module tại `module-info.java`. Ví dụ mô tả cú pháp:

~~~java
@com.example.ModuleTag
module example.app {
}
~~~

Để biên dịch, `com.example.ModuleTag` phải là annotation type hợp lệ và được định nghĩa với `@Target(ElementType.MODULE)`, đồng thời module phải được bố trí đúng trong project. Đoạn trên **chỉ là fragment minh họa**, không thể chạy độc lập thiếu định nghĩa annotation và cấu trúc module.

## 7. `RECORD_COMPONENT` và điều cần lưu ý về propagation

Một record:

~~~java
record Person(String name, int age) {
}
~~~

có hai record components `name` và `age` trong header. Target `RECORD_COMPONENT` dùng cho vị trí đó:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
@interface ColumnName {
    String value();
}

record Person(@ColumnName("full_name") String name) {
}
~~~

Đây là đoạn mã minh họa độc lập về kiểu, chưa có phương thức `main`. Nếu đọc `Person.class.getRecordComponents()[0].getAnnotation(ColumnName.class)`, có thể lấy giá trị `full_name`.

Java có quy tắc **propagation**: annotation viết trên record component có thể được truyền sang field, accessor hoặc tham số constructor tương ứng nếu annotation type được phép áp dụng tại các declaration/type contexts đó. Khi annotation chỉ nhắm `RECORD_COMPONENT`, không nên giả định sẽ nhìn thấy nó trên field hay method. Để đọc đúng thông tin của **component**, dùng `RecordComponent` và retention phù hợp.

## 8. `@Target` và `@Retention` giải quyết hai bài toán khác nhau

| Khía cạnh | `@Target` | `@Retention` |
| --- | --- | --- |
| Câu hỏi | Annotation được đặt **ở đâu**? | Metadata được lưu **đến khi nào**? |
| Giá trị | Một hay nhiều `ElementType` | Một `RetentionPolicy` |
| Ví dụ | `@Target(METHOD)` | `@Retention(RUNTIME)` |
| Compiler kiểm tra | Vị trí đặt annotation hợp lệ không | Metadata cần được giữ trong class file/runtime không |
| Có tự chạy nghiệp vụ? | Không | Không |

`RetentionPolicy.SOURCE` chỉ cần phục vụ source/compiler; `RetentionPolicy.CLASS` lưu metadata trong class file nhưng thông thường runtime reflection không truy cập; `RetentionPolicy.RUNTIME` hỗ trợ reflection tại những nơi có API thích hợp.

Một lưu ý quan trọng với `LOCAL_VARIABLE`: runtime reflection không cung cấp `LocalVariable.getAnnotation()` để tự do truy vấn khai báo local variable trong thân method. Không thể nghĩ rằng chỉ cần `@Retention(RUNTIME)` là mọi annotation trên local variable đều truy cập được như class và field. Annotation **trên kiểu** của biến local có các quy tắc ghi bytecode khác với annotation **trên khai báo** biến đó.

## 9. Các nhầm lẫn thường gặp

**Nhầm 1 — `TYPE` có thể dùng ở mọi nơi xuất hiện một tên kiểu.** Sai. `TYPE` chủ yếu áp dụng cho khai báo định nghĩa class/interface/enum/record; kiểu được sử dụng trong `List<@Mark String>` cần `TYPE_USE`.

**Nhầm 2 — `TYPE_PARAMETER` và `PARAMETER` là một.** Sai. `<T>` thuộc generic type parameter; `void method(String input)` có formal parameter.

**Nhầm 3 — `FIELD` bao gồm mọi biến.** Sai. Biến local có `LOCAL_VARIABLE`; component record có target chuyên biệt.

**Nhầm 4 — constructor là một `METHOD`.** Sai. Annotation trực tiếp trên declaration constructor cần target `CONSTRUCTOR`.

**Nhầm 5 — không viết `@Target` tương đương đặt mọi `ElementType`.** Sai. Quy tắc mặc định cho declaration contexts; type contexts không được bao gồm.

**Nhầm 6 — `ANNOTATION_TYPE` giống hệt `TYPE`.** Sai. `ANNOTATION_TYPE` chỉ khai báo `@interface`, còn `TYPE` có phạm vi rộng hơn.

**Nhầm 7 — `TYPE_USE` tuyệt đối không bao gồm vị trí khai báo.** Sai. Java cho phép một số trường hợp như khai báo class/interface và type parameter theo quy tắc JLS.

**Nhầm 8 — `@Target` có thể kích hoạt validation hoặc logging.** Sai. Nó chỉ giới hạn vị trí; cần bộ xử lý hay framework để thực hiện nghiệp vụ.

**Nhầm 9 — runtime annotation trên record component chắc chắn có mặt trên accessor/field.** Sai nếu không xét target và quy tắc propagation.

**Nhầm 10 — thêm `@Retention(RUNTIME)` sẽ làm annotation sai target biên dịch được.** Sai vì target và retention độc lập.

## 10. Bài tập và đáp án

**Bài 1.** Một annotation có `@Target({ElementType.FIELD, ElementType.PARAMETER})`. Có thể đặt trên biến thành viên, biến local, tham số method và khai báo method không?  
**Đáp án:** Có trên biến thành viên (field) và khai báo tham số; không trên biến local và khai báo method.

**Bài 2.** Nếu muốn gắn `@Mark` tại `Map<String, @Mark Integer>`, cần target nào?  
**Đáp án:** `TYPE_USE`; `Integer` tại đây là type argument.

**Bài 3.** `class Container<@Mark T>` gắn annotation vào phần nào?  
**Đáp án:** Khai báo generic type parameter `T`; dùng `TYPE_PARAMETER` (hoặc annotation type hỗ trợ type contexts theo JLS).

**Bài 4.** `@Target(ElementType.METHOD)` có cho phép đặt trên constructor không?  
**Đáp án:** Không. Constructor declaration cần `CONSTRUCTOR`.

**Bài 5.** `@Target(ElementType.TYPE)` có thể dùng trên khai báo `@interface MyRule` không?  
**Đáp án:** Có. Annotation interface là một loại interface; `ANNOTATION_TYPE` là lựa chọn hẹp hơn nếu chỉ muốn gắn trên annotation type.

**Bài 6.** Tại sao `Field.getAnnotation(Mark.class)` không phải luôn là cách đọc một `TYPE_USE` annotation đặt trước kiểu field?  
**Đáp án:** Declaration annotation và type annotation có thể nằm ở các vị trí metadata khác nhau. Đối với type-use trên kiểu field, dùng `Field.getAnnotatedType()`.

**Bài 7.** Thêm `@Retention(RUNTIME)` có làm `@Target(FIELD)` sử dụng hợp lệ trên method không?  
**Đáp án:** Không. Retention không thay đổi target.

**Bài 8.** Trong `TargetDemo.java`, nếu đổi target của `ComponentMarker` thành chỉ `METHOD`, điều gì xảy ra?  
**Đáp án:** `@ComponentMarker` trên record component `id` không hợp lệ, nên compilation thất bại.

## 11. Nguồn chuẩn để tra cứu

- [JLS Java SE 17 — §9.6.4.1 `@Target`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.1)
- [JLS Java SE 17 — §9.7.4 Where Annotations May Appear](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.4)
- [Java SE 17 API — `ElementType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html)
- [Java SE 17 API — `Target`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html)

Thiết kế annotation bắt đầu từ việc xác định **đang chú thích một declaration hay một type use**. Khi đã chọn đúng `ElementType`, hãy bổ sung retention và logic xử lý phù hợp với nhu cầu của ứng dụng.