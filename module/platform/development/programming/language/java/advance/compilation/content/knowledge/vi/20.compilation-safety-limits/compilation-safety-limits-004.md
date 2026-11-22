# Cô lập nguồn không tin cậy, quyền tệp và tài nguyên tiến trình khi biên dịch Java

## 1. Vì sao đây là một vấn đề của hệ thống biên dịch?

Dịch vụ chấm bài Java, trình biên tập trực tuyến, hệ thống phân tích mã hoặc công cụ nhận repository do người dùng gửi đều phải xử lý **source code không tin cậy**. Công việc có thể gồm giải nén source, chạy `javac`, thực thi annotation processor, nạp class và chạy chương trình để kiểm thử. Những bước này có mức rủi ro khác nhau nhưng cùng đòi hỏi kiểm soát quyền và tài nguyên.

Một chương trình nộp có thể cố tình hoặc vô tình:

- Tiêu tốn CPU bằng vòng lặp, generic/type graph phức tạp hoặc tạo số lượng lớn thread.
- Cấp phát RAM, native memory và bộ đệm quá mức; khiến JVM hoặc host bị thiếu bộ nhớ.
- Ghi hàng GB log, sinh vô số file tạm, làm đầy inode hoặc disk.
- Đọc file nội bộ, credentials, source của bài nộp khác; kết nối mạng để chuyển dữ liệu.
- Tạo tiến trình con tồn tại sau khi tiến trình chính bị hủy.
- Chèn đường dẫn `../`, symlink hoặc entry ZIP lạ để thoát khỏi thư mục bài nộp.
- Cung cấp annotation processor, plugin hoặc build script có khả năng **chạy code ngay trong quá trình biên dịch**.

**Biên dịch thành công không chứng minh mã an toàn.** Compiler kiểm tra tính hợp lệ theo ngôn ngữ và cấu hình, không phải một công cụ chứng nhận hành vi runtime. Ngược lại, chỉ chưa gọi `main()` cũng không có nghĩa mọi thao tác trong compilation đều không thực thi code.

Mục tiêu bài học là thiết kế **ranh giới an toàn của compile/run worker**, với quyền tệp tối thiểu, quota tài nguyên, quản lý tiến trình và trạng thái lỗi chính xác.

## 2. Mô hình ranh giới tin cậy

```text
 Client / Upload source / ZIP (UNTRUSTED)
                     |
                     v
       Control plane đáng tin cậy
       - admission limits, validation
       - tạo workspace độc lập
       - chọn JDK, classpath, compiler flags
       - quản lý thời gian và tài nguyên
                     |
                     v
         Isolated compile worker
           javac / compiler API
                     |
                     v
          Isolated run worker
              java / tests
                     |
                     v
          Bounded result collector
                     |
                     v
        Cleanup worker + workspace
```

**Control plane** quyết định chính sách, phân bổ quota và theo dõi job. **Execution plane** là các tiến trình trực tiếp xử lý source và bytecode của bài nộp. Execution plane cần ít quyền hơn, chỉ thấy dữ liệu cần cho job.

| Đối tượng | Độ tin cậy | Chính sách hợp lý |
|---|---|---|
| Source, tên file, ZIP entries | Không tin cậy | Giới hạn kích thước, số lượng, kiểm tra path |
| Compiler/JDK và flags | Do hệ thống chọn | Không nhận tùy ý từ chuỗi người dùng |
| Dependencies/JAR do người dùng tải | Không tin cậy | Allowlist hoặc worker cô lập mạnh |
| Annotation processor/plugin | Có thể chạy mã khi compile | Tắt nếu không cần; không nạp trong server JVM |
| Bytecode sinh ra | Không tin cậy | Chỉ chạy trong sandbox |
| Test harness và expected output | Đáng tin hơn mã nộp | Read-only và tách khỏi user code |
| Secrets, token, home của server | Nhạy cảm | Không cấp cho worker |
| Stdout/stderr, output artifacts | Không tin cậy | Giới hạn và escape khi hiển thị |

Một kiến trúc có hai worker compile và run tách biệt là hữu ích khi muốn cấp quyền khác nhau: compiler cần đọc source và ghi class; runner chỉ cần đọc class/test input, ghi kết quả trong vùng scratch. Có thể triển khai cùng một sandbox với các phase được kiểm soát hoặc hai sandbox riêng tùy threat model. Với workload đối kháng, nên ưu tiên **môi trường mới theo job**, tránh chia sẻ bộ nhớ hoặc filesystem giữa tenants.

## 3. Tại sao không dùng chính JVM của server làm sandbox?

Ví dụ một API Spring Boot gọi `ToolProvider.getSystemJavaCompiler()` trực tiếp trong cùng JVM. Dù người dùng chưa chạy class nộp, một số tình huống nguy hiểm vẫn có thể xảy ra:

1. Compiler dùng CPU/RAM của server và có thể gây mất ổn định dịch vụ.
2. Compiler có quyền filesystem/network tương ứng với process server.
3. Annotation processor hoặc compiler plugin được cấu hình có thể thực thi mã ở lúc compile.
4. Nếu sau đó nạp class bằng reflection, `URLClassLoader` hoặc JShell, mã nộp chạy trong JVM có quyền của server.

`ClassLoader` quản lý namespace/nạp lớp, **không** đặt CPU quota, giới hạn RAM, quyền OS hay network boundary. `ThreadGroup` cũng không tạo sandbox. `try/catch` không chặn được mọi sự cố gây cạn tài nguyên.

### 3.1. Security Manager đã bị vô hiệu hóa

`SecurityManager` được đánh dấu deprecated for removal từ Java 17 (JEP 411), và **bị vô hiệu hóa vĩnh viễn từ JDK 24** (JEP 486). Trên JDK 24+, không thể bật nó để hạn chế code nộp. Ngay cả trên JDK cũ, cơ chế này không bảo vệ tuyệt đối trước lỗi runtime, native code hay mọi kênh tấn công.

Mô hình hiện đại đặt isolation **bên ngoài JVM** bằng OS process identities, container namespaces/cgroups, policies, VM/microVM khi cần. Oracle Java Security Guide cũng hướng tới các cơ chế ngoài JDK cho tình huống này.

**Một tiến trình riêng chưa đủ:** Nếu child vẫn chạy cùng tài khoản OS, cùng home, cùng network và có thể đọc secrets của server, child vẫn có quyền tương đương trên những tài nguyên đó. Phải kết hợp tiến trình riêng với **least privilege** và quota cứng ở hệ điều hành/container/VM.

## 4. Phân biệt compile và run

| Điều cần kiểm soát | Compile phase | Run phase |
|---|---|---|
| Chương trình được phép khởi chạy | `javac` / compiler tin cậy | `java` / test runner tin cậy |
| Input | Các `.java` đã kiểm tra, dependency cho phép | Class đã build và test input |
| Output | `.class`, generated source, diagnostics | Stdout, stderr, test result |
| Annotation processors | Tắt nếu không cần hoặc allowlist rõ | Không tự kích hoạt trừ khi chạy compilation khác |
| Quyền ghi | Chỉ output/scratch của compile job | Chỉ scratch/log của runtime job |
| Quyền đọc | Source và dependencies được phép | Class và test cases được phép |
| Network | Không có theo mặc định | Không có theo mặc định |
| Quota | CPU, RAM, disk, timeout riêng | CPU, RAM, PIDs, timeout, output riêng |

Compile worker cũng có thể bị tấn công bằng input phức tạp, compiler bug, build script hoặc annotation processors; vì vậy nó vẫn cần isolation. Runtime worker còn phải xử lý vòng lặp vô hạn, socket, fork, đọc file và native access.

Không thực thi mã nộp khi nghiệp vụ chỉ yêu cầu kiểm tra lỗi compiler. Ngay cả khi có yêu cầu chạy, phải có điều kiện admission và worker đã được cấp quyền giới hạn.

## 5. Hạn chế annotation processor và build script

Annotation processor là mã Java chạy **trong quá trình biên dịch**, chứ không phải một bước kiểm tra cú pháp thụ động. Nếu cho JAR của người nộp vào processor path, processor có thể đọc/ghi theo quyền process `javac`. Cơ chế khám phá processor tùy phiên bản JDK và cách cấu hình; không nên dựa vào mặc định ngầm định để bảo vệ hệ thống.

Với bài tập không cần sinh mã, trên JDK 17 có thể:

```bash
javac -proc:none -d classes src/Main.java
```

`-proc:none` tắt annotation processing của `javac`. Tuy nhiên:

- Lệnh này **không tạo sandbox**, vẫn phải chạy `javac` trong worker có quota.
- Một số code thực sự cần Lombok, MapStruct hoặc processor khác để compile; nếu bài tập cho phép, phải có policy processor được chấp thuận và worker cô lập.
- Nếu người dùng cung cấp Gradle/Maven scripts hoặc compiler plugins, quá trình build có thể thực thi logic tùy ý. Phải coi **chạy build script là thực thi mã không tin cậy**.
- Các flags như `-processorpath`, `-Xplugin`, `-d`, `-s`, `-J...`, classpath/module-path cần do server kiểm soát; không cho người dùng tự cấu hình toàn bộ.

Dịch vụ chỉ chấm bài `.java` thường an toàn và dễ tái lập hơn khi chính server tạo lệnh compile, cài sẵn JDK và thư viện allowlist. Dịch vụ build cả repository từ internet cần threat model nghiêm ngặt hơn.

## 6. Thiết kế workspace và quyền tệp tối thiểu

Ví dụ cấu trúc **logic** của một job:

```text
sandbox/jobs/<random-job-id>/
├── input/        # file đã validate, chỉ đọc trong worker
├── deps/         # dependencies được allowlist, chỉ đọc
├── classes/      # class output có quota
├── scratch/      # file tạm có quota
├── logs/         # stdout/stderr có giới hạn
└── result.json   # kết quả được xác thực trước khi trả
```

Tên `<random-job-id>` minh họa định danh được server sinh; không ghép trực tiếp username hay tên do người dùng nhập thành thư mục host.

Nguyên tắc:

1. **Mỗi job có filesystem riêng**; tránh cho hai tenant cùng quyền ghi vào thư mục này.
2. **Input read-only**, output/scratch là nơi ghi duy nhất mà worker được cấp.
3. Không mount host `/home`, mã nguồn backend, SSH keys, cloud credentials, metadata endpoint hay container runtime socket vào worker.
4. Worker chạy dưới **OS identity không đặc quyền**; không dùng root/administrator nếu không thật sự cần.
5. Đặt **disk quota và inode/file count limit**, không chỉ giới hạn số byte upload.
6. Kiểm soát quyền đọc của artifact tải xuống bằng identity của job/tenant, không cho user chọn absolute path.
7. Cleanup cả khi timeout, crash, cancellation hoặc node mất kết nối.

Trên POSIX, thư mục riêng có quyền tương đương `0700`, file nhạy cảm tương đương `0600` là một điểm khởi đầu. Trên Windows phải dùng NTFS ACL và process token phù hợp; `PosixFilePermissions` không hoạt động trên mọi filesystem.

`Files.createTempDirectory` giúp tạo tên duy nhất nhưng **không tự chứng minh** quyền OS, ACL, symlink safety, quota và isolation. Các yêu cầu này cần kiểm tra trên môi trường thực.

## 7. Đường dẫn từ upload: traversal, ZIP bomb và symbolic link

Một ZIP có thể chứa:

```text
src/Main.java
../../config/secrets.yml
/absolute/path.txt
link-to-outside/escape.java
```

Không được áp dụng trực tiếp tên entry vào đường dẫn filesystem:

```java
// Anti-pattern: fragment minh họa, không dùng để giải nén.
Path destination = workspace.resolve(userSuppliedEntryName);
Files.copy(uploadStream, destination);
```

Chuỗi `../` có thể thoát root. Đường dẫn tuyệt đối có thể trỏ nơi khác. Symlink có thể nằm **bên trong** workspace nhưng trỏ ra ngoài.

### 7.1. Java 17: ví dụ validation đường dẫn ở mức từ vựng

**Tệp `PathBoundaryDemo.java`, chạy độc lập:**

```java
import java.nio.file.Path;

public class PathBoundaryDemo {
    static Path lexicalDestination(Path root, String input) {
        Path candidate = root.resolve(input).normalize();
        if (!candidate.startsWith(root) || candidate.equals(root)) {
            throw new IllegalArgumentException("Outside workspace");
        }
        return candidate;
    }

    public static void main(String[] args) {
        Path root = Path.of("job-space").toAbsolutePath().normalize();

        System.out.println(
                lexicalDestination(root, "src/Main.java").startsWith(root));

        try {
            lexicalDestination(root, "../secret.txt");
            System.out.println("unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("traversal rejected");
        }
    }
}
```

Chạy:

```bash
javac PathBoundaryDemo.java
java PathBoundaryDemo
```

**Stdout:**

```text
true
traversal rejected
```

Ví dụ chỉ **tính toán path, không ghi file**. `normalize()` và `startsWith()` chỉ kiểm tra path ở mức từ vựng; **không đủ bảo vệ trước symlink hoặc TOCTOU**. Chẳng hạn `root/link/file.java` có thể vượt root nếu `link` là symlink trỏ ra ngoài. Trong môi trường có actor khác thay đổi filesystem đồng thời, việc check path trước rồi mở file sau cũng có race.

### 7.2. Quy tắc cho xử lý archive

- Giới hạn kích thước tệp upload, tổng kích thước **sau giải nén**, số entry, độ sâu thư mục, độ dài tên và tổng số file để giảm ZIP bomb.
- Từ chối entry tuyệt đối, `..`, tệp không hợp lệ, symlink/hardlink không cần thiết, tên trùng sau normalize và đường dẫn quá dài.
- Chỉ cho phép loại tệp cần cho tác vụ; không tin extension hay MIME do client tự khai.
- Không follow symlink khi tạo file hoặc cleanup; nếu cần thao tác trong directory có đối thủ đồng thời, dùng primitive an toàn thích hợp như handle-relative/no-follow hoặc `SecureDirectoryStream` khi được filesystem hỗ trợ.
- Tách filesystem worker khỏi host secrets và đặt quyền ghi chỉ trong mount riêng; đây là tuyến phòng thủ thứ hai nếu validation có bug.
- Không ghi đè file có sẵn do job khác tạo. Tạo workspace sạch, riêng biệt và kiểm chứng quyền sở hữu trước khi ghi.

`Path.normalize().startsWith(root)` là bước đầu để loại bỏ traversal phổ biến, không phải **security boundary duy nhất**.

## 8. Quota cần thiết: CPU, RAM, thời gian, PIDs, disk và output

| Tài nguyên | Ví dụ làm cạn | Biện pháp |
|---|---|---|
| CPU | Vòng lặp bận; compile generic phức tạp | CPU quota cgroup/VM/OS |
| Wall-clock | `sleep()`, deadlock, chờ input | Deadline do supervisor bên ngoài áp dụng |
| RAM | Object allocation, compiler heap, native memory | Memory limit ở container/VM |
| Threads/PIDs | Tạo nhiều thread, fork process con | PID/task quota toàn nhóm |
| Disk | Ghi file vô hạn hoặc nhiều output classes | Scratch volume quota / size cap |
| File count/inodes | Tạo hàng triệu tệp nhỏ | Inode/file-count limits |
| Stdout/stderr | In không ngừng | Byte cap và cancel/discard policy |
| File descriptors | Mở nhiều file/socket | OS resource limit |
| Network | Exfiltration, scan nội bộ | Disable hoặc deny-by-default policy |
| Độ đồng thời | Hàng nghìn job chạy cùng lúc | Admission control, per-tenant quotas |

**`-Xmx256m` không phải hard RAM limit cho cả job**. Nó chỉ giới hạn Java heap của một JVM; native allocations, threads, metaspace, direct buffers, child processes và compiler có thể dùng thêm RAM. Tương tự, `-XX:ActiveProcessorCount=1` không phải CPU quota cứng. Các JVM flags có thể bổ trợ nhưng không thay thế giới hạn OS/container.

**Timeout wall-clock khác CPU quota:** một task ngủ trong một giờ không dùng nhiều CPU nhưng phải bị hủy khi quá deadline; một task tạo nhiều thread có thể dùng gần hết CPU trước thời hạn. Cần **cả hai**, cộng với giới hạn độ đồng thời ở hệ thống.

## 9. ProcessBuilder: quản lý vòng đời, không phải sandbox

`ProcessBuilder` cho phép khởi tạo child process với **argv dạng danh sách**. Điều này giúp tránh shell expansion khi không chạy qua `sh -c`/`cmd /c`, nhưng process mới vẫn có quyền của OS user khởi chạy trừ khi đã được sandbox bên ngoài.

### 9.1. Ví dụ Java 17 hoàn chỉnh với child tin cậy

Ví dụ sau chỉ chạy một child class **cố định** do chúng ta định nghĩa. Nó minh họa timeout, exit code, log redirect và cleanup. **Không thay Child bằng mã nộp từ internet trên host.**

**Tệp `ProcessLifecycleDemo.java`:**

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public class ProcessLifecycleDemo {
    public static final class Child {
        public static void main(String[] args) {
            System.out.println("child-ok");
        }
    }

    public static void main(String[] args) throws Exception {
        boolean windows = System.getProperty("os.name")
                .toLowerCase().contains("win");
        Path javaBin = Path.of(
                System.getProperty("java.home"),
                "bin",
                windows ? "java.exe" : "java");

        Path log = Files.createTempFile("child-log-", ".txt");
        try {
            ProcessBuilder pb = new ProcessBuilder(
                    javaBin.toString(),
                    "-cp",
                    System.getProperty("java.class.path"),
                    Child.class.getName());
            pb.redirectErrorStream(true);
            pb.redirectOutput(log.toFile());

            Process child = pb.start();
            boolean finished = child.waitFor(3, TimeUnit.SECONDS);
            if (!finished) {
                child.destroyForcibly();
                child.waitFor();
                throw new IllegalStateException("Timed out");
            }
            if (child.exitValue() != 0) {
                throw new IllegalStateException(
                        "Failed with exit " + child.exitValue());
            }
            System.out.println("finished: " + finished);
            System.out.println("output: " + Files.readString(log).strip());
        } finally {
            Files.deleteIfExists(log);
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac ProcessLifecycleDemo.java
java ProcessLifecycleDemo
```

**Stdout mong đợi:**

```text
finished: true
output: child-ok
```

Giải thích:

- `java.home/bin/java` chọn executable theo JVM đang chạy thay vì phụ thuộc PATH.
- `ProcessBuilder` không gọi shell; mỗi argument được truyền riêng.
- `redirectErrorStream(true)` gộp stderr vào stdout, còn `redirectOutput(log.toFile())` tránh kẹt do pipe không được đọc trong ví dụ nhỏ.
- `waitFor(timeout, TimeUnit.SECONDS)` áp deadline wall-clock cho child process.
- `destroyForcibly()` yêu cầu hủy child khi quá hạn, rồi `waitFor()` đợi kết thúc trước khi dọn log.
- Exit code chỉ được truy cập khi child đã dừng.
- `finally` dọn file log nếu parent chạy đến block này.

**Giới hạn phải hiểu:** Log trong ví dụ không có size cap; nếu child in liên tục, file có thể rất lớn trước timeout. `destroyForcibly()` cũng **không đảm bảo** mọi descendant process của child bị hủy. Ví dụ phù hợp để học Java process lifecycle trên **code tin cậy**, chưa phải bộ chạy mã không tin cậy an toàn.

### 9.2. Trong production cần bổ sung gì?

1. Spawn child bên trong worker có OS identity, filesystem, network và quota đã hạn chế.
2. Quản lý toàn **process group/cgroup/container/Windows Job Object**, hủy cả descendants khi timeout.
3. Giới hạn byte output bằng collector hoặc filesystem quota, không chỉ cắt chuỗi HTTP response.
4. Thu log có kiểm soát, phân biệt compiler stderr với child output khi cần.
5. Gắn mỗi process với job ID nội bộ, không tin tên process hoặc pid do người dùng gửi.
6. Cleanup khi parent mất kết nối/crash; không thể chỉ dựa vào `finally` ở bên trong process bị kill.

`ProcessHandle.descendants()` cho phép quan sát descendants, nhưng cây process thay đổi liên tục; chỉ quét rồi hủy lần lượt có race. Supervisor gắn quyền quản lý với cả nhóm process sẽ đáng tin hơn.

## 10. Deadlock và tràn bộ nhớ từ stdout/stderr

Với `ProcessBuilder`, stdout và stderr mặc định là **pipe**. Nếu child in nhiều nhưng parent gọi `waitFor()` mà không đọc, pipe có thể đầy. Child chặn ở thao tác ghi, parent chờ child: deadlock.

Có những chiến lược:

- **Redirect logs ra file có quota:** dễ kiểm tra nhưng cần cap số byte và ACL.
- **Đọc đồng thời cả hai streams:** reader/collector phải áp byte cap, có thể tiếp tục đọc và bỏ phần dư hoặc hủy worker. Chỉ ngừng đọc khi đầy buffer có thể làm child block.
- **Merge stderr/stdout:** dễ thu một stream nhưng mất phân biệt hai kênh; dùng khi nghiệp vụ không cần tách.
- **Bounded streaming:** chuyển chunks qua queue giới hạn; cần backpressure và cancellation.

Đừng giữ toàn bộ output vào `ByteArrayOutputStream` hoặc `StringBuilder` vô hạn. Cũng đừng chỉ trả 16 KiB đầu trong response khi child vẫn đang ghi file không giới hạn.

**Stdout/stderr là dữ liệu không tin cậy**: có thể chứa HTML/JS, terminal control characters, JSON giả mạo kết quả, hoặc chuỗi cực dài. UI phải escape theo ngữ cảnh, server phải giới hạn kích thước và không coi chuỗi `PASS` do code nộp tự in là phán quyết test.

## 11. Cô lập bằng container/VM: các lớp bảo vệ

Container runtime hoặc VM phải được cấu hình để thực thi chính sách an toàn của job:

| Lớp | Điều cần áp dụng |
|---|---|
| User identity | Không đặc quyền, UID/GID riêng hoặc user namespace phù hợp |
| Root filesystem | Read-only nếu có thể, chỉ mount input/deps cần thiết |
| Scratch/output | Writable volume riêng, quota bytes/inodes |
| Network | Disabled hoặc allowlist thực sự cần |
| CPU/RAM/PIDs | Hard limits, không chỉ JVM flags |
| Capabilities | Drop không cần thiết, no-new-privileges |
| Syscalls | Seccomp/AppArmor/SELinux phù hợp nền tảng |
| Lifecycle | Job mới, teardown toàn worker/process group |
| Tenant separation | Không chia sẻ workspace/secrets/socket |

**Container không tự động có nghĩa là an toàn tuyệt đối.** Privileged container, mount Docker socket, host network, host paths có secret hoặc quyền kernel rộng sẽ làm giảm đáng kể isolation. Với mã có chủ đích đối kháng mạnh, xem xét VM/microVM để giảm phụ thuộc vào một kernel được dùng chung.

### 11.1. Ví dụ chính sách ở mức logic

```yaml
# Đây là policy minh họa, KHÔNG phải manifest Kubernetes/Docker đầy đủ.
submission:
  maxFiles: 20
  maxSourceBytes: 100000
  maxUncompressedBytes: 500000

compile:
  wallClockSeconds: 15
  memoryMiB: 512
  cpuCoresQuota: 1
  maxLogBytes: 65536

run:
  wallClockSeconds: 3
  memoryMiB: 256
  maxProcesses: 32
  maxLogBytes: 16384
  network: disabled
```

Các con số chỉ minh họa, không phải mức khuyến nghị áp dụng mọi sản phẩm. Bài tập phức tạp, số lượng source lớn hoặc annotation processing được cho phép có thể đòi quota khác. Quan trọng là worker/supervisor **enforce** những giới hạn đó và có trạng thái báo khi chúng bị vượt.

Một policy chỉ ghi trong YAML mà runtime không thiết lập cgroups/network namespaces/volume quotas tương ứng thì chưa có hiệu quả an toàn.

## 12. Tránh command injection và tùy chọn compiler nguy hiểm

**Không nối trực tiếp user input thành shell command:**

```java
// Anti-pattern, chỉ minh họa: shell sẽ phân tích cú pháp của input.
new ProcessBuilder(
        "sh", "-c", "javac " + userFlags + " " + submittedFile
).start();
```

Dấu cách, ký tự shell, command substitution và path lạ có thể làm command thay đổi ý nghĩa. Thay vào đó, dùng `ProcessBuilder(List<String>)` hoặc constructor nhận từng argument, với **flags do server quyết định** và filename được validate.

Tuy nhiên, truyền arguments riêng **không tự làm user-supplied compiler flags an toàn**: một flag hợp lệ của compiler có thể yêu cầu nạp plugin, annotation processor, đổi output folder, can thiệp JVM hoặc đọc file ngoài mục tiêu. Vì vậy:

- Chọn một tập `javac` options cố định; `--release` và classpath phải đến từ policy.
- Không cho user quyết định trực tiếp `-processorpath`, `-Xplugin`, `-J...`, `-d` và `-s`.
- Không để file nộp có tên bất kỳ dẫn tới option injection; dùng đường dẫn được kiểm soát và bảo đảm argument là path.
- Không để user kiểm soát `CLASSPATH`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` và các env vars có thể ảnh hưởng compiler/runtime.
- Nếu bắt buộc chạy Gradle/Maven project của user, phải coi build script và plugin như code không tin cậy; compile worker cần isolation tương đương runtime worker.

Một dependency cache chung có thể đọc được thường phù hợp hơn việc cho worker tải thư viện tùy ý từ Internet. Nếu network cần mở để fetch dependency, dùng proxy được kiểm soát chứ không cấp quyền truy cập mạng nội bộ.

## 13. Phân loại kết quả: tránh quy lỗi môi trường thành lỗi source

Một mã exit khác 0 từ `javac` **không tự động** có nghĩa source Java sai. Có thể JDK chưa cài, executable bị chặn, worker bị OOM killed, timeout, dependency thiếu hoặc lỗi I/O.

Nên trả trạng thái có nghĩa:

| Status | Ý nghĩa |
|---|---|
| `COMPILE_OK` | Compiler chạy và chấp nhận source |
| `COMPILE_ERROR` | Compiler chạy đúng, từ chối source với diagnostic lỗi |
| `RUNTIME_FAILED` | Chương trình/test chạy nhưng kết quả hoặc exit code không đạt |
| `TIMEOUT` | Worker vượt thời gian cho phép |
| `RESOURCE_LIMIT` | CPU/RAM/PIDs/disk/output quota bị vượt |
| `INPUT_REJECTED` | Source/archive/path vi phạm admission policy |
| `INFRA_ERROR` | Không tìm được compiler, container lỗi, mount/config sai |
| `CANCELLED` | Người dùng hoặc quản trị hủy job |

Ví dụ **schema minh họa của ứng dụng**, không phải JSON do `javac` tự in:

```json
{
  "jobId": "opaque-job-id",
  "phase": "COMPILE",
  "status": "COMPILE_ERROR",
  "exitCode": 1,
  "timedOut": false,
  "quota": null,
  "diagnostics": [
    { "kind": "ERROR", "file": "Main.java", "line": 3 }
  ],
  "stdoutTruncated": false,
  "stderrTruncated": false
}
```

Nếu dùng `JavaCompiler` API để lấy `Diagnostic.Kind.ERROR`, vẫn phải chạy compiler trong worker đã cô lập nếu source không tin cậy. `Diagnostic.getMessage()` và stdout/stderr chỉ nên dùng làm thông tin chẩn đoán, không phụ thuộc chính xác câu chữ hoặc tin kết quả do code nộp tự khai.

Đối với test negative compilation, phải xác minh compiler **thực sự khởi chạy và nhận đúng fixture**. Một lỗi “command not found” không được tính là pass của bài test mong compiler từ chối nguồn.

## 14. Cleanup bền vững và quản lý toàn bộ vòng đời

```text
ACCEPTED
  |
  v
VALIDATING --------> INPUT_REJECTED ------> CLEANUP
  |
  v
PROVISIONING ------> INFRA_ERROR ---------> CLEANUP
  |
  v
COMPILING
  |-- bad source ---> COMPILE_ERROR ------> CLEANUP
  |-- timeout/limit -> TERMINATE_GROUP ---> CLEANUP
  v
RUNNING (nếu được yêu cầu)
  |-- test failure -> RUNTIME_FAILED -----> CLEANUP
  |-- timeout/limit -> TERMINATE_GROUP ---> CLEANUP
  v
COLLECTING (bounded)
  |
  v
FINISHED ------------> CLEANUP
```

`try/finally` trong worker chỉ chạy khi JVM/flow còn có cơ hội thực thi; process bị SIGKILL, mất điện hoặc node chết thì `finally` không đảm bảo dọn được. Vì vậy **control plane ngoài worker** phải sở hữu lifecycle: job lease/TTL, orphan detection và cleanup/reaper.

Trình tự quản lý hợp lý:

1. Ghi job identity và cấu hình quota trước khi cấp worker.
2. Khởi tạo worker với mount, user, network, resource policy.
3. Thực hiện compile/run; theo dõi deadline/quota và hủy **toàn nhóm** khi cần.
4. Thu kết quả đã giới hạn, exit status, reason bị kill/OOM, logs và metrics.
5. Validate result schema; không cho worker tự ghi sửa kết quả của job khác.
6. Xóa worker, scratch, mount và quyền tạm; nếu cleanup lỗi, đánh dấu để retry có kiểm soát.

Giữ secrets/test harness ngoài vùng ghi của bài nộp. Khi trả downloadable artifacts, định danh bằng job và quyền tenant, không cung cấp API nhận absolute filesystem path bất kỳ.

## 15. Kiểm thử độ an toàn của sandbox

Các fixture có hành vi gây quá tải nên được thử **trong môi trường đã cách ly và có quota**, không chạy trên developer machine hoặc production server.

| Tình huống | Điều cần chứng minh |
|---|---|
| ZIP chứa `../escape.java` | Không ghi ra ngoài workspace |
| ZIP có symlink ra ngoài | Không follow link tới file host |
| File upload rất lớn / nhiều entries | Admission limits hoặc quota chặn |
| Chương trình vòng lặp vô hạn | Timeout/CPU budget được áp, job bị thu hồi |
| Chương trình ghi stdout không ngừng | Byte cap và disk quota giữ vững |
| Sinh nhiều child processes | PID quota áp dụng cho descendants; nhóm bị teardown |
| Thử đọc file cấu hình host | OS permission/mount isolation từ chối |
| Thử truy cập network nội bộ | Network policy từ chối |
| Processor không được phép | Không được phát hiện/chạy trong compiler |
| Worker crash trong khi compile | Supervisor thu dọn orphan và báo INFRA_ERROR |
| Hai tenant chạy đồng thời | Không đọc/ghi workspace hoặc kết quả của nhau |

Metrics cần quan sát gồm thời gian queue/compile/run, CPU và peak RAM, số PIDs, disk bytes, file count, log bytes, số lần timeout/quota, orphan cleanup và tỷ lệ lỗi hạ tầng. Metrics/logs cũng cần phân quyền và tránh ghi source chứa bí mật không cần thiết.

## 16. Sai lầm phổ biến và cách sửa

**“Chỉ biên dịch, không chạy `main()`, nên an toàn.”** Compiler vẫn dùng tài nguyên và có thể nạp processor/plugin; chạy compile trong worker cô lập và có chính sách rõ.

**“`URLClassLoader` hoặc JShell là sandbox.”** Chúng không tạo ranh giới quyền OS; dùng worker process và cô lập filesystem/network/resources.

**“Chỉ bật `SecurityManager`.”** Bị vô hiệu hóa từ JDK 24; thiết kế mới phải dùng cơ chế bên ngoài JVM.

**“`-Xmx` đã đặt RAM limit.”** Chỉ Java heap; phải có hard memory quota ở OS/container.

**“Timeout là đủ.”** Quota CPU, PIDs, disk và memory vẫn phải được áp trước khi job chạy.

**“`destroyForcibly()` hủy hết children.”** Không bảo đảm; cần process group/container supervisor.

**“Dùng `normalize().startsWith(root)` là không thể traversal.”** Chưa giải quyết symlink/TOCTOU; dùng filesystem isolation và thao tác no-follow an toàn.

**“Cắt log khi trả HTTP là đủ.”** Child vẫn có thể ghi vô hạn; phải enforce output byte cap.

**“Docker mặc định an toàn tuyệt đối.”** Phải xem identity, privileged mode, mounts, network, resource limits, security profile; cân nhắc VM khi cần.

**“Exit code khác 0 nghĩa source sai.”** Lỗi hạ tầng, quota và compiler errors phải phân loại riêng.

**“Một file do người dùng đưa chỉ là dữ liệu.”** Build scripts, processors, compiler plugins và bytecode có khả năng thực thi; đánh giá đúng phase và quyền.

## 17. Bài tập vận dụng

**Tình huống A — Compiler trong Spring Boot.** API dùng `ToolProvider.getSystemJavaCompiler()` ngay trong server JVM để chấm mã upload. Một plugin annotation processor của user hoạt động và ghi file ngoài workspace. Cần sửa kiến trúc gì?

*Gợi ý:* Dùng compile worker riêng có OS identity và filesystem isolation; nếu bài không cần processing, dùng `-proc:none`; nếu cần, chỉ allowlist processor đã tin cậy. Không nạp compiler/user plugins trong server JVM.

**Tình huống B — Path validator.** Ứng dụng dùng `Path.normalize().startsWith(root)` và kết luận mọi path đều an toàn. Bài nộp tạo symbolic link bên trong root trỏ tới file bí mật. Vì sao kiểm tra trên chưa đủ?

*Gợi ý:* Validation ở mức từ vựng không giải quyết symlink hoặc race; cần no-follow/handle-relative operations và filesystem không chứa file bí mật trong worker.

**Tình huống C — Child process sống sót.** Parent bị timeout và gọi `destroyForcibly()`; sau đó vẫn có tiến trình con. Cần lớp kiểm soát nào?

*Gợi ý:* OS process group/cgroup/Job Object/container supervisor có ownership của mọi descendants, PID quotas và teardown toàn nhóm.

**Tình huống D — Output vài GB.** API chỉ trả 16 KiB stdout nhưng host disk vẫn bị đầy. Vấn đề ở đâu?

*Gợi ý:* API truncation không phải log/file quota. Enforce byte cap tại output collector hoặc filesystem và xử lý policy khi cap bị vượt.

**Tình huống E — Compile error giả.** Không tìm thấy `javac`, hệ thống trả `COMPILE_ERROR`. Nên sửa status thế nào?

*Gợi ý:* Đây là `INFRA_ERROR`, vì compiler chưa đánh giá source. Kết quả negative compile chỉ hợp lệ khi compiler chạy đúng và có diagnostic phù hợp.

**Tình huống F — Hai tenants.** Job A và B dùng chung scratch directory có quyền ghi. B bị thay class file trước khi test. Quyền gì bị vi phạm?

*Gợi ý:* Tính toàn vẹn artifact giữa tenants. Mỗi job cần workspace tách biệt, output không cho job khác ghi, và ideally immutable handoff từ compile sang run.

## 18. Checklist kiểm tra trước khi triển khai

- [ ] Threat model bao gồm source, archive, annotation processors, build scripts, compiler và runtime.
- [ ] Biên dịch nguồn không tin cậy trong worker có OS-level isolation; không dùng server JVM.
- [ ] Giới hạn upload/giải nén, số file, path depth và file names.
- [ ] Chống traversal, symlink, TOCTOU, và không cấp host secrets vào filesystem worker.
- [ ] Input/dependencies read-only, output/scratch riêng có quota và quyền truy cập tối thiểu.
- [ ] Compiler JDK/flags/classpath do hệ thống quyết định; processor được tắt hoặc allowlist.
- [ ] Worker không đặc quyền, network mặc định bị từ chối.
- [ ] CPU, RAM, PIDs, disk/inodes, file descriptors và log byte caps được thực thi.
- [ ] Wall-clock timeout, cancellation và cleanup bao gồm toàn process tree.
- [ ] Log được thu có giới hạn, escape khi hiển thị và không được coi là kết quả đáng tin.
- [ ] Trạng thái `COMPILE_ERROR`, `TIMEOUT`, `RESOURCE_LIMIT` và `INFRA_ERROR` được phân biệt.
- [ ] Có kiểm thử isolation thực tế và quy trình dọn orphan worker/workspace.
- [ ] Tenant quotas/concurrency limits và metrics giúp phát hiện quá tải.

## Tài liệu chính thức

- [Oracle Secure Coding Guidelines for Java SE](https://www.oracle.com/java/technologies/javase/seccodeguide.html).
- [OpenJDK JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486).
- [Oracle Java Security Guide — Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html).
- [Java SE 17 — `ProcessBuilder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html).
- [Java SE 17 — `Process`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html).
- [Java SE 17 — `ProcessHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html).
- [Java SE 17 — `Path` and `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/package-summary.html).
- [Java SE 17 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html).
- [Docker — Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/).
- [Kubernetes — Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/).
- [Kubernetes — Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal).

**Kết luận kỹ thuật:** `javac` có thể kiểm tra ngôn ngữ nhưng không thay thế isolation. Sự an toàn của một dịch vụ biên dịch/chạy mã nộp được quyết định bởi **quyền hệ điều hành, filesystem/network policy, quota tài nguyên, quản lý tiến trình và kiểm chứng trạng thái**, được áp dụng từ trước khi worker nhận input.
