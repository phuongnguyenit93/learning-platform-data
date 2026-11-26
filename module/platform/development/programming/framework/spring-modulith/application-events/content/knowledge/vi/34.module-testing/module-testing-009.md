# Test với application context

## Vì sao cần kiểm thử với ApplicationContext thật?

Một unit test có thể gọi trực tiếp service và mock repository để xác nhận quy tắc nghiệp vụ. Cách đó hữu ích nhưng không chứng minh ứng dụng Spring có thể khởi tạo các bean cần thiết và kết nối chúng đúng cách.

Nhiều lỗi chỉ xuất hiện khi Spring tạo ApplicationContext: thiếu bean, cấu hình điều kiện không khớp, component không được scan, dependency injection sai, proxy transaction không hoạt động, listener không được đăng ký hoặc cấu hình persistence không tương thích. Kiểm thử với ApplicationContext giúp xác nhận các thành phần được lắp ráp và hoạt động trong môi trường gần với cách ứng dụng chạy thực tế.

Trong Spring Modulith, cần chọn phạm vi context phù hợp. Có test chỉ cần module đang phát triển; có test cần thêm các module mà nó phụ thuộc; và có test cần toàn bộ ứng dụng cùng hạ tầng tích hợp. Khởi tạo phạm vi nhỏ giúp test nhanh và làm rõ module nào đang được kiểm tra.

## ApplicationContext bao gồm những gì?

ApplicationContext là container của Spring quản lý bean, dependency injection, lifecycle, event multicaster, environment, resource và nhiều cơ chế nền tảng khác.

Khi test khởi tạo context, Spring thực hiện các bước như:

1. Đọc cấu hình ứng dụng và cấu hình test.
2. Tìm component và cấu hình bean trong phạm vi được chọn.
3. Tạo bean, giải quyết dependency và áp dụng bean post-processor.
4. Tạo proxy cho các cơ chế như transaction hoặc method security khi được cấu hình.
5. Áp dụng profile, property source và điều kiện cấu hình.
6. Hoàn tất quá trình refresh ApplicationContext trước khi chạy test method.

Một test chỉ khởi tạo context và xác nhận không có exception đã kiểm tra được wiring cơ bản. Để chứng minh module hoạt động đúng, cần gọi use case hoặc phát event và kiểm tra kết quả có ý nghĩa.

~~~mermaid
flowchart TD
    T[Test class] --> B[Spring test bootstrap]
    B --> E[Environment and profiles]
    B --> C[Component scanning and configuration]
    C --> D[Dependency injection and proxies]
    D --> A[ApplicationContext ready]
    A --> U[Invoke module use case]
    U --> V[Assert state and behavior]
~~~

## Chọn loại test context

Không phải mọi test đều cần khởi động toàn bộ ứng dụng. Chọn loại context theo phạm vi hành vi cần xác nhận:

| Loại test | Phạm vi | Khi phù hợp |
|---|---|---|
| Unit test | Không khởi tạo Spring context | Kiểm tra logic thuần của service hoặc mapper |
| ApplicationModuleTest | Một module và dependency theo bootstrap mode | Kiểm tra wiring, public API và hành vi trong ranh giới module |
| SpringBootTest | Toàn bộ ứng dụng hoặc cấu hình ứng dụng được chọn | Kiểm tra tích hợp giữa nhiều module và cấu hình production-like |
| Slice test | Một lát cắt như MVC hoặc persistence | Kiểm tra một tầng framework với phạm vi bean giới hạn |
| ApplicationContextRunner | Context nhỏ do test điều khiển | Kiểm tra auto-configuration và điều kiện tạo bean |

Một test module không cần khởi động web server nếu mục tiêu chỉ là kiểm tra service và event listener. Một test API HTTP có thể dùng web slice. Một luồng xuyên nhiều module có thể cần SpringBootTest hoặc nhiều module context được cấu hình rõ.

Khởi động context lớn hơn mức cần thiết làm test chậm, tăng phụ thuộc giữa test và khiến lỗi khó định vị. Ngược lại, context quá nhỏ có thể bỏ qua cấu hình hoặc bean mà hành vi thật cần.

## Dùng @ApplicationModuleTest của Spring Modulith

Spring Modulith cung cấp @ApplicationModuleTest để khởi tạo ApplicationContext theo ranh giới module. Đặt test class trong package thuộc module cần kiểm tra để Spring Modulith xác định module tương ứng.

Ví dụ:

~~~java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrdersModuleContextTests {

    @Autowired
    OrderManagement orderManagement;

    @Test
    void startsOrdersModuleContext() {
        assertThat(orderManagement).isNotNull();
    }
}
~~~

Ví dụ trên xác nhận context của module Orders có thể khởi tạo và public API OrderManagement được đăng ký. Đây là kiểm tra wiring ban đầu; cần thêm test use case để xác nhận hành vi và side effect.

ApplicationModuleTest phù hợp khi muốn kiểm tra module trong phạm vi kiến trúc đã khai báo. Nó giúp phát hiện sớm việc module vô tình phụ thuộc bean nội bộ hoặc cấu hình của module khác mà không thông qua dependency được công bố.

## Chọn bootstrap mode

@ApplicationModuleTest hỗ trợ các chế độ bootstrap để điều khiển module nào được đưa vào context:

| Bootstrap mode | Phạm vi khởi tạo | Mục đích |
|---|---|---|
| STANDALONE | Module đang được test | Kiểm tra module độc lập qua public API và các dependency được cung cấp phù hợp |
| DIRECT_DEPENDENCIES | Module đang test cùng các module phụ thuộc trực tiếp | Kiểm tra tích hợp với những module mà module hiện tại khai báo phụ thuộc |
| ALL_DEPENDENCIES | Module đang test cùng toàn bộ dependency theo chuỗi phụ thuộc | Kiểm tra luồng cần nhiều module liên quan |

Ví dụ chọn DIRECT_DEPENDENCIES:

~~~java
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES
)
class OrdersWithDirectDependenciesTests {
}
~~~

Dùng STANDALONE khi muốn kiểm tra module tách biệt và thay thế dependency ngoài module bằng test double hoặc adapter phù hợp. Dùng DIRECT_DEPENDENCIES khi use case cần gọi public API của module phụ thuộc trực tiếp. Chọn ALL_DEPENDENCIES khi hành vi cần kiểm tra đi qua chuỗi dependency sâu hơn.

Không chọn ALL_DEPENDENCIES chỉ để test chạy được khi một bean bị thiếu. Hãy xem dependency nào đang được kéo vào và vì sao module cần nó. Nếu module cần một module khác, dependency đó nên được thể hiện rõ trong kiến trúc và qua API được công bố.

## Kiểm tra public API và ranh giới module

Một module nên được sử dụng qua public API được công bố. Application context test giúp xác nhận use case bên ngoài có thể tương tác với module qua API đó mà không truy cập repository hoặc service nội bộ.

Ví dụ:

~~~java
@ApplicationModuleTest(
    mode = ApplicationModuleTest.BootstrapMode.DIRECT_DEPENDENCIES
)
class OrderConfirmationContextTests {

    @Autowired
    OrderManagement orderManagement;

    @Test
    void confirmsOrderThroughPublicApi() {
        OrderId orderId = OrderId.of("ORD-1001");

        orderManagement.confirm(orderId);

        // Assert trạng thái qua API đọc được công bố hoặc kết quả nghiệp vụ.
    }
}
~~~

Fixture và cách kiểm tra trạng thái cần theo public API thực tế của module. Không inject repository nội bộ chỉ để test thuận tiện nếu repository đó không thuộc contract module.

Nếu module cần một collaborator từ module khác, test nên dùng public API hoặc contract được công bố. Cách này giúp test phản ánh cách các module thực sự tích hợp và giữ ranh giới được kiểm tra.

## Khi nào dùng @SpringBootTest?

@SpringBootTest khởi tạo context dựa trên cấu hình Spring Boot của ứng dụng. Nó phù hợp với hành vi cần nhiều module hoặc cấu hình toàn ứng dụng cùng hoạt động.

Ví dụ:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class OrderWorkflowIntegrationTests {

    @Autowired
    OrderManagement orderManagement;

    @Autowired
    BillingQueries billingQueries;

    @Test
    void confirmsOrderAndCreatesBillingEntry() {
        OrderId orderId = OrderId.of("ORD-2001");

        orderManagement.confirm(orderId);

        // Chờ hoặc truy vấn kết quả theo semantics của workflow.
    }
}
~~~

WebEnvironment.NONE tránh khởi chạy web server khi test chỉ cần application context. Nếu cần xác nhận endpoint HTTP, chọn MOCK hoặc RANDOM_PORT theo mục tiêu test.

@SpringBootTest nên dành cho các luồng tích hợp có giá trị. Nếu mọi test service đều dùng full context, test suite có thể chậm đáng kể và trở nên dễ vỡ khi cấu hình toàn ứng dụng thay đổi.

## Kết hợp test context với profile và properties

Context test cần cấu hình môi trường xác định. Dùng profile và property để cung cấp endpoint, database hoặc feature flag phù hợp với test.

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
    "spring.main.web-application-type=none",
    "orders.events.externalization.enabled=false"
})
class OrdersApplicationContextTests {
}
~~~

Tên property trong ví dụ chỉ minh họa; hãy dùng property thực tế mà ứng dụng định nghĩa. Không đặt secret production hoặc credential thật trong test resource.

Với property động như cổng server test hoặc URL container, có thể dùng @DynamicPropertySource:

~~~java
@SpringBootTest
class OrdersWithDynamicPropertiesTests {

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("integration.endpoint", () -> "http://localhost:18080");
    }
}
~~~

Giữ cấu hình test tách biệt khỏi cấu hình production. Nếu test cần một bean giả lập, đăng ký rõ ràng qua test configuration hoặc bean override, tránh phụ thuộc vào một profile vô tình vô hiệu hóa nhiều thành phần.

## Thêm test bean và thay thế dependency

Có thể dùng @TestConfiguration để khai báo bean chỉ phục vụ test:

~~~java
@TestConfiguration
class OrdersTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-15T10:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
~~~

Đưa cấu hình vào test bằng @Import:

~~~java
@SpringBootTest
@Import(OrdersTestConfiguration.class)
class OrderTimeBehaviorTests {
}
~~~

Một dependency bên ngoài như payment gateway hoặc email client có thể được thay thế bằng mock trong context. Với Spring Framework hỗ trợ bean override của Mockito, có thể dùng @MockitoBean:

~~~java
@SpringBootTest
class OrderPaymentContextTests {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    OrderManagement orderManagement;

    @Test
    void handlesPaymentGatewayResponse() {
        given(paymentGateway.authorize(any()))
            .willReturn(PaymentAuthorization.approved());

        // Gọi use case và kiểm tra kết quả.
    }
}
~~~

@MockitoBean thuộc cơ chế bean override của Spring Test ở các phiên bản Spring Framework tương ứng. Với phiên bản Spring Boot/Spring Framework cũ hơn, dự án có thể đang dùng @MockBean; hãy theo phiên bản dependency đã khai báo.

Chỉ mock hệ thống ngoài hoặc collaborator mà test không nhằm xác minh. Nếu mục tiêu là kiểm tra transaction, repository hoặc event listener thật, không mock chính thành phần cần kiểm tra.

## Kiểm tra bean wiring và điều kiện cấu hình

Một context test có thể xác nhận các bean quan trọng được tạo đúng:

~~~java
@SpringBootTest
class OrdersWiringTests {

    @Autowired
    ApplicationContext context;

    @Test
    void registersRequiredComponents() {
        assertThat(context.getBean(OrderManagement.class)).isNotNull();
        assertThat(context.getBean(OrderRepository.class)).isNotNull();
        assertThat(context.getBean(OrderConfirmedListener.class)).isNotNull();
    }
}
~~~

Không nên biến mọi test thành danh sách assert bean tồn tại. Việc bean được tạo không chứng minh method hoạt động hoặc transaction đúng. Hãy dùng kiểm tra wiring cho các thành phần quan trọng, rồi kiểm tra behavior qua use case.

Với bean có điều kiện, cần test cả hai nhánh property bật và tắt. Ví dụ, nếu externalization chỉ được bật khi có cấu hình broker, test cần xác nhận adapter được tạo khi cấu hình hợp lệ và không làm context thất bại khi tính năng bị tắt theo thiết kế.

Nếu có nhiều bean cùng type, xác nhận qualifier hoặc primary selection đúng. Nếu context tạo nhầm implementation, test hành vi có thể phát hiện lỗi tốt hơn việc chỉ assert bean count.

## Kiểm tra application event trong context thật

ApplicationContext test hữu ích để xác nhận publisher và listener được Spring đăng ký đúng. Có thể ghi nhận event bằng @RecordApplicationEvents:

~~~java
@SpringBootTest
@RecordApplicationEvents
class OrderEventContextTests {

    @Autowired
    OrderManagement orderManagement;

    @Autowired
    ApplicationEvents applicationEvents;

    @Test
    void publishesOrderConfirmed() {
        orderManagement.confirm(OrderId.of("ORD-3001"));

        assertThat(applicationEvents.stream(OrderConfirmed.class))
            .hasSize(1);
    }
}
~~~

ApplicationEvents ghi nhận event trong phạm vi test. Đây là cách xác nhận event được publish; nó không tự chứng minh mọi listener bất đồng bộ đã hoàn tất hoặc side effect đã commit.

Để kiểm tra listener, hãy chờ kết quả cuối cùng bằng Awaitility hoặc Spring Modulith Scenario API. Nếu event được xử lý sau commit, test phải tạo điều kiện để transaction publisher commit thật.

## Kiểm tra transaction và listener sau commit

Một context test có thể xác nhận cấu hình transaction và listener cùng hoạt động. Các trường hợp quan trọng:

- Transaction commit: listener after-commit được gọi theo phase đã khai báo.
- Transaction rollback: listener after-commit không xử lý thay đổi chưa commit.
- Listener có transaction riêng: side effect của listener commit hoặc rollback độc lập theo cấu hình.
- Listener lỗi: trạng thái publication và cơ chế phục hồi tuân theo Event Publication Registry đã cấu hình.

Spring Test thường tự rollback transaction được gắn trên test method hoặc test class. Nếu test phát event trong transaction đó, listener AFTER_COMMIT có thể không chạy vì transaction chưa commit. Có thể dùng test không bọc transaction hoặc chủ động kết thúc transaction bằng TestTransaction khi phù hợp.

~~~java
@Test
@Transactional
void commitsTransactionToTriggerAfterCommitListener() {
    orderManagement.confirm(OrderId.of("ORD-3002"));

    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Sau khi transaction kết thúc, chờ side effect của listener.
}
~~~

Ví dụ cần được dùng với test transaction được Spring Test quản lý. Không gọi TestTransaction nếu test không chạy trong transaction test. Sau khi kết thúc transaction, hãy xác nhận side effect bằng truy vấn độc lập hoặc Awaitility.

## Kiểm tra listener bất đồng bộ

Listener bất đồng bộ có thể bắt đầu sau khi method command đã trả về. Vì vậy, assertion tức thời thường tạo flaky test.

Ví dụ dùng Awaitility:

~~~java
@Test
void updatesProjectionAfterEventCommit() {
    orderManagement.confirm(OrderId.of("ORD-4001"));

    await()
        .atMost(Duration.ofSeconds(5))
        .untilAsserted(() ->
            assertThat(orderSummaryRepository.findByOrderId(
                OrderId.of("ORD-4001")
            )).isPresent()
        );
}
~~~

Chờ một điều kiện có ý nghĩa, chẳng hạn version projection đạt version event hoặc một bản ghi được commit. Tránh Thread.sleep cố định vì test có thể chạy nhanh hơn hoặc chậm hơn thời gian sleep tùy máy.

Nếu có nhiều listener, chờ từng side effect hoặc một điều kiện tổng hợp bao phủ tất cả. Không chờ listener nhanh nhất rồi kết luận cả context đã xử lý xong event.

Cũng cần cấu hình executor test đủ tài nguyên. Một executor bị tắt hoặc queue quá nhỏ có thể khiến listener không được dispatch, dù bean đã tồn tại.

## Kiểm tra module với Scenario API

Spring Modulith cung cấp Scenario API để viết test theo luồng event. Scenario có thể phát event, chờ event tiếp theo và xác nhận nội dung event nhận được.

~~~java
@ApplicationModuleTest
class OrderScenarioTests {

    @Autowired
    Scenario scenario;

    @Test
    void emitsShipmentPreparedAfterOrderConfirmation() {
        OrderConfirmed event = new OrderConfirmed(
            UUID.randomUUID(),
            OrderId.of("ORD-5001")
        );

        scenario.publish(event)
            .andWaitForEventOfType(ShipmentPrepared.class)
            .toArriveAndVerify(next ->
                assertThat(next.orderId()).isEqualTo(event.orderId())
            );
    }
}
~~~

Scenario phù hợp để kiểm tra event chain và listener trong phạm vi module. Nếu cần xác nhận side effect database, kết hợp assertion repository hoặc public query API. Nếu event đi qua broker thật, cần broker integration test riêng.

API cụ thể và cách cấu hình Scenario phụ thuộc phiên bản Spring Modulith. Hãy dùng test support tương ứng với dependency của dự án.

## Kiểm tra dependency giữa các module

Một module context test có thể giúp phát hiện dependency thiếu hoặc dependency ngoài ranh giới. Hãy kiểm tra module chỉ truy cập API được công bố và các module phụ thuộc được bootstrap đúng.

Khi cần kiểm tra toàn bộ kiến trúc module, có thể bổ sung test cấu trúc:

~~~java
class ModuleArchitectureTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Đây là kiểm tra kiến trúc riêng, không thay thế ApplicationContext test. ApplicationModules.verify() kiểm tra cấu trúc và dependency theo quy tắc Spring Modulith; context test kiểm tra bean wiring và hành vi khi Spring khởi tạo.

Nếu context chỉ chạy được khi import một repository nội bộ của module khác, đó có thể là dấu hiệu module đang vượt ranh giới. Ưu tiên sửa thiết kế để phụ thuộc public API thay vì thêm import test để che lỗi.

## Kiểm tra persistence và external dependency

Một ApplicationContext test có thể dùng database test, embedded service hoặc container tùy mức độ tích hợp cần xác nhận.

| Thành phần | Cách kiểm thử |
|---|---|
| Repository/JPA mapping | Database test phù hợp với dialect và schema |
| Transaction manager | Gọi use case thật rồi xác nhận commit/rollback |
| Kafka/RabbitMQ adapter | Broker test khi cần xác nhận serialization, routing và acknowledgement |
| HTTP client | Mock server hoặc test server cho contract HTTP |
| Clock | Clock cố định để test thời gian xác định |
| File/object storage | Adapter test hoặc storage giả lập có hành vi phù hợp |

Không thay toàn bộ persistence bằng mock trong test có mục tiêu xác nhận transaction. Hành vi transaction, constraint và query phụ thuộc database thực tế.

Không nhất thiết phải khởi động mọi dịch vụ ngoài cho mỗi context test. Dùng test double cho các dependency không thuộc phạm vi đang kiểm tra, và có một số integration test riêng để xác nhận adapter với hệ thống thật hoặc container tương đương.

## Tối ưu tốc độ và cô lập context

Spring Test có cơ chế cache ApplicationContext giữa các test có cấu hình tương đương. Tận dụng cache giúp giảm thời gian khởi động, nhưng các thay đổi context khác nhau có thể làm cache miss.

Để test nhanh và ổn định:

- Dùng chung cấu hình test khi các test có cùng phạm vi.
- Tránh thêm property hoặc mock bean khác nhau không cần thiết vào từng class.
- Dùng module context thay cho full application context khi đủ.
- Tránh @DirtiesContext trừ khi test thực sự làm context không còn dùng được.
- Dọn dữ liệu test thay vì khởi tạo lại context chỉ để cô lập database.
- Dùng ID riêng và transaction boundary rõ ràng.
- Đóng tài nguyên test như container, executor hoặc server đúng lifecycle.

Cache context không có nghĩa dữ liệu database tự được reset. Cần có chiến lược cleanup hoặc transaction rollback phù hợp. Với listener async, rollback test transaction có thể không dọn được side effect chạy trong transaction riêng; test cần cleanup rõ ràng.

## Chẩn đoán lỗi khởi tạo ApplicationContext

Khi test báo ApplicationContext failure, bắt đầu từ nguyên nhân đầu tiên trong exception chain thay vì chỉ đọc dòng cuối cùng.

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| NoSuchBeanDefinitionException | Bean chưa được scan hoặc module không nằm trong bootstrap scope | Kiểm tra package, component scan, bootstrap mode và dependency |
| NoUniqueBeanDefinitionException | Có nhiều bean cùng type | Kiểm tra qualifier, primary và test configuration |
| UnsatisfiedDependencyException | Constructor dependency không thể tạo | Theo dõi cause chain tới bean lỗi đầu tiên |
| BeanCreationException | Lỗi trong factory method hoặc lifecycle | Kiểm tra property, external resource và initialization |
| Circular dependency | Các bean phụ thuộc vòng tròn | Sửa dependency direction hoặc tách trách nhiệm |
| Failed to configure DataSource | Thiếu URL, driver hoặc test database | Kiểm tra profile và property test |
| Listener không chạy | Bean không đăng ký, transaction chưa commit hoặc executor lỗi | Kiểm tra event publication, phase và async configuration |
| Test chạy được riêng nhưng lỗi khi chạy cả suite | Dữ liệu dùng chung, context state hoặc test song song | Cô lập fixture và cleanup |

Không thêm bean giả chỉ để làm context khởi động nếu bean đó là thành phần cần kiểm tra. Trước tiên xác định test đang dùng sai bootstrap mode hay module thực sự thiếu dependency được khai báo.

## Quy trình thiết kế ApplicationContext test

Khi thêm test cho một module Spring Modulith, thực hiện theo thứ tự:

1. Xác định hành vi cần kiểm tra và module sở hữu hành vi đó.
2. Chọn unit test, ApplicationModuleTest, SpringBootTest hoặc slice test theo phạm vi.
3. Chọn bootstrap mode nhỏ nhất vẫn chứa dependency cần thiết.
4. Đặt test class trong package phù hợp để Spring Modulith nhận diện module.
5. Cấu hình profile và properties test rõ ràng.
6. Dùng public API của module để gọi use case.
7. Kiểm tra bean wiring và kết quả nghiệp vụ, không chỉ kiểm tra context khởi tạo.
8. Nếu có event, xác nhận publish riêng với listener completion và side effect.
9. Kiểm tra transaction commit/rollback và async behavior theo cấu hình thật.
10. Chỉ mở rộng context hoặc thêm test double khi có lý do rõ ràng.
11. Giữ fixture cô lập, tận dụng context cache và cleanup tài nguyên.

Kiểm thử với ApplicationContext giúp xác nhận các module được Spring lắp ráp đúng trong phạm vi đã chọn. Khi bắt đầu bằng module context, dùng public API, cấu hình môi trường xác định và kiểm tra cả side effect lẫn transaction, test vừa bảo vệ ranh giới module vừa phát hiện được lỗi wiring trước khi triển khai.

## Tài liệu tham khảo

- Spring Modulith Reference — Testing Application Modules: https://docs.spring.io/spring-modulith/reference/testing.html
- Spring Modulith Reference — Application Module Structure: https://docs.spring.io/spring-modulith/reference/fundamentals.html
- Spring Boot Reference — Testing: https://docs.spring.io/spring-boot/reference/testing/index.html
- Spring Framework Reference — Testing: https://docs.spring.io/spring-framework/reference/testing.html
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
