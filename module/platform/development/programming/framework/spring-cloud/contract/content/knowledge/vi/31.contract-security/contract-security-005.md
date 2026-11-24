# Bảo vệ quyền đọc và ghi kho artifact

## 1. Vì sao kho artifact là một phần của bảo mật hợp đồng?

Trong **Spring Cloud Contract (SCC)**, producer và consumer thống nhất cách giao tiếp HTTP hoặc messaging qua **Groovy/YAML DSL**. Producer sử dụng **Contract Verifier** để sinh và chạy các bài kiểm thử xác minh implementation, tạo **stub artifact** và công bố chúng vào kho Maven tương thích (ví dụ Nexus hoặc Artifactory). Consumer dùng **Stub Runner** lấy đúng stub, khởi chạy HTTP stub hoặc mô phỏng thông điệp, rồi kiểm tra HTTP client/message handler của mình. CI giúp phát hiện thay đổi API không tương thích.

Nhưng chuỗi bằng chứng đó chỉ đáng tin khi **gói stub mà consumer tải thực sự là gói đã được producer kiểm tra và phát hành có thẩm quyền**.

Ví dụ:

```text
Producer:
  com.acme.billing:payment-service:1.4.2
  └─ payment-service-1.4.2-stubs.jar

Consumer:
  checkout-service
  └─ Stub Runner REMOTE
     └─ com.acme.billing:payment-service:1.4.2:stubs

Repository:
  https://repo.example.org/repository/maven-releases/
```

Nếu một người dùng consumer có cả **quyền ghi** vào `maven-releases`, họ có thể vô tình hoặc cố ý thay gói stub phiên bản đã công bố. Consumer CI sau đó có thể kiểm tra với **contract mô phỏng sai nguồn gốc**, dẫn đến false pass hoặc chặn nhầm release. Ngược lại, nếu producer CI không có quyền ghi tối thiểu phù hợp, quá trình phát hành stub bị gián đoạn.

**Chủ đề của bài:** thiết kế và vận hành cơ chế **phân quyền đọc/ghi kho artifact** để bảo vệ tính bí mật, toàn vẹn, nguồn gốc và tính sẵn sàng của hợp đồng. Đây là yêu cầu quản trị hạ tầng **bổ sung** cho tính năng kiểm thử của SCC, không phải SCC tự quản lý tài khoản hay ACL của Nexus/Artifactory.

### 1.1. Bạn sẽ học được gì?

1. Phân biệt **người đọc stub** và **người công bố stub** cùng các quyền tối thiểu.
2. Nhận diện boundary giữa repository, build tool, Stub Runner và consumer HTTP tests.
3. Cấu hình đọc/ghi qua Maven `settings.xml`, Gradle `maven-publish` và Stub Runner `REMOTE` với secret ngoài source.
4. Phân biệt `401/403/404` do quyền kho với `404` trả bởi HTTP stub.
5. Bảo vệ release artifact khỏi ghi đè, dependency confusion, nguồn không tin cậy, cache/mirror sai.
6. Thiết kế CI gates, token rotation, audit trail và quy trình thu hồi khi sự cố.
7. Xử lý trường hợp snapshot, môi trường phát triển, external partner và nhiều nhóm cùng tiêu thụ stubs.
8. Thực hành xây role matrix và kiểm thử cả đường thành công lẫn các đường **bị từ chối đúng chính sách**.

> **Nguyên tắc nền tảng:** Consumer cần **quyền đọc đúng gói stub**, không cần quyền triển khai/gỡ/xóa; producer release CI cần **quyền ghi có giới hạn**, không cần quản trị toàn kho.

## 2. Mô hình tin cậy: ai được làm gì?

Một hệ thống tối thiểu có bốn chủ thể:

- **Producer developer:** viết contract, sửa implementation, chạy producer verification local; không tự nhiên có quyền publish release.
- **Producer CI release identity:** tạo artifact từ commit/contract được duyệt, chạy tests và **publish** vào repository được chỉ định.
- **Consumer CI test identity:** **đọc** artifact đã phát hành, chạy Stub Runner với version đã chọn; không cần upload/delete.
- **Repository administrator:** tạo repository, policies, identities/roles, audit, retention và xử lý sự cố; không nên dùng tài khoản admin làm credential build mặc định.

```mermaid
flowchart LR
    DEV["Producer developer"] -->|PR + contract review| CI["Producer CI"]
    CI -->|Verify + package| JAR["Versioned -stubs.jar"]
    JAR -->|WRITE qua publish identity| REPO["Artifact repository"]
    CON["Consumer CI"] -->|READ qua test identity| REPO
    REPO -->|Stub JAR| RUN["SCC Stub Runner"]
    RUN -->|WireMock/message stubs| TEST["Consumer tests"]
    ADMIN["Repository admin"] -. "ACL, retention, audit" .-> REPO
```

Mũi tên **WRITE** và **READ** đại diện hai quyền khác nhau. CI runner có thể đồng thời chạy build và test, nhưng **credential phải được cấp theo job/stage và mục đích**; không nên phát token write vào mọi job chỉ để “đỡ cấu hình”.

### 2.1. Ma trận phân quyền mẫu

| Chủ thể | Đọc release stubs | Ghi release stubs | Đọc snapshot stubs | Ghi snapshot stubs | Xóa/ghi đè release | Quản trị ACL |
|---|---|---|---|---|---|---|
| Consumer CI | **Có** | Không | Khi cần | Không | Không | Không |
| Producer PR CI (untrusted code) | Theo nhu cầu | **Không** | Theo nhu cầu | Thường không | Không | Không |
| Producer release CI | Có | **Chỉ namespace được cấp** | Có | Theo policy | **Không** | Không |
| Producer development publisher | Có | Không | Có | Có thể trong namespace dev | Không | Không |
| Artifact admin | Theo nhiệm vụ | Theo nhiệm vụ | Theo nhiệm vụ | Theo nhiệm vụ | Chỉ theo quy trình ngoại lệ | **Có** |

Đây là **chính sách đề xuất**, không phải nhóm role mặc định của Nexus/Artifactory. Quyền cụ thể có thể biểu diễn bằng repository/path/namespace ACL, token scope, project role hoặc workload identity tùy sản phẩm.

**Nếu consumer chỉ đọc được artifact, họ vẫn có thể bị lừa bởi artifact bị thay thế** bởi publisher khác. Vì vậy phải bảo vệ cả write path và danh tính nguồn gốc, không chỉ khóa quyền consumer.

## 3. Những tài sản cần bảo vệ

| Tài sản | Ví dụ | Rủi ro nếu mất kiểm soát |
|---|---|---|
| Contract DSL | `contracts/payments/payment-captured.yml` | Kỳ vọng API bị thay đổi trái phép |
| Producer verification report | Generated tests cho P2 | Artifact không được xác minh nhưng bị gắn nhãn verified |
| Stub JAR | `payment-service-1.4.2-stubs.jar` | Mapping bị sửa, thêm response giả hoặc chứa dữ liệu nhạy cảm |
| Artifact metadata/POM | `payment-service-1.4.2.pom` | Consumer resolve nhầm bản hoặc kéo dependencies ngoài dự kiến |
| Repository URL/mirror | `maven-releases`, `maven-snapshots` | Stub đến từ kho không được duyệt |
| Read/write credentials | Username/token/OIDC identity | Rò rỉ, ghi đè, xem artifact không được phép |
| Consumer test configuration | Stub Runner `ids`/`repositoryRoot` | CI tải nhầm classifier/version hoặc dùng production URL |
| Audit/build provenance | Commit, test report, checksum, publisher identity | Không truy ra bản stub đã được dùng khi có sự cố |

### 3.1. Contract không phải nơi chứa bí mật thật

SCC stub artifact có thể chứa **request headers, body, path và response mẫu**. Vì thế contract chứa literal token, cookie, mật khẩu, email hoặc dữ liệu cá nhân thật có nguy cơ được đóng vào `-stubs.jar` rồi lan sang consumer machines hoặc kho artifact.

Ví dụ **không nên làm**:

```yaml
request:
  method: GET
  url: /api/payments/PAY-42
  headers:
    Authorization: "Bearer REAL_ACCESS_TOKEN_VALUE"
response:
  status: 200
```

Dùng **giá trị giả không có quyền truy cập thật**, matchers thích hợp hoặc fixture synthetic. Nếu contract cần chứng minh có header `Authorization`, mô tả cấu trúc/matcher theo DSL, không nhúng token production.

### 3.2. Stub JAR là artifact phát hành, không phải một file JSON vô hại

Gói `-stubs.jar` thường dùng để chạy mappings; nhưng dạng JAR/POM/metadata có thể tương tác với hệ thống build và dependency resolution. Việc tải từ repository sai, mirror không kiểm soát hoặc sử dụng POM kéo dependencies không tin cậy vẫn tạo **rủi ro supply chain**.

Không coi “chỉ là stub để test” là lý do tắt kiểm tra nguồn, xác thực hoặc nguyên tắc cấp quyền tối thiểu.

## 4. Tách ba vùng repository: development, release và bên ngoài

Một thiết kế kho Maven có thể phân tách:

```text
https://repo.example.org/repository/maven-snapshots/
  com/acme/billing/payment-service/1.5.0-SNAPSHOT/...

https://repo.example.org/repository/maven-releases/
  com/acme/billing/payment-service/1.4.2/...

https://repo.example.org/repository/maven-proxy/
  approved external dependencies...
```

**`maven-proxy` chỉ là tên minh họa**, không phải loại repo SCC quy định. Nexus/Artifactory có hosted, proxy, virtual/group repositories theo cách triển khai riêng.

### 4.1. Release repository

- Chỉ CI identity được duyệt có quyền **publish** vào namespace producer.
- Release artifacts nên **bất biến**: cấm overwrite/redeploy cùng GAV/version/classifier.
- Consumer được **read** các artifacts đã phát hành mà họ được phép sử dụng.
- Có audit logs, retention và backup phù hợp.
- Không cho anonymous write; anonymous read chỉ nếu dữ liệu được phép công khai theo chính sách.

### 4.2. Snapshot/development repository

- Hỗ trợ bản chưa final, ví dụ `1.5.0-SNAPSHOT`.
- Có thể cho developer/CI riêng publish trong namespace dev.
- Retention ngắn hơn, có rules dọn bản cũ.
- Consumer CI dùng snapshot cần ghi artifact thực tế/timestamp/checksum; không xem nó là bằng chứng release tái lập.
- **Không** dùng token snapshot publisher làm token release publisher.

### 4.3. Repository bên ngoài

Nếu consumer test tải từ kho của đối tác hoặc public repository, phải đánh giá chính sách trust:

- Host/domain và TLS certificate được chấp thuận.
- Artifact/group namespace xác định đúng nhà phát hành.
- Có cơ chế lock/pin version và integrity/provenance phù hợp.
- Không tự thêm repository không rõ nguồn khi resolver báo 404.
- Tránh gửi credential của kho nội bộ tới endpoint bên ngoài do thay URL/mirror.

## 5. Authentication, authorization, integrity và audit: bốn lớp khác nhau

**Authentication (AuthN)** trả lời **“Ai đang truy cập?”** Ví dụ CI job dùng token đã được cấp.

**Authorization (AuthZ)** trả lời **“Identity này được phép làm gì, trên repository/path nào?”** Ví dụ consumer CI có scope read-only.

**Integrity/provenance** trả lời **“Gói này có đúng nội dung và nguồn phát hành đã được xác minh?”** Ví dụ checksum, signature và build metadata liên kết source commit.

**Auditability** trả lời **“Ai đã tải/ghi/ghi đè/xóa artifact nào, lúc nào?”** Repository audit logs và CI release records.

Không đánh đồng:

- Token hợp lệ **không** có nghĩa nó được phép publish mọi groupId.
- HTTPS thành công **không** có nghĩa nội dung là artifact producer đã duyệt.
- Checksum được lưu cạnh artifact **không** tự xác minh tác giả nếu attacker sửa được cả JAR lẫn checksum.
- Producer verification PASS cho commit A **không** chứng minh JAR từ commit B.
- Consumer Stub Runner test xanh **không** xác minh credentials được cấp đúng quyền.

### 5.1. Zero trust không nghĩa là mọi thứ đều “public”

Consumer test có thể cần stub của nhiều producer khác nhau. Thay vì một token admin dùng cho tất cả:

- Cấp read grants theo **team, repository, namespace và môi trường**.
- Cấp write grants theo **producer namespace và release workflow**.
- Hạn chế quyền manage/delete/overwrite tối đa.
- Dùng identities riêng giữa PR, main branch, release tag và production deploy.
- Thu hồi quyền khi service hoặc pipeline bị ngừng sử dụng.

Đây là thực hành **least privilege**, đặc biệt quan trọng khi artifacts có thể ảnh hưởng quyết định phát hành.

## 6. Mô hình đe dọa thực tế của kho stub

| Tình huống | Hậu quả có thể | Lớp phòng vệ |
|---|---|---|
| Consumer token có write permission | CI consumer có thể thay stub producer | Role read-only, kiểm thử denied write |
| Token producer xuất hiện trong PR build | Pull request không tin cậy có thể lấy credential | Secret isolation, protected workflows |
| Artifact release có thể overwrite | “Version 1.4.2” trỏ tới hai nội dung khác nhau | Repository immutability |
| Stub JAR chứa token thật | Bí mật lan qua artifact và cache | Synthetic data, secret scanning |
| Download dùng HTTP cleartext | Credentials/content dễ bị lộ hoặc sửa | HTTPS + certificate validation |
| Resolver fallback public repo | Dependency confusion/namespace collision | Repository allowlist, mirrors/content filters |
| Không ghi build provenance | Không biết stub đến từ commit/test nào | Build metadata, checksum/signatures |
| Developer dùng admin token | Quyền quá rộng, khó revoke theo job | Scoped tokens/workload identity |
| Read credential lộ vào logs | Người ngoài tải artifacts không được phép | Masking, không log secret, rotation |
| 401/403 bị “sửa” bằng anonymous repo | Mất kiểm soát truy cập | Khắc phục role/credential đúng chỗ |
| Cache cũ giúp test vẫn xanh | Consumer test dùng bản chưa được kiểm tra cho release mới | Pin version, cache policy, log resolved artifact |
| Token hết hạn giữa publish | Artifact/POM có thể publish dở tùy repo | Retry có kiểm soát, kiểm tra trạng thái publication |
| Plugin/build dependency bị thay từ mirror lạ | Build producer có thể bị ảnh hưởng | Pin trusted plugins/repositories, verification |

### 6.1. Ví dụ kiểm tra quyền âm tính

Bên cạnh “producer publish thành công” và “consumer download thành công”, cần kiểm tra:

- Token `consumer-read` **không thể upload/delete** artifact.
- Token `producer-payment-publish` **không thể publish** vào namespace của `inventory-service`.
- PR CI không có credential release khi code từ nhánh chưa đáng tin.
- Release repository **từ chối redeploy** đúng một version đã tồn tại.
- Tài khoản đã thu hồi không còn tải/publish được, có lưu event audit.

**Không thực hiện phép thử xóa/ghi đè trên repository release thật** nếu chưa có môi trường test và quyền thử nghiệm. Dùng repository sandbox với artifact giả và policy tương đương để xác minh các trường hợp bị từ chối.

## 7. Stub Runner lấy artifact bằng cách nào?

SCC Stub Runner hỗ trợ ba chế độ thông dụng:

| Mode | Stub lấy từ đâu? | Kiểm soát bảo mật cần thiết |
|---|---|---|
| `CLASSPATH` | Stub JAR có trên test classpath | Dependency provenance, lock/verification, kiểm soát repository build tool |
| `LOCAL` | Local Maven repository, thường `~/.m2` | Ai có thể ghi vào local cache, tránh dùng artifact cũ |
| `REMOTE` | Maven-compatible repository, ví dụ Nexus/Artifactory | TLS, credentials, **read-only role**, pin version và audit |

**Không có chế độ nào đồng nghĩa “không cần bảo mật”.** `CLASSPATH` có thể nạp JAR từ dependency repository; `LOCAL` vẫn có rủi ro cache bị thay; `REMOTE` phụ thuộc ACL và network boundary.

### 7.1. Phân biệt artifact coordinates với URL producer

```text
Stub ID:
  com.acme.billing:payment-service:1.4.2:stubs

Repository root:
  https://repo.example.org/repository/maven-releases/

Stub HTTP server khi test chạy:
  http://localhost:<dynamic-port>

Producer API ở môi trường thật:
  https://payment-api.example.internal/
```

`repositoryRoot` là **nguồn để tải JAR**, không phải HTTP base URL của producer. Khi test, consumer phải gọi **Stub Runner's HTTP URL/port**, tránh vô tình gọi producer thật khi không tải được stubs.

### 7.2. Dùng version bất biến thay vì `+` cho release gate

```text
# Cố định để truy vết được:
com.acme.billing:payment-service:1.4.2:stubs

# Theo dõi tương thích với bản mới nhất:
com.acme.billing:payment-service:+:stubs
```

Dấu `+` của Stub Runner yêu cầu resolver chọn version mới nhất mà nguồn cho phép. Nó hữu ích với **job khám phá breaking changes** nhưng có thể thay đổi giữa hai lần chạy. Release CI nên pin version cụ thể hoặc ghi rõ resolved version, artifact checksum và provenance.

### 7.3. Không “fallback” sang repository yếu bảo mật

Nếu `REMOTE` không tải được artifact vì credential sai, **không** tự thêm một public Maven repo hoặc chuyển sang `LOCAL` để dùng cache bất kỳ rồi tuyên bố consumer tương thích. Cần sửa nguyên nhân: token, repository policy, namespace, version, classifier hay network.

## 8. Cấu hình consumer Stub Runner đọc bằng quyền tối thiểu

Ví dụ `application-contract-test.yml` cho **consumer CI**:

```yaml
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: REMOTE
        repository-root: "https://repo.example.org/repository/maven-releases/"
        ids:
          - "com.acme.billing:payment-service:1.4.2:stubs"
        username: "${STUB_REPO_READ_USER}"
        password: "${STUB_REPO_READ_TOKEN}"
        fail-on-no-stubs: true
```

Giải thích:

- `STUB_REPO_READ_USER` và `STUB_REPO_READ_TOKEN` chỉ là **tên biến môi trường**, được CI secret manager cấp khi chạy test.
- Tài khoản/token tương ứng chỉ có **quyền đọc** những artifacts cần thiết; không dùng release publisher token.
- Stub Runner nhận `repository-root`, `ids`, `username` và `password`; các tên property này có trong tài liệu SCC.
- `fail-on-no-stubs: true` giúp không âm thầm bỏ qua khi không tìm thấy gói bắt buộc. Đây **không phải** kiểm tra repository ACL đầy đủ.
- File YAML chứa **tham chiếu secret**, không chứa giá trị secret thực tế.

**Chú ý vận hành:** Cách khởi tạo Spring test context, active profile hoặc annotation `@AutoConfigureStubRunner` có thể ghi đè properties. Sau khi cấu hình, phải kiểm tra log không lộ token, đúng artifact được tải và HTTP client gọi đúng server stub.

### 8.1. Không đặt secret mặc định rỗng ở release CI

Cấu hình như:

```yaml
username: "${STUB_REPO_READ_USER:}"
password: "${STUB_REPO_READ_TOKEN:}"
```

có thể khiến build dùng chuỗi rỗng khi CI chưa cấp secret, dẫn đến lỗi khó phân biệt hoặc vô tình dùng anonymous access nếu repository cho phép. Trong pipeline bắt buộc xác thực, nên:

- Không cấp default rỗng cho các secret required.
- Kiểm tra sự hiện diện của biến môi trường **mà không in giá trị**.
- Fail trước khi chạy consumer test nếu token chưa được inject.
- Giữ log đủ để biết **missing credential** khác **artifact not found**.

### 8.2. Annotation là cấu hình thay thế, không phải kho chứa mật khẩu

```java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme.billing:payment-service:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.REMOTE,
    repositoryRoot = "https://repo.example.org/repository/maven-releases/"
)
class CheckoutContractTest {
    // Read credentials từ Spring test configuration/CI secrets.
}
```

**Không hard-code username/token vào Java source hoặc test annotation.** Khả năng kết hợp annotation và Spring properties phụ thuộc phiên bản và precedence; khi dùng cả hai, xác minh resolved configuration thực tế.

### 8.3. Consumer code vẫn phải được kiểm tra

Một test bảo mật repository thành công chỉ chứng minh **tải được stub**. Bài consumer contract testing vẫn phải gọi **PaymentHttpClient hoặc CheckoutService thật** với stub URL và assert status/body/error semantics đã thỏa thuận. Stub Runner read permission và behavior compatibility là **hai bằng chứng khác nhau**.


## 9. Producer Maven: công bố stub bằng write identity riêng

Bên producer, SCC Maven plugin có thể sinh tests, chuyển DSL thành stubs và đính kèm `-stubs.jar` vào artifact của module. Sau khi generated producer verification tests thực sự chạy, Maven `deploy` sẽ công bố các artifacts đã attach theo cấu hình.

**Phân biệt POM và credential:**

- `pom.xml` ghi **repository ID, URL và cấu hình publishing**.
- `settings.xml` thuộc **môi trường build** hoặc tệp được CI cấp, chứa **cách xác thực** tương ứng.
- Repository server quyết định **identity này có được ghi vào path/namespace cụ thể hay không**.

### 9.1. Khai báo đích công bố ở producer POM

Trích đoạn `pom.xml`:

```xml
<project>
    <!-- Các khai báo project, parent và plugin đã có -->
    <groupId>com.acme.billing</groupId>
    <artifactId>payment-service</artifactId>
    <version>1.4.2</version>

    <distributionManagement>
        <repository>
            <id>internal-releases</id>
            <url>
                https://repo.example.org/repository/maven-releases/
            </url>
        </repository>
        <snapshotRepository>
            <id>internal-snapshots</id>
            <url>
                https://repo.example.org/repository/maven-snapshots/
            </url>
        </snapshotRepository>
    </distributionManagement>
</project>
```

Đây là **trích đoạn giải thích**; không dán nguyên khối thành POM độc lập nếu dự án đã có cấu trúc `project` và `distributionManagement` khác. Cặp `repository.id`/`snapshotRepository.id` cần **trùng đúng với server id** trong settings dùng khi Maven `deploy`.

Nếu `payment-service` phát hành version `1.4.2` (release), Maven thường chọn `internal-releases`. Nếu version là `1.5.0-SNAPSHOT`, sử dụng `internal-snapshots` theo plugin/repository policy. Không cấu hình snapshot write token vào release job nếu không cần.

### 9.2. Maven `settings.xml` trong CI

CI cung cấp tệp settings trong **workspace bí mật** hoặc home tạm, với các placeholder môi trường:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>internal-releases</id>
            <username>${env.REPO_RELEASE_WRITE_USER}</username>
            <password>${env.REPO_RELEASE_WRITE_TOKEN}</password>
        </server>
        <server>
            <id>internal-snapshots</id>
            <username>${env.REPO_SNAPSHOT_WRITE_USER}</username>
            <password>${env.REPO_SNAPSHOT_WRITE_TOKEN}</password>
        </server>
    </servers>
</settings>
```

Maven hỗ trợ interpolation từ environment variables trong `settings.xml`. Đây là **tham chiếu runtime**, không có token thật. Những giá trị secret phải được hệ CI cấp và có scope khác nhau.

Những điểm cần chú ý:

- `<id>internal-releases</id>` **không phải username**; nó là khóa liên kết đến repository ID trong POM.
- Không commit `settings.xml` chứa token thật vào repository.
- Nếu CI tạo file settings chứa secret đã được render, phải hạn chế quyền đọc và xóa an toàn sau job.
- Không in nội dung `settings.xml`, `effective-settings` hoặc biến môi trường chứa secret vào log.
- Dùng `-s` để chỉ định tệp settings khi cần, nhưng **không truyền token trực tiếp trên CLI**.

Ví dụ lệnh build **sau khi CI cấp settings và credentials**:

```bash
./mvnw -s ci-settings.xml clean verify
./mvnw -s ci-settings.xml deploy
```

`ci-settings.xml` là **tên minh họa của file do CI cấp trong môi trường job**, không phải file cần tạo trong thư mục bài học này. Trong project thực tế, cần bảo đảm **deploy** có producer verification gate, không bị các flags `skipTests` hoặc plugin executions tùy chỉnh bỏ qua.

### 9.3. Maven server credentials không kiểm soát quyền được cấp

Cho dù Maven có thể xác thực bằng `internal-releases`, **repository ACL** vẫn phải giới hạn identity đó: publish vào `com/acme/billing/payment-service/**` hoặc namespace/hosted repository được phép, không được xóa mọi artifact.

**Không cấp quyền admin của Nexus/Artifactory để sửa lỗi `403 Forbidden`.** Hãy kiểm tra role scope, repository/path, phương thức upload được phép và chính sách immutable release.

### 9.4. Lưu ý về mã hóa mật khẩu Maven

Maven 3 có tính năng **password encryption** cho các `server` entries, nhưng tài liệu chính thức cảnh báo cơ chế Maven 3 có mức bảo vệ **obfuscation-grade**, không thay thế secret manager hoặc kiểm soát quyền file.

Vì vậy:

- Ưu tiên CI secret store/vault và short-lived credential khi hạ tầng hỗ trợ.
- Đừng xem giá trị `{...}` “đã mã hóa” trong `settings.xml` là an toàn để commit lên Git.
- Không đặt master password hoặc file `settings-security.xml` dùng chung cho mọi developer/job.
- Bảo vệ file settings và mọi nơi có thể chứa secret: cache, logs, artifacts và shell history.

## 10. Gradle producer: tách Maven publication khỏi thông tin xác thực

Với Gradle, SCC tạo task `verifierStubsJar` để đóng gói mappings/DSL, còn plugin `maven-publish` công bố **artifact đã khai báo trong publication**. Hai bước này cần được nối bằng build configuration.

Ví dụ `build.gradle` Groovy DSL của producer, **trích đoạn**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.cloud.contract' version 'REPLACE_WITH_SCC_VERSION'
    id 'maven-publish'
}

group = 'com.acme.billing'
version = '1.4.2'

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            // Stub artifact do Spring Cloud Contract sinh.
            artifact(tasks.named('verifierStubsJar'))
        }
    }

    repositories {
        maven {
            name = 'internalReleases'
            url = uri(
                'https://repo.example.org/repository/maven-releases/'
            )

            // Gradle lấy giá trị từ Gradle properties hoặc
            // các nguồn credential được quản lý tương ứng.
            credentials(PasswordCredentials)
        }
    }
}
```

Với repository name `internalReleases`, Gradle có thể tìm credential property names:

```text
internalReleasesUsername
internalReleasesPassword
```

Các property đó **không nên được lưu với giá trị thật trong `gradle.properties` được commit**. Có thể cấp thông qua CI secrets mapping vào Gradle project properties, hoặc dùng credential provider phù hợp với hạ tầng.

Ví dụ một cách cấp **không ghi giá trị vào source**:

```text
CI secret: REPO_RELEASE_WRITE_USER
    → Gradle property internalReleasesUsername

CI secret: REPO_RELEASE_WRITE_TOKEN
    → Gradle property internalReleasesPassword
```

Đây là **mô hình ánh xạ**, không phải các biến môi trường tự động được Gradle hiểu nếu chưa cấu hình. Nếu dùng Gradle project property environment convention, tên tương ứng có thể là `ORG_GRADLE_PROJECT_internalReleasesUsername` và `ORG_GRADLE_PROJECT_internalReleasesPassword`, tùy phiên bản/cách chạy.

### 10.1. Nếu muốn truy xuất environment variables tường minh

Một cách khác trong `publishing.repositories.maven`:

```groovy
credentials {
    username = providers.environmentVariable(
        'REPO_RELEASE_WRITE_USER').orNull
    password = providers.environmentVariable(
        'REPO_RELEASE_WRITE_TOKEN').orNull
}
```

**Chọn một cơ chế quản lý credential thống nhất**, không kết hợp nhiều nguồn khó kiểm tra precedence. Trong release CI, fail khi không có credential thay vì fallback sang anonymous publish, HTTP plaintext hoặc repository không kiểm soát.

### 10.2. Bắt producer verification chạy trước publication

Ví dụ:

```groovy
tasks.named('publish') {
    dependsOn(tasks.named('contractTest'))
}

tasks.named('publishToMavenLocal') {
    dependsOn(tasks.named('contractTest'))
}
```

`contractTest` là task kiểm thử producer của SCC Gradle plugin; phải thực sự chạy generated tests. `verifierStubsJar` chỉ tạo JAR, **không đồng nghĩa verification đã PASS**.

Cần kiểm tra **task graph của phiên bản plugin và release workflow thực**, vì một job có thể gọi publication task cụ thể chứ không gọi aggregate `publish`. Nếu muốn tránh đường đi vòng gate, đặt dependency/policy cho **mọi publish task được cấp write privilege**, hoặc chỉ cấp write token cho stage có kiểm tra bắt buộc.

### 10.3. Sự khác nhau giữa `publish` và `publishToMavenLocal`

- `publish`: công bố Maven publications đến repositories cấu hình.
- `publishToMavenLocal`: cài các publications vào local Maven repo của user/build agent.
- `verifierStubsJar`: chỉ tạo stub JAR; **không tự công bố**.
- `mavenLocal()` trong dependency repositories: giúp **đọc** local Maven artifacts; **không phải lệnh ghi**.

**Không dùng việc publish local thành công để chứng minh repository remote có ACL đúng**; hai đích khác nhau và có đường phân quyền khác nhau.

## 11. Phân quyền theo pipeline: PR, main, release và consumer CI

Một repo có thể có nhiều workflow, nhưng **không workflow nào cũng cần write token**.

| Pipeline | Nhiệm vụ | Credential được cấp |
|---|---|---|
| Producer pull request | Generate contracts, tests, test build | Read-only dependencies/stubs nếu cần; **không release write** |
| Producer main snapshot | Verification + publish snapshot nếu policy cho phép | Write chỉ vào snapshot repo/namespace |
| Producer release tag | Verify, package, attest/sign, publish | Write vào release repo/namespace đã duyệt |
| Consumer pull request | Download fixed stubs, chạy Stub Runner/tests | Read-only |
| Consumer release | Regression/compatibility matrix với stubs | Read-only |
| Repository maintenance | Retention, audit, key rotation | Admin identity chỉ trong workflow quản trị |

### 11.1. Untrusted PR code không được thấy token write

Build scripts và tests là mã có thể thực thi trong CI. Nếu pull request chưa được review mà có access đến write credential:

- Một thay đổi Gradle/Maven build script có thể làm lộ thông tin xác thực.
- Một dependency/plugin không được kiểm soát có thể truy cập môi trường runner.
- Một job bị sửa có thể publish artifacts trước khi producer verification hoàn tất.

**Không inject release write secrets vào jobs chạy code không tin cậy**, kể cả PR đến từ fork hoặc branch nội bộ chưa qua điều kiện protection tương ứng. Cần protected environments, approval gates và điều kiện branch/tag phù hợp.

### 11.2. Tách build và publish stage

Một pipeline an toàn có thể theo sơ đồ:

```mermaid
flowchart TD
    PR["PR/code change"] --> VERIFY["Producer verification: không có write token"]
    VERIFY --> QA{"Generated tests PASS và artifact hợp lệ?"}
    QA -- "Không" --> FAIL["Build fail, không cấp publish credential"]
    QA -- "Có" --> APPROVE["Protected release approval/tag"]
    APPROVE --> PUB["Publish stage: identity ghi có scope hẹp"]
    PUB --> REPO["Immutable Maven release repository"]
    REPO --> CON["Consumer CI: read-only identity"]
    CON --> TEST["Stub Runner + consumer tests"]
```

Một số CI nền tảng có thể cấp **short-lived federated credentials** theo OIDC/workload identity. Chỉ nên dùng khi repository hoặc token broker thực sự hỗ trợ và có chính sách ánh xạ identity/claims; SCC không tự cung cấp cơ chế này.

### 11.3. Không nhầm quyền publish artifact với quyền deploy ứng dụng

Tài khoản có quyền `mvn deploy` lên Maven repository **không nhất thiết** có quyền deploy container/app lên staging hoặc production. Hai workflow nên có identities và approvals riêng. Ngược lại, tài khoản dùng để deploy ứng dụng không cần tự động có quyền thay stub artifacts.

Đây là cơ sở để ngăn một sự cố ở consumer test runner lan sang nguồn contract artifact được dùng trong release.

## 12. Artifact immutability: gói đã phát hành không được biến đổi

Giả sử consumer C1 được test với:

```text
com.acme.billing:payment-service:1.4.2:stubs
SHA-256: <digest_of_approved_jar>
```

Nếu producer team publish lại `1.4.2-stubs.jar` với nội dung khác nhưng không tăng version:

- Một CI runner giữ cache cũ, runner khác tải bản mới.
- Cùng consumer commit có thể **PASS ở máy A, FAIL ở máy B**.
- Báo cáo “tested against 1.4.2” không đủ để tái lập.
- Attestation/test report ký cho artifact cũ có thể không còn ứng với file hiện tại.

**Release repository nên chặn redeploy/overwrite same coordinates** `groupId:artifactId:version:classifier`. Đó là policy repository, không phải cấu hình `@AutoConfigureStubRunner`.

### 12.1. Snapshot khác release

`1.5.0-SNAPSHOT` thường được thiết kế cho phát triển liên tục, có thể xuất bản nhiều builds và có timestamped snapshots tùy Maven repository. Đừng dùng snapshot mutable làm bằng chứng release lâu dài nếu không lưu resolved version/build metadata/checksum.

Khi cần kiểm tra một candidate:

- Tạo release candidate version rõ ràng (ví dụ `1.5.0-rc.1` theo quy ước tổ chức).
- Pin artifact trong consumer CI.
- Gắn artifact với source commit và test report.
- Chỉ phát hành release sau khi các CI gates bắt buộc đạt.

### 12.2. Xác minh integrity khác với kiểm tra authorization

**Checksum** giúp phát hiện nội dung khác digest đã biết; nếu attacker có quyền thay cả JAR lẫn checksum trong cùng kho, riêng checksum không chứng minh nguồn gốc.

**Digital signature/attestation** có thể nâng mức xác thực khi khóa ký, issuer và policy được quản trị độc lập. Một consumer/test pipeline cần **thực sự verify** signature/provenance theo trust policy; có file `.asc` cạnh JAR không tự làm mọi công cụ xác minh chữ ký.

**Repository access control** vẫn cần thiết ngay cả khi có signature, vì nó hạn chế ai có thể thay đổi metadata/artifacts hoặc làm gián đoạn phân phối.

## 13. Dependency confusion, repository mirrors và nguồn được phép

Một rủi ro supply chain là project yêu cầu `com.acme.billing:payment-service:1.4.2:stubs` nhưng resolver được phép tìm cả repository công khai và nội bộ mà không có chính sách nguồn rõ ràng.

Mục tiêu là bảo đảm **namespace nội bộ phải được phân giải từ repository nội bộ được duyệt**, không để một artifact giả cùng tọa độ ở nguồn khác được ưu tiên.

### 13.1. Kiểm soát đường phân giải

- Định nghĩa repository allowlist tại Maven settings/Gradle settings hoặc CI policy.
- Dùng repository mirror/virtual/group repository của tổ chức với routing rõ.
- Với Gradle, dùng `content`/`exclusiveContent` filters khi phù hợp để ràng buộc group nội bộ.
- Pin plugin/dependency versions và bảo vệ cả plugin repositories.
- Không bật `mavenLocal()` vô điều kiện trong release CI nếu local repo có thể chứa artifact không được kiểm chứng.
- Log resolved artifact location, version và checksum khi cần audit.

### 13.2. Một ví dụ Gradle content filter

```groovy
repositories {
    maven {
        url = uri(
            'https://repo.example.org/repository/maven-internal/'
        )
        content {
            includeGroupByRegex('com\\.acme\\..*')
        }
    }
    mavenCentral {
        content {
            excludeGroupByRegex('com\\.acme\\..*')
        }
    }
}
```

Ví dụ này minh họa **cách lọc group**, nhưng không tự chặn mọi đường truy cập khác nếu dự án còn khai báo repositories ở settings/plugin management/subprojects. Cần kiểm tra cấu hình resolution thực tế.

### 13.3. Không đổi sang URL HTTP thường để giải quyết lỗi TLS

Nếu Gradle/Maven báo lỗi certificate hoặc handshake, cần kiểm tra CA trust store, proxy/TLS interception được doanh nghiệp chấp thuận, hostname, certificate validity hoặc cấu hình repository. **Không dùng `allowInsecureProtocol=true` hay vô hiệu hóa kiểm tra SSL** cho kho chứa artifact/credentials quan trọng chỉ để build xanh.

## 14. Không để secret chảy vào artifact, cache và log

Một write token có thể lộ qua nhiều chỗ ngoài POM/build script:

- Shell command-line arguments và process listing.
- Gradle `--info`/`--debug` hoặc Maven `-X` nếu plugin/logging chưa mask dữ liệu phù hợp.
- CI environment dump, `printenv`, `env`, `set`, stack traces.
- Gradle configuration cache, build cache hoặc CI workspace artifacts.
- Container layers khi dùng `ARG`/`ENV` hoặc `RUN echo ...` lúc build image.
- File `settings.xml` được lưu lại như build artifact, PR attachment hoặc test report.
- Test fixtures/contract YAML chứa real token.
- Browser/dev tool/network trace vô tình chụp Authorization header.

### 14.1. Nguyên tắc truyền secret

1. Lấy secret qua hệ thống quản lý secret/CI secret store đã được phê duyệt.
2. Cấp **chỉ cho đúng job**, sau khi branch/protection điều kiện đạt.
3. Ưu tiên short-lived tokens, workload identity và scope hẹp khi repository hỗ trợ.
4. Không in giá trị secret, kể cả khi debug lỗi 401.
5. Không ghi vào output, Docker layers hoặc generated stub JAR.
6. Xóa/thu hồi secret theo lifecycle job; không lưu lâu trong shared runner.
7. Rotate và revoke ngay nếu nghi ngờ đã lộ.

### 14.2. Placeholder và giá trị thực

Một contract minh họa có thể dùng:

```yaml
request:
  method: GET
  url: /api/payments/PAY-42
  headers:
    Authorization: "Bearer TEST_TOKEN_NOT_VALID_OUTSIDE_TEST"
response:
  status: 200
```

Đây là **fixture giả không cấp quyền thật**. Nếu cần kiểm tra token presence/format nhưng không muốn pin giá trị, dùng `request.matchers` của SCC hoặc matcher DSL thích hợp theo version. Đừng kiểm tra bằng cách dùng lại token thật của production.

### 14.3. Quét trước khi publish

Một CI policy có thể quét:

- Contract source, generated mappings và test resources.
- Stub JAR contents trước publish.
- Build logs/artifacts không chứa token/password/cookie nhạy cảm.
- Maven POM/Gradle published metadata không có URL nhúng credentials.

Secret scanning không hoàn hảo; vẫn cần review và nguyên tắc dữ liệu synthetic.

## 15. Audit, rotation và thu hồi quyền

**Một quyền đã cấp không nên tồn tại vô thời hạn.** Security review định kỳ nên đối chiếu:

- Danh sách **service identities** có read/write trên từng repository/namespace.
- Identity nào đã lâu không sử dụng, service nào đã ngừng.
- Có tài khoản con người dùng chung với CI không.
- Có write quyền vượt phạm vi team không.
- Có quyền delete/overwrite release không.
- Credentials có hết hạn/rotation policy và owner rõ ràng không.
- Log ghi lại package/version/classifier, action, identity, thời điểm, kết quả và địa chỉ nguồn phù hợp chính sách không.

### 15.1. Khi nghi ngờ publish token bị lộ

Một quy trình ứng phó mức cao:

1. **Thu hồi/disable token** hoặc revoke workload identity bị ảnh hưởng.
2. Dừng publish từ job/identity liên quan, bảo vệ artifacts chưa kiểm chứng.
3. Kiểm tra audit logs các thao tác write/delete/overwrite gần đây.
4. Đối chiếu published artifacts với build provenance/checksum/signature được lưu ở nguồn tin cậy khác.
5. Nếu có artifact đáng ngờ, cách ly hoặc đánh dấu bị thu hồi theo policy; thông báo những consumer đã tải nó.
6. Cấp credential mới với scope tối thiểu cho pipeline đã được sửa.
7. Chạy lại producer verification và consumer matrix bằng artifact đã xác minh.
8. Lưu incident report, phạm vi ảnh hưởng và các hành động phòng ngừa.

**Đừng chỉ đổi mật khẩu rồi kết luận artifact trong kho chắc chắn an toàn.** Nếu token có write quyền, cần kiểm tra integrity của những bản đã tồn tại trong khoảng thời gian có thể bị ảnh hưởng.

### 15.2. Khi read token bị lộ

Rủi ro trọng tâm là **xem/tải artifacts không được phép**. Thu hồi token, xem log download, đánh giá mức độ nhạy cảm của stubs và thông báo theo chính sách dữ liệu. Không giả định stub “chỉ dành cho test” chắc chắn không có thông tin cần bảo vệ.

### 15.3. Rotation không nên làm mọi consumer CI ngừng hoạt động

Khi rotate:

- Chuẩn bị credential mới và mapping secret store.
- Xác minh read-only access trong sandbox/job kiểm tra.
- Cập nhật các workflow được phép sử dụng.
- Thu hồi credential cũ theo cửa sổ chuyển đổi được quản lý.
- Xác nhận các jobs không còn dùng token cũ và audit không xuất hiện truy cập bất thường.

Không làm một token dùng chung cho mọi producer và consumer chỉ để rotation “dễ hơn”. Việc tách identities theo role giúp giảm blast radius.


## 16. Phân biệt lỗi repository với lỗi HTTP contract

Trong consumer testing, có **hai đường HTTP hoàn toàn khác nhau**:

1. **Repository HTTP:** Stub Runner dùng HTTP(S) để tải `payment-service-1.4.2-stubs.jar` từ kho artifact.
2. **Stub API HTTP:** PaymentHttpClient của ứng dụng consumer gọi WireMock stub tại `localhost:<port>` và nhận `200`, `404`, `409` ... theo contract.

```mermaid
flowchart TD
    C["Consumer test"] --> SR["Stub Runner"]
    SR -->|"HTTPS: resolve artifact"| REPO["Maven repository"]
    REPO -->|"JAR mappings"| SR
    SR --> W["WireMock HTTP server"]
    C --> PC["PaymentHttpClient thật"]
    PC -->|"HTTP: /api/payments/PAY-42"| W
    W -->|"200/404/409 theo mapping"| PC
```

Nếu repository từ chối tải JAR, **client chưa có stub nào để gọi**. Đừng vội chỉnh `response.status: 404` trong YAML contract.

### 16.1. Bảng mã lỗi cần đọc theo đúng đường

| Triệu chứng | Nằm ở đâu? | Phân tích đầu tiên |
|---|---|---|
| Repository **401 Unauthorized** | Tải artifact | Thiếu/không hợp lệ credential, token hết hạn |
| Repository **403 Forbidden** | Tải/publish artifact | Identity có xác thực nhưng thiếu quyền path/action |
| Repository **404 Not Found** | Tải artifact | GAV/classifier/version sai; cũng có kho **ẩn sự tồn tại** với user không đủ quyền |
| Repository **409 Conflict** | Publish artifact | Duplicate version, immutable repo hoặc metadata conflict tùy sản phẩm |
| Repository **429 Too Many Requests** | Download/publish | Rate limit, quá nhiều CI jobs, policy của kho |
| TLS/certificate error | Kết nối kho | Trust store, CA, hostname, proxy |
| Stub Runner **no stubs found** | Nạp JAR/mappings | Thiếu artifact, layout sai hoặc không có contract |
| WireMock **404** sau khi stub đã chạy | Client → stub | Không khớp request mapping **hoặc** contract trả 404 nghiệp vụ |
| Consumer **401/403** từ WireMock | Client → stub | Hành vi auth contract hoặc mapping test, không phải quyền Maven |
| Maven/Gradle plugin resolution fail | Build-tool repository | Build plugin dependencies, khác Stub Runner JAR resolution |

**Không suy rằng repository 404 luôn có nghĩa artifact không tồn tại.** Một số repository managers có thể trả 404 thay 403 để tránh lộ thông tin artifact; cần kiểm tra policy và audit logs với đúng role.

### 16.2. Quy trình debug không làm lộ secret

**Bước A — Xác định đường bị lỗi:** producer publish, consumer download, hay consumer gọi WireMock stub?

**Bước B — Xác định tọa độ và repository:** groupId, artifactId, version, classifier, URL host/repository *không chứa credentials*.

**Bước C — Xác định identity (không in token):** read/write role nào được cấp cho job? Đúng namespace và thời hạn?

**Bước D — Xác minh artifact metadata:** file/POM/classifier đã có, trạng thái release immutable, logs upload/download.

**Bước E — Chỉ sau khi tải và nạp stubs thành công**, kiểm tra WireMock mappings, HTTP port và consumer behavior.

### 16.3. Không dùng quyền admin để “xác định lỗi cho nhanh”

Nếu read-only token bị 403, thử bằng admin token có thể xác nhận rằng một tài khoản nhiều quyền hơn đọc được — nhưng **không giải thích chính sách role nào bị sai** và có thể lộ quyền admin vào runner. Hãy kiểm tra repository ACL/audit bằng kênh quản trị riêng hoặc dùng **sandbox test identity** đã được tạo cho chẩn đoán.

## 17. CI bảo vệ cả kiểm thử và công bố artifact

Một bài consumer test chỉ đáng tin khi pipeline đã kết nối các bằng chứng:

1. Contracts đã được review theo đúng consumer needs.
2. Producer verification đã **sinh và chạy tests thật**, có test report.
3. Stub artifact được đóng gói với version/classifier, không chứa secret thật.
4. Repository chấp nhận publish **chỉ từ identity được phép**.
5. Artifacts release không bị ghi đè sau khi công bố.
6. Consumer có thể **chỉ đọc** artifact cụ thể và Stub Runner nạp đúng mappings.
7. Consumer tests gọi client code thật và assert hành vi cần thiết.
8. Audit/provenance đủ để tái lập và điều tra regression.

### 17.1. Mô hình pipeline tổng thể

```mermaid
sequenceDiagram
    participant P as Producer CI - no write secret
    participant V as Verification gate
    participant PUB as Protected publish job
    participant R as Artifact repository
    participant C as Consumer CI - read-only

    P->>V: Generate + execute contract tests
    V-->>P: PASS/FAIL + report
    P->>V: Scan stub JAR + provenance
    V-->>PUB: Approved artifact + release metadata
    PUB->>R: Publish exact version with scoped credential
    R-->>PUB: Accepted + artifact identity
    C->>R: Read pinned group:artifact:version:stubs
    R-->>C: Stub JAR
    C->>C: Stub Runner + consumer code tests
```

**Đây là một kiến trúc CI tham khảo**, không phải workflow SCC tự sinh. Việc tách build và publish stages cần bảo đảm **artifact được publish chính là artifact đã được kiểm tra**; nếu publish job rebuild từ source khác commit, tính liên kết test→release không còn được bảo đảm.

### 17.2. Cổng bảo vệ publication

| Gate | Điều kiện đạt |
|---|---|
| Branch/commit protection | Chỉ release tag/commit đã được duyệt có thể yêu cầu publish |
| Producer contract tests | Không bị skip; số test thực chạy như kỳ vọng |
| Stub packaging | Có đúng mappings/contracts/classifier |
| Secret scan | Không có credential/dữ liệu nhạy cảm thật trong artifact |
| Artifact identity | GAV/version/classifier trùng với release metadata |
| Repository authorization | Write identity chỉ vào namespace/repo được phép |
| Immutability | Không thể ghi đè release coordinates đã tồn tại |
| Consumer read | Read identity nạp được đúng stub, không có write |
| Consumer compatibility | HTTP/message client tests chạy qua Stub Runner |
| Auditability | Có trace từ commit và test report tới artifact đã phân phối |

Không cần mỗi gate là một ứng dụng riêng, nhưng **bỏ một gate cần là quyết định có lý do**, không phải do pipeline không hiển thị thất bại.

### 17.3. “Publish successful” chưa chứng minh consumer đã đọc được

Producer CI có thể upload artifact thành công, nhưng consumer CI vẫn 401/403 vì thiếu quyền read, bị chặn route hoặc namespace ACL khác. Sau publish, nên thực hiện **read-side smoke test** bằng **consumer-like identity** trong môi trường phù hợp.

Ngược lại, consumer read được JAR không chứng minh producer verification đã pass nếu publisher không có release gate. Hãy giữ hai lớp bằng chứng riêng.

## 18. Khi nào dùng kho công khai, kho nội bộ hoặc kho riêng cho đối tác?

Không phải mọi stub đều có cùng độ nhạy cảm.

| Loại contract/stub | Chính sách thường phù hợp |
|---|---|
| API công khai, toàn bộ payload dùng dữ liệu synthetic | Có thể công bố công khai sau security review và license policy |
| API nội bộ giữa các microservices | Hosted repository chỉ read cho identities được cấp |
| API dùng schema nghiệp vụ nhạy cảm | Giới hạn theo team/project; kiểm tra thông tin tiết lộ trong mappings |
| API đối tác | Repository/namespace riêng, token read có phạm vi/expiry, lịch rotation |
| Contracts có dữ liệu đặc biệt nhạy cảm | Trước tiên **loại bỏ dữ liệu nhạy cảm**; ACL không thay redaction |

**Không dùng repository private như một lý do để nhúng token thật** hoặc copy production payload vào contract. Dữ liệu trong `-stubs.jar` có thể được cache/download/đưa vào test reports và logs ở nhiều máy.

### 18.1. Đối tác chỉ được đọc, không được publish bản của producer

Nếu một đối tác cần kiểm tra client với stub:

- Cung cấp artifact version đã được duyệt qua repository/download channel phù hợp.
- Cấp read credentials scoped theo artifact/repo nếu cần.
- Không cấp write/delete dù đối tác chỉ “muốn upload lại file khi test lỗi”.
- Khi đối tác đề xuất contract mới, dùng quy trình PR/review/contract proposal; producer sẽ verify và publish stub của mình.

Bảo vệ publisher identity giúp giữ ranh giới trách nhiệm ai **được cam kết hành vi API nào**.

## 19. Đào tạo quyền qua “positive” và “negative” tests

Một hệ thống bảo mật tốt không chỉ kiểm tra hành động được phép thành công, mà còn xác minh hành động **không được phép bị từ chối**.

### 19.1. Kịch bản kiểm thử trong sandbox

Tạo repository thử nghiệm **không chứa artifacts production**, với identities và ACL tương tự:

```text
Repo sandbox:
  maven-sandbox-releases

Identity A: payment-publisher
  allow: read/write namespace com.acme.billing
  deny: delete/overwrite release, write com.acme.catalog

Identity B: checkout-consumer
  allow: read com.acme.billing
  deny: write/delete

Identity C: unauthenticated
  allow: none (nếu private repo)
```

Kịch bản cần chạy bằng tool/client được chính tổ chức cho phép:

| Bước | Ai thực hiện | Thao tác | Kết quả kỳ vọng |
|---|---|---|---|
| 1 | Payment publisher | Upload stub `1.4.2` trong namespace được cấp | **ALLOW** |
| 2 | Checkout consumer | Download cùng gói | **ALLOW** |
| 3 | Checkout consumer | Thử publish gói **giả trong sandbox** | **DENY** |
| 4 | Payment publisher | Upload vào namespace inventory | **DENY** |
| 5 | Payment publisher | Redeploy cùng release version | **DENY** |
| 6 | Anonymous client | Đọc gói private | **DENY** |
| 7 | Revoked identity | Đọc/gửi artifact sau revoke | **DENY** |

**Không hướng dẫn hay thực hiện xóa/ghi đè artifact production để test ACL.** Các negative tests phải chạy trong sandbox có cho phép và hoàn toàn dùng dữ liệu giả.

### 19.2. Các giới hạn của test quyền

- Một negative test DENY không thay security audit tổng thể của repository.
- ACL có thể khác khi dùng virtual/group repository so với hosted repository.
- Token có thể còn hiệu lực trong khoảng propagation delay sau revoke.
- Read permission theo group có thể thay đổi khi thêm Maven mirror.
- Test phải ghi **identity class/action/path/result**, không ghi secret.

## 20. Bài tập thực hành: phân quyền cho payment và inventory stubs

### 20.1. Bối cảnh

Một tổ chức có hai producer và một consumer:

| Service | Tọa độ stub | Vai trò |
|---|---|---|
| `payment-service` | `com.acme.billing:payment-service:2.3.1:stubs` | Producer thanh toán |
| `inventory-service` | `com.acme.catalog:inventory-service:4.0.0:stubs` | Producer kho |
| `checkout-service` | Cần đọc cả hai artifacts | Consumer dùng Stub Runner |

Repositories:

```text
https://repo.example.org/repository/maven-releases/
https://repo.example.org/repository/maven-snapshots/
```

Ba identities cần thiết:

```text
payment-release-publisher
inventory-release-publisher
checkout-consumer-reader
```

### 20.2. Nhiệm vụ

1. Lập role matrix read/write/delete/overwrite/admin cho ba identities và hai namespaces.
2. Giải thích vì sao `checkout-consumer-reader` không cần write token.
3. Thiết kế producer CI release stage chỉ cấp `payment-release-publisher` sau khi generated producer tests PASS.
4. Viết `distributionManagement` ở `payment-service/pom.xml` và `settings.xml` dùng **environment references**, không chứa token thật.
5. Viết `publishing.repositories.maven` cho Gradle producer có publisher credentials được cấp từ CI.
6. Viết `application-contract-test.yml` để Stub Runner đọc **cả hai stub artifacts** qua `REMOTE`.
7. Nêu cách bảo đảm checkout HTTP client thật gọi đúng WireMock ports, không gọi producer production.
8. Thiết kế sandbox negative tests: consumer write bị từ chối, payment publisher ghi namespace inventory bị từ chối, redeploy release bị từ chối.
9. Giải thích khác nhau giữa repository `403` và WireMock `404`.
10. Nếu token publisher bị lộ, lập các bước revoke, audit, đối chiếu artifact integrity và khôi phục CI.
11. Nếu cùng version stub có hai checksums ở hai runners, giải thích rủi ro và policy sửa.
12. Chỉ ra cách CI lưu commit, test report, GAV/classifier, checksum, publisher identity và consumer test result.
13. Đề xuất giới hạn quyền cho external partner chỉ cần đọc một artifact.
14. Nêu cách ngăn PR CI không tin cậy lấy token release.
15. Giải thích vì sao một artifact checksum được tải từ cùng kho không đủ xác minh publisher identity nếu kho đó có thể bị sửa cả JAR lẫn checksum.

### 20.3. Gợi ý consumer YAML

```yaml
spring:
  cloud:
    contract:
      stubrunner:
        stubs-mode: REMOTE
        repository-root: "https://repo.example.org/repository/maven-releases/"
        ids:
          - "com.acme.billing:payment-service:2.3.1:stubs"
          - "com.acme.catalog:inventory-service:4.0.0:stubs"
        username: "${STUB_REPO_READ_USER}"
        password: "${STUB_REPO_READ_TOKEN}"
        fail-on-no-stubs: true
```

Đây là **cấu hình mẫu** cho trường hợp read identity được cấp quyền tải cả hai namespace. Nếu tổ chức không cho một identity đọc cả hai, phải thiết kế repository access/CI test jobs phù hợp; không đặt hai username/password vào cùng một Stub Runner config rồi giả định nó tự chọn theo từng artifact.

### 20.4. Gợi ý rule kiểm tra token

```text
ALLOW payment-release-publisher:
  upload com/acme/billing/** to releases
DENY payment-release-publisher:
  upload com/acme/catalog/**, delete/overwrite releases

ALLOW inventory-release-publisher:
  upload com/acme/catalog/** to releases
DENY inventory-release-publisher:
  upload com/acme/billing/**, delete/overwrite releases

ALLOW checkout-consumer-reader:
  read approved billing/catalog stubs
DENY checkout-consumer-reader:
  upload/delete/overwrite any artifact

DENY untrusted pull request:
  access release write credential
```

**Đây là policy pseudocode**, không phải cú pháp ACL có thể dán nguyên vào Nexus hoặc Artifactory. Người triển khai cần ánh xạ nó sang quyền cụ thể của sản phẩm repository, đặc biệt khi artifact path/classifier không thể được phân biệt chỉ bằng group-level role.

### 20.5. Tiêu chí tự đánh giá

Một bài hoàn thành đạt khi:

- Read/write identities được tách rõ và chỉ có quyền tối thiểu.
- Đường publish chỉ nhận gói sau producer verification gate.
- Consumer dùng `REMOTE`, pin version, không có fallback insecure.
- Secrets không xuất hiện trong source, logs, artifact hay CI cache.
- Sandbox DENY tests chứng minh consumer không có write.
- Artifact không thể overwrite cùng release coordinates.
- Có test bảo đảm chỉ stub đã được verify mới được công bố.
- CI có audit/provenance và phương án revoke/rotate.
- Người học phân biệt được **quyền truy cập repository** với **hành vi HTTP API trong contract**.

## 21. Checklist trước khi merge, publish hoặc cấp quyền

- [ ] Contract sử dụng dữ liệu synthetic; không chứa token/cookie/password thật.
- [ ] Producer verification tests thực sự chạy, không bị skip hoặc có `0 tests` ngoài chủ đích.
- [ ] Stub JAR và POM có version/classifier đúng, mapping/DSL đúng layout.
- [ ] Mọi artifact release có nguồn gốc từ commit/build đã được kiểm tra.
- [ ] Repository URL nằm trong allowlist và dùng HTTPS với certificate validation.
- [ ] Release và snapshot repositories có quyền/quy tắc khác nhau.
- [ ] Không có anonymous **write**; anonymous read chỉ khi đã cho phép dữ liệu public.
- [ ] Consumer CI dùng read-only identity, không có release write secret.
- [ ] Producer release publisher chỉ ghi vào namespace/repository được cấp.
- [ ] PR CI không được truy cập token release.
- [ ] Tokens được cấp qua CI secrets/vault, không hard-code vào POM/Gradle/YAML.
- [ ] File settings/Gradle cache/logs không phát tán credentials.
- [ ] Không cấp repository admin cho build jobs chỉ để sửa lỗi 401/403.
- [ ] Repository không cho redeploy/overwrite release coordinates bất biến.
- [ ] CI có kiểm tra checksum/signature/provenance theo mức rủi ro.
- [ ] Internal group namespace không tự resolve từ public repositories không tin cậy.
- [ ] Consumer Stub Runner `ids` pin version, `repositoryRoot` đúng, `failOnNoStubs` không bị tắt vô cớ.
- [ ] Consumer HTTP client thật gọi WireMock stub URL, không gọi producer thật.
- [ ] Quyền READ/WRITE/DENY được kiểm tra trong sandbox.
- [ ] Audit logs ghi thao tác và identity theo policy, không chứa secret.
- [ ] Có owner/token expiry/rotation plan, quy trình revoke và incident response.
- [ ] Không xóa artifact release lịch sử ngoài retention policy có phê duyệt.
- [ ] External partner chỉ có quyền đọc những artifacts được phép chia sẻ.
- [ ] Các lỗi repository auth được phân loại khác lỗi HTTP contract.
- [ ] Có test report và provenance đủ để tái lập một consumer compatibility run.

## 22. Ghi nhớ và tài liệu tham khảo

**Bảo vệ quyền đọc và ghi kho artifact** là bảo vệ **chuỗi tin cậy từ contract của producer đến stub mà consumer thực sự chạy**.

- SCC tạo producer tests, mappings và stubs, nhưng **không tự cấp ACL** cho Nexus/Artifactory.
- **Producer publisher** cần write privilege hẹp và chỉ khi CI verification đã đạt.
- **Consumer Stub Runner** cần read privilege tối thiểu để tải đúng `groupId:artifactId:version:stubs`.
- Maven `distributionManagement`/`settings.xml` và Gradle `maven-publish`/credentials giúp tích hợp **repository authentication**, không thay thế authorization policy của repository.
- **Release immutability, TLS, provenance, secret management, audit và rotation** giúp giảm nguy cơ gói stub bị thay hoặc credential bị lộ.
- Consumer test PASS chỉ có giá trị trong phạm vi stub artifact thực sự được tải; cần biết version, checksum và các generated producer tests đã xác minh gói đó.
- **Repository error `401/403/404` khác HTTP status của WireMock stub** trong kiểm thử business contract.

### Tài liệu chính thức

- [Spring Cloud Contract — Stub Runner Core: CLASSPATH, LOCAL, REMOTE và tải JAR](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-core.html).
- [Spring Cloud Contract — Stub Runner Common Properties: username, password, repositoryRoot, IDs](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html).
- [Spring Cloud Contract — Configuration Properties: fail-on-no-stubs và các tùy chọn](https://docs.spring.io/spring-cloud-contract/reference/configprops.html).
- [Spring Cloud Contract — Maven Project và producer verifier](https://docs.spring.io/spring-cloud-contract/reference/maven-project.html).
- [Spring Cloud Contract — Gradle Project và verifierStubsJar](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html).
- [Apache Maven — Settings Reference: servers và interpolation](https://maven.apache.org/settings.html).
- [Apache Maven — Security and Deployment Settings](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html).
- [Apache Maven — Password Encryption: cảnh báo về Maven 3 encryption](https://maven.apache.org/guides/mini/guide-encryption.html).
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html).
- [Gradle — Supported Repository Protocols: credentials và authentication](https://docs.gradle.org/current/userguide/supported_repository_protocols.html).
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html).

**Lưu ý cuối:** Quyền theo namespace/path, bất biến artifact, workload identity, logging và retention là **chính sách của nền tảng repository/CI**, không phải một tính năng mà Spring Cloud Contract tự bật khi bạn thêm `@AutoConfigureStubRunner`. Hãy cấu hình và kiểm thử những chính sách đó độc lập với các contract tests.



