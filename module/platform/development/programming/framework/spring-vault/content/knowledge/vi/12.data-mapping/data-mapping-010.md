# Kiểm thử ánh xạ bằng dữ liệu giả và phản hồi tối thiểu

Trong Spring Vault, một lệnh đọc secret có thể thành công ở tầng HTTP nhưng dữ liệu Java vẫn sai: lấy nhầm tầng `data`, để trường bắt buộc thành `null`, hiểu nhầm metadata là secret hoặc bỏ qua lỗi phân quyền. Vì vậy, kiểm thử ánh xạ phải xác nhận **cấu trúc phản hồi Vault → đối tượng Java → quy tắc sử dụng dữ liệu**, bên cạnh việc kiểm tra mã trạng thái HTTP.

Bài thuộc chương **Ánh xạ dữ liệu**, tập trung vào cách tạo dữ liệu giả và phản hồi nhỏ nhất để kiểm thử ứng dụng Java truy cập HashiCorp Vault qua `VaultTemplate`/`VaultKeyValueOperations`. Các ví dụ dùng KV secrets v2; nguyên tắc tương tự áp dụng khi làm việc với token, lease, Transit encryption và PKI. Không cần lưu thông tin đăng nhập Vault thật để chạy các phép thử này.

## 1. Chọn đúng ranh giới kiểm thử

Một luồng đọc KV v2 thường có dạng:

```text
Ứng dụng Java
    |
    v
Service kiểm tra dữ liệu và ánh xạ sang kiểu miền nghiệp vụ
    |
    v
VaultKeyValueOperations / VaultTemplate
    |
    v
HTTP GET /v1/<mount>/data/<path>
    |
    v
HashiCorp Vault (KV v2, token/workload auth, policy)
```

Có ba cấp độ kiểm thử bổ trợ nhau:

| Cấp độ | Đối tượng thay bằng dữ liệu giả | Khẳng định chính | Không thể chứng minh |
| --- | --- | --- | --- |
| Unit test | `VaultKeyValueOperations` hoặc `VaultOperations` | Service nhận đúng kiểu dữ liệu, kiểm tra trường bắt buộc và xử lý `null`/lỗi | JSON thực tế có được Spring Vault giải mã đúng hay không |
| HTTP contract test | HTTP server cục bộ trả JSON giả cho `VaultTemplate` thật | Đường dẫn KV v2, envelope JSON, header xác thực và việc giải mã sang DTO | Chính sách ACL, engine mount, phiên bản Vault thật |
| Integration test | Vault thử nghiệm cô lập, chẳng hạn Testcontainers hoặc Vault dev | Workload authentication, policy, KV/Transit/PKI, lease và hành vi hệ thống | Độ ổn định, cấu hình của môi trường sản xuất |

**Nguyên tắc:** một unit test pass không đủ để kết luận cấu trúc JSON đúng; một mock HTTP trả `200 OK` cũng không chứng minh ứng dụng được phép truy cập Vault thật. Hãy dùng mỗi cấp độ cho đúng câu hỏi của nó.

## 2. Nhận diện đúng cấu trúc phản hồi KV v2

Giả sử secret nằm tại mount `secret`, khóa `payments` và chứa hai thuộc tính `username`, `password`.

Lệnh tương ứng với KV v2 là `GET /v1/secret/data/payments`. Phản hồi giả **tối thiểu cho phép thử ánh xạ dữ liệu** có thể là:

```json
{
  "data": {
    "data": {
      "username": "demo_reader",
      "password": "fake-password-only"
    },
    "metadata": {
      "version": 1
    }
  }
}
```

Hai tầng `data` có mục đích khác nhau:

- `data` bên ngoài là payload của API Vault.
- `data.data` là cặp khóa/giá trị thực sự được lưu trong KV v2.
- `data.metadata` mô tả phiên bản, thời điểm tạo, trạng thái xóa…; nó không phải nội dung `DatabaseSettings`.

Một phản hồi Vault thật còn có thể chứa `request_id`, `lease_id`, `renewable`, `lease_duration`, `warnings`, `auth` và metadata phong phú hơn. Không cần chép tất cả vào fixture nếu trường đó không liên quan tới hành vi đang kiểm thử. Tuy nhiên, khi kiểm thử **phiên bản secret** hay vòng đời lease, phải thêm chính các trường metadata/lease mà code dùng và kiểm tra giá trị của chúng.

> **Lưu ý KV v1/KV v2:** KV v1 thường trả dữ liệu tại `data` và dùng đường dẫn `/v1/<mount>/<path>`; KV v2 có đường dẫn `/data/` và dữ liệu lồng tại `data.data`. Chọn sai backend hoặc bỏ bớt tầng lồng có thể làm bài test giả pass nhưng ứng dụng thật đọc sai.

## 3. Tách ánh xạ dữ liệu khỏi việc gọi Vault

Ví dụ sau yêu cầu Java 17+ và thư viện Jackson có hỗ trợ `record`, như trong nhiều dự án Spring hiện đại. `VaultKeyValueOperations` được truyền vào service để có thể thay bằng mock khi kiểm thử; lúc chạy thật, bean được tạo từ `vaultTemplate.opsForKeyValue("secret", KeyValueBackend.KV_2)`.

```java
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.support.VaultResponseSupport;

record DatabaseSettings(String username, String password) {}

final class DatabaseSettingsService {
    private final VaultKeyValueOperations kv;

    DatabaseSettingsService(VaultKeyValueOperations kv) {
        this.kv = kv;
    }

    DatabaseSettings read(String key) {
        VaultResponseSupport<DatabaseSettings> response =
                kv.get(key, DatabaseSettings.class);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Required Vault secret was not found");
        }

        DatabaseSettings settings = response.getData();
        if (settings.username() == null || settings.username().isBlank()
                || settings.password() == null || settings.password().isBlank()) {
            throw new IllegalArgumentException("Vault secret is missing required fields");
        }

        return settings;
    }
}
```

```java
// Wiring tại ranh giới hạ tầng của ứng dụng:
VaultKeyValueOperations kv =
        vaultTemplate.opsForKeyValue("secret", KeyValueBackend.KV_2);
DatabaseSettingsService service = new DatabaseSettingsService(kv);
DatabaseSettings settings = service.read("payments");
```

`KeyValueBackend` là enum lồng trong `VaultKeyValueOperationsSupport` (`org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend`). Service chủ động từ chối secret thiếu dữ liệu; quy tắc trên phải được điều chỉnh nếu ứng dụng của bạn thực sự cho phép mật khẩu rỗng hoặc có giá trị mặc định. Trong sản phẩm thực tế, tránh đưa `password`, raw response hay giá trị token vào exception hoặc log.

## 4. Unit test với dữ liệu giả: kiểm tra logic ánh xạ

Với JUnit 5 và Mockito, không cần khởi động HTTP server hay Vault. Mock đối tượng phản hồi để kiểm tra chính xác phần service xử lý sau khi Spring Vault đã ánh xạ dữ liệu.

```java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.support.VaultResponseSupport;

class DatabaseSettingsServiceTest {

    @Test
    @SuppressWarnings("unchecked")
    void returnsMappedValuesWhenSecretIsValid() {
        VaultKeyValueOperations kv = mock(VaultKeyValueOperations.class);
        VaultResponseSupport<DatabaseSettings> response =
                mock(VaultResponseSupport.class);
        when(response.getData())
                .thenReturn(new DatabaseSettings("demo_reader", "fake-password-only"));
        when(kv.get("payments", DatabaseSettings.class)).thenReturn(response);

        DatabaseSettings actual = new DatabaseSettingsService(kv).read("payments");

        assertEquals("demo_reader", actual.username());
        assertEquals("fake-password-only", actual.password());
        verify(kv).get("payments", DatabaseSettings.class);
    }

    @Test
    void rejectsMissingSecret() {
        VaultKeyValueOperations kv = mock(VaultKeyValueOperations.class);
        when(kv.get("missing", DatabaseSettings.class)).thenReturn(null);

        assertThrows(IllegalStateException.class,
                () -> new DatabaseSettingsService(kv).read("missing"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void rejectsResponseWithoutPassword() {
        VaultKeyValueOperations kv = mock(VaultKeyValueOperations.class);
        VaultResponseSupport<DatabaseSettings> response =
                mock(VaultResponseSupport.class);
        when(response.getData()).thenReturn(new DatabaseSettings("demo_reader", null));
        when(kv.get("payments", DatabaseSettings.class)).thenReturn(response);

        assertThrows(IllegalArgumentException.class,
                () -> new DatabaseSettingsService(kv).read("payments"));
    }
}
```

Nếu dùng cơ chế lỗi riêng (`SecretNotFoundException`, `InvalidSecretException`), thay các kiểu exception trong ví dụ bằng kiểu của dự án. Khi ứng dụng cần phân biệt **404 thiếu secret** với **403 bị cấm**, kiểm thử thêm một case mock ném exception từ Vault; service không nên chuyển lỗi phân quyền thành `null` hoặc giá trị mặc định.

Điểm cần nhớ: Mockito ở đây tạo sẵn `VaultResponseSupport<DatabaseSettings>`, vì vậy **chưa kiểm tra** việc giải mã JSON `data.data`. Đó là lý do cần cấp độ HTTP tiếp theo.

## 5. Dùng phản hồi HTTP tối thiểu để kiểm tra `VaultTemplate` thật

Đặt WireMock vào cổng ngẫu nhiên, dùng token thử nghiệm giả và cho `VaultTemplate` gửi request HTTP tới localhost. Kiểu test này kiểm tra cả đường dẫn REST và cách Spring Vault ánh xạ envelope KV v2 thành `DatabaseSettings`.

Ví dụ minh họa với JUnit 5, WireMock JUnit Jupiter và Spring Vault (các import thông thường được rút gọn):

```java
import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.junit.jupiter.api.Assertions.*;

import com.github.tomakehurst.wiremock.junit5.WireMockExtension;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;

class VaultKvMappingHttpTest {
    @RegisterExtension
    static WireMockExtension mockVault = WireMockExtension.newInstance()
            .options(wireMockConfig().dynamicPort())
            .build();

    @Test
    void mapsMinimalKvV2ResponseToRecord() {
        mockVault.stubFor(get(urlEqualTo("/v1/secret/data/payments"))
                .withHeader("X-Vault-Token", equalTo("test-token"))
                .willReturn(okJson("""
                    {
                      "data": {
                        "data": {
                          "username": "demo_reader",
                          "password": "fake-password-only"
                        },
                        "metadata": {"version": 1}
                      }
                    }
                    """)));

        VaultEndpoint endpoint = VaultEndpoint.create("localhost", mockVault.getPort());
        endpoint.setScheme("http");
        VaultTemplate template =
                new VaultTemplate(endpoint, new TokenAuthentication("test-token"));
        VaultKeyValueOperations kv = template.opsForKeyValue("secret", KeyValueBackend.KV_2);

        DatabaseSettings settings = new DatabaseSettingsService(kv).read("payments");

        assertEquals("demo_reader", settings.username());
        assertEquals("fake-password-only", settings.password());
        mockVault.verify(1, getRequestedFor(urlEqualTo("/v1/secret/data/payments")));
    }
}
```

Khi kết hợp với Spring Boot, có thể thay bước tự tạo `VaultTemplate` bằng cấu hình test trỏ endpoint về WireMock. **Không dùng token thật trong fixture**: `test-token` chỉ là chuỗi giả để kiểm tra ứng dụng có đặt header như dự kiến. Bài test cũng không chứng minh Vault đã xác thực token, vì WireMock không thực hiện authentication hoặc kiểm tra ACL.

Nên bổ sung các HTTP fixture ngắn gọn sau, mỗi fixture ứng với một câu hỏi:

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"errors": []}
```

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"errors": ["permission denied"]}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"data":{"data":{"username":"demo_reader"},"metadata":{"version":2}}}
```

Với `404`, kiểm tra hành vi thiếu secret tại tầng gọi phù hợp phiên bản Spring Vault đang dùng; với `403`, kiểm tra lỗi truy cập được truyền ra rõ ràng; với `200` thiếu `password`, kiểm tra validation của service. Đừng viết bài test gán cùng một kết quả rỗng cho cả ba tình huống.

## 6. Tối thiểu hóa fixture nhưng giữ đúng ngữ nghĩa

Một JSON giả tốt giữ lại **mọi trường quyết định kết quả của case** và bỏ các trường không liên quan. Ví dụ:

| Trường hợp | Phản hồi tối thiểu cần có | Điều cần xác minh |
| --- | --- | --- |
| KV v2 đọc thành công | `data.data.username`, `data.data.password` | DTO được ánh xạ đúng; không lấy nhầm `data.metadata` |
| KV v2 có version | `data.metadata.version` | Code sử dụng đúng thông tin phiên bản, không nhầm với giá trị secret |
| Secret thiếu trường | `data.data` chỉ có `username` | Validation từ chối nếu `password` bắt buộc |
| Secret không tồn tại | HTTP `404` với lỗi JSON hợp lệ | Có hành vi missing-secret rõ ràng |
| Policy từ chối | HTTP `403` với `errors` | Không xử lý như dữ liệu hợp lệ hoặc bỏ qua phân quyền |
| Vault lỗi tạm thời | HTTP `500`/`503` | Có xử lý lỗi, retry có kiểm soát tại tầng thích hợp |
| Dynamic credential | `data.username`, `data.password` cùng các trường lease ở cấp ngoài | Không nhầm TTL/lease ID với secret; có quản lý vòng đời |
| Transit mã hóa | `data.ciphertext` | Trả ciphertext đúng định dạng, không coi là plaintext |

Ví dụ **dynamic secret** từ engine database có dạng khác KV v2:

```json
{
  "lease_id": "database/creds/report-readonly/example-lease",
  "lease_duration": 3600,
  "renewable": true,
  "data": {
    "username": "generated_demo_user",
    "password": "fake-dynamic-password"
  }
}
```

Tại đây, dữ liệu nằm trong `data` (không có `data.data` của KV v2), còn `lease_id`, `lease_duration` và `renewable` nằm ngoài payload. Nếu ứng dụng giữ credential lâu hơn lease, một bài test ánh xạ đúng username/password vẫn chưa đủ: cần bài integration test hoặc kiểm thử vòng đời để kiểm tra làm mới, thu hồi và xử lý hết hạn lease.

Ví dụ **Transit encrypt** tối thiểu:

```json
{
  "data": {
    "ciphertext": "vault:v1:FAKE_CIPHERTEXT_FOR_TEST"
  }
}
```

Transit decrypt thường trả `data.plaintext` dưới dạng **Base64**, không phải chuỗi UTF-8 đã giải mã. Kiểm tra rõ bước Base64 decode nếu lớp ứng dụng trả dữ liệu gốc. PKI issuance có các trường như `data.certificate`, `data.private_key`, `data.ca_chain` và thông tin serial/lease tùy endpoint; chỉ đưa đúng trường mà ứng dụng thực sự ánh xạ, đồng thời kiểm tra không ghi private key vào log. Các engine này có hợp đồng JSON riêng: không lấy fixture KV v2 áp đặt cho mọi endpoint.

## 7. Ma trận ca kiểm thử cần có

| Nhóm | Đầu vào giả / đáp ứng Vault | Kỳ vọng |
| --- | --- | --- |
| Happy path | Secret chứa đủ trường, đúng kiểu | Đối tượng Java khớp từng trường |
| Lồng JSON | `data.data` đúng, `data.metadata.version` riêng | Không nhầm tầng dữ liệu và metadata |
| Missing | `null`, `404`, hoặc `data` không tồn tại | Phân loại thiếu secret theo contract service |
| Partial data | Thiếu `password`, chuỗi rỗng, giá trị `null` | Từ chối nếu trường bắt buộc |
| Kiểu sai | Số/boolean nơi cần chuỗi, ngày không hợp lệ | Validation hoặc mapper xử lý có chủ đích; không âm thầm chấp nhận dữ liệu sai |
| Tương thích mở rộng | Có trường JSON mới không dùng đến | Hành vi được quyết định rõ bởi cấu hình Jackson/DTO |
| Authentication/ACL | `401` hoặc `403` | Lỗi xác thực/phân quyền không bị che thành dữ liệu rỗng |
| Lỗi dịch vụ | `500`, `503`, timeout | Lỗi truyền ra hoặc retry đúng chính sách, không log secret |
| Version/lease | Thay `version`, `lease_duration`, `renewable` | Phần code phụ thuộc metadata nhận đúng giá trị |
| Bảo mật | Chuỗi mật khẩu giả làm giá trị sentinel | Nội dung secret/token không xuất hiện trong log hay lỗi trả cho client |

Một số kiểm tra đáng đưa vào test độc lập:

1. **Không dựa vào thứ tự field JSON.** Sắp xếp lại `username`, `password` và metadata nhưng kết quả phải giữ nguyên.
2. **Phân biệt thiếu với rỗng.** `"password": null`, thiếu key và `"password": ""` có thể cần ba thông báo nghiệp vụ khác nhau, tùy yêu cầu.
3. **Kiểm tra thêm field.** Nếu DTO yêu cầu chống thay đổi schema, cấu hình Jackson theo cách kiểm soát unknown field; nếu muốn tương thích tiến hóa schema, chỉ bỏ qua trường không được dùng và giữ validation cho trường bắt buộc.
4. **Không tự kiểm thử Vault policy bằng mock.** Muốn chứng minh role/token chỉ đọc được đường dẫn cho phép, cần môi trường Vault có policy tương ứng và kiểm tra cả truy cập được phép lẫn bị từ chối.

## 8. Kinh nghiệm tổ chức dữ liệu giả

Nên đặt fixture theo **hành vi**, chẳng hạn `kv2-success.json`, `kv2-missing-password.json`, `kv2-403.json`, `dynamic-lease.json`, thay vì một file JSON rất lớn dùng chung mọi test. Tên và nội dung fixture cần đủ rõ để khi test lỗi, người đọc biết ngay contract nào đã thay đổi.

Nếu dùng file `.json` riêng, lưu ý rằng một fixture `200` cho KV v2 chỉ nên chứa response body, còn mã HTTP và headers cần nằm trong cấu hình server giả. Dùng các chuỗi dễ nhận ra như `fake-password-only` và `test-token`; không trích nguyên phản hồi production vì có thể chứa token, ciphertext nhạy cảm, private key hoặc lease ID có thể sử dụng được. Với lỗi hệ thống, mock độ trễ hoặc timeout ở lớp HTTP thay vì lạm dụng JSON không hợp lệ để đại diện cho mọi loại lỗi.

Các bài test nên chạy độc lập và xác định rõ phiên bản Spring Vault, Jackson, WireMock/JUnit sử dụng. Nếu dùng mock HTTP với `VaultTemplate` thật, hãy so sánh path chính xác và khi cần cả `X-Vault-Token`, `X-Vault-Namespace` (nếu triển khai Vault Enterprise namespace), HTTP method và request body. Không gán giá trị Vault namespace vào đường dẫn nếu cấu hình thực tế sử dụng header.

Khi có thể chạy Vault test instance, thêm ít nhất một integration test tạo KV v2, ghi secret, đọc lại qua Spring Vault rồi xóa/revoke tài nguyên test. Dùng role, namespace và policy dành riêng cho test để xác minh đúng phạm vi quyền. Thử lease renewal/revocation hoặc PKI certificate issuance chỉ khi ứng dụng thực sự dùng các chức năng đó.

## 9. Bài thực hành

**Yêu cầu:** mở rộng `DatabaseSettingsService` để hỗ trợ thêm thuộc tính tùy chọn `host` với mặc định do ứng dụng định nghĩa, nhưng vẫn buộc có `username` và `password`.

- Viết unit test có đủ ba tình huống: đủ trường, thiếu `host`, thiếu `password`.
- Tạo fixture HTTP KV v2 `200 OK` có `data.data` và `data.metadata.version`; xác nhận lớp dùng `VaultTemplate` ánh xạ được DTO.
- Tạo hai phản hồi `404` và `403`; chứng minh service phân biệt secret không tồn tại với request bị từ chối.
- Thêm một thuộc tính JSON không được DTO sử dụng; quyết định và ghi rõ chính sách xử lý unknown field.
- Kiểm tra test report và log không chứa `fake-password-only` hoặc token, trừ các assertion test chuyên biệt nằm trong mã test.

**Tiêu chí hoàn thành:** mỗi phép thử xác nhận một hành vi cụ thể, fixture nhỏ nhưng giữ đúng envelope của endpoint, không có kết nối mạng tới Vault production, và kết quả khác nhau rõ ràng giữa ánh xạ thành công, dữ liệu không hợp lệ, không tìm thấy secret và không đủ quyền truy cập.
