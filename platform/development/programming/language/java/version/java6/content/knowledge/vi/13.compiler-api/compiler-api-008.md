# Tái sử dụng file manager và đóng tài nguyên trong Java Compiler API

## 1. Vì sao file manager quan trọng khi biên dịch nhiều lần?

Trong Java Compiler API (`javax.tools`), `JavaCompiler` chịu trách nhiệm tạo và chạy tác vụ biên dịch, còn `JavaFileManager` chịu trách nhiệm tìm, đọc và ghi các đối tượng file liên quan đến quá trình biên dịch: file nguồn, class file, dependency trong thư mục/JAR, module path và file đầu ra.

Khi dùng trình biên dịch hệ thống, ứng dụng thường lấy một `StandardJavaFileManager`:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("System Java compiler is unavailable");
}
StandardJavaFileManager files =
        compiler.getStandardFileManager(null, Locale.ROOT, StandardCharsets.UTF_8);
~~~

Đoạn trên là **snippet** nằm trong một phương thức Java; cần import `javax.tools.*`, `java.util.Locale` và `java.nio.charset.StandardCharsets`. Khi dùng trong ứng dụng thật, hãy đặt `files` trong `try-with-resources` như ví dụ hoàn chỉnh bên dưới.

**Ý chính:** một `StandardJavaFileManager` có thể được **tái sử dụng qua nhiều tác vụ biên dịch chạy tuần tự**, thay vì tạo và đóng một file manager cho mỗi tác vụ. Theo tài liệu `JavaCompiler` hiện hành, điều đó *có thể* giảm chi phí quét hệ thống file và đọc các JAR do file manager có thể giữ trạng thái/cache; không có cam kết mọi trường hợp sẽ chạy nhanh hơn. Mặt khác, file manager quản lý tài nguyên nên phải được đóng đúng thời điểm.

Sơ đồ vòng đời phù hợp:

~~~text
JavaCompiler
  └── getStandardFileManager(...) -> 1 file manager
        ├── Task #1: tạo CompilationTask mới, call() xong
        ├── Task #2: tạo CompilationTask mới, call() xong
        ├── Task #3: tạo CompilationTask mới, call() xong
        └── close() một lần ở cuối vòng đời sở hữu
~~~

Ở đây **file manager được chia sẻ**, còn **mỗi lần biên dịch phải có một `CompilationTask` riêng**. Việc dùng lại file manager **không có nghĩa** dùng lại `CompilationTask` đã gọi `call()`.

## 2. Phân biệt vai trò của compiler, task và file manager

| Thành phần | Vai trò | Chiến lược vòng đời |
| --- | --- | --- |
| `JavaCompiler` | API tạo các tác vụ biên dịch | Lấy từ `ToolProvider.getSystemJavaCompiler()` nếu runtime có compiler |
| `StandardJavaFileManager` | Quản lý file đầu vào/đầu ra, location và các nguồn như JAR | Tạo một instance cho một chuỗi tác vụ tuần tự; đóng khi xong |
| `JavaCompiler.CompilationTask` | Một lần biên dịch với source/options cụ thể | Tạo mới cho **mỗi** lần; gọi `call()` một lần |
| `DiagnosticCollector<JavaFileObject>` | Thu thập diagnostic do một lần biên dịch gửi ra | Tạo mới cho mỗi task khi muốn tách lỗi và cảnh báo |
| `JavaFileObject` | Đại diện source/class được compiler đọc/ghi | Tạo hoặc lấy từ file manager theo input của mỗi task |
| `StandardLocation.CLASS_PATH` | Nơi tìm các lớp và dependency trên classpath | Cấu hình đúng theo yêu cầu của mỗi chuỗi compile |
| `StandardLocation.CLASS_OUTPUT` | Nơi lưu `.class` sinh ra | Chọn thư mục hợp lệ; không tự xóa khi đóng file manager |

**Một file manager không phải là một kết quả biên dịch.** Các tùy chọn/nguồn truyền vào `compiler.getTask(...)` thuộc task cụ thể. Trạng thái location hoặc nguồn tài nguyên do file manager quản lý có thể tiếp tục có hiệu lực giữa các task; cần kiểm soát rõ khi tái sử dụng.

## 3. Khi nào nên tái sử dụng, khi nào nên tạo mới?

### Tái sử dụng trong chuỗi biên dịch tuần tự

Tình huống phù hợp là một ứng dụng/build tool cần biên dịch nhiều bộ nguồn liên tiếp với classpath, module path hoặc thư viện chung. Mỗi lượt là một task mới, nhưng có thể dùng chung một file manager còn mở:

~~~text
Tạo file manager
  -> cấu hình CLASS_PATH, CLASS_OUTPUT
  -> getTask(sourceA, optionsA).call()  -> xong
  -> getTask(sourceB, optionsB).call()  -> xong
  -> close file manager
~~~

Tài liệu `JavaCompiler` xác định `StandardJavaFileManager` **phải hoạt động với nhiều lần biên dịch tuần tự**. Đây là cơ sở API cho mẫu sử dụng trên, khác với việc dựa vào hành vi nội bộ riêng của một bản JDK.

Điều có thể được tối ưu là việc quét đường dẫn, tìm class và đọc JAR; **không nên khẳng định file manager luôn cache mọi dependency** hoặc giảm thời gian một tỉ lệ cố định. Nếu có nhu cầu tối ưu, hãy đo thời gian/CPU/I/O trên workload thực tế.

### Tạo file manager mới cho vòng đời độc lập

Nên tách file manager khi các job có classpath/module path khác nhau đáng kể, yêu cầu cô lập tài nguyên khác nhau, có dependency được cập nhật, hoặc các job biên dịch chạy đồng thời mà chưa có hợp đồng thread-safety phù hợp. Cùng một file manager được bảo đảm cho **các compilation tuần tự**; **không tự suy diễn** nó an toàn nếu nhiều task gọi đồng thời trên một instance.

Nếu cần biên dịch nhiều job song song, một thiết kế dễ kiểm soát là mỗi job có file manager riêng, hoặc xếp hàng tuần tự các task dùng chung manager dưới một owner. Chia sẻ file manager qua các luồng mà không kiểm soát có thể gây cạnh tranh location, stream và cache.

### Không dùng file manager như bộ nhớ kết quả build

`StandardJavaFileManager` không phải hệ thống incremental build hoàn chỉnh. Nó không tự tính đồ thị phụ thuộc để quyết định class nào cần biên dịch lại, không tự đồng bộ module path sau khi dependency ngoài thay đổi và không tự làm sạch class file cũ. Nếu ứng dụng có incremental build, logic phát hiện nguồn thay đổi, dọn output, version dependency và tính tái lập là trách nhiệm riêng.

## 4. Ví dụ Java 17+ hoàn chỉnh: một file manager, hai lần biên dịch

Ví dụ sau thực hiện **hai compilation tuần tự**:

1. Biên dịch `First` với phương thức `value()` trả về `7`.
2. Biên dịch `Second`, trong đó source tham chiếu `First.value()`.
3. Dùng **chung `StandardJavaFileManager`**, cấu hình `CLASS_OUTPUT` là thư mục tạm và `CLASS_PATH` trỏ tới thư mục ấy để task thứ hai thấy class tạo từ task đầu.
4. Đóng file manager tự động khi rời `try-with-resources`, kể cả khi có ngoại lệ trong khối.

Lưu thành tệp **`FileManagerReuseDemo.java`** (chương trình độc lập đầy đủ):

~~~java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public class FileManagerReuseDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String className, String code) {
            super(URI.create("string:///" + className + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private static boolean compile(JavaCompiler compiler,
                                   StandardJavaFileManager files,
                                   String className, String sourceCode) {
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        JavaFileObject source = new Source(className, sourceCode);

        Boolean result = compiler.getTask(
                null, files, diagnostics,
                List.of("--release", "17", "-proc:none"),
                null, List.of(source)
        ).call();

        for (Diagnostic<? extends JavaFileObject> d
                : diagnostics.getDiagnostics()) {
            if (d.getKind() == Diagnostic.Kind.ERROR) {
                System.err.println("Line " + d.getLineNumber() + ": "
                        + d.getMessage(Locale.ROOT));
            }
        }
        return Boolean.TRUE.equals(result);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "System Java compiler is unavailable");
        }

        Path output = Files.createTempDirectory("compiled-classes-");
        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             null, Locale.ROOT, StandardCharsets.UTF_8)) {
            files.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(output));
            files.setLocationFromPaths(
                    StandardLocation.CLASS_PATH, List.of(output));

            boolean first = compile(
                    compiler, files, "First",
                    "public class First { "
                            + "public static int value() { return 7; } "
                            + "}");
            System.out.println("First compilation: " + first);
            if (!first) {
                throw new IllegalStateException("First compilation failed");
            }

            boolean second = compile(
                    compiler, files, "Second",
                    "public class Second { "
                            + "public static int value() { "
                            + "return First.value() * 2; } "
                            + "}");
            System.out.println("Second compilation: " + second);
            System.out.println("Both class files exist: "
                    + (Files.isRegularFile(output.resolve("First.class"))
                            && Files.isRegularFile(output.resolve("Second.class"))));
        }

        System.out.println("File manager closed");
    }
}
~~~

Trong thư mục chứa `FileManagerReuseDemo.java`, chạy:

~~~sh
javac --release 17 FileManagerReuseDemo.java
java FileManagerReuseDemo
~~~

Kết quả chuẩn (đã biên dịch và chạy thực tế trên JDK 24):

~~~text
First compilation: true
Second compilation: true
Both class files exist: true
File manager closed
~~~

**Giải thích cơ chế:**

- `ToolProvider.getSystemJavaCompiler()` có thể trả `null` khi runtime không chứa system compiler. Chương trình dừng bằng thông điệp rõ ràng thay vì gọi trên giá trị `null`.
- `Files.createTempDirectory(...)` tạo thư mục output có tên riêng để không nhầm với class file của lượt chạy trước. Hai task ghi vào **cùng** thư mục này.
- `setLocationFromPaths(CLASS_OUTPUT, ...)` xác định nơi ghi `First.class` và `Second.class`. Đường dẫn phải tồn tại trước khi cấu hình; `Files.createTempDirectory` đã bảo đảm điều đó.
- `setLocationFromPaths(CLASS_PATH, ...)` giúp task thứ hai tìm thấy `First.class` từ task thứ nhất. Nếu ứng dụng cần thư viện ngoài, cần đưa các thư mục/JAR phù hợp vào classpath chứ không chỉ đặt một output folder như ví dụ.
- `compile(...)` tạo **một collector và một task mới** cho mỗi nguồn, nhưng nhận lại cùng `files`; thứ tự hai lời gọi là tuần tự vì task đầu đã trả kết quả trước khi task sau bắt đầu.
- `List.of("--release", "17", "-proc:none")` chọn target Java 17 và tắt annotation processing cho ví dụ đơn giản. Trong ứng dụng thật, quyết định processor/options theo hợp đồng build.
- Khi rời khối `try`, `files.close()` được gọi tự động. Dòng `File manager closed` ở cuối minh họa việc chương trình đã thoát bình thường khỏi khối. Nó không phải phép kiểm tra bằng API trạng thái “đã đóng” và không thay thế xử lý `IOException` nếu `close()` gặp lỗi.
- Hai file `.class` vẫn tồn tại sau khi file manager đóng. Ví dụ giữ thư mục tạm để minh họa; ứng dụng thực tế phải quyết định lưu hoặc dọn artifact tạm bằng chính sách riêng.

**Không sử dụng lại `CompilationTask`:** gọi `getTask(...)` lần thứ hai để tạo một task mới. Một đối tượng `CompilationTask` đại diện cho một lượt biên dịch; `call()` được thiết kế để gọi một lần cho task ấy.

## 5. `close()`, `flush()` và điều gì xảy ra sau khi đóng

### `close()`: giải phóng tài nguyên của file manager

`JavaFileManager.close()` được định nghĩa để **giải phóng tài nguyên được file manager mở trực tiếp hoặc gián tiếp**. Tùy implementation và hành vi đã thực hiện, tài nguyên có thể gồm stream, handle tới archive/JAR, filesystem cache, bộ đệm liên quan đến thao tác file. `close()` **không đồng nghĩa** xóa file nguồn, JAR hay output `.class` trên ổ đĩa.

`StandardJavaFileManager` mở rộng `Closeable`/`AutoCloseable` nên có thể dùng `try-with-resources`:

~~~java
try (StandardJavaFileManager files =
             compiler.getStandardFileManager(null, null, null)) {
    // Tạo nhiều task biên dịch tuần tự qua files.
} // close() tự được gọi kể cả khi một thao tác trong khối ném ngoại lệ.
~~~

Đây là snippet cần một biến `compiler` hợp lệ. Đưa code sử dụng file manager **vào bên trong phạm vi `try`**; không trả tham chiếu `files` ra ngoài rồi tiếp tục dùng không kiểm soát.

Khi `close()` ném `IOException`, `try-with-resources` chuyển ngoại lệ cho cơ chế xử lý thông thường; nếu trong khối `try` đã có một ngoại lệ khác, ngoại lệ từ `close()` có thể được ghi trong `getSuppressed()` của ngoại lệ chính. Điều này tránh bỏ qua lỗi cleanup một cách âm thầm.

### `flush()`: đẩy dữ liệu đầu ra, vẫn đang sở hữu manager

`JavaFileManager.flush()` dùng để **flush các tài nguyên mở cho việc ghi**. `flush()` không phải một thao tác thay thế bảo đảm cho `close()` ở cuối vòng đời. Ví dụ, các archive/stream được mở để đọc không nhất thiết được giải phóng chỉ vì bạn gọi `flush()`.

Một chuỗi sử dụng hợp lý là:

~~~text
Tạo và cấu hình file manager
 -> compile task A
 -> compile task B
 -> (flush nếu hợp đồng thao tác yêu cầu)
 -> close khi toàn bộ chuỗi công việc kết thúc
~~~

Sau khi `CompilationTask.call()` trả về, compiler đã hoàn tất lượt biên dịch tương ứng; trong trường hợp thông thường không cần tự gọi `flush()` sau từng task chỉ để có thể gọi task sau. Nếu dùng file manager tùy biến với buffering đặc biệt thì cần tuân thủ hợp đồng của implementation đó.

### Chi tiết API dễ bỏ sót: standard file manager có thể tự mở lại

Tài liệu `JavaCompiler.getStandardFileManager(...)` quy định **standard file manager được tự động mở lại nếu bị truy cập sau `flush()` hoặc `close()`**. Vì vậy, **không khẳng định `close()` vĩnh viễn vô hiệu hóa mọi lệnh dùng lại trên `StandardJavaFileManager` do compiler cung cấp**.

Điều đó không làm thay đổi mẫu quản lý vòng đời nên dùng: **đóng một lần khi kết thúc phạm vi sở hữu**. Nếu lại truy cập đối tượng đã đóng, implementation có thể mở tài nguyên lần nữa, làm mất ý nghĩa giải phóng tài nguyên ở ranh giới logic trước đó. Ngoài ra, **file manager tùy biến** không đương nhiên có cùng hành vi tự mở lại; phải xem hợp đồng của nó. Nếu bước sau là một phiên công việc độc lập, chủ động tạo một file manager mới thường dễ quản lý hơn.

## 6. File manager phải sống bao lâu trong một hệ thống thực tế?

| Phạm vi sở hữu | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Một lượt compile độc lập** | Công cụ nhỏ gọi compiler một lần | Tạo manager trong `try-with-resources` và đóng ngay sau task |
| **Một batch tuần tự** | Compile nhiều tệp/job có dependency chung | Tạo một manager cho batch, một task cho từng lần compile, đóng cuối batch |
| **Dịch vụ chạy lâu** | Hàng đợi các yêu cầu build liên tục | Quản lý owner, giới hạn thời gian sống/tài nguyên, phân batch và dọn định kỳ; tránh manager mở vô hạn |
| **Các job song song** | Nhiều yêu cầu compile đồng thời | Mỗi job dùng manager riêng hoặc có cơ chế tuần tự hóa; không giả định một manager chia sẻ an toàn |
| **Dependency thay đổi** | JAR/classpath được thay giữa các job | Xác định lại location, invalidation và output; tạo manager mới khi cần trạng thái sạch |

Điểm quyết định là **ranh giới tài nguyên**: manager giữ trạng thái cần thiết cho những compilation liên quan, rồi được đóng. Không nên dùng một biến static `StandardJavaFileManager` tồn tại suốt tiến trình chỉ vì nghĩ “cache luôn nhanh hơn”; thiết kế ấy có thể giữ handle/JAR lâu hơn nhu cầu và làm khó xử lý dependency thay đổi.

Một số `StandardJavaFileManager` có khả năng cache việc đọc các JAR; nếu xóa/ghi đè dependency trong lúc manager còn dùng, kết quả phụ thuộc implementation và cơ chế cache. Thực tế an toàn là **xem dependency của một batch là bất biến**, hoặc đóng scope cũ và tạo scope/manager mới khi hệ dependency thay đổi.

## 7. Diagnostics và cleanup khi một task thất bại

Tái sử dụng file manager không có nghĩa dùng chung một `DiagnosticCollector` rồi bỏ mặc danh sách diagnostic cũ. Nếu cần báo cáo theo từng lần compile, tạo một collector mới cho từng task (như `compile(...)` trong ví dụ), rồi:

1. Gọi `compiler.getTask(..., diagnostics, ...).call()` và kiểm tra `Boolean.TRUE.equals(result)`.
2. Khi thất bại, đọc `diagnostics.getDiagnostics()`; mỗi `Diagnostic` có thể cho biết loại lỗi (`getKind()`), dòng (`getLineNumber()`), mã (`getCode()`) và thông điệp.
3. Báo cho caller lỗi của **task hiện tại**, không đánh đồng với lỗi của task trước.
4. Đảm bảo file manager vẫn được đóng ở ranh giới `try-with-resources`, kể cả khi trả lỗi sớm hoặc ném ngoại lệ.

Không nên suy luận rằng `call() == false` tức file manager bị hỏng: nguồn có thể sai cú pháp, thiếu classpath hoặc option. Ngược lại, `getTask()` có thể ném `IllegalArgumentException` khi option không hợp lệ, và thao tác file manager có thể ném `IOException`. Các nhánh lỗi cần được xử lý theo nguyên nhân.

Trong ví dụ trên, khi task đầu thất bại thì chương trình ném `IllegalStateException` **trong khối `try`**; `try-with-resources` vẫn gọi `files.close()`. Đây là lợi ích lớn so với chỉ gọi `files.close()` ở cuối phương thức: nếu gặp return/throw trước đó, lệnh close thủ công ở cuối có thể không chạy.

Nếu phải quản lý tài nguyên ngoài file manager (ví dụ tự mở `InputStream`, `FileSystem`, custom file object, thư mục build tạm hoặc class loader tải artifact), đừng mặc định `files.close()` sẽ thay bạn đóng/xóa tất cả. Mỗi tài nguyên cần owner và cleanup riêng theo hợp đồng của chính nó.

## 8. Với file manager tùy biến: đóng đúng đối tượng sở hữu

`JavaCompiler` có thể nhận một `JavaFileManager` không phải manager chuẩn, ví dụ bọc manager chuẩn bằng `ForwardingJavaFileManager` để thay đổi cơ chế đọc/ghi file. Khi đó:

- Xác định **đối tượng nào sở hữu tài nguyên nền** (standard manager, archive FS, stream, cache).
- Khi dùng wrapper, bảo đảm `close()` được chuyển tiếp hoặc xử lý đúng để tài nguyên nền thực sự được giải phóng.
- Không để compiler task đang chạy mà đóng file manager từ một luồng khác.
- Không dựa vào việc manager tùy biến tự mở lại sau `close()`; khả năng tự mở lại là một quy định cụ thể được nói đến cho **standard file manager** nhận từ `JavaCompiler`.
- Tránh đóng file manager do thành phần khác sở hữu, trừ khi hợp đồng ownership quy định thành phần của bạn phải đóng nó.

Nếu đã cung cấp một file manager tùy biến cho `getTask(...)`, hãy đảm bảo nó xử lý các `StandardLocation` mà compiler yêu cầu, bao gồm nguồn/classpath/output/module path phù hợp. Nếu chỉ muốn biên dịch nguồn `String` nhưng ghi class file ra đĩa, dùng `SimpleJavaFileObject` để chứa source **không bắt buộc** phải tự viết một file manager từ đầu; ví dụ mục 4 đã minh họa đường đi đơn giản.

## 9. Những lỗi thường gặp

1. **Tạo manager mới cho mọi tệp trong một batch:** không sai về tính đúng đắn, nhưng bỏ qua cơ hội chia sẻ cache/scan/JAR giữa các task có liên quan. Hãy đo hiệu năng trước khi tối ưu quá mức.
2. **Gọi `getTask(...)` một lần rồi gọi `call()` lặp lại:** `CompilationTask` là một lần biên dịch; muốn lần nữa phải tạo task mới.
3. **Dùng cùng manager cho các task đang chạy đồng thời:** tài liệu bảo đảm chuỗi compilation **tuần tự**, không bảo đảm thread safety của cách chia sẻ đồng thời.
4. **Quên `close()` hoặc không dùng `try-with-resources`:** có thể giữ handle JAR/file, gây giữ tài nguyên lâu và khó thay/xóa file trong một số môi trường.
5. **Tưởng `flush()` là đủ để dọn mọi tài nguyên:** flush dữ liệu đầu ra không thay thế close ở cuối vòng đời.
6. **Tưởng close xóa class file hoặc thư mục tạm:** artifact đã ghi vẫn là file trên hệ thống; cần một bước cleanup có chủ đích.
7. **Tưởng manager sau close luôn bị vô hiệu vĩnh viễn:** standard manager có quy định tự mở lại khi được truy cập; tránh dùng lại ngoài scope ownership dù kỹ thuật này có thể hoạt động.
8. **Tưởng task thứ hai nhìn thấy tự động mọi class vừa compile:** cần cấu hình `CLASS_PATH`/`MODULE_PATH` và `CLASS_OUTPUT` rõ ràng. Ví dụ chỉ hoạt động vì đã đặt `CLASS_PATH` vào đúng thư mục output của task thứ nhất.
9. **Đọc diagnostics lẫn giữa các lượt:** collector dùng chung sẽ tiếp tục giữ bản ghi cũ; tạo collector riêng cho mỗi task để tránh báo lỗi nhầm.
10. **Đưa mã không tin cậy vào compiler trong tiến trình chính:** compiler, processor và plugin có thể tiêu tốn tài nguyên hoặc chạy logic mở rộng. `-proc:none` chỉ tắt annotation processing, không phải sandbox; hãy cô lập nguồn không tin cậy theo yêu cầu an toàn của hệ thống.

## 10. Câu hỏi tự kiểm tra

**Câu 1:** Có hai tập nguồn cần biên dịch tuần tự cùng classpath, một manager có dùng được cho cả hai không?  
**Trả lời:** Có. `StandardJavaFileManager` được thiết kế để hoạt động qua nhiều compilation tuần tự; mỗi compilation vẫn cần một `CompilationTask` riêng.

**Câu 2:** Sau task thứ nhất, tại sao task thứ hai báo không tìm thấy `First` dù `First.class` đã tồn tại trong thư mục output?  
**Trả lời:** Compiler không nhất thiết tìm dependency ở mọi nơi trên ổ đĩa. Hãy kiểm tra và cấu hình `StandardLocation.CLASS_PATH` (hoặc module path nếu thích hợp) để thấy nơi chứa class từ task đầu.

**Câu 3:** Nên gọi `flush()` thay cho `close()` khi kết thúc batch?  
**Trả lời:** Không. `flush()` đẩy dữ liệu output; `close()` mới biểu thị kết thúc vòng đời và giải phóng tài nguyên được quản lý. Dùng `try-with-resources` để đóng ngay cả khi lỗi.

**Câu 4:** Nếu gọi lại standard file manager sau `close()`, Java bắt buộc phải ném lỗi “closed” đúng không?  
**Trả lời:** Không. Tài liệu `JavaCompiler.getStandardFileManager(...)` nói standard manager **tự mở lại khi được truy cập sau `flush` hoặc `close`**. Tuy nhiên đây không phải lý do để mở rộng lifetime của manager không kiểm soát.

**Câu 5:** Nếu biên dịch theo hai job song song và muốn tăng hiệu năng, có thể chia sẻ cùng một manager mà không đồng bộ không?  
**Trả lời:** Không nên. Hợp đồng nêu rõ tái sử dụng qua các lượt tuần tự; song song cần thiết kế quản lý riêng hoặc mỗi job một manager.

**Ghi nhớ:** **Tái sử dụng `StandardJavaFileManager` trong một batch compile tuần tự** có thể tiết kiệm chi phí đọc thư viện; **mỗi lần biên dịch tạo `CompilationTask` và diagnostics riêng**, đồng thời **đóng file manager đúng ranh giới sở hữu** bằng `try-with-resources`. `flush`, `close`, cache và output artifact là các khái niệm khác nhau, cần phân biệt để không rò rỉ tài nguyên hay phụ thuộc vào trạng thái cũ.

### Tài liệu API hiện hành

- [Java SE 26 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): hợp đồng tái sử dụng standard file manager qua nhiều compilation tuần tự và quy tắc tự mở lại.
- [Java SE 26 — `StandardJavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): location, `Path`, file objects và vòng đời.
- [Java SE 26 — `JavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileManager.html): `close()`, `flush()` và quản lý file.
