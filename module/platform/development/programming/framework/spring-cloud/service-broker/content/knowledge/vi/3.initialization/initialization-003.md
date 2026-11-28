# Khai báo spring-cloud-starter-open-service-broker bằng Maven hoặc Gradle

Để xây dựng **SPRING_CLOUD_SERVICE_BROKER**, ứng dụng Spring cần có thư viện tích hợp Open Service Broker API (OSB API). Starter chính của Spring Cloud Open Service Broker có tọa độ Maven:

- **Group:** `org.springframework.cloud`
- **Artifact:** `spring-cloud-starter-open-service-broker`

Starter giúp đưa các thành phần cần thiết của Spring Cloud Open Service Broker vào classpath và kết nối chúng với ứng dụng Spring Boot. Bạn có thể khai báo dependency bằng Maven hoặc Gradle. Việc thêm dependency mới chỉ chuẩn bị nền tảng thư viện; broker vẫn cần cấu hình ứng dụng, công bố catalog và triển khai nghiệp vụ provision, update, deprovision, bind, unbind.

## 1. Hiểu tọa độ và vai trò của starter

Một dependency Maven được xác định bởi các thông tin như group ID, artifact ID và version. Với starter của Spring Cloud Open Service Broker:

| Thành phần | Giá trị | Ý nghĩa |
|---|---|---|
| Group ID | `org.springframework.cloud` | Nhóm phát hành thư viện |
| Artifact ID | `spring-cloud-starter-open-service-broker` | Tên starter cần khai báo |
| Version | Phiên bản tương thích của dự án | Xác định bản thư viện được tải |
| Scope/configuration | `compile` trong Maven hoặc `implementation` trong Gradle | Cho biết dependency tham gia vào classpath nào |

Tên artifact cần được ghi chính xác. Các tên gần giống như `spring-cloud-open-service-broker` hoặc một thư viện OSB API thuần không nhất thiết thay thế được starter. Starter thường đóng vai trò điểm vào để gom các thành phần mà ứng dụng Spring cần, trong khi những artifact lõi có thể được khai báo gián tiếp dưới dạng dependency bắc cầu.

Khi sử dụng starter, Gradle hoặc Maven sẽ giải quyết dependency trực tiếp và dependency bắc cầu, tải các artifact từ repository đã cấu hình và đưa chúng vào classpath tương ứng. Vì vậy, không nên thêm thủ công tất cả thư viện con nếu starter đã cung cấp chúng, trừ khi có yêu cầu kỹ thuật cụ thể và đã kiểm tra cây dependency.

## 2. Chọn và quản lý phiên bản

Phiên bản starter phải tương thích với nền tảng Spring Boot, Spring Framework và Java mà dự án sử dụng. Hãy xác định phiên bản dựa trên ma trận tương thích và hướng dẫn phát hành của Spring Cloud Open Service Broker tại thời điểm xây dựng dự án.

Có hai cách quản lý phiên bản thường gặp:

1. Dùng Spring Cloud BOM (Bill of Materials) nếu BOM được chọn quản lý phiên bản của starter này.
2. Khai báo version trực tiếp bằng một property hoặc biến dùng chung nếu BOM không quản lý artifact hoặc dự án không dùng BOM đó.

Không nên tự đoán phiên bản, dùng phiên bản động như `+` hoặc đặt mỗi thư viện Spring một phiên bản ngẫu nhiên. Việc trộn các phiên bản không tương thích có thể gây lỗi khi Maven/Gradle giải quyết dependency hoặc khi ứng dụng khởi động.

### 2.1. Khi dùng Spring Cloud BOM

BOM là một POM có vai trò quản lý phiên bản cho một tập dependency. Trong Maven, BOM thường được import trong phần `dependencyManagement`. Trong Gradle, có thể dùng BOM như một platform.

Chỉ bỏ version khỏi khai báo starter khi BOM đang dùng thực sự quản lý artifact `spring-cloud-starter-open-service-broker` ở phiên bản tương thích. Nếu không, hãy khai báo version rõ ràng theo mục 3 hoặc 4.

## 3. Khai báo dependency bằng Maven

### 3.1. Khai báo version trực tiếp

Trong dự án Maven, mở file `pom.xml` của module chạy broker. Đặt version ở một property để có thể thay đổi tập trung:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud-open-service-broker.version>YOUR_COMPATIBLE_VERSION</spring-cloud-open-service-broker.version>
</properties>
~~~

Giá trị `YOUR_COMPATIBLE_VERSION` là chỗ giữ phiên bản đã được xác nhận tương thích; thay nó bằng phiên bản phát hành thực tế mà dự án chọn. Sau đó khai báo starter trong phần `dependencies`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-open-service-broker</artifactId>
        <version>${spring-cloud-open-service-broker.version}</version>
    </dependency>
</dependencies>
~~~

Maven mặc định dùng scope `compile` nếu không chỉ định `scope`. Dependency này vì thế có mặt khi biên dịch và trong classpath runtime. Đây là cách phù hợp với starter mà ứng dụng cần để khởi chạy broker.

### 3.2. Khai báo version thông qua BOM

Nếu dự án đã chọn một Spring Cloud BOM tương thích và BOM đó quản lý starter, cấu hình có thể tách quản lý version khỏi khai báo dependency.

Phần quản lý phiên bản:

~~~xml
<properties>
    <spring-cloud.version>YOUR_COMPATIBLE_SPRING_CLOUD_TRAIN</spring-cloud.version>
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

Phần dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-open-service-broker</artifactId>
    </dependency>
</dependencies>
~~~

Tên property ở trên chỉ là ví dụ; cần thay bằng release train phù hợp với Spring Boot của dự án. Nếu BOM không quản lý starter, Maven sẽ báo thiếu version hoặc phải dùng một cơ chế quản lý version khác. Khi đó, thêm `<version>` vào dependency hoặc sử dụng một BOM chuyên biệt được dự án xác nhận.

Không import nhiều BOM có các quy tắc quản lý phiên bản chồng chéo mà không hiểu thứ tự ưu tiên. Nếu dự án đã kế thừa một parent POM quản lý Spring Boot/Spring Cloud, hãy kiểm tra cấu hình hiện có trước khi thêm một BOM thứ hai.

### 3.3. Đặt dependency ở đúng module

Nếu repository có nhiều module Maven, starter nên được khai báo trong module thực sự chạy ứng dụng broker. Không nhất thiết đặt dependency ở parent POM nếu parent chỉ dùng để quản lý phiên bản hoặc đóng gói các module dùng chung.

Ví dụ cấu trúc:

~~~text
service-broker/
├── pom.xml
├── broker-api/
│   └── pom.xml
├── broker-core/
│   └── pom.xml
└── broker-application/
    └── pom.xml
~~~

Nếu `broker-application` là module tạo Spring Boot executable JAR, dependency starter thường được đặt trong `broker-application/pom.xml`. Các module lõi có thể chỉ cần những API mà chúng trực tiếp sử dụng. Cách chia module cụ thể tùy kiến trúc; điều quan trọng là dependency phải xuất hiện trên runtime classpath của ứng dụng khởi chạy.

## 4. Khai báo dependency bằng Gradle

Gradle hỗ trợ khai báo dependency trong `build.gradle` (Groovy DSL) hoặc `build.gradle.kts` (Kotlin DSL). Với ứng dụng Spring Boot, starter thường được khai báo bằng configuration `implementation`.

### 4.1. Gradle Groovy DSL — version trực tiếp

Trong `build.gradle`:

~~~groovy
def springCloudOpenServiceBrokerVersion = 'YOUR_COMPATIBLE_VERSION'

dependencies {
    implementation "org.springframework.cloud:spring-cloud-starter-open-service-broker:${springCloudOpenServiceBrokerVersion}"
}
~~~

Thay `YOUR_COMPATIBLE_VERSION` bằng phiên bản tương thích đã chọn. Đặt biến ở đầu file giúp tránh lặp version và làm cho mục đích quản lý dependency dễ đọc hơn.

### 4.2. Gradle Kotlin DSL — version trực tiếp

Trong `build.gradle.kts`:

~~~kotlin
val springCloudOpenServiceBrokerVersion =
    providers.gradleProperty("springCloudOpenServiceBrokerVersion").get()

dependencies {
    implementation(
        "org.springframework.cloud:spring-cloud-starter-open-service-broker:$springCloudOpenServiceBrokerVersion"
    )
}
~~~

Khai báo property trong `gradle.properties`:

~~~properties
springCloudOpenServiceBrokerVersion=YOUR_COMPATIBLE_VERSION
~~~

Cũng như ví dụ Maven, hãy thay giá trị giữ chỗ bằng một phiên bản phát hành cụ thể. Có thể quản lý version bằng Gradle version catalog nếu dự án đã sử dụng cơ chế đó.

### 4.3. Gradle với BOM

Khi Spring Cloud BOM đã chọn quản lý starter, có thể import BOM như một platform. Ví dụ Groovy DSL:

~~~groovy
dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation "org.springframework.cloud:spring-cloud-starter-open-service-broker"
}
~~~

Ví dụ Kotlin DSL:

~~~kotlin
dependencies {
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"))
    implementation("org.springframework.cloud:spring-cloud-starter-open-service-broker")
}
~~~

Biến `springCloudVersion` phải được khai báo ở nơi phù hợp trong cấu hình Gradle của dự án. Các ví dụ BOM chỉ dùng khi release train đã chọn có quản lý version của starter. Nếu không, thêm version trực tiếp vào dependency như các ví dụ trước.

`implementation` đưa starter vào compile classpath của module và runtime classpath của ứng dụng. Không dùng `compileOnly` cho dependency mà ứng dụng cần khi chạy broker, vì thư viện có thể vắng mặt lúc khởi động hoặc xử lý request.

## 5. Cấu trúc tối thiểu của ứng dụng sử dụng starter

Sau khi dependency được giải quyết, ứng dụng vẫn cần điểm khởi chạy Spring Boot. Một lớp khởi động tối thiểu có thể như sau:

~~~java
package com.example.broker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServiceBrokerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServiceBrokerApplication.class, args);
    }
}
~~~

Lớp này khởi tạo Spring Boot và kích hoạt cơ chế component scanning, auto-configuration theo classpath và cấu hình ứng dụng. Starter cung cấp các thành phần tích hợp; nó không tự biết catalog, plan, tài nguyên hoặc chính sách nghiệp vụ của tổ chức.

Để trở thành một broker có thể phục vụ request, ứng dụng còn phải cung cấp các thành phần nghiệp vụ phù hợp với phiên bản Spring Cloud Open Service Broker đang sử dụng. Ở mức chức năng, chúng bao gồm:

- Cung cấp catalog gồm service và plan được công bố.
- Xử lý provision và truy vấn trạng thái operation của service instance.
- Xử lý update và deprovision instance.
- Xử lý bind và unbind, bao gồm việc cấp và thu hồi thông tin xác thực.
- Kết nối với kho dữ liệu và hệ thống hạ tầng thực hiện cấp phát tài nguyên.

Vì vậy, thêm starter là bước chuẩn bị dependency và tích hợp framework. Nó không thay thế phần triển khai các hành vi OSB API.

## 6. Repository và quá trình tải dependency

Maven và Gradle cần truy cập repository chứa artifact. Các dự án Spring thường lấy dependency công khai từ Maven Central hoặc repository được cấu hình thông qua môi trường build của tổ chức.

Khi khai báo đúng tọa độ nhưng build vẫn thất bại, cần phân biệt lỗi cấu hình dependency với lỗi truy cập repository:

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy artifact | Sai group/artifact/version hoặc repository chưa có bản phát hành đó | Kiểm tra tọa độ và repository |
| Maven báo thiếu version | Dependency không được BOM hoặc parent quản lý | Khai báo version hoặc sửa dependency management |
| Gradle không resolve được | Repository chưa khai báo, mạng hoặc credentials không hợp lệ | Kiểm tra `repositories` và cấu hình xác thực |
| Timeout khi tải | Kết nối mạng hoặc mirror nội bộ gặp vấn đề | Kiểm tra proxy, mirror và trạng thái repository |
| Build dùng được ở máy này nhưng không ở máy khác | Cache cục bộ che giấu vấn đề hoặc cấu hình repository khác nhau | Thử build sạch trong môi trường tương đương CI |

Ví dụ cấu hình repository Maven Central trong Gradle:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Với Maven, Maven Central thường đã được cấu hình mặc định. Nếu công ty sử dụng repository proxy hoặc mirror, hãy theo cấu hình được quản trị dự án cung cấp thay vì tự thêm nhiều nguồn tải không cần thiết.

Không đưa username, password hoặc access token của repository vào file build được commit. Sử dụng cơ chế credentials và secret của môi trường build.

## 7. Kiểm tra dependency sau khi khai báo

Sau khi sửa file build, hãy chạy lệnh phù hợp để xác nhận starter đã được resolve và xuất hiện trong dependency graph.

Với Maven:

~~~bash
./mvnw -pl broker-application dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-starter-open-service-broker
~~~

Nếu dự án không có Maven Wrapper hoặc module không mang tên `broker-application`, dùng Maven đã cài đặt và điều chỉnh đường dẫn/module tương ứng:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud
~~~

Có thể kiểm tra POM sau khi hợp nhất parent và BOM bằng:

~~~bash
mvn help:effective-pom
~~~

Với Gradle:

~~~bash
./gradlew :broker-application:dependencies --configuration runtimeClasspath
~~~

Để xem dependency nào đưa một thư viện vào graph hoặc phiên bản nào được chọn:

~~~bash
./gradlew :broker-application:dependencyInsight --dependency spring-cloud-starter-open-service-broker --configuration runtimeClasspath
~~~

Hãy thay tên module trong ví dụ bằng tên module thực tế của dự án. Trên Windows, có thể chạy wrapper tương ứng `mvnw.cmd` hoặc `gradlew.bat`.

Kết quả cần xác nhận:

1. Artifact có đúng group ID và artifact ID.
2. Một version cụ thể đã được chọn.
3. Dependency có mặt trong runtime classpath của module chạy broker.
4. Không có xung đột phiên bản Spring Boot/Spring Cloud rõ ràng trong cây dependency.
5. Build hoàn tất mà không có lỗi resolve hoặc compile.

Nếu dependency xuất hiện nhiều lần trong cây, điều đó có thể là do nhiều nhánh dependency bắc cầu cùng tham chiếu đến nó. Maven và Gradle có cơ chế chọn phiên bản; hãy dùng dependency tree hoặc dependency insight để hiểu phiên bản cuối cùng thay vì tự loại bỏ một dependency một cách tùy tiện.

## 8. Những lỗi khai báo thường gặp

### Sai artifact ID

Một ký tự sai trong `spring-cloud-starter-open-service-broker` khiến công cụ build tìm một artifact không tồn tại. Sao chép tọa độ từ tài liệu phát hành hoặc cấu hình đã được dự án xác nhận.

### Không khai báo version và không có BOM quản lý

Maven có thể báo `'dependencies.dependency.version' is missing`; Gradle có thể không xác định được phiên bản nếu không có platform hoặc version constraint. Hãy kiểm tra BOM thực sự có quản lý starter hay không, sau đó khai báo version phù hợp.

### Dùng BOM không tương thích

Một BOM quản lý nhiều thư viện Spring theo cùng một release train. Chọn sai train có thể kéo theo phiên bản không tương thích với Spring Boot hoặc Spring Framework hiện tại. Kiểm tra ma trận tương thích trước khi nâng hoặc hạ BOM.

### Đặt dependency sai module hoặc sai configuration

Dependency được khai báo trong module không chạy ứng dụng sẽ không tự động xuất hiện trên runtime classpath của module broker. Tương tự, `compileOnly` không bảo đảm thư viện có mặt khi chạy. Hãy kiểm tra đúng module executable và configuration `implementation` hoặc scope runtime phù hợp.

### Khai báo thủ công quá nhiều dependency con

Starter được thiết kế để gom các dependency cần thiết. Thêm các module lõi với version khác nhau có thể tạo xung đột. Trước tiên xem dependency tree; chỉ khai báo trực tiếp một artifact con khi mã nguồn thực sự phụ thuộc vào nó hoặc tài liệu của phiên bản yêu cầu.

### Build thành công nhưng broker chưa xử lý được request

Dependency resolve thành công chỉ chứng minh thư viện đã có trên classpath. Ứng dụng vẫn cần cấu hình Spring, các thành phần catalog và xử lý vòng đời, lưu trạng thái, xác thực request và kết nối hệ thống cấp phát tài nguyên. Hãy tiếp tục kiểm tra log khởi động và cấu hình nghiệp vụ sau khi hoàn tất bước dependency.

## 9. Checklist hoàn tất khai báo

Trước khi chuyển sang cấu hình và triển khai broker, hãy xác nhận:

- [ ] Đã chọn Maven hoặc Gradle theo hệ thống build của dự án.
- [ ] Đã khai báo đúng `org.springframework.cloud:spring-cloud-starter-open-service-broker`.
- [ ] Version được quản lý tập trung hoặc do BOM tương thích cung cấp.
- [ ] BOM được dùng chỉ khi nó thực sự quản lý starter ở phiên bản phù hợp.
- [ ] Dependency nằm trong module chạy ứng dụng broker.
- [ ] Starter có mặt trong runtime classpath.
- [ ] Dependency graph không có xung đột phiên bản chưa được giải quyết.
- [ ] Build thành công trên môi trường phát triển và có thể tái lập trong CI.

## 10. Kết luận

Với Spring Cloud Service Broker, starter cần khai báo là `org.springframework.cloud:spring-cloud-starter-open-service-broker`. Maven đặt dependency trong `pom.xml`; Gradle đặt dependency trong `build.gradle` hoặc `build.gradle.kts`. Cả hai công cụ đều cần một phiên bản cụ thể, được quản lý trực tiếp hoặc thông qua BOM tương thích.

Sau khi khai báo, hãy kiểm tra dependency graph và runtime classpath của đúng module khởi chạy broker. Đây là nền tảng để tiếp tục cấu hình ứng dụng Spring và triển khai catalog, service plan, provision, update, deprovision, binding cùng các cơ chế trạng thái và bảo mật của Open Service Broker API.

