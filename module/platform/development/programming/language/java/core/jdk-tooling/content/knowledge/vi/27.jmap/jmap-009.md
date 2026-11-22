# Quyền tạo dump bằng jmap

`jmap` có thể kết nối tới một JVM đang chạy và ghi heap thành file HPROF. Lệnh tạo dump chỉ thành công khi hai điều kiện độc lập cùng được đáp ứng: người vận hành có quyền attach vào tiến trình Java, và tài khoản chạy JVM có thể tạo file trong thư mục đích. Có quyền chạy `jmap` trên máy chưa đủ nếu tiến trình thuộc tài khoản khác hoặc thư mục dump không cho phép ghi.

Trong JDK hiện đại, Oracle khuyến nghị dùng `jcmd` cho chẩn đoán tiến trình đang chạy. `jmap` vẫn hữu ích để hiểu cú pháp cũ và xử lý hệ thống hiện có, nhưng Oracle xếp `jmap` vào nhóm công cụ experimental/unsupported và khuyên chuyển sang `jcmd`. Nội dung dưới đây giải thích cả hai để bạn có thể chọn đúng công cụ và cấp quyền đúng phạm vi.

## 1. Dump là gì và đang tạo loại dump nào?

Từ “dump” thường được dùng cho nhiều loại tệp khác nhau. Cần xác định loại dữ liệu cần thu thập trước khi cấp quyền hoặc chọn lệnh.

| Loại dump | Nội dung | Công cụ thường dùng | Mục đích |
| --- | --- | --- | --- |
| Heap dump (`.hprof`) | Object đang nằm trong Java heap, trường tham chiếu và quan hệ giữ object sống | `jmap -dump`, `jcmd GC.heap_dump`, `-XX:+HeapDumpOnOutOfMemoryError` | Điều tra memory leak, object tăng bất thường và `OutOfMemoryError` |
| Heap histogram | Số lượng object và tổng dung lượng theo class | `jmap -histo`, `jcmd GC.class_histogram` | Tìm class chiếm nhiều heap trước khi tạo heap dump lớn |
| Thread dump | Stack trace, trạng thái thread và có thể có thông tin lock | `jstack`, `jcmd Thread.print`, `jcmd Thread.dump_to_file` | Điều tra deadlock, thread bị block hoặc ứng dụng không phản hồi |
| Flight Recording (`.jfr`) | Sự kiện JVM theo thời gian như GC, thread, lock, allocation và CPU | `jcmd JFR.start`, `JFR.dump`, `jfr` | Xem diễn biến trước/sau sự cố và phân tích hiệu năng |
| OS core/crash dump | Memory image của tiến trình ở mức hệ điều hành, gồm cả native memory và trạng thái OS | Linux core dump, Windows crash dump, `gcore`, debugger | Điều tra crash native, lỗi JVM hoặc lỗi ở JNI |

`jmap -dump` tạo **heap dump HPROF**, không tạo OS core dump. Heap dump tập trung vào object do JVM quản lý; core dump chứa trạng thái tiến trình rộng hơn, bao gồm native memory và trạng thái hệ điều hành tại thời điểm crash. Hai loại file có kích thước, quyền truy cập và cách phân tích khác nhau.

## 2. Hai lớp quyền phải có

### Quyền attach vào JVM

Để lấy dump từ JVM đang chạy, công cụ cần kết nối được tới đúng tiến trình:

- Chạy trên cùng máy với JVM đích.
- Với `jcmd`, dùng cùng effective user ID và group ID đã khởi chạy JVM. Trên Linux, thông thường chạy bằng đúng service account.
- Dùng JDK phù hợp với JVM đích. Oracle không hỗ trợ dùng bộ `jcmd`, `jmap`, `jstack` hoặc `jinfo` từ một phiên bản JDK để chẩn đoán JVM thuộc phiên bản JDK khác.
- JVM phải cho phép Attach mechanism. Nếu JVM được khởi chạy với `-XX:+DisableAttachMechanism`, các công cụ attach như `jcmd`, `jstack`, `jmap` và `jinfo` không thể kết nối theo cách thông thường.
- PID phải thuộc đúng host/container và PID namespace. `jcmd -l` không liệt kê JVM nằm trong một Docker process riêng; trong trường hợp đó, tra PID bằng `ps` trong container hoặc chạy công cụ từ đúng container.

Quyền root hoặc quyền Administrator không nên là cách xử lý mặc định. Hãy xác định service account của ứng dụng và thực hiện thao tác chẩn đoán theo đúng identity đó. Trên Windows, một terminal được mở bằng tài khoản Administrator không nhất thiết là cùng identity với Windows Service đang chạy bằng virtual service account hoặc domain account.

### Quyền ghi file dump

Tiến trình JVM phải ghi được file vào đường dẫn được yêu cầu. Kiểm tra:

- Thư mục đích đã tồn tại; các lệnh tạo dump không phải lúc nào cũng tự tạo các thư mục cha.
- Tài khoản chạy JVM có quyền tạo file và ghi file trong thư mục.
- Trên POSIX, thư mục cần quyền write và execute cho tài khoản đó; mọi thư mục cha cũng phải cho phép traverse.
- Trên Windows, ACL của NTFS phải cấp quyền tạo/ghi file cho đúng service identity.
- Phân vùng còn đủ dung lượng, quota và giới hạn inode chưa bị chạm.
- Đường dẫn không nằm trên mount read-only hoặc network filesystem đang lỗi.
- SELinux, AppArmor, container security profile, antivirus hoặc Windows Controlled Folder Access không chặn thao tác ghi.

**Điểm cần nhớ:** lệnh attach được gửi từ tài khoản vận hành, nhưng file dump được tạo trong JVM đích. Vì vậy, phải kiểm tra quyền ghi của tài khoản chạy ứng dụng, không chỉ quyền của người gõ lệnh.

## 3. Cấp quyền cho thư mục dump

Nên tạo một thư mục riêng cho từng ứng dụng, chỉ service account và nhóm vận hành được phép truy cập. Không dùng thư mục dùng chung như `/tmp` làm nơi lưu trữ lâu dài cho heap dump production.

### Linux

Ví dụ ứng dụng chạy bằng user/group `myapp`:

```bash
APP_USER=myapp
APP_GROUP=myapp
DUMP_DIR=/var/lib/myapp/dumps

sudo install -d \
  -o "$APP_USER" \
  -g "$APP_GROUP" \
  -m 0700 \
  "$DUMP_DIR"

sudo -u "$APP_USER" test -w "$DUMP_DIR" \
  && echo "DUMP_DIR_WRITABLE"
```

`0700` cho phép chủ sở hữu đọc, ghi và truy cập thư mục; user/group khác không có quyền mặc định. Nếu nhóm SRE cần đọc dump, có thể tạo group chẩn đoán riêng và dùng `0750` hoặc ACL có kiểm soát. Không cấp `0777` chỉ để làm lệnh dump chạy được.

Kiểm tra owner, quyền trên toàn bộ đường dẫn và dung lượng:

```bash
namei -l /var/lib/myapp/dumps
stat -c '%U:%G %a %n' /var/lib/myapp/dumps
df -h /var/lib/myapp/dumps
df -i /var/lib/myapp/dumps
```

Nếu chạy bằng systemd, thư mục phải tồn tại và service account phải được cấp quyền trước khi JVM cần ghi dump. Có thể dùng `StateDirectory=myapp` trong unit file để systemd tạo state directory theo chính sách của service; vẫn cần kiểm tra owner/mode thực tế.

### Windows

Ví dụ Windows Service chạy bằng virtual account `NT SERVICE\MyApp`:

```powershell
$dumpDir = 'C:\ProgramData\MyApp\dumps'

New-Item -ItemType Directory -Force -Path $dumpDir | Out-Null

icacls $dumpDir /grant 'NT SERVICE\MyApp:(OI)(CI)M'
icacls $dumpDir
```

Thay `NT SERVICE\MyApp` bằng identity thực tế của service. `(OI)(CI)` cho phép quyền kế thừa xuống file và thư mục con; `M` là Modify. Chạy thao tác cấp ACL bằng tài khoản quản trị được phê duyệt. Sau đó xác nhận JVM thực sự chạy dưới identity đã được cấp quyền và đường dẫn tồn tại trên máy/volume mà service nhìn thấy.

## 4. Tạo heap dump thủ công bằng jmap

`jmap -dump` kết nối tới PID của JVM đang chạy và ghi heap ở định dạng HPROF.

Cú pháp:

```bash
jmap -dump:live,format=b,file=/var/lib/myapp/dumps/heap.hprof <PID>
```

Ý nghĩa:

- `live`: chỉ dump các object còn sống sau khi JVM xác định object unreachable.
- `format=b`: ghi HPROF binary.
- `file=...`: đường dẫn file đích.
- `<PID>`: PID của JVM cần chẩn đoán.

Nếu bỏ `live`, dump có thể bao gồm cả object unreachable. Lựa chọn `live` có thể yêu cầu Full GC và làm tiến trình tạm dừng. Heap dump có thể lớn gần bằng phần heap đang sử dụng, vì vậy hãy ước lượng dung lượng trước khi chạy.

Trên Windows PowerShell, ví dụ dùng đường dẫn không có khoảng trắng để đơn giản hóa việc truyền tham số cho công cụ:

```powershell
$pidTarget = 12345
$dumpFile = 'C:\ProgramData\MyApp\dumps\heap.hprof'

jmap.exe "-dump:live,format=b,file=$dumpFile" $pidTarget

if ($LASTEXITCODE -ne 0) {
    throw 'jmap heap dump failed'
}
```

Sau khi lệnh hoàn tất, kiểm tra file tồn tại, kích thước lớn hơn 0 và đúng thư mục. Nếu dùng một file name đã tồn tại, hãy chọn tên mới hoặc xử lý file cũ theo retention policy; không ghi đè dump cần giữ để điều tra.

### Dùng jcmd cho JDK hiện đại

Oracle khuyến nghị `jcmd` thay cho các công cụ cũ `jmap`, `jstack` và `jinfo`. Lệnh tương đương:

```bash
jcmd <PID> help GC.heap_dump

jcmd <PID> GC.heap_dump \
  -gz=1 \
  /var/lib/myapp/dumps/heap.hprof.gz
```

`GC.heap_dump` ghi HPROF. `-gz=1` bật gzip nhanh; mức `1` ưu tiên tốc độ, mức `9` nén mạnh hơn nhưng tốn CPU hơn. Mặc định lệnh yêu cầu Full GC trước khi dump; tùy chọn `-all` yêu cầu ghi cả object unreachable và thay đổi hành vi đó. Đây là lệnh có impact cao theo tài liệu JDK, nên tránh chạy lặp lại không cần thiết trên hệ thống đang tải cao.

`jcmd` cũng tạo thread dump ra file:

```bash
jcmd <PID> Thread.dump_to_file \
  -format=json \
  /var/lib/myapp/dumps/threads.json
```

Với Flight Recorder, có thể bắt đầu recording và lưu một snapshot:

```bash
jcmd <PID> JFR.start \
  name=incident \
  settings=default \
  filename=/var/lib/myapp/dumps/incident.jfr \
  maxsize=256m

jcmd <PID> JFR.dump \
  name=incident \
  filename=/var/lib/myapp/dumps/incident-snapshot.jfr
```

`JFR.dump` ghi dữ liệu hiện có ra file trong khi recording tiếp tục chạy. Đặt `maxsize` và `maxage` phù hợp để giới hạn lượng dữ liệu lưu trên disk. Dùng `jfr summary` để kiểm tra file recording sau khi thu thập.

## 5. Tự động tạo heap dump khi OutOfMemoryError

Nếu ứng dụng cần thu thập heap dump khi Java heap hết chỗ, cấu hình JVM lúc khởi động:

```bash
java \
  -Xmx2g \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/lib/myapp/dumps \
  -XX:ErrorFile=/var/log/myapp/hs_err_pid%p.log \
  -jar myapp.jar
```

- `-XX:+HeapDumpOnOutOfMemoryError` bật heap dump khi xảy ra `OutOfMemoryError` liên quan Java heap.
- `-XX:HeapDumpPath` chỉ định thư mục hoặc tên file heap dump. Khi truyền một thư mục có sẵn, HotSpot tạo file `java_pid<PID>.hprof` trong thư mục đó.
- `-XX:ErrorFile` chỉ định fatal error log khi JVM gặp lỗi nghiêm trọng. File `hs_err` là log chẩn đoán, không phải heap dump.

Tạo thư mục và cấp quyền trước khi khởi động service. Nếu `HeapDumpPath` không ghi được, JVM không thể lưu heap dump vào vị trí mong muốn. Đừng dựa vào working directory ngẫu nhiên của service vì nó có thể khác khi chạy từ terminal, systemd hoặc Windows Service.

`-XX:+HeapDumpOnOutOfMemoryError` chỉ áp dụng cho OutOfMemoryError; nó không thay thế cơ chế OS core dump khi tiến trình JVM crash do native fault. Heap dump và fatal error log cũng cần dung lượng riêng.

## 6. Quyền tạo OS core dump

Khi cần phân tích crash ở mức native/JVM, cần OS core dump thay vì chỉ HPROF. Trên Linux, việc tạo core file phụ thuộc giới hạn process và cấu hình kernel.

Kiểm tra giới hạn của shell:

```bash
ulimit -c
```

Nếu chính sách vận hành cho phép tạo core dump, cấu hình giới hạn trước khi khởi chạy JVM:

```bash
ulimit -c unlimited
java -jar myapp.jar
```

Với systemd service, giới hạn của tiến trình do service manager đặt; cấu hình `LimitCORE=infinity` trong unit file nếu được quản trị viên phê duyệt. Kiểm tra `kernel.core_pattern` để biết kernel ghi core file trực tiếp vào đâu hay chuyển cho một collector. Nếu dùng systemd-coredump, tra cứu bằng `coredumpctl` theo quy trình của máy chủ.

Một số nguyên nhân phổ biến khiến core dump không xuất hiện:

- Core size limit bằng `0` hoặc quá thấp.
- Service account không thể ghi vào working directory hoặc thư mục đích.
- Disk đầy, quota hết hoặc network filesystem không sẵn sàng.
- Đã tồn tại file `core` không ghi được hoặc có thư mục tên `core` cản trở tên file.
- Chương trình chạy với setuid hoặc chính sách kernel hạn chế core dump.
- JVM xử lý một số tín hiệu nội bộ như `SIGSEGV` cho mục đích riêng; không phải mọi lần nhận tín hiệu đều tạo core file.

Trên Windows, crash dump do cơ chế chẩn đoán của hệ điều hành/debugger quản lý. Quyền ghi và vị trí dump phụ thuộc cấu hình Windows Error Reporting hoặc công cụ debugger đã được tổ chức triển khai. `jmap -dump` vẫn là thao tác tạo Java heap dump trong JVM, khác với Windows process crash dump.

Với core file đã có, `jhsdb jmap --core` có thể phân tích heap từ trạng thái postmortem. `jhsdb` là công cụ experimental; attach vào JVM đang chạy có thể khiến tiến trình treo và có khả năng crash khi debugger detach. Không dùng nó thay cho `jcmd` trong quy trình dump heap thông thường.

## 7. Ví dụ kiểm tra end-to-end trên Java 17+

Chương trình dưới đây giữ lại một số mảng byte để heap có dữ liệu quan sát được, sau đó tiếp tục chạy để có thể attach.

Tạo `DumpTarget.java`:

```java
package com.example;

import java.util.ArrayList;
import java.util.List;

public final class DumpTarget {
    private static final List<byte[]> RETAINED = new ArrayList<>();

    private DumpTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        for (int i = 0; i < 32; i++) {
            RETAINED.add(new byte[256 * 1024]);
        }

        System.out.println("DUMP_TARGET_READY");

        while (true) {
            Thread.sleep(1_000);
        }
    }
}
```

Compile và chạy trên Linux:

```bash
mkdir -p build/dump-demo
javac --release 17 -d build/dump-demo DumpTarget.java

java -cp build/dump-demo com.example.DumpTarget \
  > build/dump-demo/application.log 2>&1 &
APP_PID=$!

jps -lv
```

Giả sử PID của ứng dụng là `12345`. Tạo thư mục riêng và cấp quyền trước khi gửi lệnh:

```bash
sudo install -d -o myapp -g myapp -m 0700 \
  /var/lib/myapp/dumps

sudo -u myapp test -w /var/lib/myapp/dumps

sudo -u myapp jcmd 12345 GC.heap_dump -gz=1 \
  /var/lib/myapp/dumps/heap.hprof.gz
```

Kiểm tra file:

```bash
sudo -u myapp test -s /var/lib/myapp/dumps/heap.hprof.gz
ls -lh /var/lib/myapp/dumps
```

Nếu lệnh báo `Permission denied`, hãy kiểm tra identity của JVM và quyền ghi thư mục bằng `namei -l`, `stat`, ACL/SELinux/AppArmor. Không đổi thư mục thành `0777` để bỏ qua lỗi.

### Kết quả kiểm thử thực tế

Trên Windows 11 với Azul Zulu JDK 24.0.2, cùng một JVM demo được chạy dưới tài khoản hiện tại. Các thao tác sau đã thực hiện thành công trong một thư mục kiểm thử riêng:

| Thao tác | Kết quả |
| --- | --- |
| `jmap -dump:format=b,file=... <PID>` | Tạo HPROF khoảng 10,9 MB |
| `jcmd <PID> GC.heap_dump -gz=1 ...` | Tạo HPROF gzip khoảng 1,3 MB |
| `jcmd <PID> Thread.dump_to_file -format=json ...` | Tạo thread dump JSON |
| `jcmd <PID> JFR.start` và `JFR.dump` | Tạo JFR recording; `jfr summary` đọc được |
| `-XX:+HeapDumpOnOutOfMemoryError` với `-XX:HeapDumpPath=<thư mục>` | OOM test tạo `java_pid<PID>.hprof` khoảng 19,4 MB |

Các con số chỉ là kết quả của chương trình demo nhỏ, không phải kích thước dự kiến cho ứng dụng production. Mọi file và tiến trình kiểm thử đã được dọn sau khi xác minh.

## 8. Bảo vệ dump vì dữ liệu có thể rất nhạy cảm

Heap dump và core dump có thể chứa dữ liệu gần như đầy đủ trong bộ nhớ tiến trình. Chúng có thể bao gồm:

- Password, access token, refresh token, session cookie và API key.
- Dữ liệu cá nhân, request/response, nội dung giao dịch và dữ liệu cache.
- Khóa mã hóa, thông tin xác thực database và cấu hình nội bộ.
- Nội dung object của ứng dụng, URL, SQL, payload hoặc thông tin khách hàng.

Thread dump có thể lộ tên thread, class, stack trace, đường dẫn và một số giá trị được ghi vào log. JFR có thể chứa system properties, environment metadata, thread names và stack traces tùy event settings.

Áp dụng các nguyên tắc sau:

1. Chỉ service account và nhóm incident được phê duyệt có quyền đọc dump.
2. Lưu dump ở volume riêng, có mã hóa at rest và kiểm soát quyền truy cập.
3. Không upload heap/core dump vào public artifact, thư mục web server hoặc ticket không có phân quyền.
4. Chuyển file qua kênh bảo mật; xác minh checksum sau khi truyền.
5. Đặt retention ngắn, ghi nhận người truy cập và xóa file sau khi hoàn tất điều tra.
6. Không bật `-overwrite` trừ khi đã xác định rõ file cũ có thể bị thay thế.
7. Không gửi password, token hoặc keystore trong command line/log để phục vụ việc dump.

Dump là dữ liệu production nhạy cảm; quyền tạo và quyền đọc dump nên được cấp riêng theo nguyên tắc least privilege.

## 9. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `jmap` hoặc `jcmd` không tìm thấy PID | Sai PID, PID namespace khác hoặc JVM chạy trong Docker riêng | Kiểm tra bằng `ps` trong đúng host/container; dùng PID của namespace đích |
| `AttachNotSupportedException` | Khác effective UID/GID, attach bị tắt hoặc JVM không hỗ trợ attach | Dùng đúng service identity, kiểm tra `-XX:+DisableAttachMechanism`, dùng JDK tương ứng |
| `Permission denied` khi tạo dump | JVM account không ghi được thư mục hoặc OS security policy chặn | Kiểm tra owner, mode, NTFS ACL, SELinux/AppArmor và quyền trên thư mục cha |
| `No such file or directory` | Thư mục dump chưa tồn tại hoặc không được mount vào container | Tạo thư mục trước khi khởi động; kiểm tra mount/path trong namespace JVM |
| `Not enough space` hoặc dump bị thiếu | Disk/quota/inode hết hoặc giới hạn core file quá thấp | Kiểm tra `df -h`, `df -i`, quota, `ulimit -c` và retention |
| `jmap` không phản hồi | Công cụ cũ hoặc tiến trình đang treo/GC lâu | Ưu tiên `jcmd`; cân nhắc impact của Full GC và heap size |
| File dump không xuất hiện khi OOM | JVM thực tế không có flag, path sai hoặc không ghi được | Kiểm tra command line JVM, `HeapDumpOnOutOfMemoryError`, `HeapDumpPath` và quyền service account |
| Có `hs_err_pid*.log` nhưng không có `.hprof` | Fatal error log và heap dump là hai cơ chế khác nhau | Kiểm tra `HeapDumpOnOutOfMemoryError` và loại lỗi đã xảy ra |
| Core dump không xuất hiện | `ulimit -c`, `core_pattern`, quyền thư mục hoặc kernel policy | Kiểm tra cấu hình OS và service manager; không nhầm với HPROF |
| File tồn tại nhưng không mở được | File ghi dở, thiếu dung lượng, truyền lỗi hoặc công cụ phân tích không tương thích | Kiểm tra kích thước, checksum, định dạng và bản JDK/tool phân tích |

## 10. Checklist trước khi tạo dump production

1. Xác định đang cần heap dump, thread dump, JFR hay OS core dump.
2. Xác định PID, host/container và JDK thực tế của JVM đích.
3. Xác định service account và effective UID/GID của JVM.
4. Kiểm tra Attach mechanism không bị vô hiệu hóa.
5. Tạo thư mục đích trước và cấp quyền ghi cho JVM account.
6. Kiểm tra disk space, quota, inode và giới hạn core dump.
7. Chọn tên file duy nhất, có incident ID và timestamp.
8. Ước lượng impact của Full GC và kích thước heap trước khi tạo HPROF.
9. Chạy một lệnh dump, kiểm tra exit code và file size.
10. Xác minh HPROF/JFR có thể mở được bằng công cụ phân tích phù hợp.
11. Giới hạn quyền đọc, mã hóa, audit và retention của file.
12. Ghi lại JDK version, PID, command, thời điểm, người thực hiện và checksum.

## 11. Ghi nhớ

- `jmap -dump` tạo Java heap dump HPROF; nó không tạo OS core dump.
- Muốn tạo dump cần quyền attach tới JVM và quyền ghi của tài khoản chạy JVM trên thư mục đích.
- `jcmd` yêu cầu cùng máy và cùng effective UID/GID; `-XX:+DisableAttachMechanism` vô hiệu hóa các công cụ attach.
- Oracle khuyến nghị dùng `jcmd` thay cho `jmap` vì `jmap` thuộc nhóm công cụ experimental/unsupported.
- `-XX:+HeapDumpOnOutOfMemoryError` và `-XX:HeapDumpPath` cho phép tạo heap dump tự động khi Java heap OOM.
- Linux core dump còn phụ thuộc `ulimit -c`, `core_pattern`, working directory và chính sách kernel.
- JDK 24 trở lên đã vô hiệu hóa Security Manager; không thể sửa lỗi attach bằng cách thêm grant vào `java.policy`.
- Heap/core dump có thể chứa bí mật và dữ liệu khách hàng; chỉ cấp quyền cho người cần điều tra, lưu có mã hóa và xóa theo retention policy.

Khi identity của JVM, quyền attach và quyền ghi thư mục đều được kiểm tra trước, việc tạo dump trở thành thao tác chẩn đoán có kiểm soát. Nhóm có thể thu thập bằng chứng cần thiết mà không phải cấp quyền quá rộng cho toàn bộ máy chủ.

## Tài liệu tham khảo

- [Oracle JDK 24: Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 24: The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Oracle JDK 24: The java Command and HeapDumpPath](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Oracle JDK 24: Prepare Java for Troubleshooting](https://docs.oracle.com/en/java/javase/24/troubleshoot/prepare-java-troubleshooting.html)
- [Oracle JDK 24: Submit a Bug Report and Collect Core Dumps](https://docs.oracle.com/en/java/javase/24/troubleshoot/submit-bug-report.html)
- [Oracle JDK 24: The jhsdb Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jhsdb.html)
- [Oracle: The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/27/security/security-manager-is-permanently-disabled.html)
