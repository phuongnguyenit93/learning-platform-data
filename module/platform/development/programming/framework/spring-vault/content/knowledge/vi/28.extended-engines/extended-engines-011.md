# Đối chiếu khả năng của server với phiên bản client

## 1. Vì sao phải đối chiếu cả hai phía?

Một ứng dụng Java có thể biên dịch thành công với Spring Vault nhưng vẫn thất bại khi chạy: Vault server không có secrets engine cần dùng, engine được mount dưới tên khác, plugin chưa có endpoint cần gọi, một tính năng chỉ có trong Vault Enterprise, hoặc token workload không được cấp quyền.

Chiều ngược lại cũng xảy ra: Vault server có secrets engine mới hay plugin tùy chỉnh, nhưng phiên bản Spring Vault đang sử dụng chưa có interface Java chuyên biệt. Khi ấy ứng dụng vẫn có thể tương tác với endpoint HTTP API qua `VaultOperations.read(…)`, `VaultOperations.write(…)` hoặc HTTP client phù hợp, nếu server, plugin và policy hỗ trợ.

Đối với module **SPRING_VAULT**, vấn đề này liên quan trực tiếp đến truy cập KV secrets, xác thực workload, token/lease, Transit encryption, PKI và các engine mở rộng như Database, AWS, SSH, TOTP hoặc plugin riêng. Cần kiểm tra khả năng thực thi theo **một yêu cầu nghiệp vụ cụ thể**, không đơn giản kết luận “Spring Vault mới + Vault server mới” là tương thích.

Mục tiêu của bài:

- Phân biệt phiên bản **Spring Vault client**, **Vault server**, **secrets engine/plugin**, edition và mount configuration.
- Kiểm tra Vault đang hỗ trợ endpoint nào bằng bằng chứng kiểm kê và integration test.
- Quyết định khi nào dùng API chuyên biệt, khi nào dùng `VaultOperations` chung hoặc client HTTP.
- Tách thiếu tính năng server khỏi sai mount, sai policy và sai schema JSON.
- Xây dựng bảng compatibility và quy trình nâng cấp để giảm rủi ro cho workload Java.

**Định nghĩa làm việc:** Một feature được xem là *khả dụng cho workload* khi client gọi được API, server/plugin triển khai đúng endpoint, mount đã cấu hình, identity có quyền phù hợp và response cùng side effect đáp ứng hợp đồng nghiệp vụ đã kiểm thử.

## 2. Sáu lớp tương thích cần kiểm tra

| Lớp | Giá trị cần ghi nhận | Ví dụ lỗi |
| --- | --- | --- |
| **Ứng dụng/client** | JDK, Spring Boot, Spring Cloud Vault, `spring-vault-core` version | Method có ở JavaDoc mới nhưng không có trong jar đang build. |
| **Vault server** | Server version, Community/Enterprise, trạng thái seal/HA/namespace | Tính năng Enterprise không khả dụng trên cluster hiện tại. |
| **Plugin/engine** | Engine type, plugin name, configured/running version | Plugin đã đăng ký nhưng mount đang chạy version cũ. |
| **Mount/config** | Mount path, KV version, PKI role, Transit key, TTL, options | API gọi `transit/` nhưng engine nằm ở `payments-transit/`. |
| **Quyền/kết nối** | Auth method, Vault token, ACL, namespace, TLS | Token có quyền `read` nhưng endpoint yêu cầu `update`. |
| **Hành vi** | HTTP method, request/response, lease, revoke, error | JSON đã đổi dạng, lease không được xử lý. |

Một lớp PASS không kéo theo các lớp còn lại PASS. Đặc biệt, **Vault server version không phải Spring Vault client version**, **plugin version không phải Vault server version**, còn **KV engine version 1/2 không phải Vault server API version**.

### 2.1. Ví dụ cùng “version”, khác ý nghĩa

~~~text
Java app:
  spring-vault-core = <version trong dependency runtime>
  Java/JDK          = <version JVM runtime>

Vault cluster:
  server version    = <version từ vault status>
  edition           = <Community / Enterprise>

Secrets engine:
  mount path        = secret/
  engine type       = kv
  KV API version    = 2
  plugin version    = <phiên bản plugin đang chạy>

Workload:
  namespace         = <namespace khi áp dụng>
  auth role         = <role của workload>
  ACL               = read secret/data/orders/config
~~~

Các trường này phải được lấy từ từng môi trường chạy thực tế. Không suy rằng mã client “mới hơn” server nên chắc chắn tương thích: mỗi dự án có hệ thống version và changelog riêng.

## 3. Kiểm kê Vault server, engine và plugin

Dùng Vault CLI đã xác thực vào **môi trường test/staging** với quyền kiểm kê phù hợp:

~~~bash
# Version của CLI được cài trên máy, không nhất thiết trùng server.
vault version

# Server version, sealed/HA, kết nối tới cluster.
vault status

# Engine nào đã mount, mount path là gì?
vault secrets list

# Khi cần kiểm tra option KV, plugin version và running version.
vault secrets list -detailed

# Plugin có trong catalog; cần quyền quản trị phù hợp.
vault plugin list secret
~~~

| Nguồn thông tin | Ý nghĩa | Điều không thể suy ra |
| --- | --- | --- |
| `vault version` | Version của CLI đang cài. | Không xác minh version binary của Vault server từ xa. |
| `vault status` | Trạng thái và server version của cluster kết nối. | Không cho biết một plugin/role cụ thể có hoạt động. |
| `vault secrets list` | Mount path và engine type đã bật. | Không chứng minh endpoint trong mount chạy đúng. |
| `vault secrets list -detailed` | Options, TTL, plugin version/running version trên mount. | Không chứng minh ACL của token ứng dụng. |
| `vault plugin list secret` | Plugin có trong catalog. | Không chứng minh plugin đã được mount hoặc đang chạy. |

HTTP API tương ứng cũng hữu ích trong công cụ kiểm kê:

- `GET /v1/sys/health` cho biết trạng thái, trường `version` và một số thông tin HA; các mã 200/429/472/473/501/503 mang ý nghĩa health khác nhau, không phải mã “feature supported”. Một số yêu cầu tới endpoint health phải thực hiện ở root namespace.
- `GET /v1/sys/mounts` và `GET /v1/sys/mounts/{path}` cho biết các engine đã mount và cấu hình, nhưng quyền xem inventory có thể bị giới hạn.
- `GET /v1/sys/plugins/catalog` cho biết plugin trong catalog, không đủ để xác nhận plugin đang chạy ở mount nào.
- `POST /v1/sys/capabilities-self` trả capability của **token hiện tại** trên danh sách path.

Ví dụ kiểm tra token workload ở staging:

~~~bash
# Chạy bằng VAULT_TOKEN của identity cần kiểm tra.
vault token capabilities secret/data/orders/config
vault token capabilities payments-transit/encrypt/orders-key
vault token capabilities pki_int/issue/orders-server
~~~

**Phân biệt quyền với khả năng:** capability `update` trên `payments-transit/encrypt/orders-key` chưa chứng minh có mount Transit, key tồn tại, thuật toán được hỗ trợ hoặc body hợp lệ. Khả năng `deny` cũng có thể do policy hoặc namespace, chứ không nhất thiết server không triển khai endpoint.

Nếu token runtime không có quyền xem `sys/mounts`, đội vận hành hoặc deployment pipeline có quyền riêng nên cung cấp bản inventory. Không cấp quyền quản trị trên toàn bộ mounts chỉ để làm health check.

### 3.1. Plugin version phải lấy tại mount

Vault hỗ trợ các loại plugin như auth, secret và database. Plugin external/discrete có thể có vòng đời version độc lập với Vault server; cùng loại plugin có thể chạy ở nhiều mount với các version khác nhau. Lệnh `vault secrets list -detailed` hiển thị trường cấu hình **Version** và **Running Version** khi có dữ liệu; hai giá trị có thể khác nếu đã đổi cấu hình nhưng chưa reload plugin.

Do đó một báo cáo tương thích cần ghi **version đang chạy**, không chỉ version có trong plugin catalog. Plugin đã được đăng ký thành công nhưng lỗi startup, dependency hoặc runtime vẫn có thể khiến API không sẵn sàng.

## 4. Bản đồ API chuyên biệt và API chung trong Spring Vault

Spring Vault có extension thuận tiện cho một số secrets engine, nhưng không phải mọi Vault plugin đều có interface Java tương ứng.

| Chức năng/engine | Lối vào Java tiêu biểu | Cần kiểm chứng |
| --- | --- | --- |
| KV v1 | `VaultKeyValueOperations` với `KeyValueBackend.KV_1` | Mount chạy KV v1, path không chứa `data/`. |
| KV v2 | `VaultKeyValueOperations` với `KeyValueBackend.KV_2` | Mount chạy KV v2, path `data/`/`metadata/`, CAS/version. |
| Transit | `VaultOperations.opsForTransit(path)` | Mount đúng Transit, key, algorithm, context và ACL. |
| PKI | `VaultOperations.opsForPki(path)` | Issuer/CA/role, SAN, TTL, ACL issue/sign. |
| Transform (Enterprise) | `VaultTransformOperations` nếu client có hỗ trợ | Edition/license, role, template, mount và policy. |
| Token/System | API chuyên biệt của Vault token/system operations | Scope của token, endpoint, capability. |
| Database credentials | `VaultOperations.read("database/creds/{role}")` | Plugin database, role, lease, username/password schema. |
| AWS/SSH/TOTP/custom | `VaultOperations.read/write` hoặc HTTP client | Plugin-specific path, method, body, schema, TTL. |

**Quy tắc:** Giao diện Java chuyên biệt giúp mapping và tránh phải tự ghép nhiều path/response, nhưng **không tự tạo engine ở server**. Ngược lại, không thấy một interface Java riêng không có nghĩa server không hỗ trợ engine đó.

Spring Vault hiện đại hỗ trợ thao tác generic `read` (HTTP GET), `write` (HTTP POST), `list`, `delete` và các phương pháp giao tiếp HTTP thấp hơn. Với API engine dùng PATCH, DELETE đặc thù hoặc method ngoài các helper đang dùng, cần chọn đúng client/method theo tài liệu API. Không biến POST thành PATCH chỉ bằng cách đổi tên path.

## 5. Trường hợp điển hình: KV v1 và KV v2

Cùng engine type `kv` có thể sử dụng hai phiên bản API:

~~~text
Mount secret/ chạy KV v1:
  GET /v1/secret/orders/config

Mount secret/ chạy KV v2:
  GET /v1/secret/data/orders/config
  GET /v1/secret/metadata/orders/config
~~~

Đây là **KV API version**, không phải Vault HTTP API `/v1` hay version Vault server. Một Vault server có thể đồng thời chạy KV v1 trên `legacy-secret/` và KV v2 trên `secret/`.

Khi đã biết mount là KV v2:

~~~java
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

VaultKeyValueOperations kv =
        vaultOperations.opsForKeyValue("secret", KeyValueBackend.KV_2);

VaultResponse result = kv.get("orders/config");
// 'orders/config' là path tương đối so với mount 'secret/'.
~~~

Nếu code chọn KV v2 nhưng mount chạy v1, một request có thể đi tới path `secret/data/orders/config` không được engine v1 hỗ trợ. Đó là lỗi mapping mount/API, **không phải bằng chứng Vault server quá cũ**.

Từ **Spring Vault 4.1**, overload `opsForKeyValue(String path)` có thể xác định KV backend version bằng cách hỏi Vault. Method một tham số này **phụ thuộc version client**: code sử dụng nó sẽ không compile nếu jar đang dùng chưa có API tương ứng. Việc tự xác định còn phụ thuộc endpoint metadata và policy; với hệ thống giới hạn quyền, nên cấu hình rõ KV version rồi dùng overload tường minh sau khi đã kiểm chứng.

Có thể tham khảo CLI:

~~~bash
vault kv get -mount=legacy-secret orders/config
vault kv get -mount=secret orders/config
~~~

Vault CLI có khả năng che một số khác biệt đường HTTP. Khi tự viết HTTP client phải đối chiếu path thật của API engine, không chỉ dựa vào việc lệnh CLI thành công.

## 6. Trường hợp engine mở rộng: Database credentials

Giả sử môi trường có Database engine tại `database/` và role `orders-readonly` được cấu hình để cấp PostgreSQL credentials ngắn hạn. Spring Vault có thể dùng API chung `VaultOperations.read(String)`:

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersDbCredentials {

    private final VaultOperations vault;

    public OrdersDbCredentials(VaultOperations vault) {
        this.vault = vault;
    }

    public CredentialLease requestCredential() {
        // GET này sinh credential động/lease trên Vault.
        // Chỉ gọi khi nghiệp vụ thực sự cần cấp credential.
        VaultResponse response =
                vault.read("database/creds/orders-readonly");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Vault không trả credential theo hợp đồng đã kiểm chứng");
        }

        Map<String, Object> fields = response.getData();
        Object rawUser = fields.get("username");
        Object rawPassword = fields.get("password");

        if (!(rawUser instanceof String username) || username.isBlank()
                || !(rawPassword instanceof String password)
                || password.isBlank()) {
            throw new IllegalStateException(
                    "Schema DB credential chưa được hỗ trợ");
        }

        return new CredentialLease(
                username, password, response.getLeaseId());
    }

    public record CredentialLease(
            String username, String password, String leaseId) {}
}
~~~

Các điều kiện bắt buộc của ví dụ:

1. Spring Vault client có `VaultOperations.read` và `VaultResponse`.
2. Server đã mount Database engine ở đúng `database/`, cấu hình plugin kết nối tới DB và role `orders-readonly`.
3. Workload token có capability `read` trên `database/creds/orders-readonly`.
4. Response có `data.username`, `data.password` và lease metadata phù hợp; credential được kiểm thử dùng được trên DB với quyền dự kiến.
5. Ứng dụng quản lý TTL/lease, renew/revoke và thay đổi connection pool khi credential hết hạn.

**Quan trọng:** Dù dùng HTTP GET, endpoint này **có side effect**: Vault tạo credential động và lease. Không gọi nó mỗi giây trong liveness probe, không lấy credential chỉ để “thử endpoint có tồn tại”. Record chứa password chỉ là ví dụ mô hình hóa; trong sản xuất phải hạn chế thời gian lưu biến, không log/serialize password và bảo vệ crash dump.

Một custom engine có thể dùng `POST my-engine/issue` với schema khác. Không hard-code parser database cho mọi engine mới. Dựa vào tài liệu của **đúng plugin version đang chạy** và dựng model dữ liệu phù hợp.

## 7. Tính năng Enterprise và custom plugin

Một client có thể có lớp `VaultTransformOperations` nhưng Vault cluster Community không có feature Transform tương ứng. Nâng cấp jar Java không thay đổi edition, license, engine mount hay ACL của server.

| Bằng chứng quan sát | Điều khẳng định được | Điều chưa được khẳng định |
| --- | --- | --- |
| Class `VaultTransformOperations` tồn tại trong jar. | Client có khả năng gọi API Java tương ứng. | Server có Transform engine, license và policy. |
| Plugin `my-plugin` xuất hiện trong catalog. | Plugin đã đăng ký với Vault. | Plugin đã mount hoặc runtime hoạt động. |
| `vault secrets list` có mount `my-plugin/`. | Engine đang được khai báo tại mount đó. | Running Version/endpoint cụ thể thực thi đúng. |
| API thành công bằng root token của lab. | Endpoint có thể hoạt động với quyền rộng. | Workload token có quyền tương ứng. |
| API trả HTTP 200. | Một request đã được xử lý thành công. | Schema, lease và side effect phù hợp nghiệp vụ. |

Plugin ngoài còn có vấn đề binary/OCI runtime, Vault plugin protocol/SDK, phụ thuộc dịch vụ ngoài và phiên bản đang chạy. Một plugin đăng ký được nhưng không khởi tạo hoặc không tương thích với server có thể lỗi khi phục vụ request. Cần kiểm tra log/plugin health trong môi trường có quyền vận hành.

Nếu engine mới có API mà Spring Vault chưa bọc sẵn, chọn hai phương án có kiểm chứng:

- Gọi endpoint qua `VaultOperations.read/write` khi HTTP GET/POST và JSON schema phù hợp.
- Dùng HTTP client tích hợp Vault authentication/session/TLS với method theo tài liệu endpoint khi yêu cầu PATCH, DELETE, custom header hoặc response khác.

Không tự tạo “fallback” sang endpoint khác chỉ vì trả 200: có thể làm sai cách bảo vệ dữ liệu hoặc cấp quyền rộng hơn.

## 8. Quy trình xác định feature có thực sự khả dụng

~~~mermaid
flowchart TD
 A["Chốt nghiệp vụ và endpoint cần dùng"] --> B["Kiểm tra API của Spring Vault version đang build"]
 B --> C{"Có method Java chuyên biệt?"}
 C -->|Có| D["Dùng interface phù hợp và mount path chính xác"]
 C -->|Không| E["Chọn Vault HTTP API generic theo contract"]
 D --> F["Kiểm tra Vault edition/server/plugin Running Version"]
 E --> F
 F --> G{"Engine/role/key đã cấu hình tại mount?"}
 G -->|Không| H["Báo thiếu cấu hình/feature cho vận hành"]
 G -->|Có| I["Xác minh token workload, namespace và ACL"]
 I --> J{"Có capability cần thiết?"}
 J -->|Không| K["Điều chỉnh policy hoặc identity theo quyền tối thiểu"]
 J -->|Có| L["Chạy integration contract test trên Vault test/staging"]
 L --> M{"Schema và side effect đáp ứng?"}
 M -->|Có| N["SUPPORTED: có bằng chứng để rollout"]
 M -->|Không| O["BLOCKED/UNKNOWN: lưu nguyên nhân và cách khắc phục"]
~~~

Một feature **không được kết luận SUPPORTED** chỉ vì server version nằm trên một ngưỡng đọc được từ changelog. Ngoài version, còn phải thỏa mount/role, quyền và kiểm thử hành vi.

Lưu các trường sau cho mỗi feature:

| Thuộc tính | Ví dụ minh họa |
| --- | --- |
| Feature ID | `db-orders-readonly` |
| Vault API | `GET database/creds/orders-readonly` |
| Mount/engine/plugin | `database/` và database plugin đang chạy |
| Client API | `VaultOperations.read(String)` |
| Spring Vault/JDK | Version thực tế trong runtime |
| Vault server/edition | Version và Community/Enterprise từ môi trường |
| Plugin Running Version | Từ inventory mount |
| Identity và policy | Auth role của workload, `read` tại path thật |
| Response contract | `username`, `password`, `lease_id`, `lease_duration` |
| Test | Cấp credential, kết nối DB, thu hồi lease |
| Kết quả | `SUPPORTED`, `BLOCKED` hoặc `UNKNOWN` và bằng chứng |

`UNKNOWN` là trạng thái hợp lệ khi chưa được cấp môi trường/identity để kiểm tra. Không biến “không có bằng chứng thiếu feature” thành “đã hỗ trợ”.

## 9. Đối chiếu dependency client một cách chính xác

Trong Java, version được tải vào runtime có thể khác version nhìn thấy trực tiếp ở một khai báo Gradle/Maven bởi BOM, starter hoặc dependency mediation.

Ví dụ với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.vault:spring-vault-core
~~~

Ví dụ với Gradle:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-vault-core \
  --configuration runtimeClasspath
~~~

Các lệnh này là gợi ý cho người học chạy trên dự án của mình; bài này chưa chạy build. Nếu sử dụng Spring Cloud Vault starter, kiểm tra thêm phiên bản Spring Boot/Spring Cloud và bản `spring-vault-core` được quản lý trong dependency graph.

**JavaDoc phải khớp phiên bản client thực sự**. Ví dụ tài liệu của Spring Vault 4.1 cho biết Java SE 17+ và có overload mới cho KV backend detection; không suy API đó sẵn có trong mọi phiên bản 3.x/4.0. Khi cần một method mới, đọc changelog/migration guide và nâng client theo compatibility matrix của framework dự án. Một baseline tổng quát ghi trong Getting Started không có nghĩa mọi endpoint mới của Vault server đều chạy trên mọi Vault version đáp ứng baseline đó.

Bên Vault, lưu chính xác:

~~~text
environment          : staging
vault_endpoint       : https://vault-staging.example.test
vault_server_version : <lấy từ cluster thực>
vault_edition        : <lấy từ cluster thực>
vault_namespace      : <nếu áp dụng>
engine_mount         : database/
engine_type          : database
plugin_running_ver   : <lấy từ inventory>
spring_vault_version : <lấy từ jar runtime>
jdk_runtime_version  : <lấy từ runtime>
workload_auth        : <Kubernetes/AppRole/...>
workload_identity    : <role name, không phải Vault token>
feature_endpoint     : database/creds/orders-readonly
~~~

Các giá trị placeholder phải được điền bằng thông tin thật của **cùng môi trường và cùng thời điểm kiểm thử**. Nếu production khác staging ở plugin version hoặc mount, không thể dùng kết quả test staging để khẳng định production hỗ trợ đầy đủ.

## 10. Capability detection phải an toàn

Một số endpoint như `sys/health` không kiểm tra tính năng cụ thể. Một số endpoint khác có tên “read” nhưng có side effect, như `database/creds/...` sinh credential, `pki/issue/...` cấp certificate, `transit/keys/.../rotate` xoay khóa.

Không nên gọi endpoint tạo tài nguyên ở mỗi lần khởi động, readiness hoặc liveness probe chỉ để hỏi server có hỗ trợ không.

Thứ tự kiểm tra được khuyến nghị:

1. **Static client check:** chốt version thư viện, method, request model và feature flag trong deployment.
2. **Admin inventory:** xem Vault server edition, mount, plugin Running Version, KV options và role/config liên quan.
3. **ACL check:** dùng identity workload để kiểm tra capability trên endpoint cụ thể (không suy ra capability đồng nghĩa request hợp lệ).
4. **Read-only probe:** chỉ gọi endpoint *được tài liệu xác định không gây side effect* với tần suất có kiểm soát.
5. **Contract integration test:** chạy thao tác tạo dữ liệu trong Vault/database test cô lập, thu hồi/dọn tài nguyên theo lifecycle.
6. **Runtime guard:** nếu thiếu bằng chứng hoặc contract thất bại, bật cảnh báo, trả lỗi rõ hoặc tạm tắt chức năng phụ thuộc theo cấu hình đã phê duyệt.

Ví dụ cấu hình feature flag của ứng dụng:

~~~yaml
app:
  vault:
    extended:
      enabled: true
      mount: database
      role: orders-readonly
      contract: database-dynamic-creds-v1
~~~

`contract` ở đây chỉ là mã hợp đồng **do nhóm ứng dụng đặt** để gắn với kết quả kiểm thử, không phải version API mà Vault server tự cam kết. Tuyệt đối không đặt `enabled=true` thành bằng chứng tính năng được server hỗ trợ.

### 10.1. Kiểm soát lỗi và truy vết

Với một request có lỗi, ghi nhận loại thao tác, endpoint template, mount/role đã được phép ghi, server/plugin/client version, mã HTTP, request ID và latency. Không ghi Vault token, AppRole SecretID, private key PKI, database password, ciphertext nhạy cảm hoặc plaintext Transit vào log và trace.

| Triệu chứng | Khả năng | Kiểm tra tiếp |
| --- | --- | --- |
| Java báo `cannot find symbol` | Method chưa có trong jar client hoặc import sai. | Dependency runtime và JavaDoc đúng version. |
| 404 với `secret/data/...` | KV v1, mount sai, key vắng hoặc endpoint không tồn tại. | Mount options, KV version, namespace, path thực tế. |
| 403 tại `sys/mounts` | Identity không có quyền kiểm kê. | Nhờ role vận hành lấy inventory; không coi là không có engine. |
| 403 tại endpoint nghiệp vụ | ACL/auth role/namespace/parameter constraint từ chối. | Kiểm token của workload và path/method thật. |
| 400/405 | Body/parameter/method không hợp API/plugin version. | Tài liệu endpoint đúng version và HTTP method. |
| 5xx/timeout | Lỗi Vault/plugin/backend/DB/HA hoặc network. | Log server/plugin, circuit breaker, timeout và retry có giới hạn. |
| HTTP 200 nhưng mapping Java thất bại | Schema JSON khác hợp đồng. | Body đã loại secret, trường bắt buộc và kiểu dữ liệu. |
| Staging OK, production lỗi | Khác version plugin, edition, mount hoặc policy. | So manifest và chạy smoke test theo identity thật. |

Đặc biệt, **403/404 không đủ để kết luận server thiếu một feature**. Có thể hệ thống chỉ thiếu quyền hoặc đang gọi vào namespace/mount sai. Việc phân loại cần dựa trên nhiều bằng chứng thay vì retry vô hạn hay tự động fallback sang API nguy hiểm hơn.

## 11. Kiểm thử tương thích theo lớp

| Kiểm thử | Xác minh được | Chưa xác minh được |
| --- | --- | --- |
| Unit test/mock | Code mapping, nhánh xử lý lỗi, method tồn tại. | Mount, ACL hay plugin server thật. |
| HTTP contract test với stub | Method/path/body, mapping JSON và mã lỗi. | Vault thật có triển khai đúng contract. |
| Integration test với Vault test | Engine/role/policy, request thật và side effect. | Production đã cấu hình y hệt. |
| Staging smoke test | Stack phiên bản thực ở staging hoạt động. | Production cùng mọi version/permission. |
| Production canary có kiểm soát | Workload phiên bản mới chạy với môi trường thật trên phạm vi nhỏ. | Không còn lỗi TTL/lease/scale phát sinh theo thời gian. |

Với Database engine, một integration test có ý nghĩa:

1. Dùng Vault test và database test; mount engine và plugin **đúng version mục tiêu**.
2. Tạo database connection/role `orders-readonly` với ACL chỉ có `read` trên path cấp credential.
3. Gọi ứng dụng qua `VaultOperations.read("database/creds/orders-readonly")`.
4. Xác minh `data.username`, `data.password`, lease metadata và quyền thực của user trên database test.
5. Revoke lease hoặc cho hết hạn theo kịch bản, xác minh credential bị vô hiệu hóa theo plugin/backend.
6. Thử sai mount, role không tồn tại, token thiếu quyền và backend gián đoạn; kiểm tra lỗi không rò credential.
7. Ghi lại Vault server/plugin Running Version, Spring Vault/JDK, mount options, identity và thời điểm test.
8. Lặp lại sau khi đổi một trong các version, policy, mount hoặc schema.

Ví dụ assertions ở test tích hợp:

~~~java
VaultResponse response =
        vaultOperations.read("database/creds/orders-readonly");

assertNotNull(response);
assertNotNull(response.getData());
assertInstanceOf(String.class, response.getData().get("username"));
assertInstanceOf(String.class, response.getData().get("password"));
assertFalse(((String) response.getData().get("username")).isBlank());
~~~

Request này tạo lease nên **test phải dọn tài nguyên**, và không in `password` ra test report. Nếu JUnit phiên bản dự án chưa có `assertInstanceOf`, thay bằng assertion phù hợp.

Với KV kiểm tra v1/v2, CAS và metadata; với Transit kiểm tra key/algorithm/context và encrypt/decrypt/rewrap; với PKI kiểm tra issuer, role, TTL, SAN và CA chain; với các plugin khác kiểm tra operation cụ thể theo schema plugin.

## 12. Cách nâng cấp an toàn

Không có thứ tự nâng cấp server trước hay client trước áp dụng cho mọi trường hợp. Thứ tự đúng được quyết định bởi feature cần dùng và tài liệu compatibility tương ứng.

1. **Chốt trạng thái hiện tại:** lưu server/edition, plugin Running Version, mount/options, Spring Vault/JDK, auth/policy và suite test đang PASS.
2. **Chốt feature mới:** định nghĩa endpoint và contract; xem release notes của Vault, plugin, Spring Vault và các framework quản lý dependency.
3. **Thử trong môi trường giống mục tiêu:** dùng plugin/mount/identity và cấu hình tương đương; chạy hồi quy các luồng KV, token/lease, Transit, PKI liên quan.
4. **Nâng từng lớp có kiểm soát:** server/plugin trước nếu endpoint cần server mới; client trước nếu source code cần method mới, với điều kiện các lớp còn lại tương thích.
5. **Chạy integration/contract test và thử rollback:** xác minh data/lease cũ còn hoạt động, cách xử lý lỗi an toàn.
6. **Canary rollout:** bật feature flag ở phạm vi nhỏ, quan sát 4xx/5xx, latency, renew/revoke và lỗi auth/schema.
7. **Cập nhật manifest:** ghi lại đúng version/config đã chạy và bằng chứng PASS để lần nâng cấp sau so sánh.

Không chữa lỗi bằng cách đổi mount path hay loại bỏ policy check cho request thành công. Với engine quản lý secret, một đường API trả 200 nhưng truy cập nhầm namespace/key hoặc bỏ qua version/rotation vẫn là lỗi bảo mật/nghiệp vụ.

## 13. Bài thực hành tổng hợp

Giả sử một dịch vụ cần hai khả năng: cấp Database credentials qua `database/` và mã hóa thông tin bằng Transit mount `payments-transit/`. Đội vận hành nói rằng cluster staging đã có cả hai mount.

Hãy thu thập bằng chứng theo bảng:

| Feature | Endpoint | API client | Quyền tối thiểu | Kiểm thử |
| --- | --- | --- | --- | --- |
| DB credential | `GET database/creds/orders-readonly` | `VaultOperations.read` | `read` | Schema, kết nối DB, TTL/lease, revoke. |
| Transit encrypt | `POST payments-transit/encrypt/orders-key` | `opsForTransit("payments-transit")` | `update` | Ciphertext, key version, round-trip trong test. |

Với mỗi feature, kiểm tra server version/edition, plugin/mount thực tế, policy identity, schema và side effect. Kết luận trạng thái `SUPPORTED`, `BLOCKED` hoặc `UNKNOWN` cùng bằng chứng. Nếu Database có 403 nhưng Transit chạy được, hãy kiểm tra policy Database **trước khi** đề xuất nâng Vault server. Nếu plugin Database khác version giữa staging và production, đưa nó vào bản ghi rủi ro triển khai.

Một mẫu báo cáo:

~~~text
Environment         : staging
Feature             : db-orders-readonly
Vault server/edition: <từ môi trường>
Plugin Running Ver  : <từ mount>
Spring Vault + JDK  : <từ runtime>
Mounted engine      : database/
Auth / ACL          : <identity và capability đã xác minh>
Contract test       : PASS / FAIL / NOT_RUN
Decision            : SUPPORTED / BLOCKED / UNKNOWN
Reason / evidence   : <test id, HTTP status, đường lỗi đã bỏ secret>
~~~

Không ghi giả số phiên bản hoặc PASS khi chưa chạy test thật. Với credential nhạy cảm, chỉ lưu metadata kiểm thử và mã lỗi đã được loại secret.

## 14. Câu hỏi tự đánh giá

1. Vì sao code Java có `opsForTransit` vẫn có thể lỗi khi chạy dù version Spring Vault mới?
2. `Vault server version`, `plugin Running Version` và `Spring Vault client version` khác nhau thế nào?
3. Tại sao `vault plugin list secret` chưa đủ chứng minh plugin đang phục vụ endpoint tại một mount?
4. Khi Spring Vault không có class chuyên biệt cho engine mới, có thể làm gì?
5. KV v2 API khác KV v1 ra sao và điều đó liên quan gì đến mount option?
6. Vì sao permission `update` từ `sys/capabilities-self` chưa đủ khẳng định request thực thi được?
7. Vì sao endpoint `GET database/creds/orders-readonly` không phù hợp làm probe mỗi giây?
8. Có `VaultTransformOperations` ở client có bảo đảm Vault Community hỗ trợ Transform không?
9. Chứng cứ nào cần có để kết luận schema/lease của engine mới đáp ứng nghiệp vụ?
10. Nếu production có plugin khác staging, cần bổ sung kiểm thử và hồ sơ nào trước rollout?

## Tài liệu tham khảo

- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Vault — VaultOperations Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html)
- [Spring Vault — Getting Started, yêu cầu nền tảng](https://docs.spring.io/spring-vault/reference/introduction/getting-started.html)
- [Spring Vault — Vault repositories và mount metadata](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html)
- [HashiCorp Vault — HTTP API và compatibility](https://developer.hashicorp.com/vault/api-docs)
- [HashiCorp Vault — System Health API](https://developer.hashicorp.com/vault/api-docs/system/health)
- [HashiCorp Vault — System Mounts API](https://developer.hashicorp.com/vault/api-docs/system/mounts)
- [HashiCorp Vault — Capabilities Self API](https://developer.hashicorp.com/vault/api-docs/system/capabilities-self)
- [HashiCorp Vault — Plugin ecosystem và versioning](https://developer.hashicorp.com/vault/docs/plugins)
- [HashiCorp Vault — Secrets list và Running Version](https://developer.hashicorp.com/vault/docs/commands/secrets/list)
- [HashiCorp Vault — Plugin Catalog API](https://developer.hashicorp.com/vault/api-docs/system/plugins-catalog)
