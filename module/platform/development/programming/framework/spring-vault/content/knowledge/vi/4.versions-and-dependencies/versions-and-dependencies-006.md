# Phụ thuộc cho Reactor và client không chặn

Trong **SPRING_VAULT**, ứng dụng Java có thể đọc KV secrets, mã hóa bằng Transit, làm việc với PKI và theo dõi token/lease qua `VaultTemplate`. Với dịch vụ xử lý nhiều yêu cầu đồng thời, Spring Vault còn có API **reactive** để gửi request HTTP tới HashiCorp Vault mà không giữ một luồng Java chờ phản hồi mạng. Để dùng đúng mô hình này, không chỉ thêm Reactor vào `pom.xml`; ứng dụng cần Spring WebFlux, JSON codecs, một HTTP connector có khả năng không chặn, và luồng cấp token tương thích.

**Chương:** Phiên bản và phụ thuộc. Bài học này trả lời câu hỏi **“cần thư viện gì để dùng Reactor và client không chặn trong Spring Vault?”** đồng thời chỉ rõ API, cấu hình, xử lý lỗi và kiểm thử tích hợp với Vault server. Sau bài, người học có thể:

- Chọn `spring-vault-core`, `spring-webflux`, Reactor và JSON mapper tương thích.
- Phân biệt `ReactiveVaultTemplate` (API domain) với `ReactiveVaultClient` (HTTP fluent), `WebClient` và transport bên dưới.
- Khởi tạo bean reactive có `ReactiveSessionManager`/`VaultTokenSupplier` và xác thực theo workload.
- Viết luồng `Mono`/`Flux` cho KV và Transit; xử lý kết quả rỗng, timeout, lỗi Vault và backpressure.
- Kiểm tra runtime classpath và thực hiện kiểm thử bằng Reactor Test/Testcontainers mà không lộ secret.

> **Mốc phiên bản: 25/11/2026.** Ví dụ dùng **Spring Vault 4.1.2** trên **Java 17+**, Spring Framework **7.0.11+**. `ReactiveVaultTemplate` đã có trước dòng 4.1; **`ReactiveVaultClient` được bổ sung từ 4.1**. Các API, artifact và phiên bản liên quan được đối chiếu với tài liệu 4.1.2. Nếu dự án ở Spring Framework 6.x, hãy dùng dòng Spring Vault 3.x tương thích và đọc Javadoc tương ứng.

## 1. Reactive và non-blocking có ý nghĩa gì với Vault?

Một lời gọi đồng bộ như `VaultOperations.read(...)` chỉ trả về khi request đã hoàn thành (hoặc lỗi). Ở API reactive, `ReactiveVaultOperations.read(...)` trả `Mono<VaultResponse>`: đây là mô tả công việc sẽ được thực thi khi có subscriber. Trong luồng mạng non-blocking, khi socket đang chờ Vault phản hồi, event loop có thể tiếp tục phục vụ tác vụ khác thay vì giữ một thread chỉ để chờ I/O.

| Khái niệm | Ý nghĩa | Trong Spring Vault |
| --- | --- | --- |
| `Publisher<T>` | Hợp đồng phát tín hiệu dữ liệu/lỗi/hoàn tất | Nền tảng Reactive Streams |
| `Mono<T>` | Phát **0 hoặc 1** kết quả, rồi complete hoặc error | Đọc một secret, mã hóa một payload, login lấy một token |
| `Flux<T>` | Phát **0 đến nhiều** phần tử | Liệt kê key, xử lý batch Transit hoặc nhiều request |
| `WebClient` | HTTP client reactive thuộc Spring WebFlux | Tầng HTTP mà client Vault reactive sử dụng |
| `ReactiveVaultClient` | Fluent API biết về request/response Vault; thêm từ 4.1 | Gọi endpoint Vault chưa có API domain |
| `ReactiveVaultTemplate` / `ReactiveVaultOperations` | API mức cao cho KV, Transit, sys và mapping | Code nghiệp vụ làm việc với Vault |
| `ReactiveSessionManager` | Cấp, tái sử dụng và có thể gia hạn token theo hợp đồng reactive | Không login mới cho mỗi request |

```text
HTTP request của ứng dụng
         │
         ▼
Service trả Mono / Flux
         │
         ▼
ReactiveVaultOperations / ReactiveVaultTemplate
         │  path KV/Transit, mapping VaultResponse
         ▼
ReactiveVaultClient (4.1+)
         │  token, namespace, error mapping
         ▼
Spring WebFlux WebClient + JSON codecs
         │
         ▼
ClientHttpConnector (JDK/Netty/Apache/Jetty)
         │
         ▼
HTTPS ──── Vault Server
           auth role + Vault policy + KV/Transit/PKI
```

**Reactive không làm bản thân Vault Server nhanh hơn**; nó giúp tận dụng tài nguyên trong JVM khi đang chờ I/O. Đọc một secret lúc startup của ứng dụng batch nhỏ chưa chắc cần reactive. Ngược lại, API HTTP phục vụ hàng nghìn request đồng thời và đã dùng WebFlux có thể giữ chuỗi bất đồng bộ liên tục đến Vault. Các tác vụ **blocking** từ thư viện khác (đọc file lớn, JDBC, SDK cloud cũ) vẫn có thể chặn event loop nếu đưa thẳng vào callback `map`/`flatMap`.

## 2. Những dependency thực sự cần

Spring Vault đóng cả lớp reactive vào artifact **`org.springframework.vault:spring-vault-core`**. Không có artifact riêng tên `spring-vault-reactor`, `spring-vault-webclient` hoặc `spring-vault-reactive-core` để phải thêm khi muốn dùng `ReactiveVaultTemplate`. Tuy nhiên Core **không tự đảm bảo** mọi thành phần tùy chọn có mặt ở runtime.

| Mức | Artifact / thành phần | Vì sao |
| --- | --- | --- |
| **Bắt buộc** | `org.springframework.vault:spring-vault-core` | `ReactiveVaultOperations`, `ReactiveVaultTemplate`, `ReactiveVaultClient`, reactive KV/Transit, auth |
| **Bắt buộc cho client reactive** | `org.springframework:spring-webflux` | `WebClient`, `ClientHttpConnector`, codecs, các loại request/response reactive |
| **Cần có qua dependency** | `io.projectreactor:reactor-core` và `org.reactivestreams:reactive-streams` | `Mono`, `Flux`, Reactive Streams; thông thường WebFlux kéo theo |
| **JSON cho 4.x** | `tools.jackson.core:jackson-databind` (Jackson 3) | Đọc/ghi Vault JSON; Jackson **không** được Spring Vault Core mang vào transitively |
| **HTTP transport** | JDK `HttpClient` **hoặc** `io.projectreactor.netty:reactor-netty`, Apache/Jetty tương ứng | Kết nối mạng không chặn; **không bắt buộc có Reactor Netty** nếu chọn JDK connector |
| **Kiểm thử publisher** | `io.projectreactor:reactor-test`, phạm vi test | `StepVerifier`, `TestPublisher`, virtual time |
| **Kiểm thử Vault thật** | `org.testcontainers:testcontainers-vault`, phạm vi test | Tạo Vault test container với mount/policy để kiểm tra tích hợp |
| **Tùy chọn theo ứng dụng** | `spring-boot-starter-webflux` hoặc Spring Cloud Vault starter | WebFlux/Boot auto-configuration hoặc nhập `vault://` vào Environment; trách nhiệm khác Core |

### Tách ba vai trò thường bị nhầm

**Reactor Core** quản lý chuỗi `Mono`/`Flux`, nhưng **không tự tạo HTTP client**. **Spring WebFlux** cung cấp `WebClient`, codecs và connector API; nó **không bắt buộc phải chạy web server** nếu chỉ làm client. **Reactor Netty** là một lựa chọn triển khai transport HTTP, không phải điều kiện bắt buộc của Reactive Streams. Nếu chỉ thêm `reactor-core` mà thiếu `spring-webflux`, bạn vẫn không có đủ class cho cơ sở hạ tầng `ReactiveVaultTemplate`.

Với Spring Boot, `spring-boot-starter-webflux` thường thêm WebFlux và Reactor Netty, thuận tiện khi ứng dụng đồng thời phục vụ HTTP theo WebFlux. Nếu chỉ muốn client Vault trong một dịch vụ khác, khai báo WebFlux và connector được chọn có thể gọn hơn; cần kiểm tra auto-configuration của ứng dụng thực tế.

**Đừng trộn thế hệ:** Spring Vault 4.1.x cần Spring Framework 7.0.11+, còn các dòng Spring Vault 3.x được thiết kế cho Spring Framework 6.x. Dependency tree có WebFlux 6.x và spring-vault-core 4.1.2 có thể dẫn tới lỗi binary trước khi request được gửi.

Nguồn: [Spring Vault 4.1.2 – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html), [Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html).

## 3. Maven: cấu hình cho Spring Boot 4.1.x

Ví dụ POM cho một **ứng dụng đã có Spring Boot parent**. Bộ phiên bản tham chiếu là Spring Boot **4.1.3** và Spring Vault **4.1.2**; Boot quản lý phiên bản Spring Framework, WebFlux, Reactor và Jackson 3:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.3</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-vault-client-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.vault</groupId>
            <artifactId>spring-vault-core</artifactId>
            <version>4.1.2</version>
        </dependency>

        <!-- Có WebClient, Reactor Core và codecs -->
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-webflux</artifactId>
        </dependency>

        <!-- Spring Vault 4.x cho ứng dụng tự chọn JSON mapper -->
        <dependency>
            <groupId>tools.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </dependency>

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**Đây là ví dụ dependency**, chưa tự kết nối Vault. Bean HTTP connector, TLS, `VaultTokenSupplier`/`ReactiveSessionManager`, role và policy cần được cấu hình ở ứng dụng. Vì dùng JDK `HttpClient` là một lựa chọn được Spring Vault hỗ trợ, đoạn POM trên **không bắt buộc** thêm `reactor-netty` chỉ để dùng API reactive.

Nếu dùng Spring Framework thuần không có Boot BOM, cần tự quản lý đồng bộ **Spring Framework 7**, Reactor, Jackson 3, connector và những dependency đi kèm. Không sao chép những dependency thiếu `<version>` vào POM không có BOM.

### Khi muốn Reactor Netty cụ thể

Thêm lựa chọn transport sau vào `dependencies` ở trên:

```xml
<dependency>
    <groupId>io.projectreactor.netty</groupId>
    <artifactId>reactor-netty</artifactId>
    <!-- Phiên bản do BOM Boot/Reactor quản lý -->
</dependency>
```

Chỉ có JAR trên classpath **chưa chứng minh** client đang sử dụng Reactor Netty: cần kiểm tra `ClientHttpConnector` được chọn/cấu hình. Đừng thêm cùng lúc mọi transport JDK, Netty, Jetty, Apache rồi suy rằng tất cả đều được dùng.

## 4. Gradle Kotlin DSL: quản lý phiên bản và phạm vi test

Ví dụ ứng dụng Java dùng Gradle native `platform` để nhập BOM Spring Boot, không cần plugin web server:

```kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:4.1.3"))

    implementation("org.springframework.vault:spring-vault-core:4.1.2")
    implementation("org.springframework:spring-webflux")
    implementation("tools.jackson.core:jackson-databind")

    testImplementation("io.projectreactor:reactor-test")
}
```

Nếu muốn dùng Netty, thêm `implementation("io.projectreactor.netty:reactor-netty")` trong cùng `dependencies`. Nếu thay bằng `spring-boot-starter-webflux`, xem lại dependency tree để tránh khai báo lặp `spring-webflux`; starter quản lý thêm các thành phần dành cho ứng dụng Spring Boot.

Với **Gradle dependency management khác** (Boot plugin, version catalog, constraints, `io.spring.dependency-management`), hãy thống nhất một nguồn phiên bản và xem `runtimeClasspath`. Đặc biệt `reactor-test` phải ở **test scope**, không đưa vào runtime production.

**Spring Cloud Vault starter là đường khác:** dùng khi cần tải KV secret vào Spring `Environment`/Config Data (`spring.config.import: "vault://"`). Cần BOM Spring Cloud tương thích Spring Boot. Starter Cloud Vault **không biến mọi tác vụ Vault thành reactive API**; muốn gọi `Mono`/`Flux` chủ động hãy sử dụng `ReactiveVaultOperations` và cấu hình bean reactive.

## 5. Những HTTP connector nào thực sự không chặn?

Spring Vault 4.1.2 có `ClientHttpConnectorFactory` để dựng một `ClientHttpConnector` theo những transport có mặt; JDK `HttpClient` là lựa chọn sẵn có không cần dependency ngoài JDK. Các lựa chọn khác:

| Connector | Dependency mẫu | Thích hợp khi |
| --- | --- | --- |
| **JDK reactive `HttpClient`** | Có trong Java 17, không cần JAR thêm | Client đơn giản, TLS theo truststore JVM, ít tuỳ biến |
| **Reactor Netty** | `io.projectreactor.netty:reactor-netty` | Ứng dụng muốn kiểm soát connection pool, event loops, TLS/timeout theo Netty |
| **Apache HTTP Components reactive** | `org.apache.httpcomponents.core5:httpcore5-reactive` | Tổ chức đã chọn Apache reactive transport |
| **Jetty reactive** | `org.eclipse.jetty:jetty-reactive-httpclient` | Dự án sử dụng Jetty reactive client và bộ phụ thuộc phù hợp |

Để **chọn connector rõ ràng**, dùng API Spring Vault thay vì trông đợi thư viện tự chọn dựa trên classpath.

```java
import java.time.Duration;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.vault.client.ClientHttpConnectorFactory;
import org.springframework.vault.support.ClientOptions;
import org.springframework.vault.support.SslConfiguration;

ClientOptions options = new ClientOptions(
        Duration.ofSeconds(3), Duration.ofSeconds(12));

ClientHttpConnector connector = ClientHttpConnectorFactory.create(
        options, SslConfiguration.unconfigured());
```

Đoạn trên khai báo timeout kết nối/đọc và để factory chọn transport **từ dependency hiện có**. Để bắt buộc Reactor Netty khi đã cài đúng artifact:

```java
ClientHttpConnector nettyConnector =
        ClientHttpConnectorFactory.ReactorNetty.usingReactorNetty(
                options, SslConfiguration.unconfigured());
```

Hai khối Java trên là những đoạn mã liên tiếp trong cùng method có đủ biến/import. Không dùng `nettyConnector` nếu không cài Reactor Netty. Đối với client được tạo bằng factory, xác minh transport qua cấu hình bean và kiểm thử kết nối, không chỉ qua sự hiện diện của JAR.

**TLS/mTLS:** không tắt hostname verification để làm bài test “xanh”. Đặt CA tin cậy, truststore và client certificate theo cách connector cụ thể hỗ trợ. Tài liệu Spring Vault 4.1 lưu ý cơ chế `SslConfiguration` scoped của Vault chỉ áp dụng khi có **Apache HttpComponents** theo cấu hình mô tả; với JDK hoặc Netty cần xác minh SSL context thực tế. Khi dùng default truststore của JVM, `SslConfiguration.unconfigured()` không cung cấp CA riêng cho hệ thống.

Nguồn: [HTTP Client Support](https://docs.spring.io/spring-vault/reference/vault/client-support.html), [ClientHttpConnectorFactory Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ClientHttpConnectorFactory.html).

## 6. Khởi tạo `ReactiveVaultTemplate` với quản lý session

Ở Spring Vault 4.1+, `ReactiveVaultTemplate` nhận `ReactiveVaultClient` và `VaultTokenSupplier` (mà `ReactiveSessionManager` triển khai). Ví dụ bean sau minh họa việc gắn một client có endpoint và connector rõ ràng với **reactive session manager đã được cấu hình ở nơi khác**:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.vault.authentication.ReactiveSessionManager;
import org.springframework.vault.client.ClientHttpConnectorFactory;
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.ReactiveVaultTemplate;
import org.springframework.vault.support.ClientOptions;
import org.springframework.vault.support.SslConfiguration;

@Configuration(proxyBeanMethods = false)
public class ReactiveVaultClientConfiguration {

    @Bean
    ReactiveVaultOperations reactiveVaultOperations(
            ReactiveSessionManager sessionManager) {

        ClientHttpConnector connector = ClientHttpConnectorFactory.create(
                new ClientOptions(Duration.ofSeconds(3), Duration.ofSeconds(12)),
                SslConfiguration.unconfigured());

        ReactiveVaultClient client = ReactiveVaultClient.builder()
                .endpoint(org.springframework.vault.client.VaultEndpoint.from(
                        java.net.URI.create("https://vault.internal.example:8200")))
                .clientConnector(connector)
                .build();

        return new ReactiveVaultTemplate(client, sessionManager);
    }
}
```

**Giới hạn của ví dụ:** `vault.internal.example` là tên giả; cần CA/TLS, DNS, Vault role/policy thực và một **bean `ReactiveSessionManager` đang hoạt động**. Mẫu này chủ động tạo bean `ReactiveVaultOperations`; nếu dùng `AbstractReactiveVaultConfiguration` hoặc starter đã tự tạo `ReactiveVaultTemplate`, **không tạo thêm bean cạnh tranh cùng mục đích**.

### 6.1. Có thể để Spring Vault cung cấp hạ tầng reactive

`AbstractReactiveVaultConfiguration` là lớp Spring hỗ trợ sẵn. Ứng dụng kế thừa lớp này cần cung cấp `vaultEndpoint()` và `clientAuthentication()`, sau đó framework có thể tạo `ReactiveVaultClient`, `ReactiveVaultTemplate`, `ReactiveSessionManager` và các thành phần liên quan. Các bean `ReactiveVaultClientCustomizer` có thể điều chỉnh builder khi cấu hình sử dụng cơ chế nhận diện chúng. Cách này phù hợp khi muốn vòng đời bean/session thuộc Spring context.

**Không phải mọi `ClientAuthentication` đều phản ứng không chặn.** Cấu hình reactive tạo `VaultTokenSupplier` từ authentication theo `AuthenticationStepsFactory`; những phương thức xác thực phụ thuộc SDK cloud/IAM/metadata có thể có đoạn blocking hoặc không hỗ trợ bước reactive tương ứng. Cần đối chiếu auth cụ thể (Kubernetes, JWT, AppRole, AWS, GCP) với tài liệu cùng phiên bản.

### 6.2. Session manager phải tái sử dụng token

`ReactiveSessionManager` cung cấp token bằng `Mono<VaultToken>` qua `getVaultToken()`. `ReactiveLifecycleAwareSessionManager` có thể quản lý việc lấy và gia hạn/re-login token, gửi sự kiện auth lỗi/hết hạn và hủy session khi Spring context đóng. **Không tự login lại mỗi lần đọc một KV secret**: điều đó tăng tải Vault và làm lộ cơ hội hết hạn/race khi nhiều request đến cùng lúc.

Tương tự, việc trả `Mono` từ phương thức chỉ đang gọi `VaultTemplate.read()` đồng bộ **không làm lời gọi này tự trở thành non-blocking**. Giải pháp là dùng `ReactiveVaultOperations` với connector reactive và token supplier tương ứng.

Nguồn: [AbstractReactiveVaultConfiguration Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/config/AbstractReactiveVaultConfiguration.html), [ReactiveLifecycleAwareSessionManager Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/ReactiveLifecycleAwareSessionManager.html).

## 7. Đọc KV v2 bằng `Mono` và xử lý kết quả rỗng

Giả sử Vault mount KV v2 có tên `secret`, secret path `orders/config` được phép đọc, và ứng dụng đã inject `ReactiveVaultOperations`:

```java
import reactor.core.publisher.Mono;
import org.springframework.vault.core.ReactiveVaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponseSupport;

public final class OrderConfigService {
    private final ReactiveVaultOperations vault;

    public OrderConfigService(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    public Mono<OrderConfig> load() {
        return vault.opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("orders/config", OrderConfig.class)
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Required Vault config is missing")))
                .flatMap(response -> Mono.justOrEmpty(response.getData()))
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Vault config has no data")));
    }

    public record OrderConfig(String baseUrl, int retryLimit) { }
}
```

`ReactiveVaultKeyValueOperations.get(path, Class<T>)` trả về `Mono<VaultResponseSupport<T>>`. Khi thiếu secret, publisher có thể **complete rỗng**, nên dùng `switchIfEmpty` để thể hiện rõ nghĩa “secret bắt buộc”. Khi lỗi Vault auth/ACL hoặc chuyển JSON, publisher phát `onError`; **không** dùng `onErrorResume(e -> Mono.empty())` cho mọi exception, vì điều đó biến 403 hoặc lỗi TLS thành “không có secret” và che sự cố bảo mật.

KV v2 có HTTP path dạng `secret/data/orders/config`; khi gọi API domain `opsForKeyValue("secret", KV_2).get("orders/config")`, **không** tự thêm `data/` vào path. Nếu muốn dùng version cụ thể hoặc CAS, xem `opsForVersionedKeyValue`. Cơ chế này không cấp thêm quyền: token vẫn phải có `read` trên path KV tương ứng.

**Chú ý DTO:** ví dụ chỉ minh họa kiểu giá trị, còn ứng dụng thật cần validate dữ liệu sau deserialize. Jackson 3 được chọn có chủ đích theo stack Framework 7; nếu thiếu Jackson hoặc custom codec sai, kết nối HTTPS có thể thành công nhưng mapping POJO vẫn thất bại.

## 8. Gọi Transit và các endpoint đặc biệt

Reactive Spring Vault có API domain Transit. Ví dụ mã hóa một giá trị qua Transit key `orders-key`:

```java
import reactor.core.publisher.Mono;
import org.springframework.vault.core.ReactiveVaultOperations;

class PaymentCipherService {
    private final ReactiveVaultOperations vault;

    PaymentCipherService(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    Mono<String> encrypt(String plaintext) {
        return vault.opsForTransit("transit")
                .encrypt("orders-key", plaintext);
    }
}
```

Phương thức `encrypt(String keyName, String plaintext)` trả `Mono<String>` chứa ciphertext do Vault tạo; TLS, token và policy Transit `update` vẫn bắt buộc. Đừng log plaintext hoặc ciphertext nhạy cảm từ callback `doOnNext` để debug reactive.

Nếu endpoint Vault chưa có API domain, `ReactiveVaultClient` cung cấp HTTP fluent:

```java
import reactor.core.publisher.Mono;
import org.springframework.vault.authentication.ReactiveSessionManager;
import org.springframework.vault.client.ReactiveVaultClient;
import org.springframework.vault.support.VaultResponse;

class RawSecretReader {
    private final ReactiveVaultClient client;
    private final ReactiveSessionManager sessionManager;

    RawSecretReader(ReactiveVaultClient client,
                    ReactiveSessionManager sessionManager) {
        this.client = client;
        this.sessionManager = sessionManager;
    }

    Mono<VaultResponse> read() {
        return sessionManager.getVaultToken()
                .flatMap(token -> client.get()
                        .path("secret/data/orders/config")
                        .token(token)
                        .retrieve()
                        .body());
    }
}
```

Ở đây `body()` là **Mono<VaultResponse>`, việc gửi HTTP được thực hiện khi publisher được subscribe. Client fluent đọc **HTTP JSON response của KV v2**, có lớp `data` và metadata lồng nhau; nếu chỉ cần secret data nên dùng `ReactiveVaultOperations` như ở phần 7. Không truyền URI tuyệt đối hoặc chuỗi traversal từ người dùng vào `path(...)`. Các bản Spring Vault 4.0.5/4.1.2 đã vá CVE-2026-41698 liên quan secret path, nhưng ứng dụng vẫn phải validate input path.

## 9. Giới hạn song song, timeout, retry và các lỗi Reactor thường gặp

### 9.1. Có non-blocking chưa chắc đã kiểm soát tải

Mỗi `Mono` KV thường chỉ trả một kết quả. Khi xử lý nhiều đơn hàng, đừng tạo hàng nghìn request Vault không giới hạn bằng `flatMap` mặc định hoặc `subscribe()` thủ công trong vòng lặp. Đặt **giới hạn concurrency**, quan sát lỗi 429/5xx và cân nhắc cache secret an toàn theo TTL nếu nhiều request cùng đọc một giá trị:

```java
Flux.fromIterable(orderIds)
    .flatMap(id -> fetchMetadataThenUseSecret(id), 8)
    .collectList();
```

Đoạn trên chỉ minh họa điều phối Reactor: `fetchMetadataThenUseSecret` và `orderIds` là giá trị/phương thức của ứng dụng. Concurrency 8 là ví dụ, phải chọn theo giới hạn Vault, latency và quy mô pod. Không nên tải cùng một secret cho từng request nếu giá trị có thể được cache ngắn hạn với cơ chế invalidation/rotation được xác định rõ.

**Backpressure không thay thế rate limit hoặc concurrency limit.** Reactor có thể yêu cầu ít dữ liệu từ upstream, nhưng một pipeline chứa nhiều `flatMap` và request HTTP riêng lẻ vẫn có thể gây tải lớn lên Vault nếu không giới hạn.

### 9.2. Timeout theo từng tầng

Phân biệt **HTTP connector timeout** với **deadline của pipeline Reactor**:

- `ClientOptions`/connector đặt connect/read timeout của transport; phù hợp với hạ tầng mạng và Vault HA.
- `Mono.timeout(Duration)` tạo deadline cho **toàn chuỗi**, có thể bao gồm chờ login, queue hoặc xử lý khác; nó không tự sửa TCP timeout bị cấu hình sai.
- `retryWhen(Retry.backoff(...))` chỉ dành cho lỗi nhất thời **đã phân loại**. 401/403 cần kiểm tra authentication/policy; 404 thường cần kiểm tra path/mount; không retry POST ghi secret, Transit/PKI thiếu kiểm soát idempotency/CAS.
- `onErrorResume` phải có điều kiện rõ (ví dụ fallback read-only được phép) và không được nuốt mọi lỗi thành secret mặc định.

Không đặt timeout quá thấp rồi tăng số lần retry vô hạn: điều đó khuếch đại tải khi Vault đang lỗi. Không đưa toàn bộ request/response hoặc giá trị token vào log, metrics tag hay trace.

### 9.3. Tránh chặn event loop

| Anti-pattern | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `vaultMono.block()` trong WebFlux handler | Chặn luồng nhận request; có thể gây deadlock/tăng latency | Trả `Mono` từ handler/service, để framework subscribe |
| `Mono.just(blockingVaultTemplate.read(...))` | Lời gọi đồng bộ chạy **ngay** trước khi tạo Mono | Dùng `ReactiveVaultOperations`; nếu bắt buộc tích hợp mã blocking, tách sang `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` |
| `subscribe()` trong service rồi trả `void` | Mất đường truyền lỗi, cancellation, deadline và trace | Trả publisher lên caller; chỉ subscribe ở boundary chủ đích |
| Chạy SDK xác thực blocking trong `map` | Chặn event loop dù HTTP Vault reactive | Dùng auth có bước reactive; nếu không có, cách ly bước blocking trên scheduler phù hợp và kiểm thử |
| `onErrorResume(err -> Mono.empty())` cho mọi lỗi | Che lỗi 403/TLS/JSON, khiến ứng dụng tưởng không có secret | Phân loại lỗi và giữ nguyên `onError` cho lỗi quan trọng |
| Nhiều `flatMap` không hạn chế | Gây bão request Vault và 429/timeout | Đặt giới hạn concurrency, timeout và metric |

### 9.4. Session/lease không tự được làm mới chỉ vì có Mono

**Token** phải được cấp và tái sử dụng qua `ReactiveSessionManager`; **lease của dynamic credentials** có vòng đời riêng. Một pipeline đọc username/password bằng `Mono` một lần rồi giữ vào connection pool sẽ **không tự làm cho pool nhận mật khẩu mới** sau khi Vault rotate. Cần thiết kế cập nhật credential/connection, gia hạn lease, expiry và kiểm thử khi Vault không sẵn sàng.

Các API quản lý vòng đời/lease và PKI có thể có hoạt động nội bộ hoặc callback đòi thread riêng. Đừng suy từ việc caller nhận `Mono` rằng **mọi** tác vụ auth, SDK cloud, scheduler và rotation trong ứng dụng đều non-blocking.

## 10. Kiểm tra classpath runtime và test reactive

### Maven

```bash
mvn -version
mvn help:effective-pom
mvn dependency:tree
```

Tìm tối thiểu `spring-vault-core`, `spring-webflux`, `reactor-core`, `reactive-streams`, `jackson-databind` và connector đang dùng. Nếu dùng Spring Boot, kiểm tra BOM thực sự resolve, không chỉ dựa vào phiên bản bạn ghi trên dependency trực tiếp.

### Gradle

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-vault-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webflux
./gradlew dependencyInsight --configuration runtimeClasspath --dependency reactor-core
./gradlew dependencyInsight --configuration runtimeClasspath --dependency jackson-databind
```

Ở Windows dùng `gradlew.bat`. Khi lỗi xuất hiện ở CI/container nhưng máy phát triển chạy được, kiểm tra JDK, packaged runtime dependency, SSL truststore và DNS trên **container thực tế**.

### Test luồng tín hiệu bằng Reactor Test

Dependency `io.projectreactor:reactor-test` trong phạm vi `test` cung cấp `StepVerifier`. Ví dụ kiểm tra publisher mã hóa Transit có phát ciphertext đúng định dạng và hoàn tất:

```java
import reactor.test.StepVerifier;
import org.junit.jupiter.api.Test;
import org.springframework.vault.core.ReactiveVaultOperations;

class TransitIntegrationTest {
    private final ReactiveVaultOperations vault;

    // Giả định framework kiểm thử đã inject Vault và cấu hình
    // transit/orders-key trong Vault test server.
    TransitIntegrationTest(ReactiveVaultOperations vault) {
        this.vault = vault;
    }

    @Test
    void encryptsWithTransit() {
        StepVerifier.create(vault.opsForTransit("transit")
                .encrypt("orders-key", "non-sensitive-test-payload"))
            .expectNextMatches(value -> value.startsWith("vault:v"))
            .verifyComplete();
    }
}
```

Đây là **ví dụ thân phương thức test**: để JUnit có thể chạy thật, cần cấu hình test engine/extension phù hợp để tạo instance test và inject `ReactiveVaultOperations`. Không copy nguyên constructor injection mà bỏ qua extension/constructor autowiring. Test nói trên chỉ có giá trị tích hợp khi thực sự kết nối Vault test được cấp quyền trên key; mock có thể giúp test luồng Reactor nhưng không kiểm chứng TLS/auth/policy.

Đối với test nghiệp vụ chỉ cần `Mono`/`Flux`, `StepVerifier` có thể xác minh thứ tự `onNext`/`onComplete`/`onError`. Với luồng retry/timeout phụ thuộc thời gian, dùng `StepVerifier.withVirtualTime(...)` nhưng **virtual time không thay thế timeout mạng của connector**, cũng không làm một Vault thật trả phản hồi nhanh hơn.

Nếu dùng Testcontainers Vault, khai báo `testImplementation("org.testcontainers:testcontainers-vault")` và quản lý phiên bản bằng Testcontainers BOM phù hợp. Bật KV v2/Transit/PKI, tạo auth role và policy **chỉ trong môi trường test** để kiểm tra cả đường thành công lẫn 403, 404, token hết hạn, retry và không lộ secret.

Nguồn: [Reactor Test – StepVerifier](https://docs.spring.io/projectreactor/reactor-core/docs/current/reference/html/#testing), [Testcontainers – Vault Module](https://java.testcontainers.org/modules/vault/).

## 11. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `NoClassDefFoundError: WebClient` hoặc `ClientHttpConnector` | Thiếu `spring-webflux` hoặc sai thế hệ Spring | Runtime classpath, Framework 7 với Vault 4.1 |
| `ClassNotFoundException: Mono` / `Flux` | Reactor Core bị exclude/xung đột | Cây phụ thuộc Reactor và WebFlux |
| JSON mapping/codec thất bại | Thiếu Jackson, hai thế hệ Jackson lẫn nhau, sai DTO | Jackson 3/2, codec WebClient, response shape |
| HTTP không phản hồi dù `Mono` được tạo | Publisher chưa được subscribe; hoặc kết nối/network lỗi | Subscriber tại framework boundary, logs an toàn, DNS/TLS |
| `block()` gây lỗi ở event loop | Đang gọi blocking API trong luồng non-blocking | Trả publisher, thay synchronous VaultTemplate |
| `SSLHandshakeException` / `PKIX` | Truststore/client cert của connector sai | CA, hostname, mTLS và connector thực |
| HTTP 401/403 | Auth, role, token hết hạn hoặc Vault policy thiếu quyền | `ReactiveSessionManager`, namespace, Vault ACL |
| `Mono.empty()` khi đọc KV | Secret không tồn tại hoặc API domain có semantics absent | Mount/version/path; dùng `switchIfEmpty` có chủ đích |
| 429/5xx và timeout dưới tải | Concurrency cao, thiếu giới hạn request, Vault quá tải | `flatMap` concurrency, metrics, backoff có giới hạn |
| Credential đổi nhưng kết nối cũ vẫn dùng password cũ | Rotation/lease chưa được đưa vào client/pool | Lifecycle token/lease, refresh của datasource/client |

## 12. Lộ trình áp dụng trong dự án

Một dịch vụ WebFlux cần đọc KV v2 để lấy cấu hình, mã hóa một trường dữ liệu bằng Transit và chạy trên Kubernetes có thể thực hiện như sau:

1. **Chọn bộ phiên bản** Java 17+, Spring Framework 7.0.11+, Spring Vault 4.1.2. Khai báo Core + WebFlux + Jackson 3, và Reactor Netty **chỉ khi** chọn connector Netty. Dùng BOM Spring Boot nếu ứng dụng dựa trên Boot.
2. **Cấu hình HTTPS** endpoint, CA/truststore và timeout. Chọn connector rõ ràng, tránh wire logging; xác minh trong pod thực.
3. **Thiết lập workload auth** bằng JWT ServiceAccount/Kubernetes role và `ReactiveSessionManager`/`VaultTokenSupplier`; không hard-code root token hoặc biến static giữ token.
4. **Thiết kế Vault policy** giới hạn `read` KV v2 path cần thiết và `update` Transit encrypt path tương ứng. Không cấp wildcard rộng để sửa lỗi tạm.
5. **Trả Mono/Flux** từ service/WebFlux handler, phân loại `Mono.empty()` và lỗi; không tự `subscribe()`/`block()` trong event loop.
6. **Giới hạn đồng thời, đặt timeout** và retry có điều kiện; không log secret, token hoặc plaintext của Transit.
7. **Kiểm thử** bằng `StepVerifier`, Vault container và policy gần production; xác nhận ứng dụng không dùng credential hết hạn sau rotation.
8. **Kiểm tra dependency tree và bản vá bảo mật** trước phát hành. Spring đã công bố bản sửa CVE-2026-41698 trong Spring Vault 4.0.5 và 4.1.2 ngày 19/11/2026; vẫn cần validate secret path từ input ngoài.

**Ghi nhớ:** **`spring-vault-core` chứa API reactive**, **`spring-webflux` và Reactor cung cấp WebClient/Mono/Flux**, **`ClientHttpConnector` đảm nhiệm HTTP không chặn**, **Jackson xử lý JSON**, còn **`ReactiveSessionManager` duy trì token an toàn**. Một pipeline chỉ thực sự có lợi khi đường I/O và các callback quan trọng không chặn event loop, đồng thời có kiểm soát concurrency và vòng đời secret.

### Nguồn chính thức để đối chiếu

1. [Spring Vault 4.1.2 – Dependencies](https://docs.spring.io/spring-vault/reference/introduction/dependencies.html)
2. [Spring Vault – Reactive Infrastructure](https://docs.spring.io/spring-vault/reference/vault/reactive-template.html)
3. [Spring Vault – HTTP Client Support](https://docs.spring.io/spring-vault/reference/vault/client-support.html)
4. [Spring Vault – VaultClient và ReactiveVaultClient](https://docs.spring.io/spring-vault/reference/vault/vault-client.html)
5. [ReactiveVaultOperations Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultOperations.html)
6. [ReactiveVaultTemplate Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/ReactiveVaultTemplate.html)
7. [ReactiveVaultClient Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ReactiveVaultClient.html)
8. [ReactiveVaultClient.Builder Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ReactiveVaultClient.Builder.html)
9. [ClientHttpConnectorFactory Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/ClientHttpConnectorFactory.html)
10. [AbstractReactiveVaultConfiguration Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/config/AbstractReactiveVaultConfiguration.html)
11. [ReactiveLifecycleAwareSessionManager Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/ReactiveLifecycleAwareSessionManager.html)
12. [Reactor – Testing with StepVerifier](https://docs.spring.io/projectreactor/reactor-core/docs/current/reference/html/#testing)
13. [Testcontainers – Vault Module](https://java.testcontainers.org/modules/vault/)
14. [Spring Vault 4.0.5/4.1.2 – security fixes, 19/11/2026](https://spring.io/blog/2026/11/19/spring-vault-4-0-5-4-1-2-available/)
