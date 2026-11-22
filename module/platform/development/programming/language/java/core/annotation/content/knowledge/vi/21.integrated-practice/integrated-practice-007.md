# Đóng gói thư viện annotation và annotation processor rồi sử dụng từ dự án khác

Mục tiêu của bài thực hành là xây dựng **hai thư viện JAR có trách nhiệm riêng**, sau đó dùng chúng từ một dự án Java độc lập: một JAR cung cấp annotation để mã nguồn ứng dụng import; JAR còn lại chứa annotation processor chạy trong quá trình biên dịch để tạo mã Java. Sau bài này, bạn có thể đóng gói, công bố, cấu hình và kiểm tra một processor như một thư viện được tái sử dụng, thay vì chỉ chạy processor trong cùng dự án tạo ra nó.

Ví dụ dùng **Java 17+**, annotation `@AutoGreeting`, processor `GreetingProcessor` và ứng dụng `App`. Khi compiler gặp `@AutoGreeting` trên lớp `App`, processor tạo `demo.consumer.AppGreeting`. Ứng dụng gọi `AppGreeting.text()` và in `Hello from generated source`.

## 1. Kiến trúc ba dự án và các đường dẫn biên dịch

```text
annotation-api/                              # Thư viện API người dùng import
  src/main/java/demo/api/AutoGreeting.java
greeting-processor/                          # Thư viện processor, biên dịch trước ứng dụng
  src/main/java/demo/processor/GreetingProcessor.java
  src/main/resources/META-INF/services/
    javax.annotation.processing.Processor
consumer/                                    # Dự án ứng dụng độc lập dùng hai JAR
  src/main/java/demo/consumer/App.java
```

Quan hệ dependency:

```text
consumer source ──compile classpath──> annotation-api.jar
                                            ^
                                            | processor cũng cần định nghĩa annotation
compiler ──processor path──> greeting-processor.jar + annotation-api.jar
                                            |
                                            v
                         GreetingProcessor được tải trong javac
                                            |
                                   tạo AppGreeting.java
                                            |
                            javac biên dịch thành AppGreeting.class
```

**Phân tách API và processor** rất có ích: mã ứng dụng cần annotation API khi biên dịch nhưng không nhất thiết cần lớp processor lúc chạy. Processor là một công cụ thuộc **thời điểm biên dịch**; trong tình huống này, JAR processor không phải dependency runtime của ứng dụng. Thư viện annotation API được công bố độc lập giúp dự án tiêu thụ import annotation mà không bị kéo cả compiler extension vào runtime.

Phân biệt rõ ba khái niệm:

| Thành phần | Chức năng | Nơi đặt |
| --- | --- | --- |
| Annotation API | Khai báo `@AutoGreeting`, phần mà mã ứng dụng tham chiếu | Compile classpath của consumer; compile dependency của processor |
| Annotation processor | Implement `javax.annotation.processing.Processor`, đọc mô hình source qua `javax.lang.model` và sinh code | Processor path của compiler |
| Service registration | Cho `javac` tự khám phá processor qua `ServiceLoader` | `META-INF/services/javax.annotation.processing.Processor` bên trong processor JAR |

Processor chạy trên JVM của công cụ biên dịch. Vì vậy, nó phải tương thích với **JDK đang thực thi compiler**; source level của ứng dụng có thể khác. Ví dụ `javac` chạy bằng JDK 21 với `--release 17` cho ứng dụng là tình huống hợp lệ.

## 2. Xây dựng thư viện annotation API

Tạo `annotation-api/src/main/java/demo/api/AutoGreeting.java`:

```java
package demo.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface AutoGreeting {
}
```

`@Target(TYPE)` cho phép gắn annotation lên khai báo kiểu. `RetentionPolicy.SOURCE` đủ cho annotation processor đọc annotation trong lúc `javac` xử lý mã nguồn; bài này không cần reflection ở runtime. Annotation API nằm trong package riêng (`demo.api`) để consumer không phụ thuộc trực tiếp vào package triển khai processor.

Nếu thư viện thật có thêm thuộc tính cho annotation (ví dụ tên lớp sinh hoặc cấu hình), xác định rõ giá trị mặc định, kiểu hợp lệ và chính sách tương thích phiên bản. Thay đổi tên/gói annotation sẽ ảnh hưởng đồng thời mã ứng dụng và `@SupportedAnnotationTypes` trong processor.

## 3. Xây dựng GreetingProcessor để sinh nguồn Java

Tạo `greeting-processor/src/main/java/demo/processor/GreetingProcessor.java`:

```java
package demo.processor;

import demo.api.AutoGreeting;
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.api.AutoGreeting")
public final class GreetingProcessor extends AbstractProcessor {

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        if (roundEnv.processingOver()) {
            return false;
        }

        for (Element element : roundEnv.getElementsAnnotatedWith(AutoGreeting.class)) {
            if (element.getKind() != ElementKind.CLASS
                    || element.getEnclosingElement().getKind() != ElementKind.PACKAGE) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@AutoGreeting chỉ hỗ trợ top-level class",
                        element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();
            String generatedSimpleName = type.getSimpleName() + "Greeting";
            String generatedName = packageName.isEmpty()
                    ? generatedSimpleName
                    : packageName + "." + generatedSimpleName;

            try {
                JavaFileObject sourceFile = processingEnv.getFiler()
                        .createSourceFile(generatedName, type);

                try (Writer out = sourceFile.openWriter()) {
                    if (!packageName.isEmpty()) {
                        out.write("package " + packageName + ";\n\n");
                    }
                    out.write("public final class " + generatedSimpleName + " {\n");
                    out.write("    private " + generatedSimpleName + "() {}\n");
                    out.write("    public static String text() {\n");
                    out.write("        return \"Hello from generated source\";\n");
                    out.write("    }\n");
                    out.write("}\n");
                }

                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.NOTE,
                        "Generated " + generatedName,
                        element);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate " + generatedName + ": " + ex.getMessage(),
                        element);
            }
        }
        return true;
    }
}
```

Các điểm cần hiểu trước khi đóng gói:

- `@SupportedAnnotationTypes("demo.api.AutoGreeting")` dùng **tên kiểu đầy đủ**. Nếu đổi package của annotation mà không sửa metadata này, processor có thể được phát hiện nhưng không xử lý annotation mong muốn.
- `getSupportedSourceVersion()` trả phiên bản source mới nhất mà chính compiler hiện tại hỗ trợ; dùng `SourceVersion.RELEASE_17` cũng được khi chủ động giới hạn phiên bản, nhưng có thể gây cảnh báo khi ứng dụng biên dịch source mới hơn.
- `RoundEnvironment` mô tả phần tử trong round xử lý hiện tại; `processingOver()` đánh dấu round cuối và ví dụ không sinh source mới ở round đó.
- `getElementsAnnotatedWith(AutoGreeting.class)` trả phần tử source phù hợp. Processor cố ý giới hạn **lớp top-level** để tên `AppGreeting` được sinh đơn giản và tránh quy tắc đặt tên lớp lồng phức tạp.
- `Filer.createSourceFile(generatedName, type)` tạo source mới và chỉ rõ originating element, hỗ trợ công cụ build liên kết output với source đã kích hoạt processor.
- Ghi ra source thông qua `Writer` và để compiler tự biên dịch source đó trong các round tiếp theo. Không cần gọi `javac` một lần nữa chỉ để compile `AppGreeting.java` ở ví dụ này.
- Trả `true` để thông báo processor đã nhận trách nhiệm với annotation phù hợp. Khi có nhiều processor cùng xử lý một annotation, quyết định claim cần tương thích với hợp đồng giữa chúng.
- Nếu source cùng tên đã tồn tại, `FilerException` là một dạng `IOException`; log lỗi có ngữ cảnh giúp phân biệt đụng tên với lỗi đường dẫn. Bài mẫu giả định chưa có file `AppGreeting.java` viết tay.

**Giới hạn của ví dụ:** phương pháp sinh chuỗi Java bằng `Writer` phù hợp khi nội dung luôn cố định như trên. Với annotation chứa chuỗi tùy ý do người dùng nhập, phải escape đầy đủ literal Java hoặc dùng thư viện sinh mã nguồn được kiểm chứng. Không ghép dữ liệu tùy ý vào Java source mà không encode.

## 4. Đăng ký processor qua service provider

Tạo tệp **không có phần mở rộng**:

```text
greeting-processor/src/main/resources/META-INF/services/javax.annotation.processing.Processor
```

Nội dung nguyên văn, một dòng:

```text
demo.processor.GreetingProcessor
```

Tên của service file là tên đầy đủ của interface `javax.annotation.processing.Processor` (dùng Java `javax` API, không đổi thành `jakarta`). Dòng bên trong là tên đầy đủ của lớp processor. File phải được đóng gói đúng vị trí dưới gốc JAR:

```text
greeting-processor.jar
  demo/processor/GreetingProcessor.class
  META-INF/services/javax.annotation.processing.Processor
  META-INF/MANIFEST.MF
```

Với **processor trên classpath**, service file hỗ trợ compiler khám phá processor mà không cần tham số `-processor`. Nếu chỉ định `-processor demo.processor.GreetingProcessor` thì compiler tải đích danh lớp này; đó cũng là phép thử tách lỗi service discovery khỏi lỗi tải class.

Nếu đóng gói processor thành **JPMS named module** và dùng `--processor-module-path`, hãy đăng ký provider bằng `provides javax.annotation.processing.Processor with demo.processor.GreetingProcessor;` trong `module-info.java` và cấu hình module dependencies tương ứng. Ví dụ thực hành ở đây dùng JAR trên **processor classpath**, không dùng module path.

**Bẫy khi tự xây JAR:** biên dịch trực tiếp processor trong một đợt javac mà service file đã có trên compiler classpath có thể khiến compiler cố tải processor trước khi `GreetingProcessor.class` tồn tại. Hãy biên dịch các lớp của processor trước, sau đó thêm service file vào JAR; trong dự án có Gradle/Maven, resource được đóng gói cùng artifact lúc `jar` / `package`.

## 5. Consumer độc lập dùng annotation và lớp được sinh

Tạo `consumer/src/main/java/demo/consumer/App.java`:

```java
package demo.consumer;

import demo.api.AutoGreeting;

@AutoGreeting
public class App {
    public static void main(String[] args) {
        System.out.println(AppGreeting.text());
    }
}
```

`AppGreeting` **không có trong source tự viết**. Compiler chỉ resolve được kiểu này nếu annotation processor chạy thành công, sinh `demo.consumer.AppGreeting.java` và đưa file sinh vào cùng đợt biên dịch.

Sau khi xử lý, mã được sinh có nội dung tương đương:

```java
package demo.consumer;

public final class AppGreeting {
    private AppGreeting() {}
    public static String text() {
        return "Hello from generated source";
    }
}
```

Đặt các file của `consumer` vào **repository/dự án khác** là hoàn toàn hợp lệ: dự án consumer chỉ nhận hai artifact đã build/publish và khai báo chúng ở đúng configuration; không cần copy source processor sang ứng dụng.

## 6. Thực hành đóng gói bằng javac và jar (Java 17+)

Các lệnh dưới đây chạy ở thư mục cha chứa ba thư mục `annotation-api`, `greeting-processor` và `consumer` đã tạo. Ví dụ dùng Bash/macOS/Linux; trong PowerShell Windows, tạo thư mục bằng `New-Item -ItemType Directory -Force ...` và dùng dấu `;` làm dấu phân cách classpath.

**Bước 1: Biên dịch và đóng gói annotation API.**

```bash
mkdir -p build/api-classes build/processor-classes build/consumer-classes build/generated
javac --release 17 -d build/api-classes \
  annotation-api/src/main/java/demo/api/AutoGreeting.java
jar --create --file build/annotation-api.jar -C build/api-classes .
```

**Bước 2: Biên dịch processor với annotation API trên compile classpath.**

```bash
javac --release 17 -cp build/annotation-api.jar \
  -d build/processor-classes \
  greeting-processor/src/main/java/demo/processor/GreetingProcessor.java

jar --create --file build/greeting-processor.jar \
  -C build/processor-classes . \
  -C greeting-processor/src/main/resources META-INF

jar --list --file build/greeting-processor.jar
```

`jar --list` phải có ít nhất `demo/processor/GreetingProcessor.class` và `META-INF/services/javax.annotation.processing.Processor`. `annotation-api.jar` phải chứa `demo/api/AutoGreeting.class`. Nếu tệp service ở sai vị trí, processor JAR vẫn có thể được build thành công nhưng discovery thất bại.

**Bước 3: Biên dịch consumer với hai đường dẫn độc lập.**

```bash
javac --release 17 \
  -cp build/annotation-api.jar \
  -processorpath build/greeting-processor.jar:build/annotation-api.jar \
  -processor demo.processor.GreetingProcessor \
  -XprintRounds -XprintProcessorInfo \
  -s build/generated \
  -d build/consumer-classes \
  consumer/src/main/java/demo/consumer/App.java
```

Giải thích chính xác vai trò:

- `-cp` chứa API annotation để source `App.java` import `demo.api.AutoGreeting`.
- `-processorpath` chứa **cả** processor JAR và annotation API JAR, vì lớp processor tham chiếu trực tiếp đến `AutoGreeting.class` khi chạy. Dependency của processor cũng phải có trên đường dẫn này nếu processor sử dụng thư viện khác.
- `-processor` chọn processor cụ thể; giúp chạy nhất quán trên JDK 17+ và cả JDK 23+, nơi chính sách annotation processing mặc định chặt hơn.
- `-s` chỉ định thư mục viết generated **source**; `-d` chỉ định thư mục biên dịch **class**.
- `-XprintRounds` và `-XprintProcessorInfo` in dấu vết xử lý. Log chi tiết phụ thuộc phiên bản JDK; diagnostic có cụm `Generated demo.consumer.AppGreeting`.

Đến đây, đường dẫn `build/generated/demo/consumer/AppGreeting.java` và `build/consumer-classes/demo/consumer/AppGreeting.class` phải tồn tại.

**Bước 4: Chạy consumer.**

```bash
java -cp build/consumer-classes:build/annotation-api.jar demo.consumer.App
```

Stdout chính xác:

```text
Hello from generated source
```

Trên Windows thay dấu `:` trong `-processorpath` và runtime `-cp` bằng dấu `;`, đồng thời đặt argument chứa dấu `;` trong dấu ngoặc kép nếu shell yêu cầu.

**Bước 5: Thử tự động discovery bằng service file.** Để kiểm tra quá trình đăng ký đúng, chạy lại Bước 3 sau khi làm sạch thư mục output, **bỏ `-processor demo.processor.GreetingProcessor`** và thêm `-proc:full` trong lệnh `javac`. Tùy bản cập nhật JDK 17, tùy chọn `-proc:full` có thể chưa có; khi đó giữ phép thử `-processor` ở trên hoặc dùng JDK hiện đại có `-proc:full`. Từ JDK 23, nên chỉ định bật annotation processing rõ ràng, thay vì trông chờ xử lý ngầm từ compile classpath. Cách chạy tường minh ở Bước 3 là cơ sở kiểm chứng độc lập với cơ chế discovery.

## 7. Tái sử dụng bằng Gradle ở dự án khác

Giả sử ba project được khai báo trong một Gradle multi-project build phục vụ thử nghiệm. `settings.gradle`:

```groovy
rootProject.name = 'greeting-workspace'
include 'annotation-api', 'greeting-processor', 'consumer'
```

Một `build.gradle` Groovy DSL đơn giản ở root:

```groovy
subprojects {
    apply plugin: 'java'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(17)
        }
    }
}

project(':greeting-processor') {
    dependencies {
        implementation project(':annotation-api')
    }
}

project(':consumer') {
    dependencies {
        implementation project(':annotation-api')
        annotationProcessor project(':greeting-processor')
        annotationProcessor project(':annotation-api')
    }
}
```

Lưu các Java file và resource theo đúng layout `src/main/java` / `src/main/resources` ở trên. Chạy:

```bash
./gradlew :consumer:clean :consumer:compileJava
./gradlew :consumer:run
```

**Chú ý:** task `:consumer:run` chỉ có khi consumer áp dụng plugin `application` và cấu hình `mainClass`. Với cấu hình chỉ có plugin `java` ở trên, lệnh bắt buộc để xác minh build là `./gradlew :consumer:clean :consumer:compileJava`; để chạy ứng dụng, thêm vào `consumer/build.gradle`:

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.consumer.App'
}
```

Lúc đó `./gradlew :consumer:run` sẽ in `Hello from generated source`. `annotationProcessor` định nghĩa đường dẫn processor riêng. `implementation` của consumer chỉ chứa annotation API (và các dependency khác ứng dụng thật cần); processor JAR không phải runtime dependency.

Để dùng từ **repository Gradle độc lập**, công bố hai artifact bằng `maven-publish` rồi thay `project(...)` bằng tọa độ dependency. Ví dụ sau giả định đã xuất bản `demo:annotation-api:1.0.0` và `demo:greeting-processor:1.0.0` vào `mavenLocal()` hoặc repository có quyền truy cập:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenLocal()
    mavenCentral()
}

dependencies {
    implementation 'demo:annotation-api:1.0.0'
    annotationProcessor 'demo:greeting-processor:1.0.0'
    annotationProcessor 'demo:annotation-api:1.0.0'
}

application {
    mainClass = 'demo.consumer.App'
}
```

**Cấu hình producer để publish:** mỗi thư viện cần plugin `java-library` (hoặc `java`) và `maven-publish`, khai báo `group = 'demo'`, `version = '1.0.0'` và publication từ `components.java`, ví dụ:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'demo'
version = '1.0.0'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
```

Đưa cấu hình này vào mỗi producer project (`annotation-api` và `greeting-processor`) rồi chạy `publishToMavenLocal` cho từng project sau khi khai báo dependency processor → annotation-api. Cần đảm bảo **processor JAR thực sự chứa file service** trước khi công bố. Trong dự án thật, publish lên repository nội bộ/ngoài theo chính sách tổ chức; tránh dùng `mavenLocal()` làm nguồn dependency duy nhất của CI vì máy build khác có thể không có artifact.

Nếu chỉ cần thử local nhanh, multi-project dependencies là đủ; muốn tái sử dụng qua nhiều repository/máy, artifact repository và version chính là hợp đồng phân phối.

## 8. Tái sử dụng bằng Maven ở dự án khác

Với Maven 3 và `maven-compiler-plugin` 3.x, `consumer/pom.xml` cần hai mảng khai báo khác nhau:

1. Dependency `annotation-api` trong `<dependencies>` để mã nguồn consumer import `AutoGreeting`.
2. `annotationProcessorPaths` trong compiler plugin để compiler tải `greeting-processor` cùng annotation API. Có thể chỉ đích danh processor bằng `annotationProcessors`, hữu ích cho JDK 23+.

Ví dụ đoạn POM cho **consumer độc lập**, sau khi các producer artifact đã được `install` / `deploy`:

```xml
<dependencies>
  <dependency>
    <groupId>demo</groupId>
    <artifactId>annotation-api</artifactId>
    <version>1.0.0</version>
  </dependency>
</dependencies>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.14.1</version>
      <configuration>
        <release>17</release>
        <annotationProcessorPaths>
          <path>
            <groupId>demo</groupId>
            <artifactId>greeting-processor</artifactId>
            <version>1.0.0</version>
          </path>
          <path>
            <groupId>demo</groupId>
            <artifactId>annotation-api</artifactId>
            <version>1.0.0</version>
          </path>
        </annotationProcessorPaths>
        <annotationProcessors>
          <annotationProcessor>demo.processor.GreetingProcessor</annotationProcessor>
        </annotationProcessors>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Đoạn trên là **phần tử bên trong `<project>`** của một POM Maven hợp lệ, chưa phải file POM standalone. Các producer có thể dùng `mvn install` để xuất bản local theo thứ tự annotation API trước rồi processor; consumer dùng `mvn clean compile` và xem `target/generated-sources/annotations/demo/consumer/AppGreeting.java`. Artifact coordinates là ví dụ; phải khớp `groupId`, `artifactId`, `version` khi công bố thực tế.

Trong Maven 4 + Compiler Plugin 4.x, cách khai báo dependency kiểu `processor` / `classpath-processor` / `modular-processor` thay đổi so với 3.x; không trộn tùy tiện cấu hình của hai major version. Khi chuyển toolchain, kiểm tra tài liệu chính thức của plugin đang dùng.

## 9. Kiểm chứng artifact và hợp đồng phát hành

Trước khi đưa JAR cho dự án khác, tạo một **consumer fixture sạch** chỉ có những artifact dự kiến public. Đây là cách phát hiện dependency vô tình dựa vào thư mục `build/classes`, cache IDE hoặc source của processor.

Các phép kiểm tra hữu ích:

| Phép kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| `jar --list --file annotation-api.jar` | Có `demo/api/AutoGreeting.class` |
| `jar --list --file greeting-processor.jar` | Có `demo/processor/GreetingProcessor.class` và `META-INF/services/javax.annotation.processing.Processor` |
| Đọc tệp service trong JAR | Một dòng tên đầy đủ `demo.processor.GreetingProcessor`, không gõ sai hoặc đổi thành package khác |
| `javac` với `-processor ...` và processor path đúng | Có log `Generated demo.consumer.AppGreeting` |
| `javac` chỉ discovery qua service | Chạy processor khi chủ động bật AP và cấu hình processor path |
| `build/generated/.../AppGreeting.java` | Source được tạo ở package consumer |
| `build/consumer-classes/.../AppGreeting.class` | Generated source đã được compiler compile |
| `java demo.consumer.App` | Stdout `Hello from generated source` |

Khi phát hành thật, nên kiểm tra thêm **mã phiên bản Java của JAR**, sự tương thích giữa phiên bản `annotation-api` với `greeting-processor`, tọa độ artifact, file POM/module metadata, checksum và giấy phép. Không public API type riêng của processor trừ khi hợp đồng thư viện thật sự yêu cầu.

Lược đồ phiên bản nên rõ ràng: hai artifact cùng `1.0.0` trong ví dụ để dễ đồng bộ; thực tế có thể version độc lập nhưng cần ghi rõ processor phiên bản nào tương thích với annotation API nào. Nếu thêm property bắt buộc vào annotation hay đổi tên generated class, đó có thể là thay đổi phá vỡ mã consumer.

### Hợp đồng generated code và tính lặp lại

- Không đặt generated Java source vào `src/main/java` của consumer. Để `Filer` và build tool quản lý thư mục output; tránh commit generated artifacts trừ khi có lý do cụ thể.
- Processor phải tạo cùng output khi cùng input; không nhúng thời gian/máy/ngẫu nhiên vào source nếu không cần. Điều này cải thiện build reproducibility và cache.
- Mỗi source do `Filer` tạo nên có tên duy nhất trong đợt compile; đừng ghi cùng tên ở nhiều round. Trong ví dụ, một top-level class `App` tạo `AppGreeting`; nếu người dùng tự định nghĩa cùng tên, hãy báo lỗi rõ.
- Với Gradle incremental AP, việc gắn nhãn `isolating` / `aggregating` cần thỏa hợp đồng thật. Ví dụ một generated file bắt nguồn từ một annotated class đã chuyển originating element cho `Filer`, nhưng chỉ đăng ký incremental metadata sau khi kiểm thử đúng các trường hợp incremental build.
- Không gọi processor trực tiếp lúc runtime hoặc kéo processor dependency vào `runtimeOnly` chỉ để xử lý annotation. Annotation processor phải hoạt động khi **biên dịch**.

## 10. Các lỗi thường gặp khi dùng từ dự án khác

**Lỗi `cannot find symbol: class AutoGreeting`:** annotation API JAR không có trong **compile classpath** của consumer hoặc package import sai. Processor path riêng không thay thế dependency API của mã nguồn.

**Lỗi `Annotation processor 'demo.processor.GreetingProcessor' not found`:** JAR processor không nằm trên processor path, sai tên lớp, class không public/không load được, hoặc processor bytecode yêu cầu JDK mới hơn compiler. Kiểm tra `jar --list`, đường dẫn và dependency processor.

**Lỗi `NoClassDefFoundError: demo/api/AutoGreeting` khi processor chạy:** processor phụ thuộc annotation API nhưng thư viện API không có trên **processor path**. Compile dependency của processor trong lúc đóng gói không đồng nghĩa dependency đó được tự động nhúng vào JAR processor thủ công.

**Compiler thành công nhưng không có `AppGreeting`:** annotation processing chưa chạy, service file chưa được đưa vào JAR, annotation type không trùng `@SupportedAnnotationTypes`, hoặc compiler không compile source `App.java`. Thêm `-processor`, `-XprintProcessorInfo`, `-XprintRounds` và diagnostic qua `Messager`. Với JDK 23+, tuyệt đối không dựa vào việc tự bật AP do classpath tình cờ chứa processor.

**Lỗi `Attempt to recreate a file for type ...`:** có class/generated source cùng tên, nhiều annotated elements cùng tạo một tên, hoặc processor tạo lặp lại trong nhiều round. Kiểm tra `Filer.createSourceFile`, tên đầy đủ và logic round; không chữa bằng xóa tùy ý file ở module khác.

**IDE không hiển thị generated class nhưng CLI build chạy:** xác minh annotation processing được bật, IDE có đang delegate build cho Gradle/Maven hay không, JDK toolchain và generated sources directory đã được IDE nhận diện. Tránh copy generated file vào source tree làm giải pháp lâu dài.

**Consumer compile nhưng runtime `ClassNotFoundException` đối với thư viện processor:** trong kiến trúc này runtime không cần processor; chỉ generated class phải nằm trong artifact consumer. Nếu generated code thật sự tham chiếu helper của processor, hãy tách helper thành **runtime library riêng**, khai báo dependency runtime rõ ràng.

**Maven/Gradle build sạch lỗi dù máy cá nhân chạy:** artifact `annotation-api` / `greeting-processor` chưa được publish vào repository CI đọc được, service file không có trong JAR đã publish, hoặc producer/consumer dùng phiên bản không tương thích. Thử consumer sạch với artifact tải từ kho thực tế, không dùng source cùng checkout.

## 11. Checklist hoàn thành bài thực hành

1. Có hai JAR được đóng gói độc lập: annotation API và processor.
2. Processor JAR chứa chính xác service provider file tại `META-INF/services/javax.annotation.processing.Processor`.
3. Consumer chỉ import annotation API trong source, và khai báo processor trên processor path.
4. Build từ nguồn sạch tạo `AppGreeting.java` qua `Filer`, biên dịch được `AppGreeting.class` và chạy ra `Hello from generated source`.
5. Có thể đưa JAR lên Maven repository rồi dùng bằng version tọa độ trong **dự án khác**, không phụ thuộc source producer.
6. Đã kiểm tra compiler JDK/toolchain, publication metadata, phiên bản và chẩn đoán khi processor không được phát hiện.
7. Đã hiểu phần nào thuộc compile classpath, processor path và runtime classpath; các artifact và generated source được quản lý ở đúng vòng đời.

## Tài liệu tham khảo

- Java SE, API `Processor`, `AbstractProcessor`, `RoundEnvironment`, `Filer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html
- `javac` options (`-processor`, `-processorpath`, `-s`, `-proc`): https://docs.oracle.com/en/java/javase/23/docs/specs/man/javac.html
- Gradle Java annotation processing: https://docs.gradle.org/current/userguide/java_plugin.html#sec:java_compile_avoidance
- Gradle Maven Publish plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Maven Compiler Plugin 3.x annotation processing: https://maven.apache.org/plugins/maven-compiler-plugin-3.14.1/compile-mojo.html
