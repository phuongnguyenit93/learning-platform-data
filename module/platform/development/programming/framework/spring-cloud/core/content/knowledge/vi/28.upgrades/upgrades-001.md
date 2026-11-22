# Lập bảng Java, Spring Boot, release train và phiên bản Commons

## 1. Vì sao phải lập ma trận phiên bản?

Spring Cloud được phát hành theo release train. Mỗi train gom một tập module như Spring Cloud Commons, Config, LoadBalancer, OpenFeign, Gateway và Bus. Các module có thể có số phiên bản riêng, nhưng release train BOM chọn một tập phiên bản đã được kiểm tra cùng nhau.

Khi nâng cấp một ứng dụng, cần đối chiếu ít nhất bốn trục:

1. **Java:** JDK dùng để biên dịch và chạy ứng dụng.
2. **Spring Boot:** nền tảng quản lý dependency, auto-configuration và lifecycle.
3. **Spring Cloud release train:** tập phiên bản Spring Cloud tương thích với thế hệ Spring Boot.
4. **Spring Cloud Commons:** phiên bản artifact cụ thể chứa các abstraction chung như DiscoveryClient, ServiceRegistry, LoadBalancerClient và RefreshScope.

Các số phiên bản này không có cùng quy tắc. Ví dụ, Spring Cloud release train 2025.1.4 quản lý Spring Cloud Commons 5.0.4; không có nghĩa Commons phải mang số 2025.1.4. Spring Cloud BOM là nơi liên kết các module trong train với nhau.

Bài thuộc chương **Nâng cấp** của mô-đun **SPRING_CLOUD_CORE**. Mô-đun giúp người học hiểu các nền tảng cốt lõi của Spring Cloud trong hệ thống phân tán, đặc biệt Spring Cloud Commons, Context, cấu hình ngoài và khả năng tương thích với Spring Boot; người học cũng tìm hiểu refresh scope, discovery, service registry, giao tiếp dịch vụ và kiểm thử, vận hành các abstraction chung.

Sau bài học, người học có thể:

- Đọc bảng tương thích giữa Java, Spring Boot và Spring Cloud.
- Chọn release train theo phiên bản Spring Boot đang dùng.
- Tra phiên bản Spring Cloud Commons do BOM quản lý.
- Phân biệt bản GA, bản preview và release train đã hết hỗ trợ OSS.
- Cấu hình Maven hoặc Gradle bằng Spring Cloud BOM.
- Kiểm tra phiên bản dependency thực tế được resolve.
- Lập kế hoạch nâng cấp khi Java, Boot hoặc Cloud không còn nằm trong ma trận hỗ trợ.

## 2. Cách đọc bốn trục phiên bản

### 2.1. Java là baseline của Spring Boot

Spring Boot xác định JDK tối thiểu và tập JDK tương thích cho từng dòng phát hành. Với các dòng hiện đại:

- Spring Boot 2.x có baseline Java 8.
- Spring Boot 3.x yêu cầu Java 17 trở lên.
- Spring Boot 4.x yêu cầu Java 17 trở lên.

Java 17 là baseline chung của Boot 3 và Boot 4, nhưng điều đó không có nghĩa mọi dependency bên thứ ba trong ứng dụng đều hỗ trợ mọi JDK mới hơn. Hãy kiểm tra yêu cầu của driver, agent, SDK và thư viện tích hợp.

Bảng trong bài ghi **JDK tối thiểu** để dễ chọn môi trường. Phiên bản Java tối đa được hỗ trợ có thể thay đổi theo từng minor/patch của Spring Boot; ví dụ Boot 3.5.16 và Boot 4.1.2 có giới hạn Java tối đa khác nhau. Không suy luận giới hạn đó chỉ từ major version.

### 2.2. Spring Boot quyết định release train tương thích

Spring Cloud công bố bảng mapping release train với Spring Boot generation. Đây là điểm bắt đầu khi chọn dependency:

- Boot 4.0.x và Boot 4.1.x dùng Spring Cloud 2025.1.x; hỗ trợ Boot 4.1.x bắt đầu từ Spring Cloud 2025.1.2.
- Boot 3.5.x tương ứng Spring Cloud 2025.0.x.
- Boot 3.4.x tương ứng Spring Cloud 2024.0.x.
- Boot 3.2.x/3.3.x tương ứng Spring Cloud 2023.0.x; Boot 3.3.x được hỗ trợ từ 2023.0.2.
- Boot 3.0.x/3.1.x tương ứng Spring Cloud 2022.0.x; Boot 3.1.x được hỗ trợ từ 2022.0.3.
- Boot 2.6.x/2.7.x tương ứng Spring Cloud 2021.0.x; Boot 2.7.x được hỗ trợ từ 2021.0.3.

Không chọn release train chỉ dựa trên số thứ tự có vẻ gần nhau. Hãy dùng mapping chính thức của Spring Cloud.

### 2.3. Commons được quản lý bởi release train BOM

Spring Cloud Commons có version riêng. BOM của train quản lý version Commons cùng các module khác, ví dụ:

| Spring Cloud release train | Spring Cloud Commons |
| --- | --- |
| 2025.1.x | 5.0.x |
| 2025.0.x | 4.3.x |
| 2024.0.x | 4.2.x |
| 2023.0.x | 4.1.x |
| 2022.0.x | 4.0.x |
| 2021.0.x | 3.1.x |
| 2020.0.x | 3.0.x |
| Hoxton | 2.2.x |
| Greenwich | 2.1.x |
| Finchley | 2.0.x |

Các dòng trong bảng là **series** của module Commons. Patch version cụ thể do release train BOM chọn; không nên tự lấy một patch version từ train khác rồi ép vào ứng dụng.

## 3. Ma trận phiên bản tại ngày 18-11-2026

| Spring Cloud train | Spring Boot tương thích | Java tối thiểu | Spring Cloud Commons | Trạng thái tại thời điểm tra cứu |
| --- | --- | --- | --- | --- |
| 2026.0.0-RC2 (Paddington) | 4.2.0-RC2 | 17 | 5.1.0-RC2 | Preview, chưa phải GA |
| 2025.1.4 (Oakwood) | 4.0.x; 4.1.x từ 2025.1.2 | 17 | 5.0.4 | GA, train ổn định mới nhất |
| 2025.0.3 (Northfields) | 3.5.15; thuộc dòng Boot 3.5.x | 17 | 4.3.3 | Bản OSS cuối; hỗ trợ OSS kết thúc 30-06-2026 |
| 2024.0.3 (Moorgate) | 3.4.12 | 17 | 4.2.4 | Hết hỗ trợ OSS |
| 2023.0.6 (Leyton) | 3.3.13 | 17 | 4.1.6 | Hết hỗ trợ OSS |
| 2022.0.5 (Kilburn) | 3.0.13; train hỗ trợ 3.0.x/3.1.x | 17 | 4.0.5 | Hết hỗ trợ OSS |
| 2021.0.x (Jubilee) | 2.6.x/2.7.x | 8 | 3.1.x | Hết hỗ trợ OSS |
| 2020.0.x (Ilford) | 2.4.x/2.5.x | 8 | 3.0.x | Hết hỗ trợ OSS |
| Hoxton | 2.2.x/2.3.x | 8 | 2.2.x | Hết hỗ trợ OSS |
| Greenwich | 2.1.x | 8 | 2.1.x | Hết hỗ trợ OSS |
| Finchley | 2.0.x | 8 | 2.0.x | Hết hỗ trợ OSS |

### 3.1. Dòng nên chọn cho ứng dụng mới

Tại ngày 18-11-2026:

- **GA mới nhất:** Spring Cloud 2025.1.4, Spring Cloud Commons 5.0.4.
- **Spring Boot ổn định mới nhất:** Boot 4.1.2; train 2025.1.x hỗ trợ Boot 4.1.x từ 2025.1.2.
- **JDK tối thiểu:** Java 17 cho Boot 4.x.
- **Preview tiếp theo:** Spring Cloud 2026.0.0-RC2, Boot 4.2.0-RC2, Commons 5.1.0-RC2; chỉ dùng để thử nghiệm tương thích và chuẩn bị nâng cấp.

Nếu bắt đầu một ứng dụng Spring Cloud mới, dùng Boot 4.1.x cùng Cloud 2025.1.x là lựa chọn GA mới nhất trong ma trận đã kiểm tra. Có thể dùng Boot 4.0.x cùng train này nếu hệ thống cần giữ nguyên minor Boot 4.0.

### 3.2. Lưu ý về Spring Cloud 2025.0.x

Spring Cloud 2025.0.3 là bản phát hành OSS cuối của train 2025.0.x. Spring thông báo hỗ trợ OSS cho train này kết thúc ngày 30-06-2026. Vì vậy, mặc dù Boot 3.5.x vẫn có các bản Spring Boot ổn định, không nên hiểu rằng Spring Cloud 2025.0.x vẫn được cập nhật OSS sau ngày kết thúc hỗ trợ.

Nếu ứng dụng vẫn cần Boot 3.5.x, hãy đánh giá hỗ trợ thương mại và kế hoạch chuyển sang Boot 4.x/Cloud 2025.1.x. Không nâng riêng Commons lên 5.x để cố giữ Boot 3.5; đó là trộn hai thế hệ dependency.

### 3.3. Phân biệt GA và preview

2026.0.0-RC2 là release candidate. Nó được công bố dựa trên Boot 4.2.0-RC2 và Commons 5.1.0-RC2. Các phiên bản này có thể thay đổi trước GA; không đưa chúng vào production chỉ vì số phiên bản mới hơn.

Khi ghi tài liệu hoặc tạo release manifest, cần giữ suffix -M, -RC hoặc -SNAPSHOT. Không xóa suffix để làm một bản preview trông giống bản phát hành ổn định.

## 4. Ví dụ chọn version cho ứng dụng

Giả sử ứng dụng dùng Java 17 và cần Spring Cloud LoadBalancer cùng các abstraction Commons. Cách chọn:

1. Chọn Spring Boot 4.1.2.
2. Tra bảng tương thích: Boot 4.1.x dùng Cloud 2025.1.x từ 2025.1.2.
3. Chọn patch train GA hiện tại là Cloud 2025.1.4.
4. Để BOM chọn Commons 5.0.4.
5. Không khai báo version riêng cho từng Spring Cloud starter hoặc Commons.

Ma trận của ứng dụng:

| Thành phần | Version được chọn |
| --- | --- |
| Java toolchain/runtime | 17 |
| Spring Boot | 4.1.2 |
| Spring Cloud release train BOM | 2025.1.4 |
| Spring Cloud Commons | 5.0.4, do BOM quản lý |
| Spring Cloud LoadBalancer | Version do BOM 2025.1.4 quản lý |

## 5. Cấu hình Maven bằng Spring Cloud BOM

Ví dụ POM dùng Spring Boot parent và import Spring Cloud release train BOM:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2025.1.4</spring-cloud.version>
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

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-commons</artifactId>
    </dependency>
</dependencies>
```

Trong POM này:

- Spring Boot parent quản lý dependency thuộc hệ sinh thái Boot.
- spring-cloud-dependencies quản lý các module Spring Cloud theo train 2025.1.4.
- Các dependency Spring Cloud không cần khai báo version riêng.
- spring-cloud-commons thường đã có mặt gián tiếp qua starter. Chỉ khai báo trực tiếp khi mã nguồn ứng dụng thật sự dùng API Commons ở compile time; nếu không, chỉ cần starter tương ứng.

Nếu dự án không dùng Spring Boot parent, vẫn có thể import spring-cloud-dependencies trong dependencyManagement cùng với Boot BOM hoặc cơ chế quản lý dependency hiện có. Không import một BOM Cloud khác train chỉ để lấy một module riêng.

## 6. Cấu hình Gradle bằng Spring Cloud BOM

Ví dụ dùng Gradle Groovy DSL với plugin dependency management:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

ext {
    set('springCloudVersion', '2025.1.4')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'org.springframework.cloud:spring-cloud-commons'
}
```

Có thể dùng Gradle native platform/BOM dependency management thay cho plugin. Dù dùng cách nào, mục tiêu vẫn là một release train BOM duy nhất quản lý các module Spring Cloud.

## 7. Kiểm tra version thực tế được resolve

Không chỉ đọc version trong file build. Dependency có thể bị ghi đè bởi:

- Một BOM khác được import.
- Version được khai báo trực tiếp ở dependency.
- Dependency constraint hoặc resolution strategy của Gradle.
- Dependency bắc cầu từ một thư viện khác.
- Parent POM hoặc convention plugin của tổ chức.

### 7.1. Maven

Xem cây dependency Commons:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-commons
```

Xem POM sau khi hợp nhất:

```bash
mvn help:effective-pom
```

Trong kết quả, xác nhận spring-cloud-commons được resolve về 5.0.4 nếu dùng Cloud 2025.1.4.

### 7.2. Gradle

Xem dependency được chọn và lý do chọn:

```bash
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
```

Nếu muốn xem toàn bộ runtime graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Kiểm tra JVM mà build tool sử dụng:

```bash
java -version
mvn -version
./gradlew --version
```

java -version trong shell chưa chắc là JVM mà IDE hoặc Gradle daemon đang dùng. Cần đối chiếu toolchain, JVM của build tool và runtime trong container/deployment.

## 8. Compatibility Verifier của Spring Cloud

Spring Cloud Commons có Compatibility Verifier để phát hiện một số tổ hợp Spring Boot không nằm trong danh sách tương thích của train. Có thể bật bằng:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

Trong các phiên bản Commons hiện hành, verifier được cấu hình qua spring.cloud.compatibility-verifier.enabled; property metadata ghi mặc định là false. Vì vậy, nếu muốn dùng nó như một bước kiểm tra startup, cần bật tường minh.

Verifier là một lớp bảo vệ bổ sung. Nó không thay thế bảng tương thích chính thức, BOM hoặc việc kiểm tra dependency tree. Không chỉnh compatible-boot-versions để che một tổ hợp không được Spring Cloud hỗ trợ. Nếu buộc phải dùng tổ hợp tùy biến, cần có kiểm thử tích hợp, đánh giá rủi ro và quyết định hỗ trợ rõ ràng.

## 9. Những lỗi thường gặp khi lập ma trận

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Boot khởi động nhưng Spring Cloud báo không tương thích | Chọn release train không hỗ trợ Boot generation đang dùng | Đối chiếu bảng mapping, chọn đúng train và bật Compatibility Verifier. |
| NoSuchMethodError hoặc NoClassDefFoundError trong Commons | Ép một module Commons khác series so với BOM hoặc trộn nhiều train | Bỏ version override, dùng một Cloud BOM và kiểm tra dependency tree. |
| Commons 4.x đi cùng Boot 4.x | Lấy version Commons từ train Boot 3.x | Dùng Cloud 2025.1.x và Commons 5.0.x cho Boot 4.x. |
| Commons 5.x đi cùng Boot 3.5.x | Ép Commons lên major mới nhưng giữ train cũ | Không trộn major; chọn train tương ứng với Boot hoặc nâng Boot. |
| Dùng Cloud 2025.0.x cho Boot 4.0.x | Nhầm 2025.0 với 2025.1 | Boot 4.0/4.1 dùng 2025.1.x; 2025.0.x dành cho Boot 3.5.x. |
| Dùng 2026.0.0-RC2 trong production | Nhầm release candidate là GA | Chờ GA hoặc chỉ dùng RC trong môi trường đánh giá có kiểm soát. |
| Build chạy Java mới nhưng deploy lỗi | Build JVM và runtime container khác nhau hoặc thư viện phụ chưa hỗ trợ | Kiểm tra JDK runtime, toolchain và yêu cầu của third-party dependencies. |
| Dependency tree hiển thị Commons patch khác mong đợi | BOM khác, direct version hoặc resolution rule ghi đè | Xem effective POM/dependencyInsight và loại bỏ override không cần thiết. |
| Release train đã hết hỗ trợ OSS | Tiếp tục dùng train cũ vì ứng dụng vẫn build thành công | Lập kế hoạch nâng cấp hoặc xác nhận phạm vi hỗ trợ thương mại. |

## 10. Quy trình lập ma trận trước khi nâng cấp

1. Ghi lại Java runtime, Java toolchain và version Spring Boot hiện tại.
2. Tra release train tương thích với Boot generation trong bảng Spring Cloud.
3. Kiểm tra train còn được hỗ trợ OSS hay chỉ còn hỗ trợ thương mại.
4. Chọn patch release mới nhất trong train tương ứng.
5. Tra version spring-cloud-commons trong train reference/BOM.
6. Import duy nhất spring-cloud-dependencies BOM phù hợp.
7. Bỏ version riêng của các Spring Cloud module nếu BOM đã quản lý.
8. Chạy dependency:tree hoặc dependencyInsight để xác nhận version thực tế.
9. Bật Compatibility Verifier trong môi trường kiểm thử/startup validation.
10. Chạy test cho discovery, registration, load balancing, refresh scope và service calls.
11. Kiểm tra các third-party integration như Eureka, Consul, Kubernetes, Feign và broker.
12. Ghi Boot, Cloud train, Commons version, Java runtime và ngày tra cứu vào release manifest.

## 11. Lộ trình nâng cấp tham khảo

### 11.1. Từ Boot 2.7 / Cloud 2021.0 sang Boot 3.x

Boot 2.7 dùng Java 8 trở lên và Cloud 2021.0 dùng Commons 3.1.x. Khi chuyển sang Boot 3.x, cần Java 17 và release train Cloud 2022.0 trở lên tùy minor Boot:

- Boot 3.0/3.1: Cloud 2022.0.x, Commons 4.0.x.
- Boot 3.2/3.3: Cloud 2023.0.x, Commons 4.1.x.
- Boot 3.4: Cloud 2024.0.x, Commons 4.2.x.
- Boot 3.5: Cloud 2025.0.x, Commons 4.3.x.

Các train 2021.0 và 2022.0 hiện đã hết hỗ trợ OSS. Nếu hệ thống còn dùng chúng, nên lập lộ trình nâng cấp qua các mốc Boot/Cloud được hỗ trợ, thay vì chỉ nâng riêng Commons.

### 11.2. Từ Boot 3.5 / Cloud 2025.0 sang Boot 4.x / Cloud 2025.1

Đây là bước nâng major của Spring Boot và Spring Framework. Lộ trình:

1. Kiểm tra Java 17 trở lên và nâng build tool theo yêu cầu Boot 4.
2. Đọc migration guide của Spring Boot 4 và các module Spring Cloud đang dùng.
3. Nâng Boot lên dòng 4.0.x hoặc 4.1.x.
4. Chuyển Cloud BOM sang 2025.1.x.
5. Để BOM quản lý Commons 5.0.x.
6. Xử lý API/package đã bị loại hoặc thay đổi trong Spring Framework 7, Boot 4 và các Spring Cloud modules.
7. Chạy integration test cho cấu hình, discovery, registry, load balancer, HTTP client và observability.
8. Triển khai canary trước khi nâng toàn bộ dịch vụ.

Không nâng Commons 4.3 lên 5.0 một cách độc lập trong khi giữ nguyên các module Cloud 2025.0. Release train BOM phải được nâng cùng lúc.

## 12. Release train và vòng đời hỗ trợ

Spring Cloud release train là tập hợp các project độc lập, mỗi project có thể có lịch phát hành riêng. Spring Cloud phát hành BOM để quản lý một tập version đã được tuyển chọn. Vì vậy:

- Một train có thể vẫn có artifact trên Maven Central sau khi hết hỗ trợ OSS.
- Có version tồn tại không đồng nghĩa còn được vá lỗi hoặc CVE.
- Trạng thái hỗ trợ của train phụ thuộc vòng đời các project thành phần và Spring Boot mà train hỗ trợ.
- Spring Cloud 2025.0.3 là ví dụ: artifact vẫn có thể tải được, nhưng OSS support đã kết thúc ngày 30-06-2026.

Spring Cloud support policy nêu major được hỗ trợ tối thiểu ba năm và minor tối thiểu mười hai tháng theo chính sách OSS; release train không có một lịch hỗ trợ riêng tách biệt khỏi các project thành phần. Khi lên kế hoạch nâng cấp, kiểm tra cả Spring Cloud Supported Versions và vòng đời Spring Boot, không chỉ kiểm tra Maven Central còn lưu artifact.

## 13. Câu hỏi tự kiểm tra

1. Vì sao Java, Spring Boot, Spring Cloud release train và Spring Cloud Commons là bốn trục phiên bản khác nhau?
2. Spring Cloud 2025.1.4 tương thích với những dòng Spring Boot nào?
3. Vì sao Cloud 2025.1.4 quản lý Commons 5.0.4 chứ không phải Commons 2025.1.4?
4. Boot 3.x và Boot 4.x yêu cầu Java tối thiểu nào?
5. Tại sao 2026.0.0-RC2 không nên được xem là GA?
6. Cloud 2025.0.3 có trạng thái hỗ trợ OSS như thế nào sau ngày 30-06-2026?
7. Vì sao nên import spring-cloud-dependencies BOM thay vì đặt version cho từng module?
8. Dùng Maven hoặc Gradle command nào để xác minh version Commons thực tế?
9. Compatibility Verifier có được bật mặc định trong Commons 5.0.4 không?
10. Cần kiểm thử những phần nào sau khi nâng Boot/Cloud major?

## 14. Tài liệu tham khảo chính thức

- [Spring Cloud — Release Train / Spring Boot Compatibility](https://spring.io/projects/spring-cloud/)
- [Spring Cloud Supported Versions and Project Mapping](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
- [Spring Cloud Release 2025.1.4 — Project Versions](https://docs.spring.io/spring-cloud-release/reference/index.html)
- [Spring Cloud Release 2025.0.3 — Project Versions](https://docs.spring.io/spring-cloud-release/reference/2025.0/index.html)
- [Spring Cloud Release 2024.0.3 — Project Versions](https://docs.spring.io/spring-cloud-release/reference/2024.0/index.html)
- [Spring Cloud Release 2023.0.6 — Project Versions](https://docs.spring.io/spring-cloud-release/reference/2023.0/index.html)
- [Spring Cloud Release 2026.0.0-RC2 — Preview Project Versions](https://docs.spring.io/spring-cloud-release/reference/2026.0/index.html)
- [Spring Boot 4.1 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4.0 System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 2.7.18 System Requirements](https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/getting-started.html#system-requirements)
- [Spring Cloud Commons 5.0.4 Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud 2025.0.3 — Final OSS Release Announcement](https://spring.io/blog/2026/06/11/spring-cloud-2025-0-3-aka-northfields-has-been-released/)
- [Spring Cloud 2026.0.0-RC2 Announcement](https://spring.io/blog/2026/11/05/spring-cloud-2026-0-0-rc2-has-been-released/)

Ma trận phiên bản là ảnh chụp theo thời điểm tra cứu. Trước mỗi lần phát hành, hãy đối chiếu lại release train mới nhất, Spring Boot compatibility table, Commons project version và trạng thái hỗ trợ OSS.
