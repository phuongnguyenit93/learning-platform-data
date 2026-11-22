# Đánh giá chi phí khởi động compiler và tái sử dụng tài nguyên có giới hạn

## 1. Vấn đề và mục tiêu

Một lần chạy `javac` không chỉ gồm phân tích mã nguồn và sinh `.class`. Công cụ có thể phải khởi động tiến trình/JVM, nạp compiler, xử lý options, truy cập classpath/module path, đọc JAR, phân giải kiểu, chạy annotation processor và ghi kết quả. Với một lượt compile lớn, phần làm việc trên mã nguồn có thể chiếm phần lớn thời gian; với hàng trăm lượt compile nhỏ, **chi phí khởi động lặp lại** có thể đáng kể.

Do đó hệ thống biên dịch nhiều lần như chấm bài lập trình, công cụ IDE, service biên dịch theo yêu cầu hoặc pipeline xử lý nhiều module thường đặt câu hỏi: gộp nguồn, gọi compiler trong JVM hiện có hay dùng lại tài nguyên để giảm overhead?

Tuy nhiên, giữ tài nguyên quá lâu có thể tăng bộ nhớ, file handles, cache cũ, tranh chấp giữa task và rủi ro từ compiler plugin/annotation processor. Bài toán đúng là **đo chi phí và quyết định vòng đời tái sử dụng có giới hạn**, không giả định “càng giữ lâu càng nhanh”.

Sau bài này, bạn có thể:

- Phân tách chi phí khởi động tiến trình, setup compiler, quét dependency và công việc biên dịch thực tế.
- Dùng `javax.tools.JavaCompiler` và `StandardJavaFileManager` đúng vòng đời để chạy các tác vụ **tuần tự**.
- Đo latency, throughput và bộ nhớ trong các kịch bản cold, warm, in-process và external compiler.
- Thiết kế worker pool, queue, timeout, invalidation và resource budget hữu hạn.
- Nhận biết trường hợp reuse không đem lại lợi ích hoặc làm kết quả compile thiếu cập nhật.

## 2. Các thành phần chi phí cần đo

Có thể dùng mô hình gần đúng:

```text
T_total ≈ T_spawn_JVM
        + T_compiler_setup
        + T_discover_dependencies
        + T_parse_and_type_check
        + T_annotation_processing
        + T_generate_class_files
        + T_file_IO
```

Đây là mô hình phân tích, không phải hợp đồng đo đếm của JDK: các bước có thể trùng lấp và bị ảnh hưởng bởi GC, JIT, OS page cache, ổ đĩa và tải hệ thống.

| Thành phần | Biểu hiện | Cách đánh giá |
| --- | --- | --- |
| Tiến trình/JVM startup | Mỗi lệnh `javac` bên ngoài thông thường tạo một JVM mới | So sánh external process với in-process compilation |
| Compiler/task initialization | Tạo cấu trúc nội bộ, parse options, xác lập context | Đo setup và phần `CompilationTask.call()` riêng |
| Đọc source và dependency | Quét thư mục, đọc metadata/class files từ JAR | Tách tập dependency nhỏ/lớn; đo I/O và cache |
| Annotation processing | Processor quét cấu trúc Java hoặc sinh code | So sánh khi bật processor và khi tắt trong phép đo chẩn đoán |
| Type checking/code generation | Phân giải tên, kiểu, generic, ghi bytecode | Thay đổi số lượng/độ phức tạp nguồn để tìm bottleneck |
| Tài nguyên JVM | GC, heap, metaspace, file handles, CPU | Ghi RSS, GC, CPU và lỗi tài nguyên trong benchmark |

Đừng gọi mọi thời gian `javac` là “startup”. Một project có annotation processor nặng hoặc nhiều generic/dependency có thể mất thời gian ở phân tích kiểu hay I/O ngay cả khi JVM đã khởi động.

## 3. Bốn cách thực hiện nhiều lần compile

### 3.1. Một tiến trình `javac` mới cho mỗi lượt

Ví dụ từ thư mục có hai tệp Java:

```powershell
javac --release 17 -d out src/Alpha.java
javac --release 17 -d out src/Beta.java
```

Mô hình đơn giản, dễ cô lập, dễ buộc deadline ở ranh giới process nhưng lặp chi phí khởi động. Nếu hai nguồn có cùng cấu hình phù hợp, có thể gộp:

```powershell
javac --release 17 -d out src/Alpha.java src/Beta.java
```

Không gộp một cách máy móc nếu các tập nguồn dùng Java release, module path, dependency, annotation processor hoặc biên giới truy cập khác nhau. Gộp sai có thể thay đổi semantics và che lỗi dependency.

### 3.2. JavaCompiler API trong JVM sẵn có

`ToolProvider.getSystemJavaCompiler()` trả về compiler khi runtime hiện tại có công cụ tương ứng. Ứng dụng có thể tạo nhiều `CompilationTask` mà không phải sinh tiến trình `javac` bên ngoài cho mỗi task.

Lợi ích tiềm năng là tránh process/JVM startup lặp lại. Nhưng một `CompilationTask` mới vẫn phải phân tích input và sinh output. Nó không tự động trở thành incremental compiler hoặc build cache.

### 3.3. Tái sử dụng `StandardJavaFileManager`

Tài liệu chính thức JavaCompiler của JDK 21 khuyến nghị mẫu sử dụng cùng standard file manager trong **nhiều lượt biên dịch tuần tự**. Việc này *có thể* giảm chi phí quét filesystem và đọc JAR; tài liệu không hứa mọi workload sẽ nhanh hơn.

Phân biệt:
- **Tạo task mới:** bắt buộc cho mỗi compilation, vì `CompilationTask.call()` chỉ được gọi một lần.
- **Tái sử dụng file manager:** có thể hữu ích ở những lượt tuần tự có classpath/tập tài nguyên ổn định.
- **Đóng file manager:** cần mốc kết thúc rõ để giải phóng tài nguyên; dùng `try-with-resources`.

### 3.4. Worker hoặc daemon dài hạn

Một tiến trình compiler worker có thể phục vụ nhiều request để giảm startup; nhưng phải quản lý số worker, heap/RSS, JAR handles, giới hạn queue, timeout và vòng đời. Daemon của Gradle hay công cụ build có chính sách riêng; không nên mặc định JavaCompiler API tự tạo daemon hoặc bảo đảm thread safety của mọi tài nguyên.

## 4. Ví dụ Java 17+: biên dịch hai lần và tái sử dụng file manager

Tệp **`CompileTwice.java`** dưới đây tạo hai file nguồn thử nghiệm, biên dịch lần lượt bằng **hai task khác nhau**, dùng chung một `StandardJavaFileManager` rồi đóng manager. Ví dụ minh họa hành vi API, **không phải phép đo benchmark**.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileTwice {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        Path src = Files.createDirectories(Path.of("sample-src"));
        Path out = Files.createDirectories(Path.of("sample-out"));

        Files.writeString(
            src.resolve("Alpha.java"),
            "public class Alpha { public static int n() { return 1; } }\n",
            StandardCharsets.UTF_8
        );
        Files.writeString(
            src.resolve("Beta.java"),
            "public class Beta { public static int n() { return 2; } }\n",
            StandardCharsets.UTF_8
        );

        List<String> options = List.of(
            "--release", "17", "-proc:none", "-d", out.toString()
        );

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                    null, Locale.ROOT, StandardCharsets.UTF_8)) {
            for (String name : List.of("Alpha.java", "Beta.java")) {
                Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjectsFromPaths(
                        List.of(src.resolve(name))
                    );

                JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, null, options, null, units
                );

                boolean ok = Boolean.TRUE.equals(task.call());
                System.out.println(name + "=" + ok);
                if (!ok) {
                    throw new IllegalStateException("Compile failed: " + name);
                }
            }
        }

        System.out.println("Alpha.class=" +
            Files.exists(out.resolve("Alpha.class")));
        System.out.println("Beta.class=" +
            Files.exists(out.resolve("Beta.class")));
    }
}
```

Tại thư mục thử nghiệm riêng, có JDK 17 trở lên:

```powershell
javac --release 17 CompileTwice.java
java CompileTwice
```

Khi thư mục có quyền ghi và compiler hoạt động bình thường, stdout dự kiến:

```text
Alpha.java=true
Beta.java=true
Alpha.class=true
Beta.class=true
```

Phân tích các điểm cần nắm:

1. `getSystemJavaCompiler()` có thể trả `null` trong runtime image không chứa compiler, dù `java` vẫn có thể chạy nhiều ứng dụng. Chạy thí nghiệm bằng JDK đầy đủ phù hợp.
2. Hai source tạo ra trong `sample-src`; output ở `sample-out`, tính từ working directory. Chỉ chạy ở thư mục thử nghiệm vì `Files.writeString` sẽ thay nội dung hai tệp cùng tên nếu đã tồn tại.
3. `getStandardFileManager` chạy một lần và được dùng cho hai tác vụ **tuần tự**. `getTask` tạo một task mới ở mỗi vòng; `call()` chỉ chạy một lần trên mỗi task.
4. `-proc:none` tắt annotation processing để thí nghiệm tập trung vào compiler/file manager; không dùng kết quả của thí nghiệm này để suy ra hiệu năng dự án có processors.
5. `try-with-resources` đóng manager ở cuối block; không giữ nó vĩnh viễn chỉ vì có thể cache.
6. Việc nhìn thấy hai file `.class` xác nhận đầu ra ví dụ. Với hệ thống thực, vẫn cần kiểm tra bytecode, classpath và kết quả test để bảo đảm output không cũ hoặc bị nhầm phiên bản.

Mã trên không khẳng định sự khác biệt thời gian. Muốn đo lợi ích reuse, phải chạy thêm phiên bản **manager mới mỗi task** và đối chiếu workload, options, số nguồn, output, môi trường trong cùng một phép đo.

### Không gọi `call()` hai lần

API quy định một `CompilationTask` chỉ được thực hiện một lần. Gọi `task.call()` lần thứ hai trên task cũ gây `IllegalStateException`. Tái sử dụng nên nằm ở tài nguyên được thiết kế để chia sẻ; task là đơn vị công việc một lần.

Nếu thu diagnostics, tạo `DiagnosticCollector` riêng theo từng lượt hoặc có chính sách quản lý rõ. Đừng vô tình trộn warning/error của nhiều request khi đo tỷ lệ compile thất bại.

## 5. Bounded reuse: xác định phạm vi, hạn mức và chủ sở hữu

**Tái sử dụng có giới hạn** nghĩa là mỗi tài nguyên được giữ sống trong một phạm vi đã định, có tiêu chí tiếp tục sử dụng và điểm kết thúc. Những điều cần thiết kế:

| Giới hạn | Câu hỏi cần trả lời | Chính sách minh họa |
| --- | --- | --- |
| Số worker | Bao nhiêu compile được chạy đồng thời? | Pool cố định và bounded queue |
| Thời gian mỗi task | Task được chạy tối đa bao lâu? | Deadline có giám sát; terminate process nếu cần hard timeout |
| Bộ nhớ | Heap, metaspace, RSS, file handles tối đa? | Memory budget và giám sát trước khi nhận task mới |
| Số lượt reuse | Một worker xử lý bao nhiêu task rồi tái tạo? | Max task count/worker age, điều chỉnh bằng đo đạc |
| Freshness | Khi classpath/source/options thay đổi thì sao? | Invalidation hoặc tạo manager/worker mới |
| Cô lập | Ai có quyền đọc/ghi source và output của task? | Directory và process isolation theo request/tenant |

Những giới hạn này là **chính sách thiết kế hệ thống**, không phải thuộc tính có sẵn của mọi JavaCompiler. Không tự đặt giá trị cố định kiểu “10 task chắc chắn tối ưu”: hệ số phù hợp phải đo theo JDK, dependency, kích thước dự án, số core và tài nguyên server.

Có thể dùng luồng xử lý:

```text
Request -> validate -> bounded queue
                          |
                     acquire slot
                          |
                  check input/version
                          |
                  create new task
                          |
                 compile + collect diagnostics
                          |
                release task data
                          |
               check resource budget
                          |
               reuse or close worker
```

Tách trách nhiệm: task chứa đầu vào và diagnostics của **một request**; manager có thể phục vụ nhiều task tuần tự nếu hợp lệ; worker quản lý process/JVM, concurrency, giới hạn và restart. Thời gian chờ trong queue cũng là một phần latency mà người dùng cảm nhận.

## 6. Vì sao cache có thể làm kết quả sai?

Reusing manager không tự đồng nghĩa incremental compilation. Nếu một JAR dưới cùng đường dẫn được thay bằng bản khác, hoặc classpath/annotation processor/options thay đổi, không nên giả định bộ đệm cũ trong mọi implementation tự phát hiện chính xác.

Tình huống cần làm mới manager hoặc worker theo phiên bản input:

- Một dependency JAR đã đổi nội dung hoặc thứ tự classpath thay đổi.
- Source, generated sources hoặc module path thay đổi trong khi compile nhiều lượt.
- Annotation processor/plugin được nâng cấp và có trạng thái nội bộ.
- Task của tenant khác yêu cầu classpath hoặc quyền filesystem khác.
- Output còn `.class` mồ côi sau khi source bị xóa/đổi tên.
- Worker dài hạn tăng RSS, heap, file handles hoặc có dấu hiệu rò rỉ tài nguyên.

**Phân biệt bốn cơ chế**:

| Cơ chế | Tái sử dụng cái gì? | Rủi ro nếu quản lý kém |
| --- | --- | --- |
| Process/JVM reuse | Tiến trình compiler đang sống | Memory, GC, interference, quyền truy cập |
| File manager reuse | File manager qua các compilation tuần tự | Cache/handles và dữ liệu nguồn thay đổi |
| Incremental compilation | Bỏ qua phần nguồn không bị ảnh hưởng dựa vào graph | Thiếu dependency làm bytecode cũ tồn tại |
| Build cache | Artifact đã tạo cho input fingerprint tương ứng | Cache key thiếu input khiến output sai |

Một cơ chế không tự thay thế các cơ chế khác. Ví dụ manager được dùng lại không loại bỏ nhiệm vụ compile lại những client phụ thuộc vào hằng số compile-time đã đổi.

### Quy tắc đóng tài nguyên

`StandardJavaFileManager` có phương thức `close()`; dùng `try-with-resources` trong ví dụ để đóng ở cuối scope. Tài liệu cũng nêu standard manager có khả năng tự mở lại sau `flush`/`close` khi được truy cập; tuy nhiên điều đó không biến `close()` thành biện pháp giải phóng ngay mọi bộ nhớ JVM. GC và implementation quyết định phần còn lại.

Đóng manager và dừng worker khi hết quota; nếu cần đảm bảo không còn handle hoặc cô lập trạng thái, kiểm tra thực tế của implementation và cân nhắc kết thúc tiến trình.

## 7. Tránh chia sẻ compiler state đồng thời không được bảo đảm

Tài liệu `JavaCompiler` khuyến nghị mẫu reuse `StandardJavaFileManager` với **nhiều compilations tuần tự**. Điều này không phải lời bảo đảm rằng dùng chung manager hoặc tất cả thành phần compiler **trong nhiều thread cùng lúc** luôn an toàn.

Với xử lý song song, phương án bảo thủ là mỗi worker có manager/owner riêng và chỉ chạy một task trong phạm vi manager đó tại một thời điểm. Nếu implementation cụ thể quảng bá hỗ trợ concurrency khác, vẫn cần kiểm thử và quản lý state/diagnostics/output riêng.

Tăng số worker từ 1 lên 8 không đảm bảo throughput tăng tám lần: compiler có thể bị giới hạn CPU, I/O, bộ nhớ hoặc GC. Khi tranh tài nguyên, median có thể tốt hơn nhưng p99 tệ hơn. Chọn concurrency bằng benchmark tăng tải dần, theo dõi throughput, p95/p99, RSS và error rate.

**Timeout:** `Future.cancel(true)` hoặc ngắt một thread Java không bảo đảm compiler/processor tùy biến dừng ngay. Nếu hệ thống cần hard deadline, giới hạn CPU/RAM và khả năng dừng chắc chắn, dùng process/container cô lập và cơ chế terminate ở ranh giới tiến trình.

**Bảo mật:** biên dịch nguồn không tin cậy trong JVM ứng dụng chủ không phải sandbox. Annotation processors, compiler plugins và build scripts có thể chạy mã với quyền của tiến trình. Phải đặt chính sách an toàn/giới hạn và isolation phù hợp trước khi nhận nguồn từ bên ngoài.

## 8. Thiết kế benchmark công bằng

Không thể kết luận reuse nhanh hơn nếu hai phương án làm số lượng công việc khác nhau. Một benchmark có giá trị phải so sánh trên **cùng một workload**.

Các kịch bản nên đo riêng:

1. **Cold external `javac`:** khởi động tiến trình mới, compile một tập source được chỉ định.
2. **Repeated external `javac`:** mỗi lượt một process mới, đo nhiều lượt để thấy tác động OS cache.
3. **In-process fresh manager:** một JVM dài hạn nhưng tạo manager mới cho mỗi task.
4. **In-process reused manager:** một JVM dài hạn, manager dùng tuần tự cho nhiều task.
5. **Build tool thật:** pipeline Gradle/Maven/IDE đang sử dụng, gồm worker, incremental hoặc cache.
6. **Tải đồng thời:** nhiều request, queueing, worker scheduling và memory pressure.

Ghi cùng các kết quả: JDK vendor/version, OS, CPU, RAM, ổ đĩa, số source/LOC, số dependency và JAR size, options, annotation processors, heap flags, output policy, số lần warm-up, số mẫu, concurrency và tải nền. Không so số liệu của hai máy/JDK khác nhau như thể chúng là một thí nghiệm kiểm soát.

Cần theo dõi:

- **Latency mỗi task:** wall-clock milliseconds, median/p50, p95 và p99 khi đủ số mẫu.
- **Throughput:** compilations/second ở tải xác định.
- **Startup overhead:** phần tạo process/JVM + init, tách khỏi compiler work khi khả thi.
- **Tài nguyên:** CPU, peak RSS, heap/metaspace, GC pause, open handles.
- **Tính đúng:** tỷ lệ compile thành công, diagnostics, tên/số bytecode và kết quả test.
- **Độ ổn định:** sai số theo lần chạy và tail latency khi tăng tải.

Một phép thử 100 lần liên tiếp trên hệ thống đã ấm không phải đo cold start. Ngược lại, xóa cache hệ điều hành hoặc lặp clean build bằng cách bất nhất giữa các phương án sẽ tạo so sánh thiếu công bằng.

## 9. Đo lượt `javac` bên ngoài trong PowerShell

Sau khi chạy `CompileTwice`, các nguồn `sample-src/Alpha.java` và `sample-src/Beta.java` đã tồn tại. Có thể đo mười lần gọi `javac` **mỗi lần là một process riêng**:

```powershell
New-Item -ItemType Directory -Force external-out | Out-Null

$measurements = foreach ($run in 1..10) {
    $duration = Measure-Command {
        & javac --release 17 -proc:none -d external-out sample-src/Alpha.java sample-src/Beta.java
    }

    if ($LASTEXITCODE -ne 0) {
        throw "javac failed at run $run"
    }

    [pscustomobject]@{
        Run = $run
        Milliseconds = $duration.TotalMilliseconds
    }
}

$measurements | Format-Table
```

**Không có bảng số liệu cố định:** thời gian phụ thuộc máy, JVM, OS cache và tải nền. Lệnh đo gồm chi phí PowerShell gọi tiến trình, khởi động compiler và thực thi việc biên dịch. Nguồn được chỉ định trực tiếp nên compiler được yêu cầu xử lý chúng ở mỗi lượt; tuy nhiên OS file cache vẫn có thể ấm và output đã tồn tại.

Đừng so sánh trực tiếp lệnh này với ví dụ `CompileTwice`, vì ví dụ API chưa đo thời gian và chia compile thành hai task. Muốn so sánh công bằng, phải biên dịch đúng cùng tập nguồn, options, số lượt, output policy; chạy nhiều sample rồi tính phân phối latency.

Nếu muốn đo **clean build**, dọn output *một cách nhất quán* theo cả hai phương án và tách thời gian dọn thư mục khỏi thời gian compiler nếu đó không phải phần muốn đo. Không bao gồm việc xóa file trong phương án A nhưng bỏ qua ở B.

### Đo khoảng `CompilationTask.call()` trong Java

Mã sau là **mảnh chèn vào phương thức có biến `task` đã tạo**, không phải chương trình độc lập:

```java
long startedNanos = System.nanoTime();
boolean success = Boolean.TRUE.equals(task.call());
long elapsedNanos = System.nanoTime() - startedNanos;

if (!success) {
    throw new IllegalStateException("Compilation failed");
}
double elapsedMs = elapsedNanos / 1_000_000.0;
```

`System.nanoTime()` phù hợp để đo khoảng thời gian trong một JVM, không phải timestamp lịch. Đo quanh `task.call()` **không bao gồm** process/JVM startup, tạo compiler/manager/task hoặc queueing trước khi call. Đo ở ranh giới phù hợp với mục tiêu: “compiler execution” khác “API request end-to-end latency”.

Để kiểm định hiệu quả file manager reuse, cần đo setup và call của **cả hai** chiến lược fresh/shared manager, không chỉ thời gian call của riêng một bên.

## 10. Đánh đổi giữa latency và resource budget

Giảm latency không đủ nếu bộ nhớ hoặc độ trễ request khác tăng mạnh:

| Thay đổi | Lợi ích kỳ vọng | Rủi ro / chỉ số cần theo dõi |
| --- | --- | --- |
| Gộp các source tương thích trong một compile | Bớt process startup và phân giải lặp lại | Độ phức tạp/lỗi một phần ảnh hưởng cả batch |
| Dùng JavaCompiler in-process | Giảm startup JVM mỗi lượt | Ảnh hưởng heap, CPU, GC của app chủ |
| Reuse file manager tuần tự | Có thể bớt filesystem/JAR scanning | Handles, freshness, vòng đời và concurrency |
| Giữ worker JVM lâu | Giảm startup qua nhiều request | RSS/GC tăng, tài nguyên mở, trạng thái tích lũy |
| Tăng worker count | Tăng công suất nếu chưa bão hòa | Tranh CPU/I/O/RAM, tăng p95/p99 |
| Giảm concurrency và giới hạn queue | Bảo vệ hệ thống dưới tải | Tăng chờ hoặc từ chối request quá quota |

Chỉ giữ một worker khi workload đủ thường xuyên để lợi ích startup vượt chi phí idle memory. Với lượt compile hiếm, process độc lập có thể rẻ hơn về tổng tài nguyên và dễ phục hồi.

Nếu dùng pool, cân nhắc quota theo số task và thời gian sống, nhưng phải kiểm tra ngưỡng bằng dữ liệu thay vì dùng con số tùy ý. Khi đạt quota, đóng manager/worker và tạo mới; báo metric về lý do recycle để phát hiện memory leak hoặc input invalidation.

## 11. Các tình huống dễ đo sai hoặc triển khai sai

**Dùng một `CompilationTask` cho nhiều lượt.** Không hợp lệ: task gọi `call()` một lần. Tạo mới task.

**Dùng file manager chung trong nhiều thread rồi mặc định thread-safe.** Mẫu chuẩn bảo đảm reuse tuần tự. Phải có ownership/concurrency strategy rõ.

**Giữ manager dù JAR hoặc classpath đổi.** Không giả định bộ đệm luôn phản ánh input mới. Invalidate/recreate có kiểm soát.

**Giữ worker vô hạn để tránh khởi động.** Rủi ro tăng heap, file handles, GC và ảnh hưởng tới ứng dụng chủ.

**Dùng `-proc:none` khi benchmark rồi suy ra production có processor cũng nhanh.** Phải đo workload production, bao gồm processors và generated sources.

**Chỉ nhìn `task.call()` mà gọi đó là “startup latency”.** Startup có thể đã nằm ngoài khoảng đo. Định nghĩa KPI đúng.

**So sánh clean build với warm incremental build.** Hai phương án làm lượng công việc khác nhau; không thể kết luận từ một con số.

**Tăng worker không giới hạn khi queue tăng.** Có thể gây thiếu bộ nhớ hoặc khiến tổng throughput giảm. Dùng queue hữu hạn/backpressure.

**Dùng JavaCompiler in-process làm sandbox cho nguồn không tin cậy.** Không bảo đảm bảo mật; dùng isolation.

**Nhìn output cũ và kết luận compile thành công.** Kiểm tra kết quả `call()`, diagnostics và class files mới. Output mồ côi có thể tồn tại nếu không dọn thư mục thuộc quyền build.

## 12. Quy trình quyết định trong dự án thật

1. **Nêu mục tiêu:** giảm cold start, median latency, p99, hay tăng throughput? Có memory/CPU budget nào?
2. **Ghi baseline:** JDK, lệnh build, số source, dependency, processor, trạng thái cache, metric thời gian và bộ nhớ.
3. **Tìm bottleneck:** spawn/JVM, dependency scanning, processing, parse/type check, I/O hay queue?
4. **Thử thay đổi ít rủi ro trước:** loại compile dư, chia module hợp lý, gộp nguồn tương thích, sửa dependency graph và incremental cache.
5. **Nếu cần in-process compile:** thiết lập task mới mỗi lần, cân nhắc reuse file manager tuần tự, chính sách close/invalidation.
6. **Nếu cần worker pool:** bounded queue, concurrency, resource limit, deadline và restart lifecycle.
7. **Benchmark lại công bằng:** giữ input và compile semantics, đo cả memory/tail latency và số lỗi.
8. **Xác minh tính đúng:** diagnostics, bytecode, classpath, test trên artifact sinh thực tế.
9. **Giám sát sau triển khai:** RSS/GC, handle count, p95/p99, queue depth, timeout và compile failures.

### Khi nào nên ưu tiên cách nào?

- Ít lần compile, latency không quan trọng, cần cô lập: **process `javac` riêng** thường đơn giản.
- Nhiều lần compile nhỏ **tuần tự** với dependency tương đối ổn định: thử **JavaCompiler API + file manager reuse** và đo.
- Build lớn, nhiều module: kiểm tra **incremental compilation và build cache** của công cụ đang dùng trước.
- Tải đồng thời và cần hạn mức nghiêm ngặt: cân nhắc **pool worker cô lập**, không chia sẻ mutable compiler state tùy tiện.
- Compile nguồn không tin cậy: chọn ranh giới **process/container isolation** và giới hạn tài nguyên phù hợp.
- Reuse không cải thiện số liệu hoặc làm memory tăng: giữ phương án đơn giản hơn và tìm bottleneck khác.

## 13. Câu hỏi tự kiểm tra

**1. Vì sao hai lệnh `javac` nhỏ có thể tốn hơn một lệnh gộp?**  
Vì có thể lặp quá trình tạo tiến trình/JVM và setup compiler, ngoài phần xử lý từng source. Chỉ gộp khi cấu hình compile tương thích.

**2. Loại tài nguyên nào được JavaCompiler API nêu rõ là có thể dùng giữa các compilation tuần tự?**  
`StandardJavaFileManager`; reuse có thể giúp giảm scanning/JAR I/O, nhưng không có cam kết tốc độ cho mọi workload.

**3. Gọi lại `task.call()` được không?**  
Không. Mỗi `CompilationTask` chỉ thực hiện một lần. Lượt tiếp theo cần task mới.

**4. Vì sao file manager reuse không thay thế incremental compilation?**  
Nó quản lý truy cập file/JAR; không tự xác định đầy đủ những source cần biên dịch lại theo dependency graph.

**5. Tại sao cần đo RSS và p99 khi tăng worker?**  
Một phương án có thể tăng throughput trung bình nhưng dùng quá nhiều bộ nhớ hoặc làm tail latency xấu hơn.

**6. `Future.cancel(true)` có bảo đảm compiler dừng ngay không?**  
Không. Interrupt không phải hard timeout, đặc biệt khi processor/plugin tùy biến không phối hợp; có thể cần terminate process cô lập.

**7. Một kết quả “reuse nhanh gấp đôi” có đáng tin nếu phương án reuse biên dịch một file, còn external `javac` biên dịch hai file?**  
Không. Benchmark phải giữ số lượng công việc và cấu hình tương đương.

## 14. Checklist trước khi áp dụng

- [ ] Phân biệt startup với parsing/type checking/annotation processing/I/O.
- [ ] Có workload đại diện và các thông số JDK, classpath, options, nguồn, output rõ ràng.
- [ ] Đo cold và warm riêng, có warm-up và số mẫu phù hợp.
- [ ] Tạo `CompilationTask` mới cho mỗi lượt; `call()` đúng một lần.
- [ ] Nếu reuse `StandardJavaFileManager`: tuần tự, owner rõ, input ổn định và đóng theo vòng đời.
- [ ] Có invalidation/restart khi dependency, source, processor hoặc options thay đổi.
- [ ] Có giới hạn số worker, queue, deadline, heap/RSS và handles.
- [ ] Đo latency, throughput, p95/p99, memory, error rate; không chỉ chọn con số nhanh nhất.
- [ ] Kiểm tra compiler diagnostics, bytecode đầu ra và test trên artifact mới.
- [ ] Không coi biên dịch in-process là vùng cách ly an toàn với mã không tin cậy.

**Ghi nhớ:** Tái sử dụng tài nguyên compiler là một tối ưu có điều kiện. Chỉ giữ sống những tài nguyên có hợp đồng reuse rõ ràng, có kiểm soát vòng đời, giới hạn tài nguyên và bằng chứng benchmark trên workload thật.

## Tài liệu tham khảo

- [Java SE 21 — JavaCompiler API](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Java SE 21 — JavaCompiler.CompilationTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html)
- [Java SE 21 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html)
- [Java SE 21 — ToolProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ToolProvider.html)
- [Java SE 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
