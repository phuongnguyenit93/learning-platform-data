# Chuẩn bị policy và danh tính riêng cho từng nhóm kiểm thử

## 1. Vì sao không nên chạy mọi test bằng một Vault root token?

Trong một ứng dụng Java sử dụng **Spring Vault**, kiểm thử có thể bao gồm đọc KV secrets, tạo dữ liệu fixture, xác thực AppRole/Kubernetes, gia hạn token hoặc lease, mã hóa Transit, cấp chứng thư PKI và xác nhận các thao tác không được phép. Một cách làm dễ nhưng nguy hiểm là chạy tất cả test bằng root token trong Vault dev server hoặc token quản trị của staging.

Nếu mọi test dùng cùng identity có quyền `sudo`/`root`, các case đáng lẽ phải trả `403 permission denied` sẽ vô tình thành công. Test bị lỗi có thể xóa dữ liệu của suite khác, sửa role, revoke lease hoặc làm lộ credential qua log. Kết quả **test xanh nhưng không chứng minh được policy dành cho workload production là đúng**.

Chủ đề của chương **Kiểm thử** này là **chuẩn bị Vault policy và danh tính riêng cho từng nhóm kiểm thử**. Trong module **SPRING_VAULT**, bạn sẽ áp dụng ranh giới phân quyền cho `VaultTemplate`/`VaultOperations`, cách xác thực workload và những bài thực hành KV, Transit, PKI, token/lease, lỗi và kiểm thử tích hợp.

Mục tiêu bài học:

1. Phân loại các suite và định nghĩa một **principal** (token/workload identity) theo đúng nhiệm vụ kiểm thử.
2. Tách quyền quản trị fixture, quyền của ứng dụng, quyền kiểm tra lỗi từ chối và quyền dọn dữ liệu.
3. Tạo ACL HCL với đường dẫn KV v2, Transit, PKI, lease và role được giới hạn rõ ràng.
4. Chuẩn bị auth role và credential test ngắn hạn mà không phát tán root token.
5. Chạy test Spring Vault bằng token đúng nhóm và viết assertion dương/âm có ý nghĩa.
6. Cô lập các lượt chạy CI song song, thu hồi tài nguyên và xử lý dữ liệu bí mật an toàn.

**Nguyên tắc:** Nếu test nhằm chứng minh quyền của `orders-service`, lời gọi Vault trong assertion phải được thực hiện dưới **danh tính tương đương orders-service**, không phải danh tính quản trị có thể bỏ qua ACL.

## 2. Những nhóm kiểm thử cần danh tính nào?

Không nhất thiết có một token riêng cho từng phương thức JUnit; mức tách hợp lý thường là **theo nhóm quyền/loại workload và theo lượt chạy test**.

| Nhóm | Mục tiêu | Vault identity đề xuất | Quyền cần thiết |
| --- | --- | --- | --- |
| Unit test dùng mock | Kiểm tra mapping và xử lý exception trong Java. | **Không cần** Vault token. | Không kết nối Vault thật. |
| Bootstrap/infrastructure test | Tạo mounts, auth methods, role, policy trong Vault cô lập. | Bootstrap admin chỉ dùng trong setup. | Quyền quản trị có giới hạn trong môi trường test; không chuyển cho test application. |
| Fixture writer | Tạo/cập nhật KV test data cho case đọc. | `it-orders-fixture`. | `create/update` ở đúng prefix fixture. |
| Application read test | Xác minh ứng dụng đọc đúng KV key. | `it-orders-reader`. | `read` ở prefix dữ liệu test được giao. |
| Negative authorization test | Xác nhận thiếu quyền read/write/other secret. | `it-orders-negative`. | Không có quyền nhạy cảm, hoặc có `deny` tường minh ở path kiểm tra. |
| Transit test | Encrypt-only hoặc encrypt/decrypt round-trip. | `it-transit-encrypt`, `it-transit-crypt`. | Chỉ `update` ở endpoint encrypt/decrypt cần dùng. |
| PKI test | Issue/sign certificate đúng role và từ chối role khác. | `it-pki-issuer`, `it-pki-denied`. | `update` ở một role test được phép. |
| Dynamic secrets/token lifecycle | Đọc credential/lease, renew/revoke khi được ủy quyền. | `it-db-reader`, `it-lease-operator`. | Đúng endpoint và capability cần cho case. |
| Cleanup | Dọn dữ liệu, role/key/lease được tạo trong run. | `it-cleanup` hoặc bootstrap job riêng. | Chỉ phạm vi tài nguyên của run, không quyền sửa môi trường khác. |

Đừng dùng một identity `it-all-tests` có quyền đọc/ghi mọi mount cho tất cả suite. Cũng đừng cấp token bootstrap cho Spring application context rồi hy vọng những negative test vẫn bị từ chối.

Một nguyên tắc hữu ích là **tách đường tạo dữ liệu thử nghiệm khỏi đường ứng dụng tiêu thụ dữ liệu**. Fixture writer có quyền ghi secret test; ứng dụng chỉ đọc. Từ chối truy cập phải được kiểm thử bằng identity thật sự không có quyền đó.

## 3. Ranh giới môi trường: Vault cô lập, namespace và tiền tố run

~~~text
CI / Local Test Runner
│
├── Bootstrap job (admin test-only, tồn tại ngắn)
│     ├── Mount KV v2 / Transit / PKI / DB trong Vault test
│     ├── Tạo policy và auth roles cho từng suite
│     └── Tạo fixture, bàn giao credential suite qua kênh bảo vệ
│
├── Suite A: KV reader          → token reader, chỉ read
├── Suite B: KV negative        → token denied
├── Suite C: Transit encrypt    → token chỉ encrypt
├── Suite D: PKI issue          → token chỉ issue role test
└── Cleanup job                → token cleanup, xóa phạm vi run
~~~

Ưu tiên **Vault server test riêng cho mỗi pipeline** (ví dụ container ephemeral) khi cần thử enable engine, tạo CA test hoặc revoke lease. Không thử những hành động gây side effect lên Vault production hay shared staging.

Nếu dùng Vault test chung:

- Dùng tên mount/role và tiền tố riêng cho môi trường: `secret/ci/<run-id>/...`, `transit-ci/`, `pki-ci/`, hoặc mount test tách biệt.
- Tạo `run-id` mới từ hệ thống điều phối tin cậy (ví dụ job execution ID + nonce), chỉ dùng trong path đã được kiểm soát; không chấp nhận giá trị tùy ý từ PR chưa được tin cậy làm policy path.
- Gán một **policy giới hạn đúng run-id** cho token test; không dùng policy wildcard xuyên mọi run.
- Với Vault Enterprise, có thể thêm namespace riêng nếu tổ chức có tính năng và quyền tạo namespace; **Community không có Enterprise namespaces**, nên dùng mount/path isolation phù hợp.
- Mỗi run chịu trách nhiệm cleanup secret/lease/token đã tạo, với cơ chế dọn bổ sung cho job bị hủy.

**Không coi prefix là boundary nếu ACL vẫn cho truy cập prefix của run khác.** Cần xác minh bằng cross-run negative test chứ không chỉ đặt tên thư mục khác nhau.

## 4. Ví dụ policy HCL cho nhóm KV v2

Giả định Vault test đã mount KV v2 tại `secret/` và run hiện tại có ID `run-7fd3`. Dữ liệu đọc của service `orders` nằm ở path logic:

~~~text
ci/run-7fd3/orders/config
~~~

Đường HTTP của KV v2 là `secret/data/ci/run-7fd3/orders/config`, trong khi listing/metadata sử dụng `secret/metadata/...`. Policy phải ghi **đường API đúng**, không chỉ path logic từ `kv.get`.

### 4.1. Reader: chỉ đọc fixture của run hiện tại

~~~hcl
# it-orders-reader.hcl
path "secret/data/ci/run-7fd3/orders/*" {
  capabilities = ["read"]
}
~~~

Nếu reader chỉ cần đúng một key, thu hẹp hơn:

~~~hcl
path "secret/data/ci/run-7fd3/orders/config" {
  capabilities = ["read"]
}
~~~

Trong các ví dụ kế tiếp, giả sử dùng phiên bản policy chỉ đọc một key `config`. Token này không được ghi/xóa dữ liệu hoặc đọc `ci/run-another/...`.

**Chú ý:** Capability `list` ở `secret/metadata/…` có thể làm lộ **tên key** dù người dùng không có quyền đọc nội dung. Chỉ cấp khi test thật sự phải list; không list theo mặc định.

### 4.2. Fixture writer: chỉ ghi dữ liệu của run

~~~hcl
# it-orders-fixture.hcl
path "secret/data/ci/run-7fd3/orders/*" {
  capabilities = ["create", "update", "read"]
}
~~~

Writer không có quyền cấu hình `sys/mounts`, tạo policy, cấp token cho service khác hoặc đọc dữ liệu production. Trong pipeline có thể để bootstrap job chạy lệnh chuẩn bị fixture trước rồi mới khởi động application tests; test runtime không nhận token writer.

### 4.3. Negative identity: khẳng định thiếu quyền

~~~hcl
# it-orders-negative.hcl
path "secret/data/ci/run-7fd3/orders/*" {
  capabilities = ["deny"]
}
~~~

Một token không được gắn bất kỳ policy nào cấp quyền trên path test cũng có thể làm negative test; policy `deny` ở đây giúp diễn đạt rõ ý định. `deny` có ưu tiên cao hơn các capability khác trên path tương ứng. Nhưng cần kiểm tra **toàn bộ policy gắn với token**: nếu test chỉ kiểm tra một path mà token vẫn có quyền rộng ở nơi khác thì phân quyền tổng thể chưa an toàn.

### 4.4. Cleanup: tách quyền phá hủy dữ liệu

Với KV v2, xóa version và xóa metadata có nghĩa khác nhau. Job cleanup riêng có thể được cấp `delete` trên path metadata của prefix run:

~~~hcl
# it-orders-cleanup.hcl
path "secret/metadata/ci/run-7fd3/orders/*" {
  capabilities = ["delete", "list", "read"]
}

path "secret/metadata/ci/run-7fd3/orders" {
  capabilities = ["list"]
}
~~~

Thao tác xóa metadata trong KV v2 **xóa vĩnh viễn toàn bộ versions/metadata của key**, khác với soft delete một phiên bản. Chỉ dùng trên run test riêng, sau khi xác minh prefix run thực. Cleanup token không nên có quyền xóa metadata của run khác.

### 4.5. Tại sao không dùng một policy cho cả reader và writer?

Nếu reader có `create/update` để “tiện khởi tạo data trước test”, test sẽ không phát hiện cấu hình production bị cấp dư quyền. Trong mô hình tốt, dữ liệu do một bootstrap/fixture identity tạo, sau đó ứng dụng đọc bằng token read-only. Negative test dùng một identity khác nhằm kiểm tra hành vi bị từ chối.

## 5. Mở rộng cho Transit, PKI và dynamic secrets

Chỉ bật các engine này trong Vault test được kiểm soát. Việc tạo Transit key, CA issuer hoặc DB role thường cần admin setup; runtime test chỉ thực thi endpoint đã chuẩn bị.

### 5.1. Transit: kiểm tra quyền encrypt tách khỏi decrypt

~~~hcl
# it-transit-encrypt.hcl
path "transit-ci/encrypt/ci-orders-key" {
  capabilities = ["update"]
}
~~~

Token này không được quyền `transit-ci/decrypt/ci-orders-key`. Một suite khác khi cần round-trip mã hóa và giải mã có thể nhận:

~~~hcl
# it-transit-crypt.hcl
path "transit-ci/encrypt/ci-orders-key" {
  capabilities = ["update"]
}

path "transit-ci/decrypt/ci-orders-key" {
  capabilities = ["update"]
}
~~~

Encrypt và decrypt trong Transit là các thao tác POST, nên dùng capability `update`. Test kiểm tra rằng encrypt-only token không thể decrypt. Không đưa quyền `transit-ci/keys/*` hoặc export/backup key cho application test.

### 5.2. PKI: issue certificate trên role riêng

~~~hcl
# it-pki-issuer.hcl
path "pki-ci/issue/ci-client" {
  capabilities = ["update"]
}
~~~

CA/issuer và role `ci-client` được tạo trong **setup của môi trường test**; role giới hạn SAN, TTL và mục đích sử dụng. Test issue certificate bằng token này, sau đó thử gọi `pki-ci/issue/ci-admin` (không được cấp) để xác nhận bị từ chối. Không tạo root CA test vào mount production.

Nếu test ký CSR, dùng endpoint `pki-ci/sign/ci-client` và policy `update` tương ứng, không dùng quyền issue thay thế một cách ngẫu nhiên. Khi test rotation/CA, dùng môi trường ephemeral tách biệt vì các thao tác đó ảnh hưởng toàn bộ issuer/chuỗi tin cậy.

### 5.3. Dynamic database credentials

~~~hcl
# it-db-reader.hcl
path "database-ci/creds/ci-readonly" {
  capabilities = ["read"]
}
~~~

Lời gọi `GET database-ci/creds/ci-readonly` **tạo credential mới và lease**, dù HTTP method là GET. Vì vậy capability là `read`, nhưng mỗi lần test chạy sẽ tạo tài nguyên cần revoke/cleanup. Không gọi endpoint này làm liveness probe và không tái sử dụng DB production.

Test renewal/revoke cần phân quyền trên các system endpoint liên quan theo yêu cầu và phiên bản Vault; không cấp wildcard `sys/leases/*` cho toàn bộ nhóm reader nếu chỉ cần test cấp credential. Tách identity `it-lease-operator` cho case điều khiển lease, kiểm tra cả quyền và hiệu lực thật với backend.

### 5.4. Xác thực token và endpoint self

Nếu kiểm tra `auth/token/lookup-self`, `auth/token/renew-self` hay `sys/capabilities-self`, quyền `read` hoặc `update` tương ứng cần được xác minh theo policy token (kể cả `default` policy). Chỉ cần quan sát token còn hạn hoặc self-lookup **không đồng nghĩa** token có quyền đọc secret nghiệp vụ. Không cho application test `auth/token/create` hay cấp quyền quản trị token không cần thiết.

## 6. Tạo policy và AppRole riêng cho test suite

Các lệnh dưới đây chỉ chạy bằng bootstrap identity trong **Vault development/test độc lập**. HCL ở mục trước là nội dung các policy mà đội test/IaC quản lý; worker runtime không tự sửa policy.

### 6.1. Bootstrap policy

~~~bash
# Thực hiện trong Vault test đã xác thực bằng bootstrap admin.
vault policy write it-orders-reader it-orders-reader.hcl
vault policy write it-orders-fixture it-orders-fixture.hcl
vault policy write it-orders-negative it-orders-negative.hcl
vault policy write it-transit-encrypt it-transit-encrypt.hcl
vault policy write it-pki-issuer it-pki-issuer.hcl
~~~

Trong lab độc lập, có thể tạo file HCL từ nội dung đã khai báo; nếu chạy nhiều lượt song song, **tên policy/role cũng cần gắn run-id** để tránh run B ghi đè policy của run A. Các tên `it-orders-reader` trong ví dụ chỉ dùng để bài học dễ đọc.

### 6.2. AppRole với quyền và TTL riêng từng suite

~~~bash
# Bật auth mount test, nếu chưa bật.
vault auth enable -path=approle-ci approle

# Chỉ cấp policy reader; SecretID và token đều ngắn hạn.
vault write auth/approle-ci/role/it-orders-reader \
  token_policies="it-orders-reader" \
  token_ttl="15m" \
  token_max_ttl="30m" \
  secret_id_ttl="5m" \
  secret_id_num_uses=1

vault write auth/approle-ci/role/it-orders-negative \
  token_policies="it-orders-negative" \
  token_ttl="15m" \
  token_max_ttl="30m" \
  secret_id_ttl="5m" \
  secret_id_num_uses=1
~~~

Thay role `it-orders-reader` bằng một tên có run-id khi chạy CI song song trên Vault dùng chung. Bản chất AppRole role quyết định policy sẽ gắn vào token lúc login; **policy không tự động áp dụng cho mọi token cùng tên service**.

Dùng phương thức bootstrap có trách nhiệm lấy RoleID và cấp SecretID, ví dụ:

~~~bash
# RoleID có thể được phân phối bằng kênh cấu hình đã được kiểm soát.
vault read -field=role_id auth/approle-ci/role/it-orders-reader/role-id

# SecretID được trả dưới dạng response wrapping, hạn dùng 120 giây.
vault write -wrap-ttl=120s -f \
  auth/approle-ci/role/it-orders-reader/secret-id
~~~

Pipeline chỉ bàn giao **wrapping token**, không ghi SecretID rõ vào console/log. Workload nhận token đó, kiểm tra `creation_path` đúng và unwrap một lần trước AppRole login. Wrapping token cũng là bearer credential phải được bảo vệ. RoleID, SecretID và Vault token **không được commit** vào repository hoặc đưa vào test report.

Môi trường thực có thể dùng Kubernetes auth/CI JWT/OIDC thay vì AppRole. Khi CI hỗ trợ identity federation, thường ưu tiên token ngắn hạn được Vault cấp dựa trên claims tin cậy thay vì cất SecretID dài hạn. Ràng buộc JWT role vào audience, repository/project, branch/ref, môi trường và job identity; tên claim cụ thể tùy OIDC provider. **Không cho pull request không tin cậy lấy token quản trị** chỉ vì nó được chạy trong CI.

### 6.3. TokenAuthentication trong integration test

Trong integration test cục bộ hoặc Vault ephemeral, bootstrap có thể cấp riêng một **test token TTL ngắn** rồi đưa cho test process bằng kênh bảo vệ. Với Spring Vault, `TokenAuthentication` thích hợp để test *authorization* của một token cụ thể. Để test chính cơ chế AppRole/Kubernetes auth, dùng `AppRoleAuthentication` hoặc `KubernetesAuthentication` thực, không thay bằng TokenAuthentication và gọi là test auth.

Hãy đảm bảo mỗi test suite có token được cấp **đúng policy cần kiểm tra**, không lẫn token bootstrap.

## 7. Spring Vault: mỗi suite sử dụng VaultOperations riêng

Một test muốn kiểm tra reader token phải dùng một `VaultTemplate` được tạo với client authentication của **reader identity**. Ví dụ minh họa JUnit 5:

~~~java
import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.authentication.VaultToken;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

import static org.junit.jupiter.api.Assertions.*;

class KvReaderAuthorizationIT {

    private VaultTemplate readerTemplate() {
        // Test harness cấp token riêng qua kênh bảo mật.
        // Không dùng token root/admin được cấp cho bootstrap.
        String token = System.getenv("IT_KV_READER_TOKEN");
        if (token == null || token.isBlank()) {
            throw new IllegalStateException(
                    "Thiếu reader token cho integration test");
        }

        String vaultUri = System.getenv("IT_VAULT_URI");
        if (vaultUri == null || vaultUri.isBlank()) {
            throw new IllegalStateException("Thiếu Vault test URI");
        }

        VaultEndpoint endpoint = VaultEndpoint.from(
                URI.create(vaultUri));

        return new VaultTemplate(
                endpoint,
                new TokenAuthentication(VaultToken.of(token)));
    }

    @Test
    void readerCanReadOnlyItsFixture() {
        VaultTemplate vault = readerTemplate();
        VaultKeyValueOperations kv = vault.opsForKeyValue(
                "secret", KeyValueBackend.KV_2);

        VaultResponse response =
                kv.get("ci/run-7fd3/orders/config");

        assertNotNull(response);
        Map<String, Object> data = response.getData();
        assertNotNull(data);
        assertEquals("staging-test", data.get("environment"));
    }
}
~~~

Các biến môi trường ở đây chỉ để minh họa contract giữa test harness và test process, **không phải** yêu cầu cố định của Spring Vault. Secret test nên là **giá trị giả không nhạy cảm**. Với Vault test dùng TLS, client Java phải được cấu hình truststore đúng CA và hostname. Không hạ cấp TLS validation chỉ vì test đang chạy trong CI.

**Quan trọng với `VaultTemplate`:** không tạo một bean singleton dùng bootstrap token rồi truyền vào mọi JUnit test. Nếu một `@SpringBootTest` sử dụng auto-configuration Spring Cloud Vault, cần xác minh instance `VaultOperations` đang được inject và credential mà nó sử dụng; đừng giả định override một property đã thay auth cho mọi bean tạo từ trước.

### 7.1. Negative test chứng minh reader không thể ghi

Một test sai thường chỉ assert là “không ghi được secret không tồn tại”. Điều đó dễ lẫn giữa `404` và `403`, khiến kết luận về quyền không chính xác. Hãy tạo fixture tồn tại bằng writer trước, dùng **reader token** và thử thao tác vượt quyền trên đúng path.

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.vault.VaultException;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;

import static org.junit.jupiter.api.Assertions.assertThrows;

class KvNegativeAuthorizationIT {

    // Hàm này do test harness cung cấp bằng reader identity.
    private VaultTemplate readerTemplate() {
        throw new UnsupportedOperationException("Test harness wiring");
    }

    @Test
    void readerCannotOverwriteFixture() {
        VaultTemplate reader = readerTemplate();

        assertThrows(VaultException.class, () ->
                reader.opsForKeyValue("secret", KeyValueBackend.KV_2)
                        .put("ci/run-7fd3/orders/config",
                             Map.of("environment", "should-not-write")));
    }
}
~~~

Đoạn này **chỉ minh họa assertion**, không phải class chạy được độc lập vì wiring token đang để placeholder. Trong integration suite thực, dùng helper lấy token reader giống ví dụ trước và kiểm tra lỗi là **permission denied**, không chỉ bất kỳ `VaultException` do network/mount/schema; có thể xét Vault HTTP status/exception phù hợp client version. Sau request bị từ chối, đọc lại bằng reader để xác nhận fixture chưa bị thay đổi.

Kiểm thử quyền cần phân biệt:

- **Positive:** quyền cần có phải thực sự hoạt động bằng identity đích.
- **Negative:** quyền không cần có phải thực sự bị từ chối bằng identity đích.
- **Cross-run:** reader của run A không đọc/ghi dữ liệu run B.
- **Side effect:** một request bị từ chối không làm thay đổi secret/lease/key/certificate.

Không dùng `assertThrows(Exception.class, ...)` để qua test khi Vault đang down.

## 8. Tránh chia sẻ identity giữa các test chạy song song

Một số lỗi khó tái hiện xuất hiện khi nhiều suite chạy đồng thời:

- Suite A rotate key Transit trong khi suite B đang decrypt.
- Suite A xóa metadata KV của suite B do dùng cùng path.
- Suite cleanup A revoke token mà suite B cũng đang dùng.
- Một JUnit test thay `VAULT_TOKEN` toàn tiến trình rồi test khác dùng nhầm.
- `@DirtiesContext` hoặc cache Spring context giữ `VaultOperations` của suite trước.
- Test TTL/lease dùng chung AppRole `secret_id_num_uses=1` khiến một suite tiêu thụ SecretID của suite khác.

Giải pháp:

1. Tạo `run-id` riêng và chỉ dùng prefix được policy cho phép.
2. Tạo token/role riêng cho từng suite hoặc từng scope chạy song song khi cần.
3. Đặt mount riêng cho bài test phá hủy trạng thái CA, key rotation hay engine configuration.
4. Không cập nhật environment variables hoặc static fields toàn JVM giữa những test song song.
5. Trong Spring, dùng test configuration/bean riêng hoặc tách application context khi auth/endpoint khác nhau; chỉ reuse context khi identity và cấu hình thật sự giống.
6. Không dùng chung SecretID một-lần-đăng-nhập cho nhiều instance; cấp SecretID riêng hoặc dùng workload auth cho từng pod.
7. Cleanup chỉ được chạm tài nguyên do chính run tạo ra; kiểm tra prefix an toàn trước xóa.

**Test isolation không chỉ là data isolation.** Nếu tất cả suite dùng cùng token, một test có thể giữ credential cho suite khác dù dữ liệu đã chia thư mục.

## 9. Kiểm thử xác thực workload thay vì chỉ kiểm tra ACL

`TokenAuthentication` là công cụ tốt khi chỉ muốn xác minh quyền. Nhưng khi yêu cầu kiểm tra **Kubernetes/AppRole/JWT authentication**, test phải thật sự thực hiện login bằng auth method đó, dùng role riêng cho từng loại workload.

| Nhóm | Cần xác nhận |
| --- | --- |
| AppRole positive | Đúng RoleID + SecretID chưa hết TTL/số lần dùng → token có policy dự kiến. |
| AppRole negative | SecretID sai/hết hạn/đã dùng hết → login bị từ chối. |
| Kubernetes auth | ServiceAccount/namespace/audience được bind đúng; token của service account khác không được cấp role tương tự. |
| CI JWT/OIDC | Audience, issuer, bound claims, branch/environment và expiration đúng; PR không tin cậy không được token đặc quyền. |
| Token lifecycle | TTL/max TTL/renewability/re-login theo auth method; không được tạo token quản trị ngoài policy. |

Ví dụ AppRole role `it-orders-reader` với `secret_id_num_uses=1` chỉ cho một login bằng một SecretID; đó là giới hạn của **SecretID**, không phải quyền API `read` trên KV của token được trả về. Token dùng cho API KV vẫn có TTL riêng. Nếu muốn hai test cùng đăng nhập, chuẩn bị hai SecretID khác nhau, không tăng số lần dùng vô điều kiện.

Trong Vault Enterprise, mỗi namespace có auth mount và policy riêng; request cần namespace phù hợp. Một test giả lập namespace sai không được chạy với root namespace token rồi xem là đại diện cho workload thật.

## 10. Kết hợp policy test với hợp đồng engine

Cần kiểm tra **đường API thật** và side effect của engine; không chỉ tên role/policy.

| Engine | Positive test | Negative test | Cần cleanup |
| --- | --- | --- | --- |
| KV v2 | Reader đọc `secret/data/ci/run-7fd3/orders/config`. | Reader không ghi `data/` hoặc list `metadata/` nếu chưa cấp quyền. | Dọn metadata key/version thuộc run. |
| Transit | Encrypt-only token gọi `transit-ci/encrypt/ci-orders-key`. | Encrypt-only không decrypt hoặc export key. | Key test trong mount ephemeral; xóa/rotate bằng admin test riêng khi thích hợp. |
| PKI | Issuer token gọi `pki-ci/issue/ci-client` với SAN được phép. | Không issue role khác hoặc SAN trái role. | Theo dõi serial/revoke nếu cần và hủy CA test. |
| Database dynamic | Reader gọi `database-ci/creds/ci-readonly`, credential dùng được. | Token thiếu `read` không sinh credential. | Revoke lease/DB account, dọn role test. |
| Token/lease | Auth token đúng policy; renew tự thân khi được phép. | Token không thể create/manage policy/secret khác. | Revoke token và lease gắn với run, xử lý orphan có chủ đích. |
| KV/Transit/PKI sai namespace | Chỉ token đúng namespace/path được phép. | Identity namespace khác không tiếp cận resource. | Cleanup trong đúng namespace. |

Với `GET database-ci/creds/...`, HTTP method GET nhưng **có side effect tạo credential động**, nên không dùng làm health probe liên tục. Với PKI `issue`, cũng tạo certificate/keypair; không gọi trong beforeEach của mọi unit test trừ khi test thực sự cần nó.

Một negative test “policy không có quyền” khác test “role có quyền nhưng request vi phạm ràng buộc”:

- ACL: token không có `update` trên `pki-ci/issue/ci-client` → bị từ chối trước hoặc trong authorization.
- Role constraint: token có `update` nhưng đề nghị SAN không thuộc domain cho phép → bị Vault PKI role từ chối.

Cả hai cần test riêng; không đánh đồng mã lỗi `403`, `400` hay `404` thành cùng một kết luận.

## 11. Quy trình CI nhiều giai đoạn, không phát tán token admin

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Bootstrap job
    participant V as Vault test
    participant F as Fixture writer
    participant R as Reader suite
    participant N as Negative suite
    participant C as Cleanup job
    B->>V: Setup mounts, policies, roles cho run-id
    B->>F: Bàn giao credential fixture ngắn hạn
    F->>V: Ghi KV fixture test
    B->>R: Bàn giao token reader/role credential
    B->>N: Bàn giao token denied
    R->>V: Đọc KV / thao tác được cho phép
    N->>V: Thử đọc/ghi path bị cấm
    V-->>N: Permission denied
    R-->>B: Test results không chứa secret
    N-->>B: Test results không chứa secret
    B->>C: Yêu cầu cleanup đúng run-id
    C->>V: Revoke tokens/leases và xóa data test
~~~

Đội vận hành nên tách môi trường thực thi và secret scope giữa bootstrap và application tests. Một pipeline job có đủ quyền tạo token không nên chuyển environment chứa admin token xuống test runner để tiện thao tác.

Một kịch bản triển khai:

1. **Bootstrap** (được phép quản trị Vault test): tạo mount nếu cần, policy HCL, AppRole/JWT roles, dữ liệu và danh tính suite.
2. **Fixture**: ghi dữ liệu test với writer identity, sau đó hủy token writer.
3. **Run**: mỗi suite dùng credential riêng, chạy positive/negative theo quyền.
4. **Report**: xuất kết quả assertion, latency, loại HTTP lỗi và phiên bản môi trường; không đính kèm token/key/password.
5. **Cleanup**: revoke lease/token, xóa secret/policy/role/mount test đúng phạm vi sau khi suites kết thúc, kể cả khi pipeline fail.
6. **Audit**: lưu audit metadata an toàn để xác minh principal nào gọi path nào; không coi tên hiển thị token là bằng chứng khi token đã bị chia sẻ.

Test chạy từ fork/PR không tin cậy nên dùng Vault hoàn toàn cô lập hoặc credential không có quyền vào tài nguyên nội bộ. JWT/OIDC role phải ràng buộc chặt claims và branch, đặc biệt với workflow có quyền deploy.

### 11.1. Không lưu credential test trong log và artifact

Các giá trị cần che: `VAULT_TOKEN`, SecretID, JWT assertion, wrapping token, database password, private key PKI, Transit plaintext và bất kỳ response JSON có credential. Không nên bật HTTP wire logging đầy đủ cho Vault endpoint.

Nếu cần đối chiếu policy, ghi **tên policy**, logical run-id, kết quả capabilities và status code; không ghi token. Trên môi trường test độc lập vẫn giữ quy tắc này để không tạo thói quen vô tình rò secret khi chuyển sang staging/production.

## 12. Kiểm tra capability trước test: hữu ích nhưng chưa đủ

Có thể dùng Vault CLI với đúng identity của suite:

~~~bash
# VAULT_TOKEN phải là token reader của test, không phải bootstrap token.
vault token capabilities secret/data/ci/run-7fd3/orders/config

# Kiểm tra một path không nên có quyền.
vault token capabilities secret/data/ci/run-other/orders/config

# Với Transit encrypt-only:
vault token capabilities transit-ci/encrypt/ci-orders-key
vault token capabilities transit-ci/decrypt/ci-orders-key
~~~

Nếu một lệnh được thực hiện dưới admin token, kết quả capability chỉ nói về admin, không nói về reader. Cần chạy bằng credential thật của suite hoặc gọi `sys/capabilities-self` từ chính session đó.

**Capability test không thay integration test:** `read` trên path không chứng minh secret tồn tại, `update` trên `pki/issue` không chứng minh PKI role cho phép SAN cụ thể, và một plugin có thể chưa được mount dù policy đã cho quyền. Sau capability check phải chạy positive operation và negative operation thích hợp.

Không cần cấp quyền xem toàn bộ `sys/mounts` cho mọi suite. Inventory được tạo bởi bootstrap hoặc admin test riêng; runtime chỉ cần các endpoint đúng nghiệp vụ.

## 13. Dọn tài nguyên và thu hồi danh tính sau test

Cleanup là một phần của bảo mật kiểm thử, không phải công việc tùy chọn.

- Revoke token/credential ngắn hạn khi test kết thúc; nếu token đã hết hạn có thể không cần revoke riêng nhưng cần theo dõi credential phụ trợ.
- Với dynamic DB credentials, ghi nhận lease metadata và revoke/cleanup theo cơ chế backend; kiểm tra DB account test đã được vô hiệu hóa.
- Với KV v2, phân biệt soft delete từng version và delete metadata vĩnh viễn; chỉ xóa prefix của run hiện tại.
- Với PKI, quản lý serial/CA/role test, không động tới CA staging/production. Một certificate đã được phát hành có thể tồn tại tới hết hạn dù xóa role; kiểm tra revocation theo test cần thiết.
- Với Transit, key thường không thể xóa nếu chưa cấu hình cho phép deletion; không bật deletion toàn hệ thống chỉ để cleanup. Dùng mount ephemeral và dọn mount bằng admin trong môi trường test.
- Với auth roles/policies, không xóa role đang được run khác sử dụng; đặt tên có run-id.
- Thiết kế finalizer/TTL cleanup job để thu hồi tài nguyên nếu CI bị kill trước bước dọn thông thường.

Nếu lựa chọn **một Vault dev container riêng cho mỗi job**, cleanup có thể đơn giản là hủy toàn bộ container và dữ liệu test sau khi test hoàn thành. Nhưng chỉ dùng cách đó khi môi trường thật sự hoàn toàn ephemeral và không lưu state/secret production.

## 14. Bộ kiểm thử quyền khuyến nghị

| Test ID | Identity | Endpoint/hành vi | Kỳ vọng |
| --- | --- | --- | --- |
| KV-01 | Reader | `read secret/data/ci/run-7fd3/orders/config` | Thành công; dữ liệu fixture chính xác. |
| KV-02 | Reader | `write` cùng path | Bị từ chối do không có create/update; dữ liệu không đổi. |
| KV-03 | Negative | `read` cùng path có fixture tồn tại | Bị từ chối, không rò nội dung. |
| KV-04 | Reader run A | `read` path của run B | Bị từ chối bởi policy, không phải chỉ vì key vắng mặt. |
| KV-05 | Fixture writer | Ghi fixture trong prefix run | Thành công; không ghi được path ngoài run. |
| TRANSIT-01 | Encrypt-only | Encrypt bằng key `ci-orders-key` | Thành công, ciphertext đúng định dạng. |
| TRANSIT-02 | Encrypt-only | Decrypt ciphertext đã chuẩn bị | Bị từ chối vì thiếu quyền decrypt. |
| PKI-01 | Issuer | Issue certificate bằng role `ci-client`, SAN đúng | Thành công, certificate chain hợp lệ. |
| PKI-02 | Issuer | Issue bằng role `ci-admin` | Bị từ chối do thiếu quyền trên role khác. |
| PKI-03 | Issuer | Issue `ci-client` nhưng SAN không được phép | Bị role validation từ chối. |
| DB-01 | DB reader | Cấp credential dynamic theo role `ci-readonly` | Thành công, lease và quyền DB đúng. |
| DB-02 | DB denied | Cấp credential cùng role | Bị từ chối; không tạo account mới. |
| AUTH-01 | AppRole reader | RoleID + SecretID hợp lệ | Có token TTL ngắn, chỉ policies cần thiết. |
| AUTH-02 | AppRole reader | SecretID đã dùng hết/hết TTL | Login bị từ chối. |
| CLEAN-01 | Cleanup | Dọn đúng prefix run A | Thành công; run B không bị ảnh hưởng. |

**Độ tin cậy của negative test:** phải bảo đảm test setup đúng (engine/role/fixture tồn tại). Nếu gọi sai path hoặc backend down, một `VaultException` không chứng minh phân quyền hoạt động. Kiểm tra status/error category và side effect bằng chính ứng dụng test.

## 15. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Mọi suite dùng root token. | Authorization tests giả xanh; test có thể sửa cấu hình global. | Bootstrap admin riêng, runtime suite token tối thiểu. |
| Fixture writer và reader cùng token. | Không test được việc reader không có quyền ghi. | Tách role/token writer và reader. |
| Negative test chỉ assert bất kỳ exception. | Lỗi mạng/404 cũng làm test “pass”. | Xác minh permission denied và resource tồn tại. |
| Dùng chung SecretID một lần cho nhiều test song song. | Login test va chạm, kết quả flaky. | Cấp SecretID riêng mỗi session hoặc dùng workload auth đúng cách. |
| Policy path dùng logic KV v2, thiếu `data/`. | Đúng dữ liệu nhưng ACL không khớp endpoint. | Xây policy theo HTTP API path thật. |
| Policy wildcard toàn `secret/*`. | Một suite đọc dữ liệu suite khác. | Giới hạn exact path/run prefix, test cross-run. |
| Reuse `VaultTemplate` từ Spring context dùng token admin. | Không phản ánh identity thực. | Inject/configure test client đúng role cho mỗi nhóm. |
| Bỏ cleanup sau khi test fail. | Tích tụ tokens, leases, certificates, DB accounts. | Finalizer, TTL, container ephemeral. |
| CI runner của PR không tin cậy nhận credential staging. | Mã PR có thể lấy secret ngoài mục tiêu test. | JWT/OIDC bound claims, tách môi trường không tin cậy. |
| Dùng database/PKI issue trong liveness probe. | Tạo tài nguyên mới ngoài ý muốn. | Chỉ test endpoint có side effect trong suite quản lý cleanup. |

## 16. Bài thực hành tổng hợp

Một dự án `orders-service` dùng KV v2 để đọc cấu hình, Transit để mã hóa dữ liệu nhạy cảm và PKI để cấp chứng thư client. Bạn cần chuẩn bị ba nhóm test: **reader**, **security negative** và **PKI/Transit integration**.

Hãy thiết kế theo trình tự:

1. Khởi tạo Vault test cô lập, bật `secret/` KV v2, `transit-ci/` và `pki-ci/`.
2. Tạo run-id `run-7fd3`, các HCL policy đã giới thiệu và auth roles riêng.
3. Bootstrap writer identity ghi `ci/run-7fd3/orders/config` với giá trị giả, rồi hủy writer token.
4. Reader test dùng token chỉ có `read`, gọi `VaultTemplate`/`opsForKeyValue` và đọc thành công.
5. Negative test dùng deny token, xác minh không đọc được cùng fixture **đã tồn tại**; reader cũng không ghi được.
6. Encrypt-only test mã hóa thành công nhưng không decrypt được; không đòi quyền export Transit key.
7. PKI issuer test chỉ issue role `ci-client` với SAN hợp lệ, không issue role khác hoặc SAN trái chính sách.
8. Kiểm tra cross-run access bị từ chối: run A không nhìn dữ liệu run B.
9. Dọn token, leases, KV metadata, PKI/Transit resources trong Vault test; không xóa nhầm run khác.
10. Xuất báo cáo test có tên role/policy, run-id và kết quả; che token/SecretID/private key.

Bảng nghiệm thu:

| Điều kiện | Bằng chứng PASS |
| --- | --- |
| Tách identity | Mỗi suite lấy token từ auth role/policy đúng nhiệm vụ. |
| Quyền tối thiểu | Các operation hợp lệ thành công và operation vượt quyền bị từ chối. |
| Cô lập run | Token run A không đọc, sửa hoặc xóa dữ liệu run B. |
| Hợp đồng engine | KV/Transit/PKI trả response đúng, token thật được dùng. |
| An toàn CI | Bootstrap/admin token không vào runner thực thi test của workload. |
| Cleanup | Không còn secret/token/lease ngoài phạm vi cần giữ để debug có kiểm soát. |
| Không lộ thông tin | Test report, log, trace, metrics không chứa credential rõ. |

## 17. Câu hỏi tự đánh giá

1. Vì sao unit test dùng mock không cần Vault token, còn integration test cần identity riêng?
2. Nếu reader test dùng root token, assertion nào về ACL sẽ mất giá trị?
3. KV v2 tại mount `secret/` khác nhau thế nào giữa path logical `ci/run-7fd3/orders/config` và ACL path?
4. Tại sao fixture writer cần quyền khác reader, và cleanup cần quyền khác cả hai?
5. Một token `it-transit-encrypt` nên được phép decrypt không? Dùng capability nào cho encrypt?
6. Vì sao PKI test dùng SAN ngoài role và test thiếu ACL issue là hai trường hợp lỗi khác nhau?
7. Khi `GET database-ci/creds/...` có side effect, vì sao không dùng làm health probe?
8. Làm sao dùng AppRole SecretID có `secret_id_num_uses=1` cho nhiều suite song song?
9. Khi nào chọn Vault ephemeral, khi nào dùng namespace Enterprise hoặc prefix run?
10. Vì sao test thiếu quyền phải xác minh fixture tồn tại và error là permission denied?
11. `TokenAuthentication` kiểm tra được Vault auth method Kubernetes/AppRole thật không?
12. Làm sao tránh để PR không tin cậy tiếp cận root/admin credential trong CI?
13. Những tài nguyên nào phải được thu hồi/xóa sau một test về dynamic secrets, PKI hoặc Transit?
14. Báo cáo PASS cần ghi gì để chứng minh mỗi test dùng đúng workload identity?

## Tài liệu tham khảo

- [Spring Vault — Introduction to VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — VaultTemplate Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html)
- [Spring Vault — Authentication](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — Testing / Testcontainers reference](https://docs.spring.io/spring-vault/reference/)
- [Spring Vault — KV Secrets Engine](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [HashiCorp Vault — ACL policies, capabilities và deny](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — AppRole auth method](https://developer.hashicorp.com/vault/docs/auth/approle)
- [HashiCorp Vault — AppRole API, TTL và SecretID usage](https://developer.hashicorp.com/vault/api-docs/auth/approle)
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2)
- [HashiCorp Vault — Token Capabilities](https://developer.hashicorp.com/vault/docs/commands/token/capabilities)
- [HashiCorp Vault — Response Wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping)
- [HashiCorp Vault — Kubernetes Auth](https://developer.hashicorp.com/vault/docs/auth/kubernetes)
- [HashiCorp Vault — JWT/OIDC Auth](https://developer.hashicorp.com/vault/docs/auth/jwt)
