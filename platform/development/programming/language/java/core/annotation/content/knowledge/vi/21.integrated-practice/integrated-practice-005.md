# Viết annotation processor phát hiện khai báo không hợp lệ trong Java

## 1. Mục tiêu thực hành

Một **annotation processor** có thể chạy ngay trong quá trình `javac` biên dịch chương trình để kiểm tra những khai báo có gắn annotation và đưa ra thông báo lỗi có vị trí chính xác. Nhờ vậy, một quy tắc nghiệp vụ hoặc quy ước kiến trúc có thể được **kiểm tra trước khi ứng dụng chạy**, thay vì đợi đến runtime.

Trong bài này, ta thiết kế annotation `@Route` cho method xử lý một đường dẫn. Hợp đồng đơn giản của nó là:

- Chỉ dùng trên **method của class**, không dùng trên field hay interface method.
- Method phải **`public`, không `static`, không `abstract`**.
- Method **không có tham số**.
- Kiểu trả về phải **đúng `java.lang.String`**.
- Giá trị `path` phải khớp biểu thức chính quy `/[a-z][a-z0-9/-]*`, ví dụ `/health` hoặc `/users`.
- Trong **cùng một class**, không được có hai method hợp lệ dùng cùng `path`.

Ví dụ **hợp lệ**:

~~~java
@Route(path = "/health")
public String health() {
    return "ok";
}
~~~

Ví dụ **không hợp lệ**:

~~~java
@Route(path = "health")
private static int health(int code) {
    return code;
}
~~~

Ví dụ thứ hai vi phạm nhiều quy tắc cùng lúc. Processor sẽ phát hiện bằng API tiêu chuẩn `javax.annotation.processing` và `javax.lang.model`, rồi gửi `Diagnostic.Kind.ERROR` cho compiler. `javac` sẽ trả exit code khác 0 khi có lỗi; chương trình không được coi là đã build thành công.

**Phạm vi của bài:** kiểm tra các **declaration có annotation**, không tự ý sửa AST, không thêm method vào class, không tạo ứng dụng HTTP server. `@Route` chỉ là một ví dụ annotation do chúng ta định nghĩa; nó không phải annotation có sẵn của JDK hay một framework web.

## 2. Các công cụ trong Java Annotation Processing

Java SE 17 cung cấp JSR 269 trong module `java.compiler`. Những thành phần chính:

| API | Vai trò trong bài |
|---|---|
| `AbstractProcessor` | Lớp cơ sở giúp triển khai annotation processor |
| `@SupportedAnnotationTypes` | Công bố tên annotation type mà processor hỗ trợ |
| `@SupportedSourceVersion` | Công bố phiên bản ngôn ngữ mà processor hỗ trợ |
| `process(annotations, round)` | Entry point được compiler gọi trong các processing rounds |
| `RoundEnvironment.getElementsAnnotatedWith(...)` | Lấy các element mang annotation trong round hiện tại |
| `Element.getKind()` / `ElementKind` | Phân biệt method, field, class, record... |
| `ExecutableElement` | Đọc modifier, tham số, kiểu trả về của method |
| `TypeMirror` và `Types.isSameType(...)` | So sánh kiểu theo mô hình type system |
| `AnnotationMirror`, `AnnotationValue` | Đọc giá trị annotation khi biên dịch |
| `Elements.getElementValuesWithDefaults(...)` | Lấy cả giá trị tường minh và `default` |
| `Messager.printMessage(...)` | Báo lỗi, cảnh báo hoặc ghi chú cho compiler |

Một processor thông thường **không cần `java.lang.reflect.Method` hay `Class.forName` để phân tích class nguồn**. Khi compiler còn đang phân tích source, class đích thậm chí chưa có `.class` để runtime reflection load.

Processor cũng không cần annotation có `RetentionPolicy.RUNTIME`. Với kiểm tra lúc biên dịch, retention `SOURCE` hoàn toàn phù hợp.

### Hai loại quy tắc cần tách riêng

1. **Quy tắc cú pháp và ngôn ngữ do `javac` kiểm tra sẵn:** chẳng hạn `@Target(ElementType.METHOD)` khiến `@Route` đặt trên field bị compiler bác bỏ.
2. **Quy tắc do chúng ta tự thiết kế:** chẳng hạn path phải bắt đầu bằng `/`, method không được `static`, hay hai routes trong class không được trùng nhau. Processor chịu trách nhiệm kiểm tra những điều này.

Không cần viết lại toàn bộ Java compiler bên trong annotation processor; chỉ kiểm tra các ràng buộc mà annotation type và ngôn ngữ chưa mô tả đủ.

## 3. Định nghĩa hợp đồng `@Route`

File **`src/demo/Route.java`**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.METHOD)
public @interface Route {
    String path() default "";
}
~~~

Các lựa chọn có chủ ý:

- `@Target(METHOD)` giới hạn nơi đặt annotation vào declaration method. Nếu đặt `@Route` trên class/field, compiler sẽ báo annotation không áp dụng cho loại declaration đó, trước hoặc trong quy trình biên dịch; không cần processor tự phát hiện một element không được phép gắn annotation.
- `@Retention(SOURCE)` nghĩa là metadata chỉ cần thiết khi biên dịch. Nó có thể được processor nhìn thấy qua model của compiler; không cần giữ lại ở runtime chỉ để xác thực các khai báo.
- `String path() default ""` giúp cú pháp `@Route` **hợp lệ về mặt annotation interface** dù không cung cấp `path`. Sau đó processor chủ động báo lỗi với chuỗi rỗng. Đây là ví dụ **tách cú pháp hợp lệ của Java khỏi hợp đồng nghiệp vụ**.
- Giá trị `path` phải là một compile-time constant expression kiểu `String`. Method call như `System.getenv(...)` không phải giá trị annotation hợp lệ ngay từ cấp độ ngôn ngữ.

Regex `/[a-z][a-z0-9/-]*` trong bài là **một chính sách mẫu**: bắt đầu bằng dấu slash, sau đó là chữ thường và các ký tự cho phép. Ví dụ `/health`, `/v1/users` hợp lệ; `health`, `/`, `/with space` không hợp lệ. Chính sách này **không phải chuẩn URI toàn diện**, không xử lý path variables, URL encoding, dấu slash liên tiếp, percent escapes hoặc quốc tế hóa. Khi đưa vào hệ thống thật, cần một specification rõ hơn.

## 4. Cấu trúc project độc lập để thử nghiệm

Dùng cấu trúc sau, tính từ thư mục `project/`:

~~~text
project/
├── RouteProcessor.java
├── src/
│   └── demo/
│       ├── Route.java
│       ├── ValidRoutes.java
│       ├── App.java
│       └── InvalidRoutes.java
├── processor/       # Tạo khi build
├── valid-classes/   # Tạo khi build
└── invalid-classes/ # Tạo khi build
~~~

`RouteProcessor.java` ở **default package** chỉ để đơn giản hóa command line. Source cần kiểm tra nằm trong package `demo`. Trong dự án thực tế, processor nên có package riêng, được đóng gói thành JAR, cấu hình `annotationProcessor`/`processorpath` và test như một module độc lập.

Trình tự thực hành:

1. Biên dịch **processor** trước.
2. Biên dịch ví dụ **hợp lệ** và chỉ định processor bằng `-processor RouteProcessor`.
3. Chạy ứng dụng; xác minh stdout.
4. Biên dịch ví dụ **không hợp lệ** bằng processor đó; kiểm tra diagnostic và exit code.
5. Hiểu vì sao compiler chặn build và cách cải thiện thông báo.

## 5. Code đầy đủ: `RouteProcessor.java`

File này **độc lập và biên dịch được với Java 17**. Processor kiểm tra declaration, đọc annotation argument và báo lỗi tại chính method vi phạm.

~~~java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.AnnotationValue;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.Modifier;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.Route")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class RouteProcessor extends AbstractProcessor {
    private final Set<String> registered = new HashSet<>();

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment round) {
        if (round.processingOver()) {
            return true;
        }

        TypeElement route = processingEnv.getElementUtils()
                .getTypeElement("demo.Route");
        TypeElement string = processingEnv.getElementUtils()
                .getTypeElement("java.lang.String");

        if (route == null || string == null) {
            return false;
        }

        for (Element element : round.getElementsAnnotatedWith(route)) {
            if (element.getKind() != ElementKind.METHOD) {
                error(element, "@Route requires a method");
                continue;
            }

            ExecutableElement method = (ExecutableElement) element;
            boolean ok = true;

            if (method.getEnclosingElement().getKind()
                    != ElementKind.CLASS) {
                error(method, "@Route requires a method in a class");
                ok = false;
            }

            Set<Modifier> modifiers = method.getModifiers();
            if (!modifiers.contains(Modifier.PUBLIC)
                    || modifiers.contains(Modifier.STATIC)
                    || modifiers.contains(Modifier.ABSTRACT)) {
                error(method,
                        "@Route method must be public, instance and concrete");
                ok = false;
            }

            if (!method.getParameters().isEmpty()) {
                error(method, "@Route method must have no parameters");
                ok = false;
            }

            if (!processingEnv.getTypeUtils().isSameType(
                    method.getReturnType(), string.asType())) {
                error(method, "@Route method must return String");
                ok = false;
            }

            String path = readPath(method, route);
            if (path == null
                    || !path.matches("/[a-z][a-z0-9/-]*")) {
                error(method, "@Route path must match /[a-z][a-z0-9/-]*");
                ok = false;
            }

            if (ok) {
                String key = method.getEnclosingElement().toString()
                        + "#" + path;
                if (!registered.add(key)) {
                    error(method,
                            "Duplicate @Route path in the same class: " + path);
                }
            }
        }

        return true;
    }

    private String readPath(
            ExecutableElement method,
            TypeElement annotationType) {

        for (AnnotationMirror mirror : method.getAnnotationMirrors()) {
            if (!mirror.getAnnotationType().asElement()
                    .equals(annotationType)) {
                continue;
            }

            for (Map.Entry<? extends ExecutableElement,
                           ? extends AnnotationValue> entry
                    : processingEnv.getElementUtils()
                        .getElementValuesWithDefaults(mirror).entrySet()) {

                if (entry.getKey().getSimpleName().contentEquals("path")) {
                    return (String) entry.getValue().getValue();
                }
            }
        }
        return null;
    }

    private void error(Element element, String message) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR,
                "[ROUTE] " + message,
                element);
    }
}
~~~

### 5.1. Vì sao không đọc annotation bằng reflection?

`method` là một **`ExecutableElement`** do compiler cung cấp, không phải `java.lang.reflect.Method`. Annotation có retention `SOURCE` có thể không tồn tại trong class file sau biên dịch; gọi runtime reflection để phân tích declaration này là không phù hợp.

Trong ví dụ, `readPath(...)` duyệt `AnnotationMirror` để tìm annotation type `demo.Route` và lấy phần tử `path`. Việc so `mirror.getAnnotationType().asElement().equals(annotationType)` dựa trên symbol model của cùng compilation environment.

`getElementValuesWithDefaults(mirror)` quan trọng vì `@Route` **không chỉ định `path`** phải được đọc thành `""` rồi bị rule validation từ chối. Nếu chỉ sử dụng `mirror.getElementValues()`, phần tử dùng default **không xuất hiện trong map**, dễ khiến code bỏ sót kiểm tra.

Với annotation hợp lệ về cú pháp, giá trị `path` được Java type-check là `String`, nên ví dụ cast `(String) entry.getValue().getValue()` phù hợp. Một processor tổng quát hơn cần xét nhiều loại `AnnotationValue` (primitive, enum, class, annotation lồng, array) thay vì giả định tất cả đều là String.

### 5.2. Vì sao dùng `Types.isSameType`?

Nếu gọi:

~~~java
method.getReturnType().toString().equals("java.lang.String")
~~~

ta đang so **chuỗi biểu diễn kiểu**, không phải quy tắc type system của compiler. Ví dụ chuẩn sử dụng:

~~~java
processingEnv.getTypeUtils().isSameType(
        method.getReturnType(),
        string.asType())
~~~

để yêu cầu đúng `java.lang.String`. Method trả về `Object`, `CharSequence`, `int`, `void` hoặc `StringBuilder` đều bị từ chối. Đây là chủ đích của bài: contract yêu cầu **đúng String**, không phải “bất cứ thứ gì chuyển thành chuỗi được”.

Cần phân biệt **equality** với **assignability**: nếu contract cần subtype của một interface, có thể xem `Types.isAssignable(...)` hoặc kiểm tra tương ứng thay vì `isSameType(...)`. Hãy quyết định theo mục đích thiết kế, không thay tuỳ tiện.

### 5.3. Vì sao kiểm tra `ElementKind` trước khi cast?

`RoundEnvironment.getElementsAnnotatedWith(...)` trả các `Element`. Muốn gọi `getParameters()`, `getReturnType()`, ta cần `ExecutableElement`, nhưng ép kiểu vô điều kiện có thể ném `ClassCastException` nếu processor được thay đổi/annotation target khác.

Vì vậy:

~~~java
if (element.getKind() != ElementKind.METHOD) {
    error(element, "@Route requires a method");
    continue;
}
ExecutableElement method = (ExecutableElement) element;
~~~

Ví dụ `@Target(METHOD)` vốn đã loại những vị trí khác ở tầng compiler, nhưng nhánh phòng vệ là hợp lý khi processor được mở rộng hoặc phải xử lý source đang có lỗi.

### 5.4. Vì sao báo lỗi ở `Element`?

`Messager.printMessage(Diagnostic.Kind.ERROR, message, element)` yêu cầu compiler gắn diagnostic với declaration liên quan. Với `javac`, thông báo thường chỉ đến dòng method và hiển thị caret `^`.

Không dùng `System.out.println("ERROR")` để thay thế: một dòng stdout **không tự khiến compiler coi build thất bại**. `Diagnostic.Kind.ERROR` mới biểu đạt lỗi biên dịch qua giao diện processor chuẩn.

### 5.5. Vì sao lưu đường dẫn đã thấy?

Processor xây key từ **tên khai báo class + path**, rồi thêm vào `HashSet`. Nếu một method thứ hai hợp lệ dùng cùng key, `Set.add(...)` trả `false` và phát diagnostic:

~~~text
[ROUTE] Duplicate @Route path in the same class: /dupe
~~~

Bản demo chỉ kiểm tra **trùng trong cùng class**, không cấm một đường dẫn giống nhau ở hai class. Nó cũng không tính inherited route methods, overload hierarchy, module/package scoping phức tạp hoặc route normalization. Đó là các quyết định API cần thiết kế thêm trong ứng dụng thật.

`registered` là **state của processor instance trong một compilation task**, nên giúp phát hiện trùng khi compiler xử lý các annotated elements thuộc nhiều vòng. Không xem `Set` này là database dùng lại giữa những lần build khác nhau.

## 6. Ví dụ đúng: `ValidRoutes.java` và `App.java`

Tạo **`src/demo/ValidRoutes.java`**:

~~~java
package demo;

public final class ValidRoutes {
    @Route(path = "/health")
    public String health() {
        return "ok";
    }

    @Route(path = "/users")
    public String users() {
        return "users";
    }
}
~~~

Cả hai method đều `public`, instance, concrete, không tham số, trả đúng `String` và có đường dẫn khác nhau phù hợp regex.

Tạo **`src/demo/App.java`**:

~~~java
package demo;

public class App {
    public static void main(String[] args) {
        ValidRoutes routes = new ValidRoutes();
        System.out.println(routes.health());
        System.out.println(routes.users());
    }
}
~~~

Annotation `@Route` trong ví dụ **không tạo cơ chế định tuyến HTTP**; method vẫn được gọi bằng Java thông thường. Chức năng processor là bảo vệ hợp đồng khi compile, không thay cách JVM gọi method.

### 6.1. Biên dịch processor

Tại thư mục `project/`, trên Bash:

~~~bash
mkdir -p processor valid-classes invalid-classes

javac --release 17 -d processor RouteProcessor.java
~~~

Lệnh này biên dịch processor trước để `javac` ở bước sau có thể load class `RouteProcessor`. Nó không cần load `demo.Route` khi compile processor vì processor **tra cứu annotation type bằng tên tại thời điểm process**, không import annotation type thành một dependency Java compile-time.

### 6.2. Biên dịch ví dụ hợp lệ

~~~bash
javac --release 17 \
  -processorpath processor \
  -processor RouteProcessor \
  -d valid-classes \
  src/demo/Route.java \
  src/demo/ValidRoutes.java \
  src/demo/App.java
~~~

Các tùy chọn:

- `--release 17`: áp dụng Java 17 source/API target.
- `-processorpath processor`: nơi compiler load annotation processor.
- `-processor RouteProcessor`: chọn processor rõ ràng; không phụ thuộc cơ chế service discovery.
- `-d valid-classes`: nơi lưu output `.class`.
- Ba file nguồn gồm annotation type, class hợp lệ và chương trình thử.

Lệnh build hợp lệ **không bắt buộc in bất kỳ thông báo nào**. Việc không có diagnostic không phải vấn đề; hãy kiểm tra exit code bằng công cụ build/shell (thành công là 0).

### 6.3. Chạy kết quả

~~~bash
java -cp valid-classes demo.App
~~~

Stdout chính xác:

~~~text
ok
users
~~~

Hai dòng này đã được chạy và xác minh bằng `javac --release 17` và `java`. Chúng được in bởi `App`, **không phải** bởi annotation processor.

## 7. Ví dụ sai: `InvalidRoutes.java`

Tạo **`src/demo/InvalidRoutes.java`** với các vi phạm độc lập:

~~~java
package demo;

class InvalidRoutes {
    @Route(path = "relative")
    public String relative() { return "bad"; }

    @Route(path = "/hidden")
    private String hidden() { return "bad"; }

    @Route(path = "/static")
    public static String staticMethod() { return "bad"; }

    @Route(path = "/params")
    public String withArg(String x) { return x; }

    @Route(path = "/number")
    public int number() { return 3; }

    @Route(path = "/dupe")
    public String first() { return "a"; }

    @Route(path = "/dupe")
    public String second() { return "b"; }

    @Route
    public String missingPath() { return "bad"; }
}

interface InvalidInterface {
    @Route(path = "/interface")
    String interfaceMethod();
}

abstract class AbstractRoutes {
    @Route(path = "/abstract")
    public abstract String abstractMethod();
}
~~~

Tất cả các annotation ở ví dụ trên **được Java cho phép về mặt `@Target(METHOD)`**: chúng đều nằm trên method declaration. Nhưng chúng vi phạm **hợp đồng do processor của bài đặt ra**, nên một compiler chạy đúng processor sẽ báo lỗi.

Lệnh biên dịch độc lập:

~~~bash
javac --release 17 \
  -processorpath processor \
  -processor RouteProcessor \
  -d invalid-classes \
  src/demo/Route.java \
  src/demo/InvalidRoutes.java
~~~

**Kỳ vọng:** lệnh `javac` thất bại (exit code khác 0). Processor có thể đưa ra nhiều diagnostics trong cùng lần biên dịch; số dòng file/path/caret cụ thể phụ thuộc máy và vị trí nguồn.

### 7.1. Danh sách diagnostic đã được kiểm chứng

Trong lần chạy thực tế với Java 17 target, processor phát ra **10 lỗi**:

| Khai báo | Lỗi do processor báo |
|---|---|
| `relative()` | `@Route path must match /[a-z][a-z0-9/-]*` |
| `hidden()` | `@Route method must be public, instance and concrete` |
| `staticMethod()` | `@Route method must be public, instance and concrete` |
| `withArg(String)` | `@Route method must have no parameters` |
| `number()` | `@Route method must return String` |
| `second()` | `Duplicate @Route path in the same class: /dupe` |
| `missingPath()` | `@Route path must match /[a-z][a-z0-9/-]*` |
| `interfaceMethod()` | `@Route requires a method in a class` |
| `interfaceMethod()` | `@Route method must be public, instance and concrete` |
| `abstractMethod()` | `@Route method must be public, instance and concrete` |

Mỗi lỗi có tiền tố `[ROUTE]` do method `error(...)` thêm vào. Vì processor **không dừng ngay ở lỗi đầu tiên**, `interfaceMethod()` có hai lỗi khác nhau: enclosing element là `INTERFACE` và method là `ABSTRACT`.

Một phần output điển hình (chỉ trích nội dung diagnostic; đường dẫn và số dòng được lược bỏ):

~~~text
error: [ROUTE] @Route path must match /[a-z][a-z0-9/-]*
error: [ROUTE] @Route method must be public, instance and concrete
error: [ROUTE] @Route method must have no parameters
error: [ROUTE] @Route method must return String
error: [ROUTE] Duplicate @Route path in the same class: /dupe
...
10 errors
~~~

Đây **không phải đầu ra stdout của ứng dụng**. Diagnostic thường được `javac` ghi ra **stderr**; build script hoặc IDE cần đánh giá exit code/diagnostics chứ không chỉ đọc stdout.

### 7.2. Vì sao `@Route` thiếu path cũng được processor bắt?

`Route.path()` có `default ""` nên `@Route` không vi phạm quy tắc khai báo element bắt buộc của Java. Nhưng processor dùng `getElementValuesWithDefaults`, lấy `""` và áp dụng regex. Chuỗi rỗng không khớp, do đó `missingPath()` bị báo lỗi.

Nếu bỏ `default` khỏi `Route.path()` thì compiler sẽ yêu cầu annotation user nhập `path` ở mọi nơi. Cách nào tốt hơn phụ thuộc thiết kế API: muốn để **compiler** kiểm tra thiếu giá trị bắt buộc, bỏ default; muốn **processor** kiểm tra path và phát thông báo riêng, có thể dùng sentinel rồi validation.

### 7.3. Compiler có thể phát hiện lỗi sớm hơn processor

Một ví dụ **cố ý sai khác** không cần chạy trong tập bài kiểm thử:

~~~java
class WrongPlace {
    @Route(path = "/x")
    String field; // SAI: @Route chỉ có @Target(METHOD), không áp dụng cho FIELD
}
~~~

Trường hợp này compiler sẽ báo annotation không áp dụng cho field, bởi `@Target` là quy tắc ngôn ngữ. Không nên kỳ vọng processor luôn nhận được `FIELD` trong `round.getElementsAnnotatedWith(Route)` ở source đã vi phạm quy tắc target. Nhánh kiểm tra `ElementKind.METHOD` trong processor là **phòng vệ**, không phải thay thế `@Target`.

## 8. Giải thích cơ chế kiểm tra theo từng nhóm

### 8.1. Loại declaration và enclosing element

~~~java
element.getKind() == ElementKind.METHOD
method.getEnclosingElement().getKind() == ElementKind.CLASS
~~~

- Điều kiện đầu cho biết element là method declaration.
- Điều kiện sau chỉ chấp nhận method **bên trong một class**.
- Method trong interface có enclosing kind `INTERFACE`, bị từ chối.
- Method trong record có enclosing kind `RECORD`, theo hợp đồng demo hiện tại cũng bị từ chối.
- Method trong annotation type có enclosing kind `ANNOTATION_TYPE`, cũng không phải class method theo hợp đồng này.

Nếu muốn cho phép method trong record hay interface, phải **thay đổi hợp đồng rõ ràng** và viết lại validation phù hợp; không tự biến `ElementKind.RECORD` thành `CLASS` trong phép so sánh equality.

### 8.2. Modifier: phân biệt public, static, abstract

~~~java
Set<Modifier> modifiers = method.getModifiers();

if (!modifiers.contains(Modifier.PUBLIC)
        || modifiers.contains(Modifier.STATIC)
        || modifiers.contains(Modifier.ABSTRACT)) {
    error(method, "...");
}
~~~

Vì yêu cầu method instance concrete public, cả ba vế cần được kiểm tra. Không thể chỉ dựa vào `@Target(METHOD)` vì Java cho phép gắn annotation vào private/static/abstract method khi target là METHOD.

Một method trong interface được compiler xem có các modifier tương ứng theo quy tắc interface method, nhưng trong bài còn bị loại bởi enclosing kind không phải CLASS. Việc xuất hiện hai lỗi trên cùng khai báo là nhất quán với thuật toán ví dụ.

### 8.3. Tham số

~~~java
method.getParameters().isEmpty()
~~~

Đây là kiểm tra **danh sách tham số khai báo của method**, không phải kiểm tra class có field hoặc generic type parameters hay không. Method `String withArg(String x)` không đạt dù trả đúng String và path hợp lệ.

### 8.4. Return type

~~~java
processingEnv.getTypeUtils().isSameType(
        method.getReturnType(),
        string.asType())
~~~

Đây là kiểm tra kiểu thực tế bằng compiler model. `int` không tương đương `java.lang.String`. `Object` hoặc `CharSequence` cũng không phải đúng String. Nếu hợp đồng muốn chấp nhận một tập các kiểu trả về, hãy đổi rule dùng `Types.isAssignable` hoặc kiểm tra cụ thể, rồi bổ sung test.

### 8.5. Regex

~~~java
path.matches("/[a-z][a-z0-9/-]*")
~~~

`String.matches` so khớp toàn bộ chuỗi. `/health` và `/v1/users` hợp lệ; `relative`, `/`, `/WhiteSpace` và `""` không hợp lệ. Hợp đồng cố tình đơn giản để học processor.

### 8.6. Trùng đường dẫn trong class

~~~java
String key = method.getEnclosingElement().toString() + "#" + path;
if (!registered.add(key)) {
    error(method, "Duplicate @Route path in the same class: " + path);
}
~~~

Nhờ đưa enclosing class vào key, `/health` ở hai class khác nhau **không bị xem là trùng**. Trong hệ thống route thật, có thể cần phạm vi toàn application thay vì mỗi class, có tiền tố route cấp class, có HTTP method hoặc normalize đường dẫn. Khi đó mô hình key phải được thiết kế lại.

Ví dụ chỉ thêm key nếu những rule **khác đã hợp lệ**, để method sai path/return type không chiếm chỗ của một route hợp lệ.

## 9. Cách kiểm thử processor chuyên nghiệp

Một processor chất lượng cần cả **positive tests** và **negative tests**:

- **Positive:** source hợp lệ biên dịch thành công, processor không phát ERROR, ứng dụng chạy đúng khi có runtime code.
- **Negative:** source sai không biên dịch được; compiler có ít nhất diagnostic đúng nội dung và trỏ đúng khai báo.
- **Boundary:** path rỗng, path có dấu cách, modifier combinations, method trong interface/record, method generic, overload/trùng tên.
- **Multiple rounds:** nếu có generated sources, kiểm tra không báo trùng giả hoặc lặp lỗi không cần thiết.
- **Isolation:** chạy processor bằng `-processorpath` rõ ràng, không dựa trên processor được load ngẫu nhiên từ classpath.
- **Version:** chạy với `--release 17` hoặc source version thực tế mà dự án cam kết.
- **Result code:** negative test cần khẳng định compilation **thất bại**, không chỉ tìm chuỗi error trong console.

Với terminal Bash, có thể kiểm tra exit code sau `javac`:

~~~bash
javac --release 17 \
  -processorpath processor \
  -processor RouteProcessor \
  -d invalid-classes \
  src/demo/Route.java \
  src/demo/InvalidRoutes.java

echo "$?"
~~~

Khi `javac` phát `Diagnostic.Kind.ERROR`, giá trị exit code **khác 0**. Một số shell/build tools in diagnostic khác nhau; đừng viết test cứng phụ thuộc tuyệt đối vào đường dẫn, số dòng hoặc thứ tự thông báo.

### 9.1. Không đòi con số lỗi cố định trong mọi refactor

Với **chính bộ ví dụ và processor của bài**, đã kiểm tra thấy 10 diagnostics. Tuy vậy, khi thêm rule hoặc thay code, số lượng có thể thay đổi: một declaration có thể vi phạm nhiều rule, và các compiler khác nhau có thể gắn thêm diagnostic của ngôn ngữ.

Trong unit tests của processor thật, nên kiểm tra **lỗi nào đã được phát cho declaration nào**, thay vì chỉ so nguyên văn cả stderr. Các framework thử nghiệm compilation có thể hỗ trợ assert diagnostics một cách cấu trúc; không cần phụ thuộc tool ngoài JDK để hiểu bài này.

## 10. `process`, các processing rounds và ý nghĩa `return true`

Method `process(...)` có thể được compiler gọi qua nhiều vòng. Trong ví dụ:

~~~java
if (round.processingOver()) {
    return true;
}
~~~

giúp processor không xử lý annotated elements lần nữa ở **vòng cuối**. Không có source được sinh trong bài này, nhưng trong processor khác, source/class được sinh có thể tạo ra round mới.

Các vòng thường được hình dung:

~~~text
Initial round:
  compiler biết các source declarations
  RouteProcessor nhận các method có @Route
  validates -> Messager ERROR nếu sai

Potential subsequent rounds:
  chỉ khi tool/compiler có thêm source/class generated phù hợp

Final round:
  round.processingOver() == true
  processor kết thúc xử lý
~~~

`@SupportedAnnotationTypes("demo.Route")` chỉ rõ annotation type supported. `return true` nghĩa là processor **claim các annotation thuộc tập nó xử lý trong round**; không có nghĩa compiler tự sinh code hoặc tự sửa source. Với nhiều processor, việc claim có thể ảnh hưởng processor nào còn nhận annotation để xử lý, nên phải lựa chọn có chủ đích.

### 10.1. `-processor` và phát hiện processor qua service metadata

Lệnh thực hành dùng:

~~~bash
-processor RouteProcessor
~~~

nên compiler biết chính xác processor class nào phải load. Trong JAR processor thật, có thể công bố tên processor qua file `META-INF/services/javax.annotation.processing.Processor` hoặc thiết lập tương đương trong build. Khi đó việc chọn processor phụ thuộc cấu hình build/toolchain. Việc khai báo `@SupportedAnnotationTypes` **không tự đăng ký processor vào classpath** theo mọi hình thức chạy.

Nếu thiếu cấu hình processor, `javac` có thể biên dịch source hợp lệ về cú pháp Java mà **không chạy validation riêng của chúng ta**. Đây là lỗi tích hợp rất đáng chú ý khi một dự án chuyển từ CLI sang IDE hoặc CI.

## 11. Những giới hạn của phiên bản demo

### 11.1. Chỉ kiểm tra declaration được annotate

Processor không tìm tất cả method trong class rồi suy ra method nào “nên” có `@Route`. Nó chỉ duyệt những `Element` được `RoundEnvironment` trả về vì đã gắn annotation. Nếu muốn bắt buộc class nào đó phải có route, cần kiểm tra ở cấp class hoặc quét type/member theo hợp đồng riêng.

### 11.2. Không sửa code người dùng

JSR 269 chuẩn không cung cấp cơ chế thêm method, sửa modifiers hoặc xóa annotation trực tiếp khỏi class đang biên dịch. Processor báo lỗi để developer **sửa nguồn**, hoặc có thể dùng `Filer` để **sinh file mới** trong bài toán khác.

### 11.3. Kiểm tra đa module / đa compilation chưa đầy đủ

`registered` chỉ thấy những method được processor xử lý trong **compilation task hiện tại**. Nếu nhiều module được biên dịch riêng, processor không tự có một danh sách route toàn hệ thống. Muốn kiểm tra trùng toàn application, cần thiết kế registry/build aggregation hoặc xử lý bằng một công cụ kiểm tra phạm vi rộng hơn.

### 11.4. Không phân tích inheritance

`getElementsAnnotatedWith(route)` xử lý các elements mang annotation trong round. Nó không tự duyệt đầy đủ method được thừa kế, method override hay interface default methods theo một “route policy” tùy ý. Cần phân tích `Elements.getAllMembers(...)`, `Elements.overrides(...)` hoặc type hierarchy khi quy tắc ứng dụng đòi hỏi.

### 11.5. Không kiểm tra logic bên trong method

Processor chỉ kiểm tra declaration/signature và giá trị annotation. Nó không chứng minh method `health()` thực sự xử lý request, không ném lỗi, không rò dữ liệu hoặc luôn trả response hợp lệ. Muốn phân tích cây cú pháp của method body cần công cụ hỗ trợ AST; muốn kiểm tra hành vi cần thêm runtime/integration tests.

### 11.6. Bộ regex chưa phải bộ phân tích HTTP routing

Regex mẫu có thể cho phép `//` ở phần sau và không hỗ trợ `{id}`. Các framework HTTP thường có quy tắc URI template, URL encoding, HTTP method, route precedence và conflict detection riêng. Mở rộng hợp đồng cần thêm parser và test, không chỉ sửa một chuỗi regex.

### 11.7. Diagnostic chỉ gắn vào method, chưa vào argument `path`

Hiện tại dùng `printMessage(kind, message, element)`, caret thường nằm ở method declaration. Nếu muốn lỗi trỏ trực tiếp tới giá trị `path` trong `@Route(path = "...")`, `Messager` có overload nhận thêm `AnnotationMirror`, `AnnotationValue`. Vì thế có thể nâng cấp `readPath(...)` để trả cả mirror/value và dùng overload chuyên biệt.

### 11.8. State của processor và code generation

Một processor có thể sinh thêm source trong các round, nên cần phân biệt phương thức đọc elements theo round và state đã xử lý. Bộ `registered` trong bài được khởi tạo cho processor instance, không đảm bảo tự động hoạt động như persistence layer qua các lần build.

## 12. Mở rộng bài thực hành

Sau khi ví dụ chạy đúng, có thể tự nâng cấp từng bước:

### 12.1. Kiểm tra một path hợp lệ nhưng không hỗ trợ route lồng

Thay regex bằng parser hoặc quy tắc chặt hơn; viết thêm negative test cho `//`, dấu gạch chéo cuối, ký tự Unicode, query string hoặc path variable. Đây là cơ hội luyện tập **kiểm tra input tại compile-time** mà không cần tạo web server.

### 12.2. Yêu cầu method không khai báo checked exception

Dùng `ExecutableElement.getThrownTypes()` và API `Types`/`Elements` để phân tích danh sách exception. Không nên kết luận “không có checked exception” chỉ bằng việc `getThrownTypes().isEmpty()`: method có thể khai báo unchecked exceptions; cần xác định đúng phân loại.

### 12.3. Cho phép record hoặc interface default method

Thay rule enclosing kind và modifier để cho phép `ElementKind.RECORD` hoặc `INTERFACE` theo chính sách mới. Sau đó test record accessor, interface default method, abstract method và việc generated code tiêu thụ chúng.

### 12.4. Kiểm tra route trả `CompletionStage<String>`

Nếu muốn method trả generic type, cần làm việc với `DeclaredType`, `TypeElement` và `Types` để so sánh đúng generic arguments; không chỉ so `TypeMirror.toString()`. Cần test raw types, wildcards và erasure khi thiết kế.

### 12.5. Chuyển kết quả lỗi thành regression test

Tạo test compile nhiều source snippets và xác nhận:

- `javac` exit code 0 cho code hợp lệ.
- `javac` exit code khác 0 cho code không hợp lệ.
- Có diagnostic chứa `[ROUTE]` và đúng rule.
- Processor không tạo duplicate false positive khi compile nhiều class.
- Các thông điệp có vị trí declaration phù hợp.

Những test dạng này rất hữu ích để duy trì annotation API khi đội ngũ thêm rule mới hoặc nâng cấp JDK.

## 13. Những lỗi thường gặp khi tự viết processor

**Processor không chạy:** chỉ khai báo `@SupportedAnnotationTypes` trên class không đủ để compiler tự tìm thấy processor. Hãy chỉ rõ `-processor` và `-processorpath` hoặc đóng gói service registration phù hợp, rồi kiểm chứng bằng negative test.

**Không thấy annotation `SOURCE` bằng reflection:** đúng theo retention. Processor nên dùng model compiler; đừng bắt annotation đổi thành `RUNTIME` chỉ để chạy validation compile-time.

**`ClassCastException` khi cast element:** hãy kiểm tra `getKind()` hoặc dùng type-safe `ElementFilter` trước khi cast thành `ExecutableElement`/`TypeElement`.

**Chỉ in lỗi ra stdout:** `System.out.println(...)` không thay thế `Messager`. Dùng `Diagnostic.Kind.ERROR` để compilation thất bại.

**Sai khi đọc phần tử mặc định:** `AnnotationMirror.getElementValues()` không tự thêm `default`; dùng `Elements.getElementValuesWithDefaults(...)` nếu muốn rule áp dụng cho mọi usage.

**So sánh kiểu qua tên hiển thị:** chuỗi từ `asType().toString()` không phải phép so sánh type chính thức. Dùng `Types`, tránh bỏ sót generics hoặc qualified names.

**Dùng `return false` mà không hiểu tác dụng:** false cho phép processors khác tiếp tục xét annotation types; true claim chúng trong round theo contract. Đây không phải cờ “build đã pass/failed”; errors được báo bằng `Messager`.

**Dựa vào thứ tự diagnostics:** thứ tự duyệt elements/processing rounds không nên được xem như contract ổn định để thiết kế logic nghiệp vụ. Với negative tests, kiểm tra tập thông điệp và vị trí, không cần giả định lỗi thứ nhất luôn là cùng method.

**Nhầm compiler error và processor error:** khi một `@Route` xuất hiện trên field, lỗi từ quy tắc `@Target` có thể do compiler trực tiếp phát ra, không có tiền tố `[ROUTE]`. Đừng xem điều đó là bằng chứng processor chưa chạy.

**Coi processor như công cụ sửa mã nguồn:** JSR 269 không có API chuẩn thêm getter vào declaration có sẵn. Processor có thể phát diagnostic hoặc sinh các tệp mới với `Filer` nhưng không “vá” AST gốc thông qua `Element`.

## 14. Checklist nghiệm thu

- [ ] Annotation type khai báo `@Target` và `@Retention` phù hợp.
- [ ] Processor hỗ trợ đúng tên annotation type và source version.
- [ ] Processor được load bằng cấu hình compiler/build rõ ràng.
- [ ] Code dùng `RoundEnvironment` lấy đúng annotated elements.
- [ ] Mọi cast `Element` sang interface con đều có kiểm tra kind.
- [ ] Rules về modifier, parameter, return type và value được kiểm tra độc lập.
- [ ] Type checking sử dụng `Types` thay vì so text.
- [ ] Metadata có `default` được đọc bằng `getElementValuesWithDefaults`.
- [ ] Lỗi được báo bằng `Messager` với `Diagnostic.Kind.ERROR`.
- [ ] Positive test biên dịch thành công, ứng dụng in đúng `ok`, `users`.
- [ ] Negative test biên dịch thất bại và hiển thị diagnostics đúng.
- [ ] State/trùng lặp hoạt động đúng cho phạm vi class và compilation task đã chọn.
- [ ] Thử chạy lại clean build với JDK mục tiêu, không phụ thuộc vào metadata biên dịch cũ.
- [ ] Không vô tình sửa source, tạo file ngoài phạm vi hoặc che giấu diagnostic.

## 15. Tài liệu chuẩn

- [Java SE 17 — `AbstractProcessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): cơ sở để triển khai processor.
- [Java SE 17 — `Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): hợp đồng xử lý annotation, claim và processing rounds.
- [Java SE 17 — `RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): tìm annotated elements và vòng xử lý.
- [Java SE 17 — `Messager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Messager.html): diagnostic gắn với element, annotation mirror hoặc annotation value.
- [Java SE 17 — `ExecutableElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ExecutableElement.html): chữ ký method, parameters, return type.
- [Java SE 17 — `ElementKind`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/element/ElementKind.html): phân loại declarations.
- [Java SE 17 — `Types`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Types.html): so sánh kiểu trong compiler model.
- [Java SE 17 — `Elements`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/util/Elements.html): tra cứu types, lấy annotation values kèm defaults.
- [Java SE 17 — `AnnotatedConstruct`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/AnnotatedConstruct.html): truy cập annotation mirrors trong ngữ cảnh compile-time.
- [JDK 17 `javac` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): các cờ `-processor`, `-processorpath`, `--release` và `-d`.

**Tổng kết:** Một processor phát hiện khai báo không hợp lệ có ba bước cốt lõi: **tìm đúng `Element`, kiểm tra hợp đồng bằng compiler model, báo `Diagnostic.Kind.ERROR` tại declaration vi phạm**. Qua ví dụ `@Route`, bạn có thể kiểm soát quy tắc về modifier, tham số, return type, annotation value và trùng lặp ngay trong `javac`, đồng thời dùng positive/negative compilation tests để chứng minh rằng code đúng đi qua và code sai bị chặn trước runtime.