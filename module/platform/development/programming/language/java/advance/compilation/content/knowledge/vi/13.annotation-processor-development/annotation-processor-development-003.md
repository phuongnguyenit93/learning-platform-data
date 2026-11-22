# Dùng RoundEnvironment để duyệt phần tử cần xử lý

## Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vai trò của `javax.annotation.processing.RoundEnvironment` trong từng vòng (*round*) của Java annotation processing.
2. Phân biệt `RoundEnvironment.getRootElements()`, `getElementsAnnotatedWith(...)`, tham số `annotations` của `Processor.process(...)`, và việc duyệt trực tiếp các phần tử con qua `Element.getEnclosedElements()`.
3. Kiểm tra đúng loại phần tử với `ElementKind`, ép kiểu an toàn sang `TypeElement` hoặc `ExecutableElement` và dùng `Elements`, `Types` khi cần phân tích mô hình ngôn ngữ.
4. Xây dựng và chạy được processor Java 17+ sinh một class từ annotation nguồn; quan sát round kế tiếp và round cuối bằng `javac`.
5. Xử lý đúng `processingOver()`, `errorRaised()`, việc claim annotation, lỗi do `Filer` và trường hợp không có phần tử khớp.
6. Tránh các lỗi phổ biến như tưởng mỗi round chứa toàn bộ project, chỉ dựa vào tên annotation, tạo trùng file, kiểm tra runtime Reflection thay vì compile-time model hoặc quên compiler/processor path.

Bài tập trung vào cách **duyệt và xử lý phần tử bằng `RoundEnvironment`** bên trong annotation processor. Việc sinh file được đưa vào như một trường hợp thực tế cho thấy tại sao compiler phải tổ chức nhiều round.

## 1. Annotation processing hoạt động ở compile-time

Annotation processor là thành phần tham gia quá trình biên dịch Java. Nó có thể kiểm tra các declaration được gắn annotation, phát diagnostic, sinh source hoặc resource thông qua những API được hỗ trợ. Nó không cần khởi động ứng dụng, không gọi `main` của class đang biên dịch và không nhất thiết dùng Java Reflection của runtime.

Ví dụ một class được đánh dấu:

~~~java
@AutoGreeting
public class HelloService {
}
~~~

Một processor hỗ trợ `@AutoGreeting` có thể tìm phần tử khai báo `HelloService` thông qua `RoundEnvironment`, rồi sinh ra `HelloServiceGreeting.java`. Ở vòng xử lý tiếp theo, compiler xét source mới sinh và có thể gọi lại processor. Sau khi không còn source mới cần xử lý, compiler thường thực hiện vòng cuối để processor hoàn tất.

Sơ đồ khái quát:

~~~text
Source ban đầu
  HelloService.java (có @AutoGreeting)
  Main.java
        |
        v
javac khởi tạo processor
        |
        v
Round 1: roundEnv tìm @AutoGreeting
        |
        +--> Processor phát hiện HelloService
        +--> Filer tạo HelloServiceGreeting.java
        |
        v
Round 2: compiler đưa source mới vào tập root của round mới
        |
        +--> Processor vẫn có thể được gọi
        +--> Không có @AutoGreeting mới thì tập khớp rỗng
        |
        v
Final round: processingOver() == true
        |
        v
javac hoàn tất compile (nếu không có lỗi)
        |
        v
.class của source gốc và source sinh ra
~~~

Sơ đồ trên mô tả trường hợp ví dụ của bài; nếu source sinh ra lại có annotation cần xử lý, có thể có thêm round. Nếu processor không sinh source/class mới, chuỗi round ngắn hơn. Chi tiết log phụ thuộc compiler và cấu hình.

### Những đối tượng bạn sẽ gặp

| API/kiểu | Ý nghĩa |
| --- | --- |
| `Processor` | Giao diện của annotation processor; phương thức quan trọng là `process(...)` |
| `AbstractProcessor` | Lớp cơ sở tiện lợi, cung cấp `processingEnv` và một số phương thức mặc định |
| `ProcessingEnvironment` | Cung cấp `Messager`, `Filer`, `Elements`, `Types`, tùy chọn processor |
| `RoundEnvironment` | Cung cấp những phần tử liên quan **round hiện tại** và trạng thái kết thúc/lỗi |
| `Element` | Mô hình một declaration của Java (type, field, method, parameter, package...) |
| `TypeElement` | Mô hình một khai báo class/interface/enum/record/annotation type |
| `ExecutableElement` | Mô hình method hoặc constructor |
| `TypeMirror` | Mô hình kiểu trong hệ thống kiểu của compiler, không phải đối tượng `Class<?>` |
| `AnnotationMirror` | Mô hình annotation được compiler nhìn thấy, hữu ích khi không nên load annotation class bằng Reflection |

Các API chuẩn của annotation processing nằm trong module `java.compiler`; những package hay dùng là `javax.annotation.processing`, `javax.lang.model.element`, `javax.lang.model.type` và `javax.lang.model.util`.

## 2. Vai trò cụ thể của RoundEnvironment

Chữ ký quan trọng trong processor:

~~~java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    // Đọc các declaration và xử lý vòng hiện tại.
    return true;
}
~~~

Đây là **đoạn minh họa chữ ký method**, không phải một Java class hoàn chỉnh. Processor đầy đủ xuất hiện ở mục 5.

Đối số `annotations` và `roundEnv` **khác vai trò**:

- `annotations`: tập các **loại annotation** mà compiler yêu cầu processor xử lý ở lần gọi hiện tại. Nó có thể là tập con của các annotation được processor khai báo hỗ trợ, thậm chí có thể rỗng.
- `roundEnv`: cửa sổ truy vấn **các declaration xuất hiện trong round**, trạng thái round và các phần tử được đánh dấu bằng annotation.

Đừng viết code giả định `annotations.size()` là số lượng các class được gắn annotation. Một loại annotation có thể xuất hiện trên nhiều declaration. Nếu muốn biết số phần tử cần làm việc, phải truy vấn `roundEnv`.

### 2.1 `getRootElements()`

~~~java
Set<? extends Element> roots = roundEnv.getRootElements();
~~~

Trả tập **root elements của round hiện tại**. Ở round đầu, root thường liên quan đến các source/class mà tool được yêu cầu xử lý. Ở round tiếp theo, root có thể đến từ source/class được sinh bởi round trước. Root không nhất thiết có annotation mà processor của bạn quan tâm.

Điều không được suy ra:

- Root không đồng nghĩa với toàn bộ source của project.
- Root không nhất thiết bao gồm mọi field và method như những phần tử độc lập.
- `getRootElements()` ở round kế tiếp không phải bản sao toàn bộ root của round đầu.
- Thứ tự duyệt `Set` không phải thứ tự ổn định có thể dùng làm hợp đồng đầu ra.

Muốn phân tích thành viên của một root type, có thể duyệt `root.getEnclosedElements()` hoặc dùng `ElementFilter` phù hợp. Nhưng khi mục đích là tìm mọi declaration được gắn annotation cụ thể **trong phạm vi round**, `getElementsAnnotatedWith` thường ngắn và chính xác hơn tự duyệt cây.

### 2.2 `getElementsAnnotatedWith(...)`

Các overload phổ biến trong Java 17:

~~~java
roundEnv.getElementsAnnotatedWith(MyAnnotation.class);
roundEnv.getElementsAnnotatedWith(myAnnotationTypeElement);
~~~

Đây là **hai lời gọi minh họa**, giả định `MyAnnotation` và biến `myAnnotationTypeElement` đã tồn tại ở processor.

- Overload nhận `Class<? extends Annotation>`: thuận tiện khi processor có thể nạp annotation type từ classpath dành cho processor.
- Overload nhận `TypeElement`: dùng mô hình compiler; hữu ích khi annotation type không nên được load trực tiếp hoặc bạn lấy type bằng `Elements.getTypeElement(...)`.

Kết quả là tập `Set<? extends Element>` gồm các phần tử có annotation tương ứng theo quy tắc hiện diện của API, trong phạm vi những element mà round đưa vào. Annotation có thể được coi là hiện diện trực tiếp hoặc qua kế thừa trong các trường hợp hợp lệ. Phạm vi không chỉ gồm root type mà còn có thể gồm member, constructor, parameter, type parameter và record component khai báo trong các type được bao gồm.

**Cần phân biệt annotation trên declaration với annotation trên type-use.** `getElementsAnnotatedWith(...)` không phải một công cụ tìm toàn bộ nơi annotation xuất hiện trên mọi vị trí kiểu bất kỳ trong source.

### 2.3 `getElementsAnnotatedWithAny(...)`

Java 17 có các overload giúp lấy **hợp** những phần tử mang ít nhất một trong nhiều annotation types:

~~~java
Set<? extends Element> hits =
        roundEnv.getElementsAnnotatedWithAny(firstType, secondType);
~~~

Đoạn trên giả định `firstType` và `secondType` là `TypeElement` đại diện annotation types. Kết quả là tập phần tử, không phải danh sách được sắp thứ tự hay bản ghi tách theo annotation. Với annotation lặp lại (`@Repeatable`), có thể cần quan tâm cả annotation type gốc **và container annotation type** trong khai báo supported types và truy vấn, tùy cách biểu diễn annotation.

Nếu muốn phân tích riêng từng annotation, gọi `getElementsAnnotatedWith` cho từng loại rồi áp dụng logic phù hợp. Đừng ngầm xem mọi lần lặp annotation là một phần tử mới trong tập `Set`.

### 2.4 `processingOver()`

~~~java
if (roundEnv.processingOver()) {
    return true;
}
~~~

Giá trị `true` thể hiện round mà các kiểu được sinh ở round này **sẽ không được đưa vào một vòng annotation processing tiếp theo**. Thông thường đây là round cuối. Đây là điểm phù hợp để hoàn tất một số việc báo cáo/tổng hợp nếu đã lưu trạng thái giữa các round.

**Không nên cố sinh source Java mới ở final round rồi mong compiler xử lý nó như một round kế tiếp.** Nếu processor cần tạo source để compiler compile, hãy tạo nó ở những round chưa kết thúc.

Vẫn có thể có nhu cầu ghi một số tài nguyên tổng hợp ở final round theo hợp đồng của `Filer`, nhưng phải hiểu rõ ràng buộc thời điểm và không mặc định file mới được đưa vào pipeline compile.

### 2.5 `errorRaised()`

~~~java
boolean previousRoundHadError = roundEnv.errorRaised();
~~~

Nó cho biết đã có error được phát ra ở **round trước**; không nên hiểu là cờ phản ánh tức thì mọi lỗi bạn vừa emit trong chính lần gọi `process(...)` này. Vì vậy không viết logic như sau:

~~~java
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.ERROR,
        "Invalid declaration"
);
// Không nên kỳ vọng roundEnv.errorRaised() chuyển thành true ngay tại đây.
~~~

Đây là đoạn minh họa trong `process`, không phải chương trình độc lập. Nếu cần biết processor của mình đã phát lỗi trong round hiện tại, theo dõi bằng biến riêng, ví dụ `boolean hadLocalError` hoặc trạng thái thích hợp.

### 2.6 Bảng tóm tắt các API

| Phương thức | Câu hỏi nó trả lời | Lỗi hiểu sai thường gặp |
| --- | --- | --- |
| `getRootElements()` | Root declarations của round này là gì? | Coi đó là mọi class của project trong mọi round |
| `getElementsAnnotatedWith(A.class)` | Những declaration nào trong phạm vi round có `@A`? | Cho rằng nó chỉ tìm top-level classes |
| `getElementsAnnotatedWith(TypeElement)` | Tìm declaration theo annotation type biểu diễn bởi compiler? | Đưa vào một type không phải annotation |
| `getElementsAnnotatedWithAny(...)` | Hợp các declaration mang ít nhất một annotation cần tìm? | Đòi hỏi thứ tự cố định hoặc số bản ghi tương ứng số lần gắn annotation |
| `processingOver()` | Có đang ở giai đoạn không còn round tiếp để xử lý kiểu sinh mới? | Nghĩ cứ final round thì phải sinh thêm source |
| `errorRaised()` | Round **trước** có báo error không? | Dùng làm biến tức thời để biết vừa báo lỗi trong cùng round |

## 3. Duyệt phần tử sao cho an toàn

### 3.1 Kiểm tra `ElementKind` trước khi ép kiểu

`getElementsAnnotatedWith(...)` trả `Element` chung. Annotation có thể cho phép gắn vào type, field, method, parameter hoặc nhiều target khác nhau. Trước khi ép thành `TypeElement`, kiểm tra `getKind()`:

~~~java
for (Element element : roundEnv.getElementsAnnotatedWith(MyAnnotation.class)) {
    if (!element.getKind().isClass()) {
        processingEnv.getMessager().printMessage(
                javax.tools.Diagnostic.Kind.ERROR,
                "@MyAnnotation chỉ hợp lệ trên class",
                element
        );
        continue;
    }
    TypeElement type = (TypeElement) element;
    // Dùng type.getSimpleName(), type.getQualifiedName(), ...
}
~~~

Đoạn trên là snippet của processor, giả định `MyAnnotation` được khai báo. `ElementKind.isClass()` trả true cho các kind mô tả class, gồm một số dạng class cụ thể. Nếu contract chỉ cho class thường, kiểm tra `element.getKind() == ElementKind.CLASS`. Annotation `@Target(ElementType.TYPE)` cho phép nhiều kiểu khai báo, trong khi processor có thể cần giới hạn thêm.

Nếu muốn xử lý method:

~~~java
if (element.getKind() == ElementKind.METHOD) {
    ExecutableElement method = (ExecutableElement) element;
    // method.getParameters() trả List<? extends VariableElement>.
}
~~~

Đây cũng là snippet, không phải lớp có thể compile độc lập. Duyệt dựa trên kind giúp tránh `ClassCastException` và giúp compiler diagnostic trỏ trực tiếp vào source location.

### 3.2 `Element` khác Reflection `Class<?>`

Trong annotation processor, type đang được compile có thể **chưa có class file**. Truy vấn bằng `TypeElement` và `TypeMirror`, thay vì cố dùng `Class.forName("app.SomeType")` để nạp type mục tiêu.

- `TypeElement.getQualifiedName()`: tên đủ package của declaration.
- `Element.getSimpleName()`: tên ngắn.
- `Element.getEnclosedElements()`: các thành viên được khai báo bên trong element.
- `ExecutableElement.getParameters()`: những parameter declarations của method/constructor trong compile-time model.
- `Element.asType()`: kiểu tương ứng theo `TypeMirror`.
- `Elements` và `Types`: tiện ích cho mô hình compiler, ví dụ kiểm tra type assignment hoặc tìm enclosing package.

Một lỗi thiết kế là dùng `Class<?>` và `getDeclaredMethods()` cho source chưa được compile; nó có thể nạp nhầm phiên bản class cũ ở processor classpath, hoặc đơn giản không tìm thấy class.

### 3.3 Root, member và annotation targets

Giả sử `@Audit` được phép gắn vào method trong `OrderService`. `OrderService` có thể xuất hiện như root, còn method `submit` là **enclosed member**. `roundEnv.getElementsAnnotatedWith(Audit.class)` có thể trả `ExecutableElement` cho `submit` dù nó không phải root top-level.

Nếu bạn chỉ duyệt `roundEnv.getRootElements()` và kiểm tra annotation trực tiếp trên root, bạn có thể bỏ sót annotation nằm trên method/field. Đây là lý do nên chọn cách truy vấn dựa trên mục tiêu: tìm **annotated elements** thì dùng `getElementsAnnotatedWith`; kiểm tra **cấu trúc tất cả member** thì dùng `getEnclosedElements`/`ElementFilter`.

### 3.4 Không dựa vào thứ tự của tập

`getRootElements()` và `getElementsAnnotatedWith(...)` trả `Set`. Không giả định iteration order bằng thứ tự file/source. Nếu bạn sinh báo cáo deterministic, hãy lấy danh sách, chuyển tên có thể so sánh rồi sort:

~~~java
List<Element> elements = new ArrayList<>(
        roundEnv.getElementsAnnotatedWith(MyAnnotation.class)
);
elements.sort(Comparator.comparing(
        e -> e.toString()
));
~~~

Đây là snippet, cần import `java.util.List`, `java.util.ArrayList`, `java.util.Comparator` và có annotation `MyAnnotation`. Khi sắp xếp trong chương trình thật, nên dùng khóa ổn định đúng ngữ nghĩa (qualified name, signature, vị trí theo model) chứ không coi `toString()` luôn là định danh duy nhất của mọi declaration.

## 4. Chuẩn bị project chạy được không cần IDE

Mục tiêu tạo ba phần:

1. Annotation `demo.AutoGreeting` để đánh dấu class.
2. Processor `demo.processor.GreetingProcessor` tìm các class có annotation bằng `RoundEnvironment` và sinh code.
3. Source ứng dụng `sample.HelloService` và `sample.Main` để xác minh code được sinh ra và sử dụng trong cùng invocation `javac`.

Sử dụng **JDK 17 trở lên**. Kiểm tra:

~~~bash
java -version
javac -version
~~~

Ví dụ được viết cho Java 17 và sử dụng `--release 17` khi compiler hỗ trợ target đó. Nếu dùng JDK mới hơn, vẫn có thể chọn `--release 17`. Để thí nghiệm tái lập, hãy tạo thư mục riêng và mở terminal tại thư mục gốc:

~~~text
round-demo/
├── src/
│   ├── demo/
│   │   ├── AutoGreeting.java
│   │   └── processor/
│   │       └── GreetingProcessor.java
│   └── sample/
│       ├── HelloService.java
│       └── Main.java
└── build/
    ├── tools/
    ├── classes/
    └── generated/
~~~

`build/tools` chứa annotation và processor đã biên dịch. `build/classes` chứa class ứng dụng và class sinh ra. `build/generated` là output source do `Filer` tạo.

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force src/demo/processor, src/sample, build/tools, build/classes, build/generated | Out-Null
~~~

**Bash/Zsh (macOS/Linux):**

~~~bash
mkdir -p src/demo/processor src/sample build/tools build/classes build/generated
~~~

Lưu từng file Java bằng UTF-8 với **đúng package và đường dẫn**. Các lệnh biên dịch sau đây chạy từ `round-demo`.

## 5. Ví dụ hoàn chỉnh: annotation và processor

### 5.1 Khai báo annotation — `src/demo/AutoGreeting.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface AutoGreeting {
}
~~~

`@Target(ElementType.TYPE)` cho phép gắn trên khai báo type. Trong processor, chúng ta giới hạn tiếp về **class**. `@Retention(SOURCE)` đủ cho compile-time processor: annotation không cần tồn tại ở runtime để processor tìm thấy.

Đừng nhầm annotation processor với runtime reflection. Retention policy `SOURCE` không ngăn javac nhìn thấy annotation trên source ở pha xử lý annotation.

### 5.2 Viết processor — `src/demo/processor/GreetingProcessor.java`

~~~java
package demo.processor;

import demo.AutoGreeting;
import java.io.IOException;
import java.io.Writer;
import java.util.HashSet;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.AutoGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {

    private final Set<String> generatedNames = new HashSet<>();

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(AutoGreeting.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@AutoGreeting chi dung cho class",
                        element
                );
                continue;
            }

            TypeElement owner = (TypeElement) element;

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(owner)
                    .getQualifiedName()
                    .toString();
            String simpleName = owner.getSimpleName() + "Greeting";
            String qualifiedName = pkg.isEmpty()
                    ? simpleName : pkg + "." + simpleName;

            if (!generatedNames.add(qualifiedName)) {
                continue;
            }

            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, owner);

                try (Writer writer = file.openWriter()) {
                    if (!pkg.isEmpty()) {
                        writer.write("package " + pkg + ";\n\n");
                    }

                    writer.write("public final class " + simpleName + " {\n");
                    writer.write("    private " + simpleName + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"Hello from "
                            + owner.getSimpleName() + "\";\n");
                    writer.write("    }\n");
                    writer.write("}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualifiedName
                                + ": " + ex.getMessage(),
                        owner
                );
            }
        }

        return true;
    }
}
~~~

Đây là class processor độc lập, biên dịch được bằng JDK 17+. Lớp kế thừa `AbstractProcessor`, có public no-arg constructor ngầm định vì không định nghĩa constructor riêng; compiler có thể khởi tạo nó khi được chỉ định.

Những dòng quan trọng:

1. `@SupportedAnnotationTypes("demo.AutoGreeting")` công bố annotation processor hỗ trợ. Đây là **tên đầy đủ của annotation**, không phải tên lớp được gắn annotation.
2. `@SupportedSourceVersion(SourceVersion.RELEASE_17)` khai báo cấp nguồn mà processor hỗ trợ. Nếu dùng compiler với source level cao hơn, có thể có warning về version; trong ví dụ chúng ta compile với `--release 17`.
3. `roundEnv.processingOver()` tránh tạo source khi đã ở final round.
4. `roundEnv.getElementsAnnotatedWith(AutoGreeting.class)` duyệt **đúng phần tử được gắn annotation trong round**, không quét thủ công toàn bộ package.
5. `ElementKind.CLASS` ngăn ép kiểu từ những loại phần tử không mong muốn.
6. `TypeElement owner` dùng mô hình compiler để lấy tên class và package.
7. `Filer.createSourceFile(qualifiedName, owner)` sinh file ở đường output source; `owner` được khai báo là originating element để tool/build system có thông tin nguồn liên quan.
8. `generatedNames` bảo vệ tránh xử lý lặp cùng tên trong một lần chạy processor. Nó **không thay thế** các kiểm tra xung đột với source/JAR có sẵn; `Filer` vẫn có thể báo lỗi.
9. `Diagnostic.Kind.ERROR` khiến lỗi được compiler báo như diagnostic và thường dẫn tới compile thất bại, thay vì chỉ in console rồi để lỗi bị bỏ qua.
10. `return true` báo processor claim các annotation types được yêu cầu xử lý trong lần gọi này. Nó **không** nghĩa là đã duyệt hết mọi annotation của project.

**Giới hạn chủ đích của demo:** tên lớp sinh được ghép từ tên class Java và chuỗi `Greeting`; chúng ta không sinh Java string literal từ một tham số annotation tùy ý. Với processor sinh code từ dữ liệu người dùng, cần escape/validate ký tự hoặc dùng code generation API phù hợp để tránh tạo Java source không hợp lệ.

### 5.3 Source được gắn annotation — `src/sample/HelloService.java`

~~~java
package sample;

import demo.AutoGreeting;

@AutoGreeting
public class HelloService {
}
~~~

`HelloService` được đặt trong package `sample`. Nếu processor hoạt động đúng, file source được tạo sẽ là `sample/HelloServiceGreeting.java`, và class hoàn tất sẽ là `sample.HelloServiceGreeting`.

### 5.4 Ứng dụng sử dụng class sinh — `src/sample/Main.java`

~~~java
package sample;

public final class Main {
    public static void main(String[] args) {
        System.out.println(HelloServiceGreeting.message());
    }
}
~~~

Khi chỉ nhìn hai file source ban đầu ở package `sample`, `HelloServiceGreeting` chưa tồn tại. Nó được processor tạo ra trong quá trình compile. Ví dụ vì vậy chứng minh được annotation processing **có thể tạo source trước khi compiler hoàn tất biên dịch các class sử dụng source đó**.

## 6. Biên dịch và chạy toàn bộ ví dụ

### Bước 1 — Biên dịch annotation và processor

~~~bash
javac --release 17 -encoding UTF-8 -d build/tools src/demo/AutoGreeting.java src/demo/processor/GreetingProcessor.java
~~~

Lệnh này tạo ít nhất:

~~~text
build/tools/
└── demo/
    ├── AutoGreeting.class
    └── processor/
        └── GreetingProcessor.class
~~~

Ở bước này, processor chưa được yêu cầu chạy: ta đang **biên dịch chính class processor** như code Java thông thường.

### Bước 2 — Cho javac chạy processor với source ứng dụng

~~~bash
javac --release 17 -encoding UTF-8 -cp build/tools -processorpath build/tools -processor demo.processor.GreetingProcessor -s build/generated -d build/classes src/sample/HelloService.java src/sample/Main.java
~~~

Ý nghĩa các phần:

| Tùy chọn | Vai trò |
| --- | --- |
| `--release 17` | Kiểm tra cú pháp, platform API và class-file target của Java 17 |
| `-encoding UTF-8` | Đọc source files bằng UTF-8 |
| `-cp build/tools` | Cho source ứng dụng resolve annotation `demo.AutoGreeting` |
| `-processorpath build/tools` | Cho javac **load processor** và các dependency của nó |
| `-processor demo.processor.GreetingProcessor` | Chọn đích danh processor cần chạy, không cần file service registration |
| `-s build/generated` | Thư mục ghi **generated source files** do `Filer` tạo |
| `-d build/classes` | Thư mục ghi class files sau compile |
| `src/sample/HelloService.java`, `src/sample/Main.java` | Hai source files ban đầu cần biên dịch |

Cả `-cp` và `-processorpath` đều trỏ tới `build/tools` **trong demo đơn giản này**, nhưng chúng có trách nhiệm khác nhau. Ở project thực tế, processor dependencies và application compile dependencies thường nên được tách.

Sau lệnh thành công, kết quả điển hình:

~~~text
build/
├── tools/
│   └── demo/...
├── generated/
│   └── sample/
│       └── HelloServiceGreeting.java
└── classes/
    └── sample/
        ├── HelloService.class
        ├── HelloServiceGreeting.class
        └── Main.class
~~~

Source file được sinh sẽ có nội dung tương đương:

~~~java
package sample;

public final class HelloServiceGreeting {
    private HelloServiceGreeting() {}
    public static String message() {
        return "Hello from HelloService";
    }
}
~~~

Vì `-s build/generated` được cấu hình, source đi vào thư mục đó. Khi javac xử lý source mới sinh và compile thành công, binary tương ứng ở `build/classes`.

### Bước 3 — Chạy ứng dụng

~~~bash
java -cp build/classes sample.Main
~~~

Stdout chính xác của ví dụ:

~~~text
Hello from HelloService
~~~

Khi chạy chương trình này, bạn không cần đưa `build/tools` lên runtime classpath: `HelloServiceGreeting.class` chứa mã bình thường, annotation có retention `SOURCE`, và demo không gọi tới processor hoặc annotation runtime. **Đừng áp dụng kết luận này cho mọi processor/framework**: nếu generated code hoặc ứng dụng phụ thuộc class khác khi chạy, bạn vẫn cần runtime dependency tương ứng.

### Bước 4 — Quan sát thứ tự round

Có thể thêm các tùy chọn chẩn đoán của `javac`:

~~~bash
javac -XprintRounds -XprintProcessorInfo --release 17 -encoding UTF-8 -cp build/tools -processorpath build/tools -processor demo.processor.GreetingProcessor -s build/generated -d build/classes src/sample/HelloService.java src/sample/Main.java
~~~

**Hãy thử trên output mới hoặc dọn riêng generated/output demo trước khi chạy lại.** Processor dùng `Filer` để tạo file; nếu bạn giữ nguyên source sinh cũ, hành vi build/rebuild và cảnh báo liên quan file đã tồn tại có thể gây nhiễu. Dùng thư mục `build/generated-second` và `build/classes-second` mới khi chỉ muốn quan sát:

~~~bash
javac -XprintRounds -XprintProcessorInfo --release 17 -encoding UTF-8 -cp build/tools -processorpath build/tools -processor demo.processor.GreetingProcessor -s build/generated-second -d build/classes-second src/sample/HelloService.java src/sample/Main.java
~~~

Trước lệnh thứ hai, tạo `build/generated-second` và `build/classes-second` như cách tạo output ở mục 4. Thông tin chẩn đoán sẽ thể hiện các round, phần root và annotation types; định dạng, độ dài, thứ tự phần tử và wording có thể thay đổi theo JDK.

Trong demo, bạn mong đợi:

- Một round nhận source gốc chứa `@AutoGreeting`.
- Một round tiếp theo có generated type `HelloServiceGreeting`.
- Final round mà `processingOver()` là `true`.

Không cần kỳ vọng chính xác từng dòng do `-XprintRounds` in ra, vì đó là output chẩn đoán của compiler chứ không phải stdout có hợp đồng ổn định của ứng dụng.

## 7. Hiểu vòng xử lý bằng ví dụ vừa chạy

### Round đầu

Processor được gọi vì có annotation `demo.AutoGreeting` thuộc supported types. Một số giá trị có ý nghĩa:

- `roundEnv.processingOver() == false`.
- `roundEnv.getElementsAnnotatedWith(AutoGreeting.class)` chứa `HelloService`.
- `getRootElements()` có thể chứa cả `HelloService` và `Main` (các root ban đầu) dù chỉ một trong hai được annotate.
- `annotations` là tập annotation types được giao để xử lý; nó **không phải** tập các class `HelloService`.

Processor tạo `sample.HelloServiceGreeting` qua `Filer`. File source mới không làm thay đổi ngay nội dung mảng root của round đầu.

### Round tiếp theo

Khi javac xử lý source vừa sinh, nó có thể đưa `HelloServiceGreeting` vào roots của round mới. Class này **không mang `@AutoGreeting`**, nên kết quả `getElementsAnnotatedWith(AutoGreeting.class)` có thể rỗng. Processor cần chấp nhận điều đó như trạng thái hợp lệ.

Điều rất quan trọng: **processor đã được gọi ở một round thì có thể tiếp tục được gọi ở các round sau, gồm final round, ngay cả khi không còn annotation mới của nó**. Đừng viết code kiểu “nếu annotations rỗng là có lỗi”.

### Final round

Trong lần gọi cuối, `processingOver()` thường là true; code demo trả true ngay, không sinh source mới. `errorRaised()` lúc này có thể cho biết round trước đã báo error, nhưng không có nghĩa mọi phần tử của những round trước được tập hợp lại ở đây.

### Lưu trạng thái qua các round

Một instance processor thường được compiler dùng xuyên suốt một lần chạy annotation processing; nó không được tạo mới cho từng round. Vì thế trường `generatedNames` trong demo lưu trạng thái theo **lần chạy compiler/processor**, cho phép tránh sinh cùng qualified name hai lần trong trường hợp callback có dữ liệu lặp.

Không dựa vào trường instance đó để giữ state qua **các lần build riêng biệt**. Một lần gọi `javac` mới thường tạo processing environment mới. Build incremental của tool có chính sách caching riêng, không được suy ra từ một biến instance trong processor.

## 8. Duyệt root khác gì tìm annotation?

Giả sử có source:

~~~java
package sample;

@AutoGreeting
class PackageWorker {
    void run() {}
}

class PlainWorker {
    void stop() {}
}
~~~

Đây là snippet minh họa, giả định `AutoGreeting` import phù hợp; không phải source độc lập cho demo, và không dùng nó cùng tên class khác trong package khi copy.

- `getRootElements()` trả các **root types** mà compiler đang xử lý trong round. Nó có thể bao gồm annotated và non-annotated types.
- `getElementsAnnotatedWith(AutoGreeting.class)` trả những declaration được gắn `@AutoGreeting` trong phạm vi tìm kiếm; `PlainWorker` không khớp.
- Khi cần tìm method `run` trong `PackageWorker` mà method không mang annotation riêng, bạn phải lấy `TypeElement` rồi duyệt `getEnclosedElements()`; `getElementsAnnotatedWith(AutoGreeting.class)` không tự trả mọi method con.

Nếu annotation có `@Target(METHOD)`, method được annotate có thể được trả trực tiếp bởi `getElementsAnnotatedWith` mặc dù không nằm trong `getRootElements()` dưới dạng một root riêng.

### Khi cần truy vấn nhiều loại annotation

Với một processor hỗ trợ `@A` và `@B`, bạn có thể:

1. Gọi `getElementsAnnotatedWith(aType)` và `getElementsAnnotatedWith(bType)` riêng để có hai tập.
2. Dùng `getElementsAnnotatedWithAny(aType, bType)` để có hợp các phần tử.
3. Kiểm tra `AnnotationMirror` hoặc method thích hợp nếu một element có nhiều annotation và yêu cầu xử lý khác nhau.

Trường hợp `@Repeatable` đặc biệt: compiler có thể biểu diễn các annotation lặp bằng container; hãy xem cả repeatable annotation và container type. Đừng mặc định `getElementsAnnotatedWith(MyRepeatable.class)` trong mọi môi trường đủ mô tả tất cả trạng thái lặp.

## 9. Khai báo supported annotation types và ý nghĩa return value

Processor của demo dùng:

~~~java
@SupportedAnnotationTypes("demo.AutoGreeting")
~~~

Đây là declarative metadata để tool quyết định khi nào processor phù hợp với annotation types hiện diện. Lưu ý:

- Tên cần đầy đủ và chính xác.
- Có thể khai báo nhiều loại nếu processor xử lý chúng.
- `@SupportedAnnotationTypes("*")` là cách hỗ trợ mọi annotation types theo hợp đồng API, nhưng không nên dùng bừa vì có thể ảnh hưởng processor khác.
- Một processor hỗ trợ `"*"` thường nên `return false` nếu chỉ quan sát/kiểm tra mà không muốn claim mọi annotation types.

`process(...)` trả:

- **`true`**: processor claim những annotation types được giao trong lần gọi, khiến các processor phía sau không còn được yêu cầu xử lý cùng những types đó theo cơ chế claim.
- **`false`**: không claim; processor khác vẫn có thể xử lý chúng.

Đừng hiểu `true` là “processor không có lỗi”, “không còn round” hay “mọi element trong project đã được xử lý”. Nó chỉ là quyết định **claim annotation types của lần gọi hiện tại**.

Với processor riêng cho `demo.AutoGreeting`, `return true` phù hợp khi nó đảm nhận annotation này. Trong hệ thống gồm nhiều processor phối hợp, lựa chọn true/false phải theo contract của mỗi processor.

## 10. Cách phát diagnostic đúng vị trí

Khi người dùng gắn annotation sai mục tiêu hoặc cấu hình sinh code bất hợp lệ, đừng chỉ dùng `System.out.println`. Hãy dùng `Messager`:

~~~java
processingEnv.getMessager().printMessage(
        Diagnostic.Kind.ERROR,
        "Chi ho tro class thong thuong",
        element
);
~~~

Đây là snippet bên trong processor, cần biến `element` và import `javax.tools.Diagnostic`. Việc truyền `element` cho phép compiler liên hệ diagnostic tới một declaration; IDE/build tool thường có thể hiển thị vị trí lỗi tốt hơn.

Các mức phổ biến:

| Diagnostic kind | Mục đích |
| --- | --- |
| `ERROR` | Lỗi khiến compilation không thể được coi là thành công |
| `WARNING` | Cảnh báo vấn đề nhưng không nhất thiết chặn compilation |
| `MANDATORY_WARNING` | Cảnh báo có yêu cầu hiển thị theo cơ chế tool |
| `NOTE` | Thông tin hỗ trợ chẩn đoán |
| `OTHER` | Thông điệp không thuộc các loại trên |

Nếu cần một thông báo chỉ ra annotation cụ thể, các overload của `Messager.printMessage` có thể nhận `AnnotationMirror` và `AnnotationValue` bên cạnh `Element`. Không phải mọi trường hợp lỗi đều gắn được tới một annotation vị trí chính xác; khi không có vị trí, thông báo có thể ít cụ thể hơn.

### Thực hành: chủ động báo lỗi đúng loại phần tử

Processor demo chỉ xử lý `ElementKind.CLASS`. `@Target(ElementType.TYPE)` cho phép cả một số loại khai báo type khác. Nếu bạn gắn `@AutoGreeting` lên interface:

~~~java
@AutoGreeting
public interface GreetingContract {
}
~~~

Đây là snippet, không phải chương trình chạy độc lập; đặt trong file `GreetingContract.java` có package/import hợp lệ nếu muốn thử. Annotation hợp lệ theo `@Target(TYPE)`, nhưng processor sẽ phát `ERROR` vì element kind không phải `CLASS`.

Điều này minh họa sự khác nhau giữa **giới hạn do annotation target cho phép** và **ràng buộc nghiệp vụ do processor tự kiểm tra**.

## 11. Dùng Filer đúng theo round

`Filer` là công cụ chính thống để processor tạo source, class hoặc resource file. Nó giúp javac biết file nào được sinh ra trong annotation processing. Tự ghi file bằng `Files.writeString` đến đường dẫn tùy tiện có thể khiến build tool và compiler không biết artifact thuộc processing round nào.

Trong demo:

~~~java
JavaFileObject file = processingEnv.getFiler()
        .createSourceFile(qualifiedName, owner);
~~~

- `qualifiedName` phải là tên type phù hợp, ví dụ `sample.HelloServiceGreeting`.
- `owner` là originating element, giúp liên hệ file sinh với source cần thiết.
- `createSourceFile` không có nghĩa compiler đã compile ngay class đó trong round hiện tại.
- `file.openWriter()` mở writer để ghi source. Sau khi đóng writer, compiler có thể đọc file ở round tiếp.
- `-s build/generated` định vị generated source output; `-d build/classes` định vị binary output.
- `Filer` có quy tắc không tạo lại cùng pathname/type nhiều lần trong một run. Nếu sinh trùng, có thể gặp `FilerException`, một subtype của `IOException`.

### Vì sao tạo trùng là lỗi phổ biến?

Nếu processor thấy cùng target nhiều lần do cách tổ chức rounds, hoặc hai class khác nhau cùng sinh tên `sample.Generated`, lời gọi tạo file lần thứ hai sẽ xung đột. `generatedNames` giúp tránh **một số tình huống lặp trong processor này**, nhưng không xử lý mọi xung đột với processor khác hoặc type đã tồn tại.

Cách đặt tên artifact cần deterministic, tránh collision và tính toán được từ declaration đầu vào. Nếu có nhiều declaration cùng sinh một registry chung, bạn có thể cần tổng hợp state và tạo file đúng một lần ở thời điểm phù hợp; lựa chọn phụ thuộc contract của `Filer` và việc file sinh cần được compiler xử lý tiếp hay chỉ là resource tổng hợp.

### Không sửa trực tiếp source gốc từ processor

Processor nên **đọc model và sinh file mới**, không tự chỉnh `HelloService.java` đang được compiler phân tích. Sửa source gốc trong khi compiler đang chạy tạo vấn đề về đồng bộ trạng thái, build reproducibility và tính đúng của compilation.

## 12. Lỗi và giới hạn thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `getElementsAnnotatedWith(...)` luôn rỗng | Annotation không nằm trong round, supported type sai, processor không thực sự được gọi hoặc annotation nằm ở vị trí không được API tìm | Kiểm tra tên annotation, `-processor`, source được compile và `-XprintRounds` |
| `annotations` rỗng trong một round | Không có annotation type mới được giao cho processor trong round đó | Xử lý hợp lệ; không coi đó là exception |
| `getRootElements()` không chứa source từ round trước | Root thuộc từng round, không phải toàn bộ project | Lưu thông tin cần thiết nếu phải tổng hợp qua rounds |
| `ClassCastException` khi ép `Element` thành `TypeElement` | Annotation có thể gắn vào method/field/parameter | Kiểm tra `ElementKind` |
| `ClassNotFoundException` khi load type đang compile | Dùng Java Reflection thay vì compiler model | Dùng `TypeElement` và `TypeMirror` |
| Không tìm thấy processor | Sai `-processorpath`, chưa build processor, tên class sai hoặc thiếu dependency của processor | Xem `build/tools` và tên `demo.processor.GreetingProcessor` |
| Không tìm thấy annotation trong source app | Annotation không nằm trên compile classpath | Thêm `build/tools` vào `-cp` cho demo |
| `FilerException: Attempt to recreate a file...` | Sinh cùng file/type nhiều lần hoặc xung đột với input | Kiểm tra tên sinh, state và cách chia trách nhiệm giữa processors |
| Chạy javac được nhưng không thấy file sinh | Processor chưa chạy, không có element khớp hoặc `-s` trỏ nơi khác | Kiểm tra `-XprintProcessorInfo`, `-XprintRounds`, source output |
| Processor sinh code nhưng app không compile | Generated source sai cú pháp/type, xung đột tên hoặc thiếu dependency | Xem generated source và diagnostic đầu tiên |
| Processor chỉ nhìn annotation trong round 1 | Không xử lý đúng vòng tiếp theo | Hiểu root và annotated elements ở từng round |
| Lỗi sau khi `errorRaised()` trả false | Hàm báo lỗi **ở round trước**, không phải cờ cập nhật tức thì | Theo dõi lỗi vừa phát bằng state riêng |
| Đang ở final round nhưng vẫn sinh source mong compiler compile | Không còn round tiếp xử lý generated types | Tạo source ở vòng phù hợp trước khi `processingOver()==true` |
| Thứ tự output ngẫu nhiên | Duyệt `Set` không có thứ tự contract | Sort bằng khóa ổn định trước khi xuất báo cáo |
| Processor “cướp” annotation của processor khác | `return true`/`"*"` claim quá rộng | Khai báo supported types đúng và chọn return value phù hợp |

### Điểm cần nhớ về `errorRaised()`

Nếu một processor tạo `ERROR` ở round hiện tại, compiler thường vẫn hoàn thành round theo quy tắc của tool, rồi round tiếp theo có thể phản ánh lỗi đó bằng `errorRaised()`. Đừng cố lấy `roundEnv.errorRaised()` thay cho biến `hasErrorThisRound` trong cùng lời gọi `process`.

Nếu mục đích của bạn chỉ là ngăn sinh file tiếp khi đã có lỗi, có thể giữ state riêng và kết hợp với kiểm tra `errorRaised()` của các round tiếp theo. Đừng giả định compiler sẽ tiếp tục sinh/compile mọi file như bình thường sau một lỗi nghiêm trọng.

## 13. Annotation kế thừa, nested type và repeatable annotation

### 13.1 `@Inherited`

Với một annotation type có `@Inherited` và cho phép gắn trên class, class con có thể được xem là có annotation thông qua cơ chế kế thừa dù nó không trực tiếp ghi annotation trong source. `getElementsAnnotatedWith(...)` có thể trả declaration dựa trên quy tắc hiện diện của annotation.

Nhưng `@Inherited` không tự áp dụng tương tự cho method, field hay interface ở mọi ngữ cảnh. Khi phải phân biệt “được viết trực tiếp” và “được xem là hiện diện qua kế thừa”, dùng các API annotation/model thích hợp và hiểu chính xác semantics của annotation.

### 13.2 Nested type

Một root có thể chứa nested classes được gắn annotation. `getElementsAnnotatedWith` có thể tìm phần tử được annotate ở các type được bao gồm của round, không chỉ root top-level. `TypeElement.getQualifiedName()` cho nested type mang tên phù hợp mô hình Java; đừng giả định tên nested luôn có hình thức đơn giản như top-level hoặc dùng `getSimpleName()` làm định danh toàn cục duy nhất.

### 13.3 Record components và parameters

Trong Java 17, compile-time model hỗ trợ các declaration hiện đại như record và record components. Nếu một annotation được phép ở target tương ứng, truy vấn annotated elements có thể trả `RecordComponentElement` hoặc `VariableElement` cho parameter, thay vì `TypeElement`.

Khi thiết kế processor hỗ trợ nhiều target, dùng phân nhánh `ElementKind`, `instanceof` hoặc visitor pattern của javax.lang.model; không ép mọi annotated element về class.

### 13.4 Repeating annotations

Khi khai báo một annotation `@Repeatable(Container.class)`, compiler có thể biểu diễn nhiều lần gắn cùng annotation thông qua container. Processor nên khai báo các supported annotation types cần thiết và kiểm tra retrieval API theo chính sách xử lý annotation lặp.

Java 17 có `getElementsAnnotatedWithAny(...)` hỗ trợ lấy hợp các annotated elements theo nhiều annotation types; nhưng bạn vẫn cần giải nghĩa các **giá trị annotation** và container nếu logic nghiệp vụ phụ thuộc số lần lặp.

## 14. Một processor duyệt phần tử phương thức sẽ khác ra sao?

Ví dụ cho phép annotation ở method:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
public @interface ValidateCall {
}
~~~

Đây là một annotation declaration có thể đặt trong `demo/ValidateCall.java`. Một processor hỗ trợ `demo.ValidateCall` có thể duyệt:

~~~java
for (Element element :
        roundEnv.getElementsAnnotatedWith(ValidateCall.class)) {
    if (element.getKind() != ElementKind.METHOD) {
        continue;
    }

    ExecutableElement method = (ExecutableElement) element;
    String name = method.getSimpleName().toString();
    int parameterCount = method.getParameters().size();

    processingEnv.getMessager().printMessage(
            Diagnostic.Kind.NOTE,
            name + " has " + parameterCount + " parameter(s)",
            method
    );
}
~~~

Đây là **snippet** đặt trong `process(...)` với import cho `ExecutableElement`, `Element`, `ElementKind`, `Diagnostic` và annotation `ValidateCall`. Khi method được annotate, `getElementsAnnotatedWith` đưa bạn tới chính method declaration, không cần duyệt từng root rồi tìm text chứa dấu `@ValidateCall`.

Ví dụ này cũng cho thấy vì sao `Element` là mô hình declaration: chúng ta lấy tham số từ `ExecutableElement.getParameters()` mà không nạp class vừa biên dịch bằng Reflection.

## 15. Cách kiểm thử processor đúng phạm vi

Một processor cần được kiểm thử ít nhất ở các tình huống:

1. **Một class được annotate:** source được sinh đúng tên, package và nội dung.
2. **Nhiều class được annotate:** mỗi type có artifact riêng, không phụ thuộc iteration order.
3. **Không có annotation khớp:** không ném exception; processor có thể không được chọn ở round đầu nếu không có annotation phù hợp.
4. **Annotation ở target không được processor chấp nhận:** nhận diagnostic `ERROR` rõ vị trí.
5. **Tạo source mới qua nhiều rounds:** generated type được compile và processor không sinh lặp.
6. **Xung đột tên output:** xử lý diagnostic đúng, không âm thầm ghi đè file người dùng.
7. **Compilation thất bại:** không tạo “success report” sai khi đã có diagnostic lỗi.
8. **Biên dịch lặp lại trên output sạch:** kết quả không phụ thuộc artifact cũ.

Để tách biến khi kiểm thử demo, giữ `build/tools` là output processor, tạo một cặp output generated/classes mới cho mỗi lần compile app. Lúc debug, xem cả stdout/stderr và file source trong `-s`, không chỉ xem exit code.

### Thử với hai class mang annotation

Tạo thêm file độc lập **`src/sample/AnotherService.java`**:

~~~java
package sample;

import demo.AutoGreeting;

@AutoGreeting
public class AnotherService {
}
~~~

Compile app với thêm source này, ví dụ:

~~~bash
javac --release 17 -encoding UTF-8 -cp build/tools -processorpath build/tools -processor demo.processor.GreetingProcessor -s build/generated-multi -d build/classes-multi src/sample/HelloService.java src/sample/AnotherService.java src/sample/Main.java
~~~

Trước đó tạo hai thư mục output mới `build/generated-multi` và `build/classes-multi`. Processor tạo hai source:

- `sample.HelloServiceGreeting` với `message()` trả `Hello from HelloService`.
- `sample.AnotherServiceGreeting` với `message()` trả `Hello from AnotherService`.

Vì `Main` của demo chỉ gọi `HelloServiceGreeting.message()`, stdout khi chạy:

~~~bash
java -cp build/classes-multi sample.Main
~~~

vẫn là:

~~~text
Hello from HelloService
~~~

Đây là điều mong đợi. Tên class được sinh riêng là bằng chứng hai annotated elements đã được xử lý; một output ứng dụng không nhất thiết phải in tất cả generated classes.

## 16. Chẩn đoán khi processor không chạy

### Bước 1 — Processor class đã tồn tại chưa?

Kiểm tra file:

~~~text
build/tools/demo/processor/GreetingProcessor.class
build/tools/demo/AutoGreeting.class
~~~

Nếu thiếu, biên dịch lại bước 1. `-processor demo.processor.GreetingProcessor` đòi hỏi processor class có thể được processor class loader tìm thấy.

### Bước 2 — Compiler có thực sự chỉ định processor không?

Dùng `-processor` tường minh như bài thực hành. Trong project build tool, processor có thể được đăng ký qua file service:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

nội dung là tên fully qualified của processor. Tuy nhiên, ví dụ này **không cần** service file vì đã dùng `-processor`. Đừng vừa thiếu service file vừa không truyền `-processor` rồi kết luận `RoundEnvironment` bị lỗi.

### Bước 3 — Annotation type có đúng không?

`@SupportedAnnotationTypes` của demo dùng `demo.AutoGreeting`. Trong source ứng dụng cũng phải là annotation ấy, không phải một annotation khác có cùng tên ngắn được import từ package khác.

### Bước 4 — Input source có nằm trong invocation?

Nếu bạn chỉ compile `src/sample/Main.java` mà không cung cấp hoặc làm cho `HelloService` và annotation được nhận diện, đừng trông chờ processor luôn tìm mọi class trong project trên ổ đĩa. `RoundEnvironment` chỉ thấy những phần tử mà compiler thực sự đưa vào các round của invocation.

### Bước 5 — Xem log rounds

Thêm `-XprintRounds -XprintProcessorInfo`, dùng output mới. Nếu processor không được gọi hoặc annotation không được phát hiện, log giúp thu hẹp vị trí vấn đề. Nếu processor chạy nhưng không tạo file, kiểm tra nhánh `processingOver()`, tập `getElementsAnnotatedWith(...)` và diagnostic.

### Bước 6 — Phân biệt generated source và generated class

`-s` và `-d` là hai đường output khác nhau. Nhìn thấy file `HelloServiceGreeting.java` không đủ chứng minh compiler đã tạo `HelloServiceGreeting.class` thành công. Nếu generated source có lỗi cú pháp hoặc dependency, javac có thể thất bại trước khi tạo binary hợp lệ.

## 17. Bài tập và đáp án kiểm chứng

### Bài 1 — Root hay annotated element?

Một round chứa hai root types `A` và `B`, chỉ `A` gắn `@AutoGreeting`. `getRootElements()` và `getElementsAnnotatedWith(AutoGreeting.class)` khác nhau thế nào?

**Đáp án:** root set có thể chứa cả A và B; annotated set chỉ gồm declaration khớp, ở đây là A. Không suy ra thứ tự duyệt từ `Set`.

### Bài 2 — Final round

Processor đang ở final round và `roundEnv.processingOver()` là true. Có nên gọi `Filer.createSourceFile` rồi kỳ vọng javac lập round tiếp để compile file này?

**Đáp án:** Không. Final round không cam kết có round tiếp để xử lý các type mới. Source cần compile nên sinh trước giai đoạn kết thúc.

### Bài 3 — Method annotation

Với annotation `@ValidateCall` gắn vào method, vì sao ép mọi kết quả `getElementsAnnotatedWith(ValidateCall.class)` thành `TypeElement` là sai?

**Đáp án:** method là `ExecutableElement`; phải kiểm tra `ElementKind.METHOD` rồi ép kiểu phù hợp.

### Bài 4 — `errorRaised()`

Ngay sau khi gọi `Messager.printMessage(ERROR, ...)` trong `process`, bạn kiểm tra `roundEnv.errorRaised()`. Hàm này có bắt buộc thành true ngay lúc đó không?

**Đáp án:** Không. `errorRaised()` mô tả lỗi từ **round trước**; muốn biết lỗi vừa phát ở round này, phải theo dõi bằng state của processor.

### Bài 5 — Nhiều round

Round 1 của demo tạo `HelloServiceGreeting.java`. Vì sao round 2 có thể có root mới nhưng `getElementsAnnotatedWith(AutoGreeting.class)` lại rỗng?

**Đáp án:** generated type không mang `@AutoGreeting`, nên nó có thể là root nhưng không phải annotated element phù hợp. Processor phải chấp nhận tập rỗng.

### Bài 6 — Classpath và processorpath

Tại sao demo dùng đồng thời `-cp build/tools` và `-processorpath build/tools`?

**Đáp án:** source ứng dụng cần thấy annotation type để compile; compiler cần tìm và nạp processor class để chạy. Đây là hai vai trò khác nhau dù demo dùng chung thư mục.

### Bài 7 — Generated output

Sau lệnh compile, bạn thấy `build/generated/sample/HelloServiceGreeting.java` nhưng thiếu `build/classes/sample/HelloServiceGreeting.class`. Có thể kết luận processor chưa hoạt động không?

**Đáp án:** Không. Source đã được sinh chứng minh processor/Filer đã thực hiện một phần công việc. Cần xem diagnostic vì compilation có thể dừng trước khi sinh class file.

### Bài 8 — Claim annotation

Nếu processor hỗ trợ `demo.AutoGreeting`, duyệt xong và `return true`, điều này có nghĩa toàn bộ annotation của mọi module đã xử lý hoàn tất không?

**Đáp án:** Không. Giá trị true chỉ claim những annotation types được giao ở lần gọi process hiện tại, không mô tả toàn bộ project.

## 18. Checklist hoàn thành

- [ ] Tôi hiểu `RoundEnvironment` cung cấp thông tin theo **round**.
- [ ] Tôi phân biệt root elements với annotated elements.
- [ ] Tôi biết dùng `getElementsAnnotatedWith(Class/TypeElement)`.
- [ ] Tôi không dựa vào iteration order của `Set` khi sinh artifact deterministic.
- [ ] Tôi kiểm tra `ElementKind` trước khi ép kiểu.
- [ ] Tôi dùng compile-time `Element`/`TypeMirror` thay vì Reflection khi phân tích source chưa compile.
- [ ] Tôi xử lý được `processingOver()` và hiểu ý nghĩa round trước của `errorRaised()`.
- [ ] Tôi không sinh trùng type/source bằng `Filer`.
- [ ] Tôi biết giải thích `return true` và `return false` của `process`.
- [ ] Tôi đã compile annotation/processor, chạy `javac -processor` và xem generated source.
- [ ] Tôi đã chạy `sample.Main` và nhận `Hello from HelloService`.
- [ ] Tôi biết debug với `-XprintRounds` và `-XprintProcessorInfo`.
- [ ] Tôi biết kiểm tra annotation, compile classpath, processorpath, `-s` và `-d` khi thiếu file.
- [ ] Tôi phân biệt demo runnable với các đoạn snippet giải thích API.

## Tài liệu tham khảo

- [Java SE 17 — RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html)
- [Java SE 17 — Processor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html)
- [Java SE 17 — AbstractProcessor](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html)
- [Java SE 17 — javax.annotation.processing package](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html)

## Ghi nhớ

**`RoundEnvironment` là cửa sổ nhìn vào từng annotation-processing round, không phải kho dữ liệu toàn bộ project.** `getRootElements()` trả các root của round; `getElementsAnnotatedWith(...)` tìm declaration có annotation trong phạm vi round; `processingOver()` và `errorRaised()` giúp điều khiển cách processor phản ứng với tiến trình biên dịch. Kết hợp các API ấy với `ElementKind`, compiler model, `Filer` và diagnostic đúng vị trí là nền tảng để tạo processor đáng tin cậy, có thể tái lập và hỗ trợ nhiều vòng sinh source.