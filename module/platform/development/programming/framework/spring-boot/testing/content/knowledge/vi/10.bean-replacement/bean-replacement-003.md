# Thay bean theo type, tên và qualifier khi có nhiều ứng viên trong Spring Boot Test

## 1. Mục tiêu

Giả sử ứng dụng có hai bean cùng implement interface `ShippingGateway`:

- `economyGateway`: vận chuyển thường, phí 10.
- `expressGateway`: vận chuyển nhanh, phí 30.

`QuoteService` thật sử dụng `expressGateway` bằng constructor injection. Trong test, nếu bạn muốn mock riêng `expressGateway` trả phí 55 và giữ `economyGateway` thật, làm sao Spring biết **chính xác bean nào cần thay**?

Đó là mục tiêu của bài này: hiểu và áp dụng cơ chế chọn bean bằng **type (kiểu)**, **bean name (tên bean)**, **`@Qualifier` (bộ lọc ứng viên)**, cùng quy tắc **fallback field name** của `@MockitoBean`. Bài học cũng giải thích các trường hợp có nhiều candidate, tác động của `@Primary`, mock tạo mới vì đánh sai tên, quy tắc `enforceOverride` và cách kiểm chứng một bean thật sự đã bị thay trong `ApplicationContext`.

Sau khi học, bạn có thể:
- Vẽ ra các bean candidates theo một interface và xác định injection point của service.
- Chọn đúng syntax `@MockitoBean` ở field hoặc class khi muốn thay một bean cụ thể.
- Giải quyết ambiguity bằng explicit `name` hoặc `@Qualifier`, hiểu giới hạn của việc trông chờ vào tên field.
- Phân biệt **bean name** với **qualifier metadata** và với **tên biến Java**.
- Dùng `@MockitoSpyBean` đúng target, đồng thời bảo vệ các bean còn lại.
- Viết JUnit/Spring Boot tests có khả năng phát hiện trường hợp “test pass vì đã tạo bean mới” thay vì thay bean production.
- Chẩn đoán `NoUniqueBeanDefinitionException`, lỗi bean override và dependency injection không đi đến mock.

Ngữ cảnh kỹ thuật: **Java 17+, Spring Boot 3.5.16, Spring Framework 6.2, JUnit Jupiter, Mockito**. Spring Boot 3.4–3.5 dùng API `org.springframework.test.context.bean.override.mockito.MockitoBean` và `MockitoSpyBean`. Với các phiên bản khác, đối chiếu tài liệu tương ứng trước khi copy annotation/import.

## 2. Hai lựa chọn độc lập: bean Spring inject vào service và bean test muốn override

Đầu tiên, phải tách **hai quyết định**:

1. **Production wiring:** Spring chọn bean nào để inject vào constructor/field của `QuoteService`.
2. **Test bean override:** Spring TestContext chọn bean nào để thay bằng Mockito mock/spy **trước khi context cho test được sử dụng**.

Chúng liên quan nhưng không đồng nhất. Một annotation ở test chỉ có tác dụng mong muốn nếu nó xác định đúng bean mà service nhận.

```text
ApplicationContext của ứng dụng
  |
  +-- economyGateway : ShippingGateway (implementation thật, phí 10)
  |
  +-- expressGateway : ShippingGateway (implementation thật, phí 30)
  |
  +-- quoteService   : QuoteService
          |
          +-- constructor @Qualifier("expressGateway")
                    -> expressGateway

ApplicationContext của test override đúng:
  economyGateway : bean thật (phí 10)
  expressGateway : Mockito mock (stub phí 55)
  quoteService   : bean thật -> expressGateway mock
```

Nếu test tạo `ShippingGateway mock = Mockito.mock(...)` rồi không đưa vào context, `QuoteService` do Spring tạo vẫn dùng `expressGateway` thật. Nếu test override **nhầm** `economyGateway`, service vẫn dùng `expressGateway` thật. Nếu test tạo một bean mới tên `typoGateway`, service vẫn dùng `expressGateway` thật.

**Nhãn “test có mock” chưa đủ. Hãy hỏi: mock đang thay bean có tên nào, và đường gọi từ service thực sự trỏ tới đâu?**

## 3. Thuật ngữ cốt lõi

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Bean type | Kiểu Java của bean, có thể là interface/superclass | `ShippingGateway` |
| Bean name | Tên định danh duy nhất trong một context; có thể khai báo tường minh và có alias | `"expressGateway"` |
| Bean candidate | Bean phù hợp kiểu cùng các quy tắc autowiring khác | Hai implementation của `ShippingGateway` |
| `@Qualifier` | Metadata/ràng buộc dùng để lọc candidates theo type | `@Qualifier("expressGateway")` |
| Field name fallback | Khi không có qualifier, tên **field test** có thể làm qualifier dự phòng cho override | `@MockitoBean ShippingGateway expressGateway;` |
| `@Primary` | Ưu tiên một bean khi Spring autowire có nhiều ứng viên thích hợp | `@Primary` trên một implementation |
| Bean override | Spring TestContext thay hoặc wrap bean trong context của test | `@MockitoBean` hoặc `@MockitoSpyBean` |
| SUT | System under test: đối tượng có hành vi thật đang kiểm | `QuoteService` |
| Mock | Mockito double, không chạy implementation thật theo mặc định | `when(mock.fee("HCM")).thenReturn(55)` |
| Spy | Wrapper theo dõi bean thật, gọi method thật nếu không stub | `@MockitoSpyBean(name="expressGateway")` |

**Bean name không đồng nghĩa tên class hoặc tên interface.** Một bean từ `@Component` thường có tên suy ra từ class theo quy tắc naming của Spring. Bean từ `@Bean` thường có tên từ method trừ khi cấu hình khác. Khi có nhiều implementation, nên đặt name rõ ràng, nhất là với các adapter có vai trò nghiệp vụ khác nhau.

**`@Qualifier("fast")` không phải trong mọi tình huống là lời yêu cầu bean tên `fast`.** Qualifier là cơ chế lọc trong số bean tương thích type: nó có thể khớp bean name hoặc qualifier metadata được khai báo. Ngược lại, `@MockitoBean(name="fast")` hướng đến **bean name** cụ thể. Nếu bean thật tên `expressGateway` nhưng được gắn qualifier riêng `fast`, hai cách này có thể chọn khác nhau.

## 4. Quy tắc chọn bean của `@MockitoBean` trong Spring Framework 6.2

### 4.1. Đặt trên field: type trước, qualifier/name để phân biệt

```java
@MockitoBean
ShippingGateway shippingGateway;
```

Trước hết Spring xem **field type** (`ShippingGateway`). Nếu có đúng một bean phù hợp, nó có thể thay bean đó. Nếu có nhiều bean phù hợp, Spring cần tiêu chí phân biệt:
- `@Qualifier` gắn trên field.
- Hoặc, nếu không có `@Qualifier`, tên field Java được dùng như **fallback qualifier**.
- Hoặc chỉ định chính xác bean name bằng thuộc tính `name`/`value` của `@MockitoBean`.

Khi trong context chỉ có bean duy nhất `pricingService` với type `PricingService`, viết `@MockitoBean PricingService pricingService;` là đủ. Nhưng với hai `ShippingGateway`, `@MockitoBean ShippingGateway gateway;` thường mơ hồ vì không bean nào tên `gateway` và không có qualifier nào chọn đúng một candidate.

### 4.2. Ba cách chọn đích rõ ràng

**Cách A — chỉ định bean name trực tiếp:**

```java
@MockitoBean(name = "expressGateway", enforceOverride = true)
ShippingGateway mockExpress;
```

Đây là lựa chọn dễ audit nhất nếu bạn biết tên đăng ký thực tế của bean. Tên field `mockExpress` không cần trùng bean name, vì `name` đã chỉ đích.

**Cách B — dùng `@Qualifier` trên field override:**

```java
@MockitoBean
@Qualifier("expressGateway")
ShippingGateway selectedGateway;
```

Dùng khi project đã sử dụng qualifier trong wiring. Spring lọc các bean type `ShippingGateway` theo qualifier value. `@Qualifier` cần import `org.springframework.beans.factory.annotation.Qualifier`.

**Cách C — dùng tên field làm fallback qualifier:**

```java
@MockitoBean
ShippingGateway expressGateway;
```

Nếu có bean tương thích type mang name `expressGateway`, Spring có thể chọn nó nhờ fallback field name. Cách này ngắn nhưng dễ bị ảnh hưởng khi refactor tên field. Với nhiều ứng viên có vai trò khác nhau, ưu tiên **explicit name/qualifier** để ý định kiểm thử không phụ thuộc tên biến tình cờ.

### 4.3. So sánh cách khai báo và kết quả

| Khai báo trong test | Context có `economyGateway` và `expressGateway` | Kết quả dự kiến |
| --- | --- | --- |
| `@MockitoBean ShippingGateway gateway;` | Hai bean cùng type; không target tên `gateway` | Ambiguous; context có thể fail khi xử lý override |
| `@MockitoBean ShippingGateway expressGateway;` | Có bean tên `expressGateway` | Fallback field-name chọn express |
| `@MockitoBean @Qualifier("expressGateway") ShippingGateway target;` | Candidate theo qualifier/name | Chọn express |
| `@MockitoBean(name="expressGateway") ShippingGateway target;` | Bean name express tồn tại | Chọn express |
| `@MockitoBean(name="economyGateway") ShippingGateway target;` | Bean name economy tồn tại | Chọn economy; service dùng express vẫn thật |
| `@MockitoBean(name="expresGateway") ShippingGateway target;` | Đánh sai tên; mặc định REPLACE_OR_CREATE | Có thể tạo **bean mock mới**; express thật không bị thay |
| `@MockitoBean(name="expresGateway", enforceOverride=true) ShippingGateway target;` | Không tồn tại tên đó | Context fail, giúp bắt typo |
| `@MockitoBean QuoteService quoteService;` | Chỉ một bean QuoteService | Thay service theo type; không kiểm logic service thật |

Hãy kiểm **cả bean bị thay lẫn bean không bị thay**. Chỉ `verify(mock).fee("HCM")` chưa chứng minh toàn graph đang như mong muốn nếu test tự gọi mock hoặc chính SUT cũng là mock.

### 4.4. `value` là alias của `name`

```java
@MockitoBean("expressGateway")
ShippingGateway gateway;
```

Có thể dùng dạng ngắn khi không cần thuộc tính khác. Trong bài thực hành dùng `name="expressGateway"` vì rõ và có thể đi với `enforceOverride=true`.

### 4.5. Lưu ý với `@Primary`

`@Primary` ưu tiên candidate khi Spring autowire một dependency theo type nhưng có nhiều implementation. Tuy nhiên **bean override vẫn có logic chọn target riêng**, với quy tắc type, field qualifier, fallback field name và explicit name. Không coi việc một bean `@Primary` là đủ để test luôn mock đúng bean đó, đặc biệt khi cần thay bean khác `@Primary`.

Nếu production service thực sự dùng `@Qualifier("expressGateway")`, override cần chọn `expressGateway`; dù `economyGateway` có `@Primary`, explicit qualifier của service vẫn quyết định dependency theo các quy tắc wiring của Spring.

## 5. Phân biệt `@Qualifier` của dependency injection với `@Qualifier` của field test

Hai vị trí thường thấy:

```java
@Service
class QuoteService {
    private final ShippingGateway gateway;

    QuoteService(@Qualifier("expressGateway") ShippingGateway gateway) {
        this.gateway = gateway;
    }
}
```

```java
@SpringBootTest
class QuoteServiceTest {
    @MockitoBean
    @Qualifier("expressGateway")
    ShippingGateway selected;

    @Autowired
    QuoteService quoteService;
}
```

Qualifier **trên constructor** nói Spring phải inject implementation có qualifier phù hợp. Qualifier **trên field test** nói cơ chế override phải tìm đúng bean target. Đó là hai điểm lựa chọn khác nhau; thông thường chúng cần nhắm tới cùng bean nếu bạn muốn stub tác động đến service.

Ví dụ một bean có name và qualifier metadata khác:

```java
// Đoạn minh họa không nằm trong project mẫu:
@Bean("expressGateway")
@Qualifier("priority")
ShippingGateway expressGateway() {
    return new ExpressGateway();
}
```

Khi có nhiều bean cùng type:
- `@Qualifier("priority")` có thể lọc đến bean name `expressGateway` nhờ qualifier metadata nếu nhãn này phân biệt được duy nhất.
- `@MockitoBean(name = "expressGateway")` chọn bean name express.
- `@MockitoBean(name = "priority")` tìm bean có **name priority**; nó không tự diễn giải `priority` thành qualifier metadata. Nếu không có bean mang tên đó và không enforce, nó có thể **tạo một mock bean mới**.

Vì vậy, khi gặp tên kiểu `"priority"`, hãy xác định đó là name, alias hay qualifier. Không suy từ giá trị string của `@Qualifier` rằng nó luôn là bean name.

### 5.1. Qualifier có thể không duy nhất

Spring cho phép dùng một qualifier value như bộ lọc trên nhiều bean, nhất là khi inject `List<ShippingGateway>` hoặc `Set<ShippingGateway>`. Nếu hai bean đều có qualifier `"fast"`, field `@MockitoBean @Qualifier("fast") ShippingGateway gateway;` vẫn chưa đủ để xác định **một** bean. Chọn name cụ thể hoặc tách qualifier theo contract.

### 5.2. Bean name và alias

Spring bean registry có thể gắn một hoặc nhiều alias cho cùng bean. Khi cần override một candidate, nên dùng canonical bean name được cấu hình rõ, kiểm metadata của context khi debug và tránh để test phụ thuộc alias không ổn định sau refactor. Điều này hữu ích khi project có `@Bean(name={"expressGateway","fastShipping"})` hoặc nhiều module import configuration.

### 5.3. Tên field fallback ảnh hưởng context cache

Spring TestContext dùng các qualifier, kể cả fallback field name, như một yếu tố khi xác định cấu hình context có thể tái sử dụng. Hai lớp test thay cùng bean nhưng dùng tên field khác nhau có thể tạo **cache key** khác nhau và khiến Spring khởi động nhiều context hơn.

Do đó:
- Với cùng target bean, chọn tên field và qualifier nhất quán.
- Với bean đặc biệt dễ nhầm, explicit `name` giúp người review nhận ra target.
- Đừng ép mọi test dùng chung nhiều mock không cần thiết chỉ để tăng cache hit: chọn đúng boundary quan trọng hơn micro-optimization.

## 6. Demo đầy đủ có thể chạy: hai bean cùng interface

Dự án dưới đây minh họa sáu cách test, hai trường hợp cố ý thất bại, và sự khác biệt giữa “mock đã được tạo” với “bean đúng đã được thay”.

### 6.1. Cấu trúc Maven

```text
bean-selection-lab/
├── pom.xml
├── src/main/java/com/example/beanselection/
│   ├── BeanSelectionApplication.java
│   ├── ShippingGateway.java
│   ├── EconomyGateway.java
│   ├── ExpressGateway.java
│   └── QuoteService.java
└── src/test/java/com/example/beanselection/
    ├── OriginalWiringTest.java
    ├── UniqueTypeOverrideTest.java
    ├── NamedOverrideTest.java
    ├── QualifierOverrideTest.java
    ├── FieldNameFallbackTest.java
    ├── ClassLevelOverrideTest.java
    ├── SelectedSpyTest.java
    ├── WrongNameCreatesBeanTest.java
    ├── AmbiguousOverrideExercise.java
    └── MissingTargetExercise.java
```

Tất cả test `*Test` dự kiến PASS. Hai lớp tên `*Exercise` được thiết kế FAIL khi bạn chọn chạy riêng, nên không được Maven Surefire chọn theo naming pattern test mặc định.

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
  <artifactId>bean-selection-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
```

`spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito và Spring TestContext theo dependency management của Spring Boot. Project không cần web server, database hoặc Docker.

### 6.3. Application và hai implementation

`src/main/java/com/example/beanselection/BeanSelectionApplication.java`:

```java
package com.example.beanselection;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BeanSelectionApplication {
    public static void main(String[] args) {
        SpringApplication.run(BeanSelectionApplication.class, args);
    }
}
```

`src/main/java/com/example/beanselection/ShippingGateway.java`:

```java
package com.example.beanselection;

public interface ShippingGateway {
    int fee(String city);
}
```

`src/main/java/com/example/beanselection/EconomyGateway.java`:

```java
package com.example.beanselection;

import org.springframework.stereotype.Component;

@Component("economyGateway")
public class EconomyGateway implements ShippingGateway {
    @Override
    public int fee(String city) {
        return 10;
    }
}
```

`src/main/java/com/example/beanselection/ExpressGateway.java`:

```java
package com.example.beanselection;

import org.springframework.stereotype.Component;

@Component("expressGateway")
public class ExpressGateway implements ShippingGateway {
    @Override
    public int fee(String city) {
        return 30;
    }
}
```

`src/main/java/com/example/beanselection/QuoteService.java`:

```java
package com.example.beanselection;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final ShippingGateway gateway;

    public QuoteService(@Qualifier("expressGateway") ShippingGateway gateway) {
        this.gateway = gateway;
    }

    public int total(int subtotal, String city) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be >= 0");
        }
        return subtotal + gateway.fee(city);
    }
}
```

Khi không mock: `total(100,"HCM") = 100 + 30 = 130`. Bean `economyGateway` vẫn tồn tại nhưng không được `QuoteService` chọn. Đây là điểm mấu chốt cho các test bên dưới.

### 6.4. Test #1 — Không override: xác nhận wiring gốc

`src/test/java/com/example/beanselection/OriginalWiringTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class OriginalWiringTest {
    @Autowired QuoteService quoteService;
    @Autowired ApplicationContext context;

    @Test
    void serviceUsesExpressAndBothBeansExist() {
        assertEquals(130, quoteService.total(100, "HCM"));
        assertEquals(10,
                context.getBean("economyGateway", ShippingGateway.class)
                        .fee("HCM"));
        assertEquals(30,
                context.getBean("expressGateway", ShippingGateway.class)
                        .fee("HCM"));
        assertTrue(context.containsBean("economyGateway"));
        assertTrue(context.containsBean("expressGateway"));
    }
}
```

Test này xác nhận **cấu hình thật**: cả hai bean có mặt, service chọn express. Nó hữu ích làm baseline để hiểu mọi thay đổi trong các test override.

### 6.5. Test #2 — Chỉ có một `QuoteService`: override theo type

`src/test/java/com/example/beanselection/UniqueTypeOverrideTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.Mockito.when;

@SpringBootTest
class UniqueTypeOverrideTest {
    @MockitoBean(enforceOverride = true)
    QuoteService quoteService;

    @Autowired ApplicationContext context;

    @Test
    void uniqueTypeIdentifiesServiceBean() {
        when(quoteService.total(100, "HCM")).thenReturn(999);

        assertEquals(999, quoteService.total(100, "HCM"));
        assertSame(quoteService, context.getBean(QuoteService.class));
    }
}
```

Vì chỉ có một `QuoteService`, type đủ chọn target. Test này **không kiểm logic QuoteService** vì đã mock chính service; mục tiêu chỉ là chứng minh chọn bean theo type. Trong unit test nghiệp vụ, giữ service thật và mock gateway.

### 6.6. Test #3 — Có nhiều gateway: override theo bean name

`src/test/java/com/example/beanselection/NamedOverrideTest.java`:

```java
package com.example.beanselection;

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
class NamedOverrideTest {
    @MockitoBean(name = "expressGateway", enforceOverride = true)
    ShippingGateway target;

    @Autowired QuoteService quoteService;
    @Autowired ApplicationContext context;

    @Test
    void replacesExpressAndLeavesEconomyReal() {
        when(target.fee("HCM")).thenReturn(55);

        assertEquals(155, quoteService.total(100, "HCM"));
        verify(target).fee("HCM");

        assertSame(target,
                context.getBean("expressGateway", ShippingGateway.class));
        assertEquals(10,
                context.getBean("economyGateway", ShippingGateway.class)
                        .fee("HCM"));
    }
}
```

Tên field test là `target`, nhưng name annotation tường minh là `expressGateway` nên Spring thay đúng bean express. Test assert cả output từ service thật (155), instance trong context, và economy vẫn hoạt động với phí 10.

### 6.7. Test #4 — Override theo `@Qualifier`

`src/test/java/com/example/beanselection/QualifierOverrideTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest
class QualifierOverrideTest {
    @MockitoBean
    @Qualifier("expressGateway")
    ShippingGateway selected;

    @Autowired QuoteService quoteService;

    @Test
    void qualifierSelectsTheCorrectCandidate() {
        when(selected.fee("HCM")).thenReturn(55);

        assertEquals(155, quoteService.total(100, "HCM"));
        verify(selected).fee("HCM");
    }
}
```

Tên field là `selected`, khác bean name. `@Qualifier("expressGateway")` phân biệt hai candidates. Trong ứng dụng thật có qualifier metadata khác tên bean, cách này cũng có thể chọn target theo metadata thay vì exact bean name.

### 6.8. Test #5 — Fallback theo tên field

`src/test/java/com/example/beanselection/FieldNameFallbackTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@SpringBootTest
class FieldNameFallbackTest {
    @MockitoBean
    ShippingGateway expressGateway;

    @Autowired QuoteService quoteService;

    @Test
    void fieldNameActsAsFallbackQualifier() {
        when(expressGateway.fee("HCM")).thenReturn(55);

        assertEquals(155, quoteService.total(100, "HCM"));
    }
}
```

Đây là quy tắc **fallback**, không phải cách đặt tên bean qua annotation. Nếu đổi field `expressGateway` thành `gateway` khi vẫn có hai candidates, test có thể fail lúc load context vì không còn đủ thông tin chọn bean.

### 6.9. Test #6 — Override ở cấp class bằng `types` và `name`

`src/test/java/com/example/beanselection/ClassLevelOverrideTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@SpringBootTest
@MockitoBean(
        types = {ShippingGateway.class},
        name = "expressGateway",
        enforceOverride = true)
class ClassLevelOverrideTest {
    @Autowired QuoteService quoteService;

    @Autowired
    @Qualifier("expressGateway")
    ShippingGateway mockExpress;

    @Test
    void typeLevelDeclarationTargetsNamedBean() {
        when(mockExpress.fee("HCM")).thenReturn(55);

        assertEquals(155, quoteService.total(100, "HCM"));
    }
}
```

Khi annotation đặt trên **class**, phải khai báo `types` vì không có field làm nguồn suy ra type. Nếu chỉ định `name`, danh sách `types` phải chứa **một kiểu**; để thay nhiều bean khác tên, dùng nhiều annotation `@MockitoBean` (repeatable) hoặc cấu hình riêng có kiểm soát.

### 6.10. Test #7 — Spy đúng một bean trong số nhiều candidates

`src/test/java/com/example/beanselection/SelectedSpyTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;

@SpringBootTest
class SelectedSpyTest {
    @MockitoSpyBean(name = "expressGateway")
    ShippingGateway expressGateway;

    @Autowired QuoteService quoteService;

    @Test
    void spyTargetsOneRealBeanWithoutReplacingBehavior() {
        assertEquals(130, quoteService.total(100, "HCM"));
        verify(expressGateway).fee("HCM");
    }
}
```

`@MockitoSpyBean` dùng strategy **WRAP** và yêu cầu đúng một bean phù hợp đã có. Khi không stub, method thật của ExpressGateway chạy nên phí vẫn 30. `@MockitoBean` dùng mock thay toàn bộ bean và method chưa stub trả giá trị mặc định (ở đây `int` thường 0).

Khi spy method có side effect, `when(spy.method()).thenReturn(value)` có thể gọi method thật lúc stubbing; ưu tiên `doReturn(value).when(spy).method()` khi cần tránh side effect.

### 6.11. Test #8 — Sai tên nhưng vẫn tạo thêm mock bean

`src/test/java/com/example/beanselection/WrongNameCreatesBeanTest.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class WrongNameCreatesBeanTest {
    // Cố ý sai chính tả: "expresGateway" (thiếu s).
    @MockitoBean(name = "expresGateway")
    ShippingGateway newMock;

    @Autowired QuoteService quoteService;
    @Autowired ApplicationContext context;

    @Test
    void newMockDoesNotReplaceRealExpressBean() {
        assertTrue(context.containsBean("expresGateway"));
        assertTrue(context.containsBean("expressGateway"));
        assertEquals(130, quoteService.total(100, "HCM"));
    }
}
```

Đây là một **bài kiểm dương tính để minh họa bẫy**, không phải chiến lược test ứng dụng: vì mặc định `@MockitoBean` là `REPLACE_OR_CREATE`, một bean mock tên `expresGateway` có thể được tạo mới. Service có `@Qualifier("expressGateway")` vẫn dùng bean express thật và trả 130. Không được suy luận “test dùng `@MockitoBean` nên mock chắc chắn thay bean cũ”.

Muốn bắt typo khi chủ đích là thay một bean **đang có**, dùng `enforceOverride = true` như test #3.

### 6.12. Các lệnh chạy

Tại thư mục `bean-selection-lab`, dùng JDK 17+ và Maven:

```bash
mvn -q clean test
mvn -q -Dtest=NamedOverrideTest test
mvn -q -Dtest=QualifierOverrideTest test
mvn -q -Dtest=FieldNameFallbackTest test
mvn -q -Dtest=ClassLevelOverrideTest test
mvn -q -Dtest=SelectedSpyTest test
mvn -q -Dtest=WrongNameCreatesBeanTest test
```

Tất cả lớp có hậu tố `Test` được thiết kế PASS khi cấu hình/versions như project trên. Maven trả exit code 0 nếu mọi test thành công; log Spring, thứ tự và thống kê thời gian có thể khác môi trường.

Kỳ vọng hành vi được assert:

| Lớp | Mock/spy nào | Kết quả `quoteService.total(100,"HCM")` |
| --- | --- | --- |
| `OriginalWiringTest` | Không mock | 130 |
| `UniqueTypeOverrideTest` | Mock chính QuoteService | Stub trả 999; không kiểm service thật |
| `NamedOverrideTest` | Mock express theo name | 155 |
| `QualifierOverrideTest` | Mock express theo qualifier | 155 |
| `FieldNameFallbackTest` | Mock express qua tên field | 155 |
| `ClassLevelOverrideTest` | Mock express ở cấp class | 155 |
| `SelectedSpyTest` | Spy express thật | 130 |
| `WrongNameCreatesBeanTest` | Tạo mock bean mới sai tên | 130 |

Không cần `javac` riêng lẻ: các test dùng Spring/JUnit/Mockito nằm trong Maven test classpath; lệnh tái lập là `mvn test` (hoặc `mvn -q clean test` trên môi trường sạch).

## 7. Hai bài tập cố ý gây lỗi context

Các lớp sau đặt tên `*Exercise` để không được Surefire chạy mặc định; chỉ chạy khi muốn quan sát lỗi. **Không** đưa chúng vào một suite CI mặc định yêu cầu PASS.

### 7.1. Không qualifier khi có hai ứng viên

`src/test/java/com/example/beanselection/AmbiguousOverrideExercise.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class AmbiguousOverrideExercise {
    // "gateway" không trùng "economyGateway" hoặc "expressGateway".
    @MockitoBean
    ShippingGateway gateway;

    @Test
    void contextCannotChooseBetweenTwoGatewayBeans() {
        // Không nên tới method này nếu context override mơ hồ.
    }
}
```

Chạy:

```bash
mvn -Dtest=AmbiguousOverrideExercise test
```

Dự kiến test **FAIL lúc tải ApplicationContext**: Spring thấy nhiều bean phù hợp type `ShippingGateway` và không có qualifier/fallback name xác định được một target. Đọc root cause của bean override, không sửa bằng cách chuyển toàn bộ production beans sang một implementation.

Cách sửa đúng ý định: thêm `@Qualifier("expressGateway")`, đổi thành `@MockitoBean(name="expressGateway")`, hoặc đặt tên field `expressGateway` nếu muốn dùng fallback. Ưu tiên explicit theo hợp đồng.

### 7.2. Bean name không tồn tại và `enforceOverride=true`

`src/test/java/com/example/beanselection/MissingTargetExercise.java`:

```java
package com.example.beanselection;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class MissingTargetExercise {
    @MockitoBean(name = "expresGateway", enforceOverride = true)
    ShippingGateway gateway;

    @Test
    void cannotReplaceNonexistentNamedBean() {
        // Không chạy vì không có bean tên "expresGateway".
    }
}
```

Chạy:

```bash
mvn -Dtest=MissingTargetExercise test
```

Dự kiến FAIL trong context preparation vì chế độ **REPLACE** yêu cầu bean có sẵn. Khác với `WrongNameCreatesBeanTest` không enforce: ở đó một mock mới được tạo và test có thể xanh dù bean thật không thay.

Sửa `"expresGateway"` thành `"expressGateway"` khi đó đúng tên bean trong project. Lưu ý thời gian/stack trace chính xác phụ thuộc Spring Framework/Maven/Surefire; không coi bất kỳ thông báo được tóm tắt trong tài liệu này là stdout nguyên văn.

## 8. Nhiều candidates: quyết định từng bước như thế nào?

Khi mở một project thật, dùng quy trình sau:

1. **Xác định type** mà collaborator cần, ví dụ `PaymentPort`.
2. **Liệt kê bean definitions thuộc type đó** và tên bean thực tế. Đừng đoán từ tên class; `@Bean` method, `@Component("name")`, alias, profile, `@Conditional` có thể thay đổi danh sách.
3. **Xem injection point của SUT**: constructor có `@Qualifier`? `@Primary`? bean name? Injection qua `Map<String,PaymentPort>` hay list?
4. **Xác định target override**: bean nào thực sự tạo side effect hoặc trả dữ liệu cần giả lập?
5. **Chọn syntax tường minh**: `@MockitoBean(name="...")` khi biết bean name; `@MockitoBean @Qualifier("...")` nếu dự án dùng qualifier metadata phân biệt; chỉ dùng type khi duy nhất.
6. **Cân nhắc `enforceOverride=true`** khi muốn test FAIL nếu target bean không được tạo bởi cấu hình ứng dụng.
7. **Kiểm bằng hành vi**: stub mock → gọi SUT thật → assert output/side effect; kiểm những bean khác không bị override sai.
8. **Giữ context test đúng phạm vi**: slice test chỉ có một tập bean con; việc có/không có candidate khác full app là bình thường nhưng cần được hiểu.

Ví dụ kiểm danh sách theo type trong một context test:

```java
// Đoạn minh họa trong test đã @Autowired ApplicationContext context:
Map<String, ShippingGateway> beans =
        context.getBeansOfType(ShippingGateway.class);
System.out.println(beans.keySet());
```

Cần import `java.util.Map`. Trong project mẫu, với context không override, danh sách bean type này chứa ít nhất tên `economyGateway` và `expressGateway`. Thứ tự hiển thị của key set không phải contract; đừng assert một thứ tự map không được công bố. Với mock bean, `getBeansOfType` còn cho thấy tên được đăng ký mới nếu `REPLACE_OR_CREATE` xảy ra.

Một cách kiểm rõ khi có multiple candidates:

```java
ShippingGateway express =
        context.getBean("expressGateway", ShippingGateway.class);
ShippingGateway economy =
        context.getBean("economyGateway", ShippingGateway.class);

assertThat(Mockito.mockingDetails(express).isMock()).isTrue();
assertThat(Mockito.mockingDetails(economy).isMock()).isFalse();
```

Đây là **đoạn minh họa** khi một test đã dùng `@MockitoBean(name="expressGateway")` và import AssertJ/Mockito. Với bean proxy hoặc spy, `mockingDetails(...).isMock()` có thể cần xét target/proxy; không dùng nó làm tiêu chí duy nhất cho mọi kiến trúc AOP. Trong project demo đơn giản, kiểm này có ý nghĩa trực tiếp.

## 9. Nếu thay sai bean: triệu chứng và nguyên nhân

### 9.1. Stub đã đặt nhưng SUT vẫn chạy implementation thật

```java
@MockitoBean(name = "economyGateway")
ShippingGateway economy;

@Autowired QuoteService quoteService;

@Test
void wrongTarget() {
    when(economy.fee("HCM")).thenReturn(55);
    // QuoteService dùng expressGateway, nên vẫn trả 130.
    assertEquals(130, quoteService.total(100, "HCM"));
}
```

Đây là một **đoạn minh họa**, không phải file độc lập. Nếu bạn dự định kết quả 155 nhưng nhận 130, có thể đã mock nhầm `economyGateway`. Spring không tự đổi injection point của service sang economy chỉ vì test thay economy bean.

Trong Mockito strictness, stub không dùng có thể tạo cảnh báo/lỗi tùy runner và cách mock được quản lý. Khi chẩn đoán, kiểm target và đường gọi thực, đừng thêm `lenient()` để che dấu.

### 9.2. Field tên khác sau refactor khiến override đổi target

Ban đầu:

```java
@MockitoBean ShippingGateway expressGateway;
```

Sau refactor chỉ đổi field name:

```java
@MockitoBean ShippingGateway gateway;
```

Nếu context có hai candidates, behavior chọn bean có thể từ “chọn express nhờ fallback” thành “ambiguous”. Đây là lý do explicit `name`/`@Qualifier` thường thích hợp hơn với test quan trọng.

### 9.3. `@Primary` bị hiểu là “test sẽ override primary”

Production `@Autowired` có thể chọn một bean `@Primary`, nhưng cơ chế override của `@MockitoBean` dựa trên type và qualifier/name trong test. Nếu test cố thay implementation cụ thể khác primary, phải nói rõ target. Với những project phức tạp, xem bean definitions của context để xác nhận quyết định trước khi sửa test.

### 9.4. `@Qualifier` gắn sai nơi

```java
@MockitoBean
ShippingGateway mockExpress;

@Autowired
@Qualifier("expressGateway")
QuoteService quoteService;
```

Ví dụ này **không hợp lý** nếu `QuoteService` chỉ có một bean và `@Qualifier` được gắn lên field **QuoteService** thay vì `ShippingGateway`: nó không giúp phân biệt ShippingGateway candidates cho override. Qualifier phải nằm trên **field mock cần chọn** (hoặc explicit `name` trên `@MockitoBean`), và injection point của service phải có qualifier nếu production wiring yêu cầu.

### 9.5. Test slice tạo mock nhưng không có production bean

Trong `@WebMvcTest`, service collaborator thường không có bean thật vì slice chỉ load MVC-related beans. `@MockitoBean Service service;` dùng `REPLACE_OR_CREATE` để đăng ký mock. Điều đó là đúng cho mục tiêu web slice, **không** chứng minh production có service bean.

Trong `@SpringBootTest` mà mục tiêu là xác nhận bean production có tồn tại, dùng `enforceOverride=true` khi thay bean thật; nếu không có, test sẽ fail thay vì sinh mock bean mới.

### 9.6. Bean đúng nhưng type field không tương thích

Nếu bean `expressGateway` có class/interface type `ShippingGateway` nhưng test khai báo `@MockitoBean(name="expressGateway") WrongInterface mock;`, type có thể không tương thích với dependency đang chờ. Luôn dùng type tương thích và cùng contract mà service nhận; naming không thay thế type safety.

### 9.7. `@MockitoSpyBean` không tìm được đúng một target

Khác `@MockitoBean`, spy cần một bean hiện hữu chính xác để wrap. Khi có nhiều bean cùng type, chọn `name` hoặc qualifier. Khi target thiếu hoàn toàn, không có chế độ “create new spy” tương tự `REPLACE_OR_CREATE`; phải sửa context hoặc dùng mock bean nếu không cần hành vi thật.

## 10. Các trường hợp nâng cao

### 10.1. Bean override từ `@Bean` method

Thay vì `@Component("expressGateway")`, project thực tế có thể đăng ký:

```java
@Configuration(proxyBeanMethods = false)
class ShippingConfiguration {
    @Bean("economyGateway")
    ShippingGateway economyGateway() {
        return new EconomyGateway();
    }

    @Bean("expressGateway")
    ShippingGateway expressGateway() {
        return new ExpressGateway();
    }
}
```

Đây là code **minh họa thay thế cơ chế đăng ký của project mẫu**, không thêm đồng thời vào project mẫu vì sẽ tạo trùng bean names. `@MockitoBean(name="expressGateway")` vẫn chọn bean theo name. Đừng vô tình cùng lúc để `@Component` và `@Bean` cho cùng instance loại này rồi chẩn đoán sai lỗi duplicate/ambiguity.

### 10.2. Nhiều bean cùng generic raw type

Giả sử có `Store<Customer>` và `Store<Order>`. Generics có thể là một phần cơ chế autowiring qualifier trong Spring, nhưng test bean override phải nhìn đúng **type/signature** và metadata mà Spring TestContext hỗ trợ. Đừng dùng raw `Store` mơ hồ khi nhiều beans, hoặc giả định type erasure không gây vấn đề. Chọn bean name rõ hoặc khai báo type phù hợp theo tài liệu API, rồi xác minh bằng test context.

### 10.3. FactoryBean và scope

Spring Framework bean override chỉ hỗ trợ **singleton beans**; override non-singleton có thể fail. Nếu một bean là product của `FactoryBean`, `@MockitoBean` thay bean product bằng singleton mock, còn `@MockitoSpyBean` tạo spy của **object do FactoryBean tạo**, không spy chính FactoryBean. Nếu hệ thống có scoped proxy, phải biết object nào được inject để tránh verify nhầm proxy.

### 10.4. Context hierarchy

Với `@ContextHierarchy`, một `@MockitoBean` có thể được áp dụng tới **mọi level** theo mặc định. Khi muốn chỉ thay bean ở child context, dùng `contextName` khớp `@ContextConfiguration(name="...")`:

```java
@MockitoBean(
    name = "expressGateway",
    contextName = "app-config")
ShippingGateway expressGateway;
```

Đây là ví dụ cú pháp, chỉ có ý nghĩa trong test có context hierarchy thật với level `app-config`. Project Maven ở mục 6 chỉ dùng một ApplicationContext, nên không cần cấu hình này.

### 10.5. Type-level và repeatable overrides

`@MockitoBean` có thể đặt trên class, superclass, interface và ở dạng meta-annotation phù hợp. Ví dụ khi muốn thay **hai bean khác nhau cùng type**:

```java
@SpringBootTest
@MockitoBean(types = ShippingGateway.class, name = "economyGateway")
@MockitoBean(types = ShippingGateway.class, name = "expressGateway")
class BothGatewaysMockedTest {
    // @Autowired @Qualifier("...") ShippingGateway để stub từng bean.
}
```

Đây là **minh họa** chứ không phải phần phải thêm vào project đã có tests. Mỗi annotation có target name riêng; đừng dùng một annotation `types={ShippingGateway.class,OtherClass.class}, name="expressGateway"` vì **khi có name, types phải chỉ một type**.

### 10.6. Context caching và nhiều bộ mock khác nhau

Spring context cache có xét bean override customizers; nếu mỗi lớp test chọn bean khác nhau hoặc cấu hình qualifier/name khác nhau, Spring có thể tạo context riêng. Điều này đúng vì graph của các test thực sự khác nhau. Chọn unit test thuần Java cho logic thuần, web slice khi chỉ kiểm HTTP, full context cho wiring. Đừng lạm dụng `@DirtiesContext` hoặc thay đổi tên field fallback chỉ vì thói quen vì có thể làm suite chậm.

### 10.7. AOP, transaction và security

Bean được `@MockitoBean` thay bằng Mockito mock sẽ không còn logic thật và các behavior của advice/proxy bean gốc tại vị trí đó. Một test `@SpringBootTest` mock service mang `@Transactional` **không** chứng minh transaction của service thật. Giữ bean có behavior cần kiểm là bean thật, mock outbound gateway/repository nếu ranh giới test cho phép, hoặc dùng integration test với hạ tầng đủ thật.

`@MockitoSpyBean` khác: nó wrap bean có sẵn bằng spy, có thể cần chú ý Spring AOP proxy và target. Khi spy có method thực gọi database/network, hãy kiểm soát side effect; stub `doReturn(...).when(spy).method()` để tránh gọi thật tại thời điểm tạo stub.

### 10.8. @Mock và @MockitoBean

`@Mock` thuộc Mockito tạo object Java trong test; nó **không** đăng ký trong Spring context. `@MockitoBean` thuộc Spring Framework TestContext yêu cầu Spring thay/đăng ký bean phù hợp. Nếu SUT do test tạo với `new`, dùng `@Mock`/`Mockito.mock`. Nếu SUT do Spring `@Autowired`, dùng bean override khi cần điều chỉnh collaborator của SUT.

Không đặt cả `@InjectMocks` và `@Autowired` trên cùng SUT rồi nghĩ Mockito sẽ thay dependency trong context; đó là hai cơ chế quản lý khác nhau.

## 11. Quyết định theo loại bài test Spring Boot

| Rủi ro cần kiểm | Công cụ và target | Lưu ý khi có nhiều ứng viên |
| --- | --- | --- |
| Logic nội bộ `QuoteService` | Unit test; `new QuoteService(mock)` và Mockito `@Mock` | Không cần Spring bean selection |
| Wiring thật của `QuoteService` với express | `@SpringBootTest`, không mock gateway, assert 130 | `@Qualifier` trên constructor bảo đảm chọn express |
| Service logic với phí giả | `@SpringBootTest` + `@MockitoBean(name="expressGateway")` | Giữ service thật; xác nhận economy không bị thay |
| HTTP mapping của controller | `@WebMvcTest` + `@MockitoBean` service collaborator | Slice có thể không chứa service thật; REPLACE_OR_CREATE hợp lý |
| Hành vi của riêng express adapter | Unit/adapter test với ExpressGateway thật | Không mock chính adapter đang kiểm |
| Quan sát method express thật | `@MockitoSpyBean(name="expressGateway")` | Cần bean target duy nhất, xem side effects |
| Bean có `@Transactional`/`@PreAuthorize` | Integration với bean service thật | Mock ở outbound boundary; đừng thay chính bean mang advice |
| Persistence repository/query | `@DataJpaTest` và database phù hợp | Không mock repository đang kiểm |
| Nhiều implementations theo profile | Context test profile phù hợp + target name/qualifier đúng | Không assume bean có mặt dưới mọi profile |
| Multiple context levels | `@MockitoBean(contextName="...")` khi có hierarchy | Đúng context level và canonical name |

Nếu test không có ý định kiểm Spring DI, hãy ưu tiên unit test nhanh và rõ ràng. Khi đã dùng Spring context, xác định **một bean cụ thể** cần thay, rồi assert kết quả đi xuyên qua bean thật đang dùng nó.

## 12. Debug theo thông báo lỗi

| Dấu hiệu | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| `No qualifying bean of type ...` | Không có bean cho injection point trong profile/slice hiện tại | Kiểm scan, profile, `@Bean`, `@MockitoBean` nếu collaborator của slice |
| `NoUniqueBeanDefinitionException` | Nhiều candidates cùng type, injection/override thiếu selector | Thêm `@Qualifier`, bean name cụ thể, hoặc thiết kế `@Primary` theo wiring |
| `Failed to load ApplicationContext` khi test có `@MockitoBean ShippingGateway gateway;` | Override mơ hồ hoặc target không tồn tại/enforce | Đọc `Caused by` liên quan bean override |
| `when(mock.fee(...))` không tác động total | Mock không phải bean mà SUT dùng | Kiểm constructor qualifier, target name, object graph |
| Test pass nhưng mock bean mới được tạo | Viết sai `name` và dùng REPLACE_OR_CREATE | Dùng `enforceOverride=true` để phát hiện lỗi |
| Spy fail vì không tìm thấy bean | `@MockitoSpyBean` cần bean tồn tại và duy nhất | Chỉ định name/qualifier hoặc sửa profile |
| `@MockitoBean` chọn sai bean khi đổi tên field | Fallback field name đã đổi | Dùng `name`/`@Qualifier` tường minh |
| Bean có `@Primary` nhưng test thay sai target | Nhầm production autowiring với override selection | Kiểm bean name/qualifier thực sự dùng |
| Bean proxy không trùng mock reference | AOP/scoped proxy hoặc spy wrapping | Xem Spring proxy/target và behavior thay vì chỉ identity |
| Context load nhiều lần, test chậm | Khác cấu hình overrides, qualifier, field name | Thống nhất naming/config theo test boundary |
| Test Boot cũ không tìm thấy `MockitoBean` | Spring Framework chưa có API 6.2 | Dùng API tương ứng version hoặc nâng Boot/Framework |

### 12.1. Theo nguyên nhân đầu tiên

`Failed to load ApplicationContext` thường chỉ là wrapper. Hãy tìm `Caused by` đầu tiên có thông tin cụ thể, ví dụ candidate ambiguity, không tìm thấy bean name hoặc không thể override non-singleton. Với Spring TestContext failure threshold (Spring Framework 6.1+), cùng cache key fail một lần có thể làm những lần sau báo “skipping repeated attempt”; hãy tìm **lần fail đầu tiên**, không cố sửa threshold.

### 12.2. Kiểm type, name và qualifier đang tồn tại

Trong test có context, dùng `ApplicationContext#getBeansOfType(...)` để xem map bean name → instance phù hợp. Nếu chỉ có tên cần hỏi, `containsBean("...")` kiểm tồn tại. Với mock đã target, `Mockito.mockingDetails(bean).isMock()` và `verify(mock).fee(...)` có thể giúp xác minh trong project đơn giản. Với proxy/FactoryBean, cần hiểu rằng object trả về có thể là proxy/product; tránh kết luận chỉ từ identity.

### 12.3. Không sửa bằng cách tắt các ranh giới bảo vệ

Khi mock không hoạt động, đừng:
- Chuyển tất cả test sang full `@SpringBootTest` và mock mọi dependency.
- Cho phép bean overriding toàn cục hoặc bỏ qualifier khỏi code production.
- Xóa `@Primary` hoặc annotation bảo mật mà chưa hiểu service cần bean nào.
- Thêm `lenient()` khi stub không được gọi thay vì kiểm mock placement.
- Chỉ assert stub trực tiếp trong test rồi tuyên bố service sử dụng mock.

Cách sửa tốt là chọn đúng bean và kiểm **SUT thật** với behavior quan sát được.

## 13. Câu hỏi luyện tập và đáp án gợi ý

1. Có hai bean `economyGateway` và `expressGateway` cùng interface. `@MockitoBean ShippingGateway gateway;` có đủ không? **Không**; type không duy nhất, field name `gateway` cũng không chọn được target. Cần name hoặc qualifier.
2. Nếu viết `@MockitoBean ShippingGateway expressGateway;` thì yếu tố nào được dùng? **Tên field fallback** khi không có `@Qualifier`.
3. Khai báo `@MockitoBean(name="economyGateway")` nhưng `QuoteService` dùng express. Kết quả phí sau khi stub economy = 55 là gì? **30**, vì QuoteService vẫn dùng express thật; total = 130 với subtotal 100.
4. Viết nhầm `@MockitoBean(name="expresGateway")`. Có chắc context fail không? **Không**, mặc định `REPLACE_OR_CREATE` có thể tạo bean mock mới. Dùng `enforceOverride=true` khi muốn bắt buộc thay bean tồn tại.
5. Qualifier `"priority"` trên bean `expressGateway` có đồng nghĩa bean tên priority không? **Không**. `@Qualifier("priority")` là tiêu chí lọc; `name="priority"` chọn tên bean.
6. Vì sao `@MockitoSpyBean(name="expressGateway")` khác `@MockitoBean(name="expressGateway")`? Spy wrap bean có sẵn và mặc định chạy method thật; mock thay bean và mặc định không chạy implementation.
7. Vì sao `@MockitoBean(name="expressGateway")` trong test full context làm mất khả năng kiểm code ExpressGateway thật? Vì method gateway bị mock; cần một test riêng giữ ExpressGateway thật.
8. Với `@MockitoBean(types={ShippingGateway.class}, name="expressGateway")` ở class-level, cần gì khác so với field-level? Phải chỉ định `types`; khi có `name` thì type list chỉ chứa một type.
9. Hai lớp test thay cùng bean bằng field-name fallback khác nhau. Tác động gì? Có thể thay đổi context cache key; đặt tên consistent hoặc explicit name.
10. Với hai bean cùng @Qualifier("fast"), việc dùng `@MockitoBean @Qualifier("fast")` có đủ không? Không chắc; nếu vẫn nhiều candidates, phải chọn bean name/candidate duy nhất.

## 14. Checklist ứng dụng trong code review

- [ ] Tôi đã xác định bean type và danh sách bean **thực sự được đăng ký** trong context test?
- [ ] Tôi biết name của bean target và nó khác gì với tên biến field Java?
- [ ] Có nhiều candidates cùng type? Đã dùng `name` hoặc `@Qualifier` một cách tường minh?
- [ ] Qualifier value là bean name, alias hay qualifier metadata? Có đang nhầm chúng?
- [ ] SUT được Spring inject bean nào qua constructor, `@Primary` hoặc qualifier?
- [ ] Override target có phải bean **SUT thật đang gọi** không?
- [ ] Nếu bean bắt buộc có sẵn, đã cân nhắc `enforceOverride=true`?
- [ ] Test có kiểm ít nhất một bean không bị mock nhầm hoặc kiểm đúng bean identity khi phù hợp?
- [ ] Nếu `@MockitoSpyBean`, target có tồn tại duy nhất và singleton không?
- [ ] Nếu annotation đặt trên class, `types` và `name` có hợp lệ (name đi với một type)?
- [ ] Nếu chỉ muốn kiểm logic thuần, đã cân nhắc Mockito unit test và constructor injection?
- [ ] Nếu kiểm service transaction/security/cache, có giữ service thật thay vì mock service?
- [ ] Khi test fail, đã tìm root cause của Spring TestContext thay vì chỉ sửa assertion?
- [ ] Khi refactor tên field fallback, đã kiểm lại bean target và context caching?
- [ ] Đã chạy test ở đúng Spring Boot/Framework version và kiểm các test cả khi đứng riêng và khi chạy suite?

**Điểm cần ghi nhớ:** Chọn bean theo **type** khi duy nhất; dùng **bean name tường minh** hoặc **`@Qualifier`** khi có nhiều ứng viên; xem field name chỉ là fallback; dùng `enforceOverride=true` để bắt lỗi thiếu bean khi mục tiêu là thay bean hiện hữu. Sau đó kiểm đường gọi từ **SUT thật** đến đúng mock trong Spring context, thay vì chỉ xác nhận mock riêng được stub.

## 15. Tài liệu tham khảo chính thức

- Spring Framework 6.2 — `@MockitoBean` và `@MockitoSpyBean`, lựa chọn bằng type/name/qualifier: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Framework — Bean Overriding in Tests: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/bean-overriding.html
- Spring Framework — Fine-tuning Autowiring with Qualifiers: https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html
- Spring Framework — `@Primary` and `@Fallback`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-primary.html
- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5.16 release (phiên bản sử dụng cho ví dụ): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- JUnit 5 User Guide: https://docs.junit.org/5.11.4/user-guide/
