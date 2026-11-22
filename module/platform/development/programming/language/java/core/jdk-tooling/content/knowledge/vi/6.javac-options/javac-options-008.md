# Pha xử lý annotation trong javac

Annotation Processing là giai đoạn xử lý annotation tại thời điểm biên dịch. Trình biên dịch **javac** có thể nạp các annotation processor để đọc thông tin về package, lớp, phương thức, trường và annotation trong mã nguồn, sau đó kiểm tra quy tắc hoặc tạo thêm mã nguồn, class và tài nguyên.

Pha này được dùng rộng rãi trong thư viện và framework Java. Ví dụ: Lombok hỗ trợ sinh mã cho một số cấu trúc Java; MapStruct sinh mapper; Dagger sinh mã phục vụ dependency injection; các processor khác có thể tạo metadata, registry, adapter hoặc kiểm tra quy ước API.

Annotation processing diễn ra khi build, trước khi ứng dụng chạy. Nó không phải cơ chế reflection lúc runtime. Processor chạy trong tiến trình biên dịch và làm việc với mô hình chương trình mà compiler cung cấp.

## 1. Annotation Processing nằm ở đâu trong quá trình biên dịch?

Một lượt biên dịch có thể hình dung theo các bước chính:

1. **Đọc và phân tích cú pháp:** javac đọc các tệp nguồn, phân tích package, import, khai báo kiểu và cú pháp Java.
2. **Thiết lập mô hình khai báo:** compiler xác định các phần tử gốc và thông tin kiểu cần thiết để processor có thể truy vấn.
3. **Annotation processing:** javac tìm processor được cấu hình, xác định annotation phù hợp và gọi processor theo từng round.
4. **Phân tích và kiểm tra kiểu:** compiler kiểm tra kiểu, quyền truy cập, overload, generic và các quy tắc ngôn ngữ trên tập nguồn cuối cùng.
5. **Sinh bytecode:** nếu không dùng chế độ chỉ xử lý annotation, javac tạo các tệp .class cho mã nguồn ban đầu và mã nguồn được sinh ra.

Đây là mô hình khái niệm để hiểu vai trò của pha xử lý. Chi tiết nội bộ của javac có thể phức tạp hơn, đặc biệt khi có nhiều module hoặc annotation processor sinh thêm nguồn.

Processor thường không thao tác trực tiếp trên bytecode đã biên dịch. Nó đọc mô hình ngôn ngữ thông qua API như Element, TypeMirror, Elements và Types, sau đó tạo nguồn hoặc tài nguyên thông qua Filer.

## 2. Vòng xử lý annotation (processing rounds)

Annotation processing hoạt động theo các vòng (rounds). Một round nhận tập nguồn ban đầu hoặc các nguồn được sinh ra từ round trước.

Quy trình tổng quát:

~~~text
Nguồn Java ban đầu
       |
       v
Round 1: tìm annotation và gọi processor
       |
       +---- processor không sinh nguồn mới
       |             |
       |             v
       |       Round cuối (processingOver)
       |
       +---- processor sinh nguồn mới
                     |
                     v
              javac đọc nguồn mới
                     |
                     v
              Round 2, Round 3, ...
                     |
                     v
              Không còn nguồn mới
                     |
                     v
                Round cuối
                     |
                     v
          Phân tích và sinh class files
~~~

Trong mỗi round:

- RoundEnvironment cung cấp các phần tử gốc và những phần tử mang annotation cần xử lý.
- Processor có thể đọc cấu trúc khai báo, kiểm tra điều kiện và tạo nguồn mới.
- Nguồn Java mới được đưa vào các round tiếp theo để compiler tiếp tục xử lý.
- Processor đã được gọi trong một lượt biên dịch có thể tiếp tục được gọi ở các round sau, kể cả round cuối.
- Khi roundEnv.processingOver() trả về true, processor biết không còn round xử lý thông thường nào tiếp theo.

Round cuối là cơ hội để hoàn tất công việc tổng hợp dựa trên các round trước. Không nên tạo thêm source file ở round cuối vì không còn round tiếp theo để compiler xử lý nguồn đó.

Một processor thường kiểm tra processingOver() ở đầu phương thức process để tránh lặp lại việc sinh file trong round cuối.

## 3. Processor API và vai trò của các thành phần

Các API chính nằm trong hai package:

- javax.annotation.processing: giao diện processor, môi trường xử lý, round, Filer và Messager.
- javax.lang.model: mô hình biểu diễn element, type, package, module và tiện ích truy vấn kiểu.

Các thành phần thường gặp:

| API | Vai trò |
|---|---|
| Processor | Hợp đồng mà annotation processor phải triển khai |
| AbstractProcessor | Lớp cơ sở giúp giảm phần mã phải tự cài đặt |
| ProcessingEnvironment | Cung cấp Filer, Messager, Elements, Types và options |
| RoundEnvironment | Cung cấp phần tử và trạng thái của round hiện tại |
| Element | Biểu diễn khai báo như class, method, field, package |
| TypeElement | Biểu diễn khai báo kiểu như class hoặc interface |
| ExecutableElement | Biểu diễn method hoặc constructor |
| VariableElement | Biểu diễn field, parameter hoặc biến cục bộ trong mô hình |
| TypeMirror | Biểu diễn kiểu Java trong compiler model |
| Elements | Tiện ích truy vấn khai báo và package |
| Types | Tiện ích so sánh, kiểm tra và thao tác trên kiểu |
| Filer | Tạo source file, class file và resource |
| Messager | Gửi NOTE, WARNING hoặc ERROR về compiler output |

### AbstractProcessor

Phần lớn processor thực tế kế thừa AbstractProcessor thay vì tự cài đặt toàn bộ Processor.

Các phương thức thường được khai báo bằng annotation:

- @SupportedAnnotationTypes: những annotation mà processor nhận xử lý.
- @SupportedSourceVersion: phiên bản ngôn ngữ Java mà processor hỗ trợ.
- @SupportedOptions: các tùy chọn riêng mà processor chấp nhận qua javac -A.

Processor cũng có thể ghi đè các phương thức tương ứng nếu cần cấu hình động.

### process

Phương thức cốt lõi:

~~~java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv
)
~~~

- annotations là tập annotation interface được yêu cầu xử lý trong round hiện tại.
- roundEnv cung cấp các phần tử mang annotation, các phần tử gốc và trạng thái round.
- Giá trị trả về cho biết processor có nhận xử lý (claim) các annotation interface được truyền vào hay không.

Nếu trả về true, processor tuyên bố đã xử lý các annotation interface trong tập được truyền vào, và các processor sau không tiếp tục nhận những annotation đã được claim đó trong round. Nếu trả về false, processor không claim chúng, cho phép processor khác có cơ hội xử lý.

Một processor tổng quát hỗ trợ annotation "*" cần cẩn thận với giá trị trả về. Nếu không có ý định chặn các processor khác, hãy trả về false.

## 4. Cách javac tìm và nạp processor

Processor là mã Java được biên dịch thành class và thường được đóng gói trong JAR. Nó chạy trong môi trường thực thi của compiler, nên cần phân biệt:

- **Compile classpath:** nơi javac tìm class mà mã nguồn đang biên dịch tham chiếu tới.
- **Processor path:** nơi javac tìm class của annotation processor và dependency mà processor cần khi chạy.
- **Processor module path:** nơi tìm processor được đóng gói dưới dạng module.

Các tùy chọn quan trọng:

| Tùy chọn | Ý nghĩa |
|---|---|
| -processorpath hoặc --processor-path | Đường dẫn chứa processor và dependency của processor |
| --processor-module-path | Module path dành cho processor |
| -processor | Chỉ định tên class processor cần chạy |
| -proc:none | Tắt annotation processing |
| -proc:only | Chỉ chạy annotation processing, không thực hiện bước biên dịch class tiếp theo |
| -proc:full | Thực hiện annotation processing và biên dịch |
| -Akey=value | Truyền option riêng cho processor |

Ví dụ chỉ định processor rõ ràng:

~~~bash
javac \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -d build/classes \
    src/app/demo/app/App.java
~~~

Nếu processor phụ thuộc annotation type hoặc thư viện mà mã nguồn ứng dụng cũng cần dùng, hãy đặt dependency tương ứng trên compile classpath. Processor path và compile classpath có mục đích khác nhau, dù một số dự án có thể dùng cùng một thư mục cho cả hai.

### Tự động phát hiện qua Service Provider

Một processor có thể được phát hiện tự động bằng Java Service Provider mechanism. Trong JAR của processor, tạo file:

META-INF/services/javax.annotation.processing.Processor

Nội dung file là tên đầy đủ của processor, mỗi dòng một tên:

~~~text
demo.processor.GenerateGreetingProcessor
~~~

Khi javac được cấu hình để chạy annotation processing và tìm thấy JAR có service descriptor này trên processor path, compiler có thể phát hiện processor mà không cần ghi tên class trong -processor.

Nếu chỉ có processor class nhưng thiếu service descriptor và không chỉ định -processor, javac có thể không tìm thấy processor khi dùng cơ chế tự động discovery.

### Thay đổi từ JDK 23

Từ JDK 23, javac không còn mặc định tự chạy mọi processor được tìm thấy trên classpath chỉ vì chúng có mặt ở đó. Annotation processing cần được yêu cầu rõ ràng, chẳng hạn bằng -processor, --processor-path, --processor-module-path, -proc:full hoặc -proc:only.

Trong JDK 17, javac có hành vi mặc định cũ: khi tìm thấy processor trên classpath, compiler có thể chạy annotation processing mà không cần cấu hình tường minh như trên. Vì vậy, build cũ có thể hoạt động trên JDK 17 nhưng dừng sinh mã sau khi nâng JDK nếu dựa vào discovery ngầm.

Để build ổn định qua nhiều phiên bản, hãy cấu hình processor path và processor class/service rõ ràng trong build tool hoặc lệnh javac. Không dựa vào việc một dependency tình cờ xuất hiện trên compile classpath.

## 5. Tạo đầu ra bằng Filer

Processor không nên tự ghi file vào thư mục src hoặc thao tác filesystem tùy tiện. API Filer giúp compiler quản lý các file được tạo ra trong quá trình annotation processing.

Các phương thức thường dùng:

- createSourceFile(...): tạo tệp nguồn Java.
- createClassFile(...): tạo tệp class.
- createResource(...): tạo resource trong một location như SOURCE_OUTPUT hoặc CLASS_OUTPUT.

Đường dẫn đầu ra có thể cấu hình bằng các tùy chọn javac:

| Tùy chọn | Đầu ra |
|---|---|
| -s directory | Thư mục chứa source file do processor sinh ra |
| -d directory | Thư mục chứa class file |
| -Akey=value | Giá trị option mà processor đọc qua ProcessingEnvironment.getOptions() |

Ví dụ:

~~~bash
javac \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/app/demo/app/App.java
~~~

Trong ví dụ này, source được processor sinh ra đi vào build/generated-sources; các class được biên dịch đi vào build/classes.

Nếu processor sinh resource, cần chỉ định đúng location và package path khi gọi Filer.createResource. Build tool cũng cần biết resource được tạo ở đâu để đưa vào output hoặc artifact đóng gói.

Filer theo dõi những file được tạo trong một lượt biên dịch. Không tạo lại cùng một tên file ở nhiều round; điều đó có thể dẫn đến FilerException do file đã tồn tại.

## 6. Gửi thông báo bằng Messager

Processor nên báo lỗi gắn với element cụ thể thay vì ném exception chung chung hoặc chỉ in ra console.

Ví dụ:

~~~java
processingEnv.getMessager().printMessage(
    Diagnostic.Kind.ERROR,
    "Tên khai báo không hợp lệ",
    element
);
~~~

Các loại thông báo chính:

- NOTE: thông tin phục vụ người phát triển.
- WARNING: cảnh báo, nhưng không nhất thiết làm compilation thất bại.
- MANDATORY_WARNING: cảnh báo bắt buộc hiển thị theo quy tắc compiler.
- ERROR: lỗi khiến compilation thất bại.

Có thể gắn thông báo vào Element, AnnotationMirror hoặc một member cụ thể để IDE và compiler chỉ ra vị trí trong mã nguồn.

Không nên dùng System.out.println làm kênh thông báo chính. Messager tích hợp với diagnostic của compiler, hỗ trợ định vị lỗi và cho build tool biết compilation có lỗi hay không.

## 7. Đọc option riêng của processor

Tùy chọn bắt đầu bằng -A được javac chuyển cho processor. Ví dụ:

~~~bash
javac \
    -Aapp.generatedPackage=demo.generated \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -d build/classes \
    src/app/demo/app/App.java
~~~

Trong processor, đọc giá trị bằng:

~~~java
String generatedPackage =
        processingEnv.getOptions().get("app.generatedPackage");
~~~

Để công bố option được hỗ trợ, có thể dùng:

~~~java
@SupportedOptions("app.generatedPackage")
~~~

Nếu option bắt buộc bị thiếu hoặc giá trị không hợp lệ, processor nên báo lỗi bằng Messager. Không âm thầm dùng một giá trị khác nếu điều đó có thể tạo mã nguồn sai hoặc không nhất quán.

Có thể khai báo nhiều option trong annotation:

~~~java
@SupportedOptions({
    "app.generatedPackage",
    "app.generatedClassName"
})
~~~

Giữ tên option có namespace như app. hoặc tên dự án để giảm khả năng trùng với option của processor khác.

## 8. Ví dụ hoàn chỉnh: tạo mã nguồn bằng annotation processor

Ví dụ sử dụng Java 17+ và javac. Một annotation @GenerateGreeting đánh dấu class. Processor đọc class đó và sinh thêm một class có phương thức message().

Cấu trúc dự án:

~~~text
annotation-demo/
├── src/
│   ├── processor/
│   │   └── demo/
│   │       ├── GenerateGreeting.java
│   │       └── processor/
│   │           └── GenerateGreetingProcessor.java
│   └── app/
│       └── demo/
│           └── app/
│               └── App.java
└── build/
~~~

### Bước 1: định nghĩa annotation

Tạo src/processor/demo/GenerateGreeting.java:

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

RetentionPolicy.SOURCE nghĩa là annotation chỉ cần có trong mã nguồn lúc compile; nó không được giữ trong class file để ứng dụng đọc bằng reflection khi runtime.

ElementType.TYPE giới hạn annotation này cho khai báo kiểu như class, interface, enum hoặc record. Processor trong ví dụ chỉ chấp nhận class thông thường.

### Bước 2: viết processor

Tạo src/processor/demo/processor/GenerateGreetingProcessor.java:

~~~java
package demo.processor;

import demo.GenerateGreeting;

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
public final class GenerateGreetingProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateGreeting chỉ áp dụng cho class",
                        element);
                continue;
            }

            TypeElement typeElement = (TypeElement) element;
            String generatedName =
                    typeElement.getSimpleName() + "Generated";
            String qualifiedName =
                    "demo.generated." + generatedName;

            try {
                JavaFileObject sourceFile =
                        processingEnv.getFiler()
                                .createSourceFile(qualifiedName, element);

                try (Writer writer = sourceFile.openWriter()) {
                    writer.write(
                            "package demo.generated;\n\n"
                            + "public final class " + generatedName + " {\n"
                            + "    private " + generatedName + "() {}\n"
                            + "    public static String message() {\n"
                            + "        return \"Generated by annotation processing\";\n"
                            + "    }\n"
                            + "}\n");
                }

                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.NOTE,
                        "Generated " + qualifiedName,
                        element);

            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualifiedName + ": "
                                + e.getMessage(),
                        element);
            }
        }

        return true;
    }
}
~~~

Processor này:

1. Công bố annotation mà nó hỗ trợ.
2. Khai báo mức source version 17.
3. Nhận các element có annotation @GenerateGreeting.
4. Kiểm tra element là class.
5. Dùng Filer.createSourceFile để sinh class mới.
6. Dùng Messager để thông báo kết quả cho compiler.
7. Trả về true để claim annotation mà processor xử lý.

Processor không dùng reflection để phân tích class đang được compile. Nó dùng Element và TypeElement do compiler cung cấp, phù hợp với mã nguồn chưa có bytecode.

### Bước 3: viết ứng dụng sử dụng annotation

Tạo src/app/demo/app/App.java:

~~~java
package demo.app;

import demo.GenerateGreeting;

@GenerateGreeting
public class App {

    public static void main(String[] args) {
        System.out.println(
                demo.generated.AppGenerated.message());
    }
}
~~~

Lớp AppGenerated chưa tồn tại trong source ban đầu. Nó sẽ được processor tạo ra trong quá trình compile.

### Bước 4: biên dịch annotation và processor

Tạo thư mục đầu ra:

~~~bash
mkdir -p build/processor-classes
~~~

Biên dịch annotation cùng processor:

~~~bash
javac --release 17 \
    -d build/processor-classes \
    src/processor/demo/GenerateGreeting.java \
    src/processor/demo/processor/GenerateGreetingProcessor.java
~~~

Sau bước này, thư mục build/processor-classes chứa:

~~~text
build/processor-classes/
└── demo/
    ├── GenerateGreeting.class
    └── processor/
        └── GenerateGreetingProcessor.class
~~~

### Bước 5: chạy annotation processing khi biên dịch ứng dụng

Tạo các thư mục đầu ra:

~~~bash
mkdir -p build/classes build/generated-sources
~~~

Biên dịch ứng dụng và chỉ định processor rõ ràng:

~~~bash
javac --release 17 \
    -cp build/processor-classes \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/app/demo/app/App.java
~~~

Giải thích:

- -cp build/processor-classes: giúp compiler tìm annotation demo.GenerateGreeting mà App sử dụng.
- -processorpath build/processor-classes: giúp javac nạp processor và dependency khi chạy processor.
- -processor demo.processor.GenerateGreetingProcessor: chỉ định processor cần chạy.
- -s build/generated-sources: nơi ghi source được sinh ra.
- -d build/classes: nơi ghi bytecode đã biên dịch.

Vì processor được chỉ định rõ, lệnh này không phụ thuộc vào discovery ngầm từ compile classpath và phù hợp với thay đổi mặc định từ JDK 23.

### Bước 6: kiểm tra đầu ra

Sau khi compile, các tệp chính có dạng:

~~~text
build/
├── processor-classes/
│   └── demo/
│       ├── GenerateGreeting.class
│       └── processor/
│           └── GenerateGreetingProcessor.class
├── generated-sources/
│   └── demo/
│       └── generated/
│           └── AppGenerated.java
└── classes/
    ├── demo/
    │   ├── app/
    │   │   └── App.class
    │   └── generated/
    │       └── AppGenerated.class
~~~

AppGenerated.java được sinh trong round đầu. Javac đọc nguồn mới ở round tiếp theo, sau đó biên dịch nó thành AppGenerated.class.

Chạy ứng dụng:

~~~bash
java -cp build/classes demo.app.App
~~~

Output:

~~~text
Generated by annotation processing
~~~

Ứng dụng chỉ cần class output; annotation có retention SOURCE và processor chỉ cần trong compile time. Vì vậy không cần đưa build/processor-classes vào runtime classpath của ví dụ này.

## 9. Chế độ annotation processing của javac

Các chế độ thường dùng:

~~~bash
javac -proc:none -d build/classes src/demo/App.java
~~~

Tắt annotation processing. Mã nguồn vẫn được biên dịch bình thường, nhưng processor không được gọi.

~~~bash
javac -proc:only \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -s build/generated-sources \
    -d build/classes \
    src/demo/App.java
~~~

Chỉ chạy annotation processing. Chế độ này hữu ích khi muốn kiểm tra nguồn sinh ra riêng, nhưng không thực hiện bước compile class cuối cùng như chế độ đầy đủ.

~~~bash
javac -proc:full \
    -processorpath build/processor-classes \
    -processor demo.processor.GenerateGreetingProcessor \
    -d build/classes \
    src/demo/App.java
~~~

Thực hiện annotation processing và biên dịch. Khi có cấu hình processor tường minh, javac có thể bật xử lý theo mặc định; -proc:full giúp biểu đạt rõ ý định trong script.

Chế độ mặc định thay đổi theo phiên bản JDK. Từ JDK 23, nếu không có cấu hình annotation processing tường minh thì javac không tự chạy processor chỉ vì processor nằm trên classpath. Khi build cần sinh mã, hãy cấu hình processor path hoặc processor class và kiểm tra hành vi với JDK mục tiêu.

## 10. Tích hợp processor vào build tool

Trong dự án thực tế, không nên yêu cầu developer nhớ các lệnh javac dài. Build tool có cơ chế riêng để phân tách dependency biên dịch và processor.

### Gradle

Với Java plugin, dependency của annotation processor được khai báo riêng:

~~~groovy
dependencies {
    compileOnly "com.example:my-annotations:1.0"
    annotationProcessor "com.example:my-processor:1.0"
}
~~~

- compileOnly cung cấp annotation type trong quá trình biên dịch nếu ứng dụng cần import nó.
- annotationProcessor cung cấp processor và dependency cần thiết để processor chạy lúc compile.

Nếu annotation và processor nằm chung một artifact, có thể cần khai báo dependency phù hợp theo cách đóng gói của thư viện. Tránh đưa processor vào runtime classpath của ứng dụng nếu ứng dụng không cần dùng nó lúc chạy.

### Maven

Với Maven Compiler Plugin, processor có thể được cấu hình trong annotationProcessorPaths hoặc theo cấu hình processor tương ứng của phiên bản plugin đang dùng. Cấu hình chính xác phụ thuộc version của plugin và cách dự án quản lý dependency.

Khi chuyển JDK hoặc plugin version, hãy kiểm tra log Maven để xác nhận processor thực sự được nạp và nguồn sinh ra xuất hiện trong output directory mong muốn.

### Build tăng dần và tính xác định

Processor nên tạo đầu ra xác định từ đầu vào. Cùng một mã nguồn, annotation và option nên tạo cùng một kết quả. Tránh phụ thuộc vào thời gian hiện tại, thứ tự duyệt không ổn định, nội dung máy developer hoặc truy cập mạng không cần thiết.

Build tool có thể tối ưu incremental compilation dựa trên quan hệ giữa source, processor và generated output. Processor không xác định hoặc ghi file ngoài phạm vi build có thể làm kết quả build khó tái lập.

## 11. Các lỗi thường gặp

**Processor không được chạy**

Kiểm tra processor path, -processor, service descriptor và phiên bản JDK. Với JDK 23+, đừng dựa vào việc processor tình cờ nằm trên compile classpath.

**Không tìm thấy annotation type**

Mã nguồn ứng dụng cần annotation trên compile classpath. Processor path chỉ phục vụ việc nạp processor; nó không thay thế compile classpath.

**Processor chạy nhưng không thấy annotation**

Kiểm tra @SupportedAnnotationTypes, package name đầy đủ, retention, target và element được đánh dấu. Kiểm tra cả round mà annotation xuất hiện.

**Không tìm thấy class được sinh ra**

Kiểm tra processor có thực sự gọi Filer.createSourceFile, compiler có chạy round tiếp theo và mã nguồn được sinh có compile thành công không. Xem -s và -d để xác định đúng thư mục đầu ra.

**FilerException: Attempt to recreate a file**

Processor có thể đang tạo cùng một tên file nhiều lần. Kiểm tra round, tên file và logic tránh sinh trùng. Không ghi cùng một generated type ở mỗi round.

**Lỗi source version**

@SupportedSourceVersion phải phù hợp với source version mà processor hỗ trợ. Nếu dùng API ngôn ngữ mới hơn, hãy nâng source version hoặc xử lý rõ ràng giới hạn hỗ trợ.

**Generated source có lỗi cú pháp**

Dùng Messager để báo lỗi đầu vào sớm, kiểm tra escaping khi sinh literal Java và xem file trong -s để tìm nguyên nhân. Không ghép chuỗi tên package hoặc identifier từ dữ liệu chưa được kiểm tra.

**Annotation processing làm build chậm**

Tránh quét toàn bộ classpath hoặc filesystem không cần thiết. Chỉ xử lý annotation mà processor hỗ trợ, tránh lặp công việc qua round và giới hạn dữ liệu cần đọc.

**Hai processor cùng xử lý một annotation**

Hiểu quy tắc claim. Processor trả về true sẽ claim annotation được truyền vào; processor sau có thể không nhận annotation đó trong round. Nếu các processor cần cộng tác, hãy thiết kế rõ annotation nào được claim và processor nào chịu trách nhiệm.

## 12. Bảo mật và nguyên tắc thiết kế

Annotation processor là mã thực thi trong lúc build. Processor bên thứ ba có thể đọc tệp mà user build có quyền truy cập, gọi tiến trình khác hoặc truy cập mạng nếu môi trường cho phép. Vì vậy:

- Chỉ dùng processor từ nguồn tin cậy và pin version dependency.
- Phân biệt dependency runtime với dependency chỉ dùng khi compile.
- Không đưa secret vào processor option hoặc command line nếu không cần thiết.
- Không ghi token, credential hoặc nội dung nhạy cảm ra generated source hay diagnostic.
- Không để processor sửa trực tiếp source tree hoặc file ngoài output directory.
- Dùng Filer và Messager để tích hợp với compiler.
- Kiểm tra identifier, package name và giá trị được đưa vào mã sinh ra.
- Tránh phụ thuộc vào thứ tự file, thời gian hoặc môi trường máy build.
- Giữ processor nhỏ, dễ kiểm thử và có lỗi đầu vào rõ ràng.

Nếu processor tạo mã dựa trên thông tin ngoài source, hãy đưa dữ liệu đó thành input được quản lý và ghi nhận trong build. Điều này giúp build có thể tái lập và cache an toàn hơn.

## 13. Checklist khi triển khai annotation processor

1. Xác định annotation nào được hỗ trợ và element nào hợp lệ.
2. Chọn source version và khai báo @SupportedSourceVersion.
3. Viết processor dựa trên AbstractProcessor.
4. Dùng RoundEnvironment để lấy element cần xử lý.
5. Dùng Elements và Types để kiểm tra khai báo và kiểu.
6. Dùng Filer để tạo source, class hoặc resource.
7. Dùng Messager để báo lỗi và cảnh báo tại đúng element.
8. Định nghĩa option bằng @SupportedOptions và đọc qua getOptions().
9. Cấu hình processor path hoặc processor module path rõ ràng.
10. Kiểm tra discovery trên JDK 23+.
11. Tách generated source (-s) và class output (-d).
12. Kiểm thử trường hợp annotation thiếu, sai target, nhiều element, nhiều round và generated name bị trùng.
13. Kiểm tra build tăng dần, clean build và kết quả trên CI.

Pha xử lý annotation mở rộng compiler bằng cách cho phép kiểm tra và sinh mã dựa trên cấu trúc chương trình ngay trong thời điểm biên dịch. Khi hiểu processing rounds, processor discovery, compiler model và Filer, có thể xây dựng công cụ sinh mã an toàn, tích hợp tốt với javac và tạo ra build có thể tái lập.
