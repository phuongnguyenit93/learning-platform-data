# Giới hạn phiên bản khóa được phép sử dụng trong Vault Transit

## 1. Bối cảnh: khóa Transit có nhiều phiên bản

Trong module **SPRING_VAULT**, ứng dụng Java truy cập HashiCorp Vault thông qua `VaultTemplate` hoặc `VaultTransitOperations` để mã hóa, giải mã và quản lý ciphertext. Transit secrets engine thực hiện các phép toán mật mã theo yêu cầu; ứng dụng thường **lưu ciphertext ở hệ thống dữ liệu của mình** (database, message hoặc object storage), thay vì yêu cầu Transit lưu hộ nội dung đã mã hóa.

Một khóa Transit có thể được **xoay vòng (rotate)** qua các phiên bản `v1`, `v2`, `v3`, v.v. Phiên bản được nhúng trong ciphertext trả về, thường có dạng:

~~~text
vault:v1:<dữ-liệu-mã-hóa>
vault:v2:<dữ-liệu-mã-hóa>
~~~

Phần `vault:vN:` cho biết phiên bản khóa được dùng để tạo ciphertext và giúp Vault biết nên dùng phiên bản nào khi giải mã. Tuy nhiên, việc **phiên bản khóa còn tồn tại** chưa có nghĩa là Vault **cho phép** dùng phiên bản ấy cho mọi thao tác.

Ví dụ: một dịch vụ thanh toán đã sử dụng khóa `transit/keys/payment-data` ở phiên bản 1 trong nhiều tháng. Sau khi xoay sang phiên bản 2, dữ liệu mới nên mã hóa bằng `v2`, nhưng các bản ghi cũ vẫn mang `vault:v1:...`. Nếu cấm giải mã phiên bản 1 trước khi chuyển đổi dữ liệu lịch sử, dịch vụ sẽ không đọc được những bản ghi đó.

Bài học này tập trung vào **giới hạn phiên bản khóa được phép sử dụng**, là một phần của quản trị vòng đời khóa Transit. Chủ đề liên quan trực tiếp tới phân quyền workload, thao tác `encrypt` / `decrypt` / `rewrap`, giám sát lỗi và kiểm thử tích hợp với ứng dụng Java.

## 2. Hai ngưỡng điều khiển phiên bản: encryption và decryption

Transit cho phép cấu hình các ngưỡng phiên bản tối thiểu trên từng khóa thông qua API cấu hình khóa:

~~~http
POST /v1/transit/keys/:name/config
~~~

Trong đó `transit` là tên mount minh họa; nếu engine được gắn ở mount khác, thay prefix cho phù hợp.

| Trường cấu hình | Kiểm soát | Hệ quả khi đặt bằng `2` |
|---|---|---|
| `min_encryption_version` | Phiên bản thấp nhất được phép chọn cho việc **mã hóa mới** | Yêu cầu dùng `key_version=1` để mã hóa mới bị từ chối |
| `min_decryption_version` | Phiên bản thấp nhất được phép **giải mã ciphertext** | Ciphertext `vault:v1:...` không thể giải mã qua API thông thường |
| `latest_version` | Phiên bản mới nhất hiện có của khóa (trạng thái do Vault quản lý, **không phải ngưỡng nhập tùy ý**) | Nếu `latest_version=2` thì thao tác mã hóa mặc định thường tạo `vault:v2:...` |

Cần phân biệt hai hành vi:

- **Mã hóa mặc định:** nếu client không yêu cầu một `key_version` cụ thể, Transit chọn phiên bản khóa mới nhất có thể dùng. Sau khi rotate, những yêu cầu mã hóa mặc định mới chuyển sang phiên bản mới; thao tác rotate **không tự mã hóa lại ciphertext cũ**.
- **Chỉ định phiên bản cũ:** một số request mã hóa chỉ định `key_version`. `min_encryption_version` là rào chắn để workload không tiếp tục tạo dữ liệu mới bằng phiên bản quá cũ.

Khi ngưỡng giải mã tăng lên, ciphertext có phiên bản thấp hơn ngưỡng **không còn được API giải mã chấp nhận**, dù ciphertext vẫn còn trong database. Đây là thay đổi tác động trực tiếp đến tính sẵn sàng của dữ liệu lịch sử.

Không suy ra rằng nâng `min_decryption_version` tự động xóa toàn bộ key material cũ, hay hạ ngưỡng chắc chắn phục hồi dữ liệu. Khả năng phục hồi phụ thuộc vào vật liệu khóa còn được Vault giữ lại hay đã bị trim/xóa, backup, cũng như các cấu hình và quyền liên quan. Vận hành thực tế cần coi thao tác nâng ngưỡng giải mã là một thay đổi có rủi ro cao và có kế hoạch khôi phục rõ ràng.

## 3. Ví dụ vòng đời khóa v1 → v2

Giả sử khóa `orders-key` thuộc mount `transit` đã tạo được hai ciphertext trước khi rotate:

~~~text
C1 = vault:v1:...   # Bản ghi A
C2 = vault:v1:...   # Bản ghi B
~~~

Sau khi xoay vòng lên `v2`, muốn ứng dụng tiếp tục chạy ổn định, người vận hành phải phân biệt ba thời điểm:

| Giai đoạn | `latest_version` | `min_encryption_version` | `min_decryption_version` | Hành vi quan trọng |
|---|---:|---:|---:|---|
| Trước rotate | 1 | 1 | 1 | Mã hóa và giải mã bằng `v1` |
| Sau rotate, trong thời gian chuyển đổi | 2 | 2 | 1 | Mã hóa mới phải dùng từ `v2`; ciphertext `v1` vẫn giải mã và rewrap được |
| Sau khi chuyển đổi hoàn tất | 2 | 2 | 2 | Mã hóa mới dùng `v2`; giải mã ciphertext `v1` bị từ chối |

Đây là **giá trị minh họa được cấu hình chủ động**, không phải cam kết về giá trị mặc định của mọi phiên bản Vault.

Đặt `min_encryption_version=2` trước khi nâng ngưỡng giải mã giúp ngăn các client tiếp tục tạo ciphertext mới bằng `v1`. Giữ `min_decryption_version=1` trong thời gian chuyển đổi tạo cơ hội đọc hoặc **rewrap** toàn bộ dữ liệu cũ.

~~~mermaid
flowchart TD
    A["Khóa v1: ciphertext cũ dùng v1"] --> B["Rotate: latest_version = 2"]
    B --> C["Đặt min_encryption_version = 2"]
    C --> D["Giữ min_decryption_version = 1"]
    D --> E["Rewrap ciphertext v1 thành v2"]
    E --> F{"Đã kiểm tra hết dữ liệu lịch sử, bản sao và consumer?"}
    F -->|Chưa| E
    F -->|Đã hoàn tất| G["Nâng min_decryption_version = 2"]
    G --> H["Ciphertext v2 giải mã được; v1 bị từ chối"]
~~~

**Nguyên tắc:** Đừng nâng ngưỡng giải mã trước khi bảo đảm tất cả ciphertext còn cần sử dụng đã được chuyển sang phiên bản được phép. Ngay cả khi ứng dụng hiện tại chỉ đọc bản ghi mới, batch job, dữ liệu backup, hàng đợi cũ hoặc một consumer khác có thể vẫn phụ thuộc vào ciphertext `v1`.

## 4. Rewrap khác gì với decrypt rồi encrypt?

Transit cung cấp thao tác **rewrap** để tạo ciphertext mới từ ciphertext cũ, dùng phiên bản khóa hiện tại mà **không trả plaintext về ứng dụng**:

~~~http
POST /v1/transit/rewrap/:name
Content-Type: application/json

{
  "ciphertext": "vault:v1:..."
}
~~~

Trong trường hợp khóa đã rotate sang `v2` và phiên bản nguồn `v1` còn được phép giải mã, kết quả có dạng:

~~~json
{
  "data": {
    "ciphertext": "vault:v2:..."
  }
}
~~~

Chuỗi phía sau `vault:v2:` là kết quả minh họa; không được tự đoán hay tạo thủ công ciphertext thật.

So sánh:

| Cách chuyển đổi | Plaintext có đi qua ứng dụng? | Mục đích | Lưu ý |
|---|---|---|---|
| `decrypt` rồi `encrypt` | Có | Trường hợp ứng dụng cần xử lý lại nội dung rõ | Tăng bề mặt lộ plaintext và số bước xử lý |
| `rewrap` | Không được trả về client | Nâng ciphertext lên phiên bản khóa mới | Vẫn cần quyền gọi rewrap và khả năng xử lý phiên bản ciphertext nguồn |
| `rotate` | Không | Tạo phiên bản khóa mới | **Không** thay đổi ciphertext đã lưu |

Một điều kiện quan trọng: để rewrap ciphertext `vault:v1:...`, phiên bản `v1` còn phải được chấp nhận làm nguồn. Nếu đã tăng `min_decryption_version=2`, việc rewrap ciphertext nguồn `v1` thông thường cũng thất bại; không thể coi rewrap là lối tắt để vượt ngưỡng giải mã.

Với khóa derived hoặc cấu hình mật mã yêu cầu `context`, các yêu cầu `encrypt`, `decrypt` và `rewrap` phải truyền context phù hợp. Thiếu hoặc sai context có thể làm request thất bại dù số phiên bản đúng.

## 5. Thực hành cấu hình bằng Vault CLI

Ví dụ giả định Vault đã hoạt động, Transit engine đã được mount tại `transit/` và người thao tác có quyền quản trị đúng khóa trong **môi trường thử nghiệm**. Các lệnh dưới đây dùng khóa minh họa `orders-key`.

### Bước 1: Tạo khóa và tạo ciphertext phiên bản 1

~~~bash
# Thực hiện một lần nếu key chưa tồn tại.
vault write -f transit/keys/orders-key

# Quan sát metadata của key.
vault read transit/keys/orders-key

# "invoice-123" được biểu diễn dưới dạng Base64.
vault write transit/encrypt/orders-key plaintext=aW52b2ljZS0xMjM=
~~~

Ghi lại giá trị `data.ciphertext` thực tế mà Vault trả về, chẳng hạn bắt đầu bằng `vault:v1:`. Phải dùng **ciphertext thực do Vault phát sinh** cho các bước sau, không thay bằng chuỗi minh họa.

### Bước 2: Rotate và chặn mã hóa bằng phiên bản cũ

~~~bash
# Xoay khóa từ v1 lên v2.
vault write -f transit/keys/orders-key/rotate

# Trong cửa sổ chuyển đổi: chỉ cho phép mã hóa từ v2,
# đồng thời vẫn cho phép giải mã dữ liệu v1.
vault write transit/keys/orders-key/config \
  min_encryption_version=2 \
  min_decryption_version=1

vault read transit/keys/orders-key
~~~

Sau bước này, `latest_version` phải phù hợp với phiên bản vừa rotate. Hãy kiểm tra ngưỡng thực tế bằng `vault read`, vì thao tác cấu hình thành công chỉ là một phần của xác minh.

Kiểm tra hành vi:

~~~bash
# Không chỉ định phiên bản: mã hóa bằng phiên bản mới nhất.
vault write transit/encrypt/orders-key plaintext=aW52b2ljZS0xMjM=

# Cố chọn v1: phải bị từ chối do ngưỡng mã hóa.
vault write transit/encrypt/orders-key \
  plaintext=aW52b2ljZS0xMjM= key_version=1
~~~

### Bước 3: Rewrap toàn bộ dữ liệu cũ

~~~bash
# Thay <CIPHERTEXT_V1_THUC_TE> bằng giá trị nhận từ Vault.
vault write transit/rewrap/orders-key \
  ciphertext="<CIPHERTEXT_V1_THUC_TE>"
~~~

Lưu `data.ciphertext` mới vào đúng bản ghi tương ứng trong cơ sở dữ liệu sau khi xác minh kết quả và cơ chế cập nhật an toàn. Không ghi đè bản ghi bằng một ciphertext ví dụ hay bằng chuỗi chứa dấu ba chấm.

Đối với hệ thống lớn, cần xử lý theo batch có khả năng chạy lại, đánh dấu phiên bản và tiến độ, cập nhật atomically hoặc có optimistic locking. Đặc biệt lưu ý các bản ghi được cập nhật đồng thời bởi ứng dụng. Sau mỗi batch, kiểm tra dữ liệu đã dùng `vault:v2:` và vẫn giải mã được.

### Bước 4: Nâng ngưỡng giải mã sau khi đã xác minh

~~~bash
# Chỉ thực hiện khi dữ liệu còn cần sử dụng đã được rewrap đầy đủ.
vault write transit/keys/orders-key/config min_decryption_version=2

vault read transit/keys/orders-key
~~~

Kiểm tra hai chiều:

- `decrypt` với ciphertext nguồn `vault:v1:...` phải bị từ chối.
- `decrypt` với ciphertext mới `vault:v2:...` phải thành công nếu token có đúng quyền và context.

Các lệnh CLI minh họa hai kiểm tra:

~~~bash
vault write transit/decrypt/orders-key \
  ciphertext="<CIPHERTEXT_V1_THUC_TE>"

vault write transit/decrypt/orders-key \
  ciphertext="<CIPHERTEXT_V2_SAU_REWRAP>"
~~~

Dữ liệu `plaintext` trả về bởi `decrypt` là Base64; chỉ giải mã ra chuỗi gốc ở nơi thực sự cần và không in dữ liệu nhạy cảm vào log ứng dụng.

## 6. Ví dụ Spring Vault: thao tác qua VaultTemplate

Trong Java, `VaultTemplate` có thể gọi các endpoint Transit theo đường dẫn Vault tương ứng. Mẫu sau cho thấy **đường dữ liệu**: mã hóa, giải mã và rewrap. Việc sửa ngưỡng phiên bản nằm ở luồng quản trị riêng.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;
import java.util.Objects;

import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

public final class OrderTransitService {

    private static final String KEY = "orders-key";
    private final VaultTemplate vault;

    public OrderTransitService(VaultTemplate vault) {
        this.vault = Objects.requireNonNull(vault);
    }

    public String encrypt(String plaintext) {
        String encoded = Base64.getEncoder().encodeToString(
            plaintext.getBytes(StandardCharsets.UTF_8)
        );
        VaultResponse result = vault.write(
            "transit/encrypt/" + KEY,
            Map.of("plaintext", encoded)
        );
        return field(result, "ciphertext");
    }

    public String rewrap(String oldCiphertext) {
        VaultResponse result = vault.write(
            "transit/rewrap/" + KEY,
            Map.of("ciphertext", oldCiphertext)
        );
        return field(result, "ciphertext");
    }

    public String decrypt(String ciphertext) {
        VaultResponse result = vault.write(
            "transit/decrypt/" + KEY,
            Map.of("ciphertext", ciphertext)
        );
        byte[] decoded = Base64.getDecoder().decode(
            field(result, "plaintext")
        );
        return new String(decoded, StandardCharsets.UTF_8);
    }

    private static String field(VaultResponse response, String name) {
        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Missing Transit response data");
        }
        Object value = response.getData().get(name);
        if (!(value instanceof String)) {
            throw new IllegalStateException("Missing Transit field: " + name);
        }
        return (String) value;
    }
}
~~~

Giải thích:

1. `encrypt` mã hóa Base64 đầu vào theo yêu cầu Transit. Kết quả là ciphertext do Vault cung cấp, có tiền tố `vault:vN:`.
2. `rewrap` nhận ciphertext và trả lại ciphertext phiên bản mới, ứng dụng không cần giải mã plaintext trong tiến trình chuyển đổi.
3. `decrypt` nhận ciphertext và giải mã Base64 của trường `plaintext` trả về.
4. Ví dụ dùng request/response trực tiếp qua `VaultTemplate` để nhìn rõ API. Ứng dụng có thể dùng lớp `VaultTransitOperations` của Spring Vault cho thao tác cấp cao khi phù hợp.
5. Không cài đặt logic **ép** phiên bản bằng cách chỉnh sửa tiền tố `vault:vN:`. Phiên bản là một phần định dạng ciphertext do Vault xác nhận, phải được quản lý bằng API đúng chức năng.

Mã trên chưa có kiểm tra input, retry policy, xử lý lỗi mạng và quản trị dữ liệu nhạy cảm đầy đủ; đây là ví dụ tập trung vào cơ chế phiên bản. Khi triển khai thực tế, hạn chế chuyển plaintext qua log, exception và hệ thống telemetry; kiểm thử cả timeout, phiên bản bị chặn và thay đổi token.

## 7. Phân quyền: workload và người vận hành giữ hai vai trò khác nhau

Quản trị phiên bản khóa yêu cầu quyền rộng hơn thao tác mã hóa thông thường. Một ứng dụng Java chỉ có chức năng mã hóa/giải mã không cần quyền điều chỉnh `min_decryption_version` hay xoay khóa.

**Policy ví dụ cho ứng dụng thông thường:**

~~~hcl
# transit-workload.hcl
path "transit/encrypt/orders-key" {
  capabilities = ["update"]
}

path "transit/decrypt/orders-key" {
  capabilities = ["update"]
}

# Chỉ cấp cho công việc chuyển đổi ciphertext có yêu cầu rewrap.
path "transit/rewrap/orders-key" {
  capabilities = ["update"]
}
~~~

**Policy ví dụ cho nhóm vận hành khóa:**

~~~hcl
# transit-operator.hcl
path "transit/keys/orders-key" {
  capabilities = ["read"]
}

path "transit/keys/orders-key/rotate" {
  capabilities = ["update"]
}

path "transit/keys/orders-key/config" {
  capabilities = ["update"]
}
~~~

Hai policy trên là ví dụ độc lập về vai trò; trong sản phẩm thực tế, hãy gán capability phù hợp cho từng workload và quy trình vận hành. Quyền `update` trên `transit/keys/orders-key/config` có thể thay đổi các thông số nhạy cảm khác của khóa, vì vậy cần bảo vệ nghiêm ngặt. Nếu workload được xác thực qua Kubernetes auth hoặc AppRole, role tương ứng phải được gắn policy đúng nhu cầu.

Một phiên bản khóa bị chặn bởi ngưỡng là **quy tắc của Transit**, không phải thiếu capability ACL trên một phiên bản riêng. Không thể khắc phục lỗi `decrypt vault:v1` bằng việc chỉ bổ sung `update` vào `transit/decrypt/orders-key` nếu `min_decryption_version` đang là `2`.

Token còn phải hợp lệ về TTL/renewal và đúng Vault namespace. Nếu quyền bị từ chối, cần phân biệt **403 do token/policy** với **lỗi yêu cầu do key version không hợp lệ**; đừng sửa policy chỉ dựa trên một chuỗi thông báo lỗi chung.

## 8. Thiết kế tiến trình chuyển đổi an toàn trong ứng dụng thật

Đối với một hệ thống có nhiều service cùng dùng khóa Transit, thay đổi giới hạn phiên bản nên được điều phối như một quá trình chuyển đổi dữ liệu.

**Giai đoạn chuẩn bị**

- Kiểm kê nơi lưu ciphertext: database, object storage, queue, cache, snapshot và các bản backup còn cần đọc.
- Xác định key và mount của từng loại dữ liệu; không nhầm khóa Transit với khóa mã hóa nằm ngoài Vault.
- Kiểm tra `latest_version`, `min_encryption_version` và `min_decryption_version` đang áp dụng; đánh giá khả năng dùng cùng khóa ở nhiều consumer.
- Xác minh các client dùng API mặc định hay truyền `key_version` cố định; nếu có client khóa cứng `v1`, cần cập nhật trước khi chặn mã hóa `v1`.
- Lên kế hoạch xử lý lỗi và cách bảo vệ dữ liệu khi tác vụ migration bị dừng giữa chừng.

**Giai đoạn chuyển đổi**

1. Rotate để có phiên bản mới và đặt ngưỡng mã hóa ngăn ghi thêm bằng phiên bản cũ.
2. Cho phép đọc phiên bản cũ trong thời gian chuyển tiếp, bảo đảm các consumer vẫn truy xuất dữ liệu.
3. Rewrap ciphertext cũ và lưu kết quả an toàn; theo dõi số bản ghi chưa chuyển đổi.
4. Kiểm tra lại các nguồn dữ liệu lịch sử và những tác vụ chạy chậm hoặc bất đồng bộ.
5. Chỉ nâng ngưỡng giải mã khi đã có bằng chứng dữ liệu còn được sử dụng không phụ thuộc phiên bản cũ.
6. Kiểm thử các consumer sau thay đổi; giám sát lỗi giải mã và chuẩn bị quy trình xử lý sự cố.

**Giai đoạn kết thúc**

- Ghi lại key, phiên bản khóa, thời điểm thay đổi, người phê duyệt và bằng chứng xác minh.
- Xác nhận không còn thành phần tạo ciphertext phiên bản cũ hoặc giữ dữ liệu cũ chưa chuyển đổi.
- Xem xét chính sách lưu trữ và loại bỏ các phiên bản vật liệu khóa cũ theo một quy trình riêng, được đánh giá rủi ro độc lập.

Không dùng việc nâng `min_decryption_version` như một bước “dọn dẹp” tự động mỗi lần rotate. Có thể phải duy trì khả năng giải mã các phiên bản cũ lâu hơn một chu kỳ vận hành để đáp ứng yêu cầu dữ liệu và thời gian khôi phục.

## 9. Kiểm thử tích hợp: ranh giới phiên bản phải được chứng minh

Một bài test có giá trị nên sử dụng instance Vault thử nghiệm, token giới hạn như workload thật và một khóa riêng cho bộ kiểm thử. Không dùng token root để chứng minh runtime ACL.

| Ca kiểm thử | Chuẩn bị | Kết quả mong đợi |
|---|---|---|
| Encrypt mặc định sau rotate | `latest_version=2` | Ciphertext mới mang tiền tố `vault:v2:` |
| Encrypt ép phiên bản cũ | `min_encryption_version=2`, request `key_version=1` | Request bị từ chối |
| Decrypt v1 trong thời gian chuyển đổi | `min_decryption_version=1`, ciphertext `vault:v1:...` còn hợp lệ | Giải mã thành công |
| Rewrap v1 → v2 | Có quyền rewrap; vẫn cho phép dùng v1 làm nguồn | Ciphertext mới có tiền tố `vault:v2:` và giải mã ra nội dung ban đầu |
| Decrypt v1 sau khi khóa ngưỡng | `min_decryption_version=2` | Request bị từ chối |
| Decrypt v2 sau khi khóa ngưỡng | `min_decryption_version=2` | Giải mã thành công |
| Workload cố sửa cấu hình khóa | Token chỉ có quyền `encrypt`/`decrypt` | Bị từ chối vì ACL |
| Truy cập với token hết hạn | Token bị thu hồi hoặc hết TTL | Thất bại xác thực; không được hiểu là lỗi phiên bản |

Để kiểm tra cấu hình thực tế, hãy đọc metadata khóa từ Vault bằng **danh tính có quyền vận hành**, sau đó thực hiện các phép mã hóa và giải mã bằng **danh tính workload**. Kiểm thử cần so sánh phiên bản ciphertext **và nội dung plaintext sau giải mã**, không chỉ so sánh HTTP status.

Với Spring Boot, có thể cấu hình bài test tích hợp dùng một Vault instance tạm, bật Transit một lần trong bước setup, tạo khóa và xoay vòng theo từng mốc. Cần cô lập key namespace/test key để các test không tác động qua lại. Bài kiểm thử hoàn chỉnh còn phải chứng minh hai chiều: phiên bản được phép hoạt động, còn phiên bản đã chặn bị từ chối.

Lưu ý: code kiểm thử nên kiểm tra loại lỗi theo **ngữ cảnh API và response thực tế**; mã HTTP và exception do Spring Vault ánh xạ có thể phụ thuộc trạng thái xác thực, request và phiên bản thư viện.

## 10. Các lỗi thường gặp khi đặt giới hạn phiên bản

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Ciphertext cũ đột nhiên không decrypt được | Tăng `min_decryption_version` trước khi rewrap dữ liệu | Đối chiếu phiên bản nguồn; đánh giá khả năng phục hồi theo key material, backup và quy trình được phê duyệt |
| Rotate thành công nhưng database vẫn có `vault:v1:` | Rotate chỉ tạo phiên bản khóa mới | Chạy migration rewrap cho ciphertext đã lưu |
| Encrypt chọn `key_version=1` thất bại | `min_encryption_version` đã lớn hơn 1 | Bỏ tham số ép phiên bản cũ hoặc nâng ứng dụng lên phiên bản hợp lệ |
| Rewrap ciphertext nguồn v1 thất bại | V1 đã dưới ngưỡng decrypt, context không đúng hoặc thiếu quyền | Kiểm tra ngưỡng, context và ACL theo đúng request |
| Chỉ một vài service báo lỗi | Consumer cũ vẫn truyền phiên bản cố định, token khác hoặc dữ liệu lịch sử chưa chuyển | Kiểm tra từng luồng và phiên bản của dữ liệu; tránh suy luận từ một service thành công |
| Nhìn thấy lỗi 403 từ Spring Vault | Token sai, thiếu policy, sai namespace hoặc đã hết hạn | Kiểm tra workload identity, capability và TTL; phân biệt với quy tắc version |
| Ciphertext `vault:v2:` nhưng decrypt sai | Nhầm key/mount, sai context hoặc ciphertext không nguyên vẹn | Kiểm tra key metadata, đầu vào và đúng API; không sửa tay prefix version |

Hai nhầm lẫn đặc biệt nguy hiểm:

**Nhầm lẫn 1: “Rotate đồng nghĩa đã bảo vệ toàn bộ dữ liệu cũ.”** Rotate chỉ ảnh hưởng phiên bản dùng cho các thao tác mới. Ciphertext đã lưu vẫn mang phiên bản cũ cho đến khi được rewrap hoặc mã hóa lại.

**Nhầm lẫn 2: “Có thể nâng ngưỡng decrypt ngay vì ứng dụng đã nâng cấp.”** Độ mới của phiên bản ứng dụng không chứng minh toàn bộ dữ liệu cũ đã được chuyển đổi. Cần có thống kê và kiểm tra trên **dữ liệu thực**, kể cả bản sao và consumer.

## 11. Checklist vận hành và câu hỏi ôn tập

Trước khi thay đổi ngưỡng phiên bản khóa:

- [ ] Xác định đúng Vault namespace, Transit mount, tên khóa và token thao tác.
- [ ] Đọc lại `latest_version`, `min_encryption_version`, `min_decryption_version`.
- [ ] Xác định nơi lưu ciphertext, những dữ liệu lịch sử và consumer còn cần giải mã.
- [ ] Rotate và chặn việc **mã hóa mới** bằng phiên bản cũ nếu phù hợp kế hoạch.
- [ ] Rewrap ciphertext còn cần đọc khi phiên bản nguồn vẫn được cho phép.
- [ ] Kiểm chứng dữ liệu sau rewrap còn giải mã ra đúng nội dung.
- [ ] Thử cả trường hợp phiên bản được phép và trường hợp phải bị chặn.
- [ ] Chỉ thay đổi `min_decryption_version` sau khi xác minh kết quả migration.
- [ ] Giới hạn ACL quản trị `config`/`rotate` và theo dõi lỗi sau triển khai.

Tự trả lời ba câu hỏi sau để kiểm tra sự hiểu bài:

1. Vì sao đặt `min_encryption_version=2` nhưng giữ `min_decryption_version=1` là cấu hình hợp lý trong giai đoạn chuyển tiếp?
2. Khi `latest_version=3`, tại sao cơ sở dữ liệu vẫn có thể còn ciphertext `vault:v1:...`?
3. Nếu `min_decryption_version=2` và người dùng yêu cầu đọc bản ghi `vault:v1:...`, việc cấp thêm quyền `transit/decrypt/*` có đủ để giải quyết lỗi hay không?

## 12. Tổng kết

Trong Transit, giới hạn phiên bản là cách **quy định phiên bản nào còn được phép phục vụ thao tác mới và dữ liệu cũ**. `min_encryption_version` ngăn tạo ciphertext mới bằng các phiên bản thấp hơn ngưỡng; `min_decryption_version` ngăn giải mã ciphertext dưới ngưỡng. `latest_version` tăng theo thao tác rotate, trong khi ciphertext lịch sử chỉ thay đổi khi thực hiện rewrap hoặc mã hóa lại.

Với ứng dụng Java dùng Spring Vault, trình tự vận hành an toàn là **rotate → chặn mã hóa phiên bản cũ → rewrap dữ liệu lịch sử → xác minh → nâng ngưỡng giải mã**. Kết hợp trình tự đó với xác thực workload, ACL tối thiểu, giám sát lỗi và kiểm thử tích hợp sẽ giúp giảm rủi ro mất khả năng truy cập dữ liệu khi nâng cấp vòng đời khóa.
