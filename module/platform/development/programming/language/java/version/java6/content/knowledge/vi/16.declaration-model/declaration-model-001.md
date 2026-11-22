# javax.lang.model và mô hình chương trình trong compiler

## 1. Vì sao trình biên dịch cần một mô hình riêng của chương trình?

Khi `javac` hoặc một công cụ biên dịch Java xử lý mã nguồn, nó phải hiểu **khai báo** (`class`, `record`, `interface`, method, field, type parameter, package, module...), **kiểu** (primitive, array, generic, wildcard, kiểu khai báo...) và **quan hệ kiểu** (kế thừa, gán được, thay thế tham số generic). Tại thời điểm đó, lớp đang biên dịch **chưa nhất thiết có file `.class` hoặc đối tượng `Class<?>` trong JVM**.

Java SE cung cấp **`javax.lang.model`** và các package con làm **mô hình ngữ nghĩa chuẩn** cho công cụ như annotation processor, mã sinh tự động, kiểm tra tính hợp lệ ở compile time và phân tích khai báo Java.

Ba ý cốt lõi:

1. **`Element` mô tả một khai báo hoặc thành phần của chương trình**: khai báo type, method, field, package, module, record component...
2. **`TypeMirror` mô tả một kiểu**: `String`, `List<String>`, `T`, `int[]`, wildcard, kiểu của method... Nó không phải `java.lang.Class<?>`.
3. **`Elements` và `Types` cung cấp phép tra cứu và tính toán ngữ nghĩa**, còn **`ProcessingEnvironment`** và **`RoundEnvironment`** giúp annotation processor truy cập mô hình trong từng lần/round biên dịch.

Sơ đồ khái niệm:

~~~text
Mã nguồn Java + classpath/module path
               |
               v
       Trình biên dịch Java
               |
          Mô hình ngữ nghĩa
               |
       +-------+---------+
       |                 |
       v                 v
   Element          TypeMirror
 (khai báo)          (kiểu)
       |                 |
       v                 v
   Elements            Types
 (tra cứu)       (quan hệ kiểu)
       |                 |
       +-------+---------+
               |
               v
     Annotation processor
    diagnostic / sinh mã
               |
               v
        .class / resource
~~~

**`javax.lang.model` không phải AST đầy đủ của mọi biểu thức/câu lệnh.** Nó tập trung vào **ngữ nghĩa khai báo và kiểu**. Nếu một công cụ cần duyệt từng `if`, biểu thức cộng, câu lệnh `return` hay vị trí chi tiết trong cú pháp, trình biên dịch JDK còn cung cấp **Compiler Tree API** (`com.sun.source.tree`, `com.sun.source.util.Trees` trong module `jdk.compiler`). Đó là mô hình bổ sung, không thay thế `Element`/`TypeMirror`.

## 2. Bản đồ package và các interface quan trọng

| Package / module | Thành phần tiêu biểu | Vai trò |
| --- | --- | --- |
| `javax.lang.model` | `SourceVersion`, `AnnotatedConstruct` | Khả năng của mô hình ngôn ngữ và phiên bản nguồn |
| `javax.lang.model.element` | `Element`, `TypeElement`, `ExecutableElement`, `VariableElement`, `RecordComponentElement` | Các phần tử **được khai báo** |
| `javax.lang.model.type` | `TypeMirror`, `DeclaredType`, `ArrayType`, `TypeVariable`, `ExecutableType`, `ErrorType` | Các **kiểu** Java được trình biên dịch hiểu |
| `javax.lang.model.util` | `Elements`, `Types`, `ElementFilter`, visitor và scanner | Tra cứu, duyệt phần tử, so sánh và tạo kiểu |
| `javax.annotation.processing` | `Processor`, `AbstractProcessor`, `ProcessingEnvironment`, `RoundEnvironment`, `Messager`, `Filer` | Vòng đời và công cụ annotation processing |
| `javax.tools` | `JavaCompiler`, `Diagnostic`, `JavaFileObject` | Gọi compiler, quản lý file và diagnostic |
| **Module `java.compiler`** | Các package chuẩn nêu trên | API Java SE, vẫn được hỗ trợ hiện nay |

**Không đổi tên sang `jakarta.lang.model` hoặc `jakarta.annotation.processing`.** Dù nhiều API Jakarta EE khác đã chuyển namespace, những API compiler nêu ở đây vẫn thuộc **Java SE** với tiền tố `javax` trên Java 17+ và các phiên bản hiện hành.

### 2.1. Từ khai báo đến kiểu

Một khai báo thường có **một `Element`** và có thể được biểu diễn bằng **`TypeMirror`** khi cần sử dụng như một kiểu:

~~~java
TypeElement type = elements.getTypeElement("java.util.List");
TypeMirror declaredForm = type.asType();
~~~

Đoạn này là **snippet trong processor**, với biến `elements` đã lấy từ `ProcessingEnvironment`. `TypeElement` mô tả khai báo generic `List<E>`; một `DeclaredType` như `List<String>` là **một cách sử dụng cụ thể của khai báo đó**.

Không đồng nhất:

- `TypeElement`: “`List` được khai báo với những type parameter, method, interface nào?”
- `DeclaredType`: “Kiểu `List<String>` cụ thể này có những type argument nào?”
- `Class<?>`: “Một class đã được JVM nạp lúc chạy là gì?”

### 2.2. Phân biệt từ cùng âm: `ElementKind` và `TypeKind`

`Element#getKind()` phân loại **khai báo**, ví dụ `CLASS`, `INTERFACE`, `RECORD`, `METHOD`, `FIELD`, `RECORD_COMPONENT`. `TypeMirror#getKind()` phân loại **kiểu**, ví dụ `DECLARED`, `ARRAY`, `INT`, `TYPEVAR`, `WILDCARD`, `ERROR`.

Một `TypeElement` của `record Student(...)` có `ElementKind.RECORD`, nhưng `Student` được dùng trong một biểu thức kiểu thường là `DeclaredType` với `TypeKind.DECLARED`. Nhìn thấy hai “kind” khác nhau là đúng, vì chúng trả lời hai câu hỏi khác nhau.

## 3. Hệ thống `Element`: chương trình được tổ chức theo khai báo

Xét ví dụ minh họa độc lập:

~~~java
package example;

public class Box<T> {
    private T value;

    public Box(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }
}
~~~

Ở cấp mô hình:

- `PackageElement` biểu diễn `example`.
- `TypeElement` biểu diễn khai báo `Box<T>`.
- `TypeParameterElement` biểu diễn type parameter `T`.
- `VariableElement` biểu diễn field `value` và parameter `value` của constructor.
- `ExecutableElement` biểu diễn constructor `Box(...)` và method `get()`.
- `Element#getEnclosingElement()` từ field đưa về type chứa field; `TypeElement#getEnclosedElements()` giúp lấy các phần tử được khai báo trực tiếp trong type.

Chương trình trên chỉ là **đối tượng phân tích**, không phải ví dụ chạy độc lập của bài. Ví dụ processor hoàn chỉnh nằm ở mục 7.

### 3.1. API của `Element` và `TypeElement`

| API | Công dụng |
| --- | --- |
| `element.getKind()` | Phân biệt class, record, method, field, parameter... |
| `element.getSimpleName()` | Tên ngắn của khai báo |
| `element.getEnclosingElement()` | Phần tử bao trực tiếp (package, class, method...) |
| `element.getEnclosedElements()` | Các phần tử được khai báo trực tiếp bên trong |
| `element.getModifiers()` | Tập `Modifier` tương ứng |
| `element.asType()` | Kiểu liên quan đến phần tử |
| `element.getAnnotationMirrors()` | Annotation model hiện diện trên phần tử |
| `type.getQualifiedName()` | Tên đủ theo mô hình ngôn ngữ |
| `type.getNestingKind()` | Top-level, member, local hoặc anonymous |
| `type.getTypeParameters()` | Các tham số generic được khai báo |
| `type.getSuperclass()`, `type.getInterfaces()` | Superclass và các interface trực tiếp |
| `type.getRecordComponents()` | Các record component của record |
| `type.getPermittedSubclasses()` | Các subtype được `sealed` type cho phép |

Với Java 17+, `record` và `sealed class/interface` là thành phần ngôn ngữ chính thức. Vì vậy, **`ElementKind.RECORD`, `RecordComponentElement` và `TypeElement.getPermittedSubclasses()` là kiến thức hiện hành**, không phải trường hợp ngoại lệ dành cho API nội bộ.

**Lưu ý:** `Element#getEnclosedElements()` nói về khai báo *trực tiếp*, không phải toàn bộ method được kế thừa. Khi cần cả inherited members, dùng `Elements.getAllMembers(TypeElement)`; khi cần lọc nhóm method, field, record component, cân nhắc `ElementFilter`. Không tự kết luận một class chỉ có những method được liệt kê từ `getEnclosedElements()`.

### 3.2. Record component không chỉ là field

Trong:

~~~java
public record Student(String name, int age) {}
~~~

`name` và `age` xuất hiện trong `TypeElement.getRecordComponents()` dưới dạng `RecordComponentElement`. Trình biên dịch cũng hình thành các phần tử liên quan đến accessor, field và constructor của record; chúng có **vai trò ngữ nghĩa riêng**.

Nếu cần kiểm tra cấu trúc record theo API chính thức, hãy duyệt **`getRecordComponents()`** thay vì tự đoán record component từ tất cả `FIELD` trong `getEnclosedElements()`. Danh sách record component giữ thứ tự thành phần trong header của record và có tên/kiểu của từng component.

### 3.3. Tên qualified, binary và module

Một class lồng nhau có thể có:

~~~text
Qualified name:  example.Outer.Inner
Binary name:     example.Outer$Inner
~~~

`Elements.getBinaryName(TypeElement)` dùng để lấy binary name khi cần map sang tên class JVM/file class; tránh tự thay dấu `.` thành `$` một cách tùy tiện. Dùng `Elements.getPackageOf(element)` và `getModuleOf(element)` khi cần biết phạm vi package/module.

Trong ứng dụng có nhiều named module, một tên type có thể cần ngữ cảnh module để phân giải duy nhất. `Elements.getTypeElement(CharSequence)` có thể trả `null` khi không có hoặc không duy nhất trong phạm vi tìm kiếm; có các overload/phương thức dành cho module hoặc mọi khai báo trùng tên. Không giả định compiler luôn hoạt động trong một classpath toàn cục duy nhất.

## 4. Hệ thống `TypeMirror`: các kiểu được trình biên dịch phân tích

`TypeMirror` là interface gốc cho mô hình kiểu. Các loại thường gặp:

| Mô hình | Trường hợp |
| --- | --- |
| `PrimitiveType` | `int`, `boolean`, `long`... |
| `ArrayType` | `String[]` hoặc `T[]` |
| `DeclaredType` | `String`, `List<String>`, `Student` |
| `TypeVariable` | `T` trong `Box<T>` hoặc `<T> T method(...)` |
| `WildcardType` | `?`, `? extends Number`, `? super Integer` |
| `ExecutableType` | Kiểu method/constructor, gồm các tham số và return type |
| `IntersectionType` | Giao kiểu như ràng buộc `T extends A & B` |
| `UnionType` | Kiểu union có thể xuất hiện trong multi-catch |
| `NoType` | Kiểu đặc biệt như `void`, `none`, package/module |
| `NullType` | Kiểu null theo mô hình |
| `ErrorType` | Kiểu chưa phân giải được trong môi trường compiler |

Nhiều phần tử có `asType()`, nhưng không phải mọi `TypeMirror` đều có một `TypeElement` tương ứng. Ví dụ `int` là primitive, `List<String>[]` là array, wildcard chỉ là thành phần của một kiểu generic. Vì vậy không ép mọi `TypeMirror` thành `DeclaredType` hoặc suy ra `TypeElement` từ mọi kiểu.

### 4.1. Dùng `Types` để hỏi đúng câu hỏi ngữ nghĩa

| Phương thức | Câu hỏi |
| --- | --- |
| `types.isSameType(a, b)` | Hai kiểu có tương đương theo quy tắc API không? |
| `types.isSubtype(a, b)` | `a` có phải subtype của `b` không? |
| `types.isAssignable(a, b)` | Một giá trị kiểu `a` có gán được cho biến kiểu `b` không? |
| `types.directSupertypes(t)` | Các supertype trực tiếp của kiểu |
| `types.erasure(t)` | Kiểu sau erasure là gì? |
| `types.getDeclaredType(element, arguments...)` | Tạo kiểu tham số hóa như `Box<String>` |
| `types.asElement(t)` | Lấy declaration element tương ứng nếu loại kiểu hỗ trợ |
| `types.asMemberOf(containing, element)` | Xem kiểu của member **trong ngữ cảnh kiểu chứa** |
| `types.boxedClass(primitive)`, `types.unboxedType(wrapper)` | Ánh xạ boxing và unboxing |
| `types.getArrayType(component)` | Tạo mô hình kiểu mảng |
| `types.isSubsignature(m1, m2)` | Kiểm tra quan hệ chữ ký giữa hai executable types |

**Không dùng `a.toString().equals(b.toString())` hoặc `a.equals(b)` thay thế cho `types.isSameType(a,b)`.** Để kiểm tra một class ứng viên có triển khai một interface, dùng `types.isAssignable(candidate.asType(), contract.asType())` theo **chiều từ ứng viên sang hợp đồng**. Đảo chiều có thể ra kết quả khác.

`isAssignable` và `isSubtype` không hoàn toàn tương đương: assignment conversion có thể bao gồm các chuyển đổi được phép ngoài quan hệ subtype thuần. Khi một đối số của `isSameType` là wildcard, đặc tả còn có hành vi riêng: nó có thể trả `false` ngay cả nếu truyền lại cùng một wildcard. Hãy dùng phương thức phù hợp câu hỏi của ứng dụng.

### 4.2. Khai báo generic khác một lần áp dụng generic

Với khai báo:

~~~java
interface Box<T> {
    T get();
}
~~~

`TypeElement Box` chỉ ra generic declaration và parameter `T`. Mô hình `Box<String>` là một `DeclaredType` với type argument `String`.

Nếu xem trực tiếp `ExecutableElement#getReturnType()` của `get()` tại khai báo `Box<T>`, ta thấy kiểu liên quan đến `T`. Khi xem member ấy **qua `Box<String>`**, cần dùng `Types.asMemberOf(boxOfString, getMethodElement)` để nhận `ExecutableType` với return type tương ứng sau khi thay type argument.

Điều này quan trọng khi viết source generator, thư viện mapping/serialization, dependency injection hoặc kiểm tra method của subtype generic. Chỉ đọc chuỗi `T` hoặc gọi `erasure` ngay từ đầu làm mất thông tin kiểu cần thiết.

## 5. `Elements`: tiện ích tra cứu và phân tích khai báo

`Elements` thuộc `javax.lang.model.util`; một processor lấy bằng:

~~~java
Elements elements = processingEnv.getElementUtils();
~~~

Đây là snippet trong processor đã khởi tạo. Một số API quan trọng:

| Phương thức | Kết quả / lưu ý |
| --- | --- |
| `getTypeElement("java.lang.String")` | `TypeElement` nếu có và phân giải được |
| `getPackageElement("java.util")` | `PackageElement` nếu có |
| `getModuleElement("java.base")` | `ModuleElement` nếu có trong môi trường |
| `getAllTypeElements(name)` | Tập khai báo type theo tên khi cần xét nhiều module |
| `getBinaryName(type)` | Tên nhị phân của type |
| `getPackageOf(element)` | Package chứa element |
| `getModuleOf(element)` | Module chứa element |
| `getAllMembers(type)` | Member được khai báo và được thừa kế |
| `getAllAnnotationMirrors(element)` | Annotation mirrors theo quy tắc mô hình, kể cả inherited annotation phù hợp |
| `getElementValuesWithDefaults(mirror)` | Giá trị annotation cùng giá trị mặc định |
| `getDocComment(element)` | Documentation comment nếu có |

Không nên lưu chuỗi tên rồi dựa vào reflection để tìm lớp đang được biên dịch. `Elements.getTypeElement(...)` cho phép truy cập cả source đang được xử lý và dependency trong compilation environment.

### 5.1. Annotation: proxy, mirror và giá trị mặc định

Với annotation đơn giản, `element.getAnnotation(Inspect.class)` hoặc `round.getElementsAnnotatedWith(Inspect.class)` có thể tiện dùng. Tuy nhiên, khi annotation có giá trị kiểu `Class<?>`, tên module hoặc kiểu chưa loadable trong JVM chạy processor, không nên ép mọi thuộc tính annotation thành đối tượng runtime; có thể gặp `MirroredTypeException` hoặc `MirroredTypesException`.

Để xử lý metadata annotation tổng quát, dùng:

- `element.getAnnotationMirrors()` — tập `AnnotationMirror`.
- `annotationMirror.getAnnotationType()` — kiểu annotation trong model.
- `annotationMirror.getElementValues()` — các giá trị được khai báo tường minh.
- `elements.getElementValuesWithDefaults(annotationMirror)` — kèm giá trị mặc định.
- `AnnotationValue` và `AnnotationValueVisitor` — thao tác giá trị có cấu trúc.

Đây là lý do source generator tổng quát thường dựa vào **mirror API**, không tìm cách nạp lớp mới bằng `Class.forName()`.

## 6. Annotation processing gắn mô hình này với compiler ra sao?

Processor là chương trình Java **chạy trong môi trường công cụ build/compiler**, trong khi `Element` và `TypeMirror` mô tả **môi trường chương trình đích đang được biên dịch**. Hai môi trường có thể sử dụng classpath/module path khác nhau.

Vòng đời cơ bản:

~~~text
javac --release 17 ... -processor demo.ModelInspector
        |
        v
Processor.init(ProcessingEnvironment)
        |  getElementUtils() --> Elements
        |  getTypeUtils() ----> Types
        |  getMessager() -----> Messager
        |
        v
process(annotations, RoundEnvironment round)
        |  getElementsAnnotatedWith(...)
        |  Element -> TypeElement -> RecordComponentElement
        |  TypeElement.asType() -> TypeMirror
        |  Types.isAssignable(...)
        |
        +--> printMessage(NOTE / ERROR, ..., element)
        |
        v
Round tiếp theo (nếu có nguồn mới) / round cuối
        |
        v
Compile .class nếu không có ERROR
~~~

`ProcessingEnvironment` là môi trường của **phiên processor**, còn `RoundEnvironment` thay đổi theo **round**. Processor không được mặc định giả định chỉ có một round. Khi một processor dùng `Filer.createSourceFile(...)` sinh thêm source, compiler có thể có round mới để phân tích nguồn vừa sinh và annotation trên chúng.

Những quy tắc quan trọng:

- Kế thừa `AbstractProcessor`, nếu override `init` thì gọi `super.init(env)` trước khi dùng `processingEnv`.
- Dùng `round.processingOver()` để nhận biết round cuối.
- Nếu `round.errorRaised()` báo lỗi ở round trước, cân nhắc dừng bước sinh artifact phụ thuộc vào source chưa hợp lệ.
- Dùng `Messager.printMessage(Diagnostic.Kind.ERROR, message, element)` để IDE/CI có thể gắn chẩn đoán với khai báo liên quan.
- Không cache `TypeMirror` hoặc `Element` xuyên **những lần biên dịch độc lập**; model là đối tượng của compilation environment, không phải registry toàn cục bất biến.
- Không sửa AST hay tự ghi file nguồn đã có bằng thao tác tùy ý rồi kỳ vọng compiler tự cập nhật model. Khi sinh file, dùng `Filer` và tuân thủ quy tắc không tạo trùng tệp trong một processing run.

## 7. Ví dụ Java 17+ chạy được: quan sát mô hình của một `record`

Ví dụ dùng một processor có nhiệm vụ **đọc mô hình khai báo**, không sử dụng reflection. Nó quan sát `@Inspect` trên một record và:

1. Lấy `Elements`, `Types` từ `ProcessingEnvironment`.
2. Tìm `demo.Named` bằng `Elements.getTypeElement(...)`.
3. Duyệt khai báo có annotation trong `RoundEnvironment`.
4. Kiểm tra `ElementKind.RECORD` trước khi ép thành `TypeElement`.
5. Lấy **record components** bằng `TypeElement.getRecordComponents()`.
6. Lấy **binary name** bằng `Elements.getBinaryName(...)`.
7. Dùng `Types.isAssignable(...)` để hỏi record có dùng được như `Named` không.
8. Xuất `NOTE` cho model; nếu sai hợp đồng, xuất `ERROR` khiến compile thất bại.

Cấu trúc project:

~~~text
model-demo/
├── src/
│   └── demo/
│       ├── Inspect.java
│       ├── Named.java
│       ├── ModelInspector.java
│       ├── Student.java
│       └── Broken.java
└── build/          (được tạo khi chạy lệnh)
~~~

### 7.1. Annotation được xử lý: `src/demo/Inspect.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface Inspect {}
~~~

`@Retention(SOURCE)` giữ annotation ở bước xử lý nguồn; không bắt buộc lưu nó vào class file runtime. `@Target(TYPE)` cho phép đánh dấu type; processor sẽ kiểm tra thêm `ElementKind.RECORD` để thu hẹp đối tượng được phép.

### 7.2. Hợp đồng: `src/demo/Named.java`

~~~java
package demo;

public interface Named {
    String label();
}
~~~

Đây là interface phải được record ứng viên triển khai. Trong processor, chúng ta sẽ tìm **`TypeElement`** mô tả `demo.Named`, không gọi `Class.forName("demo.Named")`.

### 7.3. Processor: `src/demo/ModelInspector.java`

~~~java
package demo;

import java.util.Set;
import java.util.stream.Collectors;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.ProcessingEnvironment;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.Elements;
import javax.lang.model.util.Types;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.Inspect")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ModelInspector extends AbstractProcessor {
    private Elements elements;
    private Types types;

    @Override
    public synchronized void init(ProcessingEnvironment environment) {
        super.init(environment);
        elements = environment.getElementUtils();
        types = environment.getTypeUtils();
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }

        TypeElement contract = elements.getTypeElement("demo.Named");
        if (contract == null) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, "Cannot resolve demo.Named");
            return true;
        }

        for (Element element :
                round.getElementsAnnotatedWith(Inspect.class)) {
            if (element.getKind() != ElementKind.RECORD) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, "@Inspect requires a record",
                        element);
                continue;
            }

            TypeElement record = (TypeElement) element;
            String components = record.getRecordComponents().stream()
                    .map(component -> component.getSimpleName() + ":"
                            + component.asType())
                    .collect(Collectors.joining(", "));

            boolean assignable =
                    types.isAssignable(record.asType(), contract.asType());

            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.NOTE,
                    "Model " + elements.getBinaryName(record)
                            + " kind=" + record.getKind()
                            + " components=[" + components + "]"
                            + " assignableToNamed=" + assignable,
                    record);

            if (!assignable) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Record must implement demo.Named", record);
            }
        }
        return true;
    }
}
~~~

**Cách đọc code:**

- `elements` và `types` là những **utility của compiler**, không được khởi tạo bằng `new`.
- `elements.getTypeElement("demo.Named")` trả model của hợp đồng. Nếu `null`, processor báo lỗi rõ ràng thay vì dereference `null`.
- `round.getElementsAnnotatedWith(Inspect.class)` lấy các khai báo có annotation ở **round này**.
- `record.getRecordComponents()` trả các component của record trong thứ tự khai báo. Mỗi component có `getSimpleName()` và `asType()`.
- `elements.getBinaryName(record)` trả `demo.Student` trong test này. Nếu type lồng nhau, binary name có thể khác qualified name.
- `types.isAssignable(record.asType(), contract.asType())` hỏi một giá trị có kiểu `Student` có gán vào biến `Named` được không.
- `Messager` được dùng để hiển thị thông điệp từ compiler; `NOTE` không làm fail compilation, `ERROR` làm build thất bại.
- `return true` báo processor **claim** các annotation type được xử lý; nó không có nghĩa rằng mọi annotation hợp lệ.

### 7.4. Trường hợp hợp lệ: `src/demo/Student.java`

~~~java
package demo;

@Inspect
public record Student(String name, int age) implements Named {
    @Override
    public String label() {
        return name + ":" + age;
    }

    public static void main(String[] args) {
        System.out.println("Label: " + new Student("Lan", 21).label());
    }
}
~~~

Đây là Java record hợp lệ từ Java 16 trở đi, tương thích yêu cầu Java 17+. Record components là `name:java.lang.String` và `age:int`, còn `Student` implements `Named`.

### 7.5. Trường hợp sai để kiểm thử: `src/demo/Broken.java`

~~~java
package demo;

@Inspect
public record Broken(String name) {}
~~~

`Broken` có annotation và là record hợp lệ, nhưng **không implements `Named`**. Đây là một test negative có chủ đích: chương trình Java trong file này hợp lệ về cú pháp, còn processor chặn lại vì không đáp ứng quy tắc do ứng dụng đặt ra.

### 7.6. Biên dịch và chạy: test thành công

Từ thư mục `model-demo`, tạo các thư mục đầu ra trên Linux/macOS:

~~~sh
mkdir -p build/processor build/classes
~~~

Trên Windows PowerShell, thay lệnh tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force build/processor,build/classes | Out-Null
~~~

Sau đó, các lệnh `javac`/`java` sau chạy tương tự trên Windows, Linux và macOS (đường dẫn chỉ có một directory ở từng option):

~~~sh
javac --release 17 -d build/processor src/demo/Inspect.java src/demo/ModelInspector.java
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.ModelInspector -d build/classes src/demo/Named.java src/demo/Student.java
java -cp build/classes demo.Student
~~~

Thứ tự là bắt buộc: processor và annotation phải được biên dịch **trước** để compiler có thể nạp chúng ở bước xử lý source của `Student`. `-cp build/processor` giúp source đang biên dịch nhìn thấy `@Inspect`. `-processorpath build/processor` cho compiler nhìn thấy mã processor. `-processor demo.ModelInspector` **chỉ định tường minh processor phải chạy**; không dựa vào discovery ngầm trên classpath.

Ở bước `javac` thứ hai, processor tạo diagnostic `NOTE` có **nội dung** chính xác:

~~~text
Model demo.Student kind=RECORD components=[name:java.lang.String, age:int] assignableToNamed=true
~~~

Công cụ `javac` thường bổ sung đường dẫn file, dòng, tiền tố `Note:` và dấu caret khi in diagnostic ra terminal; IDE hoặc build tool có thể hiển thị khác. Vì thế trên đây là **phần message của diagnostic**, không phải cam kết toàn bộ console output byte-for-byte giống nhau.

Sau bước compile, **stdout chính xác của chương trình**:

~~~text
Label: Lan:21
~~~

Kết quả đã được **biên dịch và chạy trên JDK 24 với `--release 17`**.

### 7.7. Test lỗi: model vẫn đọc được nhưng quan hệ kiểu không đạt

Chạy riêng:

~~~sh
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.ModelInspector -d build/classes src/demo/Named.java src/demo/Broken.java
~~~

Lệnh **phải thất bại**, có exit code khác `0` vì processor tạo `ERROR`. Các diagnostic chứa phần thông điệp:

~~~text
Model demo.Broken kind=RECORD components=[name:java.lang.String] assignableToNamed=false
Record must implement demo.Named
~~~

`javac` có thể in tiền tố `Note:` / `error:`, tên file và vị trí khai báo. Đừng coi hai dòng ở trên là stdout của một chương trình `java`: đó là **nội dung diagnostic trong quá trình compilation**. Đã kiểm thử rằng lệnh này kết thúc thất bại đúng như mong muốn.

**Ý nghĩa học tập:** processor thấy `Broken` như một `TypeElement` và phân tích được `RecordComponentElement` ngay cả khi không hề nạp `Broken.class` vào JVM. Phần `Types` xác định chính xác quan hệ `Broken` → `Named` không hợp lệ và phát diagnostic trước khi đưa mã vào sản phẩm.

## 8. `javax.lang.model` và Reflection: cùng nói về kiểu nhưng ở thời điểm khác nhau

| Khía cạnh | Compiler model (`javax.lang.model`) | Reflection (`java.lang.reflect` / `Class<?>`) |
| --- | --- | --- |
| Thời điểm | Trong compilation, annotation processing | Runtime, sau khi JVM có thể nạp lớp |
| Đối tượng type | `TypeElement`, `TypeMirror`, `DeclaredType` | `Class<?>`, `Type`, `ParameterizedType`... |
| Source chưa compile | **Có thể phân tích** nếu trong compilation environment | Không thể dùng reflection trên một class chưa loadable |
| Generics | Thông tin kiểu trong compilation context, có thể xử lý `ErrorType` và type inference | Metadata generic khả dụng ở runtime theo định dạng class file |
| Đọc annotation `SOURCE` | Có thể qua source/model đang xử lý | Không: không được lưu vào class file |
| Kiểm tra lỗi kiểu | `Types` dùng luật ngôn ngữ Java | Runtime type/reflective checks, không thay compiler |
| Kết quả lỗi | `Messager` + diagnostics và build failure | Exception/Error hoặc kiểm tra runtime |

Đừng xây annotation processor bằng cách gọi `Class.forName(...)` trên tên class đang được biên dịch. Compiler có thể biết mọi thành phần của class trong source trong khi JVM chạy processor **chưa thể nạp nó**.

Ngược lại, khi ứng dụng chỉ cần kiểm tra object đã có trong runtime, reflection có thể phù hợp hơn. Lựa chọn phụ thuộc **thời điểm và mục tiêu**: compiler model để phân tích/kiểm tra/generate tại build time; reflection cho thao tác với lớp/object ở runtime.

## 9. `javax.lang.model` và AST: vì sao có hai API?

Mô hình khai báo và kiểu trả lời:

- “Lớp `Student` có phải record không?”
- “Record có những component nào?”
- “`Student` có thể gán cho `Named` không?”
- “Method này trả về kiểu nào sau khi thay tham số generic?”
- “Kiểu nào được sealed type cho phép kế thừa?”

AST hay **Compiler Tree API** trả lời câu hỏi cú pháp:

- “Trong method có những câu lệnh `if`, `for` hoặc biểu thức nào?”
- “Một biểu thức `a + b` nằm ở dòng nào và có node tree gì?”
- “Thứ tự hoặc cấu trúc các câu lệnh trong body là gì?”

Trong JDK hiện đại, `com.sun.source.tree.Tree` và `com.sun.source.util.Trees` thuộc API được JDK cung cấp trong **`jdk.compiler`**, nhưng không phải là phần thay thế các interface `Element`/`TypeMirror` của Java SE.

Processor chỉ cần kiểm tra annotation, record components, method signature, quan hệ generic hoặc sinh class tương ứng thường có thể làm bằng `javax.lang.model` mà không cần parse AST. Nếu thật sự cần body của method hay vị trí `TreePath`, dùng đúng API cây cú pháp và chú ý khác biệt giữa một source tree đang có và declaration được lấy từ `.class` (có thể không có source tree).

## 10. Visitor, scanner và bộ lọc theo loại phần tử

Để duyệt hàng loạt phần tử, package `javax.lang.model.util` có `ElementVisitor`-based helpers, `ElementScanner`, `SimpleElementVisitor*`, `TypeVisitor`, `TypeScanner`, `SimpleTypeVisitor*` và `ElementFilter`.

Ví dụ lọc **các method khai báo trực tiếp** trong một type:

~~~java
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.ElementFilter;

TypeElement type = elements.getTypeElement("demo.Student");
for (ExecutableElement method :
        ElementFilter.methodsIn(type.getEnclosedElements())) {
    System.out.println(method.getSimpleName());
}
~~~

Đây là **snippet minh họa trong môi trường processor** với biến `elements` đã sẵn sàng; không phải một chương trình Java độc lập và `System.out` không phải cơ chế báo lỗi được khuyến nghị trong processor. `ElementFilter.methodsIn(...)` lọc những `ExecutableElement` là method trong tập đầu vào; nó không tự thêm inherited methods nếu tập ban đầu là `getEnclosedElements()`. Muốn duyệt cả inherited members, truyền tập từ `elements.getAllMembers(type)`.

Visitor hữu ích khi muốn phân nhánh theo `TypeMirror` hoặc `Element` mà không viết chuỗi dài `if instanceof`. Khi dùng các base visitor có hậu tố theo version, hãy **chọn phiên bản hỗ trợ loại phần tử/kiểu mà công cụ của bạn cần**. Tránh subclass visitor đời cũ rồi giả định nó sẽ xử lý hoàn toàn chính xác record, module hoặc các loại phần tử tương lai. Mã tương thích Java 17+ nên kiểm thử với `ElementKind.RECORD` và các trường hợp mới liên quan.

## 11. Các tình huống nâng cao cần xử lý cẩn thận

### 11.1. Kiểu chưa được phân giải: `ErrorType`

Trong quá trình biên dịch nhiều round, một source có thể tham chiếu một kiểu mà processor khác **sẽ sinh trong round sau**. Khi đó compiler có thể biểu diễn kiểu chưa phân giải dưới dạng `ErrorType` (có `TypeKind.ERROR`).

Không ép một `ErrorType` thành `DeclaredType` rồi cho rằng mọi thuộc tính generic đã hợp lệ; cũng không mặc định lỗi ấy không bao giờ được giải quyết. Với processor phụ thuộc mã sinh, cần chiến lược chờ round sau hoặc báo lỗi cuối cùng khi không thể tiếp tục.

### 11.2. Named modules và phạm vi lookup

`Elements.getTypeElement("a.b.C")` có thể không đủ khi cùng tên type thuộc nhiều module. Khi dùng JPMS, cân nhắc lookup theo `ModuleElement`. Các package `javax.lang.model.*` vẫn thuộc module `java.compiler`; với processor là named module:

~~~java
module example.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
            with example.processor.ModelInspector;
}
~~~

Đây là **minh họa định dạng `module-info.java`**, không khớp package `demo` ở ví dụ classpath, nên **không ghép thẳng vào demo rồi mong chạy**. Module provider và package thực tế phải thống nhất. Với ví dụ ở mục 7, đường đơn giản nhất là **classpath + `-processor`**.

### 11.3. Generic và annotation trên kiểu

Đừng trộn annotation trên **khai báo** với annotation ở **type use**. `element.getAnnotationMirrors()` mô tả annotation của phần tử; kiểu cũng có thể có annotation thông qua `TypeMirror` / `AnnotatedConstruct`, tùy vị trí (`@NonNull String`, type argument...). Nếu cần xử lý mọi vị trí của type-use annotation, phải kiểm tra đúng model của kiểu, không chỉ quét annotation trên class hoặc field.

### 11.4. Quy tắc source level và JDK hiện hành

`SourceVersion` mô tả phiên bản ngôn ngữ, còn `--release 17` chọn các giới hạn compile cho Java 17 (ngôn ngữ, bytecode/API phù hợp). Một processor công bố `@SupportedSourceVersion(RELEASE_17)` phù hợp với ví dụ. Nếu project chuyển sang nguồn JDK mới hơn, cập nhật processor và kiểm thử các model mới thay vì ngầm giả định code hiện tại bao quát mọi tính năng mới.

Từ JDK 23, annotation processing **không còn tự động được kích hoạt chỉ vì compiler tìm thấy processor trên classpath** khi không có cấu hình processing tường minh. Sử dụng `-processor` hoặc cấu hình processor path/module path/`-proc:full` theo tài liệu `javac`. Demo dùng `-processor demo.ModelInspector` và `-processorpath build/processor` nên không phụ thuộc thay đổi default này.

### 11.5. Không xem tên chuỗi là hợp đồng ngữ nghĩa

`Element.toString()` và `TypeMirror.toString()` hữu ích khi hiển thị diagnostic, nhưng muốn kiểm tra subtype, assignability hoặc generic phải gọi đúng API `Types`. Khi chuyển tên class sang binary name, dùng `Elements.getBinaryName(...)` thay vì dựa vào chuỗi in từ `TypeElement`.

### 11.6. Độ ổn định của model trong nhiều round

Đối tượng `Element`, `TypeMirror` và các tiện ích `Elements`/`Types` liên kết với môi trường biên dịch. Khi processor làm việc nhiều round, hãy dùng model theo trạng thái mà API cung cấp trong phiên này; không cache các object model để tái sử dụng xuyên job/build khác. Nếu cần persist kết quả, lưu dạng dữ liệu tường minh (tên/metadata) và phân giải lại trong môi trường mới.

## 12. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dùng `Class.forName` trong processor để đọc type nguồn | Type có thể chưa được compile/load | Tra cứu `Elements.getTypeElement` |
| So sánh `TypeMirror.toString()` | Chỉ là hiển thị; không thay quan hệ kiểu | Dùng `Types.isSameType`, `isAssignable`, `isSubtype` |
| Nhầm `ElementKind.RECORD` với `TypeKind.DECLARED` | Một bên là khai báo, một bên là kiểu | Kiểm tra đúng tầng mô hình |
| Dùng `getEnclosedElements` và tưởng có inherited methods | Chỉ lấy phần tử khai báo bên trong trực tiếp | Dùng `Elements.getAllMembers` khi cần |
| Lấy field để tự suy ra record component | Record components có model riêng | `TypeElement.getRecordComponents()` |
| Đảo đối số `isAssignable` | Tính gán được có chiều | `isAssignable(candidate, contract)` |
| Đánh mất generic bằng `erasure` quá sớm | Không phân biệt các type arguments | Dùng `getDeclaredType`, `asMemberOf` |
| Đọc `getTypeElement` mà không xét `null` | Có thể thiếu hoặc không duy nhất | Kiểm tra dependency/module/round |
| Báo lỗi bằng `System.out.println` | Không gắn diagnostic vào source | `Messager.printMessage(ERROR, ..., element)` |
| Không kích hoạt processor trên JDK mới | Processor có thể không chạy | `-processor` và cấu hình build tool rõ ràng |
| Dùng mirror/element cũ qua nhiều compilation | Model phụ thuộc compiler session | Phân giải lại trong mỗi phiên |
| Dựa vào API nội bộ compiler để làm mọi việc | Tăng phụ thuộc implementation | Ưu tiên API `javax.lang.model` chuẩn |

## 13. Tự kiểm tra kiến thức

**Câu 1:** `TypeElement` và `DeclaredType` khác nhau thế nào?  
**Trả lời:** `TypeElement` là **khai báo type**, còn `DeclaredType` là **kiểu được dùng** từ khai báo ấy, có thể chứa type arguments như `List<String>`.

**Câu 2:** `Student` là record, vậy `ElementKind.RECORD` có đồng nghĩa `TypeKind.RECORD`?  
**Trả lời:** Không. `ElementKind.RECORD` mô tả khai báo; kiểu `Student` có thể được mô tả bằng `DeclaredType` với `TypeKind.DECLARED`.

**Câu 3:** Muốn xác nhận `Student implements Named` trong processor thì dùng API gì?  
**Trả lời:** Lấy hai `TypeMirror`, rồi dùng `types.isAssignable(student.asType(), named.asType())`. Không cần và không nên dùng reflection để nạp `Student`.

**Câu 4:** Source `Box<T>.get()` trả `T`; khi nhìn từ `Box<String>`, làm sao lấy kiểu return cụ thể?  
**Trả lời:** Tạo `DeclaredType` tương ứng `Box<String>` và dùng `Types.asMemberOf(...)` để nhận kiểu member trong ngữ cảnh ấy.

**Câu 5:** `-processorpath` đủ để khiến mã nguồn chắc chắn được kiểm tra trên mọi JDK?  
**Trả lời:** Nó là một cách cấu hình annotation processing; muốn dễ kiểm thử và rõ processor nào phải chạy, dùng thêm `-processor <FQN>` hoặc cấu hình build tool tường minh. Demo dùng cả hai.

**Câu 6:** Compiler model có thể xem body của một method như từng biểu thức/câu lệnh hay không?  
**Trả lời:** `javax.lang.model` chủ yếu mô tả declarations và types; khi cần AST của method body trên `javac`, dùng Compiler Tree API (`com.sun.source.tree` / `Trees`) cho source tương ứng.

**Ghi nhớ:** Mô hình khai báo của Java hiện đại nằm trong **`javax.lang.model`**: `Element` biểu diễn cấu trúc khai báo, `TypeMirror` biểu diễn kiểu, `Elements` tra cứu khai báo, `Types` kiểm tra ngữ nghĩa kiểu. Chúng là công cụ chuẩn để viết annotation processor, đặc biệt với generic, record, sealed type và môi trường có module; **đừng thay chúng bằng reflection hoặc so sánh chuỗi**.

### Tài liệu chính thức

- [Java SE 26 — javax.lang.model](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/package-summary.html)
- [Java SE 26 — javax.lang.model.element](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/package-summary.html)
- [Java SE 26 — TypeElement](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/element/TypeElement.html)
- [Java SE 26 — TypeMirror](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/type/TypeMirror.html)
- [Java SE 26 — Elements](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Elements.html)
- [Java SE 26 — Types](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Types.html)
- [Java SE 26 — javac và annotation processing](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
