# Đối chiếu bytecode, phiên bản thư viện và mã nguồn khi trace không khớp

## 1. Vấn đề: stack trace trỏ tới một dòng không giống mã đang mở

Một exception Java có thể ghi:

~~~text
java.lang.IllegalStateException: failed to create invoice
    at com.example.billing.InvoiceService.create(InvoiceService.java:87)
    at com.example.billing.InvoiceController.submit(InvoiceController.java:32)
~~~

Đây là **trace minh họa**, không phải output từ chương trình chạy ở phần thực hành. Bạn mở `InvoiceService.java` trong IDE nhưng dòng 87 chỉ là comment, một lời gọi khác, hoặc thậm chí file hiện tại chỉ còn 75 dòng. Có nhiều nguyên nhân có thể xảy ra:

- JVM đang chạy **class file biên dịch từ phiên bản mã cũ**.
- Class đã được nạp từ **một JAR khác** với JAR bạn tưởng.
- Có nhiều bản của cùng một dependency, và **runtime chọn một bản khác** bản dùng để compile.
- Build sinh/biến đổi bytecode, shading, obfuscation hoặc instrument class.
- Thông tin `SourceFile` / `LineNumberTable` trong class thiếu, cũ hoặc không còn ánh xạ trực quan về source đang mở.
- Exception ngoài cùng chỉ là **wrapper**, còn dòng ném lỗi thực sự nằm trong `Caused by`.
- Đoạn thực thi thuộc lambda, bridge method, proxy hoặc class được sinh động; file và method trong trace không có ánh xạ một-một đơn giản sang một dòng Java nguồn hiện tại.

**Không sửa code theo số dòng đang hiển thị trong IDE nếu chưa xác minh artifact thực sự chạy.** Stack trace phản ánh thông tin mà runtime lấy từ bytecode/đối tượng exception và metadata của class đã được nạp; nó không tự cập nhật theo checkout Git hiện tại.

Mục tiêu của bài:

1. Hiểu vì sao bytecode chứa hoặc không chứa metadata dòng nguồn.
2. Dùng `javap` đối chiếu `LineNumberTable` với stack trace.
3. Xác định đúng bản class/JAR, class loader, module và dependency runtime.
4. Phân biệt lỗi source-line mismatch với lỗi version/binary compatibility.
5. Xử lý các tình huống khó: fat JAR, multi-release JAR, shading, obfuscation, generated code và async.
6. Tạo quy trình chẩn đoán có thể kiểm chứng bằng build ID, artifact và test tái hiện.

## 2. Ba lớp thông tin cần luôn tách biệt

Một lần điều tra thường liên quan đến ba lớp:

| Lớp | Chứa những gì? | Câu hỏi quan trọng |
| --- | --- | --- |
| **Source** | File `.java`, commit Git, generated sources, các dòng trong IDE | Đây có phải đúng source đã dùng để tạo class đang chạy? |
| **Artifact/bytecode** | File `.class`, JAR, WAR, executable JAR, image, module; constant pool, bytecode, debug attributes | Class file nào đã được compile, đóng gói và phân phối? |
| **Runtime** | JVM, class loaders, module path/classpath, container, JDK và dependency thực tế | JVM đã nạp bản class nào khi exception xảy ra? |

Ví dụ:

~~~text
Git commit A         -> javac -> Service.class (line 87)
                             -> app-old.jar
                             -> production JVM

Git commit B         -> IDE hiển thị Service.java (line 87 đã thay)
~~~

Nếu runtime vẫn chạy `app-old.jar`, việc IDE mở commit B không làm thay đổi số dòng trong stack trace từ production. Đổi nhánh Git hoặc recompile ở máy cá nhân cũng không chứng minh server đã dùng class mới.

**Mối liên hệ đúng** phải đi từ log → định danh deployment/runtime → class file thực sự được nạp → source/build tương ứng, không đi ngược từ “source mới nhất” rồi ép trace vào.

## 3. JVM dùng thông tin nào để hiển thị dòng nguồn?

Một class file có các cấu trúc/thuộc tính liên quan:

- **`SourceFile` attribute:** tên file nguồn được compiler ghi lại, thường là `Service.java`, không phải đường dẫn tuyệt đối tới repository.
- **`Code` attribute:** bytecode thực thi của từng phương thức cụ thể.
- **`LineNumberTable`:** ánh xạ từ **chỉ số bắt đầu của bytecode instruction (`start_pc`)** tới **số dòng source**. Nhiều instruction có thể cùng thuộc một dòng; một dòng source có thể có nhiều vị trí bytecode.
- **`LocalVariableTable`:** thông tin một số biến cục bộ (khi được xuất) để hỗ trợ debug; không phải thành phần bắt buộc để stack trace hiển thị file:line.
- Metadata của class/method, descriptors, constant pool và flags, giúp biết phương thức mà JVM thực thi dù source không còn ở máy.

Stack trace có thể hiện:

~~~text
at com.example.app.PriceService.compute(PriceService.java:114)
~~~

Nghĩa là runtime có thể quy chiếu frame đó tới `PriceService.java` dòng 114 theo thông tin gắn với class được nạp. Nó **không cam kết** rằng toàn bộ phép toán trong dòng 114 là nguyên nhân gốc, cũng không cam kết source bản checkout hiện tại là file đã biên dịch.

Đặc biệt, trong một biểu thức phức tạp hoặc nhiều instruction tương ứng cùng một dòng, stack trace thường chỉ định vị được **dòng**, không tự xác định chính xác subexpression nào gây exception.

### 3.1. `File.java:line` không phải đường dẫn tuyệt đối

`StackTraceElement.getFileName()` thường trả tên file như `OrderService.java`, không phải `src/main/java/com/example/OrderService.java`. Cần kết hợp tên class đầy đủ, package, module và artifact để biết file nào thực sự liên quan.

Class `Outer$Inner` thường đến từ file `Outer.java`; lambda có thể xuất hiện là `lambda$process$0` trong frame của một class. Không suy ra tên source bằng cách thêm `.java` vào tên synthetic class.

### 3.2. `Unknown Source` và số dòng âm

Nếu class thiếu `SourceFile` hoặc `LineNumberTable`, frame có thể hiện `Unknown Source` hoặc chỉ có tên file mà không có số dòng. Trong API `StackTraceElement`, `getFileName()` có thể là `null` và `getLineNumber()` có thể trả số âm.

Một số class không lưu stack trace có thể do constructor tùy biến, thông tin debug bị strip, obfuscator/bytecode transformer hoặc các cơ chế tối ưu/runtime đặc thù. **Không đoán số dòng** khi metadata không có; xác minh class đã nạp và tạo lại một bản build có debug info khi phù hợp.

## 4. Ví dụ runnable Java 17: số dòng lấy từ class file, không từ IDE

Dưới đây là chương trình độc lập minh họa stack trace có source-line metadata. Lưu thành **`BytecodeTraceDemo.java`** với dòng đầu tiên đúng là dòng khai báo class (không chèn dòng trống ở đầu) nếu muốn output số dòng khớp mẫu.

~~~java
public class BytecodeTraceDemo {
    static void verify(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative value: " + value);
        }
    }

    static void service() {
        verify(-3);
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (IllegalArgumentException error) {
            System.out.println(error.getClass().getSimpleName() + ": " + error.getMessage());
            for (StackTraceElement element : error.getStackTrace()) {
                if (element.getClassName().equals(BytecodeTraceDemo.class.getName())) {
                    System.out.println(element.getMethodName() + " -> "
                            + element.getFileName() + ":" + element.getLineNumber());
                }
            }
        }
    }
}
~~~

Từ thư mục chứa source với JDK 17+:

~~~bash
javac --release 17 BytecodeTraceDemo.java
java BytecodeTraceDemo
~~~

Stdout đã kiểm chứng với `javac` mặc định lưu thông tin số dòng:

~~~text
IllegalArgumentException: negative value: -3
verify -> BytecodeTraceDemo.java:4
service -> BytecodeTraceDemo.java:9
main -> BytecodeTraceDemo.java:14
~~~

Đối chiếu trực tiếp với source:

- `verify`, dòng **4**: tạo/ném `IllegalArgumentException`.
- `service`, dòng **9**: gọi `verify(-3)`.
- `main`, dòng **14**: gọi `service()` bên trong `try`.

Trong trường hợp này, trace cho đường đi từ nơi exception phát sinh về các caller cùng class. Nếu thêm comment trước dòng 4 **và biên dịch lại**, số dòng mới sẽ phản ánh source mới. Nhưng nếu chỉnh source và **không biên dịch lại class đang chạy**, output từ bytecode cũ vẫn là `4`, `9`, `14`: đó là một ví dụ tối giản của tình huống source và artifact lệch nhau.

### 4.1. Thí nghiệm tắt metadata debug

Biên dịch lại cùng file bằng:

~~~bash
javac --release 17 -g:none BytecodeTraceDemo.java
java BytecodeTraceDemo
~~~

Stdout đã kiểm chứng:

~~~text
IllegalArgumentException: negative value: -3
verify -> null:-1
service -> null:-1
main -> null:-1
~~~

Tên class/method vẫn được JVM biết, nhưng tên file và số dòng đã mất trong thí nghiệm vì bytecode không còn debug attributes tương ứng. **`-g:none` không loại bỏ logic ném exception**; nó chỉ làm giảm khả năng đối chiếu trace với source.

Để quay về bản có thông tin line/source, biên dịch lại, ví dụ:

~~~bash
javac --release 17 -g:lines,source BytecodeTraceDemo.java
java BytecodeTraceDemo
~~~

Số dòng trả về như ví dụ mặc định với file nguồn đã cho.

Lưu ý: ghi đè `BytecodeTraceDemo.class` bằng bản mới sau mỗi lệnh compile; nếu muốn so sánh hai artifact đồng thời, hãy compile chúng vào **hai thư mục build khác nhau** bằng `-d` và chỉ rõ classpath tương ứng. Đó cũng là cách nên làm khi điều tra hai phiên bản thực tế.

## 5. Đọc bytecode và LineNumberTable bằng `javap`

`javap` là công cụ disassembler/inspector đi kèm JDK. Các tùy chọn hữu ích:

| Lệnh/tùy chọn | Mục đích |
| --- | --- |
| `javap -c -l ClassName` | In bytecode và bảng line/local-variable khi có |
| `javap -c -l -p ClassName` | Bao gồm phương thức private/package-private |
| `javap -v ClassName` | In thông tin class file chi tiết hơn: version, constant pool, attributes |
| `javap -classpath path/to/app.jar -c -l -p package.Class` | Kiểm tra class cụ thể từ một JAR |
| `javap -c -l -p path/to/Foo.class` | Kiểm tra trực tiếp một class file theo đường dẫn thích hợp |

Với ví dụ `BytecodeTraceDemo` sau khi biên dịch bản có metadata:

~~~bash
javap -c -l -p BytecodeTraceDemo
~~~

Các đoạn `LineNumberTable` liên quan của output chứa những ánh xạ như:

~~~text
static void verify(int);
    ...
    LineNumberTable:
      line 2: 0
      line 3: 0
      line 4: 4
      ...

static void service();
    ...
    LineNumberTable:
      line 8: 0
      line 9: 0
      ...

public static void main(java.lang.String[]);
    ...
    LineNumberTable:
      line 12: 0
      line 14: 0
      ...
~~~

Đây là **các trích đoạn minh họa được giản lược**, không phải toàn bộ output `javap`; các bytecode offset ngoài phần đã kiểm chứng có thể thay đổi theo compiler/options. Với test Java 17 ở trên, các ánh xạ `line 4: 4`, `line 9: 0`, `line 14: 0` đã được đối chiếu thực tế.

**Ý nghĩa của `line 4: 4`:** instruction tại bytecode offset 4 được gắn với source line 4. Đây không phải “dòng 4 ứng với bytecode dòng 4” hoặc địa chỉ bộ nhớ máy. Nếu có nhiều instruction thuộc line 4, bảng thường chỉ ghi vị trí bắt đầu cần cho ánh xạ.

Ở một số bản JDK, `javap -l` **mà không kèm `-c`** có thể chỉ in warning không xuất bảng line number như kỳ vọng; dùng `javap -c -l` hoặc `javap -v` để xem dữ liệu đầy đủ. Không lấy việc chạy một lệnh sai options rồi không thấy bảng làm bằng chứng class thiếu metadata.

### 5.1. Đối chiếu bytecode với source theo trình tự

1. Lấy **class file thực tế** từ artifact của môi trường lỗi.
2. Dùng `javap -c -l -p` với đúng classpath hoặc đường dẫn class file.
3. Tìm tên phương thức trong frame, kể cả descriptor/overload nếu có nhiều phương thức trùng tên.
4. Xem `LineNumberTable` cho method đó; xác nhận line được stack trace nhắc tới có trong metadata hay không.
5. Mở source của **build đã tạo class này**, tới đúng dòng; xem toàn bộ expression và các call sites gần đó.
6. Nếu source lệch nhưng LineNumberTable khớp trace, nhiều khả năng bạn đang mở sai source revision hoặc class bị sinh/biến đổi sau bước biên dịch.
7. Nếu LineNumberTable trong artifact lấy được không khớp trace, rất có thể bạn đã lấy **sai artifact/classloader/JAR**, hoặc runtime có bytecode instrumentation/transformation; quay lại bước xác minh class được nạp.

Trường hợp source line 100 chứa nhiều lời gọi, hãy đọc bytecode/operand stack hoặc chia biểu thức thành các bước có tên trong một test tái hiện để biết null/exception đến từ đâu. Không chỉnh code dựa duy nhất vào offset hay line table.

### 5.2. `-g`, `--release` và phiên bản runtime là các khái niệm khác nhau

- `-g:lines,source` yêu cầu compiler ghi thông tin nguồn/số dòng.
- `-g:none` tắt thông tin debug do `javac` xuất.
- `--release 17` yêu cầu compile nhắm tới API và bytecode theo Java 17; nó **không khóa phiên bản dependency bên thứ ba**, không bảo đảm deployment đã dùng đúng jar, và không bảo đảm release hiện tại của ứng dụng chính là bản bạn đang xem.
- `java -version` chỉ nói JDK/JRE tại nơi thực thi **lệnh đó**; muốn chẩn đoán server thật, cần xác minh runtime của chính tiến trình/server.
- Class file có `major version` theo Java target, nhưng version đó không mã hóa Git commit hay Maven artifact version.

Một chương trình có thể được biên dịch với `--release 17`, chạy trên JDK 21, dùng thư viện Java-compatible version mới, và vẫn có stack trace line do class đã biên dịch bằng source cũ. Những yếu tố này độc lập.

## 6. Tìm đúng JAR/class mà JVM đã nạp

Trước khi so source, hãy trả lời: **class đang bị lỗi đến từ đâu?** Trong một ứng dụng lớn có thể có nhiều class loaders, nested JAR, module path, plugin hoặc cùng tên class trong nhiều version.

### 6.1. Kiểm tra CodeSource bằng API

Đoạn Java sau là **fragment**, giả định `InvoiceService` là class ứng dụng có thể tham chiếu từ nơi chạy:

~~~java
Class<?> type = InvoiceService.class;
var domain = type.getProtectionDomain();
var codeSource = domain == null ? null : domain.getCodeSource();
System.out.println(codeSource == null
        ? "unknown"
        : codeSource.getLocation());
~~~

Nếu `CodeSource` tồn tại, URL trả về có thể chỉ ra thư mục classes hoặc JAR chứa class. Nhưng:
- `getCodeSource()` có thể `null`.
- Với JDK modules, custom loader, nested/fat jar hoặc class sinh động, vị trí hiển thị có thể không phản ánh một file JAR “thường” có thể mở trực tiếp.
- `CodeSource` không phải một proof đầy đủ về git commit/source revision.
- Đường dẫn server và thông tin triển khai không nên được log ra nơi công khai.

Đọc `getClassLoader()` và `getModule()` cũng có thể giúp phân biệt nơi lớp được nạp. Một số JDK classes có classloader `null` (bootstrap), không phải lỗi.

### 6.2. Log class loading của JVM

Với JVM hỗ trợ unified logging của Java 9+, có thể bật logging nạp class trong môi trường chẩn đoán:

~~~bash
java -Xlog:class+load=info -cp path/to/app.jar com.example.Main
~~~

Đây là lệnh **tham khảo**: `path/to/app.jar` và `com.example.Main` là placeholder đường dẫn/tên class, cần thay bằng artifact thật; với ứng dụng chạy bằng `java -jar`, module path hoặc app server, cách khởi động khác. Log nạp class có thể cho biết class được nạp từ nguồn nào.

Cần cân nhắc log volume và thông tin nhạy cảm, không tự bật debug dày đặc trên production lâu dài. Logging class load cho runtime bạn khởi chạy **không tự chứng minh** runtime khác trên production dùng cùng bộ class, trừ khi cấu hình/artifact đã được xác nhận.

### 6.3. Kiểm tra trong JAR

Ví dụ lệnh tham khảo:

~~~bash
jar tf path/to/library.jar
javap -classpath path/to/library.jar -c -l -p com.example.lib.Parser
~~~

`jar tf` liệt kê các entry được đóng gói. `javap` đọc class theo classpath bạn chỉ định. Đừng nhầm việc `javap` tìm thấy một class trong JAR với việc runtime chắc chắn **đã nạp đúng class đó**: class loader và thứ tự phân giải thực tế mới quyết định.

Một JAR có thể chứa tên `com/example/lib/Parser.class` giống JAR khác. Nếu có hai bản, kiểm tra artifact identity, checksums, vị trí classloader và kết quả load thực tế trước khi kết luận.

## 7. Phân biệt compile-time dependency và runtime dependency

Một lỗi phổ biến là IDE hoặc build compile dựa trên thư viện **v2**, nhưng runtime chạy cùng tên library **v1**.

Ví dụ tình huống giả định:

~~~text
Compile:
    app.class -> lib-api 2.0, có method parse(String, int)

Runtime:
    app.class -> lib-api 1.4, chỉ có parse(String)

Khi lời gọi được resolve:
    java.lang.NoSuchMethodError
~~~

Lỗi `NoSuchMethodError` thường là dấu hiệu **binary linking/runtime compatibility mismatch**, không phải checked exception do xử lý input thông thường. Frame ứng dụng tại dòng gọi có thể hoàn toàn đúng nếu nhìn source v2, nhưng JVM không tìm thấy method với tên/descriptor tương ứng ở class runtime.

Các lỗi cần phân biệt:

| Triệu chứng | Giải thích thường gặp | Kiểm tra |
| --- | --- | --- |
| `NoSuchMethodError` | Runtime type không có phương thức với descriptor mà bytecode gọi | `javap -p -s` trên bản class/runtime dependency; kiểm tra version |
| `NoSuchFieldError` | Field kỳ vọng ở compile không tồn tại ở runtime | Kiểm tra field descriptor và phiên bản dependency |
| `IncompatibleClassChangeError` | Class/interface/static/instance hoặc cấu trúc binary không tương thích | Kiểm tra thay đổi API và class file thực được nạp |
| `AbstractMethodError` | Runtime dispatch không tìm implementation phù hợp | Kiểm tra ABI của interface/implementation và mix versions |
| `ClassNotFoundException` | Cố tải class theo tên nhưng loader không tìm thấy | Classpath/module path, plugin loading, artifact layout |
| `NoClassDefFoundError` | Class cần khi linking/initialization không thể định nghĩa/sử dụng; cũng có thể liên quan lỗi init trước đó | Xem cause, lỗi init ban đầu, classloader và dependency |
| `UnsupportedClassVersionError` | Class file được biên dịch cho version JVM cao hơn runtime hỗ trợ (hoặc không được hỗ trợ) | `java -version` của tiến trình và `javap -verbose` của class |
| `ExceptionInInitializerError` | Static initializer ném exception | Xem `<clinit>`, cause và trạng thái class initialization |

Các lỗi liên kết nhiều trường hợp là `LinkageError`/`Error`, không nên “sửa” bằng `catch (Exception)` rồi trả fallback. Việc catch rộng có thể che nguyên nhân và khiến hệ thống tiếp tục trong trạng thái sai. **Giải quyết artifact/dependency compatibility là hướng chính**.

### 7.1. Method descriptor có quan trọng hơn tên method không?

Có. Bytecode tham chiếu method cùng **tên, lớp/interface và descriptor** (tham số/trả về). Hai bản thư viện cùng có phương thức tên `parse` nhưng descriptor khác vẫn có thể gây `NoSuchMethodError`.

Dùng:

~~~bash
javap -classpath path/to/library.jar -p -s com.example.lib.Parser
~~~

`-s` hiển thị internal type signatures (descriptors) bên cạnh signatures, hữu ích khi có overload, generic erasure, thay đổi kiểu primitive/reference hoặc return type. `javap -c -v` trên class gọi giúp nhìn constant pool và instruction invoke target khi cần.

Generic source có thể trông tương tự do type erasure, nhưng bridge methods và descriptor thực tế vẫn ảnh hưởng linking. Vì thế đừng kết luận “method tồn tại mà JVM báo NoSuchMethodError thì JVM sai” chỉ bằng cách tìm chữ `parse` trong IDE.

## 8. Truy vết dependency qua Maven/Gradle

Trong project Maven, các lệnh hay dùng:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dverbose
~~~

Đây là **lệnh tham khảo cho project Maven có plugin phù hợp**; chi tiết các tùy chọn phụ thuộc phiên bản `maven-dependency-plugin`. Hãy kiểm tra dependency tree ở cấu hình đúng module/profile, xét dependency mediation, scope, exclusion và parent/BOM management. Một cây compile-time hiển thị đúng **không đủ** để chứng minh app server không tự cung cấp thêm một JAR runtime.

Trong project Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency group:name --configuration runtimeClasspath
~~~

Đây là **lệnh tham khảo**; thay `group:name` bằng dependency thật. Trên Windows, wrapper thường là `gradlew.bat`. Lệnh `dependencyInsight` giúp xem tại sao version được chọn, conflict resolution và dependency chain trong configuration được kiểm tra. Tên configuration thực tế thay đổi theo plugin và loại project; chọn configuration tương ứng artifact runtime cần điều tra.

### 8.1. Vì sao dependency tree vẫn chưa đủ?

Bởi vì runtime có thể:
- Có dependency **provided** do application server cung cấp.
- Được đóng gói bằng fat/uber JAR khác với classpath của IDE.
- Có plugin và child classloader nạp bản khác.
- Đã bị container image cache hoặc deploy nhầm bản.
- Có class trùng trong nhiều JAR; classpath/module resolution chọn một lớp không như mong đợi.
- Dùng shaded/relocated class với namespace thay đổi.
- Đang chạy nhiều instance/version song song sau rollout.

Do đó kết hợp **dependency tree + contents of released artifact + runtime class loading evidence**. Không dùng một nguồn riêng lẻ để kết luận.

### 8.2. Cần so dependency trong đúng môi trường

Một build chạy với profile `prod` có thể khác profile `dev`; Gradle runtimeClasspath khác testRuntimeClasspath; IDE có thể thêm thư viện từ workspace mà JAR production không chứa. Bước kiểm chứng phải ghi nhận:
- Lệnh build/profile/environment thực tế.
- Lockfile/BOM/versions catalog hoặc resolved dependency versions.
- Build artifact hash và container image digest.
- Cách đóng gói và cách process được khởi động.
- JDK/runtime architecture/version thích hợp.
- Classloader hierarchy khi dùng plugin/app server.

Không suy rằng việc `mvn test` pass trên máy cá nhân chứng minh production đã chạy đúng những class đó.

## 9. Classpath, module path và class loader quyết định class nào được chọn

### 9.1. Classpath và duplicate class

Trên **class path truyền thống** (unnamed module), nếu nhiều JAR chứa cùng FQCN và có thể được một loader phân giải, thứ tự classpath và quy tắc loader có thể quyết định bản được dùng. Nhưng Java class loading thực tế còn chịu ảnh hưởng của **parent delegation**, custom class loaders và runtime embedding. Không viết luật đơn giản “JAR đầu tiên trong tất cả tình huống thắng” cho mọi deployment.

Ví dụ cấu trúc trên Linux/macOS:

~~~bash
java -cp "lib/legacy.jar:lib/new.jar:app/classes" com.example.Main
~~~

Trong Windows, dấu phân cách classpath thường là `;` thay vì `:`. Đây là ví dụ lệnh giả định; không chạy nguyên trạng nếu không có những artifact được liệt kê.

Với plugin loaders, application servers hoặc hot reload, cùng tên class có thể được nạp bởi **hai classloader khác nhau**, dẫn tới hai class runtime khác nhau ngay cả khi tên hiển thị giống nhau. Đặc biệt, lỗi `ClassCastException` kiểu “`com.example.Widget cannot be cast to com.example.Widget`” có thể liên quan classloader identity khác nhau.

### 9.2. Named modules

Trên module path, Java Platform Module System có cơ chế giải quyết module và đọc/exports rõ ràng. Cùng tên package/class trong nhiều module có thể gây vấn đề resolution/access theo quy tắc JPMS, khác với classpath phẳng. Khi stack trace có tiền tố như `my.module/com.example.Service`, dùng nó như manh mối module chứa frame. Không chỉ cắt bỏ prefix rồi đoán thư viện.

Một số công cụ hữu ích có thể là `java --list-modules`, `jar --describe-module --file path/to.jar` hoặc xem `module-info.class`. Các lệnh này chỉ có ý nghĩa khi áp dụng đúng module/artifact đang chạy.

### 9.3. Java launcher `-jar` và `-cp`

Khi chạy `java -jar executable.jar`, launcher dùng cơ chế classpath theo JAR manifest hoặc launcher riêng; chỉ nối thêm `-cp` bên ngoài không chắc có hiệu quả như chạy main class bằng `-cp`. Với Spring Boot executable JAR hoặc framework có nested-JAR class loader, runtime còn có logic nạp class riêng.

**Không đổi tùy ý `java -jar` thành `java -cp` chỉ để debug** rồi coi đó là cùng môi trường: bạn có thể vô tình thay đổi classpath và che mất chính lỗi cần điều tra. Hãy ghi nhận command line thực và tái hiện theo packaging gốc.

## 10. Hash, build ID và xác minh artifact

Khi trace không khớp source, cách đáng tin là lập một “chuỗi bằng chứng”:

~~~text
Log/trace + thời gian lỗi
          |
          v
Deployment ID / pod / instance / build ID
          |
          v
Binary artifact hoặc container image chính xác
          |
          v
JAR/class file được classloader nạp
          |
          v
Source commit + build config + generated sources tương ứng
          |
          v
So stack frame và LineNumberTable
~~~

Ở tầng artifact, có thể dùng checksum SHA-256 để nhận dạng một file JAR. Ví dụ lệnh trên PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath "C:\deploy\app.jar"
~~~

Lệnh trên là **mẫu thao tác**, đường dẫn mang tính minh họa. Trên hệ Unix có thể dùng `sha256sum app.jar`. Checksum giúp đối chiếu file **có cùng bytes hay không**; nó không tự chứng minh đây là source commit nào nếu tổ chức không lưu quan hệ build provenance.

Một artifact reproducible build có thể hỗ trợ truy vết source, nhưng không nên giả định mọi project sinh byte-identical JAR khi build lại: timestamps, tool versions, thứ tự đóng gói, generated code và metadata có thể tạo khác biệt. Nếu không thể tái tạo hash, cần đọc build manifest, CI release record, commit ID và kiểm tra class file cụ thể.

### 10.1. Nên lưu gì trong build metadata?

Các thuộc tính có giá trị chẩn đoán:
- Git commit SHA và trạng thái dirty/clean khi build.
- Build number, pipeline/job ID, thời điểm và môi trường build.
- Version ứng dụng và phiên bản JDK compiler.
- Artifact checksum và image digest.
- Resolved dependency versions hoặc lockfile.
- Tên module/component và thông tin generated source khi có.

Đừng chỉ ghi version dạng `1.0-SNAPSHOT` vào tất cả image rồi mong phân biệt hai bản deploy. Với release quan trọng, liên kết **build ID → immutable artifact → commit** là nền tảng để đối chiếu trace.

## 11. Shading, relocation và obfuscation: tên class có thể không còn như source

Khi Maven Shade/Gradle Shadow hoặc một công cụ bytecode transform **relocate** package, trace có thể hiển thị tên đã đổi. Ví dụ trong source dependency là `com.vendor.json.Parser`, nhưng runtime có thể chứa `com.myapp.shaded.vendor.json.Parser`. Mở file theo package mới trong repo có thể không có kết quả, vì class đến từ dependency đã được chuyển namespace lúc build.

Các câu hỏi cần kiểm tra:
- Có cấu hình shade/relocate không?
- Package/class được đổi từ đâu sang đâu?
- Source JAR tương ứng với version dependency nào?
- Debug metadata được giữ hay thay đổi qua transformation?
- Stack trace xảy ra trước hay sau instrumentation của agent?

Nếu dùng obfuscator, tên method/class có thể bị rút ngắn thành `a.b.c`; số dòng có thể bị xóa hoặc thay đổi. Một số hệ sinh thái có **mapping file** để giải mã; cần đúng mapping **của build đang deploy**. Mapping từ release khác có thể tạo kết quả giả đáng tin nhưng hoàn toàn sai.

**Đừng xem tên method obfuscated là tên method Java gốc.** Nếu ứng dụng có quy trình deobfuscation, áp dụng đúng file mapping và xác minh kết quả bằng class/JAR tương ứng.

### 11.1. Bytecode instrumentation

Monitoring agents, AOP, runtime weaving hoặc coverage tools có thể thêm wrapper và thay đổi đường gọi. Tùy công cụ, bytecode được instrument nhưng line numbers gốc được giữ một phần, hoặc có thể xuất hiện frame do công cụ sinh ra. Trace từ runtime instrumented có thể khác chương trình chạy cùng source khi **không** có agent.

Khi tái hiện bug, ghi nhận:
- Java agents ở lệnh khởi động.
- Build-time weaving/annotation processing.
- Proxy generators / Byte Buddy / CGLIB / aspect configurations.
- Runtime khác biệt về phiên bản instrumentation.

Không tắt agent rồi tuyên bố lỗi biến mất do code đã sửa nếu nguyên nhân có thể nằm ở instrumentation hoặc khác biệt timing.

## 12. Multi-release JAR: cùng tên class nhưng nhiều phiên bản bytecode

Một **multi-release JAR** có thể chứa class ở đường dẫn gốc và các phiên bản chuyên biệt:

~~~text
META-INF/MANIFEST.MF
com/example/Codec.class
META-INF/versions/9/com/example/Codec.class
META-INF/versions/17/com/example/Codec.class
~~~

Đây là cấu trúc minh họa; JAR phải được cấu hình multi-release đúng chuẩn, không phải mọi JAR có thư mục `META-INF/versions` đều được xử lý như một multi-release JAR.

Khi chạy trên runtime tương thích, JVM có thể chọn class versioned phù hợp với phiên bản runtime. Điều đó nghĩa là:
- Source của phiên bản gốc có thể khác implementation versioned.
- `javap` không được cấu hình version đúng có thể đọc bản class khác runtime.
- Cùng một JAR nhưng chạy trên Java 11 và Java 17 có thể dùng bytecode khác.

Có thể kiểm tra entries:

~~~bash
jar tf path/to/library.jar
~~~

Với JDK có hỗ trợ tùy chọn multi-release, có thể dùng công cụ như:

~~~bash
javap --multi-release 17 -classpath path/to/library.jar -c -l -p com.example.Codec
~~~

Lệnh mang tính **tham khảo**; cần xác minh JAR thật và phiên bản Java/toolchain đang dùng. Mục tiêu là kiểm tra đúng class bản Java 17 thay vì mặc định trỏ vào entry gốc.

### 12.1. Không nhầm target Java với entry Java-specific

Class ở `META-INF/versions/17` không có nghĩa source hiện tại đang compile bằng `--release 17` ở mọi module. Nó nói có một alternate implementation trong JAR cho runtime phù hợp. Hãy kiểm tra manifest `Multi-Release: true` và đường load thật. Nếu stack trace khớp class versioned nhưng IDE mở source base implementation, dòng và logic có thể khác xa.

## 13. Generated sources, annotation processors và code generation

Framework và tool build có thể tạo:
- Java source trong `target/generated-sources`, `build/generated` hoặc một generated directory tương đương;
- class bytecode trực tiếp không có file `.java` tương ứng;
- implementation cho interface, mapper, serializer, proxy;
- lambda/synthetic/bridge methods.

Nếu frame chỉ tới `com.example.generated.MapperImpl.map(MapperImpl.java:...)`:
1. Kiểm tra class đó có phải generated class không.
2. Tìm generated source **được sinh trong chính build production**.
3. Xác nhận processor/plugin version và cấu hình.
4. Mở file generated nếu có, không chỉ mở interface `Mapper` nguồn.
5. Xem caller đưa input gì vào generated code.
6. Nếu file generated được tạo lại từ source mới, số dòng có thể lệch; không dùng nó để suy ra line number production.

Với bytecode được sinh trực tiếp, không chắc có source để mở. Khi đó `javap -c -l -v`, bytecode inspection và cấu hình generator là các công cụ chính.

### 13.1. Lambda và bridge methods

Trace có thể chứa `lambda$process$0` hoặc bridge method do compiler sinh. Khi tìm trong IDE, tìm **method bao lambda** và source line được ghi trong `LineNumberTable`; không cố tìm một file tên `lambda$process$0.java`.

Generics có thể tạo bridge methods để duy trì polymorphism sau type erasure. Method có thể tồn tại trong bytecode nhưng không được viết tường minh ở source. Dùng `javap -v -p` để nhận diện flags như `ACC_BRIDGE`/`ACC_SYNTHETIC` và đọc method thực mà nó gọi khi cần.

## 14. JDK/JRE version và stack trace formatting

JDK version ảnh hưởng:
- Các method/frames bên trong thư viện chuẩn.
- Cách xử lý class file version.
- Cơ chế module/class loading.
- Helpful NullPointerException messages trong trường hợp được hỗ trợ.
- Tối ưu JIT và hành vi stack capture trong một số tình huống đặc biệt.

Không hardcode một số dòng từ JDK internals như `java.util.Objects.java:123` làm chân lý cho mọi version. Cùng phương thức JDK có thể ở dòng khác giữa các release/update.

### 14.1. Những thứ JIT tối ưu không làm bạn phải bỏ qua

JIT có thể inline hoặc tối ưu nhiều lời gọi, nhưng không vì vậy mà mọi line number sai đều do JIT. JVM cố giữ ngữ nghĩa exception/stack trace theo cách hỗ trợ chẩn đoán, trong khi có những tối ưu và tình huống đặc biệt có thể làm trace khác điều mong đợi. Chẳng hạn một số JVM có tối ưu cho exception ném lặp lại rất nhiều lần khiến stack trace bị lược bớt trong điều kiện cụ thể.

Nếu một trace lặp lại dưới tải rất cao bị thiếu frame, cần cân nhắc:
- Bytecode có line number table không?
- Throwable có bật stack trace không?
- Logger có truncate exception không?
- Có JVM flag/tối ưu gây thay đổi thông tin stack không?
- Exception bị tạo một lần rồi ném lại nhiều lần không?

**Chỉ suy luận về JIT sau khi đã loại trừ những nguyên nhân phổ biến** như sai artifact, sai source revision hoặc thiếu debug info.

## 15. Root cause nằm trong `Caused by`, không nhất thiết ở trace ngoài

Ví dụ:

~~~text
java.util.concurrent.CompletionException: task failed
    at java.base/java.util.concurrent.CompletableFuture...
    at com.example.app.ApiHandler.handle(ApiHandler.java:61)
Caused by: java.lang.NoSuchMethodError: ...
    at com.example.app.Adapter.callLibrary(Adapter.java:42)
    ...
~~~

Đây là trace **minh họa với dấu rút gọn**, không phải stack thật. Exception ngoài cùng đến từ cách future/callback truyền lỗi; cause là `NoSuchMethodError`, gợi ý runtime dependency ABI mismatch.

Điều tra đúng:
1. Xem cả exception ngoài cùng và cause, không chỉ frame có tên `CompletableFuture`.
2. Ở `Adapter.callLibrary:42`, xác định lời gọi method mà bytecode đang thực hiện.
3. Dùng `javap -c -v` trên **class Adapter đã deploy** để biết target method descriptor.
4. Dùng `javap -p -s` trên **library class được runtime nạp** để xem method đó có tồn tại không.
5. So dependency versions và runtime class loader.
6. Xác nhận artifact/build IDs và sửa packaging/dependency resolution thay vì chỉ thay `catch`.

Nếu cause là `IOException` hoặc exception nghiệp vụ thông thường, quy trình sẽ khác: cần kiểm tra input/state, không tự áp lý thuyết ABI mismatch cho mọi failure.

### 15.1. `... N more` và suppressed traces

`Throwable.printStackTrace()` có thể rút gọn các frame trùng giữa exception ngoài và cause thành `... N more`. Nó không có nghĩa class file thiếu đúng N dòng. `Suppressed` thường là lỗi cleanup trong try-with-resources; phần đó có stack riêng. Một logger cũng có thể cắt ngắn trace do cấu hình; cần phân biệt **nén frame trùng của Java** với **log truncation**.

Nếu log đã bị cắt mất cause hoặc suppressed, hãy bổ sung telemetry an toàn và thu lại tại lần tái hiện phù hợp. Không bịa một cause chỉ vì có một dòng trace rời.

## 16. Truy vết binary compatibility bằng bytecode, không chỉ source API

Giả sử `Service` trong app đã biên dịch với thư viện phiên bản B. Trong source B có:

~~~java
public String find(String key, int limit) { ... }
~~~

Đây là **chữ ký minh họa**, không phải Java class độc lập. Nhưng runtime nạp bản A chỉ có `find(String)`. Dù method gọi ở source app có tên `find`, JVM phải resolve theo descriptor đã được ghi trong constant pool và bytecode.

### 16.1. Cần so những gì?

- FQCN của class/interface được tham chiếu.
- Tên method/field.
- Các tham số và kiểu trả về trong JVM descriptor.
- `static` so với instance; class so với interface.
- Access modifiers và khả năng truy cập qua module.
- Bridge/erasure nếu có generics.
- API version thực và thay đổi binary-incompatible.

Các command tham khảo:

~~~bash
javap -classpath path/to/app.jar -c -v com.example.app.Service
javap -classpath path/to/lib.jar -p -s com.example.lib.Client
~~~

Output rất dài; chỉ tìm đúng method ref và implementation được JVM resolve. Điều quan trọng là đọc **class file thực trong artifact**, không chỉ `Client.java` của dependency sources JAR có thể không khớp.

### 16.2. Vì sao “rebuild sạch” đôi khi giúp nhưng chưa đủ?

Một clean build xóa stale class output và giúp phát hiện source/bytecode lệch trong workspace. Nhưng nếu pipeline deploy vẫn trỏ bản artifact cũ, hoặc container image vẫn chứa JAR cũ, clean build máy cá nhân không thay đổi runtime. Chỉ tuyên bố đã xử lý khi:
- Artifact mới có identity rõ ràng.
- Runtime deploy thực sự nạp nó.
- Mismatch không còn trong classloading evidence.
- Test/reproduction chạy trên artifact tương đương production.

## 17. Fat JAR, executable JAR, container và application server

Trong các deployment hiện đại, “class nằm trong app.jar” chưa chắc đơn giản:
- Spring Boot executable JAR có thể đặt application classes dưới `BOOT-INF/classes` và dependencies dưới `BOOT-INF/lib`, thường được load bởi launcher riêng.
- WAR được application server giải nén hoặc nạp bằng classloader ứng dụng, đồng thời server có thể cung cấp shared libraries.
- Container image có thể chứa nhiều bản JAR, scripts khởi động chọn một bản cụ thể.
- Plugin architecture có nhiều classloader với quyền ưu tiên khác nhau.
- Một release có thể chạy nhiều replica ở các version khác nhau trong rolling update.

Khi có trace không khớp, xác định **instance cụ thể phát ra log** bằng pod/container/process/build ID. Cùng một URL dịch vụ chưa chắc mọi request vào cùng một version trong giai đoạn rollout.

### 17.1. Cần gì ngoài `jar tf`?

`jar tf app.jar` có thể cho thấy layout, nhưng chưa đủ nếu:
- JAR chứa nested JAR dưới thư mục đặc biệt.
- Bytecode bị transform khi class load.
- Launcher chọn dependency theo layer/classloader.
- Có external config hoặc plugins bổ sung class.
- Runtime nạp class từ directory ngoài JAR.

Khi đó kết hợp build manifest, classloading diagnostics, CodeSource/classloader và startup command của **process thật**. Nếu chỉ copy một JAR ra máy khác và chạy bằng một command khác launcher, bạn có thể thấy kết quả không đại diện deployment.

## 18. Quy trình điều tra thực tế theo mức độ ưu tiên

### Giai đoạn A — Bảo toàn bằng chứng

Ghi nhận:
- Full exception class, message, stack trace, cause, suppressed.
- Timestamp, instance/pod, request/operation ID và thread.
- Ứng dụng/service version, build ID, image digest.
- JDK/runtime version của chính tiến trình.
- Hành động được thực hiện, input **đã ẩn thông tin nhạy cảm**, trạng thái transaction/job.

Không chỉnh sửa log gốc; có thể đánh dấu các frame ứng dụng trong bản sao để phân tích.

### Giai đoạn B — Xác minh nguồn của class

1. Tìm frame ứng dụng gần lỗi ở **đúng cause**.
2. Xác định FQCN, module và classloader.
3. Lấy class file thực trong artifact, xác minh JAR/source origin.
4. So checksum/artifact ID với CI release record.
5. Xác định có duplicate class hoặc dependency conflict không.

Nếu ngay bước này class được nạp không thuộc release dự kiến, đây là một **artifact/deployment problem** cần xử lý trước, không phải bài toán “line 87 viết gì”.

### Giai đoạn C — Đối chiếu bytecode và source

1. `javap -c -l -p` đúng class file để lấy LineNumberTable.
2. `javap -v` khi cần constant pool, major version, flags.
3. Nếu lỗi linking, dùng `javap -p -s` và phân tích descriptor.
4. Mở source đúng commit/release và generated source phù hợp.
5. Đọc caller/input và xác định line là vị trí ném hay gọi.
6. Cân nhắc shading, instrumentation, multi-release JAR và obfuscation mapping.

### Giai đoạn D — Kiểm chứng nguyên nhân bằng thực nghiệm

1. Tái hiện trên artifact giống production.
2. So behavior với artifact/version nghi ngờ.
3. Nếu thay dependency, dùng test nhắm đúng method/ABI bị thiếu.
4. Nếu vấn đề source/line metadata, compile bản có `-g:lines,source` khi cần và xác nhận trace.
5. Nếu lỗi concurrency/async, dùng test điều phối thay vì ngẫu nhiên sleep.
6. Kiểm tra side effect/trạng thái sau exception; đối chiếu được bytecode **không** đồng nghĩa dữ liệu đã rollback.

### Giai đoạn E — Kết luận và phòng ngừa

Báo cáo rõ:
- Class/JAR/commit nào đã chạy.
- Vì sao source trong IDE không khớp.
- Evidence: artifact hash, classloading source, LineNumberTable, dependency resolution hoặc reproducer.
- Root cause và cách sửa.
- Cách ngăn tái diễn: build provenance, dependency locking, clean/reproducible builds, artifact pinning, canary checks hoặc test compatibility.

Tránh chỉ ghi “sửa line 87” nếu thực chất sản phẩm chạy sai JAR.

## 19. Bảng triệu chứng → hướng kiểm tra

| Hiện tượng | Khả năng cần xem trước | Công cụ/bằng chứng |
| --- | --- | --- |
| Trace trỏ line lớn hơn file source hiện tại | Sai source revision, generated source khác | Build ID, Git commit, packaged source |
| Line đúng nhưng statement không liên quan | Stale class/JAR, đổi bố trí source, instrumentation | `javap -c -l`, artifact hash |
| `Unknown Source` hoặc `null:-1` | Thiếu debug info, class generated/obfuscated | `javap -v`, compile options |
| Source trong IDE có method nhưng runtime báo `NoSuchMethodError` | Sai library version/descriptor | Runtime class origin, `javap -p -s` |
| `NoClassDefFoundError` chỉ xuất hiện production | Thiếu runtime dependency hoặc class init lỗi | Cause, dependency tree, class loader |
| `ClassCastException` với cùng tên class ở hai phía | Hai class loaders hoặc duplicate APIs | Class identity, loader/module evidence |
| Trace có tên `lambda$...` | Synthetic method sinh từ lambda | Source method bao lambda, line table |
| Trace có tên class bị relocate | Shading/obfuscation | Relocation config, mapping, dependency version |
| Class khác nhau khi chạy JDK 11 và 17 | Multi-release JAR/JDK/library selection | Manifest, versioned entries, `javap --multi-release` |
| Log từ replica A khớp, replica B không | Mixed deployments | Pod/image digest/build ID |
| Trace chỉ có wrapper Future | Lỗi gốc nằm trong cause của task | `getCause()`, trace từng throwable |
| Không thấy lỗi cause đầy đủ | Logging truncation/cause mất khi bọc | Logger config, giữ nguyên throwable |
| Build lại vẫn thấy trace cũ | Deploy/chạy artifact cũ, cache/launcher | Process command, artifact hash, class load log |

Bảng là **định hướng**, không phải kết luận xác suất chắc chắn. Một triệu chứng có thể có nhiều nguyên nhân; xác minh bằng đúng class/runtime là bước quyết định.

## 20. Anti-pattern thường gây điều tra sai

### 20.1. “Trace nói dòng 55, hãy sửa file source đang mở ở dòng 55”

Sai nếu source không cùng phiên bản build. Hãy xác minh artifact, LineNumberTable và commit.

### 20.2. “IDE compile được nên production có method đó”

Compile thành công chỉ chứng minh compiler nhìn thấy method trong compile classpath. JVM production có thể nạp binary khác. Với `NoSuchMethodError`, kiểm tra runtime descriptor.

### 20.3. “Dependency tree hiển thị version mới, chắc runtime dùng nó”

Có thể app server cung cấp shared JAR, shaded dependency, plugin loader hoặc fat JAR mang version khác. Kết hợp với runtime classloading evidence.

### 20.4. “`javap` không in bảng khi chạy `-l`, tức class không có line numbers”

Tùy tổ hợp options, lệnh có thể báo warning; dùng `javap -c -l` hoặc `-v` đúng class trước khi kết luận.

### 20.5. “FileName.java nghĩa là file này nằm ở đường dẫn đó trong project”

Tên file không chứa path; FQCN/module/classloader mới giúp xác định chính xác.

### 20.6. “Frame đầu luôn chỉ bug cần sửa”

Frame đầu có thể là thư viện phát hiện input xấu; frame ứng dụng gần đó có thể là call site. Exception ngoài cùng còn có thể bọc lỗi cause sâu hơn.

### 20.7. “`javap` trên library.jar đã chứng minh JVM nạp chính JAR ấy”

Không: `javap` chỉ đọc path mà bạn chỉ định. Runtime có thể dùng JAR khác với FQCN trùng. Xác minh CodeSource/load log hoặc artifact thực sự của process.

### 20.8. “Cứ bắt exception là giải quyết mismatch”

Catching `LinkageError` không thay đổi binary ABI. Catch rộng có thể che vấn đề triển khai và khiến trạng thái không an toàn. Sửa classpath/dependency và kiểm thử compatibility.

### 20.9. “Clean build đồng nghĩa đã deploy”

Không. Build output, container image, rollout và process runtime là các bước khác nhau. Cần chứng cứ cho từng bước.

### 20.10. “Không thấy source nên phải có lỗi ở JDK”

Generated code, missing line table, obfuscation, fat JAR hoặc wrong source version thường thực tế hơn. Điều tra theo bằng chứng, không đoán.

## 21. Kiểm thử tự động cho sự khớp giữa binary và source

Một pipeline có thể bổ sung các kiểm tra sau:

1. **Unit tests và integration tests** trên đúng JDK target; không chỉ compile.
2. **Dependency lock hoặc BOM rõ ràng** để giảm version drift.
3. **Duplicate class detection** khi build/deploy đóng gói nhiều JAR.
4. **Smoke test trên artifact đã đóng gói**, chạy bằng launcher/entrypoint như production.
5. **Build metadata** nhúng hoặc xuất cùng artifact để truy commit/image digest.
6. **Binary compatibility checks** khi public API của thư viện thay đổi; đặc biệt ở module chia sẻ.
7. **Line number metadata policy** với module cần chẩn đoán: không vô tình strip `SourceFile`/`LineNumberTable`.
8. **Reproducibility checks** hoặc checksums cho release artifact.
9. **Class origin diagnostics** được bật tạm thời có kiểm soát khi cần.
10. **Canary và rollout verification** để tránh nhiều replica chạy khác version mà không nhận ra.

Ví dụ test một lỗi từ `BytecodeTraceDemo`:

~~~java
IllegalArgumentException error =
        org.junit.jupiter.api.Assertions.assertThrows(
                IllegalArgumentException.class,
                () -> BytecodeTraceDemo.verify(-3));

StackTraceElement top = error.getStackTrace()[0];
org.junit.jupiter.api.Assertions.assertEquals(
        "BytecodeTraceDemo", top.getClassName());
org.junit.jupiter.api.Assertions.assertEquals(
        "verify", top.getMethodName());
~~~

Đây là **fragment JUnit 5 không độc lập**: cần dependency JUnit 5 và class `BytecodeTraceDemo` từ ví dụ runnable. Test về hành vi nghiệp vụ không nên hardcode line number `4`, vì thêm comment đầu file sẽ làm test vỡ dù logic đúng. Khi chủ đích kiểm tra **debug metadata trong release artifact**, có thể kiểm tra line > 0/`LineNumberTable` tồn tại ở giai đoạn CI riêng; phải xác nhận đó là một yêu cầu kỹ thuật thực sự.

### 21.1. Kiểm tra phiên bản binary bị lệch trong test

Tạo hai biến thể của một API ở hai JAR khác nhau và chạy app đã compile với v2 trên runtime classpath chỉ chứa v1. Nếu v1 thiếu method được gọi, test có thể tái hiện `NoSuchMethodError`. Thí nghiệm kiểu này nên chạy trong một tiến trình/loader cô lập và **tuyệt đối không thay thư viện chung của workstation hoặc repo** chỉ để chứng minh. Kết luận phải dựa trên descriptor và bản JAR thực được nạp.

## 22. Checklist chẩn đoán production

- [ ] Đã có **toàn bộ** exception, cause, suppressed, thread và context phù hợp.
- [ ] Đã xác định **instance/process** phát log, không chỉ tên service.
- [ ] Đã lấy deployment version, build ID, commit và artifact/image digest.
- [ ] Đã tìm đúng frame ứng dụng trong **trace của cause liên quan**.
- [ ] Đã xác định FQCN/package/module/classloader.
- [ ] Đã kiểm tra class/JAR thật được runtime nạp, không chỉ dependency trong IDE.
- [ ] Đã xác định có duplicate classes, classpath/module-path hoặc container loader đặc biệt không.
- [ ] Đã so LineNumberTable bằng `javap -c -l -p` hoặc metadata phù hợp.
- [ ] Đã đối chiếu source đúng commit và generated source nếu cần.
- [ ] Nếu lỗi linking, đã kiểm tra descriptors/method/field tại runtime bằng `javap -p -s`.
- [ ] Đã xem shading, obfuscation mapping, multi-release JAR và instrumentation.
- [ ] Đã phân biệt thiếu debug info với source/JAR không khớp.
- [ ] Đã kiểm tra runtime JDK version khi phân tích class file version và thư viện JDK.
- [ ] Đã tái hiện bằng artifact tương đương production trước khi tuyên bố sửa xong.
- [ ] Đã thêm test và cách phòng ngừa version drift/deploy nhầm.
- [ ] Đã bảo vệ dữ liệu nhạy cảm trong log, artifact metadata và thao tác chẩn đoán.

### Bài tập thực hành

Bạn nhận một trace từ một API Java:

~~~text
java.util.concurrent.CompletionException: java.lang.NoSuchMethodError: '...'
    at ...CompletableFuture...
Caused by: java.lang.NoSuchMethodError: ...
    at com.example.order.OrderGateway.send(OrderGateway.java:96)
    ... 3 more
~~~

Bản source trong IDE cho thấy `OrderGateway.java:96` chỉ là câu lệnh ghi log, và Maven/Gradle đang hiển thị thư viện client version mới.

Hãy thực hiện theo thứ tự:

1. Xác định bản deployment đã phát log và hash của artifact chạy.
2. Tìm class `OrderGateway` từ JAR/classloader thực thay vì dùng bản IDE.
3. Dùng `javap -c -l -p` đối chiếu dòng 96 của **class file ấy** với source ở commit phù hợp.
4. Dùng `javap -c -v` trên caller tìm method reference gây `NoSuchMethodError`, sau đó dùng `javap -p -s` trên bản dependency được runtime nạp để so descriptor.
5. Kiểm tra dependency conflict, shared libraries, shaded/nested JAR, module path và classpath thực tế.
6. Nếu hệ thống có nhiều replica, so version/artifact của tất cả instance; không kết luận từ một máy đơn lẻ.
7. Viết một integration test chạy từ packaged artifact bảo đảm method ABI đúng và stack trace/LineNumberTable đủ thông tin.
8. Mô tả root cause bằng bằng chứng: chính xác JAR/class nào đã bị lệch, vì sao source mới không khớp, và hành động sửa ở pipeline/deployment.

**Điểm cốt lõi:** Khi stack trace không khớp mã nguồn, câu hỏi đầu tiên không phải “dòng nào sai?” mà là **“JVM đang thực thi chính xác bytecode nào, được nạp từ đâu và được build từ source nào?”**. Chỉ khi ba lớp source–artifact–runtime khớp nhau thì số dòng trong trace mới trở thành bằng chứng đáng tin để sửa lỗi.