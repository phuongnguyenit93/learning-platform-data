# Quản lý phiên bản bằng Spring Cloud BOM trong Maven hoặc Gradle

## Mục tiêu của bài học

Spring Cloud CircuitBreaker giúp ứng dụng ngăn lỗi lan truyền khi một dịch vụ phụ thuộc chậm hoặc không khả dụng. Khi triển khai, ứng dụng thường cần các thành phần thuộc nhiều nhóm: Spring Boot, Spring Cloud CircuitBreaker, Resilience4j và thư viện giao tiếp HTTP hoặc reactive. Nếu mỗi thư viện được gán một phiên bản độc lập, dự án dễ gặp xung đột API, lỗi khởi tạo bean hoặc hành vi khác nhau giữa môi trường phát triển và môi trường triển khai.

Spring Cloud BOM (Bill of Materials) giải quyết phần quản lý phiên bản bằng cách cung cấp một tập hợp phiên bản đã được căn chỉnh cho một release train Spring Cloud. Maven và Gradle có thể nhập BOM để các dependency Spring Cloud dùng phiên bản tương thích mà không phải khai báo phiên bản lặp lại ở từng dòng dependency.

Sau bài học, bạn có thể:

- Giải thích BOM quản lý phiên bản như thế nào và vì sao BOM không tự thêm thư viện vào ứng dụng.
- Chọn Spring Cloud release train tương thích với phiên bản Spring Boot của dự án.
- Import Spring Cloud BOM trong Maven bằng dependencyManagement.
- Import BOM trong Gradle bằng plugin dependency management hoặc cơ chế platform có sẵn.
- Khai báo starter CircuitBreaker đồng bộ hoặc reactive mà không gắn phiên bản riêng.
- Kiểm tra dependency tree và xử lý các phiên bản bị ghi đè hoặc xung đột.

## 1. Vì sao cần quản lý phiên bản tập trung?

Một ứng dụng Spring Boot có thể dùng nhiều thư viện cùng lúc. Ví dụ, order-service gọi inventory-service và cần circuit breaker để bảo vệ lời gọi. Phần tích hợp có thể gồm:

- Spring Boot cung cấp nền tảng ứng dụng, auto-configuration và Actuator.
- Spring Cloud CircuitBreaker cung cấp API trừu tượng để tạo circuit breaker.
- Resilience4j cung cấp implementation với các trạng thái CLOSED, OPEN, HALF_OPEN, sliding window, timeout hoặc bulkhead.
- WebClient, RestClient hoặc HTTP client khác thực hiện lời gọi mạng.

Mỗi thư viện có thể phát hành phiên bản riêng. Một phiên bản Spring Cloud CircuitBreaker có thể được xây dựng để làm việc với một dải phiên bản Spring Framework và Spring Boot nhất định. Nếu tùy ý ghép các phiên bản, dự án có thể biên dịch được nhưng gặp lỗi khi chạy, chẳng hạn thiếu method, không tạo được bean hoặc không tương thích giữa các lớp cấu hình.

Một cách quản lý thủ công là ghi phiên bản vào từng dependency. Cách này nhanh chóng trở nên khó bảo trì: khi nâng cấp, phải tìm mọi vị trí có cùng thư viện, kiểm tra các dependency bắc cầu và bảo đảm tất cả vẫn tương thích. BOM gom các phiên bản đã được quản lý vào một điểm cấu hình để công cụ build giải quyết nhất quán hơn.

## 2. BOM là gì và hoạt động ra sao?

BOM là một file POM có packaging là pom, chứa các khai báo dependency management. Khi dự án nhập BOM, Maven hoặc Gradle đọc các quy tắc phiên bản trong đó để chọn phiên bản cho dependency tương ứng.

BOM có hai vai trò cần phân biệt:

1. **Quản lý phiên bản:** cung cấp phiên bản mặc định cho những dependency được BOM quản lý.
2. **Thêm dependency vào ứng dụng:** được thực hiện riêng trong phần dependencies của dự án.

Vì vậy, chỉ import Spring Cloud BOM không làm cho Spring Cloud CircuitBreaker xuất hiện trong classpath. Dự án vẫn cần khai báo starter tương ứng. Ngược lại, khi starter đã được BOM quản lý, thông thường không cần ghi phiên bản trên chính dependency đó.

Spring Cloud BOM có tọa độ:

    org.springframework.cloud:spring-cloud-dependencies:<release-train-version>

Phần version ở đây là phiên bản của Spring Cloud release train. Nó không phải phiên bản Spring Boot và không nên được chọn bằng cách sao chép số phiên bản Boot. Hãy chọn release train theo bảng tương thích chính thức của Spring Cloud đối với dòng Spring Boot đang dùng.

BOM giúp đồng bộ các thành phần trong phạm vi mà nó quản lý. Nó không thay thế việc chọn phiên bản JDK, phiên bản plugin Maven/Gradle hoặc các thư viện ngoài phạm vi BOM. Nếu dự án có nhiều BOM, cần hiểu quy tắc ưu tiên của công cụ build và kiểm tra phiên bản cuối cùng đã được resolve.

## 3. Chọn phiên bản Spring Cloud tương thích

Trước khi sửa file build, hãy xác định nền tảng hiện có của dự án:

- Phiên bản Spring Boot đang được khai báo trong parent POM hoặc plugin Gradle.
- Phiên bản Java mà dự án biên dịch và chạy.
- Các module Spring Cloud khác đã được sử dụng.
- Phiên bản Spring Cloud release train được hỗ trợ cho dòng Spring Boot đó.

Tra cứu bảng tương thích và hướng dẫn phát hành của Spring Cloud tại tài liệu chính thức. Chọn một release train được công bố tương thích với dòng Spring Boot của dự án, sau đó dùng phiên bản patch đang được tổ chức chấp thuận trong release train đó. Không suy ra phiên bản Cloud bằng cách dùng cùng số với Boot.

Một số nguyên tắc khi chọn:

- Giữ Spring Boot và Spring Cloud trong cặp phiên bản tương thích.
- Không nâng riêng một module Spring Cloud lên phiên bản khác với release train chỉ để xử lý một lỗi nếu chưa xác minh các dependency liên quan.
- Ưu tiên phiên bản đang được hỗ trợ và đã qua kiểm thử của dự án.
- Ghi phiên bản BOM ở một nơi duy nhất để việc nâng cấp và review dễ theo dõi.
- Khi nâng release train, kiểm tra cả thay đổi API, cấu hình và yêu cầu Java được nêu trong tài liệu phát hành.

Các chuỗi như BOOT_VERSION và SPRING_CLOUD_RELEASE_TRAIN_VERSION trong ví dụ bên dưới là chỗ giữ chỗ. Thay chúng bằng phiên bản cụ thể đã được kiểm tra tương thích trước khi build.

## 4. Import Spring Cloud BOM trong Maven

Với Maven, BOM được import trong phần dependencyManagement. Một dự án dùng Spring Boot parent có thể giữ parent đang sử dụng và thêm Spring Cloud BOM như sau:

    <properties>
        <java.version>YOUR_JAVA_VERSION</java.version>
        <spring-cloud.version>SPRING_CLOUD_RELEASE_TRAIN_VERSION</spring-cloud.version>
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

Các thành phần trong khai báo có ý nghĩa:

- groupId và artifactId xác định Spring Cloud BOM.
- version lấy từ property để chỉ phải sửa một vị trí khi nâng release train.
- type pom cho Maven biết đây là một POM.
- scope import yêu cầu Maven nhập các quy tắc dependency management từ BOM.

Tiếp theo, khai báo starter cần dùng trong dependencies. Ví dụ ứng dụng gọi dịch vụ theo kiểu đồng bộ:

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
        </dependency>
    </dependencies>

Không cần ghi version cho starter nếu phiên bản của nó được quản lý bởi BOM đã import. Maven sẽ lấy phiên bản được quản lý tương ứng.

Nếu ứng dụng dùng WebClient và Reactor, starter reactive có thể được khai báo thay cho starter đồng bộ:

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>

Chỉ thêm những starter mà ứng dụng thực sự cần. Một ứng dụng chỉ có lời gọi đồng bộ không cần thêm starter reactive chỉ để có thể sử dụng circuit breaker. Nếu một ứng dụng có cả hai kiểu lời gọi, hãy xác minh các dependency được resolve và cách cấu hình của từng kiểu.

Nếu dự án không dùng spring-boot-starter-parent, vẫn có thể import Spring Cloud BOM trong dependencyManagement. Khi đó, nhóm dự án cần quyết định cách quản lý dependency của Spring Boot, plugin build và các BOM khác. Tránh bỏ sót BOM nền tảng chỉ vì đã import BOM của Spring Cloud.

## 5. Import BOM trong Gradle

Gradle có thể nhập Maven BOM bằng plugin Spring dependency management hoặc bằng cơ chế platform tích hợp. Chọn một cách rõ ràng cho dự án để người đọc biết phiên bản đến từ đâu.

### Cách A: dùng plugin io.spring.dependency-management

Trong file build.gradle dùng Groovy DSL, khai báo plugin và phiên bản release train:

    plugins {
        id 'java'
        id 'org.springframework.boot' version 'BOOT_VERSION'
        id 'io.spring.dependency-management' version 'DEPENDENCY_MANAGEMENT_PLUGIN_VERSION'
    }

    ext {
        set('springCloudVersion', 'SPRING_CLOUD_RELEASE_TRAIN_VERSION')
    }

    dependencyManagement {
        imports {
            mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
        }
    }

    dependencies {
        implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
    }

Plugin dependency management đọc BOM và áp dụng phiên bản được quản lý cho dependency của Gradle. Starter được khai báo trong dependencies mà không cần ghi version.

Với Kotlin DSL trong file build.gradle.kts, cách khai báo tương đương là:

    plugins {
        java
        id("org.springframework.boot") version "BOOT_VERSION"
        id("io.spring.dependency-management") version "DEPENDENCY_MANAGEMENT_PLUGIN_VERSION"
    }

    extra["springCloudVersion"] = "SPRING_CLOUD_RELEASE_TRAIN_VERSION"

    dependencyManagement {
        imports {
            mavenBom(
                "org.springframework.cloud:spring-cloud-dependencies:${property("springCloudVersion")}"
            )
        }
    }

    dependencies {
        implementation("org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j")
    }

Cần thay các chuỗi giữ chỗ bằng phiên bản thật đã được xác minh. Phiên bản plugin dependency management cũng là phiên bản của plugin build, không phải phiên bản Spring Cloud release train.

### Cách B: dùng platform tích hợp của Gradle

Gradle hỗ trợ nhập BOM thông qua platform mà không cần plugin dependency management. Với Groovy DSL:

    plugins {
        id 'java'
        id 'org.springframework.boot' version 'BOOT_VERSION'
    }

    ext {
        springCloudVersion = 'SPRING_CLOUD_RELEASE_TRAIN_VERSION'
    }

    dependencies {
        implementation platform(
            "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
        )

        implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
    }

Với Kotlin DSL:

    plugins {
        java
        id("org.springframework.boot") version "BOOT_VERSION"
    }

    val springCloudVersion = "SPRING_CLOUD_RELEASE_TRAIN_VERSION"

    dependencies {
        implementation(
            platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
        )

        implementation("org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j")
    }

platform đưa các dependency constraints từ BOM vào cấu hình Gradle. Cách này phù hợp với dự án muốn dùng cơ chế quản lý dependency gốc của Gradle. Nếu cần bắt buộc mọi dependency phải tuân theo constraint của BOM, Gradle có enforcedPlatform, nhưng đây là lựa chọn mạnh hơn và có thể ghi đè lựa chọn phiên bản từ dependency khác. Chỉ dùng khi nhóm dự án hiểu rõ tác động.

Không cần nhập cùng một BOM bằng cả plugin dependency management lẫn platform trong cùng cấu hình nếu không có lý do cụ thể. Hai cơ chế cùng quản lý một nhóm dependency có thể khiến cấu hình khó hiểu khi xảy ra xung đột.

## 6. Quản lý starter đồng bộ và reactive

Spring Cloud CircuitBreaker có các starter khác nhau theo kiểu lập trình. Với Resilience4j, hai tọa độ thường gặp là:

| Kiểu lời gọi | Dependency | Trường hợp sử dụng |
| --- | --- | --- |
| Đồng bộ | spring-cloud-starter-circuitbreaker-resilience4j | Lời gọi chặn, ví dụ một gateway dùng RestClient hoặc HTTP client đồng bộ. |
| Reactive | spring-cloud-starter-circuitbreaker-reactor-resilience4j | Luồng bất đồng bộ dựa trên Reactor, ví dụ WebClient trả về Mono hoặc Flux. |

BOM cung cấp phiên bản phù hợp cho các dependency được quản lý. Ứng dụng vẫn phải chọn đúng starter theo mô hình giao tiếp. Việc import BOM không tự chuyển lời gọi đồng bộ thành reactive và cũng không thay thế cấu hình timeout, fallback, bulkhead hoặc sliding window.

Khi có nhiều module Maven hoặc Gradle trong cùng repository, nên quản lý release train tại cấp build chung nếu cấu trúc dự án cho phép. Các module con dùng chung một phiên bản Spring Cloud sẽ giảm nguy cơ mỗi module tự chọn một bộ dependency khác nhau. Với dự án có nhiều ứng dụng độc lập, từng ứng dụng có thể có BOM riêng, nhưng phải ghi nhận rõ phiên bản tương thích của từng ứng dụng.

## 7. Hiểu thứ tự ưu tiên và tránh ghi đè phiên bản

Import BOM không có nghĩa mọi phiên bản trong dự án đều bị khóa cứng. Một khai báo dependency trực tiếp có version cụ thể thường thể hiện ý định chọn phiên bản riêng và có thể ghi đè phiên bản được quản lý. Điều này đôi khi cần thiết để xử lý một vấn đề đã được xác minh, nhưng nếu làm tùy tiện sẽ phá vỡ tính đồng bộ mà BOM cung cấp.

Ví dụ, cách khai báo sau làm mất lợi ích quản lý tập trung cho starter:

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
        <version>ANOTHER_VERSION</version>
    </dependency>

Khi BOM đã quản lý dependency này, hãy bỏ thẻ version trừ khi có quyết định nâng hoặc hạ phiên bản riêng được kiểm soát. Nếu buộc phải override, ghi lại lý do, phạm vi ảnh hưởng và kế hoạch quay lại phiên bản được quản lý.

Các tình huống thường gặp:

- **BOM chưa được import:** dependency không có version và Maven báo thiếu version, hoặc Gradle không tìm được constraint mong muốn. Kiểm tra dependencyManagement hoặc platform.
- **Chọn release train không tương thích:** ứng dụng có thể gặp lỗi tương thích Spring Boot/Spring Framework. Kiểm tra lại bảng tương thích thay vì thử nâng từng thư viện ngẫu nhiên.
- **Có version ghi trực tiếp:** phiên bản resolved khác với BOM. Tìm khai báo version trong module hoặc convention plugin.
- **Nhiều BOM quản lý cùng dependency:** quy tắc ưu tiên của Maven hoặc Gradle có thể làm kết quả khác dự kiến. Kiểm tra effective POM hoặc dependency insight.
- **Plugin build không tương thích:** lỗi có thể xuất hiện trước khi ứng dụng biên dịch. Phân biệt phiên bản plugin Maven/Gradle với phiên bản thư viện chạy trong ứng dụng.

BOM của Spring Cloud và BOM của Spring Boot có phạm vi quản lý khác nhau. Một dự án có thể dùng cả hai thông qua parent hoặc dependency management. Khi nhập nhiều BOM, hãy đọc kết quả cuối cùng của công cụ build; đừng mặc định rằng BOM khai báo sau luôn thay thế tất cả quy tắc của BOM khai báo trước trong mọi tình huống.

## 8. Kiểm tra dependency sau khi cấu hình

Sau khi import BOM và khai báo starter, hãy kiểm tra phiên bản thực tế mà công cụ build chọn. Mục tiêu là xác nhận starter CircuitBreaker và các dependency liên quan được resolve đúng, không có một khai báo riêng vô tình kéo phiên bản khác vào.

Với Maven, có thể xem dependency tree:

    ./mvnw dependency:tree -Dincludes=org.springframework.cloud,io.github.resilience4j

Nếu dự án không có Maven Wrapper, dùng lệnh mvn tương ứng. Để kiểm tra POM sau khi các parent và BOM được kết hợp, có thể tạo effective POM:

    ./mvnw help:effective-pom

Tìm dependency spring-cloud-starter-circuitbreaker-resilience4j trong kết quả và xác nhận version được quản lý như mong đợi. Nếu có nhiều phiên bản của cùng một thư viện bắc cầu, kiểm tra đường dẫn dependency dẫn đến từng phiên bản.

Với Gradle, xem dependency của runtimeClasspath:

    ./gradlew dependencies --configuration runtimeClasspath

Có thể kiểm tra riêng một dependency bằng dependencyInsight:

    ./gradlew dependencyInsight --dependency spring-cloud-starter-circuitbreaker-resilience4j --configuration runtimeClasspath

Các lệnh trên chỉ là thao tác kiểm tra trong quy trình phát triển. Chúng không thay thế việc chạy ứng dụng và kiểm tra cấu hình CircuitBreaker thực tế. Sau khi phiên bản đã đúng, cần tiếp tục kiểm tra ứng dụng khởi động, bean được tạo, lời gọi được bảo vệ và các trạng thái breaker được quan sát đúng trong môi trường thử nghiệm.

## 9. Quy trình nâng cấp Spring Cloud release train

Khi cần nâng Spring Cloud, thực hiện theo trình tự có thể review:

1. Ghi nhận phiên bản Spring Boot, Java và release train hiện tại.
2. Tra cứu release train tương thích với phiên bản Spring Boot mục tiêu.
3. Chọn patch release được chấp thuận và cập nhật property hoặc biến BOM ở một vị trí.
4. Kiểm tra các module dùng chung BOM và dependency có version override.
5. Xem dependency tree hoặc dependency insight để phát hiện thay đổi phiên bản bắc cầu.
6. Đọc ghi chú phát hành cho thay đổi tương thích, API hoặc cấu hình.
7. Chạy build và kiểm thử tích hợp lời gọi đến dịch vụ phụ thuộc.
8. Thử tình huống dịch vụ lỗi, chậm, phục hồi để xác nhận circuit breaker vẫn hoạt động như mong đợi.

Không nâng đồng thời Spring Boot, Spring Cloud, Resilience4j và các plugin build nếu chưa có kế hoạch kiểm tra rõ ràng. Khi nhiều lớp thay đổi cùng lúc, việc xác định nguyên nhân của lỗi trở nên khó hơn. Nếu cần nâng nhiều thành phần, chia thành các thay đổi có thể đánh giá và kiểm thử riêng.

## 10. Bài thực hành: cấu hình BOM cho ứng dụng CircuitBreaker

Giả sử order-service dùng Maven và cần bảo vệ lời gọi đồng bộ đến inventory-service. Thực hiện các bước sau:

1. Xác định phiên bản Spring Boot và Java mà dự án đang dùng.
2. Tra cứu release train Spring Cloud tương thích.
3. Thêm property spring-cloud.version và import spring-cloud-dependencies trong dependencyManagement.
4. Thêm spring-cloud-starter-circuitbreaker-resilience4j vào dependencies, không ghi version riêng.
5. Xem dependency tree và xác nhận phiên bản starter được quản lý.
6. Nếu ứng dụng dùng WebClient, thử cấu hình starter reactive trong một nhánh hoặc module thử nghiệm và xác nhận dependency tree.
7. Khởi động ứng dụng trong môi trường thử nghiệm và kiểm tra tích hợp trước khi đưa thay đổi vào nhánh phát hành.

Với dự án Gradle, lặp lại bài thực hành bằng plugin dependency management hoặc platform. Ghi rõ cơ chế nào đang được dùng trong file build và không nhập BOM trùng lặp. So sánh kết quả dependency insight trước và sau khi thay đổi để thấy BOM ảnh hưởng đến các phiên bản được chọn như thế nào.

Kết quả mong đợi là nhóm phát triển có thể nâng phiên bản Spring Cloud tại một điểm cấu hình, giữ các starter trong cùng release train và giải thích được vì sao một dependency đang dùng phiên bản cụ thể. Khi nền tảng dependency ổn định, việc tiếp tục cấu hình Resilience4j, fallback, timeout, bulkhead, lời gọi reactive và metric sẽ dễ kiểm soát hơn.

