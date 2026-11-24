# Kiểm tra đơn vị bảo trì, BOM và khả năng tương thích hiện tại

## 1. Vì sao cần kiểm tra trước khi chọn dependency?

Một ứng dụng Spring Boot cần dùng Nacos Discovery để đăng ký service và OSS để lưu file hóa đơn. Nhóm phát triển tìm thấy một starter trên GitHub, thêm dependency rồi build. Tuy nhiên, ứng dụng đang dùng Spring Boot 4, trong khi starter được phát hành từ nhiều năm trước và chưa công bố ma trận tương thích tương ứng. Build có thể resolve dependency nhưng lỗi runtime vẫn xuất hiện do API Spring thay đổi, Jakarta namespace, SDK transitive hoặc cấu hình auto-configuration cũ.

Trước khi chọn thư viện, cần trả lời bốn câu hỏi:

1. **Ai chịu trách nhiệm bảo trì?** Tổ chức nào sở hữu repository, nhóm nào review pull request, có maintainer hoạt động và kênh hỗ trợ nào?
2. **Dòng phát hành nào đang được duy trì?** Có release GA, changelog, security fix và hướng dẫn nâng cấp không?
3. **BOM nào quản lý dependency?** Spring Boot, Spring Cloud, Spring Cloud Alibaba, Aliyun service starter và SDK sản phẩm có thể dùng các BOM khác nhau.
4. **Toàn bộ stack có tương thích không?** Cần xét đồng thời JDK, Spring Boot, Spring Cloud, Spring Cloud Alibaba, client Nacos/Sentinel/Seata/RocketMQ, starter dịch vụ và runtime của Alibaba Cloud.

Bài học thuộc chương **Alibaba Cloud** trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module hướng dẫn tích hợp Spring Boot với dịch vụ managed của AWS, Azure, Google Cloud và Alibaba Cloud qua thư viện tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các provider.

Sau bài học, bạn có thể:

- Đánh giá đơn vị bảo trì và sức khỏe của một thư viện qua bằng chứng công khai.
- Phân biệt trạng thái duy trì của Spring Cloud Alibaba với trạng thái hỗ trợ của Spring Cloud upstream.
- Chọn BOM và phiên bản phù hợp theo ma trận chính thức.
- Đọc dependency tree để tìm xung đột và dependency bị override.
- Lập kế hoạch nâng cấp, kiểm thử, pin version và rollback.
- Nhận diện rủi ro khi dùng Aliyun Spring Boot Starters có dấu hiệu hoạt động thấp.

## 2. Ba lớp bảo trì cần kiểm tra

Trong hệ sinh thái Alibaba Cloud, không phải mọi dependency đều do cùng một nhóm phát triển. Hãy xác định đúng dự án trước khi đánh giá.

| Thành phần | Phạm vi | Nơi kiểm tra |
| --- | --- | --- |
| **Spring Cloud Alibaba (SCA)** | Tích hợp microservice theo Spring Cloud: Nacos, Sentinel, Seata, RocketMQ và các thành phần liên quan | Repository **alibaba/spring-cloud-alibaba**, tài liệu **sca.aliyun.com**, release notes, FAQ và pull requests |
| **Aliyun Spring Boot Starters** | Auto-configuration cho dịch vụ cụ thể như OSS, SMS, Redis, RDS hoặc SchedulerX | Repository **alibaba/aliyun-spring-boot**, BOM, module starter, sample và issue |
| **Alibaba Cloud Java SDK** | Client API theo sản phẩm, ví dụ OSS SDK hoặc OpenAPI SDK | Repository SDK của sản phẩm, tài liệu SDK, Maven Central và security advisories |
| **Spring Boot / Spring Cloud** | Nền tảng Spring mà integration phụ thuộc | Tài liệu compatibility/support chính thức của Spring |
| **Managed service runtime** | Nacos/MSE, OSS, SMS, RDS, RocketMQ hoặc dịch vụ cụ thể trên cloud | Tài liệu sản phẩm, supported protocol/version, region và thông báo vận hành của Alibaba Cloud |

**Đơn vị bảo trì** có thể là một tổ chức, nhóm sản phẩm, cộng đồng open-source hoặc một nhóm committer. Repository owner chỉ cho biết nơi lưu mã nguồn và chịu trách nhiệm quản lý dự án ở cấp tổ chức; nó không tự chứng minh có đội ngũ trực hỗ trợ 24/7 hoặc cam kết vá lỗi theo SLA.

Cần tách ba trách nhiệm:

- **Maintainer của thư viện:** review mã nguồn, phát hành artifact, sửa lỗi tích hợp và cập nhật tương thích.
- **Nhà cung cấp managed service:** vận hành dịch vụ cloud, endpoint, SLA, quota và các thay đổi phía server.
- **Đội ứng dụng:** chọn version, quản lý credentials, kiểm thử tương thích và nâng cấp dependency.

Ví dụ, SCA có thể được duy trì bởi cộng đồng Alibaba nhưng Nacos cluster của doanh nghiệp lại do Alibaba Cloud MSE vận hành. Sự cố Nacos client tương thích Spring khác với sự cố endpoint MSE; phải xác định đúng đơn vị xử lý.

## 3. Đánh giá đơn vị bảo trì và sức khỏe repository

### 3.1. Kiểm tra quyền sở hữu và governance

Bắt đầu từ repository được tài liệu chính thức liên kết. Kiểm tra:

- Organization/repository owner có khớp tài liệu của sản phẩm không?
- Có license, Code of Conduct, CONTRIBUTING hoặc hướng dẫn báo lỗi không?
- Ai có quyền merge/release? Có nhiều maintainer độc lập hay một người xử lý phần lớn thay đổi?
- Có kênh hỗ trợ chính thức, roadmap, release notes và lịch cộng đồng không?
- Issue bảo mật có quy trình báo cáo riêng hay chỉ mở public issue?

SCA công bố tài liệu và cộng đồng tại **sca.aliyun.com**, liên kết tới repository GitHub và các kênh trao đổi cộng đồng. FAQ của dự án công bố danh sách các nhánh đang được duy trì. Đây là tín hiệu tích cực về governance và hoạt động phát triển, nhưng vẫn cần kiểm tra commit/release thực tế của nhánh mà ứng dụng định dùng.

Với một thư viện service starter riêng, cần kiểm tra repository của chính starter. Không suy ra tình trạng bảo trì của **aliyun-spring-boot** từ hoạt động của **spring-cloud-alibaba**; hai dự án có lịch phát hành riêng.

### 3.2. Dấu hiệu của một dự án được duy trì tốt

| Tín hiệu | Bằng chứng cần xem | Câu hỏi đánh giá |
| --- | --- | --- |
| Release | GitHub Releases, Maven Central, changelog | Có GA release mới và mô tả thay đổi rõ ràng không? |
| Commit | Lịch sử commit của nhánh stable | Có sửa lỗi, cập nhật dependency và tài liệu đều đặn không? |
| Pull request | PR mở/đã merge, reviewer | Có review độc lập và phản hồi trong thời gian hợp lý không? |
| Issue | Bug, feature request, stale/closed issue | Lỗi nghiêm trọng có được triage và giải quyết không? |
| CI | Workflow build, test, security scan | Nhánh release có pipeline xanh và test trên JDK/Boot mục tiêu không? |
| Security | Security policy, advisory, dependency bot | Có cơ chế nhận và phát hành bản vá bảo mật không? |
| Tài liệu | Version matrix, migration guide, sample | Tài liệu có khớp artifact đang phát hành không? |
| Bus factor | Số maintainer/reviewer thực sự hoạt động | Nếu một người nghỉ, ai có thể review và phát hành? |

Không đánh giá chỉ bằng số star, fork hoặc commit tổng. Một repository có nhiều star nhưng không có release trong thời gian dài vẫn có thể là rủi ro. Ngược lại, một thư viện nhỏ có maintainer phản hồi đều và có release ổn định vẫn có thể đáp ứng nhu cầu.

### 3.3. Snapshot bảo trì ngày 24/11/2026

Tại thời điểm kiểm tra, tài liệu chính thức của **Spring Cloud Alibaba** liệt kê các nhánh **2.2.x, 2021.x, 2022.x, 2023.x, 2025.0.x và 2025.1.x** là đang được duy trì. Release notes 2025.x ghi rõ 2025.1.x dành cho Spring Boot 4.0.x/Spring Cloud 2025.1.x và 2025.0.x dành cho Spring Boot 3.5.x/Spring Cloud 2025.0.x. Đây là tuyên bố về nhánh SCA; cần kiểm tra thêm trạng thái hỗ trợ của Spring Cloud upstream trước khi kết luận toàn stack còn được hỗ trợ. [FAQ chính thức](https://sca.aliyun.com/en/docs/2025.x/overview/faq/) · [SCA release notes](https://sca.aliyun.com/en/docs/2025.x/overview/version-explain/)

Repository **alibaba/aliyun-spring-boot** tự mô tả là Spring Boot Starters cho các dịch vụ Aliyun. README hướng dẫn dùng BOM **aliyun-spring-boot-dependencies:1.0.0** và ghi dự án hỗ trợ Spring Boot 2 trở lên. Tuy nhiên, hoạt động công khai của repository có dấu hiệu thấp: chỉ mục GitHub ghi nhận lần cập nhật cuối là **08/03/2023**. Điều này **không phải thông báo chính thức rằng dự án đã EOL**, nhưng là rủi ro cần xem xét trước khi đưa starter vào ứng dụng Spring Boot 3/4 hoặc workload quan trọng. [Repository và README](https://github.com/alibaba/aliyun-spring-boot) · [GitHub activity listing](https://github.com/topics/spring-boot-starters)

Trong khi đó, repository **alibaba/spring-cloud-alibaba** có release notes, nhánh 2025.x và hoạt động issue/PR gần đây. Dự án đang tiến hành cập nhật tương thích với Spring Boot 4.2 và Spring Cloud 2026.0: PR **#4429** được mở ngày 20/11/2026, còn ở trạng thái **Open** và đang chờ ít nhất một review phê duyệt vào ngày 24/11/2026. Vì vậy, không lấy branch hoặc PR chưa merge làm bằng chứng rằng artifact GA đã hỗ trợ stack mới. [SCA PR #4429](https://github.com/alibaba/spring-cloud-alibaba/pull/4429)

Một bình luận công khai trong issue nâng cấp cũng đề cập nhiều committer hiện chưa thực hiện vai trò thường xuyên. Đây là tín hiệu cần theo dõi về **bus factor** và khả năng review, không phải tuyên bố chính thức rằng toàn bộ dự án đã ngừng bảo trì. Khi đánh giá thư viện cho production, ghi lại người review, release cadence và kênh escalation thay vì chỉ dựa vào một nhận xét riêng lẻ. [Issue #4400](https://github.com/alibaba/spring-cloud-alibaba/issues/4400)

**Kết luận đánh giá:** SCA có tài liệu nhánh và ma trận release rõ hơn; Aliyun Spring Boot Starters cần thẩm định kỹ hơn vì README/BOM cũ và dấu hiệu hoạt động thấp. SDK sản phẩm có thể vẫn được cập nhật độc lập; ví dụ repository umbrella **aliyun/alibabacloud-sdk** có hoạt động gần thời điểm kiểm tra. Không suy ra SDK hoặc starter còn được hỗ trợ chỉ từ tình trạng của dự án khác.

## 4. BOM là gì và vì sao phải dùng đúng BOM?

**Bill of Materials (BOM)** là POM quản lý phiên bản dependency. Khi import BOM vào **dependencyManagement**, Maven có thể chọn version đồng bộ cho các artifact thuộc cùng hệ sinh thái. BOM giúp giảm khai báo version lặp lại, nhưng không tự bảo đảm mọi dependency trong ứng dụng tương thích.

Một ứng dụng có thể có nhiều BOM:

| BOM | Quản lý nhóm nào? | Ví dụ tọa độ |
| --- | --- | --- |
| Spring Boot dependencies/parent | Thư viện nền Spring Boot và dependency được Boot quản lý | **org.springframework.boot:spring-boot-dependencies** |
| Spring Cloud BOM | Thành phần thuộc Spring Cloud release train | **org.springframework.cloud:spring-cloud-dependencies** |
| SCA BOM | Artifact của Spring Cloud Alibaba và các phiên bản component tích hợp | **com.alibaba.cloud:spring-cloud-alibaba-dependencies** |
| Aliyun Spring Boot BOM | Các service starters trong dự án aliyun-spring-boot | **com.alibaba.cloud:aliyun-spring-boot-dependencies** |
| Product SDK BOM | Các module của một SDK sản phẩm nếu nhà cung cấp công bố | Tùy sản phẩm/SDK |

**Không dùng BOM SCA để đoán version OSS/SMS starter**, và cũng không mặc định BOM Aliyun starter quản lý mọi SDK được ứng dụng thêm thủ công. Nếu dự án cần cả Nacos Discovery và OSS, có thể cần BOM SCA cùng một cơ chế quản lý version SDK/starter OSS. Trước khi import nhiều BOM, kiểm tra dependency convergence và các version bị override.

### 4.1. Cách Maven chọn version

Maven xét dependency management và quy tắc mediation để quyết định version cuối. Một BOM có thể quản lý version gián tiếp của dependency transitively; khai báo version trực tiếp trong dependency hoặc import BOM khác có thể làm thay đổi kết quả.

Ví dụ không nên làm:

~~~xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
    <!-- Không tự khai báo version khi BOM đã quản lý artifact này. -->
</dependency>
~~~

Khi SCA đã cung cấp BOM, hãy bỏ version ở từng starter và để BOM quản lý. Nếu có lý do override một dependency con, ghi rõ lý do, kiểm thử lại và theo dõi thay đổi trong các lần nâng cấp.

### 4.2. Import BOM không thay thế kiểm tra compatibility

Một dependency có thể resolve thành công nhưng vẫn không tương thích runtime. Ví dụ:

- API **javax.*** thay đổi sang **jakarta.***.
- Spring Framework đổi signature hoặc auto-configuration contract.
- Jackson major version đổi.
- Spring Cloud release train đổi interface hoặc behavior.
- Nacos client và server không cùng dải protocol/tính năng.
- SDK sản phẩm thay đổi signing, credential provider hoặc endpoint resolution.

Vì vậy, BOM là **điểm xuất phát quản lý version**, không phải chứng nhận rằng ứng dụng của bạn đã kiểm thử tương thích.

## 5. Ma trận tương thích SCA hiện hành

### 5.1. Các cặp version do SCA công bố

Theo release notes chính thức 2025.x, hai dòng version có ma trận sau:

| Spring Cloud Alibaba | Spring Cloud | Spring Boot | Java/JDK | Ghi chú |
| --- | --- | --- | --- | --- |
| **2025.1.0.0** | **2025.1.0** | **4.0.x** (bảng release ghi 4.0.0) | JDK 17+ theo README nhánh 2025.1.x | Dòng SCA mới hơn trong release notes đã tra cứu |
| **2025.0.0.0** | **2025.0.0** | **3.5.x** (bảng release ghi 3.5.0) | JDK 17+ theo README nhánh 2025.0.x | Cần xét riêng trạng thái hỗ trợ Spring Cloud upstream |
| **2023.x** | **2023.x** | **3.2.x** | Theo nhánh tương ứng | Dòng legacy; không mặc định dùng cho dự án mới |
| **2022.x** | **2022.x** | **3.0.x** | Theo nhánh tương ứng | Dòng legacy |
| **2021.x** | **2021.x** | **2.6.x** | Theo nhánh tương ứng | Dòng legacy |
| **2.2.x** | **Hoxton** | **2.2.x/2.3.x tùy release** | Theo nhánh tương ứng | Dòng legacy |

Nguồn chính thức có thể cập nhật theo release mới; kiểm tra lại trước mỗi lần nâng cấp: [SCA Version Release Notes](https://sca.aliyun.com/en/docs/2025.x/overview/version-explain/) và [SCA FAQ](https://sca.aliyun.com/en/docs/2025.x/overview/faq/).

### 5.2. Component versions được BOM SCA 2025.x ghim

SCA release notes còn công bố các version component tích hợp:

| Component | SCA 2025.1.0.0 | SCA 2025.0.0.0 |
| --- | --- | --- |
| Sentinel | 1.8.9 | 1.8.9 |
| Nacos | 3.1.1 | 3.0.3 |
| RocketMQ | 5.3.1 | 5.3.1 |
| SchedulerX | 1.13.3 | 1.13.1 |
| Seata | 2.5.0 | 2.5.0 |

Không tự nâng một component lên version mới hơn chỉ vì Maven Central đã có artifact đó. SCA có thể phụ thuộc vào behavior hoặc API cụ thể của component; nâng riêng Nacos/Sentinel/Seata có thể làm mất compatibility. Nếu cần nâng, kiểm tra issue/PR chính thức, release notes component và chạy integration tests.

### 5.3. Chú ý về Spring Cloud upstream support

Có hai khái niệm cần phân biệt:

- **SCA branch maintenance:** FAQ của SCA liệt kê nhánh nào dự án SCA đang duy trì.
- **Spring Cloud support:** vòng hỗ trợ của Spring Cloud release train và các project upstream.

Bảng hỗ trợ Spring Cloud được chỉnh sửa ngày **18/11/2026** đánh dấu release train **2025.0** bằng gạch ngang (ngoài OSS support policy), trong khi 2025.1 vẫn nằm trong cột hiện hành. Do đó, dù FAQ SCA vẫn liệt kê nhánh **2025.0.x** đang được duy trì, stack Boot 3.5/Cloud 2025.0 cần được đánh giá theo chính sách upstream và yêu cầu support của tổ chức. Không diễn giải **SCA branch active** thành **mọi thành phần upstream còn nhận security fix**. [Spring Cloud Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions)

Spring Cloud công bố chính sách hỗ trợ major version ít nhất 3 năm và minor version ít nhất 12 tháng, đồng thời khuyến nghị dùng GA mới nhất. Release train gồm nhiều project; thời gian hỗ trợ của train phụ thuộc vòng đời các project thành phần. Bảng hỗ trợ cũng lưu ý dependency bên thứ ba có thể hết hỗ trợ trước khi Spring Cloud release train kết thúc. Vì vậy, cần kiểm tra vòng đời Nacos, Sentinel, Seata, RocketMQ và SDK riêng thay vì chỉ nhìn version Spring Cloud.

### 5.4. Spring Cloud 2026.0 và Spring Boot 4.2

Spring Cloud **2026.0.0** đã được phát hành ngày 20/11/2026 và Spring Boot **4.2.0** có release notes. Tuy nhiên, tại thời điểm **24/11/2026**, PR **#4429** nâng SCA lên Spring Cloud 2026.0.0/Spring Boot 4.2.0 vẫn đang mở, cần ít nhất một review phê duyệt. Trang release notes SCA 2025.x chưa liệt kê artifact GA cho cặp mới này.

Vì vậy:

1. Không tự đặt version SCA 2026.0.0 chỉ vì upstream Spring Cloud đã phát hành 2026.0.0.
2. Không dùng branch/PR chưa merge như một dependency production đã phát hành.
3. Chờ PR được review/merge, release SCA GA và release notes cập nhật.
4. Sau khi artifact xuất hiện trên Maven Central, kiểm tra BOM, changelog, JDK baseline, component versions và integration test.

Đây là ví dụ thực tế cho thấy compatibility là giao điểm của nhiều dự án, không phải chỉ một version number. [Spring Cloud release](https://github.com/spring-cloud/spring-cloud-release/releases) · [SCA PR #4429](https://github.com/alibaba/spring-cloud-alibaba/pull/4429)

## 6. Ví dụ Maven: quản lý SCA BOM đúng cách

Ví dụ dưới đây dùng nhánh **Spring Boot 4.0.x + Spring Cloud 2025.1.x + Spring Cloud Alibaba 2025.1.0.0** theo ma trận đã công bố. Chọn một bản Boot 4.0.x đã được dự án xác minh trong release notes; không tự thay bằng Boot 4.2.

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>${springBootVersion}</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>${springCloudVersion}</spring-cloud.version>
    <spring-cloud-alibaba.version>${springCloudAlibabaVersion}</spring-cloud-alibaba.version>
</properties>

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

<dependencies>
    <dependency>
        <groupId>com.alibaba.cloud</groupId>
        <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
    </dependency>
</dependencies>
~~~

**BOOT_VERSION** phải là một version Boot 4.0.x GA đã được dự án chấp nhận. BOM Spring Cloud quản lý Spring Cloud projects; BOM SCA quản lý integration artifacts của Alibaba. Khi nâng version, thay version property ở một nơi, sau đó xem effective POM và dependency tree.

Ví dụ cấu hình discovery:

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

Đây là ví dụ property cơ bản. Với Nacos Config trên nhánh SCA 2025.1, release notes cho biết bootstrap config support đã bị loại bỏ và ứng dụng cần chuyển sang **spring.config.import** theo tài liệu nhánh mới. Không sao chép cấu hình **bootstrap.yml** của dự án cũ sang nhánh mới mà không xem migration guide.

## 7. Aliyun Spring Boot Starter BOM: kiểm tra riêng

### 7.1. BOM và artifact

Repository **alibaba/aliyun-spring-boot** hướng dẫn import BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>aliyun-spring-boot-dependencies</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau đó thêm starter theo dịch vụ, ví dụ:

~~~xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>aliyun-oss-spring-boot-starter</artifactId>
</dependency>
~~~

BOM **1.0.0** là version được README của repository công bố. README ghi hỗ trợ Spring Boot 2 trở lên, nhưng không đưa ra ma trận chi tiết chứng minh mọi starter đều tương thích Spring Boot 3.x hoặc 4.x. Điều kiện **Boot 2+** không nên được hiểu là chứng nhận cho mọi major version phát hành sau đó.

### 7.2. Đánh giá rủi ro trước khi dùng

Trước khi thêm starter vào production, xác minh:

- Artifact starter có bản release mới trên Maven Central không?
- POM của starter kéo SDK sản phẩm version nào?
- SDK đó còn được duy trì và hỗ trợ JDK/Spring Boot mục tiêu không?
- Auto-configuration dùng **javax.*** hay **jakarta.***?
- Có test với Spring Boot 3/4 không?
- Có security fixes, issue response và migration notes không?
- Starter có hỗ trợ RAM role/STS credential provider hiện hành hay chỉ AccessKey tĩnh?
- Có cách thay bean/client mặc định và cấu hình timeout/endpoint không?

Nếu thiếu bằng chứng tương thích, hãy thử trên một nhánh nhỏ với integration test và kiểm tra source/bytecode trước khi dùng. Với dịch vụ OSS, có thể dùng OSS Java SDK trực tiếp và tự cấu hình Spring bean nếu starter cũ không đáp ứng yêu cầu.

### 7.3. Phân biệt starter và SDK còn hoạt động

Một starter ít cập nhật không có nghĩa product SDK cũng ngừng cập nhật. Ví dụ repository SDK umbrella **aliyun/alibabacloud-sdk** có hoạt động gần thời điểm kiểm tra. Nhưng điều đó cũng không chứng minh một starter cụ thể tự động tương thích với SDK mới. Cần kiểm tra version transitive thực tế và khả năng API mà starter gọi.

Nếu dùng SDK trực tiếp, hãy quản lý client trong Spring bean, tái sử dụng client, cấu hình credentials/region/endpoint theo hướng dẫn sản phẩm và đóng client khi ứng dụng dừng. Tách SDK sau interface nội bộ để có thể thay thế adapter khi nhà cung cấp thay đổi.

## 8. Kiểm tra dependency tree và effective POM

### 8.1. Xem version Maven thực sự chọn

Chạy trong thư mục dự án:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn dependency:tree -Dverbose -DoutputFile=target/dependency-tree.txt
~~~

Đọc kết quả để xác định:

- Version của **spring-boot**, **spring-cloud** và các artifact **com.alibaba.cloud**.
- Nacos client, Sentinel, Seata, RocketMQ và SchedulerX thực tế được resolve.
- SDK OSS/SMS/RDS nào được kéo vào.
- Dependency nào bị **omitted for conflict** hoặc bị version trực tiếp override.
- Có cùng một thư viện xuất hiện ở nhiều major version hay không.

Ví dụ một module có thể yêu cầu Nacos client 3.1.x nhưng dependency khác kéo 2.x. Build vẫn có thể thành công nếu Maven chọn một version, nhưng runtime có thể phát sinh **NoSuchMethodError**, **NoClassDefFoundError** hoặc lỗi giao thức.

### 8.2. Kiểm tra dependency convergence

Có thể dùng Maven Enforcer để chặn dependency tree không hội tụ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-enforcer-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>enforce-dependency-convergence</id>
            <goals>
                <goal>enforce</goal>
            </goals>
            <configuration>
                <rules>
                    <dependencyConvergence/>
                    <requireUpperBoundDeps/>
                </rules>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**dependencyConvergence** phát hiện nhiều version của cùng artifact trong cây dependency; **requireUpperBoundDeps** phát hiện một số trường hợp version được chọn thấp hơn version mà dependency khác yêu cầu. Không phải conflict nào cũng có thể giải quyết bằng cách chọn version cao nhất; hãy theo BOM chính thức và kiểm tra API compatibility trước khi override.

Nếu dùng Gradle, xem **dependencies**, **dependencyInsight** và dependency constraints/platform để tìm nguồn version được chọn. Không import Maven BOM theo cách tùy tiện trong Gradle; dùng **platform(...)** hoặc **enforcedPlatform(...)** khi có chủ đích.

### 8.3. Ghi nhận version đã kiểm thử

Tạo một bảng trong tài liệu kỹ thuật của dự án để nhóm phát triển biết chính xác stack đang chạy:

| Thành phần | Version pin | Nguồn quyết định | Test đã chạy |
| --- | --- | --- | --- |
| JDK | 17 | Baseline SCA 2025.1 | Build/unit/integration |
| Spring Boot | 4.0.x | Boot parent/BOM | Context smoke test |
| Spring Cloud | 2025.1.0 | Spring Cloud BOM | Discovery test |
| Spring Cloud Alibaba | 2025.1.0.0 | SCA release notes | Nacos integration |
| Nacos client | BOM quản lý | SCA component matrix | Register/config lookup |
| OSS SDK/starter | Version được chọn riêng | Product SDK/starter docs | Upload/download test |

Bảng này là baseline đã kiểm thử của ứng dụng, không phải bản sao của bảng compatibility nhà cung cấp. Cập nhật sau mỗi lần nâng dependency và giữ lại kết quả test/release notes tương ứng.

## 9. Quy trình nâng cấp an toàn

### 9.1. Trước khi nâng cấp

1. Chốt phiên bản hiện tại từ effective POM/dependency tree.
2. Kiểm tra release notes và migration guide của Spring Boot, Spring Cloud, SCA và product SDK.
3. Đọc security advisories và issue đã biết của các dependency chính.
4. Xác nhận JDK baseline, Jakarta namespace, Jackson version và các API bị deprecate.
5. Chọn một cặp version nằm trong ma trận chính thức.
6. Tạo branch nâng cấp riêng, không đồng thời thay đổi logic nghiệp vụ lớn.

### 9.2. Khi nâng cấp

- Nâng Spring Boot, Spring Cloud và SCA theo cặp version đã công bố.
- Giữ BOM là nguồn quản lý version chính; hạn chế pin version con trực tiếp.
- Nâng product SDK/starter riêng nếu compatibility matrix yêu cầu.
- Chạy compile, unit test, Spring context test và integration test trên dịch vụ sandbox.
- Kiểm tra startup logs, auto-configuration report và warning về property cũ.
- Xác minh credentials, RAM role, endpoint, region và TLS vẫn hoạt động.
- Đo latency/error rate trước và sau nâng cấp trong staging.

### 9.3. Sau khi nâng cấp

- Canary một workload trước khi rollout toàn bộ.
- Theo dõi lỗi connection, timeout, discovery/config refresh và API service.
- Kiểm tra metrics/logs, không chỉ kiểm tra process đã khởi động.
- Giữ artifact cũ và cấu hình cũ để rollback.
- Cập nhật dependency inventory, SBOM và baseline version đã kiểm thử.

Không nâng toàn bộ hệ sinh thái chỉ vì một BOM mới xuất hiện. Nếu dự án cần một security fix ở SDK sản phẩm, có thể nâng SDK độc lập sau khi xác nhận tương thích mà không đổi release train Spring.

## 10. Kiểm thử tương thích thực tế

### 10.1. Test tối thiểu cho Spring Cloud Alibaba

| Test | Mục tiêu | Dấu hiệu đạt |
| --- | --- | --- |
| Spring context startup | Auto-configuration khởi tạo được | ApplicationContext lên không lỗi |
| Nacos registration | Service đăng ký vào đúng namespace/group | Instance xuất hiện với metadata đúng |
| Discovery lookup | Client tìm được service | Có instance và gọi endpoint thành công |
| Config import/refresh | Cấu hình lấy từ Nacos theo nhánh hiện tại | Property được nạp và refresh theo thiết kế |
| Sentinel rule | Rule được áp dụng | Request vượt ngưỡng có behavior đúng |
| Seata transaction | Giao dịch phân tán được commit/rollback | Không để lại trạng thái không nhất quán |
| RocketMQ messaging | Producer/consumer dùng đúng protocol | Message gửi, nhận và xử lý idempotent |

Chỉ kiểm thử component mà ứng dụng thực sự dùng. Không cần triển khai Seata/RocketMQ trong một ứng dụng chỉ cần Nacos Discovery.

### 10.2. Test cho service starter hoặc SDK

Với OSS, kiểm tra upload/download, object metadata, multipart, endpoint/region và quyền RAM. Với SMS, kiểm tra sender/template đã được phê duyệt, số điện thoại test và quota. Với Redis/RDS, kiểm tra TLS, connection pool, failover, timeout và driver version.

Unit test mock client chỉ xác nhận logic adapter. Integration test với account sandbox mới xác nhận credentials, network, IAM/RAM policy và API server thực tế.

### 10.3. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| **NoSuchMethodError** | Spring/SDK transitive version không tương thích | dependency tree, effective POM và BOM |
| **ClassNotFoundException** | Dependency thiếu hoặc javax/jakarta không khớp | Classpath, starter version và migration notes |
| ApplicationContext fail | Auto-configuration/property thay đổi | Startup condition report và release notes |
| Nacos registration fail | Namespace, endpoint, credentials, network hoặc client/server mismatch | Log Nacos, version matrix, RAM/ACL |
| OSS **AccessDenied** | RAM policy/bucket policy hoặc principal sai | Runtime credentials và resource ARN |
| OSS **SignatureDoesNotMatch** | AccessKey/STS token, region, endpoint, clock skew và signing version | Cấu hình SDK và đồng hồ máy |
| SDK timeout | VPC/public endpoint, DNS, firewall hoặc timeout quá ngắn | Network path và request ID |
| Credentials hết hạn | STS refresh, role trust policy, OIDC token và cache/provider lifecycle | Credentials provider và token expiry |
| Test local pass, staging fail | Credentials provider/region khác nhau | Principal/region không nhạy cảm và config profile |
| Build pass nhưng runtime lỗi | Compile không phủ hết reflection/auto-config/protocol | Spring context và integration tests |

## 11. Rubric ra quyết định: có nên dùng thư viện này?

Đánh giá từng tiêu chí theo ba mức: **Đạt**, **Cần kiểm chứng**, **Không đạt**.

| Tiêu chí | Đạt | Cần kiểm chứng | Không đạt |
| --- | --- | --- | --- |
| Maintainer | Có tổ chức/nhóm rõ và reviewer hoạt động | Một maintainer chính, phản hồi chưa ổn định | Không xác định được đơn vị chịu trách nhiệm |
| Release | Có GA release và changelog phù hợp | Release cũ nhưng có patch/PR | Không có artifact/release đáng tin cậy |
| Compatibility | Có matrix cho đúng Boot/Cloud/JDK | Chỉ tuyên bố chung, cần tự test | Không tương thích stack mục tiêu |
| Security | Có advisory/process và patch | Chưa rõ SLA hoặc phản hồi | Có lỗ hổng nghiêm trọng chưa xử lý |
| Dependency | BOM rõ, cây dependency hội tụ | Có override cần kiểm soát | Conflict major version không giải quyết được |
| Testing | Có CI và integration tests phù hợp | Chỉ có unit/samples | Không build/test được trên stack mục tiêu |
| Support | Có tài liệu/kênh escalation | Chỉ cộng đồng, SLA không rõ | Không có đường xử lý sự cố |

Đối với thư viện ít hoạt động, có thể vẫn sử dụng nếu API ổn định và tổ chức chấp nhận tự sở hữu adapter, fork hoặc duy trì bản vá. Tuy nhiên, phải tính chi phí bảo trì nội bộ và có kế hoạch thay thế nếu dependency trở thành rào cản nâng cấp.

## 12. Bài tập thực hành

**Bài tập:** đánh giá một ứng dụng Spring Boot sử dụng Nacos Discovery và OSS trước khi nâng cấp lên stack mới.

1. Ghi lại JDK, Spring Boot, Spring Cloud, SCA, Nacos client và OSS SDK hiện tại.
2. Tìm repository chính thức và đơn vị bảo trì của từng dependency.
3. Đọc release notes, supported branches, issue/PR và security advisories.
4. Đối chiếu ma trận SCA với Spring Boot/Spring Cloud mục tiêu.
5. Import BOM đúng và chạy **mvn help:effective-pom**, **mvn dependency:tree**.
6. Phát hiện version conflict và giải thích nguồn dependency kéo vào.
7. Nâng trên branch riêng, chạy context/discovery/OSS integration tests.
8. Viết báo cáo gồm lựa chọn version, rủi ro, kết quả test và rollback plan.

**Câu hỏi ôn tập:**

1. Vì sao repository owner không đồng nghĩa với đội hỗ trợ SLA?
2. Những bằng chứng nào cho thấy một nhánh thư viện đang được duy trì?
3. SCA BOM và Aliyun Spring Boot BOM quản lý những artifact nào?
4. Vì sao một version Spring Cloud được hỗ trợ chưa đủ chứng minh Nacos client hoặc OSS SDK cũng được hỗ trợ?
5. SCA 2025.0.x được FAQ liệt kê active nhưng Spring Cloud 2025.0 bị đánh dấu ngoài OSS support policy: cần giải thích sự khác biệt này thế nào?
6. Vì sao không dùng SCA branch hoặc PR chưa merge làm dependency production?
7. dependency:tree và effective-pom giúp phát hiện lỗi gì?
8. Khi nào nên dùng service starter cũ, và khi nào nên bọc SDK sản phẩm trực tiếp?
9. Một dependency ít maintainer có thể được chấp nhận nếu doanh nghiệp tự sở hữu fork trong trường hợp nào?
10. Những integration tests nào cần có trước khi nâng SCA?

## 13. Tài liệu tham khảo

- [Spring Cloud Alibaba — Release Notes](https://sca.aliyun.com/en/docs/2025.x/overview/version-explain/): ma trận SCA/Spring Cloud/Spring Boot và component versions.
- [Spring Cloud Alibaba — FAQ](https://sca.aliyun.com/en/docs/2025.x/overview/faq/): các nhánh SCA đang được duy trì và nơi tra cứu version.
- [Alibaba — Spring Cloud Alibaba repository](https://github.com/alibaba/spring-cloud-alibaba): source, branches, issues, releases và contributor activity.
- [SCA — PR #4429](https://github.com/alibaba/spring-cloud-alibaba/pull/4429): trạng thái nâng cấp Spring Boot 4.2/Spring Cloud 2026.0 tại thời điểm kiểm tra.
- [SCA — Issue #4400](https://github.com/alibaba/spring-cloud-alibaba/issues/4400): thảo luận về hỗ trợ stack mới và tình hình reviewer/committer.
- [Spring Cloud — Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions): chính sách hỗ trợ upstream và trạng thái release train.
- [Spring Cloud — Releases](https://github.com/spring-cloud/spring-cloud-release/releases): kiểm tra release GA và nội dung thay đổi.
- [Alibaba — Aliyun Spring Boot Starters](https://github.com/alibaba/aliyun-spring-boot): BOM, artifact, starter và phạm vi hỗ trợ công bố trong README.
- [Alibaba Cloud Java SDK](https://github.com/aliyun/alibabacloud-sdk): hoạt động và tài liệu SDK sản phẩm.
- [Alibaba Cloud SDK — Manage credentials](https://www.alibabacloud.com/help/en/sdk/developer-reference/v2-manage-access-credentials): credentials provider, RAM role, STS và OIDC.

**Kết quả mong đợi:** người học biết xác minh đơn vị bảo trì, đọc BOM và ma trận version từ nguồn chính thức, phân biệt trạng thái duy trì của SCA với vòng hỗ trợ upstream, kiểm tra dependency tree và nâng cấp Spring Boot/Spring Cloud/Alibaba Cloud integration có kiểm soát.
