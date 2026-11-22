# Quét classpath khác khám phá một `Class` đã biết trong Java Reflection

## 1. Câu hỏi nền tảng: đã biết *lớp nào* chưa?

Khi xây công cụ dùng reflection, có hai tác vụ thường bị gọi chung là “quét class”, nhưng đầu vào và phạm vi hoàn toàn khác nhau:

- **Khám phá (introspection) một `Class<?>` đã biết:** chương trình đã có đối tượng `Class`, ví dụ `Order.class`, `object.getClass()` hay kết quả của `Class.forName("com.example.Order")`. Công việc là đọc **metadata của đúng kiểu đó**: tên, interface, constructor, method, field, annotation, superclass và một số thông tin kiểu tổng quát.
- **Quét classpath (classpath scanning):** chương trình **chưa có danh sách đầy đủ các tên lớp ứng viên**. Nó cần duyệt một hoặc nhiều nguồn chứa class như thư mục biên dịch, JAR, hoặc những cơ chế cung cấp lớp khác; từ mỗi resource/class được tìm thấy, xác định ứng viên nào đáp ứng tiêu chí rồi có thể dùng reflection để kiểm tra kỹ hơn.

**Reflection không tự động biến một `Class<?>` thành danh sách tất cả class của ứng dụng.** `Class.getDeclaredMethods()` chỉ trả về những method được khai báo bởi kiểu đang xem; `Class.getDeclaredClasses()` chỉ trả về các member class/interface được khai báo trực tiếp trong kiểu đó, không phải mọi class ở cùng package. Không có phương thức chuẩn `Class.getAllClassesInPackage()` hoặc `ClassLoader.listAllClasses()` cho toàn bộ classpath.

Ví dụ: nếu biết `PaymentService.class`, ta có thể đọc các annotation của `PaymentService` ngay. Nếu muốn tìm **tất cả class có `@Handler`** trong ứng dụng mà chưa biết tên, trước hết phải xác định nguồn ứng viên (qua scan, registry, metadata build-time hoặc cơ chế plugin), rồi mới introspect từng kiểu.

## 2. So sánh đầu vào, kết quả và chi phí

| Khía cạnh | Khám phá một `Class` đã biết | Quét classpath tìm lớp ứng viên |
| --- | --- | --- |
| Đầu vào | Một đối tượng `Class<?>` hoặc tên kiểu đã xác định | Một tập root: thư mục, JAR, package prefix, class loader, module hoặc index |
| Mục tiêu | Hỏi “lớp này có gì?” | Hỏi “trong phạm vi chọn, có lớp nào phù hợp?” |
| API cốt lõi | `getDeclaredMethods`, `getMethods`, `getDeclaredFields`, `getAnnotations`, `getSuperclass` | `Files.walk`, duyệt JAR/resource, module reader, index/framework scanner |
| Phạm vi | Một kiểu, hoặc các kiểu được truy cập có chủ đích từ nó | Có thể rất nhiều file/entry và nhiều kiểu |
| Điều kiện cần | Kiểu có thể được tham chiếu hoặc nạp dưới loader phù hợp | Biết nơi tìm bytecode/resource; xử lý từng định dạng packaging |
| Kết quả | Metadata, `Method`/`Field`/`Constructor`, điều kiện truy cập | Tập *ứng viên*; muốn phân loại thường cần đọc metadata hoặc load class |
| Chi phí | Thường tương ứng số thành viên cần khảo sát | I/O, duyệt entry, lọc, xử lý class loader và đôi khi load nhiều class |
| Lỗi đặc thù | `NoSuchMethodException`, quyền truy cập, lỗi resolution phụ thuộc | Bỏ sót JAR/loader, class hỏng, duplicate names, classpath sai, quét quá rộng |

Quét classpath **thường có thể dẫn đến reflection**, nhưng hai giai đoạn không tương đương. Một scanner tốt nên hạn chế tập ứng viên trước khi cố nạp class; còn khi lớp đã được xác định thì thao tác trên đúng `Class<?>` là đủ, không cần quét lại.

## 3. Khám phá một `Class<?>` đã biết hoạt động thế nào?

Ba cách lấy đối tượng `Class` phổ biến:

```java
Class<String> known = String.class;       // Biết kiểu khi viết mã.
Class<?> runtime = "abc".getClass();      // Biết đối tượng, hỏi kiểu runtime.
Class<?> byName = Class.forName("java.lang.String"); // Biết tên nhị phân.
```

Đây là **các đoạn minh họa** cần đặt trong một method; `Class.forName` cần xử lý hoặc khai báo `ClassNotFoundException`. Dạng một tham số cũng yêu cầu khởi tạo class; muốn hoãn initialization ở tình huống phù hợp có thể dùng `Class.forName(name, false, loader)`.

Khi đã có `Class<?>`, ta có thể:

- `type.getDeclaredMethods()`: các method khai báo trực tiếp trong kiểu đó, gồm cả non-public; không tự gồm method kế thừa.
- `type.getMethods()`: những public method khả kiến theo quy tắc API, gồm cả method public kế thừa.
- `type.getDeclaredFields()` và `getDeclaredConstructors()`: metadata thành viên khai báo trực tiếp.
- `type.getAnnotations()` / `getDeclaredAnnotations()` / `isAnnotationPresent(...)`: xem annotation có `RetentionPolicy.RUNTIME` theo quy tắc kế thừa của API.
- `type.getInterfaces()`, `getSuperclass()`, `isAssignableFrom(...)`: quan hệ kiểu mà JVM mô tả.

Kết quả là metadata của **một kiểu và những mối liên hệ được hỏi cụ thể**. Đọc được metadata không đồng nghĩa có quyền gọi private method hoặc truy cập field qua ranh giới Java Platform Module System (JPMS). Ngoài ra, các API như `getDeclaredMethods()` đôi khi phải resolve những kiểu phụ thuộc trong chữ ký; lỗi liên kết có thể xuất hiện dù đã có `Class<?>`.

## 4. Quét classpath thực chất phải làm những gì?

### Bước A — Xác định phạm vi tìm kiếm

Định nghĩa nguồn ứng viên rõ ràng: một package prefix trong các JAR do ứng dụng sở hữu, thư mục output build, bộ plugin riêng, hay cấu hình module. Không mặc định quét mọi thứ từ JDK, dependency, ứng dụng và tất cả custom loader. Một classpath có thể bao gồm nhiều entry; **module path không đồng nhất với classpath**, còn custom class loader có thể không công bố nơi lưu bytecode.

### Bước B — Liệt kê class resource

Trong thư mục lớp, scanner có thể dùng `Files.walk(root)` để tìm file `.class` rồi chuyển đường dẫn tương đối thành tên nhị phân. Trong JAR, có thể duyệt entries bằng `JarFile`; phải xử lý thư mục, `module-info.class`, `package-info.class` và tên lớp lồng có dấu `$` theo mục đích. Với các cơ chế đóng gói khác (nested JAR, ứng dụng chạy qua launcher riêng, Java modules, runtime image), cần adapter tương ứng.

**`ClassLoader.getResources("package/path")` không phải wildcard quét tất cả class.** API tìm những resource khớp **tên được chỉ định** từ nguồn mà loader thấy. Không nên dựa vào việc liệt kê URL của package resource để kết luận đã bao phủ mọi class có thể nạp. Tương tự, `ClassLoader.getDefinedPackages()` không trả danh sách toàn bộ tên class.

### Bước C — Lọc ứng viên

Scanner có thể lọc path/tên lớp trước, rồi chọn một trong hai hướng:

1. **Đọc metadata bytecode mà không load từng class**, qua thư viện phân tích classfile hoặc chỉ mục có sẵn. Cách này có thể giảm side effect và số class bị load; vẫn phải quan tâm phiên bản bytecode và lớp hỗ trợ.
2. **Load class để kiểm tra bằng reflection**, ví dụ `Class.forName(binaryName, false, chosenLoader)` rồi `isAnnotationPresent` hoặc `isAssignableFrom`. `initialize=false` tránh yêu cầu chạy static initializer ngay lúc đó, **không cam kết không có mọi tác động từ loading/linking**, và class vẫn có thể thất bại vì dependency thiếu, binary mismatch hoặc loader sai.

Annotation dùng để tìm khi chạy phải có `@Retention(RetentionPolicy.RUNTIME)` nếu scanner lọc bằng reflection. Annotation có retention `SOURCE` hoặc `CLASS` không nhất thiết hiện diện qua `Class.getAnnotation(...)` khi chạy.

### Bước D — Quyết định cách dùng kết quả

Sau khi chọn lớp phù hợp, công cụ có thể lưu metadata, tạo registry, kết nối provider hoặc khởi tạo đối tượng (nếu thực sự cần). **Phát hiện một class không có nghĩa nên tạo instance ngay**: class có thể abstract, không có constructor thích hợp, bị giới hạn module hoặc có side effect khi khởi tạo. Nên xác định lifecycle và điều kiện hợp lệ của ứng viên trước khi instantiate.

## 5. Ví dụ Java 17+ chạy được: introspection rồi quét một thư mục

Ví dụ này cố ý dùng **một thư mục output được biết rõ** để thấy sự khác biệt. Nó không giả vờ là một scanner hỗ trợ JAR/module đầy đủ.

Tạo tệp duy nhất `ScanVsInspectDemo.java`, không khai báo `package`:

```java
import java.io.IOException;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ToolComponent {}

interface Tool {
    String run();
}

@ToolComponent
final class FormatterTool implements Tool {
    public String run() {
        return "format";
    }
}

@ToolComponent
final class ParserTool implements Tool {
    public String run() {
        return "parse";
    }
}

final class NotATool {}

public class ScanVsInspectDemo {
    static void inspectKnownClass() throws NoSuchMethodException {
        Class<FormatterTool> known = FormatterTool.class;
        System.out.println("Known: " + known.getSimpleName());
        System.out.println("Method: "
                + known.getDeclaredMethod("run").getName());
        System.out.println("Implements Tool: "
                + Tool.class.isAssignableFrom(known));
    }

    static void scanOwnedDirectory() throws IOException, ClassNotFoundException {
        Path root = Path.of("out");
        List<String> found = new ArrayList<>();

        try (Stream<Path> files = Files.list(root)) {
            for (Path file : files
                    .filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".class"))
                    .toList()) {
                String fileName = file.getFileName().toString();
                String binaryName =
                        fileName.substring(0, fileName.length() - 6);

                Class<?> candidate = Class.forName(
                        binaryName, false,
                        ScanVsInspectDemo.class.getClassLoader());

                if (candidate.isAnnotationPresent(ToolComponent.class)
                        && Tool.class.isAssignableFrom(candidate)
                        && !candidate.isInterface()) {
                    found.add(candidate.getSimpleName());
                }
            }
        }

        Collections.sort(found);
        System.out.println("Discovered: " + String.join(", ", found));
    }

    public static void main(String[] args) throws Exception {
        inspectKnownClass();
        scanOwnedDirectory();
    }
}
```

Chạy từ thư mục có tệp nguồn. Tạo thư mục output rồi biên dịch (Linux/macOS):

```bash
mkdir -p out
javac -encoding UTF-8 -d out ScanVsInspectDemo.java
java -cp out ScanVsInspectDemo
```

PowerShell (Windows):

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out ScanVsInspectDemo.java
java -cp out ScanVsInspectDemo
```

Kết quả chuẩn:

```text
Known: FormatterTool
Method: run
Implements Tool: true
Discovered: FormatterTool, ParserTool
```

**Giải thích từng phần:**

1. `FormatterTool.class` cho ta đối tượng `Class` đã biết ngay từ mã nguồn; `getDeclaredMethod("run")` tìm đúng method thuộc kiểu đó. Không có bước nào cần liệt kê tất cả file `.class`.
2. `Files.list(Path.of("out"))` **chỉ liệt kê trực tiếp** các file của một thư mục output; code lọc tên `.class` và chuyển phần tên tệp thành tên lớp vì ví dụ ở **default package**. Với package thực tế, phải duyệt thư mục con và đổi đường dẫn tương đối thành tên nhị phân đầy đủ.
3. `Class.forName(binaryName, false, loader)` lấy `Class<?>` cho từng ứng viên qua class loader ứng dụng, không yêu cầu chạy initializer ngay. Với bộ lớp của ví dụ, tên class trùng tên file cơ bản vì không dùng các định dạng hay layout đặc biệt.
4. `isAnnotationPresent(ToolComponent.class)` loại các lớp không đánh dấu `@ToolComponent`; `Tool.class.isAssignableFrom(candidate)` chỉ nhận kiểu triển khai hợp đồng `Tool`; điều kiện `!candidate.isInterface()` loại interface khỏi tập ứng viên.
5. `Collections.sort(found)` bảo đảm output ổn định, độc lập thứ tự hệ thống tệp. Hai lớp được phát hiện là `FormatterTool` và `ParserTool`. `NotATool` không được đánh dấu và không triển khai `Tool`.

**Giới hạn có chủ ý:** ví dụ không quét JAR, package lồng, module path, các class loader khác, multi-release JAR, và không xử lý class hỏng. Nó chỉ minh họa dòng xử lý `liệt kê tệp → chuyển tên → lấy Class → introspection → lọc`. Trong công cụ thực tế, phải chọn scanner/thư viện phù hợp và thiết kế xử lý lỗi theo từng nguồn.

## 6. Thiết kế scanner dùng thực tế: các giới hạn khó

### Classpath không phải một thư mục duy nhất

Một ứng dụng có thể nạp class từ nhiều thư mục và JAR. `java.class.path` chỉ phản ánh một phần cấu hình trong nhiều môi trường, không định nghĩa đầy đủ khả năng của custom class loader, module layer hay nested JAR. Class có thể đến từ runtime image (`jrt:`), module path, nguồn động hoặc cơ chế container/framework. Không có API reflection phổ quát để “liệt kê toàn bộ class mà JVM có thể nạp trong tương lai”.

### Cùng tên không nhất thiết cùng kiểu runtime

Hai class loader có thể định nghĩa hai class cùng binary name nhưng khác định danh runtime. Truy vấn `candidate.getName()` bằng nhau chưa đủ để kết luận `candidateA == candidateB`. Khi scanner nạp ứng viên, phải dùng loader đúng biên plugin/framework; không tùy tiện dùng system class loader cho mọi loại ứng dụng.

### Metadata, bytecode và annotation

Nếu chỉ muốn lập **chỉ mục tên class**, đọc bytecode mà không thực hiện `Class.forName` có thể phù hợp hơn. Nếu cần kiểm tra quan hệ subtype hoặc annotation runtime, reflection hữu ích sau khi đã lọc tên. Với annotation metadata, cần xét `RetentionPolicy`, `@Inherited` (chỉ có hiệu lực theo quy tắc đối với annotation trên superclass của class), và những trường hợp annotation trên interface không tự động trở thành annotation của class triển khai.

### Thứ tự, lỗi và độ tin cậy

- Một JAR hỏng, class biên dịch bằng JDK mới hơn, superclass vắng mặt hoặc một class không thể link có thể làm `Class.forName` thất bại. Ghi ngữ cảnh ứng viên, loader và cause; đừng lặng lẽ coi scan là đầy đủ nếu có lỗi.
- Scan cần có phạm vi package/JAR cho phép, giới hạn tài nguyên, chống duyệt đường dẫn ngoài root; một thư mục/JAR do bên không tin cậy cung cấp không nên được coi như nguồn plugin có quyền chạy code.
- Sắp xếp kết quả theo quy tắc xác định và có chính sách duplicate name/classloader. Tránh dựa vào thứ tự `Files.walk` hoặc entries JAR để quyết định ưu tiên provider.
- Nếu classpath ổn định, cache index hoặc dùng metadata build-time; đừng quét lại mọi JAR trên mỗi request. Quét startup có thể chậm và tốn I/O, nhất là trong ứng dụng lớn.
- Không tự động `newInstance` mọi class vừa phát hiện. Chọn constructor, quản lý vòng đời, quyền truy cập, class visibility và lỗi khởi tạo theo hợp đồng rõ ràng.

### JPMS, đóng gói đặc biệt và native image

Khi dùng JPMS, các module được resolve trong layer có thông tin riêng; `ModuleReader` có API để liệt kê resource trong một module theo phạm vi được mở, nhưng đó không tương đương quét mọi classpath. `exports`/`opens` ảnh hưởng quyền truy cập; việc tìm được tên class không đồng nghĩa thực hiện deep reflection được.

Spring Boot executable JAR hoặc framework khác có thể chứa thư viện trong JAR lồng. Một scanner chỉ hiểu `Files.walk` hoặc URL `file:` sẽ bỏ sót các lớp đó. Với native-image/closed-world runtime, kiểu reachable và metadata phản chiếu có thể cần được đăng ký hoặc khai báo ở build-time; quét động như trên JVM thường không được đảm bảo sẽ hoạt động nguyên trạng.

## 7. Khi nào nên quét, khi nào chọn giải pháp khác?

| Nhu cầu thực tế | Cách phù hợp |
| --- | --- |
| Đọc method/field/annotation của một kiểu đã biết | Lấy `Class<?>` rồi dùng reflection; không quét classpath |
| Đã biết các implementation lúc phát triển | Registry/factory/DI cấu hình tường minh, có thể tạo bằng compile-time annotation processor |
| Tìm implementation plugin đã đăng ký theo Java SPI | `ServiceLoader<ServiceType>`; provider khai báo qua `META-INF/services` hoặc `provides ... with` của module |
| Xây framework tìm mọi class có annotation theo package | Scanner có phạm vi rõ, hỗ trợ packaging/class loader và metadata cần đọc; cân nhắc index ở build-time |
| Cần danh sách class hiện có trong một JAR tự quản | Liệt kê entry JAR hoặc classfile; sau đó chọn tiêu chí lọc; đừng mặc định load mọi class |
| Cần quan sát class đã được JVM load | Dùng công cụ chẩn đoán/runtime instrumentation phù hợp; **khác** việc tìm tất cả class có thể tải từ classpath |

`ServiceLoader` có thể làm plugin discovery mà không cần tự quét mọi `.class`, nhưng **nó chỉ phát hiện các provider được đăng ký theo hợp đồng SPI**. Dependency injection framework có cơ chế component scanning/metadata/index riêng; không nên nhầm các cơ chế ấy với API reflection `Class` thuần.

## 8. Cách quyết định và tự kiểm tra

Hãy hỏi theo thứ tự:

1. **Đầu vào đã có `Class<?>` hoặc object cụ thể chưa?** Nếu có, truy vấn metadata của chính kiểu đó trước.
2. **Có cần tìm tên lớp chưa biết trước không?** Nếu có, xác định source được phép và cách khám phá (SPI, registry, build index, scanner).
3. **Phải hỗ trợ thư mục, JAR, nested JAR hay module?** Chọn cơ chế phù hợp môi trường triển khai; không coi một ví dụ `Files.list` là giải pháp tổng quát.
4. **Có cần load/initialize lớp khi scan không?** Ưu tiên lọc metadata trước; nếu dùng `Class.forName`, cân nhắc `initialize=false` và chính sách xử lý lỗi.
5. **Kết quả sẽ dùng để làm gì?** Đọc metadata, đăng ký handler hay tạo instance? Mỗi bước có yêu cầu về constructor, quyền truy cập, lifecycle và an toàn khác nhau.

**Câu 1.** Có `UserService.class` và chỉ muốn lấy danh sách method `public`. Cần classpath scanning không?

**Đáp án:** Không. Dùng `UserService.class.getMethods()`; nếu chỉ muốn method khai báo trực tiếp, dùng `getDeclaredMethods()`.

**Câu 2.** Gọi `MyType.class.getDeclaredClasses()` có tìm mọi class trong package `com.example` không?

**Đáp án:** Không. Nó mô tả những member type được khai báo trực tiếp bên trong `MyType`, không duyệt package hay classpath.

**Câu 3.** Code gọi `ClassLoader.getResources("com/example")` rồi nhận hai URL. Có thể khẳng định tất cả class trong package đã được tìm hết?

**Đáp án:** Không. API tìm resource theo tên được yêu cầu; loader và cách đóng gói quyết định khả năng liệt kê. Hai URL không chứng minh đã bao phủ các class trong nested JAR, custom loader hoặc module khác.

**Câu 4.** Muốn phát hiện các implementation được phát hành dưới dạng provider SPI, bắt buộc tự duyệt tất cả file `.class`?

**Đáp án:** Không. `ServiceLoader` tận dụng đăng ký provider chuẩn của Java. Chỉ khi yêu cầu là tìm những lớp chưa đăng ký theo tiêu chí riêng mới cân nhắc scanner thích hợp.

**Câu 5.** `Class.forName(name, false, loader)` có bảo đảm tuyệt đối không có lỗi và không có tác động runtime?

**Đáp án:** Không. Nó tránh yêu cầu khởi tạo class ở lời gọi đó, nhưng class loading/linking và resolution có thể phát sinh lỗi; về sau class vẫn có thể phải khởi tạo.

**Kết luận:** **Introspection trả lời “kiểu này có những gì?”**, còn **classpath scanning trả lời “trong những nguồn đã chọn có kiểu ứng viên nào?”**. Reflection là công cụ kiểm tra metadata sau khi có `Class<?>`; scanner/registry/SPI là cơ chế xác định tập kiểu cần kiểm tra. Chọn đúng tầng giúp công cụ nhanh, kiểm soát được phạm vi và dễ chạy ổn định qua các kiểu đóng gói Java.