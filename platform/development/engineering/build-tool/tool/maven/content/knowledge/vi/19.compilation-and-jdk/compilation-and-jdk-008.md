# Annotation processor và cấu hình đường dẫn xử lý annotation trong Maven

## 1. Annotation processing là gì, chạy vào thời điểm nào?

**Annotation processing** là cơ chế để Java compiler gọi các **annotation processors** trong lúc biên dịch. Processor đọc cấu trúc chương trình thông qua API của Java compiler, tìm những phần tử được gắn annotation, rồi có thể **sinh source code**, **sinh resource**, **kiểm tra ràng buộc** hoặc báo lỗi biên dịch.

Ví dụ: khi gặp `@GenerateNote` trên một class, processor có thể tạo một class Java mới là `AppNote`. Trong cùng lượt biên dịch, `javac` có thể tiếp tục biên dịch class vừa được sinh. Những công cụ như **MapStruct**, bộ sinh JPA static metamodel hay một số thư viện tạo boilerplate tận dụng xử lý annotation theo các cách khác nhau.

Cần phân biệt:

- **Annotation** là thông tin gắn vào class, method, field... (ví dụ `@Override`, `@Deprecated` hoặc annotation riêng do dự án định nghĩa).
- **Annotation processor** là code **thực thi trong lúc compile** để xử lý annotation. Bản thân một annotation không bảo đảm có processor.
- **Generated source** là tệp `.java` được tạo ra bởi processor, thường ở `target/generated-sources/annotations`.
- **Generated class** là `.class` được compiler tạo từ Java source thông thường hoặc generated source.
- **Runtime reflection** là code quan sát annotation khi chương trình đang chạy; khác annotation processing tại compile time.

Không phải mọi annotation đều liên quan annotation processor. Ví dụ `@Override` được compiler kiểm tra bằng ngữ nghĩa Java, không có nghĩa phải tải một JAR processor. **RetentionPolicy.SOURCE**, **CLASS** hoặc **RUNTIME** mô tả annotation có mặt đến giai đoạn nào; chúng không phải công tắc kích hoạt Maven processor.

Annotation processing có thể ảnh hưởng tính đúng đắn của build: khi thiếu processor, compiler có thể không thấy class được sinh và báo **cannot find symbol**, hoặc chương trình vẫn biên dịch nhưng thiếu validation/generator cần thiết. Vì vậy cần cấu hình minh bạch **processor nào được phép chạy** và **processor được tìm ở đâu**.

## 2. Cơ chế hoạt động từ Maven tới javac

Với project Java Maven có `packaging=jar`, lifecycle mặc định thường gọi `maven-compiler-plugin:compile` ở phase `compile` và `maven-compiler-plugin:testCompile` ở phase `test-compile`. Compiler Plugin chuẩn bị source roots, classpath, compiler options và, khi được cấu hình, đường dẫn cho annotation processors.

Sơ đồ:

~~~text
pom.xml / parent POM / active profiles
    |
    | Maven Compiler Plugin (compile goal)
    v
[Compiler configuration]
    |
    +-- main sources: src/main/java
    |
    +-- compile classpath: các types/dependencies mà code tham chiếu
    |
    +-- processor path: JARs chứa annotation processors
    |                    cùng transitive dependencies của processor
    |
    +-- processor selection: tên processor được gọi
    |
    +-- processor options: -Akey=value
    v
[javac annotation processing rounds]
    |
    +-- đọc annotations / Element / TypeMirror
    +-- sinh .java hoặc resource bằng Filer
    +-- có thể phát hiện source mới và chạy round tiếp theo
    v
[Compile Java source + generated source]
    |
    +-- target/classes/*.class
    +-- target/generated-sources/annotations/*.java
    v
[package/test/runtime theo lifecycle]
~~~

**Annotation processor là build-time code**. Một processor bình thường không cần được đóng gói vào runtime classpath của ứng dụng chỉ vì nó đã chạy khi biên dịch.

### 2.1. Annotation processing có nhiều round

API `javax.annotation.processing` cho processor đọc các phần tử của một **round** qua `RoundEnvironment`. Processor có thể tạo source mới; javac sẽ xét các source sinh ra trong round sau. Khi không còn source mới, một round cuối báo `processingOver()`.

Điều này giải thích vì sao:

- Một processor có thể sinh file mà một processor khác tiếp tục xử lý.
- Processor không nên tạo lại cùng tên file qua nhiều rounds; `Filer` có thể báo `FilerException`.
- Một processor được thiết kế tốt phải cẩn thận với **side effects** và tình huống mã nguồn không đổi nhưng compiler có thêm lượt xử lý.
- File sinh ra phải có tên package/class hợp lệ và được đưa vào output phù hợp.

### 2.2. Hai mục tiêu khác nhau: đọc annotation và sinh mã

Có processor chỉ kiểm tra quy tắc và gọi `Messager.printMessage(ERROR, ...)` để fail compile. Có processor tạo `JavaFileObject` qua `Filer.createSourceFile(...)`. Có processor tạo resource thông qua `createResource(...)`.

**Không phải processor nào cũng tạo Java source**, và không phải thư viện annotation nào cũng cung cấp processor. Khi chẩn đoán lỗi, hãy xác định công cụ bạn dùng **thật sự phải sinh file gì**.

## 3. Compile classpath khác annotation processor path

Đây là ranh giới quan trọng nhất của chủ đề.

| Đường dẫn | Ai dùng? | Chứa gì? |
| --- | --- | --- |
| **Compile classpath** | Compiler để resolve Java types mà source tham chiếu | API classes, annotations, libraries ứng dụng |
| **Annotation processor path** | Compiler để tìm và tải code processor | Processor implementations và dependencies của chúng |
| **Module path** | Java compiler/module system cho modular code | Modules theo JPMS |
| **Processor module path** | `javac` tìm modular processors nếu cấu hình | Processor modules, không đồng nghĩa compile module path |
| **Runtime classpath** | JVM chạy ứng dụng sau khi build | Code ứng dụng và runtime dependencies, thường không cần processor |

Nếu ứng dụng viết:

~~~java
import com.example.apt.GenerateNote;

@GenerateNote
public final class App {
}
~~~

thì compiler phải **nhìn thấy class annotation `GenerateNote`** trên compile classpath hoặc module path phù hợp. **Chỉ đặt processor vào annotationProcessorPaths không tự làm annotation API xuất hiện trong source compile classpath** nếu API ấy chưa có ở chỗ cần thiết.

Ngược lại, nếu project chỉ khai báo processor như một dependency compile mà không có cấu hình processor path/selection rõ ràng, chuyện processor có thực sự được phát hiện và chạy còn phụ thuộc **javac version, service registration và options**. Từ JDK 23, javac không còn mặc định quét classpath để chạy processor khi không có yêu cầu annotation-processing tường minh.

### Ba trường hợp cần nhớ

**Trường hợp A — Chỉ cần dùng annotation API:** khai báo artifact chứa annotation type trong `<dependencies>`, scope thích hợp.

**Trường hợp B — Cần chạy implementation xử lý annotation:** đặt implementation và thư viện phụ thuộc của nó vào **processor path**; nêu processors được chọn nếu có thể.

**Trường hợp C — Cần cả hai:** annotation API và processor JAR thường là **hai artifacts khác nhau** trong dự án thực tế. Ví dụ MapStruct có một artifact cung cấp API annotations, một artifact cung cấp processor. Bài thực hành phía dưới dùng **chung một JAR cho hai vai trò nhằm giữ demo nhỏ**, đồng thời khai báo nó ở hai nơi với hai mục đích khác nhau.

## 4. Cấu hình Maven Compiler Plugin 3.x: annotationProcessorPaths

Với **Maven 3** và **maven-compiler-plugin 3.x**, cơ chế điển hình là:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
        <annotationProcessorPaths>
            <path>
                <groupId>org.example</groupId>
                <artifactId>example-processor</artifactId>
                <version>1.2.3</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

Đây là **mảnh plugin** đặt trong `<build><plugins>...` của POM, không phải POM độc lập; `org.example:example-processor:1.2.3` là tọa độ minh họa.

**Ý nghĩa chính xác:**

- `<annotationProcessorPaths>` tạo **processor classpath** từ các Maven artifact coordinates.
- Mỗi `<path>` có groupId/artifactId/version và có thể có classifier/type phù hợp.
- Compiler Plugin giải quyết **transitive dependencies** của processor path (với quy tắc phiên bản và exclusions).
- Khi processor path được khai báo, compiler tìm processors trong **các phần tử của processor path** thay vì tự mở rộng tới mọi dependency compile.
- Một JAR processor phải tồn tại trong repository có thể resolve, local hoặc remote.
- Plugin 3.x không dùng `<type>classpath-processor</type>` như cơ chế thay thế của Compiler Plugin 4.x trong Maven 4.

**Ưu điểm:** tách build tooling khỏi dependencies của ứng dụng và giới hạn những JAR có thể được dùng để tìm processor. Nếu ứng dụng không tham chiếu processor API ở runtime, không nên thêm processor implementation vào runtime dependency một cách vô tình.

## 5. annotationProcessors: chọn đích danh implementation được phép chạy

`annotationProcessorPaths` nói **ở đâu** để tìm processors; còn `<annotationProcessors>` nói **processor classes nào** phải chạy.

~~~xml
<configuration>
    <annotationProcessorPaths>
        <path>
            <groupId>org.example</groupId>
            <artifactId>example-processor</artifactId>
            <version>1.2.3</version>
        </path>
    </annotationProcessorPaths>
    <annotationProcessors>
        <annotationProcessor>org.example.processor.ExampleProcessor</annotationProcessor>
    </annotationProcessors>
</configuration>
~~~

Hai phần trên là **bổ sung cho nhau**:

- `annotationProcessorPaths`: cấp các JAR/dependencies để class loader tìm implementation.
- `annotationProcessors`: chỉ định fully qualified class name, tương ứng javac `-processor`.
- Processor class phải implement `javax.annotation.processing.Processor`, thường thông qua `AbstractProcessor`.
- Nếu tên processor sai hoặc class không có trên processor path, compiler có thể báo **Annotation processor ... not found**.
- Khi chỉ định danh sách bằng `-processor`, javac **không phụ thuộc vào service-based automatic discovery** để chọn implementation.
- Cấu hình explicit giúp tránh thực thi processor không mong muốn trong những JAR khác.

### Service-based discovery

Một processor JAR cũng có thể công bố service provider file:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung là tên class đầy đủ, ví dụ:

~~~text
org.example.processor.ExampleProcessor
~~~

`javac` có thể sử dụng service registration khi auto-discovery được bật và processor path thích hợp. **Chỉ có service file không bảo đảm processor sẽ chạy trên JDK 23+** nếu command line không có lựa chọn annotation processing phù hợp.

Trong một project **đang tự biên dịch processor của nó**, service file có thể gây lỗi nếu compiler cố load processor từ JAR/class chưa build xong. Đó là một lý do bài thực hành chọn cách **explicit annotationProcessors**, và module processor của ví dụ không cần service registration.

## 6. -proc:none, -proc:only và -proc:full

`javac` có chính sách về annotation processing. Maven Compiler Plugin có tham số `<proc>` ánh xạ thành `-proc:`:

| Giá trị | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| **none** | Biên dịch Java, **không** chạy annotation processors | Module không cần processor; bước compile processor implementation |
| **only** | Chỉ annotation processing, **không** biên dịch class files thông thường | Một số workflow tách riêng bước generate/validate |
| **full** | Chạy annotation processing **và** biên dịch | Workflow muốn cả generate và compile |

Ví dụ:

~~~xml
<configuration>
    <proc>none</proc>
</configuration>
~~~

**Chú ý về phiên bản JDK:** từ **JDK 23**, javac **không còn tự động kích hoạt annotation processing chỉ vì một processor tình cờ nằm trên compile classpath**. Cần cấu hình tường minh như `-processor`, processor path/module path hoặc `-proc` phù hợp. Ở JDK 17, việc tìm processors trên classpath khi không chỉ định có thể từng xảy ra, nhưng không nên dựa vào cơ chế ngầm.

Tham số `-proc:full` được đưa vào javac muộn hơn những JDK 17 bản đầu; nó đã được backport vào nhiều bản JDK 17 update mới (ví dụ 17.0.11). **Không nên sao chép `<proc>full</proc>` vô điều kiện vào project chạy một bản JDK 17 cũ mà không kiểm tra**, vì compiler có thể không hiểu giá trị đó. Demo Java 17 của bài dùng **explicit annotationProcessors** và không cần khai báo `<proc>full</proc>`.

**Bảo mật:** chỉ đặt `proc=full` hoặc `only` mà không kiểm soát processors có thể kích hoạt các processor được phát hiện từ classpath. Processor là code thực thi với quyền build. Vì thế tài liệu Maven khuyến nghị **liệt kê rõ processors dự kiến** hoặc dùng processor dependency types mới trong hệ tương thích.

### -proc:only không phải cách build Java app hoàn chỉnh

Nếu bật `<proc>only</proc>`, tool có thể sinh Java source nhưng **không sinh toàn bộ `.class`** cho ứng dụng. Đừng mong `mvn package` với `proc=only` mà tự có JAR chạy được, trừ khi pipeline còn bước compile riêng được cấu hình cẩn thận. Với đa số ứng dụng, dùng annotation processing cùng compile bình thường đơn giản hơn.

## 7. Compiler options -A: truyền tham số cho annotation processor

`javac` hỗ trợ options dạng:

~~~text
-Akey=value
~~~

Processor đọc bằng:

~~~java
processingEnv.getOptions().get("key");
~~~

Trong Maven Compiler Plugin 3.x:

~~~xml
<compilerArgs>
    <arg>-Anote.message=READY</arg>
</compilerArgs>
~~~

Đây là **compiler argument**, không phải Maven user property hay Java runtime system property. Tương tự:

- `-Anote.message=READY` → processor đọc `processingEnv.getOptions()`.
- `mvn -Dnote.message=READY ...` → Maven user property, **không tự là -A option** nếu POM không map.
- `-Dnote.message=READY` trong `MAVEN_OPTS` → system property của JVM chạy Maven.
- `argLine` của Surefire → tham số JVM kiểm thử, **không phải javac processor option**.

Processor tốt nên khai báo các option được hỗ trợ qua `@SupportedOptions` hoặc override `getSupportedOptions()`, kiểm tra kiểu/giá trị và cung cấp diagnostic hữu ích nếu sai. Tránh đưa secret vào `-A` bởi compiler logs, generated sources hoặc artifact output có thể phơi bày dữ liệu.

Ví dụ map một Maven property vào processor option, nếu thật sự muốn điều khiển từ CLI:

~~~xml
<properties>
    <note.message>READY</note.message>
</properties>
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <compilerArgs>
                    <arg>-Anote.message=${note.message}</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Phần này là **mảnh POM**, phải kết hợp với processor path/selection thật và main POM. Khi đó `mvn -Dnote.message=CI ...` có thể được Maven nội suy thành option `-Anote.message=CI`. **Không phải mọi property `-D` tự được javac chuyển thành `-A`.**

## 8. generatedSourcesDirectory và output class

Maven Compiler Plugin 3.x có tham số `<generatedSourcesDirectory>`. Giá trị mặc định thường là:

~~~text
target/generated-sources/annotations
~~~

Đây là nơi đặt **Java source do annotation processors sinh ra**. Các `.class` cuối thường ở:

~~~text
target/classes
~~~

Ví dụ:

~~~text
target/
├── generated-sources/
│   └── annotations/
│       └── com/example/app/AppNote.java
└── classes/
    └── com/example/app/
        ├── App.class
        └── AppNote.class
~~~

Thư mục generated source **không phải source tree do developer quản lý**. Không nên sửa thủ công `target/generated-sources/annotations` rồi commit; lần clean hoặc compilation tiếp theo có thể xóa/tái tạo.

Nếu cần đổi output:

~~~xml
<configuration>
    <generatedSourcesDirectory>${project.build.directory}/generated-sources/annotations</generatedSourcesDirectory>
</configuration>
~~~

Đây chính là giá trị mặc định minh họa, không phải bắt buộc khai báo. Compiler Plugin sử dụng đường dẫn generated sources khi chạy annotation processing; generated Java được javac xem xét trong vòng compile phù hợp. **Thông thường không cần thêm `build-helper:add-source` cho chính output mặc định của javac annotation processing**. Với tool sinh mã chạy ở plugin khác trước compile, cơ chế đăng ký source roots có thể khác và phải đọc tài liệu của generator đó.

Cần phân biệt **file `.java` được sinh**, **file `.class` sau compiler** và **file resource** được `Filer` sinh. Tham số generatedSourcesDirectory liên quan output Java source; không dùng nó như đường dẫn tùy tiện để đặt mọi loại file của dự án.

## 9. Demo hoàn chỉnh Java 17: một processor JAR và một ứng dụng dùng nó

Bài thực hành tạo **hai Maven projects độc lập** để tránh vòng lặp tự biên dịch processor và tránh giả định thứ tự reactor khi processor JAR chưa được build.

- **Project `note-processor`**: công bố annotation `@GenerateNote` và `NoteProcessor`, phiên bản `1.0.0`, rồi `mvn install` vào local Maven repository.
- **Project `note-consumer`**: khai báo `note-processor` cho annotation API ở compile classpath với scope `provided`, **đồng thời** liệt kê cùng artifact trong `<annotationProcessorPaths>` để compiler chạy processor. Đây là sự trùng artifact **có chủ đích vì demo gộp API + processor vào một JAR**, không phải mẫu kiến trúc bắt buộc.
- Processor tìm `@GenerateNote` trên class `App`, đọc `-Anote.message=READY`, tạo Java source `AppNote.java`.
- App chạy `AppNote.message()` và in đúng `Generated: READY`.

Trong sản phẩm thực tế, annotation API và processor implementation thường nên tách thành **hai artifacts**. Khi đó ứng dụng phụ thuộc annotation API ở compile path, còn processor implementation chỉ nằm trên processor path.

### 9.1. Cấu trúc hai projects

~~~text
apt-workshop/
├── note-processor/
│   ├── pom.xml
│   └── src/main/java/com/example/apt/
│       ├── GenerateNote.java
│       └── NoteProcessor.java
└── note-consumer/
    ├── pom.xml
    └── src/main/java/com/example/app/
        └── App.java
~~~

Lưu ý các thư mục trên là **hai project Maven độc lập**. Không có parent `pom.xml` ở `apt-workshop/`; phải chạy lệnh Maven ở đúng thư mục của từng project.

### 9.2. note-processor/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.apt</groupId>
    <artifactId>note-processor</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <proc>none</proc>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Đọc POM này:**

- `release=17` biên dịch processor bằng Java 17.
- `<proc>none</proc>` bảo đảm **khi build chính project chứa implementation processor**, compiler không cố chạy annotation processors trong project này.
- Không có external Java dependencies: `javax.annotation.processing`, `javax.lang.model` và `javax.tools` là Java compiler APIs từ JDK.
- **Không tạo service registration file** trong demo: consumer sẽ chọn processor bằng fully qualified class name.
- Sau `mvn install`, Maven local repository có JAR `com.example.apt:note-processor:1.0.0`.

### 9.3. Annotation: GenerateNote.java

Tạo **note-processor/src/main/java/com/example/apt/GenerateNote.java**:

~~~java
package com.example.apt;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateNote {
}
~~~

`@Target(TYPE)` giới hạn annotation dùng cho kiểu; processor mẫu bên dưới chỉ chấp nhận class. `RetentionPolicy.SOURCE` là đủ vì processor đọc annotation khi compile; runtime không cần lưu nó để reflection.

### 9.4. Processor: NoteProcessor.java

Tạo **note-processor/src/main/java/com/example/apt/NoteProcessor.java**:

~~~java
package com.example.apt;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedOptions;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("com.example.apt.GenerateNote")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
@SupportedOptions("note.message")
public final class NoteProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        String message =
                processingEnv.getOptions().getOrDefault("note.message", "READY");

        if (!message.matches("[A-Za-z0-9_]+")) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "note.message must contain only letters, numbers or _");
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateNote.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateNote must be placed on a class",
                        element);
                continue;
            }

            TypeElement target = (TypeElement) element;

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(target).getQualifiedName().toString();
            String generatedName = target.getSimpleName() + "Note";
            String qualifiedName = pkg.isEmpty()
                    ? generatedName
                    : pkg + "." + generatedName;

            try {
                JavaFileObject source = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, target);

                try (Writer writer = source.openWriter()) {
                    if (!pkg.isEmpty()) {
                        writer.write("package " + pkg + ";\n\n");
                    }
                    writer.write("public final class "
                            + generatedName + " {\n");
                    writer.write("  private " + generatedName + "() {}\n");
                    writer.write("  public static String message() {\n");
                    writer.write("    return \"Generated: "
                            + message + "\";\n");
                    writer.write("  }\n");
                    writer.write("}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + qualifiedName
                                + ": " + ex.getMessage(),
                        element);
            }
        }
        return true;
    }
}
~~~

**Giải thích API:**

- `@SupportedAnnotationTypes` chỉ định loại annotation mà processor nhận.
- `@SupportedSourceVersion` mô tả Java source version processor hỗ trợ.
- `@SupportedOptions` cho phép compiler biết các `-A` options processor hiểu.
- `RoundEnvironment.getElementsAnnotatedWith(...)` lấy các phần tử có annotation trong round.
- `ElementKind.CLASS` giúp từ chối trường hợp không phải class.
- `Filer.createSourceFile` tạo Java source mới và liên kết originating element.
- `Messager.printMessage(ERROR, ...)` làm compiler báo lỗi khi input không hợp lệ.
- `processingOver()` giúp không tạo lại file ở final round.
- Option `note.message` được giới hạn `[A-Za-z0-9_]+` để tránh chèn ký tự lạ vào Java string literal được sinh. Với processor thực tế nhận chuỗi tùy ý, phải escape Java source đầy đủ chứ không dùng cách nối chuỗi trực tiếp này.

Đây là implementation **tối giản có thể biên dịch**, không phải bộ generator production. Trong dự án lớn, cần kiểm tra duplicate file names, compatibility với incremental compilation, option validation chi tiết, source version và xử lý multi-round nghiêm ngặt hơn.

### 9.5. Build và install processor

Trên Linux/macOS, từ thư mục `apt-workshop`:

~~~bash
cd note-processor
mvn -B clean install
cd ..
~~~

Trên Windows PowerShell cũng có thể dùng cùng các lệnh `cd` và `mvn`; `-B` bật batch mode, không ảnh hưởng annotation-processing logic.

Sau `install`, local Maven repository mặc định chứa những tệp chính:

~~~text
~/.m2/repository/com/example/apt/note-processor/1.0.0/
  note-processor-1.0.0.pom
  note-processor-1.0.0.jar
~~~

Nếu dùng custom local repository, đường dẫn thực tế sẽ khác. **Không chuyển sang consumer trước khi install processor thành công**; nếu không, consumer không resolve được artifact giả định của demo.

### 9.6. note-consumer/pom.xml

Tạo **note-consumer/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.app</groupId>
    <artifactId>note-consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.example.apt</groupId>
            <artifactId>note-processor</artifactId>
            <version>1.0.0</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>

                    <annotationProcessorPaths>
                        <path>
                            <groupId>com.example.apt</groupId>
                            <artifactId>note-processor</artifactId>
                            <version>1.0.0</version>
                        </path>
                    </annotationProcessorPaths>

                    <annotationProcessors>
                        <annotationProcessor>com.example.apt.NoteProcessor</annotationProcessor>
                    </annotationProcessors>

                    <compilerArgs>
                        <arg>-Anote.message=READY</arg>
                    </compilerArgs>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Tại sao khai báo `note-processor` hai nơi?**

- Ở `<dependencies>` với scope `provided`, JAR này **cung cấp annotation class `@GenerateNote` để source App biên dịch**. Vì annotation có SOURCE retention, demo runtime không cần processor JAR.
- Ở `<annotationProcessorPaths>`, cùng JAR cung cấp **processor implementation** cho compiler gọi khi compile. Đây là đường dẫn build-tool, không đơn thuần là runtime dependency.
- `<annotationProcessors>` chọn `com.example.apt.NoteProcessor` rõ ràng, không dựa vào service discovery hay implicit classpath scanning.
- `<compilerArgs>` truyền `-Anote.message=READY`, đọc qua `processingEnv.getOptions()`.
- `<release>17</release>` đặt Java release; nó **không tự kích hoạt** annotation processor.
- Không có `<proc>full</proc>` để tránh đòi hỏi cụ thể về các bản JDK 17 update cũ; explicit processor selection đã yêu cầu xử lý annotation.

**Chính sách production tốt hơn:** tạo artifact annotation API riêng (chứa `@GenerateNote`) và artifact processor riêng (chứa `NoteProcessor`); consumer đưa API vào compile dependencies và processor implementation **chỉ vào processor path**, thay vì đưa implementation vào compile classpath như demo gộp.

### 9.7. Source class sử dụng generated class

Tạo **note-consumer/src/main/java/com/example/app/App.java**:

~~~java
package com.example.app;

import com.example.apt.GenerateNote;

@GenerateNote
public final class App {

    private App() {
    }

    public static void main(String[] args) {
        System.out.println(AppNote.message());
    }
}
~~~

`AppNote` **chưa có trong source tree** lúc mới tạo. Đây không phải lỗi thiết kế: processor sẽ sinh class ấy trong quá trình compile. Nếu processor không chạy, compiler báo không tìm thấy `AppNote`.

### 9.8. Chạy consumer và xác minh file được sinh

Từ thư mục `apt-workshop` sau khi đã install processor:

~~~bash
cd note-consumer
mvn -B clean package
java -cp target/classes com.example.app.App
~~~

**Stdout chính xác của lệnh Java cuối** khi build thành công:

~~~text
Generated: READY
~~~

Thư mục generated source dự kiến có:

~~~text
target/generated-sources/annotations/com/example/app/AppNote.java
~~~

Code được sinh tương đương:

~~~java
package com.example.app;

public final class AppNote {
    private AppNote() {}

    public static String message() {
        return "Generated: READY";
    }
}
~~~

Trong `target/classes/` dự kiến có:

~~~text
com/example/app/App.class
com/example/app/AppNote.class
~~~

Bạn có thể kiểm tra các class:

~~~bash
jar tf target/note-consumer-1.0.0.jar
~~~

JAR phải chứa `com/example/app/App.class` và `com/example/app/AppNote.class` nếu packaging bình thường. Kết quả `jar tf` còn có entries khác; danh sách trên không phải toàn bộ stdout.

POM demo không cấu hình `Main-Class` trong manifest, nên lệnh `java -cp target/classes com.example.app.App` là lựa chọn rõ ràng. Nếu muốn chạy từ main JAR, vì generated class chỉ dùng Java chuẩn và annotation có SOURCE retention:

~~~bash
java -cp target/note-consumer-1.0.0.jar com.example.app.App
~~~

lệnh này cũng dự kiến in đúng `Generated: READY`. Trong demo không cần mang theo JAR processor ở runtime.

### 9.9. Thử bỏ processor path để thấy lỗi

Chỉ thực hiện trên **bản sao project demo**. Nếu bỏ cả `<annotationProcessorPaths>` và `<annotationProcessors>` và đảm bảo annotation processor không tự chạy từ classpath (ví dụ bằng `<proc>none</proc>`), build sẽ không sinh `AppNote`. Khi source vẫn tham chiếu `AppNote.message()`, compiler có thể báo dạng:

~~~text
cannot find symbol
  symbol:   variable AppNote
  location: class com.example.app.App
~~~

Văn bản diagnostic thay đổi theo JDK/Compiler Plugin; đây chỉ là **dạng lỗi minh họa**, không phải stdout cố định. Với JDK 23+, việc không bật annotation processing là nguyên nhân thường gặp khi một project từng dựa vào quét classpath ngầm.

Để sửa, khôi phục processor path, processor class selection và option như phần 9.6. Sau đó chạy:

~~~bash
mvn -B clean package
~~~

Dùng `clean` để tránh generated source/class cũ trong `target/` che giấu sự cố.

## 10. Ví dụ thực tế: annotation API và processor implementation tách riêng

Với những thư viện tạo mã phổ biến, cách tách trách nhiệm rõ ràng là:

~~~text
compile classpath:
  API annotation types mà source Java import

processor path:
  processor implementation + dependencies của nó

runtime classpath:
  những libraries thật sự cần khi ứng dụng chạy
~~~

Ví dụ MapStruct (mảnh POM mô tả vị trí, **không phải ví dụ runnable độc lập**, version phải được chọn nhất quán theo project):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.mapstruct</groupId>
        <artifactId>mapstruct</artifactId>
        <version>1.6.3</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.mapstruct</groupId>
                        <artifactId>mapstruct-processor</artifactId>
                        <version>1.6.3</version>
                    </path>
                </annotationProcessorPaths>
                <annotationProcessors>
                    <annotationProcessor>org.mapstruct.ap.MappingProcessor</annotationProcessor>
                </annotationProcessors>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **hai phần POM** phải được gộp vào cấu trúc `<project>` hợp lệ; không chạy nguyên mảnh XML như một file độc lập. Ví dụ minh họa sự phân chia **`mapstruct` API vs `mapstruct-processor` build tool**, không bao gồm mapper interface hoặc business logic cụ thể.

Với Lombok, JPA metamodel generators và các công cụ tương tự, mô hình đường dẫn cũng quan trọng nhưng yêu cầu module-access, version compatibility và processing options có thể khác. **Không copy nguyên cấu hình MapStruct sang một processor khác** mà không đọc hướng dẫn chính thức.

## 11. Maven 4 và Maven Compiler Plugin 4.x: processor dependency types

Đây là thay đổi quan trọng giữa hai thế hệ:

### Maven 3 + Compiler Plugin 3.x

Thông thường dùng:

~~~xml
<annotationProcessorPaths>
    <path>
        <groupId>com.example.apt</groupId>
        <artifactId>note-processor</artifactId>
        <version>1.0.0</version>
    </path>
</annotationProcessorPaths>
~~~

### Maven 4 + Compiler Plugin 4.x

Các version Compiler Plugin 4.x hỗ trợ khai báo processor như **dependency với type đặc biệt**:

~~~xml
<dependency>
    <groupId>com.example.apt</groupId>
    <artifactId>note-processor</artifactId>
    <version>1.0.0</version>
    <type>classpath-processor</type>
</dependency>
~~~

Các type được tài liệu Maven 4 mô tả:

| Type | Ý nghĩa |
| --- | --- |
| **processor** | Processor dependency, plugin cố xác định classpath/module path |
| **classpath-processor** | Cố định processor trên **processor classpath** |
| **modular-processor** | Cố định processor trên **processor module path** |

**Khuyến nghị:** nếu biết processor thuộc classpath hay module path, dùng type rõ ràng thay vì `processor` và phụ thuộc heuristics. Đối với processor kiểu classpath như demo, `classpath-processor` minh bạch hơn.

`annotationProcessorPaths` trong Compiler Plugin 4.x được đánh dấu **deprecated**, có kế hoạch loại bỏ ở phiên bản tương lai; thay thế bằng typed processor dependencies khi dùng đúng tổ hợp Maven 4 + Compiler Plugin 4.x. **Không đưa `classpath-processor` vào Maven 3/Compiler Plugin 3.x rồi cho rằng nó có cùng behavior.**

Khi nâng Maven 3 lên 4, cần kiểm tra:

1. Version Maven Core và Compiler Plugin có hỗ trợ typed processor dependencies.
2. API annotation có nằm trên compile path khi source cần import không.
3. Processor implementation được khai báo trên processor path hay module path đúng.
4. Chính sách annotation processing của JDK hiện tại.
5. Compiler/test executions và generated sources có cùng output như trước.
6. Plugin khác có hiểu artifact types mới hay không; không giả định mọi plugin đều đã hỗ trợ.

## 12. JPMS: processor classpath không phải processor module path

Nếu project có `module-info.java`, một số dependencies được đặt trên **module path**. Annotation processors cũng có thể được đưa lên **processor module path** khi chúng được thiết kế như Java modules.

Phân biệt:

- `javac -classpath`: types cho application compile.
- `javac --module-path`: modules cho code đang biên dịch.
- `javac -processorpath` hoặc `--processor-path`: classpath để tìm/load processors.
- `javac --processor-module-path`: module path để tìm/load modular processors.

Không nên chọn `modular-processor` chỉ vì **ứng dụng** dùng `module-info.java`: processor JAR phải tương thích cơ chế module path/registration của nó. Ngược lại, một processor không modular thường được dùng thuận tiện trên processor classpath ngay cả khi ứng dụng có mô hình module.

Một số frameworks dựa vào compiler internals hoặc reflection có thể cần flags phù hợp với JDK/module access. **Không mở rộng module access bằng `--add-opens` một cách tùy tiện** chỉ để che lỗi version không tương thích; trước hết kiểm tra JDK, processor version và hướng dẫn chính thức.

## 13. annotationProcessorPathsUseDepMgmt và transitive processor dependencies

Maven Compiler Plugin 3.13.0 hỗ trợ cấu hình:

~~~xml
<annotationProcessorPathsUseDepMgmt>true</annotationProcessorPathsUseDepMgmt>
~~~

Cờ này **ảnh hưởng cách dependencyManagement được áp dụng cho transitive dependencies** của annotationProcessorPaths. Nó **không phải công tắc bật/tắt toàn bộ dependencyManagement**, và không làm annotation processors tự xuất hiện ở compile classpath.

Phân biệt hai trường hợp:

1. **Top-level processor path version** có thể lấy từ dependencyManagement khi cấu hình/plugin hỗ trợ; đó là việc quản lý version của chính artifact được liệt kê.
2. **Transitive dependencies của processor** có thể chịu lựa chọn management khác; cờ `annotationProcessorPathsUseDepMgmt` của Compiler Plugin 3.x điều khiển khía cạnh này.

Nếu một processor gặp `ClassNotFoundException` hoặc `NoSuchMethodError`, nguyên nhân có thể do **xung đột phiên bản trong processor path**, không phải trong compile dependency tree của ứng dụng. Hãy kiểm tra resolved processor artifacts và plugin configuration tương ứng; không chỉ dựa vào `mvn dependency:tree` của application classpath để khẳng định processor dependencies đúng.

Compiler Plugin 3.x còn cho phép **exclusions** trên path entries từ phiên bản phù hợp (ví dụ 3.13.0 hỗ trợ). Chỉ loại transitive dependency khi đã có bằng chứng xung đột; loại nhầm thư viện processor cần có sẽ làm build fail.

## 14. Main compile và test compile có thể cần processors khác nhau

Với `packaging=jar`:

- Phase **compile** chạy `compiler:compile` cho `src/main/java`.
- Phase **test-compile** chạy `compiler:testCompile` cho `src/test/java`, với classpath và output test riêng.

Cấu hình **ở cấp plugin** có thể tác động tới nhiều goals của Maven Compiler Plugin. Nếu processor chỉ nên chạy cho main sources hoặc chỉ nên chạy cho test sources, cần cấu hình theo **execution ID** phù hợp:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <executions>
        <execution>
            <id>default-compile</id>
            <configuration>
                <annotationProcessors>
                    <annotationProcessor>com.example.apt.NoteProcessor</annotationProcessor>
                </annotationProcessors>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.example.apt</groupId>
                        <artifactId>note-processor</artifactId>
                        <version>1.0.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **mảnh plugin**; mục đích minh họa cấu hình cho implied execution `default-compile` thay vì tạo một execution mới gây compile trùng. Cấu hình `default-testCompile` riêng nếu cần xử lý annotations ở test sources bằng một processor khác.

Không thêm execution `compiler:compile` mới chỉ để truyền annotationProcessorPaths: `jar` packaging đã bind compile goal mặc định. Khi có hai compiler executions cùng phase, annotation processor có thể chạy lặp hoặc tạo file trùng.

## 15. Java source generation khác những cơ chế tạo code khác

Annotation processing chỉ là một loại code generation. Không nên nhầm với:

- **OpenAPI/Protobuf/ANTLR plugins**: thường generate Java từ schema ngoài, gắn vào phase như `generate-sources`; không nhất thiết dùng JSR 269 annotation processing.
- **Java annotation processors**: chạy trong javac compile với annotation model API, thường generated sources ở `target/generated-sources/annotations`.
- **Runtime proxies/code generation**: xảy ra khi ứng dụng chạy, không phải lúc Maven compiler xử lý annotation.
- **Bytecode instrumentation**: một số tool sửa class bytes, có thể dùng Java agent hoặc build plugin khác, không nhất thiết sinh Java source.
- **Javadoc tags/processors**: xử lý docs, không đồng nghĩa `javax.annotation.processing.Processor`.

Nếu một build có nhiều generator, phải xác định rõ **producer/consumer order**. Một generator từ schema cần tạo `.java` **trước compile**; annotation processor lại có thể sinh Java **trong compile rounds**.

## 16. Incremental build, clean build và stale generated sources

Generated code có thể tồn tại trong `target/` từ lượt build trước. Một ví dụ đáng lo:

1. Build có processor chạy thành công và sinh `AppNote.java`.
2. Developer vô tình tắt annotation processing.
3. `target/classes/AppNote.class` vẫn còn từ build cũ.
4. Lượt `mvn compile` không clean có thể trông thành công trong một số trường hợp dù cấu hình processor mới đã hỏng.

Vì vậy khi điều tra processor:

~~~bash
mvn -B clean compile
~~~

rồi kiểm tra **generated source mới**, compiler logs và actual `.class` output. **Clean build là phép thử tốt để phát hiện generated outputs cũ che khuất vấn đề**.

Maven Compiler Plugin có cơ chế incrementalCompilation, nhưng annotation processors có thể sinh file dựa trên nhiều source/classpath elements hoặc aggregate toàn project. Đừng mặc định mọi processor hỗ trợ incremental compilation chính xác. Một số build tools/IDEs có các annotation processor settings riêng, vì vậy kết quả IDE có thể không tương đồng với Maven CLI.

Nếu generated code bắt đầu lỗi sau khi đổi version processor, hãy thử clean build trong môi trường xác định, thay vì sửa trực tiếp file dưới target rồi commit.

## 17. Bảo mật: processor là code được thực thi trong build

Một annotation processor được tải và chạy bởi compiler có thể:

- Đọc source code và compiler model.
- Tạo/sửa generated files thông qua API hoặc các cơ chế khác mà process được phép.
- Tương tác với filesystem và network theo quyền của môi trường build nếu implementation cố làm vậy.
- Truy cập một số environment values/CI credentials nếu quyền process cho phép.

Do đó:

1. **Chỉ chọn processors được duyệt**, pin versions và kiểm tra nguồn artifacts.
2. Ưu tiên liệt kê rõ `<annotationProcessors>` hoặc typed processor dependencies khi được hỗ trợ.
3. Không bật implicit discovery của mọi JAR một cách vô ý.
4. Không trao secrets/production credentials cho build job không cần chúng.
5. Không trộn processor implementation vào runtime dependencies nếu không có lý do.
6. Không nhận processor JAR không tin cậy rồi cho chạy trong CI có quyền publish.
7. Kiểm soát transitive dependencies của processor path, không chỉ application dependencies.
8. Theo dõi changelog của processors khi nâng Java/JDK.
9. Dùng build logs thận trọng: compiler args và diagnostics có thể lộ thông tin.
10. Trong JDK 23+, hãy xem yêu cầu cấu hình explicit là một biện pháp giảm auto-execution, **không phải bảo đảm mọi processor đã chỉ định đều an toàn**.

## 18. Lỗi thường gặp khi cấu hình annotation processing

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra/sửa |
| --- | --- | --- |
| `cannot find symbol: AppNote` | Processor không chạy, không sinh source hoặc source stale | `mvn clean compile`, xem processor config và generated sources |
| `Annotation processor ... not found` | Sai FQCN, JAR chưa có trên processor path | Kiểm tra `<annotationProcessors>` và artifact coordinates |
| `package com.example.apt does not exist` | Annotation API thiếu ở compile classpath | Thêm dependency API phù hợp; processor path không thay compile path |
| Đã có processor JAR trong dependency mà JDK 23+ không chạy | Dựa vào implicit classpath scanning | Khai báo processors/path tường minh |
| `-proc:full` không được javac nhận | JDK update cũ hoặc toolchain khác | Không ép proc full khi có processor selection; kiểm tra `javac -version` |
| `Attempt to recreate a file for type ...` | Processor tạo file cùng tên nhiều rounds/lượt | Kiểm tra processingOver, Filer và generated file naming |
| Build thành công nhưng thiếu generated class trên clean CI | IDE có annotation processing riêng, CLI không cấu hình | Kiểm tra Maven Compiler Plugin POM hiệu lực |
| Processor tạo file nhưng compiler vẫn không thấy class | Sai package/class name, code generated không hợp lệ hoặc output path sai | Kiểm tra generated source và compiler diagnostics |
| `NoClassDefFoundError` trong processor | Thiếu transitive processor dependency | Kiểm tra annotationProcessorPaths và management |
| Processor version xung đột JDK | Dùng compiler internals không tương thích | Nâng processor theo hướng dẫn của publisher |
| Duplicate generated file error | Hai processors cùng sinh class hoặc compile execution trùng | Rà soát processors và default/custom executions |
| Source annotation nhận được, không có output | Processor không hỗ trợ annotation FQCN, option validation lỗi | Kiểm tra SupportedAnnotationTypes và Messager |
| `Unrecognized processor option` warning | `-Akey` không được processor hỗ trợ | Kiểm tra `@SupportedOptions` và spelling |
| Test code gen không chạy | Chỉ cấu hình main compile hoặc test processor path khác | Xem `default-testCompile` và test classpath |
| Code chạy local nhưng lỗi trên CI | Processor chưa install/publish, repository rights sai | Kiểm tra GAV, local vs remote repository, credentials |
| `module-info.java` làm processor không tìm thấy | Nhầm processor path và module path | Xem type `classpath-processor`/`modular-processor` theo stack |
| Generated file bị commit nhầm | Chưa phân biệt src với target | Bỏ output build khỏi Git; tái sinh trong CI |
| Dùng `-D` thay cho `-A` mà option không có tác dụng | Maven property không được map sang compilerArgs | Thêm `<arg>-Akey=${property}</arg>` có chủ đích |

Đọc error gốc thay vì xóa cache hoặc thêm flags ngẫu nhiên. Nhiều lỗi liên quan annotation processors phát sinh trong compiler JVM, nhưng log nhìn chung vẫn được Maven Compiler Plugin thu nhận dưới phase compile.

## 19. Quy trình chẩn đoán theo từng tầng

**Bước 1 — Xác nhận toolchain**

~~~bash
mvn -version
javac -version
~~~

`mvn -version` xác nhận JDK chạy Maven; `javac -version` trong shell là compiler mặc định của shell. Nếu Maven dùng **toolchains** hoặc Compiler Plugin chỉ định executable khác, hai thông số không nhất thiết đại diện cho cùng compiler. Kiểm tra effective compiler config.

**Bước 2 — Đọc POM hiệu lực**

~~~bash
mvn help:effective-pom
mvn help:active-profiles
~~~

Tìm đúng version Compiler Plugin, `annotationProcessorPaths`, `annotationProcessors`, `proc`, `compilerArgs`, profile và parent inheritance. Lưu ý `<pluginManagement>` và actual `<plugins>`; một execution từ parent/profile cũng có thể chạy processor ở những phase khác.

**Bước 3 — Clean compile để tránh stale source**

~~~bash
mvn -B clean compile
~~~

Nếu fail, xác định lỗi đến từ **tìm annotation type**, **tìm processor implementation**, **chạy processor** hay **biên dịch generated code**.

**Bước 4 — Quan sát generated source/output**

Trong project phù hợp, xem:

~~~text
target/generated-sources/annotations/
target/classes/
~~~

Nếu processor chỉ validate và không sinh Java, việc thư mục generated source trống chưa đủ chứng minh processor không chạy; xem diagnostics.

**Bước 5 — Bật diagnostics một cách kiểm soát**

Để hiểu processor rounds, javac có options như:

~~~text
-XprintRounds
-XprintProcessorInfo
~~~

Có thể đưa chúng vào Compiler Plugin `<compilerArgs>` trong bản build thử nghiệm. Log có thể dài; không phải cấu hình production cần giữ mãi.

~~~xml
<compilerArgs>
    <arg>-XprintRounds</arg>
    <arg>-XprintProcessorInfo</arg>
</compilerArgs>
~~~

Đây là mảnh configuration, khi tích hợp cần bảo toàn những `<compilerArgs>` khác như `-Anote.message=READY`. Không ghi đè toàn bộ compilerArgs có giá trị khác chỉ để thêm debug.

**Bước 6 — Kiểm tra bảo mật và dependency resolution**

Không tải processors từ nguồn lạ; xem GAV, transitive processor libraries, repository/mirror và release policy. Nếu problem chỉ xảy ra với test compile, kiểm tra riêng compiler:testCompile.

## 20. Các câu hỏi tự kiểm tra

**Câu 1.** Dự án import `@Mapper` nhưng chỉ thêm `mapstruct-processor` vào annotationProcessorPaths. Java compile chắc chắn tìm thấy `@Mapper`?

**Đáp:** Không nhất thiết. Annotation API phải có ở compile classpath/module path; processor path là nơi tìm implementation.

**Câu 2.** Trên JDK 23+, chỉ thêm một processor JAR vào compile dependencies mà không cấu hình annotation processing, compiler có bắt buộc tự chạy nó?

**Đáp:** Không. Từ JDK 23, xử lý annotation cần được yêu cầu tường minh; không dựa vào implicit classpath scan.

**Câu 3.** `annotationProcessorPaths` và `annotationProcessors` làm cùng việc?

**Đáp:** Không. Một cái xác định **nơi chứa code processor**, một cái xác định **processor class nào được gọi**.

**Câu 4.** `<proc>only</proc>` tạo full `.class` output cho ứng dụng?

**Đáp:** Không. Nó chỉ chạy annotation processing, không thực hiện compile đầy đủ.

**Câu 5.** Generated Java thường nằm ở đâu?

**Đáp:** Với Maven Compiler Plugin 3.x cấu hình mặc định, thường ở `target/generated-sources/annotations`; class files sau compile ở `target/classes`.

**Câu 6.** Vì sao một processor JAR đôi khi cần mặt trên cả compile classpath và processor path?

**Đáp:** Trong demo gộp annotation type và processor implementation chung JAR, compile path cung cấp annotation type cho source, còn processor path cung cấp implementation để javac chạy. Với kiến trúc tốt hơn có thể tách hai artifacts.

**Câu 7.** Processor có dùng Java `System.getProperty` thay cho `processingEnv.getOptions()` để nhận `-Akey` không?

**Đáp:** Không tương đương. `-Akey=value` truyền qua compiler processor options, đọc bằng `processingEnv.getOptions()`.

**Câu 8.** Maven 4 + Compiler Plugin 4.x có thể dùng typed processor dependencies nào?

**Đáp:** `processor`, `classpath-processor`, `modular-processor`; nếu biết path type, nên khai báo rõ.

**Câu 9.** Nếu `AppNote.class` tồn tại từ build cũ, có đủ chứng minh annotation processor đang chạy sau khi POM đổi?

**Đáp:** Không. Cần `mvn clean compile` và xác minh generated source/diagnostics mới.

**Câu 10.** Annotation processor chỉ tạo Java code, không phải thực thi code?

**Đáp:** Sai. Processor là **code chạy trong compiler build process**; nó có thể đọc và ghi tệp theo quyền process, nên phải kiểm soát nguồn và versions.

## 21. Checklist cấu hình processor an toàn và ổn định

1. Ghi rõ Java/JDK và Maven Compiler Plugin versions.
2. Xác định annotation API mà Java source cần import và đặt trên compile path phù hợp.
3. Xác định processor implementation JAR riêng và transitive dependencies của nó.
4. Với Maven 3 + Compiler Plugin 3.x, dùng `annotationProcessorPaths` cho processor path.
5. Khai báo `annotationProcessors` khi có thể để chỉ thực thi implementation mong muốn.
6. Với Maven 4 + Compiler Plugin 4.x, cân nhắc typed processor dependencies phù hợp thay cho cấu hình 3.x cũ.
7. Không trông chờ implicit processor discovery trên JDK 23+.
8. Không đặt `<proc>full</proc>` chỉ vì nghe giống lựa chọn mặc định; kiểm tra JDK support và mục tiêu bảo mật.
9. Truyền processor options qua `-Akey=value`; nếu nhận từ Maven properties, map tường minh.
10. Để generated files trong `target/` và tránh commit output có thể tái sinh.
11. Nếu processor cần chạy ở test compile, cấu hình đúng implied execution của test.
12. Không tạo compiler execution bổ sung không cần thiết rồi làm processor chạy trùng.
13. Kiểm tra generated Java **và** `.class`, không chỉ dựa vào BUILD SUCCESS.
14. Dùng clean build trên CI để giảm stale generated outputs.
15. Pin plugin/processor/dependencies; cập nhật có kiểm thử khi đổi JDK hoặc framework.
16. Đừng chạy processor chưa tin cậy trong CI có quyền đọc secrets hoặc publish.
17. Khi có JPMS, phân biệt processor classpath và processor module path.
18. Đọc diagnostics, Maven effective POM và Java compiler options trước khi thêm workaround.

## Tài liệu tham khảo

- [Apache Maven Compiler Plugin 3.13.0 — compile goal parameters](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.13.0/compile-mojo.html)
- [Apache Maven Compiler Plugin — Annotation Processors, Maven 3 và Maven 4](https://maven.apache.org/components/plugins/maven-compiler-plugin-4.x/examples/annotation-processor.html)
- [Apache Maven — What's New in Maven 4: Processor Types](https://maven.apache.org/whatsnewinmaven4.html)
- [OpenJDK — javac Command Documentation](https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html)
- [Inside Java — JDK 23 Changes Default Annotation Processing Policy](https://inside.java/2024/06/18/quality-heads-up/)
- [Java Platform — javax.annotation.processing API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html)
- [Java Platform — javax.lang.model API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/lang/model/package-summary.html)

