# Kiểm kê JDK thực tế của máy phát triển, CI và môi trường chạy

## 1. Vì sao phải kiểm kê JDK đang thực sự được sử dụng?

Trong một hệ thống Java, câu trả lời cho câu hỏi “dự án đang dùng JDK nào?” thường không phải là một phiên bản duy nhất. Máy phát triển có thể cài nhiều JDK; terminal chọn một bản theo PATH; IDE lại dùng Project SDK hoặc Gradle JVM riêng; Gradle daemon chạy trên một JVM nhưng Java toolchain biên dịch bằng JDK khác; CI chạy trong runner hoặc container riêng; còn ứng dụng production có thể chạy trong một image chứa runtime khác với máy build.

Nếu chỉ đọc cấu hình JAVA_HOME hoặc chạy java -version ở một terminal, ta mới biết một phần của hệ thống. Thông tin đó chưa đủ để kết luận JDK mà compiler, test process hay ứng dụng đang dùng.

Kiểm kê JDK thực tế là việc thu thập bằng chứng cho từng môi trường và từng tiến trình có liên quan đến vòng đời ứng dụng:

~~~text
Máy phát triển
  ├─ Terminal / shell
  ├─ IDE và cấu hình chạy ứng dụng
  └─ Gradle hoặc Maven được IDE khởi chạy

CI
  ├─ Runner / agent
  ├─ Job container hoặc build container
  └─ Compiler, test process và công cụ đóng gói

Môi trường chạy
  ├─ Local / development
  ├─ Test / staging
  └─ Production và từng replica / instance
~~~

Mục tiêu là xác định phiên bản, nhà cung cấp, đường dẫn cài đặt, kiến trúc và vai trò của từng JDK/JRE; sau đó đối chiếu chúng với phiên bản đã khai báo trong build và phiên bản mà ứng dụng yêu cầu.

## 2. Phân biệt các JDK/JVM trong cùng một quy trình

Trước khi thu thập thông tin, cần phân biệt các vai trò sau. Chúng có thể trùng phiên bản nhưng không mặc nhiên là một.

| Vai trò | Ý nghĩa | Nơi cần kiểm tra |
|---|---|---|
| JDK của terminal | JDK được tìm thấy khi chạy lệnh java hoặc javac trong shell hiện tại. | PATH, JAVA_HOME và executable thực tế. |
| JDK của IDE | SDK được IDE dùng để phân tích mã nguồn, biên dịch hoặc chạy cấu hình ứng dụng. | Project SDK, module SDK, run configuration và IDE runtime. |
| JVM chạy build tool | JVM khởi chạy Gradle hoặc Maven. Với Gradle, cần chú ý cả daemon JVM. | gradlew --version, mvn -version, cấu hình IDE và build properties. |
| Java toolchain | JDK được build tool chọn cho compile, test, javadoc hoặc task cụ thể. | Gradle toolchain, Maven Toolchains và cấu hình compiler/test plugin. |
| JVM của test process | JVM thực thi test khi plugin tạo tiến trình fork riêng. | Cấu hình test task, Surefire/Failsafe và log của test process. |
| JVM của ứng dụng | JVM thực thi tiến trình ứng dụng thực tế. | Tiến trình trên host, trong container hoặc trên application server. |
| Bytecode target | Phiên bản class file mà compiler tạo ra. | --release, compiler configuration hoặc kiểm tra class file. |

Ví dụ, một máy có thể có JDK 21 trong terminal, Gradle daemon chạy bằng JDK 21, compiler toolchain dùng JDK 17 và production chạy một runtime Java 17. Đây là một cấu hình có thể có chủ đích nếu dự án đặt mục tiêu bytecode phù hợp. Chỉ nhìn thấy JDK 21 trong terminal không đủ để kết luận ứng dụng đã được biên dịch hoặc đang chạy trên Java 21.

### 2.1. JDK và runtime không phải lúc nào cũng giống nhau

JDK cung cấp compiler và các công cụ phát triển như javac, javadoc, jcmd. Runtime dùng để chạy ứng dụng cần JVM và các module runtime cần thiết, nhưng có thể không chứa compiler. Một số image triển khai chỉ cài runtime tối giản hoặc runtime tùy biến được tạo bằng jlink.

Vì vậy:

- java -version cho biết runtime được gọi qua lệnh java trong môi trường hiện tại.
- javac -version cho biết compiler được gọi qua lệnh javac; lệnh này có thể không tồn tại trên image runtime tối giản.
- Đường dẫn JAVA_HOME là một giá trị cấu hình; cần kiểm tra executable thực tế được shell hoặc tiến trình sử dụng.
- java.home trong system properties giúp xác định Java home của JVM đang chạy tiến trình đó.

Không nên xem việc thiếu javac trên production là lỗi nếu production chỉ cần chạy artifact. Cần xác định đúng vai trò của môi trường trước khi đánh giá.

### 2.2. Phiên bản cần ghi nhận

Không chỉ ghi một số phiên bản lớn như Java 17 hoặc Java 21. Khi có thể, hãy lưu:

- Phiên bản Java và runtime đầy đủ, bao gồm update/build number.
- Nhà cung cấp JDK, ví dụ Oracle, Eclipse Temurin, Amazon Corretto, Microsoft Build of OpenJDK hoặc bản phân phối khác.
- Tên JVM và loại VM nếu có.
- Đường dẫn java.home và đường dẫn executable thực tế.
- Kiến trúc hệ điều hành và JVM, ví dụ x86_64 hoặc aarch64.
- Hệ điều hành, image/container và định danh môi trường.
- Thời điểm thu thập và phiên bản commit/artifact đang được kiểm tra.

Hai máy cùng hiển thị Java 21 vẫn có thể khác nhà cung cấp, bản cập nhật, kiến trúc hoặc đường dẫn runtime. Những khác biệt này có thể quan trọng khi điều tra lỗi native library, TLS, hiệu năng hoặc hành vi JVM.

## 3. Kiểm kê trên máy phát triển

Máy phát triển thường có nhiều JDK cài song song để phục vụ các dự án khác nhau. Việc kiểm kê nên thực hiện trong terminal mà lập trình viên thực sự dùng, sau đó lặp lại trong IDE nếu build hoặc chạy ứng dụng từ IDE.

### 3.1. Kiểm tra trên Windows PowerShell

Chạy các lệnh sau trong PowerShell:

~~~powershell
Write-Output "JAVA_HOME=$env:JAVA_HOME"
Get-Command java -All | Select-Object CommandType, Source
Get-Command javac -All | Select-Object CommandType, Source
where.exe java
where.exe javac
java -version
javac -version
java -XshowSettings:properties -version 2>&1 |
    Select-String 'java.home|java.version|java.vendor|java.runtime.version|java.vm.name|os.arch'
~~~

Các lệnh trên trả lời những câu hỏi khác nhau:

- JAVA_HOME cho biết biến môi trường đang được cấu hình trong phiên PowerShell.
- Get-Command và where.exe cho biết các executable có thể được tìm thấy qua cơ chế phân giải lệnh/PATH.
- java -version và javac -version cho biết phiên bản của executable được chọn đầu tiên.
- java -XshowSettings:properties cung cấp thêm java.home, java.vendor, java.runtime.version, tên VM và kiến trúc.

Nếu JAVA_HOME trỏ đến một thư mục nhưng where.exe java trả về executable ở thư mục khác, cần kiểm tra thứ tự PATH. Không tự sửa biến môi trường ngay trong bước kiểm kê; trước hết ghi lại cả giá trị khai báo lẫn kết quả thực tế.

### 3.2. Kiểm tra trên Linux và macOS

Trong shell Bash hoặc Zsh:

~~~bash
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
command -v java
type -a java
command -v javac
type -a javac
java -version
javac -version
java -XshowSettings:properties -version 2>&1 |
  grep -E 'java.home|java.version|java.vendor|java.runtime.version|java.vm.name|os.arch'
~~~

Trên Linux, có thể xác định đường dẫn sau khi giải quyết symbolic link:

~~~bash
readlink -f "$(command -v java)"
readlink -f "$(command -v javac)"
~~~

Trên macOS, có thể liệt kê các JDK mà hệ điều hành nhận diện:

~~~bash
/usr/libexec/java_home -V
/usr/libexec/java_home
~~~

Lệnh java_home -V liệt kê các JDK được macOS nhận diện; lệnh không có -V trả về một Java home được chọn theo cấu hình hiện tại. Kết quả này vẫn cần đối chiếu với command -v java và java.home của tiến trình thực tế.

### 3.3. Kiểm tra công cụ quản lý nhiều phiên bản

Một số máy dùng SDKMAN!, asdf hoặc jenv để chuyển phiên bản Java theo thư mục dự án hoặc phiên shell. Khi các công cụ này được sử dụng, cần ghi lại phiên bản đang được chọn và phạm vi áp dụng:

~~~bash
sdk current java
asdf current java
jenv version
~~~

Chỉ chạy lệnh tương ứng với công cụ đã cài. Kết quả của công cụ quản lý phiên bản giúp giải thích vì sao hai terminal trên cùng máy có thể chọn JDK khác nhau. Nó không thay thế việc kiểm tra executable thực tế bằng java -version và đường dẫn.

### 3.4. Kiểm tra JDK mà IDE sử dụng

IDE có thể khởi chạy compiler, Gradle/Maven hoặc ứng dụng bằng JDK riêng với terminal. Vì vậy, hãy kiểm tra từng cấu hình có liên quan:

| IDE / công cụ | Vị trí hoặc cấu hình cần xem |
|---|---|
| IntelliJ IDEA | Project SDK, SDK của module, Gradle JVM, Maven runner JRE và JRE trong từng Run/Debug Configuration. |
| Eclipse | Installed JREs, Execution Environments, JRE của project và cấu hình Maven/Gradle nếu có. |
| Visual Studio Code | Java runtime được cấu hình cho extension, project runtime và terminal tích hợp. |
| NetBeans | Java Platform của project và JDK được IDE dùng để chạy task. |

Đặc biệt với IntelliJ IDEA, Project SDK và Gradle JVM là hai thiết lập khác nhau. Project SDK có thể dùng để phân tích/biên dịch mã nguồn trong IDE, trong khi Gradle JVM dùng để khởi chạy Gradle. Nếu lập trình viên nhấn nút Run, IDE còn có thể sử dụng JRE được chỉ định riêng trong cấu hình chạy.

Nên ghi lại kết quả của hai tình huống: chạy build từ terminal và chạy build từ IDE. Nếu kết quả khác nhau, kiểm tra JDK được cấu hình trong IDE và các biến môi trường mà IDE kế thừa khi khởi động.

## 4. Kiểm kê JVM và toolchain của Gradle/Maven

Kết quả java -version trong terminal không cho biết đầy đủ JDK của build tool. Cần kiểm tra bằng chính wrapper của dự án, vì wrapper là phiên bản công cụ mà repository yêu cầu.

### 4.1. Gradle

Từ thư mục dự án, chạy:

~~~bash
./gradlew --version
~~~

Trên Windows:

~~~powershell
.\gradlew.bat --version
~~~

Kết quả Gradle có thể hiển thị phiên bản JVM của launcher và daemon. Hãy ghi lại cả hai nếu phiên bản Gradle đang dùng hiển thị chúng. Launcher JVM là JVM khởi chạy wrapper/Gradle; daemon JVM là JVM thực thi phần lớn hoạt động build.

Nếu phiên bản Gradle của dự án hỗ trợ task liệt kê Java toolchains, có thể chạy:

~~~bash
./gradlew -q javaToolchains
~~~

Task này giúp xem các toolchain mà Gradle phát hiện được, bao gồm đường dẫn, vendor và phiên bản khi thông tin có sẵn. Nếu task không tồn tại ở phiên bản Gradle đang dùng, ghi nhận rằng chưa thu được báo cáo toolchain; không suy đoán từ JDK của daemon.

Khi kiểm kê, cần đọc các cấu hình liên quan:

- JAVA_HOME và PATH trong shell/runner.
- org.gradle.java.home trong gradle.properties ở user home hoặc project.
- Gradle JVM được cấu hình trong IDE.
- Gradle daemon JVM criteria nếu repository có cấu hình và wrapper đang dùng hỗ trợ cơ chế đó.
- Java toolchain trong build script hoặc convention plugin.
- Cấu hình riêng của test task, javadoc task hoặc task fork tiến trình Java.

org.gradle.java.home điều khiển JVM dùng cho Gradle daemon; nó không đồng nghĩa với việc mọi task biên dịch đều dùng cùng JDK. Java toolchain có thể chọn compiler riêng. Một task test cũng có thể chỉ định launcher riêng để chạy test trên một JVM khác.

Ví dụ một dự án có thể cấu hình toolchain như sau:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Trong ví dụ này, compiler được chọn từ toolchain Java 21, còn bytecode/API mục tiêu được giới hạn ở Java 17. Cấu hình cụ thể của dự án có thể khác; mục đích của ví dụ là cho thấy phiên bản toolchain và mức bytecode target là hai thông tin riêng cần kiểm kê.

### 4.2. Maven

Sử dụng Maven Wrapper nếu repository có cung cấp:

~~~bash
./mvnw -version
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd -version
~~~

Kết quả cho biết Maven version, Java version, vendor và Java home mà tiến trình Maven đang dùng. Nếu chỉ chạy java -version, ta không xác nhận được Maven Wrapper đang dùng cùng runtime đó.

Tiếp theo, kiểm tra:

- JAVA_HOME và PATH của tiến trình Maven.
- Maven Wrapper và cấu hình JVM trong .mvn/jvm.config nếu có.
- maven.compiler.release, source và target trong cấu hình compiler plugin.
- Maven Toolchains Plugin và file toolchains.xml nếu dự án dùng.
- Cấu hình fork compiler, Surefire/Failsafe và các plugin tạo tiến trình Java riêng.
- JDK mà IDE Maven runner sử dụng khi chạy goal từ IDE.

Maven Toolchains cho phép một plugin chọn JDK khác với JDK đang chạy Maven. Vì vậy, mvn -version xác nhận JVM của Maven nhưng chưa chứng minh compiler hoặc test fork đang chạy bằng JDK nào. Cần đối chiếu toolchain configuration và log của plugin tương ứng.

### 4.3. Không nhầm JVM build với bytecode target

Ba giá trị sau phải được ghi thành các trường riêng:

1. JVM chạy Gradle/Maven.
2. JDK compiler/toolchain được chọn để biên dịch.
3. Mức bytecode/API mục tiêu của ứng dụng.

Ví dụ, build tool có thể chạy bằng JDK 21, compiler toolchain dùng JDK 17 và bytecode target là Java 17. Ứng dụng sau đó có thể chạy bằng runtime Java 17. Ngược lại, nếu artifact yêu cầu API Java 21 nhưng production chỉ có runtime Java 17, ứng dụng có thể thất bại dù bước build trên CI đã thành công.

## 5. Kiểm kê JDK trong CI

CI thường có nhiều lớp thực thi. Một workflow có thể khai báo runner image, cài JDK bằng action, chạy job trong container, gọi Docker build rồi chạy test trong container khác. Mỗi lớp có thể sử dụng JDK khác nhau.

### 5.1. Xác định môi trường thực thi của từng job

Với mỗi job, hãy ghi nhận:

- Loại runner: hosted runner hay self-hosted agent.
- Hệ điều hành, phiên bản image và kiến trúc.
- Job có chạy trong container hay không; nếu có, ghi image và digest thực tế khi hệ thống cung cấp.
- Bước cài đặt/chọn JDK, gồm nhà cung cấp và phiên bản yêu cầu.
- Các bước có chuyển sang container hoặc máy khác để build/test không.
- Các biến JAVA_HOME, PATH và cấu hình Gradle/Maven có hiệu lực trong job.

Một dòng cấu hình workflow khai báo Java 21 mới chỉ cho biết ý định cấu hình. Cần kiểm tra lệnh thực tế sau bước cài đặt JDK để xác nhận runner hoặc container đang chọn đúng phiên bản.

### 5.2. In thông tin JDK có mục tiêu trong pipeline

Có thể thêm một bước chẩn đoán tạm thời hoặc giữ lại một bước thông tin môi trường không chứa bí mật. Ví dụ với runner Linux:

~~~yaml
- name: Inspect Java environment
  shell: bash
  run: |
    printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
    command -v java
    java -version
    command -v javac || true
    javac -version || true
    ./gradlew --version
~~~

Nếu dự án dùng Maven, thay hoặc bổ sung lệnh:

~~~bash
./mvnw -version
~~~

Với Windows runner, dùng PowerShell:

~~~powershell
Write-Output "JAVA_HOME=$env:JAVA_HOME"
Get-Command java -All | Select-Object Source
java -version
javac -version
.\gradlew.bat --version
~~~

Nếu build có Java toolchain, cần thu thập thêm thông tin toolchain bằng cơ chế phù hợp với phiên bản Gradle/Maven đang sử dụng. Nếu test chạy forked JVM hoặc Docker build, cần kiểm tra JDK bên trong tiến trình/container đó; thông tin của runner bên ngoài không đại diện cho các lớp này.

Không in toàn bộ environment variables hoặc toàn bộ system properties vào log CI. Các giá trị này có thể chứa token, mật khẩu, thông tin kết nối hoặc dữ liệu nội bộ. Chỉ in những trường Java cần thiết và che thông tin định danh nhạy cảm trước khi chia sẻ log.

### 5.3. Self-hosted runner và cache

Với self-hosted runner, JDK có thể được cài thủ công hoặc được quản lý bởi image/agent. Cần ghi lại đường dẫn và bản phân phối thực tế, bởi cùng một tên runner có thể được nâng cấp hoặc thay đổi cấu hình theo thời gian.

Gradle/Maven cache không chứng minh JDK nào đã được sử dụng. Cache chỉ là dữ liệu được tái sử dụng; JDK phải được xác nhận từ tiến trình hiện tại. Nếu runner được dùng chung cho nhiều workflow, cần kiểm tra xem mỗi job có cài/chọn lại JDK rõ ràng hay phụ thuộc vào trạng thái còn lại từ job trước.

### 5.4. Ghi nhận theo job và matrix

Nếu CI có matrix Java version, operating system hoặc module, mỗi tổ hợp là một môi trường kiểm thử riêng. Không gộp kết quả của tất cả job thành một dòng duy nhất. Ghi lại job name, matrix parameters, runner/container, JDK thực tế và trạng thái kiểm chứng tương ứng.

## 6. Kiểm kê JVM của ứng dụng đang chạy

Đối với môi trường chạy, điều quan trọng là xác định JVM của tiến trình ứng dụng đang hoạt động. Cấu hình trong Dockerfile, manifest hoặc biến JAVA_HOME chỉ là đầu vào; tiến trình có thể được khởi chạy bằng một executable khác, một image khác hoặc một tham số ghi đè.

### 6.1. Kiểm tra trên máy Linux

Trước tiên, xác định PID của tiến trình Java bằng công cụ quản lý tiến trình hoặc process supervisor. Sau đó, nếu có quyền truy cập:

~~~bash
ps -p <PID> -o pid,args
readlink -f /proc/<PID>/exe
jcmd <PID> VM.version
jcmd <PID> VM.system_properties |
  grep -E '^(java.home|java.version|java.vendor|java.runtime.version|java.vm.name|os.arch)='
~~~

/proc/<PID>/exe cho biết executable mà tiến trình đang chạy trên Linux. jcmd có thể truy vấn phiên bản VM và các system properties của tiến trình đích nếu công cụ tương thích, cùng user/permission và cơ chế attach cho phép. Một số môi trường production tối giản không cài jcmd; khi đó cần dùng bằng chứng từ executable, image và thông tin runtime mà nền tảng cung cấp.

### 6.2. Kiểm tra trên Windows

Với quyền phù hợp, có thể truy vấn đường dẫn executable và command line của tiến trình:

~~~powershell
$javaPid = 1234
Get-CimInstance Win32_Process -Filter "ProcessId = $javaPid" |
    Select-Object ProcessId, ExecutablePath, CommandLine
~~~

Thay 1234 bằng PID thực tế. Nếu máy chạy nhiều Java process, phải xác định đúng PID của ứng dụng cần kiểm kê; không suy ra từ một tiến trình Java bất kỳ.

Nếu có JDK tương thích và quyền attach, có thể sử dụng jcmd với PID đó để xem phiên bản VM và các thuộc tính cần thiết. Kết quả từ jcmd phản ánh tiến trình được truy vấn tốt hơn việc chạy java -version trong một cửa sổ PowerShell khác.

### 6.3. Kiểm tra trong Docker

Nếu container có shell và công cụ Java:

~~~bash
docker exec <container> java -version
docker exec <container> sh -lc 'command -v java; printf "JAVA_HOME=%s\n" "$JAVA_HOME"'
~~~

Nếu ứng dụng có PID riêng, cần kiểm tra executable hoặc VM properties của đúng PID bên trong container. Không giả định PID ứng dụng luôn là PID 1.

Ghi nhận thêm:

- Image name/tag và image digest thực tế.
- Base image JDK/JRE được khai báo trong Dockerfile.
- Entrypoint, command và biến môi trường Java.
- Container ID, thời điểm tạo và phiên bản artifact đang chạy.

Tag image có thể được cập nhật để trỏ sang image khác. Digest giúp nhận diện image thực tế đã được triển khai tại thời điểm kiểm kê. Dockerfile cho biết cách image được dự định xây dựng; digest và tiến trình đang chạy giúp xác nhận artifact/runtime thực tế.

### 6.4. Kiểm tra trên Kubernetes

Trong Kubernetes, một workload có thể có nhiều pod, nhiều container và nhiều replica. Hãy kiểm tra từng loại container có chạy Java: application container, sidecar hoặc container xử lý tác vụ riêng. Với pod cần kiểm kê, ghi nhận image khai báo và imageID/digest mà node đã tải.

Ví dụ, có thể kiểm tra thông tin pod và container bằng kubectl describe pod hoặc truy vấn các trường cần thiết từ Pod specification/status. Nếu container cho phép thực thi lệnh:

~~~bash
kubectl exec <pod> -c <container> -- java -version
~~~

Nếu cần kiểm tra process cụ thể, dùng PID trong container và cơ chế quan sát phù hợp. Một pod có thể bị thay thế trong lúc kiểm kê; cần ghi lại namespace, pod name, container name, node, thời điểm và imageID để kết quả có thể đối chiếu.

Một số image distroless hoặc image tối giản không có shell, java trên PATH hay jcmd. Khi đó không kết luận rằng Java không tồn tại. Hãy dùng image digest, command/args, executable của process nếu nền tảng cho phép quan sát, hoặc một cơ chế chẩn đoán được tổ chức hỗ trợ. Không thay image production chỉ để cài thêm công cụ kiểm tra.

### 6.5. Kiểm tra theo từng môi trường và replica

Không nên chỉ kiểm tra một máy rồi đại diện cho toàn bộ production. Hệ thống có thể đang trong giai đoạn rolling deployment, một số instance vẫn chạy image cũ hoặc một nhóm worker dùng runtime khác với web application.

Tối thiểu cần phân biệt các môi trường thực sự tồn tại như local, development, test, staging và production. Trong production, xác định nhóm workload/replica có cùng cấu hình và kiểm tra đủ để phát hiện instance lệch phiên bản. Nếu một số process được quản lý bởi scheduler hoặc job runner, đưa chúng vào kiểm kê khi chúng thực thi mã Java của hệ thống.

## 7. Đối chiếu khai báo với kết quả thực tế

Sau khi thu thập dữ liệu, cần phân biệt rõ ba loại thông tin:

1. **Khai báo:** phiên bản được ghi trong build file, toolchain, workflow, Dockerfile hoặc manifest.
2. **Môi trường được chọn:** JDK được tìm thấy qua PATH, JAVA_HOME, IDE setting, runner setup hoặc container image.
3. **Tiến trình thực tế:** JVM/compiler đã thực thi build, test hoặc ứng dụng tại thời điểm kiểm kê.

Các loại thông tin này có thể khác nhau mà không phải lúc nào cũng là lỗi. Ví dụ, một dự án chủ động build bằng JDK 21 nhưng tạo bytecode Java 17 và triển khai trên runtime Java 17. Điều cần làm là xác nhận tổ hợp đó nằm trong ma trận tương thích được chấp nhận.

### 7.1. Những sai lệch thường gặp

| Quan sát | Nguyên nhân có thể | Việc cần xác minh |
|---|---|---|
| JAVA_HOME là một JDK nhưng java -version hiển thị bản khác. | PATH ưu tiên một executable khác; shell/IDE chưa nhận biến mới; công cụ quản lý version đang chọn bản khác. | Đường dẫn executable, thứ tự PATH và môi trường của tiến trình. |
| Terminal và IDE build cho kết quả khác nhau. | IDE có Project SDK, Gradle JVM hoặc Maven runner JRE riêng. | So sánh cấu hình và log của từng cách chạy. |
| gradlew --version cho thấy daemon JDK khác terminal. | org.gradle.java.home, daemon JVM criteria hoặc IDE setting chọn JVM khác. | Cấu hình Gradle hiệu lực và daemon JVM. |
| Gradle daemon dùng JDK A nhưng compile dùng JDK B. | Java toolchain chỉ định compiler riêng. | Báo cáo toolchain và compiler task. |
| Maven chạy bằng JDK A nhưng compiler dùng JDK B. | Maven Toolchains hoặc compiler fork. | toolchains.xml, plugin configuration và log compiler. |
| CI runner dùng JDK mới nhưng ứng dụng trong container dùng JDK cũ. | Docker build/runtime image có JDK riêng. | Image digest và JVM bên trong container. |
| Một số pod chạy phiên bản khác các pod còn lại. | Rolling deployment, node/image cache hoặc rollout chưa hoàn tất. | ImageID và runtime của từng replica. |
| javac không có trên production. | Runtime image chỉ chứa JRE hoặc runtime tối giản. | Xác nhận tiến trình ứng dụng và runtime; không yêu cầu compiler nếu không cần biên dịch tại chỗ. |

### 7.2. Không suy ra phiên bản runtime từ bytecode target

Bytecode target cho biết mức class file compiler tạo ra, không cho biết JVM nào đang chạy ứng dụng. Tương tự, runtime Java 21 có thể chạy bytecode được biên dịch theo Java 17. Vì vậy, khi báo cáo cần có trường riêng cho:

- JDK chạy compiler.
- Release/bytecode target.
- JVM runtime của ứng dụng.

Nếu cần xác minh class file, có thể dùng javap -verbose trên một class đã biên dịch và xem major version. Tuy nhiên, chỉ số class-file version là bằng chứng về bytecode của class được kiểm tra; nó không xác định JDK của tiến trình build hay runtime đang chạy.

## 8. Mẫu bảng kiểm kê JDK

Nên dùng một dòng cho mỗi vai trò/môi trường có ý nghĩa. Không gộp máy phát triển, CI và production vào một dòng vì chúng có thể có cấu hình khác nhau.

| Môi trường / host | Vai trò / tiến trình | JDK/JVM version và vendor | Executable / java.home | Kiến trúc | Cách chọn JDK | Bằng chứng / thời điểm |
|---|---|---|---|---|---|---|
| Developer workstation | Terminal |  |  |  | JAVA_HOME / PATH / version manager |  |
| Developer workstation | IDE build/run |  |  |  | Project SDK / IDE runner |  |
| Developer workstation | Gradle daemon hoặc Maven |  |  |  | Wrapper / IDE / gradle.properties |  |
| Developer workstation | Compiler toolchain |  |  |  | Gradle toolchain / Maven Toolchains |  |
| CI job | Runner / agent |  |  |  | Runner image / setup step |  |
| CI job | Build container / test JVM |  |  |  | Container image / task configuration |  |
| Runtime environment | Application process |  |  |  | Image / startup command / process |  |
| Runtime environment | Worker / scheduled job |  |  |  | Image / service configuration |  |

Tùy quy mô hệ thống, có thể bổ sung các trường:

- Tên dự án/module, job, service, pod hoặc container.
- OS và phiên bản OS; runner label hoặc node.
- JDK distribution, full build number và image digest.
- PID/process name, artifact version và commit SHA.
- JAVA_HOME, PATH entry được chọn và cấu hình toolchain.
- Bytecode target, framework version và trạng thái hỗ trợ.
- Người/nhóm phụ trách và thời điểm kiểm kê tiếp theo.

Ví dụ cách ghi một dòng, với giá trị minh họa:

| Môi trường / host | Vai trò / tiến trình | JDK/JVM version và vendor | Executable / java.home | Kiến trúc | Cách chọn JDK | Bằng chứng / thời điểm |
|---|---|---|---|---|---|---|
| CI job compile | Gradle daemon | Java 21, vendor theo output thực tế | Đường dẫn lấy từ java.home | Theo os.arch | Runner setup và cấu hình Gradle | Log gradlew --version, thời điểm chạy |

Không điền giá trị dựa trên dự đoán. Nếu chưa truy cập được một môi trường, đánh dấu “chưa xác minh”, ghi lý do và chỉ rõ bằng chứng còn thiếu.

## 9. Quy trình kiểm kê có thể lặp lại

Một quy trình thống nhất giúp so sánh kết quả giữa các nhóm và giữa các lần migration:

1. **Xác định phạm vi môi trường:** liệt kê workstation/IDE, CI job, build container, test environment, runtime service, worker và replica liên quan.
2. **Ghi nhận cấu hình khai báo:** JDK version, vendor, toolchain, workflow setup, image, startup command và bytecode target.
3. **Thu thập từ môi trường thực tế:** chạy lệnh kiểm tra tại đúng terminal/runner/container hoặc truy vấn đúng process đang hoạt động.
4. **Tách theo vai trò:** ghi riêng JVM chạy build, compiler toolchain, test JVM và application JVM.
5. **Đối chiếu:** so sánh khai báo, môi trường được chọn và tiến trình thực tế; giải thích mọi khác biệt có chủ đích.
6. **Ghi nhận bằng chứng:** lưu output có chọn lọc, đường dẫn, image digest, job/pod/PID và thời điểm kiểm tra.
7. **Đánh dấu phần chưa xác minh:** ghi rõ môi trường chưa truy cập được hoặc công cụ không thể attach.
8. **Chốt baseline:** dùng bảng đã xác nhận làm mốc để so sánh với JDK mục tiêu trong kế hoạch chuyển đổi.

Khi lặp lại kiểm kê sau khi thay đổi, nên dùng cùng lệnh và cùng cách xác định môi trường. Nếu runner image, container digest hoặc số replica thay đổi, cần ghi nhận để so sánh đúng đối tượng.

## 10. Bảo vệ thông tin khi thu thập bằng chứng

Thông tin JDK thường ít nhạy cảm hơn cấu hình ứng dụng, nhưng log hệ thống có thể chứa username, hostname, đường dẫn nội bộ, command line, tham số JVM hoặc system properties có dữ liệu bí mật.

Khi chia sẻ kết quả kiểm kê:

- Chỉ thu thập các thuộc tính Java cần thiết; không xuất toàn bộ environment variables hoặc toàn bộ system properties.
- Kiểm tra command line và log trước khi đưa lên ticket, repository hoặc tài liệu dùng chung.
- Che token, mật khẩu, URL có credential, thông tin kết nối và định danh cá nhân.
- Giữ lại các trường kỹ thuật cần cho việc đối chiếu như Java version, vendor, java.home, kiến trúc và image digest.
- Tuân theo quyền truy cập của môi trường; không cố attach vào process hoặc container khi không được cấp quyền.

## 11. Kết quả cần có sau khi kiểm kê

Một đợt kiểm kê hoàn chỉnh cần cho phép nhóm trả lời được:

- Máy phát triển đang có những JDK nào và terminal/IDE chọn bản nào?
- Gradle hoặc Maven được khởi chạy bằng JVM nào?
- Compiler và test process sử dụng toolchain nào?
- CI runner, job container và Docker build/runtime có JDK nào?
- Ứng dụng thực tế đang chạy bằng JVM nào trong từng môi trường và replica?
- Bytecode target của artifact là bao nhiêu?
- Những khác biệt nào là chủ đích, khác biệt nào là sai lệch cần xử lý?
- Môi trường nào chưa có bằng chứng xác nhận?

Kết quả nên được lưu thành baseline có ngày kiểm kê, nguồn bằng chứng và người phụ trách. Baseline này là đầu vào để chọn JDK mục tiêu, xác định build tool/framework tương thích, lập kế hoạch nâng cấp và kiểm tra sau migration. Nếu không biết chính xác JDK đang được dùng ở từng lớp, nhóm rất dễ sửa nhầm cấu hình hoặc đánh giá thành công dựa trên một môi trường không đại diện cho hệ thống thực tế.
