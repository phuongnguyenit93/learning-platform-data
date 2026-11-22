# Phân biệt annotation processing với reflection và biến đổi AST trong Java

Khi gặp một annotation như `@Override`, `@Deprecated`, `@Entity` hoặc `@GenerateBuilder`, người học dễ hiểu nhầm rằng bản thân annotation “tự chạy” và sửa mã Java. Thực tế **annotation là metadata**; hành vi phụ thuộc vào **công cụ đọc metadata**, **thời điểm đọc** và **API được phép thao tác**. Ba cơ chế cần phân biệt là:

1. **Annotation processing (JSR 269)**: công cụ được compiler kích hoạt trong quá trình biên dịch, đọc mô hình khai báo/kiểu, xác minh quy tắc và thường **sinh tệp Java, class hoặc tài nguyên mới**.
2. **Reflection**: chương trình đang chạy dùng API như `Class.getAnnotation(...)`, `getDeclaredMethods()` để **quan sát cấu trúc và annotation được giữ lại ở runtime**, có thể gọi method theo quyền truy cập được cấp.
3. **Biến đổi AST (Abstract Syntax Tree transformation)**: can thiệp vào **cây cú pháp nội bộ hoặc các pha compiler** để thay đổi cấu trúc chương trình, chẳng hạn thêm field, constructor hoặc method vào kiểu đang được biên dịch. Đây **không phải** quyền chỉnh sửa chuẩn của JSR 269.

Bài học nằm trong ngữ cảnh **biên dịch Java**: cần biết compiler quan sát annotation lúc nào, các công cụ có thể làm gì, cách tổ chức build, và vì sao annotation processor thông thường không đồng nghĩa với cơ chế sửa trực tiếp AST.

## 1. Bảng so sánh nhanh

| Tiêu chí | Annotation processing (JSR 269) | Reflection | Biến đổi AST |
| --- | --- | --- | --- |
| Thời điểm chính | Trong **build/compile** qua `javac` hoặc compiler tương thích | Khi **chương trình chạy**; cũng có thể được công cụ khác dùng trên class đã nạp | Trong pipeline parser/compiler hoặc một công cụ phân tích/biến đổi source |
| Đối tượng quan sát | `Element`, `TypeMirror`, `RoundEnvironment` và annotation trên mô hình ngôn ngữ | `Class`, `Method`, `Field`, `Constructor` và annotation runtime | Các node cây cú pháp, thông tin vị trí, cấu trúc biểu thức/câu lệnh |
| API đặc trưng | `javax.annotation.processing`, `javax.lang.model`, `Filer`, `Messager` | `java.lang.reflect`, `java.lang.annotation` | API tree/compiler/plugin hoặc thư viện AST tùy công cụ |
| Kết quả thường gặp | Sinh source/resource; kiểm tra và phát diagnostic; sinh class mới | Đọc metadata, tìm thành viên, gọi method qua reflection | Sửa/thay thế node, chèn khai báo, viết lại mã hoặc thay bước compiler |
| Có tự sửa trực tiếp thân class gốc? | **Không**, không được API JSR 269 chuẩn cung cấp | **Không**, reflection không viết lại định nghĩa class đã biên dịch | **Có thể**, tùy framework/compiler và giới hạn hỗ trợ |
| Annotation retention cần thiết | Có thể đọc annotation ở compile-time kể cả `SOURCE` | Phải là `RUNTIME` mới thấy annotation qua reflection chuẩn | Tùy lúc và cơ chế đọc AST, không nhất thiết dựa vào runtime retention |
| Khả năng di động | Tương đối tốt nếu chỉ dùng API chuẩn JSR 269 | API reflection chuẩn của Java | Thường phụ thuộc compiler/phiên bản nếu thao tác cây nội bộ |
| Ví dụ | Dagger, AutoService, MapStruct (theo cơ chế sinh code), processor tự viết | Framework quét `@Controller`, đọc `@Test` lúc chạy | Một số kỹ thuật của Lombok, javac compiler plugin hoặc trình biến đổi source |

**Chú ý:** tên một thư viện không thay thế việc kiểm tra cách nó hoạt động. Một framework có thể phối hợp annotation processor, reflection, code generation và bytecode instrumentation. Bản thân chữ `@` không quyết định thời điểm hay phương pháp xử lý.

## 2. Annotation chỉ định dữ liệu; công cụ quyết định hành vi

Xét:

~~~java
@Deprecated
public void oldMethod() {
}
~~~

`@Deprecated` là metadata. Compiler và IDE có thể cảnh báo khi phương thức đã lỗi thời được dùng; annotation không tự thực thi một lệnh thay đổi object lúc runtime. Tương tự, annotation của ứng dụng như `@GenerateGreeting` chỉ tạo ra sản phẩm khi có một processor **được cấu hình và chạy** để hiểu annotation ấy.

Một annotation type khai báo như interface đặc biệt:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
~~~

Đoạn này chỉ minh họa khai báo annotation. Nó chưa có processor và cũng chưa có `main`.

- `@Target(TYPE)` giới hạn nơi sử dụng về mặt cú pháp/kiểu khai báo (class, interface, enum, annotation type, record tùy quy tắc).
- `@Retention(SOURCE)` quy định annotation không cần được ghi vào file `.class`. Compiler/processor **vẫn có thể đọc nó trong quá trình xử lý nguồn**.
- Việc processor hiểu `@GenerateGreeting` là yêu cầu do processor lập trình, **không phải** năng lực có sẵn do `@Retention` hoặc `@Target` tạo ra.

Annotation có thể có tham số: `public @interface Table { String name(); }` và dùng `@Table(name = "orders")`. Đây là metadata mà processor hoặc reflection có thể đọc khi retention phù hợp; nó không tự sinh SQL hoặc tự thêm field.

## 3. Ba mức retention: SOURCE, CLASS, RUNTIME

| RetentionPolicy | Có trong source? | Được ghi vào class file? | Reflection chuẩn lúc runtime đọc được? |
| --- | --- | --- | --- |
| `SOURCE` | Có | Không giữ annotation như metadata runtime/class | Không |
| `CLASS` | Có | Có, thông thường dưới dạng annotation metadata không runtime-visible | Không |
| `RUNTIME` | Có | Có, metadata runtime-visible | Có |

Nếu không ghi `@Retention`, mặc định là **`CLASS`**. Chỉ định `@Retention(RUNTIME)` khi một công cụ runtime cần đọc annotation, chứ không phải để “bật” khả năng annotation processing. Một processor JSR 269 có thể xử lý cả annotation được khai báo `SOURCE`, `CLASS` hoặc `RUNTIME` khi annotation xuất hiện trong mô hình biên dịch mà nó đang xử lý.

Ví dụ thực tế:

- **SOURCE** phù hợp metadata chỉ phục vụ kiểm tra hoặc sinh code khi compile.
- **CLASS** phù hợp công cụ đọc bytecode/metadata class mà không cần reflection runtime thông thường.
- **RUNTIME** phù hợp framework dùng reflection để tìm annotation khi ứng dụng đang chạy.

Đừng nhầm việc `Class.getAnnotations()` không thấy một annotation `CLASS` với việc annotation đó chưa từng tồn tại. Nó có thể hiện diện trong class file dưới dạng runtime-invisible annotation attribute nhưng không được reflection trả về.

`@Inherited`, nếu được dùng, chỉ ảnh hưởng một số truy vấn annotation trên **class** theo quan hệ superclass; nó không khiến annotation tự sinh code và không phải cách áp dụng annotation kế thừa cho mọi method, field hoặc interface.

## 4. Annotation processing: cơ chế JSR 269 khi javac chạy

Java cung cấp API chuẩn trong `javax.annotation.processing`. Một processor thường extends `AbstractProcessor` và thực thi:

~~~java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv
)
~~~

Đây là **chữ ký phương thức minh họa**, không phải một tệp Java độc lập. Các đối tượng chính:

- **`Processor`/`AbstractProcessor`**: hợp đồng triển khai xử lý annotation.
- **`@SupportedAnnotationTypes`**: cho biết processor hỗ trợ tên annotation type nào (hoặc processor có thể override `getSupportedAnnotationTypes()`).
- **`@SupportedSourceVersion`**: cho biết mức source language mà processor công bố hỗ trợ.
- **`RoundEnvironment`**: thông tin các phần tử gốc, phần tử được annotation và trạng thái vòng xử lý.
- **`Element`/`TypeElement`**: mô hình **khai báo** như package, type, method, field, parameter.
- **`TypeMirror`**: mô hình **kiểu** của phần tử/biểu thức trong phạm vi API tương ứng, không đồng nhất với đối tượng `java.lang.Class` đã được JVM nạp.
- **`ProcessingEnvironment`**: cung cấp `Elements`, `Types`, `Filer`, `Messager` và options.
- **`Filer`**: tạo source, class hoặc resource **mới** do processor sinh ra.
- **`Messager`**: báo `NOTE`, `WARNING` hoặc `ERROR` tới compiler ở phần tử thích hợp.

Processor chạy **trong quy trình biên dịch** với quyền thực thi mã trên môi trường build. Nó có thể đọc cấu trúc source và những kiểu compiler đang biết mà không yêu cầu phải có một đối tượng runtime của class đang được biên dịch.

### Khái niệm vòng (round)

Một luồng thường gặp:

~~~text
javac đọc nguồn đầu vào
        |
        v
Round 1: processor thấy @GenerateGreeting trên App
        |
        +--> Filer tạo AppGreeting.java
        |
        v
Round 2: compiler/processor thấy source được sinh ra
        |
        +--> các processor khác có thể xử lý annotation mới
        |
        v
Round kết thúc: processingOver() = true
        |
        v
javac hoàn tất kiểm tra kiểu và sinh các file .class phù hợp
~~~

Đây là sơ đồ **mô hình tư duy**: trình tự và số round thực tế tùy nội dung được sinh, processor và compiler. Processor không nên tự định nghĩa lại cùng một tệp trong nhiều round; `Filer` có thể báo lỗi nếu tạo trùng một path trong một lần xử lý.

**Giới hạn quan trọng:** Với API JSR 269 chuẩn, processor không có lệnh “mở class gốc và thêm field/method vào AST của nó”. Nó có thể **sinh một class mới, báo lỗi, hoặc sinh metadata/tài nguyên**. Những công cụ thực hiện chỉnh sửa khai báo đang biên dịch cần cơ chế/compiler extension khác.

## 5. Ví dụ chạy được trên Java 17: processor sinh mã nguồn mới

Ví dụ này có thể biên dịch bằng JDK 17+ (dùng `SourceVersion.RELEASE_17`) mà không cần dependency ngoài JDK. Ta sẽ tạo một annotation `@GenerateGreeting`, processor và ứng dụng dùng class mới được sinh ra.

Tạo cây file tại root dự án:

~~~text
annotation-lab/
└── src/
    ├── annotation/demo/GenerateGreeting.java
    ├── processor/demo/GreetingProcessor.java
    └── app/demo/App.java
~~~

### 5.1. Định nghĩa annotation SOURCE

**Tệp `src/annotation/demo/GenerateGreeting.java`:**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
~~~

Ở đây, retention SOURCE là đủ cho compiler/processor trong thí nghiệm. Annotation này không tồn tại trong runtime metadata của `App.class`.

### 5.2. Viết processor chuẩn JSR 269

**Tệp `src/processor/demo/GreetingProcessor.java`:**

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
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

@SupportedAnnotationTypes("demo.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateGreeting requires a class",
                        element
                );
                continue;
            }

            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(element).getQualifiedName().toString();
            String generatedName =
                    element.getSimpleName().toString() + "Greeting";
            String qualifiedName = packageName.isEmpty()
                    ? generatedName
                    : packageName + "." + generatedName;

            try {
                JavaFileObject file =
                        processingEnv.getFiler()
                                .createSourceFile(qualifiedName, element);
                try (Writer writer = file.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n");
                    }
                    writer.write("public final class " + generatedName + " {\n");
                    writer.write("  private " + generatedName + "() {}\n");
                    writer.write(
                            "  public static String message() {\n"
                            + "    return \"Generated for "
                            + element.getSimpleName() + "\";\n"
                            + "  }\n"
                    );
                    writer.write("}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualifiedName + ": "
                                + ex.getMessage(),
                        element
                );
            }
        }

        return true;
    }
}
~~~

Điểm kỹ thuật:

- `getElementsAnnotatedWith(GenerateGreeting.class)` tìm các khai báo được đánh dấu annotation.
- `ElementKind.CLASS` bảo đảm bài lab chỉ hỗ trợ class; annotation type được `@Target(TYPE)` cho phép đặt trên những dạng type khác nhưng processor **cố ý chặn** trong ví dụ này.
- `getPackageOf(...)` lấy package của khai báo.
- `Filer.createSourceFile(...)` tạo **một tệp source mới**, không thay đổi `App.java`.
- `Messager` phát lỗi compiler có định vị nếu không thể sinh file.
- `return true` cho compiler biết processor **claim** các annotation types được truyền vào cho round đó; không phải giá trị “đã sửa AST thành công”.
- Processor tạo source với tên `AppGreeting` khi xử lý class `App`. Trong hệ thống thực, cần thêm xử lý tên đặc biệt, duplicate, escaping và kiểm thử nhiều package trước khi công bố processor dùng chung. Đây là bài lab có chủ đích với tên class đơn giản.

### 5.3. Ứng dụng dùng mã được sinh

**Tệp `src/app/demo/App.java`:**

~~~java
package demo;

@GenerateGreeting
public final class App {
    public static void main(String[] args) {
        System.out.println(AppGreeting.message());
        System.out.println(
                App.class.isAnnotationPresent(GenerateGreeting.class)
        );
    }
}
~~~

`AppGreeting` **chưa tồn tại** trước khi processor chạy. Nếu chỉ compile `App.java` mà không chạy processor, dòng gọi `AppGreeting.message()` gây lỗi không tìm được symbol. Khi processor tạo source trong một round, compiler có thể biên dịch source được sinh trong cùng lần chạy `javac`.

### 5.4. Biên dịch và chạy trên Linux/macOS (Bash)

Từ root `annotation-lab`:

~~~bash
mkdir -p build/processor build/app build/generated
javac -encoding UTF-8 -d build/processor \
  src/annotation/demo/GenerateGreeting.java \
  src/processor/demo/GreetingProcessor.java
jar --create --file build/greeting-processor.jar -C build/processor .
javac -encoding UTF-8 \
  -cp build/greeting-processor.jar \
  -processorpath build/greeting-processor.jar \
  -processor demo.GreetingProcessor \
  -s build/generated -d build/app \
  src/app/demo/App.java
java -cp "build/app:build/greeting-processor.jar" demo.App
~~~

**Stdout chính xác** của ứng dụng:

~~~text
Generated for App
false
~~~

Tệp được sinh ra sẽ nằm tại `build/generated/demo/AppGreeting.java`, và `javac` tạo `build/app/demo/AppGreeting.class` cùng `App.class`. Bạn có thể mở file sinh để xem nội dung hoặc chạy `javap -classpath build/app demo.AppGreeting`.

Vì `@GenerateGreeting` có retention SOURCE, reflection runtime trong `App` trả `false`. Việc processor đã chạy và sinh code **không** làm retention chuyển thành RUNTIME.

### 5.5. Lệnh tương ứng trên Windows PowerShell

Tạo các file ở đúng layout trên rồi chạy trong root `annotation-lab`:

~~~powershell
New-Item -ItemType Directory -Force "build\processor", "build\app", "build\generated" | Out-Null
javac -encoding UTF-8 -d "build\processor" "src\annotation\demo\GenerateGreeting.java" "src\processor\demo\GreetingProcessor.java"
jar --create --file "build\greeting-processor.jar" -C "build\processor" .
javac -encoding UTF-8 -cp "build\greeting-processor.jar" -processorpath "build\greeting-processor.jar" -processor demo.GreetingProcessor -s "build\generated" -d "build\app" "src\app\demo\App.java"
java -cp "build\app;build\greeting-processor.jar" demo.App
~~~

Stdout:

~~~text
Generated for App
false
~~~

Windows dùng dấu `;` để nối entry runtime classpath. Trong lab, processor đã được **chỉ định tường minh** qua `-processor demo.GreetingProcessor`; vì vậy không cần tạo `META-INF/services` cho cơ chế autodiscovery.

### 5.6. Phân biệt các đường dẫn và tùy chọn

| Tùy chọn | Vai trò trong lab |
| --- | --- |
| `-d build/processor` | Gốc file `.class` của annotation và processor lúc build JAR |
| `-processorpath build/greeting-processor.jar` | Nơi `javac` tìm và nạp processor để thực thi trong build |
| `-processor demo.GreetingProcessor` | Yêu cầu chạy processor cụ thể, không lệ thuộc vào autodiscovery |
| `-cp build/greeting-processor.jar` | Cho compiler ứng dụng biết kiểu `demo.GenerateGreeting` |
| `-s build/generated` | Thư mục lưu `.java` được processor sinh |
| `-d build/app` | Thư mục lưu class file cuối của ứng dụng và các class sinh |
| `java -cp ... demo.App` | Runtime classpath và tên đầy đủ của main class |

**Processor path và compile classpath là hai vấn đề khác nhau.** Một processor có thể cần có mặt trên processor path để chạy, trong khi annotation/API mà mã ứng dụng import cần xuất hiện trên compile classpath. Trong dự án dùng build tool, dependency cấu hình riêng cho annotation processing thường an toàn hơn việc đưa mọi processor vào dependency runtime.

## 6. Reflection: đọc annotation khi chương trình đã chạy

Reflection không cần `Filer`, `RoundEnvironment` hay một compiler round. Nó làm việc với các class đã được JVM tải và metadata có sẵn ở runtime.

**Tệp độc lập `ReflectionDemo.java`:**

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

public final class ReflectionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    public @interface Label {
        String value();
    }

    @Label("runtime")
    static final class Task {
    }

    public static void main(String[] args) {
        Label label = Task.class.getAnnotation(Label.class);
        System.out.println(label.value());
        System.out.println(Task.class.isAnnotationPresent(Label.class));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 ReflectionDemo.java
java ReflectionDemo
~~~

**Stdout chính xác:**

~~~text
runtime
true
~~~

Vì `@Label` có `RUNTIME` retention, `Class.getAnnotation(Label.class)` trả thông tin annotation. Reflection đang đọc metadata của `Task.class`, **không sinh `TaskGenerated.java`, không thay AST và không chèn method vào `Task`**.

### Những API reflection thường gặp

- `Class.getDeclaredAnnotations()` trả annotation khai báo trực tiếp theo quy tắc API, khác với truy vấn có xét thừa kế `@Inherited`.
- `Class.getDeclaredFields()`, `getDeclaredMethods()`, `getDeclaredConstructors()` liệt kê thành viên đã biên dịch của class.
- `Method.invoke(receiver, args...)` gọi method reflectively khi quyền truy cập và các điều kiện runtime cho phép.
- `Class.forName("some.Type")` nạp/tìm class theo tên theo hành vi API; nó **không** khởi chạy một annotation processor để tạo source mới.

Reflection có thể phát hiện annotation để framework đưa ra quyết định, ví dụ đăng ký endpoint, tạo object hoặc ánh xạ dữ liệu. Nhưng logic ấy được **framework lập trình**, không tự đến từ annotation.

### Cùng một annotation có thể được dùng tại hai thời điểm

Một annotation `@Retention(RUNTIME)` có thể được processor kiểm tra khi compile **và** được reflection đọc khi chạy, nếu cả hai công cụ tồn tại và được cấu hình. Hai cơ chế không loại trừ nhau. Điểm khác biệt là **thời điểm, mô hình dữ liệu và tác dụng**, không phải chỉ tên annotation.

## 7. Biến đổi AST: thay cấu trúc code thay vì sinh một class mới

**AST** là mô hình cây của source code sau khi phân tích cú pháp. Ví dụ:

~~~java
public final class Person {
    private final String name;
}
~~~

Có thể minh họa một AST rất giản lược:

~~~text
ClassDecl Person
  Modifier public final
  FieldDecl name
    Modifier private final
    Type String
~~~

Một công cụ **AST transformation** có thể chèn constructor, getter hoặc method vào cây của class `Person` trước khi các pha compiler liên quan hoàn tất:

~~~text
ClassDecl Person
  FieldDecl name
  ConstructorDecl Person(String name)   <-- do transformer chèn
  MethodDecl getName(): String          <-- do transformer chèn
~~~

Đây là **sơ đồ**, không phải output từ một API AST chuẩn có thể dùng với mọi compiler. Điều cốt lõi là class **gốc** sau biến đổi có thêm thành viên khi sinh bytecode, dù file nguồn không chứa các thành viên đó dưới dạng văn bản.

### Vì sao JSR 269 thông thường không sửa được AST gốc?

`javax.lang.model.element.TypeElement` đại diện **khai báo/kiểu** cho việc quan sát và phân tích, chứ không phải node AST có phương thức `addMethod(...)`. `Filer` cung cấp cơ chế tạo **tệp mới** và không phải công cụ sửa một tệp nguồn đầu vào hiện hữu. JSR 269 không hứa hẹn quyền chỉnh sửa nội bộ parser/attribution của compiler.

Một processor có thể:
- Đọc khai báo `Person` và các trường được annotation.
- Tạo `PersonBuilder.java` hoặc `PersonMapper.java`.
- Phát compile error nếu `Person` thiếu điều kiện cần thiết.
- Tạo resource metadata để code runtime dùng.

Nó **không thể dựa hoàn toàn vào API JSR 269 chuẩn** để thêm method `getName()` trực tiếp vào kiểu `Person` mà compiler đang biên dịch.

### Compiler tree API và các extension

JDK có các API như `com.sun.source.tree` và `com.sun.source.util.Trees` để quan sát cây cú pháp của source khi compiler cung cấp. Việc **đọc** tree thông qua API được công bố không đồng nghĩa có một API chuẩn để **sửa tùy ý** node compiler rồi bảo đảm bytecode hợp lệ.

Các công cụ muốn sửa cây nội bộ `javac` đôi khi sử dụng `com.sun.tools.javac.*`, plugin đặc thù, internal hooks hoặc transformer riêng. Những chi tiết này có thể thay đổi giữa JDK, compiler, IDE và module boundaries. Một hệ thống dựa trên các API nội bộ có thể cần cấu hình truy cập module hoặc cập nhật thường xuyên khi đổi JDK.

Vì vậy hãy tách ba ý tưởng:

1. **Quan sát AST** (compiler tree inspection) để phân tích hoặc chẩn đoán.
2. **Tạo source khác** bằng JSR 269 (`Filer`): cơ chế chuẩn, dễ triển khai đa compiler hơn.
3. **Sửa AST đang được biên dịch**: can thiệp sâu vào pipeline compiler, mức độ hỗ trợ và tính di động tùy công cụ.

## 8. Vì sao Lombok dễ gây nhầm lẫn?

Các annotation kiểu `@Getter`, `@Setter` hoặc `@Builder` của Lombok thường làm developer thấy class như thể đã được thêm method/constructor mà source không viết ra. Lombok có cơ chế tích hợp với compiler và IDE để đạt hiệu ứng đó; ở nhiều môi trường `javac`, annotation processing là một **điểm kích hoạt**, nhưng thao tác biến đổi cấu trúc dùng **cơ chế/compiler internals ngoài các khả năng sinh tệp chuẩn của JSR 269**.

Không nên lập luận “Lombok dùng annotation processor nên mọi processor có thể thay đổi class gốc bằng `TypeElement`”. Processor thuần JSR 269 như ví dụ `GreetingProcessor` chỉ sinh `AppGreeting.java`; Lombok hướng tới thay đổi cách class gốc được compiler hiểu. Đây là hai mô hình **khác nhau**.

Những hệ quả thiết kế:

- Processor sinh class riêng có file `.java` để kiểm tra; codegen rõ ràng nhưng có thể cần gọi helper class.
- AST transformer có trải nghiệm source ngắn gọn hơn nhưng phụ thuộc sâu vào compiler/IDE.
- Khi nâng JDK, lỗi của AST transformer có thể khác với lỗi processor JSR 269 thuần.
- Tích hợp IDE cần hiểu/generated source hoặc plugin AST tương ứng. IDE báo không tìm thấy getter trong khi command-line compile được là một dấu hiệu cần kiểm tra IDE/plugin/config, không thể kết luận Java runtime reflection sẽ “tạo getter” lúc chạy.

## 9. Annotation processor không phải bytecode transformer

Có một nhóm kỹ thuật khác: **biến đổi bytecode sau khi class đã được biên dịch**, hoặc instrumentation khi class được nạp.

| Cơ chế | Đầu vào | Đầu ra/tác động |
| --- | --- | --- |
| JSR 269 | Mô hình source/element trong compile | Tệp source/class/resource **mới**, diagnostic |
| AST transform | Cây cú pháp/compiler model | Cây hoặc mã nguồn **được thay đổi** trước khi phát bytecode |
| Bytecode transform | Tệp `.class`/bytecode | Bytecode **được viết lại** hoặc biến đổi trước khi thực thi |
| Runtime reflection | Class và metadata đã tải | Quan sát/call/access tại runtime, không tự sửa bytecode |

Thư viện xử lý bytecode có thể dùng ASM hoặc các cơ chế khác để sửa instruction, field, method hay attributes trên bytecode. Java agents có thể instrumentation ở lúc class loading, với các ràng buộc riêng về thời điểm và loại thay đổi cho phép. **Reflection không tương đương instrumentation**, và annotation processor không mặc định là Java agent.

Thứ tự pipeline khái quát:

~~~text
.java
  |
  +--> Parser / compiler AST
  |          |
  |          +--> JSR 269 processor: xem model, sinh tệp mới
  |          |
  |          +--> compiler extension: có thể thao tác AST
  |
  v
.class
  |
  +--> bytecode transformer / agent (nếu có)
  |
  v
JVM tải/liên kết/thực thi class
  |
  +--> runtime reflection: đọc metadata và thành viên đã có
~~~

Sơ đồ là cách **phân biệt chức năng**, không bảo đảm thứ tự chính xác giữa mọi phase trong `javac` hay mọi transformer; một số framework kết hợp nhiều kỹ thuật.

## 10. Filer, generated source và compiler rounds: các quy tắc cần nhớ

### Không viết đè mã nguồn đầu vào

Processor nên sinh tệp **mới, xác định rõ tên đầy đủ và package**. `Filer` quản lý những file được tạo ra trong processing environment; cố gắng tạo trùng path trong một lần processing hoặc trùng tệp đầu vào có thể dẫn đến `FilerException`/diagnostic. Không cố lấy `Writer` của `TypeElement` và viết đè file `App.java`: không có API JSR 269 chuẩn như vậy.

### Một processor có thể làm nhiệm vụ kiểm tra

Không phải processor nào cũng sinh file. Processor xác minh annotation đặt đúng loại khai báo, tên database column có hợp lệ, hoặc điều kiện API cần tuân thủ có thể gọi:

~~~java
processingEnv.getMessager().printMessage(
        javax.tools.Diagnostic.Kind.ERROR,
        "Unsupported annotation usage",
        element
);
~~~

Đây là **đoạn trong thân `Processor.process`**, không chạy độc lập; biến `element` là một `Element` của processor. Compiler sẽ báo lỗi có vị trí khi có thể, từ đó chặn build. Không cần reflection hay AST mutation để xác minh metadata ở compile-time.

### Round, annotation type và claim

Processor có thể nhận các annotation types cần xét trong mỗi round, sinh source làm phát sinh round tiếp theo, và được gọi trong round cuối với `processingOver() = true`. Một processor nên xử lý vòng cuối, idempotency và khả năng đầu vào sai một cách có chủ đích. `process(...)` trả `true` nghĩa là claim những annotation types mà nó xử lý; **không** phải “còn dữ liệu sinh” hay “compile thành công”.

Trong ví dụ `GreetingProcessor`, chỉ class `App` có `@GenerateGreeting`; class mới sinh không mang annotation nên không tự kích hoạt vòng sinh vô hạn.

### Kết quả build cần tái lập

Khi processor tạo tên file phụ thuộc timestamp, random, thứ tự phần tử không ổn định hoặc trạng thái máy build, output có thể khác giữa hai lần build cùng source. Để tạo build đáng tin, hãy:
- Dựa trên input khai báo được compiler cung cấp.
- Sắp xếp phần tử khi thứ tự ảnh hưởng nội dung file.
- Dùng đường dẫn/encoding ổn định và tránh phụ thuộc working directory khi không cần.
- Không phát sinh thêm file không liên quan.
- Kiểm tra processor trong incremental build/clean build theo công cụ build đang dùng.

Processor là **mã chạy trong build**, nên thư viện processor không đáng tin có thể thực thi thao tác với môi trường build. Chọn dependency và version cẩn thận; không xem annotation processor như metadata tĩnh vô hại.

## 11. Cấu hình processor: explicit discovery và build tools

Ví dụ đã dùng:

~~~bash
javac -cp build/greeting-processor.jar \
  -processorpath build/greeting-processor.jar \
  -processor demo.GreetingProcessor \
  -s build/generated -d build/app \
  src/app/demo/App.java
~~~

Các chế độ đáng biết:

- `-processor fully.qualified.Processor`: chọn processor theo tên; tiện cho lab và build có yêu cầu rõ.
- `-processorpath path`: nơi compiler tìm processor được chạy. Nếu không cấu hình, một số phiên bản/cấu hình `javac` có cách tìm processor mặc định khác nhau; không dựa vào discovery ngầm để tái lập build.
- `META-INF/services/javax.annotation.processing.Processor`: cơ chế `ServiceLoader` để công bố processor cho discovery ở những môi trường cho phép. File chứa tên đầy đủ của processor, ví dụ `demo.GreetingProcessor`.
- `-s dir`: nơi compiler ghi source được sinh; hữu ích cho debug.
- `-proc:only`: yêu cầu chỉ chạy processing, không tạo các file class như lần biên dịch thông thường. Đừng dùng nếu mục tiêu là chạy ngay ứng dụng mà không compile tiếp.
- `-proc:none`: vô hiệu hóa annotation processing, hữu ích khi chẩn đoán khác biệt giữa source thuần và bước codegen.
- `-Akey=value`: truyền option do processor hỗ trợ; processor đọc qua `ProcessingEnvironment.getOptions()`.

Những phiên bản JDK có thể thay đổi mặc định discovery vì lý do bảo mật/tính rõ ràng của build; do đó một bài lab dùng `-processor` **tường minh** cho kết quả dễ dự đoán hơn. Với ứng dụng thật, Maven/Gradle và IDE nên có annotation processor configuration thống nhất với build CI.

**Lưu ý:** Nếu tắt processing trong lab, `App.java` tham chiếu `AppGreeting` sẽ không biên dịch nếu không có class/source đã được sinh sẵn. Xóa output sinh từ các lượt trước khi kiểm chứng để tránh tình huống class cũ làm tưởng rằng processor vẫn đang chạy.

## 12. Reflection và quyền truy cập không tạo quyền sửa kiểu

Reflection thường được dùng để đọc các annotation runtime, liệt kê field/method và có thể truy cập/gọi thành viên theo Java access checks, module boundaries và policy runtime tương ứng. Nhưng điều đó không có nghĩa:

- Có thể gọi `Class.addMethod(...)`; **không tồn tại** API reflection chuẩn như vậy.
- `Method.invoke(...)` tự thêm một method vào class. Nó chỉ gọi method **đã tồn tại**.
- Annotation `@Retention(RUNTIME)` tự phát sinh hành vi. Cần có code runtime thực sự đọc và xử lý nó.
- `setAccessible(true)` bảo đảm bỏ qua mọi giới hạn module Java. Trên Java 9+ strong encapsulation có thể chặn deep reflection nếu package chưa được mở theo cách hợp lệ.

Một framework dùng reflection có thể xây object proxy hoặc phát triển một lớp khác bằng bytecode generation. Khi đó **proxy/bytecode generation** là cơ chế bổ sung, không phải reflection tự sửa class ban đầu.

## 13. Tình huống chọn cơ chế phù hợp

### Sinh mapper/builder theo schema ở compile-time

Muốn sinh `UserMapperImpl` dựa trên annotation và khai báo interface, không cần sửa interface gốc: **JSR 269 processor** thường phù hợp. Sinh source rõ ràng, kiểm tra lỗi kiểu trong build, không cần reflection ở mỗi request runtime.

### Kiểm tra quy tắc annotation

Muốn phát lỗi nếu `@Route` đặt trên class không public hoặc method có tham số không hợp lệ: **annotation processor** và `Messager` phù hợp. Không cần runtime để phát hiện những sai sót tĩnh có thể kiểm tra.

### Framework phát hiện endpoint lúc ứng dụng khởi động

Muốn tìm các method có `@Route` và đăng ký handler khi chạy: dùng **RUNTIME annotation + reflection/scanning**, hoặc metadata/index được codegen sẵn để giảm runtime scan. Annotation retention và cơ chế đọc phải phù hợp với thiết kế.

### Tự động thêm getter vào chính class gốc

Muốn biến `class User { private String name; }` thành một class có method `getName()` mà source không khai báo method: **JSR 269 thuần không cung cấp thao tác này**. Cần phương án khác như sửa source/template, generated subclass/helper, compiler AST extension hoặc tool như Lombok với tích hợp riêng.

### Công cụ thay đổi instruction bytecode

Muốn thêm log vào method đã biên dịch hoặc instrumentation khi class load: xem **bytecode transformer/Java agent**. Đây không phải annotation processor hay reflection theo nghĩa chuẩn, dù công cụ có thể quyết định thay đổi dựa vào annotation.

## 14. Những lỗi/nhầm lẫn thường gặp

| Triệu chứng hoặc nhận định | Nguyên nhân/điểm cần phân biệt |
| --- | --- |
| `cannot find symbol: AppGreeting` | Processor chưa chạy, thất bại, sinh khác package/name hoặc generated source không được compile |
| Annotation SOURCE không xuất hiện trong reflection | **Đúng kỳ vọng**, vì retention SOURCE loại bỏ metadata annotation khỏi class file |
| `getAnnotation(...)` trả `null` | Không có annotation runtime phù hợp; kiểm tra `@Retention(RUNTIME)`, khai báo thực tế, `@Inherited` và truy vấn declared/inherited |
| Processor được nạp nhưng không sinh gì | Không có phần tử annotated phù hợp, annotation type name sai hoặc processor/round trả kết quả không như dự kiến |
| `FilerException` do file trùng | Một file được tạo lặp trong cùng processing environment hoặc trùng input; kiểm tra round và tên output |
| IDE không nhận class được sinh | Chưa bật/cấu hình annotation processing hoặc generated sources chưa nằm trong model IDE |
| Chạy được nhưng generated code cũ | Artifact cũ chưa clean; build tool incremental cache chưa cập nhật đúng |
| Processor “không thêm getter vào class gốc” | JSR 269 không cung cấp quyền biến đổi AST đó |
| Lombok lỗi khi nâng JDK | Có thể do phụ thuộc vào compiler/IDE integration khác nhau; kiểm tra phiên bản hỗ trợ, không suy luận do reflection |
| Runtime có annotation nhưng không có tác dụng | Chưa có framework/code đọc metadata và thực hiện hành vi |
| Reflection không truy cập được member | Java accessibility và module encapsulation giới hạn việc đọc/call |
| Có `AppGreeting.java` nhưng thiếu `AppGreeting.class` | Đã chỉ chạy processing `-proc:only` hoặc bước compile generated sources chưa diễn ra |

### Checklist ngắn để điều tra

1. Annotation type có đúng package, `@Target` và retention phù hợp không?
2. Compiler đang chạy JDK nào? Annotation processor có được chọn bởi `-processor` hoặc discovery hợp lệ không?
3. Processor có nằm trên processor path, annotation type có trong compile classpath không?
4. `-s` có sinh file nào không? `Filer` có báo trùng hay lỗi IO không?
5. Generated source đã được compiler biên dịch và runtime classpath có chứa output cần thiết chưa?
6. Nếu cần runtime reflection, annotation thực sự là `RUNTIME` và query đang kiểm tra đúng `Class`/`Method`/`Field` không?
7. Nếu muốn sửa method/field của class hiện hữu, bạn có đang dùng nhầm JSR 269 cho công việc của AST transformer hoặc bytecode tool không?
8. Nếu có plugin/compiler internals, JDK và IDE hiện tại có được công cụ đó hỗ trợ không?

## 15. Bài tập tự kiểm tra có đáp án

**Bài 1.** `@Check` có `RetentionPolicy.SOURCE`. Một processor `javac` có thể đọc annotation ấy không? Runtime reflection có đọc được không?

**Đáp án:** Processor có thể đọc nó trong mô hình biên dịch. Runtime reflection chuẩn không thấy annotation SOURCE trên class đã biên dịch.

**Bài 2.** Processor dùng `Filer.createSourceFile("demo.UserBuilder")`. Nó đã thêm method trực tiếp vào `demo.User` chưa?

**Đáp án:** Chưa. Nó tạo file source của một type khác (`demo.UserBuilder`). Muốn thay đổi trực tiếp nội dung class gốc cần cách khác ngoài quyền của Filer chuẩn.

**Bài 3.** `@Label` có `RetentionPolicy.RUNTIME` và một method `getAnnotation(Label.class)` trả annotation đúng. Điều này chứng minh `javac` đã chạy một processor để sinh code không?

**Đáp án:** Không. Reflection đọc metadata runtime; việc annotation tồn tại không chứng minh có processor nào chạy.

**Bài 4.** Một tool thêm getter vào AST đang được `javac` xử lý. Có thể nói tool ấy chỉ dùng `javax.lang.model.element.TypeElement` và `Filer` chuẩn không?

**Đáp án:** Không. JSR 269 chuẩn có model khai báo và cơ chế sinh file, không có API chỉnh sửa AST class gốc. Tool có thể dùng extension/compiler internals.

**Bài 5.** Vì sao trong lab `App.class.isAnnotationPresent(GenerateGreeting.class)` in `false` dù có `AppGreeting.class`?

**Đáp án:** `@GenerateGreeting` có SOURCE retention nên không được giữ lại để reflection thấy. Generated class là sản phẩm của processing ở build-time, hai việc độc lập.

**Bài 6.** `-processorpath` đã trỏ đúng JAR processor, nhưng compiler không tìm thấy `@GenerateGreeting` khi compile `App.java`. Cần kiểm tra gì?

**Đáp án:** Compile classpath hoặc module path chứa annotation type được source import, package/name, và sự hiện diện file class/source tương ứng. Processor path không tự thay thế compile classpath cho mọi kiểu của ứng dụng.

**Bài 7.** Tại sao không nên dùng compiler AST internals chỉ để sinh một helper class?

**Đáp án:** Khi JSR 269 và Filer đã đáp ứng, dùng API chuẩn thường dễ tái lập và ít phụ thuộc compiler hơn. Internal AST mutation tăng chi phí tương thích JDK, IDE và module boundaries.

## Ghi nhớ

- **Annotation không tự chạy**; hành vi đến từ công cụ đọc annotation.
- **JSR 269** là xử lý **trong compile**, quan sát `Element`/`TypeMirror`, phát diagnostic và sinh tệp mới qua `Filer`; nó không được chuẩn hóa để sửa AST của class gốc.
- **Reflection** là truy vấn/call **ở runtime** trên class đã nạp; muốn đọc annotation thì cần **RUNTIME retention** và code runtime thực sự xử lý metadata.
- **AST transformation** có thể thay đổi cấu trúc class đang compile, nhưng là cơ chế khác và thường phụ thuộc compiler/tool; một số hệ thống như Lombok kết hợp annotation processing với compiler-specific integration.
- **Bytecode transformation** tác động lên class sau biên dịch hoặc lúc tải, không đồng nghĩa với reflection hay JSR 269.
- Muốn build ổn định, hãy xác định processor path, compile classpath, generated source path, compiler rounds và retention đúng mục đích. Chọn công cụ theo **tác động cần đạt**, không chọn chỉ vì tất cả cùng dùng cú pháp `@Annotation`.
