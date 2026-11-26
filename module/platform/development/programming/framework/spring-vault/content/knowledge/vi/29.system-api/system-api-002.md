# Đọc trạng thái health, initialized và seal

## 1. Bối cảnh: khi nào Vault thực sự sẵn sàng?

Trong **Spring Vault**, ứng dụng Java thường truy cập HashiCorp Vault qua `VaultTemplate` (giao diện `VaultOperations`) để lấy KV secrets, sử dụng Transit, xin chứng thư PKI hoặc làm việc với token và lease. Các thao tác đó phụ thuộc vào việc Vault đã được khởi tạo, mở khóa (*unsealed*), có node phục vụ request và kết nối đến Vault hoạt động bình thường. Xác thực theo workload và Vault policy quyết định ứng dụng được gọi API nào; chúng không tự biến một Vault đang sealed thành sẵn sàng.

Ví dụ: dịch vụ `orders` khởi động trong Kubernetes. Nếu Vault chưa initialized, đang sealed sau restart hoặc node standby không liên lạc được leader, đọc `secret/data/orders` có thể thất bại mặc dù cổng TCP 8200 vẫn mở. Hệ thống vận hành cần phân biệt:

- **`initialized`**: kho lưu trữ Vault đã được thiết lập vật liệu khóa ban đầu và cấu trúc cần thiết hay chưa.
- **`sealed`**: Vault hiện đã mở khóa để thực hiện thao tác mật mã và xử lý secret hay chưa.
- **Health/node role**: node hiện active, standby, performance standby, DR secondary, bị loại khỏi cụm hay đang gặp lỗi HA.
- **Khả năng phục vụ yêu cầu nghiệp vụ**: ngoài ba điều trên còn phụ thuộc TLS, mạng, workload authentication, policy, mount path, tình trạng của secret engine và dịch vụ phụ thuộc.

Bài này tập trung vào ba API **chỉ đọc** thuộc System Backend: `GET/HEAD /v1/sys/health`, `GET /v1/sys/init` và `GET /v1/sys/seal-status`. Bạn sẽ đọc chúng bằng HTTP/CLI, dùng Spring Vault để truy vấn thông tin tương ứng, phân loại phản hồi và thiết kế health probe đúng mục đích.

> **Kết quả cần đạt:** Nhìn vào trạng thái thực tế để trả lời “Vault đã khởi tạo chưa?”, “Vault có bị sealed không?”, “Node này ở vai trò nào?”, và “Load balancer/monitoring có nên định tuyến request tới đây hay không?” mà không phát sinh thao tác quản trị nguy hiểm.

## 2. Mô hình trạng thái: ba câu hỏi khác nhau

### 2.1. `initialized` không đồng nghĩa với `unsealed`

Một Vault mới chưa được thiết lập thường ở trạng thái `initialized=false`. Thao tác **khởi tạo** tạo vật liệu khóa và dữ liệu nền tảng cho Vault. Với hệ thống tự quản lý, đây là công việc provisioning có kiểm soát, thông thường chỉ thực hiện một lần trên storage backend mới.

Sau khi đã initialized, Vault vẫn có thể ở trạng thái **sealed**, chẳng hạn lúc khởi động lại hoặc khi không thể sử dụng backend Auto Unseal. Trạng thái sealed ngăn xử lý phần lớn API nghiệp vụ. Phải hoàn thành quy trình **unseal** tương ứng với cơ chế seal đã cấu hình, hoặc chờ Auto Unseal hoạt động, mới có thể phục vụ secrets.

~~~mermaid
stateDiagram-v2
    [*] --> ChuaKhoiTao
    ChuaKhoiTao: initialized=false
    ChuaKhoiTao --> DaKhoiTaoDangSeal: Khởi tạo Vault (admin)
    DaKhoiTaoDangSeal: initialized=true / sealed=true
    DaKhoiTaoDangSeal --> DaMoKhoa: Unseal hoặc Auto Unseal
    DaMoKhoa: initialized=true / sealed=false
    DaMoKhoa --> DaKhoiTaoDangSeal: Seal hoặc restart cần unseal
~~~

Sơ đồ mô tả chuyển trạng thái khái niệm. Vault dùng **Shamir seal**, **Auto Unseal** và tùy chọn triển khai khác nhau có quy trình quản lý khóa riêng. Không suy từ `sealed=true` rằng cần gọi API unseal bằng recovery key; recovery key trong một số cấu hình Auto Unseal không có vai trò giống unseal key của Shamir.

### 2.2. `unsealed` cũng chưa đủ kết luận node active

Trong chế độ HA, nhiều node có thể `initialized=true` và `sealed=false`, nhưng **chỉ node active** xử lý vai trò leader; node standby bình thường có thể chuyển tiếp một số request đến active. Với Vault Enterprise, performance standby có khả năng phục vụ một số luồng đọc, còn DR secondary phục vụ mục tiêu sao chép/khôi phục và không tương đương active của primary.

| initialized | sealed | Vai trò/điều kiện bổ sung | Đánh giá |
| --- | --- | --- | --- |
| `false` | Thường `true` | Chưa có dữ liệu khởi tạo | Chưa sẵn sàng; cần quy trình provisioning |
| `true` | `true` | Dù leader/standby trước đó là gì | Chưa phục vụ secret; cần xử lý seal |
| `true` | `false` | Active | Có thể phục vụ yêu cầu nếu mạng, auth, policy và secrets engine bình thường |
| `true` | `false` | Standby | Có thể chuyển tiếp request; tính phù hợp phụ thuộc định tuyến/HA |
| `true` | `false` | Performance standby | Có khả năng xử lý một số request; cần chọn health policy đúng |
| `true` | `false` | DR secondary | Vai trò DR; không đưa vào pool ghi của primary |
| Không xác định | Không xác định | Lỗi TLS, mạng hoặc proxy | **Unknown**; không được giả định là healthy |

Đừng để `initialized`, `sealed` và `standby` thành một biến Boolean chung “Vault khỏe”: từng tín hiệu phản ánh một lớp của hệ thống.

## 3. Ba endpoint chỉ đọc và mục đích sử dụng

| HTTP method | Đường dẫn | Nội dung trả về | Mục đích |
| --- | --- | --- | --- |
| `GET /v1/sys/health` | System health | HTTP status + JSON chứa `initialized`, `sealed`, `standby`, thông tin node/cluster | Phân loại sức khỏe node, HA, load balancer, cảnh báo |
| `HEAD /v1/sys/health` | System health | Chỉ HTTP status, **không có body JSON** | Probe gọn nhẹ khi chỉ cần mã trạng thái |
| `GET /v1/sys/init` | Initialization status | `{"initialized": true/false}` | Xác định Vault đã được initialized hay chưa |
| `GET /v1/sys/seal-status` | Seal status | JSON gồm `initialized`, `sealed`, thông tin seal/unseal | Chẩn đoán seal và tiến độ unseal |

Các endpoint đọc trạng thái này có thể được gọi **không cần Vault token** theo cơ chế công khai của Vault. Tuy nhiên, `sys/health` và `sys/init` có yêu cầu truy cập qua **root namespace** theo tài liệu API hiện hành; môi trường Vault Enterprise dùng namespace cần đặt đường dẫn/client đúng theo cấu hình của tổ chức. Việc “không cần token” **không có nghĩa nên công khai endpoint lên Internet**. Áp dụng HTTPS, xác minh CA, mạng giám sát giới hạn và endpoint của node đúng mục tiêu.

**Phân biệt method:** `GET /sys/init` là đọc trạng thái, còn `POST /sys/init` là thao tác **khởi tạo Vault**, có tác dụng rất khác. Tương tự, `GET /sys/seal-status` chỉ quan sát, còn `PUT /sys/seal` hoặc `POST /sys/unseal` thay đổi trạng thái và cần quy trình quản trị riêng. Health probe chỉ sử dụng các method đọc.

## 4. Đọc `GET/HEAD /sys/health`

### 4.1. Mã HTTP mặc định và ý nghĩa

Khác với API chỉ trả 200 khi mọi thứ bình thường, `sys/health` cố ý dùng các mã phản ánh trạng thái node. Theo tài liệu Vault, mặc định:

| Mã HTTP | Ý nghĩa | Gợi ý diễn giải |
| --- | --- | --- |
| **200** | Initialized, unsealed, **active** | Active khỏe ở mức Vault health |
| **429** | Unsealed, **standby** | Không tự động coi là lỗi rate limit; node standby, cần kiểm tra có phục vụ qua HA forwarding không |
| **472** | **DR secondary** | Node thuộc site DR secondary; không đồng nghĩa active của primary |
| **473** | **Performance standby** | Có thể đủ điều kiện nhận một số loại request tùy kiến trúc |
| **474** | Standby không kết nối được active | Lỗi HA đáng chú ý; không giả định forwarding hoạt động |
| **501** | Vault **chưa initialized** | Cần người quản trị xử lý khởi tạo |
| **503** | Vault **sealed** | API nghiệp vụ chưa sẵn sàng; cần xử lý seal/backend |
| **530** | Node bị **removed** khỏi HA cluster | Không đưa node vào pool xử lý bình thường |

Trong một số thời điểm cluster biến động, node ở DR secondary hoặc performance standby cũng có thể trả `429`. Đừng xây dựng logic khẳng định vai trò node chỉ dựa trên một lần đọc duy nhất. Mã có thể bị **tùy chỉnh bởi tham số query**, nên hệ thống giám sát phải cố định URL/mã mong đợi và ưu tiên phân tích JSON nếu muốn chi tiết.

### 4.2. Ví dụ HTTP và JSON

~~~http
GET /v1/sys/health HTTP/1.1
Host: vault-node-1.internal:8200
Accept: application/json
~~~

Phản hồi minh họa cho node active:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "initialized": true,
  "sealed": false,
  "standby": false,
  "performance_standby": false,
  "replication_dr_mode": "disabled",
  "replication_performance_mode": "disabled",
  "server_time_utc": 1709559327,
  "version": "1.16.0",
  "cluster_name": "vault-demo",
  "cluster_id": "11111111-2222-3333-4444-555555555555"
}
~~~

Đây là **dữ liệu minh họa**, không phải output của Vault thật trong dự án. Các trường xuất hiện phụ thuộc bản Vault, Enterprise/Community, trạng thái node và cấu hình. Ví dụ, standby có thể có `ha_connection_healthy` và `last_request_forwarding_heartbeat_ms`; bản Enterprise có thêm thông tin replication. Không nên viết parser bắt buộc mọi trường tùy chọn đều có mặt.

Nếu chỉ muốn kiểm tra mã:

~~~http
HEAD /v1/sys/health HTTP/1.1
Host: vault-node-1.internal:8200
~~~

`HEAD` không trả JSON body. Dùng `GET` khi cần phân tích `initialized`, `sealed`, `standby` hoặc các trường cảnh báo HA.

### 4.3. Tham số query để điều chỉnh health probe

Vault hỗ trợ tùy chỉnh mã phản hồi trên đúng request:

| Tham số | Mặc định | Tác dụng |
| --- | --- | --- |
| `standbyok=true` | `false` | Cho standby thường trả mã của active thay vì `429`; không áp dụng cho performance standby |
| `perfstandbyok=true` | `false` | Cho performance standby trả mã của active thay vì `473` |
| `activecode=<int>` | `200` | Mã cho active |
| `standbycode=<int>` | `429` | Mã cho standby |
| `drsecondarycode=<int>` | `472` | Mã cho DR secondary |
| `performancestandbycode=<int>` | `473` | Mã cho performance standby |
| `haunhealthycode=<int>` | `474` | Mã khi standby không liên lạc active |
| `sealedcode=<int>` | `503` | Mã khi sealed |
| `uninitcode=<int>` | `501` | Mã khi chưa initialized |
| `removedcode=<int>` | `530` | Mã khi node đã bị loại khỏi cluster |

Ví dụ:

~~~bash
# Có thể chấp nhận standby thường cho một pool có hỗ trợ forwarding.
curl -sS -i \
  "$VAULT_ADDR/v1/sys/health?standbyok=true"

# Chấp nhận performance standby theo thiết kế pool đọc phù hợp.
curl -sS -i \
  "$VAULT_ADDR/v1/sys/health?perfstandbyok=true"
~~~

**Thay đổi status code không thay đổi năng lực node.** Nếu đặt `standbyok=true`, mã `200` không làm standby trở thành active; nếu DR secondary vẫn `472` thì cũng không nên ép nó thành 200 chỉ để load balancer xanh. Hãy chọn probe theo loại traffic và topology cụm, không điều chỉnh tất cả mã để “đạt 200”.

### 4.4. Một mã `429` có thể mang nhiều ý nghĩa

Ở endpoint `/sys/health`, `429` mặc định biểu thị **standby**. Trong các API Vault khác, `429` cũng có thể liên quan tới quota hoặc số lượng request. Khi chẩn đoán cần ghi **endpoint + HTTP method + mã + body (đã làm sạch)**. Bộ xử lý lỗi chung không nên tự động coi mọi `429` từ Vault là “Too Many Requests” để backoff như rate limiting.

Cùng nguyên tắc, một `503` từ `/sys/health` thường là sealed, nhưng `503` ở API khác có thể là lỗi tạm thời, quá tải hoặc bảo trì. Mã mà proxy phía trước trả cũng không nhất thiết có JSON health chuẩn.

## 5. Đọc `GET /sys/init`: Vault đã initialized chưa?

~~~http
GET /v1/sys/init HTTP/1.1
Host: vault-node-1.internal:8200
Accept: application/json
~~~

Phản hồi ví dụ:

~~~json
{
  "initialized": true
}
~~~

`initialized=true` chứng minh storage Vault đã qua bước khởi tạo. Nó **không bảo đảm** node đang unsealed, có active leader, có đủ workload policy hoặc các secrets engine đang hoạt động. `initialized=false` xảy ra khi Vault chưa được khởi tạo trên storage mà node đang nhìn thấy. Với môi trường dự kiến đã vận hành, đây là tín hiệu cần cảnh báo và kiểm tra lại cấu hình storage/mount; không tự động chạy initialize trong ứng dụng.

**Đặc biệt quan trọng với triển khai HA:** nhiều node cùng dùng một backend storage đồng bộ; thao tác initialize không phải công việc cần lặp riêng trên từng pod. Nếu ứng dụng nhận `initialized=false` trong cluster production đã từng hoạt động, có thể là sai storage backend/namespace hoặc cấu hình deployment — phải điều tra, **không tự tạo hệ Vault mới** trên storage nhầm.

CLI hoặc HTTP:

~~~bash
# Trả đúng một boolean quan trọng, không thao tác tạo khóa.
curl -sS "$VAULT_ADDR/v1/sys/init" | jq -r '.initialized'
~~~

Trong Spring Vault, thao tác tương đương là `vaultOperations.opsForSys().isInitialized()`.

## 6. Đọc `GET /sys/seal-status`: Vault đang sealed không?

~~~http
GET /v1/sys/seal-status HTTP/1.1
Host: vault-node-1.internal:8200
Accept: application/json
~~~

Phản hồi minh họa của một node **đang sealed** dùng Shamir seal:

~~~json
{
  "initialized": true,
  "sealed": true,
  "type": "shamir",
  "t": 2,
  "n": 3,
  "progress": 1,
  "nonce": "<session-unseal-nonce>",
  "migration": false,
  "recovery_seal": false,
  "storage_type": "raft",
  "version": "1.19.0"
}
~~~

| Trường | Ý nghĩa | Diễn giải đúng |
| --- | --- | --- |
| `initialized` | Vault đã khởi tạo | Có thể true ngay cả khi sealed |
| `sealed` | Node còn đang khóa hay đã mở khóa | `true`: chưa thể phục vụ phần lớn API secrets |
| `type` | Cơ chế seal đang cấu hình | Ví dụ `shamir`, loại Auto Unseal cụ thể; ảnh hưởng quy trình vận hành |
| `t` | Ngưỡng số key shares liên quan đến seal | Không phải TTL, không phải số node cần chạy |
| `n` | Tổng số shares cấu hình | Không được lấy shares từ endpoint này; chỉ có metadata |
| `progress` | Số key shares đã được cung cấp trong lần unseal hiện tại (với Shamir) | Dùng chẩn đoán tiến độ; không yêu cầu unseal qua monitor |
| `nonce` | Giá trị định danh phiên unseal nếu có | Không phải unseal key |
| `migration` | Trạng thái liên quan quá trình chuyển seal | Cần quy trình quản trị khi đang migration |
| `recovery_seal` | Metadata về chế độ seal/recovery | Không suy recovery key luôn dùng để unseal |
| `storage_type` | Loại backend lưu trữ | Ví dụ `raft`; hữu ích khi chẩn đoán môi trường |
| `version`, `cluster_id`, `cluster_name` | Metadata node/cluster nếu có | Hữu ích kiểm tra đang kết nối đúng cluster |

Các trường có thể thay đổi theo phiên bản Vault, cơ chế seal và trạng thái initialized. Với **Auto Unseal**, giá trị `n`/`t` hoặc recovery key có thể thể hiện mô hình quản lý recovery key, nên **không được suy cách unseal thủ công** chỉ bằng một mẫu JSON. Liên hệ runbook của nền tảng trước khi can thiệp.

Với node **đã unsealed** thường có:

~~~json
{
  "initialized": true,
  "sealed": false,
  "type": "shamir",
  "t": 2,
  "n": 3,
  "progress": 0,
  "nonce": "",
  "storage_type": "raft"
}
~~~

`sealed=false` là tín hiệu node có thể xử lý giao dịch Vault về mặt seal, nhưng vẫn cần `health` để biết HA role/khả năng forward, và kiểm tra đường mạng/auth khi workload thực sự gọi secret.

## 7. Thực hành đọc trạng thái bằng CLI và HTTP

### 7.1. Chuẩn bị

Bài tập giả định `VAULT_ADDR` trỏ đến **một node Vault thử nghiệm hoặc endpoint được phép giám sát**, kết nối dùng HTTPS và CA hợp lệ. Không dùng `curl -k` để bỏ qua xác minh certificate; nếu Vault dùng CA nội bộ, cấu hình `VAULT_CACERT` hoặc `CURL_CA_BUNDLE` đúng theo hướng dẫn quản trị.

~~~bash
# Ví dụ shell Bash; thay bằng địa chỉ test của bạn.
export VAULT_ADDR="https://vault-node-1.internal:8200"
export CURL_CA_BUNDLE="/path/to/approved-vault-ca.pem"
~~~

### 7.2. Ba lệnh đọc tương ứng

~~~bash
# 1) Xem health: -i hiện cả status line và header.
# KHÔNG dùng -f / --fail ở ví dụ này vì 429/501/503 là tín hiệu cần đọc.
curl -sS -i "$VAULT_ADDR/v1/sys/health"

# Chỉ kiểm tra status, không cần body (HEAD).
curl -sS -I "$VAULT_ADDR/v1/sys/health"

# 2) Kiểm tra initialized.
curl -sS "$VAULT_ADDR/v1/sys/init" \
  | jq '{initialized}'

# 3) Kiểm tra seal.
curl -sS "$VAULT_ADDR/v1/sys/seal-status" \
  | jq '{initialized, sealed, type, t, n, progress, storage_type}'
~~~

Lệnh trên được phép đọc trạng thái mà không cần cung cấp root token. Trong một số môi trường, reverse proxy, network policy hoặc Vault namespace có thể hạn chế đường truy cập; cần sử dụng endpoint monitoring được quản trị viên phê duyệt.

### 7.3. Đối chiếu với `vault status`

~~~bash
vault status
~~~

CLI này tóm tắt nhiều thông tin seal và HA: `Initialized`, `Sealed`, `Seal Type`, `HA Mode`, `Storage Type`, phiên bản/cluster nếu có. Mã thoát của `vault status` có ý nghĩa: **0 = unsealed**, **2 = sealed**, **1 = lỗi**. Script giám sát không nên coi mọi exit code khác 0 là cùng một sự cố.

Lưu ý `vault status` không thay thế hoàn toàn `/sys/health`: CLI thường tập trung vào seal và thông tin cluster, còn HTTP health code thuận tiện cho load balancer và phân loại standby/performance standby/DR.

## 8. Đọc trong Java bằng `VaultTemplate` / `VaultSysOperations`

### 8.1. API Spring Vault cung cấp sẵn

Trong Spring Vault, lấy `VaultSysOperations` từ `VaultOperations.opsForSys()`. Ba phương thức quan trọng:

| Spring Vault | Kiểu trả về | Đối chiếu API |
| --- | --- | --- |
| `opsForSys().isInitialized()` | `boolean` | `GET /sys/init` |
| `opsForSys().getUnsealStatus()` | `VaultUnsealStatus` | Thông tin seal/unseal, cùng mục đích đọc seal status |
| `opsForSys().health()` | `VaultHealth` | `GET /sys/health` |

`VaultHealth` cung cấp `isInitialized()`, `isSealed()`, `isStandby()`, `isPerformanceStandby()`, `isRecoveryReplicationSecondary()`, `getVersion()` và `getServerTimeUtc()`. `VaultUnsealStatus` cung cấp `isSealed()`, `getSecretShares()`, `getSecretThreshold()`, `getProgress()`.

Tên method cần chính xác: **`getUnsealStatus()`** là đọc trạng thái, còn **`unseal(String keyShare)`**, **`seal()`**, **`initialize(...)`** là thao tác thay đổi trạng thái. Dịch vụ chỉ cần giám sát tuyệt đối không được gọi nhầm các method có tác dụng quản trị.

### 8.2. Ví dụ Java: đọc metadata hệ thống

Ví dụ Java 17+ sau giả định `VaultOperations` đã được tạo bằng `VaultTemplate` và cấu hình endpoint/TLS xác minh CA. Nó không dùng root token hay triển khai chức năng initialize/seal:

~~~java
import java.util.Objects;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultSysOperations;
import org.springframework.vault.support.VaultHealth;
import org.springframework.vault.support.VaultUnsealStatus;

public final class VaultSystemStatusReader {

    private final VaultSysOperations sys;

    public VaultSystemStatusReader(VaultOperations vaultOperations) {
        this.sys = Objects.requireNonNull(vaultOperations).opsForSys();
    }

    public SystemSnapshot read() {
        boolean initialized = sys.isInitialized();
        VaultUnsealStatus unseal = sys.getUnsealStatus();

        boolean sealed = unseal.isSealed();

        // Health chỉ đọc thêm khi Vault đã khởi tạo/mở khóa.
        // Non-2xx từ một số health states có thể khiến client throw.
        if (!initialized || sealed) {
            return new SystemSnapshot(
                    initialized, sealed, null, null, null);
        }

        VaultHealth health = sys.health();
        return new SystemSnapshot(
                initialized,
                sealed,
                health.isStandby(),
                health.isPerformanceStandby(),
                health.getVersion());
    }

    public record SystemSnapshot(
            boolean initialized,
            boolean sealed,
            Boolean standby,
            Boolean performanceStandby,
            String version) {
    }
}
~~~

**Cách đọc kết quả:**

- `initialized=false` cho biết cần xử lý provisioning/storage; `sealed=true` cho biết node chưa sẵn sàng phục vụ secrets.
- `standby=null` trong record nghĩa là **chưa đọc health role**, không phải `standby=false`.
- Khi `initialized=true` và `sealed=false`, code mới gọi `sys.health()` để lấy role. Tuy nhiên, một số client/môi trường có thể xem các HTTP code như `429`/`472`/`473` là lỗi và **ném ngoại lệ** trước khi map `VaultHealth`. Bởi vậy, đoạn code phù hợp cho chẩn đoán đơn giản; muốn phân loại chính xác mọi mã health, dùng HTTP status probe như mục kế tiếp.

Cũng cần bắt lỗi mạng/TLS, `VaultException` hoặc timeout ở tầng gọi để xuất trạng thái **UNKNOWN**, không tự trả `initialized=false` hoặc `sealed=true` khi thực tế chỉ mất kết nối. Khi triển khai thành actuator health indicator, tránh biến ngoại lệ thành “Vault đang sealed” vì sẽ che mất nguyên nhân.

### 8.3. Khi cần giữ nguyên mã HTTP non-2xx

`VaultSysOperations.health()` là API cấp cao tiện lợi, nhưng một health monitor chuyên biệt cần phân biệt **429 standby**, **472 DR**, **473 performance standby**, **474 HA lỗi**, **501 uninitialized**, **503 sealed** và **530 removed**. Dùng một HTTP client riêng của JDK để đọc status mà không phụ thuộc exception mapping của SDK; kết nối này cũng có thể không cần Vault token.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class VaultHealthHttpProbe {

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    // baseUri là URL node được cấu hình đáng tin cậy.
    // Ví dụ URI.create("https://vault-node-1.internal:8200/").
    public HealthResult probe(URI baseUri)
            throws IOException, InterruptedException {

        URI healthUri = baseUri.resolve("/v1/sys/health");

        HttpRequest request = HttpRequest.newBuilder(healthUri)
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        // Không tự gọi getBody trong ví dụ chỉ cần mã HTTP.
        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        int status = response.statusCode();
        String state = switch (status) {
            case 200 -> "ACTIVE";
            case 429 -> "STANDBY";
            case 472 -> "DR_SECONDARY";
            case 473 -> "PERFORMANCE_STANDBY";
            case 474 -> "HA_UNHEALTHY";
            case 501 -> "UNINITIALIZED";
            case 503 -> "SEALED";
            case 530 -> "REMOVED";
            default -> "UNKNOWN";
        };
        return new HealthResult(status, state);
    }

    public record HealthResult(int httpStatus, String state) {}
}
~~~

**Giới hạn của mẫu:** Trạng thái được suy từ **các mã mặc định** của `/sys/health`. Nếu URL dùng `standbyok=true` hoặc override `activecode`/`sealedcode`, bảng mapping phải thay theo hợp đồng probe. Mã `UNKNOWN` gồm cả lỗi reverse proxy hoặc response không mong đợi; không tự xem là active. Mã này không parse JSON, nên muốn xác minh cờ `initialized`/`sealed`/`standby` vẫn cần `GET` lấy body và đối chiếu khi cần. Cấu hình hostname, TLS trust và timeout là trách nhiệm của môi trường triển khai.

**Không cho phép người dùng bên ngoài tự cung cấp `baseUri`:** code dùng client tin cậy truy cập host Vault. Nếu URL nguồn không được kiểm soát, nó có thể thành điểm truy cập mạng nội bộ trái phép (SSRF). Khi dùng URI của node, nên có danh sách địa chỉ được chấp thuận và cấu hình TLS đúng CA.

### 8.4. Dùng trong Spring Boot Actuator một cách hợp lý

Một ứng dụng Spring Boot có thể công bố chỉ số `vault_dependency_reachable`, `vault_initialized`, `vault_sealed`, `vault_node_role`, thời gian phản hồi và số lần lỗi liên tiếp qua metrics hoặc HealthIndicator. Tách rõ:

- **Liveness của chính ứng dụng**: tiến trình Java còn chạy và có thể tiếp tục hoạt động; thông thường **không phụ thuộc trực tiếp** việc Vault đang down, để tránh vòng lặp restart hàng loạt.
- **Readiness của ứng dụng**: có thể phụ thuộc Vault nếu dịch vụ phải lấy secret mới để xử lý traffic; nhưng nếu đang có token/secret đã cache hợp lệ, quy tắc readiness phải phản ánh khả năng phục vụ thực tế.
- **Health của node Vault cho load balancer**: dùng HTTP `/sys/health` trực tiếp với chính sách active/standby/perf standby/DR thích hợp.

Không nên đặt một lời gọi Vault blocking và timeout dài vào mỗi lần kiểm tra liveness của Kubernetes. Nếu cần polling, đặt interval, jitter, timeout và caching ngắn phù hợp; health probe lỗi phải tạo tín hiệu giám sát rõ, không lặp login/renew token vô hạn.

## 9. Thiết kế health check cho HA và load balancer

### 9.1. Chọn tiêu chí trước khi chọn URL

Một topology minh họa:

~~~text
                     Load Balancer
                    /      |      \
                   v       v       v
              Vault A   Vault B   Vault C
              ACTIVE    STANDBY   STANDBY
                200       429       429

       /v1/sys/health (mặc định): node A đủ điều kiện
       /v1/sys/health?standbyok=true: có thể chấp nhận B/C
       khi request forwarding và topology cho phép
~~~

| Mục tiêu | Chiến lược cân nhắc | Vì sao |
| --- | --- | --- |
| Pool chỉ nhận active leader | `/v1/sys/health` mặc định, kỳ vọng `200` | Tránh gửi request trực tiếp tới standby |
| Pool được thiết kế cho standby forwarding | `?standbyok=true` hoặc quy tắc mã riêng | Cho standby hợp lệ vào pool sau khi đã kiểm chứng forwarding |
| Pool chấp nhận Enterprise performance standby | `?perfstandbyok=true` nếu request tương thích | Không đồng nhất performance standby với active cho mọi thao tác |
| DR site nhận traffic sau failover có kiểm soát | Health check riêng và quy trình DR | `472` không phải dấu hiệu site DR được phép phục vụ production write |
| Health monitoring/alert | Giữ mã mặc định và đọc GET JSON | Phân biệt role, sealed, initialized, HA degraded và removed |

Một node standby có thể trả `429` nhưng vẫn là thành viên cluster **hoạt động bình thường**. Ngược lại, nếu `ha_connection_healthy=false` hoặc `474`, không nên kỳ vọng node chuyển tiếp được. Bởi vậy cần phân biệt “node không phải active” với “node bị lỗi”.

### 9.2. Không gom mọi node vào một probe duy nhất

Gọi `/sys/health` qua VIP hoặc ingress chỉ chứng minh **đường đó có một đích phản hồi**, có thể bị load balancer chọn node khỏe thay cho node đang lỗi. Khi vận hành HA nên quan sát cả:

- **Node endpoint**: trạng thái từng node, seal, HA connectivity, removed.
- **Client endpoint**: URL mà Spring Vault/workload sử dụng có thể phục vụ request thật.
- **Ứng dụng nghiệp vụ**: xác thực, policy, KV/Transit/PKI và các dependency có thể phục vụ tác vụ cụ thể.

Không đưa cùng tên metric “vault_up” cho ba lớp trên mà không có nhãn phân biệt; sẽ khó xác định hệ thống hỏng ở mạng, seal, HA, token hay secret engine.

## 10. Quyền truy cập, namespace và bảo mật thông tin trạng thái

`GET /sys/health`, `GET /sys/init`, `GET /sys/seal-status` thường không đòi Vault token. **Không cần cấp root policy cho monitoring** chỉ để gọi ba endpoint này. Đối với các API quản trị như initialize, seal, unseal, rotate, mount hay policy changes, sử dụng danh tính và quy trình phê duyệt riêng.

Các điểm cần bảo vệ:

1. **Mạng và TLS**: chỉ mở endpoint monitoring cho load balancer, runtime và hệ thống giám sát được phép; xác thực chứng thư TLS của Vault.
2. **Metadata**: health và seal status có thể tiết lộ phiên bản Vault, cluster ID/name, storage type và kiến trúc HA. Bảo vệ mức truy cập nếu đây là thông tin nội bộ.
3. **Root namespace**: `/sys/health` và `/sys/init` yêu cầu đường API từ root namespace theo API hiện hành; không suy đoán tình trạng hệ thống khi request đang bị gửi sai namespace.
4. **Workload credentials**: API không cần token thì không nên nhúng root token vào health URL, shell script, ConfigMap hoặc dashboard.
5. **Logging**: chỉ ghi status, node ID đã được phê duyệt, thời điểm, latency, trạng thái lỗi. Không in session token, unseal key, recovery key hoặc request header nhạy cảm.
6. **Tách quyền quan sát và thao tác**: monitor chỉ đọc không nên có khả năng gọi `POST /sys/init`, `PUT /sys/seal` hay `POST /sys/unseal`.
7. **Không tự chữa trạng thái nguy hiểm**: nếu `initialized=false` hoặc `sealed=true`, dịch vụ tự động cần báo lỗi rõ và phối hợp runbook, không tự gửi unseal shares hoặc khởi tạo lại storage.

Với Vault Enterprise có namespace, hãy kiểm tra cách cấu hình root/system endpoint và cách ingress xử lý `X-Vault-Namespace`; lỗi namespace có thể khiến client đọc trạng thái khác dự kiến hoặc bị từ chối.

## 11. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách phân biệt/xử lý |
| --- | --- | --- |
| `sys/health` trả `429` | Node standby hợp lệ | Kiểm tra HA và forwarding; không mặc định retry như rate limit |
| `sys/health` trả `472` | DR secondary | Đối chiếu kế hoạch DR, không đưa vào pool primary |
| `sys/health` trả `473` | Enterprise performance standby | Xác minh pool có cho phép traffic qua node này |
| `sys/health` trả `474` | Standby không liên lạc active | Kiểm tra HA networking, leader và request forwarding |
| `sys/health` trả `501` hoặc `sys/init` trả `false` | Chưa initialized, có thể trỏ nhầm storage | Kiểm tra cấu hình backend và triển khai; không chạy initialize tự động |
| `sys/health` trả `503`, `seal-status.sealed=true` | Vault sealed | Xem cơ chế seal, Auto Unseal backend/HSM/KMS, runbook vận hành |
| `sys/health` trả `530` | Node removed khỏi cluster | Không route; kiểm tra việc thay node/cấu hình cụm |
| TCP 8200 mở nhưng API không dùng được | Seal, HA, proxy, policy hoặc session token | Dùng GET health/init/seal, sau đó kiểm tra auth và endpoint thật |
| GET qua load balancer báo `200` nhưng một node lỗi | Load balancer luôn chọn node khỏe | Probe từng node qua địa chỉ nội bộ đã định danh |
| Java `health()` throw trên standby | HTTP non-2xx bị client/SDK chuyển thành exception | Đọc nguyên mã HTTP `/sys/health` khi cần phân loại đầy đủ |
| Request đến `/sys/init` bị 403/404 | Proxy, namespace, network policy hoặc đường URL sai | Kiểm tra root namespace, base URL và HTTP method |
| `curl -f` báo lỗi với health `429/503` | Flag `-f` coi non-2xx là failure và ẩn body | Dùng `curl -i`/`-w`, xử lý mã riêng |
| TLS handshake thất bại | CA/hostname không đúng, cert hết hạn, proxy cấu hình sai | Sửa truststore/endpoint, không dùng `-k` để bỏ qua TLS |
| `vault status` trả exit code `2` | Vault sealed theo quy ước CLI | Phân biệt với exit `1` do lỗi khác |

**Phân biệt ba loại sự cố:** (1) HTTP health trả mã có ý nghĩa về **trạng thái Vault**, (2) HTTP client/transport trả lỗi **kết nối hoặc TLS**, (3) logic gọi secret nghiệp vụ gặp **auth/policy/lease/mount**. Dù biểu hiện cuối đều là ứng dụng không đọc được secret, cách xử lý và người chịu trách nhiệm khác nhau.

## 12. Bài thực hành và kiểm thử tích hợp

Chuẩn bị Vault dev/test cô lập hoặc container kiểm thử và quyền đọc đúng endpoint. Bài học này **không cần** root token và **không yêu cầu** thao tác seal/unseal trên hệ thống dùng thật. Nếu muốn tạo trạng thái sealed/chưa initialized để thử, dùng instance test riêng do người quản trị kiểm soát.

### 12.1. Các bước thực hành

1. Khởi chạy Vault dev/test đã initialized và unsealed. Gọi ba endpoint; mong đợi `/sys/init` trả `true`, `/sys/seal-status` trả `sealed=false`, node active trả `/sys/health` mã `200`.
2. Dùng `HEAD /sys/health`; kiểm tra có HTTP status nhưng không có body.
3. Dùng `GET /sys/health`; so sánh `initialized`/`sealed` với kết quả từ hai API chuyên biệt.
4. Dùng Spring Vault `opsForSys().isInitialized()` và `getUnsealStatus()` để đọc lại các cờ trạng thái. Thử `health()` ở trạng thái active để xem `VaultHealth`.
5. Với topology HA test, query trực tiếp active và standby. Xác minh `429` của standby khác với lỗi mạng; thử `?standbyok=true` trên node standby và quan sát mã thay đổi.
6. Nếu môi trường Enterprise có performance standby hoặc DR secondary, xác nhận `473`/`472` và kiểm tra hành vi khi điều chỉnh query phù hợp. Không tự tạo DR failover chỉ vì bài tập.
7. Mô phỏng thiếu kết nối/TLS không tin cậy và xác minh ứng dụng phân loại **UNKNOWN** thay vì trả initialized=false.
8. Thử client cùng cấu hình sau khi workload token hết hạn: ba API đọc trạng thái vẫn có thể hoạt động, nhưng gọi KV/Transit có thể thất bại do auth. Đừng lấy điều đó làm bằng chứng secret engine khỏe.

### 12.2. Ma trận kiểm thử khuyến nghị

| Trạng thái đầu vào | API/Probe | Kết quả kỳ vọng |
| --- | --- | --- |
| Vault active, initialized, unsealed | `GET /sys/health` | `200` và JSON phù hợp |
| Cùng node active | `GET /sys/init`, `GET /sys/seal-status` | `true`, `sealed=false` |
| Node standby khỏe | `GET /sys/health` mặc định | `429`, không tự map thành lỗi mạng |
| Node standby khỏe với `standbyok=true` | Health URL đã cho phép standby | Có thể trả `200`; vẫn là standby |
| Chưa initialized (test riêng) | `GET /sys/init` | `initialized=false`, không kích hoạt init |
| Sealed (test riêng) | `GET /sys/seal-status` | `sealed=true`, không làm thay đổi seal |
| API health trả 503 hoặc 501 | HTTP client có error handler mặc định | Logic vẫn ghi nhận mã đúng, không nhầm transport error |
| TLS sai CA hoặc timeout | Cả ba API | UNKNOWN/timeout và cảnh báo, không đoán giá trị boolean |
| Root namespace sai hoặc proxy chặn | Health/init | Phân loại là lỗi truy cập, không coi sealed |
| `HEAD /sys/health` | Chỉ đọc mã | Không đòi JSON body |
| DNS/VIP trỏ qua LB | Health trên VIP và từng node | Phân biệt được sức khỏe endpoint tổng và node riêng |

Với kiểm thử Java tự động, nên tách **unit test** cho bảng phân loại mã HTTP khỏi **integration test** với Vault thật. Test unit không cần tạo Vault; integration test kiểm tra parser/SDK thực sự tương thích phiên bản thư viện, chính sách HTTP và môi trường TLS. Không viết test làm thay đổi trạng thái Vault dùng chung chỉ để tạo dữ liệu.

## 13. Checklist vận hành

- [ ] Đã xác định URL là node, VIP hay ingress; hiểu ý nghĩa giám sát của từng điểm.
- [ ] Dùng `GET/HEAD /sys/health` để quan sát mã theo vai trò HA.
- [ ] Dùng `GET /sys/init` để xác định khởi tạo, không gọi `POST /sys/init` trong health probe.
- [ ] Dùng `GET /sys/seal-status` để xác định sealed và metadata seal, không gửi unseal key.
- [ ] Phân biệt initialized, sealed, standby, performance standby và DR secondary.
- [ ] Xử lý đủ các mã `200/429/472/473/474/501/503/530` của health mặc định.
- [ ] Không làm mất mã non-2xx do error handler, proxy hoặc `curl -f`.
- [ ] Chỉ chấp nhận `standbyok`/`perfstandbyok` nếu topology và loại traffic cho phép.
- [ ] Spring Vault gọi đúng `opsForSys().isInitialized()`, `getUnsealStatus()`, `health()`; lỗi kết nối là UNKNOWN.
- [ ] Tách liveness của ứng dụng, readiness theo khả năng phục vụ và health probe node Vault.
- [ ] Giám sát qua HTTPS, CA được phê duyệt và mạng hạn chế; không dùng root token cho API đọc trạng thái.
- [ ] Có cảnh báo/nhật ký sạch về seal, uninitialized, HA loss, timeout, TLS, sai namespace và đường đi client.
- [ ] Runbook xử lý Auto Unseal, storage, HA và incident thuộc nhóm vận hành được ủy quyền.

## Tài liệu tham khảo

- HashiCorp Vault, [`/sys/health` API](https://developer.hashicorp.com/vault/api-docs/system/health) — mã HTTP theo trạng thái HA, GET/HEAD và các query parameters.
- HashiCorp Vault, [`/sys/init` API](https://developer.hashicorp.com/vault/api-docs/system/init) — GET kiểm tra initialized và phân biệt với thao tác initialization.
- HashiCorp Vault, [`/sys/seal-status` API](https://developer.hashicorp.com/vault/api-docs/system/seal-status) — initialized, sealed, seal type, threshold, shares và progress.
- HashiCorp Vault, [`vault status` CLI](https://developer.hashicorp.com/vault/docs/commands/status) — thông tin trạng thái và mã thoát của CLI.
- HashiCorp Vault, [System Backend HTTP API](https://developer.hashicorp.com/vault/api-docs/system) — danh mục endpoint hệ thống.
- Spring Vault, [`VaultSysOperations` Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultSysOperations.html) — isInitialized, getUnsealStatus, health.
- Spring Vault, [`VaultHealth` Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultHealth.html) và [`VaultUnsealStatus` Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultUnsealStatus.html) — ý nghĩa các trường trạng thái.
