# Lease ID, thời hạn và thuộc tính renewable

## 1. Vì sao phải hiểu lease khi dùng Spring Vault?

Giả sử ứng dụng Java dùng **Spring Vault** để yêu cầu một tài khoản PostgreSQL ngắn hạn từ **HashiCorp Vault**. Vault có thể tạo một username/password mới, gắn thời gian tồn tại và trả về thông tin quản lý vòng đời. Ứng dụng cần biết **tài khoản còn hiệu lực trong bao lâu**, **có thể gia hạn không** và **cần làm gì khi sắp hết hạn**. Những câu hỏi đó liên quan đến **lease**.

Bài học thuộc chương **Vòng đời lease** của module **SPRING_VAULT**: ứng dụng Java dùng `VaultTemplate` với danh tính workload, policy phân quyền và các secrets engine như KV, database, Transit hoặc PKI. Ở đây chúng ta tập trung vào ba trường cơ bản trong phản hồi Vault:

- `lease_id`: mã định danh một lease cụ thể.
- `lease_duration`: thời lượng còn hiệu lực được Vault cấp, tính bằng **giây** khi nhận phản hồi JSON.
- `renewable`: cho biết lease **đủ điều kiện** để yêu cầu gia hạn tại thời điểm đó.

Sau bài học, bạn có thể đọc metadata của secret động, phân biệt token TTL với secret lease TTL, thử lookup/renew/revoke một lease và thiết kế cách xử lý trong ứng dụng Spring Vault khi không thể gia hạn.

## 2. Lease là gì? Khác gì với secret và token?

**Lease** là thông tin Vault quản lý cho một tài nguyên có vòng đời. Khi cấp một **dynamic secret**, chẳng hạn tài khoản database tạm thời hoặc credential cloud được tạo theo yêu cầu, Vault trả thông tin lease để ứng dụng biết hạn sử dụng và có thể xin gia hạn hoặc thu hồi. Vault thường thu hồi tài nguyên khi lease hết hạn; tác động thực tế phụ thuộc plugin của secrets engine và việc revocation có thành công hay không.

Một ví dụ mang tính minh họa khi Vault đã cấu hình secrets engine `database/` và role `readonly`:

~~~json
{
  "request_id": "example-request-id",
  "lease_id": "database/creds/readonly/example-lease-id",
  "lease_duration": 3600,
  "renewable": true,
  "data": {
    "username": "example-ephemeral-user",
    "password": "REDACTED"
  }
}
~~~

Các giá trị `example-...` là **placeholder**, không phải credential thật. Trong response thực tế có thể xuất hiện những trường khác.

| Trường | Kiểu | Cần hiểu thế nào? |
| --- | --- | --- |
| `lease_id` | Chuỗi | Định danh lease để lookup, renew hoặc revoke bằng API được cấp quyền |
| `lease_duration` | Số nguyên giây | TTL được trả tại thời điểm cấp/renew; không phải thời điểm hết hạn tuyệt đối |
| `renewable` | Boolean | `true`: có thể **yêu cầu** gia hạn; Vault vẫn quyết định kết quả |
| `data.username` / `data.password` | Dữ liệu secret | Credential do secrets engine tạo; bảo vệ riêng, không log hoặc xuất ra API công khai |
| `request_id` | Chuỗi | Dấu vết yêu cầu; **không** dùng thay `lease_id` |

Một lần đọc `database/creds/readonly` thường tạo credential và lease mới. **Không suy ra** hai lần đọc cùng path sẽ nhận cùng `lease_id`, username hoặc mật khẩu. Lease ID là định danh phục vụ quản trị vòng đời, **không phải Vault authentication token** và không cho phép truy cập tài nguyên nếu người gọi không có token/ACL hợp lệ.

### Không phải response Vault nào cũng có lease thực

- **Dynamic secrets** như `database/creds/...`: được cấp lease, thường có `lease_id` khác rỗng.
- **KV v1/v2** lưu secret tĩnh: thông thường **không phát hành secret lease** cho mỗi lần đọc. Một phản hồi có `lease_duration` bằng 0 hoặc một giá trị metadata không đồng nghĩa có lease có thể renew; phải xem `lease_id`.
- **Transit encrypt/decrypt**: tạo kết quả mã hóa/giải mã, không phải tài khoản động được cấp lease ở mỗi thao tác.
- **PKI**: thời hạn chứng thư (`not_after`/validity) cần được đối chiếu với semantics của engine và cách thu hồi chứng thư; không giả định mọi chứng thư PKI đều có lease renewable giống database credential.
- **Token xác thực** có TTL và cơ chế renewal/revocation riêng; thao tác token dùng `vault token ...`, không dùng nhầm `vault lease renew`.

Vì vậy khi code kiểm tra lease, cần kết hợp **có `lease_id` hợp lệ**, `lease_duration` và `renewable` thay vì chỉ dựa vào một trường.

## 3. Lease ID: định danh, phạm vi và quyền thao tác

Định dạng thường thấy:

~~~text
database/creds/readonly/27e1b9a1-27b8-83d9-9fe0-d99d786bdc83
|------- path cấp credential -------| |---- phần định danh ----|
~~~

Phần tiền tố thường phản ánh path cấp secret. Vault có thể dùng tiền tố để xác định nhóm lease phục vụ quản trị. Tuy nhiên **đừng tự dựng lease ID** từ tên database role hoặc từ mã request; phải lấy đúng ID Vault trả về.

Các thao tác quản lý:

| Thao tác | CLI | HTTP API | Tác dụng |
| --- | --- | --- | --- |
| Lookup | `vault lease lookup LEASE_ID` | `POST /v1/sys/leases/lookup` | Lấy metadata hiện tại |
| Renew | `vault lease renew LEASE_ID` | `POST /v1/sys/leases/renew` | Yêu cầu đặt TTL còn lại mới |
| Revoke | `vault lease revoke LEASE_ID` | `POST /v1/sys/leases/revoke` | Yêu cầu thu hồi tài nguyên trước hạn |

Các endpoint quản trị lease yêu cầu **Vault token có capability phù hợp**. Token được phép *đọc secret động* không mặc nhiên được phép *lookup/renew/revoke lease*; quyền thực tế phụ thuộc policy, cơ chế quản trị và ràng buộc của Vault. Không cấp quyền rộng trên `sys/leases/*` cho mọi ứng dụng chỉ để đơn giản hóa bài lab.

### Vòng đời cơ bản

~~~mermaid
flowchart TD
    A["Secrets engine cấp secret động + lease ID"] --> B["Ứng dụng sử dụng credential còn hạn"]
    B --> C{"Lease sắp hết hạn?"}
    C -->|Chưa| B
    C -->|Rồi| D{"Có thể renew?"}
    D -->|Có| E["Yêu cầu Vault renew"]
    E --> F{"Vault chấp thuận?"}
    F -->|Có| G["Cập nhật TTL còn lại"]
    G --> B
    F -->|Không| H["Lấy credential thay thế"]
    D -->|Không| H
    H --> I["Chuyển kết nối/dữ liệu sử dụng sang credential mới"]
    I --> J["Thu hồi/để hết hạn lease cũ theo chính sách"]
    J --> B
~~~

Đây là **mô hình quyết định phía ứng dụng**, không phải cam kết Vault tự gửi thông báo hết hạn. Spring Vault có thành phần quản lý lease theo scheduler/event; nếu ứng dụng trực tiếp đọc response bằng `VaultTemplate`, nó vẫn phải chọn chiến lược quản lý phù hợp.

## 4. Đọc đúng `lease_duration`: TTL là khoảng thời gian còn lại

`lease_duration: 3600` nghĩa là Vault trả một khoảng TTL **3.600 giây** cho lease khi request được xử lý. Nó không phải Unix timestamp, không phải số phút và không phải thông báo credential tồn tại vĩnh viễn.

Giả sử ứng dụng nhận secret lúc **12:00:00** với TTL 3.600 giây: nếu không có gia hạn hoặc revoke, thời điểm hết hạn dự kiến ban đầu khoảng **13:00:00** theo thời gian server. Để lên lịch an toàn, ứng dụng không nên đợi tới đúng 13:00 mới hành động: còn độ trễ mạng, chênh lệch đồng hồ, lỗi retry và thời gian tạo kết nối bằng credential mới.

Có thể ước tính nội bộ:

~~~text
remainingTtl = lease_duration giây Vault trả về
observedAt = đồng hồ monotonic cục bộ khi nhận response
renewAt = observedAt + tỷ lệ TTL đã chọn (có khoảng đệm)
~~~

Đừng cộng cố định `lease_duration` của response ban đầu vào thời gian hiện tại của từng lần kiểm tra; mỗi lần thực hiện như vậy sẽ vô tình kéo dài lease **trong bộ nhớ ứng dụng** dù Vault chưa hề renew.

### Increment khi renew không phải số giây cộng tiếp

Ví dụ:

1. Vault cấp lease lúc 12:00 với TTL 60 phút, dự kiến hết hạn lúc 13:00.
2. Tới 12:40, ứng dụng gọi `vault lease renew -increment=30m LEASE_ID`.
3. Nếu Vault chấp thuận và trả TTL mới là 30 phút, thời gian hết hạn dự kiến chuyển thành **13:10** (30 phút tính từ **12:40**), không phải 13:30 và cũng không mặc định là 13:40.

`increment` là **TTL còn lại được yêu cầu tính từ lúc renew**, không phải khoảng cộng vào thời hạn cũ. Vault có thể trả TTL **ngắn hơn** hoặc từ chối nếu role, mount, max TTL, các ràng buộc backend hay tình trạng lease không cho phép. Luôn đọc **response sau renew** và cập nhật kế hoạch từ TTL thực nhận.

## 5. Thuộc tính `renewable` thực sự nói điều gì?

| Giá trị | Diễn giải đúng | Hành động phù hợp |
| --- | --- | --- |
| `true` | Lease hiện được đánh dấu **có thể xin gia hạn** | Lập lịch renew đủ sớm; kiểm tra response và các giới hạn thực tế |
| `false` | Lease **không thể renew** theo cơ chế hiện tại | Chủ động xin credential thay thế trước khi hết hạn nếu còn cần |
| Không có `lease_id` | Không có secret lease để chỉ đích renew/revoke | Không gọi `sys/leases/renew` theo response này; kiểm tra loại secrets engine |
| `lease_duration: 0` | Không có TTL lease hữu ích từ phản hồi đó | Xem loại response/backend; không diễn giải là credential vĩnh viễn |

**`renewable: true` không phải lời hứa gia hạn vô hạn.** Lease có thể chạm giới hạn `max_ttl`, bị revoke, auth token hoặc quyền của caller thay đổi, backend từ chối renewal hoặc Vault mất kết nối. Mặc dù ban đầu `renewable = true`, việc renew sau đó vẫn có thể thất bại.

**`renewable: false` không có nghĩa credential đã hết hạn ngay lập tức.** Credential còn có thể dùng đến lúc TTL kết thúc theo thông tin thực tế. Trong thời gian còn hiệu lực, ứng dụng cần tạo/nhận credential mới và chuyển kết nối an toàn.

### Phân biệt `renewable` của secret lease và Vault token

| Đối tượng | Thông tin vòng đời | Quản lý bằng |
| --- | --- | --- |
| Token dùng đăng nhập vào Vault | Token TTL, `renewable` của token, token type, max TTL | `vault token lookup`, `vault token renew`, `vault token revoke` |
| Database dynamic secret | `lease_id`, `lease_duration`, `renewable` của **secret lease** | `vault lease lookup/renew/revoke` |
| Secret tĩnh KV v2 | Data version và metadata KV, **thường không có lease động** | API KV v2 (`data/`, `metadata/`) và chính sách riêng |
| Transit encryption | Key/version của Transit và ciphertext; không phải lease trên từng ciphertext | API Transit, key rotation theo chính sách |
| PKI certificate | Validity của certificate, chính sách cấp/thu hồi và metadata có thể khác theo engine | API PKI, validity và cơ chế revocation tương ứng |

Một Vault token vẫn còn hiệu lực **không gia hạn tự động** credential database đã cấp. Ngược lại, secret lease còn hạn không bảo đảm token dùng cho **yêu cầu gọi Vault tiếp theo** vẫn hợp lệ. Khi một token cha bị revoke, các secret lease liên quan có thể bị thu hồi theo quan hệ mà Vault quản lý; đừng thiết kế ứng dụng dựa trên giả định hai vòng đời hoàn toàn độc lập.

## 6. Quyền quản lý lease và trách nhiệm của ứng dụng

Ứng dụng chỉ cần đọc một secret động nên có policy cấp đúng đường dẫn đọc:

~~~hcl
path "database/creds/readonly" {
  capabilities = ["read"]
}
~~~

Policy này **chưa đủ** để suy ra ứng dụng được quyền gọi mọi API `sys/leases/*`. Hãy xem các thao tác lease như một quyền vận hành riêng: cấu hình những capability cần thiết theo policy của foundation, chỉ ở phạm vi phù hợp, và kiểm chứng bằng token thật. Các lệnh renew/revoke bên dưới nên dùng **token của operator/lab được cấp quyền quản lý lease** khi token workload không có quyền.

Ví dụ cấu hình ranh giới trách nhiệm:

- **Workload:** lấy credential database tại `database/creds/readonly`, sử dụng trong tiến trình, không gửi secret ra client.
- **Thành phần quản lý lease:** giám sát TTL, gia hạn nếu được cấp quyền và có thể thực hiện; nếu không, xin credential thay thế trước hạn.
- **Vault server + database plugin:** giữ lease, áp dụng giới hạn, thực thi tạo/xóa credential theo backend.
- **Vận hành:** theo dõi renewal/revocation failure, mức độ đáp ứng của database plugin và các credential không thu hồi được.

Các secrets engine có thể gặp lỗi thu hồi ở hệ thống đích (ví dụ database tạm thời không kết nối được). Vault có thể ghi nhận lease **không thu hồi được** để operator xử lý. Không mặc định rằng lệnh revoke thành công ở tầng HTTP đồng nghĩa mọi kết nối dùng credential cũ đã lập tức biến mất; cần kiểm tra hành vi xác thực của hệ thống đích khi cần.

## 7. Thực hành CLI: cấp lease, lookup, renew và revoke

**Điều kiện đầu vào:** Có một Vault dev/test server, một database secrets engine đã cấu hình dưới mount `database/`, role `readonly`, database thử nghiệm có thể tạo/xóa user và token Vault có quyền phù hợp. `vault server -dev` **không tự tạo** database plugin/role hoặc PostgreSQL để lệnh `database/creds/readonly` chạy được.

Trên Bash, có thể kiểm tra cấu hình đã tồn tại:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"

# VAULT_TOKEN được cấp cho môi trường LAB; không in token.
vault status
vault secrets list
vault read database/roles/readonly
~~~

Nếu role không tồn tại, cần **chuẩn bị database secrets engine theo hướng dẫn triển khai cho PostgreSQL hoặc hệ quản trị đang sử dụng** trước khi đi tiếp. Không chuyển sang secrets engine KV chỉ để có dữ liệu vì KV không cung cấp lease động tương đương. Nếu một role đã thiết lập TTL, nó có thể khác các số trong ví dụ minh họa.

### 7.1. Lấy một lease mới mà không in username/password

Cài `jq` để chỉ trích xuất metadata. Lệnh `vault read` tạo credential động; biến chứa phản hồi chỉ tồn tại trong shell hiện tại và được xóa ngay sau khi tách metadata:

~~~bash
CREDS_JSON="$(vault read -format=json database/creds/readonly)"

LEASE_ID="$(printf '%s' "$CREDS_JSON" | jq -r '.lease_id // empty')"
LEASE_TTL="$(printf '%s' "$CREDS_JSON" | jq -r '.lease_duration')"
LEASE_RENEWABLE="$(printf '%s' "$CREDS_JSON" | jq -r '.renewable')"

unset CREDS_JSON

test -n "$LEASE_ID" || {
  echo "Khong nhan duoc lease_id tu dynamic secret"
  exit 1
}

printf 'TTL ban dau (giay): %s\n' "$LEASE_TTL"
printf 'Renewable: %s\n' "$LEASE_RENEWABLE"
~~~

Không in `LEASE_ID` trong log công khai: ID có thể tiết lộ thông tin về mount/role, và một thao tác quản lý đúng quyền có thể dùng nó. Trong môi trường thật, cũng phải lưu/luân chuyển **credential động** an toàn tới nơi sử dụng; ở bước minh họa này, credential đã được tạo nhưng không đưa vào kết nối nên cần revoke lease ở cuối bài.

Kỳ vọng: `LEASE_TTL` là số giây dương, `LEASE_RENEWABLE` là `true` hoặc `false`, `LEASE_ID` không rỗng. Một role khác có thể trả TTL và thuộc tính renewability khác.

### 7.2. Lookup lease hiện tại

Dùng **token đủ quyền lease lookup**:

~~~bash
vault lease lookup "$LEASE_ID"
~~~

Kết quả có thể gồm `id`, `issue_time`, `expire_time`, `last_renewal`, `renewable`, `ttl`. `ttl` ở lần lookup **thường nhỏ hơn** `lease_duration` khi vừa cấp vì thời gian đã trôi qua.

Nếu nhận 403, kiểm tra policy và token của người đang thực hiện lookup. Không kết luận lease không tồn tại chỉ từ 403.

### 7.3. Gia hạn khi `renewable = true`

~~~bash
# Thực hiện trước khi hết hạn, với token có quyền renew lease.
vault lease renew -increment=30m "$LEASE_ID"

# Xem TTL và trạng thái mới sau lần renew.
vault lease lookup "$LEASE_ID"
~~~

Lệnh `-increment=30m` **xin** TTL còn lại 30 phút từ thời điểm renew; Vault có thể trả ngắn hơn hoặc từ chối. Không cộng thêm 30 phút vào TTL cũ ở phía ứng dụng. Sau renew, hãy dựa trên TTL mới và `renewable` do Vault trả về.

Với `LEASE_RENEWABLE=false`, **không cần cố renew** để chứng minh nó thất bại trong production. Trong sandbox, có thể kiểm tra một lần theo quyền thực tế và ghi nhận lỗi; chiến lược đúng là yêu cầu credential mới trước khi hết hạn.

### 7.4. Thu hồi lease trước hạn

~~~bash
# Revoke đúng duy nhất lease vừa tạo.
vault lease revoke "$LEASE_ID"

# Nếu lookup được phép, việc lookup lại sẽ cho biết lease không còn tồn tại.
vault lease lookup "$LEASE_ID"
~~~

Lệnh cuối được kỳ vọng không còn trả lease hợp lệ sau khi revocation hoàn tất. Với database role, Vault sẽ yêu cầu database plugin chạy thao tác thu hồi user/credential phù hợp. Có thể kiểm tra phía database bằng tài khoản quản trị của **sandbox**, nhưng không thử trên hệ thống dữ liệu thật.

**Cảnh báo về phạm vi:** `vault lease revoke -prefix database/creds/readonly` có thể thu hồi **nhiều lease** của role, ảnh hưởng các ứng dụng khác. Bài này chỉ sử dụng `vault lease revoke "$LEASE_ID"` để giới hạn tác động lên lease vừa tạo.

### 7.5. Gọi đúng HTTP API

Nếu ứng dụng hoặc bài kiểm thử cần dùng HTTP trực tiếp, payload đối với ba thao tác có dạng:

~~~http
POST /v1/sys/leases/lookup
Content-Type: application/json
X-Vault-Token: <TOKEN_DU_QUYEN>

{"lease_id":"database/creds/readonly/example-lease-id"}
~~~

~~~http
POST /v1/sys/leases/renew
Content-Type: application/json
X-Vault-Token: <TOKEN_DU_QUYEN>

{"lease_id":"database/creds/readonly/example-lease-id","increment":1800}
~~~

~~~http
POST /v1/sys/leases/revoke
Content-Type: application/json
X-Vault-Token: <TOKEN_DU_QUYEN>

{"lease_id":"database/creds/readonly/example-lease-id"}
~~~

Mỗi `<...>` hoặc `example-...` ở đây là **placeholder**; không gửi nguyên văn để thử với Vault. `increment: 1800` biểu diễn 1.800 giây TTL đề nghị. Quyền API phải được cấp theo policy tương ứng. **Token lease** dùng endpoint khác (`auth/token/renew`) và các lệnh `vault token`, không dùng `sys/leases/renew`.

## 8. Đọc metadata lease trong Spring Vault

Để lấy một dynamic secret trong Java, `VaultTemplate` có thể gọi `read(path)`. `VaultResponse` chứa cả dữ liệu secret (`getData()`) và metadata lease, với các method:

- `getLeaseId()` trả `String` có thể null.
- `getLeaseDuration()` trả `long`, theo giây.
- `isRenewable()` trả `boolean`.

Ví dụ service Spring Boot sau yêu cầu một secret động từ role `readonly` đã được cấu hình trước:

~~~java
import java.time.Duration;
import java.util.Map;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class DatabaseLeaseReader {

    private final VaultTemplate vault;

    public DatabaseLeaseReader(VaultTemplate vault) {
        this.vault = vault;
    }

    public DatabaseCredentialLease requestCredentials() {
        VaultResponse response =
                vault.read("database/creds/readonly");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Database credentials unavailable");
        }

        String leaseId = response.getLeaseId();
        long durationSeconds = response.getLeaseDuration();

        if (leaseId == null || leaseId.isBlank()
                || durationSeconds <= 0) {
            throw new IllegalStateException(
                    "Dynamic secret response has no usable lease");
        }

        Map<String, Object> data = response.getData();
        String username = Objects.toString(data.get("username"), "");
        String password = Objects.toString(data.get("password"), "");

        if (username.isBlank() || password.isBlank()) {
            throw new IllegalStateException(
                    "Database credentials are incomplete");
        }

        // Chỉ truyền nội bộ cho thành phần quản lý kết nối.
        // Không serialize đối tượng này thành API response hay ghi log.
        return new DatabaseCredentialLease(
                username,
                password,
                leaseId,
                Duration.ofSeconds(durationSeconds),
                response.isRenewable()
        );
    }

    public static final class DatabaseCredentialLease {
        private final String username;
        private final String password;
        private final String leaseId;
        private final Duration ttl;
        private final boolean renewable;

        private DatabaseCredentialLease(
                String username,
                String password,
                String leaseId,
                Duration ttl,
                boolean renewable) {
            this.username = username;
            this.password = password;
            this.leaseId = leaseId;
            this.ttl = ttl;
            this.renewable = renewable;
        }

        // Thành phần quản lý kết nối đọc nội bộ các field
        // qua phương thức kiểm soát phù hợp, không public hóa secrets.
        public boolean canRequestRenewal() {
            return renewable && !leaseId.isBlank() && !ttl.isZero();
        }
    }
}
~~~

Ví dụ dùng lớp giữ dữ liệu riêng nhằm tránh `record.toString()` vô tình ghi password vào log. Khi triển khai thực tế cần định nghĩa đường truyền credential vào connection pool, thay đổi credential an toàn, hủy tham chiếu không còn sử dụng và cleanup lease nếu tạo thất bại giữa chừng. **Mỗi lần gọi `requestCredentials()` có thể phát sinh credential và lease mới**; không gọi method này chỉ để kiểm tra trạng thái cho vui hoặc đặt nó vào endpoint public.

`VaultTemplate` sử dụng Vault token do hệ thống authentication/session của ứng dụng cấp. **Chính token đó cần quyền đọc `database/creds/readonly`**; lease metadata không thể thay thế Vault token trong việc gọi các endpoint khác.

### `getLeaseDuration()` khác một đối tượng `Lease` của Spring Vault

Spring Vault có lớp `org.springframework.vault.core.lease.domain.Lease` bao gồm `getLeaseId()`, `getLeaseDuration()` và `isRenewable()`. Trong lớp `Lease`, `getLeaseDuration()` trả **`Duration`**; còn trong `VaultResponse`, method cùng tên trả **`long`**. Đây là khác biệt kiểu dữ liệu quan trọng khi chuyển giữa REST response và abstraction quản lý lease.

Một ứng dụng không nên suy rằng mọi response có `getLeaseDuration() > 0` đều có thể renew. Cần xác nhận lease ID thực, `renewable`, semantics của engine và quyền caller.

## 9. Tự động hóa bằng SecretLeaseContainer

Việc tự đọc một lần bằng `VaultTemplate` **không tự động tạo vòng lập quản lý lease**. Spring Vault cung cấp `SecretLeaseContainer` để đăng ký secrets cần quản lý, gia hạn khi phù hợp, phát sự kiện vòng đời và có thể yêu cầu secret mới theo chiến lược *rotation*.

Các thành phần đáng biết:

| Thành phần | Trách nhiệm |
| --- | --- |
| `SecretLeaseContainer` | Theo dõi secret được đăng ký và lập lịch renew/rotation |
| `RequestedSecret` | Mô tả path và chế độ quản lý lease |
| `Lease` | Metadata ID, duration, renewable theo mô hình Spring Vault |
| `LeaseListener` | Nhận sự kiện lease được tạo, renew, expired hoặc rotated |
| `LeaseErrorListener` | Nhận lỗi trong quá trình tương tác với Vault |
| `TaskScheduler` | Thực hiện công việc renew/rotation theo lịch |

Ví dụ cấu trúc từ API Spring Vault; code cần scheduler được cấu hình theo lifecycle của ứng dụng:

~~~java
import org.springframework.scheduling.TaskScheduler;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;

public class LeaseSetup {

    public SecretLeaseContainer create(
            VaultOperations vault,
            TaskScheduler scheduler) {

        SecretLeaseContainer container =
                new SecretLeaseContainer(vault, scheduler);

        RequestedSecret requested =
                container.requestRotatingSecret(
                        "database/creds/readonly");

        // Có thể gắn LeaseListener/LeaseErrorListener cho requested
        // để cập nhật connection pool và theo dõi sự kiện an toàn.
        container.afterPropertiesSet();
        container.start();

        return container;
    }
}
~~~

**Không dừng ở bước “container tự gia hạn”.** Với database connection pool, khi secret **được rotate**, ứng dụng phải chuẩn bị pool/credential mới, chuyển lưu lượng, đóng các connection cũ theo chiến lược phù hợp. Nếu container vẫn nhận sự kiện expired muộn hơn thời điểm Vault hết hạn do độ trễ scheduling, việc chỉ nghe event không bảo đảm credential luôn dùng được.

`SimpleSessionManager`/`LifecycleAwareSessionManager` quản lý **token xác thực** ở mức session; `SecretLeaseContainer` quản lý **vòng đời secret lease**. Dùng session manager có khả năng renew token **không thay thế** quản lý lease cho tài khoản database động.

## 10. Ma trận kiểm thử `lease_id`, TTL và renewable

| Tình huống | Dữ liệu kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Dynamic secret được cấp thành công | `lease_id` không rỗng, TTL dương | Có thông tin để theo dõi lease |
| Đọc KV v2 tĩnh | `lease_id` rỗng/không có | Không gọi renew secret lease dựa vào kết quả KV |
| Lease `renewable=true` | Renew trước khi hết hạn và có quyền | Vault có thể cho phép; đọc TTL mới thực tế |
| Renew yêu cầu 30 phút | `increment=1800` | TTL mới tính từ thời điểm renew, không cộng vào thời hạn cũ |
| Lease `renewable=false` | TTL vẫn dương | Dùng đến hạn; chuẩn bị credential mới |
| Lease đã hết hạn | Lookup/renew với ID cũ | Không còn lease hợp lệ để renew; phải xin secret mới |
| Lease bị revoke | Revoke một ID cụ thể | Credential bị thu hồi theo khả năng backend; kiểm tra ở hệ thống đích |
| Caller thiếu quyền lease management | Renew/lookup API | Có thể trả 403, không kết luận lease không tồn tại |
| Token của workload hết hạn | Yêu cầu gọi Vault tiếp theo | Có thể bị từ chối dù secret lease còn thời hạn |
| Database plugin không thu hồi được | Vault revoke/expiry | Có lỗi vận hành cần quan sát và xử lý, có thể có irrevocable lease |

**Trường hợp phản ví dụ:** một test chỉ kiểm tra `renewable=true` rồi mặc định gia hạn thành công là sai. Một test chỉ nhìn `lease_duration=3600` sau khi đã chờ hơn một giờ cũng không chứng minh credential còn sống. Cần kết hợp thời gian thực, phản hồi Vault và thử xác thực ở backend thử nghiệm khi an toàn.

## 11. Xử lý lỗi và giám sát

Đối với hệ thống thực tế, theo dõi tối thiểu các tín hiệu:

1. **Lease sắp hết hạn:** thời gian còn lại theo quan sát gần nhất, thời điểm dự kiến renew/rotate và khoảng đệm.
2. **Renew thất bại:** status của Vault, khả năng retry, policy và tính hợp lệ của token.
3. **Rotation thất bại:** không tạo được secret mới, không cập nhật được connection pool hoặc kết nối cũ chưa đóng.
4. **Revocation thất bại:** Vault/database plugin không dọn được credential, cần phối hợp vận hành.
5. **Token authentication lỗi:** phân biệt token hết hạn/không có ACL với lease của secret; tránh lặp retry vô hạn.
6. **Khả năng truy cập Vault và backend:** lỗi mạng, TLS, seal state, database không kết nối được, quota và scheduler.

Log nên ghi loại thao tác, tên secrets engine/role, mã lỗi, request correlation ID và metric đã giảm thông tin nhạy cảm. Tránh ghi **giá trị secret**, Vault token, username/password, hoặc toàn bộ `VaultResponse`; cũng hạn chế phát tán `lease_id` ra hệ thống log có quyền truy cập rộng.

Trong môi trường production, thiết kế hành vi *fail closed* khi credential hết hạn: không fallback sang account đặc quyền cao hay giữ credential đã bị revoke để cố kết nối. Kế hoạch luân chuyển và cleanup nên được thử bằng test tích hợp trước khi triển khai.

## 12. Câu hỏi tự kiểm tra

1. Vault trả `lease_id = "database/creds/readonly/abc"`, `lease_duration = 900`, `renewable = true`. Những điều gì ứng dụng **biết chắc** và điều gì chưa chắc?
2. Lúc 10:00, Vault cấp lease TTL 60 phút. Lúc 10:40, yêu cầu renew với `increment=20m` được Vault chấp thuận và trả TTL 20 phút. Thời điểm hết hạn dự kiến mới là lúc nào?
3. Một secret KV v2 trả dữ liệu và metadata có `lease_duration`, nhưng `lease_id` rỗng. Có nên gọi `vault lease renew` không?
4. Vì sao token còn hạn và `renewable=true` trên secret không bảo đảm gia hạn thành công mãi?
5. Nếu renewal thất bại vì max TTL, ứng dụng dùng credential database hiện có nên làm gì trước thời điểm hết hạn?
6. Nếu `vault lease revoke` trả lỗi do database không kết nối được, có thể kết luận credential đã bị xóa ở database chưa?
7. Trong Spring Vault, những lớp nào quản lý token xác thực và những lớp nào quản lý dynamic secret lease?

**Gợi ý đáp án:** (1) Có ID, TTL lúc trả response và khả năng *đề nghị* renew; chưa biết renew có được chấp thuận hay backend có thu hồi thành công. (2) Khoảng **11:00**, do increment tính từ 10:40. (3) Không; KV tĩnh thường không có lease động. (4) Còn giới hạn max TTL, trạng thái lease, quyền, plugin và hạ tầng. (5) Lấy credential mới, chuyển kết nối có kiểm soát trước hạn. (6) Không; phải kiểm tra trạng thái revocation thực tế. (7) Session manager/token authentication là một lớp, `SecretLeaseContainer` là lớp quản lý secret lease.

## 13. Tài liệu tham khảo và tiêu chí hoàn thành

**Tài liệu chính thức:**

- [HashiCorp Vault — Lease, renew and revoke](https://developer.hashicorp.com/vault/docs/concepts/lease)
- [HashiCorp Vault — /sys/leases HTTP API](https://developer.hashicorp.com/vault/api-docs/system/leases)
- [HashiCorp Vault — lệnh vault lease](https://developer.hashicorp.com/vault/docs/commands/lease)
- [HashiCorp Vault — quản lý lease của database dynamic credentials](https://developer.hashicorp.com/vault/tutorials/db-credentials/manage-dynamic-leases)
- [Spring Vault — VaultResponse API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultResponse.html)
- [Spring Vault — Lease API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/domain/Lease.html)
- [Spring Vault — SecretLeaseContainer API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html)
- [Spring Vault — Credentials Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)

Bài học đạt mục tiêu khi bạn phân biệt được **`lease_id`**, **TTL theo giây** và **`renewable`**, xác định được khi nào không có lease thực, đọc đúng thời hạn còn lại sau renew, và giải thích phương án **gia hạn, thay credential hoặc revoke** cho secret động. Trong ứng dụng Java, quản lý vòng đời lease cần một chiến lược riêng bên cạnh việc quản lý Vault token và chính sách ACL của workload.
