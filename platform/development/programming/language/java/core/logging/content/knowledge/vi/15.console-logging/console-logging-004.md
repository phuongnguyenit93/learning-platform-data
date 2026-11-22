# Console trong container — Logging Java qua stdout/stderr với Docker và Kubernetes

## 1. Console logging trong container là gì?

**Console logging trong container** là cách ứng dụng ghi sự kiện log vào **standard output (stdout)** hoặc **standard error (stderr)** của tiến trình chạy trong container, để **container runtime và hạ tầng quan sát** có thể thu thập, hiển thị, chuyển tiếp và lưu trữ chúng.

Thay vì bắt buộc ứng dụng tự tạo file như /var/log/orders/application.log bên trong filesystem của container, ứng dụng có thể ghi:

~~~text
INFO | event=service.started service=orders port=8080
WARN | event=dependency.slow dependency=catalog durationMs=750
ERROR | event=request.failed requestId=req-42 errorCode=UPSTREAM_TIMEOUT
~~~

Ba dòng trên là **format minh họa**, không phải định dạng mặc định của mọi thư viện Java. Khi dùng Logback, cấu hình **ConsoleAppender** và encoder quyết định nội dung, level nào được in và stream đích.

**Nguyên tắc quan trọng:** Ghi log ra stdout/stderr là việc của **ứng dụng**; đọc các stream và cung cấp lệnh như docker logs hoặc kubectl logs là việc của **container runtime/hệ thống điều phối**; lưu trữ tập trung, tìm kiếm dài hạn, phân quyền và retention lại là trách nhiệm của **logging platform** khi được triển khai.

Việc ứng dụng gọi LOG.info(...) không bảo đảm dòng log đã được thu thập và lưu bền vững. Nó có thể bị lọc tại logger/appender, không được flush, bị mất khi container dừng hoặc nằm ngoài chính sách lưu trữ của runtime.

### Mục tiêu học tập

Sau bài này, bạn có thể giải thích:

1. stdout và stderr nằm ở đâu trong chuỗi ứng dụng → runtime → collector.
2. Docker, Kubernetes nhìn log console khác gì log file nằm trong container.
3. Cấu hình Logback ConsoleAppender để ghi log Java vào đúng stream.
4. Tại sao không nên tự ý dùng System.out.println thay cho logging framework.
5. Cách xem log bằng docker logs và kubectl logs, cũng như giới hạn của các lệnh đó.
6. Cách kiểm soát level, format, JSON Lines, exception, MDC, lượng dữ liệu và bảo mật.
7. Các lỗi thường gặp khi log biến mất, bị lặp, sai stream hoặc bị cắt.

## 2. Đường đi của một bản ghi log trong container

Một pipeline đơn giản:

~~~text
Java application
  |
  |  LOG.info(...), LOG.warn(...), LOG.error(...)
  v
SLF4J API / Logger (Logback hoặc backend khác)
  |
  |  effective level + filter
  v
ConsoleAppender + Encoder
  |
  +-------------------------+
  |                         |
  v                         v
stdout (FD 1)           stderr (FD 2)
  |                         |
  +-------------+-----------+
                |
                v
        Container runtime
                |
                v
      Node-level logging files
        / logging driver
                |
          +-----+------+
          |            |
          v            v
    docker logs    kubelet/kubectl logs
          |
          v
    Optional log collector/agent
          |
          v
  Central log storage / search / alerts
~~~

Sơ đồ mang tính **khái niệm**: Docker thu thập theo **logging driver**, còn Kubernetes làm việc với container runtime qua giao diện phù hợp và kubelet quản lý quyền truy cập log. Không phải mọi môi trường đều có đầy đủ những thành phần trong hình hay cùng một cách lưu file.

Đường đi có thể gồm nhiều lớp lọc:

- **Application logger:** LOG.debug(...) có thể bị loại khi root level là INFO.
- **Appender/Handler:** nhận event nhưng có thể tiếp tục từ chối theo filter hoặc ghi ra stream khác.
- **Runtime:** có cơ chế driver, định dạng, rotation và lưu trữ cục bộ riêng.
- **Collector:** có thể parse, thêm metadata, lấy mẫu, giới hạn kích thước hoặc chuyển tiếp thất bại.
- **Log store:** có retention, quyền truy cập, chỉ mục và chi phí khác nhau.

Vì thế, **không thấy log trong dashboard không đủ để kết luận nhánh Java không chạy**.

## 3. stdout, stderr và ý nghĩa của hai stream

Hai luồng chuẩn là những kênh I/O của tiến trình:

| Luồng | File descriptor trên Unix | Cách sử dụng thông thường |
| --- | --- | --- |
| stdin | 0 | Nhận đầu vào |
| stdout | 1 | Kết quả chính hoặc log ứng dụng, theo chính sách |
| stderr | 2 | Thông tin chẩn đoán, cảnh báo/lỗi, theo chính sách |

**Không có quy tắc của JVM rằng mọi ERROR phải in stderr và mọi INFO phải in stdout.** Logging framework lựa chọn target dựa vào cấu hình. Ví dụ:

- **Logback ConsoleAppender** thường mặc định ghi **System.out**; có thể đặt target System.err.
- **java.util.logging.ConsoleHandler** (JUL) mặc định ghi **System.err**.
- **System.out.println(...)** và **System.err.println(...)** trực tiếp in vào stream tương ứng, không có logic level của logger.
- **Log4j 2 ConsoleAppender** có cấu hình và API riêng, không dùng nguyên cấu hình Logback để điều khiển nó.

Trong nhiều hệ thống container, cả stdout và stderr được thu thập, nhưng **stream không phải log level**. Một dòng ERROR có thể nằm ở stdout nếu appender được cấu hình như thế. Bộ phân loại cấp độ ở collector nên dựa vào trường **level** đáng tin cậy, không suy luận máy móc rằng stream=stderr nghĩa là lỗi nghiêm trọng.

### Khi nào nên dùng stdout, khi nào stderr?

Với **dịch vụ web/container chạy dài**, sử dụng một stream nhất quán (thường stdout) cùng trường level thường đơn giản cho việc thu thập. Với **công cụ CLI** cần trả JSON hoặc CSV trên stdout cho chương trình khác, nên cân nhắc gửi log chẩn đoán ra stderr để không phá kết quả máy đọc.

Nếu dùng hai stream song song, collector có thể nhận chúng theo thứ tự khác so với thứ tự Java phát sự kiện. **Không coi thứ tự dòng khi gộp stdout/stderr là một thứ tự toàn cục tuyệt đối**; dùng timestamp, requestId và traceId để phân tích.

## 4. Docker xử lý log console thế nào?

Khi container chạy, Docker có thể thu dữ liệu stdout/stderr thông qua **logging driver** đã được cấu hình. Một số driver sử dụng cơ chế lưu cục bộ; một số driver chuyển log đến hệ thống khác. Driver mặc định và tùy chọn cụ thể **phụ thuộc cấu hình Docker daemon và cách chạy container**, không nên khẳng định mọi máy đều dùng một driver giống nhau.

**docker logs** là lệnh thường dùng để xem log mà Docker runtime cho phép truy xuất cho một container. Nó **không phải** lệnh đọc mọi file ở bên trong container và **không thay thế** nền tảng log tập trung lâu dài.

Một số lệnh thực hành:

~~~bash
docker run --name order-console-demo java-console-demo:1
docker logs order-console-demo
docker logs --timestamps order-console-demo
docker logs --tail 20 order-console-demo
docker rm order-console-demo
~~~

Đây là ví dụ giả định image **java-console-demo:1** đã được build ở mục 7 và container chưa có tên trùng. Trong ví dụ, ứng dụng Java chạy xong nhanh; lệnh docker run hiển thị log khi chạy, sau đó docker logs có thể xem lại các dòng đã được driver lưu. Đừng chạy với **--rm** nếu muốn tiếp tục xem lại container đã kết thúc bằng docker logs, vì Docker sẽ xóa đối tượng container sau khi chạy.

Với container chạy dài, có thể xem log theo thời gian thực:

~~~bash
docker logs --follow --tail 100 order-console-demo
~~~

Nếu container đã kết thúc, lệnh follow không làm ứng dụng chạy lại; nó chỉ đọc các log còn được truy xuất. Khả năng đọc lại log phụ thuộc driver, cấu hình và vòng đời container.

### Logging driver và rotation

Docker cho phép lựa chọn driver/tùy chọn ghi log. Ví dụ một cấu hình khi tạo container dùng driver json-file và đặt giới hạn theo file:

~~~bash
docker run --name order-console-rotated \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  java-console-demo:1
~~~

Trong ví dụ này, **10m** và **3** là giá trị cấu hình minh họa, **không phải mặc định bắt buộc**. Tùy driver, các tùy chọn rotation khác nhau; không sao chép max-size/max-file sang mọi driver mà không kiểm tra tài liệu driver tương ứng.

**Không chỉnh sửa trực tiếp file log nội bộ của Docker daemon** để xóa dung lượng khi container đang chạy; cần sử dụng cơ chế quản lý/rotation của runtime và logging platform.

Để quan sát logging driver đã chọn trong daemon/container, có thể dùng lệnh xem cấu hình phù hợp, chẳng hạn:

~~~bash
docker info --format '{{.LoggingDriver}}'
docker inspect --format '{{.HostConfig.LogConfig.Type}}' order-console-demo
~~~

Lệnh inspect yêu cầu container order-console-demo còn tồn tại. Driver mặc định của daemon không nhất thiết trùng với driver đã được cấu hình riêng cho một container.

### Dùng console thay vì tự ghi file trong image

Một file dưới filesystem bên trong container có thể **không xuất hiện trong docker logs**, nếu ứng dụng chỉ ghi file đó và không có thành phần nào chuyển file ra stdout/stderr. File có thể biến mất khi container bị xóa nếu không được đưa ra persistent volume hoặc một hệ lưu trữ ngoài.

Với hệ thống triển khai container thông thường, cách dễ vận hành là **ứng dụng ghi console**, để runtime/collector quản lý việc nhận và lưu log. Không phải mọi ứng dụng đều bị cấm ghi file; một số yêu cầu audit hoặc phần mềm cũ vẫn cần file, volume hoặc sidecar thu thập, nhưng phải thiết kế rõ ràng.

## 5. Kubernetes đọc log container như thế nào?

Trong Kubernetes, kubelet và container runtime tham gia quản lý log của container ở node. Lệnh **kubectl logs** yêu cầu Kubernetes cung cấp nội dung log của container thuộc một Pod.

Ví dụ giả định có Pod **order-console-demo** trong namespace **demo**, với container tên **app**:

~~~bash
kubectl logs -n demo pod/order-console-demo -c app
kubectl logs -n demo pod/order-console-demo -c app --timestamps
kubectl logs -n demo pod/order-console-demo -c app --since=10m
kubectl logs -n demo pod/order-console-demo -c app --follow
~~~

Đây là **lệnh minh họa với tên tài nguyên cụ thể**; Pod, namespace và container phải tồn tại thật thì lệnh mới chạy. Tên **app** hữu ích khi Pod có nhiều container. Nếu chạy Pod chỉ có một container, thường có thể bỏ cờ -c.

Các tình huống cần phân biệt:

- **Pod nhiều container:** log của từng container được truy cập riêng, cần chọn đúng tên container.
- **Container đã restart:** có thể sử dụng tùy chọn **--previous** để xem log của phiên bản container trước **nếu log còn khả dụng** trong ngữ cảnh Pod đó.
- **Pod bị xóa hoặc node log đã xoay/hết retention:** kubectl logs không phải nơi bảo đảm truy xuất mọi log lịch sử.
- **Streaming --follow:** chỉ theo dõi stream có thể truy cập, không bảo đảm dữ liệu đã được ghi bền vững ở log store.

Ví dụ xem bản chạy trước của một container trong Pod:

~~~bash
kubectl logs -n demo pod/order-console-demo -c app --previous
~~~

Nếu không có previous terminated container hoặc log đã không còn, lệnh sẽ báo không tìm được nội dung phù hợp. Không dùng sự tồn tại của kubectl logs để giả định rằng cluster đã có logging tập trung.

### Node-level và cluster-level logging

Kubelet có thể quản lý rotation file log container trên node theo các thiết lập tương ứng. **kubectl logs là công cụ truy xuất log theo container/Pod**, không phải một giải pháp tìm kiếm toàn cluster với retention dài hạn.

Hệ thống cần truy vấn lâu dài hoặc nhiều node thường có thêm **log agent/collector**, chuyển sự kiện từ node/runtime đến một dịch vụ lưu trữ và tìm kiếm. Việc vận hành collector, chính sách lưu, phân quyền, parse JSON và alerting là phần khác với việc ứng dụng gọi Logger.

**Lưu ý thực tế:** log đã được runtime ghi xuống node nhưng chưa được collector đọc, log bị cắt vì kích thước, hoặc collector bị lỗi đều có thể khiến truy vấn trung tâm thiếu dữ liệu.

## 6. Java logging trong container: chọn API đúng

Một ứng dụng Java có thể dùng:

| Lựa chọn | Cơ chế | Ghi vào console |
| --- | --- | --- |
| **SLF4J + Logback** | Mã gọi SLF4J, backend Logback xử lý | ConsoleAppender target System.out/System.err |
| **JUL** | API tích hợp JDK | ConsoleHandler mặc định stderr; handler tùy biến có thể ghi stdout |
| **Log4j 2** | API/backend của Log4j 2 | ConsoleAppender của Log4j 2, cấu hình theo chính Log4j 2 |
| **System.out.println** | Ghi trực tiếp String | stdout, không có level/filter/schema logging tự động |

Với dự án mới hoặc dự án đã chuẩn hóa SLF4J, **sử dụng logger và ConsoleAppender** thường dễ bảo trì hơn việc in println khắp code. Lợi ích gồm:

- Level theo package/module và theo môi trường.
- Pattern hoặc structured encoder thống nhất.
- Throwable/stack trace qua backend.
- MDC và tương quan request/trace ID khi được cấu hình đúng.
- Thay đích và mức ghi mà không phải sửa mọi lời gọi log.
- Filter để giảm chi phí và tránh xuất thông tin nhạy cảm không cần thiết.

Trong container, cách dễ nhớ là: **mã nghiệp vụ gọi Logger, cấu hình backend hướng log tới console, hạ tầng nhận stream**.


## 7. Ví dụ Java 17 + Maven + Docker: log ra stdout

Ví dụ này tạo một chương trình Java **chạy được trên máy có Maven/JDK 17**, sau đó đóng gói thành Docker image. Ứng dụng dùng **org.slf4j.Logger** với **Logback Classic**, root ở INFO và một ConsoleAppender ghi System.out.

Để output xác định, formatter demo cố ý **không in timestamp**; ở production phải thêm timestamp chuẩn hoặc dựa trên metadata runtime/collector được tổ chức quy định.

### 7.1. Cấu trúc dự án

~~~text
java-console-demo/
├── pom.xml
├── Dockerfile
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── ContainerConsoleDemo.java
        └── resources/
            └── logback.xml
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>java-console-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.7.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các phiên bản cố định trong ví dụ chỉ phục vụ tái lập bài học, **không phải lời khẳng định đó là phiên bản mới nhất hoặc an toàn nhất hiện tại**. Dự án thật nên tuân theo dependency management, kiểm tra tương thích/bản vá bảo mật và tránh đưa nhiều SLF4J provider vào runtime.

### 7.3. src/main/resources/logback.xml

~~~xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Logback sẽ lấy **logback.xml trên classpath** nếu không bị framework/cấu hình khác ghi đè:

- **Root INFO:** không xuất DEBUG; INFO, WARN, ERROR được xét để ghi.
- **ConsoleAppender:** ghi vào **System.out**.
- **Pattern:** chỉ in mức log và message, không chèn thời gian/thông tin thay đổi để demo có stdout cố định.
- **UTF-8:** phù hợp với Unicode khi nơi nhận giải mã tương ứng.
- **Appender chỉ gắn tại root:** tránh nhân đôi các event trong ví dụ.

**%level | %msg%n** là cú pháp pattern Logback; dấu **{}** trong lời gọi Java là placeholder của SLF4J, không phải cùng một cơ chế định dạng.

### 7.4. src/main/java/demo/ContainerConsoleDemo.java

~~~java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ContainerConsoleDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(ContainerConsoleDemo.class);

    public static void main(String[] args) {
        LOG.debug("event=service.debug enabled=false");

        LOG.info("event=service.started service={} port={}",
                "orders", 8080);

        LOG.warn("event=dependency.slow dependency={} durationMs={}",
                "catalog", 750);

        LOG.error("event=request.failed requestId={} errorCode={}",
                "req-42", "UPSTREAM_TIMEOUT");
    }
}
~~~

Đây là **lớp Java hoàn chỉnh**. Dữ liệu cố định làm output có thể kiểm chứng. Nó không mở HTTP server hoặc chạy dài; tiến trình kết thúc sau khi ghi log, để phần thử Docker đơn giản.

### 7.5. Biên dịch và chạy trực tiếp trên máy

Cần **JDK 17+**, Maven và dependency tải được (hoặc đã có sẵn trong Maven cache). Tại thư mục **java-console-demo**, chạy:

~~~bash
mvn -q -DskipTests package dependency:copy-dependencies
java -cp "target/classes:target/dependency/*" demo.ContainerConsoleDemo
~~~

Dòng java ở trên dùng ký tự **:** cho classpath theo Linux/macOS. Trong **Windows PowerShell**, dùng dấu **;**:

~~~powershell
java -cp "target/classes;target/dependency/*" demo.ContainerConsoleDemo
~~~

**Stdout do chương trình Java phát ra** khi dùng đúng logback.xml ở trên:

~~~text
INFO | event=service.started service=orders port=8080
WARN | event=dependency.slow dependency=catalog durationMs=750
ERROR | event=request.failed requestId=req-42 errorCode=UPSTREAM_TIMEOUT
~~~

**Stderr của ứng dụng không có dòng log dự kiến.** Lời gọi DEBUG bị root INFO loại; chương trình không in thêm nội dung bằng println. Thông báo build, cấu hình hoặc lỗi runtime nếu có nằm ngoài ba dòng log nghiệp vụ đã dự kiến.

### 7.6. Dockerfile đa giai đoạn

Tạo **Dockerfile**:

~~~dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src
COPY pom.xml .
COPY src ./src
RUN mvn -q -DskipTests package dependency:copy-dependencies

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /src/target/classes /app/classes
COPY --from=build /src/target/dependency /app/lib
ENTRYPOINT ["java", "-cp", "/app/classes:/app/lib/*", "demo.ContainerConsoleDemo"]
~~~

Giải thích:

1. Stage **build** dùng Maven + JDK 17 để biên dịch và copy dependency runtime vào target/dependency.
2. Stage runtime dùng **Java 17 JRE**, không cần mang Maven vào image chạy.
3. **target/classes** chứa class đã biên dịch và tài nguyên **logback.xml**.
4. **target/dependency** chứa JAR thư viện cần cho SLF4J/Logback; classpath **/app/lib/* ** được Java xử lý trên Linux container.
5. **ENTRYPOINT dạng exec-array** chạy java trực tiếp như tiến trình chính thay vì bọc trong một shell script không chuyển tiếp signal.
6. Stdout/stderr của tiến trình Java đi vào stream do container runtime quản lý.

Các tên image/tag ở đây là ví dụ thực hành. Khi triển khai thật, nên pin base-image digest hoặc áp dụng chính sách image đã kiểm chứng, cập nhật CVE và dùng user không đặc quyền khi phù hợp.

### 7.7. Build image và xem log

Từ thư mục chứa Dockerfile:

~~~bash
docker build -t java-console-demo:1 .
docker run --name order-console-demo java-console-demo:1
docker logs order-console-demo
docker logs --timestamps order-console-demo
docker rm order-console-demo
~~~

**Nội dung log ứng dụng trong docker run/docker logs** là ba dòng INFO, WARN, ERROR đã nêu ở mục 7.5. Nếu dùng **--timestamps**, Docker có thể thêm timestamp do runtime khi hiển thị; vì vậy output đầy đủ của lệnh docker logs --timestamps **không giống nguyên văn ba dòng demo**, nhưng phần message từ Java giữ nguyên.

Lưu ý ứng dụng kết thúc ngay. Không dùng **docker run --rm** trong cùng chuỗi lệnh này nếu muốn kiểm tra docker logs sau đó; tùy chọn --rm xóa container khi đã kết thúc.

### 7.8. Thử tắt INFO mà không sửa code

Thay trong logback.xml:

~~~xml
<root level="WARN">
    <appender-ref ref="STDOUT"/>
</root>
~~~

Build lại image rồi chạy với tên container mới hoặc xóa container cũ trước khi dùng lại tên. Lúc này stdout log của Java chỉ còn:

~~~text
WARN | event=dependency.slow dependency=catalog durationMs=750
ERROR | event=request.failed requestId=req-42 errorCode=UPSTREAM_TIMEOUT
~~~

Điều này cho thấy **level và appender được cấu hình ở backend**; Docker chỉ nhận các dòng mà ứng dụng thực sự ghi vào stream. Runtime không thể khôi phục một event DEBUG/INFO đã bị ứng dụng lọc trước khi xuất.

## 8. Phân luồng INFO/WARN ở stdout và ERROR ở stderr

Một số nền tảng muốn giữ lỗi ở stream khác với log thông thường. Với Logback, **mỗi ConsoleAppender chỉ có một target**, nên có thể tạo hai appender với filter phù hợp.

Ví dụ **logback.xml thay thế** (không dùng đồng thời với file ví dụ mục 7):

~~~xml
<configuration>
    <appender name="OUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <filter class="ch.qos.logback.classic.filter.LevelFilter">
            <level>ERROR</level>
            <onMatch>DENY</onMatch>
            <onMismatch>NEUTRAL</onMismatch>
        </filter>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ERR"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.err</target>
        <filter class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>ERROR</level>
        </filter>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%level | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="OUT"/>
        <appender-ref ref="ERR"/>
    </root>
</configuration>
~~~

Trong thang level Logback thông dụng:

- **OUT** ghi INFO và WARN, từ chối ERROR bằng LevelFilter.
- **ERR** chỉ ghi ERROR bằng ThresholdFilter.
- **Root INFO** không phát DEBUG từ logger kế thừa INFO.
- ERROR không bị ghi đồng thời ở cả hai stream như khi hai appender đều không có filter.

Điều này **không có nghĩa ERROR là “một loại dữ liệu đặc biệt của stderr”**. Đó chỉ là quyết định routing của backend.

Để xem tách luồng trên bash, có thể chạy sau khi Maven build:

~~~bash
java -cp "target/classes:target/dependency/*" \
  demo.ContainerConsoleDemo > out.log 2> err.log
~~~

Với cấu hình thay thế nêu trên, **out.log** chứa INFO và WARN; **err.log** chứa ERROR. Thứ tự hai stream khi được công cụ ngoài gộp lại có thể khác thứ tự phát.

Khi dùng Kubernetes hoặc Docker, nên xác định collector có quy tắc xử lý stdout/stderr ra sao trước khi quyết định tách stream; nhiều hạ tầng thích giữ mọi log trong một stream với trường level rõ ràng.

## 9. Structured logging và một log event trên một dòng

Trong container, các công cụ thu log thường xử lý dữ liệu theo **dòng**. Vì vậy, đối với hệ thống nhiều service, một định dạng **JSON Lines** (mỗi sự kiện là một object JSON trên một dòng vật lý) có thể tiện hơn text tùy ý.

Ví dụ JSON log:

~~~json
{"timestamp":"2026-11-09T10:15:00.125Z","level":"INFO","service":"orders","event":"order.created","requestId":"req-42","durationMs":18}
{"timestamp":"2026-11-09T10:15:02.100Z","level":"ERROR","service":"orders","event":"payment.failed","requestId":"req-42","errorCode":"UPSTREAM_TIMEOUT"}
~~~

Đây là **dữ liệu minh họa**, không phải output của ứng dụng ở mục 7. Nó có nhiều lợi ích:

- **Tên trường ổn định:** service, event, requestId, errorCode.
- **Kiểu dữ liệu rõ:** durationMs là số để có thể so sánh nếu collector parse đúng.
- **Timestamp có múi giờ:** ký hiệu Z biểu diễn UTC.
- **Dễ lọc theo requestId:** xem các event cùng request hoặc trace.
- **Giảm lỗi tách dòng:** serializer JSON phù hợp sẽ escape newline bên trong giá trị.

Tuy nhiên, **không phải cứ in chuỗi trông như JSON lên stdout thì collector sẽ tự parse và index các trường**. Cần một JSON encoder thực sự ở backend, schema rõ ràng và cấu hình log collector/ingestion tương ứng.

### Exception và stack trace nhiều dòng

Khi Java log Throwable, encoder text có thể in **nhiều dòng**:

~~~text
ERROR event=payment.failed errorCode=UPSTREAM_TIMEOUT
java.io.IOException: dependency unavailable
    at demo.PaymentClient.call(PaymentClient.java:42)
    at demo.OrderService.pay(OrderService.java:81)
~~~

Đây là **mẫu minh họa**, không phải stack trace của chương trình mục 7. Nếu collector chỉ dựa vào newline, nó có thể hiểu stack trace thành nhiều event và làm hỏng truy vấn.

Các giải pháp thường dùng:

1. **Collector multiline parser**: nhận diện dòng bắt đầu event và ghép các dòng exception theo rule.
2. **Structured exception fields**: xuất exception type/message/stack trace vào JSON, escape newline bên trong giá trị.
3. **Tổ chức schema rõ ràng**: một event có một mã lỗi và ngữ cảnh, hạn chế lặp cùng stack trace tại mọi tầng.

Không nên xóa Throwable chỉ để giữ log một dòng. Cần chọn cách biểu diễn mà cả Java backend và collector hỗ trợ.

### Escaping và log injection

Message từ request có thể chứa dấu nháy, backslash, newline hoặc ký tự điều khiển. Nếu nối trực tiếp vào text hoặc JSON tự chế, người dùng có thể vô tình hoặc cố ý tạo ra các dòng log giả.

Nên dùng serializer/encoder xử lý escaping đúng và **không log raw dữ liệu không tin cậy không cần thiết**. Với dữ liệu nhạy cảm, escaping không đủ: còn phải masking, giảm dữ liệu và phân quyền.

## 10. Timestamp: của Java hay của runtime?

Một dòng log có thể có nhiều mốc thời gian:

- **Event timestamp:** thời điểm mà Java/logging framework ghi nhận sự kiện.
- **Runtime timestamp:** thời điểm container runtime ghi/đánh dấu một record.
- **Ingestion timestamp:** thời điểm log collector/storage nhận dữ liệu.

Các thời điểm có thể chênh lệch vì buffering, network, queue hoặc clock skew. Khi dùng **docker logs --timestamps** hoặc **kubectl logs --timestamps**, các lệnh có thể hiển thị timestamp từ cơ chế log của runtime/cluster, **không phải timestamp được tự động chèn vào message bởi logger Java**.

Với quan sát production, nên thống nhất:

1. Mốc thời gian nào được gọi là **timestamp** trong schema log.
2. Có timezone rõ ràng (thường UTC) hay không.
3. Precision như millisecond hay microsecond.
4. Cách phân biệt event time và collector receive time.
5. Cách kiểm soát đồng hồ của các máy và độ lệch giữa nhiều node.

**Đừng loại timestamp khỏi log production chỉ vì ví dụ học tập bỏ nó để stdout xác định.** Bài demo có thể inject một clock cố định khi test hoặc parse trường thời gian riêng để đối chiếu schema.

## 11. Luồng đời tiến trình: PID 1, signal và flush

Container thường có một tiến trình chính; khi tiến trình đó kết thúc, container sẽ dừng. Điều này ảnh hưởng khả năng ghi log.

### ENTRYPOINT dạng exec-array

Dockerfile ở mục 7 dùng:

~~~dockerfile
ENTRYPOINT ["java", "-cp", "/app/classes:/app/lib/*", "demo.ContainerConsoleDemo"]
~~~

Đây là **exec form**, không bọc Java trong một lệnh shell thừa. Đối với một service chạy dài, cấu hình này giúp việc chuyển signal từ container runtime đến tiến trình Java rõ ràng hơn so với nhiều kiểu shell wrapper không dùng exec.

Khi Docker hoặc Kubernetes yêu cầu dừng, tiến trình có thể nhận tín hiệu kết thúc theo chính sách runtime. Ứng dụng cần thiết kế **graceful shutdown**: ngừng nhận việc mới, hoàn tất hoặc hủy tác vụ hợp lý, đóng tài nguyên và cho logging backend flush/stop theo lifecycle phù hợp.

**Không giả định mọi signal hoặc forced kill đều được xử lý đầy đủ.** Nếu container bị kill đột ngột, node chết hoặc timeout shutdown, những event trong buffer/async queue có thể chưa xuất ra stream. Ngay cả khi logger đã flush cục bộ, collector từ xa vẫn có thể chưa lưu bền vững.

### AsyncAppender và chi phí console I/O

Logback có **AsyncAppender** để đẩy một số công việc I/O sang worker qua queue:

~~~text
Application thread
       |
       v
  AsyncAppender -> queue -> ConsoleAppender -> stdout
~~~

Cách này có thể giảm thời gian thread nghiệp vụ phải chờ ghi console khi tải cao. Nhưng queue có giới hạn và chính sách bỏ event hoặc block khi đầy; shutdown đột ngột có thể làm mất event chưa chuyển.

Cần đo **log volume, kích thước message, queue capacity, discard/block policy, shutdown flush** trên tải thực. Không mặc định chuyển sang async là luôn nhanh hơn hoặc an toàn hơn.

### stdout buffering

Một số chương trình ghi stdout qua buffer, vì vậy thời điểm log xuất có thể khác thời điểm gọi phương thức. Backend Java có thể có chính sách flush riêng. Ví dụ JUL StreamHandler có thể cần **flush()** trong chương trình chạy rất ngắn; Logback ConsoleAppender có cơ chế ghi khác.

Không suy luận rằng một dòng chưa xuất tức là Logger chưa chạy. Cần kiểm tra level/filter, buffer, runtime, reader, collector và thời điểm process dừng.

## 12. File log trong container có phải luôn sai?

Không. Nhưng cần hiểu trách nhiệm khác nhau.

| Cách ghi | Phù hợp khi | Cần chú ý |
| --- | --- | --- |
| **ConsoleAppender → stdout/stderr** | Dịch vụ trong container, hạ tầng đã thu log stream | Driver/collector, rotation, retention, dữ liệu nhạy cảm |
| **FileAppender trong container** | Ứng dụng cũ hoặc yêu cầu file nội bộ đặc biệt | File có thể không hiện trong docker logs, filesystem có thể mất khi xóa container |
| **File trên persistent volume** | Chính sách lưu file cụ thể | Quản lý volume, nhiều replica, rotation, quyền và thu thập |
| **Sidecar/agent đọc file** | Hệ thống cần parse/ship file log | Đường dẫn chia sẻ, chính sách đa container, tài nguyên tăng |
| **Audit/event store riêng** | Sự kiện cần bảo toàn theo hợp đồng nghiệp vụ | Không phụ thuộc vào console log vốn có thể bị mất |

Khác biệt quan trọng là **logging để quan sát** và **lưu sự kiện nghiệp vụ có cam kết bền vững**. Một lời gọi LOG.info không thay thế transaction commit, outbox pattern hoặc kho audit theo yêu cầu tuân thủ.

Khi có nhiều replica, đường dẫn file bên trong container không phải một nơi duy nhất chứa mọi log của service. Console + collector tập trung thường giúp tránh phải truy cập từng node/volume để tìm sự cố.

## 13. Bảo mật log trong container

Log console có thể được thu thập bởi daemon, container runtime, agent trên node, dịch vụ cloud, hệ thống CI/CD hoặc nền tảng phân tích. Không nên xem nó là dữ liệu “chỉ xuất tạm trong terminal của developer”.

Nguyên tắc:

- **Không ghi password, API key, bearer token, refresh token, session cookie, private key hoặc dữ liệu thẻ** ở mọi level.
- Không mặc định ghi **toàn bộ HTTP body, Authorization header hoặc toString() của object** có dữ liệu riêng tư.
- Exception/stack trace có thể mang thông tin nội bộ, đường dẫn hoặc nội dung nhạy cảm; cần masking và phân quyền.
- Mã yêu cầu/định danh nghiệp vụ cũng có thể nhạy cảm tùy chính sách. Đừng dùng ID có thông tin cá nhân trực tiếp nếu không cần.
- Dùng encoder escape giá trị không tin cậy để hạn chế giả mạo bản ghi log.
- Giới hạn quyền đọc log trên Docker daemon, cluster và nền tảng tập trung; việc được xem Pod không tự đồng nghĩa nên được xem mọi nội dung log.
- Có chính sách **retention, xóa dữ liệu và giới hạn kích thước**; log lâu dài có thể trở thành kho chứa dữ liệu nhạy cảm không mong muốn.
- Nếu muốn thêm **traceId, requestId** để điều tra, đảm bảo chúng được tạo và truyền hợp lệ qua các service, không ghi bí mật vào ID.

Mức DEBUG/TRACE có thể làm lộ nhiều chi tiết hơn khi bật trong production, nên chỉ bật có chọn lọc và thời hạn cần thiết. Không ghi bí mật ở DEBUG với lý do “bình thường production chỉ bật INFO”.

## 14. Hiệu năng, lượng log và hệ thống quan sát

Console logging có chi phí ở nhiều lớp: format message, encode JSON/text, ghi stream, runtime lưu/đóng gói, collector đọc/chuyển tiếp và log store lưu/index.

Các cách kiểm soát:

1. Đặt **level hợp lý**: INFO cho sự kiện quan trọng, WARN cho bất thường, ERROR cho thất bại, DEBUG/TRACE cho điều tra có chọn lọc.
2. Tránh một INFO cho từng phần tử trong vòng lặp lưu lượng cao mà không có giá trị chẩn đoán.
3. Dùng **parameterized logging** để giảm thao tác nối chuỗi thừa.
4. Tránh tính các biểu thức tốn CPU trước khi Logger biết level; dùng guard hoặc cơ chế lazy có hỗ trợ.
5. Dùng **metrics** cho số đếm/tỷ lệ/latency theo thời gian, **tracing** cho request xuyên service.
6. Kiểm soát kích thước stack trace và dữ liệu đi kèm, không xóa bằng chứng quan trọng một cách máy móc.
7. Kiểm tra rotation/storage của runtime và quota/retention của collector.
8. Quan sát **dropped logs, parse errors, queue lag và disk usage** khi hạ tầng cung cấp số liệu.

Ví dụ SLF4J:

~~~java
// Đoạn minh họa cần LOG, payload và expensiveSerialize().
LOG.debug("payload={}", expensiveSerialize(payload));

if (LOG.isDebugEnabled()) {
    LOG.debug("payload={}", expensiveSerialize(payload));
}
~~~

Lời gọi thứ nhất vẫn đánh giá **expensiveSerialize(payload)** khi DEBUG bị tắt vì Java tính đối số trước lời gọi. Nhánh if của lời gọi thứ hai giúp tránh chi phí đó khi level không được bật. **isDebugEnabled không bảo đảm appender/collector sẽ ghi thành công event**.

Không đặt logic nghiệp vụ có side effect bắt buộc bên trong nhánh dùng để tối ưu logging.

## 15. Những lỗi thường gặp

| Lỗi | Triệu chứng | Cách xử lý |
| --- | --- | --- |
| Log chỉ ghi file bên trong container | docker logs/kubectl logs không thấy | Dùng console hoặc agent đọc file riêng |
| Dùng JUL ConsoleHandler mà tưởng stdout | Redirect sai stream | Nhớ JUL mặc định stderr, Logback ConsoleAppender thường stdout |
| Root INFO nhưng tìm DEBUG | Không có dòng debug | Đổi effective level của đúng logger |
| Appender filter chặn sự kiện | Code gọi log nhưng không thấy | Kiểm tra filter, appender-ref, additivity |
| Gắn appender ở logger con và root | Một event xuất hai lần | Xem appender-ref và additivity |
| Chỉ thêm SLF4J API, thiếu provider | Log không được xử lý như dự kiến | Chọn một provider tương thích |
| Có nhiều provider/bridge xung đột | Backend không như mong muốn | Kiểm tra dependency tree và routing |
| Dùng docker run --rm rồi docker logs | Container đã bị xóa | Chạy không --rm nếu cần đọc lại |
| Xem sai Pod/container trong Kubernetes | Log tưởng bị thiếu | Chọn namespace, pod, -c đúng |
| Mong kubectl logs lưu lịch sử vô hạn | Log cũ không còn | Dùng collector và retention phù hợp |
| Không cấu hình runtime rotation | Disk của node/host tăng | Đặt chính sách driver/kubelet đúng hạ tầng |
| Message chứa raw newline/stack trace | Một event thành nhiều dòng | JSON Lines hoặc multiline parser |
| Dùng timestamp không có timezone | Khó so nhiều node | Thống nhất thời gian có offset/UTC |
| Bật DEBUG toàn hệ thống lâu dài | Log volume/chi phí tăng | Bật theo logger, có thời hạn |
| Không flush hoặc dừng đột ngột | Thiếu log cuối trước shutdown | Graceful shutdown và chính sách flush |
| Ghi token/raw request vào stdout | Collector lưu dữ liệu nhạy cảm | Data minimization, masking, access control |
| Coi stream=stderr là severity=ERROR | Phân loại sai log | Đọc trường level hoặc normalize tại collector |

## 16. Checklist xử lý khi không thấy log container

Khi nghi log bị mất, kiểm tra theo thứ tự:

1. **Mã Java thực sự gọi Logger chưa?** Event được phát ở tình huống đang kiểm tra không?
2. **Logger level và filter:** event có qua ngưỡng logger, appender và TurboFilter không?
3. **Backend nào đang chạy:** Logback/JUL/Log4j 2; có đúng file cấu hình và provider?
4. **Appender/Handler:** target đang System.out, System.err hay file?
5. **Docker:** container còn tồn tại không, đang dùng logging driver nào, có cấu hình rotation/caching gì?
6. **Kubernetes:** đúng namespace, Pod, tên container, container hiện tại hay previous?
7. **Dữ liệu đã ra stream chưa:** có buffer/flush, lifecycle shutdown hoặc PID 1 forwarding vấn đề không?
8. **Collector:** có hoạt động không, có parse sai JSON/multiline hoặc filter theo stream không?
9. **Retention:** dữ liệu đã quá hạn, log bị rotate/cắt hay container/Pod đã bị xóa?
10. **Tương quan:** có đúng requestId/traceId/time range không? Timestamp từ app hay runtime?
11. **Lưu lượng:** queue/appender/collector có nghẽn hoặc drop event dưới tải không?
12. **Bảo mật:** có log bị redaction hoặc quyền truy vấn không đủ không?

Không tự sửa hàng loạt logger để INFO/ERROR “chắc chắn in” mà chưa biết log mất ở tầng nào. Đổi level sai có thể làm log quá nhiều, tăng chi phí và rủi ro lộ dữ liệu.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Logback ConsoleAppender mặc định hướng tới stdout hay stderr?

**Đáp án:** Thông thường **System.out**; có thể đặt target System.err. JUL ConsoleHandler mặc định lại ghi stderr.

**Câu 2.** Tại sao một file /app/logs/app.log có nội dung nhưng docker logs trống?

**Đáp án:** docker logs đọc log theo cơ chế logging driver từ stdout/stderr, không tự đọc mọi file trong filesystem container. Cần appender console hoặc một giải pháp thu thập file được cấu hình riêng.

**Câu 3.** Docker logs và Kubernetes kubectl logs có phải giải pháp retention tập trung vô thời hạn không?

**Đáp án:** Không. Chúng phụ thuộc log còn khả dụng ở runtime/node. Với tìm kiếm dài hạn, cần logging platform/collector và chính sách lưu phù hợp.

**Câu 4.** Appender Logback ghi ERROR vào stdout. Collector có được mặc định hiểu đó là INFO vì stream là stdout không?

**Đáp án:** Không. Stream là đích I/O; severity phải dựa trên level thực tế hoặc quy tắc normalization có căn cứ.

**Câu 5.** Trong ví dụ root INFO, vì sao LOG.debug không xuất nhưng LOG.warn xuất?

**Đáp án:** DEBUG thấp hơn ngưỡng INFO nên bị logger loại, còn WARN đủ ngưỡng để tới ConsoleAppender nếu không có filter khác.

**Câu 6.** Nếu có hai ConsoleAppender target khác nhau, có tự động tách INFO và ERROR không?

**Đáp án:** Không. Cần filter phù hợp để tránh cùng event xuất cả hai stream. Mục 8 trình bày một cách cấu hình.

**Câu 7.** Khi chạy kubectl logs --previous, có chắc xem lại được mọi container đã restart từ nhiều ngày trước không?

**Đáp án:** Không. Tùy chọn previous chỉ phục vụ log của phiên bản container trước khi còn khả dụng trong ngữ cảnh Pod, không phải kho lịch sử vô hạn.

**Câu 8.** Vì sao JSON Lines hữu ích cho logging container?

**Đáp án:** Mỗi event trên một dòng vật lý, các trường có tên và kiểu rõ, dễ parse. Nhưng vẫn cần encoder đúng và collector có cấu hình nhận/parse/index.

**Câu 9.** Tại sao không nên log access token vào stdout ngay cả khi container chỉ nằm trong cluster nội bộ?

**Đáp án:** Hệ thống thu log có thể lưu/chia sẻ rộng hơn app; cần kiểm soát dữ liệu nhạy cảm ở mọi level.

**Câu 10.** AsyncAppender có bảo đảm không bao giờ mất log khi container dừng đột ngột không?

**Đáp án:** Không. Hàng đợi có thể còn event chưa flush, bị drop khi quá tải hoặc khi runtime kill; cần chính sách shutdown và giám sát phù hợp.

**Câu 11.** Có thể dựa vào thứ tự dòng từ System.out và System.err sau khi collector gộp lại để kết luận thứ tự thực thi tuyệt đối không?

**Đáp án:** Không. Hai stream độc lập có buffering và đường thu thập khác nhau; dùng timestamp, correlation ID và trace để phân tích.

**Câu 12.** Trong container, có nên dùng println thay logging framework cho mọi code production không?

**Đáp án:** Không nên mặc định như vậy. Println thiếu level, filter, cấu hình formatter/encoder, Throwable và context tích hợp. Logger với ConsoleAppender thường linh hoạt và dễ quan sát hơn.

## 18. Kết luận

**Console trong container** là một ranh giới quan sát quan trọng: ứng dụng Java ghi sự kiện ra **stdout/stderr**, runtime có thể ghi/đưa stream đó tới lệnh Docker/Kubernetes, và collector tập trung có thể tiếp tục parse, lưu, tìm kiếm và cảnh báo.

Một cấu hình vận hành tốt cần:

1. **Gọi Logger thay vì rải rác println** trong mã nghiệp vụ.
2. **Đặt appender/handler vào đúng stream**, có level và filter rõ ràng.
3. **Dùng format ổn định**, có timestamp, event code, request/trace ID, encoding và Throwable phù hợp.
4. **Quản lý logging driver, rotation, collector và retention** ở hạ tầng.
5. **Bảo vệ dữ liệu nhạy cảm, đo hiệu năng và xử lý graceful shutdown**.

**Ghi được một dòng ra console chỉ là bước đầu; phải kiểm chứng cả đường đi từ Java đến hệ thống thu thập để log thực sự phục vụ điều tra và vận hành.**
