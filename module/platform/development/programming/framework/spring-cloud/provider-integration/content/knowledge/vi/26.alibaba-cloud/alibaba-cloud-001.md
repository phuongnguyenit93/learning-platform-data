# Phân biệt Spring Cloud Alibaba và starter dịch vụ Alibaba Cloud

## 1. Bài toán và mục tiêu học tập

Một ứng dụng Spring Boot chạy trên Alibaba Cloud có thể cần đăng ký service vào Nacos, giới hạn lưu lượng bằng Sentinel, lưu file lên Object Storage Service (OSS), gửi SMS hoặc truy cập Redis managed. Các nhu cầu này đều thuộc hệ sinh thái Alibaba Cloud, nhưng không nhất thiết dùng cùng một bộ dependency.

Tên **Spring Cloud Alibaba**, **Aliyun Spring Boot Starter** và **Alibaba Cloud Java SDK** thường xuất hiện cạnh nhau trong tài liệu. Chúng có quan hệ với nhau nhưng giải quyết các lớp tích hợp khác nhau:

- **Spring Cloud Alibaba (SCA)** cung cấp các thành phần theo mô hình Spring Cloud để xây dựng microservice phân tán: service discovery/configuration với Nacos, flow control với Sentinel, distributed transaction với Seata và messaging với RocketMQ.
- **Aliyun Spring Boot Starters** cung cấp auto-configuration và starter theo từng dịch vụ Alibaba Cloud như OSS, SMS, Redis, RDS MySQL hoặc SchedulerX. Nhóm này hướng tới cách sử dụng dịch vụ từ Spring Boot.
- **Alibaba Cloud Java SDK** là client API của từng sản phẩm. Ứng dụng gọi trực tiếp SDK để dùng chức năng của dịch vụ; có thể bọc client trong Spring bean hoặc tự xây adapter nếu không có starter phù hợp.

Bài học thuộc chương **Alibaba Cloud** trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure, Google Cloud và Alibaba Cloud qua thư viện tương ứng; người học cần biết cấu hình danh tính/quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa provider.

Sau bài học, bạn có thể:

1. Phân biệt mục tiêu và phạm vi của Spring Cloud Alibaba, Aliyun Spring Boot Starters và SDK sản phẩm.
2. Chọn đúng BOM, starter và dependency theo bài toán.
3. Hiểu vì sao version của Spring Cloud Alibaba không tự động quản lý version của mọi SDK dịch vụ Alibaba Cloud.
4. Cấu hình Nacos discovery và tích hợp OSS bằng SDK hoặc starter.
5. Chọn RAM user, RAM role, STS hoặc OIDC phù hợp với môi trường chạy.
6. Kiểm thử từng lớp tích hợp và chẩn đoán lỗi dependency, credentials, endpoint, region hoặc permission.

## 2. Ba lớp tích hợp cần nhận diện

~~~mermaid
flowchart TD
    APP["Spring Boot application"]
    SCA["Spring Cloud Alibaba<br/>Microservice integration"]
    STARTER["Aliyun Spring Boot Starters<br/>Service-specific auto-configuration"]
    SDK["Alibaba Cloud Java SDK<br/>Product API client"]
    NACOS["Nacos / Sentinel / Seata / RocketMQ"]
    SERVICE["OSS / SMS / Redis / RDS / SchedulerX"]
    API["Product REST/OpenAPI or SDK API"]

    APP --> SCA
    APP --> STARTER
    APP --> SDK
    SCA --> NACOS
    STARTER --> SERVICE
    SDK --> API
~~~

| Lớp | Câu hỏi nó trả lời | Ví dụ thành phần | Dependency/BOM tiêu biểu |
| --- | --- | --- | --- |
| **Spring Cloud Alibaba** | Các microservice đăng ký, khám phá, quản lý cấu hình, điều tiết traffic hoặc giao tiếp phân tán thế nào? | Nacos Discovery/Config, Sentinel, Seata, RocketMQ integration | BOM **spring-cloud-alibaba-dependencies** và starter **spring-cloud-starter-alibaba-...** |
| **Aliyun Spring Boot Starters** | Ứng dụng Spring Boot cấu hình và sử dụng một dịch vụ Alibaba Cloud cụ thể ra sao? | OSS, SMS, Redis, RDS MySQL, SchedulerX | BOM **aliyun-spring-boot-dependencies** và starter **aliyun-...-spring-boot-starter** |
| **Java SDK sản phẩm** | Làm thế nào gọi API cụ thể của một sản phẩm với đầy đủ request/response và tính năng của SDK? | OSS Java SDK, OpenAPI SDK của ECS, SLS hoặc sản phẩm khác | Dependency SDK do sản phẩm phát hành, ví dụ **aliyun-sdk-oss** |

**Điểm mấu chốt:** Spring Cloud Alibaba không phải tên chung cho tất cả starter dịch vụ của Alibaba Cloud. Nó là một dự án tích hợp microservice theo mô hình Spring Cloud. Bộ starter dịch vụ được phát triển trong dự án **aliyun-spring-boot**, có BOM riêng. SDK sản phẩm lại có vòng đời và cách cấu hình riêng.

### 2.1. Ví dụ để nhận ra sự khác nhau

- Một service cần **đăng ký tên service, địa chỉ instance và khám phá service khác**: dùng Nacos Discovery qua Spring Cloud Alibaba.
- Một service cần **giới hạn request, circuit breaking và degrade**: dùng Sentinel integration qua Spring Cloud Alibaba.
- Một service cần **upload/download file từ OSS**: dùng Aliyun OSS Spring Boot Starter nếu phiên bản và tính năng phù hợp, hoặc OSS Java SDK trực tiếp.
- Một service cần **gửi SMS**: xem Aliyun SMS Spring Boot Starter; nếu cần API mới hoặc tham số chưa được starter bọc, dùng SDK của SMS.
- Một service cần **một API sản phẩm đặc thù** chưa có starter: dùng SDK/OpenAPI client của sản phẩm và tự cấu hình bean.

Nacos, Sentinel, Seata và RocketMQ là các thành phần middleware/giải pháp microservice. Chúng có thể được tự vận hành hoặc dùng thông qua dịch vụ managed tương thích, chẳng hạn nền tảng MSE/EDAS tùy sản phẩm. OSS, SMS và RDS là dịch vụ cloud cụ thể với API và quyền truy cập riêng.

## 3. Spring Cloud Alibaba làm gì?

### 3.1. Phạm vi chức năng

Spring Cloud Alibaba kết nối ứng dụng Spring Cloud với các giải pháp microservice của Alibaba theo programming model của Spring. Những nhóm chức năng tiêu biểu:

| Năng lực | Thành phần | Vai trò |
| --- | --- | --- |
| Service registration/discovery | **Nacos Discovery** | Đăng ký instance và tìm địa chỉ service khác |
| Externalized configuration | **Nacos Config** | Lấy cấu hình tập trung và hỗ trợ cập nhật cấu hình |
| Flow control/circuit breaking | **Sentinel** | Rate limiting, circuit breaking, degradation và system protection |
| Distributed transaction | **Seata** | Hỗ trợ quản lý giao dịch phân tán theo mô hình Seata |
| Distributed messaging | **RocketMQ integration** | Kết nối ứng dụng Spring với RocketMQ |
| Job scheduling | **SchedulerX integration** trong các nhánh hỗ trợ | Tích hợp lịch chạy job phân tán |

SCA giúp ứng dụng dùng các abstraction, annotation và auto-configuration theo Spring. Nó không biến Nacos, Sentinel hay RocketMQ thành một API chung để truy cập OSS hoặc SMS.

### 3.2. Ví dụ Nacos Discovery

Maven BOM và starter minh họa:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>spring-cloud-alibaba-dependencies</artifactId>
            <version>${springCloudAlibabaVersion}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.alibaba.cloud</groupId>
        <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
    </dependency>
</dependencies>
~~~

Cấu hình ví dụ:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    nacos:
      discovery:
        server-addr: ${NACOS_SERVER_ADDR}
        namespace: ${NACOS_NAMESPACE}
~~~

Trong môi trường thực tế, địa chỉ Nacos, namespace, group, credentials và TLS phải được cấu hình theo cluster/tenant đang dùng. Không đưa mật khẩu Nacos hoặc token vào YAML được commit lên Git.

Khi ứng dụng khởi động, integration của Nacos Discovery đăng ký instance theo cấu hình. Một service khác có thể tìm service theo tên thông qua cơ chế discovery tương ứng của Spring Cloud. Đây là **service governance/discovery**, không phải thao tác upload file hay gửi SMS.

### 3.3. Ví dụ Sentinel

Sentinel tích hợp vào luồng request để áp dụng rule bảo vệ. Ứng dụng cần starter tương ứng và cấu hình dashboard/transport/rule theo phiên bản.

~~~xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-sentinel</artifactId>
</dependency>
~~~

Ví dụ khái niệm: giới hạn endpoint tạo đơn ở 100 request/giây và trả về phản hồi degrade khi vượt rule. Sentinel điều khiển traffic của ứng dụng; nó không phải hàng đợi message thay thế SQS/RocketMQ và không phải SDK gọi dịch vụ cloud.

### 3.4. Khi nào không cần Spring Cloud Alibaba?

Nếu ứng dụng chỉ là một Spring Boot service đơn giản cần upload file lên OSS, không có nhu cầu service discovery, centralized config, traffic governance hoặc distributed transaction, không cần thêm toàn bộ Spring Cloud Alibaba chỉ vì ứng dụng chạy trên Alibaba Cloud.

Chọn đúng starter dịch vụ hoặc SDK OSS sẽ giảm số dependency, cấu hình và thành phần vận hành không cần thiết. Có thể bổ sung SCA sau khi kiến trúc microservice thật sự cần các năng lực đó.

## 4. Aliyun Spring Boot Starters làm gì?

### 4.1. Tích hợp theo sản phẩm

Dự án **aliyun-spring-boot** cung cấp Spring Boot starters cho các dịch vụ Alibaba Cloud. Danh sách được công bố gồm những module như:

| Dịch vụ | Starter artifact được công bố | Mục đích |
| --- | --- | --- |
| Object Storage Service | **aliyun-oss-spring-boot-starter** | Upload/download object và thao tác bucket |
| Short Message Service | **aliyun-sms-spring-boot-starter** | Gửi SMS và tích hợp tham số dịch vụ SMS |
| Redis | **aliyun-redis-spring-boot-starter** | Kết nối Redis managed |
| RDS MySQL | **aliyun-rds-spring-boot-starter** | Hỗ trợ tích hợp với RDS MySQL |
| SchedulerX | **aliyun-schedulerx-spring-boot-starter** | Tích hợp lịch chạy job |
| Function Compute | **aliyun-fc-spring-boot-starter** | Tích hợp một số khả năng Function Compute |

Tên starter là artifactId, không phải tên Java package hay tên sản phẩm. Kiểm tra README và tài liệu của đúng phiên bản trước khi copy cấu hình. Không suy ra property names của OSS từ property names của SMS hoặc Redis.

### 4.2. BOM riêng cho service starters

BOM của Aliyun Spring Boot Starters có tọa độ riêng:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>aliyun-spring-boot-dependencies</artifactId>
            <version>${aliyunSpringBootVersion}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó thêm starter cần dùng, ví dụ OSS:

~~~xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>aliyun-oss-spring-boot-starter</artifactId>
</dependency>
~~~

**Không thay BOM này bằng spring-cloud-alibaba-dependencies.** Hai BOM quản lý hai nhóm artifact khác nhau. Tài liệu của Spring Cloud Alibaba cũng chỉ rõ muốn dùng Spring Boot starters cho dịch vụ Alibaba Cloud thì cần thêm Aliyun Spring Boot BOM.

Dự án starter và SCA có lịch phát hành, phạm vi hỗ trợ và ma trận tương thích riêng. Đừng lấy bảng tương thích Spring Boot/Spring Cloud của SCA rồi mặc định áp dụng cho tất cả Aliyun service starters. Trước khi dùng, xác nhận version được publish trên Maven Central, yêu cầu Java/Spring Boot và SDK transitive dependencies.

### 4.3. Starter thường mang lại gì?

Một starter tốt thường kết hợp một số phần:

- Dependency tới SDK sản phẩm.
- Auto-configuration tạo client hoặc template bean.
- Property binding cho endpoint, region, bucket hoặc thông số kết nối.
- Conditional configuration để ứng dụng có thể ghi đè bean mặc định.
- Tích hợp với lifecycle của Spring, chẳng hạn đóng client khi context shutdown.
- Có thể có abstraction hoặc helper để giảm mã cấu hình.

Mức độ hỗ trợ không giống nhau giữa các starter. Cần đọc tài liệu và source/sample của module đang dùng để biết nó tạo bean nào, cấu hình gì và API nào được bọc. Starter không làm mất nhu cầu hiểu RAM permission, endpoint, region, network và quota của dịch vụ.

## 5. SDK sản phẩm trực tiếp làm gì?

### 5.1. Khi nào nên dùng SDK?

Dùng SDK trực tiếp khi:

- Chưa có starter phù hợp với sản phẩm.
- Starter hiện có không hỗ trợ API hoặc tính năng cần thiết.
- Cần kiểm soát request/response, retry, timeout, multipart upload hoặc metadata chi tiết.
- Muốn kiểm soát rõ phiên bản SDK và thời điểm nâng cấp.
- Muốn viết một adapter nội bộ để tách domain service khỏi API nhà cung cấp.

SDK thường cung cấp client theo sản phẩm. Ứng dụng phải tự quyết định cách tạo client, lấy credentials, chọn region/endpoint, quản lý connection pool, đóng client và ánh xạ lỗi sang exception nghiệp vụ.

### 5.2. Ví dụ dependency OSS Java SDK

Tài liệu OSS Java SDK V1 công bố Maven coordinates:

~~~xml
<dependency>
    <groupId>com.aliyun.oss</groupId>
    <artifactId>aliyun-sdk-oss</artifactId>
    <version>${aliyunOssSdkVersion}</version>
</dependency>
~~~

Tài liệu hiện hành có ví dụ dependency version **3.18.4**; trong dự án thật hãy chọn bản đã kiểm tra trên Maven Repository và quản lý bằng version catalog/property. OSS Java SDK V2 có artifact riêng, không thay thế dependency V1 bằng cách chỉ đổi version.

### 5.3. Đóng gói SDK thành Spring bean

Ví dụ dưới đây dùng OSS Java SDK V1 và credentials từ environment variables theo hướng dẫn SDK:

~~~java
package demo.storage;

import com.aliyun.oss.ClientBuilderConfiguration;
import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSClientBuilder;
import com.aliyun.oss.common.auth.CredentialsProvider;
import com.aliyun.oss.common.auth.CredentialsProviderFactory;
import com.aliyun.oss.common.comm.SignVersion;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OssClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    public OSS ossClient(
            @Value("${aliyun.oss.endpoint}") String endpoint,
            @Value("${aliyun.oss.region}") String region) {

        CredentialsProvider credentialsProvider =
                CredentialsProviderFactory
                        .newEnvironmentVariableCredentialsProvider();

        ClientBuilderConfiguration clientConfig =
                new ClientBuilderConfiguration();
        clientConfig.setSignatureVersion(SignVersion.V4);

        return OSSClientBuilder.create()
                .credentialsProvider(credentialsProvider)
                .clientConfiguration(clientConfig)
                .region(region)
                .endpoint(endpoint)
                .build();
    }
}
~~~

Ví dụ dùng các environment variables **OSS_ACCESS_KEY_ID** và **OSS_ACCESS_KEY_SECRET** theo provider tương ứng của SDK V1. Không ghi giá trị thật vào source code hoặc YAML. Trong workload chạy trên Alibaba Cloud, ưu tiên cơ chế credentials ngắn hạn/RAM role phù hợp với môi trường thay vì AccessKey tĩnh.

Client OSS có thể được tái sử dụng như một singleton Spring bean; không tạo mới client cho mỗi lần upload. Client quản lý connection pool và cần được đóng khi ứng dụng dừng.

### 5.4. Dùng client trong service

~~~java
package demo.storage;

import com.aliyun.oss.OSS;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.InputStream;

@Service
public class ObjectStorageService {
    private final OSS ossClient;
    private final String bucketName;

    public ObjectStorageService(
            OSS ossClient,
            @Value("${aliyun.oss.bucket}") String bucketName) {
        this.ossClient = ossClient;
        this.bucketName = bucketName;
    }

    public void upload(String objectKey, InputStream content) {
        ossClient.putObject(bucketName, objectKey, content);
    }
}
~~~

Đoạn code chỉ minh họa ranh giới adapter. Trong production cần kiểm tra kích thước/loại file, quyền ghi đúng bucket/prefix, xử lý stream và metadata, chính sách overwrite, multipart upload cho file lớn, timeout, retry và log request ID. Không trả URL công khai cho object private nếu chưa có cơ chế kiểm soát truy cập phù hợp.

### 5.5. So sánh starter và SDK trực tiếp

| Tiêu chí | Service Spring Boot Starter | SDK trực tiếp |
| --- | --- | --- |
| Tạo client | Thường auto-configure | Ứng dụng tự tạo bean |
| Property binding | Có thể có sẵn theo starter | Tự định nghĩa ConfigurationProperties hoặc Value |
| Tích hợp lifecycle | Thường do auto-configuration quản lý | Tự cấu hình destroy/close |
| API sản phẩm | Phụ thuộc mức độ starter bọc | Thường truy cập API đầy đủ của SDK |
| Tùy biến | Theo extension point mà starter cung cấp | Kiểm soát client và request trực tiếp |
| Nâng cấp | Cần kiểm tra starter và SDK transitive cùng nhau | Chủ động chọn SDK version |
| Chi phí mã cấu hình | Ít hơn nếu starter phù hợp | Nhiều hơn nhưng minh bạch |
| Khi chọn | Nhu cầu phổ biến, starter được duy trì và tương thích | Tính năng mới/đặc thù hoặc cần kiểm soát sâu |

## 6. BOM và version compatibility: chọn đúng trước khi thêm dependency

### 6.1. BOM của Spring Cloud Alibaba

SCA có BOM **spring-cloud-alibaba-dependencies**. Nó quản lý các artifact thuộc Spring Cloud Alibaba và phiên bản thành phần mà dự án tích hợp. Cần phối hợp với Spring Cloud BOM và Spring Boot version.

Tại tài liệu nhánh 2025.x, các cặp tương thích được công bố gồm:

| Spring Cloud Alibaba | Spring Cloud | Spring Boot |
| --- | --- | --- |
| **2025.1.0.0** | **2025.1.x** | **4.0.x** |
| **2025.0.0.0** | **2025.0.x** | **3.5.x** |

Đây là ma trận theo nhánh tài liệu được tra cứu; luôn xem release notes mới nhất khi bắt đầu dự án. Không chọn SCA version chỉ vì nó là số lớn hơn. Không nâng riêng Nacos/Sentinel/RocketMQ lên phiên bản bất kỳ nếu BOM đã quản lý phiên bản tương thích.

Ví dụ Maven cho nhánh Spring Boot 3.5 / Spring Cloud 2025.0:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${springCloudVersion}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>spring-cloud-alibaba-dependencies</artifactId>
            <version>${springCloudAlibabaVersion}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Spring Boot parent/BOM phải được chọn tương thích với cặp trên. Không import một Spring Cloud release train khác với SCA chỉ vì build vẫn resolve được dependency.

### 6.2. BOM của Aliyun Spring Boot Starters

BOM **aliyun-spring-boot-dependencies** quản lý các starter của dự án Aliyun Spring Boot. Nó không phải BOM của SCA. Đọc release notes/README của chính project này để xác nhận tương thích Spring Boot và SDK sản phẩm.

Nếu một ứng dụng cần cả Nacos Discovery lẫn OSS Starter, có thể phải sử dụng cả hai bộ dependency, nhưng phải kiểm tra version convergence, các thư viện transitive và xung đột giữa các SDK. Không import cả hai BOM theo thói quen khi ứng dụng chỉ dùng một nhóm.

### 6.3. Version SDK sản phẩm

SDK sản phẩm có version độc lập:

- OSS Java SDK V1/V2 có lịch phát hành riêng.
- Alibaba Cloud OpenAPI SDK V2 sinh client theo sản phẩm/API version.
- Credentials tool, Tea/OpenAPI runtime và product SDK có dependency chung cần được giữ tương thích.

Tài liệu Alibaba Cloud SDK V2 liệt kê các package phổ biến như **credentials-java**, **tea**, **tea-openapi** và **tea-util**. Các package này thường được SDK sản phẩm kéo theo; chỉ thêm thủ công khi thiếu hoặc cần giải quyết conflict theo tài liệu.

Không dùng **spring-cloud-alibaba-dependencies** để đoán version OSS SDK. Cũng không mặc định Aliyun starter BOM quản lý mọi SDK mà ứng dụng tự thêm.

## 7. Danh tính, credentials và quyền truy cập Alibaba Cloud

### 7.1. RAM và AccessKey

Alibaba Cloud dùng **Resource Access Management (RAM)** để quản lý user, role và permission. Một ứng dụng chỉ cần truy cập bucket OSS nên có quyền phù hợp với bucket/prefix đó; không cấp **AdministratorAccess** hoặc **AliyunOSSFullAccess** nếu không cần.

| Môi trường | Cách xác thực nên xem xét |
| --- | --- |
| Máy phát triển | Alibaba Cloud CLI/profile hoặc environment variables cho RAM user test có quyền tối thiểu |
| ECS/ECI | RAM role gắn với instance; lấy credentials tạm thời qua instance metadata |
| ACK | OIDC/RRSA và RAM role cho workload/pod nếu cluster được cấu hình |
| Hệ thống bên ngoài Alibaba Cloud | STS/AssumeRole hoặc credentials URI/secret broker phù hợp |
| Legacy integration | RAM user AccessKey được lưu trong secret manager và xoay vòng theo chính sách |

Không dùng AccessKey của root account. Nếu cần AccessKey tĩnh, tạo RAM user chuyên biệt, cấp policy tối thiểu, lưu trong secret manager hoặc môi trường runtime an toàn và có kế hoạch xoay vòng.

### 7.2. Alibaba Cloud SDK V2 và Credentials tool

SDK V2 có công cụ quản lý credentials riêng. Default credential chain có thể tìm credentials từ system properties, environment variables, shared credentials file, OIDC RAM role và instance RAM role tùy môi trường/phiên bản.

Ví dụ cấu hình môi trường cho RAM user trong local test:

~~~text
ALIBABA_CLOUD_ACCESS_KEY_ID=<ram-user-access-key-id>
ALIBABA_CLOUD_ACCESS_KEY_SECRET=<ram-user-access-key-secret>
~~~

Đây chỉ là tên biến môi trường; không ghi giá trị thật vào tài liệu, file cấu hình hoặc log. Với ACK có RRSA/OIDC, có thể cấu hình RAM role ARN, OIDC provider ARN và token file để lấy STS credentials ngắn hạn. Với ECS/ECI, credentials tool có thể lấy RAM role từ instance metadata và tự refresh.

**Credentials tool nên được tái sử dụng** theo singleton/client lifecycle để tận dụng caching và tránh gọi lấy credentials quá thường xuyên. Nếu SDK V2 client dùng credential provider, truyền provider vào client config theo đúng API của SDK phiên bản đó.

### 7.3. Region và endpoint

Không phải mọi dịch vụ đều có cùng endpoint format. Cần phân biệt:

- **Region ID**: khu vực nơi resource được tạo.
- **Endpoint**: địa chỉ API của dịch vụ trong region, có thể là public, VPC/internal hoặc endpoint tùy sản phẩm.
- **Bucket/resource location**: region thực tế nơi resource tồn tại; không suy ra từ region của ứng dụng.

Với Alibaba Cloud OpenAPI SDK V2, cấu hình client có thể nhận **regionId** để resolve endpoint, hoặc endpoint được chỉ định rõ. Khi endpoint được đặt tường minh, kiểm tra nó khớp region/network path. Với OSS, chọn endpoint và region đúng bucket; SDK V1 Signature V4 yêu cầu khai báo region tương ứng.

## 8. Cách chọn dependency trong một ứng dụng Spring Boot

~~~mermaid
flowchart TD
    A{"Nhu cầu chính là gì?"}
    A -->|"Discovery / config / traffic governance / distributed transaction"| B["Spring Cloud Alibaba"]
    A -->|"Dùng một managed service qua Spring Boot auto-config"| C["Aliyun Spring Boot Starter"]
    A -->|"Cần API đặc thù hoặc starter không đáp ứng"| D["Java SDK sản phẩm"]
    B --> E["Import spring-cloud-alibaba-dependencies"]
    C --> F["Import aliyun-spring-boot-dependencies"]
    D --> G["Quản lý SDK + credentials + endpoint + client bean"]
    E --> H["Kiểm tra Spring Boot / Spring Cloud compatibility"]
    F --> I["Kiểm tra starter release và SDK transitive"]
    G --> J["Kiểm tra product API version và lifecycle"]
~~~

### 8.1. Ví dụ quyết định theo yêu cầu

| Yêu cầu ứng dụng | Chọn | Vì sao |
| --- | --- | --- |
| Các service tự đăng ký và tìm nhau qua Nacos | Spring Cloud Alibaba Nacos Discovery | Đây là năng lực service discovery |
| Quản lý cấu hình tập trung bằng Nacos | Spring Cloud Alibaba Nacos Config | Đây là externalized configuration |
| Bảo vệ endpoint khỏi traffic burst | Spring Cloud Alibaba Sentinel | Đây là flow control/circuit breaking |
| Gửi SMS từ Spring Boot | Aliyun SMS starter nếu tương thích; nếu không, SMS SDK | API SMS là dịch vụ cụ thể |
| Upload file lên OSS | Aliyun OSS starter hoặc OSS Java SDK | Đây là object storage API |
| Cần một thao tác OSS mới chưa được starter expose | OSS Java SDK trực tiếp | Cần API sản phẩm đầy đủ |
| Dùng RDS MySQL | JDBC driver/DataSource chuẩn và thông tin kết nối RDS; starter nếu có giá trị bổ sung | RDS là MySQL managed, không phải thay thế JDBC |
| Dùng Redis managed | Spring Data Redis/Lettuce hoặc starter phù hợp | Chọn theo protocol/compatibility của Redis service |
| Lịch chạy distributed job | SchedulerX integration/starter | Cần quản lý lịch và thực thi job phân tán |

Một dịch vụ managed không bắt buộc phải có starter riêng mới dùng được từ Spring Boot. Nếu sản phẩm tương thích giao thức chuẩn (ví dụ MySQL/JDBC hoặc Redis protocol), Spring ecosystem tương ứng có thể đủ; starter chỉ thêm giá trị khi nó đơn giản hóa cấu hình hoặc tích hợp đặc thù.

## 9. Cấu trúc mã nên dùng trong Spring Boot

### 9.1. Tách domain khỏi SDK

Không để controller hoặc domain service phụ thuộc trực tiếp vào lớp SDK của Alibaba Cloud. Tạo một interface nội bộ:

~~~java
package demo.storage;

import java.io.InputStream;

public interface ObjectStorage {
    void upload(String objectKey, InputStream content);
}
~~~

Adapter triển khai interface bằng OSS SDK:

~~~java
package demo.storage;

import com.aliyun.oss.OSS;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.InputStream;

@Component
public class AlibabaOssStorage implements ObjectStorage {
    private final OSS ossClient;
    private final String bucket;

    public AlibabaOssStorage(
            OSS ossClient,
            @Value("${aliyun.oss.bucket}") String bucket) {
        this.ossClient = ossClient;
        this.bucket = bucket;
    }

    @Override
    public void upload(String objectKey, InputStream content) {
        ossClient.putObject(bucket, objectKey, content);
    }
}
~~~

Domain service chỉ cần **ObjectStorage**. Khi thay OSS bằng một object storage khác, thay adapter và cấu hình, không phải sửa logic nghiệp vụ upload ở mọi nơi. Cách tổ chức này cũng giúp unit test mock interface mà không gọi cloud thật.

### 9.2. Cấu hình theo profile

~~~yaml
aliyun:
  oss:
    endpoint: ${ALIYUN_OSS_ENDPOINT}
    region: ${ALIYUN_OSS_REGION}
    bucket: ${ALIYUN_OSS_BUCKET}
~~~

Không đặt AccessKey secret trong file này. Tách endpoint/bucket không nhạy cảm khỏi credentials; dùng environment, RAM role, STS hoặc secret manager cho thông tin xác thực. Có thể dùng profile local/staging/prod để chọn endpoint, namespace và bucket khác nhau.

## 10. Kiểm thử và chẩn đoán

### 10.1. Kiểm thử theo lớp

| Loại test | Phạm vi | Cách thực hiện |
| --- | --- | --- |
| Unit test domain | Logic upload/gửi SMS không phụ thuộc cloud | Mock interface nội bộ như ObjectStorage |
| Unit test adapter | Ánh xạ request, object key, metadata | Mock client SDK hoặc kiểm tra adapter qua wrapper |
| Spring context test | Auto-configuration và bean injection | Dùng test context, property test và condition |
| Integration test | Kết nối Nacos/OSS/SMS thật hoặc sandbox | Dùng account test, bucket/namespace riêng và quyền giới hạn |
| Permission test | RAM role và policy | Thử quyền được phép/từ chối trong account test |
| Failure test | Timeout, endpoint sai, quota, network | Kiểm tra exception mapping, retry và log request ID |

Không dùng unit test để chứng minh IAM policy cloud đã đúng. Không chạy integration test gửi SMS thật tới người dùng hoặc upload dữ liệu nhạy cảm vào bucket production.

### 10.2. Triệu chứng thường gặp

| Triệu chứng | Lớp cần kiểm tra |
| --- | --- |
| Dependency không resolve | Maven coordinates, repository, BOM import và version được publish |
| **NoSuchMethodError / ClassNotFoundException** | Conflict giữa Spring Boot, Spring Cloud, SCA, starter và SDK transitive |
| Nacos không đăng ký service | server address, namespace, group, credentials, network và phiên bản client/server |
| OSS **AccessDenied** | RAM policy, bucket policy, object prefix, endpoint/region và credentials runtime |
| OSS **SignatureDoesNotMatch** | AccessKey/STS token, region, endpoint, clock skew và signing version |
| OSS **NoSuchBucket / NoSuchKey** | Tên bucket/object key, region và resource path |
| SMS bị từ chối | RAM permission, sender/template approval, phone format, quota và trạng thái dịch vụ |
| SDK timeout | Public/VPC endpoint, DNS, firewall, proxy, connect/read timeout |
| Credentials hết hạn | STS refresh, role trust policy, OIDC token và cache/provider lifecycle |

Phân biệt lỗi **client-side** (DNS, timeout, TLS, credentials provider) với lỗi **server-side** (AccessDenied, InvalidParameter, NoSuchBucket). Khi có request ID, lưu nó trong log để tra cứu trên hệ thống hỗ trợ của Alibaba Cloud. Không log AccessKey, secret, STS token hoặc toàn bộ payload có dữ liệu cá nhân.

### 10.3. Kiểm tra dependency tree

Khi dùng cả SCA và service starter, hãy kiểm tra dependency tree của Maven/Gradle để phát hiện:

- Hai version của Nacos client hoặc Sentinel.
- SDK product kéo theo version khác với starter.
- Phiên bản Spring Boot/Cloud không nằm trong ma trận SCA.
- Thư viện logging/HTTP client trùng hoặc bị override.
- Starter cũ kéo API không tương thích với Java/Jakarta version hiện tại.

Chỉ override dependency sau khi biết artifact nào gây xung đột và đã kiểm thử chức năng liên quan. Tránh dùng một BOM để ép mọi dependency về cùng một version số.

## 11. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Spring Cloud Alibaba là starter cho tất cả dịch vụ Alibaba Cloud | SCA tập trung vào tích hợp microservice như Nacos, Sentinel, Seata và RocketMQ |
| **spring-cloud-alibaba-dependencies** quản lý OSS/SMS SDK | Aliyun service starters có BOM riêng; SDK sản phẩm có version riêng |
| Có starter nghĩa là không cần biết RAM permission | Mọi request vẫn cần principal, permission, endpoint và resource policy phù hợp |
| Chạy trên Alibaba Cloud tự động có quyền truy cập mọi dịch vụ | Cần RAM role/credentials và policy cụ thể |
| Nacos thay thế OSS hoặc RDS | Nacos là registry/configuration center; OSS/RDS là dịch vụ storage/database |
| Mọi SDK Alibaba Cloud dùng cùng một endpoint | Endpoint/region phụ thuộc từng sản phẩm và network path |
| AccessKey của root account tiện nhất cho ứng dụng | Dùng RAM user/role có quyền tối thiểu và credentials ngắn hạn khi có thể |
| Một ứng dụng chỉ được chọn một trong ba lớp | Có thể kết hợp SCA, service starter và SDK khi mỗi lớp giải quyết một nhu cầu rõ ràng; phải quản lý version và bean lifecycle có chủ đích |

## 12. Bài tập thực hành

**Bài tập:** xây dựng một ứng dụng Spring Boot quản lý đơn hàng và file hóa đơn trên Alibaba Cloud.

1. Chọn phiên bản Spring Boot/Spring Cloud phù hợp với một nhánh SCA hiện hành.
2. Import **spring-cloud-alibaba-dependencies** và thêm Nacos Discovery để đăng ký service.
3. Tạo namespace Nacos riêng cho môi trường dev.
4. Thêm OSS service starter nếu phiên bản tương thích đáp ứng nhu cầu; nếu không, thêm OSS Java SDK và cấu hình client bean.
5. Tạo RAM role/user chỉ có quyền upload vào một bucket/prefix thử nghiệm.
6. Viết adapter **ObjectStorage** để upload file hóa đơn.
7. Unit test domain service bằng mock ObjectStorage.
8. Integration test upload file vào bucket dev, kiểm tra metadata và quyền truy cập.
9. Mô phỏng AccessDenied, endpoint sai và credentials hết hạn; ghi lại cách phân loại lỗi.
10. So sánh hai cách triển khai OSS: service starter và SDK trực tiếp về số lượng cấu hình, quyền kiểm soát, khả năng nâng cấp và khả năng kiểm thử.

**Câu hỏi ôn tập:**

1. Spring Cloud Alibaba và Aliyun Spring Boot Starters khác nhau ở mục tiêu nào?
2. Khi nào cần import **spring-cloud-alibaba-dependencies**?
3. Khi nào cần import **aliyun-spring-boot-dependencies**?
4. Vì sao version SCA không tự động quản lý version của OSS Java SDK?
5. Nếu cần một API OSS chưa được starter bọc, nên xử lý thế nào?
6. Vì sao cần tạo một OSS client singleton thay vì tạo client mỗi request?
7. Khi ứng dụng chạy trên ECS/ACK, nên cân nhắc RAM role/STS/OIDC như thế nào?
8. **AccessDenied** khác **SignatureDoesNotMatch** ở đâu?
9. Có thể dùng Nacos để thay thế RDS hoặc OSS không? Vì sao?
10. Nếu ứng dụng cần cả Nacos Discovery và OSS, cần kiểm tra những BOM/dependency nào?

## 13. Tài liệu tham khảo

- [Spring Cloud Alibaba — What is Spring Cloud Alibaba](https://sca.aliyun.com/en/docs/2025.x/overview/what-is-sca/): định vị SCA và phạm vi microservice.
- [Spring Cloud Alibaba — Release Notes 2025.x](https://sca.aliyun.com/en/docs/2025.x/overview/version-explain/): ma trận tương thích Spring Boot, Spring Cloud và SCA.
- [Spring — Spring Cloud Alibaba project](https://spring.io/projects/spring-cloud-alibaba/): phân biệt SCA với Spring Boot starters cho dịch vụ Alibaba Cloud và BOM tương ứng.
- [Alibaba — aliyun-spring-boot](https://github.com/alibaba/aliyun-spring-boot): dự án Aliyun Spring Boot Starters, BOM và danh sách starter.
- [Alibaba Cloud SDK — V2 Java SDK](https://www.alibabacloud.com/help/en/sdk/developer-reference/v2-java-sdk/): dependency chung và cấu hình endpoint/region cho SDK V2.
- [Alibaba Cloud SDK — Manage credentials](https://www.alibabacloud.com/help/en/sdk/developer-reference/v2-manage-access-credentials): default credential chain, RAM role, STS, OIDC và credentials cache.
- [OSS Java SDK V1 — Installation and quickstart](https://www.alibabacloud.com/help/en/oss/developer-reference/oss-java-sdk/): dependency, credentials, region, endpoint, Signature V4 và client lifecycle.
- [OSS Java SDK V2](https://www.alibabacloud.com/help/en/oss/developer-reference/oss-sdk-for-java-2-0/): hướng dẫn SDK V2 cho ứng dụng Java.
- [Alibaba Cloud RAM](https://www.alibabacloud.com/help/en/ram/): quản lý user, role và permission.

**Kết quả mong đợi:** người học nhận diện đúng ba lớp tích hợp: **Spring Cloud Alibaba cho microservice**, **Aliyun Spring Boot Starters cho dịch vụ managed**, và **Java SDK trực tiếp cho API sản phẩm**; biết chọn BOM/dependency, cấu hình RAM credentials, region/endpoint và kiểm thử từng lớp trong một ứng dụng Spring Boot.
