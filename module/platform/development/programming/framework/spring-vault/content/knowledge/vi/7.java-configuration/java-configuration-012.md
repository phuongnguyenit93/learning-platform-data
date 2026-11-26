# Quản lý đóng client và dừng các tác vụ nền

Trong chương **Cấu hình Java** của **SPRING_VAULT**, cấu hình đúng `VaultEndpoint`, `ClientAuthentication` và `VaultTemplate` mới giải quyết được **nửa đầu** bài toán tích hợp HashiCorp Vault. Với một ứng dụng Java chạy lâu, còn cần đóng client theo trật tự, dừng những tác vụ gia hạn token/lease và giải phóng tài nguyên HTTP khi ứng dụng ngừng phục vụ.

Một lần đọc KV secret thành công không bảo đảm ứng dụng sẽ tắt sạch. Nếu scheduler còn chạy sau khi HTTP client hoặc token đã bị hủy, request renew có thể thất bại hoặc giữ luồng JVM không thoát. Ngược lại, nếu dừng token trước khi thu hồi lease của secret động, việc revoke lease có thể không còn đủ quyền để hoàn thành.

Bài này hướng dẫn **quyền sở hữu tài nguyên (resource ownership)**, các callback của Spring `ApplicationContext`, cách sử dụng `AbstractVaultConfiguration`, phân biệt `stop()` với `destroy()` của `SecretLeaseContainer`, cách đóng chương trình Java standalone và thiết kế graceful shutdown cho service. Kiến thức áp dụng trực tiếp cho KV, database dynamic secrets, token/session lifecycle, Transit encryption, PKI và kiểm thử tích hợp.

> **Phạm vi API:** Các khái niệm `VaultTemplate`, `SessionManager`, `SecretLeaseContainer` và `AbstractVaultConfiguration.TaskSchedulerWrapper` được hỗ trợ trong các nhánh Spring Vault thông dụng như 3.2 và 4.1. Các constructor liên quan `VaultClient` chỉ có từ Spring Vault 4.1. Khi chỉnh mã production, đối chiếu Javadoc của đúng phiên bản Spring Vault và Spring Framework mà dự án sử dụng.

## 1. Vì sao đóng một client Vault cần nhiều hơn “hủy object”?

Một ứng dụng đơn giản có thể gọi:

~~~java
VaultTemplate template =
        new VaultTemplate(endpoint, authentication);
~~~

Nhưng một ứng dụng production có thể còn sở hữu:

- **`SessionManager`:** giữ token phiên làm việc, đăng ký renew task và có thể quản lý revoke.
- **`TaskScheduler`:** thực thi các task nền theo lịch để gia hạn token hoặc secret lease.
- **`SecretLeaseContainer`:** theo dõi secret động, renew hoặc rotate credential và cố gắng revoke lease khi bị hủy.
- **HTTP client hoặc connection pool:** quản lý kết nối, TLS, keep-alive và các executor liên quan.
- **Các consumer nghiệp vụ:** JDBC pool, dịch vụ ký số, client Transit/PKI hoặc job nền vẫn đang dùng credential.
- **Spring `ApplicationContext`:** tạo, sở hữu và gọi lifecycle callback cho những bean đã đăng ký.

Nếu chỉ bỏ tham chiếu Java tới `VaultTemplate`, garbage collector **không thể thay** việc hủy scheduler, thu hồi lease hay đóng connection pool.

~~~mermaid
flowchart TD
    A["Ứng dụng sắp dừng"] --> B["Ngừng nhận công việc mới"]
    B --> C["Chờ request/job đang chạy trong giới hạn"]
    C --> D["Dừng đăng ký renew/rotation mới"]
    D --> E["Cleanup lease đang sở hữu khi phù hợp"]
    E --> F["Đóng session/token và scheduler"]
    F --> G["Đóng tài nguyên HTTP có chủ sở hữu"]
    G --> H["Process kết thúc"]
~~~

Đây là **thứ tự mục tiêu**: thứ tự thực tế phụ thuộc dependency graph và vòng đời bean. Không tự hủy thủ công mọi bean nếu Spring đã quản lý chúng; cũng không giả định shutdown luôn hoàn thành khi Vault đang unavailable.

## 2. Phân biệt stop, destroy, revoke và close

Những từ này thường xuất hiện cùng nhau nhưng không mang nghĩa tương đương.

| Thao tác | Đối tượng/đích | Hệ quả chính | Điều không được ngầm suy ra |
| --- | --- | --- | --- |
| `stop()` | `SmartLifecycle`, `SecretLeaseContainer` | Dừng công việc và sự kiện theo lịch của component | **Không tự revoke** các lease đang hoạt động |
| `destroy()` | `DisposableBean` | Callback giải phóng tài nguyên mà bean sở hữu | Không có nghĩa mọi secret/token ngoài Vault đều bị xóa |
| `shutdown()` | Scheduler/executor | Ngăn nhận task mới, giải phóng thread theo chính sách | Không tương đương revoke Vault token |
| Token revoke | Vault token API hoặc session manager phù hợp | Làm token không còn được dùng để gọi API | Không phải cách xóa một KV secret |
| Lease revoke | Vault lease API | Hủy/thu hồi credential động theo engine | Không áp dụng cho mỗi lần đọc KV tĩnh |
| HTTP client close | Connection manager/HTTP stack | Giải phóng connection, executor, socket do client sở hữu | Không tự làm token hết hiệu lực |
| Context `close()` | Spring `ConfigurableApplicationContext` | Kích hoạt stop/destroy bean được quản lý | Không bảo đảm mọi remote cleanup thành công nếu mạng mất |

**Quy tắc quan trọng nhất:** component nào tạo và sở hữu một tài nguyên thì component đó phải chịu trách nhiệm dọn dẹp, **trừ khi** quyền sở hữu đã được chuyển giao rõ ràng cho Spring hoặc hạ tầng khác.

### Một lỗi thiết kế điển hình

Giả sử ứng dụng tự tạo một `ThreadPoolTaskScheduler` rồi đưa nó cho ba bean khác. Nếu một bean gọi `scheduler.shutdown()` khi nó dừng, hai bean còn lại có thể bị `RejectedExecutionException` khi muốn đặt lịch. Điều đúng là chỉ **chủ sở hữu scheduler** được quyền đóng nó, và các client sử dụng phải dừng việc lên lịch trước đó.

## 3. Ai sở hữu tài nguyên trong Spring Vault?

| Thành phần | Spring quản lý như bean? | Khi đóng có thể xảy ra gì? | Lưu ý |
| --- | --- | --- | --- |
| `VaultTemplate` | Có, nếu khai báo `@Bean`/auto-config | Spring gọi `DisposableBean.destroy()` | Không gọi thêm thủ công trên cùng bean |
| `LifecycleAwareSessionManager` | Có, nếu là bean | Hủy phiên, dừng refresh; có thể revoke **LoginToken** do nó quản lý | Không mặc định revoke `VaultToken` tĩnh |
| `SimpleSessionManager` | Có thể | Không có cơ chế renew nền của lifecycle manager | Đừng nhầm với login manager |
| `SecretLeaseContainer` | Có, nếu đăng ký bean | Spring xử lý `SmartLifecycle` và `DisposableBean`; `destroy()` cố gắng revoke lease được quản lý | `stop()` **không** revoke |
| `ThreadPoolTaskScheduler` | Có thể | Đóng worker threads theo lifecycle/config | Scheduler có thể được chia sẻ |
| `TaskSchedulerWrapper` | Có, trong `AbstractVaultConfiguration` | Bọc scheduler của Spring Vault và thực thi callbacks theo ownership | `fromInstance(...)` không sở hữu lifecycle của scheduler bên ngoài |
| HTTP client/connection manager | Tùy cách tạo | Chỉ tự đóng nếu có owner/callback tương ứng | Kiểm tra API cụ thể và bean destruction |
| `VaultEndpoint` | Có hoặc không | Chủ yếu chứa cấu hình kết nối | Không phải network connection đang mở |

Theo Javadoc của Spring Vault, `VaultTemplate` triển khai cả `InitializingBean` và `DisposableBean`. `LifecycleAwareSessionManager` cũng có `destroy()`, còn `SecretLeaseContainer` triển khai `SmartLifecycle` và `DisposableBean`. Vì thế, nên để `ApplicationContext` thực hiện callbacks cho những đối tượng **được khai báo là bean**.

### Token tĩnh và LoginToken khác nhau

- `TokenAuthentication` cung cấp một `VaultToken` có sẵn. Token này **không mặc nhiên bị revoke** chỉ vì ứng dụng kết thúc; nhiều trường hợp nó thuộc sở hữu của Vault Agent, hệ thống triển khai hoặc một quy trình cấp token khác.
- Auth method tạo token mới khi login thường trả `LoginToken` có metadata TTL. `LifecycleAwareSessionManager` có thể gia hạn và cố gắng revoke `LoginToken` do phiên quản lý khi shutdown, theo contract và khả năng của Vault.
- Một token đã hết hạn hoặc bị revoke từ bên ngoài không thể renew chỉ bằng cách gọi shutdown lại. Việc cleanup network thất bại phải được giám sát và có phương án xử lý phía Vault.

**Không biến một lỗi dọn dẹp thành lý do ghi token/SecretID vào log.** Chỉ log loại operation, nhóm lỗi và metadata không nhạy cảm.

## 4. Dùng AbstractVaultConfiguration để Spring quản lý lifecycle

Khi dự án sử dụng `AbstractVaultConfiguration`, bạn triển khai hai phương thức bắt buộc:

- `vaultEndpoint()` trả địa chỉ Vault.
- `clientAuthentication()` trả cơ chế xác thực.

Phần cơ sở có thể cung cấp những bean như `VaultTemplate`, `SessionManager`, `SecretLeaseContainer` và scheduler riêng cho Vault. Trong các phiên bản hiện hành, `sessionManager()` mặc định tạo `LifecycleAwareSessionManager`, còn `threadPoolTaskScheduler()` trả về `TaskSchedulerWrapper`.

### 4.1. Cấu hình Java có scheduler riêng

Ví dụ dành cho Spring Boot, Java 17 trở lên. Tạo `VaultLifecycleConfiguration.java`:

~~~java
package com.example.vault;

import java.net.URI;

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
public class VaultLifecycleConfiguration extends AbstractVaultConfiguration {

    private final Environment environment;

    public VaultLifecycleConfiguration(Environment environment) {
        this.environment = environment;
    }

    @Override
    public VaultEndpoint vaultEndpoint() {
        URI uri = URI.create(
                environment.getRequiredProperty("app.vault.uri"));
        String scheme = uri.getScheme();

        if (uri.getHost() == null
                || (!"http".equalsIgnoreCase(scheme)
                    && !"https".equalsIgnoreCase(scheme))
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || (uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty()
                    && !"/".equals(uri.getRawPath()))) {
            throw new IllegalArgumentException(
                    "app.vault.uri phải là base URL Vault hợp lệ");
        }

        return VaultEndpoint.from(uri);
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String token = environment.getRequiredProperty("app.vault.token");
        if (token.isBlank()) {
            throw new IllegalArgumentException(
                    "app.vault.token không được để trống");
        }

        // Dùng token demo để học. Production nên ưu tiên workload auth.
        return new TokenAuthentication(token);
    }

    @Override
    @Bean("vaultThreadPoolTaskScheduler")
    public TaskSchedulerWrapper threadPoolTaskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("vault-lifecycle-");
        scheduler.setRemoveOnCancelPolicy(true);

        // Hạn chế chạy các renew task còn trong queue khi đang tắt.
        scheduler.setWaitForTasksToCompleteOnShutdown(false);
        scheduler.setAwaitTerminationSeconds(5);

        // Wrapper sở hữu lifecycle của scheduler mới này.
        return new TaskSchedulerWrapper(scheduler);
    }
}
~~~

**Ý nghĩa:**

1. `VaultEndpoint` và `ClientAuthentication` được Spring gọi trong lúc dựng hạ tầng Vault; chúng không bị đọc lại theo mỗi request KV.
2. `AbstractVaultConfiguration` đăng ký `VaultTemplate` và session manager, tránh phải định nghĩa thêm `@Bean VaultTemplate` có thể gây trùng bean.
3. Scheduler dành cho Vault có tên bean **`vaultThreadPoolTaskScheduler`**. Override đúng phương thức của lớp cơ sở để session/lease manager sử dụng nó.
4. `TaskSchedulerWrapper` thực hiện callback tạo/destroy của `ThreadPoolTaskScheduler` bên trong. **Không gọi `scheduler.initialize()` và `scheduler.shutdown()` thủ công** trong bean factory này.
5. `setWaitForTasksToCompleteOnShutdown(false)` giúp tránh tiếp tục xử lý các tác vụ định kỳ cũ sau khi ứng dụng đã chủ động dừng. `setAwaitTerminationSeconds(5)` là giới hạn minh họa; phải kiểm tra hành vi thực tế với Spring Framework version và thời gian xử lý.
6. Token lab nhận từ `app.vault.token` không phải danh tính production; không suy ra từ cấu hình này rằng token sẽ luôn được renew hoặc tự login lại.

Không cần override scheduler nếu mặc định đã đáp ứng yêu cầu. Việc tùy chỉnh thread pool phải dựa trên số lease, tần suất renew và thời gian phản hồi Vault, không chỉ tăng thread để che lỗi policy.

### 4.2. Property theo môi trường

`src/main/resources/application.yml`:

~~~yaml
app:
  vault:
    uri: ${VAULT_ADDR}
    token: ${VAULT_TOKEN}
~~~

`src/main/resources/application-local.yml`:

~~~yaml
app:
  vault:
    uri: ${VAULT_ADDR:http://127.0.0.1:8200}
~~~

Các khóa `app.vault.*` là **quy ước của ví dụ này**, không phải thuộc tính tiêu chuẩn của `EnvironmentVaultConfiguration`. Ở môi trường khác phải cấp `VAULT_ADDR` chính xác và dùng HTTPS với certificate/trust store hợp lệ; không để fallback HTTP production.

## 5. Khi nào Spring đóng các bean?

Trong một ứng dụng Spring Boot web chạy dưới container, thông thường khi process nhận tín hiệu dừng có kiểm soát, ứng dụng bắt đầu graceful shutdown và Spring đóng `ApplicationContext`. Đối với ứng dụng non-web, bạn cũng có thể chủ động đóng context hoặc đăng ký shutdown hook.

Những cơ chế liên quan:

| API Spring | Thời điểm | Chức năng |
| --- | --- | --- |
| `InitializingBean.afterPropertiesSet()` | Sau khi property của bean được thiết lập | Chuẩn bị tài nguyên, trạng thái |
| `SmartLifecycle.start()` | Giai đoạn context refresh/start | Bắt đầu các component auto-start như lease tracking |
| `SmartLifecycle.stop(...)` | Giai đoạn stop context | Ngừng công việc đang diễn ra theo phase |
| `DisposableBean.destroy()` | Khi hủy bean | Giải phóng/revoke tài nguyên do bean sở hữu |
| `@PreDestroy` | Trước khi bean bị hủy | Hook cleanup do ứng dụng định nghĩa |
| `@Bean(destroyMethod="...")` | Khi đóng context | Chỉ rõ phương thức đóng cho một bean |
| `@DependsOn` | Khi init và destroy singleton | Bean phụ thuộc được hủy **trước** bean mà nó phụ thuộc |

Với `@DependsOn("vaultSessionManager")`, chẳng hạn, bean consumer được yêu cầu khởi tạo sau dependency và bị destroy trước dependency. Đây là cách hỗ trợ quản lý thứ tự khi dependency không thể hiện được qua constructor injection; cần dùng **đúng bean name thực tế**. Không coi mọi thứ tự shutdown giữa những bean không liên quan là được Spring bảo đảm.

### Hai giai đoạn cần phân biệt

- **Stop phase**: ngừng các component `SmartLifecycle`, thường được thực hiện trước khi hủy singleton.
- **Destroy phase**: gọi `@PreDestroy`/`DisposableBean.destroy()` và giải phóng tài nguyên.

Một bean có thể cần hoạt động HTTP trong destroy phase để revoke lease; vì vậy phải tránh đóng session hoặc HTTP client cần thiết **quá sớm**. Đặc biệt khi có nhiều `VaultTemplate`, xác định đúng dependency và owner cho từng cụm Vault.

## 6. SecretLeaseContainer: stop() khác destroy() chính xác ra sao?

`SecretLeaseContainer` là ví dụ rõ nhất về khác biệt này:

- `start()`: bắt đầu lấy secret đã đăng ký và xử lý lease/events.
- `stop()`: dừng renew, rotation và phát hành event; **các lease đang hoạt động không bị đánh dấu hết hạn/không bị revoke chỉ bởi stop**.
- `destroy()`: tắt container và **cố gắng revoke các lease mà nó quản lý** theo API/contract của Spring Vault.

Bảng minh họa:

| Trước shutdown | Sau `stop()` | Sau `destroy()` thành công |
| --- | --- | --- |
| Secret động còn TTL | Lease vẫn có thể còn hiệu lực tại Vault | Lease được yêu cầu revoke và credential có thể mất hiệu lực |
| Task renew đã được đặt lịch | Không tiếp tục renew/rotate theo container | Container bị hủy, không thể restart |
| Listener lease | Ngừng event publishing theo lifecycle | Cleanup container |
| Token dùng để gọi Vault | Không đổi chỉ do stop | Phụ thuộc session manager và thứ tự hủy, **không đồng nghĩa revoke mọi token** |

**Không gộp `stop()` và `destroy()` thành một hành động.** Khi dùng `ApplicationContext`, Spring thường gọi stop trong lifecycle phase và gọi destroy khi hủy bean. Với standalone, nếu chỉ gọi `stop()` rồi thoát, ứng dụng **không thực hiện yêu cầu revoke lease** của `destroy()`.

### Cleanup lease có thể thất bại

Gọi `destroy()` là một **nỗ lực gửi revoke request**, không phải bảo đảm tuyệt đối rằng mọi credential tại Vault đã mất hiệu lực. Ví dụ: Vault sealed, network timeout, token đã bị revoke hoặc workload bị kill đột ngột. Vì vậy, thiết kế vẫn cần TTL giới hạn, policy ít quyền, quan sát lỗi cleanup và quy trình xử lý sự cố.

## 7. Đăng ký secret động trước khi container tự khởi động

`AbstractVaultConfiguration` đã có thể cung cấp bean `SecretLeaseContainer`. **Có container không có nghĩa nó tự quét tất cả secrets engine**. Ứng dụng hoặc integration phải đăng ký đường dẫn muốn theo dõi.

Ví dụ dành cho một môi trường thử nghiệm **đã bật database secrets engine** tại `database/creds/orders-reader`. Có thể đăng ký một secret động trước giai đoạn tự khởi động của `SmartLifecycle`:

~~~java
package com.example.vault;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.vault.core.lease.SecretLeaseContainer;

@Configuration(proxyBeanMethods = false)
@Profile("dynamic-lease-demo")
public class LeaseRegistrationConfiguration {

    @Bean
    SmartInitializingSingleton registerOrdersLease(
            SecretLeaseContainer leaseContainer) {

        return () -> leaseContainer.requestRotatingSecret(
                "database/creds/orders-reader");
    }
}
~~~

`SmartInitializingSingleton` được gọi khi những singleton thông thường đã tạo xong, trước giai đoạn `SmartLifecycle` auto-start của context. Nhờ vậy, secret được đăng ký trước khi container bắt đầu cấp credential. **Chỉ bật profile này trong môi trường đã cấu hình engine và policy thật**; nếu không, container có thể thất bại khi lấy secret.

Khi shutdown:
1. Ứng dụng dừng nhận công việc mới và dừng những consumer dùng credential.
2. Spring dừng các lifecycle components.
3. `SecretLeaseContainer.destroy()` cố gắng revoke những lease được quản lý.
4. Session/token và scheduler/HTTP resources cần còn khả dụng đúng lúc cleanup thực hiện.

Ví dụ không tự cài đặt JDBC connection pool rotation. Trong hệ thống thật, nhận credential mới từ lease event còn phải áp vào kết nối nghiệp vụ, và phải chấm dứt việc dùng credential cũ một cách có kiểm soát.

### KV và Transit không tạo lease theo cùng cách

- Đọc `secret/demo/app` từ **KV v2 tĩnh** thường không tạo secret lease riêng.
- Gọi Transit encryption bằng token `transit/encrypt/...` là thao tác API theo policy; không tự sinh database credential lease.
- Chứng chỉ PKI có hiệu lực và cơ chế revoke/rotation riêng; từ các phiên bản mới, Spring Vault còn có những abstraction quản lý certificate chuyên biệt. Không mặc định đưa mọi chứng chỉ vào một `SecretLeaseContainer` giống dynamic database credential.

## 8. Tránh đóng scheduler trước khi xử lý lease và token

Một quy tắc shutdown có chủ đích:

~~~mermaid
sequenceDiagram
    participant App as App/Ingress
    participant Lease as SecretLeaseContainer
    participant Session as SessionManager
    participant HTTP as Vault HTTP client
    participant Scheduler as TaskScheduler
    participant Vault as Vault Server

    App->>App: Ngừng nhận request/job mới, drain
    App->>Lease: stop()
    Note over Lease: Ngừng renew và rotation
    App->>Lease: destroy()
    Lease->>Session: Lấy token cho revoke nếu cần
    Lease->>Vault: Revoke các lease đã quản lý
    App->>Session: destroy()/đóng theo ownership
    App->>Scheduler: shutdown()
    App->>HTTP: close nếu là owner
~~~

Sơ đồ mô tả mục tiêu **thứ tự tài nguyên**, không chỉ thị gọi trực tiếp `destroy()` trên một bean mà Spring đang sở hữu. Với Spring context, dependency graph, `SmartLifecycle` phases và các callback được cấu hình phải tạo ra kết quả tương đương.

**Vì sao lease trước session?** Revoke lease cần request đã xác thực tới Vault. Nếu session đã bỏ token hoặc HTTP client đã đóng, revoke có thể bị từ chối. Tuy nhiên, với token/lease do hệ thống bên ngoài quản lý, trách nhiệm revoke có thể nằm ngoài Java process; không tự thu hồi một token dùng chung của nhiều consumer chỉ vì một app dừng.

### @DependsOn để kiểm soát hủy bean khi tự cấu hình

Khi tự tạo các bean độc lập, có thể thể hiện mối quan hệ:

~~~java
@Bean("ordersLeaseContainer")
@DependsOn({"ordersSessionManager", "ordersScheduler"})
SecretLeaseContainer ordersLeaseContainer(
        @Qualifier("ordersVaultTemplate") VaultTemplate template,
        @Qualifier("ordersScheduler") TaskScheduler scheduler) {

    SecretLeaseContainer container =
            new SecretLeaseContainer(template, scheduler);
    container.requestRotatingSecret("database/creds/orders-reader");
    return container;
}
~~~

Ví dụ này **chỉ là đoạn method trong một `@Configuration` được tự thiết kế**, giả định đã có các bean `ordersSessionManager`, `ordersScheduler`, `ordersVaultTemplate`, và các import `Bean`, `DependsOn`, `Qualifier`, `TaskScheduler`, `VaultTemplate`, `SecretLeaseContainer`. Nó **không được ghép đồng thời** với bean `secretLeaseContainer()` mặc định mà không kiểm soát tên và trách nhiệm.

Khi `ordersLeaseContainer` phụ thuộc vào session/scheduler singleton, Spring sẽ hủy container **trước** những dependency này. Nếu tự tạo một HTTP connection manager, bạn cũng phải làm rõ quan hệ destroy để nó không đóng sớm. `@DependsOn` không thay thế việc xác định connection ownership, timeout và cancellation.

## 9. Cấu hình scheduler có chủ sở hữu và timeout rõ ràng

Trong Spring Vault, một `TaskScheduler` có thể chạy token renew và secret lease renew trên background threads. `ThreadPoolTaskScheduler` có một số thiết lập quan trọng:

| Cấu hình | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `setPoolSize(n)` | Số worker threads | Không tự giải quyết lỗi 403/TTL |
| `setThreadNamePrefix(...)` | Nhận diện luồng của Vault trong thread dump | Dùng tên không nhạy cảm |
| `setRemoveOnCancelPolicy(true)` | Giảm giữ tác vụ đã bị hủy trong queue | Hữu ích khi nhiều task renew bị cancel |
| `setWaitForTasksToCompleteOnShutdown(false)` | Không cố chạy hết queued renew tasks khi shutdown | Phù hợp khi consumer đã ngừng hoạt động |
| `setAwaitTerminationSeconds(n)` | Giới hạn khoảng đợi executor kết thúc | Cần đối chiếu termination grace của nền tảng |
| `TaskSchedulerWrapper.fromInstance(...)` | Reuse scheduler Spring bean có sẵn | Wrapper không khởi tạo/hủy scheduler bên ngoài |

Đừng bật `setWaitForTasksToCompleteOnShutdown(true)` chỉ với mục tiêu “graceful hơn”. Với task định kỳ hoặc nhiệm vụ renew không còn cần thiết, điều này có thể kéo dài quá trình shutdown hoặc cho phép task gọi HTTP sau khi client bắt đầu đóng.

Nếu ứng dụng dùng chung scheduler cho tác vụ nghiệp vụ và Vault, một batch job chạy lâu có thể chiếm hết thread, làm token/lease renew đến muộn. Đối với service cần độ tin cậy cao, scheduler riêng cho Vault thường dễ giám sát và cô lập hơn.

### Reuse scheduler đã có

Khi `ThreadPoolTaskScheduler` được định nghĩa là bean độc lập, có thể trả:

~~~java
return TaskSchedulerWrapper.fromInstance(existingScheduler);
~~~

ở phương thức override `threadPoolTaskScheduler()` của `AbstractVaultConfiguration`. `existingScheduler` phải là scheduler **đã được Spring quản lý** và có owner chịu trách nhiệm init/shutdown. Wrapper `fromInstance(...)` sẽ không gọi lifecycle trên scheduler được mượn. Không vừa gọi `shutdown()` ở owner vừa gọi lại thủ công ở tất cả consumer.

## 10. Thực hành cơ bản: đọc KV v2 và đóng context đúng cách

### 10.1. Khởi động Vault dev

Terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=dev-only-token
~~~

Terminal thứ hai (Bash):

~~~bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=dev-only-token
export SPRING_PROFILES_ACTIVE=local

vault kv put secret/demo/app apiKey=demo-value
~~~

Với PowerShell:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "dev-only-token"
$env:SPRING_PROFILES_ACTIVE = "local"

vault kv put secret/demo/app apiKey=demo-value
~~~

Dev server thông thường gắn KV v2 tại mount `secret`. Kiểm tra bằng `vault secrets list -detailed` nếu cấu hình đã được thay đổi. Root token và HTTP localhost ở đây **chỉ dành cho lab**, không dùng cho production.

### 10.2. Service đọc secret

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

    public boolean canReadApiKey() {
        VaultResponse response = vault
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("demo/app");

        Map<String, Object> data =
                response == null ? null : response.getData();

        return data != null
                && data.get("apiKey") instanceof String key
                && !key.isBlank();
    }
}
~~~

`VaultTemplate` do `AbstractVaultConfiguration` đăng ký triển khai `VaultOperations`. Với KV v2, `secret` là mount còn `demo/app` là đường dẫn tương đối trong mount. API đọc tương ứng là `GET /v1/secret/data/demo/app`.

Trong class `@SpringBootApplication`, có thể xác nhận:

~~~java
@Bean
CommandLineRunner checkVault(DemoSecretReader reader) {
    return args -> {
        if (!reader.canReadApiKey()) {
            throw new IllegalStateException("Không có apiKey mẫu");
        }
        System.out.println("Đọc KV v2 thành công");
    };
}
~~~

Method trên cần import `org.springframework.boot.CommandLineRunner` và `org.springframework.context.annotation.Bean`. **Không in nội dung `apiKey` hoặc token**. Ví dụ này không đăng ký secret động, nên không có lease riêng cần revoke từ lần đọc KV.

### 10.3. Đóng Spring context của một job Java non-web

Trong một ứng dụng Spring Boot chạy như command-line job, nếu tự mở context và muốn kết thúc ngay sau tác vụ, có thể dùng:

~~~java
package com.example.vault;

import org.springframework.boot.SpringApplication;
import org.springframework.context.ConfigurableApplicationContext;

public final class VaultJobMain {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(VaultJobApplication.class, args)) {

            DemoSecretReader reader =
                    context.getBean(DemoSecretReader.class);

            if (!reader.canReadApiKey()) {
                throw new IllegalStateException("Secret không hợp lệ");
            }

            System.out.println("Hoàn tất Vault job");
        } // context.close() chạy ở đây.
    }
}
~~~

Ví dụ giả định có class cấu hình `VaultJobApplication` được đánh dấu `@SpringBootApplication`/`@Import` phù hợp, và project đã có dependency Spring Boot. Không nên ghép đoạn này với `CommandLineRunner` tự động kiểm tra thêm nếu không có nhu cầu chạy hai lần.

`try-with-resources` kích hoạt `ConfigurableApplicationContext.close()` cả khi job ném exception thông thường. Spring sẽ thực hiện các bước stop/destroy của bean được quản lý. **Không gọi `destroy()` thêm một lần trên `VaultTemplate` hoặc `SecretLeaseContainer` đã thuộc context.**

Với long-running web service, không tự đóng context sau một request. Spring Boot và cơ chế dừng process/container quản lý quá trình này.

## 11. Java standalone: đóng VaultTemplate trong finally

Spring Vault dùng được **ngoài `ApplicationContext`**. Khi đó, chương trình phải tự khởi tạo và hủy những đối tượng mình sở hữu.

Ví dụ CLI nhỏ chỉ đọc KV v2 bằng một token đã có:

~~~java
package com.example.vault;

import java.net.URI;
import java.util.Map;

import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

public final class StandaloneVaultJob {

    public static void main(String[] args) throws Exception {
        String address = requireEnv("VAULT_ADDR");
        String token = requireEnv("VAULT_TOKEN");

        URI uri = URI.create(address);
        if (uri.getHost() == null
                || (!"http".equalsIgnoreCase(uri.getScheme())
                    && !"https".equalsIgnoreCase(uri.getScheme()))) {
            throw new IllegalArgumentException("VAULT_ADDR không hợp lệ");
        }

        VaultTemplate template = new VaultTemplate(
                VaultEndpoint.from(uri),
                new TokenAuthentication(token));

        try {
            template.afterPropertiesSet(); // Không có Spring container gọi hộ.

            VaultResponse response = template
                    .opsForKeyValue("secret", KeyValueBackend.KV_2)
                    .get("demo/app");

            Map<String, Object> data =
                    response == null ? null : response.getData();

            if (data == null || data.get("apiKey") == null) {
                throw new IllegalStateException("Secret không có apiKey");
            }
            System.out.println("Standalone Vault job hoàn tất");
        } finally {
            template.destroy();
        }
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Thiếu biến môi trường " + name);
        }
        return value;
    }
}
~~~

Lưu ý:
- `afterPropertiesSet()`/`destroy()` là callback của `VaultTemplate`; trong standalone, caller phải quyết định cách gọi hợp lý.
- Constructor `VaultTemplate(VaultEndpoint, ClientAuthentication)` thích hợp với ví dụ đơn giản; không biến token tĩnh thành token có thể tự login lại.
- `destroy()` có thể ném exception khi cleanup; chương trình nên báo lỗi thích hợp cho job runner, nhưng không đưa token hay response secret vào log.
- Nếu sau này bạn tự thêm HTTP connection pool, `SessionManager` hoặc scheduler riêng, **hủy template thôi chưa chắc đóng mọi resource bên ngoài**.
- Phần validation demo chỉ kiểm tra scheme/host. Production cần kiểm tra base URI chặt chẽ, HTTPS/CA/hostname và timeout.

### Nếu chương trình standalone có SecretLeaseContainer riêng

Đây là **mẫu thứ tự**, chỉ áp dụng nếu đã có dynamic secrets engine thực tế và các resource được tạo bởi chương trình. Không nên chạy nguyên mẫu này với KV v2 tĩnh:

~~~java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(2);
try {
    scheduler.initialize();

    VaultTemplate template = new VaultTemplate(endpoint, authentication);
    try {
        template.afterPropertiesSet();

        SecretLeaseContainer leases =
                new SecretLeaseContainer(template, scheduler);
        try {
            leases.afterPropertiesSet();
            leases.requestRotatingSecret("database/creds/orders-reader");
            leases.start();

            // Thực hiện nghiệp vụ với credential động.
        } finally {
            leases.destroy(); // Cố gắng revoke lease trước.
        }
    } finally {
        template.destroy(); // Hủy client/session khi còn hợp lệ.
    }
} finally {
    scheduler.shutdown(); // Chỉ owner đóng scheduler.
}
~~~

Đoạn trên là snippet thuộc một phương thức có `throws Exception`, với các biến `endpoint`/`authentication` và import đã chuẩn bị. Các khối `try/finally` bao lấy từng resource đã tạo: nếu `afterPropertiesSet()` hoặc `start()` thất bại, template và scheduler vẫn được dọn dẹp theo ownership. Nếu thao tác `destroy()` của lease thất bại, các `finally` bên ngoài vẫn chạy. Đây không phải utility hoàn chỉnh có thể chạy trên mọi môi trường: cần dynamic secrets engine thật, auth/policy đúng và timeout có giới hạn.

Trong standalone, chỉ caller mới biết được scheduler/HTTP pool có đang được dùng chung với tác vụ khác không. Không đóng resource “mượn” từ một hệ thống bên ngoài.

## 12. Graceful shutdown trong Spring Boot và Kubernetes

Trong web service, shutdown có hai việc khác nhau:
1. **Ngừng nhận yêu cầu mới và xử lý hết việc đang chạy trong một thời hạn**.
2. **Đóng các bean Vault và tài nguyên nền**.

Spring Boot có thể cấu hình graceful shutdown của web server và timeout cho các lifecycle phases:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Đây là ví dụ thời hạn, không phải mức mặc định phù hợp mọi môi trường. Đảm bảo thời gian shutdown của nền tảng triển khai **lớn hơn hoặc tương ứng** với tổng thời gian drain công việc và cleanup được cho phép.

Nếu chạy trên Kubernetes:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
~~~

Đoạn YAML chỉ minh họa một phần Pod specification, không phải manifest đầy đủ. Khi Pod bị xóa, Kubernetes có cơ chế gửi tín hiệu dừng và thời hạn chấm dứt. Readiness và routing phải được điều phối để tránh tiếp tục đưa request mới vào Pod đang dừng; không suy ra chỉ đặt `terminationGracePeriodSeconds` sẽ bảo đảm đã drain xong.

### Điều gì có thể xảy ra khi grace period quá ngắn?

- Spring bắt đầu dừng, nhưng `SecretLeaseContainer.destroy()` còn đang liên hệ Vault.
- Container runtime buộc kết thúc process trước khi revoke request hoàn tất.
- Lease vẫn có thể còn hiệu lực đến TTL hoặc cho tới khi bị thu hồi theo quy trình phía Vault.
- Nếu scheduler/HTTP resources bị đóng không đúng thứ tự, lỗi cleanup xuất hiện ngay cả khi grace period vẫn còn.

Không để shutdown treo vô hạn vì Vault unreachable; sử dụng network timeout, task cancellation và giám sát cleanup failure. Không coi `SIGKILL` hay mất điện là tình huống có thể bảo đảm callback `@PreDestroy` chạy.

## 13. Xử lý ngoại lệ khi dừng: tránh che lỗi hoặc lộ secret

| Triệu chứng lúc shutdown | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| JVM không thoát sau khi context đóng | Thread scheduler/HTTP pool do ứng dụng tự tạo chưa được hủy | Kiểm tra owner, thread dump, executor lifecycle |
| `RejectedExecutionException` | Renew task được đặt lịch sau khi scheduler đã shutdown | Dừng consumer/lease/session đúng trước scheduler |
| Revoke lease nhận 403 | Token đã hết hạn/bị thu hồi hoặc không đủ quyền | Giữ session còn dùng được lúc cleanup; kiểm tra policy |
| Revoke lease timeout | Vault unavailable, network/DNS/TLS lỗi | Giới hạn timeout, alert, xử lý lease phía Vault nếu cần |
| Token vẫn dùng được sau khi app dừng | Token tĩnh `VaultToken` do hệ thống ngoài quản lý | Không mong chờ tự revoke; dùng TTL và quy trình quản trị |
| Database pool lỗi sau rotation | App đang dùng credential cũ trong connection hiện có | Thiết kế sự kiện rotate và drain connection pool |
| Thread nền chạy sau đóng context | TaskScheduler không được Spring sở hữu hoặc shutdown policy không phù hợp | Đăng ký bean đúng, kiểm tra scheduler riêng |
| `stop()` chạy nhưng lease còn hiệu lực | `stop()` không tương đương `destroy()` | Kiểm tra destroy callback và quyền revoke |
| Nhiều client Vault cùng bị ảnh hưởng | Dùng chung session/token/scheduler không có ownership | Tách identity/session và quyết định shared pool rõ |
| Lỗi trong một callback làm thiếu cleanup khác | Cleanup viết tuần tự, không dùng `finally` | Dùng try/finally theo resource ownership, không nuốt lỗi quan trọng |

**Logging an toàn:** có thể ghi tên logical client (ví dụ `orders`), loại sự kiện `lease-revoke-failed`, HTTP status và latency. Không ghi Vault token, AppRole SecretID, Kubernetes JWT, private key PKI, secret KV, hoặc toàn bộ body lỗi chưa được làm sạch.

### Không tự động retry vô hạn trong shutdown

Nếu Vault unavailable, retry mãi có thể khiến process bị kill trước khi chạy những callback khác. Nên có **deadline toàn cục** cho shutdown, HTTP timeout hữu hạn, backoff/circuit breaker phù hợp và cơ chế cảnh báo nếu một lease chưa revoke được. Với dynamic secrets, thiết kế TTL/lease policy để hạn chế ảnh hưởng ngay cả khi ứng dụng chết đột ngột.

## 14. Kiểm thử lifecycle và dọn dẹp

**STEP 4** chỉ soạn nội dung. Khi triển khai thật, cần có bài kiểm thử tại STEP kiểm thử/tích hợp của dự án để xác nhận hành vi cleanup, thay vì chỉ kiểm tra khởi động Spring.

Ma trận kiểm thử gợi ý:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| `AbstractVaultConfiguration` được import | Có `VaultTemplate`, session manager, lease container và scheduler bean |
| Spring context đóng bình thường | Callback destroy chạy; scheduler kết thúc theo cấu hình |
| Có dynamic secret được đăng ký | `SecretLeaseContainer.start()` lấy secret; có event theo thiết kế |
| Gọi `stop()` của container | Không còn renew/rotation, **lease chưa bị revoke chỉ vì stop** |
| Gọi `destroy()` và Vault còn reachable | Có revoke request đối với lease thuộc sở hữu của container |
| Vault unavailable lúc destroy | Lỗi được ghi nhận; process không đợi vô hạn |
| Token login có thể revoke | Session manager thực hiện revoke theo contract |
| Token tĩnh không thuộc ownership của app | Không mong đợi session manager tự revoke nó |
| Scheduler bị đóng sớm | Test bắt được rejected task/cleanup lỗi, sửa lại thứ tự |
| Hai Vault clients riêng | Shutdown client A không làm đóng resource B khi B vẫn dùng |
| Chạy standalone rồi thoát | Không còn thread nền/connection pool do job sở hữu |
| App bị kill cưỡng bức | Không giả định `finally` hoặc bean destroy đã chạy |
| Đọc KV tĩnh | Không có secret lease dynamic chỉ do phép đọc |
| PKI/Transit workflow | Tài nguyên/certificate/operation có policy và lifecycle tương ứng |

### 14.1. Test cấu hình Spring bằng ApplicationContextRunner

Khi dùng `spring-boot-test`, có thể tạo context chỉ để kiểm tra bean và cleanup:

~~~java
package com.example.vault;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.vault.core.VaultTemplate;

import static org.assertj.core.api.Assertions.assertThat;

class VaultLifecycleConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            VaultLifecycleConfiguration.class);

    @Test
    void createsVaultInfrastructure() {
        runner.withPropertyValues(
                "app.vault.uri=http://127.0.0.1:8200",
                "app.vault.token=unit-test-token")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(VaultTemplate.class);
                    assertThat(context)
                            .hasBean("vaultThreadPoolTaskScheduler");
                });
        // ApplicationContextRunner đóng context sau callback.
    }
}
~~~

Ví dụ dùng JUnit Jupiter, AssertJ và `spring-boot-test`. Nó kiểm tra wiring/đóng context theo `ApplicationContextRunner`, **không chứng minh** revoke token/lease với Vault thật; đặc biệt khi auth và lookup có thể phát request HTTP ngay lúc bean initialization. Tùy phiên bản/session manager, test cần Vault test instance hoặc mock phù hợp nếu bean buộc login sớm.

### 14.2. Integration test nên dùng Vault thật

Một test tích hợp có giá trị phải tạo **dynamic secret có lease** trên Vault test server:

1. Bật secrets engine động trong môi trường test cô lập, đặt TTL ngắn nhưng ổn định.
2. Cấu hình role/token với quyền nhận và revoke secret phù hợp.
3. Bật `SecretLeaseContainer` và đăng ký requested secret.
4. Xác minh container nhận lease và có renewal/rotation theo thiết kế.
5. Dừng container bằng `stop()`, xác minh lease không bị revoke chỉ bởi hành động dừng.
6. Gọi `destroy()` khi Vault reachable, kiểm tra revoke/credential invalidation.
7. Đóng context và xác nhận không có thread scheduler bị giữ lại.
8. Lặp tình huống Vault unavailable và kiểm tra giới hạn thời gian shutdown/alert.

Không nên dùng dev root token vô hạn để kết luận session manager đã renew/revoke token đúng. Token test cần có TTL/policy tương đương workload thực tế.

## 15. Giám sát shutdown trong production

Những chỉ số đáng quan sát:

- `vault_shutdown_duration`: thời gian từ lúc stop nhận request đến khi context đóng.
- `vault_token_renew_failures` và `vault_lease_renew_failures`: lỗi tác vụ nền.
- `vault_lease_revoke_attempts`, `vault_lease_revoke_failures`: mức độ hoàn thành cleanup.
- `vault_background_tasks_active`: số task/thread còn hoạt động trước khi tắt scheduler.
- `vault_http_timeout_count` và các nhóm HTTP status: tách lỗi mạng khỏi lỗi policy.
- Thời gian chờ shutdown hook, số lần process bị SIGKILL vì quá grace period.

Tên metric chỉ là **gợi ý do ứng dụng định nghĩa**, không khẳng định Spring Vault tự xuất tất cả số liệu này. Đừng đưa secret path nhạy cảm, token, lease ID, mật khẩu database hoặc khóa Transit/PKI vào metric labels hoặc traces.

Nếu lượng lease lớn, cần giám sát tổng số lease và tần suất rotation để scheduler không bị starvation. Nếu dùng chung scheduler với job nền khác, xác định liệu các job đó có làm renew trễ và gây gián đoạn credential không.

## 16. Checklist trước khi triển khai

| Câu hỏi | Hướng xử lý |
| --- | --- |
| Ai sở hữu `VaultTemplate`, session, scheduler và HTTP pool? | Vẽ dependency graph và ghi rõ owner |
| Token dùng là `VaultToken` tĩnh hay `LoginToken` của auth method? | Thiết kế renew/revoke theo loại token |
| Có secret động cần theo dõi không? | Đăng ký `SecretLeaseContainer` chỉ cho path cần thiết |
| `stop()` có bị nhầm với revoke không? | Phân biệt lifecycle pause và `destroy()` |
| Revoke lease còn đường đi HTTP và token không? | Giữ session/client đến khi cleanup kết thúc |
| Scheduler có nhận thêm task khi dừng không? | Ngừng scheduling trước shutdown và hạn chế queued renew |
| Scheduler có được mượn từ bean khác không? | `fromInstance(...)` không đóng scheduler bên ngoài |
| Có Grace period và HTTP timeout hữu hạn không? | Đặt theo SLO, tránh chờ vô hạn |
| Có cơ chế restart/retry khi Vault unavailable không? | Dùng TTL, alert và recovery có giới hạn |
| Đã có test stop/destroy/revoke thật chưa? | Test integration bằng dynamic secret |
| Lúc SIGKILL có thể bỏ qua cleanup không? | Dựa vào Vault TTL và vận hành phía server |
| Có rủi ro lộ secret khi log lỗi cleanup không? | Log metadata an toàn, không xuất credential |

### Câu hỏi tự luyện

1. `VaultTemplate.destroy()` và `ThreadPoolTaskScheduler.shutdown()` giải quyết hai trách nhiệm khác nhau thế nào?
2. Tại sao `SecretLeaseContainer.stop()` không thể được dùng thay cho `destroy()` khi muốn revoke lease?
3. Vì sao phải giữ session/token và HTTP client khả dụng trong lúc cố gắng revoke một lease?
4. Với `TokenAuthentication`, tại sao việc đóng ứng dụng không bảo đảm token tĩnh bị thu hồi?
5. `TaskSchedulerWrapper.fromInstance(...)` có sở hữu scheduler được truyền vào không?
6. Thêm `@DependsOn("ordersSessionManager")` cho bean consumer ảnh hưởng gì đến thứ tự destroy của singleton?
7. Lý do nào khiến `setWaitForTasksToCompleteOnShutdown(true)` không luôn phù hợp với token-renew tasks?
8. Một lần đọc KV v2 tĩnh tạo ra secret lease riêng cần revoke khi shutdown hay không?
9. Nếu Pod bị SIGKILL, những callback nào có thể không được gọi? Hệ thống hạn chế rủi ro bằng cách nào?
10. Kiểm thử `ApplicationContextRunner` chứng minh gì, và kiểm thử động trên Vault thật cần xác nhận thêm điều gì?

**Kết quả mong đợi:** bạn có thể quản lý việc đóng `VaultTemplate`, `SessionManager`, `SecretLeaseContainer` và `TaskScheduler` theo **resource ownership và thứ tự phụ thuộc**; phân biệt chính xác `stop`, `destroy` và revoke; thiết kế graceful shutdown có giới hạn thời gian; đồng thời kiểm thử token/lease cleanup mà không đánh đồng việc đọc KV với secret lease. Đây là nền tảng giúp ứng dụng Java sử dụng SPRING_VAULT bền vững khi chạy với auth theo workload, Transit encryption, PKI, giám sát và kiểm thử tích hợp.

### Tài liệu chính thức

- [Javadoc: VaultTemplate](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html)
- [Javadoc: LifecycleAwareSessionManager](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/LifecycleAwareSessionManager.html)
- [Javadoc: SecretLeaseContainer](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/lease/SecretLeaseContainer.html)
- [Javadoc: AbstractVaultConfiguration](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/config/AbstractVaultConfiguration.html)
- [Javadoc: AbstractVaultConfiguration.TaskSchedulerWrapper](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/config/AbstractVaultConfiguration.TaskSchedulerWrapper.html)
- [Spring Vault: Credentials Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
- [Spring Framework: Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework: Using depends-on](https://docs.spring.io/spring/reference/7.0/core/beans/dependencies/factory-dependson.html)

