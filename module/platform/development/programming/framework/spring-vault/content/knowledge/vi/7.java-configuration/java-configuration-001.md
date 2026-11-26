# Các bean tối thiểu để đọc được một secret

Trong chương **Cấu hình Java** của **SPRING_VAULT**, mục tiêu đầu tiên là để ứng dụng Java gọi được HashiCorp Vault, xác thực và lấy một giá trị bí mật. Trước khi triển khai các chủ đề nâng cao như xác thực theo workload, vòng đời token/lease, Transit encryption hoặc PKI, cần hiểu ba thành phần cơ bản: **VaultEndpoint**, **ClientAuthentication** và **VaultTemplate**.

Bài này cấu hình bằng Java, chủ động tạo các bean và đọc một secret thuộc **KV Secrets Engine**. Ví dụ sử dụng token từ biến môi trường để dễ chạy ở máy phát triển; phần cuối giải thích những điểm phải thay đổi khi đưa lên môi trường thật.

## 1. Một lần đọc secret cần những gì?

Giả sử dịch vụ quản lý đơn hàng cần đọc thông tin kết nối đến cơ sở dữ liệu. Thay vì lưu mật khẩu trong mã nguồn hoặc đưa giá trị bí mật trực tiếp vào file cấu hình ứng dụng, nhóm vận hành đặt chúng tại Vault:

| Thành phần | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| Địa chỉ Vault | `http://127.0.0.1:8200` | Máy chủ và cổng ứng dụng sẽ kết nối |
| Secrets engine | `secret` | Tên mount của KV engine |
| Phiên bản engine | `KV v2` | Ảnh hưởng đến đường dẫn API và cách đọc |
| Đường dẫn secret | `demo/app` | Đường dẫn bên trong mount `secret` |
| Các trường dữ liệu | `username`, `password` | Các khóa được lưu trong secret |
| Phương thức xác thực | Token (chỉ cho bài thực hành) | Bằng chứng để Vault xác định ứng dụng là ai |
| Policy tối thiểu | `read` tại `secret/data/demo/app` | Quyền đọc chính xác dữ liệu cần thiết |

Luồng thực hiện:

~~~mermaid
flowchart LR
    A["DatabaseSecretReader"] --> B["VaultTemplate"]
    B --> C["VaultEndpoint"]
    B --> D["ClientAuthentication"]
    B --> E["Vault KV v2<br/>secret/data/demo/app"]
    D -. "Xác thực request" .-> E
~~~

- **VaultEndpoint** trả lời câu hỏi *kết nối tới Vault nào?*
- **ClientAuthentication** trả lời câu hỏi *ứng dụng chứng minh danh tính như thế nào?*
- **VaultTemplate** cung cấp các thao tác Java để gửi request đã xác thực tới Vault.
- **VaultKeyValueOperations** là API chuyên biệt để đọc/ghi KV. Ta lấy đối tượng này từ `VaultTemplate`, nên ban đầu **không cần khai báo thêm bean**.

Cả kết nối hợp lệ lẫn token hợp lệ đều chưa đủ: Vault còn kiểm tra **policy** trước khi trả secret.

## 2. Chuẩn bị Vault và secret mẫu

### 2.1. Dependency

Trong ứng dụng Spring Boot đã có Spring Context, thêm thư viện cốt lõi của Spring Vault vào `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Ví dụ này giả định dự án đang quản lý phiên bản dependency tương thích qua Spring Boot/BOM. Nếu dự án không có cơ chế quản lý phiên bản cho thư viện này, hãy khai báo phiên bản Spring Vault tương thích với Spring Framework đang dùng. Không cần cài Spring Cloud Vault chỉ để tạo thủ công `VaultTemplate`.

Mã Java bên dưới dùng cú pháp Java 17 trở lên.

### 2.2. Khởi tạo Vault cục bộ

Có thể dùng một Vault dev server để thực hành. Trong một terminal:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Trong terminal khác, chỉ định endpoint và token:

~~~bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token

vault kv put secret/demo/app username=demo_user password=demo_password
vault kv get secret/demo/app
~~~

Với PowerShell, hai lệnh đặt biến môi trường tương ứng là:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"
~~~

Chạy lệnh `vault kv put` ở cùng terminal đã đặt biến môi trường. Dev server thường gắn KV v2 tại mount `secret/`; xác minh bằng `vault secrets list -detailed` nếu hệ thống thực hành đã được cấu hình khác. Dữ liệu và root token ví dụ này **chỉ dùng cho môi trường phát triển**, không dùng cho production.

Một secret KV v2 có dữ liệu ứng dụng tương đương:

~~~json
{
  "username": "demo_user",
  "password": "demo_password"
}
~~~

Đây là *nội dung logic* bên trong secret. Khi gọi API HTTP KV v2, Vault còn bao bọc nội dung này bằng thông tin phiên bản và metadata.

## 3. Khai báo đúng ba bean bằng Java

Tạo lớp `VaultJavaConfig.java` trong package được Spring Boot component scan:

~~~java
package com.example.vault;

import java.net.URI;
import java.util.Locale;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class VaultJavaConfig {

    // 1. Nơi gửi request. VAULT_ADDR có giá trị mặc định cho dev.
    @Bean
    VaultEndpoint vaultEndpoint(
            @Value("${VAULT_ADDR:http://127.0.0.1:8200}") String address) {

        URI uri = URI.create(address);
        String scheme = uri.getScheme();

        if (uri.getHost() == null
                || (!"http".equalsIgnoreCase(scheme)
                    && !"https".equalsIgnoreCase(scheme))) {
            throw new IllegalArgumentException("VAULT_ADDR phải là URL HTTP(S) hợp lệ");
        }

        int port = uri.getPort() >= 0
                ? uri.getPort()
                : ("https".equalsIgnoreCase(scheme) ? 443 : 80);

        VaultEndpoint endpoint = VaultEndpoint.create(uri.getHost(), port);
        endpoint.setScheme(scheme.toLowerCase(Locale.ROOT));
        return endpoint;
    }

    // 2. Danh tính của ứng dụng: token được cấp qua môi trường chạy.
    @Bean
    ClientAuthentication clientAuthentication(
            @Value("${VAULT_TOKEN}") String token) {
        return new TokenAuthentication(token);
    }

    // 3. API chính để tương tác với Vault.
    @Bean
    VaultTemplate vaultTemplate(
            VaultEndpoint vaultEndpoint,
            ClientAuthentication clientAuthentication) {
        return new VaultTemplate(vaultEndpoint, clientAuthentication);
    }
}
~~~

**Vì sao từng bean tồn tại?**

| Bean | Vai trò | Điều gì xảy ra nếu thiếu/sai? |
| --- | --- | --- |
| `VaultEndpoint` | Chứa host, port, scheme của Vault | Không thể định tuyến request tới máy chủ đúng |
| `ClientAuthentication` | Cung cấp thông tin xác thực cho request | Request có thể bị Vault từ chối vì token thiếu, sai, hết hạn hoặc không đủ quyền |
| `VaultTemplate` | Đóng gói HTTP client và các Vault operations | Service không có đối tượng Spring Vault để thực hiện đọc secret |

Ba phương thức `@Bean` có quan hệ phụ thuộc rõ ràng. Spring tạo `VaultEndpoint` và `ClientAuthentication`, sau đó truyền chúng vào `vaultTemplate(...)`. Lớp business không cần tự tạo kết nối mới mỗi lần đọc.

**Lưu ý về token:** `@Value("${VAULT_TOKEN}")` đọc từ cấu hình/môi trường của Spring. Khi không đặt `VAULT_TOKEN`, ứng dụng sẽ lỗi lúc tạo bean thay vì âm thầm sử dụng token mặc định. Đây là hành vi mong muốn đối với thông tin xác thực. Token ở đây là token tĩnh để minh họa; nó không tự có cơ chế làm mới khi hết hạn.

**Lưu ý về địa chỉ:** Đoạn mã xử lý URL HTTP(S) dạng `http://host:port` hoặc `https://host`. Vault chạy thật nên dùng HTTPS, chứng chỉ TLS đáng tin cậy và endpoint nội bộ có thể truy cập; cấu hình trust store hoặc HTTP client tùy chỉnh là chủ đề vận hành bổ sung.

### Tại sao chưa cần `@Bean VaultKeyValueOperations`?

`VaultTemplate` có sẵn phương thức `opsForKeyValue(mountPath, backend)`, trả về một đối tượng thao tác trên KV engine. Nếu một service chỉ đọc secret, lấy operations tại thời điểm gọi là đủ. Việc đưa `VaultKeyValueOperations` thành bean riêng chỉ hữu ích khi nhiều service cùng dùng một mount và phiên bản engine, ví dụ:

~~~java
@Bean
VaultKeyValueOperations applicationKv(VaultTemplate template) {
    return template.opsForKeyValue("secret", KeyValueBackend.KV_2);
}
~~~

Đoạn mở rộng này cần import `org.springframework.vault.core.VaultKeyValueOperations` và `org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend`. Nó **không nằm trong ba bean tối thiểu**.

## 4. Dùng `VaultTemplate` để đọc một secret KV v2

Tạo service `DatabaseSecretReader.java`:

~~~java
package com.example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class DatabaseSecretReader {

    private final VaultTemplate vaultTemplate;

    public DatabaseSecretReader(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public DatabaseCredentials read() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("demo/app");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Không tìm thấy secret tại secret/demo/app");
        }

        Map<String, Object> values = response.getData();

        String username = requireText(values, "username");
        String password = requireText(values, "password");

        return new DatabaseCredentials(username, password);
    }

    private static String requireText(Map<String, Object> values, String key) {
        Object value = values.get(key);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalStateException(
                    "Secret thiếu trường String hợp lệ: " + key);
        }
        return text;
    }

    public record DatabaseCredentials(String username, String password) {
    }
}
~~~

Cần phân biệt hai loại đường dẫn:

- `"secret"` là **mount path** của KV engine.
- `"demo/app"` là **đường dẫn tương đối** của secret trong mount.

Spring Vault tự chuyển thao tác KV v2 thành request tương ứng, về nguyên tắc là `GET /v1/secret/data/demo/app`. Vì vậy không chèn thêm `data/` vào tham số `get(...)`. Với API `VaultKeyValueOperations`, `response.getData()` cho phép truy cập trực tiếp các trường logic `username` và `password`.

Đoạn code đọc secret và kiểm tra cấu trúc trả về, nhưng chưa sử dụng mật khẩu để kết nối cơ sở dữ liệu. Một ứng dụng thật có thể đưa `DatabaseCredentials` vào thành phần tạo kết nối hoặc cập nhật cấu hình theo vòng đời phù hợp; cần tránh đưa giá trị bí mật lên log hoặc response HTTP.

### Chạy kiểm tra tối thiểu khi khởi động

Tạo một bean `CommandLineRunner` trong lớp ứng dụng Spring Boot để xác minh service đọc thành công:

~~~java
package com.example.vault;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class VaultExampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(VaultExampleApplication.class, args);
    }

    @Bean
    CommandLineRunner checkSecret(DatabaseSecretReader reader) {
        return args -> {
            reader.read();
            System.out.println("Đã đọc và kiểm tra cấu trúc secret từ Vault.");
        };
    }
}
~~~

Nếu chạy theo ví dụ, cần có dependency Spring Boot application phù hợp bên cạnh `spring-vault-core`. Kết quả mong đợi:

~~~text
Đã đọc và kiểm tra cấu trúc secret từ Vault.
~~~

Chỉ in thông báo thành công; **không in username, password, token hoặc toàn bộ `VaultResponse`**. Khi secret thiếu, token không hợp lệ hoặc mất kết nối Vault, ứng dụng sẽ xuất lỗi thay vì giả vờ đọc thành công.

## 5. KV v1 và KV v2: chọn đúng API

Cùng tên mount `secret` nhưng cách vận hành giữa hai phiên bản KV khác nhau. Cần xác nhận phiên bản thực tế trước khi viết mã.

| Tiêu chí | KV v1 | KV v2 |
| --- | --- | --- |
| API trong Spring Vault | `KeyValueBackend.KV_1` | `KeyValueBackend.KV_2` |
| Ví dụ HTTP GET | `/v1/secret/demo/app` | `/v1/secret/data/demo/app` |
| Lưu phiên bản secret | Không | Có, kèm metadata |
| Policy đọc | `path "secret/demo/app"` | `path "secret/data/demo/app"` |
| Mã Java | `opsForKeyValue("secret", KV_1)` | `opsForKeyValue("secret", KV_2)` |

Đây là lý do nên dùng `opsForKeyValue` thay vì gọi trực tiếp `vaultTemplate.read("secret/data/demo/app")` trong ví dụ đầu tiên. Với API thấp hơn, caller phải tự hiểu cấu trúc bao ngoài của response KV v2, dễ nhầm `data` với dữ liệu ứng dụng.

Các phép đọc KV có thể trả về kết quả rỗng khi đường dẫn không tồn tại, hoặc phát sinh ngoại lệ ở các lỗi giao tiếp, permission hay protocol. Kiểm tra `null` **và** có chiến lược xử lý ngoại lệ thích hợp ở ranh giới ứng dụng.

## 6. Policy: có token vẫn cần đúng quyền

Để cho phép **chỉ đọc** secret `demo/app` của KV v2, policy HCL tối thiểu có thể là:

~~~hcl
path "secret/data/demo/app" {
  capabilities = ["read"]
}
~~~

Policy này cần được gắn vào token hoặc danh tính mà ứng dụng sử dụng. Token dành riêng cho service chỉ nên nhận các quyền tối thiểu; ví dụ đọc một secret không cần `create`, `update`, `delete` hoặc `list`.

Nếu dùng KV v1, đường dẫn trong policy thay đổi thành `secret/demo/app`. Với KV v2, một số thao tác đọc metadata, liệt kê hoặc xem lịch sử phiên bản có đường dẫn policy khác; bài thực hành hiện tại chỉ yêu cầu đọc giá trị mới nhất của một secret, nên không cần mở quyền cho các thao tác đó.

## 7. Các lỗi thường gặp và cách khoanh vùng

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra / hướng xử lý |
| --- | --- | --- |
| Spring không tạo được bean, thiếu `VAULT_TOKEN` | Chưa cung cấp biến môi trường | Đặt `VAULT_TOKEN` ở tiến trình chạy ứng dụng; không hardcode token vào Git |
| Kết nối bị từ chối hoặc timeout | Địa chỉ/cổng sai, Vault không chạy, mạng chặn | Kiểm tra `VAULT_ADDR`, trạng thái Vault và khả năng kết nối từ chính workload |
| Lỗi TLS handshake/chứng chỉ | Dùng HTTPS nhưng chain CA không đáng tin cậy | Cấu hình chứng chỉ và trust store đúng; không tắt kiểm tra TLS để chữa lỗi |
| Vault trả 403 | Policy thiếu `read` hoặc sai đường dẫn KV v2 | Soát policy gắn với danh tính chạy ứng dụng, đặc biệt đoạn `/data/` |
| Vault trả 401 / lỗi token | Token không hợp lệ, hết hạn hoặc bị thu hồi | Kiểm tra phương thức đăng nhập và vòng đời token; cấp lại đúng quy trình |
| Secret không tồn tại, trả null hoặc 404 | Nhầm mount, đường dẫn hoặc phiên bản KV | Kiểm tra `secret`, `demo/app`, `KV_1`/`KV_2` và dữ liệu đã ghi |
| Có response nhưng thiếu field | Dữ liệu trong secret thay đổi cấu trúc | Kiểm tra schema, tên `username`/`password`; xử lý lỗi rõ ràng |
| Đọc được lúc đầu nhưng thất bại về sau | Token tĩnh hết TTL hoặc bị revoke | Thay token tĩnh bằng xác thực workload và quản lý session/token có vòng đời |

Ví dụ, nếu chạy `vault kv get secret/demo/app` thành công với root token trên máy cá nhân nhưng ứng dụng bị 403 ở cluster, điều đó **không** chứng minh ứng dụng có quyền. Phải kiểm tra identity và policy đúng với token hoặc auth role của ứng dụng tại cluster.

Tránh in nội dung secret trong stack trace tự tạo, sự kiện audit của ứng dụng, logs hoặc dashboard. Có thể ghi nhận đường dẫn logic, loại lỗi và thời gian truy cập ở mức phù hợp, nhưng không ghi token hay mật khẩu.

## 8. Từ ví dụ cục bộ tới ứng dụng production

Cấu hình ba bean ở trên phù hợp để nhìn rõ các mảnh ghép của Spring Vault, nhưng token cố định chỉ là lựa chọn thực hành. Khi đưa dịch vụ vào workload thật:

1. **Xác thực theo workload.** Chọn cơ chế như Kubernetes auth, AppRole hoặc identity của nền tảng triển khai để Vault cấp quyền dựa trên danh tính chạy thực tế. Thay `TokenAuthentication` bằng triển khai `ClientAuthentication` phù hợp và cấu hình session/token management.
2. **Cấp quyền nhỏ nhất.** Chỉ cho phép các secret và API cần dùng; cân nhắc tách role và policy theo ứng dụng, môi trường, namespace.
3. **Bảo vệ đường truyền.** Dùng HTTPS/TLS, CA đáng tin cậy, cấu hình mạng và timeout phù hợp. Không dùng root token, token dev, HTTP plaintext hoặc giá trị mặc định của bài demo.
4. **Thiết kế vòng đời secret.** Định nghĩa thời điểm đọc, cache hợp lý, cơ chế refresh khi secret thay đổi và phản ứng khi Vault tạm thời không sẵn sàng. Không giả định đọc một lần lúc khởi động sẽ tự nhận mọi thay đổi sau này.
5. **Giám sát, kiểm thử tích hợp.** Kiểm tra tình huống đọc thành công, policy 403, secret thiếu, Vault unavailable và token hết hạn bằng môi trường kiểm thử có Vault thật hoặc container thử nghiệm. Chỉ đo latency, tỷ lệ lỗi và trạng thái hệ thống; không công bố dữ liệu bí mật.

**Phân biệt hai vòng đời:** Secret KV tĩnh thường không tạo một lease mới cho mỗi lần đọc; còn *token dùng để gọi Vault* có TTL và có thể bị thu hồi. Những loại secret động, chứng chỉ PKI hoặc thao tác Transit có semantics và API riêng. Sau khi làm chủ `VaultTemplate` và cách xác thực cơ bản, có thể mở rộng sang quản lý token/lease, Transit và PKI mà không gộp chúng vào quy trình đọc KV.

## 9. Tự kiểm tra sau bài học

Hãy trả lời được các câu sau trước khi chuyển sang bài tiếp theo:

- Tại sao service chỉ cần inject `VaultTemplate`, còn `VaultEndpoint` và `ClientAuthentication` được Spring quản lý ở lớp cấu hình?
- Với mount `secret` là KV v2 và đường dẫn `demo/app`, phương thức Java truyền vào `get(...)` giá trị gì? Policy `read` phải chỉ tới đường dẫn nào?
- Nếu CLI đọc được bằng root token nhưng ứng dụng nhận 403, nên kiểm tra quyền của danh tính nào?
- Vì sao không nên ghi một token cố định trong mã nguồn và vì sao token hợp lệ hôm nay chưa chắc còn hợp lệ sau khi hết TTL?

Hoàn thành bài thực hành nghĩa là ứng dụng tạo được ba bean, đọc đúng `username` và `password` từ KV v2 và thông báo thành công mà không tiết lộ secret. Đó là nền tảng trực tiếp cho các bài Spring Vault tiếp theo về xác thực, phân quyền, vòng đời credential và tích hợp Vault trong ứng dụng Java.

