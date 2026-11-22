# Tham số khởi động trong script, systemd hoặc cấu hình Kubernetes

## 1. Bối cảnh: tham số khởi động cũng là hợp đồng tương thích Java

Trong **Java Advance Compatibility Migration**, nhóm thường kiểm tra source code, dependency, API và bytecode nhưng quên rằng JVM ở môi trường thật có thể được khởi động bằng một tổ hợp flags hoàn toàn khác local. Một ứng dụng chạy được bằng lệnh java -jar trên máy phát triển vẫn có thể lỗi khi triển khai qua shell script, Linux systemd hoặc Kubernetes.

Ví dụ:

- JVM flag bị đặt sau -jar nên không có tác dụng lên JVM mà trở thành application argument.
- Một script tự ghép chuỗi command rồi dùng eval, làm hỏng quoting hoặc gây rủi ro injection.
- systemd ExecStart được viết như lệnh Bash, trong khi systemd không tự dùng shell để xử lý mọi cú pháp.
- EnvironmentFile đặt JAVA_OPTS nhưng startup command không hề đọc biến đó.
- Docker image chứa ENTRYPOINT thiết lập agent và TLS, còn Kubernetes command override entrypoint khiến các bước chuẩn bị bị bỏ qua.
- Shell chạy như PID 1 và không forward SIGTERM đúng cách, khiến shutdown hooks không được gọi theo kỳ vọng.
- JDK mới từ chối các VM options đã bị loại bỏ, hoặc đọc cgroups khiến kích thước heap/số processor hiệu dụng khác trước.
- Truststore, heap dump, GC log và agent paths phù hợp trên VM nhưng thiếu trong container.
- Secret xuất hiện trong -D hoặc application arguments và bị lộ trong process list, log hay diagnostic output.

Do đó, cần xem **artifact + JDK runtime + startup command + environment + resource limits + lifecycle settings** là một tổ hợp phải kiểm chứng. Bài học thuộc chương *Đóng gói và môi trường*, tập trung vào cách quản lý tham số từ script, systemd đến Kubernetes khi nâng hoặc chuyển đổi Java.

Sau bài học, người đọc có thể phân biệt JVM options và application arguments, tổ chức startup scripts an toàn, viết systemd unit/drop-in đúng semantics, hiểu Docker ENTRYPOINT/CMD và Kubernetes command/args, quản lý JVM environment variables, kiểm tra effective flags và thiết kế test/rollback sau migration.

## 2. Cú pháp Java launcher và vị trí của mỗi tham số

Một số dạng launcher phổ biến:

~~~text
java [JVM/launcher options] -jar application.jar [application arguments]
java [JVM/launcher options] -cp classpath com.example.Main [application arguments]
java [JVM/launcher options] --module-path modules -m module.name/com.example.Main [application arguments]
~~~

Ví dụ:

~~~bash
java -Xms256m -Xmx768m -Dapp.mode=production \
    -jar /opt/app/app.jar --server.port=8080
~~~

| Thành phần | Nhóm | Ý nghĩa |
|---|---|---|
| java | Executable | Java launcher từ JDK/JRE được chọn. |
| -Xms256m | JVM option | Initial heap size. |
| -Xmx768m | JVM option | Maximum Java heap size. |
| -Dapp.mode=production | JVM system property | Có thể được ứng dụng/framework đọc. |
| -jar /opt/app/app.jar | Main selector | Chọn executable JAR để chạy. |
| --server.port=8080 | Application argument | Được truyền cho main; chỉ có tác dụng nếu ứng dụng/framework hỗ trợ. |

### 2.1. JVM flags phải đứng trước -jar, main class hoặc -m

Ví dụ sai nếu muốn đặt kích thước heap:

~~~bash
java -jar app.jar -Xmx768m
~~~

Trong lệnh trên, -Xmx768m là **application argument** sau -jar, không phải JVM heap option. Java launcher không dùng nó để đổi Xmx.

Tương tự:

~~~bash
java -jar app.jar -Dapp.mode=production
~~~

không đặt app.mode thành system property theo cách JVM launcher hiểu khi -D được sử dụng trước -jar.

Đây là khác biệt quan trọng khi chuyển một lệnh khởi động thành danh sách args trong Kubernetes hoặc khi dùng Docker CMD để bổ sung arguments sau image ENTRYPOINT.

### 2.2. Application arguments và JVM system properties khác nhau

Ví dụ Java:

~~~java
import java.util.Arrays;

public final class StartupArguments {
    public static void main(String[] args) {
        System.out.println("args=" + Arrays.toString(args));
        System.out.println("app.mode=" +
                System.getProperty("app.mode"));
    }
}
~~~

Nếu chạy:

~~~bash
java -Dapp.mode=production StartupArguments --profile=blue
~~~

thì -Dapp.mode là system property, còn --profile=blue xuất hiện trong args. Một số framework có cơ chế riêng để ánh xạ application arguments thành configuration properties; điều đó không có nghĩa mọi Java application tự hiểu --profile hoặc --server.port.

### 2.3. Không trộn các kiểu chọn main

Với executable JAR, dùng -jar. Với main class trực tiếp, dùng -cp/--class-path và tên class. Với named module, dùng --module-path và -m/--module theo cấu trúc module.

Việc chuyển từ classpath sang module path trong migration cần được kiểm thử riêng vì service discovery, reflection, exports/opens và module resolution có thể khác. Đừng thêm -jar, main class và -m cùng một command mà không có thiết kế rõ ràng.

## 3. Các nhóm JVM options thường liên quan khi nâng JDK

| Nhóm | Một số tùy chọn thường gặp | Vì sao cần xem khi migration |
|---|---|---|
| Heap | -Xms, -Xmx | Giới hạn heap và memory footprint. |
| Ergonomic memory | -XX:MaxRAMPercentage, -XX:InitialRAMPercentage | Cách tính heap khi không đặt tường minh Xmx/Xms. |
| CPU | -XX:ActiveProcessorCount | Ảnh hưởng số processors JVM dùng cho một số quyết định. |
| Garbage collection | -XX:+UseG1GC và các tùy chọn collector tương ứng | GC và flag cũ có thể bị loại hoặc đổi default. |
| Diagnostics | -Xlog, -XX:+HeapDumpOnOutOfMemoryError | Logging, dump và storage permissions. |
| Agents | -javaagent, -agentpath, -agentlib | Phụ thuộc Java/bytecode/JVMTI và OS/architecture. |
| Module access | --add-opens, --add-exports, --add-modules | Một số thư viện legacy cần quyền truy cập tạm thời. |
| Encoding/timezone | -Dfile.encoding, -Duser.timezone | Có thể ảnh hưởng output và test behavior. |
| TLS | -Djavax.net.ssl.trustStore và thuộc tính liên quan | Certificate trust, mTLS và keystore paths. |
| Application framework | --spring.profiles.active, --server.port, --app.config | Tùy framework, thường là application arguments. |

Đây là nhóm ví dụ cho JVM/Java launcher phù hợp; không phải mọi JVM vendor/release đều hỗ trợ cùng flags. Khi chuyển từ HotSpot sang JVM implementation khác, cần kiểm tra tài liệu của implementation đó.

### 3.1. Tách JVM flags, application config và secrets

Một startup contract tốt phân loại:

~~~text
JVM options: heap, GC, module access, JVM diagnostics
Application arguments: profile, port, config path, feature switches
Environment/config files: endpoint, log level, app-specific settings
Secrets: secret manager hoặc protected credential files
Deployment: CPU/memory, probes, restart, filesystem permissions
~~~

Không dùng một chuỗi “JAVA_OPTS” khổng lồ làm nơi chứa cả JVM flags, URL, password và command shell. Phần này đặc biệt quan trọng khi nhiều nhóm cùng sửa startup configuration.

## 4. Nguồn cấu hình và thứ tự áp dụng

Một runtime có thể có nhiều nguồn:

~~~text
Script / systemd unit / container image
                │
                ▼
 Environment và deployment config
                │
                ▼
 Java launcher + JVM options
                │
                ▼
   Main class / executable JAR
                │
                ▼
Application arguments / framework configuration
                │
                ▼
Runtime business behavior
~~~

Sơ đồ mô tả các lớp trách nhiệm, **không** tuyên bố một precedence order chung cho mọi framework.

Ví dụ Spring Boot có precedence riêng giữa command-line arguments, environment variables, system properties và configuration files. Ứng dụng tự viết có thể chỉ đọc một tập nhỏ. Tương tự, JVM flags trùng lặp có behavior phụ thuộc JVM/launcher và option cụ thể; không nên thiết kế dựa trên quy tắc “flag nào xuất hiện sau luôn thắng” khi chưa kiểm chứng trên JDK đích.

Mỗi setting quan trọng nên có **một nguồn sự thật** hoặc một precedence rule được văn bản hóa và test.

## 5. Startup script trên Linux/Unix

Startup script có thể giúp chọn Java executable, kiểm tra cấu hình và chuẩn bị đường dẫn. Tuy nhiên, nó cũng là nơi dễ mắc lỗi quoting, tách arguments và signal handling.

### 5.1. Ví dụ POSIX shell script đơn giản

Giả sử file start.sh nằm trong /opt/myapp và app.jar ở cùng thư mục:

~~~sh
#!/bin/sh
set -eu

APP_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

exec /usr/bin/java \
    -Xms256m \
    -Xmx768m \
    -XX:+ExitOnOutOfMemoryError \
    "-Dapp.config=$APP_DIR/conf/app.yml" \
    -jar "$APP_DIR/app.jar" \
    "$@"
~~~

Ví dụ này sử dụng lệnh Java cố định ở /usr/bin/java và giả định shell/utility hỗ trợ cú pháp được dùng; đường dẫn cụ thể phải được thay theo host/container. Trong một môi trường có wrapper quản lý JDK theo version, có thể dùng đường dẫn tuyệt đối tới JDK đã phê duyệt thay vì phụ thuộc PATH.

Điểm cần chú ý:

1. Dùng đường dẫn đến vị trí script để xác định artifact, không phụ thuộc current working directory.
2. Quote đường dẫn có thể chứa khoảng trắng.
3. JVM flags đứng trước -jar.
4. "$@" chuyển tiếp từng argument cho ứng dụng.
5. **exec** thay shell process bằng Java thay vì để shell đứng giữa Java và supervisor.
6. Startup không tự in secrets ra stdout/stderr.

Không nên sử dụng eval hoặc thực thi tùy ý nội dung của biến môi trường như shell command.

### 5.2. Quoting sai làm đổi ý nghĩa arguments

Ví dụ đường dẫn có dấu cách:

~~~text
/opt/My Application/config/app.yml
~~~

Không an toàn về mặt phân tách arguments:

~~~sh
java -Dapp.config=/opt/My Application/config/app.yml -jar app.jar
~~~

Cách rõ ràng:

~~~sh
java "-Dapp.config=/opt/My Application/config/app.yml" -jar app.jar
~~~

Quoting cũng cần áp dụng với Java agent paths, truststore paths, heap dump paths, application JAR và parameters người dùng truyền vào.

### 5.3. "$@" và "$*" không tương đương

Khi script được gọi:

~~~sh
./start.sh "--display-name=Example App" --profile=staging
~~~

script dùng "$@" sẽ truyền hai application arguments riêng biệt. Trong nhiều cách dùng, "$*" gộp positional arguments thành một chuỗi và có thể làm mất ranh giới arguments.

Đừng nối tất cả arguments thành một string rồi để shell parse lại, vì dữ liệu có chứa khoảng trắng, wildcard hoặc ký tự đặc biệt sẽ không được bảo toàn.

### 5.4. Pattern nguy hiểm: ghép lệnh rồi eval

Không nên:

~~~sh
JAVA_OPTS="-Xmx768m"
CMD="java $JAVA_OPTS -jar app.jar"
eval "$CMD"
~~~

Nếu một phần string bị chỉnh sửa từ environment/secret/config, eval có thể biến dữ liệu thành cú pháp shell. Nó cũng gây khó khăn khi quote đường dẫn, options có dấu cách và các arguments cần giữ nguyên.

Ưu tiên truyền từng flag rõ ràng hoặc dùng Java argument file được quản lý.

## 6. Java argument files để quản lý nhiều options

Ở JDK có hỗ trợ argument files cho Java launcher, có thể đặt một số options trong tệp:

File /etc/myapp/jvm.args:

~~~text
-Xms256m
-Xmx768m
-Duser.timezone=UTC
-Xlog:gc*:stdout:time,uptime,level,tags
~~~

Lệnh:

~~~sh
java @/etc/myapp/jvm.args -jar /opt/myapp/app.jar
~~~

Ưu điểm:

- Ít phụ thuộc cách escape của shell/systemd/YAML khi danh sách options dài.
- Dễ quản lý bằng versioned configuration.
- Thuận tiện tách JVM options với application arguments.

Hạn chế:

- Tệp dùng cú pháp Java launcher argument file, không phải shell script; không giả định shell expansion tự xảy ra bên trong.
- Cần bảo đảm Java launcher của JDK đích hỗ trợ cú pháp dự kiến.
- File permissions và source provenance vẫn phải được quản lý.
- Không nên lưu secrets trong tệp chỉ vì tệp không hiện hết trên command line.
- Cần tránh khai báo cùng một JVM flag xung đột ở argfile, command trực tiếp và environment.

Nếu dùng argfile trong systemd/Kubernetes, cần mount hoặc copy file vào đúng path trước khi Java chạy.

## 7. Các biến môi trường liên quan Java

| Biến | Vai trò | Cảnh báo |
|---|---|---|
| JAVA_HOME | Quy ước đường dẫn cài JDK/JRE thường được script/build tool dùng. | Java launcher không tự bắt buộc lấy binary từ JAVA_HOME. |
| JAVA_TOOL_OPTIONS | Có thể được JVM nhận ở thời điểm khởi tạo để bổ sung một số VM options. | Không đồng nghĩa toàn bộ Java launcher options. |
| JDK_JAVA_OPTIONS | Được Java launcher của các JDK hỗ trợ đọc để bổ sung launcher options. | Có các hạn chế với những options thay đổi main selector/launcher behavior. |
| JAVA_OPTS | Tên biến quy ước do script/app server/image đặt. | **Java launcher không tự đọc JAVA_OPTS theo chuẩn.** |
| _JAVA_OPTIONS | Biến được một số JVM/HotSpot implementations xử lý. | Không nên coi là cấu hình portable bắt buộc của mọi Java runtime. |

### 7.1. JAVA_TOOL_OPTIONS

Ví dụ:

~~~sh
export JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0 -Dapp.mode=production"
java -jar app.jar
~~~

Trong các JVM hỗ trợ, các VM options có thể được đưa vào quá trình khởi tạo JVM. Tùy chọn này hữu ích khi không thể sửa trực tiếp launcher command, nhưng không thể coi là bản thay thế chung cho mọi command-line option như -jar hay tên main class.

Một số JVM hiển thị thông báo “Picked up JAVA_TOOL_OPTIONS”; đó có thể là thông tin hữu ích khi chẩn đoán, nhưng không chứng minh mọi option được truyền đều đã có ý nghĩa theo dự kiến.

### 7.2. JDK_JAVA_OPTIONS

Ví dụ:

~~~sh
export JDK_JAVA_OPTIONS="-Xmx768m -Dapp.mode=production"
java -jar app.jar
~~~

Biến được Java launcher hỗ trợ ở các JDK phù hợp và có một số restriction riêng đối với options mà nó được phép chứa. Cần tham khảo Java launcher documentation của runtime mục tiêu; không đưa -jar, main selector hoặc các options bị cấm vào biến rồi kỳ vọng nó hoạt động.

Nếu JDK_JAVA_OPTIONS và image ENTRYPOINT cùng đặt -Xmx hoặc GC, phải xác minh effective behavior và sửa cấu hình để tránh xung đột.

### 7.3. JAVA_OPTS không tự hoạt động

Ví dụ:

~~~sh
export JAVA_OPTS="-Xmx512m"
java -jar app.jar
~~~

Lệnh Java thông thường phía trên **không tự đọc JAVA_OPTS**. Một số application servers, build scripts hoặc Docker images cung cấp wrapper có xử lý JAVA_OPTS, nhưng đó là contract của wrapper, không phải tính năng tiêu chuẩn của launcher.

Khi thấy JAVA_OPTS trong systemd unit hoặc Kubernetes ConfigMap, phải tìm xem startup script thực tế có đọc nó hay không.

### 7.4. Dùng nguồn cấu hình duy nhất khi có thể

Quy định rõ:

- Flags nào được mã hóa trong image hoặc unit.
- Flags nào thay đổi theo môi trường.
- Biến nào chỉ dành cho application configuration.
- Secret nào phải được đọc từ protected file/secret manager.
- Cách kiểm tra Java process thực tế.

Tránh tình trạng cùng một -Xmx được đặt ở Dockerfile, JAVA_TOOL_OPTIONS, JDK_JAVA_OPTIONS và Kubernetes command mà không ai chịu trách nhiệm thứ tự ưu tiên.

## 8. systemd service: không phải một shell script tự do

Trên Linux, systemd thường quản lý Java service với restart policy, process supervision, signals, logging và cgroup limits.

Ví dụ unit file:

~~~ini
[Unit]
Description=Example Java Application
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=javaapp
Group=javaapp
WorkingDirectory=/opt/javaapp
Environment=APP_ENV=production
ExecStart=/usr/bin/java -Xms256m -Xmx768m -XX:+ExitOnOutOfMemoryError -jar /opt/javaapp/app.jar --app.env=production
Restart=on-failure
RestartSec=5s
TimeoutStopSec=60s
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
~~~

Ví dụ giả định user/group javaapp, file app.jar và đường dẫn /usr/bin/java tồn tại, service có permission cần thiết.

### 8.1. ExecStart không tự dùng cú pháp Bash

Không được coi những ký tự như pipe, redirect, && hoặc command substitution trong ExecStart là cú pháp shell được xử lý mặc định. systemd có quy tắc riêng để parse executable và arguments.

Nếu chỉ chạy Java với flags rõ ràng, ExecStart trực tiếp thường ít rủi ro hơn việc thêm shell wrapper. Nếu ứng dụng thật sự cần preflight script, unit có thể gọi script có shebang và script nên exec Java ở bước cuối.

### 8.2. WorkingDirectory và quyền filesystem

WorkingDirectory hỗ trợ ứng dụng xử lý đường dẫn tương đối nhất quán, nhưng với JAR, agent, truststore và config quan trọng thường nên dùng absolute paths.

Chạy service dưới dedicated user/group với quyền tối thiểu. Nếu dùng systemd sandboxing (ProtectSystem, ReadWritePaths, PrivateTmp...), phải thử các đường dẫn ghi log, temporary files, heap dumps và application data. Thiếu quyền có thể chỉ lộ khi xảy ra sự cố, không nhất thiết ngay lúc startup.

### 8.3. Type=simple và readiness

Type=simple hữu ích cho Java process chạy foreground. Nhưng systemd coi process bắt đầu không đồng nghĩa application đã khởi tạo xong database, cache hoặc HTTP endpoint. Nếu ứng dụng cần readiness semantics chặt hơn, phải thiết kế health/readiness theo stack phù hợp.

Đừng coi systemctl status trả active là bằng chứng mọi business endpoint đã sẵn sàng.

## 9. EnvironmentFile của systemd

Ví dụ:

~~~ini
[Service]
EnvironmentFile=-/etc/javaapp/javaapp.env
ExecStart=/usr/bin/java -Xmx768m -jar /opt/javaapp/app.jar
~~~

File javaapp.env:

~~~text
APP_ENV=production
LOG_LEVEL=INFO
~~~

EnvironmentFile có cú pháp của systemd, **không tự được shell source**. Dấu trừ trước path biểu thị file vắng mặt có thể được bỏ qua theo cú pháp liên quan; với file bắt buộc, nên khai báo không có dấu trừ để thiếu file là lỗi vận hành.

Nếu file chứa:

~~~text
JAVA_OPTS=-Xmx1024m
~~~

thì biến JAVA_OPTS vẫn không tự biến thành command-line argument của Java, trừ khi ExecStart hoặc một wrapper có logic sử dụng biến đó.

### 9.1. Expansion của environment trong systemd

systemd hỗ trợ một số hình thức thay thế biến trong command line, nhưng cách phân tách giữa $VAR và dạng có dấu ngoặc là đặc thù systemd, không giống hoàn toàn shell. Nếu biến chứa nhiều JVM arguments, cần kiểm tra semantics cho đúng systemd version.

Trong đa số dịch vụ đơn giản, nên đặt flags cố định trực tiếp trong ExecStart hoặc dùng Java argument file, thay vì phụ thuộc một chuỗi biến chứa nhiều flags khó parse.

### 9.2. Không dùng systemd environment làm nơi giữ secrets không kiểm soát

Các biến môi trường có thể bị hiển thị qua cấu hình chẩn đoán hoặc process environment nếu quyền truy cập cho phép. Không đưa database password, private key hoặc bearer token trực tiếp vào ExecStart bằng -Dsecret=... .

Ở những systemd releases hỗ trợ, có thể dùng cơ chế credentials như LoadCredential hoặc protected credential files và ứng dụng đọc theo đường dẫn phù hợp. Quyền đọc file và vòng đời rotation cần được xác định rõ.

## 10. systemd drop-in và override ExecStart

Nếu unit được package hoặc nền tảng quản lý, có thể dùng drop-in thay vì sửa trực tiếp vendor unit.

Ví dụ:

~~~sh
sudo systemctl edit javaapp.service
~~~

Nội dung override:

~~~ini
[Service]
ExecStart=
ExecStart=/usr/bin/java -Xms384m -Xmx1024m -jar /opt/javaapp/app.jar --app.env=production
~~~

Trong service type thông thường như Type=simple, để thay ExecStart cũ bằng một dòng mới cần reset list trước bằng **ExecStart= rỗng**. Chỉ thêm một ExecStart thứ hai có thể khiến unit không hợp lệ.

### 10.1. Nạp và áp dụng thay đổi

~~~sh
sudo systemctl daemon-reload
sudo systemctl restart javaapp.service
sudo systemctl status javaapp.service
sudo journalctl -u javaapp.service -n 100 --no-pager
~~~

Đây là các lệnh vận hành minh họa. Restart production cần change window, replication/rolling strategy và rollback plan phù hợp.

Việc sửa unit file hoặc EnvironmentFile **không tự đổi flags của JVM đang chạy**. Đối với những JVM options chỉ có hiệu lực khi khởi động, cần restart process.

### 10.2. Kiểm tra unit có hiệu lực

~~~sh
systemctl cat javaapp.service
systemctl show javaapp.service -p ExecStart -p Environment -p FragmentPath -p DropInPaths
~~~

Cẩn trọng khi lưu output vì nếu hệ thống cấu hình sai và chứa secrets trong command/environment, kết quả có thể lộ thông tin nhạy cảm. Để xác minh JVM flags thật sự hiệu lực, cần thêm quan sát từ Java process sau khi restart.

## 11. systemd resource limits và JVM ergonomics

systemd có thể quản lý tài nguyên qua cgroups:

~~~ini
[Service]
MemoryMax=2G
CPUQuota=150%
TasksMax=1024
LimitNOFILE=65536
~~~

Ý nghĩa:

- MemoryMax là memory limit của service cgroup, không chỉ Java heap.
- CPUQuota=150% cho ngân sách CPU time khoảng 1,5 CPU khi cơ chế quota hoạt động.
- TasksMax hạn chế số tasks/threads theo controller/chính sách phù hợp.
- LimitNOFILE điều chỉnh giới hạn file descriptors theo hệ điều hành.

Không đặt -Xmx bằng đúng MemoryMax mà không tính Metaspace, code cache, thread stacks, direct buffers, native libraries, page cache và các khoản memory accounting khác.

Không dùng -XX:ActiveProcessorCount=8 để tưởng rằng container/service có thêm CPU khi kernel chỉ cho quota tương đương 1,5 CPU.

Khi nâng JDK, cần ghi lại cgroups version, effective CPU count, heap max, GC threads và memory usage; JDK mới có thể nhận diện container limits khác với JDK cũ.

## 12. Logging và diagnostic paths trong systemd

Với ứng dụng Java chạy foreground, ghi logs ra stdout/stderr để journald thu thập có thể đơn giản hơn việc để nhiều log files không được quản lý.

Ví dụ HotSpot unified GC logging trên JDK hỗ trợ:

~~~sh
java -Xlog:gc*:stdout:time,uptime,level,tags -jar app.jar
~~~

Nếu cần GC log file:

~~~text
-Xlog:gc*:file=/var/log/javaapp/gc.log:time,uptime,level,tags:filecount=5,filesize=10m
~~~

Khi dùng đường dẫn file:

- Tạo directory và đặt quyền ghi đúng user.
- Đảm bảo sandbox policy cho phép ghi.
- Có disk quota/retention, tránh ổ đĩa đầy.
- Phân biệt GC log với application log.
- Xem xét sensitive data trong heap dump/crash dump.

Một số GC logging flags cũ có thể bị thay bằng unified logging hoặc không còn được hỗ trợ; kiểm tra trên JDK đích.

## 13. Docker ENTRYPOINT và CMD

Docker/container image thường cung cấp ENTRYPOINT (program mặc định) và CMD (default command/arguments), với hai dạng khai báo chính.

Exec form:

~~~dockerfile
ENTRYPOINT ["java", "-Xmx768m", "-jar", "/app/app.jar"]
~~~

Shell form:

~~~dockerfile
ENTRYPOINT java -Xmx768m -jar /app/app.jar
~~~

Trong Linux containers, exec form thường giúp Java là tiến trình chính trực tiếp. Shell form thường chạy qua shell, có thể làm thay đổi signal forwarding và process supervision nếu không được thiết kế cẩn thận.

### 13.1. Ví dụ Dockerfile

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY app.jar /app/app.jar
USER 10001:10001

ENTRYPOINT ["java", "-XX:MaxRAMPercentage=65.0", "-XX:+ExitOnOutOfMemoryError", "-jar", "/app/app.jar"]
~~~

Đây là ví dụ, không phải image đã được tạo. Với hệ thống thực, cần pin image version/digest theo policy, kiểm tra Linux OS/architecture, file permissions và chọn memory percentage từ kết quả đo.

### 13.2. CMD để truyền application arguments

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
CMD ["--server.port=8080"]
~~~

Khi dùng mặc định, CMD được ghép làm arguments phía sau ENTRYPOINT. Vì -jar đã có trong ENTRYPOINT, --server.port=8080 là application argument.

**Không đặt -Xmx trong CMD của ví dụ này rồi tưởng nó đổi heap**: tham số đó sẽ nằm sau JAR. Muốn sửa JVM flags phải thay thiết kế ENTRYPOINT, dùng startup script/argument file hoặc cơ chế launcher environment phù hợp.

### 13.3. PID 1 và exec

Startup script dùng làm ENTRYPOINT nên kết thúc bằng:

~~~sh
exec java -jar /app/app.jar
~~~

khi không cần giữ một supervisor riêng. exec thay shell process bằng Java, làm signal và exit status đi trực tiếp đến Java. Nếu sử dụng init process chuyên dụng để reaping child processes, phải đảm bảo cơ chế forward SIGTERM phù hợp.

Shell wrapper không exec có thể làm Java không nhận SIGTERM đúng như mong muốn và buộc container bị kill sau termination grace period.

### 13.4. Không đóng gói production secrets trong Dockerfile

Không đưa private key, passwords hoặc tokens vào Dockerfile ENV/ARG hoặc image layers. Secrets cần được cấp phát lúc chạy qua secret store/volume với access control. Không log toàn bộ environment ở entrypoint để “xem cho dễ”.

## 14. Kubernetes command và args

Trong Pod spec:

- command thường override image ENTRYPOINT.
- args thường override image CMD.

Đây là khái niệm về **container command**, không phải Kotlin/Java main arguments tự động. Kubernetes không tự kiểm tra flag -Xmx có đặt đúng trước -jar hay không.

### 14.1. Ví dụ chạy Java trực tiếp

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: java-example
spec:
  replicas: 2
  selector:
    matchLabels:
      app: java-example
  template:
    metadata:
      labels:
        app: java-example
    spec:
      containers:
        - name: app
          image: example/java-app:1.0
          command: ["java"]
          args:
            - "-XX:MaxRAMPercentage=60.0"
            - "-XX:+ExitOnOutOfMemoryError"
            - "-jar"
            - "/app/app.jar"
            - "--server.port=8080"
          ports:
            - containerPort: 8080
~~~

Image example/java-app:1.0 là placeholder. Thứ tự arguments đúng: JVM flags trước -jar, application arguments sau JAR.

**Quan trọng:** Pod command trong ví dụ thay ENTRYPOINT của image. Nếu ENTRYPOINT cũ là wrapper thiết lập truststore, Java agent hoặc cấu hình native library, override có thể bỏ qua những bước đó.

### 14.2. Chỉ override args khi image hỗ trợ

Nếu image ENTRYPOINT đã là java -jar /app/app.jar và được thiết kế nhận application args:

~~~yaml
containers:
  - name: app
    image: example/java-app:1.0
    args:
      - "--app.env=staging"
      - "--server.port=8080"
~~~

Những args này truyền cho application. Nếu image dùng startup script có contract khác, cần xem logic script và Dockerfile trước khi dùng.

### 14.3. Kubernetes không tự khởi chạy shell với list command

Không tương đương:

~~~yaml
command: ["java -Xmx768m -jar /app/app.jar"]
~~~

và:

~~~yaml
command: ["java", "-Xmx768m", "-jar", "/app/app.jar"]
~~~

Trong dạng array, phần tử đầu phải chỉ ra executable. Nếu cần cố ý dùng shell:

~~~yaml
command: ["/bin/sh", "-c"]
args:
  - "exec java -Xmx768m -jar /app/app.jar"
~~~

thì image phải chứa shell và việc quoting/exec được quản lý đúng. Với distroless images, thường không có /bin/sh; hãy dùng exec-form command hoặc image entrypoint có sẵn.

## 15. Environment trong Kubernetes

Ví dụ truyền application environment và launcher options:

~~~yaml
containers:
  - name: app
    image: example/java-app:1.0
    env:
      - name: APP_ENV
        value: "production"
      - name: JDK_JAVA_OPTIONS
        value: "-XX:MaxRAMPercentage=60.0 -Dapp.mode=production"
~~~

JDK_JAVA_OPTIONS có thể hữu ích khi muốn giữ nguyên image ENTRYPOINT mà bổ sung các options được Java launcher hỗ trợ. Nhưng phải xác nhận:

- Launcher thực tế sử dụng đúng JDK/version.
- Options được phép qua JDK_JAVA_OPTIONS.
- Không có flag xung đột với ENTRYPOINT hoặc JAVA_TOOL_OPTIONS.
- Chính sách hiệu lực được kiểm chứng từ JVM thật.

Không dùng môi trường làm kênh cho mọi launcher option và không cố chèn -jar qua JDK_JAVA_OPTIONS.

### 15.1. ConfigMap cho cấu hình không nhạy cảm

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: java-example-config
data:
  APP_ENV: "production"
  LOG_LEVEL: "INFO"
~~~

Có thể tham chiếu:

~~~yaml
envFrom:
  - configMapRef:
      name: java-example-config
~~~

Đổi ConfigMap **không tự sửa environment variables của Java process đã khởi động**. Thông thường Pod cần được tạo lại/rollout để nhận env mới. Nếu mount ConfigMap làm file, cơ chế cập nhật và ứng dụng reload có semantics khác; JVM startup flags vẫn không tự động đổi.

### 15.2. Secret volumes và credential files

Với secret thực, ưu tiên cơ chế secret management của nền tảng theo chính sách tổ chức. Ví dụ mount Kubernetes Secret:

~~~yaml
volumes:
  - name: credentials
    secret:
      secretName: java-example-credentials
containers:
  - name: app
    image: example/java-app:1.0
    volumeMounts:
      - name: credentials
        mountPath: /run/secrets/javaapp
        readOnly: true
~~~

Ứng dụng phải được thiết kế để đọc file đúng path mà không log nội dung. Secret không tự mặc định an toàn trong mọi cluster; cần RBAC, audit, encryption at rest và quản lý rotation tương ứng.

Không truyền production password qua -Ddb.password=... hoặc --password=... vì command line và VM diagnostics có thể hiển thị nó.

## 16. Cgroup resource limits khác JVM heap settings

Ví dụ:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1500m"
    memory: "1Gi"
~~~

- requests.cpu liên quan Kubernetes scheduling và phân phối tài nguyên, **không phải hard CPU cap**.
- limits.cpu thường được thực thi bằng CPU quota trên Linux theo runtime policy.
- requests.memory dùng cho scheduling và chính sách liên quan.
- limits.memory là giới hạn bộ nhớ container, không chỉ heap.

Nếu limit.memory=1Gi, đặt -Xmx1g thường rủi ro vì JVM còn native/non-heap memory.

### 16.1. MaxRAMPercentage

Với JVM container-aware trên runtime phù hợp:

~~~text
-XX:MaxRAMPercentage=60.0
~~~

là cách đề nghị JVM tính ergonomic maximum heap dựa trên tỷ lệ của RAM nền tảng mà nó nhận diện. Nếu cơ sở là container 1 GiB, phép tính thô khoảng 614 MiB; giá trị thực tế phụ thuộc JDK ergonomics, các flags khác và điều kiện runtime.

Không dùng một tỷ lệ cố định cho mọi workload. Hệ thống dùng Netty/direct buffers, JNI, nhiều platform threads hoặc agents có thể cần native headroom lớn hơn.

### 16.2. CPU count và throttling

Với CPU limit 1500m, JVM có thể nhìn một số active processors nguyên theo cách implementation tính từ quota/cpuset. Runtime.availableProcessors() không trả về 1,5.

~~~text
-XX:ActiveProcessorCount=2
~~~

có thể điều chỉnh JVM ergonomics nhưng **không** cấp thêm CPU time. Nếu kernel quota thấp, thêm GC/executor threads có thể làm CPU throttling và latency tăng.

### 16.3. Thay JDK có thể đổi behavior dù YAML không đổi

JDK target có thể hỗ trợ cgroups v2 hoặc đọc giới hạn hiệu quả hơn JDK cũ; từ đó default Xmx, active processor count và GC thread count thay đổi. Khi so sánh phải ghi JDK vendor/update, kernel, cgroup mode và hiệu quả flags thật.

## 17. Probes và thời gian khởi động

Kubernetes có các probe:

- startupProbe: hỗ trợ thời gian startup theo cấu hình.
- readinessProbe: quyết định Pod có sẵn sàng nhận traffic.
- livenessProbe: phát hiện trạng thái cần restart theo policy.

Ví dụ:

~~~yaml
ports:
  - containerPort: 8080
startupProbe:
  httpGet:
    path: /health/startup
    port: 8080
  periodSeconds: 5
  failureThreshold: 30
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
~~~

Các endpoint là ví dụ; ứng dụng phải thực sự cung cấp chúng.

Nâng JDK có thể đổi startup time do classloading, GC, agent, TLS hoặc framework. Nếu probe threshold quá thấp, Pod có thể bị restart trước khi boot hoàn tất. Nếu readiness endpoint không kiểm tra dependency cần thiết, Pod có thể nhận traffic quá sớm.

Không dùng liveness probe phụ thuộc máy móc vào mọi dịch vụ ngoài rồi gây restart loop khi một dependency tạm thời gián đoạn. Thiết kế health semantics theo yêu cầu hệ thống.

### 17.1. Đồng bộ port và host

Nếu application nhận --server.port=9090 nhưng Pod containerPort/probe/Service vẫn trỏ 8080, JVM có thể khởi động tốt còn Pod không ready.

Kiểm tra:

- Application bind port và network interface.
- Probe port/path.
- Service targetPort và ingress/backend configuration.
- Management port nếu khác application port.

Tăng probe timeout không sửa được một sai sót cố định về port/path.

## 18. SIGTERM, graceful shutdown và termination grace

Khi Kubernetes dừng một Pod, process thường nhận SIGTERM theo lifecycle và có khoảng grace trước khi bị force kill nếu chưa dừng.

Ví dụ:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
~~~

Nếu Java là PID 1 hoặc signal được forward đúng, JVM có thể xử lý shutdown hooks và framework thực hiện graceful shutdown theo thiết kế.

Ví dụ Java:

~~~java
public final class ShutdownHookExample {
    public static void main(String[] args) throws Exception {
        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> System.out.println("Shutdown requested")));
        Thread.sleep(Long.MAX_VALUE);
    }
}
~~~

Đây chỉ là ví dụ hook; shutdown logic production phải quản lý transactions, request draining, message consumption, timeouts và resource cleanup.

### 18.1. Những câu hỏi cần kiểm tra

1. Java có nhận SIGTERM trực tiếp không?
2. Readiness đổi trạng thái thế nào trước khi ngừng nhận traffic?
3. Requests đang xử lý có thời gian hoàn thành hợp lý?
4. Background consumers, scheduler, transactions có dừng an toàn không?
5. Stop timeout của systemd và termination grace của Kubernetes có phù hợp?
6. Khi hết grace và SIGKILL, dữ liệu có thể ở trạng thái nào?

Shutdown hooks không được bảo đảm chạy trong mọi trường hợp như SIGKILL hoặc crash native. Không dùng sleep đơn giản trong preStop để thay cho drain logic đã được xác minh.

### 18.2. preStop

Kubernetes preStop hook có thể hỗ trợ một số quy trình drain, nhưng nó sử dụng một phần termination grace period. Nếu có hook, phải hiểu thời gian, failure behavior và signal ordering.

Không thêm preStop sleep vô điều kiện chỉ để che lỗi readiness propagation hoặc load balancer configuration.

## 19. VM flags bị thay đổi hoặc loại bỏ khi nâng Java

Khi chuyển từ JDK cũ, startup có thể dừng ngay:

~~~text
Unrecognized VM option
Error: Could not create the Java Virtual Machine
~~~

Nguyên nhân có thể:

- Option/collector không còn tồn tại.
- Cú pháp flag thay đổi.
- Flag thuộc một JVM implementation khác.
- Một legacy option giờ chỉ in warning hoặc không có hiệu lực.
- Option bị tách sai bởi shell/systemd/YAML.

Ví dụ cấu hình cho một collector đã bị loại khỏi HotSpot JDK mới không thể được “sửa” bằng cách giữ nguyên và thêm flag bỏ qua lỗi. Cần chọn collector và policy mới được hỗ trợ, rồi benchmark/so sánh hành vi.

### 19.1. Kiểm tra trên JDK đích

~~~sh
java -version
java -XshowSettings:vm -version
java -XX:+PrintFlagsFinal -version
java -Xlog:help
~~~

Các lệnh phù hợp với HotSpot/JDK có hỗ trợ tính năng tương ứng; output có thể rất dài hoặc khác giữa vendors. Không đưa nguyên VM flags/command line có chứa secrets lên logs công khai.

### 19.2. Không che flags không hợp lệ

Một số JVM có cách bỏ qua unrecognized VM options. Dùng cơ chế này bừa bãi có thể làm service startup xanh nhưng âm thầm bỏ qua settings quan trọng về memory, GC hoặc security.

Trong migration, nên phân loại từng flag: giữ, thay bằng cơ chế mới, hoặc loại bỏ có giải thích. Chỉ dùng workaround có phạm vi, thời hạn và owner.

### 19.3. Module flags và reflective access

Một số thư viện legacy có thể cần:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

trong giai đoạn chuyển đổi. Đây là ví dụ cho phép mở package JDK có kiểm soát trong môi trường module system, không phải flag nên bật cho mọi ứng dụng.

Nếu dependency dùng reflection tới internal JDK APIs, nên ưu tiên bản cập nhật tương thích. Với workaround, ghi rõ package mở, dependency yêu cầu, test liên quan và kế hoạch loại bỏ.

**--add-opens không khôi phục class/module đã bị xóa khỏi JDK.**

## 20. Java agents và native agents

Java agent thường được nạp:

~~~sh
java -javaagent:/opt/agents/observability.jar -jar /opt/app/app.jar
~~~

Native JVMTI agent có thể dùng:

~~~sh
java -agentpath:/opt/agents/libobserver.so -jar /opt/app/app.jar
~~~

Cần kiểm tra:

- Agent version hỗ trợ JDK/class-file version mục tiêu.
- Native agent đúng OS/CPU/ABI của container/VM.
- File paths và permissions.
- Có agent nào đã được image ENTRYPOINT thêm nhưng Kubernetes env lại thêm lần nữa?
- Agent startup hoặc dynamic attach có policy mới theo JDK không?
- Agent credentials được quản lý qua secret store, không lộ trong command line.

Không nên nạp cùng một agent hai lần từ command và JAVA_TOOL_OPTIONS/JDK_JAVA_OPTIONS. Nó có thể tạo duplicate instrumentation, lỗi startup hoặc overhead không kiểm soát.

## 21. Encoding, timezone và truststore

Một số system properties thường xuất hiện:

~~~text
-Dfile.encoding=UTF-8
-Duser.timezone=UTC
-Djavax.net.ssl.trustStore=/etc/myapp/truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Đây là ví dụ các settings có thể cần, không phải bộ flags mặc định cho mọi service.

### 21.1. Charset

Default charset có lịch sử thay đổi theo JDK/OS/locale. Với dữ liệu giao tiếp và file format quan trọng, nên sử dụng Charset rõ ràng như StandardCharsets.UTF_8 tại các API thay vì chỉ hy vọng -Dfile.encoding giải quyết mọi vấn đề.

Việc override file.encoding có thể có giới hạn khác nhau theo JDK release. Cần kiểm tra runtime mục tiêu và regression tests về serialization/file I/O.

### 21.2. Timezone

-Duser.timezone có thể ảnh hưởng default JVM timezone; nó không thay thế timezone của database, remote service, Java library dùng ZoneId explicit hoặc OS clock policy.

Nên dùng Instant/ZoneId thích hợp, kiểm thử ngày giờ ở các timezones và DST boundaries nếu nghiệp vụ có liên quan.

### 21.3. Truststore

Khi chuyển từ VM sang container, đường dẫn truststore trước đây có thể không tồn tại. Cần mount file/certificates đúng path, quyền đọc, định dạng và CA chain.

Không tắt certificate/hostname verification chỉ vì TLS handshake lỗi sau migration. Thay vào đó, điều tra truststore, certificate chain, SAN và Java security policy.

Đặc biệt tránh truyền truststore password/private key trên command line hoặc in ra JVM diagnostic logs.

## 22. Bảo mật của startup configuration

Tham số khởi động có thể bị quan sát qua process list, systemd unit, Pod spec, image metadata, JVM management tools, logs hoặc crash dumps tùy quyền truy cập.

Các nguyên tắc:

- Không đưa passwords/API tokens/private keys trực tiếp vào -D hoặc --password arguments.
- Không in toàn bộ command/environment nếu chưa redaction.
- Giới hạn người có quyền sửa systemd unit, Kubernetes Deployment và ConfigMap.
- Dùng Secret/credential file và secret manager khi phù hợp.
- Đảm bảo runtime user chỉ có quyền đọc những secrets cần thiết.
- Không đặt thư mục log/agent/truststore trong location writable bởi đối tượng không tin cậy.
- Quản lý checksums và nguồn gốc Java agent/native library.
- Đặt quyền bảo vệ heap dumps/core dumps vì chúng có thể chứa thông tin nhạy cảm.

Nếu dùng Java Security properties hoặc custom crypto providers, phải quản lý bằng policy được review; không nới thuật toán TLS bị hạn chế để vượt lỗi khởi động mà không có phê duyệt bảo mật.

### 22.1. Configuration drift cũng là rủi ro bảo mật

Hai replicas có cùng image nhưng nhận flags khác nhau có thể áp dụng security providers/truststore/agent khác nhau. Điều này tạo hành vi không nhất quán, thậm chí một replica chấp nhận certificate hoặc API mà replica khác từ chối.

Nên version hóa startup profile, dùng GitOps hoặc cơ chế quản lý configuration phù hợp và xác minh rollout đến toàn bộ instances.

## 23. Xác nhận effective flags từ JVM thật

Sau khi triển khai, cần trả lời:

1. Java executable và runtime version nào đang chạy?
2. JVM nhận flags/heap/GC/module options nào?
3. Application nhận arguments và profile gì?
4. Environment/ConfigMap/Secret references đã được áp dụng chưa?
5. Agent/truststore/classpath/module path có được nạp đúng?
6. Process nhận signals và hoạt động theo resource limits không?

### 23.1. Thông tin an toàn từ Java API

~~~java
public final class RuntimeSnapshot {
    public static void main(String[] args) {
        Runtime runtime = Runtime.getRuntime();

        System.out.println("java.version=" +
                System.getProperty("java.version"));
        System.out.println("java.vendor=" +
                System.getProperty("java.vendor"));
        System.out.println("os.name=" +
                System.getProperty("os.name"));
        System.out.println("os.arch=" +
                System.getProperty("os.arch"));
        System.out.println("availableProcessors=" +
                runtime.availableProcessors());
        System.out.println("maxHeapBytes=" +
                runtime.maxMemory());
    }
}
~~~

Chương trình này không in toàn bộ arguments/system properties, vì production startup có thể chứa thông tin nhạy cảm. Runtime.maxMemory thể hiện giới hạn heap JVM, **không phải total container memory limit**.

### 23.2. jcmd

Với JDK/JVM cho phép attach và có jcmd:

~~~sh
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.info
~~~

Các lệnh hỗ trợ chẩn đoán, nhưng có thể không tồn tại trong minimal runtime image hoặc bị hạn chế bởi quyền/namespace. VM.command_line có thể làm lộ startup arguments, cần chạy trong môi trường được phép và xử lý output an toàn.

### 23.3. systemd diagnostics

~~~sh
systemctl status javaapp.service
systemctl cat javaapp.service
journalctl -u javaapp.service -n 100 --no-pager
~~~

Output giúp xem unit, drop-in và startup failures. Nhưng systemd config có thể đã thay đổi mà JVM process cũ chưa restart; xác minh từ process đang chạy vẫn cần thiết.

### 23.4. Kubernetes diagnostics

~~~sh
kubectl describe pod <pod-name> -n <namespace>
kubectl get pod <pod-name> -n <namespace> -o yaml
kubectl logs <pod-name> -n <namespace>
~~~

Kiểm tra image digest, command/args, environment references, probes, restarts và Pod events. Không in nguyên Secret values hoặc tất cả system properties để debug.

### 23.5. Java version của host không đủ

java -version ngoài host không chứng minh process trong container hoặc systemd sử dụng cùng Java executable. Chỉ thông tin từ đúng process/image và hiệu quả của task runtime mới đủ để kết luận.

## 24. Kiểm thử trước và sau migration

Tổ chức kiểm thử theo ba lớp triển khai:

| Lớp | Kiểm thử cần có |
|---|---|
| Script | Shebang, executable path, quoting, forwarding "$@", JVM flags trước -jar, exec, signal forwarding, exit status. |
| systemd | Unit parsing, EnvironmentFile, drop-in replacement, service user, cgroup limits, journald, stop/restart. |
| Docker/Kubernetes | ENTRYPOINT/CMD, command/args, env/ConfigMap/Secret, memory/CPU, probes, PID1, graceful shutdown. |

### 24.1. Test positive path

1. Khởi động artifact trên JDK mục tiêu.
2. Xác minh runtime Java vendor/version.
3. Xác minh effective heap, processors, modules và agents.
4. Gọi health endpoint/CLI functionality.
5. Kiểm tra kết nối database, TLS, messaging theo ứng dụng.
6. Gửi SIGTERM ở môi trường test và xác nhận graceful shutdown.
7. Kiểm tra logs/diagnostics được thu thập an toàn.

### 24.2. Negative tests

| Kịch bản | Mong đợi |
|---|---|
| JVM flag đã bị loại khỏi JDK | Startup/CI phát hiện rõ, không âm thầm bỏ qua. |
| Java executable path sai | Có thông báo lỗi rõ, không tự dùng JDK khác trái policy. |
| Argfile không tồn tại | Startup fail có thể chẩn đoán. |
| Agent JAR hoặc native agent sai platform | Smoke test phát hiện trước rollout. |
| Secret bắt buộc không tồn tại | Fail closed, không in giá trị nhạy cảm. |
| Truststore thiếu CA/không đọc được | TLS test thất bại an toàn, không disable verification. |
| Kubernetes port/probe sai | Staging phát hiện Pod không ready. |
| Container bị SIGTERM | Dừng theo policy và termination grace. |
| Memory/CPU limit quá chặt | Capacity test phát hiện throttling/OOM risk. |

Các negative tests phải thực hiện trong môi trường thử nghiệm có thể khôi phục, không cố tình phá dịch vụ production.

## 25. Bảng đối chiếu startup giữa môi trường cũ và mới

| Thành phần | Baseline | JDK/deployment mục tiêu | Bằng chứng |
|---|---|---|---|
| Java executable/version | JDK đang chạy thực | JDK/vendor/update mục tiêu | Process metadata, java -version trong đúng runtime. |
| JVM flags | GC/heap/module/agent hiện hành | Flags còn hỗ trợ | VM.flags, startup test. |
| Main selector | -jar/-cp/-m | Packaging mục tiêu | Runtime start. |
| Application arguments | Profile/port/config | Contract không đổi hoặc versioned | Integration tests. |
| System properties | -D settings | Setting được kiểm soát | App diagnostics đã redaction. |
| Environment | Script/systemd/Kubernetes env | Nguồn và precedence mới | Deployment inspection. |
| Heap/CPU limits | Host/cgroup baseline | Runtime constraints mới | JVM metrics, cgroups. |
| Security | User, truststore, secrets | Policy và mounts phù hợp | Security integration tests. |
| Logging | GC/application paths | Stdout/journald/collector | Log collection checks. |
| Agents | Java/native agents | Bản hỗ trợ JDK/OS | Agent load smoke tests. |
| Lifecycle | Stop/restart behavior | Graceful shutdown + probes | SIGTERM/staging test. |

Không đồng nhất “JVM start được” với “ứng dụng sẵn sàng sản xuất”. Cần test request/transaction/connections và lifecycle trên môi trường thực tế.

## 26. Điều tra lỗi thường gặp

### 26.1. Flag bị đặt sau -jar

Triệu chứng: Pod có Xmx nhỏ hơn dự kiến dù YAML chứa -Xmx1g.

Kiểm tra command/args và java process: nếu -Xmx1g nằm sau /app/app.jar, đó là application argument. Chuyển nó trước -jar hoặc dùng JVM option source đúng.

### 26.2. JAVA_OPTS không hoạt động

Triệu chứng: ConfigMap có JAVA_OPTS, nhưng heap không đổi.

Nguyên nhân thường là image ENTRYPOINT không đọc JAVA_OPTS. Xem startup script/image contract và effective VM flags; chuyển sang một cơ chế được hỗ trợ như direct launcher options hoặc JDK_JAVA_OPTIONS khi phù hợp.

### 26.3. systemd service không đọc shell syntax

Triệu chứng: ExecStart chứa pipe/redirection hoặc biến theo syntax shell và service không khởi động/arguments sai.

Sửa về systemd ExecStart semantics, dùng một script chuyên trách nếu thực sự cần shell và kết thúc script bằng exec Java.

### 26.4. Kubernetes command ghi đè ENTRYPOINT

Triệu chứng: sau migration mất Java agent hoặc thiếu certificate setup dù image không đổi.

Xem Dockerfile và Pod command: nếu Pod override toàn bộ ENTRYPOINT, logic trong image script không chạy. Khôi phục contract hoặc đưa các bước cần thiết vào startup mới có kiểm thử.

### 26.5. JVM cũ/mới nhận diện heap khác nhau

Triệu chứng: cùng memory limit, Runtime.maxMemory khác.

So sánh JDK vendor/update, cgroups v1/v2, Xmx/MaxRAMPercentage, UseContainerSupport và giới hạn cgroup ancestor. Đây có thể là thay đổi ergonomic chứ không phải heap leak.

### 26.6. JVM bị OOMKilled dù heap chưa đầy

Điều tra non-heap/native memory, direct buffers, thread stacks, page cache, container memory events và image limits. Java OutOfMemoryError khác kernel/container OOM kill; exit code 137 riêng lẻ chưa chứng minh nguyên nhân.

### 26.7. Rollout báo Running nhưng không Ready

Kiểm tra startup/readiness probes, port, bind address, truststore, dependency initialization và startup duration. Một process còn sống không chứng minh đã đủ điều kiện nhận traffic.

### 26.8. SIGTERM không tới JVM

Kiểm tra PID1 và startup script. Nếu shell không exec/forward signals đúng, Kubernetes có thể phải SIGKILL sau grace period; sửa process lifecycle thay vì chỉ tăng timeout.

## 27. Quy trình thay đổi startup khi nâng JDK

**Bước 1 — Kiểm kê:** xác định ai khởi động Java (script, systemd, Docker ENTRYPOINT, Kubernetes command, application server), JDK nào và những options nào đã có.

**Bước 2 — Chốt runtime contract:** ghi minimum/runtime JDK, application profile, heap/CPU policy, module access, agent, logging, security và lifecycle.

**Bước 3 — Phân loại flags:** flag còn hỗ trợ, đã loại bỏ, cần thay thế, legacy workaround và flags chỉ dùng debug.

**Bước 4 — Chọn một nguồn cấu hình:** quyết định settings nào ở script/image, systemd unit/drop-in, argfile, env hoặc application configuration; không xung đột ngầm.

**Bước 5 — Chuẩn hóa cú pháp:** VM options trước main selector, quote paths, forward arguments, systemd parse rules, Docker ENTRYPOINT/CMD, Kubernetes command/args.

**Bước 6 — Bảo mật:** không để secrets trong command lines, bảo vệ truststore/log/heap dump, quản lý agent provenance và quyền filesystem.

**Bước 7 — Khởi động trên JDK mục tiêu:** dùng đúng artifact/container/unit, xác minh Java runtime và effective JVM flags.

**Bước 8 — Test chức năng và lifecycle:** chạy integrations, probes, GC/resource metrics, SIGTERM, shutdown hooks và restart/rollout.

**Bước 9 — Lưu bằng chứng:** artifact/image digest, unit/manifest revision, Java version, flags, resource limits, test results và chưa kiểm tra gì.

**Bước 10 — Rollout và rollback:** canary/staging trước, theo dõi crash loops, OOMKilled, readiness, latency/GC và lỗi TLS; chuẩn bị rollback cả artifact, startup config và secret references.

## 28. Mẫu báo cáo cấu hình khởi động

~~~text
Service/module:
Artifact version + checksum:
JDK vendor/version/update:
Runtime: script / systemd / Docker / Kubernetes
OS/architecture + image digest:

Launcher:
  Java executable:
  Main selector: -jar / -cp + main / -m
  JVM options source:
  Application arguments source:
  Environment/config references:
  Agent paths + versions:

Effective JVM:
  Heap initial/max:
  GC collector/logging:
  Active processors:
  Module flags:
  Encoding/timezone:
  Certificate/truststore policy:

Deployment and lifecycle:
  Service user:
  CPU/memory requests/limits:
  PID1/signal forwarding:
  Graceful shutdown duration:
  Startup/readiness/liveness probes:
  Log/dump permissions:

Security:
  Secrets absent from plain-text command arguments:
  Credentials/protected files:
  Agent/native artifact provenance:

Validation:
  Startup:
  Runtime flags:
  Application integration:
  SIGTERM/shutdown:
  Resource/GC:
  Deployment rollout:
  Known gaps and blockers:
~~~

Bảng trên là khung thu thập dữ liệu khi kiểm chứng một migration, không phải kết quả test đã thực hiện. Chỉ lưu metadata đủ dùng để tái tạo và chẩn đoán, tránh đính kèm secrets vào tài liệu.

## 29. Kết luận

**Tham số khởi động là một thành phần trực tiếp của tính tương thích Java.** Cùng một JAR có thể vận hành khác nhau khi JVM flags bị đặt sai vị trí, JAVA_OPTS không được script xử lý, systemd phân tích command khác với Bash, container mất ENTRYPOINT logic hoặc Kubernetes thay đổi command/args và resource limits. JDK mới cũng có thể đổi hỗ trợ VM flags, container-awareness, GC ergonomics và module access.

Một phương pháp bền vững cần tách rõ **JVM options, application arguments, environment settings, secrets và deployment lifecycle/resource configuration**. Startup script phải quản lý quoting và exec; systemd cần unit/drop-in rõ ràng; Kubernetes phải tương thích với image entrypoint, probes và graceful shutdown. Mọi thay đổi phải được xác minh từ JVM **thực sự đang chạy**, cùng integration tests, resource metrics và kế hoạch rollback.

Đích đến của Java Advance Compatibility Migration không chỉ là lệnh java khởi động thành công, mà là **một runtime configuration có thể tái lập, kiểm soát phiên bản và kiểm chứng trên các môi trường triển khai**, giúp duy trì hành vi nghiệp vụ, độ ổn định và bảo mật sau khi nâng JDK.
