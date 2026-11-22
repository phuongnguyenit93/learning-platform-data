# Phân biệt mock đối tượng Java với thay thế bean trong Spring context

## 1. Mục tiêu

Khi viết test cho Spring Boot, hai đoạn code sau nhìn giống nhau nhưng kiểm soát **hai object graph khác nhau**:

```java
@Mock
ShippingGateway shippingGateway;
```

```java
@MockitoBean
ShippingGateway shippingGateway;
```

`@Mock` tạo một Mockito object thuộc phạm vi test Java, còn `@MockitoBean` yêu cầu Spring TestContext **đăng ký hoặc thay thế một bean trong ApplicationContext của test**. Nếu service do Spring tạo đã được inject gateway thật, mock Java tạo thêm trong test không làm service tự đổi tham chiếu sang mock mới.

Bài này giải thích chính xác:
- Vì sao `Mockito.mock`/`@Mock` đủ cho unit test thuần Java nhưng chưa đủ để tác động tới dependency injection của Spring.
- `@InjectMocks` khác `@Autowired`; trường hợp nào dùng constructor injection tường minh.
- Cơ chế `@MockitoBean` và `@MockitoSpyBean`, chọn bean theo type/name/qualifier, trạng thái bean khi không có target.
- Lựa chọn trong `@WebMvcTest`, `@SpringBootTest` và khi cần kiểm thử database/AOP/security.
- Những hiểu lầm về phiên bản cũ `@MockBean`/`@SpyBean`, Spring context caching, reset mocks và mock không nhận lời gọi.
- Ví dụ Maven + Java 17 + JUnit Jupiter chạy được, từ unit test tới web slice và full context.

Ví dụ sử dụng Spring Boot **3.5.16**, tương ứng Spring Framework 6.2.x với `@MockitoBean` thuộc Spring TestContext. Với Boot 3.3 trở xuống, hãy xem mục tương thích phiên bản trước khi copy import.

## 2. Căn bản: Mock object và Spring bean không phải cùng một việc

### 2.1. Mockito tạo object giả

`Mockito.mock(ShippingGateway.class)` trả về một Java object. Mặc định các method chưa stub sẽ trả về giá trị mặc định (ví dụ `0` cho `int`; semantics chi tiết phụ thuộc kiểu trả về và Mockito). Bạn quyết định đầu ra và ghi nhận tương tác:

```java
ShippingGateway gateway = Mockito.mock(ShippingGateway.class);
Mockito.when(gateway.feeFor("HCM")).thenReturn(20);

int result = gateway.feeFor("HCM"); // 20
Mockito.verify(gateway).feeFor("HCM");
```

Đoạn trên là minh họa bên trong một Java method, với `ShippingGateway` là interface của dự án ở mục 6. Nó không dùng `ApplicationContext`, `@ComponentScan`, `@Autowired` hay bean factory.

Mockito không biết:
- `ShippingGateway` nào đã được inject vào `CheckoutService` của Spring.
- Có mấy bean cùng interface hoặc bean nào có `@Primary`/`@Qualifier`.
- Spring profile, auto-configuration, transaction, retry, cache và method security.
- Những bean nào có dependency graph đã hình thành trước khi mock được tạo.

Mockito chỉ thấy **object mà test giữ và lời gọi thật sự đi đến object đó**.

### 2.2. Spring tạo và nối các bean

Giả sử application có graph:

```text
Spring ApplicationContext
  |
  +-- CheckoutController bean
  |       |
  |       +-- CheckoutService bean
  |               |
  |               +-- FlatShippingGateway bean
  |
  +-- MVC, Jackson và các bean hạ tầng khác
```

Khi Spring khởi tạo `CheckoutService`, constructor nhận bean `ShippingGateway` được chọn từ container. Nếu sau đó test khai báo:

```java
@Mock
ShippingGateway shippingGateway;

@Autowired
CheckoutService checkoutService;
```

thì mặc định test chỉ có **một field mock riêng**, còn `checkoutService` vẫn dùng bean đã được Spring inject. Thậm chí nếu thiếu `MockitoExtension`/`openMocks`, field có `@Mock` có thể là `null`.

Để Spring thay dependency trong graph được khởi tạo cho test, dùng:

```java
@SpringBootTest
class ServiceContextTest {
    @MockitoBean
    ShippingGateway shippingGateway;

    @Autowired
    CheckoutService checkoutService;
}
```

Trong context test, bean `ShippingGateway` phù hợp sẽ là Mockito mock; `CheckoutService` thật được Spring inject mock đó. Có thể `when`/`verify` như Mockito thông thường vì bản chất bean thay thế vẫn là một Mockito mock.

### 2.3. So sánh nhanh

| Điểm phân biệt | `@Mock` / `Mockito.mock` | `@MockitoBean` |
| --- | --- | --- |
| Bên tạo | Mockito (test/extension) | Spring TestContext kết hợp Mockito |
| Có cần Spring context? | Không | Có |
| Vị trí object | Field/biến do test nắm giữ | Bean trong test `ApplicationContext` và field tương ứng |
| Tác động đến Spring DI? | Không tự động | Có, khi resolve đúng bean |
| Thay bean hiện hữu? | Không | Có |
| Nếu không có bean phù hợp? | Vẫn tạo mock object | Mặc định tạo mock bean mới theo `REPLACE_OR_CREATE` |
| Tốn chi phí load context? | Không | Có; có thể dùng context cache |
| Kiểm Spring wiring? | Không | Có thể kiểm service/bean thật nhận mock đúng; không kiểm logic của bean đã bị mock |
| Trường hợp phù hợp | Unit test cho domain/service | Test slice/web/full context cần thay collaborator |

Điểm quyết định là **ai nắm tham chiếu tới dependency của đối tượng đang kiểm thử**. Đối tượng do test tự tạo → test tự inject. Đối tượng do Spring tạo → Spring phải đăng ký/thay bean trong context nếu muốn thay dependency.

## 3. Unit test thuần Mockito: `@Mock`, `@InjectMocks` và khởi tạo

### 3.1. JUnit 5 phải khởi tạo field Mockito

```java
@ExtendWith(MockitoExtension.class)
class CheckoutServiceUnitTest {
    @Mock
    ShippingGateway shippingGateway;

    @Test
    void testMethod() {
        when(shippingGateway.feeFor("HCM")).thenReturn(20);
    }
}
```

`@ExtendWith(MockitoExtension.class)` xử lý annotation Mockito trong JUnit Jupiter và quản lý trạng thái/strict stubbing của test. Với test chỉ có một mock, cách tạo tường minh cũng hợp lệ:

```java
ShippingGateway shippingGateway = mock(ShippingGateway.class);
```

Không cần context hoặc `@SpringBootTest`. Đừng thêm Spring chỉ để Mockito hoạt động.

### 3.2. `@InjectMocks` là tiện ích, không phải Spring DI

```java
@ExtendWith(MockitoExtension.class)
class ServiceUnitTest {
    @Mock ShippingGateway shippingGateway;
    @InjectMocks CheckoutService checkoutService;
}
```

Mockito tìm cách inject các mock/spy trong test vào instance `CheckoutService` (constructor, setter hoặc field injection theo cơ chế Mockito). Nó **không**:
- Khởi động Spring `ApplicationContext`.
- Tìm bean theo `@Qualifier`/`@Primary`.
- Đọc `@Value` từ Spring Environment.
- Áp dụng Spring bean lifecycle/AOP advice.
- Tự xây toàn bộ graph cho các service phụ thuộc phức tạp.

Mockito documentation cũng nêu rằng injection có thể không hoàn tất như bạn mong đợi mà không báo lỗi ngay; hãy kiểm bằng test hành vi. Với một constructor duy nhất, viết `new CheckoutService(shippingGateway)` thường tường minh hơn:

```java
ShippingGateway mockGateway = mock(ShippingGateway.class);
CheckoutService sut = new CheckoutService(mockGateway);
when(mockGateway.feeFor("HCM")).thenReturn(20);
assertEquals(120, sut.total(100, "HCM"));
```

Đây là đoạn minh họa trong method, cần JUnit/Mockito imports. SUT = system under test, tức **đối tượng có logic thật bạn muốn kiểm**, còn mock là collaborator bên ngoài.

### 3.3. Unit test chứng minh được gì?

Một unit test service có thể chứng minh:
- Kiểm tra input sai trước khi gọi outbound dependency.
- Công thức tính toán và nhánh nghiệp vụ.
- Có/không gọi collaborator hoặc truyền đúng tham số.
- Xử lý exception từ collaborator nếu được stub.

Nó không chứng minh việc `@Transactional` hoạt động, controller trả JSON đúng, JPA chạy SQL đúng hoặc message được broker phát thật. Với những rủi ro đó, cần test đúng Spring/hạ tầng boundary.

## 4. `@MockitoBean`: thay thế bean trong Spring TestContext

### 4.1. Đúng package và thời điểm sử dụng

Import cho Spring Framework 6.2+:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Annotation này là một phần của Spring TestContext bean overriding. Nó được xử lý khi test chạy với Spring extension/context, chẳng hạn `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest` hoặc `@SpringJUnitConfig` phù hợp.

```java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerWebTest {
    @Autowired MockMvc mvc;
    @MockitoBean CheckoutService checkoutService;
}
```

```java
@SpringBootTest
class CheckoutServiceContextTest {
    @Autowired CheckoutService checkoutService;
    @MockitoBean ShippingGateway shippingGateway;
}
```

Trường hợp thứ nhất: controller thật, MVC thật, service mock. Trường hợp thứ hai: service thật, gateway mock. Cả hai đều dùng Mockito nhưng **đối tượng thật đang được kiểm** khác nhau.

### 4.2. Chọn đúng bean theo type, name và qualifier

Khi annotation đặt trên field, Spring suy ra type từ kiểu field. Nếu nhiều bean cùng kiểu, cần disambiguation:

```java
// Ví dụ minh họa khi context có nhiều PriceClient:
@MockitoBean
@Qualifier("remotePriceClient")
PriceClient priceClient;
```

Hoặc:

```java
@MockitoBean(name = "remotePriceClient")
PriceClient priceClient;
```

`PriceClient` là interface minh họa ngoài project mẫu. Spring cũng có thể dùng **tên field làm fallback qualifier** nếu không có qualifier tường minh. Vì thế cùng một bean bị mock ở nhiều test nhưng tên field khác nhau có thể ảnh hưởng cache key; đặt tên nhất quán khi các test thật sự có cấu hình giống nhau.

Có thể dùng trên type của test:

```java
@MockitoBean(types = {ShippingGateway.class})
@SpringBootTest
class AlternativeOverrideTest {
    // ...
}
```

Đây là minh họa cú pháp, không phải class bắt buộc trong bài chạy. Khi chỉ định tên bean ở cấp type, danh sách `types` tương ứng phải rõ và chỉ bao gồm một loại bean cho tên ấy.

### 4.3. Bean chưa tồn tại: REPLACE_OR_CREATE và enforceOverride

Mặc định Spring Framework dùng chiến lược `REPLACE_OR_CREATE` cho `@MockitoBean`. Nếu tìm thấy bean target, nó bị thay bằng mock. Nếu không tìm thấy, Spring có thể tạo một mock bean mới.

Điều này hữu ích trong `@WebMvcTest`: service thường **không nằm trong MVC slice**, nhưng controller phải inject một service, nên mock được thêm vào context. Mặt trái: full-context test có thể vô tình pass dù bean production đã biến mất khỏi component scan.

Muốn phát hiện trường hợp đó:

```java
@MockitoBean(enforceOverride = true)
ShippingGateway shippingGateway;
```

`enforceOverride=true` buộc phải có bean để thay, tức strategy `REPLACE`. Hợp lý cho `@SpringBootTest` khi bạn muốn chắc chắn production bean đã có; không nên máy móc dùng trong slice cố tình không load service gốc.

### 4.4. Scope, factory và proxy

Spring TestContext bean override hỗ trợ singleton bean. Thay bean non-singleton có thể thất bại; `@MockitoSpyBean` còn đòi đúng một bean hiện hữu để wrap.

Nếu target là product của `FactoryBean`, behavior override áp dụng cho object product theo quy tắc Spring Framework; đừng nhầm factory với object được cấp cho collaborator.

Spring có thể đặt AOP proxy quanh bean thật để xử lý transaction, cache, retry hoặc method security. `@MockitoBean` đăng ký **mock thay thế trực tiếp**, vì vậy behavior advice của bean gốc **không còn trên mock ấy**. Test gọi mock service không chứng minh transaction/cache/security của service thật.

Mocking bean **A** không tự động xóa AOP của bean **B** đang được giữ thật; cần phân tích chính bean nào được thay.

### 4.5. Reset giữa các test

`@MockitoBean` do Spring TestContext quản lý; mặc định reset mock sau mỗi test method theo `MockReset.AFTER`. Context có thể được cache và tái sử dụng, nhưng Mockito stubbing/interactions vẫn có cơ chế reset.

Không suy ra điều đó cũng reset database, static state, file system hoặc external service. Nếu có dữ liệu chung, thiết kế fixture/transaction/cleanup riêng. Việc tự `Mockito.reset(mock)` quá thường xuyên thường là dấu hiệu scope của test chưa rõ.

## 5. `@MockitoSpyBean`: theo dõi bean có hành vi thật

Một spy về cơ bản quan sát **một đối tượng thật** và có thể stub/verify chọn lọc, khác mock mặc định không chạy logic thật.

| Công cụ | Điều được tạo/bao bọc | Spring DI |
| --- | --- | --- |
| `spy(realObject)` hoặc `@Spy` | Mockito spy của object trong code test | Không tự đăng ký vào container |
| `@MockitoSpyBean` | Spring bean hiện hữu được wrap bằng spy | Có; cần bean target |
| `@MockitoBean` | Mockito mock thay bean Spring | Có; method thật của bean bị thay không chạy |

```java
@SpringBootTest
class CheckoutSpyBeanTest {
    @MockitoSpyBean
    CheckoutService checkoutService;

    @Test
    void observesRealMethod() {
        int result = checkoutService.total(100, "HCM");
        assertEquals(200, result);
        verify(checkoutService).total(100, "HCM");
    }
}
```

Đoạn này sẽ chạy được trong project ở mục 6. Vì không stub service và gateway vẫn thật, total là **200**.

Khi stub spy, lưu ý:

```java
// Có thể gọi method thật ngay khi tạo stubbing:
when(spy.someMethod()).thenReturn(value);

// Thường tránh gọi method thật tại thời điểm stub:
doReturn(value).when(spy).someMethod();
```

Hai dòng chỉ minh họa pattern; `spy`/`value` do test cụ thể định nghĩa. `@MockitoSpyBean` dùng chiến lược `WRAP` và tương tác với Spring AOP proxy khác `@MockitoBean`. Trong hệ thống có proxy, spy target và object được inject có thể không cùng một tham chiếu trực tiếp; khi stub/verify method qua proxy cần theo hướng dẫn Spring Framework. Không dùng spy cho method có side effect không kiểm soát (gửi email, thanh toán, gọi mạng).

## 6. Project thực hành có thể chạy bằng Maven

Cùng một use case báo giá vận chuyển sẽ được kiểm ở năm phạm vi. Kết quả khác biệt giữa mock Java và mock bean Spring là **quan sát được**, không phải lý thuyết.

### 6.1. Cây project

```text
mock-boundary-lab/
├── pom.xml
├── src/main/java/com/example/mockboundary/
│   ├── MockBoundaryApplication.java
│   ├── ShippingGateway.java
│   ├── FlatShippingGateway.java
│   ├── CheckoutService.java
│   └── CheckoutController.java
└── src/test/java/com/example/mockboundary/
    ├── CheckoutServiceUnitTest.java
    ├── CheckoutControllerWebTest.java
    ├── CheckoutServiceContextTest.java
    ├── DetachedMockSpringTest.java
    └── CheckoutSpyBeanTest.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>mock-boundary-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

`spring-boot-starter-test` kéo theo Mockito, JUnit Jupiter, Spring Test/AssertJ theo dependency management của Spring Boot. Không cần khai báo version cho từng thư viện trong project này.

### 6.3. Mã ứng dụng

`src/main/java/com/example/mockboundary/MockBoundaryApplication.java`:

```java
package com.example.mockboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MockBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(MockBoundaryApplication.class, args);
    }
}
```

`src/main/java/com/example/mockboundary/ShippingGateway.java`:

```java
package com.example.mockboundary;

public interface ShippingGateway {
    int feeFor(String zone);
}
```

`src/main/java/com/example/mockboundary/FlatShippingGateway.java`:

```java
package com.example.mockboundary;

import org.springframework.stereotype.Component;

@Component
public class FlatShippingGateway implements ShippingGateway {
    @Override
    public int feeFor(String zone) {
        return 100;
    }
}
```

`src/main/java/com/example/mockboundary/CheckoutService.java`:

```java
package com.example.mockboundary;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final ShippingGateway shippingGateway;

    public CheckoutService(ShippingGateway shippingGateway) {
        this.shippingGateway = shippingGateway;
    }

    public int total(int subtotal, String zone) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("Subtotal must be >= 0");
        }
        return subtotal + shippingGateway.feeFor(zone);
    }
}
```

`src/main/java/com/example/mockboundary/CheckoutController.java`:

```java
package com.example.mockboundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/checkout")
public class CheckoutController {
    private final CheckoutService checkoutService;

    public CheckoutController(CheckoutService checkoutService) {
        this.checkoutService = checkoutService;
    }

    @GetMapping("/quote")
    public Quote quote(@RequestParam int subtotal,
                       @RequestParam String zone) {
        return new Quote(checkoutService.total(subtotal, zone));
    }

    public record Quote(int total) {}
}
```

Không có mock trong code ứng dụng. Với subtotal = 100, `FlatShippingGateway` thật trả phí 100, kết quả business là `total=200`.

### 6.4. Test #1: Mock Java, không Spring context

`src/test/java/com/example/mockboundary/CheckoutServiceUnitTest.java`:

```java
package com.example.mockboundary;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceUnitTest {
    @Mock
    ShippingGateway shippingGateway;

    @InjectMocks
    CheckoutService checkoutService;

    @Test
    void mockFeeIsUsedByJavaObject() {
        when(shippingGateway.feeFor("HCM")).thenReturn(20);

        assertEquals(120, checkoutService.total(100, "HCM"));
        verify(shippingGateway).feeFor("HCM");
    }

    @Test
    void invalidSubtotalSkipsGateway() {
        assertThrows(IllegalArgumentException.class,
                () -> checkoutService.total(-1, "HCM"));
        verifyNoInteractions(shippingGateway);
    }
}
```

Mockito tạo service object và inject mock gateway. Spring không khởi động. Test kiểm business logic, không kiểm Spring bean wiring.

### 6.5. Test #2: Controller thật + mock service trong web slice

`src/test/java/com/example/mockboundary/CheckoutControllerWebTest.java`:

```java
package com.example.mockboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CheckoutController.class)
class CheckoutControllerWebTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    CheckoutService checkoutService;

    @Test
    void webSliceUsesMockService() throws Exception {
        when(checkoutService.total(100, "HCM")).thenReturn(120);

        mvc.perform(get("/checkout/quote")
                        .param("subtotal", "100")
                        .param("zone", "HCM"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").value(120));

        verify(checkoutService).total(100, "HCM");
    }
}
```

`@WebMvcTest` tạo MVC infrastructure và controller nhưng không tự load toàn bộ `@Service` như full context. `@MockitoBean` tạo mock bean `CheckoutService` để controller constructor có dependency. `MockMvc` kiểm HTTP routing, request parameter, JSON và delegation mà không chạy web server thật. Vì service bị mock, test **không** xác nhận công thức tính của service.

### 6.6. Test #3: Full context giữ service thật, thay gateway

`src/test/java/com/example/mockboundary/CheckoutServiceContextTest.java`:

```java
package com.example.mockboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest
class CheckoutServiceContextTest {
    @Autowired
    ApplicationContext context;

    @Autowired
    CheckoutService checkoutService;

    @MockitoBean(enforceOverride = true)
    ShippingGateway shippingGateway;

    @Test
    void contextInjectsMockIntoRealService() {
        when(shippingGateway.feeFor("HCM")).thenReturn(20);

        assertEquals(120, checkoutService.total(100, "HCM"));
        assertSame(shippingGateway,
                context.getBean(ShippingGateway.class));
        verify(shippingGateway).feeFor("HCM");
    }
}
```

Ở đây service **do Spring tạo** và nhận gateway mock **do Spring bean override cung cấp**. `enforceOverride=true` đòi bean gateway thật phải tồn tại trước khi thay. `assertSame` phù hợp trong project này vì gateway không có AOP proxy; không suy rộng identity assertion cho mọi bean có proxy.

### 6.7. Test #4: Mock Java tách rời không tác động đến bean đã inject

`src/test/java/com/example/mockboundary/DetachedMockSpringTest.java`:

```java
package com.example.mockboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

@SpringBootTest
class DetachedMockSpringTest {
    @Autowired
    CheckoutService checkoutService;

    @Test
    void detachedJavaMockDoesNotChangeSpringWiring() {
        ShippingGateway detached = mock(ShippingGateway.class);

        int result = checkoutService.total(100, "HCM");

        assertEquals(200, result); // gateway thật vẫn trả 100
        verifyNoInteractions(detached);
    }
}
```

Chủ đích của test là chứng minh một mock Java tồn tại nhưng **không nằm trên đường gọi của service**. Kết quả là 200, trong khi các test stub gateway/mock service ở trên có thể trả 120. Test không stub object tách rời để tránh `UnnecessaryStubbingException` của strict Mockito; nếu cố stub detached, đó chính là dấu hiệu mock được tạo nhưng SUT không dùng.

### 6.8. Test #5: Spy Spring bean và chạy method thật

`src/test/java/com/example/mockboundary/CheckoutSpyBeanTest.java`:

```java
package com.example.mockboundary;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;

@SpringBootTest
class CheckoutSpyBeanTest {
    @MockitoSpyBean
    CheckoutService checkoutService;

    @Test
    void spyRunsRealService() {
        int result = checkoutService.total(100, "HCM");

        assertEquals(200, result);
        verify(checkoutService).total(100, "HCM");
    }
}
```

`@MockitoSpyBean` wrap bean thật. Vì không stub, method thật gọi `FlatShippingGateway` thật và trả 200. Spy phù hợp khi cần quan sát lời gọi mà giữ business behavior.

### 6.9. Chạy project và quan sát

Cần JDK 17+ và Maven. Trong thư mục chứa `pom.xml`:

```bash
mvn -q -Dtest=CheckoutServiceUnitTest test
mvn -q -Dtest=CheckoutControllerWebTest test
mvn -q -Dtest=CheckoutServiceContextTest test
mvn -q -Dtest=DetachedMockSpringTest test
mvn -q -Dtest=CheckoutSpyBeanTest test
mvn -q test
```

Cả năm lớp test được thiết kế để qua assertion; Maven trả exit code `0` khi mọi kiểm thử thành công. Không khẳng định một stdout cụ thể vì log Spring/Maven và thời gian chạy thay đổi theo môi trường. `-Dtest=...` chọn một lớp; `mvn -q test` chạy toàn bộ lớp có tên kết thúc `Test`.

| Test | Bean/SUT thật | Object bị mock/spy | Kết quả kiểm |
| --- | --- | --- | --- |
| Unit | `CheckoutService` Java object | `@Mock ShippingGateway` | Total = 120 |
| Web slice | `CheckoutController` Spring bean | `@MockitoBean CheckoutService` | JSON total = 120 |
| Full context | `CheckoutService` Spring bean | `@MockitoBean ShippingGateway` | Total = 120 |
| Detached mock | `CheckoutService` Spring bean | Mock Java riêng, không inject | Total = 200 |
| Spy bean | `CheckoutService` Spring bean qua spy | `@MockitoSpyBean CheckoutService` | Total = 200 |

Có thể chạy app thật:

```bash
mvn spring-boot:run
```

Gọi endpoint ở terminal khác:

```bash
curl "http://localhost:8080/checkout/quote?subtotal=100&zone=HCM"
```

Khi code mẫu chạy không có cấu hình ngoài can thiệp, body JSON:

```json
{"total":200}
```

Khi application chạy bình thường không dùng mock test, Spring inject `FlatShippingGateway` thật, vì thế phép thử 120 ở các test không phải kết quả production.

## 7. So sánh `@MockitoBean` với `@MockBean` và `@MockitoSpyBean` với `@SpyBean`

Cần tránh nhầm hai package:

| API | Package | Tình trạng |
| --- | --- | --- |
| `@Mock` / `@Spy` | `org.mockito` | Mockito thuần Java; vẫn đúng cho unit tests |
| `@MockBean` / `@SpyBean` | `org.springframework.boot.test.mock.mockito` | Cũ, Spring Boot 3.4 đánh dấu deprecated để loại bỏ ở Boot 4.0 |
| `@MockitoBean` / `@MockitoSpyBean` | `org.springframework.test.context.bean.override.mockito` | Spring Framework 6.2+; hướng mới cho test có context |

Ví dụ chuyển đổi:

```java
// Cũ trong Spring Boot 3.x (deprecated từ 3.4):
import org.springframework.boot.test.mock.mockito.MockBean;

// Mới khi Spring Framework >= 6.2:
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Sau khi sửa import, cần thay annotation ở test. Nhưng **không** thay mọi `@Mock` thành `@MockitoBean`: unit test vẫn nên dùng Mockito thuần. Nếu nâng dự án Spring Boot 3.3 trở xuống lên API mới, kiểm tra BOM/Framework vì ở phiên bản cũ annotation Spring TestContext tương ứng chưa sẵn có.

Một số chi tiết matching/bean override/reset có thể khác giữa legacy và API mới. Khi migrate, nên chạy bộ test đầy đủ và kiểm những lớp có `@Qualifier`, bean name, context hierarchy, FactoryBean, proxy hoặc nhiều implementation.

## 8. Các lỗi thường gặp

### 8.1. Đặt `@Mock` trong test Spring rồi tưởng đã thay bean

```java
@SpringBootTest
class WrongTest {
    @Mock ShippingGateway gateway;
    @Autowired CheckoutService checkoutService;
}
```

Ngay cả khi mock được MockitoExtension khởi tạo, service Spring có thể vẫn gọi `FlatShippingGateway`. Giải pháp: dùng `@MockitoBean` cho dependency trong context, hoặc không dùng Spring và tự tạo service bằng constructor mock.

### 8.2. Vừa `@InjectMocks` vừa `@Autowired` cùng đối tượng

```java
@SpringBootTest
@ExtendWith(MockitoExtension.class)
class ConfusingTest {
    @Autowired @InjectMocks CheckoutService checkoutService;
    @Mock ShippingGateway gateway;
}
```

Hai framework cùng tham gia khởi tạo/inject một field, ý nghĩa test trở nên khó kiểm soát. Chọn một đường:
- Thuần Java: MockitoExtension, `@Mock`, constructor/`@InjectMocks`, không tạo Spring context.
- Spring: `@Autowired` service thật, `@MockitoBean` collaborator, không thêm `@InjectMocks`.

### 8.3. Mock chính thứ muốn kiểm

```java
@SpringBootTest
class TrivialTest {
    @MockitoBean CheckoutService checkoutService;

    @Test
    void onlyChecksStubbing() {
        when(checkoutService.total(100, "HCM")).thenReturn(120);
        assertEquals(120, checkoutService.total(100, "HCM"));
    }
}
```

Test chủ yếu khẳng định stub do chính test đặt, **không kiểm công thức service thật**. Mock service là hợp lý khi SUT là controller trong web slice. Nếu SUT là service, giữ service thật và mock gateway.

### 8.4. Quên Spring context với `@MockitoBean`

`MockitoExtension` không xử lý `@MockitoBean`. Nếu test không dùng Spring TestContext, annotation bean override không thể thay bean nào. Với unit test không Spring, dùng `@Mock`; với Spring test, dùng `@SpringBootTest`/`@WebMvcTest` và import Spring TestContext đúng.

### 8.5. Mock bean không tồn tại nhưng vẫn pass

Mặc định `@MockitoBean` có thể tạo mock bean nếu target chưa tồn tại. Trong full context khi target bắt buộc phải có, chọn `enforceOverride=true` để phát hiện lỗi component scan/profile/config.

### 8.6. Ambiguous bean: type không đủ xác định

Khi hai bean cùng implement interface, `@MockitoBean ShippingGateway gateway` có thể mơ hồ hoặc chọn nhầm candidate nếu fallback name trùng không đúng ý. Dùng `@Qualifier` hoặc `@MockitoBean(name = "...")`. Đặt tên field nhất quán trong các test muốn chia sẻ Spring context cache.

### 8.7. Mock repository rồi tuyên bố đã kiểm database

`verify(repository).save(...)` chỉ cho biết mock nhận lời gọi. Nó không chứng minh SQL, JPA mapping, constraint, transaction hay migration. Dùng `@DataJpaTest` và database test phù hợp cho persistence; với full flow, giữ repository/DB thật ở integration test.

### 8.8. Mock bean có `@Transactional`/`@Cacheable` rồi kiểm proxy behavior

`@MockitoBean` thay bean thành mock trực tiếp, nên AOP advice của bean bị thay không được kiểm như behavior thật. Khi cần xác nhận transaction/cache/security, giữ bean đó thật, mock outbound dependency ở ngoài boundary và thiết kế integration test phù hợp.

### 8.9. Spy vô tình chạy side effect

`when(spy.call()).thenReturn(result)` có thể thực thi method thật ngay lúc stubbing. Với method có side effect, dùng `doReturn(result).when(spy).call()` hoặc thiết kế mock ở outbound port để tránh gửi email, ghi DB hoặc gọi mạng thật không mong muốn.

### 8.10. Giả định context cache và reset là một

Spring có thể tái sử dụng `ApplicationContext` giữa các test có cấu hình tương thích. `@MockitoBean` có cơ chế reset state của Mockito, nhưng **không reset mọi trạng thái khác** trong context/external systems. Test vẫn cần fixture độc lập, transactional cleanup hoặc cách cô lập phù hợp.

## 9. Tác động đến test slice, integration và hiệu năng

| Mục tiêu | Cách kiểm phù hợp | Ranh giới mock |
| --- | --- | --- |
| Quy tắc tính giá/validation trong service | Mockito unit không Spring | Mock gateway/repository port |
| HTTP mapping, JSON, validation, exception handler | `@WebMvcTest` + `MockMvc` | `@MockitoBean` service collaborator |
| Wiring service và bean trong full context | `@SpringBootTest` | `@MockitoBean` outbound gateway |
| Mapping/query JPA | `@DataJpaTest` với database | Không mock repository đang kiểm |
| Cache, transaction, security advice | Spring context/integration test | Giữ bean mang advice thật |
| REST → service → repository → DB | Integration có database phù hợp | Chỉ mock hệ ngoài không thuộc phạm vi |
| Quan sát bean thật có chọn lọc | `@MockitoSpyBean` | Spy đúng bean; tránh side effect |

**Chi phí:** Unit mock Java không load Spring, thường phản hồi nhanh. `@WebMvcTest` load một slice, `@SpringBootTest` load full context. Thêm mock bean khác nhau làm cấu hình/cache key khác nhau; đổi tên field fallback qualifier hay lạm dụng `@DirtiesContext` có thể khiến Spring khởi động nhiều context.

Không ép tất cả test về `@SpringBootTest` chỉ vì dễ autowire. Mục tiêu là chọn **ranh giới nhỏ nhất đủ chứng minh lỗi cần phát hiện**, đồng thời giữ đúng bean thật ở những vị trí có hành vi đang được kiểm.

## 10. Chẩn đoán theo triệu chứng

| Triệu chứng | Khả năng cao | Kiểm tra |
| --- | --- | --- |
| `when(...)` có khai báo nhưng kết quả vẫn từ bean thật | Mock Java không được inject | SUT lấy từ `new` hay `@Autowired`? Có `@MockitoBean` đúng type? |
| `@Mock` field là `null` | Chưa khởi tạo Mockito annotations | `@ExtendWith(MockitoExtension.class)` hoặc `Mockito.mock(...)` |
| `@MockitoBean` không hoạt động | Không có Spring TestContext / import sai | Spring Boot/Framework version và test annotations |
| `@WebMvcTest` fail `UnsatisfiedDependencyException` | Service không nằm trong web slice | `@MockitoBean` service hoặc `@Import` nếu thật sự cần service thật |
| Bean override báo nhiều candidates | Type có nhiều implementation | `@Qualifier` hoặc tên bean rõ ràng |
| Test full context pass dù bean gốc biến mất | `REPLACE_OR_CREATE` tạo bean test mới | `enforceOverride = true` nếu cần kiểm bean tồn tại |
| Stub của spy kích hoạt request thật | Spy gọi method thật | `doReturn`/mock outbound dependency |
| Mockito báo `UnnecessaryStubbingException` | Stub không dùng/sai mock/sai argument | Kiểm object graph và actual invocations |
| Test full context vẫn không bắt bug trong mocked gateway | Gateway không chạy implementation thật | Viết test cho gateway hoặc integration phù hợp |
| Test chậm vì nhiều lần tạo context | Khác mock overrides, qualifiers, properties, `@DirtiesContext` | Nhóm cấu hình có chủ đích, ưu tiên unit/slice |
| Transaction/security không hoạt động như tưởng | Bean mang advice đã bị thay bằng mock | Giữ bean thật để kiểm AOP |
| Nâng Boot 4 không tìm thấy `@MockBean` | Legacy Spring Boot API đã được lên kế hoạch loại bỏ | Chuyển Spring TestContext `@MockitoBean` theo version |

Quy trình debug:
1. **Xác định SUT:** bean nào có logic phải chạy thật?
2. **Xác định owner:** SUT do test tự tạo hay Spring tạo?
3. **Xác định collaborator:** object nào được SUT giữ trong constructor/field?
4. **Kiểm vị trí mock:** chỉ là biến Java hay đã đăng ký bean override?
5. **Kiểm lựa chọn bean:** type, name, qualifier, scope, proxy, context hierarchy.
6. **Kiểm assertion:** có chứng minh behavior thật của SUT hay chỉ lặp lại stubbing? Với persistence/HTTP, đã assert trạng thái quan sát được chưa?

## 11. Mở rộng: khi nào cần cẩn trọng hơn?

### 11.1. Nhiều context hierarchy

Với `@ContextHierarchy`, bean override có thể áp dụng cho nhiều context levels theo mặc định; thuộc tính `contextName` của `@MockitoBean`/`@MockitoSpyBean` giúp giới hạn vào level có tên `@ContextConfiguration(name = "...")` tương ứng. Đây là tình huống nâng cao khi test parent/child context; không dùng nếu project chỉ có một Spring Boot context.

### 11.2. AOP và Mockito spy

`@MockitoSpyBean` dùng chiến lược WRAP thay vì REPLACE. Nếu bean ban đầu được Spring proxy, việc gọi method qua proxy và việc `verify` trên spy target cần quan sát cẩn thận. Tùy cấu hình, Spring giữ advice/proxy bao quanh spy; đừng mặc định proxy là cùng Java reference với spy.

### 11.3. Reactive/asynchronous code

Mock method trả Reactor `Mono`/`Flux` cần stub đúng publisher, nếu không có thể tạo `null` hoặc thiếu signal khi code subscribe. `verify(mock).send(...)` chỉ xác nhận method đã gọi, chưa chứng minh publisher được subscribe, message đã được broker xử lý hoặc transaction commit. Chọn StepVerifier, fake server, Testcontainers và integration test theo đúng behavior cần kiểm.

### 11.4. Không làm mock lọt vào production

`@MockitoBean` là công cụ cho **Spring TestContext**, đặt trong test source set và test annotations. Tránh để các bean test double trong `src/main` để làm application khởi động “dễ hơn”; điều đó có thể che lỗi cấu hình production. Nếu cần lựa chọn implementation theo environment, thiết kế rõ interface và configuration production/test.

### 11.5. Strictness của Mockito

JUnit MockitoExtension có chế độ phát hiện stub không được dùng, sai argument, và các interaction đáng ngờ. Nếu một stub không bao giờ được gọi, đây có thể chính là dấu hiệu mock sai vị trí. Đừng giải quyết mọi cảnh báo bằng `lenient()`; kiểm lại dependency graph và test intention.

## 12. Bài tập tự luyện

1. Trong `CheckoutServiceContextTest`, thay `@MockitoBean` bằng `@Mock` nhưng vẫn `@Autowired CheckoutService`. Dự đoán total và giải thích tại sao mock không được gọi.
2. Trong `CheckoutControllerWebTest`, bỏ `@MockitoBean CheckoutService`. Dự đoán vì sao MVC slice có thể fail khi constructor controller thiếu service bean.
3. Viết lại `CheckoutServiceUnitTest` bằng `new CheckoutService(shippingGateway)` thay `@InjectMocks`. Giải thích chỗ nào dependency được inject.
4. Với hai implementation `ShippingGateway`, thêm qualifier cho bean và test. Chọn đúng bean bằng `@MockitoBean(name = "...")`, sau đó kiểm lời gọi từ service thực.
5. Thêm một bean gateway thật chỉ được đăng ký dưới profile production. So sánh `@MockitoBean` mặc định và `enforceOverride=true` trong full context khi profile không bật.
6. Thêm một phương thức có side effect vào bean spy. So sánh `when(spy.method())` với `doReturn(...).when(spy).method()` và giải thích rủi ro.
7. Viết một test JPA với repository thật thay vì `@MockitoBean Repository`, rồi kiểm trạng thái database sau `saveAndFlush`. Điều gì mới được chứng minh?
8. Nêu lý do vì sao một full-context test đã mock service không thể khẳng định `@Transactional` của service thật vận hành đúng.

Đạt yêu cầu khi có thể nói rõ: **đối tượng nào thật, đối tượng nào giả, Spring/Mockito quản lý nó, ai đã inject nó, và assertion thực sự chứng minh điều gì**.

## 13. Checklist áp dụng

- [ ] Tôi đã xác định đúng SUT và collaborator cần mock chưa?
- [ ] SUT thuộc Java object graph do test tạo hay Spring `ApplicationContext`?
- [ ] Nếu unit không cần Spring, tôi dùng `@Mock`/`Mockito.mock` và constructor injection?
- [ ] Nếu Spring tạo SUT, tôi dùng `@MockitoBean` để thay đúng collaborator trong context?
- [ ] Nếu test controller MVC, service thường là `@MockitoBean` trong `@WebMvcTest`?
- [ ] Nếu test service logic, service vẫn là bean/object thật?
- [ ] Nếu cần bean thật tồn tại, `enforceOverride=true` có phù hợp?
- [ ] Nếu nhiều bean cùng type, đã chọn đúng name/`@Qualifier`?
- [ ] Nếu spy, có side effect hoặc AOP proxy cần chú ý không?
- [ ] Mock bean đang thay có phải bean mang transaction/cache/security tôi cần kiểm không?
- [ ] Tôi có biết phiên bản Spring Boot/Framework và package annotation đúng không?
- [ ] Có dùng `verify` trên object thực sự được SUT gọi không?
- [ ] Test có kiểm result/HTTP/DB thực theo boundary thay vì chỉ kiểm stubbing?
- [ ] Context cache/reset mock có che state chia sẻ nào không?

**Quy tắc nhớ lâu:** `@Mock` giả lập đối tượng Java, `@InjectMocks` nối các mock vào đối tượng do Mockito/test quản lý, còn `@MockitoBean` điều chỉnh bean graph trong **Spring TestContext**. `@MockitoSpyBean` theo dõi bean thật và có thể giữ logic gốc. Chọn công cụ theo **chủ sở hữu của SUT** và **ranh giới hành vi cần chứng minh**.

## 14. Nguồn chính thức

- Spring Framework 6.2 — `@MockitoBean` và `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework — Bean Overriding in Tests, AOP proxies: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 API — `@MockBean` deprecated: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/mock/mockito/MockBean.html
- Mockito — `@InjectMocks` Javadoc: https://javadoc.io/static/org.mockito/mockito-core/5.18.0/org.mockito/org/mockito/InjectMocks.html
- JUnit Jupiter — Extension Model: https://docs.junit.org/5.11.4/user-guide/
