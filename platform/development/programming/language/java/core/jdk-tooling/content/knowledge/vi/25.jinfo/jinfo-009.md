# jinfo và jcmd trong JDK

`jinfo` và `jcmd` đều có thể lấy thông tin cấu hình từ một JVM đang chạy. `jinfo` là công cụ cũ, tập trung vào VM flags và Java system properties; `jcmd` là công cụ chẩn đoán tổng quát hơn, cho phép gửi nhiều diagnostic command tới JVM như xem flags, properties, command line, heap, thread và các dữ liệu runtime khác.

Trong các JDK hiện đại, nên ưu tiên `jcmd` cho công việc mới. `jinfo` vẫn hữu ích khi cần đọc hoặc thay đổi nhanh một số VM flags trong hệ thống cũ, nhưng Oracle xếp công cụ này vào nhóm experimental/unsupported và khuyến nghị dùng `jcmd` thay thế.

## 1. jinfo dùng để làm gì?

`jinfo` tạo báo cáo cấu hình của một Java process. Thông tin thường gồm:

- Các VM flags và giá trị hiện tại, ví dụ `-Xms`, `-Xmx` hoặc các cờ `-XX`.
- Java system properties, ví dụ `java.version`, `java.class.path`, `user.dir`.
- Một số flag cụ thể theo tên.
- Khả năng bật/tắt hoặc thay đổi giá trị của một số VM flags có thể thay đổi khi JVM đang chạy.

Cú pháp cơ bản:

~~~text
jinfo <option> <pid>
~~~

`pid` là process ID của JVM đích. Có thể dùng `jps -l`, `jcmd -l` hoặc công cụ hệ điều hành để tìm process trước khi gọi `jinfo`.

`jinfo` làm việc với JVM đang chạy. Với core dump sau sự cố, dùng biến thể Serviceability Agent là `jhsdb jinfo`; không truyền file core như thể nó là PID của một process đang chạy.

## 2. Trạng thái hỗ trợ và khi nào nên dùng jcmd

`jinfo` được Oracle mô tả là công cụ experimental và unsupported. Công cụ có thể thay đổi hoặc không còn được cung cấp trong các bản JDK tương lai. Trong Oracle JDK 24 Troubleshooting Guide, Oracle khuyến nghị dùng `jcmd` thay cho công cụ `jinfo` trước đây để có chẩn đoán phong phú hơn và giảm overhead.

`jcmd` có thể:

- Liệt kê các JVM local.
- Lấy VM flags, system properties và command line.
- Xem phiên bản, uptime và thông tin JVM.
- Gửi diagnostic command có sẵn trên JVM đích.
- Thay đổi một số VM flags có thể quản lý bằng runtime.
- Chạy nhiều lệnh chẩn đoán khác ngoài phạm vi của `jinfo`.

Vì vậy:

- Dùng `jinfo` khi đang hỗ trợ một hệ thống cũ hoặc cần thao tác ngắn đã quen thuộc.
- Dùng `jcmd` cho quy trình chẩn đoán mới, script vận hành và thu thập thông tin JVM.
- Kiểm tra `jcmd <pid> help` vì danh sách command phụ thuộc JVM, phiên bản JDK và provider.

## 3. Các tùy chọn của jinfo

Kiểm tra trợ giúp:

~~~bash
jinfo -help
~~~

Trên Azul OpenJDK 24.0.2, trợ giúp hiển thị:

~~~text
Usage:
    jinfo <option> <pid>

where <option> is one of:
    -flag <name>         to print the value of the named VM flag
    -flag [+|-]<name>    to enable or disable the named VM flag
    -flag <name>=<value> to set the named VM flag to the given value
    -flags               to print VM flags
    -sysprops            to print Java system properties
    <no option>          to print both VM flags and system properties
    -? | -h | --help | -help to print this help message
~~~

Các tùy chọn chính:

| Tùy chọn | Chức năng |
|---|---|
| `-flags` | In các VM flags và giá trị hiện tại của chúng. |
| `-sysprops` | In Java system properties dưới dạng cặp tên/giá trị. |
| `-flag <name>` | Đọc giá trị của một VM flag. |
| `-flag +<name>` | Bật một boolean VM flag nếu flag đó có thể thay đổi lúc runtime. |
| `-flag -<name>` | Tắt một boolean VM flag nếu flag đó có thể thay đổi lúc runtime. |
| `-flag <name>=<value>` | Đặt giá trị mới cho VM flag có thể thay đổi lúc runtime. |
| Không có option | In cả VM flags và Java system properties. |
| `-h`, `-help`, `--help`, `-?` | Hiển thị trợ giúp. |

Ví dụ, đọc toàn bộ cấu hình:

~~~bash
jinfo 49344
~~~

Chỉ đọc flags:

~~~bash
jinfo -flags 49344
~~~

Chỉ đọc properties:

~~~bash
jinfo -sysprops 49344
~~~

Các lệnh trên là thao tác đọc. Các dạng `-flag +name`, `-flag -name` và `-flag name=value` có thể thay đổi trạng thái JVM, vì vậy cần kiểm tra flag và tác động trước khi chạy.

## 4. Đọc một VM flag cụ thể

Dùng `-flag <name>` để đọc giá trị của một flag:

~~~bash
jinfo -flag MaxHeapSize 49344
~~~

Output thực tế trên JDK 24.0.2 trong lần kiểm thử:

~~~text
-XX:MaxHeapSize=134217728
~~~

Giá trị trên tương đương 128 MiB. Flag `MaxHeapSize` thể hiện giới hạn heap tối đa của JVM trong lần chạy đó.

Một ví dụ khác:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 49344
~~~

Output khi flag đang tắt:

~~~text
-XX:-HeapDumpOnOutOfMemoryError
~~~

Quy ước output:

- `-XX:+TênFlag`: boolean flag đang bật.
- `-XX:-TênFlag`: boolean flag đang tắt.
- `-XX:TênFlag=GiáTrị`: flag có giá trị số hoặc chuỗi.

Đừng suy luận một flag có thể thay đổi chỉ vì `jinfo` đọc được nó. Khả năng đọc và khả năng thay đổi là hai việc khác nhau.

## 5. Đọc VM flags bằng -flags

Dùng:

~~~bash
jinfo -flags 49344
~~~

Output có dạng:

~~~text
VM Flags:
-XX:InitialHeapSize=33554432
-XX:MaxHeapSize=134217728
-XX:+UseCompressedOops
-XX:+UseG1GC
...
~~~

Danh sách và thứ tự flag thay đổi theo phiên bản JVM, collector, phần cứng và cấu hình khởi chạy. Một số giá trị có thể là mặc định được JVM chọn, không nhất thiết do người vận hành truyền trực tiếp trên command line.

`jinfo -flags` phù hợp khi cần xem nhanh cấu hình flags hiện tại. Nếu cần danh sách đầy đủ các flag mà VM hỗ trợ, dùng `jcmd`:

~~~bash
jcmd 49344 VM.flags -all
~~~

Lệnh `VM.flags -all` yêu cầu JVM in tất cả flags mà VM hỗ trợ. Kết quả có thể rất dài; nên lọc theo tên flag khi điều tra một giá trị cụ thể.

## 6. Đọc Java system properties bằng -sysprops

Java system properties là các cặp tên/giá trị được JVM hoặc ứng dụng sử dụng. Chúng có thể được đặt lúc khởi chạy bằng `-Dname=value` hoặc thay đổi trong chương trình bằng `System.setProperty`.

Đọc toàn bộ properties:

~~~bash
jinfo -sysprops 49344
~~~

Một phần output từ lần kiểm thử:

~~~text
app.profile=qa
app.runtime.mode=diagnostic
java.vm.name=OpenJDK 64-Bit Server VM
java.class.path=...\\out
~~~

Ví dụ, ứng dụng được khởi chạy với:

~~~bash
java -Dapp.profile=qa -cp out com.acme.JInfoDemo
~~~

sẽ có property:

~~~text
app.profile=qa
~~~

Nếu code chạy `System.setProperty("app.runtime.mode", "diagnostic")`, property runtime đó cũng xuất hiện khi đọc `jinfo -sysprops` trong lúc JVM còn chạy.

Không nhầm Java system properties với environment variables. `System.getProperty("app.profile")` đọc system property; `System.getenv("APP_PROFILE")` đọc biến môi trường. `jinfo -sysprops` không phải lệnh liệt kê toàn bộ environment variables của hệ điều hành.

## 7. In cả flags và properties

Nếu không truyền option:

~~~bash
jinfo 49344
~~~

`jinfo` in cả Java system properties và VM flags. Output thường có những phần tương tự:

~~~text
Java System Properties:
app.profile=qa
java.class.path=...
java.version=24.0.2
...

VM Flags:
-XX:InitialHeapSize=33554432
-XX:MaxHeapSize=134217728
...

jvm_args: -Xms32m -Xmx128m -Dapp.profile=qa
~~~

Đây là cách nhanh để thu thập cấu hình ban đầu khi debug. Tuy nhiên, output có thể dài và chứa thông tin nhạy cảm như classpath, username, thư mục nội bộ, system properties do ứng dụng tự đặt hoặc giá trị secret nếu ứng dụng cấu hình không an toàn.

Không gửi nguyên output vào ticket công khai hoặc log dùng chung trước khi rà soát dữ liệu nhạy cảm.

## 8. Thay đổi boolean VM flag bằng jinfo

`jinfo` có thể bật/tắt một số boolean flags khi JVM đang chạy:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 49344
~~~

Đọc lại để xác minh:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 49344
~~~

Output sau khi bật:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
~~~

Tắt lại:

~~~bash
jinfo -flag -HeapDumpOnOutOfMemoryError 49344
~~~

Đọc lại:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 49344
~~~

Output:

~~~text
-XX:-HeapDumpOnOutOfMemoryError
~~~

`HeapDumpOnOutOfMemoryError` yêu cầu JVM ghi heap dump khi gặp `OutOfMemoryError`. Bật flag này có thể giúp điều tra sự cố bộ nhớ, nhưng file heap dump có thể rất lớn và chứa dữ liệu nhạy cảm của ứng dụng.

Chỉ bật khi đã xác định vị trí lưu, dung lượng đĩa, quyền truy cập và quy trình bảo vệ file dump.

## 9. Đặt giá trị flag bằng name=value

Với một flag có thể thay đổi lúc runtime, cú pháp tổng quát là:

~~~bash
jinfo -flag FlagName=NewValue <pid>
~~~

Cú pháp này dùng cho flag có kiểu và giá trị tương ứng, chẳng hạn số hoặc chuỗi. Với boolean flag, cách dùng dấu cộng/trừ thường dễ đọc hơn:

~~~bash
jinfo -flag +HeapDumpOnOutOfMemoryError 49344
~~~

Chỉ dùng `name=value` nếu flag đó hỗ trợ cập nhật runtime và giá trị mới hợp lệ. Không phải mọi `-XX` flag đều có thể thay đổi sau khi JVM đã khởi động. Một số flag chỉ có hiệu lực trong giai đoạn khởi tạo; nếu cố thay đổi, thao tác sẽ thất bại.

Không được coi việc `jinfo` có cú pháp đặt giá trị là bằng chứng mọi flag đều có thể sửa.

## 10. Vì sao chỉ một số flag có thể thay đổi?

HotSpot phân loại một số VM flags là manageable. Các flag này được phép cập nhật trong lúc JVM đang chạy. Các flag còn lại có thể bị giới hạn ở thời điểm khởi động vì VM đã dùng chúng để cấu hình heap, collector, JIT hoặc cấu trúc nội bộ.

Ví dụ:

- `HeapDumpOnOutOfMemoryError` có thể thay đổi khi JVM chạy.
- `MaxHeapSize` là cấu hình heap tối đa được xác lập khi khởi động và không thể tùy tiện tăng bằng `jinfo`.
- Các flag khác phải kiểm tra theo tài liệu của đúng phiên bản HotSpot.

Trước khi thay đổi:

1. Đọc giá trị hiện tại bằng `jinfo -flag FlagName <pid>`.
2. Xác minh flag có hỗ trợ thay đổi runtime.
3. Xác định tác động và điều kiện áp dụng.
4. Ghi lại giá trị cũ để có thể khôi phục.
5. Thay đổi trong phạm vi có kiểm soát.
6. Đọc lại flag để xác minh.
7. Theo dõi ứng dụng sau thay đổi.

Thay đổi runtime thường chỉ tồn tại trong vòng đời JVM hiện tại. Khi process khởi động lại, giá trị có thể trở về cấu hình khởi chạy hoặc mặc định.

## 11. jcmd là gì?

`jcmd` là công cụ chẩn đoán tổng quát của JDK, dùng để gửi diagnostic command tới một JVM đang chạy.

Cú pháp:

~~~text
jcmd <pid | main-class> <command> [arguments]
~~~

Các dạng thường dùng:

~~~bash
jcmd -l
jcmd 49344 help
jcmd 49344 VM.flags
jcmd 49344 VM.system_properties
jcmd 49344 VM.command_line
~~~

- `jcmd -l` liệt kê JVM local mà công cụ có thể nhìn thấy.
- `jcmd <pid> help` liệt kê diagnostic command mà JVM đích hỗ trợ.
- `jcmd <pid> VM.flags` đọc VM flags.
- `jcmd <pid> VM.system_properties` đọc Java system properties.
- `jcmd <pid> VM.command_line` xem command line đã dùng để khởi chạy JVM.

Danh sách diagnostic command phụ thuộc phiên bản JVM và implementation. Hãy truy vấn `help` trên chính JVM đích thay vì dùng một danh sách lệnh cố định từ máy khác.

## 12. Dùng jcmd thay cho các thao tác đọc của jinfo

Các thao tác đọc phổ biến có thể chuyển sang `jcmd`:

| Nhu cầu | jinfo | jcmd |
|---|---|---|
| Liệt kê JVM local | Thường dùng `jps` để tìm PID | `jcmd -l` |
| Đọc VM flags | `jinfo -flags <pid>` | `jcmd <pid> VM.flags` |
| Đọc mọi VM flags hỗ trợ | Không có chế độ tương đương trực tiếp rõ ràng | `jcmd <pid> VM.flags -all` |
| Đọc một flag cụ thể | `jinfo -flag Name <pid>` | `jcmd <pid> VM.flags -all` rồi lọc tên |
| Đọc system properties | `jinfo -sysprops <pid>` | `jcmd <pid> VM.system_properties` |
| Xem command line lúc khởi chạy | Có trong báo cáo tổng hợp | `jcmd <pid> VM.command_line` |
| Bật/tắt một manageable boolean flag | `jinfo -flag +Name/-Name <pid>` | `jcmd <pid> VM.set_flag Name true/false` |
| Đặt giá trị manageable flag | `jinfo -flag Name=Value <pid>` | `jcmd <pid> VM.set_flag Name Value` |

Ví dụ lấy thông tin bằng jcmd:

~~~bash
jcmd 49344 VM.flags
jcmd 49344 VM.system_properties
jcmd 49344 VM.command_line
~~~

Đọc tất cả flags:

~~~bash
jcmd 49344 VM.flags -all
~~~

Cần nhớ `jinfo` không phải lệnh gọi tắt cho mọi diagnostic command. `jcmd` có nhiều command chuyên biệt cho heap, GC, threads, JFR và các thành phần VM mà `jinfo` không cung cấp.

## 13. Thay đổi VM flag bằng jcmd VM.set_flag

`jcmd` cung cấp diagnostic command `VM.set_flag` để đặt một VM flag:

~~~bash
jcmd 49344 VM.set_flag HeapDumpOnOutOfMemoryError true
~~~

Output khi thao tác thành công:

~~~text
49344:
Command executed successfully
~~~

Kiểm tra giá trị:

~~~bash
jinfo -flag HeapDumpOnOutOfMemoryError 49344
~~~

Hoặc dùng `jcmd`:

~~~bash
jcmd 49344 VM.flags
~~~

Tắt flag:

~~~bash
jcmd 49344 VM.set_flag HeapDumpOnOutOfMemoryError false
~~~

Trong thử nghiệm trên Azul OpenJDK 24.0.2, `jinfo` bật được `HeapDumpOnOutOfMemoryError` và `jcmd VM.set_flag` tắt lại được; lần đọc sau đó xác nhận flag trở về trạng thái false.

`VM.set_flag` vẫn chịu giới hạn manageable flags của HotSpot. Lệnh không cho phép thay đổi tùy ý mọi cấu hình JVM sau khi khởi động.

## 14. Ví dụ hoàn chỉnh: Java 17+ và jinfo/jcmd

Ví dụ sau tạo một JVM có system property lúc khởi chạy, sau đó đặt thêm một property khi chương trình chạy để kiểm tra cách công cụ đọc cấu hình.

Cấu trúc:

~~~text
jinfo-demo/
└── src/
    └── com/
        └── acme/
            └── JInfoDemo.java
~~~

Tệp `src/com/acme/JInfoDemo.java`:

~~~java
package com.acme;

public class JInfoDemo {
    public static void main(String[] args) throws InterruptedException {
        System.setProperty("app.runtime.mode", "diagnostic");
        System.out.println("JInfoDemo ready");
        Thread.sleep(60_000);
    }
}
~~~

### Bước 1: biên dịch

Từ thư mục gốc `jinfo-demo`:

~~~bash
javac --release 17 -d out src/com/acme/JInfoDemo.java
~~~

### Bước 2: chạy chương trình

~~~bash
java -Xms32m -Xmx128m -Dapp.profile=qa \
  -cp out com.acme.JInfoDemo --mode=inspect
~~~

Stdout chính xác:

~~~text
JInfoDemo ready
~~~

Ứng dụng giữ JVM hoạt động trong 60 giây để có thời gian kiểm tra.

### Bước 3: tìm PID

Mở terminal khác:

~~~bash
jcmd -l
~~~

Tìm dòng có tên `com.acme.JInfoDemo` và ghi lại PID tương ứng. Có thể dùng `jps -l` nếu cần.

### Bước 4: đọc cấu hình bằng jinfo

~~~bash
jinfo -flags <pid>
jinfo -sysprops <pid>
jinfo -flag MaxHeapSize <pid>
~~~

Trong system properties cần thấy:

~~~text
app.profile=qa
app.runtime.mode=diagnostic
~~~

Trong VM flags cần thấy heap tối đa tương ứng với `-Xmx128m`, tức 134217728 byte.

### Bước 5: đọc bằng jcmd

~~~bash
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> VM.command_line
~~~

Ba command tách riêng giúp xem flags, properties và command line theo từng mục đích.

### Bước 6: thay đổi một flag có thể quản lý

~~~bash
jcmd <pid> VM.set_flag HeapDumpOnOutOfMemoryError true
jinfo -flag HeapDumpOnOutOfMemoryError <pid>
~~~

Sau khi xác nhận trạng thái, có thể khôi phục:

~~~bash
jcmd <pid> VM.set_flag HeapDumpOnOutOfMemoryError false
~~~

Ví dụ không gây ra `OutOfMemoryError`, nên không tạo heap dump. Nó chỉ xác minh khả năng thay đổi flag và đọc lại trạng thái.

## 15. jinfo và jcmd cần quyền truy cập nào?

Hai công cụ cần kết nối tới JVM đích để lấy dữ liệu hoặc gửi diagnostic command. Việc attach thường phụ thuộc:

- JVM đích còn chạy và hỗ trợ cơ chế attach.
- Công cụ được chạy trên cùng máy với JVM đích.
- Tài khoản có quyền truy cập phù hợp; với `jcmd`, Oracle yêu cầu cùng effective user và group đã khởi chạy JVM.
- Chính sách bảo mật của JVM và hệ điều hành cho phép attach.
- Công cụ và target JVM tương thích về nền tảng và cách triển khai.

Nếu JVM được khởi chạy với `-XX:+DisableAttachMechanism`, các công cụ dựa trên Attach API có thể không kết nối được.

Trong container, PID namespace có thể khiến PID nhìn thấy từ host khác PID bên trong container. `jcmd -l` không liệt kê JVM nằm trong Docker process riêng; hãy xác định PID trong đúng namespace và chạy công cụ ở môi trường phù hợp.

Không nên chạy công cụ với quyền cao hơn cần thiết chỉ để vượt qua lỗi attach. Trước tiên hãy xác minh user sở hữu process, PID, namespace và chính sách bảo mật.

## 16. jhsdb jinfo và core dump

`jinfo` thông thường đọc cấu hình từ process đang chạy. Khi cần phân tích core dump sau crash, dùng `jhsdb jinfo` của Serviceability Agent.

Cú pháp tổng quát:

~~~bash
jhsdb jinfo --exe /path/to/java --core /path/to/core
~~~

- `--exe` trỏ tới Java executable tương ứng với JVM đã tạo core.
- `--core` trỏ tới core dump cần phân tích.

Binary Java và core dump phải thuộc cùng process/build tương ứng để Serviceability Agent diễn giải dữ liệu chính xác. Core dump có thể chứa dữ liệu nhạy cảm từ bộ nhớ ứng dụng; cần giới hạn quyền truy cập và dung lượng lưu trữ.

Phân tích core dump khác với attach vào process đang chạy. Nếu chỉ cần xem cấu hình runtime của ứng dụng còn hoạt động, dùng `jcmd`.

## 17. Bảo mật khi thu thập cấu hình JVM

`jinfo` và `jcmd` có thể in ra dữ liệu nội bộ:

- System properties chứa token, mật khẩu hoặc endpoint nội bộ nếu ứng dụng cấu hình không an toàn.
- Command line có thể chứa giá trị `-Dsecret=value`.
- Classpath có thể tiết lộ cấu trúc thư mục, tên thư viện và vị trí triển khai.
- Heap dump và core dump có thể chứa dữ liệu nhạy cảm ở mức bộ nhớ.

Thực hành an toàn:

- Chỉ chạy công cụ với tài khoản được phép truy cập JVM.
- Không truyền mật khẩu hoặc token trực tiếp trong JVM arguments.
- Rà soát output trước khi đính kèm vào ticket hoặc log.
- Hạn chế quyền đọc file output và core dump.
- Không lưu diagnostic artifact trong thư mục công khai.
- Ghi lại giá trị flag cũ trước khi thay đổi.
- Thay đổi một flag mỗi lần, theo dõi ứng dụng và khôi phục nếu có tác dụng phụ.

Đặc biệt, `jinfo` không có option để che hoặc lọc toàn bộ system properties. Khi chỉ cần một giá trị, hãy dùng `-flag <name>` hoặc một diagnostic command cụ thể thay vì in toàn bộ cấu hình.

## 18. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jinfo is not recognized` | JDK bin chưa có trong PATH hoặc chỉ cài runtime. | Kiểm tra `java -version` và vị trí công cụ trong JDK. |
| `AttachNotSupportedException` hoặc không attach được | JVM đã dừng, khác user, attach bị vô hiệu hóa hoặc môi trường giới hạn. | Xác minh PID, user/group, namespace và `DisableAttachMechanism`. |
| `Could not attach to process` | PID không phải JVM phù hợp hoặc process không còn chạy. | Dùng `jps -l`/`jcmd -l` để tìm lại process; xác minh bằng công cụ OS. |
| Không đọc được một VM flag | Tên flag sai hoặc flag không tồn tại trong phiên bản JVM đó. | Kiểm tra `jinfo -flags` hoặc `jcmd <pid> VM.flags -all`. |
| Đọc được flag nhưng không đặt được | Flag không thuộc nhóm có thể quản lý lúc runtime. | Xác minh manageable status; thay cấu hình khởi chạy và restart nếu cần. |
| System property không có trong output | Property chưa được đặt, tên sai hoặc đang kiểm tra nhầm JVM. | Kiểm tra PID và dùng `jcmd <pid> VM.system_properties`. |
| Giá trị flag trở lại sau restart | Thay đổi runtime không được lưu vào cấu hình khởi chạy. | Cập nhật script/service configuration nếu muốn giữ qua lần khởi động tiếp theo. |
| jcmd không có command mong đợi | Command phụ thuộc phiên bản JVM và implementation. | Chạy `jcmd <pid> help` trên target. |
| Output có dữ liệu nhạy cảm | Properties hoặc JVM arguments chứa secret. | Che giá trị trước khi chia sẻ, giới hạn quyền truy cập và chuyển secret sang secret manager. |

Không sửa security policy hoặc khởi động lại production chỉ để thử một lệnh chẩn đoán. Hãy tái hiện trên môi trường thử nghiệm khi cần xác minh một thao tác có thể thay đổi trạng thái JVM.

## 19. Quy trình chẩn đoán khuyến nghị

Khi cần điều tra cấu hình JVM:

1. Tìm JVM bằng `jcmd -l` hoặc `jps -l`.
2. Xác nhận PID, main class và user sở hữu process.
3. Chạy `jcmd <pid> help` để kiểm tra command có sẵn.
4. Lấy flags bằng `jcmd <pid> VM.flags`.
5. Lấy system properties bằng `jcmd <pid> VM.system_properties`.
6. Lấy command line bằng `jcmd <pid> VM.command_line`.
7. Chỉ dùng `VM.set_flag` với flag được phép thay đổi lúc runtime.
8. Ghi lại giá trị cũ, thay đổi có kiểm soát và xác minh lại.
9. Bảo vệ output và diagnostic artifacts.
10. Nếu cần điều tra sâu hơn, xem các command heap, thread, GC và JFR của `jcmd`.

`jinfo` có thể dùng để đọc hoặc điều chỉnh một số cấu hình trong hệ thống cũ. Với workflow mới, `jcmd` là công cụ phù hợp hơn vì có command discovery, đầu ra phân tách theo mục đích và nhiều khả năng chẩn đoán hơn.

## 20. Tài liệu tham khảo

- Oracle JDK 24 — [Troubleshooting Guide: The jinfo Utility](https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf) — phần The jinfo Utility và Troubleshooting with the jinfo Utility.
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html).
- Oracle JDK 24 — [Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html).

