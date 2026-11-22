# Container configuration cho Java Logging: Docker và Kubernetes

## 1. Mục tiêu

Khi đưa ứng dụng Java vào Docker container hoặc Kubernetes Pod, logging không chỉ còn là chọn mức INFO/DEBUG và tên file log. Cần quyết định **log đi ra đâu**, ai thu thập và xoay vòng log, cấu hình được truyền vào lúc nào, log có còn sau khi container bị xóa hay không, và cách giữ tương quan giữa log của nhiều bản sao (replica).

Sau bài này, người học có thể:

1. Cấu hình Java logging để ghi sự kiện ra stdout/stderr, hiểu sự khác nhau giữa log của ứng dụng và log do runtime container lưu.
2. Chuyển logging level, môi trường chạy và tên dịch vụ vào container bằng biến môi trường hoặc file cấu hình.
3. Thiết lập Docker logging driver và giới hạn dung lượng lưu log.
4. Dùng ConfigMap, env và volume trên Kubernetes; phân biệt cập nhật file cấu hình với việc ứng dụng thực sự reload.
5. Thu thập, kiểm tra và xử lý log khi Pod restart, scale, bị evict hoặc node mất.
6. Tránh lỗi phổ biến về multi-line, JSON log, permission, secrets, cấu hình sai classpath và mất log lúc shutdown.

Bối cảnh bài là **Java Core Logging trong môi trường container**. Các ví dụ bên dưới dùng JDK 17 và thư viện chuẩn để dễ chạy, sau đó liên hệ tới Spring Boot, Logback và Log4j 2.

## 2. Container logging hoạt động thế nào?

Ứng dụng Java có thể tạo log qua java.util.logging (JUL), SLF4J với Logback/Log4j 2 hoặc framework khác. Trong container, cách tích hợp phổ biến nhất là:

~~~text
Java Logger / Handler / Appender
           │
           ├── stdout (standard output)
           └── stderr (standard error)
                    │
                    ▼
             Container runtime
                    │
       ┌────────────┴────────────┐
       │                         │
     Docker                   Kubernetes
  logging driver             CRI + kubelet
       │                         │
  docker logs               kubectl logs
       │                         │
       └────────► collector ◄────┘
                        │
               central log backend
           (search, retention, alerting)
~~~

Luồng này có **ba lớp cấu hình khác nhau**:

| Lớp | Ví dụ cấu hình | Chịu trách nhiệm |
| --- | --- | --- |
| Ứng dụng Java | JUL logging.properties, logback.xml, log4j2.xml, Spring Boot logging.* | Level, logger name, định dạng, appender, MDC/trace ID, nơi phát log |
| Container runtime / node | Docker logging driver; kubelet containerLogMaxSize, containerLogMaxFiles | Thu nhận stdout/stderr, lưu tạm, xoay vòng log ở node |
| Logging pipeline / backend | DaemonSet collector, OpenTelemetry Collector, Fluent Bit, hệ thống lưu tập trung | Bổ sung metadata, parse, lọc, chuyển tiếp, retention, tìm kiếm/alert |

**Không nhầm file log trong filesystem của container với log của stdout/stderr.** Nếu ứng dụng ghi vào /app/logs/app.log thì docker logs hoặc kubectl logs thường sẽ không tự đọc file đó. Muốn xem qua các lệnh trên, appender phải xuất ra stream mà runtime thu thập, hoặc có giải pháp forward riêng.

Docker json-file ghi một định dạng envelope chứa log/stream/time để runtime quản lý. Envelope đó **không đồng nghĩa** nội dung message của ứng dụng đã là structured JSON. Nếu muốn query theo trace_id/level/service, nên cân nhắc log từng dòng JSON được ứng dụng/encoder tạo ra, rồi cho collector parse đúng trường.

## 3. Chiến lược mặc định: một event cho mỗi dòng stdout/stderr

Với service Java chạy trong container, lựa chọn đơn giản, phổ biến:

- Ghi log ứng dụng ra stdout hoặc stderr; mức độ khẩn cấp không bắt buộc đồng nghĩa một stream cụ thể, vì mỗi logging backend có cách cấu hình riêng.
- Dùng logging framework đã hỗ trợ concurrent logging và cung cấp một event hoàn chỉnh trong một lời gọi.
- Cấu hình level theo môi trường, giới hạn lượng DEBUG/TRACE ở production.
- Ghi timestamp có timezone rõ ràng (thường UTC/ISO 8601) cùng level, logger/service, message, request_id/trace_id khi có.
- Để runtime/kubelet/collector quản lý phần lưu tạm, rotation và shipping; đừng tự chia sẻ một file log bên trong nhiều replica.
- Giữ thông tin cần thiết cho chẩn đoán nhưng tránh token, mật khẩu, cookie, dữ liệu cá nhân nhạy cảm.

### stdout và stderr

System.out và System.err là hai stream của process. Docker và Kubernetes thông thường đều thu thập cả hai stream. Tuy nhiên **JUL ConsoleHandler mặc định ghi ra System.err**, kể cả khi log có level INFO. Nhiều backend khác có thể ghi toàn bộ level ra stdout qua console appender được cấu hình. Vì vậy không suy rằng “INFO luôn stdout, ERROR luôn stderr”.

Dữ liệu trong docker logs thường là tổng hợp log được driver hỗ trợ lưu từ hai stream. Trong Kubernetes, kubectl logs đọc log container qua API/kubelet. Các công cụ này không thay thế bộ lưu trữ dài hạn cho toàn cluster.

### Console JSON so với text

Text dễ đọc trực tiếp:

~~~text
INFO service=orders env=prod trace_id=... order accepted
~~~

JSON dễ query ở collector:

~~~json
{"timestamp":"2026-11-10T02:00:00Z","level":"INFO","service":"orders","environment":"prod","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"order accepted"}
~~~

Hai dòng trên minh họa định dạng, không phải output mặc định của JDK. Một event nên tạo thành một dòng có cấu trúc ổn định, kèm ký tự newline kết thúc. Nếu message hoặc stack trace có xuống dòng, encoder JSON nên escape nội dung phù hợp thay vì phá bản ghi thành nhiều dòng không được đánh dấu rõ.

## 4. Ví dụ hoàn chỉnh: Java 17 đọc logging configuration từ env

Đây là chương trình **chạy độc lập bằng JDK 17+**, không phụ thuộc Spring Boot hay thư viện ngoài. Nó đọc ba biến môi trường:

| Biến | Mặc định | Công dụng |
| --- | --- | --- |
| APP_LOG_LEVEL | INFO | Ngưỡng log theo tên level của JUL, ví dụ INFO, FINE, WARNING |
| APP_ENV | local | Tên môi trường chạy, ví dụ dev, staging, prod |
| SERVICE_NAME | orders | Tên service được gắn trong thông điệp |

**Lưu ý:** APP_LOG_LEVEL là tên do **chính chương trình ví dụ** định nghĩa. JUL không tự đọc một biến tên APP_LOG_LEVEL; việc đọc env, parse và áp dụng level phải do code hoặc framework cấu hình.

Cấu trúc:

~~~text
container-logging-demo/
├── src/
│   └── example/
│       └── ContainerLoggingDemo.java
└── Dockerfile
~~~

**src/example/ContainerLoggingDemo.java**

~~~java
package example;

import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ContainerLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(ContainerLoggingDemo.class.getName());

    private static String safeTag(String name, String fallback) {
        String value = System.getenv().getOrDefault(name, fallback);
        if (!value.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid setting: " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String service = safeTag("SERVICE_NAME", "orders");
        String environment = safeTag("APP_ENV", "local");

        String configuredLevel = System.getenv()
                .getOrDefault("APP_LOG_LEVEL", "INFO")
                .trim()
                .toUpperCase(Locale.ROOT);

        // Tên level không hợp lệ sẽ gây lỗi rõ ràng khi khởi động.
        Level threshold = Level.parse(configuredLevel);

        // Không chuyển event lên root handler để tránh in trùng.
        LOG.setUseParentHandlers(false);
        LOG.setLevel(threshold);

        // JUL ConsoleHandler ghi vào stderr; runtime container thu thập.
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " service=" + service
                        + " env=" + environment
                        + " message=" + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        try {
            LOG.info("started");
            LOG.fine("diagnostic detail");
            LOG.warning("sample warning");
        } finally {
            console.flush();
            LOG.removeHandler(console);
            console.close();
        }
    }
}
~~~

Chương trình cố ý ngắn, ghi ba event rồi kết thúc để dễ kiểm tra cấu hình. Lớp safeTag giới hạn giá trị từ env dùng làm metadata, giảm nguy cơ các ký tự xuống dòng hoặc dữ liệu quá dài làm hỏng định dạng log. Ứng dụng production có thể dùng chuẩn validation riêng; không dùng regex này để kiểm tra mọi loại giá trị cấu hình.

### Chạy trực tiếp trên máy có JDK

Từ thư mục gốc của ví dụ:

~~~bash
javac -encoding UTF-8 -d out src/example/ContainerLoggingDemo.java
java -cp out example.ContainerLoggingDemo
~~~

Log do chương trình ghi trên **stderr**, với cấu hình mặc định:

~~~text
INFO service=orders env=local message=started
WARNING service=orders env=local message=sample warning
~~~

Dòng FINE không xuất hiện vì level đang là INFO. Để thấy FINE, cấu hình biến môi trường trước khi khởi chạy. Trên hệ shell hỗ trợ cú pháp POSIX:

~~~bash
APP_LOG_LEVEL=FINE APP_ENV=staging SERVICE_NAME=payments java -cp out example.ContainerLoggingDemo
~~~

Kết quả trên stderr:

~~~text
INFO service=payments env=staging message=started
FINE service=payments env=staging message=diagnostic detail
WARNING service=payments env=staging message=sample warning
~~~

Trên Windows PowerShell, biến môi trường có cú pháp khác, ví dụ:

~~~powershell
$env:APP_LOG_LEVEL = "FINE"
$env:APP_ENV = "staging"
$env:SERVICE_NAME = "payments"
java -cp out example.ContainerLoggingDemo
~~~

Cả hai cách khởi động đều sử dụng cùng chương trình đã biên dịch. **Giá trị env được đọc khi process bắt đầu.** Thay env của shell sau khi JVM đã chạy không khiến chương trình đang chạy tự cập nhật log level.

### Tính đúng đắn của ví dụ

LOG.setLevel(threshold) điều khiển việc tạo event ở logger. ConsoleHandler được setLevel(Level.ALL) để handler không chặn thêm các event đã qua logger. setUseParentHandlers(false) ngăn root handler mặc định in thêm bản sao. Formatter chỉ xuất level, service, environment, message nên output ổn định, không có timestamp/stack trace ngẫu nhiên. ConsoleHandler tự flush khi publish; phần finally dọn handler khi hoàn tất. Dữ liệu sample warning chỉ nhằm quan sát WARNING, không biểu thị lỗi thực tế.

## 5. Đóng gói chương trình bằng Docker multi-stage build

**Dockerfile** tại root của ví dụ:

~~~dockerfile
FROM eclipse-temurin:17-jdk AS build
WORKDIR /workspace
COPY src/example/ContainerLoggingDemo.java /workspace/src/example/ContainerLoggingDemo.java
RUN javac -encoding UTF-8 -d /workspace/out /workspace/src/example/ContainerLoggingDemo.java

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /workspace/out /app/classes
ENV APP_LOG_LEVEL=INFO APP_ENV=local SERVICE_NAME=orders
USER 10001
ENTRYPOINT ["java", "-cp", "/app/classes", "example.ContainerLoggingDemo"]
~~~

Giải thích:

- Stage build dùng JDK để biên dịch, stage cuối dùng JRE để chạy, không mang compiler vào image runtime.
- ENTRYPOINT ở dạng exec (mảng JSON) chạy trực tiếp process Java, thuận lợi cho quản lý tín hiệu dừng và exit code.
- ENV đặt **mặc định trong image**; docker run -e và Kubernetes env có thể cung cấp giá trị ở lúc tạo container.
- USER 10001 minh họa chạy non-root; ví dụ chỉ đọc class và ghi ra stderr nên không cần thư mục log có quyền ghi.
- Tag image eclipse-temurin:17-jdk và :17-jre có thể được cập nhật theo thời gian. Triển khai production nên quản lý phiên bản/digest image theo chính sách dự án.

Build và chạy (yêu cầu có Docker Engine/Desktop hoạt động):

~~~bash
docker build -t container-logging-demo:1.0 .
docker run --name log-demo \
  --log-driver local \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  -e APP_LOG_LEVEL=FINE \
  -e APP_ENV=staging \
  -e SERVICE_NAME=payments \
  container-logging-demo:1.0
~~~

Container chạy chương trình một lần rồi thoát với exit code 0 nếu không có lỗi. Output xuất hiện trong terminal chạy docker run:

~~~text
INFO service=payments env=staging message=started
FINE service=payments env=staging message=diagnostic detail
WARNING service=payments env=staging message=sample warning
~~~

Vì không dùng --rm, có thể đọc lại log và sau đó xóa container:

~~~bash
docker logs log-demo
docker inspect --format '{{.HostConfig.LogConfig.Type}}' log-demo
docker rm log-demo
~~~

Lệnh docker logs hiển thị lại các dòng ở trên, không phải chương trình chạy lần thứ hai. Câu lệnh inspect ở ví dụ trả về local vì lần chạy này chỉ định driver local. Docker CLI hỗ trợ cú pháp xuống dòng tùy shell; trên PowerShell có thể gõ cùng lệnh docker run trên một dòng thay vì dùng dấu backslash nối dòng kiểu shell POSIX.

**Không thêm -it trừ khi cần tương tác**; bật pseudo-TTY có thể ảnh hưởng cách stdout/stderr được phân biệt. Với service backend thông thường, chạy không có TTY sẽ thuận lợi hơn cho thu thập log.

## 6. Docker logging driver, giới hạn dung lượng và vòng đời log

Docker có logging drivers như json-file, local, journald, syslog, fluentd hoặc driver/plug-in bên thứ ba. Driver quyết định cách Docker lưu hoặc chuyển tiếp stdout/stderr; nó không thay thế appender hoặc logging level ở Java.

### json-file và local

Theo tài liệu Docker, json-file là driver mặc định của Docker Engine trong nhiều thiết lập, chủ yếu vì tương thích ngược. Nếu không cấu hình giới hạn, log có thể tăng đến mức làm đầy disk. Driver local tối ưu lưu trữ và có rotation mặc định, thường phù hợp với những máy chạy container thông thường.

Ví dụ chỉ định json-file và giới hạn cho **một container**:

~~~bash
docker run --name log-demo-json \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  container-logging-demo:1.0
~~~

Cấu hình driver mặc định ở Docker daemon (tệp daemon.json, đường dẫn tùy hệ điều hành):

~~~json
{
  "log-driver": "local",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
~~~

Các giá trị log-opts trong cấu hình Docker daemon được biểu diễn bằng **string**, kể cả các giá trị nhìn giống số. Sau khi cập nhật daemon.json, cần reload/restart Docker theo tài liệu môi trường chạy. **Thay cấu hình mặc định của daemon không tự đổi logging driver của container đã tồn tại**; container mới sẽ nhận cấu hình mới khi được tạo, nếu không ghi đè tùy chọn.

### Cần phân biệt retention và độ bền dữ liệu

Giới hạn max-size/max-file là **giữ dung lượng log trên node trong mức mong muốn**, không bảo đảm log được giữ dài hạn. Khi container bị xóa hoặc host gặp sự cố, dữ liệu runtime lưu cục bộ có thể không còn. Để tra cứu lịch sử qua nhiều node, gửi log tới backend tập trung và đặt chính sách retention tại đó.

Cũng không nên mở trực tiếp các file nội bộ mà Docker dùng cho json-file hoặc local driver rồi tự xóa/xoay vòng; Docker quản lý định dạng và metadata của chúng. Dùng docker logs, driver settings và công cụ thu thập tương thích.

### Blocking, non-blocking và mất log

Một số driver/cấu hình Docker hỗ trợ chế độ giao log blocking hoặc non-blocking. Khi nơi nhận log chậm hoặc buffer đầy, producer có thể bị chặn, hoặc các thông điệp bị loại bỏ tùy chế độ và cấu hình. Điều này độc lập một phần với async appender ở Java: có thể có **hàng đợi ở cả ứng dụng lẫn runtime**.

Vì vậy phải theo dõi dung lượng, dropped logs, lỗi collector và độ trễ ghi theo hệ thống thực tế. Log ứng dụng không thay thế audit store cần tính bền vững giao dịch.

## 7. Kubernetes: cấu hình bằng ConfigMap và env

Kubernetes thường chạy nhiều Pod cho cùng service. Mỗi container phát log ra stdout/stderr, runtime ghi theo giao thức CRI, kubelet phục vụ kubectl logs và đảm nhiệm việc rotation ở node. Để log tồn tại sau vòng đời Pod/node, cần một giải pháp cluster-level logging.

### 7.1. Cấu hình chạy bằng ConfigMap

Ví dụ sau sử dụng **chính image Docker của mục 5**. Vì chương trình Java demo kết thúc ngay sau khi ghi vài dòng, ta dùng **Job** thay vì Deployment; nếu dùng Deployment cho chương trình một lần rồi thoát, Pod sẽ bị restart theo chính sách của Deployment và không thể hiện đúng mục đích học.

**container-logging-k8s.yaml**

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: container-logging-settings
data:
  APP_LOG_LEVEL: "FINE"
  APP_ENV: "staging"
  SERVICE_NAME: "payments"
---
apiVersion: batch/v1
kind: Job
metadata:
  name: container-logging-demo
spec:
  backoffLimit: 0
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: app
          image: container-logging-demo:1.0
          imagePullPolicy: IfNotPresent
          envFrom:
            - configMapRef:
                name: container-logging-settings
~~~

Giải thích:

- ConfigMap chứa cấu hình không bí mật theo dạng key/value.
- envFrom biến các key hợp lệ thành biến môi trường trong process; Java đọc được qua System.getenv.
- Image phải **thực sự có sẵn trong container runtime của node**, hoặc được đẩy lên registry và Job dùng image reference truy cập được. Một image chỉ tồn tại trong Docker của máy cá nhân không mặc nhiên có trong mọi node Kubernetes.
- Với cluster kind mặc định để thực hành local, có thể nạp image bằng kind load docker-image container-logging-demo:1.0 trước khi apply. Với cluster quản lý từ xa, cần image trong registry và cấu hình quyền pull phù hợp.
- Job dùng restartPolicy Never vì đây là ứng dụng ngắn hạn. Service HTTP/JVM sống lâu nên dùng Deployment và cần process chạy liên tục.

Thực hiện khi cluster Kubernetes đã sẵn sàng và image đã có trên node:

~~~bash
kubectl apply -f container-logging-k8s.yaml
kubectl logs job/container-logging-demo -c app
kubectl get job container-logging-demo
~~~

Các dòng log ứng dụng kỳ vọng là:

~~~text
INFO service=payments env=staging message=started
FINE service=payments env=staging message=diagnostic detail
WARNING service=payments env=staging message=sample warning
~~~

kubectl logs job/... giải quyết Pod phù hợp của Job; nếu chưa chạy xong, có thể cần xem trạng thái Pod và thử lại sau khi nó đã tạo container. Nếu không thấy log, kiểm tra lỗi pull image, sự kiện Pod và namespace trước khi kết luận Java logging bị lỗi.

**Lưu ý cập nhật:** thay data trong ConfigMap **không tự thay env của một Pod đang chạy**. Với ứng dụng dạng Deployment, cần triển khai lại/rolling restart để Pod mới nhận env mới. Với Job đã hoàn thành, muốn chạy lại với giá trị mới phải tạo lần thực thi mới phù hợp, không trông chờ Job cũ tự khởi động lại.

### 7.2. Mount file cấu hình từ ConfigMap

Một số ứng dụng dùng Logback/Log4j 2/JUL phải đọc XML hoặc .properties thay vì chỉ dùng env. Khi đó có thể mount ConfigMap vào file trong container.

**Ví dụ cho Spring Boot sử dụng Logback**:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-logback
data:
  logback-spring.xml: |
    <configuration>
      <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
          <pattern>%d{ISO8601} %-5level service=orders %logger - %msg%n</pattern>
        </encoder>
      </appender>
      <root level="INFO">
        <appender-ref ref="CONSOLE"/>
      </root>
    </configuration>
~~~

Đoạn Deployment bên dưới minh họa cách app Spring Boot **có sẵn trong image** chọn file đó; image phải chứa ứng dụng Boot thật, không phải chương trình Java nhỏ ở mục 4:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: app
          image: registry.example.com/orders:1.0
          env:
            - name: LOGGING_CONFIG
              value: "file:/etc/app/logging/logback-spring.xml"
          volumeMounts:
            - name: logging-config
              mountPath: /etc/app/logging
              readOnly: true
      volumes:
        - name: logging-config
          configMap:
            name: orders-logback
~~~

Image và registry ở manifest Deployment là **ví dụ kiến trúc**; phải thay bằng image Spring Boot thực tế được publish và truy cập được trước khi triển khai. Đoạn cấu hình không thêm các mục health check, resource limits hay network vì những phần đó phụ thuộc ứng dụng cụ thể.

Kubernetes project mỗi key ConfigMap thành một file dưới mountPath; với ConfigMap ở ví dụ, file là /etc/app/logging/logback-spring.xml. Spring Boot dùng LOGGING_CONFIG để chọn cấu hình logging tương ứng từ lúc khởi động.

**Một số lưu ý quan trọng:**

- Mount ConfigMap dưới dạng volume có thể được kubelet cập nhật **sau một khoảng trễ** khi ConfigMap đổi. Điều đó **không bảo đảm** logging backend tự reload; ứng dụng có thể chỉ nạp cấu hình một lần khi startup.
- Nếu dùng volumeMount với subPath trỏ tới một key, file đã mount sẽ **không nhận cập nhật ConfigMap tự động** theo cơ chế thông thường.
- Cấu hình truyền qua env của Pod không tự cập nhật khi ConfigMap đổi. Rolling restart thường là cách triển khai thay đổi dễ kiểm soát.
- Một số extension cấu hình của Spring Boot không tương thích với cơ chế scan/reload trực tiếp của Logback; không bật scan chỉ để mong ConfigMap đổi có hiệu lực mà chưa kiểm tra tài liệu backend.
- Dùng ConfigMap cho nội dung không nhạy cảm; Secret và cơ chế quản lý bí mật phù hợp cho dữ liệu nhạy cảm. Tránh đưa cả password/token vào log pattern hoặc MDC.

## 8. Liên hệ Java logging framework thực tế

### 8.1. Java Util Logging

JUL có ConsoleHandler ghi stderr. File cấu hình logging.properties có thể được chọn từ lúc khởi động JVM qua:

~~~bash
java -Djava.util.logging.config.file=/etc/app/logging.properties -jar app.jar
~~~

Trong đó /etc/app/logging.properties phải tồn tại và có cú pháp JUL. Nếu container dùng Kubernetes ConfigMap để mount file, mount tới đường dẫn này rồi truyền system property phù hợp.

**Ví dụ tệp cấu hình JUL:**

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$s %5$s%n
~~~

Ví dụ này dành cho ứng dụng dùng JUL và để JUL tự khởi tạo logger/handler từ LogManager. Chương trình ContainerLoggingDemo ở mục 4 **tự tạo ConsoleHandler và override format/level trong code**, nên không dùng ví dụ file properties này để thay thế hành vi của nó. Khi ứng dụng dùng launcher hoặc entrypoint phức tạp, hãy kiểm tra tùy chọn -D đến được JVM trước khi logger khởi tạo.

### 8.2. Logback và Log4j 2

Với Java dùng SLF4J + Logback, cấu hình file logback.xml/logback-spring.xml tùy môi trường, dùng ConsoleAppender với encoder phù hợp. Khi chạy Spring Boot, file logback-spring.xml được Boot hỗ trợ; còn Logback độc lập thường tìm logback.xml/logback-test.xml hoặc đường dẫn do logback.configurationFile chỉ định.

Với Log4j 2, dùng log4j2.xml/log4j2-spring.xml tùy chế độ chạy, Console appender và PatternLayout/JSON layout phù hợp. Đường dẫn có thể được chỉ định bằng log4j2.configurationFile trong ứng dụng Java thuần. Không trộn cú pháp XML của Logback với XML của Log4j 2, cũng không dùng hai backend chính cùng lúc nếu không có thiết kế rõ ràng.

Ví dụ Logback ConsoleAppender ngắn gọn:

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger trace_id=%X{trace_id:-} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Đây là **cấu hình XML**, không phải chương trình Java chạy độc lập. Các khóa MDC như trace_id chỉ có giá trị nếu app/tracing instrumentation thực sự cung cấp context đó. Một pattern có placeholder trace_id không tự tạo ra distributed trace.

### 8.3. Spring Boot: biến môi trường và structured logging

Spring Boot hỗ trợ ánh xạ thuộc tính từ environment, ví dụ:

~~~text
LOGGING_LEVEL_ROOT=INFO
SPRING_APPLICATION_NAME=orders
~~~

Ở các phiên bản Spring Boot hỗ trợ structured logging tích hợp, có thể chọn JSON ECS ở console bằng cấu hình:

~~~properties
logging.structured.format.console=ecs
~~~

Hoặc cấu hình tương ứng qua env:

~~~text
LOGGING_STRUCTURED_FORMAT_CONSOLE=ecs
~~~

Hỗ trợ thuộc tính này **phụ thuộc phiên bản Spring Boot**, không phải tính năng mặc định của mọi phiên bản hoặc của JUL độc lập. Nếu ứng dụng đã cung cấp custom logback-spring.xml/log4j2-spring.xml, cần kiểm tra encoder/layout tương ứng có thực sự sử dụng cấu hình structured logging từ Boot; một custom console appender tự viết không mặc nhiên đổi sang JSON chỉ vì biến env tồn tại.

Đặt cấu hình mức root qua LOGGING_LEVEL_ROOT thường tiện hơn sửa file trong image cho từng môi trường. Với logging level theo package/class, hãy kiểm tra quy tắc property binding của phiên bản Boot đang dùng, đặc biệt các logger name phân biệt hoa/thường.

## 9. Kubernetes: log rotation và truy xuất khi restart

### 9.1. kubectl logs chỉ là một cửa sổ nhìn vào log node

Kubernetes kubelet quản lý đường dẫn log container và rotation theo cấu hình node. Hai tham số thường gặp:

~~~yaml
containerLogMaxSize: 10Mi
containerLogMaxFiles: 5
~~~

Đây là các khóa **của kubelet configuration**, không phải spec của ứng dụng Deployment hay biến môi trường Java. Giá trị mặc định thường được tài liệu Kubernetes mô tả là 10Mi và 5, nhưng một cluster quản lý có thể chỉnh khác. Không tự áp giá trị vào manifest Pod nếu không có quyền cấu hình kubelet.

Theo tài liệu Kubernetes, kubectl logs thông thường đọc nội dung file log mới nhất do kubelet cung cấp; các log đã được rotate trước đó không nhất thiết xem lại được qua lệnh đó. Nếu container trong Pod được khởi tạo lại, có thể thử:

~~~bash
kubectl logs pod/orders-abc123 -c app --previous
~~~

Tên Pod orders-abc123 chỉ là tên minh họa. Tham số --previous yêu cầu log của instance trước của container, khi instance đó và log còn được node giữ. Nó không phải kho lưu mọi lần restart và không giúp khôi phục log của Pod đã bị xóa/evict hoặc node đã mất.

Để điều tra Pod đang chạy:

~~~bash
kubectl get pods -l app=orders
kubectl logs deployment/orders -c app --tail=100
kubectl logs deployment/orders -c app --since=10m
~~~

Lệnh có Deployment chỉ thuận tiện khi có thể chọn Pod/container phù hợp. Khi chạy nhiều replica và cần xem **tất cả**, hãy truy vấn bằng label selector cùng giới hạn/concurrency phù hợp với kubectl đang dùng, hoặc tốt nhất dùng backend tập trung để tổng hợp.

### 9.2. Cluster-level logging

Hệ thống production thường bố trí collector ở node (ví dụ DaemonSet) để đọc log container, bổ sung metadata như namespace, pod, container, node và gửi tới nơi lưu trữ độc lập. Một số hệ thống dùng sidecar khi ứng dụng chỉ ghi file hoặc cần xử lý đặc biệt.

Nên xác định rõ trách nhiệm:

- Ứng dụng quyết định field nghiệp vụ và độ nhạy cảm của thông điệp.
- Runtime/kubelet quản lý việc nhận stream và rotation cục bộ.
- Collector chịu trách nhiệm parsing, bổ sung metadata, batching, retry và chuyển tiếp.
- Backend đặt retention, phân quyền tìm kiếm, truy vấn và alert.

Đừng mặc định vì kubectl logs đang hiển thị nên dữ liệu đã được thu thập tập trung, hay mọi log chắc chắn sẽ còn sau một lần crash.

## 10. Multi-line, JSON, trace context và thời gian

### 10.1. Một sự kiện có nhiều dòng

Stack trace Java tự nhiên có nhiều dòng:

~~~text
ERROR failed to process order
java.lang.IllegalStateException: invalid state
    at example.OrderService.process(OrderService.java:42)
    at example.App.main(App.java:10)
~~~

Các dòng ở đây là minh họa. Trong logging pipeline, một log record nhiều dòng có thể bị runtime/collector xem như nhiều log line riêng biệt nếu không có cách ghép. Hãy dùng formatter/encoder và cấu hình collector có thể bảo toàn event; nhiều hệ thống hỗ trợ structured JSON chứa thông điệp/exception dưới dạng một field đã escape newline. Không giải quyết bằng cách loại bỏ stack trace khỏi mọi lỗi.

### 10.2. Thông tin tương quan (correlation)

Nên có các trường nhất quán, chẳng hạn:

~~~text
service.name=orders
environment=prod
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
span_id=00f067aa0ba902b7
request_id=req-42
~~~

Trace ID và span ID phải xuất phát từ tracing context hợp lệ; không gán chuỗi bất kỳ rồi khẳng định đó là distributed tracing. Với thread pool, CompletableFuture hoặc reactive framework, cần có cơ chế context propagation và cleanup tương ứng. MDC/ThreadLocal có thể giúp gắn ID vào log nhưng **không tự lan qua network hay thread bất đồng bộ**.

Thông tin pod/node/namespace có thể được collector bổ sung từ Kubernetes metadata; ứng dụng không nhất thiết phải hard-code tên Pod trong từng log line. Dùng service.name và environment để query nhất quán qua nhiều replica.

### 10.3. Timestamp

Ưu tiên thời gian có múi giờ rõ ràng. Timestamp do application event, runtime và collector ghi có thể khác nhau vì buffering, network delay hoặc lệch đồng hồ giữa node. Đừng suy diễn quan hệ nhân quả chính xác chỉ bằng thứ tự các dòng hiển thị trên backend. Phân tích distributed tracing dùng span relationship và correlation ID phù hợp.

## 11. Shutdown, reload cấu hình và hiệu năng

### 11.1. Graceful shutdown

Khi Kubernetes dừng Pod hoặc Docker dừng container, process thường nhận tín hiệu dừng (theo cấu hình runtime) trước khi bị cưỡng bức nếu quá thời hạn grace period. Với Java, nên:

- Để JVM nhận tín hiệu đúng cách (ENTRYPOINT dạng exec hoặc entrypoint có forward signal).
- Dừng nhận tác vụ mới và hoàn tất những công việc có thể hoàn tất trong grace period.
- Flush/close async logging appender theo vòng đời backend, tránh mất log còn trong queue.
- Theo dõi timeout, exception và tình huống bị kill để hiểu giới hạn bảo đảm của log.

**Không nhầm logger.info() trả về với việc log đã đến backend tập trung.** Với async appender hoặc network sink, event có thể đang nằm trong buffer. Một kill cưỡng bức, crash hoặc node failure có thể làm mất event chưa chuyển tiếp.

### 11.2. Reload logging configuration

Các nguồn cấu hình có vòng đời khác nhau:

| Nguồn | Khi thay đổi | Hệ quả thường gặp |
| --- | --- | --- |
| ENV trong Docker/Kubernetes Pod | Khi tạo container/Pod mới | Process hiện tại không nhận giá trị env mới |
| File được mount từ ConfigMap volume | Sau một khoảng trễ của kubelet | File có thể cập nhật, nhưng app chỉ đổi behavior nếu thực sự re-read/reload |
| Cấu hình nằm trong image | Sau rebuild image/deploy phiên bản mới | Container cũ không tự đổi file |
| logging level được update qua API quản trị | Trong runtime nếu framework hỗ trợ | Có thể đổi level ngay, cần kiểm soát quyền và vòng đời |
| Collector/backend settings | Sau khi pipeline được cập nhật | Có thể đổi filter/parse/retention mà không đổi code Java |

Một thay đổi cấu hình log có thể ảnh hưởng tải CPU, I/O, lưu trữ và chi phí. Bật DEBUG/TRACE cho toàn bộ production mà không có giới hạn thời gian hoặc filter có thể tạo lượng dữ liệu rất lớn. Khi cần debug một sự cố, chỉ bật đúng logger/package và tắt sau khi đã thu được thông tin.

### 11.3. Hiệu năng và backpressure

- Parameterized logging có thể giảm chi phí dựng chuỗi khi level bị vô hiệu, nhưng không làm phép đọc trạng thái dùng chung trở nên thread-safe.
- Logging đồng bộ tới console có thể block khi downstream chậm. Async logging có queue riêng, cần chính sách khi đầy và shutdown flush.
- Container runtime cũng có buffer và driver; collector có thêm retry/batch. Phải đo tổng đường đi, không chỉ benchmark riêng lời gọi logger.
- Đặt quota và retention ở tầng lưu trữ phù hợp; theo dõi drop rate, queue depth, stdout/stderr throughput và disk pressure trên node.

## 12. Security và vận hành production

### 12.1. Không ghi bí mật vào log

Không log access token, password, private key, cookie session, dữ liệu thanh toán hoặc cả request body chứa thông tin nhạy cảm. ConfigMap không dành cho bí mật; nếu dùng Kubernetes Secret thì cũng **không** suy ra nội dung Secret an toàn để ghi vào log. Biến môi trường có thể bị lộ qua diagnostic dump hoặc command output; bảo vệ quyền đọc cấu hình và tránh in toàn bộ System.getenv().

### 12.2. User không phải root và root filesystem chỉ đọc

Container thường chạy với non-root user và có thể đặt readOnlyRootFilesystem: true. Ghi stdout/stderr không cần thư mục log writable trong image. Nếu appender cố ghi /var/log/app.log hoặc logback.xml trỏ tới một path không có quyền, log file có thể không tạo được; điều này là lỗi đường dẫn/quyền ghi, không phải lỗi logging level.

Nếu bắt buộc ghi file, phải mount volume phù hợp, cấp quyền cho UID của process, quản lý rotation/retention và xác định cách collector đọc file. Trong môi trường nhiều replica, tránh chia một file log giữa nhiều JVM và coi đó là một stream được bảo đảm thứ tự.

### 12.3. Cấu hình phân cấp rõ ràng

Một thứ tự thiết kế dễ vận hành:

1. Image chứa default cấu hình an toàn (INFO, console output).
2. Deploy platform truyền env cho giá trị cần khác nhau theo môi trường.
3. ConfigMap mount file XML/.properties khi cần cấu hình appender/format phức tạp.
4. Runtime/kubelet quản lý log cục bộ; collector gửi log tới backend.
5. Chính sách retention và quyền truy cập log đặt ở backend/cluster theo yêu cầu hệ thống.

Đây là cách phân chia trách nhiệm, không phải một thứ tự override cứng áp dụng cho mọi logging framework. Logback, Log4j 2, JUL và Spring Boot có cơ chế chọn file/property khác nhau; luôn dựa vào backend thực tế để xác định ưu tiên.

## 13. Troubleshooting: lỗi điển hình trong container

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| docker logs không thấy log dù /app/logs có file | App ghi file trong filesystem container | Chuyển sang ConsoleAppender/ConsoleHandler, hoặc thiết lập forwarder/collector cho file |
| kubectl logs trống | Pod chưa chạy, container sai, log chỉ ghi file, logging level chặn, driver không có dữ liệu | Kiểm tra get pod, describe, container -c, log level và sink |
| Đã sửa ConfigMap nhưng level không đổi | ENV không tự cập nhật, app chỉ đọc file khi startup, dùng subPath | Tạo Pod mới/rollout, kiểm tra reload thực sự được hỗ trợ |
| INFO xuất hiện ở stderr | JUL ConsoleHandler mặc định dùng stderr | Hiểu stream của handler; vẫn có thể thu thập qua Docker/Kubernetes |
| Bị thiếu log cũ | Container/Pod bị xóa, log rotate, node mất, không có backend tập trung | Kiểm tra node retention/collector; xây cluster-level logging |
| Node đầy ổ đĩa | json-file không giới hạn, appender file tự ghi, quá nhiều DEBUG | Bật rotation, hạ level, theo dõi disk/retention |
| Log bị cắt thành nhiều record | Stack trace nhiều dòng, collector parse sai | Dùng JSON encoder/ multiline parser có cấu hình rõ |
| Lẫn trace/request ID giữa task | Không propagate/clear MDC đúng khi dùng thread pool | Chụp và phục hồi context đúng scope; dùng instrumentation phù hợp |
| Chạy được trên máy local nhưng fail trong container | File cấu hình không nằm runtime classpath, case-sensitive, đường dẫn hoặc quyền sai | Kiểm tra image contents/working directory, config path và quyền file |
| Log tăng chi phí đột biến sau deploy | DEBUG/TRACE, request payload lớn, high-cardinality fields | Giới hạn mức log, lọc dữ liệu, đo throughput và chi phí |
| Log biến mất khi dừng Pod | Async buffer chưa flush hoặc kill quá nhanh | Cấu hình graceful shutdown và thời gian flush phù hợp |

### Trình tự kiểm tra gợi ý

1. Đọc log ở **lớp gần ứng dụng nhất**: log có thực sự được phát ra stdout/stderr không?
2. Xác định backend/config file nào đang active (JUL, Logback, Log4j 2, Spring Boot).
3. Với Docker: kiểm tra docker logs, docker inspect logging driver và max-size/max-file.
4. Với Kubernetes: kiểm tra Pod, container name, events, kubectl logs và --previous khi có restart.
5. Nếu container có log nhưng backend tập trung không có: kiểm tra collector, parsing, quota/queue, network, credential và lỗi gửi.
6. Nếu log thiếu trong giai đoạn shutdown: kiểm tra vòng đời process, grace period và flush.
7. Xác nhận lại trong môi trường test có cấu hình giống production, tránh bật DEBUG hàng loạt trên cluster đang phục vụ người dùng.

## 14. Bài tập thực hành

### Bài 1: So sánh environment

Build Docker image ở mục 5, chạy lần lượt với APP_LOG_LEVEL=INFO và FINE. Ghi nhận số lượng và thứ tự sự kiện; giải thích vì sao cùng image có output khác nhau khi tạo container mới.

### Bài 2: Rotation

Chạy image với Docker driver local và giới hạn max-size/max-file. Tăng số lượng log trong bản demo riêng tại môi trường thử nghiệm rồi kiểm tra cấu hình docker inspect. So sánh với driver json-file được giới hạn rõ và phân biệt dung lượng lưu của Docker với file ứng dụng tự ghi.

### Bài 3: Kubernetes ConfigMap

Dùng Job và ConfigMap ở mục 7. Chạy với APP_ENV=staging, sau đó đổi ConfigMap thành prod. Giải thích vì sao Job đã hoàn thành không tự đổi giá trị và cách tạo lần chạy mới để kiểm tra cấu hình mới.

### Bài 4: File cấu hình Logback

Ở một ứng dụng Spring Boot dùng Logback thực tế, mount một file logback-spring.xml từ ConfigMap, đặt LOGGING_CONFIG trỏ tới file và quan sát log console. Sau khi cập nhật ConfigMap, xác nhận file mount được cập nhật, rồi thử rolling restart. So sánh hành vi giữa “file thay đổi” và “logging framework đổi level”.

### Bài 5: Điều tra log bị mất

Giả sử service bị restart nhiều lần và chỉ còn log gần nhất trong kubectl logs. Vẽ lại các lớp appender → runtime → kubelet → collector → backend, đánh dấu nơi có thể giữ hoặc mất dữ liệu. Đề xuất monitoring cho queue, dropped logs và retention phù hợp.

## 15. Ghi nhớ

**Container configuration cho Java Logging** là sự phối hợp giữa cấu hình ứng dụng, container runtime và hạ tầng thu thập. Với service thông thường, bắt đầu bằng console logging tới stdout/stderr, cấu hình level bằng env hoặc file mount, giới hạn log cục bộ qua Docker/kubelet, và sử dụng collector/backend tập trung khi cần lịch sử bền vững. Luôn kiểm tra việc ứng dụng thật sự đọc/reload cấu hình, đặc biệt khi ConfigMap thay đổi. Một dòng log xuất hiện trong docker logs hoặc kubectl logs chưa chứng minh đã được lưu lâu dài.

### Tài liệu tham khảo chính thức

- Kubernetes – Logging Architecture: https://kubernetes.io/docs/concepts/cluster-administration/logging/
- Kubernetes – ConfigMaps: https://kubernetes.io/docs/concepts/configuration/configmap/
- Kubernetes – Configure a Pod to Use a ConfigMap: https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/
- Kubernetes – Updating Configuration via a ConfigMap: https://kubernetes.io/docs/tutorials/configuration/updating-configuration-via-a-configmap/
- Docker – Configure Logging Drivers: https://docs.docker.com/engine/logging/configure/
- Docker – Local File Logging Driver: https://docs.docker.com/engine/logging/drivers/local/
- Docker – JSON File Logging Driver: https://docs.docker.com/engine/logging/drivers/json-file/
- Docker – Multi-stage Builds: https://docs.docker.com/get-started/docker-concepts/building-images/multi-stage-builds/
- Oracle JDK 17 – ConsoleHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- Oracle JDK 17 – LogManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- Spring Boot – Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Logback – Configuration: https://logback.qos.ch/manual/configuration.html
- Apache Log4j 2 – Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
