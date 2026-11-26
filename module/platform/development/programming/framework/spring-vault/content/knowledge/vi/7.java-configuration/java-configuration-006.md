# Khởi tạo VaultTemplate bằng các constructor phù hợp phiên bản

Trong chương **Cấu hình Java** của **SPRING_VAULT**, `VaultTemplate` là điểm vào chính để ứng dụng Java làm việc với HashiCorp Vault: đọc/ghi KV secrets, gọi Transit encryption, sử dụng PKI và các API token liên quan. Sau khi xác định `VaultEndpoint` và `ClientAuthentication`, ta cần tạo `VaultTemplate` với **constructor tồn tại trong phiên bản Spring Vault mà dự án thật sự dùng**.

Điểm dễ nhầm là API đã thay đổi theo các thế hệ: Spring Vault **3.2.x** thiên về `VaultEndpoint`, `RestTemplateBuilder` và `ClientHttpRequestFactory`; **4.0.x** bổ sung `RestClientBuilder`; từ **4.1.x** có `VaultClient` và nhiều constructor xây trên `RestTemplate`/request factory cũ được đánh dấu deprecated. Bài này so sánh các lựa chọn, cung cấp ví dụ Java theo phiên bản và hướng dẫn xác minh bằng một secret KV v2.

**Sau bài học**, bạn có thể chọn đúng constructor theo nhu cầu, biết khi nào dùng `ClientAuthentication` hoặc `SessionManager`, tránh vô tình gửi request không có token, và giữ nguyên được logic nghiệp vụ khi đổi cách xây HTTP client.

## 1. Các thành phần tham gia khởi tạo

`VaultTemplate` thuộc package `org.springframework.vault.core` và triển khai `VaultOperations`. Khi gọi các thao tác nghiệp vụ, template phụ thuộc vào những thành phần sau:

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `VaultEndpoint` | Xác định server/port/giao thức Vault | `https://vault.internal:8200` |
| `ClientAuthentication` | Lấy/cung cấp token cho danh tính workload | `TokenAuthentication`, AppRole, Kubernetes |
| `SessionManager` | Cấp token phiên làm việc và quản lý cách dùng lại, renew/revoke tùy triển khai | `SimpleSessionManager`, `LifecycleAwareSessionManager` |
| HTTP client/request factory | Thực hiện kết nối, TLS, timeout, proxy | `ClientHttpRequestFactory`, `RestClientBuilder` |
| `VaultClient` (4.1+) | Abstraction HTTP chuyên biệt cho Vault, hỗ trợ đường dẫn tương đối | `VaultClient.create(endpoint)` |
| `VaultTemplate` | Bao bọc API KV, Transit, PKI và các operations khác | `opsForKeyValue("secret", KV_2)` |

~~~mermaid
flowchart TD
    A["VaultEndpoint<br/>địa chỉ server"] --> D["HTTP client / VaultClient"]
    B["ClientAuthentication<br/>workload identity"] --> C["SessionManager"]
    C --> E["VaultTemplate"]
    D --> E
    E --> F["VaultOperations"]
    F --> G["KV v2"]
    F --> H["Transit / PKI"]
    F --> I["Token APIs"]
~~~

**Đọc đúng tầng trách nhiệm:** constructor của `VaultTemplate` xác định cách đối tượng có được kết nối và token. Nó không tạo Vault policy, không tự cấp quyền đọc một secret và không làm một token tĩnh trở thành token có thể gia hạn vô hạn.

### Đừng nhầm hai cách cấu hình

Có hai hướng thường gặp khi dùng Spring Framework/Spring Boot:

1. **Tự khai báo bean `VaultTemplate`:** chọn một constructor tường minh trong một lớp `@Configuration`.
2. **Kế thừa `AbstractVaultConfiguration`:** override `vaultEndpoint()` và `clientAuthentication()`; cấu hình cơ sở lo các bean hạ tầng, trong đó có `VaultTemplate` và session management.

Hai hướng phù hợp cho các nhu cầu khác nhau. Nếu chọn hướng thứ hai, **không cần thêm một `@Bean VaultTemplate` thủ công** chỉ vì thấy các ví dụ constructor trong bài này. Việc tạo hai cấu hình hạ tầng cùng lúc có thể gây trùng bean hoặc inject sai instance.

## 2. Bảng constructor theo Spring Vault 3.2, 4.0 và 4.1

Bảng dưới đây chọn các chữ ký quan trọng từ Javadoc chính thức; đây **không phải danh sách đầy đủ của mọi phiên bản lịch sử**.

| Constructor hoặc overload | 3.2.x | 4.0.x | 4.1.x | Nên chọn khi |
| --- | --- | --- | --- | --- |
| `VaultTemplate(VaultEndpoint, ClientAuthentication)` | Có | Có | Có | Cần khởi tạo nhanh với auth, không yêu cầu session lifecycle tùy chỉnh |
| `VaultTemplate(VaultEndpoint)` | Có | Có | Có | Đi qua Vault Agent/proxy **đã xử lý authentication**, không cần client gửi token header |
| `VaultTemplate(VaultEndpoint, ClientHttpRequestFactory, SessionManager)` | Có | Có | Deprecated từ 4.1 | Cần HTTP factory + session rõ ràng ở nhánh cũ |
| `VaultTemplate(VaultEndpointProvider, ClientHttpRequestFactory, SessionManager)` | Có | Có | Deprecated từ 4.1 | Hạ tầng nhánh cũ có endpoint provider |
| `VaultTemplate(RestTemplateBuilder, SessionManager)` | Có | Có | Deprecated từ 4.1 | HTTP builder kiểu RestTemplate trong code hiện có |
| `VaultTemplate(RestClientBuilder, SessionManager)` | Chưa có | Có | Có | Chuyển sang builder dùng `RestClient`, đặc biệt ở 4.0 |
| `VaultTemplate(VaultClient, ClientAuthentication)` | Chưa có | Chưa có | Có, từ 4.1 | Tạo đơn giản với `VaultClient` mới và auth |
| `VaultTemplate(VaultClient, SessionManager)` | Chưa có | Chưa có | Có, từ 4.1 | Kiểm soát HTTP client và token lifecycle trên API mới |
| `VaultTemplate(VaultClient)` | Chưa có | Chưa có | Có, từ 4.1 | Vault Agent/proxy hoặc trường hợp không dùng session token |

Hai chi tiết cần nhớ:

- **`RestClientBuilder` không đồng nghĩa với `VaultClient`.** Loại đầu tiên được bổ sung từ Spring Vault **4.0**; loại thứ hai là API mới từ **4.1**. Không copy import `VaultClient` vào dự án còn dùng 4.0.
- **Deprecated không có nghĩa đã bị xóa.** Nhiều constructor cũ vẫn biên dịch trong 4.1 nhưng nên ưu tiên `VaultClient` khi viết mới, nhất là khi tùy chỉnh TLS, timeouts hoặc HTTP client. Khi nâng cấp phiên bản lớn, kiểm tra lại Javadoc và build của chính nhánh đang sử dụng.

### Chọn nhanh theo nhu cầu

| Nhu cầu | Hướng khởi tạo đề xuất |
| --- | --- |
| Lab Java với token demo, cần tối thiểu | `new VaultTemplate(endpoint, authentication)` |
| Spring Boot đã kế thừa `AbstractVaultConfiguration` | Inject `VaultTemplate` hiện có |
| Spring Vault 3.2 cần factory + session riêng | `new VaultTemplate(endpoint, factory, sessionManager)` |
| Spring Vault 4.0 muốn dùng HTTP RestClient | `new VaultTemplate(restClientBuilder, sessionManager)` |
| Spring Vault 4.1 trở lên, code mới | `new VaultTemplate(vaultClient, authentication)` hoặc `(vaultClient, sessionManager)` |
| Vault Agent injection/proxy, không tự gửi token | Constructor không có authentication, **chỉ khi proxy đã được cấu hình đúng** |

## 3. Trước khi viết code: kiểm tra phiên bản thực tế

Tên lớp giống nhau không bảo đảm overload giống nhau. Nếu IDE hiển thị `Cannot resolve constructor` hoặc không import được `VaultClient`, đừng vội đổi constructor theo đoạn code trên mạng; trước hết xác định:

1. Artifact `org.springframework.vault:spring-vault-core` và **phiên bản thực tế được resolve**, gồm tác động của BOM/dependency management.
2. Phiên bản Spring Framework/Boot tương thích với phiên bản Spring Vault đó.
3. Kiểu tham số bạn truyền: `ClientAuthentication` khác `SessionManager`; `RestClientBuilder` khác `RestTemplateBuilder`; `VaultClient` chỉ có từ 4.1.
4. Các starter/integration đang tự đăng ký `VaultTemplate` hay không.

Ví dụ dependency trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Đoạn trên **chỉ hoàn chỉnh khi dự án đã quản lý phiên bản tương thích** qua BOM hoặc `dependencyManagement`. Nếu chưa có, cần cấp version rõ ràng. Không nên tự ý kéo một bản Spring Vault mới nhất vào dự án đang khóa Spring Framework cũ rồi chỉ sửa import để vượt lỗi biên dịch.

Nếu dùng Maven, có thể xem dependency được resolve (lệnh tham khảo, chạy trong dự án người học):

~~~bash
mvn dependency:tree -Dincludes=org.springframework.vault:spring-vault-core
~~~

Với Gradle, có thể kiểm tra cấu hình dependency thích hợp, ví dụ:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-vault-core \
  --configuration runtimeClasspath
~~~

Các lệnh này phục vụ người học kiểm tra môi trường. Phần thực hành của bài không yêu cầu build lại toàn bộ module sinh tài liệu.

## 4. Cách cơ bản tương thích nhiều phiên bản: Endpoint + ClientAuthentication

Đây là ví dụ dễ hiểu nhất cho một ứng dụng Spring Boot tự khai báo bean. Constructor `VaultTemplate(VaultEndpoint, ClientAuthentication)` tồn tại trong các nhánh **3.2, 4.0 và 4.1**.

Tạo `VaultConfig.java`:

~~~java
package com.example.vault;

import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class VaultConfig {

    @Bean
    VaultTemplate vaultTemplate(
            @Value("${VAULT_ADDR}") String address,
            @Value("${VAULT_TOKEN}") String token) {

        URI uri = URI.create(address);
        if (!"http".equalsIgnoreCase(uri.getScheme())
                && !"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException("VAULT_ADDR phải có http(s)");
        }
        if (uri.getHost() == null
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || (uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty()
                    && !"/".equals(uri.getRawPath()))) {
            throw new IllegalArgumentException(
                    "VAULT_ADDR phải là base URL của Vault");
        }
        if (token.isBlank()) {
            throw new IllegalArgumentException("VAULT_TOKEN không được rỗng");
        }

        VaultEndpoint endpoint = VaultEndpoint.from(uri);
        ClientAuthentication authentication =
                new TokenAuthentication(token);

        return new VaultTemplate(endpoint, authentication);
    }
}
~~~

**Vì sao constructor này phù hợp để bắt đầu?** Nó nhận đúng hai mảnh thông tin cần thiết: server và phương thức lấy/cung cấp token. Các operation thông thường sẽ gửi request tới endpoint và sử dụng token do Spring Vault cung cấp.

Trong những nhánh triển khai thông dụng, overload `(VaultEndpoint, ClientAuthentication)` sử dụng cơ chế session **đơn giản**: token được lấy và dùng lại, không phải lựa chọn được thiết kế để tự động renew/revoke mọi token. Không nên suy ra đã có vòng đời token đầy đủ chỉ vì code chạy được.

### Dùng nguồn biến môi trường an toàn

Trong terminal chạy ứng dụng local (Bash):

~~~bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token
~~~

Hoặc PowerShell:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"
~~~

Token trong ví dụ chỉ dùng cho Vault dev. **Không đưa token thật vào repository, log, trace hoặc HTTP response.** Ở staging/production nên dùng HTTPS với CA tin cậy và cơ chế authentication theo workload (Kubernetes/AppRole/cloud identity), cùng chính sách quản lý token/session phù hợp.

**Lưu ý:** `VaultEndpoint.from(uri)` tạo endpoint từ URI, không kiểm chứng Vault server có tồn tại hay không, certificate có đáng tin hay token được phép đọc. Cần một request thực để xác minh phần còn lại.

## 5. Spring Vault 3.2: truyền SessionManager và ClientHttpRequestFactory

Khi cần kiểm soát **HTTP timeout, TLS hoặc vòng đời token** ở nhánh 3.2.x, chọn overload:

~~~java
VaultTemplate(
    VaultEndpoint vaultEndpoint,
    ClientHttpRequestFactory clientHttpRequestFactory,
    SessionManager sessionManager)
~~~

Ví dụ dưới đây là một **phương án thay thế hoàn chỉnh** cho bean `vaultTemplate(...)` ở mục 4; không khai báo cả hai trong cùng Spring Context.

~~~java
package com.example.vault;

import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.authentication.SimpleSessionManager;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class Vault32Config {

    @Bean
    VaultTemplate vaultTemplate(
            @Value("${VAULT_ADDR}") String address,
            @Value("${VAULT_TOKEN}") String token) {

        VaultEndpoint endpoint =
                VaultEndpoint.from(URI.create(address));

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(3_000);
        factory.setReadTimeout(5_000);

        ClientAuthentication authentication =
                new TokenAuthentication(token);
        SessionManager sessionManager =
                new SimpleSessionManager(authentication);

        return new VaultTemplate(endpoint, factory, sessionManager);
    }
}
~~~

Ở đây:

- `ClientHttpRequestFactory` cấu hình cách thực hiện HTTP request; ví dụ chọn timeout 3 giây cho kết nối và 5 giây để đọc. **Đó là giá trị minh họa**, không phải SLO khuyến nghị cho mọi workload.
- `SessionManager` quản lý token mà request sẽ sử dụng. `SimpleSessionManager` không tự lên lịch renew hoặc revoke.
- Khi cần session lifecycle dài hạn, có thể dùng `LifecycleAwareSessionManager` cùng scheduler và HTTP client phù hợp, hoặc dựa vào cấu hình chuẩn của `AbstractVaultConfiguration`.
- `SimpleClientHttpRequestFactory` thích hợp cho lab đơn giản; muốn mTLS, kết nối qua proxy, trust store riêng hoặc pool connection cần HTTP client factory tương thích với hạ tầng đó.

**Không dùng overload `(endpoint, requestFactory)` thay cho `(endpoint, requestFactory, sessionManager)` nếu ứng dụng cần gửi token từ chính Java.** Overload không có authentication/session được thiết kế cho luồng mà Vault Agent/proxy xử lý xác thực.

### Khác với RestTemplateBuilder thế nào?

Spring Vault 3.2 cũng có constructor:

~~~java
VaultTemplate(
    RestTemplateBuilder restTemplateBuilder,
    SessionManager sessionManager)
~~~

Trong code hiện có dùng HTTP builder, overload này vẫn hợp lệ ở 3.2 và 4.0. Nhưng ở Spring Vault 4.1, nó thuộc nhóm **deprecated**; với code mới nên cân nhắc `VaultClient`. Không nhầm `org.springframework.vault.client.RestTemplateBuilder` với một loại builder của Spring Boot chỉ vì chúng có tên giống nhau.

## 6. Spring Vault 4.0: RestClientBuilder xuất hiện

Ở nhánh **4.0.x**, Spring Vault giới thiệu `org.springframework.vault.client.RestClientBuilder`. Nó tạo HTTP client dùng API `RestClient` của Spring, và `VaultTemplate` có overload nhận builder này cùng `SessionManager`.

Ví dụ thay thế cho bean mục 4 (chỉ dùng khi dependency đã ở nhánh 4.0+):

~~~java
package com.example.vault;

import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.SimpleSessionManager;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.RestClientBuilder;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class Vault40Config {

    @Bean
    VaultTemplate vaultTemplate(
            @Value("${VAULT_ADDR}") String address,
            @Value("${VAULT_TOKEN}") String token) {

        VaultEndpoint endpoint =
                VaultEndpoint.from(URI.create(address));

        RestClientBuilder builder = RestClientBuilder.builder()
                .endpoint(endpoint);

        SimpleSessionManager sessionManager =
                new SimpleSessionManager(
                        new TokenAuthentication(token));

        return new VaultTemplate(builder, sessionManager);
    }
}
~~~

`RestClientBuilder` là builder HTTP của Spring Vault; `VaultClient` chưa có ở nhánh 4.0 nên **không import `org.springframework.vault.client.VaultClient` trong dự án 4.0**.

Cả `new VaultTemplate(builder)` và `new VaultTemplate(builder, sessionManager)` đều tồn tại từ 4.0, nhưng chỉ overload thứ hai có session manager để cung cấp Vault token cho request. Với overload không có session, Spring Vault không tự thêm token của ứng dụng.

Khi dùng 4.1, `RestClientBuilder` vẫn tồn tại, nhưng kiến trúc mới có `VaultClient`. Việc giữ builder cũ để phục vụ migration có thể hợp lý; code mới nên ưu tiên thiết kế 4.1 ở mục tiếp theo.

## 7. Spring Vault 4.1: ưu tiên constructor dựa trên VaultClient

Từ **Spring Vault 4.1**, lớp `org.springframework.vault.client.VaultClient` cung cấp API HTTP chuyên biệt của Vault. Nó xử lý đường dẫn tương đối dựa trên `VaultEndpoint` và tạo ranh giới rõ hơn giữa thao tác Vault với cấu hình HTTP tổng quát.

Những constructor quan trọng:

~~~java
new VaultTemplate(vaultClient);
new VaultTemplate(vaultClient, clientAuthentication);
new VaultTemplate(vaultClient, sessionManager);
~~~

Trong đó:
- `(VaultClient)` không tự thêm credential; dùng khi luồng xác thực đã được một proxy/agent đảm nhiệm.
- `(VaultClient, ClientAuthentication)` phù hợp khi cần tạo nhanh và xác thực bằng provider cụ thể.
- `(VaultClient, SessionManager)` cho phép tái sử dụng session manager đã cấu hình, nhất là với workload chạy lâu.

### 7.1. Ví dụ 4.1 tối thiểu

Tạo `Vault41Config.java`, thay thế một trong các ví dụ cấu hình ở các mục trước:

~~~java
package com.example.vault;

import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
public class Vault41Config {

    @Bean
    VaultTemplate vaultTemplate(
            @Value("${VAULT_ADDR}") String address,
            @Value("${VAULT_TOKEN}") String token) {

        VaultEndpoint endpoint =
                VaultEndpoint.from(URI.create(address));
        VaultClient client = VaultClient.create(endpoint);

        ClientAuthentication authentication =
                new TokenAuthentication(token);

        return new VaultTemplate(client, authentication);
    }
}
~~~

Cấu hình này tách rõ **HTTP client** (`VaultClient`) với **nguồn token** (`ClientAuthentication`). Code đọc KV/Transit/PKI ở service không cần thay đổi khi chuyển từ `VaultTemplate(endpoint, authentication)` sang `VaultTemplate(client, authentication)`.

### 7.2. Ví dụ 4.1 với SessionManager và HTTP factory tùy chỉnh

Khi cần kiểm soát connection/TLS/timeout, sử dụng builder của `VaultClient`:

~~~java
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

// Trong lớp @Configuration, dùng đúng một bean VaultTemplate:
@Bean
VaultTemplate vaultTemplate(
        VaultEndpoint endpoint,
        ClientHttpRequestFactory requestFactory,
        SessionManager sessionManager) {

    VaultClient client = VaultClient.builder()
            .endpoint(endpoint)
            .requestFactory(requestFactory)
            .build();

    return new VaultTemplate(client, sessionManager);
}
~~~

Đoạn trên **giả định** ba dependency `VaultEndpoint`, `ClientHttpRequestFactory` và `SessionManager` đã được cấu hình thành Spring bean thích hợp. Nó là mẫu nâng cao để tích hợp vào hệ thống có hạ tầng HTTP riêng, không phải một file Java có thể chạy độc lập khi chưa cung cấp các bean đó.

Nếu chỉ cần token demo, có thể thay bằng `new SimpleSessionManager(new TokenAuthentication(token))`, nhưng việc thay lifecycle manager bằng simple manager đồng nghĩa mất khả năng renew token tự động.

Ưu điểm của `VaultClient.builder()` là có thể cấu hình HTTP factory một lần rồi cấp cho `VaultTemplate`. Với Spring Vault 4.1+, nhiều constructor kiểu `(VaultEndpoint, ClientHttpRequestFactory, SessionManager)` đã deprecated. Do đó, khi cập nhật code mới, chỉ thay cách tạo HTTP client ở tầng configuration, giữ interface nghiệp vụ `VaultOperations` khi phù hợp.

### 7.3. Các constructor cũ có bị vô hiệu hóa ngay không?

Không. Javadoc 4.1 vẫn liệt kê `VaultTemplate(VaultEndpoint, ClientAuthentication)` và các constructor cũ khác. Một số overload dùng `ClientHttpRequestFactory`, `VaultEndpointProvider` hoặc `RestTemplateBuilder` được đánh dấu `@Deprecated(since="4.1")`. Nghĩa là chúng vẫn có thể biên dịch trong 4.1 nhưng có tín hiệu sẽ được thay bằng API mới.

Cần phân biệt **không tồn tại** với **deprecated** khi xử lý lỗi:
- Không tồn tại: IDE/Java compiler không tìm thấy class hoặc constructor trong phiên bản hiện tại.
- Deprecated: class/constructor vẫn có thể sử dụng, compiler có thể phát warning; cần lên kế hoạch migration.
- Lỗi runtime: constructor biên dịch nhưng endpoint, auth, policy hoặc TLS vẫn có thể sai.

## 8. Trường hợp chỉ truyền VaultEndpoint: dành cho Vault Agent/proxy

Câu lệnh sau có vẻ ngắn:

~~~java
VaultEndpoint endpoint =
        VaultEndpoint.from(URI.create("http://127.0.0.1:8200"));

VaultTemplate template = new VaultTemplate(endpoint);
~~~

Nhưng `VaultTemplate(VaultEndpoint)` **không sử dụng cơ chế `ClientAuthentication`**, và không mặc nhiên gắn header `X-Vault-Token`. Javadoc mô tả nó cho tình huống đi qua **Vault Agent** để client kế thừa authentication do agent/proxy xử lý.

Vì vậy, không nên dùng overload chỉ có endpoint để gọi trực tiếp một Vault server yêu cầu token rồi chờ nó “tự phát hiện” `VAULT_TOKEN` trong môi trường.

### Điều gì phải đúng khi dùng Vault Agent?

| Yêu cầu | Ý nghĩa |
| --- | --- |
| Vault Agent đã cấu hình auto-auth/proxy phù hợp | Agent có thể lấy hoặc xử lý credential theo thiết kế |
| App trỏ endpoint tới listener/proxy phù hợp | Không nhầm địa chỉ agent với Vault server trực tiếp |
| Đường đi request kế thừa authentication dự kiến | Java không tự gửi token nhưng request vẫn phải được ủy quyền theo policy |
| Kênh truyền được bảo vệ | Đặc biệt khi agent/proxy ở máy khác hoặc container khác |
| Có xử lý khi agent unavailable | Không coi mọi lỗi proxy là lỗi policy của Vault |

Một ứng dụng có thể dùng agent để đơn giản hóa credential handling, nhưng vẫn phải quản lý security boundary, policy và lỗi vận hành. Không phải cứ thấy Vault Agent chạy ở gần là constructor không có authentication sẽ tự hoạt động.

## 9. SessionManager và vòng đời token khi chọn constructor

Một trong những khác biệt có tác động lớn nhất giữa overload **có `ClientAuthentication`** và **có `SessionManager`** là mức kiểm soát vòng đời token.

| Cấu hình | Có token cho request? | Có tự renew token? | Lưu ý |
| --- | --- | --- | --- |
| `new VaultTemplate(endpoint, authentication)` | Có | Không nên giả định có lifecycle renewal | Phù hợp lab/khởi tạo đơn giản |
| `new VaultTemplate(client, authentication)` (4.1+) | Có | Không nên giả định có lifecycle renewal | Phù hợp code mới với auth đơn giản |
| `new VaultTemplate(endpoint, factory, manager)` (3.2/4.0) | Theo manager | Theo triển khai manager | Dùng manager có chủ đích |
| `new VaultTemplate(client, manager)` (4.1+) | Theo manager | Theo triển khai manager | Tách kết nối khỏi lifecycle |
| `AbstractVaultConfiguration` mặc định | Có | Có thể quản lý renewal qua `LifecycleAwareSessionManager` khi token cho phép | Thích hợp Spring Context cần lifecycle |
| Constructor không có auth/session | Không tự đính token | Không | Chỉ dùng khi proxy/agent đảm trách |

### SimpleSessionManager và LifecycleAwareSessionManager

`SimpleSessionManager` lấy token qua `ClientAuthentication` rồi tái sử dụng mà không tự sắp lịch renew/revoke. `LifecycleAwareSessionManager` có thể quản lý renewal theo TTL, quyền và khả năng renewable của token; cần scheduler và cấu hình phù hợp.

Dù sử dụng lifecycle manager, **token không renewable, đã revoke hoặc đạt giới hạn TTL** vẫn có thể không được gia hạn. Với workload running lâu, nên dùng auth method có khả năng cấp token mới (Kubernetes, AppRole hoặc cloud identity phù hợp) và thiết kế session/credential rotation tương ứng.

**Phân biệt token với lease:** đọc một secret KV tĩnh không tạo lease mới cho mỗi request; còn database dynamic credential hoặc một số tài nguyên khác có lease riêng. `SessionManager` điều khiển token phiên làm việc, trong khi `SecretLeaseContainer` hoặc logic chuyên biệt quản lý lease của secret động. Chọn constructor đúng chưa giải quyết toàn bộ bài toán lease của ứng dụng.

### Ai sở hữu lifecycle của manager?

Khi tự tạo `SessionManager` trong thân một phương thức `@Bean` rồi truyền vào template, có thể không có một bean `SessionManager` độc lập để Spring quản lý toàn bộ lifecycle. Với manager có scheduler, renewal và teardown phức tạp, nên tạo/configure bean đúng cách hoặc dùng `AbstractVaultConfiguration` để framework quản lý.

Đồng thời, không tự tạo thêm manager/lifecycle instance khi `AbstractVaultConfiguration` đã cung cấp hạ tầng tương ứng. Tránh nhiều scheduler/session cùng cố renew một token theo những trạng thái khác nhau.

## 10. Thực hành xác minh mọi constructor bằng KV v2

Một cách kiểm tra dễ quan sát là dùng **cùng một service đọc secret** và chỉ thay đúng **một** lớp cấu hình (`VaultConfig`, `Vault32Config`, `Vault40Config` hoặc `Vault41Config`) tương ứng với dependency. Mã nghiệp vụ giữ nguyên.

### 10.1. Tạo Vault dev secret

Terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Terminal thứ hai, sau khi đặt `VAULT_ADDR` và `VAULT_TOKEN`:

~~~bash
vault kv put secret/demo/app username=demo_user password=demo_password
vault kv get secret/demo/app
~~~

Ví dụ giả định `secret` là mount KV v2 (Vault dev server thường có mount đó). Kiểm tra bằng `vault secrets list -detailed` nếu cấu hình lab khác đi. Dev root token và HTTP cục bộ **không được dùng cho production**.

### 10.2. Service chỉ phụ thuộc VaultOperations

Tạo `DemoSecretReader.java`:

~~~java
package com.example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class DemoSecretReader {

    private final VaultOperations vault;

    public DemoSecretReader(VaultOperations vault) {
        this.vault = vault;
    }

    public boolean secretHasExpectedFields() {
        VaultResponse response = vault
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("demo/app");

        Map<String, Object> fields =
                response == null ? null : response.getData();

        return fields != null
                && fields.get("username") instanceof String user
                && !user.isBlank()
                && fields.get("password") instanceof String password
                && !password.isBlank();
    }
}
~~~

Inject qua interface `VaultOperations` giúp service ít phụ thuộc vào cách constructor được chọn. `VaultTemplate` triển khai interface này nên Spring vẫn inject được nếu chỉ có một bean phù hợp.

Trong một lớp `@SpringBootApplication`, có thể đặt:

~~~java
@Bean
CommandLineRunner verifyVault(DemoSecretReader reader) {
    return args -> {
        if (!reader.secretHasExpectedFields()) {
            throw new IllegalStateException(
                    "Secret KV v2 không có dữ liệu mong đợi");
        }
        System.out.println("Đọc KV v2 qua VaultTemplate thành công");
    };
}
~~~

Phương thức cần import `org.springframework.boot.CommandLineRunner` và `org.springframework.context.annotation.Bean`. Chỉ in trạng thái, **không in password, username, token hoặc response đầy đủ**.

### 10.3. Vì sao KV v2 phải dùng API phù hợp?

Với mount `secret` và secret path `demo/app`, lời gọi Java là:

~~~java
vault.opsForKeyValue("secret", KeyValueBackend.KV_2)
     .get("demo/app");
~~~

Request HTTP tương ứng:

~~~text
GET /v1/secret/data/demo/app
~~~

`get("demo/app")` nhận **đường dẫn tương đối trong mount**; không truyền `data/demo/app`. Vault policy đọc tối thiểu:

~~~hcl
path "secret/data/demo/app" {
  capabilities = ["read"]
}
~~~

Khi phép đọc trả 403, đừng vội đổi constructor. Hãy xác minh identity thực tế, policy trên path KV v2 và trạng thái token. Nếu trả 404/null, kiểm tra mount/path/version của engine. Nếu timeout/TLS lỗi, kiểm tra endpoint và HTTP client.

## 11. Tùy chỉnh HTTP client và TLS theo phiên bản

Nếu ứng dụng triển khai trong staging/production, constructor đơn giản chỉ phù hợp khi HTTP client mặc định đã đáp ứng yêu cầu. Thực tế thường cần TLS trust store, hostname verification, timeout, proxy, khả năng failover và telemetry.

| Khía cạnh | 3.2.x | 4.0.x | 4.1.x |
| --- | --- | --- | --- |
| Điểm tùy chỉnh HTTP quen thuộc | `ClientHttpRequestFactory`, `RestTemplateBuilder` | `RestClientBuilder`, `ClientHttpRequestFactory` | `VaultClient.builder()`, `ClientHttpRequestFactory`, `configureRestClient(...)` |
| Đưa session vào template | Overload nhận `SessionManager` | Overload nhận `SessionManager` | `VaultTemplate(VaultClient, SessionManager)` |
| Hướng chọn mới | Theo API đang hỗ trợ | Ưu tiên builder của RestClient | Ưu tiên VaultClient; xử lý deprecation ở API cũ |
| Trách nhiệm TLS | JVM/HTTP client | JVM/HTTP client | JVM/HTTP client |

**Không tắt kiểm tra TLS** để làm một ví dụ chạy được. Với HTTPS, certificate chain và hostname của `VAULT_ADDR` phải phù hợp CA/trust store và hệ thống DNS thực tế. Dùng `http://127.0.0.1:8200` chỉ cho lab local đã cách ly.

Cần nhớ rằng `VaultClient` 4.1 có thể nhận một `ClientHttpRequestFactory` tùy chỉnh nhưng **không tự thiết lập trust store doanh nghiệp**. Phải cấu hình factory đúng với HTTP stack. Khi dùng auth theo workload, thành phần thực hiện login có thể cần HTTP client phù hợp; kiểm tra cấu hình cả đường login lẫn đường gọi KV.

## 12. Các lỗi hay gặp khi nâng cấp hoặc chọn constructor

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `Cannot resolve symbol VaultClient` | `spring-vault-core` còn ở 3.2 hoặc 4.0 | Dùng overload sẵn có; chỉ import `VaultClient` khi đã dùng 4.1+ |
| `Cannot resolve symbol RestClientBuilder` | Dự án còn ở nhánh trước 4.0 hoặc import sai package | Dùng `RestTemplateBuilder`/endpoint theo version; kiểm tra Javadoc |
| `No suitable constructor` | Truyền `ClientAuthentication` vào overload cần `SessionManager`, hoặc truyền builder sai loại | Đối chiếu chữ ký chính xác và kiểu tham số |
| Warning `deprecated` sau khi lên 4.1 | Dùng factory/`RestTemplateBuilder` overload cũ | Xem xét migration sang `VaultClient`; kiểm tra behavior trước khi xóa code |
| `NoSuchMethodError` ở runtime | Thư viện compile và runtime bị lệch version | Kiểm tra dependency tree, BOM và artifact thực sự được đóng gói |
| `NoSuchBeanDefinitionException` cho `VaultTemplate` | Configuration không được component scan/import | Đảm bảo bean `@Configuration` được nạp |
| `NoUniqueBeanDefinitionException` | Tạo nhiều bean `VaultTemplate` từ cấu hình thủ công, Spring Cloud Vault hoặc `AbstractVaultConfiguration` | Chọn một cách cấu hình hoặc dùng bean name/qualifier rõ ràng |
| `VaultTemplate(endpoint)` bị 403 | Chỉ có endpoint, không có auth/session, Agent không chèn token | Cấu hình Agent/proxy hoặc dùng constructor có auth phù hợp |
| Khởi động/read bị lỗi 401/403 | Token không hợp lệ, hết TTL hoặc thiếu policy | Kiểm tra identity và policy, không in token |
| HTTP timeout / PKIX | Sai DNS, cổng, TLS/trust hoặc HTTP factory | Kiểm tra từ đúng container/pod và cấu hình TLS |
| Đọc KV v2 rỗng/404 | Sai mount/path hoặc dùng API KV_1 | Dùng `KeyValueBackend.KV_2` và path tương đối đúng |
| Đọc thành công lúc đầu rồi lỗi | Token/session không được renew, hoặc token bị revoke | Dùng workload auth/session manager phù hợp, kiểm tra TTL |
| Vault HA chuyển node, ứng dụng lỗi | Endpoint chọn node tĩnh hoặc HTTP client/failover sai | Dùng endpoint ổn định và đánh giá mạng, retry có giới hạn |

**Một lỗi biên dịch về constructor là vấn đề API/version; lỗi 403 là vấn đề identity/policy; lỗi timeout thường thuộc mạng hoặc HTTP client.** Khoanh vùng đúng tầng giúp tránh sửa lan sang các thành phần không liên quan.

## 13. Kiểm thử tích hợp và giám sát

Đối với `VaultTemplate`, test chỉ mock service là chưa đủ để khẳng định constructor, authentication và HTTP client đã tích hợp đúng. Nên dùng Vault dev/test instance hoặc Testcontainers khi điều kiện dự án cho phép.

Các kiểm tra có giá trị:

1. **Spring Context:** chỉ có một bean `VaultTemplate`/`VaultOperations` được inject theo dự kiến.
2. **Tương thích version:** code 3.2 không phụ thuộc `VaultClient`, code 4.0 dùng được `RestClientBuilder`, code 4.1 tạo được `VaultClient`; compiler không báo sai signature.
3. **Kết nối & auth:** cấu hình đúng endpoint, token/role có quyền và đọc được secret KV v2.
4. **KV v2 sai quyền:** token không có `read` trên `secret/data/demo/app` dẫn tới lỗi quyền có thể quan sát, không giả lập secret.
5. **KV sai path:** trả kết quả thiếu/404 phù hợp; không đánh đồng với token lỗi.
6. **Lỗi TLS/network:** kiểm tra timeout và certificate verification đúng; không bỏ TLS validation.
7. **Token lifecycle:** nếu service chạy lâu, thử TTL ngắn/renewability để đánh giá manager. Không dùng root token dev không hết hạn làm bằng chứng có auto renew.
8. **Migration 4.1:** thay constructor cũ bằng `VaultClient`, xác nhận operation/policy/TLS vẫn hoạt động như trước.
9. **Shutdown:** Spring Context dọn dẹp session manager và HTTP resource theo lifecycle đã thiết kế.
10. **Giám sát:** theo dõi latency, nhóm HTTP status 4xx/5xx, lỗi auth/renew, lỗi TLS mà không lưu credential.

Không log Vault token, database password, Transit key material, private key PKI hoặc secret KV vào metric labels và trace. Nên chỉ ghi trạng thái thao tác, lỗi ở mức đã làm sạch và số liệu độ trễ.

## 14. Câu hỏi tự luyện

1. Tại sao `VaultTemplate(VaultEndpoint)` không tương đương `VaultTemplate(VaultEndpoint, ClientAuthentication)`?
2. Với Spring Vault 3.2, cần truyền thêm gì nếu muốn kiểm soát HTTP factory và session manager?
3. `RestClientBuilder` xuất hiện từ nhánh nào, còn `VaultClient` xuất hiện từ nhánh nào?
4. Những constructor nào bị đánh dấu deprecated ở 4.1 và hướng thay thế là gì?
5. Khi dùng `new VaultTemplate(vaultClient, sessionManager)`, ai chịu trách nhiệm quản lý vòng đời token?
6. Nếu service đã kế thừa `AbstractVaultConfiguration`, vì sao thường không cần khai báo thêm `@Bean VaultTemplate`?
7. Cùng một service KV v2, muốn chuyển cấu hình từ 3.2 sang 4.1 thì cần thay gì và có cần viết lại `opsForKeyValue(...)` không?
8. Nếu IDE báo không tồn tại `VaultClient`, bước kiểm tra nào cần làm trước khi sửa code?
9. Dùng root token đọc thành công một lần có chứng minh session renew/lease hoạt động không?
10. Vì sao một request bị 403 không tự chứng minh constructor đã chọn sai?

**Kết quả mong đợi:** bạn phân biệt được constructor tương thích với **Spring Vault 3.2, 4.0 và 4.1**, tạo được `VaultTemplate` với endpoint và authentication, biết khi nào cấp `SessionManager`/HTTP factory hoặc chuyển sang `VaultClient`, đồng thời giữ API `VaultOperations` ổn định cho logic KV, Transit và PKI. Đây là nền tảng để tiếp tục xác thực workload, phân quyền, quản lý token/lease, xử lý lỗi, giám sát và kiểm thử tích hợp trong SPRING_VAULT.

### Tài liệu tham khảo chính thức

- [Spring Vault 3.2: Introduction to VaultTemplate](https://docs.spring.io/spring-vault/reference/3.2/vault/imperative-template.html)
- [Spring Vault 3.2: Javadoc VaultTemplate](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/core/VaultTemplate.html)
- [Spring Vault 4.0: Javadoc VaultTemplate](https://docs.spring.io/spring-vault/reference/4.0/api/java/org/springframework/vault/core/VaultTemplate.html)
- [Spring Vault 4.1: Javadoc VaultTemplate](https://docs.spring.io/spring-vault/reference/4.1/api/java/org/springframework/vault/core/VaultTemplate.html)
- [Spring Vault 4.1: Javadoc VaultClient](https://docs.spring.io/spring-vault/reference/4.1/api/java/org/springframework/vault/client/VaultClient.html)
- [Spring Blog: Evolving Spring Vault — Introducing VaultClient](https://spring.io/blog/2025/12/26/evolving-spring-vault/)

