# Context, khóa dẫn xuất và yêu cầu khi sử dụng

## 1. Vì sao Transit cần context?

Trong **Spring Vault**, ứng dụng Java thường gọi HashiCorp Vault qua `VaultTemplate` / `VaultOperations` để mã hóa dữ liệu bằng **Transit secrets engine**. Vault giữ và quản lý khóa; ứng dụng gửi plaintext khi mã hóa, nhận ciphertext để lưu trong cơ sở dữ liệu rồi gửi lại ciphertext khi cần giải mã. Transit không lưu hộ dữ liệu nghiệp vụ.

Hãy xét một dịch vụ quản lý thông tin khách hàng của nhiều tenant. Có hai cách phổ biến để tổ chức khóa:

- **Mỗi tenant một named key**: `tenant-a-pii`, `tenant-b-pii`, ... Cách này phân tách rõ về quản trị nhưng có thể tạo rất nhiều khóa cần quản lý.
- **Một named key có dẫn xuất khóa**: `customer-pii` được tạo với `derived=true`. Mỗi lần mã hóa, ứng dụng gửi một `context` xác định tenant hoặc mục đích sử dụng. Vault dùng context để dẫn xuất khóa phù hợp từ khóa gốc đã quản lý.

Bài này giải thích chính xác context được dùng như thế nào, cách thiết kế và lưu nó, các điều kiện ở thời điểm tạo khóa, cách gọi từ Spring Vault và những giới hạn bảo mật phải hiểu trước khi áp dụng.

> **Kết quả cần đạt:** Có thể tạo một Transit key hỗ trợ dẫn xuất, mã hóa/giải mã đúng context qua CLI và Java, giải thích được vì sao sai context không giải mã được, đồng thời thiết kế được dữ liệu lưu trữ và chính sách Vault phù hợp.

## 2. Context và khóa dẫn xuất hoạt động ra sao?

### 2.1. Context là dữ liệu đầu vào cho quá trình dẫn xuất khóa

Trong Transit, `context` là một chuỗi **byte** do client cung cấp. Khi named key được cấu hình `derived=true`, Vault kết hợp khóa gốc (cùng phiên bản khóa) với context trong quá trình dẫn xuất để sử dụng khóa mã hóa tương ứng. Các context khác nhau tạo ra vật liệu khóa dẫn xuất khác nhau, dù cùng tên named key.

Có thể hiểu ở mức khái niệm:

```text
Named key: customer-pii (version 1, derived=true)
                  |
                  +-- context = "app:pii:v1:tenant-A" --> khóa dẫn xuất A
                  |                                   --> Encrypt/Decrypt A
                  |
                  +-- context = "app:pii:v1:tenant-B" --> khóa dẫn xuất B
                                                      --> Encrypt/Decrypt B
```

Sơ đồ thể hiện quan hệ sử dụng, **không phải công thức mật mã** để tự triển khai. Vault thực hiện thuật toán dẫn xuất và mã hóa nội bộ; ứng dụng không nhận khóa gốc hay khóa dẫn xuất.

Với khóa mã hóa đối xứng hỗ trợ xác thực như `aes256-gcm96`:

1. Khi **encrypt**, Vault dẫn xuất khóa từ context, mã hóa plaintext và trả ciphertext, ví dụ dạng `vault:v1:...`.
2. Khi **decrypt**, Vault đọc phiên bản khóa từ ciphertext và phải nhận **đúng context** đã dùng khi encrypt để tái tạo khóa dẫn xuất phù hợp.
3. Nếu context sai, thiếu hoặc bị thay đổi, việc giải mã thất bại (thường là lỗi xác thực bản mã với AEAD). Không có cơ chế tự suy ra context từ ciphertext.

**Context không phải mật khẩu, token Vault, tên khóa hay một cơ chế ủy quyền.** Nó là đầu vào của phép toán mật mã. Một client được Vault ACL cho phép gọi `transit/decrypt/customer-pii` vẫn có thể thử các context khác; vì vậy ứng dụng vẫn phải xác thực và kiểm tra quyền truy cập bản ghi của tenant.

### 2.2. Phân biệt những khái niệm dễ nhầm

| Thành phần | Mục đích | Có cần tái sử dụng khi decrypt? |
| --- | --- | --- |
| **Named key**, ví dụ `customer-pii` | Định danh khóa và keyring do Vault quản lý | Có, phải dùng đúng named key |
| **`context`** | Đầu vào dẫn xuất khóa khi `derived=true` | Có, phải khớp **chính xác từng byte** |
| **`plaintext`** | Dữ liệu thực tế cần mã hóa | Chỉ cần ở lần encrypt |
| **`ciphertext`** | Kết quả mã hóa được ứng dụng lưu trữ | Có, gửi lại khi decrypt/rewrap |
| **Phiên bản khóa** `vault:vN:...` | Xác định phiên bản trong keyring để Vault giải mã | Đã được thể hiện trong ciphertext |
| **Nonce/IV** | Tham số của chế độ mã hóa, không phải context | Thông thường Vault tự xử lý; ngoại lệ với khóa convergent đời cũ |
| **AAD / `associated_data`** | Dữ liệu liên kết được xác thực trong chế độ AEAD hỗ trợ AAD | Nếu dùng AAD thì phải cung cấp đúng AAD theo yêu cầu API; không thay thế context |
| **Vault token và ACL** | Xác thực workload và phân quyền endpoint | Có, yêu cầu có quyền phù hợp tại thời điểm gọi |

Trong HTTP API của Vault, cả `plaintext` lẫn `context` được biểu diễn bằng **Base64** vì chúng có thể chứa byte bất kỳ. Base64 chỉ là cách chuyên chở byte qua JSON, **không phải mã hóa bảo mật**.

### 2.3. Context không nằm trong ciphertext

Ciphertext Transit chứa thông tin để Vault xác định phiên bản khóa, nhưng **không tự mang context nghiệp vụ**. Nếu chỉ lưu `vault:v1:...` mà đánh mất cách tạo context, dữ liệu có thể không còn giải mã được dù Vault vẫn giữ khóa.

Vì vậy cần coi *quy tắc sinh context* và *dữ liệu cần thiết để dựng lại context* là một phần của hợp đồng lưu trữ dài hạn, tương tự lựa chọn named key.

## 3. Cấu hình khóa: derived và convergent

Các chế độ thường gặp:

| Cấu hình lúc tạo khóa | Cách hoạt động | Yêu cầu khi encrypt/decrypt | Tính chất khi mã hóa lặp lại |
| --- | --- | --- | --- |
| `derived=false`, `convergent_encryption=false` (mặc định) | Không dùng context để dẫn xuất khóa | Không bắt buộc context | Cùng plaintext thường cho ciphertext khác do nonce ngẫu nhiên |
| `derived=true`, `convergent_encryption=false` | Dẫn xuất khóa theo context | **Bắt buộc context** trong các thao tác mã hóa/giải mã và rewrap | Cùng plaintext và cùng context thường vẫn cho ciphertext khác |
| `derived=true`, `convergent_encryption=true` | Dẫn xuất khóa và dùng mã hóa có tính xác định | Bắt buộc context; yêu cầu nonce phụ thuộc phiên bản convergent key | Cùng plaintext, context và phiên bản khóa cho cùng ciphertext |

Các điểm cần quyết định **trước khi tạo named key**:

- `derived` mặc định là `false`; muốn dùng context để dẫn xuất thì phải khai báo `derived=true` ngay khi tạo.
- Convergent encryption **yêu cầu** `derived=true`. Không nên bật chỉ để tận dụng context vì nó làm lộ khả năng so sánh các ciphertext bằng nhau.
- Các thuộc tính xác định khi tạo khóa, bao gồm kiểu khóa và chế độ dẫn xuất, không thể tùy ý chuyển đổi trên một named key đã tồn tại. Nếu cần thay đổi chiến lược, thiết kế named key và kế hoạch di chuyển dữ liệu mới.
- `aes256-gcm96` là loại khóa đối xứng mặc định của Transit, có hỗ trợ dẫn xuất. Không phải mọi loại khóa Transit đều hỗ trợ mã hóa hoặc dẫn xuất theo cùng cách; cần kiểm tra loại khóa trước khi áp dụng mẫu này.

**Trường hợp convergent:** Vault hiện đại tự dẫn xuất nonce trong các phiên bản convergent phù hợp; key được tạo từ Vault 0.6.1 dùng cơ chế cũ đòi hỏi client cung cấp nonce 96 bit. Chế độ này có hệ quả bảo mật riêng và cần đánh giá cụ thể trước khi dùng cho dữ liệu có miền giá trị nhỏ như trạng thái, giới tính hoặc mã có thể đoán được. Với dữ liệu cần bảo mật thông thường, ưu tiên **`derived=true`, convergent tắt**.

## 4. Thiết kế context ổn định cho ứng dụng

### 4.1. Chọn context theo ranh giới nghiệp vụ

Context nên mang ý nghĩa rõ, có khả năng tái tạo lâu dài và phân tách mục đích sử dụng. Ví dụ:

```text
app:customer-pii:v1:tenant=tenant-123
app:customer-pii:v1:tenant=tenant-456
app:payment-token:v1:tenant=tenant-123
```

Các thành phần `app`, phạm vi dữ liệu, `v1` và tenant ID đóng vai trò *domain separation* ở cấp ứng dụng. Chúng không phải cú pháp bắt buộc của Vault. Có thể chọn format khác, miễn có quy ước thống nhất và không thay đổi bất ngờ.

| Nguyên tắc | Lý do |
| --- | --- |
| Dùng định danh ổn định, ví dụ immutable tenant ID | Đổi tên hiển thị tenant sẽ không làm mất khả năng giải mã |
| Có tiền tố ứng dụng và mục đích sử dụng | Tránh vô tình dùng chung context cho các miền dữ liệu khác nhau |
| Quy định encoding cố định, thường là UTF-8 | Cùng ký tự biểu diễn khác byte có thể dẫn đến khóa khác |
| Định phiên bản **format context** | Có cách giữ logic dựng context cũ khi nâng cấp ứng dụng |
| Lưu đủ dữ liệu để tái tạo context | Dùng lại được khi decrypt, rewrap, phục hồi và di chuyển dữ liệu |
| Không đưa bí mật, email hay PII vào context khi không cần | Giảm rủi ro lộ định danh qua log, metadata và quy trình vận hành |
| Chuẩn hóa ranh giới của các thành phần | Tránh nhập nhằng do nối chuỗi không có escape/delimiter |

Ví dụ nếu tenant ID được đặt bởi người dùng, phải quy định cách validate, escaping, Unicode normalization và độ dài trước khi ghép; ứng dụng không nên tự thay đổi các quy tắc này theo locale hoặc thư viện mới. Dùng context ngẫu nhiên **vẫn khả thi** nếu lưu đầy đủ byte context bên cạnh ciphertext, nhưng không phù hợp khi mục tiêu là phân tách nhất quán theo tenant và cần dựng lại từ định danh.

**Lưu ý về bảo mật:** Cùng một context không có nghĩa là các tenant được Vault tự động phân quyền tách biệt. Nếu dùng chung một named key và cùng token có quyền encrypt/decrypt cho key đó, Vault ACL chỉ kiểm soát được endpoint/key path, không tự kiểm tra quyền sở hữu tenant ID bên trong context. Phải thực thi tenant authorization ở ứng dụng, hoặc dùng named key/mount/namespace và policy riêng khi yêu cầu cô lập mạnh hơn.

### 4.2. Thiết kế bản ghi lưu trữ

Một bản ghi lưu trong database có thể gồm:

```json
{
  "tenantId": "tenant-123",
  "keyName": "customer-pii",
  "contextFormatVersion": 1,
  "ciphertext": "vault:v1:<ciphertext-do-vault-tra-ve>"
}
```

Giá trị ciphertext trên chỉ minh họa cấu trúc, không phải bản mã hợp lệ để thử giải mã. Ứng dụng dựng lại context từ `tenantId` và `contextFormatVersion` theo đúng quy tắc đã công bố. Nếu đã lưu trực tiếp context (hoặc Base64 của nó), cần bảo đảm giá trị đó luôn gắn với bản ghi và được xác thực quyền đọc.

Không nhầm `contextFormatVersion=1` với `v1` trong ciphertext: **một bên là phiên bản quy ước nghiệp vụ, một bên là phiên bản khóa của Vault**. Rotation khóa không bắt buộc thay đổi format context.

## 5. Thực hành với Vault CLI và HTTP API

Giả sử Vault đã hoạt động, CLI được cấu hình `VAULT_ADDR` và workload có token/policy thích hợp. Các lệnh sau dùng **dữ liệu thử**, chạy trong Bash hoặc môi trường tương đương.

### 5.1. Tạo named key có dẫn xuất

```bash
# Thao tác một lần bởi người quản trị nếu Transit chưa được mount.
vault secrets enable transit

# Tạo key có hỗ trợ context.
vault write transit/keys/customer-pii \
  type=aes256-gcm96 \
  derived=true

# Kiểm tra metadata và xác nhận derived=true.
vault read transit/keys/customer-pii
```

Nếu `transit/` đã tồn tại, bỏ qua lệnh `vault secrets enable transit`. Các lệnh tạo key chỉ nên dùng trong quy trình provisioning/admin; ứng dụng nên nhận quyền sử dụng key đã được tạo sẵn.

### 5.2. Encrypt và decrypt với context khớp

HTTP request minh họa:

```http
POST /v1/transit/encrypt/customer-pii HTTP/1.1
X-Vault-Token: <token-co-quyen-encrypt>
Content-Type: application/json

{
  "plaintext": "aGVsbG8=",
  "context": "dGVuYW50LTEyMw=="
}
```

Ở đây `aGVsbG8=` là Base64 của `hello`; `dGVuYW50LTEyMw==` là Base64 của `tenant-123`. Ví dụ này dùng context ngắn để dễ kiểm tra; sản phẩm thật nên dùng format được định danh rõ ở mục 4.

Có thể thực hành ngay bằng CLI:

```bash
# Vault trả về ciphertext dạng vault:vN:...
CIPHER=$(vault write -field=ciphertext transit/encrypt/customer-pii \
  plaintext=aGVsbG8= \
  context=dGVuYW50LTEyMw==)

# Decrypt phải gửi LẠI context với đúng các byte ban đầu.
vault write -field=plaintext transit/decrypt/customer-pii \
  ciphertext="$CIPHER" \
  context=dGVuYW50LTEyMw== | base64 --decode
# Kết quả: hello
```

Kết quả `plaintext` trả về từ HTTP API/CLI cũng ở dạng Base64; cần giải mã Base64 để được byte gốc. Khi gọi thư viện Spring Vault, API cấp cao tự thực hiện bước encoding/decoding này ở tầng giao tiếp.

### 5.3. Thử sai context

```bash
# Context khác, là Base64 của "tenant-456".
vault write -field=plaintext transit/decrypt/customer-pii \
  ciphertext="$CIPHER" \
  context=dGVuYW50LTQ1Ng==
```

Với `aes256-gcm96` và ciphertext sinh từ context `tenant-123`, thao tác trên thất bại do không giải mã/xác thực bản mã với khóa dẫn xuất tương ứng. Nếu bỏ trường `context` khi key có `derived=true`, Vault cũng từ chối yêu cầu. Không xử lý trường hợp này bằng cách thử lần lượt context của nhiều tenant hay trả dữ liệu rác về phía người dùng.

### 5.4. Rewrap vẫn cần context

Khi khóa được rotation, bản mã cũ vẫn có thể giải mã nếu phiên bản khóa cũ được giữ và chưa bị giới hạn bởi `min_decryption_version`. `rewrap` chuyển ciphertext sang phiên bản mới **mà không trả plaintext cho caller**:

```bash
# Admin hoặc quy trình quản trị:
vault write -f transit/keys/customer-pii/rotate

# Quy trình migration có quyền rewrap:
NEW_CIPHER=$(vault write -field=ciphertext transit/rewrap/customer-pii \
  ciphertext="$CIPHER" \
  context=dGVuYW50LTEyMw==)
```

Cập nhật `NEW_CIPHER` trong database sau khi thao tác thành công, vẫn bảo toàn các trường dùng để tái tạo context. Với derived key, thiếu/sai context cũng khiến rewrap thất bại.

## 6. Gọi đúng context từ Spring Vault

Spring Vault cung cấp `VaultOperations.opsForTransit()`, trả về `VaultTransitOperations`. API `VaultTransitContext.fromContext(byte[])` nhận **byte context gốc**; thư viện sẽ mã hóa Base64 khi gửi JSON cho Vault. **Đừng tự Base64 rồi đưa byte của chuỗi Base64** vào `fromContext`, nếu không context trên wire sẽ bị mã hóa hai lần.

Ví dụ Java sau giữ nguyên context trong suốt vòng đời của bản ghi và kiểm soát phiên bản format:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTransitOperations;
import org.springframework.vault.support.VaultTransitContext;

public final class CustomerPiiTransitService {

    private static final String KEY_NAME = "customer-pii";
    private final VaultTransitOperations transit;

    public CustomerPiiTransitService(VaultOperations vaultOperations) {
        this.transit = vaultOperations.opsForTransit();
    }

    public StoredSecret encrypt(String tenantId, String sensitiveText) {
        VaultTransitContext context = contextFor(tenantId, 1);
        String ciphertext = transit.encrypt(
                KEY_NAME,
                sensitiveText.getBytes(StandardCharsets.UTF_8),
                context
        );
        return new StoredSecret(ciphertext, tenantId, 1);
    }

    public String decrypt(StoredSecret stored) {
        VaultTransitContext context =
                contextFor(stored.tenantId(), stored.contextFormatVersion());

        byte[] plaintext = transit.decrypt(
                KEY_NAME,
                stored.ciphertext(),
                context
        );
        return new String(plaintext, StandardCharsets.UTF_8);
    }

    private static VaultTransitContext contextFor(
            String tenantId, int formatVersion) {

        if (formatVersion != 1) {
            throw new IllegalArgumentException("Unsupported context format");
        }
        if (tenantId == null || !tenantId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid tenant ID");
        }

        String value = "app:customer-pii:v1:tenant=" + tenantId;
        return VaultTransitContext.fromContext(
                value.getBytes(StandardCharsets.UTF_8));
    }

    public record StoredSecret(
            String ciphertext,
            String tenantId,
            int contextFormatVersion) {}
}
```

**Giả định của ví dụ:** `VaultOperations` đã được ứng dụng khởi tạo với endpoint, TLS và cơ chế xác thực thích hợp; named key `customer-pii` đã tồn tại với `derived=true`; Java hỗ trợ `record` (Java 16+). Nếu Transit được mount ở đường dẫn tùy chỉnh, dùng `opsForTransit("ten-mount")`.

Trong sản phẩm thực, `tenantId` phải lấy từ ngữ cảnh truy cập **đã xác thực/ủy quyền**, và khi decrypt phải kiểm tra bản ghi thực sự thuộc tenant được phép truy cập. Không dùng tenant ID do client tự khai báo để bỏ qua kiểm tra quyền. Các ví dụ trả về `String` để dễ hiểu; với binary payload, hãy giữ `byte[]` và quản lý vòng đời plaintext phù hợp.

Spring Vault có các overload `encrypt(String, String)` và `decrypt(String, String)` tiện cho trường hợp không có context. **Với key `derived=true` phải chọn overload có `VaultTransitContext`** (hoặc các đối tượng `Plaintext`/`Ciphertext` mang context tương đương), nếu không yêu cầu gửi lên Vault sẽ thiếu context.

## 7. Chính sách quyền và ranh giới bảo mật

Một policy chỉ cho workload mã hóa/giải mã bằng key đã tạo sẵn có thể viết:

```hcl
path "transit/encrypt/customer-pii" {
  capabilities = ["update"]
}

path "transit/decrypt/customer-pii" {
  capabilities = ["update"]
}
```

Các endpoint Transit dạng POST trên sử dụng capability `update` khi khóa đã tồn tại. Tránh cấp `create` không cần thiết cho ứng dụng, vì endpoint encrypt có khả năng tạo khóa mặc định nếu key chưa tồn tại và upsert được cho phép. Chỉ dịch vụ hoặc quy trình migration cần `rewrap` mới nên được cấp:

```hcl
path "transit/rewrap/customer-pii" {
  capabilities = ["update"]
}
```

Quyền tạo, sửa, rotate, export hay xóa key phải giao cho nhóm quản trị tương ứng. Phân quyền theo chức năng cũng hữu ích: có workload chỉ cần `encrypt`, có workload được `decrypt`, và một job chỉ được `rewrap` mà không được nhận plaintext.

Context **không thay thế** được Vault policy, workload authentication (Kubernetes auth, AppRole hoặc cơ chế tương đương) và phân quyền dữ liệu ở API/application layer. Nếu mỗi tenant cần biên bảo mật độc lập ngay tại Vault, hãy cân nhắc tách named key, mount, namespace (tùy phiên bản/sản phẩm Vault) hoặc token/policy tương ứng thay vì chỉ dựa vào `derived=true`.

## 8. Context trong vòng đời dữ liệu và vòng đời khóa

Một thiết kế có thể giải mã an toàn về sau cần bảo toàn đồng thời:

1. **Key name và mount path** mà dữ liệu đã dùng.
2. **Ciphertext nguyên vẹn**, gồm prefix phiên bản do Vault tạo.
3. **Context đúng từng byte**, hoặc đủ thông tin và thuật toán tái tạo context.
4. **Các phiên bản khóa cần thiết** trong Vault; không nâng `min_decryption_version` trước khi dữ liệu cũ được rewrap hoặc xử lý.
5. **Quyền và kết nối tới Vault** để decrypt/rewrap tại thời điểm sử dụng.

Ví dụ, nếu đổi `app:customer-pii:v1:tenant=tenant-123` thành `app:customer-pii:v2:tenant=tenant-123`, bản mã cũ **không tự chuyển** sang context v2. Không chỉ cập nhật trường `contextFormatVersion` ở database. Muốn chuyển context phải giải mã bằng context cũ rồi mã hóa lại bằng context mới (với quyền phù hợp), kiểm tra kết quả và chuyển dữ liệu một cách kiểm soát. `rewrap` thông thường xử lý **phiên bản khóa**, không phải công cụ tự đổi ý nghĩa context.

Không xóa named key hay toàn bộ keyring chỉ vì ứng dụng đã chuyển sang key khác: dữ liệu cũ có thể trở nên không thể phục hồi. Cũng không đưa context hoặc plaintext vào log truy vết, thông báo lỗi, metrics labels hay audit message của ứng dụng.

## 9. Xử lý lỗi khi triển khai

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Encrypt/decrypt bị từ chối do thiếu context | Key đã tạo với `derived=true`, caller dùng API không truyền context | Kiểm tra cấu hình key và overload Spring Vault |
| Sai context hoặc lỗi xác thực ciphertext | Byte context khi decrypt khác lúc encrypt; sai key, ciphertext bị sửa | So sánh thuật toán tạo context, tenant ID, encoding, phiên bản format và tính toàn vẹn dữ liệu |
| `403 permission denied` | Token không có capability trên đúng endpoint/key | Kiểm tra auth method, policy và mount path |
| Key không tìm thấy hoặc sai mount | Dùng sai tên key/đường dẫn; key chưa được provision | Kiểm tra cấu hình triển khai và mount, không tự tạo key trong luồng nghiệp vụ |
| Bản mã cũ không giải mã sau thay đổi chính sách phiên bản | `min_decryption_version` chặn version cũ hoặc keyring không còn | Kiểm tra metadata key và kế hoạch rotation/rewrap |
| Java sinh context khác CLI dù nội dung trông giống nhau | Đã Base64 hai lần, khác UTF-8/normalization, có ký tự xuống dòng | So sánh **byte gốc trước Base64**, chuẩn hóa quy ước tạo context |
| Lỗi kết nối, token hết hạn, Vault tạm thời không sẵn sàng | Vấn đề mạng, TLS, session/token hoặc hệ thống Vault | Theo dõi trạng thái Vault và vòng đời token; retry có giới hạn với lỗi tạm thời |

Không coi mọi lỗi giải mã là lỗi có thể retry. Thiếu quyền, sai context hoặc ciphertext lỗi thường cần sửa dữ liệu/cấu hình. Với retry do mạng, dùng timeout, backoff và giới hạn lần thử; tránh ghi plaintext/ciphertext hoặc token vào log.

## 10. Bài thực hành tự kiểm tra

Trong môi trường Vault test riêng, dùng named key `derived=true` và lần lượt kiểm tra:

1. Tạo `customer-pii` với `aes256-gcm96`, `derived=true`; xác nhận flag từ metadata.
2. Mã hóa `hello` với context `tenant-123` hai lần. **Cả hai** ciphertext đều giải mã ra `hello`, nhưng giá trị ciphertext thường khác nhau vì nonce ngẫu nhiên.
3. Mã hóa cùng plaintext với context `tenant-456`; kiểm tra decrypt với context `tenant-456` thành công, còn dùng chéo `tenant-123` thì thất bại.
4. Gọi encrypt/decrypt không có context; quan sát Vault từ chối khi key yêu cầu derivation.
5. Mã hóa, rotate key rồi decrypt ciphertext cũ bằng context cũ; sau đó rewrap với context cũ, kiểm tra ciphertext mới giải mã được và version prefix đã tăng.
6. Trong Java, thử `VaultTransitContext.fromContext` với byte UTF-8, lưu và đọc lại `tenantId` cùng `contextFormatVersion`. Khởi động lại ứng dụng và xác nhận dữ liệu vẫn giải mã được.
7. Dùng token chỉ được `encrypt` để gọi `decrypt`; mong đợi `403`. Thử token có quyền `rewrap` nhưng không có `decrypt` cho một job migration.

Khi test tự động, nên dùng Vault dành riêng cho kiểm thử tích hợp (ví dụ môi trường Vault dev cô lập hoặc container kiểm thử), tạo key thử với chính sách rõ ràng. Không sử dụng khóa và dữ liệu thật, không chạy `rotate` trên key đang phục vụ production chỉ để thử bài học.

## 11. Checklist trước khi sử dụng thực tế

- [ ] Đã quyết định dùng named key riêng hay derived key theo yêu cầu cô lập tenant.
- [ ] Key được tạo trước bằng cấu hình `derived=true` và thuật toán hỗ trợ.
- [ ] Context có format ổn định, phân tách mục đích, encoding UTF-8 rõ ràng và có version.
- [ ] Mỗi ciphertext gắn với đủ metadata để tái tạo **đúng context**.
- [ ] Mọi encrypt/decrypt/rewrap của derived key đều truyền context phù hợp.
- [ ] Spring Vault truyền byte context gốc; HTTP API truyền Base64 của byte đó.
- [ ] Kiểm tra quyền tenant ở application layer; Vault token có ACL tối thiểu.
- [ ] Đã có quy trình rotation, rewrap và phương án giữ các phiên bản khóa cũ cần thiết.
- [ ] Có kiểm thử context sai, context thiếu, phiên bản khóa cũ, quyền bị từ chối và Vault tạm thời lỗi.
- [ ] Không log plaintext, token hay dữ liệu context nhạy cảm; kết nối Vault dùng TLS và workload authentication thích hợp.

## Tài liệu tham khảo

- HashiCorp, [Transit secrets engine](https://developer.hashicorp.com/vault/docs/secrets/transit) — cách Transit xử lý mã hóa, version key, rotation, rewrap và convergent encryption.
- HashiCorp, [Transit secrets engine HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/transit) — các tham số `derived`, `context`, `convergent_encryption`, `associated_data` và quyền endpoint.
- Spring Vault, [`VaultTransitOperations` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTransitOperations.html) — encrypt, decrypt, rewrap có context.
- Spring Vault, [`VaultTransitContext` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultTransitContext.html) — cách tạo context từ byte và cấu hình request.
