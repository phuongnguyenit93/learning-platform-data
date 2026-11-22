# Cách stubbing và verify khi spy nằm sau proxy

Trong ứng dụng Spring, bean được inject vào test có thể là một AOP proxy thay vì instance nghiệp vụ trực tiếp. Nếu target phía sau proxy là Mockito spy, test đang làm việc với hai lớp khác nhau: proxy Spring điều khiển advice như transaction, security hoặc logging; spy ghi nhận lời gọi và cho phép stubbing bằng Mockito.

Để stubbing và verify đúng, cần xác định object nào là proxy và object nào thực sự là spy. Thông thường, hãy dùng proxy được inject để gọi hành vi cần kiểm tra, lấy target spy bằng `AopTestUtils` để cấu hình stub và xác minh invocation. Cách này giữ cho lời gọi thực tế đi qua Spring advice trong khi Mockito theo dõi đúng target.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt Spring AOP proxy với Mockito spy.
- Mô tả đường đi của lời gọi khi spy nằm phía sau proxy.
- Lấy target object từ proxy bằng `AopTestUtils`.
- Dùng `doReturn`, `doThrow` và `doAnswer` để stubbing spy mà không gọi method thật trong lúc cấu hình.
- Verify invocation trên đúng Mockito spy.
- Gọi qua proxy để vẫn thực thi advice của Spring.
- Phân biệt lỗi khi verify proxy với lỗi khi verify target.
- Hiểu ảnh hưởng của JDK dynamic proxy, CGLIB, self-invocation và bean scope.
- Dùng `@MockitoSpyBean` hoặc annotation tương ứng của phiên bản dự án để spy bean trong Spring context.

## 1. Hai cơ chế khác nhau: Spring AOP proxy và Mockito spy

Spring AOP proxy và Mockito spy đều có thể đứng trước một đối tượng, nhưng chúng giải quyết hai vấn đề khác nhau.

**Spring AOP proxy** chặn lời gọi phương thức để chạy advice trước, sau hoặc xung quanh lời gọi target. Các tính năng như `@Transactional`, `@Cacheable`, method security và aspect tự viết thường hoạt động thông qua proxy.

**Mockito spy** là một test double dựa trên một đối tượng thật. Nếu chưa được stub, spy thường gọi implementation thật. Mockito có thể ghi nhận invocation, thay thế kết quả của một số method hoặc ném exception theo cấu hình test.

Khi spy nằm sau Spring proxy, cấu trúc thường có dạng:

~~~mermaid
flowchart LR
    T["Test"] --> P["Spring AOP proxy"]
    P --> A["Advice chain"]
    A --> S["Mockito spy (target)"]
    S --> R["Implementation thật"]
~~~

Lời gọi từ test đi qua proxy, advice chain rồi tới spy. Nếu method chưa được stub, spy gọi implementation thật. Nếu method đã được stub, spy trả về kết quả được cấu hình.

Hai đối tượng có vai trò riêng:

| Đối tượng | Vai trò | Thao tác thường dùng |
|---|---|---|
| Spring AOP proxy | Bảo đảm lời gọi đi qua advice | Gọi method cần kiểm tra |
| Mockito spy ở target | Ghi nhận invocation và áp dụng stub | Stubbing và verify |
| Implementation thật | Logic nghiệp vụ gốc | Được gọi khi spy không có stub phù hợp |

Không nên mặc định object được inject vào test chính là Mockito spy. Với bean có AOP, object đó có thể là proxy Spring bao quanh spy target.

## 2. Vì sao cần lấy target từ proxy?

Giả sử một service có transaction:

~~~java
@Service
public class InventoryService {

    @Transactional(readOnly = true)
    public int available(String sku) {
        // Đọc số lượng tồn kho từ nguồn dữ liệu.
        return 10;
    }
}
~~~

Khi Spring áp dụng transaction advice, bean được inject thường là một proxy. Test nhận được tham chiếu kiểu `InventoryService`, nhưng instance ở runtime có thể là JDK dynamic proxy hoặc CGLIB proxy.

Nếu test muốn cấu hình Mockito spy nằm ở target, nó cần tham chiếu tới chính target đó. Spring cung cấp tiện ích `AopTestUtils` trong package:

~~~java
import org.springframework.test.util.AopTestUtils;
~~~

Hai phương thức hữu ích:

- `AopTestUtils.getTargetObject(proxy)`: lấy target trực tiếp của một lớp proxy.
- `AopTestUtils.getUltimateTargetObject(proxy)`: đi qua các proxy lồng nhau để lấy target cuối cùng.

Ví dụ:

~~~java
InventoryService target =
    AopTestUtils.getUltimateTargetObject(inventoryService);
~~~

Nếu target là Mockito spy, có thể xác nhận bằng:

~~~java
assertTrue(Mockito.mockingDetails(target).isSpy());
~~~

Nếu kết quả là `false`, đừng tiếp tục gọi `when` hoặc `verify` trên object đó như thể nó là spy. Hãy kiểm tra cách bean được thay thế, annotation spy đã được áp dụng hay chưa và object nào thực sự được Mockito quản lý.

`getUltimateTargetObject` phù hợp với proxy có target source ổn định, thường gặp ở singleton bean. Với scoped proxy hoặc target source tạo target động theo từng lần gọi, việc lấy target một lần có thể không đại diện cho target được dùng ở request khác. Hãy hiểu scope của bean trước khi giữ target để stubbing hoặc verify.

## 3. Stubbing spy bằng doReturn để tránh gọi method thật

Với Mockito spy, cú pháp:

~~~java
when(spy.available("SKU-1")).thenReturn(3);
~~~

có thể gọi implementation thật của `available` ngay trong lúc thiết lập stub. Điều này có thể gây truy vấn database, gọi HTTP, ghi log hoặc tạo side effect trước khi test bắt đầu phần hành vi cần kiểm tra.

Khi spy nằm sau proxy, vấn đề còn rõ hơn: nếu gọi method thông qua proxy để stubbing, lời gọi có thể đi qua advice rồi mới đến target spy. Transaction hoặc side effect có thể xảy ra ngay trong bước cấu hình.

Dùng cú pháp `doReturn(...).when(spy)...` để cài stub mà không cần gọi method thật:

~~~java
doReturn(3)
    .when(targetSpy)
    .available("SKU-1");
~~~

Các dạng do-style khác:

~~~java
doThrow(new IllegalStateException("Inventory unavailable"))
    .when(targetSpy)
    .refresh();

doNothing()
    .when(targetSpy)
    .clearCache();

doAnswer(invocation -> {
    String sku = invocation.getArgument(0);
    return sku.equals("SKU-1") ? 3 : 0;
}).when(targetSpy).available(anyString());
~~~

Chọn cách stubbing theo hành vi cần mô phỏng:

| Cú pháp | Mục đích |
|---|---|
| `doReturn(value)` | Trả về giá trị đã định |
| `doThrow(exception)` | Ném exception |
| `doNothing()` | Không thực hiện hành vi của method void |
| `doAnswer(answer)` | Tính kết quả từ invocation |
| `doCallRealMethod()` | Yêu cầu spy gọi implementation thật cho method đó |

Với spy, `doReturn` thường là lựa chọn dễ kiểm soát nhất khi method thật có side effect hoặc khi target nằm sau proxy.

## 4. Ví dụ hoàn chỉnh với ProxyFactory và Mockito spy

Có thể minh họa cơ chế mà không cần khởi động toàn bộ ứng dụng bằng cách tạo một Spring AOP proxy trực tiếp. Ví dụ này cho thấy test stubbing target spy nhưng gọi method qua proxy.

Interface và implementation:

~~~java
public interface InventoryService {
    int available(String sku);
}

public class DefaultInventoryService implements InventoryService {

    @Override
    public int available(String sku) {
        // Implementation thật trong ứng dụng có thể truy vấn repository.
        return 10;
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;

import java.util.concurrent.atomic.AtomicInteger;

import org.aopalliance.intercept.MethodInterceptor;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.test.util.AopTestUtils;

class InventoryProxySpyTest {

    @Test
    void stubsAndVerifiesTargetSpyThroughSpringProxy() {
        InventoryService targetSpy =
            Mockito.spy(new DefaultInventoryService());

        AtomicInteger adviceCalls = new AtomicInteger();

        ProxyFactory factory = new ProxyFactory();
        factory.setTarget(targetSpy);
        factory.setInterfaces(InventoryService.class);
        factory.addAdvice((MethodInterceptor) invocation -> {
            adviceCalls.incrementAndGet();
            return invocation.proceed();
        });

        InventoryService proxy =
            (InventoryService) factory.getProxy();

        InventoryService unwrapped =
            AopTestUtils.getUltimateTargetObject(proxy);

        assertSame(targetSpy, unwrapped);
        assertTrue(Mockito.mockingDetails(unwrapped).isSpy());

        doReturn(3)
            .when(unwrapped)
            .available("SKU-1");

        int result = proxy.available("SKU-1");

        assertEquals(3, result);
        verify(unwrapped).available("SKU-1");
        assertEquals(1, adviceCalls.get());
    }
}
~~~

Luồng của test:

1. Mockito tạo spy từ implementation thật.
2. `ProxyFactory` đặt spy làm target và tạo Spring AOP proxy.
3. `AopTestUtils.getUltimateTargetObject(proxy)` trả về target spy.
4. `doReturn` cấu hình kết quả cho target mà không gọi method thật.
5. Test gọi `proxy.available(...)`, nên advice vẫn chạy.
6. Proxy chuyển lời gọi tới target spy; spy trả về giá trị stub và ghi nhận invocation.
7. Test verify target spy và kiểm tra advice đã được gọi.

Ví dụ này thể hiện nguyên tắc quan trọng: dùng target để cấu hình và quan sát Mockito, dùng proxy để thực thi đường đi của ứng dụng.

## 5. Áp dụng trong Spring test với @MockitoSpyBean

Trong Spring Framework 6.2 trở lên, có thể dùng `@MockitoSpyBean` để yêu cầu Spring tạo spy từ bean hiện có trong context. Ví dụ:

~~~java
@SpringBootTest
class InventoryServiceIntegrationTest {

    @MockitoSpyBean
    InventoryService inventoryService;

    @Test
    void stubsTargetAndInvokesThroughAopProxy() {
        InventoryService target =
            AopTestUtils.getUltimateTargetObject(inventoryService);

        assertTrue(Mockito.mockingDetails(target).isSpy());

        doReturn(3)
            .when(target)
            .available("SKU-1");

        int result = inventoryService.available("SKU-1");

        assertEquals(3, result);
        verify(target).available("SKU-1");
    }
}
~~~

Ở ví dụ này, `inventoryService` là tham chiếu được Spring cung cấp cho test. Nếu bean được AOP proxy, hãy lấy target cuối cùng rồi xác nhận target đó thực sự là Mockito spy.

Trong dự án Spring Boot cũ, có thể gặp `@SpyBean` từ package `org.springframework.boot.test.mock.mockito`. Annotation và hành vi hỗ trợ phụ thuộc phiên bản Spring Boot/Spring Framework của dự án. Hãy dùng annotation có sẵn trong dependency hiện tại; không thêm đồng thời hai cơ chế spy cho cùng bean.

Nếu context có nhiều bean cùng kiểu, hãy xác định bean bằng qualifier hoặc tên bean rõ ràng. Spy cần được áp dụng lên đúng bean mà service đang sử dụng. Nếu service nhận một implementation khác, việc stubbing bean không được sử dụng sẽ không ảnh hưởng kết quả.

## 6. Verify trên target spy, không mặc định verify trên proxy

Mockito `verify` cần một mock hoặc spy mà Mockito quản lý. Spring AOP proxy tự nó không nhất thiết là Mockito spy.

Nếu gọi:

~~~java
verify(inventoryService).available("SKU-1");
~~~

và `inventoryService` chỉ là Spring AOP proxy, Mockito có thể ném `NotAMockException`. Trong cấu trúc proxy bao quanh spy, hãy verify target:

~~~java
InventoryService target =
    AopTestUtils.getUltimateTargetObject(inventoryService);

verify(target).available("SKU-1");
~~~

Có thể kiểm tra object trước khi verify:

~~~java
assertTrue(Mockito.mockingDetails(target).isSpy());
verify(target).available("SKU-1");
~~~

Không nên giả định mọi proxy đều không thể verify. Trong một số cấu hình, object được inject có thể chính là Mockito spy hoặc một proxy được cấu hình hỗ trợ tương tác với target. Cách chắc chắn là kiểm tra object thực tế bằng `Mockito.mockingDetails(...)` và lấy target khi spy nằm phía sau Spring AOP proxy.

Nếu cần xác nhận advice chạy, verify target spy là chưa đủ. Spy ghi nhận lời gọi method ở target; nó không chứng minh một transaction đã commit hoặc security advice đã từ chối request. Hãy kiểm tra tác động của advice bằng assertion phù hợp, chẳng hạn trạng thái transaction, audit event hoặc kết quả bảo mật.

## 7. Stubbing và verify method void

Với method void, dùng `doNothing`, `doThrow` hoặc `doAnswer` trên target spy.

Ví dụ:

~~~java
public interface InventoryService {
    void refresh(String sku);
}
~~~

Cấu hình không gọi method thật trong lúc stubbing:

~~~java
doNothing()
    .when(target)
    .refresh("SKU-1");
~~~

Sau đó gọi qua proxy:

~~~java
proxy.refresh("SKU-1");

verify(target).refresh("SKU-1");
~~~

Nếu muốn mô phỏng lỗi:

~~~java
doThrow(new IllegalStateException("Refresh failed"))
    .when(target)
    .refresh("SKU-1");

assertThrows(
    IllegalStateException.class,
    () -> proxy.refresh("SKU-1")
);

verify(target).refresh("SKU-1");
~~~

Nếu method void thật sự cần chạy trong test, không cần stub nó. Gọi qua proxy và verify invocation hoặc side effect mong muốn. Chỉ stub khi muốn thay đổi hành vi thật ở một điểm có chủ đích.

## 8. Phân biệt stubbing qua proxy và stubbing trực tiếp target

Hai cách gọi có thể tạo ra kết quả khác nhau:

~~~java
// Cấu hình trực tiếp target spy:
doReturn(3).when(targetSpy).available("SKU-1");

// Thực thi qua Spring proxy:
int result = serviceProxy.available("SKU-1");
~~~

Khi cấu hình trực tiếp target, test không đi qua Spring advice. Đây là điều mong muốn trong bước stubbing vì ta chỉ đang cài hành vi Mockito.

Khi thực thi qua proxy, advice được chạy rồi lời gọi mới tới target spy. Đây là đường đi cần thiết nếu test muốn giữ transaction, cache, security hoặc aspect.

Nếu gọi trực tiếp target để kiểm tra hành vi:

~~~java
int result = targetSpy.available("SKU-1");
~~~

thì Spring AOP advice không chạy. Test chỉ kiểm tra Mockito spy và implementation phía sau nó.

Vì vậy, hãy tách rõ hai mục đích:

| Giai đoạn | Object nên dùng | Lý do |
|---|---|---|
| Stubbing | Target spy | Cấu hình đúng Mockito object |
| Thực thi hành vi có AOP | Spring proxy | Giữ advice trong call chain |
| Verify invocation của target | Target spy | Mockito ghi nhận lời gọi tại spy |
| Verify tác động của advice | Kết quả hoặc trạng thái advice | Chứng minh phần AOP thực sự chạy |

## 9. JDK dynamic proxy và CGLIB ảnh hưởng thế nào?

Spring AOP thường dùng một trong hai kiểu proxy:

- **JDK dynamic proxy:** proxy triển khai các interface của target. Consumer thường tương tác qua interface.
- **CGLIB proxy:** proxy là subclass của class target và override các method có thể được proxy.

Việc chọn kiểu proxy không thay đổi nguyên tắc lấy target spy, nhưng ảnh hưởng tới kiểu tham chiếu và method có thể được intercept.

Với JDK proxy, hãy inject và gọi qua interface:

~~~java
@Autowired
InventoryService inventoryService;
~~~

Không nên ép object JDK proxy thành class implementation cụ thể:

~~~java
DefaultInventoryService service =
    (DefaultInventoryService) inventoryService;
~~~

Phép cast này có thể thất bại vì proxy chỉ triển khai interface.

Với CGLIB, proxy là subclass của class target, nhưng vẫn không có nghĩa object proxy là Mockito spy. Hãy kiểm tra target bằng `AopTestUtils` và Mockito mocking details thay vì suy luận từ class runtime.

Spring AOP proxy cũng có giới hạn về method được intercept. JDK proxy chỉ xử lý lời gọi qua interface; CGLIB không thể override method final hoặc private. Nếu method không nằm trong phạm vi proxy, test có thể gọi implementation mà không chạy advice mong đợi.

## 10. Self-invocation và lời gọi nội bộ

Spring AOP dựa trên proxy. Một lời gọi từ bên ngoài đi qua proxy có thể kích hoạt advice. Nhưng nếu method trong target gọi một method khác trên chính `this`, lời gọi nội bộ đó thường không quay lại proxy.

Ví dụ:

~~~java
@Service
public class OrderService {

    public void placeOrder() {
        validateOrder();
    }

    @Transactional
    public void validateOrder() {
        // Logic kiểm tra.
    }
}
~~~

Khi consumer gọi `placeOrder()` qua proxy, Spring có thể intercept `placeOrder`. Nhưng lời gọi `this.validateOrder()` bên trong target không đi qua proxy lần nữa, nên transaction advice trên `validateOrder` không được kích hoạt chỉ nhờ lời gọi nội bộ đó.

Mockito spy có thể ghi nhận một số lời gọi nội bộ tùy cách spy và method dispatch hoạt động, nhưng điều đó không chứng minh Spring AOP advice đã chạy. Hãy kiểm tra riêng invocation của spy và tác động của advice.

Nếu cần advice áp dụng cho một method, hãy tổ chức lời gọi qua bean/proxy phù hợp hoặc xem lại cấu trúc service để lời gọi đi qua proxy một cách tự nhiên.

## 11. Các vấn đề với scoped proxy và target động

Một singleton AOP proxy thường trỏ tới một target ổn định. Với request scope, session scope hoặc prototype, proxy có thể chọn target khác nhau tùy ngữ cảnh hoặc từng lần gọi.

Trong trường hợp đó, lấy target một lần:

~~~java
Object target = AopTestUtils.getUltimateTargetObject(proxy);
~~~

không đảm bảo target được dùng ở request tiếp theo là cùng instance. Việc giữ một target spy trong test có thể khiến stubbing và verify không phản ánh invocation của target thực tế.

Trước khi dùng `AopTestUtils`, hãy xác định:

- Bean có phải singleton không?
- TargetSource có ổn định không?
- Proxy có tạo target theo request hoặc session không?
- Test có chạy trong đúng scope cần thiết không?
- Target được lấy ra có còn là instance được proxy dùng ở lần gọi sau không?

Với scoped bean, hãy dùng test scope phù hợp và kiểm tra object thực tế trong cùng scope. Tránh giữ target của một request rồi dùng nó để verify request khác.

## 12. Các lỗi thường gặp

- **Gọi `verify` trên Spring proxy:** proxy không nhất thiết là Mockito spy. Lấy target bằng `AopTestUtils` rồi verify object Mockito quản lý.
- **Dùng `when(spy.method())` khi method có side effect:** Mockito có thể gọi implementation thật trong lúc cấu hình. Dùng `doReturn`, `doThrow` hoặc do-style tương ứng.
- **Stubbing qua proxy và vô tình chạy advice:** lời gọi cấu hình có thể đi qua transaction, security hoặc aspect. Cấu hình trực tiếp target spy.
- **Gọi target thay vì proxy trong phần thực thi:** test bỏ qua Spring AOP advice. Hãy gọi bean proxy nếu muốn kiểm tra đường đi production.
- **Cho rằng spy và proxy là cùng một object:** dùng `Mockito.mockingDetails` và `AopTestUtils` để xác định rõ từng lớp.
- **Dùng `Mockito.spy` trực tiếp trên proxy Spring:** spy có thể làm thay đổi cách proxy và target hoạt động. Ưu tiên cơ chế spy bean của Spring hoặc spy target có chủ đích.
- **Ép kiểu JDK proxy thành implementation class:** JDK proxy thường chỉ triển khai interface. Inject và sử dụng interface.
- **Verify spy rồi kết luận transaction đã chạy:** invocation trên target không chứng minh advice thành công. Kiểm tra tác động của advice riêng.
- **Bỏ qua self-invocation:** lời gọi nội bộ trong target thường không quay lại proxy nên advice có thể không chạy.
- **Lấy target từ scoped proxy rồi giữ lâu:** target có thể thay đổi theo request hoặc scope.
- **Spy nhầm bean:** khi có nhiều implementation, cần xác định đúng bean bằng qualifier hoặc bean name.
- **Stubbing một method không được proxy intercept:** kiểm tra interface, method visibility, final modifier và loại proxy.

## 13. Quy trình stubbing và verify khi spy nằm sau proxy

Khi test cần spy một bean có Spring AOP, hãy làm theo trình tự:

1. Xác định bean được inject có phải Spring AOP proxy không.
2. Xác định cách bean được spy: `@MockitoSpyBean`, annotation spy của Spring Boot hoặc cấu hình Mockito riêng.
3. Lấy target bằng `AopTestUtils.getUltimateTargetObject(...)` khi target source ổn định.
4. Dùng `Mockito.mockingDetails(target).isSpy()` để xác nhận target thực sự là spy.
5. Cấu hình stub trên target bằng `doReturn`, `doThrow`, `doNothing` hoặc `doAnswer`.
6. Gọi method thông qua bean proxy để advice vẫn chạy.
7. Verify invocation trên target spy.
8. Kiểm tra tác động của advice bằng assertion riêng, không suy luận từ verify của Mockito.
9. Nếu không tìm thấy target spy, kiểm tra annotation spy, bean selection và context configuration.
10. Nếu bean có scope động, xác định target trong đúng scope và không dùng một target cũ cho invocation khác.

## Kết luận

Khi Mockito spy nằm phía sau Spring AOP proxy, hai lớp có trách nhiệm khác nhau. Proxy đảm nhiệm advice của Spring; spy ở target ghi nhận invocation và áp dụng stubbing. Dùng `AopTestUtils.getUltimateTargetObject(...)` để lấy target khi phù hợp, cấu hình spy bằng `doReturn` hoặc do-style tương ứng, gọi hành vi qua proxy và verify trên target spy.

Cách phân chia này giúp test kiểm soát được kết quả của một method mà vẫn giữ đường đi qua transaction, security, cache hoặc aspect. Hãy xác nhận object thực tế bằng Mockito và Spring utilities, đặc biệt khi dự án dùng nhiều lớp proxy hoặc bean scope động.

