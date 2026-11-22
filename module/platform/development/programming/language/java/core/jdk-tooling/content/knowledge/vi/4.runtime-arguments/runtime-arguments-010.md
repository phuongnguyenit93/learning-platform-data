# Kiểm tra tham số runtime Java thực tế

## Mục tiêu

Sau bài này, bạn có thể phân biệt tham số của Java launcher, JVM và ứng dụng; tìm các nguồn đã thêm tham số khi khởi động; kiểm tra cấu hình của một tiến trình Java đang chạy bằng jcmd; đọc system properties và VM flags từ bên trong ứng dụng; và xác định vì sao giá trị thực tế khác với cấu hình bạn nghĩ đã truyền vào.

## 1. “Tham số runtime thực tế” là gì?

Khi một ứng dụng Java chạy, có nhiều nhóm tham số cùng ảnh hưởng đến cách chương trình hoạt động. Không phải tất cả đều là một loại “JVM argument”.

| Nhóm | Ví dụ | Nơi được xử lý |
|---|---|---|
| Java launcher options | -cp, --module-path, -jar, --add-modules | Java launcher |
| JVM options / VM flags | -Xms, -Xmx, -Xss, -XX:+UseG1GC | JVM implementation |
| System properties | -Dapp.mode=prod, -Duser.timezone=UTC | Java runtime, đọc bằng System.getProperty |
| Environment variables | JAVA_TOOL_OPTIONS, JDK_JAVA_OPTIONS, CLASSPATH | Shell, launcher hoặc JVM tùy biến |
| Application arguments | --mode prod, input.csv | main method hoặc bộ phân tích tham số của ứng dụng |
| Application configuration | application.yml, config.properties, command-line options của framework | Chính ứng dụng hoặc framework |

Một ví dụ:

~~~bash
java -Xms256m -Xmx1g -Dapp.mode=prod -cp app.jar com.example.Main --port 8080
~~~

Trong lệnh này:

- -Xms256m và -Xmx1g cấu hình heap ban đầu và heap tối đa.
- -Dapp.mode=prod đặt system property tên app.mode.
- -cp app.jar cấu hình classpath cho launcher.
- com.example.Main là main class.
- --port 8080 là hai đối số ứng dụng, được truyền vào main(String[] args).

Vì thế, khi kiểm tra tham số, trước hết phải xác định bạn muốn biết **lệnh khởi chạy**, **VM flags hiện đang có hiệu lực**, **system properties hiện tại**, hay **đối số mà ứng dụng nhận được**. Một lệnh kiểm tra đơn lẻ không trả lời đầy đủ cả bốn câu hỏi.

## 2. Giá trị được khai báo và giá trị đang có hiệu lực

Có ba loại thông tin thường bị nhầm lẫn:

1. **Cấu hình dự định:** tham số ghi trong script, Dockerfile, service unit, IDE hoặc file cấu hình.
2. **Tham số lúc khởi chạy:** những tùy chọn launcher/JVM thực sự được cung cấp khi tiến trình bắt đầu.
3. **Trạng thái runtime hiện tại:** giá trị JVM đang sử dụng hoặc system property sau khi ứng dụng có thể đã thay đổi nó.

Ví dụ, file chạy ứng dụng có thể ghi -Xmx2g nhưng service đang chạy lại được khởi động bởi một script khác với -Xmx1g. Hoặc JVM khởi động với -Dapp.mode=dev nhưng mã ứng dụng gọi System.setProperty("app.mode", "prod") sau đó. Khi đó giá trị hiện tại của system property là prod, dù tham số khởi động ban đầu là dev.

Để xác minh, hãy đối chiếu nguồn cấu hình với tiến trình đang chạy. Khi cần biết giới hạn heap hiện tại, đọc VM flags của đúng PID. Khi cần biết property mà code đang đọc, đọc System.getProperty hoặc VM.system_properties. Khi cần biết đối số ứng dụng, kiểm tra args hoặc log ứng dụng.

## 3. Những nơi tham số có thể được thêm vào

### 3.1. Command line của java

Các tham số có thể được viết trực tiếp trong lệnh khởi chạy:

~~~bash
java -Xms256m -Xmx1g -Dapp.mode=prod -jar app.jar --port 8080
~~~

Thứ tự rất quan trọng: tùy chọn JVM và launcher đứng trước mục tiêu chạy; đối số ứng dụng đứng sau class, JAR, module hoặc source file.

### 3.2. JDK_JAVA_OPTIONS

JDK_JAVA_OPTIONS là biến môi trường được Java launcher đọc. Nội dung của biến được thêm vào trước các tùy chọn được truyền trực tiếp trong command line của java.

Ví dụ trên Linux/macOS:

~~~bash
export JDK_JAVA_OPTIONS="-Xms256m -Dapp.mode=staging"
java -Xmx1g -jar app.jar
~~~

Launcher xử lý như thể các tùy chọn từ biến môi trường được đặt trước các tùy chọn trực tiếp. Khi biến này được đặt, launcher in một thông báo nhắc trên stderr.

Kiểm tra biến:

~~~bash
echo "$JDK_JAVA_OPTIONS"
~~~

Trên Windows PowerShell:

~~~powershell
$env:JDK_JAVA_OPTIONS
~~~

### 3.3. JAVA_TOOL_OPTIONS

JAVA_TOOL_OPTIONS được xử lý khi JVM được tạo thông qua JNI Invocation API. Nó hữu ích khi command line khởi chạy khó truy cập, chẳng hạn ứng dụng nhúng JVM hoặc tiến trình được khởi tạo qua nhiều lớp script.

Ví dụ:

~~~bash
export JAVA_TOOL_OPTIONS="-Dapp.region=ap-southeast-1 -Xmx1g"
~~~

Biến này bổ sung tùy chọn cho JVM ở thời điểm khởi tạo. Nó không thay thế các tùy chọn do Java launcher xử lý như chọn class, -jar hoặc classpath. Trong một số môi trường, JAVA_TOOL_OPTIONS có thể bị vô hiệu hóa vì lý do bảo mật.

Kiểm tra biến:

~~~bash
echo "$JAVA_TOOL_OPTIONS"
~~~

Trên Windows PowerShell:

~~~powershell
$env:JAVA_TOOL_OPTIONS
~~~

### 3.4. File tham số @argfile

Khi command line dài, Java launcher cho phép đặt các tùy chọn vào file rồi truyền tên file có tiền tố @.

Ví dụ file jvm.args:

~~~text
-Xms256m
-Xmx1g
-Dapp.mode=prod
-Duser.timezone=UTC
~~~

Khởi chạy:

~~~bash
java @jvm.args -jar app.jar
~~~

Các tùy chọn trong file được launcher mở rộng trước khi xử lý command line. Vì vậy, khi script chỉ có dòng java @jvm.args, cần đọc cả file jvm.args để biết tham số thực sự.

Đường dẫn tương đối trong argument file được tính từ thư mục làm việc hiện tại của tiến trình, không phải thư mục chứa argument file.

### 3.5. Script, service và build tool

Tham số còn có thể nằm trong:

- Script .bat, .cmd, .ps1 hoặc shell script.
- Dockerfile, docker-compose hoặc cấu hình Kubernetes.
- Windows Service, systemd unit hoặc service manager khác.
- Cấu hình chạy của IDE.
- Cấu hình Gradle/Maven và các plugin chạy ứng dụng.
- File cấu hình riêng của framework.

Các biến như JAVA_OPTS, MAVEN_OPTS hoặc GRADLE_OPTS thường được script/build tool sử dụng theo quy ước riêng. Chúng không phải một bộ biến môi trường chuẩn chung cho mọi Java launcher. Hãy đọc script hoặc tài liệu của công cụ tạo tiến trình.

Đặc biệt, JVM chạy Gradle daemon có thể khác JVM chạy ứng dụng. Khi ứng dụng được chạy bằng Gradle task, hãy tìm đúng PID của tiến trình ứng dụng thay vì chỉ kiểm tra daemon của Gradle.

## 4. Tìm tiến trình Java cần kiểm tra

Trước khi đọc tham số, phải xác định đúng PID. Một máy có thể chạy nhiều JVM cùng lúc: ứng dụng, Gradle daemon, Maven, IDE, server và các công cụ Java khác.

### Dùng jcmd

Lệnh sau liệt kê các JVM mà công cụ có thể nhận diện:

~~~bash
jcmd -l
~~~

Ví dụ kết quả minh họa:

~~~text
18420 com.example.OrderApplication
19210 org.gradle.launcher.daemon.bootstrap.GradleDaemon
~~~

Chọn PID của ứng dụng cần kiểm tra. Không nhầm PID của Gradle daemon hoặc IDE với PID của tiến trình ứng dụng.

Có thể dùng lệnh jcmd không có đối số thay cho jcmd -l.

### Dùng jps

JDK cũng có công cụ jps:

~~~bash
jps -lmv
~~~

Các tùy chọn:

| Tùy chọn | Thông tin |
|---|---|
| -l | Tên đầy đủ của main class hoặc đường dẫn JAR |
| -m | Đối số truyền cho main method |
| -v | Các đối số truyền cho JVM |

jps được Oracle đánh dấu là công cụ experimental và unsupported; định dạng đầu ra có thể thay đổi và không nên dùng để xây dựng script phụ thuộc vào việc phân tích output. Ưu tiên jcmd cho quy trình kiểm tra thông thường.

### Khi ứng dụng chạy trong Docker

jcmd -l trên host có thể không liệt kê JVM đang chạy trong một Docker process riêng. Hãy kiểm tra từ bên trong container:

~~~bash
docker exec -it <container-name> sh
jcmd -l
~~~

Sau đó chạy jcmd với PID được nhìn thấy trong container. Nếu image không có shell hoặc JDK diagnostic tools, cần dùng công cụ phù hợp với image/runtime hoặc kiểm tra PID từ đúng process namespace trên host.

## 5. Kiểm tra command line của JVM đang chạy

Sau khi có PID, dùng:

~~~bash
jcmd <pid> VM.command_line
~~~

Lệnh này in command line đã dùng để khởi động VM. Đây là điểm kiểm tra tốt để tìm các tham số như:

- -Xms và -Xmx.
- -Dproperty=value.
- -XX:+UseG1GC hoặc các tùy chọn GC khác.
- -javaagent hoặc -agentlib.
- Class, JAR hoặc mục tiêu chạy.

Ví dụ đầu ra minh họa:

~~~text
VM Arguments:
jvm_args: -Xms256m -Xmx1g -Dapp.mode=prod
java_command: com.example.OrderApplication --port 8080
java_class_path (initial): app.jar
~~~

Tên trường và cách trình bày có thể thay đổi theo phiên bản/JVM. Hãy đọc nội dung trả về thay vì phụ thuộc vào một chuỗi output cố định.

Lưu ý: command line hiển thị thông tin khởi chạy. Nó không nhất thiết phản ánh mọi thay đổi cấu hình được thực hiện sau khi JVM đã chạy.

## 6. Kiểm tra VM flags đang có hiệu lực

Dùng:

~~~bash
jcmd <pid> VM.flags
~~~

Lệnh này in các VM flag và giá trị hiện tại của chúng. Muốn xem đầy đủ các flag mà VM hỗ trợ, dùng:

~~~bash
jcmd <pid> VM.flags -all
~~~

Một số flag thường cần kiểm tra:

| Flag | Ý nghĩa |
|---|---|
| InitialHeapSize | Heap ban đầu mà JVM sử dụng |
| MaxHeapSize | Giới hạn heap tối đa |
| ThreadStackSize | Kích thước stack mặc định cho thread Java |
| UseG1GC | Trạng thái sử dụng G1 garbage collector |
| UseZGC | Trạng thái sử dụng ZGC nếu JVM hỗ trợ |
| ActiveProcessorCount | Số CPU mà JVM dùng cho một số quyết định nội bộ |
| MaxMetaspaceSize | Giới hạn metaspace nếu được cấu hình |

Ví dụ:

~~~bash
jcmd 18420 VM.flags -all
~~~

Tìm các dòng liên quan đến heap hoặc GC trong output. Nếu cần xác định giá trị chính xác của một flag, hãy đọc tên và giá trị flag trực tiếp từ kết quả.

Không phải mọi JVM/vendor đều hỗ trợ cùng một tập flag. Một số flag chỉ thuộc HotSpot, có thể bị loại bỏ hoặc thay đổi theo phiên bản. Dùng:

~~~bash
jcmd <pid> help
~~~

để xem các diagnostic command mà JVM mục tiêu hỗ trợ.

## 7. Kiểm tra system properties

System property là các cặp tên/giá trị được truy cập từ Java code qua System.getProperty().

Ví dụ đặt property lúc khởi động:

~~~bash
java -Dapp.mode=prod -Dapp.region=ap-southeast-1 -jar app.jar
~~~

Để xem system properties hiện tại của tiến trình:

~~~bash
jcmd <pid> VM.system_properties
~~~

Ví dụ một phần kết quả:

~~~text
app.mode=prod
app.region=ap-southeast-1
java.home=/opt/jdk
java.version=25
java.vendor=Eclipse Adoptium
user.timezone=UTC
~~~

Các giá trị ví dụ chỉ để minh họa. Kết quả thực tế phụ thuộc JDK, hệ điều hành, cấu hình và ứng dụng.

Trong ứng dụng, có thể đọc một property cụ thể:

~~~java
String mode = System.getProperty("app.mode", "local");
System.out.println("app.mode = " + mode);
~~~

System.getProperties() trả về tập system properties hiện tại. Ứng dụng có thể gọi System.setProperty() để thay đổi giá trị trong quá trình chạy. Do đó, property hiện tại không nhất thiết giống nguyên văn tham số -D lúc khởi động.

## 8. Kiểm tra từ bên trong ứng dụng bằng RuntimeMXBean

Java Management API cung cấp RuntimeMXBean để đọc một số thông tin của JVM đang chạy.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.util.Arrays;

public class RuntimeParametersDemo {
    public static void main(String[] args) {
        RuntimeMXBean runtime =
                ManagementFactory.getRuntimeMXBean();

        System.out.println("PID: " + runtime.getPid());
        System.out.println("VM input arguments: "
                + runtime.getInputArguments());
        System.out.println("Application arguments: "
                + Arrays.toString(args));
        System.out.println("app.mode: "
                + System.getProperty("app.mode"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac RuntimeParametersDemo.java
java -Xms128m -Xmx512m -Dapp.mode=demo RuntimeParametersDemo --mode test "two words"
~~~

Kết quả minh họa:

~~~text
PID: <pid>
VM input arguments: [-Xms128m, -Xmx512m, -Dapp.mode=demo]
Application arguments: [--mode, test, two words]
app.mode: demo
~~~

PID thay đổi theo mỗi lần chạy. Các VM input arguments có thể có thêm phần tử nếu môi trường bổ sung tham số.

### Giới hạn của getInputArguments()

RuntimeMXBean.getInputArguments() trả về các đối số đã được truyền cho JVM và không bao gồm các đối số truyền cho main method. API này có thể trả về danh sách rỗng nếu không có VM input arguments.

Một số JVM nhận tùy chọn từ nhiều nguồn như lệnh java, biến môi trường hoặc file cấu hình. Không phải tất cả tùy chọn của lệnh java đều được chuyển tiếp thành VM input arguments. Vì vậy:

- Dùng getInputArguments() để xem VM input arguments mà runtime báo cáo.
- Dùng args trong main để xem đối số ứng dụng.
- Dùng jcmd VM.command_line để kiểm tra command line khởi chạy.
- Dùng jcmd VM.flags để kiểm tra giá trị VM flags hiện tại.

Không dùng getInputArguments() làm bằng chứng duy nhất cho toàn bộ command line.

### Đọc toàn bộ system properties bằng API

RuntimeMXBean còn có getSystemProperties(), trả về map các system property hiện tại:

~~~java
runtime.getSystemProperties().forEach((key, value) ->
        System.out.println(key + "=" + value));
~~~

Không nên in toàn bộ properties trong log production nếu chưa lọc dữ liệu. Một số ứng dụng có thể đặt thông tin nhạy cảm vào property.

## 9. Kiểm tra một JVM mới trước khi triển khai

Nếu muốn biết một JDK mới sẽ chọn giá trị VM flag như thế nào, có thể khởi chạy một JVM kiểm tra riêng.

### In VM settings

~~~bash
java -XshowSettings:vm -version
~~~

Xem thêm system properties:

~~~bash
java -XshowSettings:properties -version
~~~

Các lệnh này tạo một JVM mới rồi kết thúc. Chúng cho biết cấu hình của lần chạy kiểm tra, không đọc cấu hình của ứng dụng đang chạy.

### In toàn bộ VM flags ở thời điểm khởi động

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Tùy chọn này hữu ích để kiểm tra giá trị cuối cùng của nhiều HotSpot VM flags trong JVM vừa tạo. Có thể lọc output theo tên flag bằng công cụ của hệ điều hành.

Ví dụ trên Linux/macOS:

~~~bash
java -XX:+PrintFlagsFinal -version 2>&1 | grep -E 'InitialHeapSize|MaxHeapSize|UseG1GC'
~~~

Ví dụ trên Windows PowerShell:

~~~powershell
java -XX:+PrintFlagsFinal -version 2>&1 |
    Select-String 'InitialHeapSize|MaxHeapSize|UseG1GC'
~~~

Để xem các flag được JVM chọn theo cơ chế ergonomics, có thể dùng:

~~~bash
java -XX:+PrintCommandLineFlags -version
~~~

Các giá trị được JVM tự chọn có thể phụ thuộc RAM, CPU, container limits, hệ điều hành và phiên bản JDK. Không nên giả định giá trị mặc định trên máy phát triển sẽ giống môi trường production.

## 10. Đối chiếu các nguồn cấu hình

Khi giá trị thực tế không như mong đợi, kiểm tra theo bảng sau:

| Cần xác minh | Cách kiểm tra |
|---|---|
| Java executable được gọi | where java / Get-Command java -All / command -v java |
| PID ứng dụng | jcmd -l; công cụ process của hệ điều hành; PID trong log |
| Command line khởi chạy | jcmd <pid> VM.command_line |
| VM flags hiện tại | jcmd <pid> VM.flags -all |
| System properties hiện tại | jcmd <pid> VM.system_properties |
| VM input arguments từ code | RuntimeMXBean.getInputArguments() |
| Application arguments | main(String[] args) |
| Environment variables | Get-ChildItem Env:... hoặc printenv/echo |
| Cấu hình JVM của build tool | Gradle/Maven/IDE config và đúng tiến trình được khởi chạy |
| Cấu hình container/service | Docker/Kubernetes/service unit/launch script |

Ví dụ kiểm tra các biến môi trường trên Windows PowerShell:

~~~powershell
Get-ChildItem Env:JDK_JAVA_OPTIONS,Env:JAVA_TOOL_OPTIONS,Env:CLASSPATH
~~~

Trên Linux/macOS:

~~~bash
printenv JDK_JAVA_OPTIONS
printenv JAVA_TOOL_OPTIONS
printenv CLASSPATH
~~~

Nếu không có biến tương ứng, lệnh có thể không in ra giá trị. CLASSPATH thường chỉ được dùng làm classpath mặc định khi command line không chỉ định -cp hoặc --class-path.

Nếu cần xem command line của tiến trình ở cấp hệ điều hành:

Linux:

~~~bash
ps -ww -p <pid> -o pid,args
~~~

Windows PowerShell:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = <pid>" |
    Select-Object ProcessId, Name, CommandLine
~~~

Đầu ra của hệ điều hành phụ thuộc quyền truy cập và có thể bị rút gọn hoặc khác cách biểu diễn theo nền tảng. Command line cũng có thể chứa mật khẩu, token hoặc dữ liệu nhạy cảm nếu ứng dụng truyền chúng trực tiếp làm đối số.

## 11. Quy trình chẩn đoán khi tham số bị sai

Giả sử ứng dụng dự kiến chạy với heap tối đa 1 GB nhưng log cho thấy giới hạn thấp hơn.

Thực hiện lần lượt:

1. Xác định đúng PID của ứng dụng đang gặp vấn đề.
2. Chạy jcmd <pid> VM.command_line để biết command line khởi động.
3. Chạy jcmd <pid> VM.flags để xem giá trị heap hiện tại.
4. Kiểm tra JDK_JAVA_OPTIONS và JAVA_TOOL_OPTIONS trong môi trường tạo tiến trình.
5. Đọc script, service unit, Dockerfile hoặc cấu hình orchestrator đã thực sự tạo tiến trình.
6. Nếu ứng dụng chạy qua Gradle/Maven/IDE, xác định JVM nào chạy build và JVM nào chạy ứng dụng.
7. Sau khi tìm thấy nguồn sai, sửa đúng nguồn cấu hình rồi khởi động lại tiến trình.
8. Lặp lại bước kiểm tra trên PID mới để xác nhận giá trị đã thay đổi.

Không thể thay đổi mọi JVM option sau khi tiến trình đã khởi động. Các tham số khởi tạo như heap ban đầu/tối đa cần được cấu hình trước khi tạo JVM và thường phải khởi động lại ứng dụng. Một số HotSpot diagnostic flag có thể thay đổi động nếu flag đó cho phép; việc này phụ thuộc flag và JVM, không phải quy tắc áp dụng cho mọi tham số.

## 12. Lỗi thường gặp

### Kiểm tra nhầm PID

**Dấu hiệu:** jcmd trả về tham số của Gradle daemon, IDE hoặc một ứng dụng khác.

**Nguyên nhân:** máy có nhiều JVM; tên process ngắn hoặc PID bị thay đổi sau restart.

**Cách xử lý:** đối chiếu PID với main class/JAR và log khởi động. Luôn kiểm tra lại sau khi service restart vì PID mới có thể khác.

### getInputArguments() không hiển thị -cp

**Nguyên nhân:** getInputArguments() trả về VM input arguments, không đảm bảo chứa mọi tùy chọn của Java launcher.

**Cách xử lý:** dùng jcmd VM.command_line và kiểm tra cấu hình launcher/classpath riêng.

### System.getProperty() không có giá trị mong muốn

**Nguyên nhân:** property chưa được đặt, tên bị sai, tham số -D nằm sau main class nên trở thành application argument, hoặc ứng dụng đã ghi đè property.

**Cách xử lý:** kiểm tra vị trí -D, đọc jcmd VM.system_properties và tìm các lời gọi System.setProperty trong code.

### jcmd không thể attach vào process

**Nguyên nhân thường gặp:**

- Người chạy jcmd không có cùng effective user/group với process đích.
- Công cụ đang chạy trên máy hoặc process namespace khác.
- JVM không cho phép attach hoặc attach listener chưa khả dụng.
- PID không còn tồn tại hoặc process vừa restart.
- Runtime/vendor không hỗ trợ diagnostic command cần dùng.

**Cách xử lý:** chạy jcmd với đúng quyền người dùng trên cùng máy/container, xác nhận PID mới và kiểm tra jcmd <pid> help. Nếu công cụ không hỗ trợ lệnh đó, dùng JMX hoặc tài liệu diagnostic chính thức của vendor.

### jps không tìm thấy ứng dụng trong container

**Nguyên nhân:** jps không liệt kê JVM đang chạy trong một Docker process riêng khi gọi từ host.

**Cách xử lý:** chạy công cụ trong container hoặc lấy PID từ đúng process namespace.

### Giá trị heap khác với con số trong script

**Nguyên nhân:** script không phải nguồn thực tế, tham số bị thêm từ biến môi trường, JVM tự chọn giá trị ergonomic, hoặc bạn đang đọc một PID khác.

**Cách xử lý:** đối chiếu command line với VM.flags. Với heap, xem InitialHeapSize và MaxHeapSize thay vì chỉ tìm chuỗi -Xms/-Xmx trong script.

### jinfo không hoạt động

jinfo là công cụ experimental và unsupported trong tài liệu JDK hiện hành; nó có thể không có hoặc thay đổi trong các bản phát hành sau.

**Cách xử lý:** ưu tiên jcmd VM.command_line, VM.flags và VM.system_properties.

## 13. Bảo mật khi kiểm tra tham số

Tham số runtime có thể chứa thông tin nhạy cảm như access token, password, đường dẫn nội bộ, thông tin kết nối hoặc cấu hình agent. Vì vậy:

- Chỉ đọc command line và properties của process mà bạn có quyền kiểm tra.
- Không sao chép toàn bộ output vào ticket/log công khai khi chưa rà soát.
- Không truyền password/token qua command-line argument nếu có lựa chọn cấu hình an toàn hơn.
- Không mở JMX remote port công khai chỉ để xem RuntimeMXBean; nếu cần remote monitoring, cấu hình xác thực, mã hóa và network access phù hợp.
- Chỉ cấp quyền attach/diagnostic cho người vận hành được phép.

## 14. Checklist thực hành

- [ ] Phân biệt launcher options, JVM flags, system properties và application arguments.
- [ ] Xác định đúng PID của ứng dụng.
- [ ] Kiểm tra command line bằng jcmd VM.command_line.
- [ ] Kiểm tra VM flags bằng jcmd VM.flags hoặc VM.flags -all.
- [ ] Kiểm tra system properties bằng jcmd VM.system_properties.
- [ ] Đọc RuntimeMXBean.getInputArguments() và hiểu giới hạn của API.
- [ ] Kiểm tra args trong main method.
- [ ] Kiểm tra JDK_JAVA_OPTIONS, JAVA_TOOL_OPTIONS và file @argfile.
- [ ] Đối chiếu script/service/container/IDE/build tool đã tạo tiến trình.
- [ ] Khởi động lại và xác minh PID mới sau khi sửa tham số khởi tạo.
- [ ] Loại bỏ hoặc che dữ liệu nhạy cảm trước khi chia sẻ output.

## 15. Tài liệu tham khảo chính thức

- [jcmd — Java SE 25 Tool Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — danh sách JVM process và diagnostic commands như VM.command_line, VM.flags, VM.system_properties.
- [RuntimeMXBean — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/RuntimeMXBean.html) — getInputArguments(), getSystemProperties(), PID và thông tin runtime.
- [java — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — launcher options, JDK_JAVA_OPTIONS, argument files, -XshowSettings và HotSpot VM flags.
- [jps — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jps.html) — cách liệt kê JVM và ý nghĩa các tùy chọn -l, -m, -v.
- [jinfo — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jinfo.html) — trạng thái experimental/unsupported của jinfo.
- [Troubleshooting Guide — JAVA_TOOL_OPTIONS](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-guide.pdf) — cách biến môi trường bổ sung tùy chọn khi JVM được tạo.

Các diagnostic command và VM flags có thể khác nhau theo vendor/JVM và phiên bản JDK. Khi làm việc với một tiến trình cụ thể, dùng jcmd <pid> help để xác nhận những lệnh mà chính JVM đó hỗ trợ.
