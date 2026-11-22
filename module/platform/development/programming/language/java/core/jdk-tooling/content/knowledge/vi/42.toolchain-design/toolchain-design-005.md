# Chọn cách chẩn đoán lỗi trong Java toolchain

Khi Java build hoặc ứng dụng gặp lỗi, công cụ chẩn đoán nên được chọn theo triệu chứng và lớp đang lỗi. Lệnh **java --version** có thể xác nhận runtime, nhưng không giải thích vì sao Gradle chọn JDK khác, dependency không resolve, IDE biên dịch thành công còn CI thất bại, hay JVM bị treo.

Cách làm hiệu quả là bắt đầu bằng bằng chứng ít tác động, xác định lỗi nằm ở môi trường, compiler, build tool, dependency, IDE, CI hay JVM đang chạy, rồi chọn công cụ chuyên biệt cho lớp đó. Mỗi bước nên trả lời một câu hỏi cụ thể và giúp quyết định bước tiếp theo.

## 1. Chẩn đoán là chọn đúng lớp, không phải chạy thật nhiều lệnh

Một Java toolchain thường có nhiều lớp:

1. Hệ điều hành, architecture, filesystem và environment variables.
2. JDK cài đặt: java, javac, javadoc, jcmd và các công cụ khác.
3. Build engine: Gradle hoặc Maven, Wrapper, daemon và plugin.
4. Compiler/toolchain được build engine chọn.
5. Dependency, classpath, module path và annotation processor.
6. IDE, test runner và cấu hình chạy.
7. CI runner, container image và cache.
8. JVM runtime, garbage collector, thread, memory và native library.

Một lỗi có thể xuất hiện ở lớp này nhưng được báo ở lớp khác. Ví dụ lỗi “package does not exist” có thể do source sai package, dependency thiếu, classpath sai hoặc module chưa export package. Thêm JAR vào classpath ngay lập tức có thể che mất nguyên nhân nếu ứng dụng thực tế chạy bằng JPMS.

Trước khi chọn lệnh, hãy viết lại triệu chứng thành một câu hỏi có thể kiểm chứng:

- Máy có tìm thấy đúng javac không?
- Gradle daemon đang chạy bằng JDK nào?
- Compiler task dùng toolchain nào?
- Dependency nào được resolve và từ repository nào?
- JVM runtime có cùng version với compiler không?
- Lỗi chỉ xảy ra trong IDE, CI hay ở mọi môi trường?
- Process bị treo, thiếu memory hay chỉ chậm ở một task?

Một câu hỏi rõ giúp giới hạn phạm vi và tránh thu thập log không cần thiết.

## 2. Quy trình chọn công cụ theo thứ tự

Dùng quy trình sau cho một lỗi mới:

1. **Tái hiện:** ghi lại lệnh, thư mục chạy, thời điểm, exit code và phần output đầu tiên có ý nghĩa.
2. **Xác định phạm vi:** chỉ một máy, mọi developer, IDE, CI, một module, một test hay một process runtime?
3. **Thu thập baseline:** OS/architecture, java, javac, Gradle/Maven version, JDK path và cấu hình toolchain.
4. **Phân loại lớp lỗi:** môi trường, compile, dependency, module, test, IDE, CI hoặc runtime.
5. **Chọn một phép đo nhỏ nhất:** lệnh cần thiết để xác nhận hoặc loại trừ giả thuyết hiện tại.
6. **So sánh với môi trường hoạt động tốt:** dùng cùng lệnh, cùng project revision và cùng dữ liệu đầu vào.
7. **Tăng mức chi tiết khi cần:** stack trace, log --info, dependency tree, module resolution hoặc JVM diagnostics.
8. **Đưa ra kết luận có bằng chứng:** ghi rõ nguyên nhân đã xác nhận, điều đã loại trừ và bước sửa tiếp theo.

Không thay đổi đồng thời JDK, dependency, plugin và build flags trong lúc chẩn đoán. Nếu nhiều yếu tố đổi cùng lúc, sẽ khó xác định yếu tố nào làm lỗi biến mất.

## 3. Bảng chọn nhanh theo triệu chứng

| Triệu chứng | Câu hỏi cần trả lời | Công cụ nên dùng trước |
|---|---|---|
| java hoặc javac không tìm thấy | Shell đang phân giải executable ở đâu? | Get-Command, where.exe, command -v, PATH, JAVA_HOME |
| java đúng nhưng compiler sai | Runtime và compiler có đến từ cùng JDK không? | java --version, javac --version, đường dẫn executable |
| Build dùng sai JDK | Launcher JVM, daemon JVM hay compiler toolchain đang khác? | gradle --version, javaToolchains, mvn -version, Maven toolchains |
| Lỗi cú pháp hoặc API khi compile | Compiler báo lỗi đầu tiên ở file/dòng nào? | javac diagnostic, --release, -verbose |
| Không tìm thấy class/package | Dependency có trong classpath/module path không? | Gradle dependency insight, mvn dependency:tree, jdeps |
| Module không resolve | Module path và descriptor có khớp không? | jar --describe-module, java --show-module-resolution |
| Chỉ IDE lỗi | IDE đang dùng SDK, runner và build model nào? | Project SDK, Gradle JVM, Maven Runner, IDE build log |
| Chỉ CI lỗi | Runner, image, JDK và environment khác gì local? | Version report, action log, image digest, CI environment |
| Một test lỗi | Test runner có fork JVM hoặc property khác không? | Chạy riêng test, test report, JVM args của test worker |
| Ứng dụng treo | Thread đang chạy, block hay deadlock? | jcmd PID Thread.print |
| CPU cao hoặc latency tăng | CPU, lock, allocation hay I/O là nút thắt? | JFR, JDK Mission Control |
| Memory tăng hoặc GC nhiều | Heap, allocation hay native memory tăng? | JFR, jcmd PID GC.heap_info, GC log |
| JVM crash | Exception Java hay process crash ở native layer? | hs_err_pid log, OS crash report, core dump |

Bảng này giúp chọn điểm bắt đầu. Nếu kết quả không trả lời câu hỏi, hãy chuyển sang lớp tiếp theo thay vì lặp lại cùng một lệnh.

## 4. Xác minh JDK và môi trường shell

Đây là bước đầu tiên khi lỗi liên quan đến Java version, compiler hoặc toolchain.

### 4.1. Windows PowerShell

~~~powershell
Get-Command java -All
Get-Command javac -All
where.exe java
where.exe javac

$env:JAVA_HOME
java --version
javac --version
~~~

Get-Command cho biết PowerShell sẽ chạy executable nào và có thể hiển thị nhiều kết quả trùng tên. where.exe liệt kê các file khớp trong PATH. Lệnh where không có phần .exe trong PowerShell thường là alias của Where-Object, nên dùng where.exe để tránh nhầm.

### 4.2. Linux và macOS

~~~bash
command -v java
command -v javac
type -a java
type -a javac

printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
java --version
javac --version
~~~

command -v cho biết shell phân giải command nào; type -a có thể cho thấy alias, function và nhiều executable cùng tên.

### 4.3. Kiểm tra runtime properties

~~~bash
java -XshowSettings:properties -version
~~~

Tìm các thuộc tính:

- java.version: product version.
- java.runtime.version: runtime version đầy đủ, thường gồm build number.
- java.vendor: vendor string do runtime cung cấp.
- java.vm.name và java.vm.version: VM identity.
- java.home: Java home thực tế của JVM.
- os.name, os.arch: hệ điều hành và architecture.
- file.encoding: charset mặc định mà JVM báo cáo.

JAVA_HOME là cấu hình môi trường; java.home là property của JVM đang chạy. Hai đường dẫn thường liên quan nhưng không nên mặc định chúng giống nhau. Tương tự, java --version và javac --version phải được kiểm tra riêng vì shell có thể phân giải chúng từ hai thư mục khác nhau.

Nếu javac không có nhưng java có, máy có thể chỉ cài JRE/runtime image hoặc PATH trỏ đến runtime thay vì JDK. Xác nhận executable path và kiểm tra thư mục JAVA_HOME/bin có javac hay không.

### 4.4. Các biến môi trường có thể làm thay đổi kết quả

Ngoài JAVA_HOME và PATH, hãy xem có các biến ảnh hưởng đến launcher hoặc build không:

- JDK_JAVA_OPTIONS: thêm option vào Java launcher.
- JAVA_TOOL_OPTIONS và _JAVA_OPTIONS: có thể thêm JVM options/agent.
- GRADLE_OPTS và org.gradle.jvmargs: ảnh hưởng JVM chạy Gradle.
- MAVEN_OPTS: ảnh hưởng JVM chạy Maven.
- MAVEN_ARGS: có thể thêm đối số Maven từ môi trường.
- CLASSPATH: có thể ảnh hưởng cách chạy Java không dùng module path hoặc không truyền classpath rõ ràng.

Không đăng toàn bộ giá trị biến môi trường lên issue hoặc log công khai. Một số biến có thể chứa token, proxy credential, đường dẫn nội bộ hoặc JVM agent không nên tiết lộ. Chỉ ghi tên biến liên quan và giá trị đã được rà soát/che thông tin nhạy cảm.

## 5. Phân biệt JVM chạy build với JDK dùng để compile

Một trong các lỗi chẩn đoán thường gặp là thấy java --version đúng rồi kết luận toàn bộ build dùng đúng JDK.

### 5.1. Gradle

Bắt đầu bằng:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

--version hiển thị Gradle version, launcher JVM và daemon JVM. javaToolchains liệt kê các JDK Gradle phát hiện cùng metadata của chúng.

Các khái niệm cần tách biệt:

- **Launcher JVM:** JVM chạy Gradle client.
- **Daemon JVM:** JVM chạy Gradle build daemon.
- **Java compiler toolchain:** JDK dùng cho task compile.
- **Test/runtime launcher:** JDK dùng để chạy test hoặc JavaExec.

Một project có thể chạy Gradle trên JDK 24 nhưng compile bằng JDK 17. Điều này hợp lệ nếu build được cấu hình như vậy. Nếu lỗi chỉ xuất hiện ở compile, kiểm tra compiler toolchain thay vì chỉ đổi JAVA_HOME.

Có thể xem log task cụ thể:

~~~bash
./gradlew compileJava --info
~~~

Nếu nghi ngờ task dùng sai toolchain, xem cấu hình java.toolchain, các task JavaCompile, Test, JavaExec và kết quả javaToolchains.

### 5.2. Maven

~~~bash
mvn -version
mvn -e -DskipTests compile
~~~

mvn -version cho biết Maven version và JVM chạy Maven. Nếu project dùng Maven Toolchains, compiler plugin có thể dùng một JDK khác. Kiểm tra toolchains.xml, Maven Toolchains Plugin và log lựa chọn toolchain.

Khi cần dependency tree:

~~~bash
mvn dependency:tree
~~~

Để giới hạn một dependency:

~~~bash
mvn dependency:tree -Dincludes=org.example:library
~~~

mvn -version không chứng minh compiler toolchain được chọn đúng. Cần đối chiếu runtime của Maven, cấu hình toolchain và compiler plugin.

### 5.3. --release không phải cách chọn JDK

Ví dụ:

~~~bash
javac --release 17 Main.java
~~~

--release 17 giới hạn language rules, class-file target và API Java SE được phép dùng cho release 17. Nó không tự chọn JDK 17 để chạy compiler. Một compiler JDK mới hơn vẫn có thể biên dịch với --release 17.

Vì vậy, khi điều tra compatibility, cần kiểm tra cả compiler JDK thực tế và --release/toolchain target.

## 6. Khi lỗi nằm ở compiler hoặc source code

Bắt đầu từ lỗi đầu tiên trong compiler output. Các lỗi phía sau đôi khi chỉ là hậu quả của lỗi đầu tiên.

Chạy lại task compile cụ thể để giảm log:

Gradle:

~~~bash
./gradlew compileJava --stacktrace
~~~

Maven:

~~~bash
mvn -e -DskipTests compile
~~~

Nếu cần xem compiler đọc file hoặc tìm class như thế nào, có thể dùng javac -verbose trên một compile tái hiện nhỏ. Không nên tự dựng một command javac khác hoàn toàn với build tool rồi kết luận source có vấn đề; command thủ công có thể bỏ sót annotation processor, compiler arguments, classpath hoặc generated source.

Kiểm tra các điểm sau:

- Source level và target release có khớp không?
- Import/package declaration có đúng không?
- Generated source đã được tạo trước compile chưa?
- Annotation processor có được khai báo và resolve đúng version không?
- Compiler có nhận đúng classpath/module path không?
- IDE và build tool có cùng compiler options không?

Nếu lỗi invalid source release, release version not supported hoặc API không tồn tại, đối chiếu compiler JDK với --release trước khi sửa code.

## 7. Khi lỗi nằm ở dependency hoặc module

Đừng thêm một dependency khác chỉ để làm hết lỗi. Trước tiên xác định dependency thực tế được resolve.

### 7.1. Gradle dependency diagnostics

~~~bash
./gradlew dependencies --configuration compileClasspath
~~~

Xem vì sao một version được chọn:

~~~bash
./gradlew dependencyInsight --dependency guava --configuration compileClasspath
~~~

Thay guava bằng tên dependency cần điều tra. Dùng đúng configuration, ví dụ runtimeClasspath, testCompileClasspath hoặc configuration riêng của project.

### 7.2. Maven dependency diagnostics

~~~bash
mvn dependency:tree
mvn dependency:resolve
~~~

dependency:tree cho thấy dependency hierarchy sau khi Maven resolve. dependency:resolve giúp xác nhận các dependency cần thiết có tải được và version nào được chọn. Nếu lỗi chỉ liên quan một artifact, dùng -Dincludes=groupId:artifactId với dependency:tree.

### 7.3. Module path

Nếu lỗi liên quan JPMS, chọn công cụ theo câu hỏi:

~~~bash
jar --describe-module --file lib/example.jar
java --module-path lib --describe-module com.example.module
java --show-module-resolution --module-path lib --module com.example.app
jdeps --module-path lib --check com.example.app
~~~

- jar --describe-module: xem module descriptor trong JAR.
- java --describe-module: xem module được tìm thấy trên module path.
- --show-module-resolution: xem dependency nào được resolve khi khởi động.
- jdeps --check: xem descriptor và module dependency graph.

Nếu module được tìm thấy nhưng package không visible, xem exports. Nếu module không đọc được dependency, xem requires. Nếu lỗi do deep reflection, kiểm tra opens và quyền truy cập runtime. Sửa đúng descriptor hoặc module path thay vì thêm JAR vào classpath một cách ngẫu nhiên.

## 8. Khi lỗi chỉ xuất hiện trong IDE

IDE có thể giữ nhiều cấu hình Java độc lập:

- Project SDK/JDK.
- Language level của project hoặc module.
- JDK dùng cho Gradle import/build.
- JRE/JDK dùng cho Maven runner.
- JDK của test runner và run configuration.
- Compiler settings, annotation processor và generated-source directories.

Nếu command line build thành công nhưng IDE báo lỗi:

1. Kiểm tra Project SDK và module SDK.
2. Kiểm tra language level và bytecode target.
3. Với Gradle, kiểm tra Gradle JVM và Wrapper được IDE dùng.
4. Với Maven, kiểm tra JRE của Maven Runner.
5. Kiểm tra run/test configuration có truyền environment variables hoặc VM options riêng không.
6. Refresh/sync project model sau khi thay đổi cấu hình build.

Nếu IDE build thành công nhưng Wrapper thất bại, chạy đúng Wrapper ở terminal và đọc lỗi đầu tiên. IDE có thể đang dùng JDK khác hoặc cache/generated source khác. Không kết luận rằng IDE đang dùng đúng toolchain chỉ vì editor không gạch đỏ.

## 9. Khi lỗi chỉ xuất hiện trên CI hoặc container

So sánh môi trường thực tế, không chỉ so sánh file cấu hình.

Trong CI, ghi lại các thông tin không nhạy cảm:

~~~bash
java --version
javac --version
./gradlew --version
mvn -version
~~~

Và xác định:

- Runner OS, architecture và image.
- JDK distribution/version được cài ở step nào.
- Wrapper version và action/plugin version.
- Container image tag và digest nếu có.
- Working directory, checkout revision và submodule state.
- Environment variables ảnh hưởng build, sau khi che credential.
- Cache key và trạng thái cache.
- Dependency repository, proxy và certificate chain.

Nếu build local thành công nhưng CI lỗi, chạy cùng Wrapper command trên cùng JDK feature/update và cùng project revision. Nếu vẫn khác, so sánh dependency resolution, architecture, filesystem permissions, locale/timezone và network.

Không dùng cache clear như bước đầu tiên. Trước hết kiểm tra cache key và log resolve. Xóa cache có thể làm mất bằng chứng và kéo dài thời gian build; chỉ thực hiện khi có dấu hiệu cache stale hoặc corruption.

## 10. Chẩn đoán test và runtime exception

Nếu compile thành công nhưng test thất bại, tách test runner khỏi compiler:

- Test có chạy trong forked JVM không?
- Test worker dùng JDK nào?
- Test có nhận system properties, environment variables, module opens hoặc agent riêng không?
- Lỗi có phụ thuộc thứ tự chạy hoặc test song song không?
- Có resource ngoài JVM như database, file, port hoặc service không?

Chạy riêng test đang lỗi:

Gradle:

~~~bash
./gradlew test --tests "com.example.MyTest" --info
~~~

Maven Surefire:

~~~bash
mvn -Dtest=MyTest test -e
~~~

Với exception runtime, giữ nguyên stack trace đầu tiên, exception cause và tên thread. Xác định exception phát sinh trong code ứng dụng, framework, JDK hay native library. Đừng bỏ qua Caused by đầu tiên để chỉ sửa dòng cuối cùng.

Nếu process crash ngoài luồng exception Java, tìm hs_err_pid*.log, Windows Event Viewer hoặc core dump của hệ điều hành. JVM crash và Java exception là hai loại sự cố khác nhau.

## 11. Chẩn đoán process treo, deadlock hoặc phản hồi chậm

Nếu JVM vẫn chạy nhưng không phản hồi, bắt đầu bằng thread dump:

~~~bash
jcmd -l
jcmd 12345 Thread.print
~~~

Thay 12345 bằng PID thực tế. jcmd -l liệt kê các JVM mà công cụ nhìn thấy. Thread.print in thread stack traces và có thể kèm thông tin lock nếu tùy chọn được hỗ trợ.

Một thread dump là ảnh chụp tại một thời điểm. Nếu nghi ngờ deadlock hoặc thread bị block, lấy thêm hai hoặc ba dump cách nhau một khoảng ngắn, rồi so sánh stack trace:

- Stack có giữ nguyên ở cùng một dòng không?
- Thread đang BLOCKED, WAITING hay chạy CPU?
- Có monitor/lock owner nào lặp lại không?
- Thread pool có cạn worker không?
- Có nhiều thread chờ cùng một dependency bên ngoài không?

jcmd cần chạy trên cùng máy với JVM và cùng effective user/group identity đã khởi chạy JVM. Trong container, PID namespace có thể khiến host PID khác PID bên trong container. Nếu không thấy process, kiểm tra đúng container và namespace trước khi kết luận attach bị tắt.

## 12. Chẩn đoán CPU, latency và memory bằng JFR

Khi triệu chứng là CPU cao, latency tăng hoặc allocation nhiều, JDK Flight Recorder (JFR) thường cung cấp bằng chứng tốt hơn một stack trace đơn lẻ.

Bắt đầu một recording có thời hạn:

~~~bash
jcmd 12345 JFR.start name=ToolchainDiag settings=default duration=60s filename=toolchain-diag.jfr
~~~

Sau khi recording hoàn tất:

~~~bash
jfr summary toolchain-diag.jfr
jfr print --events jdk.CPULoad,jdk.ExecutionSample toolchain-diag.jfr
~~~

Dùng jcmd 12345 help JFR.start để kiểm tra các option được JVM hiện tại hỗ trợ. Template default phù hợp cho thu thập cơ bản; profile ghi nhiều dữ liệu hơn và có thể tạo overhead cao hơn. Chọn recording ngắn, giới hạn phạm vi và kiểm tra dung lượng đĩa.

Để xem heap summary:

~~~bash
jcmd 12345 GC.heap_info
~~~

Có thể đối chiếu với GC log nếu ứng dụng đã được khởi động với logging phù hợp:

~~~text
-Xlog:gc*:file=gc.log:time,uptime,level,tags
~~~

Không tạo heap dump ngay khi thấy memory tăng. Heap dump có thể lớn, tốn thời gian, tạo pause và chứa dữ liệu nhạy cảm như token, nội dung request hoặc thông tin cá nhân. Nếu thực sự cần, xác định người nhận, dung lượng trống, vị trí lưu an toàn và chính sách giữ/xóa trước khi chạy GC.heap_dump.

Tương tự, GC.class_histogram và các diagnostic command khác có impact riêng. Dùng jcmd <pid> help <command> để đọc mô tả và impact của đúng lệnh trước khi thực hiện trên production.

## 13. Chọn mức độ chi tiết và tác động

Không phải lúc nào log chi tiết nhất cũng là lựa chọn tốt nhất.

| Mức | Ví dụ | Khi nào dùng |
|---|---|---|
| 1. Read-only baseline | java --version, javac --version, gradle --version, mvn -version | Luôn bắt đầu ở đây |
| 2. Log task/build | Gradle --stacktrace/--info, Maven -e | Cần biết task hoặc plugin lỗi ở đâu |
| 3. Resolve detail | Dependency tree, toolchain listing, module resolution | Lỗi version, dependency, compiler hoặc module |
| 4. Process snapshot | jcmd Thread.print, GC.heap_info | Process đang chạy bị treo, chậm hoặc dùng memory bất thường |
| 5. Recording/profiling | JFR, JDK Mission Control | Cần phân tích CPU, latency, allocation và GC theo thời gian |
| 6. Heap/core dump | GC.heap_dump, OS core dump | Điều tra sâu khi đã có lý do và kế hoạch lưu trữ |

Tăng mức chi tiết khi bằng chứng hiện tại không đủ. Nếu một bước đã xác nhận nguyên nhân, dừng thu thập thêm dữ liệu không cần thiết.

### 13.1. Bảo vệ thông tin trong diagnostic output

- Gradle --debug tạo log rất lớn và có thể lộ thông tin nhạy cảm.
- Maven -X có thể in cấu hình repository, proxy và đường dẫn nội bộ.
- Build Scan có thể gửi dữ liệu build đến dịch vụ bên ngoài; chỉ dùng khi chính sách tổ chức cho phép.
- JFR, thread dump, heap dump và core dump có thể chứa dữ liệu ứng dụng.
- Không đính kèm settings.xml, environment dump, credential hoặc toàn bộ log vào issue công khai.
- Che token, password, URL có credential, username và thông tin khách hàng trước khi chia sẻ.

Chỉ thu thập dữ liệu cần cho giả thuyết đang kiểm tra và giới hạn quyền truy cập vào file chẩn đoán.

## 14. Ví dụ Java 17: tạo báo cáo nhận diện toolchain

Khi cần so sánh hai môi trường, có thể chạy một chương trình nhỏ trong cả hai môi trường. Chương trình này báo runtime identity, VM, feature version, OS và encoding. Nó không tự xác định compiler đang được shell chọn; vì vậy vẫn phải chạy javac --version riêng.

Tạo ToolchainReport.java:

~~~java
public final class ToolchainReport {
    private static void print(String key, String value) {
        System.out.println(key + "=" + value);
    }

    public static void main(String[] args) {
        Runtime.Version version = Runtime.version();

        print("JAVA_VERSION", System.getProperty("java.version"));
        print("JAVA_RUNTIME_VERSION", System.getProperty("java.runtime.version"));
        print("JAVA_VENDOR", System.getProperty("java.vendor"));
        print("JAVA_VM", System.getProperty("java.vm.name"));
        print("JAVA_VM_VERSION", System.getProperty("java.vm.version"));
        print("JAVA_FEATURE", Integer.toString(version.feature()));
        print("OS", System.getProperty("os.name"));
        print("OS_ARCH", System.getProperty("os.arch"));
        print("FILE_ENCODING", System.getProperty("file.encoding"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 đã chọn:

~~~bash
javac --release 17 -d out ToolchainReport.java
java -cp out ToolchainReport
~~~

Trên Windows với Amazon Corretto 17.0.15+6-LTS, output đã kiểm thử:

~~~text
JAVA_VERSION=17.0.15
JAVA_RUNTIME_VERSION=17.0.15+6-LTS
JAVA_VENDOR=Amazon.com Inc.
JAVA_VM=OpenJDK 64-Bit Server VM
JAVA_VM_VERSION=17.0.15+6-LTS
JAVA_FEATURE=17
OS=Windows 11
OS_ARCH=amd64
FILE_ENCODING=UTF-8
~~~

Compiler version của lần chạy này:

~~~text
javac 17.0.15
~~~

Khi so sánh hai máy, hãy lưu output của chương trình cùng output java --version, javac --version, gradle --version hoặc mvn -version. So sánh theo từng trường để thấy khác biệt ở runtime, compiler hay build engine.

## 15. Lỗi thường gặp khi chọn công cụ chẩn đoán

| Sai lầm | Vì sao không hiệu quả | Cách chọn lại |
|---|---|---|
| Chỉ chạy java --version | Không cho biết javac, daemon hoặc compiler toolchain | Kiểm tra riêng runtime, compiler và build tool |
| Chạy javac thủ công để kết luận Gradle compile sai | Bỏ qua compiler args, processors và classpath của Gradle | Xem task log và toolchain của Gradle |
| Thấy mvn -version đúng rồi kết luận Maven compiler dùng JDK đó | Maven Toolchains có thể chọn JDK khác | Kiểm tra toolchains.xml và compiler plugin |
| Chạy --debug ngay từ đầu | Log lớn, khó đọc và có thể lộ secrets | Dùng --stacktrace hoặc --info trước |
| Xóa toàn bộ cache để sửa dependency | Có thể che dấu lỗi resolution và làm mất bằng chứng | Xem dependency tree, cache key và repository trước |
| Tạo heap dump khi chỉ thấy memory tăng | Có thể gây pause, tốn disk và chứa dữ liệu nhạy cảm | Bắt đầu với JFR và GC.heap_info |
| Dùng thread dump một lần để kết luận deadlock | Một snapshot không cho thấy thread có đang tiến triển không | So sánh nhiều dump theo thời gian |
| Dùng --add-opens để sửa mọi lỗi module | Có thể che sai requires hoặc exports | Xác định lỗi readability, export hay reflection |
| Chỉ kiểm tra IDE | IDE có thể dùng SDK và runner khác terminal | So sánh command line và IDE build logs |
| Chỉ kiểm tra local | CI có thể khác OS, architecture, JDK hoặc network | Thu thập cùng baseline ở runner |
| Gửi toàn bộ log ra issue công khai | Có thể lộ token, đường dẫn và dữ liệu ứng dụng | Lọc, che thông tin và chỉ gửi đoạn liên quan |

## 16. Mẫu ghi nhận kết quả chẩn đoán

Một báo cáo ngắn có cấu trúc giúp người khác tái hiện lỗi:

~~~text
Problem:
- Triệu chứng và thông báo lỗi đầu tiên.

Scope:
- Local / IDE / CI / container / production.
- OS và architecture.

Reproduction:
- Git revision.
- Working directory.
- Exact command.
- Exit code.

Toolchain:
- java --version
- javac --version
- Gradle/Maven version
- Launcher JVM / Daemon JVM / Compiler toolchain nếu liên quan.

Evidence:
- Log hoặc diagnostic command đã chạy.
- Kết quả quan sát được.
- Giả thuyết đã xác nhận hoặc loại trừ.

Conclusion:
- Lớp gây lỗi và bằng chứng.
- Thay đổi tối thiểu cần thực hiện.
- Cách xác nhận sau khi sửa.
~~~

Không ghi mật khẩu, token, nội dung secret, toàn bộ environment hoặc heap dump vào báo cáo này.

## 17. Checklist chọn cách chẩn đoán

- [ ] Đã mô tả triệu chứng thành câu hỏi có thể kiểm chứng.
- [ ] Đã ghi lệnh, working directory, revision và exit code.
- [ ] Đã xác định lỗi chỉ ở local, IDE, CI hay runtime.
- [ ] Đã kiểm tra riêng java và javac.
- [ ] Đã phân biệt launcher JVM, daemon JVM và compiler toolchain.
- [ ] Đã chọn dependency/module diagnostic nếu lỗi nằm ở resolve.
- [ ] Đã kiểm tra IDE runner hoặc CI environment nếu lỗi chỉ xảy ra ở một nơi.
- [ ] Đã dùng thread dump cho process treo và JFR cho vấn đề theo thời gian.
- [ ] Đã kiểm tra impact trước diagnostic command có thể pause hoặc tạo file lớn.
- [ ] Đã che dữ liệu nhạy cảm trong log và dump.
- [ ] Đã ghi bằng chứng và bước xác nhận sau khi sửa.
- [ ] Đã dừng thu thập khi nguyên nhân đã được xác nhận.

## 18. Ghi nhớ

Chọn công cụ theo câu hỏi và lớp lỗi. Dùng java/javac để kiểm tra JDK, Gradle/Maven để kiểm tra build engine và compiler toolchain, dependency tree để kiểm tra resolution, module diagnostics để kiểm tra JPMS, IDE/CI logs để tìm khác biệt môi trường, và jcmd/JFR để điều tra JVM đang chạy.

Bắt đầu với phép đo ít tác động, chỉ tăng độ chi tiết khi bằng chứng chưa đủ. Một chẩn đoán tốt phải tái hiện được, chỉ ra lớp gây lỗi và cung cấp cách xác nhận sau khi sửa.

Tài liệu tham khảo:

- [Oracle Java SE 17 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/17/troubleshoot/diagnostic-tools.html)
- [Oracle Java SE 17 — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [Oracle Java SE 17 — The javac Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Gradle — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html)
- [Gradle — Command-Line Interface and Logging](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Apache Maven — Dependency Plugin Usage](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [Apache Maven — Configuring Maven](https://maven.apache.org/configure.html)
- [Apache Maven — Command-Line Interface](https://maven.apache.org/ref/current/maven-embedder/cli.html)