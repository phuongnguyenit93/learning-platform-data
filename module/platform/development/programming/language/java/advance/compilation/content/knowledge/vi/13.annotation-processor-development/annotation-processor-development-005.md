# Dùng Elements, Types thay cho suy đoán từ chuỗi kiểu khi xây dựng annotation processor

## 1. Bài toán: đừng coi tên kiểu in ra là mô hình kiểu Java

Trong Java annotation processing, ta thường muốn trả lời những câu hỏi như:

- Một method có trả về kiểu triển khai `CharSequence` không?
- `List<String>` có thể gán cho `List<Object>` không?
- Method `get()` khai báo trong `Box<T>` trả về kiểu gì khi nhìn từ `Box<String>`?
- Một method có override method được kế thừa không?
- Một nested type có qualified name, binary name và owner nào?

Cách xử lý dễ viết nhưng không đáng tin là gọi `typeMirror.toString()`, rồi dùng `equals`, `startsWith`, `contains` hoặc tách chuỗi theo `<`, `>`, dấu phẩy và dấu chấm. Ví dụ:

~~~java
// SAI về hướng thiết kế: minh họa cách không nên quyết định quan hệ kiểu.
String printed = method.getReturnType().toString();
if (printed.equals("java.lang.String")
        || printed.endsWith("StringBuilder")) {
    // Có thể bỏ sót subtype và nhận nhầm kiểu chỉ giống tên.
}
~~~

Cách này nhầm **biểu diễn văn bản của một kiểu** với **ngữ nghĩa của kiểu trong compiler**. Java có generic type arguments, type variables, wildcards, intersection bounds, arrays, nested types, overloaded methods, module boundaries và các kiểu tạm thời chưa resolve. Việc một tên trông giống nhau không chứng minh hai kiểu giống nhau, có quan hệ kế thừa hoặc gán được cho nhau.

Hướng đúng là dùng **language model API** trong module `java.compiler`:

- `javax.lang.model.element.*`: các **khai báo** như class, interface, field, method, type parameter, package, module.
- `javax.lang.model.type.*`: các **kiểu** của khai báo và biểu thức ở mức mô hình type, như `DeclaredType`, `ArrayType`, `TypeVariable`, `WildcardType`, `ExecutableType`, `ErrorType`.
- `javax.lang.model.util.Elements`: tiện ích truy vấn và so sánh **program elements**.
- `javax.lang.model.util.Types`: tiện ích xây dựng và kiểm tra **quan hệ kiểu**.
- `javax.annotation.processing.ProcessingEnvironment`: cung cấp hai tiện ích trên qua `getElementUtils()` và `getTypeUtils()`.

**Nguyên tắc:** dùng `TypeMirror.toString()` để in thông báo cho người đọc khi phù hợp; dùng `Types` để ra quyết định có đúng kiểu, subtype hay assignable. Dùng `Elements` để nhận diện khai báo thực sự, thay vì tự parse tên class và method.

## 2. Phân biệt Element và TypeMirror

Ví dụ khai báo:

~~~java
// Minh họa, không phải toàn bộ chương trình runnable.
class Box<T> {
    T value;
    T get() { return value; }
}
~~~

- `TypeElement` của `Box` đại diện cho **khai báo class** `Box` với các tham số kiểu của nó.
- `TypeParameterElement` của `T` đại diện cho **khai báo tham số kiểu**.
- `VariableElement` của field `value` đại diện cho **khai báo field**.
- `ExecutableElement` của `get` đại diện cho **khai báo method**.
- `TypeMirror` của field mô tả **kiểu** field đó. Với field `T value`, đây là kiểu biến kiểu `T`, không phải một `TypeElement` tên `T`.
- `DeclaredType` của `Box<String>` mô tả một **lần dùng class được tham số hóa**, không phải một class declaration mới tên `Box<String>`.

Đối với khai báo `TypeElement box`, `box.asType()` là kiểu của khai báo với các type variables liên quan; nó không tự trở thành `Box<String>`. Để biểu diễn `Box<String>`, cần `Types.getDeclaredType(box, stringElement.asType())` khi đó là kiểu thích hợp.

| Muốn biết | Chọn API |
| --- | --- |
| Một class/package/module có khai báo/quan sát được không? | `Elements.getTypeElement`, `getPackageElement`, `getModuleElement` |
| Tên canonical/qualified hoặc binary của class? | `TypeElement.getQualifiedName`, `Elements.getBinaryName` |
| Method/field nào thuộc hoặc được thừa kế bởi class? | `getEnclosedElements` và `Elements.getAllMembers` |
| Class là subtype của một interface? | `Types.isSubtype` |
| Giá trị kiểu A có gán được vào biến kiểu B? | `Types.isAssignable(A,B)` |
| Hai biểu diễn kiểu có cùng kiểu Java? | `Types.isSameType` |
| Một generic type được tham số hóa đúng cách? | `Types.getDeclaredType`, `DeclaredType.getTypeArguments` |
| Kiểu method khi được kế thừa qua `Box<String>`? | `Types.asMemberOf` rồi `ExecutableType` |
| Có đúng quan hệ override/hiding? | `Elements.overrides`, `Elements.hides` |
| Kiểu phần tử của array hoặc primitive tương ứng? | `ArrayType.getComponentType`, `Types.getArrayType`, `getPrimitiveType` |

`Element.getSimpleName()` hữu ích để hiển thị tên; nó không đủ để phân biệt các type trùng tên ở các package/module khác nhau.

## 3. Nhận Elements và Types trong annotation processor

Processor có thể kế thừa `AbstractProcessor`. Sau khi compiler gọi `init`, trường `processingEnv` cung cấp utilities và `Messager`:

~~~java
// Fragment ở bên trong một AbstractProcessor; không phải file độc lập.
Elements elements = processingEnv.getElementUtils();
Types types = processingEnv.getTypeUtils();
Messager messages = processingEnv.getMessager();

TypeElement charSequence =
        elements.getTypeElement("java.lang.CharSequence");
if (charSequence == null) {
    messages.printMessage(Diagnostic.Kind.ERROR,
            "Cannot resolve java.lang.CharSequence");
    return true;
}
~~~

`getTypeElement` nhận **canonical name** của type mà compiler nhìn thấy, không phải tên của parameterized type như `java.util.List<java.lang.String>`. Nó có thể trả `null` nếu type không được xác định duy nhất trong môi trường hiện tại. Trong dự án có JPMS, có các overload truy vấn theo module để tránh mơ hồ; không tự giả định mọi package/class đều nằm trên classpath.

Các đối tượng `Element`/`TypeMirror` thuộc **mô hình đang được compiler xử lý**. Không dùng `Class.forName` để kiểm tra class của user source: class ấy có thể chưa được biên dịch/tải vào JVM chạy processor, và reflection nhìn vào classpath của processor thay vì mô hình compilation hiện tại.

## 4. Ví dụ hoàn chỉnh Java 17+: annotation kiểm tra return type

Ta xây một annotation processor yêu cầu method mang `@CheckReturn` phải có kiểu trả về **gán được vào `java.lang.CharSequence`**. Điều kiện này chấp nhận `String`, `StringBuilder` và những kiểu khác thực sự phù hợp; từ chối `Object` dù implementation có thể trả về một `String` ở runtime.

Không dùng kiểm tra chuỗi tên return type. Processor dùng chính `Types.isAssignable`.

Cấu trúc dự án:

~~~text
project/
├── src/
│   ├── processor/java/demo/validation/
│   │   ├── CheckReturn.java
│   │   └── ReturnTypeProcessor.java
│   └── main/java/demo/
│       ├── App.java
│       └── BadApp.java          # dùng riêng cho ca thất bại
└── build/
    ├── processor/
    └── classes/
~~~

### 4.1. Tệp src/processor/java/demo/validation/CheckReturn.java

~~~java
package demo.validation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.SOURCE)
public @interface CheckReturn {
}
~~~

`SOURCE` retention nghĩa là annotation dùng trong quá trình compile; runtime không cần giữ nó. `@Target(METHOD)` ngăn đặt annotation lên class/field ở compile time.

### 4.2. Tệp src/processor/java/demo/validation/ReturnTypeProcessor.java

~~~java
package demo.validation;

import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.type.TypeKind;
import javax.lang.model.type.TypeMirror;
import javax.lang.model.util.Elements;
import javax.lang.model.util.Types;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.validation.CheckReturn")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ReturnTypeProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return true;
        }

        Elements elements = processingEnv.getElementUtils();
        Types types = processingEnv.getTypeUtils();
        TypeElement expected =
                elements.getTypeElement("java.lang.CharSequence");

        if (expected == null) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Cannot resolve java.lang.CharSequence");
            return true;
        }

        TypeMirror target = expected.asType();

        for (Element element :
                roundEnv.getElementsAnnotatedWith(CheckReturn.class)) {
            if (element.getKind() != ElementKind.METHOD) {
                continue;
            }

            ExecutableElement method = (ExecutableElement) element;
            TypeMirror returned = method.getReturnType();

            // Tránh đưa ra kết luận sai khi kiểu vẫn lỗi/unresolved.
            if (returned.getKind() == TypeKind.ERROR) {
                continue;
            }

            if (!types.isAssignable(returned, target)) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@CheckReturn requires a type assignable to "
                                + "java.lang.CharSequence",
                        method);
            }
        }
        return true;
    }
}
~~~

Giải thích các dòng quan trọng:

1. `getElementsAnnotatedWith(CheckReturn.class)` trả về những **khai báo thực** được chú thích; không cần tìm chuỗi `@CheckReturn` trong source.
2. `ElementKind.METHOD` xác nhận element thuộc dạng method. `@Target(METHOD)` đã kiểm soát điều này; nhánh kiểm tra vẫn minh họa cách xử lý thận trọng.
3. `((ExecutableElement) element).getReturnType()` lấy `TypeMirror` của kiểu trả về đã được compiler phân giải, chứ không phải text signature.
4. `elements.getTypeElement("java.lang.CharSequence").asType()` cung cấp target type theo mô hình compiler.
5. `types.isAssignable(returned, target)` kiểm tra **quan hệ gán kiểu của Java**. Kiểm tra này không chỉ giới hạn ở các class được liệt kê thủ công hay các tên kết thúc bằng một hậu tố nào đó.
6. `Messager.printMessage(ERROR, ..., method)` gắn lỗi vào khai báo method, giúp người dùng định vị nguyên nhân thay vì phát log ngoài luồng bằng `System.out.println`.
7. `return true` nói processor này **claim** annotation types mà nó xử lý. Processor khác không được kỳ vọng tiếp tục xử lý cùng annotation trong lượt dispatch đó; lựa chọn trả `true/false` phải phù hợp thiết kế processor thực tế.

Nhánh `TypeKind.ERROR` là một chính sách tối giản trong ví dụ nhằm tránh chẩn đoán dây chuyền khi compiler đã không giải được return type; processor production có thể trì hoãn/ghi nhận ở các vòng sau theo yêu cầu generator và compiler. Không được dùng `ERROR` như một kiểu hợp lệ hoặc âm thầm bỏ qua mọi dependency lỗi.

### 4.3. Tệp src/main/java/demo/App.java

~~~java
package demo;

import demo.validation.CheckReturn;

public final class App {
    @CheckReturn
    static String first() {
        return "ready";
    }

    @CheckReturn
    static StringBuilder second() {
        return new StringBuilder("built");
    }

    public static void main(String[] args) {
        System.out.println(first());
        System.out.println(second());
    }
}
~~~

Cả `String` và `StringBuilder` đều triển khai `CharSequence`, nên hai method hợp lệ mà không cần đối chiếu text tên type.

### 4.4. Biên dịch processor rồi biên dịch ứng dụng

Từ thư mục `project/` trên Bash, với JDK 17+:

~~~bash
mkdir -p build/processor build/classes

javac --release 17 -encoding UTF-8 -d build/processor src/processor/java/demo/validation/CheckReturn.java src/processor/java/demo/validation/ReturnTypeProcessor.java

javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.validation.ReturnTypeProcessor -d build/classes src/main/java/demo/App.java

java -cp build/classes demo.App
~~~

Stdout của lệnh `java` cuối:

~~~text
ready
built
~~~

Lần `javac` thứ nhất tạo annotation class và processor class. Lần `javac` thứ hai:

- Dùng `-cp build/processor` để source ứng dụng **nhìn thấy annotation type** khi biên dịch.
- Dùng `-processorpath build/processor` để compiler **nạp processor implementation**.
- Dùng `-processor demo.validation.ReturnTypeProcessor` để chọn đúng processor cần thực thi, không phụ thuộc vào auto-discovery qua `META-INF/services`.
- Dùng `-d build/classes` để ghi application class file; processor class output vẫn tách ở `build/processor`.

Trên PowerShell, có thể thay `mkdir -p build/processor build/classes` bằng:

~~~powershell
New-Item -ItemType Directory -Force build/processor, build/classes | Out-Null
~~~

Các lệnh `javac` ở trên chỉ có một thư mục cho mỗi classpath/processorpath nên không cần đổi dấu phân cách; nếu thêm nhiều entries thì Unix dùng `:`, Windows dùng `;`.

### 4.5. Trường hợp bị processor từ chối

Tạo tệp độc lập **src/main/java/demo/BadApp.java**:

~~~java
package demo;

import demo.validation.CheckReturn;

public final class BadApp {
    @CheckReturn
    static Object invalid() {
        return "text";
    }
}
~~~

Biên dịch riêng BadApp với processor đã tạo:

~~~bash
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor demo.validation.ReturnTypeProcessor -d build/classes src/main/java/demo/BadApp.java
~~~

Đây là một **lệnh được thiết kế để thất bại**: kiểu *khai báo* của `invalid()` là `Object`, không thể gán trực tiếp vào biến `CharSequence`. Việc thân method tình cờ trả về `String` không đổi return type đã khai báo. Compiler nhận một `Diagnostic.Kind.ERROR` kèm thông báo:

~~~text
@CheckReturn requires a type assignable to java.lang.CharSequence
~~~

Không nên kỳ vọng toàn bộ stderr (file, dòng, caret, số errors) giống hệt trên mọi phiên bản JDK. Processor không chạy chương trình `BadApp`; lỗi xuất hiện ngay khi biên dịch.

**Chỉ sửa return type sang `String` hoặc một type thật sự phù hợp**, nếu hợp đồng API cho phép, là cách hợp lệ để đạt điều kiện. Tắt processor hoặc so sánh hậu tố tên `Object` không giải quyết ngữ nghĩa cần kiểm tra.

## 5. Ba quan hệ kiểu khác nhau: same type, subtype, assignable

Các phép kiểm tra sau có ý nghĩa khác nhau:

| API | Câu hỏi | Ví dụ |
| --- | --- | --- |
| `types.isSameType(a, b)` | Hai TypeMirror mô tả cùng một kiểu? | `String` và `String` |
| `types.isSubtype(a, b)` | Kiểu a có là subtype của b? | `String` subtype `CharSequence` |
| `types.isAssignable(a, b)` | Một giá trị có kiểu a có gán được cho biến kiểu b? | `int` có thể gán vào `long` theo widening primitive |
| `types.erasure(a)` | Kiểu sau xóa generic type arguments là gì? | `List<String>` có erasure `List` |
| `types.directSupertypes(a)` | Những supertypes trực tiếp là gì? | `String` có các supertype liên quan |

**Thứ tự đối số có ý nghĩa:** `isAssignable(sourceType, destinationType)`. Đổi ngược hai đối số sẽ kiểm tra hướng ngược lại.

Ví dụ, việc `Integer` là subtype của `Number` không làm `List<Integer>` thành subtype của `List<Number>`; generic của Java không covariance theo cách đó. Nhưng `List<Integer>` có thể gán vào `List<? extends Number>` theo quy tắc wildcard. So sánh chuỗi `"java.util.List<java.lang.Integer>"` và `"java.util.List<? extends java.lang.Number>"` không thể diễn đạt hết các quan hệ này.

`isSameType` còn có **ngoại lệ cần biết từ API contract**: khi một đối số là kiểu wildcard, phương thức trả false, kể cả khi xét chính cùng wildcard TypeMirror. Không viết `isSameType(w, w)` rồi kết luận model bị hỏng. Khi thao tác với wildcards/capture, chọn toán tử quan hệ phù hợp và kiểm tra `TypeKind`.

`isAssignable` theo assignment conversion cũng không hoàn toàn đồng nghĩa `isSubtype`; có trường hợp widening/boxing hoặc unchecked conversions được language model đánh giá theo quy tắc Java. Nếu yêu cầu là “phải implement interface”, `isSubtype` thường diễn đạt đúng hơn; nếu yêu cầu là “kết quả return có thể gán cho CharSequence”, `isAssignable` đúng hơn cho ví dụ ở trên.

## 6. Không parse tên type để xử lý generic và wildcard

Một biểu thức kiểu như:

~~~java
// Minh họa kiểu nguồn:
java.util.Map<String, java.util.List<? extends Number>>
~~~

chứa nhiều cấp `DeclaredType` và một `WildcardType`. Tự split chuỗi theo dấu phẩy, dấu `<` hoặc `>` rất dễ hỏng khi nesting tăng hoặc gặp type annotations, raw types, capture variables và type variables.

Trong processor, đường đúng là:

1. Kiểm tra `mirror.getKind() == TypeKind.DECLARED`.
2. Cast `DeclaredType declared = (DeclaredType) mirror`.
3. Đọc `declared.asElement()` để biết element sở hữu khai báo type.
4. Đọc `declared.getTypeArguments()` cho type arguments; duyệt đệ quy bằng `TypeKind`.
5. Với `TypeKind.WILDCARD`, dùng `WildcardType.getExtendsBound()` hoặc `getSuperBound()` thay vì parse ký tự `?` và khoảng trắng.
6. Với `TypeKind.ARRAY`, dùng `ArrayType.getComponentType()`, không suy từ hậu tố `[]`.
7. Với `TypeKind.TYPEVAR`, dùng `TypeVariable.asElement()` và bounds theo model; không thử tìm một top-level class có tên `T`.

Đoạn kiểm tra cấu trúc ngắn (dùng trong processor khi đã có `TypeMirror mirror`):

~~~java
// Fragment, không phải chương trình độc lập:
if (mirror.getKind() == TypeKind.DECLARED) {
    DeclaredType declared = (DeclaredType) mirror;
    TypeElement raw = (TypeElement) declared.asElement();
    String owner = raw.getQualifiedName().toString();
    for (TypeMirror argument : declared.getTypeArguments()) {
        // Kiểm tra từng TypeKind/quan hệ kiểu bằng Types.
    }
}
~~~

Chuỗi `owner` ở đây dùng để **hiển thị tên khai báo**, không dùng để suy ra quan hệ inheritance hay generic compatibility.

Nếu cần dựng kiểu `List<String>` theo mô hình compiler, lấy `TypeElement` của `java.util.List` và `java.lang.String`, rồi gọi:

~~~java
// Fragment trong processor:
TypeElement list = elements.getTypeElement("java.util.List");
TypeElement str = elements.getTypeElement("java.lang.String");
if (list != null && str != null) {
    DeclaredType listOfString = types.getDeclaredType(list, str.asType());
    // Đây là model List<String>, không phải một class tên List<String>.
}
~~~

`Elements.getTypeElement("java.util.List<java.lang.String>")` không phải cách hợp lệ để lấy một kiểu được tham số hóa. Không dùng tên đầy đủ của JAR/source file như một “generic type string” để thay thế `DeclaredType`.

## 7. asMemberOf: cùng method nhưng chữ ký thay đổi theo generic owner

Xét:

~~~java
// Minh họa model generic; không phải file độc lập để chạy.
class Box<T> {
    T get() { return null; }
}

class StringBox extends Box<String> {
}
~~~

`get()` được khai báo trong `Box<T>`, nên tại **vị trí khai báo** return type là type variable `T`. Nhưng khi xem method ấy như một thành viên của `Box<String>` hoặc subtype `StringBox`, người dùng API thấy return type đã được thay thế bằng `String`.

Đừng lấy `method.getReturnType().toString()` rồi thay chữ `T` bằng `String` theo text: cách này hỏng với nhiều type variables, nested generics, bounds và inheritance chain.

Sử dụng:

~~~java
// Fragment trong processor; giả định đã có:
//   DeclaredType viewedAs
//   ExecutableElement inheritedGet
//   Types types
TypeMirror viewedMember = types.asMemberOf(viewedAs, inheritedGet);
if (viewedMember.getKind() == TypeKind.EXECUTABLE) {
    ExecutableType signature = (ExecutableType) viewedMember;
    TypeMirror actualReturn = signature.getReturnType();
    // actualReturn phản ánh kiểu get() nhìn từ viewedAs.
}
~~~

`viewedAs` cần thật sự là declared type mà method đó có thể được xem là member. Đây là lý do method `asMemberOf` nhận **cả owner context lẫn element**, thay vì chỉ nhận một chuỗi signature. Nó giúp xử lý generic substitution đúng theo Java Language Specification.

Khi cần xem members đã thừa kế, dùng `elements.getAllMembers(typeElement)`; `element.getEnclosedElements()` chủ yếu trả members khai báo trực tiếp. Nếu muốn phân loại method/field, dùng `ElementKind` hoặc `ElementFilter.methodsIn(...)` cho danh sách đúng dạng.

**Chú ý:** `getAllMembers` không tự thay thế mọi kiểm tra accessibility hoặc overload của riêng mục tiêu processor. Tập member và việc một caller ở package/module khác có quyền dùng member là hai câu hỏi khác nhau.

## 8. Tránh đoán override và method signature từ text

Hai method có cùng tên đơn `run` không nhất thiết override nhau: có thể là overload khác tham số, method static che khuất method khác hoặc declaration không nằm trong quan hệ inheritance phù hợp.

Các API cần dùng:

- `elements.overrides(overrider, overridden, contextType)`: hỏi một `ExecutableElement` có override method kia **khi xem trong ngữ cảnh type** nào không.
- `elements.hides(hider, hidden)`: hỏi một type/method/field có che khuất declaration kia theo quy tắc Java không.
- `types.isSubsignature(methodType1, methodType2)`: so sánh quan hệ method signature theo language rules, không dựa vào `toString()`.
- `types.asMemberOf(contextDeclaredType, methodElement)`: lấy signature sau substitution của generics ở owner được xét.

Với method `m(List<String>)`, text và erasure có thể giống/khác theo những quy tắc mà một phép so chuỗi không biểu diễn đủ. Dùng compiler model thay vì so số ký tự hay tên method.

`Elements.getBinaryName(TypeElement)` có thể trả tên khác `getQualifiedName()` đối với member/nested class: ví dụ binary name có dấu `$` như `Outer$Inner`, trong khi qualified name dùng dấu chấm `Outer.Inner`. Chọn đúng loại tên theo mục đích (hiển thị Java source, class-file lookup, code generation), không tự viết regex để thay `.` bằng `$` trong mọi trường hợp.

## 9. Annotation Class<?> và MirroredTypeException

Giả sử annotation khai báo thuộc tính:

~~~java
// Fragment minh họa, không phải file độc lập.
@interface UsesType {
    Class<?> value();
}
~~~

Khi processor đọc `@UsesType(SomeClass.class)`, class `SomeClass` có thể **chưa được load** vào JVM chạy processor. Gọi `annotation.value()` trên proxy annotation do language model cung cấp có thể ném `MirroredTypeException`; điều này là một phần cơ chế annotation processing, không có nghĩa class bị lỗi.

Có hai hướng thích hợp:

1. Đọc `AnnotationMirror` và `AnnotationValue` theo `Element.getAnnotationMirrors()` (hoặc dùng `Elements.getElementValuesWithDefaults` khi cần default values). Thuộc tính kiểu class thường được biểu diễn bằng `TypeMirror`.
2. Nếu cố ý dùng API proxy annotation, xử lý `MirroredTypeException` và lấy `getTypeMirror()` thay vì cố nạp class bằng reflection.

Sau khi có `TypeMirror`, dùng `Types` để hỏi quan hệ kiểu, không ép `Class<?>.getName()` làm nguồn chân lý cho mã đang được biên dịch.

Đối với repeatable annotations, inherited annotations và các trường hợp type-use annotations, API model có chi tiết riêng. Đừng coi việc parse text của source là tương đương với compiler's symbol table.

## 10. Kiểm soát error types, rounds và model chưa hoàn chỉnh

Annotation processing có thể diễn ra qua **nhiều rounds**. Processor tạo source ở một round thì compiler có thể nhận các source ấy trong round tiếp theo. Vì vậy một type chưa được resolve ở thời điểm đầu không nhất thiết có cùng trạng thái ở mọi round.

Cần biết:

- `TypeKind.ERROR` biểu diễn kiểu không thể được phân giải hợp lệ trong mô hình hiện tại. Nó có thể xuất hiện khi dependency chưa hiện diện hoặc generated source chưa sẵn sàng.
- `getTypeElement(...)` có thể trả `null` khi lookup không thành công hoặc không xác định duy nhất; không ép null thành một type string tùy tiện.
- `roundEnv.processingOver()` cho biết round cuối dành cho kết thúc xử lý; `roundEnv.errorRaised()` cho biết trạng thái lỗi liên quan round trước theo contract.
- `Messager` nên gắn chẩn đoán vào `Element`, `AnnotationMirror` hoặc `AnnotationValue` liên quan khi có thể, để người dùng thấy đúng vị trí.
- `Filer` chỉ được dùng tạo output mới theo contract. Không tự sửa source người dùng hoặc ghi trùng một generated file qua các rounds.
- Model objects chỉ có ý nghĩa trong ngữ cảnh processing environment hiện hành; không serialize `TypeMirror.toString()` để làm cache ngữ nghĩa xuyên các lần build.

Một processor lớn có thể lựa chọn **trì hoãn** xử lý element chứa `ErrorType` đến khi code được sinh xong, hoặc báo lỗi có ngữ cảnh khi hết rounds, tùy hệ sinh thái. Không tự suy kết luận “không assignable” chỉ vì ở thời điểm sớm compiler còn chưa resolve một type.

**Phân biệt ERROR và NONE/VOID:** `TypeKind.ERROR` biểu thị vấn đề phân giải; `TypeKind.VOID` là kiểu trả về `void`; `TypeKind.NONE` là pseudo-type trong những vị trí không có kiểu thực. Đừng cho rằng mọi `TypeMirror` đều là `DeclaredType` rồi cast thẳng.

## 11. Các lỗi thiết kế processor thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách thay |
| --- | --- | --- |
| `mirror.toString().equals("java.lang.String")` | Chỉ nhận một cách in tên, bỏ subtype/aliases/generics | `Elements.getTypeElement` + `Types.isSameType/isAssignable/isSubtype` |
| `printed.contains("List")` | Tên package/class khác có thể chứa cùng chuỗi | Kiểm tra `DeclaredType.asElement()`, `getQualifiedName()` |
| Parse `List<Map<A,B>>` bằng dấu phẩy | Nested generics và wildcard làm split sai | `getTypeArguments()`, `TypeKind`, `WildcardType` |
| So `typeMirror1 == typeMirror2` | Object identity không phải Java type equality | `types.isSameType` với caveat wildcard |
| Dùng `Class.forName` để resolve user source | Mã chưa được biên dịch/load; classloader processor khác | `Elements.getTypeElement` |
| Dùng `method.toString()` để nhận biết override | Không đủ owner, inheritance, overload context | `Elements.overrides`, `Types.isSubsignature` |
| Lấy return type của method generic ở khai báo rồi tự thay T | Substitution có thể nhiều tầng và nested | `Types.asMemberOf` |
| So class name `endsWith("Entity")` để kiểm tra implement interface | Trùng tên không chứng minh quan hệ | `Types.isSubtype`/ `isAssignable` |
| Bỏ qua null hoặc ErrorType | Processor có thể crash hay báo lỗi dây chuyền | Kiểm tra lookup, `TypeKind.ERROR`, round policy |
| Gọi `getTypeElement("List<String>")` | API tìm **khai báo class**, không tìm parameterized use | `getTypeElement("java.util.List")` + `getDeclaredType` |
| Dùng erasure để quyết định toàn bộ generic compatibility | Erasure xóa thông tin type arguments | Chỉ erase khi đúng yêu cầu (ví dụ signature-level logic) |
| Nghĩ `getAllMembers` tự lọc quyền caller | Inheritance/membership không phải accessibility API cho mọi caller | Xem modifiers, package, JPMS và ngữ cảnh |
| Print lỗi bằng System.out | Mất vị trí source và cơ chế javac diagnostics | `Messager.printMessage` |

Một số nhiệm vụ **thực sự cần tên chuỗi**: sinh tên file, tạo source code, ghi log, so khớp tên annotation được cấu hình tường minh. Khi đó dùng `Name`, `getQualifiedName()` hoặc `getBinaryName()` phù hợp; chỉ tránh chuyển những phép **kiểm tra quan hệ kiểu** thành xử lý text.

## 12. Quy trình kiểm chứng processor ở compile time

Với ví dụ `@CheckReturn`, có thể kiểm chứng theo các bước:

1. Compile hai file annotation và processor thành `build/processor`.
2. Compile `App.java` với đủ cả `-cp`, `-processorpath` và `-processor`; xác nhận processor không chặn `String` và `StringBuilder`.
3. Chạy `java -cp build/classes demo.App`; xác nhận hai dòng `ready`, `built`.
4. Compile `BadApp.java` riêng; xác nhận **compile thất bại** và có diagnostic do processor tạo cho return type `Object`.
5. Thử một method trả về interface implementation khác `String`, để xác minh processor không phụ thuộc tên type.
6. Thử `void`, primitive hoặc declared type chưa resolve để quan sát policy; so sánh kết quả với `TypeKind` và `isAssignable`.
7. Với generic method hoặc inherited members, dùng `Types.asMemberOf` và các quan hệ kiểu để kiểm tra signature sau substitution.
8. Kiểm tra trên clean build/CI: processor artifacts phải được build trước, processorpath và compile classpath đúng, không lấy output cũ.

**Đọc log compiler đúng:** khi `BadApp` bị từ chối, đó là một lỗi **do annotation processor phát ra bằng Messager** trong quá trình biên dịch. Không cần và không thể chạy `BadApp` để tái hiện lỗi ấy. Đừng khẳng định stderr có đúng số dòng cố định vì output của `javac` khác theo môi trường.

## 13. Gắn với Gradle/Maven mà không đánh tráo vai trò dependency

Trong dự án thật, processor thường nằm ở artifact riêng với annotation/API để tránh kéo implementation vào runtime của ứng dụng.

Với Gradle, ý tưởng cấu hình dependency là:

~~~groovy
dependencies {
    compileOnly project(':annotations')
    annotationProcessor project(':processor')
}
~~~

Đây là **fragment minh họa**, cần có các subprojects `annotations` và `processor` tương ứng, và processor artifact phải nhìn thấy annotation API của nó. Khi annotation cũng cần ở runtime, chọn scope phù hợp thực tế thay vì mặc định compileOnly.

Với Maven, processor được khai báo qua cấu hình Maven Compiler Plugin/annotation processor paths phù hợp với plugin version và JDK. Không thay thế processor path bằng runtime dependency một cách ngẫu nhiên. Processor code dùng `javax.lang.model` trong JDK module `java.compiler`; nó không phải API reflection đọc class đã load.

Khi muốn package processor tự động được phát hiện, cung cấp đúng service provider declaration hoặc cơ chế khai báo processor được toolchain hỗ trợ. Ví dụ `-processor` tường minh trong bài này có chủ đích để tránh phụ thuộc service discovery, đồng thời giúp học viên thấy chính xác processor nào chạy.

## 14. Checklist: quyết định nào phải dựa trên language model?

Hãy kiểm tra lần lượt trước khi xuất một chẩn đoán từ processor:

- **Tôi đang xem khai báo hay kiểu?** Nếu là khai báo, dùng `Element`; nếu là quan hệ/type arguments, dùng `TypeMirror` và `Types`.
- **Tên có thể lookup duy nhất không?** `getTypeElement` có thể trả null; trên module system có overload theo module.
- **TypeKind đã đúng chưa?** `DeclaredType`, array, type variable, wildcard, error, void và primitive không thể cast chung một kiểu.
- **Tôi muốn kiểm tra giống hệt, subtype hay assignable?** Chọn `isSameType`, `isSubtype` hoặc `isAssignable` đúng ngữ nghĩa và đúng hướng tham số.
- **Tôi có làm mất thông tin generic không?** Tránh `erasure` khi type arguments quan trọng; dùng `getTypeArguments`, `capture` hoặc `asMemberOf` khi phù hợp.
- **Tôi có tự đoán override/method signature không?** Dùng `Elements.overrides` hoặc các method của `Types`.
- **Một kiểu chưa resolve có bị kết luận oan không?** Xử lý `ErrorType` và processing rounds theo chính sách rõ ràng.
- **Diagnostic có gắn đúng element không?** `Messager` tốt hơn in console khi muốn người dùng định vị lỗi.
- **Bài toán thật sự cần text hay ngữ nghĩa?** Text dành cho hiển thị và tên output; quan hệ kiểu dành cho language model APIs.

**Kết luận:** `Elements` giúp tìm đúng *khai báo Java* và quan hệ giữa các khai báo; `Types` giúp hỏi đúng *quan hệ của các kiểu Java*. `TypeMirror.toString()` chỉ là biểu diễn hỗ trợ chẩn đoán, không phải bộ phân tích cú pháp hay cơ sở để định nghĩa tương thích kiểu. Xây processor dựa trên hai utilities này giúp code đúng với generics, inheritance, nested types và compiler rounds, đồng thời tránh báo lỗi sai khi người dùng đổi cách viết type nhưng giữ nguyên ngữ nghĩa.

## Tài liệu tham khảo

- [Java SE 17: Elements API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html).
- [Java SE 17: Types API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html).
- [Java SE 17: ProcessingEnvironment API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html).
- [Java SE 17: TypeMirror và TypeKind](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html).
