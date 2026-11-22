# Cập nhật dependency và kiểm tra cảnh báo lỗ hổng đúng phiên bản

> **Bối cảnh:** Spring Security – authentication, chủ đề **Vận hành**. Bài học dành cho kỹ sư vận hành, security engineer, backend developer dùng Java 17+, Spring Boot, Spring Security, Maven/Gradle và CI/CD. Trọng tâm không chỉ là “chạy máy quét CVE”, mà là **xác định đúng JAR thực tế đang chạy, đối chiếu affected version + điều kiện khai thác + fix version + kênh hỗ trợ**, cập nhật có kiểm soát và chứng minh không làm hỏng authentication/authorization. Các bản vá/CVE minh họa được lấy từ advisory Spring công bố **ngày 20/08/2026**; mọi lần xử lý sự cố sau đó phải đọc advisory gốc và kiểm tra lịch phát hành tại thời điểm thao tác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác nhau giữa dependency **khai báo**, **được quản lý qua BOM**, **đã resolve cho runtime**, **đóng gói trong executable JAR/container** và **thực sự đang chạy ở production**.
2. Tra một cảnh báo ở [Spring Security Advisories](https://spring.io/security/) và đọc đầy đủ sản phẩm, dải phiên bản ảnh hưởng, điều kiện cấu hình, bản đã sửa, kênh phát hành, migration và mitigation.
3. Chứng minh một CVE có hoặc không áp dụng bằng **version evidence + feature configuration + deployment runtime evidence**, không phán đoán từ CVSS hoặc artifact name.
4. Kiểm tra Maven `dependency:tree`/effective POM, Gradle `dependencies`/`dependencyInsight`, dependency lockfiles, SBOM, các phiên bản transitive và BOM overrides.
5. Dùng OWASP Dependency-Check/SCA và nguồn OSV/GHSA/NVD như **công cụ phát hiện**, không thay xác minh advisory từ nhà phát hành.
6. Lập kế hoạch cập nhật Spring Boot/Security theo **release train tương thích**; tránh nâng một JAR Spring Security 7.x vào Boot 3.x dùng Security 6.x một cách tùy tiện.
7. Đánh giá mức khẩn cấp dựa vào reachability, internet exposure, data sensitivity, exploitability, SLA, kênh bản vá và rủi ro regression.
8. Kiểm thử sau nâng cấp: form login, Basic/Bearer, JWT validators, CSRF, role/method security, MFA, OTT, WebAuthn, session và logout/revocation.
9. Lưu bằng chứng quản trị thay đổi: baseline, dependency graph, advisory URL, quyết định fix/mitigation, test results, SBOM mới, image digest và rollback.
10. Tự chạy chương trình Java 17 mô phỏng xác định dải phiên bản của một CVE có điều kiện cấu hình và diễn giải stdout chính xác.

## 2. Vì sao “thư viện Spring Security phiên bản nào?” không phải câu hỏi đơn giản?

Một ứng dụng Spring Boot có nhiều lớp dependency:

```text
build.gradle / pom.xml
    |
    +-- Spring Boot plugin / starter-parent
    |     |
    |     +-- spring-boot-dependencies BOM
    |              |
    |              +-- versions cho spring-security-core/config/web/crypto
    |              +-- versions cho spring-framework / jackson / tomcat ...
    |
    +-- dependencies trực tiếp (starters, security modules)
    +-- dependencies bắc cầu/transitive (JOSE/JWT, servlet, JSON ...)
    +-- overrides / constraints / dependency locks / profiles
                        |
                        v
             Resolved runtime classpath
                        |
                        v
          bootJar / executable JAR / container
                        |
                        v
        Production deployment đang chạy digest X
```

**Điểm mấu chốt:** trong `build.gradle` có dòng `implementation 'org.springframework.boot:spring-boot-starter-security'` nhưng **không thấy version** không có nghĩa chưa có phiên bản. Spring Boot BOM xác định tập phiên bản được kiểm thử cùng nhau. Ngược lại, một version khai báo trong POM không đảm bảo đó là version đã được resolve nếu có dependency management, constraints, profile, plugin hoặc transitive conflict.

Một ứng dụng có thể có:

- Spring Boot `3.x`, Spring Security `6.x` (một kết hợp thông dụng; **không suy ra từng patch** chỉ từ số major).
- Spring Boot `4.x`, Spring Security `7.x` theo release line tương thích.
- Một service A đã cập nhật nhưng service B vẫn chạy Docker image cũ.
- Tests chạy với một dependency graph khác production do `testRuntimeClasspath` hoặc `-Pprofile`.
- Local Gradle cache chứa bản JAR mới, nhưng container image production đóng gói bản cũ.
- Một `spring-security-web` được nâng, nhưng `spring-security-config` hoặc `spring-security-core` ở phiên bản khác do override không đồng bộ.
- Một lỗ hổng thuộc Spring Framework, Spring Session, Nimbus JOSE, Tomcat hoặc Jackson thay vì trực tiếp Spring Security, dù mọi thứ đều xuất hiện qua `spring-boot-starter-security`.

**Trả lời đúng:** cần thu thập `group:artifact:version` **đã resolve theo cấu hình runtime**, nguyên nhân chọn version, bản đóng gói và image đang được deploy.

### 2.1. “Version đang chạy” có ít nhất năm lớp

| Câu hỏi | Nguồn dữ liệu | Ý nghĩa |
|---|---|---|
| Dự án khai version nào? | `build.gradle(.kts)` / `pom.xml` | Ý định khai báo; có thể bị BOM override |
| BOM/parent đưa version nào? | `spring-boot-dependencies`, `dependencyManagement` | Ràng buộc/quản lý phiên bản |
| Build thực sự chọn bản nào? | Gradle `dependencyInsight` / Maven `dependency:tree` | **Resolved** dependency graph |
| Artifact chứa JAR nào? | `BOOT-INF/lib` của boot JAR, SBOM/image scan | Đóng gói thực tế sau build |
| Production chạy artifact nào? | CI artifact SHA/digest, Kubernetes image digest, deployment metadata | Quyết định liệu CVE đang hiện diện ở môi trường thực |

Đừng lấy `git main` hay “CI hôm nay build xanh” thay chứng cứ deployment; production có thể đang chạy image với digest khác.

### 2.2. Direct vs transitive dependency

**Direct dependency** là thư viện bạn khai trực tiếp, ví dụ starter security hoặc OAuth2 Resource Server.

**Transitive dependency** được kéo theo bởi thư viện khác, ví dụ JWT JOSE library được dùng bởi Resource Server. Nếu scanner phát hiện CVE ở transitive module, cần truy vết ai kéo nó vào graph, xem bản đang chạy và cân nhắc cập nhật **parent/BOM** trước khi override độc lập.

### 2.3. Không nhầm build tool plugin với thư viện runtime

Một cảnh báo trong Maven plugin, Gradle plugin, test library hoặc dependency scanner có thể ảnh hưởng **CI/build environment** nhưng không nằm trong classpath runtime của web app; ngược lại một JAR trong `runtimeClasspath` nhưng không thấy ở `compileClasspath` vẫn có thể tạo lỗ hổng production.

Không bỏ qua build-time CVE nếu attacker có khả năng kiểm soát CI, artifact signing hoặc dependency resolution; chỉ cần **định danh đúng attack surface**.

## 3. Đọc thông báo bảo mật theo cấu trúc nào?

Một advisory đáng tin thường cho biết:

1. **CVE / GHSA / identifier:** mã tham chiếu, ngày công bố/cập nhật.
2. **Product và module:** Spring Security, Spring Framework, Spring Session, Spring Authorization Server hay bên thứ ba.
3. **Description:** lỗi kỹ thuật cụ thể, hành vi bị bypass/exposure.
4. **Affected versions:** dải min–max, có bao gồm biên không, nhánh 6.4/6.5/7.0... có khác nhau không.
5. **Exploit prerequisites:** chỉ Servlet hay WebFlux, chỉ WebAuthn, cấu hình specific, storage, URL pattern, roles, headers/forwarded setup.
6. **Fix versions:** patch nào sửa, có tương ứng với release line đang sử dụng không.
7. **Availability:** OSS, Enterprise Support Only, repository/quyền truy cập; không nhầm “đã có fix” với “hệ thống của mình có quyền tải fix đó”.
8. **Workaround / mitigation:** tắt feature, thay cấu hình, bảo vệ exposure, nâng version, migration dữ liệu.
9. **Impact và severity:** CVSS, khả năng lạm dụng, dữ liệu/quyền bị ảnh hưởng.
10. **References, history:** advisory được sửa đổi ra sao; theo dõi update vì điều kiện hoặc affected ranges có thể được bổ sung.

**Không chỉ đọc phần CVE ID và ô “HIGH”.** Chẳng hạn scanner báo `org.springframework.security:spring-security-web:6.5.10` nhưng mô tả một vấn đề WebAuthn **chỉ xảy ra trong trường hợp userVerification REQUIRED + distributed session**; cần xác minh thực sự app có dùng flow đó. Ngược lại, thiếu bằng chứng về cấu hình **không có nghĩa an toàn**: trạng thái phải là `UNKNOWN / NEEDS_REVIEW` chứ không gán “not affected”.

### 3.1. Thứ tự nguồn khi có mâu thuẫn

Ưu tiên:

- **Advisory của nhà phát hành** tại `https://spring.io/security/`: điều kiện kích hoạt, versions, bản sửa và migration.
- **Release notes/changelog/Spring support policy** cho bản vá và hỗ trợ dài hạn.
- **Build artifacts metadata & SBOM** của service: xác định module và exact version.
- **CVE/NVD, GHSA, OSV, OWASP Dependency-Check**: đối chiếu IDs, CVSS, component matches, bổ sung evidence; dữ liệu có thể trễ và false-positive.
- **Security tests, feature flags, cấu hình hạ tầng**: xác định reachability và điều kiện ứng dụng.

Không dùng blog tổng hợp không rõ ngày làm nguồn duy nhất để kết luận lỗ hổng có/không áp dụng. **NVD lag** hoặc severity bị đổi sau khi xuất bản không phủ định advisory từ nhà phát hành.

## 4. Ví dụ thật: CVE-2026-47841 và cách đối chiếu đúng

**Nguồn chính thức:** [CVE-2026-47841 – WebAuthn User Verification Bypass via Session Serialization](https://spring.io/security/cve-2026-47841/), công bố **20/08/2026**.

Đây là ví dụ về lỗ hổng mà **version-only matching chưa đủ**. Theo advisory, ứng dụng có thể bị ảnh hưởng nếu **đồng thời**:

1. Dùng **WebAuthn/passkey authentication** của Spring Security.
2. Cấu hình `userVerification = REQUIRED` (mặc định `PREFERRED` không bị vấn đề được mô tả).
3. Dùng **distributed HTTP session store** như Spring Session với Redis, JDBC hoặc Hazelcast; serialization/deserialization khiến kiểm tra identity không còn đúng.

Khi cả ba đúng, người có được authenticator device có thể có cơ hội hoàn tất WebAuthn mà không đáp ứng xác minh người dùng tại thiết bị (PIN/sinh trắc), trái yêu cầu UV. Đây **không** phải tuyên bố rằng mọi ứng dụng có Spring Security đều có cùng exposure. Cần xem hiệu ứng ở session storage và cấu hình WebAuthn **đang deploy**.

### 4.1. Dải version ghi trong advisory (snapshot 20/08/2026)

| Nhánh Spring Security | Affected versions (inclusive) | Fix ghi nhận | Availability trong advisory |
|---|---|---|---|
| 6.4 | `6.4.0 – 6.4.18` | `6.4.19` | **Enterprise Support Only** |
| 6.5 | `6.5.0 – 6.5.11` | `6.5.12` | **Enterprise Support Only** |
| 7.0 | `7.0.0 – 7.0.6` | `7.0.7` | **OSS** |
| 7.1 | `7.1.0` | `7.1.1` | **OSS** |

Advisory cũng ghi `7.0.6.1` và `7.1.0.1` là các fix **Enterprise Support Only**. Đây là bảng lịch sử có nguồn, **không phải danh sách “phiên bản mới nhất” vĩnh viễn**; mỗi lần xử lý thực tế phải đọc phiên bản và entitlement hiện hành.

### 4.2. Điều kiện test nào quyết định applicability?

| Bằng chứng version | WebAuthn | UV Required | Session phân tán | Kết luận |
|---|---|---|---|---|
| 6.5.10 | Có | Có | Có | **Affected configuration**; lên phương án patch ngay |
| 6.5.10 | Có | Có | Không | Không đáp ứng điều kiện đầy đủ trong advisory, cần ghi evidence |
| 6.5.10 | Không | N/A | Có | Không dùng feature được mô tả; vẫn xem các CVE khác |
| 6.5.10 | Có | **Chưa rõ** | Có | **Needs investigation**, chưa được đóng false-positive |
| 6.5.12 | Có | Có | Có | Ngoài affected range của advisory này; **kiểm entitlement/kênh Enterprise** |
| 7.0.6 | Có | Có | Có | Affected configuration |
| 7.0.7 | Có | Có | Có | Ngoài affected range và là OSS fix được công bố |

**Bằng chứng cấu hình:** `SecurityFilterChain` đăng ký `webAuthn`, resolver `userVerification`, source của WebAuthn options, Spring Session setup, `spring.session.store-type`, Redis/JDBC deployment, thực tế session replication/serialization. Nếu production cấu hình khác staging, staging “not affected” không chứng minh production.

### 4.3. Bản vá và điều kiện hỗ trợ

Nếu đang ở Spring Security 6.5.x nhưng fix `6.5.12` ghi **Enterprise Support Only**, đừng tự tuyên bố “cứ thêm 6.5.12 từ Maven Central là xong” khi chưa xác minh entitlement/repository. Nhóm phải lựa chọn **một release line OSS được hỗ trợ và tương thích với toàn Spring Boot stack**, hoặc bản Enterprise mà tổ chức đủ điều kiện sử dụng, hoặc mitigation có đánh giá rủi ro được phê duyệt. **Không** tự override một mình `spring-security-web` lên `7.0.7` trong một ứng dụng Spring Boot 3 dùng Security 6.

Fix của CVE này được mô tả không cần bước mitigation nào khác ngoài nâng đúng bản. Tuy nhiên mọi upgrade vẫn cần test WebAuthn UV requirement, session serialization, login và rollback.

## 5. Ví dụ thứ hai: CVE-2026-47842 chứng minh “vá JAR chưa đủ”

**Nguồn chính thức:** [CVE-2026-47842 – Deterministic AES/CBC Encryption in Spring Security](https://spring.io/security/cve-2026-47842/), công bố **20/08/2026**.

Vấn đề nằm ở **cách sử dụng `AesBytesEncryptor`** với two-argument constructor hoặc CBC với IV generator null. IV cố định khiến cùng plaintext (với password/salt như nhau) tạo ciphertext giống nhau, có thể bị correlate khi attacker đọc được ciphertext store.

**Quan trọng:** scanner báo Spring Security vulnerable không cho biết ứng dụng **có dùng API đó, constructor đó hoặc dữ liệu đã mã hóa bằng định dạng cũ hay không**. Điều kiện code path và data migration mới quyết định remediation.

Advisory liệt kê affected ranges gồm `6.5.0–6.5.11`, `7.0.0–7.0.6` (cùng một số nhánh khác); fix `7.0.7`/`7.1.1` OSS, `6.5.12` Enterprise Support Only. Tài liệu cảnh báo rằng việc chuyển sang `AesCbcBytesEncryptor`/`AesGcmBytesEncryptor` có thể **cần migration/re-encryption dữ liệu** vì IV và key derivation khác trước.

### 5.1. Checklist áp dụng cho CVE này

1. Kiểm tra resolved `spring-security-crypto` version trong runtime, không chỉ `spring-security-web`.
2. Tìm usage `AesBytesEncryptor`, `Encryptors.standard()`/`stronger()`/`text()`/`delux()` và mode/constructor trong code thật, bao gồm các thư viện wrapper nội bộ.
3. Đối chiếu constructor và IV generator với **điều kiện advisory**. Dùng GCM với secure IV hoặc CBC với explicit random IV là threat profile khác null IV.
4. Nếu có ciphertext đã lưu, inventory dữ liệu, key access và khả năng giải mã ngược định dạng cũ; không thay library rồi làm dữ liệu không thể decrypt.
5. Chọn chính xác migration path được advisory mô tả, test dữ liệu thực đã được anonymize và chiến lược rollback.
6. Tránh đưa encryption password/key/IV hoặc plaintext vào log, CI artifacts hoặc tài liệu incident.
7. Chỉ đánh dấu `RESOLVED` khi đã có bản đã sửa **và** dữ liệu/operations được kiểm tra theo migration cần thiết; hoặc triage `NOT_APPLICABLE` có evidence cụ thể.

**Bài học:** dependency upgrade có thể tạo thay đổi **data format và vận hành**, không chỉ thay version trong build file. Đôi khi remediation là một **project migration** với backup/restore và key rotation, không phải một PR một dòng.

## 6. Thu thập exact version bằng Gradle

Trong dự án Gradle, dùng **Gradle Wrapper** đã commit trong repository để đảm bảo môi trường build theo cấu hình. Các lệnh dưới giả sử project có `./gradlew`; trên Windows dùng `gradlew.bat`.

### 6.1. Đọc phiên bản build tool

```bash
./gradlew --version
./gradlew help
```

Kết quả cung cấp Gradle/JVM, nhưng **không tự nói Spring Security version**. Tiếp tục đọc `build.gradle(.kts)`, `settings.gradle(.kts)`, version catalogs `gradle/libs.versions.toml`, pluginManagement, Spring Boot plugin và dependency locks nếu có.

### 6.2. Dependency tree thực sự resolve

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Nếu là multi-module, thêm project path:

```bash
./gradlew :api:dependencies --configuration runtimeClasspath
./gradlew :worker:dependencies --configuration runtimeClasspath
```

**Runtime là mục tiêu chính cho production**; `compileClasspath` và `testRuntimeClasspath` có thể chọn/bổ sung phiên bản khác. Đọc các dấu Gradle như `->` (version được nâng do conflict/constraint), `(c)` (dependency constraint) và nguyên nhân resolution, không chỉ grep “spring-security”.

### 6.3. Dependency Insight cho từng module nghi vấn

```bash
./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-core \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-config \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency org.springframework.security:spring-security-crypto \
  --configuration runtimeClasspath
```

Để hiểu nguyên nhân chọn version (BOM, direct dependency, constraint, transitive), `dependencyInsight` có giá trị hơn chỉ nhìn một dòng khai version. Nếu ứng dụng có `oauth2ResourceServer`/`webAuthn`, điều tra thêm `spring-security-oauth2-resource-server`, `spring-security-oauth2-jose` và thư viện JOSE/WebAuthn có liên quan.

### 6.4. Khi có version override hoặc lockfile

Đọc kỹ:

- `resolutionStrategy.force(...)`, `eachDependency`, constraints, `strictly`, `enforcedPlatform`, Spring dependency-management plugin.
- Version catalog aliases và Gradle dependency locking.
- Platform/imported BOM khác có thể cạnh tranh với Spring Boot BOM.
- Phụ thuộc `-SNAPSHOT`, dynamic versions `6.+`, `latest.release`: làm build thiếu tái lập.
- Composite builds và plugin build logic: một module plugin có thể nạp library riêng vào build JVM.

Nên tránh `force` một phiên bản Spring Security riêng lẻ chỉ để scanner hết cảnh báo nếu các module Security khác chưa tương thích. **Ưu tiên cập nhật phiên bản Spring Boot được duy trì** để BOM đưa các module liên quan đi cùng release train, trừ khi có hướng dẫn vendor/chính sách override có thử nghiệm đầy đủ.

### 6.5. Xem artifact đóng gói

Với executable Boot JAR:

```bash
./gradlew bootJar
jar tf build/libs/app.jar
```

`build/libs/app.jar` là tên **minh họa**, không mặc định mọi dự án đều có file này. Tìm `BOOT-INF/lib/spring-security-*.jar` hoặc tạo SBOM trên archive/image thật; có thể dùng `jar tf` với đường dẫn JAR thực tế do build tạo. Container layer/digest và deployment cần được đối chiếu với CI artifact, không tự coi resolved classpath trên laptop là production.

## 7. Thu thập exact version bằng Maven

Nếu dùng `spring-boot-starter-parent` hoặc import `spring-boot-dependencies` BOM, nhiều dependencies không ghi version trực tiếp trong POM. Maven sẽ dùng dependency management và quy tắc mediation.

### 7.1. Dependency tree

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=org.springframework.security:spring-security-web
```

Dùng `mvnw.cmd` trên Windows. Với multi-module, có thể gọi `-pl :service-api` và `-am` phù hợp. Đọc `scope`, `version`, parent và profile đang active.

### 7.2. Effective POM và dependency management

```bash
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw dependency:tree -DoutputFile=resolved-dependencies.txt
```

Lưu ý `effective-pom.xml` và dependency tree là **artifacts phục vụ điều tra**, không commit bí mật môi trường hoặc URL chứa credentials. Xác minh `pom.xml` có `dependencyManagement` imports, property overrides như `spring-security.version`, `spring-framework.version`, riêng `spring-boot-starter-parent` và plugin version. Nếu Maven dùng profile khác nhau giữa CI và developer workstation, tái chạy với profile thực sự deploy.

### 7.3. Ví dụ Maven dependency không ghi version

```xml
<!-- Trích đoạn pom.xml được quản lý bởi Spring Boot parent/BOM. -->
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
</dependencies>
```

Thiếu `<version>` ở đây **đúng** khi BOM quản lý. Nhưng muốn kết luận một CVE có liên quan phải lấy các JAR `spring-security-*` đã resolve và điều kiện app, không chỉ “đã có starter”.

## 8. BOM, release train và cách nâng cấp có kiểm soát

### 8.1. Vì sao nên nâng Spring Boot trước?

Spring Boot cung cấp một **Bill of Materials** gồm các Spring modules và third-party dependencies được release team kiểm tra cùng nhau. Trong đa số dự án Boot, đường nâng cấp an toàn là:

```text
Baseline Boot version + resolved graph
         |
         v
Chọn bản Boot được hỗ trợ,
chứa hoặc tương thích với Spring Security fix
         |
         v
Review release notes / migration guides / support terms
         |
         v
Build / run tests / inspect resolved graph
         |
         v
Patch policy evidence & production deployment
```

**Không bao giờ** mặc định Spring Boot `3.4` tương thích với bất kỳ Spring Security `7.1` nào chỉ vì Maven có thể resolve JAR. Major/minor security DSL, Spring Framework, Java baseline, servlet container và WebFlux/Servlet internals có thể thay đổi. Tương thích được xác nhận qua docs/BOM/CI, không qua việc compile một method.

### 8.2. Gradle: BOM quản lý version

Trích đoạn dependencies phù hợp khi project đã áp dụng Spring Boot plugin và dependency-management plugin hoặc cấu hình platform tương đương:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**Đừng thêm trực tiếp `org.springframework.security:spring-security-web:7.0.7` vào mọi app Boot 3.x** để “sửa CVE”. Đó có thể tạo dependency drift/mismatch với `spring-security-config`, `spring-security-core`, và Spring Framework. Nếu cần override ngắn hạn theo tư vấn nhà phát hành, ghi rõ lý do, scope, TTL, tests và kế hoạch quay lại BOM.

### 8.3. Chọn phiên bản cần dữ kiện gì?

- Nhánh target còn trong **OSS support** hay cần Enterprise Support?
- JDK, Spring Framework, Boot, Security và plugin compatibility.
- Có thay đổi behavior của `SecurityFilterChain`, `AuthorizationManager`, `PasswordEncoder`, session handling, OAuth2/OIDC?
- Có breaking changes ở major (6 → 7), deprecations, servlet API version?
- Migrations data/key/config như ví dụ `AesBytesEncryptor`?
- Có nhiều services/các gateway cùng dùng JWT/schema/session chung cần nâng đồng bộ?
- Có rollback path sau khi thay session serialization hoặc dữ liệu mã hóa?
- Có vulnerability **khác** trong target version không, và có bản cập nhật mới hơn kể từ advisory?

Một version “fix cho CVE A” chưa chắc là version **an toàn trước mọi CVE B–Z**. Cần chạy SCA trên **graph cuối** và theo dõi advisories mới.

## 9. Máy quét dependency: phát hiện, không thay thế triage

### 9.1. OWASP Dependency-Check

OWASP Dependency-Check là Software Composition Analysis (SCA) tool dùng nguồn dữ liệu công khai như NVD và metadata dependency để tìm **các lỗ hổng đã công bố**. Công cụ không tự chứng minh mọi code path reachable, và có thể gán sai component/phiên bản hoặc bỏ sót nếu evidence không đủ.

Ví dụ Gradle (plugin ID đã được công bố; phiên bản `13.0.0` là **mẫu ghim công cụ công bố 08/2026**, phải xác nhận lại tính tương thích trước khi áp dụng):

```groovy
plugins {
    id 'org.owasp.dependencycheck' version '13.0.0'
}
```

Chạy trên project đã có plugin và dependency metadata:

```bash
./gradlew dependencyCheckAnalyze
```

Báo cáo thường được lưu trong vùng `build/reports`, phụ thuộc plugin/config. Trong multi-project, nghiên cứu `dependencyCheckAggregate` hoặc scan từng deployable module. Không chỉ quét `testImplementation` rồi kết luận runtime sạch.

### 9.2. Không bật tắt máy quét theo kết quả mong muốn

- Bảo đảm NVD feed đã cập nhật, API key/rate limit, mạng, CI cache và plugin version phù hợp.
- Nếu scanner **bị lỗi không tải dữ liệu**: trạng thái `SCAN_FAILED/INCOMPLETE`, không phải `NO_FINDINGS`.
- Nếu scanner không có metadata Maven Central/private repository, có thể false-positive hoặc false-negative; xem artifact coordinates/POM evidence.
- Nếu suppression là cần thiết, phải có **chủ sở hữu, CVE, component+version+environment, lý do có chứng cứ, ngày hết hạn, link ticket và review**.
- Không dùng rule “ignore everything with CVSS < 9” làm chính sách duy nhất; exploitability và sensitive paths quan trọng.
- Sau upgrade, chạy lại scan và so diff report; một bản mới có thể vẫn có CVE khác.
- Báo cáo nên được lưu cùng commit SHA, build ID, image digest và timestamp của feed để tái lập điều tra.

### 9.3. NVD, GHSA, OSV và các thuật ngữ

| Nguồn | Hữu ích cho | Giới hạn cần nhớ |
|---|---|---|
| Spring official advisories | Điều kiện Spring/feature, affected/fix versions, mitigation | Phải đọc bản cập nhật gần nhất, phân biệt Enterprise fix |
| NVD/NIST | CVE descriptions, CVSS/CPE, metadata công khai | CPE matching có thể sai hoặc chậm cập nhật |
| GitHub Security Advisories (GHSA) | Affected package ranges, ecosystem, references | Phụ thuộc độ chính xác ecosystem/package mapping |
| OSV | Vulnerabilities theo package/version, API/bulk scan | Không có nghĩa reachability đã được chứng minh |
| OWASP Dependency-Check | Quét Java dependencies và tạo báo cáo | False positives/negatives và phụ thuộc nguồn dữ liệu |
| SBOM CycloneDX/SPDX | Inventory BOM theo bản build/artifact | SBOM tự nó không thay thế vulnerability analysis |
| Runtime/image scanners | JAR/base-image/OS packages trong artifact | Cần map đúng installed runtime và context |
| SAST/DAST/fuzzing | Kiểm code/config behavior và attack surface | Không thay version inventory/SCA |

CVE là identifier của vấn đề, **không phải tên package**. Một CVE có thể ảnh hưởng nhiều artifact trong một project; một artifact có thể liên quan nhiều CVE. Không suy từ `CVE-2026-XXXX` ra chính xác version mới nhất nếu chưa đọc affected/fix table.

## 10. SBOM và supply chain: gắn cảnh báo vào bản build cụ thể

**SBOM (Software Bill of Materials)** là inventory các thành phần có trong build/image, với coordinates, versions và định dạng chuẩn như CycloneDX hoặc SPDX. Nó giúp:

1. Tìm mọi service phụ thuộc module bị CVE bằng truy vấn SBOM registry.
2. Đối chiếu bản build source với artifact thực đã deploy.
3. Chứng minh sau patch rằng module version đã thay, thay vì chỉ nhìn Git diff.
4. Lưu history/version lineage cho incident response.
5. Kiểm transitive modules bị ảnh hưởng nhưng không được khai trực tiếp.

Dữ liệu nên ghi:

```text
service: payments-api
release: git-sha-abc123
buildId: ci-2026-11-06-001
imageDigest: sha256:<digest-from-registry>
javaRuntime: vendor/version
springBoot: resolved version
springSecurityModules:
  spring-security-core: <resolved version>
  spring-security-web: <resolved version>
  spring-security-config: <resolved version>
  spring-security-crypto: <resolved version>
sbom: CycloneDX file hash and generation time
scanner: tool/version/advisory-feed-timestamp
```

Các chuỗi trong record trên là **schema biểu diễn**, không phải báo cáo từ một hệ thống đang chạy. Điền version/digest thật từ CI/repository; đừng xuất bản các identifiers nhạy cảm ở nguồn công khai nếu không cần.

### 10.1. Lockfile và reproducible builds

Gradle dependency locking, Maven wrapper, container base-image digest, artifact repository pinning và CI cache policies giúp giảm tình huống cùng một source SHA lại resolve khác nhau. Cố định phiên bản plugin và JDK toolchain khi có thể. Không dùng dynamic dependency ranges làm nguồn bản vá tự động cho production mà thiếu kiểm thử.

**Lưu ý:** Dependency locks có thể giữ lại version vulnerable khi chỉ nâng BOM. Sau upgrade phải cập nhật lockfile đúng cách, so diff và test; không nhầm “BOM đã nâng” với “runtime đã nâng”.

### 10.2. Runtime JDK, proxy và servlet container cũng cần vá

Cảnh báo ứng dụng authentication có thể phát sinh từ:

- JVM/JDK TLS/security providers; CA store và crypto implementation.
- Tomcat/Jetty/Undertow, Netty/Reactor, Jackson.
- Spring Session/Redis/JDBC serialization.
- Gateway, reverse proxy, ingress và session cookie handling.
- Nimbus JOSE JWT validation / WebAuthn libraries.
- OS/base image packages, TLS termination, WAF/IDP integration.

Không dừng ở `spring-security-web` khi triage. Dù dependency scanner Java sạch, một container base image vẫn có lỗ hổng; ngược lại OS scanner có thể flag package không hiện diện trong Java runtime.

## 11. Đánh giá mức độ ảnh hưởng: không chỉ dựa vào CVSS

Khi triage một finding, dùng **bằng chứng** thay vì đoán:

1. **Exact artifact/version** thực đang deploy (Maven coordinates, image digest).
2. **Affected range** từ advisory. Version có nằm trong range không?
3. **Feature prerequisites**: Servlet/WebFlux, WebAuthn, BCrypt, method security, AesBytesEncryptor, OAuth2 Resource Server, session store.
4. **Code path/reachability**: flow có expose qua Internet/VPN/tenant boundary? Có feature flag và route protections nào?
5. **Attacker prerequisites**: anonymous/authenticated, cần chiếm thiết bị, cần đọc DB, vai trò user, điều kiện race.
6. **Impact**: bypass MFA, leak dữ liệu, RCE/DoS, quyền admin, secret/password exposure, integrity loss.
7. **Exploit maturity**: public PoC, weaponization, exploit in wild, EPSS/CISA KEV nếu phù hợp.
8. **Mitigation**: guardrails, WAF, feature disable, session isolation; có kiểm thử chứng minh nó hiệu quả không?
9. **Fix availability**: OSS/Enterprise, hợp đồng support, migration path, time-to-ship.
10. **Compensating controls và deadline**: chủ sở hữu quyết định, chấp nhận rủi ro có thời hạn và monitoring.

### 11.1. Mô hình trạng thái finding rõ ràng

| Trạng thái | Bằng chứng cần để sử dụng |
|---|---|
| `AFFECTED` | Runtime version trong range **và** điều kiện khai thác có bằng chứng |
| `POTENTIALLY_AFFECTED` | Version trong range, config/reachability chưa biết |
| `NOT_APPLICABLE_BY_VERSION` | Runtime version chứng minh nằm ngoài affected range |
| `NOT_APPLICABLE_BY_CONFIGURATION` | Version trong range nhưng điều kiện trong advisory không thỏa, có logs/config/test chứng minh |
| `MITIGATED_TEMPORARILY` | Biện pháp kiểm soát đã áp dụng và kiểm thử; có deadline vá |
| `FIX_AVAILABLE_NOT_DEPLOYED` | Bản vá phù hợp đã phát hành nhưng production còn bản cũ |
| `PATCHED_AND_VERIFIED` | Artifact production mới, tests và post-deploy checks đạt |
| `SCAN_INCOMPLETE` | Tool/feed/repository failure, thiếu dữ liệu không được kết luận sạch |
| `RISK_ACCEPTED_UNTIL` | Người có thẩm quyền, lý do, compensating controls, ngày hết hạn |

**Tránh bẫy:** `NOT_APPLICABLE_BY_CONFIGURATION` không giống `PATCHED`. Khi bật feature mới hoặc thay session store, finding trước đó có thể trở lại applicable. Config-dependent suppressions phải được re-evaluate khi kiến trúc thay đổi.

### 11.2. SLA và thời gian phản ứng

Doanh nghiệp nên có risk-based patch SLA. Ví dụ minh họa, không phải chuẩn bắt buộc:

- **Emergency:** exploit đang diễn ra, bypass authentication/authorization có Internet exposure → hành động ưu tiên cao, giảm attack surface trong lúc vá.
- **High:** sản phẩm bị ảnh hưởng trên login/session/MFA và có bản vá → quy trình hotfix nhanh, tăng giám sát.
- **Medium/Low:** đánh giá tính khai thác và mức độ tiếp cận, lên lịch patch trong maintenance window.
- **Unknown:** cần điều tra, không chờ đến khi scanner tự hết cảnh báo.

Không thay triage bằng “CVSS cao thì update ngay tất cả lên major mới”; major migration không thử nghiệm có thể tự làm ứng dụng lỗi hoặc mở bypass security configuration.

## 12. Java 17 độc lập: kiểm dải version và điều kiện CVE

Chương trình này **biên dịch/chạy bằng JDK 17+**, không cần Spring/Maven. Nó mô phỏng cách triage **CVE-2026-47841**: các dải version đã công bố cộng với ba điều kiện cấu hình WebAuthn/UV_REQUIRED/distributed session. Mọi kết quả là mô hình minh họa **tại snapshot advisory 20/08/2026**, không phải vulnerability scanner tổng quát.

**Quan trọng:** comparator ở đây chỉ đọc version dạng `major.minor.patch` **toàn số**. Nó không xử lý SemVer pre-release, Maven qualifiers, Spring Enterprise bốn thành phần như `7.0.6.1`, SNAPSHOT, OSGi metadata, support policy hay BOM resolution. Đối với production, dùng version resolver ecosystem + advisory ranges thật, không dùng code demo làm nguồn đánh giá duy nhất.

Lưu file `SpringSecurityAdvisoryTriageDemo.java`:

```java
import java.util.List;

public class SpringSecurityAdvisoryTriageDemo {

    record Version(int major, int minor, int patch)
            implements Comparable<Version> {
        static Version parse(String value) {
            String[] parts = value.split("\\.");
            if (parts.length != 3) {
                throw new IllegalArgumentException(
                    "Only numeric major.minor.patch supported");
            }
            return new Version(
                Integer.parseInt(parts[0]),
                Integer.parseInt(parts[1]),
                Integer.parseInt(parts[2]));
        }

        @Override
        public int compareTo(Version other) {
            int byMajor = Integer.compare(major, other.major);
            if (byMajor != 0) return byMajor;

            int byMinor = Integer.compare(minor, other.minor);
            if (byMinor != 0) return byMinor;

            return Integer.compare(patch, other.patch);
        }
    }

    record AffectedRange(Version first, Version last) {
        boolean contains(Version value) {
            return value.compareTo(first) >= 0
                && value.compareTo(last) <= 0;
        }
    }

    enum Setting { YES, NO, UNKNOWN }

    record WebAuthnConfig(
        Setting usesWebAuthn,
        Setting requiresUserVerification,
        Setting distributedSessionStore) {}

    private static final List<AffectedRange> AFFECTED =
        List.of(
            new AffectedRange(
                Version.parse("6.4.0"), Version.parse("6.4.18")),
            new AffectedRange(
                Version.parse("6.5.0"), Version.parse("6.5.11")),
            new AffectedRange(
                Version.parse("7.0.0"), Version.parse("7.0.6")),
            new AffectedRange(
                Version.parse("7.1.0"), Version.parse("7.1.0"))
        );

    static String classify(String rawVersion, WebAuthnConfig config) {
        Version version = Version.parse(rawVersion);

        boolean inRange = AFFECTED.stream()
            .anyMatch(range -> range.contains(version));
        if (!inRange) {
            return "NOT_IN_AFFECTED_RANGE";
        }

        if (config.usesWebAuthn() == Setting.NO
                || config.requiresUserVerification() == Setting.NO
                || config.distributedSessionStore() == Setting.NO) {
            return "NOT_APPLICABLE_BY_CONFIG";
        }

        if (config.usesWebAuthn() == Setting.UNKNOWN
                || config.requiresUserVerification() == Setting.UNKNOWN
                || config.distributedSessionStore() == Setting.UNKNOWN) {
            return "NEEDS_CONFIG_REVIEW";
        }

        return "AFFECTED_CONFIGURATION";
    }

    public static void main(String[] args) {
        WebAuthnConfig affected = new WebAuthnConfig(
            Setting.YES, Setting.YES, Setting.YES);
        WebAuthnConfig noDistributed = new WebAuthnConfig(
            Setting.YES, Setting.YES, Setting.NO);
        WebAuthnConfig unknownUv = new WebAuthnConfig(
            Setting.YES, Setting.UNKNOWN, Setting.YES);

        System.out.println("6.5.10 + affected: " +
            classify("6.5.10", affected));
        System.out.println("6.5.10 + no distributed: " +
            classify("6.5.10", noDistributed));
        System.out.println("6.5.10 + unknown UV: " +
            classify("6.5.10", unknownUv));
        System.out.println("6.5.12 + affected: " +
            classify("6.5.12", affected));
        System.out.println("7.0.6 + affected: " +
            classify("7.0.6", affected));
        System.out.println("7.0.7 + affected: " +
            classify("7.0.7", affected));
        System.out.println("6.4.18 + affected: " +
            classify("6.4.18", affected));
        System.out.println("6.4.19 + affected: " +
            classify("6.4.19", affected));
    }
}
```

Biên dịch và chạy:

```bash
javac SpringSecurityAdvisoryTriageDemo.java
java SpringSecurityAdvisoryTriageDemo
```

Stdout **chính xác**:

```text
6.5.10 + affected: AFFECTED_CONFIGURATION
6.5.10 + no distributed: NOT_APPLICABLE_BY_CONFIG
6.5.10 + unknown UV: NEEDS_CONFIG_REVIEW
6.5.12 + affected: NOT_IN_AFFECTED_RANGE
7.0.6 + affected: AFFECTED_CONFIGURATION
7.0.7 + affected: NOT_IN_AFFECTED_RANGE
6.4.18 + affected: AFFECTED_CONFIGURATION
6.4.19 + affected: NOT_IN_AFFECTED_RANGE
```

### 12.1. Điều code chứng minh và không chứng minh

**Có thể chứng minh:**
- Chỉ xét một bản `major.minor.patch` đã cho, so đúng range inclusive.
- Một điều kiện `NO` đủ để kết luận không thỏa **ba điều kiện đồng thời** của advisory này.
- Điều kiện chưa rõ trả `NEEDS_CONFIG_REVIEW`, không âm thầm “not affected”.
- 6.5.12 và 7.0.7 nằm ngoài dải phiên bản bị ảnh hưởng **của CVE cụ thể**.

**Không chứng minh:**
- Build/production có thật sự dùng `6.5.10` hay 6.5.12.
- 6.5.12 có sẵn trên Maven Central hoặc người dùng có Enterprise Support.
- Có CVE khác ảnh hưởng bản đã chọn hay không.
- User verification trong app có thực sự REQUIRED/được enforce trong distributed session.
- Chữ ký WebAuthn được verify thực tế hoặc session serialization đúng.
- Tập dependencies khác có compatible khi upgrade.
- Các version qualifiers hoặc Maven/Gradle resolution semantics.

**Đừng copy comparator này vào công cụ triage production.** Dùng SCA/OSV ranges/Spring Advisory chính thức cùng resolved graph, evidence đã kiểm tra.

## 13. Kiểm thử regression sau khi cập nhật Spring Security

### 13.1. Authentication

| Chức năng | Positive test | Negative/security test |
|---|---|---|
| Username/password | Password đúng được xác minh qua provider thật | Sai password, account disabled/locked không login |
| Password hashing | `PasswordEncoder.matches` đúng với hash được lưu | Không chấp nhận mật khẩu khác; migration hash cũ đúng policy |
| HTTP Basic | Basic credential hợp lệ mới truy cập | Thiếu/sai credential → 401 + Basic challenge |
| OAuth2 JWT Resource Server | JWT ký thật, issuer/audience/time hợp lệ | Sai chữ ký, `alg`, issuer, audience, expired → 401 |
| Form login | Session context được lưu đúng sau POST + CSRF | CSRF thiếu/invalid không tạo session |
| Session management | Session fixation protection, logout/invalidate | Cookie cũ/đã revoke không còn quyền |
| Authorization | Đúng role và owner mới xem resource | Cross-tenant/BOLA/`@PreAuthorize` bị từ chối |
| OTT/magic link | Token mới, TTL, one-use | Expired, replay, concurrent consume, wrong purpose |
| WebAuthn/passkey | Assertion signed đúng origin/RP/UV | UV=false khi REQUIRED, challenge stale/wrong session |
| MFA/step-up | Đủ factor hiện hành và freshness | Chỉ password, factor wrong owner/expired/removed |
| OIDC | Callback hợp lệ và identity mapping chính xác | State/nonce/issuer mismatch, email collision/link hijack |

**Không dùng mỗi `@WithMockUser` hoặc `jwt()` để tuyên bố đã test password verifier/JWT signature**. Các test fixtures đó đặt sẵn principal; cần ít nhất một integration test qua filter/provider/decoder thật với credential thật hoặc ký bởi test key.

### 13.2. Test cực kỳ quan trọng với CVE-2026-47841

Nếu app dùng WebAuthn UV=REQUIRED và distributed HTTP session:

1. Tạo WebAuthn challenge/options theo cấu hình thật, lưu request context trong shared session.
2. Cho request đi qua serialize/deserialize giữa hai nodes hoặc session store integration.
3. Dùng virtual authenticator hoặc WebAuthn test key tạo assertion có chữ ký hợp lệ **nhưng UV=false**.
4. Assert **login bị từ chối** khi UV_REQUIRED, ngay cả khi chữ ký/challenge/origin/RP ID đúng.
5. Tạo assertion với UV=true, verify đủ toàn bộ điều kiện, assert login hợp lệ.
6. Kiểm replay assertion/challenge bị từ chối, credential thuộc user khác bị từ chối.
7. Chạy test trên **build mới và môi trường tương đương production**, không chỉ unit test một method bỏ qua session serialization.
8. Kiểm các nodes đều chạy image digest mới, không có rolling deployment giữ phiên bản cũ quá thời gian cho phép.

### 13.3. Test với CVE-2026-47842

Nếu app dùng Spring Security crypto encryptors liên quan:

- Kiểm ciphertext được mã hóa trước upgrade có giải mã được sau migration theo tài liệu.
- Kiểm ciphertext mới có IV/nonce đúng và cùng plaintext không bị đồng nhất một cách có thể khai thác.
- Kiểm key rotation, backwards compatibility window và rollback data format.
- Test corruption/truncation/tampering theo mode và format mới; AEAD/GCM dùng authentication tag.
- Không kiểm thử bằng dữ liệu cá nhân/key sản xuất trên CI công khai.
- Lưu kiểm định migration cùng backup/restore runbook, không coi build pass là đủ.

### 13.4. Regression ngoài authentication

Nâng Boot/Security có thể tác động `SecurityFilterChain` matcher order, exception handling 401/403, CSRF, CORS, cookie SameSite, Spring Session serialization, OAuth claims mapping, method security proxies, WebFlux vs Servlet differences, resource-server auto-config, HSTS và exception responses.

Một `401` tăng đột biến sau deploy có thể do issuer/audience validator hoặc cookie thay đổi, không tự kết luận “đã vá thành công”. Theo dõi security metrics, canary traffic và synthetic login flows đã được kiểm soát.

## 14. Quy trình CI/CD đề nghị

### 14.1. Trước khi tạo PR

```text
1. Inventory deployed version/image digest.
2. Tìm CVE theo Spring Advisory; đọc đầy đủ điều kiện, affected/fix.
3. Ghi finding ticket: evidence version + feature + impact + severity.
4. Chọn branch patch tương thích, OSS/Enterprise entitlement.
5. Sửa Boot/BOM/lockfile hoặc sanctioned override.
6. Kiểm dependency diff và API migration.
7. Run unit + Spring integration + security negative tests.
8. Scan resolved runtime dependencies và SBOM mới.
9. Review source, release notes, repository và provenance.
```

### 14.2. Trong CI

Pipeline logic minh họa (không phải YAML hoàn chỉnh):

```text
CHECKOUT pinned commit
VERIFY JDK + Maven/Gradle Wrapper
VERIFY dependency lockfiles/repositories
RESOLVE runtime dependency graph
GENERATE build-scoped SBOM
RUN SCA (fresh advisory feed; fail on scanner errors)
TRIAGE relevant findings / check approved exceptions
RUN unit tests
RUN authentication/security integration tests
BUILD artifact and container image
SCAN artifact/container/image digest
SIGN/ATTEST artifact if organization policy requires
PUBLISH immutable artifact + SBOM + reports
```

**Không đưa secret scanner API key, signing key, authorization tokens hoặc IDP credentials vào logs**. Sử dụng secret manager/CI scoped credentials. Pin action/plugin versions khi phù hợp và test cơ chế update chúng.

### 14.3. Trước khi deploy

- Xem PR diff, Gradle/Maven resolved versions, SCA report, advisory conditions.
- Chạy security canary: login success/failure, role-denied, JWT reject, WebAuthn UV=REQUIRED trên session distributed, logout.
- Xác nhận rollback image digest **và** đường rollback schema/serialized session/data migration nếu thay đổi format.
- Phê duyệt change window theo mức khẩn cấp, có người trực monitor.
- Nếu patch đòi thay đổi migrations không đảo ngược, rollback binary có thể không an toàn; chuẩn bị forward-fix plan.

### 14.4. Sau deploy

- Xác minh chính xác **image digest** ở mỗi pod/node; tránh canary giữ bản cũ cho route authentication.
- Kiểm `BOOT-INF/lib`/SBOM runtime cho đúng resolved versions.
- So sánh error rate 401/403/5xx, session login rate, WebAuthn UV errors, MFA completion, token refresh, latency.
- Kiểm các negative security tests trên production-like synthetic accounts.
- Ghi thời điểm patch deployed, CVE closed và evidence mới trong security registry.
- Đặt lại monitoring cho advisory mới; không coi “đã patch tháng này” là trạng thái vĩnh viễn.

## 15. Khi bản vá chưa khả dụng hoặc chưa tương thích

Có thể gặp tình huống một fix chỉ được cung cấp qua **Enterprise Support** ở release line cũ, trong khi nâng lên release line OSS mới yêu cầu migration lớn. Đừng tự sáng tác version/fork hoặc hứa fix có trên public repository.

Quy trình hợp lý:

1. Xác nhận **exact affected range** và **availability** từ advisory, trong thời gian thực.
2. Xác minh hợp đồng support/repository access của tổ chức và compatibility matrix.
3. Ước lượng nâng cấp lên một nhánh OSS supported; chấp nhận rằng 6.x → 7.x có thể không phải một line change.
4. Thực hiện **mitigation** nếu vendor công bố; nếu chưa có, cân nhắc tạm tắt feature dễ bị khai thác, hạn chế exposure, thêm kiểm tra server-side có thể chứng minh, theo policy/risk approval.
5. Không tự coi WAF là fix chắc chắn cho bypass bên trong authentication.
6. Ghi deadline/owner, test giảm thiểu, giám sát và rollback.
7. Khi bản vá phù hợp có sẵn, triển khai qua review/tests/SBOM/deployment verification.
8. Cập nhật user/security stakeholders nếu có sự cố đã khai thác hoặc yêu cầu pháp lý.

**Đặc biệt:** nếu tính năng WebAuthn user verification là lớp bảo vệ bắt buộc, tạm chuyển `REQUIRED` sang `PREFERRED` để tránh điều kiện CVE **có thể làm giảm assurance nghiêm trọng**. Không gọi đó là remediation tương đương nếu threat model của hệ thống đòi UV; phải có phương án được phê duyệt và kiểm chứng.

## 16. Các sai lầm thường gặp khi xử lý advisory

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| “Đang dùng Boot 3 nên Security luôn an toàn” | Patch cụ thể có thể thuộc affected range | Đọc BOM và resolved runtime version |
| “BOM đã nâng nghĩa là production đã vá” | Lockfile/image cũ/không redeploy | Kiểm artifact và digest thật |
| “Scanner báo CVE HIGH nên tất cả app đều bị khai thác” | Có thể yêu cầu feature/config cụ thể | Triage điều kiện theo advisory và test |
| “Không dùng WebAuthn nên sửa mọi cách bằng Security 7” | Major upgrade có migration/regression | Chọn đường patch tương thích và risk |
| “Có fix 6.5.12 nên ai cũng tải công khai được” | Advisory ghi Enterprise Support Only | Kiểm entitlement và kênh phát hành |
| “Chỉ cập nhật spring-security-web là xong” | Modules khác/trains không đồng bộ | Dùng BOM và dependencyInsight |
| “Scan không có finding nghĩa là không CVE” | Feed lỗi hoặc component bị miss | Kiểm scan completeness và advisor nguồn |
| “CVE trong test scope nghĩa là bị lộ runtime web” | Attack surface khác nhau | Phân loại runtime/test/build/CI |
| “Không có call site theo grep nên không ảnh hưởng” | Dynamic config/reflection/transitive usage | Phân tích runtime/config và tracing có chứng cứ |
| “CVSS thấp nên bỏ qua” | Exploitability và tác động tùy ứng dụng | Kết hợp CVSS/EPSS/KEV và attack path |
| “Suppress scanner để pipeline xanh” | Giấu risk thật | Suppression timebound có approval + evidence |
| “Test @WithMockUser pass nên password/JWT được verify” | Fixture bỏ qua authentication providers | Integration bằng credentials/keys thật |
| “Nâng crypto encryptor nhưng không migrate data” | Ciphertext cũ có thể không decrypt | Đọc migration advisory, backup/migrate/test |
| “Đổi password admin trong DB là thu hồi mọi JWT” | Token stateless còn hạn | Version/introspection/revocation policy |
| “Chỉ kiểm local build” | Deployed image có thể khác | Attested artifact SBOM + runtime digest |
| “Tắt UV required để tránh CVE” | Hạ assurance | Review threat model và vendor mitigation |
| “Release notes cũ đủ để kết luận bản vá hiện tại” | Advisories có thể bổ sung affected ranges | Đọc bản official cập nhật vào ngày triage |

## 17. Checklist vận hành định kỳ

1. **Inventory:** có danh mục services, owners, deploy versions, SBOM/image digest, JDK, Spring Boot, Security, runtime và transitive libraries.
2. **Advisory ingestion:** theo dõi Spring advisories/RSS, NVD/GHSA/OSV và supplier security announcements.
3. **Applicability:** với từng CVE, ghi package, exact version range, affected features/config và evidence.
4. **Availability:** phân biệt OSS, Enterprise, unsupported/EOL, release-train compatibility.
5. **Prioritization:** severity + reachability + exploit maturity + sensitivity, có SLA/owner.
6. **Patch design:** Boot/BOM dependency graph nhất quán, lockfile được cập nhật, không force mù các modules.
7. **Security tests:** wrong password, 401/403, JWT issuers/audience, CSRF, session, role, OTT/WebAuthn/MFA.
8. **Crypto/data migration:** backup, restore, re-encryption, compatibility, rollback khả thi.
9. **CI gates:** scanner freshness/failure detection, policy exceptions timebound, SBOM per release, immutable artifacts.
10. **Production verification:** rollout/canary, exact image digest, metrics, rollbacks và regression evidence.
11. **Incident handling:** khi có auth bypass, thu thập audit đã redact, kiểm session/token validity, xác định khách hàng ảnh hưởng theo policy.
12. **Repeatability:** có script/commands và artifact evidence tái chạy cho vụ việc tiếp theo; không chỉ chat message “đã cập nhật”.

## 18. Câu hỏi tự đánh giá

**Câu 1.** Một dự án khai `spring-boot-starter-security` không version trong Gradle. Làm sao biết Spring Security đang chạy version nào?  
**Trả lời:** Xem Spring Boot BOM và `dependencyInsight --configuration runtimeClasspath` để lấy JAR version đã resolve; sau đó đối chiếu `BOOT-INF/lib`/SBOM/image digest production.

**Câu 2.** Máy quét thấy `spring-security-web:6.5.10` và CVE-2026-47841. Có thể tự kết luận toàn bộ website bị ảnh hưởng?  
**Trả lời:** Chưa. Cần xác minh ứng dụng có WebAuthn, `userVerification=REQUIRED` và HTTP sessions phân tán như advisory nêu, cùng version thực đang deploy. Nếu thiếu evidence, trạng thái là `POTENTIALLY_AFFECTED`, không phải `NOT_APPLICABLE`.

**Câu 3.** Theo advisory 20/08/2026, bản vá 6.5.12 có được ghi là OSS không?  
**Trả lời:** Không; advisory ghi **Enterprise Support Only**. Bản 7.0.7/7.1.1 được ghi OSS. Chọn version tương thích và kiểm kênh download thật.

**Câu 4.** Vì sao không override `spring-security-web` riêng lẻ thành 7.0.7 trong Spring Boot 3 để fix CVE?  
**Trả lời:** Spring Security modules và Spring Framework có compatibility constraints theo release train. Có thể compile/runtime lỗi, bypass config hoặc data migration; nên theo BOM/hướng dẫn vendor và kiểm toàn bộ graph.

**Câu 5.** SCA không tải được NVD feed nhưng report không có findings. Đã an toàn chưa?  
**Trả lời:** Chưa. Scan incomplete, không được đổi lỗi máy quét thành “No vulnerabilities”.

**Câu 6.** Dữ liệu đã mã hóa bằng `AesBytesEncryptor` trước patch; vì sao cần xem migration guide?  
**Trả lời:** CVE-2026-47842 có thay đổi IV/KDF và API thay thế; ciphertext cũ có thể không decrypt với encryptor mới, cần đánh giá và migration dữ liệu.

**Câu 7.** Một pull request có dependency tree sạch nhưng production pod chưa redeploy. CVE đã closed chưa?  
**Trả lời:** Chưa. Cần chứng minh artifact/image digest mới thực sự chạy, với runtime dependencies đã vá và security regression tests phù hợp.

**Câu 8.** `@WithMockUser` pass trên `/admin` có đủ chứng minh sau upgrade WebAuthn UV được verify?  
**Trả lời:** Không. Cần integration với assertion ký thật có UV=false/true, distributed session serialize/deserialize, challenge/origin/RP/credential ownership.

**Câu 9.** Scanner flag CVE thuộc build-time Maven plugin, có thể bỏ qua chỉ vì nó không nằm trong runtime jar?  
**Trả lời:** Không tự động. Phải phân loại attack surface là CI/build, đánh giá quyền attacker và tác động tới artifacts/secrets, rồi xử lý theo risk.

**Câu 10.** Kết luận `NOT_APPLICABLE_BY_CONFIGURATION` có tồn tại vĩnh viễn không?  
**Trả lời:** Không. Khi bật feature, thêm distributed session hoặc đổi security config, điều kiện CVE có thể trở thành đúng. Suppression phải có owner/expiry và review khi đổi kiến trúc.

**Câu 11.** Khi cập nhật Spring Security làm thay đổi encrypted-data format, rollback binary đã đủ chưa?  
**Trả lời:** Chưa chắc; cần xét tương thích ciphertext, migration/backup và forward-fix. Kiểm khả năng rollback dữ liệu và bảo vệ keys.

**Câu 12.** Có nên tiếp tục giám sát advisories sau khi đã upgrade thành công một lần?  
**Trả lời:** Có. Một bản có thể vá CVE A nhưng còn/bị bổ sung CVE B; inventory SBOM, scanner và advisory monitoring phải định kỳ.

## Tài liệu tham khảo chính thức

- [Spring Security Advisories – danh sách cập nhật](https://spring.io/security/): tra CVE theo project/generation, affected versions và release fix.
- [CVE-2026-47841 – WebAuthn UV bypass và session serialization](https://spring.io/security/cve-2026-47841/): affected versions, điều kiện đồng thời và OSS/Enterprise fixes công bố 20/08/2026.
- [CVE-2026-47842 – AesBytesEncryptor deterministic CBC](https://spring.io/security/cve-2026-47842/): affected versions, bản fix, APIs thay thế và hướng dẫn migration dữ liệu.
- [Spring Boot – Build Systems / Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html): BOM, release train và quản lý phiên bản các thư viện Spring.
- [Spring Boot – Managing Dependencies trong Gradle Plugin](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html): dependency-management plugin vs native BOM, cách override.
- [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies` và `dependencyInsight`.
- [Apache Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): resolved dependency graph và các tham số.
- [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/): SCA, nguồn dữ liệu và limitations.
- [OWASP Dependency-Check Gradle Plugin](https://dependency-check.github.io/DependencyCheck/dependency-check-gradle/index.html): cài plugin và task `dependencyCheckAnalyze`.
- [OSV.dev](https://osv.dev/): vulnerability database theo ecosystem/package.
- [NVD – National Vulnerability Database](https://nvd.nist.gov/): CVE/CVSS và thông tin công khai.
- [CycloneDX](https://cyclonedx.org/): tiêu chuẩn SBOM cho phần mềm và thành phần.
- [OWASP – Vulnerable and Outdated Components](https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/): quản lý nguy cơ từ các thư viện cũ.
