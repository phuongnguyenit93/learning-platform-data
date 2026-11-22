# Spring Boot cũ: `@MockBean`, `@SpyBean` và phạm vi thay thế bean khi kiểm thử

## 1. Vì sao cần thay một bean trong Spring test?

Trong ứng dụng Spring Boot, service thường nhận dependency qua constructor. Ví dụ `CheckoutService` dùng `PaymentGateway`, `DiscountPolicy` và một repository. Nếu chạy test với toàn bộ bean thật, một lời gọi có thể đụng database, gửi email hoặc gọi payment API. Ngược lại, nếu tạo mọi đối tượng giả, test sẽ không kiểm chứng wiring và logic Spring mà mình muốn giữ.

Hai annotation của **Spring Boot đời cũ** giải quyết nhu cầu thay thế có kiểm soát:

- **`@MockBean`**: đưa một **Mockito mock** vào `ApplicationContext` của test; có thể thay bean sẵn có hoặc bổ sung một mock bean khi chưa có candidate phù hợp.
- **`@SpyBean`**: tạo **Mockito spy** để bao bọc bean của context, giữ hành vi thật khi không stub nhưng cho phép quan sát, thay riêng các lời gọi.

Điểm dễ nhầm là `@MockBean` **khác** `@Mock`. `@Mock` của Mockito chỉ tạo object giả trong test; nó không tự đưa object đó vào Spring context. Còn `@MockBean` tạo/đăng ký mock ở cấp bean để các service được Spring inject có thể sử dụng cùng mock ấy.

Bài học tập trung vào Spring Boot **1.4–3.3** và quá trình chuyển tiếp **3.4–3.5**. Từ Spring Boot **3.4.0**, `@MockBean` và `@SpyBean` bị đánh dấu deprecated để hướng tới `@MockitoBean` và `@MockitoSpyBean` của Spring Framework 6.2. **Spring Boot 4.x** loại bỏ annotation legacy. Mã runnable trong bài dùng **Java 17 + Spring Boot 3.3.0** để API, imports và phụ thuộc có cùng một nền tảng.

Mục tiêu sau bài:

1. Chọn được mock toàn phần và spy một phần theo hợp đồng kiểm thử.
2. Hiểu quy tắc thay bean theo type/name/qualifier, trường hợp thiếu bean và nhiều bean.
3. Dùng `@MockBean` trong `@WebMvcTest`, `@SpringBootTest` đúng phạm vi.
4. Biết stub spy an toàn, xử lý Spring AOP proxy và không tạo side effect vô ý.
5. Hiểu Mockito reset, cache của Spring TestContext và state dùng chung.
6. Viết test thực sự chứng minh hành vi, không mock mất chính thành phần đang cần test.
7. Phân biệt các khác biệt không tương thích khi nâng từ Boot cũ sang Spring Framework bean overrides.

## 2. Ba cấp độ mock thường bị lẫn

Xét service:

```java
@Service
class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    String checkout(String orderId, long amount) {
        return gateway.charge(orderId, amount);
    }
}
```

Đây là **ví dụ cấu trúc**, cần khai báo `PaymentGateway` và Spring imports để chạy. Có ba cách setup:

| Cách | Object giả ở đâu? | Khi nào hợp lý? |
| --- | --- | --- |
| `PaymentGateway gateway = mock(PaymentGateway.class)` | Local variable, không phải Spring bean | Unit test tạo service bằng `new CheckoutService(gateway)` |
| `@Mock PaymentGateway gateway` | Field của test được Mockito/extension khởi tạo | Mockito unit test, hoặc test có setup thủ công |
| `@MockBean PaymentGateway gateway` | Bean trong **Spring test ApplicationContext**, đồng thời được inject vào field | Test mà service/controller thật do Spring quản lý phải nhận gateway giả |

Ví dụ lỗi ý tưởng:

```java
@SpringBootTest
class BrokenTest {
    @Autowired
    CheckoutService service;

    @Mock
    PaymentGateway gateway;

    @Test
    void test() {
        when(gateway.charge("ORD-42", 100L))
                .thenReturn("TX-42");
        // service có thể đang giữ gateway THẬT từ ApplicationContext.
    }
}
```

Đây là **đoạn phản ví dụ**, không phải test hoàn chỉnh. Nếu field `@Mock` được khởi tạo bởi Mockito, nó vẫn **không tự thay bean** đang nằm trong `service`.

Sửa bằng `@MockBean` trên gateway nếu mục tiêu là chạy Spring context, hoặc bỏ `@SpringBootTest` và khởi tạo service bằng constructor với mock nếu chỉ cần unit test.

```text
JUnit + @Mock:
 test field ------> mock A
 Spring context --> CheckoutService --> gateway B

Spring Boot + @MockBean:
 test field -------+
                   |
 Spring context --> mock A
      |
      +--> CheckoutService --> mock A
```

## 3. Bản chất và phạm vi của `@MockBean`

### 3.1. Đăng ký một Mockito mock làm Spring bean

Spring Boot 3.3 cung cấp `org.springframework.boot.test.mock.mockito.MockBean`. Trên **field**:

```java
@MockBean
PaymentGateway gateway;
```

Framework suy ra bean type từ field, đăng ký một Mockito mock và inject mock đó trở lại field. Nếu có **một bean phù hợp** với type này, Boot thay bean ấy trong context test. Nếu chưa có bean phù hợp, Boot có thể thêm mock bean mới. Đây là điểm thuận tiện trong slice tests nhưng cũng có thể che lỗi cấu hình nếu ta tưởng đã thay một bean hiện hữu.

Trên **class**, phải cung cấp type rõ:

```java
@SpringBootTest
@MockBean(PaymentGateway.class)
class PaymentIntegrationTest {
    @Autowired
    PaymentGateway gateway;
}
```

Không phải mã test độc lập vì còn cần `@Test` và ứng dụng. `@MockBean` legacy hỗ trợ lặp trên class:

```java
@MockBean(PaymentGateway.class)
@MockBean(EmailGateway.class)
@SpringBootTest
class CheckoutIntegrationTest {
    // PaymentGateway và EmailGateway đều thành mocks.
}
```

Khai báo `EmailGateway` ở đây là minh họa. Đừng mock cả service đang được kiểm thử nếu cần chạy nghiệp vụ thật.

### 3.2. Phân biệt thay bean theo type và bean name

Giả sử context có hai implementation `PaymentGateway`: `bankGateway` và `sandboxGateway`. Mock theo type có thể không xác định được candidate hoặc không trúng bean mà service thực sự inject. Khi ấy chỉ rõ tên:

```java
@MockBean(name = "bankGateway")
PaymentGateway gateway;
```

Hoặc sử dụng qualifier trên field:

```java
@MockBean
@Qualifier("bankGateway")
PaymentGateway gateway;
```

Hai cách này là **phương án thay thế**, không phải bắt buộc dùng cùng lúc. Tên bean phải được kiểm chứng từ cấu hình thực, chẳng hạn `@Component("bankGateway")` hoặc tên phương thức `@Bean`. Nếu service inject `@Qualifier("sandboxGateway")` thì thay `bankGateway` có thể **không cô lập** lời gọi mà bài test dự định.

### 3.3. Những thuộc tính ở API cũ

| Thuộc tính `@MockBean` | Chức năng |
| --- | --- |
| `value` / `classes` | Type cần mock, thường dùng ở class level |
| `name` | Tên bean cụ thể muốn thay hoặc đăng ký |
| `answer` | Mockito default answer |
| `extraInterfaces` | Các interface phụ mà mock thực hiện |
| `serializable` | Yêu cầu mock có thể serialization |
| `reset` | Chọn `MockReset.BEFORE`, `AFTER`, `NONE` |

Đây là thuộc tính **legacy Boot**. Khi chuyển sang `@MockitoBean` của Framework, không giả định từng thuộc tính có bản sao cùng tên hoặc cùng hành vi.

### 3.4. Mock mặc định không chạy code thật

Với một mock không được stub, phương thức trả một giá trị mặc định theo Mockito: thường `null` cho reference, `0` cho số primitive và `false` cho boolean, tùy trả về và default answer. Nếu một service cần transaction ID nhưng gateway mock chưa được stub, một `null` có thể dẫn tới lỗi phía sau. Đây là hành vi của mock, không phải bằng chứng service production thật trả null.

Hãy stub đúng dữ liệu phục vụ test, đồng thời **verify đối số quan trọng**. Nếu tổng đơn hàng 100.000 được giảm còn 90.000, verification `charge("ORD-42", 90_000L)` hữu ích hơn `charge(anyString(), anyLong())`.

## 4. Bản chất và phạm vi của `@SpyBean`

### 4.1. Spy bọc đối tượng thực

`@SpyBean` dùng Mockito spy thay vì mock thuần. Khi chưa stub, method được gọi có thể chạy logic thật:

```java
@SpyBean
DiscountPolicy discountPolicy;
```

Trong một test Spring Boot, nếu Spring có bean `DiscountPolicy`, lời gọi `discountPolicy.payable(100_000L)` thực thi thuật toán thật, ví dụ trả 90.000. Điều này khác hẳn `@MockBean DiscountPolicy` vốn mặc định trả `0L` nếu chưa stub.

```text
@MockBean:
  test/service --> Mockito mock --> stubs / default answer

@SpyBean:
  test/service --> Mockito spy --> method được stub?
                                   | Có -> trả stub
                                   | Không -> gọi method thật
```

### 4.2. Khi nào nên spy?

Spy phù hợp khi:

- Muốn **giữ nghiệp vụ thật** của service hoặc policy nhưng quan sát một lời gọi có giá trị.
- Cần thay đúng một nhánh của một class có phần lớn logic hữu ích.
- Cần xác minh cách các bean thật phối hợp, đồng thời kiểm soát một điểm khó tái hiện.

Spy không phù hợp nếu method thật chạm **database production**, thanh toán, email, network hoặc gây side effect chưa được kiểm soát. Trong tình huống ấy, mock outbound gateway hoặc dựng môi trường integration test riêng sẽ rõ hơn.

### 4.3. Stub spy an toàn

Với Mockito spy:

```java
doReturn(77_000L)
        .when(discountPolicy)
        .payable(100_000L);
```

`doReturn(...).when(spy).method(...)` tránh gọi phương thức thật **ngay trong bước stubbing**. Mẫu khác:

```java
when(discountPolicy.payable(100_000L))
        .thenReturn(77_000L);
```

có thể gọi method thật trước khi đăng ký stub. Với một hàm thuần không side effect, cách thứ hai có thể không gây hậu quả, nhưng với method tương tác DB/network hoặc thay đổi mutable state thì rất nguy hiểm.

**Quy tắc:** nếu dùng spy, ưu tiên `doReturn`/`doThrow`/`doAnswer` cho method có nguy cơ side effect. Đừng làm test xanh bằng cách ngầm thực thi logic production trong bước Arrange.

### 4.4. Legacy `@SpyBean` có thể xử lý thiếu bean khác Framework mới

JavaDoc Spring Boot 3.3 mô tả khả năng gắn spy theo type/name và có cơ chế **bổ sung một bean khi chưa có bean phù hợp**. Đừng dựa vào khả năng đó để thay cho việc xác minh cấu hình production có bean thật hay không.

Ngược lại, Spring Framework 6.2+ `@MockitoSpyBean` dùng chiến lược **WRAP**, đòi hỏi **đúng một singleton bean đã tồn tại** để wrap. Khi nâng cấp, một test cũ đã vô tình nhờ legacy annotation tạo bean có thể bắt đầu fail ở bước context bootstrap; đây là điểm cần sửa configuration, không đơn giản thay tên annotation.

## 5. Ví dụ chạy được: Spring Boot 3.3.0 + Java 17

Bộ ví dụ sau là một dự án Spring Boot nhỏ **không dùng web hoặc database**. Nó kiểm tra Spring wiring, giữ `CheckoutService` và `DiscountPolicy` chạy thật, thay `PaymentGateway` bằng mock. Phần spy giữ policy thật hoặc stub riêng một quyết định.

### 5.1. Cấu trúc dự án

```text
legacy-bean-test/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/
    │   ├── ShopApplication.java
    │   ├── PaymentGateway.java
    │   ├── DemoPaymentGateway.java
    │   ├── DiscountPolicy.java
    │   └── CheckoutService.java
    └── test/java/example/
        ├── CheckoutMockBeanTest.java
        └── CheckoutSpyBeanTest.java
```

### 5.2. Build Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'legacy-bean-test'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dự án cần Gradle Wrapper tương thích, ví dụ Gradle 8.5 với Boot 3.3 và Java 17. Phiên bản 3.3.0 được chọn cố định để ví dụ legacy không bị lẫn import của Boot 4. Khi áp dụng vào hệ thống thực, hãy dùng phiên bản Boot/Java/Gradle mà dự án hỗ trợ và bản bảo trì thích hợp.

### 5.3. Application và các bean thật

**`src/main/java/example/ShopApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

**`src/main/java/example/PaymentGateway.java`:**

```java
package example;

public interface PaymentGateway {
    String charge(String orderId, long amountInVnd);
}
```

**`src/main/java/example/DemoPaymentGateway.java`:**

```java
package example;

import org.springframework.stereotype.Component;

@Component
public class DemoPaymentGateway implements PaymentGateway {
    @Override
    public String charge(String orderId, long amountInVnd) {
        return "DEMO-" + orderId;
    }
}
```

Adapter này trả dữ liệu giả tại chỗ, không thực hiện thanh toán. Trong ứng dụng thật, `PaymentGateway` thường đại diện cho một cổng ngoài cần được cô lập trong test service.

**`src/main/java/example/DiscountPolicy.java`:**

```java
package example;

import org.springframework.stereotype.Component;

@Component
public class DiscountPolicy {
    public long payable(long subtotal) {
        if (subtotal <= 0L) {
            throw new IllegalArgumentException(
                    "subtotal must be positive");
        }
        return subtotal >= 100_000L
                ? subtotal - 10_000L
                : subtotal;
    }
}
```

Policy minh họa giảm 10.000 VND nếu subtotal từ 100.000 VND; không chấp nhận số tiền không dương.

**`src/main/java/example/CheckoutService.java`:**

```java
package example;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    public record Receipt(
            String orderId,
            long chargedAmount,
            String transactionId) {}

    private final PaymentGateway gateway;
    private final DiscountPolicy policy;

    public CheckoutService(
            PaymentGateway gateway,
            DiscountPolicy policy) {
        this.gateway = gateway;
        this.policy = policy;
    }

    public Receipt checkout(String orderId, long subtotal) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException(
                    "orderId must not be blank");
        }

        long amount = policy.payable(subtotal);
        String transactionId = gateway.charge(orderId, amount);
        return new Receipt(orderId, amount, transactionId);
    }
}
```

`@SpringBootApplication` trong package `example` giúp component scan tìm `DemoPaymentGateway`, `DiscountPolicy` và `CheckoutService`. Constructor injection đảm bảo service nhận các bean đang có trong context.

### 5.4. Test A — thay gateway bằng `@MockBean`

**`src/test/java/example/CheckoutMockBeanTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringBootTest(
        classes = ShopApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CheckoutMockBeanTest {
    @Autowired
    CheckoutService checkout;

    @Autowired
    ApplicationContext context;

    @MockBean
    PaymentGateway gateway;

    @Test
    void replacesGatewayButRunsRealServiceAndPolicy() {
        when(gateway.charge("ORD-42", 90_000L))
                .thenReturn("TX-42");

        CheckoutService.Receipt receipt =
                checkout.checkout("ORD-42", 100_000L);

        assertEquals("ORD-42", receipt.orderId());
        assertEquals(90_000L, receipt.chargedAmount());
        assertEquals("TX-42", receipt.transactionId());
        assertSame(gateway, context.getBean(PaymentGateway.class));

        verify(gateway).charge("ORD-42", 90_000L);
    }

    @Test
    void rejectsBlankOrderWithoutCallingGateway() {
        assertThrows(IllegalArgumentException.class,
                () -> checkout.checkout(" ", 100_000L));
        verifyNoInteractions(gateway);
    }
}
```

Mỗi assertion chứng minh một điều:

- `chargedAmount==90000`: `DiscountPolicy` thật đã trừ tiền đúng theo quy tắc.
- `transactionId=="TX-42"`: service sử dụng kết quả từ mock gateway đã stub.
- `assertSame(gateway, context.getBean(PaymentGateway.class))`: field mock và bean được inject trong context là cùng instance.
- `verify(..., 90000)`: gateway nhận đúng amount do service tính.
- Ở đường input sai, gateway không được gọi.

Test này không chứng minh HTTP endpoint, database commit hay giao thức thanh toán ngoài vì những thành phần ấy không được dựng trong ứng dụng minh họa.

### 5.5. Test B — spy policy thật, mock gateway ngoài

**`src/test/java/example/CheckoutSpyBeanTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest(
        classes = ShopApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class CheckoutSpyBeanTest {
    @Autowired
    CheckoutService checkout;

    @MockBean
    PaymentGateway gateway;

    @SpyBean
    DiscountPolicy policy;

    @Test
    void spyCallsRealPricingMethodByDefault() {
        when(gateway.charge("ORD-7", 90_000L))
                .thenReturn("TX-7");

        CheckoutService.Receipt result =
                checkout.checkout("ORD-7", 100_000L);

        assertEquals(90_000L, result.chargedAmount());
        assertEquals("TX-7", result.transactionId());
        verify(policy).payable(100_000L);
        verify(gateway).charge("ORD-7", 90_000L);
    }

    @Test
    void spyCanReplaceOnePricingDecision() {
        doReturn(77_000L).when(policy).payable(100_000L);
        when(gateway.charge("ORD-8", 77_000L))
                .thenReturn("TX-8");

        CheckoutService.Receipt result =
                checkout.checkout("ORD-8", 100_000L);

        assertEquals(77_000L, result.chargedAmount());
        assertEquals("TX-8", result.transactionId());
        verify(policy).payable(100_000L);
        verify(gateway).charge("ORD-8", 77_000L);
    }
}
```

Test đầu giữ logic thật của policy, test sau chỉ stub phép tính `payable(100000)` để tái hiện một quyết định đặc biệt. Cả hai vẫn dùng gateway mock, nên không có side effect thanh toán ngoài.

**Cần chú ý:** `@SpyBean` thường reset Mockito interactions/stubs theo từng test, nhưng nếu bản thân `DiscountPolicy` có mutable state, reset spy không tự làm dữ liệu ấy trở lại ban đầu. Policy trong ví dụ là stateless nên không có vấn đề đó.

### 5.6. Chạy và kết quả mong đợi

Trong thư mục dự án đã có Gradle Wrapper phù hợp:

```bash
./gradlew test
./gradlew test --tests example.CheckoutMockBeanTest
./gradlew test --tests example.CheckoutSpyBeanTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.CheckoutSpyBeanTest
```

Dự kiến **4 test methods pass**; Gradle báo `BUILD SUCCESSFUL` khi các test và build task không có lỗi. Không có stdout nghiệp vụ cố định; các dòng log Boot và số task tùy môi trường.

Ví dụ không có HTTP/database nên không cần container runtime hoặc API key. Nếu mã được sao chép vào một dự án đã tồn tại, có thể xuất hiện bean cùng tên hoặc auto-configuration ngoài ý muốn; hãy kiểm tra khác biệt với dự án tối giản này.

## 6. So sánh lựa chọn mock, spy và bean thật theo hợp đồng

| Bạn muốn chứng minh | Cấu hình phù hợp | Assertion có giá trị |
| --- | --- | --- |
| Service không gọi gateway khi input sai | Service thật + gateway mock | Exception/error và `verifyNoInteractions` |
| Service tính số tiền đúng | Service và policy thật + gateway mock | Amount return và tham số gửi gateway |
| Controller map URL và JSON đúng | `@WebMvcTest` + mock service | HTTP status, JSON field |
| Policy tính đúng ở biên | JUnit thuần hoặc bean policy thật | Bảng input/output ở ngưỡng |
| Quan sát service thật gọi policy mấy lần | Spy policy nếu số lần là contract | `verify(spy)` cùng outcome |
| Repository thực lưu được dữ liệu | Repository/DB thật | Query đọc lại persisted row |
| Outbound HTTP đúng method/header/body | HTTP mock server theo giao thức | Request wire contract |
| Security filter từ chối đúng | Security test context phù hợp | 401/403 + không có effect cấm |

**Không mock lớp đang là đối tượng cần kiểm chứng.** Test `@MockBean DiscountPolicy` rồi stub trả 90000 không kiểm chứng quy tắc giảm giá; nó chỉ chứng minh Mockito trả dữ liệu được khai báo. Một service unit test dùng `new DiscountPolicy()` có thể mạnh hơn và chạy nhanh hơn cho mục tiêu ấy.

## 7. Phạm vi `@MockBean` trong `@WebMvcTest`

Trong Spring Boot 2.x/3.3, `@WebMvcTest` nạp MVC slice: controller, MVC infrastructure và một số bean phục vụ web, thường **không nạp service thông thường**. Controller cần service bean, do đó dùng `@MockBean` là tình huống rất phổ biến.

```java
@WebMvcTest(OrderController.class)
class OrderControllerWebTest {
    @Autowired
    MockMvc mvc;

    @MockBean
    OrderService orders;

    @Test
    void serializesOrderStatus() throws Exception {
        when(orders.find("ORD-42"))
                .thenReturn(new OrderView("ORD-42", "PAID"));

        mvc.perform(get("/orders/ORD-42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
```

Đây là **khung MVC minh họa**, cần `OrderController`, `OrderService`, `OrderView` và imports ứng dụng. Nó chứng minh route/status/JSON theo phản hồi giả từ service, **không chứng minh** logic service hay persistence.

Một lỗi phổ biến là bật `@SpringBootTest` chỉ vì `@WebMvcTest` không tìm thấy service. Nếu mục tiêu chỉ là web contract, cung cấp mock service đúng slice; nếu muốn toàn luồng nhiều bean thật, chuyển sang integration test có chủ đích.

## 8. Phạm vi trong `@SpringBootTest` và những slice khác

`@SpringBootTest` nạp Boot context, phù hợp khi cần kiểm tra cấu hình bean thật hoặc tương tác nhiều lớp. Lúc ấy `@MockBean` chỉ nên thay dependency **nằm ngoài mục tiêu xác minh**, như remote client hoặc email gateway.

```text
@SpringBootTest
  controller thật (nếu có)
     |
  checkout service thật
     |                   |
  discount thật         payment gateway mock
     |
  repository thật (nếu mục tiêu có persistence)
```

Với `@DataJpaTest`, mục tiêu là entity/repository/query, nên đừng mock repository đang cần test. Có thể mock một collaborator phụ nếu slice thực sự cần nó. Tương tự, trong WebFlux, Security hay batch tests, hãy hiểu **slice quét bean gì** trước khi thêm mock.

**Scope thay thế:** `@MockBean`/`@SpyBean` tác động lên context mà test yêu cầu, không phải sửa global production bean definitions. Context test khác có thể có mock set khác và vì thế khác cache key.

## 9. Thứ tự khởi tạo context và vấn đề stub quá muộn

Ở test Boot thông thường, `ApplicationContext` được refresh **trước khi phương thức `@Test` chạy**. Nếu một bean gọi remote client trong `@PostConstruct` hoặc lúc context refresh, stub được khai báo trong `@BeforeEach` hay `@Test` sẽ được thiết lập **sau** lời gọi khởi tạo ấy.

```text
Spring test context startup
    |
    +--> tạo bean
    +--> @PostConstruct / initialization
    |       +--> gọi PaymentGateway
    |
    +--> inject @MockBean field vào test instance
    |
JUnit @BeforeEach / @Test
    +--> when(gateway.charge(...)).thenReturn("TX-42")
          ^ quá muộn cho lời gọi lúc context startup
```

Tài liệu Boot 3.3 nêu hạn chế này với `@MockBean`. Nếu bắt buộc kiểm soát hành vi **trong context refresh**, cân nhắc tạo một mock đã được stub sẵn bằng test `@Bean` trong `@TestConfiguration` phù hợp, hoặc thay đổi thiết kế để không gọi hệ thống ngoài khi khởi tạo bean. Không tự động thêm test `@MockBean` rồi kỳ vọng mọi lời gọi cũ sẽ được replay.

## 10. Reset mock/spy và context cache

### 10.1. Reset mặc định `AFTER`

Annotation legacy Boot có `reset` với các chế độ `MockReset.BEFORE`, `MockReset.AFTER`, `MockReset.NONE`. Mặc định là **`AFTER`**, nghĩa là Boot test infrastructure reset Mockito stubs/interactions sau mỗi test method.

```java
@MockBean(reset = MockReset.AFTER)
PaymentGateway gateway;
```

Đây là **ví dụ cú pháp**, cần import `org.springframework.boot.test.mock.mockito.MockReset`. Với `@SpyBean`, lựa chọn `reset` tương tự.

**Reset không phải đóng và tạo lại ApplicationContext.** Context có thể được cache/reuse, mock object vẫn nằm trong context nhưng interactions/stubs được reset. Một singleton thật chứa `Map`/counter còn state sau reset; cần dọn state bằng fixture hoặc thiết kế stateless.

### 10.2. Tác động lên context cache

Spring TestContext dùng cache theo tập cấu hình. `@MockBean`/`@SpyBean` tham gia vào context customization/cache key; hai test khác nhau về danh sách mock/spy có thể tạo **hai context**. Điều này làm suite chậm nếu mỗi test class thay hàng chục bean khác nhau.

Tối ưu có căn cứ:

- Dùng unit test thuần nếu không cần Spring.
- Chỉ mock/spy bean thật sự ở ranh giới cần kiểm soát.
- Giữ test configurations nhất quán khi có thể.
- Không lạm dụng `@DirtiesContext` để reset Mockito.
- Giữ test data và mutable singleton state độc lập với context cache.

### 10.3. Reset và thứ tự test

Không viết test B giả định test A đã chạy trước để setup hoặc dọn data. Khi cần chứng minh input không hợp lệ không gọi gateway, `verifyNoInteractions(gateway)` hợp lệ **cho chính kịch bản đó**, không cần dựa vào test khác.

## 11. Spring AOP proxy, spy và những điểm cần thận trọng

Một bean có `@Transactional`, `@Cacheable`, `@PreAuthorize` hoặc advice khác có thể được Spring bọc bằng proxy. Khi spy bean này, có thể có **proxy** và **target** khác nhau; `Mockito.verify` hoặc `when` có thể tác động lên object chưa đúng ý.

Ở Spring Boot 3.3, legacy `@SpyBean` có thuộc tính `proxyTargetAware` (mặc định `true`) để Mockito APIs như `verify` sử dụng target với các AOP-advised beans. Trong tình huống đặc biệt, tài liệu Boot đề cập `AopTestUtils.getTargetObject(...)` hoặc `getUltimateTargetObject(...)` để truy cập target.

Trước khi sửa một test spy AOP, hãy tự hỏi: hành vi cần chứng minh nằm ở **lời gọi qua proxy** hay ở **method thật**? Nếu mục tiêu là test transaction/security/cache advice, vô tình gọi trực tiếp target có thể bỏ qua advice, khiến test xanh sai ý định.

Lưu ý thêm về `@Cacheable` dùng tên tham số trong expression: Spring Boot 3.3 khuyến nghị biên dịch với `-parameters` khi spy bean có các method như vậy, để caching infrastructure đọc được tên tham số. Đừng mặc định mọi lỗi cache sau khi thêm spy là lỗi Mockito.

## 12. Các vấn đề bean name, scope và container registry

### 12.1. Bean cùng type

Nếu context có hơn một bean cùng interface, `@MockBean PaymentGateway` có thể báo ambiguous candidate hoặc thay bean khác dự kiến. Dùng bean `name` hoặc `@Qualifier` đúng với dependency mà service thật inject.

### 12.2. Đối tượng không thực sự là Spring bean

`@MockBean` chỉ thay bean trong context. Một instance tạo bằng `new` hoặc giữ trong static field bên ngoài IoC không tự được thay. Spring Boot legacy JavaDoc còn phân biệt dependency **được đăng ký trực tiếp nhưng không phải bean definition**: mock có thể được thêm bên cạnh dependency cũ thay vì thay reference ấy.

### 12.3. Scope và proxy

Bean prototype, request/session scoped hoặc FactoryBean có các chi tiết riêng; đừng mặc định mọi đối tượng đều là singleton thông thường. Khi áp dụng API mới của Framework, bean override được thiết kế cho **singleton**, và spy yêu cầu có đúng một bean tồn tại. Khi migrate từ annotation legacy, kiểm tra scope và BeanFactory/FactoryBean theo JavaDoc phiên bản.

### 12.4. Đừng cố sửa bằng bean overriding toàn cục

Một số ứng dụng cấu hình không cho phép đăng ký đè bean name. Đừng bật overriding global chỉ để test vượt qua lỗi cấu hình chưa hiểu. Dùng cơ chế bean override chuyên dụng, `@TestConfiguration` hoặc profile test có chủ đích và kiểm tra candidate thật.

## 13. Dòng phiên bản: lúc nào dùng API cũ, lúc nào cần đổi?

| Dòng phát hành | Tình trạng | Cách xử lý |
| --- | --- | --- |
| Spring Boot 1.4–2.x | Có `@MockBean` và `@SpyBean` | Dùng đúng imports/test runner/BOM của dòng ấy |
| Spring Boot 3.0–3.3 | API legacy vẫn là cách phổ biến | Có thể dùng các ví dụ Boot 3.3 trong bài |
| Spring Boot 3.4–3.5 | API legacy còn nhưng **deprecated for removal** từ 3.4 | Bắt đầu migrate sang Spring Framework 6.2+ annotations |
| Spring Boot 4.x | API legacy `org.springframework.boot.test.mock.mockito` đã bị loại bỏ | Dùng `@MockitoBean` và `@MockitoSpyBean` của Framework |

Imports:

```java
// Spring Boot 3.3 và các dòng cũ:
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;

// Spring Framework 6.2+ (Boot 3.4+), Framework 7.x (Boot 4.x):
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

Đây là **hai lựa chọn theo version**, không đưa cả hai bộ annotation vào cùng test để thay cùng bean nếu không hiểu chiến lược override.

**Không dùng Spring Framework 6.2 annotations trong dự án Boot 3.3 đang quản lý Spring Framework 6.1.x** bằng cách tự ép artifact riêng lẻ. Ưu tiên nâng cả Boot BOM theo tổ hợp tương thích rồi sửa imports.

## 14. Khác biệt quan trọng khi đổi sang `@MockitoBean` và `@MockitoSpyBean`

| Nội dung | Boot legacy | Framework 6.2+ |
| --- | --- | --- |
| Mock bean annotation | `@MockBean` | `@MockitoBean` |
| Spy bean annotation | `@SpyBean` | `@MockitoSpyBean` |
| Khai báo class-level type | `@MockBean(PaymentGateway.class)` | `@MockitoBean(types = PaymentGateway.class)` |
| Mock bean không tồn tại | Có thể thêm mock mới | Mặc định `REPLACE_OR_CREATE`, có thể dùng `enforceOverride = true` để yêu cầu bean cũ tồn tại |
| Spy bean không tồn tại | Legacy có đường tạo thêm tùy điều kiện | `WRAP` yêu cầu chính xác một singleton bean tồn tại |
| Lựa chọn bean | Type/name/qualifier theo cơ chế legacy | Type/name/field qualifier, fallback theo field name; cần hiểu cache key |
| Context hierarchy | Cơ chế legacy riêng | Có `contextName` để nhắm một level |
| Reset enum | `org.springframework.boot.test.mock.mockito.MockReset` | `org.springframework.test.context.bean.override.mockito.MockReset` |
| Các attributes khác | `answer`, `extraInterfaces`, `serializable`, `proxyTargetAware`... | Không tự giả định tương ứng một-một |

Một nâng cấp tưởng đơn giản:

```java
// Cũ:
@MockBean
PaymentGateway gateway;

@SpyBean
DiscountPolicy policy;

// Mới (Framework 6.2+, khi bean và scope hợp lệ):
@MockitoBean
PaymentGateway gateway;

@MockitoSpyBean
DiscountPolicy policy;
```

Đây là đoạn minh họa **không phải một test class độc lập**. Nếu old `@SpyBean` đã tự thêm policy khi ứng dụng thực tế không có policy bean, new `@MockitoSpyBean` sẽ fail: cần tạo bean thật hoặc đổi mục tiêu thành mock.

Nếu điều quan trọng là **phải thay một bean đã tồn tại**, `@MockitoBean(enforceOverride = true)` giúp bắt lỗi khi type/name không có bean tương ứng. Điều đó còn giúp tránh tình trạng test cũ xanh nhờ tự thêm mock, dù wiring production bị lỗi.

Spring Framework mới cũng có những khác biệt AOP proxy cho chiến lược `REPLACE`/`WRAP`; cần kiểm tra transaction, caching, method security qua đúng proxy ranh giới. Không coi migration hoàn tất chỉ vì code compile.

## 15. Quy trình migrate test Boot cũ

1. **Chốt version:** Boot, Framework, JDK, Maven/Gradle, `spring-boot-starter-test` và cách quản lý dependency.
2. **Thống kê từng mục đích:** web slice mocks, outbound gateway mocks, bean spy, mock class-level, bean name/qualifier, custom reset, AOP proxy.
3. **Nâng BOM tương thích:** Boot 3.4+ hỗ trợ Framework 6.2; Boot 4 dùng API Framework mới và có các test starters theo chức năng.
4. **Đổi imports/annotations:** `@MockBean` → `@MockitoBean`, `@SpyBean` → `@MockitoSpyBean`, class-level `classes` → `types` theo API mới.
5. **Xác minh bean tồn tại:** với spy phải có một singleton bean; với mock mà test đòi bean thật tồn tại, dùng `enforceOverride=true`.
6. **Rà soát attributes:** `reset`, `name`, qualifiers, attributes legacy không còn tương đương.
7. **Chạy test từng tầng:** compile tests, JUnit unit, MVC/JPA slices, `@SpringBootTest` và integration có database/HTTP.
8. **Kiểm tra behavior:** HTTP/body/state/event thực tế, không chỉ Mockito verify.
9. **Xem chi phí context:** số context khác nhau có tăng do qualifiers/bean overrides không.
10. **Chốt migration bằng số test và kết quả:** test discovery không giảm, test quan trọng vẫn bảo vệ được contract.

**Cảnh báo riêng Boot 4:** không chỉ đổi annotation mà còn phải xem lại starter/module test theo công nghệ, package `@WebMvcTest`/`@DataJpaTest` và các API khác. Không thêm artifact Boot 3.x vào BOM Boot 4 chỉ để một import cũ tồn tại.

## 16. Bảng chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân cần xét | Cách kiểm tra/sửa |
| --- | --- | --- |
| Mock field nhận stub nhưng service gọi thật | Dùng `@Mock` thay `@MockBean` hoặc service tạo ngoài context | Xác minh cùng Spring bean/instance |
| Mockito `Wanted but not invoked` | Service dùng bean khác hoặc rẽ nhánh khác | Kiểm tra injection và request/arguments |
| `NoUniqueBeanDefinitionException` | Nhiều bean type, thiếu qualifier/name | Chọn đúng bean theo `@Qualifier`/`name` |
| MVC slice fail thiếu service | Slice không tự load service thường | `@MockBean` hoặc test configuration có chủ đích |
| Stub không khớp, mock trả null | Argument mismatch hoặc quên stub | Assert input, dùng matcher nhất quán |
| `InvalidUseOfMatchersException` | Trộn literal với `any`/`eq` trong cùng invocation | Nếu dùng một matcher, mọi arg của invocation cần matcher |
| Spy gọi method thật khi stub | `when(spy.method())` thực thi method khi Arrange | Dùng `doReturn`/`doThrow` |
| Spy có effect ngoài ý muốn | Method chưa stub chạy thật | Mock outbound hoặc isolation hạ tầng |
| Context fail khi init bean | Stub test cấu hình quá muộn cho startup callback | Preconfigure mock bean trước refresh hoặc thiết kế init lại |
| Test chạy riêng xanh, chạy suite đỏ | State singleton/DB chưa reset, khác context config | Cleanup fixture và điều tra cache |
| Chạy chậm, nạp nhiều context | Mỗi class có bộ mock/spy khác nhau | Giảm override và thống nhất cấu hình |
| Spy với `@Transactional` verify sai | AOP proxy vs target | Xem `proxyTargetAware`/`AopTestUtils` |
| Boot 3.4 warning deprecated | API cũ chuẩn bị bị loại bỏ | Lập kế hoạch migrate |
| Boot 4 không có `MockBean` | API Boot legacy đã bị remove | Chuyển sang Framework annotations |
| `@MockitoSpyBean` báo không có bean | Framework `WRAP` cần singleton có sẵn | Cấu hình bean thật hoặc chọn mock |
| Test xanh dù nghiệp vụ sai | Mock mất chính service/repository cần test | Đổi ranh giới và assert output/state thật |

Đọc **lỗi gốc đầu tiên** khi context load fail. Một lỗi Mockito argument matcher khác bản chất với lỗi không có Spring bean; không nên xử lý cả hai bằng cách tăng phạm vi `@SpringBootTest`.

## 17. Bài tập thực hành

### Bài 1 — Tìm vì sao `@Mock` không thay bean

Cho một test có `@Autowired CheckoutService` và field `@Mock PaymentGateway`. Hãy:

- Giải thích vì sao service vẫn có thể giữ bean gateway thật.
- Chuyển sang legacy `@MockBean` ở Boot 3.3.
- Stub gateway trả `TX-42` khi amount bằng 90.000.
- Assert receipt đúng và verify gateway nhận đúng số tiền.

**Tiêu chí:** không chỉ thấy test xanh; chứng minh mock bean trong context và service đang dùng cùng object.

### Bài 2 — Spy chỉ một quyết định

Chạy `CheckoutSpyBeanTest`. Trong test có `doReturn(77_000L)`, thử thay bằng `when(policy.payable(100_000L)).thenReturn(...)` trong sandbox. Policy thuần hiện tại có thể vẫn pass. Hãy mô tả tại sao cách đó gây nguy cơ nếu policy có side effect. Khôi phục `doReturn`.

### Bài 3 — Cần mock hay giữ service thật?

Với endpoint HTTP trả order status, so sánh:

- `@WebMvcTest` + mock service: bằng chứng web mapping/serialization.
- `@SpringBootTest` + gateway mock + service/repository thật: bằng chứng luồng nghiệp vụ nội bộ.
- Integration test với DB/container và HTTP mock server: bằng chứng transaction/persistence và giao thức.

Viết một assertion trọng yếu cho mỗi mức. Nếu chưa cần database, đừng nạp DB chỉ để đạt mức integration.

### Bài 4 — Nhiều implementation cùng interface

Thêm `bankGateway` và `sandboxGateway` vào test sandbox; chỉ định qualifier ở service. Dùng `@MockBean(name = "bankGateway")` và xác minh service nhận đúng bean. Nếu service dùng sandbox thì mock bank có ích không? Đáp án phụ thuộc mục tiêu, nhưng không thể giả định hai bean thay thế cho nhau.

### Bài 5 — Chú ý cache và reset

Tạo một singleton `Counter` có state và wrap bằng spy. Chạy hai test methods. Mockito reset làm sạch interaction, nhưng `Counter.value` có tự về 0 không? Hãy dùng fixture reset hoặc thiết kế lại state để test độc lập. Không mặc định cần `@DirtiesContext`.

### Bài 6 — Migrate sang Framework 6.2+

Lấy một class Boot 3.3 có:

```java
@MockBean
PaymentGateway gateway;

@SpyBean
DiscountPolicy discountPolicy;
```

Nâng theo BOM tương thích, đổi sang `@MockitoBean`/`@MockitoSpyBean`, rồi xác minh policy bean tồn tại và singleton. Nếu test cũ đã dựa vào việc `@SpyBean` thêm policy mới, migration cần sửa thiết kế thay vì chỉ imports.

## 18. Checklist trước khi hoàn thành bài

- [ ] Tôi biết phiên bản Boot đang dùng có hỗ trợ `@MockBean`/`@SpyBean` hay không.
- [ ] Tôi phân biệt Mockito `@Mock`/`@Spy` với Spring Boot bean replacement.
- [ ] Tôi biết **bean thật nào** được thay, theo type, name hoặc qualifier.
- [ ] Tôi không mock lớp chính đang cần kiểm tra logic.
- [ ] Nếu dùng spy, tôi biết method chưa stub sẽ gọi code thật.
- [ ] Tôi dùng `doReturn`/`doThrow` khi cần ngăn method thật chạy ở bước Arrange.
- [ ] Tôi đã cô lập database/network/email/payment side effects.
- [ ] Tôi biết reset Mockito state không reset state trong singleton thật.
- [ ] Tôi hiểu mock/spy ảnh hưởng context cache key và hiệu năng suite.
- [ ] Nếu bean dùng AOP, tôi biết proxy/target và điểm kiểm chứng đúng.
- [ ] Với startup callbacks, tôi không giả định stub trong `@Test` tác động ngược lên context refresh.
- [ ] Với Boot 3.4–3.5, tôi nhận biết deprecation và kế hoạch migrate.
- [ ] Với Boot 4, tôi dùng Framework override annotations và module test phù hợp.
- [ ] Khi migrate spy, tôi đã kiểm tra chính xác một singleton bean tồn tại.
- [ ] Test có assertion đúng về giá trị trả, state hoặc effect nghiệp vụ.

## 19. Sơ đồ quyết định

```text
Chỉ muốn kiểm tra logic Java?
    -> JUnit + mock()/@Mock, tạo service qua constructor.

Cần Spring tạo/inject các bean?
    |
    +-- Dependency ngoài cần giả hoàn toàn?
    |       -> Legacy @MockBean (Boot <= 3.3).
    |
    +-- Cần giữ logic thật và can thiệp một phần?
    |       -> Legacy @SpyBean; kiểm soát side effect/proxy.
    |
    +-- Chỉ test MVC mapping?
    |       -> @WebMvcTest + mock service ngoài slice.
    |
    +-- Test nhiều bean nội bộ?
            -> @SpringBootTest + mock outbound có chủ đích.

Boot >= 3.4: lên kế hoạch chuyển Framework @MockitoBean/@MockitoSpyBean.
Boot 4: API Boot cũ đã bị loại bỏ, dùng annotation mới.
```

Hai điều phải nhớ: **mock đúng ranh giới** và **đừng để spy chạy tác động thật ngoài ý muốn**. `@MockBean`/`@SpyBean` giúp kiểm soát bean của test context; chúng không tự xác minh business behavior, không làm transaction/database/network trở nên an toàn và không thay thế assertion quan sát được.

## 20. Tài liệu chính thức theo phiên bản

- Spring Boot 3.3 `@MockBean` JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/MockBean.html
- Spring Boot 3.3 `@SpyBean` JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/mock/mockito/SpyBean.html
- Spring Boot 3.3 Testing Applications, “Mocking and Spying Beans”: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.4 deprecated Mockito integration: https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/package-summary.html
- Spring Framework 6.2 `@MockitoBean` và `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework Bean Overrides: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html
- Spring Boot Testing (dòng hiện hành): https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Mockito: https://site.mockito.org/
- JUnit: https://docs.junit.org/current/user-guide/
