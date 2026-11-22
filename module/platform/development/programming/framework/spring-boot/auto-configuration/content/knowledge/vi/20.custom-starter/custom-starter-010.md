# Kiểm chứng starter từ dự án tiêu thụ độc lập với mã nguồn thư viện

> **Spring Boot Auto Configuration → Starter tùy chỉnh.** Bài học hướng dẫn kiểm chứng một starter bằng một dự án tiêu thụ riêng, chỉ phụ thuộc artifact đã đóng gói và resolve qua Maven. Trọng tâm là xác nhận dependency graph, nội dung JAR, file đăng ký auto-configuration, hành vi bean lúc chạy và khả năng thay thế từ phía ứng dụng. Ví dụ dùng Java 17+, Maven và Spring Boot 3.3.13.

## 1. Vì sao phải kiểm chứng từ một dự án độc lập?

Một thư viện có thể chạy đúng trong chính repository của nó nhưng thất bại khi người dùng cài vào ứng dụng thật. Các nguyên nhân thường gặp:

- Auto-configuration class có trong source nhưng bị thiếu khỏi JAR.
- File AutoConfiguration.imports đặt sai thư mục hoặc sai fully qualified class name.
- Starter không khai báo dependency đến module auto-configuration.
- Auto-configuration module không kéo core module theo dependency graph.
- Một dependency cần lúc runtime bị khai báo với scope không phù hợp.
- Code demo vô tình dùng @Import hoặc component scan để nạp cấu hình, che giấu lỗi đăng ký auto-configuration.
- Maven reactor nhìn thấy module sibling trong cùng build, trong khi người dùng bên ngoài chỉ có artifact đã phát hành.
- Phiên bản Spring Boot hoặc thư viện được resolve trong consumer khác với phiên bản đã dùng khi phát triển starter.

Vì vậy, việc chạy test ngay trong module thư viện là chưa đủ. Cần tạo một **consumer độc lập**:
- Nằm ngoài Maven reactor của thư viện.
- Không import source hoặc class output từ thư viện.
- Không khai báo systemPath, đường dẫn ../ hay relativePath đến module thư viện.
- Chỉ phụ thuộc tọa độ Maven groupId:artifactId:version của starter.
- Được build sau khi thư viện đã được cài vào local repository hoặc phát hành lên repository dùng chung.

Nếu consumer vẫn build được khi không cần mở source repository của thư viện, ta có bằng chứng mạnh hơn rằng starter đã được đóng gói và công bố đúng cách.

## 2. Những gì cần xác minh

Một bài kiểm chứng starter nên đi qua bốn lớp:

| Lớp kiểm chứng | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| Artifact | Các JAR cần thiết có được tạo và cài đặt không? | File trong target/ và local Maven repository |
| Metadata | Boot có thể phát hiện auto-configuration từ JAR không? | META-INF/spring/...AutoConfiguration.imports nằm trong JAR |
| Dependency | Consumer nhận đủ core, auto-config và dependency cần thiết không? | mvn dependency:tree |
| Runtime behavior | Bean có được tạo, tắt và thay thế đúng không? | Integration test và stdout của ứng dụng consumer |

Chỉ kiểm tra artifact tồn tại là chưa đủ. Một JAR có thể được cài vào repository nhưng thiếu imports metadata. Một dependency tree có thể đầy đủ nhưng condition không match. Một context có thể khởi động nhưng bean mặc định không được tạo. Mỗi lớp cần bằng chứng riêng.

## 3. Phân biệt ba dự án và hai môi trường resolve dependency

Ví dụ dùng ba module thư viện và một consumer độc lập:

~~~text
workspace/
├── notice-library/
│   ├── pom.xml
│   ├── notice-core/
│   ├── notice-autoconfigure/
│   └── notice-spring-boot-starter/
│
└── notice-consumer/
    ├── pom.xml
    └── src/
~~~

notice-library là Maven reactor. Nó chứa các module được phát triển và phát hành cùng nhau:
- notice-core: API và logic lõi.
- notice-autoconfigure: bean definitions và metadata tự cấu hình.
- notice-spring-boot-starter: artifact gom dependencies cho người dùng.

notice-consumer là một Maven project riêng. Nó chỉ nhìn thấy các artifact đã được cài vào local Maven repository hoặc tải từ remote repository.

### 3.1. Maven reactor khác local repository thế nào?

Trong một Maven reactor build, Maven có thể resolve module phụ thuộc từ output của module sibling trong cùng reactor. Điều này thuận tiện khi phát triển, nhưng có thể che giấu lỗi đóng gói hoặc phát hành.

mvn install thực hiện build và cài artifact vào local repository mặc định, thường là:

~~~text
~/.m2/repository/
~~~

Trên Windows, thư mục thường nằm dưới:

~~~text
%USERPROFILE%\.m2\repository\
~~~

Sau khi install, consumer có thể resolve dependency theo tọa độ Maven mà không cần biết thư mục source của thư viện.

Phân biệt:
- mvn package: tạo artifact trong target/, chưa cài vào local repository.
- mvn install: tạo artifact và cài vào local repository.
- mvn deploy: chuyển artifact lên remote repository đã cấu hình, thường dùng trong CI/release.

Trong bài thực hành, dùng install để kiểm chứng cục bộ. Không cần phát hành artifact ra ngoài để chứng minh consumer có thể dùng dependency đã đóng gói.

## 4. Thiết kế thư viện mẫu

Ta tạo một thư viện thông báo rất nhỏ. Khi starter được cài, Spring Boot tự cung cấp bean NoticeClient. Ứng dụng có thể tắt bean bằng property hoặc tự khai báo bean thay thế.

### 4.1. Cấu trúc thư viện

~~~text
notice-library/
├── pom.xml
├── notice-core/
│   ├── pom.xml
│   └── src/main/java/com/acme/notice/core/NoticeClient.java
├── notice-autoconfigure/
│   ├── pom.xml
│   ├── src/main/java/com/acme/notice/autoconfigure/NoticeAutoConfiguration.java
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── notice-spring-boot-starter/
    └── pom.xml
~~~

### 4.2. Parent pom.xml của thư viện

Tệp notice-library/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme.notice</groupId>
    <artifactId>notice-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <modules>
        <module>notice-core</module>
        <module>notice-autoconfigure</module>
        <module>notice-spring-boot-starter</module>
    </modules>
</project>
~~~

Parent quản lý phiên bản Spring Boot, Java và version nội bộ của các module. Maven reactor sẽ sắp xếp thứ tự build dựa trên quan hệ dependency; thứ tự liệt kê module không thay thế việc khai báo dependency thật.

### 4.3. Core module

Tệp notice-core/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.notice</groupId>
        <artifactId>notice-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>notice-core</artifactId>
</project>
~~~

Tệp notice-core/src/main/java/com/acme/notice/core/NoticeClient.java:

~~~java
package com.acme.notice.core;

public class NoticeClient {

    public String send(String message) {
        return "sent:" + message;
    }
}
~~~

Core module không cần Spring Boot hoặc Spring Context. Nó chỉ cung cấp API độc lập để các module khác sử dụng. Trong dự án thực tế, đây là nơi đặt interface, domain object và logic nền không cần biết cách Spring đăng ký bean.

### 4.4. Auto-configuration module

Tệp notice-autoconfigure/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.notice</groupId>
        <artifactId>notice-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>notice-autoconfigure</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.acme.notice</groupId>
            <artifactId>notice-core</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Tệp notice-autoconfigure/src/main/java/com/acme/notice/autoconfigure/NoticeAutoConfiguration.java:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.core.NoticeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NoticeClient.class)
    NoticeClient noticeClient() {
        return new NoticeClient();
    }
}
~~~

Cấu hình có hai điều kiện:
- Nếu acme.notice.enabled không tồn tại hoặc bằng true, auto-configuration có thể được áp dụng.
- Nếu ứng dụng chưa cung cấp NoticeClient, Spring tạo bean mặc định.

Khi property là false, bean mặc định không được tạo. Khi ứng dụng tự khai báo NoticeClient, điều kiện missing-bean làm auto-configuration nhường cho bean của ứng dụng.

### 4.5. Đăng ký auto-configuration bằng imports metadata

Tạo file chính xác tại:

~~~text
notice-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung một dòng:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
~~~

Đây là phần rất quan trọng khi kiểm chứng starter. Class NoticeAutoConfiguration có thể biên dịch và nằm trong JAR nhưng Spring Boot không tự phát hiện nếu imports metadata thiếu, sai đường dẫn hoặc ghi sai FQCN.

Không dựa vào component scan của ứng dụng để tìm lớp auto-configuration trong thư viện. Cơ chế đăng ký chuẩn của Spring Boot 3 là file AutoConfiguration.imports.

### 4.6. Starter module

Tệp notice-spring-boot-starter/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme.notice</groupId>
        <artifactId>notice-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>notice-spring-boot-starter</artifactId>

    <dependencies>
        <dependency>
            <groupId>com.acme.notice</groupId>
            <artifactId>notice-autoconfigure</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Starter là artifact gom dependency. Nó đưa auto-configuration và các dependency cần thiết vào ứng dụng. notice-core được kéo theo bắc cầu thông qua notice-autoconfigure; do dependency mặc định có scope compile, consumer có thể import NoticeClient trong source code.

Starter không cần chứa class Java nếu không có logic riêng. JAR của starter có thể gần như rỗng về source nhưng vẫn hữu ích vì dependency descriptor của nó quyết định những artifact nào được đưa vào consumer.

## 5. Build và cài thư viện vào local Maven repository

Mở terminal tại notice-library, tức thư mục có parent pom.xml, rồi chạy:

~~~bash
mvn clean install
~~~

Maven thực hiện:
1. Build notice-core.
2. Build notice-autoconfigure với dependency core.
3. Build notice-spring-boot-starter với dependency auto-config.
4. Đóng gói JAR và POM của từng module.
5. Cài parent và artifact vào local Maven repository.

Kết quả dự kiến:

~~~text
notice-core/target/notice-core-1.0.0.jar
notice-autoconfigure/target/notice-autoconfigure-1.0.0.jar
notice-spring-boot-starter/target/notice-spring-boot-starter-1.0.0.jar
~~~

Trong local Maven repository, tọa độ được ánh xạ thành đường dẫn:

~~~text
com/acme/notice/notice-core/1.0.0/
com/acme/notice/notice-autoconfigure/1.0.0/
com/acme/notice/notice-spring-boot-starter/1.0.0/
~~~

Mỗi thư mục thường chứa POM, JAR và metadata do Maven quản lý.

Nếu build thất bại, cần xử lý lỗi ở module tương ứng trước khi tạo consumer. Không dùng consumer để kiểm tra artifact chưa được tạo hoặc chưa được install thành công.

### 5.1. Kiểm tra các JAR đã được tạo

Từ thư mục notice-library, chạy:

~~~bash
dir notice-core/target
dir notice-autoconfigure/target
dir notice-spring-boot-starter/target
~~~

Trên Bash:

~~~bash
ls notice-core/target
ls notice-autoconfigure/target
ls notice-spring-boot-starter/target
~~~

Kiểm tra tên file và version có đúng tọa độ dependency mà consumer sẽ dùng hay không.

### 5.2. Kiểm tra AutoConfiguration.imports nằm trong JAR

Trên Windows PowerShell/CMD:

~~~powershell
jar tf notice-autoconfigure/target/notice-autoconfigure-1.0.0.jar | findstr /I AutoConfiguration.imports
~~~

Trên Bash:

~~~bash
jar tf notice-autoconfigure/target/notice-autoconfigure-1.0.0.jar | grep AutoConfiguration.imports
~~~

Kết quả cần có:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Tiếp theo kiểm tra class auto-configuration:

~~~bash
jar tf notice-autoconfigure/target/notice-autoconfigure-1.0.0.jar
~~~

Trong danh sách phải có đường dẫn class tương ứng:

~~~text
com/acme/notice/autoconfigure/NoticeAutoConfiguration.class
~~~

Nếu class có nhưng file imports không có, cần kiểm tra vị trí file trong src/main/resources. Maven mặc định chỉ copy resource từ vị trí chuẩn đó vào JAR.

Có thể đọc nội dung file trong JAR bằng lệnh:

~~~bash
unzip -p notice-autoconfigure/target/notice-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nếu môi trường không có unzip, dùng công cụ ZIP/JAR phù hợp. Dòng trả về phải đúng FQCN, không có tên class viết sai hoặc package cũ.

## 6. Tạo consumer độc lập

Bây giờ chuyển sang thư mục notice-consumer nằm ngang hàng với notice-library:

~~~text
workspace/
├── notice-library/
│   └── pom.xml
└── notice-consumer/
    ├── pom.xml
    └── src/
        ├── main/java/com/acme/consumer/ConsumerApplication.java
        └── test/java/com/acme/consumer/
            ├── NoticeStarterEnabledTest.java
            ├── NoticeStarterDisabledTest.java
            └── NoticeStarterOverrideTest.java
~~~

Consumer không phải module con của notice-library. Nó có parent Maven riêng và chỉ khai báo dependency theo tọa độ.

### 6.1. pom.xml của consumer

Tệp notice-consumer/pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme.consumer</groupId>
    <artifactId>notice-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme.notice</groupId>
            <artifactId>notice-spring-boot-starter</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Điểm cần kiểm tra:
- Consumer chỉ khai báo notice-spring-boot-starter.
- Consumer không khai báo trực tiếp notice-core hoặc notice-autoconfigure.
- Không dùng đường dẫn file JAR bằng systemPath.
- Không dùng dependency file: hoặc ../notice-library/....
- Không thêm source directory từ repository thư viện.
- Consumer dùng Spring Boot 3.3.13 để khớp phiên bản compile của thư viện mẫu.

Việc chỉ khai báo starter giúp kiểm chứng dependency graph thực tế mà người dùng nhận được.

### 6.2. ConsumerApplication.java

Tệp notice-consumer/src/main/java/com/acme/consumer/ConsumerApplication.java:

~~~java
package com.acme.consumer;

import com.acme.notice.core.NoticeClient;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ObjectProvider<NoticeClient> clients) {
        return args -> {
            NoticeClient client = clients.getIfAvailable();

            System.out.println(
                    "noticeClient present: " + (client != null)
            );

            if (client != null) {
                System.out.println(
                        "notice result: " + client.send("hello")
                );
            }
        };
    }
}
~~~

Application nằm trong package com.acme.consumer, khác package thư viện com.acme.notice. @SpringBootApplication không component-scan package thư viện. Nếu bean xuất hiện, bằng chứng quan trọng là Boot đã phát hiện auto-configuration qua imports metadata trong artifact.

ObjectProvider cho phép runner xử lý cả trường hợp feature bị tắt. Consumer không inject NoticeClient theo kiểu bắt buộc ở constructor vì bài kiểm chứng cần quan sát cả trạng thái có bean và không có bean.

### 6.3. Test mặc định starter tạo bean

Tệp NoticeStarterEnabledTest.java:

~~~java
package com.acme.consumer;

import com.acme.notice.core.NoticeClient;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class NoticeStarterEnabledTest {

    @Autowired
    ApplicationContext context;

    @Test
    void starterRegistersNoticeClientInConsumer() {
        assertThat(context).hasSingleBean(NoticeClient.class);
        assertThat(context.getBean(NoticeClient.class).send("hello"))
                .isEqualTo("sent:hello");
    }
}
~~~

Test này không import NoticeAutoConfiguration và không gọi @Import. Nó chỉ khởi động consumer như ứng dụng thực tế, rồi kiểm tra bean có mặt và hoạt động.

### 6.4. Test property tắt bean mặc định

Tệp NoticeStarterDisabledTest.java:

~~~java
package com.acme.consumer;

import com.acme.notice.core.NoticeClient;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "acme.notice.enabled=false")
class NoticeStarterDisabledTest {

    @Autowired
    ApplicationContext context;

    @Test
    void disabledPropertyPreventsDefaultBean() {
        assertThat(context).doesNotHaveBean(NoticeClient.class);
    }
}
~~~

Test xác nhận property công khai của starter được đọc trong dự án tiêu thụ. Nó cũng chứng minh bean không được tạo chỉ vì JAR có trên classpath; condition vẫn được áp dụng.

### 6.5. Test user bean thay thế

Tạo cấu hình test:

~~~java
package com.acme.consumer;

import com.acme.notice.core.NoticeClient;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
class CustomNoticeClientConfiguration {

    @Bean
    NoticeClient customNoticeClient() {
        return new NoticeClient() {
            @Override
            public String send(String message) {
                return "custom:" + message;
            }
        };
    }
}
~~~

Tệp NoticeStarterOverrideTest.java:

~~~java
package com.acme.consumer;

import com.acme.notice.core.NoticeClient;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = {
        ConsumerApplication.class,
        CustomNoticeClientConfiguration.class
})
class NoticeStarterOverrideTest {

    @Autowired
    ApplicationContext context;

    @Test
    void userBeanMakesStarterBackOff() {
        assertThat(context).hasSingleBean(NoticeClient.class);
        assertThat(context.getBean(NoticeClient.class).send("hello"))
                .isEqualTo("custom:hello");
    }
}
~~~

Vì NoticeClient không phải final và method send có thể override, test tạo một implementation tùy chỉnh. Nếu starter vẫn tạo bean mặc định cạnh tranh, assertion hasSingleBean sẽ thất bại; nếu starter không nhường, kết quả custom:hello sẽ không xuất hiện.

Đây là kiểm tra hợp đồng override ở phía người dùng. Không cần sửa source thư viện để chạy test.

## 7. Build consumer mà không dùng Maven reactor của thư viện

Sau khi mvn clean install đã thành công trong notice-library, mở terminal mới hoặc chuyển hẳn sang notice-consumer.

Từ thư mục notice-consumer, chạy:

~~~bash
mvn clean test
~~~

Maven chỉ đọc POM của consumer và resolve:
- Spring Boot dependencies.
- com.acme.notice:notice-spring-boot-starter:1.0.0.
- Các dependency bắc cầu mà starter khai báo.

Kỳ vọng ba test PASS:
1. Starter mặc định tạo NoticeClient.
2. Property acme.notice.enabled=false ngăn bean mặc định.
3. Bean do ứng dụng tự cung cấp được ưu tiên.

Không chạy lệnh này từ notice-library với -pl notice-consumer hoặc thêm consumer thành module của parent chỉ để cho Maven nhìn thấy sibling module. Mục tiêu là chứng minh dependency đã được cài/resolve như một thư viện bên ngoài.

### 7.1. Kiểm tra dependency tree của consumer

Từ notice-consumer:

~~~bash
mvn dependency:tree -Dincludes=com.acme.notice
~~~

Kết quả đại diện cần thể hiện quan hệ:

~~~text
com.acme.consumer:notice-consumer:jar:1.0.0
+- com.acme.notice:notice-spring-boot-starter:jar:1.0.0:compile
   +- com.acme.notice:notice-autoconfigure:jar:1.0.0:compile
      +- com.acme.notice:notice-core:jar:1.0.0:compile
~~~

Cách hiển thị chính xác có thể khác theo phiên bản Maven và plugin, nhưng ba artifact phải xuất hiện trong dependency graph.

Nếu notice-core không có mặt, consumer có thể không compile được import NoticeClient. Kiểm tra POM của notice-autoconfigure và starter để bảo đảm dependency không bị khai báo optional hoặc scope không phù hợp.

Nếu notice-autoconfigure không có mặt, starter POM chưa kéo module cấu hình. Khi đó dù core API có trong classpath, Boot cũng không có auto-configuration để đăng ký bean.

### 7.2. Kiểm tra consumer không tham chiếu source repository

Mở notice-consumer/pom.xml và source code, xác nhận:
- Không có module notice-consumer trong parent của thư viện.
- Không có relativePath trỏ về notice-library.
- Không có systemPath trỏ đến file JAR.
- Không có plugin thêm source folder từ thư viện.
- Không import NoticeAutoConfiguration trong ConsumerApplication.
- Không có @Import(NoticeAutoConfiguration.class).

Consumer chỉ cần import public API NoticeClient. Spring Boot tự phát hiện cấu hình từ dependency JAR.

Đây là một trong những tiêu chí quan trọng nhất của bài kiểm chứng: **nếu phải mở source thư viện hoặc tự import auto-configuration thì starter chưa được chứng minh hoạt động như một starter độc lập.**

## 8. Chạy ứng dụng consumer thực tế

Sau khi test pass, đóng gói consumer:

~~~bash
mvn -q -DskipTests package
~~~

Chạy JAR:

~~~bash
java -jar target/notice-consumer-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Stdout do ApplicationRunner in:

~~~text
noticeClient present: true
notice result: sent:hello
~~~

Điều này chứng minh:
- Consumer compile được với API từ artifact đã cài.
- Starter kéo core và auto-configuration vào runtime.
- Boot phát hiện metadata trong JAR.
- Condition mặc định match.
- Bean được tạo và được inject vào consumer.
- API thực thi được.

### 8.1. Chạy lại với property tắt

~~~bash
java -jar target/notice-consumer-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --acme.notice.enabled=false
~~~

Stdout:

~~~text
noticeClient present: false
~~~

Ứng dụng vẫn khởi động vì runner dùng ObjectProvider. Không có bean mặc định khi property tắt.

### 8.2. Chạy với property bật tường minh

~~~bash
java -jar target/notice-consumer-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --acme.notice.enabled=true
~~~

Stdout:

~~~text
noticeClient present: true
notice result: sent:hello
~~~

Kết quả giống trường hợp mặc định vì auto-configuration dùng matchIfMissing=true. Trong thư viện thực tế, mặc định có thể là tắt; khi đó hãy điều chỉnh tài liệu và test theo đúng chính sách của sản phẩm.

## 9. Kiểm chứng bằng JAR, dependency tree và Condition Evaluation Report

Khi consumer không tạo bean, đừng sửa ngay code ứng dụng. Kiểm tra theo từng lớp.

### 9.1. Artifact có được resolve không?

~~~bash
mvn dependency:tree -Dincludes=com.acme.notice
~~~

Nếu starter không xuất hiện, kiểm tra tọa độ dependency:
- groupId
- artifactId
- version
- Repository mà Maven đang tìm kiếm
- Local repository có artifact tương ứng hay chưa

Nếu báo Could not find artifact, kiểm tra mvn install ở thư viện và version trong consumer. Với remote repository, kiểm tra settings, credentials và repository URL theo quy trình tổ chức.

### 9.2. Starter có kéo auto-configuration không?

Dependency tree phải có notice-autoconfigure. Nếu chỉ có notice-spring-boot-starter nhưng không có module này, starter POM chưa đầy đủ.

Mở POM đã cài trong local repository để xem nội dung dependency được phát hành:

~~~text
~/.m2/repository/com/acme/notice/notice-spring-boot-starter/1.0.0/notice-spring-boot-starter-1.0.0.pom
~~~

Trên Windows, thay ~/.m2 bằng %USERPROFILE%\.m2. Kiểm tra dependency có tọa độ đúng và không bị đánh dấu optional ngoài ý muốn.

### 9.3. Auto-configuration JAR có metadata không?

Kiểm tra:

~~~bash
jar tf notice-autoconfigure-1.0.0.jar
~~~

Trong JAR phải có:
- com/acme/notice/autoconfigure/NoticeAutoConfiguration.class
- META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Đọc nội dung imports và xác nhận FQCN đúng. Nếu metadata không có, hãy sửa resource path rồi build/install lại artifact. Consumer sẽ không tự đoán class nào là auto-configuration.

### 9.4. Dùng --debug

Chạy consumer với:

~~~bash
java -jar target/notice-consumer-1.0.0.jar --debug
~~~

Trong Condition Evaluation Report, tìm:
- NoticeAutoConfiguration
- @ConditionalOnProperty
- @ConditionalOnMissingBean

Các trường hợp:
- Cấu hình không xuất hiện trong report: có thể JAR hoặc imports metadata không được nạp.
- Condition property không match: kiểm tra tên property, profile, command line và giá trị thực tế.
- Condition missing-bean không match: ứng dụng hoặc thư viện khác đã cung cấp NoticeClient.
- Cấu hình match nhưng bean không tạo được: đọc BeanCreationException và Caused by.

Positive match chỉ cho biết condition được đáp ứng; nó không chứng minh mọi thao tác của bean nghiệp vụ sẽ thành công.

### 9.5. Không phụ thuộc Actuator khi startup thất bại

Endpoint /actuator/conditions có ích khi context đã khởi động và Actuator được thêm, expose, bảo vệ phù hợp. Nếu context fail trước khi server sẵn sàng, dùng --debug và stack trace. Không coi endpoint là công cụ duy nhất để chẩn đoán.

## 10. Kiểm chứng độc lập mạnh hơn trong CI

Local mvn install chứng minh consumer có thể dùng artifact từ local repository. CI có thể kiểm chứng mạnh hơn bằng cách chia pipeline thành hai job hoặc hai workspace.

~~~text
Pipeline
   |
   +--> Job A: Build library
   |       |
   |       +--> mvn clean verify
   |       +--> package JARs
   |       +--> publish to staging Maven repository
   |
   +--> Job B: Build consumer
           |
           +--> checkout consumer only
           +--> resolve starter from staging repository
           +--> mvn clean test
           +--> package and run smoke test
~~~

Job B chỉ checkout repository consumer; nó không được dùng workspace source của thư viện. Đây là cách phát hiện lỗi mà local reactor có thể che giấu.

Một số lựa chọn:
- Publish snapshot vào repository staging nội bộ.
- Dùng repository tạm trong pipeline.
- Dùng local Maven repository được seed từ artifact build ở job trước.
- Tạo integration test project riêng, nhưng vẫn build từ artifact đã cài thay vì module sibling.

Không nên phát hành release lên repository production chỉ để thử nghiệm. Dùng snapshot hoặc staging repository, sau đó promote artifact đã được kiểm chứng theo quy trình release.

### 10.1. Kiểm tra version và cache

Maven lưu artifact trong local repository. Khi sửa thư viện nhưng giữ nguyên version release 1.0.0, consumer có thể vẫn dùng artifact cũ hoặc cache không như mong đợi.

Trong phát triển:
- Tăng version snapshot như 1.0.1-SNAPSHOT khi đang thay đổi API.
- Chạy lại mvn clean install sau khi sửa.
- Xác nhận POM/JAR được cập nhật ở local repository.
- Có thể dùng mvn -U khi cần cập nhật snapshot hoặc metadata từ remote repository.

Không xóa toàn bộ .m2 một cách tùy tiện. Nếu cần xử lý cache, xác định đúng tọa độ artifact và lý do Maven đang resolve phiên bản cũ.

Với release version bất biến, không nên ghi đè nội dung artifact đã phát hành. Hãy phát hành version mới để consumer có thể tái lập build.

## 11. Các ca kiểm thử nên có cho starter thật

Bài lab kiểm tra default, property disable và user override. Với starter production, nên mở rộng test matrix:

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| Starter có trên classpath, property thiếu | Default behavior đúng với contract |
| Property bật | Bean mặc định được tạo |
| Property tắt | Bean mặc định không được tạo |
| User cung cấp bean thay thế | Auto-configuration back off |
| Dependency tùy chọn thiếu | Integration tương ứng không làm core lỗi |
| Bean nền thiếu | Adapter phụ thuộc bean nền không được tạo |
| Nhiều bean cùng type | @Primary / @Qualifier và điều kiện hoạt động đúng |
| Phiên bản Spring Boot được hỗ trợ | API và condition tương thích |
| Executable JAR | Metadata và dependency được đóng gói đầy đủ |
| Consumer không có source library | Build/test vẫn thành công |

Nếu thư viện có nhiều integration, tạo một consumer test cho từng starter hoặc từng tổ hợp dependency. Không nên chỉ test một starter tổng hợp kéo mọi tính năng vì lỗi dependency optional sẽ khó khoanh vùng.

### 11.1. Test classpath tối thiểu

Có thể dùng FilteredClassLoader của Spring Boot test trong module auto-configuration để giả lập thiếu thư viện tùy chọn. Tuy nhiên, test cần tránh tham chiếu trực tiếp class optional trong signature hoặc annotation của lớp test, nếu không class có thể bị resolve trước khi condition được đánh giá.

Với bài kiểm chứng artifact, một consumer chỉ khai báo core starter là bằng chứng quan trọng rằng optional dependency không bị kéo theo ngoài ý muốn. Có thể bổ sung dependency tree assertion trong CI để kiểm tra điều đó.

### 11.2. Test metadata và behavior

Một integration test tiêu thụ độc lập nên kiểm tra cả:
- Bean có tồn tại trong context.
- Bean có đúng implementation/behavior.
- Property bật/tắt có tác động đúng.
- User override được ưu tiên.
- Consumer không cần import auto-configuration class.

Nếu test chỉ gọi new NoticeClient() trực tiếp, nó không kiểm chứng Spring Boot starter. Nếu test dùng @Import(NoticeAutoConfiguration.class), nó kiểm tra class cấu hình nhưng bỏ qua việc Boot phát hiện metadata trong JAR.

## 12. Những lỗi thường gặp khi kiểm chứng starter

1. **Chạy test trong cùng Maven reactor rồi kết luận starter độc lập.** Reactor có thể resolve module sibling mà không cần artifact đã install.
2. **Consumer dùng source directory của thư viện.** Build thành công nhưng không chứng minh JAR phát hành đầy đủ.
3. **Thiếu AutoConfiguration.imports.** Class có trong JAR nhưng Boot không tự phát hiện.
4. **Sai FQCN trong imports.** Metadata tồn tại nhưng trỏ đến class không có.
5. **Starter quên dependency đến auto-config module.** Consumer nhận core nhưng không có cấu hình để đăng ký bean.
6. **Auto-config quên dependency đến core module.** Consumer không có public API hoặc runtime class cần thiết.
7. **Đánh dấu core dependency là optional.** Consumer có thể không compile được khi import API lõi.
8. **Dùng scope test cho driver hoặc thư viện runtime.** Unit test có thể pass nhưng executable JAR thiếu dependency.
9. **Dùng @Import để sửa bean vắng mặt.** Cách này che giấu lỗi discovery của starter.
10. **Component scan package thư viện.** Cấu hình xuất hiện do scan thay vì imports metadata.
11. **Version giữa thư viện và consumer không tương thích.** Dependency management có thể resolve một Spring Boot version khác với version đã compile.
12. **Chỉ kiểm tra dependency tree.** Dependency có mặt không đảm bảo condition match hoặc bean tạo thành công.
13. **Chỉ kiểm tra bean count.** Cần gọi method/kiểm tra behavior để xác nhận bean đúng.
14. **Không test property tắt.** Starter có thể tạo bean dù người dùng đã yêu cầu disable.
15. **Không test user override.** Bean mặc định có thể cạnh tranh với cấu hình ứng dụng.
16. **Giữ nguyên release version sau khi thay code.** Consumer có thể dùng artifact cũ trong cache.
17. **Chỉ chạy trên IDE.** Runtime classpath của executable JAR hoặc container có thể khác.
18. **Dùng mvn package nhưng chưa install.** Consumer độc lập không resolve được artifact từ local repository nếu chưa có remote repository.
19. **Dùng dependency systemPath.** Làm build phụ thuộc đường dẫn máy cá nhân và phá tính tái lập.
20. **Cho rằng local install chứng minh remote publish.** Install chỉ kiểm tra local repository; remote deploy cần kiểm tra repository, credentials và artifact đã upload.

## 13. Quy trình kiểm chứng chuẩn trước khi phát hành

1. Build tất cả module thư viện bằng mvn clean verify.
2. Cài artifact vào local repository bằng mvn clean install hoặc deploy lên staging repository.
3. Kiểm tra JAR core, auto-config và starter đã được tạo đúng version.
4. Mở auto-config JAR, xác nhận class và AutoConfiguration.imports tồn tại.
5. Kiểm tra nội dung imports chứa đúng FQCN.
6. Tạo/checkout consumer độc lập nằm ngoài reactor.
7. Chỉ khai báo starter theo tọa độ Maven, không tham chiếu source.
8. Chạy mvn dependency:tree để xác nhận core và auto-config là dependency bắc cầu.
9. Chạy mvn clean test trong consumer để kiểm tra default, disable và override.
10. Đóng gói consumer và chạy executable JAR để xác nhận behavior thực tế.
11. Chạy thêm --debug khi condition không như mong đợi.
12. Lặp lại trong CI với consumer checkout độc lập hoặc staging repository trước khi phát hành release.

## 14. Checklist nghiệm thu starter

- [ ] Core module có public API và không phụ thuộc integration không cần thiết.
- [ ] Auto-configuration module phụ thuộc đúng core và Spring Boot.
- [ ] Starter khai báo dependency đến auto-configuration module.
- [ ] Dependency transitively cần cho public API không bị đánh dấu optional ngoài ý muốn.
- [ ] AutoConfiguration.imports nằm đúng đường dẫn trong JAR.
- [ ] FQCN trong imports khớp class thực tế.
- [ ] Thư viện đã được install hoặc publish trước khi build consumer.
- [ ] Consumer nằm ngoài reactor và không dùng source library.
- [ ] Consumer chỉ khai báo starter theo Maven coordinates.
- [ ] Dependency tree có starter, auto-config và core.
- [ ] Consumer không dùng @Import hoặc component scan để nạp auto-configuration.
- [ ] Test xác nhận default, property disable và user override.
- [ ] Executable JAR chạy được và in output mong đợi.
- [ ] Phiên bản Spring Boot và Java tương thích.
- [ ] CI kiểm tra bằng consumer độc lập hoặc repository staging.
- [ ] Release version bất biến; thay đổi được phát hành dưới version mới.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao test trong cùng Maven reactor chưa đủ để chứng minh starter có thể dùng độc lập?  
**Đáp án:** Reactor có thể resolve module sibling từ output build mà không cần artifact đã được install hoặc publish. Consumer độc lập phải resolve bằng Maven coordinates.

**Câu 2.** Class auto-configuration có trong JAR nhưng bean không xuất hiện. Nên kiểm tra gì đầu tiên?  
**Đáp án:** Kiểm tra META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports, vị trí resource và FQCN được ghi trong file.

**Câu 3.** Consumer chỉ khai báo starter nhưng không thấy core API khi compile. Nguyên nhân có thể là gì?  
**Đáp án:** Starter hoặc auto-config không khai báo core dependency đúng cách, hoặc dependency bị đánh dấu optional/scope không phù hợp.

**Câu 4.** Vì sao không dùng @Import(NoticeAutoConfiguration.class) trong consumer test?  
**Đáp án:** Nó bỏ qua cơ chế discovery từ JAR metadata và có thể che lỗi đóng gói starter.

**Câu 5.** mvn install khác mvn deploy thế nào?  
**Đáp án:** install đưa artifact vào local Maven repository; deploy upload artifact lên remote repository đã cấu hình.

**Câu 6.** Dependency tree có starter và auto-config nhưng bean vẫn không tạo. Cần kiểm tra gì?  
**Đáp án:** Condition Evaluation Report, property, classpath, bean nền, @ConditionalOnMissingBean và exception khi tạo bean.

**Câu 7.** Vì sao cần test property disable và user override từ consumer?  
**Đáp án:** Chúng xác nhận hợp đồng công khai hoạt động trong ứng dụng thật, không chỉ trong test nội bộ của thư viện.

## 16. Tài liệu tham khảo chính thức

- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
- [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).
- [Spring Boot Javadoc — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html).
- [Spring Boot Javadoc — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html).
- [Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html).
- [Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html).