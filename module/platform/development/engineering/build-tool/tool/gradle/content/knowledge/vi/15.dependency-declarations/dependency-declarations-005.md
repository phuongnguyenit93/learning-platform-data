# annotationProcessor và testAnnotationProcessor trong Gradle: tách processor path cho main và test

## 1. Bài toán và mục tiêu học tập

Trong một dự án Java, các annotation như **@GenerateMarker**, **@Mapper**, **@AutoService** hoặc annotation của Lombok có thể được một **annotation processor** xử lý ngay trong quá trình biên dịch để sinh source code, kiểm tra quy tắc hoặc tạo metadata. Người mới thường thêm thư viện chứa processor vào **implementation** rồi thắc mắc tại sao lớp generated không tồn tại, hoặc thấy main compile được nhưng **compileTestJava** thất bại.

Nguyên nhân chủ yếu là Gradle phân biệt **thư viện cần nhìn thấy để biên dịch source** với **công cụ chạy bên trong Java compiler để xử lý annotation**. Hai source set mặc định **main** và **test** còn có **processor path** riêng.

Bài học thuộc nhóm **Khai báo dependency** và tập trung trực tiếp vào hai configuration do Java plugin cung cấp:

- **annotationProcessor**: khai báo annotation processor phục vụ biên dịch source set **main**, thường là task **compileJava**.
- **testAnnotationProcessor**: khai báo annotation processor phục vụ biên dịch source set **test**, thường là task **compileTestJava**.

Sau bài học, bạn có thể:

1. Giải thích annotation processing theo JSR 269, các vòng xử lý của javac và việc sinh source bằng **Filer**.
2. Phân biệt **annotationProcessor/testAnnotationProcessor**, **compileOnly/testCompileOnly**, **implementation/testImplementation** và runtime classpath.
3. Thiết lập processor cho source **main**, source **test** hoặc cả hai, tránh nhầm việc main compile được có nghĩa test tự kế thừa processor.
4. Tạo processor Java 17 có service registration, nối qua Gradle multi-project và chạy ví dụ sinh class riêng cho main/test.
5. Sử dụng Gradle Wrapper để xem dependency, processor path, generated sources và log lỗi compiler.
6. Hiểu các vấn đề hiệu năng, incremental compilation, IDE, an toàn chuỗi cung ứng và giới hạn với Kotlin/Android.

## 2. Annotation processor là gì?

### 2.1. Annotation không tự sinh code

Annotation trong Java là metadata gắn với class, method, field, constructor hoặc vị trí khác. Ví dụ:

~~~java
package demo.app;

import demo.annotations.GenerateMarker;

@GenerateMarker
public class ProductionExample {
}
~~~

Nếu chỉ định nghĩa annotation **@GenerateMarker** mà không có processor, Java compiler vẫn có thể biên dịch class trên nhưng **không tự sinh thêm class**. Annotation không phải macro hay một chỉ thị mặc định bắt javac tạo code.

Một annotation processor là một class triển khai **javax.annotation.processing.Processor**, thông thường kế thừa **AbstractProcessor**, được javac gọi trong lúc biên dịch để đọc phần tử annotated. Processor có thể:

- Sinh file Java mới bằng **Filer.createSourceFile(...)**.
- Sinh tài nguyên phụ trợ bằng **Filer.createResource(...)**.
- Báo lỗi hoặc cảnh báo qua **Messager** và **Diagnostic.Kind**.
- Kiểm tra type, method, annotation và các element từ mô hình **javax.lang.model**.
- Tạo mapper, adapter, builder, registry, metadata... theo quy tắc đã lập trình.

Processor chạy ở **compile time**, không phải khi chương trình Java main() đang chạy. Kết quả có thể là source Java được javac biên dịch tiếp trong những round sau hoặc một file resource có thể đóng gói vào artifact.

### 2.2. Sơ đồ một lần biên dịch có processing

~~~text
Java source main, ví dụ ProductionExample.java
                |
                v
          task :app:compileJava
                |
                +---- compileClasspath
                |       annotation API và các type cần tham chiếu
                |
                +---- annotationProcessorPath
                |       processor class + dependencies của processor
                |
                v
          javac chạy rounds xử lý annotation
                |
                +---- tìm processor đã đăng ký
                +---- gọi process(...)
                +---- Filer sinh ProductionExampleGenerated.java
                |
                v
          javac biên dịch source gốc và source generated
                |
                v
          build/classes/java/main
~~~

Với source test, dòng tương ứng là **:app:compileTestJava**, **testCompileClasspath**, **testAnnotationProcessor** và output test classes. **Không nhầm** source set test với task **test**: annotation processing xảy ra khi **biên dịch test source**, còn task **test** dùng các class đã biên dịch để chạy unit test.

### 2.3. Annotation retention và thời điểm processor nhìn thấy dữ liệu

Một annotation dành riêng cho compile time thường được định nghĩa với:

~~~java
package demo.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateMarker {
}
~~~

**RetentionPolicy.SOURCE** có nghĩa annotation chỉ tồn tại trong source, không cần được giữ lại trong class file hoặc runtime. Annotation processor vẫn nhìn thấy nó trong quá trình javac xử lý source.

Không phải mọi annotation processor đều tạo source. Một processor có thể chỉ xác thực quy tắc và báo lỗi compile; nhiều processor cần các annotation riêng nằm trong một artifact độc lập với artifact triển khai processor.

## 3. Hai configuration cốt lõi của Gradle

### 3.1. annotationProcessor dành cho source set main

Khi plugin **java**, **java-library** hoặc **application** được áp dụng, Gradle tạo các source set và configuration phù hợp. Ví dụ:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.36'
    annotationProcessor 'org.projectlombok:lombok:1.18.36'
}
~~~

Đây là **ví dụ về cặp cấu hình** cho một processor thông dụng. Chọn version thực sự tương thích với JDK và dự án; không coi một version trong bài là khuyến nghị mới nhất. Với nhiều processor giống Lombok, cùng artifact chứa cả annotation API lẫn processor implementation nên cần khai báo ở **hai vai trò riêng**.

**annotationProcessor** được Java plugin dùng cho **annotation processor path** của compile task tương ứng **main**, thay vì trộn processor vào application runtime. Processor artifact không vì thế tự trở thành thư viện của chương trình được chạy hoặc đóng gói vào JAR của ứng dụng.

### 3.2. testAnnotationProcessor dành cho source set test

Để processor xử lý những file trong **src/test/java**, cần khai báo:

~~~groovy
dependencies {
    testCompileOnly 'org.projectlombok:lombok:1.18.36'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.36'
}
~~~

Cùng một processor có thể được yêu cầu cho cả main và test:

~~~groovy
dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.36'
    annotationProcessor 'org.projectlombok:lombok:1.18.36'

    testCompileOnly 'org.projectlombok:lombok:1.18.36'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.36'
}
~~~

**Không tự suy ra rằng khai báo annotationProcessor cho main làm testAnnotationProcessor được cấu hình theo.** Mỗi source set có processor path riêng. Các dependency test có quy tắc kế thừa classpath riêng, nhưng Gradle không vì vậy tự chuyển tất cả processor main thành processor test.

### 3.3. Bảng phân biệt các vai trò dependency

| Configuration | Cung cấp cho đâu? | Dùng khi nào? |
| --- | --- | --- |
| **implementation** | Source compilation và runtime của module theo Java plugin | Library mà ứng dụng dùng khi chạy |
| **compileOnly** | Compile classpath của main, không đưa vào runtime | Annotation API chỉ cần khi biên dịch, API do môi trường cung cấp |
| **runtimeOnly** | Runtime classpath | Driver hoặc module chỉ cần khi chạy |
| **annotationProcessor** | Annotation processor path của main | Processor chạy khi **compileJava** |
| **testImplementation** | Compile/runtime dependency cho source set test | JUnit, AssertJ hoặc helper dùng khi chạy test |
| **testCompileOnly** | Chỉ compile classpath của test | Annotation API chỉ dùng trong src/test/java |
| **testRuntimeOnly** | Runtime của test | JUnit Platform Launcher hoặc test implementation runtime |
| **testAnnotationProcessor** | Annotation processor path của test | Processor chạy khi **compileTestJava** |

**compileOnly** khác **annotationProcessor**: cái đầu cho source code nhìn thấy **annotation type**; cái sau cho javac thực thi **processor implementation**. Nếu một artifact chứa cả hai thì khai báo cùng tọa độ ở hai configuration. Nếu annotation API và processor được xuất bản thành hai artifact khác nhau, khai báo đúng từng artifact.

Không dùng **testImplementation** để thay một cách tùy ý cho **testAnnotationProcessor**; test source có thể compile được annotation type nhưng processor vẫn không chạy.

### 3.4. Vai trò của testImplementation

Nếu ứng dụng test dùng JUnit 5, dependency:

~~~groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
}
~~~

là **thư viện phục vụ test**, không phải annotation processor path. Annotation **@Test** là metadata được JUnit phát hiện khi chạy test; nó không có nghĩa JUnit Jupiter phải đặt trong **testAnnotationProcessor**.

Hai khái niệm độc lập:

- **JUnit**: framework thực thi kiểm thử Java, thường dùng testImplementation và test runtime launcher.
- **JSR 269 annotation processor**: công cụ javac gọi khi biên dịch và nằm trên annotation processor path.

Trong ví dụ chạy được ở mục 7, ta **không yêu cầu tải JUnit** để tránh nhiễu giữa tác vụ kiểm thử và annotation processing. Ta chạy một class trong test source set bằng **JavaExec** để xác minh class được sinh ra.

## 4. Processor path khác compile classpath và runtime classpath

### 4.1. Ba classpath có mục đích khác nhau

~~~text
             src/main/java
                 |
          +------+--------+
          |               |
          v               v
     compileClasspath   annotationProcessorPath
       annotation API     processor implementation
       Java libraries     service registration
          |               |
          +------+--------+
                 v
             Java compiler
                 |
                 v
            main classes
                 |
                 v
           runtimeClasspath
           (không tự bao gồm processor)
~~~

**options.annotationProcessorPath** của task **JavaCompile** là file collection chứa processor path. Với Java plugin, source set có **annotationProcessorPath** và mặc định trỏ vào configuration annotation processor tương ứng.

Ví dụ để quan sát cấu hình với task do Java plugin cung cấp:

~~~groovy
tasks.named('compileJava', JavaCompile) {
    doFirst {
        println 'Processor path files: ' +
                options.annotationProcessorPath.files.size()
    }
}
~~~

Đây là **đoạn quan sát mang tính chẩn đoán**, cần đặt trong project đã áp dụng Java plugin; không phải ví dụ độc lập. Tránh in toàn bộ đường dẫn/metadata dependency vào log CI công khai nếu hệ thống dùng repository riêng. Trong thực tế nên kiểm tra compile logs/đường dẫn generated sources và báo cáo cấu hình, thay vì thêm nhiều println vào task build.

### 4.2. Vì sao implementation không phải nơi đặt processor?

Nếu một processor JAR chỉ được khai báo trong **implementation**:

~~~groovy
dependencies {
    implementation project(':processor')
}
~~~

JAR đó có thể xuất hiện trong application compile/runtime classpath nhưng **không đồng nghĩa Gradle cấu hình nó trên processor path**. Bạn có thể gặp:

~~~text
cannot find symbol: class ProductionExampleGenerated
~~~

vì processor không được compiler phát hiện/chạy. Ngoài ra, vô tình đưa processor và thư viện phụ thuộc của nó vào artifact runtime thường không cần thiết, làm classpath phình to và ảnh hưởng compile avoidance.

Khi muốn chạy processor cho main, dùng:

~~~groovy
dependencies {
    annotationProcessor project(':processor')
}
~~~

Khi muốn nó chạy cho test, dùng:

~~~groovy
dependencies {
    testAnnotationProcessor project(':processor')
}
~~~

Đường dẫn **:processor** là project path Gradle đã được include trong settings. Đó là một project dependency trỏ tới artifact chứa processor, **không phải task tên processor**.

### 4.3. Vì sao compileOnly một mình cũng chưa đủ?

Nếu chỉ có:

~~~groovy
dependencies {
    compileOnly project(':annotations')
}
~~~

javac nhìn thấy **@GenerateMarker**, nhưng không có processor implementation trên annotation processor path nên nó không tự sinh **ProductionExampleGenerated**. Source code có thể tham chiếu annotation hợp lệ nhưng compilation của code tham chiếu generated class sẽ thất bại.

Với hai artifact riêng:

~~~groovy
dependencies {
    compileOnly project(':annotations')
    annotationProcessor project(':processor')
}
~~~

đây mới là hai nửa cần thiết. Nếu processor tham chiếu annotation API bằng class **GenerateMarker.class**, artifact annotations cũng phải sẵn có khi processor chạy, thông thường qua transitive runtime dependency của artifact processor.

### 4.4. Khi nào annotation API cần có ở runtime?

**RetentionPolicy.SOURCE** không cần annotation type ở runtime, nên **compileOnly** thường hợp lý. Nhưng không được áp quy tắc đó cho mọi annotation:

- Nếu thư viện runtime dùng reflection để đọc annotation có **RetentionPolicy.RUNTIME**, annotation type có thể cần trên runtime classpath.
- Nếu generated code tham chiếu một API runtime riêng, API đó phải được khai báo **implementation** hoặc **runtimeOnly** phù hợp.
- Nếu annotation type xuất hiện trong chữ ký public API của một thư viện, cần xem API exposure và **java-library** thay vì mặc định compileOnly.

Nên xác định **processor chỉ cần để sinh code**, **annotation chỉ cần để compile**, hay **thư viện thật sự cần khi chạy**. Một artifact chứa nhiều thành phần không thay thế phân tích này.

## 5. JSR 269: processor được phát hiện và gọi ra sao?

### 5.1. Service registration

Với processor triển khai class:

~~~java
package demo.processor;

public final class GenerateMarkerProcessor
        extends javax.annotation.processing.AbstractProcessor {
    // Phần triển khai thật được trình bày đầy đủ ở mục 7.
}
~~~

Đây chỉ là **đoạn cấu trúc minh họa**, chưa đầy đủ để biên dịch. Để javac tự phát hiện processor qua service loader, JAR có file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung file là **tên class đủ package** trên một dòng:

~~~text
demo.processor.GenerateMarkerProcessor
~~~

Trong Gradle Java project, đường dẫn source resources tương ứng thường là:

~~~text
processor/src/main/resources/META-INF/services/javax.annotation.processing.Processor
~~~

Khi build artifact của **:processor**, resources được đưa vào JAR. Javac tìm processor qua service file trên processor path. Nếu bạn quên file này, class processor vẫn tồn tại nhưng có thể không được tự động phát hiện.

Có thể đăng ký processor bằng cơ chế processor discovery khác hoặc chỉ rõ processor qua tham số **-processor**, nhưng ví dụ này dùng service loader để minh họa cách thư viện processor được đóng gói.

### 5.2. Mỗi vòng processing làm gì?

Java compiler có thể gọi processor qua nhiều **round**:

1. Phân tích source, phát hiện các annotation được hỗ trợ.
2. Gọi **process(annotations, roundEnv)** của processor.
3. Processor dùng **Filer.createSourceFile** tạo source mới.
4. Javac tiếp tục round để xử lý source vừa sinh và các annotation mới.
5. Khi không còn source được sinh và quá trình hoàn thành, round cuối có **roundEnv.processingOver() = true**.

**Không tự viết lại cùng một generated file ở mỗi round**, vì Filer có thể báo **FilerException: Attempt to recreate a file for type ...**. Processor cần thiết kế tên generated class duy nhất theo từng element và chỉ sinh khi gặp element cần xử lý.

### 5.3. @SupportedAnnotationTypes và @SupportedSourceVersion

Processor có thể khai báo:

~~~java
@SupportedAnnotationTypes("demo.annotations.GenerateMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
~~~

- **SupportedAnnotationTypes** chỉ các loại annotation mà processor nhận xử lý.
- **SupportedSourceVersion** nói processor hỗ trợ mô hình ngôn ngữ đến phiên bản nào.
- **SourceVersion.RELEASE_17** phù hợp khi ví dụ biên dịch bằng Java toolchain 17.

**@SupportedSourceVersion không tự chọn JDK cho Gradle.** Toolchain trong build.gradle mới quyết định Java compiler dùng để compile source. Khi nâng source level cao hơn, cần kiểm tra processor/Gradle/JDK tương thích.

## 6. Cấu hình tách main và test trong build.gradle

Với plugin **java** hoặc **application**, một mô hình thông thường:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    // Annotation API chỉ có khi compile main.
    compileOnly project(':annotations')

    // Processor được javac dùng trong compileJava.
    annotationProcessor project(':processor')

    // Annotation API khi compile test.
    testCompileOnly project(':annotations')

    // Processor được javac dùng trong compileTestJava.
    testAnnotationProcessor project(':processor')
}
~~~

Đoạn trên yêu cầu các project **:annotations** và **:processor** được khai báo trong **settings.gradle**. Nó không tự chạy nếu bạn chép vào một project không có các module đó.

### 6.1. Sơ đồ theo source set

| Java source set | Source | Task compile thường gặp | Processor dependency |
| --- | --- | --- | --- |
| **main** | **src/main/java** | **compileJava** | **annotationProcessor** |
| **test** | **src/test/java** | **compileTestJava** | **testAnnotationProcessor** |
| **integrationTest** tự tạo | Ví dụ **src/integrationTest/java** | Task compile tương ứng do plugin/source set tạo | Configuration processor tương ứng với source set, thường **integrationTestAnnotationProcessor** |
| Source set khác | Thư mục theo cấu hình | JavaCompile task tương ứng | Annotation processor path riêng nếu plugin cung cấp |

Đừng mặc định mọi plugin JVM/Android tự dùng đúng tên configuration của Java plugin:

- Kotlin JVM thường dùng **kapt** hoặc **KSP** nếu processor/generator hỗ trợ và có plugin tương ứng.
- Android Gradle Plugin có variant-specific task/configuration và quy tắc riêng, nhất là Kotlin/Java mixed modules.
- Java Module System có module path và processor path/module path cần xem tài liệu riêng.

Bài này áp dụng trực tiếp cho **Gradle Java plugin và javac**.

### 6.2. Khi nào test không cần testAnnotationProcessor?

Nếu trong **src/test/java** không có annotation cần xử lý và test source chỉ dùng các class generated từ **main**, bạn có thể **không cần** cấu hình testAnnotationProcessor. Class generated từ main đã được biên dịch và nằm trên output main, thường có trong test compile/runtime classpath.

Ngược lại, nếu **test source tự dùng annotation cần sinh class riêng cho test**, phải cấu hình processor trên **testAnnotationProcessor**. Trong ví dụ sắp tới, **ProductionExampleGenerated** được sinh khi compile main, còn **TestExampleGenerated** được sinh khi compile test.

## 7. Ví dụ Java 17 chạy được: tự viết annotation processor và dùng cho main/test

Đây là một ví dụ độc lập, không cần tải thư viện JUnit/Lombok/MapStruct từ bên ngoài. Ta tự tạo:

1. **:annotations** chứa annotation **@GenerateMarker**.
2. **:processor** chứa processor JSR 269 và service file để javac tự phát hiện.
3. **:app** chứa Java source main và test, trong đó mỗi source set có annotated class riêng.

Processor sinh một class mới có hậu tố **Generated** cho từng class được gắn **@GenerateMarker**. Ví dụ **ProductionExample** sinh **ProductionExampleGenerated**; **TestExample** sinh **TestExampleGenerated**.

### 7.1. Cấu trúc đầy đủ

~~~text
annotation-processing-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── annotations/
│   ├── build.gradle
│   └── src/main/java/demo/annotations/GenerateMarker.java
├── processor/
│   ├── build.gradle
│   ├── src/main/java/demo/processor/GenerateMarkerProcessor.java
│   └── src/main/resources/META-INF/services/
│       └── javax.annotation.processing.Processor
└── app/
    ├── build.gradle
    ├── src/main/java/demo/app/ProductionExample.java
    ├── src/main/java/demo/app/Main.java
    ├── src/test/java/demo/app/TestExample.java
    └── src/test/java/demo/app/TestGeneratedCheck.java
~~~

Nếu repo mới chưa có Wrapper, hãy dùng một Gradle CLI đáng tin để chạy **gradle wrapper** ở root một lần, rồi dùng **./gradlew** trên Linux/macOS hoặc **.\gradlew.bat** trên Windows. Cần Gradle version tương thích JDK trên máy, và Java 17 toolchain có sẵn hoặc cấu hình cung cấp JDK phù hợp.

### 7.2. settings.gradle

~~~groovy
rootProject.name = 'annotation-processing-lab'
include ':annotations', ':processor', ':app'
~~~

Tất cả project thuộc một build. Không cần tải external dependency nào trong ví dụ, vì chỉ dùng Gradle Java plugins và Java standard library.

### 7.3. build.gradle ở root

~~~groovy
plugins {
    id 'base'
}
~~~

Root chỉ là project điều phối, không cần áp dụng Java plugin cho mọi subproject.

### 7.4. annotations/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**annotations/src/main/java/demo/annotations/GenerateMarker.java:**

~~~java
package demo.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateMarker {
}
~~~

Annotation là source-retention, dùng trên type. Module **:annotations** có thể biên dịch thành JAR, để code app compile annotation và để processor nhận dạng annotation class.

### 7.5. processor/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':annotations')
}
~~~

**:processor** phụ thuộc **:annotations** vì Java source của processor tham chiếu **GenerateMarker.class**. Dependency **implementation** này phục vụ **biên dịch và chạy chính processor**; nó không có nghĩa app phải dùng **implementation project(':processor')**.

Khi app dùng **annotationProcessor project(':processor')**, Gradle resolve artifact processor cùng các runtime dependencies cần để processor chạy, bao gồm **:annotations** theo metadata từ project dependency.

### 7.6. processor/src/main/java/demo/processor/GenerateMarkerProcessor.java

~~~java
package demo.processor;

import demo.annotations.GenerateMarker;
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

@SupportedAnnotationTypes("demo.annotations.GenerateMarker")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GenerateMarkerProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateMarker.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateMarker chỉ hỗ trợ class",
                        element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            String original = type.getSimpleName().toString();
            String generated = original + "Generated";
            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(type)
                    .getQualifiedName()
                    .toString();

            String fullName = packageName.isEmpty()
                    ? generated
                    : packageName + "." + generated;

            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile(fullName, type);

                try (Writer writer = file.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n");
                    }
                    writer.write("public final class " + generated + " {\n");
                    writer.write("  private " + generated + "() { }\n");
                    writer.write(
                            "  public static String message() { " +
                            "return \"generated:" + original + "\"; }\n");
                    writer.write("}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Không thể sinh " + fullName + ": " + ex.getMessage(),
                        element);
            }
        }

        return true;
    }
}
~~~

Giải thích những chi tiết quan trọng:

- **AbstractProcessor** đã cung cấp một phần API thông thường của Processor; class khai báo annotation và source version được hỗ trợ.
- **roundEnv.getElementsAnnotatedWith(GenerateMarker.class)** tìm class được annotate trong round hiện tại.
- **ElementKind.CLASS** tránh sinh code khi annotation gắn vào loại phần tử không được xử lý bởi logic demo.
- **createSourceFile(fullName, type)** sinh Java source mới và khai báo **originating element**, hữu ích cho Gradle và công cụ build hiểu nguồn gốc output.
- **Writer** được đóng bằng try-with-resources, không để file generated ghi dở.
- Tên class generated lấy từ class gốc, ví dụ **ProductionExampleGenerated**.
- Generated class có **message()** trả một chuỗi xác định, không chứa thời gian ngẫu nhiên, đường dẫn máy hoặc tác động mạng.
- Nếu Filer không ghi được file, **Messager** báo lỗi compile rõ ràng thay vì âm thầm bỏ qua.
- **return true** cho javac biết processor đã nhận trách nhiệm các annotation nó hỗ trợ trong round này.

Processor chỉ sinh class cho những class gắn annotation trong source được compile. Nó không tạo file cho mọi class của project và không được chạy khi chương trình main() thực thi.

### 7.7. Service file để javac phát hiện processor

Tạo chính xác file:

~~~text
processor/src/main/resources/META-INF/services/javax.annotation.processing.Processor
~~~

Với nội dung một dòng, kết thúc bằng newline:

~~~text
demo.processor.GenerateMarkerProcessor
~~~

Tên file **javax.annotation.processing.Processor** dùng namespace của **JSR 269**, không phải **jakarta.annotation.processing.Processor**. Khi build **:processor:jar**, service file phải nằm trong JAR tại **META-INF/services/**; nếu thiếu, javac không tự phát hiện processor mặc dù class Java đã được compile.

### 7.8. app/build.gradle

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // Annotation API cho source main:
    compileOnly project(':annotations')

    // Processor chạy khi compileJava:
    annotationProcessor project(':processor')

    // Annotation API cho source test:
    testCompileOnly project(':annotations')

    // Processor chạy khi compileTestJava:
    testAnnotationProcessor project(':processor')
}

application {
    mainClass = 'demo.app.Main'
}

tasks.register('runGeneratedTest', JavaExec) {
    group = 'verification'
    description = 'Chạy class test-source sau annotation processing'
    dependsOn tasks.named('testClasses')
    classpath = sourceSets.test.runtimeClasspath
    mainClass.set('demo.app.TestGeneratedCheck')
}
~~~

**application** plugin cung cấp Java plugin và task **run**. **runGeneratedTest** là custom JavaExec task, dùng output **testClasses** và test runtime classpath để chạy một class main đặt trong **src/test/java**.

Nó **không phải** một task **Test** của JUnit; demo không cần cài JUnit. Ta cố ý phân tách “source set test được biên dịch với processor riêng” khỏi “framework chạy test”. Không chạy **:app:test** trong demo để kết luận annotation processor hoạt động, vì **:app:test** được thiết kế cho test framework, không tự chạy class có main().

### 7.9. app/src/main/java/demo/app/ProductionExample.java

~~~java
package demo.app;

import demo.annotations.GenerateMarker;

@GenerateMarker
public class ProductionExample {
}
~~~

Khi biên dịch main, processor sẽ tạo **demo.app.ProductionExampleGenerated**.

### 7.10. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
                "main=" + ProductionExampleGenerated.message());
    }
}
~~~

**ProductionExampleGenerated** chưa tồn tại trong Git source tree. Nó được javac tạo và compile trong quá trình **:app:compileJava**. Đó là mục đích cốt lõi của annotation processing.

### 7.11. app/src/test/java/demo/app/TestExample.java

~~~java
package demo.app;

import demo.annotations.GenerateMarker;

@GenerateMarker
public class TestExample {
}
~~~

Class này thuộc **source set test**, không thuộc main. Processor trên **testAnnotationProcessor** sẽ tạo **demo.app.TestExampleGenerated** khi chạy **compileTestJava**.

### 7.12. app/src/test/java/demo/app/TestGeneratedCheck.java

~~~java
package demo.app;

public final class TestGeneratedCheck {
    private TestGeneratedCheck() {
    }

    public static void main(String[] args) {
        System.out.println(
                "test=" + TestExampleGenerated.message());
    }
}
~~~

Task **runGeneratedTest** sẽ chạy class này sau khi **testClasses** được tạo. Nếu bỏ **testAnnotationProcessor**, **TestExampleGenerated** không được sinh và javac sẽ báo lỗi không tìm thấy symbol.

### 7.13. Chạy demo bằng Gradle Wrapper

**Linux/macOS:**

~~~bash
./gradlew --version
./gradlew :app:compileJava
./gradlew :app:run
./gradlew :app:compileTestJava
./gradlew :app:runGeneratedTest
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat --version
.\gradlew.bat :app:compileJava
.\gradlew.bat :app:run
.\gradlew.bat :app:compileTestJava
.\gradlew.bat :app:runGeneratedTest
~~~

**Stdout chính xác do class Main in khi gọi :app:run:**

~~~text
main=generated:ProductionExample
~~~

**Stdout chính xác do class TestGeneratedCheck in khi gọi :app:runGeneratedTest:**

~~~text
test=generated:TestExample
~~~

Những dòng trên là stdout của Java code, không phải toàn bộ log Gradle. Gradle còn có thể in các dòng về task, daemon, cache, cảnh báo hoặc **BUILD SUCCESSFUL**.

### 7.14. Tìm generated sources ở đâu?

Với layout mặc định của Java plugin hiện hành, có thể tìm các file tương tự:

~~~text
app/build/generated/sources/annotationProcessor/java/main/demo/app/
    ProductionExampleGenerated.java

app/build/generated/sources/annotationProcessor/java/test/demo/app/
    TestExampleGenerated.java
~~~

Đường dẫn có thể khác nếu thay **buildDirectory** hoặc compiler generated-source output location. Đừng chỉnh sửa generated sources rồi commit như mã nguồn chính; hãy sửa annotated source hoặc processor và để Gradle sinh lại.

Class files sau compile thường nằm trong:

~~~text
app/build/classes/java/main/demo/app/ProductionExampleGenerated.class
app/build/classes/java/test/demo/app/TestExampleGenerated.class
~~~

Có thể dùng **javap -classpath app/build/classes/java/main demo.app.ProductionExampleGenerated** để xem API class đã biên dịch. Nếu Gradle task **UP-TO-DATE**, processor có thể không chạy lại vì không cần, nhưng generated source/class vẫn còn từ lần build đúng trước đó.

### 7.15. Xác minh bằng javac không phụ thuộc Gradle task

Có thể kiểm chứng chính compiler API bằng JDK 17. Sau đây là lệnh cho Linux/macOS tại root repo; nó tự chỉ định processor class qua **-processor**, nên không cần copy service file riêng vào classpath thủ công.

~~~bash
mkdir -p out/annotations out/processor out/main out/test gen/main gen/test

javac --release 17 -d out/annotations \
  annotations/src/main/java/demo/annotations/GenerateMarker.java

javac --release 17 -cp out/annotations -d out/processor \
  processor/src/main/java/demo/processor/GenerateMarkerProcessor.java

javac --release 17 \
  -cp out/annotations \
  -processorpath out/processor:out/annotations \
  -processor demo.processor.GenerateMarkerProcessor \
  -s gen/main -d out/main \
  app/src/main/java/demo/app/ProductionExample.java \
  app/src/main/java/demo/app/Main.java

javac --release 17 \
  -cp out/annotations:out/main \
  -processorpath out/processor:out/annotations \
  -processor demo.processor.GenerateMarkerProcessor \
  -s gen/test -d out/test \
  app/src/test/java/demo/app/TestExample.java \
  app/src/test/java/demo/app/TestGeneratedCheck.java

java -cp out/main demo.app.Main
java -cp out/test:out/main demo.app.TestGeneratedCheck
~~~

**Đầu ra hai lệnh java cuối** là:

~~~text
main=generated:ProductionExample
test=generated:TestExample
~~~

Trên Windows PowerShell, dấu phân tách classpath/processorpath là **dấu chấm phẩy**, thay cho dấu hai chấm dùng trên Linux/macOS; các lệnh nhiều dòng cũng dùng cú pháp nối dòng PowerShell thay **\**. Lệnh Gradle Wrapper ở mục 7.13 đã có biến thể PowerShell chạy trực tiếp, nên với người học trên Windows nên ưu tiên các lệnh đó.

Lệnh javac thủ công xác nhận processor JSR 269 và source Java hợp lệ; lệnh Gradle xác nhận việc wiring **annotationProcessor** và **testAnnotationProcessor** đúng.

## 8. Hai kịch bản sai dễ gặp nhất

### 8.1. Main compile được, test compile lỗi

Giả sử app còn:

~~~groovy
dependencies {
    compileOnly project(':annotations')
    annotationProcessor project(':processor')
    testCompileOnly project(':annotations')
}
~~~

Bỏ **testAnnotationProcessor project(':processor')** có nghĩa test javac không được cung cấp processor path cần thiết trong mô hình demo. Khi compileTestJava, class **TestExampleGenerated** không xuất hiện; **TestGeneratedCheck.java** báo **cannot find symbol**.

Đừng tự sửa bằng **testImplementation project(':processor')**: đó là đưa JAR vào test classpath thông thường, không phải khai báo processor path. Giải pháp đúng là khôi phục **testAnnotationProcessor**.

### 8.2. Có annotation type nhưng không có generated class của main

Giả sử app chỉ có:

~~~groovy
dependencies {
    compileOnly project(':annotations')
}
~~~

**ProductionExample.java** compile được về mặt annotation syntax; nhưng Main.java tham chiếu **ProductionExampleGenerated** nên compilation thất bại vì file chưa được sinh. Thêm:

~~~groovy
annotationProcessor project(':processor')
~~~

vào **dependencies** của app.

Nếu đã khai báo processor mà vẫn không sinh class, kiểm tra tiếp **service registration file**, version JDK, supported annotation type và lỗi trong processor.

## 9. Cách Gradle nối processor path với task compile

### 9.1. JavaCompile và source sets

Java plugin tạo **compileJava** và **compileTestJava**, mỗi task có input sources, classpath, compiler options và output directory. Processor được cấu hình từ source set:

~~~text
sourceSets.main
    src/main/java
    compileClasspath
    annotationProcessorPath = annotationProcessor
            |
            v
        compileJava

sourceSets.test
    src/test/java
    compileClasspath
    annotationProcessorPath = testAnnotationProcessor
            |
            v
        compileTestJava
~~~

**annotationProcessor** là tên configuration để **khai báo dependency**, không phải tên một task có thể chạy trực tiếp như **./gradlew annotationProcessor**.

**compileTestJava** sử dụng output main khi cần, nhưng nguồn annotationProcessor của main không tự trở thành testAnnotationProcessor. Nếu test source không có annotation riêng cần xử lý, việc không khai báo testAnnotationProcessor có thể hoàn toàn hợp lý.

### 9.2. Kiểm tra report dependency

Các lệnh:

~~~bash
./gradlew :app:dependencies --configuration annotationProcessor
./gradlew :app:dependencies --configuration testAnnotationProcessor
./gradlew :app:compileJava --info
./gradlew :app:compileTestJava --info
~~~

giúp kiểm tra declaration và quá trình compile. Một số Gradle version đánh dấu những configuration chỉ-dùng-để-khai-báo là **không resolvable trực tiếp**, vì thế báo cáo dependencies có thể hiển thị thông tin khai báo mà không đi sâu vào graph đã resolve. Khi cần biết classpath processor thực tế, xem input **JavaCompile.options.annotationProcessorPath** hoặc log compiler phù hợp.

Không suy luận chỉ từ việc output class đã tồn tại trên disk rằng processor đã chạy trong lần gọi hiện tại: task có thể **UP-TO-DATE** hoặc **FROM-CACHE**.

### 9.3. Tham số javac để điều tra

Trong một JavaCompile task, có thể tạm thêm:

~~~groovy
tasks.named('compileJava', JavaCompile) {
    options.compilerArgs.addAll([
        '-XprintRounds',
        '-XprintProcessorInfo'
    ])
}
~~~

Lệnh này yêu cầu javac in thông tin round và processor. Đây là **chế độ chẩn đoán**, không phải cấu hình cần giữ vĩnh viễn. Khi sửa compilerArgs, fingerprint của task compile có thể thay đổi và buộc compile lại; sau khi điều tra, hãy xóa để tránh log quá lớn.

**-proc:none** tắt annotation processing. **-proc:only** yêu cầu chỉ xử lý annotation mà không biên dịch bình thường. Đừng vô tình giữ hai flag đó khi bạn muốn javac sinh và compile code ứng dụng đầy đủ.

## 10. Incremental annotation processing và hiệu năng

### 10.1. Vì sao phải tách processor khỏi compile classpath?

Annotation processor là **mã Java được thực thi trong compiler**. Một thay đổi trong implementation của processor có thể làm generated source khác đi, ngay cả khi ABI của thư viện không đổi. Vì vậy Gradle phải theo dõi processor path như input phù hợp, khác với một số tối ưu compile avoidance cho dependency thường.

Khi processor nằm lẫn trên compile classpath, Gradle khó tách phạm vi ảnh hưởng và có thể phải phân tích lại nhiều dependency hơn, làm giảm hiệu năng. Khai báo **annotationProcessor** riêng không chỉ giúp dễ hiểu mà còn hỗ trợ compile avoidance và caching đúng hơn.

### 10.2. Incremental processor: isolating và aggregating

Gradle hỗ trợ các annotation processor có thể tham gia incremental annotation processing khi processor tuân thủ contract và khai báo metadata phù hợp.

Hai nhóm khái niệm:

- **Isolating**: generated file có nguồn gốc từ một phần tử đầu vào cụ thể. Khi chỉ phần tử đó thay đổi, processor có thể hỗ trợ giới hạn phần công việc phải làm lại.
- **Aggregating**: generated file phụ thuộc vào tập hợp nhiều phần tử, chẳng hạn registry tổng hợp tất cả annotated classes. Thay đổi một phần tử có thể làm output tổng hợp cần sinh lại.

Đoạn demo **GenerateMarkerProcessor** tạo một generated class cho mỗi annotated class và truyền **originating element** vào **createSourceFile(fullName, type)**; đây là bước quan trọng để một processor kiểu isolating có thể hoạt động đúng. Tuy nhiên **demo chưa khai báo metadata incremental của Gradle**, nên không được tuyên bố nó đã được Gradle nhận diện là processor incremental.

Với processor thật, cần tham khảo tài liệu Gradle về metadata file **META-INF/gradle/incremental.annotation.processors**, khai báo dạng isolating hoặc aggregating đúng với hành vi của processor và kiểm thử khi đổi/xóa annotated source. **Không gắn nhãn isolating cho processor tổng hợp nhiều nguồn** chỉ để có kết quả benchmark đẹp.

### 10.3. Generated source cần tính xác định

Để build có khả năng tái lập:

- Không thêm timestamp, đường dẫn máy hoặc ID ngẫu nhiên vào generated source nếu không thật sự cần.
- Nếu tổng hợp nhiều element, sắp xếp chúng theo thứ tự ổn định.
- Dùng **Filer** thay vì tự viết file tùy ý sang **src/main/java** hoặc **src/test/java**.
- Không truy cập internet từ processor trong compilation thông thường nếu có thể tránh.
- Ghi rõ compiler options làm thay đổi output; dùng API khai báo input tương ứng.
- Không để generated source phụ thuộc vào state biến đổi ngoài input của compilation.

Một processor sinh file ở thư mục source được commit dễ gây stale code, merge conflict và khó dọn sạch. Trong demo, Gradle quản lý generated outputs trong build directory.

### 10.4. Annotation processing và build cache

Task JavaCompile có thể được Gradle đánh giá up-to-date hoặc lấy output từ build cache khi input đúng và task đủ điều kiện. Processor version, processor classpath, compiler arguments, input sources và các yếu tố liên quan đều có thể ảnh hưởng fingerprint.

Đừng dùng **--rerun-tasks** để chữa mọi vấn đề sinh code; nó chỉ buộc một số công việc chạy lại. Nếu processor path thiếu hoặc service file sai, chạy lại không tự làm processor xuất hiện. Khi debugging có thể dùng **clean compileJava**, nhưng cần sửa cấu hình gốc trước.

## 11. Lombok và MapStruct: cấu hình thường gặp

### 11.1. Lombok: annotation và processor trong cùng artifact

Một cấu hình Groovy DSL quen thuộc:

~~~groovy
plugins {
    id 'java'
}

dependencies {
    compileOnly 'org.projectlombok:lombok:1.18.36'
    annotationProcessor 'org.projectlombok:lombok:1.18.36'

    testCompileOnly 'org.projectlombok:lombok:1.18.36'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.36'
}
~~~

Đây là **ví dụ để nhận diện các scope**, không có nghĩa version minh họa là phiên bản mới nhất hay đã tương thích mọi JDK. Lombok thực hiện các kỹ thuật compiler integration đặc thù ngoài ví dụ JSR 269 đơn giản; với JDK mới, hãy kiểm tra compatibility của Lombok trước khi nâng Gradle/JDK.

Nếu Lombok được dùng trong main mà không trong test, không nhất thiết phải khai báo cả hai test configurations. Ngược lại, nếu test source dùng **@Getter** hoặc **@Builder** của Lombok, phải kiểm tra processor có chạy khi compileTestJava.

### 11.2. MapStruct: annotation/API và processor có thể tách artifact

Ví dụ dạng điển hình:

~~~groovy
dependencies {
    implementation 'org.mapstruct:mapstruct:1.6.3'
    annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'
}
~~~

**org.mapstruct:mapstruct** cung cấp API/annotation mà source tham chiếu; **mapstruct-processor** cung cấp code generator. Cách chọn **implementation** hay **compileOnly** cho API còn tùy việc annotation/API có cần trong runtime/public ABI hay không, và yêu cầu project. Không chuyển processor vào implementation chỉ để “IDE thấy JAR”.

Nếu test source tự khai báo **@Mapper** và cần implementation riêng cho test, bổ sung:

~~~groovy
dependencies {
    testImplementation 'org.mapstruct:mapstruct:1.6.3'
    testAnnotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'
}
~~~

Đây là ví dụ scope, không thay thế tài liệu chính thức của MapStruct hoặc yêu cầu JDK/version cụ thể. Với thư viện có processor transitive hoặc plugin companion, cần xem hướng dẫn của thư viện trước khi cấu hình.

### 11.3. JUnit không cần annotationProcessor

JUnit **@Test** không được dùng theo nghĩa Gradle Java annotation processing để sinh class. Khi muốn chạy JUnit tests, bạn cần test framework và cấu hình task **Test** thích hợp, chẳng hạn JUnit Platform. Không đưa JUnit Jupiter vào **testAnnotationProcessor** nếu mục đích chỉ là chạy unit tests.

## 12. Các lỗi phổ biến và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **cannot find symbol: FooGenerated** ở compileJava | Thiếu annotationProcessor, service file, annotation type không đúng hoặc processor lỗi | Kiểm tra processor path, JAR META-INF/services, compiler logs |
| **cannot find symbol: TestFooGenerated** chỉ ở compileTestJava | Thiếu testAnnotationProcessor cho test source | Khai báo processor ở testAnnotationProcessor |
| **package demo.annotations does not exist** | Thiếu compileOnly/testCompileOnly hoặc API không được expose | Bổ sung annotation API đúng source set |
| Processor JAR có class nhưng không sinh file | Service registration sai hoặc processor không nhận annotation | Kiểm tra tên class trong META-INF/services và @SupportedAnnotationTypes |
| **Bad service configuration file** | Service file trỏ class sai, class không load được hoặc có lỗi packaging | Kiểm tra nội dung và dependency runtime của processor |
| **NoClassDefFoundError** trong processor | Processor runtime path thiếu dependency của chính processor | Thêm runtime dependency ở module processor hoặc sửa metadata |
| **FilerException: Attempt to recreate a file** | Sinh cùng FQCN nhiều lần hoặc nhiều processor trùng output | Tạo tên duy nhất và tôn trọng processing rounds |
| Annotation có nhưng không được processor chọn | Target/retention/type hoặc supported type sai | Kiểm tra package FQCN, annotation source, logic process |
| Main generated code có, test generated code thiếu | Test dùng processor path riêng | Kiểm tra testAnnotationProcessor và compileTestJava |
| Có generated file nhưng IDE gạch đỏ | IDE chưa sync generated sources/annotation processing | Reimport Gradle project, delegate build hoặc bật processor support phù hợp |
| IDE chạy nhưng CI compile lỗi | IDE có processor config riêng, CI thiếu Gradle declaration | Đồng bộ cách build qua Gradle Wrapper, tránh lệ thuộc IDE-only config |
| Nâng JDK thì processor lỗi | Processor/Lombok/MapStruct không tương thích compiler version | Kiểm tra compatibility matrix, nâng processor hoặc dùng toolchain phù hợp |
| Build quá chậm khi bật processor | Processor non-incremental, scan toàn bộ elements, IO nặng | Kiểm tra incremental metadata, số round, profiling |
| **-proc:none** khiến không sinh code | Annotation processing bị tắt | Bỏ flag khi cần compiler chạy processor |
| Processor nằm trên implementation và lọt runtime | Khai báo sai classpath | Chuyển processor sang annotationProcessor/testAnnotationProcessor |
| Build vẫn dùng generated file cũ | File stale, task up-to-date hoặc output được cache | Kiểm tra input/path; clean có thể hỗ trợ chẩn đoán nhưng không thay sửa cấu hình |
| Gradle không tìm thấy processor artifact | Repository/version/credential sai | Kiểm tra dependencyResolutionManagement, repository và network |
| **ClassNotFoundException** khi chạy ứng dụng | Generated class chưa được compile/đóng gói, hoặc runtime API còn thiếu | Kiểm tra compile output, JAR/classpath, runtime dependencies |

### 12.1. Chuỗi kiểm tra có hệ thống

~~~text
Annotation processing không tạo kết quả?
           |
           v
1. Đang compile source set main hay test?
           |
           v
2. Source có annotation type hợp lệ trên compileClasspath?
           |
           v
3. Processor artifact nằm đúng annotationProcessor
   hoặc testAnnotationProcessor?
           |
           v
4. Processor JAR có META-INF/services đúng tên class?
           |
           v
5. @SupportedAnnotationTypes có khớp annotation FQCN?
           |
           v
6. Processor có được javac gọi, có exception/Messager lỗi?
           |
           v
7. Filer sinh generated source ở đâu?
           |
           v
8. Generated source đã compile thành class chưa?
           |
           v
9. Test/runtime classpath có chứa output/API cần dùng?
~~~

Lệnh điều tra:

~~~bash
./gradlew --version
./gradlew :processor:jar
./gradlew :app:compileJava --info
./gradlew :app:compileTestJava --info
./gradlew :app:dependencies --configuration annotationProcessor
./gradlew :app:dependencies --configuration testAnnotationProcessor
~~~

Tất cả tên project ở đây thuộc lab. Trong repo khác, thay theo **./gradlew projects** và đúng Gradle configuration.

## 13. An toàn khi sử dụng annotation processor

Annotation processor là mã Java **thực thi trong quá trình build**, thường được tải như dependency. Nó có thể truy cập file, môi trường và mạng trong phạm vi quyền của tiến trình compiler. Vì vậy processor từ nguồn không đáng tin có thể gây rủi ro chuỗi cung ứng ngay cả khi chương trình ứng dụng không bao giờ load processor ở runtime.

Thực hành an toàn:

1. Chỉ dùng artifact processor từ repository được phê duyệt; đặt policy ở **dependencyResolutionManagement** khi phù hợp.
2. Pin version hoặc dùng chiến lược version catalog/locking đã kiểm soát; review nâng processor giống review plugin build.
3. Bật **dependency verification** và kiểm tra checksum/signature theo chính sách.
4. Không đưa secret không cần thiết vào compiler environment.
5. Không cho processor ghi bừa sang source tree hoặc tải code bên ngoài không được kiểm soát.
6. Kiểm tra generated source khi processor mới được bổ sung hoặc nâng major version.
7. Phân biệt nguy cơ của **compileOnly annotation API** với **annotationProcessor executable code**: processor nguy hiểm hơn do được chạy trong build.

Không tự tắt TLS hoặc bỏ verification để một artifact processor tải được. Nếu Maven repository/proxy gây lỗi, sửa nguồn và credentials phù hợp.

## 14. Source set tùy chỉnh, Kotlin và Android

### 14.1. Source set khác main/test

Một dự án Java có thể tự tạo **integrationTest** source set. Java plugin cung cấp configuration liên quan tới source set đó, trong đó annotation processor path thường nhận từ **integrationTestAnnotationProcessor**.

Sơ đồ minh họa:

~~~text
src/integrationTest/java
    |
    +-- integrationTestCompileClasspath
    +-- integrationTestAnnotationProcessor
    |
    v
compileIntegrationTestJava
~~~

Đây là **sơ đồ ý tưởng**, không phải một build.gradle độc lập có sẵn task trong mọi repo. Bạn phải khai báo source set, configuration và test task theo cách plugin của dự án hỗ trợ. Đừng tự thêm dependency vào main annotationProcessor rồi giả định integrationTest compile được annotation.

### 14.2. Kotlin dùng cơ chế khác

Java source biên dịch bằng javac dùng **annotationProcessor**. Trong Kotlin JVM:

- **KAPT** cho phép chạy nhiều Java annotation processors trên Kotlin code theo plugin KAPT.
- **KSP** là API riêng dành cho symbol processing Kotlin; sử dụng processor KSP, không phải mọi Java JSR 269 processor đều chạy với KSP.
- Nếu module có Java và Kotlin, cần xem plugin JVM/Kotlin/Android tương ứng xử lý generated sources và classpaths thế nào.

Không dùng **annotationProcessor** của Java plugin như giải pháp chung thay cho **kapt** hoặc **ksp** khi annotation nằm trong **.kt**.

### 14.3. Android có variant-specific processor configurations

Android Gradle Plugin quản lý debug/release/flavor và các test variant theo cách riêng. Đối với app Android, **annotationProcessor** có thể tồn tại cho Java source, nhưng test configurations và task có thể khác Java plugin thuần. Đừng lấy demo **testAnnotationProcessor** của Java plugin rồi áp dụng máy móc cho Android unit tests/instrumentation tests.

## 15. Câu hỏi và bài tập thực hành

### Bài tập A: Processor chỉ chạy cho main

Trong lab, tạm bỏ **testAnnotationProcessor project(':processor')** khỏi app rồi chạy **:app:compileTestJava**. Vì sao **compileJava** vẫn hoạt động nhưng **TestGeneratedCheck** không biên dịch được? Khôi phục khai báo sau khi đọc lỗi.

### Bài tập B: Annotation API chỉ có compileOnly

Tạm bỏ **compileOnly project(':annotations')** nhưng vẫn giữ annotationProcessor. Biên dịch main và giải thích vì sao javac không còn nhìn thấy **demo.annotations.GenerateMarker** trong source. Đưa lại compileOnly sau thử nghiệm.

### Bài tập C: Service registration

Đổi nội dung file **META-INF/services/javax.annotation.processing.Processor** thành một tên class không tồn tại, rebuild processor JAR và chạy **compileJava**. Xác định lỗi phát hiện processor, sau đó sửa lại FQCN đúng.

### Bài tập D: Generated source phải có classpath đúng

Chạy **:app:compileJava**, tìm **ProductionExampleGenerated.java** và **.class**, rồi chạy **:app:run**. Giải thích cách Gradle khiến class generated được đóng gói cùng output chính mà không phải commit file generated.

### Bài tập E: Vòng xử lý

Thử thêm một annotated class mới trong **src/test/java**. Processor sẽ sinh thêm một **<Name>Generated** riêng trong test generated sources. Quan sát task compileTestJava; không kết luận rằng processor main đã xử lý test class.

### Bài tập F: Thiết kế dependency cho Lombok/MapStruct

Một module dùng Lombok ở main và test; hãy viết bốn dòng **compileOnly**, **annotationProcessor**, **testCompileOnly**, **testAnnotationProcessor**. Module khác dùng MapStruct annotation/API và processor ở main; hãy phân biệt artifact annotation/API và processor. Nêu lý do vì sao processor không nên mặc định nằm trên runtimeClasspath.

### Câu hỏi tự kiểm tra

1. Annotation có tự sinh code khi chỉ import annotation type không?
2. **annotationProcessor** và **testAnnotationProcessor** phục vụ hai task compile nào?
3. **compileOnly** khác **annotationProcessor** ở đâu?
4. Tại sao **testImplementation JUnit** không phải là **testAnnotationProcessor**?
5. Mục đích file **META-INF/services/javax.annotation.processing.Processor** là gì?
6. Khi annotation processor tạo Java source, nó nên dùng API nào và ở thời điểm nào?
7. Một source test chỉ dùng generated class đã được tạo ở main có luôn cần testAnnotationProcessor không?
8. Vì sao **-proc:none** làm generated classes biến mất?
9. Chỉ thêm processor JAR vào **implementation** có bảo đảm javac chạy processor không?
10. Gradle có thể đánh dấu một compile task **UP-TO-DATE** dù generated source vẫn tồn tại không?
11. Khi dùng Kotlin/KSP, có thể thay mọi configuration bằng annotationProcessor của Java plugin không?
12. Vì sao annotation processor dependency là một vấn đề bảo mật build?

**Đáp án gợi ý:** (1) không; (2) compileJava và compileTestJava; (3) annotation type compile classpath so với processor executable processor path; (4) JUnit là framework runtime/test; (5) service loader discovery; (6) Filer trong JSR 269 processing rounds; (7) không; (8) tắt annotation processing; (9) không; (10) có; (11) không; (12) processor chạy mã ở compile time và có quyền truy cập tài nguyên của compiler.

## 16. Checklist áp dụng trong dự án thật

- [ ] Xác nhận module có Java plugin/source set cần annotation processing.
- [ ] Xác nhận annotation API nằm trên **compileOnly/implementation** hoặc **testCompileOnly/testImplementation** phù hợp với nhu cầu runtime.
- [ ] Processor nằm đúng **annotationProcessor** cho main và **testAnnotationProcessor** cho test khi cần.
- [ ] Processor JAR có service registration hoặc một cơ chế chỉ định processor được hỗ trợ.
- [ ] Tên package của annotation khớp **@SupportedAnnotationTypes**.
- [ ] Generated source không bị ghi vào thư mục source được commit nếu không có lý do chính đáng.
- [ ] Generated class được compile vào output đúng source set, Java toolchain tương thích.
- [ ] Không có **-proc:none** hoặc override processor path vô tình tắt processor.
- [ ] Processor có lỗi rõ ràng khi không tạo được file hoặc annotation sai cấu trúc.
- [ ] Runtime classpath không chứa processor chỉ vì khai báo sai configuration.
- [ ] Test source cần processor được cấu hình độc lập, không dựa vào main processor path.
- [ ] IDE sync dùng Gradle đúng và CI chạy Wrapper có thể tái lập.
- [ ] Version processor được kiểm soát, artifact lấy từ repository được phép và được verification.
- [ ] Xem xét incremental annotation processing, cache và deterministic generation nếu build lớn.
- [ ] Nếu dùng Kotlin/Android, theo đúng tài liệu plugin cho từng source set/variant.

## 17. Tài liệu chính thức

- [Gradle — The Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Building Java & JVM Projects](https://docs.gradle.org/current/userguide/tutorial_java_projects.html)
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html)
- [Gradle — CompileOptions (annotationProcessorPath)](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html)
- [Gradle — Caching Java Projects](https://docs.gradle.org/current/userguide/caching_java_projects.html)
- [Gradle — Improve Build Performance](https://docs.gradle.org/current/userguide/performance.html)
- [Java SE 17 — Annotation Processing API (JSR 269)](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html)
- [Java SE 17 — Filer](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html)

**Kết luận:** **annotationProcessor** và **testAnnotationProcessor** không biểu thị những thư viện “cần khi chạy”, mà là hai **đường dẫn riêng để javac chạy annotation processor lúc biên dịch main và test source**. Annotation API đi vào compile classpath; processor implementation đi vào processor path; generated classes được compiler biên dịch tiếp. Khi hiểu ba lớp này và kiểm tra service registration/processing rounds, bạn sẽ sửa đúng lỗi code generation, tránh kéo processor vào runtime và giữ Gradle build dễ kiểm chứng, bảo trì và mở rộng.
