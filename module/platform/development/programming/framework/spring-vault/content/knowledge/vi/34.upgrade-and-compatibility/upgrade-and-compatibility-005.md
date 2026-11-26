# Đối chiếu constructor và phương thức đã deprecated

## 1. Vì sao nâng cấp Spring Vault không chỉ là sửa phiên bản dependency?

Một dịch vụ Java dùng **Spring Vault** có thể đang khởi tạo `VaultTemplate`, cấu hình `ClientAuthentication`, `SessionManager` và HTTP client theo ví dụ viết từ nhiều năm trước. Sau khi đổi phiên bản `spring-vault-core`, code có thể xuất hiện cảnh báo `[deprecation]`, không còn compile, hoặc vẫn compile nhưng gửi request Vault với header, namespace, TLS hay token khác trước.

Trong module **SPRING_VAULT**, những thay đổi đó tác động trực tiếp đến workload authentication, chính sách phân quyền, KV secrets, vòng đời token/lease, Transit encryption, PKI và xử lý lỗi. Vì vậy cần phân tích **chính xác từng chữ ký constructor/method đã deprecated** và kiểm thử hành vi thay vì tìm–thay tên API hàng loạt.

Bài này sử dụng tài liệu Spring Vault **3.2.x và 4.1.x** để làm ví dụ đối chiếu. Tại bản tài liệu 4.1.2, nhiều API nhận `RestOperations` hoặc `RestTemplateBuilder` được đánh dấu deprecated từ **4.1**, trong khi `VaultClient` là abstraction mới từ 4.1. Với một dự án đang dùng bản khác, Javadoc của **đúng jar runtime/compile** mới là nguồn quyết định API có tồn tại hay không.

Sau bài học, bạn có thể:

- Phân biệt `@Deprecated`, API đã bị xóa, API mới xuất hiện và thay đổi hành vi không có deprecation.
- Dựng bảng đối chiếu constructor cũ/mới và kiểm tra version tối thiểu của API thay thế.
- Migrate `VaultTemplate`, auth method, token session và cách cấu hình namespace/HTTP client có kiểm soát.
- Nhận diện những method *không* deprecated để tránh sửa code vô ích.
- Chạy compile với deprecation warnings và integration test cho đúng workload identity trước khi rollout.

**Nguyên tắc:** Chỉ đánh dấu “đã migrate” khi **source code dùng API được hỗ trợ, cấu hình kết nối/xác thực giữ đúng chính sách và các luồng nghiệp vụ vượt qua kiểm thử**. “Build xanh” là điều kiện cần nhưng chưa đủ.

## 2. Những khái niệm phải phân biệt trước khi sửa code

| Khái niệm | Nghĩa thực tế | Hành động |
| --- | --- | --- |
| `@Deprecated` trên constructor/method | API vẫn có thể compile nhưng không còn được khuyến nghị, có khả năng bị bỏ về sau. | Đọc Javadoc `since`, `forRemoval`, replacement và lên kế hoạch thay. |
| API đã bị xóa | Java compiler không tìm thấy lớp/method/constructor nữa. | So version cũ–mới và migration guide; dùng API thay thế đã có thật. |
| API mới nhưng chưa có trong jar hiện tại | Bạn copy ví dụ của bản 4.1 vào ứng dụng dùng 3.x/4.0. | Không áp dụng cho tới khi nâng dependency/compatibility platform. |
| API không deprecated | Vẫn là lựa chọn hợp lệ trong version tương ứng. | Không tự ý thay chỉ vì constructor khác mới hơn. |
| Thay hành vi không được đánh dấu deprecated | Mapping JSON, exception type, token session, namespace hoặc transport khác. | Viết contract/integration test; không chỉ nhìn warning. |
| Deprecated phía Spring Framework/Boot | Không nhất thiết là deprecated của Spring Vault. | Kiểm package và phiên bản chính xác, xem BOM/release train. |

**Không dự đoán ngày xóa API** chỉ từ một cảnh báo. Đọc annotation và Javadoc ở release đang dùng; có API deprecated qua nhiều phiên bản, cũng có API bị xóa sau một major/minor. Đừng dùng `@SuppressWarnings("deprecation")` đại trà để qua build mà không ghi nhận nợ kỹ thuật.

### 2.1. Phạm vi version trong ví dụ

Các cột “Spring Vault 3.2.x” và “4.1.x” chỉ nhằm đối chiếu **API Java**, không phải phiên bản HashiCorp Vault server. Spring Vault client, Spring Framework/Boot, Spring Cloud Vault, JDK, Jackson và Vault server là **các thành phần khác nhau**.

- Một class Java có constructor mới không làm Vault server tự có engine/mount mới.
- Một server mới không bổ sung method Java vào jar client đã đóng gói.
- Spring Cloud Vault starter có thể quản lý phiên bản `spring-vault-core` qua BOM; đừng chọn hai phiên bản lệch nhau tùy ý.
- API deprecated chỉ phát hiện khi code thực sự dùng chữ ký cũ. Một ứng dụng dùng Spring Cloud Vault auto-configuration có thể không tự viết constructor nào; cần kiểm release notes/starter thay vì thêm code cấu hình không cần thiết.

## 3. Bước đầu tiên: xác định dependency nào đang được build và chạy

Trong Maven:

~~~bash
# Xem spring-vault-core thực tế được resolve trong dependency graph.
mvn dependency:tree \
  -Dincludes=org.springframework.vault:spring-vault-core

# Khi cần kiểm tra Spring Cloud Vault hoặc Spring Framework liên quan:
mvn dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-vault-core
~~~

Trong Gradle:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-vault-core \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-cloud-vault-core \
  --configuration runtimeClasspath
~~~

Các lệnh này dành cho dự án người học; chúng **không được thực thi trong phạm vi viết bài**. Lưu version của cả `compileClasspath` và `runtimeClasspath` khi có khác biệt. Kiểm BOM, dependency constraints và những bản jar được đóng gói thật vào image/artifact, không chỉ nhìn số version ở dòng khai báo.

Ví dụ báo cáo đầu vào migration:

~~~text
build_system             = Maven / Gradle
jdk_version              = <runtime JDK>
spring_framework_version = <resolved version>
spring_boot_version      = <nếu dùng>
spring_cloud_vault       = <nếu dùng>
spring_vault_core        = <resolved version>
vault_server_version     = <từ cluster staging>
vault_edition_namespace  = <nếu áp dụng>
client_authentication    = <Kubernetes / AppRole / JWT / token>
http_transport           = <JDK / Apache / Jetty / Reactor Netty>
critical_features        = <KV v2, lease renewal, Transit, PKI, ...>
~~~

Chỉ sau khi có inventory mới chọn Javadoc phiên bản nguồn và đích để xem những chữ ký nào thay đổi.

### 3.1. Bật deprecation warning khi biên dịch

Javac hỗ trợ `-Xlint:deprecation` để đưa cảnh báo vào output khi code gọi API deprecated.

Maven Compiler Plugin (trong dự án Maven thích hợp):

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <compilerArgs>
      <arg>-Xlint:deprecation</arg>
    </compilerArgs>
  </configuration>
</plugin>
~~~

Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Xlint:deprecation']
}
~~~

`-Werror` có thể biến warning thành lỗi, nhưng nếu bật ngay trên dự án cũ nhiều cảnh báo thì sẽ chặn build ngoài ý muốn. Giai đoạn đầu nên **thu inventory warning**, phân loại, thay các API cần thiết rồi mới đặt chính sách fail build cho những deprecation mới.

Cảnh báo có thể đến từ code ứng dụng hoặc thư viện bên thứ ba. Không chỉnh trực tiếp mã của dependency; xử lý qua version nâng cấp hoặc issue upstream. `javac` cũng có thể báo API đã được xóa, lỗi binary linkage hoặc framework behavior khác không nằm trong danh sách deprecated.

## 4. Nguồn đối chiếu chính xác: JavaDoc của phiên bản đang dùng

Quy trình cho một constructor/method:

1. Ghi **fully-qualified class name** và **đầy đủ chữ ký** (số và kiểu tham số), không chỉ tên method.
2. Tìm trong `deprecated-list.html` của version nguồn. Đọc annotation `@Deprecated(since=...)` và mô tả thay thế.
3. Mở JavaDoc của **class trong version đích**; xác nhận constructor/method thay thế có tồn tại và `Since`.
4. So sánh **ngữ nghĩa**: ai tạo token, ai đặt header `X-Vault-Token`, default namespace, TLS, timeout, exception và lifecycle.
5. Tìm các caller/bean/test phụ thuộc; migrate theo một đường chung để tránh trộn auth cũ/mới.
6. Chạy compile và test trên **Vault test/staging có mount và policy giống thực tế**.
7. Ghi kết quả, rủi ro, rollback; không kết luận chỉ từ IDE hết gạch ngang.

Ví dụ cùng tên `VaultTemplate` có nhiều constructor. Trong Spring Vault 4.1, `VaultTemplate(VaultEndpoint, ClientAuthentication)` vẫn được JavaDoc liệt kê **không deprecated**, trong khi `VaultTemplate(VaultEndpoint, ClientHttpRequestFactory, SessionManager)` **deprecated từ 4.1**. Chúng khác nhau ở loại tham số; không được gán nhãn cả class `VaultTemplate` là deprecated.

### 4.1. Phân biệt một bảng “API replacement” với bộ quy tắc thay thế máy móc

Một bảng migration cung cấp **điểm bắt đầu**, không đủ để chạy script thay tên. Ví dụ chuyển từ `RestOperations` sang `VaultClient` có thể thay cách inject token/namespace và cách dịch lỗi; nếu code từng tùy biến `RestTemplate` bằng interceptor, cần chuyển tùy biến đó sang lớp thích hợp, không bê nguyên interceptor sang callback khác.

## 5. Bảng deprecated quan trọng ở Spring Vault 4.1

Theo JavaDoc Spring Vault **4.1.x**, các chữ ký tiêu biểu:

| API cũ | Trạng thái từ 4.1 | Hướng thay thế/điểm kiểm tra |
| --- | --- | --- |
| `VaultTemplate(VaultEndpoint, ClientHttpRequestFactory)` | Deprecated | Dùng `VaultClient` đã cấu hình endpoint/request factory rồi khởi tạo `VaultTemplate`. |
| `VaultTemplate(VaultEndpoint, ClientHttpRequestFactory, SessionManager)` | Deprecated | `VaultTemplate(VaultClient, SessionManager)`. |
| `VaultTemplate(VaultEndpointProvider, ClientHttpRequestFactory[, SessionManager])` | Deprecated | `VaultClient.Builder.endpoint(...)`, `requestFactory(...)` và constructor VaultTemplate tương ứng. |
| `VaultTemplate(RestTemplateBuilder[, SessionManager])` | Deprecated | Ưu tiên `VaultClient`; `RestClientBuilder` vẫn là lựa chọn trung gian cho `VaultTemplate`. |
| `AppRoleAuthentication(AppRoleAuthenticationOptions, RestOperations)` | Deprecated | `AppRoleAuthentication(options, VaultClient)`. |
| `KubernetesAuthentication(KubernetesAuthenticationOptions, RestOperations)` | Deprecated | `KubernetesAuthentication(options, VaultClient)`. |
| `JwtAuthentication(JwtAuthenticationOptions, RestOperations)` | Deprecated | `JwtAuthentication(options, VaultClient)`. |
| `AwsIamAuthentication(AwsIamAuthenticationOptions, RestOperations)` | Deprecated | `AwsIamAuthentication(options, VaultClient)`. |
| `ClientCertificateAuthentication(ClientCertificateAuthenticationOptions, RestOperations)` | Deprecated | `ClientCertificateAuthentication(options, VaultClient)`. |
| `CubbyholeAuthentication(CubbyholeAuthenticationOptions, RestOperations)` | Deprecated | `CubbyholeAuthentication(options, VaultClient)`. |
| `LifecycleAwareSessionManager(ClientAuthentication, TaskScheduler, RestOperations)` | Deprecated | `LifecycleAwareSessionManager(auth, scheduler, VaultClient)`. |
| `LifecycleAwareSessionManager(..., RestOperations, RefreshTrigger)` | Deprecated | `LifecycleAwareSessionManager(..., VaultClient, RefreshTrigger)`. |
| `VaultClients.createRestTemplate()` | Deprecated | Tạo `VaultClient` theo endpoint, dùng fluent API hoặc `VaultTemplate` tùy nhu cầu. |
| `VaultClients.createNamespaceInterceptor(String)` | Deprecated | `VaultClient.Builder.defaultNamespace(String)` hoặc per-request `namespace(String)`. |
| `RestTemplateBuilder`, `RestTemplateCustomizer` trong package `org.springframework.vault.client` | Deprecated | `VaultClientCustomizer` hoặc `RestClientCustomizer` theo lớp cấu hình cần tác động. |
| `AbstractVaultConfiguration.restOperations()` và `getRestTemplateFactory()` | Deprecated | Chuyển sang `VaultClient`/cơ chế customization mới. |
| `VaultTemplate.doCreateRestTemplate(...)`, `doCreateSessionTemplate(...)` | Deprecated | Chuyển customization từ subclass sang VaultClient/HTTP client cấu hình tường minh. |

Bảng chỉ chọn những API có ảnh hưởng lớn tới dự án Spring Vault; xem danh sách chính thức cho tất cả provider như Azure MSI, AWS EC2, GCP, GitHub, Username/Password, LoginTokenAdapter và AuthenticationStepsExecutor. Không phải mọi overload cùng tên đều deprecated; phải mở chính xác JavaDoc của version đích.

**Cần lưu ý:** Một `RestClientBuilder` của **Spring Vault** (được giới thiệu từ 4.0) khác với `RestTemplateBuilder` cũ của Spring Vault. Một `RestTemplateBuilder` thuộc Spring Boot hoặc package khác cũng không tự động mang trạng thái deprecated giống tên trùng.

## 6. Ví dụ 1: migrate constructor VaultTemplate sang VaultClient

Giả sử trước nâng cấp, nhóm tự quản lý HTTP request factory để cấu hình TLS/timeout và tự tạo `SessionManager`.

**Trước (API được đánh dấu deprecated ở 4.1):**

~~~java
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

// endpoint, requestFactory và sessionManager do cấu hình cung cấp.
VaultTemplate template = new VaultTemplate(
        endpoint, requestFactory, sessionManager);
~~~

**Sau (Spring Vault 4.1+):**

~~~java
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

VaultClient client = VaultClient.builder()
        .endpoint(endpoint)
        .requestFactory(requestFactory)
        .build();

VaultTemplate template = new VaultTemplate(client, sessionManager);
~~~

`VaultClient.Builder` có các phương thức `endpoint(VaultEndpoint)`, `endpoint(VaultEndpointProvider)`, `requestFactory(ClientHttpRequestFactory)` và `build()`. Constructor `VaultTemplate(VaultClient, SessionManager)` xuất hiện từ 4.1.

**Không bỏ qua bảo mật khi migrate:**

- Giữ nguyên cấu hình **TLS truststore/keystore**, timeout, proxy, connection pool và `ClientHttpRequestFactory` đã được kiểm chứng; client mặc định có thể chọn HTTP transport khác tùy classpath.
- Giữ `SessionManager` quản lý token/renewal và identity workload theo kiến trúc cũ; đừng thay bằng root/static token chỉ để test migration.
- Giữ endpoint scheme/host/port/namespace đúng; kiểm tra header token và namespace trên request thực tế mà không ghi credential ra log.
- Kiểm tra `VaultTemplate` chỉ được khởi tạo một lần theo lifecycle bean mong muốn, tránh hai session manager cùng làm mới token một cách không chủ đích.
- Khi đổi cách khởi tạo, test lỗi 403, 404, timeout và failover; một API khác có thể map exception khác ở lớp HTTP bên dưới.

### 6.1. Những VaultTemplate constructor vẫn hợp lệ

Ở JavaDoc 4.1, có cả:

~~~java
// Vẫn không được đánh dấu deprecated tại 4.1.x:
VaultTemplate withAuthentication =
        new VaultTemplate(endpoint, clientAuthentication);

// Dùng khi truy cập qua một Vault Agent đã gánh authentication;
// không tự gắn X-Vault-Token bởi constructor này:
VaultTemplate agentStyle = new VaultTemplate(endpoint);
~~~

Chọn constructor theo **kiến trúc xác thực thật**. Constructor chỉ nhận `VaultEndpoint` được tài liệu mô tả cho luồng không cấu hình ClientAuthentication trong client, thường dùng Vault Agent; không tự cho rằng nó tương đương constructor có `SessionManager`. Nếu cần TLS/mTLS tùy biến, cân nhắc `VaultClient` builder để bảo đảm request factory đúng.

**Đừng migrate một API không deprecated chỉ vì tên class xuất hiện trong deprecation list ở overload khác.**

## 7. Ví dụ 2: migrate AppRoleAuthentication và KubernetesAuthentication

Một số dự án khởi tạo auth method bằng `RestOperations`/`RestTemplate`. Spring Vault 4.1 đánh dấu những constructor đó deprecated để khuyến nghị `VaultClient`.

**Trước (mẫu chữ ký cũ):**

~~~java
import org.springframework.web.client.RestOperations;
import org.springframework.vault.authentication.AppRoleAuthentication;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;

// authOptions và restOperations được cấu hình sẵn.
AppRoleAuthentication authentication =
        new AppRoleAuthentication(authOptions, restOperations);
~~~

**Sau (4.1+):**

~~~java
import org.springframework.vault.authentication.AppRoleAuthentication;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.client.VaultClient;

VaultClient client = VaultClient.builder()
        .endpoint(endpoint)
        .requestFactory(requestFactory)
        .build();

AppRoleAuthentication authentication =
        new AppRoleAuthentication(authOptions, client);
~~~

Chữ ký thay thế tồn tại trong Javadoc từ 4.1. `authOptions` phải vẫn chỉ đúng AppRole mount/role và cách lấy RoleID/SecretID; bản thân việc đổi constructor không làm thay đổi SecretID TTL, num-uses, bound CIDRs hoặc ACL. Không hard-code `secret_id` vào source code hoặc log.

Với Kubernetes auth, thay đổi tương tự:

~~~java
import org.springframework.vault.authentication.KubernetesAuthentication;
import org.springframework.vault.authentication.KubernetesAuthenticationOptions;
import org.springframework.vault.client.VaultClient;

// k8sOptions chứa Vault auth role và ServiceAccount JWT supplier.
KubernetesAuthentication authentication =
        new KubernetesAuthentication(k8sOptions, client);
~~~

**Mục tiêu sau migration** là auth method vẫn gọi đúng `auth/kubernetes/login` ở đúng mount/namespace và token kết quả có policy/TTL như trước. Một constructor mới compile được không chứng minh service account JWT/audience và Vault role vẫn hợp lệ.

### 7.1. Kết hợp auth mới với SessionManager

Ví dụ Spring Vault 4.1+ với bean scheduler đã được quản lý:

~~~java
import org.springframework.scheduling.TaskScheduler;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.LifecycleAwareSessionManager;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

// client và authentication đã được tạo với cùng Vault endpoint/namespace.
SessionManager sessions =
        new LifecycleAwareSessionManager(
                authentication, taskScheduler, client);

VaultOperations vaultOperations =
        new VaultTemplate(client, sessions);
~~~

`LifecycleAwareSessionManager(ClientAuthentication, TaskScheduler, VaultClient)` thay thế overload nhận `RestOperations` từ 4.1. Session manager vẫn phải chịu trách nhiệm renew/re-login phù hợp; không tự cache `login()` thành token bất biến rồi bỏ renewal.

Khi ứng dụng dùng Spring Cloud Vault auto-configuration, ưu tiên dùng session/clients đã được framework cấu hình sẵn thay vì tự tạo một session manager khác không cần thiết. Những ví dụ thủ công ở đây dùng cho trường hợp dự án đã có JavaConfig tự quản lý.

### 7.2. Soát các auth provider khác

| Auth class có constructor RestOperations deprecated từ 4.1 | Điểm cần giữ khi đổi sang VaultClient |
| --- | --- |
| `JwtAuthentication` | Issuer/audience, auth role, JWT supplier và expiration. |
| `AwsIamAuthentication` | IAM role/signing region, STS request và clock skew. |
| `AwsEc2Authentication` | Identity document, PKCS7/signature, metadata transport. |
| `AzureMsiAuthentication` | MSI token retrieval và instance metadata. |
| `GcpComputeAuthentication` / `GcpIamCredentialsAuthentication` | Credential source và Google token/signature. |
| `ClientCertificateAuthentication` | Client private key, TLS truststore, mTLS identity. |
| `CubbyholeAuthentication` | Wrapping token single-use, creation_path và bootstrap flow. |
| `UsernamePasswordAuthentication` | Role/userpass mount, credential provider. |

Một số provider cần **cả VaultClient và RestClient** ở constructor mới để nói chuyện với metadata service hoặc cloud API khác Vault. Ví dụ theo JavaDoc: `AwsEc2Authentication(options, VaultClient, RestClient)` và `AzureMsiAuthentication(options, VaultClient, RestClient)`. Đừng chuyển một `RestOperations` đơn giản thành cùng một `VaultClient` cho cả Vault và cloud metadata endpoint; đây là hai kênh/trust boundary khác nhau.

## 8. Ví dụ 3: migrate cách đặt namespace

Một dự án Vault Enterprise trước đây có thể thêm interceptor:

~~~java
// Cách cũ, method deprecated từ 4.1.
// Chỉ minh họa mục tiêu migration, không dùng cho code mới:
var namespaceInterceptor =
        VaultClients.createNamespaceInterceptor("team-a");
~~~

Thay bằng lựa chọn tại client:

~~~java
import org.springframework.vault.client.VaultClient;

// Default namespace áp dụng nếu request không tự chỉ định namespace.
VaultClient client = VaultClient.builder()
        .endpoint(endpoint)
        .defaultNamespace("team-a")
        .build();
~~~

Hoặc chọn namespace ở request với fluent API:

~~~java
VaultResponse response = client.get()
        .path("secret/data/orders/config")
        .namespace("team-a")
        .token(vaultToken)
        .retrieve()
        .requiredBody();
~~~

Ví dụ `VaultClient.RequestHeadersSpec.namespace(String)` chỉ minh họa một request; sử dụng VaultToken từ workload authentication đúng quyền và không in ra log. Với Community Vault không dùng Enterprise namespace, không tự đưa `X-Vault-Namespace` không tồn tại để tránh gây lỗi.

**Không tự ý thêm namespace vào path** như `team-a/secret/data/orders/config` nếu kiến trúc Vault yêu cầu header namespace; cần giữ ranh giới của server namespace. Test ít nhất hai môi trường/namespace được phép và một negative case từ identity sai để bảo đảm không đọc nhầm secret.

Một interceptor cũ có thể còn làm nhiều việc (tracing, token headers, retries). Chỉ chuyển **logic namespace** sang `defaultNamespace`; các chức năng còn lại cần được đối chiếu riêng để không làm mất timeout, TLS hoặc kiểm soát redirect.

## 9. Ví dụ 4: RestTemplateBuilder và RestTemplateCustomizer

Spring Vault 4.1 deprecated các loại **thuộc package `org.springframework.vault.client`**:

- `RestTemplateBuilder`,
- `RestTemplateCustomizer`,
- `RestTemplateRequestCustomizer`,
- `RestTemplateFactory`.

Thay thế cần chọn theo mục tiêu cấu hình:

| Cần tùy biến gì? | API khuyến nghị ở 4.1 |
| --- | --- |
| Endpoint, namespace, default headers, request factory | `VaultClient.Builder`. |
| Cấu hình dùng chung cho VaultClient của Spring Vault configuration | `VaultClientCustomizer`. |
| Tùy biến mức thấp `RestClient.Builder` (interceptor, converter khi được phép) | `RestClientCustomizer` hoặc `VaultClient.Builder.configureRestClient(...)`. |
| Request initializer cho RestClientBuilder | `RestClientBuilder.requestInitializers(ClientHttpRequestInitializer...)`. |
| Tự tạo HTTP RestClient khác Vault | Cấu hình theo API Spring Framework RestClient, không bắt buộc dùng VaultClient. |

Ví dụ `VaultClientCustomizer` dùng trong Spring context có cấu hình Spring Vault tương ứng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.client.VaultClientCustomizer;

@Configuration(proxyBeanMethods = false)
class VaultClientCustomizations {

    @Bean
    VaultClientCustomizer vaultNamespaceCustomizer() {
        return builder -> builder.defaultNamespace("team-a");
    }
}
~~~

JavaDoc cho biết những bean `VaultClientCustomizer` được áp dụng cho `VaultClient` builder do `AbstractVaultConfiguration` tạo. **Nếu ứng dụng tự gọi `VaultClient.builder()` để tạo client độc lập, bean này không tự động can thiệp vào instance đó**; hãy áp dụng configuration tường minh hoặc qua một factory chung.

Khi tùy biến HTTP client, **không ghi `X-Vault-Token` rõ vào default header config hoặc log request**, vì token runtime phải do auth/session cung cấp. Kết nối Vault cần xác minh CA/hostname; không dùng `trustAll` chỉ để khắc phục lỗi migrate.

### 9.1. Đừng tưởng toàn bộ RestTemplate đã bị xóa

Deprecated trên `VaultClients.createRestTemplate()` hoặc `RestTemplateBuilder` trong Spring Vault **không có nghĩa mọi API của Spring Framework RestTemplate đều ngay lập tức bị xóa**. Tương tự, `RestClientBuilder` ở package Spring Vault vẫn tồn tại. Tài liệu 4.1 khuyến nghị `VaultClient` như lớp truy cập Vault đồng bộ; `RestClient` mức thấp vẫn phù hợp cho thư viện cần điều khiển HTTP thủ công.

Đọc đúng package/import và chữ ký cụ thể trước khi mở pull request migration.

## 10. Ví dụ 5: method tạo HTTP client và error mapping

**Trước (4.1 deprecated):**

~~~java
// Hàm static này deprecated; không tạo session manager.
RestTemplate oldHttp = VaultClients.createRestTemplate();
~~~

**Sau (4.1+):**

~~~java
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.authentication.VaultToken;
import org.springframework.vault.support.VaultResponse;

VaultClient client = VaultClient.create(endpoint);

VaultResponse raw = client.get()
        .path("secret/data/orders/config")
        .token(vaultToken)
        .retrieve()
        .requiredBody();
~~~

`VaultClient` là fluent HTTP client **không phải** `VaultTemplate`. Một request tự dùng `VaultClient` cần cung cấp token/context phù hợp, còn `VaultTemplate` với `SessionManager` cung cấp lớp thao tác cao hơn và tích hợp session. Với nhiều CRUD KV, Transit, PKI hoặc lease operations, giữ `VaultOperations` có thể phù hợp hơn việc viết lại mọi path HTTP.

Khi migrate, không quên các khác biệt:

- `RestClient`/`RestOperations` có các exception Spring Web, trong khi `VaultClient` có thể chuyển `4xx/5xx` sang `VaultClientResponseException`; `VaultTemplate` tiếp tục cung cấp exception translation ở lớp abstraction.
- JSON response KV v2 thường có trường `data.data`, nên nếu dùng `VaultClient` thô phải đọc đúng wrapper hoặc chọn `opsForKeyValue("secret", KV_2)`.
- Method `GET database/creds/role` **tạo dynamic credential**, không dùng như health probe chỉ vì API mới gọi dễ hơn.
- Không dùng path do người dùng nhập trực tiếp để tạo URI tới host khác; `VaultTemplate`/`VaultClient` cần giữ endpoint scoping và sanitize input để tránh path traversal hoặc SSRF.
- Cấu hình retry phải chú ý request tạo resource (issue certificate, wrap token, dynamic secret): timeout không chứng minh server chưa xử lý request.

Nếu code cũ override `VaultTemplate.doCreateRestTemplate(...)`, `doCreateRestClient(...)` hoặc `doCreateSessionTemplate(...)` để thêm interceptor/session token, đừng giữ nguyên subclass hook như trước: JavaDoc 4.1 đánh dấu chúng deprecated vì session authentication được xử lý qua `VaultClient`, không còn dựa trên request interceptor đó. Chuyển logic sang `VaultClient` builder/HTTP client customization và viết test xác minh token được gửi đúng sau renew/re-login.

## 11. Deprecated ở các version cũ: ví dụ Transit sign/verify

Không phải mọi deprecation bắt đầu từ 4.1. Trong Spring Vault **3.2.x**, JavaDoc đánh dấu từ **2.4** một số method sau:

| API cũ ở 3.2.x | Thay thế ghi trong JavaDoc | Ý nghĩa cần kiểm tra |
| --- | --- | --- |
| `VaultSignRequest.getAlgorithm()` | `getSignatureAlgorithm()` | Thuật toán chữ ký RSA, không phải mặc định thuật toán băm. |
| `VaultSignRequestBuilder.algorithm(String)` | `signatureAlgorithm(String)` | Phân biệt lựa chọn RSA signature với hash. |
| `VaultSignatureVerificationRequest.getAlgorithm()` | `getSignatureAlgorithm()` | Tránh nhầm verify signature với digest. |
| `VaultSignatureVerificationRequestBuilder.algorithm(String)` | `signatureAlgorithm(String)` | Cần kiểm đúng ý nghĩa giá trị tham số. |
| `Policy.BuiltinCapabilities.WRITE` | Dùng capability Vault hiện hành như `create`/`update` theo endpoint. | Không tương đương một-một; ACL cần xem HTTP method và path. |

**Cạm bẫy quan trọng:** JavaDoc cũ của `algorithm(String)` có thể mô tả giá trị dạng `sha2-256`, trong khi `signatureAlgorithm(String)` của RSA chấp nhận `pss` hoặc `pkcs1v15`; `hashAlgorithm(String)` mới là nơi chỉ định `sha2-256`. Vì vậy không được thay tên method rồi giữ nguyên đối số mà không đọc contract.

Ví dụ **code đích** trên Spring Vault có builder hiện đại:

~~~java
import org.springframework.vault.support.Plaintext;
import org.springframework.vault.support.VaultSignRequest;

// inputBytes là payload do ứng dụng kiểm soát, không phải secret loggable.
VaultSignRequest request = VaultSignRequest.builder()
        .plaintext(Plaintext.of(inputBytes))
        .hashAlgorithm("sha2-256")
        .signatureAlgorithm("pss")
        .build();
~~~

Giá trị `pss` chỉ có nghĩa với loại RSA key phù hợp; nếu key type hoặc yêu cầu xác minh của backend khác, chọn tham số theo Vault Transit API và policy đang dùng. Không chỉ test code compile: cần thử sign và verify bằng **cùng key/algorithm/context** và xác nhận signature đúng.

Tương tự, Spring Vault 3.2 ghi các class `AppIdAuthentication`/`AppIdAuthenticationOptions` deprecated với khuyến nghị chuyển sang `AppRoleAuthentication`; đây là **đổi auth method**, không phải rename class 1–1. Cần provision AppRole role, RoleID/SecretID, policy, TTL và test bootstrap lại trước khi đổi code.

Các API bị xóa khỏi một JavaDoc phiên bản mới không còn xuất hiện trong mục Deprecated List của bản đó. Vì vậy khi một method biến mất, hãy đọc **JavaDoc phiên bản cũ** để biết lịch sử thay vì chỉ tìm trong danh sách deprecated mới nhất.

## 12. Kỹ thuật rà soát source theo khu vực rủi ro

Ưu tiên rà theo nhóm dưới đây, không sửa bừa tất cả cùng lúc.

| Khu vực | Dấu hiệu cần tìm | Rủi ro sau migration |
| --- | --- | --- |
| Khởi tạo VaultTemplate | `new VaultTemplate(...)`, `doCreateRestTemplate`, `RestTemplateBuilder` | Mất TLS, namespace, token/session customization. |
| Client authentication | `new AppRoleAuthentication(...)`, Kubernetes/JWT/AWS auth, `RestOperations` | Auth login thất bại, role khác, header/signer khác. |
| Session/lease lifecycle | `LifecycleAwareSessionManager(...)`, `SecretLeaseContainer` | Không renew token/lease, sử dụng stale credential. |
| Tenant/namespace | `createNamespaceInterceptor`, `X-Vault-Namespace` | Đọc/ghi nhầm namespace hoặc 403. |
| KV/Transit/PKI | `opsForKeyValue`, `opsForTransit`, `opsForPki` | API path, key version, TTL, encryption/certificate behavior. |
| Error translation | `VaultException`, `RestClientResponseException`, retry handlers | Xử lý 403 như lỗi network, retry thao tác có side effect. |
| HTTP configuration | `ClientHttpRequestFactory`, SSL, timeout, proxy | TLS fail, timeout khác hoặc lộ token qua redirect/log. |
| Reactive vs imperative | `ReactiveVaultTemplate`, `VaultTemplate`, WebClient/RestClient | Chặn event loop, đổi thread context, tạo client không phù hợp. |
| Repositories/mapping | `VaultMappingContext`, repository DSL | Keyspace/mapping/version khác dẫn đến đọc sai secret. |

Dùng chức năng Find Usages của IDE hoặc phân tích source có giới hạn trên namespace dự án. Với những case đặc thù, search fully-qualified class name để phân biệt API từ Spring Vault với class tên gần giống của Spring Boot.

**Không bỏ `@SuppressWarnings("deprecation")` vào toàn package.** Nếu chưa thể migrate ngay vì SDK khác còn dùng API cũ, ghi rõ phạm vi, lý do, deadline và test bảo vệ, rồi bỏ suppression khi đổi dependency.

## 13. Kiểm thử hồi quy theo hành vi, không chỉ biên dịch

Ma trận tối thiểu khi chuyển nhóm API 3.x/4.0 → 4.1.x:

| Luồng | Positive test | Negative/failure test |
| --- | --- | --- |
| Workload auth | Đăng nhập AppRole/Kubernetes/JWT nhận token đúng policy. | RoleID/SecretID/JWT sai hoặc thiếu quyền trả lỗi phân loại đúng. |
| Token lifecycle | SessionManager renew/re-login theo TTL, không dùng token hết hạn. | Mất Vault, token bị revoke, 403 và retries không vô hạn. |
| KV v2 | Đọc `secret/data/orders/config` bằng `opsForKeyValue(... KV_2)`. | Sai mount, wrong KV version hoặc token thiếu `read`. |
| Transit | Encrypt/decrypt đúng key/context và verify signature nếu dùng. | Encrypt-only token không decrypt/sign được; sai signature algorithm bị từ chối. |
| PKI | Issue/sign certificate với role hợp lệ, SAN/TTL/chain đúng. | Role khác, SAN trái quy tắc, token thiếu `update`. |
| Namespace | Default namespace và per-request namespace đúng. | Identity tenant A không thấy tenant B, không rơi về root ngoài ý muốn. |
| TLS/HTTP | CA/hostname verification, request factory và timeout như trước. | Server cert không tin cậy, connection reset, timeout. |
| Error mapping | 400/403/404/429/5xx được phân loại và báo đúng. | Không retry vô hạn các lỗi ACL hoặc request non-idempotent. |
| Dynamic lease | Credential được cấp/renew/rotate, pool nhận generation mới. | Lease hết hạn trong outage thì không dùng cache vô hạn. |
| Response wrapping | Lookup và unwrap một lần, creation_path đúng. | Token đã dùng/hết TTL không được nhận lại plaintext. |

Ví dụ test dùng token workload **không phải root token**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

import static org.junit.jupiter.api.Assertions.*;

class VaultMigrationContractIT {

    private final VaultOperations vault;

    // vault được inject/cấu hình bởi test context dùng workload identity.
    VaultMigrationContractIT(VaultOperations vault) {
        this.vault = vault;
    }

    @Test
    void kvV2StillReadsExpectedData() {
        VaultResponse response = vault.opsForKeyValue(
                "secret", KeyValueBackend.KV_2)
                .get("orders/config");

        assertNotNull(response);
        assertNotNull(response.getData());
        assertEquals("orders", response.getData().get("service"));
    }
}
~~~

Đây là **mẫu kiểm tra contract**; để JUnit inject `VaultOperations` vào constructor phải có cấu hình Spring/JUnit phù hợp (ví dụ `@SpringBootTest` hoặc `@ExtendWith(SpringExtension.class)`, tùy project), và fixture phải tồn tại. Không trình bày đoạn này như một test chạy độc lập chưa có wiring.

**Chốt nguyên tắc kiểm thử ACL:** luôn dùng token có policy workload thật; test chạy bằng root token không phát hiện mất quyền hoặc vô tình cấp dư quyền sau migration. Dữ liệu test là fixture giả, không chạm secret production.

### 13.1. So sánh kết quả trước và sau trên cùng hợp đồng

Đối với mỗi feature, lưu các điều kiện sau (không chứa secret):

~~~text
feature         : kv-orders-config
library_before  : <spring-vault version trước>
library_after   : <spring-vault version sau>
auth_role       : <workload role>
vault_namespace : <nếu có>
vault_mount     : secret/
http_contract   : KV v2 read orders/config
expected        : data.service=orders, missing key => controlled error
old_test        : PASS / FAIL
new_test        : PASS / FAIL
status          : VERIFIED / BLOCKED / UNKNOWN
~~~

Nếu đổi đồng thời Vault server version, role/policy và Spring Vault client, rất khó quy nguyên nhân lỗi. Nên giữ server/engine/policy cố định khi kiểm tra migration Java trước, rồi thử tổ hợp server mới riêng bằng compatibility suite.

## 14. Xử lý các lỗi migration thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `cannot find symbol: VaultClient` | Ứng dụng chưa dùng Spring Vault 4.1+, hoặc dependency bị resolve thấp hơn. | Dependency graph đúng compile/runtime; JavaDoc đúng version. |
| `no suitable constructor for VaultTemplate` | Truyền factory/manager sai overload hoặc dùng ví dụ 4.1 trên jar cũ. | So đầy đủ chữ ký, kiểm import. |
| `@Deprecated` vẫn xuất hiện sau migration | Còn caller hoặc helper cũ, hoặc một constructor khác còn deprecated. | Biên dịch `-Xlint:deprecation`, Find Usages. |
| AppRole/Kubernetes login bị 403 | Auth role/path, namespace, token provider khác sau migrate. | Kiểm actual login path, identity và Vault policy. |
| Token renew thất bại | SessionManager bị bỏ/khởi tạo sai hoặc transport đến Vault lỗi. | Kiểm token TTL, scheduler, exception, network. |
| KV v2 404 | Nhầm mount/version, gọi `data/` sai hoặc namespace không đúng. | Inventory mount KV, đường API thực tế, test fixture. |
| HTTP 403 với root namespace | Namespace interceptor không được thay đúng; default header thiếu/sai. | Kiểm VaultClient defaultNamespace/per-request và token. |
| `PKIX path building failed` | Request factory/TLS truststore mới không tương đương cấu hình cũ. | TLS CA/hostname/mTLS và client factory. |
| Transit sign/verify fail | Nhầm `hashAlgorithm` và `signatureAlgorithm` hoặc key type. | Contract thuật toán, round-trip sign/verify. |
| Error handler không bắt exception | Lớp lỗi của VaultClient khác RestOperations. | Kiểm kiểu exception, status, retry classification. |
| Code build nhưng service không đọc được KV | Server mount, ACL, namespace hoặc auth role sai. | Integration test bằng workload token, không admin token. |

Thay mọi exception thành một lỗi “Vault unavailable” là không an toàn: 403 có thể là policy sai, 400 là validation, 404 là mount/path, 429/5xx là tải/trạng thái. Retry không được biến lỗi quyền thành một chuỗi login/renew vô hạn.

## 15. Quy trình rollout và rollback an toàn

~~~mermaid
flowchart TD
 A["Chụp dependency/constructor baseline"] --> B["Liệt kê deprecation và replacement đúng version"]
 B --> C["Migrate một nhóm API"]
 C --> D["Compile, xử lý warning"]
 D --> E["Integration test Vault test với workload identity"]
 E --> F{"PASS cả security và lifecycle?"}
 F -->|Không| G["Sửa hoặc rollback code/config"]
 F -->|Có| H["Staging với cùng server/mount/policy"]
 H --> I{"Canary và observability PASS?"}
 I -->|Không| G
 I -->|Có| J["Rollout từng nhóm và ghi compatibility manifest"]
~~~

Một quy trình tốt:

1. **Chốt baseline:** dependency runtime, server/mount, policy, danh sách API deprecated và test hiện đang PASS.
2. **Migrate nhóm nhỏ:** ưu tiên client construction và auth/session trước, sau đó namespace/HTTP customization, cuối cùng logic feature-specific.
3. **Compile dưới chính JDK/Boot/Cloud release train dự kiến**, không dùng classpath của IDE khác pipeline.
4. **Chạy integration test có cả positive/negative ACL**, lease/token rotation, KV/Transit/PKI và failure injection.
5. **Canary:** quan sát login failures, Vault 403/5xx, renew errors, latency, TLS errors, secret read failures và cache expiration.
6. **Rollback:** có version artifact cũ, cấu hình endpoint/namespace/token provider cũ và migration path đã được chứng minh; không rollback bằng cách nới ACL hoặc tắt TLS.
7. **Ghi bản đồ tương thích:** API source/target, annotation, replacement, test IDs và thời điểm đã xác minh.

Tránh chạy đồng thời migration constructor, đổi PKI issuer, bật KV v2 và nâng server production trong một lần triển khai. Những thay đổi này cùng lúc tạo quá nhiều biến để điều tra nếu xảy ra lỗi.

## 16. Checklist review pull request

- [ ] Đã xác minh version `spring-vault-core` thực tế ở compile và runtime.
- [ ] Danh sách deprecated được trích từ JavaDoc **đúng version**; không đánh đồng overload.
- [ ] Mỗi constructor cũ có chữ ký đầy đủ, replacement và version `Since` đã kiểm tra.
- [ ] Không sửa các API không deprecated chỉ vì trùng class.
- [ ] Không chuyển `RestOperations` sang `VaultClient` mà bỏ `SessionManager` hoặc workload authentication.
- [ ] TLS CA, hostname verification, timeout, proxy, namespace và request factory vẫn đúng.
- [ ] Không hard-code `X-Vault-Token`, root token, AppRole SecretID hoặc private key.
- [ ] Khi thay `VaultClients.createNamespaceInterceptor`, đã test đúng tenant/namespace.
- [ ] Khi sửa Transit sign/verify, đã phân biệt signature algorithm và hash algorithm.
- [ ] Spring Cloud Vault/Boot/JDK/Jackson dependencies được chọn theo compatibility matrix.
- [ ] Compile warnings được xử lý hoặc ghi nhận có trách nhiệm; không suppression toàn project.
- [ ] Test KV v2, Transit, PKI, token/lease và negative ACL chạy với Vault test.
- [ ] Đã phân loại 400/403/404/429/5xx, không retry các side-effect requests vô hạn.
- [ ] Có canary, metric, rollback và người chịu trách nhiệm phê duyệt.
- [ ] Báo cáo không chứa token, password, lease credential, plaintext/private key.

## 17. Bài tập thực hành

Giả sử một dự án Spring Boot đang dùng Spring Vault 3.2.x, và nhóm dự kiến nâng tới nhánh 4.1.x đã được tổ chức chấp thuận. Dự án có ba phần code:

~~~java
// A. Old VaultTemplate custom transport
VaultTemplate a =
        new VaultTemplate(endpoint, requestFactory, sessions);

// B. Old AppRole authentication
AppRoleAuthentication b =
        new AppRoleAuthentication(options, restOperations);

// C. Transit sign builder from older code
VaultSignRequest c = VaultSignRequest.builder()
        .plaintext(input)
        .algorithm("sha2-256")
        .build();
~~~

Hãy thực hiện:

1. Đối chiếu constructor A/B và method C với JavaDoc 3.2.x và 4.1.x; ghi đầy đủ `since` và replacement.
2. Dùng `VaultClient.builder().endpoint(endpoint).requestFactory(requestFactory).build()` rồi `VaultTemplate(client, sessions)` cho A, giữ mọi cấu hình TLS/timeout/namespace.
3. Dùng `new AppRoleAuthentication(options, client)` cho B, xác nhận role/path và credential delivery không đổi.
4. Với C, **không** thay tên `algorithm` rồi giữ đối số `sha2-256` vào `signatureAlgorithm`. Chọn `hashAlgorithm("sha2-256")` và một signature algorithm phù hợp (chẳng hạn `pss` với RSA) theo Vault Transit key/contract, rồi test sign/verify.
5. Bật compiler deprecation warnings, chạy test bằng token workload và thử cả 403 (thiếu ACL), wrong namespace, token renewal và TLS lỗi.
6. Ghi bảng kết quả `VERIFIED/BLOCKED/UNKNOWN` cùng dependency version và test evidence, không chèn dữ liệu bí mật.

**Điểm cần nhận ra:** A/B là migration **constructor/transport**, còn C là migration **method có nguy cơ thay đổi ngữ nghĩa tham số**. Một công cụ replace tự động không thể xác nhận hai loại migration này tương đương về bảo mật.

## 18. Câu hỏi tự đánh giá

1. Deprecated khác API đã bị xóa như thế nào và vì sao cần JavaDoc của cả version cũ lẫn mới?
2. `VaultTemplate(VaultEndpoint, ClientAuthentication)` có deprecated trong Spring Vault 4.1.x không? Tại sao không được suy từ những overload khác?
3. Vì sao đổi từ `VaultTemplate(endpoint, requestFactory, sessions)` sang `VaultTemplate(client, sessions)` phải kiểm tra TLS, timeout và namespace?
4. `AppRoleAuthentication(options, RestOperations)` được thay bằng constructor nào ở 4.1?
5. `LifecycleAwareSessionManager` quản lý vòng đời gì và điều gì xảy ra nếu bỏ nó khi migrate?
6. `VaultClients.createNamespaceInterceptor` được thay bằng hai API nào?
7. `VaultClientCustomizer` và `RestClientCustomizer` khác nhau ở mức tùy chỉnh nào?
8. Tại sao có `RestTemplateBuilder` deprecated trong Spring Vault không có nghĩa mọi Spring Framework RestTemplate đều biến mất?
9. Khi migrate từ `.algorithm("sha2-256")` của Transit sign, vì sao dùng `signatureAlgorithm("sha2-256")` là đáng nghi?
10. Vì sao compile thành công với `VaultClient` không chứng minh role/ACL và KV mount trên Vault server đúng?
11. Những failure tests nào cần có khi chuyển từ `RestOperations` sang `VaultClient`?
12. Nếu Spring Cloud Vault đã tự cấu hình `VaultTemplate`, có nên tự tạo một client/session manager khác chỉ để “dùng API mới” không?
13. Tại sao không thể kết luận phiên bản server Vault từ version `spring-vault-core` của ứng dụng?
14. Một bản review migration tốt phải ghi lại những bằng chứng gì để rollback an toàn?

## Tài liệu tham khảo

- [Spring Vault 4.1.x — Danh sách Deprecated API chính thức](https://docs.spring.io/spring-vault/reference/api/java/deprecated-list.html)
- [Spring Vault 4.1.x — VaultTemplate constructors và methods](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html)
- [Spring Vault 4.1.x — VaultClient](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.html)
- [Spring Vault 4.1.x — VaultClient.Builder](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClient.Builder.html)
- [Spring Vault — Vault Client Access, so sánh RestClient/VaultClient/VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/vault-client.html)
- [Spring Vault 4.1.x — AppRoleAuthentication constructors](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthentication.html)
- [Spring Vault 4.1.x — KubernetesAuthentication constructors](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/KubernetesAuthentication.html)
- [Spring Vault 4.1.x — LifecycleAwareSessionManager constructors](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/LifecycleAwareSessionManager.html)
- [Spring Vault 4.1.x — AbstractVaultConfiguration](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/config/AbstractVaultConfiguration.html)
- [Spring Vault 4.1.x — VaultClientCustomizer](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClientCustomizer.html)
- [Spring Vault 3.2.x — Deprecated API (đối chiếu các API cũ hơn)](https://docs.spring.io/spring-vault/docs/current/api/deprecated-list.html)
- [Spring Vault 4.1.x — VaultSignRequestBuilder signature/hash algorithms](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultSignRequest.VaultSignRequestBuilder.html)
- [Spring Vault — Dependencies và version compatibility](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html)
- [Spring Vault — Release notes và artifacts](https://github.com/spring-projects/spring-vault/releases)
