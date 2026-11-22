# Dùng `javap -v` để kiểm tra annotation trong class file

## 1. Tại sao cần xem annotation trong file `.class`?

Annotation trong mã nguồn Java có thể được xử lý khi biên dịch, được lưu vào bytecode hoặc tiếp tục hiện diện để chương trình đọc qua reflection. Khi ứng dụng hoặc framework không tìm được một annotation như mong đợi, câu hỏi đầu tiên thường là: **trình biên dịch có lưu metadata đó vào đúng class file và đúng vị trí không?**

Công cụ `javap` đi kèm JDK có thể giải mã cấu trúc của file `.class`. Tùy chọn **`-v`** (tương đương `-verbose`) hiển thị dữ liệu chi tiết, bao gồm *attributes* chứa annotation, constant pool, chữ ký, phương thức và một số chỉ dẫn bytecode. Với annotation, các dấu vết quan trọng gồm:

- `RuntimeVisibleAnnotations` và `RuntimeInvisibleAnnotations`: annotation trên declaration như class, field, method.
- `RuntimeVisibleParameterAnnotations` và `RuntimeInvisibleParameterAnnotations`: annotation trên **declaration của tham số** method/constructor.
- `RuntimeVisibleTypeAnnotations` và `RuntimeInvisibleTypeAnnotations`: annotation tại **vị trí sử dụng kiểu** như return type, parameter type, cast, generic argument, kiểu của field.
- `AnnotationDefault`: giá trị mặc định của một phần tử khai báo bên trong **annotation interface**.

`javap` không phải annotation processor và không thực thi ứng dụng: nó **đọc class file đã được biên dịch**. Vì thế, đây là cách hữu ích để kiểm tra metadata một cách độc lập với logic reflection/framework lúc chạy.

### Những điều `javap -v` trả lời được

1. Annotation có thật sự được compiler lưu vào class file không?
2. Nó nằm trên **class**, **field**, **method**, **parameter**, hay **type-use**?
3. Annotation có retention `RUNTIME` hay `CLASS`, nhìn qua nhóm attribute được tạo?
4. Với annotation lặp lại, compiler dùng annotation container nào?
5. Một annotation trên cast hoặc kiểu trả về có *target* bytecode tương ứng nào?
6. Một phần tử annotation có giá trị mặc định được lưu ở đâu?

**Giới hạn:** `javap` giải mã metadata của **từng file class cụ thể**. Nó không thực hiện quy tắc tìm annotation trên superclass của `Class.getAnnotations()`, không chạy framework, và không chứng minh annotation sẽ gây ra một hành vi runtime.

## 2. Ba chính sách `@Retention` và dấu vết trong class file

Java định nghĩa ba retention policy:

| Retention | Ý nghĩa chính | Kỳ vọng khi xem class file |
|---|---|---|
| `RetentionPolicy.SOURCE` | Annotation chỉ phục vụ giai đoạn mã nguồn/biên dịch; compiler không giữ nó trong file class | Không có annotation tương ứng trong attributes của file `.class` được sinh |
| `RetentionPolicy.CLASS` | Annotation được ghi vào class file nhưng không bắt buộc hiển thị qua reflection lúc chạy | Thường xuất hiện trong `RuntimeInvisibleAnnotations` hoặc `RuntimeInvisibleTypeAnnotations`, tùy vị trí |
| `RetentionPolicy.RUNTIME` | Annotation được ghi vào class file và có thể truy cập qua API reflection hỗ trợ vị trí đó | Thường xuất hiện trong `RuntimeVisibleAnnotations` hoặc nhóm `RuntimeVisible...` thích hợp |

Nếu **không khai báo `@Retention`**, mặc định là **`CLASS`**; đừng suy luận mặc định là `RUNTIME`.

Các từ “Visible” và “Invisible” là tên thuộc tính theo **JVM class-file format**, không phải các mức truy cập `public`/`private`:

- **`RuntimeVisible...`** chỉ nhóm metadata được định nghĩa là hiển thị tại runtime qua cơ chế hỗ trợ phù hợp.
- **`RuntimeInvisible...`** vẫn là dữ liệu hiện diện trong class file; `javap` hoặc công cụ phân tích bytecode đọc được, nhưng Java reflection tiêu chuẩn không cung cấp trực tiếp annotation này.
- Annotation `SOURCE` đã bị loại khỏi class file; chạy `javap` sau biên dịch không thể dựng lại toàn bộ annotation từng có trong source.

**Một phân biệt quan trọng:** dù một annotation trên *cast expression* có `RUNTIME` và được liệt kê dưới `RuntimeVisibleTypeAnnotations`, reflection Java tiêu chuẩn không có API thông thường để liệt kê mọi cast trong thân method. Vì thế **“RuntimeVisible” không có nghĩa mọi vị trí đều đọc được bằng `Class.getAnnotation()`**.

## 3. Ví dụ hoàn chỉnh Java 17+: biên dịch để xem bằng `javap`

Tạo một thư mục thực hành và lưu đoạn sau vào đúng file **`Main.java`**. Chỉ có một top-level class `public` tên `Main`; các annotation types và `Demo` được khai báo package-private trong cùng file để dễ thử nghiệm.

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface RuntimeTag {
    String value();
}

@Retention(RetentionPolicy.CLASS)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface ClassTag {
    String value();
}

@Retention(RetentionPolicy.SOURCE)
@Target({
    ElementType.TYPE,
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.PARAMETER
})
@interface SourceTag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface TypeTag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Notes.class)
@interface NoteTag {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Notes {
    NoteTag[] value();
}

@RuntimeTag("class")
@ClassTag("class")
@SourceTag("class")
@NoteTag("first")
@NoteTag("second")
class Demo {

    @RuntimeTag("field")
    @ClassTag("field")
    private String field;

    @RuntimeTag("method")
    public @TypeTag("return") String greet(
            @RuntimeTag("parameter")
            @TypeTag("parameter-type") String input) {

        Object raw = input;
        String result = (@TypeTag("cast") String) raw;
        return result;
    }
}

public class Main {
    public static void main(String[] args) throws Exception {
        Demo demo = new Demo();

        System.out.println(demo.greet("Java"));
        System.out.println("runtime="
                + Demo.class.isAnnotationPresent(RuntimeTag.class));
        System.out.println("class="
                + Demo.class.isAnnotationPresent(ClassTag.class));
        System.out.println("source="
                + Demo.class.isAnnotationPresent(SourceTag.class));
        System.out.println("type="
                + Demo.class.getMethod("greet", String.class)
                        .getAnnotatedReturnType()
                        .isAnnotationPresent(TypeTag.class));
        System.out.println("repeat="
                + Demo.class.getAnnotationsByType(NoteTag.class).length);
    }
}
~~~

Các annotation được dùng có chủ ý khác nhau:

- `RuntimeTag`: retention `RUNTIME` trên class, private field, method và parameter declaration.
- `ClassTag`: retention `CLASS` trên class và field.
- `SourceTag`: retention `SOURCE` trên class.
- `TypeTag`: retention `RUNTIME` nhưng `@Target(TYPE_USE)`, áp dụng vào return type, parameter type và cast.
- `NoteTag`: annotation `@Repeatable`, dùng hai lần trên `Demo`; `Notes` là container.

### 3.1. Lệnh biên dịch và chạy

Tại thư mục chứa `Main.java`, dùng JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 -parameters Main.java
java Main
~~~

Kết quả từ `java Main`:

~~~text
Java
runtime=true
class=false
source=false
type=true
repeat=2
~~~

Điều này xác nhận:

1. Method `greet` vẫn chạy bình thường và trả `"Java"`.
2. `RuntimeTag` có thể được reflection đọc trên `Demo`.
3. `ClassTag` tuy được lưu trong file class nhưng `Demo.class.isAnnotationPresent(ClassTag.class)` trả `false`.
4. `SourceTag` không xuất hiện tại runtime.
5. `TypeTag` trên **kiểu trả về** được `getAnnotatedReturnType()` đọc; phương thức `getAnnotation` gọi trực tiếp trên `Method` sẽ không phải cách thay thế để đọc mọi annotation TYPE_USE.
6. Hai annotation `NoteTag` được lấy bằng `getAnnotationsByType`, dù class file có thể chứa chúng qua container.

### 3.2. File được tạo sau khi biên dịch

Biên dịch nguồn trên tạo `Main.class`, `Demo.class` và các file class cho annotation types `RuntimeTag`, `ClassTag`, `SourceTag`, `TypeTag`, `NoteTag`, `Notes`.

**Muốn kiểm tra annotation áp dụng trên `Demo` thì xem `Demo.class`, không chỉ xem `Main.class`.** Annotation không tự chuyển thành metadata của `Main` chỉ vì hai class cùng nằm trong `Main.java`.

Lệnh quan trọng:

~~~bash
javap -v -p Demo
~~~

Hoặc chỉ rõ vị trí classpath:

~~~bash
javap -classpath . -v -p Demo
~~~

- **`-v`** in chi tiết attributes, constant pool, bytecode và metadata.
- **`-p`** (tương đương `-private`) cho xem các member private trong kết quả; ví dụ `field` được khai báo `private`.
- `Demo` là tên binary class trong package hiện tại, còn `javap -v -p Main` giải mã một class khác.
- `-parameters` trong lệnh `javac` lưu metadata tên tham số (`MethodParameters`), giúp xác minh tên `input`; **không phải điều kiện để parameter annotation được lưu**.

Ví dụ trên dùng `--release 17` để yêu cầu trình biên dịch biên dịch theo API/ngữ nghĩa Java 17 dù môi trường có JDK mới hơn. Nếu bạn sử dụng đúng JDK 17, vẫn có thể dùng `javac -encoding UTF-8 -parameters Main.java`.

## 4. Đọc `RuntimeVisibleAnnotations` và `RuntimeInvisibleAnnotations`

Ở gần cuối bản giải mã **`Demo.class`**, bạn sẽ thấy phần annotation áp dụng trên **class**. Một đoạn đầu ra **rút gọn để giải thích** (không phải bản chép đủ từ `javap`):

~~~text
RuntimeVisibleAnnotations:
  ... RuntimeTag(
        value="class"
      )
  ... Notes(
        value=[@NoteTag(value="first"), @NoteTag(value="second")]
      )
RuntimeInvisibleAnnotations:
  ... ClassTag(
        value="class"
      )
~~~

Trong đầu ra thực tế, tên có thể được in theo ký pháp khác, kèm **constant-pool indices** dạng `#14`, vị trí, kiểu mã hóa như `s` hoặc các dòng thụt đầu khác. **Đừng dựa vào số `#...` hay thứ tự tuyệt đối:** đó là chỉ số do compiler tạo ra và có thể thay đổi khi sửa source.

Cách hiểu:

- **`RuntimeVisibleAnnotations`** trên `Demo` chứa `RuntimeTag("class")` và **`Notes`** container của hai `NoteTag`.
- **`RuntimeInvisibleAnnotations`** trên `Demo` chứa `ClassTag("class")`.
- Không thấy `SourceTag("class")` vì retention `SOURCE` yêu cầu compiler loại nó khỏi class file.

### 4.1. Không nhầm container với từng annotation lặp lại

Hai dòng trong source:

~~~java
@NoteTag("first")
@NoteTag("second")
class Demo {}
~~~

được compiler biểu diễn qua annotation container `Notes` theo quy tắc `@Repeatable`. Khi xem `javap -v`, bạn có thể tìm thấy dạng `Notes(value=[@NoteTag(...), @NoteTag(...)])`, **không nhất thiết là hai annotation `NoteTag` ngang hàng ở thuộc tính trên class**.

Điều này giải thích vì sao:

~~~java
Demo.class.getAnnotationsByType(NoteTag.class).length // 2
~~~

trong khi API dạng số ít `getAnnotation(NoteTag.class)` không tự động bóc container để trả nhiều `NoteTag`. Nếu cần các annotation lặp lại, chọn `getAnnotationsByType(...)`.

## 5. Phân biệt annotation trên class, field và method

Trong `javap -v -p Demo`, **ngữ cảnh thụt lề và vị trí attribute** quyết định annotation thuộc declaration nào.

Một class file có thể được hiển thị theo bố cục:

~~~text
class Demo
  ...

  private java.lang.String field;
    ...
    RuntimeVisibleAnnotations:
      ... RuntimeTag(value="field")
    RuntimeInvisibleAnnotations:
      ... ClassTag(value="field")

  public java.lang.String greet(java.lang.String);
    ...
    RuntimeVisibleAnnotations:
      ... RuntimeTag(value="method")

  ...
RuntimeVisibleAnnotations:
  ... RuntimeTag(value="class")
  ... Notes(...)
~~~

Đây là **sơ đồ minh họa**, có lược bỏ `descriptor`, `flags`, `Code`, `LineNumberTable`, constant-pool indices và chi tiết mã hóa. Các mục thật trong `javap` thường dài hơn nhiều.

**Không kết luận theo việc cùng tên thuộc tính:** `RuntimeVisibleAnnotations` có thể xuất hiện **nhiều lần** vì mỗi class, field, method có chỗ chứa attributes riêng. Muốn xác định annotation thuộc declaration nào, nhìn **member signature ngay phía trên** hoặc vị trí ở cuối phần thông tin class.

Annotation trên private field sẽ bị khó quan sát nếu xem dạng rút gọn; dùng `-p` để hiện đủ member. Lựa chọn `-p` không sửa class file và không biến private annotation thành public metadata.

## 6. Parameter declaration khác parameter type

Trong source, method của `Demo` có:

~~~java
public @TypeTag("return") String greet(
        @RuntimeTag("parameter")
        @TypeTag("parameter-type") String input) {
    // ...
}
~~~

Ở đây hai annotation trước `String input` có **đích áp dụng khác nhau**:

- `@RuntimeTag("parameter")` có `@Target(PARAMETER)`, nên là annotation trên **khai báo parameter**.
- `@TypeTag("parameter-type")` có `@Target(TYPE_USE)`, nên là annotation trên **kiểu String được dùng cho parameter**.

Khi giải mã, chúng thường nằm trong **hai nhóm attribute khác nhau**:

~~~text
RuntimeVisibleParameterAnnotations:
  parameter 0:
    ... RuntimeTag(value="parameter")

RuntimeVisibleTypeAnnotations:
  ... METHOD_FORMAL_PARAMETER, param_index=0
      TypeTag(value="parameter-type")
~~~

`parameter 0` là tham số đầu tiên theo thứ tự chỉ số bắt đầu từ 0. Phân biệt vị trí tham số trong `RuntimeVisibleParameterAnnotations` với mã đích `METHOD_FORMAL_PARAMETER` của **type annotation**.

Ví dụ `@TypeTag("return")` trên kiểu trả về nằm dưới:

~~~text
RuntimeVisibleTypeAnnotations:
  ... METHOD_RETURN
      TypeTag(value="return")
~~~

**Một `Annotation[]` lấy từ `Method.getParameterAnnotations()`** không tương đương hoàn toàn với **`AnnotatedType[]` từ `Method.getAnnotatedParameterTypes()`**. Hai API đọc hai loại metadata khác nhau.

### `MethodParameters` có phải annotation không?

Không. Dòng `MethodParameters:` (nếu có) mô tả **tên và flags của tham số**, ví dụ tên `input` do `javac -parameters` lưu lại. Nó không chứa annotation declaration/type-use.

Đừng thấy class file không có `MethodParameters` rồi kết luận parameter annotation bị mất. Đây là hai cấu trúc độc lập.

## 7. Dùng `RuntimeVisibleTypeAnnotations` để kiểm tra cast và kiểu trong thân method

Annotation với `@Target(TYPE_USE)` có thể xuất hiện trong các ngữ cảnh như:

- Kiểu trả về method: `METHOD_RETURN`.
- Kiểu tham số method: `METHOD_FORMAL_PARAMETER`.
- Kiểu của field: `FIELD`.
- Superclass hoặc superinterface: `CLASS_EXTENDS`.
- Cast expression: `CAST`.
- Biểu thức tạo object: `NEW`.
- Kiểu trong phép thử, generic argument, array dimension và những ngữ cảnh type-use khác có mã `target_type` tương ứng theo JVM Specification.

Với source:

~~~java
Object raw = input;
String result = (@TypeTag("cast") String) raw;
~~~

Bản giải mã thực tế có mục tương tự:

~~~text
Code:
  ...
  RuntimeVisibleTypeAnnotations:
    ... CAST, offset=..., type_index=0
        TypeTag(value="cast")
~~~

Đó là annotation trên **kiểu String của phép cast**, được lưu cùng metadata của `Code`. Con số `offset` biểu thị vị trí trong bytecode; `type_index` hoặc `type_path` mô tả loại/nhánh kiểu được annotate khi cần. Chúng **không phải chỉ số dòng source**.

Trong khi đó, annotation trên **kiểu trả về** và **kiểu tham số** thường được hiển thị ở thuộc tính `RuntimeVisibleTypeAnnotations` gắn với **method**.

**Phân biệt quan trọng:** cả nhóm annotation trên cast và trên kiểu trả về đều có thể mang tên `RuntimeVisibleTypeAnnotations`, nhưng chúng được gắn với **các cấu trúc bytecode khác nhau** và có `target_type` khác nhau. Đọc vị trí của attribute và mã target; không chỉ tìm tên annotation.

### 7.1. Reflection đọc được gì?

Ví dụ:

~~~java
Demo.class.getMethod("greet", String.class)
        .getAnnotatedReturnType()
        .getAnnotation(TypeTag.class);
~~~

trả được `@TypeTag("return")` vì đây là annotation trên return type, có API `AnnotatedType` tương ứng.

Nhưng Java reflection tiêu chuẩn **không có** một lời gọi như `getAllCastAnnotationsInMethod()` để liệt kê mọi cast trong bytecode. Muốn kiểm tra annotation `cast`, hãy dùng `javap -v` hoặc một bytecode library hỗ trợ đọc type-annotation attributes.

Cùng một annotation type, cùng retention `RUNTIME`, nhưng **bề mặt truy vấn khác nhau**. Đừng dùng kết quả reflection trên method declaration để phủ nhận metadata đã được lưu trong `Code`.

## 8. Kiểm tra annotation có `default`: `AnnotationDefault`

`AnnotationDefault` không phải attribute chứng minh một class đang *sử dụng* annotation. Nó là thuộc tính của **method khai báo một phần tử trong annotation interface**, chứa giá trị mặc định đã được khai báo.

Ví dụ nguồn độc lập:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Retry {
    int times() default 3;
    String mode() default "safe";
}
~~~

Nếu biên dịch `Retry.java` (hoặc file chứa khai báo hợp lệ) rồi chạy:

~~~bash
javap -v -p Retry
~~~

bạn sẽ thấy mỗi element có default tương ứng trong `AnnotationDefault`, chẳng hạn:

~~~text
public abstract int times();
  ...
  AnnotationDefault:
    default_value: I#...
      3
~~~

Số `#...` thay đổi theo constant pool. Element `mode()` cũng có attribute `AnnotationDefault` với giá trị `"safe"`.

Nếu nơi dùng annotation viết `@Retry` mà không truyền `times`, đó không có nghĩa compiler nhất thiết lưu lại `times=3` ở từng nơi sử dụng: **giá trị mặc định được tra từ annotation type**, không cần phải lặp giá trị mặc định ở từng annotated class.

## 9. Kiểm tra annotation lồng nhau và giá trị các phần tử

Khi giải mã `javap -v`, bạn có thể thấy các dạng biểu diễn như:

- `value="class"`: giá trị chuỗi.
- `value=3`: số nguyên.
- `SomeEnum.VALUE`: enum constant.
- `java.lang.String.class` hoặc constant pool type descriptor: class literal.
- `@Nested(...)`: annotation lồng nhau.
- `value=[..., ...]`: mảng giá trị, ví dụ container của repeatable annotations.

`javap` thường hiển thị thêm những phần như `#14(#15=s#34)` để mô tả constant-pool references và kiểu element-value. Đây là cấu trúc class file, không phải một cú pháp Java source cần copy nguyên vào `@Annotation(...)`.

Nếu giá trị hiển thị trong `javap` khác điều bạn dự đoán ở source, hãy kiểm tra:

1. Đã biên dịch **đúng source** chưa?
2. `javap` đang đọc **đúng output directory/JAR và đúng classpath** chưa?
3. Đó là giá trị được truyền trực tiếp ở nơi dùng hay **default** trong annotation type?
4. Annotation có dùng `@Repeatable` và container nên cấu trúc hiển thị khác source?
5. Constant-pool indices đã thay đổi do compiler build khác, nhưng giá trị logic vẫn giống nhau?

Đừng suy luận mọi chi tiết biểu diễn là API ổn định giữa các phiên bản compiler. **Tên attribute và ngữ nghĩa class-file format** mới là phần cần đối chiếu; các chỉ số, offset và cách trình bày có thể thay đổi.

## 10. Dùng `javap` đúng classpath, package, class file và JAR

Trong dự án thật, class file có thể nằm trong `target/classes`, `build/classes/java/main` hoặc một JAR. Khi đó, chạy `javap Demo` tại thư mục nguồn có thể báo không tìm được class hoặc đọc nhầm class cùng tên.

### Với class trong package

Nếu source có:

~~~java
package com.example.annotation;

class Demo {}
~~~

và đã được biên dịch ra thư mục `out`, dùng binary name đầy đủ:

~~~bash
javap -classpath out -v -p com.example.annotation.Demo
~~~

**Đừng nhập `Demo.java` để xem annotation trong class file.** `javap` làm việc với class file, còn `javac` xử lý source.

### Với class nằm trong JAR

Nếu `app.jar` chứa `com/example/annotation/Demo.class`:

~~~bash
javap -classpath app.jar -v -p com.example.annotation.Demo
~~~

### Với đường dẫn class file

Một số cách gọi `javap` chấp nhận truyền trực tiếp đường dẫn tới class file:

~~~bash
javap -v -p out/com/example/annotation/Demo.class
~~~

Tuy nhiên, dùng **`-classpath` cộng với binary class name** thường dễ kiểm soát hơn khi có package, class trùng tên hoặc nhiều output roots.

### Inner/nested class và ký tự `$`

Compiler đặt binary name dạng `Outer$Nested`. Với shell có cơ chế mở rộng `$`, hãy **quote** hoặc escape tên chứa `$`, ví dụ trong Bash:

~~~bash
javap -classpath out -v -p 'com.example.Outer$Nested'
~~~

Đừng dựa vào việc tên file nguồn giống tên class nested.

## 11. Quy trình chẩn đoán khi reflection không thấy annotation

Khi `clazz.getAnnotation(MyAnnotation.class)` trả về `null`, dùng quy trình ngắn dưới đây:

1. **Xác minh class thực tế.** Kiểm tra package, output folder và version JAR. Lệnh `javap -classpath <output> -v -p <binary-name>` phải chỉ đúng class.
2. **Tìm annotation type name** trong kết quả. Nếu chỉ thấy trong **constant pool** nhưng không có attribute annotation ở vị trí cần thiết, đừng vội kết luận annotation đã được áp dụng. Constant pool có thể chứa tham chiếu xuất hiện vì mục đích khác.
3. **Xác định retention.** Nếu `SOURCE`, không kỳ vọng thấy class-file annotation. Nếu `CLASS`, sẽ là nhóm `RuntimeInvisible...`; nếu `RUNTIME`, tìm nhóm `RuntimeVisible...` tương ứng.
4. **Kiểm tra đúng đích.** Class annotation khác field annotation; parameter declaration khác parameter **type**; return type khác method declaration.
5. **Kiểm tra annotation được lặp lại.** Nếu source có nhiều `@NoteTag`, xem container `Notes` và thử `getAnnotationsByType(NoteTag.class)`.
6. **Kiểm tra quy tắc kế thừa.** `@Inherited` có thể khiến reflection trên subclass thấy annotation của superclass **mà subclass không chứa annotation đó trong class file**. Khi đó xem cả class file của superclass.
7. **Phân biệt Java reflection với framework.** Một framework có thể quét method/interface/type hierarchy theo quy tắc riêng, còn `javap` chỉ báo dữ liệu thực sự trong file class.
8. **Rebuild sạch khi cần.** Nếu source vừa đổi retention/target/giá trị, xóa output build cũ bằng quy trình build được dự án cho phép rồi biên dịch lại; tránh xem class file lỗi thời.
9. **Đối chiếu bằng hai phép kiểm tra.** Dùng `javap -v` để biết bytecode lưu gì; dùng reflection test để biết API runtime nhìn thấy gì.

`javap` rất mạnh để giải thích **vì sao** metadata có mặt hoặc vắng mặt, nhưng không thay thế việc kiểm thử logic annotation processor, static checker, dependency injection hay validation của framework.

## 12. Những nhầm lẫn và lỗi thường gặp

### 12.1. Chạy `javap -c` rồi không thấy annotation

`-c` tập trung vào mã bytecode của method. Nếu mục tiêu là class-file metadata, hãy dùng **`-v`**. Có thể kết hợp `-c -v -p` khi muốn vừa phân tích bytecode vừa xem attributes chi tiết.

### 12.2. Không thấy annotation `SOURCE` nên nghĩ compiler đã bỏ qua

Retention `SOURCE` được thiết kế để **không tồn tại trong file class**. Annotation processor hoặc compiler vẫn có thể sử dụng nó trong quá trình biên dịch. Việc `javap` không hiển thị là **đúng ngữ nghĩa**, không chứng minh source không có annotation.

### 12.3. `RuntimeInvisible` nghĩa là annotation riêng tư

Không đúng. “Invisible” liên quan **runtime reflection visibility**, không liên quan modifier `private`. `javap -p` cho xem private members; nó không làm retention `CLASS` biến thành `RUNTIME`.

### 12.4. Chỉ tìm `RuntimeVisibleAnnotations` nhưng annotation là `TYPE_USE`

Annotation TYPE_USE thường nằm trong `RuntimeVisibleTypeAnnotations`, có thể dưới `Code` khi ở cast, dưới method khi ở return/parameter type. Tìm đúng nhóm attribute và `target_type`.

### 12.5. Hiển thị container rồi nghĩ mất annotation lặp

Hai lần `@NoteTag` có thể được biểu diễn qua `@Notes` container. Xem các phần tử `value=[@NoteTag(...), ...]` và dùng `getAnnotationsByType()` khi kiểm tra runtime.

### 12.6. Tìm `getAnnotations` trên subclass nhưng `javap` subclass không có annotation

Với annotation type có `@Inherited`, Java reflection có thể tra **superclass chain**. `javap` khi chỉ đọc subclass file **không tự tổng hợp metadata của superclass**. Hãy xem class file cha.

### 12.7. Nhầm tên annotation trong constant pool với annotation được áp dụng

`Constant pool` chứa chuỗi tên kiểu, UTF-8 constants và descriptor tham chiếu. Sự xuất hiện của tên annotation ở đây **chưa đủ** chứng minh một declaration cụ thể có annotation; phải đối chiếu attribute thực tế ở member/class/type vị trí cần thiết.

### 12.8. Đọc sai file do classpath

Nếu một dự án có nhiều output folder hoặc dependency JAR, `javap` có thể phân tích một phiên bản class khác với chương trình đang chạy. Cần kiểm soát đường dẫn classpath và binary name; có thể dùng class loader/resource diagnostics nếu nghi ngờ classpath runtime khác build artifact.

### 12.9. Phụ thuộc vào `#NN` hay offset cụ thể

Constant pool và offset bytecode là dữ liệu chi tiết phụ thuộc compiler và code. Thêm một field hoặc sửa một câu lệnh có thể thay số `#NN`, `offset` và `LineNumberTable` dù ý nghĩa annotation không đổi. Đừng viết test so sánh toàn bộ output `javap -v` như một giao diện ổn định.

## 13. Checklist thực hành

- [ ] Đã biên dịch thành công bằng đúng JDK/source compatibility chưa?
- [ ] Đã chạy `javap -v -p` với **đúng class file**, đúng classpath và package chưa?
- [ ] Đã xác định annotation nằm trên class, field, method, parameter declaration hay type-use chưa?
- [ ] Đã phân biệt **`RuntimeVisible`**, **`RuntimeInvisible`** và retention **`SOURCE`** chưa?
- [ ] Đã xem `RuntimeVisibleParameterAnnotations` hoặc `RuntimeVisibleTypeAnnotations` nếu annotation nằm tại parameter/type-use chưa?
- [ ] Nếu dùng `@Repeatable`, đã xem container annotation và thử `getAnnotationsByType` chưa?
- [ ] Nếu annotation là default element value, đã xem `AnnotationDefault` trên **annotation type** chưa?
- [ ] Đã lưu ý sự khác biệt giữa metadata trong class file và metadata mà reflection/framework thật sự đọc chưa?

## 14. Tài liệu chuẩn

- [JDK 17 `javap` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): các tùy chọn `-v`, `-p`, `-classpath` và cách chỉ định class.
- [Java SE 17 JLS `9.6.4.2 — `@Retention`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.4.2): retention policies và mặc định `CLASS`.
- [Java SE 17 JVM Spec `4.7.16–`4.7.22](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.16): định dạng các annotation-related attributes và `AnnotationDefault`.
- [Java SE 17 API — `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): quy tắc tra cứu annotation lúc chạy, gồm `@Repeatable` và `@Inherited`.
- [Java SE 17 API — `AnnotatedType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedType.html): API đọc annotation trên kiểu ở các vị trí được hỗ trợ.

**Ghi nhớ:** hãy biên dịch rồi chạy **`javap -v -p <ClassName>`** để kiểm tra **metadata thật sự được lưu trong `.class`**. `RUNTIME` thường đi vào `RuntimeVisible...`; `CLASS` vào `RuntimeInvisible...`; `SOURCE` không được lưu. Muốn đọc đúng kết quả, cần quan sát **chính xác attribute, member và target type**, thay vì chỉ tìm chuỗi tên annotation trong output. Dùng thêm reflection test khi cần xác nhận ứng dụng nhìn thấy metadata đó như thế nào.