# Elements và tra cứu cấu trúc khai báo trong Java

## 1. Mục tiêu và vai trò của Elements

Trong **mô hình khai báo Java** (`javax.lang.model`), một chương trình xử lý annotation hoặc công cụ phân tích source thường cần trả lời những câu hỏi: “Kiểu này thuộc package nào?”, “Đây có phải class/interface không?”, “Những thành viên nào được kế thừa?”, “Tên binary của nested class là gì?”, “Method này có override method của lớp cha không?”, hay “Giá trị mặc định của một annotation member là gì?”.

`javax.lang.model.util.Elements` là **interface cung cấp các phép tra cứu và tiện ích trên các phần tử khai báo** (`Element`). Nó được lấy trong annotation processor qua:

```java
Elements elements = processingEnv.getElementUtils();
```

`processingEnv` được framework cung cấp cho processor trong `init(...)`; đoạn trên **chưa phải chương trình độc lập**. `Elements` là API Java SE đang được duy trì, không phải API nội bộ của `javac`. Để hoạt động với kiểu Java, hệ API song hành là `Types` từ `processingEnv.getTypeUtils()`.

Sau bài học, bạn có thể:

- Phân biệt `Element`, `TypeElement`, `PackageElement`, `ModuleElement`, `ExecutableElement`, `VariableElement`, `TypeMirror` và `Elements`.
- Tra cứu class/package/module bằng tên, phát hiện khi không tìm thấy hoặc tên bị mơ hồ giữa các module.
- Duyệt cây khai báo trực tiếp bằng `getEnclosedElements()`; lấy cả thành viên kế thừa qua `getAllMembers(...)`.
- Phân biệt tên simple, canonical/qualified và **binary name** (đặc biệt với nested types).
- Dùng `overrides(...)`, `hides(...)`, `isFunctionalInterface(...)`, `getAllAnnotationMirrors(...)`, `getElementValuesWithDefaults(...)` và `getDocComment(...)` đúng mục đích.
- Viết một annotation processor Java 17+ có thể chạy thật, kiểm thử cả tra cứu cấu trúc và source file được sinh.

**Phạm vi:** Kiến thức và API vẫn còn áp dụng trong Java hiện đại. Ví dụ dùng `javac --release 17`, các phép `Elements` cốt lõi được kiểm thử trên JDK 24. Một số overload tiện ích cho hệ module và các method mới hơn chỉ dùng khi dự án nhắm tới phiên bản Java hỗ trợ chúng.

## 2. Bản đồ mô hình khai báo

```text
        Source Java hoặc class được compiler quan sát
                         │
                         ▼
                  Element (khai báo)
                         │
        ┌────────────────┼─────────────────────┐
        ▼                ▼                     ▼
   TypeElement     ExecutableElement      VariableElement
 (class/interface,  (method, constructor) (field, parameter,
  enum, record)                           enum constant...)
        │
        ├─ getSimpleName()
        ├─ getQualifiedName()
        ├─ getEnclosedElements()       (chỉ phần tử trực tiếp)
        ├─ getSuperclass()
        └─ getInterfaces()
                         │
                         ▼
               Elements (các tiện ích)
            ┌────────────┼──────────────────────┐
            ▼            ▼                      ▼
      getTypeElement  getPackageOf         getAllMembers
      getBinaryName   getModuleOf          overrides / hides
                         │
                         ▼
                     Types
            (phân tích quan hệ kiểu,
          TypeMirror, generic, assignability)
```

### Phân biệt đối tượng với công cụ

- **`Element`:** một khai báo được mô hình hóa, ví dụ class `demo.Child`, method `greet` hoặc field `own`. Nó không phải `java.lang.reflect.Member` hoặc đối tượng runtime.
- **`TypeElement`:** một `Element` đại diện cho **khai báo kiểu** như class, interface, enum, annotation interface hoặc record.
- **`PackageElement`:** khai báo package. `ModuleElement` đại diện module trong môi trường có modules.
- **`ExecutableElement`:** method, constructor và các phần tử executable được mô hình hóa. `VariableElement` thường dùng cho field, parameter và enum constant.
- **`TypeMirror`:** mô hình **kiểu**. Ví dụ `List<String>` là một kiểu có type arguments; không đồng nhất nó với khai báo `List`.
- **`Elements`:** nhóm method tiện ích trên khai báo; **không phải** một collection chứa “tất cả elements” của chương trình.
- **`Types`:** nhóm phép xử lý mô hình kiểu, chẳng hạn `isSameType`, `isAssignable`, `isSubtype` và `erasure`.

Một nguồn Java có thể **chưa được biên dịch thành class có thể load** khi processor chạy, vì vậy tránh dùng `Class.forName(...)` hoặc runtime reflection để giải quyết cấu trúc của mã người dùng đang được compile.

## 3. Các loại Element phổ biến

| Mô hình | Đại diện cho | Cách nhận biết/khai thác |
| --- | --- | --- |
| `PackageElement` | `package demo;` | `getQualifiedName()`, `isUnnamed()` |
| `ModuleElement` | Named hoặc unnamed module | `getQualifiedName()`, `isUnnamed()` |
| `TypeElement` | Class, interface, enum, annotation interface, record | `getKind()`, `getQualifiedName()`, `getEnclosedElements()` |
| `ExecutableElement` | Method, constructor | `getParameters()`, `getReturnType()`, `getThrownTypes()` |
| `VariableElement` | Field, parameter, enum constant | `getSimpleName()`, `asType()`, `getConstantValue()` (khi thích hợp) |
| `TypeParameterElement` | Type variable được khai báo ở generic class/method | `getBounds()`, `getGenericElement()` |
| `RecordComponentElement` | Record component (Java 16+) | `getAccessor()`, `asType()` |
| `AnnotationMirror` | Mô hình annotation trên một construct | `getAnnotationType()`, `getElementValues()` |

`ElementKind` giúp phân loại. Ví dụ:

```java
if (element.getKind() == ElementKind.CLASS) {
    TypeElement type = (TypeElement) element;
    // Tiếp tục tra cứu khai báo class.
}
```

Đây là **đoạn minh họa trong processor**, với `element` đã có. Phải kiểm tra kind trước khi cast: một `@Target(ElementType.TYPE)` cho phép gắn annotation vào nhiều loại khai báo kiểu hơn chỉ class, còn processor có thể đặt quy tắc riêng.

### Truy vấn các phần tử được khai báo trực tiếp

Mỗi `Element` có `getEnclosingElement()` và `getEnclosedElements()`, tạo quan hệ bao chứa. Với:

```java
package demo;

public class Child {
    public int own;
    public void greet() {}
    public static class Nested {}
}
```

`Child` bao trực tiếp field `own`, method `greet`, nested type `Nested` và những khai báo khác được mô hình hóa. Nhưng `getEnclosedElements()` **không tự liệt kê toàn bộ field/method được kế thừa từ superclass**. Để lấy inherited members, dùng `Elements.getAllMembers(type)`.

## 4. Cách lấy Elements trong annotation processor

Cách thông dụng là kế thừa `AbstractProcessor`, có `ProcessingEnvironment` được compiler cấp:

```java
@SupportedAnnotationTypes("demo.Inspect")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ModelProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {

        Elements elements = processingEnv.getElementUtils();
        // Dùng elements để kiểm tra khai báo trong round.
        return true;
    }
}
```

Đây là **khung code minh họa**, chưa có imports và phần sinh file; phần 9 là project chạy độc lập. Các method quan trọng của `ProcessingEnvironment`:

- `getElementUtils()` trả `Elements` để tra cứu khai báo.
- `getTypeUtils()` trả `Types` để xét quan hệ kiểu.
- `getMessager()` phát diagnostic phù hợp với element.
- `getFiler()` tạo source/class/resource file mới.

`Elements` phản ánh **môi trường biên dịch hiện tại**. Cùng một tên kiểu có thể không quan sát được do classpath/module path hoặc bản source đang xử lý, chứ không phải vì kiểu đó chưa tồn tại trên internet hay trên ổ đĩa.

## 5. Tra cứu class, package và module bằng tên

### 5.1. `getTypeElement(...)`

```java
TypeElement stringType =
        elements.getTypeElement("java.lang.String");
TypeElement child =
        elements.getTypeElement("demo.Child");

if (child == null) {
    // Không tìm thấy hoặc không thể xác định duy nhất.
}
```

Dùng **canonical name** khi gọi overload nhận `CharSequence`; ví dụ `java.util.Map.Entry` chứ không phải đường dẫn `java/util/Map$Entry.class`. Theo hợp đồng API hiện hành, `getTypeElement(name)` có thể trả `null` khi kiểu không thể tìm hoặc **không thể phân định duy nhất** trong môi trường module.

Điều này có hai hệ quả:

1. **Không dùng `Objects.requireNonNull(...)` vô điều kiện** nếu truy vấn tên được lấy từ dữ liệu cấu hình hoặc source tùy ý. Kiểm tra `null` và tạo diagnostic rõ ràng.
2. Với project JPMS có nhiều module, chỉ tên canonical có thể **không đủ** để định vị chính xác một type. Dùng overload có `ModuleElement` khi biết module đích.

Ví dụ:

```java
ModuleElement module =
        elements.getModuleElement("my.app.module");
TypeElement service = module == null ? null :
        elements.getTypeElement(module, "com.acme.Service");
```

Đoạn này **minh họa**: `my.app.module` và `com.acme.Service` phải tồn tại trong môi trường thực tế; trên classpath của demo phần 9 không có module này. Overload module-aware được bổ sung từ Java 9 và còn hữu ích trong dự án JPMS hiện tại.

### 5.2. `getPackageElement(...)`

```java
PackageElement pkg =
        elements.getPackageElement("demo");
boolean found = pkg != null;
```

Tên trống `""` có thể dùng để truy vấn unnamed package, nhưng không nên sử dụng unnamed package trong thiết kế code generator quy mô lớn vì khó quản lý naming và module boundaries.

Trong JPMS, một package name có thể xuất hiện ở nhiều module; dùng `getPackageElement(module, "demo")` khi có module cụ thể, hoặc các method `getAllPackageElements(...)` nếu muốn xem nhiều kết quả thay vì bỏ qua khả năng trùng.

### 5.3. `getModuleElement(...)` và `getModuleOf(...)`

```java
ModuleElement moduleOfChild =
        elements.getModuleOf(child);

if (moduleOfChild != null && moduleOfChild.isUnnamed()) {
    // Child thuộc unnamed module trong môi trường đang xét.
}
```

`getModuleOf` (Java 9+) trả module chứa element. Trong một số môi trường compiler không biểu diễn module, kết quả có thể `null`; **không dereference vô điều kiện** khi viết processor đa phiên bản hay kiểm tra nhiều loại môi trường.

Lưu ý `getPackageOf(element)` trên **module element** có thể trả `null`; đừng giả định mọi `Element` đều thuộc một package.

### 5.4. `getAllTypeElements` / `getAllPackageElements`

Các tiện ích hiện hành còn cung cấp:

```java
Set<? extends TypeElement> candidates =
        elements.getAllTypeElements("demo.Service");
```

Đây là minh họa để biểu diễn vấn đề cùng canonical name trong nhiều module. Trả về một `Set`, có thể rỗng hoặc có nhiều `TypeElement`. Đừng mặc định lấy phần tử đầu tiên là type đúng; phải xác định module/scope rõ ràng.

**Khi nào dùng gì?**

| Nhu cầu | API ưu tiên |
| --- | --- |
| Một type duy nhất trong môi trường đơn giản | `getTypeElement("p.Type")` |
| Type trong một module xác định | `getTypeElement(module, "p.Type")` |
| Tất cả type có cùng canonical name | `getAllTypeElements("p.Type")` |
| Package duy nhất | `getPackageElement("p")` |
| Package của một element | `getPackageOf(element)` |
| Module của một element | `getModuleOf(element)` |
| Module tên cụ thể | `getModuleElement("module.name")` |

## 6. Tên simple, qualified và binary: đừng trộn lẫn

Một nested class minh họa:

```java
package demo;
public class Child {
    public static class Nested {}
}
```

Các cách gọi tên quan trọng:

| API hoặc cách viết | Giá trị với nested type |
| --- | --- |
| `nested.getSimpleName()` | `Nested` |
| `nested.getQualifiedName()` | `demo.Child.Nested` |
| `elements.getBinaryName(nested)` | `demo.Child$Nested` |
| Đường dẫn class file trên classpath | `demo/Child$Nested.class` |
| URI/path của Java source định nghĩa outer | Thường gắn với `Child.java`, không mặc định có `Nested.java` |

`Name` trả về từ các API như `getSimpleName()` hoặc `getBinaryName(...)` không phải `String`, nhưng triển khai `CharSequence` và có `contentEquals(...)`. Khi so tên với một literal:

```java
boolean isNested =
        nested.getSimpleName().contentEquals("Nested");
```

**Binary name** khác qualified name khi có nested types. Nó quan trọng khi quản lý output `.class`, tra cứu bytecode và tương tác với công cụ dùng quy tắc đặt tên JVM. Không tự tạo binary name bằng cách thay mọi dấu chấm thành `$` vì dấu chấm phân cách package phải giữ nguyên và cấu trúc nesting cần được phân biệt.

`elements.getBinaryName(type)` là phép tra cứu chuẩn; không lấy `type.getQualifiedName()` rồi giả định phù hợp mọi mục đích. Với local/anonymous classes, tên, khả năng có qualified name và mô hình khai báo có những khác biệt riêng; đừng áp một quy tắc naming duy nhất lên tất cả.

## 7. Thành viên khai báo trực tiếp và thành viên kế thừa

### 7.1. `getEnclosedElements()` chỉ phản ánh quan hệ bao chứa

```java
List<? extends Element> declared =
        child.getEnclosedElements();
```

Đây là các phần tử có `child` làm enclosing element, không phải danh sách đầy đủ các members visible qua inheritance.

Ví dụ:

```java
package demo;

public class Base {
    public int inherited;
    public String greet() { return "base"; }
}

public class Child extends Base {
    public int own;
    @Override public String greet() { return "child"; }
}
```

*Đây là minh họa hai khai báo, không phải một file Java hợp lệ duy nhất khi cả hai đều `public`; ở project hoàn chỉnh chúng được đặt trong hai file khác nhau.*

`child.getEnclosedElements()` có field `own`, method `greet` của Child, nhưng **không có field `inherited` chỉ được khai báo trong Base**.

### 7.2. `getAllMembers(TypeElement)` có xét inheritance

```java
List<? extends Element> all =
        elements.getAllMembers(child);
```

Javadoc `Elements` mô tả đây là các members của type, bao gồm thành viên được khai báo trực tiếp và **thành viên kế thừa**. Với class, kết quả bao gồm constructors tương ứng; không bao gồm local/anonymous classes như các thành viên thông thường.

Để lấy đúng nhóm, `ElementFilter` dễ đọc hơn tự cast toàn bộ `Element`:

```java
List<VariableElement> fields = ElementFilter.fieldsIn(
        elements.getAllMembers(child));
List<ExecutableElement> methods = ElementFilter.methodsIn(
        elements.getAllMembers(child));
```

Các đoạn này thuộc code có `elements` và `child` đã được khởi tạo; compiler trả các collection theo kiểu con tương ứng.

**Đừng khẳng định số lượng `getAllMembers` luôn cố định**: object methods, constructors, inherited interfaces, accessibility và cách biểu diễn thành viên có thể ảnh hưởng kết quả. Khi test, kiểm tra **sự có mặt của member cần thiết** thay vì assert tổng số entries.

### 7.3. `ElementFilter` giúp truy vấn theo kind

`javax.lang.model.util.ElementFilter` có các tiện ích `fieldsIn(...)`, `methodsIn(...)`, `constructorsIn(...)`, `typesIn(...)` và các nhóm phù hợp. Trong annotation processor:

```java
boolean hasOwn = ElementFilter.fieldsIn(
        child.getEnclosedElements()).stream()
        .anyMatch(f -> f.getSimpleName().contentEquals("own"));

boolean inheritedVisible = ElementFilter.fieldsIn(
        elements.getAllMembers(child)).stream()
        .anyMatch(f -> f.getSimpleName().contentEquals("inherited"));
```

Đây là **hai điều kiện khác nhau**: cái đầu hỏi có field **được khai báo trong Child**; cái sau hỏi field **thuộc tập members của Child** bao gồm inheritance.

## 8. Hiểu đúng `overrides`, `hides` và các phép semantic

### 8.1. Kiểm tra method override

Một class có method instance:

```java
public class Base {
    public String greet() { return "base"; }
}

public class Child extends Base {
    @Override public String greet() { return "child"; }
}
```

*Hai class trên là minh họa tách biệt theo file.* Để kiểm tra override theo ngữ nghĩa Java, thay vì chỉ so tên:

```java
boolean overrides = elements.overrides(
        childGreet, parentGreet, child);
```

Tham số:

- `childGreet`: `ExecutableElement` của method ở subtype.
- `parentGreet`: `ExecutableElement` của method ở supertype.
- `child`: `TypeElement` dùng làm ngữ cảnh xét override.

`Elements.overrides(...)` áp dụng quy tắc override của Java (signature, inheritance, accessibility, generics và type relations). Hai method trùng tên chưa đủ để được coi là override; method `private` hoặc `static` có semantics khác.

### 8.2. Kiểm tra member hiding

Với static method:

```java
public class Base {
    public static String tag() { return "base"; }
}

public class Child extends Base {
    public static String tag() { return "child"; }
}
```

*Đây là hai file minh họa*. `Child.tag()` **hide** method `Base.tag()`, không override kiểu dynamic dispatch. Dùng:

```java
boolean hides = elements.hides(childTag, parentTag);
```

`hides(...)` cũng áp dụng cho các tình huống che khuất loại/field theo quy tắc JLS. Đừng dùng `overrides` cho static methods hoặc khẳng định đồng tên là hidden nếu điều kiện access/scope không thỏa.

### 8.3. Những tiện ích semantic khác

| API | Ý nghĩa/ghi chú |
| --- | --- |
| `isFunctionalInterface(TypeElement)` | Kiểm tra interface có thuộc loại functional interface, ví dụ `java.lang.Runnable`. |
| `isDeprecated(Element)` | Xác định element được đánh dấu deprecated theo API; đừng chỉ tìm tên annotation bằng chuỗi. |
| `getConstantExpression(Object)` | Tạo biểu thức hằng Java biểu diễn primitive/String; có ích khi sinh code. |
| `getOrigin(Element)` | Thông tin origin `EXPLICIT`, `MANDATED` hoặc `SYNTHETIC` khi implementation cung cấp (Java 9+). |
| `getOutermostTypeElement(Element)` | Tìm outermost type chứa element (Java 18+). |
| `getFileObjectOf(Element)` | Lấy file object gắn với element nếu có, có thể `null` tùy môi trường/element. |
| `getName(CharSequence)` | Tạo `Name` với cùng chuỗi ký tự. |

Không dùng những method bổ sung gần đây trong source được biên dịch với `--release 17` nếu method đó xuất hiện sau target. Demo độc lập ở phần 9 chỉ dùng các phép phù hợp với Java 17. Hợp đồng mới nhất có thể thêm các default methods trong `Elements` theo thời gian; luôn tham chiếu Javadoc phiên bản dự án sử dụng.

## 9. Ví dụ Java 17+: viết processor tra cứu Elements và sinh báo cáo

Demo có **một annotation**, **một processor** và **ba class ứng dụng**. Nó kiểm tra package/module, tra cứu type, phân biệt declared/inherited fields, tên binary nested class, overriding/hiding, functional interface, giá trị mặc định annotation và Javadoc comment.

Processor không chỉ in log; nó **sinh `ModelReport.java`** qua `Filer`. Ứng dụng gọi `ModelReport.describe()` để đưa ra stdout ổn định. Cách này chứng minh kết quả truy vấn `Elements` được thực hiện **trong lúc compile**, rồi chuyển thành dữ liệu có thể dùng lúc chạy.

### 9.1. Cây file

```text
elements-demo/
├── src/
│   └── demo/
│       ├── Inspect.java
│       └── ModelProcessor.java
├── app/
│   └── demo/
│       ├── Base.java
│       ├── Child.java
│       └── Main.java
└── build/
    ├── processor/              # API annotation + processor
    ├── generated/              # ModelReport.java được sinh
    └── classes/                # class files, gồm ModelReport.class
```

### 9.2. `src/demo/Inspect.java`

```java
package demo;

import java.lang.annotation.*;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Inspect {
    String value() default "default";
}
```

`@Retention(SOURCE)` đủ cho processor tìm annotation trên mã đang biên dịch; runtime reflection không cần thấy nó. `value()` có default để demo minh họa `Elements.getElementValuesWithDefaults(...)`.

### 9.3. `src/demo/ModelProcessor.java`

```java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.List;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.ElementFilter;
import javax.lang.model.util.Elements;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.Inspect")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ModelProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> types,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }

        Elements elements = processingEnv.getElementUtils();
        for (Element element : round.getElementsAnnotatedWith(Inspect.class)) {
            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "@Inspect requires a class", element);
                continue;
            }

            TypeElement child = (TypeElement) element;
            TypeElement parent = elements.getTypeElement("demo.Base");

            TypeElement nested = ElementFilter.typesIn(
                    child.getEnclosedElements()).stream()
                    .filter(x -> x.getSimpleName().contentEquals("Nested"))
                    .findFirst().orElseThrow();

            ExecutableElement childGreet = method(child, "greet");
            ExecutableElement parentGreet = method(parent, "greet");
            ExecutableElement childTag = method(child, "tag");
            ExecutableElement parentTag = method(parent, "tag");

            AnnotationMirror mirror = elements
                    .getAllAnnotationMirrors(child).stream()
                    .filter(a -> a.getAnnotationType().asElement()
                            .getSimpleName().contentEquals("Inspect"))
                    .findFirst().orElseThrow();

            String defaultValue = elements
                    .getElementValuesWithDefaults(mirror).entrySet().stream()
                    .filter(e -> e.getKey().getSimpleName()
                            .contentEquals("value"))
                    .findFirst().orElseThrow()
                    .getValue().getValue().toString();

            List<String> lines = List.of(
                    "type=" + child.getQualifiedName(),
                    "package=" + elements.getPackageOf(child)
                            .getQualifiedName(),
                    "moduleUnnamed=" + elements.getModuleOf(child).isUnnamed(),
                    "packageLookup=" + (elements.getPackageElement("demo")
                            != null),
                    "typeLookup=" + (elements.getTypeElement("demo.Child")
                            != null),
                    "missingType=" + (elements.getTypeElement("demo.Missing")
                            == null),
                    "directOwn=" + ElementFilter.fieldsIn(
                            child.getEnclosedElements()).stream()
                            .anyMatch(f -> f.getSimpleName()
                                    .contentEquals("own")),
                    "inheritedField=" + ElementFilter.fieldsIn(
                            elements.getAllMembers(child)).stream()
                            .anyMatch(f -> f.getSimpleName()
                                    .contentEquals("inherited")),
                    "nestedBinary=" + elements.getBinaryName(nested),
                    "overrides=" + elements.overrides(
                            childGreet, parentGreet, child),
                    "hides=" + elements.hides(childTag, parentTag),
                    "functional=" + elements.isFunctionalInterface(
                            elements.getTypeElement("java.lang.Runnable")),
                    "defaultValue=" + defaultValue,
                    "doc=" + elements.getDocComment(child).trim());

            try {
                JavaFileObject generated = processingEnv.getFiler()
                        .createSourceFile("demo.ModelReport", child);
                try (Writer out = generated.openWriter()) {
                    out.write("package demo;\n"
                            + "public final class ModelReport {\n"
                            + "  private ModelReport() {}\n"
                            + "  public static String describe() { return \""
                            + escape(String.join("\n", lines)) + "\"; }\n"
                            + "}\n");
                }
            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, e.getMessage(), child);
            }
        }
        return true;
    }

    private static ExecutableElement method(
            TypeElement type, String name) {
        return ElementFilter.methodsIn(type.getEnclosedElements())
                .stream()
                .filter(x -> x.getSimpleName().contentEquals(name))
                .findFirst().orElseThrow();
    }

    private static String escape(String s) {
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r");
    }
}
```

**Giải thích quan trọng:**

1. `processingEnv.getElementUtils()` cung cấp công cụ tra cứu; không xây `Elements` bằng constructor vì nó là interface do compiler implementation cung cấp.
2. `round.getElementsAnnotatedWith(Inspect.class)` tìm đúng khai báo được annotate trong vòng hiện tại; `processingOver()` tránh tạo source mới ở final round.
3. `elements.getTypeElement("demo.Base")` lấy superclass từ **mô hình biên dịch** dù class `Base` có thể đang được compile trong cùng task; không gọi `Class.forName("demo.Base")`.
4. `ElementFilter.typesIn(child.getEnclosedElements())` lấy nested type **được khai báo trực tiếp**; `elements.getBinaryName(nested)` cho `demo.Child$Nested`.
5. `ElementFilter.fieldsIn(child.getEnclosedElements())` phát hiện `own`; `fieldsIn(elements.getAllMembers(child))` phát hiện `inherited`.
6. `elements.overrides(childGreet, parentGreet, child)` kiểm tra instance-method overriding theo ngữ nghĩa Java. `elements.hides(childTag, parentTag)` kiểm tra static-method hiding.
7. `getAllAnnotationMirrors(child)` tìm annotation mirror; `getElementValuesWithDefaults(mirror)` gồm member mặc định `value="default"` dù `@Inspect` không truyền value.
8. `elements.getDocComment(child)` lấy nội dung Javadoc trong **nguồn fixture có comment**; kết quả có thể `null` trong trường hợp khác. Demo gọi `trim()` vì kiểm soát fixture luôn có comment.
9. `Filer.createSourceFile("demo.ModelReport", child)` tạo source mới và ghi originating element; dùng `try-with-resources` đóng writer.
10. Helper `escape` bảo vệ dấu nháy, backslash và line endings khi đưa báo cáo thành Java string literal. Nếu xây generator hỗ trợ mọi loại văn bản, cần encoder Java literal đầy đủ và tests cho ký tự điều khiển/Unicode; demo chỉ tạo những dòng có cấu trúc đã biết.

### 9.4. `app/demo/Base.java`

```java
package demo;

public class Base {
    public int inherited;

    public String greet() {
        return "base";
    }

    public static String tag() {
        return "base";
    }
}
```

### 9.5. `app/demo/Child.java`

```java
package demo;

/** Child example. */
@Inspect
public class Child extends Base {
    public int own;

    @Override
    public String greet() {
        return "child";
    }

    public static String tag() {
        return "child";
    }

    public static class Nested {}
}
```

`Child` vừa có field tự khai báo, vừa kế thừa field `inherited`, override method instance `greet`, hide method static `tag`, và chứa nested class `Nested`. Đây là một fixture có đủ các quan hệ để kiểm thử `Elements`.

### 9.6. `app/demo/Main.java`

```java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println(ModelReport.describe());
    }
}
```

`ModelReport` **chưa tồn tại lúc viết `Main.java`**; nó được annotation processor sinh và compiler biên dịch trong invocation xử lý source ứng dụng.

### 9.7. Build và chạy — Linux/macOS

Ở thư mục `elements-demo`:

```bash
mkdir -p build/processor build/classes build/generated

# Build annotation API và processor trước.
javac --release 17 -d build/processor \
  src/demo/Inspect.java \
  src/demo/ModelProcessor.java

# Chọn processor tường minh để phù hợp cả JDK 23+.
javac --release 17 \
  -cp build/processor \
  -processorpath build/processor \
  -processor demo.ModelProcessor \
  -s build/generated \
  -d build/classes \
  app/demo/Base.java \
  app/demo/Child.java \
  app/demo/Main.java

# Chạy báo cáo do compile-time processor tạo.
java -cp build/classes demo.Main
```

### 9.8. Build và chạy — Windows PowerShell

```powershell
New-Item -ItemType Directory -Force build/processor,build/classes,build/generated | Out-Null

javac --release 17 -d build/processor src/demo/Inspect.java src/demo/ModelProcessor.java

javac --release 17 -cp build/processor -processorpath build/processor -processor demo.ModelProcessor -s build/generated -d build/classes app/demo/Base.java app/demo/Child.java app/demo/Main.java

java -cp build/classes demo.Main
```

**Lưu ý JDK 23+:** Vì có `-processor demo.ModelProcessor`, javac được yêu cầu thực thi annotation processor rõ ràng. Không dựa vào hành vi discovery classpath ngầm của các JDK cũ. `-cp build/processor` cho mã ứng dụng thấy `@Inspect`; `-processorpath build/processor` là nơi compiler tải `ModelProcessor`.

### 9.9. Stdout xác minh

```text
type=demo.Child
package=demo
moduleUnnamed=true
packageLookup=true
typeLookup=true
missingType=true
directOwn=true
inheritedField=true
nestedBinary=demo.Child$Nested
overrides=true
hides=true
functional=true
defaultValue=default
doc=Child example.
```

Bên cạnh stdout, có hai file mới:

```text
build/generated/demo/ModelReport.java
build/classes/demo/ModelReport.class
```

Dòng `moduleUnnamed=true` phản ánh **fixture dùng classpath không có `module-info.java`**; không phải khẳng định mọi class Java thuộc unnamed module. Dòng `missingType=true` kiểm tra `getTypeElement("demo.Missing") == null`. Dòng `defaultValue=default` cho thấy annotation value mặc định được trả dù nguồn chỉ viết `@Inspect`.

**Về tính lặp lại của ví dụ:** tên `ModelReport` cố định, nên ví dụ giả định **chỉ một class được gắn `@Inspect`**. Nếu có nhiều origin trong một compilation task, processor phải đặt tên output theo từng type hoặc tổng hợp dữ liệu trước khi sinh đúng một report, tránh `FilerException` do tạo trùng tên.

## 10. Duyệt cây khai báo sâu hơn

Trong processor thật, việc lấy một type rồi duyệt các member thường là công việc trung tâm. Một visitor có thể xử lý package, type, method và field theo `ElementKind` hoặc sử dụng `ElementVisitor`/`AbstractElementVisitor`, `SimpleElementVisitor` và các scanner trong `javax.lang.model.util`.

### 10.1. Duyệt children theo cách đơn giản

```java
static void walk(Element root) {
    System.out.println(root.getKind() + ": " + root.getSimpleName());
    for (Element child : root.getEnclosedElements()) {
        walk(child);
    }
}
```

Đây là **method minh họa**, cần import `javax.lang.model.element.Element`. Nó duyệt **quan hệ bao chứa**, không tự mở rộng sang superclass/superinterfaces. Vì vậy `walk(childType)` sẽ không tự khám phá field `inherited` của `Base`.

Với những mô hình rộng, cần giới hạn phạm vi, chọn nhóm kinds cần quan tâm và tránh coi việc duyệt cấu trúc đơn thuần là kiểm tra quan hệ kiểu.

### 10.2. Tìm top-level type từ một nested member

Một method bên trong nested class có nhiều lớp enclosing. Có thể duyệt ngược `getEnclosingElement()` tới top-level type; trên Java 18+ còn có `Elements.getOutermostTypeElement(element)`. Nếu code cần biên dịch với Java 17, nên dùng cách duyệt enclosing theo những APIs đã có thay vì gọi method mới hơn target.

### 10.3. Constructor, record component và method

- Constructor được biểu diễn bởi `ExecutableElement` với `ElementKind.CONSTRUCTOR`, không phải một `java.lang.reflect.Constructor`.
- Record (Java 16+) có `ElementKind.RECORD` và `RecordComponentElement`; record component không đồng nhất với field hoặc accessor method.
- `getAllMembers(type)` liên quan đến members và inheritance; không lấy nó làm danh sách mọi node trong source AST.
- `getEnclosedElements()` có thể bao gồm phần tử do compiler mô hình hóa ngay cả khi source người dùng không khai báo rõ (ví dụ implicit constructor). Khi cần phân biệt origin, API `Elements.getOrigin(element)` cung cấp thông tin theo hợp đồng, nhưng chi tiết classfile/model có thể hạn chế.

## 11. AnnotationMirrors, giá trị mặc định và metadata

### 11.1. Trực tiếp và tất cả annotation mirrors

`element.getAnnotationMirrors()` cho các annotation hiện diện trực tiếp trên element theo mô hình. `elements.getAllAnnotationMirrors(element)` còn xét các annotation inherited theo semantics có liên quan, nhưng **không có nghĩa mọi annotation của mọi superclass đều tự động được kế thừa**. Với Java, `@Inherited` chỉ có hiệu lực trong những trường hợp quy định, chủ yếu trên class declarations.

Khi cần đọc giá trị annotation một cách tổng quát mà không phụ thuộc class runtime:

```java
for (AnnotationMirror mirror :
        elements.getAllAnnotationMirrors(type)) {
    Map<? extends ExecutableElement, ? extends AnnotationValue> values =
            elements.getElementValuesWithDefaults(mirror);
    // Duyệt entry key là method khai báo annotation member,
    // value là AnnotationValue (có thể lấy getValue()).
}
```

Đây là **đoạn minh họa** cần imports `AnnotationMirror`, `AnnotationValue`, `ExecutableElement`, `Map` và biến `type` từ processor. Lưu ý `mirror.getElementValues()` tự nó **không bắt buộc** chứa member dùng default; nếu muốn báo cáo đầy đủ config, dùng `Elements.getElementValuesWithDefaults(mirror)`.

### 11.2. Giá trị Class trong annotation

Khi annotation có member kiểu `Class<?>`, không nên dựa vào `type.getAnnotation(...).someClassMember()` như cách truy cập tổng quát trong processor, vì có thể phát sinh `MirroredTypeException`: class đích có thể chưa load được. Sử dụng `AnnotationMirror`, `AnnotationValue` và `TypeMirror` để giữ quá trình phân tích ở compile-time model.

### 11.3. Javadoc comment

`elements.getDocComment(element)` trả text documentation comment nếu compiler/môi trường có thông tin đó; nếu không có, kết quả có thể `null`. API không bảo đảm bạn có source comment cho mọi type được tìm từ classpath; nhiều type được đọc từ `.class` không mang nguyên văn Javadoc source.

Đừng kiểm tra “không có tài liệu” bằng `getDocComment(element).isBlank()` trước khi xử lý `null`. Ví dụ trong demo có comment rõ ràng:

```java
/** Child example. */
@Inspect
public class Child extends Base { /* ... */ }
```

nên `elements.getDocComment(child).trim()` cho `Child example.`. Đó là đặc điểm của fixture đã kiểm soát, không phải bảo đảm mọi loại element có doc comment.

## 12. Các tình huống module-aware và độ rõ ràng của lookup

Dự án JPMS có thể có các module độc lập cùng quan sát những package hoặc type names giống nhau. `getTypeElement("p.Name")` và `getPackageElement("p")` chỉ an toàn khi có thể xác định duy nhất. Nếu được trả `null`, ngoài tình huống không tồn tại còn cần nghĩ đến **mơ hồ giữa modules**.

Một quy trình thích hợp:

1. Xác định `ModuleElement` của element gốc bằng `getModuleOf(origin)`, hoặc module name được người dùng cấu hình và tìm qua `getModuleElement(name)`.
2. Nếu lookup target phải nằm trong module đó, gọi `getTypeElement(module, name)` hoặc `getPackageElement(module, name)`.
3. Nếu người dùng chủ ý tìm *mọi* candidate theo tên, dùng `getAllTypeElements(name)`/`getAllPackageElements(name)`.
4. Nếu không xác định được, báo diagnostic về module/name thay vì âm thầm chọn phần tử đầu tiên.
5. Với named modules, quan tâm đến `uses/provides`, module path, source path và visibility; file manager/processor path cũng là cấu hình build cần nhất quán.

Không nên coi `TypeElement.getQualifiedName()` là một khóa định danh toàn cục cho mọi compilation environment; module identity có thể cần nằm trong khóa khi lập registry hoặc chỉ mục.

## 13. Dùng Elements để xác thực API thay vì so chuỗi

Giả sử processor làm validator: một class dùng `@Handler` phải có method instance `handle(Request)` public, trả `Response`. Làm thế nào?

**Không nên** chỉ kiểm tra:

```java
method.getSimpleName().contentEquals("handle")
        && method.getReturnType().toString().equals("demo.Response")
```

Bởi vì overloaded methods, generics, import aliases không tồn tại theo cú pháp nhưng package resolution, inheritance, accessibility và type erasure có thể làm phép so chuỗi sai.

**Nên** kết hợp:

- `Elements.getAllMembers(handlerType)` để nhìn thấy cả method được kế thừa.
- `ElementFilter.methodsIn(...)` để bỏ field/type khỏi danh sách.
- `ExecutableElement.getParameters()`, `getReturnType()` và `getModifiers()` để kiểm tra signature.
- `Elements.overrides(...)` khi cần so quy tắc override.
- `Types.isSameType(...)`, `isAssignable(...)` hoặc `isSubtype(...)` khi cần xét các quan hệ kiểu.
- `Elements.getTypeElement("demo.Request")`/`getTypeElement("demo.Response")` để lấy khai báo mục tiêu.
- `Messager.printMessage(Diagnostic.Kind.ERROR, message, offendingElement)` để người dùng thấy lỗi gắn vào source.

`Types` và `Elements` cùng nằm ở compile-time, nhưng giải quyết hai loại câu hỏi khác nhau: **Elements tìm/kiểm tra khai báo**, **Types xét quan hệ kiểu**. Không cần reflection runtime.

## 14. Kiểm thử và QA cho processor dùng Elements

| Test | Fixture | Kỳ vọng |
| --- | --- | --- |
| Tra cứu kiểu | Source `demo.Child` được compile | `getTypeElement("demo.Child") != null`. |
| Lookup thiếu | Không có `demo.Missing` | `getTypeElement("demo.Missing") == null`. |
| Package | `package demo;` | `getPackageOf(child).getQualifiedName()` là `demo`. |
| Module classpath | Không có `module-info.java` | `getModuleOf(child).isUnnamed()` là `true` trong môi trường demo. |
| Declared field | `Child.own` | `fieldsIn(child.getEnclosedElements())` tìm thấy `own`. |
| Inherited field | `Base.inherited` | `fieldsIn(getAllMembers(child))` tìm thấy `inherited`. |
| Nested binary name | `Child.Nested` | `getBinaryName(nested)` là `demo.Child$Nested`. |
| Method override | `Child.greet` / `Base.greet` | `overrides(..., child) == true`. |
| Static hiding | `Child.tag` / `Base.tag` | `hides(...) == true`. |
| Functional interface | `java.lang.Runnable` | `isFunctionalInterface(...) == true`. |
| Annotation default | `@Inspect` không chỉ định `value` | `getElementValuesWithDefaults` trả `default`. |
| Doc comment | `/** Child example. */` | `getDocComment(child).trim()` là `Child example.`. |
| Source sinh | Processor tạo `ModelReport` | Generated `.java` và compiled `.class` đều tồn tại. |

**Đừng test bằng total count của `getAllMembers`** nếu thứ bạn cần là một member cụ thể. Điều đó làm test kém ổn định do các thành viên ngầm hoặc members từ platform. So sánh semantics của phần tử mong đợi tốt hơn.

Với JUnit Jupiter, một test môi trường tích hợp thường compile fixture bằng `JavaCompiler`, cấu hình processor, sau đó assert diagnostics và generated artifacts. Đoạn minh họa ngắn sau giả định một `JavaCompiler.CompilationTask task` và `DiagnosticCollector<JavaFileObject> diagnostics` được dựng trước:

```java
boolean ok = Boolean.TRUE.equals(task.call());

boolean hasError = diagnostics.getDiagnostics().stream()
        .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

// Dùng Assertions.assertTrue(ok) và assertFalse(hasError)
// trong test của fixture hợp lệ.
```

Đoạn trên **không phải chương trình độc lập**. Nếu fixture sai, hãy mong compiler thất bại và phát error gắn vào element. Không assert nguyên văn toàn bộ `javac` stderr, vì path, locale và JDK có thể khác nhau.

## 15. Những lỗi thường gặp khi tra cứu cấu trúc khai báo

**Lỗi 1 — Nhầm `Elements` với `Element`.**  
`Element` đại diện một khai báo; `Elements` là dịch vụ tiện ích. Từ processor gọi `processingEnv.getElementUtils()`, không tự xây nó bằng `new Elements()`.

**Lỗi 2 — Chỉ dùng `getEnclosedElements()` rồi kết luận type không có member kế thừa.**  
`getEnclosedElements()` phản ánh members được chứa trực tiếp; cần `getAllMembers(type)` để xét inherited members.

**Lỗi 3 — Dùng `getAllMembers` như một AST traversal.**  
Đây là truy vấn members theo hợp đồng Java, không phải cây cú pháp đầy đủ và không mang mọi node/biểu thức trong source.

**Lỗi 4 — Dùng qualified name thay binary name cho nested class.**  
`demo.Child.Nested` khác `demo.Child$Nested`. Dùng `getBinaryName` khi cần binary class name.

**Lỗi 5 — Cho rằng `getTypeElement(name)` luôn có kết quả.**  
Phương thức có thể trả `null` nếu name không tìm được hoặc mơ hồ trong module-aware environment. Xử lý `null` và dùng module-specific overload nếu phù hợp.

**Lỗi 6 — So tên method và coi đó là override.**  
Overload, static hiding, accessibility và generics có thể khiến logic sai. Dùng `Elements.overrides` hoặc `hides` theo quy tắc ngôn ngữ.

**Lỗi 7 — Dùng runtime reflection trên source chưa compile.**  
`TypeElement`/`TypeMirror` là mô hình compile-time; `Class.forName` không thay thế cho symbol lookup của compiler.

**Lỗi 8 — Cast `Element` mà không kiểm tra `ElementKind`.**  
Annotation target `TYPE` rộng hơn class; dùng `element.getKind() == ElementKind.CLASS` trước khi cast khi validator yêu cầu class.

**Lỗi 9 — Bỏ qua giá trị annotation default.**  
`AnnotationMirror.getElementValues()` không luôn chứa default values; dùng `getElementValuesWithDefaults(...)`.

**Lỗi 10 — Cho rằng mọi annotation superclass đều inherited.**  
`getAllAnnotationMirrors` áp dụng semantics inheritance, nhưng không biến mọi annotation thành inheritable; cần hiểu `@Inherited` và vị trí annotation.

**Lỗi 11 — Gọi `getDocComment(element).trim()` không kiểm tra `null`.**  
Source docs không luôn có trong processing environment, nhất là với classpath binaries.

**Lỗi 12 — Tạo cùng generated file qua mỗi round.**  
`Filer` sẽ từ chối output trùng, có thể ném `FilerException`. Xử lý `processingOver()` và thiết kế naming/ownership.

**Lỗi 13 — Dựa vào order của Set/Map elements để sinh output.**  
Nếu cần nội dung deterministic, sắp xếp theo khóa ổn định; đừng tin thứ tự iteration ngẫu nhiên.

**Lỗi 14 — Dùng API được bổ sung ở JDK mới trong processor target cũ.**  
Một số method default trong `Elements` được thêm qua các release. So API theo Javadoc của target `--release`, không chỉ JDK đang cài.

**Lỗi 15 — Quên bật annotation processing khi build.**  
Từ JDK 23, cấu hình processor rõ ràng như `-processor`/`--processor-path` thay vì dựa vào quét classpath ngầm.

**Lỗi 16 — Bỏ qua module identity.**  
Nếu có nhiều module, `getTypeElement("p.Type")` có thể không xác định duy nhất. Sử dụng module-aware lookup hoặc xử lý nhiều candidates.

## 16. Câu hỏi tự kiểm tra

**1. `Elements` và `Types` khác nhau ra sao?**  
`Elements` xử lý **khai báo** (lookup, members, binary name, overriding, annotations); `Types` xử lý **quan hệ kiểu** (`TypeMirror`, assignability, erasure, subtype).

**2. Muốn tìm field được kế thừa, chọn `getEnclosedElements` hay `getAllMembers`?**  
`getAllMembers(TypeElement)` rồi dùng `ElementFilter.fieldsIn(...)`.

**3. Vì sao `getTypeElement("demo.Missing")` có thể trả `null`?**  
Không tìm thấy type; trong module-aware environment còn có thể do lookup không xác định duy nhất.

**4. `getBinaryName` của nested class `demo.Child.Nested` là gì?**  
`demo.Child$Nested`.

**5. `Child.greet` là instance override hay static hiding trong demo?**  
`overrides(...)` trả `true` vì `greet` là method instance override. `Child.tag` là static hiding và `hides(...)` trả `true`.

**6. Tại sao không dùng `Class.forName("demo.Child")` trong processor?**  
Class đang compile chưa chắc có bytecode/runtime class có thể load. Dùng `TypeElement` từ môi trường compiler.

**7. `getAllAnnotationMirrors` và `getElementValuesWithDefaults` giải quyết hai việc gì?**  
Phương thức đầu tìm annotation mirrors (kể cả inheritance theo quy tắc); phương thức sau lấy **các member values kể cả defaults**.

**8. `getDocComment` có bảo đảm không `null`?**  
Không. Source comment có thể không tồn tại hoặc không được mô hình môi trường cung cấp.

**9. Nếu cần truy vấn type cùng tên ở nhiều modules, dùng gì?**  
Overload `getTypeElement(module, name)` khi biết module; `getAllTypeElements(name)` khi muốn xét mọi candidates.

**10. `@Retention(SOURCE)` có phù hợp với annotation processor không?**  
Có. Processing diễn ra tại compile-time nên SOURCE retention là hợp lý khi annotation không dùng runtime.

## Tài liệu chính thức hiện hành

- [Oracle Java SE 26 — `Elements`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Elements.html): lookup class/package/module, members, binary name, override/hide, annotation defaults, doc comments và các method mới.
- [Oracle Java SE 26 — `Element`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/Element.html): quan hệ `getEnclosedElements()`, `getEnclosingElement()`, `getKind()` và modifiers.
- [Oracle Java SE 26 — `TypeElement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/TypeElement.html): mô hình khai báo type, simple/qualified names và inheritance.
- [Oracle Java SE 26 — `ElementFilter`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/ElementFilter.html): lọc fields/methods/types/constructors.
- [Oracle Java SE 26 — `Types`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Types.html): type relations và `TypeMirror`.
- [Oracle Java SE 26 — `ProcessingEnvironment`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `getElementUtils()` và `getTypeUtils()`.
- [Oracle Java SE 26 — `AnnotationMirror`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/AnnotationMirror.html): mô hình annotation và values.
- [Oracle Java SE 26 — `javac`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): cấu hình `-processor`, `-processorpath`, `-s`, `-d` và `--release`.

**Ghi nhớ:** `Element` là một khai báo, `Elements` là tiện ích tra cứu và phân tích khai báo, `Types` làm việc với quan hệ kiểu. Với source đang được compiler xử lý, ba công cụ này đáng tin hơn reflection runtime; hãy luôn phân biệt declared/inherited members, canonical/binary names và context module khi viết annotation processor hiện đại.
