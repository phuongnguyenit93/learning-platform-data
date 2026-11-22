# Xử lý file lock, daemon, đường dẫn dài và quyền truy cập khi dùng Gradle

## 1. Bài học thuộc nhóm IDE và chẩn đoán

Một project Java có thể biên dịch bình thường trên một máy nhưng lỗi khi mở IntelliJ IDEA, chạy Gradle từ terminal khác hoặc build trên Windows CI:

- `Timeout waiting to lock ...` hoặc `Cannot lock execution history cache`.
- `Unable to delete directory .../build` khi chạy `clean`.
- `AccessDeniedException` / `The process cannot access the file because it is being used by another process`.
- `Gradle daemon disappeared unexpectedly` hoặc không kết nối được daemon.
- `The filename or extension is too long` / `File name too long`.
- `Permission denied` khi chạy `./gradlew` trên Linux/macOS.
- Lỗi xuất hiện lúc IDE sync nhưng không xuất hiện lúc terminal build.
- Nhiều CI jobs/containers tranh cùng cache hoặc output directory.

Các trường hợp này thường được gọi chung là “Gradle bị khóa file”, nhưng thực ra có **bốn nhóm nguyên nhân khác nhau**:

1. **File locking:** Gradle cache locks hoặc một OS process đang giữ file handle.
2. **Daemon/process:** nhiều Gradle invocations, IDE sync, JDK mismatch, daemon crash, worker/test JVMs.
3. **Đường dẫn:** Windows `MAX_PATH`, nested source/generated paths, filename/segment quá dài, tool-specific path limits.
4. **Quyền truy cập:** NTFS ACL, POSIX UID/GID/mode/ACL, read-only mounts, storage quota, antivirus/cloud sync.

**Nguyên tắc quan trọng:** Không xóa toàn bộ `~/.gradle`, không xóa `*.lock` đang được dùng, không giết mọi process Java, không chạy Gradle dưới quyền Administrator/root chỉ vì một lỗi filesystem. Trước hết phải **xác định đúng path, operation, PID và nguyên nhân**.

### 1.1. Mục tiêu

Sau bài học, bạn có thể:
- Đọc đúng stacktrace để phân biệt lock timeout, permission denied, daemon error và long path.
- Hiểu Gradle daemon client/daemon/worker và vì sao IDE + terminal có thể giữ các processes khác nhau.
- Dùng `./gradlew --status`/`--stop`, `jps -lv`, daemon logs, `--info`, `--stacktrace`.
- Biết `--stop` chỉ xử lý daemon của **cùng Gradle version** được gọi, không thay OS file permissions.
- Hiểu project `.gradle`, Gradle User Home, Wrapper distributions, dependency caches và generated outputs.
- Tìm file handles trên Windows bằng Process Explorer/Handle, trên POSIX bằng `lsof`/`fuser` nếu có.
- Giải thích sự khác nhau giữa Windows path length policy và app `longPathAware`.
- Phân tích NTFS ACL, Unix permission bits, Docker UID/GID và cloud/network filesystems.
- Thực hành **Gradle Groovy DSL + Java 17** với task ghi output và Java file write/lock probe vô hại.
- Thiết kế CI cache/workspaces không va chạm, checklist phòng tránh lỗi.

## 2. Triệu chứng và cách phân loại nhanh

| Thông báo điển hình | Phân loại | Kiểm tra ưu tiên |
| --- | --- | --- |
| `Timeout waiting to lock ...` | Cache coordination lock | Lock owner PID, Gradle daemons, IDE sync |
| `Could not acquire lock on ...` | Gradle lock contention | Other builds/processes, GRADLE_USER_HOME |
| `Could not delete ...` / `Unable to delete directory` | Open handle hoặc permission | File owner, Windows handles, ACL |
| `AccessDeniedException` | OS deny hoặc sharing violation | ACL/owner, open file, read-only policy |
| `The process cannot access the file ... another process` | Windows sharing violation | Process Explorer/Handle tìm PID |
| `./gradlew: Permission denied` | Execute bit/mount | `ls -l gradlew`, mount `noexec` |
| `File name too long` / `ENAMETOOLONG` | Path or segment too long | Full absolute path, nested folder depth |
| `CreateProcess error=206` | Windows process args/command line/path quá dài | JavaExec/native launcher/classpath |
| `InvalidPathException` | Path syntax/encoding invalid | Path construction, reserved names |
| `No space left on device` | Disk/quota/inodes | Storage usage, container volume |
| `Read-only file system` | Read-only mount | Mount options/runner filesystem |
| `Gradle daemon disappeared unexpectedly` | Daemon crash/kill/OOM | Daemon log, OS memory/JVM diagnostics |
| `Could not connect to Gradle daemon` | Daemon socket/process/loopback | Logs, JVM, local network/AV |
| `No matching toolchains found` | JDK/toolchain selection | `javaToolchains`, JAVA_HOME, IDE JVM |

**Phải đọc root cause**, không chỉ câu báo cuối cùng. Chẳng hạn `clean` lỗi vì một test JVM đang dùng JAR không liên quan tới Gradle dependency lock. Tương tự, timeout tải Maven artifact qua HTTP là network timeout, không phải Gradle file-lock timeout.

## 3. Phân biệt các loại thư mục Gradle

Một project có thể chứa:

~~~text
my-project/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
├── .gradle/                     # project-specific state
│   ├── <gradle-version>/
│   └── configuration-cache/
└── build/                       # generated task outputs
    ├── classes/
    ├── reports/
    └── libs/
~~~

Gradle User Home mặc định:

~~~text
Linux/macOS: ~/.gradle
Windows:     C:\Users\<USERNAME>\.gradle

$GRADLE_USER_HOME/
├── gradle.properties
├── init.d/
├── caches/
│   ├── modules-2/
│   ├── <gradle-version>/
│   └── ...
├── daemon/
│   └── <gradle-version>/
│       └── daemon-<pid>.out.log
├── wrapper/dists/
└── jdks/
~~~

**Ý nghĩa:**
- `build/`: outputs được các tasks tạo; Gradle `clean` thông thường nhắm vào build directory.
- Project `.gradle/`: task execution history, input/output snapshots, configuration cache.
- `GRADLE_USER_HOME`: dependency/plugin caches, daemon data, Wrapper distributions, init scripts và có thể credentials.
- IDE caches: thư mục khác, thuộc IntelliJ IDEA/Eclipse/VS Code, không phải Gradle User Home.

Đừng nhầm `GRADLE_HOME` (nếu dùng, thường là thư mục cài Gradle) với `GRADLE_USER_HOME` (user-specific state). Thay `GRADLE_USER_HOME` có thể làm Gradle phải tải lại distribution/dependencies hoặc không thấy global settings cũ.

### 3.1. Xác định path chính xác

Khi stacktrace nói `.../.gradle/8.x/executionHistory/executionHistory.lock`, đây là project-local history lock. Nếu nói `~/.gradle/caches/modules-2`, đây là shared dependency cache. Nếu nói `build/libs/app.jar`, nghi output file handle. Mỗi đường dẫn có cách điều tra khác nhau.

### 3.2. Không tự sửa cache đang được dùng

Gradle quản lý locking/cleanup cho caches. Xóa file `.lock` đang hoạt động có thể làm mất cơ chế phối hợp; xóa `~/.gradle` có thể xóa credentials, init scripts, Wrapper distributions và dependencies nhiều GB. Chỉ sửa state cụ thể sau khi xác minh tất cả relevant processes đã dừng và đã backup dữ liệu cần thiết.

## 4. File locks: Gradle coordination khác OS open handle

### 4.1. Gradle file-based cache locks

Gradle dùng file-based locks để phối hợp metadata stores, ví dụ dependency cache. Theo Gradle docs, nhiều Gradle processes có thể chia sẻ dependency cache **khi các processes có thể giao tiếp để phối hợp**. Điều đó thường không đúng với builds chạy trong những containers cô lập dù cùng mount một directory.

Một ví dụ **dạng** log:

~~~text
Timeout waiting to lock file hash cache ...
Owner PID: 12345
It is currently in use by another Gradle instance.
~~~

Không coi PID hoặc wording trên là output bắt buộc của mọi Gradle version. Cần xem log thật: lock name, PID, current owner operation, waiting process và cache path.

### 4.2. OS-level handle/lock trên Windows

Windows file APIs có sharing semantics. Process đang mở một file hoặc JAR có thể không cho process khác rename/delete. Khi chạy `clean`, bạn có thể thấy:

~~~text
Unable to delete directory '.../build'
Could not delete file '.../build/libs/app.jar'
~~~

Thủ phạm có thể là IDE, test JVM, application còn chạy, file viewer/Explorer preview, antivirus, indexer, OneDrive sync hoặc một build khác.

Dừng Gradle daemon **không bảo đảm** tất cả các processes trên đóng handle. Nếu file vẫn bị khóa, phải tìm đúng owner.

### 4.3. Linux/macOS: file đang mở thường vẫn có thể unlink

Trên nhiều POSIX filesystems, một file đang mở vẫn có thể bị unlink; process tiếp tục giữ file descriptor/inode. Vì vậy lỗi `Permission denied` trên Linux cần kiểm tra ownership/mode/ACL, quyền truy cập parent directories, filesystem mount, immutable flags hoặc MAC policies, không mặc định kết luận “có process mở file”.

File có tên `something.lock` tồn tại trên disk cũng không chứng minh OS lock vẫn active. Lock owner là trạng thái process/kernel tùy lock API.

### 4.4. File lock không phải mọi dạng “Gradle bị kẹt”

Daemon `BUSY` có thể compile, resolve dependencies, chạy test, chờ network, worker process hoặc đang deadlock trong plugin code. Chỉ khi log/stacktrace nêu lock failure mới nên coi file lock là nguyên nhân chính.

## 5. Daemon: lifecycle và điều tra đúng phiên bản

Gradle daemon là một JVM chạy nền chứa Gradle execution engine. IDE thường gọi Gradle qua Tooling API nên có thể khởi động Gradle daemon dù terminal không chạy.

### 5.1. Lệnh chuẩn

Linux/macOS:

~~~bash
./gradlew --version
./gradlew --status
./gradlew help --stacktrace --info
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --status
.\gradlew.bat help --stacktrace --info
~~~

- `--version` xác nhận Gradle distribution và JVM runtime đang được báo.
- `--status` liệt kê daemons của **cùng Gradle version** với Wrapper invocation, có PID/IDLE/BUSY.
- `help --stacktrace --info` thu thập thêm context khi project đáng tin; lệnh này vẫn thực thi build configuration/plug-in code, không phải chế độ sandbox.

### 5.2. `./gradlew --stop` làm gì?

~~~bash
./gradlew --stop
~~~

Nó yêu cầu dừng các Gradle daemons do **cùng version Gradle** khởi tạo. Nó không tự:
- Dừng mọi daemon của version khác.
- Giết mọi `java`/`java.exe`.
- Dừng test JVM, Kotlin daemon, JavaExec app, IDE.
- Đóng antivirus/Explorer handles.
- Sửa NTFS ACL hoặc Unix ownership.
- Sửa lỗi quá dài path.
- Phục hồi metadata cache hỏng.

**Chỉ chạy khi không có build cần giữ đang hoạt động.** Nếu IDE đang sync hoặc job khác đang build cùng user, chờ/hủy đúng công việc trước để tránh làm gián đoạn.

### 5.3. `--status` không thấy process?

Gradle chỉ liệt kê daemons của version đang gọi. Dùng JDK process tools để xem nhiều versions:

~~~bash
jps -lv
jcmd -l
~~~

Nếu JDK tools có sẵn, có thể thấy `GradleDaemon` cùng các processes Java khác. Không kết luận tất cả những process Java đều là Gradle.

Windows PowerShell read-only:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -in @('java.exe', 'javaw.exe') } |
    Select-Object ProcessId, Name, CommandLine
~~~

**Không dùng** `taskkill /F /IM java.exe` hoặc `killall java` vì có thể giết server, IDE, tests và ứng dụng không liên quan.

### 5.4. Daemon logs

Gradle ghi logs tại:

~~~text
$GRADLE_USER_HOME/daemon/<gradle-version>/daemon-<pid>.out.log
~~~

Ví dụ:

~~~text
~/.gradle/daemon/8.14.3/daemon-12345.out.log
~~~

Đối chiếu **PID + Gradle version** xuất hiện trong lỗi. Với daemon crash/không kết nối, kiểm tra cuối log, JVM crash report, OS memory/OOM và localhost/loopback settings. Gradle client-daemon communication dùng local sockets; một số cấu hình firewall/NAT có thể tác động. Không giải thích mọi daemon crash bằng file lock.

### 5.5. Vì sao IDE tạo nhiều daemons?

IDE Gradle JVM có thể khác `JAVA_HOME` của terminal. Daemon compatibility còn phụ thuộc Gradle version, JVM/JVM args và daemon criteria. Ví dụ IDE chạy Gradle trên JDK21 còn terminal dùng JDK17 sẽ có thể tạo daemon khác.

`java { toolchain { languageVersion = JavaLanguageVersion.of(17) } }` chọn Java compiler/test JVM cho project, **không nhất thiết đặt JVM chạy Gradle daemon**. Cần kiểm tra riêng IDE Gradle JVM, Gradle daemon JVM và Java toolchain.

### 5.6. `--no-daemon` là phép thử, không phải phép chữa

~~~bash
./gradlew help --no-daemon --stacktrace
~~~

Có thể giúp so lỗi liên quan daemon reuse. Nhưng Gradle vẫn có thể tạo **single-use daemon** khi JVM arguments yêu cầu khác với client. Nó cũng không tránh locks từ processes khác và không thay OS permissions.

## 6. Quy trình chẩn đoán ít rủi ro nhất

### Bước 1 — Lưu root cause

Ghi lại command, task, Gradle version, OS, Java runtime, đầy đủ exception class/path, PID nếu có, IDE đang làm gì, thay đổi gần đây (JDK, Git branch, Gradle version, workspace location), CI jobs đang cùng chạy hay không.

### Bước 2 — Kiểm tra tác vụ đang chạy

Chờ/hủy đúng IDE sync/terminal build/CI job. Không cố stop một daemon đang xử lý build quan trọng của người khác cùng user.

### Bước 3 — Quan sát daemon/process

~~~bash
./gradlew --status
jps -lv
~~~

Nếu owner PID trong log, so khớp PID với command line. Nếu `--status` không hiện, PID có thể thuộc version khác hoặc process đã kết thúc.

### Bước 4 — Thu thập stacktrace và logs

~~~bash
./gradlew help --stacktrace --info
~~~

Dùng trên project đã tin cậy. `help` lỗi ngay thường gợi ý bootstrap/configuration/Gradle project state; `clean` lỗi riêng thì xem output handle; `test` lỗi riêng thì xem test worker/file outputs.

### Bước 5 — Dừng daemon đúng cách khi không còn build active

~~~bash
./gradlew --stop
~~~

Nếu vẫn có handle, tìm owner bằng OS tools; không kill mọi JVM.

### Bước 6 — Kiểm tra permissions, path và filesystem

- File/directory có tồn tại?
- Đường dẫn lỗi là project output/cache hay global cache?
- Path quá dài hay chứa ký tự không hợp lệ?
- Filesystem readonly, quota đầy hay UID/GID sai?
- Windows có antivirus/IDE/Explorer/cloud sync giữ open handle?
- NFS/SMB/container volume có semantics khác local disk?

### Bước 7 — Thử ít concurrency

~~~bash
./gradlew help --no-parallel --max-workers=1 --info
~~~

Chỉ là **thí nghiệm** xem có internal task concurrency issue không. Nó không sửa cache lock giữa hai Gradle processes độc lập hay những CI containers dùng cùng shared writable home.

### Bước 8 — Cô lập Gradle User Home khi nghi cache conflict

Thử với một home mới, **không có secrets**, trên project đã tin cậy. Việc này có thể tải lại Gradle distribution/dependencies.

Linux/macOS:

~~~bash
GUH="$(mktemp -d)"
GRADLE_USER_HOME="$GUH" ./gradlew help --stacktrace
printf 'Diagnostic home: %s\n' "$GUH"
~~~

Không xóa directory test khi còn processes dùng nó. Đổi home còn làm mất user-specific `gradle.properties`/init scripts, nên nếu build khác hành vi, phải xem xét cả khác biệt cấu hình, không chỉ kết luận cache cũ corrupt.

PowerShell:

~~~powershell
$old = $env:GRADLE_USER_HOME
$env:GRADLE_USER_HOME = Join-Path $env:TEMP ('gradle-diag-' + [guid]::NewGuid().ToString('N'))
try {
    .\gradlew.bat help --stacktrace
    Write-Host "Diagnostic home: $env:GRADLE_USER_HOME"
} finally {
    $env:GRADLE_USER_HOME = $old
}
~~~

Giữ diagnostic home để kiểm tra nếu cần. Cleanup sau khi chắc chắn không có process đang giữ và path nằm trong directory đã tạo.

### Bước 9 — Sửa đúng phần state có vấn đề

Chỉ khi có evidence corruption/lock còn sau shutdown:
- Backup/rename đúng project-local `.gradle` hoặc đúng cache subtype được phép, sau khi processes đã dừng.
- Không xóa toàn bộ global Gradle User Home, credentials và init scripts.
- Không xóa `*.lock` đang live.
- Biết rằng mất local task history làm build phải chạy lại nhiều tasks.
- Với dependency cache, Gradle có built-in cleanup; xóa thủ công là phương án cuối, cần tải lại artifacts từ nguồn đã xác minh.

## 7. Chẩn đoán Windows open handles

Trên Windows, file sharing modes có thể ngăn delete/rename ngay cả khi ACL có Modify permission.

### 7.1. Công cụ phù hợp

- **Microsoft Sysinternals Process Explorer**: tìm handle/DLL theo path.
- **Microsoft Sysinternals Handle**: tra open handles từ command line.
- **Resource Monitor**: xem associated handles.
- PowerShell `Get-CimInstance Win32_Process`: xem process PID/command line.
- Task Manager: xác nhận process/activity.

Nếu đã cài `handle.exe` chính thức:

~~~powershell
handle.exe "build\libs"
~~~

Đây là tra cứu read-only; tool có thể yêu cầu privilege để thấy đủ handles. Kết quả cần đối chiếu PID/path, không tự suy rằng một match gần đúng chính là lock owner.

**Không force-close handle** bằng công cụ chỉ để chạy `clean`. Đóng sai handle có thể làm process hỏng trạng thái hoặc crash. Hãy đóng application/IDE debug session một cách graceful.

### 7.2. Các process thường giữ output

| Process | Tình huống | Cách xử lý |
| --- | --- | --- |
| IntelliJ/Gradle Tooling API | IDE đang sync/build | Chờ/hủy đúng sync |
| Test JVM hoặc JavaExec | App/test mở JAR/report/log | Dừng đúng Run/Debug |
| Explorer preview/file viewer | PDF/HTML/log vẫn mở | Đóng viewer |
| Antivirus/endpoint security | Quét file mới tạo/xóa | Thu thập evidence cho IT, không disable diện rộng |
| OneDrive/cloud sync | Workspace nằm trong synchronized folder | Dùng local workspace không sync |
| Gradle terminal khác | Hai builds cùng outputs | Chờ build kia xong |
| Language server | Code indexing/Java extension | Restart đúng subsystem nếu cần |

### 7.3. ACL và file attributes

Chỉ đọc:

~~~powershell
Test-Path -LiteralPath '.\build'
Get-Item -LiteralPath '.\build' | Format-List FullName,Attributes
Get-Acl -LiteralPath '.\build' | Format-List
icacls ".\build"
~~~

Nếu `build` chưa tồn tại, lệnh `Get-Item`/`Get-Acl` sẽ lỗi — dùng path thật từ stacktrace. NTFS ACL có inheritance, explicit deny và group membership; một người có thể đọc file nhưng không được delete/rename.

**Không làm mặc định:**
- `icacls /grant Everyone:(F)`.
- Run IDE/Gradle as Administrator.
- Tắt Windows Defender/endpoint protection.
- Reset ACL cả user profile.

Sửa quyền nhỏ nhất trên path do bạn sở hữu và theo policy.

## 8. Linux/macOS: ownership, mode, mount, open files

### 8.1. Kiểm tra user và permission

~~~bash
id
pwd
ls -ld .
ls -ld build
ls -l gradlew
~~~

Nếu `build` chưa tồn tại, `ls -ld build` báo missing; hãy xem path lỗi thật. Trên POSIX:
- Đọc file cần quyền read.
- Ghi file cần quyền write.
- Vào directory cần quyền execute/search trên từng parent.
- Tạo/xóa entry trong directory thường cần quyền write + execute trên parent (còn chịu ACL/sticky bit/flags).

Linux có thể dùng `namei -l /path/to/file` xem từng component; `getfacl` nếu cài sẵn. macOS có thể dùng `ls -le`/`stat` để xem ACL/attributes.

### 8.2. `gradlew: Permission denied`

Kiểm tra:

~~~bash
ls -l gradlew
~~~

Nếu file được phép chỉnh và thiếu executable bit:

~~~bash
chmod u+x gradlew
./gradlew --version
~~~

Trong Git:

~~~bash
git ls-files --stage gradlew
git update-index --chmod=+x gradlew
~~~

Commit executable mode nếu cần. Nhưng nếu workspace mount `noexec`, chỉ `chmod +x` có thể không đủ; cần mount policy phù hợp hoặc workspace khác. Không tự đổi mount flags trên shared runner nếu không có quyền.

### 8.3. Tra open files

Khi có `lsof`:

~~~bash
lsof -- build/libs/app.jar
~~~

Linux có `fuser` khi được cài:

~~~bash
fuser -v build/libs/app.jar
~~~

Đây là lệnh chỉ đọc để tìm processes đang mở path. Kết quả trống không chứng minh không có lock ở path khác. Trên Linux/macOS, unlink semantics khác Windows nên việc file đang mở không nhất thiết ngăn xóa.

### 8.4. Disk/mount/quota

~~~bash
df -h .
df -i .
~~~

`df -i` giúp xem inodes trên filesystems hỗ trợ. Nếu quota/inodes hết hoặc mount readonly, `chmod` và `--stop` không thể giải quyết nguyên nhân gốc.

### 8.5. Root-owned build outputs

Nếu từng chạy `sudo ./gradlew`, `build/` hay `.gradle/` có thể do root sở hữu. Normal user sẽ gặp AccessDenied/Permission denied. Chẩn đoán chính xác UID/GID rồi sửa ownership **trong phạm vi project được phép**. Không dùng recursive `sudo chown -R` vô điều kiện trên toàn bộ home/shared volume, và không tiếp tục dùng sudo như workaround.

## 9. Windows long paths: `MAX_PATH` và app compatibility

Một checkout sâu có thể tạo path kiểu:

~~~text
C:\Users\dev\OneDrive\Documents\Company\Training\Java\Lessons\VeryLongModule\build\classes\java\main\...
~~~

### 9.1. MAX_PATH không phải giới hạn tuyệt đối cho mọi chương trình hiện đại

Win32 APIs truyền thống có `MAX_PATH` khoảng **260 characters** (gồm null terminator). Windows 10 version 1607 trở đi hỗ trợ long paths cho nhiều Unicode APIs khi:
1. Machine policy/registry **LongPathsEnabled** được bật.
2. Application có manifest **longPathAware** và thực sự hỗ trợ.

Vì thế chỉ bật long paths trong registry **không** đảm bảo mọi plugin, IDE, Java/native library, ZIP utility hoặc process launcher đều xử lý được. Các tools có giới hạn riêng, bao gồm component/filename limits và command-line length limits.

Microsoft Learn là tài liệu gốc về điều kiện này; đừng truyền lệnh chỉnh registry không qua chính sách IT của tổ chức.

### 9.2. Chẩn đoán path dài

1. Copy **full path** từ root cause log, không chỉ tên file.
2. Xem absolute length và từng segment.
3. Kiểm tra workspace trong OneDrive/Sync/UNC/network share không.
4. Xác định lỗi đến từ Java NIO, Gradle, JDK compiler, ZIP unpacker hay external process.
5. Thử checkout project ở root ngắn và đáng tin, ví dụ `C:\src\app`.
6. Nếu Gradle User Home quá dài, có thể dùng một home ngắn, riêng cho user/job.
7. Nếu vẫn lỗi, xem support của từng app và OS long-path policy.
8. Không thêm `\\?\` vào mọi string path một cách mù quáng.

### 9.3. Đo checkout root path bằng PowerShell

~~~powershell
$root = (Resolve-Path -LiteralPath '.').Path
$root
$root.Length
~~~

Kết quả là string length của **project root** trong PowerShell, chưa bao gồm nested package/generated file paths. Nó hữu ích để thấy root quá sâu, không phải chứng minh tool đã hỗ trợ mọi long paths.

### 9.4. `CreateProcess error=206` có thể khác file path quá dài

Lỗi Win32 process creation có thể do command line/classpath arguments quá dài hoặc executable path. Giải pháp có thể là rút ngắn classpath, dùng Java argument files khi tool hỗ trợ, thay cách launch của plugin hoặc nâng tool version; không nhất thiết chỉ bật LongPathsEnabled.

### 9.5. Git/ZIP/IDE có giới hạn riêng

Git for Windows có một số options như `core.longpaths`, nhưng chúng không sửa giới hạn của mọi process khác. IDE và unzip/native compilers có thể vẫn lỗi. Với build outputs:
- Rút ngắn project root.
- Dùng local filesystem.
- Tránh nested generated directory names không cần thiết.
- Giữ files dưới Gradle `layout.buildDirectory` thay vì hard-code absolute paths dài.
- Không ép người học đổi package names chỉ để chữa lỗi chưa xác định.

### 9.6. GRADLE_USER_HOME ngắn hơn

Một home như `C:\gradle-cache\developer1` có thể giảm nesting cho downloaded modules và toolchain paths, nhưng:
- Phải có quyền truy cập đúng.
- Không được dùng writable chung cho nhiều users/containers untrusted.
- Đổi home sẽ thay global settings/init scripts/cached distribution availability.
- Không xóa home cũ khi có build đang chạy.

## 10. IDE và terminal khác môi trường như thế nào?

### 10.1. IntelliJ IDEA

Kiểm tra:
- Gradle distribution là Wrapper hay installed Gradle?
- Gradle JVM được cấu hình là JDK nào?
- Terminal `JAVA_HOME`/`./gradlew --version` báo gì?
- Có background Gradle sync, indexing, Run/Debug process?
- IDE có mở output JAR/report/file không?
- Có nhiều projects cùng dùng Gradle User Home?

Khi nghi IDE giữ file:
1. Chờ hoặc hủy **đúng** Gradle sync.
2. Dừng đúng Run/Debug application.
3. Kiểm tra Process Explorer/`lsof` nếu OS vẫn báo lock.
4. Chạy terminal task riêng để so sánh.
5. Chỉ invalidate IDE cache khi có evidence IDE indexes hỏng, không dùng để sửa OS ACL/Gradle dependency lock.

### 10.2. Eclipse Buildship và VS Code Java extensions

Các công cụ này sử dụng Gradle Tooling API/Java language servers. Có thể có JVMs khác với terminal. Chẩn đoán bằng output views, IDE Gradle JDK, process ID và logs. Restart **đúng extension/language server** thay vì kết thúc mọi Java process.

### 10.3. IDE Clean Project khác Gradle `clean`

IDE caches/indexes không giống project `.gradle` và Gradle User Home. `./gradlew clean` thông thường xóa build outputs, không reset toàn bộ IDE indexes. IDE Invalidate Caches không sửa external process giữ file hoặc ACL. Chọn tool theo đúng layer.

### 10.4. Chẩn đoán nhiều JDK/daemon

Terminal JDK17 và IDE Gradle JVM21 có thể tạo các daemon khác nhau. Java toolchain dùng JDK17 cho compiler không nhất thiết làm Gradle daemon JVM chuyển thành JDK17. Cần tách:
- Java khởi động Wrapper.
- Gradle daemon JVM.
- Java compiler toolchain.
- Test/JavaExec launcher.
- IDE Gradle JVM.

## 11. CI và Gradle caches: tránh lock giữa jobs

### 11.1. Hai builds cùng project directory

Không cho hai independent Gradle processes cùng lúc ghi `build/` và project `.gradle` trên shared workspace mà không có thiết kế phù hợp. Task outputs có thể chồng lấn, task history lock tranh nhau, cleanup của một job xóa outputs của job khác.

Mỗi CI job nên có workspace riêng. Trong một build, Gradle tự quản lý task graph/parallel scheduling và dependencies phù hợp.

### 11.2. Shared writable dependency cache qua containers

Gradle dependency cache locking phối hợp khi các Gradle processes có thể giao tiếp. Containers cô lập thường không đáp ứng. **Không** mount cùng writable `~/.gradle/caches` cho nhiều containers rồi coi Gradle tự xử lý mọi lock.

Giải pháp:
- Private writable `GRADLE_USER_HOME` cho mỗi job.
- CI cache restore/save có thứ tự và quyền phù hợp.
- Remote build cache có trust/permission policy khi cần.
- Portable seeded dependency cache read-only theo tài liệu Gradle; không copy `*.lock`/`gc.properties` vào seed.
- Tách cache của untrusted PR khỏi trusted release.

### 11.3. Không biến shared cache thành nơi chứa secrets

Gradle User Home có thể chứa `gradle.properties`, init scripts, daemon logs và configuration cache encryption keys. Không upload toàn bộ home làm artifact hoặc chia sẻ giữa users có mức độ tin cậy khác nhau. Không dùng cache hit là chứng minh artifact đã được kiểm tra security.

### 11.4. OS-specific CI practice

**Windows runner:**
- Workspace root ngắn.
- Local non-synced directory.
- Không tắt antivirus diện rộng.
- Chờ tasks/JavaExec/test JVM hoàn tất trước cleanup.
- Gradle User Home riêng/job.
- Long-path policy được IT review.

**Linux/macOS runner:**
- Chạy non-root user.
- Bind-mounted workspace UID/GID phù hợp.
- Script `gradlew` executable.
- Filesystem writable, quota/inodes đủ.
- Không chia sẻ init scripts/global cache writable giữa jobs untrusted.

## 12. Lab thực hành: Java 17 thử quyền ghi và file lock riêng

Bài lab không can thiệp Gradle's `*.lock`. Nó dùng:
- Gradle task `writeReport` khai `@OutputFile`.
- Java `AccessProbe` có chế độ `write` để tạo/đọc/xóa file tạm.
- Chế độ `lock` dùng `FileChannel.tryLock()` **trên một file do lab tạo**, không khóa cache Gradle.
- Lệnh `javac`/`java` độc lập để kiểm chứng output.
- Gradle Groovy DSL + JDK17.

### 12.1. Cấu trúc

~~~text
gradle-diagnostics-lab/
├── settings.gradle
├── build.gradle
├── src/main/java/dev/example/diagnostics/AccessProbe.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Yêu cầu một Wrapper/JDK17 tương thích, đáng tin. Các lệnh chạy trong root project. Không dùng external Gradle plugins/libraries.

### 12.2. `settings.gradle`

~~~groovy
rootProject.name = 'gradle-diagnostics-lab'
~~~

### 12.3. `build.gradle` — file hoàn chỉnh

~~~groovy
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 17
}

application {
    mainClass = 'dev.example.diagnostics.AccessProbe'
}

abstract class WriteReportTask extends DefaultTask {

    @OutputFile
    abstract RegularFileProperty getReportFile()

    @TaskAction
    void writeReport() {
        Path path = getReportFile().get().asFile.toPath()
        Files.createDirectories(path.getParent())
        Files.writeString(
            path,
            "Gradle report OK\n",
            StandardCharsets.UTF_8
        )
        logger.lifecycle('REPORT_WRITE=PASS')
    }
}

tasks.register('writeReport', WriteReportTask) {
    group = 'verification'
    description = 'Create a Gradle-owned diagnostic report'
    reportFile.set(
        layout.buildDirectory.file('diagnostics/report.txt')
    )
}
~~~

**Giải thích:**
1. `application` là core Gradle plugin, không cần tải plugin thứ ba.
2. `java.toolchain` và `options.release=17` chọn JDK/API target Java17.
3. `WriteReportTask` extends `DefaultTask`, output là managed `RegularFileProperty`.
4. `@OutputFile` cho Gradle biết file được sở hữu bởi task.
5. `@TaskAction` chỉ ghi khi task thực thi, không tạo file trong configuration.
6. File nằm dưới project build directory; không ghi vào global cache.
7. Với filesystem writable, TaskAction tạo parent rồi ghi UTF-8.
8. Khi output và task implementation không đổi, lần sau có thể `UP-TO-DATE`, nên không in `REPORT_WRITE=PASS` lại.
9. Nếu AccessDeniedException xuất hiện, đó là lỗi filesystem thật; không bắt/nuốt exception rồi báo thành công.
10. Tên task/project đầy đủ để không xung đột với built-in `clean`.

### 12.4. `src/main/java/dev/example/diagnostics/AccessProbe.java`

~~~java
package dev.example.diagnostics;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class AccessProbe {

    private AccessProbe() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: AccessProbe write|lock <lab-directory>"
            );
        }

        Path directory = Path.of(args[1])
            .toAbsolutePath()
            .normalize();

        if ("write".equals(args[0])) {
            probeWrite(directory);
        } else if ("lock".equals(args[0])) {
            probeLock(directory);
        } else {
            throw new IllegalArgumentException(
                "Unknown mode: " + args[0]
            );
        }
    }

    private static void probeWrite(Path directory) throws IOException {
        Files.createDirectories(directory);
        Path temporary = Files.createTempFile(
            directory,
            "write-probe-",
            ".tmp"
        );

        try {
            Files.writeString(
                temporary,
                "write-ok\n",
                StandardCharsets.UTF_8
            );

            String actual = Files.readString(
                temporary,
                StandardCharsets.UTF_8
            );
            if (!"write-ok\n".equals(actual)) {
                throw new IOException("Readback mismatch");
            }
        } finally {
            Files.deleteIfExists(temporary);
        }

        System.out.println("WRITE_TEST=PASS");
    }

    private static void probeLock(Path directory) throws IOException {
        Files.createDirectories(directory);
        Path target = directory.resolve("lock-probe.dat");

        try (FileChannel channel = FileChannel.open(
                target,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE
        )) {
            FileLock lock = null;
            try {
                lock = channel.tryLock();
                if (lock == null) {
                    System.out.println("LOCK_TEST=BUSY");
                } else {
                    System.out.println("LOCK_TEST=ACQUIRED");
                }
            } catch (OverlappingFileLockException ex) {
                System.out.println("LOCK_TEST=BUSY_SAME_JVM");
            } finally {
                if (lock != null && lock.isValid()) {
                    lock.release();
                }
            }
        }
    }
}
~~~

**Mã Java này đầy đủ và không import Gradle API.** Có thể compile/run chỉ bằng javac/java17.

### 12.5. Hiểu chính xác phép thử

- `probeWrite` thử create, write, read, delete **trong directory cụ thể**. Chỉ sau khi cleanup thành công mới in PASS.
- `Files.createDirectories` có thể lỗi vì ACL, path, readonly filesystem hoặc quota.
- `probeLock` thử nonblocking `FileChannel.tryLock()` trên **lock-probe.dat** của lab.
- Khi không có competing lock và filesystem hỗ trợ, nó thường in `LOCK_TEST=ACQUIRED`.
- Nếu process khác giữ lock xung đột, có thể trả `null` và in `LOCK_TEST=BUSY`.
- Nếu chính JVM đã giữ overlapping lock, có thể gặp `OverlappingFileLockException`.
- Cuối cùng lock được release và channel đóng.
- **File `lock-probe.dat` còn tồn tại không có nghĩa lock còn được giữ.**
- Lock semantics trên Linux thường advisory; trên Windows sharing modes còn có các quy tắc khác. Probe này **không** mô phỏng toàn bộ Gradle cache locking hoặc Windows delete-sharing.

Chỉ truyền folder test như `build/probe`. Không nhập paths chứa dữ liệu nhạy cảm hoặc cache của ứng dụng khác.

### 12.6. Chạy task ghi report

Linux/macOS:

~~~bash
./gradlew writeReport --console=plain
cat build/diagnostics/report.txt
~~~

**Nội dung file chính xác:**

~~~text
Gradle report OK
~~~

TaskAction lần chạy đầu cũng in lifecycle line:

~~~text
REPORT_WRITE=PASS
~~~

Nó là **một dòng log do task tự ghi**, không phải toàn bộ Gradle console output. Nếu `writeReport` được đánh giá `UP-TO-DATE` ở lần thứ hai, TaskAction không chạy nên không có log đó.

PowerShell:

~~~powershell
.\gradlew.bat writeReport --console=plain
Get-Content '.\build\diagnostics\report.txt'
~~~

### 12.7. Chạy Java write probe qua Gradle

~~~bash
./gradlew run --quiet --args="write build/probe"
~~~

**Stdout chính xác khi create/read/write/delete thành công:**

~~~text
WRITE_TEST=PASS
~~~

Windows:

~~~powershell
.\gradlew.bat run --quiet --args="write build/probe"
~~~

Nếu OS deny một thao tác, Java ném IOException và chương trình không thể in PASS. Điều đó là evidence cho **build/probe tại thời điểm chạy**, không khẳng định global cache nào cũng writable.

### 12.8. Chạy Java lock probe qua Gradle

~~~bash
./gradlew run --quiet --args="lock build/probe"
~~~

Với local filesystem hỗ trợ locking và không có competing lock:

~~~text
LOCK_TEST=ACQUIRED
~~~

Nếu busy, có thể in `LOCK_TEST=BUSY` hoặc báo OS exception. Không xem lock probe PASS là bằng chứng Gradle daemon/cache lock của project đã lành.

### 12.9. Compile/run Java17 độc lập

~~~bash
javac --release 17 -encoding UTF-8 -d standalone src/main/java/dev/example/diagnostics/AccessProbe.java
java -cp standalone dev.example.diagnostics.AccessProbe write build/probe
java -cp standalone dev.example.diagnostics.AccessProbe lock build/probe
~~~

**Stdout chính xác trong điều kiện filesystem writable và không có competing lock:**

~~~text
WRITE_TEST=PASS
LOCK_TEST=ACQUIRED
~~~

Hai dòng thuộc **hai command Java nối tiếp**, không phải Gradle task log.

### 12.10. Java `Files.isWritable` không phải bảo đảm tuyệt đối

`Files.isWritable(path)` chỉ cho biết phép kiểm tra quyền của filesystem provider tại một thời điểm. Quyền có thể thay đổi ngay sau đó hoặc process khác chiếm handle. Probe tạo/ghi/đọc/xóa file tạm phản ánh hành vi thực hơn, nhưng vẫn không đảm bảo tất cả lệnh sau đó thành công trên mọi path.

### 12.11. Điều lab không chứng minh

- Không biết process nào đang giữ **Gradle cache** lock.
- Không chứng minh IDE không giữ một JAR khác.
- Không giải thích lỗi daemon socket/OOM.
- Không chứng minh mọi directory writable chỉ vì `build/probe` writable.
- Không kiểm tra mọi long-path limitations của OS/native tools.
- Không khẳng định network-mounted file locks giống local locks.

Để chẩn đoán Gradle thực, phải kết hợp logs, PID, handles, ACL/path và CI state.

## 13. Các phản xạ sai khi gặp lỗi Gradle

### 13.1. Xóa `~/.gradle` ngay

Sai vì nó chứa global properties, init scripts, caches, Wrapper distributions, JDK toolchains và có thể credentials. Xóa có thể phá builds khác đang chạy, mất cấu hình hoặc buộc tải lại dependencies. Dùng đúng path/provenance và xác minh không còn process active trước khi sửa cache cụ thể.

### 13.2. Xóa file `*.lock`

Sai khi chưa biết owner. Live OS lock không đơn giản là sự tồn tại của tên file. Gradle dùng lock để bảo vệ metadata. Không tự xóa lock marker khi processes còn hoạt động.

### 13.3. Kill mọi `java.exe`

Sai vì có thể giết IDE, Java server, debugger, tests và process của người khác. Ưu tiên `--stop` và kiểm tra PID, chỉ dừng đúng process gracefully.

### 13.4. Chạy Gradle bằng Administrator/root

Tăng quyền build scripts/plugins và tạo output/cache có ownership khác. Sửa đúng ACL/UID/GID thay vì liên tục leo quyền.

### 13.5. `chmod -R 777` hoặc `Everyone Full Control`

Làm giảm bảo mật, không chữa Windows file-sharing lock hoặc readonly mount/long path. Cấp quyền tối thiểu cho đúng user/path.

### 13.6. Tắt antivirus toàn bộ

Không nên. Với endpoint protection của doanh nghiệp, ghi bằng chứng process/path rồi liên hệ IT để điều chỉnh policy/exclusion hẹp nếu cần.

### 13.7. Dùng `--no-daemon` cho mọi lỗi

Không chữa permission/path/disk quota/other process locks, có thể vẫn dùng single-use daemon. Chỉ là phép thử daemon reuse có kiểm soát.

### 13.8. Đổi nhiều thứ cùng lúc

Nâng Gradle, JDK, di chuyển project, xóa caches và sửa ACL cùng lúc khiến khó xác định root cause. Thay từng điều, ghi lại result và có đường rollback.

## 14. Bảng quyết định nhanh

| Tình huống | Kiểm tra | Khắc phục có kiểm soát |
| --- | --- | --- |
| Timeout chờ Gradle cache lock | Log owner PID, `--status`, IDE sync | Chờ/đóng đúng process, xem shared cache |
| `--status` không hiện daemon cũ | Khác Gradle version | `jps -lv`/OS process tools |
| `--stop` rồi `clean` vẫn không xóa được JAR | External open handle | Process Explorer/`lsof`, đóng app đúng cách |
| Windows path dưới OneDrive quá sâu | Full absolute length, offending tool | Workspace root ngắn hơn |
| LongPathsEnabled bật nhưng vẫn lỗi | Process không hỗ trợ longPathAware | Update tool hoặc rút ngắn path |
| Linux `gradlew` không chạy | Executable bit/mount | `chmod u+x`/Git mode hoặc mount policy |
| Linux build files root-owned | `id`, `ls -ld`, ACL | Sửa owner đúng phạm vi, non-root Gradle |
| Windows ACL deny delete | `icacls`/`Get-Acl` | Least-privilege ACL correction |
| CI containers tranh global cache | Shared writable GRADLE_USER_HOME | Job-specific writable home |
| Test JVM còn mở file | IDE/debug/process list | Dừng đúng test/app process |
| Daemon disappeared | daemon log/OS OOM/JDK | Sửa resource/JVM/network theo evidence |
| Missing dependency network timeout | HTTP logs/repository | Xử lý proxy/network, không xóa lock |
| Build filesystem readonly | mount/volume permissions | Chọn writable workspace/mount |
| `No space left on device` | quota/inodes/df | Dọn đúng phần được phép hoặc tăng quota |
| Project `.gradle` nghi lỗi | Isolate Gradle User Home/logs | Backup/rename đúng state khi processes dừng |
| IDE Gradle JVM khác terminal JDK | IDE Gradle settings/JAVA_HOME | Align theo policy, không nhầm toolchain |

## 15. Câu hỏi và đáp án

### Bài 1 — Hai lệnh `--status` và `--stop`

**Hỏi:** `--stop` từ Wrapper Gradle8 có dừng daemon Gradle9 không?

**Đáp án:** Không theo cơ chế được mô tả; nó dừng daemons cùng Gradle version được dùng để gọi.

### Bài 2 — IDE sync

**Hỏi:** IntelliJ đang sync và terminal báo lock timeout. Có nên xóa `.gradle`?

**Đáp án:** Không. Xem đúng PID/build/sync trước; chờ hoặc hủy task IDE phù hợp, rồi thử lại.

### Bài 3 — Windows JAR đang mở

**Hỏi:** Process Explorer thấy Java application đang mở `app.jar`, `clean` không xóa được. Bước tiếp?

**Đáp án:** Dừng đúng application gracefully, kiểm tra handle đã đóng, chạy lại `clean`.

### Bài 4 — Linux unlink

**Hỏi:** Một file đang được process mở có luôn ngăn unlink trên POSIX?

**Đáp án:** Không; tùy OS/filesystem semantics, thường có thể unlink entry trong khi process giữ inode.

### Bài 5 — Cache folder

**Hỏi:** `build/` và `~/.gradle/caches/modules-2` có cùng chức năng không?

**Đáp án:** Không. `build/` chứa project outputs, `modules-2` là dependency cache trong Gradle User Home.

### Bài 6 — Locks và containers

**Hỏi:** Hai containers cô lập cùng ghi vào một Gradle dependency cache có được Gradle hỗ trợ an toàn mặc định?

**Đáp án:** Không nên giả định. Gradle file locking yêu cầu processes có thể giao tiếp; dùng private writable Gradle User Home cho mỗi job.

### Bài 7 — Path quá dài

**Hỏi:** Bật LongPathsEnabled trên Windows có đủ cho mọi Gradle plugin/native tool không?

**Đáp án:** Không. App cần hỗ trợ long paths, có thể có giới hạn riêng; rút ngắn workspace path nếu phù hợp.

### Bài 8 — File permissions

**Hỏi:** POSIX file có read permission nhưng không delete được vì parent directory thiếu write. Mâu thuẫn không?

**Đáp án:** Không. Delete liên quan directory entry và quyền parent.

### Bài 9 — `sudo ./gradlew`

**Hỏi:** Dùng sudo để chữa Permission denied có rủi ro gì?

**Đáp án:** Nâng quyền build scripts/plugins, tạo outputs/cache root-owned, gây lỗi cho non-root runs sau đó.

### Bài 10 — `GRADLE_USER_HOME`

**Hỏi:** Đổi user home sang directory tạm và thấy hết lỗi chứng minh cache cũ corrupt?

**Đáp án:** Chưa chắc. Nó còn đổi global properties/init scripts/Wrapper caches và môi trường khác; cần so nguyên nhân.

### Bài 11 — Daemon JVM

**Hỏi:** Java toolchain 17 có đảm bảo daemon chạy Java17 không?

**Đáp án:** Không. Daemon JVM có cấu hình và compatibility riêng.

### Bài 12 — `--no-daemon`

**Hỏi:** Flag này có đảm bảo không tạo một JVM daemon phụ nào không?

**Đáp án:** Không. Gradle có thể chạy single-use daemon.

### Bài 13 — File lock probe

**Hỏi:** Java `FileChannel.tryLock()` trả lock thành công trên file lab. Có chứng minh Gradle cache lock không bị tranh không?

**Đáp án:** Không. Nó chỉ kiểm tra file cụ thể và OS lock protocol ở thời điểm đó.

### Bài 14 — File tồn tại

**Hỏi:** Sau khi Java chương trình thoát, `lock-probe.dat` còn. Điều đó có nghĩa lock vẫn active?

**Đáp án:** Không. File existence không bằng kernel lock ownership.

### Bài 15 — Report task

**Hỏi:** Chạy `writeReport` hai lần và không đổi gì. Lần hai có thể hiện gì?

**Đáp án:** `UP-TO-DATE` khi Gradle có execution history và output snapshot hợp lệ; TaskAction không in lại `REPORT_WRITE=PASS`.

### Bài 16 — Read-only mount

**Hỏi:** Workspace là volume read-only. `chmod 777` có chữa được không?

**Đáp án:** Không. Cần writable mount hoặc workspace khác theo policy.

### Bài 17 — Java stdout

**Hỏi:** Khi `AccessProbe write build/probe` thành công, stdout?

**Đáp án:** `WRITE_TEST=PASS` cùng một newline. Khi `AccessProbe lock build/probe` không có competing lock, stdout thường `LOCK_TEST=ACQUIRED`.

### Bài 18 — Thực hành kiểm chứng

1. Tạo project Gradle Groovy DSL + Java17 theo phần 12.
2. Chạy `./gradlew writeReport`, kiểm tra file `build/diagnostics/report.txt`.
3. Chạy lại, quan sát `UP-TO-DATE` khi history hợp lệ.
4. Chạy `./gradlew run --quiet --args="write build/probe"`, đối chiếu stdout.
5. Chạy `./gradlew run --quiet --args="lock build/probe"` khi không có lock, đối chiếu stdout.
6. Compile/run `AccessProbe` độc lập bằng `javac`/`java`.
7. Dùng `./gradlew --status` và `jps -lv`, so danh sách PID.
8. Chờ job hoàn tất rồi dùng `./gradlew --stop`.
9. So sánh Gradle JVM trong IDE với terminal và Java toolchain.
10. Dùng Process Explorer/`lsof` read-only khi nghi file handle.
11. Với Windows, đo chiều dài workspace absolute path và thử root ngắn trong môi trường cho phép.
12. Xây checklist CI dùng private writable Gradle User Home cho từng job.
13. Viết báo cáo phân biệt cache lock, access denied, file too long, daemon connection và disk quota.
14. Trình bày cách xử lý không xóa global cache hoặc giết process bừa bãi.

**Tiêu chí đạt:** Phân biệt đúng bốn nguyên nhân, biết đọc PID/log/ACL, hiểu caveat long paths và có Java17 diagnostic lab không phá dữ liệu.

## 16. Checklist hỗ trợ IDE/Gradle

- [ ] Có full exception/path/PID/Gradle version, không chỉ thông báo cuối.
- [ ] Xác định chính xác `build`, project `.gradle` hay Gradle User Home.
- [ ] Kiểm tra IDE sync/Run/Debug và terminal builds đang chạy.
- [ ] Nhớ `--status` chỉ hiện cùng Gradle version.
- [ ] Đối chiếu `jps -lv`/OS process list khi có JVM versions khác.
- [ ] Đọc đúng daemon log PID/version.
- [ ] Chỉ `--stop` sau khi không còn build cần giữ.
- [ ] Không kill all Java processes.
- [ ] Không xóa `*.lock` đang hoạt động.
- [ ] Không xóa toàn bộ `~/.gradle` như bước đầu.
- [ ] Tìm Windows handles bằng Process Explorer/Handle/Resource Monitor.
- [ ] Kiểm tra POSIX modes/ACL và parent directory execute/write.
- [ ] Kiểm tra NTFS ACL/share flags/file attributes.
- [ ] Xem readonly mount/quota/disk inodes.
- [ ] Tránh chạy Gradle bằng root/Administrator như workaround.
- [ ] Không chmod 777/Everyone Full Control.
- [ ] Với Windows, hiểu MAX_PATH/longPathAware không tự sửa mọi tool.
- [ ] Ưu tiên project local path ngắn thay OneDrive/cloud synced path.
- [ ] Không tắt antivirus diện rộng.
- [ ] Mỗi CI job có workspace/private writable Gradle User Home.
- [ ] Không chia sẻ writable dependency cache qua isolated containers.
- [ ] Phân biệt Java toolchain vs Gradle daemon JVM vs IDE Gradle JVM.
- [ ] Test có kiểm soát `--no-parallel`/`--max-workers=1` nếu nghi concurrency.
- [ ] Dùng `--no-configuration-cache` để tách thử vấn đề configuration cache, không coi là giải pháp quyền truy cập.
- [ ] Ghi lại giải pháp/điều kiện để tránh lỗi lặp lại.

## 17. Tài liệu chính thức

- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): daemon lifecycle, `--status`, `--stop`, PID/JVM và logs.
- [Gradle — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html): daemon connection issues và Gradle errors.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--info`, `--stacktrace`, `--no-daemon`, parallel/worker flags.
- [Gradle — Dependency Caching](https://docs.gradle.org/current/userguide/dependency_caching.html): cache locking và điều kiện chia sẻ giữa Gradle processes.
- [Gradle — Gradle-managed Directories and Caches](https://docs.gradle.org/current/userguide/directory_layout.html): project .gradle, Gradle User Home, module caches và daemon logs.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): JAVA_HOME, GRADLE_USER_HOME, JVM args.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): compiler/test toolchains vs daemon.
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): Gradle User Home credentials và access permissions.
- [Microsoft Learn — Maximum Path Length Limitation](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation): MAX_PATH, LongPathsEnabled và longPathAware.
- [Microsoft Sysinternals — Process Explorer](https://learn.microsoft.com/en-us/sysinternals/downloads/process-explorer): xác định process đang mở file.
- [Microsoft Sysinternals — Handle](https://learn.microsoft.com/en-us/sysinternals/downloads/handle): command-line file-handle diagnosis.
- [Java 17 FileChannel API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): tryLock, FileLock semantics.
- [Java 17 Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): create/write/read/delete trên filesystem.
