# Annotation processing và mã nguồn được sinh trong build

Trong Java, không phải mọi file `.java` đều phải do lập trình viên viết bằng tay. Trong quá trình biên dịch, compiler có thể chạy **annotation processor** để đọc annotation và thông tin kiểu dữ liệu, sau đó tạo thêm mã nguồn, resource hoặc metadata cho ứng dụng. Compiler tiếp tục xử lý những file được sinh ra trong cùng quá trình build.

Cơ chế này được dùng trong nhiều thư viện và framework, chẳng hạn MapStruct sinh mapper implementation, Dagger sinh mã phục vụ dependency injection, AutoService sinh metadata service provider và Lombok tham gia quá trình xử lý annotation để hỗ trợ mã nguồn ngắn gọn hơn. Khi build thành công trên máy này nhưng máy khác không sinh mã hoặc không tìm thấy class được tạo, nguyên nhân thường nằm ở cách khai báo processor, classpath, phiên bản JDK hoặc thư mục đầu ra.

Bài này giải thích annotation processing trong Java, vòng đời xử lý, cách tạo mã nguồn, cách cấu hình Maven và Gradle, cũng như cách kiểm tra mã được sinh trong build.

## 1. Annotation processing là gì?

Annotation là metadata gắn với declaration như class, method, field, parameter hoặc package. Ví dụ:

```java
@Deprecated
public void oldMethod() {
    // ...
}
```

Một annotation processor là thành phần chạy trong quá trình biên dịch, có thể đọc annotation và mô hình chương trình để thực hiện hành động. Hành động thường gặp là:

- Sinh thêm file `.java` để compiler biên dịch cùng project.
- Sinh resource hoặc metadata vào output directory.
- Kiểm tra quy tắc và báo lỗi/warning nếu mã nguồn không hợp lệ.
- Tạo registry, adapter, mapper, factory hoặc implementation dựa trên khai báo của developer.

Annotation processing chuẩn của Java được định nghĩa bởi API `javax.annotation.processing` và `javax.lang.model`, thuộc Java Compiler API. Cơ chế này thường được gọi là JSR 269.

Điểm quan trọng: annotation processor chạy **trong lúc build/compile**. Nó không phải một phần của luồng xử lý annotation bằng reflection lúc ứng dụng đang chạy. Processor có thể tạo class mà ứng dụng sẽ sử dụng sau đó, nhưng chính processor thường không cần được đưa vào runtime của ứng dụng.

## 2. Vì sao build cần sinh mã nguồn?

Một số thao tác có thể được tạo tự động từ khai báo có cấu trúc, giúp giảm mã lặp và giữ cho các phần liên quan đồng bộ.

Ví dụ developer khai báo:

```java
@GenerateGreeting
public class Customer {
}
```

Processor có thể sinh `CustomerGreeting.java`:

```java
public final class CustomerGreeting {
    public static String message() {
        return "Hello from Customer";
    }
}
```

Compiler sau đó biên dịch cả `Customer.java` và `CustomerGreeting.java` thành các file `.class`. Developer có thể gọi class được sinh như một phần của ứng dụng.

Các ứng dụng thực tế:

| Công việc | Ví dụ sử dụng annotation processing |
|---|---|
| Mapping giữa các kiểu dữ liệu | MapStruct sinh implementation của mapper interface |
| Dependency injection | Dagger sinh factory và component implementation |
| Đăng ký service | AutoService sinh file `META-INF/services/...` |
| Kiểm tra API hoặc quy ước | Processor kiểm tra annotation và phát diagnostic tại compile time |
| Sinh adapter/boilerplate | Processor tạo builder, metadata hoặc lớp hỗ trợ theo khai báo |

Không phải công cụ nào có chữ “annotation” cũng là annotation processor. Một số framework đọc annotation bằng reflection lúc runtime; một số plugin phân tích bytecode sau compile; một số công cụ dùng compiler plugin hoặc source transformation riêng. Cần xem cơ chế thực tế của thư viện trước khi quyết định cấu hình dependency.

## 3. Annotation, retention và processor

Một annotation có thể được khai báo như sau:

```java
package com.example.codegen;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
```

Ba thành phần đáng chú ý:

- `@Target(ElementType.TYPE)` giới hạn annotation có thể đặt trên khai báo kiểu như class, interface, enum hoặc record.
- `@Retention(RetentionPolicy.SOURCE)` giữ annotation trong mã nguồn để compiler/processor đọc, nhưng annotation không được lưu vào bytecode.
- `@interface` khai báo một annotation type.

### 3.1. Ba chính sách retention

| Retention | Annotation có ở đâu? | Mục đích thường gặp |
|---|---|---|
| `SOURCE` | Mã nguồn và mô hình compile; bị loại khỏi class file | Annotation chỉ phục vụ build, sinh mã hoặc kiểm tra compile |
| `CLASS` | Được lưu trong class file, nhưng không cần có mặt qua runtime reflection | Metadata cho bytecode tool hoặc processor ở giai đoạn phù hợp |
| `RUNTIME` | Được lưu trong class file và có thể đọc bằng reflection | Framework cần kiểm tra annotation lúc ứng dụng chạy |

Annotation processor có thể xử lý annotation `SOURCE`, vì processor chạy khi compiler vẫn đang xử lý mã nguồn. Không cần đặt retention là `RUNTIME` chỉ để processor nhìn thấy annotation.

Nếu cùng một annotation vừa được dùng để sinh mã trong build vừa cần framework đọc lúc runtime, có thể chọn `RUNTIME`. Tuy nhiên, hãy cân nhắc mục đích thực tế và không giữ metadata lâu hơn mức cần thiết.

## 4. Vòng đời annotation processing

Annotation processing diễn ra trong một hoặc nhiều **round** (vòng xử lý). Compiler tìm processor được cấu hình, khởi tạo processor, rồi gọi `process` với tập annotation và các phần tử liên quan trong round hiện tại.

Quy trình khái quát:

```text
Mã nguồn ban đầu
       |
       v
Compiler tìm và khởi tạo processors
       |
       v
Round 1: processor đọc annotation/model
       |
       +----> sinh .java / resource
       |              |
       |              v
       |       Compiler nhận source mới
       |              |
       +--------------+
       |
       v
Round tiếp theo nếu có source mới
       |
       v
Round cuối: processingOver() = true
       |
       v
Compiler hoàn tất compile và tạo .class
```

Một processor có thể sinh thêm source. Những source mới được đưa vào các round tiếp theo để processor khác hoặc compiler xử lý. Quá trình kết thúc khi không còn source mới cần xử lý và compiler đi vào round cuối.

### 4.1. `process` và `RoundEnvironment`

Processor thường kế thừa `AbstractProcessor` và cài đặt phương thức:

```java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv
)
```

Trong đó:

- `annotations` là các annotation type được processor quan tâm trong round.
- `roundEnv` cung cấp các phần tử được đánh dấu annotation và trạng thái round.
- `roundEnv.getElementsAnnotatedWith(...)` tìm các phần tử mang annotation.
- `roundEnv.processingOver()` cho biết đã đến round cuối hay chưa.
- `roundEnv.errorRaised()` cho biết có lỗi được phát ra trong các round trước hay không.

Processor có thể tạo file bằng `Filer`, phát thông báo bằng `Messager` và truy vấn kiểu/package bằng `Elements` cùng `Types` thông qua `ProcessingEnvironment`.

### 4.2. Giá trị trả về của `process`

Nếu processor trả về `true`, nó cho biết các annotation type trong round đã được processor claim/tiêu thụ. Nếu trả về `false`, các processor khác vẫn có thể xử lý những annotation type đó.

Điều này hữu ích khi nhiều processor cùng quan tâm một annotation hoặc annotation được dùng trong một hệ sinh thái processor phối hợp. Không nên trả về `true` một cách tùy tiện nếu processor không thực sự xử lý annotation.

### 4.3. Không sinh lặp cùng một file

Trong một compilation, `Filer` không cho phép nhiều lần tạo cùng một file output. Nếu processor cố tạo lại một qualified name đã được tạo trong compilation, compiler có thể báo `FilerException` hoặc lỗi tương ứng.

Processor nên:

- Sinh file có tên ổn định và duy nhất.
- Kiểm tra phần tử đầu vào trước khi tạo output.
- Không tạo lại file trong các round tiếp theo nếu đã xử lý.
- Xử lý trường hợp annotation được áp dụng trên nhiều phần tử.
- Phát diagnostic rõ ràng khi đầu vào xung đột hoặc không hợp lệ.

## 5. Viết một annotation processor đơn giản

Để minh họa, ta xây dựng một processor đọc `@GenerateGreeting` trên class và sinh một class có hậu tố `Greeting`.

Ví dụ cấu trúc module:

```text
greeting-annotations/
└── src/main/java/com/example/codegen/
    └── GenerateGreeting.java

greeting-processor/
└── src/main/java/com/example/codegen/
    └── GreetingProcessor.java

app/
└── src/main/java/com/example/app/
    └── Customer.java
```

Trong một dự án thực tế, annotation API và processor thường được tách thành artifact/module riêng để consumer chỉ phụ thuộc vào annotation ở compile time và đưa processor vào processor path. Cấu trúc trên làm rõ trách nhiệm của từng phần.

### 5.1. Annotation type

File `GenerateGreeting.java`:

```java
package com.example.codegen;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface GenerateGreeting {
}
```

### 5.2. Processor implementation

File `GreetingProcessor.java`:

```java
package com.example.codegen;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;

import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.FilerException;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.PackageElement;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("com.example.codegen.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_21)
public final class GreetingProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element : roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {
            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateGreeting chỉ dùng trên class",
                        element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            PackageElement pkg = processingEnv.getElementUtils().getPackageOf(type);
            String packageName = pkg.isUnnamed()
                    ? ""
                    : pkg.getQualifiedName().toString();

            String generatedSimpleName = type.getSimpleName() + "Greeting";
            String qualifiedName = packageName.isEmpty()
                    ? generatedSimpleName
                    : packageName + "." + generatedSimpleName;

            try {
                JavaFileObject sourceFile = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, type);

                try (Writer writer = sourceFile.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n\n");
                    }

                    writer.write("public final class " + generatedSimpleName + " {\n");
                    writer.write("    private " + generatedSimpleName + "() {}\n");
                    writer.write("    public static String message() {\n");
                    writer.write("        return \"Hello from "
                            + type.getSimpleName() + "\";\n");
                    writer.write("    }\n");
                    writer.write("}\n");
                }
            } catch (FilerException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Source đã được tạo hoặc bị trùng: " + qualifiedName,
                        element);
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Không thể tạo source " + qualifiedName + ": " + ex.getMessage(),
                        element);
            }
        }

        return true;
    }
}
```

Đây là ví dụ nhập môn. Processor production cần xử lý đầy đủ escaping của chuỗi, nested type, tên package, nhiều loại element, generic type và trường hợp trùng tên. Không nên ghép dữ liệu người dùng trực tiếp vào source mà không escape các ký tự đặc biệt.

### 5.3. Đăng ký processor để compiler tìm thấy

Với cơ chế service discovery truyền thống, thêm file:

```text
META-INF/services/javax.annotation.processing.Processor
```

Nội dung file là tên đầy đủ của processor, mỗi dòng một processor:

```text
com.example.codegen.GreetingProcessor
```

File này phải được đóng gói vào JAR của processor. Nếu build tool cấu hình processor tường minh bằng tên class hoặc processor path, có thể không cần dựa vào discovery tự động, nhưng service registration vẫn là quy ước phổ biến khi phát hành processor.

Với module Java có `module-info.java`, processor module có thể đăng ký service bằng khai báo `provides`:

```java
module com.example.greeting.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with com.example.codegen.GreetingProcessor;
}
```

Khi phát hành processor dưới dạng module, cần bảo đảm module path và module descriptor phù hợp với cách build tool khởi chạy compiler/processor.

### 5.4. Sử dụng annotation trong ứng dụng

File `Customer.java`:

```java
package com.example.app;

import com.example.codegen.GenerateGreeting;

@GenerateGreeting
public class Customer {
}
```

Sau annotation processing, compiler có thể nhận source `CustomerGreeting.java` trong package `com.example.app`. Ứng dụng có thể gọi class đó:

```java
package com.example.app;

public class Main {
    public static void main(String[] args) {
        System.out.println(CustomerGreeting.message());
    }
}
```

Nếu processor không chạy, `CustomerGreeting` không được tạo và compile sẽ báo không tìm thấy symbol. Nếu source được tạo nhưng không được compile hoặc output directory không được đưa vào source set, ứng dụng vẫn có thể thiếu class khi chạy.

## 6. Dùng `javac` trực tiếp với annotation processor

Compiler có các tùy chọn để chỉ định processor và nơi lưu generated source:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-processorpath` hoặc `--processor-path` | Nơi tìm annotation processor và dependency của processor |
| `-processor` | Chỉ định tên processor cần chạy |
| `-s <dir>` | Thư mục lưu source được sinh |
| `-d <dir>` | Thư mục lưu class file |
| `-proc:none` | Tắt annotation processing |
| `-proc:only` | Chỉ chạy annotation processing, không thực hiện compile bình thường |
| `-proc:full` | Yêu cầu annotation processing và compilation đầy đủ |
| `--processor-module-path` | Nơi tìm processor được tổ chức dưới dạng module |

Ví dụ trên Linux/macOS:

```bash
javac \
  -cp greeting-annotations.jar \
  -processorpath "greeting-processor.jar:greeting-annotations.jar" \
  -processor com.example.codegen.GreetingProcessor \
  -s build/generated-sources \
  -d build/classes \
  src/main/java/com/example/app/Customer.java \
  src/main/java/com/example/app/Main.java
```

Trên Windows, separator giữa các mục classpath/processor path là dấu `;`:

```bat
javac -cp greeting-annotations.jar -processorpath "greeting-processor.jar;greeting-annotations.jar" -processor com.example.codegen.GreetingProcessor -s build\generated-sources -d build\classes src\main\java\com\example\app\Customer.java src\main\java\com\example\app\Main.java
```

Trong lệnh này:

- `-cp` cung cấp annotation API để compiler hiểu `@GenerateGreeting`.
- `-processorpath` cung cấp processor và dependency mà processor cần khi chạy.
- `-processor` chỉ định processor cụ thể.
- `-s` chọn thư mục source output.
- `-d` chọn thư mục class output.

Compile classpath và processor path có trách nhiệm khác nhau. Đưa processor vào runtime classpath của ứng dụng không phải cách cấu hình chuẩn để chạy annotation processing.

## 7. Maven: cấu hình annotation processor

Với Maven, annotation processor thường được cấu hình trong Maven Compiler Plugin. Tách annotation API và processor thành artifact riêng giúp dependency của ứng dụng rõ ràng.

Ví dụ POM:

```xml
<dependencies>
    <!-- Annotation type mà source code của ứng dụng sử dụng -->
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>greeting-annotations</artifactId>
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
                <release>21</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.example</groupId>
                        <artifactId>greeting-processor</artifactId>
                        <version>1.0.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Ở đây:

- `greeting-annotations` có trên compile classpath để mã nguồn import annotation.
- `greeting-processor` được cung cấp cho compiler như annotation processor.
- Processor path được quản lý riêng với dependency runtime của ứng dụng.
- Maven Compiler Plugin gọi compiler và tích hợp source được sinh vào quá trình compile.

Đường dẫn generated source mặc định thường nằm dưới `target/generated-sources/annotations`. Compiler plugin quản lý source output của annotation processing; không nên tự thêm cùng thư mục nhiều lần hoặc commit file được sinh vào Git.

### 7.1. Chỉ định processor cụ thể

Khi cần kiểm soát processor được chạy, Maven Compiler Plugin hỗ trợ cấu hình processor theo phiên bản plugin/JDK tương ứng. Có thể dùng phần `<annotationProcessors>` để khai báo tên processor khi dự án cần danh sách tường minh.

Ví dụ cấu hình:

```xml
<configuration>
    <annotationProcessors>
        <annotationProcessor>com.example.codegen.GreetingProcessor</annotationProcessor>
    </annotationProcessors>
    <annotationProcessorPaths>
        <path>
            <groupId>com.example</groupId>
            <artifactId>greeting-processor</artifactId>
            <version>1.0.0</version>
        </path>
    </annotationProcessorPaths>
</configuration>
```

Chỉ khai báo processor path mà không có annotation API trên compile classpath có thể khiến mã nguồn ứng dụng không import được annotation. Ngược lại, chỉ khai báo annotation API không bảo đảm processor được phát hiện và chạy.

### 7.2. Kiểm tra Maven build

Chạy compile với log chi tiết:

```bash
./mvnw -X clean compile
```

Quan sát compiler arguments, processor path và thông báo processor. Có thể kiểm tra thư mục:

```text
target/
├── classes/
│   └── ...
└── generated-sources/
    └── annotations/
        └── ...
```

Nếu thư mục generated source rỗng, kiểm tra processor có được cấu hình, annotation có xuất hiện trên source element, processor có claim đúng annotation và compiler có thực sự chạy processing hay không.

## 8. Gradle: `annotationProcessor` và generated sources

Gradle Java plugin cung cấp configuration riêng cho annotation processor. Không nên khai báo processor như dependency `implementation` chỉ vì nó được dùng trong quá trình compile.

Ví dụ Kotlin DSL:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    compileOnly("com.example:greeting-annotations:1.0.0")
    annotationProcessor("com.example:greeting-processor:1.0.0")

    testCompileOnly("com.example:greeting-annotations:1.0.0")
    testAnnotationProcessor("com.example:greeting-processor:1.0.0")
}
```

Với Groovy DSL:

```groovy
dependencies {
    compileOnly 'com.example:greeting-annotations:1.0.0'
    annotationProcessor 'com.example:greeting-processor:1.0.0'

    testCompileOnly 'com.example:greeting-annotations:1.0.0'
    testAnnotationProcessor 'com.example:greeting-processor:1.0.0'
}
```

`annotationProcessor` dành cho processor chạy khi compile mã nguồn chính. `testAnnotationProcessor` dành cho processor chạy khi compile mã nguồn test. Nếu annotation chỉ dùng ở source main thì không cần khai báo test configuration trừ khi test cũng sử dụng annotation đó.

### 8.1. Thư mục generated source mặc định

Với Java plugin, Gradle thường đặt source do annotation processing tạo tại các thư mục tương tự:

```text
build/generated/sources/annotationProcessor/java/main/
build/generated/sources/annotationProcessor/java/test/
```

Các source này được kết nối với compile task tương ứng. Khi chạy `compileJava`, Gradle chuẩn bị processor path, chạy compiler và thu nhận source được sinh. Không cần tự thêm generated source directory vào `sourceSets` nếu đang dùng annotation processing chuẩn của Java plugin.

Khi task `clean` xóa `build/`, generated source cũng được tạo lại ở lần build tiếp theo. Vì vậy không nên sửa tay hoặc commit các file trong thư mục generated output.

### 8.2. Phân biệt annotation processor với task sinh source riêng

Không phải mọi code generation đều dùng JSR 269. Một plugin Gradle có thể đăng ký task riêng để sinh `.java` từ OpenAPI schema, Protocol Buffers, grammar hoặc file cấu hình.

Với task riêng, cần khai báo output của task và nối output đó vào source set/compile task theo API Gradle. Ví dụ khái quát:

```kotlin
val generatedApiDir = layout.buildDirectory.dir("generated/sources/api/main")

val generateApi by tasks.registering {
    outputs.dir(generatedApiDir)

    doLast {
        // Gọi generator và ghi source vào generatedApiDir.get().asFile
    }
}

sourceSets.main {
    java.srcDir(generatedApiDir)
}

tasks.named<JavaCompile>("compileJava") {
    dependsOn(generateApi)
}
```

Đây chỉ là minh họa cách liên kết task output với source set; task generator thực tế cần khai báo input/output chính xác và phải tạo file trước khi compile. Annotation processor được Gradle Java plugin điều phối qua `annotationProcessor`; task generator riêng có vòng đời và dependency task riêng.

## 9. Annotation processor path khác compile classpath và runtime classpath

Có ba môi trường dependency cần phân biệt:

| Path | Thành phần cần có | Ai sử dụng? |
|---|---|---|
| Compile classpath | Annotation API, thư viện mà source code tham chiếu | Java compiler khi compile mã nguồn ứng dụng |
| Processor path | Annotation processor và dependency của chính processor | Compiler host khi chạy processor |
| Runtime classpath/module path | Lớp ứng dụng và thư viện cần khi ứng dụng thực thi | JVM của ứng dụng |

Ví dụ, một ứng dụng dùng MapStruct:

- Annotation API như `org.mapstruct.Mapper` cần có trên compile classpath.
- MapStruct processor cần có trên annotation processor path.
- Mapper implementation được sinh ra sẽ trở thành class của ứng dụng.
- Processor thường không cần có trong runtime classpath sau khi compile.

Nếu đặt processor vào `implementation`, nó có thể bị đưa vào dependency graph/runtime packaging dù không cần. Nếu chỉ khai báo processor trong `annotationProcessor` mà quên annotation API, source code có thể không compile được vì không tìm thấy annotation type.

## 10. JDK hiện đại và việc kích hoạt annotation processing

Không nên dựa vào giả định rằng compiler luôn tự động chạy mọi processor tìm thấy trong classpath. Với các JDK hiện đại, đặc biệt từ JDK 23, việc chạy annotation processor cần được cấu hình rõ ràng theo cơ chế compiler/build tool; các dự án nên chỉ định processor path hoặc processor cần dùng thay vì phụ thuộc vào discovery ngầm.

Các cách kích hoạt tường minh ở mức `javac` gồm:

- Chỉ định processor bằng `-processor`.
- Cung cấp `--processor-path` hoặc `--processor-module-path`.
- Chọn chế độ annotation processing phù hợp bằng tùy chọn `-proc` khi cần.

Maven Compiler Plugin và Gradle Java plugin có cấu hình riêng để truyền processor path. Việc khai báo `annotationProcessor` trong Gradle hoặc `annotationProcessorPaths` trong Maven làm cho mục đích build rõ ràng và giảm phụ thuộc vào cách compiler dò processor trên compile classpath.

Khi nâng JDK mà processor ngừng chạy, hãy kiểm tra compiler options và build tool/plugin version. Đừng vội kết luận annotation của source bị sai nếu generated source đột nhiên không xuất hiện sau khi đổi JDK.

## 11. Annotation processor và các công cụ phổ biến

Một số thư viện dùng annotation processing theo các cách khác nhau:

### MapStruct

MapStruct đọc mapper interface và annotation mapping để sinh implementation Java trong compile time. Ứng dụng compile classpath cần MapStruct API; processor được khai báo ở annotation processor path.

Ví dụ ý tưởng:

```java
@Mapper
public interface CustomerMapper {
    CustomerDto toDto(Customer customer);
}
```

Processor sinh implementation của `CustomerMapper`, giúp tránh phải viết mapper thủ công. Nếu processor không chạy, ứng dụng có thể báo không tìm thấy implementation hoặc lỗi khi framework tìm bean.

### Dagger

Dagger sử dụng annotation processing để sinh factory và component implementation từ các annotation như `@Component`, `@Module` và `@Inject`. Generated code là một phần của compile output; dependency runtime của ứng dụng thường là API/runtime thành phần cần thiết, không phải processor dùng để sinh code.

### AutoService

AutoService có thể sinh metadata `META-INF/services` từ annotation `@AutoService`. Nếu processor không chạy hoặc resource không được đưa vào JAR, `ServiceLoader` có thể không tìm thấy provider dù class implementation đã được compile.

### Lombok

Lombok dùng annotation processing và tích hợp sâu với compiler để hỗ trợ các cấu trúc như getter, setter, constructor hoặc builder. Vì cách hoạt động của Lombok có các chi tiết phụ thuộc compiler và IDE, cần cấu hình plugin/processor tương thích với JDK và IDE đang dùng. Trong dự án, thường khai báo Lombok ở compile-only và annotation processor path theo hướng dẫn của phiên bản Lombok.

## 12. Incremental annotation processing

Build tool có thể tối ưu bằng cách chỉ xử lý phần source bị ảnh hưởng thay vì chạy lại toàn bộ project. Annotation processor cần tuân thủ hợp đồng incremental của build tool để Gradle biết tác động của từng input lên generated output.

Gradle phân loại processor theo các kiểu phổ biến:

- **Isolating**: mỗi output được tạo từ một input type riêng; thay đổi một type có thể chỉ cần tạo lại output liên quan.
- **Aggregating**: output phụ thuộc vào tập hợp nhiều input; thay đổi một input có thể ảnh hưởng đến output tổng hợp.
- **Dynamic**: processor khai báo loại hành vi theo cơ chế hỗ trợ của Gradle và có thể xác định ở runtime processing.

Processor có thể khai báo loại incremental trong file metadata của JAR:

```text
META-INF/gradle/incremental.annotation.processors
```

Nội dung có dạng tên processor và loại tương ứng, ví dụ:

```text
com.example.codegen.GreetingProcessor,isolating
```

Chỉ khai báo `isolating` nếu processor thực sự đáp ứng quy tắc isolating. Nếu output tổng hợp từ nhiều source mà khai báo sai, Gradle có thể bỏ qua input cần thiết hoặc tạo kết quả không chính xác khi incremental build. Nếu processor không hỗ trợ incremental, build vẫn có thể chạy nhưng Gradle có thể phải xử lý rộng hơn.

### 12.1. Quy tắc thiết kế processor thân thiện incremental

- Tạo output gắn với input rõ ràng.
- Truyền originating elements vào `Filer.createSourceFile`/`createResource` khi phù hợp.
- Không đọc tùy tiện mọi file ngoài source model mà không khai báo nguồn phụ thuộc.
- Tránh output toàn cục nếu thực chất processor có thể tạo output riêng cho từng type.
- Nếu tạo registry tổng hợp, phân loại processor là aggregating.
- Không ghi file ngoài output location do build tool quản lý.

Incremental processing là hợp đồng kỹ thuật, không phải nhãn để tăng tốc tùy ý. Nếu processor có side effect hoặc đọc dữ liệu không được khai báo, cache và incremental build có thể cho kết quả sai.

## 13. Generated source nằm ở đâu và có nên commit không?

Generated source thường nằm trong build output, không nằm chung với source do con người duy trì.

| Công cụ | Thư mục thường gặp |
|---|---|
| Maven Compiler Plugin | `target/generated-sources/annotations/` |
| Gradle Java plugin, main | `build/generated/sources/annotationProcessor/java/main/` |
| Gradle Java plugin, test | `build/generated/sources/annotationProcessor/java/test/` |
| Generator task riêng | Thường dưới `build/generated/...` hoặc `target/generated-sources/...` theo cấu hình |

Thông thường, không commit generated source vì:

- File có thể được tái tạo từ source, annotation và processor version.
- Generated code có thể rất dài và gây nhiễu trong review.
- Commit file sinh ra có thể dẫn đến lệch giữa output và processor hiện tại.
- Build sạch phải tái tạo được output nếu cấu hình đúng.

Một số dự án chủ động commit generated code vì consumer không chạy generator hoặc vì quy trình phát hành yêu cầu source artifact cụ thể. Đây là quyết định dự án, cần có lý do và cách xác nhận output luôn đồng bộ. Với annotation processing thông thường, hãy để build tool quản lý generated directory và thêm nó vào `.gitignore` thông qua quy tắc ignore `build/` hoặc `target/` phù hợp.

Không sửa tay file trong generated directory. Nếu muốn thay đổi hành vi, hãy sửa annotation, source input, processor hoặc cấu hình build. Thay đổi tay sẽ bị ghi đè khi clean/rebuild và không tái tạo được trên CI.

## 14. Kiểm tra và gỡ lỗi khi không sinh mã

Khi một generated class không xuất hiện, hãy kiểm tra từ đầu vào đến output:

### Bước 1 — Annotation có trên source element không?

Kiểm tra import đúng annotation, target hợp lệ và annotation có được đặt trên element mà processor tìm kiếm hay không. Nếu processor chỉ hỗ trợ `ElementKind.CLASS` nhưng annotation đặt trên interface, processor có thể bỏ qua hoặc phát lỗi.

### Bước 2 — Processor có nằm trên processor path không?

Với Gradle, kiểm tra dependency `annotationProcessor`/`testAnnotationProcessor`. Với Maven, kiểm tra `annotationProcessorPaths` và Maven Compiler Plugin version. Với `javac`, kiểm tra `-processorpath` hoặc `--processor-path`.

### Bước 3 — Processor có được phát hiện/kích hoạt không?

Kiểm tra tên processor, service registration `META-INF/services/javax.annotation.processing.Processor`, module descriptor nếu có và compiler options. Nếu build tool cấu hình processor tường minh, kiểm tra tên class có đúng package hay không.

### Bước 4 — Processor có phát diagnostic không?

Dùng `Messager` để phát thông báo `NOTE`, `WARNING` hoặc `ERROR`. `ERROR` có thể làm compile thất bại; xem log compiler để tìm thông báo đầu tiên thay vì chỉ nhìn lỗi cuối cùng.

### Bước 5 — Generated source có được ghi vào đúng thư mục không?

Kiểm tra `-s` của javac, `target/generated-sources/annotations` của Maven hoặc `build/generated/sources/annotationProcessor/...` của Gradle. Nếu file nằm ở một thư mục không được compile task quản lý, compiler có thể không biên dịch nó.

### Bước 6 — Có xung đột hoặc tạo file trùng không?

Nếu nhiều processor sinh cùng qualified name, hoặc processor chạy nhiều round mà tạo lại file, có thể gặp `FilerException`. Kiểm tra tên output, originating element và logic tránh tạo trùng.

### Bước 7 — Phiên bản JDK và processor có tương thích không?

Một processor có thể phụ thuộc API compiler nội bộ hoặc giả định về cấu trúc compiler. Sau khi nâng JDK, hãy kiểm tra phiên bản processor và build plugin. Dùng API chuẩn `javax.lang.model`/`javax.annotation.processing` thường bền vững hơn truy cập compiler internals.

## 15. Các lệnh và vị trí hữu ích khi điều tra

### Maven

```bash
# Chạy lại compile sạch và hiển thị log chi tiết
./mvnw -X clean compile

# Xem dependency graph của project
./mvnw dependency:tree

# Liệt kê output generated source sau compile
```

Kiểm tra thủ công:

```text
target/generated-sources/annotations/
target/classes/
```

`target/generated-sources/annotations` cho biết processor có tạo source hay không; `target/classes` cho biết generated source đã được compile thành class hay chưa.

### Gradle

```bash
# Compile source chính với log chi tiết
./gradlew clean compileJava --info

# Xem processor dependency được resolve
./gradlew dependencies --configuration annotationProcessor

# Xem processor dành cho test
./gradlew dependencies --configuration testAnnotationProcessor
```

Kiểm tra:

```text
build/generated/sources/annotationProcessor/java/main/
build/classes/java/main/
```

Nếu processor chỉ được khai báo cho main nhưng annotation xuất hiện trong `src/test/java`, cần khai báo `testAnnotationProcessor` tương ứng.

### `javac`

Có thể bật thông tin xử lý annotation bằng các tùy chọn compiler phù hợp, ví dụ `-XprintRounds` và `-XprintProcessorInfo` trong các JDK hỗ trợ. Chúng giúp quan sát processor nào được gọi và các round nào diễn ra.

Ví dụ:

```bash
javac \
  -XprintRounds \
  -XprintProcessorInfo \
  -processorpath processor.jar \
  -processor com.example.codegen.GreetingProcessor \
  -s build/generated-sources \
  -d build/classes \
  src/main/java/com/example/app/Customer.java
```

## 16. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `cannot find symbol` với class được kỳ vọng sinh ra | Processor không chạy hoặc source output không được compile | Kiểm tra processor path, annotation, generated source directory |
| `package ... does not exist` cho annotation | Annotation API thiếu trên compile classpath | Khai báo annotation artifact ở compile/compileOnly scope phù hợp |
| Không tìm thấy processor | Thiếu processor path, sai tên class hoặc thiếu service registration | Kiểm tra `annotationProcessorPaths`, Gradle `annotationProcessor`, service file/module descriptor |
| Generated source không xuất hiện trên JDK mới | Processor discovery/activation thay đổi hoặc compiler options chưa rõ | Cấu hình processor tường minh và cập nhật build plugin/processor |
| `FilerException: Attempt to recreate a file` | Nhiều lần tạo cùng output trong một compilation | Tránh tạo trùng, chọn tên duy nhất, kiểm soát rounds |
| `NoClassDefFoundError` khi processor chạy | Thiếu dependency của chính processor trên processor path | Khai báo dependency bắc cầu/processor path đầy đủ |
| `UnsupportedClassVersionError` khi tải processor | Processor được build bằng JDK mới hơn JDK chạy compiler | Dùng processor tương thích với JDK của build |
| IDE báo lỗi nhưng CLI build thành công | IDE chưa đồng bộ annotation processor configuration | Reload Gradle/Maven project, bật annotation processing nếu IDE yêu cầu |
| CLI build thành công nhưng CI không sinh mã | CI dùng JDK, wrapper hoặc settings khác; processor dependency không resolve | So sánh JDK, wrapper, repository và processor path |
| Generated file có nhưng ứng dụng runtime thiếu class | Source chưa được compile/package hoặc file nằm ngoài output | Kiểm tra `target/classes`, `build/classes` và artifact cuối |
| Generated resource thiếu trong JAR | Processor ghi resource vào sai output location hoặc packaging bỏ qua | Dùng `Filer` và kiểm tra resource output/package task |

## 17. Tác động của IDE và CI

IDE có thể tích hợp annotation processing riêng để hiển thị generated code trong editor. Một số IDE tự đồng bộ processor path từ Maven/Gradle; một số cần bật annotation processing hoặc refresh project.

Nếu IDE báo đỏ nhưng `./mvnw compile` hoặc `./gradlew compileJava` thành công, hãy kiểm tra IDE đã import đúng build model chưa. Ngược lại, nếu IDE chạy được nhưng CI thất bại, không nên dựa vào processor đã cài thủ công trong IDE; hãy bảo đảm build file khai báo đầy đủ annotation API, processor dependency và JDK phù hợp.

CI nên build từ trạng thái sạch hoặc workspace được kiểm soát để xác nhận generated source thực sự được tạo từ đầu vào. Nếu build chỉ thành công khi còn file generated cũ trong workspace, có thể quy trình đang phụ thuộc vào output không được khai báo hoặc generated source bị commit ngoài dự kiến.

## 18. Bảo mật và độ tin cậy của annotation processor

Annotation processor là code chạy trên máy build. Processor có thể đọc source/model, tạo file và thực thi logic trong tiến trình build. Vì vậy, processor dependency cần được xem xét như một build-time dependency có ảnh hưởng đến supply chain.

Thực hành phù hợp:

- Chỉ dùng processor từ nguồn tin cậy và version được kiểm soát.
- Khai báo processor path riêng, tránh đưa mọi thư viện runtime lên processor path.
- Pin version processor và build plugin theo chính sách dự án.
- Kiểm tra thay đổi dependency khi nâng processor.
- Không để processor ghi file tùy ý ngoài build output nếu không có lý do rõ ràng.
- Không đưa secret vào source hoặc annotation parameter để processor in ra log.
- Bảo đảm generated source có thể tái tạo từ commit và dependency đã khóa/kiểm soát.

Vì processor chạy trong CI, một processor độc hại hoặc bị xâm phạm có thể ảnh hưởng đến môi trường build và artifact. Quy trình review dependency, repository policy và kiểm soát phiên bản áp dụng cho processor cũng quan trọng như dependency ứng dụng.

## 19. Quy trình tổng quát từ annotation đến artifact

Một build sử dụng annotation processing có thể được hình dung như sau:

```text
Source code + Annotation API
             |
             v
Build tool resolve processor dependency
             |
             v
Compiler khởi chạy annotation processor
             |
             v
Processor đọc element/model và annotation
             |
             v
Filer sinh source/resource vào build output
             |
             v
Compiler compile source ban đầu + source được sinh
             |
             v
Class files + resources
             |
             v
Packaging task tạo JAR/WAR
```

Processor là thành phần build-time; generated source và class là đầu ra build; runtime chỉ cần các class/resource được đóng gói hoặc phân phối theo đúng cách. Nếu runtime cần processor để sinh code khi ứng dụng khởi chạy, đó là một kiến trúc khác và không còn là annotation processing JSR 269 thông thường trong compile.

## 20. Những điều cần ghi nhớ

- Annotation processing là cơ chế compile-time theo JSR 269, không phải reflection xử lý annotation lúc runtime.
- Processor đọc annotation/model và có thể sinh Java source, resource hoặc metadata.
- Compiler xử lý generated source trong các round tiếp theo và biên dịch thành class.
- Annotation API cần trên compile classpath; processor và dependency của processor cần trên processor path; runtime chỉ cần các output mà ứng dụng thực sự sử dụng.
- Maven cấu hình processor bằng Maven Compiler Plugin, thường qua `annotationProcessorPaths`; Gradle dùng `annotationProcessor` và `testAnnotationProcessor`.
- Generated source thường nằm trong `target/generated-sources/annotations` hoặc `build/generated/sources/annotationProcessor/...`.
- Không sửa tay generated source và thường không commit thư mục build output.
- Processor cần tránh tạo file trùng và nên khai báo incremental behavior chính xác nếu muốn Gradle tối ưu build.
- Khi nâng JDK, hãy kiểm tra processor discovery/activation, processor compatibility và build plugin version.
- Luôn kiểm tra generated source, compiled class và artifact cuối để biết lỗi nằm ở processing, compile hay packaging.

Khi một class được kỳ vọng sinh ra nhưng không xuất hiện, hãy lần theo từng bước: annotation có trong source không, processor có được resolve và kích hoạt không, processor có tạo file vào đúng thư mục không, compiler có biên dịch file đó không và packaging có đưa class vào artifact không. Cách truy vết này giúp phân biệt lỗi cấu hình processor với lỗi compile hoặc đóng gói, đồng thời giữ cho build có thể tái tạo trên máy developer và CI.
