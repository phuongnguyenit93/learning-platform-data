# Máy chủ Vault tạm thời cho kiểm thử tích hợp

## 1. Vì sao cần một Vault thật trong kiểm thử?

Trong module **SPRING_VAULT**, ứng dụng Java kết nối HashiCorp Vault bằng `VaultTemplate`, xác thực theo danh tính workload và ACL policy để thao tác KV secrets, token/lease, Transit encryption, PKI hoặc database dynamic credentials. Unit test dùng Mockito có thể xác minh một method Java gọi đúng tham số, nhưng không đủ để trả lời:

- Endpoint của Spring Vault có tương thích phiên bản Vault hiện dùng không?
- Path KV v2 là `kv/data/...` hay `kv/...`, role có đúng capability không?
- Vault token không có quyền thật sự bị từ chối hay mock đã trả về dữ liệu ngoài dự kiến?
- Transit trả ciphertext đúng định dạng, PKI có cấp chứng thư theo role, database plugin có tạo và thu hồi username không?
- Ứng dụng xử lý HTTP 403/404, token hết hạn, lease renewal và mất kết nối thế nào?

Để trả lời, ta chạy **máy chủ Vault tạm thời (ephemeral Vault server)** cho mỗi lần kiểm thử hoặc mỗi test suite, tạo fixture và gọi API thật từ Java. Máy chủ này chỉ phục vụ test, được xóa sau khi chạy; không sử dụng secrets hoặc root token của môi trường production.

Một lựa chọn thông dụng là **Testcontainers for Java** với `VaultContainer`: Testcontainers tạo một container Vault, công bố cổng ngẫu nhiên lên máy chạy test, chờ container sẵn sàng và dọn container theo vòng đời kiểm thử. Bài học mô tả cách dùng thực tế, giới hạn của Vault dev mode và cách ghép cùng Spring Boot.

### Kết quả mong muốn sau bài học

1. Phân biệt unit test, integration test với Vault tạm thời, và thử nghiệm gần production.
2. Khởi động Vault dev container tạm thời bằng Testcontainers/JUnit 5.
3. Chuẩn bị KV v2 mount, policy và token workload giới hạn quyền.
4. Dùng `VaultTemplate` đọc secret hợp lệ, kiểm tra request ghi trái quyền bị từ chối.
5. Quản lý khởi tạo, cô lập fixture, TLS/auth, Config Data, timeout và cleanup.
6. Thiết kế test mở rộng cho Transit, PKI, database leases và tình huống thất bại.

## 2. Chọn mức kiểm thử phù hợp

| Loại kiểm thử | Vault server thật? | Phù hợp để kiểm chứng | Không chứng minh được |
|---|---|---|---|
| Unit test với mock `VaultOperations` | Không | Logic mapping request/response, validation, xử lý Java exception | ACL, path, behavior của Vault |
| HTTP contract test với fake server | Không, chỉ mô phỏng HTTP | Serialization, URL/method, error mapper, retry HTTP | Chính sách Vault thực, lease, backend behavior |
| Integration test với Vault dev/Testcontainers | **Có** | Vault API thật, KV v1/v2, policies, auth, Transit/PKI fixture | HA, KMS auto-unseal, hiệu năng production |
| Integration test với Vault + database/container khác | **Có** | Dynamic DB credentials, SQL grants, revocation, network thực | Toàn bộ đặc tính cluster production |
| Staging/prod-like E2E | **Có** | Kubernetes auth, TLS, namespace, audit, hạ tầng phân tán | Không phải test tạm thời; tốn công và cần quy trình vận hành |

**Quy tắc thực dụng:** dùng test nhỏ nhất có thể phát hiện lớp lỗi đang nhắm tới. Unit tests chạy nhanh cho nghiệp vụ; một tập integration tests chạy Vault thật cần thiết để kiểm tra cấu hình engine, ACL và phản hồi từ server.

## 3. Vault dev mode khác Vault production như thế nào?

`VaultContainer` thường khởi chạy Vault ở **development mode**:

- Vault được khởi tạo và unseal sẵn, không cần quy trình bootstrap production.
- Có **root token dành riêng cho test**, được truyền khi tạo container.
- Dữ liệu thường nằm trong bộ nhớ hoặc phạm vi lưu trữ tạm; container bị hủy thì fixture cũng mất.
- API Vault là thật, có thể bật secrets engines và khai báo policy.
- HTTPS, HA/raft cluster, standby/failover, auto-unseal KMS, enterprise namespace, cấu hình audit và các network policy production **không được mô phỏng đầy đủ**.

Root token ở dev mode **chỉ để dựng fixture**. Test cấp quyền phải đăng nhập bằng token workload có policy giới hạn, không dùng root token để chứng minh việc một thao tác được phép hoặc bị từ chối.

Không coi việc test `GET` KV thành công với root token là bằng chứng policy Kubernetes/AppRole của production đã chính xác. Mô hình xác thực workload thật cần test bổ sung bằng Kubernetes hoặc một auth method phù hợp hạ tầng.

### Tính “tạm thời” cần được bảo đảm ở đâu?

| Tầng | Phạm vi nên tạm thời | Lý do |
|---|---|---|
| Container Vault | Mỗi test class hoặc suite độc lập | Không đụng vào Vault cluster khác |
| Root token | Một giá trị test riêng | Không tái sử dụng production credentials |
| Mount/role/policy | Tên có prefix test, tạo lúc setup | Không ảnh hưởng ứng dụng thật |
| Lease/secret | Cấp trong test và tự hết/hủy cùng container | Tránh giữ tài khoản hoặc PKI artifacts ngoài môi trường test |
| Port host | Port ngẫu nhiên Testcontainers map | Không phụ thuộc `localhost:8200` |
| Mạng | Chỉ cho môi trường CI/test cần thiết | Không expose Vault dev token ra Internet |

Nếu cần nhiều bộ test chạy song song, tạo fixture có namespace logic hoặc prefix riêng thay vì để các class cùng sửa một key hoặc policy global.

## 4. Kiến trúc một integration test

~~~mermaid
sequenceDiagram
    participant J as JUnit 5
    participant T as Testcontainers
    participant V as Vault dev container
    participant A as VaultTemplate operator
    participant W as VaultTemplate workload

    J->>T: Khởi tạo VaultContainer
    T->>V: Start dev server / expose port
    V-->>T: Ready
    J->>A: Tạo client root chỉ cho fixture
    A->>V: Mount KV v2, viết secret, tạo ACL policy
    A->>V: Tạo token ít quyền với policy test
    V-->>A: Trả token dành cho workload
    J->>W: Tạo VaultTemplate với token ít quyền
    W->>V: Đọc secret hợp lệ
    V-->>W: Dữ liệu KV v2
    W->>V: Thử ghi secret trái quyền
    V-->>W: Permission denied
    J->>T: Kết thúc test
    T->>V: Stop/remove container và fixture
~~~

Trong sơ đồ, `operator` và `workload` là **hai client khác token**. Chúng có thể dùng cùng endpoint container nhưng quyền truy cập khác nhau.

Một trường hợp quan trọng: có thể khởi động container Vault thành công nhưng fixture chưa được tạo, hoặc fixture tạo thành công mà token workload không được gán đúng policy. Vì vậy test phải kiểm tra **mỗi bước độc lập**, không dựa vào điều kiện “container chạy” để suy ra “ứng dụng được cấu hình đúng”.

## 5. Dependencies và môi trường chạy

Với dự án Spring Boot dùng Java 17+ và JUnit Jupiter, cần có các thành phần phù hợp:

~~~xml
<!-- Trích đoạn Maven dependencies; versions do BOM của project quản lý. -->
<dependencies>
  <dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>vault</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Nếu project không sử dụng BOM của Spring Boot/Testcontainers hoặc dependency management tương ứng, phải khai báo phiên bản đã kiểm tra tương thích; không copy trích đoạn này rồi mặc định dependency sẽ resolve trong mọi Maven project. Với Gradle, artifacts tương ứng được khai báo ở `testImplementation`.

Ví dụ Gradle (khi dự án đã có phiên bản được quản lý):

~~~kotlin
dependencies {
    implementation("org.springframework.vault:spring-vault-core")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:vault")
    testImplementation("org.testcontainers:junit-jupiter")
}
~~~

Trước khi chạy cần có:

- Docker Engine hoặc runtime Testcontainers tương thích và có thể truy cập từ JVM chạy test.
- Khả năng kéo image Vault đã được duyệt về máy/registry nội bộ.
- Tài nguyên CPU/RAM/disk đủ để start container.
- Không bị chính sách mạng CI chặn Docker daemon, mapped ports hoặc container network.
- Không có phần mềm bảo mật tự ngăn test container tạo network.

**Không tắt kiểm thử một cách im lặng khi Docker vắng mặt trong CI** nếu integration tests là quality gate. Nếu chạy local mà Docker chưa sẵn sàng, có thể tách profile/task integration test rõ ràng; trên CI phải hiển thị test fail hoặc được skip theo một chính sách minh bạch.

## 6. Ví dụ JUnit 5 + Testcontainers: KV v2 và ACL thực

Đoạn mã sau là **một integration test tự chứa về mặt logic**. Nó tạo Vault container, bật một mount KV v2 riêng, ghi secret bằng operator, tạo ACL policy ít quyền, cấp một workload token và kiểm thử **đọc thành công / ghi bị từ chối**.

Cần Java 17+ cho text block, phiên bản Spring Vault/Testcontainers tương thích và image Vault có sẵn. Image `hashicorp/vault:1.16.2` chỉ là bản pin minh họa: với dự án thật, chốt tag/digest đã được kiểm thử và được phê duyệt.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.vault.VaultException;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;
import org.testcontainers.containers.VaultContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class TemporaryVaultIntegrationTest {

    // Chỉ có giá trị trong Vault dev container. Không dùng ở staging/prod.
    private static final String DEV_ROOT_TOKEN = "dev-only-root-token";

    @Container
    static final VaultContainer<?> VAULT =
        new VaultContainer<>(
            DockerImageName.parse("hashicorp/vault:1.16.2"))
            .withVaultToken(DEV_ROOT_TOKEN);

    static VaultTemplate template(String token) {
        URI uri = URI.create(
            "http://" + VAULT.getHost() + ":" + VAULT.getMappedPort(8200));

        return new VaultTemplate(
            VaultEndpoint.from(uri),
            new TokenAuthentication(token));
    }

    @Test
    void kvV2ReadAllowedButWriteDeniedByAcl() {
        VaultTemplate operator = template(DEV_ROOT_TOKEN);

        // Admin fixture: mount test riêng, không dựa vào secret/ mặc định.
        operator.write(
            "sys/mounts/kv-it",
            Map.of("type", "kv",
                   "options", Map.of("version", "2")));

        VaultKeyValueOperations adminKv = operator.opsForKeyValue(
            "kv-it", KeyValueBackend.KV_2);

        adminKv.put(
            "apps/orders/config",
            Map.of("mode", "integration-test"));

        // Policy cho phép đọc KV v2, không cho ghi/update.
        String policy = """
            path "kv-it/data/apps/orders/*" {
              capabilities = ["read"]
            }
            """;

        operator.write(
            "sys/policies/acl/orders-it-readonly",
            Map.of("policy", policy));

        // Cấp token giới hạn quyền, không kế thừa policy default.
        VaultResponse issued = operator.write(
            "auth/token/create",
            Map.of("policies", List.of("orders-it-readonly"),
                   "no_default_policy", true,
                   "ttl", "5m"));

        assertNotNull(issued);
        assertNotNull(issued.getAuth());
        String workloadToken =
            (String) issued.getAuth().get("client_token");
        assertNotNull(workloadToken);

        VaultTemplate workload = template(workloadToken);
        VaultKeyValueOperations workloadKv = workload.opsForKeyValue(
            "kv-it", KeyValueBackend.KV_2);

        VaultResponse allowed =
            workloadKv.get("apps/orders/config");

        assertNotNull(allowed);
        assertNotNull(allowed.getData());
        assertEquals("integration-test",
                     allowed.getData().get("mode"));

        // Cùng token phải bị chặn khi cố sửa dữ liệu.
        assertThrows(
            VaultException.class,
            () -> workloadKv.put(
                "apps/orders/config",
                Map.of("mode", "overwritten")));
    }
}
~~~

### Vì sao ví dụ này có ý nghĩa hơn một mock?

- `VaultContainer` chạy **Vault server thật** và Testcontainers điều phối start/stop.
- `operator` gọi `sys/mounts`, `sys/policies/acl` và `auth/token/create` để dựng fixture.
- Token trả về từ `auth/token/create` được dùng riêng cho `workload`. Không truyền root token vào đối tượng được kiểm thử quyền hạn.
- `KeyValueBackend.KV_2` khiến Spring Vault ánh xạ path logic `apps/orders/config` tới API KV v2 phù hợp.
- Ca positive đảm bảo mount, secret và token đang hoạt động; ca negative cùng token kiểm chứng Vault thực thi ACL.
- Container được JUnit Jupiter extension quản lý; khi test kết thúc, tài nguyên của container được dọn theo cấu hình Testcontainers.

**Lưu ý giới hạn:** ví dụ dùng một test method trong một container mới. Nếu tách thành nhiều methods nhưng giữ `@Container static`, mount `kv-it` sẽ tồn tại từ method trước; phải chuyển fixture sang `@BeforeAll` hoặc tạo tên riêng, đồng thời quy định rõ dọn dẹp. Nếu app có nền tảng Spring Boot và dùng `@SpringBootTest`, cần tích hợp Vault endpoint/token với Spring context đúng giai đoạn khởi tạo.

### Về giá trị trả về của `auth/token/create`

Vault token creation API trả token trong phần `auth.client_token`; với `VaultResponse`, phần `auth` có thể đọc qua `getAuth()`. Không đưa token này vào assertion message, logger hoặc log raw response. Nếu API/phiên bản client trả response không như mong đợi, phải dừng test thay vì fallback sang root token.

Trong production, workload thường sử dụng Kubernetes/AppRole auth thay vì operator cấp token trực tiếp. Token creation ở đây chỉ là **fixture để kiểm chứng ACL**. Nó không chứng minh cấu hình Kubernetes auth hoặc AppRole đã được thiết lập đúng.

## 7. Đường dẫn KV v2 và quyền cần kiểm tra

KV v2 có cách tổ chức API quan trọng đối với integration test:

| Thao tác logic | API path thực tế trên mount `kv-it` | ACL capability thường cần |
|---|---|---|
| Đọc secret `apps/orders/config` | `kv-it/data/apps/orders/config` | `read` |
| Ghi secret `apps/orders/config` | `kv-it/data/apps/orders/config` | `create` / `update` tùy thao tác |
| Liệt kê key `apps/orders/` | `kv-it/metadata/apps/orders` | `list` |
| Đọc metadata/key versions | `kv-it/metadata/apps/orders/config` | `read` khi cần metadata |

Policy ở ví dụ chỉ cấp `read` cho `kv-it/data/apps/orders/*` nên cập nhật secret phải thất bại. Nếu một testcase cho phép `list` mà không cấp trên `metadata`, testcase đó có thể báo 403 mặc dù quyền `read` trên `data` đã đúng.

Cần kiểm tra **cả request hợp lệ lẫn request bị từ chối**. Một kết quả thành công do root token không đủ chứng minh ACL. Một negative test bị từ chối trong lúc Vault chưa chạy cũng không chứng minh policy đúng.

## 8. Testcontainers lifecycle và chiến lược cô lập

Testcontainers hỗ trợ hai phạm vi phổ biến trong JUnit 5:

| Cách khai báo | Vòng đời thường dùng | Ưu điểm | Rủi ro |
|---|---|---|---|
| `@Container static` | Một container cho test class | Tiết kiệm thời gian khởi tạo | Các test methods có thể chia sẻ trạng thái |
| `@Container` instance | Container theo từng test instance/method (theo JUnit lifecycle) | Cô lập mạnh hơn | Chạy chậm, dùng tài nguyên nhiều hơn |

Khi dùng `@Testcontainers` extension, các fields `@Container` được start/stop theo lifecycle. Nếu đặt container ở một singleton chia sẻ nhiều class, việc Testcontainers dừng container trước khi context Spring Boot kết thúc có thể gây lỗi cho test class kế tiếp.

**Không bật container reuse toàn cục một cách mặc định trong CI**, đặc biệt với Vault chứa token/secret test. Reuse giúp tiết kiệm thời gian local, nhưng có thể khiến policy, lease hoặc key còn sót từ lần chạy trước. Với bài học về tạm thời và cô lập, nên ưu tiên container không tái sử dụng.

### Cô lập fixture khi chạy parallel

- Dùng mount prefix riêng: `kv-it-<runId>` hoặc tạo container độc lập.
- Dùng policy prefix theo suite: `orders-it-readonly` và xóa khi fixture cần.
- Không giả định namespace Enterprise tồn tại trong Vault dev OSS.
- Mỗi test ghi key riêng, tránh `test A` ghi đè data dùng bởi `test B`.
- Với Transit và PKI, keys/issuer/roles trong cùng mount có thể là trạng thái dùng chung; tách mount hoặc serial execution khi cần.
- Với database dynamic credentials, dùng PostgreSQL test riêng vì revoke/SQL statements là side effects ngoài Vault container.

**Khuyến nghị:** trước tiên dùng một VaultContainer cho một test class có fixture độc lập; chỉ tối ưu thành shared container khi đã có kiểm chứng về parallel isolation và vòng đời Spring context.

## 9. Test Spring Boot: phân biệt runtime VaultTemplate và Config Data

Đây là điểm thường gây lỗi nhất khi tích hợp Vault tạm thời với Spring Boot.

### 9.1. Runtime integration: tạo VaultTemplate từ endpoint container

Ví dụ ở mục 6 lấy host/port sau khi Testcontainers start và tự tạo `VaultTemplate`. Cách này phù hợp để kiểm thử `VaultOperations` tại runtime: KV, Transit, PKI, token/lease. Nó **không cần** Spring Cloud Vault Config Data import.

Nếu muốn inject `VaultTemplate` vào service qua Spring context, có thể cung cấp `@TestConfiguration` tạo bean từ container đã start, nhưng vẫn cần quản lý nhất quán lifecycle và tránh đụng `VaultTemplate` auto-config đang tồn tại.

### 9.2. Config Data integration: Vault cần sẵn sàng sớm hơn

Nếu application có:

~~~yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "http://127.0.0.1:8200"
      authentication: TOKEN
~~~

Spring Cloud Vault có thể đọc secrets **trong giai đoạn Config Data**, trước khi `ApplicationContext` tạo xong các bean. Do vậy, **không nên mặc định** rằng chỉ dùng `@DynamicPropertySource` đặt `spring.cloud.vault.uri` và token là đủ cho mọi phiên bản Boot/Cloud: dynamic test properties có thể được áp dụng quá muộn so với bước Config Data import.

Ba hướng cần cân nhắc:

1. **Test không cần Config Data:** vô hiệu hóa import trong một cấu hình test chuyên biệt và kiểm thử bằng `VaultTemplate`/`VaultOperations`; đây là phạm vi của ví dụ trên.
2. **Test Config Data thật:** start Vault **trước khi Spring Boot xử lý Config Data**, truyền `spring.cloud.vault.uri`, authentication và token qua nguồn cấu hình sớm đúng với phiên bản Boot/Cloud; quản lý stop/cleanup sau khi context đóng.
3. **Test property precedence:** cấu hình một startup fixture riêng và assertion trên `Environment` để chứng minh Vault property source được nạp; không chỉ kiểm tra bean runtime có thể đọc một secret.

Nếu test có `spring.config.import=optional:vault://`, đừng hiểu từ `optional` rằng mọi lỗi network/TLS/ACL sẽ được bỏ qua. Tài liệu Spring Cloud Vault theo phiên bản cần được kiểm tra; một secret bắt buộc phải fail fast khi không có nguồn cần thiết.

### 9.3. Một mô hình integration test có thể bảo trì

Tách hai nhóm test:

- **`VaultRuntimeIT`:** dùng Testcontainers + `VaultTemplate` trực tiếp; kiểm thử API, permissions, secrets engines.
- **`VaultBootstrapIT`:** khởi động Vault từ test launcher/initializer phù hợp, rồi khởi tạo Spring Boot với Config Data import; kiểm thử property sources, authentication và fail-fast.

Không ép hai nhóm vào một test class phức tạp rồi sửa thứ tự bean bằng cách bật override hoặc hardcode localhost.

## 10. Fixture chuẩn: policy, workload identity, engines và secrets

Thành công của integration test phụ thuộc setup đủ chính xác. Một fixture cần mô tả những tài nguyên phải có trước khi chạy:

| Tài nguyên | Ai tạo? | Kiểm thử sau setup |
|---|---|---|
| Vault dev instance và root token test | Testcontainers | HTTP API sẵn sàng, container healthy |
| KV v2 mount riêng | Operator fixture | Có version 2 và API `data`/`metadata` |
| KV keys/versions | Operator fixture | Đọc đúng dữ liệu đã seed |
| ACL policy | Operator fixture | Đọc lại policy và test capability |
| Workload token hoặc auth role | Operator fixture | Có quyền cần thiết, không có quyền thừa |
| Transit mount/key | Operator fixture | Encrypt/decrypt hoạt động bằng token đúng quyền |
| PKI mount/issuer/role | Operator fixture | Issue hợp lệ thành công, request ngoài role bị từ chối |
| Database connection/role | Operator + PostgreSQL test fixture | Credentials sinh ra dùng được và bị revoke khi phù hợp |
| Token/lease TTL | Fixture đặt giá trị ngắn hợp lý | Renew/re-auth/revoke theo vòng đời mong muốn |

Trong ví dụ KV v2, ta không phụ thuộc mount `secret/` mặc định của dev server mà tạo `kv-it` tường minh. Đây là cách giảm lỗi khác biệt khi đổi image/version.

**Chỉ dựng những engines cần thiết cho từng test suite.** Một bài test KV không nên phải dựng CA, database plugin và Transit nếu không sử dụng; làm vậy tăng độ trễ, rủi ro flaky và khó xác định nguyên nhân.

## 11. Kiểm thử auth và ACL bằng token của workload

Trong production, `ClientAuthentication` thường được cấu hình theo Kubernetes auth hoặc AppRole. Trong Vault dev test, có hai cấp độ:

**Cấp độ A — Xác minh ACL:** operator tạo policy và token có policy đó; Spring Vault dùng `TokenAuthentication` để thực hiện request. Phù hợp mục tiêu “path/capability đúng hay sai”.

**Cấp độ B — Xác minh auth method:** test setup thêm một auth mount, role và credential thử nghiệm (ví dụ AppRole). Sau đó dùng `ClientAuthentication` thực tế mà ứng dụng định sử dụng, lấy token và kiểm tra policies. Phù hợp mục tiêu “ứng dụng đăng nhập đúng phương thức và nhận đúng quyền”.

Kubernetes auth trong một Vault container độc lập **không tự mô phỏng Kubernetes API service account identity**. Nếu muốn test Kubernetes auth thật, cần môi trường K8s phù hợp với service account JWT, issuer, CA/JWKS, role và auth backend configuration. Không tạo một JWT giả rồi kết luận workload auth của production hoạt động.

### Ma trận ACL tối thiểu

| ID | Danh tính | API request | Kết quả |
|---|---|---|---|
| A01 | Operator test | `POST sys/mounts/kv-it` | Thành công khi dựng fixture |
| A02 | Workload reader | `GET kv-it/data/apps/orders/config` | Thành công |
| A03 | Workload reader | `POST kv-it/data/apps/orders/config` | Vault từ chối (thiếu quyền ghi) |
| A04 | Workload reader | `GET kv-it/data/apps/payments/config` | Vault từ chối nếu không có policy khác |
| A05 | Workload reader | `POST sys/policies/acl/orders-it-readonly` | Vault từ chối (không quản trị policy) |
| A06 | Token không hợp lệ/hết TTL | `GET kv-it/data/apps/orders/config` | Bị từ chối xác thực, phân biệt lỗi ACL |

Với các negative cases, đừng chỉ `assertThrows(Exception.class)`; nếu fixture thất bại trước đó, test cũng có thể “pass”. Cần chạy ca positive trước, nhận diện status/error category và xác minh thao tác bị cấm **thật sự không thay đổi trạng thái**.

## 12. Mở rộng tích hợp: Transit encryption và PKI

Vault container tạm thời có thể dùng để kiểm thử thêm các secrets engines.

### Transit encryption

Fixture (operator) bật mount và tạo key riêng:

~~~bash
# Chạy trong Vault test, dùng operator token của container.
vault secrets enable -path=transit-it transit
vault write -f transit-it/keys/orders-it-key
~~~

Sau đó tạo policy workload phù hợp:

~~~hcl
path "transit-it/encrypt/orders-it-key" {
  capabilities = ["update"]
}

path "transit-it/decrypt/orders-it-key" {
  capabilities = ["update"]
}
~~~

Các assertions quan trọng:

1. Encode plaintext thành Base64 đúng yêu cầu Transit API.
2. Encrypt hợp lệ trả ciphertext có dạng `vault:vN:...`.
3. Decrypt ciphertext đó trả plaintext gốc.
4. Token không có `update` bị từ chối.
5. Encrypt/decrypt sai key hoặc context bị từ chối phù hợp.
6. Nếu test rotate, dùng key riêng; không tái sử dụng ciphertext từ test class khác.

Không assert ciphertext mã hóa hai lần phải giống nhau: thuật toán có thể có nonce ngẫu nhiên. So sánh dữ liệu sau giải mã và tiền tố phiên bản thay vì so sánh toàn bộ ciphertext.

### PKI certificates

Fixture PKI đầy đủ hơn vì phải có CA/issuer, role cấp chứng thư và giới hạn tên. Một bài test cần chứng minh:

- Với role `orders-server-it`, CN/SAN thuộc `apps.example.test` được cấp chứng thư phù hợp.
- Tên ngoài miền, wildcard hoặc TTL vượt ràng buộc bị từ chối theo cấu hình role.
- Chứng thư trả về có SAN, validity và issuer đúng; secret private key không xuất hiện trong log.
- Token workload không thể sửa `pki-it/roles/*` hoặc issuer configuration.

Không kết luận policy PKI đúng khi chỉ nhận HTTP 200; cần đọc certificate thực tế và kiểm tra hạn, Subject Alternative Names, Extended Key Usage, CA chain.

## 13. Mở rộng tích hợp: dynamic database credentials

Chạy một Vault container **và** một PostgreSQL container test. Database secrets engine cần đường mạng từ Vault tới PostgreSQL để tạo, gia hạn và thu hồi tài khoản SQL.

~~~mermaid
flowchart LR
    J["JUnit test"] --> V["Vault Testcontainer"]
    V --> P["PostgreSQL Testcontainer"]
    J --> W["Spring Vault workload client"]
    W --> V
    J --> D["JDBC dùng dynamic credential"]
    D --> P
~~~

**Cảnh báo mạng quan trọng:** `VaultContainer.getHost()` và `getMappedPort(8200)` là địa chỉ từ **JVM test chạy trên host** đến Vault. Khi **Vault container kết nối PostgreSQL container**, không dùng `localhost` hoặc mapped host port của PostgreSQL; hãy đặt chúng vào **Testcontainers Network** và dùng **network alias cùng container port**.

Các ca cần có:

| Ca | Dữ liệu/điều kiện | Kỳ vọng |
|---|---|---|
| D01 | `database/creds/orders-readonly` | Vault cấp username/password, lease ID và TTL |
| D02 | JDBC dùng user động | `SELECT` được phép theo SQL grants |
| D03 | JDBC dùng user readonly | `INSERT`/`UPDATE` bị PostgreSQL từ chối đúng vì quyền |
| D04 | Gia hạn lease | Thời hạn được gia hạn trong giới hạn cấu hình |
| D05 | Revoke lease | Kết nối **mới** bằng account cũ không còn được chấp nhận sau cleanup thành công |
| D06 | PostgreSQL tạm mất kết nối | Vault báo lỗi plugin/SQL; không ghi raw password |
| D07 | Nhiều credentials cùng role | Mỗi lease thuộc đúng tài khoản được cấp, không revoke nhầm |

Cần cân nhắc session JDBC đã mở trước revoke có thể còn hoạt động tùy PostgreSQL/plugin; kiểm tra đăng nhập mới và trạng thái account DB mới là bằng chứng chính. Phải xác minh SQL grants bằng cách tạo bảng test đã có cấu trúc/quyền phù hợp; `SELECT 1` thành công không chứng minh user có quyền đọc bảng nghiệp vụ.

## 14. Token, lease và thời gian trong test

Test dùng Vault thật giúp phát hiện lỗi rất dễ bị che bởi mock:

- Token có TTL và có thể hết hạn; `SessionManager` có thể re-auth hoặc renew.
- Database credentials trả về `lease_id`, `lease_duration`, `renewable`.
- `SecretLeaseContainer` quản lý renewal/rotation theo lifecycle riêng, không đồng nghĩa ứng dụng JDBC đã thay connection pool.
- PKI certificate TTL và key version của Transit phụ thuộc role/engine.
- Vault dev mode có đồng hồ thực và scheduling thật; test phụ thuộc chính xác mili-giây dễ flaky.

### Thiết kế test TTL ổn định

**Không** đặt TTL bằng vài trăm mili-giây rồi dùng `Thread.sleep` cố định để chờ. Nên dùng các TTL hợp lệ, ngắn vừa đủ cho integration test và điều kiện polling với deadline hữu hạn.

Ví dụ pseudo-code:

~~~text
deadline = current_monotonic_time + 30 seconds
repeat until deadline:
    inspect lease state / test a new login / observe event
    if expected terminal state reached:
        PASS
    else:
        wait a short bounded interval
FAIL with diagnostic metadata only
~~~

Nếu API thực sự hỗ trợ revoke tường minh, kiểm thử revoke có thể nhanh và quyết định hơn chờ TTL tự hết. Mọi test lease phải clean up, kể cả khi assertion thất bại; nếu còn database container bên ngoài Vault, cần bảo đảm account được thu hồi hoặc container DB cũng bị hủy.

### Phân biệt hai loại failure

| Hiện tượng | Kiểm tra |
|---|---|
| Vault token hết hạn | Workload bị lỗi xác thực khi gọi Vault |
| Database account hết hiệu lực | JDBC login thất bại dù Vault token có thể vẫn hợp lệ |
| Vault server tắt | Mạng/HTTP từ Java đến Vault lỗi |
| Database server tắt | Vault database plugin và JDBC đều có thể bị lỗi |
| Lease bị revoke | Account có thể bị xóa/khóa; cần xem cleanup và kết nối mới |

Đừng “sửa” test bằng việc kéo dài root token hoặc cấp tất cả capabilities cho workload. Test phải chứng minh ranh giới quyền vẫn được giữ.

## 15. Kiểm thử lỗi mất kết nối và retry

Một máy chủ tạm thời cho phép tạo các tình huống mà unit test khó phản ánh. Tuy nhiên, dừng `VaultContainer` trong cùng test class sẽ làm hỏng fixture và các test khác; dùng container hoặc test suite riêng cho fault injection.

Các tình huống hữu ích:

1. **Vault chưa sẵn sàng:** app phải chờ readiness hợp lý hoặc fail-fast theo cấu hình.
2. **Vault mất kết nối sau khi chạy:** request đang gửi phải timeout hữu hạn, không treo vô thời hạn.
3. **HTTP 403:** token có thể đã nhận nhưng không đủ ACL; test phải phân biệt với lỗi kết nối.
4. **HTTP 404:** secret/role không tồn tại hoặc API path sai, không được tự mặc định là 403.
5. **Token hết hạn:** client có thể cần renew/re-auth, nhưng retry phải dùng danh tính workload được duyệt.
6. **Lease renew/revoke lỗi:** thành phần quản lý lifecycle cần log metadata an toàn và báo trạng thái.
7. **TLS sai CA:** test ở môi trường Vault TLS-enabled riêng; dev HTTP test không chứng minh cấu hình TLS production.

### Retry không phải giải pháp cho mọi lỗi

- Không retry vô hạn `403 permission denied`; cần kiểm tra policy, auth và request path.
- Không retry vô điều kiện lệnh tạo **dynamic credentials**, cấp PKI certificate hay ghi dữ liệu, vì request đầu có thể đã thành công trên Vault nhưng client mất response, dẫn đến tác dụng phụ lặp lại.
- Retry có giới hạn và backoff cho lỗi mạng/tạm thời; đo thời gian và số lần thử để tránh làm tăng tải cho Vault.
- Không fallback sang root token khi workload gặp lỗi.

Với những phép kiểm thử đang tạo side effects, log/trace chỉ ghi operation, path template, request ID (nếu có) và loại lỗi; không ghi token hoặc secret.

## 16. Logging, audit và kiểm tra rò rỉ secrets trong test

Vault dev container cũng chứa **giá trị bí mật test**: root token, workload token, PKI private key và database password. Không vì là “dev token” mà in vào build log một cách tùy tiện.

Các mục cần áp dụng:

- Không `System.out.println(response)` hoặc log `VaultResponse`; phần `data` có thể chứa password/private key.
- Không ghi giá trị `auth.client_token` trong `AssertionError`, tên test, log CI hay exception message.
- Các giá trị canary/test secrets nên không trùng bất kỳ credential production nào.
- Nếu bật Vault audit device trong test, bảo vệ log artifact; audit vẫn có metadata và một số trường không HMAC.
- Có thể dùng `VaultResponse.getRequestId()` (khi response trả dạng này) để join event Java với `request.id` trong audit.
- Token root chỉ hiện trong cấu hình test do người vận hành kiểm soát; không copy log này sang issue tracker công khai.

Một test bảo mật bổ sung có thể cố ý ghi canary `integration-secret-marker-123` vào KV v2 rồi quét application log/trace output để chắc chắn canary không xuất hiện ở bất kỳ dòng không được phép nào. Kiểm thử này **khác** với việc không tìm thấy canary trong Vault audit; audit có chính sách HMAC và masking riêng.

## 17. CI/CD: từ chạy local đến quality gate

Cấu trúc kiểm thử gợi ý:

~~~text
unitTest:
  không cần Docker, không gọi Vault server

integrationTest:
  cần Docker/Testcontainers
  start Vault test container
  setup fixture
  run positive + negative assertions
  stop Vault container
  publish test report (không chứa secrets)

stagingE2E:
  chạy với môi trường gần production
  Kubernetes/AppRole, TLS, Vault namespace, network policy
  kiểm thử vòng đời thật và quyền được cấp
~~~

**Mỗi cấp có mục tiêu riêng.** Không cần thay staging E2E bằng root-token Vault dev test; cũng không nên bắt tất cả unit tests luôn phải khởi động Vault để giải bài toán không liên quan.

Một số nguyên tắc CI:

- Chốt version/digest image Vault; nâng version bằng một thay đổi có review và chạy lại integration suite.
- Không dùng `latest` image nếu muốn tái lập lỗi.
- Dùng isolated Docker network, mapped ports động và không hardcode `localhost:8200` cho mọi job.
- Chuẩn bị image cache nếu registry truy cập hạn chế.
- Đặt timeout startup hợp lý; phân biệt không tải được image với Vault health check thất bại.
- Không cấu hình CI skip test khi không có Docker nếu test là quality gate.
- Xóa container và network theo lifecycle; xử lý cả trường hợp job bị interrupt.
- Không giữ log raw chứa token trong artifacts.

### Cảnh báo về container reuse và parallelism

Testcontainers có hỗ trợ tái sử dụng container trong môi trường phát triển, nhưng không nên dùng cho Vault integration tests chạy CI nếu chưa có chiến lược cleanup hoàn chỉnh. Một policy `orders-it-readonly` sót lại từ phiên chạy trước có thể làm testcase tưởng đã setup thành công, trong khi setup mới thật sự thất bại.

Nếu muốn test theo nhóm để tiết kiệm startup, nên nhóm các tests cùng fixture vào một class và chạy tuần tự những tests chỉnh sửa cùng mount/role/key. Đừng lạm dụng một singleton VaultContainer toàn project rồi để các test class dùng chung quyền root và một database.

## 18. Troubleshooting: khi máy chủ Vault tạm thời không hoạt động

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
|---|---|---|
| `Could not find a valid Docker environment` | Docker daemon/permissions không sẵn sàng | Xác minh Docker từ JVM/CI runner, không bỏ qua test lặng lẽ |
| Container khởi động quá lâu | Image pull, tài nguyên yếu, health/wait strategy | Kiểm tra Docker logs và deadline; pin image dùng trong CI |
| HTTP connection refused tới `localhost:8200` | Dùng port cố định thay vì mapped port | Lấy `getHost()` + `getMappedPort(8200)` sau khi start |
| HTTP 403 dù root fixture thành công | Workload token thiếu policy hoặc sai path | Đọc policy, kiểm tra capability, không fallback root token |
| HTTP 404 với KV v2 | Sai mount, nhầm `data`/`metadata` hoặc key không được seed | Kiểm tra mount options/version, key fixture và path thực |
| `permission denied` khi tạo mount/policy | Fixture đang dùng workload client | Sử dụng operator test client chỉ cho setup |
| `mount already exists` | Fixture chạy lặp trên container chia sẻ | Tạo mount một lần, cô lập tên hoặc làm setup idempotent có xác minh |
| `NoUniqueBeanDefinitionException` | Tự tạo `VaultTemplate` trong khi auto-config đã có | Chọn owner bean, dùng `@Qualifier` và test config minh bạch |
| Spring Boot fail trước khi `@DynamicPropertySource` có tác dụng | Config Data Vault cần kết nối sớm hơn | Start container trước giai đoạn Config Data, hoặc tách runtime test |
| PKI test fail dù certificate hợp lệ | CA/issuer/role chưa chuẩn bị hoặc TTL/SAN mismatch | Setup issuer/role tường minh và đọc chứng thư thực |
| Database credentials trả về nhưng JDBC fail | Vault container không nối tới DB container, SQL grants/TLS sai | Sử dụng Testcontainers Network alias và kiểm tra SQL grants |
| Test ngẫu nhiên fail khi chờ lease | TTL quá ngắn, `sleep` cố định, CPU CI chậm | Poll có deadline và lựa chọn TTL hợp lý |
| Container còn chạy sau test | Chạy thủ công không cleanup, reuse hoặc job bị dừng đột ngột | Kiểm tra lifecycle và cleanup trong CI |

**Runbook ngắn:**

1. Xác định test đang dùng runtime `VaultTemplate` hay đang nạp Vault Config Data khi boot.
2. Kiểm tra container started/ready, host/port mapping và image version.
3. Kiểm tra fixture operator đã tạo mount, policy, secret/key/role như mong đợi.
4. Xác định token hiện gọi request: root fixture hay workload ít quyền.
5. Kiểm tra API path chính xác và Vault status/response (đã lọc bí mật).
6. Phân biệt 403 ACL, 404 missing path, lỗi backend và lỗi network.
7. Kiểm tra test isolation/lifecycle, nhất là khi nhiều test class chạy song song.

## 19. Bài thực hành có tiêu chí hoàn thành

### Bài A — KV v2 và quyền ít nhất

Từ ví dụ `TemporaryVaultIntegrationTest`, mở rộng một test method:

- Đọc `kv-it/data/apps/orders/config` thành công bằng workload token.
- Ghi vào cùng path bằng workload token bị từ chối.
- Đọc `kv-it/data/apps/payments/config` bị từ chối.
- Token không có quyền sửa `sys/policies/acl/orders-it-readonly`.
- Root fixture có thể tạo secret cho test nhưng không được dùng trong assertions kiểm tra ACL.

**Đạt** khi các ca đều chạy trên Vault test container thật và xác nhận chính xác loại lỗi; không tính pass khi Vault không kết nối được.

### Bài B — Transit và ciphertext

Trong một VaultContainer khác, bật Transit mount, tạo key `orders-it-key`, cấp policy cho phép `encrypt`/`decrypt` nhưng không cho phép `keys/*/rotate`. Thực hiện roundtrip encode plaintext → encrypt → decrypt. Cố rotate bằng token workload và xác minh bị từ chối.

**Đạt** khi plaintext sau decrypt bằng plaintext đầu vào và một lệnh quản trị không được cấp quyền bị Vault chặn.

### Bài C — Config Data của Spring Boot

Tạo một integration test riêng để khởi động Vault trước khi Spring Boot load `spring.config.import=vault://`, seed key cấu hình theo `spring.application.name`, khởi động ứng dụng và khẳng định property có trong `Environment`. Sau đó chạy ca thiếu quyền đọc để chắc chắn ứng dụng fail fast theo cấu hình đã chọn.

**Đạt** khi test chứng minh thời điểm khởi tạo Vault phù hợp với Config Data lifecycle, không chỉ chứng minh `VaultTemplate.read` có thể lấy secret sau boot.

### Bài D — Dynamic credential lease

Dựng Vault + PostgreSQL trên chung Testcontainers network. Định nghĩa database role readonly, lấy dynamic credential, thử `SELECT` hợp lệ và `UPDATE` trái quyền, sau đó revoke lease và thử đăng nhập JDBC **mới** bằng user cũ.

**Đạt** khi user dynamic được cấp đúng SQL permissions và bị vô hiệu hóa sau revoke, không cần đưa username/password vào log CI.

## 20. Câu hỏi tự kiểm tra

1. Vì sao một Mockito test trả về `VaultResponse` không chứng minh được Vault ACL policy đúng?
2. Trong `TemporaryVaultIntegrationTest`, root token được dùng cho việc gì và vì sao không dùng root token ở bước negative test?
3. Tại sao một VaultContainer có thể sẵn sàng nhưng application vẫn gặp 403?
4. Vì sao `@Container static` có thể gây rò rỉ trạng thái giữa các test methods?
5. `getHost()`/`getMappedPort(8200)` phục vụ kết nối từ đâu đến đâu? Vì sao container Vault cần network alias để kết nối PostgreSQL container?
6. Khi dùng `spring.config.import=vault://`, tại sao `@DynamicPropertySource` có thể không giải quyết được bài toán chọn URI của Vault trước startup?
7. Khi thử revoke database credentials, vì sao nên kiểm tra đăng nhập JDBC mới thay vì chỉ kiểm tra connection đã mở?
8. Kiểm thử ACL, kiểm thử auth Kubernetes và kiểm thử PKI role có phải cùng một bài test không?
9. Nếu một integration test negative pass do Vault chưa sẵn sàng, cần thêm bằng chứng nào để xác nhận chính sách thực sự từ chối request?
10. Những loại dữ liệu nào tuyệt đối không nên in vào build log dù chỉ dùng Vault dev container?

## 21. Tổng kết

**Máy chủ Vault tạm thời** giúp kiểm thử tích hợp Spring Vault dựa trên **Vault API thực**, thay vì chỉ mô phỏng Java method. Testcontainers/JUnit 5 cho phép dựng Vault dev container, tạo KV v2 mount, ACL policy, workload token và chạy cả ca được phép lẫn ca bị từ chối. Token quản trị chỉ dành cho fixture; ứng dụng dùng token giới hạn quyền, đúng tinh thần least privilege.

Khi kiểm thử **SPRING_VAULT**, cần phân biệt runtime `VaultTemplate` với giai đoạn nạp Config Data, tách các tầng KV/Transit/PKI/Database, quản lý token/lease có thời hạn và cô lập fixture giữa các tests. Testcontainers phù hợp để xác minh logic tích hợp và Vault semantics, còn Kubernetes auth, TLS, HA và hạ tầng production cần được xác nhận ở một tầng E2E thích hợp.

Một bộ integration test đáng tin cậy phải có **positive baseline, negative assertions có nguyên nhân rõ ràng, cleanup, không rò rỉ secrets và khả năng chạy lặp lại trong CI**.

### Tài liệu tham khảo

- [Testcontainers for Java — Vault module](https://java.testcontainers.org/modules/vault/)
- [Testcontainers for Java — JUnit 5 integration](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Testcontainers for Java — Networking](https://java.testcontainers.org/features/networking/)
- [HashiCorp Vault — Dev server](https://developer.hashicorp.com/vault/docs/concepts/dev-server)
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2)
- [HashiCorp Vault — ACL policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — Tokens](https://developer.hashicorp.com/vault/docs/concepts/tokens)
- [Spring Vault — VaultTemplate API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html)
- [Spring Cloud Vault — Config Data API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html)
