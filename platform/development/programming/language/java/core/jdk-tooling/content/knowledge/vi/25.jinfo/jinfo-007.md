# Quyền truy cập process với jinfo

**jinfo** là công cụ dòng lệnh của JDK dùng để lấy thông tin cấu hình từ một Java process đang chạy. Công cụ có thể hiển thị các JVM flags và Java system properties, đồng thời hỗ trợ thay đổi một số VM flags có thể cập nhật trong lúc JVM hoạt động.

Đề bài **Quyền truy cập process** tập trung vào cách xác định đúng process, điều kiện hệ điều hành cho phép attach, quyền của tài khoản vận hành và những rủi ro khi đọc hoặc thay đổi cấu hình JVM. Một PID đúng chưa đủ: process phải là Java process, attach mechanism phải được bật và người chạy công cụ phải có quyền truy cập phù hợp.

Cần biết trạng thái của công cụ: trong JDK 26, Oracle đánh dấu jinfo là **experimental and unsupported**, có thể không còn trong các JDK tương lai. Oracle khuyến nghị dùng **jcmd** cho chẩn đoán hiện đại vì có nhiều chức năng hơn và giảm overhead. Bài này vẫn trình bày jinfo để hiểu hệ thống cũ, cách cấp quyền process và cách chuyển sang jcmd.

## 1. jinfo dùng để làm gì?

jinfo lấy thông tin cấu hình từ một Java process được chỉ định bằng process ID (PID). Thông tin chính gồm:

- JVM command-line flags: các tùy chọn dùng để khởi chạy HotSpot JVM.
- Java system properties: các cặp tên/giá trị được cung cấp qua -D hoặc do runtime và ứng dụng thiết lập.
- Giá trị của một JVM flag cụ thể.
- Một số JVM flags có thể được bật, tắt hoặc đổi giá trị trong lúc process đang chạy.

Các tình huống sử dụng:

| Tình huống | Thông tin cần xem |
|---|---|
| Ứng dụng dùng sai Java release | JVM version và command line |
| Không rõ heap được cấu hình bao nhiêu | Các flags như InitialHeapSize và MaxHeapSize |
| Điều tra classpath | java.class.path và các property liên quan |
| Kiểm tra cấu hình ứng dụng | System properties |
| Xác nhận một flag đang bật hay tắt | Giá trị flag cụ thể |
| Kiểm tra cấu hình sau khi khởi chạy | Flags và properties hiện tại |

jinfo không phải công cụ đọc mọi trạng thái nội bộ của process, không phải debugger và không phải công cụ giám sát liên tục. Nó cũng không tự xác định cấu hình nào là an toàn; người vận hành phải hiểu ý nghĩa của từng flag/property.

## 2. Cú pháp và cách chỉ định process

Cú pháp JDK 26:

~~~bash
jinfo [option] pid
~~~

Trong đó:

- option là tùy chọn muốn thực hiện.
- pid là process ID của Java process cần kiểm tra.

Ví dụ:

~~~bash
jinfo 2125
~~~

Nếu không truyền option, jinfo in cả JVM command-line flags và system properties.

jinfo làm việc với PID của process trên máy cục bộ. Cú pháp jinfo JDK 26 không phải một giao thức quản trị JVM từ xa qua hostname hoặc IP. Muốn quản trị từ xa, cần dùng cơ chế quản trị riêng có xác thực và bảo vệ mạng phù hợp, chẳng hạn JMX được cấu hình an toàn.

## 3. Xác định đúng PID trước khi attach

Không nên đoán PID hoặc chọn một PID chỉ vì process có tên gần giống ứng dụng cần điều tra.

### Dùng jps

~~~bash
jps -l
~~~

Ví dụ output minh họa:

~~~text
2125 com.acme.DemoServer
5485 jdk.jcmd/sun.tools.jps.Jps
~~~

jps liệt kê các HotSpot JVM mà tài khoản hiện tại có quyền nhìn thấy. Tùy chọn -l hiển thị tên class đầy đủ hoặc tên module/JAR của ứng dụng.

### Dùng công cụ hệ điều hành

Trên Linux:

~~~bash
ps -ef | grep java
~~~

Hoặc:

~~~bash
ps -eo pid,user,group,args
~~~

Trên Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^java(w)?\.exe$' } |
    Select-Object ProcessId, Name, CommandLine
~~~

Các lệnh này giúp đối chiếu PID, tài khoản chạy process và command line. Output command line có thể chứa thông tin nhạy cảm; chỉ lưu hoặc chia sẻ khi có quyền phù hợp.

### Kiểm tra PID trước khi dùng

Giả sử PID là 2125:

~~~bash
jinfo -flags 2125
~~~

Nếu PID đã kết thúc và được hệ điều hành cấp lại cho process khác, lệnh có thể thất bại hoặc nhắm nhầm process. Vì vậy, hãy xác nhận PID ngay trước thao tác attach, đặc biệt khi chạy script tự động.

## 4. Quyền truy cập process và cơ chế attach

jinfo cần kết nối tới JVM đang chạy thông qua cơ chế attach của HotSpot. Đây là thao tác ở cấp hệ điều hành và process, không phải quyền Java thông thường của một class trong ứng dụng.

Các điều kiện vận hành quan trọng:

| Điều kiện | Ý nghĩa |
|---|---|
| Cùng máy | jinfo chạy trên host đang có JVM đích |
| PID hợp lệ | PID phải thuộc Java process |
| Quyền hệ điều hành | Tài khoản chạy công cụ phải được phép truy cập process |
| Tài khoản phù hợp | Với HotSpot attach tools, nên chạy bằng cùng effective user ID và group ID đã khởi chạy JVM |
| Attach được bật | JVM không được khởi chạy với DisableAttachMechanism |
| JDK tương thích | Dùng công cụ cùng JDK release với JVM đích khi có thể |

Oracle nêu rõ yêu cầu cùng effective user và group identifiers trong hướng dẫn attach của jcmd. jinfo cũng thuộc nhóm công cụ attach cục bộ của HotSpot, vì vậy quy trình vận hành an toàn là dùng tài khoản service đã khởi chạy JVM hoặc tài khoản được quản trị viên cấp quyền tương ứng.

Không mặc định chạy bằng Administrator hoặc root để vượt qua lỗi quyền. Hãy xác định process thuộc tài khoản nào và dùng quy trình truy cập được tổ chức cho phép.

### Ví dụ tài khoản process

~~~text
PID    USER          COMMAND
2125   acme-service  java -jar app.jar
~~~

Nếu JVM chạy bằng tài khoản acme-service, người vận hành nên thực hiện lệnh jinfo bằng chính tài khoản đó hoặc một tài khoản được cấp quyền attach theo chính sách hệ điều hành.

Trên Linux có thể kiểm tra danh tính process bằng ps:

~~~bash
ps -o pid,user,group,args -p 2125
~~~

Lệnh này chỉ hiển thị thông tin process; nó không cấp quyền attach.

## 5. Attach mechanism có thể bị vô hiệu hóa

HotSpot cung cấp tùy chọn:

~~~bash
-XX:+DisableAttachMechanism
~~~

Khi JVM được khởi chạy với tùy chọn này, các công cụ dựa trên attach mechanism như jcmd, jinfo, jstack và jmap không thể attach theo cách thông thường.

Điểm cần nhớ:

- Mặc định, attach mechanism được bật.
- DisableAttachMechanism phải được quyết định khi khởi chạy JVM.
- jinfo không thể tự bật lại attach mechanism cho một process đang chạy.
- Nếu cần dùng công cụ attach, phải đánh giá cấu hình khởi chạy và lên kế hoạch restart process khi phù hợp.
- Không tự ý bỏ tùy chọn bảo vệ trong production nếu chưa hiểu lý do nó được bật.

Kiểm tra command line của process hoặc cấu hình service để tìm flag này. Nếu process đã khởi chạy với attach bị tắt, việc chạy jinfo nhiều lần không giải quyết được nguyên nhân.

## 6. Quyền truy cập trong Docker và container

PID trong container có thể khác PID nhìn thấy từ host do PID namespace. Một process có thể mang PID 1 bên trong container nhưng có PID khác trên host.

Một số điểm cần lưu ý:

- jps -l có thể không liệt kê JVM chạy trong Docker process riêng biệt.
- Dùng ps trong đúng namespace để xác định PID.
- Có thể chạy jinfo bên trong container nếu JDK và quyền attach có sẵn.
- Nếu dùng host PID namespace, phải xác nhận PID host trỏ tới đúng JVM.
- Tài khoản chạy jinfo vẫn cần quyền truy cập process tương ứng.
- Container policy, user namespace và cơ chế bảo vệ của host có thể giới hạn thao tác attach.

Ví dụ thực hiện bên trong container:

~~~bash
ps -ef
jinfo -flags 1
~~~

PID 1 ở đây chỉ đúng khi Java process thực sự là process có PID 1 trong container. Hãy kiểm tra bằng ps trước khi chạy.

Không lấy PID từ container này rồi dùng trong container khác. PID namespace có thể khiến cùng một con số đại diện cho các process khác nhau.

## 7. Các tùy chọn đọc thông tin của jinfo

### In toàn bộ thông tin mặc định

~~~bash
jinfo 2125
~~~

Khi không truyền option, jinfo in cả command-line flags và các cặp Java system property.

Output có thể dài. Trong môi trường production, hãy cân nhắc chỉ lấy nhóm thông tin cần thiết.

### In các flags được truyền lúc khởi chạy

~~~bash
jinfo -flags 2125
~~~

Tùy chọn -flags hiển thị JVM flags được truyền khi khởi chạy process. Nó hữu ích để kiểm tra các tùy chọn như heap size, garbage collector hoặc cấu hình JVM đã được khai báo rõ trong startup script.

Không nên nhầm danh sách flags khởi chạy với toàn bộ flags mặc định mà JVM hỗ trợ.

### In system properties

~~~bash
jinfo -sysprops 2125
~~~

Tùy chọn -sysprops in các cặp Java system property name-value.

Các property có thể gồm:

- java.version
- java.vendor
- java.home
- java.class.path
- user.dir
- file.encoding
- Các property ứng dụng truyền bằng -D.

System properties có thể tiết lộ endpoint nội bộ, đường dẫn cấu hình, tên tài khoản hoặc secret nếu ứng dụng lưu secret sai cách. Hãy xem output là dữ liệu nội bộ và lọc trước khi chia sẻ.

### Xem giá trị một flag

~~~bash
jinfo -flag MaxHeapSize 2125
~~~

Tùy chọn -flag name in tên và giá trị của JVM flag được chỉ định.

Dùng cách này khi chỉ cần xác nhận một cấu hình cụ thể, thay vì in toàn bộ flags.

### Xem trợ giúp

~~~bash
jinfo -help
~~~

Có thể dùng:

~~~bash
jinfo -h
~~~

Tài liệu và option khả dụng có thể thay đổi giữa các JDK vì jinfo là công cụ experimental.

## 8. Tùy chọn -flag có thể thay đổi cấu hình process

Đây là phần cần thận trọng nhất khi nói về quyền truy cập process.

jinfo hỗ trợ ba dạng -flag:

| Cú pháp | Hành động |
|---|---|
| -flag name | Đọc giá trị của flag |
| -flag +name hoặc -flag -name | Bật hoặc tắt một Boolean flag |
| -flag name=value | Đặt giá trị mới cho flag |

Ví dụ dạng đọc:

~~~bash
jinfo -flag MaxHeapSize 2125
~~~

Dạng bật/tắt Boolean:

~~~bash
jinfo -flag +BooleanFlag 2125
jinfo -flag -BooleanFlag 2125
~~~

Dạng đặt giá trị:

~~~bash
jinfo -flag FlagName=NewValue 2125
~~~

BooleanFlag và FlagName ở trên là tên minh họa cho cú pháp. Khi vận hành thật, chỉ dùng tên flag được JVM đích hỗ trợ.

Không phải mọi JVM flag đều có thể thay đổi trong lúc chạy. Một số flag chỉ có hiệu lực khi JVM khởi động; một số flag được đánh dấu có thể quản lý động. Nếu cố thay đổi flag không hỗ trợ cập nhật runtime, thao tác sẽ thất bại hoặc JVM từ chối giá trị.

Trước khi thay đổi:

1. Xác nhận flag có được phép thay đổi động không.
2. Đọc giá trị hiện tại.
3. Kiểm tra giá trị mới có nằm trong phạm vi hợp lệ không.
4. Đánh giá tác động tới heap, GC, logging hoặc hành vi runtime.
5. Ghi nhận người thực hiện và thời điểm thay đổi.
6. Có kế hoạch khôi phục giá trị nếu kết quả không mong muốn.

Không thay đổi flag của process production chỉ để thử nghiệm cú pháp.

## 9. Đọc flags và system properties bằng jcmd

Oracle khuyến nghị dùng jcmd thay cho jinfo cho chẩn đoán mới. Các lệnh tương ứng thường dùng:

| Nhu cầu | jinfo | jcmd |
|---|---|---|
| Xem flags | jinfo -flags PID | jcmd PID VM.flags |
| Xem mọi flags được JVM hỗ trợ | Không có tùy chọn tương đương trực tiếp rõ ràng | jcmd PID VM.flags -all |
| Xem một flag | jinfo -flag name PID | jcmd PID VM.flags -all và tìm flag |
| Xem system properties | jinfo -sysprops PID | jcmd PID VM.system_properties |
| Đổi giá trị flag có thể quản lý | jinfo -flag name=value PID | jcmd PID VM.set_flag name value |

Ví dụ đọc flags:

~~~bash
jcmd 2125 VM.flags
~~~

Xem tất cả flags:

~~~bash
jcmd 2125 VM.flags -all
~~~

Xem system properties:

~~~bash
jcmd 2125 VM.system_properties
~~~

Đổi một flag có hỗ trợ runtime:

~~~bash
jcmd 2125 VM.set_flag FlagName NewValue
~~~

Trước khi dùng VM.set_flag, kiểm tra:

~~~bash
jcmd 2125 help VM.set_flag
~~~

jcmd cũng yêu cầu quyền attach phù hợp và chạy trên cùng máy với JVM. Oracle mô tả cùng effective user và group identifiers là điều kiện của thao tác này. Việc chuyển sang jcmd không loại bỏ yêu cầu quyền process.

## 10. jinfo là công cụ experimental và unsupported

Manual JDK 26 ghi rõ jinfo là experimental và unsupported. Điều này có ý nghĩa thực tế:

- Công cụ có thể thay đổi hoặc bị loại bỏ trong JDK tương lai.
- Không nên xây dựng pipeline production phụ thuộc vào format output của jinfo.
- Script phân tích output có thể hỏng khi JDK thay đổi.
- Khả năng hỗ trợ trên các hệ điều hành không giống nhau.
- Nên ưu tiên jcmd cho quy trình chẩn đoán mới.

Oracle cũng khuyến nghị không dùng serviceability tools từ một JDK release để troubleshoot JVM thuộc release khác. Hãy dùng JDK tương thích với process đích để tránh lỗi do khác implementation hoặc giao thức nội bộ.

Nếu một hệ thống cũ đang sử dụng jinfo, hãy ghi lại phiên bản JDK, hệ điều hành, command và định dạng output trước khi migration.

## 11. Yêu cầu riêng trên Windows

Manual jinfo JDK 26 nêu một điều kiện Windows cụ thể:

- Nếu dbgeng.dll không có, cần cài Debugging Tools for Windows để các công cụ này hoạt động.
- PATH cần chứa vị trí của jvm.dll được process đích sử dụng hoặc vị trí tương ứng với executable/core file.

Khi gặp lỗi native debugging hoặc attach trên Windows, kiểm tra:

1. JDK và kiến trúc JVM đích.
2. PATH có chứa thư mục cần thiết.
3. dbgeng.dll có sẵn hay chưa.
4. Process có thuộc đúng tài khoản và quyền truy cập không.
5. jinfo có tương thích với JDK của process đích không.

Không tải riêng DLL từ nguồn không xác định để sửa lỗi. Dùng công cụ Windows chính thức và bộ JDK được tổ chức quản lý.

## 12. Bảo vệ dữ liệu lấy từ process

Quyền attach có thể cho phép người vận hành đọc nhiều thông tin mà ứng dụng đang sử dụng.

Ví dụ:

- java.class.path có thể tiết lộ thư mục và cấu trúc triển khai.
- java.home cho biết vị trí JDK.
- user.dir cho biết thư mục làm việc.
- System properties tùy chỉnh có thể chứa endpoint, token hoặc cấu hình nội bộ.
- JVM flags có thể tiết lộ heap size, GC và các tùy chọn vận hành.

Các biện pháp cần áp dụng:

- Chỉ cấp quyền attach cho nhóm vận hành cần thiết.
- Không chia sẻ output đầy đủ lên kênh công khai.
- Lọc secret và thông tin định danh trước khi gửi log.
- Không lưu output trong thư mục có quyền đọc công khai.
- Ghi lại PID, tài khoản, thời gian và mục đích thu thập.
- Giới hạn retention của file diagnostic.
- Không đưa password hoặc token vào tham số JVM ngay từ đầu.

Đặc biệt, không chạy jinfo trên process không thuộc phạm vi quản trị của mình. Quyền truy cập process có thể tiết lộ dữ liệu ứng dụng và có thể cho phép thay đổi một số JVM flags.

## 13. Dùng jhsdb jinfo cho core dump

jinfo trong JDK 26 nhận PID của Java process đang chạy. Khi cần đọc thông tin từ core dump sau sự cố, dùng chế độ postmortem của jhsdb:

~~~bash
jhsdb jinfo --exe /path/to/java --core /path/to/core
~~~

Trong đó:

- --exe là Java executable tương ứng với core dump.
- --core là file core dump cần phân tích.

Ví dụ trên Linux có thể dùng gcore để tạo core dump khi có quyền và chính sách vận hành phù hợp, sau đó phân tích bằng jhsdb.

Cần phân biệt rõ hai trường hợp:

- jinfo PID: lấy cấu hình từ Java process đang chạy.
- jhsdb jinfo --exe ... --core ...: đọc thông tin từ core dump.

Không dùng jhsdb để attach tùy tiện vào live production process. Manual JDK 26 cảnh báo việc attach jhsdb vào process đang chạy có thể khiến process bị treo và có khả năng crash khi debugger detach. Với process đang hoạt động, ưu tiên jcmd.

## 14. Ví dụ Java 17+: tạo process để thực hành quyền truy cập

Ví dụ này tạo một Java process chạy chờ để có thời gian xác định PID và dùng jinfo từ terminal thứ hai.

Cấu trúc:

~~~text
project/
  src/
    com/acme/DemoServer.java
  out/
~~~

Tệp src/com/acme/DemoServer.java:

~~~java
package com.acme;

import java.util.concurrent.CountDownLatch;

public final class DemoServer {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");
        new CountDownLatch(1).await();
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d out src/com/acme/DemoServer.java
~~~

Chạy process:

~~~bash
java -cp out com.acme.DemoServer
~~~

Stdout:

~~~text
READY
~~~

Mở terminal thứ hai và tìm PID:

~~~bash
jps -l
~~~

Giả sử PID hiển thị là 2125. Xem flags:

~~~bash
jinfo -flags 2125
~~~

Xem system properties:

~~~bash
jinfo -sysprops 2125
~~~

Xem một flag:

~~~bash
jinfo -flag MaxHeapSize 2125
~~~

Output flags và properties thay đổi theo JDK, hệ điều hành và cấu hình khởi chạy. Không có một danh sách giá trị cố định cho mọi máy.

Nếu jinfo không có hoặc không hoạt động trên JDK đang dùng, thực hiện các bước tương ứng bằng jcmd:

~~~bash
jcmd 2125 VM.flags
jcmd 2125 VM.system_properties
~~~

Sau khi hoàn tất, quay lại terminal chạy DemoServer và nhấn Ctrl+C để dừng process thử nghiệm.

## 15. Troubleshooting lỗi truy cập process

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Process ID không tồn tại | PID sai hoặc process đã thoát | Chạy lại jps/ps và xác nhận PID mới |
| Process không phải Java process | PID trỏ tới ứng dụng khác | Kiểm tra command line và process executable |
| Attach failed hoặc permission denied | Tài khoản chạy tool không có quyền truy cập | Kiểm tra owner, effective UID/GID và quyền hệ điều hành |
| Không thấy JVM trong jps | Khác user hoặc JVM ở Docker namespace riêng | Dùng ps trong đúng namespace hoặc chạy tool trong container |
| Attach mechanism disabled | JVM khởi chạy với -XX:+DisableAttachMechanism | Kiểm tra startup flags và lập kế hoạch restart nếu cần attach |
| jinfo không được nhận diện | JDK bin chưa nằm trong PATH hoặc bản JDK không có tool | Kiểm tra JAVA_HOME và thư mục bin |
| Unknown flag | Flag không tồn tại trong JVM release hoặc viết sai tên | Kiểm tra flags bằng jcmd và dùng tên chính xác |
| Flag không thể đổi | Flag không hỗ trợ cập nhật runtime | Kiểm tra khả năng quản lý động và thay đổi khi restart nếu cần |
| Output thiếu system property | Đã dùng -flags thay cho -sysprops | Chọn đúng option |
| jinfo lỗi trên Windows | Thiếu dbgeng.dll hoặc PATH không tìm thấy jvm.dll | Cài Debugging Tools for Windows và kiểm tra PATH |
| jinfo hoạt động khác giữa hai JDK | Công cụ experimental hoặc khác release | Dùng tool cùng release với target JVM; ưu tiên jcmd |
| Output có secret | Ứng dụng truyền secret qua -D hoặc command line | Hạn chế truy cập, lọc output và sửa cách quản lý secret |
| Core dump không đọc được | Sai executable hoặc core file không tương ứng | Dùng đúng binary đã tạo core và kiểm tra file dump |

## 16. Quy trình cấp và sử dụng quyền truy cập process

Một quy trình vận hành có thể áp dụng:

1. Xác định service và mục tiêu cần chẩn đoán.
2. Xác nhận host, container và PID của JVM.
3. Kiểm tra tài khoản sở hữu process bằng ps hoặc công cụ OS.
4. Dùng tài khoản vận hành được cấp quyền attach.
5. Xác nhận attach mechanism không bị vô hiệu hóa.
6. Kiểm tra JDK release của JVM và dùng công cụ tương thích.
7. Bắt đầu bằng lệnh đọc ít tác động như jinfo -flag hoặc jcmd VM.flags.
8. Chỉ đọc system properties khi cần và bảo vệ output.
9. Không đổi VM flag nếu chưa kiểm tra flag có thể quản lý động và tác động của nó.
10. Ghi lại command, PID, người thực hiện và thời điểm.
11. Xóa hoặc bảo vệ output theo chính sách retention.
12. Ưu tiên chuyển script mới sang jcmd và kiểm tra lại trên JDK mục tiêu.

Quyền attach nên được cấp theo nguyên tắc least privilege. Nếu cần hỗ trợ nhiều service, hãy dùng tài khoản vận hành và quy trình phân quyền rõ ràng thay vì cấp quyền quản trị toàn máy cho mọi người.

## 17. Ghi nhớ

- jinfo lấy JVM flags và Java system properties của một Java process được chỉ định bằng PID.
- jinfo JDK 26 là công cụ experimental và unsupported; Oracle khuyến nghị dùng jcmd cho chẩn đoán mới.
- jinfo dùng cơ chế attach cục bộ; quyền truy cập phụ thuộc tài khoản và chính sách hệ điều hành.
- Với HotSpot attach tools, dùng cùng effective user ID và group ID đã khởi chạy JVM.
- -XX:+DisableAttachMechanism vô hiệu hóa attach tools như jinfo và jcmd.
- jps -l giúp tìm PID nhưng có thể không thấy JVM trong Docker process riêng.
- -flags in flags truyền lúc khởi chạy; -sysprops in system properties; -flag name đọc giá trị một flag.
- -flag +name, -flag -name và -flag name=value có thể thay đổi một số flags khi JVM đang chạy.
- Không phải mọi JVM flag đều có thể thay đổi trong lúc chạy; kiểm tra khả năng quản lý động trước khi thao tác.
- Output có thể chứa classpath, endpoint, đường dẫn và secret; cần bảo vệ như dữ liệu nội bộ.
- jcmd VM.flags và VM.system_properties là lựa chọn hiện đại để thay thế thao tác đọc phổ biến.
- Dùng jhsdb jinfo cho core dump; tránh attach jhsdb tùy tiện vào live process vì có thể làm process treo hoặc crash.
- Dùng JDK tương thích với JVM đích và kiểm tra yêu cầu riêng của Windows khi cần.

## Tài liệu tham khảo chính thức

- [The jinfo Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jinfo.html)
- [Diagnostic Tools — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The java Command — DisableAttachMechanism, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The jhsdb Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jhsdb.html)