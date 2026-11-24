# Chọn starter khám phá và đọc cây phụ thuộc Gradle hoặc Maven

## 1. Vì sao phải chọn đúng starter?

Trong Spring Cloud Service Discovery, ứng dụng cần một cơ chế để đăng ký instance và tìm các instance khác theo tên dịch vụ. Spring Cloud cung cấp các abstraction dùng chung như **DiscoveryClient** và **ServiceRegistry**; mỗi hệ thống discovery cụ thể cung cấp phần tích hợp tương ứng.

Khi dùng Eureka, ứng dụng cần starter Eureka phù hợp với vai trò của nó. Eureka Server nhận đăng ký và cung cấp registry; Eureka Client đăng ký instance, gia hạn lease và tra cứu dịch vụ. Nếu dùng Consul, ứng dụng chọn starter Consul Discovery. Starter là điểm vào tập hợp dependency và auto-configuration để tích hợp hệ thống đó với Spring Boot.

Chọn starter đúng giúp dự án có các thư viện cần thiết và cấu hình tự động tương ứng. Chọn nhầm starter có thể làm ứng dụng thiếu chức năng, kéo thêm thư viện không cần thiết hoặc tạo ra xung đột phiên bản. Vì vậy, trước khi viết code discovery, hãy xác định vai trò ứng dụng, chọn starter và kiểm tra cây phụ thuộc do Maven hoặc Gradle giải quyết.

## 2. Phân biệt các starter thường gặp

Các starter phổ biến trong phạm vi service discovery:

| Starter | Dùng khi nào? | Vai trò chính |
|---|---|---|
| **spring-cloud-starter-netflix-eureka-server** | Tạo ứng dụng Eureka Server | Cung cấp Eureka Server và cơ chế nhận đăng ký, lưu registry, phục vụ tra cứu |
| **spring-cloud-starter-netflix-eureka-client** | Ứng dụng đăng ký hoặc tra cứu qua Eureka | Tích hợp Eureka Client với Spring Cloud Discovery |
| **spring-cloud-starter-consul-discovery** | Dùng Consul làm hệ thống discovery | Đăng ký và tra cứu dịch vụ thông qua Consul |
| **spring-cloud-starter-loadbalancer** | Ứng dụng cần chọn một instance từ danh sách instance | Cung cấp bộ cân bằng tải phía client |

Không phải ứng dụng nào cũng cần tất cả starter trên. Một ứng dụng Eureka Server thường dùng starter server. Một ứng dụng nghiệp vụ đăng ký vào Eureka dùng starter client. Chỉ thêm LoadBalancer khi ứng dụng cần chức năng chọn instance phía client và chưa có dependency phù hợp được cung cấp trong cấu hình hiện tại.

### 2.1. Server và client có hai vai trò khác nhau

**Eureka Server** duy trì registry và tiếp nhận các thao tác đăng ký, gia hạn, hủy đăng ký. Một ứng dụng server thường bật chức năng server bằng annotation **@EnableEurekaServer**:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class DiscoveryServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiscoveryServerApplication.class, args);
    }
}
~~~

**Eureka Client** là ứng dụng nghiệp vụ muốn công bố instance của chính nó hoặc tra cứu các dịch vụ khác. Khi có Eureka Client starter và cấu hình endpoint phù hợp, Spring Cloud có thể tự cấu hình phần tích hợp Eureka. Ứng dụng có thể sử dụng abstraction **DiscoveryClient** để tra cứu instance theo service ID:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class ServiceLookup {
    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }
}
~~~

Tên package và một số chi tiết cấu hình có thể khác theo phiên bản Spring Cloud. Hãy dùng phiên bản tương thích với Spring Boot của dự án và kiểm tra tài liệu của release train tương ứng.

### 2.2. Discovery và load balancing không phải một chức năng

Discovery trả về danh sách instance đã biết của một dịch vụ. Load balancing chọn một instance từ danh sách đó cho một request cụ thể. Ví dụ, **DiscoveryClient** có thể trả về ba instance của **payment-service**; bộ cân bằng tải phía client quyết định request tiếp theo đi đến instance nào.

~~~mermaid
flowchart LR
    APP[Ứng dụng gọi dịch vụ] --> DISC[DiscoveryClient]
    DISC --> REG[Registry Eureka hoặc Consul]
    REG --> INST[Danh sách instance]
    INST --> LB[LoadBalancer]
    LB --> TARGET[Instance được chọn]
~~~

Do đó, không nên xem việc thêm Eureka Client starter là đồng nghĩa với việc ứng dụng đã có mọi chính sách cân bằng tải. Hãy kiểm tra dependency tree và cấu hình thực tế để biết LoadBalancer có mặt hay không.

## 3. Quản lý phiên bản bằng Spring Cloud BOM

Các thư viện trong Spring Cloud được phát hành theo release train. Các module trong cùng một release train được kiểm thử để làm việc với những phiên bản Spring Boot tương ứng. Dự án nên quản lý phiên bản theo ma trận tương thích Spring Boot và Spring Cloud, thay vì tự chọn một version riêng cho từng starter.

**BOM (Bill of Materials)** là tập hợp metadata quản lý phiên bản dependency. Khi import Spring Cloud BOM, dự án có thể khai báo các starter Spring Cloud mà không phải lặp lại version cho từng dependency. BOM giúp các module Spring Cloud sử dụng các phiên bản đã được căn chỉnh trong cùng release train.

Quy trình chọn phiên bản:

1. Xác định phiên bản Spring Boot đang dùng.
2. Tra ma trận tương thích để chọn Spring Cloud release train hỗ trợ phiên bản Boot đó.
3. Import BOM của release train đã chọn.
4. Khai báo starter cần dùng mà không ghi version riêng nếu BOM đã quản lý version đó.
5. Kiểm tra cây dependency và dependency được Maven hoặc Gradle thực sự chọn.

Không nên chọn release train chỉ vì nó là phiên bản mới nhất. Phiên bản mới có thể yêu cầu một dòng Spring Boot khác với dự án hiện tại.

## 4. Khai báo dependency với Maven

### 4.1. Import Spring Cloud BOM

Trong **pom.xml**, khai báo release train ở phần properties rồi import BOM trong **dependencyManagement**. Thay giá trị minh họa bằng release train tương thích với phiên bản Spring Boot của dự án:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Giá trị **REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN** là chỗ cần điền version thật, không phải version hợp lệ để giữ nguyên trong dự án.

### 4.2. Chọn dependency cho Eureka Server

Với một dự án chỉ đóng vai trò Eureka Server, dependency cốt lõi là:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Starter Eureka Server cung cấp phần tích hợp server. Web starter được khai báo để ứng dụng phục vụ giao diện và HTTP endpoint qua Spring MVC trong ví dụ này. Tùy phiên bản và cách đóng gói, hãy kiểm tra các dependency đã được kéo vào trước khi thêm thư viện trùng lặp.

### 4.3. Chọn dependency cho Eureka Client

Với một ứng dụng nghiệp vụ đăng ký vào Eureka:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Web starter ở đây phục vụ API HTTP của ứng dụng nghiệp vụ. Nó không phải thành phần cốt lõi của discovery; ứng dụng có thể dùng loại giao tiếp khác nếu kiến trúc yêu cầu.

Không cần khai báo cả server starter và client starter trong mọi ứng dụng. Chỉ thêm cả hai khi có chủ đích xây dựng một tiến trình vừa chạy Eureka Server vừa đóng vai trò Eureka Client trong một kiến trúc đặc biệt.

### 4.4. Chọn Consul thay cho Eureka

Nếu hệ thống sử dụng Consul làm registry, starter thường dùng là:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
~~~

Không thêm đồng thời Eureka Client và Consul Discovery chỉ để dự phòng nếu chưa có thiết kế rõ ràng. Khi bật nhiều discovery client, ứng dụng có thể đăng ký hoặc tra cứu qua nhiều hệ thống, khiến việc vận hành và xác định nguồn dữ liệu phức tạp hơn.

## 5. Khai báo dependency với Gradle

Gradle có thể import BOM bằng dependency platform. Ví dụ sau dùng Groovy DSL trong **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_COMPATIBLE_BOOT_VERSION'
}

ext {
    springCloudVersion = 'REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN'
}

dependencies {
    implementation platform(
        'org.springframework.cloud:spring-cloud-dependencies:' + springCloudVersion
    )

    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Thay hai placeholder bằng phiên bản Spring Boot và Spring Cloud tương thích. Nếu dự án đã có plugin hoặc convention quản lý dependency, hãy theo cơ chế sẵn có của dự án thay vì thêm một cách quản lý phiên bản thứ hai.

Đối với Eureka Server, thay dependency Eureka Client bằng:

~~~groovy
implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-server'
~~~

Đối với Consul Discovery, dùng:

~~~groovy
implementation 'org.springframework.cloud:spring-cloud-starter-consul-discovery'
~~~

Gradle Kotlin DSL (**build.gradle.kts**) có cú pháp khác, nhưng nguyên tắc vẫn giống nhau: import BOM bằng **platform(...)**, sau đó khai báo starter trong **dependencies**.

## 6. Cách đọc cây phụ thuộc

Cây phụ thuộc (dependency tree) mô tả dependency trực tiếp và dependency bắc cầu (transitive dependency) mà công cụ build phân giải cho dự án. Khi thêm một starter, dự án thường nhận nhiều thư viện bên dưới chứ không chỉ một artifact duy nhất.

Ví dụ sơ đồ khái quát:

~~~text
payment-service
└── spring-cloud-starter-netflix-eureka-client
    ├── tích hợp Eureka với Spring Cloud
    ├── Spring Cloud Commons / Context
    ├── Eureka Client của Netflix
    └── các thư viện nền tảng liên quan
~~~

Đây là sơ đồ khái niệm để giải thích quan hệ, không phải danh sách dependency cố định. Cây thực tế phụ thuộc vào release train, phiên bản starter, các dependency khác của dự án và quy tắc resolution của Maven hoặc Gradle.

Khi đọc cây, hãy phân biệt:

- **Direct dependency:** dependency được khai báo trực tiếp trong file build.
- **Transitive dependency:** dependency được một dependency khác kéo vào.
- **Version constraint hoặc version management:** quy tắc giới hạn hay quản lý phiên bản được chọn.
- **Conflict resolution:** cách công cụ build chọn một phiên bản khi nhiều nhánh yêu cầu các phiên bản khác nhau.
- **Exclusion:** quy tắc loại một dependency bắc cầu khỏi nhánh cụ thể.

Một starter có thể kéo vào các thư viện dùng chung của Spring Cloud. Nếu một thư viện xuất hiện nhiều lần ở các nhánh, điều đó không tự động có nghĩa là runtime sẽ đóng gói nhiều bản của cùng artifact. Maven và Gradle thực hiện quá trình phân giải để chọn dependency hiệu lực theo quy tắc của chúng.

## 7. Xem dependency tree bằng Maven

### 7.1. In toàn bộ cây

Chạy tại thư mục chứa **pom.xml**:

~~~bash
mvn dependency:tree
~~~

Kết quả hiển thị các dependency theo dạng cây, bao gồm quan hệ cha-con và version đã được chọn.

### 7.2. Lọc các dependency liên quan đến Spring Cloud và Eureka

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud:*,com.netflix.eureka:*
~~~

Lệnh lọc giúp tập trung vào các artifact liên quan đến Spring Cloud và Eureka. Nếu cần hiểu vì sao một version được chọn, dùng chế độ verbose:

~~~bash
mvn dependency:tree -Dverbose
~~~

### 7.3. Kiểm tra POM sau khi áp dụng BOM

~~~bash
mvn help:effective-pom
~~~

Effective POM là POM sau khi Maven áp dụng parent, properties, dependency management và các cấu hình kế thừa. Đây là nơi hữu ích để kiểm tra version được quản lý từ BOM và cấu hình được kế thừa mà file **pom.xml** hiện tại không thể hiện trực tiếp.

Nếu build không phân giải được dependency, hãy kiểm tra:

1. BOM có được import đúng trong dependencyManagement không.
2. Version Spring Cloud release train có tương thích với Spring Boot không.
3. Tên groupId và artifactId có chính xác không.
4. Repository Maven có thể truy cập và artifact có được phát hành không.
5. Có dependency management từ parent hoặc profile nào ghi đè version hay không.

## 8. Xem dependency tree bằng Gradle

### 8.1. In runtime dependency tree

Với Gradle Wrapper trên Linux hoặc macOS:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trên Windows:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

**runtimeClasspath** thể hiện dependency cần có khi chạy ứng dụng. Nếu muốn xem các dependency phục vụ biên dịch mã nguồn, có thể kiểm tra **compileClasspath**. Hai configuration có thể khác nhau vì một số dependency chỉ cần khi biên dịch hoặc chỉ cần lúc chạy.

### 8.2. Tìm lý do một dependency được chọn

~~~bash
./gradlew dependencyInsight --dependency spring-cloud-starter-netflix-eureka-client --configuration runtimeClasspath
~~~

**dependencyInsight** tập trung vào một dependency, cho biết nó được đưa vào từ đâu và vì sao version được chọn. Đây là lệnh hữu ích khi có nhiều module cùng yêu cầu một artifact hoặc khi một constraint ảnh hưởng đến kết quả resolution.

### 8.3. Đọc kết quả Gradle

Khi xem output, chú ý:

- Nhánh nào đưa starter vào runtime classpath.
- Version yêu cầu ban đầu và version thực tế được chọn.
- Dependency nào bị thay thế hoặc nâng version do constraint/platform.
- Có dòng nào thể hiện dependency không được chọn, bị loại hoặc không thể phân giải.
- Starter có kéo vào thư viện trùng vai trò với dependency đã khai báo trực tiếp hay không.

Nếu dùng multi-module build, hãy chạy lệnh với đúng project path hoặc đúng module. Cây của root project không nhất thiết đại diện cho classpath của service cần kiểm tra.

## 9. Ví dụ phân tích một cây phụ thuộc

Giả sử một ứng dụng có các dependency trực tiếp:

~~~text
spring-boot-starter-web
spring-cloud-starter-netflix-eureka-client
spring-cloud-starter-loadbalancer
~~~

Khi xem cây, ta có thể đặt các câu hỏi:

1. Eureka Client starter có xuất hiện trong runtime classpath không?
2. Artifact Eureka Client thực tế được kéo vào là version nào?
3. Spring Cloud Commons và các thư viện nền tảng có được căn chỉnh theo BOM không?
4. LoadBalancer có mặt do dependency trực tiếp hay do một starter khác kéo vào?
5. Có hai release train hoặc nhiều version của cùng module Spring Cloud xuất hiện trong cây không?

Nếu cây cho thấy nhiều version Spring Cloud không đồng nhất, hãy kiểm tra BOM và dependency management trước. Không nên vội thêm exclusion hoặc ép version thủ công, vì cách đó có thể che giấu nguyên nhân và tạo tổ hợp thư viện chưa được kiểm thử cùng nhau.

### 9.1. Khi nào nên dùng exclusion?

Exclusion có ích khi một dependency bắc cầu cụ thể thực sự không phù hợp và dự án có phương án thay thế tương thích. Ví dụ cú pháp Maven:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>library-a</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>library-b</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Đây chỉ là ví dụ cú pháp với tọa độ giả định, không phải đề xuất loại một dependency Eureka cụ thể. Trước khi exclusion, hãy xác định dependency nào cần bị loại, dependency nào sẽ thay thế nó và kiểm thử các luồng khởi động, đăng ký, heartbeat và tra cứu dịch vụ.

## 10. Quy trình chọn starter và xác minh dependency

Có thể áp dụng quy trình sau cho mỗi service:

1. **Xác định vai trò:** service là Eureka Server, Eureka Client hay ứng dụng dùng Consul?
2. **Chọn starter:** chỉ thêm starter đáp ứng vai trò đó; cân nhắc LoadBalancer theo nhu cầu gọi dịch vụ.
3. **Chọn phiên bản nền tảng:** đối chiếu Spring Boot với Spring Cloud release train.
4. **Import BOM:** để BOM quản lý phiên bản các module Spring Cloud.
5. **Khai báo dependency:** tránh chỉ định version riêng cho starter đã được BOM quản lý.
6. **In dependency tree:** kiểm tra direct và transitive dependency trong classpath cần dùng.
7. **Điều tra xung đột:** dùng effective POM hoặc dependencyInsight để tìm nguồn version và constraint.
8. **Xác minh ứng dụng:** build, khởi động và kiểm tra khả năng đăng ký hoặc tra cứu qua registry.

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Không tìm thấy class Eureka Server | Thiếu server starter hoặc dependency không nằm trong classpath |
| Không có instance trong registry | Client starter, endpoint, cấu hình đăng ký hoặc kết nối server |
| Build báo không tìm thấy artifact | Sai tọa độ, version, BOM hoặc repository |
| Lỗi tương thích khi khởi động | Spring Boot và Spring Cloud release train không tương thích |
| Runtime thiếu class dù compile thành công | Dependency scope/configuration hoặc runtime classpath |
| Kết quả dependency tree có version bất ngờ | BOM, parent, constraint, conflict resolution hoặc dependency khai báo trực tiếp |

## 11. Tổng kết

Starter xác định phần tích hợp service discovery mà ứng dụng cần: Eureka Server, Eureka Client hoặc Consul Discovery. **DiscoveryClient** cung cấp abstraction để tra cứu instance; LoadBalancer đảm nhiệm việc chọn instance cho request và là một chức năng riêng cần được kiểm tra dependency tương ứng.

Với Maven hoặc Gradle, hãy import Spring Cloud BOM tương thích với Spring Boot rồi khai báo starter mà không tự đặt version riêng khi BOM đã quản lý. Các lệnh **mvn dependency:tree**, **mvn help:effective-pom**, **gradlew dependencies** và **dependencyInsight** giúp xác định dependency trực tiếp, dependency bắc cầu và version thực tế được chọn. Đọc cây phụ thuộc trước khi xử lý xung đột giúp dự án có classpath rõ ràng và giảm rủi ro khi triển khai service discovery.
