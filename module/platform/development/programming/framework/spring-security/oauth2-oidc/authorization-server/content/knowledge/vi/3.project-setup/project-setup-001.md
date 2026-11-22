# Chọn bộ phiên bản tương thích của Java, Spring Boot và Spring Security

> **Chương:** Khởi tạo dự án  
> **Phạm vi học:** Thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao phải chọn **Java, Spring Boot, Spring Framework, Spring Security và Authorization Server** như một bộ tương thích.
2. Phân biệt mô hình **Spring Authorization Server 1.x với Spring Security 6.x** và nhánh **Authorization Server được tích hợp vào Spring Security 7.x**.
3. Chọn bộ phiên bản phù hợp cho dự án mới hoặc dự án đang bảo trì, có tính đến vòng đời hỗ trợ và bản vá bảo mật.
4. Tận dụng cơ chế quản lý phiên bản phụ thuộc của Spring Boot thay vì tự ghép những phiên bản không tương thích.
5. Kiểm tra phiên bản Java và dependency thực sự được dùng khi build, test và chạy ứng dụng.

Bài học tập trung vào **quyết định phiên bản và cấu hình build**. Việc đăng ký client, tạo khóa ký, cấu hình filter chain và triển khai các endpoint OAuth 2.0/OIDC sẽ được xử lý ở các chủ đề tương ứng.

## 1. Vì sao Authorization Server nhạy cảm với phiên bản?

Authorization Server xử lý những thành phần bảo mật trọng yếu: xác thực người dùng và client, phát hành authorization code, access token, refresh token, ID token, kiểm tra redirect URI, thực thi PKCE, quản lý consent và khóa ký. Một thay đổi dependency có thể làm ảnh hưởng đến API cấu hình, bộ lọc bảo mật, endpoint hoặc hành vi mặc định.

Nhìn theo chiều phụ thuộc, ứng dụng thường có cấu trúc:

~~~mermaid
flowchart TB
    J["Java/JDK<br/>Nền tảng biên dịch và chạy"]
    FW["Spring Framework<br/>Web, DI, ApplicationContext"]
    B["Spring Boot<br/>Auto-configuration, starter, BOM"]
    S["Spring Security<br/>Authentication, filter chain, OAuth2"]
    A["OAuth2/OIDC Authorization Server<br/>Endpoint, token, registered client"]
    P["Ứng dụng Spring Boot của bạn"]

    J --> FW
    FW --> B
    B --> S
    S --> A
    A --> P
~~~

Sơ đồ diễn tả các **lớp trách nhiệm và khả năng tương thích**, không có nghĩa mã nguồn Maven/Gradle nhất thiết khai báo dependency đúng theo hình. Trong thực tế, Spring Boot quản lý một tập phiên bản qua dependency management và các starter kéo những thư viện cần thiết vào dự án.

Một bộ phiên bản phải đồng thời thỏa mãn:

- **JDK tương thích** với yêu cầu của nhánh Spring Boot và môi trường chạy.
- **Spring Boot cùng thế hệ với Spring Framework và Spring Security** được nó hỗ trợ.
- **Authorization Server cùng thế hệ với Spring Security**, vì nó dùng nhiều API bảo mật của Spring.
- **Thư viện bổ sung và plugin build** hoạt động với bộ phiên bản đó.
- **Nhánh còn được hỗ trợ theo chính sách của dự án** và có đường cập nhật bản vá bảo mật.

Chỉ thấy ứng dụng biên dịch thành công **chưa đủ** chứng minh hệ thống an toàn hoặc được hỗ trợ: một số lỗi chỉ xuất hiện khi khởi động, khi thực hiện token exchange hoặc lúc Resource Server xác minh token.

## 2. Hiểu cách các phiên bản liên hệ với nhau

| Thành phần | Vai trò trong bài toán | Quy tắc lựa chọn |
| --- | --- | --- |
| **Java / JDK** | Ngôn ngữ, bytecode, JVM, TLS và API nền tảng | Chọn bản JDK được nhánh Spring Boot hỗ trợ; đồng bộ build, CI, image container và production |
| **Spring Boot** | Starter, auto-configuration, dependency management, packaging | Chọn một bản release được duy trì và khóa chính xác bản patch trong build |
| **Spring Framework** | Dependency injection, web stack, lifecycle, HTTP | Thường để Spring Boot quản lý, không tự ép về một bản Framework khác |
| **Spring Security** | Filter chain, xác thực, phân quyền và các thành phần OAuth 2.0/OIDC | Ưu tiên phiên bản Spring Boot BOM quản lý |
| **Authorization Server** | OAuth 2.0/OIDC endpoints, cấp token, client/authorization/consent | Chọn API/thư viện theo **thế hệ Spring Security** đang dùng |
| **Maven/Gradle** | Resolve dependency, biên dịch, test, đóng gói | Chọn phiên bản công cụ tương thích với JDK và Spring Boot; dùng wrapper được commit vào dự án |

### 2.1. Java 17, Java 21 và Java 25 có ý nghĩa gì?

Java 17, 21 và 25 đều là các phiên bản **LTS** của Java. Nhưng “LTS” không đồng nghĩa với “được mọi phiên bản Spring Boot hỗ trợ ngay lập tức” hoặc “phù hợp với mọi thư viện”.

Đối với bài thực hành Authorization Server, **Java 21** là một mốc cấu hình dễ hiểu: đủ hiện đại, có hỗ trợ LTS và phù hợp với cả hai thế hệ Spring Boot 3.x/4.x khi dùng nhánh hỗ trợ Java 21. Nếu tổ chức bị ràng buộc ở Java 17, có thể lựa chọn nhánh Spring Boot hỗ trợ Java 17 và các thư viện tương ứng. Khi muốn dùng Java 25, cần kiểm tra rõ **release notes của chính phiên bản Spring Boot đã chọn**, Java toolchain, driver và image container.

Phân biệt ba giá trị thường bị lẫn:

1. **JDK chạy Maven/Gradle:** dùng để khởi chạy công cụ build và plugin.
2. **Java toolchain / compiler release:** quyết định JDK dùng để biên dịch và mức bytecode/API của ứng dụng.
3. **JRE/JDK production:** JVM thực sự chạy file JAR hoặc image container.

Ví dụ, ứng dụng biên dịch với `--release 21` không thể chạy trên JVM 17. Trong CI, chỉ thay `JAVA_HOME` mà không kiểm tra compiler toolchain có thể khiến máy build và container dùng hai nền tảng khác nhau.

### 2.2. Đừng suy luận tương thích chỉ từ số phiên bản

Ba sản phẩm Spring không luôn có cùng major:

- Spring Boot **3.x** chạy trên thế hệ Spring Framework **6.x**, Spring Security **6.x**.
- Spring Boot **4.x** là thế hệ Spring Framework **7.x**, Spring Security **7.x**.
- Với Spring Security **6.x**, Authorization Server được sử dụng theo nhánh **Spring Authorization Server 1.x**.
- Từ thế hệ Spring Security **7.x**, chức năng Authorization Server được tích hợp vào Spring Security; cần dùng tài liệu và cách khai báo dependency dành cho **thế hệ 7.x**.

Vì vậy, câu hỏi đúng không phải “tôi nên cài Spring Security mới nhất bao nhiêu?”, mà là “**Spring Boot đang quản lý Spring Security nào, và Authorization Server của tôi sử dụng API của thế hệ nào?**”.

## 3. Hai hướng lựa chọn chính cho Authorization Server

Bảng dưới đây là **bản đồ thế hệ** để định hướng, không phải danh sách bản patch mới nhất tại thời điểm triển khai. Hãy xác minh support policy và các phiên bản đang được Spring Boot BOM quản lý trước khi chốt release sản xuất.

| Ngữ cảnh | Java nên cân nhắc | Spring Boot | Spring Security | Thành phần Authorization Server | Ý nghĩa |
| --- | --- | --- | --- | --- | --- |
| Ứng dụng dựa trên API **Spring Authorization Server 1.x** | Java 21; hoặc Java 17 nếu đáp ứng yêu cầu | **3.5.x** | **6.5.x** | **Spring Authorization Server 1.5.x** | Bộ phiên bản đi cùng một thế hệ, thuận tiện khi học hoặc duy trì mã nguồn SAS 1.x |
| Ứng dụng dựa trên Spring Boot 3.4 | Java 17/21 phù hợp | **3.4.x** | **6.4.x** | **Spring Authorization Server 1.4.x** | Mốc tương thích để đọc và bảo trì dự án cũ; xác minh tình trạng hỗ trợ trước khi sử dụng |
| Ứng dụng mới chọn thế hệ Spring hiện đại | Java 21 là mốc khởi đầu hợp lý | **4.x** | **7.x** | **Authorization Server trong hệ Spring Security 7.x** | Chọn starter và API đúng tài liệu của nhánh Boot 4/Security 7, đánh giá migration nếu có code SAS 1.x |

**Điểm cần đọc chính xác:** các ô `x` diễn tả nhánh minor. Phiên bản **patch thực tế** do BOM/Gradle dependency resolution quyết định và cần được kiểm chứng bằng công cụ build. Các cặp nhánh trong bảng không là cam kết rằng mọi patch trong nhánh đều hỗ trợ mọi JDK tương lai hoặc vẫn còn support ở thời điểm bạn đọc bài.

### 3.1. Bộ ví dụ để học API Spring Authorization Server 1.x

Nếu mục đích là học cấu hình kiểu Spring Authorization Server 1.x (như `RegisteredClientRepository`, `OAuth2AuthorizationService` và các ví dụ Spring Security 6), một mốc học có thể chọn là:

~~~text
JDK                 = Java 21
Spring Boot         = 3.5.x
Spring Framework    = 6.2.x (do Spring Boot quản lý)
Spring Security     = 6.5.x (do Spring Boot quản lý)
Authorization Server= 1.5.x (do Spring Boot quản lý nếu dùng starter/BOM phù hợp)
Build tool          = Maven Wrapper hoặc Gradle Wrapper
~~~

**Không tự đặt** số patch cho Spring Security, Spring Framework và Spring Authorization Server chỉ để “khớp” những số trong bảng. Cần kiểm tra phiên bản chính xác được quản lý bởi bản Spring Boot cụ thể, và ưu tiên bản patch có sửa lỗi/bảo mật còn nằm trong chính sách hỗ trợ của tổ chức.

Đây là **mốc học và đối chiếu API**, không phải lời khuyên tự động dùng Spring Boot 3.5 cho mọi dự án production mới ở một thời điểm bất kỳ. Quyết định production còn phụ thuộc nhánh đã hết hay còn thời hạn hỗ trợ công khai/thương mại.

### 3.2. Bộ ví dụ cho dự án mới theo Spring Security 7

Với một dự án khởi tạo mới theo Spring Boot 4, nên bắt đầu từ **bản Spring Boot 4.x đang được duy trì**, giữ Spring Security và Spring Framework theo BOM của bản đó, rồi dùng starter/cấu hình Authorization Server **được tài liệu nhánh này chỉ rõ**.

~~~text
JDK                 = Java 21 (kiểm tra yêu cầu chính thức của release)
Spring Boot         = 4.x đang được hỗ trợ, khóa patch cụ thể
Spring Framework    = 7.x tương ứng (do Spring Boot quản lý)
Spring Security     = 7.x tương ứng (do Spring Boot quản lý)
Authorization Server= Thành phần/cấu hình theo Spring Security 7.x
Build tool          = Wrapper phù hợp với bản Boot/JDK
~~~

Tránh sao chép nguyên ví dụ dependency hoặc extension API của Spring Authorization Server 1.x sang Boot 4 mà chưa đọc migration guide. Những thay đổi major có thể ảnh hưởng tên starter, package, API cấu hình, mặc định bảo mật hoặc cách tích hợp auto-configuration.

### 3.3. Quy tắc chọn giữa hai hướng

~~~mermaid
flowchart TD
    A["Bắt đầu chọn bộ phiên bản"]
    B{"Đã có ứng dụng hoặc bài học dùng<br/>API Spring Authorization Server 1.x?"}
    C["Duy trì thế hệ Boot 3 / Security 6<br/>và dùng SAS 1.x tương ứng"]
    D["Ưu tiên khảo sát nhánh Spring Boot 4<br/>và Spring Security 7"]
    E{"Nhánh được chọn còn phù hợp<br/>với chính sách hỗ trợ?"}
    F["Chốt JDK và bản patch cụ thể<br/>từ release notes + BOM"]
    G["Lập kế hoạch nâng cấp/migration<br/>hoặc chọn release đang hỗ trợ"]

    A --> B
    B -->|"Có"| C
    B -->|"Không"| D
    C --> E
    D --> E
    E -->|"Có"| F
    E -->|"Không"| G
    G --> D
~~~

Với dự án nhiều dịch vụ, còn phải xét phiên bản thư viện tại **OAuth2 Client** và **Resource Server**. Chúng **không bắt buộc** cùng phiên bản Spring Boot với AS; điều bắt buộc là tương tác qua giao thức và metadata/token tương thích, có kiểm thử tích hợp theo chính sách bảo mật.

## 4. Spring Boot BOM giải quyết vấn đề gì?

BOM (Bill of Materials) là tập phiên bản dependency đã được quản lý nhằm tạo ra một bộ thư viện nhất quán. Spring Boot cung cấp dependency management để version của nhiều thành phần Spring và thư viện liên quan được xác định tập trung.

Trong dự án dùng Spring Boot parent (Maven) hoặc Spring Boot plugin/BOM (Gradle), ta thường khai báo dependency **không kèm version** để bộ quản lý dependency chọn bản phù hợp.

### 4.1. Ví dụ Maven với Spring Boot 3.5

Khởi tạo Maven project trên Spring Initializr và **chọn đúng bản patch Boot 3.5 được tổ chức cho phép**, Java 21. File `pom.xml` do Initializr sinh ra có Spring Boot parent, version đã khóa và cấu hình plugin. Phần sau minh họa **các đoạn cần có**:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>

<dependencies>
    <!-- Starter Authorization Server cho thế hệ Spring Boot 3 -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đoạn này **không phải POM hoàn chỉnh**: nó được thêm vào file đã được Spring Initializr tạo với `<parent>` và các phần khác. Khai báo không kèm version là có chủ ý: Spring Boot quản lý phiên bản phụ thuộc phù hợp.

Nếu chủ động dùng dependency `org.springframework.security:spring-security-oauth2-authorization-server` thay cho starter, hãy kiểm tra BOM và tài liệu của đúng thế hệ Spring Boot đang dùng. Không đưa thêm `spring-security-core` phiên bản “mới nhất” để cố gắng nâng riêng bảo mật.

### 4.2. Ví dụ Gradle Kotlin DSL với Spring Boot 3.5

Tạo dự án Gradle Kotlin DSL từ Spring Initializr, chọn Java 21 và Boot 3.5 phù hợp. Sau khi Initializr đã tạo `plugins { ... }` và cơ chế quản lý phụ thuộc, dùng cấu hình minh họa:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-oauth2-authorization-server")
    implementation("org.springframework.boot:spring-boot-starter-web")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Đây là **mảnh cấu hình** cho file `build.gradle.kts` đã có Spring Boot plugin và dependency management phù hợp. Không tự ý thêm `version("6.5.x")` cho Spring Security trong phần `dependencies`. Nếu dùng Gradle với nền tảng BOM theo cách riêng, cần chắc rằng Spring Boot BOM thực sự được import và dependency resolution không bị một `enforcedPlatform` hoặc constraint khác ghi đè.

### 4.3. Với Boot 4, giữ nguyên nguyên tắc nhưng dùng starter đúng thế hệ

Cơ chế **để Spring Boot quản lý các version tương ứng** vẫn giữ nguyên. Tuy nhiên, hãy lấy tên dependency/starter và cách cấu hình Authorization Server từ tài liệu chính thức của bản Boot 4/Security 7 đang dùng, vì chuyển major có thể thay đổi cả bộ starter và API tích hợp. **Không coi các ví dụ Maven/Gradle ở mục 4.1–4.2 là mẫu build Boot 4 có thể copy nguyên.**

## 5. Quy trình chọn và khóa bộ phiên bản có thể kiểm chứng

Đề xuất thực hiện theo sáu bước:

### Bước 1 — Chốt yêu cầu và ràng buộc

Ghi rõ:

- Ứng dụng mới hay nâng cấp từ hệ thống đang chạy?
- Có mã nguồn phụ thuộc API Spring Authorization Server 1.x hay không?
- Công ty hỗ trợ JDK nào ở development, CI, container và production?
- Nhánh Spring Boot dự kiến còn được bảo trì trong thời gian vận hành không?
- Hệ thống có dùng JDBC, Redis, Redis session, database migration, native image, servlet container hoặc thư viện OAuth2 tùy biến không?

Không nên chọn chỉ theo ngày phát hành: bản major mới có thể cần migration chưa được lên kế hoạch; ngược lại bản cũ có thể đã ngừng nhận bản vá miễn phí.

### Bước 2 — Chọn thế hệ Spring, rồi chọn Java

Chọn **Spring Boot 3 + Security 6 + SAS 1.x** khi cần khớp API của tài liệu/ứng dụng thuộc thế hệ đó và có chính sách duy trì thích hợp. Chọn **Spring Boot 4 + Security 7** cho hướng thế hệ mới khi dự án chấp nhận API và hướng cấu hình tương ứng. Sau đó chọn JDK đã được phiên bản cụ thể hỗ trợ; Java 21 là ví dụ dùng xuyên suốt bài này.

### Bước 3 — Chọn release và patch từ nguồn chính thức

Trước khi đóng băng build:

1. Tra release notes và system requirements của **Spring Boot** bản định chọn.
2. Kiểm tra release notes/API migration của **Spring Security** cùng thế hệ.
3. Với nhánh 1.x, kiểm tra tài liệu/release notes của **Spring Authorization Server**.
4. Xác minh bản patch đã được Spring Boot BOM quản lý, tình trạng support và advisories bảo mật.
5. Kiểm tra yêu cầu của thư viện bên thứ ba, plugin Maven/Gradle và hệ điều hành/container.

Nguồn tham khảo chính thức:

- <https://spring.io/projects/spring-boot>
- <https://docs.spring.io/spring-boot/>
- <https://spring.io/projects/spring-security>
- <https://docs.spring.io/spring-security/reference/>
- <https://spring.io/projects/spring-authorization-server>
- <https://docs.spring.io/spring-authorization-server/reference/>

Các đường dẫn dự án và tài liệu có thể thay đổi cấu trúc theo thế hệ; khi truy cập, luôn đối chiếu **version selector** với dự án của bạn.

### Bước 4 — Tạo project có version rõ ràng

Dùng <https://start.spring.io/> hoặc template nội bộ đã kiểm chứng. Chọn rõ Java, Spring Boot release, build tool và dependency tương ứng. Khóa version Spring Boot trong parent/plugin; commit `mvnw`, `mvnw.cmd` hoặc `gradlew`, `gradlew.bat` cùng các tệp wrapper cần thiết.

Không dùng nhãn động như `LATEST` hay `RELEASE` trong build được triển khai. Nếu nội dung hướng dẫn ghi `3.5.x`, khi tạo repository thực tế phải thay bằng **số patch cụ thể** mà tổ chức đã chọn.

### Bước 5 — Xác minh dependency được resolve

**Với Maven** (đúng thư mục chứa `pom.xml`):

~~~bash
./mvnw -version
./mvnw dependency:tree
./mvnw verify
~~~

Khi muốn tìm riêng dependency Spring Security:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

**Với Gradle** (đúng thư mục chứa `build.gradle.kts`):

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-oauth2-authorization-server --configuration runtimeClasspath
./gradlew test
~~~

Trên Windows PowerShell, có thể dùng `.\mvnw.cmd` hoặc `.\gradlew.bat` tương ứng.

Hãy đọc kết quả đã resolve, tập trung vào:

- `org.springframework.boot`: phiên bản Boot parent/plugin.
- `org.springframework.security`: các module Spring Security và Authorization Server thực tế.
- `org.springframework`: các module Spring Framework.
- Các dấu hiệu một dependency bị **ép nâng/hạ phiên bản** bởi override, constraint, dependency trực tiếp hoặc dependency management của một BOM khác.

Tên artifact và nhóm dependency trong ví dụ trên áp dụng cho thế hệ Spring Boot 3/SAS 1.x. Với Spring Security 7, tìm các artifact đúng theo dependency graph của thế hệ được sử dụng.

### Bước 6 — Chạy kiểm thử tích hợp theo giao thức

Chỉ khi build và dependency graph ổn định mới tiếp tục kiểm thử chức năng OAuth2/OIDC:

- Authorization endpoint nhận `client_id`, `redirect_uri`, `scope` hợp lệ; từ chối redirect URI không đăng ký.
- Token endpoint xử lý authorization code và PKCE (`code_verifier`); từ chối verifier sai hoặc code đã sử dụng.
- AS phát hành JWT có issuer/claim đúng thiết kế, công bố khóa xác minh phù hợp.
- OIDC discovery, ID token và các claim cần thiết hoạt động khi bật OIDC.
- Resource Server chấp nhận access token đúng issuer, audience, thời hạn, scope; từ chối token sai.
- Hành vi lưu client, authorization, consent, khóa ký và xoay khóa phù hợp với cấu hình môi trường.

Một project khởi động thành công nhưng sai grant type, sai claim, lỗi PKCE hoặc thay đổi cách áp dụng filter chain vẫn chưa thể gọi là bộ phiên bản đã được xác minh đầy đủ.

## 6. Ví dụ lựa chọn theo tình huống thực tế

### Tình huống A — Khóa học có mã ví dụ Spring Authorization Server 1.x

Nhóm học tập đang theo tài liệu viết cho Spring Boot 3.5, Spring Security 6.5, Spring Authorization Server 1.5. Chọn **Java 21** cùng nhánh Boot 3.5/Security 6.5/SAS 1.5, để Boot quản lý dependency rồi kiểm tra version thực tế. Không ép Spring Security 7 chỉ để được số major mới hơn vì mã cấu hình có thể khác.

Nếu dùng cho production thay vì phòng thực hành, phải xem lại **tình trạng hỗ trợ tại thời điểm triển khai** và có kế hoạch nâng cấp nếu nhánh đó không còn nhận bản vá theo chính sách.

### Tình huống B — Xây Authorization Server mới, ít ràng buộc mã cũ

Nhóm chọn **bản Boot 4.x đang được hỗ trợ**, dùng Security 7.x và thành phần Authorization Server cùng thế hệ. Chọn Java 21 nếu đáp ứng yêu cầu của release. Bắt đầu từ tài liệu Spring Security 7, nhất là phần thay đổi migration và cấu hình; không lấy một ví dụ SAS 1.5 rồi chỉ thay plugin Boot thành 4.x.

### Tình huống C — Resource Server ở Boot 3, Authorization Server ở Boot 4

Hai dịch vụ có thể chạy trên **hai thế hệ Spring khác nhau**. Điều phải kiểm tra là chuẩn giao thức liên thông: issuer, authorization server metadata, JWKS, token signature, audience, scope, endpoint, claim mapping, OIDC discovery và thời hạn token. Thay đổi Boot của AS không bắt buộc cập nhật Boot RS đồng thời, miễn API/giao thức vẫn tương thích và hệ thống được kiểm thử.

### Tình huống D — CI dùng Java 21 nhưng production còn Java 17

Nếu ứng dụng build với `--release 21` thì JVM 17 không chạy được. Cách sửa không phải đổi riêng một dependency Spring Security; phải chọn **target Java tương thích** hoặc nâng production JVM, đồng thời kiểm tra lại thư viện và image. Đây là ràng buộc kỹ thuật cần giải quyết trước khi triển khai.

## 7. Những sai lầm khi ghép phiên bản

| Sai lầm | Biểu hiện có thể gặp | Cách phòng tránh |
| --- | --- | --- |
| Ghép Spring Boot 3.x với Spring Security 7.x | Lỗi binary/API compatibility, cấu hình không khớp | Dùng Security 6.x tương ứng với Boot 3 hoặc nâng cả ứng dụng theo kế hoạch Boot 4 |
| Ghép Spring Boot 4.x với thư viện/cấu hình SAS 1.x theo thói quen | Lỗi class/method, starter/config không tương thích | Theo tài liệu Spring Security 7 và hướng migration phù hợp |
| Ghi cứng version cho mọi module Spring | Các module cùng hệ bị lệch minor/patch | Để Spring Boot BOM quản lý, chỉ override khi có lý do và kiểm thử |
| Chọn Java mới hơn nhưng chưa kiểm tra hỗ trợ | Lỗi build plugin, toolchain hoặc runtime | Đối chiếu system requirements và chạy test trên đúng JVM |
| Chọn bản patch quá cũ trong nhánh đã chốt | Có thể tồn tại lỗi được sửa ở patch mới hơn | Áp dụng bản patch được duy trì theo chính sách hỗ trợ |
| Dùng `SNAPSHOT` hoặc milestone vô tình trong production | API hoặc dependency graph biến động, khả năng hỗ trợ khác release ổn định | Chỉ dùng pre-release trong thử nghiệm có chủ đích |
| Nâng riêng Authorization Server mà không kiểm tra Boot/Security | `NoSuchMethodError`, `ClassNotFoundException`, lỗi khởi động và giao thức | Nâng theo thế hệ tương thích và kiểm thử các endpoint |
| Tin rằng Maven/Gradle báo `BUILD SUCCESSFUL` là đủ | Lỗi chỉ lộ ở đường đi OAuth 2.0/OIDC thực tế | Bổ sung test luồng authorization, token, discovery, resource validation |

### 7.1. Phân biệt các lỗi thường gặp

**`UnsupportedClassVersionError`:** bytecode được biên dịch bởi Java cao hơn JVM chạy. Kiểm tra `java -version` của runtime và toolchain/target release.

**`NoSuchMethodError` hoặc `NoClassDefFoundError`:** có thể do module Spring/Security không cùng thế hệ, hoặc một thư viện đã được build theo API khác. In dependency tree và tìm bản thực tế được nạp.

**`BeanCreationException` khi bật security auto-configuration:** có thể do cấu hình chưa đầy đủ, bean trùng nhau, thay đổi API hoặc cấu hình theo phiên bản khác. Cần đọc nguyên nhân gốc của stack trace; không suy ngay rằng “Spring Security bị lỗi”.

**Token endpoint trả lỗi sau nâng cấp:** nguyên nhân có thể là client registration, grant type, PKCE, redirect URI, phương thức xác thực client hoặc thay đổi cấu hình chính sách. Xác minh request và server log đã che thông tin bí mật.

## 8. Khóa phiên bản mà vẫn cập nhật bảo mật được

Có hai nhu cầu tưởng như trái ngược: **reproducible build** và **cập nhật bản vá**. Cách giải quyết là khóa **phiên bản cụ thể của release đang dùng**, sau đó nâng cấp có kiểm soát.

~~~mermaid
flowchart LR
    A["Chọn bản Boot patch được hỗ trợ"]
    B["Pin trong parent/plugin và wrapper"]
    C["Resolve, kiểm tra dependency tree"]
    D["Test OAuth2/OIDC + regression"]
    E["Build image và triển khai"]
    F["Theo dõi advisories / release notes"]
    G["Nâng patch, kiểm tra lại"]

    A --> B --> C --> D --> E --> F --> G
    G --> C
~~~

Lưu ý vận hành:

- Sử dụng Maven/Gradle Wrapper để tránh chênh lệch phiên bản công cụ giữa máy cá nhân và CI.
- Ghi lại bản JDK, Spring Boot, dependency graph và image digest cho mỗi release khi hệ thống yêu cầu truy vết.
- Khi phát hiện lỗ hổng, xem advisory và bản sửa của **cả nhánh Spring Boot/Security/Framework**. Không tự nâng ngẫu nhiên một artifact rồi bỏ qua kết quả test.
- Ưu tiên tiến hành cập nhật patch định kỳ trong một minor đang hỗ trợ; nâng major theo kế hoạch riêng có migration test.
- Xem xét lưu SBOM để có khả năng đối chiếu dependency trong phiên bản đã phát hành.
- Xác minh môi trường staging và production sử dụng đúng image, JDK và cấu hình issuer/key management đã kiểm thử.

## 9. Checklist trước khi triển khai bài học

Đánh dấu sau khi kiểm tra trên máy và repository thực tế:

- [ ] Đã chọn thế hệ Spring Boot 3/Security 6/SAS 1.x **hoặc** Boot 4/Security 7 đúng với mã nguồn.
- [ ] Có bản Spring Boot patch cụ thể, còn phù hợp chính sách hỗ trợ và cập nhật bảo mật.
- [ ] Biết rõ Java requirement của release; build JDK, toolchain và production JVM tương thích.
- [ ] Maven/Gradle Wrapper đã được đưa vào repository.
- [ ] Dependency Spring Framework/Security/Authorization Server không bị override sai thế hệ.
- [ ] Lệnh dependency tree/insight xác nhận bản thư viện được resolve đúng.
- [ ] Build và unit test thành công.
- [ ] Các luồng cấp code/token, PKCE, OIDC và kiểm tra token từ RS được test theo nhu cầu ứng dụng.
- [ ] Có kế hoạch theo dõi patch và migration khi nhánh ngừng hỗ trợ.

## 10. Câu hỏi ôn tập

**Câu 1.** Vì sao không thể chỉ chọn Spring Security 7.x mới nhất cho dự án Spring Boot 3.5?  
**Đáp án:** Boot 3.x và Security 6.x cùng thế hệ API/phụ thuộc. Đẩy Security 7 vào Boot 3 có thể làm lệch Spring Framework, API cấu hình và autoconfiguration. Muốn dùng Security 7 cần lên kế hoạch chuyển sang thế hệ Boot tương ứng.

**Câu 2.** Maven POM dùng Spring Boot parent đã quản lý dependencies. Có cần khai báo `<version>` cho `spring-boot-starter-oauth2-authorization-server` không?  
**Đáp án:** Thông thường không. Để parent/BOM quản lý version; chỉ tùy chỉnh khi có lý do rõ ràng và kiểm chứng dependency graph.

**Câu 3.** Đã chọn Java 21 làm toolchain, vì sao vẫn phải kiểm tra Java trong image Docker?  
**Đáp án:** Bytecode tạo ra có thể yêu cầu JVM 21; nếu image chạy Java 17, ứng dụng sẽ không khởi động. JDK biên dịch và runtime cần tương thích.

**Câu 4.** Một Authorization Server Spring Boot 4 có thể cấp token cho Resource Server Spring Boot 3 không?  
**Đáp án:** Có, nếu giao thức, issuer, chữ ký/JWKS, token audience/claim, chính sách và client integration tương thích; cần kiểm thử thực tế.

**Câu 5.** Một dự án đã build thành công với bộ phiên bản mới, có thể đưa thẳng vào production chưa?  
**Đáp án:** Chưa. Cần xác minh dependency resolve, support policy, các endpoint OAuth 2.0/OIDC, quản lý token/khóa và kiểm thử tương tác với client/resource server.

## 11. Tóm tắt quyết định thiết kế

**Bắt đầu từ Spring Boot, để BOM quản lý Spring Security/Spring Framework, rồi chọn Authorization Server theo cùng thế hệ.** Với mã ví dụ SAS 1.x, bộ Java 21 + Boot 3.5.x + Security 6.5.x + SAS 1.5.x là một mốc tham chiếu nhất quán về API. Với dự án theo hướng Spring mới, chọn bản Boot 4.x đang được hỗ trợ cùng Security 7.x và tài liệu Authorization Server tương ứng.

Trong cả hai trường hợp, ký hiệu `x` chỉ **nhánh**, không phải version dùng để triển khai. Bản patch phải được chọn và khóa cụ thể, đối chiếu với tài liệu chính thức, dependency tree, kết quả test và vòng đời hỗ trợ. Đây là nền tảng để những bước cấu hình Authorization Server tiếp theo có thể xây dựng, kiểm thử và vận hành một cách đáng tin cậy.

