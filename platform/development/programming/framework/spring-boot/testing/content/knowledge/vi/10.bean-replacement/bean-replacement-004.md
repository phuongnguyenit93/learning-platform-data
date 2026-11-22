# Thêm mock khi thiếu bean so với bắt buộc thay bean đã tồn tại

Trong kiểm thử Spring Boot, **thêm một mock khi context thiếu bean** và **thay một bean đã tồn tại bằng mock** là hai chủ đích khác nhau. Một bài test slice có thể cố ý không tải adapter thật, nên bổ sung một mock là hợp lý. Nhưng bài test kiểm chứng cấu hình ứng dụng phải phát hiện bean bị thiếu; nếu mock được tự tạo, test có thể xanh dù production wiring sai.

Spring TestContext hỗ trợ cách diễn đạt rõ ràng bằng `@MockitoBean`:

- **`@MockitoBean` mặc định:** sử dụng chiến lược `REPLACE_OR_CREATE` — nếu có bean phù hợp thì thay thế, nếu không có thì tạo một bean Mockito mới.
- **`@MockitoBean(enforceOverride = true)`:** sử dụng chiến lược `REPLACE` — yêu cầu bean phù hợp đã có trong context; nếu không có thì **quá trình khởi tạo test context phải thất bại**.
- **`@MockitoSpyBean`:** sử dụng chiến lược `WRAP` — cần có bean gốc phù hợp để bọc thành spy; không phải phương án thay thế trực tiếp của hai chế độ trên.

Đây là kiến thức trọng tâm thuộc nhóm **Thay thế bean**. Một test xanh với `@MockitoBean` mặc định chứng minh ứng dụng *trong context của test sau khi thêm mock* chạy được, **không tự chứng minh rằng production đã đăng ký bean ấy**.

Ví dụ và API bên dưới nhắm tới **Java 17+, Spring Framework 6.2+ và Spring Boot 3.4+**; với Spring Boot 4.x, dùng annotation thuộc Spring TestContext thay vì `@MockBean` cũ đã bị loại bỏ.

## 1. Vấn đề cần giải quyết

Giả sử ứng dụng có một service:

```text
OrderController
      |
      v
OrderNotifier  ---->  ReceiptGateway
                          |
                          v
                  REST/Email adapter thật
```

`OrderNotifier` cần `ReceiptGateway` trong constructor. Từ đây có hai mục tiêu test hợp lý:

**Mục tiêu A — test logic service/controller:** không muốn gọi API gửi biên nhận thật, có thể chưa đưa adapter vào slice. Test chỉ cần một `ReceiptGateway` mock để service xử lý request. **Cho phép tạo mock nếu chưa có bean** là phù hợp.

**Mục tiêu B — test cấu hình ứng dụng:** dự án phải có một adapter `ReceiptGateway` được đăng ký theo đúng profile. Ta vẫn muốn thay adapter để tránh gửi email/API trong test, **nhưng nếu adapter production biến mất, test phải đỏ**. Lúc này bắt buộc dùng chế độ `enforceOverride = true` trong context thực sự chứa những bean cần xác minh.

Một nhầm lẫn thường thấy là đặt `@MockitoBean` lên mọi collaborator trong `@SpringBootTest`, rồi từ kết quả xanh kết luận “Spring wiring chuẩn”. Mặc định annotation có thể **che chính lỗi thiếu bean**.

## 2. Bean overriding diễn ra ở đâu?

Spring TestContext tạo hoặc tùy chỉnh `ApplicationContext` trước khi chạy các method `@Test`. Cơ chế bean overriding tham gia vào quá trình chuẩn bị bean, không phải một lệnh gọi `Mockito.when(...)` bên trong test method.

Bảng chiến lược:

| Strategy | Bean phù hợp tồn tại | Bean phù hợp không tồn tại | Ý nghĩa |
| --- | --- | --- | --- |
| `REPLACE_OR_CREATE` | Thay bean bằng override instance | Tạo bean mới | Cho phép thiếu bean |
| `REPLACE` | Thay bean bằng override instance | Lỗi khi chuẩn bị context | Bắt buộc bean gốc tồn tại |
| `WRAP` | Bọc bean gốc | Không thể bọc bean vắng mặt | Cần bean thật để quan sát/chạy một phần hành vi |

`@MockitoBean` mặc định ánh xạ sang `REPLACE_OR_CREATE`. Bật `enforceOverride = true` chọn `REPLACE`. `@MockitoSpyBean` có hành vi `WRAP` và thường yêu cầu đúng **một** candidate bean phù hợp.

So sánh ngắn:

```java
@MockitoBean
ReceiptGateway gateway; // REPLACE_OR_CREATE
```

```java
@MockitoBean(enforceOverride = true)
ReceiptGateway gateway; // REPLACE, phải có bean
```

```java
@MockitoSpyBean
ReceiptGateway gateway; // WRAP, gọi method thật nếu không stub
```

Những snippet này là các phương án **thay thế nhau**, không đặt cả ba trên cùng một field. Khi cần dùng spy, nhớ rằng method thật có thể phát sinh network/database side effect.

**Sơ đồ lựa chọn:**

```text
Bạn muốn kiểm tra điều gì?
         |
         +-- Logic đơn thuần, không Spring?
         |       --> Mockito @Mock hoặc mock(...) + new Service(...)
         |
         +-- Test slice cố ý thiếu collaborator?
         |       --> @MockitoBean (mặc định)
         |
         +-- Bean BẮT BUỘC có trong context hiện tại?
         |       --> @MockitoBean(enforceOverride = true)
         |
         +-- Bean có thật, muốn giữ hành vi thật một phần?
                 --> @MockitoSpyBean khi phù hợp
```

## 3. @Mock khác gì @MockitoBean?

Trong unit test Java thuần:

```java
@ExtendWith(MockitoExtension.class)
class OrderNotifierUnitTest {
    @Mock ReceiptGateway gateway;

    @Test
    void canSend() {
        OrderNotifier service = new OrderNotifier(gateway);
        // when(gateway.send(...)) rồi assert...
    }
}
```

Đoạn trên minh họa cấu trúc, chưa phải test độc lập vì thiếu imports và assertion. Điểm chính: `@Mock` tạo Mockito object khi được `MockitoExtension` xử lý. Nó **không đăng ký Spring bean**. Test tự xây service bằng `new` và truyền mock vào constructor.

Ngược lại:

```java
@SpringJUnitConfig(SomeConfig.class)
class OrderNotifierContextTest {
    @MockitoBean
    ReceiptGateway gateway;

    @Autowired
    OrderNotifier service;
}
```

Đây cũng là đoạn minh họa cần `SomeConfig` thật. `@MockitoBean` được Spring TestContext xử lý, nên mock vừa là Mockito object vừa có mặt trong `ApplicationContext` để bean `OrderNotifier` có thể inject.

| Công cụ | Có Mockito mock? | Spring context thấy được? | Bắt buộc bean production tồn tại? |
| --- | --- | --- | --- |
| `Mockito.mock(...)` | Có | Không | Không |
| `@Mock` của Mockito | Có, khi khởi tạo đúng | Không | Không |
| `@MockitoBean` | Có | Có | Không |
| `@MockitoBean(enforceOverride=true)` | Có | Có | **Có, trong context được nạp** |
| `@MockitoSpyBean` | Spy | Có | Cần bean phù hợp để bọc |

Đừng thêm `@SpringBootTest` chỉ để có Mockito mock nếu đang test service bằng constructor injection. Ngược lại, đừng nhầm `@Mock` với một Spring bean khi đang cần resolve dependency của bean trong context.

## 4. Ví dụ hoàn chỉnh: cùng một service, hai chiến lược

**Hợp đồng nghiệp vụ:**

- `OrderNotifier.sendReceipt(orderId)` yêu cầu mã đơn không null/blank.
- Với mã hợp lệ, service gọi `ReceiptGateway.send(orderId)` và trả về chuỗi phản hồi.
- Adapter thật trả `real:ORD-7`.
- Test mock trả `mock:ORD-7`.
- Ta tách riêng **một context không khai báo gateway** và **một context đã có gateway bean** để thấy khác biệt.

Cấu trúc:

```text
src/
├── main/java/example/testing/beans/
│   ├── OrderNotifier.java
│   └── OrderNotifierDemo.java
└── test/java/example/testing/beans/
    ├── CreateIfAbsentTest.java
    └── ReplaceExistingTest.java
```

### 4.1. File production OrderNotifier.java

Tạo `src/main/java/example/testing/beans/OrderNotifier.java`:

```java
package example.testing.beans;

import java.util.Objects;

public final class OrderNotifier {
    private final ReceiptGateway gateway;

    public OrderNotifier(ReceiptGateway gateway) {
        this.gateway = Objects.requireNonNull(
                gateway, "gateway");
    }

    public String sendReceipt(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }
        return gateway.send(orderId);
    }
}

interface ReceiptGateway {
    String send(String orderId);
}

final class RealReceiptGateway implements ReceiptGateway {
    @Override
    public String send(String orderId) {
        return "real:" + orderId;
    }
}
```

Mã này chạy với JDK 17+: file có đúng một top-level `public` là `OrderNotifier`; các kiểu còn lại package-private và dùng được từ các test **cùng package**. Trong dự án lớn, nên tách interface/adapter thành file riêng và cấp mức truy cập phù hợp khi có class ở package khác.

Service **không gắn `@Service`** vì cả hai test sẽ khai báo bean bằng `@Bean`. Điều quan trọng ở đây không phải Spring scan class nào, mà là TestContext có **bean definition** `ReceiptGateway` hay không. Đừng vô tình thêm `@Component` vào adapter của trường hợp A, bởi như vậy sẽ làm mất ý nghĩa “context thiếu bean”.

### 4.2. Trường hợp A: thiếu bean vẫn tạo được mock

Tạo `src/test/java/example/testing/beans/CreateIfAbsentTest.java`:

```java
package example.testing.beans;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(CreateIfAbsentTest.Config.class)
class CreateIfAbsentTest {

    // REPLACE_OR_CREATE: không có gateway bean thì tạo mock.
    @MockitoBean
    private ReceiptGateway receiptGateway;

    @Autowired
    private OrderNotifier notifier;

    @Autowired
    private ApplicationContext context;

    @Test
    void createsMockWhenGatewayBeanDoesNotExist() {
        when(receiptGateway.send("ORD-7"))
                .thenReturn("mock:ORD-7");

        String actual = notifier.sendReceipt("ORD-7");

        assertEquals("mock:ORD-7", actual);
        verify(receiptGateway).send("ORD-7");
        assertSame(receiptGateway,
                context.getBean(ReceiptGateway.class));
        assertTrue(
                Mockito.mockingDetails(receiptGateway).isMock());
    }

    @Test
    void invalidIdIsRejectedBeforeCallingMock() {
        assertThrows(IllegalArgumentException.class,
                () -> notifier.sendReceipt(" "));
        verifyNoInteractions(receiptGateway);
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        // KHÔNG có @Bean ReceiptGateway ở context này.
        @Bean
        OrderNotifier orderNotifier(ReceiptGateway gateway) {
            return new OrderNotifier(gateway);
        }
    }
}
```

**Vì sao class này pass dù thiếu gateway?** Trước khi Spring tạo `OrderNotifier`, bean override infrastructure nhìn thấy field `@MockitoBean`, tạo mock `ReceiptGateway` với strategy `REPLACE_OR_CREATE` và đăng ký vào context. Constructor của `OrderNotifier` nhận mock đó. Test stub và verify một lời gọi đúng; test thứ hai xác nhận validation xảy ra trước khi truy cập gateway.

Nếu xóa annotation `@MockitoBean` mà không cung cấp bean tương ứng, Spring thường sẽ không tạo được `OrderNotifier` do constructor dependency bị thiếu. Đó là một khác biệt cấu trúc — không phải do assertion trong method test.

**Kết luận đúng:** “Một context chỉ có `OrderNotifier`, sau khi bổ sung mock `ReceiptGateway`, có thể chạy logic mong muốn.” Kết luận **sai:** “Production đã có adapter `ReceiptGateway`.”

### 4.3. Trường hợp B: bắt buộc thay bean đã tồn tại

Tạo `src/test/java/example/testing/beans/ReplaceExistingTest.java`:

```java
package example.testing.beans;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(ReplaceExistingTest.Config.class)
class ReplaceExistingTest {

    // REPLACE: bắt buộc có bean phù hợp trước khi thay.
    @MockitoBean(enforceOverride = true)
    private ReceiptGateway receiptGateway;

    @Autowired
    private OrderNotifier notifier;

    @Autowired
    private ApplicationContext context;

    @Test
    void replacesPreviouslyRegisteredGatewayBean() {
        when(receiptGateway.send("ORD-7"))
                .thenReturn("mock:ORD-7");

        String actual = notifier.sendReceipt("ORD-7");

        assertEquals("mock:ORD-7", actual);
        assertNotEquals("real:ORD-7", actual);
        verify(receiptGateway).send("ORD-7");
        assertSame(receiptGateway,
                context.getBean(ReceiptGateway.class));
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        ReceiptGateway receiptGateway() {
            return new RealReceiptGateway();
        }

        @Bean
        OrderNotifier orderNotifier(ReceiptGateway gateway) {
            return new OrderNotifier(gateway);
        }
    }
}
```

Ở đây `Config.receiptGateway()` định nghĩa sẵn một bean của loại `ReceiptGateway`. `@MockitoBean(enforceOverride = true)` tìm đúng bean này và thay thế bằng Mockito mock. Vì vậy, `OrderNotifier` nhận mock; test không gọi implementation thật.

**Ý nghĩa của strict:** nếu `@Bean ReceiptGateway receiptGateway()` bị xóa, nhưng vẫn còn `OrderNotifier` yêu cầu gateway, Spring TestContext không được tự “cứu” bằng cách đăng ký mock. Nó phải fail ở giai đoạn chuẩn bị context, báo hiệu không còn bean để thay.

**Giới hạn bằng chứng:** ví dụ này chỉ chứng minh bean trong **cấu hình fixture của test** tồn tại và bị thay thành công. Muốn chứng minh **cấu hình production** có bean tương ứng, hãy dùng context nạp configuration production thích hợp; không nên tự khai báo một bean test để làm `enforceOverride=true` pass rồi tuyên bố production wiring đúng.

### 4.4. Negative example: strict fail khi không có bean

Giả sử dùng lại `CreateIfAbsentTest.Config` (chỉ định nghĩa `OrderNotifier`), nhưng chuyển annotation sang strict.

**Ví dụ cố tình không chạy thành công; không đưa vào suite cần xanh:**

```java
@SpringJUnitConfig(CreateIfAbsentTest.Config.class)
class StrictWithoutBeanTest {

    @MockitoBean(enforceOverride = true)
    ReceiptGateway receiptGateway;

    @Test
    void cannotReachTestBodyWhenContextCannotStart() {
        // Không có bean ReceiptGateway để REPLACE.
    }
}
```

Đây là đoạn class minh họa đặt cùng package với các test ở trên; imports tương tự test trước. Kết quả mong muốn khi chạy riêng là **ApplicationContext không được tạo vì không tìm thấy bean cần override**, nên method `@Test` không được thực thi. Không nên gọi việc “test method không chạy” là lỗi assertion; đây là lỗi **setup context** đúng ý nghĩa fail-fast.

Thử nghiệm tư duy:

```text
Context thiếu ReceiptGateway
          |
          +-- @MockitoBean
          |     --> Spring tạo mock ReceiptGateway
          |     --> OrderNotifier được tạo
          |     --> test methods có thể chạy
          |
          +-- @MockitoBean(enforceOverride = true)
                --> Spring cố tìm bean để REPLACE
                --> Không thấy -> lỗi tạo context
                --> test method chưa được chạy
```

Nếu chỉ cần quan sát sự khác biệt, hai class test xanh và negative snippet là đủ. **Không cần làm test production luôn đỏ** để chứng minh một ý tưởng; dùng strict mode đúng nơi mới là thực hành lâu dài.

### 4.5. Cấu hình Gradle và chạy test

Trong một dự án Spring Boot đã có Gradle plugin/repositories và dependency management phù hợp, phần liên quan ở `build.gradle` (Groovy DSL) là:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung** vào một project Spring Boot hoàn chỉnh. Nó không tự chứa phiên bản plugin/Java toolchain. Cần một bộ dependencies tương thích với `org.springframework.test.context.bean.override.mockito.MockitoBean`, tức Spring Framework 6.2+; các dòng Spring Boot 3.4/3.5 và 4.x hỗ trợ cơ chế mới thông qua phiên bản Framework tương ứng.

Chạy hai class dự kiến xanh:

```bash
./gradlew test --tests example.testing.beans.CreateIfAbsentTest
./gradlew test --tests example.testing.beans.ReplaceExistingTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.beans.CreateIfAbsentTest"
.\gradlew.bat test --tests "example.testing.beans.ReplaceExistingTest"
```

**Kỳ vọng:** hai test ở `CreateIfAbsentTest` và một test ở `ReplaceExistingTest` đều pass; tổng **3 test methods**. Output Gradle/JUnit tùy phiên bản và cấu hình nên không có một chuỗi stdout chuẩn. Kiểm tra test report để đối chiếu kết quả từng method.

**Không chạy chung `StrictWithoutBeanTest`** vào bộ pass thông thường: class đó là minh họa fail-fast và phải thất bại ở bước tạo context. Nếu muốn biến việc thiếu bean thành một assertion `assertThrows` có thể pass, cần thiết kế riêng một test điều khiển quá trình bootstrap context trong mã Java, không đơn giản đặt `assertThrows` bên trong method chưa được gọi.

### 4.6. Kiểm tra logic Java bằng javac/java

Để tách logic service khỏi việc override bean, tạo `src/main/java/example/testing/beans/OrderNotifierDemo.java`:

```java
package example.testing.beans;

public class OrderNotifierDemo {
    public static void main(String[] args) {
        ReceiptGateway real = new RealReceiptGateway();
        OrderNotifier notifier = new OrderNotifier(real);

        System.out.println(notifier.sendReceipt("ORD-7"));

        try {
            notifier.sendReceipt(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Từ thư mục gốc project:

```bash
javac -d out src/main/java/example/testing/beans/OrderNotifier.java src/main/java/example/testing/beans/OrderNotifierDemo.java
java -cp out example.testing.beans.OrderNotifierDemo
```

Stdout chính xác:

```text
real:ORD-7
orderId must not be blank
```

Demo Java thuần **không chạy JUnit hay Spring TestContext**; nó chỉ chứng minh service và adapter thật hoạt động không cần container. Hai chiến lược `REPLACE_OR_CREATE` và `REPLACE` được minh họa bởi các class test Spring ở mục 4.2–4.3.

## 5. Quyết định đúng trong Spring Boot slice và integration tests

### 5.1. @WebMvcTest: thêm mock bị thiếu thường là chủ đích

`@WebMvcTest` tập trung vào MVC layer. Một controller có constructor yêu cầu service có thể cần một mock vì service thật nằm **ngoài slice**. Dùng `@MockitoBean` mặc định là hợp lý:

```java
@WebMvcTest(OrderController.class)
class OrderControllerWebTest {

    @MockitoBean
    OrderApplicationService service;

    @Autowired
    MockMvc mockMvc;

    // Test status, binding, validation, JSON...
}
```

Đây là **đoạn class minh họa**, chưa chạy độc lập vì `OrderController`/`OrderApplicationService` chưa định nghĩa và chưa có method assertion. Test thực tế phải cấu hình security khi cần, gửi request và kiểm tra response. Điểm cần nhớ: service không thuộc MVC slice **có thể được tạo mới dưới dạng mock** mà không phải lỗi thiết kế.

Nếu áp dụng `enforceOverride=true` cho service được cố ý loại khỏi slice, context có thể fail đúng cơ chế nhưng **mục tiêu test đã bị đặt sai**. Chỉ dùng strict khi bean được kỳ vọng tồn tại trong context đó.

### 5.2. @SpringBootTest: strict nếu cần xác minh sự tồn tại bean production

Với full-context integration test, thiếu bean production có thể là lỗi đáng phát hiện. Có thể dùng kiểu cấu trúc:

```java
@SpringBootTest
class ReceiptWiringTest {

    @MockitoBean(enforceOverride = true)
    ReceiptGateway receiptGateway;

    @Autowired
    OrderNotifier notifier;

    @Test
    void usesMockOfExistingGateway() {
        when(receiptGateway.send("ORD-7"))
                .thenReturn("mock:ORD-7");
        assertEquals("mock:ORD-7",
                notifier.sendReceipt("ORD-7"));
    }
}
```

Đây là **đoạn minh họa**, không phải class copy-run độc lập: cần import đúng, application config thật đăng ký `OrderNotifier`/`ReceiptGateway`, và các type phù hợp. Nếu test chạy profile khác production hoặc có test-specific `@Bean` thay thế, nó chỉ chứng minh context của profile ấy. **Enforce override không thể chứng minh điều mà context không nạp.**

Khi dùng Spring Boot 4, đừng giả định `@SpringBootTest` tự tạo MockMvc; với yêu cầu MVC cần cấu hình test MVC riêng (ví dụ `@AutoConfigureMockMvc` khi thích hợp). Điều này không thay đổi ý nghĩa `@MockitoBean`: cơ chế override phụ thuộc vào TestContext và tập bean đã nạp.

### 5.3. Test focused: không cần context cho logic thuần

Nếu mục tiêu chỉ là kiểm tra `OrderNotifier.sendReceipt(...)` gọi đúng collaborator với một input, có thể sử dụng JUnit + Mockito:

```java
ReceiptGateway gateway = Mockito.mock(ReceiptGateway.class);
OrderNotifier notifier = new OrderNotifier(gateway);

when(gateway.send("ORD-7")).thenReturn("ok");
assertEquals("ok", notifier.sendReceipt("ORD-7"));
verify(gateway).send("ORD-7");
```

Đây là snippet trong method test, cần Mockito/JUnit imports. Không có context nên không có khái niệm “bean có tồn tại hay không”; đó là vấn đề **khác** cần được kiểm tra tại Spring TestContext boundary.

## 6. Chọn bean nào để override: type, name và qualifier

Cơ chế bean overriding không có toàn bộ heuristic như autowiring thông thường. Nó thường xác định bean theo type và qualifier; nếu có nhiều candidates, tên field cũng có thể được dùng làm fallback qualifier. Vì vậy, dùng type không rõ ràng có thể thay sai bean hoặc thất bại do ambiguity.

Ví dụ config có hai bean:

```java
@Bean("emailReceiptGateway")
ReceiptGateway emailGateway() { ... }

@Bean("smsReceiptGateway")
ReceiptGateway smsGateway() { ... }
```

Đây là đoạn minh họa phương thức cấu hình, không có implementation đầy đủ. Nếu muốn bắt buộc thay bean email, có thể chọn **theo tên**:

```java
@MockitoBean(
        name = "emailReceiptGateway",
        enforceOverride = true)
ReceiptGateway emailReceiptGateway;
```

Hoặc chọn bằng qualifier:

```java
@MockitoBean(enforceOverride = true)
@Qualifier("emailReceiptGateway")
ReceiptGateway gateway;
```

Hai cách là **lựa chọn thay thế**, không nhất thiết dùng đồng thời. Cần xác minh tên thật từ code/cấu hình ứng dụng, không đoán. Test không nên vô tình tạo thêm bean cùng interface rồi làm thay đổi việc inject `@Primary`, qualifier hoặc lựa chọn theo type.

**Những trường hợp dễ nhầm:**

- Field tên `gateway` có type đúng nhưng context có nhiều bean `ReceiptGateway`. Không mặc định Spring biết bean nào cần thay.
- Field tên trùng bean name trong một test rồi bị đổi khi refactor; việc fallback theo tên có thể đổi candidate và ảnh hưởng cache key của Spring TestContext.
- Bean được tạo theo profile/condition nên chỉ có ở một môi trường. Strict mode chỉ đảm bảo tồn tại **trong context mà test thực sự nạp**.
- Bean đã được đăng ký dạng đối tượng phụ thuộc nhưng không có bean definition tương ứng; override infrastructure có thể không nhận ra nó như candidate cần thay.

Với context nhiều tầng `@ContextHierarchy`, override có thể ảnh hưởng nhiều level. Nếu cần giới hạn vào một level, dùng thuộc tính `contextName` khớp với tên `@ContextConfiguration(name = "...")`, theo hướng dẫn phiên bản Spring Framework đang dùng.

## 7. @MockitoSpyBean là WRAP, không phải strict replacement

Đôi khi muốn chạy phần lớn hành vi bean thật và chỉ quan sát hoặc stub một method, khi ấy có thể dùng `@MockitoSpyBean`. Nhưng nó **khác** `@MockitoBean(enforceOverride=true)`:

| Khía cạnh | Strict mock | Spy |
| --- | --- | --- |
| Cơ chế | `REPLACE` | `WRAP` |
| Có yêu cầu bean gốc? | Có | Có, thường đúng một candidate |
| Method chưa stub | Mockito mock trả default/cấu hình answer | Thường gọi method thật |
| Rủi ro I/O thật | Thấp nếu chỉ mock target | Cao hơn nếu method thật chạy |
| Có thể quan sát behavior thật? | Không, target gốc bị thay | Có, nhưng cần đánh giá AOP/spy |
| Mục tiêu | Thay hẳn dependency, thiếu bean là lỗi | Quan sát/điều khiển một phần bean có thật |

Với spy, `Mockito.when(spy.method())` có thể gọi **method thật ngay lúc stubbing**. Nếu method thao tác DB/network, hãy dùng kiểu `doReturn(value).when(spy).method(...)` khi phù hợp để tránh side effect. Không dùng spy như một cách “đảm bảo bean có thật” nếu bạn không muốn bất cứ hành vi thật nào chạy.

**Quan trọng với proxy:** `@MockitoBean` theo `REPLACE`/`REPLACE_OR_CREATE` thay bean trực tiếp thành mock và có thể **không giữ Spring AOP advice** đã có quanh bean gốc, như `@Transactional`, `@Cacheable` hoặc method security. `@MockitoSpyBean` có cơ chế `WRAP` khác và có thể giữ lớp AOP proxy xung quanh spy. Đừng dùng mock service rồi tuyên bố đã kiểm thử transaction/cache/security của chính service đó.

## 8. Vì sao mock có thể làm một integration test xanh giả?

Ví dụ cấu hình production bị thay đổi làm bean adapter biến mất:

```text
Một @Configuration / @ComponentScan bị thay đổi
       |
       v
ReceiptGateway không được đăng ký trong app context
       |
       v
Test có @MockitoBean (default)
       |
       v
Spring TestContext tạo mock gateway mới
       |
       v
OrderNotifier khởi tạo thành công, test PASS
       |
       v
Kết luận sai: "production bean wiring chuẩn"
```

Để tránh:

1. **Phân loại mục tiêu test trước:** behavior, MVC slice, adapter contract hay wiring thật.
2. **Chọn context đúng:** test slice chủ động thiếu bean là hợp lý; full-context muốn bảo vệ wiring phải nạp đúng configuration/profile.
3. **Bật strict ở đúng boundary:** dùng `enforceOverride=true` trên bean phải tồn tại, không áp dụng cứng cho mọi mock.
4. **Không tự đăng ký bean test chỉ để strict pass:** điều đó chỉ chứng minh fixture, không chứng minh production.
5. **Giữ target thật khi test AOP:** nếu kiểm chứng transaction/security/cache, mock các dependency phía sau target thay vì target đang được advice.

Strict không có nghĩa “luôn tốt hơn”. Nó là một **contract assertion về cấu trúc context**. Dùng sai chỗ tạo test đỏ vô ích, giống việc dùng chế độ linh hoạt sai chỗ tạo test xanh giả.

## 9. Các kiểu lỗi thực tế và cách đọc triệu chứng

### Thiếu bean trong context

Triệu chứng thường là context startup thất bại với nguyên nhân liên quan việc không có candidate phù hợp để override hoặc dependency không được giải quyết. Với `@MockitoBean(enforceOverride=true)`, kiểm tra xem bean definition có nằm trong config/profile test không. Nếu nó đúng ra phải tồn tại, **sửa registration** chứ không gỡ strict để làm xanh.

### Nhiều bean cùng interface

Nếu context có nhiều implementations, matching có thể không đủ rõ. Dùng `name` hoặc `@Qualifier` rõ ràng và kiểm tra component thực sự inject bean nào. Đừng thêm `@Primary` ngẫu nhiên vào test để che ambiguity mà không hiểu khác biệt runtime.

### @Mock không có tác dụng với Spring context

Mockito có thể tạo mock field nhưng Spring vẫn inject adapter khác hoặc báo thiếu bean. Khi cần mock là Spring bean, dùng `@MockitoBean`; khi chỉ dùng Java unit test, gọi constructor trực tiếp.

### Mock service có @Transactional làm transaction test không còn ý nghĩa

Thay target bằng mock có thể bỏ qua AOP proxy. `verify(mock).method()` không chứng minh transaction đã commit, cache được áp dụng hoặc phân quyền được kiểm tra. Chọn Spring integration test với **service thật**.

### Spy làm tác vụ thật chạy ngoài ý muốn

Dùng spy với `when(...)` có thể thực thi method thật trong lúc stubbing; dùng `doReturn(...)`/`doThrow(...)` khi đúng tình huống và không spy vào adapter I/O nếu không kiểm soát được side effect.

### Test mất thời gian khởi tạo context

Mỗi tập bean override, qualifier và cách đặt tên có thể ảnh hưởng Spring TestContext cache. Đặt tên field nhất quán, cấu hình các test cùng mục tiêu theo một pattern để tránh context bị tách không cần thiết. Không dùng `@DirtiesContext` làm giải pháp mặc định cho vấn đề dữ liệu chưa cleanup.

### Mocks reset nhưng dữ liệu DB/cache vẫn còn

Test framework có cơ chế reset mock, nhưng không tự xóa database, Redis, message queue hay static/singleton state. Quản lý fixture/transaction/cleanup phù hợp; đừng xem việc thay bean bằng mock là một cơ chế cô lập toàn ứng dụng.

## 10. Nâng cấp @MockBean cũ sang @MockitoBean

Trong các dự án Spring Boot cũ, có thể gặp:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
```

Từ Spring Boot **3.4**, `@MockBean`/`@SpyBean` của Boot bị deprecated để chuyển sang các annotation Spring Framework. Trong Spring Boot **4.0**, hỗ trợ annotation cũ đã bị loại bỏ. Mã mới dùng:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

**Không chỉ đổi tên import mà không kiểm tra semantics:**

- `@MockitoBean` mặc định replace-or-create; nếu trước đây test “tình cờ” hoạt động do tạo mock khi thiếu bean, xác định đó là mục tiêu hay lỗi che khuất.
- Nếu muốn fail khi bean không tồn tại, dùng `enforceOverride=true`.
- Cách đặt annotation trong `@Configuration` cũ không hoàn toàn tương ứng với việc đặt `@MockitoBean` của Spring Framework. Đọc tài liệu vị trí hỗ trợ; thường khai báo field hoặc annotation trên test class/type hierarchy được framework hỗ trợ, không chuyển nguyên các annotations cũ trong `@TestConfiguration`.
- Với Spring Framework 6.2, việc override các bean scope đặc biệt có giới hạn: ưu tiên singleton bean để tránh giả định thay prototype/request scope như bình thường. Kiểm tra tài liệu đúng phiên bản cho trường hợp phức tạp.
- Context hierarchy và bean-name matching có thể làm test migrate khác trước; chỉ định `contextName`/qualifier khi thật sự cần.

**Ví dụ migration đúng chủ đích:** test controller thật, service ngoài web slice được tạo mock => dùng `@MockitoBean` mặc định. Test full context bắt buộc có adapter production => dùng `@MockitoBean(enforceOverride=true)` và bảo đảm test không đăng ký một adapter giả để làm strict pass.

## 11. Khi nào dùng @Primary hoặc @TestBean thay thế?

Một cách khác là tạo `@TestConfiguration` chứa fake:

```java
@TestConfiguration
class FakeGatewayConfig {

    @Bean
    @Primary
    ReceiptGateway fakeGateway() {
        return id -> "fake:" + id;
    }
}
```

Đây là đoạn cấu hình minh họa, cần Spring Boot TestConfiguration, Spring Bean/Primary imports và interface phù hợp. `@Primary` ưu tiên bean fake khi autowire theo type, **không nhất thiết thay đúng bean production**. Bean gốc vẫn có thể được tạo và gây side effect. Vì thế nó không tương đương `@MockitoBean(name="...", enforceOverride=true)` khi yêu cầu là thay chính xác một bean đã có.

`@TestBean` của Spring TestContext có thể thay bean bằng một test implementation được cung cấp qua factory method thay vì Mockito. Đây là lựa chọn khi fake cần behavior/state thật để test, không chỉ một tập stub. Chọn kỹ strategy và version tương ứng; **không trộn các công cụ chỉ vì tên nghe giống nhau**.

**Quy tắc:** nếu chỉ cần một dependency giả để unit test, tránh Spring context. Nếu cần mock tham gia bean injection, dùng Spring TestContext override. Nếu cần giữ một fake giàu hành vi, dùng test bean/config phù hợp và xác định rõ có còn bean thật trong context hay không.

## 12. Các lỗi phổ biến

**1. Coi mock được tự tạo là bằng chứng bean gốc tồn tại.** Với `REPLACE_OR_CREATE`, đây là kết luận sai. Sử dụng strict khi muốn bảo vệ sự tồn tại.

**2. Bật strict trong một slice cố tình không tải collaborator.** Lỗi context là kết quả đúng của một yêu cầu test đặt sai; dùng default create nếu slice cần bổ sung dependency.

**3. Gắn `@Mock` rồi mong Spring inject mock.** Mockito field không tự được đăng ký thành bean. Dùng đúng annotation cho boundary.

**4. Không chỉ định bean khi có nhiều candidates.** Type, qualifier, field fallback và bean name cần phù hợp với cấu hình thật.

**5. Gắn strict nhưng lại tự tạo mock/bean đích trong test configuration.** Test chỉ chứng minh fixture được dựng đúng, không chứng minh production wiring.

**6. Bật global bean definition overriding.** Điều đó có thể che lỗi duplicate beans và không thay thế cơ chế `@MockitoBean`.

**7. Mock chính bean cần kiểm tra proxy.** Mất transaction/cache/security advice của target có thể khiến test xanh nhưng mất hiệu lực kiểm thử framework behavior.

**8. Dùng spy trên adapter I/O không kiểm soát.** Spy có thể chạy method thật; tránh side effect lúc stub bằng cách phù hợp.

**9. Nhầm lỗi tạo context với lỗi assertion.** `enforceOverride=true` và bean vắng mặt khiến fail **trước khi test method chạy**; xem root cause về bean override, không sửa assertion không được chạy.

**10. Đổi tên field khiến candidate thay đổi.** Khi có nhiều bean, dùng tên/qualifier nhất quán; field name có thể là fallback qualifier và ảnh hưởng context cache.

**11. Dùng `@MockBean` cũ trong Boot 4.** Annotation Boot cũ không còn; chuyển sang Spring TestContext API mới.

**12. Không dọn trạng thái ngoài Mockito.** Reset mock không xóa DB/cache; bảo vệ isolation bằng setup/cleanup phù hợp.

**13. Dùng strict cho bean ở profile khác.** Strict chỉ áp dụng cho **context hiện tại**, không thể kiểm tra một profile chưa tải.

**14. Giữ một test xanh bằng cách mock mọi thứ.** Khi mock cả target/service cần chứng minh, test chỉ kiểm chứng stub. Giữ SUT thật và giới hạn test doubles ở collaborator.

## 13. Checklist trước khi chốt QA

- Tôi cần **thêm mock để làm đầy một slice** hay **thay bean production đã có**?
- Nếu bean không tồn tại, test cần pass hay fail? Kỳ vọng này có được phản ánh bằng `enforceOverride`?
- Spring TestContext nạp đúng configuration/profile cần xác minh chưa?
- Có nhiều bean cùng type phải dùng `name`/`@Qualifier` không?
- Test thực sự gọi SUT thật hay chỉ kiểm tra hành vi đã stub của mock?
- Chỉ cần unit test bằng constructor injection hay thực sự cần Spring context?
- Test đang chứng minh business behavior, bean wiring, proxy advice hay HTTP/DB integration?
- Nếu đổi bean name/config, test strict có fail đúng chỗ thay vì tự thêm mock không?
- Mock có làm mất AOP/transaction/cache/security của target đang được kiểm tra không?
- Có cần reset cache/DB và cô lập dữ liệu qua các test methods/context không?
- API thuộc đúng Spring Framework version và đúng package import chưa?
- Kết luận sau khi test xanh có đúng phạm vi bằng chứng không?

**Kết luận:** `@MockitoBean` mặc định sử dụng **`REPLACE_OR_CREATE`** nên có thể bổ sung mock khi chưa có bean; `@MockitoBean(enforceOverride = true)` sử dụng **`REPLACE`** nên đòi một bean đã tồn tại. Chọn chế độ theo câu hỏi cần bảo vệ, không theo cách nào làm test xanh nhanh hơn. Một context xanh nhờ mock được tạo mới **không phải bằng chứng cấu hình production đúng**.

## 14. Tài liệu tham khảo

- [Spring Framework 6.2 — @MockitoBean và @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
