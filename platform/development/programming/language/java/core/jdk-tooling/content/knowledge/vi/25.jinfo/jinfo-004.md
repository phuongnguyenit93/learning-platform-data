# Thay đổi flag động của JVM bằng jinfo

`jinfo` là công cụ JDK dùng để xem cấu hình của một Java process, bao gồm JVM command-line flags và system properties. Tùy chọn `-flag` còn cho phép đọc hoặc thay đổi **một số VM flag ngay khi JVM đang chạy**.

Flag động (dynamic flag) là VM flag mà HotSpot cho phép thay đổi trong runtime. Không phải flag nào cũng thay đổi được. Chỉ những flag được đánh dấu có thể quản lý (manageable) mới có thể được cập nhật bằng cơ chế này. Flag chỉ có hiệu lực lúc khởi động, chẳng hạn lựa chọn garbage collector hoặc kích thước heap ban đầu, thường cần cấu hình lại lệnh khởi chạy và restart JVM.

Cần biết giới hạn này trước khi dùng `jinfo -flag` trên một tiến trình đang phục vụ người dùng. Thay đổi một flag có thể tác động tới heap, garbage collection, log hoặc file dump; hãy kiểm tra giá trị hiện tại, khả năng thay đổi, phạm vi ảnh hưởng và cách khôi phục trước khi thực hiện.

## 1. JVM flag là gì?

JVM flag là tùy chọn cấu hình của Java Virtual Machine. Nhiều flag HotSpot được truyền lúc khởi động bằng tiền tố `-XX:`. Ví dụ:

~~~sh
java -XX:MaxHeapFreeRatio=75 -cp out FlagProbe
java -XX:+HeapDumpOnOutOfMemoryError -cp out FlagProbe
java -XX:-UseG1GC -cp out FlagProbe
~~~

Ví dụ trên minh họa cú pháp:

- `-XX:MaxHeapFreeRatio=75` đặt một giá trị số.
- `-XX:+HeapDumpOnOutOfMemoryError` bật một boolean flag.
- `-XX:-UseG1GC` tắt một boolean flag nếu flag đó được hỗ trợ và phù hợp với JVM.

Không phải mọi flag đều có thể đổi sau khi JVM đã khởi động. Một số giá trị được đọc khi VM khởi tạo hoặc ảnh hưởng tới cấu trúc đã được tạo, nên chỉ có thể chọn trước khi chạy ứng dụng.

Một flag có thể thay đổi động thường được JVM đánh dấu `manageable`. Thuộc tính này cho biết VM cho phép cập nhật giá trị trong lúc chạy qua diagnostic interface. Các flag khác có thể được đánh dấu `product`, `diagnostic` hoặc thuộc nhóm chỉ cấu hình lúc khởi động; không suy luận rằng mọi flag đều có thể đổi chỉ vì `jinfo` có tùy chọn setter.

## 2. Kiểm tra tiến trình Java và flag hiện tại

Cú pháp tổng quát:

~~~sh
jinfo <option> <pid>
~~~

`<pid>` là process ID của JVM cần kiểm tra. Có thể liệt kê các Java process bằng:

~~~sh
jcmd -l
~~~

Hoặc:

~~~sh
jps -l
~~~

Kết quả minh họa:

~~~text
60236 FlagProbe
51276 com.example.Server
~~~

Chọn đúng PID trước khi chạy lệnh. Nếu nhiều ứng dụng Java đang chạy, việc dùng nhầm PID có thể làm thay đổi cấu hình của tiến trình khác.

Đọc một flag cụ thể:

~~~sh
jinfo -flag MaxHeapFreeRatio 60236
~~~

Kết quả ví dụ:

~~~text
-XX:MaxHeapFreeRatio=70
~~~

`jinfo -flag <name> <pid>` chỉ đọc giá trị hiện tại. Tên flag truyền vào không cần tiền tố `-XX:`; output thường hiển thị lại dạng `-XX:...`.

In các VM flag:

~~~sh
jinfo -flags 60236
~~~

In system property:

~~~sh
jinfo -sysprops 60236
~~~

Nếu không chỉ định option, `jinfo <pid>` in cả VM flag và các cặp system property. Hai loại dữ liệu này khác nhau: `-XX:...` là VM flag, còn `-Dname=value` thường tạo Java system property.

## 3. Phân biệt flag có thể thay đổi và flag chỉ cấu hình lúc khởi động

Trên HotSpot, dùng `jcmd` để xem toàn bộ flag và thuộc tính của chúng:

~~~sh
jcmd 60236 VM.flags -all
~~~

Tìm tên flag cần kiểm tra. Một số dòng minh họa:

~~~text
bool HeapDumpOnOutOfMemoryError = false {manageable} {default}
uintx MaxHeapFreeRatio = 70 {manageable} {default}
bool UseG1GC = true {product} {ergonomic}
~~~

Trong ví dụ:

- `HeapDumpOnOutOfMemoryError` và `MaxHeapFreeRatio` có nhãn `{manageable}`, vì vậy có thể thay đổi động trên JVM hỗ trợ chúng.
- `UseG1GC` không có nhãn `{manageable}`; đây là lựa chọn collector của VM và không thể đổi bằng `jinfo -flag` trong tiến trình đang chạy.

Đầu ra và giá trị thực tế phụ thuộc phiên bản JDK, nhà cung cấp JVM và cấu hình tiến trình. Luôn xem kết quả trên đúng JVM đích thay vì sao chép danh sách flag từ máy khác.

Nếu thử thay đổi một flag không được quản lý động, lệnh có thể báo lỗi tương tự:

~~~text
AttachOperationFailedException:
flag 'UseG1GC' cannot be changed
~~~

Lỗi này cho biết flag không hỗ trợ cập nhật trong runtime. Hãy đặt flag đó khi khởi chạy JVM nếu phiên bản và cấu hình cho phép, sau đó restart ứng dụng theo quy trình vận hành.

## 4. Thay đổi flag dạng số bằng -flag name=value

Cú pháp:

~~~sh
jinfo -flag <name>=<value> <pid>
~~~

Ví dụ thay đổi `MaxHeapFreeRatio` thành 75:

~~~sh
jinfo -flag MaxHeapFreeRatio=75 60236
~~~

Đọc lại để xác nhận:

~~~sh
jinfo -flag MaxHeapFreeRatio 60236
~~~

Output ví dụ:

~~~text
-XX:MaxHeapFreeRatio=75
~~~

Trong thử nghiệm với JDK 24.0.2, flag này có giá trị ban đầu 70, được đổi thành 75 và đọc lại thành công. `MaxHeapFreeRatio` là một ví dụ manageable flag; không giả định tất cả flag dạng số đều có thể thay đổi.

Giá trị phải đúng kiểu và giới hạn mà flag yêu cầu. Nếu nhập sai tên, sai kiểu, nằm ngoài miền hợp lệ hoặc flag không manageable, JVM có thể từ chối thay đổi. Không coi việc command không in lỗi là bằng chứng duy nhất; luôn query lại giá trị sau khi set.

Một số flag có quan hệ ràng buộc với flag khác. Ví dụ các ngưỡng tỷ lệ heap tối thiểu và tối đa phải có thứ tự hợp lệ. Hãy đọc tài liệu flag cụ thể và xem các giá trị liên quan trước khi thay đổi.

## 5. Bật hoặc tắt boolean flag

Với flag kiểu boolean, dùng dấu `+` để bật và dấu `-` để tắt:

~~~sh
jinfo -flag +HeapDumpOnOutOfMemoryError 60236
jinfo -flag HeapDumpOnOutOfMemoryError 60236
~~~

Dòng đầu bật flag; dòng thứ hai đọc lại giá trị. Output ví dụ:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
~~~

Để tắt:

~~~sh
jinfo -flag -HeapDumpOnOutOfMemoryError 60236
jinfo -flag HeapDumpOnOutOfMemoryError 60236
~~~

Output sau khi tắt:

~~~text
-XX:-HeapDumpOnOutOfMemoryError
~~~

Trong thử nghiệm với JDK 24.0.2, `HeapDumpOnOutOfMemoryError` được đánh dấu manageable và chuyển từ false sang true thành công. Đây là flag có thể khiến JVM ghi heap dump khi gặp `OutOfMemoryError`. Heap dump có thể rất lớn; trước khi bật trên production, hãy kiểm tra dung lượng đĩa, đường dẫn lưu, quyền ghi và chính sách bảo vệ dữ liệu.

Chỉ dùng dạng `+name` hoặc `-name` với boolean flag. Với flag dạng số hoặc chuỗi, dùng `name=value`.

## 6. Ví dụ thực hành hoàn chỉnh

Tạo file `FlagProbe.java`:

~~~java
public class FlagProbe {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("flag-probe-ready");
        Thread.sleep(120_000);
    }
}
~~~

Chương trình in một dòng rồi giữ JVM chạy hai phút để có thời gian thao tác từ terminal khác.

Biên dịch:

~~~sh
mkdir -p out
javac -d out FlagProbe.java
~~~

Khởi chạy:

~~~sh
java -cp out FlagProbe
~~~

Stdout chính xác:

~~~text
flag-probe-ready
~~~

Mở terminal thứ hai, tìm PID:

~~~sh
jcmd -l
~~~

Giả sử PID là `60236`. Kiểm tra giá trị ban đầu:

~~~sh
jinfo -flag MaxHeapFreeRatio 60236
~~~

Đổi giá trị:

~~~sh
jinfo -flag MaxHeapFreeRatio=75 60236
~~~

Xác nhận:

~~~sh
jinfo -flag MaxHeapFreeRatio 60236
~~~

Kiểm tra metadata để xác nhận flag có thể quản lý:

~~~sh
jcmd 60236 VM.flags -all
~~~

Tìm dòng `MaxHeapFreeRatio` và xác nhận có nhãn `{manageable}`. Khi hoàn tất, quay lại terminal chạy `FlagProbe` và nhấn `Ctrl+C` để dừng tiến trình.

PID trong ví dụ chỉ là số minh họa. Hãy dùng PID thực tế từ `jcmd -l` trên máy của bạn.

## 7. Dùng jcmd làm lựa chọn chẩn đoán hiện đại

Oracle khuyến nghị dùng `jcmd` thay cho công cụ cũ `jinfo` trong các quy trình chẩn đoán mới. `jinfo` được tài liệu JDK phân loại là công cụ experimental và unsupported; công cụ có thể không còn trong một bản JDK tương lai.

Với `jcmd`, có thể đọc flag:

~~~sh
jcmd 60236 VM.flags -all
~~~

Xem cú pháp command thay đổi flag:

~~~sh
jcmd 60236 help VM.set_flag
~~~

Thay đổi flag dạng số:

~~~sh
jcmd 60236 VM.set_flag MaxHeapFreeRatio 80
~~~

Đọc lại bằng `jinfo` hoặc `jcmd`:

~~~sh
jinfo -flag MaxHeapFreeRatio 60236
jcmd 60236 VM.flags -all
~~~

Trong thử nghiệm với JDK 24.0.2, `jcmd <pid> VM.set_flag MaxHeapFreeRatio 80` trả về `Command executed successfully` và `jinfo` đọc lại giá trị 80.

`jcmd` cũng dùng attach tới JVM đích. Hãy xem `jcmd <pid> help` để biết command có sẵn trên phiên bản JVM đó. Đối với công việc tự động hóa mới, ưu tiên giao diện diagnostic command được JDK hiện hành hỗ trợ và kiểm tra lại kết quả sau khi thay đổi.

## 8. Flag động không làm thay đổi cấu hình khởi động vĩnh viễn

Một thay đổi bằng `jinfo -flag` hoặc `jcmd VM.set_flag` áp dụng cho JVM đang chạy. Nó không tự sửa script, service unit, Docker image, cấu hình Gradle/Maven hoặc tham số triển khai.

Khi tiến trình dừng và khởi động lại, JVM sẽ lấy flag từ cấu hình khởi chạy hoặc giá trị mặc định. Nếu muốn giữ thay đổi qua lần restart, cập nhật cấu hình startup theo quy trình quản lý ứng dụng, ví dụ:

~~~sh
java -XX:MaxHeapFreeRatio=75 -cp out FlagProbe
~~~

Với boolean flag:

~~~sh
java -XX:+HeapDumpOnOutOfMemoryError -cp out FlagProbe
~~~

Không nên chỉ thay đổi runtime rồi coi đó là cấu hình đã được lưu lâu dài. Ghi lại giá trị mong muốn, nơi cấu hình khởi động được quản lý và cách rollback.

Ngoài ra, một flag có thể được đọc khi một thành phần khởi tạo. Thay đổi giá trị sau thời điểm đó không nhất thiết làm thành phần đã khởi tạo hoạt động lại theo cấu hình mới. Tác động cụ thể phụ thuộc từng flag; hãy kiểm tra tài liệu của flag trước khi kỳ vọng thay đổi có hiệu lực ngay lập tức.

## 9. Quyền truy cập và điều kiện attach

`jinfo` kết nối tới một Java process đang chạy thông qua cơ chế attach. Một số điều kiện có thể làm lệnh thất bại:

- PID không tồn tại, tiến trình đã dừng hoặc PID không phải JVM.
- Người dùng hiện tại không có quyền truy cập tiến trình đích.
- JVM được khởi chạy với `-XX:+DisableAttachMechanism`.
- Công cụ và JVM đích không tương thích hoặc khác môi trường chạy.
- JVM chạy trong container/PID namespace riêng nên PID trên host không trùng PID bên trong container.
- Nền tảng thiếu thành phần hỗ trợ attach cần thiết.

Chạy công cụ trên cùng máy và bằng tài khoản có quyền attach phù hợp. Với container, xác định PID trong đúng namespace và thực hiện lệnh từ môi trường có thể nhìn thấy JVM đích.

Trên một số cấu hình Windows, tài liệu `jinfo` cũng nêu yêu cầu thành phần Debugging Tools for Windows khi thiếu `dbgeng.dll`, cùng việc PATH cần trỏ tới `jvm.dll` của JVM đích. Nếu attach lỗi trên Windows, kiểm tra thông báo cụ thể và cấu hình JDK/native debugging tools của máy.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jinfo: command not found` | JDK chưa được cài hoặc PATH thiếu JDK bin | Kiểm tra `JAVA_HOME` và PATH |
| `flag 'UseG1GC' cannot be changed` | Flag không hỗ trợ thay đổi động | Kiểm tra `VM.flags -all`; cấu hình lúc khởi động nếu cần |
| Không đọc được PID | PID sai, JVM đã dừng hoặc ở container khác | Dùng `jcmd -l` và kiểm tra PID trong đúng namespace |
| `AttachNotSupportedException` | Attach bị tắt hoặc không đủ quyền | Kiểm tra user, `DisableAttachMechanism` và môi trường attach |
| Giá trị flag không đổi | Lệnh bị từ chối, flag không manageable hoặc giá trị không hợp lệ | Đọc lỗi, kiểm tra metadata và query lại bằng `-flag <name>` |
| Giá trị bị trả về mặc định sau restart | Thay đổi chỉ áp dụng cho tiến trình hiện tại | Cập nhật tham số startup và triển khai lại |
| Tác động không xuất hiện ngay | Flag chỉ ảnh hưởng tới sự kiện/hoạt động xảy ra sau khi đổi hoặc thành phần đã cache cấu hình | Đọc mô tả flag và kiểm tra hành vi của thành phần liên quan |
| Thay đổi flag gây tác động ngoài dự kiến | Chọn flag không phù hợp hoặc không đánh giá tác động | Khôi phục giá trị cũ nếu còn hỗ trợ và thực hiện rollback theo quy trình |

## 11. Quy trình thay đổi flag động an toàn

Khi cần đổi một JVM flag trong runtime, hãy làm theo thứ tự:

1. Xác định đúng máy, container và PID của ứng dụng.
2. Ghi nhận phiên bản JDK/JVM đang chạy.
3. Đọc giá trị hiện tại bằng `jinfo -flag <name> <pid>`.
4. Dùng `jcmd <pid> VM.flags -all` để kiểm tra flag có nhãn `manageable` hay không.
5. Đọc tài liệu flag và các ràng buộc với flag liên quan.
6. Ghi lại giá trị cũ để có thể rollback.
7. Chỉ thay đổi đúng flag cần thiết bằng `jinfo -flag` hoặc `jcmd VM.set_flag`.
8. Query lại để xác nhận giá trị mới.
9. Quan sát log, metric và hành vi ứng dụng sau thay đổi.
10. Cập nhật cấu hình startup nếu cần giữ giá trị qua restart.

Không thay đổi nhiều flag cùng lúc khi đang điều tra sự cố, vì sẽ khó xác định thay đổi nào tạo ra tác động. Nếu flag không manageable, dừng thao tác runtime và lập kế hoạch restart với cấu hình phù hợp.

### Checklist

- [ ] Đã chọn đúng PID và JVM đích.
- [ ] Đã ghi lại phiên bản JDK/JVM.
- [ ] Đã đọc giá trị flag hiện tại.
- [ ] Đã xác nhận flag có thuộc tính `manageable`.
- [ ] Đã hiểu kiểu dữ liệu, miền giá trị và tác động của flag.
- [ ] Đã ghi lại giá trị cũ để rollback.
- [ ] Đã dùng cú pháp đúng: `+/-name` cho boolean hoặc `name=value` cho giá trị khác.
- [ ] Đã query lại sau khi set.
- [ ] Đã theo dõi ứng dụng sau thay đổi.
- [ ] Đã cập nhật startup configuration nếu cần giữ thay đổi qua restart.
- [ ] Đã cân nhắc dùng `jcmd` cho quy trình chẩn đoán mới.

`jinfo -flag` có thể đọc và thay đổi một số JVM flag trong khi tiến trình đang chạy. Kiểm tra nhãn `manageable`, xác nhận giá trị sau khi set và hiểu rằng thay đổi runtime không tự lưu qua restart là ba bước cần thiết để dùng flag động đúng cách.

## Tài liệu tham khảo

- [Oracle JDK 24 — The jinfo Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jinfo.html)
- [Oracle JDK 24 — Troubleshooting Guide, The jinfo Utility](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf)
- [Oracle JDK 24 — The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)