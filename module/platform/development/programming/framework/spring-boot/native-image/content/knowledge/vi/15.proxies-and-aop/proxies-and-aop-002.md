# Thứ tự interface và sự khớp đúng của metadata proxy

## 1. Vì sao thứ tự interface quan trọng?

Spring AOP thường dùng proxy để áp dụng transaction, security, caching, logging hoặc các advice khác quanh lời gọi method. Với JDK dynamic proxy, proxy được tạo từ một danh sách interface. Danh sách này không chỉ cho biết proxy cần triển khai những contract nào; **thứ tự interface cũng là một phần của cấu hình proxy**.

Trong Java, hai proxy được tạo từ cùng tập interface nhưng thứ tự khác nhau có thể là hai proxy class khác nhau. Điều này ảnh hưởng đến metadata mà GraalVM Native Image cần biết trước khi build. Nếu Spring AOT hoặc ứng dụng đăng ký proxy hints với thứ tự interface không khớp với proxy thực tế được tạo lúc runtime, Native Image có thể không tìm thấy metadata phù hợp cho tổ hợp interface đó.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, cần hiểu cách Spring AOT khai báo proxy và vì sao phải giữ chính xác danh sách interface, thứ tự và classloader assumptions. Bài học tập trung vào JDK dynamic proxy và API `RuntimeHints.proxies()`.

## 2. JDK dynamic proxy được xác định bởi danh sách interface

JDK cung cấp `java.lang.reflect.Proxy` để tạo proxy triển khai một hoặc nhiều interface:

```java
public interface PaymentService {
    Receipt pay(String orderId);
}

public interface Auditable {
    String auditId();
}
```

Tạo proxy:

```java
Object proxy = Proxy.newProxyInstance(
        PaymentService.class.getClassLoader(),
        new Class<?>[] { PaymentService.class, Auditable.class },
        invocationHandler
);
```

Proxy class được tạo ra triển khai cả `PaymentService` và `Auditable`. Các lời gọi interface method được chuyển tới `InvocationHandler`.

JDK yêu cầu các interface truyền vào phải thỏa điều kiện hợp lệ, bao gồm khả năng được nhìn thấy qua classloader và không có xung đột method không thể giải quyết theo quy tắc proxy. Danh sách interface rỗng, interface không hợp lệ hoặc visibility không tương thích có thể khiến tạo proxy thất bại.

## 3. Thứ tự interface là một phần của proxy identity

Xét hai danh sách:

```java
new Class<?>[] { PaymentService.class, Auditable.class }
new Class<?>[] { Auditable.class, PaymentService.class }
```

Cả hai chứa cùng hai interface nhưng khác thứ tự. JDK dynamic proxy xem thứ tự interface là một phần của định nghĩa proxy class; do đó hai thứ tự có thể tạo ra hai proxy class khác nhau. Thứ tự cũng ảnh hưởng thứ tự interface được trả về khi introspect proxy class.

Điều này có ý nghĩa thực tế trong Native Image: metadata proxy được đăng ký cho một danh sách interface theo thứ tự cụ thể. Một hint cho `[PaymentService, Auditable]` không nên được xem là tự động bao phủ `[Auditable, PaymentService]`.

| Danh sách interface | Kết quả cần hiểu |
|---|---|
| `[PaymentService, Auditable]` | Một tổ hợp proxy cụ thể |
| `[Auditable, PaymentService]` | Tổ hợp khác do thứ tự đổi |
| `[PaymentService]` | Proxy chỉ triển khai một interface |
| `[PaymentService, Auditable, MetricsAware]` | Tổ hợp thứ ba, cần metadata đúng thứ tự |

Không sắp xếp danh sách interface một cách tùy tiện sau khi metadata đã được khai báo. Nếu ứng dụng tạo proxy bằng một thứ tự, registrar phải đăng ký đúng thứ tự đó.

## 4. Spring ProxyHints và RuntimeHints.proxies()

Spring AOT cung cấp API để khai báo JDK proxy cần thiết:

```java
hints.proxies().registerJdkProxy(
        PaymentService.class,
        Auditable.class
);
```

Thứ tự đối số được giữ trong proxy hint. Khi Native Image xử lý metadata, tổ hợp interface được mô tả đúng theo thứ tự khai báo.

Có thể đăng ký qua `RuntimeHintsRegistrar`:

```java
final class PaymentProxyHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.proxies().registerJdkProxy(
                PaymentService.class,
                Auditable.class
        );
    }
}
```

Gắn registrar vào cấu hình Spring:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentProxyHints.class)
class PaymentAotConfiguration {
}
```

Spring AOT thu thập proxy hint ở build time. Chỉ khai báo interface trong reflection hints không thay thế proxy hint: proxy generation là một dạng runtime capability riêng.

## 5. Metadata phải khớp với proxy thực tế được tạo

Giả sử một thư viện hoặc cấu hình Spring tạo proxy như sau:

```java
Class<?>[] interfaces = {
    PaymentService.class,
    Auditable.class
};

Object proxy = Proxy.newProxyInstance(
        classLoader,
        interfaces,
        handler
);
```

Hint cần phản ánh chính xác:

```java
hints.proxies().registerJdkProxy(
        PaymentService.class,
        Auditable.class
);
```

Nếu runtime path khác tạo proxy với thứ tự ngược lại, cần khai báo thêm tổ hợp đó hoặc chuẩn hóa cách tạo proxy để mọi nơi dùng cùng một thứ tự. Việc chỉ đăng ký từng interface riêng lẻ không tương đương đăng ký tổ hợp proxy.

**Nguyên tắc:** metadata proxy mô tả một proxy interface set có thứ tự, không phải một tập không thứ tự các interface có thể kết hợp tùy ý.

## 6. Vì sao proxy hint không giống reflection hint?

Reflection hints mô tả class/member được truy cập qua Java reflection; proxy hints mô tả interface combination cần dùng để tạo JDK dynamic proxy.

| Nhu cầu | RuntimeHints API |
|---|---|
| Gọi constructor bằng reflection | `hints.reflection()` |
| Gọi method bằng reflection | `hints.reflection()` |
| Truy cập field bằng reflection | `hints.reflection()` |
| Tạo JDK dynamic proxy từ interface | `hints.proxies().registerJdkProxy(...)` |
| Đọc classpath resource | `hints.resources()` |
| Truy cập kiểu từ JNI | `hints.jni()` |

Một ứng dụng có thể cần cả reflection và proxy hints. Ví dụ framework tạo JDK proxy cho service interface và đồng thời dùng reflection để đọc annotation hoặc gọi constructor của implementation. Đăng ký proxy không tự động đăng ký tất cả member reflection của target class.

## 7. Ví dụ Spring AOP với interface proxy

Giả sử service:

```java
public interface OrderOperations {
    String submit(String orderId);
}

@Service
class OrderService implements OrderOperations {
    @Override
    public String submit(String orderId) {
        return "submitted:" + orderId;
    }
}
```

Một aspect ghi log lời gọi:

```java
@Aspect
@Component
class AuditAspect {

    @Around("execution(* com.example.OrderOperations.*(..))")
    Object audit(ProceedingJoinPoint joinPoint) throws Throwable {
        return joinPoint.proceed();
    }
}
```

Khi Spring AOP dùng JDK dynamic proxy, proxy triển khai interface `OrderOperations`. Nếu ứng dụng còn có interface bổ sung như `Auditable`, tổ hợp interface thực tế cần được xác định từ cách Spring tạo proxy và các advisor/introduction đã cấu hình.

Không phải mọi ứng dụng Spring AOP đều cần tự viết proxy hints. Spring AOT và các thư viện tích hợp có thể đăng ký metadata cần thiết. Chỉ bổ sung registrar khi có proxy combination tùy chỉnh hoặc khi diagnostics cho thấy metadata còn thiếu.

## 8. Interface introduction và nhiều advisor

Spring AOP có thể thêm interface vào proxy thông qua introduction/advisor. Khi đó proxy không chỉ triển khai interface nghiệp vụ ban đầu mà còn triển khai interface được giới thiệu.

Ví dụ một proxy có thể cần:

- `OrderOperations`: contract nghiệp vụ.
- `Auditable`: contract truy vấn audit id.
- `DecoratedObject`: contract do framework thêm vào.

Danh sách cuối cùng phụ thuộc cấu hình proxy factory, target và advisor. Khi đăng ký hint, phải căn cứ vào **danh sách interface thực tế của proxy cuối cùng**, không chỉ nhìn interface khai báo trên class implementation.

Nếu có nhiều biến thể advisor tạo các tổ hợp interface khác nhau, mỗi tổ hợp JDK proxy cần được kiểm tra và đăng ký tương ứng. Cách khác là chuẩn hóa proxy configuration để giảm số biến thể.

## 9. Classloader và visibility cũng là một phần của điều kiện tạo proxy

JDK dynamic proxy được tạo qua một classloader. Các interface phải nhìn thấy được trong ngữ cảnh classloader đó và đáp ứng quy tắc visibility/module. Hai interface cùng tên nhưng được nạp bởi hai classloader khác nhau vẫn có thể là hai Class object khác nhau.

Khi debug proxy, ghi nhận:

```java
for (Class<?> type : interfaces) {
    System.out.println(type.getName());
    System.out.println(type.getClassLoader());
    System.out.println(type.getModule());
}
```

Với Native Image, classloader behavior có thể khác ứng dụng JVM dùng plugin classloader phức tạp. Native Image phù hợp nhất với tập type và proxy được xác định trước khi build. Không nên kỳ vọng nạp interface mới từ plugin sau khi executable được tạo.

Proxy hint không sửa được lỗi interface không visible, module access không hợp lệ hoặc classloader tạo ra các Class object không tương thích. Những điều kiện Java này vẫn phải đúng khi tạo proxy.

## 10. Chuẩn hóa thứ tự interface khi tạo proxy

Nếu ứng dụng tự tạo proxy, hãy giữ danh sách interface tại một nơi và dùng cùng danh sách cho cả runtime factory lẫn hint registrar.

Ví dụ:

```java
final class ProxyContracts {

    static Class<?>[] paymentInterfaces() {
        return new Class<?>[] {
                PaymentService.class,
                Auditable.class
        };
    }
}
```

Runtime proxy factory:

```java
Proxy.newProxyInstance(
        PaymentService.class.getClassLoader(),
        ProxyContracts.paymentInterfaces(),
        handler
);
```

Registrar có thể gọi cùng helper để đăng ký:

```java
hints.proxies().registerJdkProxy(
        ProxyContracts.paymentInterfaces()
);
```

Chữ ký overload của `registerJdkProxy` cần kiểm tra theo Spring Framework version; các phiên bản hỗ trợ nhận varargs interface classes. Đảm bảo helper chỉ trả về danh sách ổn định, không phụ thuộc environment hoặc trạng thái runtime.

Nếu interface list được tạo từ cấu hình runtime không cố định, cần xác định trước mọi tổ hợp hợp lệ và đăng ký từng tổ hợp ở build time, hoặc thay đổi thiết kế để tập interface proxy ổn định.

## 11. Kiểm tra proxy interface list trước khi đăng ký hints

Có thể kiểm tra proxy class trên JVM:

```java
Class<?> proxyClass = proxy.getClass();

System.out.println(
        Arrays.toString(proxyClass.getInterfaces()));
```

Hoặc assertion:

```java
assertThat(proxy.getClass().getInterfaces())
        .containsExactly(
                PaymentService.class,
                Auditable.class
        );
```

`containsExactly` xác nhận cả nội dung và thứ tự. `containsExactlyInAnyOrder` chỉ xác nhận tập phần tử, không đủ để kiểm tra proxy metadata cần đúng thứ tự.

Đối với proxy do Spring tạo, có thể lấy bean từ ApplicationContext và kiểm tra:

```java
Object bean = context.getBean(OrderOperations.class);
Class<?>[] interfaces = bean.getClass().getInterfaces();
```

Proxy có thể được bọc qua nhiều lớp hoặc có interface được thêm bởi framework; kiểm tra đúng object cuối cùng mà code sử dụng. Không giả định danh sách interface chỉ gồm interface business.

## 12. Kiểm thử RuntimeHints proxy

Spring cung cấp `RuntimeHintsPredicates` để kiểm tra proxy hints. Ví dụ:

```java
@Test
void registersPaymentJdkProxy() {
    RuntimeHints hints = new RuntimeHints();

    new PaymentProxyHints().registerHints(
            hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.proxies()
            .forInterfaces(
                    PaymentService.class,
                    Auditable.class)
            .test(hints))
            .isTrue();
}
```

Predicate API có thể khác theo phiên bản Spring Framework; kiểm tra Javadoc/IDE của project để dùng đúng method. Điểm cần xác minh là đúng **tổ hợp và thứ tự** interface.

Unit test chỉ chứng minh registrar ghi metadata đúng. Nó chưa chứng minh Spring AOT đã thu thập registrar hoặc native executable tạo proxy thành công. Cần build native và chạy integration test tạo đúng proxy trên binary.

## 13. Chẩn đoán lỗi proxy trên Native Image

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Native không tạo được JDK proxy | Thiếu proxy hint cho interface combination | Đăng ký tổ hợp interface thực tế |
| Hint có cùng interface nhưng proxy vẫn lỗi | Thứ tự interface khác | So sánh danh sách theo `containsExactly` |
| JVM tạo proxy, native lỗi | Proxy được tạo động nhưng không có metadata AOT | Kiểm tra registrar và AOT output |
| Chỉ một bean proxy lỗi | Advisor/introduction tạo interface bổ sung | Kiểm tra interface list của proxy cuối |
| Lỗi class visibility | Interface không visible qua classloader/module | Sửa classloader/module configuration |
| Reflection trên target lỗi | Thiếu reflection metadata riêng | Đăng ký reflection hints bổ sung |
| Plugin interface mới không hoạt động | Interface chỉ xuất hiện sau khi build | Build lại image hoặc thay kiến trúc plugin |

Khi chẩn đoán, phân biệt lỗi tạo proxy với lỗi gọi method trên target. Proxy metadata có thể đúng nhưng target method vẫn lỗi vì reflection, access hoặc business logic.

## 14. Bài thực hành: proxy hai interface trong native image

**Bối cảnh:** ứng dụng Spring Boot có `OrderOperations` và `Auditable`. Một proxy factory tạo JDK proxy triển khai cả hai interface theo thứ tự cố định.

**Bước 1 — Tạo interface.** Khai báo hai interface với method độc lập và implementation phù hợp.

**Bước 2 — Tạo proxy trên JVM.** Dùng `Proxy.newProxyInstance` với danh sách `[OrderOperations, Auditable]`; kiểm tra proxy class interfaces bằng `containsExactly`.

**Bước 3 — Đăng ký RuntimeHints.** Viết `RuntimeHintsRegistrar` gọi `hints.proxies().registerJdkProxy(OrderOperations.class, Auditable.class)`.

**Bước 4 — Viết unit test.** Dùng RuntimeHintsPredicates kiểm tra đúng interface combination và thứ tự.

**Bước 5 — Tạo biến thể đảo thứ tự.** Tạo proxy `[Auditable, OrderOperations]`, xác nhận đây là một tổ hợp khác và không giả định hint ban đầu bao phủ biến thể này.

**Bước 6 — Build native.** Chạy Spring AOT và GraalVM Native Image; xác minh registrar được thu thập.

**Bước 7 — Chạy native integration test.** Tạo proxy, gọi method từ cả hai interface và xác nhận behavior giống JVM.

Tiêu chí hoàn thành: metadata proxy khớp chính xác interface list và thứ tự; mọi biến thể hợp lệ được đăng ký; native executable tạo và sử dụng proxy đúng.

## 15. Kết luận

JDK dynamic proxy được xác định bởi danh sách interface có thứ tự. Vì vậy, **thứ tự interface trong `RuntimeHints.proxies().registerJdkProxy(...)` phải khớp với thứ tự proxy thực tế được tạo**. Đăng ký từng interface riêng lẻ hoặc cùng tập interface theo thứ tự khác không thay thế metadata cho tổ hợp cần dùng.

Trong Spring Boot Native Image, hãy xác định interface list cuối cùng sau khi Spring AOP/advisor/introduction cấu hình proxy, giữ danh sách ổn định giữa registrar và runtime factory, kiểm tra bằng assertion có thứ tự và chạy native integration test. Proxy hints là một phần riêng của RuntimeHints, cần phối hợp với reflection hints khi target hoặc framework còn truy cập member bằng reflection.
