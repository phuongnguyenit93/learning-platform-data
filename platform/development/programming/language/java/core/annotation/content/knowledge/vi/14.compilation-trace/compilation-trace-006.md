# Đối chiếu mã nguồn, class file và kết quả reflection của annotation Java

Một annotation được viết trong mã nguồn **không nhất thiết tồn tại trong class file**, và một annotation có mặt trong class file **không nhất thiết được Java reflection trả về**. Đây là điểm mấu chốt khi debug framework tìm annotation, khi đọc kết quả `javap -v` hoặc khi thấy IDE hiển thị metadata nhưng chương trình `getAnnotation(...)` lại trả `null`.

Có thể xem quá trình theo ba lớp bằng chứng:

~~~text
Mã nguồn Java (.java)
    |
    | javac: kiểm tra @Target, element values, annotation processors...
    v
Class file (.class) + các attributes được biên dịch giữ lại
    |
    | JVM nạp class và reflection xét loại annotation, retention, vị trí
    v
Kết quả từ Class / Field / Method / AnnotatedType / ... khi chạy
~~~

Bài này hướng dẫn đối chiếu **mã nguồn → bytecode/class file → reflection** với một ví dụ Java 17 có thể chạy. Trọng tâm là phân biệt `@Retention(SOURCE)`, `CLASS`, `RUNTIME`; đọc đúng vùng metadata từ `javap -v`; và giải thích những trường hợp có dữ liệu trong class file nhưng API reflection thông thường không tìm thấy.

## 1. Ba câu hỏi trước khi điều tra một annotation

Khi thấy annotation như:

~~~java
@Audited("checkout")
class CheckoutService {}
~~~

cần hỏi **ba câu khác nhau**:

1. **Mã nguồn có annotation hợp lệ không?** Trình biên dịch kiểm tra annotation type tồn tại, `@Target` cho phép vị trí áp dụng, element `value` đúng kiểu và biểu thức giá trị hợp lệ. Annotation processor có thể tiêu thụ metadata ngay khi biên dịch.
2. **Compiler có ghi annotation lên class file của `CheckoutService` không?** Điều này phụ thuộc `@Retention` và loại vị trí. Annotation `SOURCE` thông thường không xuất hiện trên class file đích; `CLASS` hoặc `RUNTIME` có thể được lưu trong attribute tương ứng.
3. **Reflection có thể tìm thấy nó không?** Thông thường annotation phải có `RetentionPolicy.RUNTIME`, còn phải truy vấn **đúng phần tử** như `Class`, `Method`, `Field` hoặc `AnnotatedType`. Một annotation trên method không tự biến thành annotation trên class chứa method đó.

Đừng suy luận rằng ba câu trả lời sẽ giống nhau. Đặc biệt, `javap -v` có thể hiển thị metadata mà `SomeClass.class.getAnnotation(...)` **không trả về**.

## 2. @Retention: mắt xích quyết định giữa source, class file và runtime

`@Retention` đặt trên **khai báo annotation type**, không phải tự động thay đổi tùy từng chỗ sử dụng annotation.

| Retention | Trong source | Trên class file đích | Qua reflection runtime thông thường |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Có | Không giữ annotation đó trong binary representation | Không |
| `RetentionPolicy.CLASS` | Có | Có, trừ những trường hợp đặc biệt được JLS loại trừ | Không được cung cấp như runtime annotation |
| `RetentionPolicy.RUNTIME` | Có | Có, trừ những trường hợp đặc biệt được JLS loại trừ | Có thể đọc nếu truy vấn đúng annotated element/type |

**Mặc định** khi annotation type không khai báo `@Retention` là **`RetentionPolicy.CLASS`**, không phải `SOURCE` hoặc `RUNTIME`.

Một minh họa ngắn (chỉ là các khai báo, chưa phải file hoàn chỉnh):

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@interface CheckedAtCompileTime {}

@Retention(RetentionPolicy.CLASS)
@interface StoredInBytecode {}

// Không có @Retention => mặc định CLASS.
@interface AlsoStoredInBytecode {}

@Retention(RetentionPolicy.RUNTIME)
@interface VisibleAtRuntime {}
~~~

Từ đây suy ra:

- `SOURCE` phù hợp cho các công cụ phân tích/kiểm tra hoặc annotation processor chỉ cần thông tin trong vòng biên dịch.
- `CLASS` phù hợp khi cần metadata ở binary level, công cụ đọc/biến đổi class file hoặc các bước xử lý sau khi biên dịch; reflection runtime Java không tự expose nó.
- `RUNTIME` phù hợp khi thư viện/framework dùng reflection để tìm metadata khi chương trình chạy.

**Lưu ý ngoại lệ:** JLS quy định annotation **trên khai báo biến cục bộ** và **trên khai báo tham số hình thức của lambda** không được giữ trong binary representation, kể cả annotation type có retention CLASS/RUNTIME. Annotation trên **kiểu** của biến cục bộ/lambda parameter với `TYPE_USE` là một trường hợp khác và có thể được lưu theo quy tắc type annotations. Vì vậy không nên viết quy tắc quá rộng kiểu “mọi `@Retention(RUNTIME)` đều đọc được bằng reflection”.

## 3. Class file lưu annotation ở đâu?

File `.class` không lưu nguyên bản toàn bộ source code. Compiler tạo cấu trúc JVM class file chứa constant pool, class/field/method descriptors và các **attributes**.

Đối với *declaration annotations* thông thường, các tên attribute quan trọng gồm:

- **`RuntimeVisibleAnnotations`**: annotation trên class/field/method thuộc nhóm runtime-visible.
- **`RuntimeInvisibleAnnotations`**: annotation còn lại trong class file nhưng không được reflection Java thông thường expose như runtime annotation; ví dụ một annotation có retention CLASS.
- **`RuntimeVisibleParameterAnnotations`** và **`RuntimeInvisibleParameterAnnotations`**: metadata annotation trên formal parameters của method/constructor.
- **`RuntimeVisibleTypeAnnotations`** và **`RuntimeInvisibleTypeAnnotations`**: annotation trên **type-use contexts** (`TYPE_USE`), ví dụ generic type argument hoặc thành phần kiểu phức tạp.
- **`AnnotationDefault`**: giá trị mặc định được khai báo bởi một **annotation element method**, nằm trong class file của **annotation type**.

Tên “RuntimeInvisible” có nghĩa annotation **không được JVM reflection cung cấp như một annotation runtime bình thường**; nó **không** có nghĩa bytecode đã xóa annotation hoặc công cụ như `javap` không thể xem.

Một class file có thể chứa nhiều nhóm attribute ở **các vị trí khác nhau**. Ví dụ annotation ở **field** được ghi trong thông tin của field; annotation ở **method** được ghi trong phần method; type annotation của generic argument có thể nằm trong `RuntimeVisibleTypeAnnotations` thuộc vùng metadata của field/method, không phải `RuntimeVisibleAnnotations` trên class.

Ngoài các nhóm trên còn có annotation-specific metadata tại những cấu trúc đặc thù như record components; cần đọc vị trí thực tế trong `javap -v`. Việc thấy tên annotation trong **constant pool** chưa đủ để kết luận nó được gắn lên class đang xem: constant pool cũng chứa tham chiếu kiểu, tên method, string và thông tin khác.

## 4. Ví dụ Java 17 chạy được: cùng một class, ba retention và một type annotation

Tạo file duy nhất **`AnnotationTraceDemo.java`**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.AnnotatedParameterizedType;
import java.util.List;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceOnly { String value(); }

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface BinaryOnly { String value(); }

@Target(ElementType.TYPE)
@interface DefaultBinary { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RuntimeReadable { String value(); }

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.METHOD})
@interface MemberLabel { String value() default "auto"; }

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeMark {}

@SourceOnly("compiler")
@BinaryOnly("classfile")
@DefaultBinary("implicit")
@RuntimeReadable("reflection")
final class Sample {
    @MemberLabel("identifier")
    private int id = 42;

    @MemberLabel
    public int id() { return id; }

    private List<@TypeMark String> names;
}

public class AnnotationTraceDemo {
    public static void main(String[] args) throws Exception {
        Class<Sample> type = Sample.class;
        System.out.println("SOURCE=" + type.isAnnotationPresent(SourceOnly.class));
        System.out.println("CLASS=" + type.isAnnotationPresent(BinaryOnly.class));
        System.out.println("DEFAULT=" + type.isAnnotationPresent(DefaultBinary.class));
        System.out.println("RUNTIME=" + type.getAnnotation(RuntimeReadable.class).value());
        System.out.println("FIELD=" +
                type.getDeclaredField("id").getAnnotation(MemberLabel.class).value());
        System.out.println("METHOD=" +
                type.getDeclaredMethod("id").getAnnotation(MemberLabel.class).value());
        var annotated = type.getDeclaredField("names").getAnnotatedType();
        var parameterized = (AnnotatedParameterizedType) annotated;
        var arg = parameterized.getAnnotatedActualTypeArguments()[0];
        System.out.println("TYPE_USE=" + arg.isAnnotationPresent(TypeMark.class));
    }
}
~~~

File này dùng các annotation types và lớp `Sample` ở mức package-private, chỉ có `AnnotationTraceDemo` là public. Vì thế lưu chính xác tên file `AnnotationTraceDemo.java` để `javac` biên dịch đúng.

Mở terminal tại thư mục chứa file và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 -d out AnnotationTraceDemo.java
java -cp out AnnotationTraceDemo
~~~

**Stdout chính xác** (đã biên dịch bằng `javac --release 17` và chạy thử):

~~~text
SOURCE=false
CLASS=false
DEFAULT=false
RUNTIME=reflection
FIELD=identifier
METHOD=auto
TYPE_USE=true
~~~

### Đọc từng dòng stdout

1. **`SOURCE=false`**: `@SourceOnly("compiler")` có trong source của `Sample` nhưng bị loại khỏi class file; reflection không thấy.
2. **`CLASS=false`**: `@BinaryOnly("classfile")` được giữ trong class file với retention CLASS, nhưng không đọc được qua `Class.isAnnotationPresent`.
3. **`DEFAULT=false`**: `@DefaultBinary` không khai báo `@Retention`, nên mặc định CLASS và cũng không được reflection trả về.
4. **`RUNTIME=reflection`**: `@RuntimeReadable` có retention RUNTIME và được gắn trực tiếp lên `Sample`, nên `Class.getAnnotation(RuntimeReadable.class)` đọc được giá trị `reflection`.
5. **`FIELD=identifier`**: `MemberLabel` được khai báo trên field `id`; lấy bằng `getDeclaredField("id")` rồi đọc annotation của `Field` ấy.
6. **`METHOD=auto`**: method `id()` gắn `@MemberLabel` nhưng không ghi `value`. Reflection trả giá trị default `auto` được định nghĩa trong annotation type.
7. **`TYPE_USE=true`**: `@TypeMark` nằm trên **`String` trong `List<String>`**, nên phải đi qua `Field.getAnnotatedType()`, ép sang `AnnotatedParameterizedType` và chọn actual type argument. Nó không phải declaration annotation trên field `names`.

Các giá trị in ra từ chính chương trình không chứng minh vị trí bytecode, nên ta cần **`javap -v`** ở bước tiếp theo.

## 5. Kiểm tra class file bằng javap -v

Sau khi biên dịch ví dụ trên, chạy:

~~~bash
javap -v -p -classpath out Sample
~~~

Ở đây:

- **`-classpath out`** chỉ tới thư mục có các `.class` do lệnh `javac -d out` tạo.
- **`-v`** (verbose) hiển thị thông tin chi tiết của class file, bao gồm constant pool và attributes.
- **`-p`** cho phép hiển thị thêm các thành viên private, để ta kiểm tra field `id` và field `names`.

Output đầy đủ của `javap -v` khá dài và có các chỉ số constant-pool như `#12`, `#35` phụ thuộc bản biên dịch. Ta chỉ cần tìm **tên attribute** và vị trí xuất hiện, không ghi nhớ các chỉ số đó.

### 5.1. Metadata trên chính class Sample

Khi xem phần cuối bản dump cho `Sample`, bạn sẽ tìm thấy các thông tin về annotation của **class** tương ứng:

~~~text
RuntimeVisibleAnnotations:
    RuntimeReadable(
      value="reflection"
    )
RuntimeInvisibleAnnotations:
    BinaryOnly(
      value="classfile"
    )
    DefaultBinary(
      value="implicit"
    )
~~~

Đây là **bản lược bỏ chỉ số constant pool và một số dòng phụ** để dễ đọc; không phải yêu cầu toàn bộ output `javap` phải giống hệt cách căn lề trong khối này.

- `RuntimeReadable` xuất hiện trong `RuntimeVisibleAnnotations` vì retention là RUNTIME.
- `BinaryOnly` và `DefaultBinary` xuất hiện trong `RuntimeInvisibleAnnotations` vì retention là CLASS.
- **`SourceOnly` không xuất hiện như một annotation được lưu trên `Sample`** vì retention là SOURCE. Nếu grep tên trong **những class file khác**, vẫn có thể thấy tên `SourceOnly` do class định nghĩa annotation hoặc do code tham chiếu tới kiểu đó; điều này không bác bỏ kết luận về metadata trên `Sample`.

### 5.2. Metadata trên field/method

Ở phần riêng của field `id` và method `id()`, tìm `RuntimeVisibleAnnotations` có `MemberLabel`. Đừng nhầm nhóm đó với annotation ở cấp class.

Trên field `names`, compiler ghi type-use annotation cho generic argument vào vùng metadata tương ứng, trong ví dụ này có **`RuntimeVisibleTypeAnnotations`** với `TypeMark`. Attribute này giải thích vì sao code phải đọc `getAnnotatedType()` và actual type argument thay vì `getAnnotation(TypeMark.class)` trực tiếp trên `Field`.

### 5.3. Giá trị default nằm trên annotation type, không phải luôn ở nơi sử dụng

Xem định nghĩa của `MemberLabel`:

~~~bash
javap -v -p -classpath out MemberLabel
~~~

Tìm phần method `value()` và attribute **`AnnotationDefault`** với chuỗi `auto`. Khi sử dụng `@MemberLabel` không có đối số trên method `Sample.id()`, metadata tại chỗ sử dụng không cần lưu lặp lại giá trị default. Khi đọc bằng reflection, runtime diễn giải default từ định nghĩa annotation type và trả `auto`.

Điều này cũng giải thích một tình huống nâng cấp thư viện: nếu giá trị default trong annotation type thay đổi ở phiên bản mới, một class dùng annotation mà **không ghi giá trị tường minh** có thể nhận default mới khi chạy với annotation type phiên bản mới. Vì vậy default của annotation type là một phần của hợp đồng API, cần kiểm thử tương thích.

## 6. Vì sao javap thấy mà reflection không thấy?

Có ít nhất **bốn nhóm nguyên nhân** cần phân biệt.

### 6.1. Retention không phải RUNTIME

Đây là lý do trực tiếp của `CLASS=false` và `DEFAULT=false`: bytecode vẫn có metadata nhưng Java reflection chỉ cung cấp các runtime annotations phù hợp. Dùng `javap -v` hoặc thư viện phân tích bytecode khi cần kiểm tra CLASS-retained annotations.

Nếu cần framework tìm annotation ở runtime, **thiết kế annotation type với `@Retention(RUNTIME)`**. Đổi retention tại source không tự sửa các class đã biên dịch từ trước; cần biên dịch/đóng gói lại những class dùng annotation để metadata được tạo theo chính sách mới.

### 6.2. Truy vấn sai annotated element

Nếu annotation được gắn trên `method`, `field`, `parameter`, `record component`, `package` hoặc `module`, việc gọi `SomeClass.class.getAnnotation(A.class)` không thay thế được API của đúng phần tử.

| Nơi khai báo | Cách lấy đối tượng cần tra cứu |
| --- | --- |
| Class | `SomeClass.class` |
| Method | `SomeClass.class.getDeclaredMethod("name", parameterTypes...)` |
| Field | `SomeClass.class.getDeclaredField("fieldName")` |
| Formal parameter | `Method.getParameters()[index]` và `Parameter.getAnnotation(...)` |
| Record component | `SomeRecord.class.getRecordComponents()[index]` |
| Package | `SomeClass.class.getPackage()` |
| Module | `SomeClass.class.getModule()` |
| Type-use, ví dụ generic argument | `Field.getAnnotatedType()`, hoặc `Method.getAnnotatedReturnType()` và các `AnnotatedType` tương ứng |

Với package/module, phải compile/đóng gói đúng `package-info.class` hoặc `module-info.class` và chạy trong ngữ cảnh tương ứng. Một annotation trên record component có thể có quy tắc propagation sang thành viên được sinh khi `@Target` tương thích; không tự giả định mọi field/method đều nhận annotation.

### 6.3. Nhầm declaration annotations với TYPE_USE annotations

`RuntimeVisibleAnnotations` và `RuntimeVisibleTypeAnnotations` mô tả **hai cấu trúc khác nhau**. Ví dụ:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface MarkType {}

class Container {
    java.util.List<@MarkType String> values;
}
~~~

Đây là **đoạn khai báo minh họa**, không phải file runnable độc lập. Muốn đọc `@MarkType` trên type argument `String`, lấy `Field.getAnnotatedType()` rồi duyệt `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`. Chỉ gọi `Field.getAnnotation(MarkType.class)` sẽ không cho kết quả về type annotation đó.

Một annotation có nhiều target, chẳng hạn `FIELD` và `TYPE_USE`, có thể được biểu diễn ở các nơi khác nhau tùy cú pháp/vị trí áp dụng. Vì vậy phải xác định vị trí từ source trước khi suy luận class file chứa attribute nào.

### 6.4. Bytecode hoặc runtime class khác với source bạn đang nhìn

Những vấn đề thường gặp:

- **Class cũ trong output/cache**: source đã đổi, nhưng `.class` được load vẫn là bản trước. Cần compile lại và xác minh đúng output folder/JAR.
- **Classpath có nhiều phiên bản cùng tên**: class loader nạp một class khác với class vừa chỉnh. Kiểm tra đường dẫn class thực tế, ví dụ `SomeClass.class.getProtectionDomain().getCodeSource()` nếu có và phù hợp.
- **Class loader khác nhau**: hai class cùng tên hoàn chỉnh do hai class loaders định nghĩa là hai kiểu khác nhau. `getAnnotation(A.class)` so khớp theo đối tượng kiểu annotation, không chỉ theo chuỗi tên.
- **Annotation type hoặc element đã thay đổi**: phiên bản runtime không tương thích có thể khiến giá trị annotation không đọc được hoặc phát sinh lỗi như `AnnotationTypeMismatchException`, `IncompleteAnnotationException`, `TypeNotPresentException` hoặc `EnumConstantNotPresentException` khi truy cập các element liên quan.

Vì vậy, trước khi kết luận “compiler đã xóa annotation”, hãy xem **đúng binary** mà ứng dụng đang chạy, không chỉ một class file khác có cùng tên.

## 7. Compilation trace: annotation processor khác reflection ở thời điểm đọc

Một annotation processor dùng `javax.annotation.processing` và mô hình `javax.lang.model` đọc source/element model **trong quá trình biên dịch**. Nó có thể xử lý một annotation có retention SOURCE vì annotation chưa bị loại khỏi nguồn dữ liệu compile time.

Ví dụ việc một processor đọc `@SourceOnly("compiler")` là **khả năng có thể triển khai**, không phải hành vi tự động trong chương trình `AnnotationTraceDemo`: chương trình ví dụ không đăng ký processor nào.

Luồng thời gian:

~~~text
Source code, @SourceOnly("compiler")
        |
        +--> javac + annotation processor (nếu được cấu hình)
        |        đọc model của source
        |
        +--> javac tạo Sample.class
                 không giữ SourceOnly trên class
                 giữ BinaryOnly/DefaultBinary ở invisible annotations
                 giữ RuntimeReadable ở visible annotations
                        |
                        +--> runtime reflection thấy RuntimeReadable
                             nhưng không thấy SourceOnly/BinaryOnly
~~~

Điểm cần nhớ: **annotation processing không phải Java runtime reflection**. Annotation processor có thể dùng các API của trình biên dịch, trong khi reflection đọc metadata mà runtime class model cung cấp. Đối chiếu hai thời điểm giúp giải thích tại sao một tool build đã xử lý annotation thành công nhưng ứng dụng chạy vẫn không tìm thấy nó.

### @Target cũng không thay thế @Retention

`@Target` kiểm tra tính hợp lệ của **vị trí**: `TYPE`, `METHOD`, `FIELD`, `TYPE_USE`, v.v. `@Retention` quyết định vòng đời metadata. Một annotation `@Target(METHOD)` + `@Retention(RUNTIME)` vẫn không hiện ra khi truy vấn `Class.getAnnotation(...)`, vì nó nằm trên method chứ không nằm trên class.

Ngược lại, `@Target(TYPE)` + `@Retention(CLASS)` có thể xuất hiện trong class file nhưng không qua runtime reflection. Phải giải đúng **cả hai chiều**.

## 8. Các ranh giới cần nhớ về class file và reflection

### 8.1. Không phải tất cả thông tin trong source đều có reflection API trực tiếp

Local-variable **declaration annotation** không được giữ trong class file theo quy tắc JLS. Với type-use annotation ở local variable type, metadata có thể được giữ trong bytecode (ví dụ trong `Code` attribute) tùy retention và target, nhưng Java reflection chuẩn **không có API tổng quát để liệt kê annotation trên tất cả biến cục bộ trong bytecode của một method**.

Muốn khảo sát dữ liệu này, cần phân tích class file chuyên sâu (hoặc dùng bytecode tooling). `Method.getAnnotations()` không phải cách tìm annotation nằm trên biến cục bộ bên trong body method.

### 8.2. @Inherited là một quy tắc tra cứu riêng, không phải phép copy bytecode

Nếu annotation có `@Inherited`, `@Target(TYPE)` và `@Retention(RUNTIME)`, `Child.class.getAnnotation(A.class)` có thể tìm lên superclass khi `Child` không có annotation trực tiếp. Điều đó **không có nghĩa** class file của `Child` tự có thêm attribute annotation tương ứng.

Hơn nữa, `@Inherited` không làm annotation trên method override tự được kế thừa, và không tự chuyển annotation từ interface sang implementing class. Khi đối chiếu reflection với `javap -v Child`, phải biết rằng reflection class-level có thể áp dụng quy tắc tra cứu ở runtime mà không cần bytecode của child lưu annotation mới.

### 8.3. Repeatable annotations có thể được lưu dưới dạng container

Với `@Repeatable`, nhiều base annotations tại cùng vị trí thường được biểu diễn bằng **container annotation**. `javap -v` có thể cho thấy container mang mảng các giá trị, trong khi `getAnnotationsByType(Base.class)` trả về nhiều base annotation đã được mở container.

Vì vậy, thấy một container trong class file nhưng reflection trả nhiều base annotations **không phải mâu thuẫn**. Muốn so sánh đúng, hiểu cả API `getDeclaredAnnotationsByType` và `getAnnotationsByType`, cũng như retention/target của container. Container phải thỏa các ràng buộc JLS đối với repeatable annotation.

### 8.4. Giá trị annotation phải là compile-time-compatible

Một annotation declaration không cho dùng mọi kiểu giá trị runtime như các lời gọi method bình thường. Primitive/`String` element cần biểu thức hằng hợp lệ; `Class` element dùng class literal; enum element dùng enum constant; nested annotation/array có cú pháp giới hạn. Nếu source dùng sai, **không có class file thành công để đối chiếu**; trước hết giải quyết lỗi `javac`.

Phần này cần phân biệt với **mất metadata do retention**. Lỗi compile-time không thuộc cùng nhóm với “source compile thành công nhưng reflection không đọc được annotation”.

## 9. Quy trình debug có thể lặp lại

Khi được giao kiểm tra vì sao annotation không xuất hiện ở runtime, hãy đi theo thứ tự sau:

1. **Xác định annotated element** trong source: class, method, field, parameter, record component, package, module hay type use. Ghi chính xác tên và signature.
2. **Đọc khai báo annotation type**: xác nhận `@Target`, `@Retention` (hoặc mặc định CLASS), khả năng `@Repeatable`/container, và các element có default.
3. **Biên dịch lại có kiểm soát** bằng JDK/`--release` phù hợp, làm rõ vị trí output. Kiểm tra lệnh thành công, không chỉ dựa trên dấu báo của IDE.
4. **Dùng `javap -v -p` đúng class file** và tìm attribute tương ứng: visible/invisible declaration, parameter, type annotations hoặc default. Phân biệt attribute thực với chỉ xuất hiện tên trong constant pool.
5. **Chạy reflection trên chính ứng dụng/binary**: lấy đúng `Class`/`Method`/`Field`/`AnnotatedType`, gọi `getAnnotation` hoặc `getAnnotationsByType` theo nhu cầu.
6. **So sánh với kỳ vọng retention**: SOURCE không giữ; CLASS có thể hiện trong binary nhưng không qua reflection; RUNTIME có thể đọc nếu đúng phần tử và không vướng quy tắc đặc biệt.
7. **Nếu kết quả vẫn lệch**, kiểm tra class loader, classpath/module path, phiên bản annotation type, package/class file cũ và các quy tắc `@Inherited` hoặc repeatable/container.

Bảng chẩn đoán:

| Hiện tượng | Giải thích thường gặp | Cách xác minh |
| --- | --- | --- |
| Annotation có trong source, không có trên class file đích | Retention SOURCE hoặc vị trí đặc biệt không được lưu | Đọc `@Retention`, dùng `javap -v` đúng binary |
| Có trong `RuntimeInvisibleAnnotations` nhưng `getAnnotation` trả `null` | Retention CLASS | Cần RUNTIME nếu muốn reflection |
| Có `RuntimeVisibleAnnotations` trên method nhưng `Class.getAnnotation` trả `null` | Truy vấn sai đối tượng | `getDeclaredMethod(...)` rồi đọc `Method` |
| Có `RuntimeVisibleTypeAnnotations` trên generic argument | Đang đọc declaration thay vì type use | Duyệt `AnnotatedType`/`AnnotatedParameterizedType` |
| Reflection thấy annotation trên subclass nhưng `javap` subclass không có | `@Inherited` class-level lookup | So sánh superclass binary và `getDeclaredAnnotation` |
| Reflection trả nhiều base annotations, `javap` thấy một container | Repeatable annotation representation | `getAnnotationsByType` và khai báo container |
| Reflection có metadata khác bản nguồn vừa sửa | Binary/classloader cũ hoặc khác phiên bản | Kiểm tra origin binary và build/redeploy |

## 10. Sai lầm phổ biến khi giải thích dấu vết

**Sai lầm 1 — Thấy tên annotation ở constant pool rồi kết luận nó được gắn vào class.** Constant pool chứa cả tên kiểu được dùng ở nơi khác. Chỉ coi annotation là được gắn vào một phần tử khi attribute thực sự mô tả nó tại đúng vị trí.

**Sai lầm 2 — Nghĩ “RuntimeInvisible” nghĩa là đã bị xóa.** Nó còn trong class file; điều bị giới hạn là khả năng phản chiếu như runtime annotation.

**Sai lầm 3 — Thấy `@Retention(RUNTIME)` rồi quên `@Target` và annotated element.** Retention không làm metadata tự lan tới class, package hoặc method khác. Phải đọc nơi gắn thật.

**Sai lầm 4 — Dùng `getDeclaredAnnotations()` và `getAnnotations()` như hai API hoàn toàn đồng nhất.** Với class annotations và `@Inherited`, kết quả có thể khác. Repeatable annotations lại có cách đọc container riêng.

**Sai lầm 5 — Thay default rồi tin mọi class file lưu giá trị cũ.** Nếu nơi sử dụng không ghi element tường minh, giá trị default có thể đến từ phiên bản annotation type đang được nạp khi chạy. Xác minh cả class file đích và class file định nghĩa annotation.

**Sai lầm 6 — Coi file `.java` của workspace là bằng chứng JVM đang chạy đúng bản đó.** Một bản sao trên classpath, JAR dependency hoặc class loader khác có thể giải thích phần lớn các sai khác.

**Sai lầm 7 — Dùng kết quả `javap` đầy đủ của một bản JDK làm hợp đồng về thứ tự mọi dòng.** Số constant-pool, chỉ số, cấu trúc trình bày có thể đổi giữa các compiler/JDK. Tập trung vào attribute và giá trị thực tế.

## 11. Bài tập tự kiểm tra

Dựa trên chương trình `AnnotationTraceDemo`:

**1. Vì sao `Sample.class.isAnnotationPresent(SourceOnly.class)` trả `false`?** Vì `@SourceOnly` bị loại khỏi class file của `Sample` theo retention SOURCE. Annotation type `SourceOnly` vẫn tồn tại như một kiểu đã được biên dịch vì code tham chiếu tới nó, nhưng **việc sử dụng annotation trên Sample** không được lưu.

**2. Vì sao `@BinaryOnly` có thể nhìn thấy qua `javap -v Sample` mà reflection vẫn không thấy?** Metadata của nó được giữ ở `RuntimeInvisibleAnnotations` vì retention CLASS.

**3. Vì sao `DefaultBinary` lại không đọc được runtime dù không khai báo `@Retention`?** Vì retention mặc định của annotation type là CLASS.

**4. `MemberLabel.value()` mặc định là `auto`. Giá trị này nằm ở đâu?** Default được mã hóa trong metadata của **annotation type `MemberLabel`** (`AnnotationDefault`). Khi `Sample.id()` chỉ ghi `@MemberLabel`, reflection diễn giải default từ annotation type.

**5. Vì sao phải ép `AnnotatedParameterizedType` khi đọc `@TypeMark`?** Vì annotation được gắn vào **generic type argument** `String` trong `List<String>`, không phải declaration annotation trên field `names`.

**6. Nếu `Sample` có `@RuntimeReadable` nhưng bạn truy vấn `Sample.class.getDeclaredMethod("id").getAnnotation(RuntimeReadable.class)` thì sao?** Trả `null` vì đó là annotation của class, không của method.

**7. Nếu một annotation RUNTIME đặt trên local-variable declaration, có thể liệt kê nó bằng `Method.getAnnotations()` không?** Không. Declaration annotation đó không được giữ như annotation của method; muốn nghiên cứu type annotations bên trong code cần công cụ phù hợp.

**8. Nếu `@Inherited` cho phép `Child.class.getAnnotation(X.class)` tìm được annotation của parent, có chắc `javap -v Child` hiển thị X trên class con không?** Không. Reflection có thể tìm lên superclass mà không cần compiler sao chép X vào binary của child.

## 12. Tài liệu chính thức

- **Java Language Specification `9.6.4.2 — @Retention**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.6.4.2
- **JLS `9.7.4 — Where Annotations May Appear**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7.4
- **JVM Specification `4.7 — Attributes**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7
- **Java SE 21 API — RetentionPolicy**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/annotation/RetentionPolicy.html
- **Java SE 21 API — AnnotatedElement**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
- **javap command reference (JDK 21)**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html

Đối chiếu annotation đúng nghĩa là xác định **mã nguồn khai báo gì**, **compiler đã mã hóa gì và ở đâu trong class file**, rồi **runtime reflection đang nhìn vào phần tử nào và áp dụng quy tắc tra cứu nào**. Chỉ khi ba mắt xích đó khớp nhau mới có thể giải thích chắc chắn vì sao một annotation được tìm thấy, bị ẩn khỏi reflection hoặc hoàn toàn không được giữ sau biên dịch.