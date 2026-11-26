# Đọc, ghi thử bằng CLI để đối chiếu đường dẫn

## 1. Mục tiêu và bối cảnh

Với **Spring Vault**, ứng dụng Java thường gọi **VaultTemplate** để đọc KV secrets, sử dụng Transit encryption, cấp chứng chỉ PKI và làm việc với token hoặc lease. Trước khi sửa lỗi trong Java, cần biết chính xác request đang đến đường dẫn nào của **HashiCorp Vault**. Lệnh **vault kv get** có vẻ sử dụng một đường dẫn đơn giản, nhưng HTTP API của KV phiên bản 2 (**KV v2**) lại có thêm thành phần **data/** hoặc **metadata/**. Nếu viết sai phần này trong policy, ứng dụng có thể nhận **403 permission denied** ngay cả khi secret tồn tại.

Bài học thuộc chương **Môi trường thực hành** và hướng dẫn đọc, ghi dữ liệu giả từ **Vault CLI**, sau đó đối chiếu lệnh CLI, API, policy và lời gọi Spring Vault.

Sau bài này, bạn có thể:

1. Phân biệt **secrets engine mount**, **logical key**, **CLI path**, **API path** và **policy path**.
2. Dùng **vault kv put/get/patch/list/metadata** để tạo dữ liệu giả, đọc version và xem lịch sử.
3. Dùng lệnh **vault read** để nhìn thấy API path thật của KV v2.
4. Viết policy chỉ đọc, kiểm tra thao tác ghi bị từ chối và xác định quyền cần có trên **data/** so với **metadata/**.
5. Đối chiếu một lệnh **vault kv get** với **VaultTemplate.opsForVersionedKeyValue**.
6. Nhận biết khi nào dùng đường dẫn của KV, Transit, PKI hay AppRole, đồng thời chẩn đoán lỗi sai mount, sai quyền và token hết hạn.

**Phạm vi:** Các ví dụ chỉ chạy trên Vault dev mode cục bộ, qua HTTP ở loopback và dùng dữ liệu giả. Root token cố định chỉ dành cho người tạo dữ liệu lab; ứng dụng và phép thử phân quyền phải sử dụng token giới hạn. Không đưa credential thật vào CLI được ghi log, mã nguồn hoặc Git.

## 2. Giải mã các loại đường dẫn

Ví dụ mount KV v2 tên **lab-kv/** chứa key **apps/orders/config**:

~~~text
Vault
└── lab-kv/                       # mount path của KV v2
    └── apps/
        └── orders/
            └── config           # logical key tương đối với mount
~~~

| Cách nhìn | Biểu diễn | Ý nghĩa |
| --- | --- | --- |
| Mount path | **lab-kv/** | Tiền tố được Vault dùng để xác định secrets engine |
| Logical key | **apps/orders/config** | Tên bản ghi bên trong mount |
| CLI thân thiện | **vault kv get -mount=lab-kv apps/orders/config** | CLI tự thêm path thích hợp cho KV v2 |
| HTTP API đọc | **GET /v1/lab-kv/data/apps/orders/config** | **/v1/** là API prefix, **data/** là endpoint KV v2 |
| HTTP API ghi | **POST /v1/lab-kv/data/apps/orders/config** | Body có đối tượng **data** |
| HTTP API metadata | **GET /v1/lab-kv/metadata/apps/orders/config** | Thông tin version và trạng thái key |
| HTTP API liệt kê | **LIST /v1/lab-kv/metadata/apps/orders** | Liệt kê tên các key dưới prefix |
| Vault policy đọc | **path "lab-kv/data/apps/orders/config"** | Bỏ **/v1/**; giữ **data/** |
| Spring Vault | **opsForVersionedKeyValue("lab-kv").get("apps/orders/config")** | Tách tên mount và logical key |

~~~mermaid
flowchart LR
    CLI["Vault CLI<br/>kv get -mount=lab-kv"]
    Java["Spring Vault<br/>VaultTemplate"]
    API["GET /v1/lab-kv/data/<br/>apps/orders/config"]
    Policy["Policy: read<br/>lab-kv/data/apps/orders/config"]
    KV["KV v2<br/>lab-kv/"]
    CLI --> API
    Java --> API
    API -->|"kiểm tra quyền"| Policy
    API --> KV
~~~

**Quy tắc đối chiếu:** Khi dùng **vault kv ...** hoặc **opsForVersionedKeyValue(...)**, truyền logical key **apps/orders/config**, **không** tự chèn **data/**. Khi dùng **vault read** với raw path hoặc viết Vault policy, phải có **lab-kv/data/apps/orders/config**. HTTP API thêm **/v1/** ở đầu URL, còn biểu thức trong policy không có tiền tố này.

Nếu bạn đưa **apps/orders/data/config** vào tham số key, Vault sẽ hiểu đó là một key *khác*; tự chèn **data/** không giúp truy cập đúng KV v2.

## 3. Khởi tạo môi trường cục bộ và mount

### 3.1. Vault dev chạy trong Docker

Cần Docker Engine/Docker Desktop, Docker Compose v2 và cổng **8200** còn trống. Tạo **compose.yaml** trong một thư mục lab riêng:

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

Chạy từ thư mục chứa **compose.yaml**:

~~~bash
docker compose up -d
docker compose ps
docker compose exec -T vault vault status
docker compose exec -T vault vault secrets list -detailed
~~~

Kỳ vọng **Initialized = true**, **Sealed = false**. Để đơn giản và dùng được trên Windows/macOS/Linux, các ví dụ CLI chạy **trong container** qua **docker compose exec -T vault vault ...**. Giá trị **VAULT_TOKEN** bên trong container là root token dev phục vụ bootstrap; về sau chúng ta sẽ ghi đè bằng token giới hạn khi kiểm thử.

### 3.2. Mount KV v2 riêng cho bài

Nếu **lab-kv/** chưa có trong danh sách secrets engines, tạo nó:

~~~bash
docker compose exec -T vault vault secrets enable -path=lab-kv kv-v2
docker compose exec -T vault vault secrets list -detailed
~~~

Trong kết quả, tìm mount **lab-kv/** có type **kv** và phiên bản **2**. Nếu mount đã tồn tại, **bỏ qua lệnh enable**; Vault không cho kích hoạt thêm một engine đè lên cùng path. Đừng dùng **vault secrets disable lab-kv** để xử lý lỗi trùng path, vì disable sẽ tháo mount và làm mất dữ liệu được quản lý trong đó.

## 4. Đọc, ghi dữ liệu KV v2 bằng CLI

### 4.1. Ghi một secret giả

Trên PowerShell hoặc mọi hệ điều hành, lệnh một dòng sau dùng được trong thư mục Compose:

~~~bash
docker compose exec -T vault vault kv put -mount=lab-kv apps/orders/config app_name=orders-api env=lab timeout_ms=1500
~~~

Kết quả thường có **created_time** và **version**. Trên mount sạch, lần ghi đầu tiên tạo **version 1**. Chạy lại **kv put** sẽ tạo **version mới**, không ghi đè lịch sử KV v2 theo cách của KV v1.

**Lưu ý kiểu dữ liệu:** Với cú pháp **key=value**, các giá trị CLI thường được xử lý như chuỗi, chẳng hạn **timeout_ms=1500**. Nếu Java cần một JSON number, phải kiểm tra kiểu thực tế hoặc ghi JSON với kiểu rõ ràng; không nên ép kiểu dựa vào tên trường.

### 4.2. Đọc cùng một key theo ba định dạng

~~~bash
docker compose exec -T vault vault kv get -mount=lab-kv apps/orders/config
docker compose exec -T vault vault kv get -field=app_name -mount=lab-kv apps/orders/config
docker compose exec -T vault vault kv get -format=json -mount=lab-kv apps/orders/config
~~~

Lệnh đầu in bảng dữ liệu và metadata; lệnh thứ hai chỉ in giá trị **app_name**; lệnh thứ ba in JSON để quan sát wrapper của KV v2. Một phần phản hồi JSON (lược bỏ những trường không liên quan) có dạng:

~~~json
{
  "data": {
    "data": {
      "app_name": "orders-api",
      "env": "lab",
      "timeout_ms": "1500"
    },
    "metadata": {
      "version": 1,
      "created_time": "..."
    }
  }
}
~~~

**data.data** chứa giá trị của key; **data.metadata** mô tả version và thời điểm tạo. Đây là ví dụ minh họa, không phải bản sao phản hồi đầy đủ. Không in nguyên phản hồi JSON nếu môi trường chứa secret thật.

### 4.3. Tạo thêm key và liệt kê tên

~~~bash
docker compose exec -T vault vault kv put -mount=lab-kv apps/orders/database jdbc_url=jdbc:postgresql://127.0.0.1:5432/orders_lab username=demo password=not-a-real-password
docker compose exec -T vault vault kv list -mount=lab-kv apps/orders
~~~

Kết quả **kv list** dự kiến chứa **config** và **database**. Lệnh này liệt kê **tên các key** chứ không đọc nội dung secret. Về phân quyền, liệt kê là thao tác trên endpoint **metadata/** và yêu cầu capability **list** riêng.

### 4.4. Patch một trường và đối chiếu phiên bản

~~~bash
docker compose exec -T vault vault kv patch -mount=lab-kv apps/orders/config timeout_ms=2500
docker compose exec -T vault vault kv get -mount=lab-kv apps/orders/config
docker compose exec -T vault vault kv get -version=1 -mount=lab-kv apps/orders/config
docker compose exec -T vault vault kv metadata get -mount=lab-kv apps/orders/config
~~~

Nếu key mới có version 1 trước bước này, version 1 sẽ giữ **timeout_ms=1500**, version mới nhất có **timeout_ms=2500**. **kv patch** cập nhật có chọn lọc, nên **app_name** và **env** vẫn tồn tại trong phiên bản mới. Ngược lại, **kv put** với một tập trường không đầy đủ sẽ tạo version mới chỉ chứa các trường vừa đưa vào.

Nếu đã thực hiện **kv put** hoặc **kv patch** nhiều lần, version mới nhất có thể lớn hơn 2. Luôn xem **kv metadata get** thay vì giả định một số version cố định.

**Phân biệt:** KV v2 version không phải **lease_id** hay token TTL. KV v2 lưu secret có phiên bản; đọc một secret tĩnh không phát hành dynamic lease như các secrets engine tạo credential ngắn hạn.

## 5. Đối chiếu CLI thân thiện với raw API

### 5.1. Gọi đúng endpoint bằng vault read

~~~bash
docker compose exec -T vault vault kv get -format=json -mount=lab-kv apps/orders/config
docker compose exec -T vault vault read -format=json lab-kv/data/apps/orders/config
~~~

Lệnh đầu nhận mount + logical key rồi tự xác định endpoint của KV v2. Lệnh thứ hai gọi raw API path **lab-kv/data/apps/orders/config**. Cả hai đọc cùng dữ liệu và cần có cấu trúc **data.data** tương ứng trong phản hồi.

Thử cố ý bỏ **data/**:

~~~bash
docker compose exec -T vault vault read lab-kv/apps/orders/config
~~~

Lệnh thường thất bại vì path này không phải endpoint GET của KV v2. Thất bại đó **không chứng minh secret đã mất**.

Hai lệnh liệt kê tương đương về mục đích:

~~~bash
docker compose exec -T vault vault kv list -mount=lab-kv apps/orders
docker compose exec -T vault vault list lab-kv/metadata/apps/orders
~~~

Với **vault list**, người gọi tự viết endpoint metadata. Không liệt kê bằng **lab-kv/data/apps/orders** vì **data/** không phải namespace liệt kê của KV v2.

### 5.2. Quan sát HTTP path và body

HTTP API đọc từ host:

~~~http
GET /v1/lab-kv/data/apps/orders/config
X-Vault-Token: <reader-token>
~~~

Mẫu request ghi KV v2:

~~~http
POST /v1/lab-kv/data/apps/orders/config
X-Vault-Token: <writer-token>
Content-Type: application/json

{
  "data": {
    "app_name": "orders-api",
    "env": "lab",
    "timeout_ms": 2500
  }
}
~~~

Đây là ví dụ về **cấu trúc HTTP**, chưa phải lệnh gửi. Trường **timeout_ms** trong JSON ở đây là number, khác với dữ liệu nhập từ CLI **key=value** có thể được lưu như chuỗi.

Để thử raw HTTP GET bằng Bash/zsh sau khi đã tạo token reader ở mục 6:

~~~bash
curl -sS -i -H "X-Vault-Token: $LAB_READER_TOKEN" "http://127.0.0.1:8200/v1/lab-kv/data/apps/orders/config"
~~~

PowerShell tương đương:

~~~powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8200/v1/lab-kv/data/apps/orders/config" -Headers @{ "X-Vault-Token" = $env:LAB_READER_TOKEN }
~~~

Không đưa token vào query string hoặc code; đối với môi trường vận hành cần **HTTPS** với CA tin cậy và xác minh hostname.

### 5.3. Bảng quy chiếu các thao tác KV v2

| Thao tác | Vault CLI | API path sau **/v1/** | Capability điển hình |
| --- | --- | --- | --- |
| Đọc key | **kv get -mount=lab-kv apps/orders/config** | **lab-kv/data/apps/orders/config** | **read** |
| Ghi mới/cập nhật | **kv put -mount=lab-kv apps/orders/config ...** | **lab-kv/data/apps/orders/config** | **create/update** theo trạng thái key |
| Xem metadata | **kv metadata get -mount=lab-kv apps/orders/config** | **lab-kv/metadata/apps/orders/config** | **read** |
| Liệt kê tên key | **kv list -mount=lab-kv apps/orders** | **lab-kv/metadata/apps/orders** | **list** |
| Đọc bản cũ | **kv get -version=1 -mount=lab-kv apps/orders/config** | **lab-kv/data/apps/orders/config?version=1** | **read** |
| Patch một phần | **kv patch -mount=lab-kv apps/orders/config ...** | KV v2 data endpoint, hình thức request tùy cách patch | Tùy HTTP PATCH hoặc cơ chế đọc–ghi |

Với **kv patch**, phiên bản Vault CLI và lựa chọn kiểu patch có thể ảnh hưởng cách thực thi và capability cần thiết. Khi thiết kế policy ứng dụng, kiểm tra phương thức request thực sự sử dụng thay vì mặc định nó giống **kv put**.

## 6. Kiểm chứng đường dẫn bằng token có quyền tối thiểu

Thử nghiệm ở các mục trước sử dụng root token dev để bảo đảm thao tác ghi và đọc thuận tiện. Nó chưa chứng minh **policy path** chính xác, bởi root token có quyền đặc biệt rộng. Ta sẽ tạo một token chỉ đọc duy nhất key **apps/orders/config**.

### 6.1. Policy đọc data KV v2

Trong thư mục chứa Compose, tạo thêm thư mục **policies/** và tệp **policies/orders-reader.hcl**:

~~~hcl
path "lab-kv/data/apps/orders/config" {
  capabilities = ["read"]
}
~~~

Nạp policy từ host vào container, sau đó tạo token TTL ngắn:

~~~bash
docker compose cp policies/orders-reader.hcl vault:/tmp/orders-reader.hcl
docker compose exec -T vault vault policy write orders-reader /tmp/orders-reader.hcl
docker compose exec -T vault vault policy read orders-reader
docker compose exec -T vault vault token create -policy=orders-reader -ttl=15m -field=token
~~~

Lệnh cuối in ra token mới. Trong **Bash/zsh**, lưu token này vào biến của phiên terminal:

~~~bash
export LAB_READER_TOKEN="<token-vua-tao>"
~~~

Trên **PowerShell**:

~~~powershell
$env:LAB_READER_TOKEN = "<token-vua-tao>"
~~~

Chỉ dùng token giả lập trong lab; không lưu credential trong tệp nguồn, lệnh được chia sẻ, screenshot hoặc log. Token có thể mang thêm policy mặc định, nhưng **default policy** không cấp quyền đọc toàn bộ dữ liệu KV.

### 6.2. Bắt buộc ghi đè token root của container

Vì môi trường container có **VAULT_TOKEN=dev-root-only** từ Compose, hãy dùng **-e** để ghi đè token khi gọi Vault CLI:

~~~bash
docker compose exec -T -e "VAULT_TOKEN=$LAB_READER_TOKEN" vault vault kv get -mount=lab-kv apps/orders/config
docker compose exec -T -e "VAULT_TOKEN=$LAB_READER_TOKEN" vault vault kv get -mount=lab-kv apps/orders/database
docker compose exec -T -e "VAULT_TOKEN=$LAB_READER_TOKEN" vault vault kv put -mount=lab-kv apps/orders/config env=should-fail
docker compose exec -T -e "VAULT_TOKEN=$LAB_READER_TOKEN" vault vault kv metadata get -mount=lab-kv apps/orders/config
docker compose exec -T -e "VAULT_TOKEN=$LAB_READER_TOKEN" vault vault kv list -mount=lab-kv apps/orders
~~~

Với PowerShell, sử dụng **-e "VAULT_TOKEN=$env:LAB_READER_TOKEN"** cho tham số truyền token. Ví dụ:

~~~powershell
docker compose exec -T -e "VAULT_TOKEN=$env:LAB_READER_TOKEN" vault vault kv get -mount=lab-kv apps/orders/config
~~~

Kết quả mong đợi khi token đúng và chưa hết hạn:

| Thao tác | Kết quả | Lý do |
| --- | --- | --- |
| Đọc **apps/orders/config** | Thành công | Có capability **read** trên data path |
| Đọc **apps/orders/database** | **403 permission denied** | Không có quyền với key khác |
| Ghi **apps/orders/config** | **403 permission denied** | Không có **create/update** |
| Xem **kv metadata get** | **403 permission denied** | Chưa có metadata **read** |
| **kv list** các key dưới **apps/orders** | **403 permission denied** | Chưa có metadata **list** |

Nếu lệnh ghi thành công, trước tiên hãy kiểm tra lệnh có thực sự dùng **LAB_READER_TOKEN** hay vẫn dùng root token và token có vô tình mang thêm policy rộng không. Ghi thất bại không được tạo version mới; xác nhận điều đó bằng cách dùng CLI quản trị đọc metadata sau phép thử.

### 6.3. Cấp quyền metadata khi thật sự cần

Nếu workflow có yêu cầu xem metadata/version hoặc liệt kê các key, có thể thêm **đúng hai path** sau vào policy reader, rồi nạp lại:

~~~hcl
path "lab-kv/metadata/apps/orders/config" {
  capabilities = ["read"]
}

path "lab-kv/metadata/apps/orders" {
  capabilities = ["list"]
}
~~~

**read** trên metadata cho phép xem metadata của key đã chỉ định, còn **list** tại prefix cho phép xem tên các key bên dưới. Hai quyền này không tự cấp quyền đọc **giá trị dữ liệu** của toàn bộ key con. Không mở rộng policy thành **lab-kv/metadata/** toàn bộ nếu ứng dụng chỉ cần một prefix.

Khi dùng ứng dụng Java, policy **data read** là đủ cho thao tác **get** một key đã biết bằng API dữ liệu; không bắt buộc cấp metadata list chỉ vì đang sử dụng KV v2.

### 6.4. Token dành cho người ghi

Để kiểm tra thao tác ghi không phải bằng root token, có thể tạo một policy **orders-writer** tại **policies/orders-writer.hcl**:

~~~hcl
path "lab-kv/data/apps/orders/config" {
  capabilities = ["create", "read", "update"]
}
~~~

Nạp policy và cấp token ngắn hạn:

~~~bash
docker compose cp policies/orders-writer.hcl vault:/tmp/orders-writer.hcl
docker compose exec -T vault vault policy write orders-writer /tmp/orders-writer.hcl
docker compose exec -T vault vault token create -policy=orders-writer -ttl=15m -field=token
~~~

Gán token mới cho **LAB_WRITER_TOKEN** và thử **kv put** bằng tham số **-e "VAULT_TOKEN=$LAB_WRITER_TOKEN"** trong Bash, hoặc **-e "VAULT_TOKEN=$env:LAB_WRITER_TOKEN"** trong PowerShell. Quyền **create** dùng cho trường hợp ghi key chưa có; **update** cho phép sửa secret đã tồn tại. Cấp cả hai để bài tập ghi hoạt động trên môi trường có trạng thái khác nhau, nhưng chỉ ở đúng **một** data path.

Tách token reader và writer giúp chứng minh thao tác đọc/ghi là các quyền độc lập. Khi học xác thực theo workload, có thể thay token phát thủ công bằng **AppRole**, Kubernetes hoặc auth method thích hợp; token nhận sau login vẫn phải chịu policy tương ứng.

## 7. Chuyển kết quả CLI sang VaultTemplate

Sau khi CLI xác nhận một token đọc được secret, ứng dụng Java sử dụng **Spring Vault** phải chọn đúng mount và logical key. Đối với KV v2, dùng **VersionedKeyValueOperations** qua **VaultTemplate.opsForVersionedKeyValue(...)**.

Một smoke test tối thiểu với dependency **org.springframework.vault:spring-vault-core** (chọn phiên bản tương thích nền Spring của dự án):

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

public class KvPathCheck {
    public static void main(String[] args) {
        String url = System.getenv("VAULT_ADDR");
        String token = System.getenv("VAULT_TOKEN");
        if (url == null || url.isBlank()
                || token == null || token.isBlank()) {
            throw new IllegalStateException("Missing Vault connection settings");
        }

        VaultTemplate template = new VaultTemplate(
                VaultEndpoint.from(URI.create(url)),
                new TokenAuthentication(token));

        Versioned<Map<String, Object>> result = template
                .opsForVersionedKeyValue("lab-kv")
                .get("apps/orders/config");

        if (result == null || result.getData() == null) {
            throw new IllegalStateException("KV v2 secret not found");
        }
        // Chỉ in tên trường; không in giá trị secret.
        System.out.println("Fields: " + result.getData().keySet());
    }
}
~~~

Đặt biến môi trường trên host trước khi chạy chương trình:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="$LAB_READER_TOKEN"
~~~

Trong PowerShell:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = $env:LAB_READER_TOKEN
~~~

Đối chiếu bốn cách viết:

~~~text
CLI:       vault kv get -mount=lab-kv apps/orders/config
Spring:    template.opsForVersionedKeyValue("lab-kv").get("apps/orders/config")
HTTP:      GET /v1/lab-kv/data/apps/orders/config
Policy:    path "lab-kv/data/apps/orders/config" { capabilities = ["read"] }
~~~

Kết quả dự kiến: ứng dụng nhận dữ liệu của cùng key mà CLI đã đọc và chỉ in tên trường. Nếu thay key trong Java thành **apps/orders/database** nhưng giữ token reader, request phải bị từ chối vì policy không cấp quyền cho key đó.

Nếu cần thử ghi bằng VaultTemplate, sử dụng token writer đã tạo và gọi thao tác **put** trên cùng VersionedKeyValueOperations:

~~~java
// Chỉ chạy với token được cấp create/update trên data path tương ứng.
template.opsForVersionedKeyValue("lab-kv").put(
        "apps/orders/config",
        Map.of("app_name", "orders-api", "env", "lab"));
~~~

Tương tự **vault kv put**, thao tác này tạo version mới chứa các trường bạn truyền. Nếu bạn bỏ **timeout_ms**, version mới sẽ không giữ trường ấy chỉ vì version trước có nó. Không dùng mẫu ghi này trên secret thật khi chưa xác định rõ cơ chế thay thế/cập nhật.

Cũng có thể gọi **template.read("lab-kv/data/apps/orders/config")** để đọc trực tiếp raw endpoint, nhưng khi đó cần tự hiểu wrapper dữ liệu KV v2. Dùng **opsForVersionedKeyValue("lab-kv")** giúp tách biệt mount/key và thao tác với version đúng ngữ nghĩa hơn.

**Vòng đời token:** **TokenAuthentication** ở ví dụ chỉ phù hợp để đối chiếu nhanh. Khi token hết hạn hoặc bị thu hồi, request Java tiếp theo sẽ thất bại. Ứng dụng chạy dài hạn cần cơ chế xác thực theo workload và **SessionManager** phù hợp để quản lý login/renew, đồng thời xử lý lỗi kết nối, timeout và chính sách retry.

## 8. Phân biệt đường dẫn của KV với Transit, PKI và AppRole

Khi chuyển sang các secrets engine khác, không tự thêm **data/** hoặc **metadata/** như KV v2.

| Công việc | Lệnh CLI minh họa | API path sau **/v1/** |
| --- | --- | --- |
| Đọc KV v2 | **vault kv get -mount=lab-kv apps/orders/config** | **lab-kv/data/apps/orders/config** |
| Mã hóa Transit | **vault write lab-transit/encrypt/orders-lab plaintext=...** | **lab-transit/encrypt/orders-lab** |
| Giải mã Transit | **vault write lab-transit/decrypt/orders-lab ciphertext=...** | **lab-transit/decrypt/orders-lab** |
| Cấp chứng chỉ PKI | **vault write lab-pki/issue/lab-server common_name=...** | **lab-pki/issue/lab-server** |
| Đăng nhập AppRole | **vault write auth/lab-approle/login role_id=... secret_id=...** | **auth/lab-approle/login** |

Nếu mount Transit **lab-transit/** và khóa **orders-lab** đã được tạo, có thể mã hóa một chuỗi giả bằng CLI:

~~~bash
docker compose exec -T vault vault write -field=ciphertext lab-transit/encrypt/orders-lab plaintext=cGluZy10ZXN0
~~~

**cGluZy10ZXN0** là Base64 của **ping-test**. Kết quả ciphertext có dạng **vault:v1:...**. Đường dẫn này thuộc Transit, không thể đọc bằng **vault kv get -mount=lab-transit ...**. Nếu muốn giải mã, phải dùng đúng ciphertext vừa nhận và token có quyền tương ứng trên endpoint **lab-transit/decrypt/orders-lab**.

Với PKI, **lab-pki/issue/lab-server** là endpoint phát hành theo role; PKI role kiểm soát common name và TTL được phép, còn Vault policy quy định ai được gọi endpoint. Khi in kết quả cấp chứng chỉ, chỉ lấy trường **certificate** nếu cần kiểm chứng để tránh đưa **private_key** ra terminal.

Với AppRole, endpoint **auth/lab-approle/login** thuộc **auth mount**, không phải secrets engine. **role_id/secret_id** dùng để đăng nhập lấy client token; secret ID không phải token gửi trong các request KV sau khi đăng nhập.

## 9. Chẩn đoán lỗi khi đọc, ghi và đối chiếu path

| Dấu hiệu | Nguyên nhân có thể | Kiểm tra đầu tiên |
| --- | --- | --- |
| **404**, **No value found** hoặc **null** | Sai mount, key chưa tồn tại, version đã xóa hoặc nhầm KV v1/v2 | **vault secrets list -detailed**, **vault kv get** |
| **403 permission denied** | Token sai/hết hạn, thiếu capability hoặc policy sai endpoint | **vault token lookup**, **vault policy read** |
| **vault read lab-kv/apps/...** lỗi nhưng **kv get** thành công | Thiếu **data/** ở raw API path | **vault read lab-kv/data/apps/...** |
| **kv get** thành công nhưng **kv list** thất bại | Thiếu **list** trên **metadata/** | So policy với path của thao tác list |
| **kv metadata get** thất bại | Thiếu **read** trên **metadata/** | Kiểm tra policy metadata cụ thể |
| Version tăng bất ngờ | Chạy lại **kv put/patch** | **vault kv metadata get** |
| Trường biến mất ở version mới | Ghi **kv put** thiếu trường thay vì patch | Đọc lại version trước và sau |
| Java đọc key khác với CLI | Truyền sai mount, logical key hoặc tự thêm **data/** | Bảng đối chiếu bốn đường dẫn ở mục 7 |
| **Connection refused**, timeout | Vault chưa chạy, sai host/cổng hoặc mạng | **docker compose ps**, **vault status** |
| Dữ liệu mất sau restart | Dev mode dùng storage trong bộ nhớ | Tái tạo mount và seed dữ liệu giả |

Một **403** không chứng minh key tồn tại hay không tồn tại: Vault có thể kiểm tra quyền trước khi xử lý nội dung. Với key thực sự không có, CLI/SDK có thể hiển thị 404, null hoặc ngoại lệ khác nhau tùy API và phiên bản client.

Khi ghi log phía Spring Vault, ưu tiên **loại thao tác**, **logical path**, **mã HTTP**, **thời gian xử lý** và mã tương quan; không log token, password, plaintext, secret ID, private key hoặc raw Vault response chứa dữ liệu. Retry có giới hạn phù hợp với lỗi mạng tạm thời; retry vô hạn không sửa được policy 403.

## 10. Thực hành tự kiểm tra

### Bài A — Tạo đường dẫn mới

Tạo key **apps/orders/features** với dữ liệu giả. Viết lại bốn giá trị cần thiết để đọc nó: CLI **kv get**, HTTP GET path, policy read path và lời gọi **VaultTemplate**. Tự chỉ ra thành phần nào thêm **/v1/**, thành phần nào thêm **data/**.

**Gợi ý:** Logical key luôn là **apps/orders/features**; data API path là **lab-kv/data/apps/orders/features**.

### Bài B — Version và thay thế trường

Tạo secret ba trường **a**, **b**, **c**. Dùng **kv patch** thay **b**, rồi dùng **kv put** chỉ với **a**. Đọc từng version bằng **-version=N**; giải thích vì sao patch giữ trường không thay đổi và put tạo version mới với tập dữ liệu được cung cấp.

### Bài C — Data read khác metadata list

Tạo token chỉ read trên **lab-kv/data/apps/orders/config**. Kiểm tra **kv get** thành công nhưng **kv list** và **kv metadata get** bị từ chối. Cấp đúng **list**/**read** trên metadata path cần thiết rồi thử lại, không cấp quyền đọc dữ liệu của key khác.

### Bài D — Java và CLI phải đọc cùng secret

Chạy ví dụ Java bằng token reader, so sánh tên trường trả về với lệnh CLI. Cố ý thay **lab-kv** bằng **lab-unknown** hoặc thay logical key thành **apps/orders/data/config** rồi ghi nhận lỗi. Trả về đúng đường dẫn để khôi phục phép thử.

### Bài E — Ghi với quyền tối thiểu

Ghi một version bằng token writer; thử ghi cùng key bằng token reader và xác nhận request bị từ chối, version không đổi. Sau đó revoke token writer và thử lại để quan sát tác động của vòng đời token lên một thao tác vốn được policy cho phép.

### Checklist hoàn thành

- [ ] Có mount **lab-kv/** phiên bản KV v2 và ít nhất hai key chứa dữ liệu giả.
- [ ] Đọc, ghi được bằng **vault kv put/get**, hiểu patch, list, metadata và version.
- [ ] Đối chiếu chính xác CLI path, HTTP API path, policy path và VaultTemplate.
- [ ] Token read-only không ghi được KV và không mặc định có quyền list metadata.
- [ ] Giải thích được vì sao **data/** thuộc endpoint KV v2 nhưng không thuộc logical key của **vault kv**.
- [ ] Biết chẩn đoán lỗi sai mount, thiếu quyền, token hết hạn và key không tồn tại.
- [ ] Không lưu token/secret thật trong log và biết tái tạo phòng lab khi dev mode khởi động lại.

**Điểm mấu chốt:** Khi thao tác Spring Vault thất bại, hãy dùng CLI kiểm chứng **mount + logical key**, chuyển sang **API path** và so với **Vault policy**. Phương pháp này giúp khoanh vùng lỗi quyền, đường dẫn và trạng thái dữ liệu trước khi sửa code ứng dụng Java.
