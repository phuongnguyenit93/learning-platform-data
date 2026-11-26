# Đối chiếu repository với API KV theo cùng dữ liệu đầu vào

## 1. Bối cảnh bài thực hành tổng hợp

Trong **Spring Vault (SPRING_VAULT)**, cùng một secret KV có thể được truy cập bằng nhiều tầng API:

- **Vault Repository**: dùng mô hình Spring Data, một entity gắn `@Secret`, khóa định danh `@Id`, repository kế thừa `CrudRepository` và converter để ánh xạ đối tượng Java.
- **Vault Key-Value API**: dùng `VaultOperations.opsForKeyValue(...)` hoặc `opsForVersionedKeyValue(...)`, nơi ứng dụng làm việc với key và document trực tiếp.
- **API KV v2 cấp thấp**: dùng `VaultTemplate`/`VaultOperations` với path `secret/data/...`, đọc payload `data.data`, metadata `data.metadata` và tự gửi `options.cas` khi cập nhật có điều kiện.

Ba cách có thể truy cập **cùng một nguồn dữ liệu Vault**, nhưng **không có nghĩa output Java, metadata, path, version và hành vi xóa hoàn toàn giống nhau**. Repository đưa thêm logic ánh xạ entity, query theo ID và optimistic locking; KV API cho phép kiểm soát rõ dữ liệu và metadata.

Đây là bài **Thực hành tổng hợp** có mục tiêu **“Đối chiếu repository với API KV theo cùng dữ liệu đầu vào”**. Bài tập hướng tới ứng dụng Java sử dụng Spring Vault, workload authentication và policy tối thiểu. Bạn sẽ viết một entity mẫu, cấu hình repository và API KV v2, thực hiện round-trip từ cả hai hướng, kiểm tra CAS, xóa mềm, lỗi quyền và xây dựng integration test.

**Lưu ý phạm vi:** đây là bài về **KV secrets engine**, không phải repository quản lý database dynamic credentials, Transit ciphertext hay PKI certificate. Token xác thực Vault có vòng đời riêng; KV v2 có **version** nhưng không phải **dynamic lease**. Chỉ chạy ví dụ với **dữ liệu giả, không nhạy cảm**, trên Vault test độc lập.

## 2. Kết quả cần đạt và tiêu chí đối chiếu

Khi hoàn thành, hai đường truy cập phải thống nhất ở **giá trị nghiệp vụ**, **đường dẫn**, **version hiện tại**, **thao tác cập nhật** và **quyền thực tế**.

| Tiêu chí | Repository | KV API v2 | Điều kiện PASS |
| --- | --- | --- | --- |
| Định danh | `@Id id` + `@Secret` keyspace | Path tương đối trong mount | Cùng ID ánh xạ đến cùng một secret |
| Dữ liệu | Java entity qua `VaultConverter` | JSON document/map | Các field nghiệp vụ đồng nhất |
| Metadata lớp Java | Converter có thể ghi `_class` | Thấy nguyên field trong JSON | Không nhầm `_class` với nghiệp vụ |
| Version | `@Version` | `metadata.version` | Đọc ra cùng current version |
| Cập nhật cạnh tranh | Spring Data optimistic locking | `options.cas` | Write stale bị từ chối |
| Xóa | `deleteById` hoặc `delete(entity)` | KV v2 delete API | Không hiểu nhầm xóa mềm là destroy |
| Danh sách | `findAll`, `count` cần list | LIST metadata prefix | Kết quả tương đương trong một snapshot ổn định |
| Phân quyền | Repository cần mount discovery và các endpoint phù hợp | Quyền data/metadata theo thao tác | Test dùng token workload, không dùng root |

**Điểm cần nhớ:** không dùng `Objects.equals(repoEntity, vaultResponse)` để so sánh. Một đối tượng repository và một raw `VaultResponse` có cấu trúc, metadata và loại Java khác nhau. Ta cần **chuẩn hóa về các field nghiệp vụ mong đợi** trước khi đối chiếu.

## 3. Kiến trúc bài lab và đường đi của dữ liệu

Giả sử ứng dụng `orders-api` giữ một số cấu hình kiểm thử trong KV v2 tại mount `secret`.

~~~mermaid
flowchart LR
    IN[Cùng input: id, serviceName, enabled, labels] --> R[Spring Data Vault Repository]
    IN --> K[Vault KV v2 API]
    R --> CONV[VaultConverter: entity -> JSON]
    CONV --> E[(Vault KV v2: secret/compare-lab/id)]
    K --> RAW[HTTP KV v2: data + metadata]
    RAW --> E
    E --> M[So sánh business fields + version]
    M --> V[Assertions và báo cáo kết quả]
~~~

Một **đường dẫn logic** duy nhất được dùng xuyên suốt:

~~~text
Vault KV v2 mount:               secret
Repository keyspace:             compare-lab
Entity ID:                       case-001
Logical KV path:                 compare-lab/case-001

HTTP read/write:                 /v1/secret/data/compare-lab/case-001
HTTP metadata:                   /v1/secret/metadata/compare-lab/case-001
Spring Vault low-level path:     secret/data/compare-lab/case-001
Spring Vault versioned KV path:  compare-lab/case-001
Repository lookup key:           case-001
~~~

Điểm khác biệt dễ gây lỗi: `VaultOperations.read("secret/data/compare-lab/case-001")` đã dùng **path đầy đủ** với `data/`, trong khi `opsForVersionedKeyValue("secret").get("compare-lab/case-001")` nhận **path tương đối**, tự đưa `data/` vào khi gửi HTTP. Trộn hai kiểu path sẽ dẫn đến 404 hoặc ghi vào key khác.

## 4. Chuẩn bị Vault test và quyền truy cập

### 4.1. Bật KV v2 trong môi trường cô lập

Ví dụ sử dụng Vault CLI với quyền quản trị **chỉ trong lab**:

~~~bash
# Chạy một lần khi mount "secret" chưa tồn tại.
vault secrets enable -path=secret -version=2 kv

# Xác minh mount có type=kv, options version=2.
vault secrets list -detailed

# Tạo một key mẫu để xác nhận API thực sự hoạt động.
vault kv put -mount=secret compare-lab/sanity serviceName=orders
vault kv get -mount=secret compare-lab/sanity
~~~

Nếu mount `secret` đã tồn tại, **không enable lại hoặc thay cấu hình vô điều kiện**. Một test suite nên được cấp Vault instance/namespace hoặc mount cô lập; không ghi vào secret production. Lệnh CLI có data thử vô hại, không đưa password/token thực vào shell history.

### 4.2. Policy tối thiểu cho các thao tác cần kiểm tra

Một policy ví dụ cho **workload lab**:

~~~hcl
# Ghi, đọc và xóa mềm các key trong keyspace.
path "secret/data/compare-lab/*" {
  capabilities = ["create", "read", "update", "delete"]
}

# List theo prefix và đọc metadata version/trạng thái xóa.
path "secret/metadata/compare-lab" {
  capabilities = ["list"]
}

path "secret/metadata/compare-lab/*" {
  capabilities = ["read", "list"]
}

# Một số luồng Spring Vault cần mount discovery.
# Kiểm tra ACL thực tế và chính sách Vault deployment.
path "sys/internal/ui/mounts/secret" {
  capabilities = ["read"]
}

path "sys/internal/ui/mounts/secret/*" {
  capabilities = ["read"]
}
~~~

**Giải thích:**

- `secret/data/...` xử lý dữ liệu; `secret/metadata/...` hỗ trợ xem metadata và LIST.
- Repository có thể tìm engine/mount qua `sys/internal/ui/mounts/...`. Nếu lookup mount bị từ chối bởi policy hoặc cấu hình Vault, repository có thể không hoạt động dù một lệnh HTTP KV trực tiếp vẫn đọc được.
- Không cấp `sys/mounts/*`, Vault root hoặc `secret/*` cho workload chỉ thực hành một prefix.
- Trong ứng dụng thật, phân quyền `read/write` và `list/delete` thường nên tách theo use case; policy trên là tập quyền **cần cho bài lab tích hợp**, không phải đề xuất cấp chung cho mọi production service.

Mặc dù có policy minh họa cho endpoint mount discovery, hành vi `sys/internal/ui/mounts` còn phụ thuộc cách Vault thực thi preflight và phiên bản server. **Hãy xác minh từ integration test với token workload thực**, đừng giả định ACL copy-paste là luôn đủ.

### 4.3. Authentication theo workload

Các lời gọi từ repository và KV API phải dùng **cùng một cấu hình `VaultTemplate`/`VaultOperations`**, với `ClientAuthentication` phù hợp (Kubernetes, JWT hoặc AppRole). Trong lab có thể dùng token test ngắn hạn do fixture cung cấp. Không hardcode root token trong Java.

Một lỗi kiểm thử phổ biến là repository dùng `VaultTemplate` có workload policy hạn chế, trong khi raw HTTP client lại dùng admin token nên mọi thao tác đều thành công. Khi đó phép so sánh về **quyền và lỗi** mất ý nghĩa. Nếu cần admin để setup/cleanup, giữ riêng khỏi cả hai client đang kiểm thử.

## 5. Bộ dữ liệu đầu vào chung

Dùng bộ dữ liệu có cấu trúc đơn giản nhưng đủ để kiểm tra nested mapping:

~~~json
{
  "id": "case-001",
  "serviceName": "orders-api",
  "enabled": true,
  "labels": {
    "environment": "integration-test",
    "region": "apac"
  }
}
~~~

Ở đây `id` là phần tử định danh path của repository, không nhất thiết là field nằm trong JSON data lưu tại Vault. `serviceName`, `enabled` và `labels` là các **field nghiệp vụ để đối chiếu**. Tất cả đều là dữ liệu giả.

Thiết kế **hai loại kiểm tra**:

1. **Cùng một key và cùng dữ liệu:** repository ghi key `case-001`, raw KV API đọc đúng key đó. Sau đó raw API cập nhật có CAS, repository đọc lại.
2. **Hai key độc lập cùng payload nghiệp vụ:** repository tạo `repo-case-001`, raw API tạo `api-case-001`; sau khi chuẩn hóa bỏ ID/path và metadata kỹ thuật, hai kết quả phải chứa cùng field nghiệp vụ.

Cách thứ nhất xác minh **interoperability**; cách thứ hai giúp phát hiện sự khác biệt do **mapping và default fields**, đồng thời tránh nhầm rằng hai phép ghi độc lập phải có cùng version number.

## 6. Chuẩn bị Spring Data Vault Repository

### 6.1. Dependencies và version

Vault repositories dựa trên Spring Data Commons và Spring Data KeyValue. Với Maven, cần một BOM tương thích với Spring Boot/Spring Vault đang dùng, rồi thêm các thành phần cần thiết:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-keyvalue</artifactId>
  </dependency>
</dependencies>
~~~

Trong dự án thật, `spring-data-commons` thường được kéo theo từ hệ sinh thái Spring Data. **Không sao chép các version độc lập rồi bỏ qua Spring Boot BOM / Spring Data BOM**: repository abstraction, `@Version` và mapping cần bộ dependencies tương thích. Spring Vault hỗ trợ KV v2 repository từ nhánh 2.4; tính năng/kiểu interface có thể thay đổi theo version, nên kiểm tra docs tương ứng với dependency tree.

### 6.2. Domain entity gắn `@Secret`, `@Id`, `@Version`

Dùng JavaBean có constructor rỗng để converter ánh xạ dễ dàng:

~~~java
package com.example.vaultlab;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.vault.repository.mapping.Secret;

@Secret(value = "compare-lab", backend = "secret")
public class LabSetting {

    @Id
    private String id;

    @Version
    private Long version;

    private String serviceName;
    private boolean enabled;
    private Map<String, String> labels = new LinkedHashMap<>();

    public LabSetting() {}

    public LabSetting(String id, String serviceName,
            boolean enabled, Map<String, String> labels) {
        this.id = id;
        this.serviceName = serviceName;
        this.enabled = enabled;
        this.labels = new LinkedHashMap<>(labels);
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Long getVersion() {
        return version;
    }

    public void setVersion(Long version) {
        this.version = version;
    }

    public String getServiceName() {
        return serviceName;
    }

    public void setServiceName(String serviceName) {
        this.serviceName = serviceName;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Map<String, String> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, String> labels) {
        this.labels = new LinkedHashMap<>(labels);
    }
}
~~~

Ý nghĩa annotation:

- `@Secret(value="compare-lab", backend="secret")`: chọn **keyspace** và mount `secret`. Nếu chỉ dùng `@Secret` không tham số, keyspace có thể suy ra từ tên entity và không trùng path trong bài.
- `@Id`: ID kiểu `String` là phần cuối của key `compare-lab/<id>`. Không lấy username/password thật làm ID.
- `@Version`: phiên bản KV v2 dùng cho optimistic locking; thuộc tính numeric `Long` được map vào cơ chế CAS khi cập nhật. Nó không phải một field nghiệp vụ phải ghi thủ công vào JSON document.
- `labels`: map lồng nhau, dùng để xác minh converter và raw JSON đều giữ đúng các cặp khóa/giá trị.

Không đưa `LabSetting.toString()` chứa secret thật vào log khi áp dụng mẫu này cho dữ liệu nhạy cảm. Bản thân class học tập chỉ chứa giá trị giả.

### 6.3. Repository interface và cấu hình Spring

~~~java
package com.example.vaultlab;

import java.util.List;

import org.springframework.data.repository.CrudRepository;

public interface LabSettingRepository
        extends CrudRepository<LabSetting, String> {

    List<LabSetting> findByIdStartingWith(String prefix);
}
~~~

~~~java
package com.example.vaultlab;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.repository.configuration.EnableVaultRepositories;

@Configuration
@EnableVaultRepositories(basePackageClasses = LabSettingRepository.class)
public class VaultRepositoryConfiguration {
    // VaultTemplate/VaultOperations dùng chung được cấu hình
    // qua các bean authentication, TLS và endpoint của ứng dụng.
}
~~~

Với Spring Vault 4.x hoặc nhánh phù hợp, `@EnableVaultRepositories` kích hoạt repository và wiring tới `VaultTemplate`/`VaultOperations`. Nếu có nhiều `VaultTemplate` hoặc `KeyValueTemplate` beans, cần cấu hình đúng bean refs thay vì để repository dùng nhầm client.

Repository **không sử dụng SQL**: `findByIdStartingWith` thường bắt đầu bằng thao tác **LIST key** ở KV prefix, lọc theo ID rồi fetch các entity liên quan. Nó không phải index backend trên các trường `serviceName` hoặc `enabled`. Paging/sorting cũng có thể tốn nhiều HTTP calls. Không dùng Vault Repository như một database query engine cho hàng triệu bản ghi.

## 7. Đọc và ghi cùng key qua repository

### 7.1. Repository ghi đầu tiên

~~~java
LabSetting input = new LabSetting(
        "case-001",
        "orders-api",
        true,
        Map.of(
                "environment", "integration-test",
                "region", "apac"));

LabSetting saved = repository.save(input);
LabSetting fromRepository =
        repository.findById("case-001").orElseThrow();

assertThat(fromRepository.getServiceName())
        .isEqualTo("orders-api");
assertThat(fromRepository.isEnabled()).isTrue();
assertThat(fromRepository.getLabels())
        .containsEntry("region", "apac");
assertThat(fromRepository.getVersion())
        .isNotNull()
        .isPositive();
~~~

Đây là **phác thảo JUnit + AssertJ**, trong đó `repository` được Spring test context cung cấp. Kết quả `repository.save()` có thể là một entity được converter cập nhật version; **luôn đọc lại từ Vault** trước khi so sánh metadata, không giả định object đầu vào đã được mutate theo một cách cụ thể.

### 7.2. Repository lưu gì vào Vault?

Document được `VaultConverter` tạo ra thường có cấu trúc gần như:

~~~json
{
  "_class": "com.example.vaultlab.LabSetting",
  "serviceName": "orders-api",
  "enabled": true,
  "labels": {
    "environment": "integration-test",
    "region": "apac"
  }
}
~~~

`_class` là **type hint** của Spring Data mapping, không phải trường người dùng nhập. Theo quy tắc mapping mặc định, định danh `@Id` nằm ở path, còn `@Version` liên quan metadata KV v2. Đừng assert rằng raw JSON bắt buộc có `id` và `version` như bộ dữ liệu nhập ban đầu.

Thực tế dữ liệu có thể khác do `VaultCustomConversions`, alias type, annotations hoặc phiên bản converter. **Integration test phải quan sát document thực**, không hardcode một layout không thuộc hợp đồng của dự án.

## 8. Dùng VaultOperations để đọc chính key repository vừa ghi

### 8.1. API KV v2 cấp thấp

~~~http
GET /v1/secret/data/compare-lab/case-001
X-Vault-Token: <WORKLOAD_TOKEN>
~~~

Phản hồi rút gọn:

~~~json
{
  "data": {
    "data": {
      "_class": "com.example.vaultlab.LabSetting",
      "serviceName": "orders-api",
      "enabled": true,
      "labels": {
        "environment": "integration-test",
        "region": "apac"
      }
    },
    "metadata": {
      "version": 1,
      "created_time": "2026-11-25T10:00:00Z",
      "deletion_time": "",
      "destroyed": false
    }
  }
}
~~~

`version: 1` là ví dụ cho một key mới tạo sạch; **không khẳng định test nào cũng bắt đầu ở version 1** nếu không dọn fixture. Một write mới trên cùng key tạo version mới.

### 8.2. Adapter đọc raw dữ liệu và version

~~~java
package com.example.vaultlab;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;

import org.springframework.stereotype.Component;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Component
public final class RawKvV2Adapter {

    private static final String PREFIX =
            "secret/data/compare-lab/";

    // Ngăn ID tùy ý chèn thêm slash/path segment.
    private static final Pattern ID_PATTERN =
            Pattern.compile("[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}");

    private final VaultOperations vault;

    public RawKvV2Adapter(VaultOperations vault) {
        this.vault = vault;
    }

    public KvSnapshot read(String id) {
        String path = path(id);
        VaultResponse response = vault.read(path);
        Map<String, Object> outer = requireData(response);

        Map<String, Object> document = objectMap(
                outer.get("data"), "data");
        Map<String, Object> metadata = objectMap(
                outer.get("metadata"), "metadata");

        int version = positiveVersion(
                metadata.get("version"));

        return new KvSnapshot(
                Collections.unmodifiableMap(
                        new LinkedHashMap<>(document)),
                version);
    }

    public int replaceAtVersion(
            String id, int expectedVersion,
            Map<String, Object> completeDocument) {

        if (expectedVersion <= 0) {
            throw new IllegalArgumentException(
                    "Expected existing positive version");
        }
        Objects.requireNonNull(completeDocument, "completeDocument");

        Map<String, Object> request = Map.of(
                "options", Map.of("cas", expectedVersion),
                "data", new LinkedHashMap<>(completeDocument));

        VaultResponse response = vault.write(path(id), request);

        return positiveVersion(
                requireData(response).get("version"));
    }

    private static String path(String id) {
        if (id == null || !ID_PATTERN.matcher(id).matches()) {
            throw new IllegalArgumentException("Invalid secret id");
        }
        return PREFIX + id;
    }

    private static Map<String, Object> requireData(
            VaultResponse response) {
        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Missing KV v2 response data");
        }
        return response.getData();
    }

    private static int positiveVersion(Object raw) {
        if (!(raw instanceof Number version)
                || version.intValue() <= 0) {
            throw new IllegalStateException("Invalid KV version");
        }
        return version.intValue();
    }

    private static Map<String, Object> objectMap(
            Object raw, String field) {
        if (!(raw instanceof Map<?, ?> map)) {
            throw new IllegalStateException(
                    "Missing KV field: " + field);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalStateException(
                        "Non-string KV map key");
            }
            result.put(key, entry.getValue());
        }
        return result;
    }

    public record KvSnapshot(
            Map<String, Object> document,
            int version) {}
}
~~~

Adapter cố ý làm ba việc rõ ràng:

1. Sử dụng `secret/data/compare-lab/<id>` để đọc/ghi KV v2, không thêm prefix HTTP `/v1/` vào `VaultOperations`.
2. Tách document nghiệp vụ ra khỏi metadata `version`.
3. Khi cập nhật, gửi `options.cas` và **toàn bộ document** để tránh ghi đè không có điều kiện.

Hàm `replaceAtVersion` không hỗ trợ tạo path mới. Muốn tạo **chỉ khi path chưa tồn tại**, phải có một operation riêng gửi `cas=0`. Không truyền 0 vào method cập nhật chỉ dành cho secret đã tồn tại.

**An toàn dữ liệu:** bản sao map ở adapter là **shallow copy**, không làm bất biến các map/list lồng nhau. Với dữ liệu nhạy cảm có cấu trúc phức tạp, cần cơ chế kiểm soát mutation, validate schema và tuyệt đối không log toàn bộ `VaultResponse`.

## 9. Kịch bản 1 — Repository ghi, raw KV API đọc

Dùng **chính dữ liệu đầu vào ở mục 5**:

~~~java
@Test
void repositoryWriteMustBeVisibleThroughRawKvApi() {
    String id = uniqueTestId("repo-to-api");

    LabSetting input = new LabSetting(
            id, "orders-api", true,
            Map.of("environment", "integration-test",
                   "region", "apac"));

    repository.save(input);

    LabSetting byRepository =
            repository.findById(id).orElseThrow();

    RawKvV2Adapter.KvSnapshot byApi = rawKv.read(id);

    assertThat(byApi.document().get("serviceName"))
            .isEqualTo(byRepository.getServiceName());
    assertThat(byApi.document().get("enabled"))
            .isEqualTo(byRepository.isEnabled());

    assertThat(byApi.document().get("labels"))
            .isEqualTo(byRepository.getLabels());

    assertThat(byApi.version())
            .isEqualTo(byRepository.getVersion().intValue());
}
~~~

`uniqueTestId()` là fixture tạo ID hợp lệ, ví dụ `repo-to-api-7a1b`. Nó phải tạo key riêng cho test run để version/data không bị test khác thay đổi. Kiểm tra `_class` có mặt nếu đang dùng converter mặc định, nhưng không đưa `_class` vào tiêu chí so sánh field nghiệp vụ.

**Kết luận của kịch bản:** repository thực sự lưu dữ liệu vào KV v2 ở path mong đợi; raw API có thể đọc **cùng một document** và metadata version.

## 10. Kịch bản 2 — Raw API cập nhật, repository đọc lại

Tiếp theo, sử dụng key đã được repository tạo để đổi duy nhất `enabled`:

~~~java
@Test
void rawApiUpdateMustBeVisibleThroughRepository() {
    String id = uniqueTestId("api-to-repo");
    repository.save(new LabSetting(
            id, "orders-api", true,
            Map.of("environment", "integration-test",
                   "region", "apac")));

    RawKvV2Adapter.KvSnapshot before = rawKv.read(id);

    Map<String, Object> updated =
            new LinkedHashMap<>(before.document());
    updated.put("enabled", false);

    int newVersion = rawKv.replaceAtVersion(
            id, before.version(), updated);

    LabSetting byRepository =
            repository.findById(id).orElseThrow();

    assertThat(byRepository.isEnabled()).isFalse();
    assertThat(byRepository.getServiceName())
            .isEqualTo("orders-api");
    assertThat(byRepository.getLabels())
            .containsEntry("region", "apac");
    assertThat(byRepository.getVersion().intValue())
            .isEqualTo(newVersion);
}
~~~

Vì sao **copy raw document rồi chỉ sửa một field**? Theo cấu trúc KV v2, `POST /data/<path>` **thay toàn bộ map dữ liệu** của version mới. Nếu gửi mỗi `{"enabled":false}`, bạn có thể làm mất `serviceName`, `labels` và `_class` vốn do converter ghi. Kết quả có thể khiến repository đọc sai hoặc mất dữ liệu.

**Không cập nhật bằng cách đổi CAS sang version hiện tại nhưng giữ snapshot cũ.** Nếu writer khác đã sửa tài liệu, bạn phải đọc lại, áp dụng lại ý định thay đổi và gửi CAS mới.

## 11. Kịch bản 3 — Cùng payload nghiệp vụ, hai key riêng

Kịch bản này đối chiếu **đường ghi của hai abstraction**, không chỉ tính tương thích khi đọc.

### 11.1. Repository tạo key A

~~~java
String repoId = uniqueTestId("repo");
repository.save(new LabSetting(
        repoId, "orders-api", true,
        Map.of("environment", "integration-test",
               "region", "apac")));
~~~

### 11.2. Raw API tạo key B với CAS 0

Raw writer có thể gửi document theo đúng schema entity. Vì một repository có thể sử dụng `_class` để hỗ trợ type mapping, test có thể ghi type hint tương ứng với class cụ thể; trong production hãy kiểm soát class name và không chấp nhận `_class` không đáng tin từ người dùng.

~~~java
String apiId = uniqueTestId("api");
String path = "secret/data/compare-lab/" + apiId;

Map<String, Object> apiDocument = Map.of(
        "_class", LabSetting.class.getName(),
        "serviceName", "orders-api",
        "enabled", true,
        "labels", Map.of(
                "environment", "integration-test",
                "region", "apac"));

vaultOperations.write(
        path,
        Map.of(
                "options", Map.of("cas", 0),
                "data", apiDocument));
~~~

Đoạn trên là **request create-only**: chỉ thành công nếu key B chưa có lịch sử version. Nếu test chạy lại với cùng key, cần đổi ID hoặc cleanup **trong Vault test** theo đúng quyền và mục đích; không dùng CAS 0 để “tạo lại” một secret đã soft delete.

### 11.3. Đối chiếu sau khi đọc

~~~java
LabSetting fromRepoA =
        repository.findById(repoId).orElseThrow();
LabSetting fromRepoB =
        repository.findById(apiId).orElseThrow();

assertThat(fromRepoB.getServiceName())
        .isEqualTo(fromRepoA.getServiceName());
assertThat(fromRepoB.isEnabled())
        .isEqualTo(fromRepoA.isEnabled());
assertThat(fromRepoB.getLabels())
        .isEqualTo(fromRepoA.getLabels());
~~~

ID của A và B **cố ý khác**, vì cả hai là hai key độc lập. Version cũng có thể khác nếu key có lịch sử trước đó; không yêu cầu `versionA == versionB` khi đối chiếu payload. Trong fixture mới tạo sạch, thường cả hai là version đầu tiên, nhưng test không cần dựa vào giả định này.

### 11.4. Vì sao không dùng raw document làm chuẩn tuyệt đối?

Repository có thể lưu `_class`, các converter riêng, alias hoặc kiểu dữ liệu có representation khác raw input ban đầu. Khi muốn kiểm tra tương đương về nghiệp vụ, hãy trích các trường cụ thể:

~~~java
record BusinessView(
        String serviceName,
        boolean enabled,
        Map<String, String> labels) {}

static BusinessView normalize(LabSetting entity) {
    return new BusinessView(
            entity.getServiceName(),
            entity.isEnabled(),
            Map.copyOf(entity.getLabels()));
}
~~~

So sánh `normalize(fromRepoA)` và `normalize(fromRepoB)`, không so sánh nguyên JSON có metadata kỹ thuật. Đồng thời nên có test riêng cho **mapping contract** để phát hiện khi một phiên bản converter thay đổi type hint hoặc tên field.

## 12. Kịch bản 4 — @Version của repository và CAS của API KV

KV v2 bảo vệ concurrent updates bằng `options.cas`. Spring Vault Repository sử dụng `@Version` để phát hiện ghi stale, thường ném `OptimisticLockingFailureException` khi dữ liệu đã bị writer khác thay đổi.

### 12.1. Hai repository readers cùng một version

~~~java
@Test
void repositoryMustRejectStaleVersion() {
    String id = uniqueTestId("repo-cas");

    repository.save(new LabSetting(
            id, "orders-api", true,
            Map.of("environment", "integration-test")));

    LabSetting first =
            repository.findById(id).orElseThrow();
    LabSetting stale =
            repository.findById(id).orElseThrow();

    first.setServiceName("orders-api-v2");
    repository.save(first); // Version tăng tại Vault.

    stale.setEnabled(false);

    assertThatThrownBy(() -> repository.save(stale))
            .isInstanceOf(
                    org.springframework.dao
                            .OptimisticLockingFailureException.class);

    LabSetting latest =
            repository.findById(id).orElseThrow();

    assertThat(latest.getServiceName())
            .isEqualTo("orders-api-v2");
    assertThat(latest.isEnabled()).isTrue();
}
~~~

Đây là test ý nghĩa hơn kiểm tra mỗi message lỗi: nó chứng minh **ghi stale không làm mất cập nhật đã thành công**. Trong môi trường có writer ngoài test, nên dùng ID riêng và chặn test khác cùng path.

### 12.2. Repository cập nhật khiến raw CAS cũ thất bại

~~~java
@Test
void repositoryUpdateMustInvalidateOldRawCas() {
    String id = uniqueTestId("cross-cas");
    repository.save(new LabSetting(
            id, "orders-api", true, Map.of("region", "apac")));

    RawKvV2Adapter.KvSnapshot staleRaw = rawKv.read(id);

    LabSetting current =
            repository.findById(id).orElseThrow();
    current.setServiceName("orders-api-v2");
    repository.save(current);

    // Dùng version cũ. Vault phải từ chối write này.
    Map<String, Object> staleDocument =
            new LinkedHashMap<>(staleRaw.document());
    staleDocument.put("enabled", false);

    assertThatThrownBy(() ->
            rawKv.replaceAtVersion(
                    id, staleRaw.version(), staleDocument))
            .isInstanceOf(RuntimeException.class);

    LabSetting latest = repository.findById(id).orElseThrow();
    assertThat(latest.getServiceName())
            .isEqualTo("orders-api-v2");
    assertThat(latest.isEnabled()).isTrue();
}
~~~

**Chú ý:** `RuntimeException` chỉ là assertion tối thiểu trong ví dụ raw API. Một integration test nghiêm túc cần phân loại đúng response **CAS mismatch** từ Vault (thường HTTP 400 với thông tin check-and-set) và **không** chấp nhận lỗi mạng/403/404 như bằng chứng CAS đã hoạt động.

Với Spring Vault version cụ thể, `@Version` trên repository được mapping qua CAS, còn raw API phải tự gửi `options.cas`. Nếu một writer bỏ CAS, nó có thể ghi đè một writer khác và làm phép thử optimistic locking sai kỳ vọng. Có thể cấu hình `cas_required` ở mount/key test để bắt buộc mọi writer tuân thủ.

### 12.3. Retry thế nào là đúng?

Khi gặp CAS mismatch đã xác nhận:

1. Đọc lại key hiện tại bằng repository hoặc raw KV.
2. Kiểm tra **ý định cập nhật** còn hợp lệ với dữ liệu mới không.
3. Tính lại document từ snapshot mới, giữ những trường không muốn thay đổi.
4. Ghi bằng version mới và giới hạn số lần retry.
5. Nếu hai writer sửa cùng trường theo quyết định khác nhau, trả **conflict nghiệp vụ**, không merge bừa.

Không được xử lý 403 (token/policy lỗi), 404 (sai path/mount) hoặc timeout như CAS mismatch. Khi timeout POST, chưa biết Vault đã ghi hay chưa; cần đối soát phiên bản và nội dung trước khi retry.

## 13. Kịch bản 5 — Xóa bằng repository và đọc bằng KV API

Ở **KV v2**, xóa secret bằng repository thường tương ứng thao tác **DELETE bản mới nhất** theo semantics KV v2, không tự động **destroy vĩnh viễn** tất cả các version. Spring Vault cũng phân biệt xóa theo ID và xóa theo entity có `@Version`.

Một test có thể:

~~~java
@Test
void repositoryDeleteMustHideLatestDataButKeepMetadata() {
    String id = uniqueTestId("delete");
    repository.save(new LabSetting(
            id, "orders-api", true,
            Map.of("environment", "integration-test")));

    repository.deleteById(id);

    assertThat(repository.findById(id)).isEmpty();

    VaultResponse metadata = vaultOperations.read(
            "secret/metadata/compare-lab/" + id);

    assertThat(metadata).isNotNull();
    assertThat(metadata.getData()).isNotNull();
}
~~~

Vì lịch sử vẫn có thể tồn tại, metadata của key vẫn có `current_version`, trạng thái xóa và các version metadata. **Không dùng `cas=0` để tạo lại key đã có history**, ngay cả khi `repo.findById(id)` báo không có dữ liệu hiện thời.

Nếu muốn kiểm tra `undelete` hoặc `destroy`, đó là **API và quyền riêng** của KV v2; không cấp các quyền nguy hiểm này cho workload chỉ cần CRUD thông thường. Xóa entity theo version có thể tác động tới một version được chỉ định, khác với `deleteById` xóa version mới nhất.

## 14. Kịch bản 6 — findAll/list và giới hạn query repository

Repository có thể cung cấp:

~~~java
Iterable<LabSetting> settings = repository.findAll();
long count = repository.count();

List<LabSetting> byPrefix =
        repository.findByIdStartingWith("case-");
~~~

Nhưng Vault KV **không có SQL query engine**:

- Repository thường **LIST các ID ở prefix**, lọc ID và đọc từng secret cần thiết.
- Query derivation chủ yếu hỗ trợ predicate theo **`@Id`**; không suy luận `findByEnabledTrue()` tương đương một indexed query ở Vault.
- Paging/sorting có thể yêu cầu liệt kê ID và tải nhiều entity vào bộ nhớ trước khi sắp xếp/lọc theo logic repository. Hiệu năng phụ thuộc số secret và số HTTP calls.
- LIST cần quyền riêng trên KV v2 **metadata path**; chỉ có `read` data thường chưa đủ.
- Khi writer tạo/xóa trong lúc LIST + GET, kết quả `findAll()` không nhất thiết là một snapshot nguyên tử.

Ví dụ HTTP LIST KV v2:

~~~http
LIST /v1/secret/metadata/compare-lab
X-Vault-Token: <WORKLOAD_TOKEN>
~~~

Vault có thể trả danh sách key dưới prefix. Cần phân biệt những tên có dấu `/` biểu diễn thư mục logic với key lá; nếu keyspace có nhiều mức lồng nhau, repository mapping và LIST path cần được kiểm tra. Không dùng secret IDs có slash khi lab chủ động giới hạn ID một segment.

**Bài đo hiệu năng:** seed 10, 100 và 1.000 key test, đo số HTTP requests và thời gian `findAll()` so với `repo.findById(id)`. Không dùng throughput của Vault repository làm tiêu chí đánh giá database PostgreSQL hay một search engine.

## 15. Ma trận sự khác biệt dễ mắc phải

| Vấn đề | Repository | API KV cấp thấp | Cách đối chiếu đúng |
| --- | --- | --- | --- |
| Path | `@Secret` backend/keyspace + `@Id` | Ghi rõ `secret/data/keyspace/id` | Xác minh cùng mount và key |
| Field `id` | Thường là định danh trong key | Có thể không nằm trong payload | So ID từ path, không bắt buộc JSON có id |
| Field `version` | Từ `@Version` | Trong `data.metadata.version` | So phiên bản, không tìm field trong document |
| Field `_class` | Do mapper thêm type hint | Raw API có thể thấy/ghi | Không tính là nghiệp vụ |
| Nested map | Converter ánh xạ theo kiểu Java | JSON object | So map theo giá trị, không so chuỗi JSON |
| Write | `save` có thể dùng optimistic locking | POST với `data` và `options.cas` | Bật CAS đúng, không ghi stale |
| Delete | Thường là soft delete ở KV v2 | DELETE data hoặc API versioned | Kiểm metadata còn tồn tại |
| List | Repository tự list/lọc | LIST metadata prefix | Kiểm quyền list và tính nhất quán thời điểm |
| Query | Chủ yếu theo ID; không index fields khác | Không có SQL-like query | Không đánh đồng repository với database |
| Error | Có thể được dịch sang Spring Data exception | Vault/HTTP exception | Phân loại theo semantic, không so class exception |
| Quyền | Mount discovery + data/metadata | Có thể chỉ cần data với read cụ thể | Dùng cùng token để test ACL |
| Version compatibility | Yêu cầu đúng Spring Data/BOM | API KV v2 được Spring Vault hỗ trợ trực tiếp | Kiểm tra dependency và runtime mount |

**Một nguyên tắc:** các field bổ sung do mapper tạo ra là một phần của **storage contract** khi nhiều ứng dụng cùng truy cập key. Nếu công cụ CLI hoặc raw API ghi đè mà làm mất `_class` hay nested field quan trọng, lần deserialize bằng repository có thể thay đổi hành vi. Cần tài liệu hóa schema khi cho phép nhiều writer.

## 16. Kiểm thử lỗi và quan sát trong môi trường tích hợp

Không chỉ kiểm tra happy path. Các lỗi có thể cho biết repository và raw API hoạt động khác nhau vì setup, policy hoặc conversion.

### 16.1. Các tình huống bắt buộc

1. **Sai mount version:** cấu hình `secret` không phải KV v2, raw path có `/data/` sai; repository có thể tự khám phá engine version hoặc thất bại ở bước phát hiện.
2. **Thiếu mount discovery:** workload đọc raw API thành công nhưng repository lỗi khi tra cứu `sys/internal/ui/mounts`.
3. **Thiếu LIST permission:** `findById` hoạt động nhưng `findAll/count` thất bại.
4. **Thiếu quyền write:** repo `save` và raw POST bị Vault từ chối; không được fallback sang root token.
5. **Sai schema:** raw API ghi `enabled="true"` kiểu string thay vì boolean; converter có thể ép kiểu hoặc báo lỗi tùy cấu hình. Test phải quyết định schema hợp lệ, không dựa vào ép kiểu tình cờ.
6. **Thiếu type hint:** thử raw document không có `_class` để xem repository có deserialize chính xác concrete entity không; không giả định hỗ trợ polymorphism nếu không test.
7. **CAS mismatch:** raw write với version cũ bị từ chối; repository với `@Version` phải tránh ghi stale.
8. **Timeout sau write:** có thể Vault đã tạo version mới dù client không nhận response; không retry tạo bản ghi với CAS đã đoán.
9. **Soft delete:** repo không đọc được latest nhưng metadata vẫn có version lịch sử.
10. **Auth token hết hạn/revoke:** hai đường truy cập phải phản ánh quyền của token thực sự được sử dụng; với SessionManager tự đăng nhập lại cần xác định token nào đã gửi request.
11. **Data bị đổi giữa hai lần đọc:** kết quả version và field không còn cùng snapshot; phải dùng barrier/test lock riêng để xác minh đối chiếu.
12. **Lỗi conversion nested field:** list/map/null hoặc enum có quy tắc serialization riêng, cần kiểm thử round-trip.

### 16.2. Metrics phù hợp

| Chỉ số đề xuất | Mục đích |
| --- | --- |
| `vault_lab_repo_requests_total` | Đếm thao tác repository theo loại/kết quả |
| `vault_lab_raw_kv_requests_total` | Đếm thao tác raw KV theo loại/kết quả |
| `vault_lab_comparison_mismatch_total` | Số khác biệt nghiệp vụ hoặc metadata |
| `vault_lab_cas_conflicts_total` | Số write bị từ chối vì CAS mismatch |
| `vault_lab_missing_metadata_total` | Response không có version/metadata hợp lệ |
| `vault_lab_operation_seconds` | Đo latency từng đường truy cập |
| `vault_lab_auth_forbidden_total` | Lỗi quyền trên path hoặc mount discovery |

Đây là **tên metric tự đề xuất cho lab**, không phải metric Spring Vault mặc định. Không đưa token, plaintext secret, `VaultResponse`, nội dung labels nhạy cảm hoặc ID có cardinality lớn vào metric label. Ở production, audit Vault có thể giúp truy vết HTTP endpoints được truy cập, nhưng quyền xem audit và dữ liệu log phải được kiểm soát.

## 17. Thiết kế một integration test suite hoàn chỉnh

### 17.1. Môi trường

Dùng một Vault test instance có KV v2, policy dành cho workload và một Spring test context. Có thể dùng container nếu hệ thống build đã hỗ trợ; không cần tạo root token ngoài fixture. Bài này không yêu cầu chạy Gradle/Maven hoặc Docker trong bước viết nội dung.

**Thứ tự setup khuyến nghị:**

1. Start Vault test độc lập, bật KV v2 ở mount `secret`.
2. Provision workload policy và auth method test.
3. Tạo một `VaultTemplate`/`VaultOperations` cho cả repository và raw adapter.
4. Kích hoạt `@EnableVaultRepositories`, xác nhận repository bean được tạo.
5. Với mỗi test, dùng ID riêng và dữ liệu giả; không dùng chung key với test song song.
6. Teardown đúng namespace/prefix test, không động vào secret của người khác.

### 17.2. Test matrix và kết quả mong đợi

| Test | Input chính | Kết quả PASS |
| --- | --- | --- |
| T1: Repo → API | Một `LabSetting` có nested labels | Raw data khớp business fields, metadata version hợp lệ |
| T2: API → Repo | Repository seed, raw CAS update | Repo đọc được giá trị mới, version tăng |
| T3: Two writers | Hai entity từ cùng version | Writer stale bị từ chối, dữ liệu mới không bị ghi đè |
| T4: Raw stale CAS | Repo update xen giữa | Raw request CAS cũ bị Vault từ chối |
| T5: Create-only | Hai request raw `cas=0` cùng path | Chỉ một request tạo được key |
| T6: Delete | Repo `deleteById` | Latest không đọc được, metadata vẫn tồn tại |
| T7: List | Nhiều IDs cùng keyspace | `findAll/count` hoạt động khi có LIST |
| T8: Missing LIST | Token chỉ có read | `findById` có thể hoạt động, `findAll` bị chặn |
| T9: Wrong mount | Repo/backend và API path không trùng | Phát hiện cấu hình sai, không báo đồng nhất giả |
| T10: Mapping drift | Raw thiếu `labels` hoặc đổi kiểu | Test xác nhận mismatch hoặc conversion error |
| T11: Auth failure | Workload token không có ACL | Không quyền ghi/đọc ngoài phạm vi |
| T12: Timeout | Mất response sau POST | Kết quả là trạng thái chưa xác định, cần đối soát |

### 17.3. Tránh test flaky

- Không so version tuyệt đối bằng `1` trừ khi fixture đảm bảo key **chưa tồn tại** và chưa từng bị soft delete.
- Không so sánh `created_time` chính xác tới mili giây giữa hai request.
- Khi so sánh repository và raw API, sử dụng **cùng một version** hoặc chặn writer khác trong khoảng đối chiếu.
- Không cho test cleanup bằng `deleteById` rồi dùng lại ID với CAS 0; soft delete giữ lịch sử.
- Không suy từ HTTP 403 rằng token đã hết hạn; có thể chỉ là policy thiếu quyền.
- Nếu test mất kết nối, không khẳng định raw write không thành công chỉ vì exception.
- Với hệ thống nhiều replica, dùng request correlation ID và dữ liệu test không nhạy cảm, không ghi giá trị secret vào log.

## 18. Bài thực hành có hướng dẫn

**Tình huống:** nhóm phát triển `orders-api` đã có code dùng repository để lưu một số cấu hình test, nhưng một công cụ CLI/migration vẫn dùng API KV trực tiếp. Hai code path cần cùng hiểu một secret.

**Các bước thực hiện:**

1. Dựng Vault test KV v2 tại mount `secret`; đặt keyspace `compare-lab`.
2. Tạo policy chứa data read/write, metadata list và các quyền mount discovery cần thiết; dùng một workload token cho cả hai client.
3. Thêm Spring Vault và Spring Data KeyValue theo BOM tương thích; tạo `LabSetting` với `@Secret`, `@Id` và `@Version`.
4. Tạo `LabSettingRepository` và cấu hình `@EnableVaultRepositories`.
5. Tạo `RawKvV2Adapter` dùng `VaultOperations`, read tách document/metadata và write với CAS.
6. Lưu entity bằng repository; đọc raw key tương ứng và so `serviceName`, `enabled`, `labels`, `version`.
7. Thực hiện raw CAS update trên cùng key; đọc lại bằng repository và chứng minh giá trị đổi đúng.
8. Tạo hai key bằng hai phương thức từ **cùng một input**, chuẩn hóa business fields và so sánh.
9. Mô phỏng một writer repository và một writer raw cùng update từ version cũ; xác minh writer stale bị từ chối.
10. Thử delete-by-ID, đọc metadata và giải thích tại sao đây không phải destroy.
11. Đo thao tác `findAll/count`, tách quyền LIST và quan sát hiệu năng.
12. Kiểm thử 403, mount discovery, schema drift, timeout và cleanup fixture.

**Bài nộp nên có:**

- Sơ đồ hai code path tới cùng KV v2 key.
- Mẫu input JSON dùng chung và một bảng kết quả PASS/FAIL cho T1–T12.
- Một ảnh chụp hoặc báo cáo **đã che dữ liệu nhạy cảm** cho version/mapping.
- Giải thích cụ thể về `_class`, `@Id`, `@Version`, `options.cas`, delete và list.
- Đề xuất chọn repository hay raw API cho production use case, kèm ràng buộc quyền và hiệu năng.

### 18.1. Câu hỏi tự đánh giá

1. Cùng input entity và JSON raw nhưng vì sao các object trả về không cùng cấu trúc?
2. `@Secret(value, backend)` kết hợp `@Id` tạo Vault path như thế nào?
3. Vì sao raw API KV v2 phải truy cập `secret/data/...` còn `opsForVersionedKeyValue` không cần `data/`?
4. Vì sao repository có thể lưu `_class` còn raw input ban đầu không có?
5. `@Version` của repository và `metadata.version` của KV v2 khác hay giống nhau?
6. Khi raw API ghi chỉ `enabled=false` mà không giữ field còn lại, rủi ro là gì?
7. Khi nào `repo.findById()` hoạt động nhưng `repo.findAll()` bị từ chối?
8. Vì sao `repo.deleteById()` không chứng minh secret đã bị destroy?
9. Nếu raw CAS update thất bại, lúc nào được retry và lúc nào phải trả conflict?
10. Tại sao không nên dùng repository query derivation thay database index?
11. Nếu hai client dùng hai Vault token khác policy, có thể so sánh quyền của hai API không?
12. Sau timeout POST, cần chứng cứ nào để xác định version đã đổi bởi chính request của mình?

## 19. Kết luận và lựa chọn cách tích hợp

**Vault Repository** phù hợp khi ứng dụng Java muốn **mô hình entity, CRUD, converter và optimistic locking** với một keyspace KV tương đối nhỏ và có schema rõ. **Vault KV API** phù hợp khi cần **kiểm soát trực tiếp document, metadata, version, CAS, delete/undelete/destroy** hoặc tương tác với hệ thống ngoài Spring Data.

**Hai lớp không phải hai kho dữ liệu:** khi mount, keyspace, ID và policy nhất quán, repository và API KV v2 nhìn vào **cùng secret**. Để chứng minh, cần **cùng input**, **đối chiếu business fields thay vì so raw object**, **kiểm tra version**, **xử lý CAS**, **hiểu delete mềm** và **kiểm thử cả hai hướng**. Authentication theo workload, policy tối thiểu, bảo vệ secret trong log, khả năng phục hồi sau timeout và integration test thực tế là điều kiện không thể bỏ qua.

### Tài liệu tham khảo

- [Spring Vault — Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html): `@Secret`, Spring Data repositories, mapping, optimistic locking và revision history.
- [Spring Vault — Vault Secrets Engines / KV](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html): API KV v1/v2 và `VaultVersionedKeyValueOperations`.
- [Spring Vault — @Secret JavaDoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/mapping/Secret.html): backend/mount và keyspace.
- [HashiCorp Vault — KV v2 HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2): data, metadata, CAS, list, delete, undelete và destroy.
- [Spring Data Commons — Repositories](https://docs.spring.io/spring-data/commons/reference/repositories.html): `CrudRepository`, repository methods và các nguyên tắc query abstraction.

Các đoạn code và policy trong bài dùng cho lab, cần xác minh dependency compatibility, Vault server version, mount discovery, TLS và bean wiring thực tế trước khi triển khai production.
