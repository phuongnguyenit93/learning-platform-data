# Đối chiếu tài liệu, cấu hình và mặc định của phiên bản đích

Nâng cấp Spring Cloud cùng Spring Boot là bài toán tương thích của cả hệ sinh thái. Chỉ đổi số phiên bản trong file build chưa đủ: release train Spring Cloud phải hỗ trợ thế hệ Spring Boot đích, các module Cloud phải thuộc cùng train, thư viện nền và JDK phải đáp ứng yêu cầu mới, còn property, auto-configuration và hành vi runtime cần được đối chiếu với tài liệu của chính phiên bản đích.

Trong module `SPRING_CLOUD_CORE`, bài học tập trung vào Spring Cloud Commons, Spring Cloud Context, external configuration, discovery, service registry và refresh. Các thành phần này được nhiều starter và provider sử dụng, nên một thay đổi ở Spring Boot hoặc Spring Framework có thể ảnh hưởng đồng thời tới nhiều integration.

Mục tiêu là xây dựng quy trình có bằng chứng: xác định phiên bản nguồn và đích, chọn release train tương thích, khóa dependency bằng BOM, đọc migration guide và release notes, so sánh property/default, kiểm tra API và auto-configuration, sau đó xác nhận bằng build, test và rollout có kiểm soát. Các con số phiên bản trong bài là ví dụ tại thời điểm biên soạn; luôn kiểm tra lại ma trận và release notes mới nhất trước khi nâng cấp dự án thực tế.

## 1. Vì sao phải đối chiếu phiên bản đích?

Spring Boot quản lý một tập dependency đã được kiểm thử cùng nhau. Spring Cloud bổ sung các project cho cấu hình phân tán, service discovery, routing, load balancing, circuit breaker và các pattern khác. Mỗi release train Cloud được phát hành để tương thích với một hoặc một số thế hệ Boot nhất định.

Nếu chọn sai tổ hợp, lỗi có thể xuất hiện ở nhiều thời điểm:

- Build không resolve được dependency hoặc plugin.
- Ứng dụng khởi động thất bại do compatibility verifier.
- Lỗi liên kết binary như `NoSuchMethodError` hoặc `NoClassDefFoundError`.
- Auto-configuration không còn match vì classpath hoặc condition thay đổi.
- Property cũ bị bỏ qua, đổi tên hoặc có default mới.
- Discovery, registration, refresh hoặc HTTP client hoạt động khác trước.
- Integration test qua nhưng lỗi chỉ xuất hiện khi chạy trên JDK, servlet container hoặc nền tảng triển khai thật.

Một bản nâng cấp tốt phải trả lời được bốn câu hỏi:

1. Phiên bản đích có nằm trong tổ hợp được Spring hỗ trợ không?
2. Dependency graph thực tế có nhất quán với BOM và yêu cầu runtime không?
3. Cấu hình và mặc định nào thay đổi, và ứng dụng đã chủ động xác nhận chúng chưa?
4. Hành vi quan trọng của ứng dụng đã được kiểm thử trên đúng classpath đích chưa?

## 2. Thứ tự ưu tiên của tài liệu tham khảo

Không dùng một trang tổng quan duy nhất để quyết định toàn bộ migration. Mỗi nguồn trả lời một phần khác nhau:

| Nguồn | Cần đọc để biết | Cách sử dụng |
| --- | --- | --- |
| Spring Cloud project compatibility matrix | Release train nào hỗ trợ thế hệ Boot nào | Chọn train trước khi sửa dependency |
| Spring Cloud Supported Versions | Train/project còn được hỗ trợ hay đã EOL | Tránh nâng cấp sang một train đã hết hỗ trợ |
| Release notes của Spring Cloud train đích | Thay đổi theo train và từng service release | Đọc từ phiên bản nguồn tới phiên bản đích |
| Migration guide của Spring Boot đích | Thay đổi nền tảng, API, property và dependency | Đọc theo từng major/feature release đã đi qua |
| Spring Boot release notes | Default, behavior và bug fix của từng bản | Xác định tác động của patch/minor release |
| Tài liệu riêng từng Spring Cloud project | Cấu hình và behavior của Config, Commons, Netflix, Gateway, Kubernetes... | Kiểm tra đúng module đang dùng |
| API Javadoc và configuration metadata | Signature, deprecation, property name/type/default | Xác minh chi tiết implementation |
| Dependency report của build | Phiên bản thực sự được resolve | Phát hiện dependency bị override hoặc kéo lệch |
| Test và log runtime | Behavior thực tế trong ứng dụng | Xác nhận tài liệu phù hợp với cấu hình đang chạy |

Khi nâng cấp qua nhiều thế hệ, đọc hướng dẫn của các phiên bản trung gian. Ví dụ đi từ Boot 3.2 lên Boot 4.1 cần xem các thay đổi liên quan ở các feature/major release đã đi qua, không chỉ đọc tài liệu của Boot 4.1.

Spring Boot đặt hướng dẫn nâng cấp ở đầu release notes và yêu cầu đọc cả các phiên bản đã bỏ qua. Spring Cloud cũng khuyến nghị chọn release train theo Boot rồi dùng service release mới nhất của train đó. Hai nguyên tắc này giúp tránh bỏ sót thay đổi tích lũy.

## 3. Chọn Spring Cloud release train tương thích với Spring Boot

### 3.1. Phân biệt version của Boot và release train Cloud

Spring Boot và Spring Cloud có cách đánh số riêng:

- Spring Boot dùng các dòng như 3.5.x, 4.0.x hoặc 4.1.x.
- Spring Cloud dùng release train như 2025.0.x hoặc 2025.1.x, kèm codename.
- Mỗi release train quản lý version của nhiều project Cloud như Commons, Config, Netflix, Gateway và Circuit Breaker.

Không suy ra hai version tương thích chỉ vì số năm hoặc số major gần nhau. Tra ma trận chính thức để xác định quan hệ.

### 3.2. Ví dụ ma trận tương thích

Bảng sau là ảnh chụp ma trận được công bố khi biên soạn bài học. Đây là ví dụ cách đọc bảng, không phải danh sách cố định cho các lần nâng cấp trong tương lai.

| Spring Cloud release train | Spring Boot tương thích được công bố | Ghi chú |
| --- | --- | --- |
| 2025.1.x (Oakwood) | 4.0.x; 4.1.x từ 2025.1.2 | Dòng mới trong ma trận tại thời điểm tra cứu |
| 2025.0.x (Northfields) | 3.5.x | Được đánh dấu EOL trên ma trận tại thời điểm tra cứu |
| 2024.0.x (Moorgate) | 3.4.x | Được đánh dấu EOL trên ma trận tại thời điểm tra cứu |
| 2023.0.x (Leyton) | 3.2.x; 3.3.x từ 2023.0.2 | Được đánh dấu EOL trên ma trận tại thời điểm tra cứu |
| 2022.0.x (Kilburn) | 3.0.x; 3.1.x từ 2022.0.3 | Được đánh dấu EOL trên ma trận tại thời điểm tra cứu |

Không phải mọi patch của Boot đều được hỗ trợ từ patch đầu tiên của Cloud train. Ví dụ ma trận có thể ghi một train hỗ trợ Boot 4.1.x bắt đầu từ một service release cụ thể. Hãy đối chiếu đúng patch train tối thiểu, sau đó chọn service release mới nhất còn được hỗ trợ.

Nếu project cần commercial support hoặc đang vận hành một train EOL, kiểm tra chính sách hỗ trợ hiện hành của tổ chức và nhà cung cấp. “Build được” không có nghĩa là còn nhận bản vá bảo mật.

### 3.3. Kiểm tra trạng thái hỗ trợ của từng project

Release train là tập hợp nhiều project. Thời gian hỗ trợ của các project trong train có thể khác nhau; không nên coi codename của train là một bảo đảm hỗ trợ vô thời hạn.

Kiểm tra:

- Spring Boot version đang dùng còn được hỗ trợ không.
- Spring Cloud release train có còn trong cửa sổ OSS support không.
- Từng project Cloud mà ứng dụng sử dụng có version được hỗ trợ không.
- Provider ngoài như Eureka, Consul, Kubernetes client hoặc thư viện tracing có chính sách vòng đời riêng không.

### 3.4. Không ghép module Cloud từ nhiều train

Không khai báo thủ công Commons từ một train, Config từ train khác và Netflix từ train thứ ba chỉ để giải quyết một lỗi compile. Những module này có thể chia sẻ contract, auto-configuration và API nội bộ. Dùng release train BOM để quản lý chúng như một tập hợp tương thích.

## 4. Khóa dependency bằng BOM

BOM (Bill of Materials) định nghĩa tập version được quản lý cho các dependency. Spring Boot cung cấp `spring-boot-dependencies`; Spring Cloud cung cấp `spring-cloud-dependencies` cho release train.

### 4.1. Maven với Spring Boot parent và Spring Cloud BOM

Ví dụ minh họa cho một tổ hợp tương thích được công bố tại thời điểm biên soạn:

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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

Các dependency được quản lý bởi BOM không cần khai báo version riêng. Khi đổi release train, cập nhật version property và xem lại dependency graph đã resolve.

Nếu project không dùng Spring Boot parent, vẫn có thể import Boot BOM và Cloud BOM trong `dependencyManagement`. Hãy kiểm tra quy tắc precedence của Maven khi nhiều BOM cùng quản lý một artifact; tránh thêm version trực tiếp vào dependency chỉ để che một xung đột chưa được hiểu rõ.

### 4.2. Gradle với dependency management plugin

Một cách cấu hình phổ biến:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2025.1.4"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
}
```

Khi dùng dependency management plugin, Spring Boot plugin tích hợp quản lý dependency từ Boot BOM. Cloud BOM bổ sung version cho các module Cloud.

### 4.3. Gradle native platform BOM

Gradle cũng có thể dùng native BOM support:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    implementation platform('org.springframework.cloud:spring-cloud-dependencies:2025.1.4')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
}
```

Chọn một cách quản lý rõ ràng theo cấu trúc build. Tránh import cùng BOM theo nhiều cơ chế hoặc thêm version constraint chồng chéo mà không có chủ đích.

### 4.4. Không override version nền tùy tiện

Spring Boot kiểm thử một tập dependency cụ thể. Override Spring Framework, Jackson, Reactor, Netty, Micrometer hoặc thư viện logging có thể làm lệch tổ hợp đã được kiểm thử.

Chỉ override khi:

- Có yêu cầu bảo mật hoặc bug fix cụ thể.
- Version thay thế tương thích với Boot/Cloud đang dùng.
- Có lý do và owner chịu trách nhiệm.
- Có test chứng minh behavior.
- Có kế hoạch bỏ override khi BOM đã tích hợp version phù hợp.

## 5. Kiểm tra dependency graph thực tế

File build chỉ thể hiện yêu cầu. Dependency resolver mới cho biết version thực sự nằm trên runtime classpath.

### 5.1. Maven

Xem cây dependency:

```bash
mvn dependency:tree
```

Xem effective POM:

```bash
mvn help:effective-pom
```

Tìm các artifact nền:

```bash
mvn dependency:tree -Dincludes=org.springframework,org.springframework.cloud,io.projectreactor,io.micrometer,com.fasterxml.jackson
```

Kiểm tra version của Commons, Context, Config, Netflix và các starter khác có thuộc cùng release train hay không. Đồng thời tìm dependency version bị khai báo trực tiếp trong module con hoặc parent nội bộ.

### 5.2. Gradle

Xem dependency report:

```bash
./gradlew dependencies
```

Xem lý do một version được chọn:

```bash
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-framework --configuration runtimeClasspath
```

Thực hiện tương tự cho Config, Netflix, Gateway, Reactor, Micrometer và provider đang dùng. Một dependency có thể xuất hiện qua nhiều đường transitively; cần biết rule nào khiến Gradle chọn version cuối.

### 5.3. Dấu hiệu dependency graph có vấn đề

- Cùng một họ Spring Framework có nhiều version không mong muốn.
- Spring Cloud Commons khác train với Spring Cloud Config.
- Một starter bị override bởi version khai báo ở module con.
- Dependency cũ còn kéo `javax.*` trong khi ứng dụng chuyển sang Jakarta namespace.
- Thư viện provider kéo một version Netty/Reactor không phù hợp.
- Build file nhìn đúng nhưng runtime classpath trong container khác do packaging hoặc dependency scope.

Không chỉ xem compile classpath. Kiểm tra `runtimeClasspath`, executable jar hoặc container image vì lỗi thường xảy ra khi ứng dụng chạy.

## 6. Đối chiếu yêu cầu nền tảng: JDK, Spring Framework và Jakarta

Một release train tương thích không tự bảo đảm mọi dependency ngoài Spring đều tương thích. Đọc migration guide của Boot đích để kiểm tra baseline nền tảng.

Ví dụ Spring Boot 4.0 yêu cầu Java 17 trở lên, Kotlin 2.2 trở lên nếu dùng Kotlin, Spring Framework 7.x nếu quản lý dependency trực tiếp, Jakarta EE 11 và Servlet 6.1 baseline. Nếu dùng native image, migration guide cũng quy định baseline GraalVM tương ứng. Đây là yêu cầu của Boot 4.0; không suy rộng chúng sang mọi Boot feature release.

Đối chiếu thêm:

| Hạng mục | Cần xác nhận |
| --- | --- |
| JDK | Toolchain, compiler release, runtime image và CI dùng cùng baseline |
| Kotlin | Kotlin plugin, stdlib và compiler tương thích với Boot/Kotlin target |
| Servlet API | Container và dependency dùng đúng Jakarta Servlet generation |
| Spring Framework | Các module Framework thuộc version do Boot BOM quản lý |
| Servlet container | Tomcat/Jetty/Undertow version được Boot quản lý và tương thích |
| Reactive stack | Reactor Netty/Reactor Core và client tương thích |
| Jakarta namespace | Không còn dependency hoặc import `javax.*` thuộc API đã chuyển sang `jakarta.*` |
| Native image | GraalVM, AOT processing và Spring Cloud project hỗ trợ native image |
| Build plugins | Maven/Gradle, compiler, Surefire/Failsafe, Kotlin plugin và Docker image |

### 6.1. Kiểm tra javax sang jakarta

Một thay đổi nền tảng lớn có thể chuyển API từ namespace `javax.*` sang `jakarta.*`. Không phải mọi package `javax` đều được chuyển; ví dụ một số API Java SE vẫn giữ namespace đó. Hãy phân biệt Jakarta EE API với các package Java SE như `javax.crypto` hoặc `javax.sql`.

Tìm các import và dependency servlet/JPA/validation cũ, sau đó cập nhật theo API mà Boot đích yêu cầu. Kiểm tra thư viện bên thứ ba có bản Jakarta tương thích hay không trước khi nâng cấp.

## 7. Đọc release notes theo từng Spring Cloud project

Spring Cloud Core liên quan nhiều module. Đọc release notes theo đúng starter đang có trong dependency graph:

| Project | Những điểm cần rà soát |
| --- | --- |
| Spring Cloud Commons | DiscoveryClient, ServiceRegistry, load balancer abstraction, compatibility verifier, common properties |
| Spring Cloud Context | Bootstrap context, refresh scope, environment change, lifecycle events |
| Spring Cloud Config | Config Data import, bootstrap mode, retry, override precedence, encryption |
| Spring Cloud Netflix | Eureka client/server, health propagation, registration lifecycle |
| Spring Cloud Consul | Discovery, health checks, config integration và watch |
| Spring Cloud Kubernetes | Discovery, ConfigMap/Secret property source, client library và service routing |
| Spring Cloud LoadBalancer | Service instance supplier, caching, health checks, retry và default algorithm |
| Spring Cloud CircuitBreaker | Adapter, factory, fallback, time limiter và implementation version |
| Spring Cloud OpenFeign | Client configuration, contract, HTTP client và circuit breaker integration |

Không đọc mọi release note rồi cập nhật những module không dùng. Lọc theo runtime classpath và feature thực tế của ứng dụng.

## 8. So sánh cấu hình và property của phiên bản nguồn/đích

### 8.1. Property name có thể đổi hoặc bị xóa

Một property có thể giữ nguyên tên và default, đổi tên, bị deprecated, bị xóa, thay kiểu dữ liệu/format, thay default hoặc chỉ có hiệu lực khi một starter/classpath condition tồn tại.

Đừng chỉ tìm property trong file YAML. Property có thể đến từ environment variable, command line, Config Server, secret source, `@PropertySource` hoặc một `PropertySource` tự tạo.

### 8.2. Dùng configuration metadata

Các Spring Boot/Spring Cloud project có thể phát hành metadata mô tả tên property, kiểu dữ liệu, default, description, deprecation metadata và replacement suggestion.

Tìm `spring-configuration-metadata.json` trong jar hoặc dùng IDE hỗ trợ metadata. So sánh metadata của version nguồn và đích để phát hiện key bị đổi hoặc mất.

Metadata là trợ giúp cho cấu hình, không thay thế tài liệu behavior. Default trong metadata có thể không mô tả đầy đủ giá trị runtime khi property phụ thuộc condition hoặc bean khác.

### 8.3. So sánh default một cách có hệ thống

Lập bảng riêng cho các property quan trọng:

| Property | Nguồn: giá trị thực | Đích: default được công bố | Giá trị ứng dụng chọn | Bằng chứng kiểm tra |
| --- | --- | --- | --- | --- |
| Config import/fail-fast | Ghi lại mode hiện tại | Đọc tài liệu Config Client đích | Required/optional theo nghiệp vụ | Startup test khi Config Server down |
| Discovery enabled | Ghi lại property và classpath | Kiểm tra Commons/provider docs | Bật/tắt theo service | Context test và registry test |
| Service auto-registration | Ghi lại registration lifecycle | Đọc default và event docs | Tự động/thủ công | Test registration và shutdown |
| Load balancer cache | Ghi lại TTL/implementation | Kiểm tra default của train đích | Chọn theo freshness và tải | Test cập nhật instance |
| Refresh behavior | Ghi lại scope/event hiện tại | Kiểm tra Context/Config docs | Chọn bean refresh được | Test cập nhật property |
| Actuator exposure | Ghi lại endpoint đang mở | Kiểm tra Boot endpoint defaults | Allowlist tối thiểu | Security integration test |

Không điền giá trị suy đoán. Nếu tài liệu không công bố default hoặc default phụ thuộc môi trường, ghi “conditional/không cố định” và kiểm tra runtime.

### 8.4. Giá trị được bind khác giá trị default

Giá trị hiệu lực có thể đến từ nhiều property source. Để xác định nguồn, dùng endpoint `env` hoặc `configprops` trong môi trường test/quản trị được bảo vệ, log configuration binding phù hợp hoặc kiểm tra `Environment` trong test.

Không dump toàn bộ property ra log production vì có thể chứa credential, token hoặc private endpoint. Ghi key và source cần thiết, mask giá trị nhạy cảm.

## 9. Dùng spring-boot-properties-migrator đúng cách

Spring Boot cung cấp `spring-boot-properties-migrator` để chẩn đoán một số property đã đổi tên hoặc bị loại bỏ khi nâng cấp feature release.

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
```

Gradle:

```groovy
runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
```

Migrator có thể in diagnostic và tạm thời chuyển một số property cũ sang property mới trong runtime. Đây là công cụ chuyển tiếp để tìm việc cần sửa, không phải giải pháp migration cuối cùng.

Lưu ý:

- Chạy trong môi trường kiểm thử hoặc staging với log được kiểm soát.
- Đọc từng warning và sửa file cấu hình gốc.
- Kiểm tra cả Config Server và environment variables, không chỉ application.yml.
- Property được thêm muộn vào Environment, ví dụ qua một số `@PropertySource`, có thể không được migrator phát hiện.
- Sau khi migration hoàn tất, gỡ dependency migrator khỏi project.
- Công cụ này chủ yếu hỗ trợ property Spring Boot; không tự động xử lý mọi property của Spring Cloud hoặc provider bên thứ ba.

## 10. Kiểm tra compatibility verifier của Spring Cloud

Spring Cloud Commons có compatibility verifier để phát hiện một số tổ hợp Spring Boot không được release train hiện tại hỗ trợ. Cơ chế này có thể dừng startup và đưa ra báo cáo về version không tương thích.

Có thể bật rõ ràng trong môi trường kiểm thử:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

Property `spring.cloud.compatibility-verifier.compatible-boot-versions` có thể dùng để cấu hình danh sách Boot version được chấp nhận trong trường hợp có yêu cầu đặc biệt và đã được kiểm chứng.

Không tắt verifier chỉ để làm ứng dụng khởi động. Nếu verifier báo sai tổ hợp, trước hết kiểm tra Boot version, Cloud BOM và dependency graph. Chỉ thay danh sách compatible version khi tổ chức có bằng chứng tương thích, kiểm thử đầy đủ và chấp nhận trách nhiệm bảo trì tổ hợp đó.

Verifier là một hàng rào hữu ích nhưng không thay thế compatibility matrix. Nó không xác minh mọi provider, servlet container, JDK, cấu hình hoặc hành vi nghiệp vụ.

## 11. Đối chiếu auto-configuration và bean conditions

Một dependency upgrade có thể làm thay đổi classpath, condition hoặc bean mặc định.

Với mỗi integration quan trọng, kiểm tra:

- Auto-configuration class có còn tồn tại không.
- Condition theo classpath/property/bean có thay đổi không.
- Bean nào được tạo mặc định.
- `@ConditionalOnMissingBean` có chọn implementation khác không.
- Bean name, qualifier và primary candidate có thay đổi không.
- Provider-specific configuration có còn được import không.
- Customizer/interceptor/filter có được gắn vào client như trước không.

Dùng condition evaluation report hoặc Actuator `conditions` trong môi trường được bảo vệ. So sánh bean inventory ở môi trường nguồn và đích để tìm bean mất đi, bean mới hoặc implementation thay đổi.

Không xem một bean có mặt là bằng chứng integration hoạt động. Ví dụ `DiscoveryClient` bean có thể tồn tại nhưng registry không reachable; `LoadBalancerClient` bean có thể tồn tại nhưng service instance list rỗng.

## 12. Các khu vực Spring Cloud Core cần kiểm tra sâu

### 12.1. External configuration và Config Data

Kiểm tra:

- `spring.config.import` và Config Server location.
- `optional:`/required behavior và fail-fast.
- Active profile, application name và label.
- Discovery-first lookup nếu dùng.
- Retry, timeout và credentials.
- Property source precedence và override policy.
- Legacy bootstrap mode nếu ứng dụng vẫn dùng.
- Encryption/decryption và secret handling.
- Thời điểm property source được nạp so với bean creation.

Một cấu hình có thể parse thành công nhưng property source không được nạp như dự kiến. Test phải xác nhận giá trị cuối trong Environment và bean được bind.

### 12.2. Spring Cloud Context và refresh

Kiểm tra:

- `@RefreshScope` còn được áp dụng đúng bean không.
- Bean nào được refresh và bean nào giữ state.
- Environment change event có kích hoạt hành vi mong muốn không.
- Refresh endpoint/Bus có còn được expose và bảo vệ đúng không.
- Bean có resource lifecycle cần đóng/recreate không.
- Client connection pool, cache và scheduled task có phản ứng đúng sau refresh không.

Không giả định mọi property đều có thể đổi nóng. Một số cấu hình như listener port, server SSL, thread pool hoặc dependency graph cần restart/recreate ứng dụng thay vì refresh bean đơn lẻ.

### 12.3. DiscoveryClient và ServiceRegistry

Kiểm tra:

- Provider starter và API version.
- Auto-registration enabled/disabled.
- Instance ID, hostname, port, secure flag và metadata.
- Registration/deregistration events.
- Health propagation và heartbeat.
- Discovery cache/refresh interval.
- Client có xử lý empty instance list không.
- Registry outage ảnh hưởng startup hay chỉ discovery request.

### 12.4. Service calls và load balancing

Kiểm tra:

- `RestTemplate`, `WebClient`, Feign hoặc HTTP interface integration.
- Load-balanced annotation/customizer/interceptor.
- Service ID resolution.
- Retry và circuit breaker integration.
- Timeout, connection pool và TLS.
- Error mapping và fallback.
- Trace propagation và metrics.

Một request có thể vẫn compile nhưng không còn đi qua load balancer nếu custom client builder hoặc interceptor bị thay đổi.

### 12.5. Actuator và observability

Kiểm tra endpoint ID, exposure, access policy, health groups, metrics names, tags và registry exporter. Một default exposure thay đổi có thể ảnh hưởng monitoring hoặc bảo mật.

Không mở rộng endpoint exposure chỉ để làm dashboard hoạt động. Cập nhật scraper và security policy theo endpoint cần thiết.

## 13. So sánh mặc định và behavior bằng test

Tài liệu cho biết default được thiết kế; test cho biết ứng dụng đang nhận giá trị và behavior nào.

| Khu vực | Kiểm tra | Bằng chứng mong đợi |
| --- | --- | --- |
| Dependency | Resolve runtime graph | Các module cùng train và không có override ngoài ý muốn |
| Config binding | Khởi động context với cấu hình đại diện | Properties bind đúng, validation pass |
| Config Server | Test remote import và lỗi unavailable | Required/optional và retry đúng policy |
| Auto-configuration | Test conditions và bean inventory | Bean mong đợi có mặt, không có duplicate |
| Refresh | Thay đổi property rồi trigger refresh | Bean được refresh đúng và resource không rò rỉ |
| Discovery | Đăng ký, query instance, deregister | Metadata và lifecycle đúng |
| Load balancing | Gọi service ID với nhiều instance | Chọn instance và retry theo policy |
| Actuator | Gọi endpoint với role phù hợp | Exposure và authorization đúng |
| Web/runtime | Khởi động embedded server trên JDK đích | Port, TLS, servlet/reactive behavior đúng |
| Shutdown | SIGTERM/graceful close | Request drain và registry cleanup đúng |

### 13.1. Kiểm thử cấu hình có tính quyết định

Mỗi test nên khai báo rõ profile, property và mock dependency. Tránh phụ thuộc vào environment của máy phát triển hoặc Config Server production.

Với test property, xác nhận giá trị cuối bằng `Environment` hoặc `@ConfigurationProperties` bean. Với dynamic endpoint/container, dùng property supplier phù hợp và kiểm soát context cache.

### 13.2. Kiểm thử provider thật ở mức integration

Mock test xác nhận contract của code ứng dụng, nhưng không thay thế hoàn toàn integration test với Eureka, Consul, Config Server hoặc Kubernetes. Dùng container/test server phù hợp để xác minh protocol, metadata, health check và lifecycle của provider.

Không cần mọi test suite khởi động toàn bộ hạ tầng. Phân tầng unit, context, contract và integration để giữ feedback nhanh mà vẫn kiểm tra được các ranh giới quan trọng.

## 14. Quy trình nâng cấp theo từng bước

### Bước 1 — Chốt baseline nguồn

Ghi lại:

- Spring Boot version và Spring Cloud release train.
- JDK/toolchain và build plugin.
- Các Spring Cloud starter và provider đang dùng.
- Dependency graph runtime.
- Profile/property sources và cấu hình triển khai.
- Test suite, startup duration, health, registration và request metrics hiện tại.

Lưu kết quả build/test làm baseline để so sánh sau migration.

Nếu đích là Spring Boot 4.0, migration guide khuyến nghị đưa ứng dụng lên bản mới nhất của dòng 3.5.x trước khi bắt đầu bước nâng major. Việc này giúp baseline nguồn nhận các dependency patch mới nhất và làm rõ lỗi tồn tại trước khi chuyển major.

### Bước 2 — Chọn version đích

Tra compatibility matrix và support policy. Chọn release train hỗ trợ đúng Boot target, sau đó chọn service release mới nhất còn được hỗ trợ. Xác nhận JDK, Spring Framework, Jakarta, servlet/reactive container và provider requirements.

### Bước 3 — Đọc migration guide và release notes

Đọc theo thứ tự:

1. Spring Boot migration guide cho từng major/feature release đã đi qua.
2. Spring Boot release notes của các bản bị bỏ qua.
3. Spring Cloud release notes của train đích.
4. Release notes từng project Cloud đang dùng.
5. Migration guide của provider bên thứ ba.

Ghi lại các mục có ảnh hưởng thành issue/checklist, phân loại thành build, source code, property, default, behavior và deployment.

### Bước 4 — Cập nhật BOM và build plugin

Cập nhật Boot plugin/parent, Cloud BOM và JDK toolchain. Giữ version Cloud module theo BOM. Sau đó resolve dependency graph và sửa xung đột có nguyên nhân rõ ràng.

### Bước 5 — Sửa compile và API

Xử lý compile error, deprecated API, package Jakarta, generic/signature và client builder. Không thay đổi hàng loạt bằng search/replace nếu chưa hiểu semantic change.

### Bước 6 — Di trú cấu hình

So sánh property nguồn/đích. Dùng properties migrator khi phù hợp, cập nhật file local, environment, Config Server và deployment manifest. Kiểm tra default runtime và property precedence.

### Bước 7 — Kiểm thử theo feature

Chạy context test, integration test và contract test cho Config, refresh, discovery, registry, service calls, Actuator và security. Đối chiếu bean/condition report khi có khác biệt.

### Bước 8 — Kiểm tra runtime và hiệu năng

Đo startup time, heap, thread count, connection pool, latency, error rate, retry, discovery cache và metrics. Một bản nâng cấp compile được vẫn có thể đổi default timeout hoặc connection behavior.

### Bước 9 — Canary và rollout

Triển khai một nhóm nhỏ, kiểm tra registration, health, config version, request distribution và error rate. Chỉ tăng batch khi các chỉ số ổn định.

### Bước 10 — Gỡ công cụ migration và hoàn tất hồ sơ

Gỡ properties migrator, bỏ override tạm thời, cập nhật runbook và dependency inventory. Ghi rõ version nguồn/đích, release train, các property đã đổi, test evidence và cách rollback.

## 15. Rollback và quản lý cấu hình trong rollout

Nâng cấp framework thường thay đổi cả artifact và cấu hình. Rollback chỉ image cũ có thể chưa đủ nếu Config Server đã phát property mới mà code cũ không hiểu.

Trước rollout, chuẩn bị:

- Artifact/image nguồn còn có thể triển khai lại.
- Snapshot hoặc label cấu hình remote của phiên bản nguồn.
- Schema database tương thích ngược nếu migration schema đi kèm.
- Kế hoạch rollback registry metadata hoặc service registration nếu format thay đổi.
- Feature flag để bật/tắt hành vi mới khi phù hợp.
- Canary signal và ngưỡng dừng rollout.
- Người chịu trách nhiệm quyết định rollback.

Nếu thay đổi cấu hình không tương thích ngược, dùng versioned config label hoặc staged property migration: phát cấu hình mà cả code cũ và mới hiểu được, rollout code mới, rồi mới xóa key cũ sau khi toàn bộ fleet đã nâng cấp.

## 16. Các lỗi thường gặp khi đối chiếu phiên bản

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Compatibility verifier dừng startup | Boot version ngoài danh sách của Cloud train | Chọn train đúng hoặc kiểm chứng tổ hợp có chủ đích |
| `NoSuchMethodError` | Dependency graph có API binary không đồng bộ | Xem runtime dependency tree và BOM |
| `ClassNotFoundException`/`NoClassDefFoundError` | Module bị bỏ, đổi artifact hoặc thiếu dependency | Kiểm tra migration guide và runtime classpath |
| Property không còn tác dụng | Key đổi tên, bị xóa hoặc property source không nạp | Đối chiếu metadata, migrator và Environment |
| Bean auto-config không xuất hiện | Condition/classpath/default thay đổi | Xem condition report và dependency |
| Nhiều bean cùng interface | Auto-config mới tạo bean bổ sung hoặc custom config không còn match | Kiểm tra `@Primary`, `@Qualifier`, condition |
| Discovery không thấy instance | Provider/config/version hoặc metadata thay đổi | Kiểm tra registration và discovery response |
| Refresh không cập nhật bean | Scope/lifecycle hoặc property source thay đổi | Test refresh scope và resource recreation |
| HTTP client timeout/error tăng | Default timeout, pool, TLS hoặc retry thay đổi | So sánh client config và metrics |
| Actuator endpoint 404/401/403 | Exposure/access/security thay đổi | Kiểm tra endpoint ID, allowlist và security chain |
| Build local pass nhưng CI fail | JDK, plugin, cache hoặc repository khác | Khóa toolchain và kiểm tra dependency resolution trong CI |
| Rollback thất bại | Config/schema mới không tương thích code cũ | Dùng staged config/schema và giữ rollback path |

### 16.1. Phân biệt compile error và linkage error

Compile error thường cho thấy source không còn khớp API đích. Linkage error thường cho thấy code đã compile với một API nhưng runtime nạp class version khác.

Khi gặp linkage error, không chỉ thêm dependency tùy ý. Xác định class đến từ jar nào, dependency path nào chọn version đó và BOM nào đang quản lý artifact.

### 16.2. Không vô hiệu hóa verifier để che dependency drift

Tắt `spring.cloud.compatibility-verifier.enabled` có thể giúp bỏ qua một kiểm tra startup, nhưng không sửa incompatibility. Nếu cần tắt trong một môi trường đặc biệt, ghi lại lý do, khóa version graph và bổ sung test/monitoring chứng minh behavior.

## 17. Thực hành: nâng cấp một ứng dụng Catalog

Giả sử ứng dụng hiện dùng một Spring Boot 3.x và một Spring Cloud release train cũ. Ứng dụng có Config Client, Eureka, LoadBalancer và `@RefreshScope`. Mục tiêu là chuyển sang một tổ hợp Boot/Cloud mới được ma trận chính thức hỗ trợ.

### Bước 1 — Chụp baseline

- Lưu `mvn dependency:tree` hoặc Gradle dependency report.
- Ghi lại JDK và plugin version.
- Lưu các profile/property đang dùng.
- Chạy test Config import, refresh, registration và service call.
- Ghi startup time, health, registration status và request metrics.

### Bước 2 — Chọn train

Tra ma trận Spring Cloud, xác nhận Boot đích được hỗ trợ và train còn support. Chọn service release phù hợp với patch Boot cần dùng. Không chọn Cloud version bằng cách tăng số tùy ý.

### Bước 3 — Cập nhật BOM

Cập nhật Boot parent/plugin và Cloud BOM. Xóa version trực tiếp trên từng Spring Cloud starter nếu BOM đã quản lý. Resolve dependency graph và kiểm tra Commons, Context, Config, Netflix cùng thuộc train đích.

### Bước 4 — Đọc migration guide

Đánh dấu thay đổi JDK, Spring Framework, Jakarta, property và API. Kiểm tra những deprecation đã tồn tại từ bản nguồn vì chúng có thể bị loại bỏ ở major release đích.

### Bước 5 — So sánh cấu hình

Lập danh sách property từ `application.yml`, profile, environment và Config Server. Đối chiếu với configuration metadata của version đích. Chạy properties migrator nếu đây là migration Boot feature release phù hợp; sửa nguồn cấu hình và gỡ migrator sau đó.

### Bước 6 — Kiểm tra Context và refresh

Khởi động context với cấu hình đại diện. Xác nhận bean `@RefreshScope` có đúng scope, refresh event cập nhật property mong đợi và resource cũ được đóng đúng cách.

### Bước 7 — Kiểm tra discovery và service calls

Xác nhận Eureka registration có host/port/metadata đúng, DiscoveryClient trả instance, LoadBalancer chọn instance hợp lệ và caller giữ timeout/retry policy đã định.

### Bước 8 — Chạy test và canary

Chạy toàn bộ test phù hợp, build executable artifact, triển khai canary. So sánh startup, health, registration, latency, error rate và log trước khi rollout toàn bộ.

### Bước 9 — Hoàn tất migration

Gỡ dependency tạm, loại bỏ property cũ, cập nhật runbook và lưu hồ sơ version graph. Giữ snapshot cấu hình nguồn trong thời gian rollback window.

## 18. Checklist trước khi chấp nhận phiên bản đích

### Compatibility và support

- [ ] Boot target nằm trong ma trận tương thích của Cloud train.
- [ ] Release train và từng project quan trọng còn được hỗ trợ.
- [ ] Đã chọn service release phù hợp với patch Boot đích.
- [ ] JDK, Kotlin, Spring Framework, Jakarta và container đáp ứng yêu cầu.
- [ ] Provider bên thứ ba có version tương thích.

### Build và dependency

- [ ] Boot BOM/parent/plugin được cập nhật.
- [ ] Cloud BOM được import một lần theo cách quản lý dependency nhất quán.
- [ ] Không pin version riêng cho module Cloud nếu BOM đã quản lý.
- [ ] Dependency tree runtime không có version lệch ngoài chủ đích.
- [ ] Maven/Gradle và compiler plugin tương thích với JDK đích.

### Configuration và defaults

- [ ] Đã đọc migration guide và release notes của mọi phiên bản bị bỏ qua.
- [ ] Đã so sánh property name, type, default và deprecation.
- [ ] Đã kiểm tra Config Data/bootstrap, profile và precedence.
- [ ] Đã kiểm tra discovery/registration/refresh properties.
- [ ] Properties migrator đã được gỡ sau migration.
- [ ] Không log hoặc công khai secret khi kiểm tra cấu hình.

### Behavior và tests

- [ ] Compatibility verifier được bật/kiểm tra theo policy.
- [ ] Auto-configuration conditions và bean inventory đúng.
- [ ] Config Server và refresh behavior đã được test.
- [ ] Discovery, ServiceRegistry và load balancing đã được test.
- [ ] HTTP client timeout/retry/TLS đã được xác minh.
- [ ] Actuator exposure và authorization đúng.
- [ ] Startup, graceful shutdown và rollback đã được kiểm thử.

### Rollout

- [ ] Artifact nguồn và snapshot cấu hình nguồn sẵn sàng cho rollback.
- [ ] Canary có ngưỡng dừng rõ ràng.
- [ ] Monitoring dashboard so sánh version, error rate, latency và registration.
- [ ] Config/schema migration tương thích ngược trong thời gian rollout.
- [ ] Runbook và dependency inventory đã cập nhật.

### Câu hỏi tự kiểm tra

1. Vì sao phải chọn Spring Cloud release train dựa trên Spring Boot version?
2. BOM `spring-cloud-dependencies` quản lý điều gì?
3. Vì sao không nên ghép Commons và Config từ hai release train?
4. Compatibility matrix và compatibility verifier khác vai trò như thế nào?
5. Dependency tree runtime giúp phát hiện lỗi gì?
6. Vì sao version compile classpath có thể khác vấn đề runtime?
7. Spring Boot migration guide cần được đọc theo những version nào khi bỏ qua nhiều release?
8. `spring-boot-properties-migrator` hỗ trợ điều gì và cần gỡ khi nào?
9. Vì sao configuration metadata không thay thế runtime test?
10. Những behavior nào cần kiểm tra khi nâng cấp Spring Cloud Context?
11. Vì sao discovery registration thành công chưa đủ chứng minh service call hoạt động?
12. Rollback có thể thất bại thế nào nếu Config Server đã phát property mới?

**Gợi ý đáp án:** (1) Mỗi Cloud train chỉ hỗ trợ một tập Boot generation/patch nhất định; (2) Quản lý version của các project Spring Cloud thuộc train; (3) API và auto-configuration giữa module có thể không tương thích; (4) Matrix xác định tổ hợp được hỗ trợ, verifier là hàng rào kiểm tra một số điều kiện lúc startup; (5) Version transitively được chọn, dependency bị override và nhiều version cùng tồn tại; (6) Runtime có thể nạp jar khác với jar dùng khi compile; (7) Đọc migration guide/release notes của từng major/feature release đã đi qua; (8) Chẩn đoán và tạm di trú property Boot, gỡ sau khi sửa cấu hình gốc; (9) Metadata không mô tả hết condition và property source runtime; (10) Refresh scope, event, lifecycle, resource recreation và endpoint/security; (11) Caller còn phụ thuộc discovery visibility, cache, network, load balancer và health state; (12) Code cũ có thể không hiểu key mới hoặc default mới, nên cần staged/versioned config.

## 19. Những nguyên tắc cần nhớ

- Chọn Spring Cloud release train bằng compatibility matrix chính thức của Spring Boot đích.
- Kiểm tra support/EOL của train và từng project; ưu tiên service release còn được hỗ trợ.
- Dùng Spring Boot BOM và Spring Cloud release train BOM để quản lý dependency nhất quán.
- Không tự ghép module Cloud từ nhiều train hoặc override version nền khi chưa có bằng chứng.
- Đọc migration guide và release notes của mọi version đã bỏ qua.
- Đối chiếu JDK, Kotlin, Spring Framework, Jakarta, servlet/reactive container và provider bên thứ ba.
- So sánh property name, type, default, condition và deprecation; không giả định default cũ còn giữ nguyên.
- Dùng configuration metadata và properties migrator để hỗ trợ tìm thay đổi, sau đó sửa cấu hình gốc và gỡ công cụ tạm.
- Dùng compatibility verifier như một hàng rào, không coi nó là bằng chứng tương thích toàn diện.
- Kiểm tra auto-configuration, refresh, discovery, registration, load balancing, Actuator và security bằng test trên runtime classpath đích.
- Triển khai canary, theo dõi behavior và giữ cấu hình/artifact nguồn cho rollback.
- Ghi lại version graph và bằng chứng kiểm thử để lần nâng cấp sau có baseline rõ ràng.

Đối chiếu phiên bản đích là công việc kết hợp tài liệu, dependency graph và hành vi runtime. Khi release train, BOM, property và auto-configuration được xác minh theo cùng một phiên bản đích, việc nâng cấp Spring Cloud trở nên có thể kiểm soát, dễ review và có đường rollback rõ ràng.

## Tài liệu tham khảo

- [Spring Cloud — Project, Release Train Compatibility Matrix and BOM Setup](https://spring.io/projects/spring-cloud/)
- [Spring Cloud — Supported Versions and Support Policy](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)
- [Spring Boot — Upgrading Guide](https://docs.spring.io/spring-boot/upgrading.html)
- [Spring Boot — Dependency Management with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Cloud Commons — Compatibility Verification](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Boot — Deprecated Application Properties](https://docs.spring.io/spring-boot/appendix/deprecated-application-properties/)
