# Khởi tạo dữ liệu mẫu và mount riêng cho bài thực hành

## 1. Mục tiêu bài học

Khi học **Spring Vault**, một ứng dụng Java có thể dùng **VaultTemplate** để đọc KV secrets, mã hóa dữ liệu với Transit, xin chứng chỉ từ PKI và xác thực bằng token hoặc danh tính workload. Để những ví dụ đó kiểm chứng được, trước tiên cần chuẩn bị **mount**, **dữ liệu giả lập** và **quyền truy cập** có tổ chức trong HashiCorp Vault.

Một lỗi phổ biến khi học là sử dụng mọi loại secret dưới cùng một tên đường dẫn, dùng root token cho ứng dụng, hoặc để dữ liệu của các bài tập chồng lên nhau. Bài này xây dựng một phòng lab có thể tạo lại, trong đó mỗi secrets engine được gắn tại một mount riêng, dữ liệu mẫu có tên rõ ràng, và quyền truy cập của ứng dụng được kiểm tra độc lập.

Sau khi hoàn thành, bạn có thể:

1. Giải thích sự khác nhau giữa **secrets engine**, **mount path**, **secret path**, và **auth mount**.
2. Tạo các mount riêng cho **KV v2**, **Transit** và **PKI**, kể cả một mount KV thử nghiệm độc lập để tránh ảnh hưởng dữ liệu chính.
3. Khởi tạo dữ liệu giả, kiểm tra phiên bản KV v2 và quan sát dữ liệu qua Vault CLI/API.
4. Viết policy đọc có giới hạn, cấp token ngắn hạn và chứng minh ứng dụng không thể truy cập mount khác.
5. Đọc dữ liệu bằng **VaultTemplate** mà không để lộ giá trị secret trong log.
6. Lặp lại quá trình bootstrap, nhận biết các lệnh không an toàn khi chạy lại và chuẩn bị dữ liệu cho các bài về AppRole, token/lease, Transit, PKI và kiểm thử tích hợp.

**Nguyên tắc:** Chỉ sử dụng dữ liệu giả; mọi URL, mật khẩu và khóa API dưới đây đều dùng để minh họa. Vault dev mode, HTTP và root token cố định chỉ phù hợp với máy cá nhân và môi trường thử nghiệm tạm thời.

## 2. Thiết kế namespace thực hành

### 2.1. Mount không phải thư mục thông thường

Trong Vault, một **secrets engine** xử lý một loại thao tác hoặc secret; một **mount path** là tiền tố API tại đó engine được kích hoạt. Các secret cụ thể nằm dưới mount. Ví dụ:

~~~text
Vault
├── lab-kv/                           # KV version 2: dữ liệu mẫu chính
│   ├── apps/orders/config            # Cấu hình Orders API
│   ├── apps/orders/database          # Kết nối DB giả lập
│   └── apps/billing/config           # Cấu hình Billing, tách quyền
├── lab-kv-sandbox/                   # KV version 2: vùng luyện tập độc lập
│   └── apps/orders/config            # Cùng tên key, dữ liệu khác
├── lab-transit/                      # Transit: giữ khóa mã hóa trong Vault
│   └── keys/orders-lab
└── lab-pki/                          # PKI: CA và role phát hành chứng chỉ lab
    └── roles/lab-server

auth/
└── lab-approle/                      # Auth method (nếu bật), KHÔNG phải secrets engine
~~~

| Mount | Loại | Mục đích | Ví dụ đường dẫn API |
| --- | --- | --- | --- |
| **lab-kv/** | KV v2 | Cấu hình và secret giả của ứng dụng | **lab-kv/data/apps/orders/config** |
| **lab-kv-sandbox/** | KV v2 | Tự do cập nhật/xóa khi học mà không động vào dữ liệu chính | **lab-kv-sandbox/data/apps/orders/config** |
| **lab-transit/** | Transit | Tạo khóa và kiểm thử encrypt/decrypt | **lab-transit/encrypt/orders-lab** |
| **lab-pki/** | PKI | Phát hành chứng chỉ cho tên miền giả lập | **lab-pki/issue/lab-server** |
| **auth/lab-approle/** | AppRole auth | Đổi role ID và secret ID lấy client token | **auth/lab-approle/login** |

Hai mount KV có thể cùng chứa key tên **apps/orders/config** nhưng lưu **hai bản dữ liệu độc lập**; không có cơ chế tự đồng bộ giữa chúng. Tương tự, mount **lab-transit/** không phải kho KV để truy cập bằng **kv get**, và đường dẫn **auth/lab-approle/** thuộc nhóm phương thức xác thực.

Một sơ đồ luồng cơ bản:

~~~mermaid
flowchart LR
    Admin["Người quản trị lab<br/>root token dev"] -->|"enable mount<br/>seed dữ liệu + policy"| Vault["Vault local"]
    App["Java / VaultTemplate<br/>token giới hạn"] -->|"KV v2 read"| KV["lab-kv/"]
    App -. "bị từ chối" .-> Sandbox["lab-kv-sandbox/"]
    Vault --> KV
    Vault --> Sandbox
    Vault --> Transit["lab-transit/"]
    Vault --> PKI["lab-pki/"]
~~~

## 3. Chuẩn bị Vault cục bộ

### 3.1. Yêu cầu tối thiểu

Cần Docker Engine hoặc Docker Desktop, Docker Compose v2 và cổng **8200** chưa được sử dụng. Ví dụ dùng **Vault dev mode** với root token cố định chỉ để thực hiện các lệnh bootstrap. Các lệnh được chạy từ thư mục chứa **compose.yaml**. Nếu đang có Vault lab khác trên cổng 8200, dừng lab đó hoặc chọn cổng khác trước khi tiếp tục.

Tạo tệp **compose.yaml** trong một thư mục lab riêng:

~~~yaml
services:
  vault:
    image: hashicorp/vault:1.19.0
    cap_add:
      - IPC_LOCK
    command: server -dev -dev-listen-address=0.0.0.0:8200
    environment:
      VAULT_DEV_ROOT_TOKEN_ID: dev-root-only
      VAULT_ADDR: http://127.0.0.1:8200
      VAULT_TOKEN: dev-root-only
    ports:
      - "127.0.0.1:8200:8200"
    restart: "no"
~~~

Khởi động và kiểm tra:

~~~bash
docker compose up -d
docker compose ps
docker compose exec -T vault vault status
docker compose exec -T vault vault secrets list
docker compose exec -T vault vault auth list
~~~

Kỳ vọng: **Initialized = true**, **Sealed = false** và các mount mặc định của dev server có thể xem được. Tên image được cố định để bài thực hành dễ lặp lại; đây không phải khẳng định đó là phiên bản Vault mới nhất.

**Lưu ý về quyền:** Biến **VAULT_TOKEN** trong container đang là root token dev, dùng để tạo mount và policy. Khi mô phỏng ứng dụng, phải ghi đè biến này bằng token hạn chế. Root token sẽ bỏ qua nhiều giới hạn policy, làm sai kết quả kiểm thử phân quyền.

### 3.2. Quy ước thao tác

Trong bài, lệnh dạng **docker compose exec -T vault vault ...** gọi Vault CLI ngay trong container. Điều này tránh yêu cầu cài Vault CLI trên host và làm các ví dụ độc lập với Windows, macOS hay Linux. Khi phải tạo policy dạng HCL, lưu policy tại máy host rồi dùng **docker compose cp** để chép vào container.

Không đưa root token, secret ID, private key hoặc giá trị secret thật vào file cấu hình được commit. Các giá trị trong bài chỉ là dữ liệu giả nên có thể quan sát bằng CLI để học cấu trúc phản hồi.

## 4. Kích hoạt các secrets engine tại mount riêng

Trước khi tạo mới, luôn liệt kê mount hiện có:

~~~bash
docker compose exec -T vault vault secrets list -detailed
~~~

Với Vault dev mới, tạo bốn mount:

~~~bash
docker compose exec -T vault vault secrets enable -path=lab-kv kv-v2
docker compose exec -T vault vault secrets enable -path=lab-kv-sandbox kv-v2
docker compose exec -T vault vault secrets enable -path=lab-transit transit
docker compose exec -T vault vault secrets enable -path=lab-pki pki
docker compose exec -T vault vault secrets list -detailed
~~~

Quan sát cột **Type** và **Options**: hai mount KV phải có phiên bản KV v2 (thường hiện **version:2**), Transit có kiểu **transit** và PKI có kiểu **pki**. Nếu mount cùng tên đã tồn tại, lệnh **secrets enable** sẽ báo lỗi; không bật thêm chồng lên đường dẫn đó.

### 4.1. Vì sao tách mount?

- **Tách kiểu xử lý:** KV v2 cung cấp phiên bản dữ liệu; Transit mã hóa bằng khóa do Vault quản lý; PKI cung cấp giao diện cấp chứng chỉ. Chúng không dùng chung API hay policy.
- **Tách vòng đời và cấu hình:** Mỗi mount có tuning riêng, chẳng hạn TTL tối đa của PKI hay cách lưu phiên bản của KV v2.
- **Tách phạm vi bài tập:** Mount **lab-kv-sandbox/** có thể bị thay đổi hoặc xóa mà không mất dữ liệu ở **lab-kv/**.
- **Tách quyền:** Policy chỉ đọc **lab-kv/data/apps/orders/config** không tự cho quyền với **lab-kv-sandbox/**, **lab-transit/** hoặc **lab-pki/**.

**Phân biệt:** Các chuỗi **apps/orders/** và **apps/billing/** trong KV là tiền tố logical key bên trong cùng một mount, không phải hai secrets engine riêng. Nếu cần cấu hình hoặc ranh giới quản trị theo mount độc lập, phải tạo mount khác; nếu chỉ cần policy theo nhóm key, có thể tổ chức dưới nhiều prefix của một mount.

## 5. Ghi dữ liệu KV v2 mẫu

### 5.1. Đặt quy tắc tên và dữ liệu

Giả sử phòng lab mô phỏng hai ứng dụng: **orders-api** và **billing-api**. Tạo ba secret trong **lab-kv/**:

| Logical key | Trường dữ liệu mẫu | Quyền dự kiến |
| --- | --- | --- |
| **apps/orders/config** | app_name, base_url, timeout_ms | Orders API được đọc |
| **apps/orders/database** | jdbc_url, db_user, db_password | Orders API được đọc |
| **apps/billing/config** | app_name, provider_url, api_token | Billing API mới được đọc |

Tên key có chủ đích ổn định để ví dụ CLI, policy và Java dùng cùng một giá trị. Đây là dữ liệu giả; tên biến **db_password** hoặc **api_token** không làm cho giá trị demo trở thành một credential an toàn để dùng trong ứng dụng thật.

Chạy các lệnh sau bằng root token dev:

~~~bash
docker compose exec -T vault vault kv put -mount=lab-kv apps/orders/config app_name=orders-api base_url=https://orders.example.invalid/api timeout_ms=1500
docker compose exec -T vault vault kv put -mount=lab-kv apps/orders/database jdbc_url=jdbc:postgresql://127.0.0.1:5432/orders_lab db_user=demo_reader db_password=demo-not-real
docker compose exec -T vault vault kv put -mount=lab-kv apps/billing/config app_name=billing-api provider_url=https://payments.example.invalid/api api_token=fake-billing-token
~~~

**example.invalid** là miền cố ý không dùng cho dịch vụ thực tế; hai mật khẩu/token giả không cho phép kết nối vào hệ thống nào. Lệnh **kv put** tạo toàn bộ dữ liệu của một phiên bản mới tại logical key được chỉ định.

Đọc lại từng secret và liệt kê các key:

~~~bash
docker compose exec -T vault vault kv get -mount=lab-kv apps/orders/config
docker compose exec -T vault vault kv get -mount=lab-kv apps/orders/database
docker compose exec -T vault vault kv get -mount=lab-kv apps/billing/config
docker compose exec -T vault vault kv list -mount=lab-kv apps/orders/
~~~

Kỳ vọng: hai tên **config** và **database** xuất hiện khi liệt kê **apps/orders/**; từng lệnh đọc trả các trường đã ghi. Với dữ liệu thật, tránh sử dụng thao tác liệt kê/hiển thị nguyên giá trị secret trên terminal được ghi log hoặc chia sẻ.

### 5.2. Tạo một mount sandbox không dùng chung dữ liệu

Ghi một secret có **cùng logical key** vào **lab-kv-sandbox/**:

~~~bash
docker compose exec -T vault vault kv put -mount=lab-kv-sandbox apps/orders/config app_name=orders-sandbox base_url=https://sandbox.example.invalid/api timeout_ms=100
docker compose exec -T vault vault kv get -mount=lab-kv-sandbox apps/orders/config
docker compose exec -T vault vault kv get -mount=lab-kv apps/orders/config
~~~

Hai lệnh đọc cuối phải cho các giá trị **app_name** và **timeout_ms** khác nhau, chứng minh rằng mount là ranh giới độc lập. Khi viết code, chỉ cần dùng nhầm mount name là ứng dụng có thể đọc nhầm dữ liệu ở một không gian khác dù logical key giống hệt.

### 5.3. Phiên bản KV v2 và metadata

Đọc phiên bản ban đầu, chỉnh một trường rồi xem lịch sử:

~~~bash
docker compose exec -T vault vault kv get -version=1 -mount=lab-kv apps/orders/config
docker compose exec -T vault vault kv patch -mount=lab-kv apps/orders/config timeout_ms=2500
docker compose exec -T vault vault kv get -version=2 -mount=lab-kv apps/orders/config
docker compose exec -T vault vault kv metadata get -mount=lab-kv apps/orders/config
~~~

Kỳ vọng: **version 1** có **timeout_ms = 1500**, **version 2** có **timeout_ms = 2500**, còn các trường khác vẫn giữ giá trị do dùng **kv patch**. Nếu bạn đã chạy các lệnh ghi nhiều lần, số version có thể cao hơn; không giả định lúc nào version mới nhất cũng là 2.

Với KV v2:

- **vault kv get -mount=lab-kv apps/orders/config** là cú pháp tiện lợi của CLI.
- API đọc thực tế đi qua **GET /v1/lab-kv/data/apps/orders/config**.
- API metadata nằm ở **/v1/lab-kv/metadata/apps/orders/config**.
- Quyền **read** với dữ liệu và quyền **list/read** với metadata là các capability trên **những endpoint khác nhau**.

Có thể kiểm tra cấu trúc JSON:

~~~bash
docker compose exec -T vault vault kv get -format=json -mount=lab-kv apps/orders/config
~~~

Trong phản hồi của KV v2, dữ liệu ứng dụng nằm tại **data.data**, còn thông tin version và thời điểm tạo nằm ở **data.metadata**. Không nên nhầm cấp bọc JSON này với bản thân các trường **app_name**, **base_url**, **timeout_ms**.

**Phân biệt với lease:** Phiên bản của KV v2 không phải token TTL hay lease. KV v2 lưu các secret tĩnh có version; đọc secret từ KV v2 không tự phát hành credential động kèm **lease_id** như một số secrets engine khác. Các bài về vòng đời token/lease cần thử bằng token hoặc engine phát hành secret động phù hợp.

## 6. Chuẩn bị dữ liệu riêng cho Transit

Transit xử lý mã hóa/giải mã mà ứng dụng không phải nhận khóa bí mật để tự quản lý. Đây là một engine riêng; không thể coi khóa Transit như một key trong KV.

Tạo khóa thử nghiệm **orders-lab**:

~~~bash
docker compose exec -T vault vault write -f lab-transit/keys/orders-lab
docker compose exec -T vault vault read lab-transit/keys/orders-lab
~~~

Lệnh **read** trả **metadata của khóa** như phiên bản khóa; nó không xuất vật liệu khóa đối xứng mà Vault dùng để mã hóa. Để thử API encrypt, Vault yêu cầu đầu vào **plaintext được mã hóa Base64**. Chuỗi **cGluZy10ZXN0** là Base64 của văn bản giả **ping-test**:

~~~bash
docker compose exec -T vault vault write -field=ciphertext lab-transit/encrypt/orders-lab plaintext=cGluZy10ZXN0
~~~

Kết quả là ciphertext dạng **vault:v1:...**. Sao chép giá trị thực tế trả về, rồi thay chuỗi **PASTE_CIPHERTEXT_HERE** trong lệnh:

~~~bash
docker compose exec -T vault vault write -field=plaintext lab-transit/decrypt/orders-lab ciphertext=PASTE_CIPHERTEXT_HERE
~~~

Giá trị nhận được là **cGluZy10ZXN0**; sau khi giải mã Base64 sẽ trở lại **ping-test**. Nếu thử bằng ciphertext tự bịa hoặc cắt bớt ký tự, decrypt sẽ thất bại.

Ở cấp quyền, hai endpoint **lab-transit/encrypt/orders-lab** và **lab-transit/decrypt/orders-lab** thường sử dụng capability **update**. Một workload chỉ cần mã hóa nên được cấp quyền encrypt riêng, tránh cấp decrypt theo thói quen.

> Transit trả ciphertext qua API và bảo vệ vật liệu khóa ở Vault. Nó không thay thế kiểm soát quyền đọc dữ liệu, TLS trên đường truyền hay bảo mật nơi ứng dụng lưu ciphertext.

## 7. Chuẩn bị PKI giả lập

Trong mount **lab-pki/**, tạo một CA nội bộ dành cho lab và role phát hành chứng chỉ. Chứng chỉ này **không được trình duyệt/JVM tin cậy mặc định** và chỉ phục vụ kiểm thử. Vì việc tạo root CA hoặc phát hành certificate có thể liên quan private key, hãy tránh in hoặc lưu khóa riêng vào log.

Điều chỉnh TTL tối đa của mount trước khi tạo CA:

~~~bash
docker compose exec -T vault vault secrets tune -max-lease-ttl=8760h lab-pki
docker compose exec -T vault vault write -field=certificate lab-pki/root/generate/internal common_name=lab.internal ttl=8760h
~~~

Tạo role giới hạn tên miền và thử phát hành chứng chỉ một giờ:

~~~bash
docker compose exec -T vault vault write lab-pki/roles/lab-server allowed_domains=lab.internal allow_subdomains=true max_ttl=24h
docker compose exec -T vault vault write -field=certificate lab-pki/issue/lab-server common_name=orders.lab.internal ttl=1h
~~~

Lệnh cấp phát chỉ in **certificate** để tránh vô tình hiển thị private key ra terminal. Khi tích hợp thật, ứng dụng hoặc một agent phải quản lý certificate **và private key** an toàn, triển khai chúng đúng đích và thay chứng chỉ trước khi hết hạn. Mỗi lần gọi endpoint **issue** có thể tạo một chứng chỉ mới; không gọi lặp lại chỉ để đọc một bản ghi cũ.

**Vòng đời PKI:** Thời hạn hiệu lực của chứng chỉ do CA ký không đồng nghĩa với khả năng dùng **vault lease renew** để kéo dài một chứng chỉ đã phát hành. Thường cần cấp và triển khai một chứng chỉ mới; việc revoke và phân phối CRL/OCSP là chủ đề vận hành PKI riêng.

## 8. Policy và dữ liệu: kiểm chứng ranh giới mount

Đã có dữ liệu mẫu, giờ tạo policy để ứng dụng **orders-api** chỉ đọc hai secret của nó trong **lab-kv/**.

Tạo thư mục **policies/** tại nơi chứa **compose.yaml**, sau đó tạo tệp **policies/orders-reader.hcl**:

~~~hcl
path "lab-kv/data/apps/orders/config" {
  capabilities = ["read"]
}

path "lab-kv/data/apps/orders/database" {
  capabilities = ["read"]
}
~~~

Nạp policy vào Vault:

~~~bash
docker compose cp policies/orders-reader.hcl vault:/tmp/orders-reader.hcl
docker compose exec -T vault vault policy write orders-reader /tmp/orders-reader.hcl
docker compose exec -T vault vault policy read orders-reader
~~~

Policy được viết trên **đường dẫn API có data/** của KV v2, không phải chỉ trên logical key **apps/orders/config**. Policy này không có quyền **create**, **update**, **delete**; cũng không có quyền đọc Billing, sandbox, Transit hay PKI. Nó không cấp quyền **list** metadata nên liệt kê bằng **kv list** có thể bị từ chối dù **kv get** một key cụ thể thành công.

### 8.1. Cấp token ứng dụng

Tạo token ngắn hạn mang policy:

~~~bash
docker compose exec -T vault vault token create -policy=orders-reader -ttl=15m -field=token
~~~

Lưu token kết quả tạm thời vào biến môi trường của shell thực hành, không lưu cùng mã nguồn:

~~~bash
# Bash / zsh: thay chuỗi mẫu bằng token vừa tạo
export LAB_APP_TOKEN="replace-with-issued-token"
~~~

~~~powershell
# PowerShell: thay chuỗi mẫu bằng token vừa tạo
$env:LAB_APP_TOKEN = "replace-with-issued-token"
~~~

Vì Compose đang đặt root token trong môi trường container, mỗi câu lệnh thử với quyền ứng dụng phải **ghi đè VAULT_TOKEN**:

~~~bash
docker compose exec -T -e VAULT_TOKEN="$LAB_APP_TOKEN" vault vault kv get -mount=lab-kv apps/orders/config
docker compose exec -T -e VAULT_TOKEN="$LAB_APP_TOKEN" vault vault kv get -mount=lab-kv apps/orders/database
docker compose exec -T -e VAULT_TOKEN="$LAB_APP_TOKEN" vault vault kv get -mount=lab-kv apps/billing/config
docker compose exec -T -e VAULT_TOKEN="$LAB_APP_TOKEN" vault vault kv get -mount=lab-kv-sandbox apps/orders/config
docker compose exec -T -e VAULT_TOKEN="$LAB_APP_TOKEN" vault vault kv put -mount=lab-kv apps/orders/config timeout_ms=999
~~~

Trong **PowerShell**, thay đoạn **"$LAB_APP_TOKEN"** của những lệnh trên bằng **"$env:LAB_APP_TOKEN"**.

Kết quả mong đợi:

| Thử nghiệm bằng token orders-reader | Kết quả mong đợi | Giải thích |
| --- | --- | --- |
| Đọc **lab-kv/apps/orders/config** | Thành công | Policy có **read** trên API data path tương ứng |
| Đọc **lab-kv/apps/orders/database** | Thành công | Có quyền đọc chính xác key này |
| Đọc **lab-kv/apps/billing/config** | **403 permission denied** | Không có policy cho Billing |
| Đọc **lab-kv-sandbox/apps/orders/config** | **403 permission denied** | Mount khác dù logical key giống |
| Ghi **lab-kv/apps/orders/config** | **403 permission denied** | Không có capability ghi |

Mã lỗi có thể khác trong các tình huống token hết hạn, mount không tồn tại hoặc lệnh sai. Với token hợp lệ, các thao tác bị thiếu quyền nói trên thường trả **403**. Nếu mọi thao tác đều thành công, kiểm tra bạn có đang vô tình dùng **root token** thay vì token giới hạn hay không.

### 8.2. Chuẩn bị lựa chọn AppRole theo workload

Token phát trực tiếp ở trên phù hợp để kiểm chứng policy, nhưng khi thực hành xác thực theo workload có thể bật một **auth mount** AppRole riêng:

~~~bash
docker compose exec -T vault vault auth enable -path=lab-approle approle
docker compose exec -T vault vault write auth/lab-approle/role/orders-app token_policies=orders-reader token_ttl=15m token_max_ttl=1h secret_id_ttl=30m secret_id_num_uses=1
docker compose exec -T vault vault read -field=role_id auth/lab-approle/role/orders-app/role-id
docker compose exec -T vault vault write -f -field=secret_id auth/lab-approle/role/orders-app/secret-id
~~~

**role_id** và **secret_id** là thông tin dùng để đăng nhập tại **auth/lab-approle/login**, lấy token mang policy **orders-reader**. Secret ID trong ví dụ chỉ có một lượt sử dụng; khi cần đăng nhập lại phải cấp secret ID mới. Không commit hoặc ghi các giá trị này vào log. AppRole là một cách đơn giản để học nhận diện ứng dụng; trong Kubernetes/cloud có thể dùng phương thức xác thực dựa trên danh tính workload tương ứng.

**Chú ý:** **vault auth enable** cũng không thể bật hai lần trên cùng mount. Khi chạy lại bootstrap, kiểm tra **vault auth list** trước; không thêm một auth mount trùng đường dẫn.

## 9. Đọc dữ liệu mẫu bằng Spring Vault

Phần dữ liệu đã sẵn sàng để một chương trình Java kết nối đến Vault. Ví dụ bên dưới dùng **VaultTemplate** và token **orders-reader** được đưa từ môi trường chạy. Đối với dự án dùng Maven/Gradle, khai báo **org.springframework.vault:spring-vault-core** với phiên bản được quản lý phù hợp Spring Framework/Spring Boot của dự án.

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

public class OrdersSecretCheck {
    public static void main(String[] args) {
        String address = System.getenv("VAULT_ADDR");
        String token = System.getenv("VAULT_TOKEN");

        if (address == null || address.isBlank()
                || token == null || token.isBlank()) {
            throw new IllegalStateException("Missing VAULT_ADDR or VAULT_TOKEN");
        }

        VaultEndpoint endpoint = VaultEndpoint.from(URI.create(address));
        VaultTemplate template = new VaultTemplate(
                endpoint, new TokenAuthentication(token));

        Versioned<Map<String, Object>> config = template
                .opsForVersionedKeyValue("lab-kv")
                .get("apps/orders/config");

        if (config == null || config.getData() == null) {
            throw new IllegalStateException("Orders config does not exist");
        }

        Map<String, Object> fields = config.getData();
        if (!"orders-api".equals(fields.get("app_name"))) {
            throw new IllegalStateException("Unexpected sample secret");
        }

        // Chỉ in tên trường; không in password, token hoặc toàn bộ response.
        System.out.println("Found fields: " + fields.keySet());
    }
}
~~~

Ví dụ đặt biến môi trường trên host:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="$LAB_APP_TOKEN"
~~~

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = $env:LAB_APP_TOKEN
~~~

Với thông tin đã khởi tạo, chương trình phải đọc được **lab-kv/apps/orders/config** và in tên các trường. Gọi **opsForVersionedKeyValue("lab-kv")** cho KV v2 để Spring Vault sử dụng endpoint **data/** đúng với policy. Không chỉ thay logical key khi muốn đổi sang mount khác; phải chọn đúng mount name.

Khi chuyển sang AppRole, thay cơ chế **TokenAuthentication** trực tiếp bằng cấu hình **AppRoleAuthentication** và quản lý phiên phù hợp (**SessionManager** khi cần tự xử lý token lifecycle). Ví dụ token tĩnh chỉ dùng để smoke test; nó không tự giải quyết việc token hết hạn hay bị revoke.

## 10. Lặp lại bootstrap, khắc phục lỗi và dọn dẹp

### 10.1. Thứ tự bootstrap an toàn

Có thể lưu **danh sách lệnh bootstrap không chứa bí mật thật** trong tài liệu lab của riêng bạn. Một lần khởi tạo sạch nên đi theo thứ tự:

1. **Khởi động Vault**, kiểm tra status/health và bảo đảm đang kết nối đúng lab.
2. **Liệt kê mounts**, tạo KV v2 chính, KV sandbox, Transit và PKI nếu chưa có.
3. **Ghi dữ liệu giả** vào từng logical key, rồi kiểm tra giá trị/version mong đợi.
4. **Tạo khóa Transit**, CA/PKI role, tránh lặp lại thao tác tạo CA ngoài ý muốn.
5. **Viết policy**, tạo token hạn chế hoặc AppRole, sau đó xác nhận quyền được phép và bị từ chối.
6. **Chạy smoke test VaultTemplate**, ghi nhận kết quả kiểm thử không chứa secret.

Những lệnh này **không hoàn toàn idempotent**. Chạy lại **secrets enable** trên cùng path gây lỗi; **kv put** hoặc **kv patch** tạo thêm version; tạo root CA lần nữa có thể làm thay đổi trạng thái PKI; phát hành chứng chỉ thêm lần nữa tạo certificate mới. Vì vậy khi chạy lại, cần kiểm tra trạng thái trước và chỉ lặp lại lệnh có chủ đích.

### 10.2. Bảng xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| **connection refused/timeout** | Vault chưa chạy, sai cổng/địa chỉ | **docker compose ps**, **vault status** |
| **404** khi đọc KV | Sai mount, key chưa tồn tại hoặc dùng nhầm endpoint KV v1/v2 | **vault secrets list -detailed**, **vault kv get -mount=...** |
| **403** khi đọc KV | Token hết hạn, sai token hoặc thiếu capability **read** trên **data/** | **vault token lookup**, **vault policy read orders-reader** |
| Đọc được secret của Billing bằng token Orders | Đang dùng root token hoặc policy quá rộng | Kiểm tra biến **VAULT_TOKEN** và policy gắn với token |
| **kv list** bị từ chối nhưng **kv get** thành công | Policy chỉ có quyền data read, thiếu metadata list | Xem **lab-kv/metadata/...** và capability **list** |
| Transit decrypt không hợp lệ | Ciphertext không đầy đủ, sai key/mount hoặc không có quyền | Dùng nguyên ciphertext vừa tạo và đúng mount |
| PKI từ chối cấp chứng chỉ | Common name không khớp role hoặc TTL vượt giới hạn | **vault read lab-pki/roles/lab-server** |
| Dữ liệu không còn sau restart | Vault dev dùng storage trong bộ nhớ | Tạo lại mount và seed theo thứ tự |

**Quy tắc quan sát:** Với ứng dụng Java, log nên ghi operation, logical path, HTTP status và thời gian xử lý. Không log password, raw Vault response, secret ID, private key hay giá trị plaintext/ciphertext nhạy cảm. HTTP **403** thường là lỗi danh tính/quyền nên retry vô hạn không giúp sửa được policy.

### 10.3. Dọn sạch phòng lab

Nếu chỉ muốn xóa vùng sandbox, dùng lệnh dưới đây **sau khi chắc chắn** tên mount đang trỏ tới môi trường lab:

~~~bash
docker compose exec -T vault vault secrets disable lab-kv-sandbox
~~~

Lệnh **secrets disable** tháo mount và xóa dữ liệu được quản lý tại mount đó; không dùng để dọn một key riêng lẻ trên Vault có dữ liệu thật. Để tạo lại sandbox:

~~~bash
docker compose exec -T vault vault secrets enable -path=lab-kv-sandbox kv-v2
docker compose exec -T vault vault kv put -mount=lab-kv-sandbox apps/orders/config app_name=orders-sandbox base_url=https://sandbox.example.invalid/api timeout_ms=100
~~~

Kết thúc toàn bộ phòng lab dev:

~~~bash
docker compose down
~~~

Khi khởi động lại dev server, các mount, dữ liệu, policy và token đã tạo trong phiên trước có thể mất do storage trong bộ nhớ. Với non-dev có storage bền vững, không được mặc định xem **compose down** hay xóa volume là thao tác vô hại.

## 11. Bài tập thực hành và tiêu chí hoàn thành

**Bài tập A — Tách môi trường.** Tạo **lab-kv-team-b/** (KV v2), ghi logical key **apps/orders/config** với **app_name=orders-team-b**, rồi chứng minh cập nhật mount mới không thay đổi **lab-kv/apps/orders/config**.

**Bài tập B — Chính sách quyền tối thiểu.** Tạo policy chỉ cho Billing đọc **lab-kv/data/apps/billing/config**, cấp token mới và kiểm chứng: đọc Billing thành công, đọc Orders bị từ chối, ghi Billing bị từ chối.

**Bài tập C — Metadata.** Đọc version và lịch sử của **apps/orders/config**, xác định vì sao **kv list** cần quyền **metadata/** khác với quyền đọc **data/**. Bổ sung đúng một quyền **list** cần thiết vào policy dành riêng cho bài tập, rồi thử lại.

**Bài tập D — Transit/PKI.** Mã hóa và giải mã **ping-test** bằng khóa **orders-lab**; dùng role **lab-server** để xin chứng chỉ cho **orders.lab.internal**. Thử một common name nằm ngoài **lab.internal** và giải thích vì sao Vault từ chối.

**Bài tập E — Ứng dụng Java.** Chạy đoạn **VaultTemplate** bằng token Orders, xác nhận đọc được cấu hình. Thay mount name bằng **lab-kv-sandbox**, sau đó ghi nhận kết quả theo policy hiện tại và giải thích ý nghĩa của **mount isolation**.

Checklist cuối bài:

- [ ] Có bốn mount độc lập: **lab-kv**, **lab-kv-sandbox**, **lab-transit**, **lab-pki**.
- [ ] Các dữ liệu Orders/Billing được ghi bằng giá trị giả và đọc lại đúng qua KV v2.
- [ ] Key cùng tên ở hai mount KV trả dữ liệu khác nhau.
- [ ] Có ít nhất hai version của một KV v2 secret, xem được metadata.
- [ ] Tạo được một khóa Transit và một role PKI cho phòng lab.
- [ ] Token Orders chỉ đọc được secret được cấp quyền; thao tác trái quyền bị từ chối.
- [ ] **VaultTemplate** đọc được dữ liệu bằng token hạn chế và không in giá trị secret vào log.
- [ ] Biết lệnh nào không được chạy lặp lại tùy tiện và cách tái tạo lab sạch.

**Kết luận học tập:** Một phòng lab Spring Vault đáng tin cậy bắt đầu từ cách đặt tên mount và tổ chức dữ liệu mẫu. Khi KV v2, Transit, PKI và auth method có ranh giới rõ ràng, bạn có thể kiểm thử quyền, vòng đời token/lease, lỗi kết nối và thao tác **VaultTemplate** mà không nhầm engine, môi trường hay dữ liệu của workload khác.
