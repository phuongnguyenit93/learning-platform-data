# Annotation không có hiệu lực vì self-invocation hoặc thiếu AOP

Khi dùng annotation `@CircuitBreaker` của Resilience4j trong ứng dụng Spring, một phương thức được đánh dấu có thể vẫn gọi dịch vụ phụ thuộc trực tiếp mà không thấy circuit breaker mở, fallback không chạy hoặc metrics không tăng. Hai nguyên nhân thường gặp là phương thức được gọi nội bộ trong cùng bean (self-invocation) nên không đi qua Spring AOP proxy, hoặc ứng dụng thiếu cấu hình AOP cần thiết để đăng ký aspect xử lý annotation.

Để annotation có hiệu lực, phương thức phải được gọi qua proxy Spring và Resilience4j aspect phải có mặt trong ApplicationContext. Cần kiểm tra cả dependency, cách Spring tạo bean, kiểu proxy, phạm vi phương thức và đường gọi thực tế. Nếu không muốn phụ thuộc vào AOP, có thể dùng API lập trình của Spring Cloud CircuitBreaker hoặc Resilience4j để bọc lời gọi một cách tường minh.

## Annotation hoạt động thông qua Spring AOP như thế nào?

Annotation `@CircuitBreaker` không tự thay đổi bytecode của phương thức. Resilience4j cung cấp một aspect tích hợp với Spring AOP. Khi một bean được tạo và phương thức được gọi qua proxy, aspect nhận diện annotation, lấy cấu hình circuit breaker theo tên rồi thực thi lời gọi thông qua bộ ngắt mạch.

Luồng xử lý khái quát:

~~~mermaid
flowchart TD
    A[Bean A được Spring quản lý] --> B[Caller gọi bean qua proxy]
    B --> C[Resilience4j CircuitBreakerAspect]
    C --> D[Đọc @CircuitBreaker và tên instance]
    D --> E[Thực thi lời gọi qua circuit breaker]
    E --> F{Kết quả lời gọi}
    F -->|Thành công| G[Trả kết quả]
    F -->|Exception hoặc mạch OPEN| H[Fallback nếu có]
~~~

Khi caller gọi bean trực tiếp qua đối tượng proxy, aspect có cơ hội chặn lời gọi trước khi phương thức đích chạy. Nếu phương thức gọi một phương thức khác bằng `this.otherMethod()`, lời gọi nội bộ diễn ra trên đối tượng đích và không quay lại proxy. Aspect không được gọi lần thứ hai, nên annotation trên `otherMethod` không được áp dụng trong đường gọi đó.

Đây là đặc điểm của proxy-based AOP trong Spring. Việc đặt annotation đúng vị trí chưa đủ; điều quan trọng là lời gọi có đi qua proxy hay không.

## Nhận biết lỗi self-invocation

Ví dụ dưới đây có hai phương thức trong cùng một service:

~~~java
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    public Inventory findForOrder(String sku) {
        // Lời gọi nội bộ không đi qua Spring proxy.
        return findFromRemote(sku);
    }

    @CircuitBreaker(
            name = "inventoryRead",
            fallbackMethod = "inventoryFallback"
    )
    public Inventory findFromRemote(String sku) {
        return inventoryClient.fetch(sku);
    }

    public Inventory inventoryFallback(String sku, Throwable error) {
        return Inventory.unavailable(sku);
    }
}
~~~

Khi một bean khác gọi `inventoryService.findForOrder(sku)`, lời gọi bên ngoài đi qua proxy nhưng `findForOrder` không có annotation. Sau đó, `findForOrder` gọi `this.findFromRemote(sku)` trên chính đối tượng đích. Vì lời gọi thứ hai không đi qua proxy, Resilience4j aspect không chạy cho `findFromRemote`.

Triệu chứng thường thấy:

- Exception từ dịch vụ phụ thuộc truyền thẳng ra caller.
- Fallback khai báo trong annotation không được gọi.
- Failure rate, slow call rate hoặc số lời gọi của instance không tăng như mong đợi.
- Circuit breaker không chuyển trạng thái dù downstream đang lỗi.
- Gọi trực tiếp phương thức có annotation từ một bean khác lại hoạt động bình thường.

Đừng kết luận rằng annotation hoặc cấu hình Resilience4j bị hỏng chỉ từ một lần gọi nội bộ. Hãy lần theo call path để xác định phương thức được gọi từ bean khác hay từ chính đối tượng đó.

## Cách sửa self-invocation: tách phương thức được bảo vệ sang bean riêng

Cách rõ ràng và dễ bảo trì nhất là đưa lời gọi phụ thuộc được bảo vệ sang một bean Spring khác. Khi service nghiệp vụ gọi bean này thông qua dependency injection, lời gọi đi qua proxy và aspect có thể áp dụng.

~~~java
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
public class ProtectedInventoryClient {

    private final InventoryClient inventoryClient;

    public ProtectedInventoryClient(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(
            name = "inventoryRead",
            fallbackMethod = "inventoryFallback"
    )
    public Inventory find(String sku) {
        return inventoryClient.fetch(sku);
    }

    public Inventory inventoryFallback(String sku, Throwable error) {
        return Inventory.unavailable(sku);
    }
}
~~~

Service nghiệp vụ sử dụng bean đã được Spring quản lý:

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ProtectedInventoryClient protectedInventoryClient;

    public OrderService(
            ProtectedInventoryClient protectedInventoryClient) {
        this.protectedInventoryClient = protectedInventoryClient;
    }

    public OrderDecision check(String sku) {
        Inventory inventory = protectedInventoryClient.find(sku);
        return OrderDecision.from(inventory);
    }
}
~~~

Ở đây, `OrderService` gọi `ProtectedInventoryClient` qua bean được inject. Spring cung cấp proxy của client và Resilience4j aspect chặn phương thức `find`. Phần nghiệp vụ không cần biết chi tiết proxy.

Nên đặt circuit breaker ở ranh giới gọi dịch vụ phụ thuộc. Cách này giúp phạm vi được bảo vệ rõ ràng, dễ kiểm thử và tránh việc một phương thức nội bộ vừa xử lý nghiệp vụ vừa tự gọi qua nhiều tầng.

## Các cách khác và giới hạn của chúng

Có thể xử lý self-invocation theo nhiều cách, nhưng không phải cách nào cũng nên dùng mặc định:

| Cách | Cách hoạt động | Nhận xét |
|---|---|---|
| Tách bean riêng | Đưa phương thức được bảo vệ sang một Spring bean khác và inject bean đó. | Khuyến nghị; ranh giới proxy rõ ràng. |
| Inject self proxy | Inject proxy của chính bean rồi gọi phương thức qua tham chiếu proxy. | Có thể hoạt động nhưng dễ tạo vòng phụ thuộc và làm cấu trúc khó hiểu. |
| Dùng `AopContext.currentProxy()` | Lấy proxy hiện tại rồi gọi phương thức qua proxy. | Cần bật exposeProxy; tạo liên kết chặt với AOP và không phù hợp làm mặc định. |
| Dùng API lập trình | Gọi circuit breaker trực tiếp quanh supplier hoặc publisher. | Rõ ràng, không phụ thuộc annotation interception. |

Nếu dùng `AopContext.currentProxy()`, Spring phải được cấu hình để expose proxy, chẳng hạn qua `@EnableAspectJAutoProxy(exposeProxy = true)` trong cấu hình phù hợp. Việc gọi proxy từ trong bean làm mã nguồn phụ thuộc vào cơ chế AOP và cần xử lý kiểu ép đối tượng. Chỉ nên dùng khi có lý do kiến trúc cụ thể.

Không dùng `new InventoryService()` hoặc tự tạo đối tượng bằng constructor ở nơi cần annotation. Đối tượng tự tạo không nằm trong Spring ApplicationContext, vì vậy không có proxy và không nhận các aspect, transaction hay các cơ chế proxy khác.

## Kiểm tra dependency và cấu hình AOP

Annotation của Resilience4j cần có thư viện hỗ trợ Spring và aspect tương ứng. Với Spring Boot 3, dependency thường dùng là `resilience4j-spring-boot3`; với Spring Boot 2, dùng starter tương thích như `resilience4j-spring-boot2`. Không trộn artifact dành cho hai thế hệ Spring Boot.

Ví dụ Maven cho Spring Boot 3:

~~~xml
<dependencies>
    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-spring-boot3</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Phiên bản nên được quản lý qua BOM hoặc dependency management tương thích với Spring Boot và Resilience4j của dự án. Không sao chép một phiên bản tùy ý từ ví dụ vào ứng dụng đang dùng một release train khác.

Vai trò của các dependency:

- `resilience4j-spring-boot3` cung cấp tích hợp Resilience4j với Spring Boot 3, cấu hình và aspect annotation.
- `spring-boot-starter-aop` cung cấp hạ tầng Spring AOP và proxy.
- `spring-boot-starter-actuator` hỗ trợ health, metrics và quan sát ứng dụng; nó không tự thay thế AOP aspect.

Với Spring Boot auto-configuration và starter tương ứng, thường không cần tự khai báo `@EnableAspectJAutoProxy`. Nếu ứng dụng Spring không dùng auto-configuration hoặc tự cấu hình AOP, cần bật hạ tầng proxy phù hợp. Thêm annotation `@EnableAspectJAutoProxy` mà thiếu aspect Resilience4j không làm `@CircuitBreaker` tự hoạt động.

Nếu annotation không được nhận diện khi biên dịch, kiểm tra dependency chứa annotation. Nếu annotation biên dịch được nhưng không có interception lúc chạy, kiểm tra starter, aspect, AOP infrastructure và việc bean có được Spring quản lý hay không.

## Kiểm tra bean có được Spring quản lý và có đi qua proxy

Một class có annotation `@Service` hoặc `@Component` thường được Spring tạo bean nếu package nằm trong component scan. Nhưng nếu ứng dụng tự tạo instance bằng `new`, hoặc cấu hình scan không bao phủ package, bean đó không có proxy.

Có thể kiểm tra bean ở runtime:

~~~java
import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Component
public class ProxyDiagnostics {

    private final ProtectedInventoryClient inventoryClient;

    public ProxyDiagnostics(ProtectedInventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public void logProxyStatus() {
        boolean proxy = AopUtils.isAopProxy(inventoryClient);
        boolean classProxy = AopUtils.isCglibProxy(inventoryClient);
        boolean jdkProxy = AopUtils.isJdkDynamicProxy(inventoryClient);

        log.info(
                "inventoryClient: proxy={}, cglib={}, jdk={}",
                proxy,
                classProxy,
                jdkProxy
        );
    }
}
~~~

Đoạn mã minh họa cách xác định đối tượng được inject có phải AOP proxy hay không. Việc `AopUtils.isAopProxy` trả về true chưa chứng minh đúng Resilience4j aspect đã được áp dụng; bean có thể được proxy bởi transaction hoặc một aspect khác. Cần kết hợp kiểm tra dependency, log và hành vi thực tế của circuit breaker.

Không nên log toàn bộ object proxy hoặc thông tin cấu hình nhạy cảm. Chỉ ghi nhận loại proxy và bean cần chẩn đoán.

## Phạm vi phương thức và loại proxy

Spring AOP thường dùng JDK dynamic proxy hoặc CGLIB class proxy:

- **JDK dynamic proxy** tạo proxy dựa trên interface. Caller thường cần truy cập phương thức qua interface mà proxy triển khai.
- **CGLIB class proxy** tạo lớp con của class đích để chặn lời gọi. Class và phương thức không thể là `final` nếu cần override để interception.
- **Private method** không thể được gọi qua proxy theo cách cần thiết để aspect chặn.
- **Static method** không phải lời gọi instance qua proxy.
- Phương thức package/protected có thể phụ thuộc kiểu proxy và cấu hình; public method trên Spring bean là lựa chọn dễ dự đoán nhất.

Ví dụ, nếu bean dùng JDK proxy và phương thức có annotation không được khai báo trên interface mà caller đang sử dụng, caller có thể không gọi được phương thức đó qua proxy theo cách mong đợi. Nếu class hoặc method là final, CGLIB không thể override để interception.

Để giảm lỗi khó chẩn đoán, hãy đặt annotation trên phương thức public của bean Spring, bảo đảm caller gọi qua interface/proxy phù hợp và tránh class/method final khi dùng class-based proxy.

## Cấu hình instance phải khớp với tên annotation

Tên trong `@CircuitBreaker(name = "inventoryRead")` phải khớp với tên instance trong cấu hình Resilience4j nếu muốn dùng chính sách riêng:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Nếu tên không khớp, ứng dụng có thể không dùng cấu hình riêng mà nhóm phát triển kỳ vọng. Khi điều tra, kiểm tra chính xác chữ hoa/chữ thường và tên instance. Không dùng tên thay đổi theo request như SKU hoặc user ID.

Cấu hình fallback trong annotation cần chỉ đến phương thức tương thích. Với phương thức đồng bộ:

~~~java
@CircuitBreaker(name = "inventoryRead", fallbackMethod = "inventoryFallback")
public Inventory find(String sku) {
    return inventoryClient.fetch(sku);
}

public Inventory inventoryFallback(String sku, Throwable error) {
    log.warn("Inventory lookup failed", error);
    return Inventory.unavailable(sku);
}
~~~

Fallback thường có cùng các tham số nghiệp vụ với phương thức gốc và thêm một tham số exception ở cuối; kiểu trả về phải phù hợp với phương thức được bảo vệ. Có thể khai báo overload fallback cho loại exception cụ thể nếu cần xử lý riêng. Nếu chữ ký fallback không khớp, lỗi có thể chỉ xuất hiện lúc chạy khi aspect tìm phương thức fallback.

Với phương thức reactive, fallback cần giữ kiểu reactive tương ứng, ví dụ phương thức trả `Mono<Inventory>` thì fallback cũng trả `Mono<Inventory>`. Không trả một object đồng bộ hoặc gọi `block()` để ép luồng reactive thành đồng bộ.

## Annotation Resilience4j và Spring Cloud CircuitBreaker là hai cách tích hợp khác nhau

Tên gọi dễ gây nhầm lẫn:

| Cách dùng | Cơ chế |
|---|---|
| `@CircuitBreaker` từ `io.github.resilience4j.circuitbreaker.annotation` | Resilience4j aspect dùng Spring AOP để chặn phương thức được gọi qua proxy. |
| `CircuitBreakerFactory` của Spring Cloud CircuitBreaker | API lập trình tạo circuit breaker và bọc supplier/callable. |
| `ReactiveCircuitBreakerFactory` | API lập trình bảo vệ Mono/Flux theo abstraction reactive. |

Spring Cloud CircuitBreaker cung cấp abstraction và factory để tích hợp các backend như Resilience4j. Annotation `@CircuitBreaker` là cơ chế annotation của Resilience4j, không phải một annotation chung do mọi backend Spring Cloud CircuitBreaker tự động cung cấp.

Nếu ứng dụng đang sử dụng Spring Cloud CircuitBreaker factory, có thể bảo vệ lời gọi tường minh:

~~~java
public Inventory find(String sku) {
    return circuitBreakerFactory.create("inventoryRead").run(
            () -> inventoryClient.fetch(sku),
            error -> Inventory.unavailable(sku)
    );
}
~~~

Cách lập trình này không dựa vào proxy interception của annotation, nên tránh được lỗi self-invocation. Tuy nhiên, cần bảo đảm factory được inject đúng và fallback xử lý các lỗi theo chính sách nghiệp vụ.

Không nên áp dụng annotation và bọc programmatic circuit breaker trùng lặp cho cùng một lời gọi nếu không có chủ đích. Hai lớp circuit breaker có thể có sliding window, metrics, fallback và trạng thái khác nhau, khiến việc chẩn đoán khó hơn.

## Quy trình chẩn đoán khi annotation không có hiệu lực

Hãy kiểm tra theo thứ tự để tìm đúng tầng bị thiếu:

1. **Xác nhận annotation:** dùng đúng import `io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker`, không nhầm với class hoặc annotation khác cùng tên.
2. **Xác nhận dependency:** ứng dụng có starter Resilience4j tương thích với Spring Boot và hạ tầng Spring AOP.
3. **Xác nhận bean:** class được Spring tạo và inject; không tự khởi tạo bằng `new`.
4. **Xác nhận proxy:** bean được caller sử dụng có phải proxy hay không; kiểm tra JDK/CGLIB và phạm vi interface.
5. **Xác nhận call path:** lời gọi đến phương thức được bảo vệ đi từ bean khác qua proxy, không phải self-invocation.
6. **Xác nhận method:** ưu tiên public instance method; tránh private, static, final hoặc method không thể được proxy chặn.
7. **Xác nhận tên instance:** tên trong annotation khớp cấu hình Resilience4j.
8. **Xác nhận fallback:** chữ ký tham số và kiểu trả về tương thích; fallback không che giấu lỗi bằng dữ liệu giả.
9. **Xác nhận đủ mẫu:** circuit breaker cần đạt `minimumNumberOfCalls` trước khi đánh giá tỷ lệ.
10. **Kiểm tra metrics và trạng thái:** theo dõi số lời gọi, failure rate, slow call rate và trạng thái OPEN/CLOSED/HALF_OPEN.

Bảng triệu chứng giúp khoanh vùng nhanh:

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| Annotation biên dịch nhưng không có hiệu lực | Thiếu Resilience4j aspect hoặc AOP starter. | Dependency tree và auto-configuration. |
| Gọi từ controller hoạt động, gọi từ method cùng class không hoạt động | Self-invocation bypass proxy. | Call graph và ranh giới bean. |
| Bean không phải proxy | Bean tự tạo hoặc package không được scan, thiếu AOP. | ApplicationContext và AopUtils. |
| Proxy tồn tại nhưng circuit breaker không thay đổi | Aspect không được đăng ký, method không được intercept hoặc cấu hình tên sai. | Log, dependency và metrics theo instance. |
| Fallback không chạy | Chữ ký fallback sai hoặc exception không đi qua phương thức được bảo vệ. | Kiểu tham số, kiểu trả về và call path. |
| Mạch chưa OPEN dù nhiều lời gọi lỗi | Chưa đủ minimumNumberOfCalls hoặc lỗi bị phân loại không phải failure. | Metrics và exception classification. |

## Kiểm thử để chứng minh proxy và circuit breaker thực sự hoạt động

Unit test gọi trực tiếp đối tượng được tạo bằng `new` thường không kiểm tra được Spring AOP. Hãy dùng Spring context hoặc integration test để nhận bean từ ApplicationContext và gọi qua bean đó.

Một kiểm thử tích hợp nên:

- Tạo bean Spring có annotation.
- Mock hoặc stub client phụ thuộc để ném exception có thể ghi nhận.
- Gọi phương thức qua bean được inject từ context đủ số lần để đạt `minimumNumberOfCalls`.
- Xác nhận fallback được gọi khi lỗi xảy ra hoặc mạch OPEN.
- Kiểm tra trạng thái circuit breaker và metrics của đúng tên instance.
- Tạo thêm trường hợp self-invocation để chứng minh lời gọi nội bộ không đi qua proxy, rồi xác nhận cách sửa bằng bean riêng.

Không chỉ kiểm tra rằng phương thức trả fallback một lần. Fallback có thể được gọi bởi exception của supplier ngay cả khi circuit breaker chưa mở. Muốn chứng minh circuit breaker hoạt động, cần kiểm tra số mẫu, failure rate và trạng thái chuyển mạch.

Khi kiểm thử, dùng instance và registry riêng cho mỗi kịch bản hoặc reset trạng thái có kiểm soát. Tránh để trạng thái OPEN từ test trước ảnh hưởng test sau. Nếu dùng thời gian chờ OPEN hoặc HALF_OPEN, nên dùng cơ chế thời gian kiểm soát được để test không phụ thuộc vào chờ đợi dài.

## Nguyên tắc triển khai

- Đặt annotation trên public method của bean Spring được quản lý.
- Bảo đảm caller đi qua proxy; tách bean khi có self-invocation.
- Dùng starter Resilience4j và AOP phù hợp với phiên bản Spring Boot.
- Không tự tạo instance bằng `new` cho bean cần aspect.
- Kiểm tra JDK/CGLIB proxy, interface, class final và method visibility.
- Giữ tên circuit breaker ổn định và khớp cấu hình instance.
- Viết fallback đúng chữ ký và đúng ngữ nghĩa nghiệp vụ.
- Nếu không muốn phụ thuộc AOP, dùng Spring Cloud CircuitBreaker factory để bọc lời gọi tường minh.
- Kiểm thử bằng Spring context và xác nhận cả metrics lẫn trạng thái circuit breaker.

Annotation `@CircuitBreaker` chỉ có hiệu lực khi Resilience4j aspect được đăng ký và lời gọi đi qua Spring AOP proxy. Self-invocation, bean tự tạo, thiếu dependency AOP hoặc phương thức không thể được proxy chặn đều có thể khiến annotation bị bỏ qua. Xác định đúng ranh giới proxy, tách lời gọi phụ thuộc sang bean riêng và kiểm tra trạng thái thực tế sẽ giúp circuit breaker bảo vệ đúng lời gọi trong ứng dụng Spring Cloud.

