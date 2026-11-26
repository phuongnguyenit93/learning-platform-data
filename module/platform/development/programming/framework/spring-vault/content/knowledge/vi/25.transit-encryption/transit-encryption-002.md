# VaultTransitOperations và mount path tương ứng

## 1. Mục tiêu và bối cảnh

Trong Spring Vault, `VaultTransitOperations` là giao diện Java dành cho các thao tác mật mã của **Transit secrets engine** trong HashiCorp Vault. Ứng dụng gửi dữ liệu cần mã hóa/giải mã đến Vault thông qua `VaultTemplate` hoặc giao diện chung `VaultOperations`; Vault thực hiện phép toán bằng khóa do Vault quản lý và trả kết quả về ứng dụng. Khóa mã hóa không cần rời khỏi Vault.

Bài này tập trung vào một quyết định cấu hình dễ gây lỗi: **một `VaultTransitOperations` luôn gắn với một mount path cụ thể**. Mount path quyết định instance Transit nào nhận yêu cầu. Tên khóa lại xác định khóa *bên trong* instance đó. Hai giá trị không thay thế cho nhau.

Sau bài học, bạn có thể:

- Phân biệt **engine type**, **mount path**, **key name**, đường dẫn HTTP API và Vault Namespace.
- Chọn đúng `vaultOperations.opsForTransit()` hoặc `vaultOperations.opsForTransit(path)`.
- Kết nối ứng dụng Spring đến Transit mount tùy chỉnh, mã hóa/giải mã chuỗi UTF-8 và lưu ciphertext.
- Viết policy giới hạn quyền truy cập đúng mount và đúng khóa.
- Xử lý trường hợp sai mount, thiếu quyền, luân phiên phiên bản khóa và kiểm thử tích hợp.

**Giới hạn trách nhiệm:** Transit xử lý phép toán mật mã, không lưu nội dung nghiệp vụ để ứng dụng truy vấn lại sau này. Ứng dụng vẫn phải lưu ciphertext vào cơ sở dữ liệu hoặc kho riêng; phải bảo vệ đường truyền tới Vault bằng TLS, xác thực workload và quản lý vòng đời token phù hợp. KV secrets engine là dịch vụ lưu secrets, không đồng nghĩa Transit.

## 2. Mô hình: một mount path, nhiều khóa

Giả sử đội vận hành bật Transit ở đường dẫn `payments-transit/`, sau đó tạo khóa `customer-pii` trong engine này:

~~~bash
# Thao tác cấp quyền quản trị, thực hiện một lần trong môi trường cần thiết.
vault secrets enable -path=payments-transit transit
vault write -f payments-transit/keys/customer-pii
vault secrets list
~~~

Lệnh đầu bật **secrets engine type** `transit` tại **mount path** `payments-transit/`. Lệnh thứ hai tạo **key name** `customer-pii` bên trong mount đó. Nếu Transit đã được bật tại mount ấy, không chạy lại lệnh enable.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Engine type | `transit` | Loại secrets engine Vault dùng để thực hiện phép toán mật mã. |
| Mount path | `payments-transit` | Vị trí engine được mount trong Vault; có thể đặt khác `transit`. |
| Key name | `customer-pii` | Khóa logic nằm trong engine tại mount đã chọn. |
| Encrypt endpoint | `payments-transit/encrypt/customer-pii` | API Vault thực thi thao tác mã hóa với khóa tương ứng. |
| Decrypt endpoint | `payments-transit/decrypt/customer-pii` | API Vault giải mã ciphertext bằng khóa tương ứng. |
| HTTP API đầy đủ | `/v1/payments-transit/encrypt/customer-pii` | URL phía Vault server; tiền tố `/v1/` do HTTP API đảm nhiệm. |

Lời gọi Java ↔ endpoint tương ứng:

~~~text
Ứng dụng Spring                        Vault
───────────────────                    ──────────────────────────────────
VaultOperations                        mount: payments-transit/ (transit)
  .opsForTransit("payments-transit")       ├── keys/customer-pii
       │                                   ├── encrypt/customer-pii
       ├── encrypt("customer-pii", ...) ───▶│
       ├── decrypt("customer-pii", ...) ───▶├── decrypt/customer-pii
       └── rewrap("customer-pii", ...) ────▶└── rewrap/customer-pii
~~~

Một Vault server có thể mount nhiều Transit engine, ví dụ `transit/` và `payments-transit/`, mỗi engine có namespace khóa, cấu hình và policy riêng. **Hai khóa cùng tên ở hai mount không phải cùng một khóa mật mã.** Ciphertext tạo với `payments-transit/customer-pii` không thể tự động giải mã nhờ khóa tên `customer-pii` của mount `transit/`.

### 2.1. Hai cách lấy VaultTransitOperations

`VaultOperations` và `VaultTemplate` hỗ trợ hai overload:

~~~java
// Mount mặc định: transit/
VaultTransitOperations defaultTransit = vaultOperations.opsForTransit();

// Mount tùy chỉnh: payments-transit/
VaultTransitOperations paymentTransit =
        vaultOperations.opsForTransit("payments-transit");
~~~

- `opsForTransit()` tương đương lựa chọn mount mặc định `transit`.
- `opsForTransit("payments-transit")` hướng tất cả thao tác của object này đến mount `payments-transit`.
- Đối số `path` chỉ là **mount path**: không phải key name, đường dẫn `/v1/...`, hoặc endpoint `.../encrypt/...`.
- Key name được truyền vào từng lời gọi như `encrypt("customer-pii", ...)`, `decrypt("customer-pii", ...)`.

Ví dụ **sai**:

~~~java
vaultOperations.opsForTransit("payments-transit/keys/customer-pii"); // Sai: path quá sâu
vaultOperations.opsForTransit("v1/payments-transit");                  // Sai: gồm tiền tố API
vaultOperations.opsForTransit("customer-pii");                         // Sai: dùng tên khóa làm mount
~~~

Chọn giá trị mount thống nhất với kết quả `vault secrets list` và lưu giá trị đó trong cấu hình của môi trường triển khai. Khi tổ chức dùng **Vault Enterprise Namespace**, namespace là phạm vi truy cập Vault riêng, do cấu hình kết nối/header namespace quản lý; không ghép namespace một cách tùy tiện vào tham số mount path.

## 3. Luồng mã hóa và giải mã trong Spring

Ví dụ giả định Spring đã khởi tạo bean `VaultOperations` với địa chỉ Vault và cơ chế xác thực workload đang dùng (chẳng hạn Kubernetes auth hoặc AppRole). Đây là trách nhiệm cấu hình kết nối của Spring Vault/Spring Cloud Vault; lựa chọn mount Transit là bước tiếp theo.

Cấu hình ứng dụng:

~~~yaml
app:
  transit:
    mount: payments-transit
    key: customer-pii
~~~

Service sau sử dụng mount và key đọc từ cấu hình. `Plaintext` và `Ciphertext` là value object của Spring Vault; dùng `StandardCharsets.UTF_8` để không phụ thuộc charset mặc định của máy chạy Java.

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTransitOperations;
import org.springframework.vault.support.Ciphertext;
import org.springframework.vault.support.Plaintext;

@Service
public class CustomerPiiCryptoService {

    private final VaultTransitOperations transit;
    private final String keyName;

    public CustomerPiiCryptoService(
            VaultOperations vaultOperations,
            @Value("${app.transit.mount}") String mountPath,
            @Value("${app.transit.key}") String keyName) {

        this.transit = vaultOperations.opsForTransit(mountPath);
        this.keyName = keyName;
    }

    /** Trả về ciphertext để ứng dụng lưu vào database. */
    public String encrypt(String input) {
        Plaintext inputBytes = Plaintext.of(input, StandardCharsets.UTF_8);
        Ciphertext encrypted = transit.encrypt(keyName, inputBytes);
        return encrypted.getCiphertext();
    }

    /** Chỉ giải mã khi nghiệp vụ thực sự được phép đọc dữ liệu rõ. */
    public String decrypt(String storedCiphertext) {
        Ciphertext encrypted = Ciphertext.of(storedCiphertext);
        Plaintext decrypted = transit.decrypt(keyName, encrypted);
        return decrypted.asString(StandardCharsets.UTF_8);
    }
}
~~~

Sử dụng minh họa:

~~~java
String ciphertext = cryptoService.encrypt("Khách hàng Nguyễn Văn A");
repository.saveCiphertext(ciphertext);  // Kho ứng dụng giữ ciphertext.

String restored = cryptoService.decrypt(repository.loadCiphertext());
~~~

Giá trị `ciphertext` thường có tiền tố dạng `vault:v1:...`, trong đó `v1` là phiên bản khóa; phần còn lại là dữ liệu đã mã hóa. **Đừng cắt bỏ tiền tố này**, vì Vault cần thông tin phiên bản khóa để giải mã dữ liệu cũ sau khi luân phiên khóa. Không ghi plaintext, ciphertext nhạy cảm hoặc token Vault vào log, exception message, trace hay metric label.

Với dữ liệu văn bản đơn giản, Spring Vault còn có overload thuận tiện:

~~~java
String encrypted = transit.encrypt("customer-pii", "hello");
String decrypted = transit.decrypt("customer-pii", encrypted);
~~~

Hai overload chuỗi này dùng **charset mặc định** để chuyển đổi byte, nên với dữ liệu cần tính nhất quán giữa các máy và môi trường, nên chọn cặp `Plaintext.of(value, UTF_8)` / `asString(UTF_8)` ở ví dụ service. Với file, ảnh, dữ liệu nén hoặc payload nhị phân, sử dụng `Plaintext.of(byte[])` và đọc `getPlaintext()` của kết quả giải mã để giữ nguyên byte.

### 3.1. Ai chịu trách nhiệm tạo key?

`VaultTransitOperations` có những phương thức như `createKey`, `getKey`, `rotate`, `rewrap` và `deleteKey`, nhưng sự tồn tại của API Java **không có nghĩa** ứng dụng runtime nên được cấp quyền quản trị khóa. Mô hình thường dùng:

1. Nhóm vận hành/IaC tạo Transit mount, tạo key, đặt chính sách khóa và cấu hình quyền cho workload.
2. Ứng dụng runtime lấy `VaultTransitOperations` từ mount đã cấu hình, chỉ gọi endpoint được policy cho phép.
3. Khi cần luân phiên khóa, quản trị viên hoặc job vận hành có quyền riêng thực hiện rotation; ứng dụng tiếp tục giải mã ciphertext cũ khi phiên bản cũ còn được cho phép.

Một số cấu hình Vault có thể tự tạo khóa trong lời gọi encrypt khi token được cấp capability `create`. Để kiểm soát vòng đời khóa, cấp cho ứng dụng quyền `update` trên endpoint encrypt của khóa **đã được tạo trước**, và không cấp `create` nếu không cần.

## 4. Policy gắn với mount và key

Quyền của Vault được kiểm tra trên **đường dẫn thực tế**. Nếu ứng dụng dùng `opsForTransit("payments-transit")` thì policy chứa `transit/encrypt/customer-pii` sẽ không khớp. Ví dụ policy chỉ cho phép mã hóa và giải mã một khóa:

~~~hcl
# policy: customer-pii-runtime.hcl
path "payments-transit/encrypt/customer-pii" {
  capabilities = ["update"]
}

path "payments-transit/decrypt/customer-pii" {
  capabilities = ["update"]
}
~~~

Endpoint encrypt/decrypt dùng phương thức HTTP POST, do đó capability thường dùng là `update`. Quyền `read` trên `payments-transit/keys/customer-pii` không bắt buộc cho hai thao tác trên. Nếu workload chỉ được phép ghi dữ liệu đã mã hóa, bỏ rule decrypt để giảm phạm vi lộ dữ liệu rõ.

Chỉ thêm quyền cần thiết khi có nghiệp vụ tương ứng:

| Nhu cầu | Path trong policy | Capability thường dùng |
| --- | --- | --- |
| Mã hóa | `payments-transit/encrypt/customer-pii` | `update` |
| Giải mã | `payments-transit/decrypt/customer-pii` | `update` |
| Rewrap ciphertext | `payments-transit/rewrap/customer-pii` | `update` |
| Xem metadata khóa | `payments-transit/keys/customer-pii` | `read` |
| Rotate key | `payments-transit/keys/customer-pii/rotate` | `update`, dành cho vai trò vận hành |
| Tạo/xóa/cấu hình/export key | Các endpoint quản trị thuộc `payments-transit/keys/...` | Chỉ cấp theo tác vụ quản trị riêng |

Quyền giải mã là quyền nhạy cảm: người sở hữu token với `update` trên endpoint decrypt có thể yêu cầu Vault trả plaintext. Không đưa quyền này cho mọi dịch vụ chỉ vì các dịch vụ cùng dùng một mount. Dùng một key hoặc nhiều key riêng theo ranh giới dữ liệu và trách nhiệm truy cập; giới hạn đúng key cụ thể thay vì wildcard toàn mount.

Token Vault phải được cấp từ phương thức xác thực dành cho workload, có TTL/renewal phù hợp và được rút quyền khi workload ngừng hoạt động. Mọi policy trên chỉ phát huy tác dụng nếu ứng dụng thực sự gửi request bằng identity/token có policy tương ứng.

## 5. Khi có nhiều Transit mount

Một dịch vụ có thể cần dùng nhiều miền bảo mật. Chẳng hạn:

~~~java
VaultTransitOperations paymentTransit =
        vaultOperations.opsForTransit("payments-transit");

VaultTransitOperations auditTransit =
        vaultOperations.opsForTransit("audit-transit");

String paymentCiphertext =
        paymentTransit.encrypt("customer-pii", "payment data");

String auditCiphertext =
        auditTransit.encrypt("audit-record", "audit event");
~~~

Những khác biệt cần giữ rõ:

- `payments-transit` và `audit-transit` là hai **mount paths**; cấu hình/khóa của chúng độc lập.
- `customer-pii` và `audit-record` là hai **key names** theo từng mount.
- Policy phải tham chiếu đúng cặp mount–key; quyền một cặp không tự cấp quyền cho cặp còn lại.
- Không giải mã ciphertext ở mount khác dù vô tình có key trùng tên.
- Nếu thay đổi mount khi triển khai sang môi trường khác, phải xác định cách bảo toàn/migrate key và dữ liệu đã mã hóa. Chỉ thay một chuỗi cấu hình không chuyển dữ liệu khóa giữa các mount.

Nên cấu hình mount qua biến môi trường hoặc hệ thống cấu hình theo deployment, kiểm tra startup để phát hiện tên mount rỗng/sai và quy định rõ ai sở hữu key. Nếu tổ chức muốn tách quyền vận hành, nhiều mount là một công cụ; không phải lúc nào cũng cần mỗi microservice một mount. Tách key và policy trong cùng mount có thể đáp ứng yêu cầu phân quyền đơn giản hơn.

## 6. Luân phiên phiên bản khóa và rewrap

Key trong Transit có thể có nhiều **phiên bản**. `rotate(keyName)` tạo phiên bản khóa mới; các lần encrypt tiếp theo dùng phiên bản mới. Ciphertext cũ thường vẫn giải mã được với phiên bản cũ còn tồn tại và được policy/cấu hình cho phép. `rewrap` nhận ciphertext cũ và trả về ciphertext dùng phiên bản mới, **không trả plaintext cho caller**.

~~~java
VaultTransitOperations adminTransit =
        vaultOperations.opsForTransit("payments-transit");

// Chạy bởi vai trò vận hành có quyền rotate; không phải token runtime mặc định.
adminTransit.rotate("customer-pii");

// Job migration có quyền rewrap, đọc ciphertext từ kho ứng dụng
// và lưu lại kết quả. Không phải gọi decrypt() trong ứng dụng.
String upgradedCiphertext =
        adminTransit.rewrap("customer-pii", oldCiphertext);
~~~

Trình tự vận hành thường là: rotate → tiếp tục encrypt với key version mới → rewrap dữ liệu cũ theo từng đợt khi cần → xác minh đọc được dữ liệu trước khi áp dụng ngưỡng `min_decryption_version`. Rewrap thay giá trị ciphertext nên cần cập nhật cơ sở dữ liệu một cách an toàn, có khả năng chạy lại. Nếu nâng ngưỡng decryption quá sớm, ciphertext chưa rewrap có thể không đọc được.

Với key **derived** hoặc convergent encryption, encrypt/decrypt/rewrap có thể yêu cầu cùng `VaultTransitContext`; `Plaintext` và `Ciphertext` hỗ trợ gắn context. Đây là cấu hình mật mã chuyên biệt, cần thiết kế dữ liệu context nhất quán và thử nghiệm riêng. Không tự bật convergent encryption chỉ để tạo ciphertext ổn định, vì việc để lộ quan hệ bằng nhau giữa các bản rõ có thể ảnh hưởng tính riêng tư.

## 7. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Cách xác minh và xử lý |
| --- | --- | --- |
| HTTP 404 / endpoint không tồn tại | Chọn nhầm mount, engine chưa enable hoặc đường dẫn API sai. | So sánh `opsForTransit(path)` với `vault secrets list`; xác nhận engine type là Transit. |
| HTTP 403 / permission denied | Token không có policy trên đúng `mount/operation/key` hoặc không thuộc namespace/identity mong đợi. | Kiểm tra quyền của workload đối với path thật sự, nhất là `encrypt/...` và `decrypt/...`; kiểm tra token/role. |
| Không tìm thấy key, thao tác encrypt thất bại | Key chưa tạo, gọi sai key name, hoặc policy chỉ có `update` và không cho upsert. | Tạo khóa bằng vai trò vận hành; xác nhận chính xác tên key và mount. |
| Decrypt thất bại với ciphertext hợp lệ ở nơi khác | Ciphertext thuộc key/mount khác, context khác, hoặc phiên bản khóa không còn được phép giải mã. | Đối chiếu nguồn ciphertext, cặp mount–key, context, phiên bản và cấu hình `min_decryption_version`. |
| Chuỗi tiếng Việt bị lỗi mã hóa ký tự | Trộn charset khác nhau giữa lúc tạo và lúc đọc plaintext. | Dùng `Plaintext.of(input, UTF_8)` và `asString(UTF_8)`. |
| Lỗi timeout / 5xx / token hết hạn | Vault hoặc mạng gặp sự cố; lifecycle của Vault session/token chưa phù hợp. | Kiểm tra kết nối TLS, xác thực, renew token, audit log và metric Vault; retry có giới hạn khi phù hợp. |

Phân biệt 403 và 404 bằng log server và tình trạng cấu hình, vì chính sách, namespace và cách Vault xử lý quyền có thể ảnh hưởng phản hồi quan sát được. Không giả định mọi 404 chắc chắn là key không tồn tại.

**Nguyên tắc vận hành:** Chỉ ghi log tên thao tác, mount/key đã cho phép quan sát, mã lỗi, thời gian phản hồi, correlation ID và kết quả kiểm tra; không ghi plaintext, ciphertext toàn bộ hay Vault token. Chỉ retry khi lỗi có tính tạm thời, đặt timeout và circuit breaker hợp lý, tránh retry vô hạn ở đường đọc dữ liệu nhạy cảm.

## 8. Kịch bản thực hành và kiểm tra tích hợp

Thực hiện trên Vault development/test riêng có cấu hình và quyền phù hợp:

1. Bật Transit tại `payments-transit`, tạo key `customer-pii` bằng CLI quản trị; kiểm tra `vault secrets list` có mount ấy.
2. Gắn policy `update` cho encrypt/decrypt của key này vào identity của ứng dụng test.
3. Cấu hình `app.transit.mount=payments-transit`, `app.transit.key=customer-pii`, kết nối Spring Vault qua cơ chế auth của workload.
4. Gọi `encrypt("Khách hàng Nguyễn Văn A")`, lưu ciphertext; xác minh ciphertext khác plaintext và thường có tiền tố `vault:v...`.
5. Gọi `decrypt(ciphertext)`, so sánh chính xác với chuỗi gốc (gồm dấu tiếng Việt); gọi lại với bản ghi đã lưu để kiểm tra serialization.
6. Thử bỏ quyền decrypt khỏi policy bằng một identity test khác: encrypt vẫn hoạt động, decrypt bị từ chối. Thử cấu hình mount sai trên identity test: xác minh ứng dụng báo lỗi có kiểm soát và không tiết lộ dữ liệu.
7. Với một vai trò quản trị test riêng, rotate key rồi encrypt dữ liệu mới; xác nhận cả ciphertext cũ và mới vẫn giải mã được khi cấu hình cho phép. Kiểm tra rewrap có thể đổi phiên bản ciphertext mà không trả plaintext cho caller.
8. Kiểm tra log/metrics không lộ plaintext, token hay ciphertext đầy đủ; kiểm tra xử lý sự cố Vault không khả dụng.

Phần assertions cốt lõi:

~~~java
String original = "Mã hóa tiếng Việt: Đặng, Nguyễn, Trần";
String encrypted = cryptoService.encrypt(original);

assertNotEquals(original, encrypted);
assertTrue(encrypted.startsWith("vault:"));
assertEquals(original, cryptoService.decrypt(encrypted));
~~~

Đây là **integration test** khi `cryptoService` gọi đến Vault thật trong môi trường test; mock `VaultTransitOperations` chỉ xác minh code gọi đúng method, không chứng minh cấu hình mount, policy, thuật toán hay vòng đời khóa hoạt động. Nếu tự động hóa, cô lập dữ liệu test, tạo/dọn key test theo quyền quản trị của fixture và không dùng token production.

## 9. Ghi nhớ và câu hỏi tự đánh giá

- `opsForTransit()` dùng engine tại `transit`; `opsForTransit("payments-transit")` dùng engine tại `payments-transit`.
- Mount path định vị engine; key name định vị khóa **trong** engine; `/v1` và `encrypt`/`decrypt` là thành phần endpoint HTTP, không phải mount path.
- Ciphertext phải đi kèm đúng mount, key và context (nếu được dùng); phiên bản khóa trong ciphertext hỗ trợ luân phiên khóa.
- Policy vận hành phải bám đúng đường dẫn `mount/operation/key` và cấp quyền tối thiểu cho từng workload.
- Ứng dụng lưu ciphertext, Vault giữ khóa; tách vai trò runtime với vai trò quản trị key.

Tự trả lời trước khi chuyển bài:

1. Nếu CLI mount Transit tại `finance-crypto/`, code Spring cần gọi phương thức nào và tên khóa được truyền ở đâu?
2. Vì sao đổi `opsForTransit("finance-crypto")` sang `opsForTransit()` có thể làm giải mã dữ liệu cũ thất bại dù key name không đổi?
3. Một workload chỉ được mã hóa có cần capability `update` ở `decrypt/...` hay `keys/.../rotate` không?
4. Luân phiên key version khác gì với thay mount path? Khi nào cần `rewrap`?
5. Cần kiểm tra gì trong integration test để phát hiện lỗi policy và lỗi charset, ngoài việc mock lời gọi API?

## Tài liệu tham khảo

- [Spring Vault — Vault secrets engines và ví dụ Transit](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Vault — VaultOperations API, hai overload opsForTransit](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html)
- [Spring Vault — VaultTransitOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTransitOperations.html)
- [HashiCorp Vault — Transit secrets engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
- [HashiCorp Vault — Transit HTTP API và endpoint permissions](https://developer.hashicorp.com/vault/api-docs/secret/transit)
