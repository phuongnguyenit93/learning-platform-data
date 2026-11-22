# Giới hạn kích thước nguồn, đầu ra và thời gian của công việc biên dịch trong bộ nhớ

JavaCompiler (JSR 199, package javax.tools) cho phép nhận mã nguồn Java dưới dạng String/JavaFileObject, biên dịch và lưu các file .class vào bộ nhớ. Cách này phù hợp với công cụ kiểm tra bài tập, hệ thống sinh mã, biểu thức động và dịch vụ biên dịch do host quản lý. Tuy nhiên, nếu người dùng gửi mã nguồn quá lớn, yêu cầu tạo quá nhiều bytecode hoặc một cấu trúc mã khiến compiler làm việc rất lâu, một tác vụ có thể tiêu thụ phần lớn tài nguyên JVM.

Bài này thiết kế và thực nghiệm **ba giới hạn riêng**: dung lượng đầu vào, kích thước/đếm đầu ra và thời gian thực hiện. Điểm cốt lõi là phân biệt **giới hạn logic mà JavaCompiler/file manager có thể kiểm tra** với **giới hạn tài nguyên cứng** chỉ thực sự đáng tin khi biên dịch chạy trong tiến trình được giám sát và cô lập.

## 1. Vì sao giới hạn đầu vào đơn lẻ chưa đủ?

Giả sử API nhận một file nguồn Java 8 KiB. Kích thước nhỏ không bảo đảm công việc biên dịch nhẹ: source có thể tạo nhiều anonymous/nested classes, kích hoạt suy luận kiểu phức tạp hoặc chứa biểu thức khiến compiler tốn CPU và heap. Ngược lại, một file nguồn hợp lệ lớn hơn một vài KB chưa chắc phức tạp. Vì vậy chính sách nên kiểm tra nhiều mặt:

| Tài nguyên | Rủi ro nếu không kiểm soát | Nơi đặt giới hạn |
| --- | --- | --- |
| Số byte UTF-8 nguồn | Request body, JSON/String, parse và diagnostic chiếm RAM | Cổng nhận request, **trước khi** đọc hết body |
| Số đơn vị UTF-16 và số source files | Có thể đã tạo nhiều String/file object; tên tệp và tổng dung lượng vượt mức | Input validator trước getTask |
| Số class files tạo ra | Nhiều class/inner class làm tăng số entry và metadata | JavaFileManager.getJavaFileForOutput |
| Tổng byte .class sinh ra | Chiếm bộ nhớ khi giữ bytecode trong ByteArrayOutputStream/Map | OutputStream do file manager cấp, kiểm tra từng lần ghi |
| Diagnostic và text compiler | Nhiều lỗi có thể gây log amplification, response rất lớn | DiagnosticListener và Writer bị giới hạn dung lượng lưu |
| Thời gian chờ (wall-clock) | Request hoặc worker bị giữ lâu | Deadline khi chờ Future hoặc child process |
| CPU, heap, native memory thực tế | Một tác vụ làm suy giảm hoặc ngừng JVM host | Tiến trình riêng và giới hạn từ OS/container |
| Số tác vụ đồng thời | Nhiều job nhỏ cộng lại vượt tài nguyên | Queue + concurrency cap ở tầng scheduler |

**Không có một tham số JavaCompiler chuẩn nào mang nghĩa "biên dịch tối đa 2 giây và 64 MiB RAM".** API cung cấp các điểm mở rộng để kiểm soát file I/O và nhận diagnostics; việc cưỡng chế CPU, heap hay vòng đời của tác vụ phải do tầng thực thi đảm nhận.

Những con số dùng trong lab là **ví dụ**, không phải định mức an toàn được Java bảo đảm: tối đa 8.192 đơn vị UTF-16, 8.192 byte UTF-8 nguồn, 8 class files, tổng 65.536 byte .class, 5 thông báo diagnostic được giữ với tối đa 160 ký tự mỗi thông báo, 1.024 ký tự text compiler bổ sung và 2 giây chờ Future.

## 2. Giới hạn đầu vào: đo gì và đo ở thời điểm nào?

Một String trong Java được truy cập theo đơn vị UTF-16. String.length() **không phải** số byte UTF-8: tiếng Việt, ký tự Unicode ngoài BMP và escape có thể cho kích thước byte khác nhau. Nếu API nhận dữ liệu từ mạng, cần phân biệt:

- **Request bytes**: số byte đi qua mạng, có thể bị nén trước khi gửi; phải đặt quota cho cả kích thước nén và sau giải nén nếu cho phép Content-Encoding.
- **Decoded source bytes**: số byte khi mã nguồn được mã hóa theo UTF-8, thích hợp cho chính sách dung lượng source artifact.
- **String length**: số đơn vị UTF-16 đang giữ trong heap, dùng để chặn sơ bộ trước khi mã hóa lại.
- **Số file và tổng byte của cả batch**: không chỉ giới hạn riêng từng file; 100 file x 8 KiB vẫn là tổng dung lượng đáng kể.

Một kiểm tra đơn giản sau khi String đã được tạo:

~~~java
// Minh họa: áp dụng trước khi tạo compilation task.
if (source.length() > 8_192) {
    throw new IllegalArgumentException("source UTF-16 length limit");
}
if (source.getBytes(StandardCharsets.UTF_8).length > 8_192) {
    throw new IllegalArgumentException("source UTF-8 byte limit");
}
~~~

Đoạn trên **chưa bảo vệ tầng nhận HTTP** vì input đã được đọc thành String. Với dịch vụ thực, hãy dừng đọc khi vượt quota tại InputStream/BodyPublisher/parser, giới hạn số lượng phần tử và tổng số byte trước khi tạo các String lớn. Chỉ sau đó mới chuyển thành JavaFileObject để compiler sử dụng.

Đặt chính sách rõ về encoding (UTF-8), package/class name, tên file hợp lệ, một hay nhiều compilation units và danh sách tùy chọn compiler được phép. Không nhận nguyên một command-line options string do người dùng ghép tùy ý; các tùy chọn có thể thay đổi classpath, processor, nơi ghi output hoặc hành vi của compiler.

## 3. Giới hạn đầu ra: không đợi tới khi bytecode đã được tạo hết

Trong biên dịch trong bộ nhớ, ta thường triển khai:

- **SimpleJavaFileObject** cho source: getCharContent trả về String.
- **ForwardingJavaFileManager** bọc standard file manager và ghi đè getJavaFileForOutput để nhận class file.
- **JavaFileObject output** với openOutputStream trả về stream riêng, có thể ghi bytecode vào ByteArrayOutputStream.
- **DiagnosticListener** ghi nhận lỗi/warning, thay vì để mọi thông báo trôi tự do vào bộ đệm không giới hạn.

Một cách kiểm tra sai là sau khi compilationTask.call() đã hoàn tất, tính tổng kích thước của các mảng byte rồi mới quyết định "quá giới hạn". Khi ấy bộ nhớ có thể đã bị tiêu thụ. Tốt hơn, **trước mỗi write(byte[], off, len), kiểm tra còn đủ quota rồi mới ghi**. Nếu hết quota, báo IOException và đánh dấu output bị vượt giới hạn.

Cần thêm quota **số lượng file .class**: rất nhiều file rỗng hoặc file nhỏ vẫn có overhead của object, hash map, URI và metadata. Không chỉ tính số byte của một class riêng; phải tính **tổng** output của tất cả các class do cùng một task tạo ra.

Một byte quota ở file manager **không đồng nghĩa heap quota**. Compiler còn giữ AST, symbol table, constant pool, diagnostics và temporary buffers trong RAM. ByteArrayOutputStream có thể cấp phát dư capacity và toByteArray() còn sao chép mảng. Vì vậy mức giới hạn bytecode thực tế không ràng buộc toàn bộ RAM sử dụng.

## 4. Lab Java 17+: compiler trong bộ nhớ với quota và soft timeout

Ví dụ sau là **một chương trình hoàn chỉnh**. Nó biên dịch một class Java từ String, lưu các .class tạo ra trong memory map, chặn tổng bytecode và số file, giới hạn số diagnostic được lưu, hạn chế text writer, rồi chờ tối đa một khoảng thời gian. Nó không thực thi class mới biên dịch.

File duy nhất: **BudgetCompilerDemo.java**. Chạy trên **JDK 17+**, không cần thư viện bên ngoài.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.Writer;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticListener;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class BudgetCompilerDemo {
    private static final int MAX_SOURCE_CHARS = 8_192;
    private static final int MAX_SOURCE_BYTES = 8_192;
    private static final int MAX_CLASS_FILES = 8;
    private static final long MAX_CLASS_BYTES = 65_536;
    private static final int MAX_DIAGNOSTICS = 5;
    private static final int MAX_DIAG_CHARS = 160;
    private static final int MAX_OTHER_TEXT = 1_024;
    private static final long WAIT_MILLIS = 2_000;

    private record Result(
            String status,
            int classCount,
            long classBytes,
            boolean classPresent,
            int diagnosticsStored) {}

    private static Result empty(String status) {
        return new Result(status, 0, 0, false, 0);
    }

    private static final class MemorySource extends SimpleJavaFileObject {
        private final String source;

        MemorySource(String binaryName, String source) {
            super(URI.create("mem:///src/"
                    + binaryName.replace('.', '/') + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    // Lưu có giới hạn; không dùng DiagnosticCollector giữ mọi diagnostic.
    private static final class LimitedDiagnostics
            implements DiagnosticListener<JavaFileObject> {
        private final List<String> kept = new ArrayList<>();

        @Override
        public void report(Diagnostic<? extends JavaFileObject> diagnostic) {
            if (kept.size() >= MAX_DIAGNOSTICS) {
                return;
            }
            String message = diagnostic.getMessage(Locale.ROOT);
            if (message.length() > MAX_DIAG_CHARS) {
                message = message.substring(0, MAX_DIAG_CHARS);
            }
            kept.add(diagnostic.getKind() + ": " + message);
        }
    }

    // Chặn lượng text phụ mà compiler ghi qua tham số Writer của getTask.
    private static final class LimitedWriter extends Writer {
        private final StringBuilder buffer = new StringBuilder();
        private boolean truncated;

        @Override
        public void write(char[] chars, int off, int len) {
            Objects.checkFromIndexSize(off, len, chars.length);
            int room = MAX_OTHER_TEXT - buffer.length();
            int n = Math.min(len, Math.max(room, 0));
            buffer.append(chars, off, n);
            if (n < len) {
                truncated = true;
            }
        }

        @Override
        public void write(String text, int off, int len) {
            Objects.checkFromIndexSize(off, len, text.length());
            int room = MAX_OTHER_TEXT - buffer.length();
            int n = Math.min(len, Math.max(room, 0));
            buffer.append(text, off, off + n);
            if (n < len) {
                truncated = true;
            }
        }

        @Override public void flush() {}
        @Override public void close() {}
    }

    // Chỉ giữ class bytecode trong bộ nhớ, không ghi class ra thư mục.
    private static final class LimitedFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, byte[]> classes = new HashMap<>();
        private int outputFiles;
        private long outputBytes;
        private boolean limitReached;

        LimitedFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        private void reserve(int amount) throws IOException {
            // Phép trừ tránh overflow khi cộng số lượng đã dùng.
            if (amount < 0 || amount > MAX_CLASS_BYTES - outputBytes) {
                limitReached = true;
                throw new IOException("class bytes quota exceeded");
            }
            outputBytes += amount;
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location, String binaryName,
                JavaFileObject.Kind kind, FileObject sibling)
                throws IOException {
            if (kind != JavaFileObject.Kind.CLASS
                    || outputFiles >= MAX_CLASS_FILES) {
                limitReached = true;
                throw new IOException("class file count/type limit");
            }
            outputFiles++;

            URI uri = URI.create("mem:///classes/"
                    + binaryName.replace('.', '/') + kind.extension);

            return new SimpleJavaFileObject(uri, kind) {
                @Override
                public OutputStream openOutputStream() {
                    ByteArrayOutputStream bytes = new ByteArrayOutputStream();

                    return new FilterOutputStream(bytes) {
                        @Override
                        public void write(int value) throws IOException {
                            reserve(1);
                            out.write(value);
                        }

                        @Override
                        public void write(byte[] data, int off, int len)
                                throws IOException {
                            Objects.checkFromIndexSize(off, len, data.length);
                            reserve(len);
                            out.write(data, off, len);
                        }

                        @Override
                        public void close() throws IOException {
                            super.close();
                            classes.put(binaryName, bytes.toByteArray());
                        }
                    };
                }
            };
        }

        // Không cho tác vụ ghi thêm file resource/source ra đĩa.
        @Override
        public FileObject getFileForOutput(
                Location location, String packageName,
                String relativeName, FileObject sibling) throws IOException {
            limitReached = true;
            throw new IOException("non-class output is disabled");
        }
    }

    private static Result compileNow(
            String binaryName, String source, Path emptyClasspath)
            throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            return empty("NO_JDK_COMPILER");
        }

        LimitedDiagnostics diagnostics = new LimitedDiagnostics();
        LimitedWriter text = new LimitedWriter();

        try (LimitedFileManager files = new LimitedFileManager(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8))) {

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "-classpath", emptyClasspath.toString());

            JavaCompiler.CompilationTask task = compiler.getTask(
                    text,
                    files,
                    diagnostics,
                    options,
                    null,
                    List.of(new MemorySource(binaryName, source)));

            boolean success = Boolean.TRUE.equals(task.call());
            String status;
            if (files.limitReached) {
                status = "OUTPUT_LIMIT";
            } else if (text.truncated) {
                status = "COMPILER_TEXT_LIMIT";
            } else {
                status = success ? "OK" : "COMPILATION_ERROR";
            }

            return new Result(
                    status,
                    files.classes.size(),
                    files.outputBytes,
                    files.classes.containsKey(binaryName),
                    diagnostics.kept.size());
        }
    }

    private static Result compileWithBudget(
            String binaryName, String source, Path emptyClasspath) {

        // Chặn nhanh trước khi tạo JavaFileObject/CompilationTask.
        if (source.length() > MAX_SOURCE_CHARS) {
            return empty("SOURCE_LIMIT");
        }
        if (source.getBytes(StandardCharsets.UTF_8).length
                > MAX_SOURCE_BYTES) {
            return empty("SOURCE_LIMIT");
        }

        // Daemon thread chỉ phục vụ lab: không tạo hard deadline CPU/heap.
        ExecutorService executor = Executors.newSingleThreadExecutor(job -> {
            Thread worker = new Thread(job, "compiler-demo-worker");
            worker.setDaemon(true);
            return worker;
        });

        Future<Result> future = executor.submit(
                () -> compileNow(binaryName, source, emptyClasspath));
        try {
            return future.get(WAIT_MILLIS, TimeUnit.MILLISECONDS);
        } catch (TimeoutException ex) {
            future.cancel(true); // Chỉ yêu cầu interrupt; có thể vẫn đang chạy.
            return empty("SOFT_TIMEOUT");
        } catch (InterruptedException ex) {
            future.cancel(true);
            Thread.currentThread().interrupt();
            return empty("INTERRUPTED");
        } catch (ExecutionException ex) {
            // Trong sản phẩm thật: log exception/cause, không trả stack trace cho client.
            return empty("COMPILER_FAILURE");
        } finally {
            executor.shutdownNow(); // Best effort, không bảo đảm thread dừng ngay.
        }
    }

    public static void main(String[] args) throws Exception {
        // Thư mục classpath trống dùng để tránh thấy class của host.
        // Mã nguồn và .class của ví dụ vẫn được giữ trong bộ nhớ.
        Path emptyClasspath = Files.createTempDirectory("empty-javac-cp-");
        try {
            String source =
                    "package demo; public final class Hello { "
                    + "public static int answer() { return 42; } }";

            Result normal = compileWithBudget(
                    "demo.Hello", source, emptyClasspath);
            System.out.println("status=" + normal.status());
            System.out.println("classPresent=" + normal.classPresent());
            System.out.println("classCount=" + normal.classCount());
            System.out.println("withinOutputBudget="
                    + (normal.classBytes() <= MAX_CLASS_BYTES));
            System.out.println("diagnosticsStored="
                    + normal.diagnosticsStored());

            // Bị từ chối trước bước biên dịch.
            Result huge = compileWithBudget(
                    "demo.Hello", "x".repeat(MAX_SOURCE_BYTES + 1),
                    emptyClasspath);
            System.out.println("oversize=" + huge.status());
        } finally {
            Files.deleteIfExists(emptyClasspath);
        }
    }
}
~~~

Lưu ý về mã:

- Result giữ metadata để minh họa. Trong hệ thống thật, có thể giữ Map<String, byte[]> ở **kết quả thành công đã xác minh** để nạp class sau đó. Bài lab cố tình không thực thi bytecode.
- Sự kiện getJavaFileForOutput được tính vào số file; từng lệnh write đặt quota trước khi bytes được giữ lại. Nếu compiler bắt một IOException thành diagnostic hoặc RuntimeException, cờ limitReached vẫn giúp phân loại trường hợp quota class output.
- Bài lab dùng standard file manager cho classpath/JDK module lookup, nhưng redirect **class output** vào bộ nhớ. Một thư mục tạm rỗng được tạo chỉ để chỉ định classpath; đây không phải nơi lưu file .class.
- Tùy chọn **-proc:none** chặn annotation processing. Điều này giảm một nguồn thực thi code bên ngoài trong quá trình compile, nhưng không biến JavaCompiler thành sandbox. Không truyền options, classpath hoặc processor path tùy ý từ request.
- LimitedDiagnostics chỉ giới hạn **số thông điệp được giữ** và ký tự lưu mỗi thông điệp; bản thân compiler vẫn có thể sinh nhiều diagnostics hoặc tạo message lớn trước khi callback nhận được.
- LimitedWriter chặn số ký tự được giữ từ writer bổ sung. Nó không thể giới hạn lượng CPU/heap mà compiler dùng để tạo chuỗi trước khi gọi write.
- Chặn bằng IOException là một cơ chế **kiểm soát output của lab**. Compiler/provider tùy triển khai có thể ném lỗi khác; mọi bản ghi bytes sinh được trước khi thất bại phải bị loại bỏ, **không phát hành class khi status khác OK**.
- Nếu SOFT_TIMEOUT xảy ra, task có thể vẫn chạy ở daemon thread và còn tham chiếu tới input, file manager hoặc classpath. Vì vậy chương trình này dùng để học cơ chế giới hạn, **không đủ để phục vụ mã nguồn không tin cậy trong một JVM dùng chung**.

### 4.1. Build và chạy

Dùng JDK 17+:

~~~bash
javac -encoding UTF-8 BudgetCompilerDemo.java
java BudgetCompilerDemo
~~~

Với input bình thường, compiler hoàn thành trong thời gian chờ và sinh một class. Stdout kỳ vọng:

~~~text
status=OK
classPresent=true
classCount=1
withinOutputBudget=true
diagnosticsStored=0
oversize=SOURCE_LIMIT
~~~

Những dòng kết quả này giả định compiler hoàn thành trước **2 giây** trên máy có tài nguyên đủ. Nếu máy quá tải hoặc JVM khởi động compiler chậm hơn thời hạn lab, trạng thái có thể là SOFT_TIMEOUT: **timeout theo thời gian thực không phải hành vi đầu ra tất định**. Không dùng con số 2 giây làm yêu cầu tương thích xuyên máy; chọn deadline dựa vào đo đạc latency thực tế và mức dịch vụ.

Nếu chạy chương trình với Java runtime không chứa module jdk.compiler, ToolProvider.getSystemJavaCompiler() có thể trả null. Hãy chạy bằng bản phân phối JDK có compiler. Không cần thêm source file riêng, không cần tải dependency bên ngoài và không cần chuyển class vào classpath host.

### 4.2. Tại sao ba hạn mức đều có ích?

Ở nhánh normal: source được kiểm tra trước khi compiler bắt đầu; file manager nhận và chặn từng byte bytecode; host chỉ chờ trong deadline đã đặt. Ở nhánh oversize: chuỗi bị từ chối trước khi tạo task; status được gán rõ ràng là SOURCE_LIMIT.

Một trường hợp khó hơn: input chỉ 2 KiB nhưng khi compile tạo 30 class. Counter ở getJavaFileForOutput phát hiện vượt **MAX_CLASS_FILES** dù tổng byte còn nhỏ. Trường hợp khác tạo một class 100 KiB: reserve(...) phát hiện vượt **MAX_CLASS_BYTES** ngay khi write vượt ngưỡng. Cả hai phải là OUTPUT_LIMIT và không trả artifact một phần cho người dùng.

Nếu cú pháp sai, compiler có thể báo COMPILATION_ERROR, nhưng listener chỉ giữ tối đa MAX_DIAGNOSTICS thông báo đầu tiên, mỗi thông báo tối đa MAX_DIAG_CHARS. Nếu compiler cố ghi text khác vượt MAX_OTHER_TEXT, mã sẽ đánh dấu COMPILER_TEXT_LIMIT. Các giới hạn output là độc lập với kết quả parse/type-check.

## 5. Timeout trong JVM: giới hạn thời gian chờ khác giới hạn CPU

Trong demo, Future.get(timeout, TimeUnit.MILLISECONDS) **đặt giới hạn thời gian mà thread gọi đợi kết quả**. Khi hết hạn, future.cancel(true) thử interrupt worker. Điều đó **không có nghĩa** thread của compiler đã dừng. Compiler có thể đang tính toán mà không kiểm tra interrupt, giữ heap/cpu và còn tiếp tục trong khi API đã trả SOFT_TIMEOUT.

Cũng cần lưu ý:

- Future.isDone() sau cancel có thể cho biết trạng thái future đã kết thúc theo hợp đồng Future, **không xác nhận mọi công việc đang chạy đã dừng**.
- ExecutorService.shutdownNow() cố ngắt công việc đang chạy nhưng tài liệu JDK không bảo đảm nó sẽ dừng một task không hợp tác.
- Một daemon thread vẫn tiêu thụ tài nguyên khi JVM còn sống; đánh dấu daemon chỉ giúp JVM có thể kết thúc mà không cần đợi thread đó.
- Một request bị timeout nhưng worker chưa kết thúc vẫn phải được tính vào **số job đang tiêu thụ tài nguyên**, không thể lập tức trả slot concurrency cho người dùng khác như thể job đã dừng thật.
- Cố ép dừng thread qua Thread.stop() không phải một giải pháp quản lý compiler an toàn. Cần cô lập ở mức tiến trình nếu yêu cầu cưỡng chế.

Vì vậy cần đặt tên trạng thái và SLA chính xác: **SOFT_TIMEOUT** nghĩa là caller đã dừng chờ; không cam kết ngân sách CPU/RAM của compiler đã được cưỡng chế.

Một lỗi tinh tế là đóng file manager, xóa classpath tạm hoặc phát hành output **ngay sau khi Future.get hết hạn** trong khi worker còn đang sử dụng các object ấy. Thiết kế thực tế phải bảo đảm tài nguyên có owner và lifecycle thống nhất. Nếu compiler không thể bị ngắt an toàn, cần chuyển công việc sang process worker có thể kết thúc được trước khi cleanup.

## 6. Kiến trúc nên dùng khi cần giới hạn cứng

Để biên dịch mã từ nhiều người dùng hoặc nguồn chưa tin cậy, thiết kế chắc chắn hơn:

~~~text
HTTP/request gateway
    |
    | quota byte/source count + xác thực + queue limit
    v
scheduler (max concurrent compiles, per-tenant budget)
    |
    v
isolated compiler worker process/container
    |   JDK version cố định, -proc:none
    |   allowlisted options, classpath riêng
    |   OS/container CPU + memory + process + filesystem limits
    |   in-memory source/class output với quota
    |
    +--> response chỉ khi compile thành công, output/diagnostics đủ điều kiện
    |
    +--> timeout/vi phạm quota: terminate worker, cleanup, đánh dấu FAILED
~~~

Một worker process có thể tiếp tục dùng **javax.tools.JavaCompiler và memory file manager** như lab; việc tách process không buộc phải chuyển sang compile qua file trên đĩa. Nguồn đi vào worker có thể qua IPC được kiểm soát; trả lại bytecode qua giao thức có giới hạn kích thước. Host phải xác minh message length trước khi cấp phát.

Nếu chấp nhận compiler CLI javac trong process riêng, host có thể đặt timeout ở Process (mã dưới là **đoạn minh họa, chưa phải chương trình độc lập**):

~~~java
// Giả định đường dẫn executable, source file, classpath và output dir
// đều do host kiểm soát; output được redirect để tránh nghẽn pipe.
Process process = new ProcessBuilder(
        javacPath,
        "--release", "17",
        "-proc:none",
        "-classpath", safeClasspath,
        "-d", controlledOutputDirectory,
        sourceFilePath)
        .redirectOutput(ProcessBuilder.Redirect.DISCARD)
        .redirectError(ProcessBuilder.Redirect.DISCARD)
        .start();

boolean finished = process.waitFor(2, TimeUnit.SECONDS);
if (!finished) {
    process.destroyForcibly();
    process.waitFor();
    throw new IllegalStateException("COMPILER_TIMEOUT");
}
if (process.exitValue() != 0) {
    throw new IllegalStateException("COMPILATION_ERROR");
}
~~~

Ở đây Process.waitFor(timeout, unit) trả về false nếu deadline hết, và destroyForcibly() yêu cầu kết thúc process. Đây là **đường cưỡng chế hữu ích hơn Future.cancel(true)**, nhưng chưa đầy đủ cho sản phẩm thật:

- Child process có thể tạo process con; cần quản lý **process tree/process group/container** phù hợp với OS, không chỉ kill một PID.
- Sau destroyForcibly, process có thể chưa chết tức thì; waitFor() tiếp giúp thu dọn nhưng cần chính sách tổng deadline và xử lý lỗi OS.
- Đầu ra compiler, stdout/stderr, file trong output dir, log và lượng IPC đều phải bị giới hạn. Mã trên discard text để tránh tắc pipe, nên **không thu diagnostics**; sản phẩm cần thiết kế bộ đọc có quota riêng nếu muốn trả thông báo lỗi.
- Java process dùng -Xmx chỉ giới hạn một phần Java heap; native memory, CPU, file descriptors, process count và filesystem cần thêm ràng buộc của container/cgroup/Windows Job Objects hoặc cơ chế tương đương.
- Compile bằng javac CLI xuất ra thư mục file; nếu yêu cầu giữ bytecode hoàn toàn trong bộ nhớ, chạy JavaCompiler API **bên trong process cô lập**, rồi truyền kết quả qua IPC bị chặn kích thước.

Tính chất hard limit phụ thuộc tầng thực thi OS/container và cấu hình tài nguyên. Process.kill không tự thiết lập giới hạn heap, CPU, disk hoặc chống mọi side effect của một tiến trình có quyền rộng.

## 7. Chính sách an toàn cho classpath, processor và runtime

Một dịch vụ biên dịch động có thêm bề mặt tấn công ngoài kích thước nguồn. Các lựa chọn kiểm soát quan trọng:

| Thành phần | Chính sách nên áp dụng | Lý do |
| --- | --- | --- |
| JDK và --release | Ghim JDK worker và phiên bản ngôn ngữ/target được hỗ trợ | Kết quả dễ tái lập, tránh API không tương thích |
| Annotation processing | Mặc định -proc:none; chỉ bật với processor đã xét duyệt | Processor là mã có thể được thực thi khi compile |
| Classpath/module path | Cho phép danh sách dependency kiểm chứng, không tự nối toàn classpath host | Hạn chế ảnh hưởng và rò thông tin từ host |
| Compiler options | Tạo danh sách option ở server, không chấp nhận tham số tùy ý từ client | Tránh thay đường nạp/ghi file và thay chính sách |
| File manager | Ghi nhận ClassOutput và cấm/kiểm soát các loại output khác | Không bỏ lọt file/resource do task sinh ra |
| Diagnostics | Cap số lượng, kích thước text và nội dung trả về | Tránh log amplification hoặc lộ source không cần thiết |
| Compiled artifact | Chỉ publish sau status OK, size check và kiểm tra class names | Không dùng bytecode từ job lỗi/timeout |
| Execution | Không chạy class vừa biên dịch trong JVM host có quyền lớn | Biên dịch thành công không chứng minh code an toàn |

Một class có thể biên dịch thành công rồi khi được nạp/khởi tạo sẽ truy cập file, network, tạo thread hoặc dùng nhiều CPU. JavaCompiler **không kiểm chứng tính an toàn của chương trình sinh ra**. Vì thế nếu cần chạy chương trình của người dùng, execution phải có sandbox/process isolation và hạn mức riêng, tách khỏi ngân sách compile.

Có thể dùng danh sách tên binary, hash artifact, phiên bản JDK, byte count, diagnostic count và thời gian thực tế để audit; tránh log toàn bộ source khi không cần và bảo vệ thông tin nhạy cảm trong diagnostics.

## 8. Cách đo, tính ngân sách và xử lý tính đồng thời

Giới hạn theo một job không đủ nếu host chấp nhận nhiều job cùng lúc. Giả sử mỗi job có output cap 64 KiB, nhưng compile có thể dùng hàng trăm MiB heap tạm; 100 job song song vẫn có thể quá tải. Dịch vụ cần thêm:

1. **Concurrency ceiling**: số worker compiler/process tối đa, có giới hạn riêng cho từng tenant.
2. **Bounded queue**: giới hạn số request đang chờ và thời gian chờ hàng đợi; trả BUSY/429 khi đầy thay vì tích lũy vô hạn.
3. **Admission control**: kiểm tra source quota ngay trước khi vào queue hoặc trước khi dành worker, tránh giữ nhiều body đã decode.
4. **Deadline tổng**: xác định rõ thời gian gồm thời gian queue, startup JVM, compiler initialization, compile, gửi kết quả và cleanup hay chỉ phần compile; không trộn các thước đo.
5. **Per-process resource quotas**: CPU, RAM, số process, file descriptors, dung lượng đĩa và output IPC.
6. **Metrics**: tổng bytes nguồn, class count/bytes, diagnostics retained/truncated, queue wait, run wall time, CPU time nếu có nguồn số đo tin cậy, timeout/kill rate.
7. **Lifecycle cleanup**: hủy job và chắc chắn worker/process đã thoát trước khi tái sử dụng slot. Nếu worker bị timeout nhưng vẫn sống, phải theo dõi nó như một job đang chạy.
8. **Result cache có điều kiện**: nếu cần cache biên dịch, key phải bao gồm hash source, JDK/version, compiler options và dependency set. Cache cũng cần giới hạn dung lượng/TTL.

Một deadline chỉ tính từ lúc worker bắt đầu có thể để request nằm chờ không giới hạn. Một deadline tính từ lúc nhận request phải còn đủ thời gian cho các giai đoạn sau; một job đã hết hạn trong queue nên bị loại trước khi compiler được tạo.

Trong file manager nhiều tác vụ, đừng dùng một counter static toàn JVM cho mọi job nếu không thiết kế concurrency đúng. Lab tạo một LimitedFileManager mới cho mỗi invocation và ghi output trên thread compiler của job đó; counter thuộc **một task**, không chia sẻ giữa các công việc đang biên dịch song song.

## 9. Thực nghiệm thêm để hiểu giới hạn

Các thí nghiệm sau được thực hiện với chính chương trình lab, thay đổi **một chính sách mỗi lần** rồi build lại:

### A. Quá giới hạn source

Giữ source là "x".repeat(MAX_SOURCE_BYTES+1). Kết quả mong đợi SOURCE_LIMIT xảy ra **trước khi submit compiler task**, nên không có bytecode hoặc diagnostic do compiler tạo. Khi request đã được chuyển thành String, giới hạn của lab chỉ chống phát sinh thêm công việc, chưa bảo vệ heap đã dùng để nhận request.

### B. Quá số class files

Đổi MAX_CLASS_FILES thành 0 rồi chạy với mã nguồn Hello hợp lệ. getJavaFileForOutput sẽ đánh dấu output limit khi compiler yêu cầu class đầu tiên. Job phải trả OUTPUT_LIMIT hoặc COMPILER_FAILURE tùy cách lỗi IOException được compiler/driver diễn giải; trường hợp không thành công không được publish artifact. Với code lab, nếu task.call trả về và limitReached được quan sát sau đó, trạng thái là OUTPUT_LIMIT. Khi cần ổn định mã lỗi giữa compiler implementation, hãy bắt/chuẩn hóa cause trong tầng worker.

### C. Quá số byte .class

Đổi MAX_CLASS_BYTES thành 64. Compiler sẽ bắt đầu sinh class output nhưng write vượt quota. Không dùng một byte array lớn rồi chỉ kiểm tra chiều dài cuối cùng; file manager phải dừng trước lần ghi làm vượt mức. Kiểm tra count và flag, xác nhận class kết quả không được phát hành.

### D. Diagnostic nhiều hoặc quá dài

Đưa một source cố tình có nhiều lỗi cú pháp và type-check. LimitedDiagnostics lưu tối đa 5 chuỗi, mỗi chuỗi bị cắt về tối đa 160 ký tự nội dung message (không tính prefix kind). Tuy nhiên, compiler vẫn có thể đã dựng thông điệp gốc dài: cap này giới hạn **bộ nhớ trong collection của listener**, không hạn chế hoàn toàn chi phí compiler.

### E. Soft timeout

Giảm WAIT_MILLIS xuống 1 rồi chạy lặp vài lần. Có thể thấy SOFT_TIMEOUT ngay cả với chương trình nhỏ vì khởi tạo compiler cũng tốn thời gian. Đây là lý do phải đo latency và không suy từ "timed out" rằng tác vụ trong JVM đã bị kill. Không biến thử nghiệm này thành bài stress trên máy dùng chung nếu không thể theo dõi worker còn sống.

### F. Cùng source nhưng nhiều job đồng thời

Bắn nhiều yêu cầu cùng lúc qua scheduler có queue. Dù source và output mỗi job vẫn nằm trong quota, CPU/heap/latency tổng có thể tăng rất mạnh. Giới hạn số worker và reject khi hết capacity là điều bắt buộc cho hệ thống multi-tenant.

## 10. Bảng lỗi thường gặp khi thiết kế quota biên dịch

| Triệu chứng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| API hết RAM trước khi compiler bắt đầu | Đọc request thành String rồi mới kiểm tra quá lớn | Quota khi stream/decode và giới hạn tổng số file |
| Source ASCII chạy nhưng tiếng Việt vượt byte limit | Nhầm length() với số byte UTF-8 | Kiểm tra cả UTF-16 length và UTF-8 byte count |
| Bytecode vượt cap dù có kiểm tra sau call() | Đã chứa hết ByteArrayOutputStream trước khi kiểm tra | Chặn từng write trong output stream |
| Hàng trăm class nhỏ làm heap tăng | Chỉ giới hạn byte mà quên giới hạn số class | Cap số file output, metadata và tổng byte |
| Log/diagnostics chiếm bộ nhớ | DiagnosticCollector hoặc Writer/response không giới hạn | Listener và Writer có quota; giới hạn response |
| Future báo timeout nhưng CPU vẫn cao | cancel(true) là ngắt hợp tác, compiler có thể không dừng | Process isolation, kill và cleanup thực sự |
| Gặp timeout nhưng scheduler nhận job mới ngay | Đã thả permit dù worker chưa dừng | Chỉ release capacity sau khi worker/process thực sự kết thúc |
| Compiler đọc dependency host hoặc chạy processor lạ | Dùng mặc định classpath/processor path hoặc options do client điều khiển | Classpath và options do host kiểm soát, -proc:none |
| Bắt lỗi limit rồi trả class output một phần | Stream đã ghi được vài byte trước thất bại | Chỉ phát hành artifact khi toàn bộ task thành công và hợp lệ |
| Sau biên dịch code chạy và truy cập tài nguyên host | Nhầm biên dịch với sandbox thực thi | Thực thi riêng trong môi trường cô lập |

## 11. Checklist áp dụng và tài liệu tham khảo

Trước khi đưa dịch vụ biên dịch trong bộ nhớ vào môi trường có người dùng thật, xác định cụ thể:

- Nguồn đầu vào được giới hạn **ở nơi nhận bytes**, cả số file lẫn tổng kích thước sau decode.
- JavaCompiler nhận compilation units và compiler options do server kiểm soát, có version và classpath cố định, tắt annotation processing trừ khi chủ động cho phép.
- Mọi class output được tính quota **trong quá trình ghi**, có giới hạn số entry và tổng byte; output không chuẩn hoặc artifact lỗi bị loại bỏ.
- Diagnostics, writer text, response size và log đều có giới hạn riêng; thông tin lỗi phải đủ hữu ích nhưng không làm tăng tải vô hạn.
- Timeout được định nghĩa rõ là **soft wait deadline** hay **hard process termination**, và tên trạng thái phản ánh chính xác.
- Worker vẫn đang chạy sau timeout không bị coi như đã giải phóng tài nguyên. Với mã không tin cậy, worker nên nằm trong process/container có giới hạn CPU/RAM/đĩa và cơ chế kill.
- Scheduler áp dụng queue/concurrency/tenant budget, kiểm thử các tình huống SOURCE_LIMIT, OUTPUT_LIMIT, COMPILATION_ERROR, SOFT_TIMEOUT và thất bại của worker.
- Bytecode sau khi biên dịch không được chạy trong cùng host JVM chỉ vì compiler báo OK; thực thi cần chính sách cách ly riêng.

**Tài liệu JDK 17:** [JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html), [JavaFileManager và ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html), [DiagnosticListener](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticListener.html), [Future.cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html), [ExecutorService.shutdownNow](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html) và [Process.waitFor/destroyForcibly](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html).

Kết luận thực hành: **kiểm tra source trước task; chặn output tại file manager; giới hạn diagnostics và text; phân biệt timeout chờ Future với việc thực sự dừng compiler; dùng cô lập tiến trình khi cần cưỡng chế tài nguyên**. Bốn ranh giới này giúp dịch vụ biên dịch trong bộ nhớ có hành vi lỗi đoán trước được và tránh biến một request Java thành nguyên nhân làm quá tải toàn bộ host.