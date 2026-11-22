# Kiểm tra mã sinh bằng một lần biên dịch sử dụng thực tế

## 1. Vì sao phải biên dịch mã được sinh ra?

Trong Java, *generated code* là mã nguồn hoặc bytecode được tạo tự động từ annotation, schema, template, DSL hoặc một bước build. Ví dụ: annotation processor sinh class truy cập dữ liệu, API client generator sinh model và endpoint, hay công cụ sinh adapter cho một interface.

Việc **có file được tạo** chưa đủ để kết luận generator đúng. File `.java` có thể có cú pháp hợp lệ nhưng sử dụng sai tên package, thiếu import, sai kiểu generic, sai visibility, nhầm phương thức hoặc phụ thuộc vào thư viện không có trong classpath của ứng dụng. Chỉ so chuỗi nguồn với *golden file* cũng dễ bỏ sót lỗi tương thích với code thật.

Tiêu chí mạnh hơn là:

> Cho **mã người dùng thực sự gọi API được sinh** tham gia một lần biên dịch sạch, bằng đúng Java compiler, phiên bản Java và classpath dự kiến sử dụng; xem toàn bộ phép biên dịch thành công hay thất bại.

Trong bài này, “một lần biên dịch sử dụng thực tế” nghĩa là **một lần gọi `javac` biên dịch nguồn ứng dụng có tham chiếu đến class do annotation processor sinh**, để compiler tự chạy các vòng xử lý annotation và kiểm tra client trong cùng phép biên dịch. Trước đó ta vẫn cần biên dịch processor thành công cụ có thể chạy — đây là bước chuẩn bị, không phải một lần biên dịch thứ hai dùng để vá mã sinh.

## 2. Hợp đồng cần kiểm tra

Một phép kiểm thử biên dịch có giá trị phải xác nhận đồng thời các mối liên hệ:

| Thành phần | Điều cần xác minh |
|---|---|
| **Input của generator** | Annotation/schema và cấu hình đúng, thực sự kích hoạt generator |
| **Mã sinh ra** | File được tạo đúng package, class, member, kiểu trả về, modifier và generic |
| **Consumer thực tế** | Một class Java bên ngoài generator có thể import, tạo đối tượng hoặc gọi API đó |
| **Java compiler** | `javac` kiểm tra toàn bộ nguồn thật với `--release`/toolchain mục tiêu |
| **Classpath** | Có đúng dependency cần thiết, không “vô tình” thấy class của test hoặc artifact cũ |
| **Output** | File `.java` và `.class` được tạo trong thư mục sạch; lỗi compilation làm build thất bại |

Ví dụ, nếu generator định tạo `HelloGenerated.greet(String): String` nhưng lại sinh thành `greet(Object): int`, một test chỉ đếm file hoặc tìm tên class vẫn có thể đạt. Consumer gán kết quả vào biến `String` buộc compiler xác nhận chữ ký mong đợi và phát hiện sai kiểu.

Kiểm thử kiểu này có phạm vi rõ ràng: nó chứng minh **hợp đồng biên dịch** với các tình huống đã xây dựng, không tự chứng minh logic runtime, hiệu năng, tính ổn định thread, tính bảo mật hay mọi cấu hình có thể có.

## 3. Cơ chế annotation processing của `javac`

Với Java annotation processor chuẩn (JSR 269), trình biên dịch có thể thực hiện nhiều **processing rounds trong cùng một compilation invocation**:

1. `javac` đọc nguồn người dùng và xác định annotation cần xử lý.
2. Processor quan sát các element đã gắn annotation và dùng `Filer` tạo file nguồn mới.
3. Trình biên dịch đưa các file mới vào vòng tiếp theo; processor khác có thể xử lý annotation trên chúng.
4. Khi không còn nguồn mới, vòng xử lý kết thúc và compiler kiểm tra/biên dịch nguồn ban đầu lẫn nguồn sinh ra.
5. Nếu client sử dụng generated API sai kiểu, sai visibility hoặc thiếu symbol, toàn bộ lệnh `javac` thất bại.

Vì vậy, với generator dựa trên `Filer`, **không cần và không nên biên dịch thủ công file generated trong một lệnh `javac` thứ hai chỉ để chứng minh smoke test này**. Biên dịch lần thứ hai riêng lẻ có thể vô tình lấy các class cũ và bỏ qua vấn đề trong luồng thực tế.

Hai đường dẫn phải phân biệt rõ:

- **Processor path** (`-processorpath`): nơi `javac` tìm class thực thi annotation processor.
- **Compilation classpath** (`-classpath` hoặc `-cp`): nơi source ứng dụng tìm annotation, thư viện và các API nó tham chiếu.

Processor có thể được cung cấp tường minh bằng `-processor lab.GreetingProcessor`; khi dùng cách này, ví dụ không cần đăng ký service loader. Trong dự án thật, Gradle/Maven có thể cấu hình processor discovery qua dependency/`META-INF/services/javax.annotation.processing.Processor` hoặc cơ chế hỗ trợ tương ứng.

## 4. Ví dụ đầy đủ với Java 17+: sinh một API và biên dịch client

Ta xây một annotation processor tạo class `lab.generated.HelloGenerated` từ annotation `@GenerateGreeting`. Consumer sẽ gọi `HelloGenerated.greet("Lan")` và yêu cầu kết quả là `String`.

Cấu trúc file:

~~~text
src/
├── processor/
│   └── lab/
│       ├── GenerateGreeting.java
│       └── GreetingProcessor.java
└── app/
    └── demo/
        ├── GreeterSpec.java
        └── Demo.java
~~~

### 4.1. Định nghĩa annotation

File `src/processor/lab/GenerateGreeting.java`:

~~~java
package lab;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
}
~~~

`RetentionPolicy.SOURCE` đủ cho processor đọc annotation khi biên dịch; không yêu cầu annotation xuất hiện trong bytecode runtime.

### 4.2. Viết processor sinh source qua Filer

File `src/processor/lab/GreetingProcessor.java`:

~~~java
package lab;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("lab.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {
            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile("lab.generated.HelloGenerated", element)
                    .openWriter()) {
                writer.write("""
                    package lab.generated;

                    public final class HelloGenerated {
                        private HelloGenerated() {}

                        public static String greet(String name) {
                            return "Xin chào, " + name + "!";
                        }
                    }
                    """);
            } catch (IOException exception) {
                processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR,
                    "Không tạo được HelloGenerated: " + exception.getMessage(),
                    element
                );
            }
        }
        return true;
    }
}
~~~

Điểm đáng chú ý:

- `@SupportedAnnotationTypes` khai báo chính xác annotation mà processor xử lý; `@SupportedSourceVersion` cho biết phiên bản ngôn ngữ được hỗ trợ.
- `roundEnv.getElementsAnnotatedWith(...)` chỉ chọn source có annotation, tránh phát sinh file khi không có yêu cầu.
- `Filer.createSourceFile(...)` đăng ký file với compiler để xử lý ở vòng sau; `element` là **originating element**, hữu ích cho các cơ chế theo dõi nguồn sinh.
- `Diagnostic.Kind.ERROR` biến lỗi sinh mã thành lỗi compilation, không nuốt lỗi rồi trả về một build xanh.
- Ví dụ có **đúng một class được annotate**. Generator sản xuất tên class cố định như thế này cần quy tắc riêng để tránh xung đột nếu nhiều element cùng được annotate; bài thực hành này cố ý giữ phạm vi đơn giản.

### 4.3. Tạo input và consumer thực tế

File `src/app/demo/GreeterSpec.java`:

~~~java
package demo;

import lab.GenerateGreeting;

@GenerateGreeting
public final class GreeterSpec {
}
~~~

File `src/app/demo/Demo.java`:

~~~java
package demo;

import lab.generated.HelloGenerated;

public final class Demo {
    public static void main(String[] args) {
        String greeting = HelloGenerated.greet("Lan");
        System.out.println(greeting);
    }
}
~~~

`Demo.java` **không phụ thuộc vào mã nguồn processor**; nó phụ thuộc vào **API được tạo ra**. Việc gán kết quả vào biến `String` chủ động xác minh kiểu trả về. Nếu generator thay signature không tương thích, chính compiler của consumer sẽ phát hiện.

### 4.4. Biên dịch processor một lần để chuẩn bị

Dùng JDK 17 hoặc mới hơn, tại thư mục chứa `src`. Tạo ba thư mục output sạch; trên macOS/Linux:

~~~bash
mkdir -p verify-out/processor verify-out/generated verify-out/classes
javac --release 17 -d verify-out/processor   src/processor/lab/GenerateGreeting.java   src/processor/lab/GreetingProcessor.java
~~~

Trên Windows PowerShell, có thể tạo thư mục bằng `New-Item -ItemType Directory -Force verify-out/processor,verify-out/generated,verify-out/classes`; sau đó truyền hai tên file trên cùng dòng cho `javac` (không dùng ký tự nối dòng `\` của shell Unix).

Lệnh này chỉ **bootstrap** annotation và processor. Class của processor nằm trong `verify-out/processor`; không đưa source của processor vào lệnh compilation của ứng dụng ở bước tiếp theo.

### 4.5. Một lần compilation có cả consumer và generated code

Trên macOS/Linux:

~~~bash
javac --release 17   -cp verify-out/processor   -processorpath verify-out/processor   -processor lab.GreetingProcessor   -s verify-out/generated   -d verify-out/classes   src/app/demo/GreeterSpec.java   src/app/demo/Demo.java
java -cp verify-out/classes demo.Demo
~~~

`-cp` giúp compiler thấy annotation `lab.GenerateGreeting`; `-processorpath` giúp tìm và tải processor; `-processor` yêu cầu chạy đúng processor; `-s` chỉ định chỗ đặt **source sinh ra**; `-d` chỉ định chỗ đặt **class files**. Dùng `--release 17` giúp phát hiện việc sinh mã gọi API không có trong nền tảng Java 17 khi build chạy trên JDK mới.

Một lệnh `javac` ở mục này đã kiểm tra **cả input được annotate và consumer tham chiếu class generated**, nhờ compiler xử lý các round. Sau khi thành công, có thể kiểm tra:

~~~text
verify-out/generated/lab/generated/HelloGenerated.java
verify-out/classes/lab/generated/HelloGenerated.class
verify-out/classes/demo/GreeterSpec.class
verify-out/classes/demo/Demo.class
~~~

Output chạy ứng dụng đúng là:

~~~text
Xin chào, Lan!
~~~

Lệnh `java` ở đây là **runtime smoke test bổ sung** sau phép biên dịch; phần xác minh giao diện API đã được `javac` thực hiện ngay trước đó. Nếu có lỗi compilation, đừng chạy ứng dụng và diễn giải class từ lần trước như kết quả mới.

## 5. Đảm bảo phép thử không bị “xanh giả”

Việc chạy thành công có giá trị chỉ khi môi trường được cô lập:

1. **Dùng output sạch:** xóa hoặc thay mới riêng thư mục `verify-out` của bài thử trước khi chạy. Đừng để `HelloGenerated.class` từ một lần build cũ nằm sẵn trên application classpath.
2. **Không đưa generated source cũ làm input tường minh:** `src/app/demo/Demo.java` import class generated, nhưng lệnh ứng dụng không liệt kê `verify-out/generated/lab/generated/HelloGenerated.java` như một file source có sẵn.
3. **Bắt buộc kích hoạt processor:** ví dụ dùng `-processor lab.GreetingProcessor`. Nếu processor không được tải, lệnh phải thất bại do consumer không tìm thấy `lab.generated.HelloGenerated`.
4. **Không thêm classpath “quá giàu”:** một JAR chứa bản cũ của `HelloGenerated` có thể khiến consumer compile dù lần hiện tại không sinh file.
5. **Xác nhận sự kiện sinh mã:** ngoài exit code `0`, kiểm tra đúng file mới trong `-s`, package, chữ ký API và class mới trong `-d`.
6. **Kiểm tra diagnostic đầy đủ:** không bỏ qua stderr của compiler, không coi kết quả thành công khi chỉ có generator chạy mà `javac` thất bại.
7. **Khóa release/toolchain:** dùng cùng target Java và dependency versions mà ứng dụng sẽ dùng; compiler mới hoặc classpath của môi trường phát triển có thể che lỗi tương thích ở production.

Một phép đối chứng hữu ích là chạy compilation ứng dụng với `-proc:none` trong **đầu ra sạch**. Vì processor bị tắt, `Demo.java` không tìm được `lab.generated.HelloGenerated` và lệnh phải lỗi. Nếu vẫn thành công, có thể đã vô tình đưa class/source generated cũ vào classpath hoặc sourcepath — cần sửa cô lập trước khi tin vào test.

Lưu ý: `-proc:none` chỉ là **negative control** nhằm chứng minh test thực sự cần generated code; không phải cấu hình của lần biên dịch chính.

## 6. Kiểm tra thay đổi phá hợp đồng API

Ví dụ generator thay method:

~~~java
// Minh họa thay đổi sai ở mã sinh; đây không phải file chạy riêng.
public static int greet(String name) {
    return 42;
}
~~~

Consumer ở mục 4 vẫn yêu cầu:

~~~java
String greeting = HelloGenerated.greet("Lan");
~~~

Một compilation sạch sẽ phát sinh lỗi kiểu **`int cannot be converted to String`** và exit code khác 0. Đây là phát hiện có ý nghĩa mà phép kiểm tra chỉ nhìn tên file không thể thực hiện.

Các thay đổi khác nên thử trên bộ test thực tế:

| Thay đổi generator | Consumer giúp phát hiện |
|---|---|
| Đổi `lab.generated` sang package khác | Import không resolve |
| Đổi `greet` thành `hello` | Method không tồn tại |
| Đổi `public` thành package-private | Không truy cập được từ package `demo` |
| Biến `static` thành instance method | Lời gọi static bị lỗi |
| Đổi `String` sang `int` | Kiểu gán không tương thích |
| Sinh source dùng API Java cao hơn release | Compilation với `--release 17` thất bại |
| Sinh sai generic bound hoặc checked exception | Compiler phát hiện tại consumer có ràng buộc tương ứng |

Dù vậy, compilation không chứng minh kết quả văn bản `Xin chào, Lan!` đúng logic nghiệp vụ. Đó là lý do ví dụ chạy `Demo.main` sau compilation; với sản phẩm thực tế cần unit/integration tests riêng cho hành vi.

## 7. Khi nào nên tách thành bài kiểm thử tự động?

Trong CI, nên chạy lại phép **consumer compilation** mỗi khi generator hoặc dependency của generator thay đổi. Có thể triển khai bằng một script build/test trong thư mục tạm, bằng `javax.tools.JavaCompiler` trong một test Java, hoặc bằng một module fixture chuyên dùng để compile nguồn ứng dụng. Dù chọn cách nào, thứ được kiểm tra phải là **task/lệnh compilation thật** với generated API, không chỉ kiểm tra file tồn tại.

Với dự án Gradle có module processor `:generator` và module ứng dụng `:consumer-fixture`, ý tưởng khai báo dependency là:

~~~groovy
// Trong build.gradle của :consumer-fixture (đoạn cấu hình minh họa)
dependencies {
    compileOnly project(":generator")       // Annotation API dùng lúc compile
    annotationProcessor project(":generator") // Processor thực thi
}
~~~

Đoạn trên minh họa vai trò của hai classpath, không phải một project đầy đủ. Module `:generator` phải cung cấp cả annotation và processor, và processor cần được đăng ký để Gradle phát hiện (chẳng hạn bằng service registration). Nếu annotation được tách thành module API riêng, `compileOnly` nên phụ thuộc module API; `annotationProcessor` phụ thuộc module processor và các dependency của nó. Source của `:consumer-fixture` phải có code **sử dụng generated API** để compile task phát hiện signature không tương thích.

Các tình huống cần đưa vào fixture khi generator phức tạp hơn:

- Consumer ở **package khác** để kiểm tra visibility và import.
- Consumer với **generic, overload, nested type, checked exception, annotation usage** thực tế.
- Fixture có nhiều input cùng loại để phát hiện **trùng tên file sinh** và processing rounds.
- Fixture biên dịch trên **release thấp nhất được hỗ trợ** và dependency classpath tối thiểu.
- Fixture sử dụng cả **generated source** và generated resource khi sản phẩm yêu cầu, nhưng phải nhớ compiler không kiểm chứng runtime resource semantics.

Đối với processor sinh source theo nhiều rounds, không cố thêm file generated vào source set bằng đường dẫn cứng ngay từ trước; để compiler/Gradle theo dõi đầu ra processor qua task chuẩn. Các generator chạy trước compilation (ví dụ OpenAPI codegen) có luồng khác: bước generate tạo source, sau đó **một lần consumer compile thật** trên nguồn ứng dụng cộng generated sources; cần nối task dependency và generated source directory đúng trong build tool.

## 8. Phân biệt lỗi generator và lỗi cấu hình build

Một smoke test thất bại có thể đến từ nhiều tầng:

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| `Annotation processor '...' not found` | `-processorpath` sai, processor chưa được build hoặc tên fully qualified sai |
| `package lab does not exist` | Thiếu annotation API trong compilation classpath |
| `package lab.generated does not exist` | Processor không kích hoạt, annotation không khớp, output chưa sinh hoặc class cũ đã bị loại |
| `cannot find symbol` tại lời gọi generated method | Generator sinh sai tên, số tham số, visibility hoặc signature |
| `FilerException: Attempt to recreate a file` | Generator tạo trùng file qua nhiều annotated elements/rounds |
| Build chỉ thành công khi bỏ `--release 17` | Generated code hoặc dependency đòi API/language level mới hơn |
| Test pass cục bộ, fail trên CI | Classpath, JDK/toolchain, filesystem case sensitivity, output cũ, task dependencies khác nhau |
| Test pass khi processor bị tắt | Thường có generated class/source cũ lọt vào đầu vào kiểm thử |

Hãy giữ lại diagnostics gốc từ compiler, nguồn generated trong thư mục thử nghiệm và thông tin classpath/toolchain. Thông báo `cannot find symbol` thường là **triệu chứng**; nguyên nhân gốc có thể là processor không chạy hoặc sinh sai API, không nhất thiết là thiếu dependency của ứng dụng.

## 9. Quy trình đánh giá một phép kiểm thử compilation đáng tin

- [ ] Test xác định input generator và một consumer Java dùng API generated thật.
- [ ] Mã processor được build trước; consumer chỉ cần **một invocation `javac`** để sinh rồi dùng generated class (đối với annotation processing).
- [ ] Compiler/toolchain, `--release` và các dependency khớp hợp đồng Java hỗ trợ.
- [ ] Source output và class output nằm trong thư mục mới, không lẫn generated artifacts từ lần trước.
- [ ] Processor được kích hoạt tường minh hoặc qua đăng ký đã kiểm tra; compilation thất bại nếu tắt generation.
- [ ] Consumer có lời gọi đủ đặc hiệu để bắt lỗi kiểu, package, visibility, method signature và generic cần thiết.
- [ ] Exit code, diagnostics, file generated và class output được kiểm tra; runtime smoke test được thêm khi cần kiểm tra hành vi.
- [ ] CI chạy phép kiểm tra khi generator/dependency thay đổi, và artifact lỗi không thể bị cache hoặc output cũ che giấu.

**Ghi nhớ:** kiểm thử mã sinh tốt nhất là đưa một **consumer đại diện** vào **quá trình biên dịch thật**. Sự tồn tại của file chứng minh generator đã ghi được văn bản; compilation thành công từ thư mục sạch chứng minh ít nhất một chương trình Java thực tế **có thể sử dụng hợp đồng API được sinh**.
