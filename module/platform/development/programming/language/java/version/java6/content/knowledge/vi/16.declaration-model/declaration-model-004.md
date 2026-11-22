# Phân biệt phần tử khai báo với kiểu của phần tử trong Java Language Model

## 1. Vì sao phải phân biệt?

Khi viết annotation processor hay công cụ phân tích Java bằng API chuẩn `javax.lang.model`, một sai lầm phổ biến là nghĩ rằng **“phần tử được khai báo”** và **“kiểu của phần tử”** là cùng một đối tượng. Thực tế Java tách hai lớp thông tin:

- **`Element` (phần tử khai báo):** đại diện cho một thành phần của chương trình như package, module, class, interface, record, method, constructor, field, parameter hoặc type parameter. Bạn hỏi: *“Nó được khai báo ở đâu, tên là gì, loại khai báo nào, modifier gì, thành viên nào?”*
- **`TypeMirror` (kiểu):** đại diện cho một kiểu Java, ví dụ `int`, `String`, `List<String>`, `T`, `String[]`, `? extends Number` hoặc kiểu chữ ký của một phương thức. Bạn hỏi: *“Kiểu đó là gì, có tham số hóa không, có tương thích với kiểu khác không, được sử dụng trong ngữ cảnh nào?”*

Phần tử không phải object `java.lang.reflect.*` tại runtime. Cả `Element` lẫn `TypeMirror` đều thuộc **mô hình tại thời điểm biên dịch**; chúng không yêu cầu class mục tiêu đã được nạp thành `Class<?>` trong JVM của ứng dụng. Điều này rất quan trọng khi xử lý source đang biên dịch, class từ dependency, generic, các phần tử được tạo qua annotation processing hoặc class chưa có bytecode.

**Nguyên tắc:** Lấy khai báo để đọc tên, kind, modifiers, thành viên và annotation gắn với **khai báo**; lấy kiểu để đọc generic arguments, kiểu trả về/kiểu biến, tính assignable/subtype và annotation gắn với **chỗ dùng kiểu**. Hai mô hình liên quan nhưng không hoán đổi cho nhau.

## 2. Bảng so sánh ngắn

| Câu hỏi | API chính | Ví dụ kết quả |
| --- | --- | --- |
| “Đây là khai báo field hay method?” | `Element.getKind()` → `ElementKind` | `FIELD`, `METHOD` |
| “Class nào được khai báo?” | `TypeElement`, `getQualifiedName()` | `demo.Box` |
| “Field `items` có kiểu gì?” | `VariableElement.asType()` → `TypeMirror` | `java.util.List<java.lang.String>` |
| “Kiểu này là kiểu khai báo có generic args?” | `TypeMirror.getKind()` → `TypeKind`, `DeclaredType` | `DECLARED`, args `String` |
| “`Box<String>` và `Box<Integer>` do class nào định nghĩa?” | `DeclaredType.asElement()` hoặc `Types.asElement(...)` | Cùng `TypeElement` của `demo.Box` |
| “Hai kiểu có thật sự là cùng kiểu?” | `Types.isSameType(t1, t2)` | `false` với `Box<String>` và `Box<Integer>` |
| “Method khai báo trả `T`, khi dùng trên `Box<String>` trả gì?” | `Types.asMemberOf(DeclaredType, Element)` | `java.lang.String` |
| “Method/constructor có chữ ký kiểu nào?” | `ExecutableElement.asType()` → `ExecutableType` | `EXECUTABLE` |
| “Method trả về loại nào?” | `ExecutableElement.getReturnType()` | `String`, `void`, `T`, ... |
| “Một khai báo type parameter tên gì?” | `TypeParameterElement`, `getSimpleName()` | `T` |
| “Kiểu của type parameter là loại gì?” | `TypeParameterElement.asType()` → `TypeVariable` | `TYPEVAR` |

Chú ý hai enum **khác nhau**: `ElementKind` mô tả *loại khai báo*; `TypeKind` mô tả *loại kiểu*. `ElementKind.METHOD` và `TypeKind.EXECUTABLE` không phải hai tên gọi thay thế tùy ý.

## 3. Ví dụ generic: một khai báo, nhiều kiểu

Xét đoạn source **minh họa**, không chạy độc lập nếu không đặt trong file thích hợp:

~~~java
package demo;

class Box<T> {
    T get() {
        return null;
    }
}

class Example {
    Box<String> textBox;
    Box<Integer> numberBox;
}
~~~

Trong compiler model:

- `TypeElement` của `demo.Box` đại diện cho **một khai báo** `class Box<T>`. Có thể tìm nó qua `Elements.getTypeElement("demo.Box")`.
- `boxElement.asType()` thường cho **kiểu nguyên mẫu** `demo.Box<T>`. Đối với generic declaration, API trả kiểu với chính các **type variables** tương ứng tham số hình thức, chứ không tự chọn `String` hay `Integer`.
- `VariableElement` của `textBox` là **khai báo field**. `textBox.asType()` đại diện cho kiểu **được sử dụng tại field**: `demo.Box<java.lang.String>`.
- `VariableElement` của `numberBox` là **khai báo field khác** và mang kiểu `demo.Box<java.lang.Integer>`.
- Hai kiểu field này có cùng **declaration** `demo.Box` nhưng **khác type arguments**. Vì vậy không nên suy ra `Types.isSameType(...) == true` chỉ từ việc `Types.asElement(...)` trỏ tới cùng `TypeElement`.

Có thể hình dung:

~~~text
KHAI BÁO (Element):
TypeElement: demo.Box<T>                 (một định nghĩa)
    └── TypeParameterElement: T

CHỖ SỬ DỤNG (TypeMirror):
field textBox   → DeclaredType: Box<String>
field numberBox → DeclaredType: Box<Integer>
    └── mỗi DeclaredType liên hệ về TypeElement: demo.Box

Types.asElement(Box<String>) == Types.asElement(Box<Integer>)  → cùng khai báo
Types.isSameType(Box<String>, Box<Integer>)                    → false
~~~

`TypeMirror` biểu diễn **kiểu trong cấu trúc**, bao gồm type arguments, arrays, wildcards, primitive types và type variables; không chỉ là tên class. Đừng dùng `toString()` hoặc so sánh tên `Box` làm phép kiểm tra tương thích kiểu.

### Khác nhau giữa `TypeElement` và `DeclaredType`

Tài liệu Java phân biệt rất rõ: `TypeElement` đại diện cho declaration class/interface; `DeclaredType` đại diện cho **một cách sử dụng của declaration ấy** (có thể là raw type hoặc generic instantiation). Một `TypeElement` có thể ứng với nhiều `DeclaredType`.

Một field có thể trỏ về declaration qua:

~~~java
TypeMirror fieldType = field.asType();
if (fieldType.getKind() == TypeKind.DECLARED) {
    DeclaredType declared = (DeclaredType) fieldType;
    TypeElement declaration = (TypeElement) declared.asElement();
    List<? extends TypeMirror> args = declared.getTypeArguments();
    // declaration: class/interface gốc; args: các đối số kiểu thực tế.
}
~~~

Đây là **đoạn dùng bên trong processor** với `field` là `VariableElement`; cần import `List`, `DeclaredType`, `TypeKind`. Chỉ ép kiểu thành `DeclaredType` sau khi xác minh kind thích hợp. Với field kiểu `int`, `String[]` hoặc `T`, nhánh chuyển trực tiếp này không áp dụng.

## 4. `asType()` không có cùng ý nghĩa cụ thể ở mọi `Element`

`Element.asType()` là điểm nối chung, nhưng kiểu trả về có thể khác nhau theo subtype của phần tử:

| Phần tử | `ElementKind` điển hình | `asType()` |
| --- | --- | --- |
| `TypeElement` của class/interface/record | `CLASS`, `INTERFACE`, `RECORD` | Kiểu class/interface được khai báo; với generic là kiểu **nguyên mẫu** như `Box<T>` |
| `VariableElement` của field | `FIELD` | Kiểu khai báo của field, chẳng hạn `List<String>` hoặc `int` |
| `VariableElement` của parameter | `PARAMETER` | Kiểu parameter, chẳng hạn `int` |
| `TypeParameterElement` | `TYPE_PARAMETER` | `TypeVariable`, `TypeKind.TYPEVAR` |
| `ExecutableElement` của method | `METHOD` | `ExecutableType`, có kiểu parameter/return/throws... |
| `ExecutableElement` của constructor | `CONSTRUCTOR` | `ExecutableType` cho chữ ký constructor |
| `RecordComponentElement` | `RECORD_COMPONENT` | Kiểu của record component |
| `PackageElement` / `ModuleElement` | `PACKAGE` / `MODULE` | Các pseudo-type `NoType` với kind tương ứng |

**Bẫy quan trọng:**

~~~java
ExecutableElement method = /* method element trong processor */;

TypeMirror signature = method.asType();       // ExecutableType, kind EXECUTABLE
TypeMirror returnType = method.getReturnType(); // Kiểu trả về, ví dụ String
List<? extends VariableElement> params = method.getParameters();
~~~

Đây là **mã minh họa**, không phải file biên dịch riêng. Nếu cần signature với parameters/throws, bạn có thể ép `signature` sang `ExecutableType` sau khi xác minh kind; hoặc lấy `getParameters()` và `getReturnType()` để xem khai báo.

Đừng hiểu `method.asType()` là “kiểu trả về”. Với method trả `void`, `getReturnType()` có kind `VOID`; với constructor, API cung cấp quy ước khác cho `getReturnType()`, vì vậy nên xét subtype/hợp đồng cụ thể chứ không suy diễn từ method thông thường.

## 5. Chuyển giữa khai báo và kiểu bằng `Elements`, `Types`

### `Elements`: thao tác với khai báo

`ProcessingEnvironment.getElementUtils()` cung cấp tiện ích `Elements`, chẳng hạn:

- `getTypeElement("java.util.List")`: tìm **khai báo** của kiểu có tên đầy đủ (hoặc `null` nếu không tìm thấy trong ngữ cảnh).
- `getPackageElement(...)`, `getModuleElement(...)`: tìm khai báo package/module.
- `getAllMembers(TypeElement)`: xem cả các member kế thừa (khác `getEnclosedElements()` chỉ liệt kê thành viên trực tiếp bên trong khai báo).
- `overrides(...)`, `hides(...)`: phân tích quan hệ giữa **các khai báo member** trong ngữ cảnh thích hợp.

`Element.getSimpleName()` và `Element.getEnclosingElement()` cho biết tên và cha lexical của khai báo. `TypeElement.getQualifiedName()` thường thích hợp khi tạo generated source hoặc mô tả một class trong diagnostics. Không dùng `String.valueOf(element)` như đại diện cấu trúc cho mọi thuộc tính.

### `Types`: thao tác với kiểu

`ProcessingEnvironment.getTypeUtils()` cung cấp `Types`, gồm:

- `isSameType(t1, t2)`: kiểm tra cùng kiểu theo Java type model.
- `isAssignable(from, to)`: một kiểu có thể gán sang kiểu kia không.
- `isSubtype(sub, sup)`: quan hệ subtype.
- `erasure(type)`: xóa tham số kiểu khi thuật toán cần xét erased type; **không** áp dụng erasure nếu mục đích là phân biệt generic arguments.
- `getDeclaredType(typeElement, typeArgs...)`: tạo một cách dùng kiểu generic từ declaration và các đối số cụ thể.
- `asMemberOf(containingDeclaredType, memberElement)`: lấy kiểu của member **khi nhìn từ một kiểu chứa đã tham số hóa**.
- `asElement(typeMirror)`: chuyển ngược những loại kiểu có declaration tương ứng về một `Element`.

Không lấy `TypeMirror.equals` hoặc `==` làm cách so sánh kiểu chính. API không đảm bảo một kiểu luôn được biểu diễn bởi cùng một object `TypeMirror`. Dùng `Types.isSameType(...)`, nhớ rằng trường hợp wildcard có các quy tắc riêng; `Types.isSameType(wildcard, wildcard)` có thể trả `false` theo hợp đồng API.

### `Types.asElement` không luôn trả một element

`Types.asElement(TypeMirror)` hỗ trợ các kiểu có phần tử tương ứng, chẳng hạn `DeclaredType`, `TypeVariable`, pseudo-types cho package/module. Nó có thể trả **`null`** cho primitive types, array types, executable types, `void`, wildcard, null type hoặc `NONE`. Không viết:

~~~java
TypeElement name = (TypeElement) processingEnv.getTypeUtils()
        .asElement(variable.asType());
~~~

rồi giả định luôn thành công. Đây là **đoạn minh họa lỗi**: với field `int count`, `Types.asElement` trả `null`; với `T`, element (nếu có) là `TypeParameterElement`, không phải `TypeElement`.

Cách đúng là phân nhánh theo `TypeKind` rồi mới ép subtype thích hợp:

~~~java
TypeMirror type = variable.asType();

switch (type.getKind()) {
    case DECLARED -> {
        DeclaredType declared = (DeclaredType) type;
        TypeElement element = (TypeElement) declared.asElement();
        // Xử lý khai báo class/interface và các đối số kiểu.
    }
    case ARRAY -> {
        ArrayType array = (ArrayType) type;
        TypeMirror component = array.getComponentType();
        // Tiếp tục xét componentType; bản thân array không phải TypeElement.
    }
    case INT, BOOLEAN, LONG, DOUBLE -> {
        // Primitive types: không có TypeElement tương ứng.
    }
    default -> {
        // TYPEVAR, WILDCARD, ERROR, ... cần xử lý riêng.
    }
}
~~~

Đây là **mã minh họa trong processor** với `variable` là `VariableElement`, cần import `ArrayType`, `DeclaredType`, `TypeElement`, `TypeMirror`. Switch này cố ý chỉ biểu diễn một số primitive cases; processor thực phải xử lý tất cả kind phù hợp (ví dụ `BYTE`, `SHORT`, `CHAR`, `FLOAT`) hoặc dùng visitor.

## 6. Generic trong ngữ cảnh: vì sao `Types.asMemberOf()` quan trọng?

Quay lại class:

~~~java
class Box<T> {
    T get() { return null; }
}
Box<String> textBox;
~~~

Đây là source minh họa. Có **một `ExecutableElement`** cho khai báo method `get()` ở class `Box<T>`. Nếu lấy `getElement.getReturnType()` theo khai báo, kết quả là type variable `T` (`TYPEVAR`).

Nhưng khi nhìn method `get()` như thành viên của `Box<String>`, kiểu trả về về mặt type system phải là `String`, không phải chữ `T` trừu tượng. `Types.asMemberOf` giải quyết đúng sự thay thế này:

~~~java
Types types = processingEnv.getTypeUtils();
DeclaredType boxString = (DeclaredType) textBox.asType();
ExecutableElement getMethod = /* method get() khai báo trong Box<T> */;

TypeMirror declaredReturn = getMethod.getReturnType(); // T
ExecutableType specializedMethod =
        (ExecutableType) types.asMemberOf(boxString, getMethod);
TypeMirror actualReturn = specializedMethod.getReturnType(); // java.lang.String
~~~

Đây là **đoạn minh họa trong processor**, không phải file độc lập. Nếu chỉ đọc `getReturnType()` trên khai báo mà không tính context, annotation processor có thể generate method sai kiểu hoặc đánh giá validation không đúng với generic instantiation đang xét.

Các cách tiếp cận liên quan nhưng **khác nhiệm vụ**:

- `TypeElement.asType()` → nguyên mẫu của `Box<T>`.
- `VariableElement.asType()` ở field `textBox` → kiểu `Box<String>`.
- `ExecutableElement.getReturnType()` của `Box.get` → `T` tại declaration.
- `Types.asMemberOf(Box<String>, Box.get)` → một `ExecutableType` mà return type là `String` trong context đó.
- `Types.erasure(Box<String>)` → dạng đã xóa generic, **mất** type argument; không dùng để xác thực sự khác nhau giữa `Box<String>` và `Box<Integer>`.

## 7. Chương trình Java 17+ hoàn chỉnh: quan sát `Element` và `TypeMirror`

Để kiểm chứng, chương trình sau chạy một **annotation processor ngay trong Java Compiler API**. Nó không cần đóng gói processor JAR riêng: main tạo `JavaCompiler.CompilationTask`, gọi `setProcessors(...)` và chỉ định source string bằng `SimpleJavaFileObject`.

Mã nguồn cần phân tích chứa `Box<T>`, hai field dùng generic instantiations khác nhau, method `label` với parameter `int`. Processor quan sát `ElementKind`, `TypeKind`, `Types.asElement`, `Types.isSameType` và `Types.asMemberOf`. Vì sử dụng `-proc:only`, ví dụ tập trung vào **annotation processing** chứ không sinh output `.class` của `demo.Order`.

Tạo tệp **`ElementVsTypeDemo.java`** với **toàn bộ** nội dung:

~~~java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.lang.model.type.*;
import javax.lang.model.util.ElementFilter;
import javax.lang.model.util.Types;
import javax.tools.*;

public final class ElementVsTypeDemo {
    static final class Source extends SimpleJavaFileObject {
        Source() { super(URI.create("string:///demo/Order.java"), Kind.SOURCE); }
        @Override public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return """
                    package demo;
                    class Box<T> { T get() { return null; } }
                    @Deprecated
                    public final class Order {
                        private Box<String> textBox;
                        private Box<Integer> numberBox;
                        public String label(int count) { return "ok"; }
                    }
                    """;
        }
    }

    @SupportedAnnotationTypes("*")
    @SupportedSourceVersion(SourceVersion.RELEASE_17)
    public static final class InspectProcessor extends AbstractProcessor {
        final List<String> lines = new ArrayList<>();
        @Override public boolean process(Set<? extends TypeElement> annotations,
                                         RoundEnvironment round) {
            if (round.processingOver() || !lines.isEmpty()) return false;
            TypeElement box = processingEnv.getElementUtils().getTypeElement("demo.Box");
            TypeElement order = processingEnv.getElementUtils().getTypeElement("demo.Order");
            if (box == null || order == null) return false;
            VariableElement textBox = ElementFilter.fieldsIn(order.getEnclosedElements())
                    .stream().filter(e -> e.getSimpleName().contentEquals("textBox"))
                    .findFirst().orElseThrow();
            VariableElement numberBox = ElementFilter.fieldsIn(order.getEnclosedElements())
                    .stream().filter(e -> e.getSimpleName().contentEquals("numberBox"))
                    .findFirst().orElseThrow();
            ExecutableElement label = ElementFilter.methodsIn(order.getEnclosedElements())
                    .stream().filter(e -> e.getSimpleName().contentEquals("label"))
                    .findFirst().orElseThrow();
            ExecutableElement get = ElementFilter.methodsIn(box.getEnclosedElements())
                    .stream().filter(e -> e.getSimpleName().contentEquals("get"))
                    .findFirst().orElseThrow();
            Types types = processingEnv.getTypeUtils();
            TypeMirror textType = textBox.asType();
            TypeMirror numberType = numberBox.asType();
            DeclaredType textDeclared = (DeclaredType) textType;
            ExecutableType getInTextBox = (ExecutableType) types.asMemberOf(textDeclared, get);

            lines.add("box element: " + box.getQualifiedName() + " / " + box.getKind());
            lines.add("box asType: " + box.asType() + " / " + box.asType().getKind());
            lines.add("type parameter: " + box.getTypeParameters().get(0).getSimpleName()
                    + " / " + box.getTypeParameters().get(0).getKind());
            lines.add("type parameter asType: " + box.getTypeParameters().get(0).asType().getKind());
            lines.add("field element: " + textBox.getSimpleName() + " / " + textBox.getKind());
            lines.add("field type: " + textType + " / " + textType.getKind());
            lines.add("field type argument: " + textDeclared.getTypeArguments().get(0));
            lines.add("other field type: " + numberType);
            lines.add("same declaration: "
                    + types.asElement(textType).equals(types.asElement(numberType)));
            lines.add("same full type: " + types.isSameType(textType, numberType));
            lines.add("get declared return: " + get.getReturnType()
                    + " / " + get.getReturnType().getKind());
            lines.add("get in Box<String>: " + getInTextBox.getReturnType()
                    + " / " + getInTextBox.getReturnType().getKind());
            lines.add("method element: " + label.getSimpleName() + " / " + label.getKind());
            lines.add("method asType kind: " + label.asType().getKind());
            lines.add("method return: " + label.getReturnType()
                    + " / " + label.getReturnType().getKind());
            VariableElement count = label.getParameters().get(0);
            lines.add("parameter: " + count.getSimpleName()
                    + " / " + count.getKind() + " / " + count.asType().getKind());
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK compiler required");
        InspectProcessor inspector = new InspectProcessor();
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager fm = compiler.getStandardFileManager(
                diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, fm, diagnostics,
                    List.of("--release", "17", "-proc:only"), null, List.of(new Source()));
            task.setProcessors(List.of(inspector));
            boolean ok = Boolean.TRUE.equals(task.call());
            System.out.println("task success: " + ok);
            for (String line : inspector.lines) System.out.println(line);
            if (!ok || inspector.lines.isEmpty())
                throw new IllegalStateException(diagnostics.getDiagnostics().toString());
        }
    }
}
~~~

Với JDK **17+** có compiler, chạy từ thư mục chứa file:

~~~bash
javac --release 17 ElementVsTypeDemo.java
java ElementVsTypeDemo
~~~

**Stdout chính xác** của ví dụ (kiểm tra trên OpenJDK 24 với `--release 17`):

~~~text
task success: true
box element: demo.Box / CLASS
box asType: demo.Box<T> / DECLARED
type parameter: T / TYPE_PARAMETER
type parameter asType: TYPEVAR
field element: textBox / FIELD
field type: demo.Box<java.lang.String> / DECLARED
field type argument: java.lang.String
other field type: demo.Box<java.lang.Integer>
same declaration: true
same full type: false
get declared return: T / TYPEVAR
get in Box<String>: java.lang.String / DECLARED
method element: label / METHOD
method asType kind: EXECUTABLE
method return: java.lang.String / DECLARED
parameter: count / PARAMETER / INT
~~~

### Giải thích kết quả theo từng nhóm

1. `box element: demo.Box / CLASS` là **khai báo** class. `box asType: demo.Box<T> / DECLARED` là kiểu nguyên mẫu của class generic, không phải `Box<String>`.
2. `T / TYPE_PARAMETER` thuộc **ElementKind**, trong khi `TYPEVAR` là **TypeKind** của kiểu tương ứng.
3. `textBox / FIELD` đại diện khai báo field; `demo.Box<java.lang.String> / DECLARED` đại diện kiểu field đó. `String` nằm trong `getTypeArguments()` của `DeclaredType`.
4. Hai field chứa `Box<String>` và `Box<Integer>` cùng trỏ đến khai báo `demo.Box`; `Types.isSameType` vẫn trả `false` vì type arguments khác nhau.
5. `get declared return: T / TYPEVAR` cho method của declaration `Box<T>`. `get in Box<String>: java.lang.String / DECLARED` minh họa phép thay thế `T → String` của `Types.asMemberOf`.
6. `label` là phần tử kind `METHOD`, nhưng `label.asType()` là `ExecutableType` kind `EXECUTABLE`, còn `label.getReturnType()` là `String` với kind `DECLARED`.
7. `count` là phần tử `PARAMETER` có kiểu primitive `int`, kind `INT`. Đối với primitive, `Types.asElement(count.asType())` không có một `TypeElement` class tương ứng.

`@Deprecated` trong source đóng vai trò annotation giúp vòng annotation processing có work rõ ràng; nó **không** phải yêu cầu sử dụng API lỗi thời. Demo chỉ quan sát model và không dùng thành phần Java đã legacy. `InspectProcessor` được truyền trực tiếp bằng `setProcessors` để không phụ thuộc service discovery trên processor path.

## 8. Annotation gắn với khai báo khác annotation gắn với chỗ dùng kiểu

`Element` và `TypeMirror` đều triển khai `AnnotatedConstruct`, nhưng **annotation được áp dụng vào declaration** và **annotation được áp dụng vào type use** có thể thuộc các vị trí khác nhau. Khi phân tích:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;
import java.util.List;

@Target(ElementType.FIELD)
@interface IndexedField {}

@Target(ElementType.TYPE_USE)
@interface NonNullUse {}

class Example {
    @IndexedField
    List<@NonNullUse String> values;
}
~~~

Đây là **đoạn minh họa riêng**, không đặt thêm vào file demo phần 7. Với `VariableElement` của `values`, annotation `@IndexedField` thuộc khai báo field, còn `@NonNullUse` nằm tại **type argument** `String` bên trong kiểu `List<...>`. Một processor muốn phát hiện `@NonNullUse` phải phân tích `DeclaredType.getTypeArguments()` và các type-use annotations trên `TypeMirror` thích hợp, không chỉ đọc `field.getAnnotationMirrors()` rồi cho rằng đã thấy mọi annotation trong chữ ký kiểu.

Tùy target của annotation và vị trí cú pháp, một annotation có thể áp dụng ở declaration, type-use hoặc cả hai. Hãy dựa vào `@Target` và mô hình vị trí, không lấy `getAnnotationMirrors()` trên một đối tượng bất kỳ làm toàn bộ câu trả lời. Với các cấu trúc nested types, arrays hoặc wildcards, cần đi qua type structure (ví dụ `TypeVisitor`) để tìm annotation ở đúng cấp.

## 9. Phạm vi và những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `TypeElement` để biểu diễn `Box<String>` | Mất thông tin `String` | Giữ `DeclaredType` và `getTypeArguments()` |
| Dùng `element.asType()` rồi ép ngay sang `DeclaredType` | Sai với method, primitive, array, type variable, ... | Kiểm tra `TypeKind`/subtype trước khi ép |
| Xem `method.asType()` là kiểu trả về | Nhận `ExecutableType` thay vì `String`/`T` | Dùng `getReturnType()` hoặc `ExecutableType.getReturnType()` |
| Dùng `getReturnType()` khai báo generic trong mọi context | Không áp dụng phép thay thế `T` → `String` | Dùng `Types.asMemberOf(...)` khi xét member trên receiver đã parameterize |
| Gọi `Types.asElement(intType)` và dùng kết quả như class | `null` hoặc ép sai | `int` là `PrimitiveType`, không có `TypeElement` |
| So sánh `TypeMirror` bằng `==`, `equals` hay `toString()` | Đối chiếu sai/không portable | `Types.isSameType`, `isAssignable`, `isSubtype` |
| Dùng `Types.erasure` rồi so generic types | Mất đối số kiểu | So full type trước, chỉ erasure khi thuật toán yêu cầu |
| Nghĩ `getEnclosedElements()` bao gồm mọi member kế thừa | Bỏ sót members từ superclass/interface | `Elements.getAllMembers(...)` khi cần xét cả kế thừa |
| Dùng reflection `Class<?>` để phân tích source chưa compile | Không thể nạp khai báo chưa có bytecode | Dùng `Element`/`TypeMirror` trong `AnnotationProcessor` |
| Lấy annotation từ field `Element` và bỏ qua type args | Bỏ sót type-use annotations | Duyệt `TypeMirror` tương ứng |
| Giữ `Element`/`TypeMirror` vào cache lâu dài giữa nhiều build | Dựa vào model phụ thuộc ngữ cảnh compilation/processor | Chỉ dùng trong scope xử lý hiện tại; lưu định danh/metadata ổn định nếu cần |
| Xử lý type đang thiếu ngay như `DeclaredType` hoàn chỉnh | Vấp `ErrorType` ở các round có generated source chưa hiện diện | Nhận diện `TypeKind.ERROR`, báo/hoãn xử lý khi phù hợp |

### Không nhầm compile-time type với runtime class

- `java.lang.Class<?>` mô tả runtime class đã nạp; nó không giữ toàn bộ tham số generic ở mỗi **chỗ dùng** như `Box<String>` so với `Box<Integer>`.
- `TypeMirror` mô tả Java types trong compiler model, không phải đối tượng của chương trình được compile; không tạo instance bằng cách cast từ `TypeMirror` sang `Class<?>`.
- `Element` mô tả declaration tồn tại trong source hoặc classpath/module path mà compiler nhìn thấy. Cách tra cứu và những gì sẵn có phụ thuộc compilation environment; không tự coi nó là API reflection runtime.

### Chọn `Visitor` khi cần duyệt nhiều kind

Trong công cụ chung, `ElementVisitor` và `TypeVisitor` giúp xử lý các subtype có cấu trúc khác nhau. Thay vì viết một chuỗi ép kiểu không kiểm soát, hãy kiểm tra `getKind()`, dùng `ElementFilter` khi đã có danh sách element, hoặc visitor/`SimpleTypeVisitor` khi cần xử lý nhiều `TypeKind`. Khi gặp `ErrorType` (ký hiệu chưa giải quyết), `WildcardType`, `ArrayType`, `IntersectionType`, `UnionType` hoặc `ExecutableType`, cách duyệt phải phản ánh cấu trúc riêng của từng loại.

## 10. Quy trình thực hành khi viết annotation processor

1. **Bắt đầu từ khai báo:** `RoundEnvironment.getElementsAnnotatedWith(...)`, `Elements.getTypeElement(...)`, `TypeElement.getEnclosedElements()` hoặc `Elements.getAllMembers(...)`. Lấy `ElementKind` đúng để biết đang xử lý loại declaration nào.
2. **Đi vào kiểu tại nơi cần:** Với field/parameter → `VariableElement.asType()`; với method → `ExecutableElement.getReturnType()` và `getParameters()`; với generic receiver → `Types.asMemberOf(...)`.
3. **Duy trì type structure:** Trên `DeclaredType`, đọc type arguments; trên `ArrayType`, đọc component; trên `TypeVariable`, đọc bounds; trên `ExecutableType`, đọc parameters/return/throws.
4. **So sánh bằng `Types`:** `isSameType`, `isAssignable`, `isSubtype` theo đúng mục đích. Đừng so sánh simple name hoặc lạm dụng erasure.
5. **Tách annotation location:** Declaration annotations trên `Element`; type-use annotations trên type mirror đúng cấp.
6. **Trả diagnostic hoặc generate code dựa vào model đã xác minh:** `Messager`/`Filer` của annotation processor; đặc biệt kiểm tra tình huống type chưa resolve và nhiều processing round.
7. **Không lưu model objects vượt compilation:** Nếu cần build cache, lưu thông tin phù hợp (qualified name, output mapping, input fingerprints,...) thay vì giữ object model do compiler quản lý.

## 11. Tự kiểm tra

1. **`TypeElement` cho `List` có đại diện riêng `List<String>` và `List<Integer>` không?** Không. Nó là khai báo; mỗi cách dùng tham số hóa là `DeclaredType` khác nhau.
2. **`ElementKind.FIELD` khác `TypeKind.DECLARED` ở đâu?** Cái đầu là loại khai báo, cái sau là loại kiểu của một chỗ dùng.
3. **`TypeParameterElement.asType()` của `T` là loại gì?** `TypeVariable`, `TypeKind.TYPEVAR`.
4. **Vì sao `ExecutableElement.asType()` không thể thay `getReturnType()`?** Vì nó trả `ExecutableType` của toàn chữ ký, không phải chỉ return type.
5. **Nếu method `Box<T>.get()` trả `T`, kết quả khi xét `Box<String>` là gì?** Dùng `Types.asMemberOf(...)` sẽ cho `String` ở return type.
6. **`Types.asElement(type)` có luôn trả `TypeElement`?** Không. Một số kind trả `null`; `TypeVariable` có thể trỏ tới `TypeParameterElement`.
7. **`Box<String>` và `Box<Integer>` có cùng khai báo không? Có là cùng kiểu không?** Cùng `Box` declaration; khác full types.
8. **Muốn lấy tất cả method có cả inherited methods, chỉ `getEnclosedElements()` đủ không?** Không; cân nhắc `Elements.getAllMembers(...)`.
9. **Muốn đọc `@NonNullUse` nằm trên `String` trong `List<@NonNullUse String>`?** Duyệt type argument trên `DeclaredType` và annotation của type mirror đó.
10. **Có nên dùng `TypeMirror.equals()` để kiểm tra generic type equality không?** Không; dùng `Types.isSameType` với đúng ngữ cảnh/type kind.

## 12. Tài liệu API chính thức, còn áp dụng

- [Java SE 25 — `Element`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/Element.html), [`ElementKind`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/ElementKind.html): định nghĩa declaration và kind.
- [Java SE 25 — `TypeElement`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/TypeElement.html): sự khác biệt rõ giữa class declaration và declared type, nguyên mẫu `Box<T>`.
- [Java SE 25 — `TypeMirror`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html), [`TypeKind`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/type/TypeKind.html): mô hình kiểu và các kind.
- [Java SE 25 — `DeclaredType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/type/DeclaredType.html), [`ExecutableType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/type/ExecutableType.html): generic instantiations và kiểu của method/constructor.
- [Java SE 25 — `ExecutableElement`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/ExecutableElement.html), [`VariableElement`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/element/VariableElement.html): đọc thành viên, phương thức và kiểu return/parameter.
- [Java SE 25 — `Elements`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/util/Elements.html), [`Types`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/lang/model/util/Types.html): tiện ích khai báo, `asElement`, `isSameType` và `asMemberOf`.
- [Java SE 25 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html), [`RoundEnvironment`](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): ngữ cảnh dùng trong annotation processor.

**Nhớ ba câu hỏi riêng:** “*Đang xét khai báo nào?*” → `Element`. “*Kiểu nào được dùng ở đây?*” → `TypeMirror`. “*Quan hệ giữa hai kiểu hoặc member trong một generic context là gì?*” → `Types`. Phân biệt ba lớp này giúp annotation processor chính xác, đặc biệt với generic và các kiểu trong nhiều vị trí khai báo/sử dụng.