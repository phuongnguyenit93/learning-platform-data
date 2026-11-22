# Context khởi tạo nhiều lần hoặc bootstrap bean bị component scan nhầm

Khi bật Spring Cloud, log có thể cho thấy nhiều ApplicationContext được tạo, một bean cấu hình xuất hiện ở nhiều nơi hoặc ứng dụng gọi Config Server nhiều lần trong lúc khởi động. Những dấu hiệu này trông giống nhau nhưng có thể đến từ các cơ chế khác nhau. Cần xác định đó là cây context có chủ đích, một lần nạp cấu hình theo nhiều giai đoạn hay một cấu hình bị đăng ký lặp trước khi thay đổi dependency hoặc tắt bootstrap.

Bài này tập trung vào hai lỗi thường gặp: nhầm bootstrap context với một lần khởi động ứng dụng thứ hai, và đặt lớp cấu hình bootstrap trong package mà component scan của ứng dụng chính quét tới.

## 1. Phân biệt bootstrap context và application context

ApplicationContext là container quản lý bean, cấu hình và vòng đời của một phần ứng dụng Spring. Một ứng dụng có thể có nhiều context trong cùng một tiến trình. Với cơ chế bootstrap truyền thống của Spring Cloud, cây context thường có dạng:

~~~mermaid
flowchart TD
    B["Bootstrap context<br/>nạp cấu hình bên ngoài"]
    A["Main application context<br/>web, service, repository"]
    B -->|"parent"| A
~~~

Bootstrap context là context cha, được tạo để nạp property source từ nguồn bên ngoài và chuẩn bị các thành phần cần thiết trước khi main application context chạy. Context con có thể tra cứu bean ở context cha. Nếu hai context cùng có bean trùng tên, bean cục bộ của context con được ưu tiên khi tra cứu từ context con; hai bean vẫn thuộc hai BeanFactory riêng biệt.

Vì vậy, nhìn thấy hai context trong log chưa đủ để kết luận ứng dụng bị khởi tạo hai lần. Hãy kiểm tra quan hệ parent-child và mục đích của từng context. Một bootstrap context cùng một main context là cấu trúc hợp lệ khi ứng dụng bật cơ chế bootstrap cũ.

Spring Cloud cho phép đăng ký lớp cấu hình bootstrap qua file META-INF/spring.factories với key org.springframework.cloud.bootstrap.BootstrapConfiguration. Những lớp này được dùng để tạo bootstrap context. Bean được khai báo ở đó có thể được context ứng dụng chính sử dụng thông qua quan hệ cha-con.

## 2. Vì sao bootstrap bean có thể xuất hiện hai lần?

### 2.1. Package bootstrap nằm trong vùng component scan

Đây là lỗi cần kiểm tra đầu tiên khi một lớp cấu hình được nạp qua BootstrapConfiguration nhưng đồng thời nằm dưới package gốc của lớp có @SpringBootApplication.

Ví dụ cấu trúc dễ gây nhầm lẫn:

~~~text
com.acme.orders
├── OrdersApplication.java
├── service/
└── bootstrap/
    └── RemoteBootstrapConfiguration.java
~~~

~~~java
package com.acme.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

@SpringBootApplication bao gồm hành vi component scan với package của lớp ứng dụng làm package gốc mặc định. Vì RemoteBootstrapConfiguration nằm trong com.acme.orders.bootstrap, component scan của main context có thể phát hiện lớp này. Trong khi đó, Spring Cloud cũng nạp nó vào bootstrap context qua metadata. Kết quả là cùng một lớp cấu hình có thể tạo bean trong cả context cha và context con.

Hậu quả phụ thuộc vào loại bean và cách ứng dụng tra cứu chúng:

- Một bean có thể được khởi tạo ở cả hai context, khiến constructor, @PostConstruct hoặc thao tác mở kết nối chạy nhiều lần.
- Bean cùng tên trong context con có thể che khuất bean cùng tên ở context cha khi tra cứu từ context con.
- Nếu hai cấu hình cùng đăng ký bean trong một BeanFactory, ứng dụng có thể gặp lỗi trùng bean definition; hành vi cho phép ghi đè còn phụ thuộc cấu hình Spring Boot.
- Các thành phần chỉ nên chạy trong giai đoạn bootstrap có thể bị khởi tạo thêm trong vòng đời ứng dụng chính.

Không phải mọi bean xuất hiện ở cả hai context đều là lỗi. Hãy xác định bean nào cần tồn tại ở bootstrap context, bean nào thuộc ứng dụng chính và side effect nào thực sự bị lặp.

### 2.2. Ứng dụng chủ động tạo nhiều context

Kiểm tra các điểm gọi SpringApplication.run và SpringApplicationBuilder. Những tình huống sau có thể tạo nhiều context:

- Có hơn một entry point gọi SpringApplication.run cho cùng ứng dụng.
- Một cấu hình tự tạo context mới thay vì nhận bean từ context hiện tại.
- SpringApplicationBuilder khai báo parent, child hoặc sibling để chia ứng dụng thành các context có vòng đời riêng.
- Test khởi động nhiều application context, hoặc đóng và tạo lại context theo cấu hình kiểm thử.

Context cha-con hoặc sibling có thể là thiết kế hợp lệ. Chỉ sửa khi việc tạo context không có chủ đích hoặc khiến một tài nguyên bị đăng ký nhiều lần.

### 2.3. Phân biệt refresh với khởi động lại

Spring Cloud Context có cơ chế refresh cấu hình và bean. Endpoint /actuator/refresh có thể nạp lại bootstrap context và làm mới các bean thuộc @RefreshScope; thao tác này không đồng nghĩa toàn bộ main application context đã được tạo lại. Endpoint /actuator/restart có hành vi đóng rồi khởi động lại ApplicationContext và bị tắt mặc định. Nếu log cho thấy refresh hoặc restart, hãy xác định endpoint hay listener nào đã kích hoạt hành động đó trước khi tìm lỗi component scan.

### 2.4. Nhiều request cấu hình không đồng nghĩa nhiều lần khởi tạo context

Spring Boot Config Data có thể gọi Config Server ở nhiều bước. Tài liệu Spring Cloud Config giải thích rằng client trước tiên tải cấu hình với profile mặc định để xác định profile được kích hoạt, sau đó tải tiếp cấu hình cho các profile đang hoạt động. Do đó, hai hoặc nhiều request lấy cấu hình trong startup có thể là hành vi bình thường.

Từ Spring Cloud 2022.0.3, PropertySourceLocator cũng được gọi hai lần theo quy trình profile: lần đầu không có profile, lần sau sau khi main context đã khởi động với các profile đang hoạt động. Đây là số lần tìm property source, không phải bằng chứng rằng toàn bộ ứng dụng đã tạo hai main context.

## 3. Kiểm tra theo thứ tự

### Bước 1: Xác nhận số context và quan hệ cha-con

Đừng chỉ đếm dòng log có chữ “Starting”. Hãy ghi lại ID, kiểu lớp và parent của từng context. Có thể dùng đoạn chẩn đoán trong một test hoặc một điểm kiểm tra tạm thời:

~~~java
import org.springframework.context.ApplicationContext;

final class ContextDiagnostics {
    static void printContextHierarchy(ApplicationContext context) {
        ApplicationContext current = context;

        while (current != null) {
            ApplicationContext parent = current.getParent();
            String parentId = parent == null ? "<none>" : parent.getId();

            System.out.printf(
                "contextId=%s, type=%s, parentId=%s%n",
                current.getId(),
                current.getClass().getName(),
                parentId
            );

            current = parent;
        }
    }
}
~~~

Nếu thấy một bootstrap context làm parent của main context, hãy kiểm tra xem ứng dụng có chủ đích bật bootstrap hay không. Nếu thấy nhiều main context độc lập, tìm nơi gọi SpringApplication.run, SpringApplicationBuilder hoặc nơi tạo context trong test.

### Bước 2: Tìm nguồn đăng ký bootstrap configuration

Tìm toàn bộ khai báo BootstrapConfiguration trong META-INF/spring.factories của ứng dụng và các dependency nội bộ. Với mỗi lớp được khai báo:

1. Xác định package của lớp cấu hình.
2. Xác định package gốc của @SpringBootApplication và mọi scanBasePackages hoặc @ComponentScan tùy chỉnh.
3. Kiểm tra lớp bootstrap có nằm trong vùng quét của main context không.
4. Kiểm tra lớp có bị đăng ký thêm qua @Import hoặc một cấu hình khác không.
5. Xác định bean được tạo trong context nào và có side effect lúc khởi tạo hay không.

Có thể bật log chi tiết trong lúc điều tra:

~~~yaml
logging:
  level:
    org.springframework.cloud.bootstrap: DEBUG
    org.springframework.context.annotation: TRACE
    org.springframework.boot.context.config: DEBUG
~~~

Tên logger và mức log hữu ích có thể thay đổi theo phiên bản. Chỉ bật TRACE trong môi trường phát triển vì log component scan có thể rất nhiều.

### Bước 3: Kiểm tra cơ chế nạp cấu hình đang được dùng

Đọc dependency và các thuộc tính khởi động để xác định ứng dụng đang dùng Config Data hay legacy bootstrap. Tập trung vào:

- spring.config.import trong application.yml hoặc application.properties.
- Dependency spring-cloud-starter-bootstrap.
- spring.cloud.bootstrap.enabled được truyền qua system property hoặc biến môi trường.
- File bootstrap.yml/bootstrap.properties và spring.cloud.config.uri.
- Các lớp PropertySourceLocator và metadata BootstrapConfiguration.

Đừng kết luận ứng dụng có hai context chỉ từ việc Config Server nhận nhiều request. Đối chiếu request với log context và profile được tải.

## 4. Cách sửa

### 4.1. Tách package bootstrap khỏi package ứng dụng

Đặt lớp cấu hình bootstrap bên ngoài vùng quét của ứng dụng chính. Ví dụ, nếu package gốc của ứng dụng là com.acme.orders, có thể đặt cấu hình bootstrap trong com.acme.cloudbootstrap:

~~~text
com.acme
├── orders
│   ├── OrdersApplication.java
│   └── service/
└── cloudbootstrap
    └── RemoteBootstrapConfiguration.java
~~~

Đăng ký lớp đó trong META-INF/spring.factories:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.acme.cloudbootstrap.RemoteBootstrapConfiguration
~~~

Lớp cấu hình có thể khai báo PropertySourceLocator hoặc các bean thực sự cần cho bootstrap:

~~~java
package com.acme.cloudbootstrap;

import java.util.Map;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

@Configuration(proxyBeanMethods = false)
public class RemoteBootstrapConfiguration {

    @Bean
    PropertySourceLocator remotePropertySourceLocator() {
        return environment -> new MapPropertySource(
            "remoteDefaults",
            Map.of("feature.example.enabled", true)
        );
    }
}
~~~

Ví dụ trên minh họa vị trí và cơ chế đăng ký; trong ứng dụng thật, thay MapPropertySource bằng nguồn cấu hình phù hợp và tránh đặt secret trong mã nguồn. Nếu ứng dụng dùng scanBasePackages rộng hơn com.acme.orders, hãy kiểm tra lại phạm vi đó: package com.acme.cloudbootstrap vẫn có thể bị quét nếu package gốc là com.acme.

Một lựa chọn khác là thu hẹp component scan về package ứng dụng cần quản lý hoặc dùng exclude filter có chủ đích. Tránh quét từ package quá rộng như com hoặc org vì có thể kéo nhiều cấu hình ngoài phạm vi vào context.

### 4.2. Chọn đúng cách nạp cấu hình Config Server

Với Spring Boot 2.4 trở lên, Config Data qua spring.config.import là cách tích hợp Config Server mặc định. Ví dụ:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: "optional:configserver:"
~~~

Có thể chỉ rõ địa chỉ server trong import:

~~~yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
~~~

Tiền tố optional cho phép ứng dụng tiếp tục khởi động nếu Config Server không truy cập được. Nếu cấu hình từ server là bắt buộc, bỏ optional để startup thất bại khi không tải được cấu hình. Cách Config Data không cần file bootstrap.yml.

Nếu hệ thống vẫn cần legacy bootstrap, bật cơ chế này bằng dependency spring-cloud-starter-bootstrap hoặc bằng system property/biến môi trường. Ví dụ:

~~~bash
java -Dspring.cloud.bootstrap.enabled=true -jar orders-service.jar
~~~

Khi đó, cấu hình kết nối Config Server thường được đặt trong bootstrap.yml:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    config:
      uri: http://localhost:8888
~~~

Hãy chọn cơ chế phù hợp với kiến trúc và phiên bản đang chạy. Nếu đã dùng Config Data, không thêm legacy bootstrap chỉ để xử lý log có nhiều request. Nếu cần giữ bootstrap cũ, xác nhận property được đặt đủ sớm qua system property, biến môi trường hoặc starter.

### 4.3. Chỉ tạo main context một lần

Giữ một điểm vào khởi động rõ ràng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Không gọi SpringApplication.run từ bean, static initializer, ApplicationRunner hoặc mỗi lần xử lý request. Nếu cần nhiều context, khai báo quan hệ parent/child/sibling tường minh bằng SpringApplicationBuilder và ghi rõ context nào sở hữu bean, executor, scheduler, connection pool hoặc listener.

### 4.4. Tránh sửa triệu chứng bằng cách tắt bean override

Không bật cho phép ghi đè bean chỉ để ứng dụng khởi động qua lỗi trùng definition. Việc này có thể che mất nguyên nhân cấu hình được nạp hai lần và khiến bean thắng cuộc phụ thuộc thứ tự đăng ký. Hãy loại bỏ đường đăng ký thừa hoặc thu hẹp component scan trước; chỉ dùng override khi đó là quyết định thiết kế có chủ đích và đã kiểm tra bean cuối cùng được sử dụng.

## 5. Đọc kết quả chẩn đoán

| Dấu hiệu | Diễn giải có khả năng | Hướng kiểm tra |
|---|---|---|
| Có bootstrap context làm parent của main context | Legacy bootstrap đang hoạt động | Kiểm tra starter, system property và nhu cầu dùng bootstrap |
| Cùng lớp bootstrap xuất hiện trong metadata và component scan | Cấu hình bị nạp ở hai context | Chuyển package ra ngoài vùng scan hoặc thu hẹp scan |
| Một bean có cùng tên ở parent và child | Bean được đăng ký riêng ở hai BeanFactory | Xác định bean nào nên tồn tại ở mỗi context; kiểm tra bean con có che khuất bean cha |
| Config Server nhận request với profile mặc định rồi profile đang hoạt động | Config Data đang giải quyết cấu hình theo nhiều giai đoạn | Đối chiếu profile và log Config Data; không coi đây là hai lần tạo main context |
| Nhiều main context độc lập có ID khác nhau | Có thể có nhiều điểm khởi động hoặc thiết kế context hierarchy | Tìm các lời gọi run/build, cấu hình test và nơi tạo context |
| Lỗi tương thích xuất hiện sau khi nâng cấp | Spring Boot và Spring Cloud có thể thuộc hai thế hệ không tương thích | Kiểm tra release train và BOM trước khi điều chỉnh bootstrap |

## 6. Lưu ý theo phiên bản

- Spring Boot 2.4 giới thiệu Config Data và spring.config.import. Với Spring Cloud Config Client hiện đại, đây là cách nạp cấu hình mặc định; bootstrap.yml không cần thiết cho luồng này.
- Legacy bootstrap vẫn có thể được bật tường minh bằng spring-cloud-starter-bootstrap hoặc spring.cloud.bootstrap.enabled=true. Với cơ chế này, cần phân biệt bootstrap context cha với main context con.
- Từ Spring Cloud 2022.0.3, PropertySourceLocator được gọi hai lần để hỗ trợ xác định profile từ cấu hình bên ngoài. Nếu thấy nhiều lần lấy property source, hãy kiểm tra đúng luồng này trước khi kết luận context bị tạo lại.
- Trước Spring Cloud 2022.0.3, PropertySourceLocator mặc định chạy trong main application context. Tài liệu Spring Cloud nêu thuộc tính spring.cloud.config.initialize-on-context-refresh=true trong bootstrap configuration để yêu cầu chạy ở bootstrap context.
- Spring Cloud Release Train phải tương thích với thế hệ Spring Boot. Ví dụ, bảng tương thích của Spring Cloud ghi Boot 3.3.x thuộc train 2023.0.x từ 2023.0.2; đây là thông tin mapping theo train, không thay thế việc kiểm tra service release và trạng thái hỗ trợ hiện tại. Dùng Spring Cloud BOM thay vì tự ghim phiên bản rời rạc cho từng module.
- Cơ chế đăng ký BootstrapConfiguration qua spring.factories là contract riêng của Spring Cloud bootstrap. Không thay key này bằng metadata auto-configuration của Spring Boot một cách máy móc; hai cơ chế có mục đích khác nhau.

## 7. Checklist xử lý sự cố

1. Ghi lại ID và parent của từng ApplicationContext.
2. Phân biệt bootstrap context, main context và các context do test hoặc SpringApplicationBuilder tạo.
3. Tìm mọi BootstrapConfiguration trong META-INF/spring.factories.
4. So sánh package của bootstrap configuration với package gốc và scanBasePackages của @SpringBootApplication.
5. Kiểm tra bean trùng tên, nơi khai báo bean và side effect khi khởi tạo.
6. Xác định Config Data hay legacy bootstrap đang được bật.
7. Đối chiếu số request Config Server với profile và hành vi PropertySourceLocator của release train.
8. Xác minh Spring Boot/Spring Cloud bằng BOM và bảng tương thích chính thức.
9. Khởi động lại một lần trong môi trường phát triển và xác nhận mỗi bean có side effect chỉ được tạo ở context dự kiến.

## Tài liệu chính thức

- [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): bootstrap context, context hierarchy và lưu ý tách package cho BootstrapConfiguration.
- [Spring Cloud Config — Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data, spring.config.import và legacy config-first bootstrap.
- [Spring Boot — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html): vị trí lớp ứng dụng và phạm vi component scan.
- [Spring Cloud — Project and Release Train Compatibility](https://spring.io/projects/spring-cloud/): bảng tương thích Spring Boot và Spring Cloud.
