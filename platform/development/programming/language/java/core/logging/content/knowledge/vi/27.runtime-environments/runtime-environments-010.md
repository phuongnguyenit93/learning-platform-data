# Không lẫn cấu hình môi trường khi logging trong Java

## Mục tiêu

Khi một ứng dụng Java chạy ở **development (dev)**, **test**, **staging** và **production (prod)**, mục tiêu ghi log có thể khác nhau. Developer cần thông tin để gỡ lỗi; kiểm thử cần kết quả dễ tái lập; staging cần quan sát hành vi gần production; production cần log ổn định, đủ để vận hành, có kiểm soát chi phí và bảo vệ dữ liệu. **Không lẫn cấu hình môi trường** nghĩa là đúng phiên bản ứng dụng luôn dùng **đúng chính sách logging đã được phê duyệt cho môi trường đang chạy**, kể cả khi có nhiều lớp cấu hình, profile và biến môi trường cùng tồn tại.

Sau bài này, bạn sẽ:

1. Phân biệt **môi trường triển khai**, **Spring profile**, **backend logging** và **cấu hình logging thực sự có hiệu lực**.
2. Biết chọn level, destination, layout, retention và thông tin được phép ghi log theo từng môi trường.
3. Hiểu tại sao file cấu hình được đóng gói, biến môi trường, JVM system properties và tham số dòng lệnh có thể ghi đè nhau.
4. Thiết kế một artifact triển khai được nhiều môi trường mà không sao chép nhầm thông số.
5. Tự chạy ví dụ Java 17 với **java.util.logging** và nhận biết chính sách active.
6. Biết cách kiểm thử, chẩn đoán và ngăn production vô tình bật DEBUG/TRACE, ghi sai file hoặc gửi log sang hệ thống khác.

## 1. “Lẫn cấu hình môi trường” là vấn đề gì?

Đây là lỗi **môi trường A sử dụng nhầm một phần hoặc toàn bộ cấu hình logging của môi trường B**, hoặc ứng dụng kết hợp nhiều nguồn cấu hình đến mức không còn biết chính sách nào đang có hiệu lực.

Ví dụ:

- Production vô tình chạy với **root level DEBUG**, khiến khối lượng log tăng đột biến, có thể lộ dữ liệu trong thông điệp debug.
- Staging gửi log đến cùng **index, tenant, bucket hoặc dashboard** của production; bản ghi thử nghiệm làm sai tín hiệu vận hành.
- Container production dùng **đường dẫn file tuyệt đối của máy developer** nên không ghi được log hoặc ghi vào ổ đĩa không được thu thập.
- Bản build chạy đúng ở dev nhưng test có file **logback-test.xml** và production có **logback.xml** khác mà không ai kiểm soát.
- Cấu hình trong **application-prod.yml** đặt INFO, nhưng biến môi trường **LOGGING_LEVEL_ROOT=DEBUG** tại nơi triển khai lại có mức ưu tiên cao hơn.
- Một ứng dụng chạy nhiều môi trường sử dụng cùng **service name + environment tag** nên dữ liệu quan sát bị trộn, khó lọc sự cố.

Lẫn cấu hình không chỉ là sai log level. Nó còn liên quan **đích ghi, định dạng, thông tin nhạy cảm, vòng đời log, chính sách retention, trace correlation và cách phân quyền xem log**.

~~~text
Cùng mã nguồn / cùng artifact
            │
       Triển khai
            │
    ┌───────┼─────────┬─────────┐
    ▼       ▼         ▼         ▼
   dev     test     staging    prod
    │       │         │         │
    ▼       ▼         ▼         ▼
  policy  policy    policy    policy
    │       │         │         │
    └───────┴─────────┴─────────┘
        Logging backend
             │
     Đúng level / đích
     Đúng nhãn môi trường
     Đúng bảo vệ dữ liệu
~~~

Trong sơ đồ, các môi trường có thể dùng cùng backend, nhưng **giá trị chính sách và đích thu thập** được lựa chọn rõ ràng cho từng môi trường.

## 2. Phân biệt các khái niệm dễ nhầm

| Khái niệm | Vai trò | Điều không nên suy ra |
| --- | --- | --- |
| **Runtime environment** | Nơi app chạy: local, CI test, staging, production. | Tên môi trường không tự thiết lập logging nếu chưa có cơ chế đọc tên đó. |
| **Spring profile** | Nhóm cấu hình Spring đang active, ví dụ dev hoặc prod. | Profile không đương nhiên tương đương với namespace hay quyền truy cập hạ tầng. |
| **Logger level** | Ngưỡng chấp nhận sự kiện ở logger; có thể kế thừa từ root/cha. | Đặt logger DEBUG chưa bảo đảm appender/handler cũng cho qua. |
| **Appender/handler** | Thành phần ghi event đến console, file hoặc sink. | Có appender không có nghĩa sink đã lưu bền vững hoặc có quyền ghi. |
| **Formatter/encoder/layout** | Cách biểu diễn event, có thể là text hoặc JSON. | Thay layout không đồng nghĩa đã đổi đích log. |
| **Logging backend/provider** | Logback, Log4j2, JUL hoặc backend khác thực thi logging. | Dùng SLF4J API không có nghĩa backend đã là Logback. |
| **Configuration source** | Properties/YAML/XML, env var, system property, command line, code runtime. | Một file trong repo chưa chắc là nguồn giá trị cuối cùng. |
| **Environment label** | Trường giúp lọc log theo môi trường trong collector/backend. | Nhãn đúng không bù được việc gửi log sai tài khoản/tenant đích. |

Điều kiện quan trọng nhất là **kiểm tra giá trị thực sự đang active**, không dừng ở việc đọc một file cấu hình dự định được dùng.

## 3. Chọn logging policy cho từng môi trường

Bảng sau là **chính sách mẫu để học và thiết kế**, không phải mặc định bắt buộc của Java, Logback, Log4j2 hay Spring Boot. Điều chỉnh theo nhu cầu của hệ thống.

| Yếu tố | Dev | Automated test | Staging | Production |
| --- | --- | --- | --- | --- |
| Root level gợi ý | INFO; DEBUG cho package đang sửa | WARN/ERROR, trừ test cần xác minh INFO | INFO | INFO hoặc mức được vận hành chấp thuận |
| DEBUG/TRACE | Bật có chọn lọc, tạm thời | Chỉ cho trường hợp test cụ thể | Theo thời hạn, đúng package | Chỉ khi xử lý sự cố có thời hạn và quyền kiểm soát |
| Đích log | Console/IDE; file cục bộ nếu cần | Console hoặc sink cô lập của test | Collector/namespace riêng staging | Collector/namespace riêng production |
| Nhãn môi trường | dev | test | staging | prod |
| Cách biểu diễn | Dễ đọc cho developer | Ổn định và dễ assert | Tương thích pipeline production | Định dạng chuẩn, có correlation ID |
| Dữ liệu nhạy cảm | Vẫn phải redact, không log secret | Dữ liệu giả, không sử dụng secret thật | Dùng dữ liệu thử an toàn | Kiểm soát chặt chẽ, tối thiểu hóa PII/secret |
| Rotation / retention | Nhẹ, cục bộ | Ngắn hoặc dọn sau test | Theo ngân sách và chính sách staging | Theo chính sách lưu giữ và truy cập của tổ chức |
| Điều kiện khi lỗi cấu hình | Thông báo rõ để sửa | Fail test nếu cần | Không tiếp tục nếu đích/nhãn sai nghiêm trọng | Fail deploy/startup cho sai khác có ảnh hưởng an toàn |

**Nguyên tắc:** log level chỉ là một tham số. Mỗi môi trường cần một policy gồm **level + destination + format + metadata + dữ liệu được phép log + lifecycle/retention**.

Một default vận hành an toàn có thể là **root INFO, console output, không bật verbose hoặc ghi log đến đích ngoài khi thiếu cấu hình**. Với dịch vụ đòi hỏi xác định đích và môi trường rõ ràng, nên **từ chối khởi động** nếu không có nhận diện môi trường hợp lệ. Tránh chọn dev/DEBUG khi thiếu biến cấu hình: đó là cách rất dễ làm production thừa log.

## 4. Nguồn cấu hình nào đang thắng?

Tùy backend, cấu hình có thể đến từ:

1. **Defaults của JDK/backend/framework.**
2. **Tài nguyên nằm trong ứng dụng:** logging.properties, logback.xml, logback-spring.xml, log4j2.xml, application.yml, application-prod.yml...
3. **Tệp bên ngoài artifact:** file được mount qua Kubernetes Secret/ConfigMap, file cấu hình của host hoặc hệ thống phát hành.
4. **Environment variables:** ví dụ SPRING_PROFILES_ACTIVE, LOGGING_LEVEL_ROOT hoặc biến riêng do ứng dụng định nghĩa.
5. **JVM system properties:** được truyền ở lúc khởi động bằng -D..., ví dụ java.util.logging.config.file hoặc logback.configurationFile.
6. **Command-line properties:** với Spring Boot, ví dụ --spring.profiles.active=prod, --logging.level.root=INFO.
7. **Cấu hình do code/framework thay đổi lúc chạy.**

**Không có một thứ tự ưu tiên chung cho tất cả.** Với Spring Boot, các property sources có thứ tự ưu tiên được tài liệu hóa; command-line property thông thường có thể override cấu hình từ file. Với JUL, LogManager đọc logging configuration của riêng JUL. Với Logback, cơ chế tìm file cấu hình và chương trình khởi tạo có thứ tự khác. Log4j2 lại có quy tắc riêng.

Thực tế cần trả lời ba câu hỏi:

- **Nguồn nào đã được nạp?** Ví dụ application-prod.yml có thực sự được áp dụng cho process này?
- **Có nguồn mạnh hơn override không?** Ví dụ cùng khóa logging.level.root được đặt ở env var hoặc command line?
- **Giá trị cuối cùng và đích thật là gì?** Ghi nhận effective level, appender/handler và tuyến đẩy log sau khi khởi tạo.

Không đoán thứ tự từ kinh nghiệm dùng phiên bản khác; hãy đối chiếu tài liệu của **phiên bản đang chạy** và kiểm thử bằng process thật.

## 5. Thiết kế cấu hình theo mô hình “base an toàn + khác biệt theo môi trường”

Cách dễ quản trị là đặt các thuộc tính chung trong cấu hình nền, rồi chỉ override những thứ **thực sự cần khác nhau**. Không nhân bản cả file logging cho mỗi môi trường nếu chỉ khác một vài level, vì khi sửa chung một pattern hoặc bộ lọc, các bản sao có thể lệch nhau.

Mô hình tham khảo:

~~~text
Cấu hình chung (root INFO; output có kiểm soát)
              │
              ▼
      Profile môi trường
     /       |       \ 
    dev    staging    prod
     \       |       /
       External overrides
           được phê duyệt
              │
              ▼
        Effective config
              │
              ▼
        Kiểm tra startup
~~~

Hãy tách hai phạm vi:

- **Bất biến hoặc chuẩn dùng chung:** tên trường JSON, quy tắc redact, tên correlation ID, quy ước timestamp, schema và hệ thống nhận diện dịch vụ.
- **Thay đổi theo môi trường:** mức verbose, sampling, sink/tenant, retention, đường dẫn hoặc thông số collector (được cấp cho từng deployment).

Tư duy cần tránh là đóng gói đường dẫn collector production hay credentials production vào file mặc định rồi mong dev tự ghi đè mọi thứ. Default càng ít kết nối ra ngoài và càng an toàn thì nguy cơ nhầm môi trường càng thấp.

## 6. Ví dụ Spring Boot: cô lập logging bằng profile

Với Spring Boot sử dụng starter logging mặc định (thường là Logback), có thể quản lý các level thông dụng qua **application.yml** và các file **application-{profile}.yml**. Spring Boot còn hỗ trợ các backend khác, nhưng ví dụ này dùng property logging chung của Boot và **không thay thế cấu hình backend chuyên sâu**.

Giả sử cấu trúc:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-test.yml
├── application-staging.yml
└── application-prod.yml
~~~

**application.yml** (base policy: hạn chế verbose mặc định):

~~~yaml
spring:
  application:
    name: order-service

logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

**application-dev.yml** (cho phép debug code ứng dụng khi dev):

~~~yaml
logging:
  level:
    com.example.orders: DEBUG
~~~

**application-test.yml** (giảm noise khi chạy test, nếu suite không cần bắt INFO):

~~~yaml
logging:
  level:
    root: WARN
    com.example.orders: WARN
~~~

**application-staging.yml** (giữ chính sách gần production; tránh xả DEBUG toàn hệ thống):

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

**application-prod.yml** (root INFO, chặn debug vô tình từ package ứng dụng):

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: INFO
~~~

Các file trên là **ví dụ cấu hình**, không phải chương trình chạy độc lập. Package **com.example.orders** chỉ là placeholder tên package và phải đổi theo ứng dụng. Vì các profile chỉ đổi level, chưa cần viết nhiều XML appender riêng.

### 6.1. Kích hoạt profile một cách tường minh

Ví dụ khi vận hành ứng dụng đã được đóng gói dưới tên **order-service.jar**:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
java -jar order-service.jar --spring.profiles.active=staging
java -jar order-service.jar --spring.profiles.active=prod
~~~

Ba lệnh trên là **ba lần chạy độc lập**, chọn **một** môi trường triển khai cho mỗi process. Tên JAR chỉ minh họa. Ở deployment thực tế, thường cung cấp **SPRING_PROFILES_ACTIVE** bằng environment configuration; ví dụ trên dùng command line để nhìn rõ giá trị chọn.

**Không đưa spring.profiles.active vào bên trong application-prod.yml rồi mong file đó tự kích hoạt chính nó.** Profile phải được lựa chọn ở nguồn cấu hình được đọc đúng giai đoạn khởi động, như biến môi trường, command line hoặc file nền phù hợp.

Nếu profile không được chọn, Spring Boot có thể dùng profile mặc định (**default**), đồng nghĩa app chạy với **application.yml** và các nguồn khác hợp lệ. Vì vậy cần bước kiểm tra deployment để ngăn production khởi động khi thiếu profile prod. Profile Spring không phải cơ chế nhận diện hạ tầng duy nhất: một process có thể được khởi động với profile sai trong namespace production.

### 6.2. Cẩn thận khi có nhiều profile cùng active

Spring Boot có thể kích hoạt nhiều profile, chẳng hạn một profile môi trường và một profile tính năng. Việc có nhiều profile không tự động là lỗi. Nhưng trong quy ước vận hành, các profile **dev/test/staging/prod nên là nhóm loại trừ nhau**: một deployment chỉ thuộc đúng một môi trường. Nếu vừa có dev vừa có prod, các file có thể cùng tham gia resolution và dẫn tới mức log khó dự đoán.

Hãy tự đặt quy tắc kiểm tra tại startup/CI rằng nhóm profile môi trường có **đúng một** giá trị. Các profile feature (ví dụ metrics-enabled) có thể cùng active nếu được thiết kế và kiểm thử riêng.

### 6.3. Biến môi trường có thể ghi đè file profile

Với Spring Boot, **LOGGING_LEVEL_ROOT=DEBUG** là cách cấu hình root logger level từ environment. Dù **application-prod.yml** nói INFO, một override có ưu tiên cao hơn vẫn có thể khiến process thực sự chạy DEBUG.

Trong nhiều môi trường, không thể đảm bảo cấu hình đúng chỉ bằng cách nhìn file trong JAR. Cần kiểm tra cả:

- Environment variables và tham số command line của deployment.
- ConfigMap/Secret, Helm values và các template render cuối cùng nếu dùng hệ điều phối.
- Các nguồn Spring property có ưu tiên cao.
- Level đang hoạt động sau khi ứng dụng khởi tạo.

Spring Boot hỗ trợ mapping biến môi trường cho package-level logging; cách đổi tên class logger qua env var có giới hạn do relaxed binding chuyển tên theo quy tắc riêng. Khi cần mức cho một **class** cụ thể, ưu tiên cấu hình có tên logger chuẩn trong properties/YAML hoặc cơ chế tương ứng của backend, thay vì đoán cách biểu diễn env variable.

### 6.4. Tránh đưa cấu hình vô tình vào code

Các anti-pattern:

~~~java
// Minh họa sai: production thiếu APP_ENV sẽ bị coi là dev.
String environment = System.getenv().getOrDefault("APP_ENV", "dev");
~~~

~~~java
// Minh họa sai: sửa mức log toàn cục vô điều kiện.
java.util.logging.Logger.getLogger("")
        .setLevel(java.util.logging.Level.FINE);
~~~

Thay bằng bước xác thực environment và chính sách tường minh, hoặc để framework cấu hình logging thống nhất từ một nguồn đã kiểm soát. **Đừng đặt log level trong nhiều bean/configurator và không biết component nào chạy cuối.**

## 7. Ví dụ Java 17 độc lập: chọn đúng chính sách JUL

Để quan sát cơ chế này ngay cả khi chưa học Spring Boot, ta dùng **java.util.logging (JUL)** có sẵn trong JDK 17. Chương trình yêu cầu **một tên môi trường** khi khởi chạy; chỉ bốn tên hợp lệ là dev, test, staging, prod. Thiếu hoặc sai tên sẽ bị từ chối thay vì ngầm bật debug.

Chương trình đặt cùng mức cho **root logger** và **ConsoleHandler**, vì JUL có bộ lọc ở cả hai nơi. Nó cũng in tên môi trường đang active để tiện kiểm chứng. Định dạng log được cố định cho demo để output có thể dự đoán.

Lưu thành **EnvironmentLoggingDemo.java**:

~~~java
import java.util.Locale;
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class EnvironmentLoggingDemo {

    private static Level levelFor(String environment) {
        return switch (environment) {
            case "dev" -> Level.FINE;
            case "test" -> Level.WARNING;
            case "staging", "prod" -> Level.INFO;
            default -> throw new IllegalArgumentException(
                    "Unknown environment: " + environment);
        };
    }

    private static Logger configure(Level level) {
        Logger root = Logger.getLogger("");

        for (Handler old : root.getHandlers()) {
            root.removeHandler(old);
            old.close();
        }

        root.setLevel(level);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(level);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + ": " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        root.addHandler(console);
        return root;
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java EnvironmentLoggingDemo dev|test|staging|prod");
            System.exit(2);
            return;
        }

        String environment = args[0].toLowerCase(Locale.ROOT);
        final Level level;
        try {
            level = levelFor(environment);
        } catch (IllegalArgumentException ex) {
            System.err.println(ex.getMessage());
            System.exit(2);
            return;
        }

        Logger root = configure(level);
        Logger log = Logger.getLogger("example.orders");
        log.setLevel(null); // Ke thua root level cho demo.

        System.out.println("environment=" + environment);
        System.out.println("root-level=" + root.getLevel().getName());

        log.fine("Chi tiet xu ly");
        log.info("Da nhan yeu cau");
        log.warning("Do tre tang");
    }
}
~~~

Biên dịch:

~~~bash
javac EnvironmentLoggingDemo.java
~~~

Chạy với dev:

~~~bash
java EnvironmentLoggingDemo dev
~~~

**stdout** của lệnh trên:

~~~text
environment=dev
root-level=FINE
~~~

**stderr** do JUL ConsoleHandler phát ra:

~~~text
FINE: Chi tiet xu ly
INFO: Da nhan yeu cau
WARNING: Do tre tang
~~~

Chạy với production:

~~~bash
java EnvironmentLoggingDemo prod
~~~

**stdout**:

~~~text
environment=prod
root-level=INFO
~~~

**stderr**:

~~~text
INFO: Da nhan yeu cau
WARNING: Do tre tang
~~~

Lệnh với môi trường không hợp lệ:

~~~bash
java EnvironmentLoggingDemo unknown
~~~

In ra stderr:

~~~text
Unknown environment: unknown
~~~

Process thoát với **exit code 2**. Không có chính sách ghi log “dev” được áp dụng âm thầm.

Lưu ý kỹ về output: **ConsoleHandler ghi stderr**, còn hai dòng nhận diện trong chương trình ghi stdout. Nếu terminal/IDE gộp hai stream, thứ tự hiển thị giữa chúng không được bảo đảm; hãy đối chiếu **mỗi stream riêng**. Ví dụ cố tình dùng ASCII ở log message để output không phụ thuộc mã hóa terminal.

**Bài học từ demo:** sự tách biệt môi trường thể hiện ở ba hành vi kiểm chứng được: env được nhận diện tường minh, ngưỡng log áp dụng nhất quán lên logger và handler, và môi trường sai không được coi là dev. Đoạn mã chỉ cho thấy **level và console handler**; hệ production thật còn phải quyết định sink, schema, phân quyền và retention.

Trong chương trình lớn, không tùy tiện sửa root logger/close handler khi các subsystem khác đang logging. Việc cấu hình JUL như demo phù hợp để học ở giai đoạn startup; với ứng dụng có framework, dùng API cấu hình của framework hoặc file cấu hình được nạp trước khi logger bắt đầu hoạt động.

## 8. Với JUL thực tế: tách file cấu hình

JUL cho phép dùng **java.util.logging.config.file** để chọn properties file lúc JVM khởi động. Thay vì đặt mức log bằng mã chạy giữa vòng đời ứng dụng, bạn có thể quản lý file riêng theo môi trường.

Ví dụ file **logging-dev.properties**:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
com.example.orders.level=FINE
~~~

Ví dụ file **logging-prod.properties**:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
com.example.orders.level=INFO
~~~

Trong demo dev trên, chỉ namespace **com.example.orders** được phép FINE; root ở INFO. Handler được cho phép FINE để log FINE từ logger con không bị chặn. Đây là **cấu hình có chọn lọc**, không giống demo phần 7 đặt toàn bộ root ở FINE.

Chọn đúng file ở startup, ví dụ:

~~~bash
java -Djava.util.logging.config.file=logging-dev.properties -cp out com.example.orders.Main
java -Djava.util.logging.config.file=logging-prod.properties -cp out com.example.orders.Main
~~~

Hai lệnh là minh họa cho ứng dụng đã có **com.example.orders.Main** được biên dịch trong **out**; không phải lệnh chạy riêng đoạn demo phần 7. Trong production, đường dẫn file phải được provision bởi deployment tương ứng và được xác thực trước khi chạy.

Đừng tự tạo một file mặc định tên “prod” ngay trong dev image nếu có nguy cơ bị tham chiếu nhầm. Nếu chọn đường dẫn tương đối, cần nhớ **working directory** có thể khác giữa IDE, container, Windows service và CI.

## 9. Với Logback và Log4j2: tách cấu hình backend

Ở ứng dụng dùng **SLF4J + Logback**, backend thường đọc **logback.xml** từ classpath, file test riêng **logback-test.xml** trong test classpath, hoặc đường dẫn được chỉ qua JVM system property **logback.configurationFile**. Điều quan trọng là tên file đang hiện diện trong repository chưa chứng minh file đó được nạp trong runtime.

Ví dụ lựa chọn Logback configuration từ một đường dẫn đã được deployment cấp:

~~~bash
java -Dlogback.configurationFile=/etc/order-service/logback-prod.xml -jar order-service.jar
~~~

Lệnh trên là minh họa cho môi trường kiểu Unix; trên Windows đường dẫn khác. Đảm bảo đường dẫn và file thực sự tồn tại, được cấp quyền đọc và system property được đặt **trước khi** Logback khởi tạo. Đừng dùng cùng file kết nối remote production ở môi trường dev.

Với **Log4j2**, có thể dùng file **log4j2.xml** hoặc cấu hình bên ngoài qua property **log4j2.configurationFile** tùy backend/phiên bản. Cần kiểm tra đúng API/backend đang dùng và status messages khi khởi tạo. Dù có định dạng XML/JSON/YAML, hãy giữ một nguồn điều khiển được phê duyệt cho level, appender, rollover và routing.

### 9.1. Spring Boot và logback-spring.xml

Nếu Spring Boot cần cấu hình sâu hơn các khóa **logging.level.***, có thể dùng **logback-spring.xml**. Tệp này hỗ trợ extension của Boot như **springProfile** để chọn phần cấu hình theo profile.

Ví dụ **độc lập để minh họa XML**, chỉ dùng cho ứng dụng Spring Boot đã tích hợp Logback:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="dev">
        <root level="DEBUG">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="!dev">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>
</configuration>
~~~

Trong ví dụ này dev chạy root DEBUG; mọi trường hợp **không có dev** chạy root INFO. Đây **không phải chính sách bảo đảm đúng môi trường** nếu process bị gán đồng thời dev và prod; cần bước xác nhận profile và quy ước rằng chỉ một profile môi trường được active. Nếu đã chọn cách cấu hình level qua XML này, tránh khai báo cùng chính sách mâu thuẫn ở application.yml/biến môi trường mà không chủ động quản trị ưu tiên.

Dùng **logback-spring.xml** thay cho **logback.xml** nếu cần cú pháp **springProfile** và các extension của Boot. Cơ chế scan/reload của Logback không tương thích với những extension này theo tài liệu Spring Boot; không bật scan=true một cách tùy tiện. Với nhu cầu chỉ thay đổi level theo profile, các file **application-{profile}.yml** thường đơn giản và dễ kiểm tra hơn.

**Điểm mấu chốt:** profile giúp **chọn policy**, nhưng cần thêm bước **xác minh active profile, effective level và sink**. XML đúng cú pháp không bảo đảm process đang chạy đúng môi trường.

## 10. Chặn lẫn môi trường ở cấp deployment và log collector

Một chính sách logging hoàn chỉnh còn phải kiểm soát nơi log đi sau khi rời JVM.

### 10.1. Chọn sink theo môi trường

Ví dụ một hệ thống có collector tách biệt:

~~~text
dev     -> console local / collector-dev
test    -> isolated test capture
staging -> collector-staging / index-staging
prod    -> collector-prod / index-prod
~~~

Các tên chỉ minh họa. Nếu cùng collector hỗ trợ multi-tenant/namespace, cần định nghĩa rõ **tenant, namespace, index, service name và retention** theo môi trường. Có thể chung nền tảng vật lý nhưng phân vùng dữ liệu phải rõ, được bảo vệ bằng credential/permission tương ứng.

**Không dựa chỉ vào nhãn environment=prod để phân quyền.** Nếu một tiến trình staging có credential ghi được vào production index, nhãn staging đúng cũng không ngăn được dữ liệu bị đưa sai nơi. Cần giới hạn quyền tại sink, namespace, token và network policy.

### 10.2. Gắn nhãn chính xác

Log tập trung thường cần các trường như:

~~~json
{
  "service": "order-service",
  "environment": "staging",
  "severity": "INFO",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "message": "Order accepted"
}
~~~

Đây là dữ liệu minh họa, không phải stdout của chương trình Java ở phần 7. Giá trị **environment** nên được cấp tại deployment và kiểm soát bằng config; đừng lấy mặc định “prod” trong mã rồi vô tình gắn nhãn production cho log dev. **trace_id** nếu có phải đến từ tracing context thực tế, không tự sinh giả để làm log trông đầy đủ.

Nếu log collector tự thêm nhãn Kubernetes namespace hoặc deployment environment, tránh để ứng dụng tự chèn giá trị khác mâu thuẫn. Nên chọn nguồn có thẩm quyền và đối chiếu tại nơi index log.

### 10.3. Không đưa secrets vào log hoặc config repo

Không ghi token, password, authentication header, session cookie, raw payment data hoặc dữ liệu người dùng nhạy cảm trong thông điệp log. Điều này áp dụng cả dev và test; môi trường dev có thể chứa dữ liệu thật. Chọn cơ chế **redaction** theo schema và kiểm thử các trường nhạy cảm trước khi log được gửi ra khỏi process.

Đường dẫn collector, tenant ID và credential cần được quản lý theo policy deployment. Credential phải nằm trong secret store phù hợp, cấp quyền tối thiểu và được đưa vào runtime qua kênh được phép; không hard-code vào **application-prod.yml** được commit. Không in toàn bộ environment variables hoặc config dump trong log khởi động vì chúng có thể chứa secrets.

### 10.4. Retention, rollover, disk limit

Dev có thể chỉ in console hoặc giữ file nhỏ; production thường cần chiến lược retention, rotation và giới hạn dung lượng phù hợp. Không sao chép retention quá dài của production sang test (gây tốn tài nguyên), cũng không sao chép policy ngắn của dev sang production (có thể mất lịch sử sự cố). Trong container, ghi console rồi để nền tảng thu thập thường dễ kiểm soát hơn việc mỗi container tự quản lý file; nhưng lựa chọn cuối phụ thuộc hạ tầng.

## 11. Test để phát hiện lẫn cấu hình trước khi deploy

Để chắc chắn quy tắc không chỉ tồn tại trên giấy, hãy kiểm thử bằng **artifact đã build thực tế**, trên cấu hình giống môi trường đích.

### 11.1. Ma trận kiểm thử chính sách

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Chạy dev | Profile/nhãn dev; DEBUG chỉ ở logger được phép; log đi đến sink dev. |
| Chạy test | Không chạm sink production; kết quả log phù hợp nhu cầu assertion. |
| Chạy staging | Không có production credential; log có nhãn staging và đến đúng index. |
| Chạy prod | Root/selected loggers đúng level; không bật debug ngoài danh sách cho phép; sink production đúng. |
| Không đặt environment | Process fail hoặc dùng safe base có chặn triển khai sai theo thiết kế; tuyệt đối không âm thầm bật dev DEBUG. |
| Environment không hợp lệ | Báo lỗi rõ, exit code khác 0 (nếu policy yêu cầu). |
| Hai profile môi trường đồng thời | Bị phát hiện và từ chối theo quy ước triển khai. |
| Có env var override | Effective level đúng chính sách sau khi áp dụng thứ tự ưu tiên. |
| Collector/destination lỗi | Có tín hiệu vận hành và fallback đúng policy; không tự gửi sang tenant khác. |
| Shutdown/restart | File/async buffer drain theo chính sách, không phát sinh log ở đích của lần triển khai khác. |

Các test quan trọng nhất là **kiểm thử kết quả**, không chỉ kiểm thử nội dung file: có thể một file YAML ghi INFO đúng nhưng process vẫn active DEBUG do override khác.

### 11.2. Assertions nên có

- **Active environment** xác định và thuộc tập hợp cho phép.
- **Đúng một environment deployment profile** (nếu bạn chọn quy ước này).
- **Root level** và logger exceptions đúng giá trị mong đợi.
- **Appender/handler destination** hợp lệ, không có console + remote appender trùng bất ngờ.
- **Không có secret** trong event mẫu, kể cả ở DEBUG.
- **Environment label và collector namespace** khớp.
- **Startup error** được phát hiện sớm và có thông báo rõ; process không âm thầm dùng default nguy hiểm.

Trong Spring Boot test có thể dùng **@ActiveProfiles("test")** để chủ động chọn test profile, nhưng vẫn cần xác minh file test và override runtime của CI. Logging là tài nguyên có phạm vi rộng trong JVM; nếu test chủ động đổi root logger/backend bằng code, hãy restore state sau test, và tránh các test chạy song song thay đổi cùng global logging context.

### 11.3. Kiểm thử thủ công bằng ví dụ Java 17

Với chương trình ở mục 7, thử:

~~~bash
java EnvironmentLoggingDemo dev
java EnvironmentLoggingDemo test
java EnvironmentLoggingDemo staging
java EnvironmentLoggingDemo prod
java EnvironmentLoggingDemo unknown
~~~

Giá trị INFO/FINE/WARNING có thể được so sánh cho từng môi trường. Với **test**, root WARNING nên chỉ thấy log WARNING; với staging và prod, root INFO nên thấy INFO và WARNING. Đây là bài tập cơ chế level, không thay thế bài kiểm thử sink/schema thật.

## 12. Hướng dẫn chẩn đoán khi thấy log “sai môi trường”

Khi production bỗng ghi quá nhiều DEBUG hoặc log của staging xuất hiện trong dashboard production, nên truy theo từng ranh giới:

1. **Đọc thông tin triển khai:** container/image digest, JVM arguments, active profile, namespace, tên dịch vụ, deployment configuration.
2. **Kiểm tra nguồn config được nạp:** application files, Logback/Log4j config, JUL config, cấu hình đã mount, cấu hình test vô tình lọt vào package.
3. **Tìm override có ưu tiên cao:** biến môi trường, command-line properties, system properties, central config, code runtime thay đổi logger level.
4. **Đối chiếu backend thực tế:** app có đang dùng Logback, Log4j2, JUL hay provider khác? Có nhiều provider hoặc bridge bất thường không?
5. **Kiểm tra effective logger level và handler/appender:** biết sự kiện được cho qua ở đâu. Đừng chỉ đọc root level nếu package có level riêng.
6. **Kiểm tra appender/collector và namespace:** phân biệt log bị gắn nhãn sai với log được gửi nhầm sink.
7. **Kiểm tra thời điểm thay đổi:** deploy mới, restart, profile change, config reload, feature flag, manual log-level override.
8. **Khôi phục có kiểm soát:** đưa level/đích về policy được phê duyệt, triển khai lại nếu cần; thêm regression test cho lỗi vừa phát hiện.

Không khắc phục bằng cách đổi dấu nhãn environment trong log collector nếu sự cố thật sự là credential hoặc sink bị dùng chéo. Sửa điểm chọn cấu hình và quyền truy cập ban đầu.

### Tình huống “application-prod.yml đúng mà log vẫn DEBUG”

Quy trình tìm nguyên nhân:

~~~text
application-prod.yml: root=INFO
       │
       ├── Profile prod active?   -> nếu không, file chưa được chọn
       │
       ├── Override khác?        -> LOGGING_LEVEL_ROOT, CLI, config ngoài?
       │
       ├── Logger con DEBUG?     -> package/class exception?
       │
       ├── Backend có đúng?      -> Logback/Log4j2/JUL/provider khác?
       │
       └── Đích log đúng?        -> filter, appender, collector, stale deployment?
~~~

Chỉ sau khi kiểm tra từng điểm mới nên kết luận “framework bỏ qua file cấu hình”.

## 13. Những lỗi thiết kế thường gặp

**1. Dùng dev làm default khi thiếu environment.** Điều này tiện trên máy lập trình nhưng nguy hiểm khi triển khai: production có thể in DEBUG và dùng tài nguyên dev. Thay bằng safe base hoặc bắt buộc khai báo env.

**2. Sao chép một file production sang dev rồi thay vài dòng.** File copy có thể giữ endpoint, credential, file path hoặc retention production. Nên có base chung, override nhỏ, và kiểm thử sink theo từng deployment.

**3. Coi active profile là bằng chứng đủ.** Một process có thể active prod nhưng bị env var override root DEBUG hoặc collector bị cấu hình sai. Kiểm tra effective logging policy.

**4. Trộn level ở YAML, XML, biến môi trường và code.** Nhiều nguồn cùng điều khiển một khóa gây khó biết bên nào thắng. Chọn nguồn có thẩm quyền cho từng loại cấu hình và ghi rõ quy tắc override.

**5. Bật DEBUG/TRACE toàn bộ production vô thời hạn.** Tăng CPU, I/O, chi phí lưu trữ và nguy cơ để lộ dữ liệu. Ưu tiên level theo package, thời hạn, kiểm duyệt và giám sát lượng log.

**6. Đưa config test vào artifact production.** File như **logback-test.xml** có thể được nạp khi test nhưng không nên hiện diện trong production classpath ngoài ý muốn. Kiểm tra packaging và runtime classpath.

**7. Dùng log label thay cho phân quyền.** Gắn environment=staging lên bản ghi không ngăn được credential staging ghi vào production tenant. Phải tách quyền và routing tại hạ tầng.

**8. Log toàn bộ config/env để debug.** Có thể lộ credential, token hoặc thông tin cá nhân. Chỉ log các trường chẩn đoán được phép, như tên profile, config version, backend name và level (sau lọc), không log secret.

**9. Chỉ kiểm thử dev.** Lỗi lẫn môi trường thường xuất hiện khi CI/CD thay property source, container working directory, profile hoặc collector. Phải kiểm thử staging/prod policy ít nhất ở dạng smoke/config validation.

**10. Quên cấu hình có thể thay đổi lúc chạy.** Một số framework/backend hỗ trợ thay level động hoặc reload file. Cần audit ai thay, lúc nào, thời hạn khôi phục và giá trị cuối cùng sau reload.

## 14. Mẫu kiểm soát có thể áp dụng cho dự án

Một quy trình có thể dùng trong nhóm phát triển:

1. **Định nghĩa environment contract:** tên môi trường hợp lệ, root level, package exceptions, sink/tenant, format, retention và trường nhạy cảm không được log.
2. **Chọn safe base:** khi không có profile đặc biệt, ứng dụng không bật verbose và không tự ghi tới sink ngoài.
3. **Quy định nguồn cấu hình:** đâu là giá trị đóng gói, đâu là ngoại lệ được inject lúc deploy; không dùng nhiều nơi không kiểm soát cho cùng một policy.
4. **Xác thực startup:** profile đúng môi trường, không có hai profile deployment xung đột, sink/credential khớp namespace; fail nếu sai nghiêm trọng.
5. **Đo policy đang có hiệu lực:** root level, logger exceptions, appender targets, service/environment labels; không in secret.
6. **Kiểm thử deployment pipeline:** smoke test với dev/test/staging/prod và trường hợp thiếu/sai env, override, config reload.
7. **Giám sát production:** volume log theo severity, số lượng DEBUG/TRACE bất thường, collector routing và lỗi ghi log.
8. **Quy trình bật debug tạm thời:** chỉ định logger, mục đích, phạm vi, thời hạn tự phục hồi và người phê duyệt theo chính sách nhóm.

Làm tốt các bước này giúp cùng một codebase được triển khai đến nhiều nơi mà vẫn giữ logging đúng ý nghĩa, giảm nhầm lẫn khi điều tra sự cố và kiểm soát chi phí vận hành.

## 15. Câu hỏi ôn tập

1. Tại sao application-prod.yml đặt INFO vẫn có thể khiến production in DEBUG?
2. Tại sao profile prod active không chứng minh log đang đến đúng production collector?
3. Trong JUL, tại sao chỉ chỉnh logger level mà quên ConsoleHandler level có thể làm “mất log”?
4. Vì sao nên có default an toàn hoặc fail startup, thay vì tự chọn dev khi thiếu biến môi trường?
5. Làm sao phân biệt **dòng log gắn nhãn sai** với **dòng log được gửi đến sai sink/tenant**?
6. Với Spring Boot, khi nào dùng application-{profile}.yml và khi nào cần logback-spring.xml?
7. Một test nào có thể phát hiện staging vô tình dùng credential ghi production log?
8. Nếu cần bật DEBUG tạm thời ở production, phải kiểm soát những điều kiện gì?

## 16. Ghi nhớ

**Không lẫn cấu hình môi trường** là đảm bảo mỗi tiến trình Java được gắn đúng môi trường và dùng đúng **logging policy thực tế** từ startup đến runtime. Cách làm nhất quán là **safe base + override nhỏ theo môi trường + giới hạn quyền sink + kiểm tra effective configuration + regression tests**. Đừng đánh giá chỉ qua một file YAML/XML hay một dòng nhãn môi trường. Hãy kiểm tra cả level, filter, appender/handler, file/collector destination, dữ liệu nhạy cảm và tác động của các nguồn cấu hình ưu tiên cao.

### Tài liệu tham khảo

- Spring Boot Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Logback Configuration Manual: https://logback.qos.ch/manual/configuration.html
- Java 17 LogManager API: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- Log4j2 Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
