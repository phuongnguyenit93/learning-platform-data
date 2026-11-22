# getParameters và Parameter trong Java Reflection

## 1. Mục tiêu: đọc tham số của method và constructor bằng Reflection

Khi xây dựng framework định tuyến, dependency injection, validation, serializer hoặc công cụ phân tích API, việc tìm được một `Method` hay `Constructor<?>` chưa đủ: ta còn cần biết nó nhận bao nhiêu tham số, kiểu của từng tham số, thứ tự, annotation, tên tham số (nếu có metadata) và liệu tham số cuối cùng có phải varargs.

Java đặt những thông tin đó tại `java.lang.reflect.Executable` và `java.lang.reflect.Parameter`:

- `Method` và `Constructor<?>` đều kế thừa `Executable`.
- `Executable.getParameters()` trả về một mảng `Parameter[]`, theo đúng thứ tự tham số của executable ở cấp Reflection.
- Mỗi `Parameter` đại diện cho **một tham số của một executable cụ thể**. `getDeclaringExecutable()` cho phép truy ngược về method/constructor sở hữu tham số.
- `Parameter` cung cấp `getName()`, `isNamePresent()`, `getType()`, `getParameterizedType()`, `getAnnotatedType()`, `getAnnotations()`, `getAnnotation(...)`, `getModifiers()`, `isImplicit()`, `isSynthetic()` và `isVarArgs()`.

Một tham số tên `id`, có kiểu `List<String>` và annotation `@NotNull` là ba lớp metadata **khác nhau**. Nếu class được biên dịch thiếu thông tin tên, Reflection vẫn có thể biết kiểu, thứ tự và annotation; không nên suy luận rằng `getParameters()` trả mảng rỗng.

## 2. Phân biệt những API tra cứu thường gặp

| API | Kết quả | Khi nào dùng |
| --- | --- | --- |
| `Executable.getParameterCount()` | Số tham số được Reflection thấy. | Kiểm tra số lượng trước khi ghép argument. |
| `Executable.getParameters()` | `Parameter[]`, thứ tự từ trái sang phải. | Cần tên, annotation, modifier, varargs và generic type cho từng tham số. |
| `Executable.getParameterTypes()` | `Class<?>[]` chứa kiểu đã erasure. | Xây dựng chữ ký Reflection hoặc đối chiếu argument runtime. |
| `Executable.getGenericParameterTypes()` | `Type[]`, có thể là `ParameterizedType`/`TypeVariable`/`GenericArrayType`. | Cần khai báo generic. |
| `Executable.getParameterAnnotations()` | `Annotation[][]`, các annotation được khai báo trên từng formal parameter. | Khi xử lý nhiều tham số bằng chỉ số; `Parameter.getAnnotations()` tiện hơn. |
| `Executable.isVarArgs()` | Executable khai báo varargs ở cấp bytecode hay không. | Phân biệt `String[]` thông thường và `String...`. |
| `Parameter.getDeclaringExecutable()` | `Method` hoặc `Constructor<?>` sở hữu tham số. | Xây báo lỗi có ngữ cảnh đầy đủ. |
| `Parameter.getName()` | Tên lấy từ metadata nếu có, hoặc tên thay thế như `arg0`. | Hiển thị; chỉ coi là tên source khi `isNamePresent() == true`. |
| `Parameter.getParameterizedType()` | `Type` của riêng tham số, bảo toàn khai báo generic. | Phân tích `List<String>`, `T`, v.v. |
| `Parameter.getAnnotatedType()` | `AnnotatedType` cho annotation trên **cách dùng kiểu** của tham số. | Kiểm tra `@Target(TYPE_USE)`. |

`getParameterTypes()` không có tên hoặc annotation; `getParameters()` cung cấp từng đối tượng `Parameter` nhưng **không tự đọc mã nguồn Java**. Metadata được tạo từ class file/runtime.

## 3. Cờ biên dịch `-parameters` và tên tham số

Mặc định, `javac` **không bắt buộc** ghi tên tham số trong class file dưới dạng metadata Reflection. Khi không có thuộc tính `MethodParameters` chứa tên, `getParameters()` vẫn trả về các `Parameter`, còn:

- `getName()` thường là `arg0`, `arg1`, `arg2`… theo vị trí.
- `isNamePresent()` trả `false`.
- `getType()`, `getParameterizedType()` và parameter annotation vẫn có thể truy cập được, nếu metadata cần thiết tương ứng được lưu.

Biên dịch bằng `javac -parameters` yêu cầu lưu tên và modifier của formal parameters trong class file:

~~~bash
javac -parameters -encoding UTF-8 ParameterMetadataDemo.java
java ParameterMetadataDemo
~~~

Khi class có metadata hợp lệ, `getName()` trả tên thực được biên dịch (chẳng hạn `recipient`), `isNamePresent() == true`. Cờ `-parameters` là lựa chọn **lúc build**, không phải `java -parameters` ở lúc chạy.

Phân biệt `-parameters` và `-g`:

- `-parameters` ghi thuộc tính `MethodParameters` để Core Reflection lấy tên tham số.
- `-g`/`-g:vars` điều khiển debug information như local-variable tables; tên biến debug có thể phục vụ debugger, nhưng **không** tự thay thế `-parameters` cho `Parameter.getName()`.
- Sau obfuscation, transformation hoặc build bằng compiler khác, metadata có thể bị thay đổi hay loại bỏ. Runtime phải kiểm tra `isNamePresent()` thật, không đoán từ môi trường phát triển.

Ví dụ thực tế: một router muốn tự ánh xạ query parameter vào tên Java có thể dùng `isNamePresent()` để quyết định; nếu `false`, yêu cầu annotation nêu tên rõ ràng hoặc cấu hình mapping, thay vì lấy chuỗi `arg0` làm tên public API.

### Metadata tên có phải điều kiện bắt buộc?

Không phải. Một executable vẫn gọi được khi không lưu tên source. Tên tham số **không phải** thành phần của signature JVM; ví dụ hai method có cùng tên và kiểu tham số nhưng chỉ khác tên biến Java không được overload. Vì vậy tên tham số được xem là metadata phục vụ reflection/tooling, không phải định danh hành vi gọi method.

`getParameters()` cũng có thể ném `MalformedParametersException` khi thông tin `MethodParameters` trong class file không hợp lệ. Khi xử lý bytecode được biến đổi hoặc class từ nguồn không đáng tin cậy, hãy có nhánh báo lỗi metadata thay vì âm thầm giả định tên hợp lệ.

## 4. Ví dụ Java 17+ chạy độc lập: method, constructor, varargs, annotation và generic

Tạo file `ParameterMetadataDemo.java`. Không cần Spring hay thư viện ngoài.

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;
import java.util.List;

public class ParameterMetadataDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface Name {
        String value();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    @interface TypeMark {}

    static class Service {
        Service(String title) {}

        static void dispatch(
                @Name("user") @TypeMark String recipient,
                final int retries,
                String... labels) {
        }

        static <T extends Number> void aggregate(List<T> numbers, T seed) {
        }
    }

    public static void main(String[] args) throws Exception {
        Method dispatch = Service.class.getDeclaredMethod(
                "dispatch", String.class, int.class, String[].class);

        System.out.println("dispatch parameters="
                + dispatch.getParameterCount());
        Parameter[] parameters = dispatch.getParameters();
        for (int i = 0; i < parameters.length; i++) {
            Parameter parameter = parameters[i];
            Name annotation = parameter.getAnnotation(Name.class);
            System.out.println(i + ": name=" + parameter.getName()
                    + ", present=" + parameter.isNamePresent()
                    + ", type=" + parameter.getType().getSimpleName()
                    + ", generic=" + parameter.getParameterizedType().getTypeName()
                    + ", varargs=" + parameter.isVarArgs()
                    + ", label=" + (annotation == null ? "-" : annotation.value())
                    + ", typeMark=" + parameter.getAnnotatedType()
                            .isAnnotationPresent(TypeMark.class));
        }

        Method aggregate = Service.class.getDeclaredMethod(
                "aggregate", List.class, Number.class);
        Parameter[] generic = aggregate.getParameters();
        System.out.println("generic first="
                + generic[0].getParameterizedType().getTypeName());
        System.out.println("generic second="
                + generic[1].getParameterizedType().getTypeName());
        System.out.println("erased second="
                + generic[1].getType().getTypeName());

        Constructor<Service> constructor =
                Service.class.getDeclaredConstructor(String.class);
        Parameter title = constructor.getParameters()[0];
        System.out.println("constructor name=" + title.getName()
                + ", present=" + title.isNamePresent());
        System.out.println("owner is constructor="
                + (title.getDeclaringExecutable() == constructor));
    }
}
~~~

Biên dịch **không có** `-parameters`:

~~~bash
javac -encoding UTF-8 ParameterMetadataDemo.java
java ParameterMetadataDemo
~~~

Đầu ra điển hình với `javac` Java 17/21 không lưu thuộc tính tên tham số:

~~~text
dispatch parameters=3
0: name=arg0, present=false, type=String, generic=java.lang.String, varargs=false, label=user, typeMark=true
1: name=arg1, present=false, type=int, generic=int, varargs=false, label=-, typeMark=false
2: name=arg2, present=false, type=String[], generic=java.lang.String[], varargs=true, label=-, typeMark=false
generic first=java.util.List<T>
generic second=T
erased second=java.lang.Number
constructor name=arg0, present=false
owner is constructor=true
~~~

Sau đó **biên dịch lại cùng source** (ghi đè class file vừa sinh), nhưng có `-parameters`:

~~~bash
javac -parameters -encoding UTF-8 ParameterMetadataDemo.java
java ParameterMetadataDemo
~~~

Đầu ra trở thành:

~~~text
dispatch parameters=3
0: name=recipient, present=true, type=String, generic=java.lang.String, varargs=false, label=user, typeMark=true
1: name=retries, present=true, type=int, generic=int, varargs=false, label=-, typeMark=false
2: name=labels, present=true, type=String[], generic=java.lang.String[], varargs=true, label=-, typeMark=false
generic first=java.util.List<T>
generic second=T
erased second=java.lang.Number
constructor name=title, present=true
owner is constructor=true
~~~

Điều quan trọng từ ví dụ:

- `getParameters()` luôn thấy ba tham số `dispatch` trong cả hai lần biên dịch; **chỉ metadata tên thay đổi**.
- `@Name("user")` trên formal parameter lấy qua `Parameter.getAnnotation(Name.class)`; không phụ thuộc việc có tên source.
- `@TypeMark` là annotation trên **type use**, phải lấy qua `getAnnotatedType()`; không đồng nhất với annotation gắn trực tiếp vào declaration của parameter.
- `String... labels` ở bytecode là `String[]`, nên `getType().getSimpleName()` hiển thị `String[]`; `Parameter.isVarArgs()` xác nhận tham số cuối của executable varargs.
- `aggregate(List<T>, T)` trả `List<T>` và `T` ở generic metadata; erasure của `T extends Number` là `Number`. Khi tìm method bằng `getDeclaredMethod`, sử dụng `List.class` và `Number.class`, không truyền `T` hay `List<T>`.
- `getDeclaringExecutable()` trả lại constructor tương ứng; trong ví dụ, object phản chiếu constructor được so bằng `==` và kết quả đúng cho đối tượng `Parameter` thuộc cùng `Constructor` đó.

**Lưu ý reproducibility:** Hai lệnh `javac` trên chạy tuần tự, lần sau sinh lại class file với thuộc tính `MethodParameters`. Nếu dùng công cụ build có incremental compilation, hãy bảo đảm toàn bộ code cần metadata thật sự được biên dịch với tùy chọn tương ứng.

## 5. `Parameter` cho biết những gì ngoài tên?

### 5.1. Kiểu khai báo, kiểu generic, và chú thích trên kiểu

Các API này trả thông tin khác nhau:

- `getType()`: `Class<?>` đã erasure; ví dụ `List<String>` thành `List.class`, `T extends Number` thành `Number.class`, `String...` thành `String[].class`.
- `getParameterizedType()`: `java.lang.reflect.Type` có thể chứa `ParameterizedType` (ví dụ `List<T>`), `TypeVariable` (`T`), `WildcardType`, `GenericArrayType`. Nó không nhất thiết là một `Class<?>`.
- `getAnnotatedType()`: mang các annotation loại `TYPE_USE` trong khai báo kiểu, có thể kết hợp với các kiểu annotated chuyên biệt cho generic/nested components.

Không chuyển ép thẳng `(Class<?>) parameter.getParameterizedType()`; phép cast có thể gây `ClassCastException` nếu `Type` thực tế là `ParameterizedType` hoặc `TypeVariable`.

### 5.2. Annotation trên parameter và annotation trên type

Hai dạng có thể trông gần giống nhau trong source:

~~~java
// Ví dụ khai báo chú thích minh họa, không phải class độc lập.
void process(@ParamLabel("id") String id) {}
void processType(@TypeConstraint String id) {}
~~~

Khi annotation có `@Target(PARAMETER)`, `Parameter.getAnnotation(...)` hoặc `getDeclaredAnnotations()` đọc annotation trên declaration của formal parameter. Khi annotation có `@Target(TYPE_USE)`, dùng `Parameter.getAnnotatedType()` rồi `getAnnotation(...)` trên `AnnotatedType`. Annotation có thể được thiết kế cho cả hai vị trí; khi đó phải hiểu cấu trúc đặt annotation và ý nghĩa của framework. `@Retention(RUNTIME)` cần thiết để Reflection có thể truy cập annotation tương ứng lúc chạy.

`getAnnotations()` và `getDeclaredAnnotations()` trên `Parameter` trả metadata annotation của chính parameter; `getAnnotationsByType(...)` xử lý cơ chế repeatable annotation thích hợp. Không nhầm với annotation trên executable (`Method.getAnnotations()`) hoặc trên lớp khai báo.

### 5.3. Modifier, implicit/synthetic và varargs

- `Parameter.getModifiers()` và `Modifier.isFinal(...)` cho biết modifier của formal parameter **nếu metadata phù hợp hiện diện**; không giả định compiler nào cũng lưu giống nhau khi thiếu `-parameters`.
- `isImplicit()` mô tả một parameter **được khai báo ngầm trong source** theo quy tắc ngôn ngữ; `isSynthetic()` là tham số không xuất hiện trực tiếp/không được khai báo ngầm theo mô hình source, do compiler tạo. Những cờ này phụ thuộc thông tin class file và cách compiler phát sinh bytecode.
- `isVarArgs()` mô tả parameter varargs (thường là tham số cuối của method/constructor có `isVarArgs()==true`). Nó không chỉ kiểm tra xem kiểu có phải array: một method nhận `String[]` thường có thể cho `isVarArgs()==false`.

**Không suy luận `isImplicit()==false` hay `isSynthetic()==false` chứng minh tham số tồn tại nguyên văn trong source.** Một số compiler/bytecode transformer không lưu metadata đầy đủ; cũng có các tham số ẩn ở constructor class lồng, enum và các cấu trúc đặc biệt.

## 6. Tham số của constructor: không phải mọi thứ đều thấy giống source

`Constructor<?>` cũng là `Executable`, nên gọi `getParameters()` giống như với `Method`. Tuy nhiên, constructor của một số dạng class có tham số ngầm định/được compiler thêm vào:

1. **Non-static inner member class:** constructor thường nhận một tham số bổ sung để mang enclosing instance. Với `Outer.Inner`, danh sách kiểu của constructor qua Reflection có thể bắt đầu bằng `Outer.class` dù source không viết tên biến như vậy.
2. **Enum:** constructor ở bytecode có thêm tham số do runtime/compiler quản lý, ví dụ tên và ordinal; không coi đó là API constructor người dùng có thể gọi để sinh enum mới. Reflection cấm dùng `Constructor.newInstance` để tạo enum constant.
3. **Record canonical constructor:** danh sách parameter tương ứng với record components; compiler/JLS có quy tắc metadata riêng cho canonical constructor. Đừng gộp trường hợp này với “compiler luôn có tên tham số nguồn hay không”.
4. **Anonymous/local class:** constructor bytecode có thể có tham số cho captured variables hoặc enclosing context. Chi tiết phụ thuộc compiler.

Ví dụ mảnh source hợp lệ:

~~~java
class Outer {
    class Inner {
        Inner(int number) {}
    }
}
~~~

Với `javac`, tìm constructor Reflection của inner class thường phải dùng `getDeclaredConstructor(Outer.class, int.class)`. `getParameterCount()` sẽ bao gồm tham số outer, nên kết quả có thể khác số formal parameters được viết trong constructor source. Để ánh xạ parameter vào dữ liệu người dùng, phải có chính sách nhận dạng và loại trừ các tham số runtime đặc biệt; **không cứng hóa** rằng luôn bỏ tham số index 0 cho mọi constructor.

## 7. Dùng `Parameter` trong thiết kế framework

Giả sử một controller có method:

~~~java
// Mảnh minh họa API framework, annotation giả định đã được định nghĩa.
void find(@RequestKey("id") String id, int page) {}
~~~

Một binder có thể sử dụng thứ tự kiểm tra sau:

1. Đọc `Method.getParameters()`; mỗi phần tử có thứ tự và kiểu trực tiếp.
2. Nếu parameter có annotation nêu tên request rõ ràng, dùng giá trị của annotation vì đó là hợp đồng API.
3. Nếu không có annotation, chỉ dùng `getName()` khi `isNamePresent()==true`. Nếu metadata thiếu, báo lỗi cấu hình hoặc yêu cầu người dùng khai báo tên. Không coi `arg0` là tên HTTP/JSON công khai.
4. Xác định kiểu qua `getType()` và `getParameterizedType()`; dùng converter tường minh cho `String -> int`, `List<T>`, enum, nullability. `Parameter` **không** tự thực hiện chuyển đổi.
5. Xét `isVarArgs()` khi chuẩn bị argument cho method varargs; ở mức Reflection, tham số varargs có kiểu array (`String[]`), và phải chuẩn bị đối tượng array phù hợp khi gọi `Method.invoke`.
6. Ghép mảng arguments theo thứ tự parameter. Bắt lỗi phân giải, chuyển kiểu, truy cập và lời gọi riêng biệt.

Không sử dụng tên tham số như khóa cache độc lập với class/method: hai overload có thể cùng tên `value` nhưng khác kiểu; metadata source có thể thay đổi sau refactor. Khóa method đáng tin cậy phải dựa vào executable, class khai báo và kiểu tham số.

### Khi nào không cần `getParameters()`?

Nếu chỉ cần định danh overload `run(String, int)`, thường có thể dùng `getDeclaredMethod("run", String.class, int.class)` hoặc `getParameterTypes()`. Nếu chỉ cần số lượng, `getParameterCount()` rõ ràng hơn. Chỉ tạo/duyệt `Parameter[]` khi cần các tính chất ở cấp **từng tham số** (tên, annotation, generic, modifier, varargs).

## 8. Những giới hạn và lỗi phổ biến

| Hiểu nhầm | Hệ quả và cách sửa |
| --- | --- |
| “Không bật `-parameters` thì `getParameters()` trả `[]`.” | Sai: vẫn thấy tham số theo chữ ký; thường tên chỉ là `arg0`… |
| “`getName()` luôn là tên source.” | Sai: phải kiểm tra `isNamePresent()`. |
| “`-g:vars` đủ cho Core Reflection tên tham số.” | Sai: dùng `-parameters` cho metadata `MethodParameters`. |
| “`getType()` giữ đủ `List<String>`.” | Sai: dùng `getParameterizedType()` cho generic metadata. |
| “Parameter annotation và type-use annotation là một.” | Sai: phân biệt `getAnnotation(...)` với `getAnnotatedType()`. |
| “Varargs trong Reflection không phải array.” | Sai: `String...` mang kiểu `String[]`, kiểm tra thêm `isVarArgs()`. |
| “Số parameter ở constructor luôn bằng số viết trong source.” | Không đúng cho một số inner/enum/local/anonymous class. |
| “Method được override luôn giữ nguyên tên tham số của cha.” | Sai: khai báo ở lớp con có thể dùng tên khác; tên không tham gia override/signature. |
| “Parameter tự ép kiểu dữ liệu truyền vào.” | Sai: `Parameter` chỉ mô tả metadata, converter/invoker phải xử lý argument. |
| “`isSynthetic()==false` chứng minh người lập trình đã viết tham số.” | Sai: các cờ metadata có giới hạn và phụ thuộc compiler. |

### Xử lý ngoại lệ có ý nghĩa

- `getDeclaredMethod(...)` / `getDeclaredConstructor(...)` có thể ném `NoSuchMethodException` nếu sai kiểu tham số sau erasure.
- `getParameters()` có thể ném `MalformedParametersException` do thuộc tính tên/modifier tham số trong class file bị lỗi.
- Khi phân tích `getParameterizedType()`, có thể gặp `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` với generic signature không hợp lệ/không giải được.
- Khi gọi executable sau phân tích metadata, kiểm tra cả truy cập, số lượng/kiểu argument và exception do chính method/constructor ném; đó là tầng khác với việc đọc `Parameter`.

Không catch tất cả rồi coi metadata thiếu đồng nghĩa constructor/method không tồn tại. Trong công cụ phân tích bytecode, báo riêng nguồn lớp, executable, index tham số và loại lỗi để điều tra.

## 9. Bài tập kiểm chứng

1. Biên dịch demo hai lần, không và có `-parameters`; so sánh chỉ `getName()` và `isNamePresent()`, trong khi kiểu, generic và annotation vẫn giữ nguyên.
2. Thay `dispatch(String... labels)` bằng `dispatch(String[] labels)`, điều chỉnh chữ ký cho phù hợp và quan sát `isVarArgs()`.
3. Thêm một parameter `List<? extends Number> amounts` và in `getParameterizedType().getTypeName()`; kiểm tra khác biệt so với `getType()`.
4. Tạo hai overload `load(String id)` và `load(int id)`; chứng minh tên `id` không đủ để phân biệt chúng.
5. Đặt annotation `@Target(PARAMETER)` trên một parameter, annotation `@Target(TYPE_USE)` trên kiểu của parameter; đọc từng loại qua đúng API.
6. Tạo inner member class `Outer.Inner` có constructor `Inner(int id)`; kiểm tra danh sách kiểu và số lượng tham số runtime.
7. Viết binder nhỏ: ưu tiên annotation nêu tên, dùng `getName()` chỉ khi `isNamePresent()`, còn thiếu tên thì phát hiện lỗi rõ ràng.
8. Thử phương thức generic có `<T extends Number>`; so sánh `getType()` và `getParameterizedType()` của `T`.

## 10. Tài liệu tham khảo

- [Java SE 17 — Executable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html): `getParameters()`, `getParameterTypes()`, `getGenericParameterTypes()` và `getParameterAnnotations()`.
- [Java SE 17 — Parameter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html): tên, annotation, generic type, implicit/synthetic/varargs, declaring executable.
- [javac Java 17 — Options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): tùy chọn `-parameters` ghi formal parameter names để Reflection truy cập.
- [Java Language Specification 17 — `8.4.1 Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): formal parameters, modifier, varargs.
- [JVM Specification 17 — MethodParameters Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.24): metadata tên/tham số trên class file.

**Nguyên tắc cốt lõi:** `getParameters()` cho biết **tham số runtime của executable**, còn `Parameter.getName()` chỉ đáng tin là tên source khi có metadata và `isNamePresent()` xác nhận. Dùng `getType()` cho kiểu erasure, `getParameterizedType()` cho generic, `getAnnotatedType()` cho annotation trên kiểu, và `getAnnotation(...)` cho annotation của parameter.
