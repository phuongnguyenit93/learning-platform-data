# Đọc, tạo và cập nhật policy trong Vault System API

## 1. Vì sao quản lý policy là một thao tác hệ thống quan trọng?

Trong module **SPRING_VAULT**, ứng dụng Java sử dụng `VaultTemplate` để đọc KV secrets, tạo dynamic credentials, gọi Transit encryption hoặc yêu cầu chứng thư PKI. Khả năng thực hiện các thao tác đó do **Vault ACL policy** quyết định: policy mô tả những API path nào được phép truy cập và mỗi path cho phép các hành động nào.

Ví dụ, dịch vụ `orders-api` chỉ được **đọc** secrets ở `kv/data/apps/orders/*`, trong khi một tác vụ triển khai cần quyền **cập nhật** secrets cho cùng phạm vi. Người vận hành có thể xây dựng hai policy riêng rồi gán chúng cho đúng phương thức xác thực workload (Kubernetes auth, AppRole hoặc cơ chế khác).

Để triển khai và thay đổi quyền một cách có kiểm soát, ta phải biết **đọc, tạo và cập nhật ACL policy** qua **Vault System API** (`sys/policies/acl/...`). Đây là hoạt động quản trị nhạy cảm: cập nhật một policy đang được dùng có thể thay đổi quyền của các token liên quan **ngay khi policy có hiệu lực**, không cần khởi động lại mọi ứng dụng.

Bài học này giúp bạn:

1. Phân biệt nội dung policy, Vault token và vai trò xác thực workload.
2. Đọc danh sách policy, đọc nội dung một policy, tạo mới hoặc cập nhật qua CLI và HTTP API.
3. Gọi API tương ứng từ Java Spring Vault bằng `VaultOperations`/`VaultTemplate`.
4. Xây dựng quy trình cập nhật an toàn, kiểm chứng policy đã lưu và các quyền cho phép/từ chối.
5. Nhận diện lỗi thường gặp: 403, 404, sai đường dẫn KV v2, chính sách không có hiệu lực như mong đợi.

> Phạm vi: **ACL policy**. Vault Enterprise còn có các loại chính sách như RGP/EGP, nhưng cú pháp và endpoint của chúng khác; không dùng các ví dụ ACL trong bài để quản lý chúng.

## 2. Policy, capability, token và auth role

Một ACL policy thường có tên và nội dung HCL hoặc JSON, gồm các khối `path` gắn với danh sách `capabilities`:

~~~hcl
# orders-reader.hcl
path "kv/data/apps/orders/*" {
  capabilities = ["read"]
}
~~~

Đây là quy tắc **đối với đường dẫn API của Vault**, không phải quyền trực tiếp trong PostgreSQL hoặc quyền trong ứng dụng Java. Token phải được gắn policy này và còn hiệu lực thì mới có thể `read` trên path phù hợp; engine cụ thể vẫn có quy tắc và lỗi riêng.

| Khái niệm | Ví dụ | Chức năng |
|---|---|---|
| ACL policy | `orders-reader` | Tập hợp quy tắc `path` / `capabilities` |
| API path | `kv/data/apps/orders/order-001` | Tài nguyên mà Vault kiểm tra quyền |
| Capability | `read`, `create`, `update`, `delete`, `list`, `sudo`, `deny` | Hành động Vault cho phép hoặc từ chối trên path |
| Token | Token sinh từ Kubernetes auth/AppRole | Mang danh sách policy names và danh tính truy cập Vault |
| Auth role | Role Kubernetes/AppRole cho `orders-api` | Ràng buộc danh tính workload và chính sách được gán khi đăng nhập |
| Token TTL / renewal | Token có thời hạn | Quyết định token còn đủ điều kiện thực hiện các yêu cầu hay không |

**Capability không phải tên HTTP method theo nghĩa tuyệt đối.** Nhiều API có ánh xạ quen thuộc: `read` thường là GET, `list` thường là LIST, `update` thường là POST/PUT. Nhưng một lệnh GET có thể **tạo** dynamic database credentials (`database/creds/<role>`), và capability cần thiết vẫn là `read` cho API path đó.

### Các capability cần nhớ

| Capability | Ý nghĩa thường gặp | Ví dụ |
|---|---|---|
| `create` | Tạo tài nguyên qua API hỗ trợ | Tạo secret KV tại path mới |
| `read` | Đọc thông tin qua API | GET dữ liệu KV v2 `kv/data/...` |
| `update` | Sửa/ghi dữ liệu qua API | Ghi secret hoặc cập nhật policy |
| `delete` | Xóa tài nguyên | Xóa một secret hoặc policy (theo endpoint) |
| `list` | Liệt kê tên các phần tử | Liệt kê ACL policy names, KV metadata keys |
| `sudo` | Quyền bổ sung cho API path root-protected | Dùng khi endpoint thực sự yêu cầu; không cấp đại trà |
| `deny` | Từ chối quyền trên path | Có độ ưu tiên cao hơn các capability cho phép |

Policy tên `orders-reader` không tự được gán cho mọi token. Sau khi tạo, người vận hành phải gắn policy vào role xác thực, token hoặc entity theo mô hình đang dùng. **Tạo/cập nhật policy** và **gán policy cho workload** là hai thao tác riêng.

Ngược lại, khi **nội dung** của một policy đã được gán cho token được cập nhật, Vault đánh giá quyền theo nội dung policy mới. Đừng giả định phải phát hành lại token để thay đổi có hiệu lực. Việc đổi **danh sách tên policy** gán qua auth role có vòng đời riêng; các token đã cấp cần được kiểm tra theo cơ chế phát hành/renewal thực tế.

## 3. Các endpoint thuộc Vault System API

API hiện hành để quản lý ACL policy nằm dưới `/v1/sys/policies/acl`. Những path dưới đây tính từ gốc `/v1`:

| Mục đích | HTTP method | Vault path | Tương ứng CLI |
|---|---|---|---|
| Liệt kê tên ACL policies | `LIST` | `sys/policies/acl` | `vault policy list` |
| Đọc nội dung policy | `GET` | `sys/policies/acl/:name` | `vault policy read <name>` |
| Tạo policy mới | `POST` | `sys/policies/acl/:name` | `vault policy write <name> <file>` |
| Cập nhật policy hiện có | `POST` | `sys/policies/acl/:name` | `vault policy write <name> <file>` |
| Xóa policy (ngoài luồng bài học chính) | `DELETE` | `sys/policies/acl/:name` | `vault policy delete <name>` |

**Tạo và cập nhật là cùng một endpoint upsert**: nếu tên policy chưa tồn tại, Vault tạo nó; nếu tên đã tồn tại, nội dung được thay bằng tài liệu mới. Endpoint này không được hiểu là phép “thêm vài dòng vào policy cũ”. Mọi cập nhật cần gửi **toàn bộ nội dung mong muốn**.

Tài liệu Vault còn mô tả endpoint cũ `sys/policy/:name` (dạng số ít) để quản lý ACL policy. Các phiên bản Spring Vault có thể sử dụng endpoint cũ cho `VaultSysOperations`. Khi code ứng dụng gọi API trực tiếp, hãy chọn **một endpoint rõ ràng** rồi kiểm tra field response tương ứng:

| API | Đọc nội dung qua response | Ghi policy |
|---|---|---|
| `sys/policies/acl/:name` | Trường `policy` trong dữ liệu phản hồi | Body chứa `policy` |
| `sys/policy/:name` | Thường có trường `rules` trong response cũ | Body theo contract endpoint cũ |
| `VaultOperations.opsForSys()` | Object `Policy` (hạn chế khi nguồn lưu dưới dạng HCL) | `createOrUpdatePolicy(String, Policy)` |

Cần phân biệt cả request method: endpoint ACL `sys/policies/acl/:name` dùng `POST` theo HTTP API chính thức; Spring `VaultOperations.write(...)` gửi POST phù hợp. Đừng ghép các field `rules` và `policy` từ hai endpoint thành một định dạng mà server không hiểu.

## 4. Viết policy tối thiểu cho workload Spring Vault

Giả sử secret engine KV v2 được mount tại `kv/`; ứng dụng chỉ đọc các secret thuộc `apps/orders/`. Policy đầu tiên:

~~~hcl
# orders-reader.hcl — phiên bản 1
path "kv/data/apps/orders/*" {
  capabilities = ["read"]
}
~~~

Nếu ứng dụng phải liệt kê các key dưới prefix, cần thêm quyền riêng trên **metadata endpoint** của KV v2:

~~~hcl
# orders-reader.hcl — phiên bản 2
path "kv/data/apps/orders/*" {
  capabilities = ["read"]
}

path "kv/metadata/apps/orders" {
  capabilities = ["list"]
}

path "kv/metadata/apps/orders/*" {
  capabilities = ["list"]
}
~~~

Sự khác biệt quan trọng:

- `kv/data/apps/orders/*`: đường dẫn để đọc giá trị KV v2.
- `kv/metadata/apps/orders`: đường dẫn `LIST` để lấy tên key trong thư mục.
- `kv/metadata/apps/orders/*`: cần khi duyệt sâu thêm các thư mục con, tùy hành vi client.
- Các path trong policy là **đường dẫn API thực tế**. Khi dùng `VaultKeyValueOperations`, mã Java thường truyền key logic mà Spring Vault tự ánh xạ sang `/data/` hoặc `/metadata/`.

Nếu repository chỉ gọi `getById`, quyền `list` có thể không cần thiết. Liệt kê tên key có thể để lộ thông tin về cấu trúc dữ liệu, và danh sách do Vault trả về không được lọc theo quyền `read` từng key; chỉ cấp `list` trên thư mục ứng dụng thật sự cần duyệt.

Một ví dụ khác, nếu Java gọi Transit để mã hóa dữ liệu mà không phải đọc raw key material:

~~~hcl
path "transit/encrypt/orders-key" {
  capabilities = ["update"]
}

path "transit/decrypt/orders-key" {
  capabilities = ["update"]
}
~~~

Các path đó minh họa việc policy bao phủ **nhiều secret engines**. Chúng không mặc định cấp quyền quản lý khóa Transit hay quản lý cấu hình Vault.

## 5. Thực hành đọc, tạo, cập nhật policy bằng Vault CLI

Trong bài thực hành, phân tách hai danh tính:

- **Operator:** có quyền quản lý ACL policies và cấu hình auth role; dùng trong bước triển khai policy.
- **Workload:** chỉ có các quyền nghiệp vụ cần thiết; dùng trong bước kiểm chứng. Không dùng token root của operator cho kiểm thử quyền workload.

Giả định đã có `VAULT_ADDR` và cách đăng nhập an toàn. Những lệnh bên dưới chỉ được chạy trên **Vault dev/staging cô lập** với tên policy dành riêng cho bài tập.

### 5.1. Liệt kê policy và đọc policy có sẵn

~~~bash
vault policy list
vault policy read default
~~~

Lệnh đầu trả danh sách tên, lệnh sau hiển thị nội dung policy `default`. Đọc `default` để hiểu cách nó được dùng; **không chỉnh sửa default/root policy** trong bài thực hành.

Kiểm tra policy `orders-reader` trước khi tạo:

~~~bash
vault policy read orders-reader
~~~

Nếu chưa tồn tại, đây có thể là lỗi `not found`. Đối với pipeline tự động, phải phân biệt **chưa tồn tại** với **thiếu quyền đọc** hoặc **không kết nối được Vault**. Không suy đoán “policy không tồn tại” từ mọi lỗi.

### 5.2. Tạo policy mới từ HCL

Tạo một file `orders-reader.hcl` chứa chính xác nội dung phiên bản 1 ở mục trước. Kiểm tra cú pháp file bằng:

~~~bash
vault policy fmt orders-reader.hcl
~~~

Lệnh định dạng giúp kiểm tra cú pháp HCL nhưng không chứng minh policy đúng nghĩa nghiệp vụ. Hãy duyệt từng path và capability trước khi ghi.

Dùng tài khoản operator:

~~~bash
vault policy write orders-reader orders-reader.hcl
vault policy read orders-reader
vault policy list
~~~

Sau lệnh `write`, cần đọc lại để xác nhận tên policy và nội dung mong đợi đã được Vault lưu. Không chỉ dựa vào exit code 0 của lệnh ghi.

### 5.3. Cập nhật policy cùng tên

Khi ứng dụng cần thêm `findAll`, thay **toàn bộ nội dung file** bằng phiên bản 2 gồm quyền `read` trên `data` và `list` trên `metadata`.

~~~bash
# Dùng đúng file mới, đã được review và format.
vault policy fmt orders-reader.hcl
vault policy write orders-reader orders-reader.hcl
vault policy read orders-reader
~~~

Lệnh `write` lần thứ hai **cập nhật policy đang tồn tại**. Token vốn đã mang policy `orders-reader` sẽ chịu ảnh hưởng của các quy tắc mới khi Vault đánh giá các request tiếp theo.

Đây là hành động ảnh hưởng tới quyền truy cập thực tế. Trước khi nâng quyền, cần biết workload nào đang dùng policy; trước khi hạ quyền, cần biết workload nào có thể bị từ chối và cần rollback ra sao.

### 5.4. Kiểm chứng capability thay vì chỉ đọc văn bản

Sau khi dùng workload token thật, chạy:

~~~bash
vault token capabilities kv/data/apps/orders/order-001
vault token capabilities kv/metadata/apps/orders
vault token capabilities kv/data/apps/payments/payment-001
vault token capabilities sys/policies/acl/orders-reader
~~~

Với policy `orders-reader` phiên bản 2 và **không có policy khác cấp thêm quyền**:

| Path | Kết quả mong đợi |
|---|---|
| `kv/data/apps/orders/order-001` | Có `read` |
| `kv/metadata/apps/orders` | Có `list` |
| `kv/data/apps/payments/payment-001` | Không được `read` |
| `sys/policies/acl/orders-reader` | Không được quyền ghi/sửa policy |

Cần xác minh thêm bằng thao tác thực qua Spring Vault hoặc CLI, vì `vault token capabilities` đánh giá capability cho path chứ không đảm bảo secret đó tồn tại hay backend đang khỏe.

Ví dụ:

~~~bash
# Với token có quyền đọc secret; secret phải tồn tại trong môi trường test.
vault kv get -mount=kv apps/orders/order-001

# Chỉ chạy khi policy đã có list và prefix chứa các key trong test.
vault kv list -mount=kv apps/orders/
~~~

Nếu secret không tồn tại, việc đọc có thể trả “not found” dù capability `read` đúng. Không coi mọi HTTP 404 là lỗi ACL.

## 6. Thao tác cùng chức năng qua HTTP API

Khi tích hợp CI/CD hoặc service vận hành, có thể gọi trực tiếp HTTP API thay vì CLI. Hãy dùng kết nối TLS đã xác minh danh tính máy chủ; token operator được lấy từ cơ chế credential an toàn, không ghi cứng trong mã nguồn.

### 6.1. Liệt kê

~~~http
LIST /v1/sys/policies/acl
X-Vault-Token: <operator-token>
~~~

Ví dụ `curl`:

~~~bash
curl --fail-with-body --silent --show-error \
  --request LIST \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  "$VAULT_ADDR/v1/sys/policies/acl"
~~~

Response có thể có danh sách trong `data.keys`; tùy công cụ hiển thị có thể thấy thêm trường `keys` ở top-level. Nếu thư viện HTTP/proxy không hỗ trợ method LIST, hãy theo hướng dẫn API phiên bản Vault thực dùng về cách liệt kê, tránh tự thay bừa thành GET.

### 6.2. Đọc một policy

~~~http
GET /v1/sys/policies/acl/orders-reader
X-Vault-Token: <operator-token>
~~~

~~~bash
curl --fail-with-body --silent --show-error \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  "$VAULT_ADDR/v1/sys/policies/acl/orders-reader"
~~~

Cấu trúc phản hồi thường có dạng:

~~~json
{
  "data": {
    "name": "orders-reader",
    "policy": "path \"kv/data/apps/orders/*\" { capabilities = [\"read\"] }"
  }
}
~~~

Đây là ví dụ minh họa phần nội dung quan trọng. Response thực còn có thể có các trường metadata như `request_id` và `warnings`.

### 6.3. Tạo hoặc cập nhật policy

~~~http
POST /v1/sys/policies/acl/orders-reader
Content-Type: application/json
X-Vault-Token: <operator-token>

{
  "policy": "path \"kv/data/apps/orders/*\" { capabilities = [\"read\"] }"
}
~~~

Body yêu cầu là JSON có trường `policy` chứa **nội dung HCL dạng chuỗi**, không phải JSON object với key `path` ở top-level. Nếu dùng Java Spring Vault hoặc công cụ JSON serializer, để serializer escape dấu ngoặc kép và xuống dòng; đừng tự ghép chuỗi JSON bằng phép nối không an toàn.

Không gửi payload rỗng hoặc thiếu toàn bộ nội dung đã duyệt để “cập nhật một quyền nhỏ”. Endpoint create/update là upsert và có thể ghi đè chính sách đang dùng.

## 7. Java Spring Vault: đọc và ghi ACL policy từ VaultOperations

`VaultTemplate` triển khai `VaultOperations` và có các phương thức `read`, `write`, `list`. Để làm việc với HCL policy qua **API `sys/policies/acl` hiện hành**, có thể triển khai một adapter Java đơn giản.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

public final class VaultAclPolicyAdmin {

    private static final Pattern SAFE_NAME =
        Pattern.compile("[a-z][a-z0-9-]{2,63}");

    private final VaultOperations operatorVault;

    public VaultAclPolicyAdmin(VaultOperations operatorVault) {
        this.operatorVault = Objects.requireNonNull(operatorVault);
    }

    public List<String> listNames() {
        List<String> names = operatorVault.list("sys/policies/acl");
        return names == null ? List.of() : List.copyOf(names);
    }

    public String readHcl(String policyName) {
        String path = policyPath(policyName);
        VaultResponse response = operatorVault.read(path);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                "Policy not found or empty response: " + policyName
            );
        }

        Object value = response.getData().get("policy");
        if (!(value instanceof String hcl)) {
            throw new IllegalStateException(
                "Unexpected policy response for: " + policyName
            );
        }
        return hcl;
    }

    public void createOrUpdate(String policyName, String hcl) {
        if (hcl == null || hcl.isBlank()) {
            throw new IllegalArgumentException("Policy HCL must not be blank");
        }

        // operatorVault.write() gửi POST đến sys/policies/acl/:name.
        // Phần review, so sánh với bản hiện tại và quyền phê duyệt
        // phải được xử lý trước khi gọi method này.
        operatorVault.write(
            policyPath(policyName),
            Map.of("policy", hcl)
        );
    }

    private static String policyPath(String policyName) {
        if (policyName == null ||
            !SAFE_NAME.matcher(policyName).matches()) {
            throw new IllegalArgumentException("Invalid policy name");
        }
        return "sys/policies/acl/" + policyName;
    }
}
~~~

Các điểm kỹ thuật:

- Adapter dùng **operatorVault** là instance `VaultOperations` đã đăng nhập bằng danh tính có quyền quản lý policy, **không** sử dụng Vault client của ứng dụng nghiệp vụ.
- `readHcl` lấy `response.getData().get("policy")` theo contract của `sys/policies/acl/:name`; nó không dựa trên field `rules` của endpoint cũ.
- `createOrUpdate` sẽ tạo **hoặc cập nhật** cùng tên policy. Kết quả thành công từ `write` không thay cho readback và kiểm tra quyền thực tế.
- `operatorVault.list(...)` trả danh sách tên hoặc `null` khi không có kết quả theo contract client. Một danh sách trống cũng cần được phân biệt với lỗi xác thực hoặc endpoint bằng observability thích hợp.
- Kiểm tra `policyName` trước khi ghép URL giúp tránh tên chứa dấu `/`, chuỗi path không mong muốn hoặc injection. Cần chốt naming convention phù hợp tổ chức.
- API chịu sự điều khiển bởi Vault namespace và token được cấu hình cho `operatorVault`. Đổi namespace có thể làm cùng tên policy trỏ đến phạm vi khác.

**Lưu ý thiết kế:** `readHcl` có thể ném ngoại lệ nếu chưa tồn tại policy hoặc không có quyền đọc. Với pipeline cần quyết định create/update, hãy **phân loại HTTP 404 và 403** bằng loại exception/response của client đang dùng trước khi chọn bước tiếp theo. Không coi mọi ngoại lệ là “chưa tồn tại”.

### Ví dụ gọi từ service vận hành

~~~java
String policyName = "orders-reader";
String desiredHcl = """
    path "kv/data/apps/orders/*" {
      capabilities = ["read"]
    }
    path "kv/metadata/apps/orders" {
      capabilities = ["list"]
    }
    """;

VaultAclPolicyAdmin admin = new VaultAclPolicyAdmin(operatorVault);

// Trong chương trình thực tế: đọc hiện trạng, tạo diff và lấy
// phê duyệt thay đổi trước khi thao tác ghi.
admin.createOrUpdate(policyName, desiredHcl);

String storedHcl = admin.readHcl(policyName);
if (!storedHcl.contains("kv/data/apps/orders/*")) {
    throw new IllegalStateException("Policy readback incomplete");
}
~~~

Đoạn kiểm tra `contains` chỉ minh họa bước đọc lại; **không đủ** cho xác nhận policy tương đương ngữ nghĩa. Trong hệ thống triển khai cần đọc toàn bộ nội dung, so sánh hoặc parse được quy tắc tương ứng và chạy test capability. Vault có thể trả nội dung với khác biệt định dạng, nên không phụ thuộc duy nhất vào so sánh chuỗi nếu mục tiêu là tương đương policy.

## 8. Spring Vault VaultSysOperations: API quản trị bậc cao

Ngoài `VaultOperations.read/write`, Spring Vault còn cung cấp `VaultSysOperations`:

~~~java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultSysOperations;
import org.springframework.vault.support.Policy;

VaultSysOperations sys = operatorVault.opsForSys();

// Đọc danh sách tên policy qua abstraction Spring Vault:
java.util.List<String> names = sys.getPolicyNames();

// Tạo một policy từ model Policy do Spring Vault cung cấp:
Policy policy = Policy.of(
    Policy.Rule.builder()
        .path("kv/data/apps/orders/*")
        .capabilities("read")
        .build()
);
sys.createOrUpdatePolicy("orders-reader", policy);
~~~

`VaultSysOperations` hướng tới các thao tác quản trị đã được Spring Vault đóng gói. Có một **giới hạn cần nhớ**: API `sys.getPolicy(name)` làm việc với model `Policy` và theo tài liệu Spring Vault, **không thể đọc lại policy nếu nguồn biểu diễn là HCL**; nó có thể báo `UnsupportedOperationException`. Vì vậy:

- Khi muốn đọc/ghi tài liệu **HCL đầy đủ**, chọn CLI `vault policy read/write` hoặc adapter dùng `VaultOperations` và field `policy` của API hiện hành.
- Khi quản lý policy qua object `Policy` của Spring Vault, có thể dùng `VaultSysOperations.createOrUpdatePolicy` và `getPolicyNames`.
- Không mặc định các phương thức của `VaultSysOperations` luôn dùng endpoint `sys/policies/acl`. Một số phiên bản sử dụng API cũ `sys/policy`; cần kiểm tra quyền ACL trên **đường dẫn thực** do client gọi.

Việc tồn tại cả hai API không có nghĩa cần ghi policy qua cả hai. Chọn một cơ chế nhất quán cho từng công cụ triển khai, ghi rõ tên endpoint và xác minh trạng thái từ Vault.

## 9. Phân quyền để ai được đọc và ai được sửa policy?

Quyền **quản lý policy** khác quyền **sử dụng policy**. Một ứng dụng chỉ cần đọc secrets không nên có bất kỳ `create`/`update` trên `sys/policies/acl/*`.

### 9.1. Policy cấp quyền read-only cho auditor

Ví dụ người kiểm toán chỉ cần liệt kê và đọc nội dung những policy đã được duyệt:

~~~hcl
# acl-policy-auditor.hcl
path "sys/policies/acl" {
  capabilities = ["list"]
}

path "sys/policies/acl/orders-reader" {
  capabilities = ["read"]
}
~~~

Nếu operator chỉ cần một policy cụ thể, đừng cấp `read` trên `sys/policies/acl/*` toàn cục. Kết quả `LIST` cung cấp **tên policy trên phạm vi truy vấn**; đánh giá mức độ nhạy cảm trước khi cho phép liệt kê toàn cục.

### 9.2. Quyền triển khai policy giới hạn tên

Một pipeline được ủy quyền sửa **đúng một** policy có thể được cấp trên path tên đó:

~~~hcl
# acl-policy-deployer.hcl — ví dụ theo endpoint ACL hiện hành
path "sys/policies/acl/orders-reader" {
  capabilities = ["create", "read", "update"]
}
~~~

Đây chỉ là **điểm khởi đầu theo nguyên tắc ít quyền nhất**. Một số thao tác hệ thống root-protected hoặc cấu hình phiên bản Vault có thể cần thêm `sudo` trên chính path được phép; phải xác minh bằng `vault token capabilities` và một lần thử có kiểm soát. Không cấp `sudo` toàn bộ `sys/*` chỉ vì pipeline gặp 403.

Hạn chế này cũng **không bảo đảm** pipeline an toàn tuyệt đối: người có quyền sửa nội dung policy `orders-reader` có thể tăng quyền cho **mọi token đang mang chính policy đó**, bao gồm tài khoản của mình nếu trùng policy. Do vậy việc cho phép sửa policy vốn là quyền quản trị cần review và giám sát. Nếu policy `orders-reader` được dùng rộng, thay đổi nội dung có phạm vi tác động rộng dù deployer chỉ được sửa một tên.

### 9.3. Workload không quản lý policy

Vault token của dịch vụ `orders-api` nên chỉ có quyền nghiệp vụ:

~~~hcl
# orders-api.hcl
path "kv/data/apps/orders/*" {
  capabilities = ["read"]
}
~~~

Không cấp `sys/policies/acl` hay `sys/policy` cho token nghiệp vụ. Sau khi operator tạo `orders-api` và gán vào Kubernetes/AppRole role thích hợp, token được cấp từ role đó mang quyền theo cấu hình auth/policy tương ứng.

**Không chỉnh sửa `root` hoặc `default` trong bài tập**. Mọi thử nghiệm nên dùng tên policy, Vault mount và workload token riêng trên môi trường cô lập. Đối với Vault Enterprise namespace, việc quản lý policy phải dùng đúng namespace của dịch vụ dự kiến.

## 10. Quy trình cập nhật an toàn trong CI/CD

Cập nhật policy là thao tác có thể tác động ngay tới các workload đang chạy. Một quy trình triển khai nên có các bước:

~~~mermaid
flowchart TD
    A["Tệp HCL trong Git, được review"] --> B["Kiểm tra cú pháp và path"]
    B --> C["Đọc policy hiện tại từ Vault"]
    C --> D{"Tên policy đã tồn tại?"}
    D -->|Chưa| E["Tạo policy mới"]
    D -->|Rồi| F["So sánh khác biệt và đánh giá rủi ro"]
    F --> G{"Thay đổi được phép?"}
    G -->|Không| H["Dừng, chỉnh tài liệu"]
    G -->|Có| I["Ghi toàn bộ nội dung mới"]
    E --> J["Đọc lại policy đã lưu"]
    I --> J
    J --> K["Kiểm tra capability bằng workload token"]
    K --> L{"Positive/negative test đều đạt?"}
    L -->|Có| M["Ghi nhận deploy + giám sát"]
    L -->|Không| N["Khôi phục phiên bản đã duyệt theo runbook"]
~~~

Các bước cụ thể:

1. **Version control:** lưu HCL trong Git, xác định rõ owner, path, danh sách workloads sử dụng và mục tiêu thay đổi.
2. **Kiểm tra cú pháp:** dùng `vault policy fmt` và kiểm tra linter nếu có; rà soát path KV v2 `data`/`metadata` và tránh quyền rộng.
3. **Đọc trước khi ghi:** lấy policy hiện hành, phân biệt “không tồn tại” với “thiếu quyền”; nếu đã tồn tại, tạo diff trước khi cập nhật.
4. **Duyệt quyền:** đánh giá `read`, `list`, `create`, `update`, `delete` và `sudo` cho từng path, bao gồm những quyền được thêm hoặc bị xóa.
5. **Ghi có kiểm soát:** dùng `vault policy write` hoặc API `POST sys/policies/acl/:name` đúng policy name; không gửi bản HCL thiếu các rule phải giữ.
6. **Đọc lại:** lấy nội dung đã lưu và so sánh với nội dung mong muốn. Có thể parse HCL và kiểm chứng ngữ nghĩa khi server định dạng lại.
7. **Kiểm chứng token:** gọi `vault token capabilities` với danh tính workload hoặc phép thử thực; xác nhận path hợp lệ được phép và path ngoài phạm vi vẫn bị chặn.
8. **Giám sát và rollback:** lưu bản policy cũ để có thể khôi phục, nhưng nhớ rằng rollback cũng là thay đổi quyền tức thời và cần được quản lý như một lần deploy.

Trong Vault API, không nên mặc định upsert policy hỗ trợ cơ chế compare-and-swap giống KV v2. Nếu có nhiều pipeline cùng sửa policy, cần thiết kế **khóa điều phối ở hệ thống triển khai** hoặc một nguồn sở hữu rõ ràng để tránh ghi đè thay đổi của nhau.

Để tránh tăng quyền ngoài ý muốn, hãy kiểm tra **cả dữ liệu thật và cấu hình bên ngoài**. Ví dụ policy cho `kv/data/apps/orders/*` không được tự suy ra có quyền đọc `transit/keys/*` hoặc `database/config/*`.

## 11. Kiểm thử tích hợp và các trường hợp từ chối

Một bộ kiểm thử nên sử dụng Vault dev/test riêng, một token operator chỉ đủ quyền quản trị bài tập và một token workload gắn policy `orders-reader`.

| Ca | Danh tính | Hành động | Kết quả mong đợi |
|---|---|---|---|
| P01 | Operator | Gọi `GET sys/policies/acl/orders-reader` | Đọc đúng tên và policy đã lưu |
| P02 | Operator | Gọi `POST sys/policies/acl/orders-reader` với nội dung được duyệt | Tạo/cập nhật thành công |
| P03 | Operator | Gọi `LIST sys/policies/acl` | Có `orders-reader` trong danh sách |
| P04 | Workload | GET KV v2 `kv/data/apps/orders/order-001` | Được phép nếu secret tồn tại |
| P05 | Workload | LIST KV v2 `kv/metadata/apps/orders` | Thành công sau khi bổ sung `list` |
| N01 | Workload | Đọc `kv/data/apps/payments/payment-001` | Bị từ chối khi không có policy khác cho phép |
| N02 | Workload | POST `sys/policies/acl/orders-reader` | Bị từ chối do không có quyền quản trị policy |
| N03 | Auditor | POST `sys/policies/acl/orders-reader` | Bị từ chối vì chỉ có `read` |
| N04 | Operator token sai namespace hoặc hết hạn | Đọc/cập nhật policy | Bị từ chối theo xác thực/phân quyền; không diễn giải như policy chưa tồn tại |
| N05 | Pipeline | Ghi policy chứa cú pháp không hợp lệ | Vault trả lỗi; policy đang hoạt động phải được kiểm chứng giữ trạng thái mong đợi |

Điểm quan trọng: khi test N01, nếu workload còn mang một policy khác (chẳng hạn `default` được tùy chỉnh) cho phép path đó, thử nghiệm có thể không bị chặn. Test phải quan sát **toàn bộ effective capabilities**, không chỉ nội dung duy nhất policy `orders-reader`.

### Java JUnit 5: chỉ đọc và tạo/cập nhật qua operator

Bài test dưới đây tập trung vào quy trình API; muốn chạy cần fixture Vault cô lập với policy được phép dùng trong integration test, token operator và token workload được cung cấp qua cấu hình bảo mật riêng:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

// Hai client được tạo bởi test fixture hoặc Spring Test context,
// với hai workload identities khác nhau.
final class VaultAclPolicyIntegrationTest {

    private final VaultOperations operatorVault;
    private final VaultOperations workloadVault;

    VaultAclPolicyIntegrationTest(
        VaultOperations operatorVault,
        VaultOperations workloadVault
    ) {
        this.operatorVault = operatorVault;
        this.workloadVault = workloadVault;
    }

    @Test
    void operatorCanWriteAndReadPolicy() {
        String hcl = """
            path "kv/data/apps/orders/*" {
              capabilities = ["read"]
            }
            """;

        VaultAclPolicyAdmin admin =
            new VaultAclPolicyAdmin(operatorVault);

        admin.createOrUpdate("orders-reader", hcl);
        String stored = admin.readHcl("orders-reader");

        assertTrue(stored.contains("kv/data/apps/orders/*"));
        assertTrue(admin.listNames().contains("orders-reader"));
    }

    @Test
    void workloadCannotModifyPolicy() {
        VaultAclPolicyAdmin workloadAdmin =
            new VaultAclPolicyAdmin(workloadVault);

        // Test dùng đúng token không có quyền sys/policies/acl.
        assertThrows(
            org.springframework.vault.VaultException.class,
            () -> workloadAdmin.createOrUpdate(
                "orders-reader",
                """
                path "kv/data/apps/orders/*" {
                  capabilities = ["read"]
                }
                """
            )
        );
    }
}
~~~

**Giới hạn ví dụ:** đây là mã minh họa phần assertion, chưa phải fixture test chạy được độc lập. Nó cần tạo/cấp hai `VaultOperations` bằng cơ chế xác thực riêng và dọn policy test có kiểm soát. Nên dùng `@SpringBootTest` hoặc JUnit extension/constructor injection phù hợp phiên bản project; không dùng literal token trong class. Khi test bị từ chối, kiểm tra HTTP status/mã lỗi thực tế để phân biệt 403 ACL với lỗi kết nối hoặc Vault sealed.

Trong một integration test hoàn chỉnh, ngoài việc đọc lại chuỗi HCL còn phải kiểm chứng từng capability của **workload token** sau khi tạo và sau khi cập nhật policy. Ví dụ:
- Trước update: `read` trên dữ liệu, `list` metadata bị từ chối.
- Sau update: `read` trên dữ liệu vẫn hoạt động và `list` metadata được phép.
- Ở cả hai giai đoạn: workload không thể POST `sys/policies/acl/orders-reader`.

## 12. Phân tích lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xác minh và xử lý |
|---|---|---|
| `403 permission denied` khi đọc policy | Token không có `read` trên `sys/policies/acl/:name`; namespace sai, token hết hạn | Kiểm tra chính xác token, Vault namespace và capability trên path hệ thống |
| `403` khi ghi policy | Thiếu `create`/`update` hoặc yêu cầu `sudo` trên path được bảo vệ | Đối chiếu quyền của operator với endpoint thực, tránh cấp quyền `sys/*` quá rộng |
| `404` khi đọc policy | Tên policy không tồn tại hoặc gọi nhầm namespace/endpoint | So sánh `vault policy list` với đúng namespace; phân biệt với lỗi kết nối |
| Ghi thành công nhưng thiếu quyền cũ | Upsert đã thay **toàn bộ** nội dung policy | Đọc lại policy và phục hồi các rule đúng đã được duyệt |
| `VaultSysOperations.getPolicy` lỗi với HCL | Giới hạn parser/model Spring Vault đối với HCL policy | Đọc qua `VaultOperations.read("sys/policies/acl/:name")` hoặc CLI |
| API trả `rules` thay vì `policy` | Client đang dùng endpoint cũ `sys/policy` | Đọc contract đúng endpoint, không trộn response hai API |
| Workload vẫn có quyền sau khi xóa một rule | Token còn nhiều policy khác cấp cùng capability | Kiểm tra effective token capabilities và danh sách policy liên quan |
| CLI `vault kv get` bị 403 dù policy có `read` | Sai KV v1/v2 API path; thiếu `kv/data/...` hoặc token/namespace sai | Kiểm tra mount, version và path thực tế gửi tới Vault |
| LIST KV bị 403 trong khi GET thành công | Thiếu `list` trên `kv/metadata/...` | Cấp riêng quyền metadata ở prefix cần thiết nếu nghiệp vụ cần |
| Token có tên policy nhưng vừa deploy xong không đọc được secret | Policy đang sai path hoặc token hết hạn; còn khả năng có `deny` từ policy khác | Kiểm tra request path thực, effective capability và Vault audit log |
| Cập nhật policy gây mất quyền ở production | Thiếu kiểm tra khác biệt/consumer/rollback | Khôi phục bản đã review, xác minh lại các workload bị ảnh hưởng |

### Vì sao không nên chỉ đoán từ status code?

Một lỗi 403 có thể đến từ **Vault token**, **ACL path**, **namespace**, **quy tắc root-protected** hoặc những điều kiện bổ sung như quyền hệ thống. Một lỗi 404 có thể do tên policy hoặc secret không tồn tại, endpoint sai, thậm chí hệ thống che giấu tài nguyên không có quyền. Muốn chẩn đoán đúng, cần biết:
- HTTP method và Vault path thực tế.
- Namespace và identity của token.
- Policy names gắn với token và effective capabilities.
- Response/audit ID sau khi che giá trị nhạy cảm.
- Nội dung policy đã đọc lại từ Vault.

Không ghi token, nội dung secret, SecretID hay private key vào log, báo cáo build hoặc ticket.

## 13. Bảo mật khi quản lý policy bằng ứng dụng Java

Không nên cho mỗi instance ứng dụng nghiệp vụ gọi `createOrUpdatePolicy` lúc khởi động. Cách thiết kế đó biến một sai sót Java/config thành thay đổi quyền trên toàn hệ thống.

Một kiến trúc dễ kiểm soát hơn:

~~~mermaid
flowchart LR
    G["Git: policy HCL"] --> C["CI/CD hoặc công cụ quản trị"]
    C --> P["Duyệt thay đổi"]
    P --> V["Vault System API: sys/policies/acl"]
    V --> A["Policy names được gán cho auth roles"]
    A --> T["Tokens của workloads"]
    T --> S["Spring Vault: KV / Transit / PKI / Database"]
~~~

**Tài khoản operator** dùng để deploy policy nên tách khỏi **tài khoản ứng dụng** chỉ cần đọc/ghi secrets. Audit log phải cho phép truy vết ai sửa policy, tên policy nào, vào thời điểm nào và bằng workflow nào. Nếu cần ngăn pipeline tự tăng quyền thông qua policy nó sở hữu, thiết kế phân tách trách nhiệm, phê duyệt và ràng buộc bổ sung tùy khả năng Vault Enterprise/namespace.

Trong sản phẩm nhiều môi trường (`dev`/`staging`/`prod`), tên policy có thể trùng nhưng nội dung và mount khác nhau. Không đưa source policy của dev lên prod chỉ dựa vào tên; xác minh Vault address, namespace, mount và owner trước khi ghi.

### Checklist trước mỗi lần cập nhật

- [ ] Xác nhận đúng Vault cluster, namespace và policy name.
- [ ] Đọc policy hiện tại, lưu bản để review/rollback.
- [ ] Kiểm tra cú pháp HCL và sự khác biệt về các path/capabilities.
- [ ] Biết những workloads nào đang mang policy tên đó.
- [ ] Kiểm tra phạm vi KV v2 `data`/`metadata`, Transit, Database, PKI nếu liên quan.
- [ ] Dùng danh tính operator được phân quyền, không dùng root token thường trực.
- [ ] Ghi qua một endpoint/API nhất quán rồi đọc lại toàn bộ.
- [ ] Kiểm chứng permission của token thật, cả trường hợp cho phép và từ chối.
- [ ] Theo dõi audit log và lỗi permission sau khi triển khai.
- [ ] Có bản policy đã review để khôi phục khi thay đổi gây sự cố.

## 14. Bài tập thực hành

**Bài A — Tạo ACL policy và kiểm tra read-only.** Dựng Vault test với KV v2 mount `kv`, tạo một secret tại `apps/orders/order-001` bằng operator. Tạo policy `orders-reader` chỉ có `read` trên `kv/data/apps/orders/*`. Cấp token workload theo auth role dùng policy này. Kiểm tra đọc secret thành công; ghi secret và đọc `apps/payments/*` phải bị từ chối.

**Bài B — Cập nhật policy thêm quyền liệt kê.** Giữ nguyên tên `orders-reader`. Bổ sung `list` trên `kv/metadata/apps/orders` và `kv/metadata/apps/orders/*`; ghi lại bằng CLI hoặc Java. Kiểm tra `vault kv list -mount=kv apps/orders/` hoạt động và token vẫn không được ghi giá trị hoặc sửa `sys/policies/acl/orders-reader`.

**Bài C — Kiểm tra rủi ro ghi đè.** Trong môi trường test, tạo policy có hai rule. Sau đó thử đưa vào pipeline một bản HCL thiếu một rule và xem diff **trước khi ghi**. Thảo luận vì sao upsert được xem là thay toàn bộ tài liệu, và làm sao bắt buộc phê duyệt khi có quyền bị mất hoặc bị mở rộng.

**Bài D — So sánh Spring Vault abstraction.** Thử đọc một HCL policy bằng `VaultOperations.read("sys/policies/acl/:name")`, sau đó thử `VaultSysOperations.getPolicy(name)` trong phiên bản Spring Vault đang dùng. Ghi nhận sự khác biệt về biểu diễn dữ liệu và xử lý ngoại lệ.

### Câu hỏi tự kiểm tra

1. Vì sao chỉ tạo policy `orders-reader` không đủ để ứng dụng `orders-api` tự nhận quyền?
2. Vì sao việc cập nhật một policy đã gán cho token có thể ảnh hưởng ứng dụng đang chạy ngay lập tức?
3. Muốn ứng dụng `LIST` danh sách khóa KV v2, cần cấp capability trên `data` hay `metadata`?
4. Vì sao `POST sys/policies/acl/orders-reader` với một rule mới có thể làm mất rule đang tồn tại?
5. Khi Spring Vault không parse được policy viết HCL qua `VaultSysOperations.getPolicy`, nên dùng API nào?
6. Một token có `read` trên `kv/data/apps/orders/*` nhưng cũng có policy khác cấp quyền rộng hơn. Vì sao negative test có thể không đạt?
7. Vì sao quyền chỉnh sửa **một policy name** vẫn có thể tạo nguy cơ leo thang đặc quyền?

## 15. Tổng kết

**Đọc, tạo và cập nhật ACL policy** là chức năng quản trị của Vault System API, thường thực hiện qua `LIST sys/policies/acl`, `GET sys/policies/acl/:name` và `POST sys/policies/acl/:name`. API tạo/cập nhật cùng dùng một endpoint, và việc cập nhật **thay thế nội dung policy đang tồn tại**. Vì policy ảnh hưởng tới quyền của các token liên quan, quy trình triển khai cần đọc trước khi ghi, review diff, đọc lại kết quả và kiểm chứng effective capabilities.

Trong Java, `VaultTemplate`/`VaultOperations` có thể gọi trực tiếp những endpoint đó; `VaultSysOperations` cung cấp abstraction quản trị nhưng cần chú ý giới hạn khi đọc policy HCL và khác biệt giữa endpoint mới/cũ. Để giữ nguyên tắc ít quyền nhất, hãy để workload sử dụng policy qua auth role, còn việc quản trị policy do một thành phần vận hành riêng thực hiện với audit và kiểm thử tích hợp.

### Tài liệu tham khảo

- [HashiCorp Vault — System API: /sys/policies/](https://developer.hashicorp.com/vault/api-docs/system/policies)
- [HashiCorp Vault — System API cũ: /sys/policy](https://developer.hashicorp.com/vault/api-docs/system/policy)
- [HashiCorp Vault — Policies: concepts](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — Access controls with policies](https://developer.hashicorp.com/vault/tutorials/policies/policies)
- [Spring Vault — VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html)
- [Spring Vault — VaultSysOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultSysOperations.html)
- [Spring Vault — Policy type](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/Policy.html)
