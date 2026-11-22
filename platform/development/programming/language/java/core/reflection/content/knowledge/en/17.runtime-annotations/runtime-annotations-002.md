# Retention SOURCE, CLASS, RUNTIME và giới hạn quan sát của annotation trong Java

## 1. Retention trả lời câu hỏi gì?

Annotation bổ sung metadata cho khai báo hoặc vị trí dùng kiểu trong mã Java. Tuy nhiên, **không phải annotation nào xuất hiện trong mã nguồn cũng còn tồn tại ở runtime**, và không phải cứ có annotation trong class file thì Reflection thông thường sẽ đọc được.

`java.lang.annotation.RetentionPolicy` xác định **thời điểm đến đâu compiler phải giữ annotation**. Annotation type được khai báo với meta-annotation `@Retention(...)`:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Audit {
}
~~~

Trong ví dụ, các chỗ được đánh dấu `@Audit` sẽ được lưu trong class file theo dạng có thể quan sát bởi Reflection tại runtime. Nếu không khai báo `@Retention` trên annotation type thì **mặc định là `RetentionPolicy.CLASS`**, không phải `RUNTIME`.

Có ba chính sách:

| Chính sách | Trong mã nguồn | Trong class file do `javac` sinh | Reflection chuẩn lúc chạy |
| --- | --- | --- | --- |
| `SOURCE` | Có | Không giữ annotation ở vị trí sử dụng | Không tìm thấy |
| `CLASS` | Có | Có, nhưng không yêu cầu JVM duy trì để Reflection thấy | Không tìm thấy thông qua `getAnnotation` thông thường |
| `RUNTIME` | Có | Có, ở dạng metadata runtime-visible | Có thể tìm thấy khi truy vấn **đúng đối tượng/vị trí** và đúng API |

**Quan trọng:** “`RUNTIME`” là **điều kiện cần** để Java Reflection đọc annotation từ class file, nhưng không bảo đảm mọi cách gọi `getAnnotation` đều trả về nó. Cần xét annotation được đặt ở class, method, field, parameter, record component hay vị trí **TYPE_USE**, và liệu API đang hỏi đúng vị trí đó hay chưa.

## 2. Vai trò của `@Retention` và `@Target` khác nhau

Hai meta-annotation trả lời hai câu hỏi khác nhau:

- `@Retention`: annotation tồn tại tới giai đoạn nào?
- `@Target`: annotation được phép đặt ở loại vị trí nào? Ví dụ `TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `CONSTRUCTOR`, `TYPE_USE`, `TYPE_PARAMETER` hoặc `ANNOTATION_TYPE`.

Ví dụ:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RunMe {}

class Jobs {
    @RunMe
    public void run() {}
}
~~~

`RunMe` chỉ cho phép gắn trên method và có thể được Reflection đọc tại `Jobs.class.getDeclaredMethod("run").getAnnotation(RunMe.class)`. Nhưng `Jobs.class.getAnnotation(RunMe.class)` không có nhiệm vụ tìm annotation nằm trên method, nên kết quả sẽ là `null`.

Không được suy rằng `@Retention(RUNTIME)` có nghĩa annotation **tự xuất hiện ở mọi API Reflection liên quan tới class**.

## 3. Ví dụ Java 17+ độc lập: ba mức retention

Tạo file **`RetentionDemo.java`** với đầy đủ nội dung:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceMark {}

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface ClassMark {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeMark {
    String value();
}

@SourceMark
@ClassMark
@RuntimeMark("ready")
class Service {}

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface InheritedFlag {}

@InheritedFlag
class Parent {}

class Child extends Parent {}

public class RetentionDemo {
    public static void main(String[] args) {
        System.out.println("source found: "
                + Service.class.isAnnotationPresent(SourceMark.class));
        System.out.println("class found: "
                + Service.class.isAnnotationPresent(ClassMark.class));
        System.out.println("runtime found: "
                + Service.class.isAnnotationPresent(RuntimeMark.class));
        System.out.println("runtime value: "
                + Service.class.getAnnotation(RuntimeMark.class).value());
        System.out.println("declared annotation count: "
                + Service.class.getDeclaredAnnotations().length);

        System.out.println("Child declared inherited: "
                + (Child.class.getDeclaredAnnotation(InheritedFlag.class) != null));
        System.out.println("Child inherited lookup: "
                + (Child.class.getAnnotation(InheritedFlag.class) != null));
        System.out.println("SourceMark policy: "
                + SourceMark.class.getAnnotation(Retention.class).value());
    }
}
~~~

Từ thư mục chứa file trên, chạy:

~~~bash
javac --release 17 RetentionDemo.java
java RetentionDemo
~~~

Stdout chính xác, đã kiểm chứng bằng cách biên dịch Java 17 và chạy chương trình:

~~~text
source found: false
class found: false
runtime found: true
runtime value: ready
declared annotation count: 1
Child declared inherited: false
Child inherited lookup: true
SourceMark policy: SOURCE
~~~

**Giải thích:**

1. `Service` được gắn cả ba annotation trong nguồn. Reflection chỉ thấy `RuntimeMark` vì nó được giữ với `RUNTIME`. `getDeclaredAnnotations().length` bằng `1`, không phải `3`.
2. `SourceMark` không nằm trong class file của `Service` do compiler sinh theo chính sách `SOURCE`.
3. `ClassMark` vẫn có metadata trong class file, nhưng `Class.getAnnotation(ClassMark.class)` không trả về nó vì annotation không có runtime visibility.
4. `RuntimeMark("ready")` có một phần tử `value()`. Khi lấy `RuntimeMark` qua Reflection, có thể gọi `value()` để nhận `"ready"`.
5. `Child.class.getDeclaredAnnotation(InheritedFlag.class)` trả `null` vì `Child` không trực tiếp khai báo annotation. `Child.class.getAnnotation(InheritedFlag.class)` lại tìm thấy annotation được **kế thừa theo quy tắc `@Inherited`** từ `Parent`.
6. `SourceMark.class.getAnnotation(Retention.class).value()` cho ra `SOURCE`, vì ở đây ta đọc **meta-annotation `@Retention` trên chính annotation type `SourceMark`**, không đọc lần sử dụng `@SourceMark` trên `Service`. Đây là hai đối tượng bị hỏi khác nhau.

Đoạn code sử dụng `@Inherited` nhằm minh họa thêm giới hạn quan sát: retention cho phép annotation hiện diện, còn cách truy vấn có xét khai báo thừa kế hay không là một trục khác.

## 4. Đối chiếu bytecode: CLASS khác SOURCE ở đâu?

Sau khi biên dịch file ở phần 3, có thể xem class file:

~~~bash
javap -v -p Service
~~~

Trong phần thông tin annotation của kết quả `javap -v`, bạn sẽ thấy hai nhóm chính:

~~~text
RuntimeVisibleAnnotations:
    RuntimeMark(
        value="ready"
    )
RuntimeInvisibleAnnotations:
    ClassMark
~~~

Đây là **đoạn trích đã giản lược** từ output `javap`, chỉ giữ những dòng thể hiện nhóm retention; output thật còn chứa constant pool, tên kiểu đã encode, chỉ số constant và nhiều metadata khác.

- `RuntimeVisibleAnnotations` chứa `RuntimeMark`, tương ứng chính sách `RUNTIME`.
- `RuntimeInvisibleAnnotations` chứa `ClassMark`, tương ứng chính sách `CLASS`. Tên “invisible” ở đây nói về **Reflection runtime**, không có nghĩa không thể dùng công cụ đọc class file.
- Không có chỗ dùng `SourceMark` trên `Service` trong metadata annotation của class file. Annotation source có thể được **annotation processor** thấy trong quá trình biên dịch dù sau đó không được giữ trong class file.

**Cẩn trọng về cách kiểm tra:** `javap -v` đọc dữ liệu class file; `Class.getAnnotation(...)` dùng Reflection của JVM đang chạy. Hai công cụ phục vụ hai giai đoạn khác nhau. Việc `javap` nhìn thấy `ClassMark` **không mâu thuẫn** với việc `getAnnotation(ClassMark.class) == null`.

Với bytecode đã qua các trình biên dịch, bộ xử lý hoặc công cụ chỉnh sửa class file khác, metadata thực tế có thể thay đổi. Bảng retention mô tả hành vi Java thông thường khi compiler tuân theo quy tắc ngôn ngữ, không cho phép tự kết luận về mọi class file được chỉnh sửa bằng công cụ ngoài.

## 5. SOURCE: còn hữu ích dù Reflection không thấy

`RetentionPolicy.SOURCE` phù hợp với annotation có giá trị **khi biên dịch** và không cần đi vào ứng dụng đang chạy. Một annotation processor có thể truy cập các phần tử mã nguồn trong quá trình compilation bằng `javax.annotation.processing` và model `javax.lang.model`.

Những ứng dụng điển hình:

- Kiểm tra quy tắc source hoặc lint lúc compile.
- Sinh mã nguồn, metadata hoặc tài liệu từ annotation ở compile time.
- Đưa tín hiệu cho trình biên dịch hoặc công cụ xây dựng mà runtime không cần sử dụng.

Ví dụ:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateAdapter {}

@GenerateAdapter
class CustomerDto {}
~~~

Đây là **đoạn minh họa annotation và class**, không có `main` và không tự tạo output. Nếu một annotation processor được cấu hình để xử lý `GenerateAdapter`, nó có thể thấy annotation khi compile; nhưng sau khi biên dịch, `CustomerDto.class.getAnnotation(GenerateAdapter.class)` vẫn trả `null`.

**Không nhầm hai phát biểu:**

1. “Annotation `SOURCE` không tồn tại tại runtime trong class được biên dịch thông thường” — đúng.
2. “Annotation `SOURCE` không bao giờ có tác dụng” — sai: nó có thể ảnh hưởng quá trình phân tích và sinh mã lúc compile.

Một annotation type `SOURCE` không tự kích hoạt code generation. Phải có compiler/plugin/annotation processor hoặc công cụ tương ứng thực sự xử lý nó.

## 6. CLASS: có trong class file nhưng không được Reflection chuẩn nhìn thấy

`RetentionPolicy.CLASS` dành cho metadata cần được lưu vào class file nhưng không cần được VM làm sẵn qua API Reflection chuẩn. Nó là **mặc định nếu bỏ `@Retention`** trên annotation type.

Ví dụ:

~~~java
import java.lang.annotation.*;

@Target(ElementType.TYPE)
@interface BytecodeTag {}  // Mặc định RetentionPolicy.CLASS

@BytecodeTag
class AnnotatedClass {}
~~~

Đoạn trên là mã minh họa không có `main`. `BytecodeTag` sẽ được lưu tại lần sử dụng trên `AnnotatedClass` trong class file thông thường, nhưng `AnnotatedClass.class.getAnnotation(BytecodeTag.class)` không phát hiện annotation đó ở runtime.

Một bytecode analyzer/instrumenter có thể **đọc trực tiếp class file** và diễn giải annotation `CLASS` bằng thư viện phân tích bytecode (hoặc `javap` để quan sát thủ công). Điều này khác hoàn toàn việc Reflection có quyền tìm annotation đó trong JVM.

Câu hỏi cần đặt ra khi chọn retention:

- Metadata chỉ cần tới compile time? Chọn `SOURCE`.
- Metadata cần được bytecode tooling đọc, nhưng không cần Reflection runtime? Có thể chọn `CLASS`.
- Ứng dụng hoặc framework cần truy vấn annotation trên class, method, field v.v. lúc chạy? Chọn `RUNTIME` và xác định đúng vị trí truy vấn.

## 7. RUNTIME: cần thiết nhưng phải hỏi đúng nơi

Một annotation `RUNTIME` có thể được quan sát theo **vị trí gắn annotation**, nhưng Reflection có nhiều đối tượng tương ứng:

| Annotation được gắn ở đâu? | API Reflection thường dùng |
| --- | --- |
| Class/interface | `SomeClass.class.getAnnotation(...)` hoặc `getDeclaredAnnotations()` |
| Method | `Method.getAnnotation(...)`, `Method.getDeclaredAnnotations()` |
| Field | `Field.getAnnotation(...)`, `Field.getDeclaredAnnotations()` |
| Constructor | `Constructor.getAnnotation(...)` |
| Parameter declaration | `Parameter.getAnnotation(...)` qua `Executable.getParameters()` |
| Type use (generic argument, array component, return type...) | Các dạng `AnnotatedType`, ví dụ `Field.getAnnotatedType()` hoặc `Method.getAnnotatedReturnType()` |
| Record component | `RecordComponent.getAnnotation(...)` hoặc `getAnnotatedType()` tùy target |

Ví dụ phương thức:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Handler {}

class Controller {
    @Handler
    public void run() {}
}
~~~

Mã này cần import `java.lang.annotation.*`; là đoạn khai báo minh họa không có `main`. Với method được khai báo trên `Controller`:

~~~java
boolean present = Controller.class
        .getDeclaredMethod("run")
        .isAnnotationPresent(Handler.class);
~~~

Đoạn trên là một biểu thức minh họa trong method có xử lý `NoSuchMethodException`. Kết quả `true` vì truy vấn đúng **Method**, không phải `Controller.class`.

### TYPE_USE không phải lúc nào là annotation của field declaration

Một annotation đánh dấu generic type argument như `List<@NonNull String>` được gắn vào **vị trí sử dụng kiểu `String`**. Với `@Target(TYPE_USE)`, không nên mặc định gọi `Field.getAnnotation(NonNull.class)` để tìm nó; cần đi qua `AnnotatedType` của field và các type argument.

Phần 9 cung cấp ví dụ chạy được về tình huống này.

## 8. @Inherited và phạm vi kế thừa annotation

`@Inherited` là meta-annotation đặc biệt, nhưng **không tự làm annotation xuất hiện trong method/field hoặc interface của class con**.

Quy tắc cơ bản:

- Chỉ có ý nghĩa cho annotation trên **class declaration** được truy vấn thông qua cơ chế kế thừa áp dụng cho class; không làm interface annotation tự động di truyền sang class triển khai interface.
- `getAnnotation(...)` và `getAnnotations()` có thể nhìn annotation `@Inherited` từ superclass nếu subclass không khai báo annotation loại đó theo cách tương ứng.
- `getDeclaredAnnotation(...)` và `getDeclaredAnnotations()` chỉ nhìn annotation có mặt trực tiếp trên class đang xét, không tính annotation kế thừa.
- Nếu subclass khai báo annotation cùng loại phù hợp, annotation trực tiếp của nó được dùng theo quy tắc truy vấn.
- `@Inherited` không giải quyết việc annotation bị retention `SOURCE` hoặc `CLASS` làm không thể thấy qua Reflection runtime: muốn truy vấn lúc chạy vẫn cần `RUNTIME`.

Chương trình phần 3 minh họa đúng sự khác biệt: `Child.class.getDeclaredAnnotation(InheritedFlag.class)` trả `null`, nhưng `Child.class.getAnnotation(InheritedFlag.class)` không `null`.

Khi một framework tự quét interface, method, field, override hierarchy, nó có thể định nghĩa quy tắc **tự tìm trong cây kế thừa** ngoài phạm vi Java Reflection mặc định; đừng nhầm hành vi riêng của framework với `@Inherited`.

## 9. Annotation lặp lại và TYPE_USE: ví dụ mở rộng độc lập

Lưu toàn bộ chương trình sau vào file **`RetentionExtraDemo.java`**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Tags {
    Tag[] value();
}

@Tag("a")
@Tag("b")
class Tagged {}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeUseMark {}

class TypeSample {
    List<@TypeUseMark String> names;
}

public class RetentionExtraDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("direct tag count: "
                + (Tagged.class.getAnnotation(Tag.class) == null ? 0 : 1));
        System.out.println("by type count: "
                + Tagged.class.getAnnotationsByType(Tag.class).length);
        System.out.println("container present: "
                + (Tagged.class.getDeclaredAnnotation(Tags.class) != null));

        Field field = TypeSample.class.getDeclaredField("names");
        AnnotatedParameterizedType t =
                (AnnotatedParameterizedType) field.getAnnotatedType();

        System.out.println("field declaration marked: "
                + field.isAnnotationPresent(TypeUseMark.class));
        System.out.println("type argument marked: "
                + t.getAnnotatedActualTypeArguments()[0]
                        .isAnnotationPresent(TypeUseMark.class));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 RetentionExtraDemo.java
java RetentionExtraDemo
~~~

Stdout đã được xác minh:

~~~text
direct tag count: 0
by type count: 2
container present: true
field declaration marked: false
type argument marked: true
~~~

**Điều này minh họa hai giới hạn khác nhau:**

1. `@Tag` là **repeatable annotation**. Khi dùng hai lần trên một class, compiler lưu annotation container `@Tags` tại vị trí thích hợp. `getAnnotation(Tag.class)` không nhất thiết trả một trong hai `Tag`; dùng `getAnnotationsByType(Tag.class)` để lấy cả hai. Trong ví dụ, container xuất hiện trong `getDeclaredAnnotation(Tags.class)`.
2. `@TypeUseMark` nằm trên đối số kiểu `String` trong `List<@TypeUseMark String>`. `Field.isAnnotationPresent(TypeUseMark.class)` trả `false` bởi field declaration không được annotate theo target đó. Nhưng qua `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]`, Reflection đọc được annotation ở vị trí type argument.

Với repeatable annotations, annotation chứa và annotation con phải được khai báo `@Retention`/`@Target` phù hợp. Chỉ một trong hai được đánh `RUNTIME` không phải giải pháp đủ để runtime luôn khôi phục danh sách annotation lặp lại.

Ngoài ra, chú ý phân biệt `getAnnotationsByType(...)` (có thể tính trực tiếp và gián tiếp qua container) với `getDeclaredAnnotationsByType(...)` (chỉ những annotation liên quan tới vị trí khai báo hiện tại; không đi theo inheritance của superclass). Chọn API đúng mục tiêu.

## 10. Retention không đồng nghĩa đủ điều kiện quan sát mọi thứ

Một số câu hỏi chẩn đoán thường gặp:

**“Tôi đã dùng `@Retention(RUNTIME)` nhưng `getAnnotation()` vẫn trả `null`.”**

Kiểm tra lần lượt: annotation gắn đúng vào class/method/field/parameter hay TYPE_USE không; có gọi `getAnnotation` trên đúng `AnnotatedElement` không; có dùng container của repeatable annotation không; có phụ thuộc nhầm `@Inherited` qua interface hay method override không; annotation đã thực sự có trong class file được load chưa.

**“`javap -v` thấy annotation mà Java Reflection không tìm thấy.”**

Kiểm tra annotation nằm dưới `RuntimeInvisibleAnnotations` (chính sách `CLASS`), hay vị trí khác như `RuntimeVisibleTypeAnnotations`. Nếu là `CLASS`, sự khác biệt là đúng theo thiết kế. Nếu là TYPE_USE, cần dùng `AnnotatedType` đúng vị trí.

**“Annotation `SOURCE` không tìm được ở runtime nên annotation processor không thể dùng.”**

Sai. Annotation processor làm việc lúc compile và dùng source/language model; nó không cần `Class.getAnnotation`. Phạm vi retention và phạm vi tool chạy là hai vấn đề riêng.

**“Thấy một annotation type có `@Retention(SOURCE)` ở runtime nghĩa là SOURCE annotation vẫn runtime-visible.”**

Sai. Có thể đọc `@Retention` **trên chính annotation type**, vì meta-annotation `Retention` tự được giữ ở runtime. Điều đó **không biến những lần sử dụng annotation SOURCE trên đối tượng khác thành runtime-visible**.

**“Retention CLASS và RUNTIME giống nhau vì đều có trong .class.”**

Sai: class file có phân loại các attribute visible/invisible; Reflection runtime chỉ exposes thông tin được định nghĩa là runtime-visible thông qua đúng API.

## 11. Bài tập tự kiểm tra

1. Nếu bỏ `@Retention` khỏi `RuntimeMark` trong chương trình phần 3, kết quả `runtime found` và `declared annotation count` sẽ thay đổi như thế nào? Vì sao?
2. Nếu đổi `@Retention(RetentionPolicy.CLASS)` của `ClassMark` sang `RUNTIME`, dòng `class found` sẽ thay đổi thế nào? `javap -v` sẽ chuyển annotation đó sang nhóm attribute nào?
3. Với `@InheritedFlag` chỉ có trên `Parent`, vì sao hai lời gọi `Child.class.getDeclaredAnnotation(...)` và `Child.class.getAnnotation(...)` có kết quả khác nhau?
4. Tại sao `@Tag("a") @Tag("b")` cần `getAnnotationsByType(Tag.class)` để thấy cả hai?
5. Với `List<@TypeUseMark String>`, phải hỏi `AnnotatedType` ở cấp nào để thấy `TypeUseMark`?
6. Nếu công cụ đọc class file thấy `@ClassMark` nhưng `Service.class.isAnnotationPresent(ClassMark.class)` trả false, hành vi nào là phù hợp với retention policy?

## Tài liệu chuẩn

- [Java SE 17 — RetentionPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html)
- [Java SE 17 — Retention](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html)
- [Java SE 17 — AnnotatedElement (getAnnotation, getAnnotationsByType)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [Java SE 17 — AnnotatedParameterizedType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html)
- [JLS 17 §9.6.4.2 — @Retention và quy tắc retention](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2)
- [JLS 17 §9.6.4.3 — @Inherited](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.3)
- [JVMS 17 §4.7 — RuntimeVisibleAnnotations / RuntimeInvisibleAnnotations](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7)
