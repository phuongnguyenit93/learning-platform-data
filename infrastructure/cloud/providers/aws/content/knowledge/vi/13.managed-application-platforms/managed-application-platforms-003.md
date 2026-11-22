# Triển khai Java trên Elastic Beanstalk

> **Chương:** Nền tảng ứng dụng quản lý  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hạ tầng AWS từ Region/Availability Zone (AZ), IAM, VPC đến compute, storage, database, tích hợp và serverless; luyện kỹ năng chọn dịch vụ, xây dựng ứng dụng an toàn, quan sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **AWS Elastic Beanstalk** quản lý những phần nào khi triển khai một ứng dụng Java, đồng thời phân biệt **application**, **application version**, **environment** và **platform**.
2. Lựa chọn đúng giữa **Java SE platform** cho ứng dụng Java/Spring Boot chạy bằng executable JAR và **Tomcat platform** cho ứng dụng đóng gói WAR.
3. Xây dựng, kiểm thử và đóng gói một dịch vụ Spring Boot bằng Maven, tạo **Procfile**, cấu hình port, health check và source bundle tương thích với môi trường Elastic Beanstalk.
4. Thực hiện được quy trình triển khai bằng **EB CLI** trong một môi trường lab được cấp quyền; hiểu sự khác biệt giữa tạo môi trường, triển khai phiên bản, cập nhật cấu hình và xóa môi trường.
5. Thiết kế kiến trúc có **ALB, EC2 Auto Scaling, VPC, IAM roles, CloudWatch**, database độc lập và HTTPS để đạt khả năng vận hành phù hợp.
6. So sánh các **deployment policies**, rolling/immutable/traffic splitting, blue-green và chiến lược rollback.
7. Phân tích sức khỏe ứng dụng, lỗi Java, proxy 502/504, permission, dependency database, giới hạn quy mô và tổng chi phí.
8. Sử dụng AWS CLI ở chế độ chỉ đọc để truy vết **environment health, events, application versions, configuration** và tài nguyên liên quan.

## 1. AWS Elastic Beanstalk giải quyết bài toán gì?

Giả sử nhóm phát triển có một dịch vụ Java Spring Boot chạy bằng lệnh:

~~~bash
java -jar orders-api.jar
~~~

Ở máy cá nhân, việc chạy JAR tương đối đơn giản. Nhưng để công bố dịch vụ cho người dùng thật, nhóm còn phải giải quyết:

- Cấp máy chủ và cài Java runtime phù hợp.
- Cấu hình VPC, subnet, Security Group, routing và load balancer.
- Triển khai phiên bản, khởi động/tự khởi động lại tiến trình.
- Thu thập logs, theo dõi health và xử lý lỗi.
- Tăng/giảm năng lực theo traffic.
- Quản lý HTTPS, quyền IAM, secrets và kết nối database.
- Cập nhật runtime/OS và chuẩn bị rollback.

**AWS Elastic Beanstalk (EB)** là dịch vụ triển khai và vận hành ứng dụng thuộc mô hình **Platform as a Service (PaaS)**. Bạn cung cấp **mã nguồn hoặc artifact đã đóng gói** và chọn một **platform** được AWS hỗ trợ; Elastic Beanstalk giúp tạo và phối hợp các tài nguyên AWS cần thiết cho environment.

~~~mermaid
flowchart TB
    DEV["Developer / CI pipeline"] -->|"Source bundle / application version"| EB["Elastic Beanstalk"]
    EB --> CFN["AWS CloudFormation stack"]
    CFN --> EC2["EC2 instances / Auto Scaling"]
    CFN --> ALB["Elastic Load Balancer nếu có"]
    CFN --> SG["Security Groups / VPC resources"]
    CFN --> MON["CloudWatch / enhanced health"]
    USER["Client"] -->|"HTTPS"| ALB
    ALB -->|"HTTP tới Java process qua proxy"| EC2
~~~

Đây là sơ đồ logic cho **load-balanced web environment**. Single-instance environment không nhất thiết có ALB. EB tạo và quản lý tài nguyên nhưng **không thay thế trách nhiệm của nhóm đối với bảo mật ứng dụng, dữ liệu và ngân sách**.

### 1.1. Những gì Elastic Beanstalk giúp tự động hóa

| Lớp | Elastic Beanstalk hỗ trợ | Nhóm phát triển vẫn chịu trách nhiệm |
| --- | --- | --- |
| **Provisioning** | Điều phối EC2, Auto Scaling, load balancer và tài nguyên liên quan theo environment. | Chọn instance class, cấu hình network/HA, quota và giới hạn chi phí. |
| **Platform runtime** | Cung cấp platform branch/Java runtime và cơ chế triển khai tương ứng. | Chọn phiên bản được hỗ trợ, cập nhật dependency và kiểm thử tương thích. |
| **Deployment** | Quản lý application versions, phân phối artifact, tiến trình triển khai. | Build/test artifact, migrations, rollback và kiểm soát release. |
| **Scaling** | Cấu hình EC2 Auto Scaling cho load-balanced environment. | Đo tải, chọn metric/ngưỡng, thiết kế ứng dụng stateless. |
| **Health/monitoring** | Basic/enhanced health, events, log integration theo cấu hình. | Tạo readiness endpoint, đặt alarms, điều tra root cause. |
| **Security** | Tạo/gắn một số role/SG và các resources được cấu hình. | IAM least privilege, HTTPS, data encryption, secrets, network isolation. |
| **Persistence** | Có thể kết nối các dịch vụ lưu trữ và database AWS. | Chọn nơi lưu dữ liệu bền vững, backup, phục hồi và quyền sở hữu dữ liệu. |

### 1.2. Beanstalk không phải “serverless” theo nghĩa không còn EC2

Elastic Beanstalk **không biến mọi workload thành Lambda hoặc Fargate**. Với Java SE/Tomcat web environment thông thường, ứng dụng vẫn chạy trên **EC2 instances** thuộc environment; EB quản lý việc phối hợp hạ tầng nhưng chi phí EC2, load balancer và các tài nguyên vẫn được tính theo dịch vụ gốc.

Nếu muốn triển khai container mà không quản lý instance theo mô hình ECS Fargate, hãy đánh giá **Amazon ECS/Fargate**, **AWS App Runner** hoặc lựa chọn phù hợp. EB có platform Docker, nhưng bài này tập trung vào Java SE/Tomcat.

## 2. Những thành phần cần phân biệt

### 2.1. Application

**Application** là ranh giới logic tập hợp các **application versions** và **environments** cùng một sản phẩm hoặc hệ thống.

Ví dụ application có tên **orders-api**, gồm:

- Environment **orders-dev**.
- Environment **orders-staging**.
- Environment **orders-prod**.

Mỗi environment có cấu hình, URL, tập tài nguyên và phiên bản đang chạy riêng. Cùng một application version có thể được triển khai vào nhiều environment để kiểm thử theo thứ tự.

### 2.2. Application version

**Application version** đại diện cho một phiên bản có thể triển khai: một source bundle hoặc artifact tham chiếu tới object ở S3, cùng **VersionLabel**.

Ví dụ:

~~~text
Application: orders-api
VersionLabel: orders-api-1.4.2-build138
Source bundle: s3://managed-artifacts-bucket/orders-api/1.4.2.zip
~~~

Đây là đường dẫn minh họa; EB có thể quản lý bucket artifact theo tên và quy trình của dịch vụ. **VersionLabel** giúp phân biệt bản build, nhưng không bảo đảm ứng dụng bên trong artifact đã được test tốt hoặc không có secret.

### 2.3. Environment

**Environment** là một lần triển khai ứng dụng đang được vận hành, gồm những tài nguyên như EC2, Auto Scaling group, ELB và cấu hình dịch vụ.

Phân biệt:

- **Web server environment:** nhận HTTP/HTTPS requests, có thể đặt sau load balancer.
- **Worker environment:** xử lý tác vụ bất đồng bộ, có cơ chế tích hợp Amazon SQS do platform/worker tier hỗ trợ; không nên coi worker environment tự có cùng đường xử lý HTTP public như web tier.

Bài này triển khai Java API trên **web server environment**. Nếu ứng dụng Java là batch worker, cần chọn tier và đường xử lý message phù hợp.

### 2.4. Platform branch và platform version

Một environment phải chọn **platform** cho Java, chẳng hạn Java SE trên Amazon Linux 2023 hoặc Tomcat trên một phiên bản Amazon Linux được AWS hỗ trợ.

- **Platform branch** mô tả nhánh công nghệ/runtime/OS, ví dụ Java trên một dòng Amazon Linux cụ thể.
- **Platform version** là một bản phát hành cụ thể của nhánh đó.
- **Supported branch** và các runtime Corretto được hỗ trợ có thể thay đổi theo thời gian; kiểm tra danh mục platform chính thức ở Region sử dụng.
- Không nên ghim phiên bản OS/runtime đã cũ chỉ vì một hướng dẫn học tập từng dùng nó.

**AWS cung cấp runtime/platform**, nhưng bạn vẫn phải kiểm tra application dependencies, Spring Boot/Java compatibility, database drivers và hành vi ứng dụng khi nâng nền tảng.

## 3. Chọn Java SE hay Tomcat?

### 3.1. Hai con đường triển khai phổ biến

| Tiêu chí | **Java SE platform** | **Tomcat platform** |
| --- | --- | --- |
| Kiểu ứng dụng | Java process chạy độc lập, thường là **executable JAR**. | Web application kiểu servlet container, thường là **WAR**. |
| Spring Boot | Rất phổ biến với **embedded Tomcat/Jetty/Undertow** trong JAR. | Có thể đóng gói Spring Boot thành WAR cho external Tomcat khi cấu hình đúng. |
| Server HTTP | Do chính ứng dụng Java khởi chạy. | Do Tomcat do platform quản lý tiếp nhận và triển khai WAR. |
| Artifact | JAR và **Procfile** theo cách deployment. | WAR, hoặc source bundle chứa WAR(s)/cấu hình theo platform. |
| Kiểm soát startup | Procfile, app arguments, environment variables, hook hỗ trợ. | Tomcat/server settings, ứng dụng servlet và cấu hình platform. |
| Ứng dụng phù hợp | Spring Boot microservice, Dropwizard, Java service độc lập. | Ứng dụng Servlet/JSP truyền thống, WAR cần Tomcat do platform cung cấp. |
| Rủi ro thường gặp | Sai port, sai JAR path, không có startup command. | Servlet compatibility, WAR context path, Jakarta vs javax, container version mismatch. |

**Khuyến nghị cho Spring Boot REST API mới:** bắt đầu bằng **Java SE + executable JAR**, vì workflow build/run đơn giản và app tự sở hữu embedded HTTP server. Nếu hệ thống đã được đóng gói WAR và phụ thuộc external Tomcat, chọn **Tomcat platform** phù hợp.

### 3.2. Chọn Java runtime phù hợp

Ví dụ dự án sử dụng **Java 17** và **Spring Boot 3.x**:

- Chọn Elastic Beanstalk **Java SE platform** có Amazon Corretto 17 được hỗ trợ.
- Kiểm tra project thực sự compile ra bytecode tương thích Java 17.
- Không chọn runtime Java 11 cho artifact đã build bằng Java 17.
- Nếu dùng **Java 21** hoặc phiên bản khác, chọn branch Corretto tương ứng được AWS hỗ trợ tại thời điểm triển khai.

Thông báo điển hình của sai runtime:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
~~~

Đây là vấn đề **Java bytecode/runtime compatibility**, không giải quyết bằng cách tăng số EC2 instances hoặc mở Security Group.

### 3.3. Spring Boot 3 và các ứng dụng Java cũ

Spring Boot 3.x sử dụng **Jakarta EE namespaces** cho nhiều API servlet, trong khi ứng dụng Java cũ có thể còn dùng **javax.servlet**. Khi chọn Tomcat platform cho WAR, phải kiểm tra Tomcat major version và namespace compatibility; không chỉ đổi file extension JAR thành WAR.

Các ứng dụng Spring MVC/Servlet cũ nên có **migration plan** và regression tests trước khi nâng platform/runtime trong production.

## 4. Kiến trúc triển khai Java web application

Một thiết kế production phổ biến:

~~~mermaid
flowchart TB
    CLIENT["Client / Browser"] --> R53["Route 53: api.example.com"]
    R53 --> ALB["ALB HTTPS 443 / ACM"]
    subgraph VPC["Amazon VPC"]
      subgraph PUB["Public subnets — nhiều AZ"]
        ALB
      end
      subgraph PRIVATE["Private app subnets — nhiều AZ"]
        A1["EC2 Java app A"]
        A2["EC2 Java app B"]
      end
      subgraph DATA["Private database subnets"]
        DB[("Amazon RDS / database")]
      end
      ALB -->|"HTTP/HTTPS phù hợp, SG"| A1
      ALB -->|"HTTP/HTTPS phù hợp, SG"| A2
      A1 -->|"DB traffic"| DB
      A2 -->|"DB traffic"| DB
    end
    EB["Elastic Beanstalk environment"] -.->|"Quản lý deployment, ASG, cấu hình"| A1
    EB -.->|"Quản lý deployment, ASG, cấu hình"| A2
    CW["CloudWatch metrics và logs"] <-->|"Telemetry"| EB
~~~

Sơ đồ thể hiện **ALB ở public subnets**, EC2 app ở private subnets và database tách biệt. Đây là **phương án thiết kế tham khảo**, không có nghĩa mọi môi trường EB tự động tạo đúng topology này. Cần chọn đúng VPC, subnet, ELB scheme và Security Groups.

### 4.1. Single-instance và load-balanced environment

| Khía cạnh | Single-instance | Load-balanced |
| --- | --- | --- |
| EC2 instances | Thường một instance. | Một hoặc nhiều instances trong ASG. |
| Load balancer | Thường không có. | Có ELB phù hợp, thường ALB cho HTTP/HTTPS. |
| Tự động scale số instance | Không như topology load-balanced. | Có thể cấu hình Auto Scaling theo tải. |
| Khả dụng khi EC2 lỗi | Gián đoạn trong thời gian thay thế/phục hồi. | Có thể duy trì nếu còn healthy targets và phân bố AZ đúng. |
| Chi phí | Thường thấp hơn ở lab do không có ELB. | Chi phí ELB và nhiều EC2, có thể cao hơn. |
| Tình huống | Dev, thử nghiệm, bài thực hành giới hạn tải. | Staging/production có yêu cầu HA và tải thay đổi. |

**Single-instance không phải cách triển khai HA production mặc định.** Load-balanced cũng không tự đảm bảo HA nếu ASG min chỉ một instance hoặc tất cả instances cùng ở một AZ.

### 4.2. Reverse proxy và port của Java process

Trên Java SE Amazon Linux hiện đại, EB thường chạy **Nginx reverse proxy** phía trước Java app:

~~~mermaid
flowchart LR
    U["Client"] -->|"HTTPS :443"| ALB["ALB"]
    ALB -->|"HTTP :80"| NGINX["Nginx trên EC2"]
    NGINX -->|"HTTP localhost :5000"| JVM["Spring Boot Java process"]
~~~

Đây là **luồng điển hình với cấu hình mặc định**; ports, HTTPS giữa ALB và instance, Nginx settings có thể tùy chỉnh tùy platform.

- ALB có thể kết thúc TLS với certificate từ **AWS Certificate Manager (ACM)**.
- Nginx tiếp nhận traffic trên instance và reverse-proxy tới Java process.
- Ứng dụng cần **lắng nghe cổng mà Nginx được cấu hình chuyển tiếp tới**, phổ biến là **5000** trên Java SE platform.
- Nếu app vẫn mặc định **8080**, trong khi proxy chuyển tới 5000, health checks có thể lỗi và client nhận **502 Bad Gateway**.
- Không nên cố sửa bằng cách mở cổng backend ra Internet khi vấn đề là cấu hình proxy/process mismatch.

### 4.3. Trạng thái ứng dụng cần tách khỏi EC2

EC2 instances của Beanstalk có thể được **thay thế khi deploy, scale hoặc cập nhật platform**. Vì vậy:

- Không coi thư mục **/tmp**, ổ filesystem trên instance hoặc file log cục bộ là nơi lưu dữ liệu lâu dài duy nhất.
- Dùng **S3** cho ảnh/tệp upload, **RDS/Aurora** cho dữ liệu giao dịch, **ElastiCache** hoặc kho phù hợp cho session/cache khi cần.
- Thiết kế Java service **stateless**, hoặc đưa session state ra hệ thống có thể chia sẻ.
- Mọi task nền có side effect phải có cơ chế idempotency/checkpoint nếu instances được thay thế.

## 5. Tạo ứng dụng Java Spring Boot để triển khai

Ta xây dựng một REST API tối giản với:

- Java 17.
- Spring Boot 3.x.
- Maven.
- Spring Boot Actuator để có endpoint health.
- Executable JAR chạy trên Java SE platform.

### 5.1. Cấu trúc dự án

~~~text
orders-api/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/orders/
│   │   │       ├── OrdersApplication.java
│   │   │       └── StatusController.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       └── java/
└── .gitignore
~~~

File **Procfile** sẽ được đặt **ở root của source bundle** dùng triển khai, cùng executable JAR, không nhất thiết phải nằm trong thư mục src của dự án.

### 5.2. Maven POM ví dụ

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>orders-api</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
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

**Lưu ý:** Spring Boot version **3.5.0** ở ví dụ chỉ là một phiên bản minh họa đã được phát hành; với ứng dụng thật nên chọn **bản vá đang được hỗ trợ** và kiểm tra CVE/dependencies/runtime compatibility trước khi deploy.

### 5.3. Java source code

**OrdersApplication.java**

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

**StatusController.java**

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {
    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of(
            "service", "orders-api",
            "status", "ok"
        );
    }

    @GetMapping("/api/status")
    public Map<String, String> status() {
        return Map.of(
            "status", "ok",
            "at", Instant.now().toString()
        );
    }
}
~~~

**application.properties**

~~~properties
spring.application.name=orders-api

# Java SE/Nginx mặc định thường chuyển tiếp tới cổng 5000.
# Nếu phải dùng cổng khác, điều chỉnh proxy/platform tương ứng.
server.port=5000

# Chỉ công khai những actuator endpoints thực sự cần thiết.
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
~~~

Endpoints minh họa:

~~~text
GET /                 -> JSON với tên dịch vụ và status
GET /api/status       -> JSON status và timestamp
GET /actuator/health  -> health response cho readiness cơ bản
~~~

Không nên để endpoint health trả thông tin nhạy cảm như database password, environment variables, private IP hoặc stack trace. Nếu cần readiness phản ánh database và downstream, phải kiểm soát timeout để health endpoint không trở thành nguồn tải hoặc gây cascading failures.

### 5.4. Kiểm tra và build ở máy phát triển/CI

~~~bash
# Trong thư mục dự án có Maven wrapper; nếu không có, dùng mvn.
./mvnw --version

# Kiểm thử và tạo executable Spring Boot JAR.
./mvnw clean verify

# Xem artifact sau build.
ls -lh target/*.jar

# Kiểm tra local với đúng port.
java -jar target/orders-api-0.0.1-SNAPSHOT.jar
~~~

Trong terminal khác:

~~~bash
curl -i http://localhost:5000/
curl -i http://localhost:5000/actuator/health
~~~

Chỉ tiếp tục deploy khi code đã build/test thành công và endpoint health trả response phù hợp. Không dùng một JAR khác Java version hoặc artifact không tương thích platform trong production.

### 5.5. Vì sao executable JAR chạy tốt với Java SE?

Spring Boot executable JAR có HTTP server nhúng bên trong. Elastic Beanstalk Java SE chỉ cần **khởi chạy Java process** theo Procfile, sau đó reverse proxy có thể chuyển traffic vào cổng HTTP mà app lắng nghe.

Nếu ứng dụng cũ yêu cầu external Tomcat (Servlet container) và không phải executable JAR, chọn Tomcat platform/WAR như phần dưới, không gán bừa Procfile JAR cho một WAR.

## 6. Đóng gói source bundle và Procfile

### 6.1. Procfile

Với Java SE platform trên Amazon Linux 2/2023, **Procfile** ở root source bundle khai báo process cần chạy.

~~~text
web: java -jar app.jar
~~~

- **web** là tên process được platform sử dụng cho ứng dụng web.
- **app.jar** là artifact cùng cấp với Procfile trong ZIP.
- Spring Boot đang được cấu hình **server.port=5000**, phù hợp đường proxy mặc định đã nêu.
- Không hard-code access key hoặc database password trong Procfile.

Cấu trúc source bundle tối thiểu:

~~~text
orders-api-bundle/
├── app.jar
└── Procfile
~~~

### 6.2. Đóng gói artifact

Ví dụ thao tác trong môi trường local hoặc CI (không chạy các lệnh này trong môi trường production không được ủy quyền):

~~~bash
./mvnw clean verify

mkdir -p deploy
cp target/orders-api-0.0.1-SNAPSHOT.jar deploy/app.jar

# Tạo file deploy/Procfile với đúng một dòng:
# web: java -jar app.jar

cd deploy
zip ../orders-api-eb.zip app.jar Procfile
cd ..
~~~

Khi mở file ZIP, **app.jar và Procfile phải nằm ở root của ZIP**, không bị lồng dưới thư mục deploy/ hoặc orders-api-bundle/. Đây là lỗi phổ biến: source bundle có thêm một cấp thư mục khiến Procfile không được tìm thấy hoặc đường dẫn app.jar sai.

**Không đóng gói cả thư mục target, .git, IDE metadata, local secrets hoặc file cấu hình test chứa credentials** vào source bundle nếu không cần.

### 6.3. Tạo Procfile trên Linux/macOS

~~~bash
printf 'web: java -jar app.jar\n' > deploy/Procfile
~~~

Đây là ví dụ lệnh tạo file trong môi trường build; không phải một thao tác đã được thực thi bởi bài học. Trên Windows, đảm bảo nội dung là text UTF-8/ASCII phù hợp; không đưa Procfile thành **Procfile.txt**.

### 6.4. Có thể triển khai source code thay vì JAR không?

Elastic Beanstalk Java SE có khả năng xử lý một số dạng source bundle/build tùy platform; nhưng **đóng gói artifact đã kiểm thử trong CI** thường làm release **tái lập** hơn. Khi build trên instance, bạn phải kiểm soát JDK/Maven/Gradle/toolchain, thời gian khởi tạo và dependency repositories.

Trong pipeline chuyên nghiệp:

1. CI kiểm thử và tạo artifact.
2. Artifact được gắn checksum/version, đưa vào S3 hoặc kho artifact phù hợp.
3. Tạo Elastic Beanstalk application version từ artifact.
4. Triển khai đúng version ấy tới staging rồi production.
5. Có thể rollback về version trước mà không build lại mã nguồn.

## 7. Khi nào triển khai Java WAR trên Tomcat platform?

Một ứng dụng Java truyền thống thường có cấu trúc Servlet/JSP hoặc Spring MVC và đóng gói **WAR**.

Ví dụ:

~~~text
legacy-web/
├── pom.xml
└── src/main/webapp/
    └── WEB-INF/
        └── web.xml
~~~

Với Tomcat platform, Elastic Beanstalk cung cấp Tomcat container tương ứng để triển khai WAR. WAR có thể được upload trực tiếp hoặc đặt trong source bundle theo quy định của platform.

### 7.1. Spring Boot WAR cần cấu hình khác

Nếu triển khai Spring Boot lên external Tomcat:

- Đặt Maven packaging thành **war**.
- Điều chỉnh dependency Tomcat thành **provided** để tránh đóng gói/khởi tạo embedded server không phù hợp.
- Cho ứng dụng kế thừa **SpringBootServletInitializer** và override **configure(...)**.
- Build WAR và dùng Tomcat platform **cùng major version/Servlet API namespace tương thích**.
- Nếu muốn app phục vụ tại context root **/**, kiểm tra quy ước tên artifact, ví dụ **ROOT.war** theo hướng dẫn Tomcat platform.

Ví dụ phương thức cấu hình cho WAR:

~~~java
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

public class ServletInitializer extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder app) {
        return app.sources(OrdersApplication.class);
    }
}
~~~

Code này minh họa lớp hỗ trợ bootstrap WAR; project phải có đầy đủ imports/package, Maven packaging và dependencies phù hợp trước khi build.

### 7.2. Không dùng Java SE và Tomcat một cách tùy tiện

**Một executable JAR Spring Boot đã chứa embedded Tomcat** thường không cần Tomcat platform. Ngược lại, ứng dụng WAR được thiết kế để chạy trong external Tomcat có thể không hoạt động nếu chỉ đổi tên WAR thành JAR.

Nếu gặp lỗi:

~~~text
NoClassDefFoundError: javax/servlet/...
ClassNotFoundException: jakarta.servlet....
HTTP 404 ở sai context path
~~~

Hãy kiểm tra **Tomcat version, Servlet namespace, packaging, context root và dependencies**, thay vì tăng instance size hoặc mở thêm network ports.

## 8. Tạo và triển khai environment bằng EB CLI

**EB CLI** là command-line interface chuyên cho Elastic Beanstalk, khác **AWS CLI** quản lý AWS APIs nói chung. Nó hỗ trợ khởi tạo cấu hình local, tạo environment, deploy, xem logs và vận hành.

**Cảnh báo chi phí:** Các lệnh như **eb create**, **eb deploy**, **eb setenv**, **eb terminate** có thể thay đổi tài nguyên và phát sinh chi phí. Các lệnh dưới đây chỉ là **hướng dẫn minh họa**, không được thực thi trong bài. Chỉ thực hiện trên tài khoản/lab có quyền, sau khi nắm rõ cấu hình và ngân sách.

### 8.1. Chuẩn bị

Cần có:

- AWS account/role với quyền tạo Beanstalk application/environment và các tài nguyên hạ tầng cần thiết.
- **AWS CLI** và **EB CLI** được cài và cấu hình.
- Git/Maven/Java 17 phù hợp.
- Region được chọn, VPC/subnet/security và quota hợp lệ.
- **Elastic Beanstalk service role** và **EC2 instance profile** được tạo/cấp quyền theo yêu cầu, vì không nên mặc định tài khoản mới sẽ luôn có đầy đủ role mặc định.

~~~bash
aws sts get-caller-identity
aws configure get region
eb --version
java -version
~~~

**Không chia sẻ output chứa access key/secret key** trong tài liệu hoặc ticket. Lệnh **aws sts get-caller-identity** giúp xác nhận account/role thực tế trước khi triển khai, tránh tạo môi trường ở nhầm tài khoản.

### 8.2. Khởi tạo dự án EB

Trong thư mục làm việc chứa source bundle hoặc project được cấu hình để EB CLI chọn đúng artifact:

~~~bash
eb init
~~~

Quy trình thường yêu cầu:

1. Chọn **Region**.
2. Chọn hoặc tạo **Elastic Beanstalk application**, ví dụ **orders-api**.
3. Chọn **Java SE platform/branch** có Amazon Corretto tương thích.
4. Cấu hình SSH key pair nếu có nhu cầu vận hành và chính sách công ty cho phép.

Tên platform branch/version hiển thị tùy Region và thời điểm; hãy chọn đúng phiên bản AWS đang hỗ trợ thay vì sao chép tên branch từ hướng dẫn cũ.

### 8.3. Tạo dev environment

~~~bash
eb create orders-dev
~~~

Lệnh này thường kích hoạt tạo tài nguyên như CloudFormation stack, EC2, Security Groups, Auto Scaling và load balancer tùy cấu hình. Với lab muốn giảm chi phí, có thể chọn **single-instance environment** theo tùy chọn được EB CLI/console hỗ trợ; với production nên đánh giá load-balanced/multi-AZ.

Khi tạo environment, cần xác minh:

- VPC/subnets, public/private placement.
- Instance type/size và platform version.
- Capacity Min/Max cho load-balanced environments.
- Vai trò IAM service role và EC2 instance profile.
- Cấu hình Java app startup và health endpoint.
- Tags, log retention và budget.

**Không coi cấu hình mặc định của wizard là mặc định an toàn cho production** nếu chưa review security và tính sẵn sàng.

### 8.4. Triển khai ứng dụng

~~~bash
eb deploy orders-dev
~~~

Lệnh deploy phụ thuộc cách **EB CLI chọn artifact** (source code, source bundle, cấu hình build/ignore). Nếu đã tạo **orders-api-eb.zip**, cần bảo đảm EB CLI thực sự upload đúng ZIP hoặc sử dụng quy trình ApplicationVersion/S3 được pipeline cấu hình, thay vì mặc định nó sẽ tự lấy ZIP chỉ vì file tồn tại cạnh project.

Cách triển khai khác là upload source bundle qua **Elastic Beanstalk console**, hoặc tạo application version qua API/IaC. Dù dùng cách nào, quan trọng nhất là **artifact được triển khai** chứa Procfile + app.jar đúng cấu trúc.

### 8.5. Kiểm tra sau deploy

~~~bash
eb status orders-dev
eb health orders-dev
eb events orders-dev
eb logs orders-dev
eb open orders-dev
~~~

Lệnh **eb open** mở URL môi trường trong browser; những command như **status/health/events/logs** chủ yếu phục vụ quan sát. Tùy environment, **eb health** cần enhanced health và quyền phù hợp.

Checklist kiểm thử:

1. Environment trở về trạng thái health ổn định.
2. **GET /** trả status mong đợi.
3. **GET /actuator/health** trả HTTP thành công.
4. Không có 502/504 bất thường hoặc Java stack trace.
5. ALB targets đều healthy nếu dùng load balancer.
6. Application version và config đang chạy đúng release.
7. CloudWatch metrics/logs thu được tín hiệu tối thiểu.

### 8.6. Thay đổi environment variables

Ví dụ môi trường dev:

~~~bash
eb setenv SPRING_PROFILES_ACTIVE=dev
~~~

Đây là lệnh **thay đổi environment** và có thể kích hoạt cập nhật/restart deployment. Không truyền **database password, access key hoặc token** trực tiếp qua command line nếu chúng có nguy cơ xuất hiện trong shell history, logs, terminal recording hay CI output. Dùng Secrets Manager/SSM Parameter Store theo cách tích hợp platform hỗ trợ và quản trị quyền phù hợp.

### 8.7. Xóa môi trường lab sau khi kết thúc

~~~bash
# DANGEROUS: chỉ thực thi với môi trường lab chắc chắn không còn cần.
eb terminate orders-dev
~~~

**Terminate có thể xóa nhiều tài nguyên do environment quản lý.** Nếu database RDS được tạo bằng cơ chế gắn trực tiếp với lifecycle môi trường, việc terminate có thể có hậu quả mất dữ liệu tùy cấu hình. Trước khi xóa, kiểm tra database có thuộc vòng đời environment hay không, backup cần thiết, ALB/EC2/EBS và tài nguyên phát sinh chi phí.

**Không dùng lệnh terminate trong production để “thử cleanup”** nếu chưa có kế hoạch data retention, khả năng phục hồi và quyền được phê duyệt.

## 9. Quản lý cấu hình bằng .ebextensions và .platform

Source bundle không chỉ chứa application JAR. Elastic Beanstalk hỗ trợ những cơ chế cấu hình theo platform, gồm:

- **Environment configuration / option settings:** qua console, EB CLI, API, IaC hoặc file config.
- **.ebextensions:** các file **.config** YAML/JSON để cung cấp option settings và một số cơ chế cấu hình theo platform.
- **.platform/hooks:** script hooks dành cho Amazon Linux 2/2023 platform, chạy ở những giai đoạn deployment được hỗ trợ.
- **.platform/nginx:** phần mở rộng cấu hình reverse proxy khi cần, theo layout và quy tắc của platform.

Cần lựa chọn đúng tùy **platform version**. Không copy hướng dẫn cũ cho Amazon Linux 1 sang Amazon Linux 2/2023 mà không kiểm tra khả năng hỗ trợ.

### 9.1. Ví dụ option_settings

Đối với một **load-balanced Java SE environment có Application Load Balancer**, có thể cấu hình environment variable và health check path:

~~~yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    SPRING_PROFILES_ACTIVE: prod
  aws:elasticbeanstalk:environment:process:default:
    HealthCheckPath: /actuator/health
~~~

Lưu file theo cấu trúc:

~~~text
.ebextensions/01-application.config
~~~

**Giới hạn quan trọng:**

- Namespace **aws:elasticbeanstalk:environment:process:default** dành cho cấu hình **ALB process** được hỗ trợ, có thể không phù hợp single-instance hoặc cấu hình ELB khác.
- **SPRING_PROFILES_ACTIVE** ở đây không phải secret.
- Việc cấu hình health check trong .config không có nghĩa ALB sẽ tự xác minh database, migration và mọi dependency. Endpoint **/actuator/health** phải phục vụ được request thực tế.
- Environment settings từ console/CLI/IaC có thể có quy tắc precedence/override khác .ebextensions; cần chọn một nguồn cấu hình được quản lý có chủ đích.

### 9.2. Procfile so với Buildfile và platform hooks

| Thành phần | Mục đích | Khi sử dụng |
| --- | --- | --- |
| **Procfile** | Xác định command khởi chạy process ứng dụng. | Java SE executable JAR. |
| **Buildfile** | Thực thi bước build/config hỗ trợ trước app startup theo platform. | Khi cần chuẩn bị artifact trên instance và cơ chế được hỗ trợ. |
| **.ebextensions/*.config** | Option settings và cấu hình môi trường theo feature. | Environment variable, health path, các tùy chọn AWS. |
| **.platform/hooks/prebuild** | Thực thi hook trước giai đoạn build/deploy tương ứng. | Chuẩn bị môi trường nếu thật sự cần. |
| **.platform/hooks/predeploy** | Hook trước triển khai ứng dụng. | Kiểm tra điều kiện/ngữ cảnh trước startup. |
| **.platform/hooks/postdeploy** | Hook sau triển khai ứng dụng. | Tác vụ hậu kiểm, nhưng cần rất thận trọng với side effects. |

Ví dụ hook tối giản:

~~~bash
#!/bin/bash
set -euo pipefail
echo "Elastic Beanstalk postdeploy hook completed"
~~~

Đặt vào **.platform/hooks/postdeploy/10-verify.sh** khi platform hỗ trợ. Trên các platform release khác nhau, cơ chế tự cấp executable permission và xử lý line endings có thể khác; nên dùng **LF**, kiểm tra permissions và hành vi hooks trong môi trường staging.

**Không đặt schema migration có thể phá dữ liệu hay thao tác không idempotent vào hook chạy trên mọi EC2 instance**. Trong môi trường có nhiều EC2, cùng hook có thể chạy **nhiều lần**, gây race condition hoặc trùng tác dụng. Database migration nên có một quy trình điều phối riêng hoặc locking đáng tin cậy.

### 9.3. Không hard-code cấu hình theo environment

Những tham số nên được quản lý bên ngoài JAR hoặc theo từng environment:

- **SPRING_PROFILES_ACTIVE**.
- Database hostname, database name, pool settings.
- Feature flags, API base URLs.
- Log levels, observability endpoints.
- Secrets references và quyền truy cập.
- JVM memory/concurrency tuning khi cần.

Một JAR đã kiểm thử có thể được đẩy qua **dev → staging → prod** mà không build lại nếu thông số được tách khỏi artifact đúng cách.

### 9.4. Java heap và memory

Không đặt **-Xmx** bằng tổng RAM EC2 instance: hệ điều hành, Nginx, Java non-heap/native memory, metaspace, thread stacks và CloudWatch/health agents cũng cần RAM.

Ví dụ một EC2 với RAM khiêm tốn có thể bị **OOM killer** nếu Java heap chiếm phần lớn RAM, dẫn tới 502 và instance unhealthy. Hãy đo **RSS, heap usage, GC pauses, CPU, memory pressure** và chọn instance class/JVM options dựa trên quan sát. Tăng instance count không sửa memory leak trong mỗi JVM.

## 10. VPC, ALB, HTTPS và quyền truy cập mạng

### 10.1. Public ALB, private EC2

Một môi trường production có thể chọn:

- **ALB** ở public subnets thuộc tối thiểu hai AZ theo topology load-balanced.
- **EC2 Java instances** trong private application subnets.
- **RDS database** trong private database subnets, không có public access không cần thiết.
- **Security Groups** chỉ mở đúng nguồn/đích/cổng.
- **NAT Gateway hoặc VPC endpoints** cho EC2 truy cập ECR/S3/CloudWatch/SSM/Secrets Manager khi yêu cầu.

Không phải mọi Beanstalk environment mặc định đặt EC2 private. Nếu tạo environment ở default VPC mà không review subnet/SG, có thể để ứng dụng và instance expose quá rộng.

### 10.2. Luồng Security Group mẫu

| Thành phần | Hướng | Quy tắc minh họa |
| --- | --- | --- |
| ALB SG | Inbound | TCP/443 từ nguồn người dùng được phép (0.0.0.0/0 nếu là public API, cân nhắc WAF). |
| ALB SG | Outbound | Đến instance SG trên cổng target/proxy (thường TCP/80). |
| EC2 SG | Inbound | Chỉ từ **ALB SG** đến cổng Nginx/ứng dụng phù hợp. |
| EC2 SG | Outbound | Đến DB, external APIs, S3/VPC endpoints/NAT theo nhu cầu. |
| RDS SG | Inbound | Chỉ từ **EC2 instance SG** đến DB port như 5432 hoặc 3306. |

**Không mở RDS port cho cả Internet** chỉ vì Java app không kết nối được. Kiểm tra VPC routing, SG source references, database hostname, credentials và TLS.

### 10.3. HTTPS qua ACM

Với ALB:

1. Có domain như **api.example.com** trong DNS quản lý.
2. Request certificate cho hostname tại **ACM Region** phù hợp với ALB.
3. Gắn certificate với **ALB HTTPS listener/443**.
4. Nếu cần, redirect HTTP/80 tới HTTPS/443.
5. Dùng Route 53 Alias A/AAAA trỏ domain tới ALB endpoint.
6. Kiểm tra HTTPS từ browser/client bằng hostname thực, không chỉ gọi bằng ALB DNS name.

TLS có thể được **kết thúc tại ALB**. Nếu chính sách yêu cầu mã hóa từ ALB tới EC2, cấu hình target protocol/instance proxy certificate theo hướng dẫn tương ứng. Không nhầm **HTTPS từ client đến ALB** với đảm bảo toàn bộ đường truyền sau ALB luôn HTTPS.

### 10.4. Header X-Forwarded-*

Khi app đứng sau ALB/Nginx, Spring Boot có thể thấy kết nối vào instance là HTTP/port nội bộ. Ứng dụng có thể cần xử lý **X-Forwarded-Proto**, **X-Forwarded-For** và hostname để tạo redirect/absolute URL chính xác.

**Cảnh báo bảo mật:** Chỉ tin forwarded headers do **proxy/load balancer tin cậy** tạo hoặc ghi đè. Nếu app chấp nhận tùy tiện headers từ client Internet, có nguy cơ spoof scheme/client IP và gây lỗi authorization hoặc URL generation.

## 11. IAM: service role, instance profile và quyền Java app

### 11.1. Hai vai trò EB thường bị nhầm

| Thành phần | Ai dùng? | Quyền điển hình |
| --- | --- | --- |
| **Elastic Beanstalk service role** | Dịch vụ EB vận hành/tích hợp health, update và các tài nguyên liên quan. | Quyền theo managed policies/role AWS hướng dẫn. |
| **EC2 instance profile role** | EC2 instances trong environment; ứng dụng Java và agent có thể sử dụng temporary credentials tương ứng. | Truy cập S3 deployment artifact, CloudWatch và API AWS theo quyền được cấp. |

Nếu service role hoặc instance profile bị thiếu/không có quyền, môi trường có thể tạo không thành công hoặc deploy thất bại dù ứng dụng Java compile tốt.

AWS có các service-linked roles, managed policies và hướng dẫn tạo role. **Không tự cấp AdministratorAccess** chỉ để hết lỗi AccessDenied; kiểm tra chính xác principal và action cần cấp.

### 11.2. Quyền ứng dụng truy cập S3

Ví dụ Java app chỉ cần đọc object dưới prefix **invoices/** của một bucket:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadInvoicesOnly",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::example-private-invoices/invoices/*"
    }
  ]
}
~~~

Đây là policy ví dụ; ở production cần cân nhắc role isolation giữa các application environments, bucket policy, KMS key permissions và điều kiện network. Trên EC2 thông thường, Java AWS SDK có thể dùng **temporary credentials từ instance profile** theo default credentials provider chain.

**Không lưu AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY cố định trong application.properties, JAR, Procfile hoặc source control** nếu có thể dùng IAM role.

### 11.3. Secret management

Mật khẩu RDS và token của dịch vụ khác không nên nằm trong mã nguồn.

Các lựa chọn thường gặp:

- **AWS Secrets Manager** cho secret cần rotation/audit.
- **SSM Parameter Store** cho cấu hình và SecureString khi phù hợp.
- Environment properties chứa giá trị thường không nhạy cảm.
- Cơ chế **Elastic Beanstalk environment secrets** tham chiếu Secrets Manager/Parameter Store trên platform được hỗ trợ, thay vì đưa plaintext vào config file.

Khi sử dụng secret references, kiểm tra **platform version** hỗ trợ, **instance profile IAM**, **KMS permissions**, DNS/VPC endpoint/network, hành vi **secret rotation** và thời điểm ứng dụng nhận giá trị mới. Không tự khẳng định secret đã rotation trong Secrets Manager thì mọi JVM đang chạy đều reload ngay.

## 12. Kết nối database an toàn: RDS nên độc lập vòng đời environment

### 12.1. Vì sao không để database sống chết cùng EC2?

Một Java API thường dùng PostgreSQL, MySQL hoặc Aurora để lưu giao dịch. Khi Elastic Beanstalk thay EC2 trong deployment/Auto Scaling, dữ liệu database phải tiếp tục tồn tại.

**Nguyên tắc:** Database cần vòng đời, backup, recovery và quyền sở hữu **độc lập với lifecycle của environment** trừ khi đây là lab cố ý dùng DB tạm.

Elastic Beanstalk có cơ chế tích hợp tạo RDS cho environment trong một số workflow. Nếu database gắn vào environment, thao tác terminate environment có thể gây hậu quả nghiêm trọng cho database tùy configuration và chính sách lưu giữ. Với production, nên **tạo RDS riêng**, kết nối qua network/SG/IAM theo hướng dẫn, và quản lý backup/retention tách biệt.

### 12.2. Kiến trúc database tách rời

~~~mermaid
flowchart LR
    EB["EB Java environment"] -->|"JDBC/TLS"| RDS[("Amazon RDS PostgreSQL")]
    SEC["Secrets Manager"] -->|"Secret reference / SDK"| EB
    CICD["CI/CD"] -->|"Versioned migrations có kiểm soát"| RDS
    B["Automated backups / snapshots"] -.-> RDS
~~~

Đây là sơ đồ khái niệm. CI/CD migrations phải có quyền riêng và cơ chế chỉ chạy một lần khi phù hợp; không yêu cầu quyền admin database trong runtime application role.

### 12.3. Spring Boot cấu hình database

Ví dụ **application.properties** không chứa mật khẩu thật:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal.example:5432/orders
spring.datasource.username=orders_app

# Giá trị phải đến từ secret injection hoặc cấu hình runtime tin cậy.
# Không commit mật khẩu vào source repository.

spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=30000
~~~

Chỉ cài PostgreSQL JDBC driver khi ứng dụng thật sự dùng PostgreSQL. Mật khẩu có thể được cung cấp qua secrets integration hoặc cơ chế runtime được quản lý, không ghi vào tài liệu.

Nếu Auto Scaling tăng từ 2 lên 20 EC2 và mỗi JVM mở tối đa **10 DB connections**, số kết nối có thể tăng từ khoảng **20** lên **200**, chưa tính admin jobs và service khác. Phải kiểm tra **max_connections**, pool size, RDS Proxy nếu phù hợp, connection reuse và cách scale.

### 12.4. Migration schema

Một deployment Java có thể cần thêm cột database. Nên dùng Flyway/Liquibase hoặc migration workflow có kiểm soát:

1. Xây dựng thay đổi **backward-compatible** với phiên bản cũ và mới.
2. Deploy mở rộng schema trước khi code bắt đầu dùng field mới khi cần.
3. Thực hiện bước migrate có locking/coordination; không để mọi EC2 cùng chạy phá dữ liệu.
4. Deploy application version mới theo policy phù hợp.
5. Sau khi ổn định, thực hiện cleanup schema cũ ở release sau.

Rollback code **không tự rollback schema/data**. Nếu một migration đã drop cột, đổi JAR về version cũ có thể vẫn thất bại. Cần kế hoạch database change riêng.

## 13. Deployment policies và cách hạn chế downtime

Elastic Beanstalk hỗ trợ nhiều phương thức **application deployment** với sự đánh đổi giữa tốc độ, chi phí tạm thời và khả năng rollback. Tính năng được hỗ trợ tùy environment/platform/tier.

| Policy | Ý tưởng | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| **All at once** | Deploy tới toàn bộ EC2 cùng lúc. | Nhanh, đơn giản. | Có nguy cơ gián đoạn khi mọi instances đều cập nhật/restart. |
| **Rolling** | Deploy theo từng batch EC2. | Giữ một phần capacity phục vụ. | Capacity giảm trong lúc deploy; lỗi có thể tác động một phần traffic. |
| **Rolling with additional batch** | Thêm capacity tạm, deploy theo batch rồi thu lại. | Giảm mất capacity hiện có. | Tăng chi phí EC2 tạm thời, cần đủ quota/subnet IP. |
| **Immutable** | Tạo tập instance mới cho release, xác minh rồi thay tập cũ. | Cách ly thay đổi tốt, rollback thuận lợi hơn trong nhiều trường hợp. | Tốn thêm capacity/thời gian; cần hiểu giới hạn môi trường. |
| **Traffic splitting** | Chuyển một tỷ lệ traffic tới các instances dùng bản mới trong thời gian đánh giá. | Hỗ trợ canary theo tỷ lệ và theo dõi health. | Cần load balancer/điều kiện hỗ trợ và capacity tạm thời. |
| **Blue/green** | Tạo **environment khác** cho version mới, kiểm thử rồi chuyển URL/CNAME. | Cô lập release và rollback bằng chuyển traffic trở lại environment cũ. | Có hai environment, chi phí song song, cần kiểm soát state/data/DNS. |

**Phân biệt:** Blue/green qua **hai environments** là một **chiến lược release**, không đơn thuần là một giá trị trong danh sách deployment policy cho một environment.

### 13.1. Rolling deployment

Giả sử environment có 6 EC2 instances, deployment rolling theo batch 2:

1. Chọn batch 2 instances để deploy.
2. Những instances còn lại tiếp tục phục vụ.
3. Kiểm tra health theo behavior của platform.
4. Chuyển sang batch tiếp theo khi đáp ứng điều kiện.

Trong giai đoạn deploy, năng lực phục vụ có thể giảm. Phải có headroom đủ để không quá tải những instances còn khỏe. Nếu rolling deploy cùng database migration không backward-compatible, cả bản cũ lẫn mới có thể bị lỗi.

### 13.2. Immutable deployment

Immutable deployment tạo tập instance mới theo cơ chế được AWS quản lý để triển khai version mới. Sau khi health kiểm tra phù hợp, environment chuyển capacity sang tập mới và thu hồi tài nguyên cũ.

Lợi ích là release mới được **tách khỏi fleet cũ** trong giai đoạn kiểm thử, giảm rủi ro sửa trực tiếp mọi máy đang phục vụ. Nhưng **database và tài nguyên dùng chung vẫn là điểm rủi ro**: nếu code mới đã thay dữ liệu không tương thích thì trả lại fleet cũ chưa chắc khôi phục nghiệp vụ.

### 13.3. Traffic splitting

Traffic splitting cho phép gửi một tỷ lệ lưu lượng tới tập instances chạy version mới theo cơ chế được platform/ALB hỗ trợ, quan sát health trong khoảng đánh giá, rồi quyết định chuyển hết hoặc rollback.

Không nhầm **traffic splitting tại ALB** với **weighted DNS records của Route 53**. ALB chia traffic ở tầng HTTP/request phù hợp; Route 53 weighted routing chia **DNS answers**, chịu tác động caching.

### 13.4. Blue/green bằng hai environments

~~~mermaid
flowchart TB
    DNS["api.example.com / CNAME"] --> OLD["orders-prod-blue — version 1.4"]
    DNS -.->|"Sau cutover / swap"| NEW["orders-prod-green — version 1.5"]
    OLD --> DB[("RDS / shared services")]
    NEW --> DB
    TEST["Smoke tests / synthetic monitoring"] --> NEW
~~~

Quy trình:

1. Tạo **green environment** cùng application nhưng chạy version mới.
2. Cấu hình VPC/IAM/secret/database endpoints tương thích.
3. Kiểm thử green qua environment URL riêng và synthetic test.
4. Kiểm tra traffic pattern, ALB health, logs và database migrations.
5. **Swap environment CNAMEs** hoặc chuyển DNS theo kế hoạch điều phối.
6. Theo dõi health và behavior thực tế; giữ blue đủ lâu cho rollback.
7. Sau khi ổn định mới retire blue, tránh xóa nhầm resources chia sẻ.

CNAME swap không cắt ngay mọi client connection do DNS TTL/cache/keep-alive; cần dự trù thời gian chuyển và test theo những resolver thực tế.

### 13.5. Chọn policy khi nào?

- Dev/test hoặc dịch vụ chấp nhận downtime → **All at once** có thể hợp lý.
- App với nhiều instances, cần giảm tác động nhưng hạn chế capacity → **Rolling**.
- Cần giữ số instances sẵn sàng khi deploy → **Rolling with additional batch**.
- Release nhạy cảm, cần cô lập fleet mới và rollback tốt hơn → **Immutable**.
- Muốn thử một tỷ lệ traffic trên version mới trong một environment tương thích → **Traffic splitting**.
- Muốn triển khai hai environment độc lập, đổi traffic chủ động → **Blue/green**.

Không có policy nào thay thế việc kiểm thử **schema migration, backward compatibility, secrets, app health, data consistency** và khả năng rollback.

## 14. Auto Scaling và khả năng phục hồi

### 14.1. Elastic Beanstalk scale cái gì?

Với **load-balanced environment**, EB cấu hình **EC2 Auto Scaling group** để tăng/giảm số lượng EC2 instances theo settings/metrics hỗ trợ.

Đây là quy mô **máy EC2 chạy Java app**, khác với ECS Service Auto Scaling tăng/giảm số **ECS tasks**. Elastic Beanstalk không ngầm sử dụng ECS capacity providers trong workflow Java SE/Tomcat EC2 thông thường.

Các giới hạn chính:

- **Min instances**: số EC2 tối thiểu muốn duy trì.
- **Max instances**: số EC2 tối đa có thể scale theo cấu hình.
- **Metric/trigger**: CPU utilization, network traffic hoặc signal được platform/ASG hỗ trợ.
- **Scaling cooldown**: tránh dao động khi instances cần thời gian boot/deploy/warm up.

### 14.2. Tính capacity theo thực tế

Giả sử một EC2 chạy Java app có thể xử lý khoảng **100 requests/giây** ở latency chấp nhận được trong môi trường test; hệ thống có peak 600 requests/giây.

Ước tính lý tưởng:

\[
\text{Số instances tối thiểu theo throughput}
\approx \frac{600}{100}=6
\]

Đây **không** phải kết luận “chỉ cần sáu instances cho production”. Cần thêm:

- Headroom khi một AZ/instance lỗi.
- Thời gian startup/warm-up.
- CPU, JVM heap, GC pauses và thread pool.
- ALB target health, database bottleneck và connections.
- Request size và sự phân tán lưu lượng.
- Graceful shutdown, p95/p99 latency và retry.

Khi Auto Scaling tạo EC2 mới, phải đủ subnet IP, IAM instance profile, artifact, network đến dependency và thời gian khởi động; số instance tăng nhưng app không ready sẽ chưa cải thiện traffic.

### 14.3. Readiness và liveness

**Liveness:** tiến trình Java còn sống hay không.

**Readiness:** instance có sẵn sàng xử lý request thực sự hay không.

Một health endpoint chỉ trả 200 nếu JVM chạy chưa chắc chứng minh database query quan trọng hoạt động. Ngược lại, nếu health endpoint luôn fail khi một downstream phụ ít quan trọng lỗi thoáng qua, ALB có thể loại hết targets và làm availability kém hơn.

Nên thiết kế health theo **critical dependencies**, có timeout và mức chấp nhận lỗi được xác định, phân biệt mục tiêu monitoring với readiness dùng để điều phối traffic.

### 14.4. Multi-AZ không phải multi-Region

Load-balanced EB có thể phục vụ nhiều AZ **trong một Region**. Nó không tự thực hiện multi-Region active-active, replicate RDS/S3 hay chuyển DNS xuyên Region khi sự cố lớn.

Muốn DR/multi-Region, cần:

- Environment và data services ở Region dự phòng.
- Replication/backup đúng **RPO**.
- Kế hoạch traffic failover như Route 53/Global Accelerator theo nhu cầu.
- Quản lý secrets, KMS, IAM, certificates và VPC tại Region dự phòng.
- Diễn tập **RTO** thực tế.

## 15. Quan sát: health, events, logs và metrics

### 15.1. Basic health và enhanced health

Elastic Beanstalk có những cơ chế health phù hợp với environment và platform:

- **Basic health**: một số tín hiệu nền tảng như khả năng phản hồi của environment.
- **Enhanced health**: thông tin tổng hợp chi tiết hơn về instances, request health và nguyên nhân degradation theo khả năng hỗ trợ.

Các trạng thái health/color như **Ok, Warning, Degraded, Severe** giúp nhận diện tình hình, nhưng **không thay thế** log ứng dụng hoặc SLO metrics. Môi trường có trạng thái tốt không bảo đảm mọi endpoint nghiệp vụ đều đúng dữ liệu.

### 15.2. Những nguồn log cần biết

| Log/tín hiệu | Mục đích |
| --- | --- |
| **Application logs** | Java exception, business errors, startup và request diagnostics. |
| **Nginx access/error logs** | Request routing, 502/504, upstream connection errors. |
| **Elastic Beanstalk deployment logs** | Hooks, artifact unpack, startup command, deployment failure. |
| **EC2/OS/system logs** | OOM killer, disk full, service failure và instance lifecycle. |
| **ALB metrics/logs** | Healthy targets, 5xx, latency và traffic distribution. |
| **CloudWatch metrics/alarms** | CPU, network, Auto Scaling và health. |
| **CloudTrail** | Ai sửa environment config, deploy version, thay IAM/role theo phạm vi logging. |

Đường dẫn file log chi tiết khác nhau theo platform generation và version; đọc console/EB CLI và tài liệu platform thay vì hard-code một path cho mọi Amazon Linux version.

### 15.3. EB CLI xem logs và events

~~~bash
eb status orders-dev
eb health orders-dev
eb events orders-dev
eb logs orders-dev
~~~

Một số tùy chọn EB CLI cho phép tải đầy đủ logs hoặc theo dõi tiếp, tùy phiên bản EB CLI. Dùng lệnh phù hợp với quyền/khả năng triển khai trong môi trường của bạn. Nên bật **log streaming tới CloudWatch Logs** và đặt retention nếu cần điều tra sau khi EC2 bị thay thế.

**Lưu ý quyền riêng tư:** Không log JWT, Authorization headers, database password, secrets hoặc dữ liệu khách hàng nhạy cảm không cần thiết.

### 15.4. Đề xuất alarms/SLO

- Availability của **/health** và những endpoints nghiệp vụ chính.
- ALB **5xx**, target health và p95/p99 latency.
- EC2 CPU/memory/disk pressure (memory thường cần agent hoặc metric tùy chỉnh).
- JVM GC pause, heap, thread pool.
- RDS connections/CPU/latency, query error.
- Thời gian triển khai, số deployment failures.
- Chi phí EC2/ALB/NAT/data transfer và mức tăng bất thường.

Khi ứng dụng scale out mạnh, metrics backend phải được giám sát song song; một database quá tải có thể là bottleneck bất chấp EC2 đang rất khỏe.

## 16. Khắc phục lỗi triển khai Java trên Elastic Beanstalk

### 16.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| **502 Bad Gateway** sau deploy. | Java process không chạy, sai cổng Nginx↔JVM, app startup quá chậm. | Application logs, Nginx errors, Procfile, server.port, health. |
| **503** từ ALB. | Không có healthy targets, deployment đang thay instances, health path sai. | ALB target group, environment health, ASG/EC2 status. |
| **504 Gateway Timeout**. | Java xử lý chậm, thread pool hết, DB/downstream timeout, load balancer timeout. | ALB metrics/logs, app logs, DB latency và thread dumps theo quy trình. |
| **UnsupportedClassVersionError**. | Build JAR bằng Java mới hơn runtime trên EB. | java -version, Maven target/release, platform runtime. |
| **no main manifest attribute** hoặc **Unable to access jarfile**. | JAR không executable, sai path/tên artifact, Procfile sai. | Source bundle ZIP, Maven Spring Boot repackage, Procfile. |
| **Environment health Red/Degraded**. | App lỗi, EC2/ALB target unhealthy, deployment hook fail, network hoặc IAM. | EB events, enhanced health, logs, instance status. |
| **AccessDenied** đọc S3/Secrets Manager. | Instance profile thiếu quyền, bucket/KMS/secret policy deny, nhầm role. | STS identity trong runtime theo quy trình, IAM/KMS/network. |
| **RDS connection timeout**. | SG, route, DB private endpoint, DNS, subnet hoặc DB không phục vụ. | VPC path, DB SG inbound từ app SG, RDS metrics. |
| **RDS authentication failed**. | User/password sai, secret rotation lệch, DB permissions. | Secret source, runtime env, database logs. |
| **Lỗi sau khi scale-out**. | Session lưu cục bộ, file upload chỉ ở một EC2, DB connection pool quá lớn. | Shared state, sticky session, S3/RDS, per-instance logs. |
| **Build/hook fail**. | File permissions, line endings CRLF, missing dependencies, script error. | Deployment logs và cấu trúc .platform/.ebextensions. |
| **Environment update stuck**. | ASG quota/subnet IP, health mismatch, instance launch lỗi, IAM/service role. | EB events, CloudFormation events, EC2/ASG activities. |
| **Sau CNAME swap vẫn thấy release cũ**. | DNS TTL/cache, browser keep-alive, custom domain/delegation. | DNS resolver thực tế, CNAME/ALB target, versions. |
| **Chi phí cao dù ít traffic**. | ALB, min EC2, NAT, RDS, CloudWatch và môi trường staging chưa xóa. | Cost Explorer, tags, environment inventory. |

### 16.2. Cây chẩn đoán

~~~mermaid
flowchart TD
    A["Ứng dụng Java không truy cập được"] --> B{"Environment có health ổn?"}
    B -->|"Không"| C["Đọc EB events / enhanced health / deployment logs"]
    B -->|"Có"| D{"DNS/TLS/ALB hoạt động?"}
    D -->|"Không"| E["Kiểm tra Route 53, ACM, listener, SG, ALB target"]
    D -->|"Có"| F{"Nginx kết nối được Java process?"}
    F -->|"Không"| G["Kiểm tra Procfile, JAR, server.port, JVM error"]
    F -->|"Có"| H{"API kết nối được DB/Secrets/dependency?"}
    H -->|"Không"| I["Kiểm tra VPC route, SG, IAM/KMS, credentials, DB"]
    H -->|"Có"| J["Kiểm tra application logs, business errors, latency và state"]
~~~

Luôn ghi lại **application/environment/version label, Region, thời điểm deploy, HTTP status, request path và những thay đổi cấu hình gần nhất**. Không tự kết luận “AWS lỗi” khi mới thấy 502: nhiều lần đây là mismatch giữa Procfile, port và Java process.

### 16.3. Trường hợp cụ thể: Spring Boot default 8080 vs Nginx 5000

Triệu chứng:

- Spring Boot log cho thấy app chạy thành công ở **8080**.
- Nginx upstream mặc định vẫn chuyển request tới **5000**.
- Client truy cập URL environment nhận **502**.

Sửa:

1. Kiểm tra **proxy pass/upstream port** của Java SE platform.
2. Chỉnh app lắng nghe port tương ứng (ví dụ **server.port=5000**) hoặc tùy chỉnh proxy đúng quy trình.
3. Triển khai lại source bundle đã được test.
4. Kiểm tra **/actuator/health** qua environment URL.

**Không phải** thêm inbound SG 8080 từ Internet nếu Nginx chỉ cần kết nối localhost:5000.

### 16.4. Trường hợp cụ thể: Procfile không có ở ZIP root

Triệu chứng:

~~~text
orders-api-eb.zip
└── deploy/
    ├── Procfile
    └── app.jar
~~~

Platform tìm Procfile ở root nhưng file lại ở một tầng thư mục lồng. Cấu trúc đúng:

~~~text
orders-api-eb.zip
├── Procfile
└── app.jar
~~~

Cần kiểm tra artifact bằng trình giải nén trước khi upload; không chỉ xem thư mục source trên máy phát triển.

### 16.5. Trường hợp cụ thể: RDS được tạo cùng environment

Triệu chứng: nhóm dự định terminate **orders-dev** sau lab nhưng database vô tình chứa dữ liệu không thể mất.

Xử lý:

1. **Dừng quyết định terminate** cho tới khi xác định quyền sở hữu database.
2. Kiểm tra RDS có được EB quản lý trong lifecycle của environment hay không.
3. Xác định backup/snapshot/retention plan, dữ liệu cần giữ.
4. Với hệ thống không tạm thời, tách DB ra khỏi lifecycle environment trước khi cleanup theo quy trình AWS hỗ trợ.
5. Kiểm tra lại bằng restore test/DB connection và phân quyền.

Nguyên tắc là **đừng đánh đồng môi trường compute có thể tạo lại với dữ liệu cần được bảo toàn lâu dài**.

## 17. AWS CLI ở chế độ chỉ đọc

Các lệnh dưới đây chỉ để **quan sát trạng thái**, không tạo hoặc sửa resource. Chọn đúng AWS account/Region; thay tên minh họa bằng application/environment đang sở hữu hoặc được cấp quyền truy cập.

### 17.1. Xác định account và application

~~~bash
aws sts get-caller-identity

aws elasticbeanstalk describe-applications \
  --application-names orders-api \
  --region ap-southeast-1
~~~

Nếu không thấy application, hãy kiểm tra Region, account và permissions trước khi kết luận nó không tồn tại.

### 17.2. Xem environments

~~~bash
aws elasticbeanstalk describe-environments \
  --application-name orders-api \
  --region ap-southeast-1 \
  --query "Environments[].{Name:EnvironmentName,Id:EnvironmentId,Status:Status,Health:Health,Version:VersionLabel,URL:CNAME}"
~~~

Cần đọc **Status**, **Health**, **VersionLabel** và **CNAME**. Nhiều environment thuộc cùng application có thể chạy các version khác nhau.

### 17.3. Xem tài nguyên của environment

~~~bash
aws elasticbeanstalk describe-environment-resources \
  --environment-name orders-prod \
  --region ap-southeast-1
~~~

Kết quả liệt kê những resource liên quan như EC2 instances, Auto Scaling groups, load balancers, scaling triggers và những thành phần được hỗ trợ. Dùng ID này để tiếp tục điều tra bằng EC2/ELB/ASG APIs phù hợp, không đoán ID từ tên environment.

### 17.4. Xem sự kiện triển khai

~~~bash
aws elasticbeanstalk describe-events \
  --environment-name orders-prod \
  --max-records 30 \
  --region ap-southeast-1
~~~

Events cho biết các hoạt động update, deployment, instance health, failure reason ở phạm vi EB. **Events không thay application logs** khi cần tìm Java exception.

### 17.5. Xem health chi tiết

~~~bash
aws elasticbeanstalk describe-environment-health \
  --environment-name orders-prod \
  --attribute-names All \
  --region ap-southeast-1
~~~

Lệnh cần **enhanced health** được bật và quyền phù hợp. Nếu không hỗ trợ ở environment, cần dùng describe-environments, EB events, ALB/EC2 metrics/logs thay vì suy environment chắc chắn khỏe.

### 17.6. Xem phiên bản ứng dụng

~~~bash
aws elasticbeanstalk describe-application-versions \
  --application-name orders-api \
  --region ap-southeast-1 \
  --query "ApplicationVersions[].{Version:VersionLabel,Status:Status,Source:SourceBundle,Created:DateCreated}"
~~~

Kiểm tra version label và source bundle, đối chiếu release pipeline. Version label có tên đúng **không bảo đảm source bundle chứa Procfile/JAR đúng** nếu artifact được upload sai.

### 17.7. Xem cấu hình environment

~~~bash
aws elasticbeanstalk describe-configuration-settings \
  --application-name orders-api \
  --environment-name orders-prod \
  --region ap-southeast-1
~~~

Kết quả có thể chứa **environment property values** hoặc cấu hình nhạy cảm theo quyền được cấp; **không đăng nguyên output lên chat/ticket/log công khai**. Khi cần chia sẻ, mask credentials, endpoints nội bộ và secret references theo chính sách.

### 17.8. Xem platform versions có sẵn

~~~bash
aws elasticbeanstalk list-platform-versions \
  --region ap-southeast-1
~~~

Tùy kết quả, lọc theo PlatformBranchName/PlatformVersion/PlatformStatus để tìm Java SE/Tomcat và kiểm tra trạng thái hỗ trợ. Đây là cách tránh dùng **một platform cũ đã deprecated** chỉ vì có trong tutorial.

### 17.9. Đối chiếu thêm ALB/ASG

Nếu **describe-environment-resources** trả lại ASG/load balancer liên quan, có thể dùng AWS CLI tương ứng:

~~~bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names example-eb-asg \
  --region ap-southeast-1

aws elbv2 describe-load-balancers \
  --names example-eb-alb \
  --region ap-southeast-1
~~~

Tên trong đoạn code là **placeholder**, phải thay bằng tên resource thực tế. Các lệnh chỉ đọc có thể trả AccessDenied nếu role thiếu IAM permissions.

## 18. Kiểm soát chi phí và vòng đời

### 18.1. Elastic Beanstalk có phí riêng không?

**Elastic Beanstalk không thu phí bổ sung riêng cho chính dịch vụ triển khai**, nhưng tài nguyên mà environment tạo ra hoặc kết nối tới **vẫn tính phí theo các dịch vụ AWS tương ứng**.

| Tài nguyên | Chi phí có thể phát sinh |
| --- | --- |
| **Amazon EC2** | Instance hours, loại instance, Savings Plans/Reserved/Spot nếu áp dụng. |
| **Elastic Load Balancing** | Load balancer hours và LCU/đơn vị tính phí tương ứng. |
| **Amazon EBS** | Volume provisioned, snapshot. |
| **Amazon S3** | Lưu application bundles, logs, backup, request/transfer. |
| **Amazon RDS/Aurora** | DB instance/storage/IO/backup/transfer. |
| **CloudWatch** | Logs, metrics, alarms, log retention. |
| **VPC networking** | NAT Gateway, data processing, VPC endpoints, data transfer. |
| **Route 53 / ACM / WAF** | DNS hosted zone/queries, các thành phần certificate/edge security theo bảng giá. |

Một environment **không có người dùng** vẫn có thể phát sinh phí vì EC2/ALB/RDS/NAT đang chạy. Số tiền thực phụ thuộc Region, giờ hoạt động, dữ liệu và cấu hình.

### 18.2. Lab nhỏ tối ưu chi phí thế nào?

- Tạo **single-instance** nếu mục tiêu chỉ là hiểu deployment và health trong thời gian lab.
- Chọn instance phù hợp với **Java heap/CPU**, không chọn máy quá nhỏ khiến JVM liên tục OOM.
- Không tạo RDS/NAT/ALB nếu bài lab chưa thực sự cần, trừ khi đang học chính thành phần đó.
- Theo dõi AWS Budgets/Cost Explorer và gắn tag owner/environment.
- Sau lab, xác minh việc **terminate environment** và kiểm tra tài nguyên còn sót, **không xóa database quan trọng**.
- Giảm log retention phù hợp, xóa application versions/artifacts cũ theo chính sách.
- Với production, so sánh tổng chi phí/tính năng với ECS Fargate, App Runner hoặc EC2 tự quản; không mặc định Beanstalk luôn rẻ nhất.

### 18.3. Kiểm soát platform maintenance

- Theo dõi platform branch/version support và security patches.
- Cân nhắc **managed platform updates** trong maintenance window thích hợp.
- Kiểm thử environment staging trước khi nâng runtime/OS.
- Giữ snapshot cấu hình/IaC, application artifact và database rollback plan.
- Không chờ platform hết hỗ trợ rồi mới bắt đầu kiểm thử nâng cấp.

Java runtime và Spring dependencies có lifecycle độc lập. EB nâng Amazon Linux/Corretto không thay thế việc nâng Spring Boot/Log4j/JDBC driver và xử lý CVE ở ứng dụng.

## 19. So sánh Beanstalk với các lựa chọn triển khai Java khác

| Tiêu chí | **Elastic Beanstalk** | **EC2 tự quản** | **ECS Fargate** | **AWS App Runner** | **AWS Lambda Java** |
| --- | --- | --- | --- | --- | --- |
| Mức trừu tượng | PaaS triển khai ứng dụng lên stack EC2/ELB/ASG do EB quản lý. | Nhóm tự cấu hình gần như toàn bộ. | Container tasks/services, hạ tầng compute do Fargate cấp. | Managed web application/container service. | Function theo invocation/event. |
| Artifact | JAR/WAR/source bundle theo platform. | Tùy ý: JAR, WAR, Docker, AMI. | Container image/task definition. | Source/image theo tính năng hỗ trợ. | Function artifact/image theo runtime. |
| Máy chủ | EB quản lý lifecycle nhưng tài nguyên EC2 tồn tại. | Nhóm trực tiếp quản lý EC2. | Không quản lý EC2 host. | Trừu tượng hóa host ở mức cao. | Không quản lý server thường trực. |
| Scaling | EB cấu hình EC2 ASG cho load-balanced env. | Tự tạo/điều chỉnh ASG và ELB. | ECS Service Auto Scaling task count. | Service autoscaling theo lựa chọn. | Concurrency theo request/event và quota. |
| Kiểm soát OS | Có theo platform nhưng phải tuân cơ chế EB. | Cao nhất. | Hạn chế host, tập trung container. | Hạn chế hạ tầng nền. | Không kiểm soát host OS. |
| Khi phù hợp | Java web/API muốn deploy nhanh nhưng cần cấu hình EC2/ELB/VPC. | Legacy/agent/OS customization sâu. | Microservices container, cần ECS ecosystem. | Web app muốn giảm vận hành hạ tầng hơn nữa. | Event-driven/short-lived functions, theo giới hạn runtime. |
| Trade-off | Platform lifecycle, EB conventions và EC2 cost. | Tốn vận hành nhiều. | Cần containerization và điều phối tasks. | Giới hạn cấu hình/integration theo dịch vụ. | Cold starts, timeout/concurrency/event model. |

**Không có đáp án đúng tuyệt đối.** Nếu dự án là Spring Boot API luôn chạy, Beanstalk Java SE có thể giúp khởi đầu nhanh. Nếu đã có Docker pipeline và nhiều microservices, ECS Fargate có thể phù hợp hơn. Nếu workload thực chất là xử lý event, Lambda có thể phù hợp với giới hạn xử lý và kiến trúc cần thiết.

## 20. Bài tập tình huống

### Bài tập A — Deploy Spring Boot JAR bị 502

**Bối cảnh:** Team upload ZIP chứa app.jar/Procfile. Java logs cho thấy Tomcat embedded đã start ở port 8080. Truy cập environment URL trả 502.

**Câu hỏi:** Chỗ nào cần kiểm tra trước?

**Gợi ý lời giải:** Xem **Procfile**, **server.port** và port upstream của Nginx trong Java SE platform. Nếu proxy mặc định chuyển tới 5000 mà app lắng nghe 8080, chỉnh app hoặc proxy cho khớp rồi deploy lại. Kiểm tra health qua chính URL môi trường. Không mở cổng 8080 public nếu proxy chỉ cần kết nối nội bộ.

### Bài tập B — Version mới yêu cầu Java 21

**Bối cảnh:** Ứng dụng đã nâng source/bytecode lên Java 21 nhưng environment còn Corretto 17.

**Câu hỏi:** Tăng EC2 size có giải quyết không?

**Gợi ý lời giải:** Không. Cần chọn platform branch Java SE hỗ trợ Corretto 21 (nếu đang được AWS hỗ trợ trong Region), kiểm thử runtime/dependencies và lên kế hoạch cập nhật/blue-green phù hợp. UnsupportedClassVersionError là mismatch Java version, không phải thiếu CPU/RAM.

### Bài tập C — Muốn zero downtime khi deploy

**Bối cảnh:** API production phục vụ khách hàng liên tục, có 4 EC2 sau ALB. Release chứa Java code mới nhưng không thay database schema phá vỡ backward compatibility.

**Câu hỏi:** Chọn policy nào?

**Gợi ý lời giải:** Đánh giá **rolling with additional batch**, **immutable** hoặc **traffic splitting** theo quota, cost và yêu cầu canary. Với mức độ rủi ro cao, **blue/green** cho phép kiểm thử environment mới và chuyển traffic theo kế hoạch. Bất kỳ lựa chọn nào cũng cần health, startup, graceful shutdown và rollback test.

### Bài tập D — Database mất khi xóa lab environment

**Bối cảnh:** Môi trường dev có database được tạo cùng EB environment. Team muốn terminate environment.

**Câu hỏi:** Có thể xóa ngay không?

**Gợi ý lời giải:** Chưa. Phải xác định database có gắn lifecycle environment không, dữ liệu nào cần giữ, backup/retention và quy trình decouple RDS theo hỗ trợ của AWS. Chỉ terminate sau khi đã xác nhận dữ liệu được bảo toàn hoặc chấp nhận mất theo mục tiêu lab.

### Bài tập E — Scale EC2 nhưng API vẫn timeout

**Bối cảnh:** Khi traffic tăng, EB Auto Scaling tăng 2 lên 8 EC2, CPU mỗi EC2 giảm nhưng API vẫn timeout với database connection errors.

**Câu hỏi:** Nguyên nhân có thể?

**Gợi ý lời giải:** DB connection pool nhân theo số instances làm DB quá giới hạn; query chậm/locks hoặc RDS resource bottleneck. Cần kiểm tra connections, pool size, transaction duration, RDS metrics và cân nhắc RDS Proxy hoặc nâng năng lực database. Scale EC2 không tự sửa backend bottleneck.

### Bài tập F — CI muốn deploy artifact có thể tái lập

**Bối cảnh:** Pipeline hiện chạy Maven build trực tiếp trên các EC2 của Beanstalk mỗi lần deploy, dependency downloads thất thường làm rollout chậm.

**Câu hỏi:** Nên thay workflow thế nào?

**Gợi ý lời giải:** CI build/test trên runner được kiểm soát, lưu **versioned JAR/source bundle** bất biến, tạo EB application version và deploy cùng artifact qua dev/staging/prod; dùng checksums/version labels và giữ release history. Tránh để mỗi EC2 tự tải dependency theo cách không kiểm soát.

### Bài tập G — Multiple AZ nhưng mất session login

**Bối cảnh:** Sau khi tăng Auto Scaling lên hai AZ, một số người dùng liên tục bị đăng xuất.

**Câu hỏi:** Beanstalk lỗi hay ứng dụng thiếu gì?

**Gợi ý lời giải:** Có thể app lưu session trong memory của từng JVM; request tiếp theo tới EC2 khác không có session. Cần đưa session state ra shared store/ứng dụng stateless (ví dụ token/ElastiCache khi phù hợp), xem ALB stickiness chỉ như một lựa chọn có trade-off, không phải chiến lược duy nhất cho tính sẵn sàng.

## 21. Sai lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Elastic Beanstalk là Lambda nên không cần trả phí EC2.” | EB Java web environment thông thường vẫn chạy trên EC2 và tính phí tài nguyên nền. |
| “Application và Environment là cùng một đối tượng.” | Application quản lý versions/environments; một application có nhiều environments độc lập. |
| “Java SE platform nhận mọi WAR mà không cần cấu hình.” | Executable JAR phù hợp Java SE; external Tomcat WAR nên dùng Tomcat platform tương thích. |
| “App chạy local port 8080 thì EB proxy tự biết.” | Phải khớp cổng Java process với proxy configuration, thường 5000 trên Java SE mặc định. |
| “Upload ZIP chứa thư mục deploy/ là đủ.” | Procfile và app.jar cần nằm đúng cấp root source bundle/đường dẫn được cấu hình. |
| “Beanstalk tự xây dựng database HA và backup đầy đủ.” | Database lifecycle, HA/backup/RPO/RTO là trách nhiệm thiết kế riêng. |
| “Đã có ALB thì ứng dụng luôn multi-AZ/HA.” | Còn cần ASG MinSize, subnet AZ, healthy instances, data store và failover tests. |
| “Đặt secret trong .ebextensions rồi commit Git là bình thường.” | Không commit plaintext secret; dùng secret manager/secure references theo khả năng hỗ trợ. |
| “Có IAM service role nghĩa là Java app có quyền S3.” | App trên EC2 thường dùng instance profile; hai vai trò khác nhau. |
| “Rolling deployment không cần headroom capacity.” | Rolling có thể giảm số instances phục vụ trong lúc triển khai, cần tính tải và batch sizes. |
| “Immutable deploy thì chắc chắn rollback database được.” | Deployment rollback không tự hoàn tác migration/dữ liệu. |
| “Terminate chỉ xóa Java process.” | Có thể xóa EC2/ELB/ASG và các resource environment; database gắn lifecycle có rủi ro. |
| “Scale-out EC2 giải quyết mọi 502/timeout.” | Có thể lỗi code, port, IAM, network, DB, JVM memory hoặc downstream. |
| “Beanstalk health green nghĩa là mọi nghiệp vụ đều đúng.” | Health là tín hiệu kỹ thuật, không thay business testing và SLO monitoring. |
| “CNAME swap chuyển 100% users ngay lập tức.” | DNS caching và connection reuse có thể giữ traffic tại phiên bản cũ. |
| “Managed platform update không cần regression test.” | OS/runtime/library upgrades có thể gây lỗi; cần staging và rollback plan. |

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Elastic Beanstalk Application khác Environment thế nào?  
**Đáp án:** Application nhóm versions và environments; environment là tập tài nguyên đang chạy một phiên bản/cấu hình cụ thể.

**Câu 2.** Khi nào chọn Java SE platform thay vì Tomcat platform?  
**Đáp án:** Với Spring Boot executable JAR có embedded HTTP server, Java SE phù hợp; WAR cần external Tomcat thì chọn Tomcat platform tương thích.

**Câu 3.** Procfile tối thiểu cho Java SE JAR tên app.jar có nội dung gì?  
**Đáp án:** **web: java -jar app.jar**, đặt tại root source bundle.

**Câu 4.** Vì sao Java app port 8080 có thể làm Nginx trả 502?  
**Đáp án:** Nếu proxy của EB đang trỏ tới localhost:5000 thì không có process lắng nghe cổng đó; cần đồng bộ app/proxy port.

**Câu 5.** EB platform version và application version khác gì?  
**Đáp án:** Platform version xác định OS/runtime và tooling; application version xác định artifact/mã nguồn ứng dụng được triển khai.

**Câu 6.** Single-instance environment có phù hợp production HA mặc định không?  
**Đáp án:** Không. Nó thường không có ALB/multiple instances và có thể gián đoạn khi EC2 gặp sự cố.

**Câu 7.** Vì sao file upload không nên nằm duy nhất trên filesystem của EC2 trong EB environment?  
**Đáp án:** EC2 có thể được thay thế/scale; instance khác không tự có các file đó. Dữ liệu bền nên lưu S3/EFS hoặc datastore phù hợp.

**Câu 8.** IAM service role khác EC2 instance profile thế nào?  
**Đáp án:** Service role cho EB quản trị/tích hợp; instance profile cấp quyền cho EC2/ứng dụng chạy trên instance.

**Câu 9.** Một JAR cần Java 21 nhưng runtime là Java 17 sẽ có lỗi gì?  
**Đáp án:** Có thể gặp UnsupportedClassVersionError; cần platform/runtime tương thích, không phải tăng CPU.

**Câu 10.** Có nên ghi database password trực tiếp trong pom.xml, Procfile hoặc .ebextensions rồi commit không?  
**Đáp án:** Không. Dùng Secrets Manager/Parameter Store hoặc secret references được platform hỗ trợ và IAM/KMS least privilege.

**Câu 11.** ALB dùng certificate ACM có đảm bảo dữ liệu mã hóa trên đoạn ALB → EC2 không?  
**Đáp án:** Không tự động; phải kiểm tra target protocol và cấu hình backend TLS nếu chính sách yêu cầu.

**Câu 12.** Rolling deployment có thể giảm capacity đang phục vụ không?  
**Đáp án:** Có. Các batches cập nhật có thể tạm không phục vụ, nên cần headroom hoặc rolling with additional batch.

**Câu 13.** Blue/green khác immutable deployment ở điểm nào?  
**Đáp án:** Blue/green dùng hai environments độc lập và chuyển traffic/CNAME; immutable tạo fleet mới trong quy trình triển khai của environment hiện tại.

**Câu 14.** Sau khi thay code rollback thành công, schema database có tự rollback không?  
**Đáp án:** Không. Schema/data migrations cần kế hoạch tương thích và rollback riêng.

**Câu 15.** Khi cần truy lỗi 502 Java, kiểm tra những nguồn nào đầu tiên?  
**Đáp án:** EB events/health, application startup logs, Nginx error logs, Procfile/port và ALB target health.

**Câu 16.** Elastic Beanstalk có tính phí dịch vụ riêng không?  
**Đáp án:** Không có phí bổ sung riêng cho chính Elastic Beanstalk; EC2, ALB, EBS, RDS, NAT, S3, CloudWatch và các dịch vụ dùng kèm vẫn tính phí.

**Câu 17.** Vì sao tăng số EC2 có thể làm database timeout nặng hơn?  
**Đáp án:** Tổng DB connections/requests tăng; nếu bottleneck ở DB, scale web tier có thể gây quá tải thêm.

**Câu 18.** Lệnh AWS CLI nào xem sự kiện environment mà không thay đổi tài nguyên?  
**Đáp án:** **aws elasticbeanstalk describe-events --environment-name ...**.

**Câu 19.** Việc kết thúc lab nên kiểm tra điều gì trước khi terminate?  
**Đáp án:** Database lifecycle, backup, dữ liệu cần giữ, EC2/ELB/NAT/EBS và các tài nguyên phát sinh chi phí.

**Câu 20.** Tại sao một environment health ổn định chưa đủ để chứng minh phát hành thành công?  
**Đáp án:** Cần smoke tests, business checks, latency/5xx, database consistency và tình trạng người dùng thực tế.

## 23. Tổng kết và checklist triển khai production

**Triển khai Java trên Elastic Beanstalk** là quy trình đưa một executable JAR hoặc WAR vào **application version**, chọn **Java SE/Tomcat platform**, tạo **environment** và để EB phối hợp EC2, Auto Scaling, load balancer, health và lifecycle triển khai.

Checklist ngắn cho một Spring Boot API:

1. **Build:** JDK/Corretto compatible, Maven tests PASS, executable JAR và version label rõ ràng.
2. **Artifact:** source bundle ZIP có **app.jar + Procfile** ở root, không có credentials.
3. **Platform:** chọn Java SE platform được AWS hỗ trợ, port app/proxy khớp, dependency tương thích.
4. **Environment:** load-balanced, multi-AZ khi cần, VPC/subnet/SG đúng ranh giới bảo mật.
5. **IAM:** service role và EC2 instance profile tách biệt, quyền S3/Secrets/KMS tối thiểu.
6. **Data:** RDS/backup/replication độc lập environment; S3 cho file bền, session state không phụ thuộc một EC2.
7. **HTTPS:** Route 53/ACM/ALB, listener/redirect và forwarded headers tin cậy.
8. **Health:** readiness path chính xác, ALB targets healthy, enhanced health và CloudWatch logs/alarms.
9. **Release:** chọn rolling/immutable/traffic splitting hoặc blue-green phù hợp; migrations backward-compatible và rollback thử trước.
10. **Scaling:** min/max EC2, load testing, database pool size, startup/warmup và multi-AZ failover.
11. **Cost:** theo dõi EC2/ALB/RDS/NAT/EBS/CloudWatch, gắn tags và xóa lab có kiểm soát.
12. **Maintenance:** nâng platform/Java/Spring đúng vòng đời, staging regression test và audit thay đổi.

Elastic Beanstalk giúp nhóm giảm công việc quản lý deployment và phối hợp hạ tầng, nhưng **sự sẵn sàng, an toàn dữ liệu và chất lượng ứng dụng Java vẫn cần được thiết kế và đo lường**. Chọn đúng platform, cấu trúc bundle, port, health, IAM và database lifecycle sẽ giúp tránh phần lớn sự cố triển khai thực tế.

### Tài liệu AWS chính thức

- [What is AWS Elastic Beanstalk?](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/Welcome.html) — tổng quan application, environment, platform.
- [Java SE platform](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/java-se-platform.html) — Java SE, Procfile và Java application.
- [Tomcat platform](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/java-tomcat-platform.html) — triển khai web application WAR trên Tomcat.
- [Configuring Elastic Beanstalk environments](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.managing.html) — environment configuration.
- [Platform hooks](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.hooks.html) — .platform/hooks trên Amazon Linux platforms.
- [Environment configuration files](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/ebextensions.html) — .ebextensions config và option settings.
- [Deployment policies and settings](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.rolling-version-deploy.html) — rolling, immutable và các lựa chọn deploy.
- [Blue/green deployments](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.CNAMESwap.html) — hai environments và chuyển traffic.
- [Elastic Beanstalk security](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/security.html) — IAM, service roles và instance profiles.
- [Enhanced health reporting](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/health-enhanced.html) — health và diagnostics.
- [EB CLI command reference](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3.html) — init, create, deploy, logs, health và terminate.
- [Elastic Beanstalk pricing](https://aws.amazon.com/elasticbeanstalk/pricing/) — tài nguyên được tính phí.

