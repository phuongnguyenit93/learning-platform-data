# @Value trên singleton thông thường và giá trị đã được khởi tạo

Trong Spring Boot, **@Value** lấy giá trị từ Spring Environment khi Spring tạo bean và inject giá trị đó vào bean. Với một bean singleton thông thường, quá trình này thường diễn ra một lần trong vòng đời của ApplicationContext. Nếu cấu hình từ Config Server thay đổi sau đó, Spring Environment có thể được refresh, nhưng field hoặc constructor value đã inject vào singleton không tự được gán lại.

Đây là nguyên nhân phổ biến khiến một ứng dụng đã nhận cấu hình mới nhưng một số thành phần vẫn sử dụng giá trị cũ. Muốn áp dụng thay đổi khi ứng dụng đang chạy, cần chọn rõ cơ chế cập nhật: tạo lại bean bằng **@RefreshScope**, đọc giá trị động từ **Environment**, hoặc restart ứng dụng nếu thành phần không thể tái cấu hình an toàn.

Bài học này giải thích thời điểm Spring resolve **@Value**, vòng đời của singleton, điều gì xảy ra khi refresh cấu hình và cách kiểm tra bean thực sự sử dụng giá trị mới.

Sau bài học, bạn có thể:

- Xác định khi nào placeholder trong **@Value** được resolve và inject.
- Giải thích vì sao singleton thông thường giữ giá trị đã nhận dù Environment đã được refresh.
- Phân biệt refresh Environment với việc tạo lại một bean.
- Dùng **@RefreshScope** đúng chỗ để target bean được tạo lại và nhận giá trị mới.
- Chọn giữa **@Value**, **Environment**, **@ConfigurationProperties**, refresh và restart theo nhu cầu.
- Thiết kế kiểm thử để xác nhận giá trị mà mã ứng dụng đang sử dụng.

## 1. @Value được resolve khi bean được tạo

Spring xử lý placeholder trong **@Value** thông qua cơ chế dependency injection. Khi Spring tạo bean, nó resolve biểu thức từ Environment rồi gán giá trị vào constructor parameter hoặc field tương ứng.

Ví dụ:

~~~yaml
checkout:
  retry:
    max-attempts: 3
~~~

Một bean đọc thuộc tính này bằng constructor injection:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class RetryPolicy {

    private final int maxAttempts;

    public RetryPolicy(
            @Value("\${checkout.retry.max-attempts:3}") int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public int maxAttempts() {
        return maxAttempts;
    }
}
~~~

Khi Spring tạo **RetryPolicy**, placeholder được resolve. Nếu Environment có giá trị **checkout.retry.max-attempts=3**, constructor nhận số 3 và lưu vào field **maxAttempts**.

Dấu **:3** trong placeholder là giá trị mặc định nếu khóa không tồn tại. Nó không phải cơ chế refresh và cũng không khiến Spring đọc lại thuộc tính mỗi lần gọi phương thức.

Field injection có cùng đặc tính về thời điểm:

~~~java
@Component
public class CheckoutSettings {

    @Value("\${checkout.retry.max-attempts:3}")
    private int maxAttempts;

    public int maxAttempts() {
        return maxAttempts;
    }
}
~~~

Spring gán field khi khởi tạo bean. Sau khi bean đã được tạo, thay đổi property source không tự gọi lại quá trình inject field.

## 2. Vì sao singleton thông thường giữ giá trị cũ?

Trong Spring, singleton là một bean instance duy nhất cho mỗi bean definition trong một ApplicationContext. Bean được tạo khi ứng dụng khởi động theo mặc định, hoặc khi được truy cập lần đầu nếu bean dùng lazy initialization.

Sau khi bean được tạo, giá trị đã inject trở thành trạng thái của object. Ví dụ:

~~~mermaid
sequenceDiagram
    participant Config as Config Server
    participant Env as Spring Environment
    participant Spring as Spring Container
    participant Bean as RetryPolicy singleton

    Config->>Env: Cung cấp max-attempts = 3
    Spring->>Env: Resolve placeholder khi tạo bean
    Env-->>Spring: Trả về 3
    Spring->>Bean: Tạo bean với maxAttempts = 3
    Note over Bean: Field giữ giá trị 3
    Config->>Env: Cấu hình mới max-attempts = 5
    Note over Env: Environment được refresh
    Note over Bean: Singleton vẫn giữ maxAttempts = 3
    Spring->>Bean: Ứng dụng gọi maxAttempts()
    Bean-->>Spring: Trả về 3
~~~

Giả sử Config Server đã đổi giá trị thành 5 và client đã refresh thành công:

- Environment phía client có thể đã chứa giá trị mới là 5.
- Bean **RetryPolicy** vẫn giữ field **maxAttempts=3**.
- Gọi **retryPolicy.maxAttempts()** vẫn trả về 3.
- Restart ứng dụng sẽ tạo bean mới và resolve lại placeholder, nên bean mới nhận giá trị 5.

Điểm cần phân biệt là trạng thái cấu hình và trạng thái object. Refresh Environment cập nhật nguồn dữ liệu cấu hình. Nó không đồng nghĩa mọi object singleton trong ApplicationContext được khởi tạo lại.

Điều này vẫn đúng khi dùng constructor injection, field injection hoặc setter injection với **@Value**. Cách inject khác nhau, nhưng giá trị chỉ được gán trong quá trình tạo bean; không có cơ chế tự động theo dõi property source để gán lại sau mỗi lần thay đổi.

## 3. Refresh cấu hình làm gì và không làm gì?

Trong hệ thống Spring Cloud Config, endpoint refresh có thể yêu cầu client lấy lại cấu hình từ Config Server và phát sự kiện thay đổi môi trường.

Ví dụ, sau khi repository cấu hình đã có revision mới, người vận hành gọi:

~~~bash
curl --fail --show-error -X POST \
  http://localhost:8080/actuator/refresh
~~~

Endpoint phải được expose trong Actuator và bảo vệ bằng xác thực, phân quyền. Ví dụ cấu hình trong môi trường kiểm thử:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Khi refresh thành công, Spring Cloud cập nhật Environment và phát sự kiện liên quan đến thay đổi cấu hình. Những thành phần hỗ trợ cơ chế refresh có thể phản ứng với thay đổi này.

Tuy nhiên, với singleton thông thường:

- Constructor không được chạy lại chỉ vì một property thay đổi.
- Field đã được inject bằng **@Value** không tự được gán lại.
- Các biến thành viên đã copy giá trị cấu hình vẫn giữ giá trị cũ.
- Một thư viện bên thứ ba không tự cấu hình lại nếu nó không có cơ chế nhận thay đổi.

Refresh endpoint có thể trả về danh sách tên các property được nhận diện là đã thay đổi. Danh sách đó không chứng minh rằng mọi bean đã sử dụng giá trị mới. Cần kiểm tra trực tiếp thành phần tiêu thụ cấu hình.

Cũng cần xác nhận Config Server đã phục vụ revision mới trước khi refresh client. Nếu Config Server vẫn trả dữ liệu cũ do backend hoặc cache chưa cập nhật, client có thể refresh thành công về mặt kỹ thuật nhưng vẫn nhận giá trị cũ.

## 4. Dùng @RefreshScope để tạo lại target bean

Nếu một bean có thể được tạo lại an toàn và cần nhận cấu hình mới khi chạy, Spring Cloud cung cấp **@RefreshScope**.

Ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class RefreshableRetryPolicy {

    private final int maxAttempts;

    public RefreshableRetryPolicy(
            @Value("\${checkout.retry.max-attempts:3}") int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public int maxAttempts() {
        return maxAttempts;
    }
}
~~~

Spring đưa bean thuộc refresh scope qua một proxy. Khi refresh scope được làm mới, target bean hiện tại bị loại khỏi cache. Lần tiếp theo ứng dụng gọi bean qua proxy, Spring tạo target mới. Trong quá trình tạo target mới, placeholder **@Value** được resolve từ Environment hiện tại.

Luồng hoạt động:

~~~mermaid
sequenceDiagram
    participant Config as Config Server
    participant Env as Client Environment
    participant Proxy as Refresh-scope proxy
    participant Target as RefreshableRetryPolicy target

    Config->>Env: max-attempts = 3
    Proxy->>Target: Tạo target lần đầu
    Target-->>Proxy: maxAttempts = 3
    Config->>Env: Cập nhật max-attempts = 5
    Note over Env: Client refresh Environment
    Note over Proxy: Refresh scope xóa target khỏi cache
    Proxy->>Target: Lần gọi tiếp theo tạo target mới
    Target-->>Proxy: Resolve @Value = 5
    Proxy-->>Proxy: Phương thức trả về giá trị mới
~~~

Sau khi refresh, object proxy mà các bean khác đang giữ có thể vẫn là cùng một proxy. Điều thay đổi là target phía sau proxy được tạo lại khi cần. Vì vậy, bean tiêu thụ nên gọi qua proxy Spring quản lý, không giữ một tham chiếu trực tiếp đến target cũ hoặc copy giá trị ra field riêng rồi kỳ vọng field đó tự cập nhật.

**@RefreshScope** phù hợp với bean có trạng thái cấu hình đơn giản và có thể khởi tạo lại an toàn. Không nên gắn annotation này một cách máy móc lên mọi bean. Việc tạo lại target có thể ảnh hưởng tài nguyên đang mở, request đang xử lý hoặc trạng thái nội bộ nếu bean không được thiết kế cho vòng đời đó.

Nếu dùng **@Bean** trong một lớp cấu hình, có thể đặt **@RefreshScope** trên phương thức tạo bean cần refresh. Đặt annotation trên lớp **@Configuration** không có nghĩa mọi bean được khai báo trong lớp đó tự động thuộc refresh scope.

## 5. So sánh các cách đọc cấu hình

| Cách đọc | Sau khi Environment refresh | Khi nào nên dùng |
|---|---|---|
| **@Value** trong singleton thường | Field/constructor value đã inject vẫn cũ | Giá trị ít thay đổi hoặc chỉ cần khi khởi động |
| **@Value** trong bean **@RefreshScope** | Target mới resolve lại placeholder | Bean có thể tạo lại an toàn và cần cập nhật nóng |
| **Environment.getProperty** mỗi lần gọi | Có thể đọc giá trị mới từ Environment đã refresh | Giá trị cần tra cứu động tại thời điểm sử dụng |
| **Environment.getProperty** rồi lưu vào field | Field đã lưu vẫn cũ | Không phù hợp nếu kỳ vọng giá trị tự cập nhật |
| **@ConfigurationProperties** | Có thể được Spring Cloud rebinding theo cơ chế refresh | Nhóm cấu hình có cấu trúc, kiểu dữ liệu và validation |
| Restart ứng dụng | Bean được tạo lại từ đầu | Thành phần không hỗ trợ refresh hoặc cần khởi tạo lại hạ tầng |

Ví dụ đọc động bằng Environment:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DynamicRetryPolicy {

    private final Environment environment;

    public DynamicRetryPolicy(Environment environment) {
        this.environment = environment;
    }

    public int maxAttempts() {
        return environment.getProperty(
            "checkout.retry.max-attempts",
            Integer.class,
            3
        );
    }
}
~~~

Phương thức **maxAttempts()** truy vấn Environment mỗi lần được gọi. Sau khi Environment được refresh, lần gọi tiếp theo có thể nhận giá trị mới. Nếu constructor đọc một lần rồi lưu kết quả vào field, hành vi sẽ trở lại giống singleton thông thường.

Với **@ConfigurationProperties**, Spring Cloud Context có cơ chế rebinding một số bean cấu hình khi refresh. Tuy nhiên, cần kiểm tra cách đăng ký bean, tính bất biến của object, các tham chiếu đã được copy và phiên bản Spring Cloud đang sử dụng. Không giả định mọi object đã nhận một reference của cấu hình đều tự thay đổi theo.

## 6. Một singleton khác giữ bản sao giá trị thì sao?

Ngay cả khi bean cấu hình đã được refresh, một thành phần khác có thể vẫn giữ giá trị cũ nếu nó chỉ đọc giá trị một lần rồi lưu vào biến riêng.

Ví dụ:

~~~java
@Component
public class CheckoutExecutor {

    private final int maxAttempts;

    public CheckoutExecutor(RefreshableRetryPolicy policy) {
        this.maxAttempts = policy.maxAttempts();
    }

    public int maxAttempts() {
        return maxAttempts;
    }
}
~~~

Constructor của **CheckoutExecutor** gọi proxy và lấy giá trị hiện tại, rồi lưu vào field **maxAttempts**. Nếu sau đó target của **RefreshableRetryPolicy** được tạo lại, field trong **CheckoutExecutor** không tự được tính lại. Nó vẫn giữ số đã copy lúc khởi tạo.

Có thể sửa bằng cách gọi bean refresh-scoped tại thời điểm sử dụng:

~~~java
@Component
public class CheckoutExecutor {

    private final RefreshableRetryPolicy policy;

    public CheckoutExecutor(RefreshableRetryPolicy policy) {
        this.policy = policy;
    }

    public int maxAttempts() {
        return policy.maxAttempts();
    }
}
~~~

Ở đây, **CheckoutExecutor** giữ proxy do Spring inject. Mỗi lần gọi **policy.maxAttempts()**, proxy định tuyến đến target hiện hành. Sau khi refresh scope bị xóa cache và target mới được tạo, lời gọi tiếp theo có thể nhận giá trị mới.

Quy tắc thực hành: nếu cần dữ liệu thay đổi theo refresh, hãy giữ reference đến thành phần refresh-aware và đọc giá trị qua nó khi cần. Tránh copy giá trị sang field bất biến của một singleton khác nếu mong muốn giá trị đó tự thay đổi.

## 7. Kiểm thử hành vi của @Value qua refresh

Có thể kiểm tra khác biệt giữa singleton thông thường và refresh-scoped bean bằng một kịch bản tích hợp.

Giả sử ban đầu Config Server trả:

~~~yaml
checkout:
  retry:
    max-attempts: 3
~~~

Client có hai bean dưới đây; đặt mỗi lớp public trong một file Java riêng:

~~~java
@Component
public class OrdinaryRetryPolicy {

    private final int maxAttempts;

    public OrdinaryRetryPolicy(
            @Value("\${checkout.retry.max-attempts:3}") int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public int maxAttempts() {
        return maxAttempts;
    }
}

@Component
@RefreshScope
public class ScopedRetryPolicy {

    private final int maxAttempts;

    public ScopedRetryPolicy(
            @Value("\${checkout.retry.max-attempts:3}") int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public int maxAttempts() {
        return maxAttempts;
    }
}
~~~

Thực hiện theo thứ tự:

1. Khởi động client và gọi cả hai bean. Cả hai trả về 3.
2. Thay giá trị trong repository thành 5 và xác nhận Config Server đã trả về giá trị mới.
3. Gọi **POST /actuator/refresh** trên Config Client.
4. Gọi lại **OrdinaryRetryPolicy.maxAttempts()**. Kết quả vẫn là 3.
5. Gọi **ScopedRetryPolicy.maxAttempts()**. Proxy tạo target mới khi cần; kết quả là 5.
6. Restart ứng dụng. Cả hai bean được tạo mới và nhận giá trị 5.

Bảng kết quả mong đợi:

| Thời điểm | Singleton thường | Bean @RefreshScope |
|---|---:|---:|
| Khởi động với cấu hình 3 | 3 | 3 |
| Environment đã refresh thành 5 | 3 | Target cũ đã bị loại khỏi cache; lần gọi tiếp theo tạo target mới |
| Sau khi gọi bean qua proxy | 3 | 5 |
| Sau khi restart ứng dụng | 5 | 5 |

Trong bài kiểm thử, cần gọi phương thức trên proxy sau refresh để target mới thực sự được tạo. Nếu chỉ quan sát log của endpoint refresh mà chưa gọi bean, target có thể chưa được khởi tạo lại ngay tại thời điểm đó.

## 8. Khi nào nên dùng refresh và khi nào nên restart?

Không phải mọi thuộc tính đều thích hợp để thay đổi nóng. Cần xem bean và tài nguyên sử dụng giá trị có thể được tạo lại hoặc cấu hình lại an toàn hay không.

| Loại cấu hình | Cách xử lý thường phù hợp |
|---|---|
| Số lần retry, feature flag hoặc thông điệp hiển thị | Refresh bean hoặc đọc động nếu logic cho phép |
| Ngưỡng xử lý mà bean có thể tạo lại an toàn | **@RefreshScope** và kiểm thử hành vi |
| Cấu hình một thư viện đã khởi tạo connection pool | Kiểm tra API tái cấu hình; có thể cần restart |
| Port server, listener hoặc TLS đã nạp lúc startup | Thường cần restart/rolling restart |
| Static field hoặc singleton bên ngoài Spring | Cần thiết kế lại hoặc restart |
| Cấu hình có ảnh hưởng transaction đang chạy | Cần kiểm soát thời điểm áp dụng và khả năng tương thích |

Nếu thay đổi ảnh hưởng đến tài nguyên hạ tầng, hãy ưu tiên quy trình rollout có health check và khả năng rollback. Refresh thành công không chứng minh một connection pool, HTTP client hoặc thư viện bên thứ ba đã thay đổi cấu hình nội bộ.

## 9. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| **/actuator/refresh** báo có property thay đổi nhưng singleton vẫn trả giá trị cũ | **@Value** đã inject vào singleton khi bean tạo | Đọc trực tiếp field/giá trị qua phương thức và so sánh với Environment |
| Bean có **@RefreshScope** vẫn trả giá trị cũ | Target chưa đi qua proxy, refresh chưa thành công hoặc Config Server vẫn trả cấu hình cũ | Kiểm tra proxy, response Config Server và kết quả refresh |
| Bean tiêu thụ vẫn giữ giá trị cũ dù bean cấu hình đã refresh | Giá trị đã được copy vào field của bean tiêu thụ | Gọi qua proxy tại thời điểm sử dụng thay vì lưu bản sao |
| Gọi endpoint refresh bị 404 | Endpoint chưa được expose hoặc dependency/context chưa có endpoint | Kiểm tra Actuator exposure và Spring Cloud Context |
| Gọi endpoint refresh bị 401/403 | Thiếu quyền hoặc xác thực không hợp lệ | Kiểm tra security policy và danh tính vận hành |
| Bean refresh scope tạo lại nhưng khởi tạo thất bại | Giá trị mới không hợp lệ hoặc tài nguyên không thể tạo lại | Kiểm tra validation, log đã che secret và vòng đời tài nguyên |
| Một số bean đổi, một số bean không đổi | Các bean có cơ chế vòng đời khác nhau | Lập danh sách bean tiêu thụ cấu hình và kiểm tra từng bean |

Không ghi giá trị bí mật vào log để kiểm tra. Nếu cần xác minh, hãy ghi tên property, revision hoặc trạng thái đã nạp; che giá trị nhạy cảm và bảo vệ các endpoint Actuator.

## 10. Quy trình thiết kế một bean có cấu hình thay đổi

Trước khi thêm **@Value** vào một bean, hãy trả lời:

1. Giá trị này chỉ cần đúng lúc khởi động hay có thể thay đổi trong lúc ứng dụng chạy?
2. Nếu thay đổi, bean có thể tạo lại an toàn không?
3. Có thành phần nào copy giá trị sang field hoặc cache riêng không?
4. Có thể đọc trực tiếp từ Environment tại thời điểm sử dụng không?
5. Nếu dùng **@RefreshScope**, các caller có giữ proxy Spring hay giữ target/value cũ?
6. Thay đổi có ảnh hưởng tài nguyên ngoài bean như connection pool, socket hoặc listener không?
7. Có kiểm thử chứng minh hành vi trước và sau refresh không?

Với giá trị chỉ dùng khi khởi động, singleton thông thường và **@Value** là lựa chọn đơn giản. Với giá trị cần đổi nóng, hãy chọn **@RefreshScope** hoặc truy vấn Environment mỗi lần sử dụng. Với cấu hình phân cấp, cần nhiều kiểu dữ liệu và validation, hãy cân nhắc **@ConfigurationProperties** cùng cơ chế refresh phù hợp. Nếu tài nguyên không hỗ trợ thay đổi nóng, dùng restart/rolling restart.

## 11. Tự kiểm tra

1. Khi nào placeholder trong constructor parameter của **@Value** được resolve?
2. Vì sao Environment có thể chứa giá trị mới nhưng field trong singleton vẫn chứa giá trị cũ?
3. Gọi **POST /actuator/refresh** có làm constructor của mọi singleton chạy lại không?
4. **@RefreshScope** sử dụng proxy và cache target như thế nào?
5. Vì sao một singleton giữ proxy refresh-scoped có thể nhìn thấy target mới, nhưng singleton copy một số nguyên từ target lại không tự đổi?
6. Khi nào **Environment.getProperty()** mỗi lần gọi phù hợp hơn việc inject **@Value** một lần?
7. Những thay đổi cấu hình nào thường cần restart thay vì refresh?
8. Cần kiểm tra những gì để chứng minh ứng dụng đang dùng giá trị mới sau refresh?

Hãy tạo hai bean thử nghiệm: một singleton thông thường và một bean có **@RefreshScope**. Inject cùng khóa bằng **@Value**, khởi động với giá trị 3, đổi cấu hình remote thành 5 rồi gọi refresh. So sánh kết quả qua từng bean và qua một singleton tiêu thụ giữ proxy. Sau đó thay singleton tiêu thụ để nó copy giá trị vào field, quan sát vì sao bản sao vẫn cũ. Ghi lại kết quả và xác định nơi nào cần đọc động, nơi nào cần refresh scope hoặc restart.

## Tài liệu tham khảo

- [Spring Cloud Commons — Refresh Scope and Refreshing the Configuration](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Config Client — Refreshing Configuration](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Framework — @Value Annotation](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html)

