# Đánh giá nâng cấp, kiểm thử hồi quy và phương án quay lại

Nâng cấp Spring Cloud Config không chỉ là đổi version trong Maven hoặc Gradle. Một hệ thống cấu hình tập trung gồm Config Server, nhiều Config Client, Git hoặc backend khác, message broker, cơ chế xác thực, secrets và quy trình refresh. Một thay đổi dependency có thể làm ứng dụng không khởi động, đọc sai profile, không xác thực được với Config Server, mất thông báo refresh hoặc không còn giải mã được secret cũ.

Một lần nâng cấp an toàn cần trả lời ba câu hỏi: phiên bản đích có tương thích với Java, Spring Boot và Spring Cloud release train hiện tại không; các luồng cấu hình có giữ nguyên hành vi sau nâng cấp không; và hệ thống có thể quay lại trạng thái ổn định nếu rollout gặp lỗi không.

Bài học này trình bày quy trình đánh giá trước nâng cấp, lập ma trận tương thích, kiểm thử hồi quy cho Config Server/Client/Git/Bus/secrets, triển khai theo từng giai đoạn và chuẩn bị rollback. Mục tiêu là kiểm soát thay đổi trên toàn hệ thống thay vì chỉ xác nhận ứng dụng biên dịch thành công.

Sau bài học, bạn có thể:

- Lập inventory các thành phần và phiên bản trong hệ thống Spring Cloud Config.
- Chọn Spring Cloud release train tương thích với Spring Boot và Java.
- Đọc release notes, migration guide và security advisories theo từng bước nâng cấp.
- Phát hiện dependency bị override hoặc xung đột giữa các BOM.
- Xây regression suite cho Config Server, Config Client, Git, refresh, Bus và secrets.
- So sánh hành vi trước/sau nâng cấp bằng baseline và kết quả đo được.
- Triển khai canary hoặc blue-green và đặt điều kiện dừng rollout.
- Chuẩn bị rollback cho ứng dụng, Config Server, Git revision, broker và khóa mã hóa.
- Phân biệt rollback với roll-forward khi đã có thay đổi không thể đảo ngược.

## 1. Vì sao phải đánh giá toàn bộ hệ thống?

Một hệ thống có thể bao gồm các thành phần sau:

| Thành phần | Điều cần đánh giá |
|---|---|
| Java runtime | Phiên bản Java tối thiểu, TLS provider, truststore và container base image |
| Spring Boot | API bị deprecated/removed, property rename, Actuator và Config Data |
| Spring Cloud release train | Tương thích với Spring Boot và các module Cloud được quản lý |
| Config Server | REST API, Git/JDBC/Vault/S3 backend, encryption, security và health |
| Config Client | spring.config.import, bootstrap legacy, retry, profile và property precedence |
| Spring Cloud Bus / Stream | Artifact, binder, message format, broker credentials và destination |
| Git provider | HTTPS/SSH, deploy key, host key, branch/label và webhook |
| Secret backend | Vault auth, lease, encryption key, secret rotation và quyền truy cập |
| Deployment platform | Image, readiness/liveness, rolling update, environment variable và secret mount |
| Observability | Metrics, trace, log format, alert và dashboard |

Nâng cấp riêng Config Client có thể khiến client không còn lấy được cấu hình từ Config Server cũ. Nâng cấp Config Server trước có thể làm client cũ không hiểu một cơ chế xác thực mới. Nâng cấp Spring Cloud Stream hoặc broker có thể làm Bus event không được consumer nhận. Vì vậy, phải kiểm thử cả cặp Server/Client và mọi tích hợp nằm trên đường đi của cấu hình.

Hãy vẽ dependency map trước khi thay đổi:

~~~mermaid
flowchart TD
    Build["Build: Java + Spring Boot + Spring Cloud BOM"] --> Server["Config Server"]
    Build --> Client["Config Clients"]
    Server --> Git["Git / JDBC / Vault / S3"]
    Server --> Security["Authentication + TLS + encryption"]
    Client --> Security
    Server --> Bus["Spring Cloud Bus / Stream"]
    Client --> Bus
    Bus --> Broker["RabbitMQ / Kafka"]
    Server --> Observe["Metrics + traces + logs"]
    Client --> Observe
    Platform["Kubernetes / VM / container platform"] --> Server
    Platform --> Client
~~~

Một dependency map tốt phải thể hiện cả phiên bản lẫn hướng kết nối. Ghi lại client nào dùng Config Server nào, server nào đọc repository nào, workload nào dùng broker destination nào và khóa nào cần để giải mã cấu hình.

## 2. Chọn đúng Spring Cloud release train

Spring Cloud phát hành theo release train. Một train quản lý nhiều module như Config, Commons, Stream, Vault, Zookeeper và Gateway. Hãy chọn train tương thích với phiên bản Spring Boot đang dùng, sau đó dùng Spring Cloud BOM để quản lý version của các module.

Ảnh chụp tương thích dưới đây phản ánh tài liệu phát hành tại ngày 27-11-2026. Bảng tương thích và trạng thái hỗ trợ có thể thay đổi; trước khi chọn version production, hãy kiểm tra lại trang Spring Cloud và release notes mới nhất.

| Spring Cloud release train | Spring Boot tương thích được công bố | Ghi chú |
|---|---|---|
| 2026.0.0 (Paddington) | 4.2.0 | GA ngày 20-11-2026 |
| 2025.1.x (Oakwood) | 4.0.x; từ 2025.1.2 hỗ trợ 4.1.x | Dùng patch mới nhất phù hợp |
| 2025.0.x (Northfields) | 3.5.x | Kiểm tra trạng thái hỗ trợ hiện tại |
| 2024.0.x (Moorgate) | 3.4.x | Kiểm tra trạng thái hỗ trợ hiện tại |
| 2023.0.x (Leyton) | 3.2.x, 3.3.x từ service release tương ứng | Train cũ |

Spring Cloud 2026.0.0 được xây dựng trên Spring Boot 4.2.0. Với train này, các module Spring Cloud chính được phát hành ở version 5.1.0. Spring Cloud Bus đã được tích hợp vào Spring Cloud Stream; tọa độ artifact Bus được giữ nguyên, nhưng vị trí dự án và cách tổ chức release đã thay đổi. Đây là một điểm cần xác minh khi nâng cấp build và dependency management.

Tương thích không đồng nghĩa với còn được hỗ trợ. Một train có thể chạy được với Spring Boot nhưng đã hết vòng đời hỗ trợ. Kiểm tra cả:

- Bảng Spring Boot compatibility.
- Trang Supported Versions của Spring Cloud.
- Release notes của train đích.
- Ngày kết thúc hỗ trợ của Spring Boot, Spring Cloud và Java runtime.
- Security advisories của Config, Stream, Vault và các backend liên quan.

Không ghép tùy ý Spring Boot 4.2 với một Spring Cloud train cũ chỉ vì các dependency riêng lẻ tải được từ Maven Central. Việc build thành công không chứng minh tổ hợp version được hỗ trợ.

## 3. Dùng BOM để giữ dependency nhất quán

Maven nên import Spring Cloud BOM và để BOM quản lý version của các module Cloud:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2026.0.0</spring-cloud.version>
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
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-bus-amqp</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ Gradle dùng Spring Boot plugin và Spring Cloud BOM:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.2.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

ext {
    set('springCloudVersion', '2026.0.0')
}

dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
    implementation 'org.springframework.cloud:spring-cloud-starter-bus-amqp'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}
~~~

Các tọa độ starter trong ví dụ cần được xác minh theo module và release train đang dùng. Không tự thêm version riêng cho từng dependency Spring Cloud nếu BOM đã quản lý.

### Kiểm tra dependency thực tế

Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.cloud,org.springframework
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-stream --configuration runtimeClasspath
~~~

Tìm các dấu hiệu:

- Hai version khác nhau của cùng module Spring Cloud.
- Module Spring Framework bị override ngoài Boot BOM.
- Một starter kéo theo module cũ qua dependency bắc cầu.
- Dependency bị khai báo thủ công trong khi BOM đã quản lý.
- Hai BOM quản lý cùng artifact nhưng thứ tự import không rõ ràng.
- Dependency cũ còn sót lại sau khi chuyển từ bootstrap sang Config Data.

Không dùng dependency override để né compatibility verifier mà chưa hiểu nguyên nhân. Hãy sửa release train hoặc dependency conflict ở đúng tầng.

## 4. Đánh giá yêu cầu runtime khi nâng Spring Boot

Khi nâng major Spring Boot, kiểm tra Java, Spring Framework, Jakarta API và embedded server. Ví dụ, Spring Boot 4.0 yêu cầu Java 17 trở lên, Spring Framework 7.x, Jakarta EE 11 và Servlet 6.1. Các API hoặc property đã deprecated trong Boot 3 có thể đã bị loại bỏ ở Boot 4.

Đối với một hệ thống Config Server/Client, các thay đổi này có thể ảnh hưởng:

- Security filter chain và OAuth2 resource/client.
- Servlet container, HTTP client và TLS provider.
- Actuator endpoint, health group và security.
- Configuration property binding.
- Jackson serialization của Environment response.
- Spring Cloud Stream binder và message conversion.
- Custom EnvironmentRepository, PropertySourceLocator hoặc EnvironmentPostProcessor.
- Test framework, MockMvc/WebTestClient và test slice.

Nếu dự án nâng từ nhiều major release phía sau, hãy đọc release notes của từng phiên bản trung gian. Không chỉ đọc migration guide của phiên bản đích; thay đổi có thể đã xuất hiện ở một bản minor hoặc patch trước đó.

## 5. Lập inventory và baseline trước khi nâng cấp

Trước khi thay version, lưu trạng thái hiện tại để có thể so sánh và khôi phục.

Một inventory tối thiểu nên có:

| Dữ liệu | Ví dụ |
|---|---|
| Java runtime | Java 17 |
| Spring Boot | 3.5.x |
| Spring Cloud train | 2025.0.x |
| Config Server artifact/image | Version, image digest |
| Config Client artifact/image | Version theo từng service |
| Git backend | Git provider, branch, search path, refresh-rate |
| Config Data | configserver: hoặc legacy bootstrap |
| Security | Basic/JWT, TLS certificate, Git credential |
| Encryption | Key version, keystore reference, cipher format |
| Bus | Binder, broker version, topic/queue, consumer group |
| Deployment | Namespace, replica count, rollout strategy |
| Config revision | Commit SHA/label đang được phục vụ |

Chụp baseline từ môi trường đang chạy:

- Thời gian startup và thời gian lấy cấu hình.
- HTTP status và latency của Config Server.
- Revision Git mà mỗi replica đang phục vụ.
- Thứ tự và tên property sources trong Environment.
- Profile/label thực tế của từng client.
- Kết quả refresh đơn lẻ và refresh qua Bus.
- Số lượng Bus event, acknowledgement và lỗi consumer.
- Tình trạng giải mã secrets và quyền truy cập.
- Health, readiness, CPU, heap, GC và error rate.

Không lưu giá trị secret vào baseline. Có thể lưu tên property, trạng thái có/không, nguồn property và fingerprint đã được phê duyệt để so sánh mà không tiết lộ nội dung.

### Tạo bộ dữ liệu cấu hình kiểm thử

Chọn một tập application/profile/label đại diện:

- application/default cho cấu hình chung.
- order-service/dev và order-service/prod.
- payment-service/prod.
- Một branch hoặc tag phát hành cụ thể.
- Một repository composite nếu production đang dùng nhiều backend.
- Một cấu hình có cipher hoặc secret manager để kiểm tra giải mã.

Ghi lại giá trị mong đợi của các property không nhạy cảm và nguồn property tương ứng. Bộ dữ liệu này là golden baseline để so sánh trước và sau nâng cấp.

## 6. Đọc release notes và phân loại rủi ro

Đừng đọc release notes theo kiểu chỉ tìm API mới. Với mỗi thay đổi, phân loại tác động:

| Loại thay đổi | Câu hỏi cần trả lời |
|---|---|
| Breaking change | API, property hoặc hành vi nào bị đổi/xóa? |
| Deprecation | Có thể thay trước khi nâng major không? |
| Security fix | Có cấu hình mặc định hoặc validation mới cần bật? |
| Dependency upgrade | Git, broker, Vault, servlet, HTTP client có thay đổi không? |
| Behavior change | Retry, timeout, refresh, label hoặc property precedence có đổi không? |
| Operational change | Endpoint, metric, log hoặc health indicator có đổi không? |
| New feature | Có ảnh hưởng format, API response hoặc dependency bắc cầu không? |

Đặc biệt kiểm tra các mục:

- Config Server API và Environment response.
- Git HTTPS/SSH, host key verification, credential masking và repository patterns.
- Client OAuth2/JWT, Config Data import và retry.
- Encryption/decryption và key management.
- Bus event, binder, serialization và broker compatibility.
- Vault lease/session lifecycle.
- Kubernetes ConfigMap/Secret watcher.
- Actuator endpoint exposure và security.
- Micrometer metrics, Observation và tracing.

### Ví dụ thay đổi đáng chú ý ở Spring Cloud 2026.0.0

Spring Cloud 2026.0.0 có một số thay đổi quan trọng cho module cấu hình:

- Config Server sửa các lỗi bảo mật liên quan đến việc rò rỉ Git/SVN credential trong property source name, xác minh SSH host key và nguy cơ man-in-the-middle khi dùng Git SSH.
- Config Client bổ sung hỗ trợ OAuth2 để xác thực với Config Server.
- Spring Cloud Bus được tích hợp vào Spring Cloud Stream; artifact coordinates của Bus vẫn giữ nguyên.
- Spring Cloud Config module thuộc train này có version 5.1.0.

Đây là lý do regression suite phải có kiểm thử credential masking, SSH host verification, OAuth2 client authorization và Bus event delivery. Một bản nâng cấp có thể sửa lỗ hổng nhưng cũng làm lộ ra cấu hình cũ đang dựa trên hành vi không an toàn.

## 7. Di chuyển property và cấu hình Boot

Spring Boot có thể đổi tên hoặc loại bỏ application properties giữa các feature release. Công cụ spring-boot-properties-migrator giúp phân tích Environment khi startup, ghi diagnostics và tạm thời chuyển một số property sang tên mới.

Thêm dependency trong giai đoạn migration:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Sau khi sửa các property theo tên mới và xác nhận không còn cảnh báo, gỡ dependency migrator khỏi dự án. Đây là công cụ chuyển tiếp, không phải dependency production lâu dài.

Công cụ này không thay thế kiểm tra property riêng của Spring Cloud hoặc custom property do ứng dụng định nghĩa. Các property được thêm muộn vào Environment, chẳng hạn qua một số PropertySource, cũng có thể không được migrator phân tích.

Ngoài property, hãy rà soát:

- spring.config.import=configserver:... so với legacy bootstrap.
- spring.application.name, active profiles và config label.
- spring.cloud.config.* ở cả server và client.
- spring.cloud.config.server.git.* và các repository-specific settings.
- Security filter chain và actuator exposure.
- Bus binder, destination, consumer group và credential.
- Property source override và thứ tự precedence.
- Tên bean, package và API đã deprecated trong code custom.

Không sửa đồng loạt tên property chỉ dựa trên tìm kiếm chuỗi. Một property có thể xuất hiện trong test, tài liệu, Git config repository và environment variable của deployment; phải cập nhật từng nguồn và kiểm tra kết quả runtime.

## 8. Regression test cho Config Server

Config Server là nguồn cấu hình cho nhiều client, vì vậy cần kiểm tra cả API và backend.

| Nhóm kiểm thử | Kịch bản | Kết quả mong đợi |
|---|---|---|
| API | GET application/profile/label hợp lệ | Environment có đúng name, profile, label |
| API | Application hoặc label không tồn tại | Status/error theo contract được xác định |
| Property source | Có file chung và file riêng | Thứ tự và giá trị cuối đúng baseline |
| Git | Đọc branch, tag và commit SHA | Đúng revision |
| Git | Repository private qua HTTPS/SSH | Xác thực thành công, credential không lộ |
| Git | SSH host key không khớp | Kết nối bị từ chối |
| Git cache | Refresh-rate, clone-on-start và basedir | Hành vi cache đúng thiết kế |
| Search path | File nằm trong thư mục con | Property được tìm thấy |
| Composite | Nhiều backend cùng trả property | Thứ tự precedence đúng |
| Secrets | Giá trị cipher | Giải mã đúng, key cũ được giữ trong giai đoạn overlap |
| Security | Client không có quyền đọc app khác | Bị từ chối |
| Health | Repository production probe | Health phản ánh backend theo policy |
| Resource | Tải file cấu hình dạng resource | Content type và nội dung đúng nếu ứng dụng dùng API này |

### Ma trận kiểm thử theo backend

Ngoài contract chung của Config Server, chạy fixture và negative test theo backend thực tế. Mỗi test phải xác nhận cả kết quả đọc lẫn hành vi khi identity, network hoặc dữ liệu không hợp lệ.

| Backend | Kiểm thử hồi quy đặc thù |
|---|---|
| Git | HTTPS/SSH credential, host key, branch/tag/commit, fetch/cache, refresh policy, webhook và revision metadata. |
| Native | Search locations, quyền đọc filesystem, path resolution, file encoding, mounted volume và thay đổi file khi runtime. |
| Vault | Auth method, policy allow/deny, KV v1/v2 path, namespace, token TTL/renewal, lease, TLS và secret rotation. |
| Consul | ACL token, prefix/context, format KEY_VALUE/YAML/PROPERTIES, watch/reload, session reconnect và quyền truy cập bị từ chối. |
| ZooKeeper | Connect string, authentication/ACL trên parent và child znode, session expiration, reconnect và watcher re-registration. |
| Kubernetes ConfigMap/Secret | Service account/RBAC, namespace, API hoặc volume/configtree access, update propagation, rotation và quyền bị từ chối. |
| Custom repository | Repository contract, version/snapshot, precedence, concurrency, cache invalidation, timeout và failure mapping. |

Với Kubernetes, phân biệt rõ Config Server backend tùy biến với Config Client đọc ConfigMap/Secret qua volume hoặc `configtree:`. Kiểm thử đúng đường nạp mà ứng dụng đang dùng. Chạy các bài test trong môi trường có network policy, service identity, TLS trust và filesystem permission gần production.

### Kiểm tra Environment response

Với từng application/profile/label, so sánh:

- name
- profiles
- label
- version
- Tên và thứ tự propertySources
- Các property không nhạy cảm đã chọn
- Status code và response time

Không snapshot toàn bộ response nếu chứa password, token hoặc private endpoint. Viết assertion cho các property đại diện và xác minh secret chỉ tồn tại trong nơi được phép.

## 9. Regression test cho Config Client

Config Client có thể khởi động thành công nhưng vẫn đọc sai cấu hình. Cần kiểm tra hành vi ở thời điểm startup và sau khi refresh.

| Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Config Data | Import Config Server khi startup | Property được nạp trước khi bean cần chúng khởi tạo |
| Profile | Default profile rồi active profile | Đúng nguồn property và precedence |
| Label | Branch/tag/commit cụ thể | Client đọc đúng revision |
| Fail-fast | Config Server không khả dụng | Startup fail theo policy |
| Retry | Server phục hồi trong retry window | Client khởi động sau lần thử thành công |
| Timeout | Server phản hồi chậm | Client xử lý đúng connect/read timeout |
| Local override | Environment variable ghi đè remote | Giá trị cuối đúng precedence |
| Refresh | /actuator/refresh | Environment được tải lại |
| RefreshScope | Bean được đánh dấu refresh | Bean nhận giá trị mới |
| Validation | Property mới thiếu hoặc sai format | Lỗi được phát hiện trước khi phục vụ traffic |
| Security | Token hết hạn hoặc scope sai | Request bị từ chối rõ ràng |
| Health | Config Server tạm thời down | Health và readiness phản ánh policy |

Cần kiểm tra cả client dùng spring.config.import và client còn dùng legacy bootstrap nếu hệ thống đang duy trì cả hai. Không mặc định hai cơ chế có cùng thứ tự nạp cấu hình hoặc cùng thời điểm khởi tạo.

## 10. Regression test cho Spring Cloud Bus và broker

Nếu hệ thống dùng Bus, nâng cấp phải kiểm tra message path từ publisher đến consumer.

Các bài test cần có:

- Client publish hoặc nhận event trên broker.
- busrefresh gửi event tới đúng service hoặc instance.
- Event được các client nhận và không bị gửi đến destination ngoài phạm vi.
- Refresh event lặp không gây side effect nguy hiểm.
- Broker reconnect, redelivery và consumer restart.
- Message format và serialization giữa producer/consumer version cũ/mới.
- ACL/credential của từng broker principal.
- TLS certificate và hostname verification.
- Queue/topic retention, consumer group và DLQ behavior.

### Chờ kết quả refresh bất đồng bộ

Bus chỉ chuyển thông điệp refresh; việc consumer nhận event, gọi Config Server và rebind bean diễn ra bất đồng bộ. Không dùng `Thread.sleep` cố định vì test sẽ chậm khi hệ thống nhanh và chập chờn khi hệ thống chậm. Dùng Awaitility hoặc polling có timeout để chờ trạng thái cuối:

Trước khi publish event, chụp danh sách `expectedInstanceIds` của toàn bộ instance thuộc cohort mục tiêu từ test fixture hoặc orchestrator. Giữ danh sách này cố định trong suốt lần polling để một instance biến mất khỏi cohort không bị bỏ sót. Trong ví dụ, `targetCohort.instanceIds()` đại diện thao tác chụp danh sách này.

~~~java
import java.time.Duration;
import static org.awaitility.Awaitility.await;
import static org.assertj.core.api.Assertions.assertThat;

var expectedInstanceIds = targetCohort.instanceIds();
// Publish the Bus refresh event after taking this snapshot.
await()
    .pollInterval(Duration.ofMillis(250))
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> {
        var revisions = configProbe.appliedRevisions("order-service");
        assertThat(revisions.keySet())
            .containsExactlyInAnyOrderElementsOf(expectedInstanceIds);
        assertThat(revisions.values())
            .allMatch(expectedRevision::equals);
    });
~~~

`configProbe` là test helper tổng hợp kết quả của toàn bộ instance trong cohort đích: `appliedRevisions` truy vấn từng instance và trả về map `instanceId -> revision`. `expectedInstanceIds` là danh sách instance dự kiến của cohort; assertion kiểm tra không thiếu instance nào và tất cả đều áp dụng đúng revision. Helper có thể đọc revision hoặc một property marker từ endpoint kiểm thử trên từng client; endpoint này chỉ nên được expose trong môi trường test. Đặt timeout theo SLO refresh, đồng thời ghi nhận thời gian thực tế từ lúc publish event đến lúc mọi instance mục tiêu áp dụng cấu hình.

Với thuộc tính startup-only hoặc không hỗ trợ rebind, test phải xác nhận rolling restart thay vì chờ Bus thay đổi bean.

Với Spring Cloud 2026.0.0, Bus đã được tích hợp vào Spring Cloud Stream. Tọa độ artifact được giữ nguyên, nhưng cần kiểm tra dependency tree, binder và cấu hình Stream sau nâng cấp. Nếu dự án dùng custom binder hoặc message converter, hãy kiểm tra compatibility độc lập.

Không chỉ kiểm tra một event busrefresh thành công. Hãy xác minh từng client đã tải đúng revision mới từ Config Server và bean cần refresh đã áp dụng cấu hình.

## 11. Regression test cho security và secrets

Nâng cấp có thể thay đổi thư viện TLS, OAuth2, SSH hoặc cách xử lý property source. Bộ test bảo mật cần bao gồm:

| Khu vực | Kiểm thử |
|---|---|
| Config Server authentication | Basic/JWT/OAuth2 đúng issuer, audience, expiry và scope |
| Authorization | Client chỉ đọc application/profile được cấp |
| Git HTTPS | Certificate validation và credential masking |
| Git SSH | Host key validation, known_hosts và từ chối host giả |
| Secrets | Giải mã cipher, Vault authentication và lease lifecycle |
| Actuator | Chỉ expose endpoint được phép |
| Bus | Broker ACL và TLS |
| Logs | Không lộ token, password, private key hoặc decrypted property |
| Audit | Ghi nhận ai phát refresh và thay đổi cấu hình |

Khi thay encryption key, giữ khả năng giải mã cấu hình cũ trong thời gian chuyển đổi. Có thể triển khai key mới để mã hóa secret mới trong khi vẫn giữ key cũ ở trạng thái read-only để giải mã các ciphertext chưa được re-encrypt. Chỉ thu hồi key cũ sau khi đã kiểm kê và chuyển toàn bộ ciphertext.

Nếu nâng cấp có thay đổi bảo mật SSH, hãy kiểm tra trường hợp host key bị đổi hoặc không khớp. Không tắt host key verification để làm pipeline xanh trở lại.

## 12. So sánh kết quả trước và sau nâng cấp

Một regression suite có giá trị khi so sánh được kết quả với baseline. Có thể dùng bảng sau:

| Chỉ số | Baseline | Candidate | Điều kiện chấp nhận |
|---|---:|---:|---|
| Config Server startup | Đo trước | Đo lại | Không vượt startup budget |
| Config fetch p95 | Đo trước | Đo lại | Không vượt SLO đã thống nhất |
| Config Client startup | Đo trước | Đo lại | Không tăng ngoài ngưỡng |
| Retry attempts | Đo trước | Đo lại | Không tăng bất thường |
| Git fetch failures | Đo trước | Đo lại | Không có lỗi mới không giải thích được |
| Bus delivery | Đo trước | Đo lại | Tất cả client trong scope nhận event |
| Config revision | SHA/label | SHA/label | Đúng revision dự kiến |
| Secret resolution | PASS/FAIL | PASS/FAIL | 100% property bắt buộc hoạt động |
| Security tests | PASS/FAIL | PASS/FAIL | Không có regression bảo mật |
| Error rate/readiness | Đo trước | Đo lại | Trong ngưỡng SLO |

Đặt ngưỡng số cụ thể theo hệ thống. Ví dụ, nếu baseline Config Client startup p95 là 2,5 giây và SLO là 4 giây, candidate có p95 3,0 giây có thể chấp nhận; nếu tăng lên 8 giây thì cần tìm nguyên nhân trước khi rollout tiếp.

Không đánh giá chỉ bằng thời gian trung bình. Dùng p95/p99, tỷ lệ lỗi, thời gian retry và kết quả từng replica để phát hiện tail latency.

### Kiểm thử burst và thundering herd

Mô phỏng nhiều Config Client restart cùng lúc sau một đợt deploy hoặc node recovery. Chạy cả cold start và warm start, vì cold start có thể làm Config Server đồng thời clone/fetch Git hoặc mở nhiều kết nối tới Vault/Consul. Ghi nhận request rate, p95/p99, backend fetch count, connection pool, retry, CPU/heap và thời gian startup của từng cohort.

Để kết quả tái lập được, phân biệt ba trạng thái:

- **Cold Config Server repository cache:** dùng một `basedir` rỗng hoặc mới, không có working copy đã clone; request đầu tiên phải clone repository (và fetch revision cần thiết).
- **Warm Config Server repository cache:** dùng `basedir` đã có working copy và cache được làm nóng trước phép đo; ghi rõ cache đã được fetch ở thời điểm nào và server đang phân giải ref nào.
- **Client-only cold restart:** restart các Config Client trong khi Config Server tiếp tục chạy với repository cache đã warm. Trạng thái này đo startup/fetch của client mà không tính chi phí clone ban đầu của Config Server.

Với mỗi lần chạy, ghi lại trạng thái rỗng/đã populate của Config Server `basedir`, backend/cache được dùng, application/profile/label, remote ref (branch/tag), commit SHA thực tế hoặc `Environment.version`, thời điểm fetch/refresh gần nhất và cohort/instance IDs được đo. Nếu backend không phải Git, ghi cache hoặc trạng thái tương đương mà backend đó cung cấp. Không gộp kết quả cold server cache với client-only restart trong cùng một baseline.

Nếu burst vượt SLO:

- Chia rollout thành batch; đặt `maxUnavailable`/`maxSurge` hoặc giới hạn số client được restart đồng thời.
- Giới hạn concurrency ở pipeline/orchestrator và dùng backoff có jitter để client không retry cùng thời điểm.
- Pre-warm repository/cache cần thiết trước khi mở traffic nếu kiến trúc cho phép.
- Theo dõi rate limit và connection quota của Git provider, Vault, Consul hoặc broker.
- Đảm bảo retry budget và timeout không khiến toàn bộ cohort dồn request kéo dài vào backend đang lỗi.

So sánh với baseline bằng cùng số replica, dữ liệu, profile, network path và trạng thái cache. Không chỉ nhìn latency trung bình; một số ít client có startup p99 rất cao cũng có thể làm rollout bị treo.

## 13. Triển khai theo từng giai đoạn

Một rollout nên có các cổng kiểm soát:

1. **Build gate:** dependency tree sạch, compatibility verifier không báo mismatch, compile và unit tests pass.
2. **Integration gate:** Config Server/Client, Git, broker, Vault và TLS hoạt động trong staging.
3. **Regression gate:** golden Environment, profile/label, property precedence, refresh và security tests pass.
4. **Canary gate:** triển khai một Config Server replica hoặc một nhóm client nhỏ.
5. **Observation gate:** theo dõi latency, error rate, revision, health và Bus delivery trong cửa sổ quan sát.
6. **Expansion gate:** mở rộng rollout theo nhóm service/environment.
7. **Completion gate:** tất cả instance đã chạy version đích, lấy đúng config revision và không còn lỗi vượt ngưỡng.

### Cổng quyết định go/no-go

Đặt ngưỡng theo SLO và baseline của hệ thống trước khi mở rollout. Nếu một tiêu chí bắt buộc không đạt, giữ nguyên cohort hiện tại, dừng mở rộng và điều tra; chỉ rollback khi rollback đã được kiểm chứng an toàn.

| Nhóm | GO – được chuyển giai đoạn | NO-GO – dừng rollout |
|---|---|---|
| Config API | Status, schema, application/profile/label, property source và revision đúng fixture. | `5xx` tăng, thiếu property bắt buộc hoặc revision sai. |
| Client startup | Startup p95 trong budget, không có crash loop hoặc fail-fast ngoài dự kiến. | Startup vượt budget, crash loop hoặc nhiều client không nạp được config. |
| Precedence/binding | Giá trị thắng, kiểu dữ liệu và validation khớp golden baseline. | Property bị override sai, bind/validation fail. |
| Refresh/Bus | Mọi client trong cohort nhận đúng revision trong timeout; client ngoài scope không bị refresh ngoài ý muốn. | Event không đến, refresh timeout hoặc sai cohort nhận event. |
| Backend/security | Git/Vault/Consul/ZooKeeper/Kubernetes health, auth, TLS và ACL đạt; không lộ secret. | Credential/ACL/TLS lỗi, unauthorized access hoặc secret xuất hiện trong log. |
| Performance | p95/p99, error rate, CPU, memory và backend request rate trong ngưỡng. | Regression vượt ngưỡng, connection pool bão hòa hoặc backend rate limit. |
| Rollback readiness | Artifact cũ, config revision, key/credential và quy trình phục hồi đã được xác minh. | Không thể khôi phục binary hoặc giải mã cấu hình cũ an toàn. |

Ghi lại quyết định GO/NO-GO, metric snapshot, revision, cohort và người phê duyệt cho mỗi bước. Không dùng trạng thái pod `Healthy` đơn lẻ làm tiêu chí hoàn tất.

### Thứ tự nâng cấp Server và Client

Không có một thứ tự áp dụng an toàn cho mọi kiến trúc. Hãy thử compatibility matrix trong staging:

| Config Server | Config Client | Mục tiêu |
|---|---|---|
| Cũ | Cũ | Baseline |
| Mới | Cũ | Xác minh server mới còn phục vụ client cũ |
| Mới | Mới | Candidate target |
| Cũ | Mới | Chỉ thử nếu rollback yêu cầu client mới nói chuyện với server cũ |

Nếu client mới phụ thuộc API hoặc cơ chế xác thực mới, không thể mặc định client đó tương thích với server cũ. Nếu server mới đổi security defaults, client cũ có thể cần token hoặc trust configuration mới. Hãy chọn thứ tự rollout dựa trên ma trận đã kiểm chứng.

Một cách triển khai thường dùng là nâng Config Server trong môi trường staging, kiểm tra client cũ, rồi nâng một nhóm client canary. Nhưng chỉ áp dụng khi test pair cũ/mới chứng minh được compatibility.

## 14. Canary và blue-green cho Config Server

Với Config Server, blue-green có thể tạo hai nhóm server:

- Blue: version hiện tại, đang phục vụ client production.
- Green: version candidate, dùng image và cấu hình mới, trỏ tới Git/backend test hoặc revision đã khóa.

Trước khi chuyển traffic, xác minh Green trả đúng Environment cho tập application/profile/label đại diện. Khi chuyển một nhóm client sang Green, ghi nhận server instance, revision và lỗi fetch.

Không để Blue và Green cùng sửa một local working directory mutable. Mỗi nhóm nên có working copy riêng hoặc một cách quản lý repository an toàn. Nếu hai nhóm cùng đọc Git remote, theo dõi rate limit và credentials.

Với Config Client, canary theo service hoặc theo một tỷ lệ replica. Đừng chuyển toàn bộ client trong một lần nếu chưa xác nhận Bus event, refresh và readiness trên candidate.

## 15. Phương án rollback phải chuẩn bị trước rollout

Rollback không phải là quyết định có thể đưa ra lần đầu sau khi production gặp lỗi. Trước khi nâng cấp, lưu:

- Image digest và artifact version hiện tại.
- Spring Boot và Spring Cloud BOM hiện tại.
- Dependency lockfile/effective POM.
- Config Server và Client deployment manifests.
- Git commit SHA hoặc tag cấu hình ổn định.
- Config Server Git repository settings và basedir strategy.
- Broker destination, binder và credentials reference.
- Secret key reference, truststore và certificate version.
- Database/schema version nếu có migration.
- Kết quả baseline và regression suite.

Giữ artifact cũ trong registry và đảm bảo pipeline có thể deploy lại. Kiểm thử rollback ở staging ít nhất một lần; một file YAML rollback chưa chứng minh container, dependency và secrets cũ còn chạy được.

### Rollback ứng dụng

1. Dừng mở rộng rollout.
2. Đưa traffic hoặc deployment về image digest cũ.
3. Khôi phục Spring Boot/Spring Cloud BOM cũ cùng dependency set đã kiểm thử.
4. Xác nhận client kết nối được Config Server tương ứng.
5. Kiểm tra readiness, config revision và error rate.
6. Giữ candidate ở trạng thái cô lập để thu thập log và trace.

### Rollback cấu hình Git

Không force-push để viết lại lịch sử cấu hình production. Tạo một commit revert mới hoặc trỏ Config Server về một tag/commit đã được kiểm chứng. Xác minh application/profile/label và revision trước khi phát refresh.

Nếu cấu hình mới đã xóa property cũ mà client version cũ vẫn cần, khôi phục property đó trước khi rollback client. Trong giai đoạn chuyển đổi, giữ các key cũ và mới song song nếu chúng không xung đột và không làm lộ secrets.

### Rollback Bus và broker

Nếu thay binder, broker hoặc message schema, kiểm tra consumer version cũ có thể đọc event được phát từ producer mới không. Nếu không, cần đưa cả producer và consumer về phiên bản tương thích hoặc triển khai bridge/dual publishing đã được kiểm thử. Không chỉ rollback ứng dụng mà bỏ qua message đang nằm trong queue/topic.

### Rollback secrets và encryption keys

Không xóa key cũ ngay sau khi rollout candidate. Nếu candidate đã mã hóa secret bằng key mới, server cũ có thể không giải mã được. Giữ overlap giữa key cũ và mới cho đến khi rollback window đóng và toàn bộ ciphertext được xử lý.

### Trình tự rollback vận hành

Khi một cổng NO-GO được kích hoạt và quyết định rollback đã được xác nhận, thực hiện theo thứ tự:

1. Đóng băng rollout, ngừng mở rộng cohort và ghi lại thời điểm/revision đang chạy.
2. Phân loại lỗi thuộc Config Server, Config Client, Git/backend, Bus/broker, secret/key hay thay đổi schema cấu hình.
3. Chuyển traffic Config Server về fleet/image cũ hoặc rollback server canary; giữ candidate cô lập để thu thập log/trace.
4. Rollback các client cohort bị ảnh hưởng về image và dependency set đã biết là tốt.
5. Nếu Git config là nguyên nhân, pin server về commit/tag đã kiểm chứng hoặc tạo commit revert; khôi phục key/property/schema cũ mà client cũ cần.
6. Khôi phục broker destination, credential, truststore và key overlap cần thiết; không thu hồi key cũ khi còn ciphertext cần giải mã.
7. Phát refresh cho property có thể reload; restart cohort đối với property startup-only hoặc bean không hỗ trợ refresh.
8. Xác minh Environment response, label/version, property source, giá trị trong bean, readiness, business metrics và Bus delivery trước khi mở traffic.
9. Ghi nhận artifact, revision, cohort và kết quả rollback vào change record.

Không force-push để viết lại lịch sử Git production. Ưu tiên commit revert hoặc label bất biến đã được kiểm tra; rollback phải phục hồi cả binary lẫn cấu hình tương thích.

## 16. Khi nào rollback, khi nào roll-forward?

Rollback phù hợp khi:

- Candidate không khởi động hoặc liên tục crash.
- Config Client không thể tải cấu hình bắt buộc.
- Config Server trả sai Environment hoặc revision.
- Bus refresh không đến client trong phạm vi.
- Security regression làm lộ hoặc từ chối sai quyền.
- Latency/error rate vượt ngưỡng và rollback đã được chứng minh an toàn.

Roll-forward thường phù hợp khi:

- Có migration dữ liệu không thể đảo ngược.
- Config mới đã được client version mới tiêu thụ và old version không hiểu.
- Secret/key đã được rotate theo cách không còn key cũ.
- Broker message hoặc schema đã chuyển sang format mới mà consumer cũ không đọc được.
- Rollback sẽ làm mất dữ liệu hoặc tạo trạng thái không nhất quán.

Nếu cần roll-forward, giảm phạm vi ảnh hưởng, phát bản sửa nhỏ nhất và tiếp tục giữ cổng kiểm soát. Không cố rollback chỉ vì quy trình rollback đã được viết sẵn; hãy xem xét trạng thái thực tế của dữ liệu, key và message.

~~~mermaid
flowchart TD
    A["Canary candidate"] --> B{"SLO và regression gates pass?"}
    B -->|Có| C["Mở rộng rollout"]
    B -->|Không| D{"Rollback đã được kiểm chứng và an toàn?"}
    D -->|Có| E["Dừng rollout, deploy artifact cũ"]
    D -->|Không| F["Cô lập candidate, chuẩn bị roll-forward"]
    E --> G["Xác minh health, config revision và traffic"]
    F --> H["Sửa lỗi tối thiểu và chạy lại regression"]
    C --> I["Xác minh toàn bộ instance"]
~~~

## 17. Giữ tương thích cấu hình trong giai đoạn chuyển đổi

Ứng dụng và Config Server có thể được nâng cấp ở các thời điểm khác nhau. Trong giai đoạn overlap, thiết kế Git configuration theo hướng tương thích ngược:

- Thêm property mới với default an toàn trước khi client mới yêu cầu nó.
- Giữ property cũ trong thời gian client cũ còn chạy.
- Không đổi kiểu dữ liệu của key đang được nhiều version tiêu thụ nếu chưa kiểm tra.
- Không đổi tên key và xóa key cũ trong cùng một rollout.
- Không chuyển profile hoặc label mặc định cùng lúc với thay đổi dependency lớn.
- Dùng tag/commit bất biến cho rollout cần tái lập.
- Kiểm tra property precedence khi cả key cũ và mới cùng tồn tại.

Với secret, có thể triển khai key mới và property mới trước, xác nhận candidate đọc được, rồi mới chuyển client. Không xóa ciphertext cũ hoặc key giải mã cũ cho đến khi rollback window kết thúc.

Với Bus, nếu thay event schema tùy chỉnh, dùng version field hoặc chiến lược tương thích producer/consumer. Default refresh event của Spring Cloud không đồng nghĩa custom event của ứng dụng cũng tự tương thích.

## 18. Runbook nâng cấp mẫu

Một runbook có thể dùng cho mỗi lần nâng cấp:

| Giai đoạn | Việc cần làm | Bằng chứng hoàn thành |
|---|---|---|
| Prepare | Inventory, baseline, target matrix, release notes | Upgrade record được duyệt |
| Build | Cập nhật BOM, dependency tree, Java/toolchain | Build sạch, không version conflict |
| Migrate | Sửa API/property/config import/deprecation | Migration diagnostics được xử lý |
| Test | Unit, integration, regression, security, failure tests | Báo cáo test pass |
| Stage | Deploy staging, chạy load và outage simulation | Metrics trong ngưỡng |
| Canary | Một server/nhóm client nhỏ | Health và config revision đúng |
| Expand | Mở rộng từng nhóm | Error rate và latency ổn định |
| Complete | Toàn bộ instance ở target version | Inventory sau rollout khớp kế hoạch |
| Close rollback | Đóng rollback window, thu hồi artifact/key cũ theo policy | Change record và audit đầy đủ |

Upgrade record nên có owner, thời gian, version nguồn/đích, commit cấu hình, artifact digest, test result, rollback trigger và người có quyền dừng rollout.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Build pass nhưng startup fail | Runtime/API hoặc property đã bị loại bỏ | Đọc migration guide, kiểm tra log và compatibility verifier |
| Boot mới nhưng Spring Cloud cũ | Release train không tương thích | Chọn BOM đúng với Boot version |
| Nhiều version spring-cloud trong dependency tree | Override hoặc BOM conflict | Bỏ version thủ công, kiểm tra effective POM |
| Client mới không lấy được config | Config Server/API/auth chưa tương thích | Kiểm tra cặp Server/Client và OAuth2/TLS |
| Client khởi động nhưng đọc giá trị khác | Property precedence hoặc profile thay đổi | So sánh Environment và golden baseline |
| Bus event không đến | Binder, broker ACL hoặc destination thay đổi | Kiểm tra producer/consumer, queue và event trace |
| Config Server trả Environment nhưng secret lỗi | Encryption key hoặc Vault auth không tương thích | Kiểm tra key overlap và secret lifecycle |
| Rollback app nhưng vẫn lỗi config | Git config đã xóa key cũ hoặc đổi label | Revert cấu hình bằng commit mới và kiểm tra revision |
| Rollback không giải mã được secret | Key cũ đã bị thu hồi | Duy trì key overlap và kiểm thử rollback trước |
| Một số replica dùng version khác | Rollout không đồng bộ hoặc load balancer còn candidate | Đối chiếu image digest và instance inventory |
| Canary ổn nhưng rollout rộng lỗi | Tải Git/broker hoặc số client lớn làm lộ bottleneck | Thử tải gần production và rollout theo batch nhỏ |

## 20. Checklist trước khi phê duyệt nâng cấp

- [ ] Đã xác định Java, Spring Boot và Spring Cloud release train tương thích.
- [ ] Đã kiểm tra trạng thái hỗ trợ và service release mới nhất.
- [ ] Đã đọc release notes của mọi phiên bản trung gian.
- [ ] Đã rà soát breaking changes, deprecations và security advisories.
- [ ] Đã lưu inventory, BOM, dependency tree và artifact digest hiện tại.
- [ ] Đã tạo golden baseline cho Environment response và property precedence.
- [ ] Đã kiểm tra Config Server với các Config Client version cần hỗ trợ.
- [ ] Đã kiểm tra Git backend, label, branch, SSH/TLS và refresh-rate.
- [ ] Đã kiểm tra Config Data import, bootstrap legacy, retry và timeout.
- [ ] Đã kiểm tra Bus, binder, broker, message delivery và ACL.
- [ ] Đã kiểm tra encryption key, Vault auth, secret lease và rotation.
- [ ] Đã chạy regression, integration, security và failure tests.
- [ ] Đã có canary/blue-green plan và điều kiện dừng rollout.
- [ ] Đã lưu image, BOM, Git revision và key reference để rollback.
- [ ] Đã thực hiện thử rollback trong staging.
- [ ] Đã có người chịu trách nhiệm ra quyết định stop/rollback.

## 21. Tự kiểm tra

1. Vì sao phải chọn Spring Cloud release train theo Spring Boot version thay vì nâng từng module độc lập?
2. BOM giúp ngăn loại dependency conflict nào?
3. Vì sao build thành công chưa chứng minh Config Client tương thích với Config Server?
4. spring-boot-properties-migrator giúp gì và vì sao cần gỡ sau migration?
5. Những property và hành vi nào cần đưa vào golden baseline?
6. Vì sao phải kiểm tra cả startup fetch và runtime refresh?
7. Spring Cloud Bus được tích hợp vào Spring Cloud Stream ở release train 2026.0.0 có ý nghĩa gì đối với dependency và regression test?
8. Vì sao phải kiểm thử SSH host key, credential masking và OAuth2 sau nâng cấp Config Server?
9. Khi nào nên nâng Config Server trước client và khi nào cần nâng theo cặp?
10. Vì sao giữ property cũ và mới song song có thể giúp rollback?
11. Những dữ liệu nào cần lưu trước khi rollout để có thể khôi phục?
12. Khi nào roll-forward an toàn hơn rollback?

Hãy chọn một hệ thống staging có Config Server, ít nhất hai Config Client, Git backend và một broker nếu dùng Bus. Ghi lại baseline version, dependency tree, Environment response, startup time, refresh result và security tests. Tạo candidate bằng release train tương thích; chạy migration diagnostics, regression matrix và fault injection. Sau đó triển khai canary, theo dõi revision/latency/error rate và thực hiện một lần rollback có kiểm soát. Cuối cùng xác minh image, BOM, Git revision, secrets và broker state đều quay về một tổ hợp tương thích. Ghi rõ điều kiện nào sẽ khiến nhóm chọn roll-forward thay vì rollback trong lần phát hành production.

## Kết luận

Một lần nâng cấp Spring Cloud Config chỉ hoàn tất khi phiên bản, cấu hình, backend, security và luồng refresh cùng đạt các contract đã kiểm thử. Hãy giữ baseline và revision có thể tái lập, kiểm tra từng backend theo đặc thù, rollout theo cohort với cổng go/no-go rõ ràng, rồi chỉ đóng rollback window sau khi mọi client đã nhận đúng cấu hình và các artifact/key cũ không còn cần thiết.

## Tài liệu tham khảo

- [Spring Cloud — Project and Boot Compatibility Matrix](https://spring.io/projects/spring-cloud/)
- [Spring Cloud 2026.0.0 (Paddington) Release Announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Release Train — Supported Versions and Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki)
- [Spring Boot — Upgrading](https://docs.spring.io/spring-boot/upgrading.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Boot — Deprecated Application Properties](https://docs.spring.io/spring-boot/appendix/deprecated-application-properties/)
- [Spring Cloud Config — Reference Documentation](https://docs.spring.io/spring-cloud-config/reference/)
- [Spring Cloud Stream — Reference Documentation](https://docs.spring.io/spring-cloud-stream/reference/)
- [Spring Cloud Bus — Reference Documentation](https://docs.spring.io/spring-cloud-bus/reference/)
