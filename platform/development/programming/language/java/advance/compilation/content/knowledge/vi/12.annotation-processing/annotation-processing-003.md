# Vòng xử lý, mã mới sinh và điều kiện kết thúc của annotation processing

Trong Java, **annotation processing** (JSR 269) cho phép một hoặc nhiều *annotation processor* quan sát khai báo nguồn, kiểm tra quy tắc và **tạo thêm tệp nguồn Java hoặc class file** trong lúc `javac` biên dịch. Điểm đặc biệt là quy trình **không chỉ chạy đúng một lần**: compiler tổ chức thành các **vòng xử lý (processing rounds)**. Mã được tạo trong vòng hiện tại có thể trở thành đầu vào của vòng tiếp theo, rồi compiler tiếp tục cho tới khi không còn mã nguồn/lớp mới cần đưa vào xử lý và thực hiện **vòng cuối**.

Hiểu vòng xử lý quan trọng để trả lời những câu hỏi thực tế:

- Vì sao processor sinh `GeneratedHello.java` rồi chương trình có thể tham chiếu lớp này trong **cùng một lần gọi `javac`**?
- Vì sao `process(...)` được gọi nhiều lần nhưng không được tạo cùng một file lặp đi lặp lại?
- `RoundEnvironment.processingOver()` và `errorRaised()` khác nhau ra sao?
- Khi nào processor được phép sinh mã, khi nào chỉ nên tổng kết kết quả?
- Vì sao đôi lúc annotation mới đã xuất hiện mà processor khác không xử lý nó?
- Những file generated cũ còn ở thư mục build có tự tạo thêm round mới không?

Bài dùng Java 17 và các API chuẩn `javax.annotation.processing`, `javax.lang.model`, `javax.tools`.

## 1. Nền tảng: một lượt compile có thể bao gồm nhiều vòng

`javac` ban đầu đọc các compilation units nguồn, nhận diện các annotation types có thể được processor hỗ trợ, rồi chọn processor phù hợp từ **processor path** hoặc theo cấu hình được chỉ định. Theo mô hình JSR 269, đầu vào ban đầu của lượt compile có thể được xem là kết quả của **vòng 0 ảo**. Vòng 0 chỉ là mô hình giải thích, không phải một lần gọi `process` thông thường.

Ví dụ một processor phát hiện `@GenerateHello` và tạo lớp `GeneratedHello`:

```text
Đầu vào ban đầu: Main.java (@GenerateHello)
           |
           v
  ROUND 1: xử lý Main
           |
           +-- Filer.createSourceFile("demo.GeneratedHello")
           +-- viết và đóng GeneratedHello.java
           |
           v
  ROUND 2: xử lý GeneratedHello.java vừa tạo
           |  (có thể không có @GenerateHello trong file mới)
           +-- không tạo thêm Java source/class file
           |
           v
  FINAL ROUND: processingOver() == true
           |   processors đã tham gia được gọi lần cuối
           +-- tổng kết / giải phóng trạng thái; không tạo mã
           |
           v
  javac hoàn tất kiểm tra/biên dịch và xuất .class
```

Đây là **dòng xử lý điển hình** của một ví dụ chỉ tạo một file ở vòng đầu; số vòng thực tế phụ thuộc các files được sinh ra, processors, cấu hình và lỗi.

Một file nguồn được tạo trong round hiện tại **không tự động trở thành root của chính round đó**. Khi writer hoặc stream do `Filer` cấp được **đóng**, file nguồn/class mới được công cụ biết đến để xét ở **round tiếp theo**. Nếu có nhiều processors cùng tham gia round hiện tại, đừng viết mã giả định processor thứ hai sẽ nhìn thấy lập tức một kiểu mà processor thứ nhất vừa mới tạo; cách ổn định là đợi compiler chuyển qua round sau.

### Processing round không phải một “lần chạy `javac` mới”

Toàn bộ các rounds thuộc **cùng một invocation của công cụ biên dịch**. Chúng chia sẻ môi trường compiler, processor instances đã khởi tạo và các cam kết của `Filer` trong invocation đó. Dùng nhiều rounds không đồng nghĩa với việc `javac` tự khởi chạy một process OS mới, cũng không đồng nghĩa với build tool bắt đầu một tác vụ build mới.

Trong các bản OpenJDK thông thường, sau khi xử lý annotation xong, compiler tiếp tục các pha phân tích và tạo bytecode. Đừng dựa vào một pha nội bộ chính xác để thiết kế hợp đồng processor: điều có thể dựa vào là **API ProcessingEnvironment/RoundEnvironment và quy tắc tệp được tạo ở các vòng**.

## 2. Các đối tượng API cốt lõi

| API | Vai trò |
| --- | --- |
| `Processor` / `AbstractProcessor` | Giao diện processor, có `init`, `process` và metadata về annotation/source version được hỗ trợ |
| `ProcessingEnvironment` | Cung cấp `Filer`, `Messager`, `Elements`, `Types`, compiler options và source version |
| `RoundEnvironment` | Thông tin **riêng một round**: root elements, annotated elements, `processingOver()` và `errorRaised()` |
| `Element` / `TypeElement` | Mô hình cấu trúc chương trình ở compile time: loại, phương thức, trường, package |
| `Filer` | Tạo source/class/resource outputs theo giao thức compiler |
| `Messager` | Báo `NOTE`, `WARNING`, `ERROR` kèm element/vị trí khi có |
| `SourceVersion` | Khai báo release Java được processor hỗ trợ |
| `JavaFileObject` | Đối tượng file nguồn/class được compiler cung cấp, có writer/output stream |

Một processor điển hình:

```java
@SupportedAnnotationTypes("demo.GenerateHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class HelloProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        // Phân tích các Element của round hiện tại.
        return true;
    }
}
```

Đoạn trên là **khung minh họa**, chưa phải tệp tự biên dịch: cần `package`, `imports` và phần thân phù hợp. Ví dụ hoàn chỉnh nằm ở mục 5.

Processor **không hoạt động như reflection runtime**: nó thường đọc cấu trúc source qua `Element` và `TypeMirror`, không nên dùng `Class.forName` để nạp chính các lớp ứng dụng đang được biên dịch. Những lớp đó có thể còn chưa có `.class` hoặc có thể đang lỗi.

## 3. Ý nghĩa chính xác của `RoundEnvironment`

### `getRootElements()`

`roundEnv.getRootElements()` trả các root elements được đưa vào **round hiện tại**. Round đầu thường thấy các top-level declarations trong những source files ban đầu; round tiếp theo có thể thấy các top-level declarations từ generated source/class files của round trước.

**Không** giả định root set của round sau chứa mọi source đã xử lý ở các rounds trước. Nếu cần tổng hợp toàn bộ kết quả, processor phải quản lý trạng thái hợp lệ giữa các lần gọi `process` hoặc tạo artifact ở vị trí thích hợp.

### `getElementsAnnotatedWith(...)`

`roundEnv.getElementsAnnotatedWith(GenerateHello.class)` trả các `Element` trong phạm vi round hiện tại được đánh dấu annotation liên quan, theo quy tắc của API. Tập này có thể **trống**, kể cả khi `process` vẫn được gọi: ví dụ round có file mới không chứa annotation mà processor đang hỗ trợ.

Không lấy việc annotation set rỗng làm tín hiệu chắc chắn “đây là vòng cuối”. **Tín hiệu kết thúc là `roundEnv.processingOver()`**.

### `processingOver()`

`roundEnv.processingOver()` trả `true` khi **những kiểu được tạo ở round này sẽ không được đưa vào một round annotation processing tiếp theo**. Đó là cờ quan trọng nhất để nhận diện **round cuối**.

Nên dùng mẫu sau:

```java
if (roundEnv.processingOver()) {
    // Ghi nhận kết quả cuối cùng, không sinh thêm source/class.
    return true;
}
```

Đoạn này là **mảnh trong `process`**, không phải file hoàn chỉnh. Vòng cuối cho processor một cơ hội hoàn tất kiểm tra/tổng hợp; **không phải một vòng “sinh thêm mã rồi compiler sẽ xử lý tiếp”**. Việc cố tạo source/class ở round cuối không mở ra round mới như mong đợi, và `javac` có thể cảnh báo rằng file được tạo ở round cuối sẽ không được xử lý.

### `errorRaised()`

`roundEnv.errorRaised()` trả **`true` nếu một lỗi đã được báo trong round trước**. Nó không có nghĩa “bất kỳ warning nào từng xuất hiện trong toàn bộ compile” và không phải bản sao của `processingOver()`.

Bảng phân biệt:

| Điều kiện | Diễn giải |
| --- | --- |
| `processingOver() == false` | Vẫn là round xử lý bình thường, có thể sinh thêm tệp theo quy tắc |
| `processingOver() == true` | Round cuối; không trông chờ một round kế tiếp xử lý file mới |
| `errorRaised() == true` | Đã có error được đưa ra ở round trước |
| `errorRaised() == false` | Không có error theo định nghĩa đó ở round trước; không chứng minh toàn bộ compile đã chắc chắn thành công |
| `getElementsAnnotatedWith(...)` rỗng | Không có element phù hợp ở phạm vi đang hỏi; **không đồng nghĩa final round** |

Khi processor gọi `processingEnv.getMessager().printMessage(Diagnostic.Kind.ERROR, ...)`, đó là **diagnostic error** làm compilation thất bại theo quy tắc công cụ. Processor không nên cố tiếp tục sinh đầu ra thành công khi đã biết dữ liệu nguồn không hợp lệ. Nếu `process` ném exception không được xử lý, công cụ có thể dừng những processors còn lại; nên báo lỗi qua `Messager` khi có thể.

## 4. Processor tồn tại qua các rounds như thế nào?

Theo `javax.annotation.processing.Processor`, công cụ tạo processor object, gọi `init(ProcessingEnvironment)` rồi lấy supported annotation types/options/source version và gọi `process(...)` khi phù hợp.

**Nếu processor đã được gọi ở một round, nó sẽ tiếp tục được gọi ở những rounds sau, kể cả round cuối**, ngay cả khi không còn annotation khớp. Không tạo processor object mới chỉ vì chuyển từ round 1 sang round 2.

Vì vậy có thể có field trạng thái instance như:

```java
private boolean generated;
```

Biến này hữu ích để tránh processor tự tạo **cùng một file** ở mọi round. Tuy nhiên, trạng thái đó chỉ thuộc **một invocation/compiler process cụ thể** và không phải bộ nhớ bền vững qua hai lần build độc lập. Nếu code tạo nhiều file, theo dõi bằng **tên file/type đã xử lý** hoặc mô hình idempotent phù hợp thay vì một boolean chung tùy tiện.

### `return true` và `return false` trong `process`

Giá trị trả về của `process(Set<? extends TypeElement> annotations, RoundEnvironment roundEnv)` biểu thị processor có **claim các annotation types được giao** hay không:

- `true`: processor claim tập annotation được yêu cầu; những processors chạy sau trong round không được yêu cầu tiếp tục xử lý chính tập đã claim theo cơ chế discovery.
- `false`: không claim; cho phép các processors khác tiếp tục được cân nhắc cho các annotation đó.

**Nó không có nghĩa** `true = tạo file thành công`, `false = tạo file thất bại`, và cũng không có nghĩa `return false` sẽ tự tạo round mới. **Chỉ sự xuất hiện của files mới được đăng ký/đóng đúng cách** cùng quy tắc vòng mới quyết định vòng xử lý tiếp theo.

Processor hỗ trợ tất cả annotations qua `"*"` mà luôn `return true` có thể chặn processors khác nhận những annotation cần thiết. Nếu bạn viết processor toàn cục chỉ làm validation/quan sát, thông thường nên **`return false`** để không chiếm mọi annotation types.

## 5. Ví dụ hoàn chỉnh Java 17: processor sinh lớp được chương trình dùng ngay

Ví dụ có ba tệp nguồn (annotation, processor, app), được build thành hai giai đoạn: **biên dịch processor trước**, sau đó **chạy processor trong lúc biên dịch app**. Không cần thư viện bên ngoài JDK.

### 5.1. Cây thư mục ban đầu

```text
project/
└── src/
    ├── demo/
    │   ├── GenerateHello.java
    │   └── Main.java
    └── processor/
        └── HelloProcessor.java
```

**Tệp `src/demo/GenerateHello.java`:**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateHello {
}
```

`@Retention(RetentionPolicy.SOURCE)` phù hợp cho annotation chỉ dùng khi xử lý nguồn. Không cần annotation tồn tại ở runtime để processor đọc được nó trong quá trình compile.

**Tệp `src/processor/HelloProcessor.java`:**

```java
package processor;

import demo.GenerateHello;
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
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.GenerateHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class HelloProcessor extends AbstractProcessor {
    private boolean generated;

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver() || generated) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateHello.class)) {
            try {
                JavaFileObject file = processingEnv.getFiler()
                        .createSourceFile("demo.GeneratedHello", element);
                try (Writer writer = file.openWriter()) {
                    writer.write(
                            "package demo;\n" +
                            "public final class GeneratedHello {\n" +
                            "  private GeneratedHello() {}\n" +
                            "  public static String message() {\n" +
                            "    return \"Hello from generated code\";\n" +
                            "  }\n" +
                            "}\n");
                }
                generated = true;
            } catch (IOException exception) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Cannot generate demo.GeneratedHello: "
                                + exception.getMessage(),
                        element);
            }
        }
        return true;
    }
}
```

Những điểm cần để ý trong processor:

1. `@SupportedAnnotationTypes("demo.GenerateHello")` khai báo chính xác annotation processor hiểu. Nếu không có annotation phù hợp ở lần đầu, công cụ có thể không gọi processor này.
2. `@SupportedSourceVersion(RELEASE_17)` công bố version của processor đối với source. Processor được compile bằng đúng một JDK hỗ trợ Java 17.
3. `roundEnv.processingOver()` được kiểm tra trước mọi thao tác sinh mã. Vòng cuối không tạo thêm type.
4. `generated` ngăn cố tạo `demo.GeneratedHello` lần hai trong cùng compilation. Ví dụ này sinh **một lớp duy nhất**; với nhiều nguồn đầu vào cần chính sách tên và tracking thích hợp.
5. `createSourceFile("demo.GeneratedHello", element)` dùng **tên kiểu đủ package**, không dùng đường dẫn file và không tự tính `src/` hay `build/generated/`. Tham số `element` là **originating element**, hữu ích cho các tool incremental.
6. `try (Writer writer = file.openWriter())` đảm bảo writer đóng, giúp compiler đăng ký file để xử lý trong round sau.
7. Lỗi I/O được chuyển thành `Diagnostic.Kind.ERROR`, thay vì silently ignore.
8. `return true` claim annotation đã xử lý, không kiểm soát số rounds.

**Tệp `src/demo/Main.java`:**

```java
package demo;

@GenerateHello
public final class Main {
    public static void main(String[] args) {
        System.out.println(GeneratedHello.message());
    }
}
```

Lưu ý: **`GeneratedHello` chưa có trong source tree ban đầu**. Chính compiler sẽ gọi processor sinh file này, rồi xét và biên dịch nó trước khi kết thúc invocation. Đây là mục đích minh họa vòng xử lý.

### 5.2. Bước một — biên dịch annotation và processor

Từ thư mục `project`, dùng JDK 17 trở lên có hỗ trợ `--release 17`:

```sh
javac --release 17 -encoding UTF-8 -proc:none -d build/processor src/demo/GenerateHello.java src/processor/HelloProcessor.java
```

Vì `-proc:none`, bước bootstrap này **chỉ biên dịch processor và annotation**, không chạy annotation processors trong cùng invocation. Output:

```text
build/
└── processor/
    ├── demo/GenerateHello.class
    └── processor/HelloProcessor.class
```

Compiler thành công thường không in thông báo. Đường dẫn tương đối `build/processor` được tính từ working directory hiện tại của lệnh.

### 5.3. Bước hai — chạy processor trong khi biên dịch `Main`

```sh
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor processor.HelloProcessor -s build/generated -d build/classes -XprintRounds -XprintProcessorInfo src/demo/Main.java
```

Giải thích từng phần:

| Tùy chọn | Tại sao cần |
| --- | --- |
| `-cp build/processor` | Cho `Main.java` nhìn thấy kiểu annotation `demo.GenerateHello` lúc compile |
| `-processorpath build/processor` | Để compiler **nạp processor** từ output bootstrap |
| `-processor processor.HelloProcessor` | Chọn processor **tường minh** theo tên đầy đủ, không cần service-discovery file |
| `-s build/generated` | Chọn thư mục lưu **generated source files** do `Filer.createSourceFile` |
| `-d build/classes` | Chọn thư mục lưu **class files** do compiler tạo |
| `-XprintRounds` | Hiển thị thông tin các rounds (diagnostics của `javac`) |
| `-XprintProcessorInfo` | Hiển thị processor nào xử lý annotation nào/được gọi trong round |

Đây là câu lệnh **cụ thể, độc lập với cơ chế tự khám phá processor mặc định**. Các JDK khác nhau có chính sách tự động chạy processor khác nhau; chỉ định `-processor` tường minh tránh phụ thuộc vào mặc định, đặc biệt khi dùng JDK mới.

Sau khi compile thành công, phần output chính liên quan đến ví dụ:

```text
build/
├── processor/
│   ├── demo/GenerateHello.class
│   └── processor/HelloProcessor.class
├── generated/
│   └── demo/GeneratedHello.java
└── classes/
    └── demo/
        ├── GeneratedHello.class
        └── Main.class
```

File `GeneratedHello.java` **được tạo bởi processor**; `GeneratedHello.class` được `javac` biên dịch từ file ấy trong cùng lần gọi ở bước hai. Thư mục `build/processor` chứa phần build-time classpath, không phải classpath runtime cần thiết của ứng dụng minh họa.

### 5.4. Bước ba — chạy ứng dụng

```sh
java -cp build/classes demo.Main
```

**Stdout chính xác:**

```text
Hello from generated code
```

Chương trình không dùng reflection hoặc tải class thủ công. `Main` gọi trực tiếp static method của class do processor sinh. JVM chỉ cần các class ở `build/classes` để chạy ví dụ này; retention `SOURCE` của `@GenerateHello` không yêu cầu annotation class tại runtime.

### 5.5. Bước bốn — quan sát số round

Tùy chọn `-XprintRounds` thường cho thấy ba rounds liên quan ví dụ:

| Round | Roots chủ yếu | Annotation phù hợp | `processingOver()` |
| --- | --- | --- | --- |
| 1 | `demo.Main` | `demo.GenerateHello` | `false` |
| 2 | `demo.GeneratedHello` | Không có `GenerateHello` trong lớp mới | `false` |
| 3 (final) | Tập root rỗng | Không có | `true` |

Đây là **bảng diễn giải hành vi dự kiến** chứ không khẳng định log có y hệt bảng, thứ tự dòng, cách viết dấu ngoặc hoặc mọi chi tiết trên mọi JDK. Với ví dụ này, chỉ có một file source mới sinh ở round 1; round 2 không có file mới; sau đó đến round final.

Đáng chú ý: `HelloProcessor` **vẫn được gọi ở round 2 và final** sau khi đã được gọi ở round 1, mặc dù `roundEnv.getElementsAnnotatedWith(GenerateHello.class)` rỗng ở các rounds ấy. Điều đó giải thích lý do phải phân nhánh theo `processingOver` và quản lý trạng thái generated.

## 6. Khi nào một file mới tạo ra round kế tiếp?

Không phải mọi thao tác ghi file trong processor đều có cùng hiệu ứng.

| API/hành vi | Tác động với annotation processing |
| --- | --- |
| `Filer.createSourceFile("demo.X")` và đóng writer | Source được **đăng ký** để xét xử lý ở round sau |
| `Filer.createClassFile("demo.X")` và đóng stream | Class file mới được công cụ xét trong round sau theo hợp đồng `Filer` |
| `Filer.createResource(...)` | Tạo resource phụ, **không** được đăng ký như source/class để tạo round annotation mới |
| Ghi file bằng `Files.write(...)` ngoài `Filer` | Compiler không được bảo đảm nhận diện hay đưa file vào một round mới |
| Chỉ viết diagnostics/console logs | Không tạo type mới; tự nó không tạo round |
| Mã cũ còn nằm trong `build/generated` từ lần build trước | Không tự là newly generated file của invocation này, trừ khi compiler/tool được cấu hình đọc nó hoặc processor tạo mới đúng cách |

Theo `Filer`, file mới được tạo trong một round sẽ được xét ở **subsequent round sau khi Writer/OutputStream đóng**. Tạo resource chỉ để lưu metadata thông thường **không** gây thêm round, ngay cả khi tên resource nhìn giống file `.java` hoặc `.class`.

Sự kiện **một file nguồn/lớp mới được tạo** quan trọng hơn việc đoạn code của processor có gọi `process`, `getElementsAnnotatedWith` hoặc `return false` hay không.

### Tại sao phải dùng `Filer` thay vì tự tạo file?

`Filer` quản lý logical output locations, tên type, chống xung đột, quan hệ originating elements và thông báo cho compiler biết file đã được tạo. Ghi file tùy ý qua `java.nio.file.Files` có thể làm compiler không biết source mới, khiến mã app tham chiếu `GeneratedHello` bị báo `cannot find symbol` dù đã có file trên đĩa.

Với output là **generated source**, dùng `Filer.createSourceFile`; nếu output là file phụ phục vụ annotation processor, dùng `createResource` với location thích hợp.

## 7. Điều kiện kết thúc: “không sinh thêm file” và final round

Trong mô hình thông thường:

1. Compiler bắt đầu với input được đưa vào xử lý và chạy processors phù hợp.
2. Nếu các processors tạo thêm **source/class files** thông qua `Filer`, files mới được xét ở **round tiếp theo** sau khi đóng luồng ghi.
3. Nếu lại có thêm source/class files, tiếp tục các rounds tương ứng.
4. Khi một round **không tạo thêm source/class file mới để xử lý**, compiler thực hiện một **final round**.
5. Ở final round, processors đã tham gia có thể tổng kết/kiểm tra nhưng không thể trông chờ files mới sinh được tiếp tục xử lý bằng round mới.
6. Sau annotation processing, nếu compilation không bị dừng và không dùng chế độ chỉ xử lý, compiler hoàn tất việc tạo class files cho những nguồn hợp lệ.

**Không dùng con số “round 3” làm dấu kết thúc chung.** Một processor tạo source A chứa annotation dẫn tới processor khác tạo source B, rồi B lại phát sinh source C sẽ có nhiều rounds hơn. Nếu logic tạo file liên tục và không có điều kiện chặn, build có thể chạy rất lâu hoặc kết thúc do lỗi; bản thân chương trình processor phải đảm bảo tiến trình sinh mã đạt **điểm cố định (fixed point)** hợp lý.

Tín hiệu kết thúc đáng tin cậy khi processor chạy là **`roundEnv.processingOver()`**, không phải “đã gọi `process` hai lần”, “annotations trống”, hay “log không còn gì mới”.

### Mẫu processor có xử lý cuối vòng

```java
@Override
public boolean process(
        Set<? extends TypeElement> annotations,
        RoundEnvironment roundEnv) {
    if (roundEnv.processingOver()) {
        // Tổng kết trạng thái thu thập được; không sinh source/class.
        return false;
    }
    // Duyệt elements của round hiện tại.
    return false;
}
```

Đây chỉ là **mảnh minh họa method** trong một `AbstractProcessor`, không phải source file hoàn chỉnh. `return false` ở đây là lựa chọn về **claim annotations**, không liên quan đến việc round có phải final hay không.

### Trường hợp có lỗi

Nếu processor hoặc compiler báo lỗi trong một round, `errorRaised()` có thể là `true` ở round kế tiếp; compiler có thể sớm kết thúc việc phát sinh rounds và chuyển sang vòng thông báo cuối tùy trạng thái lỗi. Processor phải ưu tiên **báo diagnostic chính xác**, không cố tiếp tục pipeline giả định build vẫn thành công.

Không dùng `processingOver() == true` như bằng chứng compilation **đã thành công**: một final round cũng có thể xảy ra sau khi đã có lỗi.

## 8. Lỗi `FilerException` và vấn đề tạo trùng file

Một nguyên tắc trọng yếu: **trong một invocation của annotation processing, cùng một pathname/type không được tạo bằng `Filer` nhiều lần**. Ví dụ processor cố chạy lại:

```java
processingEnv.getFiler().createSourceFile("demo.GeneratedHello");
```

ở round 2 cho cùng type đã tạo ở round 1 thì `Filer` thường ném **`FilerException`**. Theo API, cả source và class file cùng type name hoặc trùng các input types ban đầu cũng có thể bị từ chối.

### Phân biệt hai trường hợp

- **Tạo lại trong cùng invocation:** Có nguy cơ `FilerException` ngay cả khi gọi ở round khác. Cờ `generated` ở ví dụ mục 5 bảo vệ đúng trường hợp sinh một type.
- **File output còn từ invocation cũ:** `Filer` có thể quản lý/truncate output tại lần tạo đầu tiên của invocation mới theo quy tắc của nó; không được kết luận mọi file tồn tại trên đĩa đều tự động gây `FilerException`. Tuy nhiên, file cũ không còn khớp input có thể gây stale code nếu build tool không làm sạch/khai báo nguồn đúng cách.

**Không tự “sửa” `FilerException` bằng xóa file khi processor đang chạy.** Hãy sửa thuật toán naming, tránh tạo hai lần, dùng originating elements, và để build tool quản lý output. Nếu nhiều elements được annotate mà tất cả cố sinh cùng một tên `demo.GeneratedHello`, hãy định nghĩa cách tổng hợp **một lần** hoặc tạo tên duy nhất cho mỗi element.

### Lưu ý kiểu/đường dẫn

`createSourceFile` nhận tên kiểu đủ package theo Java, ví dụ `demo.GeneratedHello`, **không phải** `"build/generated/demo/GeneratedHello.java"`. Thư mục output đến từ `javac -s` hoặc cấu hình compiler; nó không phải một phần của tên kiểu. Sử dụng đường dẫn file sai có thể gây `FilerException` hoặc sinh mã sai package.

## 9. Chọn cách chạy và quan sát annotation processors

| Lựa chọn `javac` | Tác dụng |
| --- | --- |
| `-processor processor.HelloProcessor` | Chọn processor được chỉ định theo tên đủ package |
| `-processorpath path` / `--processor-path path` | Nơi tìm/nạp classes của processors và dependencies cần thiết |
| `-classpath path` / `-cp path` | Nơi source tìm classes/annotations phụ thuộc; không đồng nghĩa `-processorpath` |
| `-s dir` | Đích generated **source files** |
| `-d dir` | Đích generated/final **class files** |
| `-proc:only` | Chạy annotation processing **mà không biên dịch final application classes** |
| `-proc:none` | Không chạy annotation processing |
| `-XprintRounds` | Chẩn đoán các processing rounds |
| `-XprintProcessorInfo` | Chẩn đoán processor nào đang tham gia |
| `-Akey=value` | Cung cấp option tùy chỉnh cho processor hỗ trợ key |
| `--processor-module-path path` | Nơi tìm processors được đóng gói dạng modules theo cơ chế tương ứng |

### `-proc:only` để xem generated source

Nếu đã bootstrap processor ở bước 5.2, chạy:

```sh
javac --release 17 -encoding UTF-8 -cp build/processor -processorpath build/processor -processor processor.HelloProcessor -s build/generated-only -d build/classes-only -proc:only -XprintRounds src/demo/Main.java
```

Compiler chạy annotation processing và ghi generated source, nhưng **không tạo application class files** qua bước biên dịch thông thường. Đây là cách quan sát `GeneratedHello.java` trước khi quyết định biên dịch riêng hoặc chạy normal mode.

Không nên dựa vào `build/classes-only/demo/Main.class` được tạo bởi lệnh `-proc:only`, vì mục tiêu của chế độ này là **chỉ processing**. Tùy cấu hình, processor chủ động tạo class files bằng `Filer.createClassFile` có thể có output riêng; phải phân biệt với final application compilation.

### Khám phá processor qua service provider

Bên cạnh `-processor` tường minh, công cụ có thể khám phá processors theo service provider mechanism. JAR processor dạng classpath truyền thống thường có:

```text
META-INF/services/javax.annotation.processing.Processor
```

Nội dung ví dụ:

```text
processor.HelloProcessor
```

Hai dòng trên là **tên resource và nội dung file service**, không phải câu lệnh shell. Processor phải có constructor public không tham số và load được từ processor path. Với processor ở named module, cơ chế module descriptor/`provides` và `--processor-module-path` có quy tắc riêng.

Để **tránh phụ thuộc thay đổi mặc định qua JDK versions**, ví dụ chính sử dụng `-processor processor.HelloProcessor` tường minh. Nếu compile không gọi processor, kiểm tra `-proc:none` có đang bật, cấu hình processor path có đúng, compiler/tool có auto discovery không, và annotations được processor hỗ trợ có thực sự hiện diện.

## 10. Chạy nhiều processors: điều gì được và không được đảm bảo?

Giả sử:

- `ProcessorA` đọc `@Model`, sinh `model.GeneratedDescriptor`.
- `ProcessorB` đọc `@Descriptor`, sinh `consumer.GeneratedClient`.

Nếu `GeneratedDescriptor` có `@Descriptor`, thông thường `ProcessorB` sẽ thấy annotation mới ở **round tiếp theo** sau khi source của A đã được tạo/đóng. Không trông đợi B nhìn thấy một `Element` chưa tồn tại trong round hiện tại chỉ vì A vừa gọi `createSourceFile`.

Các nguyên tắc giúp processor tương thích hơn:

1. **Độc lập thứ tự:** Tránh dựa vào thứ tự processors do công cụ gọi trong một round, trừ khi đã có hợp đồng cụ thể của build system.
2. **Nhất quán:** Processing cùng input cho cùng output; không phụ thuộc ngẫu nhiên, thời gian hiện tại hoặc thứ tự không ổn định của các sets.
3. **Không trùng output:** Mỗi generated type có chủ sở hữu và naming rules rõ ràng.
4. **Không dựa vào processor khác sinh file ngay trong round:** Phụ thuộc mã sinh nên được giải quyết bằng round kế tiếp hoặc bằng contract thiết kế riêng.
5. **Xử lý empty annotations:** `annotations` hay `getElementsAnnotatedWith(...)` có thể rỗng dù `process` vẫn được gọi.
6. **Không giữ `Element` vô thời hạn:** Element/TypeMirror thuộc processing environment của invocation; việc cache references qua compiler invocations là không phù hợp.
7. **Claim đúng phạm vi:** `return true`/`false` ảnh hưởng processor discovery của annotation types, không tạo/dừng round.
8. **Điều kiện kết thúc:** Mã được sinh phải tiến tới trạng thái không còn cần tạo thêm types.

JSR 269 khuyến nghị các thuộc tính **orthogonality, consistency, commutativity, independence** để processors chạy cùng nhau mà không gây kết quả phụ thuộc thứ tự hoặc những side effects khó tái lập.

## 11. Incremental build và generated code không còn hợp lệ

Annotation processing rounds là hoạt động **trong một compilation invocation**; incremental build là chức năng của **build tool** theo dõi thay đổi giữa các invocations. Hai khái niệm có liên quan nhưng không đồng nghĩa.

Nếu một source `@GenerateHello` bị xóa, build tool phải biết `GeneratedHello.java/.class` còn cần hay phải loại khỏi artifact. Một processor không thể chỉ dựa vào `generated = true` (một field của object trong invocation hiện tại) để tự quản lý file đã tồn tại nhiều lần build.

Gợi ý thiết kế:

- Truyền `originatingElements` vào `Filer.createSourceFile` để build tool biết generated file đến từ element nào; đây là **hints**, không phải cam kết mọi tool đều thực thi incremental build giống nhau.
- Tránh đọc vô cớ tất cả file ngoài processing environment, tránh viết output ra thư mục tùy ý không do build tool quản lý.
- Định nghĩa naming và ordering ổn định, đặc biệt với aggregating processors tạo một file từ nhiều elements.
- Không sửa generated source bằng tay. Source of truth là annotation/source đầu vào cùng processor.
- Cấu hình thư mục generated source riêng, tránh trùng source tree con người sửa.
- Nếu nghi stale classes, dùng chức năng clean build của dự án để tái kiểm chứng — chỉ dọn **thư mục build output được sở hữu**.

Dùng hai loại kiểm thử: **clean build** để xác nhận thuật toán sinh mã đúng và **incremental rebuild** để kiểm tra file cũ được xử lý hợp lý. Kết quả round trong một invocation không bảo đảm incremental correctness.

## 12. Một số lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân phổ biến | Hướng kiểm tra |
| --- | --- | --- |
| `cannot find symbol: GeneratedHello` | Processor không chạy, không hỗ trợ annotation, không sinh/đóng file, hoặc generated source có lỗi | Kiểm tra `-processor`, `-processorpath`, `-s`, output và log `-XprintRounds` |
| `Annotation processor ... not found` | Processor class không nằm trên processor path hoặc sai tên/cấu hình | Biên dịch processor trước, dùng fully qualified class name |
| `Attempt to recreate a file for type ...` | Cùng type được tạo lại qua `Filer` | Ghi nhận tên types đã sinh, không tạo trùng qua các rounds |
| `processingOver()` đã true nhưng vẫn muốn sinh code | Thuật toán chưa hội tụ trước final round | Chỉ tổng kết ở final; sinh code từ các rounds trước |
| `getElementsAnnotatedWith(...)` rỗng ở round 2 | Type mới không có annotation processor hỗ trợ | Không đồng nhất tập rỗng với final round |
| Có generated `.java` nhưng không có `.class` | Dùng `-proc:only`, source sinh lỗi, hoặc compilation thất bại | Kiểm tra mode, diagnostics, class output `-d` |
| Thư mục `-s` trống | Processor chỉ kiểm tra mà không sinh source, hoặc sinh class/resource thay vì source | Kiểm tra `Filer` calls và loại output |
| Error ở round trước nhưng process vẫn được gọi lần cuối | Processor lifecycle có final callback | Dùng `errorRaised()` để biết round trước có error; không tạo output mới |
| Lúc clean build đúng, incremental build lỗi | Stale generated files, phụ thuộc processor chưa khai báo hoặc naming không ổn định | Kiểm tra originating elements, task inputs/outputs, clean/rebuild |
| Hai processors sinh cùng type | Tranh chấp quyền sở hữu output | Phân tách naming hoặc điều phối đúng lớp có trách nhiệm |
| Source mới được sinh ở round final không được xử lý | Final round không mở thêm round kế tiếp | Sinh type trước final; cuối vòng chỉ tổng kết |

### Quy trình điều tra theo thứ tự

1. **Xem command đúng:** `javac -version` và toàn bộ `-processor`/`-processorpath`/`-cp`/`-s`/`-d`/`-proc:...`.
2. **Xem input:** annotation type có đúng retention, package/name, target elements? Mã được annotate có nằm trong nguồn/compiler input không?
3. **Bật log rounds:** dùng `-XprintRounds` và `-XprintProcessorInfo` trong môi trường debug.
4. **Xác nhận file mới:** generated source có đúng package/type name không? Writer đã đóng? Output có nằm dưới `-s`?
5. **Nhận diện round tiếp theo:** source/class file mới sinh có xuất hiện như root không? Nếu không, kiểm tra có dùng `Filer` và đã đóng stream.
6. **Xem vòng cuối:** processor có nhánh `processingOver`, có tránh tạo output cuối không? Có error từ round trước không?
7. **Dùng diagnostics, không đoán:** `Messager` cho error/warning có vị trí tốt hơn việc chỉ `System.out.println`.
8. **Kiểm tra thành phẩm:** chạy chương trình được biên dịch bình thường, đừng nhầm compile success từ lần trước khi output cũ vẫn tồn tại.
9. **Kiểm thử thêm các processor phối hợp:** khởi tạo và claim annotations có ảnh hưởng lẫn nhau không?
10. **So sánh clean vs incremental build:** đảm bảo generated files không bị sót hoặc trùng.

## 13. Các hiểu nhầm cần tránh

**“Một annotation thì processor chỉ gọi `process` một lần.”** Sai. Nếu processor đã tham gia, có thể được gọi trong nhiều rounds, bao gồm final round.

**“`annotations.isEmpty()` nghĩa là đã xong.”** Sai. Processor có thể được gọi ở round có root type mới nhưng không có annotation phù hợp. Dùng `processingOver()`.

**“`return true` sẽ kết thúc annotation processing.”** Sai. Nó claim annotation types, không phải nút dừng vòng xử lý.

**“`Filer.createResource` sẽ làm source mới xuất hiện ở round sau nếu tên là `.java`.”** Sai. Resource không được đăng ký xử lý như một source file.

**“Tạo file xong không cần đóng Writer.”** Sai. API đăng ký files mới để xét ở round tiếp theo sau khi luồng ghi đóng; nên dùng try-with-resources.

**“Một file sinh ra ở round 1 được tất cả processors đọc ngay trong round 1.”** Sai. Nó được xét ở **subsequent round** theo quy tắc file creation.

**“Đã tới final round nghĩa là compile thành công.”** Sai. Compilation có thể thất bại do diagnostic errors hoặc lỗi từ source sinh ra; final callback không phải success callback.

**“Processor được tạo lại ở mỗi round nên field trạng thái không hữu dụng.”** Sai. Một processor object được dùng qua những rounds trong cùng invocation; state instance cần được quản lý cẩn thận.

**“`FilerException` luôn do file từ lần build trước.”** Sai. Cố tạo cùng pathname/type hai lần **trong cùng invocation** là nguyên nhân rõ ràng; quy tắc Filer đối với file output tồn tại sẵn khác với recreation trong một run.

**“Dùng `-s` tức là đã có `.class`.”** Sai. `-s` chỉ định generated source output; `-d` chỉ định class output, còn `-proc:only` không chạy final application compilation.

**“Điều kiện kết thúc là số vòng cố định.”** Sai. Round count phụ thuộc files mới mà các processors thực sự tạo và trạng thái lỗi; không hard-code round index để phát sinh mã.

## 14. Checklist thiết kế processor an toàn

- [ ] Đã khai báo chính xác `@SupportedAnnotationTypes` và `@SupportedSourceVersion`?
- [ ] Processor có constructor public không tham số và load được từ processor path/module path?
- [ ] Đã hiểu `getRootElements()` chỉ là roots của **round hiện tại**?
- [ ] Có phân biệt `processingOver()` với việc annotation set rỗng?
- [ ] Có xử lý/ghi nhận `errorRaised()` đúng ý nghĩa **lỗi ở round trước**?
- [ ] Mã được tạo bằng `Filer.createSourceFile`/`createClassFile` và writer/stream được đóng?
- [ ] Không tái tạo cùng source/class output nhiều lần trong một invocation?
- [ ] Không cố sinh mã mới ở final round?
- [ ] `return true`/`false` được chọn theo chính sách claim annotation, không dùng làm điều kiện dừng?
- [ ] Đầu ra `-s` và `-d` tách riêng, không trộn generated source với source người viết?
- [ ] Có thử `-XprintRounds`, `-XprintProcessorInfo` và `-proc:only` khi debug?
- [ ] Đã kiểm tra kết quả trên clean build và incremental rebuild khi dùng build tool?

**Ghi nhớ:** Annotation processing hoạt động theo nhiều rounds trong **cùng một compilation**. **Generated source/class files qua `Filer` sau khi đóng luồng ghi** là đầu vào cho round tiếp theo; khi không còn file cần xử lý, công cụ chạy **final round** với `processingOver() == true`. Processor phải sinh mã trước vòng cuối, tránh tạo trùng và coi `return true` chỉ là việc **claim annotations**, không phải “kết thúc build”.

## Tài liệu tham khảo chuẩn

- Java SE 17 `Processor` — vòng xử lý, vòng cuối, lifecycle và ý nghĩa `process`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html
- Java SE 17 `RoundEnvironment` — `processingOver()`, `errorRaised()`, roots và annotated elements: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html
- Java SE 17 `Filer` — generated source/class, writer close, resource files, và `FilerException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Filer.html
- Oracle JDK 17, *The javac Command* — annotation processing rounds, `-processor`, `-s`, `-d`, `-XprintRounds`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- JSR 269 — Pluggable Annotation Processing API: https://jcp.org/en/jsr/detail?id=269