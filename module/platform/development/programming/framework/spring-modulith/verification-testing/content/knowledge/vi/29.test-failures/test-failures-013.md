# Ghi lại điều kiện tái hiện tối thiểu

Trong chương **Test failure** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**, một báo cáo lỗi chỉ ghi “`Scenario` timeout” hoặc “`ApplicationContext` không khởi động” chưa đủ để người khác sửa và ngăn hồi quy. Cần lưu **điều kiện nhỏ nhất khiến cùng một failure xuất hiện một cách kiểm chứng được**: mã nguồn/phiên bản, test nằm ở module nào, bootstrap mode, stimulus, dữ liệu, transaction, cấu hình và bằng chứng *expected/actual*.

Đây không phải yêu cầu tạo một bản sao thu nhỏ của toàn bộ ứng dụng production. Mục tiêu là **giữ nguyên cơ chế gây lỗi, bỏ những điều kiện không liên quan**, và tạo được phép đối chứng: điều kiện gây lỗi thì test đỏ; chỉ thay yếu tố nghi vấn thì test có kết quả khác đúng như dự đoán.

Kết thúc bài, người học có thể viết một *minimal reproducible example* (MRE) cho lỗi Spring Modulith, xây dựng Java/JUnit test có thể tái hiện và một test đối chứng, ghi thông tin môi trường có chọn lọc, chứng minh tính lặp lại của lỗi, bảo vệ module boundary bằng `ApplicationModules.verify()` và đưa test hồi quy vào CI.

## 1. Hợp đồng của một bản tái hiện tối thiểu

Một bản tái hiện tối thiểu phải trả lời **sáu câu hỏi**, không chỉ mô tả triệu chứng:

| Câu hỏi | Nội dung phải ghi | Ví dụ Spring Modulith |
| --- | --- | --- |
| **Đang kiểm chứng điều gì?** | Hợp đồng nghiệp vụ hoặc quy tắc kiến trúc | “Khi `OrderSubmitted` được phát và `billing` listener hoạt động, một `InvoiceCreated` cùng `orderId` được publish” |
| **Stimulus nào gây lỗi?** | Method, input, transaction, số lần gọi, thứ tự | `orders.submit(orderId)` một lần |
| **Test được khởi động thế nào?** | Test class/package, `@ApplicationModuleTest` mode, profiles, property | `com.example.shop.orders`, `STANDALONE` |
| **Môi trường và state nào thiết yếu?** | JDK/Boot/Modulith, DB nếu dùng, fixture, clock, executor | Không DB; không async; event có UUID |
| **Expected vs actual là gì?** | Số/kiểu event, exception, trạng thái, assertion fail | Expected `InvoiceCreated`; actual không thấy trước timeout |
| **Làm sao tái hiện và đối chứng?** | Một lệnh test cụ thể, điều kiện pass/fail, thay đổi duy nhất | Đặt test consumer ở `billing` sẽ thấy listener |

**“Tối thiểu” không có nghĩa “ít dòng nhất”.** Nếu bỏ annotation `@ApplicationModuleTest` hoặc chuyển test sang package khác làm biến mất nguyên nhân gốc, bản rút gọn đã **đổi bài toán**. Ngược lại, nếu lỗi vẫn xuất hiện khi bỏ controller, HTTP, database, broker và giao diện thì những phần ấy không thuộc điều kiện tối thiểu.

### 1.1. Đặt tên cho failure fingerprint

*Fingerprint* là tổ hợp dấu hiệu giúp biết ta đang tái hiện **cùng loại lỗi** chứ không phải tạo một lỗi khác:

```text
Fingerprint: SCENARIO_OUTCOME_NOT_OBSERVED
Test module: orders
Bootstrap: @ApplicationModuleTest / STANDALONE
Source: OrderSubmitted(orderId)
Expected outcome: InvoiceCreated(orderId)
Source publication: observed
Consumer listener in context: absent
Failure phase: Scenario waiting / timeout
```

Đây là **mẫu dữ kiện giả định** cho ví dụ bài học, không phải log từ một lần chạy thực tế. Mỗi mục cần được xác minh khi áp dụng trong repository của bạn.

Nếu khi rút gọn test lại chuyển sang `Failed to load ApplicationContext` do thiếu `DataSource`, fingerprint **đã đổi**. Không được báo “đã tái hiện cùng lỗi” chỉ vì cả hai đều làm CI đỏ.

### 1.2. Có thể ít thông tin nhưng phải đủ để thử lại

Một bản ghi kém:

```text
Build đỏ trên CI. Test chờ event, lâu quá. Local thỉnh thoảng xanh.
```

Một bản ghi có giá trị:

```text
Test: com.example.shop.orders.OrdersModuleReproTests#consumerOutcomeTimesOut
Bootstrap mode: STANDALONE
Stimulus: orders.submit(UUID mới)
Source event: đúng 1 OrderSubmitted theo orderId
Expected: InvoiceCreated với cùng orderId
Actual: Scenario không quan sát được event kết quả trong thời hạn
Control: test chuyển sang billing module, listener được nạp, outcome xuất hiện
Root-cause hypothesis: consumer nằm ngoài orders test context
```

Thông tin về build tool và phiên bản cụ thể được bổ sung ở mục 2. Không ghi “test đỏ” thay cho kết quả quan sát được.

## 2. Đóng băng môi trường, nguồn mã và bằng chứng trước khi sửa

Khi một lỗi vừa xảy ra, **đừng sửa ngay rồi mới cố nhớ cấu hình lúc lỗi**. Trước tiên lưu một mốc có thể quay lại:

- **Revision:** commit hash và branch/tag đã chạy; có sửa đổi local chưa commit không?
- **Toolchain:** JDK vendor/version, Spring Boot, Spring Modulith, JUnit/Jupiter, wrapper Maven/Gradle; không chỉ ghi “Java 17+”.
- **Lệnh chạy:** class/method filter và tùy chọn thực sự đã dùng, thư mục project, profiles, system properties, environment variables **đã chọn lọc**.
- **Context:** package test, annotation/bootstrap mode, test configuration/import, bean có mặt/vắng mặt, custom module detection nếu có.
- **Data:** input, correlation ID, trạng thái fixture và trạng thái DB đã commit hay chưa.
- **Thời gian/đồng thời:** số lần chạy, CI runner, async executor, timeout, timezone/clock nếu có ảnh hưởng.
- **Bằng chứng:** exception gốc, assertion expected/actual, stack trace đoạn liên quan, log theo cùng ID.

### 2.1. Mẫu manifest không bịa số phiên bản

Ghi dữ liệu theo **giá trị quan sát thực**; dưới đây là mẫu để điền, **không phải kết quả đã thu thập**:

```yaml
reproduction:
  id: "ORDERS-BILLING-SCENARIO-001"
  revision: "<git-commit-sha>"
  dirty_worktree: "<true|false|unknown>"
  jdk: "<vendor-and-version>"
  spring_boot: "<version-from-build>"
  spring_modulith: "<version-from-build>"
  junit: "<version>"
  build_tool: "<maven-or-gradle-wrapper-version>"
  test: "com.example.shop.orders.OrdersModuleReproTests"
  method: "consumerOutcomeTimesOut"
  module_under_test: "orders"
  bootstrap: "STANDALONE"
  active_profiles: []
  test_properties: {}
  datasource: "not-used-in-this-MRE"
  transaction: "none-required-in-this-MRE"
  async: "none-required-in-this-MRE"
  input: "one OrderSubmitted with a generated orderId"
  expected: "one InvoiceCreated with same orderId"
  actual: "<observed-error-or-timeout>"
  repetitions: "<fails>/<total-runs>"
  evidence: "<minimal-stacktrace-and-observed-events>"
```

Manifest này là **nội dung hướng dẫn trong bài Markdown**; người học có thể lưu cùng PR/issue dưới định dạng nhóm sử dụng, nhưng không cần thêm file cho bài học hiện tại.

Đừng copy toàn bộ `application-prod.yml`, JWT, credential, URL DB nội bộ, thông tin khách hàng hoặc email. Thay bằng **tên property, trạng thái bật/tắt và giá trị đã ẩn**. Điều kiện tái hiện phải hữu ích mà không phát tán bí mật.

### 2.2. Lệnh ghi nhận công cụ nên chạy tại repository thật

Với Maven Wrapper trên môi trường Unix:

```bash
java -version
./mvnw -version
./mvnw -Dtest=OrdersModuleReproTests test
```

Với Gradle Wrapper:

```bash
java -version
./gradlew --version
./gradlew test --tests "com.example.shop.orders.OrdersModuleReproTests"
```

Trên PowerShell/Windows, tùy repository có thể dùng `.\mvnw.cmd` hoặc `.\gradlew.bat` tương ứng. **Đây là lệnh minh họa cho môi trường thực hành; chưa được chạy khi soạn bài này.** Không mặc định cả Maven lẫn Gradle đều tồn tại. Chỉ lưu **một lệnh thực sự tái hiện** từ build tool đã chọn.

Nếu test fail khi chạy cả suite nhưng pass khi lọc một class, ghi **cả hai lệnh** và thứ tự thực thi nếu nó là điều kiện của lỗi. Không tuyên bố test “không tái hiện” chỉ vì đã thay đổi cách khởi động.

## 3. Rút gọn từ failure lớn tới phép thử nhỏ nhất mà không đổi cơ chế

Quy trình gợi ý:

1. **Giữ một failure cố định:** ví dụ `Scenario` không thấy `InvoiceCreated`; chưa chuyển sang lỗi context khác.
2. **Loại bỏ UI/HTTP:** nếu service có thể được gọi trực tiếp và vẫn fail, không cần controller trong MRE.
3. **Loại bỏ database:** nếu listener chỉ publish event và lỗi vẫn xảy ra, không cần JPA, migration hay Testcontainers.
4. **Giữ cấu trúc module thật sự quan trọng:** package `orders` và `billing`, vị trí test, bootstrap mode, public event type.
5. **Giữ đúng một stimulus:** một `orderId`, một `OrderSubmitted`; không trộn thêm nhiều event.
6. **Giữ một assertion có thể phân biệt:** nguồn publish có, outcome không có.
7. **Thêm phép đối chứng:** test ở `billing` nhìn thấy listener và outcome, giữ nguyên event contract.
8. **Ghi thay đổi đã loại bỏ:** để người khác hiểu vì sao MRE không có DB hoặc broker mà vẫn giữ cùng failure.

| Thành phần của ứng dụng lớn | Giữ trong MRE? | Vì sao |
| --- | --- | --- |
| `OrderSubmitted` public event | Có | Stimulus nguồn |
| `InvoiceCreated` result event | Có | Outcome bị chờ |
| `billing` listener | Có | Consumer thiếu trong test context |
| Package/module ownership | Có | Quyết định `@ApplicationModuleTest` bootstrap scope |
| `@ApplicationModuleTest` ở `orders` | Có | Điều kiện làm consumer vắng mặt |
| Controller REST | Không | Không ảnh hưởng event registration |
| Database/payment gateway | Không | Listener mẫu không dùng |
| Retry/async executor | Không | Failure vẫn tái hiện với listener đồng bộ |
| Transaction | Không | Listener mẫu dùng `@EventListener`, không cần commit |

**Quy tắc dừng rút gọn:** nếu bỏ một thành phần khiến failure biến mất hoặc đổi sang lỗi khác, thành phần đó có khả năng là điều kiện thiết yếu. Nếu bỏ mà failure giữ nguyên, tiếp tục thử loại bỏ những chi tiết không cần cho chẩn đoán.

### 3.1. Có cả đối chứng âm và dương

Một test không nhận `InvoiceCreated` trong orders chưa đủ để biết **listener implementation có lỗi không**. Đối chứng:

- **Âm:** trong `orders` `STANDALONE`, source event có nhưng consumer không được bootstrap.
- **Dương:** trong `billing` `STANDALONE`, listener thực có trong context và phát `InvoiceCreated` với cùng input.

Đối chứng không phải để “chứng minh production hoàn toàn đúng”; nó chỉ cô lập biến **vị trí/module bootstrap của test**.

## 4. MRE Java: hai module, hai event, một listener

Giả sử ứng dụng Spring Boot ở package gốc `com.example.shop`, dùng Spring Modulith dependency/test starter và JUnit/AssertJ do nền tảng test quản lý. Cấu trúc tối thiểu:

```text
src/main/java/com/example/shop/
├── ShopApplication.java
├── orders/
│   ├── OrderSubmitted.java
│   └── Orders.java
└── billing/
    ├── InvoiceCreated.java
    └── internal/
        └── InvoiceListener.java

src/test/java/com/example/shop/
├── orders/
│   └── OrdersModuleReproTests.java
└── billing/
    └── BillingModuleControlTests.java
```

### 4.1. Application root

```java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Vị trí root quan trọng: các module mặc định là những subpackage trực tiếp dưới `com.example.shop`, nên `orders` và `billing` được nhận diện là hai application modules riêng. Nếu dự án dùng detection strategy tùy chỉnh thì ghi rõ trong manifest; không mặc định mọi cấu trúc package đều có cùng ý nghĩa.

### 4.2. Event và publisher của orders

Tệp `orders/OrderSubmitted.java`:

```java
package com.example.shop.orders;

import java.util.UUID;

public record OrderSubmitted(UUID orderId) {
}
```

Tệp `orders/Orders.java`:

```java
package com.example.shop.orders;

import java.util.Objects;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class Orders {

    private final ApplicationEventPublisher publisher;

    public Orders(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void submit(UUID orderId) {
        Objects.requireNonNull(orderId, "orderId");
        publisher.publishEvent(new OrderSubmitted(orderId));
    }
}
```

Publisher này **không import lớp nội bộ của `billing`**. Ta có thể kiểm chứng nó publish đúng một event nguồn ngay cả khi không có listener consumer trong context.

### 4.3. Event kết quả và listener của billing

Tệp `billing/InvoiceCreated.java`:

```java
package com.example.shop.billing;

import java.util.UUID;

public record InvoiceCreated(UUID orderId) {
}
```

Tệp `billing/internal/InvoiceListener.java`:

```java
package com.example.shop.billing.internal;

import com.example.shop.billing.InvoiceCreated;
import com.example.shop.orders.OrderSubmitted;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceListener {

    private final ApplicationEventPublisher publisher;

    public InvoiceListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    public void on(OrderSubmitted event) {
        publisher.publishEvent(
                new InvoiceCreated(event.orderId()));
    }
}
```

Listener sử dụng **`@EventListener` đồng bộ**; không có `@Async`, không có `@TransactionalEventListener`, không có DB. Đây là quyết định có chủ đích để tối giản: nếu test ở `orders` vẫn không nhận `InvoiceCreated`, không thể quy nguyên nhân cho thread pool, isolation hay thiếu commit trong **MRE này**.

Mã compile-time của consumer phụ thuộc public event ở producer:

```text
Dependency tĩnh: billing -> orders
Luồng event:     orders -> billing
```

Chiều phụ thuộc tĩnh khác chiều giao event. Do đó, mở `DIRECT_DEPENDENCIES` từ `orders` **không mặc định tải module `billing`**.

## 5. Tạo test tái hiện đúng failure và ghi bằng chứng trước timeout

Tệp `src/test/java/com/example/shop/orders/OrdersModuleReproTests.java`:

```java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.billing.InvoiceCreated;
import java.util.UUID;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class OrdersModuleReproTests {

    @Autowired
    Orders orders;

    @Autowired
    ApplicationContext context;

    @Test
    void sourceEventExistsButBillingBeanIsOutsideScope(
            PublishedEvents events) {

        // Trong demo, InvoiceListener mặc định có bean name
        // "invoiceListener", nhưng orders STANDALONE không tải billing.
        assertThat(context.containsBean("invoiceListener"))
                .isFalse();

        UUID orderId = UUID.randomUUID();
        orders.submit(orderId);

        assertThat(events.ofType(OrderSubmitted.class)
                .matching(event ->
                        orderId.equals(event.orderId())))
                .hasSize(1);
    }

    @Disabled("Mở test này có chủ đích để quan sát timeout MRE")
    @Test
    void consumerOutcomeTimesOut(Scenario scenario) {
        UUID orderId = UUID.randomUUID();

        scenario.stimulate(() ->
                        orders.submit(orderId))
                .andWaitForEventOfType(InvoiceCreated.class)
                .matching(event ->
                        orderId.equals(event.orderId()))
                .toArriveAndVerify(event ->
                        assertThat(event.orderId())
                                .isEqualTo(orderId));
    }
}
```

**Cách sử dụng:** test đầu nên pass trong `orders` `STANDALONE` vì source event vẫn được publish, còn consumer bean không thuộc scope. Test thứ hai **cố ý bị `@Disabled`** để không làm pipeline bình thường đỏ; khi cần tái hiện timeout, tạm bỏ annotation `@Disabled` và chạy đúng method. Sau khi thu bằng chứng, khôi phục annotation hoặc bỏ test cố ý thất bại khỏi suite chính.

Trước khi kết luận, ghi rõ hai điều **đã kiểm tra**:

1. Context của `orders` không có bean `invoiceListener` theo bean name mặc định của class minh họa. Với dự án đặt tên bean tùy chỉnh, phải chọn phép introspection phù hợp.
2. `PublishedEvents` ghi nhận một `OrderSubmitted` đúng `orderId` trong test nguồn.

Đừng thay bằng:

```java
assertThat(events.ofType(InvoiceCreated.class)).isEmpty();
```

rồi khẳng định “lỗi chắc chắn do module scope” nếu chưa kiểm tra listener có được tạo không. Không có outcome cũng có thể do event type, filter, exception hoặc transaction trong một hệ thống khác.

### 5.1. Báo cáo expected/actual chính xác

```text
Test: OrdersModuleReproTests#consumerOutcomeTimesOut
Module under test: orders
Bootstrap mode: STANDALONE (default)
Stimulus: orders.submit(orderId)
Expected: InvoiceCreated(orderId) observed by Scenario
Observed in companion test:
  source event OrderSubmitted(orderId): exactly 1
  billing listener bean: absent
Expected failure in enabled demo test:
  Scenario waits for InvoiceCreated until timeout
```

Các dòng trên mô tả **dự kiến của ví dụ**, không phải output từ build đã được chạy. Trong báo cáo bug thật, thay “Expected failure” bằng exception và failure excerpt thu được từ lần chạy thực; nêu timeout thực tế theo cấu hình của dự án thay vì đoán một giá trị mặc định.

### 5.2. Vì sao test class và package là dữ liệu bắt buộc?

Nếu chuyển chính test chờ event sang `com.example.shop.billing`, `@ApplicationModuleTest` sẽ bootstrap **billing**; listener trở thành bean thuộc module đang test. Đây không đơn thuần là đổi tên file: đó là thay đổi **phạm vi application module**.

Muốn có MRE chính xác, phải lưu:

- `package` statement của test, không chỉ folder tên “tests”.
- Annotation và `BootstrapMode`, kể cả trường hợp dùng default `STANDALONE`.
- Kiểu source event, result event và nơi định nghĩa chúng.
- Listener thuộc module nào và dùng cơ chế đăng ký nào.
- Predicate `matching` theo khóa tương quan.

Nếu thiếu một trong các dữ kiện ấy, người nhận báo cáo có thể chạy test trong một context **khác** rồi thấy kết quả khác, dù cả hai đang nhìn cùng một source file nghiệp vụ.

## 6. Đối chứng dương trong consumer module: giữ hợp đồng, đổi scope

Tệp `src/test/java/com/example/shop/billing/BillingModuleControlTests.java`:

```java
package com.example.shop.billing;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.billing.internal.InvoiceListener;
import com.example.shop.orders.OrderSubmitted;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class BillingModuleControlTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    ApplicationEventPublisher publisher;

    @Test
    void listenerIsRegistered() {
        assertThat(context.getBeanNamesForType(
                InvoiceListener.class))
                .hasSize(1);
    }

    @Test
    void sameSourceEventProducesExpectedOutcome(
            Scenario scenario,
            PublishedEvents events) {

        UUID orderId = UUID.randomUUID();

        scenario.stimulate(() ->
                        publisher.publishEvent(
                                new OrderSubmitted(orderId)))
                .andWaitForEventOfType(InvoiceCreated.class)
                .matching(event ->
                        orderId.equals(event.orderId()))
                .toArriveAndVerify(event ->
                        assertThat(event.orderId())
                                .isEqualTo(orderId));

        assertThat(events.ofType(OrderSubmitted.class)
                .matching(event ->
                        orderId.equals(event.orderId())))
                .hasSize(1);
    }
}
```

**Phép đối chứng này có giá trị ở chỗ:**

- Vẫn dùng public event `OrderSubmitted` và `orderId` để kích hoạt cùng loại công việc.
- Không thay đổi production implementation của `InvoiceListener`.
- Test ở **billing** có listener thực trong scope, quan sát `InvoiceCreated`.
- Phân biệt “listener implementation không xử lý được `OrderSubmitted`” với “listener không nằm trong context của bài test `orders`”.

Kết luận **được phép** sau khi thực sự chạy các test:

> Trong mô hình hai module này, `orders`-only bootstrap không đưa consumer billing vào context; module test trong `billing` có listener và quan sát được outcome. Vì vậy, việc chờ outcome billing từ `orders` `STANDALONE` là sai phạm vi kiểm thử.

Kết luận **không được phép**:

> Toàn bộ production integration chắc chắn đúng, không còn khả năng lỗi DB, retry hoặc deployment profile.

Control này không khởi động producer service thật `Orders` trong billing test; nó gửi **public event làm stimulus**. Test toàn tuyến từ service thật tới listener thật, database và transaction (nếu có) vẫn là trách nhiệm của integration gate khác.

### 6.1. Khi đối chứng không đạt, phải cập nhật giả thuyết

Nếu `BillingModuleControlTests#listenerIsRegistered` cũng không thấy bean, kiểm tra:

- `@Component`/`@Bean` có đăng ký listener không?
- Class có nằm đúng package module `billing` không?
- `@Profile`/`@ConditionalOnProperty` có loại bean trong test không?
- Có `Failed to load ApplicationContext` vì dependency của listener thiếu không?
- Test build có cùng source revision/versions với lần lỗi gốc không?

**Không ép** lỗi mới vào giả thuyết cũ “chỉ sai test scope”. Một MRE tốt phải có khả năng **bác bỏ** giả thuyết nếu control không diễn ra như dự đoán.

## 7. Ghi điều kiện dữ liệu, transaction và cơ sở dữ liệu khi chúng thực sự cần

Ví dụ ``orders → billing` ở trên không cần database hoặc transaction. Nhưng nếu failure gốc liên quan `@TransactionalEventListener(AFTER_COMMIT)`, việc bỏ transaction sẽ **xóa mất điều kiện gây lỗi**. Khi ấy bản tái hiện tối thiểu **phải giữ** ranh giới commit/rollback.

### 7.1. Danh sách dữ kiện transaction tối thiểu

| Dữ kiện | Cách ghi | Vì sao quan trọng |
| --- | --- | --- |
| Event được publish trong transaction nào? | Manager và ranh giới method/template | `AFTER_COMMIT` chỉ kích hoạt sau commit thành công |
| Method test có `@Transactional` không? | Có/không; rollback mặc định | Test-managed transaction có thể chưa kết thúc khi chờ |
| `TransactionTemplate` có sở hữu transaction không? | Propagation và có outer transaction không | `REQUIRED` có thể chỉ tham gia transaction ngoài |
| Transaction có commit thật không? | Kết quả được xác minh, không chỉ “active” | Transaction active không chứng minh commit |
| Listener có transaction riêng không? | Propagation/transaction manager của listener | DB side effect có thể chưa bền vững |
| Reader của test dùng transaction nào? | Connection, isolation, cache nếu liên quan | Reader khác không thấy row chưa commit |

### 7.2. Mẫu tối thiểu ghi rõ commit trước bước chờ

**Biến thể thay thế**: khi listener dùng `@TransactionalEventListener(AFTER_COMMIT)` và có `PlatformTransactionManager` thực:

```java
TransactionTemplate tx =
        new TransactionTemplate(transactionManager);

scenario.stimulate(() ->
                tx.executeWithoutResult(status ->
                        publisher.publishEvent(
                                new OrderSubmitted(orderId))))
        .andWaitForEventOfType(InvoiceCreated.class)
        .matching(event ->
                orderId.equals(event.orderId()))
        .toArriveAndVerify(event ->
                assertThat(event.orderId())
                        .isEqualTo(orderId));
```

Đây là **thân integration test minh họa**, không phải code dùng trực tiếp với listener `@EventListener` của mục 4. Để dùng với `AFTER_COMMIT`, phải thay listener theo hợp đồng tương ứng, cung cấp transaction manager và không đặt một test transaction bao ngoài chưa commit. Nếu `TransactionTemplate` mặc định `REQUIRED` tham gia transaction của `@Transactional` test, nó có thể trả về **mà chưa commit transaction ngoài**, nên nguyên nhân timeout vẫn còn.

Một đối chứng âm cho transaction:

```java
tx.executeWithoutResult(status -> {
    publisher.publishEvent(new OrderSubmitted(orderId));
    status.setRollbackOnly();
});
```

Với listener `AFTER_COMMIT`, rollback không kích hoạt callback pha ấy. Đây là **đoạn mô tả trường hợp kiểm thử**, không tự chứng minh không có outcome nếu test chưa kiểm soát những nguồn event khác; dùng ID riêng và trạng thái quan sát được.

### 7.3. Với JPA, seed chưa commit không phải fixture nhìn thấy ở mọi thread

MRE cho `JpaObjectRetrievalFailureException`, FK lỗi hoặc “listener không thấy order” cần ghi:

- Schema/migration và database dialect: H2, PostgreSQL hoặc hệ thống thực sự được dùng.
- Entity/relationship tối thiểu, parent row và child row, có cascade hay không.
- `save`, `flush`, `clear`, `commit` đã xảy ra ở bước nào.
- `@Sql` script/fixture tạo dữ liệu gì, ID nào, thứ tự insert nào.
- Listener dùng thread/transaction khác không; có thể nhìn thấy dữ liệu seed không.

Nếu fixture trong một test-managed transaction chưa commit mà listener async cần query DB qua connection khác, listener có thể không thấy row. Thay database bằng `ConcurrentHashMap` sẽ làm lỗi biến mất **vì đã thay mất điều kiện visibility**, không chứng minh JPA production đúng.

**Không bịa production SQL hay migration** trong MRE nếu chưa có bằng chứng. Chỉ giữ một schema/fixture nhỏ phản ánh đúng constraint dẫn đến failure, và nêu rõ khi database giả lập có khác biệt dialect.

## 8. Điều kiện bất đồng bộ, flaky và thứ tự chạy phải được tái hiện có kiểm soát

Đối với lỗi chỉ xuất hiện trên CI hoặc khi chạy song song, “chạy lại vài lần thấy đỏ” chưa phải tái hiện ổn định. Cần ghi rõ **điều kiện lịch thực thi**, số lần thử và cách biết mọi worker đã hoàn tất.

### 8.1. Trước tiên phân biệt ba loại failure

| Mẫu lỗi | Điều cần giữ trong MRE | Điều không nên làm |
| --- | --- | --- |
| Race khi hai request cùng tạo bản ghi | Cùng business key, thread/barrier, điểm đọc/ghi có cạnh tranh | `Thread.sleep(100)` để “hy vọng” trùng |
| `@Async` listener chậm | Executor/queue, event ID, checkpoint completion, timeout | Assert `isEmpty()` ngay sau publish rồi kết luận sẽ không có event |
| Test A ảnh hưởng test B | Context cache, singleton state, cùng ID, thứ tự/parallel mode | Chạy riêng một test rồi kết luận không có bug |

Một `Scenario` đã thấy **một** event kết quả không chứng minh sẽ không xuất hiện duplicate về sau. Nếu muốn kiểm tra không có duplicate, MRE cần một mốc **quiescence**: tất cả công việc liên quan đã hoàn tất, hoặc database có unique constraint/business invariant được kiểm tra.

### 8.2. Dùng latch để tái hiện race thay vì phụ thuộc sleep

Ví dụ **unit test cô lập một race có chủ đích**, không cần Spring context. Một guard bị lỗi thực hiện “check rồi add” không nguyên tử; test dùng barrier để ép cả hai thread cùng quan sát trạng thái chưa có ID:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class DuplicateAcceptanceReproTests {

    @Test
    void reproducesCheckThenActRace() throws Exception {
        UUID orderId = UUID.randomUUID();
        Set<UUID> accepted = ConcurrentHashMap.newKeySet();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch proceed = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(2);

        try {
            java.util.concurrent.Callable<Boolean> command = () -> {
                boolean wasAbsent = !accepted.contains(orderId);
                bothRead.countDown();
                if (!proceed.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Barrier timeout");
                }
                if (wasAbsent) {
                    accepted.add(orderId);
                    return true; // Lỗi: trả true theo snapshot cũ.
                }
                return false;
            };

            var first = pool.submit(command);
            var second = pool.submit(command);

            assertThat(bothRead.await(5, TimeUnit.SECONDS))
                    .isTrue();
            proceed.countDown();

            assertThat(first.get(5, TimeUnit.SECONDS)).isTrue();
            assertThat(second.get(5, TimeUnit.SECONDS)).isTrue();

            // Một ID trong Set nhưng có HAI accepted decisions:
            // nếu cả hai caller publish event thì có duplicate.
            assertThat(accepted).containsExactly(orderId);
        } finally {
            proceed.countDown();
            pool.shutdownNow();
        }
    }
}
```

Test trên **mô tả và xác nhận bug có chủ đích**, nên nó assert rằng **cả hai lời gọi đều trả true** khi bị barrier ép cùng qua chỗ sai. Nó không phải regression test để chấp nhận code production lỗi.

Để sửa implementation trong ứng dụng, thay check-then-act bằng thao tác nguyên tử phù hợp (ví dụ `accepted.add(orderId)` ở một JVM; với nhiều instances, dùng database unique constraint/atomic insert). **Regression test sau sửa** phải assert **chỉ một accepted decision**, rồi event/business side effect đúng số lần. Lúc đó test chứng minh điều kiện đã thay đổi, chứ không chỉ chờ may rủi của scheduler.

### 8.3. Ghi số lần chạy và phân bố thất bại

Với lỗi flaky, ghi như mẫu:

```text
Runs: <n>
Failures: <k>
Test command: <exact command>
Run order: isolated / full suite / parallel
Worker count: <n>
Executor type: <name>
Correlation IDs: <IDs recorded per failed run>
Failure fingerprint: <consistent / multiple fingerprints>
```

Nếu 5/20 lần chạy fail, ghi **5/20**, không chỉ “thỉnh thoảng”. Nếu trong các lần fail có **hai root causes khác nhau**, tách thành hai reproduction records. Đừng gộp `NoSuchBeanDefinitionException` và `Scenario` timeout thành một case chỉ vì cùng test class.

## 9. Mẫu báo cáo MRE có thể gửi ngay cho reviewer/prime

Sau khi rút gọn, kết quả nên gồm **một gói thông tin ngắn đủ thử lại**:

```yaml
title: "Scenario không thấy InvoiceCreated ở orders STANDALONE"
scope: "Spring Modulith application-module test"
revision: "<actual-commit-id>"
environment:
  jdk: "<actual-version>"
  boot: "<actual-version>"
  modulith: "<actual-version>"
  build: "<actual-wrapper>"
repro:
  class: "com.example.shop.orders.OrdersModuleReproTests"
  method: "consumerOutcomeTimesOut"
  annotation: "@ApplicationModuleTest"
  bootstrap_mode: "STANDALONE"
  profiles: "<actual-profiles>"
  steps:
    - "Temporarily enable intentionally disabled repro test"
    - "Run only the failing test by its exact build-tool command"
    - "Observe OrderSubmitted for the generated orderId"
    - "Wait for InvoiceCreated with the same orderId"
expected: "InvoiceCreated is observed"
actual: "<exact failure from run, including timeout>"
evidence:
  source_event_count: "<observed-count>"
  listener_present: "<yes/no/unknown>"
  first_root_cause: "<real exception or observation>"
control:
  class: "com.example.shop.billing.BillingModuleControlTests"
  expected: "listener bean present and InvoiceCreated observed"
  actual: "<result from actual control run>"
conclusion: "<confirmed cause, or explicitly unresolved>"
```

**Không điền kết quả “pass”, số lần fail hay version theo trí nhớ.** Mẫu cung cấp chỗ lưu, còn giá trị trong một issue thật phải đến từ build logs, code/config đúng revision và các phép kiểm đã thực hiện. Không gửi stack trace 2.000 dòng nếu 20 dòng `Caused by` gần lỗi gốc và một đường dẫn log đầy đủ đã đủ để điều tra.

### 9.1. Phần tối thiểu cần dán vào pull request

```text
Contract:
  When source OrderSubmitted(orderId) is handled by billing,
  billing publishes InvoiceCreated(orderId).

Minimal failing condition:
  Test package = com.example.shop.orders
  @ApplicationModuleTest = STANDALONE
  Consumer listener belongs to com.example.shop.billing.internal

Observed:
  Source event count = <actual count>
  Listener in context = <actual state>
  Outcome = <actual result>

Control:
  Billing @ApplicationModuleTest with same public event
  Result = <actual result>

Change proposed:
  Place consumer-contract test inside billing,
  keep orders publisher contract independent.
```

Kết luận chỉ trở thành **confirmed** khi những quan sát trong mục `Observed`/`Control` đã được thực thi và hỗ trợ kết luận. Trước đó ghi “hypothesis” là đúng kỹ thuật.

### 9.2. Giữ nguyên dữ kiện nhưng bỏ bí mật

Khi báo lỗi nội bộ, tránh đính kèm token, password, DSN nguyên vẹn, thông tin khách hàng hoặc payload có PII. Thay:

```text
DB_URL = jdbc:postgresql://<redacted-host>/<redacted-db>
Profile = test
Feature flag notifications.enabled = false
```

Nếu host thực tế không liên quan đến failure, không cần ghi tên host. Nếu lỗi liên quan topology/multiple datasources, ghi **vai trò** và quan hệ giữa các datasource mà không tiết lộ chi tiết nhạy cảm.

## 10. Kiểm chứng lại, tích hợp CI và bài tập tự thực hiện

### 10.1. Ba phép kiểm độc lập nên đi cùng nhau

**Architecture test** không khởi động listener; nó kiểm tra quy tắc module:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureVerificationTests {

    @Test
    void verifiesDependencyBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

**Publisher module test** ở `orders` xác nhận `OrderSubmitted` đúng count/payload bằng `PublishedEvents`. **Consumer module test** ở `billing` xác nhận listener thực được bootstrap và tạo `InvoiceCreated` bằng `Scenario`. Nếu cần kiểm tra luồng xuyên module với transaction và persistence, thêm **integration test** có đủ module/hạ tầng thật.

| Gate | Có thể chứng minh | Không thể tự chứng minh |
| --- | --- | --- |
| `ApplicationModules.verify()` | Dependency/API boundary và cycle hợp lệ | Listener bean tồn tại trong runtime |
| `orders` `@ApplicationModuleTest` + `PublishedEvents` | Source event được publish đúng ID/count | Billing consumer đã chạy |
| `billing` `@ApplicationModuleTest` + `Scenario` | Consumer xử lý source event trong context đó | Toàn bộ pipeline production đã hoạt động |
| Transaction + DB integration | Commit, repository visibility, outcome theo contract | External delivery exactly-once nếu không test |
| MRE/issue record | Người khác biết điều kiện và kết quả phải kiểm tra | Tự động sửa bug khi chưa có root cause |

**Lưu ý về kiến trúc:** Trong ví dụ, `billing.internal.InvoiceListener` import event public `orders.OrderSubmitted`, không import internal implementation của orders. Nếu test bị đặt sai module, không “sửa” bằng cách mở component scanning toàn app để làm xanh rồi vô tình làm mất ý nghĩa module isolation.

### 10.2. Đưa bản tái hiện thành regression test, không giữ cố tình fail trong CI

Quy trình đóng issue:

1. Lưu bản MRE fail có fingerprint và điều kiện tái hiện.
2. Xác nhận root cause bằng đối chứng, không chỉ suy từ timeout.
3. Sửa **ít nhất một nguyên nhân đã được kiểm chứng**.
4. Chuyển MRE thành test **pass khi code/cấu hình đúng**, fail khi hồi quy quay lại.
5. Chạy riêng test, rồi chạy suite có architecture/module/integration gates thích hợp.
6. Cập nhật báo cáo bằng **kết quả thực tế** sau sửa và commit tương ứng.

Với failure do test đặt sai module, một hướng sửa tốt là giữ test `orders` chỉ assert **event nguồn**, chuyển test `InvoiceCreated` sang `billing` như đối chứng mục 6; xóa hoặc giữ disabled test lỗi **ngoài CI** theo quy ước đội. Với bug production thật, test hồi quy phải chạy **implementation lỗi trước đây**, không mock chính method cần chứng minh.

### 10.3. Lệnh test có thể dùng sau khi tạo MRE

Maven Wrapper (khi repository dùng Maven):

```bash
./mvnw -Dtest=OrdersModuleReproTests#sourceEventExistsButBillingBeanIsOutsideScope test
./mvnw -Dtest=BillingModuleControlTests test
```

Gradle Wrapper (khi repository dùng Gradle):

```bash
./gradlew test --tests "com.example.shop.orders.OrdersModuleReproTests"
./gradlew test --tests "com.example.shop.billing.BillingModuleControlTests"
```

Lưu ý `@Disabled` test timeout ở mục 5: để quan sát failure có chủ đích, tạm bỏ `@Disabled` rồi lọc **đúng method `consumerOutcomeTimesOut`**; nếu chạy cả class với test cố ý fail đang bật, lệnh test sẽ đỏ theo thiết kế. **Không có lệnh nào ở đây đã được chạy khi soạn bài.** Tên wrapper và filter phải đối chiếu build system thực tế; nếu dùng Spring Boot/Modulith phiên bản khác, cần giữ version đúng của nguồn đang tái hiện.

### 10.4. Bài tập rèn kỹ năng

1. **Tạo fingerprint:** từ một stack trace `NoSuchBeanDefinitionException`, ghi bean type, test package, bootstrap mode, phase. Không phán lỗi production khi context chưa khởi động.
2. **Rút gọn `Scenario` timeout:** bỏ HTTP/DB/async khỏi ví dụ orders–billing, kiểm tra failure vẫn do consumer nằm ngoài `orders` `STANDALONE`.
3. **Đối chứng dương:** chạy `BillingModuleControlTests`, ghi bean count, source event count và result event theo cùng `orderId`.
4. **Đổi một biến:** chuyển vị trí test chờ consumer (không đổi listener code), quan sát kết quả. Ghi kết luận có giới hạn.
5. **Đối chứng phản bác:** bỏ `@Component` khỏi `InvoiceListener` và xem consumer control fail; cập nhật giả thuyết thay vì kết luận test scope duy nhất gây lỗi.
6. **Transaction case:** dùng listener `AFTER_COMMIT`, thử với test-managed transaction rollback và transaction commit thật. Ghi transaction boundary như một thành phần của MRE.
7. **Fixture case:** seed entity chưa commit rồi đọc từ async listener; phân biệt thiếu dữ liệu với không nhìn thấy dữ liệu.
8. **Race case:** dùng `CountDownLatch` tái hiện check-then-act; sửa bằng atomic operation và viết regression assertion chỉ một acceptance.
9. **Flaky case:** ghi số lần fail/tổng lần chạy, thứ tự suite, parallel mode, correlation ID và failure fingerprint riêng.
10. **CI handoff:** điền mẫu mục 9 với revision/version/log thực, chuyển thành test pass sau sửa và giữ `ApplicationModules.verify()` độc lập.

**Tiêu chí hoàn thành:** người học có thể giao cho một đồng nghiệp **một lệnh, một test, một stimulus, một fingerprint và một phép đối chứng** đủ để tự tái hiện cùng lỗi; biết xác định dữ kiện nào được đo, dữ kiện nào còn giả thuyết, và biến MRE thành regression test có ích.

### Kết luận

**Ghi lại điều kiện tái hiện tối thiểu** là kỹ năng điều tra failure, không phải thao tác rút ngắn stack trace. Với Spring Modulith, các chi tiết như `package` của test, `@ApplicationModuleTest` bootstrap mode, chiều phụ thuộc module, thời điểm transaction commit và listener registration **có thể chính là nguyên nhân**. Hãy giữ những điều kiện ấy, loại bỏ hạ tầng không liên quan, ghi expected/actual theo correlation ID và kiểm tra bằng đối chứng độc lập. Một MRE tốt giúp phân biệt **lỗi setup của test**, **lỗi production behavior**, **lỗi kiến trúc** và **lỗi quan sát async** mà không làm xanh giả quality gate.

## Tài liệu tham khảo

- [Spring Modulith Reference — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith Reference — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith Javadoc — ApplicationModuleTest](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/ApplicationModuleTest.html)
- [Spring Modulith Javadoc — PublishedEvents](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/PublishedEvents.html)
- [Spring Modulith Javadoc — Scenario](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/test/Scenario.html)
- [Spring Framework Reference — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework Reference — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
