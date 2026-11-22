# Cách đọc output jinfo trong Java

jinfo là công cụ dòng lệnh trong JDK dùng để xem cấu hình của một tiến trình Java đang chạy. Output của nó tập trung vào hai nhóm dữ liệu: Java system properties và các JVM command-line flags. Khi biết cách đọc hai nhóm này, bạn có thể xác định JVM đang chạy phiên bản nào, ứng dụng đang dùng classpath nào, những tùy chọn heap/GC nào đang có hiệu lực và các property nào đã được truyền vào ứng dụng.

Bài này sử dụng JDK 17 trở lên. Trọng tâm là hiểu ý nghĩa từng phần của output, phân biệt property với VM flag, đọc giá trị Boolean và số, tìm thông tin hữu ích khi xử lý sự cố và biết khi nào nên dùng jcmd thay cho jinfo.

> **Lưu ý về công cụ:** Oracle đánh dấu jinfo là experimental và unsupported; công cụ có thể thay đổi hoặc không còn có trong các bản JDK tương lai. Với chẩn đoán mới, Oracle khuyến nghị dùng jcmd.

## 1. jinfo thu thập những thông tin gì?

Cú pháp cơ bản:

~~~text
jinfo [option] pid
~~~

pid là process ID của JVM cần kiểm tra. Tiến trình đích phải là một tiến trình Java mà công cụ có thể attach vào.

Nếu không truyền option, jinfo in cả hai nhóm:

- **Java System Properties:** các cặp tên và giá trị cấu hình có thể đọc trong ứng dụng bằng System.getProperty(...).
- **VM Flags:** các tùy chọn cấu hình của Java Virtual Machine, thường có dạng -XX:Name=value, -XX:+Name hoặc -XX:-Name.

Các lệnh đọc riêng từng nhóm:

~~~powershell
jinfo -sysprops 12345
jinfo -flags 12345
~~~

Đọc một VM flag:

~~~powershell
jinfo -flag MaxHeapSize 12345
jinfo -flag UseG1GC 12345
~~~

Xem trợ giúp:

~~~powershell
jinfo -help
~~~

12345 chỉ là PID minh họa. Thay bằng PID thực tế của ứng dụng trên máy đang chẩn đoán.

## 2. Tìm đúng PID trước khi đọc output

Có thể liệt kê các JVM mà JDK nhận diện bằng jps:

~~~powershell
jps -l
~~~

Ví dụ output:

~~~text
8120 com.example.JInfoTarget
9204 org.apache.catalina.startup.Bootstrap
10440 jdk.jcmd/sun.tools.jps.Jps
~~~

Trong ví dụ, PID 8120 thuộc ứng dụng com.example.JInfoTarget. Có thể kiểm tra bằng:

~~~powershell
jinfo 8120
~~~

Nếu JVM chạy trong Docker/container riêng, jps trên host có thể không liệt kê tiến trình đó. Hãy tìm PID trong đúng namespace, ví dụ dùng ps bên trong container hoặc công cụ quản trị container.

Đảm bảo đang dùng công cụ JDK tương thích với JVM đích và tài khoản có quyền attach. Thông thường, thao tác attach cần được thực hiện trên cùng máy và với quyền người dùng phù hợp với tiến trình đích. Cấu hình bảo mật, runtime hoặc môi trường container có thể hạn chế attach.

## 3. Đọc output mặc định: hai phần chính

Lệnh:

~~~powershell
jinfo 8120
~~~

Output rút gọn minh họa:

~~~text
Attaching to process ID 8120, please wait...
Debugger attached successfully.
Server compiler detected.
JVM version is 17.0.x

Java System Properties:
    java.specification.version=17
    java.version=17.0.x
    java.home=C:\Java\jdk-17
    java.class.path=C:\apps\demo\app.jar
    user.dir=C:\apps\demo
    user.name=service-user
    os.name=Windows 11
    file.encoding=UTF-8
    app.profile=staging
    app.timeoutSeconds=30
    sun.java.command=com.example.JInfoTarget

VM Flags:
    -XX:InitialHeapSize=134217728
    -XX:MaxHeapSize=536870912
    -XX:+UseG1GC
~~~

Đây là output minh họa đã rút gọn để giải thích cách đọc. Phiên bản JDK, hệ điều hành, cấu hình khởi chạy và các flag mặc định có thể làm output thực tế khác đi.

Có thể đọc theo thứ tự:

1. Các dòng attach cho biết công cụ đang kết nối tới PID nào và có nhận diện được JVM hay không.
2. Dòng phiên bản cho biết runtime của tiến trình đích.
3. Phần Java System Properties cho biết các property và giá trị hiện có.
4. Phần VM Flags cho biết các tùy chọn cấu hình JVM mà công cụ hiển thị.

Nếu cần điều tra một cấu hình cụ thể, hãy dùng -sysprops, -flags hoặc -flag name để thu hẹp output.

## 4. Đọc phần Java System Properties

System property có dạng:

~~~text
property.name=value
~~~

Ví dụ:

~~~text
java.version=17.0.x
java.home=C:\Java\jdk-17
java.class.path=C:\apps\demo\app.jar
user.dir=C:\apps\demo
app.profile=staging
app.timeoutSeconds=30
~~~

Các property thường được đọc trong Java bằng:

~~~java
String version = System.getProperty("java.version");
String profile = System.getProperty("app.profile");
~~~

Có thể chia property thành một số nhóm.

### 4.1. Thông tin phiên bản và runtime

| Property | Ý nghĩa |
|---|---|
| java.version | Phiên bản Java runtime |
| java.version.date | Ngày phát hành bản runtime, nếu có |
| java.runtime.version | Phiên bản đầy đủ của runtime |
| java.runtime.name | Tên runtime |
| java.vm.name | Tên Java Virtual Machine |
| java.vm.version | Phiên bản VM |
| java.vm.vendor | Nhà cung cấp VM |
| java.specification.version | Phiên bản Java SE specification mà runtime hỗ trợ |
| java.home | Thư mục cài đặt runtime/JDK được JVM sử dụng |

Nhóm này giúp xác nhận ứng dụng đang chạy bằng đúng JDK mong đợi hay chưa. Đặc biệt, java.home cho biết runtime mà tiến trình thực sự nạp; nó có thể khác JDK được chọn trong terminal hiện tại.

### 4.2. Classpath và thư mục chạy

| Property | Ý nghĩa |
|---|---|
| java.class.path | Classpath mà ứng dụng sử dụng |
| user.dir | Thư mục làm việc hiện tại của tiến trình |
| java.library.path | Các thư mục được tìm kiếm khi nạp native library |
| sun.java.command | Tên class chính hoặc lệnh/JAR dùng để khởi chạy ứng dụng |

Khi gặp lỗi ClassNotFoundException hoặc NoClassDefFoundError, hãy kiểm tra java.class.path và sun.java.command. Nếu đường dẫn JAR hoặc thư mục class bị thiếu, ứng dụng có thể đang chạy với classpath khác dự kiến.

java.library.path hữu ích khi điều tra lỗi nạp thư viện native như lỗi tìm thấy DLL hoặc shared library. Giá trị này là danh sách đường dẫn; dấu phân cách thường khác nhau giữa Windows và Unix-like systems.

### 4.3. Thông tin user và hệ điều hành

| Property | Ý nghĩa |
|---|---|
| user.name | Tên user mà JVM nhìn thấy |
| user.home | Thư mục home của user |
| os.name | Tên hệ điều hành |
| os.version | Phiên bản hệ điều hành |
| os.arch | Kiến trúc hệ điều hành |
| file.encoding | Charset mặc định được runtime sử dụng cho một số API |
| file.separator | Ký tự phân cách thư mục |
| path.separator | Ký tự phân cách các phần tử trong path list |
| line.separator | Ký tự xuống dòng của nền tảng |

Các property này hữu ích khi ứng dụng hoạt động khác nhau giữa máy phát triển, máy kiểm thử và production. Ví dụ, user.dir có thể giải thích vì sao một đường dẫn tương đối tìm thấy file ở local nhưng thất bại khi chạy như service.

### 4.4. Property do ứng dụng tự đặt

Các property bắt đầu bằng tên riêng của ứng dụng thường đến từ tham số -D hoặc lệnh System.setProperty(...).

Ví dụ khởi chạy:

~~~powershell
java -Dapp.profile=staging -Dapp.timeoutSeconds=30 -jar app.jar
~~~

Ứng dụng đọc chúng:

~~~java
String profile = System.getProperty("app.profile", "local");
int timeout = Integer.parseInt(
    System.getProperty("app.timeoutSeconds", "10")
);
~~~

Trong output, bạn có thể thấy:

~~~text
app.profile=staging
app.timeoutSeconds=30
~~~

Đây là bằng chứng property đang hiện diện trong JVM tại thời điểm kiểm tra. Nếu property không xuất hiện, hãy kiểm tra cách khởi chạy, code cấu hình và thời điểm ứng dụng đặt property.

### 4.5. Cẩn trọng khi đọc giá trị property

- Một số giá trị có thể rất dài, ví dụ java.class.path hoặc java.library.path.
- Đường dẫn Windows có thể xuất hiện với dấu gạch chéo ngược hoặc ký tự escape.
- Property tùy chỉnh có thể chứa dấu bằng, dấu cách hoặc danh sách phân tách.
- Property sun.* và một số property jdk.* có thể là chi tiết triển khai; không nên xem chúng là API ổn định cho logic ứng dụng.
- jinfo -sysprops không liệt kê toàn bộ environment variables của hệ điều hành.
- Không phải mọi cấu hình của ứng dụng đều là system property; ứng dụng có thể đọc từ file, database, secret manager hoặc cấu hình riêng.

## 5. Đọc phần VM Flags

VM flag là tùy chọn cấu hình JVM. Nhiều flag HotSpot có tiền tố -XX:. Output thường gặp:

~~~text
VM Flags:
    -XX:InitialHeapSize=134217728
    -XX:MaxHeapSize=536870912
    -XX:+UseG1GC
~~~

Cách đọc:

| Output | Ý nghĩa |
|---|---|
| -XX:+UseG1GC | Flag Boolean đang bật |
| -XX:-UseG1GC | Flag Boolean đang tắt |
| -XX:MaxHeapSize=536870912 | Flag dạng số có giá trị 536.870.912 byte |
| -XX:InitialHeapSize=134217728 | Initial heap size là 134.217.728 byte |

Các flag thể hiện cấu hình của VM. Một số giá trị đến từ tham số người vận hành truyền khi chạy java; một số giá trị được JVM chọn dựa trên cấu hình máy và cơ chế ergonomics. Vì vậy, output không nhất thiết chỉ lặp lại nguyên văn command line ban đầu.

### 5.1. Boolean flag: dấu cộng và dấu trừ

Với Boolean flag:

- -XX:+TênFlag nghĩa là bật.
- -XX:-TênFlag nghĩa là tắt.

Ví dụ:

~~~text
-XX:+UseG1GC
-XX:-UseBiasedLocking
~~~

Dòng đầu cho biết UseG1GC đang bật. Dòng thứ hai cho biết UseBiasedLocking đang tắt. Flag cụ thể có thể khác giữa các phiên bản JDK; không suy luận rằng một flag tồn tại hoặc có cùng ý nghĩa ở mọi phiên bản.

### 5.2. Flag dạng số và kích thước bộ nhớ

Flag dạng số thường có dạng:

~~~text
-XX:MaxHeapSize=536870912
~~~

Một số giá trị bộ nhớ được biểu diễn bằng byte. Để đổi sang MiB:

\[
\text{MiB} = \frac{\text{bytes}}{1024 \times 1024}
\]

Ví dụ:

- 536870912 byte = 512 MiB.
- 134217728 byte = 128 MiB.

Trong Java launcher, -Xmx512m thường tương ứng với giới hạn heap tối đa 512 MiB, còn -Xms128m đặt heap ban đầu 128 MiB. Trong VM flags, các giá trị có thể xuất hiện dưới tên nội bộ như MaxHeapSize và InitialHeapSize.

Không nhầm heap với tổng bộ nhớ process. Heap chỉ là một phần bộ nhớ JVM; metaspace, code cache, thread stack, direct buffer và native memory cũng sử dụng RAM.

## 6. Dùng -flags để đọc danh sách VM flag

Lệnh:

~~~powershell
jinfo -flags 8120
~~~

Chỉ in phần VM flags thay vì toàn bộ system properties.

Output rút gọn minh họa:

~~~text
VM Flags:
-XX:InitialHeapSize=134217728 -XX:MaxHeapSize=536870912 -XX:+UseG1GC
~~~

Dùng lệnh này khi cần kiểm tra cấu hình JVM tổng quát, ví dụ:

- Heap ban đầu và heap tối đa.
- Garbage collector được cấu hình.
- Các tùy chọn JVM đã được truyền khi khởi chạy.
- Những flag cần đối chiếu với cấu hình deployment.

Danh sách có thể dài và phụ thuộc phiên bản VM. Một số giá trị có thể là giá trị mặc định/ergonomic do JVM chọn. Để hiểu nguồn gốc của một flag hoặc liệu nó có thể thay đổi runtime hay không, cần xem tài liệu của đúng phiên bản JDK và loại VM.

## 7. Dùng -sysprops để đọc riêng property

Lệnh:

~~~powershell
jinfo -sysprops 8120
~~~

Output có dạng nhiều dòng tên=giá trị:

~~~text
Java System Properties:
    java.version=17.0.x
    java.home=C:\Java\jdk-17
    java.class.path=C:\apps\demo\app.jar
    user.dir=C:\apps\demo
    app.profile=staging
    app.timeoutSeconds=30
~~~

Đây là lệnh phù hợp khi bạn đang điều tra:

- JVM đang dùng phiên bản JDK nào.
- Ứng dụng được chạy từ thư mục nào.
- Classpath có chứa JAR mong đợi hay không.
- Profile hoặc property tùy chỉnh đã được nạp chưa.
- Encoding, kiến trúc và thông tin môi trường có khác giữa các máy hay không.

Nếu cần kiểm tra một property bằng code, có thể gọi System.getProperty("app.profile") trong ứng dụng. jinfo cung cấp góc nhìn từ tiến trình đang chạy mà không cần sửa source code.

## 8. Dùng -flag để đọc một VM flag

Cú pháp:

~~~text
jinfo -flag flagName pid
~~~

Ví dụ đọc heap tối đa và GC:

~~~powershell
jinfo -flag MaxHeapSize 8120
jinfo -flag UseG1GC 8120
~~~

Output minh họa:

~~~text
-XX:MaxHeapSize=536870912
-XX:+UseG1GC
~~~

Kết quả cho biết một flag cụ thể, dễ đọc hơn danh sách dài từ -flags.

Nếu flag không tồn tại trong VM đang chạy, hoặc tên flag không đúng, công cụ sẽ báo lỗi. Tên flag cần đối chiếu với phiên bản JDK đang chạy.

## 9. Phân biệt đọc flag và thay đổi flag

Option -flag có cả dạng đọc và dạng thay đổi:

| Cú pháp | Tác dụng |
|---|---|
| jinfo -flag MaxHeapSize pid | Đọc giá trị flag |
| jinfo -flag +FlagName pid | Yêu cầu bật Boolean flag |
| jinfo -flag -FlagName pid | Yêu cầu tắt Boolean flag |
| jinfo -flag FlagName=value pid | Yêu cầu đặt flag bằng giá trị mới |

Hai dạng có dấu + hoặc - hay có =value là thao tác thay đổi trạng thái JVM. Chúng không phải lệnh đọc output. Chỉ một số flag cho phép thay đổi khi JVM đang chạy; VM có thể từ chối flag không writable hoặc giá trị không hợp lệ.

Trước khi thay đổi flag:

1. Xác nhận đúng PID và đúng ứng dụng.
2. Kiểm tra tài liệu của flag trên đúng phiên bản JDK.
3. Đánh giá ảnh hưởng tới heap, GC, hiệu năng và tính ổn định.
4. Thực hiện theo quy trình vận hành đã được phê duyệt.
5. Đọc lại flag để xác nhận giá trị mới nếu thao tác thành công.

Không thử thay đổi flag trên production chỉ để kiểm tra cú pháp. Việc thay đổi cấu hình JVM có thể tác động trực tiếp tới ứng dụng đang chạy.

## 10. Ví dụ thực hành: tạo JVM để đọc output jinfo

Tạo file JInfoTarget.java:

~~~java
import java.util.concurrent.CountDownLatch;

public class JInfoTarget {
    public static void main(String[] args) throws InterruptedException {
        System.setProperty("app.profile", "staging");
        System.setProperty("app.timeoutSeconds", "30");

        System.out.println("Target JVM is ready.");
        new CountDownLatch(1).await();
    }
}
~~~

Chương trình đặt hai system properties để dễ nhận diện trong output, sau đó giữ JVM chạy để bạn có thể attach từ terminal thứ hai.

Biên dịch:

~~~powershell
javac JInfoTarget.java
~~~

Khởi chạy với các tùy chọn JVM:

~~~powershell
java -Xms128m -Xmx512m -XX:+UseG1GC -Dapp.profile=staging -Dapp.timeoutSeconds=30 JInfoTarget
~~~

Stdout:

~~~text
Target JVM is ready.
~~~

Giữ terminal này mở. Mở terminal thứ hai tại cùng máy và tìm PID:

~~~powershell
jps -l
~~~

Tìm dòng có JInfoTarget, sau đó thay <PID> trong các lệnh sau bằng số PID thực tế:

~~~powershell
jinfo <PID>
jinfo -sysprops <PID>
jinfo -flags <PID>
jinfo -flag MaxHeapSize <PID>
jinfo -flag UseG1GC <PID>
~~~

Trong -sysprops, tìm:

~~~text
app.profile=staging
app.timeoutSeconds=30
~~~

Trong -flags, tìm các giá trị tương ứng với:

~~~text
-XX:InitialHeapSize=134217728
-XX:MaxHeapSize=536870912
-XX:+UseG1GC
~~~

Các giá trị flag thực tế có thể được JVM chuẩn hóa hoặc hiển thị thêm flag mặc định. Hãy xem đây là kết quả đại diện để nhận biết dạng dữ liệu. Khi hoàn tất, quay lại terminal đầu tiên và nhấn Ctrl+C để dừng chương trình.

## 11. Dùng output jinfo để xử lý sự cố

### 11.1. Ứng dụng dùng sai JDK

Kiểm tra:

~~~text
java.version
java.runtime.version
java.home
java.vm.name
~~~

Nếu java.home trỏ tới runtime khác với JDK dự kiến, kiểm tra service wrapper, script khởi chạy, JAVA_HOME và PATH của môi trường chạy ứng dụng. PATH trong terminal của bạn không nhất thiết giống PATH của service.

### 11.2. Lỗi không tìm thấy class

Kiểm tra:

~~~text
java.class.path
sun.java.command
user.dir
~~~

Đối chiếu đường dẫn JAR, thư mục class, working directory và lệnh khởi chạy. Classpath có thể khác giữa IDE và service vì mỗi môi trường có cách tạo command line riêng.

### 11.3. Heap không đúng cấu hình

Kiểm tra:

~~~text
-XX:InitialHeapSize=...
-XX:MaxHeapSize=...
~~~

Đổi số byte sang MiB để so với -Xms và -Xmx. Nếu giá trị không đúng dự kiến, kiểm tra tham số thực tế của service, biến cấu hình, script khởi chạy và các giá trị JVM tự chọn.

Không dùng riêng MaxHeapSize để kết luận process đang thiếu RAM. Muốn đánh giá heap usage, GC pause hoặc native memory, dùng công cụ chẩn đoán chuyên biệt như jcmd, JFR hoặc JDK Mission Control.

### 11.4. Garbage collector khác dự kiến

Kiểm tra flag Boolean tương ứng, ví dụ:

~~~powershell
jinfo -flag UseG1GC <PID>
~~~

Kết quả -XX:+UseG1GC cho biết flag bật; -XX:-UseG1GC cho biết flag tắt. GC thực tế còn phụ thuộc phiên bản VM và các tùy chọn khác. Đọc tài liệu GC của đúng JDK trước khi thay đổi cấu hình.

### 11.5. Property tùy chỉnh bị thiếu

Kiểm tra bằng:

~~~powershell
jinfo -sysprops <PID>
~~~

Nếu property không xuất hiện, kiểm tra tham số -D, cấu hình service và code gọi System.setProperty. Nếu ứng dụng nạp cấu hình từ file hoặc secret manager, giá trị đó có thể không xuất hiện trong system properties.

## 12. Những gì jinfo không cho biết

jinfo là ảnh chụp cấu hình tại thời điểm chạy lệnh. Nó không phải công cụ profiling hoặc monitoring toàn diện.

Nó không trực tiếp cho biết:

- Heap đang dùng bao nhiêu byte tại thời điểm hiện tại.
- GC pause kéo dài bao lâu hoặc tần suất GC.
- Thread nào đang block hoặc deadlock.
- Method nào tiêu thụ CPU.
- Số lượng object và phân bố bộ nhớ.
- Toàn bộ environment variables của hệ điều hành.
- Nội dung cấu hình nằm trong file, database hoặc secret manager nếu ứng dụng không đưa chúng vào system properties.

Chọn công cụ theo câu hỏi:

| Cần biết | Công cụ phù hợp |
|---|---|
| System properties và VM flags | jinfo hoặc jcmd |
| Lệnh khởi chạy JVM | jcmd <PID> VM.command_line |
| Thread dump | jcmd <PID> Thread.print |
| Heap summary | jcmd <PID> GC.heap_info |
| Flight Recording | jcmd <PID> JFR.start và JFR.dump |
| Phân tích recording | JDK Mission Control hoặc jfr |

## 13. Dùng jcmd thay cho jinfo trong JDK 17

Oracle khuyến nghị jcmd cho chẩn đoán JVM mới. Các lệnh tương ứng:

~~~powershell
jcmd <PID> VM.system_properties
jcmd <PID> VM.flags
jcmd <PID> VM.command_line
~~~

Ý nghĩa:

- VM.system_properties: in system properties.
- VM.flags: in VM flags và giá trị hiện tại.
- VM.command_line: in command line đã dùng để khởi chạy JVM.

Xem các diagnostic command mà JVM hỗ trợ:

~~~powershell
jcmd <PID> help
~~~

Có thể hỏi trợ giúp riêng cho một command:

~~~powershell
jcmd <PID> help VM.flags
~~~

Các command khả dụng phụ thuộc JVM và phiên bản. jcmd cần chạy trên cùng máy và với effective user/group phù hợp với tiến trình JVM. Khi cần chẩn đoán sâu, jcmd còn cung cấp các command về thread, heap và Flight Recorder.

## 14. Lỗi thường gặp khi đọc output jinfo

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| jinfo is not recognized | JDK bin chưa nằm trong PATH hoặc máy chỉ có JRE/runtime | Cài JDK phù hợp hoặc gọi jinfo bằng đường dẫn đầy đủ |
| Unable to open socket file hoặc attach thất bại | Sai PID, sai user, attach bị hạn chế hoặc JVM không còn chạy | Xác minh PID, user, host và trạng thái tiến trình |
| Không tìm thấy PID bằng jps | JVM chạy trong container namespace khác hoặc không được liệt kê | Dùng ps trong đúng môi trường hoặc kiểm tra PID namespace |
| Output thiếu system property mong đợi | Property chưa được đặt hoặc ứng dụng dùng nguồn cấu hình khác | Kiểm tra tham số -D, code cấu hình và System.setProperty |
| Flag không được nhận diện | Tên flag sai hoặc flag không có trong phiên bản VM | Dùng đúng tên và tra tài liệu đúng JDK |
| Không thể thay đổi flag | Flag không writable khi runtime hoặc giá trị vi phạm ràng buộc | Kiểm tra loại flag, khả năng thay đổi và giá trị hợp lệ |
| Công cụ lỗi trên Windows | Thiếu thành phần debugging hoặc không tìm thấy jvm.dll | Kiểm tra yêu cầu Windows Debugging Tools và PATH theo tài liệu Oracle |
| Giá trị heap khó hiểu | Giá trị được in bằng byte | Chia cho 1.048.576 để đổi sang MiB |

Nếu jinfo không hoạt động hoặc không có trong JDK đang dùng, thử jcmd với các command tương ứng. Với crash dump, dùng jhsdb jinfo và cung cấp đúng executable cùng core file theo tài liệu Serviceability Agent của JDK.

## 15. Bảo vệ output khi chia sẻ

System properties và VM flags có thể tiết lộ thông tin môi trường:

- user.name, user.home, user.dir tiết lộ tên tài khoản và đường dẫn nội bộ.
- java.class.path và java.library.path có thể chứa tên dự án, thư mục hoặc vị trí artifact.
- sun.java.command có thể cho biết class chính và tham số khởi chạy.
- Property tùy chỉnh có thể chứa endpoint, token hoặc dữ liệu nhạy cảm nếu ứng dụng thiết kế không an toàn.

Trước khi gửi output cho đồng nghiệp, đưa vào ticket hoặc đăng lên diễn đàn, hãy rà soát và che thông tin nhạy cảm. Không chia sẻ toàn bộ output mặc định nếu chỉ cần một flag hoặc một property; hãy dùng -flag, -flags hoặc -sysprops để thu hẹp phần cần xem.

Không coi output của jinfo là định dạng lưu trữ cấu hình ổn định hoặc API để parser phụ thuộc lâu dài. Hình thức và các flag có thể thay đổi theo JDK, VM, hệ điều hành và cấu hình triển khai.

## 16. Checklist đọc output jinfo

- [ ] Đã xác định đúng PID của JVM cần kiểm tra.
- [ ] Đang dùng JDK tool tương thích và có quyền attach.
- [ ] Đã đọc phiên bản JVM và java.home.
- [ ] Đã kiểm tra java.class.path, sun.java.command và user.dir khi điều tra lỗi class/file.
- [ ] Đã phân biệt system properties với VM flags.
- [ ] Đã hiểu dấu + hoặc - của Boolean flag.
- [ ] Đã đổi giá trị byte sang MiB khi kiểm tra heap.
- [ ] Không nhầm giá trị flag với heap usage hoặc số liệu runtime.
- [ ] Không xem environment variables là system properties.
- [ ] Đã che thông tin nhạy cảm trước khi chia sẻ output.
- [ ] Đã cân nhắc jcmd cho chẩn đoán mới.

Khi đọc output jinfo, hãy bắt đầu bằng PID và phiên bản JVM, sau đó tách phần Java System Properties khỏi VM Flags. Properties giúp xác định runtime, classpath, working directory và cấu hình ứng dụng; VM flags cho biết tùy chọn JVM như heap và garbage collector. Dùng -sysprops, -flags và -flag để tập trung vào dữ liệu cần kiểm tra, đồng thời nhớ rằng jinfo là công cụ experimental/unsupported và jcmd là lựa chọn được Oracle khuyến nghị cho chẩn đoán hiện nay.

## Tài liệu tham khảo

- Oracle, The jinfo Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jinfo.html
- Oracle, The jcmd Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, Diagnostic Tools, Java SE 21 — The jinfo Utility: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle, The java Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
