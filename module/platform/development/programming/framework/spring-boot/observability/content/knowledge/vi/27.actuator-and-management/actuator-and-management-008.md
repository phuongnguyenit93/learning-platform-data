# Info endpoint trong Spring Boot

Khi vận hành một dịch vụ Spring Boot, đội hỗ trợ thường cần biết ứng dụng đang chạy phiên bản nào, artifact được build lúc nào, commit nào đã triển khai, service thuộc nhóm nào và tài liệu vận hành nằm ở đâu. Nếu thông tin chỉ nằm trong log khởi động hoặc phải truy cập từng container, việc xác minh deployment và xử lý sự cố sẽ chậm.

**Info endpoint** của Spring Boot Actuator cung cấp một điểm truy cập để công bố metadata mô tả ứng dụng. Endpoint thường được truy cập tại /actuator/info khi được bật và expose qua web. Dữ liệu có thể đến từ InfoContributor do Spring Boot cung cấp, build/git metadata được tạo trong quá trình build hoặc contributor tùy chỉnh.

Info endpoint phục vụ nhận diện và mô tả deployment; nó không phải endpoint kiểm tra khả năng phục vụ request. Health endpoint trả trạng thái sức khỏe theo health indicators, còn info endpoint trả thông tin do ứng dụng chủ động công bố. Không đưa secrets, thông tin cá nhân, credentials hoặc dữ liệu runtime nhạy cảm vào payload info.

Bài học thuộc chương **Actuator và management** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực. Bài này tập trung vào Info endpoint, nguồn metadata, cấu hình, bảo mật và cách sử dụng trong quy trình vận hành.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích mục đích của Actuator Info endpoint.
2. Phân biệt info với health, metrics và env endpoints.
3. Bật và expose info endpoint theo cấu hình Spring Boot.
4. Cung cấp metadata từ build information và Git information.
5. Tạo InfoContributor tùy chỉnh cho service metadata.
6. Hiểu management.info.* properties và cách bật contributor.
7. Thiết kế payload ổn định, hữu ích cho deployment identification.
8. Bảo vệ endpoint bằng exposure policy, authentication và network controls.
9. Kiểm thử output, contributor và behavior khi metadata thiếu.
10. Tích hợp info endpoint vào deployment verification và troubleshooting.

## 1. Info endpoint là gì?

Info endpoint là một Actuator endpoint cung cấp thông tin mô tả ứng dụng. Nó thường không thực hiện phép đo hoặc kiểm tra dependency; nội dung do các contributors cung cấp.

Response minh họa:

```json
{
  "app": {
    "name": "checkout-service",
    "description": "Checkout API",
    "version": "2.4.1"
  },
  "build": {
    "artifact": "checkout-service",
    "version": "2.4.1",
    "time": "2026-11-22T02:10:00Z"
  },
  "git": {
    "branch": "release/2.4",
    "commit": {
      "id": "a1b2c3d4",
      "time": "2026-11-22T01:55:00Z"
    }
  }
}
```

Đây là cấu trúc minh họa. Payload thực tế phụ thuộc contributor được bật và metadata có trong artifact. Không phải mọi ứng dụng đều có app/build/git sections.

### 1.1. Khi nào dùng Info endpoint?

- Xác minh phiên bản đang chạy sau deployment.
- Đối chiếu commit đã build với commit dự kiến.
- Hỗ trợ incident triage bằng metadata ổn định.
- Hiển thị service name, documentation link hoặc ownership metadata đã duyệt.
- Tự động hóa deployment smoke checks và inventory.

Info endpoint hữu ích cho metadata có vòng đời tương đối ổn định. Không dùng nó thay metrics, health checks hoặc truy vấn dữ liệu nghiệp vụ.

### 1.2. Info không phải Health

| Endpoint | Câu hỏi chính | Nội dung |
|---|---|---|
| /actuator/info | Ứng dụng là artifact/deployment nào? | Metadata do contributors công bố |
| /actuator/health | Ứng dụng có khỏe và sẵn sàng không? | Health status và components |
| /actuator/metrics | Có thể đo đại lượng nào? | Meter names, measurements và tags |
| /actuator/env | Property sources/config nào đang có? | Environment/configuration view có kiểm soát |

Ứng dụng có thể trả info thành công nhưng health DOWN; cũng có thể health UP dù info payload rỗng. Không dùng HTTP 200 từ info làm readiness check.

## 2. Bật Actuator và expose Info endpoint

Cần có Spring Boot Actuator dependency. Với Gradle:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
```

Endpoint availability và web exposure là hai khái niệm khác nhau. Endpoint phải được enable nếu bị disable trước đó, và cần được expose qua web nếu muốn truy cập HTTP.

Ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Nếu include đã được cấu hình ở nơi khác, hợp nhất danh sách theo policy ứng dụng. Không expose mọi endpoint chỉ để làm info hoạt động.

Truy cập:

```http
GET /actuator/info
```

Context path, management port và base path có thể làm URL thực tế khác ví dụ. Nếu management server dùng port riêng, endpoint có thể không nằm trên cổng ứng dụng chính.

### 2.1. Enablement và exposure

Có thể cấu hình access riêng:

```yaml
management:
  endpoint:
    info:
      access: read-only
```

Property semantics thay đổi theo Spring Boot version. Với version cũ hơn, endpoint access có thể được quản lý bằng enabled/enabled-by-default. Kiểm tra documentation đúng version. Exposure chỉ quyết định endpoint được công bố qua transport nào, không thay thế authorization.

### 2.2. Management port và base path

```yaml
management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
```

Khi đó endpoint ví dụ là /manage/info trên management port. Tách port không tự bảo vệ endpoint; vẫn cần firewall/network policy và authentication phù hợp.

## 3. InfoContributor architecture

Spring Boot xây dựng info response từ các InfoContributor. Mỗi contributor thêm một phần dữ liệu vào builder của Info endpoint.

| Nguồn | Nội dung | Cách có dữ liệu |
|---|---|---|
| Application contributor | Metadata do ứng dụng định nghĩa | Bean tùy chỉnh |
| Build info | Artifact, group, name, version, build time | Build plugin tạo build-info.properties |
| Git info | Branch, commit ID/time | Git properties file |
| Environment contributor | Property được chọn | management.info.env.* |
| Java/System info | Runtime/build-related data tùy contributor | Properties theo version |

Contributor có thể được auto-configure khi dependency và metadata resource hiện diện. Kiểm tra response thực tế thay vì giả định tất cả contributors luôn được đăng ký.

### 3.1. Tổng hợp nhiều contributors

Mỗi contributor ghi vào một section/key riêng. Tránh để nhiều contributor dùng cùng key root gây ghi đè hoặc cấu trúc khó hiểu. Dùng namespace rõ như app, build, git, runtime hoặc links.

### 3.2. Metadata nên ổn định

Info endpoint thường được polling bởi deployment tooling hoặc đọc thủ công. Giữ key names và semantics ổn định giữa releases. Nếu đổi schema, phối hợp consumer và automation.

## 4. Build information

Spring Boot Maven/Gradle plugin hỗ trợ tạo build info trong quá trình build; khi file hiện diện trên classpath, Actuator có thể công bố section build.

Gradle Kotlin DSL:

```kotlin
springBoot {
    buildInfo()
}
```

Gradle Groovy DSL:

```groovy
springBoot {
    buildInfo()
}
```

Cú pháp phụ thuộc Spring Boot Gradle plugin version và build script. Build info thường được sinh vào META-INF/build-info.properties trong artifact.

Thông tin thường gồm group, artifact, name, version, time và additional properties do build cấu hình.

### 4.1. Build time và reproducible builds

Build time hữu ích để xác định artifact, nhưng có thể làm artifact khác nhau giữa hai lần build dù source giống nhau. Với reproducible build, cân nhắc cách plugin tạo timestamp và policy pipeline. Không dùng build time làm bằng chứng duy nhất về source identity; kết hợp commit ID và artifact digest.

### 4.2. Version từ build metadata

Ưu tiên version do build system ghi vào artifact. Không suy version từ tên JAR hoặc environment variable tùy tiện nếu pipeline đã có metadata chính thức. Nếu version không được khai báo, có thể trả về giá trị không xác định hoặc bỏ field.

## 5. Git information

Spring Boot build plugins có thể tạo git properties file từ repository metadata, sau đó GitInfoContributor công bố thông tin. Với Gradle, cấu hình plugin/task tạo git properties tùy build setup. Với Maven, Git properties thường cần plugin hỗ trợ như git-commit-id plugin.

Git info có thể gồm branch, commit.id, commit.time và các field author tùy cấu hình.

### 5.1. Full commit ID hay abbreviated ID?

Full commit ID định danh chính xác hơn. Abbreviated ID dễ đọc hơn nhưng có thể mơ hồ trong repository lớn. Chọn format nhất quán theo deployment process.

### 5.2. Không công bố Git metadata nhạy cảm

Không cần công bố commit author email, nội dung commit, remote URL có embedded credentials hoặc branch names tiết lộ thông tin nội bộ cho người dùng công khai. Chỉ đưa field cần cho deployment verification và giới hạn audience.

### 5.3. Git metadata không thay artifact provenance

Commit ID cho biết source revision được ghi trong build metadata; nó không chứng minh artifact được build từ source đó một cách đáng tin cậy. Kết hợp signed build attestations, SBOM, artifact digest và CI provenance khi cần supply-chain verification.

## 6. Environment information contributor

Spring Boot có thể cung cấp EnvironmentInfoContributor để đưa properties được chọn vào info response. Cấu hình thường dùng prefix management.info.env.

Ví dụ:

```yaml
management:
  info:
    env:
      enabled: true
      prefix: "env"
      defaults:
        region: "ap-southeast-1"
        team: "commerce"
```

Property names và defaults support phụ thuộc Spring Boot version. Environment contributor có thể đọc properties được expose theo quy tắc của version; không có nghĩa toàn bộ environment được xuất ra.

### 6.1. Chỉ expose metadata đã allowlist

Không đưa toàn bộ application properties, environment variables hoặc system properties vào info. Chúng có thể chứa passwords, tokens, database URLs, internal hostnames hoặc secret references.

Ưu tiên custom InfoContributor với tập field cố định. Nếu dùng environment contributor, cấu hình allowlist cụ thể và test các trường nhạy cảm không xuất hiện.

## 7. Tạo custom InfoContributor

Khi cần metadata như service name, owner team, documentation link hoặc API compatibility, tạo bean InfoContributor.

```java
@Component
class ApplicationInfoContributor implements InfoContributor {

    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail("app", Map.of(
                "name", "checkout-service",
                "description", "Checkout API",
                "owner", "commerce-platform"
        ));
    }
}
```

Map.of yêu cầu Java 9 trở lên. Các giá trị minh họa có thể lấy từ configuration/build metadata, nhưng chỉ expose field đã duyệt.

### 7.1. Không thêm dữ liệu nhạy cảm

Không đưa credentials, tokens, private keys, database connection strings, customer data hoặc nội dung request vào Info endpoint. Info thường được truy cập bởi monitoring, deployment tooling và nhiều nhóm vận hành.

### 7.2. Contributor nhanh và không có side effects

InfoContributor được gọi khi endpoint tạo response. Không gọi database, remote API hoặc service nghiệp vụ từ contribute(). Việc đó làm endpoint chậm và phụ thuộc dependency. Metadata nên có sẵn trong memory/config/build resource.

### 7.3. Key naming và schema

Dùng key có ý nghĩa, ổn định và namespace rõ:

```json
{
  "app": {
    "name": "checkout-service",
    "owner": "commerce-platform"
  },
  "links": {
    "runbook": "https://docs.example.invalid/runbooks/checkout"
  }
}
```

URL là placeholder. Không đưa link nội bộ nếu audience của endpoint không có quyền truy cập tài liệu đó.

## 8. Info properties và contributor configuration

Các cấu hình management.info.* có thể bật/tắt hoặc điều chỉnh contributor theo Spring Boot version.

```yaml
management:
  info:
    build:
      enabled: true
    git:
      enabled: true
      mode: simple
    env:
      enabled: false
```

Tên property, default và git mode phụ thuộc version. Một số version hỗ trợ mode simple/full; full có thể công bố nhiều chi tiết hơn. Chỉ bật section cần thiết và hiểu rõ field output.

### 8.1. Configuration từ build plugin

Nếu build-info.properties hoặc git.properties không có trong artifact, contributor có thể không tạo section tương ứng. Kiểm tra file trong JAR/classpath của artifact đã deploy, không chỉ kiểm tra build script.

### 8.2. Profile-specific metadata

Tránh để info schema thay đổi mạnh theo profile. Nếu cần environment name như dev/staging/prod, dùng field đã chuẩn hóa. Không đưa profile-specific secrets hoặc toàn bộ active profiles nếu có thể tiết lộ topology.

## 9. Bảo mật Info endpoint

Info endpoint read-only nhưng metadata vẫn có thể giúp attacker fingerprint hệ thống: version, branch, commit, dependency hints và internal URLs.

- Chỉ expose endpoint cần thiết.
- Áp dụng authentication/authorization nếu payload chứa internal metadata.
- Giới hạn network access tới management port.
- Không công bố secrets hoặc config values nhạy cảm.
- Tránh Git details/author email nếu không cần.
- Không đưa internal runbook links cho audience công khai.
- Kiểm tra payload sau mỗi thay đổi contributor.
- Cân nhắc rate limiting và caching phù hợp.

### 9.1. Endpoint exposure không phải authorization

Cấu hình include=info chỉ bật web exposure. Spring Security hoặc management security policy vẫn cần quyết định ai được gọi endpoint. Nếu ứng dụng không có authentication, endpoint có thể công khai tùy deployment topology.

### 9.2. Management port riêng

Management port riêng tách traffic quản trị khỏi application traffic nhưng không thay firewall, Kubernetes NetworkPolicy, ingress rules hoặc authentication. Không bind management interface ra public network nếu không có controls.

### 9.3. Cẩn trọng với version disclosure

Version chính xác hữu ích cho deployment verification nhưng cũng giúp fingerprint dependency stack. Có thể chỉ công bố application version cho public audience và giữ commit details trong management network.

## 10. Info endpoint trong deployment verification

Pipeline có thể gọi info endpoint sau rollout và so sánh app.name, build.version, git.commit.id, environment/region và artifact build identifier.

Ví dụ kiểm tra thủ công:

```bash
curl -sS http://localhost:8080/actuator/info
```

Trong pipeline, parse JSON và so sánh field đã thống nhất. Nếu có nhiều replicas, gọi qua từng pod hoặc service discovery để xác nhận mọi instance đã cập nhật; load balancer có thể route nhiều lần tới cùng một instance.

### 10.1. Rollout và mixed versions

Trong rolling deployment, nhiều phiên bản có thể cùng tồn tại tạm thời. Info endpoint giúp phân biệt response từ replica nếu request đi trực tiếp tới instance hoặc metadata có instance identity đã chuẩn hóa.

### 10.2. Không thay deployment controller

Endpoint chỉ cung cấp metadata. Nó không tự biết rollout thành công theo policy, không điều khiển traffic và không thay readiness/liveness probes. Pipeline cần kết hợp health/readiness và replica inventory.

## 11. Kiểm thử InfoContributor và endpoint

### 11.1. Unit test contributor

Gọi contribute() với Info.Builder phù hợp và xác nhận key/value mong đợi. Test không có side effects và không gọi external services.

### 11.2. Integration test

Dùng Spring Boot test với web environment và Actuator endpoint, gọi /actuator/info. Assert HTTP status theo security policy, app/build/git sections khi contributor được bật và metadata có sẵn, custom fields đúng schema, field nhạy cảm không xuất hiện và contributor không ghi đè key không liên quan.

### 11.3. Test artifact đã build

Git/build metadata có thể tồn tại trong IDE test nhưng thiếu trong packaged artifact nếu build task không chạy. Test JAR cuối cùng hoặc smoke test container sau build để xác minh metadata được đóng gói.

### 11.4. Test security

Test anonymous và authenticated requests theo policy. Kiểm tra management port/network routing trong staging; endpoint read-only không đồng nghĩa public-safe.

## 12. Chẩn đoán Info endpoint

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| /actuator/info trả 404 | Endpoint không expose hoặc base path/port khác | Exposure, management port/base path |
| Response rỗng | Không có contributor hoặc metadata resource | Build/git files và custom beans |
| Thiếu build section | build-info.properties không được tạo/đóng gói | Build plugin và JAR contents |
| Thiếu git section | Git metadata task không chạy | git.properties trong artifact |
| Git section thiếu field | Mode/include policy | management.info.git settings/version |
| Custom key không xuất hiện | Bean không scan hoặc contribute sai | Application context và contributor test |
| Key bị ghi đè | Nhiều contributor dùng cùng key | Namespace và contributor inventory |
| Endpoint lộ secret | Environment contributor quá rộng/custom payload | Allowlist và response security test |
| Local có info, container không có | Artifact khác hoặc resource bị loại | Packaged JAR/container |
| HTTP 401/403 | Security policy yêu cầu quyền | Role/authority và management security |
| Pipeline thấy version cũ | Load balancer route tới replica cũ | Query từng instance/pod và rollout state |

### Quy trình điều tra

1. Xác định management port, base path và web exposure.
2. Kiểm tra endpoint access/enablement theo Spring Boot version.
3. Gọi info trực tiếp tới một instance.
4. Kiểm tra contributor beans được đăng ký.
5. Kiểm tra build-info/git properties trong artifact đã deploy.
6. Xác minh management.info.* và profile.
7. Kiểm tra response có key bị ghi đè hoặc thiếu.
8. Rà soát secrets/internal metadata trong payload.
9. Kiểm tra security và network policy.
10. So sánh từng replica nếu deployment đang rolling.

## 13. Các anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách phù hợp |
|---|---|---|
| Dùng info endpoint làm health check | Metadata không phản ánh readiness | Dùng health/readiness |
| Expose mọi Actuator endpoints | Tăng bề mặt tấn công | Allowlist endpoint cần thiết |
| Công bố toàn bộ environment | Lộ secrets/config nội bộ | Allowlist hoặc custom contributor |
| Contributor gọi database/HTTP | Info chậm và phụ thuộc dependency | Metadata build/config có sẵn |
| Đưa commit author email/internal URL công khai | Lộ thông tin nội bộ | Chỉ expose field cần thiết |
| Dùng build time làm source identity duy nhất | Không xác định source/artifact | Commit ID + artifact digest/provenance |
| Giả định mọi build có git.properties | Payload khác local và CI | Tạo/test metadata trong build |
| Key names thay đổi tùy profile | Automation khó tương thích | Schema ổn định |
| Coi management port riêng là đủ bảo mật | Endpoint vẫn có thể bị truy cập | Network policy + authentication |
| Dùng info để chứng minh mọi replica rollout | Load balancer có thể route lặp cùng pod | Kiểm tra từng instance |

## 14. Checklist production

1. **Purpose:** payload chỉ chứa metadata mô tả ứng dụng/deployment?
2. **Enablement:** endpoint được enable theo version và policy?
3. **Exposure:** chỉ expose info qua transport cần thiết?
4. **Security:** authentication/authorization và network controls phù hợp?
5. **Build:** build info được tạo trong pipeline?
6. **Git:** commit ID/branch/time cần thiết có trong artifact?
7. **Custom contributor:** keys ổn định, không gọi external dependency?
8. **Environment:** chỉ allowlist properties đã duyệt?
9. **Secrets:** không có passwords, tokens, credentials hoặc PII?
10. **Audience:** public/internal metadata được phân biệt?
11. **Schema:** key names và types ổn định giữa releases?
12. **Packaging:** metadata có trong artifact/container đã deploy?
13. **Testing:** unit, integration, packaged artifact và security tests?
14. **Deployment:** pipeline so sánh build/commit mong đợi?
15. **Replicas:** rollout verification kiểm tra đủ instances?
16. **Operations:** runbook giải thích cách đọc info và xử lý metadata thiếu?

## 15. Câu hỏi tự đánh giá

**Câu 1.** Info endpoint giải quyết nhu cầu gì?

**Gợi ý:** Cung cấp metadata nhận diện ứng dụng/artifact/deployment như app name, version, build và commit information.

**Câu 2.** Info endpoint khác health endpoint thế nào?

**Gợi ý:** Info mô tả metadata; health báo trạng thái sức khỏe của application/components.

**Câu 3.** Vì sao endpoint cần cả enablement và exposure?

**Gợi ý:** Enablement quyết định endpoint có hoạt động; exposure quyết định nó được công bố qua web/JMX hay transport khác.

**Câu 4.** Build info thường được tạo ở đâu?

**Gợi ý:** Trong build pipeline qua Spring Boot Maven/Gradle plugin và đóng gói thành metadata resource.

**Câu 5.** Git info giúp điều tra gì?

**Gợi ý:** Xác định branch/commit được ghi trong artifact đang chạy để đối chiếu deployment.

**Câu 6.** Vì sao không nên expose toàn bộ environment properties?

**Gợi ý:** Có thể chứa secrets, tokens, credentials và topology nội bộ.

**Câu 7.** Custom InfoContributor có nên gọi database không?

**Gợi ý:** Không. Contributor nên nhanh, không side effects và chỉ dùng metadata có sẵn.

**Câu 8.** Vì sao build metadata local có thể khác container production?

**Gợi ý:** Build task hoặc resource packaging trong pipeline có thể không tạo/đóng gói build-info/git properties.

**Câu 9.** HTTP 200 từ info endpoint có chứng minh service ready không?

**Gợi ý:** Không. Dùng health/readiness checks để đánh giá khả năng phục vụ.

**Câu 10.** Làm sao xác minh mọi replica đã deploy cùng version?

**Gợi ý:** Query metadata từng instance/pod hoặc deployment inventory; load balancer có thể route liên tục tới cùng replica.

## Kết luận

**Info endpoint cung cấp metadata ổn định để nhận diện ứng dụng và artifact đang chạy.** Spring Boot Actuator có thể tổng hợp build information, Git metadata, environment properties được chọn và dữ liệu từ custom InfoContributor. Hãy bật và expose endpoint có chủ đích, giữ schema nhất quán, chỉ công bố field cần thiết và bảo vệ management access. Dùng build/commit metadata hỗ trợ deployment verification, nhưng kết hợp health/readiness và kiểm tra từng replica để xác nhận rollout. Contributor nên nhanh, không gọi dependency bên ngoài và không làm lộ secrets hoặc thông tin nội bộ.
