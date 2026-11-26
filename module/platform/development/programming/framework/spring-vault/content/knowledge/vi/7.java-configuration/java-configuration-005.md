# Cấu hình SessionManager và TaskScheduler

Trong chương **Cấu hình Java** của **SPRING_VAULT**, việc tạo một `VaultTemplate` và đọc thành công một secret mới chỉ kiểm tra được đường đi ban đầu: ứng dụng biết Vault endpoint, có cách xác thực và có quyền đối với API được gọi. Khi service chạy hàng giờ hoặc hàng ngày, token có thể hết hạn, Vault có thể yêu cầu đăng nhập lại, và một số secret động cần được gia hạn hoặc thu hồi theo **lease**. Đó là lý do cần hiểu `SessionManager` và `TaskScheduler`.

Bài này hướng dẫn cách Spring Vault quản lý token trong ứng dụng Java, những bean sẵn có của `AbstractVaultConfiguration`, cách tùy chỉnh scheduler bằng Java và cách lựa chọn `SimpleSessionManager` hoặc `LifecycleAwareSessionManager`. Nội dung cũng phân biệt vòng đời **token**, **lease của secret động** với thao tác đọc KV, và đưa ra các kịch bản xử lý lỗi, giám sát, kiểm thử tích hợp.

> **Phạm vi phiên bản:** Ví dụ cấu hình dùng API của Spring Vault 3.2.x, gồm `AbstractVaultConfiguration.TaskSchedulerWrapper`. Một số API tạo HTTP client và `LifecycleAwareSessionManager` thay đổi ở thế hệ Spring Vault 4.x. Khi áp dụng cho dự án thật, kiểm tra Javadoc của đúng phiên bản thư viện trước khi điều chỉnh các phương thức mở rộng.

## 1. Vấn đề: token có thời hạn nhưng ứng dụng chạy lâu

Giả sử một service xử lý đơn hàng có các bước:

1. Khởi động và đăng nhập Vault bằng danh tính workload.
2. Nhận một **Vault token** có policy `read` cho secret ứng dụng.
3. Gọi `VaultTemplate` nhiều lần trong suốt thời gian sống.
4. Token tiến gần thời điểm hết TTL; nếu có thể renew, cần gia hạn hợp lệ.
5. Khi hết hạn hoặc bị revoke, cần xử lý lại quá trình authentication nếu phương thức đăng nhập hỗ trợ.
6. Khi ứng dụng dừng, cần giải phóng các tác vụ nền và xử lý token có trách nhiệm.

Không nên gửi request đăng nhập mới cho mọi lần đọc secret: việc đó tăng tải lên auth backend, làm khó kiểm soát token và gây lỗi khi có nhiều luồng đồng thời. Nhưng cache token mãi mãi cũng không được, vì một token có thể hết hạn hoặc mất quyền.

Hai thành phần giải quyết những phần khác nhau:

| Thành phần | Chức năng cốt lõi | Điều không tự giải quyết |
| --- | --- | --- |
| `ClientAuthentication` | Cung cấp hoặc lấy token theo auth method | Không mặc nhiên quản lý toàn bộ vòng đời token |
| `SessionManager` | Cung cấp token phiên làm việc cho các request; quản lý cách dùng lại/đổi token tùy triển khai | Không cấp Vault policy và không quyết định secret nào có thể đọc |
| `TaskScheduler` | Chạy công việc theo lịch, chẳng hạn renew token/lease đúng thời điểm | Không tự xác thực Vault hoặc gia hạn bất kỳ credential nào nếu không có logic được đăng ký |
| `SecretLeaseContainer` | Theo dõi một số secret có lease, hỗ trợ renew/rotate theo loại secret và cấu hình | Không biến KV secret tĩnh thành leased secret |
| `VaultTemplate` | Gọi API KV, Transit, PKI, token... qua hạ tầng xác thực/session | Không tự tạo policy hoặc role Vault |

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["ClientAuthentication<br/>Token / AppRole / Kubernetes..."] --> B["SessionManager"]
    C["TaskScheduler"] --> B
    B --> D["VaultTemplate"]
    D --> E["Vault HTTP API"]
    C --> F["SecretLeaseContainer"]
    D --> F
    E --> G["KV / Transit / PKI"]
    F --> H["Dynamic secret lease<br/>nếu ứng dụng yêu cầu theo dõi"]
~~~

`SessionManager` quản lý **token dùng cho request**; `SecretLeaseContainer` quản lý **lease của secret** khi ứng dụng sử dụng API/container phù hợp. Cả hai có thể dựa vào scheduler, nhưng trạng thái và quyền gia hạn của chúng là các khái niệm khác nhau.

## 2. SessionManager: lấy và dùng lại token

Giao diện `org.springframework.vault.authentication.SessionManager` cung cấp phương thức quan trọng:

~~~java
VaultToken getSessionToken();
~~~

`VaultTemplate` có thể dùng `SessionManager` để lấy token phiên làm việc thay vì gọi trực tiếp `ClientAuthentication.login()` trong mỗi thao tác nghiệp vụ.

Spring Vault có hai triển khai tiêu biểu:

| Triển khai | Hành vi cơ bản | Phù hợp |
| --- | --- | --- |
| `SimpleSessionManager` | Đăng nhập/lấy token một lần theo nhu cầu, đồng bộ hóa và dùng lại; không tự lên lịch renew/revoke | Trường hợp đơn giản, test, token dài hạn có chiến lược ngoài ứng dụng |
| `LifecycleAwareSessionManager` | Dùng lại token, phối hợp scheduler để renew nếu điều kiện cho phép; xử lý vòng đời token login theo thiết kế | Service chạy lâu cần quản lý token có TTL |
| Tự triển khai `SessionManager` | Điều khiển `getSessionToken()` theo logic đặc biệt | Chỉ khi có yêu cầu rõ ràng mà implementation chuẩn không đáp ứng |

**Điểm phân biệt:** `SimpleSessionManager` không có tác vụ tự gia hạn token. Nó có thể trả lại token đã hết hạn và dẫn tới lỗi khi request tiếp theo dùng token đó. `LifecycleAwareSessionManager` quan sát được thông tin TTL/renewability khi token và quyền Vault cho phép, rồi sắp xếp việc renew phù hợp.

### 2.1. Token tĩnh không đồng nghĩa token có thể đăng nhập lại

Với:

~~~java
ClientAuthentication authentication =
        new TokenAuthentication("token-do-moi-truong-cap");
~~~

`TokenAuthentication` cung cấp token đã có. Nó **không biết** cách lấy token mới nếu nguồn bên ngoài không thay đổi. Dù kết hợp `LifecycleAwareSessionManager`, một token không renewable, đã revoke hoặc không thể refresh vẫn có thể khiến service không lấy được token hợp lệ.

Ngược lại, các auth method như AppRole hoặc Kubernetes có thể thực hiện **login** bằng credential của workload để xin token mới, miễn credential nguồn còn hợp lệ và Vault auth role cho phép. Việc renew, đăng nhập lại hoặc retry vẫn phụ thuộc loại token, session manager, quyền và cấu hình.

### 2.2. Khác biệt giữa token và login token

Không phải mọi token đều có cùng nguồn gốc: token có thể được đưa trực tiếp vào ứng dụng, hoặc được Vault phát hành sau login. Với một token do provider login tạo, session manager có thể quản lý revoke khi hủy phiên theo cơ chế của Spring Vault. **Không mặc định mọi token tĩnh, token root hoặc token do hệ thống bên ngoài quản lý đều sẽ bị Spring Vault thu hồi khi shutdown.**

Khi xem xét quyền và lỗi renewal, cần biết token có phải **renewable** hay không, TTL thực tế và các giới hạn do Vault áp dụng, chẳng hạn `explicit_max_ttl`. Một refresh thành công không có nghĩa token có thể được kéo dài vô hạn.

## 3. TaskScheduler làm gì khi token sắp hết hạn?

`org.springframework.scheduling.TaskScheduler` là abstraction của Spring để chạy một tác vụ vào một thời điểm hoặc theo trigger. `ThreadPoolTaskScheduler` là một triển khai dùng thread pool, có thể chạy tác vụ nền mà không chặn luồng request nghiệp vụ.

Khi `LifecycleAwareSessionManager` nhận được token có thông tin lease duration và token đó có thể renew, nó có thể **lên lịch gia hạn bất đồng bộ** trước thời điểm hết TTL. Với triển khai phổ biến của Spring Vault, khoảng chuẩn bị sớm mặc định khoảng **5 giây** trước expiration theo hằng số `REFRESH_PERIOD_BEFORE_EXPIRY`; đây là chi tiết triển khai và không nên coi là cam kết cho mọi phiên bản, auth method hoặc tình huống mạng.

~~~mermaid
sequenceDiagram
    participant App as Service
    participant Manager as SessionManager
    participant Scheduler as TaskScheduler
    participant Vault as Vault

    App->>Manager: getSessionToken()
    Manager->>Vault: login nếu cần
    Vault-->>Manager: Token có TTL
    Manager-->>App: Token hiện tại
    Manager->>Scheduler: Đặt lịch renew khi đủ điều kiện
    Note over Scheduler: Thời điểm chuẩn bị trước expiry
    Scheduler->>Vault: renew-self hoặc xử lý refresh theo manager
    Vault-->>Scheduler: TTL mới hoặc lỗi
    App->>Manager: getSessionToken() ở request tiếp theo
    Manager-->>App: Token hợp lệ nếu còn khả dụng
~~~

Mô hình này có giới hạn thực tế:

- Vault không cho phép renew một số loại token, hoặc token đã đạt TTL tối đa.
- Nếu clock lệch, mạng chậm hoặc scheduler thiếu tài nguyên, tác vụ có thể chạy muộn.
- Khi Vault tạm unavailable, renew có thể thất bại; cần giám sát và chính sách retry/khôi phục hợp lý.
- Scheduler có thể bị dừng trước khi hoàn tất công việc; ứng dụng phải quản lý shutdown đúng.
- Một `TaskScheduler` được tạo ra **không tự đăng ký** tác vụ renew nếu ứng dụng không dùng session/lease component thích hợp.

Vì vậy, không thể khẳng định “đã cấu hình scheduler thì token sẽ không bao giờ hết hạn”.

## 4. AbstractVaultConfiguration đã cung cấp sẵn những gì?

Với cấu hình Java bằng `AbstractVaultConfiguration`, ứng dụng bắt buộc triển khai `vaultEndpoint()` và `clientAuthentication()`. Còn các bean hạ tầng sau **đã được lớp cơ sở hỗ trợ**:

| API của lớp cơ sở | Vai trò |
| --- | --- |
| `vaultTemplate()` | Tạo bean `VaultTemplate` dùng session manager |
| `sessionManager()` | Mặc định cấu hình `LifecycleAwareSessionManager` dựa trên `clientAuthentication()` |
| `threadPoolTaskScheduler()` | Tạo bean `vaultThreadPoolTaskScheduler` dạng `TaskSchedulerWrapper` |
| `secretLeaseContainer()` | Cung cấp container quản lý lease của secret được đăng ký theo dõi |

Trong Spring Vault 3.2.x, scheduler được **bọc** bởi `AbstractVaultConfiguration.TaskSchedulerWrapper`, giúp cô lập thread pool phục vụ Spring Vault khỏi các scheduler ứng dụng khác. Scheduler này được dùng bởi lifecycle session và `SecretLeaseContainer`. Với cấu hình chỉ cần quản lý token thông thường, **không bắt buộc override `sessionManager()` hoặc `threadPoolTaskScheduler()`**.

Một bảng quyết định:

| Nhu cầu | Cách làm |
| --- | --- |
| Mới học kết nối Vault, không có nhu cầu tuning | Giữ mặc định của `AbstractVaultConfiguration` |
| Task renew bị chậm do tải công việc nền | Cân nhắc tăng pool size của scheduler dành cho Vault |
| Muốn chia sẻ scheduler do ứng dụng đã quản lý | Dùng wrapper `fromInstance(...)` theo API tương thích |
| Muốn bỏ cơ chế lifecycle để có manager đơn giản | Override `sessionManager()` và dùng `SimpleSessionManager`; chấp nhận không tự renew/revoke |
| Muốn thay đổi quy tắc refresh phức tạp | Kiểm tra API `LifecycleAwareSessionManager` và refresh trigger của phiên bản đang dùng |

Các option nâng cao chỉ nên thêm khi hiểu rõ trách nhiệm shutdown, concurrency và vòng đời credential.

## 5. Ví dụ chạy được: cấu hình Java và tùy chỉnh scheduler

Ví dụ dùng Spring Boot, Java 17 trở lên và `spring-vault-core`. Trong `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
</dependency>
~~~

Dự án cần quản lý phiên bản Spring Vault tương thích với Spring Framework thông qua dependency management/BOM hoặc khai báo version cụ thể. Các phương thức wrapper dưới đây tham chiếu API của Spring Vault 3.2.x.

### 5.1. Chuẩn bị Vault dev server

Ở terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Ở terminal thứ hai (Bash):

~~~bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token
vault kv put secret/orders/api apiKey=local-demo-key
~~~

PowerShell dùng:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"
vault kv put secret/orders/api apiKey=local-demo-key
~~~

Giả định `secret` được gắn KV v2 ở dev server. Kiểm tra bằng `vault secrets list -detailed` nếu Vault cục bộ đã tùy chỉnh. **Root token và HTTP của dev server không sử dụng ở production.**

### 5.2. Lớp cấu hình Java

Tạo `VaultJavaConfiguration.java`:

~~~java
package com.example.vault;

import java.net.URI;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;
import org.springframework.vault.config.AbstractVaultConfiguration.TaskSchedulerWrapper;

@Configuration
public class VaultJavaConfiguration extends AbstractVaultConfiguration {

    private final Environment environment;

    public VaultJavaConfiguration(Environment environment) {
        this.environment = environment;
    }

    @Override
    public VaultEndpoint vaultEndpoint() {
        URI uri = URI.create(
                environment.getRequiredProperty("VAULT_ADDR"));

        String scheme = uri.getScheme();
        if (uri.getHost() == null
                || (!"http".equalsIgnoreCase(scheme)
                    && !"https".equalsIgnoreCase(scheme))) {
            throw new IllegalArgumentException(
                    "VAULT_ADDR phải là base URL http(s)://host[:port]");
        }

        int port = uri.getPort() >= 0
                ? uri.getPort()
                : ("https".equalsIgnoreCase(scheme) ? 443 : 80);

        VaultEndpoint endpoint = VaultEndpoint.create(uri.getHost(), port);
        endpoint.setScheme(scheme.toLowerCase(Locale.ROOT));
        return endpoint;
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String token = environment.getRequiredProperty("VAULT_TOKEN");
        if (token.isBlank()) {
            throw new IllegalArgumentException(
                    "VAULT_TOKEN không được rỗng");
        }
        return new TokenAuthentication(token);
    }

    // Tùy chọn: điều chỉnh scheduler riêng của Spring Vault.
    @Override
    @Bean("vaultThreadPoolTaskScheduler")
    public TaskSchedulerWrapper threadPoolTaskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("vault-lifecycle-");
        scheduler.setRemoveOnCancelPolicy(true);

        // Wrapper chịu trách nhiệm gọi lifecycle init/destroy.
        return new TaskSchedulerWrapper(scheduler);
    }

    // Không cần override sessionManager():
    // AbstractVaultConfiguration mặc định cung cấp
    // LifecycleAwareSessionManager dùng scheduler ở trên.
}
~~~

**Giải thích:**

1. `vaultEndpoint()` xác định server; ví dụ local dùng `VAULT_ADDR=http://127.0.0.1:8200`.
2. `clientAuthentication()` cung cấp token có sẵn. Đoạn này chỉ dùng để thực hành; production nên cân nhắc AppRole, Kubernetes auth hoặc danh tính workload khác.
3. `threadPoolTaskScheduler()` **override đúng extension point của lớp cơ sở** và giữ nguyên bean name `vaultThreadPoolTaskScheduler`. Điều này thay scheduler dành cho Vault, thay vì tạo một scheduler không ai sử dụng.
4. `TaskSchedulerWrapper` giữ việc khởi tạo và dọn dẹp thread pool theo vòng đời của Spring. Không gọi `scheduler.initialize()` thủ công trong ví dụ này.
5. Pool size `2` chỉ minh họa việc tùy chỉnh. Giá trị thực tế phải xét số nhiệm vụ renew/lease, thời gian thực hiện, độ trễ Vault và khả năng xử lý song song.
6. `SessionManager` mặc định vẫn là `LifecycleAwareSessionManager`. `VaultTemplate` tiếp tục dùng hạ tầng này mà không cần định nghĩa thêm bean riêng.

Ví dụ không thực hiện kiểm tra path/userinfo/query của URI để tập trung vào session và scheduler. Trong ứng dụng thật, chỉ nhận base URL hợp lệ, dùng HTTPS/TLS ở staging và production, kiểm tra CA/trust store, timeout và mạng.

### 5.3. Không cần thay scheduler nếu mặc định đã đủ

Nếu muốn dùng cấu hình mặc định, hãy **xóa toàn bộ phương thức override `threadPoolTaskScheduler()`** và các import liên quan. `AbstractVaultConfiguration` vẫn đăng ký scheduler và session manager. Chỉ thêm tùy chỉnh khi có yêu cầu vận hành và số liệu chứng minh.

## 6. Muốn chia sẻ một scheduler đã có sẵn thì làm thế nào?

Trong vài hệ thống, ứng dụng có `ThreadPoolTaskScheduler` được quản lý tập trung, ví dụ scheduler của nền tảng. Spring Vault cung cấp wrapper `TaskSchedulerWrapper.fromInstance(...)` để dùng một scheduler **đã được Spring khởi tạo và quản lý lifecycle**.

Ví dụ cấu hình thay thế cho phần scheduler ở mục 5:

~~~java
// Đặt trong một lớp @Configuration của ứng dụng:
@Bean("sharedBackgroundScheduler")
public ThreadPoolTaskScheduler sharedBackgroundScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("shared-background-");
    return scheduler;
}
~~~

Ở lớp kế thừa `AbstractVaultConfiguration`, khi đã inject một scheduler có sẵn từ Spring:

~~~java
@Override
@Bean("vaultThreadPoolTaskScheduler")
public TaskSchedulerWrapper threadPoolTaskScheduler() {
    return TaskSchedulerWrapper.fromInstance(existingScheduler);
}
~~~

Ở đây `existingScheduler` là **field `ThreadPoolTaskScheduler` được inject từ bean `sharedBackgroundScheduler`** vào lớp cấu hình; đoạn thứ hai là ví dụ thay thế, không được chép cùng lúc với phương thức của mục 5. Khi thực hiện, nên dùng constructor injection và `@Qualifier("sharedBackgroundScheduler")` để chọn đúng scheduler, tránh trường hợp có nhiều bean `TaskScheduler`. Với `fromInstance(...)`, wrapper **không sở hữu** vòng đời của scheduler bên ngoài; Spring hoặc chủ sở hữu gốc phải khởi tạo và shutdown scheduler đó.

Chỉ chia sẻ scheduler khi hiểu ảnh hưởng lẫn nhau: công việc nền của ứng dụng có thể làm chậm renew token/lease và ngược lại. Đối với production, một scheduler riêng cho Vault thường dễ cô lập và giám sát hơn.

## 7. Override SessionManager khi thực sự cần

### 7.1. Giữ LifecycleAwareSessionManager mặc định

Đây là lựa chọn phù hợp cho phần lớn workload có token cần được quản lý theo TTL. Spring Vault kết hợp `ClientAuthentication`, session manager và scheduler khi tạo `VaultTemplate`. Nếu dùng `AbstractVaultConfiguration`, **không cần** viết:

~~~java
@Bean
public SessionManager anotherSessionManager() {
    // Không nên tạo bean thứ hai chỉ để lặp lại mặc định.
    throw new UnsupportedOperationException("Chỉ minh họa");
}
~~~

Đoạn trên chỉ minh họa một **anti-pattern**, không phải code cần thêm. Tạo hai bean `SessionManager` có thể gây trùng hạ tầng hoặc khiến service sử dụng sai instance.

### 7.2. Nếu buộc phải dùng SimpleSessionManager

Với môi trường demo có vòng đời token được quản lý hoàn toàn bên ngoài ứng dụng, có thể **thay** phương thức `sessionManager()` trong lớp kế thừa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.authentication.SimpleSessionManager;

// Trong lớp extends AbstractVaultConfiguration:
@Override
@Bean
public SessionManager sessionManager() {
    return new SimpleSessionManager(clientAuthentication());
}
~~~

Đây là **lựa chọn thay thế** cho manager mặc định. `SimpleSessionManager` vẫn có thể dùng lại token nhưng **không tự lên lịch gia hạn hoặc revoke**. Nếu dùng token tĩnh hết hạn giữa chừng, các request Vault sau đó có thể lỗi cho đến khi service được cấp credential mới và vòng đời được điều phối lại.

Không nên chọn `SimpleSessionManager` chỉ để tránh lỗi renew: phải xác định nguyên nhân quyền/TTL thực tế và thiết kế cách cấp token mới đúng.

### 7.3. Khi nào tự tạo LifecycleAwareSessionManager?

Chỉ nên override nếu cần một refresh trigger riêng, thay quản lý authentication hoặc tích hợp HTTP client tùy chỉnh. Trong Spring Vault 3.2.x, constructor tiêu biểu nhận:

~~~java
new LifecycleAwareSessionManager(
    clientAuthentication,
    taskScheduler,
    restOperations);
~~~

Trong Spring Vault 4.x, API liên quan `RestClient` và `VaultClient` được mở rộng, và một số constructor nhận `RestOperations` đã được đánh dấu deprecated. Vì vậy ví dụ trên **diễn giải signature cho thế hệ 3.2**, không phải đoạn thay thế trực tiếp có thể sao chép vào mọi phiên bản. Khi không thật sự cần mở rộng, giữ `sessionManager()` mặc định giúp tránh coupling theo version và sai dependency lúc khởi tạo.

Một cách kiểm tra hành vi của session manager là đọc log sự kiện lifecycle và kiểm thử TTL bằng một token renewable thực tế, thay vì buộc phương thức `getSessionToken()` chạy theo lịch riêng từ code nghiệp vụ.

## 8. Token lifecycle khác secret lease như thế nào?

Đây là phân biệt đặc biệt quan trọng khi học Spring Vault.

| Tiêu chí | Token | Lease của secret động | Secret KV tĩnh |
| --- | --- | --- | --- |
| Được dùng để làm gì? | Xác thực các request Vault | Cho phép sử dụng credential/tài nguyên có thời hạn | Lưu dữ liệu ứng dụng như username/password |
| Do thành phần nào quản lý? | `SessionManager` / auth backend | `SecretLeaseContainer` hoặc logic quản lý lease tương ứng | `VaultKeyValueOperations` khi đọc/ghi |
| Có TTL không? | Có thể có TTL, renewable hoặc không | Thường có lease duration và lease ID | Một lần đọc KV thường không cấp lease mới |
| Renew bằng cách nào? | Token renew theo quyền và loại token | Lease renew theo khả năng của secrets engine | Không renew “lease KV” cho mỗi lần đọc |
| Revoke có tác động gì? | Token không còn hợp lệ; quyền truy cập qua token mất | Credential/tài nguyên có thể hết hiệu lực sớm | Dữ liệu KV không tự biến mất khi token bị revoke |

Ví dụ:

- Service dùng token `orders-reader` để **đọc `secret/orders/api` trong KV v2**: đây là hoạt động KV tĩnh, không phát sinh một lease của secret riêng mỗi lần đọc. Nhưng token gọi Vault có thể hết TTL.
- Service yêu cầu **database dynamic credentials**: Vault trả cặp credential có TTL/lease ID. Một thành phần quản lý lease cần xử lý thời điểm renew/rotate/revoke phù hợp, song song với quản lý token.
- Service gọi **Transit encryption**: yêu cầu permission trên path Transit, không vì vậy tự phát sinh một database lease.
- Service yêu cầu **chứng chỉ PKI**: có thời gian hiệu lực và cơ chế xử lý/thu hồi đặc thù; không coi mọi chứng chỉ tương đương một lease có thể renew tự động.

### SecretLeaseContainer có chạy tự động cho mọi path?

Không. Việc `AbstractVaultConfiguration` tạo được bean `SecretLeaseContainer` không có nghĩa Spring Vault tự tìm kiếm, đọc và theo dõi tất cả secret ở mọi mount. Ứng dụng hoặc integration phải đăng ký những lease/secret cụ thể cần quản lý theo API và cấu hình phù hợp.

Với các credential động, còn phải tính cách ứng dụng nhận giá trị mới (đổi connection pool, rotate certificate, cập nhật client...) khi lease hết hạn hoặc được cấp lại. Scheduler chỉ vận hành **thời điểm xử lý**; nó không tự thay một connection JDBC đang sử dụng credential cũ.

## 9. Quan sát thời gian sống của token trong bài thực hành

### 9.1. Root token dev không đủ để thử renew

Token `dev-only-token` của dev server rất tiện cho phép đọc KV, nhưng không phù hợp để chứng minh `LifecycleAwareSessionManager` có gia hạn token đúng hay không: dev root token không mô phỏng toàn bộ TTL, policy và login lifecycle của workload production.

Để kiểm thử token lifecycle, cần một token có TTL/renewability **được cấu hình thật** hoặc đăng nhập qua auth method như AppRole/Kubernetes với role được giới hạn thời gian. Kiểm tra policy `auth/token/lookup-self`, quyền renew khi cần, khoảng TTL, max TTL và phương thức đăng nhập lại theo chính sách của Vault.

### 9.2. Kiểm tra KV v2 bằng VaultTemplate

Tạo `OrdersSecretReader.java` trong ứng dụng Spring Boot:

~~~java
package com.example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersSecretReader {

    private final VaultTemplate vaultTemplate;

    public OrdersSecretReader(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public boolean canReadApiKey() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("orders/api");

        Map<String, Object> data =
                response == null ? null : response.getData();

        return data != null
                && data.get("apiKey") instanceof String apiKey
                && !apiKey.isBlank();
    }
}
~~~

Spring dùng `SessionManager` để cung cấp token cho request qua `VaultTemplate`. Đường dẫn HTTP tương ứng khi đọc là `GET /v1/secret/data/orders/api`; policy đọc KV v2 cần:

~~~hcl
path "secret/data/orders/api" {
  capabilities = ["read"]
}
~~~

Một test khi startup có thể inject `OrdersSecretReader` và gọi `canReadApiKey()`, sau đó chỉ ghi log rằng phép đọc thành công/thất bại. **Không log token, apiKey, response đầy đủ hay dữ liệu secret.**

Chạy đọc một lần thành công chỉ chứng minh kết nối, auth và policy tại thời điểm đó. Muốn kiểm tra renew theo thời gian, phải dùng token renewable với TTL ngắn có kiểm soát, theo dõi ít nhất một chu kỳ và thử sau khi token cũ có thể hết hạn. Không nên lấy root token không hết hạn làm bằng chứng session lifecycle chính xác.

## 10. Lỗi thường gặp khi cấu hình SessionManager/TaskScheduler

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Lỗi thiếu `VAULT_TOKEN` lúc khởi động | Credential chưa được cấp cho process Java | Cấp biến môi trường ở runtime; production dùng auth workload |
| Ban đầu đọc được, sau TTL thì 403 | Token hết hạn/đã revoke hoặc policy thay đổi | Xem token lifecycle, quyền renew/login và policy |
| Có scheduler nhưng không thấy token renew | Token không renewable, thiếu TTL hoặc không có tác vụ cần chạy | Xác minh loại token, quyền lookup/renew và session manager đang dùng |
| Task renew chạy muộn | Thread pool nhỏ, scheduler bị nghẽn, JVM pause hoặc Vault chậm | Theo dõi latency, queue, thread và thời điểm scheduled execution |
| Tăng pool size nhưng vẫn lỗi | Lỗi không phải thiếu thread: Vault sealed, network/TLS, policy | Khoanh vùng root cause trước khi tuning |
| HTTP 401 hoặc 403 khi renew | Token bị revoke, không có quyền hoặc TTL tối đa đã đạt | Xác nhận auth role, quyền và giới hạn TTL từ Vault |
| Có hai bean `SessionManager` | Override không thay đúng bean mặc định hoặc auto config chồng | Kiểm tra bean name, định nghĩa `@Bean` và cấu hình được load |
| `RejectedExecutionException` | Scheduler đã shutdown hoặc bị từ chối tác vụ | Kiểm tra bean lifecycle và quá trình dừng ứng dụng |
| App tắt nhưng thread không dừng | Scheduler tự tạo ngoài Spring mà không cleanup | Để Spring quản lý bean hoặc wrapper sở hữu lifecycle |
| KV v2 đọc được nhưng dynamic secret hết lease | Chỉ quản lý token, chưa quản lý lease riêng | Cấu hình `SecretLeaseContainer` và xử lý rotation theo engine |
| TaskScheduler chạy ổn nhưng request KV 404 | Mount hoặc đường dẫn secret sai | Kiểm tra `secret`, `orders/api`, `KV_2` |
| TLS handshake/timeout | Vấn đề kết nối, không phải scheduler | Kiểm tra endpoint, CA, DNS, timeout và trạng thái Vault |

**Không thử tự gia hạn token bằng cách gọi API renew trong nhiều thread nghiệp vụ** nếu session manager đã quản lý việc đó. Dễ tạo race condition và ghi đè trạng thái token. Nếu cần cơ chế đặc biệt, thiết kế tập trung tại tầng session.

### Token bị revoke khi ứng dụng vẫn chạy

Không phải trường hợp nào refresh cũng khôi phục được ngay. Nếu có khả năng login lại bằng identity workload, session manager/logic login phù hợp có thể xin token khác tùy lỗi và version. Nếu `TokenAuthentication` chỉ giữ nguyên một token tĩnh đã bị revoke, ứng dụng không có credential mới để đăng nhập lại. Cần quy trình rotation/cấp lại token ở tầng triển khai hoặc chuyển sang phương thức workload auth có khả năng nhận token mới.

## 11. Kiểm thử tích hợp có ý nghĩa

Với bài học này, nên kiểm thử **cả thành phần hạ tầng và hành vi theo thời gian**, tránh chỉ mock từng phương thức.

| Kịch bản | Kết quả cần xác nhận |
| --- | --- |
| Spring context với `AbstractVaultConfiguration` | Có `VaultTemplate`, `SessionManager` và scheduler phù hợp |
| Cấu hình override scheduler pool size `2` | Bean `vaultThreadPoolTaskScheduler` được tạo đúng, thread pool khởi tạo/đóng cùng Spring |
| Token hợp lệ, KV v2 có dữ liệu | Service đọc đúng secret và không log credential |
| Token không renewable | Không giả định auto-renew; xử lý TTL và giới hạn đúng |
| Token renewable, TTL ngắn | Quan sát renew trong thời gian phù hợp và đọc KV tiếp tục thành công |
| Token đạt max TTL hoặc bị revoke | Manager không quay vòng vô hạn; lỗi/đăng nhập lại theo thiết kế |
| AppRole hoặc Kubernetes auth | Token mới được cấp theo workload role khi có khả năng, policy đúng |
| Vault tạm unavailable | Có timeout, backoff/khôi phục phù hợp; không làm nghẽn vĩnh viễn scheduler |
| Nhiều tác vụ lease cùng lúc | Pool size đủ, không starve renew token |
| Shutdown Spring context | Các tài nguyên scheduler/session được giải phóng theo lifecycle |
| Dynamic secret có lease | Đăng ký lease đúng và nhận event/giá trị mới khi renew/rotate |
| KV tĩnh | Không nhầm KV với secret có lease được Vault cấp ở mỗi lần đọc |

Có thể dùng Vault thật trong môi trường kiểm thử, Vault dev container hoặc Testcontainers để kiểm tra KV/token. Các bài kiểm thử về AppRole, Kubernetes hoặc lease động phải cấu hình đúng auth backend/secrets engine để phản ánh môi trường thật. Mock `VaultTemplate` chỉ kiểm tra logic Java, **không chứng minh** scheduler đã thực sự renew được token hoặc policy của Vault đã đúng.

Bộ kiểm thử tích hợp không nên phụ thuộc thời gian chờ ngẫu nhiên hoặc root token vô thời hạn; cần kiểm soát TTL, kịch bản revoke/renew và cắt giảm flakiness do đồng hồ, network jitter.

## 12. Giám sát và vận hành an toàn

Khi triển khai service lâu dài, các tín hiệu quan trọng gồm:

- **Authentication:** tỷ lệ login thành công/thất bại, loại auth method, lỗi nhận token, số lần cần login lại.
- **Token lifecycle:** lỗi renew, token hết hạn, giới hạn TTL, các event liên quan đến authentication và session khi được framework hỗ trợ.
- **TaskScheduler:** số thread đang bận, số tác vụ bị chậm/từ chối, độ trễ renew và dấu hiệu thread pool starvation.
- **Secret lease:** số lease theo dõi, renew/rotate thất bại, lease sắp hết hạn, tác động của credential rotation lên kết nối nghiệp vụ.
- **Vault connectivity:** latency, timeout, HTTP status 4xx/5xx, lỗi TLS, Vault sealed/unavailable, hiện tượng chuyển node HA.

Không ghi **Vault token, AppRole SecretID, Kubernetes JWT, database password, private key PKI hoặc nội dung KV** vào log, metric labels, traces hay báo cáo kiểm thử. Nếu cần đối chiếu yêu cầu bị từ chối, dùng audit log Vault với quyền và chính sách lưu giữ phù hợp.

Nên có quy tắc xử lý khi gần hết TTL và renew thất bại: giới hạn retry, backoff có jitter, quan sát alert trước khi mất khả năng phục vụ, và biết trường hợp nào cần login lại. **Lỗi thiếu policy `read` sẽ không được khắc phục bởi scheduler hoặc việc tăng thread pool.**

## 13. Tự đánh giá sau bài học

1. `ClientAuthentication` và `SessionManager` khác nhau ở trách nhiệm gì?
2. Vì sao `SimpleSessionManager` không phù hợp nếu token có TTL ngắn và không có cơ chế làm mới bên ngoài?
3. `LifecycleAwareSessionManager` có thể gia hạn một token không renewable hay đã bị revoke không?
4. `AbstractVaultConfiguration` đã cung cấp những bean nào liên quan session và scheduler? Khi nào mới cần override chúng?
5. Trong Spring Vault 3.2.x, vì sao ví dụ override `threadPoolTaskScheduler()` trả về `TaskSchedulerWrapper` thay vì trả thẳng `ThreadPoolTaskScheduler`?
6. Vì sao token dùng đọc KV v2 có TTL nhưng mỗi lần đọc KV tĩnh không tự có secret lease riêng?
7. Nếu renew token chạy chậm trong giờ cao điểm, cần thu thập tín hiệu gì trước khi tăng pool size?
8. Khi dùng Kubernetes auth, credential nguồn để login lại là gì? Vì sao thay token tĩnh bằng workload auth có thể cải thiện vòng đời session?
9. Khi client được 403 từ `secret/data/orders/api`, tại sao tự đổi TaskScheduler không phải giải pháp?
10. Vì sao chỉ test startup bằng dev root token chưa đủ để chứng minh cơ chế renew/rotate hoạt động?

**Kết quả mong đợi:** bạn có thể giải thích luồng `ClientAuthentication -> SessionManager -> VaultTemplate`, biết `AbstractVaultConfiguration` mặc định cung cấp `LifecycleAwareSessionManager` và scheduler phục vụ renewal, tùy chỉnh `TaskSchedulerWrapper` khi cần, đồng thời phân biệt token lifecycle với secret lease. Nền tảng này giúp ứng dụng Java tích hợp Vault an toàn hơn khi vận hành KV, Transit encryption, PKI, workload authentication, giám sát và kiểm thử tích hợp.

### Tài liệu tham khảo chính thức

- [Spring Vault: Session Management và VaultTemplate](https://docs.spring.io/spring-vault/reference/3.2/vault/imperative-template.html)
- [Javadoc: AbstractVaultConfiguration](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/config/AbstractVaultConfiguration.html)
- [Javadoc: LifecycleAwareSessionManager](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/authentication/LifecycleAwareSessionManager.html)
- [Javadoc: AbstractVaultConfiguration.TaskSchedulerWrapper](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/config/AbstractVaultConfiguration.TaskSchedulerWrapper.html)

