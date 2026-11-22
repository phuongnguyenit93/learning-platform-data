# Compiler plugin, annotation processor và thư viện instrumentation trong Java

Bài này thuộc chủ đề **Tương thích và build**. Mục tiêu là phân biệt ba điểm can thiệp vào chương trình Java: khi công cụ build gọi trình biên dịch, khi `javac` phân tích mã nguồn và khi JVM nạp/chạy bytecode. Các cơ chế dưới đây vẫn được sử dụng trên các JDK hiện đại; ví dụ độc lập dùng Java 17 trở lên để dễ chạy và bảo trì. Với hệ thống cần duy trì đích tương thích Java 15, xem phần `--release` và kiểm thử runtime ở cuối bài.

## 1. Chọn đúng cơ chế theo thời điểm can thiệp

| Thành phần | Chạy ở đâu/khi nào? | API/cấu hình chính | Kết quả điển hình |
| --- | --- | --- | --- |
| **Build/compiler plugin** (Maven Compiler Plugin, Gradle Java plugin) | Trong tiến trình build; cấu hình và gọi `javac` | `pom.xml`, `build.gradle`, toolchain, compiler arguments | Chọn JDK, `--release`, classpath, processor path, thư mục output |
| **`javac` plugin** | Bên trong một lần biên dịch | `com.sun.source.util.Plugin`, `JavacTask`, `TaskListener`, `-Xplugin` | Theo dõi/kiểm tra AST, phát chẩn đoán, tích hợp phân tích tĩnh |
| **Annotation processor (JSR 269)** | Trong các vòng xử lý annotation lúc biên dịch | `javax.annotation.processing`, `javax.lang.model`, `Filer` | Kiểm tra khai báo, tạo file `.java`/resource/metadata |
| **Bytecode instrumentation** | Khi class được nạp, hoặc khi biến đổi class đã nạp theo khả năng JVM | `java.lang.instrument`, `ClassFileTransformer`, `-javaagent` | Quan sát hoặc biến đổi bytecode, phục vụ tracing/profiling/coverage |

Luồng cần nhớ:

~~~text
Mã nguồn .java
   │
   ├─ Maven/Gradle chọn JDK, dependencies, --release và gọi javac
   │
   ├─ javac plugin quan sát các giai đoạn parse/analyze/generate
   │
   ├─ annotation processor đọc mô hình khai báo, có thể sinh thêm .java
   │       └─ mã sinh ra được javac xử lý ở vòng sau và biên dịch
   ▼
Bytecode .class / JAR
   │
   └─ JVM + Java agent (nếu được cấu hình) có thể quan sát/biến đổi class
           └─ chương trình bắt đầu chạy
~~~

**Điểm phân biệt quan trọng:** Annotation processor không phải Java agent. Processor chủ yếu thao tác trên mô hình phần tử của mã nguồn trong build; agent thao tác trên bytecode ở runtime. Build plugin cấu hình lệnh biên dịch, còn `javac` plugin thực sự chạy bên trong trình biên dịch.

## 2. Compiler plugin và cấu hình build tương thích

### 2.1. Build plugin khác với `javac` plugin

- **Maven Compiler Plugin** thực hiện goal `compile`/`testCompile`, truyền `--release`, processor path, processor names và các tùy chọn tới trình biên dịch. Maven plugin không đồng nghĩa với interface `com.sun.source.util.Plugin`.
- **Gradle Java plugin** tạo các task `compileJava`, `compileTestJava` và các cấu hình `implementation`, `compileOnly`, `annotationProcessor`, `testAnnotationProcessor`. Gradle Java Toolchains giúp chọn đúng JDK cho task.
- **`javac` plugin** implement interface `com.sun.source.util.Plugin` của module `jdk.compiler`; được tìm qua Java `ServiceLoader` và kích hoạt bằng `-Xplugin:TenPlugin`. Nó thích hợp cho quan sát các `TaskEvent` và phân tích cú pháp/ngữ nghĩa trong một lần compile.

Không nên phụ thuộc vào các package nội bộ `com.sun.tools.javac.*` để sửa AST nếu không thực sự sở hữu và kiểm thử kỹ toàn bộ ma trận JDK: chúng có thể bị đóng gói bởi module system hoặc thay đổi giữa các bản JDK. Ưu tiên API `com.sun.source.*` được công bố; nếu mục tiêu là tạo kiểu mới, annotation processor thường đơn giản hơn.

### 2.2. Toolchain khác với `--release`

- **Toolchain** xác định **JDK chạy compiler** (ví dụ JDK 21).
- **`--release 17`** yêu cầu `javac` kiểm tra cú pháp, class-file target và API Java SE tương ứng với Java 17. Như vậy có thể build bằng JDK 21 để chạy trên Java 17.
- **`-source` và `-target` riêng lẻ** không kiểm tra đầy đủ API thư viện chuẩn theo bản Java đích; ưu tiên `--release`.
- `--release` **không tự kiểm tra toàn bộ thư viện bên thứ ba**: dependency có bytecode mới hơn hoặc yêu cầu API runtime mới vẫn có thể làm ứng dụng lỗi. Phải kiểm tra dependencies và chạy test trên JRE/JDK tối thiểu mà hệ thống hỗ trợ.

Ví dụ Gradle Groovy DSL (`build.gradle`) dùng JDK 21 để tạo bytecode tương thích Java 17:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Ở Maven, một cấu hình tương đương là đặt `maven.compiler.release` bằng `17` và chạy Maven bằng JDK/toolchain đã chọn. Khi duy trì ứng dụng yêu cầu Java 15, có thể dùng `--release 15` **chỉ nếu JDK biên dịch còn hỗ trợ đích đó**, kết hợp kiểm thử bằng runtime Java 15 thực tế. Java 15 không phải lựa chọn runtime nên dùng cho dự án mới.

### 2.3. Ví dụ `javac` plugin hoạt động được

Tạo file `plugin-src/demo/TracePlugin.java`:

~~~java
package demo;

import com.sun.source.util.JavacTask;
import com.sun.source.util.Plugin;
import com.sun.source.util.TaskEvent;
import com.sun.source.util.TaskListener;

public final class TracePlugin implements Plugin {
    @Override
    public String getName() {
        return "TraceCompile";
    }

    @Override
    public void init(JavacTask task, String... args) {
        task.addTaskListener(new TaskListener() {
            @Override
            public void started(TaskEvent event) {}

            @Override
            public void finished(TaskEvent event) {
                if (event.getKind() == TaskEvent.Kind.GENERATE) {
                    System.out.println("[javac] generated: "
                            + event.getTypeElement().getQualifiedName());
                }
            }
        });
    }
}
~~~

Tạo service descriptor `plugin-classes/META-INF/services/com.sun.source.util.Plugin` với **đúng một dòng**:

~~~text
demo.TracePlugin
~~~

Tạo file `app/demo/Example.java`:

~~~java
package demo;

public class Example {
    public static void main(String[] args) {
        System.out.println("ok");
    }
}
~~~

Sau khi tạo các thư mục `plugin-classes/META-INF/services` và `out`, chạy ở thư mục gốc ví dụ:

~~~bash
javac --release 17 -d plugin-classes plugin-src/demo/TracePlugin.java
jar --create --file trace-plugin.jar -C plugin-classes .
javac --release 17 -processorpath trace-plugin.jar -Xplugin:TraceCompile -d out app/demo/Example.java
java -cp out demo.Example
~~~

Kết quả chuẩn:

~~~text
[javac] generated: demo.Example
ok
~~~

`javac` tìm plugin từ service descriptor trên processor path (nếu không cấu hình processor path thì cơ chế tìm kiếm có thể dùng classpath). `TaskListener` cho phép quan sát các sự kiện; ví dụ chỉ in thông báo khi compiler hoàn thành tạo class. Không nên nhầm thông báo này với việc plugin đã sửa bytecode. Với dự án nhiều module, cần đặt plugin đúng vào compiler invocation của module được phân tích.

## 3. Annotation processor: cơ chế, vòng xử lý và cấu hình

### 3.1. API vẫn dùng namespace `javax`

Annotation processing chuẩn của JDK sử dụng các package **`javax.annotation.processing`**, **`javax.lang.model`** và `javax.tools`. Đây là API của Java compiler, không phải API Jakarta EE, nên không đổi nhầm thành `jakarta.annotation.processing`.

Một processor thường:

1. Kế thừa `AbstractProcessor` hoặc implement `Processor`, khai báo annotation có thể xử lý qua `@SupportedAnnotationTypes` và phiên bản source được hỗ trợ.
2. Nhận các `Element`/`TypeElement` và `RoundEnvironment`; đọc cấu trúc khai báo bằng `Elements`, `Types` thay vì tự tách chuỗi nguồn.
3. Báo lỗi/cảnh báo bằng `Messager` và `Diagnostic.Kind`, hoặc sinh nguồn/resource bằng `Filer`.
4. Mã `.java` mới sinh ra được đưa vào các **round tiếp theo**; sau vòng cuối (`processingOver()`), không tạo thêm nguồn. Tránh tạo cùng một tên file nhiều lần vì `FilerException`.
5. Đóng `Writer`/`OutputStream` để compiler nhìn thấy kết quả; truyền **originating element** cho `Filer` để công cụ build theo dõi phụ thuộc.

Các annotation có `RetentionPolicy.SOURCE` vẫn có thể được processor đọc lúc compile. Ngược lại, reflection ở runtime không thấy annotation SOURCE. Các processor dùng để tạo DTO mapper (MapStruct), dependency injection metadata, JPA metamodel, code kiểm tra tính hợp lệ... không cần Java agent.

### 3.2. Điểm thay đổi quan trọng ở JDK 23 trở lên

Từ **JDK 23**, `javac` không tự chạy processor chỉ vì tìm thấy JAR trên classpath thông thường. Build phải **cấu hình annotation processing rõ ràng**, ví dụ `-processor`, `-processorpath`, `--processor-module-path` hoặc lựa chọn `-proc:full`/`-proc:only` thích hợp.

- `-processor demo.GreetingProcessor`: chỉ định processor theo tên, dễ kiểm soát những đoạn mã được phép chạy trong build.
- `-processorpath processor.jar`: cách ly các JAR chạy như processor khỏi dependency runtime/application.
- `-proc:only`: xử lý annotation nhưng không tạo class ứng dụng.
- `-proc:none`: tắt annotation processing.
- `-proc:full`: chạy processing và compile, nhưng **chỉ bật tùy chọn này mà không giới hạn processors** có thể cho phép chạy processor không chủ định trên classpath; nên cấu hình tên/path processor cụ thể.

Các JDK trước 23 từng tự khám phá processor từ classpath theo mặc định; không dựa vào hành vi đó khi xây dựng pipeline ngày nay. Processor là **mã Java được thực thi lúc build**, do đó phải kiểm soát nguồn, phiên bản và phạm vi dependency.

### 3.3. Ví dụ đầy đủ: sinh class ở compile time

Ví dụ sau gồm ba file nguồn, build được bằng **JDK 17+**. Đầu vào là `@GreetMe` trên `Hello`, đầu ra là class `HelloGreeting` sinh tự động.

Cấu trúc file trước khi biên dịch:

~~~text
processor-src/
  demo/GreetMe.java
  demo/GreetingProcessor.java
app-src/
  demo/Hello.java
~~~

`processor-src/demo/GreetMe.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GreetMe {}
~~~

`processor-src/demo/GreetingProcessor.java`:

~~~java
package demo;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.GreetMe")
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations, RoundEnvironment round) {
        for (Element element : round.getElementsAnnotatedWith(GreetMe.class)) {
            if (!(element instanceof TypeElement type)) continue;

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();
            String name = type.getSimpleName() + "Greeting";
            String fqn = pkg.isEmpty() ? name : pkg + "." + name;

            try (Writer w = processingEnv.getFiler()
                    .createSourceFile(fqn, type).openWriter()) {
                if (!pkg.isEmpty()) w.write("package " + pkg + ";\n");
                w.write("public final class " + name + " {\n");
                w.write("    private " + name + "() {}\n");
                w.write("    public static String message() { return \"Xin chao tu processor\"; }\n");
                w.write("}\n");
            } catch (IOException ex) {
                processingEnv.getMessager()
                        .printMessage(Diagnostic.Kind.ERROR, ex.toString(), element);
            }
        }
        return true;
    }
}
~~~

`app-src/demo/Hello.java`:

~~~java
package demo;

@GreetMe
public class Hello {
    public static void main(String[] args) {
        System.out.println(HelloGreeting.message());
    }
}
~~~

Tạo hai thư mục output `processor-classes` và `out` rồi chạy ở thư mục gốc ví dụ (các lệnh dưới đây dùng Bash; trên PowerShell có thể tạo thư mục trước bằng `New-Item -ItemType Directory -Force processor-classes,out`):

~~~bash
mkdir -p processor-classes out
javac --release 17 -d processor-classes processor-src/demo/GreetMe.java processor-src/demo/GreetingProcessor.java
jar --create --file greeting-processor.jar -C processor-classes .
javac --release 17 -cp greeting-processor.jar -processorpath greeting-processor.jar -processor demo.GreetingProcessor -d out app-src/demo/Hello.java
java -cp out demo.Hello
~~~

Stdout:

~~~text
Xin chao tu processor
~~~

Giải thích: bước đầu **biên dịch riêng chính processor** và annotation definition. Bước sau dùng `-cp` để nguồn ứng dụng nhìn thấy `@GreetMe`, `-processorpath` để compiler nạp processor và `-processor` để chọn tên cụ thể. Trong round đầu, `Filer#createSourceFile` sinh `demo.HelloGreeting`; compiler biên dịch class đó và `Hello` trong cùng một lần gọi `javac`. Không cần lưu class được sinh vào source do con người sở hữu.

**Tự đăng ký thay vì chỉ định `-processor`:** khi đóng gói processor thành thư viện tái sử dụng, đặt file `META-INF/services/javax.annotation.processing.Processor` bên trong JAR với một dòng `demo.GreetingProcessor`. Sau đó công cụ có thể khám phá processor bằng `ServiceLoader` trên processor path; trong build quan trọng vẫn nên giới hạn processor nào được phép chạy.

**Lưu ý incremental:** ví dụ dùng annotation `SOURCE` để thể hiện vòng compile và chưa khai báo khả năng incremental riêng cho Gradle. Processor muốn tận dụng incremental annotation processing cần tuân thủ hợp đồng của Gradle (chẳng hạn loại `isolating`/`aggregating`, theo dõi input và originating elements, không ghi file tùy tiện ngoài `Filer`); không tự gắn nhãn incremental nếu chưa đáp ứng điều kiện.

### 3.4. Cấu hình processor trong Gradle

Ví dụ thực tế với MapStruct và Groovy DSL:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

dependencies {
    implementation 'org.mapstruct:mapstruct:1.6.3'
    annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'
}
~~~

`implementation` cho mã ứng dụng dùng các annotation/interface MapStruct; `annotationProcessor` cho mã compiler thực thi processor. Với processor dùng trong **nguồn test**, cấu hình riêng `testAnnotationProcessor` khi cần. Gradle cố ý **không chạy processor chỉ vì nó nằm trên compile classpath**. Xem `./gradlew compileJava --info` và thư mục generated sources nếu kết quả chưa xuất hiện. Khả năng compile incremental còn phụ thuộc processor và các input được khai báo.

### 3.5. Cấu hình processor trong Maven

Với Maven 3 và Maven Compiler Plugin 3.x, một đoạn `pom.xml` tương ứng (đặt phần dependency vào `dependencies` và plugin vào `build/plugins` của POM hiện có):

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
      <version>3.16.0</version>
      <configuration>
        <release>17</release>
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

`annotationProcessorPaths` chỉ rõ bộ thư viện chạy trong processor environment; `annotationProcessors` giới hạn tên processor. Với Maven 4/Compiler Plugin 4.x, dependency type `processor` hoặc `classpath-processor`/`modular-processor` là cơ chế mới; chọn cách phù hợp phiên bản Maven đang sử dụng, không sao chép cấu hình Maven 4 vào dự án Maven 3.

## 4. Thư viện instrumentation và Java agent

### 4.1. Instrumentation hoạt động như thế nào?

API chuẩn `java.lang.instrument` cung cấp `Instrumentation` và `ClassFileTransformer`. Một agent JAR có thể khởi động cùng JVM bằng `-javaagent:agent.jar`; manifest phải chứa `Premain-Class`. JVM gọi `public static void premain(String, Instrumentation)` **trước** `main` của ứng dụng. Agent có thể đăng ký transformer:

- **Class load:** transformer nhận bytecode trước khi JVM định nghĩa class; trả `null` nếu giữ nguyên, hoặc trả byte array hợp lệ nếu thực hiện biến đổi.
- **Class đã nạp:** `retransformClasses`/`redefineClasses` chỉ hoạt động khi JVM hỗ trợ, agent xin đúng capability và class có thể sửa. Có giới hạn về thay đổi cấu trúc class, chữ ký và hierarchy; không phải cơ chế hot-swap tùy ý.
- **Module/class loader:** class có thể thuộc module/loader khác; một số instrumentations cần quyền truy cập module cụ thể. Không mở toàn bộ module bằng hàng loạt `--add-opens` thiếu mục đích.

### 4.2. Ví dụ Java agent quan sát class load

Đây là agent **quan sát** để học luồng, chưa sửa bytecode. Hai file Java sau chạy được bằng JDK 17+.

`agent-src/demo/LogAgent.java`:

~~~java
package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class LogAgent {
    public static void premain(String options, Instrumentation instrumentation) {
        System.out.println("[agent] started");

        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader, String name,
                                    Class<?> type, ProtectionDomain domain, byte[] bytes) {
                if ("demo/Runner".equals(name)) {
                    System.out.println("[agent] loading demo.Runner");
                }
                return null; // Không sửa bytecode
            }
        });
    }
}
~~~

`app/demo/Runner.java`:

~~~java
package demo;

public final class Runner {
    public static void main(String[] args) {
        System.out.println("[app] running");
    }
}
~~~

Tạo file `MANIFEST.MF` (có ký tự xuống dòng ở cuối):

~~~text
Manifest-Version: 1.0
Premain-Class: demo.LogAgent

~~~

Tạo thư mục `agent-classes` và `app-classes`, sau đó:

~~~bash
mkdir -p agent-classes app-classes
javac --release 17 -d agent-classes agent-src/demo/LogAgent.java
jar --create --file log-agent.jar --manifest MANIFEST.MF -C agent-classes .
javac --release 17 -d app-classes app/demo/Runner.java
java -javaagent:log-agent.jar -cp app-classes demo.Runner
~~~

Stdout:

~~~text
[agent] started
[agent] loading demo.Runner
[app] running
~~~

Điểm cần quan sát: `premain` được gọi trước khi nạp `demo.Runner`; callback nhận tên class theo dạng có dấu gạch chéo (`demo/Runner`); `return null` nghĩa là **không biến đổi** bytecode. Khi muốn đo thời gian từng phương thức hoặc cấy advice, cần biến đổi bytecode đúng quy tắc JVM, kiểm tra stack frames, class-loader boundaries và chi phí runtime. Không cố sửa mảng byte gốc bằng cách thay chuỗi ký tự.

### 4.3. Thư viện nào phù hợp?

| Lựa chọn | Khi thích hợp | Đánh đổi cần lưu ý |
| --- | --- | --- |
| **Byte Buddy** | Tạo class, method interception, agent/instrumentation ở mức API thuận tiện | Cần phiên bản hỗ trợ bytecode/JDK đang chạy; chú ý quyền attach và giới hạn runtime |
| **ASM** | Phân tích hoặc biến đổi trực tiếp bytecode với quyền kiểm soát chi tiết | Thấp mức hơn; phải nắm instruction, constant pool, stack map frames |
| **`java.lang.classfile` (JDK 24+)** | Phân tích, tạo và biến đổi class file bằng API chuẩn của JDK mới | Chỉ có từ JDK 24; không dùng được khi chính ứng dụng/tool phải chạy trên JDK 17 hoặc 21 |

Nếu chỉ cần sinh Java source từ annotation, chọn `Filer`/processor trước. Nếu cần quan sát event compile, chọn `javac` plugin. Nếu chỉ cần log nghiệp vụ hoặc tracing qua framework, cân nhắc interceptor/filter và OpenTelemetry trước khi triển khai một Java agent tùy chỉnh. Agent phù hợp với yêu cầu can thiệp bytecode xuyên thư viện hoặc nhiều ứng dụng.

### 4.4. Agent tải động và tính toàn vẹn JVM

Khởi động **`-javaagent` ngay lúc JVM start** là cách cấu hình rõ ràng và có thể dự đoán được. Cơ chế attach agent vào JVM đang chạy dùng entry point `agentmain`, manifest `Agent-Class` và quyền/capability phụ thuộc JVM.

Từ JDK 21, việc tải agent động có thể sinh **cảnh báo** theo JEP 451; chính sách cho phép tải động có thể bị siết ở các JDK sau. Với HotSpot, `-XX:+EnableDynamicAgentLoading` thể hiện sự cho phép tải động và có thể tắt cảnh báo tương ứng; không coi đây là lý do để tự động bật cho mọi ứng dụng. Agent startup qua `-javaagent` không chịu cảnh báo do dynamic attach. Khi thư viện mock/test cần instrumentation, cấu hình agent trong JVM test một cách tường minh và kiểm thử với JDK mục tiêu.

Agent có quyền can thiệp lớn vào quá trình chạy. Chỉ dùng thư viện/JAR tin cậy, chốt phiên bản, ghi rõ mục đích can thiệp, theo dõi overhead và đảm bảo lỗi transformer không làm ứng dụng mất khả năng khởi động.

## 5. Checklist cho build và nâng cấp JDK

1. **Phân biệt build JDK, target Java và runtime Java.** Ghi lại kết quả `java -version`, `javac -version`, `mvn -v` hoặc `./gradlew -version`. Dùng toolchain và `--release` nhất quán; chạy CI với runtime thấp nhất đã cam kết hỗ trợ.
2. **Khai báo processor tường minh.** Tách processor dependencies khỏi classpath ứng dụng, chọn tên processor khi có thể; dự án dùng JDK 23+ không trông đợi auto-discovery từ compile classpath.
3. **Giữ generated source do build quản lý.** Không chỉnh sửa hoặc commit file sinh tự động khi project đã có cách tái sinh; để `Filer` tạo file một lần, truyền originating elements và khai báo input phục vụ incremental build.
4. **Chọn thư viện phù hợp bytecode/JDK.** Kiểm tra bảng hỗ trợ của Byte Buddy/ASM và version transitive đi kèm; công cụ đọc bytecode phải hiểu class-file version do compiler tạo.
5. **Đặt agent tại đúng giai đoạn.** Với tracing/test nên chuẩn bị `-javaagent` tại startup; xác nhận manifest, entry point, permission và capability nếu muốn retransform.
6. **Đo lường và kiểm thử.** Kiểm tra clean build lẫn incremental build, tests, class loading, runtime performance, logs, JAR output và tình huống nâng cấp JDK.

Các lỗi thường gặp:

| Triệu chứng | Nguyên nhân hay gặp | Cách xác minh và xử lý |
| --- | --- | --- |
| `cannot find symbol: HelloGreeting` hoặc không có generated source | Processor không chạy, sai processor path hoặc tên processor; đã bị tắt theo mặc định từ JDK 23 | Kiểm tra `-processor`/`annotationProcessor`/`annotationProcessorPaths`, build log và thư mục generated source |
| `FilerException: Attempt to recreate a file` | Sinh cùng một tên file hơn một lần trong các processing rounds | Kiểm tra tập element và logic `process`; đừng tạo lặp khi round cuối |
| Gradle mất incremental compile | Processor không tuân hợp đồng incremental, đọc tài nguyên không khai báo hoặc ghi file ngoài `Filer` | Xem `--info`, khai báo input và đúng metadata processor |
| `UnsupportedClassVersionError` | Compiler/dependency tạo bytecode mới hơn runtime | Dùng `javap -verbose` xem major version, kiểm tra `--release` và các JAR; Java 15=59, 17=61, 21=65, 25=69 |
| `IllegalAccessError` tại compiler extension | Plugin/thư viện đụng internals của `javac` bị encapsulate | Nâng phiên bản thư viện, chuyển sang API được hỗ trợ; tránh phụ thuộc `--add-exports` như giải pháp lâu dài |
| JVM không khởi động với `-javaagent` | Manifest thiếu/sai `Premain-Class`, class không nằm trong JAR, `premain` lỗi | Xem manifest của JAR và stack trace; xác minh tên fully qualified |
| `UnmodifiableClassException` hoặc transformer lỗi verify | Không hỗ trợ retransform, class không thể sửa, bytecode/frames sai | Kiểm tra `isRetransformClassesSupported()`, `isModifiableClass(...)`, giới hạn schema và bytecode verifier |
| Cảnh báo dynamic agent trên JDK 21+ | Thư viện tự attach agent sau lúc JVM chạy | Xác định bên attach; ưu tiên startup `-javaagent` và cấu hình JVM test rõ ràng |

## 6. Bài tập tự kiểm chứng

- Chạy ví dụ annotation processor rồi xóa `out`, build lại để thấy `HelloGreeting` tự tái tạo; bỏ `-processor` và `-processorpath` trên JDK 23+ để quan sát sự khác biệt khi không cấu hình annotation processing.
- Chạy ví dụ `TraceCompile` và thay `GENERATE` bằng `ANALYZE` để quan sát điểm xảy ra sự kiện trong `javac`. Không sửa file ứng dụng để giả lập kết quả.
- Chạy ví dụ Java agent hai lần, có và không có `-javaagent`; so sánh stdout. Sau đó kiểm tra manifest của `log-agent.jar` để xác nhận `Premain-Class` được đóng gói chính xác.

## 7. Tài liệu chính thức để tra cứu khi phiên bản thay đổi

- [`javac` options và annotation processing (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [`com.sun.source.util.Plugin` và `JavacTask`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.compiler/com/sun/source/util/Plugin.html)
- [`Filer` — tạo nguồn và originating elements](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/annotation/processing/Filer.html)
- [Gradle Java plugin: annotationProcessor, toolchains, incremental processing](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Maven Compiler Plugin: tham số compiler/processor](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [`java.lang.instrument` — agents, premain, agentmain, manifest](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html)
- [`java.lang.classfile` — Class-File API từ JDK 24](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/package-summary.html)
- [JDK 23 release notes: thay đổi mặc định annotation processing](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html)
- [JDK 21 release notes: cảnh báo tải agent động](https://www.oracle.com/java/technologies/javase/21-relnote-issues.html)
