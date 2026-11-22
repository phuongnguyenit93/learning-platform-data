# Đối chiếu migration guide cho các dòng framework tiếp theo

Nâng cấp Java không dừng ở việc thay JDK hoặc sửa những API đã bị loại khỏi JDK. Trong một ứng dụng doanh nghiệp, framework và nền tảng ứng dụng cũng có vòng đời riêng: Spring, Hibernate, Quarkus, Micronaut, Jakarta EE, application server, thư viện bảo mật và công cụ build có những **dòng phát hành** (*release lines*) và quy tắc nâng cấp khác nhau. Một ứng dụng có thể chạy ổn định trên JDK mới nhưng lại gặp lỗi khi chuyển sang major version tiếp theo của framework; hoặc ngược lại, một phiên bản framework mới có thể bắt buộc nâng mức Java tối thiểu.

Vì vậy, nhiệm vụ “đối chiếu migration guide cho các dòng framework tiếp theo” không phải là đọc một bài hướng dẫn mới nhất rồi sửa mã theo trí nhớ. Đó là một quy trình **so sánh các hướng dẫn chính thức theo từng chặng nâng cấp**, truy vết yêu cầu về JDK và dependency, ghi nhận thay đổi API/hành vi, rồi biến các ghi chú phát hành thành những hạng mục có thể kiểm tra trong codebase và môi trường triển khai.

Bài học thuộc chương **Framework và nền tảng** của module **Java Advance Compatibility Migration**. Nó hướng dẫn cách làm việc có hệ thống với migration guide, release notes, compatibility matrix và bằng chứng kiểm thử, bất kể dự án đang dùng Spring, Jakarta EE, Hibernate hay nền tảng framework khác.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt migration guide, upgrade guide, release notes, compatibility matrix và tài liệu reference theo phiên bản.
- Xác định **nguồn và đích nâng cấp cụ thể**, tránh suy luận từ nhãn “latest”.
- Đối chiếu các hướng dẫn theo từng major/minor release và xác định chặng chuyển tiếp cần thiết.
- Kiểm tra quan hệ giữa Java baseline, framework core, platform/BOM, thư viện mở rộng, application server và công cụ build.
- Ghi nhận thay đổi về API, namespace, cấu hình, security, persistence, serialization, class loading và hành vi mặc định.
- Xây dựng bảng đối chiếu có nguồn chứng cứ, owner, mức độ ảnh hưởng và phép kiểm thử xác nhận.
- Lập kế hoạch nâng cấp theo chặng, có điều kiện rollback và tiêu chí nghiệm thu rõ ràng.
- Nhận diện lỗi do bỏ sót migration guide hoặc áp dụng nhầm hướng dẫn của dòng framework khác.

## 2. Vì sao cần đối chiếu nhiều migration guide?

### 2.1. Framework là một chuỗi phiên bản, không phải một file JAR duy nhất

Một ứng dụng có thể có cấu trúc:

```text
Ứng dụng nghiệp vụ
├── Framework nền tảng: Spring Boot / Quarkus / Micronaut / Jakarta EE runtime
├── Framework core: DI, Web, AOP, Transactions
├── Security: filter chain, authentication, authorization
├── Persistence: JPA provider, ORM, transaction manager, JDBC
├── Serialization: JSON, XML, validation
├── Observability: logging, metrics, tracing
├── Build plugins: compiler, test, packaging, code generation
└── Deployment: application server, container, cloud runtime
```

Nâng một thành phần có thể kéo nhiều thành phần khác sang phiên bản mới. Ví dụ nâng framework nền tảng có thể đồng thời nâng bản framework web, security, ORM, logging và bộ thư viện test thông qua BOM.

Do đó, “framework đã hỗ trợ Java 17” chưa đủ để kết luận toàn bộ hệ thống hỗ trợ Java 17. Cần xét **tập dependency thực tế và đường chạy production**.

### 2.2. Một migration guide thường chỉ áp dụng một khoảng phiên bản

Giả sử hệ thống đang ở dòng framework A và muốn lên dòng C:

```text
Framework A  ──────> Framework B ──────> Framework C
     |                   |                   |
  Guide A→B           Guide B→C          Guide C reference
```

Nếu chỉ đọc guide B→C, nhóm phát triển có thể bỏ qua những thay đổi bắt buộc đã được giải thích ở A→B. Một số framework yêu cầu đi qua release trung gian để chạy công cụ migration hoặc làm sạch deprecation; một số cho phép nhảy trực tiếp nhưng vẫn phải **áp dụng tổng hợp các breaking changes**.

Không tự giả định mọi framework đều cho phép nâng trực tiếp qua nhiều major release. **Upgrade path được công bố chính thức** là đầu vào cần kiểm tra.

### 2.3. “Làm code compile” không phải mục tiêu cuối

Một framework upgrade có thể không gây lỗi biên dịch nhưng thay đổi:

- Cách match HTTP route hoặc bảo vệ endpoint.
- Giá trị mặc định của cấu hình.
- Cách khởi tạo bean và thứ tự extension.
- Transaction boundary, lazy loading, schema generation.
- JSON serialization, date/time, null handling.
- Service discovery, logging, tracing.
- Policy TLS, cookie, header và proxy.
- Cách nạp lớp/proxy khi chạy trên JDK mới.

Những thay đổi này chỉ phát hiện được qua test hành vi, contract test, quan sát runtime và triển khai thử, chứ không chỉ qua `javac`.

## 3. Phân biệt các loại tài liệu cần đọc

| Tài liệu | Trả lời câu hỏi | Cần làm gì với tài liệu? |
| --- | --- | --- |
| **Migration / upgrade guide** | Phải thay đổi gì khi đi từ dòng X sang Y? | Trích xuất bước bắt buộc, migration tools, API/config đổi và các điều kiện trước khi nâng. |
| **Release notes** | Có những tính năng, thay đổi hành vi và lỗi đã sửa trong phiên bản cụ thể? | Kiểm tra các thay đổi chưa được tóm tắt trong migration guide, nhất là maintenance releases. |
| **Compatibility matrix** | Framework hỗ trợ JDK, container, dependency và toolchain nào? | Xác minh Java baseline, application server, Gradle/Maven, library ecosystem. |
| **Deprecated API list** | API nào không nên tiếp tục dùng? | Tìm call sites và replacement trước khi bị removal. |
| **Reference documentation** | Hành vi hiện hành và cấu hình đúng của version mới là gì? | Đối chiếu contract mới sau khi áp dụng migration guide. |
| **Security advisory** | Có bản phát hành nào khắc phục CVE hoặc thay đổi security behavior? | Ưu tiên remediation và xác nhận version an toàn. |
| **Known issues** | Những vấn đề nào còn tồn tại sau nâng cấp? | Gắn risk/mitigation và test cho tính năng đang dùng. |
| **Plugin/extension compatibility notes** | Những integration nào cần nâng đồng bộ? | Kiểm tra starter, plugin, ORM dialect, test runner, native image và bên thứ ba. |

**Không dùng reference docs của một phiên bản mới hơn để suy ra chắc chắn hành vi của phiên bản đích cũ hơn.** Khi đọc tài liệu trực tuyến, ghi rõ version selector, đường dẫn và ngày đối chiếu. Nếu trang tự động chuyển tới “current”, cần quay về tài liệu đã version hóa.

## 4. Xác định baseline của dự án trước khi đọc guide

### 4.1. Những thông tin cần chụp

Đối với mỗi ứng dụng hoặc module, ghi lại:

- **Java runtime:** vendor, phiên bản thực chạy trên môi trường dev/test/production.
- **Java compiler:** JDK của Maven/Gradle và `--release` hoặc source/target level.
- **Framework line:** groupId/artifactId/version của framework nền tảng và core.
- **Dependency management:** parent POM, BOM, version catalog hoặc dependency constraints.
- **Build tool:** Maven/Gradle và wrapper version, compiler/test/packaging plugins.
- **Runtime:** application server, servlet container, Docker base image, OS/architecture.
- **Language bổ sung:** Kotlin, Groovy, Scala nếu dự án có dùng.
- **Tích hợp:** Security, ORM, JPA, validation, messaging, REST client, observability.
- **Cơ chế đặc biệt:** custom class loader, annotation processor, bytecode agent, reflection, JNI.
- **Tests:** unit/integration/contract/performance test, số lượng test thực chạy và tỷ lệ skipped.

Ví dụ từ dòng lệnh, ở nơi phù hợp:

```bash
java -version
javac -version
mvn -version
```

Với Gradle:

```bash
./gradlew --version
```

Đây là những phép đo tại môi trường chạy lệnh. Hệ thống còn có thể dùng Maven toolchains, Gradle Java toolchain hoặc container chạy ứng dụng trên một JDK khác; cần đo cả **JVM được dùng thực tế**.

### 4.2. Đọc dependency graph hiện hành

Maven:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency example-library \
  --configuration runtimeClasspath
```

Những lệnh này giúp xác định dependency được giải quyết ra version nào, kể cả khi POM hoặc build script không khai báo trực tiếp do BOM, parent hoặc plugin quản lý.

Không sửa hàng loạt các version trước khi lưu baseline. Nếu thay nhiều biến cùng lúc, nhóm phát triển sẽ khó biết lỗi phát sinh từ JDK, framework core, dependency bắc cầu hay cấu hình build.

### 4.3. Ghi lại hành vi vận hành hiện tại

Chụp baseline cho các chức năng quan trọng:

- Startup/shutdown và health checks.
- HTTP contract: status, header, JSON schema, authentication.
- Database migration, transaction, query, schema validation.
- Message schemas và xử lý retry.
- Scheduler/batch jobs.
- Cache và session.
- Logging, metrics, traces.
- Các luồng dùng reflection và dynamic loading.

Một baseline tốt giúp phân biệt **regression thực sự** với thay đổi đã tồn tại từ trước.

## 5. Xác định đích và các chặng nâng cấp

### 5.1. Phân biệt ba mục tiêu

Trong nhiều dự án, ba mục tiêu bị gộp thành một:

1. **Nâng JDK runtime:** ứng dụng tiếp tục chạy với JDK mới.
2. **Nâng major framework:** chuyển sang dòng được hỗ trợ, có breaking changes.
3. **Module hóa/hiện đại hóa kiến trúc:** thêm JPMS, đổi packaging, đổi framework stack.

Không nhất thiết làm cả ba trong cùng một commit. Có thể nâng runtime trước với framework đang được hỗ trợ, sau đó nâng framework; hoặc framework mới bắt buộc nâng JDK trước. **Migration guide và compatibility matrix** quyết định thứ tự khả thi.

### 5.2. Dựng đường nâng cấp

Ví dụ minh họa:

```text
Hiện tại:
  JDK 11 + Framework Line A + ORM Line P

Chặng 1:
  Sửa warnings / nâng patch line A + khóa dependency

Chặng 2:
  JDK 17 + Framework Line B + ORM Line Q

Chặng 3:
  Framework Line C nếu được hỗ trợ trên JDK mục tiêu
```

Đây không phải sơ đồ khẳng định rằng mọi framework đều dùng các phiên bản này. Với dự án thật, từng chặng phải có điều kiện vào, phiên bản cụ thể và guide chính thức tương ứng.

### 5.3. Khi nào cần release trung gian?

Một release trung gian có thể cần thiết khi:

- Dòng mới chỉ hỗ trợ migration từ dòng liền trước.
- Có công cụ tự sửa cấu hình/source yêu cầu chạy ở version trung gian.
- API cũ cần được thay bằng API thay thế trước khi bị xóa.
- Dependency bắc cầu hoặc plugin chỉ tương thích theo từng chặng.
- Có thay đổi dữ liệu/schema không thể rollback trực tiếp.
- Cần dọn warning để nhận diện lỗi thật trong major upgrade cuối.

**Release trung gian để thực hiện công việc migration không nhất thiết phải là một release đưa lên production.** Có thể là một nhánh staging hay bước trong CI nếu guide cho phép. Cần lưu kết quả test của từng chặng.

## 6. Lập ma trận đối chiếu migration guide

### 6.1. Một dòng trong ma trận đại diện cho một thay đổi

Thay vì lưu một checklist chung như “đã nâng Spring”, hãy ghi từng thay đổi cụ thể:

| ID | Nguồn hướng dẫn | Phạm vi | Thay đổi | Tác động dự án | Cách xác minh |
| --- | --- | --- | --- | --- | --- |
| MIG-001 | Guide A→B, mục Java baseline | Build/runtime | Minimum JDK tăng | CI và base image cũ | Build, startup trên JDK đích |
| MIG-002 | Guide A→B, mục configuration | Config | Property cũ đổi tên | `application.yml` | Config binding test |
| MIG-003 | Guide A→B, mục API removal | Source | API cũ bị xóa | 12 call sites | Compile + unit test |
| MIG-004 | Guide B→C, mục security | Behavior | Default filter/authorization thay đổi | Một số endpoint | Security contract tests |
| MIG-005 | Guide B→C, mục persistence | Runtime/data | Dialect/SQL behavior thay đổi | ORM và reporting | Database integration tests |

Tất cả tên phiên bản và số lượng trong bảng chỉ là ví dụ; kết quả thực tế phải do nhóm dự án thu thập.

### 6.2. Những trường nên có trong bản ghi

Một bảng đủ để triển khai thường có:

| Trường | Ý nghĩa |
| --- | --- |
| Framework/component | Tên, artifact, version hiện tại và version đích. |
| Guide interval | Ví dụ dòng A→B hoặc B→C. |
| Nguồn | URL/tên tài liệu, version selector, mục, ngày đối chiếu. |
| Change type | JDK, API, config, dependency, behavior, security, data, deployment. |
| Mức bắt buộc | Required, conditional, optional, deprecated, informational. |
| Điều kiện áp dụng | Dự án có đang dùng feature/API/config đó hay không? |
| Vị trí ảnh hưởng | Module, file, service, endpoint, database hoặc job. |
| Owner | Người/nhóm chịu trách nhiệm. |
| Hành động | Nâng version, sửa mã, đổi cấu hình, chạy migration tool. |
| Test evidence | Test/report/log chứng minh thay đổi đúng. |
| Trạng thái | Unassessed, impacted, in progress, validated, waived. |
| Rollback | Có thể quay lại hay cần phương án dữ liệu riêng? |

### 6.3. Đừng đánh đồng “không thấy dùng” với “không bị ảnh hưởng”

Một framework feature có thể được sử dụng gián tiếp qua starter, annotation, auto-configuration, SPI hoặc reflection. Vì vậy, trước khi đánh dấu “not applicable”, cần kiểm tra:

- Source import và annotation.
- Cấu hình properties/YAML/XML.
- Dependency tree.
- Runtime wiring và bean registry nếu có.
- Plugin/service metadata.
- Những profile chỉ bật ở production.

Bằng chứng âm tính từ `rg` hoặc một lần chạy test chưa đủ cho mọi trường hợp dynamic loading.

## 7. Cách đọc migration guide theo từng nhóm thay đổi

### 7.1. Yêu cầu JDK và class-file compatibility

Kiểm tra các mục:

- Minimum Java version của framework core.
- JDK hỗ trợ để **chạy ứng dụng**.
- JDK dùng để **build framework hoặc plugin**.
- Bytecode target mà thư viện phát hành.
- Các JDK còn trong ma trận hỗ trợ và kế hoạch hết hỗ trợ.

Nếu test framework hoặc plugin được biên dịch với bytecode mới hơn JVM đang chạy, có thể gặp `UnsupportedClassVersionError` dù code ứng dụng được biên dịch với `--release` cũ.

Ví dụ một build có thể dùng JDK 21 để compile với `--release 17`, nhưng dependency test chỉ hỗ trợ Java 21. Muốn test trên JDK 17 thì phải chọn dependency có minimum Java thích hợp.

### 7.2. Thay đổi API và deprecation

Tìm các cụm từ trong guide:

```text
removed / renamed / replaced / deprecated
no longer supported / behavior changed / default changed
migration required / upgrade required
```

Đối với mỗi API, ghi rõ:

- Kiểu/method cũ và mới.
- Thay đổi chữ ký hoặc kiểu trả về.
- Contract null/exception/transaction.
- Có adapter tạm thời không?
- Có source compatibility và binary compatibility không?
- Khi nào API cũ bị loại bỏ?

Không chỉ thay import rồi coi là xong nếu semantics của API mới khác.

### 7.3. Thay đổi cấu hình

Framework thường đổi:

- Tên property.
- Prefix hoặc hierarchy.
- Giá trị mặc định.
- Kiểu dữ liệu: boolean, duration, size, enum.
- Cơ chế profile và precedence.
- Cấu hình TLS, proxy, port và management endpoint.
- Thuộc tính đã bị bỏ qua nhưng không báo lỗi.

Ví dụ minh họa:

```yaml
# Configuration cũ (giả định)
framework:
  http:
    timeout-ms: 5000
```

Sau migration, giả sử tài liệu yêu cầu đổi thành:

```yaml
# Configuration mới (giả định)
framework:
  http:
    timeout: 5s
```

Đây chỉ là ví dụ mô phỏng phép đổi key và đơn vị; không phải một property thật của framework cụ thể. Với dự án thật, phải dùng tên key và semantics có trong guide chính thức.

Một lỗi nguy hiểm là key cũ bị **âm thầm bỏ qua** và framework dùng default mới. Ứng dụng có thể vẫn khởi động nhưng timeout, pool size hoặc security policy thay đổi.

### 7.4. Auto-configuration và dependency injection

Khi major framework thay đổi, điều kiện tạo bean có thể thay đổi:

- Một bean trước đây được tự động tạo, giờ phải khai báo.
- Thứ tự auto-configuration hoặc điều kiện conditional khác.
- Bean override không còn được cho phép mặc định.
- Component scan không còn bao phủ package cũ.
- Bean lifecycle hoặc proxy strategy thay đổi.

Test nên xác minh sự tồn tại, loại và cấu hình của bean quan trọng chứ không chỉ nhìn startup success.

### 7.5. Security behavior

Những thay đổi bảo mật cần được đối chiếu cẩn trọng:

- Cơ chế authorization và route matching.
- Filter chain và thứ tự xử lý.
- Authentication provider, password encoder.
- CSRF, CORS, cookie/session.
- TLS/cipher, header và redirect.
- Endpoint management/actuator và quyền truy cập.
- Các API security deprecated hoặc bị thay.

Không khôi phục behavior cũ thiếu an toàn bằng cách tắt toàn bộ security feature. Cần hiểu ý nghĩa của default mới rồi áp dụng policy nghiệp vụ đã được phê duyệt.

### 7.6. Persistence, ORM và transaction

Migration guide có thể nói về:

- JPA API namespace.
- ORM major version và query behavior.
- Dialect, schema validation và type mapping.
- Truy vấn HQL/JPQL, native SQL.
- Lazy loading và session boundary.
- Transaction propagation và timeout.
- ID generation, enum/date/time mapping.
- Database driver tối thiểu.

Một thay đổi ORM có thể không làm compilation thất bại nhưng khiến SQL khác trước, query không dùng index, hoặc dữ liệu được ánh xạ khác. Cần chạy integration test trên DB version và schema thực tế, tốt nhất với dữ liệu đại diện.

### 7.7. Serialization và API contract

Kiểm tra các thay đổi về:

- JSON property naming, date/time, null serialization.
- Polymorphic typing và security constraints.
- XML namespace/binding.
- Validation messages và exception payload.
- HTTP error response shape.
- Enum serialization và unknown field handling.

Nếu service khác phụ thuộc vào wire format, cần có **consumer-driven contract test** hoặc golden-file fixtures để phát hiện breaking changes.

### 7.8. Observability và vận hành

Framework nâng version có thể thay:

- Tên metric và label.
- Trace propagation.
- Cấu hình log/appenders.
- Health/readiness endpoints.
- Shutdown behavior.
- Exporter và agent compatibility.

Các thay đổi này đôi khi không làm hỏng nghiệp vụ ngay nhưng khiến dashboard, alert hoặc quy trình deploy mất hiệu lực. Cần có người phụ trách observability đối chiếu hướng dẫn tương ứng.

## 8. Tình huống quan trọng: `javax.*` sang `jakarta.*`

### 8.1. Bối cảnh

Một số dòng framework và Jakarta EE thế hệ mới chuyển nhiều API Java EE cũ từ namespace `javax.*` sang `jakarta.*`. Đây là một trong những thay đổi có tác động lớn khi nâng các dòng framework nền tảng.

Ví dụ:

```java
// Code kiểu namespace cũ
import javax.persistence.Entity;
import javax.validation.constraints.NotNull;
import javax.servlet.http.HttpServletRequest;
```

Ở hệ sinh thái phù hợp với Jakarta EE 9+, có thể cần:

```java
// Code theo namespace mới
import jakarta.persistence.Entity;
import jakarta.validation.constraints.NotNull;
import jakarta.servlet.http.HttpServletRequest;
```

**Không được thay mọi `javax.*` bằng `jakarta.*`.** Nhiều package thuộc Java SE vẫn sử dụng `javax.*`, chẳng hạn `javax.sql`, `javax.crypto` và `javax.net`. Chỉ những API thuộc phạm vi chuyển namespace của Jakarta EE mới được thay theo đúng migration guide.

### 8.2. Không chỉ source import

Thay namespace ảnh hưởng:

- API/annotation trong source.
- Dependency coordinates và version.
- Servlet container hoặc application server.
- ORM/JPA provider.
- Bean Validation provider.
- XML descriptor và namespace/schema nếu có.
- Third-party starters/extensions.
- Class generated bởi annotation processor.
- Library đã biên dịch mà còn tham chiếu `javax.servlet` hoặc `javax.persistence`.

Một JAR bên thứ ba chưa hỗ trợ Jakarta có thể không hoạt động dù source ứng dụng đã đổi import. Lỗi có thể là `ClassNotFoundException` hoặc `NoClassDefFoundError` trong runtime.

### 8.3. Ví dụ hệ Spring: hiểu đúng phạm vi

Một lộ trình được biết đến rộng rãi là chuyển từ các dòng Spring Boot 2.x/Spring Framework 5.x sang Spring Boot 3.x/Spring Framework 6.x: dòng mới đặt mức Java tối thiểu cao hơn (Java 17 cho Boot 3) và gắn với hệ sinh thái Jakarta EE mới.

Nhưng bài học này **không thay thế** upgrade guide của phiên bản nguồn và phiên bản đích cụ thể. Ngoài Java/Jakarta, dự án còn phải đối chiếu Spring Security, data access, observability, servlet container, configuration properties, thư viện extension và các thay đổi trong minor/patch releases.

Nếu dự án đang chạy ở dòng rất cũ, đọc hướng dẫn của tất cả chặng trung gian cần thiết thay vì chỉ tìm một bài “Spring Boot 3 migration”.

### 8.4. Các bước rà soát namespace

1. Tìm những import thuộc Java EE/Jakarta EE ở source.
2. Xác định dependency nào cung cấp class đó.
3. Đối chiếu API tương ứng ở phiên bản Jakarta được framework đích hỗ trợ.
4. Kiểm tra generated source và annotation processors.
5. Đảm bảo server/container và integration libraries thuộc hệ tương thích.
6. Build, chạy startup và integration tests cho HTTP, ORM và validation.
7. Không giữ cả API cũ/mới chỉ để sửa lỗi compile nếu dẫn đến hai thế hệ runtime xung đột.

## 9. Đối chiếu framework core với hệ sinh thái xung quanh

### 9.1. Không nâng mỗi parent/BOM rồi bỏ qua extension

BOM hoặc platform version thường quản lý một tập dependency, nhưng không nhất thiết kiểm soát mọi plugin và extension bên thứ ba.

Sau khi nâng BOM, kiểm tra:

- Version override thủ công trong module.
- Dependency không thuộc BOM.
- Starter/plugin chỉ hỗ trợ dòng framework cũ.
- Annotation processors và codegen tools.
- Server/container version.
- Test frameworks, mocking và coverage agents.
- Native image build tooling nếu có.

Một thư viện có cùng version được chọn ở compile và runtime vẫn có thể không tương thích nếu nó được build cho API framework cũ.

### 9.2. Mở rộng ma trận với nền tảng khác

Dù cách gọi khác nhau, cùng phương pháp áp dụng cho nhiều hệ:

| Nhóm nền tảng | Tài liệu đặc thù nên đối chiếu |
| --- | --- |
| Spring Boot/Spring Framework | Upgrade guide theo line, dependency BOM, Security/Data, configuration properties và observability. |
| Hibernate ORM/JPA | ORM migration guide, query/type mappings, schema/dialect, transaction và Jakarta namespace. |
| Quarkus | Platform BOM, extension compatibility, configuration migration, native image/build-time augmentation. |
| Micronaut | Framework major-version guide, annotation processing, AOT/native tooling, serialization, security modules. |
| Jakarta EE/application server | Java/Jakarta API level, server compatibility, servlet/JPA/validation, deployment descriptor, class loading. |
| Web/servlet container | Servlet API version, connector/TLS, session, request processing và namespace. |
| Messaging/security framework | Client/server protocol, serializers, policy defaults và release compatibility. |

Bảng này định hướng những **chỗ cần đọc**, không khẳng định một phiên bản cụ thể đang được hỗ trợ. Mỗi hệ sinh thái phải được đối chiếu với tài liệu đúng version đã chọn.

### 9.3. Đọc tài liệu extension độc lập

Ví dụ app dùng Spring Boot và một starter bên thứ ba. Việc Boot hỗ trợ JDK 17 không bảo đảm starter đó dùng được. Starter có thể phụ thuộc vào package nội bộ, API Spring đã bị xóa hoặc metadata auto-configuration của dòng trước.

Với một extension quan trọng, cần có hai chứng cứ:

1. Framework core công bố version đích và JDK phù hợp.
2. Nhà cung cấp extension công bố hoặc chứng minh bằng test rằng extension hoạt động với line đó.

Nếu chưa có chứng cứ thứ hai, đưa vào danh sách rủi ro, không tự động đánh dấu “compatible”.

## 10. Đối chiếu API removal với Java runtime

### 10.1. Framework guide và JDK guide bổ sung cho nhau

Một framework upgrade có thể không nói hết các thay đổi đến từ JDK:

- Module Java EE/CORBA bị tách/loại khỏi JDK từ những release trước.
- Reflection vào API nội bộ bị đóng gói chặt hơn.
- Encoding mặc định thay đổi trong những JDK mới.
- TLS/security provider và thuật toán mặc định thay đổi.
- Java agent, bytecode instrumentation và class-file format tiến hóa.
- Class loader, locale, timezone và runtime service behavior có thể khác.

Ngược lại, JDK migration notes thường không biết framework đang dùng những API của thư viện nào.

Nên có **hai chiều kiểm kê**: một bảng yêu cầu JDK và một bảng breaking changes của framework, rồi liên kết những hạng mục giao nhau.

### 10.2. Ví dụ một API bị loại khỏi JDK

Một dự án legacy từng phụ thuộc trực tiếp vào JAXB API trên JDK cũ. Khi chuyển lên JDK mà JAXB không còn được đóng kèm theo cách cũ, có thể phải bổ sung dependency thích hợp.

Tuy nhiên, khi đồng thời nâng framework sang dòng dùng Jakarta XML Binding, chọn artifact/namespace theo **framework đích**. Không thêm một dependency cũ chỉ để lấp `ClassNotFoundException` mà chưa kiểm tra mình đang dùng thế hệ `javax` hay `jakarta`.

### 10.3. Reflection và proxy

Một framework phiên bản cũ có thể dùng reflection sâu vào các package của JDK. Khi JDK đích đóng gói mạnh hơn, ứng dụng báo `InaccessibleObjectException`.

Giải pháp ưu tiên thường là nâng framework/bytecode library tương thích. Nếu tạm dùng `--add-opens`, phải ghi:

- Module/package cần mở.
- Module nhận quyền hoặc `ALL-UNNAMED`.
- Thành phần gây lỗi và version.
- JVM nào cần cờ (app, test, build tool).
- Kế hoạch loại bỏ workaround.

Không dùng migration guide để suy ra rằng mở nhiều package JDK là bước bắt buộc cho mọi ứng dụng.

## 11. So sánh thông tin “removed”, “deprecated”, “changed default” và “optional”

Các guide có thể dùng thuật ngữ khác nhau. Trước khi chuyển thành task cần phân loại:

| Loại | Ý nghĩa | Độ ưu tiên thường gặp |
| --- | --- | --- |
| Removed API | Class/method/option không còn tồn tại. | Bắt buộc nếu dự án đang sử dụng. |
| Renamed/replaced | Có API/config thay thế, có thể đổi semantics. | Bắt buộc hoặc có điều kiện. |
| Deprecated | Vẫn tồn tại nhưng không còn được khuyến nghị. | Lên kế hoạch bỏ trước release removal. |
| Default changed | Khi không cấu hình gì, hành vi mới khác. | Ưu tiên test hành vi vì code có thể vẫn compile. |
| New optional feature | Tính năng mới không bắt buộc dùng. | Thường có thể để giai đoạn sau. |
| Support ended | JDK/server/dependency cũ không còn trong support matrix. | Ảnh hưởng trực tiếp đến khả năng vận hành và cập nhật bảo mật. |
| Known regression | Lỗi tồn tại ở release đích. | Cần đánh giá ảnh hưởng và workaround/version khác. |

Không biến mọi bullet trong release notes thành “must do”. Nhưng cũng không bỏ qua thay đổi default chỉ vì nó không gây lỗi compile.

## 12. Kiểm soát độ tin cậy của nguồn hướng dẫn

### 12.1. Ưu tiên nguồn có thẩm quyền và đúng version

Ưu tiên theo thứ tự thực tế:

1. Migration/upgrade guide chính thức của framework.
2. Release notes/versioned reference chính thức.
3. Compatibility matrix và tài liệu plugin/extension chính thức.
4. Issue/commit được maintainer xác nhận cho một vấn đề cụ thể.
5. Bài viết cộng đồng như nguồn gợi ý, nhưng phải kiểm chứng lại.

Nếu nguồn cộng đồng khuyên tắt một feature bảo mật hoặc thêm nhiều JVM flags, không áp dụng chỉ vì “người khác đã làm”. Cần hiểu tác động và xác minh với guide/version chính thức.

### 12.2. Ghi thời điểm đọc và đường dẫn

Tài liệu trực tuyến có thể cập nhật hoặc chuyển hướng. Một bản ghi migration nên có:

```text
Framework: tên và version nguồn/đích
Document: title + đường dẫn chính thức
Version selector: dòng tài liệu đã chọn
Reviewed at: ngày đối chiếu
Relevant section: mục / heading
Decision: áp dụng / không áp dụng / cần xác minh
Evidence: commit, test report, deployment log
```

Nếu tài liệu bị sửa sau đó, nhóm phát triển có thể giải thích quyết định được đưa ra dựa trên phiên bản hướng dẫn nào.

### 12.3. Khi guide không nói rõ một tích hợp

Không nên đoán. Đánh dấu “cần xác minh”, kiểm tra compatibility của extension/driver và xây test thể hiện behavior quan trọng.

Đối với rủi ro lớn như schema migration hoặc authentication, yêu cầu xác nhận từ maintainer/vendor hoặc kiểm thử đại diện trước khi triển khai.

## 13. Quy trình triển khai một migration guide thành kế hoạch kỹ thuật

### Bước 1: Chốt baseline và đích cụ thể

Lưu JDK, framework version, BOM/parent, plugin, dependency graph, deployment runtime và baseline tests. Đích phải là **version có số cụ thể**, không chỉ “mới nhất”.

### Bước 2: Lập danh sách guide theo từng chặng

Ví dụ:

```text
Current framework line 2.x
        |
        v
Guide: 2.x -> 3.0
        |
        v
Release notes: 3.0 -> 3.1 -> 3.2
        |
        v
Target: 3.2.z (phiên bản chốt trong dự án)
```

Đây là mô hình minh họa. Tùy framework, có thể cần thêm guide qua release trung gian hoặc upgrade tool chính thức.

### Bước 3: Trích xuất thay đổi vào ma trận

Mỗi thay đổi phải có source, điều kiện áp dụng, phạm vi bị ảnh hưởng, owner và cách xác minh. Không gộp nhiều breaking changes thành một mục mơ hồ.

### Bước 4: Kiểm tra sự phụ thuộc giữa các task

Ví dụ:

```text
Nâng JDK để đạt minimum runtime
            |
            v
Nâng Maven/Gradle + compiler/test tools
            |
            v
Nâng framework BOM và extension compatibility
            |
            v
Sửa source API / namespace / configuration
            |
            v
Sửa tests, security contract, DB integration
            |
            v
Staging / performance / canary / rollout
```

Thứ tự cụ thể do guide, support matrix và hệ thống hiện tại quyết định. Nếu build tool không chạy trên JDK mới, cần xử lý nó trước khi mong framework compile.

### Bước 5: Tách thay đổi cơ học khỏi thay đổi hành vi

**Thay đổi cơ học** có thể gồm rename import, đổi property key, thêm dependency theo guide. Một số có thể dùng script hoặc OpenRewrite recipe được framework hỗ trợ.

**Thay đổi hành vi** gồm security policy, SQL semantics, transaction, serializer, route matching hoặc runtime lifecycle. Những thay đổi này cần thiết kế/test và review nghiệp vụ; không nên tự động hóa như replace-all đơn giản.

### Bước 6: Thực hiện theo lô nhỏ và lưu bằng chứng

Mỗi lô nên có:

- Commit/PR hoặc change set dễ review.
- Mã tham chiếu tới mục guide.
- Test nhỏ cho tác động chính.
- Log và report trước/sau.
- Phương án rollback nếu ảnh hưởng cấu hình/dữ liệu.

### Bước 7: Xác minh trên JDK và deployment runtime đích

Không chỉ chạy test bằng JVM của laptop. Cần thử với container/application server thực tế và profile có ý nghĩa: development, staging, production-like.

### Bước 8: Chốt kết quả và cập nhật tài liệu

Sau khi đạt nghiệm thu, cập nhật:

- Dependency/BOM lock.
- Build/CI toolchain.
- Runtime image.
- Configuration reference.
- Runbook và observability.
- Quy trình deploy/rollback.
- Danh sách deprecation còn lại và chặng upgrade tiếp theo.

## 14. Kiểm thử theo lớp để xác nhận migration

### 14.1. Compile và static checks

Đảm bảo source compile với dependency đích. Kiểm tra warnings về API deprecated, raw type, plugin compatibility hoặc các package bị loại.

Nhưng test biên dịch chỉ trả lời câu hỏi **source có hợp lệ không**, chưa trả lời behavior có giữ nguyên không.

### 14.2. Unit tests

Tập trung ở logic nghiệp vụ và API wrapper. Các test phải chạy thực sự, không bị mất do đổi JUnit engine hoặc plugin includes.

Ghi số lượng test trước/sau. Một build xanh với “Tests run: 0” không phải chứng cứ migration thành công.

### 14.3. Integration tests

Cần thử framework với database, message broker, HTTP server/client, transaction manager và các integration có thật.

Ví dụ cần kiểm tra khi nâng ORM:

- Mapping entity và database schema.
- Query có tham số/named query.
- Lazy loading và transaction boundary.
- Generated IDs.
- Migration scripts và backward compatibility của dữ liệu.

### 14.4. Contract tests

Với REST/messaging, so sánh request/response đã được consumer sử dụng. Chú ý status code, header, field name, nullability, lỗi validation, timezone và thứ tự xử lý security filters.

### 14.5. Startup, shutdown và configuration binding

Các framework có thể thay đổi default hoặc điều kiện tạo bean. Test cần xác nhận:

- Tất cả profile khởi động được.
- Properties quan trọng được bind chứ không bị bỏ qua.
- Các bean/service/provider bắt buộc được tạo.
- Health/readiness đúng.
- Graceful shutdown và resource cleanup hoạt động.

### 14.6. Performance và tài nguyên

Nâng framework có thể đổi default thread pool, connection pool, serialization hoặc observability overhead.

Không so sánh đơn giản một benchmark chạy một lần. Nên giữ workload đại diện và đo latency, throughput, CPU, memory/GC, database query count, connection usage và error rates.

### 14.7. Security tests

Những endpoint trước đây có yêu cầu authorization phải tiếp tục được bảo vệ theo chính sách. Kiểm tra request hợp lệ và không hợp lệ, anonymous/role-based access, CSRF/CORS và các trường hợp upgrade thay đổi matcher semantics.

Không xem việc service khởi động và trả HTTP 200 là test security đầy đủ.

## 15. Chọn công cụ hỗ trợ migration

### 15.1. Công cụ tìm kiếm mã nguồn

Có thể tìm những API và cấu hình được nêu trong guide:

```bash
rg -n 'javax\.persistence|javax\.validation|javax\.servlet' src
rg -n '@Deprecated|deprecated|old-property-name' .
```

Ví dụ regex này là điểm khởi đầu, không phải danh sách đầy đủ mọi Java EE package. Không được tự thay mọi `javax` thành `jakarta`.

### 15.2. Phân tích dependency

Maven:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency example-library \
  --configuration runtimeClasspath
```

Đối chiếu graph trước/sau để phát hiện dependency bị nâng ngoài dự kiến và loại bỏ version override đã lỗi thời.

### 15.3. Phân tích class/JDK dependencies

`jdeps` có thể hỗ trợ xem phụ thuộc tĩnh của JAR:

```bash
jdeps --recursive path/to/application.jar
```

Với mục tiêu tìm JDK internals, có thể tham khảo chế độ tương ứng:

```bash
jdeps --jdk-internals path/to/application.jar
```

Không coi kết quả `jdeps` là đầy đủ cho reflection, SPI hoặc class được nạp từ cấu hình. Framework thường sử dụng những cơ chế này mạnh mẽ.

### 15.4. Công cụ tự động hóa code changes

Một số hệ sinh thái cung cấp recipe, migration plugin, script hoặc IDE inspections hỗ trợ thay API/config. Có thể sử dụng để tạo diff có kiểm soát.

Quy tắc:

1. Chọn recipe đúng phiên bản nguồn/đích.
2. Chạy trên nhánh riêng với working tree có thể khôi phục.
3. Review toàn bộ diff.
4. Chạy test hành vi phù hợp.
5. Không coi kết quả recipe là bằng chứng các thay đổi thủ công trong guide đã được xử lý.

Công cụ tự động hóa giỏi phát hiện nhiều phép đổi cấu trúc; nó khó tự xác định ý định nghiệp vụ của security/transaction/data behavior.

## 16. Ví dụ thực hành: đối chiếu hai chặng nâng framework

### 16.1. Bối cảnh giả định

Một dịch vụ Java có:

```text
JDK hiện tại: 11
Framework: line 2.x
Security extension: line S1
ORM extension: line O1
Database: PostgreSQL
Build: Maven
Target: JDK 17 + framework line 3.x
```

Nhóm phát triển muốn tránh một PR khổng lồ vừa thay JDK, vừa thay API web, vừa sửa security và schema.

Các tên `S1`, `O1` là ký hiệu minh họa, không đại diện phiên bản nhà cung cấp cụ thể.

### 16.2. Tập tài liệu cần đối chiếu

Lập bảng tài liệu:

| Nguồn | Mục phải đọc | Câu hỏi |
| --- | --- | --- |
| Framework 2.x→3.x guide | Java baseline | Có bắt buộc nâng JDK trước không? |
| Framework 2.x→3.x guide | Namespace/API changes | Package, method, annotation nào phải sửa? |
| Security extension upgrade guide | Filter/authorization | Endpoint nào cần test lại? |
| ORM extension upgrade guide | Mapping/query/dialect | Query và schema nào có thể đổi hành vi? |
| Framework 3.x release notes | Defaults/known issues | Có thay đổi nào guide không mô tả đầy đủ? |
| Maven/build plugin docs | JDK/toolchain support | Plugin nào phải nâng trước? |
| Deployment runtime docs | Container/server support | Runtime production có đáp ứng minimum version không? |

### 16.3. Ma trận hành động

| ID | Đối chiếu | Hành động | Bằng chứng nghiệm thu |
| --- | --- | --- | --- |
| EX-01 | Minimum JDK mới | Nâng CI toolchain/base image lên JDK 17 | `java -version`, build/startup |
| EX-02 | Namespace Jakarta nếu áp dụng | Sửa Java EE imports và dependencies liên quan | Compile và servlet/JPA/validation tests |
| EX-03 | Security matcher/default | Review policy và test endpoint được bảo vệ | Security contract report |
| EX-04 | ORM behavior | Kiểm tra dialect/query/transaction | DB integration report |
| EX-05 | Framework properties | Đổi key/units và kiểm tra binding | Startup/config test |
| EX-06 | Test tooling | Đồng bộ JUnit engine, Surefire/Failsafe | Không mất test count |
| EX-07 | Release notes đích | Rà soát thay đổi default/known issues | Bản ghi quyết định và test liên quan |

### 16.4. Thực hiện theo chặng

Chặng A: cố định baseline, nâng plugin/build tooling và dọn warning ở dòng cũ theo hướng dẫn.

Chặng B: nâng JDK đích khi framework hiện tại có đường hỗ trợ phù hợp; nếu không, tổ chức chặng nâng framework/JDK theo compatibility matrix thay vì ép chạy cấu hình không được hỗ trợ.

Chặng C: áp dụng breaking changes của framework line mới và các extension theo guide tương ứng.

Chặng D: chạy unit/integration/contract/security/performance tests, triển khai staging/canary và cập nhật runbook.

### 16.5. Thực hành tự đánh giá

Hãy trả lời:

1. Tại sao “source đã compile” chưa chứng minh HTTP security không đổi?
2. Vì sao phải đọc guide của ORM extension, không chỉ framework core?
3. Nếu thấy `javax.sql.DataSource` trong source, có nên đổi thành `jakarta.sql.DataSource` không?
4. Nếu dependency test yêu cầu Java cao hơn JDK chạy CI, nên sửa mã nghiệp vụ hay chọn lại dependency/toolchain?
5. Nếu property cũ bị bỏ qua và app vẫn khởi động, loại test nào sẽ phát hiện?

Định hướng: kiểm tra behavior; vì integration có vòng đời riêng; không đổi Java SE `javax.sql`; xác minh baseline của dependency/JVM; dùng configuration binding và integration tests.

## 17. Những sai lầm thường gặp

### 17.1. Chỉ đọc guide của bản đích

Một hướng dẫn B→C có thể không nhắc lại breaking changes A→B. Phải ghép các chặng liên quan.

### 17.2. Dựa vào bài blog không ghi phiên bản

Một đoạn config đúng cho version khác có thể khiến framework mới âm thầm dùng default. Luôn xác nhận bằng tài liệu versioned chính thức.

### 17.3. Nâng BOM nhưng giữ starter/extension cũ

Framework core có thể dùng được nhưng extension phụ thuộc API đã xóa. Cần kiểm tra compatibility của từng extension quan trọng.

### 17.4. Thay tất cả `javax.*` bằng `jakarta.*`

Không phải mọi package `javax` đều chuyển namespace. Phải phân biệt API Java SE và Java EE/Jakarta EE.

### 17.5. Gộp thay đổi hành vi với refactor không liên quan

Nếu cùng lúc đổi ORM, security, serialization và business rules, việc xác định nguyên nhân regression trở nên rất khó. Giữ change set gắn với mục guide.

### 17.6. Xem build xanh là migration thành công

Test engine có thể không được tải; test suite có thể bị skip; lỗi data/security chỉ xuất hiện ở runtime. Cần bằng chứng test count và hành vi.

### 17.7. Không phân biệt version framework và version JDK

Một framework có thể hỗ trợ nhiều JDK, trong khi một major version khác yêu cầu mức tối thiểu cao hơn. Không dùng “framework mới” làm cách gọi thay thế cho “JDK mới”.

### 17.8. Chỉ test profile development

Production có thể dùng database, authentication, feature flag, proxy, config server và class loader khác. Staging phải đại diện cho những ranh giới quan trọng.

### 17.9. Dùng JVM flags để che mọi lỗi reflection

`--add-opens` có thể là workaround tạm thời, nhưng không giải quyết API bị xóa, provider metadata sai hoặc version bytecode không tương thích.

### 17.10. Không chuẩn bị rollback dữ liệu

Code có thể rollback nhanh, nhưng schema migration hoặc format dữ liệu mới có thể không tương thích ngược. Cần quy tắc forward/backward compatibility, backup và kế hoạch rollback riêng.

## 18. Mẫu báo cáo đối chiếu migration guide

Có thể dùng mẫu sau cho từng ứng dụng:

```markdown
# Framework migration assessment

## Baseline
- Service/module:
- JDK runtime:
- JDK compile:
- Framework line/version:
- BOM/parent:
- Major extensions:
- Build/test tooling:
- Deployment runtime:

## Target
- JDK:
- Framework line/version:
- Planned intermediate steps:
- Rollout window:

## Source documents
| Document | Version scope | Reviewed date | Relevant sections |
| --- | --- | --- | --- |

## Required changes
| ID | Guide reference | Change type | Impact | Owner | Test evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |

## Compatibility checks
- Source:
- Binary:
- Runtime:
- Security:
- Persistence:
- API contract:
- Observability:

## Risks and waivers
- Unsupported extensions:
- Required temporary flags:
- Unverified behavior:
- Rollback limitations:

## Exit criteria
- All required guide items addressed
- Unit/integration/contract tests run with expected counts
- Staging/canary results accepted
- Owners approve remaining exceptions
```

Mẫu này có thể dùng cho nhiều framework. Phần quan trọng là mỗi kết luận “không ảnh hưởng” hoặc “đã xử lý” đều có evidence, không chỉ có một checkbox.

## 19. Tiêu chí nghiệm thu trước khi chuyển sang dòng tiếp theo

- [ ] Đã xác định version nguồn và đích cụ thể, không dùng nhãn latest mơ hồ.
- [ ] Đã có danh sách migration guide theo toàn bộ chặng nâng cấp cần thiết.
- [ ] Đã kiểm tra minimum JDK, build tool, plugin và deployment runtime.
- [ ] Đã chụp dependency graph và BOM/parent trước/sau.
- [ ] Đã đối chiếu tài liệu framework core và các extension quan trọng.
- [ ] Đã tìm API removal/deprecation, namespace changes và config renames.
- [ ] Đã phân loại thay đổi cơ học và thay đổi hành vi.
- [ ] Đã đánh giá security, persistence, serialization và API contract.
- [ ] Đã rà soát JPMS/reflection, annotation processing và bytecode tooling khi JDK thay đổi.
- [ ] Đã có ma trận thay đổi kèm nguồn, owner, trạng thái và bằng chứng.
- [ ] Đã kiểm tra unit/integration test count không giảm bất thường.
- [ ] Đã chạy tests trên JDK đích và runtime gần production.
- [ ] Đã thử startup/shutdown, health checks, observability và error handling.
- [ ] Đã xác nhận những dữ liệu/schema thay đổi có chiến lược tương thích và rollback.
- [ ] Đã ghi rõ known issues, waiver và các điểm cần xử lý ở release tiếp theo.
- [ ] Đã cập nhật build/CI, tài liệu vận hành và dependency security inventory.

## 20. Kết luận

Đối chiếu migration guide cho các dòng framework tiếp theo là quá trình biến **tri thức phát hành** thành **kế hoạch thay đổi có thể kiểm chứng**. Mỗi framework có thể thay Java baseline, API, dependency, cấu hình và hành vi theo lịch riêng. Chỉ đọc hướng dẫn của bản đích, nâng một BOM hoặc làm cho mã compile thành công đều chưa đủ để chứng minh hệ thống tương thích.

Trong Java Advance Compatibility Migration, hãy chốt baseline và version đích, đọc đủ guide theo các chặng, liên kết mỗi breaking change với thành phần thực tế, rồi kiểm chứng trên test suite và môi trường vận hành đại diện. Cách làm này giúp nhóm phát triển chuẩn bị cho những dòng framework tiếp theo mà không biến mỗi đợt nâng cấp thành một lần thử sai không có bằng chứng.
