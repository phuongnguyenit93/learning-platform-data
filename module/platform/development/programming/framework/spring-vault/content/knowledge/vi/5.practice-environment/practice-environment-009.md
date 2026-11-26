# Kiểm tra kết nối và trạng thái máy chủ trước khi chạy ứng dụng

## 1. Vì sao cần kiểm tra Vault trước khi khởi động Java?

Ứng dụng dùng **Spring Vault** có thể gọi HashiCorp Vault qua **VaultTemplate** để đọc KV v2, thực hiện Transit encryption, xin chứng chỉ PKI hoặc làm việc với token và lease. Một lời gọi thất bại chưa chắc là lỗi code Java: có thể Vault chưa chạy, DNS chưa phân giải, certificate không được tin cậy, máy chủ còn **sealed**, token hết hạn hoặc policy không cho phép đúng endpoint.

Trong chương **Môi trường thực hành**, chúng ta xây dựng quy trình **preflight**: kiểm tra các điều kiện tối thiểu theo thứ tự, trước khi khởi động hoặc kiểm thử ứng dụng. Quy trình này phải trả lời được ba câu hỏi:

1. **Kết nối được đúng Vault không?** Kiểm tra endpoint, mạng, TLS và danh tính máy chủ.
2. **Vault đã sẵn sàng phục vụ chưa?** Phân biệt initialized, sealed/unsealed, active/standby và health endpoint.
3. **Danh tính ứng dụng có làm được việc cần thiết không?** Thử bằng token/role của workload và một endpoint nghiệp vụ như đọc KV v2, thay vì chỉ dùng root token.

Sau bài này, bạn có thể:

- Chạy kiểm tra theo các tầng **DNS/port → TLS → Vault health → authentication → authorization → API nghiệp vụ**.
- Đọc đúng HTTP status từ **/v1/sys/health**, kể cả khi node là standby hoặc chưa unseal.
- Dùng Vault CLI, curl và OpenSSL để phân biệt lỗi server, TLS và policy.
- Cấu hình một phép smoke test **VaultTemplate** dùng token quyền tối thiểu.
- Thiết kế liveness/readiness và quyết định fail-fast hay degrade khi Vault không sẵn sàng.
- Viết các test và cảnh báo cho sự cố mất kết nối, sealed, token hết hạn, sai policy và sai certificate.

**Nguyên tắc an toàn:** Chỉ dùng dữ liệu và credential giả trong lab. Vault dev mode, root token cố định và HTTP qua loopback không phù hợp production. Không in token, secret ID, unseal key, mật khẩu hoặc nội dung secret vào log của ứng dụng hay hệ thống CI.

## 2. Quy trình kiểm tra từ ngoài vào trong

Không bắt đầu bằng cách thử lại **VaultTemplate** vô hạn. Hãy tìm lỗi ở tầng thấp nhất trước:

~~~mermaid
flowchart TB
    A["1. Đúng môi trường, URL, DNS và cổng?"] --> B{"TCP/HTTP có tới Vault?"}
    B -- "Không" --> B1["Kiểm tra container, DNS,<br/>firewall, port, proxy"]
    B -- "Có" --> C{"2. Nếu HTTPS:<br/>CA, SAN, certificate hợp lệ?"}
    C -- "Không" --> C1["Sửa truststore / hostname / TLS"]
    C -- "Có" --> D{"3. Vault đã init, unsealed,<br/>vai trò node phù hợp?"}
    D -- "Không" --> D1["Quy trình init/unseal/HA<br/>của người vận hành"]
    D -- "Có" --> E{"4. Token/login hợp lệ?"}
    E -- "Không" --> E1["Kiểm tra auth method,<br/>TTL, identity, role binding"]
    E -- "Có" --> F{"5. Policy cho phép<br/>API nghiệp vụ?"}
    F -- "Không" --> F1["Kiểm tra API path,<br/>capability, mount, namespace"]
    F -- "Có" --> G["6. Chạy smoke test Java<br/>và theo dõi readiness"]
~~~

| Tầng | Công cụ kiểm tra | Ví dụ kết quả lỗi | Không nên xử lý bằng |
| --- | --- | --- | --- |
| Địa chỉ, mạng | Docker, DNS, TCP, curl | Connection refused, DNS không tìm thấy, timeout | Sửa Vault policy |
| TLS | curl với CA, OpenSSL, JVM truststore | PKIX, hostname mismatch, certificate expired | Tắt xác minh chứng thư |
| Trạng thái Vault | **vault status**, **/v1/sys/health** | Uninitialized, sealed, mất quorum, standby | Thay client token ngay lập tức |
| Xác thực | Vault auth method, token lookup phù hợp | Token expired, AppRole secret ID hết lượt | Dùng root token trong ứng dụng |
| Phân quyền | Policy và request nghiệp vụ | 403 tại KV data/Transit/PKI | Cấp quyền **\*** toàn mount |
| Dữ liệu/API | CLI đúng mount, version, role | 404, key/role chưa tạo | Retry vô hạn |

**Kết nối được cổng 8200 chưa có nghĩa Vault đã sẵn sàng.** Ngược lại, một mã HTTP khác 200 cũng không nhất thiết là lỗi mạng: Vault có thể trả mã biểu thị trạng thái hợp lệ của một node standby.

## 3. Dựng Vault local để quan sát các trạng thái

### 3.1. Khởi tạo máy chủ dev có thể tạo lại

Ví dụ cần Docker Engine hoặc Docker Desktop, Docker Compose v2 và cổng host **8200** chưa được dùng. Trong một thư mục lab riêng, tạo **compose.yaml**:

~~~yaml
services:
  vault:
    image: hashicorp/vault:1.19.0
    cap_add:
      - IPC_LOCK
    command: server -dev -dev-listen-address=0.0.0.0:8200
    environment:
      VAULT_ADDR: http://127.0.0.1:8200
      VAULT_DEV_ROOT_TOKEN_ID: dev-root-only
      VAULT_TOKEN: dev-root-only
    ports:
      - "127.0.0.1:8200:8200"
    restart: "no"
~~~

Chạy từ thư mục có file Compose:

~~~bash
docker compose up -d
docker compose ps
docker compose logs --tail=60 vault
docker compose exec -T vault vault status
~~~

Kỳ vọng dev server báo **Initialized: true**, **Sealed: false**. Vault dev mode thường tự khởi tạo và unseal; **không** dùng trạng thái đó để suy ra một Vault non-dev đã được triển khai với storage bền vững, HA hay TLS.

Lệnh **docker compose exec -T vault vault ...** chạy Vault CLI ngay trong container, nên không bắt buộc cài Vault CLI trên host. Cổng host chỉ được công bố trên loopback **127.0.0.1**, còn Vault lắng nghe trên mọi interface **bên trong container** để Docker chuyển tiếp cổng.

**Cảnh báo:** Giá trị **dev-root-only** chỉ là root token giả có thể đoán được. Nó phục vụ việc tạo fixture lab và không bao giờ được dùng làm credential của Java trong staging/production. Các bài kiểm tra phân quyền bắt buộc thay bằng token giới hạn.

### 3.2. Tạo một endpoint nghiệp vụ để smoke test

Trước khi bật mount, liệt kê các secrets engine hiện có:

~~~bash
docker compose exec -T vault vault secrets list -detailed
~~~

Nếu chưa có **preflight-kv/**, tạo KV v2 mount và dữ liệu giả:

~~~bash
docker compose exec -T vault vault secrets enable -path=preflight-kv kv-v2
docker compose exec -T vault vault kv put -mount=preflight-kv apps/orders/config app_name=orders-training health_probe=ready
docker compose exec -T vault vault kv get -mount=preflight-kv apps/orders/config
~~~

Không lặp lại **secrets enable** trên mount đã tồn tại. Lệnh **kv put** chạy lại trên một key KV v2 sẽ tạo **version mới**, do đó cần xác định bạn đang bootstrap lab sạch hay đang kiểm tra một lab đã có dữ liệu. **preflight-kv/** là mount dành riêng cho bài, không dùng secret thật hoặc mount của ứng dụng khác.

Kiểm tra danh sách mount và key giúp xác nhận hai tầng độc lập: máy chủ có sẵn sàng hay không, và dữ liệu cần đọc đã được khởi tạo hay chưa.

## 4. Kiểm tra kết nối, DNS và phạm vi mạng

### 4.1. Xác định VAULT_ADDR theo nơi chạy client

| Nơi chạy client | Ví dụ địa chỉ | Lý do |
| --- | --- | --- |
| Vault CLI hoặc Java **trên host** | **http://127.0.0.1:8200** | Docker publish cổng lên loopback host |
| CLI **bên trong container Vault** | **http://127.0.0.1:8200** | Loopback của chính container Vault |
| Java **trong container khác cùng Compose network** | **http://vault:8200** | Dùng DNS service name **vault**, không dùng localhost của container Java |
| Java trên VM hoặc Kubernetes | HTTPS hostname được nền tảng cấp | Dùng DNS/service discovery và mạng của môi trường triển khai |

Không dùng **localhost** trong container Java để trỏ đến container Vault khác. **127.0.0.1** luôn chỉ interface loopback của **môi trường mạng hiện tại**, không có nghĩa “máy cài Docker” trong mọi trường hợp.

Trên máy host, thử:

~~~bash
curl -i http://127.0.0.1:8200/v1/sys/health
~~~

Nếu nhận được phản hồi HTTP từ Vault, kết nối qua Docker port mapping đã hoạt động. Nếu **connection refused**, kiểm tra container có chạy, port mapping đúng và cổng có bị dịch vụ khác chiếm không:

~~~bash
docker compose ps
docker compose logs --tail=80 vault
~~~

**Connection timeout** và **connection refused** là hai hiện tượng khác nhau: timeout có thể do tuyến mạng/firewall hoặc dịch vụ không đáp ứng; refused thường cho thấy không có listener tại địa chỉ và cổng đã kết nối tới. Chúng đều chưa chứng minh token hoặc policy sai.

### 4.2. Tránh kết nối nhầm môi trường

Trước khi chạy CLI hoặc ứng dụng, đối chiếu **scheme**, **host**, **port**, **Vault namespace nếu có**, **mount** và **auth method** với bảng cấu hình của môi trường. Một URI đúng cú pháp nhưng trỏ đến Vault khác vẫn là lỗi nghiêm trọng.

Trên Bash/zsh:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
printf 'Vault endpoint for this lab: %s\n' "$VAULT_ADDR"
~~~

Trên PowerShell:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
Write-Output ("Vault endpoint for this lab: " + $env:VAULT_ADDR)
~~~

Đoạn này chỉ in endpoint của **lab**, không in token. Nếu chạy kiểm thử tích hợp với Testcontainers, ứng dụng phải nhận host/port do container test cấp, không có fallback tự động về Vault trên máy người học hoặc Vault production.

## 5. Phân tích trạng thái máy chủ bằng Vault CLI và health API

### 5.1. Trạng thái initialized, sealed và vai trò HA

Các khái niệm này không đồng nghĩa:

- **Initialized:** Cụm Vault đã được khởi tạo cấu trúc khóa gốc và storage cần thiết. Vault non-dev mới thường chưa initialized; dev mode tự khởi tạo.
- **Sealed:** Vault không có đủ quyền truy cập vật liệu khóa để phục vụ các API nghiệp vụ. Non-dev có thể cần thao tác unseal hoặc auto-unseal tùy cấu hình.
- **Unsealed:** Vault đã mở khóa, nhưng còn cần kiểm tra vai trò node, storage, quorum và khả năng xử lý request.
- **Active / standby:** Trong mô hình HA, node active phục vụ thao tác chính; standby có vai trò khác theo cấu hình, có thể chuyển tiếp hoặc tham gia xử lý một số request tùy loại node/tính năng.
- **Healthy/ready:** Đánh giá *từ góc nhìn của client* rằng request cụ thể có thể được phục vụ, không chỉ rằng tiến trình còn chạy.

~~~mermaid
stateDiagram-v2
    [*] --> Uninitialized: non-dev cluster mới
    Uninitialized --> Sealed: operator init
    Sealed --> Unsealed: unseal / auto-unseal thành công
    Unsealed --> Active: được bầu làm active
    Unsealed --> Standby: node dự phòng
    Active --> Sealed: seal / mất điều kiện giải khóa
    Standby --> Active: chuyển vai khi đủ điều kiện HA
~~~

Sơ đồ mô tả một vòng đời điển hình; không phải mọi cách cấu hình đều sử dụng Shamir unseal thủ công. Một cluster Raft cũng cần quorum, storage và mạng phù hợp. Một node unsealed nhưng mất khả năng phục vụ API không nên được coi là ready chỉ từ trạng thái unsealed.

### 5.2. Lệnh vault status

Trong container lab:

~~~bash
docker compose exec -T vault vault status
~~~

Hoặc trên host có Vault CLI:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
vault status
~~~

**vault status** hiển thị các trường quan trọng như **Initialized**, **Sealed**, phiên bản, seal type và thông tin HA khi phù hợp. Lệnh này không nhất thiết cần client token để lấy trạng thái cơ bản, nhưng cần kết nối và TLS trust đúng nếu server sử dụng HTTPS.

**Đừng nhầm exit code khác 0 từ vault status với lỗi kết nối.** Vault CLI có thể dùng exit code để biểu thị trạng thái sealed hoặc lỗi khác; hãy đọc cả nội dung và nguyên nhân, không tự động khởi tạo lại cụm khi chỉ thấy lệnh trả mã khác 0.

### 5.3. Endpoint /v1/sys/health và mã HTTP

~~~bash
curl -i http://127.0.0.1:8200/v1/sys/health
~~~

Các mã trạng thái **mặc định thường gặp**:

| HTTP status | Ý nghĩa mặc định | Cách diễn giải |
| --- | --- | --- |
| **200** | Node active và sẵn sàng theo health API | Có thể tiếp tục kiểm tra credential/API nghiệp vụ |
| **429** | Standby node | Không đồng nghĩa service đã chết; xem chính sách traffic/failover |
| **472** | Disaster recovery secondary | Có vai trò DR; không mặc định nhận request nghiệp vụ như active |
| **473** | Performance standby khi cấu hình/tính năng hỗ trợ | Trạng thái phụ thuộc cách triển khai và loại request |
| **501** | Vault chưa initialized | Cụm mới cần quy trình init của người vận hành |
| **503** | Vault sealed | Cần unseal/auto-unseal hoặc khắc phục seal backend |

Các mã có thể được tùy chỉnh qua tham số health endpoint và thay đổi theo phiên bản/tính năng Vault. Vì vậy bảng là mốc để giải thích **mã mặc định**, không phải hợp đồng bất biến cho mọi hệ thống. Khi cấu hình load balancer, cần định nghĩa rõ health check muốn đo **node active**, **node chấp nhận request**, hay **tính sẵn sàng của cả cụm**.

Tham số health API như **standbyok=true** có thể được dùng trong một số cấu hình để coi standby là trạng thái chấp nhận được. Không thêm tham số này bừa bãi: một request tới standby có khả năng chuyển tiếp không có nghĩa mọi kết nối ứng dụng qua load balancer đã được kiểm chứng. Đối với performance standby, hành vi có thể khác theo cấu hình.

**Cẩn trọng với curl --fail:** Tùy chọn này có thể khiến công cụ trả exit code lỗi cho các HTTP status như 429, 501 hoặc 503. Khi đang chẩn đoán trạng thái, dùng **curl -i** để thấy **mã HTTP thật**, không suy ra mọi kết quả khác 200 đều là lỗi TCP/TLS.

### 5.4. Health check không thay thế request nghiệp vụ

Một phản hồi **HTTP 200** từ **/sys/health** không chứng minh:

- Client đã dùng đúng token hoặc AppRole của workload.
- Policy đã cho phép **preflight-kv/data/apps/orders/config**.
- KV v2 mount, key và version đang tồn tại.
- Transit key và PKI role phù hợp đã được tạo.
- Token còn đủ TTL để phục vụ workload trong khoảng thời gian cần thiết.

Health endpoint cần được dùng cùng một **smoke test có quyền tối thiểu**. Tránh gửi root token vào request chỉ để thấy HTTP 200.

## 6. Kiểm tra TLS trên Vault non-dev

Vault dev local mặc định dùng HTTP, nhưng Vault vận hành cần HTTPS với certificate được tin cậy và hostname khớp SAN. Một kiểm tra endpoint production hoặc staging phải kiểm tra TLS **trước** khi xem token/policy.

### 6.1. Kiểm tra CA và SAN với curl

Với máy chủ minh họa **https://vault.lab.internal:8200** và CA đã được người quản trị cung cấp qua kênh tin cậy:

~~~bash
curl -i --cacert /path/to/vault-ca.pem \
  https://vault.lab.internal:8200/v1/sys/health
~~~

Địa chỉ, CA và đường dẫn file là placeholder; không thể chạy nếu bạn chưa có Vault TLS server thật. **curl --cacert** xác minh chuỗi certificate và hostname theo tên trong URL; với chứng chỉ tự ký phòng lab, phải chọn đúng CA thay vì tin mặc định.

Nếu lỗi **certificate verify failed**, hãy xác định CA hoặc chain có đúng, server certificate còn hạn và SAN khớp **vault.lab.internal** không. Không dùng **curl -k** hoặc **--insecure** để biến phép kiểm tra này thành đạt; các tùy chọn đó bỏ qua cơ chế xác minh server.

### 6.2. Kiểm tra độc lập bằng OpenSSL

~~~bash
openssl s_client \
  -connect vault.lab.internal:8200 \
  -servername vault.lab.internal \
  -CAfile /path/to/vault-ca.pem \
  -verify_return_error \
  -verify_hostname vault.lab.internal
~~~

Tìm kết quả **Verify return code: 0 (ok)** và kiểm tra certificate SAN, issuer, validity. **-servername** cung cấp SNI; **-verify_hostname** xác minh hostname. Không chỉ dựa vào việc OpenSSL in ra certificate rồi kết luận đã xác minh thành công.

Nếu URL dùng **địa chỉ IP** thay tên DNS, server certificate cần SAN loại **IP**, không chỉ DNS SAN hoặc Common Name. Trên Java, lỗi CA thường có dạng **PKIX path building failed**, còn hostname sai thường thể hiện qua lỗi certificate/SAN mismatch.

### 6.3. Phân biệt CA của Vault CLI và JVM

Vault CLI trên host có thể dùng:

~~~bash
export VAULT_ADDR="https://vault.lab.internal:8200"
export VAULT_CACERT="/path/to/vault-ca.pem"
vault status
~~~

**VAULT_CACERT** ảnh hưởng tới Vault CLI, không tự động cấu hình JSSE truststore cho JVM chạy Spring Vault. Với Java cần truststore/HTTP client SSL configuration phù hợp, ví dụ PKCS#12 chứa CA được tin cậy. Đường dẫn truststore phải tồn tại **trong môi trường chạy JVM**; một đường dẫn có thật trên host có thể không tồn tại trong container Java.

Mật khẩu truststore (nếu được yêu cầu), client token và private key cần được phân phối an toàn. Không viết mật khẩu truststore vào dòng lệnh có thể bị ghi history/process listing khi triển khai thật.

## 7. Kiểm tra token, policy và API nghiệp vụ

### 7.1. Dùng policy chỉ đọc thay cho root token

Tạo thư mục **policies/** ở cạnh tệp Compose và tạo **policies/preflight-reader.hcl**:

~~~hcl
path "preflight-kv/data/apps/orders/config" {
  capabilities = ["read"]
}
~~~

Nạp policy và tạo token ngắn hạn bằng CLI quản trị của Vault dev:

~~~bash
docker compose cp policies/preflight-reader.hcl vault:/tmp/preflight-reader.hcl
docker compose exec -T vault vault policy write preflight-reader /tmp/preflight-reader.hcl
docker compose exec -T vault vault policy read preflight-reader
docker compose exec -T vault vault token create -policy=preflight-reader -ttl=15m -field=token
~~~

Lệnh cuối in ra một **client token dành cho lab**. Không đưa token này vào file Compose, Java source hoặc Git. Với Bash/zsh, lưu token ở biến của phiên terminal:

~~~bash
export APP_VAULT_TOKEN="<token-preflight-reader-vua-tao>"
~~~

PowerShell:

~~~powershell
$env:APP_VAULT_TOKEN = "<token-preflight-reader-vua-tao>"
~~~

Một token có thể được gắn thêm **default policy** hoặc các chính sách khác; khi kiểm tra phân quyền, hãy biết **tập policy thực tế** của token. Tạo token bằng root ở phòng lab là thao tác bootstrap, không có nghĩa Java cần root token.

### 7.2. Chứng minh token đọc được secret cần thiết

Compose đã cấu hình root token trong môi trường container. Vì vậy phải **ghi đè VAULT_TOKEN** trong mỗi lệnh thử:

~~~bash
# Bash / zsh
docker compose exec -T -e "VAULT_TOKEN=$APP_VAULT_TOKEN" vault vault kv get -mount=preflight-kv apps/orders/config
docker compose exec -T -e "VAULT_TOKEN=$APP_VAULT_TOKEN" vault vault kv put -mount=preflight-kv apps/orders/config app_name=should-not-write
~~~

Tương đương với PowerShell:

~~~powershell
docker compose exec -T -e "VAULT_TOKEN=$env:APP_VAULT_TOKEN" vault vault kv get -mount=preflight-kv apps/orders/config
docker compose exec -T -e "VAULT_TOKEN=$env:APP_VAULT_TOKEN" vault vault kv put -mount=preflight-kv apps/orders/config app_name=should-not-write
~~~

Kỳ vọng: **kv get** trả secret giả đã seed; **kv put** bị **403 permission denied** vì token chỉ có **read**. Nếu put vẫn thành công, dừng phép thử và kiểm tra lại token/policy: rất có thể request vẫn đang dùng root token hoặc một token có quyền rộng.

Đối chiếu đường dẫn:

| Cách gọi | Giá trị đúng |
| --- | --- |
| Mount KV v2 | **preflight-kv/** |
| Logical key | **apps/orders/config** |
| CLI đọc | **vault kv get -mount=preflight-kv apps/orders/config** |
| HTTP GET | **/v1/preflight-kv/data/apps/orders/config** |
| Vault policy | **path "preflight-kv/data/apps/orders/config"** |
| Spring Vault | **opsForVersionedKeyValue("preflight-kv").get("apps/orders/config")** |

Đối với KV v2, API path phải chứa **data/**, còn logical key truyền vào **vault kv** hoặc **opsForVersionedKeyValue** không có **data/**. Sai phân đoạn này có thể tạo ra **403/404** dù Vault health là 200.

### 7.3. Token hợp lệ khác với quyền trên mọi endpoint

Có thể kiểm tra token bằng:

~~~bash
docker compose exec -T -e "VAULT_TOKEN=$APP_VAULT_TOKEN" vault vault token lookup
~~~

Lệnh thường cho thấy **policies**, **ttl**, **renewable** và một số metadata, khi token được phép gọi endpoint **lookup-self**. Nếu tổ chức đã bỏ default policy hoặc thu hẹp quyền lookup, thao tác này có thể bị chặn; khi đó không thể kết luận token hoàn toàn vô dụng chỉ từ lỗi lookup. **Request đọc KV thực tế** là phép thử quan trọng nhất cho chức năng nghiệp vụ.

Phân biệt:

- **Xác thực:** token được Vault chấp nhận, hoặc workload đăng nhập AppRole/Kubernetes/JWT/cloud auth thành công.
- **Phân quyền:** token được cấp capability **read**, **update**, **create** hay thao tác cụ thể trên đúng API path.
- **Dữ liệu sẵn có:** engine, logical key và version yêu cầu thực sự tồn tại.

Ví dụ: token hợp lệ nhưng không có quyền **preflight-kv/data/apps/orders/config** sẽ không đọc được KV. Một token có quyền đọc KV cũng không tự có quyền **lab-transit/encrypt/...** hoặc **lab-pki/issue/...**.

### 7.4. Auth method theo workload

Ở local, token cấp thủ công là công cụ kiểm tra nhanh. Với môi trường triển khai, danh tính workload có thể được xác thực bằng **AppRole**, **Kubernetes**, **JWT/OIDC** hoặc phương thức cloud auth phù hợp:

~~~text
Workload identity
   -> auth/<mount>/login
   -> Vault client token có policy
   -> request KV / Transit / PKI
   -> Vault kiểm tra capability tại path cụ thể
~~~

Đối với AppRole, **role_id + secret_id** dùng để lấy token; secret ID có TTL và giới hạn lượt dùng riêng. Token mới có TTL/renewal policy riêng, có thể hết hạn hoặc bị revoke sau khi login. Không đặt AppRole secret ID, root token hoặc unseal key vào source code để “kiểm tra kết nối” ở startup.

## 8. Smoke test tối thiểu bằng Spring Vault

### 8.1. Kết nối Java tới đúng endpoint

Sau khi các kiểm tra CLI thành công, dùng **Spring Vault Core** (dependency **org.springframework.vault:spring-vault-core** với phiên bản tương thích dự án) để truy cập cùng KV v2 key.

Ví dụ Java độc lập:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

public class VaultPreflightCheck {

    public static void main(String[] args) {
        String address = System.getenv("VAULT_ADDR");
        String token = System.getenv("APP_VAULT_TOKEN");

        if (address == null || address.isBlank()
                || token == null || token.isBlank()) {
            throw new IllegalStateException(
                    "VAULT_ADDR and APP_VAULT_TOKEN are required");
        }
        URI uri = URI.create(address);
        if (uri.getHost() == null
                || (!"http".equalsIgnoreCase(uri.getScheme())
                    && !"https".equalsIgnoreCase(uri.getScheme()))) {
            throw new IllegalArgumentException("Invalid Vault URI");
        }

        VaultTemplate template = new VaultTemplate(
                VaultEndpoint.from(uri),
                new TokenAuthentication(token));

        Versioned<Map<String, Object>> result = template
                .opsForVersionedKeyValue("preflight-kv")
                .get("apps/orders/config");

        if (result == null || result.getData() == null) {
            throw new IllegalStateException(
                    "Preflight KV config is missing");
        }
        if (!"orders-training".equals(result.getData().get("app_name"))) {
            throw new IllegalStateException(
                    "Unexpected preflight dataset");
        }

        // Không in giá trị secret, raw Vault response hoặc token.
        System.out.println("Vault preflight KV read: OK");
    }
}
~~~

Ví dụ này dùng **TokenAuthentication** để tách biệt vấn đề kết nối/đọc KV; nó **không** tự gia hạn token hoặc đăng nhập lại. Ứng dụng chạy dài hạn cần **ClientAuthentication** và **SessionManager** phù hợp với auth method, TTL và vòng đời credential được cấp.

Trên Bash/zsh, đặt URI của Vault local:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
# APP_VAULT_TOKEN đã được cấp bằng policy preflight-reader.
~~~

Trên PowerShell:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
# APP_VAULT_TOKEN đã được cấp bằng policy preflight-reader.
~~~

Khi cả mạng, TLS (nếu dùng HTTPS), Vault state, auth token, policy và secret đều phù hợp, chương trình in thông báo **Vault preflight KV read: OK**. Cần nhớ rằng root token hoặc endpoint khác có thể làm test “thành công giả”; dùng đúng token hạn chế đã thử ở mục 7.

### 8.2. Với HTTPS, JVM phải có truststore phù hợp

Trường hợp Vault non-dev dùng CA riêng, JVM phải tin CA phát hành server certificate và đối chiếu SAN với hostname. Ví dụ cấu hình cho một Java process thông qua JVM properties (chỉ minh họa):

~~~text
-Djavax.net.ssl.trustStore=/path/inside/runtime/vault-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Khi cần mật khẩu để tải truststore, hãy cung cấp nó an toàn qua cơ chế của runtime; không ghi mật khẩu vào script hoặc file được commit. Nếu Spring Vault sử dụng một HTTP client có **SSLContext riêng**, phải cấu hình truststore trên đúng client đó; JVM system properties không tự tác động lên mọi SSLContext tùy chỉnh.

Một request thành công bằng **Vault CLI** với **VAULT_CACERT** không có nghĩa Java tự tin CA. Trước khi sửa code KV, hãy xác minh quá trình tạo **VaultTemplate** và HTTP client đang dùng cấu hình TLS đúng.

### 8.3. Smoke test không được gây tác dụng phụ ngoài ý muốn

Phép kiểm tra trước startup nên **chỉ đọc dữ liệu giả hoặc key thực sự cần thiết**. Đừng đặt lệnh tạo KV version, cấp PKI certificate, xoay Transit key hoặc tạo dynamic credential chỉ để biết Vault có hoạt động. Những thao tác đó có thể phát sinh tài nguyên/lease và bị lặp lại mỗi lần pod khởi động hoặc health checker chạy.

Nếu ứng dụng không cần một secret cụ thể cho chức năng cốt lõi, không nhất thiết phải bắt cả ứng dụng fail startup khi secret ấy vắng mặt. Ngược lại, nếu một secret bắt buộc để bảo vệ dữ liệu hoặc xác thực database, khởi động “thành công” nhưng tiếp tục hoạt động khi thiếu secret có thể gây lỗi hoặc rủi ro. Phải xác định yêu cầu nghiệp vụ để chọn chiến lược readiness.

## 9. Thiết kế fail-fast, readiness và liveness

### 9.1. Không trộn lẫn ba mục tiêu kiểm tra

| Kiểm tra | Câu hỏi trả lời | Nên phụ thuộc vào Vault đến mức nào? |
| --- | --- | --- |
| **Preflight trước deploy/start** | Môi trường, endpoint, TLS, Vault status và credential có đúng? | Có thể kiểm tra sâu, bao gồm một read nghiệp vụ được cấp quyền |
| **Readiness** | Instance này có nhận request cần Vault ngay lúc này không? | Theo tính năng cốt lõi, trạng thái cache và cơ chế phục hồi |
| **Liveness** | Tiến trình có bị kẹt đến mức cần restart không? | Không nên phụ thuộc trực tiếp vào tình trạng tạm thời của Vault |

Nếu liveness của mọi instance liên tục gọi Vault và coi một lần timeout là “process chết”, một sự cố Vault ngắn có thể tạo **restart storm** ở toàn bộ ứng dụng. Readiness nên phản ánh khả năng phục vụ người dùng, còn liveness chủ yếu xác định tiến trình có còn hoạt động đủ để tự phục hồi hay không.

### 9.2. Chọn fail-fast hay degrade có kiểm soát

**Fail-fast phù hợp khi**:

- Thiếu secret bắt buộc để ứng dụng vận hành an toàn.
- Không thể xác minh chứng thư server hoặc đang trỏ đến sai môi trường.
- Workload không thể lấy token vì sai cấu hình danh tính.
- Policy cần thiết bị từ chối và ứng dụng không có phương án thay thế hợp lệ.

**Degrade có kiểm soát có thể phù hợp khi**:

- Một tính năng phụ cần Vault nhưng phần còn lại không phụ thuộc vào nó.
- Ứng dụng đã có dữ liệu được cache hợp lệ trong thời hạn mà chính sách cho phép.
- Cơ chế làm mới credential có thể thử lại có giới hạn mà không làm lộ hoặc dùng credential đã hết hạn.

Không đưa secret từ cache vào log để “chữa” lỗi Vault. Với credential động, TTL của credential bên ngoài và lease trong Vault cần được theo dõi, không thể giả định giá trị cache dùng được vô hạn.

### 9.3. Mẫu preflight khi khởi động Spring Boot

Nếu nghiệp vụ cần đọc secret ngay lúc startup, có thể dùng **ApplicationRunner** để thực hiện một read đã biết. Ví dụ:

~~~java
import java.util.Map;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

@Component
@Profile("local")
public class LocalVaultStartupGate implements ApplicationRunner {

    private final VaultTemplate template;

    public LocalVaultStartupGate(VaultTemplate template) {
        this.template = template;
    }

    @Override
    public void run(ApplicationArguments args) {
        Versioned<Map<String, Object>> result = template
                .opsForVersionedKeyValue("preflight-kv")
                .get("apps/orders/config");

        if (result == null || result.getData() == null) {
            throw new IllegalStateException(
                    "Required local Vault fixture is unavailable");
        }
    }
}
~~~

Đây là **ví dụ dành cho local**, yêu cầu ứng dụng đã có một bean **VaultTemplate** được cấu hình theo môi trường. Ném exception từ runner có thể khiến startup của Spring Boot thất bại, phù hợp với kiểu preflight có tính bắt buộc. Không đưa mount/key lab vào production bằng cách gỡ **@Profile("local")** mà chưa thiết kế cấu hình và readiness riêng.

Nếu ứng dụng cần đọc nhiều loại secret, không nên thực hiện một loạt thao tác có tác dụng phụ tại startup. Nên xác định tập kiểm tra tối thiểu và timeout hợp lý, đo độ trễ và giới hạn retry để tránh tăng tải Vault khi một nhóm instance được triển khai cùng lúc.

### 9.4. Health probe không nên có credential rộng

Khi triển khai, load balancer hoặc orchestrator có thể gọi **/sys/health** của Vault hoặc endpoint health của ứng dụng. Không dùng root token để poll health; Health API được thiết kế để cung cấp trạng thái thích hợp mà không cần đọc secret.

Nếu readiness phía ứng dụng cần biết workload có đọc được secret, nên thực hiện kiểm tra phù hợp với **quyền hiện có của workload**, đặt tần suất, timeout và cache kết quả hợp lý. Không cấp quyền **list**, **update**, **delete** hay quản trị Vault chỉ vì health probe yêu cầu một kết quả thành công.

Với HA Vault, quyết định chấp nhận active/standby phải căn cứ kiến trúc traffic và cách proxy/load balancer route request; không tự coi 429 từ một node standby là bằng chứng toàn cụm đã mất khả năng phục vụ.

## 10. Diễn giải lỗi theo nguyên nhân, không theo suy đoán

| Hiện tượng | Nhóm nguyên nhân ưu tiên | Hướng xác minh |
| --- | --- | --- |
| **Connection refused** | Container/listener chưa chạy hoặc sai host/port | **docker compose ps**, log Vault, VAULT_ADDR |
| **Timeout** | DNS, firewall, network policy, Vault quá tải hoặc mạng gián đoạn | Thử host/port, log, métrics network |
| **SSLHandshakeException / PKIX** | JVM không tin CA hoặc chain không hợp lệ | Truststore, certificate issuer/chain |
| **Hostname mismatch** | URL không khớp SAN | Tên DNS/IP trong URL và SAN certificate |
| **HTTP 501** từ health | Vault chưa initialized | Quy trình operator init do người quản trị thực hiện |
| **HTTP 503** từ health | Vault sealed | Operator unseal/auto-unseal, seal backend |
| **HTTP 429** từ health | Node standby theo mã mặc định | Topology HA, health policy, redirect/forwarding |
| **HTTP 403** khi đăng nhập | Sai role binding, secret ID/JWT/token hoặc chính sách auth | Auth mount, TTL, workload identity |
| **HTTP 403** khi đọc KV | Thiếu **read** trên KV v2 **data/** hoặc token không hợp lệ | Policy, mount, path, token TTL |
| **HTTP 404** hoặc null | KV key/version không tồn tại hoặc endpoint sai | CLI với đúng mount, metadata/version |
| **Transit encrypt/decrypt lỗi** | Key/role/capability sai | Path **transit/encrypt/** hoặc **transit/decrypt/** |
| **PKI issue lỗi** | Role hạn chế common name/TTL hoặc thiếu quyền | PKI role, API **issue/**, policy |
| Token hoạt động rồi hết hạn | TTL hết, revoke hoặc session không renew/re-login | SessionManager, auth method, token lifecycle |

Một lỗi **403** không chắc phản ánh secret tồn tại hay không; Vault có thể từ chối trước khi công bố thông tin về key. Khi token có quyền nhưng key không tồn tại, Spring Vault có thể trả **null**, exception hoặc kết quả khác tùy endpoint/client. Không dùng 404/403 để kích hoạt việc cấp quyền rộng hoặc tự tạo secret trong production.

**Retry:** Với lỗi mạng hoặc một số lỗi 5xx tạm thời, có thể retry hữu hạn với backoff và jitter. Với sai CA, thiếu policy, role sai hoặc key chưa seed, retry nhiều lần không sửa được nguyên nhân. Với thao tác **ghi KV**, **Transit**, **PKI issue** hoặc cấp credential động, cần xét idempotency và khả năng request trước đã thành công dù client bị timeout.

## 11. Runbook preflight trước khi chạy ứng dụng

### 11.1. Kiểm tra từ máy host

Trên máy cá nhân đang chạy Vault dev của bài:

~~~bash
# 1. Tiến trình và port mapping
docker compose ps

# 2. Vault trả health status gì?
curl -i http://127.0.0.1:8200/v1/sys/health

# 3. CLI đọc trạng thái Vault trong container
docker compose exec -T vault vault status

# 4. Mount KV v2 đã được enable?
docker compose exec -T vault vault secrets list -detailed

# 5. Data fixture có tồn tại?
docker compose exec -T vault vault kv get -mount=preflight-kv apps/orders/config
~~~

Các lệnh từ bước 4–5 dùng **root token dev để kiểm tra bootstrap**; chúng không thay thế phép thử với token ứng dụng. Sau khi xác minh fixture, chạy với token **APP_VAULT_TOKEN** theo mục 7 rồi mới thực hiện smoke test Java.

### 11.2. Bảng quyết định chạy/không chạy

| Kết quả kiểm tra | Quyết định đối với bài thực hành | Hành động |
| --- | --- | --- |
| Container chưa chạy | **Chưa chạy Java** | Sửa Compose, log, port |
| Không kết nối được HTTP/TLS | **Chưa chạy Java** | Sửa endpoint, mạng, DNS, CA/SAN |
| **501** chưa initialized | **Chưa chạy workload** | Người quản trị init cụm mới theo quy trình |
| **503** sealed | **Chưa chạy workload phụ thuộc Vault** | Người vận hành unseal/khắc phục seal backend |
| **429** từ standby | **Chưa kết luận cả cụm lỗi** | Kiểm tra kiến trúc HA, active endpoint, routing |
| Health **200**, mount thiếu | **Chưa chạy smoke test nghiệp vụ** | Bootstrap đúng mount trên lab |
| Health **200**, token đọc bị 403 | **Chưa chạy app phụ thuộc key** | Kiểm tra auth/policy, không dùng root |
| Health **200**, token đọc key đúng | **Có thể chạy smoke test Java** | Đối chiếu Java URI, mount, TLS, policy |
| Java đọc thành công, readiness phù hợp | **Đạt preflight theo phạm vi bài** | Bắt đầu thực hành KV/Transit/PKI |

Ở production, “chưa chạy” có thể nghĩa **không đưa instance vào readiness**, thay vì luôn dừng toàn bộ quy trình deploy. Đội vận hành cần xác định ngưỡng chấp nhận và phương án khôi phục theo chức năng nghiệp vụ; bài này không mặc định mọi sự cố Vault đều yêu cầu restart ứng dụng.

### 11.3. Khi Vault dùng HTTPS ở staging/production

Thay bước kiểm tra HTTP bằng:

~~~bash
# Tất cả đường dẫn và hostname sau là ví dụ; cần CA/endpoint thật.
curl -i --cacert /path/to/vault-ca.pem \
  https://vault.lab.internal:8200/v1/sys/health
~~~

Tiếp theo xác minh **đúng credential của workload** có thể đọc một endpoint được phép. Nếu workload dùng AppRole, Kubernetes hoặc JWT auth, nên thực hiện đăng nhập bằng cơ chế đó rồi mới đọc KV; một token quản trị nhập bằng tay không chứng minh cấu hình workload đã đúng.

Để tránh chẩn đoán sai: kiểm tra **Vault server endpoint** không thay cho kiểm tra **chứng thư và kết nối từ nơi ứng dụng thật chạy**. Lệnh curl chạy trên máy quản trị có thể thành công, còn pod Java vẫn thiếu DNS/network route hoặc truststore trong container.

## 12. Giám sát và cảnh báo trạng thái Vault/Spring Vault

Preflight chỉ kiểm tra một thời điểm. Khi ứng dụng chạy lâu dài, Vault có thể đổi vai trò active/standby, token có thể hết hạn, mạng có thể lỗi hoặc certificate có thể gần hết hạn. Cần quan sát liên tục nhưng không lạm dụng health polling.

| Tín hiệu | Nguồn tham khảo | Cần theo dõi |
| --- | --- | --- |
| Trạng thái init/seal/HA | Vault health, log và metrics phù hợp | Sealed, mất active/quorum, thay đổi vai trò |
| Kết nối HTTPS | HTTP client/JVM, TLS monitoring | TLS handshake error, certificate sắp hết hạn |
| Request tới Vault | Metrics của HTTP client Spring Vault | Thời gian gọi, tỉ lệ timeout, lỗi 403/404/5xx |
| Token/session | SessionManager/auth integration | Login fail, renew fail, TTL gần hết nếu quan sát được an toàn |
| KV/Transit/PKI | Tracing và audit có kiểm soát | Thao tác thường lỗi, role/policy bị từ chối |
| Độ sẵn sàng ứng dụng | Spring Boot health/readiness và endpoint nghiệp vụ | Khả năng phục vụ request phụ thuộc Vault |

Vault có các cơ chế audit và telemetry nhưng **không tự bật đầy đủ** chỉ vì server chạy non-dev. Khi dùng audit log, cần cấu hình device, độ tin cậy của đích ghi, retention và quyền truy cập. Không ghi token, raw secret, mật khẩu, private key hoặc plaintext Transit vào application log.

Một hệ thống giám sát hữu ích cần phân biệt:

- **Một node standby trả 429** với **cả cụm không có active phục vụ**.
- **Một yêu cầu bị policy từ chối 403** với **dịch vụ mạng không kết nối được**.
- **KV key không có** với **workload không có quyền biết key ấy tồn tại**.
- **Token cần renew/re-login** với **Vault cần unseal hoặc certificate cần cấp lại**.

Với sự cố phụ thuộc chung như Vault không sẵn sàng, nên giới hạn retry, có backoff/jitter và cảnh báo ở mức cụm để tránh quá nhiều instance cùng liên tục đăng nhập lại hoặc poll health.

## 13. Thiết kế kiểm thử trạng thái và sự cố

### 13.1. Không dùng production Vault cho test phá hoại

Có thể dùng **Testcontainers VaultContainer** để chạy một Vault dev riêng mỗi test suite và seed dữ liệu/policy giả trước khi khởi tạo ứng dụng. Endpoint phải được inject theo host/port động, không hardcode **127.0.0.1:8200**. Test runner cần bảo đảm:

1. Có một Vault độc lập với data fixture của suite.
2. Policy và client token được cấp riêng cho test, không lấy từ môi trường production.
3. Spring Vault client kết nối đúng test container.
4. Sau khi test, container và credential được dọn đúng phạm vi.

Các bài kiểm tra **sealed**, **uninitialized**, **HA standby** nên sử dụng môi trường kiểm thử phù hợp với trạng thái cần mô phỏng. Dev mode thường tự init/unseal nên không thể dùng nó để kiểm chứng mọi nhánh trong vòng đời non-dev hoặc failover HA. Không cố **seal** một Vault dùng chung chỉ để tạo lỗi cho test.

### 13.2. Ma trận kiểm thử đề xuất

| Tình huống | Cách tạo điều kiện trong môi trường sở hữu | Kết quả mong đợi |
| --- | --- | --- |
| Vault chạy, fixture có sẵn | Seed KV v2 + policy reader | Health phù hợp, Java read thành công |
| Vault chưa chạy | Dừng test container riêng | Connection error hoặc timeout, phân loại đúng |
| Token hết hạn/revoke | Dùng TTL ngắn hoặc revoke token test | Request bị từ chối hoặc session xử lý theo thiết kế |
| Token thiếu quyền | Token chỉ có policy khác | KV read trả lỗi quyền, không fallback root |
| Key không tồn tại | Dùng logical key chưa seed | Null/404 được xử lý rõ ràng |
| Mount không tồn tại | Chỉ đổi mount trong test config | Không kết luận nhầm là TLS lỗi |
| TLS CA sai | Dùng truststore không chứa CA server test | Handshake bị từ chối |
| Hostname SAN sai | Kết nối server TLS test bằng hostname không có trong SAN | Handshake bị từ chối |
| Vault sealed | Non-dev lab riêng và quy trình seal an toàn | Health phản ánh sealed, app không nhận request cần Vault |
| HA standby | Cụm test HA thực tế | Phân biệt standby/active và routing |
| Transit/PKI policy | Gọi bằng token không có quyền endpoint | 403 đúng path; không tạo secret/certificate ngoài ý muốn |
| Lỗi lease/token renewal | Test fixture có credential ngắn hạn phù hợp | Renewal/re-login có giới hạn, không leak credential |

Với bài test timeout, không retry vô hạn và không tạo loop quá ngắn. Khi một request có tác dụng thay đổi dữ liệu bị timeout, cần kiểm tra tính idempotent hoặc dùng cơ chế đối chiếu kết quả để tránh tạo thêm version, certificate hay credential không mong muốn.

## 14. Dọn dẹp và khôi phục lab

Kết thúc bài, nếu không còn ứng dụng nào cần Vault dev:

~~~bash
docker compose down
~~~

Với **dev mode** của bài này, tiến trình Vault lưu trạng thái trong bộ nhớ nên mount, secret giả và token tạo ở phiên cũ có thể không còn khi khởi động lại. Cần chạy lại các bước enable/seed nếu muốn lặp lại bài.

Không hiểu nhầm **docker compose down** là thao tác xoá toàn bộ dữ liệu ở mọi kiểu Vault. Với Vault non-dev dùng storage bền vững, dữ liệu có thể còn sau khi dừng container; xóa volume hoặc tháo mount là thao tác có hậu quả khác hẳn. Không chạy **vault secrets disable**, xóa mount/volume hoặc **vault operator init** lặp lại trên một cụm không rõ trạng thái chỉ để sửa lỗi preflight.

Đối với token ứng dụng, sau khi đã xác minh biến chứa **đúng token lab không phải root token**, bạn có thể revoke token đó theo quy trình thử nghiệm hoặc để nó hết TTL ngắn. Thu hồi token không xóa KV secret; xóa KV version cũng không tự thu hồi mọi token. Nếu bạn đã sao chép token ra file hoặc log, dọn container không làm bản sao đó biến mất.

**Kiểm tra cuối cùng** gồm việc không còn process Java/test đang dùng lab, không còn credential test cần sử dụng, và không có file cấu hình local chứa bí mật thật. Không dọn Vault server hoặc mount mà người học/nhóm khác đang sử dụng.

## 15. Bài tập áp dụng

**Bài 1 — Chẩn đoán ba tầng đầu.** Tắt Vault dev container riêng của bạn, chạy curl tới **/v1/sys/health** và ghi nhận lỗi mạng. Khởi động lại, so sánh kết quả. Giải thích vì sao hai kết quả chưa nói gì về policy của token Java.

**Bài 2 — Health khác quyền đọc KV.** Tạo token chỉ có policy **preflight-reader**, gọi **/v1/sys/health**, đọc **apps/orders/config**, rồi thử ghi cùng key. Chứng minh health hoạt động và read thành công nhưng write bị 403.

**Bài 3 — Đường dẫn KV v2.** Viết bốn cách biểu diễn của cùng secret: lệnh CLI, HTTP path, policy path và lời gọi VaultTemplate. Cố ý bỏ **data/** khỏi policy và giải thích nguyên nhân request bị từ chối.

**Bài 4 — TLS tin cậy.** Với một Vault HTTPS lab riêng có certificate hợp lệ, dùng curl và OpenSSL xác minh CA/SAN. Thử CA hoặc hostname sai và xác minh lỗi xảy ra **trước** giai đoạn kiểm tra policy; không sử dụng tùy chọn bỏ qua TLS verification.

**Bài 5 — Node standby và sealed.** Vẽ bảng giải thích các mã **200, 429, 472, 473, 501, 503** mặc định. Với một Vault non-dev lab riêng, mô tả bước cần thiết để khởi tạo/unseal. Chỉ kiểm chứng thực tế khi có môi trường sở hữu; không tác động cụm chia sẻ.

**Bài 6 — Readiness và liveness.** Thiết kế hai endpoint sức khỏe cho Orders API: liveness không phụ thuộc trực tiếp Vault tạm thời mất kết nối; readiness phụ thuộc khả năng phục vụ chức năng bắt buộc. Giải thích ngưỡng timeout, tần suất kiểm tra và cách tránh restart storm.

**Bài 7 — Vòng đời credential.** Tạo một token ngắn hạn cho lab và quan sát khi token không còn hợp lệ. So sánh với AppRole secret ID hết lượt dùng, credential động có lease và chứng chỉ PKI hết hiệu lực; đề xuất cơ chế renew/re-login hoặc cấp mới theo đúng loại tài nguyên.

**Bài 8 — Kiểm thử tích hợp.** Thiết kế một suite dùng Vault Testcontainers có ít nhất bốn ca: read KV thành công, thiếu quyền 403, secret không tồn tại và Vault container dừng. Chỉ ra cách truyền URI/port động và token test cho Spring Vault mà không dùng root token làm credential nghiệp vụ.

## 16. Checklist trước khi chạy ứng dụng

- [ ] Đã xác định đúng **môi trường**, **VAULT_ADDR**, cổng, namespace (nếu có) và mount.
- [ ] Đã kiểm tra DNS/TCP/HTTP hoặc HTTPS từ **chính nơi Java sẽ chạy**.
- [ ] Với HTTPS, CA chain và hostname SAN hợp lệ; JVM sử dụng truststore đúng.
- [ ] Đã đọc **vault status** và **/v1/sys/health**; biết diễn giải active, standby, uninitialized và sealed.
- [ ] Không nhầm trạng thái health của Vault với quyền truy cập secret của workload.
- [ ] Đã tạo dữ liệu giả trong **preflight-kv/** và biết API path KV v2 có **data/**.
- [ ] Token/role của ứng dụng chỉ có quyền cần thiết; phép thử ghi trái quyền bị từ chối.
- [ ] Đã thực hiện read smoke test bằng CLI và **VaultTemplate** với **đúng token hạn chế**.
- [ ] Không dùng root token, unseal key, AppRole secret ID hoặc private key trong code/log.
- [ ] Phân biệt được lỗi kết nối, TLS, sealed, auth, policy, secret không tồn tại và TTL/lease.
- [ ] Đã quyết định rõ khi nào fail-fast, khi nào degrade, và readiness khác liveness ra sao.
- [ ] Có giới hạn timeout/retry và kịch bản kiểm thử cho những lỗi quan trọng.
- [ ] Dọn môi trường đúng phạm vi và không xóa tài nguyên Vault không thuộc bài.

**Kết luận:** Preflight hiệu quả cho Spring Vault là kiểm tra theo thứ tự **đúng đích → kết nối/TLS → trạng thái Vault → danh tính workload → policy/API path → VaultTemplate**. Khi các tầng được xác minh riêng, bạn sẽ biết lúc nào cần sửa hạ tầng, certificate, token, policy hoặc dữ liệu KV, thay vì thay đổi mã Java hoặc mở rộng quyền một cách thiếu kiểm soát.
