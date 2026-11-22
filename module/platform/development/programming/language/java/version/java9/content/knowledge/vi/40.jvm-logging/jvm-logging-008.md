# Điều chỉnh cấu hình Logging JVM lúc chạy bằng lệnh chẩn đoán

## Mục tiêu

Trong nhóm **Logging JVM**, Java 9 giới thiệu Unified Logging để ghi thông tin từ các thành phần của máy ảo như garbage collection, class loading, compiler và runtime. Cấu hình có thể được đặt khi khởi động bằng **-Xlog**, hoặc điều chỉnh khi JVM đang chạy bằng lệnh chẩn đoán **jcmd <PID> VM.log**.

Bài này tập trung vào cách dùng lệnh chẩn đoán được hỗ trợ để xem cấu hình log hiện tại, bật thêm một nhóm log, chọn mức chi tiết, chuyển log sang file, cấu hình rotation, thay đổi decorators và tắt logging khi cần. Các ví dụ dùng cú pháp Unified Logging hiện hành trên JDK 17+ và được kiểm tra với JDK 24; tài liệu JDK 26 tiếp tục mô tả cùng lệnh **VM.log**.

## 1. Unified Logging và phạm vi của VM.log

Unified Logging là hệ thống log của **JVM**. Mỗi log event có:

- **Tag set**: thành phần hoặc chủ đề phát sinh sự kiện, ví dụ **gc**, **class**, **jit**, **os**.
- **Level**: mức chi tiết, từ **error**, **warning**, **info**, **debug** đến **trace**; **off** dùng để tắt một lựa chọn log.
- **Output**: nơi ghi log, chẳng hạn **stdout**, **stderr** hoặc file.
- **Decorators**: thông tin thêm trước mỗi log message, chẳng hạn uptime, thời gian, PID, thread ID, level và tags.

**jcmd <PID> VM.log** điều khiển Unified Logging của HotSpot JVM. Lệnh này không thay cấu hình của logger trong ứng dụng như SLF4J, Logback, Log4j hoặc **java.util.logging**; các hệ thống đó có cấu hình riêng.

Một điểm cần nhớ là cấu hình được thay đổi bằng **jcmd** có hiệu lực với tiến trình hiện tại. Khi khởi động lại ứng dụng, hãy cấu hình lại bằng lệnh hoặc đặt cấu hình tương ứng trên dòng lệnh **-Xlog**.

## 2. Tìm đúng JVM và kiểm tra lệnh được hỗ trợ

Trước khi gửi diagnostic command, cần xác định đúng tiến trình đích.

Liệt kê các JVM có thể nhìn thấy trên máy:

```bash
jcmd -l
```

Kết quả hiển thị PID và tên main class. Chọn PID của ứng dụng cần chẩn đoán; không gửi lệnh tới PID đoán hoặc PID của một tiến trình khác.

Kiểm tra các diagnostic command mà JVM đích hỗ trợ:

```bash
jcmd <PID> help
jcmd <PID> help VM.log
```

Lệnh thứ hai in mô tả, cú pháp và các tùy chọn của **VM.log**. Danh sách command có thể khác giữa các JVM, bản JDK và môi trường chạy. Vì vậy, hãy kiểm tra trợ giúp của đúng tiến trình trước khi áp dụng lệnh.

**jcmd** phải chạy trên cùng máy với JVM đích và dưới cùng effective user/group đã khởi chạy JVM. Nếu thiếu quyền attach hoặc PID không thuộc môi trường tiến trình mà công cụ nhìn thấy, lệnh có thể thất bại. Trong container, PID hiển thị từ host và PID bên trong container có thể khác nhau; hãy xác định PID trong đúng namespace.

## 3. Các tùy chọn của VM.log

Cú pháp tổng quát:

```bash
jcmd <PID> VM.log [options]
```

Các tùy chọn được truyền theo dạng **key=value** hoặc **key**:

| Tùy chọn | Công dụng |
|---|---|
| **output** | Chọn tên hoặc index của log output cần cấu hình; ví dụ **stdout**, **stderr**, **#0** hoặc **file=...** |
| **output_options** | Cấu hình output, ví dụ kích thước file và số file rotation |
| **what** | Chọn tag set và level cần ghi |
| **decorators** | Chọn metadata được thêm trước log message |
| **list=true** | Liệt kê cấu hình log hiện tại, tag, level và decorator có sẵn |
| **rotate=true** | Yêu cầu JVM rotate các log output hỗ trợ rotation |
| **disable=true** | Tắt toàn bộ logging và xóa cấu hình log hiện tại |

Có thể xem cấu hình trước khi thay đổi:

```bash
jcmd <PID> VM.log list=true
```

Kết quả thường có danh sách output theo index, ví dụ **#0** cho stdout và **#1** cho stderr. Một output file được thêm sau đó cũng có thể xuất hiện với index riêng. Dùng **list=true** để kiểm tra cấu hình thực tế thay vì giả định index hoặc trạng thái của output.

## 4. Chọn tag và level bằng what

Giá trị **what** dùng cú pháp tag selection của Unified Logging:

```text
tag[+tag...][*][=level]
```

Một số ví dụ:

| Giá trị | Ý nghĩa |
|---|---|
| **gc=info** | Log thông tin garbage collection |
| **gc=debug** | Log GC với mức chi tiết debug |
| **gc+heap=debug** | Log debug cho nhóm tag kết hợp gc và heap |
| **class+load=info** | Theo dõi sự kiện nạp class |
| **safepoint=info** | Ghi thông tin safepoint |
| **all=warning** | Chọn các log từ mọi tag set ở mức warning trở lên |

Có thể chỉ định nhiều lựa chọn, phân tách bằng dấu phẩy. Tag kết hợp bằng dấu **+** yêu cầu log event khớp tổ hợp tag đó; dấu **\*** là wildcard khi muốn khớp các tag set rộng hơn.

Các level hiện hành gồm **off**, **trace**, **debug**, **info**, **warning** và **error**. Level càng chi tiết thì lượng log có thể càng lớn. Khi điều tra một vấn đề, hãy bắt đầu bằng tag và level hẹp, sau đó chỉ tăng chi tiết khi cần.

**VM.log list=true** có thể hiển thị danh sách tag và level được JVM đích hỗ trợ. Hãy dùng danh sách đó để tránh chọn tag không tồn tại trong bản JVM đang chạy.

## 5. Ghi log runtime vào file và cấu hình rotation

Ví dụ bật GC debug log vào một file riêng:

```bash
jcmd <PID> VM.log output="file=/var/log/myapp/gc-runtime.log" what="gc=debug" decorators="uptime,level,tags" output_options="filecount=5,filesize=10M"
```

Ý nghĩa:

- **output="file=..."** tạo hoặc cấu hình output file.
- **what="gc=debug"** chọn log GC ở mức debug.
- **decorators="uptime,level,tags"** thêm uptime, level và tag set vào mỗi dòng.
- **output_options="filecount=5,filesize=10M"** yêu cầu giữ tối đa năm file trong rotation với kích thước mục tiêu khoảng 10 MB mỗi file.

Đường dẫn phải tồn tại hoặc có thể được JVM tạo theo quyền của tiến trình. Người dùng chạy JVM cần có quyền ghi vào thư mục đích. Trên Windows, thay đường dẫn ví dụ bằng đường dẫn file hợp lệ của hệ thống, chẳng hạn **file=C:\logs\gc-runtime.log**.

Sau khi cấu hình, kiểm tra lại:

```bash
jcmd <PID> VM.log list=true
```

Trong danh sách, xác nhận output file, tag selection, decorators và các output options đúng như mong muốn. Nếu cần điều chỉnh một output đã có, dùng tên hoặc index được hiển thị trong danh sách, ví dụ **output=#2**.

## 6. Thay đổi decorators và output

Decorators thêm ngữ cảnh vào log message. Những giá trị thường dùng:

| Decorator | Thông tin |
|---|---|
| **time** | Thời gian hiện tại theo ISO-8601 |
| **utctime** | Thời gian UTC |
| **uptime** | Thời gian kể từ khi JVM khởi động |
| **pid** | Process ID |
| **tid** | Thread ID |
| **level** | Level của log event |
| **tags** | Tag set của log event |
| **hostname** | Tên host |

Ví dụ cấu hình output hiện có để ghi GC info với thời gian và PID:

```bash
jcmd <PID> VM.log output=#0 what="gc=info" decorators="time,pid,level,tags"
```

**none** dùng để bỏ decorators:

```bash
jcmd <PID> VM.log output=#0 decorators=none
```

Các output có thể độc lập về tag selection và decorators. Nếu một output đã có nhiều cấu hình, hãy đọc kết quả **list=true** sau mỗi thay đổi để chắc rằng chỉ output dự định được điều chỉnh.

## 7. Rotate và tắt logging

Khi muốn yêu cầu JVM rotate các log output:

```bash
jcmd <PID> VM.log rotate=true
```

Lệnh này áp dụng cho các log output có hỗ trợ rotation. Với file output, rotation theo kích thước và số file còn được điều khiển bằng **output_options**.

Để tắt toàn bộ logging và xóa cấu hình hiện tại:

```bash
jcmd <PID> VM.log disable=true
```

Đây là thao tác rộng: nó tắt logging của JVM và xóa cấu hình log, bao gồm cả cấu hình mặc định. Chỉ dùng khi chủ đích là dừng toàn bộ log; nếu chỉ muốn giảm một nhóm log, hãy cấu hình lại **what** cho output tương ứng thay vì tắt tất cả.

Sau khi thay đổi, có thể chạy **jcmd <PID> VM.log list=true** để kiểm tra trạng thái cuối.

## 8. Quy trình thực hành hoàn chỉnh

Giả sử ứng dụng Java đang chạy và cần thu thập thêm GC log trong một khoảng thời gian:

1. Chạy **jcmd -l** để tìm PID.
2. Chạy **jcmd <PID> help VM.log** để xác nhận lệnh và tùy chọn có sẵn.
3. Chạy **jcmd <PID> VM.log list=true** để lưu lại cấu hình ban đầu.
4. Thêm output file với **what="gc=debug"** và rotation phù hợp.
5. Kiểm tra lại bằng **list=true**.
6. Quan sát file log trong lúc ứng dụng tiếp tục chạy.
7. Khi đủ dữ liệu, dùng **rotate=true** nếu cần chốt file hiện tại.
8. Khôi phục cấu hình đã ghi nhận sau khi điều tra xong.

Ví dụ chuỗi lệnh trên Linux:

```bash
jcmd -l
jcmd 12345 help VM.log
jcmd 12345 VM.log list=true
jcmd 12345 VM.log output="file=/var/log/myapp/gc-runtime.log" what="gc=debug" decorators="uptime,level,tags" output_options="filecount=5,filesize=10M"
jcmd 12345 VM.log list=true
jcmd 12345 VM.log rotate=true
```

Thay **12345** bằng PID thực tế. Các lệnh ví dụ là thao tác trên JVM đích; không chạy nguyên PID minh họa trên hệ thống thật.

## 9. Ví dụ Java để thử lệnh chẩn đoán

Tạo một JVM chạy đủ lâu và chủ động tạo một số GC event để có dữ liệu quan sát. Đây là chương trình thử nghiệm độc lập, không phải mã cấu hình logging trong ứng dụng:

```java
public class GcLogProbe {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("PID=" + ProcessHandle.current().pid());

        for (int i = 0; i < 30; i++) {
            System.gc();
            Thread.sleep(1000);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -Xlint:all GcLogProbe.java
java GcLogProbe
```

Chương trình in PID rồi tiếp tục chạy khoảng 30 giây. Trong terminal khác, dùng PID vừa in:

```bash
jcmd <PID> VM.log list=true
jcmd <PID> VM.log output="file=gc-runtime.log" what="gc=info" decorators="uptime,level,tags" output_options="filecount=2,filesize=1M"
jcmd <PID> VM.log list=true
```

File **gc-runtime.log** sẽ chứa các GC event được phát sinh sau khi output được cấu hình. Ví dụ dùng **System.gc()** để tạo event; môi trường chạy có thể vô hiệu hóa explicit GC, vì vậy không dùng kết quả của probe này làm cam kết về tần suất GC trong ứng dụng thật.

## 10. Cấu hình lúc khởi động và điều chỉnh lúc chạy

Có hai thời điểm cấu hình Unified Logging:

| Cách | Khi áp dụng | Công cụ |
|---|---|---|
| Startup configuration | Khi tạo JVM | Tùy chọn **-Xlog** trên lệnh java |
| Runtime configuration | Khi JVM đang chạy | Diagnostic Command **jcmd <PID> VM.log** hoặc JMX |

Ví dụ cấu hình từ lúc khởi động:

```bash
java -Xlog:gc=info:file=gc.log:uptime,level,tags -jar app.jar
```

Ví dụ điều chỉnh sau khi ứng dụng đã chạy:

```bash
jcmd <PID> VM.log output="file=gc-runtime.log" what="gc=info" decorators="uptime,level,tags"
```

Tài liệu JVM cho phép điều khiển logging khi chạy thông qua Diagnostic Commands; các diagnostic command cũng được phơi bày dưới dạng MBeans, vì vậy có thể thay đổi cấu hình qua JMX khi hệ thống quản trị đã được thiết lập phù hợp.

Cấu hình runtime chỉ tác động lên tiến trình đang chạy. Nếu cần giữ cùng cấu hình sau restart, hãy đưa lựa chọn tương ứng vào startup configuration hoặc quy trình khởi chạy của dịch vụ.

## 11. Phạm vi, quyền hạn và lỗi thường gặp

- **Không tìm thấy PID**: kiểm tra **jcmd -l**, quyền người dùng và namespace của container.
- **Không có VM.log**: chạy **jcmd <PID> help** trên đúng JVM; command khả dụng phụ thuộc implementation và phiên bản.
- **Attach bị từ chối**: dùng cùng máy và effective user/group với tiến trình JVM; kiểm tra chính sách bảo mật và quyền của môi trường.
- **Không thấy log mới**: kiểm tra tag, level, output, quyền ghi file và cấu hình bằng **list=true**.
- **File log quá lớn**: giảm phạm vi **what**, giảm level từ debug/trace xuống info hoặc warning, và đặt **filesize**/**filecount**.
- **Không thấy log trong file**: xác nhận output file thực sự được thêm và không nhầm với output stdout/stderr.
- **Tắt logging quá rộng**: **disable=true** xóa toàn bộ cấu hình; chỉ dùng khi muốn dừng toàn bộ JVM logging.
- **Nhầm log JVM với log ứng dụng**: **VM.log** không thay cấu hình của Logback, Log4j, SLF4J hay **java.util.logging**.
- **Dùng tag không được hỗ trợ**: xem danh sách tag và level qua **VM.log list=true** hoặc trợ giúp **-Xlog:help** của đúng JDK.

Chỉ bật log chi tiết trong phạm vi cần thiết và trong khoảng thời gian phù hợp. Mức debug hoặc trace có thể làm tăng dung lượng file và overhead; nên theo dõi disk space, quyền truy cập log và quy trình thu hồi cấu hình sau khi điều tra xong.

## Kết luận

Để điều chỉnh Unified Logging khi JVM đang chạy, hãy xác định đúng PID, kiểm tra **help VM.log**, xem cấu hình bằng **list=true**, rồi chọn output, tags, level và decorators cần thiết. Dùng **output_options** để quản lý file log, **rotate=true** để xoay log và chỉ dùng **disable=true** khi cần dừng toàn bộ logging.

**jcmd <PID> VM.log** là diagnostic command hiện hành dành cho JVM logging. Việc kiểm tra cấu hình sau mỗi thay đổi và khôi phục trạng thái sau khi điều tra giúp thu thập đủ dữ liệu mà vẫn kiểm soát được lượng log phát sinh.

## Nguồn tham khảo

- [JDK 26 — The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [JDK 26 — The java Command: Unified Logging](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [JDK 26 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
