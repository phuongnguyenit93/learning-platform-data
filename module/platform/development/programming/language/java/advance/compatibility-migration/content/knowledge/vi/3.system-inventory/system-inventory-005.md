# Kiểm kê JVM option, system property và biến môi trường

Trước khi nâng cấp JDK, thay đổi cách đóng gói ứng dụng hoặc chuyển hệ thống sang máy chủ/container mới, cần biết chính xác tiến trình Java đang được khởi chạy với những cấu hình nào. Một ứng dụng có thể chạy ổn định nhờ các JVM option, system property hoặc biến môi trường được đặt rải rác trong script, pipeline CI/CD, cấu hình dịch vụ, Docker image, Kubernetes manifest và công cụ triển khai. Nếu chỉ kiểm tra `build.gradle`, `pom.xml` hoặc file cấu hình ứng dụng, ta có thể bỏ sót cấu hình thực sự đang tác động đến JVM.

**Kiểm kê JVM option, system property và biến môi trường** là quá trình tìm, ghi nhận, xác định nguồn gốc và đối chiếu các giá trị cấu hình liên quan đến từng tiến trình Java. Mục tiêu là trả lời được: tiến trình nào đang chạy; dùng JDK nào; nhận cấu hình từ đâu; giá trị thực tế lúc khởi động là gì; cấu hình đó phục vụ mục đích nào; và giá trị nào cần giữ, thay thế hoặc loại bỏ khi migration.

Đây là bước khảo sát hệ thống trước khi thay đổi runtime. Một danh sách cấu hình chỉ đọc từ source code chưa đủ: cần kết hợp cấu hình được khai báo với trạng thái của tiến trình đang chạy, vì hai thứ có thể khác nhau do biến môi trường, script khởi chạy, tham số dòng lệnh, cấu hình của nền tảng triển khai hoặc code thay đổi system property lúc runtime.

## 1. Phân biệt ba nhóm cấu hình

JVM option, Java system property và biến môi trường thường xuất hiện cạnh nhau trong lệnh chạy Java, nhưng chúng có cách truyền, phạm vi và cách đọc khác nhau.

| Nhóm | Cách khai báo thường gặp | Cách đọc trong Java | Phạm vi chính |
|---|---|---|---|
| JVM option | `-Xmx2g`, `-Xss1m`, `-XX:+UseG1GC`, `--add-opens=...` | JVM hoặc launcher xử lý trước khi ứng dụng chạy | Cấu hình khởi động của JVM |
| Java system property | `-Dapp.region=ap-southeast-1` | `System.getProperty("app.region")` | Một JVM; cũng có thể được code thay đổi khi chạy |
| Biến môi trường | `APP_REGION=ap-southeast-1` | `System.getenv("APP_REGION")` | Môi trường của process và các process con được tạo từ môi trường đó |

### 1.1. JVM option

JVM option là tham số được truyền cho Java launcher hoặc máy ảo để điều khiển cách JVM khởi động và vận hành. Một số nhóm thường gặp:

| Nhóm | Ví dụ | Tác động |
|---|---|---|
| Bộ nhớ heap | `-Xms512m`, `-Xmx2g` | Heap ban đầu và giới hạn heap tối đa |
| Stack | `-Xss1m` | Kích thước stack của mỗi thread |
| Garbage Collector | `-XX:+UseG1GC`, `-XX:MaxGCPauseMillis=200` | Lựa chọn và tinh chỉnh GC |
| Metaspace | `-XX:MaxMetaspaceSize=512m` | Giới hạn vùng metaspace |
| Module access | `--add-opens=java.base/java.lang=ALL-UNNAMED` | Mở package cho truy cập phản chiếu theo quy tắc module |
| Assertion | `-ea` hoặc `-enableassertions` | Bật assertion khi chạy |
| Agent và instrumentation | `-javaagent:agent.jar`, `-agentlib:jdwp=...` | Nạp agent, profiling hoặc debugger |
| Chẩn đoán và lỗi | `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:HeapDumpPath=/var/dumps` | Tạo bằng chứng khi JVM gặp sự cố |

Một số option có dạng chuẩn, một số bắt đầu bằng `-X` hoặc `-XX`. Các option mở rộng `-X` và `-XX` có thể phụ thuộc JDK, nhà cung cấp JVM và phiên bản cụ thể. Không nên giả định một option từng chạy được trên JDK cũ sẽ tiếp tục được hỗ trợ ở JDK mới.

### 1.2. Java system property

System property là cặp khóa/giá trị dạng chuỗi thuộc về một JVM. Cách phổ biến để đặt property khi khởi động là dùng `-D`:

```bash
java -Dapp.region=ap-southeast-1 -Dfile.encoding=UTF-8 -jar application.jar
```

Ứng dụng đọc giá trị bằng:

```java
String region = System.getProperty("app.region");
String encoding = System.getProperty("file.encoding");
```

Code cũng có thể thay đổi system property trong lúc chạy:

```java
System.setProperty("app.region", "ap-southeast-1");
```

Vì vậy, giá trị đang thấy trong ứng dụng không nhất thiết chỉ đến từ `-D`. Nó có thể đến từ giá trị mặc định của JDK, tham số khởi động, thư viện hoặc lệnh `System.setProperty()` được thực thi sau đó. Một số thư viện đọc property một lần khi khởi tạo; thay đổi property sau thời điểm đó không có nghĩa thư viện tự cập nhật hành vi.

System property là dữ liệu dạng chuỗi. Ý nghĩa của từng khóa phụ thuộc vào JVM, JDK, thư viện hoặc ứng dụng. Ví dụ `user.timezone` có thể ảnh hưởng timezone mặc định; `javax.net.ssl.trustStore` có thể chỉ định truststore; `app.region` là property do ứng dụng tự định nghĩa.

### 1.3. Biến môi trường

Biến môi trường được hệ điều hành gắn vào môi trường của process khi process được tạo. Java đọc chúng bằng:

```java
String region = System.getenv("APP_REGION");
```

Hoặc lấy map các biến mà process nhìn thấy:

```java
Map<String, String> environment = System.getenv();
```

Các biến thường ảnh hưởng đến việc chọn JDK hoặc cấu hình runtime gồm:

| Biến | Vai trò thường gặp |
|---|---|
| `JAVA_HOME` | Chỉ thư mục cài JDK/JRE mà script hoặc công cụ dùng làm Java home |
| `PATH` | Quyết định executable `java` nào được tìm thấy khi gọi bằng tên |
| `JDK_JAVA_OPTIONS` | Bổ sung option cho Java launcher trên các JDK hỗ trợ biến này |
| `JAVA_TOOL_OPTIONS` | Bổ sung option khi JVM được tạo qua cơ chế khởi tạo VM, thường hữu ích với công cụ nhúng JVM |
| `_JAVA_OPTIONS` | Cơ chế riêng của một số HotSpot build; không nên coi là giao diện portable, được chuẩn hóa |
| `CLASSPATH` | Classpath mặc định khi launcher không nhận classpath khác |
| `MAVEN_OPTS` | Thường được Maven launcher dùng để truyền option cho JVM chạy Maven |
| `GRADLE_OPTS` | Thường truyền option cho JVM chạy Gradle client; JVM của Gradle daemon có thể có cấu hình riêng qua `org.gradle.jvmargs` |
| `APP_*`, `SPRING_*` | Quy ước cấu hình do ứng dụng hoặc framework sử dụng |
| `TZ`, `LANG`, `LC_ALL` | Có thể ảnh hưởng timezone, locale hoặc môi trường định dạng của process |

Tên biến và cách sử dụng có thể khác theo hệ điều hành, script và nền tảng triển khai. Java launcher không tự hiểu mọi biến có tên chứa `JAVA` hoặc `OPTS`; cần biết thành phần nào đọc biến đó.

## 2. Hiểu đúng cách cấu hình đi vào một tiến trình Java

Một cấu hình có thể được khai báo ở nhiều lớp. Ví dụ, cùng một property `app.region` có thể xuất hiện trong tham số `-D`, biến môi trường `APP_REGION`, file cấu hình ứng dụng và lệnh `System.setProperty()`. Không có một quy tắc ưu tiên chung cho mọi ứng dụng: thứ tự ưu tiên giữa environment, system property, file YAML, command-line argument và remote config phụ thuộc vào framework hoặc code đang dùng.

### 2.1. Ranh giới giữa JVM option và tham số ứng dụng

Java launcher phân biệt option của launcher/JVM với đối số truyền cho ứng dụng. Ví dụ:

```bash
java -Xmx2g -Dapp.mode=production -jar application.jar --server.port=8080
```

Trong ví dụ này:

- `-Xmx2g` là JVM option.
- `-Dapp.mode=production` đặt system property cho JVM.
- `-jar application.jar` yêu cầu launcher chạy JAR.
- `--server.port=8080` là đối số của ứng dụng, thường được framework xử lý.

Với lệnh chạy class:

```bash
java -Dapp.mode=production com.example.Main --verbose
```

Các option phải nằm trước tên class. Phần sau tên class được truyền cho `main(String[] args)`. Tương tự, với `-jar`, phần sau tên JAR là đối số ứng dụng. Đặt `-Dapp.mode=production` sau `-jar application.jar` không còn có nghĩa là đặt system property cho JVM; ứng dụng sẽ nhận chuỗi đó như một argument.

Điểm này thường bị bỏ sót khi di chuyển tham số giữa Docker `ENTRYPOINT`, `CMD`, script shell hoặc cấu hình của service manager.

### 2.2. Các nguồn bổ sung JVM option qua môi trường

Ngoài command line hiển thị trong script, một số biến môi trường có thể bổ sung option:

- `JDK_JAVA_OPTIONS` được Java launcher trên JDK hỗ trợ thêm vào command line của launcher. Biến này được giới thiệu từ JDK 9.
- `JAVA_TOOL_OPTIONS` được đọc trong quá trình tạo JVM, có thể tác động đến các chương trình nhúng JVM hoặc công cụ khởi tạo JVM mà không gọi launcher theo cách thông thường.
- `_JAVA_OPTIONS` tồn tại trong một số môi trường HotSpot nhưng là cơ chế phụ thuộc implementation; không nên dựa vào nó như một hợp đồng portable.

Do các nguồn này có thể được kết hợp với option trên command line và script, chỉ đọc một dòng `java ...` chưa chắc cho biết đầy đủ cấu hình. Cần ghi lại cả biến môi trường có liên quan và xác nhận option thực tế từ JVM đang chạy.

`JAVA_OPTS` là tên biến thường được script tự quy ước. Java launcher không tự động đọc biến này. Ví dụ, script có thể viết:

```bash
java $JAVA_OPTS -jar application.jar
```

Nếu script không tham chiếu `$JAVA_OPTS`, biến được đặt trong môi trường sẽ không tự có tác dụng. Tương tự, `MAVEN_OPTS` và `GRADLE_OPTS` được công cụ build đọc theo cơ chế riêng; không được mặc định rằng chúng cũng là option của JVM chạy ứng dụng cuối cùng.

### 2.3. Giá trị khai báo và giá trị hiệu lực

Khi kiểm kê, cần phân biệt ít nhất ba trạng thái:

1. **Giá trị được khai báo:** xuất hiện trong file cấu hình, script, pipeline hoặc manifest.
2. **Giá trị được truyền vào process:** thực sự có mặt trong command line hoặc môi trường lúc process được tạo.
3. **Giá trị hiệu lực:** JVM hoặc ứng dụng đang sử dụng sau khi xử lý mặc định, option, cấu hình framework và các thay đổi lúc runtime.

Ba trạng thái này có thể khác nhau. Một file deployment khai báo `-Xmx2g`, nhưng container giới hạn memory thấp hơn và JVM áp dụng cách tính bộ nhớ khác; một biến môi trường có thể được đặt trong manifest nhưng script khởi chạy không sử dụng; một system property có thể bị code ghi đè trong lúc khởi động.

Vì thế, inventory nên lưu cả nguồn khai báo và bằng chứng runtime. Không ghi một giá trị duy nhất rồi mặc định nó là giá trị cuối cùng.

## 3. Xác định đầy đủ các tiến trình Java cần kiểm kê

Trước khi tìm option, hãy lập danh sách các tiến trình. Một hệ thống có thể chứa nhiều JVM với cấu hình khác nhau:

- JVM chạy ứng dụng chính.
- JVM chạy Gradle hoặc Maven.
- Gradle daemon và các JVM test được fork riêng.
- JVM chạy compiler, annotation processor hoặc công cụ sinh mã.
- JVM của application server, worker, scheduler hoặc sidecar.
- JVM chạy migration tool, batch job và script quản trị.
- JVM trong môi trường development, staging, production và CI.

Không được gộp cấu hình của các process này thành một bộ chung. Ví dụ, `GRADLE_OPTS` có thể ảnh hưởng JVM chạy Gradle; `test.jvmArgs` hoặc cấu hình test fork mới ảnh hưởng JVM chạy test; `bootRun` hoặc script deploy có thể có cấu hình riêng cho ứng dụng. Nâng cấp JDK cho Gradle daemon không tự chứng minh JVM chạy ứng dụng đã được nâng cấp.

Với mỗi process, ghi nhận:

| Thuộc tính | Nội dung cần xác định |
|---|---|
| Nhận diện | Tên service, PID, container/pod, hostname hoặc job id |
| Vai trò | Application, build, test, batch, worker hay công cụ quản trị |
| Runtime | Nhà cung cấp JVM, phiên bản JDK và đường dẫn executable nếu xác định được |
| Khởi chạy | Lệnh, entrypoint, script, service unit hoặc pipeline tạo process |
| Môi trường | OS, container image, namespace, môi trường deployment |
| Thời điểm | Thời điểm chụp inventory và phiên bản release đang chạy |
| Owner | Nhóm chịu trách nhiệm về process và cấu hình |

Một process có thể được restart bởi orchestrator hoặc autoscaling. PID chỉ nhận diện một lần chạy cụ thể, không phải định danh ổn định của service. Hãy gắn PID với tên service, container/pod và thời điểm quan sát.

## 4. Tìm cấu hình được khai báo trong repository và môi trường triển khai

Kiểm kê tĩnh giúp tìm nơi cấu hình được viết ra trước khi quan sát process đang chạy. Hãy tìm theo nhiều nhóm từ khóa, đồng thời mở rộng phạm vi ra ngoài source code.

### 4.1. Tìm trong source code và build configuration

Các vị trí thường cần kiểm tra:

- `build.gradle`, `build.gradle.kts`, `gradle.properties`, `settings.gradle` và các convention plugin.
- `pom.xml`, `.mvn/jvm.config`, `.mvn/maven.config` và Maven wrapper script.
- `Dockerfile`, `docker-compose.yml`, shell script, batch file và PowerShell script.
- Cấu hình test, task `JavaExec`, `bootRun`, forked test JVM và cấu hình application plugin.
- File `.env`, file cấu hình theo profile, template triển khai và script entrypoint.
- GitHub Actions, Jenkinsfile, GitLab CI, Azure pipeline hoặc workflow CI/CD tương đương.

Có thể tìm kiếm các từ khóa phổ biến bằng `rg`:

```bash
rg -n --hidden -g '!**/.git/**' \
  'JAVA_HOME|JAVA_OPTS|JDK_JAVA_OPTIONS|JAVA_TOOL_OPTIONS|_JAVA_OPTIONS|MAVEN_OPTS|GRADLE_OPTS|CLASSPATH' .

rg -n --hidden -g '!**/.git/**' \
  -- '-Xms|-Xmx|-Xss|-XX:|-D[a-zA-Z0-9_.-]+=|--add-opens|--add-exports|-javaagent|-agentlib' .
```

Các biểu thức tìm kiếm chỉ là điểm bắt đầu. Một option có thể được tạo động bằng biến, ghép chuỗi, lấy từ file ngoài hoặc được truyền qua tham số của script. Cần lần theo nơi biến được gán, nơi được mở rộng và process cuối cùng nhận nó.

Đặc biệt kiểm tra cấu hình theo môi trường. Một file `application.yml` chung có thể không chứa giá trị production vì deployment inject biến môi trường hoặc system property riêng. Template Helm, ConfigMap, service unit, secret reference và cấu hình của nền tảng cloud có thể là nguồn quan trọng.

### 4.2. Tìm trong cấu hình hệ điều hành và service manager

Với Linux, kiểm tra unit file của systemd, các file environment được tham chiếu, script khởi động và cấu hình supervisor. Với Windows, kiểm tra Windows Service configuration, wrapper script, registry hoặc cấu hình của service wrapper nếu có. Với máy chủ ứng dụng, kiểm tra startup script và cấu hình JVM riêng của server.

Không chỉ tìm chuỗi `java`. Một service có thể gọi wrapper như `startup.sh`, `catalina.sh`, `gradlew`, một script nội bộ hoặc executable khác; wrapper mới là nơi ghép các option thực tế.

### 4.3. Kiểm tra Docker và Kubernetes

Với Docker, cần xem cả `ENTRYPOINT`, `CMD`, `ENV`, build argument được chuyển thành environment, compose override và biến được inject lúc `docker run`. `docker inspect` có thể cho thấy cấu hình container, nhưng dữ liệu environment hoặc command line có thể chứa thông tin nhạy cảm; chỉ trích xuất các khóa cần thiết và che giá trị bí mật.

Với Kubernetes, kiểm tra `command`, `args`, `env`, `envFrom`, ConfigMap reference, Secret reference, init container và các template Helm/Kustomize. Một manifest chỉ chứa tham chiếu đến Secret không cho biết giá trị thực tế; không cần xuất nội dung Secret để hoàn thành inventory JVM. Ghi nhận tên tham chiếu, key và owner theo chính sách quản lý secret của tổ chức.

Hãy phân biệt cấu hình ở Pod template với cấu hình thực tế của Pod đang chạy. Pod có thể đang dùng revision cũ, image digest khác hoặc được tạo trước lần cập nhật manifest gần nhất.

## 5. Quan sát JVM đang chạy

Kiểm tra process runtime giúp xác nhận JDK và option thực sự được JVM nhận. Các lệnh dưới đây phù hợp chủ yếu với HotSpot/OpenJDK; lệnh và tập diagnostic command có thể khác ở nhà cung cấp JVM khác.

### 5.1. Liệt kê process và command line

```bash
jps -lv
```

`jps` liệt kê các JVM mà công cụ có thể quan sát trên máy và thường hiển thị class chính cùng JVM arguments. Nó hữu ích để tìm PID, nhưng không phải lúc nào cũng nhìn thấy mọi process, đặc biệt khi khác user, khác container namespace hoặc attach bị giới hạn.

Sau khi xác định PID, dùng `jcmd`:

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags -all
jcmd <pid> VM.system_properties
```

Ý nghĩa:

- `VM.command_line` cho biết thông tin command line mà JVM ghi nhận.
- `VM.flags -all` hiển thị các VM flag và giá trị hiện tại mà JVM công bố qua diagnostic command.
- `VM.system_properties` hiển thị system properties của process tại thời điểm truy vấn.

Đây là bằng chứng runtime có giá trị hơn việc chỉ đọc script. Tuy nhiên, output của `VM.system_properties` có thể chứa đường dẫn nội bộ, token hoặc thông tin nhạy cảm nếu ứng dụng lưu chúng trong system property. Không đưa nguyên output vào ticket, log dùng chung hoặc repository.

Quyền attach, user sở hữu process, container PID namespace và chính sách bảo mật có thể ngăn `jcmd` kết nối. Khi lệnh thất bại, ghi nhận giới hạn quan sát và dùng kênh quản trị được phê duyệt; không tự ý chạy process dưới quyền cao hơn chỉ để lấy dữ liệu.

### 5.2. Quan sát flag của một JVM mới

Để xem các flag và giá trị mặc định của JDK được chọn:

```bash
java -XX:+PrintFlagsFinal -version
```

Lệnh này khởi chạy một JVM mới và in danh sách flag cuối cùng của lần chạy đó. Nó hữu ích để khảo sát JDK binary cụ thể, nhưng không thay thế việc đọc flag của process production đang chạy. Giá trị có thể thay đổi theo option truyền vào, loại JVM, phần cứng, giới hạn container và phiên bản JDK.

Để xem system property của một lần khởi chạy mới:

```bash
java -XshowSettings:properties -version
```

Đây cũng chỉ là snapshot của process mới được tạo bởi lệnh trên. Nó không chứng minh process ứng dụng đang chạy có cùng giá trị.

### 5.3. Đọc thông tin từ Java Management API

Ứng dụng có thể quan sát một số thông tin của chính JVM thông qua Management API:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;

public class RuntimeInventory {
    public static void printRuntimeIdentity() {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();

        System.out.println("VM name: " + runtime.getVmName());
        System.out.println("VM vendor: " + runtime.getVmVendor());
        System.out.println("VM version: " + runtime.getVmVersion());
        System.out.println("Input arguments:");
        runtime.getInputArguments().forEach(System.out::println);
    }
}
```

`getInputArguments()` cung cấp các đối số được truyền cho JVM theo góc nhìn của runtime. Nó hữu ích để chẩn đoán, nhưng không phải bản sao hoàn chỉnh của mọi nguồn cấu hình: không thay thế inventory environment, script, cấu hình framework hoặc các thay đổi property lúc runtime. Danh sách đối số cũng có thể chứa thông tin nhạy cảm nếu người triển khai đặt secret trực tiếp trong tham số.

Đọc một số system property cụ thể bằng `System.getProperty()` và biến môi trường cụ thể bằng `System.getenv()` giúp kiểm tra giá trị mà ứng dụng nhìn thấy. Nên chọn khóa theo allowlist thay vì xuất toàn bộ dữ liệu.

### 5.4. Kiểm tra biến môi trường của process

Biến môi trường là thuộc tính của process do hệ điều hành quản lý. `System.getenv()` trong Java cho biết môi trường mà process hiện tại nhận được. Công cụ JVM như `jcmd` không phải công cụ liệt kê đầy đủ environment variables.

Trên Linux, môi trường ban đầu của process thường có thể được quan sát qua `/proc/<pid>/environ` nếu quyền hệ điều hành cho phép. Ví dụ kỹ thuật:

```bash
tr '\0' '\n' < /proc/<pid>/environ
```

Lệnh này có thể in ra secret, credential hoặc token. Chỉ dùng khi được phép, lọc đúng các khóa cần kiểm kê và không lưu output thô vào nơi không được bảo vệ. `ps` có thể hiển thị command line nhưng không phải nguồn đầy đủ để lấy environment.

Trên Windows, `Get-ChildItem Env:` chỉ hiển thị môi trường của PowerShell hiện tại, không phải environment của một process khác. Có thể kiểm tra command line bằng CIM:

```powershell
Get-CimInstance Win32_Process |
    Select-Object ProcessId, Name, CommandLine
```

Để biết environment của Windows Service hoặc process cụ thể, cần kiểm tra service configuration, wrapper, công cụ quản trị process phù hợp và quyền truy cập được cấp. Không dùng environment của terminal hiện tại để suy luận rằng service đã nhận cùng giá trị.

## 6. Đọc system property và environment một cách an toàn

Một inventory tốt cần đủ bằng chứng để migration, nhưng không cần sao chép bí mật. JVM option, system property và environment đôi khi chứa password, token, URL có credential hoặc đường dẫn nội bộ. Ngay cả tên khóa cũng có thể tiết lộ thông tin vận hành.

### 6.1. Ưu tiên allowlist

Ví dụ, thay vì in toàn bộ system properties, hãy đọc những khóa đã xác định là cần cho migration:

```java
import java.util.List;

public class SelectedProperties {
    private static final List<String> PROPERTY_KEYS = List.of(
            "java.version",
            "java.vendor",
            "java.home",
            "file.encoding",
            "user.timezone",
            "app.region"
    );

    public static void printSelectedProperties() {
        for (String key : PROPERTY_KEYS) {
            System.out.printf("%s=%s%n", key, System.getProperty(key));
        }
    }
}
```

Tương tự, với environment, chỉ đọc các khóa được phê duyệt như `JAVA_HOME`, `APP_REGION` hoặc `TZ`. Không in `System.getenv()` toàn bộ vào log production.

Nếu cần kiểm tra các khóa cấu hình có thể chứa secret, hãy lưu trạng thái như `present`, nguồn tham chiếu và owner; không lưu giá trị. Ví dụ, inventory có thể ghi `DB_PASSWORD: configured via SecretRef/database-credentials`, thay vì sao chép password.

### 6.2. Không đặt secret trực tiếp trong JVM argument

Tham số command line có thể bị hiển thị trong process listing, diagnostic output, log của orchestrator hoặc công cụ giám sát. Đặt `-Dapi.token=...` hoặc `--password=...` có thể khiến secret lộ cho người có quyền xem process metadata. Nên dùng secret manager, file mount có quyền phù hợp hoặc cơ chế credential được nền tảng hỗ trợ; ứng dụng chỉ đọc secret tại runtime theo chính sách bảo mật.

Nếu inventory phát hiện secret đang được truyền qua command line hoặc system property, ghi nhận rủi ro và vị trí cấu hình, che giá trị trong báo cáo. Việc thay đổi cách cấp secret cần được xử lý như một hạng mục migration riêng và kiểm chứng rằng ứng dụng vẫn đọc đúng credential.

## 7. Lập bảng inventory có thể dùng cho migration

Không nên chỉ tạo một danh sách các dòng `-Xmx`, `-D` và `APP_*`. Cần ghi được nguồn gốc, phạm vi, tác dụng và bằng chứng runtime để người thực hiện biết phải kiểm tra điều gì trên JDK mới.

### 7.1. Các trường nên có

| Trường | Nội dung |
|---|---|
| Process/service | Service, job, test worker hoặc build daemon nhận cấu hình |
| Environment | Local, CI, dev, staging, production hoặc tên cluster |
| Configuration type | JVM option, system property, environment variable hoặc application argument |
| Key/option | Tên chính xác, ví dụ `-Xmx`, `app.region`, `APP_REGION` |
| Value | Giá trị đã được phép lưu; nếu nhạy cảm thì ghi trạng thái và reference |
| Source | Script, Gradle, Maven, service unit, container, manifest, CI variable hoặc secret reference |
| Effective evidence | Output `jcmd`, API runtime, process metadata hoặc xác nhận của owner |
| Scope | Một process, một host, một container, một namespace hay toàn môi trường |
| Purpose | Mục đích kỹ thuật hoặc nghiệp vụ của cấu hình |
| Owner | Nhóm hoặc thành phần chịu trách nhiệm |
| Lifecycle | Startup-only, đọc khi khởi tạo, có thể thay đổi lúc runtime hay được framework refresh |
| JDK dependency | JDK/vendor/version liên quan; portable hay implementation-specific |
| Migration action | Keep, replace, validate, remove hoặc investigate |
| Evidence/time | Nguồn chứng cứ, release và thời điểm kiểm kê |

### 7.2. Ví dụ inventory rút gọn

Các dòng sau là dữ liệu minh họa, không phải cấu hình mặc định cho mọi ứng dụng:

| Process | Loại | Cấu hình | Nguồn | Bằng chứng cần xác nhận | Hướng xử lý |
|---|---|---|---|---|---|
| `orders-api` | JVM option | `-Xmx2g` | Deployment `args` | `jcmd ... VM.flags -all` và memory limit | Validate trên JDK mới và container limit |
| `orders-api` | JVM option | `--add-opens=java.base/java.lang=ALL-UNNAMED` | `JAVA_TOOL_OPTIONS` | `VM.command_line`, environment và thư viện cần reflective access | Tìm consumer; thay thư viện hoặc giữ tạm nếu cần |
| `orders-api` | System property | `app.region=...` | `-D` trong entrypoint | `VM.system_properties` và giá trị ứng dụng đọc | Giữ semantics, xác nhận nguồn cấu hình chuẩn |
| `orders-api` | Environment | `APP_REGION` | Kubernetes ConfigMap | Environment thực tế của Pod và `System.getenv` | Kiểm tra mapping vào framework |
| `batch-worker` | Environment | `JAVA_HOME` | Service unit | Executable và `java.version` của process | Xác nhận JDK thực sự được chọn |
| `gradle-test` | JVM option | `-Xmx1g` | Cấu hình test task | JVM fork chạy test | Đánh giá riêng với JVM chạy ứng dụng |

Khi cùng một giá trị được khai báo ở nhiều nơi, tạo nhiều dòng nguồn hoặc một nhóm có quan hệ nguồn gốc rõ ràng. Không xóa bớt các nguồn trùng nhau trước khi biết nguồn nào thực sự có hiệu lực.

## 8. Phân loại cấu hình theo rủi ro khi nâng cấp JDK

Sau khi thu thập, cần phân loại để biết hạng mục nào phải kiểm tra trước khi chuyển runtime.

### 8.1. JVM option phụ thuộc phiên bản hoặc nhà cung cấp

Các option `-XX` và `-X` thường cần được đối chiếu với JDK đích. Một option có thể:

- Còn được hỗ trợ và giữ semantics.
- Được hỗ trợ nhưng đổi giá trị mặc định.
- Bị deprecated và phát cảnh báo.
- Bị obsolete hoặc không còn tác dụng như trước.
- Bị loại bỏ và làm JVM từ chối khởi động.
- Chỉ tồn tại trên một implementation hoặc một dòng JDK cụ thể.

Đặc biệt chú ý option GC, memory sizing, compiler, JIT, container awareness, diagnostic, module access và option nội bộ. Đừng sao chép nguyên bộ flag của JDK cũ sang JDK mới mà không kiểm chứng.

### 8.2. System property do JDK hoặc thư viện định nghĩa

Một số property có ý nghĩa do JDK hoặc thư viện quy định; giá trị mặc định và cách xử lý có thể thay đổi theo phiên bản. Ví dụ có thể liên quan đến encoding, timezone, TLS, proxy, truststore, logging hoặc reflective access. Cần xác định property thuộc JDK, thư viện bên thứ ba hay ứng dụng tự định nghĩa.

Property do ứng dụng tự định nghĩa thường không bị JVM tự kiểm tra. Điều đó không có nghĩa chúng an toàn: code có thể đổi tên khóa, thay default hoặc thay cách parse. Cần tìm nơi đọc property, không chỉ nơi khai báo.

### 8.3. Biến môi trường phụ thuộc nền tảng

Các biến như `JAVA_HOME`, `PATH`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, `MAVEN_OPTS` và `GRADLE_OPTS` có semantics khác nhau. Migration có thể thay đổi image, shell, service manager hoặc build agent, khiến biến không còn được truyền như trước.

Biến ứng dụng như `APP_REGION`, `SPRING_PROFILES_ACTIVE` hoặc biến kết nối dịch vụ phụ thuộc framework và ứng dụng. Cần kiểm tra cách framework ánh xạ biến sang property, bao gồm quy tắc đặt tên, kiểu dữ liệu, thứ tự ưu tiên và profile đang hoạt động. Không suy luận một quy tắc ưu tiên chung cho mọi framework.

### 8.4. Cấu hình có thể thay đổi lúc runtime

Một số system property có thể được sửa qua `System.setProperty`, một số cấu hình ứng dụng có thể refresh từ config server, còn JVM flag thường chỉ có thể đặt lúc khởi động hoặc chỉ một số flag được phép thay đổi bằng diagnostic command. Inventory cần ghi rõ thời điểm đọc và cơ chế cập nhật.

Nếu một cấu hình chỉ có hiệu lực lúc startup, thay đổi environment hoặc file sau khi process đã chạy không làm process tự nhận giá trị mới. Cần restart hoặc dùng cơ chế refresh được ứng dụng hỗ trợ. Ngược lại, nếu config refresh có thể thay đổi hành vi mà không restart, phải kiểm tra cả trạng thái trước và sau refresh.

## 9. Đối chiếu inventory khi chuyển sang JDK mới

Khi đã có baseline, thực hiện đối chiếu theo từng process và từng môi trường. Không chỉ chạy `java -version` trên máy build rồi kết luận toàn hệ thống đã dùng JDK đích.

### Bước 1: Chốt JDK đích cho từng process

Ghi rõ phiên bản Java, nhà cung cấp, distribution và đường dẫn runtime mà từng process phải dùng. Một hệ thống có thể cố ý dùng JDK khác nhau cho build tool, test, ứng dụng và công cụ migration; hãy ghi nhận quyết định đó thay vì giả định một JDK chung.

### Bước 2: Đối chiếu từng JVM option

Với mỗi option, kiểm tra tài liệu của nhà cung cấp và phiên bản JDK đích, sau đó chạy thử trên đúng binary. Xác nhận JVM khởi động, flag có tồn tại và giá trị hiệu lực phù hợp. Có thể dùng `java -XX:+PrintFlagsFinal -version` để khảo sát flag của binary đích và `jcmd` trên process thử nghiệm để xem trạng thái runtime.

Không dùng `-XX:+IgnoreUnrecognizedVMOptions` như cách sửa migration mặc định. Option không được nhận diện có thể đang bảo vệ một yêu cầu quan trọng; bỏ qua cảnh báo có thể làm thay đổi GC, bộ nhớ, module access hoặc chẩn đoán mà không ai nhận ra. Nếu cần bỏ option, phải chứng minh option đó không còn cần thiết hoặc đã có cơ chế thay thế.

### Bước 3: Đối chiếu system property

Với từng property, xác định owner và nơi đọc. Phân biệt property của JDK, property của thư viện và property ứng dụng. So sánh giá trị mặc định giữa hai JDK; nếu ứng dụng dựa vào default, hãy quyết định có nên đặt giá trị tường minh để giữ hành vi ổn định hay không.

Đặc biệt kiểm tra property đã bị đổi tên, không còn hỗ trợ hoặc có semantics mới. Đừng chỉ xác nhận property vẫn xuất hiện trong `System.getProperties()`; cần xác nhận thành phần tiêu thụ nó còn đọc và hiểu giá trị đó.

### Bước 4: Đối chiếu environment và cách khởi chạy

Xác nhận `JAVA_HOME`, executable được tìm thấy qua `PATH`, biến inject option và các biến ứng dụng đều được truyền tới đúng process. Kiểm tra script mới, container image mới, service unit mới và cấu hình của orchestrator. Đảm bảo `-D` vẫn đứng ở vị trí của JVM option, không bị chuyển thành argument của ứng dụng.

### Bước 5: Chạy thử theo đúng môi trường

Khởi chạy từng process trên JDK đích với cấu hình đã chuyển đổi. Thu lại `java.version`, `VM.command_line`, flag, system property đã chọn và các environment key được phép quan sát. So sánh với baseline theo semantics, không chỉ theo chuỗi.

### Bước 6: Kiểm tra hành vi và vận hành

Chạy test chức năng, integration, tải và các kịch bản lỗi liên quan đến cấu hình. Với memory option, kiểm tra cả giới hạn heap, native memory và container memory. Với GC, xem log/metric pause và throughput. Với module access, chạy các đường code dùng reflection. Với TLS/proxy/truststore, kiểm tra kết nối thực tế tới endpoint cần thiết.

### Bước 7: Theo dõi sau rollout

Triển khai theo từng môi trường hoặc nhóm instance, giữ khả năng rollback và theo dõi metric phù hợp. Khi phát hiện khác biệt, truy ngược từ process cụ thể tới nguồn cấu hình, thay vì sửa một biến toàn cục mà chưa rõ phạm vi tác động.

## 10. Những nhầm lẫn thường gặp khi kiểm kê

- **Chỉ xem `JAVA_HOME`:** biến này không chứng minh executable mà process thực sự dùng. `PATH`, wrapper, container image hoặc đường dẫn tuyệt đối có thể chọn JDK khác.
- **Đồng nhất `JAVA_OPTS` với option của Java launcher:** đây thường là biến do script quy ước; phải tìm nơi script đọc nó.
- **Coi `MAVEN_OPTS` hoặc `GRADLE_OPTS` là cấu hình JVM ứng dụng:** chúng thường cấu hình JVM chạy build tool; test hoặc application fork có thể có bộ option riêng.
- **Chỉ đọc file cấu hình:** giá trị thực tế có thể được inject từ môi trường, secret reference, service manager hoặc platform deployment.
- **Chỉ xem command line:** `JAVA_TOOL_OPTIONS` và các nguồn khác có thể bổ sung option; code còn có thể thay đổi system property sau khi JVM khởi động.
- **Coi system property và environment là một:** `System.getProperty()` và `System.getenv()` đọc hai nguồn khác nhau. Framework có thể ánh xạ chúng theo quy tắc riêng.
- **Kiểm tra JVM build thay cho JVM runtime:** Gradle daemon, test fork, compiler và ứng dụng có thể là các process riêng.
- **Lưu nguyên output chẩn đoán:** command line, system property và environment có thể chứa secret hoặc thông tin nội bộ.
- **Giữ tất cả flag cũ theo thói quen:** option cũ có thể không còn tác dụng, bị loại bỏ hoặc thay đổi default trên JDK mới.
- **Xóa option chỉ vì JDK mới khởi động được:** một option có thể ảnh hưởng hiệu năng, giới hạn bộ nhớ, khả năng truy cập module hoặc chẩn đoán khi lỗi xảy ra.
- **Không ghi nguồn và owner:** khi giá trị sai xuất hiện ở production, nhóm vận hành sẽ khó biết cần sửa manifest, script, pipeline hay code.

## 11. Checklist hoàn tất inventory

- [ ] Đã liệt kê các process Java trong build, test, runtime, batch và vận hành.
- [ ] Đã ghi JDK vendor, version, executable/image và môi trường của từng process.
- [ ] Đã tìm JVM option trong source, build config, script, service manager, container, orchestrator và CI/CD.
- [ ] Đã tìm system property `-D` và xác định nơi code/framework đọc hoặc thay đổi property.
- [ ] Đã kiểm tra các biến môi trường có thể chọn JDK hoặc bổ sung JVM option.
- [ ] Đã phân biệt `JAVA_OPTS`, `MAVEN_OPTS`, `GRADLE_OPTS`, `JAVA_TOOL_OPTIONS` và `JDK_JAVA_OPTIONS` theo nơi sử dụng thực tế.
- [ ] Đã thu thập bằng chứng runtime cho command line, VM flags và system properties ở process đại diện.
- [ ] Đã kiểm tra environment của process theo cách phù hợp với OS/container và quyền truy cập.
- [ ] Đã ghi nguồn, owner, purpose, scope, thời điểm đọc và độ nhạy cảm của từng cấu hình.
- [ ] Đã phân loại option/property theo mức phụ thuộc JDK và hành động migration.
- [ ] Đã che secret và giới hạn dữ liệu chẩn đoán được chia sẻ.
- [ ] Đã có baseline đủ rõ để so sánh với process chạy trên JDK đích.

## 12. Kết luận

Kiểm kê JVM option, system property và biến môi trường giúp xác định cấu hình thực sự điều khiển từng tiến trình Java. Muốn có inventory đáng tin cậy, cần kết hợp tìm kiếm tĩnh trong repository và nền tảng triển khai với quan sát process đang chạy; phân biệt cấu hình khai báo, cấu hình được truyền vào và giá trị hiệu lực; đồng thời ghi lại nguồn, owner, mục đích và mức phụ thuộc JDK. Bộ dữ liệu đó tạo baseline để migration có thể đối chiếu từng process trên runtime mới, phát hiện option lỗi thời hoặc cấu hình bị thất lạc và giữ hành vi vận hành ổn định.
