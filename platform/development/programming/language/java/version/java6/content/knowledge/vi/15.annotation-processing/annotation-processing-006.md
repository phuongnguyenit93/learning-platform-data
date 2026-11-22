# ProcessingEnvironment, Elements và Types trong Annotation Processing

## 1. Ba thành phần làm việc cùng nhau như thế nào?

**Annotation processing** là cơ chế xử lý khai báo Java trong lúc biên dịch. Một annotation processor có thể kiểm tra hợp đồng kiểu, đưa ra chẩn đoán lỗi/cảnh báo, sinh mã nguồn hoặc sinh resource bằng các API chuẩn của Java. Khác với reflection, processor hoạt động trên **mô hình ngôn ngữ của trình biên dịch**, nên có thể đọc kiểu và phần tử đang được biên dịch kể cả khi chúng **chưa có `.class` để JVM nạp**.

Trong một processor:

- **`ProcessingEnvironment`** là môi trường do công cụ biên dịch cấp khi khởi tạo processor. Nó cung cấp các tiện ích, nơi báo lỗi, nơi tạo file và tùy chọn xử lý.
- **`Elements`** (thuộc `javax.lang.model.util`) là bộ tiện ích thao tác **các phần tử khai báo**: class/interface, method, field, package, module, annotation...
- **`Types`** (cũng thuộc `javax.lang.model.util`) là bộ tiện ích thao tác **các kiểu Java**: quan hệ gán được, subtype, đồng nhất kiểu, generic type, erasure, kiểu của member trong ngữ cảnh generic...

Ba thành phần này thường xuất hiện cùng nhau:

~~~text
javac / JavaCompiler API
        |
        v
Processor.init(ProcessingEnvironment env)
        |
        +--> env.getElementUtils() --> Elements
        |       - tra cứu TypeElement
        |       - tên nhị phân, package/module
        |       - members, annotation mirrors...
        |
        +--> env.getTypeUtils() ----> Types
        |       - isAssignable, isSubtype, isSameType
        |       - erasure, getDeclaredType, asMemberOf...
        |
        +--> env.getMessager() -----> báo ERROR/WARNING/NOTE
        +--> env.getFiler() --------> sinh source/class/resource
        +--> env.getOptions() ------> tùy chọn -A...
        |
        v
Processor.process(annotations, RoundEnvironment round)
        |
        +--> Element / TypeElement / ExecutableElement
        +--> TypeMirror / DeclaredType / ExecutableType
        +--> chẩn đoán hoặc sinh file (có thể tạo round tiếp theo)
~~~

Cần phân biệt: **`ProcessingEnvironment` dùng chung cho một lần chạy processor**, còn **`RoundEnvironment` mô tả các phần tử/annotation thuộc từng vòng xử lý (round)**. Chúng không phải hai tên cho cùng một đối tượng.

## 2. Bối cảnh API và package hiện hành

| Đối tượng hoặc interface | Package | Dùng để |
| --- | --- | --- |
| `AbstractProcessor`, `Processor` | `javax.annotation.processing` | Xây dựng annotation processor |
| `ProcessingEnvironment` | `javax.annotation.processing` | Lấy tiện ích và cấu hình của phiên xử lý |
| `RoundEnvironment` | `javax.annotation.processing` | Xem phần tử thuộc từng round |
| `Element`, `TypeElement`, `ExecutableElement` | `javax.lang.model.element` | Mô hình phần tử khai báo |
| `TypeMirror`, `DeclaredType`, `ExecutableType` | `javax.lang.model.type` | Mô hình kiểu |
| `Elements`, `Types` | `javax.lang.model.util` | Các phép tra cứu và tính toán |
| `Messager`, `Filer` | `javax.annotation.processing` | Báo diagnostic và sinh file |
| `Diagnostic.Kind` | `javax.tools` | Phân loại lỗi, cảnh báo, ghi chú |

Các package `javax.annotation.processing` và `javax.lang.model` **vẫn là API chuẩn được sử dụng trong Java hiện đại**. Không đổi chúng thành `jakarta.*` chỉ vì các thư viện Jakarta EE khác đã đổi namespace: annotation processing thuộc **Java SE**, không phải một API Jakarta EE đã di chuyển.

Những API trên nằm trong module **`java.compiler`**. Khi viết named module chứa processor, cần khai báo `requires java.compiler;`; tùy cách đăng ký, module còn có thể khai báo `provides javax.annotation.processing.Processor with ...`. Khi triển khai dựa trên classpath, có thể chọn processor tường minh bằng tùy chọn `-processor` như ví dụ ở dưới.

## 3. `ProcessingEnvironment`: nguồn tiện ích chính của processor

Framework gọi `Processor.init(ProcessingEnvironment)` **trước khi** gọi `process(...)`. Nếu kế thừa `AbstractProcessor` và override `init`, cần gọi `super.init(environment)` trước khi sử dụng trường `processingEnv` kế thừa.

~~~java
@Override
public synchronized void init(ProcessingEnvironment environment) {
    super.init(environment);
    elements = environment.getElementUtils();
    types = environment.getTypeUtils();
}
~~~

Đoạn này là **snippet trong lớp processor** có hai trường `Elements elements` và `Types types`; chương trình chạy đầy đủ ở mục 6 sẽ sử dụng chính cách này.

Các phương thức quan trọng:

| Phương thức | Kết quả | Khi nào sử dụng |
| --- | --- | --- |
| `getElementUtils()` | `Elements` | Tra cứu class/method/package/module, tên, annotations |
| `getTypeUtils()` | `Types` | Kiểm tra kiểu, generic, subtype, assignability |
| `getMessager()` | `Messager` | Báo lỗi/cảnh báo/ghi chú gắn với `Element` |
| `getFiler()` | `Filer` | Sinh source/class/resource theo hợp đồng của compiler |
| `getOptions()` | `Map<String,String>` | Đọc tùy chọn `-Akey=value` do build cấu hình |
| `getSourceVersion()` | `SourceVersion` | Biết mức ngôn ngữ nguồn được công cụ cấu hình |
| `getLocale()` | `Locale` hoặc `null` | Định dạng thông điệp phù hợp locale |
| `isPreviewEnabled()` | `boolean` | Kiểm tra phiên xử lý có bật preview features hay không |

Ví dụ đọc tùy chọn riêng (snippet minh họa, không nằm trong chương trình ở mục 6):

~~~java
String mode = processingEnv.getOptions()
        .getOrDefault("service.mode", "strict");
~~~

Nếu processor hỗ trợ tùy chọn này, có thể khai báo `@SupportedOptions("service.mode")` rồi truyền `-Aservice.mode=strict` cho `javac`. Đọc `getOptions()` không làm giá trị tự thay đổi logic: processor phải tự xử lý nó.

**Vòng đời:** đừng lưu `ProcessingEnvironment`, `Elements` hay `Types` vào cache tĩnh để dùng qua **những phiên biên dịch khác nhau**. Chúng phụ thuộc vào môi trường phân tích kiểu của lần chạy hiện tại. Phép tra cứu và các `Element`/`TypeMirror` nên được sử dụng trong phạm vi phiên biên dịch mà processor đang xử lý.

## 4. `Elements` là gì? Mô hình khai báo thay vì đối tượng runtime

### 4.1. `Element` đại diện cho cấu trúc chương trình

Các đối tượng phổ biến:

- `TypeElement`: khai báo class/interface/enum/annotation type/record.
- `ExecutableElement`: khai báo method, constructor hoặc initializer thuộc những dạng được mô hình hỗ trợ.
- `VariableElement`: field, parameter, enum constant, local variable trong ngữ cảnh liên quan.
- `PackageElement` và `ModuleElement`: package và module được nhận biết trong môi trường biên dịch.
- `AnnotationMirror`, `AnnotationValue`: mô hình annotation và giá trị annotation mà không bắt buộc phải có đối tượng runtime.

Từ `Element` có thể lấy `getSimpleName()`, `getKind()`, `getModifiers()`, `getEnclosingElement()`, `getEnclosedElements()` và `asType()`. Đối với một class, ép sang `TypeElement` **sau khi kiểm tra `ElementKind` thích hợp** để dùng API cấp type.

`Element#getKind()` mô tả **loại khai báo** (ví dụ `CLASS`, `INTERFACE`, `METHOD`); trong khi `TypeMirror#getKind()` mô tả **loại kiểu** (ví dụ `DECLARED`, `ARRAY`, `TYPEVAR`, `ERROR`). Hai loại kind này không thể hoán đổi.

### 4.2. Các phương thức `Elements` thường dùng

| API | Ý nghĩa / lưu ý |
| --- | --- |
| `getTypeElement("demo.Service")` | Tìm `TypeElement` theo canonical name nếu phân giải được duy nhất; có thể trả `null` |
| `getPackageElement("demo")` | Tra cứu package, có thể `null` |
| `getBinaryName(type)` | Trả binary name; lớp lồng nhau có thể chứa dấu `$` |
| `getPackageOf(element)` | Lấy package chứa khai báo |
| `getModuleOf(element)` | Lấy module chứa phần tử trong môi trường hỗ trợ module |
| `getAllMembers(type)` | Tập member khai báo trực tiếp **và thừa kế**, gồm cả constructor của class |
| `getAllAnnotationMirrors(element)` | Lấy annotation theo quy tắc inheritance của model |
| `getElementValuesWithDefaults(annotationMirror)` | Đọc giá trị annotation kể cả default |
| `getDocComment(element)` | Lấy nội dung comment tài liệu nếu có |
| `getTypeElement(module, name)` | Tra cứu type trong **module cụ thể** khi cần phân biệt nhiều module |

**Tên khác nhau có mục đích khác nhau:** `getQualifiedName()` của `TypeElement` thường là canonical name, còn `Elements.getBinaryName(...)` cho kết quả theo dạng JVM binary name (chẳng hạn `demo.Outer$Inner`). Không nên tự nối chuỗi/dò tên lớp lồng nhau bằng quy tắc không đầy đủ.

Khi có nhiều module cùng chứa tên type phù hợp, `getTypeElement(name)` **có thể trả `null` vì không xác định duy nhất**, không chỉ vì lớp vắng mặt. Dùng overload có `ModuleElement` hoặc `getAllTypeElements(name)` khi thật sự cần phân biệt theo module.

**Lựa chọn API:** dùng `element.getEnclosedElements()` khi cần thành viên **khai báo ngay tại lớp**; dùng `elements.getAllMembers(type)` khi cần cả những thành viên được kế thừa. Với generic inherited method, chỉ nhìn `ExecutableElement#getReturnType()` tại khai báo có thể chưa phản ánh substitution theo kiểu con: khi cần ngữ cảnh generic, dùng `Types.asMemberOf(...)` ở phần sau.

## 5. `Types`: quan hệ giữa các kiểu ở compile time

`TypeMirror` mô tả kiểu Java trong model. Nó không phải `Class<?>` và không đòi hỏi load runtime. Trong processor:

~~~java
TypeElement service = elements.getTypeElement("demo.Service");
TypeMirror serviceType = service.asType();
TypeMirror candidateType = candidate.asType();
boolean allowed = types.isAssignable(candidateType, serviceType);
~~~

Đoạn trên là **snippet bên trong processor** với `elements`, `types`, `candidate` đã được khởi tạo và `service != null`. `isAssignable(from, to)` mang hướng **giá trị kiểu from gán được cho biến kiểu to hay không**. Trong demo, nếu class `GoodService implements Service` thì kết quả là `true`. Nếu `BadService` không implements `Service` thì kết quả là `false`.

### 5.1. Phân biệt `isSameType`, `isSubtype` và `isAssignable`

| Phương thức | Hỏi điều gì? | Ví dụ ý nghĩa |
| --- | --- | --- |
| `types.isSameType(a, b)` | Hai `TypeMirror` có biểu diễn cùng kiểu không? | `String` so với `String` |
| `types.isSubtype(a, b)` | Kiểu `a` có là subtype của `b` không? | `ArrayList<String>` là subtype của `List<String>` |
| `types.isAssignable(a, b)` | Giá trị kiểu `a` có thể gán cho biến kiểu `b` không? | Có thể bao gồm conversion cho phép trong assignment context |
| `types.erasure(t)` | Kiểu `t` sau type erasure là gì? | `List<String>` được xóa tham số kiểu thành raw `List` |
| `types.directSupertypes(t)` | Các supertype trực tiếp là gì? | Xác định quan hệ kế thừa từng lớp |
| `types.getDeclaredType(element, args...)` | Tạo `DeclaredType` có tham số kiểu cụ thể | `List<String>` từ `List` và `String` |
| `types.asMemberOf(containing, member)` | Kiểu của member khi nhìn qua một kiểu generic cụ thể | `T get()` của `Box<String>` có return type `String` |
| `types.asElement(type)` | Ánh xạ một kiểu có khai báo tương ứng sang `Element` | Từ `DeclaredType` đến type declaration |
| `types.boxedClass(primitive)`, `unboxedType(wrapper)` | Boxing và unboxing trong mô hình kiểu | `int` ↔ `Integer` |

**Không so `TypeMirror` bằng `==` hay `equals()` để kết luận đồng nhất ngữ nghĩa.** Hãy dùng `Types.isSameType(...)`; cần lưu ý riêng theo đặc tả: khi **một đối số là wildcard**, `isSameType` có thể trả `false` ngay cả nếu dùng cùng đối tượng wildcard cho cả hai đối số. Và `isAssignable` **không đồng nghĩa** với `isSubtype`: gán biến có thể cho phép conversion ngoài quan hệ subtype thuần.

Không dùng `isAssignable(candidate.asType(), required.asType())` đảo ngược thứ tự nếu bạn muốn kiểm tra “ứng viên implements hợp đồng”. Thứ tự ở ví dụ demo là chính xác.

### 5.2. Kiểu có tham số generic

Giả sử có:

~~~java
interface Box<T> {
    T get();
}
~~~

Đây là **khai báo minh họa riêng**, không thuộc file demo phía dưới. Trong một processor có thể lấy `TypeElement` của `Box` và `String`, rồi dùng `types.getDeclaredType(boxElement, stringElement.asType())` để biểu diễn `Box<String>`. Sau đó `types.asMemberOf((DeclaredType) boxOfString, getMethodElement)` mô tả chữ ký method `get()` **khi được nhìn từ `Box<String>`**, với kiểu trả về là `String` thay vì biến kiểu `T` tại khai báo gốc.

Chú ý:

- `TypeElement` đại diện cho **khai báo generic** `Box<T>`; `DeclaredType` có thể đại diện một **lần áp dụng tham số** `Box<String>`.
- `TypeMirror` không nhất thiết là `DeclaredType`: primitive, array, type variable, executable type, error type... có các subinterface và `TypeKind` khác.
- `types.erasure(...)` chỉ dùng khi **chủ ý bỏ thông tin generic**. Đừng vô tình kiểm tra `List<String>` và `List<Integer>` bằng erasure rồi kết luận chúng tương đương.
- Để duyệt method overload/cấu trúc phương thức, sử dụng `ExecutableElement`, `ExecutableType` và `Types.isSubsignature(...)` khi cần kiểm tra chữ ký theo đặc tả.
- Trong quá trình biên dịch nhiều round, có thể xuất hiện `ErrorType` đối với kiểu chưa phân giải được; không kết luận ngay kiểu “không tồn tại mãi mãi” nếu processor khác có thể sinh mã trong round kế tiếp.

## 6. Ví dụ Java 17+ hoàn chỉnh: dùng `ProcessingEnvironment`, `Elements` và `Types` để kiểm tra service

Bài toán: một annotation `@VerifiedService` chỉ được phép đánh dấu **class triển khai interface `demo.Service`**. Processor sẽ:

1. Lấy `Elements` và `Types` từ `ProcessingEnvironment` trong `init(...)`.
2. Dùng `elements.getTypeElement("demo.Service")` để tìm khai báo hợp đồng.
3. Dùng `RoundEnvironment.getElementsAnnotatedWith(...)` để lấy các class có annotation.
4. Dùng `types.isAssignable(candidate.asType(), contract.asType())` để quyết định ứng viên có gán được vào `Service` không.
5. Dùng `elements.getBinaryName(candidate)` đưa tên lớp vào diagnostic.
6. In `NOTE` nếu hợp lệ; in `ERROR` nếu class không triển khai hợp đồng, khiến `javac` trả mã lỗi.

Đây là **processor kiểm tra mã nguồn ở thời điểm build**, không phải logic chạy trong `main`.

### 6.1. Cấu trúc file

~~~text
annotation-demo/
└── src/
    └── demo/
        ├── VerifiedService.java
        ├── Service.java
        ├── ServiceProcessor.java
        ├── GoodService.java
        └── BadService.java
~~~

### 6.2. Annotation được xử lý

`src/demo/VerifiedService.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface VerifiedService {}
~~~

`RetentionPolicy.SOURCE` là phù hợp khi annotation chỉ dùng để **kiểm tra trong lúc biên dịch**; chương trình chạy không cần lưu metadata annotation vào class file. Điều này không có nghĩa annotation processor chỉ có thể xử lý annotation có retention `SOURCE`: các retention khác cũng có thể được processor quan sát khi biên dịch.

### 6.3. Hợp đồng service

`src/demo/Service.java`:

~~~java
package demo;

public interface Service {
    String execute();
}
~~~

### 6.4. Processor sử dụng cả `Elements` và `Types`

`src/demo/ServiceProcessor.java`:

~~~java
package demo;

import java.util.Set;
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

@SupportedAnnotationTypes("demo.VerifiedService")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class ServiceProcessor extends AbstractProcessor {
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

        TypeElement contract = elements.getTypeElement("demo.Service");
        if (contract == null) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, "Cannot resolve demo.Service");
            return true;
        }

        for (Element element :
                round.getElementsAnnotatedWith(VerifiedService.class)) {
            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, "Only classes are supported",
                        element);
                continue;
            }

            TypeElement candidate = (TypeElement) element;
            boolean valid =
                    types.isAssignable(candidate.asType(), contract.asType());
            String name = elements.getBinaryName(candidate).toString();

            if (valid) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.NOTE,
                        "Accepted service: " + name, candidate);
            } else {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Must implement demo.Service: " + name, candidate);
            }
        }
        return true;
    }
}
~~~

**Những chi tiết đáng chú ý:**

- `AbstractProcessor` có trường `processingEnv` được thiết lập khi gọi `super.init(environment)`; đây là môi trường do compiler truyền vào, không tự tạo bằng `new ProcessingEnvironment(...)`.
- `@SupportedAnnotationTypes("demo.VerifiedService")` chỉ rõ processor hỗ trợ annotation nào. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` tuyên bố mức ngôn ngữ được hỗ trợ; lệnh ví dụ dùng `--release 17` nhất quán với nó. Nếu muốn hỗ trợ mức nguồn mới hơn, cập nhật/kiểm thử processor thay vì mặc định nhận mọi tính năng mới.
- `round.processingOver()` cho biết round cuối, nơi không nên tiếp tục giả định còn nguồn mới để xử lý. Ví dụ không sinh file nên chỉ xác thực annotation được thấy.
- `ElementKind.CLASS` bảo đảm ép kiểu `TypeElement` an toàn theo bài toán. Annotation đã có `@Target(TYPE)` nên có thể áp dụng cho một số loại khai báo type khác; ví dụ cố ý chỉ chấp nhận class.
- `getTypeElement("demo.Service")` trả `null` nếu type không phân giải được duy nhất ở môi trường hiện tại. Processor phát lỗi thay vì bỏ qua kiểm tra.
- `isAssignable(candidate, contract)` kiểm tra **tính hợp lệ của quan hệ kiểu**, không so tên lớp dưới dạng `String`.
- `Messager.printMessage(kind, message, candidate)` gắn diagnostic với vị trí khai báo ứng viên. Compiler quyết định trình bày đường dẫn/dòng/cột tương ứng.
- Trả `true` từ `process(...)` nghĩa là processor **claim các annotation được giao**; nó không có nghĩa mọi class đều hợp lệ hoặc vòng biên dịch đã kết thúc ngay lập tức. Nếu muốn các processor khác tiếp tục nhận cùng annotation, cần thiết kế `return false` theo hợp đồng phối hợp.

### 6.5. Trường hợp hợp lệ

`src/demo/GoodService.java`:

~~~java
package demo;

@VerifiedService
public final class GoodService implements Service {
    @Override
    public String execute() {
        return "READY";
    }

    public static void main(String[] args) {
        System.out.println("Service: " + new GoodService().execute());
    }
}
~~~

### 6.6. Trường hợp bị từ chối

`src/demo/BadService.java`:

~~~java
package demo;

@VerifiedService
public final class BadService {
}
~~~

`BadService` không triển khai `Service` nhưng có `@VerifiedService`; processor sẽ báo `Diagnostic.Kind.ERROR`. File này **chỉ được đưa vào lần biên dịch kiểm thử lỗi riêng**, không đưa vào lần build thành công.

### 6.7. Biên dịch processor và chạy thử (Java 17+)

Từ thư mục `annotation-demo`, trên Linux/macOS:

~~~sh
mkdir -p build/processor build/classes
javac --release 17 -d build/processor src/demo/VerifiedService.java src/demo/ServiceProcessor.java
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.ServiceProcessor -d build/classes src/demo/Service.java src/demo/GoodService.java
java -cp build/classes demo.GoodService
~~~

Trên Windows PowerShell, thay lệnh tạo thư mục đầu bằng:

~~~powershell
New-Item -ItemType Directory -Force build/processor,build/classes | Out-Null
~~~

Ba lệnh `javac`/`java` còn lại chạy tương tự vì chúng chỉ tham chiếu **một thư mục** ở mỗi tham số `-cp` và `-processorpath`. Với classpath gồm nhiều thư mục/JAR, ký tự phân tách đường dẫn tùy hệ điều hành (Windows thường là dấu `;`; Linux/macOS là dấu `:`).

**Giải thích thứ tự build:**

1. Biên dịch `VerifiedService` và `ServiceProcessor` vào `build/processor` để compiler có thể **nạp và chạy processor** ở lần biên dịch tiếp theo.
2. `-cp build/processor` cho source đang biên dịch thấy `demo.VerifiedService`. `-processorpath build/processor` cho compiler thấy processor và dependency của nó ở đường dẫn riêng.
3. `-processor demo.ServiceProcessor` **kích hoạt processor tường minh**. Không phụ thuộc compiler có tự phát hiện processor nằm ngẫu nhiên trong classpath hay không.
4. Processor kiểm tra `GoodService`, rồi `javac` xuất class file vào `build/classes`.
5. Chương trình chạy `GoodService.main(...)` và in kết quả.

**Stdout chính xác của chương trình `java`** (đã kiểm tra trên JDK 24):

~~~text
Service: READY
~~~

Trong bước `javac`, processor đồng thời phát một `NOTE` có nội dung:

~~~text
Accepted service: demo.GoodService
~~~

Thông điệp trên là **phần nội dung diagnostic**, không phải toàn bộ stdout cố định của `javac`. Trình biên dịch/IDE có thể in thêm đường dẫn, dòng, caret và tiền tố `Note:` hoặc trình bày thông điệp qua diagnostics API; vì vậy không nên buộc toàn bộ log compiler phải có định dạng byte-for-byte giống nhau trên mọi máy.

**Kiểm thử nhánh lỗi:** sau đó chạy riêng:

~~~sh
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.ServiceProcessor -d build/classes src/demo/Service.java src/demo/BadService.java
~~~

Lệnh được kỳ vọng **thất bại với exit code khác 0**, có diagnostic chứa:

~~~text
error: Must implement demo.Service: demo.BadService
~~~

Vì `BadService` không implements `Service`. Nếu processor không chạy thì không có diagnostic này, nên phép thử âm tính giúp kiểm tra wiring annotation processing. Không gọi `java demo.BadService` như một ví dụ thành công; compilation được thiết kế để thất bại. Cả hai nhánh đã được kiểm tra bằng `javac` của JDK 24.

## 7. Phân biệt hai tầng “đối tượng” trong processor

Xét khai báo:

~~~java
package example;

class Box<T> {
    T value;
    T get() { return value; }
}
~~~

Đây là **đoạn source giả lập để phân tích**, không nằm trong dự án `annotation-demo`. Processor có thể gặp hai lớp dữ liệu:

**Tầng phần tử (declaration):**

- `TypeElement`: khai báo `Box<T>`.
- `VariableElement`: field `value`.
- `ExecutableElement`: method `get()`.
- `TypeParameterElement`: khai báo tham số kiểu `T`.

**Tầng kiểu (type):**

- `DeclaredType`: một lần sử dụng như `Box<String>`.
- `TypeVariable`: kiểu `T`.
- `ExecutableType`: kiểu đầy đủ của method `get()` khi đặt trong ngữ cảnh.
- `TypeMirror` biểu diễn `java.lang.String`, `T`, array, primitive... tùy vị trí.

Một `Element` có thể được ánh xạ sang `TypeMirror` với `element.asType()`; có thể cần `types.asElement(typeMirror)` để đi theo hướng ngược lại đối với các kiểu **có phần tử khai báo tương ứng**, nhưng không phải mọi kiểu đều có element (`int`, `void`, wildcard...).

Chỉ dùng `element.toString()` hoặc `typeMirror.toString()` để in log là chấp nhận được; **không dựa vào chuỗi đó để thực hiện so sánh ngữ nghĩa kiểu**. Hãy dùng API `Types`.

### 7.1. Generic method và `Types.asMemberOf`

Ví dụ `Box<T>.get()` khai báo trả `T`. Khi xét `Box<String>`, một processor muốn biết kiểu method **nhìn trong ngữ cảnh cụ thể** phải dùng `Types.asMemberOf(declaredBoxOfString, getMethodElement)` để nhận một `ExecutableType` có kiểu trả về đã được thay `T` bằng `String`.

Có thể xây dựng kiểu generic cụ thể bằng `types.getDeclaredType(boxElement, stringElement.asType())`, rồi tìm method từ `getAllMembers(boxElement)` hoặc `getEnclosedElements()` tùy bài toán. Việc đọc trực tiếp `ExecutableElement#getReturnType()` của khai báo gốc sẽ chưa thể hiện đầy đủ tất cả phép thay tham số generic.

Đây là lý do các framework kiểm tra type-safe mapping, dependency injection, serializer hay source generator dùng **`Elements` để tìm khai báo** và **`Types` để tính đúng quan hệ kiểu**.

## 8. Vòng xử lý và ý nghĩa của `RoundEnvironment`

Annotation processing có thể chạy qua **nhiều round** khi processor sinh thêm source. Mỗi round, framework cung cấp `RoundEnvironment` để truy cập các phần tử phù hợp với trạng thái biên dịch hiện tại.

Những điểm quan trọng:

- `round.getElementsAnnotatedWith(MyAnnotation.class)` lấy các phần tử mang annotation tương ứng ở round hiện tại; không mặc định hiểu đó là **toàn bộ dự án ở mọi round**.
- `round.processingOver()` cho biết round cuối. Lúc đó không nên tiếp tục cố sinh source mới như một cách tạo thêm round.
- `round.errorRaised()` báo tình trạng có lỗi từ round trước; processor có thể dùng để quyết định có nên tiếp tục tạo artifact hay không.
- `getFiler().createSourceFile(...)` sinh tệp nguồn mới, thường làm xuất hiện round sau; file được sinh có thể chứa annotation mà các processor khác tiếp tục xử lý.
- Không tạo **cùng một path/FQN đầu ra nhiều lần trong một phiên processing**. `Filer` theo dõi tên đã tạo và có thể ném `FilerException` khi trùng. Cần cơ chế ghi một lần và phân biệt round.
- Một processor nên xử lý riêng trường hợp không có phần tử phù hợp. Đừng giả định `getElementsAnnotatedWith(...)` luôn trả một tập khác rỗng.

**Phân biệt trách nhiệm:** `RoundEnvironment` cho biết **đối tượng cần xử lý ở round này**; `Elements`/`Types` cho biết **cách tra cứu, diễn giải và kiểm tra kiểu của các đối tượng ấy**; `ProcessingEnvironment` cung cấp **các công cụ xuyên suốt lần chạy processor**.

Trong ví dụ trên không sinh file, nên không cần cấu trúc chống sinh trùng. Nhưng việc kiểm tra `processingOver()` và dùng đối tượng `round` cho mỗi lời gọi `process` vẫn đúng theo cách tổ chức API hiện đại.

## 9. Lưu ý về kích hoạt processor trên các phiên bản JDK hiện đại

**Không nên dựa vào việc compiler tự chạy mọi processor tìm được trên classpath**. Kể từ JDK 23, việc chạy annotation processor cần được cấu hình tường minh; đây là thay đổi quan trọng đối với môi trường hiện hành.

Các tùy chọn phổ biến:

| Tùy chọn của `javac` | Tác dụng |
| --- | --- |
| `-processor demo.ServiceProcessor` | Chỉ đích danh processor; ví dụ này sử dụng cách đó |
| `-processorpath <path>` hoặc `--processor-path <path>` | Đường dẫn để tìm processor ở classpath mode |
| `--processor-module-path <path>` | Đường dẫn module chứa processor khi dùng processor module |
| `-proc:full` | Bật annotation processing và biên dịch (JDK hỗ trợ tùy chọn này) |
| `-proc:only` | Chỉ chạy processor, không thực hiện biên dịch thông thường sau đó |
| `-proc:none` | Tắt annotation processing |

Với project Maven/Gradle, hãy khai báo processor và dependency của nó trong **cấu hình annotation processor** của build tool, thay vì chỉ thêm processor như thư viện runtime thông thường. Xác nhận phiên bản plugin/build tool xử lý đúng JDK đang sử dụng.

Nếu không chỉ định `-processor` thì công cụ có thể tìm processor từ service descriptor `META-INF/services/javax.annotation.processing.Processor` trên processor path hoặc đăng ký `provides ... with ...` trong module tương ứng. Ví dụ này **không cần tạo service descriptor**, vì đã khai báo processor bằng `-processor`.

**Tách đường dẫn:** classpath của source cần để giải quyết annotation và dependency; processor path là nơi compiler **nạp mã của processor để chạy lúc build**. Chúng có thể khác nhau. Không đưa mã của processor thực thi lúc build vào production classpath nếu ứng dụng runtime không có nhu cầu sử dụng.

## 10. Chẩn đoán và lỗi thường gặp khi dùng `Elements` / `Types`

### 10.1. `getTypeElement(...) == null`

Có thể do class không ở trên source/classpath/module path, sai canonical name, hoặc không xác định duy nhất trong môi trường nhiều module. Hãy kiểm tra dependency, module context và thời điểm xử lý. Trong source generator nhiều round, một loại hiện chưa được sinh có thể cần đợi round tiếp theo; không nên mặc định phép tra cứu đầu tiên `null` nghĩa là “mã mãi mãi không tồn tại”.

### 10.2. `TypeMirror` là `ErrorType`

Khi compiler đang xử lý source chưa phân giải được, `TypeMirror#getKind()` có thể là `TypeKind.ERROR`. Tùy bài toán, processor có thể hoãn một phép kiểm tra cho đến round sau hoặc phát diagnostic rõ ràng, nhưng không xử lý `ErrorType` như một `DeclaredType` hoàn toàn đã sẵn sàng trong mọi trường hợp.

### 10.3. So sánh sai kiểu hoặc sai chiều quan hệ

- Sai: `candidate.asType().equals(contract.asType())` để hỏi candidate có implements interface không.
- Sai: `types.isAssignable(contract.asType(), candidate.asType())` khi muốn hỏi candidate có thể dùng như contract không.
- Đúng cho câu hỏi của demo: `types.isAssignable(candidate.asType(), contract.asType())`.
- Khi cần **kiểu giống hệt** dùng `isSameType`; khi cần **subtype** dùng `isSubtype`; khi cần **gán được** dùng `isAssignable`.

Với generic, không tự suy luận theo tên type hoặc chỉ so erasure rồi kết luận an toàn kiểu; dùng `getDeclaredType`/`asMemberOf` khi ngữ cảnh có type arguments.

### 10.4. Dùng reflection thay cho mô hình biên dịch

Mã nguồn đang được xử lý thường **chưa được định nghĩa thành `Class<?>` trong JVM chạy processor**. Không gọi `Class.forName("demo.GoodService")` để kiểm tra class nguồn vừa gõ, vì classpath của processor và chương trình đích khác nhau. Dùng `elements.getTypeElement(...)` và `Types` để đọc metadata nguồn.

Đối với annotation có thuộc tính kiểu `Class<?>`, việc gọi trực tiếp annotation proxy có thể gây `MirroredTypeException` vì kiểu đích chưa loadable ở JVM processor. Khi cần xử lý annotation phức tạp, dùng `AnnotationMirror` và `AnnotationValue` từ mô hình compiler thay vì reflection.

### 10.5. Bộ xử lý không chạy

Nếu build thành công nhưng thiếu diagnostic hoặc source được sinh:

- Kiểm tra `-processor` hoặc cấu hình build tool có thực sự bật processor không.
- Kiểm tra `-processorpath` và dependency của processor.
- Kiểm tra processor hỗ trợ annotation và source version tương ứng.
- Xác nhận không có `-proc:none` làm vô hiệu hóa processing.
- Thử test âm tính tương tự `BadService`: nếu class không hợp lệ vẫn compile thành công, rất có thể processor chưa được gọi.

### 10.6. Quản lý lỗi thay vì in stdout tự do

Dùng `processingEnv.getMessager().printMessage(...)` thay cho `System.out.println(...)` để báo lỗi build. `Messager` liên kết thông điệp với một `Element` hoặc annotation value, cho IDE/build tool cơ hội đánh dấu đúng vị trí source. Khi phát `Diagnostic.Kind.ERROR`, compilation thường thất bại; `NOTE` có thể chỉ là thông tin. Định dạng in ra của compiler không phải hợp đồng ổn định trên mọi IDE.

## 11. Cách thiết kế processor bền vững

1. **Khởi tạo một lần:** lấy `Elements`, `Types`, `Messager`/`Filer` từ `ProcessingEnvironment` sau `super.init`.
2. **Duyệt theo round:** dùng `RoundEnvironment`; tránh tạo file trùng hoặc lặp công việc không cần thiết.
3. **Dùng mô hình đúng tầng:** `Element` cho khai báo, `TypeMirror` cho kiểu; tránh parse chuỗi khi API có phép tính type-safe.
4. **Kiểm tra `null`/`TypeKind.ERROR` khi tra cứu:** xử lý dependency và multi-round rõ ràng.
5. **Phát diagnostic tại phần tử liên quan:** giúp IDE và CI gắn lỗi với source cụ thể.
6. **Quản lý options/source version:** khai báo `@SupportedAnnotationTypes`, `@SupportedSourceVersion`, `@SupportedOptions` khi cần.
7. **Đăng ký tường minh:** cấu hình processor path/module path và activation tương thích JDK hiện tại; không phụ thuộc auto-discovery tình cờ.
8. **Tách processor khỏi runtime ứng dụng:** processor là mã chạy **lúc biên dịch**, không phải dịch vụ runtime mặc định.
9. **Kiểm thử cả pass và fail:** test processor được thực sự gọi, báo đúng diagnostic, xử lý generics/multiple rounds và dependency.
10. **Không làm build phụ thuộc môi trường không cần thiết:** hạn chế I/O mạng, thời gian chạy không xác định, state static dùng chung hoặc side effect ngoài Filer.

Annotation processor có quyền thực thi mã Java trong JVM của công cụ build. Chỉ kích hoạt processor và dependency từ nguồn đáng tin cậy; tách processor path khỏi runtime classpath giúp việc quản trị nguồn code được thực thi trong CI dễ kiểm soát hơn.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `ProcessingEnvironment` và `RoundEnvironment` khác nhau thế nào?

**Đáp:** `ProcessingEnvironment` cung cấp công cụ và cấu hình cho processor trong **một phiên chạy**; `RoundEnvironment` cho biết trạng thái và phần tử của **round hiện tại**.

**Câu 2.** Muốn biết `GoodService implements Service`, nên so tên kiểu hay gọi API nào?

**Đáp:** Lấy `TypeMirror` từ cả hai `TypeElement` và dùng `types.isAssignable(goodService.asType(), service.asType())`. Không so chuỗi hoặc ép kiểu runtime `Class<?>`.

**Câu 3.** Muốn biết method kế thừa của `Box<String>` có kiểu trả về nào sau khi generic được thế bằng `String`, nên dùng gì?

**Đáp:** `Elements` tìm member, `Types.asMemberOf(...)` xét kiểu method **trong ngữ cảnh `DeclaredType Box<String>`**, thay vì chỉ đọc kiểu khai báo gốc.

**Câu 4.** `javac` biên dịch source có `@VerifiedService` nhưng không chạy processor, có thể kết luận annotation hợp lệ không?

**Đáp:** Không. Annotation Java đơn thuần không tự kích hoạt việc kiểm tra nghiệp vụ. Cần cấu hình processor tường minh và kiểm thử nhánh lỗi như `BadService`.

**Câu 5.** `getTypeElement("demo.Service") == null` có luôn có nghĩa source không thể tồn tại không?

**Đáp:** Không. Type có thể thiếu dependency, chưa được sinh ở round hiện tại, hoặc không được xác định duy nhất vì phạm vi module. Phải xử lý theo ngữ cảnh compile.

**Ghi nhớ:** `ProcessingEnvironment` là **đầu mối cấp công cụ**; `Elements` làm việc với **khai báo Java**; `Types` trả lời **câu hỏi ngữ nghĩa về kiểu**. Dùng đúng bộ ba này với `RoundEnvironment` và `Messager` để viết annotation processor kiểm tra source an toàn về kiểu, đưa lỗi chính xác và chạy ổn định trên JDK hiện đại.

### Tài liệu tham khảo hiện hành

- [Oracle Java SE 26 — ProcessingEnvironment](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/ProcessingEnvironment.html): `getElementUtils`, `getTypeUtils`, `getMessager`, `getFiler`, options và source version.
- [Oracle Java SE 26 — Elements](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Elements.html): tra cứu phần tử, members, package/module và binary name.
- [Oracle Java SE 26 — Types](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/util/Types.html): assignability, subtyping, generic và type erasure.
- [Oracle Java SE 26 — AbstractProcessor](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): `init`, `process`, claim annotations và supported declarations.
- [Oracle Java SE 25 — javac tool reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): cấu hình và kích hoạt annotation processing theo cơ chế hiện hành.
