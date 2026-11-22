# Bản đồ công cụ JDK

Java Development Kit (JDK) là bộ công cụ để viết, biên dịch, chạy, kiểm tra, đóng gói, bảo mật và chẩn đoán ứng dụng Java. JDK không chỉ có compiler. Mỗi lệnh giải quyết một phần cụ thể trong vòng đời phát triển; chọn đúng công cụ giúp tìm lỗi nhanh hơn và tránh chạy lệnh có tác động lớn khi chưa cần thiết.

Bài này nhóm các lệnh theo công việc thực tế, giải thích đầu vào/đầu ra, chỉ ra khi nào nên dùng và kết nối chúng thành một quy trình hoàn chỉnh. Ví dụ và cú pháp dựa trên JDK 26. Nhiều lệnh cốt lõi cũng có trong các bản JDK trước, nhưng option và hành vi có thể thay đổi theo phiên bản, nhà cung cấp và hệ điều hành.

## 1. Bản đồ JDK theo vòng đời

~~~text
Explore and write
  jshell, jdb
        |
        v
Compile and run
  javac, java
        |
        v
Inspect and document
  jar, javap, javadoc, serialver
        |
        v
Analyze dependencies and modules
  jdeps, jdeprscan, jnativescan, jmod, jimage
        |
        v
Package and distribute
  jar, jlink, jpackage
        |
        v
Secure artifacts and certificates
  keytool, jarsigner
        |
        v
Operate and diagnose
  jcmd, jfr, jstat, jps, jconsole, jhsdb
~~~

Sáu câu hỏi giúp chọn công cụ:

1. Muốn viết hoặc thử code? Dùng jshell; debug từng bước bằng jdb.
2. Muốn biến source thành chương trình chạy được? Dùng javac để compile và java để chạy.
3. Muốn biết file build chứa gì? Dùng jar, javap, jdeps, jmod hoặc jimage tùy loại file.
4. Muốn phân phối ứng dụng? Dùng jar, jlink hoặc jpackage.
5. Cần xác thực hoặc ký artifact? Dùng keytool và jarsigner.
6. Cần biết JVM đang làm gì? Dùng jcmd, JFR/jfr, jstat, jconsole hoặc jhsdb.

Một số công cụ xuất hiện ở nhiều giai đoạn. Ví dụ jar vừa tạo archive vừa kiểm tra nội dung; jdeps vừa hỗ trợ review dependency vừa giúp chuẩn bị module set cho jlink.

## 2. Phân biệt JDK tools và công cụ bên ngoài

Các lệnh JDK thường nằm trong thư mục bin của JDK được chọn:

~~~text
<JDK_HOME>/
  bin/
    java
    javac
    jar
    jcmd
    jlink
    ...
  conf/
  include/
  jmods/
  legal/
  lib/
~~~

Trên Windows, executable thường có hậu tố .exe, ví dụ java.exe và javac.exe.

| Nhóm | Ví dụ | Có thuộc JDK không? |
|---|---|---|
| Compile/run | java, javac, jshell | Có |
| Archive/inspect | jar, javap, javadoc | Có |
| Dependency/module | jdeps, jmod, jimage, jlink | Có |
| Package | jpackage | Có |
| Security | keytool, jarsigner | Có |
| JVM diagnostics | jcmd, jfr, jstat, jps, jconsole | Có |
| Build automation | Maven, Gradle | Không, cài riêng |
| IDE | IntelliJ IDEA, Eclipse, VS Code extensions | Không, cài riêng |
| Profiling UI | JDK Mission Control (JMC) | Phân phối riêng; không giả định luôn có sẵn trong JDK |
| Container | Docker, Podman, Kubernetes | Không |
| Source control | Git | Không |

JDK tools cung cấp thao tác nền tảng. Maven và Gradle điều phối lifecycle, dependency, plugin, test và build automation. IDE hỗ trợ viết code và tích hợp các công cụ. Chúng bổ sung cho nhau, không thay thế nhau.

## 3. Chọn đúng JDK trước khi chạy công cụ

Máy có thể cài nhiều JDK. Lệnh java trên PATH và JDK mà IDE/CI sử dụng có thể khác nhau. Trước khi điều tra, xác định chính xác executable.

Linux/macOS:

~~~bash
java --version
javac --version
command -v java
echo "$JAVA_HOME"
~~~

Windows PowerShell:

~~~powershell
java --version
javac --version
Get-Command java -All
$env:JAVA_HOME
$env:PATH -split ';'
~~~

Nếu muốn gọi trực tiếp một JDK cụ thể, dùng đường dẫn đầy đủ tới bin của nó. Không dựa vào kết quả java --version của terminal để kết luận Maven, Gradle, IDE hoặc service đang dùng cùng runtime.

Kiểm tra trợ giúp:

~~~bash
java --help
javac --help
jar --help
jlink --help
jpackage --help
~~~

Không phải mọi công cụ đều dùng cùng cú pháp trợ giúp. Với jcmd, hỏi chính JVM:

~~~bash
jcmd <pid> help
jcmd <pid> help JFR.start
~~~

Với jlink, xem plugin được JDK hiện tại hỗ trợ:

~~~bash
jlink --list-plugins
~~~

Đọc trợ giúp của đúng JDK đang chạy vì option có thể được thêm, thay đổi hoặc deprecated giữa các bản.

## 4. Công cụ tương tác và thử nghiệm: jshell

jshell là REPL (Read-Eval-Print Loop) cho phép nhập biểu thức, câu lệnh và khai báo Java mà không cần tạo project đầy đủ.

~~~text
$ jshell
jshell> int x = 7
x ==> 7

jshell> int y = 5
y ==> 5

jshell> System.out.println(x * y)
35

jshell> /exit
~~~

Dùng jshell để thử API và biểu thức nhỏ, kiểm tra cách một class hoặc method hoạt động, minh họa Java cho người học hoặc tạo nhanh một đoạn tính toán. jshell không thay thế project build có dependency, test, module và cấu hình production. Khi thử code phụ thuộc thư viện ngoài, cần cung cấp classpath hoặc module path phù hợp.

Một số lệnh REPL hữu ích:

| Lệnh | Công dụng |
|---|---|
| /help | Xem trợ giúp |
| /vars | Xem biến đã khai báo |
| /methods | Xem method đã khai báo |
| /types | Xem type đã khai báo |
| /list | Liệt kê snippet |
| /reset | Xóa trạng thái session |
| /save file.jsh | Lưu snippet |
| /open file.jsh | Nạp snippet |
| /exit | Thoát |

## 5. Biên dịch và chạy: javac, java

javac chuyển Java source thành bytecode trong các file .class. java khởi chạy ứng dụng trên JVM.

### javac

~~~bash
javac -d out src/com/acme/Main.java
~~~

Các option thường dùng:

| Option | Mục đích |
|---|---|
| -d | Thư mục output cho class file |
| -cp hoặc -classpath | Classpath chứa dependency |
| --module-path | Module path |
| --release 17 | Giới hạn API và bytecode theo Java 17 |
| -g | Sinh debug information |
| -parameters | Giữ tên tham số method trong metadata |
| -Xlint | Bật cảnh báo compiler |
| -Werror | Biến warning thành lỗi trong cấu hình hỗ trợ |

--release là lựa chọn quan trọng khi cần compile cho một Java release cũ hơn JDK đang chạy compiler. Nó kết hợp kiểm soát language rules, class file target và API nền tảng của release đó. Chỉ đặt -source và -target không cung cấp cùng mức kiểm tra API.

### java

Chạy class trên classpath:

~~~bash
java -cp out com.acme.Main
~~~

Chạy executable JAR có manifest Main-Class:

~~~bash
java -jar app.jar
~~~

Chạy modular application:

~~~bash
java --module-path mods -m com.acme.app/com.acme.Main
~~~

Chọn runtime option:

~~~bash
java -Xms256m -Xmx1g -jar app.jar
~~~

-Xms và -Xmx lần lượt đặt heap ban đầu và giới hạn heap tối đa. Đây là ví dụ cấu hình, không phải giá trị mặc định phù hợp cho mọi ứng dụng.

### Classpath và module path

- Classpath tìm class và resource theo cơ chế class loader truyền thống.
- Module path tìm named module và áp dụng module resolution, readability, exports và encapsulation.
- Một ứng dụng có thể kết hợp module path với classpath, nhưng cần hiểu ranh giới giữa named module và unnamed module.

Lỗi ClassNotFoundException, NoClassDefFoundError, UnsupportedClassVersionError và InaccessibleObjectException thường cần kiểm tra version, classpath/module path và dependency thực tế.

## 6. Archive và kiểm tra nội dung: jar

jar tạo, liệt kê, cập nhật và trích xuất Java Archive. JAR dựa trên định dạng ZIP và thường chứa class, resource cùng metadata trong META-INF.

Tạo JAR:

~~~bash
jar --create --file app.jar -C out .
~~~

Tạo executable JAR:

~~~bash
jar --create --file app.jar --main-class com.acme.Main -C out .
~~~

Liệt kê file:

~~~bash
jar --list --file app.jar
~~~

Giải nén:

~~~bash
jar --extract --file app.jar --dir extracted
~~~

Kiểm tra archive:

~~~bash
jar --validate --file app.jar
~~~

Đọc module descriptor:

~~~bash
jar --describe-module --file app.jar
~~~

Dùng jar khi cần kiểm tra archive, manifest, module descriptor hoặc nội dung resource. jar --validate kiểm tra các vấn đề cấu trúc archive mà công cụ hỗ trợ; nó không chạy unit test, không xác minh toàn bộ dependency và không chứng minh ứng dụng hoạt động đúng.

## 7. Phân tích bytecode: javap

javap disassemble class file để xem bytecode và metadata. Nó hữu ích khi cần kiểm tra compiler output, API, class version, access modifier, constant pool hoặc method invocation.

~~~bash
javap -classpath app.jar com.acme.Main
javap -classpath app.jar -c com.acme.Main
javap -classpath app.jar -verbose com.acme.Main
javap -classpath app.jar -p com.acme.Main
~~~

Kết hợp javap -verbose với lỗi UnsupportedClassVersionError để xác định class file major version. Ví dụ Java 17 dùng major version 61. javap giúp quan sát bytecode, nhưng không thay thế test hoặc debugger.

## 8. Tạo API documentation: javadoc

javadoc tạo HTML API documentation từ source và Javadoc comments.

~~~bash
javadoc -d docs/api -sourcepath src -subpackages com.acme
~~~

Javadoc comment:

~~~java
/**
 * Calculates a discount for an order.
 *
 * @param amount original amount in currency units
 * @param percent discount percentage from 0 to 100
 * @return amount after discount
 * @throws IllegalArgumentException if the inputs are invalid
 */
public static double discounted(double amount, double percent) {
    if (amount < 0 || percent < 0 || percent > 100) {
        throw new IllegalArgumentException("Invalid discount");
    }
    return amount * (1.0 - percent / 100.0);
}
~~~

Một API document tốt giải thích contract, tham số, giá trị trả về, exception và ví dụ sử dụng. Không ghi secret hoặc dữ liệu nội bộ vào Javadoc được publish công khai.

## 9. Công cụ bổ trợ trong nhóm inspect

| Công cụ | Dùng để | Ví dụ |
|---|---|---|
| serialver | Tính/hiển thị serialVersionUID cho Serializable class | serialver com.acme.Model |
| jdb | Debug Java bằng breakpoint, step và inspect variable | jdb com.acme.Main |
| javap | Xem bytecode và metadata | javap -c -verbose com.acme.Main |
| jar | Kiểm tra archive và manifest | jar --list --file app.jar |
| javadoc | Sinh tài liệu API | javadoc -d docs/api ... |

serialver chỉ hữu ích khi ứng dụng thật sự dùng Java serialization tương thích. Không tự thêm serialVersionUID vào mọi class nếu không có yêu cầu serialization.

jdb là command-line debugger. Debug từ xa có thể yêu cầu mở JDWP port; không expose cổng debug ra mạng không tin cậy. Ưu tiên debug local hoặc môi trường được kiểm soát.

## 10. Phân tích dependency và module: jdeps

jdeps phân tích dependency của class, package, JAR và module. Nó giúp phát hiện dependency ngoài, module JDK cần thiết và các tham chiếu tới API nội bộ.

~~~bash
jdeps --summary app.jar
jdeps --list-deps app.jar
jdeps --print-module-deps app.jar
jdeps --recursive --verbose:class app.jar
jdeps --missing-deps app.jar
~~~

Với ứng dụng dùng multi-release JAR, chỉ định release tương ứng bằng --multi-release. Với dependency ngoài, cung cấp classpath/module path để tránh kết luận thiếu chính xác.

jdeps dựa trên phân tích tĩnh. Reflection, ServiceLoader, class name được tạo động, JNI, plugin và resource loading có thể không được phát hiện đầy đủ. Xác minh bằng integration test và runtime evidence trước khi thu hẹp module set.

### Công cụ kiểm tra API deprecated: jdeprscan

jdeprscan quét JAR hoặc class files để tìm việc sử dụng API đã deprecated trong một Java release:

~~~bash
jdeprscan --release 17 app.jar
~~~

Dùng kết quả để lập kế hoạch nâng JDK và thay API. Deprecated không đồng nghĩa API đã bị xóa ngay; hãy đọc warning và tài liệu migration của đúng API.

### Kiểm tra native API: jnativescan

jnativescan quét JAR để tìm việc sử dụng native functionality mà công cụ có thể nhận diện:

~~~bash
jnativescan --class-path "lib/*" app.jar
~~~

Nó hỗ trợ review native access và chuẩn bị cho chính sách native access của các JDK mới. Kết quả scan không chứng minh mọi native behavior đã được phát hiện; kiểm tra JNI/JNA, dynamic loading và native dependency thực tế.

## 11. Module packaging internals: jmod và jimage

jmod tạo và liệt kê JMOD files. JMOD là định dạng module archive được dùng trong quy trình JDK/module tooling, đặc biệt làm đầu vào cho jlink. Đây không phải định dạng ứng dụng thông thường để người dùng tải và chạy như JAR.

~~~bash
jmod describe module.jmod
jmod list module.jmod
jmod create --class-path out --module-version 1.0 module.jmod
~~~

jimage kiểm tra nội dung file module image nội bộ của JDK/runtime image:

~~~bash
jimage list "$JAVA_HOME/lib/modules"
~~~

jimage hữu ích khi điều tra module/resource trong runtime image. Nó không phải công cụ thay thế jar để xem mọi JAR archive thông thường.

## 12. Dependency map nối với runtime image

~~~text
Application source + dependencies
             |
             v
       javac / build tool
             |
             v
       JAR / module output
             |
             v
        jdeps analysis
             |
             v
 Review reflection / services / JNI
             |
             v
      jlink --add-modules
             |
             v
     Custom runtime image
             |
             v
        jpackage
             |
             v
 Application image / installer
~~~

Ví dụ modular app:

~~~bash
jlink --module-path "mods:$JAVA_HOME/jmods" --add-modules com.acme.app --output build/runtime
~~~

Kiểm tra runtime:

~~~bash
build/runtime/bin/java --version
build/runtime/bin/java --list-modules
build/runtime/bin/java --validate-modules
~~~

Đóng gói app image từ runtime đã tạo:

~~~bash
jpackage --type app-image --name MyApp --module-path mods --module com.acme.app/com.acme.Main --runtime-image build/runtime --dest build/packages
~~~

jlink tạo custom runtime; jpackage tạo application image hoặc native installer. Native package phải được build trên nền tảng đích; không giả định jpackage hỗ trợ cross-platform packaging. Runtime image cần được rebuild khi JDK security update yêu cầu.

## 13. Bảo mật và ký artifact: keytool, jarsigner

keytool quản lý keystore, private/public key, certificate chain và trusted certificate. Nó thường được dùng để tạo key pair, kiểm tra certificate, import CA và quản lý truststore.

Tạo PKCS12 keystore và key pair:

~~~bash
keytool -genkeypair -alias release -keyalg RSA -keysize 3072 -validity 365 -keystore release.p12 -storetype PKCS12
~~~

Liệt kê entry:

~~~bash
keytool -list -keystore release.p12 -storetype PKCS12
~~~

In certificate:

~~~bash
keytool -printcert -file certificate.pem
~~~

Import certificate:

~~~bash
keytool -importcert -alias company-ca -file company-ca.pem -keystore truststore.p12 -storetype PKCS12
~~~

jarsigner ký và xác minh JAR:

~~~bash
jarsigner -keystore release.p12 -storetype PKCS12 app.jar release
jarsigner -verify -verbose -certs app.jar
~~~

Thứ tự quan trọng: hoàn tất shading, resource merge và chỉnh manifest trước; sau đó ký artifact cuối. Thay đổi nội dung archive sau khi ký có thể làm chữ ký không còn hợp lệ.

Không commit keystore, private key hoặc password vào repository. Dùng secret manager, HSM hoặc signing service theo policy. Chữ ký xác thực tính toàn vẹn và danh tính theo certificate chain; vẫn cần quản lý trust anchor, thời hạn certificate, revocation và private key.

## 14. Chẩn đoán JVM đang chạy: jcmd

jcmd gửi diagnostic command tới JVM. Đây thường là điểm bắt đầu tốt khi điều tra process đang chạy.

Liệt kê JVM nhìn thấy:

~~~bash
jcmd -l
~~~

Xem lệnh được JVM hỗ trợ:

~~~bash
jcmd <pid> help
~~~

Lấy version, command line, flags, system properties và uptime:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
jcmd <pid> VM.uptime
~~~

Lấy heap info:

~~~bash
jcmd <pid> GC.heap_info
~~~

Thread dump:

~~~bash
jcmd <pid> Thread.print -l
~~~

Class histogram:

~~~bash
jcmd <pid> GC.class_histogram
~~~

Heap dump:

~~~bash
jcmd <pid> GC.heap_dump heap.hprof
~~~

Các lệnh không có cùng mức tác động. Thread dump có thể tạo output lớn; class histogram có thể tốn thời gian; heap dump có thể gây pause, cần full GC và tạo file lớn chứa dữ liệu nhạy cảm. Kiểm tra dung lượng và tác động trước khi chạy trên production.

jcmd thường cần chạy trên cùng máy và cùng effective user/group với JVM. Trong container, chạy trong đúng PID namespace và môi trường. Không attach được không đồng nghĩa JVM đã hỏng.

## 15. Flight Recorder: JFR và jfr

Java Flight Recorder (JFR) thu thập event runtime như CPU samples, allocation, GC, thread, monitor contention, socket và file I/O. JFR phù hợp để phân tích diễn biến theo thời gian.

Bắt đầu recording có thời hạn:

~~~bash
jcmd <pid> JFR.start name=incident settings=profile duration=2m filename=incident.jfr
~~~

Xem summary:

~~~bash
jfr summary incident.jfr
~~~

In event:

~~~bash
jfr print --events jdk.ExecutionSample,jdk.CPULoad,jdk.JavaMonitorWait,jdk.SocketRead incident.jfr
~~~

Xem các view có sẵn:

~~~bash
jfr view all-views incident.jfr
~~~

Có thể dùng JDK Mission Control để phân tích recording bằng giao diện đồ họa. JMC là công cụ phân tích riêng; kiểm tra cách cài và version của bản đang dùng.

settings=profile thường thu thập nhiều dữ liệu hơn default; cân nhắc thời lượng và overhead. JFR chỉ ghi event được bật và thỏa threshold. Không thấy event trong recording không chứng minh sự kiện không xảy ra.

## 16. Monitoring và process inspection

| Công cụ | Công dụng | Khi nào dùng |
|---|---|---|
| jps | Liệt kê instrumented JVM | Tìm process Java trong môi trường local |
| jstat | Theo dõi JVM statistics | Xem nhanh GC/heap theo chu kỳ |
| jconsole | GUI JMX monitoring/management | Xem memory, thread, MBean và runtime |
| jcmd | Diagnostic commands | Thu thập dữ liệu chi tiết từ JVM |
| jfr | Đọc/hiển thị Flight Recorder | Phân tích event timeline |
| jhsdb | Serviceability Agent và postmortem debugging | Điều tra process/core dump ở mức thấp |

Ví dụ jstat:

~~~bash
jstat -gcutil <pid> 1000 10
~~~

Lệnh lấy mẫu mỗi giây, 10 lần. Dùng đúng option và đọc header của output để hiểu từng cột; ý nghĩa phụ thuộc lệnh con và JDK.

Mở JConsole:

~~~bash
jconsole
~~~

JConsole kết nối tới JVM qua JMX. Remote JMX cần cấu hình authentication, TLS và network access phù hợp; không mở cổng quản trị JVM ra mạng công cộng.

jps chỉ liệt kê các JVM mà cơ chế instrumentation có thể nhìn thấy; không thay thế process listing của OS. jcmd -l thường hữu ích hơn khi cần danh sách JVM cho diagnostic command.

## 17. Các công cụ diagnostics khác và lưu ý

| Công cụ | Vai trò | Lưu ý |
|---|---|---|
| jstack | In Java thread stack | jcmd Thread.print thường linh hoạt hơn |
| jmap | Thông tin memory/heap của process | jcmd GC.* thường là điểm bắt đầu tốt hơn |
| jinfo | Thông tin cấu hình process | jcmd VM.* cung cấp các diagnostic command tương ứng |
| jhsdb | Phân tích JVM process/core ở mức thấp | Có thể cần quyền cao và JDK tương thích |
| jstatd | Daemon phục vụ monitoring từ xa qua jstat | Cần xem xét bảo mật và network exposure |
| jdb | Debugger dòng lệnh | Cổng JDWP phải được bảo vệ |
| jwebserver | HTTP server đơn giản phục vụ file tĩnh | Dùng cho phát triển/thử nghiệm, không thay web server production |

jstack, jmap và jinfo vẫn có trong JDK 26 tool reference, nhưng với quy trình mới nên ưu tiên xem lệnh jcmd tương ứng và tài liệu của JDK đang dùng. Không gọi các lệnh memory dump nặng chỉ để thu thập “cho đủ”.

jwebserver có thể khởi chạy server đơn giản:

~~~bash
jwebserver --port 8000 --directory public
~~~

Không dùng server đơn giản này để thay thế reverse proxy, authentication, TLS termination hoặc web server production.

## 18. Một số công cụ chuyên biệt khác

| Công cụ | Công dụng | Phạm vi |
|---|---|---|
| rmiregistry | Tạo RMI registry | Ứng dụng dùng Java RMI |
| serialver | Hiển thị serialVersionUID | Java serialization |
| javaw | Khởi chạy ứng dụng không mở console | Windows |
| kinit, klist, ktab | Quản lý Kerberos ticket/key table | Một số nền tảng, cấu hình enterprise |
| jabswitch, jaccessinspector, jaccesswalker | Công cụ Java Accessibility Bridge | Windows |

Không phải mọi JDK vendor/distribution đều cài mọi công cụ hoặc module tùy chọn. Một số lệnh chỉ có trên Windows; một số yêu cầu module JDK bổ sung hoặc native dependency. Luôn kiểm tra tool reference của đúng OS và JDK.

## 19. Bản đồ chọn công cụ theo câu hỏi

| Câu hỏi | Bắt đầu với | Sau đó nếu cần |
|---|---|---|
| Source compile không được? | javac --release, -Xlint | Kiểm tra dependency bằng jdeps |
| Không chạy được class/JAR? | java --version, java -cp/-jar | jar --list, javap -verbose |
| JAR chứa những file nào? | jar --list | jar --extract, jar --validate |
| Bytecode target là gì? | javap -verbose | So với runtime java --version |
| Dependency JDK nào cần? | jdeps --print-module-deps | Test reflection/services/JNI |
| API deprecated ở đâu? | jdeprscan | Thay API và compile/test trên target JDK |
| Cần custom runtime? | jdeps | jlink, rồi java --list-modules |
| Cần installer? | jpackage | Kiểm tra app image và cài thử trên OS đích |
| Certificate/trust lỗi? | keytool -list, -printcert | Kiểm tra truststore và TLS |
| Cần ký JAR? | jarsigner | jarsigner -verify |
| CPU cao? | OS process/thread metrics | jcmd, JFR, JMC |
| Ứng dụng treo? | Nhiều thread dump | jcmd Thread.print -l, JFR |
| Heap tăng/OOM? | GC.heap_info, GC logs | Histogram, heap dump, JFR |
| RSS cao nhưng heap ổn? | OS memory + NMT | Kiểm tra direct buffer/JNI/native |
| JVM crash? | Fatal error log và OS logs | jhsdb, debugger/core dump |

Bản đồ là điểm bắt đầu. Sau khi có bằng chứng, chọn lệnh cụ thể theo phiên bản, môi trường và tác động dự kiến.

## 20. Ví dụ end-to-end: dùng nhiều JDK tools trên một project nhỏ

Ví dụ này minh họa compile, run, archive, inspect, dependency analysis và API documentation. Chương trình tương thích Java 17+.

Cấu trúc:

~~~text
jdk-tool-map/
  src/
    com/acme/toolmap/ToolMapDemo.java
  out/
  build/
  docs/
~~~

Tệp src/com/acme/toolmap/ToolMapDemo.java:

~~~java
package com.acme.toolmap;

/**
 * Small application used to demonstrate the JDK tool workflow.
 */
public final class ToolMapDemo {

    private ToolMapDemo() {
    }

    /**
     * Starts the demonstration application.
     *
     * @param args command-line arguments (unused)
     */
    public static void main(String[] args) {
        System.out.println(
            "JDK_TOOL_MAP_OK java=" + Runtime.version().feature()
        );
    }
}
~~~

### Compile

~~~bash
javac --release 17 -d out src/com/acme/toolmap/ToolMapDemo.java
~~~

### Run from class directory

~~~bash
java -cp out com.acme.toolmap.ToolMapDemo
~~~

Stdout khi chạy bằng Java 17:

~~~text
JDK_TOOL_MAP_OK java=17
~~~

Trên JDK mới hơn, con số sẽ là feature version của runtime đang chạy. Vì vậy stdout phụ thuộc JDK được chọn; với Java 17 cụ thể, output ở trên là chính xác.

### Create executable JAR

~~~bash
jar --create --file build/tool-map-demo.jar --main-class com.acme.toolmap.ToolMapDemo -C out .
~~~

### Run JAR

~~~bash
java -jar build/tool-map-demo.jar
~~~

### Inspect archive

~~~bash
jar --list --file build/tool-map-demo.jar
jar --validate --file build/tool-map-demo.jar
~~~

### Inspect bytecode

~~~bash
javap -classpath build/tool-map-demo.jar -verbose com.acme.toolmap.ToolMapDemo
~~~

### Analyze dependencies

~~~bash
jdeps --summary build/tool-map-demo.jar
jdeps --print-module-deps build/tool-map-demo.jar
~~~

### Generate API docs

~~~bash
javadoc -d docs/api -sourcepath src -subpackages com.acme.toolmap
~~~

Các bước này tạo ra những bằng chứng khác nhau: compiler output, runtime output, archive listing, bytecode metadata, dependency report và HTML documentation. Một bước thành công không tự động chứng minh các bước khác đều đúng.

## 21. Quy trình CI/CD ghép các công cụ thành một pipeline

~~~text
Checkout source
     |
     v
Select pinned JDK + build tool
     |
     v
javac / Maven / Gradle compile
     |
     v
Unit and integration tests
     |
     v
jar / WAR / application package
     |
     v
jar --validate + jdeps + jdeprscan
     |
     v
Smoke test with java
     |
     v
jlink / jpackage if required
     |
     v
keytool / jarsigner / checksum / SBOM
     |
     v
Publish immutable artifact
     |
     v
Deploy same artifact digest
~~~

Không nhất thiết mọi project phải chạy mọi công cụ ở mọi lần build. Chọn gate theo loại artifact và yêu cầu rủi ro:

- Library: compile, test, jar, javadoc, dependency checks, signing và publish metadata.
- CLI/service: compile, test, package, smoke test, dependency scan và runtime compatibility.
- Modular application: jdeps, jlink, module validation và runtime smoke test.
- Desktop installer: jpackage trên từng OS/architecture, cài thử và kiểm tra native integration.
- Production service: JFR/diagnostic tooling và quy trình thu thập bằng chứng khi có incident.

Build tool như Maven/Gradle thường điều phối plugin và test lifecycle; JDK tools là công cụ nền tảng mà build tool hoặc script gọi. Ghi rõ toolchain và version để có thể tái lập.

## 22. Các lỗi thường gặp khi dùng JDK tools

| Lỗi | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| java và javac khác version | PATH/JAVA_HOME trỏ tới JDK khác nhau | Kiểm tra executable path và version |
| javac không tìm thấy class | Classpath/module path thiếu | Kiểm tra -cp, --module-path và dependency |
| java -jar báo thiếu Main-Class | Manifest không có entry point | Tạo lại JAR với --main-class hoặc cấu hình manifest |
| UnsupportedClassVersionError | Runtime cũ hơn class file | Dùng javap -verbose, nâng runtime hoặc compile bằng --release phù hợp |
| jdeps báo missing dependency | Không cung cấp dependency classpath/module path | Truyền đầy đủ dependency khi phân tích |
| Runtime image thiếu module | Dependency động không được phát hiện tĩnh | Review reflection/ServiceLoader/JNI và integration test |
| jpackage tạo package lỗi | Host OS thiếu prerequisite hoặc sai loại package | Build trên OS đích và kiểm tra tool requirements |
| jcmd attach thất bại | Sai user, PID namespace hoặc attach bị disable | Chạy đúng môi trường/user và đọc lỗi attach |
| JFR thiếu event cần tìm | Recording settings/threshold không bật event | Chọn settings/event phù hợp và ghi lại có kiểm soát |
| jarsigner verify thất bại | JAR bị sửa sau khi ký hoặc certificate không tin cậy | Ký sau cùng và kiểm tra certificate chain |

## 23. An toàn khi chạy công cụ

Một số lệnh chỉ đọc file; một số khác attach vào process, tạo dump lớn, mở network listener hoặc thay đổi artifact. Đánh giá tác động trước khi chạy.

- jcmd GC.heap_dump có thể tạo file lớn và chứa dữ liệu nhạy cảm.
- jcmd GC.class_histogram có thể ảnh hưởng hiệu năng tùy heap và số object.
- JFR profile có overhead; chọn thời lượng và settings phù hợp.
- Remote JMX/JDWP cần authentication, encryption và giới hạn network.
- jwebserver không phải web server production.
- keytool và jarsigner liên quan private key; bảo vệ keystore và password.
- Không expose command line, system properties, heap dump hoặc core dump có secret.
- Không chạy lệnh ghi/đóng gói trên artifact release đã ký nếu chưa có quy trình phát hành lại.

## 24. Checklist chọn và sử dụng JDK tool

- [ ] Xác định JDK vendor, full version, OS và architecture.
- [ ] Xác nhận đúng executable trong JAVA_HOME/bin hoặc PATH.
- [ ] Đọc --help hoặc manual của đúng JDK.
- [ ] Biết rõ input, output và tác động của lệnh.
- [ ] Phân biệt JDK tools với Maven, Gradle, IDE và JMC.
- [ ] Chọn công cụ theo câu hỏi và loại bằng chứng cần thu thập.
- [ ] Cung cấp đúng classpath/module path khi phân tích.
- [ ] Kiểm tra artifact bằng archive, bytecode và dependency tools phù hợp.
- [ ] Kiểm thử runtime image/installer trên OS đích.
- [ ] Bảo vệ key, dump, log và thông tin cấu hình.
- [ ] Ghi version, command, kết quả và artifact digest trong CI.
- [ ] Không suy ra toàn bộ chất lượng ứng dụng từ một lệnh thành công.

## 25. Ghi nhớ

- JDK là bộ công cụ phát triển, đóng gói và chẩn đoán; không chỉ là java và javac.
- jshell thử snippet; javac compile; java chạy ứng dụng.
- jar tạo và kiểm tra archive; javap đọc bytecode; javadoc tạo API docs.
- jdeps phân tích dependency; jdeprscan tìm API deprecated; jnativescan rà soát native access.
- jmod thao tác JMOD; jimage kiểm tra module image nội bộ; jlink tạo custom runtime.
- jpackage tạo application image hoặc native installer trên nền tảng đích.
- keytool quản lý key/certificate; jarsigner ký và verify JAR.
- jcmd truy vấn JVM; JFR/jfr phân tích event; jstat/jconsole theo dõi; jhsdb phục vụ postmortem.
- Maven và Gradle là build automation tools bên ngoài JDK.
- Không phải mọi tool có mặt trên mọi OS hoặc JDK distribution.
- Đọc manual của đúng version, kiểm tra input/output và đánh giá impact trước khi chạy.
- Chọn lệnh theo câu hỏi cần trả lời, giữ lại bằng chứng và xác nhận kết quả bằng test phù hợp.

## Tài liệu tham khảo chính thức

- [JDK 26 Tool Specifications — Complete Tool Index](https://docs.oracle.com/en/java/javase/26/docs/specs/man/index.html)
- [The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [The jar Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [The javap Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html)
- [The javadoc Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html)
- [The jshell Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jshell.html)
- [The jdeps Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [The jdeprscan Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeprscan.html)
- [The jnativescan Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jnativescan.html)
- [The jlink Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The jfr Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [The jstat Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jstat.html)
- [The keytool Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/keytool.html)
- [The jarsigner Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html)