# Bảo vệ cấu hình logger trong Java: quyền thay đổi, tính toàn vẹn và kiểm soát vận hành

## 1. Tại sao cấu hình logger là tài sản cần bảo vệ?

**Cấu hình logger** không chỉ quyết định mức INFO, DEBUG hay ERROR. Trong các backend Java như Logback và Log4j 2, cấu hình còn chọn appender, đường dẫn file, địa chỉ gửi log, filter, định dạng, xử lý bất đồng bộ, cách nạp lại và nhiều thuộc tính của đường xuất dữ liệu.

Nếu một người không có quyền có thể thay đổi cấu hình đó, họ có thể:

- Đặt logger audit hoặc bảo mật thành OFF để che giấu hoạt động.
- Bật TRACE/DEBUG diện rộng, làm lộ thông tin nhạy cảm vốn không được phép xuất hoặc gây quá tải CPU, disk và collector.
- Đổi đích appender sang file hoặc máy chủ không đáng tin cậy, làm rò rỉ log.
- Thêm filter loại sự kiện ERROR, truy cập bị từ chối hoặc audit quan trọng.
- Chỉnh retention, rolling hoặc đường dẫn file, làm mất chứng cứ hoặc ghi log vào nơi có quyền truy cập không phù hợp.
- Nạp cấu hình từ nguồn chưa tin cậy; với một số backend, cấu hình có thể khai báo plugin hoặc lớp Java cần khởi tạo.
- Bật tính năng reload hoặc endpoint quản trị không có kiểm soát, khiến thay đổi có hiệu lực trong lúc ứng dụng chạy.

**Bảo vệ cấu hình logger** nghĩa là chỉ cho phép nguồn tin cậy định nghĩa cấu hình, chỉ người được ủy quyền mới được sửa, có khả năng phát hiện sai lệch và phục hồi một cấu hình an toàn. Phạm vi bảo vệ bao gồm cả **file cấu hình, nguồn tham số, cơ chế thay đổi ở runtime và cấu hình hạ tầng đích nhận log**.

Không nên coi logger như công cụ kiểm soát quyền truy cập vào nghiệp vụ: việc tắt log không làm hành động bị cấm trở thành hợp lệ. Logger là một phần của khả năng quan sát và chứng cứ, cần được bảo vệ bổ sung bằng xác thực, phân quyền, kiểm toán và cơ chế lưu trữ độc lập.

## 2. Những nguồn nào có thể ảnh hưởng tới cấu hình logging?

Một ứng dụng không nhất thiết chỉ đọc một file logback.xml. Cấu hình hiệu lực có thể đến từ nhiều nơi:

| Nguồn | Ví dụ | Rủi ro cần đánh giá |
| --- | --- | --- |
| Artifact/classpath | logback.xml, logback-spring.xml, log4j2.xml trong JAR | Build bị thay, dependency hoặc artifact không đáng tin |
| File ngoài ứng dụng | /etc/my-service/logback.xml | Quyền ghi rộng, volume bị thay, symlink ngoài ý muốn |
| JVM system property | logback.configurationFile, log4j2.configurationFile | Tham số khởi động bị thay hoặc trỏ sang nguồn khác |
| Environment/config server | LOGGING_LEVEL_ROOT, cấu hình môi trường, properties | Người sửa cấu hình triển khai có thể thay đổi verbosity hoặc đích |
| HTTP/JMX/Actuator | Spring Boot Actuator loggers, quản trị JMX | Endpoint bị lộ, quyền thay đổi không chặt |
| API trong tiến trình | Logger.setLevel(...), LoggerContext | Một đoạn code hoặc plugin có quyền thay đổi runtime |
| Cơ chế reload | Logback scan, Log4j 2 monitorInterval | File/nguồn thay đổi sau khi ứng dụng đã khởi chạy |

Một số cơ chế chỉ thay đổi **level**, trong khi file backend có thể thay đổi **appender, filter, plugin và đích xuất**. Vì vậy việc bảo vệ mức DEBUG không thể thay thế việc bảo vệ file cấu hình đầy đủ.

Cần xác định **nguồn cấu hình đang được nạp thực sự** cho từng môi trường và instance. Một file được kiểm soát tốt trong source repository sẽ không có tác dụng nếu tiến trình đang đọc một file khác qua tham số JVM hoặc một nguồn cấu hình runtime được ưu tiên cao hơn.

## 3. Mô hình đe dọa và ranh giới tin cậy

Xét hệ thống:

~~~text
Developer / CI / CD / Operator
             |
             v
     Configuration artifact
             |
       [approval, checksum]
             |
             v
   Deployment / runtime config
             |
             v
      Logger + appender
             |
             v
  Application logs / audit logs
             |
             v
      Collector / storage
~~~

Các ranh giới cần bảo vệ gồm:

1. **Tạo và review:** ai được sửa source cấu hình, workflow nào chấp nhận thay đổi?
2. **Phát hành:** bản cấu hình nào được đóng gói, ký/kiểm tra, triển khai vào đâu?
3. **Quyền ở runtime:** tài khoản chạy JVM có được **đọc** cấu hình nhưng không được **sửa** không?
4. **Đổi động:** ai được gọi API thay đổi logger, ở phạm vi nào, trong bao lâu?
5. **Đường xuất:** ai có quyền sửa đường dẫn/file appender, tài khoản/đích collector, filter và retention?
6. **Phát hiện và khôi phục:** có biết cấu hình bị đổi, ai đổi, đã có ảnh hưởng gì và có cách quay về bản an toàn không?

Không thể coi kiểm soát quyền của filesystem là đủ nếu một người có quyền triển khai container hoặc cập nhật ConfigMap có thể thay toàn bộ file. Tương tự, một endpoint quản trị được bảo vệ tốt không giải quyết được một dependency độc hại có khả năng can thiệp trực tiếp vào LoggerContext trong cùng JVM. Cần dùng nhiều lớp bảo vệ.

## 4. Phân loại thao tác và quyền được cấp

Chọn nguyên tắc **least privilege**: người chỉ cần xem log không cần quyền sửa logger level; người được bật DEBUG để điều tra không tự động có quyền thay đổi audit sink hoặc tắt logging bảo mật.

Một bảng phân quyền gợi ý:

| Thao tác | Quyền khuyến nghị |
| --- | --- |
| Xem effective level của logger thông thường | Quyền đọc có xác thực, giới hạn thông tin |
| Thay level package chẩn đoán từ INFO sang DEBUG | Vai trò vận hành được ủy quyền, có phạm vi và thời hạn |
| Thay ROOT=TRACE/DEBUG | Quyền cao hơn, xét nguy cơ log flood và dữ liệu nhạy cảm |
| Đặt audit.events=OFF hoặc xóa audit appender | Từ chối theo policy, trừ quy trình bảo trì được phê duyệt đặc biệt |
| Đổi nơi nhận log/endpoint của appender | Quy trình change management và xét duyệt bảo mật |
| Đổi redaction, filter hoặc retention audit | Quy trình chặt chẽ, độc lập với quyền xem log |
| Đọc/ghi file cấu hình production | Đọc cho runtime; ghi chỉ trong đường triển khai đáng tin cậy |

Nên xác thực và phân quyền bằng **identity của người/tiến trình đã xác thực**, không nhận một chuỗi role từ tham số HTTP rồi tự tin đó là quyền thật. Một yêu cầu đổi mức log cần có lý do, người duyệt nếu phù hợp, phạm vi logger, mức được phép, thời điểm hết hạn và dấu vết kiểm toán.

Đối với sự kiện audit bắt buộc, ưu tiên **cơ chế ghi nhận bền vững riêng** thay vì trông chờ logger level. Một người có thể tắt appender hoặc backend gặp sự cố; hệ thống vẫn cần phát hiện được tình huống đó.

## 5. Ví dụ Java 17+ chạy độc lập: chặn thay đổi level ngoài chính sách

Ví dụ dùng **java.util.logging (JUL)** có sẵn trong JDK để minh họa **danh sách logger cho phép** và **danh sách level cho phép**. Mã không xây một HTTP endpoint; các giá trị role được truyền trực tiếp trong ví dụ **chỉ để kiểm chứng điều kiện**, không đại diện cơ chế xác thực production.

Tạo file **GuardedLoggerConfigDemo.java**:

~~~java
import java.util.Map;
import java.util.logging.Level;
import java.util.logging.Logger;

public class GuardedLoggerConfigDemo {
    private static final Logger PAYMENT =
            Logger.getLogger("com.example.payment");

    // Giữ reference và chỉ cho phép sửa logger được chỉ định.
    private static final Map<String, Logger> EDITABLE =
            Map.of("com.example.payment", PAYMENT);

    // Không nhận DEBUG/FINE, ALL hay OFF trong ví dụ.
    private static final Map<String, Level> SAFE_LEVELS =
            Map.of("INFO", Level.INFO,
                   "WARNING", Level.WARNING,
                   "SEVERE", Level.SEVERE);

    static boolean changeLevel(String role, String name, String wanted) {
        if (!"LOG_ADMIN".equals(role)) {
            return false;
        }
        Logger target = EDITABLE.get(name);
        Level level = SAFE_LEVELS.get(wanted);
        if (target == null || level == null) {
            return false;
        }
        target.setLevel(level);
        return true;
    }

    public static void main(String[] args) {
        System.out.println("guest-change=" +
                changeLevel("VIEWER", "com.example.payment", "WARNING"));
        System.out.println("debug-change=" +
                changeLevel("LOG_ADMIN", "com.example.payment", "FINE"));
        System.out.println("audit-off=" +
                changeLevel("LOG_ADMIN", "audit.events", "OFF"));
        System.out.println("allowed-change=" +
                changeLevel("LOG_ADMIN", "com.example.payment", "WARNING"));
        System.out.println("payment-level=" +
                PAYMENT.getLevel().getName());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac GuardedLoggerConfigDemo.java
java GuardedLoggerConfigDemo
~~~

Stdout xác định:

~~~text
guest-change=false
debug-change=false
audit-off=false
allowed-change=true
payment-level=WARNING
~~~

Các tình huống được kiểm tra:

- VIEWER không có quyền thay level.
- LOG_ADMIN không thể bật FINE (mức chẩn đoán của JUL gần với mục đích DEBUG ở nhiều backend) vì mức này không có trong SAFE_LEVELS.
- Logger audit.events không thuộc EDITABLE, vì vậy yêu cầu OFF bị chặn dù người gọi tự nhận là LOG_ADMIN.
- Yêu cầu WARNING hợp lệ cho com.example.payment được chấp nhận, sau đó đọc lại level là WARNING.

**Giới hạn quan trọng:** đây là ví dụ về validation/policy, **không phải cơ chế bảo mật đầy đủ**. Trong production, giá trị role phải lấy từ session/identity đã xác thực và được xác minh quyền ở tầng server; không để client tự khai báo. Cần ghi lại yêu cầu được cho phép và bị từ chối, lưu lý do thay đổi, giới hạn thời gian, rollback, xử lý exception và đồng bộ nhiều instance.

Hơn nữa, code khác trong cùng JVM có thể có tham chiếu Logger và gọi setLevel() trực tiếp; wrapper như ví dụ không ngăn được mọi thay đổi trong tiến trình. Vì thế còn cần **quản lý dependency, review code, bảo vệ endpoint và kiểm soát môi trường thực thi**. Không coi một hàm guard là sandbox an toàn cho code không đáng tin cậy.

## 6. Bảo vệ file cấu hình: quyền đọc, quyền ghi và đường dẫn

Đường triển khai an toàn thường có nguyên tắc:

- **Runtime chỉ cần đọc** file cấu hình; không để tài khoản chạy JVM tùy ý chỉnh sửa file.
- Chỉ pipeline triển khai hoặc vai trò vận hành được phép ghi, sau khi cấu hình đi qua review/test.
- Nếu cấu hình thay bằng artifact mới, kiểm tra nguồn và checksum/signature theo chuỗi cung ứng được sử dụng.
- Bảo vệ **thư mục cha, symlink, volume mount và tham số chọn đường dẫn**, không chỉ file đích.
- Giữ **nơi ghi log** riêng và có quyền ghi cần thiết; không đặt file cấu hình cùng thư mục ứng dụng có thể ghi tùy ý.
- Không đặt token/mật khẩu kết nối collector ở file được phát tán rộng; sử dụng cơ chế cấp secret phù hợp, giới hạn quyền đọc.

Ví dụ **Linux** cho một dịch vụ có group app, hệ thống triển khai có quyền root (đây là lệnh minh họa, không tự chạy trong ứng dụng):

~~~bash
# File cấu hình do root sở hữu, group app chỉ được đọc.
sudo install -o root -g app -m 0640 \
  ./logback.xml /etc/my-service/logback.xml

# Thư mục ghi log tách khỏi thư mục cấu hình.
sudo install -d -o app -g app -m 0750 /var/log/my-service

# Kiểm tra sau triển khai.
ls -l /etc/my-service/logback.xml
ls -ld /var/log/my-service
~~~

Ở đây group app cần tồn tại và service phải chạy dưới danh tính phù hợp. Muốn kiểm soát chắc chắn, còn phải xét quyền thư mục cha, ACL, quyền mount và khả năng quản trị máy. Nếu attacker có root trên host hoặc quyền cập nhật bản triển khai, chmod 0640 không tự bảo vệ toàn bộ hệ thống.

Trong container/Kubernetes, có thể dùng image/root filesystem không cho ghi khi phù hợp, mount cấu hình read-only và tách volume ghi log. Nhưng **ConfigMap được mount read-only trong pod vẫn có thể thay đổi qua Kubernetes API** nếu quyền RBAC cho phép; bảo vệ API, CI/CD và đối tượng triển khai mới là yêu cầu cốt lõi. Cần kiểm tra khả năng cập nhật cấu hình tự động/rollout theo cách dùng ConfigMap/Secret thực tế.

## 7. Logback: kiểm soát nguồn nạp và tự động reload

Logback Classic thường tìm cấu hình trên classpath, hoặc có thể nhận vị trí cấu hình từ **logback.configurationFile**. Khi dùng Spring Boot và Logback, thường gặp **logback-spring.xml** với cơ chế tích hợp Spring. Phải xác minh file nào được nạp và liệu thuộc tính JVM/ứng dụng có thể trỏ sang file khác.

Logback hỗ trợ quét và nạp lại khi có thay đổi nếu đặt **scan="true"**. Khi muốn các thay đổi chỉ có hiệu lực qua quy trình deploy đã phê duyệt, chọn **scan="false"** để tắt chính cơ chế quét tự động đó. Ví dụ **logback.xml**:

~~~xml
<configuration scan="false">
  <appender name="APP"
            class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="AUDIT"
            class="ch.qos.logback.core.FileAppender">
    <file>/var/log/my-service/audit.log</file>
    <append>true</append>
    <encoder>
      <pattern>%d{ISO8601} %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <logger name="audit.events" level="INFO"
          additivity="false">
    <appender-ref ref="AUDIT"/>
  </logger>

  <root level="INFO">
    <appender-ref ref="APP"/>
  </root>
</configuration>
~~~

Ví dụ này có hai appender để thể hiện rằng **thay cấu hình có thể ảnh hưởng cả đường audit**. Logger audit.events được gắn AUDIT, additivity=false để không chuyển lên APP của ROOT. Thư mục ghi audit phải tồn tại, được phân quyền phù hợp và cần chính sách lưu bền vững, rotation và giám sát lỗi riêng.

**scan="false" chỉ tắt quét cấu hình tự động của Logback**; nó không khóa toàn bộ API cấu hình, JMX, Actuator hay một đoạn code có khả năng chỉnh LoggerContext. Cũng không bảo đảm sự kiện audit được ghi bền vững khi file I/O lỗi, process crash hoặc đĩa đầy.

Nếu thực sự cần hot reload, hãy bảo vệ nguồn file, giới hạn quyền sửa, xác minh bản mới, có cảnh báo thay đổi, ghi nhận người phê duyệt và có quy trình rollback. Không bật scan chỉ để sửa sự cố dễ hơn nếu đội vận hành chưa kiểm soát được nguồn cấu hình.

## 8. Log4j 2: kiểm soát nguồn, plugin và monitorInterval

Log4j 2 Core có thể nạp **log4j2.xml** từ classpath hoặc từ đường dẫn/URI do **log4j2.configurationFile** chỉ định. Cấu hình có thể khai báo appender, filter, layout và các plugin khác, nên phải coi **nội dung file cấu hình là nguồn tin cậy cần được kiểm soát**, không lấy từ một URL hoặc input do người dùng tự cung cấp.

Trong Log4j 2.x, thuộc tính **monitorInterval="0"** tắt cơ chế polling thay đổi file cấu hình. Ví dụ **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration monitorInterval="0" status="WARN">
  <Appenders>
    <Console name="APP" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
    </Console>

    <File name="AUDIT" fileName="/var/log/my-service/audit.log"
          append="true">
      <PatternLayout pattern="%d{ISO8601} %c - %m%n"/>
    </File>
  </Appenders>

  <Loggers>
    <Logger name="audit.events" level="info" additivity="false">
      <AppenderRef ref="AUDIT"/>
    </Logger>

    <Root level="info">
      <AppenderRef ref="APP"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Các điểm cần kiểm soát:

- **Không cho người dùng chọn tùy ý log4j2.configurationFile** qua request, tham số chạy hoặc cấu hình được đưa từ bên ngoài quy trình triển khai.
- Nếu phải dùng cấu hình từ xa, kiểm tra nguồn tin cậy, kênh TLS, quyền thay đổi, việc xác minh nội dung và cơ chế pinning/phát hành phù hợp. HTTPS chỉ bảo vệ đường truyền theo điều kiện tin cậy của TLS, không chứng minh file do người có quyền tạo.
- Kiểm tra chính sách protocol khi tải cấu hình. Log4j 2.x có thuộc tính **log4j2.configurationAllowedProtocols** để giới hạn giao thức cho một số nguồn URL; không mặc định rằng mọi protocol đều an toàn.
- Tránh cho phép các plugin/class tùy biến không được review vào classpath. Một cấu hình đáng tin vẫn có thể phụ thuộc vào plugin không an toàn.
- Giữ **monitorInterval=0** khi yêu cầu chỉ nhận thay đổi qua redeploy; đây không phải biện pháp ngăn API runtime khác thay đổi context.
- Kiểm thử logger audit, appender reference và filter sau mỗi lần thay cấu hình.

**Lưu ý phiên bản:** tên property, hỗ trợ giao thức và hành vi nạp lại có thể khác giữa Log4j 2.x và các major release khác. Không sao chép cấu hình từ Log4j 1 hoặc Log4j 3 như thể hoàn toàn tương đương; đối chiếu tài liệu đúng phiên bản đang dùng.

## 9. Spring Boot: bảo vệ endpoint thay đổi logger level

Spring Boot Actuator có endpoint **loggers**, cho phép xem **configured level** và **effective level**, đồng thời có khả năng đổi level ở runtime khi quyền truy cập cho phép. Một lời gọi POST có thể đổi level mà **không sửa file logback.xml/log4j2.xml**.

Đây là đường quản trị cần kiểm soát:

- Không tự động công khai /actuator/loggers trên mạng công cộng.
- Chỉ expose endpoint cần thiết; phân biệt **exposure** (HTTP/JMX có đường truy cập hay không) với **access** (quyền đọc/ghi được phép).
- Dùng xác thực mạnh, vai trò quản trị, network controls, HTTPS và kiểm toán yêu cầu đổi level.
- Nếu ứng dụng tự định nghĩa SecurityFilterChain, kiểm tra chính xác các quy tắc bảo vệ Actuator; không giả định Spring Boot vẫn tự bảo vệ mọi endpoint như khi không có custom chain.
- Giữ CSRF protection theo mô hình client; đừng vô hiệu toàn bộ chỉ để POST đổi mức log dễ hơn.
- Khi dùng nhiều replica, thay đổi runtime ở một instance có thể không áp dụng cho các instance khác; cần kiểm tra trạng thái thực tế và hoàn nguyên.

**Ví dụ Spring Boot 3.5+ hoặc phiên bản có thuộc tính endpoint access tương ứng**, chỉ cho phép mức *read-only* ở endpoint loggers và chỉ expose health/loggers theo policy (file application.properties):

~~~properties
management.endpoints.access.default=none
management.endpoint.health.access=read-only
management.endpoint.loggers.access=read-only
management.endpoints.web.exposure.include=health,loggers
~~~

Đây là **cấu hình về phạm vi endpoint, chưa phải ví dụ đầy đủ về xác thực/phân quyền HTTP**. Cần thêm security chain và chính sách mạng phù hợp nếu cho phép truy cập. Nếu không cần xem level qua HTTP, có thể không expose loggers. Với phiên bản Spring Boot cũ có thể chưa hỗ trợ thuộc tính **management.endpoint.loggers.access**; kiểm tra reference đúng phiên bản thay vì kết luận cấu hình đã chặn POST khi thuộc tính không được nhận.

**Read-only** là lựa chọn an toàn hơn việc cho POST đổi level tự do khi đội vận hành chỉ cần xem cấu hình. Nếu tổ chức thực sự cần đổi động, nên dùng công cụ quản trị có phê duyệt, TTL, audit trail, giới hạn logger name/level và phân quyền riêng; không phát tán hướng dẫn thay level qua API công khai.

## 10. Bảo vệ biến môi trường, profile và nguồn cấu hình ngoài

Một số hệ thống thiết lập level qua application.properties/YAML, environment hoặc JVM startup arguments. Ví dụ ở Spring Boot:

~~~properties
logging.level.root=INFO
logging.level.com.example.payment=INFO
logging.level.audit.events=INFO
~~~

Các dòng trên chỉ đặt **level**. Chúng không tự bảo vệ file appender, disable quyền runtime hoặc đảm bảo audit delivery.

Rủi ro không chỉ ở file: người có quyền sửa manifest, Helm values, deployment variables, secret, config server hoặc tham số khởi động có thể thay cấu hình hiệu lực. Vì vậy:

- Giới hạn ai được sửa configuration repository/Helm release/ConfigMap hoặc tham số CI/CD.
- Có review, approval, validation và dấu vết phiên bản của các thay đổi.
- Tránh cấu hình level từ dữ liệu HTTP request, query parameter hoặc header.
- Xác minh precedence giữa các nguồn cấu hình và profile; có thể một biến môi trường ghi đè file mặc định.
- Chỉ cho phép đường dẫn/file/endpoint từ danh sách tin cậy; không nối đường dẫn log từ input không kiểm soát.
- Giám sát cấu hình được áp dụng trên từng instance sau deploy, thay vì chỉ xem file trong source code.

Không đưa bí mật như mật khẩu kết nối remote appender trực tiếp vào application.properties công khai nếu có lựa chọn secret manager/credential store phù hợp. Khi báo lỗi cấu hình, không in nguyên thông tin xác thực ra console hoặc log chẩn đoán.

## 11. Bảo vệ audit logger và chính sách redaction

Hai phần đặc biệt nhạy cảm của logging configuration là:

1. **Audit/security logging:** có thể chứa chứng cứ về hành động truy cập, thay quyền và sự kiện bị từ chối.
2. **Masking/redaction:** ngăn secret, token hoặc dữ liệu nhạy cảm bị xuất ra các appender.

Nếu người không đủ quyền đổi **audit.events=OFF**, xóa appender audit hoặc chuyển additivity/filter, hệ thống có thể ngừng tạo chứng cứ dù nghiệp vụ vẫn chạy. Tương tự, việc gỡ một redaction filter có thể làm lộ thông tin vào nhiều kho log.

Đề xuất bảo vệ:

- Tách policy của audit/redaction khỏi quyền đổi level chẩn đoán thông thường.
- Có test chặn thay đổi trái phép; đặt ngưỡng cảnh báo khi event audit đột ngột biến mất hoặc routing thay đổi.
- Không dựa duy nhất vào logger và queue RAM cho dữ liệu kiểm toán bắt buộc: cân nhắc **transactional outbox**, durable broker hoặc audit store chuyên dụng có ACK, retry và dedup.
- Không tin redaction filter là cơ chế bảo vệ duy nhất: tốt nhất **không đưa secret vào LogEvent ngay từ đầu**.
- Phân quyền nơi lưu audit riêng, quản lý retention và tính toàn vẹn; tránh để quyền sửa logger đồng thời là quyền xóa bằng chứng.

Đừng dùng một chỉ số “ERROR logs/s bằng 0” làm bằng chứng hệ thống an toàn: logger hoặc filter bị đổi cũng có thể khiến số đó về 0. Cần metric/health kiểm tra độc lập và đối chiếu với số nghiệp vụ cần audit.

## 12. Quy trình thay đổi cấu hình logger an toàn

Một thay đổi level tạm thời để điều tra sự cố nên có chu trình rõ ràng:

1. **Yêu cầu:** mô tả vì sao cần đổi, tác động dự kiến, logger name, level trước/sau, phạm vi instance/environment.
2. **Đánh giá:** liệu bật DEBUG/TRACE có lộ payload, credential, PII hoặc gây quá tải disk/collector không?
3. **Phê duyệt:** kiểm tra role của người thực hiện; dùng nguyên tắc tách quyền khi ảnh hưởng tới audit/redaction hoặc toàn hệ thống.
4. **Triển khai:** qua cấu hình bất biến/CI-CD hoặc kênh quản trị đã bảo vệ. Nếu thay runtime, ghi nhận giá trị hiện tại để rollback.
5. **Xác minh:** đọc lại effective level, appender/filter/routing và metric log volume trên từng instance liên quan.
6. **Theo dõi:** quan sát CPU, latency, drop, queue backlog, collector, dung lượng disk và thông tin nhạy cảm.
7. **Hết hạn:** tự động hoặc theo quy trình hoàn nguyên về policy nền sau thời hạn đã duyệt.
8. **Kiểm toán:** lưu ai đổi, lúc nào, trên service/instance nào, giá trị cũ/mới, ticket/lý do và kết quả rollback.

Nếu đổi trong tình huống khẩn cấp, vẫn cần một quy trình rút gọn có log quyết định; tránh sửa trực tiếp file trên server rồi bỏ qua việc đồng bộ ngược vào nguồn cấu hình. Thay đổi tạm ở một pod cũng có thể mất sau restart, khiến trạng thái giữa các replica không thống nhất.

## 13. Giám sát sai lệch và phát hiện cấu hình bị thay đổi

Không phải mọi thay đổi đều diễn ra bằng PR. Có thể do operator, hệ thống cấu hình động, plugin hoặc quyền truy cập bị lạm dụng. Nên có phép kiểm độc lập:

| Tín hiệu | Tác dụng |
| --- | --- |
| Cấu hình version/hash trong lúc deploy và runtime | Phát hiện bản đang chạy khác bản đã phê duyệt |
| Effective levels của ROOT và logger bảo mật | Phát hiện TRACE/DEBUG/OFF bất thường |
| Danh sách appender/đích, additivity, filter | Phát hiện route thay đổi hoặc mất appender audit |
| Audit trail thao tác config/Actuator/JMX | Biết ai đã sửa, tại sao và khi nào |
| Log volume, entropy của message, disk/network bytes | Phát hiện bùng nổ log hoặc chuyển hướng bất thường |
| Audit delivery heartbeat, backlog/ACK, lỗi appender | Nhận biết pipeline không còn lưu sự kiện |
| Cấu hình giữa các replica | Phát hiện drift giữa các instance |

**Hash file cấu hình không đủ** nếu có thể đổi level qua API runtime mà file vẫn giữ nguyên. Phải đo cả **trạng thái logger đang có hiệu lực** và các đường xuất thực tế. Ngược lại, hash khác chưa chắc là tấn công nếu có deploy hợp lệ; đối chiếu với lịch sử triển khai đã duyệt.

Không ghi toàn bộ nội dung cấu hình hoặc secret vào hệ thống cảnh báo. Có thể log metadata an toàn: config version, hash, logger name, giá trị level trước/sau, người đổi và nguồn thay đổi.

## 14. Kiểm thử bảo mật cho cấu hình logger

Lập ma trận kiểm thử theo **quyền, nguồn cấu hình, runtime và đường xuất**:

| Ca kiểm thử | Hành động | Kỳ vọng |
| --- | --- | --- |
| Không xác thực | Gửi yêu cầu đổi level qua endpoint | Từ chối, không thay effective level |
| Chỉ có quyền đọc | POST đổi INFO thành DEBUG | Từ chối, không thay hiệu lực |
| Quyền có giới hạn | Thay đúng logger/level trong allowlist | Chấp nhận, có audit và thời hạn |
| Quyền có giới hạn | Đặt audit.events=OFF | Từ chối theo policy |
| Input không hợp lệ | Chọn tên logger/path tùy ý hoặc level ngoài danh sách | Từ chối có kiểm soát |
| File không đáng tin | Thay logback.xml/log4j2.xml từ tài khoản chạy ứng dụng | Bị hệ điều hành hoặc đường triển khai ngăn |
| Reload ngoài kế hoạch | Chỉnh file khi không cho phép hot reload | Không thay runtime; có phát hiện drift nếu file bị sửa |
| Đổi appender/filter | Chuyển audit sang sink không được phép | Bị review/policy chặn hoặc phát hiện |
| Đổi nhiều replica | Chỉ cập nhật một instance | Công cụ kiểm tra cảnh báo cấu hình không đồng nhất |
| Hết hạn debug | Sau TTL/quy trình rollback | Level trở lại ngưỡng được phê duyệt |
| Sink lỗi | Disk full, collector timeout, queue đầy | Cảnh báo độc lập; policy mất log được kiểm tra |
| Khôi phục | Triển khai bản cấu hình đã duyệt trước | Routing, filter, effective level trở lại đúng trạng thái |

Với Spring Boot Actuator, hãy thử cả **HTTP và JMX nếu JMX được bật/expose**. Xem xét proxy/ingress, firewall, xác thực và CSRF cho các thao tác thay đổi trạng thái. Không dùng test thay level ROOT=OFF trên production thật để “chứng minh” quyền: có thể khiến mất dấu vết trong quá trình thử.

Với file configuration, kiểm tra quyền người dùng thực tế của process chứ không chỉ tài khoản đăng nhập để chạy lệnh. Trong container, root filesystem/mount read-only không thay thế kiểm soát quyền cập nhật tài nguyên qua control plane.

## 15. Phản ứng khi phát hiện bị can thiệp

Khi phát hiện level/route thay đổi bất ngờ:

1. **Xác định phạm vi:** service, pod/instance, mốc thời gian, logger, appender/filter, nguồn và kênh thay đổi.
2. **Bảo toàn bằng chứng:** giữ bản cấu hình/version hiện tại, lịch sử deployment, request audit của endpoint quản trị, log collector và metadata an toàn; không xóa dấu vết khi sửa.
3. **Giới hạn quyền:** thu hồi hoặc khóa nguồn thay đổi trái phép, kiểm tra credential của operator/service account và quyền CI/CD.
4. **Khôi phục cấu hình đã duyệt:** redeploy từ artifact tin cậy hoặc rollback theo quy trình; xác minh hash và effective levels.
5. **Đánh giá ảnh hưởng:** đã có khoảng trống audit, DEBUG lộ dữ liệu, redirect tới sink lạ, disk đầy hoặc drop log hay không?
6. **Theo dõi sau phục hồi:** khôi phục event pipeline, kiểm tra đích ghi, cảnh báo và thống nhất cấu hình giữa các instance.
7. **Khắc phục nguyên nhân:** sửa quyền filesystem, RBAC, exposure endpoint, code thay runtime hoặc quy trình release; bổ sung kiểm thử và cảnh báo drift.

Nếu có nghi ngờ lộ token/secret do bật log quá chi tiết hoặc đổi đích nhận, cần đánh giá và xoay vòng credential liên quan theo quy trình ứng phó sự cố. Không tuyên bố “không có rò rỉ” chỉ vì log cục bộ không thấy: sự kiện có thể đã đi tới remote appender hoặc bị xóa.

## 16. Những hiểu nhầm thường gặp

**“Chỉ cần đặt ROOT=INFO là đủ an toàn.”** Không đúng. Logger con có thể override DEBUG/TRACE, appender/filter có thể đổi và file cấu hình có thể bị sửa.

**“chmod 0644 là không ai sửa được.”** Quyền ghi theo owner/group, ACL, parent directory, mount hoặc quyền root vẫn quan trọng. Mode 0644 chỉ quy định quyền ở một bối cảnh filesystem, không bảo vệ control plane.

**“scan=false nghĩa là logger bất biến.”** Sai. Nó chỉ vô hiệu cơ chế quét file tự động của Logback; runtime API hoặc đường cấu hình khác vẫn có thể sửa.

**“monitorInterval=0 khóa mọi thay đổi Log4j 2.”** Không. Nó tắt polling cấu hình, không chặn code hoặc hệ thống quản trị được quyền thay LoggerContext.

**“Endpoint Actuator không public thì không cần auth.”** Mạng nội bộ cũng có rủi ro tài khoản bị lạm dụng và lateral movement; cần xác thực/phân quyền theo mức nhạy cảm.

**“Chỉ expose loggers read-only là đã có phân quyền.”** Access level và exposure không tự thay thế SecurityFilterChain, firewall và identity-based authorization. Cần xác minh cả GET và POST theo phiên bản.

**“Vì audit là INFO nên có thể tắt logger audit tạm thời.”** Sự kiện audit phải dựa trên nghĩa vụ ghi nhận, không phụ thuộc sự thuận tiện khi gỡ lỗi. Nếu audit bắt buộc, cần cơ chế bảo toàn ngoài RAM logging.

**“Đổi DEBUG ngắn hạn không gây rủi ro.”** Trong vài phút vẫn có thể tạo log chứa thông tin nhạy cảm, tăng chi phí lưu trữ và làm nghẽn collector; phải giới hạn phạm vi và kiểm tra dữ liệu.

**“Có hash cấu hình là chắc chắn không ai can thiệp.”** Hash chỉ cho biết file/snapshot có thay đổi khi được so sánh với bản tin cậy; không nhận diện được mọi đổi runtime và không ngăn người có quyền cao sửa cả file lẫn thông tin kiểm tra.

## 17. Checklist triển khai

- [ ] Xác định chính xác các nguồn cấu hình: classpath, file, JVM properties, env, config server, runtime API.
- [ ] File cấu hình được quản lý qua nguồn tin cậy, review và triển khai có kiểm tra toàn vẹn.
- [ ] Process Java có quyền đọc cấu hình cần thiết, không có quyền ghi không cần thiết.
- [ ] Thư mục output log và cấu hình tách biệt; quyền ghi log không cho phép sửa logging configuration.
- [ ] Chính sách reload Logback/Log4j 2 được lựa chọn rõ ràng, không bật tự động nếu không cần.
- [ ] Endpoint HTTP/JMX có kiểm soát exposure, authentication, authorization và audit phù hợp.
- [ ] Chỉ cho phép đổi các logger/level được duyệt; audit/redaction không bị tắt tùy tiện.
- [ ] Có giới hạn thời gian, phê duyệt và rollback cho bật DEBUG/TRACE tạm thời.
- [ ] Đã kiểm tra effective level, appender/filter và đích xuất trên **từng instance**.
- [ ] Có giám sát cấu hình drift, mất audit, thay route, lỗi appender và log volume bất thường.
- [ ] Test cả trường hợp thiếu quyền, sai level, nguồn cấu hình giả và sink lỗi.
- [ ] Dữ liệu nhạy cảm không được đưa vào LogEvent ngay từ nguồn; có redaction và policy lưu trữ phù hợp.
- [ ] Có phương án khôi phục bản cấu hình an toàn và bảo toàn bằng chứng khi có sự cố.

**Kết luận:** Bảo vệ cấu hình logger là kết hợp **nguồn cấu hình đáng tin, quyền thay đổi tối thiểu, cơ chế reload có kiểm soát, bảo vệ API quản trị và khả năng phát hiện/rollback**. Một file XML đúng cú pháp chưa đủ; cần xác nhận cấu hình **thực sự đang có hiệu lực** và bảo đảm log quan trọng được gửi tới một đường lưu trữ phù hợp.

## 18. Tài liệu tham khảo

- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): nguồn cấu hình, logback.configurationFile, scan và tự động reconfiguration.
- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): logger hierarchy, level và additivity.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html): nguồn cấu hình, monitorInterval, plugin và appender reference.
- [Apache Log4j 2 — Configuration properties](https://logging.apache.org/log4j/2.x/manual/systemproperties.html): log4j2.configurationFile, configuration factory và allowed protocols.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): access, exposure, endpoint security và CSRF.
- [Spring Boot — Loggers](https://docs.spring.io/spring-boot/reference/actuator/loggers.html): xem và thay configured/effective level qua Actuator.
- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): setLevel/getLevel và quan hệ logger.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): log security, thông tin nhạy cảm, chống can thiệp và bảo vệ nơi lưu.
