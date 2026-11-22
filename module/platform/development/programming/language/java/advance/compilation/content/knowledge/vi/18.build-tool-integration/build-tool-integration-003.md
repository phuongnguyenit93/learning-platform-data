# Tách biên dịch mã chính, mã kiểm thử và nguồn được sinh

Một dự án Java có thể chứa ba nhóm mã **khác vai trò, khác vòng đời và khác classpath**: mã chính (*main/production sources*), mã kiểm thử (*test sources*) và mã nguồn được công cụ tạo ra (*generated sources*). Nếu đưa tất cả vào cùng một thư mục rồi gọi `javac` một lần không phân biệt, dự án sẽ khó xác định cái gì được đóng gói, thư viện nào chỉ phục vụ test, generated code do tác vụ nào sở hữu, vì sao build incremental không cập nhật, và cách tái tạo artifact trên CI.

Mục tiêu đúng không chỉ là tạo ra các tệp `.class`. Mục tiêu là thiết kế **đồ thị biên dịch có thứ tự, đầu vào/đầu ra tường minh**:

1. Công cụ sinh mã hoặc annotation processor phải được xây dựng/sẵn sàng **trước khi** tác vụ cần chạy nó.
2. Mã chính được biên dịch cùng generated source **thuộc phần main**, dùng đúng dependencies production.
3. Mã kiểm thử được biên dịch **sau khi có main output**, với dependencies test riêng.
4. Chạy test có thể cần cả output của main lẫn test; nhưng artifact production thông thường **không đóng gói test code, framework kiểm thử hay processor build-time**.
5. Các file sinh ra nằm dưới thư mục **build/generated...**, do task sở hữu, có thể xóa và tái tạo, không trộn với mã viết tay ở `src/main/java`.

Bài học áp dụng Java 17+, giải thích `javac` trực tiếp và cách ánh xạ sang source sets/tasks của Gradle, lifecycle Maven, annotation processing, incremental builds, CI và các lỗi classpath thực tế. Phần demo `javac` được **biên dịch/chạy thật bằng JDK 24 với `--release 17`**; phần cấu hình Gradle/Maven là hướng dẫn kiến trúc dựa trên tài liệu công cụ, cần điều chỉnh theo project/plugin thực tế.

## 1. Phân biệt ba loại nguồn bằng hợp đồng

| Loại | Vị trí quy ước | Ai tạo? | Được biên dịch khi nào? | Thường nằm trong JAR production? |
| --- | --- | --- | --- | --- |
| Mã chính (main) | `src/main/java` | Lập trình viên | Giai đoạn compile main | **Có**: class output của main |
| Mã kiểm thử (test) | `src/test/java` | Lập trình viên/tool test | Sau main, ở giai đoạn test-compile | **Không** |
| Generated source cho main | `build/generated/.../main` hoặc `target/generated-sources/...` | Annotation processor/codegen | Trong hoặc trước main compilation | **Class được tạo thường có**, không nhất thiết đóng gói file `.java` |
| Generated source cho test | `build/generated/.../test` hoặc `target/generated-test-sources/...` | Processor/codegen của test | Trong hoặc trước test compilation | **Không** trong JAR production |
| Source của processor | Một module riêng, ví dụ `processor/src/main/java` | Lập trình viên | Trước khi chạy processor | Không đi vào runtime app nếu chỉ phục vụ build |

Câu “generated source có trong JAR” rất dễ gây hiểu lầm. JAR Java thông thường **chứa class files/resources đã build**, không nhất thiết chứa file `.java`. Generated Java đóng vai trò **input cho compiler**; `.class` của nó, nếu thuộc phần main, mới được đưa vào output/packaging production.

### Các classpath là những hợp đồng khác nhau

- **Main compile classpath:** chứa những thư viện mà source main cần để type-check; ví dụ API annotation kiểu `SOURCE` nếu main dùng.
- **Main runtime classpath:** chứa main class files và dependencies ứng dụng thật cần khi chạy.
- **Test compile classpath:** thường chứa main class output/API và dependencies kiểm thử (JUnit, assertion libraries, test fixtures...).
- **Test runtime classpath:** gồm test classes, main classes, test runtime dependencies và runtime dependencies production.
- **Annotation processor path:** chứa *code chạy trong compiler* để phát sinh nguồn hoặc chẩn đoán; **không đồng nhất** với main runtime classpath.

Việc cùng một JAR xuất hiện trên hai classpath là có thể, nhưng **vai trò** của nó vẫn khác nhau. Đặc biệt, processor có thể cần thư viện dùng riêng để sinh code, không nên bị kéo vào runtime chỉ vì compiler từng nạp processor.

## 2. Đồ thị phụ thuộc biên dịch

```text
                 (1) BUILD / LẤY PROCESSOR
                     annotation API
                           |
                           v
                   annotation processor
                           |
                           v
                (2) COMPILE MAIN SOURCES
            src/main/java + processor path
                           |
                           +---- phát sinh .java -> generated/main
                           |
                           +---- javac biên dịch main + generated
                           |
                           v
                    build/classes/main
                           |
               +-----------+-----------+
               |                       |
          (3) PACKAGE                (4) COMPILE TEST
          app.jar                     src/test/java
               |                       + classpath main
               |                       + test dependencies
               |                       |
               |                       v
               |                 build/classes/test
               |                       |
               |                       v
               +                 (5) RUN TEST
                                      |
                                      v
                                 test result
```

**Đây là đồ thị quan hệ**, không phải lời khẳng định build tool nào cũng tạo mọi class theo đúng một thứ tự tác vụ vật lý. Annotation processing có thể **sinh và biên dịch source trong cùng một lần `javac`** theo nhiều processing rounds, hoặc generator độc lập chạy task riêng trước `compileJava`. Điều cần giữ là phụ thuộc đúng và đầu ra có chủ sở hữu rõ ràng.

### Ba câu hỏi kiểm tra thiết kế

1. **Ai sở hữu generated file?** Một processor, một schema generator, OpenAPI compiler hay codegen task? Tránh hai task ghi cùng đường dẫn.
2. **Generated file thuộc main hay test?** Nếu ứng dụng thật cần class thì đó là production output; nếu chỉ phục vụ test thì phải cách ly khỏi artifact.
3. **Khi đầu vào đổi, những việc gì phải chạy lại?** Thay annotation, schema hoặc dependency version phải kích hoạt task sinh và biên dịch phù hợp; đừng dựa vào file được tạo từ build cũ.

## 3. Ví dụ cấu trúc dự án tách tầng

Ta làm một demo không cần Maven/Gradle/JUnit để quan sát các nguyên tắc rõ ràng bằng `javac`.

```text
build-stages-lab/
├── src/
│   ├── processor/
│   │   └── java/
│   │       └── demo/
│   │           ├── generate/
│   │           │   └── GenerateGreeting.java
│   │           └── processor/
│   │               └── GreetingProcessor.java
│   ├── main/
│   │   └── java/
│   │       └── demo/app/Main.java
│   └── test/
│       └── java/
│           └── demo/app/MainTest.java
└── build/
    ├── processor/
    ├── classes/
    │   ├── main/
    │   └── test/
    └── generated/
        └── sources/main/
```

Trong demo, nhóm processor gồm cả **annotation API** và **implementation của processor** ở `src/processor/java` để người học chỉ cần biên dịch một lần. Trong hệ thống lớn, annotation API và processor implementation thường là **hai artifact**: mã main cần annotation API khi compile, còn processor implementation nằm trên annotation processor path.

Vị trí `src/processor/java` là **cấu trúc thủ công riêng của lab**, không phải một source set mà Gradle hoặc Maven tự động nhìn thấy trong dự án bất kỳ. Nếu chuyển sang build tool, đặt processor vào subproject/module riêng và khai báo dependency rõ ràng.

## 4. Bước 1: Xây dựng annotation API và processor

Tạo file `src/processor/java/demo/generate/GenerateGreeting.java`:

```java
package demo.generate;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {}
```

Đây là annotation mà source main sẽ dùng để yêu cầu tạo một class. `RetentionPolicy.SOURCE` phù hợp: annotation chỉ cần trong quá trình biên dịch và không phải bắt buộc có khi ứng dụng chạy.

Tạo file `src/processor/java/demo/processor/GreetingProcessor.java`:

```java
package demo.processor;

import demo.generate.GenerateGreeting;
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

@SupportedAnnotationTypes("demo.generate.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()
                || round.getElementsAnnotatedWith(GenerateGreeting.class).isEmpty()) {
            return true;
        }

        try {
            JavaFileObject output = processingEnv.getFiler()
                    .createSourceFile("demo.generated.Greeting");

            try (Writer writer = output.openWriter()) {
                writer.write("""
                        package demo.generated;
                        public final class Greeting {
                            private Greeting() {}
                            public static String text() {
                                return "Hello from generated source";
                            }
                        }
                        """);
            }
        } catch (IOException ex) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Generation failed: " + ex.getMessage());
        }
        return true;
    }
}
```

**Vai trò:** processor chạy trong JVM/compiler khi xử lý `@GenerateGreeting`. Nó tạo source logic `demo.generated.Greeting` bằng `Filer.createSourceFile(...)`, không trực tiếp tạo bytecode `Greeting.class`.

Tại sao cần `Filer` thay vì tự mở file bằng `Files.writeString`?

- `Filer` thuộc hợp đồng annotation processing và biết output location của compilation.
- `javac` quản lý generated compilation units và processing rounds liên quan.
- File được sinh có thể được compiler đưa vào vòng sau và biên dịch trong cùng compilation.
- Build tools có thể theo dõi generated files tốt hơn khi processor tuân thủ Filer API.

**Giới hạn demo:** processor này tạo **một class tên cố định** khi tìm thấy annotation; giả định chỉ có một nguồn kích hoạt generator trong compilation. Nếu nhiều phần tử cùng annotated, processor vẫn cố tạo một class duy nhất; muốn production-ready cần đặt tên và quản lý unique outputs, duplicate detection, và originating elements để build incremental theo dõi đúng phụ thuộc. Không dùng nguyên demo để tạo nhiều class trong hệ thống lớn.

### Biên dịch processor trước

Đứng trong thư mục `build-stages-lab`:

```bash
javac --release 17 -d build/processor src/processor/java/demo/generate/GenerateGreeting.java src/processor/java/demo/processor/GreetingProcessor.java
```

Sau khi thành công, các class quan trọng gồm:

```text
build/processor/demo/generate/GenerateGreeting.class
build/processor/demo/processor/GreetingProcessor.class
```

**Đây là output của giai đoạn xây dựng processor**, chưa phải output production của ứng dụng. Việc chúng ở `build/processor` giúp phân biệt rõ với `build/classes/main` và `build/classes/test`.

## 5. Bước 2: Main source gọi class được sinh

Tạo file `src/main/java/demo/app/Main.java`:

```java
package demo.app;

import demo.generate.GenerateGreeting;
import demo.generated.Greeting;

@GenerateGreeting
public final class Main {
    public static String message() {
        return Greeting.text();
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Ở thời điểm người học chưa chạy compiler, **không có file `demo/generated/Greeting.java` trong `src/main/java`**. Đó là chủ đích! Main source được viết để dùng type do processor tạo trong quá trình compilation.

### Biên dịch main và sinh source trong cùng invocation

```bash
javac --release 17 -cp build/processor -processorpath build/processor -processor demo.processor.GreetingProcessor -s build/generated/sources/main -d build/classes/main src/main/java/demo/app/Main.java
```

Phân tích từng option:

| Option | Vai trò |
| --- | --- |
| `--release 17` | Compile theo ngôn ngữ/API/class target của Java 17 |
| `-cp build/processor` | Để mã main tìm được `demo.generate.GenerateGreeting` |
| `-processorpath build/processor` | Nơi compiler tìm code `GreetingProcessor` |
| `-processor demo.processor.GreetingProcessor` | Chỉ định processor chạy tường minh, tránh phụ thuộc auto-discovery |
| `-s build/generated/sources/main` | Địa điểm lưu **source `.java` được processor tạo** |
| `-d build/classes/main` | Địa điểm lưu **class `.class` của main và generated classes** |
| `src/main/java/demo/app/Main.java` | Input source viết tay của main |

Điểm cực kỳ quan trọng:

- `-s` **không có nghĩa “class output”**; nó dành cho generated source.
- `-d` dành cho compiled classes.
- `-processorpath` không tự thêm annotation type vào compile classpath; demo phải có `-cp` vì main `import` annotation.
- `-processor` được đặt rõ để hành vi giống nhau giữa JDK/toolchain khác nhau; không nên giả định processor luôn được tự tìm và chạy.
- Lệnh **không liệt kê generated file trong source arguments**, vì `Filer` và `javac` đã quản lý nó trong cùng lượt xử lý.

Sau khi compiler chạy thành công, kiểm tra kết quả:

```text
build/generated/sources/main/demo/generated/Greeting.java
build/classes/main/demo/generated/Greeting.class
build/classes/main/demo/app/Main.class
```

File generated ở thư mục `build/generated`, **không nằm trong `src/main/java`**. Đó là phương án tốt cho vệ sinh repository và clean builds.

### Chạy main với chỉ class output

```bash
java -cp build/classes/main demo.app.Main
```

Stdout:

```text
Hello from generated source
```

Lệnh chạy này **không cần `build/processor` trên runtime classpath**, vì `@GenerateGreeting` có `RetentionPolicy.SOURCE` và class `Greeting` đã được tạo/biên dịch vào main output. Nếu code generated trong dự án khác cần một runtime library, thì library ấy phải được khai báo vào runtime classpath; không phải mọi annotation processor đều có runtime bằng 0.

Thí nghiệm được chạy thật với JDK 24 và `--release 17`: processor compilation và main compilation đều exit code `0`, generated `.java` và `.class` tồn tại, và main in đúng một dòng trên.

## 6. Bước 3: Biên dịch mã kiểm thử tách khỏi main

Không dùng JUnit ở ví dụ nhỏ để giảm phụ thuộc bên ngoài, nhưng nguyên tắc compile/test classpath giống nhau.

Tạo file `src/test/java/demo/app/MainTest.java`:

```java
package demo.app;

public final class MainTest {
    public static void main(String[] args) {
        String actual = Main.message();
        if (!"Hello from generated source".equals(actual)) {
            throw new AssertionError("Unexpected: " + actual);
        }
        System.out.println("TEST PASSED");
    }
}
```

Mã test **tham chiếu trực tiếp `Main.message()`**, nên lúc biên dịch test phải nhìn thấy main classes, bao gồm cả những class generated trong main output.

### Biên dịch test bằng output khác

Linux/macOS:

```bash
javac --release 17 -cp build/classes/main -d build/classes/test src/test/java/demo/app/MainTest.java
java -cp "build/classes/test:build/classes/main" demo.app.MainTest
```

Windows PowerShell/cmd:

```powershell
javac --release 17 -cp build/classes/main -d build/classes/test src/test/java/demo/app/MainTest.java
java -cp "build/classes/test;build/classes/main" demo.app.MainTest
```

Stdout của lệnh chạy test:

```text
TEST PASSED
```

Thí nghiệm cũng đã chạy thành công trên JDK 24 với runtime classpath **chỉ chứa output main/test**, không cần processor classes. Lớp `MainTest` không được sinh vào `build/classes/main` vì `-d build/classes/test` được dùng riêng.

**Quy tắc không đảo chiều phụ thuộc:** test đọc main, còn main **không nên** đọc test classes hoặc test framework. Nếu `Main.java` chỉ compile được khi thêm `build/classes/test` vào main classpath, đó thường là dấu hiệu sai kiến trúc hoặc test utilities bị đặt nhầm chỗ.

### Khi có thư viện kiểm thử thật

Ví dụ với JUnit Jupiter, test compilation cần JUnit API trên **test compile classpath** và chạy test cần test engine/launcher tương ứng. Các thư viện này không tự động cần được đóng gói vào JAR production. Maven/Gradle giúp quản lý các classpath đó; bài này không cố mô phỏng đầy đủ test runner của JUnit bằng lệnh `java` thuần.

**Tránh suy luận sai:** file có tên `MainTest.java` và `main` như ở demo vẫn là Java application test thủ công. Lệnh `java demo.app.MainTest` chỉ chạy phép thử; nó không phải JUnit test discovery. Khi dùng JUnit, build tool sẽ chạy một test task/plugin khác.

## 7. Tại sao không nên biên dịch tất cả chung một lượt?

Một cách làm sai về ranh giới:

```bash
javac -d all-classes src/main/java/demo/app/Main.java src/test/java/demo/app/MainTest.java
```

Lệnh **minh họa một anti-pattern**, không phải lệnh hợp lệ cho demo đã có generated class nếu bỏ processor/config đúng. Vấn đề kiến trúc khi ném cả main/test vào một output:

- Mã test có thể **vô tình xuất hiện trong JAR production** nếu package tất cả `all-classes`.
- Main có thể vô tình phụ thuộc lớp chỉ có trong test.
- Test libraries bị kéo vào compile graph của main, che lỗi missing dependency.
- Thay một file test có thể kích hoạt lại bước compile/packaging main không cần thiết.
- Generated code có thể thiếu rõ ràng owner và bị build lại sai thời điểm.
- Các quy tắc kiểm thử security/license/dependency scopes không còn dễ áp dụng.

Tách output không chỉ để “đẹp cấu trúc”. Nó giúp **đảm bảo artifact production chứa đúng phạm vi class** và giảm chi phí build lại.

### Không biến generated file thành mã viết tay

Không nên copy `build/generated/sources/main/demo/generated/Greeting.java` vào `src/main/java` rồi commit, trừ khi project có chính sách rõ rằng generator tạo source được kiểm tra/đóng băng để quản lý như mã viết tay. Nếu cả hai vị trí cùng có class `demo.generated.Greeting`, compiler có thể báo duplicate class hoặc lấy nhầm phiên bản.

Một generated file cần được coi như **output có thể tái tạo từ input**. Với annotation processor, input có thể là annotation/source, compiler options và implementation processor; với schema generator, input có thể là schema file, generator version và config.

## 8. Generated source phát sinh trong cùng lượt hay từ task riêng?

Hai hình thức phổ biến:

### 8.1. Annotation processing cùng lượt javac

```text
javac input Main.java
  -> processor phát hiện @GenerateGreeting
  -> Filer tạo Greeting.java
  -> javac xử lý round kế tiếp
  -> javac sinh Main.class + Greeting.class
```

Ví dụ ở mục 5 sử dụng hình thức này. Source generated **không cần** được liệt kê thủ công như một source root thứ hai trong chính compilation task ấy.

Cần chú ý:

- Khi processor phát sinh source nhiều round, chỉ tạo file mới khi thực sự cần.
- `Filer` thường ngăn ghi hai lần cùng một tên output trong cùng lượt; có thể phát sinh `FilerException` nếu processor cố tạo trùng.
- Không nên gọi `-proc:only` khi mong compiler sinh `Main.class` và `Greeting.class` trong cùng lượt; `-proc:only` chỉ xử lý annotation, không tạo class file của source.
- Chỉ định processor rõ ràng giúp tránh thay đổi behavior auto-discovery qua các JDK.

### 8.2. Code generator chạy như task riêng

```text
schema.yaml / API definition
         |
         v
  generateJavaSources
         |
         v
 build/generated/schema/java/*.java
         |
         v
     compileJava
         |
         v
 build/classes/java/main/*.class
```

Ví dụ khi dùng OpenAPI generator, Protocol Buffers hoặc tool sinh API có executable riêng, task `generateJavaSources` phải được gắn làm dependency của `compileJava`, và **source output directory** phải là input của compile task. Không nên chạy code generator bằng tay một lần rồi hy vọng `compileJava` sẽ tự biết có input mới.

**Không tạo cycle:** generator thường cần API/tool của chính nó trước; tránh bắt task generator phụ thuộc output của code mà generator sẽ tạo ra nếu điều đó gây vòng tròn build.

## 9. Phân biệt -s, -d, -cp, -processorpath và -proc

| Flag javac | Loại dữ liệu | Ví dụ | Câu hỏi cần hỏi |
| --- | --- | --- | --- |
| `-s` | Generated Java source destination | `-s build/generated/sources/main` | “Processor viết `.java` ở đâu?” |
| `-d` | Class file destination | `-d build/classes/main` | “Compiler đặt `.class` ở đâu?” |
| `-cp` / `--class-path` | Thư viện/class input của compilation | `-cp build/processor` | “Source đang compile cần nhìn thấy type nào?” |
| `-processorpath` | Nơi tìm annotation processor | `-processorpath build/processor` | “Compiler chạy implementation processor nào?” |
| `-processor` | Chọn processor tường minh | `-processor demo.processor.GreetingProcessor` | “Processor nào được chạy?” |
| `-proc:only` | Chỉ xử lý annotation | `-proc:only` | “Chỉ tạo nguồn/check diagnostics, không phát sinh class file?” |
| `-proc:none` | Tắt annotation processing | `-proc:none` | “Có cần loại bỏ processor khi khoanh vùng vấn đề?” |
| `--release` | Target Java platform | `--release 17` | “Bytecode/API mục tiêu là phiên bản nào?” |

Một lỗi rất thường gặp là “đưa generated source vào `-d`”: `-d` không phải tên thư mục generated Java. Một lỗi khác là chạy `-proc:only` cho main rồi thắc mắc thiếu `Main.class`. Hai loại output khác nhau, vì thế cần hai đường dẫn rõ ràng.

### Lệnh kiểm tra nhanh class được tạo

Sau khi build:

```bash
javap -classpath build/classes/main demo.generated.Greeting
javap -classpath build/classes/main demo.app.Main
javap -classpath build/classes/test demo.app.MainTest
```

Những lệnh này dùng `javap` để xác nhận class có mặt ở đúng output. `javap` in chữ ký class/method tùy JDK; chúng ta chỉ quan tâm class có được tìm thấy hay không, không buộc output giống tuyệt đối một phiên bản.

## 10. Cách Gradle tổ chức main, test và generated sources

Với **Gradle Java plugin**, hai source sets mặc định là **`main`** và **`test`**.

Cấu trúc quy ước:

```text
src/main/java                -> main sources
src/main/resources           -> main resources
src/test/java                -> test sources
src/test/resources           -> test resources
build/classes/java/main      -> main Java classes
build/classes/java/test      -> test Java classes
build/generated/sources/annotationProcessor/java/main
build/generated/sources/annotationProcessor/java/test
```

Đường generated ở trên là **quy ước mặc định của Gradle JavaCompile cho Java source set** ở các phiên bản tài liệu tương ứng, và có thể được cấu hình lại bằng `CompileOptions.generatedSourceOutputDirectory`. Đừng hard-code đường đó vào tất cả script rồi mặc nhiên đúng với plugin tùy chỉnh.

### Tasks mặc định

| Task Gradle | Vai trò |
| --- | --- |
| `compileJava` | Biên dịch `main`, gồm annotation processing cấu hình cho main |
| `processResources` | Xử lý main resources |
| `classes` | Gom việc chuẩn bị main classes/resources |
| `compileTestJava` | Biên dịch test source dựa trên main output và test dependencies |
| `processTestResources` | Chuẩn bị tài nguyên test |
| `testClasses` | Gom output test classes/resources |
| `test` | Chạy test qua test framework phù hợp |
| `jar` | Đóng gói output main vào JAR |
| `build` | Kết hợp assemble/check theo lifecycle Gradle |

`compileTestJava` phụ thuộc vào output `main`, không phải chạy trước. `jar` mặc định dựa trên main source set output, **không kéo test classes vào JAR production**. Chỉ khi tự thay cấu hình artifact (ví dụ fat/uber jar hoặc packaging tùy chỉnh) mới cần kiểm tra thành phần khác.

### Gradle Kotlin DSL đơn giản

Một `build.gradle.kts` tối thiểu (với Gradle/JDK hỗ trợ Java toolchains):

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
```

Snippet này chủ yếu cho thấy **toolchain và target release** áp dụng cho những `JavaCompile` tasks. Nó **không tự thêm processor, test framework hay generator** vì các dependency ấy phụ thuộc project. Nếu dùng plugin `java-library`, `application` hay codegen khác, xem cấu hình source set/task do plugin đóng góp.

Dùng `./gradlew compileJava`, `./gradlew compileTestJava`, `./gradlew test` hoặc `./gradlew build` theo môi trường; trên Windows cũng có wrapper `gradlew.bat`. Không gọi `javac` thủ công thêm vào một Gradle build đã cấu hình đúng nếu điều đó khiến hai hệ thống output cạnh tranh nhau.

### Cấu hình dependencies cho processor khác main runtime

Giả sử một multi-project Gradle build có hai subprojects riêng cung cấp annotation API và processor implementation, ví dụ `:annotation-api` và `:greeting-processor`. Ở project ứng dụng, phần `dependencies` có thể viết:

```kotlin
dependencies {
    compileOnly(project(":annotation-api"))
    annotationProcessor(project(":greeting-processor"))

    testCompileOnly(project(":annotation-api"))
    testAnnotationProcessor(project(":greeting-processor"))
}
```

Đây là **minh họa cho multi-project build đã có hai project con hợp lệ**, không phải một build hoàn chỉnh có thể chạy nếu chưa định nghĩa `settings.gradle.kts`, code processor và dependencies đúng. Hai nhóm đường dẫn khác nhau:

- `compileOnly` giúp source main import annotation API nhưng không tự đưa dependency vào production runtime.
- `annotationProcessor` cung cấp processor cho **main compile task**.
- `testCompileOnly` và `testAnnotationProcessor` phục vụ test source khi test cũng sử dụng annotation/generator riêng; không bắt buộc nếu test chỉ gọi class main đã sinh.

Trong demo `javac`, `GenerateGreeting` nằm cùng artifact với processor cho tiện. Trong Gradle nhiều module, tách annotation API khỏi processor implementation sẽ thuận lợi hơn cho dependency isolation.

### Không add generated annotation sources vào main sourceDirs thêm một lần

Nếu annotation processor đã tạo nguồn **bên trong chính `compileJava`**, Gradle/`javac` xử lý nó như output của annotation processing. Việc tự thêm thư mục `build/generated/sources/annotationProcessor/java/main` thành source root của `main` có thể làm generated file bị compiler nhập thêm một lần, gây duplicate source, khó khăn incremental tracking hoặc task dependency không rõ.

**Quy tắc:** chỉ khai báo source directory của task codegen **độc lập** khi đó là input được sản xuất **trước compileJava**; không “đăng ký lại” output của processor trong cùng task như một nguồn viết tay.

### Codegen task độc lập và generated root

Nếu có task chuyên tạo source từ schema, cách phù hợp là nối **producer task** với **consumer source set** qua task output/provider, để Gradle biết phụ thuộc và không phụ thuộc vị trí hard-code. Khái niệm:

```text
generateApiCode (output: build/generated/api/java)
       |
       v
compileJava (input: src/main/java + output của generateApiCode)
```

Các codegen plugins thường cung cấp cách đăng ký generated source và task dependencies. Không chỉ viết `java.srcDir("build/generated/api/java")` khi chưa tạo dependency tới task sản xuất thư mục ấy: Gradle có thể compile trước generator, dùng source cũ hoặc cảnh báo mơ hồ đầu vào.

Với generated test source cũng tương tự: nối output vào **test source set** và `compileTestJava`, không vô tình thêm vào main.

## 11. Maven lifecycle: compile, test-compile và generated-sources

Maven theo quy ước:

```text
src/main/java                 -> target/classes
src/test/java                 -> target/test-classes
target/generated-sources/annotations
target/generated-test-sources/test-annotations
```

Maven Compiler Plugin có hai goal quan trọng:

- `compiler:compile`: biên dịch nguồn chính vào `target/classes`, mặc định gắn lifecycle phase `compile`.
- `compiler:testCompile`: biên dịch nguồn test vào `target/test-classes`, mặc định gắn lifecycle phase `test-compile`.

Trong lifecycle `mvn test`, Maven đi qua các pha cần thiết trước đó: chuẩn bị/generate main sources, compile main, xử lý/generate test sources, compile test, rồi chạy test bằng plugin thích hợp (ví dụ Surefire). **`test-compile` khác `test`**: một pha tạo test classes, một pha thực thi test.

### Cấu hình release cho Maven

Đoạn plugin trong `pom.xml`:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.16.0</version>
  <configuration>
    <release>17</release>
  </configuration>
</plugin>
```

Đây là **một đoạn trong `<build><plugins>...` của POM**, không phải tệp POM độc lập. Nó cấu hình target Java 17 cho compiler plugin; dependency của processor và test framework phải được khai báo riêng tùy dự án. Dải version plugin cần phù hợp Maven/JDK đang dùng; kiểm tra tài liệu plugin tương ứng thay vì chỉ chép số version.

Maven Compiler Plugin có tùy chọn `generatedSourcesDirectory` và `generatedTestSourcesDirectory` để quản lý vị trí nguồn do annotation processing tạo ở hai giai đoạn. Giá trị mặc định thường nằm ở hai đường `target/generated-sources/annotations` và `target/generated-test-sources/test-annotations` tương ứng.

### Annotation processor trong Maven

Maven compiler plugin có các cấu hình cho processor, processor path và annotation processing, nhưng **cú pháp chi tiết phụ thuộc phiên bản plugin** (đặc biệt các thay đổi ở dòng plugin 4.x/Maven mới). Nếu processor được đóng gói thành artifact riêng, cần bảo đảm:

1. Annotation API có trong compile dependencies khi mã chính import annotation.
2. Compiler biết processor nào được chọn và tìm được implementation cùng dependencies của nó.
3. Generated source output cho main/test không chồng lấn.
4. Khi build clean, module processor được xây dựng/resolve trước module sử dụng.
5. Generated source được theo dõi bởi chính compiler plugin hoặc generator plugin, không thêm source root trùng lặp.

Không nên lẫn `maven-compiler-plugin` với `maven-surefire-plugin`: plugin compiler tạo test class files, còn plugin test thực thi các test được phát hiện theo cấu hình.

### Lệnh thường dùng và ý nghĩa

```bash
mvn clean compile
mvn test-compile
mvn test
mvn package
```

- `clean compile`: xóa output Maven trước rồi biên dịch main.
- `test-compile`: chạy các pha cần để tạo test classes nhưng **không có nghĩa test đã được thực thi**.
- `test`: thực thi test lifecycle.
- `package`: tạo JAR hoặc artifact theo packaging, sau các pha test liên quan.

**Đừng đoán rằng Maven/Gradle đặt generated source ở cùng đường dẫn**. Chúng có layout khác nhau; đọc output thực và cấu hình plugin để biết chính xác.

## 12. Annotation processor chỉ dành cho main hay cần cả test?

Nếu test chỉ gọi production APIs đã được sinh trong main, ví dụ `MainTest` gọi `Main.message()`, thường không cần chạy lại `GreetingProcessor` trên test sources. `compileTestJava` chỉ cần main output trên classpath.

Nếu **test source tự chứa annotation cần codegen**, thì test compilation cũng phải có processor path và source output riêng:

```text
main compile:
  src/main/java + processor(main)
    -> generated/main
    -> classes/main

test compile:
  src/test/java + classes/main + processor(test)
    -> generated/test
    -> classes/test
```

Dùng đúng loại dependency test annotation processor (`testAnnotationProcessor` trong Gradle hoặc cấu hình plugin testCompile tương ứng trong Maven). Đừng nhét generated test classes vào output main để “cho test nhìn thấy”, vì như vậy test-only code có thể đi vào JAR production.

### Test fixtures và integration tests

Trong dự án lớn còn có `testFixtures`, `integrationTest`, `functionalTest` hoặc source sets tương tự; chúng **không phải** tất cả là nguồn main. Hãy xác định rõ dependency hướng nào:

```text
main
  |
  +----> unitTest
  |
  +----> integrationTest
             |
             +----> test fixtures (nếu có)
```

Đây là quan hệ nhìn thấy output, không phải bắt buộc mọi build đều định nghĩa các source sets trên. Với Gradle có thể tạo source set custom; Maven có thể dùng plugin/framework cho integration tests. Mỗi tập nên có compile/runtime classpath và output rõ.

## 13. Generated sources trong JAR: chỉ bytecode nào thuộc production?

Sau khi build main và test, thường có:

```text
build/classes/main/demo/app/Main.class
build/classes/main/demo/generated/Greeting.class
build/classes/test/demo/app/MainTest.class
```

Tạo JAR production bằng cách chỉ đóng gói `build/classes/main`. Ví dụ ở thư mục lab:

```bash
jar --create --file build/app.jar -C build/classes/main .
```

Dùng lệnh:

```bash
jar --list --file build/app.jar
```

Để kiểm tra JAR chứa `demo/app/Main.class` và `demo/generated/Greeting.class`, nhưng **không chứa** `demo/app/MainTest.class` hoặc processor implementation. Lệnh `jar` trên cần **JDK jar tool** và đường dẫn `build/classes/main` có thật; không có phép dò module source ở đây.

Có thể chạy:

```bash
java -cp build/app.jar demo.app.Main
```

Stdout vẫn là:

```text
Hello from generated source
```

**Đây là kiểm thử packaging**, không phải test runner. Nếu ứng dụng phụ thuộc runtime JAR ngoài, phải cấp chúng thêm trên runtime classpath. Ví dụ lab không cần thư viện runtime ngoài Java standard library và code generated.

Một file generated `.java` có thể được giữ lại như artifact để debug, nhưng thông thường không có trong production runtime JAR, trừ khi bạn cố ý đóng gói source archive hoặc classifier riêng.

## 14. Thứ tự build và incremental correctness

Các build systems tối ưu bằng incremental compilation và build cache. Chúng chỉ tái tạo kết quả đáng tin khi **mọi đầu vào có ý nghĩa đều được khai báo**:

- Source files và annotations.
- Dependency graph, compile classpath và processor path.
- Generator implementation/version và options.
- Schema/config/resources mà generator đọc.
- JDK/toolchain/release/compiler options.
- Output directory và ownership task.
- Những environment variables thực sự ảnh hưởng tới generated output nếu build system có cách khai báo.

Nếu processor tự đọc file ngoài nhưng không khai báo làm input, Gradle/Maven hoặc cache có thể **không biết phải chạy lại** khi file ấy đổi. Đừng sửa bằng cách luôn chạy `clean` trong mọi build: clean giúp khoanh vùng, nhưng không thay thế thiết kế task inputs/outputs đúng.

### Incremental annotation processing

Gradle phân biệt **isolating** và **aggregating** annotation processors:

- **Isolating:** generated file phụ thuộc vào một hoặc một nhóm phần tử origin được xác định theo quy tắc hỗ trợ; thường cho phép rebuild phạm vi nhỏ.
- **Aggregating:** kết quả kết hợp dữ liệu từ nhiều annotated elements, nên phạm vi ảnh hưởng có thể rộng hơn.
- Processor không đáp ứng cơ chế incremental có thể khiến compile task phải xử lý/biên dịch lại nhiều hơn.

Với `Filer.createSourceFile(...)`, API cho phép truyền **originating elements** để hỗ trợ tracking. Processor demo đã viết tên cố định và không truyền origin nhằm giữ ví dụ dễ đọc; **không coi đó là processor tối ưu cho Gradle incremental**. Khi phát hành processor thật, hãy thiết kế cách lấy origins, khai báo loại processor và tránh đọc dữ liệu ngoài không được track.

Theo tài liệu Gradle, một số processor không tuân thủ hợp đồng incremental sẽ làm full recompilation. Thông tin “biên dịch incremental thành công” phải kiểm tra bằng log và build behavior thực tế, không chỉ dựa vào việc source file không đổi.

### Những lỗi stale generated code

Giả sử generator trước đây tạo `OldApi.java`, sau khi đổi schema nó chỉ tạo `NewApi.java`. Nếu task không **dọn output cũ**, `OldApi.java` có thể vẫn nằm ở thư mục generated và bị compile vào artifact. Đây là lý do generated directory cần thuộc task rõ ràng; không dùng chung một thư mục output cho nhiều producer không có chiến lược xóa/ghi an toàn.

Nếu một file nguồn bị đổi package, **class output cũ** cũng có thể tồn tại khi không clean đúng; một deployment đọc nhầm class cũ là lỗi artifact hygiene, không phải chứng cứ compiler đã bỏ qua mã mới.

## 15. Checklist build sạch có tái lập

Để chứng minh workflow hợp lệ từ checkout mới:

1. Xóa **đúng thư mục build output của dự án đang kiểm thử** hoặc chạy `gradlew clean`/`mvn clean` theo công cụ; không xóa bừa thư mục khác.
2. Khôi phục dependencies bằng build tool hoặc chuẩn bị processor artifacts đúng version.
3. Chạy task processor/codegen (nếu tách riêng); kiểm tra generated file có tạo từ input thật.
4. Biên dịch main. Kiểm tra source generated được compiler đưa vào, class phát sinh ở output main.
5. Biên dịch test với main output/classpath; test output phải riêng.
6. Chạy test; đọc exit code và test reports, không chỉ nhìn “compilation successful”.
7. Đóng gói production artifact; kiểm tra test classes và processor implementation **không bị lẫn** nếu không có nhu cầu đặc biệt.
8. Chạy artifact production bằng runtime dependencies thực.
9. Thay source annotation hoặc schema, build lại và xác minh generated output cập nhật.
10. Kiểm tra incremental behavior: thay test-only source không khiến main compile lại vô cớ; thay main ABI phải tái biên dịch test phụ thuộc khi cần.

### Lệnh javac chẩn đoán

```bash
javac --help
javac -X
java -version
javac -version
```

Một số nguyên nhân “chạy máy khác mới lỗi” xuất phát từ **JDK khác phiên bản**, annotation processor không được kích hoạt, khác classpath, hoặc build cache khác. Cần ghi nhận compiler/toolchain và toàn bộ arguments của tác vụ thực tế.

## 16. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `package demo.generated does not exist` khi compile main | Processor chưa chạy, sai processor path, tạo sai package hoặc invocation bỏ `-processor` | Kiểm tra giai đoạn processor và `-s`/`-d` |
| Generated `.java` có nhưng không có `.class` | Đã chạy `-proc:only`, lỗi compile generated source, hoặc chưa có bước compile tiếp theo | Kiểm tra mode javac và diagnostics |
| Test không nhìn thấy `Main` | Test compile classpath thiếu main output | Thêm `build/classes/main` hoặc phụ thuộc task phù hợp |
| Main chỉ compile khi có JUnit | Main vô tình import test framework | Chuyển code/test utility sang test source, kiểm tra dependency scope |
| Test class xuất hiện trong app.jar | Đóng gói nhầm toàn bộ build directory hoặc test output | Chỉ lấy output của main khi package |
| Processor implementation nằm trong runtime | Khai báo processor như dependency `implementation` không cần thiết | Dùng annotation processor path và API dependency thích hợp |
| `FilerException` khi sinh code | Processor cố tạo lại cùng file trong một compilation hoặc trùng producer | Thiết kế duy nhất tên output và rounds |
| Generated code không đổi khi schema đổi | Task inputs/outputs không khai báo đủ, cache/up-to-date sai | Khai báo schema là input và dùng task output provider |
| Xóa generated file nhưng build vẫn pass rồi runtime lỗi | Class output cũ còn trên classpath | Build sạch có kiểm soát, kiểm tra JAR thật |
| `NoClassDefFoundError` ở runtime | Generated class không được package hoặc thiếu runtime dependency | Kiểm tra class files/JAR và classpath runtime |
| Test chạy trên IDE nhưng CI không compile | IDE auto-add generated source/processor, CI chưa cấu hình | Đồng bộ build tool config và test clean CI |
| Có hai nguồn cùng tên fully-qualified class | Copy generated source vào handwritten source hoặc hai generators cùng output | Một chủ sở hữu, một đường output |
| Java 17 target không được tôn trọng | Toolchain khác, chưa cấu hình `--release` | Kiểm tra compile options của main/test/codegen |
| Annotation processor JDK mới không tự chạy | Dựa vào auto-discovery mặc định đã đổi | Cấu hình processor path/processor rõ trong build |

**Phân loại đúng pha là bước đầu tiên khi debug.** Một lỗi “generated class not found” ở main compilation cần kiểm tra processor/source output; ở test compilation cần kiểm tra main output/classpath; ở runtime cần kiểm tra artifact đã đóng gói và dependencies runtime.

## 17. Bài tập có đáp án

### Bài 1: Sắp xếp task

Cho: `compileTestJava`, `compileJava`, `generateApi`, `test`. Nếu `compileJava` cần generated source từ `generateApi`, thứ tự logic nào đúng?

**Đáp án:** `generateApi` trước `compileJava`; `compileTestJava` phụ thuộc main output; `test` chạy sau test compilation. Build tool có thể tổ chức task graph khác về song song, nhưng phải giữ những cạnh phụ thuộc thực sự.

### Bài 2: -s và -d

Một processor tạo `demo.generated.Greeting.java`; bạn muốn giữ source ở `build/generated/sources/main` và class ở `build/classes/main`. Dùng hai option nào?

**Đáp án:** `-s build/generated/sources/main` và `-d build/classes/main`. Không tráo hai option.

### Bài 3: Test classpath

`MainTest` gọi `Main.message()` nhưng compiler báo không tìm thấy `Main`. Thử test compile chưa có main output. Cần sửa gì?

**Đáp án:** Biên dịch main trước và thêm main output vào **test compile classpath**, đồng thời giữ `-d` test riêng.

### Bài 4: Processor path và compile classpath

Mã main import `@GenerateGreeting`, processor implementation chỉ dùng trong build. Có thể bỏ compile classpath annotation API và chỉ truyền `-processorpath` không?

**Đáp án:** Không trong demo này. Code main vẫn phải nhìn thấy `GenerateGreeting` như một type để compile; processor path phục vụ việc compiler nạp processor, không tự thay nghĩa của compile classpath.

### Bài 5: Generated Java trong production JAR

Một generated source `Greeting.java` được biên dịch thành `Greeting.class` thuộc main. JAR production có nhất thiết chứa file `Greeting.java` không?

**Đáp án:** Không. JAR ứng dụng thường đóng gói compiled classes/resources của main; class generated có thể vào JAR, còn Java source thường không.

### Bài 6: -proc:only

Một task dùng `-proc:only` đã tạo `Greeting.java` nhưng không thấy `Main.class`. Có phải generator hỏng?

**Đáp án:** Chưa chắc. `-proc:only` chủ động ngăn phát sinh class files; nếu muốn biên dịch class, bỏ option hoặc tạo bước compile riêng cho generated source.

### Bài 7: Chỉ sửa test code

Thay `MainTest.java` nhưng giữ main/codegen inputs nguyên. Về lý tưởng, những task nào phải chạy lại?

**Đáp án:** Chủ yếu `compileTestJava` và `test`; main codegen/main compile không cần chạy lại nếu đồ thị inputs/outputs và caching đúng. Không phải là cam kết với mọi plugin custom.

### Bài 8: Generated file bị lưu cũ

Sau khi rename annotation từ một kiểu sang kiểu khác, file generated cũ vẫn còn và tiếp tục bị đóng gói. Bạn chỉ sửa source Java ở `src/main` có đủ không?

**Đáp án:** Không. Kiểm tra task generator, directory ownership, deletion policy, build cache/incremental inputs và actual packaging; dùng clean build để xác định nguyên nhân, rồi sửa cấu hình lâu dài.

### Bài 9: Thư viện JUnit có mặt trong JAR

Nếu `jar --list` cho thấy toàn bộ test classes và test libraries trong artifact production ngoài ý muốn, cần xem phần nào?

**Đáp án:** Cấu hình packaging/fat JAR và source set output, cùng dependency scopes. Không “xóa class sau khi package” thủ công như giải pháp chính.

## 18. Kết luận và tài liệu

**Tách mã chính, mã kiểm thử và nguồn được sinh là tách ba hợp đồng build**, không chỉ tách ba thư mục:

- **Main** tạo code chạy thực tế; classpath và artifact theo nhu cầu production.
- **Test** sử dụng main output và dependencies kiểm thử, được biên dịch/chạy ở giai đoạn riêng.
- **Generated** là kết quả của một producer; phải có task ownership, output directory, dependency graph và cơ chế tái tạo rõ ràng. Class generated của main có thể thuộc production, nhưng generated source không tự động là test hay main nếu chưa được nối đúng vào compile task.

Ví dụ `javac` chứng minh cùng một build có thể có **processor compilation → main compile/code generation → test compile → test run → production packaging**, mỗi giai đoạn kiểm chứng được và không lẫn output.

Nguồn chính thống:

1. [Oracle JDK 21 — javac command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `-s`, `-d`, `-processorpath`, `-processor`, `-proc`, `--release`.
2. [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `main`/`test` source sets, `compileJava`, `compileTestJava`, classpaths và incremental annotation processing.
3. [Gradle — CompileOptions](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html): `generatedSourceOutputDirectory` và release/encoding options.
4. [Apache Maven Compiler Plugin — compiler:compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html): compilation của main và generated main source.
5. [Apache Maven Compiler Plugin — compiler:testCompile](https://maven.apache.org/plugins/maven-compiler-plugin/testCompile-mojo.html): test source output và generated test sources.
6. [Java SE 17 — Filer](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html): tạo source files qua annotation processing.
7. [Java SE 17 — RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html): vòng xử lý và elements được annotate.

Khi một build thất bại, hãy xác định chính xác **pha nào thất bại, input nào còn thiếu, output được kỳ vọng ở đâu và classpath nào đang được dùng**. Làm rõ bốn câu hỏi ấy sẽ giúp bạn sửa nguyên nhân thay vì trộn main/test/generated rồi cố “thêm mọi thư mục vào classpath” cho hết lỗi.