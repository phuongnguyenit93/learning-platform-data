# Máy chủ sealed, chưa khởi tạo hoặc đang chuyển vai trò

## 1. Vấn đề thực tế khi Spring Vault phụ thuộc vào một cụm Vault

Một ứng dụng Java dùng **Spring Vault** có thể đọc KV secrets bằng `VaultTemplate`/`VaultOperations`, nhận thông tin xác thực động, gọi Transit encryption hoặc yêu cầu PKI cấp chứng thư. Workload được Vault xác thực bằng Kubernetes auth, AppRole hay cơ chế phù hợp và chỉ được thao tác trên endpoint mà Vault policy cho phép. Tuy nhiên, **một token hợp lệ không giúp request thành công khi Vault chưa khởi tạo, đang sealed hoặc đang chuyển vai trò HA**.

Hãy xét dịch vụ `orders-api` chạy trên nhiều pod. Nó đọc `secret/data/orders/payment` từ KV v2 lúc khởi động và tiếp tục gọi Transit khi xử lý đơn hàng. Trong một lần bảo trì, cluster Vault thay leader. Một số request đi qua node standby, vài request bị timeout, trong khi hệ thống giám sát vẫn thấy một node trả HTTP 200. Nếu ứng dụng chỉ “retry tất cả lỗi” hoặc “restart pod khi Vault tạm lỗi”, sự cố có thể lan rộng.

Bài học **“Máy chủ sealed, chưa khởi tạo hoặc đang chuyển vai trò”** trong chương **Lỗi và khả năng phục hồi** giải quyết ba mục tiêu:

1. **Nhận diện đúng trạng thái** bằng tín hiệu health/init/seal và bằng lỗi thực tế của lời gọi nghiệp vụ.
2. **Phục hồi có giới hạn**: timeout, retry có điều kiện, backoff/jitter, circuit breaker, chọn endpoint HA và chính sách readiness.
3. **Bảo toàn tính đúng đắn và bảo mật**: tránh khởi tạo/unseal từ code nghiệp vụ, tránh retry mù những API sinh secret, và không tiết lộ token/private key/plaintext khi ghi log.

> **Thông điệp chính:** Mã trạng thái của `/sys/health` mô tả **node Vault**; lỗi của `VaultOperations.read/write` mô tả **một giao dịch cụ thể**. Hai nguồn tín hiệu hỗ trợ nhau nhưng không được xem là đồng nhất.

## 2. Phân biệt ba nhóm trạng thái trước khi quyết định xử lý

### 2.1. Vault chưa initialized

Một Vault trên storage backend mới hoặc chưa được thiết lập có `initialized=false`. Lúc này, dữ liệu nền tảng và vật liệu khóa cần thiết chưa được khởi tạo. Endpoint `GET /v1/sys/init` cho biết trạng thái, còn `GET /v1/sys/health` thường trả **501** khi chưa initialized.

**Không chạy `POST /sys/init` từ ứng dụng Spring Boot hay health check.** Initialize là thao tác quản trị rất nhạy cảm, phải được thực hiện một cách có kiểm soát trên storage chính xác và chỉ khi triển khai Vault lần đầu. Nếu production vốn hoạt động nhưng đột nhiên trả uninitialized, cần nghi ngờ cấu hình storage, namespace/đường đi, dữ liệu backend hoặc node/endpoint kết nối sai trước khi kết luận “cluster cần init lại”.

### 2.2. Vault sealed

Vault có thể đã initialized nhưng đang `sealed=true`. Khi sealed, Vault chưa thể sử dụng khóa để truy cập dữ liệu được bảo vệ; phần lớn endpoint secrets và auth chưa phục vụ bình thường. `GET /v1/sys/seal-status` đọc trạng thái này; `GET /v1/sys/health` thường trả **503**.

Nguyên nhân có thể gồm:

- Vault mới khởi động lại và đang chờ unseal với cơ chế Shamir.
- Auto Unseal không thể liên lạc hoặc xác thực với KMS/HSM dùng làm seal backend.
- Nhóm vận hành chủ động seal node.
- Trục trặc ở tầng storage/seal hoặc đang chuyển đổi cơ chế seal.

**Không gửi unseal key hay recovery key qua ứng dụng nghiệp vụ, metrics, log hoặc retry handler.** Recovery key trong một số triển khai Auto Unseal không tương đương Shamir unseal key. Việc unseal theo đúng quy trình và vai trò quản trị thuộc nhóm vận hành Vault; Java workload chỉ chẩn đoán và chọn hành vi an toàn.

### 2.3. Node đang standby hoặc thay đổi vai trò HA

Trong cụm Vault HA, các node có thể cùng `initialized=true` và `sealed=false`, nhưng có một node **active** và các node **standby**; với Vault Enterprise còn có performance standby hoặc DR secondary. Khi thay leader, một node có thể mất vai trò active, standby bắt đầu chuyển tiếp request hoặc client nhận lỗi/redirect trong một khoảng ngắn.

Sơ đồ khái niệm:

~~~mermaid
sequenceDiagram
    participant App as Spring Vault client
    participant LB as Vault load balancer
    participant A as Node A (active cũ)
    participant B as Node B (active mới)
    App->>LB: KV read / Transit request
    LB->>A: Gửi request
    Note over A,B: Leader thay đổi, vai trò HA chưa ổn định
    A-->>LB: Timeout / 5xx / redirect (tùy thời điểm)
    LB-->>App: Request lỗi hoặc không rõ đã xử lý
    App->>App: Phân loại operation + lỗi, kiểm tra retry budget
    App->>LB: Retry có giới hạn khi an toàn
    LB->>B: Định tuyến tới active mới
    B-->>App: Kết quả từ API
~~~

Một node standby **không mặc nhiên là node hỏng**: Vault có khả năng request forwarding đến active, hoặc trong một số cấu hình trả redirect đến active. Đánh giá phải dựa trên topology, tình trạng forwarding, health policy và loại request. **DR secondary** là vai trò sao chép phục hồi thảm họa, không nên tự coi như active của primary để nhận traffic ghi.

## 3. Chẩn đoán theo tín hiệu: health, init, seal và lời gọi thật

### 3.1. Các endpoint chỉ đọc cần biết

| API | Công dụng | Dữ liệu hoặc trạng thái quan trọng |
| --- | --- | --- |
| `GET /v1/sys/health` | Phân loại health và vai trò node | HTTP code cùng các cờ `initialized`, `sealed`, `standby` nếu response có body |
| `HEAD /v1/sys/health` | Probe chỉ cần status, không có body | Mã HTTP, phù hợp health check gọn |
| `GET /v1/sys/init` | Kiểm tra initialized | `{"initialized": true/false}` |
| `GET /v1/sys/seal-status` | Kiểm tra seal/unseal | `initialized`, `sealed`, `type`, `t`, `n`, `progress` và các trường khác tùy Vault |
| API nghiệp vụ (KV/Transit/PKI/auth) | Kiểm tra khả năng phục vụ tác vụ cụ thể | HTTP status, loại lỗi, quyền ACL, schema, mount và thời gian phản hồi |

Các API đọc trạng thái hệ thống nói trên thường cho phép truy cập không cần Vault token; chính sách mạng/TLS vẫn phải bảo vệ chúng. `/sys/health` có thể không hoạt động đúng qua namespace hoặc reverse proxy cấu hình sai. Giữ endpoint theo node khi chẩn đoán; health qua load balancer chỉ cho biết **một đường đi** còn phục vụ được.

### 3.2. Mã mặc định của `/sys/health`

| HTTP code | Trạng thái health mặc định | Gợi ý vận hành |
| --- | --- | --- |
| **200** | Active, initialized, unsealed | Có khả năng nhận request ở mức node; chưa chứng minh policy/secret engine hoạt động |
| **429** | Standby | Không vội hiểu là rate limit; kiểm tra HA forwarding |
| **472** | DR secondary | Chỉ dùng theo kiến trúc DR được phê duyệt |
| **473** | Performance standby | Phù hợp cho một số luồng read tùy topology |
| **474** | Standby không liên lạc được active | Cảnh báo sự cố HA; không giả định forwarding tốt |
| **501** | Uninitialized | Kiểm tra provisioning/storage, không tự initialize |
| **503** | Sealed | Xử lý theo runbook seal/Auto Unseal |
| **530** | Removed node | Loại khỏi pool xử lý, kiểm tra trạng thái membership |

Các mã này là **mặc định của health endpoint**. Tham số `standbyok=true`, `perfstandbyok=true` và `activecode`/`standbycode`/`sealedcode`... có thể **đổi mã mà endpoint trả**; chúng không đổi vai trò thực tế của node. Vì thế dashboard và load balancer phải biết chính xác URL probe đang dùng.

**Không suy ra lỗi API nghiệp vụ từ health code:** `429` khi gọi `/sys/health` thường là standby, nhưng `429` của một API khác có thể liên quan quota/rate limiting. Tương tự, `503` trên `/sys/health` thường là sealed; một `503` từ proxy hay lệnh KV có thể có nguyên nhân khác. Để phân loại chắc chắn, kết hợp **endpoint + method + status + error type + node health**.

### 3.3. Lệnh chẩn đoán không làm thay đổi dữ liệu

Dùng địa chỉ Vault test hoặc endpoint được phép giám sát; CA TLS phải tin cậy:

~~~bash
# VAULT_ADDR đã được cấu hình tới URL HTTPS của node cần kiểm tra.
# Không thêm -k hoặc --insecure để vượt lỗi TLS.
curl -sS -i "$VAULT_ADDR/v1/sys/health"

curl -sS "$VAULT_ADDR/v1/sys/init" \
  | jq '{initialized}'

curl -sS "$VAULT_ADDR/v1/sys/seal-status" \
  | jq '{initialized, sealed, type, progress, storage_type}'

# Health với mã mặc định (chỉ HTTP status), không nuốt non-2xx.
curl -sS -o /dev/null -w 'health_http=%{http_code}\n' \
  "$VAULT_ADDR/v1/sys/health"
~~~

Không dùng `curl --fail` nếu cần đọc `429/501/503` cùng body khi điều tra; `curl -sS -i` cho thấy đầy đủ HTTP status. Một số môi trường dùng `VAULT_NAMESPACE` hay ingress đặc biệt: cần xác nhận client đang truy cập đúng node/cluster/root namespace. Nếu health trả 200 mà ứng dụng nhận 403 ở `secret/data/...`, hãy kiểm tra **token, Vault ACL, KV mount, namespace**; retry không sửa được lỗi quyền.

### 3.4. Cây quyết định xử lý lỗi

~~~mermaid
flowchart TD
    A[Lời gọi Spring Vault lỗi] --> B{Có HTTP response từ Vault?}
    B -->|Không| C[Kiểm tra DNS, TLS, timeout, LB, network; trạng thái UNKNOWN]
    B -->|Có| D{Lỗi cấu hình/quyền 400, 403, 404?}
    D -->|Có| E[Kiểm tra token, policy, mount, request và schema; không retry mù]
    D -->|Không| F[Đọc health/init/seal bằng kênh quan sát]
    F --> G{initialized=false?}
    G -->|Có| H[Báo lỗi provisioning/storage; không gọi init]
    G -->|Không| I{sealed=true?}
    I -->|Có| J[Incident seal / Auto Unseal; fail closed hoặc degraded]
    I -->|Không| K{Đang failover/HA degraded?}
    K -->|Có| L[Chờ bounded backoff; chỉ retry tác vụ an toàn]
    K -->|Không| M[Kiểm tra secret engine, quota, proxy và ứng dụng]
~~~

**UNKNOWN** là trạng thái hợp lệ: khi mất mạng hoặc TLS handshake thất bại, client **không có bằng chứng** Vault đã sealed hay uninitialized. Đừng chuyển mọi exception thành `initialized=false` hoặc tự thông báo “Vault is sealed”.

## 4. Ứng xử của ứng dụng khi Vault sealed

### 4.1. Lúc khởi động

Nếu ứng dụng cần key/token/credential để phục vụ chức năng cốt lõi, thiếu secret vì Vault sealed nên khiến **readiness chưa đạt** hoặc startup kết thúc với lỗi được kiểm soát. Thiết kế nên:

1. Có `connect timeout`, `read timeout` và **deadline tổng** cho pha đọc secrets.
2. Retry ngắn với backoff/jitter khi lỗi có thể tạm thời, nhưng không chờ vô hạn.
3. Không nhận traffic phụ thuộc secret khi chưa nạp và kiểm tra giá trị bắt buộc.
4. Báo vận hành tình trạng Vault sealed cùng thông tin endpoint/node và thời điểm, không đính kèm token/secret.
5. Khi Vault được unseal và workload còn danh tính hợp lệ, thực hiện lại đọc secret theo lifecycle của ứng dụng.

Ví dụ: nếu payment API cần khóa từ KV nhưng report job không cần, có thể để job report khởi động độc lập; không để lỗi Vault trên nhánh tùy chọn làm toàn bộ deployment liên tục restart.

### 4.2. Khi ứng dụng đang phục vụ

Nếu một số KV secret đã tải và **vẫn có hiệu lực theo chính sách**, một request không cần Vault ngay lúc đó có thể tiếp tục chạy. Nhưng không mặc định dùng cache vô hạn:

- **KV tĩnh**: có thể cân nhắc stale-if-error trong giới hạn tuổi và chính sách rotation/revocation cho phép.
- **Dynamic database credentials**: có `lease_duration`, có thể bị revoke; cache không kéo dài quyền đăng nhập của credential.
- **Vault token**: token/session cần renew hoặc re-login độc lập; đã hết TTL không thể “gia hạn” bằng cache KV.
- **Transit**: nếu thiết kế yêu cầu Vault xử lý encrypt/decrypt, khi Vault sealed thì không có phép toán mới; không tự xuất master key ra JVM để dự phòng.
- **PKI/TLS**: certificate và private key đã cài có thể tiếp tục hoạt động đến thời điểm bị thu hồi/hết hạn tùy cơ chế kiểm tra, nhưng phải có khả năng cấp lại trước `notAfter`.

Một ứng dụng có thể còn **liveness khỏe** trong khi tính năng phụ thuộc Vault mất **readiness** hoặc báo trạng thái degraded. Không gắn liveness trực tiếp vào một Vault request rồi restart hàng loạt pod trong mỗi sự cố seal.

### 4.3. Điều không nên làm

- Không tự gọi `POST /sys/unseal`/`PUT /sys/seal` từ tầng business.
- Không ghi unseal key, recovery key, private key, dynamic password hay Vault session token vào log để “debug”.
- Không tự chuyển sang một cụm Vault khác với dữ liệu/chính sách không tương đương nếu chưa có thiết kế DR/failover được phê duyệt.
- Không cứ thấy 503 là khởi tạo Vault lại, xóa token hay xóa cache hợp lệ.
- Không giữ network request mở vô hạn chờ một người quản trị unseal xong.

## 5. Ứng xử khi Vault chưa khởi tạo

### 5.1. Tại sao đây thường là sự cố provisioning?

`initialized=false` không phải một dạng “lỗi đăng nhập” thông thường. Nó gợi ý Vault chưa có dữ liệu khởi tạo trên backend mà node nhìn thấy. Với cụm production đã vận hành, cần xem các khả năng:

| Dấu hiệu | Nguyên nhân đáng kiểm tra | Ai xử lý |
| --- | --- | --- |
| Node mới trả `initialized=false` | Trỏ nhầm storage backend, sai persistent volume/cluster | Platform/Vault admin |
| Mọi node đều báo chưa initialized sau restart | Storage bị thay, cấu hình đường dữ liệu sai, sự cố backend | Platform/Vault admin |
| Một endpoint báo 501, VIP báo 200 | LB định tuyến đến nhiều cụm/node khác nhau, sai route | Platform/network |
| `sys/init` cho kết quả khác hẳn dashboard | Sai địa chỉ, namespace, reverse proxy, cache giám sát | Platform/observability |
| 403 khi gọi secret nhưng init=true | Lỗi auth/ACL/mount, **không** liên quan initialize | Application/platform |

**Không tự phục hồi bằng initialize** trên storage có thể nhầm: thao tác đó không khôi phục dữ liệu cũ, không sửa được sai endpoint và có thể tạo một Vault hoàn toàn khác gây nhầm lẫn. Nếu hệ thống mới cài đặt lần đầu, nhóm vận hành phải thực hiện provisioning, bảo vệ vật liệu khóa và quy trình bootstrap theo tài liệu Vault.

### 5.2. Phản ứng của Java workload

Ứng dụng chỉ có hai trách nhiệm:

1. **Fail closed/không sẵn sàng** cho tính năng phụ thuộc secrets, với mã lỗi nghiệp vụ và tín hiệu giám sát rõ ràng.
2. **Thử lại có giới hạn** nếu xác nhận đây là bước triển khai mới đang chờ một quy trình initialize do platform thực hiện; giới hạn thời gian trong deployment và không gọi initialize trực tiếp.

Với môi trường đã từng healthy, cảnh báo `initialized=false` cần ưu tiên cao hơn một lỗi timeout đơn lẻ vì nó có thể báo ứng dụng đang nhìn **sai Vault**. Phải đối chiếu hostname, cluster ID và storage ở kênh vận hành trước khi cấp quyền dữ liệu.

## 6. Ứng xử khi Vault HA đang thay leader

### 6.1. Điều gì có thể xảy ra trong quá trình chuyển vai trò?

Các tình huống quan sát được tùy topology:

- Request đến standby được **forward** tới active; client có thể không biết request đang được xử lý ở node khác.
- Node standby phản hồi redirect tới `api_addr` active; HTTP client cần xử lý đúng TLS/đích.
- Active cũ rời cụm hoặc kết nối bị đứt khi request đang chạy; client nhận timeout/connection reset dù không biết request đã được thực thi chưa.
- Health của node biến đổi nhanh giữa active, standby và HA degraded; có thể có `429`/`474` ở health endpoint, trong khi data API có mã khác.
- Token login trước failover có thể vẫn hợp lệ sau failover nếu state backend nhất quán, nhưng một token gần hết TTL hoặc lease expired trong thời gian gián đoạn vẫn cần renew/re-auth/rotation.

**Không giả định leader switch đồng nghĩa token bị hủy**. Cũng không giả định mọi request thất bại nghĩa là server chưa xử lý: timeout xảy ra **sau khi** Vault đã tạo SecretID, certificate hoặc credential là một trường hợp điển hình.

### 6.2. Dùng endpoint HA phù hợp

Với Spring Vault, URL cấu hình cho client nên là một **endpoint được hỗ trợ HA**, ví dụ Vault load balancer/ingress nội bộ hoặc cơ chế kết nối nhiều node được thư viện và hệ thống vận hành hỗ trợ. Endpoint cần có:

- TLS hợp lệ với tên máy chủ được cấu hình; client tin cậy CA phục vụ endpoint đó.
- Health probe phản ánh chiến lược định tuyến: active-only, standby forwarding hoặc performance standby khi phù hợp.
- Quy tắc timeout, connection draining và cập nhật leader; không giữ node removed trong pool.
- Khả năng chuyển tới active mới khi failover, đồng thời không trỏ sang DR secondary khi chưa kích hoạt DR.
- Namespace, mount, tenancy và domain an toàn nhất quán giữa các node.
- Chính sách redirect rõ: chỉ theo `api_addr` **được phê duyệt**, không gửi `X-Vault-Token` sang host do phản hồi không tin cậy quyết định.

Một node standby trả **429 ở `sys/health`** có thể hoàn toàn phù hợp cho pool được thiết kế forwarding; muốn trả 200 cho health có thể đặt `?standbyok=true`. Nhưng cờ này chỉ **đổi cách báo trạng thái probe**, không biến standby thành active hoặc tự sửa đường forwarding bị lỗi. Đối với performance standby, tham số tương ứng là `perfstandbyok=true` và cần biết loại request nó có thể phục vụ.

### 6.3. Hạn chế “retry storm”

Khi leader failover, hàng trăm pod cùng gặp lỗi và retry ngay có thể tạo đỉnh tải đúng lúc Vault đang phục hồi. Phối hợp:

- **Exponential backoff + jitter** để các instance không retry cùng nhịp.
- **Giới hạn số lần/độ dài tổng** của một request và giới hạn đồng thời.
- **Circuit breaker** cho dịch vụ phụ thuộc Vault để ngừng đập vào endpoint lỗi liên tục; thử lại sau thời gian mở mạch có kiểm soát.
- **Single-flight** cho cache refresh: nhiều request trong một pod dùng chung một lượt đọc khi cache hết hạn.
- Giảm request khởi tạo bất đồng bộ, phân tán lịch job và dùng readiness để giảm lưu lượng khi chưa sẵn sàng.
- Khi HTTP có `Retry-After` ở một số ngữ cảnh, chỉ áp dụng hợp lệ theo endpoint và policy, không thay thế deadline của hệ thống.

Backoff là công cụ điều phối khi **lỗi có thể phục hồi**, không chữa được `403 permission denied`, `404 key không tồn tại` hoặc `400 request sai schema`.

## 7. Bảng chính sách retry theo loại lỗi và loại thao tác

### 7.1. Trước hết phân loại lỗi

| Tín hiệu trên request thực tế | Cách hiểu thận trọng | Retry tự động? |
| --- | --- | --- |
| Lỗi DNS/connect timeout/connection reset | Sự cố mạng/LB hoặc failover; chưa biết server đã xử lý | **Có điều kiện** theo tính lặp lại của thao tác |
| TLS handshake thất bại vì CA/hostname sai | Cấu hình tin cậy hoặc certificate không hợp lệ | **Không**; sửa TLS/endpoint |
| HTTP 400 | Input/role/path/format không hợp lệ | **Không**, trừ lỗi có bằng chứng là tạm thời |
| HTTP 401/403 | Token không hợp lệ/hết hạn hoặc ACL thiếu | **Không** với cùng credential; re-auth nếu token hết hạn và xác định được nguyên nhân |
| HTTP 404 | Sai path/mount, KV entry hoặc version không tồn tại | **Không**; kiểm tra thực thể cần đọc |
| HTTP 429 của **API nghiệp vụ** | Có thể bị quota/rate limit; endpoint health 429 lại có nghĩa standby | Chỉ retry bounded theo contract endpoint |
| HTTP 500/502/503/504 từ API nghiệp vụ | Server/proxy tạm lỗi, sealed hoặc failover có thể xảy ra | Chỉ retry bounded nếu thao tác an toàn |
| `/sys/health` 501 | Uninitialized | Không retry vòng vô hạn; báo provisioning |
| `/sys/health` 503 | Sealed | Quan sát, đợi vận hành xử lý; chỉ thử lại có giới hạn |
| `/sys/health` 474/530 | HA unhealthy/removed | Sửa route hoặc chờ cluster; không route node lỗi |

Trong Spring Vault, một lỗi HTTP có thể được biểu diễn bằng exception do Spring Web hay Spring Vault ném ra, tùy phiên bản và lớp client. **Không hardcode suy luận chỉ từ tên exception**; khi cần phân loại HTTP code, truy xuất code từ cause chain, xem cấu hình error handler, và đối chiếu với health probe. Đừng parse chuỗi thông báo lỗi chứa dữ liệu nhạy cảm để đoán trạng thái Vault.

### 7.2. Thao tác có thể lặp lại và thao tác tạo trạng thái

Đây là phần quyết định quan trọng nhất khi request đã gửi nhưng client chưa nhận phản hồi:

| API hoặc tác vụ | Hệ quả khi gọi lần nữa | Chính sách khi timeout/HA failover |
| --- | --- | --- |
| **KV v2 GET** `secret/data/...` | Đọc lại dữ liệu, không tạo secret mới | Có thể retry bounded, xem lại consistency/version khi cần |
| **Transit decrypt** | Thường là phép toán đọc/giải mã; cùng ciphertext/context trả plaintext tương ứng | Có thể retry bounded, bảo vệ plaintext/log |
| **Transit encrypt** | Có thể tạo ciphertext khác do IV/nonce mới dù cùng plaintext | Chỉ retry khi nghiệp vụ chưa commit và kiểm soát downstream idempotency |
| **KV v2 write** | Ghi phiên bản mới, gây side effect | Không retry mù; có thể dùng **CAS** và đọc đối chiếu version/nội dung sau timeout |
| **Database dynamic credentials** `database/creds/...` | Có thể tạo một account/lease mới mỗi lần | Tránh retry mù; có chính sách quota, audit và cleanup |
| **PKI issue** `pki/issue/:role` | Có thể cấp certificate + private key mới với serial mới | Không retry mù; nếu mất response không suy ra private key có thể lấy lại |
| **AppRole SecretID issue** | Có thể tạo SecretID mới | Không retry mù; dùng workflow cấp phát/thu hồi và đối chiếu audit |
| **Token create** | Có thể tạo token mới | Không retry mù; theo dõi accessor/quy trình cấp phát |
| **Lease renew/revoke** | Thay đổi vòng đời secret | Kiểm tra trạng thái hiện tại/TTL trước khi thử lại theo chính sách |
| **Response wrapping unwrap** | Token dùng một lần; lần đầu có thể đã tiêu thụ | **Không retry mù** cùng token sau timeout; xác minh quy trình nhận/giao |

**Idempotency** nghĩa là gọi lặp không tạo tác dụng ngoài dự kiến. Một HTTP method nhìn có vẻ “đọc” cũng có thể tạo trạng thái tại Vault: endpoint cấp dynamic credentials thường dùng HTTP GET, nhưng việc đọc **sinh ra credential và lease mới**. Vì vậy đừng suy ra “GET luôn retry an toàn” từ HTTP method.

### 7.3. Ví dụ: tại sao retry PKI có thể nguy hiểm?

1. `orders-api` yêu cầu `pki/issue/orders-role`.
2. Vault đã tạo key pair, ký certificate số serial A và gửi response.
3. Kết nối đứt trước khi client nhận private key.
4. Client tự retry, Vault tạo certificate B, private key B và serial B.
5. Bên ứng dụng chỉ có B; A vẫn có thể tồn tại ở hệ thống PKI và cần theo dõi/thu hồi tùy chính sách.

Nếu loại request này thực sự cần retry khi kết nối không rõ trạng thái, thiết kế **quy trình cấp phát có định danh nghiệp vụ**, audit, thời gian chờ, giới hạn số lần, cleanup và cơ chế xử lý cấp phát kép; đừng đặt retry interceptor toàn cục cho mọi `VaultOperations`.

## 8. Mẫu Java: đọc KV v2 có retry bounded và phân loại lỗi

Ví dụ dùng **Java 17+, Spring Vault và Spring Web**; `VaultOperations` được cấu hình trước với TLS, workload authentication và timeout phù hợp. Chỉ đọc **KV v2** ở path đã allowlist. Mã giữ riêng logic retry cho thao tác an toàn, thay vì gắn một interceptor chung lên mọi endpoint.

### 8.1. Reader dữ liệu nghiệp vụ với kiểm tra cấu trúc

~~~java
import java.util.Map;
import java.util.Objects;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

public final class OrdersConfigReader {

    private static final String PATH = "secret/data/orders/config";
    private final VaultOperations vault;

    public OrdersConfigReader(VaultOperations vault) {
        this.vault = Objects.requireNonNull(vault);
    }

    public OrdersConfig readFresh() {
        VaultResponse response = vault.read(PATH);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Orders KV configuration missing");
        }

        Object nested = response.getData().get("data");
        if (!(nested instanceof Map<?, ?> values)) {
            throw new IllegalStateException("Invalid KV v2 response shape");
        }

        Object region = values.get("region");
        if (!(region instanceof String text) || text.isBlank()) {
            throw new IllegalStateException("Invalid orders.region");
        }

        return new OrdersConfig(text);
    }

    public record OrdersConfig(String region) {}
}
~~~

`VaultResponse.getData()` với đường dẫn `secret/data/...` thường chứa lớp map dữ liệu gồm `data` (các cặp key/value) và `metadata` (KV v2 version). Vì thế ứng dụng phải lấy thêm `.get("data")`. Ví dụ dùng `region` giả không nhạy cảm để dễ quan sát; nếu thực tế chứa password/API key, tránh lưu nó trong `toString()` của record, exception hoặc HTTP response.

**Thiếu path hoặc schema sai không phải transient failure.** Đoạn reader trên chủ động ném `IllegalStateException` để caller xem đây là lỗi dữ liệu/cấu hình, khác với lỗi mạng có thể retry.

### 8.2. Retry tối đa ba lần, chỉ với lỗi tạm thời đã xác định

~~~java
import java.net.ConnectException;
import java.net.SocketException;
import java.net.SocketTimeoutException;
import java.util.concurrent.ThreadLocalRandom;

import javax.net.ssl.SSLException;

import org.springframework.web.client.RestClientResponseException;

public final class RetryingOrdersConfigReader {

    private final OrdersConfigReader delegate;

    public RetryingOrdersConfigReader(OrdersConfigReader delegate) {
        this.delegate = delegate;
    }

    public OrdersConfigReader.OrdersConfig read() {
        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                return delegate.readFresh();
            } catch (RuntimeException failure) {
                if (attempt == 3 || !isRetryable(failure)) {
                    throw failure;
                }

                long baseMillis = 100L << (attempt - 1);
                long jitterMillis =
                        ThreadLocalRandom.current().nextLong(20L, 101L);
                try {
                    Thread.sleep(baseMillis + jitterMillis);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(
                            "Interrupted while retrying Vault read",
                            interrupted);
                }
            }
        }

        throw new IllegalStateException("Unreachable");
    }

    private static boolean isRetryable(Throwable failure) {
        // TLS identity/trust mismatch cần sửa cấu hình, không retry.
        for (Throwable cause = failure;
             cause != null; cause = cause.getCause()) {
            if (cause instanceof SSLException) {
                return false;
            }
        }

        for (Throwable cause = failure;
             cause != null; cause = cause.getCause()) {
            if (cause instanceof RestClientResponseException httpError) {
                int status = httpError.getStatusCode().value();
                return status == 429
                        || status == 502
                        || status == 503
                        || status == 504;
            }
            if (cause instanceof ConnectException
                    || cause instanceof SocketTimeoutException
                    || cause instanceof SocketException) {
                return true;
            }
        }
        return false;
    }
}
~~~

**Giới hạn chủ đích của ví dụ:**

- Retry tối đa **ba lần tổng cộng**, có backoff/jitter; chỉ bao quanh **KV read** đã xác định là an toàn để lặp. Không copy lớp này để gọi PKI issue, database credentials hoặc unwrap.
- Phân loại HTTP `429/502/503/504` ở **API nghiệp vụ**, không gọi `/sys/health` rồi áp mã 429 như rate limit. Nếu chính sách quota giới hạn mạnh, cần xem `Retry-After` và budget thay vì retry ngay.
- Tùy bản Spring Vault, lỗi HTTP có thể được gói trong `VaultException` hoặc lỗi khác mà không còn `RestClientResponseException` trong cause chain. Trường hợp không nhận diện được, ví dụ **không tự retry**; cần điều chỉnh classifier theo loại exception thực tế đã quan sát và kiểm thử.
- Ví dụ dùng `Thread.sleep` để minh họa backoff cho luồng đồng bộ. Trên ứng dụng lưu lượng lớn, chọn thư viện resilience/scheduler phù hợp và **không block event-loop** của reactive stack.
- Cần cấu hình **connect/read timeout trên HTTP client**; ba attempts tự thân không đặt được deadline tổng. Nếu một request chờ 30 giây, ba lần gọi có thể vượt SLO.
- Đường dẫn Vault và danh tính được cấu hình cố định; không nhận path raw từ user. Không serialize exception có chứa request headers hoặc secret.

Có thể dùng **Spring Retry**, **Resilience4j** hoặc cơ chế tương đương để triển khai policy retry và circuit breaker có metrics, nhưng điều kiện **API nào được retry** vẫn phải được gắn với thao tác cụ thể.

### 8.3. Tách lỗi Vault khỏi lỗi ứng dụng

Với API thanh toán phụ thuộc KV, lớp service có thể chuyển exception thành kết quả ứng dụng an toàn:

~~~java
public enum SecretAvailability {
    READY,
    TEMPORARILY_UNAVAILABLE,
    CONFIGURATION_ERROR
}
~~~

- `READY`: đã đọc và kiểm tra secret; consumer có thể dùng.
- `TEMPORARILY_UNAVAILABLE`: lỗi mạng, 503, đang failover; tính năng phụ thuộc secret có thể trả mã lỗi tạm thời (ví dụ HTTP 503 ở API của ứng dụng) và metrics báo degraded.
- `CONFIGURATION_ERROR`: 403, không thấy path, schema sai; yêu cầu khắc phục cấu hình/quyền, không retry vô hạn.

Đây là **kiểu enum minh họa cho ứng dụng**, không phải enum có sẵn trong Spring Vault. Với dữ liệu nhạy cảm, response cho người dùng chỉ nên nêu dịch vụ tạm không khả dụng và correlation ID an toàn; chi tiết token/policy/mount chỉ nằm trong hệ giám sát có phân quyền.

## 9. Probe trạng thái node bằng Java mà vẫn giữ HTTP non-2xx

Các method `VaultOperations.opsForSys().isInitialized()` và `getUnsealStatus()` hữu ích khi đọc thông tin initialized/sealed. `opsForSys().health()` cũng có thể trả `VaultHealth` ở trạng thái phù hợp. Tuy nhiên, nếu cần phân biệt **429/472/473/474/501/503/530**, một HTTP client có error handler biến non-2xx thành exception trước khi mapping JSON.

Một probe chỉ đọc dùng JDK HTTP client sẽ giữ nguyên status, không cần root token:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class VaultNodeHealthProbe {

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    // nodeBaseUri cấu hình tĩnh/allowlist, dùng HTTPS CA hợp lệ.
    public ProbeResult probe(URI nodeBaseUri)
            throws IOException, InterruptedException {

        URI target = nodeBaseUri.resolve("/v1/sys/health");
        HttpRequest request = HttpRequest.newBuilder(target)
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request,
                HttpResponse.BodyHandlers.discarding());

        int status = response.statusCode();
        NodeState state = switch (status) {
            case 200 -> NodeState.ACTIVE;
            case 429 -> NodeState.STANDBY;
            case 472 -> NodeState.DR_SECONDARY;
            case 473 -> NodeState.PERFORMANCE_STANDBY;
            case 474 -> NodeState.HA_UNHEALTHY;
            case 501 -> NodeState.UNINITIALIZED;
            case 503 -> NodeState.SEALED;
            case 530 -> NodeState.REMOVED;
            default -> NodeState.UNKNOWN;
        };
        return new ProbeResult(status, state);
    }

    public enum NodeState {
        ACTIVE, STANDBY, PERFORMANCE_STANDBY, DR_SECONDARY,
        HA_UNHEALTHY, UNINITIALIZED, SEALED, REMOVED, UNKNOWN
    }

    public record ProbeResult(int httpCode, NodeState state) {}
}
~~~

**Các điều kiện sử dụng:** 

- Probe trên **URL health mặc định**; nếu dùng `standbyok=true` hoặc override HTTP code thì phải sửa classifier hoặc phân tích JSON.
- Địa chỉ `nodeBaseUri` phải do cấu hình đáng tin cậy cung cấp, tránh SSRF; hostname/TLS phải được xác minh. Với CA nội bộ, cấu hình Java truststore hoặc `SSLContext` đúng chính sách; không tắt xác minh certificate.
- `HttpClient` chỉ quan sát trạng thái. Kể cả `ACTIVE`, lời gọi `VaultOperations.read()` vẫn có thể bị `403` hoặc timeout do token/policy/network.
- Nếu request health **không thành công ở tầng TCP/TLS** và ném `IOException`, caller cần map sang **UNKNOWN** và ghi loại lỗi/latency, thay vì giả lập `SEALED`. Nếu bị interrupt, bảo toàn interrupt flag ở tầng điều phối.
- Mã `200` từ load balancer có thể đến một node khác node mà ứng dụng đang lỗi. Muốn điều tra failover, probe **từng node** bằng địa chỉ nội bộ đã định danh.
- `GET /sys/init` và `GET /sys/seal-status` giúp kiểm tra chéo hai trạng thái; dùng `VaultSysOperations` hoặc HTTP riêng để đọc JSON khi cần.

Probe này không thực hiện unseal, initialize, mount hay thay đổi policy.

## 10. Readiness, liveness và circuit breaker khi Vault không sẵn sàng

### 10.1. Phân lớp tín hiệu

| Lớp | Trả lời câu hỏi | Chiến lược khuyến nghị |
| --- | --- | --- |
| **Vault node health** | Node sealed, uninitialized, active, standby hay HA degraded? | Probe từng node, giữ mã mặc định và route theo topology |
| **Vault client reachability** | Endpoint mà ứng dụng dùng có thể kết nối được? | Theo dõi TLS, timeout, DNS, latency và HTTP codes |
| **Application readiness** | Ứng dụng có đủ secrets/leases hiện hợp lệ để xử lý request? | Dựa trên **khả năng phục vụ tính năng thiết yếu** và chính sách cache hợp lệ |
| **Application liveness** | JVM/process còn chạy bình thường? | Không restart JVM vì một lỗi Vault tạm thời |
| **Business operation** | KV/Transit/PKI/DB credential đã thực hiện thành công? | Metrics riêng theo loại API và kết quả thực tế |

Một service có thể **live nhưng chưa ready**: Vault sealed khiến nó không tải được khóa để phục vụ thanh toán. Nếu token/secret đã cache và vẫn hợp lệ theo policy, service có thể tiếp tục ready cho các request không cần tương tác Vault, nhưng không hứa hẹn Transit/PKI mới hoạt động.

### 10.2. Circuit breaker

Circuit breaker giúp hạn chế gọi dồn vào Vault khi lỗi liên tục, ví dụ:

~~~text
CLOSED   -- lỗi liên tiếp vượt ngưỡng --> OPEN
  ^                                     |
  |                                     | sau thời gian mở mạch
  +--- thành công từ HALF_OPEN <--- HALF_OPEN
                   |
              lỗi tiếp tục --> OPEN
~~~

- **Closed**: request bình thường, thống kê lỗi thực.
- **Open**: không gửi thêm những request dễ thất bại, trả lỗi tạm thời nhanh.
- **Half-open**: chỉ cho một lượng nhỏ request kiểm tra xem backend đã phục hồi chưa.

Cấu hình riêng cho KV read, Transit, issue certificate và lease operations vì retry/idempotency khác nhau. **Không dùng circuit breaker để giấu 403 hoặc KV path sai**: đây là lỗi cấu hình cần khắc phục. Không biến half-open probe thành hàng trăm lệnh cấp phát dynamic credentials.

### 10.3. Xử lý sau khi Vault hồi phục

Khi cluster trở lại active/unsealed:

1. Xác nhận endpoint thật và kết nối TLS/auth hoạt động.
2. Kiểm tra session token còn hiệu lực; reauthenticate nếu cần, **không mặc định tất cả token cũ bị mất**.
3. Với dynamic credentials, xem lease còn hạn hay cần renew/rotate; cập nhật connection pool trước khi phục vụ.
4. Với KV, tải lại theo TTL/version/invalidation và kiểm tra schema; nếu cache stale đã vượt hạn cho phép thì không tiếp tục dùng.
5. Với PKI, cấp lại identity nếu certificate hết hạn gần tới hoặc private key đã bị mất; kiểm tra đúng chuỗi CA.
6. Với Transit, resume operations bình thường; không tự chuyển key material vào ứng dụng.
7. Đóng circuit breaker theo kết quả thực, tăng traffic có kiểm soát, giảm số đồng thời khi backend vừa phục hồi.

Sự phục hồi của health endpoint **không tự chứng minh** lease/token/secret còn hợp lệ. Các consumer phải xác minh vòng đời riêng.

## 11. Giám sát, cảnh báo và runbook

### 11.1. Metrics và log an toàn

| Tín hiệu | Mục đích | Lưu ý |
| --- | --- | --- |
| `vault_health_code{node}` | Phân loại active/standby/sealed/uninitialized/removed | Không nhãn hóa secret path hay token |
| `vault_read_error_total{category}` | Phân biệt 403/404/timeout/5xx/TLS | Nhãn category có số giá trị hữu hạn |
| `vault_request_duration_seconds` | Theo dõi latency khi failover và hồi phục | Không ghi payload/raw URL có PII |
| `vault_retry_attempts_total{operation}` | Theo dõi retry storm và tỉ lệ thành công | Phân loại operation `kv_read`, `transit_encrypt`... |
| `vault_circuit_breaker_state` | Biết ứng dụng đang chặn request do sự cố | Không chứa dữ liệu bí mật |
| `vault_token_time_to_expiry` | Phát hiện session token gần hết hạn | Không xuất token |
| `vault_lease_remaining_seconds` | Phát hiện dynamic credential cần renew/rotate | Không xuất username/password |

Log chẩn đoán nên có **correlation ID**, tên hệ thống, vai trò node nếu đã biết, loại operation, HTTP code đã làm sạch, số attempts và thời gian. Không ghi `X-Vault-Token`, AppRole SecretID, response body chứa private key, plaintext Transit, database password hoặc unseal/recovery key.

Một cảnh báo nên phân biệt:

- **Cluster-wide sealed/uninitialized**: ưu tiên xử lý hạ tầng và quy trình Vault.
- **Một standby chuyển vai trò, request forwarding còn hoạt động**: có thể là biến động HA bình thường, theo dõi thêm.
- **Node health 474 hoặc removed 530**: điều tra routing và khả năng liên lạc active.
- **403 tăng mạnh**: kiểm tra auth/policy/token trước khi kết luận sealed.
- **Retry attempts tăng, latency tăng, 5xx ngắn hạn**: có thể đang chuyển leader hoặc overload.

### 11.2. Runbook cho người trực vận hành và ứng dụng

~~~text
SỰ CỐ: Vault API từ ứng dụng bị lỗi
  1. Xác định Vault URL, namespace, node/LB, HTTP method và API gốc.
  2. Kiểm tra TCP/TLS và quyền truy cập; loại lỗi transport -> UNKNOWN.
  3. GET /sys/health của node + GET /sys/init + GET /sys/seal-status.
  4. Uninitialized -> kiểm tra backend/config; không initialize tự động.
  5. Sealed -> kiểm tra seal mechanism/KMS/HSM; thực hiện runbook admin.
  6. Standby/HA unhealthy -> kiểm tra leader, forwarding, LB, routing.
  7. Healthy nhưng API 403/404 -> kiểm tra workload auth, ACL, mount,
     schema và dữ liệu secret.
  8. Với mỗi operation bị lỗi, kiểm tra có được retry không.
  9. Khi phục hồi, xác nhận token/lease/secret và bật traffic dần.
 10. Đối chiếu metrics/audit, loại trừ dữ liệu bí mật khỏi báo cáo.
~~~

**Không chuyển status monitoring thành quyền vận hành:** người triển khai Spring Vault ứng dụng thông thường không cần quyền initialize, seal, unseal, rotate key hệ thống hay quản trị policy.

## 12. Kiểm thử tích hợp và mô phỏng sự cố

Bài tập sử dụng Vault dev/test **cô lập**, không thao tác seal/unseal hay failover trên cluster dùng chung. Có thể dùng container Vault test và ứng dụng Java Spring Vault với token/policy giới hạn để quan sát hành vi thật.

### 12.1. Tình huống khuyến nghị

| Tình huống | Môi trường/động tác | Kết quả cần xác nhận |
| --- | --- | --- |
| Vault initialized, unsealed, active | Vault dev/test | Health 200; KV v2 read thành công khi có quyền |
| Vault sealed | Instance thử nghiệm theo runbook admin | Health 503; ứng dụng phân loại sealed, không tự unseal |
| Vault chưa initialized | Storage test mới | `/sys/init=false`, health 501; ứng dụng không tự initialize |
| Lỗi network | Chặn mạng trong test container hoặc dùng endpoint test không reachable | UNKNOWN + retry bounded cho KV read; không đoán sealed |
| TLS sai CA | Test với truststore không tin cậy | Fail TLS; **không retry** với cùng cấu hình, không dùng insecure |
| Thiếu quyền KV | Token có policy không cấp `secret/data/...` | 403, không retry; thông báo lỗi đã làm sạch |
| KV path không tồn tại | Gọi path có chủ đích không có dữ liệu | 404/null tùy API, không retry vô hạn |
| HA leader change | Cụm HA test được cấu hình riêng | Endpoint LB chuyển vai trò, bounded retry KV read thành công khi phục hồi |
| Standby health 429 | Gọi trực tiếp standby | Không map thành rate limiting của KV |
| `standbyok=true` | Probe node standby | Mã probe thay đổi theo query, node không trở thành active |
| Transit encrypt timeout | Mô phỏng mất response sau khi server xử lý | Thấy nguy cơ ciphertext khác; downstream không commit trùng |
| PKI issue/SecretID issue timeout | Test role riêng, giới hạn phát hành | Không retry mù; ghi nhận dữ liệu phát hành mới qua audit |
| Wrapping token unwrap lần hai | Test token ngắn hạn | Lần đầu thành công, lần hai bị từ chối; không retry tự động |
| Dynamic credential lease hết hạn lúc Vault down | DB test và lease ngắn | Không dùng credential quá hạn; ứng dụng rotate/cấp lại khi khả dụng |
| 50 pod/pipeline đồng thời phục hồi | Load test có giới hạn ở môi trường riêng | Retry có jitter, không tạo thác request vượt budget |

### 12.2. Unit test cho bộ phân loại và retry

Tách `OrdersConfigReader` khỏi `RetryingOrdersConfigReader` để test dễ kiểm soát. Có thể đưa một interface `Supplier<OrdersConfig>` hoặc `Callable<OrdersConfig>` vào lớp retry; dùng fake clock/scheduler ở phiên bản production thay cho ngủ thật. Những assertion quan trọng:

1. Đọc thành công lần đầu → **1** Vault call.
2. Timeout kết nối hai lần rồi thành công → tối đa **3** Vault calls; không phát tán raw exception tới API ngoài.
3. `403`, `404` hoặc sai schema → chỉ **1** lần, không tự retry.
4. TLS trust failure → không retry, lỗi được phân loại an toàn.
5. Retry 3 lần vẫn lỗi → trả lỗi tạm thời và mở metric/circuit breaker theo policy.
6. Sau interrupt → bảo toàn trạng thái interrupted, không nuốt lỗi.
7. Với operation cấp PKI/SecretID/credential động → wrapper retry của KV **không** được dùng.
8. Với health 429 → classifier state là standby, không dùng policy rate limiting của các API khác.

Một test chỉ “mock `VaultOperations.read` trả String” chưa đủ chứng minh ứng dụng chịu được failover. Integration test phải kiểm tra HTTP/TLS/error handler thực tế, request forwarding và cách Spring Vault ánh xạ exception. Không chạy vòng lặp retry dài hoặc tạo nhiều secret động trong test nếu không có cleanup.

## 13. Những hiểu lầm cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Health 200 nghĩa là đọc secret nào cũng thành công.” | Health chỉ phản ánh trạng thái node; ACL, token, mount, lease vẫn có thể lỗi. |
| “Health 429 nghĩa là Vault bị rate limit.” | Với `/sys/health` mặc định, 429 là **standby**; API khác có thể dùng 429 cho quota. |
| “Node sealed thì ứng dụng nên gửi unseal key.” | Unseal thuộc quy trình quản trị Vault, không thuộc ứng dụng nghiệp vụ. |
| “Vault uninitialized là chưa có AppRole; cứ init lại.” | Initialized là trạng thái storage nền tảng; init lại có thể tạo hệ dữ liệu khác. |
| “Retry 3 lần luôn an toàn.” | Với PKI issue, dynamic creds, SecretID và unwrap, retry có thể tạo side effect/tiêu thụ token. |
| “Đổi `standbyok=true` làm node thành active.” | Chỉ thay HTTP health status theo điều kiện, không thay role hoặc sửa request forwarding. |
| “Timeout tức server chắc chắn chưa xử lý request.” | Timeout có thể xảy ra sau khi server hoàn thành, nhất là operation sinh secret. |
| “Vault mở lại là lease và session token tự động hợp lệ.” | TTL/expiry/revocation vẫn có hiệu lực và phải được kiểm tra. |
| “Restart pod liên tục giúp Vault hồi phục.” | Có thể làm tăng tải, tạo retry storm và phá tính sẵn sàng của ứng dụng. |
| “Một URL VIP healthy chứng minh mọi node khỏe.” | VIP chỉ chứng minh đường được chọn; cần health theo từng node và chỉ số cụm. |

## 14. Checklist khi đưa vào production

- [ ] Client dùng Vault endpoint HA đã phê duyệt, TLS/CA hợp lệ, không chuyển token sang redirect host lạ.
- [ ] Phân biệt lỗi mạng/TLS (UNKNOWN), lỗi ACL/schema, sealed, uninitialized và HA failover.
- [ ] Biết các mã mặc định của `/sys/health`: 200/429/472/473/474/501/503/530.
- [ ] Không nhầm health code với status của lệnh KV/Transit/PKI cụ thể.
- [ ] Dùng `GET/HEAD` cho health, `GET` cho init/seal-status; ứng dụng không gọi initialize/seal/unseal.
- [ ] KV read có connect/read timeout, retry bounded/backoff/jitter và deadline tổng.
- [ ] Retry policy được gắn theo **operation**, không áp dụng toàn cục cho API cấp secret.
- [ ] Có kế hoạch idempotency/đối chiếu khi timeout sau KV write, PKI issue, SecretID issue hoặc dynamic credentials.
- [ ] Liveness của JVM không phụ thuộc một request Vault; readiness phản ánh khả năng phục vụ tính năng cốt lõi.
- [ ] Circuit breaker và cache chỉ được cấu hình theo policy secret/lease/rotation đã phê duyệt.
- [ ] Sau khi Vault phục hồi, ứng dụng đánh giá token, lease, cache và certificate trước khi mở lại traffic.
- [ ] Giám sát health theo node và endpoint client; metric không chứa token, password, path tenant nhạy cảm.
- [ ] Đã kiểm thử 403/404, TLS lỗi, sealed, uninitialized, failover, timeout và operation không idempotent.
- [ ] Runbook phân quyền rõ giữa ứng dụng, platform operator, Vault administrator và nhóm bảo mật.

## Tài liệu tham khảo

- HashiCorp, [System health API](https://developer.hashicorp.com/vault/api-docs/system/health) — trạng thái active/standby/DR, mã HTTP và query parameters.
- HashiCorp, [Initialization status API](https://developer.hashicorp.com/vault/api-docs/system/init) — phân biệt kiểm tra trạng thái với thao tác initialize.
- HashiCorp, [Seal status API](https://developer.hashicorp.com/vault/api-docs/system/seal-status) — `initialized`, `sealed`, `type`, `progress`.
- HashiCorp, [Vault High Availability](https://developer.hashicorp.com/vault/docs/concepts/ha) và [Request Forwarding](https://developer.hashicorp.com/vault/docs/concepts/ha#request-forwarding) — leader/standby và điều hướng request.
- HashiCorp, [Vault Seal/Unseal](https://developer.hashicorp.com/vault/docs/concepts/seal) — Shamir và Auto Unseal.
- HashiCorp, [Lease, Renew and Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease) — vòng đời dynamic secret độc lập với health node.
- Spring Vault, [`VaultOperations` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html) và [`VaultTemplate` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html) — Java client và lời gọi KV.
- Spring Vault, [`VaultSysOperations` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultSysOperations.html) — `health()`, `isInitialized()`, `getUnsealStatus()`.
- Spring Vault, [`SecretLeaseContainer` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html) — quản lý lease và sự kiện credential.
