# 21.5. Quản lý truy cập heap dump, JFR, command line, system property và cổng quản lý

## Mục tiêu

Thu dữ liệu chẩn đoán là một thao tác **vận hành có quyền cao**: một file heap dump có thể chứa toàn bộ dữ liệu nghiệp vụ còn trong bộ nhớ; bản JFR có thể chứa stack trace, thông tin tiến trình, tham số chạy và các dữ liệu cấu hình; `jcmd` có thể đọc system properties hoặc yêu cầu JVM tạo thêm file; cổng JMX/JDWP có thể cung cấp khả năng quan sát, điều khiển rất mạnh.

Sau bài này, bạn có thể:

1. **Phân loại mức nhạy cảm** và phạm vi truy cập của heap dump, `.jfr`, command line, system properties, log chẩn đoán và endpoint quản lý.
2. Thiết kế **quyền tối thiểu, phê duyệt, truy vết và thời hạn lưu** cho quá trình thu thập → lưu tạm → chuyển giao → phân tích → xóa.
3. Giải thích chính xác rủi ro của `jcmd VM.command_line`, `VM.system_properties`, `GC.heap_dump`, `JFR.dump`, `ps`, `/proc`, `-D...` và runtime arguments.
4. Phân biệt **attach nội bộ** với **JMX remote** và **JDWP debugging**; biết cấu hình an toàn ở cấp hệ điều hành, container, mạng và tài khoản.
5. Thực hành với **Java 17+** để quan sát một system property giả lập có thể xuất hiện trong JVM arguments và trong tiến trình, nhưng không cần dùng bất cứ mật khẩu/token thật nào.
6. Xây dựng checklist ứng phó sự cố rò rỉ artifact, phát hiện cổng mở không mong muốn, và xác định những kiểm soát **không đủ nếu đứng một mình**.

> **Nguyên tắc vận hành:** coi dump/recording và output công cụ chẩn đoán là **dữ liệu có thể chứa bí mật**, kể cả khi tên file là `debug`, `profile`, hoặc mục đích chỉ là tìm lỗi hiệu năng. Bảo vệ từ lúc xin quyền, khi JVM ghi file, khi truyền, khi phân tích và cả lúc hủy dữ liệu.

## 1. Bản đồ bề mặt truy cập: ai thấy được gì?

Trước khi chạy một công cụ, cần xác định hai thứ: **năng lực của công cụ** và **dữ liệu ứng dụng có thể bị lộ qua năng lực đó**.

| Bề mặt | Thông tin/hành động có thể có | Vì sao cần kiểm soát |
| --- | --- | --- |
| **Heap dump** (`.hprof`) | Nội dung object/mảng còn trong heap: chuỗi, token, cache, request, dữ liệu khách hàng, credential lưu trong memory; object graph và tham chiếu. | Tiết lộ dữ liệu thực tế, có thể gồm bí mật còn hiệu lực; file lớn và dễ bị sao chép. |
| **JFR recording** (`.jfr`) | Event runtime, class/method, thread/stack, đường dẫn, network endpoint; tùy event settings có JVM arguments, environment, system properties. | Có thể cho biết topology, thông tin cấu hình và dữ liệu nhạy cảm; không mặc định “JFR chỉ có hiệu năng”. |
| **Command line / JVM flags** | `-D...`, `-X...`, `-XX...`, tham số ứng dụng, đường dẫn certificate/config, endpoint, một số giá trị bí mật nếu bị đưa vào dòng lệnh. | Người/tiến trình có quyền quan sát command line hoặc chạy diagnostic command có thể thấy nội dung. |
| **System properties** | Java properties như `java.home`, `user.home`, path/config, endpoint; một số ứng dụng đặt credential bằng `-D...` hay `System.setProperty`. | `VM.system_properties`, MBeans và code trong JVM có thể đọc giá trị; không phải kho bí mật an toàn. |
| **Environment variables** | Endpoint, token hoặc credential nếu ứng dụng/triển khai đặt ở môi trường; dữ liệu có thể đi vào event JFR tùy settings. | Không nên coi env luôn bí mật đối với người có quyền inspect tiến trình/container. |
| **Local attach** (`jcmd`, `jmap`, `jstack`, JConsole local) | Xem nhiều thông tin, yêu cầu recording/dump, có lệnh ảnh hưởng runtime. | Có thể hoạt động với quyền người dùng OS của JVM; không phải chỉ “đọc không rủi ro”. |
| **JMX remote** | Đọc MBean/metrics, tùy role/MBean có thể thực hiện operation hoặc đổi cấu hình. | Endpoint quản trị qua mạng; cấu hình yếu làm lộ dữ liệu hoặc quyền điều khiển. |
| **JDWP debug port** | Breakpoint, suspend, đọc field, gọi method trong JVM, sửa trạng thái qua debugger. | Quyền rất mạnh; không an toàn để mở tự do trên mạng. |
| **Log, ticket, CI artifact, backup** | Bản sao/đoạn trích của bất kỳ dữ liệu nào ở trên. | Quyền của hệ thống nhận dữ liệu có thể rộng hơn quyền đọc JVM gốc. |

Độ nhạy thực tế phụ thuộc ứng dụng, dữ liệu và thời điểm thu, nhưng **mặc định phải kiểm soát như artifact hạn chế truy cập**. “Tôi chỉ lấy JFR”, “file có đuôi `.txt`”, hoặc “tên file không chứa chữ `secret`” **không phải cơ chế phân loại**.

### Phân biệt dữ liệu thô với báo cáo đã rút gọn

- **Raw HPROF/JFR:** chứa nhiều bằng chứng kỹ thuật và có thể có dữ liệu người dùng. Chỉ người được ủy quyền cụ thể mới nên tiếp cận.
- **Output thô `VM.system_properties`/command line:** có thể chứa trực tiếp giá trị nhạy cảm. Không dán toàn văn vào ticket/chat.
- **Báo cáo đã làm sạch:** các chỉ số tổng hợp, nhóm lỗi, stack đã lược bỏ dữ liệu nhạy cảm, phân bố duration/count. Phù hợp hơn để chia sẻ với nhóm lớn **sau khi được kiểm tra**.
- **File đã “ẩn danh” bằng cách đổi tên:** vẫn là dữ liệu thô; đổi tên không xóa payload.
- **File nén hoặc mã hóa:** có thể giảm rủi ro chuyển giao khi khóa/quyền đúng, nhưng không tự biến file thành dữ liệu công khai.

## 2. Mô hình quyền tối thiểu cho một lần thu thập

Thiết kế quyền dựa trên hành động, không chỉ chức danh. Một người được xem dashboard **không tự động cần quyền thu heap dump**. Tách các vai trò:

| Vai trò/hành động | Quyền đề xuất | Giới hạn |
| --- | --- | --- |
| **Người phát hiện sự cố** | Xem metric/log đã làm sạch, mở yêu cầu chẩn đoán. | Không có quyền tự tạo hoặc tải raw dump. |
| **Người phê duyệt** | Xác nhận phạm vi, thời điểm, dữ liệu nhạy cảm, người nhận, thời hạn lưu. | Phê duyệt phải gắn đúng sự cố/JVM, không cấp quyền toàn môi trường vô hạn. |
| **Người thu thập được ủy quyền (SRE/on-call)** | Attach đúng tiến trình hoặc thực hiện thao tác qua cơ chế quản trị được kiểm soát. | Chỉ môi trường, thời gian và command đã được chấp thuận; ghi audit. |
| **Người phân tích** | Đọc file thô trong môi trường cô lập nếu công việc cần; nếu không, chỉ đọc báo cáo đã rút gọn. | Không cần quyền remote debugger/JMX trên ứng dụng đang chạy. |
| **Người chia sẻ kết quả** | Công bố số liệu/kết luận đã được review. | Không gửi raw file, mật khẩu, token, command line chứa secret vào kênh rộng. |
| **Người dọn dẹp** | Xác nhận xóa bản sao trong staging, storage, máy phân tích, chia sẻ, retention/backup theo chính sách. | Phải theo dõi cả bản sao phát sinh, không chỉ file nguồn. |

**Một yêu cầu thu thập đủ rõ** phải có: lý do nghiệp vụ, hệ thống/JVM, môi trường, PID hoặc cách định danh chính xác, loại dữ liệu, người sở hữu, khung thời gian được phép, ảnh hưởng dự kiến (pause, dung lượng, CPU), nơi lưu an toàn, quyền đọc, thời điểm hủy và mã ticket/audit. Với tình huống khẩn cấp, dùng quy trình **break-glass** được phê duyệt/truy vết, rồi rà soát sau sự cố.

**Tách quyền đọc và quyền điều khiển:** JMX read-only MBean không giống quyền chạy diagnostic command; “có quyền xem metric” không đồng nghĩa “có quyền dump heap”. Dù chỉ có quyền đọc ở một giao diện quản trị, dữ liệu trả về có thể vẫn nhạy cảm.

## 3. Heap dump: file nhạy cảm nhất trong nhiều phiên điều tra

Heap dump định dạng HPROF là ảnh chụp dữ liệu các object trên heap JVM tại thời điểm thu. Nó có thể chứa:

- Credential/API token/session cookie trong `String`, `char[]`, `byte[]`, map hoặc object khác (tùy cách ứng dụng quản lý).
- Payload request/response đang được xử lý, dữ liệu tài khoản hoặc khách hàng trong cache.
- URL, host, key, object graph cho thấy quan hệ nội bộ.
- Dữ liệu không hiển thị trong application log vì log đã được ẩn bớt.

Không có gì đảm bảo rằng file HPROF **được redacted tự động**. Dù ứng dụng dùng password masking khi ghi log, object chứa giá trị gốc vẫn có thể nằm trong memory ở thời điểm dump. Lưu ý bản dump thường có dung lượng lớn và thao tác có **Impact: High**, có thể làm pause và tạo áp lực disk.

### 3.1. Kiểm tra quyền trước khi thu

Trên Linux, một cách chuẩn bị **thư mục riêng đã được duyệt trước** là:

```bash
umask 077
install -d -m 0700 /var/lib/app-diag
```

Đây là ví dụ cho máy mà bạn **được phép** tạo `/var/lib/app-diag`. Cần kiểm tra owner/quyền của thư mục, quota, free disk, filesystem encryption, retention và khả năng JVM đích ghi vào đó. `umask 077` giúp file tạo mới không vô tình mở quyền cho group/others theo cách mặc định của shell; **không thay thế ACL hoặc policy của dịch vụ**.

**Lệnh minh họa** trên JVM lab/được phê duyệt (PID `12345` chỉ là ví dụ):

```bash
jcmd 12345 help GC.heap_dump
jcmd 12345 GC.heap_dump /var/lib/app-diag/incident-20261029.hprof
```

Ở đây JVM **đích** tạo file trong filesystem nó nhìn thấy, với quyền của tiến trình JVM. Không phải `jcmd` shell tự ghi file như toán tử `>` của shell. Khi ở container, `/var/lib/app-diag` bên trong JVM container có thể khác path trên host.

**Không tự động chạy lệnh trên production:** phải cân nhắc GC/pause, kích thước heap, mức độ nhạy cảm và quyền người dùng. Tài liệu `jcmd` mô tả mặc định có thể yêu cầu Full GC; chế độ `-all` thay đổi phạm vi object và cách thu, nhưng vẫn có chi phí lớn.

### 3.2. Tự động dump khi OOME cũng cần quản lý quyền

HotSpot hỗ trợ:

```text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/var/lib/app-diag
```

Đây là **cờ cấu hình JVM**, không phải một shell script đầy đủ. Khi có điều kiện kích hoạt, JVM có thể tạo heap dump mà không cần thao tác tương tác. Vì vậy tổ chức phải **phê duyệt trước**: nơi lưu có quyền hạn chế, đủ dung lượng, retention, cảnh báo và quy trình xử lý file mới.

Nếu cấu hình `HeapDumpPath` mặc định hoặc trỏ vào volume chia sẻ/bucket công khai, một sự cố thiếu bộ nhớ có thể đồng thời trở thành **sự cố lộ dữ liệu**. Kiểm tra cả snapshot/backups của volume.

### 3.3. Sau khi thu

- Xác nhận file nằm ở nơi đã phê duyệt, đúng owner/quyền. Ví dụ Linux: `stat /var/lib/app-diag/incident-20261029.hprof`; chỉ xem metadata, **không in nội dung**.
- Không mở file trực tiếp trong browser/plugin/service bên ngoài chưa được duyệt.
- Nếu cần chuyển sang máy phân tích, dùng phương thức có mã hóa khi truyền, xác thực danh tính, kiểm soát truy cập và audit; không dùng link chia sẻ công khai.
- Môi trường phân tích cũng phải bảo vệ file tạm, cache, log và output từ heap analyzer.
- Khi hoàn tất, xóa theo chính sách lưu trữ và quản lý bản sao. Xóa ở một thư mục không bảo đảm file đã biến mất khỏi snapshot/backup/log máy khác.

## 4. JFR: dữ liệu quan sát không phải lúc nào cũng vô hại

JFR thu event hiệu năng/runtime. Tùy **JDK, `.jfc`, event settings và thời điểm ghi**, recording có thể chứa:

- JVM startup information, **command-line arguments**.
- Thông tin môi trường ban đầu và **system properties** khi các event liên quan được bật.
- Tên package/class/method, stack trace và thread.
- Đường dẫn file, endpoint socket, địa chỉ máy, kiểu exception, message hoặc payload của **custom JFR events**.
- Nội dung do ứng dụng tự đưa vào event fields; nếu developer ghi token vào field, nó vẫn có thể đi vào recording.

Không nên giả định mọi `.jfr` chứa toàn bộ các nhóm trên; cũng **không được** giả định chúng không xuất hiện. Dùng `jfr summary`/`jfr metadata` trong môi trường được kiểm soát để biết những loại event được ghi. Oracle mô tả rõ recording JFR **có thể chứa thông tin bí mật** như command line và environment.

### 4.1. Thu JFR có phạm vi

Trên JVM được ủy quyền:

```bash
jcmd 12345 help JFR.start
jcmd 12345 JFR.start name=incident settings=default
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=incident filename=/var/lib/app-diag/incident-20261029.jfr
jcmd 12345 JFR.stop name=incident
```

`JFR.dump` ghi file ở filesystem **JVM đích** và **recording tiếp tục sau dump** cho tới khi dừng bằng `JFR.stop` hoặc hết điều kiện kết thúc. `settings=default` là một cấu hình thu thập chung; **không phải cam kết dữ liệu không nhạy cảm**. `settings=profile` có thể thu nhiều hơn, tăng chi phí và phạm vi thông tin.

Phải quản lý **cả quyền chạy lệnh** lẫn **quyền đọc file `.jfr`**. Người không được phép phân tích raw recording không nên được trao file chỉ vì họ yêu cầu flame graph.

### 4.2. Giảm dữ liệu thu và thông tin xuất bản

- Chỉ bật event cần cho câu hỏi điều tra; nếu tắt event `JVM Information`/environment/system-property theo cấu hình thì một số rủi ro giảm, **nhưng không bảo đảm file còn lại hoàn toàn an toàn**.
- Không đưa secret/PII vào **custom event payload**, exception message hoặc debug tag.
- Nếu chỉ cần đánh giá CPU/latency, cân nhắc cung cấp **báo cáo tổng hợp** đã kiểm tra thay vì bản `.jfr` thô.
- Nếu cần nguyên file, chỉ chuyển sang môi trường/đơn vị đã được phê duyệt và hạn chế người đọc.
- Kiểm tra file sau ghi và **trước chia sẻ**; thay đổi tên hoặc nén file không phải redaction.

Tương tự heap dump, recording có thể bị giữ trong thư mục tạm, container, hệ thống artifact/CI hoặc gắn vào ticket; các vị trí đó phải nằm trong **data lifecycle**.

## 5. Command line và system properties: giá trị có thể bị lộ ở nhiều đường

### 5.1. Vì sao đưa secret vào `-D...` nguy hiểm?

Ví dụ chỉ dành cho lab, **không phải credential thật**:

```bash
java -Ddemo.accessToken=LAB_FAKE_VALUE_NOT_A_SECRET DiagnosticExposureDemo
```

Dù chương trình **không cố tình in giá trị**, một JVM có thể cho biết argument/property qua những kênh đã được cấp quyền:

- `jcmd 12345 VM.command_line`: in dòng lệnh JVM được dùng để khởi động, có thể có `-Ddemo.accessToken=...`.
- `jcmd 12345 VM.system_properties`: in system properties hiện tại, có thể có `demo.accessToken=...`.
- `ManagementFactory.getRuntimeMXBean().getInputArguments()` hoặc `System.getProperties()`/`System.getProperty(...)` trong mã ứng dụng/agent.
- Công cụ OS/process-inspection như `ps` và `/proc/<pid>/cmdline` trên Linux, tùy **quyền, cấu hình OS và namespace**.
- Event JFR liên quan JVM information hoặc system property, nếu được bật.

**Không thể coi `-Dpassword=...` là một secret store.** Kể cả chuyển từ `-D` sang environment variable, dữ liệu vẫn cần được phân loại và bảo vệ, vì cùng-user/root/container-admin hoặc runtime instrumentation có thể có quyền xem. Phương án tốt hơn là sử dụng **managed identity, secret manager, credential provider, file/volume bí mật được mount với quyền tối thiểu**, và không in trực tiếp secret ra log/command line.

### 5.2. Bề mặt lệnh `jcmd` cần nhận diện

| Lệnh/khả năng | Bản chất | Cách xử lý |
| --- | --- | --- |
| `jcmd -l` | Liệt kê JVM nhìn thấy được và thường kèm main class/argument. | Xem output như metadata hạn chế; không tự dán vào kênh rộng. |
| `jcmd 12345 VM.command_line` | In thông tin command-line của JVM. | Có thể lộ `-D`/đường dẫn; chỉ chạy và lưu output trong môi trường được duyệt. |
| `jcmd 12345 VM.system_properties` | In properties hiện tại. | Dễ lộ giá trị nhạy cảm; **không** redirect vào ticket hoặc paste công khai. |
| `jcmd 12345 VM.flags` | Hiển thị VM flags. | Có thể tiết lộ cấu hình/đường dẫn, cần phân loại phù hợp. |
| `jcmd 12345 GC.heap_dump ...` | Yêu cầu JVM tạo HPROF; impact cao. | Phê duyệt thao tác và nơi lưu, chuẩn bị tài nguyên. |
| `jcmd 12345 JFR.start` / `JFR.dump` | Điều khiển recording và tạo `.jfr`. | Phân quyền collector và bảo vệ artifact. |
| `jcmd 12345 help` | Xem command được hỗ trợ. | Thường ít nhạy cảm hơn nhưng vẫn là hành động attach; kiểm tra quyền. |

Các lệnh trên **chỉ là ví dụ cho PID `12345`**; không chạy trên một JVM thực khi chưa có phạm vi thẩm quyền. Đặc biệt, `VM.command_line` và `VM.system_properties` có thể **in bí mật ra terminal**, từ đó đi vào session recording, shell redirect, screen share hoặc hệ thống audit.

### 5.3. Quy tắc tránh lộ giá trị cấu hình

1. **Không đặt token/password trong lệnh khởi động** nếu có cơ chế quản lý bí mật tốt hơn. Tránh cả mật khẩu keystore/truststore trong `-D...`.
2. Không log toàn bộ `System.getProperties()`, runtime arguments, environment hoặc `ProcessHandle.Info.arguments()` vào ứng dụng.
3. Nếu chỉ cần biết **có cấu hình hay không**, in boolean/tên key được allowlist, **không in value**.
4. Nếu cần audit cấu hình, chỉ ghi version/profile và các key được phân loại an toàn, hoặc dùng quy trình redaction được review.
5. Không coi **regex thay `password=`** là redaction hoàn chỉnh: bí mật có thể nằm trong URL, token dạng khác, object, message và field custom.
6. Kiểm tra các bản sao ở logs, crash reports, JFR, CI artifacts, command history, container specs và dashboard.

## 6. Java 17+ lab: nhìn thấy sự hiện diện mà không tiết lộ giá trị

Ví dụ sau dùng **một token giả**, không mở cổng, không yêu cầu attach từ chính chương trình và **không in giá trị property**. Nó giúp phân biệt giá trị trong Java System properties với JVM input arguments.

Tạo file **`DiagnosticExposureDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.List;

public final class DiagnosticExposureDemo {
    public static void main(String[] args) throws Exception {
        long pid = ProcessHandle.current().pid();

        List<String> inputArguments =
                ManagementFactory.getRuntimeMXBean().getInputArguments();
        boolean argumentPresent = inputArguments.stream()
                .anyMatch(value -> value.startsWith("-Ddemo.accessToken="));
        boolean propertyPresent =
                System.getProperty("demo.accessToken") != null;

        System.out.println("pid=" + pid);
        System.out.println("propertyPresent=" + propertyPresent);
        System.out.println("argumentPresent=" + argumentPresent);
        System.out.println("Only synthetic lab values were used.");
        System.out.println("Press Enter to exit.");
        System.in.read();
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 DiagnosticExposureDemo.java
java -Ddemo.accessToken=LAB_FAKE_VALUE_NOT_A_SECRET DiagnosticExposureDemo
```

Output dự kiến (PID của tiến trình phụ thuộc hệ thống):

```text
pid=38448
propertyPresent=true
argumentPresent=true
Only synthetic lab values were used.
Press Enter to exit.
```

Dòng `pid=38448` **chỉ là một lần chạy minh họa**, không phải PID cố định. Ví dụ này đã được biên dịch và chạy thử với `javac --release 17` trên JDK 24; các dòng boolean và thông báo khớp như trên.

### 6.1. Quan sát bằng `jcmd` trên chính JVM lab

Để chương trình **đang chờ ở `System.in.read()`**, mở terminal thứ hai trên cùng máy/quyền hợp lệ. Dùng **PID do chương trình vừa in**, không dùng PID minh họa nếu khác.

```bash
jcmd -l
jcmd 38448 VM.command_line
jcmd 38448 VM.system_properties
```

Các lệnh này có thể **in giá trị token giả trực tiếp ra terminal**, nên chỉ thực hành trên tiến trình lab dùng đúng `LAB_FAKE_VALUE_NOT_A_SECRET`. Trên hệ thống thật, **không chạy và lưu output đầy đủ nếu chưa có yêu cầu chẩn đoán được phép**.

Khi nhìn thấy token giả xuất hiện trong một hoặc cả hai output, hãy xác nhận điều này: **việc chương trình không in token không đồng nghĩa người có quyền attach không thể đọc token từ JVM startup/configuration**. Với system property được thêm sau startup bằng `System.setProperty`, nó có thể hiện trong `VM.system_properties` nhưng **không nhất thiết** hiện ở input arguments ban đầu.

Quay lại terminal đầu, nhấn Enter để JVM thoát. Khi chương trình đã thoát, `jcmd` không thể attach vào PID đó.

### 6.2. Các trường hợp cần suy luận thêm

- Nếu chạy **không có** `-Ddemo.accessToken=...`, `propertyPresent` và `argumentPresent` thường là `false`.
- Nếu ứng dụng gọi `System.setProperty("demo.accessToken", ...)` **trong runtime**, property có thể hiện trong `VM.system_properties`, trong khi `RuntimeMXBean.getInputArguments()` không phản ánh lệnh được thực hiện sau khởi động.
- Nếu application argument là một chuỗi như `--api-token=...`, nó không phải JVM system property mặc định; **nó vẫn có thể lộ qua command line hoặc ứng dụng**, nhưng không tự xuất hiện dưới key `demo.accessToken` trong `System.getProperties()`.
- Trong container, PID thấy từ JVM có thể khác PID thấy từ host, và tool `jcmd` có thể không có trong runtime image tối giản. Không sửa quyền/namespace một cách tùy tiện để ép attach thành công.

## 7. Attach API và quyền tài khoản hệ điều hành

Trên HotSpot/JDK, các công cụ như `jcmd` thường dùng cơ chế **local attach**. Tài liệu JDK yêu cầu chạy với quyền phù hợp (thường **cùng effective user/group** với tiến trình Java, cùng máy và namespace tương ứng). Đây là mô hình dựa vào **ranh giới OS user/process**, không phải một cơ chế riêng “chỉ những người được cấp role Java sẽ chạy `jcmd`”.

### Kiểm soát thực tế

- Chạy service dưới **tài khoản OS chuyên biệt**, không dùng chung một UID cho nhiều ứng dụng có mức độ tin cậy khác nhau.
- Hạn chế người có thể `sudo -u`, `kubectl exec` hoặc chạy shell dưới UID service.
- Tránh container chạy `root` hoặc đặc quyền quá rộng; quản lý RBAC của cluster, hostPID/privileged containers và quyền volume.
- Kiểm soát đường dẫn socket/agent/attach và quyền filesystem theo chính sách OS; không đổi quyền hàng loạt để “làm cho tool chạy”.
- Ghi audit ai attach vào PID nào, lúc nào, dùng command nào, mục tiêu và phê duyệt; **không ghi lại giá trị bí mật trong output audit**.
- Tách môi trường production, staging, development. Cùng UID hoặc host/container với nhiều workload làm tăng phạm vi ảnh hưởng nếu một workload bị xâm nhập.

### `-XX:+DisableAttachMechanism`: hữu ích nhưng không phải lớp bảo vệ duy nhất

HotSpot có thể khởi động với:

```text
-XX:+DisableAttachMechanism
```

Cờ này vô hiệu hóa cơ chế attach thông thường dùng bởi nhiều công cụ như `jcmd`, `jstack`, `jmap`, `jinfo`; **đổi lại có thể làm mất phương án chẩn đoán khi sự cố xảy ra**. Không áp dụng đại trà nếu chưa thử phương án xử lý OOME/hang. Nó **không** bảo vệ trước quyền đọc bộ nhớ/cấu hình từ OS root, hypervisor, container host hay những cổng quản lý khác đã bật.

**Quyết định đúng**: xem attach là một năng lực cần phê duyệt và giới hạn OS; nếu tắt attach, phải có phương án thay thế (JFR khởi động sẵn có kiểm soát, log, metrics, OOME dump directory bảo vệ, restart/capture procedure).

## 8. Cổng JMX: một endpoint quản lý qua mạng cần nhiều lớp bảo vệ

**JMX (Java Management Extensions)** cho phép client truy cập MBeans. Với agent tích hợp HotSpot, các property thường gặp là:

| Property / cấu hình | Chức năng | Điều cần kiểm soát |
| --- | --- | --- |
| `com.sun.management.jmxremote.port` | Mở remote JMX connector/registry trên cổng xác định. | Chỉ bật khi thực sự cần; giới hạn network ACL và danh tính client. |
| `com.sun.management.jmxremote.rmi.port` | Xác định port RMI connector để hỗ trợ firewall/NAT có kiểm soát. | Kiểm tra **cả registry port và connector port**, không chỉ một cổng. |
| `java.rmi.server.hostname` | Xác định host/address được quảng bá trong RMI stub. | Cấu hình phù hợp mạng nội bộ, tránh quảng bá địa chỉ công cộng/sai IP. |
| `com.sun.management.jmxremote.authenticate` | Bật xác thực danh tính cho remote agent. | Không đặt `false` trên production. |
| `com.sun.management.jmxremote.ssl` | Mã hóa kênh connector bằng TLS/SSL. | Không đặt `false` cho truy cập qua mạng; phải kiểm chứng cert/trust/handshake. |
| `com.sun.management.jmxremote.registry.ssl` | Bảo vệ kênh RMI registry bằng SSL khi cấu hình phù hợp. | Tránh lỗ hổng registry không bảo vệ; kết hợp xác thực client. |
| `com.sun.management.jmxremote.ssl.need.client.auth` | Yêu cầu TLS client certificate khi dùng SSL. | Có kế hoạch cấp, xoay vòng và thu hồi chứng chỉ. |
| `com.sun.management.jmxremote.password.file` | File chứa vai trò/password với cơ chế xác thực dựa file. | Chỉ chủ sở hữu được đọc/ghi, tránh mật khẩu tái sử dụng. |
| `com.sun.management.jmxremote.access.file` | Mapping quyền `readonly`/`readwrite` cho role. | Dùng **readonly** khi chỉ quan sát; giới hạn số người/nhóm có `readwrite`. |

**Quan trọng:** mở JMX port không phải chỉ “bật metric”. Remote MBean có thể tiết lộ cấu hình, thông tin runtime và (tùy quyền) cho phép thao tác quản trị. `readwrite` và custom MBean operations có thể nguy hiểm. Ngay cả `readonly` cũng có thể tiết lộ thông tin nhạy cảm nếu MBean expose chúng.

### 8.1. Một cấu hình JMX vận hành có trách nhiệm cần những gì?

1. **Bảo vệ ở lớp mạng:** private network, firewall/security group, VPN/bastion được phê duyệt, không expose Internet. Chỉ những nguồn cụ thể được phép truy cập.
2. **TLS thật sự hoạt động:** có certificate hợp lệ, truststore/certificate rotation và client xác minh server. Đừng chỉ thấy property `ssl=true` rồi mặc định kết nối đã an toàn.
3. **Authentication và authorization:** danh tính riêng cho người/công cụ, role tối thiểu; không cho tất cả người biết cổng trở thành admin.
4. **Bảo vệ RMI registry:** Oracle cảnh báo nguy cơ registry không được bảo vệ và khuyến nghị `jmxremote.registry.ssl=true` kết hợp TLS client auth khi phù hợp; đánh giá toàn bộ đường đăng ký/connector.
5. **Tài khoản quản trị và secret:** password file chứa plaintext theo cơ chế file-based truyền thống, cần quyền chặt như `0600` trên Linux. Không lưu password thật trong shell history/chat hoặc tham số lệnh.
6. **Khả năng kiểm toán:** ghi ai kết nối, quyền gì, lúc nào và thao tác nào; theo cơ chế hạ tầng và khả năng MBean/JMX thực tế.
7. **Kiểm thử từ đúng vị trí mạng:** thử từ host được cấp và host không được cấp; xác nhận không có đường bypass từ pod/namespace khác.

Ví dụ nội dung access file minh họa về **phân quyền**:

```properties
monitorRole readonly
operatorRole readwrite
```

Đây **không phải** một cấu hình JMX an toàn đầy đủ. Cần cơ chế authentication, certificate/TLS, password/access file, ACL và kiểm tra RMI port. Không chép ví dụ rồi mở cổng trên production khi chưa hoàn thiện các lớp bảo vệ.

### 8.2. Tuyệt đối không dùng cấu hình vô hiệu hóa bảo mật qua mạng

```properties
com.sun.management.jmxremote.authenticate=false
com.sun.management.jmxremote.ssl=false
```

Hai dòng này là **mẫu không an toàn cần tránh**, không phải hướng dẫn triển khai. Oracle cảnh báo cấu hình như vậy có thể cho client mạng có quyền kiểm soát rất mạnh. Chỉ mô tả để người vận hành biết **phát hiện và loại bỏ**, không áp dụng thử trong môi trường chia sẻ.

**Đặc biệt:** JMX local connector dành cho công cụ cùng máy/quyền OS có mô hình xác thực **khác** remote connector. Không dùng việc remote JMX bật TLS để kết luận rằng mọi local attach cũng bị ràng buộc bởi password/role remote JMX.

## 9. JDWP debug port: khác JMX và càng không nên mở tự do

**JDWP** là cổng giao thức debugger, hỗ trợ đọc trạng thái, suspend thread, breakpoint, evaluate/invoke method trong JVM. Nó không phải cổng chỉ đọc metrics.

Ví dụ **chỉ dùng trong máy lab**:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 DiagnosticExposureDemo
```

Lệnh trên giả định đã biên dịch `DiagnosticExposureDemo.java`; nó không truyền token thật, chỉ mở **loopback** để IDE cùng máy debug. `127.0.0.1` giảm khả năng bị kết nối từ mạng ngoài, nhưng trên host chia sẻ vẫn cần kiểm soát ai có thể dùng local socket.

Không dùng `address=*:5005` hoặc expose port qua Service/NodePort/port-forward không kiểm soát trên production. Một người kết nối JDWP có thể có năng lực thay đổi thực thi, không chỉ nhìn stack; không nên coi firewall đơn lẻ là đủ thay cho quản trị quyền.

Nếu cần debug từ xa: ưu tiên môi trường staging; dùng tunnel/bastion có xác thực, giới hạn thời gian và audit. Sau khi hoàn tất, đóng phiên và tắt cổng. **Không mặc định bản thân JDWP cung cấp một mô hình xác thực/phân quyền TLS tương đương JMX.**

### So sánh ngắn JMX và JDWP

| Thuộc tính | JMX | JDWP |
| --- | --- | --- |
| Mục đích chính | Monitor/manage MBeans. | Debug chương trình ở mức thread/stack/breakpoint/method. |
| Mô hình quyền | Có thể xác thực, TLS, roles/read-only/read-write; tùy agent/config. | Quyền debug mạnh; cần cô lập mạng và kiểm soát endpoint. |
| Rủi ro nếu expose | Lộ metric/cấu hình hoặc thực hiện operation quản trị. | Suspend, xem/sửa trạng thái, invoke method, gián đoạn dịch vụ. |
| Khuyến nghị | Chỉ bật khi cần, chứng thực + TLS + ACL + audit. | Không bật trong production nếu không có quy trình ngoại lệ rất chặt. |

## 10. Host, container và Kubernetes: ranh giới quan trọng hơn tên công cụ

Trong container orchestration, có hai nhóm quyền thường bị bỏ qua:

1. **Quyền bên trong container/host:** UID, filesystem ACL, Linux capabilities, mount namespaces, PID namespaces, `privileged`, `hostPID`, khả năng dùng ptrace hoặc attach.
2. **Quyền của nền tảng quản lý:** ai được `exec` vào pod, copy file ra khỏi pod, tạo debug/ephemeral container, xem volume/PVC, tải artifact lên bucket, đọc logs hoặc secrets.

Ví dụ: nếu nhiều service cùng dùng UID với quyền truy cập rộng trên một host, việc chỉ “không công bố cổng JMX” không loại bỏ hoàn toàn rủi ro attach hoặc đọc file dump. Ngược lại, một tài khoản không truy cập được JVM trực tiếp nhưng có quyền **download bản dump từ object storage** vẫn có thể đọc dữ liệu.

### Những kiểm soát nên kiểm tra

- `runAsNonRoot`/UID tách biệt theo workload, chính sách privilege escalation và capabilities tối thiểu.
- RBAC cho hành động `exec`, `cp`, `port-forward`, quyền debug container và quản trị node.
- Namespace/network policies hoặc firewall giới hạn JMX/JDWP, không chỉ tin “service không có Ingress”.
- PVC/bucket chẩn đoán không công khai, không mount sang nhiều service không liên quan.
- Disk quota, encryption at rest, quyền object-level, access logs và lifecycle retention.
- Không chuyển HPROF/JFR vào CI public artifacts, chat attachment, issue công khai hoặc máy cá nhân chưa được duyệt.
- Ghi nhận **PID và filesystem view** của container khi dùng `jcmd`; cùng tên path không có nghĩa cùng volume từ host.

Đối với người có quyền root/host admin, nhiều kiểm soát trong guest JVM không đủ để chống việc đọc bộ nhớ hoặc file. Vì vậy cần kiểm soát **cả host và hạ tầng quản lý**, không chỉ cờ JVM.

## 11. Quy trình thu thập và chia sẻ an toàn từ đầu đến cuối

### Giai đoạn A — phê duyệt và chuẩn bị

1. Ghi mục tiêu chẩn đoán: CPU, GC, classloader, memory leak, thread hang hay latency. **Chọn dữ liệu ít nhạy cảm nhất** có thể trả lời câu hỏi.
2. Kiểm tra nguồn dữ liệu đã có như metric/log/JFR tổng hợp. Không tạo HPROF chỉ vì muốn “thêm thông tin”.
3. Xin quyền cho **đúng JVM, khoảng thời gian, loại file và người nhận**; đồng thời đánh giá tác động hiệu năng.
4. Xác nhận nơi lưu an toàn: owner, quyền file, quota, mã hóa, retention, khả năng truy cập từ container/host.
5. Chuẩn bị mẫu báo cáo **không có giá trị secret**. Nếu mục tiêu là kiểm tra cờ/tính năng, ghi key/status thay vì toàn bộ properties.

### Giai đoạn B — thu và xác minh

6. Chạy lệnh bằng identity được phê duyệt, sau khi kiểm tra PID và command thật của JVM đích.
7. Chỉ thu một recording/dump cần thiết hoặc theo kế hoạch cụ thể, không chạy vòng lặp không giới hạn.
8. Không chuyển stdout thô của `VM.system_properties`/`VM.command_line` vào log CI hoặc ticket; output có thể chứa bí mật.
9. Xác nhận file tạo đúng nơi, đúng quyền/dung lượng; kiểm tra **metadata** trước, nội dung chỉ trong môi trường phân tích kín.
10. Ghi manifest: thời gian, JVM/app, collector, công cụ/JDK version, mục đích, vị trí lưu, hash nếu chính sách yêu cầu, hạn xóa.

### Giai đoạn C — chuyển giao và phân tích

11. Dùng kênh truyền đã phê duyệt với mã hóa khi truyền, xác thực và audit. Không dùng link public “ai có URL cũng đọc được”.
12. Dùng máy phân tích có hardening, disk encryption và quyền tối thiểu; tránh plugin chưa được kiểm chứng, dịch vụ upload online công khai.
13. Hạn chế copy file gốc; nếu chia sẻ kết quả cho đội lớn, dùng output đã phân loại và kiểm tra thủ công các field chứa PII/secret.
14. Không upload raw HPROF/JFR để nhờ bên thứ ba phân tích nếu chưa có thỏa thuận, phê duyệt và chính sách xử lý dữ liệu.

### Giai đoạn D — kết thúc

15. Ghi quyết định/tóm tắt kỹ thuật: phát hiện nào có bằng chứng, artifact nào đã dùng, ai còn quyền truy cập.
16. Thu hồi quyền tạm thời, tắt port JMX/JDWP mở cho sự cố, xóa bản sao tạm theo retention và xử lý backup/snapshot theo chính sách.
17. Nếu phát hiện bí mật đã bị để lộ, xử lý như incident security: xác định nơi lộ, chặn chia sẻ, **rotate/revoke credential** nếu cần và kiểm tra audit trail.
18. Kiểm tra lại cấu hình startup, file path, IAM/RBAC/network để lần thu sau không lặp lỗi.

### Mẫu bảng quyết định nhanh

| Câu hỏi | Phương án ưu tiên | Khi phải nâng cấp mức thu thập |
| --- | --- | --- |
| JVM bị GC pause lâu? | GC log, metrics, JFR đã được kiểm soát. | HPROF chỉ nếu cần object graph, memory leak thực sự. |
| Muốn xem active JDK/flags? | Inventory cấu hình đã được phân loại hoặc key allowlist. | `VM.command_line`/`VM.system_properties` raw phải được phê duyệt, không chia sẻ rộng. |
| CPU nóng ở đâu? | JFR CPU samples / profiler đã cấu hình an toàn. | Chỉ xin thêm events/stack khi cần; kiểm tra payload. |
| App không phản hồi vì thread? | JFR/thread dump và log theo quy trình. | Remote debugger chỉ khi cần thiết, ngoại lệ chặt. |
| Muốn giám sát thường xuyên? | Metrics/exporter và JMX connector có TLS/auth/ACL được quản lý. | Không mở JDWP hoặc dump heap định kỳ chỉ để giám sát. |

## 12. Những sai lầm dễ gây sự cố bảo mật

| Sai lầm | Vì sao sai | Cách thay |
| --- | --- | --- |
| “Heap dump chỉ là thông tin kỹ thuật.” | Có thể chứa object và dữ liệu khách hàng/secret. | Coi là artifact hạn chế, chặn public sharing, retention và audit. |
| “JFR không chứa dữ liệu riêng tư vì chỉ đo hiệu năng.” | Có thể có args/env/properties/stack/path/custom payload tùy events. | Kiểm tra settings, phân loại và làm sạch khi chia sẻ. |
| “`-Dtoken` không lộ nếu application không log.” | Giá trị có thể có trong startup arguments/properties và công cụ inspect. | Dùng secret manager/credential provider, không truyền secret qua CLI. |
| “Để secret trong env là an toàn tuyệt đối.” | Env vẫn có thể bị đọc bởi process/container tooling có quyền, hoặc chui vào event/log. | Least privilege, giảm thời gian tồn tại, ngăn log/diagnostic leak. |
| “Chạy chung UID cho nhiều app dễ quản lý.” | Người có quyền của UID đó có thể mở rộng khả năng inspect/attach. | Tách service identities và giới hạn sudo/exec. |
| “`DisableAttachMechanism` làm JVM không thể bị đọc dữ liệu.” | Chỉ vô hiệu hóa attach thông thường, không chặn root/host/JMX/JDWP/files. | Defense in depth và kế hoạch chẩn đoán thay thế. |
| “JMX remote bật port là đủ.” | Cần kiểm soát RMI port, TLS/cert, auth, registry, role và network. | Kiểm thử cấu hình end-to-end từ client được phép/không phép. |
| “JMX readonly luôn an toàn với mọi người.” | MBean đọc có thể lộ thông tin nhạy cảm. | Giới hạn người xem và chỉ xuất metric an toàn. |
| “Chỉ cần `authenticate=false` vì có firewall.” | Nếu truy cập được mạng/port, client có thể có quyền rộng. | Không tắt auth; áp dụng TLS + identity + network ACL. |
| “JDWP là cổng chỉ xem stack.” | Debugger có thể suspend/call method và ảnh hưởng app. | Cô lập loopback/tunnel, không expose Internet. |
| “Nén HPROF/JFR rồi gửi link là đã bảo mật.” | Nén không mã hóa; quyền truy cập link quyết định ai đọc được. | Mã hóa + xác thực + audit + retention. |
| “File đã xóa trong pod thì không còn bản sao.” | Có thể còn ở PVC, bucket, backup, ticket, máy analyst. | Quản lý vòng đời mọi bản sao. |
| “Dùng một regex ẩn password là đủ để công khai artifact.” | Bí mật có thể không có tên `password`, có trong object hoặc custom field. | Cẩn trọng với raw artifacts; ưu tiên báo cáo tổng hợp được review. |

## 13. Kiểm tra thực tế và xử lý sự cố quyền

### 13.1. `jcmd` không attach được: đừng “sửa” bằng cấp quyền tùy tiện

Nếu gặp lỗi attach hoặc `jcmd -l` không thấy tiến trình:

1. Xác nhận JDK tools và JVM target dùng phiên bản phù hợp.
2. Kiểm tra đúng PID/OS user/PID namespace và tình trạng tiến trình.
3. Kiểm tra `-XX:+DisableAttachMechanism`, các chính sách bảo vệ OS/container và hình thức attach được hỗ trợ.
4. Theo quy trình được phê duyệt mới cân nhắc thay đổi cấu hình, dùng diagnostics có sẵn hoặc restart có kế hoạch.
5. **Không** đổi owner toàn bộ volume, bật privileged/hostPID hoặc cấp root cho người dùng chỉ để “cho `jcmd` chạy”.

Việc attach thất bại đôi khi là **kiểm soát bảo mật đang hoạt động đúng**, không nhất thiết là lỗi hệ thống cần vô hiệu hóa.

### 13.2. Phát hiện JMX/JDWP port mở không mong muốn

Cần xác định **cổng nào lắng nghe, giao diện nào, tiến trình nào và ai có thể kết nối**. Với Linux, trên máy bạn quản trị hợp pháp:

```bash
ss -ltnp
```

Lệnh có thể cần quyền phù hợp để hiển thị tên/PID của tiến trình. Chỉ cần **xem metadata listening socket**; không tự gửi dữ liệu nhạy cảm ra nơi khác. Kiểm tra thêm firewall/security group, pod Service/port-forward và quyền network ở từng lớp.

Nếu phát hiện endpoint không có trong approved inventory: hạn chế tiếp xúc mạng ngay theo quy trình, lưu audit, xác định cách bật (`-D...`, JVM flags, sidecar/agent), vô hiệu hóa khi an toàn và kiểm tra kết nối đáng ngờ. **Không mặc định một port đóng nghĩa toàn bộ dữ liệu an toàn**: file dumps và local attach vẫn có rủi ro riêng.

### 13.3. Phát hiện HPROF/JFR bị chia sẻ sai phạm vi

Cần ưu tiên:

1. **Hạn chế hoặc thu hồi** quyền đọc link/bucket/volume, ngăn copy tiếp theo.
2. Ghi log/ticket security với thông tin tối thiểu, không dán nội dung nhạy cảm của dump.
3. Xác minh có ai đã truy cập/tải file, kiểm tra bản sao và chính sách retention.
4. Xác định loại dữ liệu có thể nằm trong artifact, đánh giá ảnh hưởng đến khách hàng/credential.
5. Rotate/revoke token, credential, certificate nếu có khả năng bị lộ theo quy trình IR.
6. Sửa nguyên nhân gốc: dump directory, CI artifact policy, ACL, object storage public access, debug port, hoặc lệnh startup.
7. Đánh giá trách nhiệm thông báo theo yêu cầu pháp lý/chính sách áp dụng.

**Không nên** chỉ xóa file rồi kết luận đã giải quyết: secret còn hiệu lực, log truy cập, snapshot và các bản copy có thể tiếp tục tồn tại.

## 14. Checklist cuối cùng cho ca chẩn đoán Java trong production

- [ ] Có lý do và phê duyệt rõ, chọn **loại dữ liệu ít nhạy cảm nhất** đủ để giải quyết vấn đề.
- [ ] Xác định đúng PID, OS user, namespace, JDK, tác động và khung thời gian.
- [ ] Heap dump/JFR ghi trong **vùng riêng**, owner/ACL hạn chế, mã hóa và quota phù hợp.
- [ ] `-XX:+HeapDumpOnOutOfMemoryError` đã có `HeapDumpPath` và retention được xét trước.
- [ ] Không có token/password thật trong JVM args `-D...`, command-line app args hoặc log debug.
- [ ] Không xuất raw `VM.command_line`, `VM.system_properties` hay environment vào ticket/CI logs.
- [ ] Quyền local attach, `sudo`, `kubectl exec`, `cp`, debug container được kiểm soát.
- [ ] Remote JMX được giới hạn network, TLS/auth, certificate, registry/RMI ports và roles.
- [ ] JDWP không mở public; nếu phải bật thì chỉ theo quy trình tạm thời được audit.
- [ ] Người phân tích chỉ có quyền cần thiết, báo cáo chia sẻ đã được review.
- [ ] Hết sự cố đã thu hồi quyền tạm, đóng cổng, xử lý dump/recording/copy/backup.
- [ ] Nếu nghi lộ bí mật, kích hoạt quy trình security incident và rotation thích hợp.

## Câu hỏi tự kiểm tra

1. **Tại sao một `.hprof` phải được coi là nhạy cảm dù chỉ thu để xem memory leak?** Vì có thể chứa payload dữ liệu và credential trong object/mảng; không có redaction mặc định.
2. **Vì sao `-Ddemo.accessToken=...` có thể lộ dù Java code không in value?** Vì startup arguments và system properties có thể bị xem qua những đường đã được cấp quyền như `VM.command_line`, `VM.system_properties`, JMX/RuntimeMXBean và công cụ OS.
3. **`-XX:+DisableAttachMechanism` có thay thế ACL, không mở JMX/JDWP và bảo vệ file không?** Không. Nó chỉ kiểm soát cơ chế attach thông thường và gây trade-off cho vận hành.
4. **`JFR.dump` ghi file ở shell chạy `jcmd` hay JVM đích?** Ở filesystem JVM đích nhìn thấy theo path được cung cấp; cần kiểm tra container namespace.
5. **JMX có hai port để xem xét là gì?** Thường có **registry port** và **RMI connector port** (`jmxremote.port`, `jmxremote.rmi.port`); cần kiểm tra cấu hình thật, cùng cơ chế TLS/auth và network policies.
6. **Vì sao JMX `readonly` vẫn phải giới hạn người dùng?** Vì dữ liệu MBean có thể chứa cấu hình/metadata nhạy cảm.
7. **Vì sao JDWP nguy hiểm hơn một metrics endpoint?** Vì debugger có thể điều khiển execution, suspend thread và invoke method.
8. **Có thể gửi raw JFR qua chat công khai nếu tắt event system properties không?** Không: vẫn có thể chứa stack, path, endpoint, JVM args/custom events và dữ liệu khác.
9. **Nếu HPROF bị tải xuống trái phép, chỉ xóa trên server có đủ không?** Không; cần điều tra access log, bản sao và khả năng cần revoke/rotate secret.
10. **Ba bước cần nhớ trước khi chia sẻ artifact?** Phân loại nội dung, giới hạn người nhận/quyền truyền nhận, xử lý retention và audit.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 — `jcmd` (`VM.command_line`, `VM.system_properties`, `GC.heap_dump`, `JFR.dump`)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle Java 21 — `java` command (`-XX:+DisableAttachMechanism`, `HeapDumpOnOutOfMemoryError`, `HeapDumpPath`)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle Java — Monitoring and Management Using JMX Technology: authentication, SSL/TLS, role, password/access file và RMI registry](https://docs.oracle.com/en/java/javase/22/management/monitoring-and-management-using-jmx-technology.html).
- [Oracle Java Flight Recorder — Security (recording có thể chứa command line và environment)](https://docs.oracle.com/javacomponents/jmc-5-5/jfr-runtime-guide/run.htm).
- [Oracle Java 21 — JDWP connection/invocation và cấu hình debugger](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html).
- [Oracle Java 21 — `RuntimeMXBean` (JVM input arguments)](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/RuntimeMXBean.html).
- [Oracle Java 21 — `Properties` và `System.getProperties()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html).
