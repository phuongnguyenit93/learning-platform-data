# Kiểm soát thời gian, bộ nhớ và đường ghi khi cung cấp dịch vụ biên dịch Java

## 1. Vì sao dịch vụ biên dịch cần giới hạn tài nguyên?

Dịch vụ biên dịch (compilation service) thường nhận mã nguồn hoặc cấu hình từ một yêu cầu HTTP, hàng đợi hay một công cụ tự động rồi chạy Java compiler để tạo file class, JAR, diagnostics hoặc generated sources. Một job bình thường có thể dùng nhiều CPU, bộ nhớ, dung lượng đĩa và tệp tạm; một job lỗi hoặc cố tình gây tải có thể kéo dài vô hạn, sinh hàng triệu dòng log, tạo tệp ngoài thư mục được cấp hoặc làm nghẽn toàn bộ máy chủ.

**Mục tiêu của bài học:** một compilation job phải có thời hạn, tài nguyên và phạm vi ghi đã định; khi vượt giới hạn, hệ thống phải dừng và dọn tài nguyên, giữ an toàn dữ liệu của những job khác.

Ba trục chính:

1. **Thời gian:** phân biệt thời gian chờ trong queue, thời gian compiler thực thi và thời gian xử lý artifact; có deadline và xử lý timeout.
2. **Bộ nhớ và tài nguyên:** giới hạn heap JVM, bộ nhớ toàn tiến trình/container, CPU, số process/thread, stdout/stderr và disk quota.
3. **Đường ghi:** chỉ cho compiler ghi vào workspace thuộc job; bảo vệ khỏi path traversal, symlink, archive extraction và việc xuất file sang vùng của người dùng/job khác.

Nên thiết kế trên **nguyên tắc ít quyền**: không cho compiler trực tiếp truy cập host filesystem, credentials, Docker socket, mạng hoặc kho artifact dùng chung nếu không thực sự cần. Khi yêu cầu chứa mã nguồn không tin cậy, **tiến trình Java riêng chưa phải là sandbox bảo mật**; cần isolation ở cấp hệ điều hành, container được siết quyền hoặc máy ảo chuyên dụng.

## 2. Threat model: mã nguồn, processor và công cụ build có mức tin cậy khác nhau

Một dịch vụ có thể nhận các loại đầu vào:

| Đầu vào | Rủi ro chính | Chiến lược mặc định |
| --- | --- | --- |
| Tệp .java thuần | Cấu trúc quá lớn, nhiều lỗi và diagnostics, parser/compiler bug, tên tệp bất thường | Kiểm tra kích thước/số lượng; chạy javac trong worker cách ly |
| Annotation processor | Processor là **Java code thực thi ngay lúc compile**, có thể ghi file, mở mạng, lặp vô hạn | Không nạp processor không được phép; tắt xử lý khi không cần bằng -proc:none |
| Compiler plugin hoặc build script | Plugin, Gradle/Maven tasks có thể chạy mã tùy ý | Treat as untrusted executable; sandbox mạnh hơn compile thuần |
| JAR/classpath từ người dùng | Có thể chứa processor/plugin, class bị làm giả hoặc file phình lớn | Resolve dependencies có kiểm soát; cố định hash/version; chặn đường dẫn ngoài vùng cho phép |
| ZIP/TAR source upload | Zip Slip, symlink/hardlink, decompression bomb, nhiều file | Giới hạn kích thước nén và giải nén, kiểm tra path mỗi entry; không tin metadata |
| Tên output hoặc đường dẫn tương đối | ../ traversal, absolute path, tên thiết bị Windows, symlink escape | Không cho client chọn path tuyệt đối; tạo workspace server-side và đối chiếu canonical path |

**Sự khác nhau quan trọng:** Biên dịch một lớp Java thông thường không đồng nghĩa tự động chạy phương thức main() của lớp đó. Tuy nhiên annotation processor, compiler plugin, build plugin và các bước test/generation có thể thực thi ngay trong pipeline. Do đó không thể coi toàn bộ quá trình compile từ nguồn lạ là một phép biến đổi dữ liệu vô hại.

**Java SecurityManager không phải ranh giới an toàn cho dịch vụ biên dịch hiện đại.** Không dựa vào nó để chặn write/network của đoạn mã hoặc processor không tin cậy. Bảo vệ bằng isolation của hệ điều hành, tài khoản không đặc quyền, hạn chế mounts và các bộ giới hạn tài nguyên.

## 3. Mô hình kiến trúc của dịch vụ

~~~text
Client
  |
  v
API: auth, request-size limit, file-count limit, quota
  |
  v
Job queue: số job đang chờ tối đa, deadline và concurrency
  |
  v
Isolated worker / sandbox (mỗi job có job ID riêng)
  |-- /work/input       chỉ đọc
  |-- /work/output      ghi được, giới hạn dung lượng
  |-- /tmp              tạm riêng, giới hạn dung lượng
  |-- compiler JDK      image đã kiểm soát
  |-- CPU/RAM/PID/IO    giới hạn tại OS/container
  |-- watchdog          timeout -> terminate toàn bộ nhóm process
  |
  v
Artifact validation: kiểm tra file, dung lượng, path, tên
  |
  v
Publish artifact: lưu vào kho tin cậy bằng tên do server cấp
  |
  v
Cleanup: xóa workspace/job sandbox và ghi metrics
~~~

Không cho API handler trực tiếp chạy javac đồng bộ trên thread phục vụ HTTP nếu có thể tránh. Thay vào đó, API nhận việc, kiểm tra quota, đưa vào queue; worker dành riêng cho compiler. Các giới hạn quan trọng áp dụng **ngay khi nhận job**, trước khi runner được khởi tạo.

Bảng ví dụ về các ngân sách có thể cấu hình; đây là **số minh họa** để giải thích thiết kế, không phải giới hạn mặc định của Java hoặc Docker:

| Ngân sách | Ví dụ | Ranh giới chịu trách nhiệm |
| --- | --- | --- |
| Request upload | 2 MiB nguồn, tối đa 50 tệp | API / upload validator |
| Hàng đợi | 20 job chờ, tối đa 2 job chạy song song trên một worker host nhỏ | Queue + scheduler |
| Wall-clock compile | 10 giây/job | Watchdog + controller |
| CPU | 1 CPU/job | cgroup/container |
| RAM toàn job | 512 MiB | cgroup/container/VM |
| Heap javac | -J-Xmx128m | JVM của javac; chỉ một phần RAM tổng |
| Process/thread count | 64 PIDs | cgroup/container |
| Artifact/temporary bytes | Output 20 MiB, /tmp 32 MiB | filesystem quota hoặc tmpfs |
| Log trả cho client | 16 KiB được giữ | Output collector; đồng thời vẫn phải drain pipe |

Mức thực tế phụ thuộc số lượng source, annotation processing, thư viện, JDK, tốc độ lưu trữ, mức độ tin cậy và SLO. Không copy bảng này vào production mà không đo benchmark, tỉ lệ lỗi và tải song song.

## 4. Giới hạn thời gian: không nhầm timeout với kill

### 4.1. Những đồng hồ cần theo dõi

- **Queue timeout:** job chờ quá lâu thì bị hủy trước khi tiêu tốn tài nguyên compile.
- **Compilation wall-clock timeout:** thời gian thực kể từ khi compiler bắt đầu, gồm cả chờ IO và tranh chấp tài nguyên.
- **CPU time budget:** tổng thời gian dùng CPU, khác với wall-clock; job có thể dùng ít CPU nhưng treo vì IO.
- **Artifact processing timeout:** thời gian sau compile để đọc, đóng gói và upload artifacts.
- **Overall deadline:** chặn tổng vòng đời job kể cả retry và cleanup.

Ví dụ job được cấp 10 giây compile nhưng đã chờ 30 giây trong queue: timeout compile chưa phản ánh độ trễ người dùng. Tương tự, timeout cho HTTP request chưa có nghĩa tiến trình javac đã dừng — nó có thể tiếp tục chiếm CPU/RAM phía sau.

### 4.2. Java Process API

Khi chạy compiler bằng ProcessBuilder, Java 17 hỗ trợ:

- **process.waitFor(timeout, TimeUnit.SECONDS)**: trả false khi quá thời hạn; phương thức này **không tự hủy process**.
- **process.destroy()**: yêu cầu chấm dứt theo ngữ nghĩa nền tảng.
- **process.destroyForcibly()**: hủy cưỡng bức; lệnh trả về không bảo đảm process đã chấm dứt ngay lập tức, cần chờ/reap.
- **process.toHandle().descendants()**: có thể quan sát các tiến trình con, nhưng snapshot dễ có race nếu cây tiến trình thay đổi.

Đừng chỉ gọi Future.cancel(true) hoặc Thread.interrupt() với compiler chạy trong cùng JVM để kỳ vọng dừng an toàn. Annotation processor hay plugin có thể bỏ qua interrupt và sử dụng toàn bộ bộ nhớ server. Với input không tin cậy, hãy chạy compiler trong **tiến trình riêng bên trong sandbox**, sau timeout hủy **toàn bộ process group/container/VM** và chờ cleanup được xác nhận.

Nếu chỉ kill PID javac mà một processor/plugin đã spawn child process, child có thể còn sống. Trên Linux nên giao vòng đời cho cgroup/container; trên Windows dùng Job Object hoặc cơ chế quản lý process tree tương đương trong worker infrastructure.

### 4.3. Không để stdout/stderr làm treo compiler

Nếu service gọi ProcessBuilder rồi waitFor trước khi đọc stdout/stderr, pipe có thể đầy. Compiler bị chặn khi ghi log, còn parent cứ đợi compiler kết thúc: kết quả là deadlock. Chọn một trong hai cách:

1. Đọc stdout/stderr **đồng thời** với compiler, lưu tối đa N byte nhưng tiếp tục drain phần còn lại.
2. Redirect ra file có quota và reader phù hợp; không chuyển log vô hạn vào memory hoặc disk.

Nếu dùng redirectErrorStream(true), stderr và stdout chung một luồng. Diagnostics cuối có thể bị cắt khi chỉ giữ prefix; nên thêm cờ **truncated=true**, mã lỗi và metadata để người dùng biết log bị giới hạn. Trong production có thể dùng ring buffer giữ cả phần cuối, đồng thời vẫn đặt giới hạn tổng lượng log/IO để tránh abuse.

## 5. Bộ nhớ: heap không phải tổng RAM

**-J-Xmx128m** truyền cờ heap cho JVM chạy lệnh javac launcher. Cờ này giới hạn **Java heap**, không khống chế chính xác toàn bộ memory footprint: còn có native allocations, metaspace, thread stacks, JIT/code cache và mapped files. Compiler chạy qua Java Compiler API **trong cùng JVM** sẽ chia sẻ heap/GC với service; không có per-compilation heap quota đáng tin cậy chỉ nhờ tạo một Thread mới.

Vì vậy cần hai lớp:

- **JVM heap:** ví dụ -J-Xmx128m cho javac dạng process riêng; chọn sau khi benchmark tập nguồn thực.
- **OS/container memory:** ví dụ 512 MiB cho toàn worker job, tính cả compiler và children. Phân biệt memory hard limit với memory reservation (soft limit).

Khi chạm memory limit, runtime/kernel có thể kill process, thường không báo Java OutOfMemoryError như bạn mong đợi. Service cần phân loại **OOM / killed by resource limit / compiler diagnostics / timeout / infrastructure error**. Một exit code khác 0 không đủ để kết luận đó là lỗi syntax Java.

CPU quota (**--cpus**) không phải wall-clock timeout. Một compilation tiêu thụ ít hơn 1 CPU vẫn có thể chạy hàng phút; phải có watchdog riêng. Tương tự, giới hạn số threads/PIDs giảm nguy cơ fork bomb nhưng không thay giới hạn memory, disk hoặc số tác vụ đồng thời.

## 6. Đường ghi: job chỉ sở hữu workspace riêng

Nên cấp cấu trúc cố định cho từng job:

~~~text
/work/jobs/job-opaque-id/
├── input/             chỉ đọc sau bước upload/extract
├── classes/           chỉ ghi .class theo compiler
├── generated/         chỉ ghi source/resource được phép
├── temp/              thư mục tạm riêng
└── result/            staging artifacts trước khi publish
~~~

ID job do server cấp, không dùng raw username, URL hoặc tên archive làm path filesystem. Workspace phải được tạo với permission riêng, owner không đặc quyền, không dùng chung giữa các tenants. Với container, có thể mount input read-only, output writable và root filesystem read-only.

### 6.1. Kiểm tra đường dẫn theo hai tầng

**Tầng 1 — lexical validation:** từ chối path tuyệt đối, ký tự/kiểu path không hợp lệ và các thành phần .. thoát root; resolve + normalize rồi kiểm tra startsWith(root).

~~~java
import java.nio.file.Path;

public static Path lexicalOutputPath(Path root, String relativeName) {
    Path relative = Path.of(relativeName);
    if (relative.isAbsolute()) {
        throw new IllegalArgumentException("Absolute path rejected");
    }
    Path normalizedRoot = root.toAbsolutePath().normalize();
    Path candidate = normalizedRoot.resolve(relative).normalize();
    if (!candidate.startsWith(normalizedRoot)) {
        throw new IllegalArgumentException("Path traversal rejected");
    }
    return candidate;
}
~~~

**Đây chỉ là đoạn phương thức minh họa, chưa phải cơ chế ghi an toàn hoàn chỉnh.** Trên Windows cần xét drive-relative paths, UNC path, separator và reserved device names theo chính filesystem chạy service. Việc startsWith kiểm tra cây path ở mức cú pháp, không chứng minh mục tiêu cuối an toàn nếu path chứa symlink hoặc junction.

**Tầng 2 — filesystem enforcement:** ngăn người yêu cầu tạo/sửa symlink, hardlink hoặc parent directory trong lúc service đang kiểm tra rồi ghi; áp dụng permission và mount sandbox. Với thao tác nhạy cảm, dùng API truy cập dựa trên directory handle (chẳng hạn SecureDirectoryStream nếu filesystem hỗ trợ, hoặc primitive OS tương ứng) để giảm TOCTOU. Đối với file cần tạo mới, dùng ngữ nghĩa CREATE_NEW/NOFOLLOW_LINKS phù hợp và không mở file bất kỳ theo path người dùng khi các ancestor chưa được kiểm soát.

Một quy tắc thực dụng hơn là **không đưa đường dẫn output trực tiếp từ người dùng vào tùy chọn -d/-s**. Server tạo classes/ và generated/ với tên cố định bên trong workspace rồi truyền absolute paths đã kiểm soát cho compiler.

### 6.2. Zip Slip và archive bombs

Nếu client upload ZIP/TAR:

1. Chặn tổng bytes nén khi upload.
2. Chặn tổng bytes giải nén, số lượng entries, độ dài tên và độ sâu thư mục.
3. Kiểm tra mỗi entry trước khi tạo; không nhận absolute path, .. escape, symlink hoặc hardlink không được phép.
4. Không tin entry size trong metadata như bằng chứng cuối cùng; đếm số bytes thực sự giải nén.
5. Extract vào directory riêng có quota; chỉ sau khi kiểm tra xong mới chuyển input sang trạng thái read-only.

Ví dụ ZIP chứa path **../../outside.txt** có thể ghi ra ngoài thư mục đích nếu giải nén ngây thơ. Một archive nén rất nhỏ có thể bung thành dung lượng rất lớn. Cả hai vấn đề cần xử lý trước khi gọi compiler.

### 6.3. Kiểm soát các nơi compiler có thể ghi

Javac có thể ghi class theo **-d**, generated sources theo **-s**, và annotation processors có thể tạo resources thông qua Filer. Compiler/plugin/build tool còn có thể dùng temporary directory, cache và thư mục do script chỉ định.

Do đó:

- Xác định absolute output directories từ server.
- Không cho user gửi trực tiếp các option tùy ý như -d, -s, -J..., -Xplugin, -processorpath hoặc --class-path khi API chỉ hỗ trợ compile thuần.
- Dùng allowlist option và cố định classpath, sourcepath; không ghép args thành chuỗi shell.
- Tắt annotation processing khi không cần bằng **-proc:none**; nếu bắt buộc phải hỗ trợ processor tùy ý thì áp dụng sandbox của mã thực thi không tin cậy.
- Giới hạn tổng bytes, số file và kích thước mỗi file của output.
- Kiểm tra symlink và path của mọi artifact trước khi publish ra nơi lưu trữ chung.
- Không trả trực tiếp absolute host paths hay danh sách tệp nhạy cảm trong diagnostics.

**Lưu ý:** -proc:none chỉ ngăn annotation processing; nó không thay thế sandbox nếu javac có lỗ hổng, nếu service còn chạy bước build/plugin hoặc nếu người dùng được cấp tùy chọn compiler không kiểm soát.

## 7. Ví dụ Java 17 chạy được: deadline, heap và giới hạn log

Bộ ví dụ dưới đây chạy **một lần javac** trên source Java nhỏ được tạo bởi chính chương trình, giữ tối đa 16 KiB compiler output và dùng deadline 10 giây. Nó minh họa cách quản lý process và đường đầu ra do server cấp. **Nó chưa là sandbox bảo mật**: chưa đặt OS/container memory, CPU, disk quotas hoặc isolation cho input không tin cậy.

Lưu file **CompileBoundedDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public final class CompileBoundedDemo {
    private static final int LOG_LIMIT = 16 * 1024;

    private CompileBoundedDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("compile-demo-");
        Path sourceDir = Files.createDirectories(root.resolve("src"));
        Path outputDir = Files.createDirectories(root.resolve("classes"));
        Path emptyClasspath = Files.createDirectories(root.resolve("empty-cp"));
        Path emptySourcepath =
                Files.createDirectories(root.resolve("empty-sourcepath"));

        Path source = sourceDir.resolve("Hello.java");
        Files.writeString(source, """
                public final class Hello {
                    public static void main(String[] args) {
                        System.out.println("Hello from compiled Java");
                    }
                }
                """, StandardCharsets.UTF_8);

        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win");
        Path javac = Path.of(System.getProperty("java.home"), "bin",
                windows ? "javac.exe" : "javac");

        if (!Files.isRegularFile(javac)) {
            throw new IllegalStateException("JDK javac not found: " + javac);
        }

        ProcessBuilder builder = new ProcessBuilder(
                javac.toString(),
                "-J-Xmx128m",
                "-proc:none",
                "--release", "17",
                "-encoding", "UTF-8",
                "-classpath", emptyClasspath.toString(),
                "-sourcepath", emptySourcepath.toString(),
                "-d", outputDir.toString(),
                source.toString());

        builder.directory(root.toFile());
        builder.redirectErrorStream(true);

        Process compiler = builder.start();
        compiler.getOutputStream().close();

        LogDrain drain = new LogDrain(compiler.getInputStream());
        Thread reader = new Thread(drain, "compiler-output");
        reader.setDaemon(true);
        reader.start();

        boolean finished = compiler.waitFor(10, TimeUnit.SECONDS);
        if (!finished) {
            compiler.destroyForcibly();
            if (!compiler.waitFor(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Compiler did not terminate");
            }
        }

        reader.join(2000);
        if (reader.isAlive()) {
            throw new IllegalStateException("Compiler output still open");
        }
        if (drain.failure != null) {
            throw drain.failure;
        }

        String status = !finished ? "TIMEOUT"
                : compiler.exitValue() == 0 ? "SUCCESS" : "COMPILE_ERROR";

        System.out.println("status=" + status);
        System.out.println("classPresent=" + Files.isRegularFile(
                outputDir.resolve("Hello.class")));
        System.out.println("logTruncated=" + drain.truncated);

        if (status.equals("COMPILE_ERROR")) {
            System.out.println(drain.text());
        }
    }

    private static final class LogDrain implements Runnable {
        private final InputStream input;
        private final ByteArrayOutputStream buffer =
                new ByteArrayOutputStream();
        private volatile boolean truncated;
        private volatile IOException failure;

        private LogDrain(InputStream input) {
            this.input = input;
        }

        @Override
        public void run() {
            try (InputStream stream = input) {
                byte[] chunk = new byte[4096];
                int n;
                while ((n = stream.read(chunk)) != -1) {
                    int kept = Math.min(n, LOG_LIMIT - buffer.size());
                    if (kept > 0) {
                        buffer.write(chunk, 0, kept);
                    }
                    if (kept < n) {
                        truncated = true;
                    }
                }
            } catch (IOException ex) {
                failure = ex;
            }
        }

        private String text() {
            return buffer.toString(StandardCharsets.UTF_8);
        }
    }
}
~~~

Chạy trên **JDK 17+**, từ thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 CompileBoundedDemo.java
java CompileBoundedDemo
~~~

Với compiler hoạt động bình thường, stdout chính xác:

~~~text
status=SUCCESS
classPresent=true
logTruncated=false
~~~

**Tại sao các lựa chọn trên có ý nghĩa:**

1. **ProcessBuilder truyền danh sách tham số:** không cần shell, giảm lỗi quote và tránh việc input tùy ý trở thành shell command.
2. **Đường dẫn từ workspace do server tạo:** source, classpath trống, sourcepath trống và output tách biệt; người dùng không quyết định tên host directory.
3. **-proc:none:** vô hiệu hóa annotation processing cho demo compile thuần.
4. **-J-Xmx128m:** hạn chế heap của JVM javac trong demo; **không bảo đảm tổng RAM dưới 128 MiB**.
5. **waitFor(10, SECONDS):** đặt timeout cho process; **destroyForcibly() + waitFor(...)** xử lý quá hạn, nhưng chỉ PID javac, chưa xử lý cây child process.
6. **LogDrain:** đọc pipe trong một thread song song, giữ tối đa 16 KiB trong memory và tiếp tục drain phần còn lại, tránh deadlock do pipe đầy.
7. **Thư mục input/output riêng:** cho phép kiểm chứng Hello.class được compiler tạo ở đúng nơi.
8. **Không gọi java Hello:** ví dụ chỉ compile, không thực thi chương trình do user gửi; nếu dịch vụ có chức năng chạy kết quả, đó phải là một sandbox và ngân sách thực thi độc lập.

Giới hạn của demo: tiến trình kế thừa environment của chương trình gọi, workspace nằm trong temp filesystem mặc định và chưa có quota ở cấp OS. Khi xây production, chuyển compiler vào worker/container/VM được cấu hình chặt, whitelist biến môi trường, hạn chế output IO, kiểm tra artifacts và dọn directory sau khi đóng job.

## 8. Áp dụng giới hạn ở hệ điều hành/container

Ví dụ minh họa trên **Docker Engine/Linux** với một image JDK đã được quản trị, nơi thư mục /work/input và /work/output được mount sẵn từ workspace của job:

~~~bash
docker run --rm \
  --network none \
  --read-only \
  --memory 512m \
  --memory-swap 512m \
  --cpus 1 \
  --pids-limit 64 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --user 10001:10001 \
  --tmpfs /tmp:rw,nosuid,nodev,size=32m,uid=10001,gid=10001 \
  --mount type=bind,src=/srv/jobs/demo/input,dst=/work/input,readonly \
  --mount type=bind,src=/srv/jobs/demo/output,dst=/work/output \
  --workdir /work \
  example-controlled-jdk:21 \
  javac -J-Xmx128m --release 17 -proc:none -encoding UTF-8 \
    -d /work/output /work/input/Hello.java
~~~

**Đây là template vận hành minh họa**, không phải lệnh chạy độc lập: phải có Docker Engine phù hợp, image đã kiểm tra, thư mục /work trong image, hai thư mục host đã được tạo với ownership đúng và file Hello.java hợp lệ. Số giới hạn cần điều chỉnh theo tải. Các tùy chọn được dùng để giải thích:

| Tùy chọn | Ý nghĩa | Điều không giải quyết |
| --- | --- | --- |
| --network none | Không nối vào mạng ngoài theo cấu hình network này | Không phải cơ chế kiểm soát mọi syscall hoặc chứng minh sandbox an toàn tuyệt đối |
| --read-only | Root filesystem read-only | Các mount output/tmpfs vẫn được ghi; cần kiểm soát riêng |
| --memory / --memory-swap | Đặt hard RAM và swap budget theo hỗ trợ kernel | Không thay kiểm soát disk output |
| --cpus 1 | CPU quota tương ứng khoảng 1 CPU | Không phải deadline 10 giây |
| --pids-limit 64 | Giới hạn số process/thread được tính vào cgroup | Không thay memory quota |
| --cap-drop ALL, no-new-privileges | Giảm đặc quyền container | Không thể sửa lỗi thiết kế mount/host |
| --user 10001:10001 | Tránh chạy mặc định với quyền root trong container | Cần bảo đảm UID có thể ghi output hợp lệ |
| --tmpfs /tmp:size=32m | Temp riêng có giới hạn dung lượng | Không giới hạn /work/output khi đó là bind mount |

**Cực kỳ quan trọng:** bind mount output vào đường dẫn host vẫn có thể làm đầy host disk nếu không đặt filesystem quota hoặc giới hạn bytes. --read-only chỉ áp dụng root filesystem container, không tự làm mount output read-only. Không mount Docker daemon socket, host root directory, thư mục credentials hoặc cache dùng chung có quyền ghi.

Container không mặc định là boundary đủ mạnh cho mọi trường hợp multi-tenant và mã độc: phải cân nhắc kernel hardening, seccomp/AppArmor/SELinux, rootless hoặc runtime cách ly, user namespace, ephemeral VM và mức tin cậy của compiler image. Kiểm tra thực tế host cgroup/kernel có hỗ trợ những giới hạn đã cấu hình; không coi cờ được chấp nhận là chứng cứ mọi quota đều đang thực thi đúng.

## 9. Publish artifact an toàn: kiểm tra sau khi compiler kết thúc

Sau khi compiler báo exit code 0, **chưa được tự động tin mọi file trong output**. Một processor hoặc bước build có thể tạo symlink, file khổng lồ, tệp không liên quan hoặc đường dẫn bất thường. Đầu ra nằm trong workspace của job vẫn là **dữ liệu chưa tin cậy** cho đến khi được xác minh.

Một chuỗi xử lý an toàn:

1. Xác nhận job chưa vượt deadline/quota và trạng thái worker còn hợp lệ.
2. Enumerate output theo cách không follow symlink; bác symlink, hardlink nếu chính sách yêu cầu, file đặc biệt và path nằm ngoài root.
3. Giới hạn số file, tổng bytes và từng file; xem xét cả cấp thư mục/depth và tên file.
4. Chỉ chấp nhận loại artifact được API khai báo, ví dụ các file .class hoặc JAR được tạo theo bước đóng gói tin cậy.
5. Copy hoặc stream artifact vào staging **ở khu vực tin cậy**, dùng ID do server cấp; không dùng raw output name làm storage key ngoài namespace.
6. Nếu cần publish nhiều file như một kết quả, áp dụng atomic commit/rename hoặc transaction ở lớp storage phù hợp.
7. Dọn sandbox bằng controller dù job thành công, lỗi, timeout, bị hủy hoặc node gặp sự cố.

Nếu process con còn sống, việc copy file output có thể đọc phải dữ liệu đang thay đổi. Cần xác nhận worker container/process group đã dừng và filesystem output ổn định trước khi publish. Đừng để client tải trực tiếp từ writable working directory của job trong lúc compiler đang chạy.

**Đừng nhầm clean-up với quyền sở hữu:** xóa directory theo job ID chỉ sau khi root path đã được server kiểm tra; không xây lệnh rm -rf từ chuỗi do client cung cấp. Worker quản lý đường dẫn thuộc riêng job, và controller dọn các orphaned jobs sau crash/restart.

## 10. Các trạng thái lỗi phải phân biệt

| Trạng thái dịch vụ | Dấu hiệu | Phản ứng |
| --- | --- | --- |
| SUCCESS | Compiler exit 0, artifact đã được kiểm tra | Publish file hợp lệ và metadata |
| COMPILATION_ERROR | Compiler exit khác 0, có diagnostics Java hợp lệ | Trả diagnostics đã giới hạn và thông tin source |
| TIMEOUT | Deadline hết, process group đã được dừng | Dừng/purge, ghi thời gian, không publish file dang dở |
| MEMORY_LIMIT | Container/cgroup bị OOM hoặc giới hạn memory | Đánh dấu resource failure, không diễn giải thành syntax error |
| OUTPUT_LIMIT | Vượt tổng bytes/file count/log policy | Dừng hoặc không publish theo contract; cleanup |
| INVALID_PATH | Input/output path vi phạm phạm vi | Reject job/entry, ghi audit thích hợp |
| INFRA_FAILURE | Compiler binary không có, file manager hỏng, container start lỗi | Không đổ lỗi cho Java source của người dùng |
| CANCELLED | Người dùng hoặc policy chủ động hủy | Dừng worker và cleanup, không đánh dấu timeout |
| QUEUE_EXPIRED | Job hết thời hạn trước khi chạy | Không tạo compiler process |

Quy định rõ khi một job đồng thời vượt nhiều ngân sách: controller ghi nguyên nhân chính được quan sát và telemetry phụ trợ, tránh phát kết luận chắc chắn nếu chỉ có exit code 137 hoặc log thiếu. Exit code phụ thuộc hệ điều hành và runtime; cần thêm thông tin OOM/cgroup và signal để phân loại đúng.

Đối với HTTP API, các trạng thái trên có thể ánh xạ sang mã lỗi ứng dụng ổn định. Không nhất thiết mỗi compilation error là HTTP 500: source sai cú pháp là một kết quả xử lý yêu cầu bình thường với danh sách diagnostics có giới hạn.

## 11. Kiểm thử giới hạn bằng các tình huống có kiểm soát

| Case | Điều cần tạo hoặc giả lập | Assertion |
| --- | --- | --- |
| Hợp lệ | Một file Hello.java nhỏ | Success, .class trong output của job, không tạo file lạ |
| Timeout | Compiler/helper chủ động chờ vượt deadline trong sandbox thử nghiệm | Status TIMEOUT, PID/container hết sống, không còn artifacts public |
| Heap quá nhỏ | Tập source đủ nặng trong môi trường cô lập | Báo resource failure thích hợp; không ảnh hưởng host |
| Memory vượt cgroup | Worker dùng vượt giới hạn RAM | Job bị chặn/kill, controller phân loại và cleanup |
| Tràn log | Helper phát output vượt 16 KiB | Không deadlock; memory collector giới hạn; truncated true |
| Disk đầy | Output/temp đạt quota | Dừng/thất bại kiểm soát; không ghi sang vùng khác |
| Traversal | ../outside.class hoặc absolute path từ request | Bị reject trước compile; không file ngoài root |
| Symlink escape | Parent/output symlink hướng ra ngoài | Không follow; không có write outside |
| ZIP bomb/Zip Slip | Archive có nhiều entries hoặc path ../ | Reject trong extract; compiler chưa được khởi chạy |
| Hai job cùng lúc | Hai tenants tạo cùng tên Hello.java | Workspaces cách ly, không overwrite |
| Child process còn sống | Plugin/helper spawn child sau đó timeout | Toàn bộ group/container bị dừng |
| Cancel/race | Hủy đúng lúc job chuẩn bị publish | Không publish sau khi cancel, cleanup idempotent |

Chạy các bài test phá quota trong môi trường staging có hạn mức và kiểm soát chủ động. Để kiểm thử deadline, dùng **helper process thử nghiệm** cố ý sleep hoặc block thay vì phụ thuộc compiler thật sẽ treo: phép thử phải xác định được điều kiện bắt đầu và thời điểm vượt ngưỡng. Kiểm tra cả cleanup sau khi worker process chết đột ngột.

Metrics nên ghi: queue_wait_ms, compile_wall_ms, max_rss_bytes hoặc memory peak có thể đo, cpu_time, output_bytes, log_bytes_dropped, process_count_peak, exit_status, cancellation_reason và job_id. Không log toàn bộ mã nguồn, môi trường hoặc credentials khi không có nhu cầu rõ ràng.

## 12. Các sai lầm phổ biến

**Chỉ đặt timeout cho request HTTP.** HTTP có thể kết thúc nhưng javac vẫn chạy. Deadline phải gắn vào vòng đời job và sandbox.

**Chỉ dùng -Xmx.** JVM heap không bao gồm mọi native memory và child process. Cần thêm hard limit ở OS/container.

**Chỉ dùng --cpus rồi kỳ vọng process kết thúc.** CPU quota làm chậm tiêu thụ CPU, không cắt thời gian treo.

**Chỉ đọc log sau waitFor.** Pipe có thể đầy và làm cả parent/child chờ nhau. Dùng reader đồng thời và bound memory/file.

**Kiểm tra path bằng startsWith trên chuỗi.** Ví dụ /work/out2 bắt đầu bằng chuỗi /work/out, nhưng không thuộc directory /work/out. Dùng Path.resolve/normalize/startsWith theo path components, đồng thời xử lý symlink và TOCTOU bằng filesystem boundary.

**Tin rằng output của compiler luôn an toàn.** Processor/plugin có thể tạo file ngoài dự kiến. Kiểm tra artifact trước publish.

**Mount output host mà không quota.** Container root read-only không ngăn bind mount writable làm đầy ổ host.

**Để user chọn compiler flags tùy ý.** User có thể chuyển output path, nạp processor/plugin hoặc tham chiếu filesystem. API compile thuần cần allowlist; tính năng build đầy đủ cần sandbox tương đương chạy mã không tin cậy.

**Chạy compile trong Java web server JVM.** GC, OOM, thread leak hoặc processor vô hạn có thể làm sập API cho mọi tenant. Process riêng và sandbox job giúp có ranh giới dừng/cleanup cụ thể.

**Chỉ kill parent PID.** Các tiến trình con và file descriptor kế thừa có thể sống tiếp; nên quản lý toàn bộ process group/container.

## 13. Checklist thiết kế trước production

- [ ] Có threat model phân biệt Java source thuần, annotation processor, compiler plugin, build script.
- [ ] API kiểm soát kích thước upload, số file, đường dẫn, dependencies, compile flags và queue quota.
- [ ] Mỗi job có worker/workspace riêng, ID do server cấp, không chia sẻ output directory.
- [ ] Có overall deadline, queue deadline, compile timeout và cancellation điều khiển được toàn bộ process tree.
- [ ] Heap, RAM tổng, CPU, PIDs, stdout/stderr, temp và output bytes có ngân sách tách biệt.
- [ ] Input read-only; output và temp writable chỉ bên trong sandbox đã giới hạn.
- [ ] Source/archive paths được kiểm tra traversal, symlink, hardlink và giải nén quá mức.
- [ ] Tắt annotation processing khi không cần; không nhận compiler flags hoặc classpath tùy ý ngoài policy.
- [ ] Không cấp network/host mounts/credentials/Docker socket cho compiler không tin cậy.
- [ ] Không publish artifact trước khi worker dừng, đường dẫn và kích thước đã xác minh.
- [ ] Cleanup xử lý cả success, compile error, timeout, OOM, cancellation và worker crash.
- [ ] Metrics/audit có thể phân biệt lỗi input với lỗi tài nguyên/hạ tầng mà không lộ bí mật.
- [ ] Tests kiểm tra path escape, log flood, disk quota, concurrent isolation và child process còn sót.

## 14. Tài liệu tham khảo

- [Java SE 17 — Process](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html): waitFor, destroyForcibly, descendants và quản lý subprocess.
- [Java SE 17 — ProcessBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html): tạo process, chuyển arguments, directory, environment và streams.
- [Java SE 17 — javac options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): -J, -proc:none, -d, -s, classpath và options.
- [Java SE 17 — Files và Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): filesystem operations, symbolic links và file access.
- [Docker — Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/): memory/CPU constraints và ràng buộc hệ điều hành.
- [Docker — docker container run](https://docs.docker.com/reference/cli/docker/container/run/): --read-only, --pids-limit, --network, --tmpfs, mounts và security options.

**Thông điệp cốt lõi:** giới hạn timeout và -Xmx trong Java chỉ là một phần nhỏ. Một dịch vụ biên dịch đáng tin cần điều phối job, isolation của hệ điều hành, RAM/CPU/disk quotas, kiểm soát đường ghi và kiểm tra artifact như một chuỗi thống nhất, đặc biệt khi đầu vào có thể nạp processor hoặc plugin thực thi mã.