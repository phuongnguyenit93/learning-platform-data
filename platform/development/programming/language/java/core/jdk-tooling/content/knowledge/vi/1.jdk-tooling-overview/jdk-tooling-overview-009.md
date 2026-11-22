# Công cụ phát triển trong JDK

JDK (Java Development Kit) cung cấp bộ công cụ để viết, biên dịch, chạy, đóng gói, phân tích và chẩn đoán ứng dụng Java. Nắm được các công cụ này giúp bạn xử lý từng giai đoạn của vòng đời ứng dụng, hiểu lỗi ở mức mã nguồn hoặc bytecode, và thu thập dữ liệu khi chương trình chạy có vấn đề.

Bài học dùng JDK 21 làm mốc ví dụ. Phần lớn lệnh cũng áp dụng cho các bản JDK hiện đại khác, nhưng tùy chọn cụ thể có thể thay đổi theo phiên bản và hệ điều hành.

## 1. JDK gồm những gì?

JDK bao gồm môi trường chạy Java cùng các công cụ phát triển. Một số thành phần thường dùng:

- **`javac`**: biên dịch mã nguồn `.java` thành bytecode `.class`.
- **`java`**: khởi chạy ứng dụng hoặc chạy trực tiếp một tệp nguồn Java.
- **`jshell`**: REPL để thử biểu thức và đoạn mã Java tương tác.
- **`jar`**: tạo, liệt kê và giải nén tệp lưu trữ JAR.
- **`javadoc`**: sinh tài liệu API từ mã nguồn và chú thích Javadoc.
- **`javap`**: xem cấu trúc lớp và bytecode.
- **`jdeps`, `jdeprscan`**: phân tích phụ thuộc và API đã bị đánh dấu deprecated.
- **`jlink`, `jpackage`**: tạo runtime tùy chỉnh và gói ứng dụng để phân phối.
- **`jcmd`, `jstack`, `jmap`, `jstat`, `jconsole`, `jfr`**: quan sát và chẩn đoán JVM đang chạy.
- **`keytool`, `jarsigner`**: quản lý kho khóa/chứng thư và ký hoặc xác minh JAR.

Cần phân biệt ba khái niệm:

| Thành phần | Vai trò |
|---|---|
| JDK | Bộ công cụ phát triển, có compiler và các tiện ích đi kèm |
| JVM | Máy ảo thực thi bytecode Java |
| Java runtime | Môi trường cần để chạy ứng dụng; runtime tùy chỉnh có thể được tạo bằng `jlink` |

Nếu chỉ có runtime mà không có JDK, bạn có thể chạy ứng dụng nhưng thường không có `javac`, `javadoc`, `jshell` và các công cụ phát triển khác.

## 2. Kiểm tra JDK đang được sử dụng

Mở Terminal, Command Prompt hoặc PowerShell:

~~~bash
java --version
javac --version
jshell --version
~~~

`java --version` cho biết phiên bản launcher/runtime. `javac --version` cho biết phiên bản compiler. Hai lệnh có thể trả về phiên bản khác nhau nếu máy có nhiều JDK và `PATH` đang trỏ tới các thư mục khác nhau.

Tìm executable đang được hệ điều hành phân giải:

~~~powershell
# Windows PowerShell
Get-Command java
Get-Command javac
~~~

~~~bash
# macOS / Linux
command -v java
command -v javac
~~~

Kiểm tra biến môi trường:

~~~powershell
# Windows PowerShell
$env:JAVA_HOME
$env:Path -split ';'
~~~

~~~bash
# macOS / Linux
printf '%s\n' "$JAVA_HOME"
printf '%s\n' "$PATH"
~~~

Thông thường, `JAVA_HOME` trỏ tới thư mục gốc của JDK; thư mục `bin` của JDK được thêm vào `PATH`. Không nên đặt `JAVA_HOME` trỏ thẳng vào `bin`.

## 3. Biên dịch và chạy chương trình

### 3.1. Biên dịch mã nguồn

Tạo tệp `Hello.java`:

~~~java
/**
 * Chương trình nhỏ dùng để minh họa các công cụ JDK.
 */
public class Hello {
    /**
     * Điểm bắt đầu của chương trình.
     */
    public static void main(String[] args) {
        System.out.println("Hello from JDK tools");
    }
}
~~~

Tạo thư mục đầu ra rồi biên dịch:

~~~bash
# macOS / Linux
mkdir -p out
javac --release 21 -Xlint:all -d out Hello.java
~~~

~~~powershell
# Windows PowerShell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 21 -Xlint:all -d out Hello.java
~~~

Các tùy chọn quan trọng:

- `--release 21`: biên dịch theo ngôn ngữ, bytecode và API công khai của Java 21. Tùy chọn này hữu ích khi cần kiểm soát phiên bản Java tối thiểu mà ứng dụng hỗ trợ.
- `-Xlint:all`: bật các cảnh báo bổ sung để phát hiện vấn đề tiềm ẩn.
- `-d out`: đặt các tệp `.class` được tạo vào thư mục `out`.
- `-classpath` hoặc `-cp`: chỉ định nơi compiler tìm các lớp và thư viện phụ thuộc.
- `--module-path`: chỉ định đường dẫn chứa các module khi làm việc với Java Platform Module System.

Nếu dự án cần tương thích Java 17, có thể dùng `--release 17` khi biên dịch bằng một JDK có hỗ trợ release đó. Không nên chỉ dùng `-source` và `-target` khi mục tiêu còn cần giới hạn API của nền tảng; `--release` xử lý cả ba khía cạnh này.

### 3.2. Chạy bytecode

Sau khi biên dịch thành công:

~~~bash
java -cp out Hello
~~~

Launcher `java` tìm lớp `Hello` trong classpath, nạp lớp và gọi phương thức `main`.

Một số cách khởi chạy phổ biến:

| Cách chạy | Ý nghĩa |
|---|---|
| `java -cp out Hello` | Chạy lớp có tên đầy đủ `Hello` từ classpath |
| `java -cp "out:lib/*" Hello` | Chạy trên macOS/Linux với nhiều thư mục hoặc JAR trong classpath |
| `java -cp "out;lib/*" Hello` | Cách viết tương ứng trên Windows, dùng dấu `;` phân cách |
| `java -jar app.jar` | Chạy JAR có khai báo `Main-Class` trong manifest |
| `java --module-path mods -m app/com.example.Main` | Chạy lớp chính thuộc một module trên module path |

Với `java -jar`, launcher lấy lớp chính từ manifest của JAR; các thiết lập classpath truyền bằng `-cp` trên cùng dòng lệnh không được dùng theo cách chạy này. Nếu ứng dụng cần thư viện ngoài, hãy cấu hình manifest `Class-Path` hoặc dùng cách khởi chạy phù hợp.

### 3.3. Chạy trực tiếp tệp nguồn

Từ JDK 11, có thể chạy một chương trình đơn giản mà không cần gọi `javac` riêng:

~~~bash
java Hello.java
~~~

Đây là chế độ source-file của launcher. Nó tiện cho script nhỏ, ví dụ minh họa và thử nghiệm nhanh. Với ứng dụng nhiều lớp, có phụ thuộc hoặc cần quy trình build lặp lại, nên dùng compiler và cấu trúc dự án rõ ràng.

## 4. Thử mã nhanh với JShell

`jshell` là môi trường REPL (Read-Eval-Print Loop). Bạn nhập một biểu thức hoặc câu lệnh, JShell đánh giá và hiển thị kết quả ngay.

Khởi động:

~~~bash
jshell
~~~

Ví dụ trong phiên JShell:

~~~java
int x = 12;
int y = 8;
x + y
String message = "JDK";
message.toLowerCase()
/vars
/methods
/exit
~~~

Một số lệnh điều khiển thường dùng:

- `/help`: xem trợ giúp.
- `/vars`: liệt kê biến đã khai báo.
- `/methods`: liệt kê phương thức đã khai báo.
- `/imports`: xem các import hiện có.
- `/save file.jsh`: lưu nội dung phiên làm việc.
- `/open file.jsh`: nạp lệnh từ tệp.
- `/reset`: đặt lại trạng thái phiên.
- `/exit`: kết thúc JShell.

JShell phù hợp để kiểm tra API, thử thuật toán ngắn hoặc tìm hiểu hành vi của một biểu thức. Nó không thay thế cấu trúc lớp, kiểm thử tự động hay quy trình build của ứng dụng thực tế.

## 5. Đóng gói và tạo tài liệu

### 5.1. Tạo và quản lý JAR

Sau khi đã biên dịch `Hello.java` vào `out`, tạo JAR có lớp chính:

~~~bash
jar --create --file hello.jar --main-class Hello -C out .
~~~

Chạy JAR:

~~~bash
java -jar hello.jar
~~~

Liệt kê nội dung:

~~~bash
jar --list --file hello.jar
~~~

Giải nén vào thư mục hiện tại:

~~~bash
jar --extract --file hello.jar
~~~

JAR là định dạng lưu trữ dựa trên ZIP, có thể chứa bytecode, tài nguyên và metadata trong `META-INF`. Tệp manifest có thể khai báo lớp chính, classpath và một số thuộc tính đóng gói khác. JAR không tự động bao gồm mọi thư viện phụ thuộc của ứng dụng.

### 5.2. Sinh tài liệu API

`javadoc` đọc chú thích Javadoc trong mã nguồn và tạo tài liệu HTML cho API:

~~~bash
javadoc -d docs Hello.java
~~~

Ví dụ chú thích:

~~~java
/**
 * Đại diện cho một bộ chuyển đổi nhiệt độ.
 *
 * @since 1.0
 */
public class TemperatureConverter {

    /**
     * Chuyển độ C sang độ F.
     *
     * @param celsius nhiệt độ theo độ C
     * @return nhiệt độ tương ứng theo độ F
     */
    public static double toFahrenheit(double celsius) {
        return celsius * 9.0 / 5.0 + 32.0;
    }
}
~~~

Nên mô tả hợp đồng API: mục đích, tham số, giá trị trả về, ngoại lệ có thể phát sinh và điều kiện sử dụng. Chú thích cần chính xác với hành vi thật của mã nguồn; tài liệu sinh ra không thay thế việc kiểm tra và thử nghiệm API.

## 6. Kiểm tra bytecode và phụ thuộc

### 6.1. Xem cấu trúc lớp và bytecode

`javap` là công cụ disassembler của JDK. Nó giúp xem chữ ký thành viên, modifier, constant pool và bytecode.

~~~bash
javap -classpath out Hello
javap -classpath out -c Hello
javap -classpath out -c -p Hello
~~~

- `-c`: hiển thị bytecode của các phương thức.
- `-p`: hiển thị cả thành viên private.
- `-verbose`: hiển thị thêm thông tin chi tiết như constant pool và metadata.

Dùng `javap` khi cần hiểu compiler đã chuyển mã nguồn thành bytecode như thế nào, kiểm tra chữ ký lớp hoặc điều tra lỗi liên quan tới class file.

### 6.2. Phân tích phụ thuộc

`jdeps` phân tích phụ thuộc ở mức package hoặc module:

~~~bash
jdeps --summary hello.jar
jdeps --recursive hello.jar
jdeps --jdk-internals hello.jar
~~~

`--recursive` mở rộng việc phân tích qua các phụ thuộc được tìm thấy. `--jdk-internals` giúp phát hiện ứng dụng phụ thuộc vào API nội bộ của JDK; các API này có thể thay đổi hoặc bị chặn ở phiên bản Java khác.

Nếu ứng dụng dùng thư viện bên ngoài, cung cấp classpath phù hợp để kết quả phân tích đầy đủ hơn, ví dụ `--class-path "lib/*"`.

### 6.3. Tìm API deprecated

`jdeprscan` quét class hoặc JAR để tìm các API Java đã bị đánh dấu deprecated:

~~~bash
jdeprscan --release 21 hello.jar
~~~

Kết quả giúp lập kế hoạch thay thế API cũ trước khi nâng cấp Java. Deprecated không đồng nghĩa API đã bị xóa; cần đọc tài liệu của API và phiên bản mục tiêu để quyết định cách thay thế.

### 6.4. Khám phá module

Một số lệnh hữu ích:

~~~bash
java --list-modules
java --describe-module java.base
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
jmod list "$JAVA_HOME/jmods/java.base.jmod"
~~~

- `java --list-modules`: liệt kê module có trong runtime đang được sử dụng.
- `java --describe-module`: xem thông tin module.
- `jmod describe`: đọc mô tả module trong tệp JMOD.
- `jmod list`: liệt kê nội dung JMOD.

Classpath và module path phục vụ hai cơ chế tìm lớp/module khác nhau. Ứng dụng truyền thống có thể chạy trên classpath; ứng dụng modular thường khai báo `module-info.java` và được chạy bằng module path.

## 7. Tạo runtime tùy chỉnh và bộ cài

### 7.1. Tạo runtime nhỏ

`jlink` ghép các module cần thiết để tạo một runtime image riêng. Điều này hữu ích khi phân phối ứng dụng modular và muốn giảm phần runtime không cần thiết.

Ví dụ trên macOS/Linux:

~~~bash
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging --output runtime-mini
~~~

Ví dụ trên Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME/jmods" --add-modules java.base,java.logging --output runtime-mini
~~~

Runtime vừa tạo chứa các module được chọn và những phụ thuộc cần thiết. Danh sách module phải phù hợp với ứng dụng. Nếu ứng dụng dùng JDBC, XML, logging hoặc module khác, cần bổ sung các module tương ứng. Có thể dùng `jdeps` để hỗ trợ xác định phụ thuộc, nhưng vẫn phải kiểm tra các phần được nạp động qua reflection, service loader hoặc cấu hình.

### 7.2. Đóng gói ứng dụng

`jpackage` tạo gói ứng dụng hoặc application image cho nền tảng đích. Ví dụ:

~~~bash
jpackage --type app-image --name Demo --input dist --main-jar demo.jar --main-class com.example.Main
~~~

Thư mục `dist` phải chứa JAR được chỉ định và các tệp đầu vào cần thiết. Loại gói như `msi`, `exe`, `dmg`, `pkg` hoặc `deb` phụ thuộc hệ điều hành và yêu cầu công cụ đóng gói của nền tảng. Nên build và kiểm thử gói trên hệ điều hành đích, kiểm tra đường dẫn tài nguyên, quyền chạy, cấu hình runtime và cách cập nhật ứng dụng.

`jlink` tạo runtime; `jpackage` tạo bộ phân phối ứng dụng. Hai công cụ có thể kết hợp: tạo runtime riêng trước, sau đó dùng runtime đó khi đóng gói nếu quy trình phân phối yêu cầu.

## 8. Theo dõi và chẩn đoán JVM đang chạy

Các công cụ chẩn đoán thường cần PID của tiến trình Java. Có thể liệt kê các JVM cục bộ bằng:

~~~bash
jcmd -l
~~~

Trên môi trường container, máy chủ từ xa hoặc môi trường bị giới hạn quyền, danh sách tiến trình có thể không hiển thị đầy đủ.

### 8.1. jcmd — giao diện chẩn đoán tổng hợp

`jcmd` gửi lệnh chẩn đoán tới một JVM đang chạy:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> GC.heap_info
jcmd <pid> Thread.print
~~~

Xem các lệnh JVM hỗ trợ:

~~~bash
jcmd <pid> help
jcmd <pid> help GC.heap_info
~~~

`jcmd` thường là điểm bắt đầu tốt vì cung cấp nhiều thao tác quan sát và chẩn đoán. Lệnh có sẵn phụ thuộc phiên bản JVM và trạng thái tiến trình.

### 8.2. Thread dump

~~~bash
jstack -l <pid>
~~~

Thread dump ghi lại stack trace và trạng thái các thread tại một thời điểm. Dùng nó để điều tra:

- Thread bị BLOCKED hoặc chờ lock.
- Deadlock.
- Thread pool không xử lý được công việc.
- Request bị treo hoặc chậm kéo dài.

Một thread dump là ảnh chụp tại một thời điểm. Khi điều tra sự cố, nên lấy vài bản cách nhau một khoảng thời gian và so sánh trạng thái, stack trace cùng mức độ lặp lại.

### 8.3. Heap và thống kê GC

Xem histogram đối tượng:

~~~bash
jmap -histo:live <pid>
~~~

Tạo heap dump để phân tích sâu:

~~~bash
jmap -dump:live,format=b,file=heap.hprof <pid>
~~~

`heap.hprof` có thể được mở bằng công cụ phân tích heap tương thích, chẳng hạn VisualVM hoặc Eclipse Memory Analyzer. Heap dump có thể rất lớn và chứa dữ liệu nhạy cảm đang nằm trong bộ nhớ; cần kiểm soát nơi lưu, quyền truy cập và thời gian lưu giữ.

Theo dõi thống kê GC theo chu kỳ:

~~~bash
jstat -gcutil <pid> 1000 10
~~~

Lệnh trên lấy mẫu mỗi 1.000 mili giây, tối đa 10 lần. Các cột cho biết mức sử dụng vùng bộ nhớ và số liệu GC theo collector/JVM. Hãy đọc chú giải của đúng phiên bản JDK trước khi diễn giải một cột thành kết luận về nguyên nhân lỗi.

### 8.4. Quan sát bằng jconsole

~~~bash
jconsole
~~~

`jconsole` cung cấp giao diện đồ họa để xem mức sử dụng heap, thread, class, MBean và một số chỉ số JVM. Có thể chọn tiến trình Java cục bộ hoặc kết nối JMX từ xa nếu ứng dụng đã được cấu hình phù hợp.

JMX từ xa cần cấu hình xác thực và bảo vệ kết nối. Không mở cổng quản trị JVM ra mạng công cộng mà không có kiểm soát truy cập và mã hóa phù hợp.

### 8.5. Ghi và đọc Java Flight Recorder

Java Flight Recorder (JFR) thu thập sự kiện runtime với mức overhead thường thấp khi cấu hình phù hợp. Có thể khởi động bản ghi bằng `jcmd`:

~~~bash
jcmd <pid> JFR.start name=profile settings=profile duration=60s filename=profile.jfr
~~~

Sau khi tệp được tạo, xem tóm tắt:

~~~bash
jfr summary profile.jfr
~~~

In các sự kiện ra văn bản:

~~~bash
jfr print profile.jfr
~~~

Có thể mở tệp `.jfr` bằng JDK Mission Control để lọc sự kiện, xem thời gian CPU, allocation, GC, lock contention và các dữ liệu liên quan. Chọn cấu hình ghi phù hợp với câu hỏi điều tra; ghi quá nhiều sự kiện hoặc ghi quá lâu có thể tạo tệp lớn.

### 8.6. jhsdb — Serviceability Agent

`jhsdb` hỗ trợ phân tích sâu tiến trình hoặc core dump, ví dụ:

~~~bash
jhsdb jstack --pid <pid>
~~~

Đây là công cụ chuyên sâu, có thể cần quyền hệ điều hành cao hơn và có rủi ro ảnh hưởng tới tiến trình đang được kiểm tra. Chỉ dùng khi các công cụ thông thường chưa đủ và đã hiểu rõ môi trường chạy.

## 9. Quản lý khóa, chứng thư và chữ ký

### 9.1. keytool

`keytool` quản lý keystore, key pair và chứng thư số. Ví dụ tạo khóa RSA trong kho PKCS12:

~~~bash
keytool -genkeypair -alias app -keyalg RSA -keysize 3072 -validity 365 -storetype PKCS12 -keystore app.p12
~~~

Lệnh sẽ yêu cầu nhập mật khẩu và thông tin chứng thư. Liệt kê nội dung keystore:

~~~bash
keytool -list -keystore app.p12 -storetype PKCS12
~~~

Keystore chứa vật liệu khóa hoặc chứng thư; cần bảo vệ mật khẩu, khóa riêng và bản sao lưu theo chính sách bảo mật của dự án.

### 9.2. jarsigner

`jarsigner` ký JAR bằng khóa trong keystore:

~~~bash
jarsigner -keystore app.p12 -storetype PKCS12 app.jar app
~~~

Xác minh chữ ký:

~~~bash
jarsigner -verify -verbose -certs app.jar
~~~

Chữ ký giúp xác minh tính toàn vẹn và nguồn ký của nội dung JAR theo chuỗi tin cậy. Ký JAR không phải là mã hóa nội dung; người có tệp vẫn có thể đọc các lớp và tài nguyên không được mã hóa. Không đưa khóa riêng hoặc mật khẩu keystore vào mã nguồn, log hay kho Git.

## 10. Một số tiện ích chuyên biệt khác

- **`serialver`**: hiển thị giá trị `serialVersionUID` của lớp Serializable. Ví dụ: `serialver -classpath out com.example.Model`.
- **`jmod`**: tạo, mô tả và liệt kê tệp module JMOD; thường gặp trong quy trình module/runtime.
- **`jdeprscan`**: hỗ trợ rà soát API deprecated trước khi nâng cấp phiên bản Java.
- **`jfr`**: đọc và tóm tắt bản ghi Java Flight Recorder.
- **`jpackage`**: tạo application image hoặc gói cài đặt theo nền tảng.

Không phải mọi lệnh đều xuất hiện trong mọi bản phân phối hoặc mọi môi trường runtime. Nếu không tìm thấy một executable, hãy kiểm tra xem đang dùng JDK hay runtime rút gọn, kiểm tra `JAVA_HOME`, `PATH` và danh sách công cụ của đúng bản JDK.

## 11. Quy trình thực hành từ mã nguồn đến chẩn đoán

Với một chương trình Java nhỏ, có thể đi theo chuỗi sau:

1. **Xác nhận toolchain:** chạy `java --version` và `javac --version`; bảo đảm compiler và runtime đúng phiên bản mong muốn.
2. **Biên dịch:** dùng `javac --release 21 -Xlint:all -d out Hello.java`.
3. **Chạy:** dùng `java -cp out Hello` để xác nhận hành vi chương trình.
4. **Đóng gói:** dùng `jar --create --file hello.jar --main-class Hello -C out .`, sau đó chạy `java -jar hello.jar`.
5. **Sinh tài liệu:** dùng `javadoc -d docs Hello.java` để kiểm tra chú thích API.
6. **Kiểm tra bytecode và phụ thuộc:** dùng `javap -c -p -classpath out Hello` và `jdeps --summary hello.jar`.
7. **Quan sát ứng dụng thực tế:** lấy PID bằng `jcmd -l`; khi cần, dùng `jcmd`, `jstack`, `jstat` hoặc JFR để thu thập bằng chứng.

Mỗi công cụ trả lời một loại câu hỏi. Ví dụ, `javap` cho biết bytecode trông như thế nào; `jdeps` cho biết lớp/module phụ thuộc vào đâu; `jstack` cho biết thread đang làm gì tại thời điểm chụp; JFR giúp phân tích chuỗi sự kiện theo thời gian.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `javac` không được nhận diện | Chưa cài JDK hoặc `PATH` thiếu thư mục `bin` | Chạy `Get-Command javac` hoặc `command -v javac`; kiểm tra `JAVA_HOME` |
| `java` và `javac` khác phiên bản | Máy có nhiều JDK và hai executable trỏ tới các nơi khác nhau | Kiểm tra đường dẫn thực tế của cả hai lệnh |
| `Could not find or load main class` | Sai tên lớp, package hoặc classpath | Kiểm tra tên đầy đủ của lớp và vị trí `.class`; cập nhật `-cp` |
| `UnsupportedClassVersionError` | Runtime cũ hơn phiên bản bytecode đã biên dịch | Chạy bằng runtime tương thích hoặc biên dịch lại với `--release` phù hợp |
| `no main manifest attribute` | JAR thiếu `Main-Class` | Tạo manifest đúng hoặc dùng `jar --main-class` khi đóng gói |
| Thiếu lớp phụ thuộc lúc chạy | Thư viện không có trong classpath/module path hoặc manifest | Kiểm tra cấu hình classpath, module path và manifest |
| `jcmd` không kết nối được tiến trình | Khác người dùng, giới hạn container, JVM không hỗ trợ attach hoặc chính sách hệ điều hành | Kiểm tra quyền, PID, môi trường chạy và cấu hình attach |
| Không tìm thấy module khi dùng `jlink` | Thiếu module trong module path hoặc danh sách module chưa đủ | Kiểm tra JMOD/JAR đầu vào và phụ thuộc; dùng `jdeps` để hỗ trợ phân tích |

Một số lưu ý khi làm việc:

- Luôn xác nhận phiên bản bằng cả `java --version` và `javac --version`.
- Dùng `--release` để kiểm soát API mục tiêu khi biên dịch.
- Phân biệt classpath với module path; không trộn hai cơ chế mà không hiểu cách launcher tìm lớp.
- Đọc trợ giúp của đúng executable trước khi dùng tùy chọn ít quen thuộc: `java --help`, `javac --help`, `jcmd <pid> help` hoặc `jfr help`.
- Heap dump, thread dump và JFR có thể chứa thông tin vận hành hoặc dữ liệu nhạy cảm. Lưu trữ và chia sẻ chúng như dữ liệu nội bộ cần bảo vệ.
- Các lệnh attach và phân tích tiến trình có thể bị giới hạn bởi quyền người dùng, container, chính sách bảo mật hoặc hệ điều hành.

## 13. Chọn đúng công cụ

| Nhu cầu | Công cụ nên bắt đầu |
|---|---|
| Biên dịch `.java` | `javac` |
| Chạy lớp hoặc JAR | `java` |
| Thử API nhanh | `jshell` |
| Tạo hoặc xem nội dung JAR | `jar` |
| Sinh tài liệu API | `javadoc` |
| Xem bytecode | `javap` |
| Tìm phụ thuộc và JDK internals | `jdeps` |
| Rà soát API deprecated | `jdeprscan` |
| Tạo runtime nhỏ | `jlink` |
| Tạo gói phân phối | `jpackage` |
| Xem thông tin JVM đang chạy | `jcmd` |
| Kiểm tra thread/deadlock | `jstack` hoặc `jcmd Thread.print` |
| Phân tích heap | `jmap` và công cụ đọc heap dump |
| Theo dõi GC theo mẫu | `jstat` |
| Quan sát JVM bằng giao diện đồ họa | `jconsole` |
| Ghi nhận sự kiện runtime | `jcmd` và `jfr` |
| Quản lý chứng thư và ký JAR | `keytool`, `jarsigner` |

Các công cụ JDK bổ sung khả năng quan sát và kiểm soát ở nhiều tầng: mã nguồn, bytecode, module, gói phân phối và tiến trình JVM. Hãy bắt đầu bằng công cụ nhỏ nhất có thể trả lời câu hỏi hiện tại, đọc trợ giúp theo phiên bản JDK đang dùng, rồi mở rộng sang công cụ phân tích sâu khi đã có bằng chứng cần thiết.
