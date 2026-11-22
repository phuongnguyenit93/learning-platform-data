# Annotation processing: Đăng ký processor và bật xử lý tường minh trong build hiện đại

## 1. Vấn đề cần giải quyết

Annotation processing là khả năng của `javac` cho phép **annotation processor** kiểm tra cấu trúc source, báo lỗi/cảnh báo và tạo thêm tệp nguồn, class hoặc resource trong quá trình **biên dịch**. Java cung cấp các API chuẩn đang dùng trong Java 17+ như `javax.annotation.processing.Processor`, `AbstractProcessor`, `RoundEnvironment`, `ProcessingEnvironment`, `javax.lang.model` và `Filer`.

Ví dụ một thư viện có annotation `@GenerateGreeting`, processor tìm class được đánh dấu và tạo một class `GeneratedGreeting`. Tác vụ build sau đó biên dịch cả class do processor tạo ra. Để tính năng hoạt động ổn định trên toolchain hiện đại, cần hiểu hai bước **khác nhau**:

1. **Đăng ký / định vị:** javac hoặc build tool biết processor implementation nào tồn tại, tìm nó ở đâu (processor path, service file, module descriptor hoặc danh sách chỉ định).
2. **Kích hoạt / lựa chọn:** một cấu hình build **yêu cầu rõ ràng** processor chạy trong lần biên dịch và giới hạn những processor được cho phép.

**Thay đổi quan trọng từ JDK 23:** Khi không có tùy chọn liên quan đến annotation processing, `javac` **không còn tự động phát hiện và chạy processor nằm tình cờ trên classpath**. Muốn processor chạy, phải có tùy chọn như `-processor`, `--processor-path`, `--processor-module-path` hoặc `-proc:full` / `-proc:only`. Đây là chính sách hiện hành nhằm tránh kích hoạt code trong dependency một cách vô tình. Không nên thiết kế build mới dựa vào mặc định cũ “có JAR trong classpath là processor tự chạy”.

Một điểm bảo mật: processor là **code thực thi trong quá trình build**, có thể dùng quyền file/network của tiến trình compiler. Vì vậy chỉ tải processor được tin cậy, có phiên bản được kiểm soát, và hạn chế processor path.

## 2. Ba cơ chế đăng ký processor cần phân biệt

### 2.1. Chỉ định trực tiếp bằng `-processor`

~~~bash
javac --release 17 \
  --class-path build/greeting-processor.jar \
  --processor-path build/greeting-processor.jar \
  -processor demo.GreetingProcessor \
  -d build/app-classes \
  app-src/demo/App.java
~~~

Đây là **lệnh mẫu** khi những tệp đã được tạo như ví dụ đầy đủ ở phần 5.

- `-processor demo.GreetingProcessor`: nêu **fully qualified class name** của processor cần chạy; có thể truyền danh sách phân tách bằng dấu phẩy nếu nhiều processor.
- `--processor-path build/greeting-processor.jar`: xác định nơi javac **tải processor implementation** (và dependency cần thiết cho processor).
- `--class-path build/greeting-processor.jar`: xác định nơi source ứng dụng tìm annotation `demo.GenerateGreeting` trong ví dụ. Hai classpath có **vai trò khác nhau**, dù ví dụ đơn giản dùng chung một JAR chứa cả annotation và processor.
- `--release 17` và `-d`: chọn phiên bản Java đích và nơi ghi class output; chúng không phải công tắc bật annotation processing.

Khi có `-processor`, javac chọn **đúng những class được chỉ định** thay vì quét tất cả service descriptor để tìm processor. Đây là cách rõ ràng khi cần kiểm soát danh sách processor.

### 2.2. Đăng ký qua `META-INF/services`

Với processor đóng gói trên **classpath / processor path**, file service provider phải có đường dẫn chính xác trong JAR:

~~~text
META-INF/services/javax.annotation.processing.Processor
~~~

Nội dung file UTF-8, **mỗi dòng một tên class processor có package đầy đủ**; ví dụ:

~~~text
demo.GreetingProcessor
~~~

Javac dùng cơ chế service discovery để tìm processor khi annotation processing được yêu cầu mà build **không** chỉ rõ danh sách qua `-processor`. Tệp này phải nằm trong **JAR processor**, không nằm bất kỳ đâu trong thư mục source ứng dụng rồi trông chờ javac tự đi tìm.

Ví dụ kích hoạt discovery một cách tường minh:

~~~bash
javac --release 17 \
  --class-path build/greeting-processor.jar \
  --processor-path build/greeting-processor.jar \
  -proc:full \
  -d build/app-by-service \
  app-src/demo/App.java
~~~

`--processor-path` vừa giới hạn nơi tìm vừa là một cách cấu hình processing; `-proc:full` ghi rõ ý định **xử lý annotation rồi biên dịch**. Không phải luôn cần cả hai tùy chọn để kích hoạt, nhưng kết hợp giúp cấu hình rõ khi học và kiểm tra. **Chỉ liệt kê đường dẫn chưa tự chọn processor cụ thể:** trong phạm vi processor path đó, mọi processor có descriptor phù hợp có thể được phát hiện. Đường dẫn chỉ nên gồm dependency đã xét duyệt.

**Bẫy tự bootstrap:** Khi đang biên dịch chính source của `GreetingProcessor` lần đầu, đừng đặt service descriptor lên classpath biên dịch processor trước khi class processor tồn tại. Hãy biên dịch processor class **trước**, sau đó thêm descriptor vào thư mục class output và đóng gói JAR. Nếu không có thể gặp lỗi kiểu “Bad service configuration file ... Provider ... not found”.

### 2.3. JPMS: `module-info.java` cho named processor module

Với một **explicit named module** chuyên cung cấp processor, mô tả service bằng `provides ... with ...`:

~~~java
module demo.greeting.processor {
    requires java.compiler;
    provides javax.annotation.processing.Processor
        with demo.GreetingProcessor;
}
~~~

Đây là **đoạn `module-info.java` minh họa**, không phải dự án modular đầy đủ. Module phải chứa implementation `demo.GreetingProcessor` với hợp đồng processor hợp lệ. Nếu annotation API nằm trong cùng module và consumer phải sử dụng, cân nhắc `exports` package annotation hoặc tách API annotation ra module riêng.

Build sử dụng `--processor-module-path` để chọn module path chứa processor. Đây là một phạm vi khác với `--processor-path`; không trộn file service dành cho classpath thành điều kiện bắt buộc của named module. Với module provider, JPMS dùng khai báo `provides`. Không thay `provides javax.annotation.processing.Processor` bằng `uses`: `uses` thuộc module **tiêu thụ service**, còn `provides` thuộc module cung cấp implementation.

## 3. Bật và tắt processing theo chính sách hiện hành của javac

| Tùy chọn | Hành vi cần nhớ |
| --- | --- |
| `-proc:none` | Tắt annotation processing, chỉ biên dịch source thông thường |
| `-proc:only` | Chạy annotation processing, **không** tiến hành bước biên dịch class thông thường sau các processing round |
| `-proc:full` | Chạy annotation processing **và** biên dịch; kích hoạt rõ ngay cả khi không có tùy chọn processor khác |
| `-processor a.b.One,a.b.Two` | Chỉ định processor theo tên; tránh tự discovery danh sách tùy ý |
| `--processor-path PATH` | Chọn đường tìm processor trên classpath riêng; đồng thời là một cấu hình yêu cầu processing |
| `--processor-module-path PATH` | Chọn đường tìm processor trong named modules |
| `-Akey=value` | Gửi option cho processor; processor đọc qua `processingEnv.getOptions()` |
| `--class-path PATH` | Phụ thuộc compile của ứng dụng; **không nên** dùng làm nơi tự discovery processor từ dependency ngẫu nhiên |

**Quy tắc JDK 23+:** Nếu không có bất kỳ tùy chọn kích hoạt phù hợp, mặc định về cơ bản là `-proc:none`. Trước JDK 23, việc tìm processor trên classpath từng có thể xảy ra ngầm; đây không còn là giả định hợp lệ cho build mới. `-proc:full` đã có trong JDK 21 và được backport tới các bản cập nhật được hỗ trợ của JDK 17, nhưng nên sử dụng toolchain được quản lý thay vì dựa trên mọi bản vá JDK 17 cũ.

Không được hiểu `-proc:full` là “chạy tất cả processor nhưng vẫn an toàn”. Nó chỉ yêu cầu processing; nếu không khai báo danh sách/path rõ, javac có thể tìm processor từ classpath rộng ngoài ý muốn. **Lựa chọn an toàn hơn:** khai báo processor cụ thể và processor path riêng, đồng thời dùng build tool phụ trách dependency.

### Khi dùng `JavaCompiler` API thay vì CLI

Ứng dụng gọi Java Compiler API cũng chịu logic processor tương ứng của javac. Một phương án rõ ràng là tạo `CompilationTask` rồi gán chính các object processor được tin cậy **trước** `call()`:

~~~java
JavaCompiler.CompilationTask task = compiler.getTask(
        null, fileManager, diagnostics, options, null, sourceFiles);
task.setProcessors(List.of(new GreetingProcessor()));
Boolean success = task.call();
~~~

Đây là **đoạn đặt trong method đã có các biến và import cần thiết**, không phải file chạy độc lập. `task.setProcessors(...)` cho phép chỉ định các instance processor trong API thay vì discovery service. Processor class và dependency vẫn phải được ứng dụng nạp từ vị trí tin cậy; mỗi `CompilationTask` chỉ chạy **một lần**. Không gọi `setProcessors` sau khi `call` đã bắt đầu. Với build thông thường, thường dễ kiểm soát và tái lập hơn khi để Maven/Gradle thiết lập processor path.

## 4. Hợp đồng của một processor hợp lệ

Với một implementation Java hiện đại, processor thường kế thừa `AbstractProcessor`, khai báo annotation được hỗ trợ, source version và implement `process(...)`.

- `@SupportedAnnotationTypes`: mẫu tên annotation mà processor xử lý, chẳng hạn `"demo.GenerateGreeting"`. Có thể có processor dùng `"*"` để quan sát mọi loại annotation, nhưng chỉ dùng khi thực sự cần.
- `@SupportedSourceVersion(SourceVersion.RELEASE_17)`: processor tuyên bố hỗ trợ cú pháp ở phiên bản source tương ứng. Khi đổi Java source level, cập nhật thông tin này hoặc ghi đè `getSupportedSourceVersion()` phù hợp, tránh cảnh báo không cần thiết.
- `process(Set<? extends TypeElement>, RoundEnvironment)`: được gọi theo **nhiều vòng**. Processor đọc các element đã biết, có thể tạo source/asset mới bằng `Filer`. Các file mới tham gia vòng tiếp theo.
- `RoundEnvironment.processingOver()`: đánh dấu không còn vòng phát hiện bình thường; tránh tạo file không đúng lúc. Không phụ thuộc một processor chỉ được gọi đúng một lần.
- `return true` nghĩa là processor **claim** các annotation đã xử lý; `false` cho phép processor khác tiếp tục xử lý annotation tương ứng. Giá trị đó không đồng nghĩa biên dịch thành công.
- `Filer.createSourceFile(...)` và `JavaFileObject.openWriter()`: cách chuẩn tạo source mới. Tạo cùng tên file nhiều lần trong một compilation thường gây `FilerException`.
- `Messager.printMessage(Diagnostic.Kind.ERROR, ...)`: báo lỗi có cấu trúc thay vì tự in ra console; lỗi có thể làm toàn tác vụ biên dịch thất bại.
- Service provider trên classpath cần implementation có thể được javac khởi tạo qua **public no-arg constructor**. Lớp được sử dụng làm processor thường là `public` và không abstract.

Processor được **thực thi ở build time**; không nên đưa code tùy ý từ bên ngoài vào processor path chỉ vì đó là một dependency của ứng dụng.

## 5. Ví dụ chạy được trên Java 17+: từ processor đến output sinh tự động

Ví dụ có một annotation `@GenerateGreeting`, một processor `GreetingProcessor` và một ứng dụng `App`. Khi processor chạy, nó tạo class `demo.GeneratedGreeting`. `App` gọi phương thức của class mới được sinh trong cùng lượt compile.

Cấu trúc thư mục:

~~~text
greeting-demo/
├── processor-src/
│   └── demo/
│       ├── GenerateGreeting.java
│       └── GreetingProcessor.java
└── app-src/
    └── demo/
        └── App.java
~~~

Các thư mục `build/` và service descriptor sẽ được tạo bằng lệnh bên dưới. Ở dự án thật có thể tách annotation API và processor implementation thành hai artifact, nhưng ví dụ gộp chúng trong một JAR để dễ chạy mà không cần repository bên ngoài.

### 5.1. Annotation `processor-src/demo/GenerateGreeting.java`

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {}
~~~

`RetentionPolicy.SOURCE` có nghĩa annotation chỉ dùng cho source/processor, không cần được giữ trong bytecode runtime.

### 5.2. Processor `processor-src/demo/GreetingProcessor.java`

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
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (!generated && !round.processingOver()
                && !round.getElementsAnnotatedWith(GenerateGreeting.class).isEmpty()) {
            generated = true;
            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile("demo.GeneratedGreeting");
                try (Writer writer = file.openWriter()) {
                    writer.write("package demo; public final class GeneratedGreeting {"
                            + " public static String text() { return \"generated\"; } }");
                }
            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, e.getMessage());
            }
        }
        return true;
    }
}
~~~

Giải thích:

- `@SupportedAnnotationTypes` khớp annotation trong source ứng dụng.
- `round.getElementsAnnotatedWith(GenerateGreeting.class)` cho biết có class được đánh dấu trong vòng đang xét.
- `generated` tránh ghi lặp file `demo.GeneratedGreeting` ở vòng sau. Trong processor thật xử lý **nhiều** class hoặc nhiều generated file, nên quản lý tên file/element nguồn và trạng thái theo đúng phạm vi từng compilation.
- `processingEnv.getFiler().createSourceFile(...)` bàn giao file nguồn mới cho compiler, **không tự ghi file bằng `Files.writeString` vào một đường dẫn ngoài build**.
- `Diagnostic.Kind.ERROR` báo lỗi nếu tạo file thất bại, giúp người dùng biết build bị lỗi.

### 5.3. Ứng dụng `app-src/demo/App.java`

~~~java
package demo;

@GenerateGreeting
public final class App {
    public static void main(String[] args) {
        System.out.println(GeneratedGreeting.text());
    }
}
~~~

`GeneratedGreeting` **không tồn tại trong source ban đầu**. Nó chỉ được tạo khi processor có chạy; vì thế nếu vô tình tắt processing hoặc quên processor path, lệnh biên dịch sẽ thất bại vì thiếu class sinh ra.

### 5.4. Đóng gói processor và đăng ký service descriptor

Chạy các lệnh sau trong thư mục `greeting-demo` với **Bash/POSIX shell** và JDK 17+. Nếu dùng PowerShell/Windows, có thể tạo các thư mục/file tương ứng bằng lệnh PowerShell rồi dùng những lệnh `javac`/`jar` giống nhau; dấu phân cách classpath khi chạy `java` là `;` thay cho `:`.

~~~bash
mkdir -p build/processor-classes
javac --release 17 \
  -d build/processor-classes \
  processor-src/demo/GenerateGreeting.java \
  processor-src/demo/GreetingProcessor.java

mkdir -p build/processor-classes/META-INF/services
printf '%s\n' 'demo.GreetingProcessor' \
  > build/processor-classes/META-INF/services/javax.annotation.processing.Processor

jar --create --file build/greeting-processor.jar \
  -C build/processor-classes .
~~~

**Tại sao theo thứ tự này?** Trước tiên compile chính `GreetingProcessor`; tiếp theo mới đặt service descriptor chứa tên processor vào output; cuối cùng đóng gói JAR. Như vậy tránh javac đi tìm processor mà chưa được tạo khi đang bootstrap.

Sau bước này, JAR chứa `demo/GenerateGreeting.class`, `demo/GreetingProcessor.class` và đúng tệp `META-INF/services/javax.annotation.processing.Processor`.

### 5.5. Cách A — yêu cầu processor cụ thể với `-processor`

~~~bash
mkdir -p build/app-classes

javac --release 17 \
  --class-path build/greeting-processor.jar \
  --processor-path build/greeting-processor.jar \
  -processor demo.GreetingProcessor \
  -d build/app-classes \
  app-src/demo/App.java

java -cp build/app-classes:build/greeting-processor.jar demo.App
~~~

Stdout chính xác:

~~~text
generated
~~~

Trên Windows, lệnh chạy có thể viết `java -cp "build/app-classes;build/greeting-processor.jar" demo.App`. Khi dùng `-processor demo.GreetingProcessor`, javac chọn processor theo tên đã chỉ định; service descriptor có thể tồn tại trong JAR nhưng **không phải lý do processor được chọn** trong cách A.

### 5.6. Cách B — phát hiện qua `META-INF/services`, xử lý rõ ràng

~~~bash
mkdir -p build/app-by-service

javac --release 17 \
  --class-path build/greeting-processor.jar \
  --processor-path build/greeting-processor.jar \
  -proc:full \
  -d build/app-by-service \
  app-src/demo/App.java

java -cp build/app-by-service:build/greeting-processor.jar demo.App
~~~

Stdout cũng là:

~~~text
generated
~~~

Lần này không có `-processor`. Javac duyệt processor path, tìm service descriptor và tạo `GreetingProcessor`. Tùy chọn `-proc:full` ghi rõ yêu cầu chạy annotation processing cùng compilation. Ví dụ đã được kiểm tra trên **OpenJDK 24 với `--release 17`** cho cả hai cách A và B.

**Thí nghiệm nhận diện lỗi cấu hình:** Nếu dùng JDK 23+ và chỉ đặt JAR lên `--class-path`, nhưng không có bất kỳ tùy chọn kích hoạt processing, sau khi xóa output cũ, compiler sẽ không tự sinh `GeneratedGreeting`. Kết quả thường là diagnostic kiểu `cannot find symbol` đối với `GeneratedGreeting`. Không hardcode toàn bộ văn bản lỗi vì nó có thể khác nhau theo phiên bản, locale và compiler.

## 6. Cấu hình Maven đúng với từng thế hệ plugin

Trong build thật, Maven/Gradle thường quản lý artifact và đường dẫn processor. Vẫn phải hiểu **đúng hệ phiên bản của Maven Compiler Plugin**; không lấy một cách cấu hình của Maven 4 áp vào Maven 3.

### 6.1. Maven 3 + Maven Compiler Plugin 3.x

Với Maven 3, dùng cấu hình `annotationProcessorPaths` để tách processor khỏi classpath ứng dụng. Ví dụ đoạn `pom.xml` dưới đây minh họa **artifact nội bộ đã được xuất bản** với tọa độ `demo:greeting-processor:1.0.0`; không phải dependency có sẵn trên Maven Central:

~~~xml
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
        </annotationProcessorPaths>
        <annotationProcessors>
          <annotationProcessor>demo.GreetingProcessor</annotationProcessor>
        </annotationProcessors>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Đây là **đoạn cấu hình**, cần đưa vào POM hoàn chỉnh của dự án, cài/phát hành processor artifact thật và khai báo dependency của **annotation API** cho source ứng dụng khi cần. `annotationProcessorPaths` là cách **vẫn áp dụng với plugin 3.x**, không tự xem nó là lỗi thời chỉ vì Maven 4 cung cấp cách mới. `annotationProcessors` giới hạn class processor cụ thể được gọi, tránh discovery những implementation khác trong dependency graph.

### 6.2. Maven 4 + Maven Compiler Plugin 4.x

Với Maven 4 và plugin 4.x, tài liệu chính thức khuyến nghị dùng dependency có `type` chuyên biệt như `classpath-processor` hoặc `modular-processor`. Ví dụ với processor **không phải named module**:

~~~xml
<dependencies>
  <dependency>
    <groupId>demo</groupId>
    <artifactId>greeting-processor</artifactId>
    <version>1.0.0</version>
    <type>classpath-processor</type>
  </dependency>
</dependencies>
~~~

Tọa độ `demo:greeting-processor:1.0.0` chỉ là **ví dụ của artifact nội bộ**, không ngụ ý đã tồn tại trong repository công khai. Đoạn trên cần nằm trong dự án Maven 4 có plugin compiler 4.x được cấu hình phù hợp. Với named processor module dùng `modular-processor` và `module-info.java` có `provides`.

Không bê nguyên `annotationProcessorPaths` từ plugin 3.x vào plugin 4.x như một mô hình lâu dài: tài liệu plugin 4.x đã **deprecate** cách đó và hướng tới processor dependency types. Cũng không đặt `<proc>full</proc>` đơn độc làm biện pháp duy nhất: như vậy có thể kích hoạt discovery những processor vô tình có mặt trên classpath. Hãy khai báo **processor dependencies** được phép và chọn path rõ ràng.

## 7. Gradle: dùng `annotationProcessor` thay vì trông chờ compile classpath

Với Java plugin của Gradle, `annotationProcessor` là dependency configuration dành riêng cho processor path của source set; dependency trong `implementation`/`compileOnly` đơn thuần **không đồng nghĩa** được chạy như processor. Gradle tách processor path ra khỏi compile classpath để build tái lập và kiểm soát tốt hơn.

Ví dụ trong **`build.gradle.kts`** của ứng dụng Gradle multi-project, khi có project `:processor` đã build thành công JAR tương tự phần 5:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    compileOnly(project(":processor"))
    annotationProcessor(project(":processor"))
}
~~~

`compileOnly` ở đây cho consumer thấy annotation `demo.GenerateGreeting`, còn `annotationProcessor` đưa implementation/descriptor vào processor path. Do demo gộp annotation API và processor vào một JAR, cùng project xuất hiện ở hai scope. Trong kiến trúc production thường tách thành:

- Module **annotation API** chỉ chứa các annotation, được khai báo ở compile classpath (`compileOnly`/`implementation` tùy runtime contract).
- Module **processor** chứa implementation, đăng ký service và được khai báo ở `annotationProcessor`.
- Nếu có test source dùng processor, cấu hình `testAnnotationProcessor` tương ứng; đừng giả định `annotationProcessor` của main tự được áp dụng cho test compile task.

Với processor cung cấp service descriptor chính xác, Gradle sẽ đặt processor dependency trên annotation processor path; có thể dùng cấu hình compiler args `-processor` nếu cần giới hạn cụ thể. Không tự gắn `-proc:full` và quét toàn bộ compile classpath làm giải pháp thay thế.

Nếu processor hỗ trợ Gradle incremental annotation processing, nó phải khai báo và tuân thủ contract incremental của Gradle (isolating/aggregating, originating elements, Filer, v.v.). **Đăng ký processor thành công chưa có nghĩa processor mặc nhiên incremental.**

## 8. Vị trí phát sinh output, kiểm tra build và xử lý lỗi

### Generated source và class output

Processor dùng `Filer` để tạo source; compiler xử lý các file mới theo **annotation processing rounds**. Lệnh `javac -s path` chỉ định nơi lưu **generated source files**, còn `-d path` chỉ định nơi lưu class output. Build tool thường đã có cơ chế quản lý hai vị trí này, nên không nên tự ghi file ngoài output mà build tool theo dõi.

Ví dụ kiểm tra:

~~~bash
mkdir -p build/generated-sources build/classes

javac --release 17 \
  --class-path build/greeting-processor.jar \
  --processor-path build/greeting-processor.jar \
  -processor demo.GreetingProcessor \
  -s build/generated-sources \
  -d build/classes \
  app-src/demo/App.java
~~~

Sau khi compile thành công, kiểm tra generated source `build/generated-sources/demo/GeneratedGreeting.java` và class `build/classes/demo/GeneratedGreeting.class`. Đây là kết quả của ví dụ này, không phải lời hứa rằng mọi processor đều tạo file với đường dẫn/tên như vậy.

### Khi processor không được chạy

Triệu chứng quen thuộc: source dùng type đáng ra được generate nhưng báo không tìm thấy symbol, hoặc file generated source không xuất hiện sau một **clean build**.

Checklist kiểm tra:

1. Compiler JDK và target `--release` đã được xác định chưa? Nếu dùng `@SupportedSourceVersion(RELEASE_17)` thì compile với source level 17 như ví dụ.
2. Bản build có **yêu cầu xử lý** không (`-processor`, `--processor-path`, `--processor-module-path`, `-proc:full` hoặc cấu hình build tool tương ứng)?
3. Processor artifact đã nằm trên **processor path** chưa, hay chỉ nằm ở compile/runtime classpath?
4. Với discovery qua classpath: JAR có `META-INF/services/javax.annotation.processing.Processor` với tên implementation chính xác không?
5. Với named module: có `provides javax.annotation.processing.Processor with ...` và module nằm trên processor module path không?
6. Class processor có `public`, khởi tạo được, annotation type được nhận diện và source version phù hợp không?
7. Processor có bị `-proc:none` vô hiệu hóa, hoặc bị `-processor` giới hạn sang implementation khác không?
8. Có sai package, binary name, file source output, một lần tạo file trùng tên hay lỗi `FilerException` không?
9. Có bị cache build/IDE gây nhầm với generated output từ lần trước không? Hãy kiểm tra bằng clean build và compiler args thật thay vì dựa vào IDE hiển thị.
10. Processor và các transitive dependencies có tin cậy, được pin phiên bản và tương thích với JDK thực tế không?

Có thể dùng tùy chọn chẩn đoán của javac như `-XprintRounds` và `-XprintProcessorInfo` khi điều tra processor selection/rounds; output dạng logging không phải API ổn định để so sánh chuỗi trong unit test xuyên JDK.

### Khi processor báo lỗi

Một processor thường có thể báo `Diagnostic.Kind.ERROR` qua `Messager`. Kết quả `CompilationTask.call()` khi đó thất bại; trong CLI, javac trả exit status khác 0. Phân biệt lỗi source/processor, lỗi đường dẫn processor hoặc lỗi không tải được service provider. Processor được gọi trong quá trình build nên exceptions hoặc file system problems không phải lúc nào cũng xuất hiện như một lỗi cú pháp Java thông thường.

## 9. An toàn và khả năng tái lập

- **Processor là mã build-time có thể thực thi.** Tuyệt đối không tải processor không tin cậy trong JVM chứa credential quan trọng chỉ vì Java source của project “chưa chạy”.
- **Tách processor path khỏi compile/runtime classpath.** Hạn chế implementation được cho phép, pin phiên bản và review transitive dependencies, thay vì discovery tùy ý ở classpath lớn.
- **Không truyền các compiler options từ request bên ngoài một cách trực tiếp.** Các tùy chọn như `-processor`, `--processor-path`, `-Xplugin` có thể làm javac tải code tùy ý.
- **Cấu hình processing có chủ đích.** Không dùng `-proc:full` đơn độc để tái tạo hành vi quét implicit của JDK cũ trong một build mới.
- **Chỉ publish output khi toàn bộ build thành công.** Trong trường hợp lỗi processing, thư mục generated/classes có thể còn output một phần hoặc còn từ build trước; cần clean/isolated output và xử lý artifact thất bại đúng.
- **Giữ processor deterministic khi có thể.** Ghi output qua Filer, tránh phụ thuộc môi trường hoặc thời gian hiện tại và khai báo input nếu build tool cần để cache/incremental compile an toàn.

Annotation processing không phải sandbox: nếu phải build mã không tin cậy hoặc chạy processor bên ngoài, cần worker/process được cách ly bằng quyền OS, resource limits và chính sách truy cập file/network.

## 10. Tự kiểm tra

1. **JDK 23+, source có annotation nhưng không truyền tùy chọn processor, javac có tự chạy processor từ classpath không?** Không theo mặc định; cần bật processing rõ ràng.
2. **Service descriptor đặt ở đâu?** Trong JAR processor tại `META-INF/services/javax.annotation.processing.Processor`, mỗi dòng tên processor đầy đủ.
3. **Khác biệt giữa `-processor` và service discovery?** `-processor` chỉ rõ processor muốn chạy; service discovery tìm các implementation được đăng ký trong processor search path.
4. **`-proc:only` khác `-proc:full` thế nào?** Chỉ processing so với processing cộng compilation.
5. **Tại sao demo đưa cùng JAR vào cả `--class-path` và `--processor-path`?** Nó gộp annotation API và implementation; build production nên tách hai loại artifact nếu cần.
6. **Trong Maven 4 plugin 4.x nên ưu tiên `annotationProcessorPaths` hay processor dependency types?** Ưu tiên `classpath-processor`/`modular-processor` theo tài liệu plugin 4.x; cấu hình 3.x vẫn phù hợp cho Maven 3.
7. **Trong Gradle, chỉ khai báo `implementation(project(":processor"))` có đảm bảo chạy processor không?** Không; cấu hình `annotationProcessor` riêng.
8. **Processor có thể chạy bao nhiêu vòng?** Nhiều round; generated source có thể tạo round tiếp theo. Không giả định process chỉ gọi một lần.
9. **Có nên cho phép processor được tìm trên classpath bất kỳ rồi chỉ thêm `-proc:full`?** Không nên; chỉ dùng dependency/path được phép và processor đã xét duyệt.
10. **Có thể thay service descriptor bằng JPMS `provides` không?** Có đối với explicit named processor module, kèm processor module path và descriptor thích hợp.

## 11. Tài liệu hiện hành

- [OpenJDK — tài liệu javac hiện hành](https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/man/javac.md): annotation processing, `-processor`, `--processor-path`, `--processor-module-path`, `-proc`.
- [Inside Java — JDK 23 thay đổi chính sách mặc định của annotation processing](https://inside.java/2024/06/18/quality-heads-up/): lý do và hướng migration sang opt-in.
- [Java SE 25 — Processor](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/Processor.html), [AbstractProcessor](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html), [Filer](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/Filer.html): hợp đồng implementation, rounds, tạo file.
- [Maven Compiler Plugin 4.x — Annotation processors](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/annotation-processor.html): cấu hình Maven 3 và Maven 4.
- [Maven Compiler Plugin 3.x — compile goal](https://maven.apache.org/plugins/maven-compiler-plugin-3.14.1/compile-mojo.html): `annotationProcessorPaths` và `annotationProcessors` khi dùng plugin 3.x.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `annotationProcessor` dependency configuration và incremental processing.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): tách compile classpath và processor path.

**Ghi nhớ:** “**Đăng ký**” xác định implementation được tìm thấy; “**bật processing**” xác định liệu và bằng cách nào compiler chạy processor; “**giới hạn processor path và danh sách**” quyết định build có kiểm soát hay không. Với JDK 23+, hãy cấu hình tường minh, nhất quán giữa CLI/Maven/Gradle và không dựa vào implicit discovery cũ.