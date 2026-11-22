# Phân biệt Reflection ở runtime với Annotation Processing lúc biên dịch

**Java Reflection** và **Annotation Processing** đều giúp một chương trình/công cụ làm việc với thông tin về kiểu và annotation. Nhưng chúng hoạt động ở **hai giai đoạn khác nhau**, có API, quyền truy cập và đầu ra khác nhau:

- **Reflection ở runtime:** chương trình đã được biên dịch và đang chạy; đọc metadata về `Class`, method, constructor, field hoặc annotation có thể nhìn thấy lúc chạy, rồi có thể tạo instance/gọi method theo quyền truy cập. API tiêu biểu: `Class<?>`, `java.lang.reflect.*`.
- **Annotation Processing lúc biên dịch:** bộ biên dịch chạy processor trên mô hình phần tử nguồn/kiểu (`Element`, `TypeMirror`), kiểm tra annotation và **sinh mã nguồn/tài nguyên hoặc phát chẩn đoán** trước khi ứng dụng chạy. API tiêu biểu: `javax.annotation.processing.*`, `javax.lang.model.*`, `Filer` và `Messager`.

Việc một annotation được dùng để xử lý ở compile time **không đồng nghĩa** ứng dụng có thể đọc annotation đó bằng Reflection; điều này còn tùy thuộc `@Retention`. Ngược lại, việc đọc một annotation có `RUNTIME` retention tại runtime không làm annotation processor tự chạy.

## 1. Đặt hai cơ chế lên cùng trục thời gian

~~~text
Tệp nguồn .java
     |
     v
javac / build
     |
     +-- Annotation processor (0..n rounds)
     |      +-- đọc Element, AnnotationMirror, TypeMirror
     |      +-- kiểm tra cấu trúc / ghi compiler diagnostics
     |      +-- Filer sinh .java hoặc tài nguyên
     |                |
     |                +-- javac tiếp tục xử lý nguồn mới ở vòng tiếp theo
     |
     v
Bytecode .class / JAR
     |
     v
JVM nạp lớp và thực thi ứng dụng
     |
     +-- Reflection lúc chạy
            +-- đọc metadata Class / Method / Field / Constructor
            +-- đọc annotation được giữ tới runtime
            +-- tạo instance / gọi method khi được phép
~~~

Annotation processor tạo mã theo những đầu vào sẵn có ở lúc compile, còn Reflection làm việc với kiểu/lớp đã nạp vào JVM. Không có nghĩa mọi processor chạy đúng một vòng: `javac` có thể tổ chức **nhiều processing rounds** khi những processor tạo thêm tệp nguồn mới. Runtime Reflection không phải một “processing round” khác của compiler.

Hai hoạt động có thể **bổ trợ**: annotation processor sinh mã giúp ứng dụng không cần quét hoặc phản chiếu nhiều ở runtime; hoặc processor sinh metadata để mã runtime tải và sử dụng sau này. Tuy nhiên, chúng không thể tự thay thế nhau trong mọi tình huống.

## 2. So sánh theo những câu hỏi thiết kế thực tế

| Tiêu chí | Reflection runtime | Annotation Processing compile time |
|---|---|---|
| Thời điểm | Sau khi class đã được nạp trong JVM | Trong lúc `javac`/công cụ build xử lý source |
| Đầu vào chủ yếu | `Class` và các reflection member trên kiểu đã có | `Element`/`TypeMirror`, annotation và compiler model |
| Thấy những gì | Metadata được giữ trong class file và API runtime cung cấp | Cấu trúc source/element được compiler cung cấp, kể cả annotation `SOURCE` |
| Phải nạp/chạy lớp ứng dụng? | Thường có `Class<?>`; một số thao tác Reflection có thể kích hoạt code | Không cần khởi tạo các instance ứng dụng để kiểm tra element |
| Khả năng gọi logic nghiệp vụ | Có thể thông qua `Constructor.newInstance`, `Method.invoke` | Không có ý nghĩa như “chạy instance của class đang biên dịch” |
| Sinh tệp dùng cho build | Không phải chức năng cốt lõi của Reflection | Có `Filer` sinh source/class/resource theo quy tắc compiler |
| Phát lỗi tại build | Không trực tiếp; lỗi thường chỉ xuất hiện khi chạy | Có `Messager` báo `ERROR`, cảnh báo, vị trí source |
| Dependency runtime | Phụ thuộc metadata/runtime API được sử dụng | Mã processor không nhất thiết nằm trong runtime artifact |
| Hạn chế chính | Access control/JPMS, tên/chữ ký động, chi phí runtime, retention | Chỉ biết thông tin compile-time; cấu hình processor và generated source cần đúng |
| Công dụng | Plugin loader, DI runtime, serializer, command dispatcher | Generator, type-safe adapters, validation API lúc biên dịch, metadata index |

**Một lựa chọn sai phổ biến:** dùng `Class.forName` và Reflection runtime để phát hiện cấu hình sai mà compiler đã có đủ thông tin để phát hiện. Nếu công cụ có thể kiểm tra hợp đồng theo source, annotation processing có thể đưa lỗi về build. Nhưng nếu phần mở rộng chỉ được chọn khi ứng dụng chạy (ví dụ class do plugin được đưa vào sau), processor tại compile time không thể đoán trước toàn bộ plugin runtime.

## 3. Annotation retention quyết định Reflection có nhìn thấy hay không

Annotation trong Java có `@Retention` từ `java.lang.annotation.RetentionPolicy`:

| Retention | Compiler/processor ở compile time | Class file sau compile | Reflection đọc qua `getAnnotation` |
|---|---|---|---|
| `SOURCE` | Có thể đọc trong processing round thích hợp | Thông thường không được ghi vào class file | **Không** |
| `CLASS` | Có thể đọc qua compiler model | Được giữ trong class file | **Không**, theo Reflection chuẩn |
| `RUNTIME` | Có thể đọc qua compiler model | Được giữ trong class file | **Có**, trên element phù hợp |

`RetentionPolicy.CLASS` là giá trị mặc định nếu annotation không khai báo `@Retention`. Điều này không có nghĩa `CLASS` sẽ tự hiện diện trong kết quả `Class.getAnnotation(...)`.

Một ví dụ annotation chỉ dùng lúc compile:

~~~java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface AutoGreeting {}
~~~

Một ví dụ annotation cần được tra cứu lúc chạy:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface RuntimeLabel {
    String value();
}
~~~

Hai đoạn trên chỉ là **mảnh minh họa**, bản đầy đủ với imports nằm ở mục 5. Việc chọn retention cần dựa trên nhu cầu:

- `SOURCE`: các quy tắc chỉ dành cho source-time processor; không tăng metadata annotation trên class file đã biên dịch.
- `CLASS`: metadata giữ trong class file để công cụ phân tích bytecode sử dụng; không phải API Reflection chuẩn.
- `RUNTIME`: mã đang chạy cần đọc `Class`/`Method`/`Field` annotations qua Reflection.

**Đừng tăng tất cả annotations lên `RUNTIME` chỉ vì một công cụ dùng annotation processing.** Processor có thể làm việc với annotation `SOURCE`, còn runtime không cần nhìn thấy nó.

`@Target` giới hạn nơi annotation được áp dụng (ví dụ `TYPE`, `METHOD`, `FIELD`); nó độc lập với `@Retention`. Một annotation có `RUNTIME` retention gắn vào method vẫn cần được đọc từ `Method` tương ứng, không nên suy luận rằng `SomeClass.class.getAnnotation(...)` sẽ tự quét toàn bộ method annotations.

## 4. API và mô hình làm việc khác nhau

### 4.1. Phía Reflection

Các lời gọi phổ biến:

~~~java
Class<?> type = Demo.class;
Method[] methods = type.getDeclaredMethods();
RuntimeLabel label = type.getAnnotation(RuntimeLabel.class);
~~~

Đây là **mảnh minh họa**, được giả định đặt trong chương trình có `Demo` và `RuntimeLabel` ở mục 5 cùng `import java.lang.reflect.Method;`.

`Class<?>` mô tả kiểu ở runtime. `getDeclaredMethods()` trả các method khai báo trực tiếp, không bảo đảm thứ tự và không bao gồm method kế thừa. `getAnnotation(RuntimeLabel.class)` tìm một annotation loại `RuntimeLabel` có thể được Reflection nhìn thấy trên đối tượng `Class`.

Nếu cần gọi hành vi:

~~~java
Constructor<?> constructor = type.getConstructor();
Object instance = constructor.newInstance();
Method method = type.getMethod("run");
method.invoke(instance);
~~~

Đây là **mảnh minh họa API**, không phải code chạy với `Demo` của mục 5 vì `Demo` không khai báo `run()`. Tìm được member **không bảo đảm** gọi được: quyền truy cập Java/JPMS, receiver và chữ ký tham số vẫn phải hợp lệ. `Method.invoke` có thể bọc exception do method đích ném bằng `InvocationTargetException`. `Class.forName(...)` có thể nạp và khởi tạo class khi dùng overload một tham số; thao tác Reflection runtime không phải luôn chỉ đọc metadata.

### 4.2. Phía annotation processor

Processor kiểu `AbstractProcessor` nhận:

~~~java
boolean process(
    Set<? extends TypeElement> annotations,
    RoundEnvironment roundEnv)
~~~

API điển hình:

- `RoundEnvironment.getElementsAnnotatedWith(...)`: tìm các element được chú thích trong round hiện tại.
- `Element`: đại diện declaration, ví dụ class/method/field; `TypeElement` đại diện declaration của một type.
- `TypeMirror`: mô tả type trong model compiler, không tương đương việc lấy `Class<?>` bằng runtime.
- `ProcessingEnvironment.getElementUtils()` và `getTypeUtils()`: tra cứu element/type và quan hệ kiểu.
- `Filer.createSourceFile(...)`: tạo tệp Java source output cho compiler xử lý.
- `Messager.printMessage(Diagnostic.Kind.ERROR, ...)`: phát chẩn đoán, có thể khiến build thất bại.
- `RoundEnvironment.processingOver()`: báo round cuối, khi không còn processing rounds bình thường để tạo thêm nguồn.

Processor có thể kiểm tra tên, modifier, kiểu, annotation và nguồn được compiler phân tích mà không cần tạo instance của class dưới kiểm tra. **Không sử dụng `Class.forName` để đọc những lớp source đang được compile như cách thay cho `Element`**: class đó có thể chưa tồn tại dưới dạng bytecode, hoặc bytecode cũ trên classpath có thể khiến kết quả sai.

## 5. Ví dụ Java 17: processor sinh mã, Reflection đọc annotation runtime

Ví dụ có **bốn tệp ở cùng một thư mục**, không khai báo package để việc thử nghiệm độc lập đơn giản. Trong mã sản phẩm nên dùng package rõ ràng và tên annotation đầy đủ cho `@SupportedAnnotationTypes`.

Mục tiêu:

1. `@AutoGreeting` có `SOURCE` retention. Processor nhìn thấy nó lúc compile và sinh ra `GreetingGenerated.java`.
2. `@RuntimeLabel("active")` có `RUNTIME` retention. Ứng dụng dùng Reflection để đọc chuỗi `active`.
3. Mã ứng dụng gọi `GreetingGenerated.message()` như **một Java method bình thường**, không cần `Method.invoke`. Điều này minh họa một lợi ích của code generation: phương thức được biết và kiểm tra kiểu từ lúc build.

### 5.1. Tệp `AutoGreeting.java`

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface AutoGreeting {}
~~~

### 5.2. Tệp `RuntimeLabel.java`

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface RuntimeLabel {
    String value();
}
~~~

### 5.3. Tệp `GreetingProcessor.java`

~~~java
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("AutoGreeting")
public class GreetingProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.RELEASE_17;
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment roundEnv) {
        if (generated || roundEnv.processingOver()
                || roundEnv.getElementsAnnotatedWith(AutoGreeting.class).isEmpty()) {
            return false;
        }

        generated = true;
        try {
            JavaFileObject file =
                    processingEnv.getFiler().createSourceFile("GreetingGenerated");
            try (Writer writer = file.openWriter()) {
                writer.write(
                        "public final class GreetingGenerated {\n"
                        + "  public static String message() {\n"
                        + "    return \"Generated at compile time\";\n"
                        + "  }\n"
                        + "}\n");
            }
        } catch (IOException e) {
            processingEnv.getMessager().printMessage(
                    Diagnostic.Kind.ERROR, "Cannot generate source: " + e);
        }
        return true;
    }
}
~~~

Chi tiết cần hiểu:

- `@SupportedAnnotationTypes("AutoGreeting")` thông báo processor xử lý loại annotation nào. Tên ở ví dụ là loại trong **unnamed package**; mã thực tế sử dụng qualified name, ví dụ `"com.example.AutoGreeting"`.
- `process(...)` được compiler gọi trong **processing rounds**. Trường `generated` ngăn việc cố sinh lại cùng tệp khi round tiếp theo diễn ra.
- `Filer.createSourceFile("GreetingGenerated")` khai báo một tệp Java mới dưới thư mục nguồn phát sinh do compiler quản lý. Tệp mới được compiler xem xét/biên dịch khi processing tiếp tục.
- `process(...)` trả `true` khi processor **claim** annotation type mà nó xử lý, ngăn các processor khác tiếp tục nhận annotation types đã claim trong cùng cơ chế dispatch; việc trả `true` không có nghĩa compiler ngừng mọi round.
- `Messager` phát diagnostic với mức `ERROR` khi tạo nguồn thất bại; compiler/build có thể ngừng với trạng thái lỗi.
- Processor là chương trình **đã được biên dịch và nạp cho compiler chạy**. Nó không chỉ là một annotation đặt vào source.

Đây là bản demo một lớp nguồn. Một generator thực tế cần xử lý tên đầu ra theo từng element, collision, incremental build, tính lặp lại, package naming và điều kiện có nhiều annotated types; tránh dùng một cờ chung rồi sinh đúng một file cho mọi type nếu chức năng cần một file/type.

### 5.4. Tệp `Demo.java`

~~~java
@AutoGreeting
@RuntimeLabel("active")
public class Demo {
    public static void main(String[] args) {
        RuntimeLabel runtime = Demo.class.getAnnotation(RuntimeLabel.class);
        AutoGreeting sourceOnly = Demo.class.getAnnotation(AutoGreeting.class);

        System.out.println("runtime label = " + runtime.value());
        System.out.println("SOURCE annotation visible = " + (sourceOnly != null));
        System.out.println("generated method = " + GreetingGenerated.message());
    }
}
~~~

Phần `Demo.class.getAnnotation(AutoGreeting.class)` **biên dịch hợp lệ** vì kiểu annotation `AutoGreeting` có trong classpath. Nhưng annotation này đã có `SOURCE` retention, nên metadata annotation đó không tồn tại trong classfile của `Demo` và kết quả Reflection là `null`. Ngược lại `RuntimeLabel` có `RUNTIME` retention nên `getAnnotation(...)` đọc được `"active"`.

### 5.5. Biên dịch và chạy từng bước

Chạy từ thư mục chứa cả bốn file. Các lệnh dưới đây hoạt động với `javac`/`java` Java 17+; dấu `\` cuối dòng chỉ là cách minh họa shell trong ví dụ nhiều dòng, vì vậy các lệnh thực thi được viết thành **một dòng mỗi lệnh**:

~~~bash
mkdir build
mkdir generated
javac --release 17 -encoding UTF-8 -d build AutoGreeting.java RuntimeLabel.java GreetingProcessor.java
javac --release 17 -encoding UTF-8 -cp build -processorpath build -processor GreetingProcessor -s generated -d build Demo.java
java -cp build Demo
~~~

**Lưu ý Windows:** Tạo thư mục bằng `mkdir` trong PowerShell hoặc CMD cũng được khi thư mục chưa tồn tại. Nếu dùng thử lại ở nơi đã có `build`/`generated`, hãy tạo một thư mục ví dụ mới hoặc xóa riêng output của bài demo để không dùng nhầm `GreetingGenerated.class` từ lần chạy cũ.

Diễn giải hai lệnh `javac`:

1. Lệnh thứ nhất biên dịch annotation types và processor. Compiler cần tìm lớp processor `GreetingProcessor` **đã được biên dịch** ở bước sau.
2. Lệnh thứ hai có `-cp build` để mã `Demo` tìm thấy các annotation và class cần thiết; `-processorpath build` để compiler nạp processor; `-processor GreetingProcessor` kích hoạt chính processor đã chỉ định; `-s generated` chọn nơi lưu **generated source**; `-d build` chọn nơi lưu **compiled classes**.
3. Processor nhận `@AutoGreeting` ở `Demo`, tạo source cho `GreetingGenerated` và compiler biên dịch class sinh ra. `Demo` gọi class này như một dependency bình thường đã được type-check.
4. Lệnh `java` cuối cùng mới chạy chương trình và gọi runtime Reflection.

**Stdout đã kiểm chứng với `javac --release 17`:**

~~~text
runtime label = active
SOURCE annotation visible = false
generated method = Generated at compile time
~~~

Sau biên dịch, bạn có thể thấy các file đầu ra tiêu biểu:

~~~text
build/
  AutoGreeting.class
  RuntimeLabel.class
  GreetingProcessor.class
  Demo.class
  GreetingGenerated.class
generated/
  GreetingGenerated.java
~~~

Đây là **cây file minh họa**, không hiển thị mọi metadata có thể có. Hai class `AutoGreeting` và `RuntimeLabel` có sẵn như các kiểu annotation, nhưng **annotation `@AutoGreeting` gắn trên `Demo`** không nằm trong bytecode `Demo.class` vì retention `SOURCE`. Đừng nhầm “class định nghĩa annotation được biên dịch” với “dấu annotation gắn trên element được giữ lại”.

**Một thử nghiệm có ý nghĩa:** Trong thư mục build sạch, bỏ `-processor GreetingProcessor` hoặc bỏ processor path trong lệnh biên dịch `Demo.java`; compiler có thể không tạo `GreetingGenerated`, và lời gọi tới lớp sinh ra sẽ dẫn tới lỗi không tìm được biểu tượng. Tạo build sạch trước thử nghiệm để tránh output cũ che đi vấn đề. Việc processor tự động được phát hiện còn phụ thuộc cấu hình phiên bản JDK/build tool và service registration; ví dụ này chỉ định `-processor` rõ ràng để không phụ thuộc cơ chế auto-discovery.

## 6. Vòng đời của annotation processor và giới hạn source-time

Một số khác biệt dễ bị bỏ qua:

**Nhiều rounds.** Một processor sinh ra tệp Java ở round trước có thể khiến compiler tạo thêm round để xử lý declarations mới. Không cố tạo cùng một tên tệp qua `Filer` trong nhiều round: việc đó có thể gây `FilerException`. Thiết kế generator nên gắn output với source element và xác định tên duy nhất.

**Không phải runtime classloader.** Compiler model `TypeElement` và `TypeMirror` không bắt buộc tương ứng với một `Class<?>` có thể nạp trong JVM đang chạy processor. Đừng gọi `newInstance` đối với class đang được compile để “thử nghiệm” annotation. Nếu cần kiểm tra method/field theo chữ ký, dùng model `Elements`/`Types` từ compiler.

**Không sửa source do người dùng viết.** Processor nên tạo **tệp mới** qua `Filer` hoặc phát lỗi/warning, không tự ghi đè source đang được compile. Với Java chuẩn JSR 269, processor không phải công cụ biến đổi cú pháp tùy ý của mọi class hoặc bytecode. Một số thư viện dùng compiler internals/AST rewriting, bytecode instrumentation hoặc compiler plugin riêng; không nên coi đó là chức năng mặc định của `AbstractProcessor`.

**Không đảm bảo mọi source đã có tại mọi round.** Processor cần tương thích chu kỳ rounds; nếu phụ thuộc vào output processor khác, phải quản lý thứ tự và availability thay vì giả định tất cả generated classes đã tồn tại ngay round đầu.

**Processor là build-time executable code.** Một dependency processor được compiler thực thi trong môi trường build; cần kiểm soát nguồn dependency, quyền truy cập file/network của môi trường build và tính reproducible như với build plugins. Annotation metadata đầu vào có thể không đáng tin; không coi processor là bộ lọc bảo mật hoàn hảo cho dữ liệu runtime.

## 7. Giới hạn của Reflection runtime

Reflection chỉ làm việc trong phạm vi các lớp/module mà runtime nhìn thấy và các thành viên mà API có thể truy cập. Nó không thể:

- Khôi phục annotation `SOURCE` đã bị bỏ khỏi classfile sau biên dịch.
- Thay compiler để phát lỗi cú pháp/kiểu trước khi chương trình được biên dịch.
- Mặc định truy cập được private members qua JPMS chỉ vì gọi `getDeclaredFields()`.
- Tự sinh `GreetingGenerated.java` trong processing rounds quá khứ. Có thể viết mã sinh nguồn lúc chạy nhưng đó là một quy trình khác, không phải annotation processing của lần build đã xong.
- Tự xác minh đầy đủ quy tắc nghiệp vụ chỉ bằng tên field/kiểu/annotation. Annotation runtime có thể mang metadata, nhưng validation cần một API/engine chủ động thực thi.

`setAccessible(true)` có thể bị từ chối khi package của module khác không được `opens` phù hợp; `IllegalAccessException` hoặc `InaccessibleObjectException` có thể xuất hiện trong từng đường gọi. Lập trình công cụ theo public API thường bền vững hơn việc dựa vào deep reflection.

**Về hiệu năng:** Reflection có chi phí tra cứu/dispatch và hạn chế compile-time type checking; annotation processor có thể sinh mã tường minh để giảm introspection runtime nhưng làm quy trình build phức tạp hơn. Không suy luận rằng generated code luôn nhanh hơn mọi Reflection path: đo workload thực tế, xem khả năng cache metadata và chi phí khởi tạo.

**Về triển khai:** Trong môi trường giới hạn dynamic class metadata, AOT/native image hoặc runtime có chính sách đóng gói đặc biệt, compile-time code generation có thể có lợi. Nhưng khả năng hỗ trợ cụ thể phụ thuộc runtime/toolchain và metadata configuration, không có quy tắc tuyệt đối cho mọi dự án Java.

## 8. Chọn công cụ theo yêu cầu

| Yêu cầu | Lựa chọn khởi đầu hợp lý | Vì sao |
|---|---|---|
| Phát lỗi annotation sai kiểu ngay khi build | Annotation processor | Có compiler model và `Messager.ERROR` |
| Sinh adapter/mapper cố định theo kiểu nguồn | Annotation processor | Mã sinh được compiler kiểm tra kiểu, có thể gọi trực tiếp |
| Tạo tài liệu/index từ annotation trong source | Annotation processor | Trích xuất metadata khi biên dịch, tạo resource |
| Tìm plugin mới xuất hiện khi app đã chạy | Reflection hoặc contract/plugin discovery runtime | Compiler không biết trước tất cả runtime types |
| Đọc annotation dùng để điều khiển xử lý lúc chạy | Reflection + `RUNTIME` retention | Annotation có mặt trong runtime metadata |
| Gọi method theo tên lấy từ cấu hình lúc chạy | Reflection hoặc phương án dispatch runtime được kiểm soát | Tên quyết định sau compile |
| Giảm startup scan khi danh sách type có thể xác định trước | Compile-time index/code generation | Đưa phần khám phá về lúc build |
| Cần contract dùng chung cho plugin có cấu trúc cố định | Interface/factory/`ServiceLoader` trước khi chọn Reflection sâu | Rõ API, giữ kiểm tra kiểu và quyền truy cập |

**Lựa chọn thứ ba thường tốt hơn:** Nếu bạn đã biết interface hoặc service contract, dùng Java bình thường, interface, factory hay `ServiceLoader` có thể đơn giản hơn cả một hệ thống generator hoặc dynamic invocation phức tạp. Không cần áp dụng annotation processing khi việc kiểm tra đã được ngôn ngữ/type system đảm bảo.

Một framework thực tế có thể chọn **hybrid**:

1. Annotation processor sinh registry/adapters cho những type thấy tại build.
2. Registry runtime khởi tạo đối tượng qua constructor/factory và gọi method có kiểu tĩnh.
3. Reflection chỉ xử lý những type động ngoài danh sách build-time nếu use case thật sự yêu cầu.
4. Cả hai đường đều phải kiểm tra module access, hợp đồng API, validate dữ liệu và xử lý lỗi.

## 9. Lỗi thường gặp và cách kiểm chứng

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| `getAnnotation(MyAnnotation.class)` trả `null` | Annotation `SOURCE`/`CLASS`, sai element, annotation không xuất hiện | Kiểm tra `@Retention`/`@Target` và element được hỏi |
| Processor không chạy | Thiếu `-processor`, không đăng ký service, sai processor path, build tool không cấu hình | Biên dịch sạch, kiểm tra `-processorpath` và processor discovery |
| `cannot find symbol GreetingGenerated` | Generated source không được tạo/biên dịch, hoặc classpath sai | Kiểm tra thư mục `-s`, `-d` và compiler diagnostics |
| `FilerException: Attempt to recreate a file` | Sinh cùng tên nhiều lần trong các rounds hoặc processor khác nhau | Quản lý output names và theo dõi generated elements |
| Runtime ném `ClassNotFoundException` | Class không nằm trong classpath/module path được loader thấy | Kiểm tra packaging và class loader runtime |
| Runtime ném `InaccessibleObjectException` | Deep reflection bị JPMS chặn | Thiết kế qua public API hoặc chính sách `opens` được cấp có chủ đích |
| “Annotation đọc được” nhưng logic không chạy | Reflection chỉ đọc metadata, không tự thực thi handler/validator | Gọi đúng engine hoặc explicit invocation |
| Generated class hiện ra dù đã tắt processor | Class file từ build trước | Tạo output build sạch để kiểm chứng |

### Tự luyện tập

1. Đổi `@Retention(RetentionPolicy.SOURCE)` của `AutoGreeting` thành `CLASS`, rồi thành `RUNTIME`. Trước mỗi lần chạy hãy biên dịch lại sạch; so sánh `Demo.class.getAnnotation(AutoGreeting.class)`.
2. Bỏ `@RuntimeLabel("active")` trên `Demo` và xác nhận `getAnnotation(RuntimeLabel.class)` trả `null`. Hãy sửa chương trình kiểm tra `null` trước khi gọi `value()`; giải thích NPE nếu không kiểm tra.
3. Bỏ `-processor GreetingProcessor` trong lần compile thứ hai trên build sạch. Compiler báo lỗi gì và vì sao?
4. Sửa processor sinh một method trả chuỗi khác rồi build lại. Cần rebuild bước nào trước khi output runtime thay đổi?
5. Sửa `@SupportedAnnotationTypes("AutoGreeting")` sang một tên không khớp. Điều gì xảy ra với class `GreetingGenerated`? Vì sao?
6. Thiết kế annotation `@MinLength(3)` cho method parameter hoặc field: nêu trường hợp nên kiểm tra ở compile time, trường hợp bắt buộc kiểm tra dữ liệu ở runtime. Đừng coi annotation tự tạo ra validation.
7. Khi một plugin được tải từ một JAR mới sau khi ứng dụng đã build, chọn Reflection, code generation hay interface/`ServiceLoader`. Giải thích dữ kiện nào không có ở compile time.
8. Với ứng dụng dùng JPMS, vì sao việc processor đọc source model thành công không chứng minh được runtime có thể gọi private constructor của type đó?

**Ghi nhớ:** Annotation processing là **công việc của compiler** với source/type model để kiểm tra và sinh mã; Reflection là **công việc của JVM ở runtime** với class/member metadata và quyền truy cập. `RetentionPolicy.SOURCE` dành cho compile-time processing; `RetentionPolicy.RUNTIME` cho phép Reflection đọc annotation tương ứng. Chọn cơ chế theo **thời điểm bạn có đủ thông tin**, kiểu kết quả cần tạo, yêu cầu kiểm tra và chi phí duy trì hệ thống.

### Tài liệu Java 17 chính thức

- [Annotation Processing: `AbstractProcessor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html)
- [`RoundEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html)
- [`Filer` sinh source và resources](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html)
- [`RetentionPolicy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html)
- [`Class.getAnnotation` / `AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html)
- [`javac` options gồm `-processor` và `-processorpath`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
