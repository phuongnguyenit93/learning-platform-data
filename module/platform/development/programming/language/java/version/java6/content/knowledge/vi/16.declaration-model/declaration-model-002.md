# Element, TypeElement, ExecutableElement và VariableElement trong mô hình khai báo Java

## 1. Mục tiêu: đọc khai báo Java ngay tại thời điểm biên dịch

Annotation processor và các công cụ phân tích Java thường cần tìm class, method, field hoặc parameter khi source **chưa được tạo thành bytecode**. Reflection (`java.lang.reflect`) hoạt động trên class đã nạp, nên không thay thế được mô hình khai báo của compiler.

JDK cung cấp **Java Language Model API** trong module `java.compiler`, gồm:
- `javax.lang.model.element`: mô tả **khai báo** trong source/classfile/module, ví dụ package, class, method, parameter, field, annotation, type parameter.
- `javax.lang.model.type`: mô tả **kiểu dữ liệu** của những khai báo và lần sử dụng kiểu, ví dụ `int`, `String`, `List<String>`, array, type variable hoặc wildcard.
- `javax.lang.model.util`: cung cấp `Elements`, `Types`, `ElementFilter` giúp tìm kiếm, so sánh và lọc các đối tượng model.
- `javax.annotation.processing`: cung cấp `AbstractProcessor`, `RoundEnvironment`, `ProcessingEnvironment` để processor khám phá và xử lý model qua các round.

Bốn interface chính:

| Interface | Diễn giải | Ví dụ |
| --- | --- | --- |
| `Element` | Interface gốc biểu diễn một **phần tử khai báo** | Một class, field, method, parameter, package. |
| `TypeElement` | Khai báo kiểu class/interface/enum/annotation/record | `class Box<T>`, `interface Service`, `record Point`. |
| `ExecutableElement` | Khai báo method/constructor hoặc executable declaration theo model | `get()`, `Box(T value)`. |
| `VariableElement` | Khai báo field, parameter, enum constant hoặc loại biến phù hợp | `private T value`, parameter `U input`. |

Nhớ hai nguyên tắc: **Element mô tả nơi khai báo**, còn **TypeMirror mô tả kiểu**; và tất cả `TypeElement`/`ExecutableElement`/`VariableElement` đều là `Element` nhưng không phải mọi `Element` đều thuộc ba nhóm ấy.

## 2. Ví dụ ánh xạ source sang mô hình

Xét source Java 17+:

```java
package demo;

public class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }

    public <U> U echo(U input) {
        return input;
    }
}
```

Compiler biểu diễn:
- `Box` là **`TypeElement`**, `getKind() == ElementKind.CLASS`.
- `value` (field) là **`VariableElement`**, `getKind() == ElementKind.FIELD`.
- `Box(T value)` là **`ExecutableElement`**, `getKind() == ElementKind.CONSTRUCTOR`.
- `get` và `echo` là **`ExecutableElement`**, `getKind() == ElementKind.METHOD`.
- `value` (constructor parameter) và `input` (method parameter) đều là **`VariableElement`**, `getKind() == ElementKind.PARAMETER`, tách biệt với field có cùng tên.
- `T` và `U` **được khai báo bởi `TypeParameterElement`**; khi dùng làm type của field, parameter hoặc return, chúng được thể hiện dưới dạng `TypeMirror` thuộc type variable, **không phải `TypeElement`**.

Sơ đồ rút gọn:

```text
                        Element
                           |
          +----------------+----------------+
          |                |                |
      TypeElement     ExecutableElement  VariableElement
          |                |                |
     class/interface   method/constructor field/parameter
     enum/record       annotation member   enum constant
          |
     getEnclosedElements()
          |
    các khai báo trực tiếp

Các Element khác: PackageElement, ModuleElement,
TypeParameterElement, RecordComponentElement ...
```

**Bẫy thường gặp:** nếu processor lấy một `Element` từ `RoundEnvironment.getElementsAnnotatedWith(...)` rồi ép sang `TypeElement` mà không kiểm tra kind, nó sẽ lỗi khi annotation được đặt trên method hoặc field.

## 3. Element: giao diện chung cho mọi khai báo

`Element` cung cấp các thao tác nền tảng:

| API | Kết quả và cách dùng |
| --- | --- |
| `getKind()` | `ElementKind` phân loại khai báo. Nên kiểm tra trước khi cast. |
| `getSimpleName()` | Tên đơn giản; không phải tên duy nhất trong toàn dự án. |
| `getEnclosingElement()` | Phần tử chứa nó trực tiếp: parameter thuộc method; field thuộc class. |
| `getEnclosedElements()` | Các khai báo được bao trong element, **không phải toàn bộ member kế thừa**. |
| `getModifiers()` | Modifier như `PUBLIC`, `PRIVATE`, `STATIC`, `FINAL`… |
| `getAnnotationMirrors()` | Những annotation mirror phù hợp với model. |
| `asType()` | `TypeMirror` tương ứng, không phải `TypeElement`. |
| `accept(visitor, data)` | Điều hướng qua `ElementVisitor`. |

**`ElementKind`** là công cụ phân loại đáng tin:

| `ElementKind` | Loại model | Source điển hình |
| --- | --- | --- |
| `CLASS` | `TypeElement` | `class Foo {}` |
| `INTERFACE` | `TypeElement` | `interface Foo {}` |
| `ENUM` | `TypeElement` | `enum Mode { A }` |
| `ANNOTATION_TYPE` | `TypeElement` | `@interface Check {}` |
| `RECORD` | `TypeElement` | `record Point(int x) {}` |
| `METHOD` | `ExecutableElement` | `String name()` |
| `CONSTRUCTOR` | `ExecutableElement` | `Foo(int x)` |
| `FIELD` | `VariableElement` | `private int count;` |
| `PARAMETER` | `VariableElement` | `void run(int x)` |
| `ENUM_CONSTANT` | `VariableElement` | `Mode.A` |
| `TYPE_PARAMETER` | `TypeParameterElement` | `T` ở `class Box<T>` |
| `RECORD_COMPONENT` | `RecordComponentElement` | `int x` ở record `Point` |
| `PACKAGE` | `PackageElement` | `package demo;` |
| `MODULE` | `ModuleElement` | `module app { ... }` |

Đây là các kind phổ biến chứ không phải danh sách trọn vẹn. Mô hình hiện đại còn có các loại biến và initializer phù hợp từng ngữ cảnh. Đối với code tương thích Java 17+, đừng bỏ qua `RECORD` và `RECORD_COMPONENT`.

Một đoạn kiểm tra kiểu an toàn:

```java
Element element = /* được compiler/processor cung cấp */;

if (element instanceof TypeElement type) {
    System.out.println(type.getQualifiedName());
} else if (element.getKind() == ElementKind.METHOD) {
    ExecutableElement method = (ExecutableElement) element;
    System.out.println(method.getReturnType());
}
```

Đây là snippet trong phương thức có import `javax.lang.model.element.*`. Nếu dùng `instanceof TypeElement`, nó bao gồm class, interface, enum, record và annotation types, không chỉ `CLASS`.

## 4. TypeElement: class/interface/enum/record/annotation được khai báo

`TypeElement` kế thừa `Element`, dùng để quan sát một khai báo kiểu.

Các phương thức quan trọng:
- `getQualifiedName()`: tên đầy đủ của top-level/member type theo mô hình, ví dụ `demo.Box`; không giả định local/anonymous type có qualified name không rỗng.
- `getSimpleName()`: tên ngắn như `Box`.
- `getNestingKind()`: `TOP_LEVEL`, `MEMBER`, `LOCAL`, `ANONYMOUS`.
- `getTypeParameters()`: danh sách `TypeParameterElement` của kiểu generic, ví dụ `T` trong `Box<T>`.
- `getSuperclass()`: `TypeMirror` của superclass trực tiếp khi có.
- `getInterfaces()`: các `TypeMirror` của interface được khai báo trực tiếp.
- `getEnclosedElements()`: field, constructor, method, nested class… khai báo trực tiếp.
- `getRecordComponents()`: record components (`RecordComponentElement`), với kiểu record.
- `getPermittedSubclasses()`: `TypeMirror` của các kiểu được phép trong sealed hierarchy, khi phù hợp.

Ví dụ:

```java
package demo;

public sealed interface Shape permits Circle, Square {}

final class Circle implements Shape {}

final class Square implements Shape {}
```

Cả ba kiểu là `TypeElement`; `Shape.getKind()` là `INTERFACE`, còn `Shape.getPermittedSubclasses()` cung cấp các thông tin kiểu tương ứng (dạng `TypeMirror`), **không phải `List<TypeElement>`** để cast trực tiếp.

### 4.1. Tên đơn giản, qualified name và binary name

Với khai báo nested type:

```java
package demo;

public class Outer {
    public static class Inner {}
}
```

`Inner` là `TypeElement` có:
- Simple name: `Inner`.
- Qualified name: `demo.Outer.Inner`.
- Binary name thường dùng cho bytecode/class loader: `demo.Outer$Inner`.

Nếu cần binary name, sử dụng `Elements.getBinaryName(TypeElement)` thay vì tự sửa chuỗi qualified name. Điều này càng quan trọng với nested/local types hoặc khi sinh resource/class name.

### 4.2. Member trực tiếp khác member kế thừa

`getEnclosedElements()` chỉ phản ánh khai báo nằm trực tiếp bên trong type. Ví dụ class có `getName()` nhưng kế thừa `toString()` từ `Object`: không nên kỳ vọng `getEnclosedElements()` của class chứa khai báo `Object.toString()`. Nếu bài toán cần các member được kế thừa theo model, sử dụng `Elements.getAllMembers(type)`.

## 5. ExecutableElement: chữ ký method và constructor

`ExecutableElement` biểu diễn khai báo method/constructor và các executable declarations khác mà language model hỗ trợ.

| API | Ý nghĩa |
| --- | --- |
| `getParameters()` | `List<? extends VariableElement>` của tham số. |
| `getReturnType()` | `TypeMirror` của kiểu trả về. |
| `getThrownTypes()` | `TypeMirror` của các exception type trong `throws`. |
| `getTypeParameters()` | Các `TypeParameterElement` của method/constructor generic. |
| `isVarArgs()` | Có khai báo biến đối số (`...`) hay không. |
| `getDefaultValue()` | `AnnotationValue` default của member annotation type nếu có. |
| `getReceiverType()` | Receiver type trong các ngữ cảnh phù hợp. |
| `asType()` | `TypeMirror` của executable, thường thuộc `ExecutableType`. |

Ví dụ method generic:

```java
public <N extends Number> int convert(N input)
        throws IllegalArgumentException {
    return input.intValue();
}
```

Ở đây `convert` là `ExecutableElement`, `getReturnType()` biểu diễn primitive `int`, `getParameters()` chứa một `VariableElement input`, `getTypeParameters()` chứa một `TypeParameterElement N` và `getThrownTypes()` chứa kiểu `IllegalArgumentException`.

Constructor có kind `CONSTRUCTOR` dù cũng là `ExecutableElement`. Đừng suy luận loại chỉ bằng cách so sánh `getSimpleName()` với tên class; dùng `getKind()`. Với method annotation type:

```java
@interface Label {
    String value() default "ok";
}
```

`value()` là method-like executable declaration, `getDefaultValue()` trả mô hình `AnnotationValue` cho `"ok"`. Nó không phải field có tên `value`.

**Giới hạn của model:** `ExecutableElement` mô tả signature, annotations và modifiers, **không phải AST của mọi câu lệnh bên trong method body**. Muốn phân tích statement/expression phải dùng parser/compiler tree API thích hợp.

## 6. VariableElement: field, parameter và enum constant

Các kind phổ biến của `VariableElement`:
- `FIELD`: field khai báo trong class/interface.
- `PARAMETER`: parameter của method/constructor.
- `ENUM_CONSTANT`: enum constant.
- `LOCAL_VARIABLE`, `EXCEPTION_PARAMETER`, `RESOURCE_VARIABLE` và các trường hợp khác có thể được language model biểu diễn trong ngữ cảnh tương ứng.

Thường dùng:
- `getSimpleName()` để đọc tên khai báo.
- `asType()` để đọc **`TypeMirror` của kiểu**.
- `getModifiers()` để đọc thuộc tính visibility/final/static…
- `getEnclosingElement()` để xác định class hay executable chứa biến.
- `getConstantValue()` khi cần giá trị compile-time constant (nếu đủ điều kiện), nếu không trả `null`.

Ví dụ:

```java
public class Config {
    public static final int MAX = 12;
    public final int current;

    public Config(int current) {
        this.current = current;
    }
}
```

`MAX` là `VariableElement FIELD` có `getConstantValue()` trả `Integer` giá trị 12. Field `current` cũng là `FIELD` nhưng không phải compile-time constant nên `getConstantValue()` trả null, dù `final`. Tham số constructor `current` là một `VariableElement PARAMETER` **khác** field, dù tên giống nhau.

Không dùng `getConstantValue() == null` để kết luận một biến “chưa gán giá trị”: null ở đây phản ánh điều kiện *compile-time constant*, không phải phân tích definite assignment.

### RecordComponentElement khác VariableElement

`record Point(int x, int y) {}` là một `TypeElement` có kind `RECORD`. Hai thành phần `x`, `y` được mô hình hóa thành **`RecordComponentElement`** (lấy qua `TypeElement.getRecordComponents()`), không phải trực tiếp thành `VariableElement`. Compiler còn mô hình hóa field và accessor liên quan đến record, nhưng validator cho record component phải xử lý đúng loại khai báo riêng này.

## 7. Ví dụ đầy đủ Java 17+: compiler và processor đọc model

Chương trình sau không cần thư viện bên ngoài. Nó tạo source của `demo.Box<T>` trong bộ nhớ, yêu cầu `JavaCompiler` chạy một annotation processor và in tên/kind/type của các khai báo.

### 7.1. File ElementModelDemo.java

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class ElementModelDemo {
    @SupportedAnnotationTypes("*")
    @SupportedSourceVersion(SourceVersion.RELEASE_17)
    public static final class Inspector extends AbstractProcessor {
        private static String params(ExecutableElement e) {
            return e.getParameters().isEmpty()
                    ? "-"
                    : e.getParameters().stream()
                            .map(p -> p.asType().toString())
                            .collect(Collectors.joining(","));
        }

        @Override
        public boolean process(
                Set<? extends TypeElement> annotations,
                RoundEnvironment round) {

            if (round.processingOver()) {
                return false;
            }

            for (Element root : round.getRootElements()) {
                if (root.getKind() != ElementKind.CLASS) {
                    continue;
                }
                TypeElement type = (TypeElement) root;

                System.out.println("type=" + type.getQualifiedName()
                        + " kind=" + type.getKind());
                System.out.println("typeParams="
                        + type.getTypeParameters().stream()
                                .map(p -> p.getSimpleName().toString())
                                .collect(Collectors.joining(",")));

                List<String> lines = new ArrayList<>();
                for (Element child : type.getEnclosedElements()) {
                    if (child.getKind() == ElementKind.FIELD) {
                        VariableElement field = (VariableElement) child;
                        lines.add("field=" + field.getSimpleName()
                                + " type=" + field.asType());

                    } else if (child.getKind()
                            == ElementKind.CONSTRUCTOR) {
                        ExecutableElement constructor =
                                (ExecutableElement) child;
                        lines.add("constructor params="
                                + params(constructor));

                    } else if (child.getKind() == ElementKind.METHOD) {
                        ExecutableElement method =
                                (ExecutableElement) child;

                        String typeParams =
                                method.getTypeParameters().isEmpty()
                                ? "-"
                                : method.getTypeParameters().stream()
                                        .map(p -> p.getSimpleName().toString())
                                        .collect(Collectors.joining(","));

                        lines.add("method=" + method.getSimpleName()
                                + " return=" + method.getReturnType()
                                + " params=" + params(method)
                                + " typeParams=" + typeParams);
                    }
                }

                Collections.sort(lines);
                lines.forEach(System.out::println);
            }
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Use a JDK containing jdk.compiler");
        }

        String code = """
                package demo;
                public class Box<T> {
                    private final T value;
                    public Box(T value) {
                        this.value = value;
                    }
                    public T get() {
                        return value;
                    }
                    public <U> U echo(U input) {
                        return input;
                    }
                }
                """;

        JavaFileObject source = new SimpleJavaFileObject(
                URI.create("string:///demo/Box.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(
                    boolean ignoreEncodingErrors) {
                return code;
            }
        };

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, diagnostics,
                    List.of("--release", "17", "-proc:only"),
                    null, List.of(source));

            task.setProcessors(List.of(new Inspector()));
            boolean success = Boolean.TRUE.equals(task.call());
            System.out.println("success=" + success);

            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();
            System.out.println("errors=" + errors);
        }
    }
}
```

### 7.2. Chạy và kết quả

Lưu `ElementModelDemo.java` bằng UTF-8, dùng JDK 17 trở lên:

```bash
javac ElementModelDemo.java
java ElementModelDemo
```

Stdout chính xác với javac dùng trong thử nghiệm:

```text
type=demo.Box kind=CLASS
typeParams=T
constructor params=T
field=value type=T
method=echo return=U params=U typeParams=U
method=get return=T params=- typeParams=-
success=true
errors=0
```

Diễn giải:
1. `TypeElement.getQualifiedName()` cho `demo.Box` và kind `CLASS`.
2. `TypeElement.getTypeParameters()` chứa khai báo `T`.
3. Constructor và hai method được nhận diện bằng `ExecutableElement`; mỗi parameter qua `VariableElement.asType()`.
4. Field `value` là `VariableElement` kiểu `T`.
5. `echo` có type parameter riêng `U`, dùng cho return và parameter.
6. `-proc:only` chạy annotation processor mà không tạo output class cho `demo.Box`. Code chủ động đăng ký processor bằng `setProcessors`, không phụ thuộc SPI tự động.
7. Các dòng member được sắp xếp trước khi in. Đây là ví dụ output có kiểm soát; với compiler/model khác, chi tiết thành viên tổng hợp hoặc chuỗi `TypeMirror.toString()` có thể khác.

Tùy biến để học sâu: thử thêm `private int count`, method `void reset()` hoặc một generic method có `throws`, sau đó quan sát sự thay đổi của `getEnclosedElements()` và `ExecutableElement.getThrownTypes()`.

## 8. ElementFilter giúp xử lý field/method/constructor an toàn

Trong processor thực tế, `ElementFilter` tiện hơn việc lặp nhiều `if` và cast thủ công:

```java
void inspect(TypeElement type) {
    for (VariableElement field :
            ElementFilter.fieldsIn(type.getEnclosedElements())) {
        System.out.println("field: " + field.getSimpleName());
    }

    for (ExecutableElement method :
            ElementFilter.methodsIn(type.getEnclosedElements())) {
        System.out.println("method: " + method.getSimpleName());
    }

    for (ExecutableElement constructor :
            ElementFilter.constructorsIn(type.getEnclosedElements())) {
        System.out.println("constructor params: "
                + constructor.getParameters().size());
    }
}
```

Đây là **snippet trong class đã import `ElementFilter`, `TypeElement`, `VariableElement` và `ExecutableElement`**. Các method lọc trên chỉ phân loại *những elements đã cung cấp*, không tự lấy member inherited. Nếu bạn cần member kế thừa, gọi `Elements.getAllMembers(type)` trước rồi mới lọc.

## 9. Element và TypeMirror: đừng nhầm khai báo với kiểu sử dụng

Ví dụ class:

```java
class Holder {
    java.util.List<String> items;
}
```

Field `items` là `VariableElement`; `items.asType()` trả `TypeMirror` biểu diễn `List<String>`. Từ đó, nếu kind là declared type:

```java
TypeMirror mirror = field.asType();

if (mirror.getKind() == TypeKind.DECLARED) {
    DeclaredType declared = (DeclaredType) mirror;
    Element declaration = declared.asElement();

    if (declaration instanceof TypeElement type) {
        System.out.println(type.getQualifiedName());
    }
}
```

Đây là snippet trong annotation processor với biến `field` phù hợp và import `TypeMirror`, `TypeKind`, `DeclaredType`, `Element`, `TypeElement`. Khi `field` có type `java.util.List<String>`, khai báo của `List` có tên `java.util.List`; các type arguments cần đọc từ `DeclaredType.getTypeArguments()`, không xuất hiện trong `TypeElement.getQualifiedName()`.

Hai utility trung tâm:
- `ProcessingEnvironment.getElementUtils()` trả `Elements`, có `getTypeElement(...)`, `getBinaryName(...)`, `getAllMembers(...)` và nhiều thao tác khác.
- `ProcessingEnvironment.getTypeUtils()` trả `Types`, có `isSameType(...)`, `isAssignable(...)`, `isSubtype(...)`, `erasure(...)` và các phép toán kiểu khác.

Không so sánh kiểu chủ yếu bằng chuỗi `mirror.toString()`; trong phân tích generic/subtype chính xác, hãy dùng API `Types`.

## 10. Generic: TypeParameterElement khác TypeElement

Trong `class Box<T>`, `T` không đại diện cho một class khai báo độc lập như `Box`. Nó là **`TypeParameterElement`**. Khi `T` xuất hiện ở `private T value`, kiểu của field là `TypeVariable` (một `TypeMirror`).

Trong `public <U> U echo(U input)`:
- `ExecutableElement.getTypeParameters()` cho biết nơi khai báo type parameter `U`.
- `ExecutableElement.getReturnType()` biểu diễn kiểu dùng `U` ở return.
- `ExecutableElement.getParameters().get(0).asType()` biểu diễn kiểu dùng `U` ở parameter.

Nếu viết rule kiểm tra generic method, cần phân biệt **nơi khai báo** và **các vị trí dùng** type parameter; việc đọc mỗi `getSimpleName()` hoặc `getReturnType().toString()` không đủ để kiểm tra ràng buộc generic sâu.

## 11. Annotation processing và RoundEnvironment

Một annotation có thể gắn trên type, method, field hoặc parameter tùy `@Target`. Processor dùng `RoundEnvironment` để tìm:

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment round) {

    if (round.processingOver()) {
        return false;
    }

    for (TypeElement annotation : annotations) {
        for (Element element :
                round.getElementsAnnotatedWith(annotation)) {
            if (element.getKind() == ElementKind.METHOD) {
                ExecutableElement method =
                        (ExecutableElement) element;
                // Validate method signature.
            }
        }
    }

    return false;
}
```

Đây là snippet của processor có `@SupportedAnnotationTypes` đúng phạm vi. Không dùng reflection `Class.getAnnotation(...)` để tìm annotation trong source chưa biên dịch: compiler model hoạt động **trước runtime**.

Khi muốn báo lỗi gắn vào declaration, dùng:

```java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Invalid method signature",
        element);
```

Snippet này cần biến `element` từ round hiện tại. `Element` chỉ cung cấp gợi ý vị trí; compiler/IDE có thể không xác định được tọa độ nguồn cụ thể với một element lấy từ compiled dependency.

**Vòng đời:** annotation processor có thể chạy nhiều rounds khi sinh source mới bằng `Filer`. Không giữ `Element` hoặc `TypeMirror` qua compilation task khác hay cache tĩnh dài hạn; nếu cần lưu metadata, hãy sao chép tên/kind/signature có kiểm soát.

## 12. Records và sealed types: hai lý do không bỏ qua model hiện đại

**Records**: `record UserId(String value) {}` là `TypeElement` có kind `RECORD` và `getRecordComponents()`. Record component không phải `VariableElement`; để phân tích annotation trên component, dùng `RecordComponentElement` phù hợp.

**Sealed types**: `sealed interface Shape permits Circle, Square` vẫn là một `TypeElement` có kind `INTERFACE`. `getPermittedSubclasses()` trả các `TypeMirror` của kiểu được phép. Nếu viết processor phân tích hierarchy, không chỉ đọc `getInterfaces()` rồi cho rằng mọi subtype đều có thể tồn tại tùy ý.

**Nested classes**: `Outer.Inner` là `TypeElement` với `getNestingKind() == MEMBER`; không dùng chuỗi đơn giản `Inner` làm khóa duy nhất và không tự suy binary name từ qualified name.

**Annotation types**: `@interface Config { int timeout() default 5; }` có kind `ANNOTATION_TYPE`; member `timeout()` thuộc executable element và `getDefaultValue()` có thể mang `AnnotationValue`.

**Enum**: hằng `Mode.FAST` là `VariableElement` loại `ENUM_CONSTANT`, không phải `FIELD` thông thường khi phân loại bằng `ElementKind`.

## 13. Phạm vi của model so với reflection và AST

| Khía cạnh | Language Model API | Java reflection | AST/parser |
| --- | --- | --- | --- |
| Nguồn thông tin | Compiler model của source, generated source, dependency | Class/runtime metadata đã nạp | Cây cú pháp source |
| Khai báo class/method/field | Có | Có | Có |
| Source chưa compile thành class | Có | Không trực tiếp | Có |
| Generic signature/annotation | Có | Có ở mức runtime metadata thích hợp | Có |
| Nội dung statement/expression của method body | Không phải chức năng chung của `Element` | Không | Có, tùy parser/compiler tree API |
| Phù hợp cho annotation processor | Rất phù hợp | Không thay thế | Chỉ khi cần phân tích chi tiết cú pháp |

Do đó, một processor kiểm tra signature của phương thức nên dùng `ExecutableElement`; một công cụ muốn phân tích từng lời gọi method trong body cần AST/tool phù hợp. Không dựng lại cú pháp bằng regex trên tên và modifiers của Element.

## 14. Sai lầm điển hình

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cast mọi `Element` sang `TypeElement` | Element còn có method, field, parameter… | Dùng `getKind()` hoặc `instanceof`, `ElementFilter`. |
| Cast `variable.asType()` sang `TypeElement` | `asType()` trả `TypeMirror` | Kiểm tra `TypeKind`, dùng `DeclaredType.asElement()` khi phù hợp. |
| Nghĩ `getEnclosedElements()` gồm inherited members | Nó là các khai báo trực tiếp | `Elements.getAllMembers(type)` khi cần. |
| Nhầm constructor với method | Cả hai là `ExecutableElement` | Phân biệt `ElementKind.CONSTRUCTOR`/`METHOD`. |
| Nhầm type parameter với class | `T`/`U` là `TypeParameterElement` | Dùng đúng khai báo/`TypeVariable`. |
| Quên record component | `RECORD_COMPONENT` không phải `FIELD` | Dùng `getRecordComponents()`. |
| So sánh type bằng text | Không đủ cho generics/assignability | Dùng `Types.isSameType`/`isAssignable`. |
| Dùng `getSimpleName()` làm khóa toàn cục | Nhiều kiểu cùng tên đơn giản | Dùng qualified/binary name phù hợp. |
| Dùng reflection để đọc source chưa biên dịch | Runtime class chưa tồn tại | Dùng compiler model. |
| Cache `Element` qua nhiều compilation | Object gắn với environment cũ | Lưu metadata tách biệt, không lưu object model. |
| Processor bị gọi nhiều round và báo trùng | Không xét `round.processingOver()`/nguồn mới | Thiết kế xử lý và trạng thái theo round. |
| Runtime thiếu compiler | `ToolProvider.getSystemJavaCompiler()` có thể null | Dùng JDK/runtime image có `jdk.compiler`. |

## 15. Kiểm tra kiến thức

**Câu 1.** Với `public class Foo { int x; void run(int n) {} }`, `Foo`, `x`, `run` và `n` thuộc interface nào?

**Đáp án:** `Foo` là `TypeElement`; `x` là `VariableElement FIELD`; `run` là `ExecutableElement METHOD`; `n` là `VariableElement PARAMETER`.

**Câu 2.** `TypeElement.getTypeParameters()` và `TypeElement.getInterfaces()` có trả cùng loại đối tượng không?

**Đáp án:** Không. `getTypeParameters()` trả khai báo `TypeParameterElement`; `getInterfaces()` trả các `TypeMirror` của interface.

**Câu 3.** Với `record Point(int x, int y) {}`, `x` là `VariableElement FIELD` chứ?

**Đáp án:** Thành phần record `x` được biểu diễn bằng `RecordComponentElement`. Có các field/accessor liên quan, nhưng không nên nhầm record component với field.

**Câu 4.** Để tìm method kế thừa của class, chỉ dùng `methodsIn(type.getEnclosedElements())` đủ không?

**Đáp án:** Không. Nó chỉ lọc khai báo trực tiếp. Khi cần member kể cả kế thừa, dùng `Elements.getAllMembers(type)` rồi lọc theo nhu cầu.

**Câu 5.** Compiler cho field kiểu `List<String>`. Lấy tên `java.util.List` và generic argument bằng cách nào?

**Đáp án:** Xem `field.asType()` dưới dạng `DeclaredType` nếu kind phù hợp; `declared.asElement()` cho declaration của `List`, còn `getTypeArguments()` cho `String`.

**Câu 6.** Khi processor chỉ biết `Element`, cách nào xác định an toàn đó là method?

**Đáp án:** Kiểm tra `element.getKind() == ElementKind.METHOD` rồi cast sang `ExecutableElement`, hoặc dùng `ElementFilter.methodsIn(...)` với collection phù hợp.

## 16. Checklist và tài liệu chính thức

Checklist ngắn:
- `Element` = khai báo; `TypeMirror` = kiểu.
- `TypeElement` = class/interface/enum/annotation/record.
- `ExecutableElement` = method/constructor; parameter là `VariableElement`.
- `VariableElement` = field/parameter/enum constant; không nhầm `RecordComponentElement`.
- Kiểm tra `ElementKind` trước cast; dùng `ElementFilter` khi duyệt nhiều element.
- `getEnclosedElements()` chỉ cho khai báo trực tiếp; `getAllMembers()` phù hợp với inherited members.
- `getTypeParameters()` khác `getReturnType()`/`asType()`; generic declaration khác type usage.
- Dùng `Elements`/`Types` thay vì dựa vào chuỗi tên/kiểu không đủ chính xác.
- Tập trung model compile-time, không cố dùng reflection hoặc AST khi không cần.
- Kiểm tra với JDK/toolchain thực của dự án; Java 17+ hỗ trợ model của records và sealed types.

Tài liệu chuẩn:
- [Java SE 17 — Element](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/Element.html)
- [Java SE 17 — ElementKind](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ElementKind.html)
- [Java SE 17 — TypeElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/TypeElement.html)
- [Java SE 17 — ExecutableElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ExecutableElement.html)
- [Java SE 17 — VariableElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/VariableElement.html)
- [Java SE 17 — RecordComponentElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/RecordComponentElement.html)
- [Java SE 17 — TypeMirror](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html)
- [Java SE 17 — ElementFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/ElementFilter.html)
- [Java SE 17 — Elements](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html)
- [Java SE 17 — Types](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html)
- [Java SE 17 — JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
