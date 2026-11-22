# Tên file cấu hình logging trong Java

## 1. Tên file cấu hình quyết định điều gì?

Khi ứng dụng Java khởi động, logging backend cần biết level, appender/handler, định dạng thông điệp, nơi ghi và các chính sách liên quan. Một số backend tự tìm cấu hình theo **tên file quy ước** trên classpath; một số dùng cấu hình mặc định của JDK hoặc đường dẫn được chỉ định bằng system property. Nếu đặt sai tên, sai thư mục hoặc dùng cú pháp của backend khác, chương trình có thể vẫn chạy nhưng sử dụng cấu hình mặc định, dẫn đến các lỗi khó nhận ra: log DEBUG biến mất, định dạng không đúng, hoặc không ghi ra file mong muốn.

**Cần phân biệt ba khái niệm:**

- **Tên file cấu hình:** chẳng hạn logback.xml, log4j2.xml, logback-spring.xml hay logging.properties. Đây là tài liệu cấu hình backend.
- **Đường dẫn tìm cấu hình:** root của runtime classpath, một tài nguyên classpath được chỉ định rõ, hoặc đường dẫn file ngoài ứng dụng.
- **Tên file đầu ra log:** chẳng hạn application.log hoặc /var/log/orders/service.log. Đây là dữ liệu được appender/handler tạo ra; không phải file cấu hình.

Một file có tên đúng nhưng đặt nhầm chỗ vẫn có thể không được tìm thấy. Một file nằm đúng chỗ nhưng có cú pháp sai cũng không được xử lý như mong đợi.

## 2. Bảng tra cứu nhanh

| Logging system | Tên file cấu hình thường dùng | Cách được chọn | Lưu ý |
| --- | --- | --- | --- |
| Java Util Logging (JUL, java.util.logging) | logging.properties | Mặc định từ cấu hình JDK; có thể chỉ rõ đường dẫn qua java.util.logging.config.file | JUL không tự coi mọi file logging.properties trong src/main/resources là file cấu hình mặc định |
| Logback classic | logback.xml | Tự tìm trên classpath khi không có cấu hình ưu tiên cao hơn | Cấu hình XML phổ biến cho ứng dụng Java dùng SLF4J + Logback |
| Logback classic, chạy test | logback-test.xml | Khi có trên classpath thì được ưu tiên so với logback.xml trong cơ chế khám phá XML thông dụng | Đặt trong src/test/resources để không phát hành nhầm |
| Log4j 2 Core | log4j2.xml, log4j2.properties, log4j2.json, log4j2.yaml hoặc log4j2.yml | Tự khám phá theo các factory/định dạng được runtime hỗ trợ | Không lấy tên log4j.xml của Log4j 1 để mặc định cho Log4j 2 |
| Log4j 2 Core, chạy test | log4j2-test.xml hoặc log4j2-test với đuôi cấu hình được hỗ trợ | Nhóm file test được tìm trước nhóm file thường | Chỉ đặt file test trên test classpath |
| Spring Boot + Logback | logback-spring.xml; cũng hỗ trợ logback.xml | Spring Boot quản lý tích hợp logging | Ưu tiên logback-spring.xml khi cần springProfile/springProperty |
| Spring Boot + Log4j 2 | log4j2-spring.xml; cũng hỗ trợ log4j2.xml | Spring Boot quản lý tích hợp Log4j 2 | File có hậu tố -spring cần cơ chế của Boot |
| Spring Boot, cấu hình mức ứng dụng | application.properties hoặc application.yaml/application.yml | Spring Boot đọc thông số logging.* từ Environment | Không thay thế mọi cấu hình chuyên sâu của Logback/Log4j 2 |

Bảng này áp dụng cho các cách cấu hình phổ biến. Logger factory, service provider, class loader, phiên bản và instrumentation có thể làm cơ chế khám phá thực tế thay đổi; khi vận hành phải kiểm tra **backend thực sự được tải**.

**SLF4J là API/facade, không phải backend tự ghi log.** Không có một tên file cấu hình XML chung cho mọi ứng dụng chỉ vì code gọi org.slf4j.Logger. Khi SLF4J dùng Logback thì cấu hình theo Logback; khi được nối với Log4j 2 thì theo Log4j 2. Cũng không nên chỉ nhìn dependency gián tiếp và kết luận framework nào đang hoạt động.

## 3. Classpath và vị trí file

Với cấu trúc Maven thông dụng:

~~~text
logging-demo/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/example/LoggingDemo.java
│   │   └── resources/
│   │       └── logback.xml
│   └── test/
│       └── resources/
│           └── logback-test.xml
└── target/
    ├── classes/
    │   └── logback.xml
    └── test-classes/
        └── logback-test.xml
~~~

Khi build, Maven thường copy tài nguyên main vào target/classes và tài nguyên test vào target/test-classes. Trong lúc chạy test, cả hai vùng có thể cùng nằm trên classpath, nên Logback gặp logback-test.xml trước logback.xml theo quy tắc tìm cấu hình XML. Khi đóng gói ứng dụng bình thường, tài nguyên trong src/test/resources không nên được đưa vào artifact phát hành.

**Classpath root** là nơi bắt đầu của việc tìm tài nguyên, không nhất thiết là thư mục hiện tại nơi bạn gõ lệnh. Ví dụ, nếu backend đang tìm tài nguyên logback.xml ở root classpath, thì:

~~~text
src/main/resources/logback.xml             # tên mặc định: có thể được tìm
src/main/resources/config/logback.xml      # KHÔNG cùng vị trí; cần chỉ rõ đường dẫn hoặc cách nạp khác
src/main/java/logback.xml                  # KHÔNG phải nơi tài nguyên cấu hình Maven mặc định
src/test/resources/logback-test.xml        # cấu hình dành riêng cho test
~~~

Trong Spring Boot executable JAR, cấu trúc vật lý bên trong JAR khác JAR thư viện thông thường, nhưng tài nguyên từ src/main/resources vẫn có thể được truy cập qua classpath mà Boot thiết lập. Không suy diễn đường dẫn hệ điều hành bên trong JAR từ đường dẫn classpath.

### Tên phải chính xác

Trên hệ điều hành phân biệt chữ hoa/chữ thường (thường gặp trên Linux), Logback.xml và logback.xml là hai tên khác nhau. Khoảng trắng, đuôi phụ hoặc đặt nhầm extension có thể khiến file bị bỏ qua: logback.xml.txt không phải logback.xml. Trên Windows, cấu hình có thể hoạt động trong máy dev nhưng không được nạp trên máy chủ Linux nếu dựa vào sự khác nhau về chữ hoa/chữ thường.

## 4. Java Util Logging (JUL): logging.properties

JUL là logging API có sẵn trong JDK. Với JDK 17, cấu hình mặc định thông thường nằm tại:

~~~text
<JDK_HOME>/conf/logging.properties
~~~

Trong ví dụ trên, JDK_HOME là thư mục cài đặt JDK. **Không mặc định quét src/main/resources/logging.properties theo tên** như Logback tìm logback.xml. Muốn dùng file khác, thường chỉ rõ bằng JVM system property:

~~~bash
java -Djava.util.logging.config.file=conf/dev-logging.properties -cp out example.LoggingDemo
~~~

Điểm quan trọng:

- Thuộc tính java.util.logging.config.file là **đường dẫn file cấu hình JUL**, không phải đường dẫn file log được ghi ra.
- Nội dung phải theo định dạng Java .properties của JUL; đặt đuôi .xml rồi truyền cho JUL không khiến nó đọc cú pháp XML.
- Thuộc tính nên được truyền khi JVM khởi động, trước lúc LogManager khởi tạo.
- JUL còn hỗ trợ cơ chế cấu hình chuyên biệt qua java.util.logging.config.class. Nếu dùng cơ chế này, không thể chỉ nhìn tên file rồi suy ra cấu hình nạp vào.
- Gọi LogManager.readConfiguration() hoặc các API cập nhật cấu hình lúc runtime có quy tắc riêng; không coi việc thay file trên đĩa là bảo đảm tự reload.

### Ví dụ Java 17 chạy độc lập với tên tùy chọn

Ví dụ này **không cần Maven hoặc thư viện ngoài JDK**. Ta cố ý đặt file tên dev-logging.properties để chứng minh tên có thể tùy chọn khi đường dẫn được chỉ định rõ.

Cấu trúc thư mục:

~~~text
logging-demo/
├── conf/
│   └── dev-logging.properties
└── src/
    └── main/
        └── java/
            └── example/
                └── LoggingDemo.java
~~~

**conf/dev-logging.properties**

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=FINE
java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.SimpleFormatter.format=%4$s: %5$s%n
~~~

**src/main/java/example/LoggingDemo.java**

~~~java
package example;

import java.util.logging.Logger;

public final class LoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(LoggingDemo.class.getName());

    public static void main(String[] args) {
        LOG.info("INFO_VISIBLE");
        LOG.fine("FINE_VISIBLE");
    }
}
~~~

Chạy từ thư mục logging-demo bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 src/main/java/example/LoggingDemo.java
java -Djava.util.logging.config.file=conf/dev-logging.properties -cp src/main/java example.LoggingDemo
~~~

Output do ConsoleHandler tạo ra trên **stderr**:

~~~text
INFO: INFO_VISIBLE
FINE: FINE_VISIBLE
~~~

Lệnh javac sinh ra LoggingDemo.class dưới src/main/java/example. Có thể thay bằng build tool của dự án nếu không muốn biên dịch ngay bên trong cây source.

**Vì sao đúng?** System property dẫn LogManager tới file dev-logging.properties từ lúc JVM bắt đầu. Cấu hình đặt mức FINE cho root logger và ConsoleHandler; định dạng SimpleFormatter chỉ xuất level và message, giúp kết quả dễ kiểm tra. Tên dev-logging.properties không có tính năng tự khám phá đặc biệt: nếu bỏ system property, JUL sẽ dùng nguồn cấu hình mặc định/phương án cấu hình khác hiện có, và kết quả FINE_VISIBLE không còn được bảo đảm.

### Đổi tên file mà không cập nhật đường dẫn

Nếu đổi dev-logging.properties thành local.properties nhưng vẫn giữ lệnh chạy cũ, đây là **lỗi chọn nguồn cấu hình**, không phải lỗi của Logger.info. Phải cập nhật system property thành conf/local.properties, hoặc trở lại tên cũ. Kiểm tra working directory vì đường dẫn tương đối được giải từ thư mục làm việc của process.

## 5. Logback: logback.xml và logback-test.xml

Logback thường là backend của ứng dụng dùng SLF4J. Trong cơ chế tự động tìm cấu hình XML thông dụng, khi không có cấu hình tùy biến được ưu tiên, Logback thử **logback-test.xml trước**, rồi **logback.xml** trên classpath. Nếu không tìm được, nó có thể dùng cấu hình cơ bản ghi console; chi tiết cơ chế khởi tạo phụ thuộc phiên bản Logback và các configurator đã đăng ký.

Tên thường gặp:

~~~text
src/main/resources/logback.xml          # ứng dụng chạy bình thường
src/test/resources/logback-test.xml     # unit/integration test
~~~

**Ví dụ nội dung logback.xml:**

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>LB %level %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đoạn XML trên là một file cấu hình Logback hợp lệ khi ứng dụng có logging backend Logback thích hợp. Với một lời gọi SLF4J log.info("started"), pattern sẽ hiển thị:

~~~text
LB INFO started
~~~

Nó **không** phải chương trình Java độc lập. Cần dependency như logback-classic tương thích với slf4j-api và code dùng logger. Với Logback, đừng đặt file tên log4j2.xml rồi mong Logback tự hiểu.

### Chọn đường dẫn Logback bên ngoài JAR

Có thể truyền JVM system property:

~~~bash
java -Dlogback.configurationFile=/etc/orders/logback-prod.xml -jar orders.jar
~~~

Property logback.configurationFile có thể trỏ tới file path, URL hoặc classpath resource phù hợp theo cơ chế Logback. Đặt property **trước khi logger đầu tiên được tạo**. Đừng set quá muộn trong business code sau khi backend đã khởi tạo rồi chờ cấu hình tự đổi.

Trong dự án deploy khác nhau theo môi trường, giữ file mặc định đơn giản trong classpath hoặc chỉ định một file bên ngoài. Khi tên file bên ngoài không còn là logback.xml, việc load thành công đến từ **property đường dẫn**, không phải vì Logback tự tìm mọi file .xml trong thư mục.

### Test có thể che cấu hình main

Nếu logback-test.xml vô tình được đóng gói cùng ứng dụng production, nó có thể làm cấu hình quan sát được khác logback.xml. Nên giữ file test tại src/test/resources và rà soát artifact sau đóng gói. Không dựa vào việc nhìn một file logback.xml tồn tại trong repository để kết luận runtime dùng nó.

### Lưu ý phiên bản

Các phiên bản Logback mới có thêm một số cơ chế cấu hình, ví dụ các configurator được nạp qua service provider và định dạng mô hình đã serialize. Tài liệu chính thức mô tả thứ tự khởi tạo chi tiết. Quy tắc logback-test.xml rồi logback.xml ở trên là **nhánh khám phá XML thông dụng**, không có nghĩa mọi ứng dụng dùng Logback đều bỏ qua các configurator nâng cao.

## 6. Log4j 2: log4j2.xml và log4j2-test.xml

Log4j 2 là hệ thống khác Logback và khác Log4j 1.x. **Log4j 2 Core** dùng cơ chế ConfigurationFactory để tìm cấu hình. Những tên quen thuộc gồm:

~~~text
src/main/resources/log4j2.xml
src/main/resources/log4j2.properties
src/main/resources/log4j2.json
src/main/resources/log4j2.yaml
src/test/resources/log4j2-test.xml
~~~

Không phải tất cả định dạng sẽ hoạt động trong mọi runtime: cần ConfigurationFactory và các thư viện parser tương ứng. Với JSON/YAML, kiểm tra dependency của ứng dụng thay vì chỉ đổi đuôi file XML sang .json/.yaml.

### Trình tự khám phá trong Log4j 2

Tài liệu Log4j 2 mô tả nhóm tên theo mức ưu tiên:

1. log4j2-test theo tên **LoggerContext** kèm đuôi được hỗ trợ.
2. log4j2-test với đuôi được hỗ trợ.
3. log4j2 theo tên LoggerContext kèm đuôi được hỗ trợ.
4. log4j2 với đuôi được hỗ trợ.

Đối với trường hợp thông dụng không có tên context riêng, điều cần nhớ là **file -test được ưu tiên trước file thường**. Khi có nhiều định dạng cùng tồn tại (ví dụ log4j2.xml và log4j2.properties), thứ tự còn phụ thuộc ConfigurationFactory; vì vậy nên đặt **một file chủ đạo** và xóa bản cũ, thay vì cược vào thứ tự phát hiện.

**Ví dụ nội dung log4j2.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="L4J2 %level %msg%n"/>
        </Console>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Đoạn XML cấu hình Log4j 2 Core, khác cấu trúc <configuration> của Logback. Nếu ứng dụng có Log4j 2 API và Core hợp lệ, một thông điệp INFO "started" sẽ có dạng:

~~~text
L4J2 INFO started
~~~

Đoạn ví dụ biểu diễn phần cấu hình, không phải chương trình Java chạy riêng.

### Chọn file Log4j 2 ngoài classpath

Với Log4j 2.x:

~~~bash
java -Dlog4j2.configurationFile=/etc/orders/log4j2-prod.xml -jar orders.jar
~~~

Property log4j2.configurationFile chọn file cấu hình cụ thể. Nên thiết lập từ lúc khởi động JVM để có hiệu lực ngay khi backend khởi tạo.

**Tránh nhầm Log4j 1.x:** log4j.properties và log4j.xml là tên quen thuộc của Log4j 1, đã kết thúc vòng đời. Log4j 2 không mặc định đọc chúng như cấu hình Log4j 2. Nếu dự án kế thừa đang có file tên cũ, cần xác định runtime/plugin tương thích được dùng và thực hiện chuyển đổi cấu hình đúng cách.

## 7. Spring Boot: hậu tố -spring và application.properties

Spring Boot có lớp tích hợp logging riêng. Trong ứng dụng Spring Boot dùng starter logging mặc định, backend phổ biến là Logback; khi dự án thay bằng starter Log4j 2, tên file cấu hình cần đổi tương ứng.

### Dùng Logback với Spring Boot

Khuyến nghị thông thường:

~~~text
src/main/resources/logback-spring.xml
~~~

Spring Boot nhận biết logback-spring.xml, còn Logback độc lập **không coi hậu tố -spring là tên mặc định**. Lợi ích của file -spring là Boot có thể quản lý thời điểm cấu hình và cung cấp các phần mở rộng như <springProfile> và <springProperty>.

**Ví dụ logback-spring.xml:**

~~~xml
<configuration>
    <springProfile name="dev">
        <appender name="DEV" class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>DEV %level %msg%n</pattern>
            </encoder>
        </appender>
        <root level="DEBUG">
            <appender-ref ref="DEV"/>
        </root>
    </springProfile>

    <springProfile name="prod">
        <appender name="PROD" class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>PROD %level %msg%n</pattern>
            </encoder>
        </appender>
        <root level="INFO">
            <appender-ref ref="PROD"/>
        </root>
    </springProfile>
</configuration>
~~~

Đây là ví dụ cho **Spring Boot + Logback**, không dành cho chương trình Logback thuần. File chỉ xác lập appender/root cho hai profile dev và prod; cần kích hoạt một profile tương ứng để có cấu hình mong muốn. Không dùng tag <springProfile> trong logback.xml tiêu chuẩn vì file đó có thể được Logback khởi tạo quá sớm, trước khi phần mở rộng Boot sẵn sàng. Các extension của Boot cũng không tương thích với Logback configuration scanning thông thường.

### Dùng Log4j 2 với Spring Boot

Khi chọn Log4j 2 làm backend cho Boot:

~~~text
src/main/resources/log4j2-spring.xml
~~~

Spring Boot hỗ trợ tên này và các extension riêng. Log4j 2 Core độc lập thường tìm log4j2.xml/log4j2.properties... theo quy ước của chính nó; tên log4j2-spring.xml không phải tên tự khám phá chuẩn của Log4j 2 độc lập.

**Không dùng đồng thời Logback và Log4j 2 làm backend chính** chỉ để thử tên file. Chọn đúng dependency/provider trước, rồi đặt tên file tương ứng.

### application.properties và logging.config

Spring Boot có thể nhận các thuộc tính logging.* trong application.properties hoặc application.yaml. Ví dụ:

**src/main/resources/application.properties**

~~~properties
spring.profiles.active=dev
logging.level.root=INFO
logging.level.example=DEBUG
logging.config=classpath:config/logback-custom.xml
~~~

Với cấu hình này, **logging.config** yêu cầu Boot dùng tài nguyên config/logback-custom.xml trên classpath, nếu backend là Logback và file có cú pháp phù hợp. Tài nguyên cần tồn tại tại src/main/resources/config/logback-custom.xml trước khi đóng gói. Đây là ví dụ chọn file với tên tùy ý, không phải tên mặc định tự phát hiện.

Có thể chỉ rõ file ngoài JAR khi triển khai:

~~~properties
logging.config=file:/etc/orders/logback-prod.xml
~~~

Cần bảo đảm ứng dụng có quyền đọc file đó và đường dẫn áp dụng cho môi trường thực tế. Các giá trị Environment cần sẵn sàng ở giai đoạn khởi tạo logging sớm; không giả định rằng property nguồn qua @PropertySource nạp muộn sẽ thay thế được logging.config ngay từ đầu.

**Phân biệt logging.config với logging.file.name:**

~~~properties
logging.config=classpath:logback-spring.xml
logging.file.name=/var/log/orders/application.log
~~~

- logging.config: chỉ **nguồn cấu hình backend**.
- logging.file.name: chỉ **tên file đầu ra log** trong các cấu hình logging của Boot có hỗ trợ; nếu định nghĩa appender riêng trong XML, phải bảo đảm appender đó thực sự sử dụng cài đặt tên file theo thiết kế.
- application.properties: chứa thuộc tính cấu hình ứng dụng/Spring Boot, không phải file Logback XML hay Log4j 2 XML.

Nếu chỉ muốn đổi logging level đơn giản trong Boot, các khóa logging.level.* có thể đã đủ; không bắt buộc tạo XML riêng cho từng mức log.

## 8. Phạm vi lựa chọn và mức ưu tiên: cách hiểu đúng

Không nên xây dựng một danh sách ưu tiên duy nhất áp dụng cho mọi ứng dụng Java. Hệ thống lựa chọn phụ thuộc backend và cơ chế khởi động:

| Hoàn cảnh | Nguồn cấu hình cần kiểm tra đầu tiên |
| --- | --- |
| Java thuần + JUL | java.util.logging.config.file nếu đã truyền; nếu không, cấu hình mặc định của LogManager/JDK |
| Java thuần + SLF4J/Logback | logback.configurationFile hoặc configurator đã đăng ký; sau đó nhánh XML logback-test.xml/logback.xml |
| Java thuần + Log4j 2 Core | log4j2.configurationFile; nếu không có, các tên log4j2-test/log4j2 được runtime hỗ trợ |
| Spring Boot + Logback | logging.config nếu đã khai báo; không thì các vị trí/tên được Boot hỗ trợ, đặc biệt logback-spring.xml |
| Spring Boot + Log4j 2 | logging.config nếu đã khai báo; không thì các tên được Boot hỗ trợ, đặc biệt log4j2-spring.xml |
| Unit test dùng classpath test | Có thể có logback-test.xml hoặc log4j2-test.xml được ưu tiên theo backend |
| Ứng dụng chạy trong container | Kiểm tra tên file trong image, các volume mount, working directory và JVM/system properties thực tế |

Thông số JVM -D... là **Java system property** và phải xuất hiện trước tên main class hoặc trước -jar trong lệnh java. Ví dụ:

~~~bash
java -Dlogback.configurationFile=/etc/app/logback.xml -jar app.jar
~~~

Khác với:

~~~bash
java -jar app.jar -Dlogback.configurationFile=/etc/app/logback.xml
~~~

Ở lệnh thứ hai, chuỗi -D... là **application argument** chuyển tới main chứ không phải JVM system property, trừ khi ứng dụng tự giải mã và xử lý nó. Riêng Spring Boot cũng có cơ chế nhận application argument có dạng --logging.config=...; đừng trộn hai cơ chế mà không xác định ai đọc thuộc tính.

### Classpath có nhiều JAR chứa cùng tài nguyên

Thư viện có thể vô tình đóng gói logback.xml hoặc log4j2.xml, dẫn đến nhiều tài nguyên trùng tên. Kết quả phụ thuộc class loader và cơ chế phát hiện. Một **library** nên để cấu hình logging của nó trong test resources, không áp cấu hình bắt buộc cho mọi ứng dụng sử dụng library. Ứng dụng chính nên sở hữu cấu hình của chính nó.

## 9. Chẩn đoán sai tên hoặc sai vị trí cấu hình

**Tình huống 1: Đã tạo logback.xml nhưng ứng dụng vẫn chỉ log mặc định.**

Kiểm tra backend thực tế có phải Logback không; file có nằm ở root runtime classpath không; tên có đúng chữ thường, đúng extension không; có logback-test.xml, logback.configurationFile hay custom Configurator thay thế không. Nếu chạy Spring Boot và cần extension riêng, dùng logback-spring.xml.

**Tình huống 2: logback-spring.xml không có tác dụng khi chạy Java main thuần.**

Đó là tên được Spring Boot hỗ trợ. Logback độc lập thông thường tìm logback.xml hoặc logback-test.xml. Đổi về logback.xml hợp lệ hoặc chỉ đường dẫn rõ ràng qua logback.configurationFile.

**Tình huống 3: Dự án Log4j 2 có log4j.xml nhưng không đổi level.**

log4j.xml thuộc quy ước Log4j 1.x. Với Log4j 2, dùng log4j2.xml hoặc định dạng được hỗ trợ; kiểm tra dependency Log4j 2 Core. Không chỉ đổi tên file nếu nội dung XML vẫn là cú pháp Log4j 1.

**Tình huống 4: Đặt logging.properties trong src/main/resources nhưng JUL không nhận.**

JUL mặc định dùng cấu hình LogManager/JDK; chỉ rõ -Djava.util.logging.config.file=... để chọn file mong muốn, hoặc nạp qua API quản lý JUL nếu ứng dụng chủ đích thực hiện việc đó.

**Tình huống 5: Test in DEBUG nhưng khi chạy JAR không in.**

Có thể test đang chọn logback-test.xml/log4j2-test.xml, còn production dùng file main hoặc cấu hình mặc định. So sánh runtime classpath và các system properties của hai chế độ.

**Tình huống 6: Đã đổi file cấu hình trên host nhưng không thấy thay đổi.**

Backend có thể chỉ đọc lúc startup; hot reload chỉ hoạt động nếu được cấu hình và hỗ trợ. Với Spring Boot extension như <springProfile>, không bật Logback scan bừa bãi. Tránh giả định mọi thay đổi file ngoài JAR lập tức có hiệu lực.

**Tình huống 7: Đổi tên file log đầu ra nhưng vẫn ghi ở vị trí cũ.**

Có thể bạn mới đổi logging.file.name, trong khi appender riêng của XML đang trỏ thẳng tới file khác. Kiểm tra cấu hình thực tế của appender và giá trị property được tham chiếu, thay vì chỉ kiểm tra tên file XML.

### Checklist thao tác nhanh

1. Xác định logging API (JUL, SLF4J, Log4j 2 API) và **backend thực thi** từ dependency/runtime.
2. Xác định đang chạy Java thuần, Spring Boot, unit test, server hay container.
3. Đối chiếu **tên file chính xác** trong bảng ở mục 2; kiểm tra case và extension.
4. Kiểm tra file thực sự nằm tại **runtime classpath root** hoặc được trỏ tới bằng đường dẫn có chủ đích.
5. Kiểm tra các system properties và logging.config; bảo đảm chúng được truyền trước lúc logging khởi tạo.
6. Tìm tên file test hoặc cấu hình do library/agent cung cấp có thể được chọn ngoài dự kiến.
7. Bật công cụ/diagnostics của backend theo hướng dẫn chính thức khi cần xác minh file nào đã được nạp; chỉ dựa vào một dòng DEBUG xuất hiện là chưa đủ để chứng minh toàn bộ config đã đúng.
8. Kiểm tra lại trên cấu hình đóng gói/triển khai giống production, vì classpath và current working directory có thể thay đổi.

## 10. Bài tập áp dụng

### Bài 1: JUL với tên file tùy ý

Chạy ví dụ mục 4 bằng conf/dev-logging.properties, kiểm tra hai dòng INFO/FINE. Đổi tên file thành conf/local-logging.properties và sửa system property tương ứng. Giải thích vì sao đổi tên đơn thuần không đủ.

### Bài 2: Logback ở main và test

Tạo hai file logback.xml và logback-test.xml ở src/main/resources và src/test/resources. Cho mỗi file dùng pattern khác nhau, ví dụ APP và TEST. Chạy một bài test rồi chạy ứng dụng; quan sát file nào được chọn. Giải thích lợi ích của việc không đóng gói tài nguyên test vào production.

### Bài 3: Spring Boot chọn cấu hình

Trong ứng dụng Spring Boot có backend Logback, đặt src/main/resources/config/logback-custom.xml, trỏ logging.config tới classpath:config/logback-custom.xml. So sánh kết quả với logback-spring.xml tại classpath root, và xác định khi nào phải dùng tên -spring để bật các phần mở rộng Spring.

### Bài 4: Điều tra môi trường triển khai

Giả sử ứng dụng chạy trên Linux khác máy Windows phát triển. File tên LogBack.xml và JVM khởi chạy với một -D đặt sau -jar. Hãy xác định hai nguyên nhân khiến cấu hình không được nhận và viết lệnh khởi động cùng tên file đúng.

## 11. Ghi nhớ

Tên file cấu hình logging chỉ có ý nghĩa khi gắn với **đúng backend, đúng chế độ khởi động và đúng vị trí nạp**. JUL thường đọc logging.properties của JDK hoặc file được chỉ định; Logback thường tìm logback-test.xml/logback.xml; Log4j 2 tìm nhóm log4j2-test/log4j2; Spring Boot hỗ trợ các tên -spring và logging.config. File cấu hình và file đầu ra log phục vụ hai mục đích khác nhau. Khi kiểm tra lỗi, luôn bắt đầu từ backend thực tế, classpath và tham số khởi động.

### Tài liệu chính thức

- Oracle Java 17 – LogManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- Oracle Java 17 – ConsoleHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- Oracle Java 17 – SimpleFormatter: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/SimpleFormatter.html
- Logback manual – Configuration: https://logback.qos.ch/manual/configuration.html
- Logback FAQ – Classpath location: https://logback.qos.ch/faq.html
- Apache Log4j 2 – Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Apache Log4j 2 – FAQ: https://logging.apache.org/log4j/2.x/faq.html
- Spring Boot – Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
