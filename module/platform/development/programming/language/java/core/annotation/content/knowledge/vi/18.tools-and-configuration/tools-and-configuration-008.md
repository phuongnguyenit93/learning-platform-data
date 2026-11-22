# Cấu hình annotation processor trong công cụ dựng và đồng bộ với IDE

Một annotation processor Java không tự chạy chỉ vì source có `@Generate...` hoặc vì JAR của processor có trong dependency của dự án. Để quá trình **kiểm tra annotation và sinh mã khi biên dịch** ổn định giữa máy lập trình viên, CI, Maven/Gradle và IDE, ta cần cấu hình đúng **nơi compiler tìm processor**, **cách chọn processor**, **bộ nguồn được xử lý**, **thư mục mã sinh** và **JDK dùng để biên dịch**.

Ví dụ quen thuộc: processor đọc `@GenerateFlag`, tạo class `GeneratedFlag` trong lúc compile; code ứng dụng gọi `GeneratedFlag.value()`. Khi processor chạy đúng, cả mã sinh và ứng dụng đều biên dịch. Nếu IDE không chạy processor dù Maven/Gradle chạy thành công, IDE có thể báo `Cannot resolve symbol 'GeneratedFlag'`. Nếu CI đổi sang JDK 23+ mà cấu hình chỉ dựa vào dò processor ngầm trên classpath, việc sinh mã cũng có thể đột ngột ngừng hoạt động.

**Nguyên tắc cốt lõi:** build script là nguồn cấu hình chính, processor được khai báo **tường minh**, các thư mục generated sources do build quản lý, và IDE cần **nhập lại (reload/sync)** mô hình build thay vì tự cài đặt tùy ý khác với CI.

## 1. Phân biệt annotation API, processor và mã sinh

Thông thường có ba vai trò độc lập:

| Thành phần | Chứa gì? | Cần xuất hiện ở đâu? |
|---|---|---|
| **Annotation API** | `@interface GenerateFlag` hoặc `@interface Mapper` mà mã ứng dụng tham chiếu | Compile classpath của module dùng annotation |
| **Annotation processor** | Một class triển khai `javax.annotation.processing.Processor` hoặc kế thừa `AbstractProcessor` | **Processor path** của compiler, cùng dependency mà processor cần khi chạy |
| **Generated sources/classes** | Java source/class do processor tạo ra | Được compiler đưa vào compilation và IDE nhận là generated sources |

Ví dụ một cấu trúc project:

```text
root/
├── annotation-api/
│   └── src/main/java/com/example/api/GenerateFlag.java
├── annotation-processor/
│   ├── src/main/java/com/example/apt/FlagProcessor.java
│   └── src/main/resources/META-INF/services/
│       └── javax.annotation.processing.Processor
└── app/
    ├── src/main/java/com/example/app/Main.java
    └── build.gradle / pom.xml
```

Processor thường phụ thuộc vào annotation API để có thể đọc class annotation. Module ứng dụng phụ thuộc vào annotation API để **biên dịch source**, và cấu hình annotation processor của module ứng dụng để **chạy processor trong compile task**. Điều này khác với việc thêm processor như một runtime dependency thông thường.

Lưu ý:

- **Compile classpath** cho compiler biết các loại `GenerateFlag`, `List`, thư viện ứng dụng, v.v.
- **Processor path** cho compiler biết JAR/class của `FlagProcessor` và dependencies dùng **bởi processor**.
- **Runtime classpath** chỉ cần các class mà ứng dụng thực sự sử dụng khi chạy; một processor thuần túy chạy tại compile time thường không cần ở runtime.
- Mã sinh ra là *artifact của build*, không phải một tệp source cần tự chép vào `src/main/java` hay commit mặc định vào Git.

Với dự án đơn giản, có thể đóng gói annotation và processor chung một JAR; nhưng tách API/implementation giúp app không phải mang toàn bộ dependency nặng của processor ở runtime hoặc compile classpath. Khi tách module, cần bảo đảm dependency và thứ tự build tạo được processor JAR trước khi app cần đến nó.

## 2. Compiler tìm và gọi processor như thế nào?

Cơ chế Java chuẩn là **JSR 269 / Pluggable Annotation Processing API**. Processor thường:

```java
@SupportedAnnotationTypes("com.example.api.GenerateFlag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class FlagProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        // Kiểm tra annotation / sinh source bằng Filer.
        return true;
    }
}
```

Đây là **khung method** chứ chưa là file tự biên dịch: cần import, class/interface thực tế và cấu hình processor. Processor được compiler nạp rồi gọi qua nhiều rounds nếu cần. `@Retention(SOURCE)` trên annotation vẫn đủ để processor nhìn thấy annotation trong lượt compile source; không cần ép retention RUNTIME nếu runtime không tiêu thụ metadata.

Có hai hình thức chọn processor phổ biến:

**A. Service discovery:** processor JAR chứa tệp:

```text
META-INF/services/javax.annotation.processing.Processor
```

Nội dung, mỗi dòng là **tên class đầy đủ** của processor:

```text
com.example.apt.FlagProcessor
```

Khi annotation processing được kích hoạt và discovery được phép trên processor path, Java dùng cơ chế provider để tìm các processor. File service này là **tài nguyên đóng gói trong processor JAR**, không phải dòng code nằm trong `pom.xml` hoặc `build.gradle`. Trường hợp processor đóng gói dưới dạng named module (JPMS) có thể sử dụng khai báo `provides javax.annotation.processing.Processor with ...` trong `module-info.java` theo cách module-path tương ứng.

**B. Chỉ định class processor bằng `-processor`:** ví dụ:

```bash
javac -processor com.example.apt.FlagProcessor ...
```

Cách này chọn class rõ ràng; khi dùng nó phải đảm bảo processor và dependencies có trên `-processorpath` hoặc `--processor-module-path` phù hợp. Tùy build tool, lựa chọn tương đương được ghi trong cấu hình plugin thay vì viết trực tiếp `javac` command.

**An toàn và khả năng tái lập:** nên chỉ định rõ những processor được phép chạy. Không nên dựa vào việc “JAR nào tình cờ nằm trên compile classpath và có provider file thì được chạy” như một hành vi mong muốn.

## 3. Thay đổi quan trọng từ JDK 23: không tự discovery như trước

Đây là một nguyên nhân nổi bật khiến một build “trước đây sinh code, sau khi nâng JDK thì mất code sinh”.

- Với các bản JDK **đến 22**, `javac` truyền thống có thể tự tìm và chạy processor trên classpath mà không cần một tùy chọn xử lý annotation tường minh.
- **Từ JDK 23**, `javac` không tự kích hoạt annotation processing theo cách đó khi không có cấu hình/lệnh xử lý annotation rõ ràng. Thay đổi này được Oracle/OpenJDK công bố để giảm rủi ro thực thi processor ngoài ý muốn.
- Có thể yêu cầu cụ thể processor bằng `-processor`, đặt processor path/module path, hoặc bật chế độ `-proc:full`/`-proc:only` theo khả năng của compiler. Để kiểm soát security, **chỉ định processor cần chạy** và đường dẫn riêng vẫn tốt hơn mở lại mọi discovery ngầm.

Ba chế độ chính:

| Tùy chọn | Công dụng |
|---|---|
| `-proc:none` | Biên dịch **không chạy** annotation processing |
| `-proc:only` | Chỉ chạy annotation processing, không tiếp tục biên dịch bình thường thành classes |
| `-proc:full` | Annotation processing **và** compilation |

`-proc:full` đã được backport đến nhiều dòng cập nhật LTS, nhưng không giả định mọi bản JDK 17 cũ đều hỗ trợ: nên dùng patch version còn được duy trì hoặc chỉ định processor bằng `-processor`. Khi test trên JDK 23+, đặt `-processor` và processor path tường minh làm kết quả dễ hiểu hơn.

**Phân biệt JDK của compiler với `--release`:** nếu chạy `javac` thuộc JDK 24 kèm `--release 17`, luật mặc định về cách khám phá processor thuộc **javac đang chạy (JDK 24)**, trong khi `--release 17` điều khiển mức ngôn ngữ/API đích. Do đó chỉ ghi `<release>17</release>` hoặc Gradle `options.release = 17` **không đưa behavior discovery của JDK 24 trở lại JDK 17**.

Điểm này rất quan trọng khi IDE dùng JDK khác với CI dù cả hai đều build “Java 17”.

## 4. Ví dụ Java 17 chạy thật: sinh class trong compile step

Ví dụ thuần `javac` này cố tình **chỉ định processor tường minh** để không phụ thuộc discovery mặc định của JDK. Dù dùng JDK mới, chương trình vẫn được compile ở `--release 17`.

Đặt ba file sau trong **cùng một thư mục làm việc trống**. Để đơn giản ví dụ dùng *default package*; trong dự án thật nên đặt tên package đầy đủ.

### Tệp GenerateFlag.java

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateFlag {}
```

### Tệp FlagProcessor.java

```java
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.tools.*;

@SupportedAnnotationTypes("GenerateFlag")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class FlagProcessor extends AbstractProcessor {
    private boolean created = false;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver() || created) return true;

        for (Element element :
                round.getElementsAnnotatedWith(GenerateFlag.class)) {
            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile("GeneratedFlag", element);

                try (Writer out = file.openWriter()) {
                    out.write("public final class GeneratedFlag { "
                            + "public static String value() { "
                            + "return \"processor-ran\"; } }");
                }

                created = true;
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.NOTE, "GeneratedFlag created");
            } catch (Exception ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, ex.getMessage(), element);
            }
        }
        return true;
    }
}
```

Ý chính: `RoundEnvironment` tìm class gắn `@GenerateFlag`; `Filer.createSourceFile` tạo Java source mới; `Messager` in một NOTE để ta biết processor đã chạy. Cờ `created` tránh tạo trùng cùng tên source ở những rounds tiếp theo. Trong ứng dụng thực tế, tên source sinh ra phải có namespace/logic tránh đụng nhau và validation đầy đủ.

### Tệp Main.java

```java
@GenerateFlag
public class Main {
    public static void main(String[] args) {
        System.out.println(GeneratedFlag.value());
    }
}
```

Đặc biệt, source `Main.java` **không chứa định nghĩa `GeneratedFlag`**. Class đó phải được sinh bởi processor trong lúc compile.

### Cách compile

Tạo ba thư mục rỗng trong thư mục hiện tại: `processor-classes`, `app-classes` và `generated`. Sau đó:

```bash
javac --release 17 -d processor-classes GenerateFlag.java FlagProcessor.java

javac --release 17 \
  -cp processor-classes \
  -processorpath processor-classes \
  -processor FlagProcessor \
  -s generated \
  -d app-classes \
  Main.java

java -cp app-classes Main
```

Các dòng `\` nối lệnh ở đây là cú pháp của **Bash**; trong Windows PowerShell hoặc cmd hãy đặt toàn bộ lệnh `javac` trên **một dòng**:

```powershell
javac --release 17 -cp processor-classes -processorpath processor-classes -processor FlagProcessor -s generated -d app-classes Main.java
java -cp app-classes Main
```

Kết quả:

```text
Note: GeneratedFlag created
processor-ran
```

`Note: GeneratedFlag created` được `javac` in khi xử lý annotation; `processor-ran` là **stdout của chương trình Main**. Tệp mới xuất hiện:

```text
generated/GeneratedFlag.java
```

và các `.class` tương ứng xuất hiện trong `app-classes`.

Thí nghiệm này đã được kiểm tra bằng `javac` hỗ trợ `--release 17`; processor và ứng dụng đều compile thành công, mã nguồn được tạo tồn tại và chương trình in `processor-ran`. Đây là bằng chứng rõ hơn việc chỉ kiểm tra rằng source chứa `@GenerateFlag`.

Thử **bỏ `-processor FlagProcessor` và `-processorpath processor-classes`** khi chạy với javac JDK 23+, sau đó làm sạch `app-classes`/`generated`: nếu không có cấu hình kích hoạt processing nào khác, class `GeneratedFlag` sẽ không được tạo và `Main.java` sẽ lỗi “cannot find symbol”. Đó là phép thử giúp nhận diện việc thiếu processor, không phải lỗi của annotation `@GenerateFlag`.

## 5. Maven 3.x: khai báo compiler plugin và processor path

Với **Maven 3 + Maven Compiler Plugin 3.x**, cách thường dùng là cấu hình `maven-compiler-plugin` trong `pom.xml`. Ví dụ bên dưới sử dụng **tọa độ giả định** để minh họa hai artifact đã được đóng gói từ trước:

- `com.example:flag-annotations:1.0.0` chứa annotation API.
- `com.example:flag-processor:1.0.0` chứa processor và service registration / class processor.

Đây **không phải dependency thực có thể tải về từ Maven Central**. Hãy thay bằng tọa độ và version của dự án/thư viện bạn thật sự dùng.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>app</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <!-- Annotation type visible when compiling application source. -->
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>flag-annotations</artifactId>
      <version>1.0.0</version>
      <scope>provided</scope>
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
              <groupId>com.example</groupId>
              <artifactId>flag-processor</artifactId>
              <version>1.0.0</version>
            </path>
          </annotationProcessorPaths>

          <annotationProcessors>
            <annotationProcessor>com.example.apt.FlagProcessor</annotationProcessor>
          </annotationProcessors>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**Lưu ý:** `com.example.apt.FlagProcessor` ở POM này là tên class **minh họa của processor đóng gói thật**. Nó khác `FlagProcessor` của ví dụ thuần `javac` dùng default package ở phần 4; phải chọn **đúng fully qualified name** khi áp dụng vào project.

Giải thích những điểm thiết yếu:

- `<release>17</release>`: compile với source/API Java 17; **JDK thực chạy Maven vẫn phải hỗ trợ tham số này**.
- `<annotationProcessorPaths>`: đưa processor JAR và dependencies của nó lên processor path được plugin sử dụng, tách khỏi compile classpath của ứng dụng.
- `<annotationProcessors>`: liệt kê class processor muốn chạy thay vì cho phép chọn mọi processor tìm được. Đây là allowlist minh bạch và hỗ trợ việc xác định lỗi `processor not found`.
- Dependency `flag-annotations`: cung cấp annotation type cho source ứng dụng. `provided` được dùng **nếu runtime không cần chính JAR annotation đó**; đối với annotation dùng ở runtime/reflection, chọn scope thích hợp với nhu cầu thực tế. Không nên sao chép `provided` vô điều kiện cho mọi thư viện.
- Không cần thêm processor như một dependency `compile`/`implementation` bình thường chỉ để kích hoạt nó.

Lệnh kiểm tra:

```bash
mvn -U clean compile
mvn -q -DskipTests=false test
```

`mvn clean compile` giúp xóa sản phẩm sinh cũ và xác minh processor thực sự tạo source mới. Đường dẫn mặc định thường là `target/generated-sources/annotations` trong cấu hình plugin thông dụng; build có thể tùy biến nên hãy dựa vào `-s`/cấu hình thực tế thay vì giả định mọi project đều giống nhau.

Nếu processor chỉ dùng cho `src/test/java` thì phải cấu hình **test compilation** tương ứng; đường dẫn/classpath của main và test không nhất thiết tự giống nhau. Khi sửa POM, hãy **reload Maven project** trong IDE thay vì chỉ thêm một folder bằng tay.

### Cẩn trọng với JDK 23 và phiên bản Maven plugin

Từ JDK 23, không nên trông chờ auto-discovery cũ. Hãy chỉ định processor tường minh trong Maven plugin thích hợp. Với Maven Compiler Plugin 3.x, `annotationProcessorPaths` và `annotationProcessors` là cấu hình chính thống. Tài liệu của từng plugin version có thể có khác biệt về mặc định `proc`; ưu tiên tài liệu **đúng version đã khóa trong POM** và behavior của JDK thật được Maven sử dụng.

Nếu cố ý dùng `<proc>full</proc>` để bật discovery rộng, cần hiểu nó cho phép các processor tìm thấy theo cơ chế tương ứng chạy; phương án này **không thay thế** việc quản lý processor được phép thực thi.

## 6. Maven 4 + Maven Compiler Plugin 4.x: dependency type cho processor

**Đừng lẫn cấu hình Maven 3.x với Maven 4.x.** Các bản Maven Compiler Plugin **4.x** hướng đến Maven 4 có cách khai báo processor qua dependency type như:

- `processor`;
- `classpath-processor`;
- `modular-processor`.

Ví dụ **đoạn minh họa** theo thiết kế Maven 4 (cần ghép trong POM Maven 4 hợp lệ và chọn phiên bản dependency thật):

```xml
<dependencies>
  <dependency>
    <groupId>com.example</groupId>
    <artifactId>flag-processor</artifactId>
    <version>1.0.0</version>
    <type>classpath-processor</type>
  </dependency>
</dependencies>
```

`classpath-processor` thể hiện processor chạy từ processor classpath; `modular-processor` dành cho processor dạng module chạy qua module path; `processor` có thể được plugin suy luận vị trí khi phù hợp. Chọn loại đúng với cách đóng gói processor và tài liệu phiên bản bạn sử dụng, không đặt nhiều loại bừa bãi.

Cách tiếp cận này tạo metadata dependency rõ ràng để plugin biết đó là processor, không phải thư viện runtime thông thường. **Đừng chuyển toàn bộ cấu hình Maven 3 sang Maven 4 theo phép thay tên máy móc**: cần xem plugin 4.x và Maven 4 đã thực sự được dự án áp dụng, cũng như cấu hình của từng processor.

## 7. Gradle: cấu hình annotationProcessor riêng với compileOnly/implementation

Gradle Java plugin cung cấp dependency configuration riêng tên `annotationProcessor`. Với source set main, `compileJava` dùng processor path bắt nguồn từ configuration này; `Gradle` không đơn giản lấy mọi JAR trên compile classpath làm processor.

### build.gradle (Groovy DSL)

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // Annotation type used by source code.
    compileOnly 'com.example:flag-annotations:1.0.0'

    // Actual compiler plugin / code generator.
    annotationProcessor 'com.example:flag-processor:1.0.0'

    // If test sources also use the annotation/processor:
    testCompileOnly 'com.example:flag-annotations:1.0.0'
    testAnnotationProcessor 'com.example:flag-processor:1.0.0'
}
```

### build.gradle.kts (Kotlin DSL)

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    compileOnly("com.example:flag-annotations:1.0.0")
    annotationProcessor("com.example:flag-processor:1.0.0")

    testCompileOnly("com.example:flag-annotations:1.0.0")
    testAnnotationProcessor("com.example:flag-processor:1.0.0")
}
```

Các tọa độ `com.example` là **minh họa** và không chạy nếu chưa có artifact tương ứng; thay bằng artifact thật hoặc `project(":annotation-processor")` khi project dùng multi-module.

**Đừng nhầm:**

- `implementation`: thư viện cần để source ứng dụng biên dịch và chạy.
- `compileOnly`: thư viện cần khi biên dịch, không tự đưa vào runtime; hợp lý cho annotation API không cần lúc chạy.
- `annotationProcessor`: bộ xử lý annotation trong bước biên dịch `main`.
- `testAnnotationProcessor`: bộ xử lý annotation khi biên dịch **test source set**.
- `testImplementation` hoặc `testCompileOnly`: dependencies nguồn test, độc lập với việc processor có được chạy hay không.

Nếu annotation có retention RUNTIME và ứng dụng thực sự dùng reflection đọc nó, chỉ đặt annotation API vào `compileOnly` có thể **không phù hợp**; cần chọn `implementation` hoặc scope bảo đảm runtime classpath đúng nhu cầu.

Với dependency nội bộ có thể dùng:

```groovy
dependencies {
    compileOnly project(':annotation-api')
    annotationProcessor project(':annotation-processor')
}
```

Gradle sẽ xây dựng project processor theo dependency graph nếu cấu hình đúng; không nên copy thủ công một JAR vào thư mục của IDE rồi mong CI tự biết nó.

### Kiểm tra Gradle bằng build thực

```bash
./gradlew clean compileJava
./gradlew clean compileTestJava
./gradlew dependencies --configuration annotationProcessor
./gradlew compileJava --info
```

Trên Windows, dùng `gradlew.bat` thay cho `./gradlew` nếu chạy trong cmd/PowerShell phù hợp. Với Gradle Wrapper, dùng wrapper đã commit trong repo để bản Gradle giữa máy và CI đồng nhất. Lệnh `dependencies` giúp xác minh đúng processor artifact xuất hiện trong configuration.

Thông thường generated source của Java annotation processor nằm dưới `build/generated/sources/annotationProcessor/java/main` đối với source set main và một vị trí tương tự cho test. Nhưng đây là **thư mục output của Gradle build**, không phải directory bắt buộc cho mọi cấu hình/plugin. Kiểm tra `JavaCompile.options.generatedSourceOutputDirectory` hoặc output task nếu dự án có cấu hình đặc biệt.

### Thêm compiler arguments khi processor có options riêng

Processor có thể đọc tùy chọn từ `ProcessingEnvironment.getOptions()` khi compiler truyền `-Akey=value`. Ví dụ nếu **processor thật sự hỗ trợ** option `flag.mode=strict`:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Aflag.mode=strict']
}
```

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-Aflag.mode=strict")
}
```

Nếu processor không khai báo hoặc đọc option `flag.mode`, ví dụ này không có tác dụng nghiệp vụ và compiler có thể cảnh báo không nhận diện option. **Đây không phải cờ chuẩn của Java**: giá trị là hợp đồng riêng của processor.

Với Gradle, sử dụng compiler argument providers hoặc task inputs thích hợp nếu tùy chọn ảnh hưởng kết quả sinh mã và muốn bảo đảm incremental builds / build cache chính xác. Không được lưu các input thay đổi kết quả trong một chỗ ngoài mô hình Gradle mà build task không biết.

## 8. Chuyển từ lệnh javac sang build tool: ánh xạ cấu hình

| Cơ chế `javac` | Maven 3.x | Gradle |
|---|---|---|
| `-cp` / `--class-path` | `<dependencies>` và scope phù hợp | `implementation`, `api`, `compileOnly`, ... |
| `-processorpath` | `<annotationProcessorPaths>` | `annotationProcessor` / `testAnnotationProcessor` |
| `-processor com.example.apt.FlagProcessor` | `<annotationProcessors>` | Tùy chọn compiler args `-processor` khi cần allowlist thêm |
| `-Akey=value` | Compiler argument/processor option thích hợp | `options.compilerArgs` / argument provider |
| `-s path` | Plugin-managed generated-sources directory | Generated source output directory của `JavaCompile` |
| `--release 17` | `<release>17</release>` | Toolchain và/hoặc `options.release = 17` |
| `-proc:none` | Cấu hình `proc=none` nếu cần tắt | `options.compilerArgs` nếu phải tắt rõ ràng |

**Hai lưu ý khi ánh xạ:**

1. `annotationProcessor` là **dependency configuration**, không phải annotation type. Việc compile source có thể thành công dù cấu hình processor path trống nếu mã ứng dụng chưa tham chiếu tới class sinh ra. Do đó build xanh không luôn chứng minh processor chạy.
2. `-processor` có ý nghĩa **chỉ định loại processor cần thực thi**, còn `-processorpath` chỉ xác định **nơi nạp processor**. Processor class nằm trên đường dẫn chưa chắc đang được chọn, và chọn tên class nhưng thiếu artifact thì compiler cũng không thể chạy.

Để kiểm tra nguồn gốc của lỗi, hãy xác minh cả **hai vế**: discovery/selection **và** classpath/path.

## 9. Đồng bộ IntelliJ IDEA với Maven/Gradle

Theo tài liệu IntelliJ IDEA, với project Maven/Gradle có cấu hình annotation processor trong build script, IDE có thể **tự kích hoạt annotation processing và nhập processor path** khi import/reload project.

Vị trí cấu hình IDE:

```text
Settings
  → Build, Execution, Deployment
  → Compiler
  → Annotation Processors
```

Trên trang này có thể có các tùy chọn:

- **Enable annotation processing:** bật xử lý khi IDE tự biên dịch bằng compiler của IntelliJ.
- **Obtain processors from project classpath** hoặc **Processor path:** lựa chọn nguồn processor theo profile và cấu hình import.
- **Processor FQ Name:** danh sách processor cụ thể nếu chỉ định rõ.
- **Production sources / Test sources:** các vị trí nguồn sinh từ IDE build.
- **Annotation processor options:** các cặp tùy chọn riêng của processor (nếu tool hỗ trợ).

Với project được **import từ Maven/Gradle**, thường nên:

1. **Cập nhật `pom.xml` hoặc `build.gradle(.kts)` trước.**
2. **Reload All Maven Projects** hoặc **Reload All Gradle Projects** để IDE nhận model mới.
3. Xác minh compiler JDK, processor path và mục **Enable annotation processing** nếu để IntelliJ build nội bộ.
4. Nếu IntelliJ dùng **delegated build/run** qua Gradle, kiểm tra cấu hình Gradle thực tế; trong trường hợp này build engine là Gradle, nên các setting compiler nội bộ của IDE không thay thế configuration trong Gradle.
5. Xác minh thư mục generated sources được đánh dấu và nhận diện phù hợp. Với Maven, cơ chế import có thể tìm các thư mục dưới `target/generated-sources`; với Gradle, đường dẫn thường ở thư mục build được IDE nạp từ Gradle model.

**Không nên duy trì hai cấu hình thủ công trái nhau**: IDE bật processor A, CI chạy B; IDE dùng version khác; output directory riêng nhưng build tool không biết. Khi đó editor “nhìn thấy” class mà CI không sinh được, hoặc CI đúng mà editor đỏ. Ưu tiên import từ build script để tránh drift.

### Chọn JDK ở ba nơi khác nhau

Khi có bất nhất, cần phân biệt:

- **Project SDK/Language Level:** IDE biết mã nguồn hướng tới version nào.
- **JDK chạy Maven/Gradle:** JVM thực hiện build tool/compilation (Gradle có thể dùng toolchain riêng cho `JavaCompile`).
- **`--release` hoặc target compatibility:** mức API/ngôn ngữ/bytecode được biên dịch.

Ví dụ: IDE Project SDK 17, Gradle daemon dùng JVM 21, Java toolchain được cấu hình 17; một project khác dùng Maven JDK 24 với `<release>17</release>`. **Chúng không phải cấu hình giống hệt**, đặc biệt khi annotation processing của `javac` thay đổi theo bản JDK thực thi.

Để debug, xem **Build Output** của IDE và dòng lệnh/Gradle task/Maven goal thực tế. Nếu code được sinh ở CLI nhưng IDE vẫn báo unresolved, hãy kiểm tra **Reload Project**, generated source roots và cơ chế build delegation trước khi sửa source Java.

## 10. Eclipse và các IDE khác: cùng nguyên lý, khác tích hợp

Eclipse/JDT có cơ chế annotation processing và build integration riêng. Khi nhập Maven project có thể dùng tích hợp Maven và các thành phần hỗ trợ annotation processing; Gradle project có thể dùng Buildship/Gradle import. Tùy phiên bản IDE và plugin được cài, mức tự động cấu hình processor, generated source folder và incremental behavior có thể khác.

Vì vậy hướng xử lý an toàn hơn một danh sách menu cứng:

1. Kiểm tra `mvn clean compile` hoặc `./gradlew clean compileJava` **trên command line** làm chuẩn.
2. Đảm bảo IDE đã import project từ đúng build file và mô hình dependency được làm mới.
3. Xem annotation processing có được bật cho **module và source set thực tế** không.
4. Kiểm tra processor JAR, generated sources folder, output path và JDK/toolchain.
5. Nếu IDE không tích hợp hoàn chỉnh, có thể **delegate build về Maven/Gradle**, thay vì thêm JAR bằng tay trong IDE rồi coi đó là cách cấu hình chính.

Không có bảo đảm rằng mỗi phiên bản IDE dùng cùng đường dẫn hoặc cùng cách xử lý `META-INF/services`, vì vậy ưu tiên tài liệu của phiên bản IDE đang dùng.

## 11. CI và build tái lập: tiêu chí kiểm thử processor đang chạy

Một pipeline nên xác minh không chỉ **mã Java compile thành công**, mà còn **artifact mong đợi thật sự được sinh ra**.

Các bước kiểm tra:

1. **Cố định JDK/toolchain** và bản Maven/Gradle/Compiler Plugin.
2. **Chạy clean build** để loại bỏ output cũ che giấu lỗi processor không chạy.
3. **Kiểm tra task/goal đã gọi**: Maven `compiler:compile`, Gradle `compileJava` hoặc task tương ứng, không chỉ `test` đã được cache/up-to-date.
4. **Kiểm tra đường dẫn generated source** và class files thực tế (hoặc smoke test sử dụng class sinh).
5. **Thêm negative test**: cố tình đưa annotation sai và kỳ vọng processor phát `Diagnostic.Kind.ERROR` nếu processor có validation.
6. **Giữ compiler options nhất quán**, bao gồm `-A...`, source sets, JDK và processor selection.
7. **Không commit output build được tạo ra** làm cách chữa tạm cho IDE: nếu `GeneratedFlag.java` đã nằm sẵn trong source tree, build có thể xanh dù processor không được kích hoạt.

Một test rất hữu ích như ví dụ phần 4: class `Main` tham chiếu `GeneratedFlag` **mà không cung cấp class đó trong source ban đầu**. Nếu compile trên build sạch mà `GeneratedFlag` tồn tại và `Main` chạy đúng, đã có bằng chứng trực tiếp về code generation.

Với các processor chỉ tạo warning/check không sinh source, thiết kế một file input **phải bị diagnostic error** để kiểm tra processor thực sự hoạt động. Một build xanh của chương trình không sử dụng generated classes có thể là “false positive” đối với cấu hình annotation processing.

## 12. Incremental compilation và generated sources

Đặc biệt với Gradle, annotation processing tác động tới **incremental Java compilation** và build cache. Gradle phân biệt những processor có thể xử lý tăng dần theo mô hình như **isolating** và **aggregating**, khi chúng đáp ứng các giới hạn của Gradle.

Khái niệm:

- **Isolating:** output chủ yếu xuất phát từ một input được đánh dấu; Gradle có thể nối file sinh với nguồn liên quan.
- **Aggregating:** output tổng hợp nhiều nguồn được đánh dấu, ví dụ index toàn bộ `@Handler`; thay một input có thể ảnh hưởng artifact tổng hợp.
- **Không hỗ trợ incremental:** Gradle có thể cần compile lại nhiều hơn/đầy đủ nếu processor không đáp ứng hợp đồng tương ứng.

Không nên tự khai báo processor là isolating/aggregating chỉ để tăng tốc; nếu processor không tuân thủ mô hình truy cập input/output của Gradle, kết quả có thể **không được cập nhật đủ** khi source thay đổi. Hãy tham khảo tài liệu Gradle “Incremental annotation processing” và các quy tắc về `Filer`, classpath, annotation retention, task inputs.

**Đầu ra generated sources là sản phẩm của build:**

- Không sửa tay file trong `target/generated-sources` hoặc `build/generated/...`; lần build sau có thể ghi đè hoặc xóa.
- Không sinh vào `src/main/java` nếu không có yêu cầu kiến trúc rõ và cơ chế tránh ghi đè. Điều đó dễ dẫn đến duplicate class, Git noise và IDE thấy source cũ.
- Khi nâng version processor làm thay đổi output, nên clean build một lần để loại source/class cũ.
- Nếu processor đọc file cấu hình bên ngoài, tool phải khai báo input này với build system để cache/incremental compiler không sử dụng kết quả cũ sai.
- Với source sets `main` và `test`, output folder và processor dependencies có thể khác nhau; bảo đảm cả hai được nối vào model IDE.

## 13. Những lỗi phổ biến và cách chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra trước |
|---|---|---|
| `Cannot find symbol GeneratedX` khi compile | Processor không chạy hoặc không sinh class; source generated không được compile | Kiểm tra `-processor`/processor path, generated directory, clean compile |
| CLI Maven/Gradle build đúng, IDE editor báo đỏ | IDE chưa reload, generated sources chưa được nhận diện, JDK/profile khác | Reload project, kiểm tra build delegation và annotation processing settings |
| IDE build đúng, CI thất bại | Phụ thuộc vào config chỉ có trên máy IDE hoặc output cũ | CI clean build với Wrapper/JDK được khóa |
| Sau nâng JDK 23+ mất mã sinh | Dựa vào auto-discovery trên classpath | Khai báo processor tường minh và processor path |
| `Annotation processor 'X' not found` | Processor JAR thiếu hoặc tên class sai | Kiểm tra dependency resolution, FQCN, processor path |
| `ServiceConfigurationError` / provider không nạp được | Service file sai, class chưa đóng gói hoặc dependency processor thiếu | Kiểm tra `META-INF/services/...` trong JAR và classpath của processor |
| `FilerException: Attempt to recreate a file` | Processor sinh trùng cùng tên qua nhiều rounds hoặc từ nhiều processor | Ghi nhận output name/origin, chống tạo trùng |
| Tạo source rồi IDE không cập nhật | Folder generated chưa được model nhận, task chưa chạy hay cache | Xem generated output, rebuild/reimport, kiểm tra source roots |
| Test sources không có class sinh | Chỉ cấu hình processor cho `main` | Gradle `testAnnotationProcessor` / Maven testCompile tương ứng |
| Build rất chậm hoặc lần tăng dần sai | Processor không incremental hoặc input/output không khai báo | Kiểm tra Gradle `--info`, processor documentation, clean build đối chiếu |
| Processor chạy nhưng không tìm annotation | `@SupportedAnnotationTypes`/`@Target`/retention không phù hợp, package sai | Kiểm tra đúng FQCN, source đang compile và các rounds |
| `-proc:none` được bật | Annotation processing bị vô hiệu hóa | Xem compiler arguments thực tế, bỏ flag nếu cần processor |

### Đừng chữa triệu chứng bằng cách sao chép class được sinh

Nếu một người copy `GeneratedFlag.java` từ `build/generated` sang `src/main/java`, IDE có thể hết báo đỏ nhưng CI vẫn không có processor. Sau đó khi processor được sửa và bật lại, project có thể gặp **duplicate class** hoặc giữ hai phiên bản khác nhau. Cách đúng là sửa **cấu hình build, dependency và IDE import**.

### Hỏi “ai là người biên dịch?” trước khi đổi setting

Bốn câu nên kiểm tra theo thứ tự:

1. Lệnh chạy bằng `javac`, Maven, Gradle hay IDE compiler?
2. JDK thực tế nào chạy compiler, và `--release`/toolchain là gì?
3. Processor path, processor class selection và source set đang được compile có chính xác không?
4. Mã sinh có xuất hiện trên filesystem, và IDE có nhập đúng nguồn từ build system không?

Đó là cách phân biệt lỗi **không thực thi processor**, lỗi **processor chạy nhưng không nhận input**, lỗi **processor chạy rồi báo validation error** và lỗi **IDE không index được output**.

## 14. Cấu hình tùy chọn processor một cách nhất quán

Nhiều processor chấp nhận `-Akey=value`, được truy xuất bằng:

```java
String mode = processingEnv.getOptions().get("flag.mode");
```

Đây là đoạn Java **nằm trong processor**, không phải dòng standalone; `flag.mode` là tên tùy chọn do processor tự quy định, không phải tùy chọn Java chuẩn.

Với Maven 3.x có thể chuyển flag qua `compilerArgs` khi plugin/version hỗ trợ:

```xml
<configuration>
  <compilerArgs>
    <arg>-Aflag.mode=strict</arg>
  </compilerArgs>
</configuration>
```

Với Gradle Groovy:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Aflag.mode=strict']
}
```

Với Gradle Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-Aflag.mode=strict")
}
```

Muốn compiler nhận option này là **được processor khai báo hỗ trợ**, processor có thể dùng `@SupportedOptions("flag.mode")` hoặc override `getSupportedOptions()`. Nếu không khai báo, `javac` có thể cảnh báo option không được processor nhận diện.

Khi cùng một option ảnh hưởng code generation, thống nhất nó ở build script/CI; không đặt `flag.mode=strict` riêng chỉ trong IDE. Đối với Gradle incremental/build cache, giá trị option ảnh hưởng task outputs phải được mô hình hóa phù hợp, chẳng hạn qua Compiler Argument Provider khi có input dynamic.

## 15. Lưu ý bảo mật và giới hạn của annotation processing

**Annotation processor là code được thực thi bởi môi trường compiler trong build.** Một JAR processor không phải một file cấu hình “thụ động”: nó có thể chạy code Java khi người dùng build project.

Vì vậy:

- Dùng dependency từ nguồn đáng tin, khóa version và xem xét dependency chain.
- Tránh auto-execution của processor xuất hiện ngẫu nhiên trên compile classpath; cho phép chỉ những processor được biết và cần thiết.
- Không vô điều kiện bật `-proc:full` để quét mọi thứ mà không đánh giá security.
- Không lưu secrets vào `-A...` nếu chúng có thể lộ trong build log, diagnostic hoặc output. Chọn cơ chế bí mật do CI/build tool quản lý và hạn chế cách processor xử lý chúng.
- Kiểm tra output do processor sinh, vì generated code là một phần source chương trình cuối cùng.
- Phân biệt tool chỉ kiểm tra source với annotation processor thật sự: annotation processor được compiler gọi, trong khi một số code generator riêng có task/phần mở rộng Gradle/Maven không dùng JSR 269.

Nếu dùng Kotlin `kapt`, Kotlin Symbol Processing (KSP) hoặc mixed Kotlin/Java project, cấu hình có thể khác **Java `annotationProcessor` thuần**. Không mặc định `annotationProcessor` của Gradle Java plugin sẽ xử lý tất cả Kotlin sources; hãy dùng plugin/task phù hợp công nghệ đang được sử dụng.

## 16. Bài tập thực hành và kiểm tra kiến thức

### Bài 1 — Cùng annotation API nhưng thiếu processor

Một project có `implementation("com.example:annotations:1.0")` nên source chứa `@Mapper` compile được, nhưng `UserMapperImpl` không được tạo. Nguyên nhân có thể là gì?

**Đáp án:** có annotation type trên compile classpath **không bảo đảm processor đã được cấu hình/chạy**. Kiểm tra `annotationProcessor(...)` tương ứng trong Gradle hoặc processor path/processor selection trong Maven. Ngoài ra xác minh processor JAR thực sự tạo loại class đó và có input annotation hợp lệ.

### Bài 2 — Thay JDK và bản --release

Maven dùng JDK 24 nhưng `<release>17</release>`. Có thể dựa vào luật auto-discovery của javac JDK 17 không?

**Đáp án:** không. `--release 17` giới hạn language/API target, nhưng cách xử lý mặc định annotation processors là hành vi của **javac JDK 24** đang chạy. Cần cấu hình processor rõ ràng.

### Bài 3 — Chọn scope Gradle

Lệnh nào phù hợp nhất để compiler Java của `main` chạy một processor nhưng không đưa processor vào runtime classpath?

**Đáp án:** `annotationProcessor("group:processor:version")`. Annotation API dùng `compileOnly` nếu chỉ cần ở compile time, hoặc `implementation` nếu ứng dụng cần ở runtime.

### Bài 4 — IDE khác CI

`./gradlew clean compileJava` thành công và source sinh có trong `build/generated` nhưng IntelliJ báo unresolved. Có nên chép file sinh sang `src/main/java` không?

**Đáp án:** không. Reload Gradle project, kiểm tra IDE đang delegate build thế nào, project SDK/toolchain, annotation processing settings và generated source roots.

### Bài 5 — ServiceLoader và processor selection

Một JAR có `META-INF/services/javax.annotation.processing.Processor` nhưng build JDK 23 không có tùy chọn annotation processing hoặc processor path. Chỉ đặt JAR lên compile classpath có đủ không?

**Đáp án:** không nên kỳ vọng. JDK 23+ yêu cầu cấu hình kích hoạt annotation processing rõ. Chỉ định processor và processor path qua build tool là cách đáng tin hơn.

### Bài 6 — Tệp được sinh ở vòng nào?

Processor tạo `GeneratedFlag.java` trong Round 1. Có cần compile lại `GeneratedFlag.java` bằng tay như source bình thường không?

**Đáp án:** khi `javac` đang thực hiện annotation processing theo hợp đồng và file được tạo qua `Filer` đúng cách, compiler có thể đưa source mới vào các rounds/compilation tiếp theo; thí nghiệm `javac` phía trên đã chứng minh nó được biên dịch thành `GeneratedFlag.class` trong build đó. Không cần sao chép vào source tree hoặc tạo lệnh compile tay riêng cho trường hợp này.

### Bài 7 — CI có build xanh nhưng processor bị tắt

Nếu ứng dụng không tham chiếu tới class sinh, một `mvn compile` thành công có chứng minh processor chạy không?

**Đáp án:** không. Cần kiểm tra output/diagnostic hoặc tạo test input sai phải bị `ERROR`, hay một smoke test tham chiếu class sinh ra.

### Bài 8 — -Werror và processor diagnostics

Processor in một `WARNING` vì input chưa tối ưu. Với `-Werror`, build có thể thất bại không?

**Đáp án:** có, vì flag yêu cầu compiler coi warning là lỗi theo quy định. Để biết tình trạng thực tế, xem compiler args và diagnostic trong build log.

### Bài 9 — Nơi cấu hình là “source of truth”

Cần chạy processor ở CI, Maven CLI và IntelliJ. Nên chỉ bật “Enable annotation processing” trong IDE rồi để POM không khai báo processor không?

**Đáp án:** không. Khai báo đầy đủ trong POM rồi reload Maven project; IDE setting hỗ trợ tương ứng, không thay thế build script.

### Bài 10 — Test source set

Main sources được Gradle sinh mã đúng, nhưng code trong `src/test/java` cần processor lại lỗi. Nên kiểm tra gì?

**Đáp án:** processor dependency của source set test như `testAnnotationProcessor` và annotation API cho test; không mặc định `annotationProcessor` của main sẽ tự áp dụng đúng cho mọi compilation task.

## 17. Checklist triển khai và tài liệu gốc

Trước khi kết luận “annotation processing đã hoạt động”, hãy chắc rằng:

- [ ] Đúng **JDK thực chạy compile** và source/target toolchain.
- [ ] Annotation API có trên compile classpath của source set cần dùng.
- [ ] Processor JAR **và dependencies** nằm trên processor path.
- [ ] Processor được chọn/đăng ký đúng (FQCN, service file, hoặc module provider).
- [ ] JDK 23+ có cấu hình kích hoạt annotation processing rõ.
- [ ] `mvn clean compile` hoặc `./gradlew clean compileJava` thật sự sinh code trên output sạch.
- [ ] Generated sources do Maven/Gradle quản lý; không copy/commit output thay cho build.
- [ ] IDE đã import/reload build model, có JDK và generated source roots phù hợp.
- [ ] CI dùng version có thể tái lập và có smoke/negative test.
- [ ] Tùy chọn `-A...` của processor được khai báo và đồng bộ build/CI/IDE.

Tài liệu tham khảo có thể tra trực tiếp:

1. [Oracle/OpenJDK — JDK 23: Annotation processing disabled by default](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html) — thay đổi quan trọng đối với auto-discovery từ JDK 23.
2. [Inside Java — JDK 23 changes default annotation processing policy](https://inside.java/2024/06/18/quality-heads-up/) — giải thích `-proc:full`, `-proc:only`, `-processor` và lộ trình chuyển đổi.
3. [JDK 17 javac manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — `-processorpath`, `-processor`, `-s`, `-proc` và cách dùng compiler.
4. [Maven Compiler Plugin 3.14.1 — compile-mojo](https://maven.apache.org/plugins-archives/maven-compiler-plugin-3.14.1/compile-mojo.html) — `annotationProcessorPaths`, `annotationProcessors`, `release`.
5. [Maven Compiler Plugin 4.x — annotation processor examples](https://maven.apache.org/plugins-archives/maven-compiler-plugin-LATEST-4.x/examples/annotation-processor.html) — hình thức processor dependency của Maven 4.
6. [Gradle Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html) — `annotationProcessor`, source sets, JavaCompile, incremental annotation processing.
7. [Gradle Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html) — vai trò `compileOnly`, `implementation`, `annotationProcessor`.
8. [IntelliJ IDEA — Configure annotation processors](https://www.jetbrains.com/help/idea/annotation-processors-support.html) — annotation processing profiles và import processor path từ Maven/Gradle.
9. [IntelliJ IDEA — Maven importing](https://www.jetbrains.com/help/idea/maven-importing.html) — generated sources folders và cấu hình import.
10. [Java SE 17 — Processor API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html) — khám phá, điều phối và hợp đồng annotation processing.

**Kết luận:** annotation processor là một **bước thực thi trong compilation**, không phải metadata tự động hóa mọi việc. Khi cấu hình processor rõ ràng trong Maven/Gradle, duy trì toolchain và generated sources đúng, rồi để IDE đồng bộ từ build model, chương trình sẽ bớt phụ thuộc máy cá nhân và CI có thể tái lập kết quả sinh mã.
