# Chọn phiên bản Java, Spring Boot và Spring Cloud Open Service Broker tương thích

Khi khởi tạo một service broker bằng Spring Cloud Open Service Broker, cần chọn các phiên bản theo cùng một ma trận tương thích. Java quyết định môi trường biên dịch và chạy; Spring Boot cung cấp nền tảng ứng dụng; Spring Cloud Open Service Broker (SCOSB) cung cấp các thành phần triển khai Open Service Broker API (OSB API). Nếu broker còn dùng những dự án Spring Cloud khác, chẳng hạn Spring Cloud Kubernetes hoặc Spring Cloud Config, cần chọn thêm đúng Spring Cloud release train tương ứng với Spring Boot.

Không nên chọn riêng từng phiên bản theo số mới nhất hiển thị trên Maven Central. Một bộ phiên bản chỉ phù hợp khi phiên bản Java, Spring Boot, Spring Cloud Open Service Broker, Spring Cloud release train (nếu có) và nền tảng triển khai có thể làm việc cùng nhau.

## 1. Phân biệt các phiên bản cần chọn

Trong dự án service broker có một số trục phiên bản độc lập:

| Thành phần | Vai trò | Cần kiểm tra |
|---|---|---|
| Java Development Kit (JDK) | Biên dịch và chạy ứng dụng broker | Phiên bản Java tối thiểu của Spring Boot và SCOSB; JDK được hỗ trợ trên máy phát triển, CI và môi trường chạy |
| Spring Boot | Khởi tạo ứng dụng, cấu hình tự động, web server và quản lý dependency nền tảng | Phiên bản Java tối thiểu, Spring Framework đi kèm và ma trận tương thích của các thư viện |
| Spring Cloud release train | Quản lý đồng bộ các dự án Spring Cloud bổ sung như Kubernetes, Config hoặc Gateway | Release train phải tương thích với phiên bản Spring Boot đang dùng |
| Spring Cloud Open Service Broker | Cung cấp starter, controller, model và interface để triển khai OSB API | Phiên bản SCOSB phải được xây dựng cho dòng Spring Boot tương ứng và đáp ứng OSB API mà platform hỗ trợ |
| Spring MVC hoặc Spring WebFlux | Cung cấp web stack để nhận request OSB API | Chọn một web stack phù hợp với cách xử lý I/O và các thư viện của broker |

Cần chú ý rằng **phiên bản Spring Cloud Open Service Broker không phải số phiên bản của Spring Cloud release train**. Ví dụ, SCOSB 5.2.1 là phiên bản riêng của dự án Open Service Broker. Spring Cloud 2025.1.x là release train quản lý các dự án Spring Cloud khác. Hai giá trị này có thể xuất hiện cùng trong một dự án nhưng phải được kiểm tra theo tài liệu tương thích riêng.

Spring Cloud Open Service Broker cung cấp starter cho ứng dụng Spring Boot và hỗ trợ cả Spring MVC lẫn Spring WebFlux. Starter của dự án không tự kéo theo dependency của hai web stack này; ứng dụng cần khai báo một Spring Boot web starter tương ứng. [Tài liệu Spring Cloud Open Service Broker](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/).

## 2. Chọn phiên bản Java

Java là nền tảng đầu tiên cần xác định vì JDK được dùng trong quá trình biên dịch, kiểm thử và chạy broker.

### Xác định phiên bản Java tối thiểu

Đọc yêu cầu Java của phiên bản Spring Boot và SCOSB dự định sử dụng. Phiên bản Java của dự án phải đáp ứng yêu cầu cao hơn trong các thành phần đó. Ví dụ, tài liệu của Spring Cloud Open Service Broker 5.2.1 công bố yêu cầu Java 17 trở lên. Vì vậy, JDK 17 là mức tối thiểu cho cấu hình mẫu dùng SCOSB 5.2.1.

Mức tối thiểu không nhất thiết là lựa chọn duy nhất. Khi triển khai thật, nên cân nhắc một bản JDK LTS còn được nhà cung cấp JDK và nền tảng vận hành hỗ trợ. Cần xác nhận phiên bản đó tương thích với Spring Boot, SCOSB, công cụ build, agent giám sát và image runtime. Nếu hạ tầng đang chuẩn hóa Java 17 thì có thể dùng Java 17 làm baseline; nếu tổ chức dùng một LTS mới hơn thì cần chạy bộ kiểm thử trên chính JDK đó trước khi phát hành.

### Đồng bộ JDK giữa các môi trường

Một lỗi thường gặp là máy lập trình dùng JDK mới nhưng CI hoặc container production lại chạy JDK cũ. Khi đó mã nguồn có thể biên dịch thành công trên máy cá nhân nhưng thất bại khi build hoặc khởi động ở môi trường khác.

Cần thống nhất các giá trị sau:

- JDK được cài trên máy phát triển.
- Java toolchain hoặc cấu hình compiler trong Maven/Gradle.
- JDK được cài trên runner CI.
- Java runtime trong container hoặc máy chủ triển khai.
- Phiên bản Java được IDE sử dụng để import và chạy dự án.

Kiểm tra nhanh bằng các lệnh sau:

~~~powershell
java -version
javac -version

# Maven Wrapper
.\mvnw.cmd -v

# Gradle Wrapper
.\gradlew.bat -version
~~~

Khi làm việc trên Windows, dùng các file wrapper có đuôi .cmd hoặc .bat như ví dụ. Trên Linux và macOS có thể dùng ./mvnw và ./gradlew. Wrapper giúp nhóm phát triển thống nhất phiên bản Maven hoặc Gradle, nhưng không tự thay thế JDK: máy build vẫn phải có JDK phù hợp.

## 3. Chọn Spring Boot và Spring Cloud release train

Spring Boot và Spring Cloud có quan hệ tương thích theo release train. Khi dự án sử dụng các module Spring Cloud, cần chọn release train được công bố tương thích với dòng Spring Boot đang dùng.

Bảng dưới đây là một số mốc tương thích có liên quan đến các dòng Spring hiện đại. Đây là thông tin theo tài liệu Spring tại thời điểm biên soạn; cần kiểm tra lại trang dự án trước mỗi lần nâng cấp vì các bản service release có thể bổ sung hỗ trợ hoặc thay đổi trạng thái hỗ trợ.

| Spring Cloud release train | Dòng Spring Boot tương thích | Ghi chú |
|---|---|---|
| 2026.0.x (Paddington) | 4.2.x | 2026.0.0 GA được xây dựng trên Spring Boot 4.2.0 |
| 2025.1.x (Oakwood) | 4.0.x; 4.1.x từ 2025.1.2 | Phù hợp với Boot 4.1.x khi dùng bản train hỗ trợ tương ứng |
| 2025.0.x (Northfields) | 3.5.x | Kiểm tra trạng thái hỗ trợ hiện tại trước khi chọn |
| 2024.0.x (Moorgate) | 3.4.x | Kiểm tra trạng thái hỗ trợ hiện tại trước khi chọn |
| 2023.0.x (Leyton) | 3.2.x và 3.3.x từ 2023.0.2 | Dòng cũ; cần xem chính sách hỗ trợ |

Tài liệu Spring Cloud đánh dấu một số release train cũ đã hết vòng đời hỗ trợ cộng đồng. Vì vậy, không nên lấy một bảng tương thích cũ rồi mặc định rằng mọi dòng trong bảng đều còn được cập nhật bảo mật. Cần kiểm tra cả hai thông tin: phiên bản có tương thích kỹ thuật hay không và phiên bản đó còn được hỗ trợ hay không.

Tại thời điểm biên soạn, Spring Cloud 2026.0.0 đã được phát hành GA và dựa trên Spring Boot 4.2.0. Dòng Spring Cloud 2025.1.x hỗ trợ Spring Boot 4.1.x từ bản 2025.1.2. Nếu dự án chỉ dùng Spring Cloud Open Service Broker và không dùng module Spring Cloud nào khác, không nhất thiết phải thêm Spring Cloud release train BOM chỉ để có starter OSB. Nếu có thêm Spring Cloud Kubernetes, Config hoặc module khác, hãy import BOM tương ứng để quản lý phiên bản các module đó đồng bộ.

Nguồn đối chiếu: [Spring Cloud project và bảng tương thích release train](https://spring.io/projects/spring-cloud/), [thông báo Spring Cloud 2026.0.0 GA](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/).

## 4. Chọn phiên bản Spring Cloud Open Service Broker

SCOSB có vòng phát hành và ma trận tương thích riêng. Khi chọn phiên bản, cần xem phiên bản Spring Boot mà thư viện được build cùng, phiên bản Java tối thiểu, Spring Framework đi kèm và mức OSB API mà thư viện hỗ trợ.

Tại ngày 27/11/2026, các mốc sau giúp minh họa cách lựa chọn:

| Dòng SCOSB | Spring Boot được build cùng | Spring Framework | Java | OSB API | Trạng thái |
|---|---|---|---|---|---|
| 5.2.1 | 4.1.2 | 7.0.10 | 17+ | 2.17 | GA |
| 5.3.x | 4.2.x | 7.1.x | 17+ | 2.17 | Prerelease |

SCOSB 5.2.1 là lựa chọn ổn định cho dự án dùng Spring Boot 4.1.x. Dòng SCOSB 5.3.x được xây dựng cho Spring Boot 4.2 và Spring Framework 7.1, nhưng hiện là prerelease. Nếu mục tiêu là một broker production cần phiên bản GA, hãy ưu tiên dòng GA phù hợp với Spring Boot đã chọn. Chỉ sử dụng milestone, release candidate hoặc snapshot khi dự án chủ động chấp nhận rủi ro của phần mềm tiền phát hành và có kế hoạch kiểm thử, nâng cấp tương ứng.

Không suy ra rằng mọi bản SCOSB 5.x đều dùng được với mọi bản Spring Boot 4.x. Ví dụ, SCOSB 5.2.1 được xây dựng với Spring Boot 4.1.2; dòng 5.3.x mới là dòng dành cho Spring Boot 4.2. Khi chuyển từ Boot 4.1 sang 4.2, cần nâng SCOSB theo ma trận tương thích và chạy lại kiểm thử tích hợp.

Cũng cần kiểm tra OSB API mà nền tảng đích hỗ trợ. SCOSB 5.2.1 và dòng 5.3.x được công bố hỗ trợ OSB API 2.17. Nếu platform Cloud Foundry, Kubernetes integration hoặc marketplace nội bộ có yêu cầu phiên bản API cụ thể, cần xác nhận các header phiên bản và các trường request/response được hai phía hỗ trợ trước khi triển khai.

Nguồn đối chiếu: [Spring Cloud Open Service Broker](https://spring.io/projects/spring-cloud-open-service-broker/), [ma trận và lịch sử phát hành SCOSB](https://github.com/spring-cloud/spring-cloud-open-service-broker/releases).

## 5. Chọn một bộ phiên bản cụ thể

Với một service broker mới, nên bắt đầu bằng một bộ phiên bản rõ ràng, có trạng thái hỗ trợ và có thể tái tạo trên máy phát triển, CI và production.

### Cấu hình ổn định đề xuất

Bộ phiên bản mẫu dưới đây sử dụng các bản GA đã được công bố tương thích:

| Thành phần | Phiên bản mẫu | Lý do |
|---|---|---|
| JDK | 17 trở lên | Đáp ứng baseline Java của SCOSB 5.2.1 |
| Spring Boot | 4.1.2 | Phiên bản nền mà SCOSB 5.2.1 được build cùng |
| Spring Cloud release train | 2025.1.2 trở lên trong cùng dòng 2025.1.x, nếu dùng module Spring Cloud khác | Dòng này hỗ trợ Boot 4.1.x từ 2025.1.2 |
| Spring Cloud Open Service Broker | 5.2.1 | Bản GA, hỗ trợ Boot 4.1.2 và OSB API 2.17 |
| Spring Web stack | Spring MVC hoặc Spring WebFlux | Chọn một theo kiểu xử lý I/O của ứng dụng |

Đây là cấu hình khởi đầu để học và xây dựng broker. Khi triển khai vào tổ chức cụ thể, cần thay phiên bản JDK theo chuẩn vận hành và xác nhận lại các bản vá mới nhất của dòng Spring Boot, Spring Cloud và SCOSB. Không nên cố giữ nguyên patch version lâu dài nếu đã có bản vá bảo mật hoặc sửa lỗi tương thích.

### Cấu hình thử nghiệm với Spring Boot 4.2

Nếu muốn thử Spring Boot 4.2.0 và Spring Cloud 2026.0.0, có thể nghiên cứu dòng SCOSB 5.3.x. Tuy nhiên, tại thời điểm biên soạn dòng 5.3.x vẫn là prerelease. Hãy dùng tổ hợp này cho nhánh thử nghiệm, chạy kiểm thử hồi quy và kiểm thử OSB API trên platform đích. Trước khi dùng production, chờ bản SCOSB GA tương thích hoặc có quyết định chấp nhận prerelease từ nhóm vận hành.

## 6. Khai báo dependency bằng Maven

Maven có thể dùng Spring Boot parent để quản lý các dependency Spring Boot, đồng thời import Spring Cloud BOM nếu dự án dùng thêm các module thuộc Spring Cloud release train. Phiên bản SCOSB được khai báo rõ ràng bằng property riêng.

Ví dụ sau minh họa bộ ổn định ở trên:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>service-broker</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.1.2</spring-cloud.version>
        <spring-cloud-open-service-broker.version>5.2.1</spring-cloud-open-service-broker.version>
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
            <artifactId>spring-cloud-starter-open-service-broker</artifactId>
            <version>${spring-cloud-open-service-broker.version}</version>
        </dependency>

        <!-- Chọn Spring MVC cho ví dụ này. -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Nếu dự án chỉ cần SCOSB và không sử dụng các module Spring Cloud khác, có thể bỏ phần import Spring Cloud BOM. Việc khai báo phiên bản starter SCOSB vẫn cần được giữ rõ ràng theo tài liệu của dự án. Khi thêm Spring Cloud Kubernetes hoặc Config, hãy thêm dependency tương ứng và quản lý phiên bản qua BOM của release train đã chọn.

Để dùng WebFlux, thay dependency Spring MVC bằng starter WebFlux:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Không thêm cả hai web starter một cách tùy tiện. Nếu cần cùng lúc MVC và WebFlux cho các endpoint khác nhau, phải hiểu rõ cách Spring Boot chọn application type và cách cấu hình server; với bài thực hành đầu tiên, nên chọn một stack.

## 7. Khai báo dependency bằng Gradle

Với Gradle, cần khai báo phiên bản Spring Boot plugin, Java toolchain và Spring Cloud BOM. Phiên bản SCOSB vẫn được đặt tường minh:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

ext {
    set('springCloudVersion', "2025.1.2")
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-open-service-broker:5.2.1'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Nếu chọn WebFlux, thay spring-boot-starter-web bằng spring-boot-starter-webflux. Dùng Java toolchain để Gradle có thể yêu cầu đúng phiên bản JDK cho tác vụ biên dịch, kể cả khi JDK mặc định trên máy phát triển khác phiên bản đó. Tuy vậy, CI và runtime vẫn phải được cấu hình tương thích.

Không khai báo thêm phiên bản Spring Framework, Reactor, Jackson hoặc các dependency nền tảng khác khi chúng đã được Spring Boot quản lý, trừ khi có lý do kỹ thuật và đã xác minh ma trận tương thích. Việc ghi đè dependency nền tảng tùy tiện có thể tạo ra lỗi ở runtime dù compile vẫn thành công.

## 8. Chọn Spring MVC hay Spring WebFlux

Spring Cloud Open Service Broker hỗ trợ cả hai web stack. Lựa chọn này ảnh hưởng đến cách broker tích hợp với provider và xử lý I/O.

| Tiêu chí | Spring MVC | Spring WebFlux |
|---|---|---|
| Mô hình xử lý | Servlet, thường dùng mô hình imperative | Reactive, hỗ trợ non-blocking I/O |
| Phù hợp khi | Provider SDK hoặc thư viện tích hợp chủ yếu là blocking | Provider API và các tầng tích hợp hỗ trợ reactive/non-blocking |
| Dependency | spring-boot-starter-web | spring-boot-starter-webflux |
| Lưu ý | Có thể dùng reactive return type của SCOSB trên web stack blocking | Tránh gọi blocking I/O trực tiếp trên event-loop |

Với broker gọi SDK quản trị database hoặc cloud provider theo kiểu blocking, Spring MVC thường là lựa chọn dễ tiếp cận. Nếu các client provider đều hỗ trợ reactive và đội ngũ quen với Reactor, WebFlux có thể phù hợp. Không nên chọn WebFlux chỉ vì các interface SCOSB trả về Mono hoặc Flux; cần xem toàn bộ đường đi của I/O.

Dù chọn stack nào, starter SCOSB cũng cần một Spring Boot web starter để kích hoạt auto-configuration. Thiếu dependency web có thể khiến ứng dụng khởi động nhưng các endpoint OSB không được cấu hình như mong đợi.

## 9. Xác minh phiên bản sau khi cấu hình

Sau khi tạo project và khai báo dependency, cần xác minh cả phiên bản JDK thực tế lẫn dependency đã được build tool giải quyết.

### Kiểm tra Maven

~~~powershell
java -version
.\mvnw.cmd -v
.\mvnw.cmd dependency:tree
.\mvnw.cmd verify
~~~

### Kiểm tra Gradle

~~~powershell
java -version
.\gradlew.bat -version
.\gradlew.bat dependencies
.\gradlew.bat check
~~~

Khi xem dependency tree, tập trung vào các nhóm sau:

- spring-boot và spring-framework phải nằm trong dòng do Spring Boot parent hoặc plugin quản lý.
- spring-cloud-commons, spring-cloud-kubernetes và các module Spring Cloud khác phải nằm trong dòng release train đã chọn.
- spring-cloud-starter-open-service-broker và các artifact SCOSB phải cùng một dòng phiên bản tương thích.
- Chỉ có web stack dự kiến được kích hoạt, trừ khi dự án có cấu hình chủ đích cho cả hai.
- Không có phiên bản SNAPSHOT, milestone hoặc release candidate ngoài chủ đích.

Một lần build thành công chưa chứng minh broker tương thích với platform. Sau khi compile và test thành công, cần chạy contract test hoặc integration test với OSB API, kiểm tra catalog, provision, binding, polling và deprovision trên môi trường tương tự platform đích. Đồng thời xác minh các header phiên bản API mà platform gửi đến broker.

## 10. Quy trình chọn phiên bản khi bắt đầu hoặc nâng cấp

Có thể áp dụng quy trình sau cho mỗi lần tạo dự án hoặc nâng cấp stack:

1. **Xác định môi trường chạy.** Ghi nhận JDK mà Cloud Foundry, Kubernetes container hoặc máy chủ đích hỗ trợ; xác định chính sách LTS của tổ chức.
2. **Chọn Java baseline.** Đối chiếu yêu cầu Java tối thiểu của Spring Boot và SCOSB, sau đó chọn JDK được hỗ trợ trên toàn bộ môi trường.
3. **Chọn Spring Boot.** Ưu tiên bản GA còn được hỗ trợ và có bản vá phù hợp với chính sách vận hành.
4. **Chọn Spring Cloud release train.** Nếu dùng các module Spring Cloud khác, tra bảng tương thích Boot và import đúng BOM. Nếu không dùng các module đó, không cần thêm BOM chỉ vì tên dự án có chữ Spring Cloud.
5. **Chọn SCOSB.** Tra ma trận riêng của Spring Cloud Open Service Broker, xác minh Boot, Framework, Java và OSB API mà phiên bản đó hỗ trợ.
6. **Chọn web stack.** Thêm Spring MVC hoặc WebFlux phù hợp với client provider và mô hình I/O.
7. **Khóa dependency.** Dùng Maven parent/BOM hoặc Gradle dependency management; tránh để version trôi theo từ khóa latest hoặc snapshot.
8. **Kiểm tra trên CI và platform đích.** Build bằng đúng JDK, chạy test, kiểm tra dependency tree và thực hiện contract/integration test với platform.

Khi nâng cấp, nên thay đổi có kiểm soát. Ví dụ, nếu chuyển từ Spring Boot 4.1 lên 4.2, hãy kiểm tra lại Spring Cloud release train, SCOSB, Java runtime và các thư viện bên thứ ba trước khi đổi đồng loạt. Sau đó chạy kiểm thử hồi quy và xác minh các endpoint OSB API mà platform đang sử dụng.

## 11. Những lỗi chọn phiên bản thường gặp

**Dùng phiên bản Spring Cloud mới nhất với mọi phiên bản Spring Boot.** Spring Cloud phát hành theo release train và mỗi train chỉ tương thích với những dòng Boot nhất định. Hãy tra ma trận thay vì suy luận từ số phiên bản.

**Cho rằng SCOSB có cùng số phiên bản với Spring Cloud release train.** SCOSB có phiên bản dự án riêng. Cần kiểm tra trang SCOSB và chọn starter theo ma trận tương thích của chính dự án này.

**Dùng bản prerelease cho production mà không đánh giá rủi ro.** Milestone, release candidate và snapshot có thể thay đổi API hoặc dependency. Chỉ dùng khi có mục tiêu thử nghiệm, khóa phiên bản và kiểm thử đủ phạm vi.

**Chỉ đặt source compatibility mà không kiểm tra JDK chạy thật.** Cấu hình compiler không bảo đảm runtime container có cùng phiên bản Java. Phải kiểm tra cả CI và image triển khai.

**Quên khai báo Spring MVC hoặc WebFlux.** SCOSB starter không kéo theo web stack. Cần khai báo một web starter phù hợp để auto-configuration hoạt động.

**Ghi đè phiên bản dependency do Spring Boot quản lý.** Việc ép một phiên bản Spring Framework hoặc Reactor riêng có thể phá vỡ sự đồng bộ của dependency graph. Chỉ override khi có căn cứ, kiểm tra tương thích và có test chứng minh.

**Không kiểm tra phiên bản OSB API của platform.** Broker có thể khởi động bình thường nhưng platform gửi request hoặc mong đợi field mà phiên bản thư viện chưa hỗ trợ. Cần kiểm tra API version negotiation và contract test.

## Kết luận

Chọn phiên bản cho Spring Cloud Service Broker là quá trình ghép nhiều ma trận tương thích. Hãy bắt đầu từ JDK mà môi trường hỗ trợ, chọn Spring Boot phù hợp, ghép Spring Cloud release train nếu có dùng các module liên quan, rồi chọn phiên bản Spring Cloud Open Service Broker theo ma trận riêng của dự án. Với bộ GA ổn định được minh họa ở đây, có thể bắt đầu bằng Java 17+, Spring Boot 4.1.2 và Spring Cloud Open Service Broker 5.2.1; nếu dùng thêm Spring Cloud modules, chọn release train 2025.1.x tương thích Boot 4.1.x từ 2025.1.2. Sau cùng, xác minh dependency tree và chạy contract test với platform đích trước khi phát hành.

## Tài liệu tham khảo

- [Spring Cloud Open Service Broker — trang dự án và phiên bản hiện hành](https://spring.io/projects/spring-cloud-open-service-broker/)
- [Spring Cloud Open Service Broker — Reference Documentation 5.2.1](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/)
- [Spring Cloud Open Service Broker — Releases và version compatibility](https://github.com/spring-cloud/spring-cloud-open-service-broker/releases)
- [Spring Cloud — bảng tương thích Spring Boot và release train](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2026.0.0 GA — phát hành dựa trên Spring Boot 4.2.0](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Boot 4.2.0 — thông báo phát hành](https://spring.io/blog/2026/11/19/spring-boot-4-2-0-available-now/)

