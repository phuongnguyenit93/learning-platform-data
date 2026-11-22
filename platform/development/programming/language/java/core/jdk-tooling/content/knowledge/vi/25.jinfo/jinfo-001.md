# Lệnh jinfo trong JDK

## 1. jinfo là gì?

**jinfo** là công cụ dòng lệnh đi kèm JDK, dùng để đọc thông tin cấu hình của một Java Virtual Machine (JVM) đang chạy. Công cụ có thể hiển thị JVM flags và Java system properties; với một số flag được JVM cho phép thay đổi động, jinfo còn có thể bật, tắt hoặc đặt giá trị khi process vẫn hoạt động.

jinfo hữu ích khi cần trả lời các câu hỏi như:

- JVM đang chạy với heap size và garbage collector nào?
- Ứng dụng được khởi chạy với những JVM option nào?
- System property nào đang có hiệu lực?
- Một Boolean VM flag hiện bật hay tắt?
- Có thể thay đổi một flag nhất định mà không restart process hay không?

Cú pháp tổng quát:

~~~text
jinfo <option> <pid>
~~~

Trong đó PID là process ID của JVM cần kiểm tra. jinfo làm việc với một JVM process cụ thể; công cụ không tự liệt kê toàn bộ Java process. Có thể tìm PID bằng jcmd -l, jps -l hoặc công cụ process của hệ điều hành.

## 2. Vị trí của jinfo trong bộ công cụ JDK

jinfo là một công cụ chẩn đoán JVM thuộc nhóm công cụ dòng lệnh. Nó tập trung vào flags và system properties của một process.

Các công cụ liên quan có mục tiêu khác nhau:

| Công cụ | Mục đích |
|---|---|
| jps | Liệt kê các JVM process mà tài khoản hiện tại có thể quan sát. |
| jcmd | Gửi diagnostic command tới JVM, xem flags/properties và thực hiện nhiều thao tác chẩn đoán. |
| jinfo | Đọc flags và system properties; thay đổi một số VM flags được hỗ trợ. |
| jhsdb | Phân tích JVM process hoặc crash dump ở mức thấp hơn; đặc biệt hữu ích cho postmortem analysis. |

Oracle phân loại jinfo là công cụ **experimental và unsupported**. Công cụ có thể thay đổi hoặc không còn được cung cấp trong các JDK tương lai. Tài liệu JDK 24 khuyến nghị dùng jcmd thay cho jinfo cho các nhu cầu chẩn đoán mới vì jcmd có bộ diagnostic command phong phú hơn và overhead thấp hơn.

Điều này không làm mất giá trị học tập của jinfo: hiểu cú pháp của nó giúp đọc được những runbook cũ, kiểm tra hệ thống đang dùng và chuyển đổi sang lệnh jcmd tương ứng.

## 3. Kiểm tra jinfo có sẵn

jinfo được cài trong thư mục bin của JDK. Kiểm tra hướng dẫn:

~~~bash
jinfo -h
~~~

Có thể dùng các dạng help sau:

~~~bash
jinfo -help
jinfo --help
~~~

Trên Windows PowerShell:

~~~powershell
where jinfo
& "$env:JAVA_HOME\bin\jinfo.exe" -h
~~~

Trên Linux/macOS:

~~~bash
which jinfo
"$JAVA_HOME/bin/jinfo" -h
~~~

Nếu shell không tìm thấy lệnh, kiểm tra PATH và JAVA_HOME. Một runtime image tối giản được tạo bằng jlink có thể không chứa jinfo. Khi đó cần dùng JDK có công cụ chẩn đoán phù hợp với môi trường của JVM đích.

Không dùng jinfo -version để kiểm tra phiên bản: cú pháp help của công cụ không cung cấp option này. Có thể dùng java --version để xác định JDK hiện tại và jinfo -h để xác nhận các option jinfo được hỗ trợ.

## 4. Tìm PID trước khi chạy jinfo

jinfo yêu cầu PID của một Java process đang hoạt động. Một số cách tìm PID:

Liệt kê JVM bằng jcmd:

~~~bash
jcmd -l
~~~

Liệt kê JVM bằng jps:

~~~bash
jps -l
~~~

Trên Linux:

~~~bash
ps -eo pid,user,args | grep '[j]ava'
~~~

Trên Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match 'java' } |
    Select-Object ProcessId, Name, CommandLine
~~~

Sau khi tìm thấy PID, xác minh đúng ứng dụng trước khi đọc hoặc thay đổi cấu hình. PID có thể được tái sử dụng sau khi process kết thúc; không dùng lại PID cũ trong log hoặc tài liệu mà không kiểm tra.

Ví dụ các lệnh trong bài dùng PID minh họa là 12345. Hãy thay bằng PID thật vừa xác nhận.

## 5. In toàn bộ flags và system properties

Nếu không truyền option, jinfo in cả JVM flags và Java system properties:

~~~bash
jinfo 12345
~~~

Output được chia thành các phần, thường có tiêu đề như:

~~~text
Java System Properties:
java.version=24.0.2
java.vendor=...
java.class.path=...
user.dir=...
...
VM Flags:
-XX:InitialHeapSize=...
-XX:MaxHeapSize=...
-XX:+UseG1GC
...
~~~

Đây là chế độ tổng hợp, tiện khi cần chụp nhanh cấu hình JVM. Tuy nhiên output có thể dài và chứa dữ liệu nhạy cảm. Khi chỉ cần một nhóm thông tin, nên chọn option cụ thể để giảm lượng dữ liệu được in ra.

## 6. In JVM flags bằng -flags

Dùng:

~~~bash
jinfo -flags 12345
~~~

Option này in các VM flags của process đích. Flags có thể cho biết cấu hình heap, garbage collector, code cache và những lựa chọn runtime khác.

Ví dụ output minh họa:

~~~text
VM Flags:
-XX:InitialHeapSize=33554432
-XX:MaxHeapSize=31675383808
-XX:+UseCompressedOops
-XX:+UseG1GC
~~~

Các giá trị thực tế phụ thuộc JDK, kiến trúc, RAM, container limits và option lúc khởi chạy. Không giả định một giá trị heap mặc định sẽ giống nhau trên mọi máy.

Một số flag có dạng:

- -XX:+TênFlag: Boolean flag đang bật.
- -XX:-TênFlag: Boolean flag đang tắt.
- -XX:TênFlag=GiáTrị: flag có giá trị số hoặc chuỗi.

jinfo -flags giúp quan sát cấu hình đang có hiệu lực; nó không phải danh sách đầy đủ mọi flag mà JVM có thể hỗ trợ. Nếu cần xem chi tiết flag, kiểu dữ liệu hoặc khả năng thay đổi, hãy tham khảo tài liệu JVM tương ứng và các lệnh chẩn đoán của jcmd.

## 7. In Java system properties bằng -sysprops

Dùng:

~~~bash
jinfo -sysprops 12345
~~~

Option này in các Java system properties theo dạng name-value pair.

Một số property thường gặp:

| Property | Ý nghĩa |
|---|---|
| java.version | Phiên bản Java runtime. |
| java.vendor | Nhà cung cấp JDK. |
| java.home | Thư mục cài đặt runtime. |
| java.class.path | Classpath của ứng dụng. |
| java.library.path | Đường dẫn tìm native library. |
| user.dir | Working directory của process. |
| user.home | Home directory của tài khoản chạy JVM. |
| os.name | Tên hệ điều hành. |
| file.encoding | Charset mặc định được runtime sử dụng theo cấu hình. |

Ứng dụng có thể tự đặt property bằng option -D khi khởi chạy:

~~~bash
java -Dapp.environment=staging -Dapp.region=ap-southeast-1 com.example.Main
~~~

Sau khi JVM chạy, có thể kiểm tra:

~~~bash
jinfo -sysprops 12345
~~~

Trong output sẽ có các dòng tương ứng với app.environment và app.region nếu chúng vẫn là system properties của process.

System properties là cấu hình runtime. Chúng không giống environment variables của hệ điều hành. Không thể suy ra toàn bộ environment của process chỉ từ jinfo -sysprops.

## 8. Đọc một VM flag bằng -flag name

Nếu chỉ cần kiểm tra một flag, dùng:

~~~bash
jinfo -flag UseG1GC 12345
~~~

Ví dụ output:

~~~text
-XX:+UseG1GC
~~~

Một ví dụ khác:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Kết quả có thể là:

~~~text
-XX:-HeapDumpOnOutOfMemoryError
~~~

hoặc:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
~~~

Dấu cộng biểu thị Boolean flag đang bật; dấu trừ biểu thị flag đang tắt.

Cách truy vấn một flag phù hợp khi cần kiểm tra nhanh một giả thuyết mà không phải đọc toàn bộ danh sách. Tên flag phải được viết đúng theo tên HotSpot VM hỗ trợ.

## 9. Bật hoặc tắt Boolean flag khi JVM đang chạy

jinfo có thể bật hoặc tắt một số Boolean VM flags bằng cú pháp:

~~~text
jinfo -flag +<flag-name> <pid>
jinfo -flag -<flag-name> <pid>
~~~

Ví dụ bật chế độ tạo heap dump khi gặp OutOfMemoryError:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 12345
~~~

Kiểm tra lại:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Nếu flag đã bật, kết quả:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
~~~

Tắt flag:

~~~bash
jinfo -flag -HeapDumpOnOutOfMemoryError 12345
~~~

Sau đó kiểm tra lại bằng lệnh truy vấn.

Thay đổi này tác động lên JVM process đang chạy. Nếu ứng dụng restart, cấu hình lúc khởi động sẽ được áp dụng lại; thay đổi runtime không tự ghi vào file cấu hình deployment.

**Chỉ một số flag có thể thay đổi động.** Flag phải được HotSpot đánh dấu phù hợp để thay đổi khi chạy, thường được mô tả là manageable. Với flag không hỗ trợ runtime update, jinfo có thể báo lỗi dù cú pháp lệnh hợp lệ.

Không bật một flag trên production chỉ vì lệnh được chấp nhận. Ví dụ HeapDumpOnOutOfMemoryError có thể ghi heap dump ra đĩa khi OutOfMemoryError xảy ra; cần đảm bảo thư mục đích, dung lượng lưu trữ và quyền truy cập phù hợp.

## 10. Đặt giá trị cho flag bằng name=value

Với flag nhận giá trị, cú pháp là:

~~~text
jinfo -flag <flag-name>=<value> <pid>
~~~

Ví dụ cú pháp tổng quát:

~~~bash
jinfo -flag MaxHeapFreeRatio=75 12345
~~~

Lệnh chỉ thành công khi flag đó hỗ trợ thay đổi động và giá trị hợp lệ. Không phải mọi flag đều có thể cập nhật trong runtime; các lựa chọn liên quan đến kích thước heap khởi tạo, cấu trúc VM hoặc subsystem đã khởi động có thể cần restart.

Quy trình an toàn:

1. Đọc giá trị hiện tại bằng jinfo -flag.
2. Kiểm tra tài liệu của flag và xác định flag có thể thay đổi động hay không.
3. Đánh giá tác động tới hiệu năng và hành vi ứng dụng.
4. Thực hiện thay đổi trên process thử nghiệm trước.
5. Đọc lại flag để xác nhận giá trị.
6. Ghi nhận thay đổi trong nhật ký vận hành.
7. Đưa cấu hình mong muốn vào tham số khởi chạy hoặc cấu hình quản lý để lần restart sau giữ cùng chính sách.

Ví dụ MaxHeapFreeRatio ở trên minh họa cú pháp name=value; không được hiểu rằng mọi JDK hoặc JVM đều cho phép thay đổi flag này ở runtime.

## 11. Ví dụ hoàn chỉnh: kiểm tra cấu hình JVM

Tạo file **JinfoProbe.java**:

~~~java
public class JinfoProbe {
    public static void main(String[] args) throws InterruptedException {
        System.out.println(
                "JinfoProbe ready; pid=" + ProcessHandle.current().pid());

        Thread.sleep(120_000);
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 JinfoProbe.java
~~~

Chạy với một JVM flag và một system property:

~~~bash
java -Xms32m -Dprobe.mode=jinfo-check JinfoProbe
~~~

Ví dụ stdout:

~~~text
JinfoProbe ready; pid=12345
~~~

PID là giá trị động. Mở terminal thứ hai và dùng PID vừa được in ra.

In flags:

~~~bash
jinfo -flags 12345
~~~

Kiểm tra system property:

~~~bash
jinfo -sysprops 12345
~~~

Trong output system properties cần tìm:

~~~text
probe.mode=jinfo-check
~~~

Kiểm tra một flag:

~~~bash
jinfo -flag UseG1GC 12345
~~~

Bật một Boolean flag có thể thay đổi động:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 12345
jinfo -flag HeapDumpOnOutOfMemoryError 12345
~~~

Trên JDK 24.0.2, thử nghiệm với process Java 17 đã xác nhận:

- jinfo -flags kết thúc với exit code 0 và trả về VM flags.
- jinfo -sysprops kết thúc với exit code 0 và có property probe.mode=jinfo-check.
- jinfo -flag UseG1GC in -XX:+UseG1GC.
- Lệnh bật HeapDumpOnOutOfMemoryError kết thúc với exit code 0; truy vấn sau đó in -XX:+HeapDumpOnOutOfMemoryError.

Kết thúc chương trình mẫu bằng Ctrl+C sau khi kiểm tra xong.

## 12. Dùng jcmd thay cho jinfo

Oracle khuyến nghị dùng jcmd cho chẩn đoán JVM mới. Các lệnh tương ứng thường dùng:

| Nhu cầu | jinfo | jcmd |
|---|---|---|
| In VM flags | jinfo -flags PID | jcmd PID VM.flags |
| In tất cả flags VM hỗ trợ | Không có tương đương đơn giản trong jinfo | jcmd PID VM.flags -all |
| In system properties | jinfo -sysprops PID | jcmd PID VM.system_properties |
| Xem phiên bản JVM | Không phải mục đích chính | jcmd PID VM.version |
| Đặt một VM flag | jinfo -flag name=value PID | jcmd PID VM.set_flag name value |

Ví dụ:

~~~bash
jcmd 12345 VM.flags
jcmd 12345 VM.flags -all
jcmd 12345 VM.system_properties
jcmd 12345 VM.version
~~~

Thay đổi một flag bằng jcmd:

~~~bash
jcmd 12345 VM.set_flag HeapDumpOnOutOfMemoryError true
~~~

Xem cú pháp command mà JVM đích hỗ trợ:

~~~bash
jcmd 12345 help VM.set_flag
~~~

jcmd có thêm thông tin về Impact và Syntax cho từng diagnostic command. Hãy xem help của target JVM trước khi chạy, đặc biệt khi thao tác trên production.

## 13. Quyền truy cập và Attach mechanism

jinfo kết nối tới JVM đích bằng cơ chế Attach. Một số điều kiện cần đáp ứng:

- PID phải thuộc một Java process đang hoạt động.
- jinfo và JVM đích phải nằm trong môi trường máy có thể giao tiếp qua Attach.
- User chạy jinfo cần quyền phù hợp với user sở hữu JVM.
- Attach mechanism của JVM phải được bật.
- Công cụ và JVM đích phải tương thích về nền tảng và runtime.

Nếu JVM được khởi chạy với:

~~~text
-XX:+DisableAttachMechanism
~~~

các công cụ dùng Attach như jinfo và jcmd không thể kết nối theo cách thông thường.

Nếu jinfo báo permission denied hoặc attach failure, kiểm tra process owner, PID, namespace, cấu hình JVM và quyền hệ điều hành. Không mặc định chạy với quyền Administrator/root; hãy dùng đúng tài khoản vận hành được cấp quyền.

## 14. Container và giới hạn nền tảng

Khi JVM chạy trong Docker hoặc container, PID namespace và filesystem namespace có thể ảnh hưởng việc tìm process và attach.

Nếu jps trên host không liệt kê JVM trong container:

1. Xác định container và PID bên trong container bằng công cụ quản lý phù hợp.
2. Kiểm tra process bằng ps trong cùng namespace.
3. Chạy jinfo từ môi trường có thể attach vào JVM đích.
4. Đảm bảo user, filesystem và Attach socket phù hợp.
5. Xác minh lại PID trước khi gửi command.

Ví dụ chạy công cụ trong container:

~~~bash
docker exec -it <container-name> jinfo -flags <pid>
~~~

Với Kubernetes:

~~~bash
kubectl exec -it <pod-name> -c <container-name> -- jinfo -sysprops <pid>
~~~

Các lệnh trên phụ thuộc image có JDK tool và quyền truy cập container. PID trên host có thể khác PID nhìn từ bên trong container.

Trên Windows, một số cấu hình có thể cần thành phần Debugging Tools for Windows nếu thiếu dbgeng.dll; PATH cũng cần trỏ tới vị trí jvm.dll của JVM đích theo hướng dẫn JDK. Nếu jinfo chạy được trên máy hiện tại thì không cần cài thêm thành phần này chỉ để làm theo ví dụ.

## 15. Thông tin nhạy cảm trong output

jinfo -sysprops và chế độ không option có thể tiết lộ:

- User home và working directory.
- Classpath hoặc đường dẫn thư viện nội bộ.
- Endpoint, tên môi trường và thông tin kết nối.
- Property do ứng dụng tự đặt.
- Cấu hình có thể chứa token hoặc credential nếu ứng dụng truyền sai cách.

Không đưa password, API token hoặc private key vào JVM argument hay system property. Ưu tiên secret manager hoặc cơ chế cấp phát secret của nền tảng.

Trước khi gửi output cho đồng nghiệp hoặc đính kèm ticket:

- Chỉ thu thập nhóm thông tin cần thiết.
- Xóa token, password, endpoint nhạy cảm và dữ liệu cá nhân.
- Giới hạn người có thể đọc log.
- Không lưu output thô trong thư mục public hoặc repository.
- Xóa bản tạm theo chính sách lưu trữ.

Quyền chạy jinfo cũng là quyền quan sát cấu hình ứng dụng. Chỉ cấp cho tài khoản có nhiệm vụ chẩn đoán process đó.

## 16. Dùng jhsdb jinfo với core dump

jinfo thông thường nhận PID của JVM đang chạy. Khi cần phân tích crash dump/core file, dùng chế độ jinfo của công cụ jhsdb.

Ví dụ:

~~~bash
jhsdb jinfo --exe /path/to/java --core core.12345
~~~

Chỉ in VM flags:

~~~bash
jhsdb jinfo --exe /path/to/java --core core.12345 --flags
~~~

Chỉ in system properties:

~~~bash
jhsdb jinfo --exe /path/to/java --core core.12345 --sysprops
~~~

Đường dẫn executable phải là binary tương ứng với core dump. Với JVM được tạo qua JNI Invocation API, binary tạo core có thể không mang tên java.

jhsdb là công cụ phân tích mức thấp và cũng được phân loại experimental/unsupported. Đặc biệt, attach jhsdb vào một JVM đang chạy có thể làm process bị treo và thậm chí crash khi debugger detach. Chỉ dùng ví dụ core dump cho postmortem analysis và đọc hướng dẫn jhsdb của đúng JDK.

## 17. Lỗi thường gặp khi chạy jinfo

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jinfo is not recognized | JDK bin chưa nằm trong PATH hoặc runtime image không có công cụ. | Kiểm tra JAVA_HOME, PATH và JDK đầy đủ. |
| Could not attach to process | PID sai, process đã thoát hoặc Attach mechanism không khả dụng. | Chạy lại jcmd -l/jps -l và xác minh PID. |
| Operation not permitted / access denied | User không có quyền attach vào JVM. | Dùng đúng tài khoản sở hữu process hoặc quyền được cấp. |
| jinfo -flags không trả về kết quả mong đợi | Đang đọc nhầm JVM hoặc JDK vendor/runtime khác. | Kiểm tra PID, VM.version và đường dẫn công cụ. |
| jinfo -sysprops không có property mong muốn | Property không được đặt cho process hoặc đã thay đổi trong runtime. | Kiểm tra command line, ứng dụng và system property hiện tại. |
| jinfo -flag báo flag không tồn tại | Sai tên flag hoặc flag không có trong phiên bản JVM đích. | Kiểm tra tài liệu đúng JDK và jcmd VM.flags -all. |
| jinfo không đổi được flag | Flag không hỗ trợ runtime update hoặc giá trị không hợp lệ. | Kiểm tra khả năng manageable, cú pháp và giá trị. |
| Thay đổi flag mất sau restart | jinfo chỉ đổi cấu hình của process hiện tại. | Cập nhật tham số khởi chạy hoặc cấu hình deployment. |
| jinfo không thấy JVM trong container | PID namespace hoặc môi trường attach khác nhau. | Chạy công cụ trong container hoặc namespace phù hợp. |
| Output chứa thông tin bí mật | System property hoặc JVM argument có secret. | Không chia sẻ output thô; loại bỏ secret và sửa cách cấp phát. |
| jinfo không có trên JDK mới | Công cụ experimental/unsupported đã thay đổi hoặc bị loại bỏ. | Dùng jcmd hoặc công cụ chẩn đoán được hỗ trợ. |

## 18. Quy trình kiểm tra cấu hình JVM

Một quy trình dễ lặp lại:

1. Xác định JDK và công cụ đang sử dụng bằng java --version và jinfo -h.
2. Tìm JVM process bằng jcmd -l hoặc jps -l.
3. Xác minh PID, ứng dụng và user sở hữu process.
4. Dùng jinfo -flags khi cần đọc VM flags.
5. Dùng jinfo -sysprops khi cần đọc system properties.
6. Dùng jinfo -flag name PID để kiểm tra một flag cụ thể.
7. Chỉ thay đổi flag sau khi xác nhận flag hỗ trợ runtime update và hiểu tác động.
8. Đọc lại flag để xác nhận giá trị mới.
9. Ghi nhận thay đổi và cập nhật cấu hình deployment nếu cần giữ sau restart.
10. Với chẩn đoán mới, ưu tiên jcmd và xem help/Impact của command tương ứng.
11. Rà soát output để loại bỏ thông tin nhạy cảm trước khi chia sẻ.
12. Với crash dump, dùng jhsdb jinfo và executable tương ứng thay vì PID process đã kết thúc.

## 19. Checklist khi sử dụng jinfo

- [ ] Đã xác nhận jinfo có trong JDK đang dùng.
- [ ] Đã xác định đúng PID của JVM đích.
- [ ] Đã phân biệt -flags với -sysprops.
- [ ] Đã biết không option sẽ in cả flags và system properties.
- [ ] Đã dùng -flag name để đọc một flag cụ thể.
- [ ] Đã kiểm tra flag có thể thay đổi động trước khi dùng +name, -name hoặc name=value.
- [ ] Đã đọc lại flag sau khi thay đổi.
- [ ] Đã hiểu thay đổi runtime không tự tồn tại sau restart.
- [ ] Đã kiểm tra quyền user và Attach mechanism.
- [ ] Đã xem xét container/PID namespace nếu process không được tìm thấy.
- [ ] Đã bảo vệ output có thể chứa system property hoặc cấu hình nhạy cảm.
- [ ] Đã biết jinfo là công cụ experimental/unsupported và ưu tiên jcmd cho chẩn đoán mới.
- [ ] Đã dùng jhsdb jinfo đúng mục đích khi phân tích core dump.

## 20. Tài liệu tham khảo

- Oracle JDK 24 — Diagnostic Tools: https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html
- Oracle JDK 24 — The jhsdb Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jhsdb.html
- Oracle JDK 26 — The jinfo Command: https://docs.oracle.com/en/java/javase/26/docs/specs/man/jinfo.html

jinfo giúp đọc cấu hình của một JVM đang chạy và thay đổi một số flag được phép cập nhật động. Khi xác minh đúng PID, phân biệt flags với system properties, kiểm tra khả năng thay đổi của từng flag và bảo vệ output, bạn có thể dùng công cụ này để điều tra cấu hình runtime. Với công việc chẩn đoán mới, hãy ưu tiên jcmd theo khuyến nghị của tài liệu JDK 24.