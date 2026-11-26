# Kiểm chứng trường hợp được phép và bị từ chối trong bài thực hành

## 1. Mục tiêu và bối cảnh

Khi ứng dụng Java kết nối HashiCorp Vault bằng Spring Vault, kết nối thành công chưa có nghĩa là ứng dụng có quyền đọc hoặc ghi mọi secret. Vault kiểm tra **danh tính đã xác thực**, **policy gắn với token** và **đường dẫn API thực tế** của từng yêu cầu trước khi quyết định cho phép hay từ chối.

Bài này thực hành phân quyền theo nguyên tắc **đặc quyền tối thiểu** trên KV secrets engine phiên bản 2 (KV v2). Ta kiểm chứng cùng một secret bằng các token có quyền khác nhau, rồi đối chiếu kết quả qua HTTP API và VaultTemplate.

Sau bài học, bạn có thể:

1. Tạo policy chỉ đọc, policy chỉ ghi và token không có quyền trên secret.
2. Xác nhận thao tác được phép trả về phản hồi thành công, thao tác bị cấm trả về HTTP **403 Forbidden**.
3. Phân biệt **403** (không được phép) với **404** (không tìm thấy) và lỗi token hết hạn hoặc bị thu hồi.
4. Gọi secret bằng **VaultTemplate** trong Java với đúng đường dẫn KV v2.
5. Xây dựng bảng kiểm thử quyền truy cập có thể lặp lại và nhận diện nguyên nhân khi kết quả khác kỳ vọng.

**Phạm vi:** Vault server ở chế độ development chạy trên máy cá nhân. Token root chỉ dùng để chuẩn bị dữ liệu, policy và token thử nghiệm. Ứng dụng thực tế cần xác thực theo workload (ví dụ Kubernetes hoặc AppRole), gắn policy phù hợp và tránh sử dụng root token.

## 2. Mô hình quyền trong bài thực hành

Giả sử ứng dụng cần một cấu hình dưới đường dẫn logic:

~~~text
secret/                    KV v2 mount
└── lab/ac-011             Đường dẫn secret dùng trong ứng dụng
~~~

KV v2 phân biệt đường dẫn người dùng và đường dẫn API:

| Mục đích | Đường dẫn |
| --- | --- |
| Gọi qua Spring Vault KV v2 | Mount `secret`, key `lab/ac-011` |
| Đọc/ghi nội dung qua HTTP | `/v1/secret/data/lab/ac-011` |
| Đường dẫn ACL cho đọc/ghi nội dung | `secret/data/lab/ac-011` |
| Đường dẫn ACL để liệt kê hoặc thao tác metadata | `secret/metadata/lab/*` |

Trong bài này ta chỉ đọc/ghi **nội dung** của đúng một secret; không cấp quyền trên toàn bộ mount và không cấp quyền liệt kê metadata.

Ba nhóm danh tính:

- **Reader:** được đọc secret, không được tạo hay cập nhật.
- **Writer:** được tạo/cập nhật secret, không được đọc nội dung.
- **Outsider:** chỉ mang policy mặc định, không có quyền truy cập secret của bài.

Vault kết hợp các capability được cấp qua policy của token. Khi đường dẫn không khớp quy tắc cho phép, mặc định thao tác bị từ chối. Các quyền thông dụng là `create`, `read`, `update`, `delete`, `list`, `sudo` và `patch`; mỗi API yêu cầu capability phù hợp.

## 3. Chuẩn bị Vault và secret mẫu

Cài sẵn Vault CLI và cURL. Các lệnh shell trong bài dùng **Bash** (Linux, macOS hoặc Git Bash). Chạy Vault development server ở cửa sổ terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=root
~~~

Mở terminal thứ hai, cấu hình kết nối:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="root"

vault status
vault secrets list -detailed
~~~

Chế độ dev thông thường có KV v2 tại mount `secret/`. Hãy kiểm tra kết quả lệnh `vault secrets list -detailed`: dòng `secret/` phải có type `kv`, version `2`. Nếu môi trường dev riêng của bạn chưa có mount đó, tạo bằng lệnh sau **chỉ sau khi xác nhận `secret/` chưa tồn tại**:

~~~bash
vault secrets enable -path=secret -version=2 kv
~~~

Dùng root token để tạo một secret dành riêng cho bài thực hành:

~~~bash
vault kv put -mount=secret lab/ac-011 \
  app="spring-vault-lab" \
  mode="initial"
~~~

Secret trên được lưu ở KV v2, có phiên bản. Khả năng đọc được nội dung bằng root token **không** chứng minh policy Reader hoặc Writer đúng, vì root token có quyền đặc biệt. Phần kiểm chứng phải dùng các token giới hạn quyền.

## 4. Tạo policy và token độc lập

### 4.1. Policy Reader

Tạo policy chỉ cho phép đọc một đường dẫn API nội dung:

~~~bash
vault policy write lab-ac011-reader - <<'HCL'
path "secret/data/lab/ac-011" {
  capabilities = ["read"]
}
HCL
~~~

Policy không chứa `create` hay `update`, nên Reader không được ghi secret.

### 4.2. Policy Writer

Tạo policy cho phép tạo mới hoặc cập nhật tại đúng đường dẫn đó:

~~~bash
vault policy write lab-ac011-writer - <<'HCL'
path "secret/data/lab/ac-011" {
  capabilities = ["create", "update"]
}
HCL
~~~

Policy Writer không chứa `read`. Một API ghi thành công không có nghĩa token có quyền đọc lại dữ liệu.

### 4.3. Cấp ba token thử nghiệm

Dùng root token tạo các token ngắn hạn, lưu trong biến shell để tránh phải sao chép token vào tài liệu:

~~~bash
READER_TOKEN="$(vault token create -policy=lab-ac011-reader -ttl=15m -field=token)"
WRITER_TOKEN="$(vault token create -policy=lab-ac011-writer -ttl=15m -field=token)"
OUTSIDER_TOKEN="$(vault token create -policy=default -ttl=15m -field=token)"
~~~

Vault thường gắn cả policy `default` vào token mới. Policy mặc định không cấp quyền đối với `secret/data/lab/ac-011` của bài này, nên không làm sai mục tiêu kiểm chứng. Nếu token hết hạn trong lúc thực hành, tạo lại token bằng các lệnh trên.

**Lưu ý:** Không in các biến token ra màn hình dùng chung, đẩy token lên Git hay đặt token thật trong source Java. Nếu môi trường có namespace hoặc chính sách mặc định tùy chỉnh, cần kiểm tra policy thực tế của token trước khi kết luận.

## 5. Kiểm chứng trực tiếp qua HTTP API

Dùng HTTP API để quan sát rõ **mã trạng thái**, không phải dựa vào lời thông báo của CLI. Trong các lệnh dưới đây, cURL gửi token ở header `X-Vault-Token`.

### Trường hợp A — Reader được đọc: HTTP 200

~~~bash
curl -sS -i \
  -H "X-Vault-Token: $READER_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/lab/ac-011"
~~~

Kỳ vọng: **200 OK**. JSON trả về theo cấu trúc KV v2, dữ liệu nghiệp vụ ở `data.data`, ví dụ:

~~~json
{
  "data": {
    "data": {
      "app": "spring-vault-lab",
      "mode": "initial"
    },
    "metadata": {
      "version": 1
    }
  }
}
~~~

Đây là **hình dạng rút gọn** của phản hồi; Vault còn trả thêm các trường metadata và thông tin request. Giá trị `version` phụ thuộc số lần ghi thực tế.

### Trường hợp B — Reader bị cấm ghi: HTTP 403

~~~bash
curl -sS -i -X POST \
  -H "X-Vault-Token: $READER_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"data":{"app":"should-be-denied"}}' \
  "$VAULT_ADDR/v1/secret/data/lab/ac-011"
~~~

Kỳ vọng: **403 Forbidden** với phản hồi lỗi dạng `permission denied`. Vault từ chối thao tác do Reader không có capability `create`/`update`. Secret đang tồn tại vẫn giữ nguyên dữ liệu và phiên bản sau yêu cầu bị từ chối.

### Trường hợp C — Writer được cập nhật: HTTP 2xx

~~~bash
curl -sS -i -X POST \
  -H "X-Vault-Token: $WRITER_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"data":{"app":"spring-vault-lab","mode":"updated-by-writer"}}' \
  "$VAULT_ADDR/v1/secret/data/lab/ac-011"
~~~

Kỳ vọng: **thành công (thông thường HTTP 200)** và KV v2 tạo một phiên bản mới. Nếu cần xem dữ liệu mới, sử dụng Reader hoặc root token; Writer không được cấp quyền đọc.

### Trường hợp D — Writer bị cấm đọc: HTTP 403

~~~bash
curl -sS -i \
  -H "X-Vault-Token: $WRITER_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/lab/ac-011"
~~~

Kỳ vọng: **403 Forbidden**. Policy có `create` và `update` không tự động bao gồm `read`.

### Trường hợp E — Outsider bị cấm đọc: HTTP 403

~~~bash
curl -sS -i \
  -H "X-Vault-Token: $OUTSIDER_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/lab/ac-011"
~~~

Kỳ vọng: **403 Forbidden**. Token đã được xác thực nhưng không có policy cho đường dẫn secret tương ứng.

### Bảng kết quả cần ghi nhận

| Token | Yêu cầu | Capability cần có | Kỳ vọng |
| --- | --- | --- | --- |
| Reader | GET nội dung secret | `read` | **200**, thấy nội dung |
| Reader | POST cập nhật secret | `create` hoặc `update` theo thao tác | **403**, không thay đổi dữ liệu |
| Writer | POST cập nhật secret | `update` | **2xx**, tạo phiên bản mới |
| Writer | GET nội dung secret | `read` | **403** |
| Outsider | GET nội dung secret | `read` | **403** |

Bạn có thể đọc lại bằng Reader sau trường hợp B và C, so sánh `data.data.mode` và `data.metadata.version`: thao tác Reader bị từ chối không tạo phiên bản; thao tác Writer thành công tạo phiên bản mới.

## 6. Kiểm tra tự động các mã trạng thái

Để tránh kiểm chứng thủ công nhầm lẫn, có thể dùng một hàm Bash đơn giản. Hàm chỉ in **mã trạng thái**, không in secret hay token:

~~~bash
assert_status() {
  local expected="$1"
  local token="$2"
  local method="$3"
  local actual

  if [ "$method" = "POST" ]; then
    actual="$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
      -H "X-Vault-Token: $token" \
      -H "Content-Type: application/json" \
      --data '{"data":{"app":"permission-check"}}' \
      "$VAULT_ADDR/v1/secret/data/lab/ac-011")"
  else
    actual="$(curl -sS -o /dev/null -w '%{http_code}' \
      -H "X-Vault-Token: $token" \
      "$VAULT_ADDR/v1/secret/data/lab/ac-011")"
  fi

  if [ "$actual" != "$expected" ]; then
    printf 'FAIL: %s expected=%s actual=%s\n' "$method" "$expected" "$actual"
    return 1
  fi
  printf 'PASS: %s -> HTTP %s\n' "$method" "$actual"
}

assert_status 200 "$READER_TOKEN" GET
assert_status 403 "$READER_TOKEN" POST
assert_status 200 "$WRITER_TOKEN" POST
assert_status 403 "$WRITER_TOKEN" GET
assert_status 403 "$OUTSIDER_TOKEN" GET
~~~

Chạy khi cả ba token còn hiệu lực. Hàm trả mã lỗi nếu bất kỳ trường hợp nào sai kỳ vọng; trong CI, có thể dùng `set -e` để dừng sớm. **Không** thay trạng thái kỳ vọng bằng `200` cho mọi token: như vậy sẽ bỏ qua chính mục tiêu kiểm thử phân quyền.

## 7. Đối chiếu bằng Spring Vault và VaultTemplate

Ở phía ứng dụng Java, Spring Vault có `VaultTemplate` để thao tác Vault và `VaultKeyValueOperations` để truy cập KV. Chọn rõ backend **KV_2**, vì policy và API của KV v2 có thêm phân đoạn `data/`.

Nếu dự án chưa có thư viện, bổ sung `org.springframework.vault:spring-vault-core` với phiên bản tương thích với Spring Boot/Spring Framework của dự án (thường thông qua BOM quản lý dependency).

Ví dụ Java sau dùng Reader token đã tạo ở bước 4. Trước khi chạy, truyền token vào biến môi trường `LAB_VAULT_TOKEN`; đây chỉ là cách mô phỏng danh tính trong bài lab:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.vault.VaultException;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

public class VaultAccessControlCheck {

    public static void main(String[] args) {
        String address = System.getenv().getOrDefault(
                "VAULT_ADDR", "http://127.0.0.1:8200");
        String token = System.getenv("LAB_VAULT_TOKEN");

        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException("LAB_VAULT_TOKEN is required");
        }

        VaultTemplate vault = new VaultTemplate(
                VaultEndpoint.from(URI.create(address)),
                new TokenAuthentication(token)
        );

        VaultKeyValueOperations kv = vault.opsForKeyValue(
                "secret",
                VaultKeyValueOperationsSupport.KeyValueBackend.KV_2
        );

        VaultResponse secret = kv.get("lab/ac-011");
        if (secret == null || secret.getData() == null) {
            throw new IllegalStateException("Secret is missing");
        }

        // Chỉ xác nhận có dữ liệu; tránh in giá trị secret vào log.
        System.out.println("READ_ALLOWED: " + secret.getData().keySet());

        try {
            kv.put("lab/ac-011", Map.of("app", "unauthorized-update"));
            throw new IllegalStateException("WRITE_UNEXPECTEDLY_ALLOWED");
        } catch (VaultException ex) {
            // Trong bài lab, đối chiếu lỗi này với HTTP 403 ở bước 5.
            // Trong kiểm thử thực tế, cần xác minh status HTTP, không
            // mặc định mọi VaultException đều có nghĩa là bị cấm.
            System.out.println("WRITE_REJECTED: " + ex.getMessage());
        }
    }
}
~~~

Với Reader token: `get` thành công và `put` bị Vault từ chối. Kết quả `VaultException` có thể bao bọc lỗi HTTP từ tầng client, do đó bài kiểm chứng chính xác phải xác nhận mã **403** ở HTTP hoặc kiểm tra status từ exception/cause trong lớp kiểm thử thích hợp. Nếu ứng dụng dùng Writer token, chiều kết quả sẽ đảo ngược: ghi thành công còn đọc bị từ chối.

**Về cách quản lý token:** `TokenAuthentication` trong ví dụ dùng token tĩnh để học. Trong ứng dụng thật, cấu hình phương thức xác thực theo workload và quản lý vòng đời session/token phù hợp; không cấp root token cho VaultTemplate. Việc token hết hạn hoặc bị revoke có thể làm thao tác từng chạy thành công chuyển sang lỗi 403.

## 8. Thử token bị thu hồi và nhận diện lỗi

Sau khi đã hoàn thành các kiểm chứng với Reader, thu hồi token bằng root token:

~~~bash
vault token revoke "$READER_TOKEN"

curl -sS -i \
  -H "X-Vault-Token: $READER_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/lab/ac-011"
~~~

Kỳ vọng yêu cầu tiếp theo bị từ chối, thông thường trả **403 Forbidden** do token không còn hợp lệ. Tuy cùng là 403, nguyên nhân ở đây là **vòng đời token**, không phải thiếu capability trên policy. Bạn có thể tạo Reader token mới và thử lại để xác nhận.

Phân biệt các trường hợp thường gặp:

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| 200/2xx đúng kỳ vọng | Token hợp lệ và policy cho phép | Kiểm tra nội dung/phiên bản thay đổi đúng thao tác |
| 403 khi token đang hoạt động | Thiếu capability, sai ACL path, policy không gắn đúng danh tính | Kiểm tra policy/token và đường dẫn thực tế `secret/data/...` |
| 403 sau khi hết hạn hoặc revoke | Token không còn hợp lệ | Tạo token mới theo cùng policy và thử lại |
| 404 khi đọc | Key không tồn tại, đã bị xóa, phiên bản không có hoặc path sai | Đối chiếu mount, key và version bằng tài khoản có quyền |
| 5xx hoặc không kết nối được | Vault service, seal state, mạng hoặc TLS | Kiểm tra `vault status`, URL và log máy chủ |

**403 không đồng nghĩa 404.** Khi một token không được quyền đọc, không được suy diễn rằng secret không tồn tại. Tương tự, ứng dụng không nên xử lý mọi lỗi Vault thành `null` hay tự động fallback về một secret khác vì có thể che giấu lỗi phân quyền.

Nếu token có quyền đọc dữ liệu mà gọi `vault kv list` thất bại, đó chưa chắc là lỗi: thao tác `list` của KV v2 yêu cầu capability `list` ở đường dẫn **`secret/metadata/...`**, khác với quyền `read` ở `secret/data/...`. Tương tự, chính sách Transit encryption và PKI có các API path/capability riêng; không thể dùng policy KV ở bài này để suy ra quyền trên các secrets engine đó.

## 9. Nguyên tắc kiểm thử và vận hành

Để kết quả có giá trị trong hệ thống thực tế:

1. **Mỗi trường hợp dùng đúng danh tính:** kiểm thử bằng token Reader/Writer/Outsider; không dùng root token để kết luận về quyền ứng dụng.
2. **Kiểm tra cả chiều cho phép và từ chối:** chỉ có trường hợp đọc thành công thì chưa chứng minh ứng dụng được giới hạn đúng.
3. **Kiểm tra tác dụng phụ:** yêu cầu ghi bị từ chối phải giữ nguyên dữ liệu và version; yêu cầu ghi thành công phải tạo phiên bản mới phù hợp.
4. **Giới hạn đường dẫn:** cấp quyền tới đúng key hoặc nhóm key cần thiết; wildcard rộng như `secret/data/*` có thể trao thêm quyền ngoài mục tiêu.
5. **Quản lý danh tính và vòng đời:** trong triển khai thật, xác thực bằng workload, kiểm soát TTL/renewal/revocation, giám sát lỗi 403 và dùng audit log của Vault theo chính sách bảo mật.
6. **Bảo vệ dữ liệu trong kiểm thử:** không ghi token hoặc giá trị secret thật vào log, báo cáo, ảnh chụp màn hình và hệ thống theo dõi lỗi.

Khi đã xong bài lab, có thể thu hồi các token thử nghiệm còn hoạt động:

~~~bash
vault token revoke "$WRITER_TOKEN"
vault token revoke "$OUTSIDER_TOKEN"
~~~

Trong **Vault dev server dành riêng cho bài này**, nếu muốn xóa cả dữ liệu và policy thử nghiệm:

~~~bash
vault kv metadata delete -mount=secret lab/ac-011
vault policy delete lab-ac011-reader
vault policy delete lab-ac011-writer
~~~

Xóa metadata KV v2 là xóa vĩnh viễn các phiên bản của secret tương ứng; chỉ làm trên môi trường dev đã xác nhận đúng key.

## 10. Tiêu chí hoàn thành

Bài thực hành được xem là **đạt yêu cầu kỹ thuật** khi bạn có bằng chứng cho cả năm hàng trong bảng kết quả: Reader GET **200**, Reader POST **403**, Writer POST **2xx**, Writer GET **403** và Outsider GET **403**; Reader POST không thay đổi secret; Writer POST tạo phiên bản mới; sau revoke, Reader token cũ không còn truy cập được.

Từ đó có thể rút ra quy tắc quan trọng khi tích hợp Spring Vault: **quyền truy cập gắn với danh tính, capability, đường dẫn API và trạng thái token tại thời điểm yêu cầu**. Mỗi nhánh được phép hoặc bị từ chối đều cần được kiểm chứng bằng cùng một thao tác thực tế mà ứng dụng Java sẽ gọi.
