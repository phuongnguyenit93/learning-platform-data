# 4.1 — Mô hình gửi diagnostic command tới một JVM đang chạy

## 1. Bài toán: hỏi một JVM đang hoạt động mà không khởi động lại nó

Giả sử một ứng dụng Java đã chạy nhiều giờ và bắt đầu phản hồi chậm. Người vận hành cần biết JVM đang dùng phiên bản nào, những thread nào đang chờ lock, heap đang ra sao hoặc có Java Flight Recorder (JFR) nào đang hoạt động. Khởi động một chương trình Java khác rồi in thông tin của **chính chương trình mới** không trả lời được câu hỏi về JVM đang gặp sự cố.

**`jcmd`** là công cụ đi kèm JDK, dùng để **gửi yêu cầu diagnostic command đến một tiến trình JVM đang chạy**. Trong các bản HotSpot JDK, tiến trình `jcmd` kết nối qua cơ chế attach cục bộ, yêu cầu JVM đích thực thi một lệnh mà nó hỗ trợ, rồi nhận kết quả hoặc thông báo lỗi. Mỗi lệnh có tác dụng và mức ảnh hưởng riêng.

Sau bài này, người học cần nắm được:

1. Vai trò của **client `jcmd`**, **PID của JVM đích**, **kênh attach**, **bộ xử lý diagnostic command** và **kết quả**.
2. Chu trình từ chọn đúng JVM, mở kết nối, gửi tên lệnh/tham số đến xử lý và nhận phản hồi.
3. Cú pháp chọn đích, xem danh sách lệnh và trợ giúp của chính JVM đích; phân biệt lệnh đọc thông tin với lệnh thay đổi trạng thái hoặc tạo dữ liệu lớn.
4. Cách thực hành an toàn trên JDK 17+, xử lý khi attach thất bại, và những giới hạn trong host/container.

> **Luận điểm trung tâm:** `jcmd` là một **client gửi yêu cầu đến JVM đã tồn tại**. Nó không chạy method của ứng dụng theo ý muốn, không yêu cầu mở cổng JMX và không đảm bảo mọi lệnh đều nhẹ hoặc hoàn toàn chỉ đọc.

## 2. Các thành phần trong mô hình

| Thành phần | Vai trò | Cần tránh nhầm với |
| --- | --- | --- |
| Người vận hành / terminal | Chọn đúng máy, PID, lệnh và thời điểm thu thập | Người dùng đăng nhập không nhất thiết là owner của JVM |
| `jcmd` client | Tiến trình công cụ JDK riêng biệt, phân tích tham số, gửi yêu cầu và xuất kết quả | JVM ứng dụng đích |
| PID, host, PID namespace | Định vị **phiên tiến trình** mà lệnh sẽ hướng đến | Tên main class/JAR hay PID của một container khác |
| Attach mechanism | Kênh liên lạc **cục bộ** do runtime và OS cung cấp, chịu kiểm soát quyền truy cập | HTTP endpoint, JMX remote port hoặc một API nghiệp vụ |
| Diagnostic-command dispatcher trong JVM | Nhận tên lệnh, đối chiếu các command có sẵn, tham số/quyền và gọi cơ chế phục vụ chẩn đoán tương ứng | Bộ thực thi mọi đoạn Java code tùy ý |
| Bộ phận JVM thực hiện lệnh | Có thể truy vấn VM state, in thread, điều khiển JFR, ghi heap dump, chỉnh một số thiết lập | Một nhóm lệnh có impact như nhau |
| Phản hồi và side effect | Văn bản/error trả về client; đôi khi JVM thay đổi trạng thái hoặc ghi file | Mọi lệnh đều chỉ trả stdout, không tạo tác dụng phụ |

Sơ đồ luồng đơn giản:

```text
Terminal trên đúng host / namespace
    |
    | jcmd <PID> <DiagnosticCommand> [arguments/options]
    v
Tiến trình jcmd (client JDK)
    |
    | Kiểm tra đích, sử dụng local attach mechanism
    v
JVM đang chạy (PID mục tiêu)
    |
    | Tra cứu command đã đăng ký; kiểm tra cú pháp, quyền,
    | thực thi thao tác chẩn đoán trong bối cảnh JVM đích
    v
Kết quả / lỗi / thay đổi trạng thái / file do JVM tạo
    |
    | Phản hồi qua kết nối attach (đối với output tương ứng)
    v
jcmd in kết quả về stdout/stderr của terminal
```

Trong sơ đồ, **không có JVM thứ ba để “chạy hộ” ứng dụng**: `jcmd` là process công cụ; còn thông tin thread, heap và JFR được JVM đích cung cấp qua các cơ chế phục vụ chẩn đoán của nó.

### 2.1. Những gì cần phân biệt

- **`jcmd -l`** là thao tác *liệt kê tiến trình JVM nhìn thấy được*, để khám phá ứng viên. Đây chưa phải lệnh như `VM.version` gửi đến một PID cụ thể.
- **`jcmd <PID> help`** hỏi JVM đích xem **runtime hiện tại có những diagnostic command nào**; đừng suy ra danh sách cố định cho mọi vendor/JDK.
- **`jcmd <PID> VM.version`** là yêu cầu có đích và tên lệnh rõ ràng; dữ liệu phiên bản do JVM đích trả lời.
- **`java -version`** chạy Java launcher được tìm thấy trong terminal hiện tại; nó có thể khác JDK của ứng dụng đích.
- **JMX/JMC/JFR** liên quan đến chẩn đoán nhưng khác vai trò: JMX cung cấp cơ chế quản trị/monitoring, JFR là hệ thống ghi sự kiện; `jcmd` có các diagnostic command để quản lý JFR từ bên ngoài. `jcmd` không cần phải mở JMX remote port để gửi yêu cầu cục bộ.

## 3. Chu trình gửi một diagnostic command

### Bước 1 — Xác nhận JVM đích

Chọn đúng **host**, **namespace/container**, **PID**, **thời điểm khởi động**, **owner** và **lệnh chạy ứng dụng**. PID có thể tái sử dụng sau khi process kết thúc. Với nhiều bản replica, tên main class hoặc JAR cũng có thể trùng nhau.

```bash
jcmd -l
```

Output thường có PID và tên main class/JAR hoặc command line của JVM nhìn thấy được. **Không mặc định `jcmd -l` thấy mọi JVM**, đặc biệt khi process ở container khác, thiếu quyền hoặc runtime không hỗ trợ cơ chế khám phá tương ứng.

Ví dụ minh họa:

```text
18432 com.example.OrderService
18597 com.example.BatchJob
```

Đây là **ví dụ định dạng**, không phải stdout cố định trên mọi JDK. Cần đối chiếu ứng viên với công cụ hệ điều hành hoặc service manager. Tránh trộn PID **trong container** với PID **trên host**.

### Bước 2 — Client tìm và kết nối đến JVM có thể attach

`jcmd` hoạt động trên **máy chứa JVM đích** theo tài liệu JDK 17, với cùng **effective user và group** được dùng để chạy JVM. Đây là điều kiện của cơ chế attach trên HotSpot được tài liệu hóa; chính sách OS, container isolation hoặc cấu hình runtime có thể áp đặt thêm giới hạn.

Ở một số nền tảng HotSpot, attach listener có thể được khởi tạo khi có yêu cầu và sử dụng cơ chế IPC của OS (chẳng hạn socket cục bộ trên Unix). Chi tiết file/socket, tín hiệu và handshake là **chi tiết triển khai phụ thuộc OS và phiên bản JVM**, không phải giao thức công cộng để tự lập trình thay thế `jcmd`.

Không cần biết địa chỉ port HTTP/JMX. Ngược lại, chạy `jcmd` trên laptop **không tự gửi lệnh qua mạng** đến PID trên server: phải dùng công cụ tại host hoặc môi trường chẩn đoán đã được cho phép.

### Bước 3 — JVM đích tra cứu command và tham số

JVM xác định tên diagnostic command, ví dụ `VM.uptime` hoặc `Thread.print`, rồi xử lý các tùy chọn được hỗ trợ. **Mỗi JVM quyết định command nào đang sẵn có** và cách diễn giải tham số. Dùng đúng phiên bản công cụ/JDK tương thích với runtime; nhà cung cấp JDK không hỗ trợ việc trộn tùy tiện phiên bản công cụ và JVM đích.

Hỏi danh sách và trợ giúp:

```bash
jcmd 18432 help
jcmd 18432 help VM.uptime
jcmd 18432 help Thread.print
```

Một mục `help <command>` thường trình bày **description**, **impact**, **syntax**, **options/arguments** và, nếu có, yêu cầu permission. `Impact: Low/Medium/High` phản ánh đánh giá của runtime về thao tác; **Low không đồng nghĩa “hoàn toàn miễn phí”**, còn tác động thực tế phụ thuộc heap size, thread count, tải và cấu hình.

### Bước 4 — JVM thực thi thao tác và tạo phản hồi

Có các kiểu kết quả khác nhau:

- **Trả dữ liệu trực tiếp**: `VM.version`, `VM.uptime`, `VM.command_line`, `VM.flags` in thông tin JVM hiện tại.
- **Tạo snapshot có chi phí**: `Thread.print` lấy thread stacks; `GC.class_histogram` kiểm tra heap; `GC.heap_dump` tạo file HPROF.
- **Thay đổi trạng thái chẩn đoán**: `JFR.start`, `JFR.stop`, `VM.log` hoặc một số `VM.set_flag` thay đổi hoạt động/chế độ theo dõi runtime.
- **Ghi file tại JVM đích**: `GC.heap_dump /path/file.hprof` và `JFR.dump filename=/path/file.jfr` yêu cầu JVM tạo file theo đường dẫn nó nhìn thấy.

Một số lệnh có thể làm tăng latency, GC pressure, I/O hoặc chiếm đĩa. **Chỉ định tên lệnh hợp lệ không có nghĩa đã được phép dùng trên production**; hãy xem impact và phạm vi thao tác trước.

### Bước 5 — Client in kết quả, kết thúc; JVM tiếp tục sống

`jcmd` thường in header có PID rồi nội dung do JVM trả về hoặc lỗi của công cụ. Khi câu lệnh kết thúc, **tiến trình client `jcmd` kết thúc**; JVM ứng dụng vẫn chạy, trừ khi một thao tác/chính trạng thái ứng dụng làm nó dừng. File do JVM tạo, recording đã bật hoặc cấu hình logging đã thay đổi có thể còn tồn tại sau khi client thoát.

Không phải output nào cũng có schema cố định để parser tùy tiện đọc: trường, phiên bản và cách trình bày có thể thay đổi. Với automation, kiểm tra exit status, tính đầy đủ của dữ liệu và phiên bản runtime trước khi dùng output để quyết định.

## 4. Cú pháp cần thành thạo

```text
jcmd -l
jcmd -h
jcmd <pid> help
jcmd <pid> help <DiagnosticCommand>
jcmd <pid> <DiagnosticCommand> [options/arguments]
jcmd <pid> -f <command-file>
```

Một quy trình đọc thông tin từ JVM tại PID `18432`:

```bash
jcmd 18432 help
jcmd 18432 VM.version
jcmd 18432 VM.uptime
jcmd 18432 VM.command_line
jcmd 18432 help Thread.print
```

**Giải thích:**

- `VM.version` cho biết runtime/version của **JVM đích**, không phải JDK tại `PATH` của shell.
- `VM.uptime` cho biết thời gian JVM đã chạy tại thời điểm hỏi. Nó giúp đối chiếu start time, nhưng **không** tự xác định service identity.
- `VM.command_line` cho biết cách JVM được khởi động (Java command/JVM arguments); thông tin có thể chứa cấu hình nhạy cảm, vì vậy không đổ thẳng vào hệ thống log công khai.
- `help Thread.print` trả hướng dẫn của JVM đích trước khi thu thập thread stacks.
- `<pid>` là **giá trị ví dụ cần thay bằng PID thực**. Trong command chạy thật, không gõ dấu ngoặc nhọn hay góc.

### 4.1. Vì sao nên dùng PID thay cho main class?

Theo cú pháp `jcmd`, đối số đầu có thể là PID **hoặc main-class**. Dùng main-class có thể match **nhiều** tiến trình có cùng tên; chọn PID cụ thể giúp thu hẹp đích một cách rõ ràng.

`jcmd 0 <command>` được tài liệu định nghĩa là có thể gửi command tới **tất cả Java processes khả dụng**. Vì thế:

- Không dùng `0` khi chỉ cần chẩn đoán một ứng dụng.
- Không dùng tên main class ngắn khi nhiều JVM trùng tên.
- Không coi PID là định danh vĩnh viễn: đọc lại process start time ngay trước lệnh có impact.
- Không tự thay PID container bằng PID host nếu chưa xác định ánh xạ namespace.

### 4.2. Tham số: phải theo help của chính command

Diagnostic command **không dùng chung một bộ options toàn cục**. Ví dụ, trên HotSpot JDK 17, `Thread.print` hỗ trợ `-l` để hiển thị thêm các khóa `java.util.concurrent`:

```bash
jcmd 18432 Thread.print -l
```

Trong khi `JFR.start` sử dụng tham số tên/giá trị như `name=...`, `settings=...`, `duration=...`. Những chuỗi có khoảng trắng hoặc dấu đặc biệt cần được quote đúng theo **shell đang sử dụng** và cú pháp của `jcmd`. Tránh đoán options dựa trên lệnh của phiên bản khác; dùng:

```bash
jcmd 18432 help JFR.start
```

Đối với command hỗ trợ các tùy chọn Boolean, cú pháp có thể dùng dạng `-option` hoặc `-option=true` theo help của lệnh cụ thể. Một tên trông giống JVM startup flag **không nhất thiết là diagnostic command**.

### 4.3. Gửi nhiều diagnostic command từ file

`jcmd` hỗ trợ đọc lệnh từ file **ở phía client**:

```text
VM.version
VM.uptime
VM.command_line
```

Lưu ba dòng trên thành file `commands.txt`, sau đó chạy:

```bash
jcmd 18432 -f commands.txt
```

`-f` không biến những lệnh này thành một transaction nguyên tử: process có thể restart hoặc trạng thái JVM thay đổi giữa các command. Không đưa dump nặng hay lệnh thay đổi cấu hình vào danh sách tự động mà chưa đánh giá impact. File `commands.txt` được `jcmd` đọc theo filesystem của **client**, khác với đường dẫn output của `GC.heap_dump` do **JVM đích** tạo.

## 5. Nhóm diagnostic command theo mức tác động

| Lệnh trên HotSpot JDK 17 | Việc thực hiện | Gợi ý sử dụng | Lưu ý |
| --- | --- | --- | --- |
| `help` / `help <command>` | Hiển thị command, syntax, impact | **Bắt đầu ở đây** | Danh sách thay đổi theo JVM/version |
| `VM.version` | In thông tin JVM/JDK | Xác nhận runtime đích | Thông tin, impact thấp |
| `VM.uptime` | In thời gian chạy JVM | Kiểm tra phiên tiến trình | Không tự khẳng định service identity |
| `VM.command_line` | In launch settings | Xác minh đích/cấu hình | Có thể chứa secret trong arguments/properties |
| `VM.flags` | In runtime flags | Đối chiếu cấu hình | Không phải lệnh thay đổi flags |
| `Thread.print -l` | In stacks, lock details | Nghi thread bị block/deadlock | Impact trung bình, tăng theo số thread |
| `GC.heap_info` | In thông tin heap tổng quát | Tìm dấu hiệu dung lượng heap | Impact trung bình theo tài liệu |
| `GC.class_histogram` | Thống kê class/instance | Nghi giữ object hoặc phân bố heap | Impact cao, tùy kích thước/nội dung heap |
| `GC.heap_dump <file>` | Tạo HPROF snapshot | Phân tích object còn sống | **Impact cao**, có thể yêu cầu full GC, file lớn/chứa dữ liệu nhạy cảm |
| `JFR.check` | Xem các recording | Kiểm tra trạng thái JFR | Thường impact thấp |
| `JFR.start` / `JFR.dump` | Bật recording / ghi recording ra file | Quan sát timeline CPU/GC/lock | Command impact thấp theo help nhưng recording có overhead và dùng đĩa |
| `VM.log` / `VM.set_flag` | Có thể chỉnh log hoặc flag runtime | Điều chỉnh có chủ đích | **Thay đổi trạng thái**, không xếp vào lệnh đọc |

**Đừng xếp loại an toàn chỉ dựa trên tên:** `GC.heap_info` chỉ báo thông tin heap, còn `GC.heap_dump` ghi dump rất lớn; `VM.flags` đọc flag, nhưng `VM.set_flag` có thể thay đổi giá trị flag cho phép chỉnh động. Trước khi chạy, đọc `jcmd <pid> help <command>` để biết impact, tham số và khả năng hỗ trợ của JVM thực tế.

### File output được tạo ở đâu?

Hai lệnh sau **khác bản chất**:

```bash
# Chuyển stdout của client jcmd sang file ở shell hiện tại
jcmd 18432 Thread.print -l > threads.txt

# Yêu cầu chính JVM đích ghi HPROF vào filesystem mà JVM đích nhìn thấy
jcmd 18432 GC.heap_dump /var/tmp/app-heap.hprof
```

Ở lệnh đầu, `> threads.txt` là **shell redirection**. File thường nằm tại thư mục làm việc của shell đang chạy `jcmd` và do quyền của client/shell quyết định.

Ở lệnh thứ hai, `/var/tmp/app-heap.hprof` là **tham số của diagnostic command**. JVM đích cần nhìn thấy đường dẫn, có quyền ghi và đủ đĩa; trong container, đường dẫn này có thể nằm trong filesystem/mount của container, không phải vị trí người vận hành đang nhìn từ host. Không thực thi lệnh thứ hai như một bước quan sát mặc định: việc tạo heap dump có tác động lớn lên ứng dụng.

Tương tự, `JFR.dump filename=/var/tmp/incident.jfr` ghi file qua JVM đích. Dùng đường dẫn tuyệt đối, xác minh nơi lưu và chính sách bảo vệ dữ liệu trước khi chạy ở môi trường thật.

## 6. Thực hành JDK 17+: gửi lệnh đến JVM demo còn sống

Để thấy rõ mô hình **hai tiến trình độc lập**, tạo một JVM ứng dụng đơn giản chạy trong 60 giây và dùng terminal thứ hai gửi yêu cầu chẩn đoán tới đúng PID.

### 6.1. Chương trình Java hoàn chỉnh

Tạo file **`JcmdTarget.java`**:

```java
public class JcmdTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");
        Thread.sleep(60_000);
        System.out.println("DONE");
    }
}
```

Biên dịch và chạy trong **terminal 1** (JDK 17 hoặc mới hơn):

```bash
javac --release 17 JcmdTarget.java
java JcmdTarget
```

**Stdout chính xác của chương trình nếu được chạy tới khi hoàn tất bình thường:**

```text
READY
DONE
```

`READY` xuất hiện ngay; `DONE` xuất hiện sau khoảng 60 giây. Không có PID cố định trong stdout của chương trình vì PID phụ thuộc hệ điều hành và mỗi lần chạy.

### 6.2. Quan sát từ terminal khác

Khi terminal 1 đã in `READY`, trong **terminal 2 trên cùng host** chạy:

```bash
jcmd -l
```

Tìm process có main class `JcmdTarget` và ghi PID thực, ví dụ `18432`. Thay toàn bộ `18432` trong các lệnh sau bằng PID vừa tìm:

```bash
jcmd 18432 help
jcmd 18432 VM.version
jcmd 18432 VM.command_line
jcmd 18432 VM.uptime
jcmd 18432 help Thread.print
jcmd 18432 Thread.print -l
```

Các lệnh kiểm tra `VM.version`, `VM.command_line`, `VM.uptime` và `help Thread.print` truy vấn đúng JVM demo; `Thread.print -l` in thread snapshot của JVM đó tại thời điểm thực hiện. Nếu đợi quá 60 giây, JVM demo đã kết thúc: yêu cầu attach sẽ thất bại hoặc PID có thể thuộc process khác trong tương lai.

**Không có một output `jcmd` cố định để sao chép**: PID, JDK version, JVM uptime, số thread và stack thay đổi theo môi trường. Dấu hiệu cần kiểm tra là command được thực thi **đúng PID**, in kết quả hoặc lỗi xác định, và thread dump chứa `main` ở một call stack chờ `Thread.sleep` nếu chụp trong khoảng demo đang sleep.

### 6.3. Sau khi client thoát, JVM đích ra sao?

Chạy `jcmd 18432 VM.version` không tự dừng `JcmdTarget`. Sau khi lệnh `jcmd` kết thúc, terminal 1 vẫn chờ, rồi in `DONE` khi đủ thời gian sleep. Đây là bằng chứng trực quan rằng **vòng đời `jcmd` client và JVM đích tách biệt**.

Nếu người học chủ động dừng demo trước 60 giây bằng công cụ OS hoặc Ctrl+C, `DONE` có thể không xuất hiện; đó là **một lần chạy bị ngắt**, không làm thay đổi logic của mã nguồn.

### 6.4. Điều gì được kiểm tra thực tế?

Demo này có thể dùng trên JDK 17+. Mã đã được kiểm chứng biên dịch với `javac --release 17`; trong thử nghiệm với HotSpot/OpenJDK, các lệnh `VM.version`, `VM.command_line`, `VM.uptime` và `help Thread.print` đã được kiểm chứng trả về thành công khi JVM demo còn sống. **Số liệu output phụ thuộc runtime**, không nên hard-code trong tài liệu hoặc unit test.

## 7. Quyền attach và bề mặt bảo mật

**Attach là thao tác có đặc quyền vận hành đối với process**, không phải API ai cũng được truy cập. Với `jcmd` trong tài liệu Java SE 17, client cần chạy trên cùng máy với JVM và có cùng effective user/group đã dùng để khởi chạy nó. Có thể còn các cơ chế sandbox, file permission, security policy và namespace.

Những điều cần lưu ý:

- **Không cố chạy với account khác** chỉ vì PID có thể nhìn thấy trong `ps` hoặc Task Manager. Nhìn thấy tên process không đồng nghĩa được phép attach.
- Với HotSpot, startup option `-XX:+DisableAttachMechanism` vô hiệu hóa cơ chế attach; nếu ứng dụng cấu hình như vậy, `jcmd` có thể không kết nối được. Đây là lựa chọn runtime cần được hiểu từ phía vận hành, không phải lỗi ngẫu nhiên của lệnh.
- Java service trong container có thể không có JDK tools ở image; `jcmd -l` trên host cũng có thể không liệt kê JVM trong Docker process riêng. Cần chọn đúng nơi có quyền và PID mapping thích hợp.
- Diagnostic command có thể đọc thông tin nhạy cảm: `VM.command_line`, `VM.system_properties`, thread stack, heap dump và JFR có thể chứa tokens, chuỗi kết nối, request data hoặc định danh người dùng. Chỉ ghi, xem và chia sẻ trong phạm vi cho phép.
- Một số command thay đổi trạng thái runtime, như điều chỉnh logging/JFR/flags; không gộp chúng thành “read-only” chỉ vì cú pháp bắt đầu bằng `jcmd`.
- Không dùng tài khoản có đặc quyền rộng hoặc đặt quyền truy cập file dump quá thoáng chỉ để tiện điều tra. Giữ thời hạn lưu và cách xóa hiện vật theo chính sách vận hành.

**Attach không phải remote debugging:** không phải cứ có PID hoặc IP là gửi lệnh tới JVM trên máy khác. Remote management và debugger dùng các cơ chế riêng, có cấu hình và rủi ro riêng.

## 8. Các lỗi phổ biến khi gửi diagnostic command

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra phù hợp |
| --- | --- | --- |
| `jcmd -l` không hiển thị ứng dụng | PID namespace/container, quyền, runtime không công bố thông tin khám phá, process đã thoát | Dùng process list trên đúng host/namespace, đối chiếu service manager và PID hiện tại |
| Có PID nhưng attach thất bại | Sai user/group, attach bị disable, sandbox, cơ chế IPC, process không phản hồi | Xác minh owner/start time, JDK tương thích, runtime flags và quyền; không coi là “không có JVM” |
| “Unrecognized diagnostic command” hoặc help không có lệnh | Command không được JVM/vendor/version hỗ trợ | Hỏi `jcmd <pid> help` và help của đúng command |
| Lệnh chạy nhưng không tạo file | Đường dẫn được hiểu từ JVM đích, thiếu quyền ghi, hết dung lượng, tên file trùng | Kiểm tra filesystem/mount/quyền/đĩa từ góc nhìn target |
| Output phiên bản không như kỳ vọng | Terminal dùng Java khác runtime đích, hoặc đã chọn nhầm process | Dùng `VM.version`, OS executable và launch command |
| Command chỉ chạy sau một lúc lâu | JVM đang quá tải, command có impact lớn hoặc kết nối/điều phối bị trì hoãn | Kiểm tra mô tả impact, tải thực tế, logs và khả năng đáp ứng; tránh lặp hàng loạt |
| PID đúng lúc đầu nhưng kết quả thuộc ứng dụng khác | Process restart, PID tái sử dụng hoặc host/namespace khác | So PID **cùng start time**, owner, command ngay trước thao tác |
| Heap dump gây pause hoặc đầy đĩa | `GC.heap_dump` là thao tác nặng, không phải truy vấn nhỏ | Đánh giá kích thước heap, impact, quota/retention trước |
| `jcmd` từ JDK A gặp JVM JDK B không tương thích | Trộn tool/runtime khác version hoặc vendor | Dùng tool JDK phù hợp, xác nhận `VM.version` |
| Gõ tên command vào shell như executable | Command chỉ có ý nghĩa khi được truyền vào `jcmd` | Dùng `jcmd <pid> VM.version`, không chạy trần `VM.version` |

**Phân loại lỗi để xử lý:** (1) chưa xác định đúng **target**, (2) không thiết lập được **attach**, (3) attach được nhưng **command/arguments không hợp lệ**, (4) command chạy nhưng **không tạo output dự kiến**, (5) kết quả có nhưng **đã hiểu sai ý nghĩa hoặc thời điểm**. Mỗi lớp có cách kiểm tra khác nhau; không chữa bằng cách đoán PID mới hoặc retry lệnh nặng liên tục.

## 9. Quy trình kiểm tra production theo mức ảnh hưởng tăng dần

### 9.1. Luồng read-only đầu tiên

1. Từ cảnh báo, định vị đúng node/pod/instance. Ghi host, PID namespace, PID, start time và owner; đối chiếu executable/launch command với service cần điều tra.
2. Trên đúng máy, dùng `jcmd -l` (nếu khả dụng) rồi `jcmd <pid> help` để khám phá danh sách command.
3. Kiểm tra `jcmd <pid> VM.version`, `VM.uptime`, `VM.command_line` theo nhu cầu; **che thông tin bí mật** trong output.
4. Chọn command theo câu hỏi, đọc `jcmd <pid> help <command>` để kiểm tra impact/syntax trước khi sử dụng.
5. Ghi thời gian thu thập, PID + start time, JDK version, command đã chạy và outcome. So với metrics/log có timestamp cùng cửa sổ.
6. Nếu chuẩn bị thread dump, JFR, histogram hoặc heap dump, kiểm tra lại target và đánh giá impact, quota/file output phù hợp với sự cố.

Có thể dùng cấu trúc ghi biên bản như sau:

```text
event_time_utc: 2026-10-29T08:32:15Z
host: node-03
namespace: host
pid: 18432
start_time_utc: 2026-10-29T08:02:00Z
owner: svc-orders
diagnostic_command: VM.uptime
command_impact: Low (theo help trên JVM đích)
result: success
notes: phiên JVM và owner đã đối chiếu với process table
```

Đây là **hồ sơ minh họa**, không phải output bắt buộc của `jcmd`; mốc thời gian, user và PID phải lấy từ hệ thống thật.

### 9.2. Các ví dụ chọn lệnh theo câu hỏi, không chạy bừa

| Câu hỏi | Lệnh có thể dùng sau khi xác minh | Cần biết trước |
| --- | --- | --- |
| “Đây có đúng JVM/build cần điều tra?” | `VM.version`, `VM.command_line`, `VM.uptime` | Đối chiếu với PID/start/owner ở OS |
| “Thread đang ở trạng thái nào?” | `Thread.print -l` | Snapshot, impact trung bình; không chứng minh lịch sử chỉ với một dump |
| “Heap đang được JVM tổ chức thế nào?” | `GC.heap_info` | Chỉ là thông tin tổng quan, không chứng minh memory leak |
| “Có JFR đang chạy?” | `JFR.check` | Kết quả phản ánh thời điểm hỏi |
| “Cần bắt đầu ghi timeline một phút?” | `JFR.start name=triage settings=default duration=60s filename=/var/tmp/triage.jfr` | Kiểm tra overhead, volume/path và chủ sở hữu file |
| “Cần dump heap để phân tích retained objects?” | `GC.heap_dump /var/tmp/heap.hprof` | Impact cao, có thể full GC, file nhạy cảm; cần kế hoạch dung lượng |
| “Cần xem native memory?” | `VM.native_memory summary` | Native Memory Tracking phải được bật ở startup; không mặc định khả dụng |

`JFR.start` bắt đầu recording trong JVM đích; `JFR.check` cho biết trạng thái; `JFR.dump` có thể ghi dữ liệu ra file **mà không tự dừng recording**. Các command điều khiển JFR và lựa chọn cấu hình sẽ phù hợp hơn ở bài chuyên sâu về JFR; ở đây chúng minh họa rằng diagnostic command có thể tạo **side effect dài hơn vòng đời của `jcmd` client**.

### 9.3. Nếu JVM không phản hồi

Một JVM treo hoặc tài nguyên bị cạn có thể phản hồi attach rất chậm hoặc không phản hồi. Đừng kết luận “không có thread nào bị kẹt” từ việc `jcmd Thread.print` không thành công. Khi lệnh timeout/hỏng, ghi lại PID, start time, phiên bản JDK, triệu chứng và lỗi; so sánh nguồn khác (metrics, log, OS process/thread state), đồng thời tuân theo quy trình incident phù hợp.

Không thay `jcmd` bằng thao tác tùy tiện làm thay đổi process chỉ để lấy output; điều đó có thể làm mất bằng chứng.

## 10. Tư duy đúng về command, kết quả và side effect

### Phân biệt ba câu hỏi

1. **Yêu cầu có đến đúng JVM không?** Xác minh PID, start time, owner, runtime identity.
2. **Command có được JVM hỗ trợ và thực hiện không?** Dựa vào `help`, trạng thái trả về, lỗi và điều kiện attach.
3. **Dữ liệu trả về có chứng minh giả thuyết không?** Thread dump một lần chỉ là snapshot; heap info không tự chứng minh leak; JFR có sampling và cấu hình sự kiện.

### Các ngộ nhận quan trọng

- “`jcmd` là lệnh Java chạy từ xa.” → Nó dùng cơ chế attach vào JVM đang sống; cùng-host, đúng quyền, không mặc định là truy vấn qua mạng.
- “`jcmd -l` là danh sách đầy đủ mọi JVM.” → Quyền và container namespace có thể che khuất nhiều process.
- “Tên JAR hoặc main class đủ để chọn đích.” → Nhiều JVM có thể dùng cùng tên; PID cũng có thể tái sử dụng.
- “`jcmd` chỉ đọc thông tin.” → Có command đổi cấu hình, kích hoạt recording, dump heap hoặc gọi GC.
- “Có output tức là phân tích đã chính xác.” → Một snapshot có thể lấy ngoài cửa sổ sự cố; cần ngữ cảnh, thời điểm và đối chiếu chéo.
- “File path luôn thuộc terminal của tôi.” → Redirect shell là file client; tham số `filename` của command có thể là file **do target JVM** tạo.
- “Lệnh `help` trên JDK mới đúng với mọi JVM cũ.” → Khả năng phụ thuộc phiên bản và vendor; hỏi chính JVM đích.
- “Tool chạy xong là thay đổi được tự khôi phục.” → JFR recording hoặc thay đổi cấu hình có thể tiếp tục tồn tại; phải biết cách kiểm tra/dừng/hoàn nguyên nếu đã chủ động thay đổi.

## 11. Checklist trước khi gửi command cho JVM thực

- [ ] Xác định đúng **host/node**, **container/PID namespace**, **PID**, **owner**, **start time** và launch command.
- [ ] Dùng `jcmd` của JDK tương thích; xác định runtime hỗ trợ attach và user có quyền phù hợp.
- [ ] Xem `jcmd <pid> help` và `jcmd <pid> help <command>`; kiểm tra command name, options, impact và quyền.
- [ ] Phân biệt **lệnh truy vấn**, **lệnh tạo snapshot/file lớn** và **lệnh thay đổi trạng thái**.
- [ ] Kiểm tra đích ghi file, quyền truy cập, dung lượng và khả năng chứa secrets khi dump/JFR.
- [ ] Kiểm tra lại PID/start time sát lúc thao tác; không dùng `0` hoặc main class match nhiều process.
- [ ] Lưu kết quả kèm timestamp, runtime version, command và trạng thái thực thi; đối chiếu metrics/log.
- [ ] Nếu command không thành công, phân tích **target → attach → syntax → execution → result** trước khi thử lại.

**Tài liệu chính thức tham khảo:**

- [Oracle Java SE 17 — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): cú pháp, help, danh sách command, impact và tham số.
- [Oracle Java SE 17 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html): cơ chế sử dụng `jcmd` để chẩn đoán JVM đang chạy.
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:+DisableAttachMechanism` và các tùy chọn serviceability.
- [Java SE 17 — DiagnosticCommandMBean](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/DiagnosticCommandMBean.html): cách diagnostic command được trình bày qua cơ chế quản trị Java.

**Ghi nhớ:** mô hình `jcmd` gồm **client → nhận diện JVM đích → attach cục bộ được phép → diagnostic-command dispatcher → kết quả hoặc side effect**. Làm đúng bước chọn JVM và đọc `help` quan trọng không kém việc thuộc lệnh: cùng một `jcmd` có thể chỉ in phiên bản trong vài mili giây hoặc khiến JVM xử lý một heap dump rất lớn.