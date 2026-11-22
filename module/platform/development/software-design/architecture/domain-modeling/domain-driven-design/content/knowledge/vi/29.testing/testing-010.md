# Kiểm thử kiến trúc để phát hiện phụ thuộc sai ranh giới

Trong Domain-Driven Design (DDD), một mô hình có thể được chia thành nhiều Aggregate, module và Bounded Context để mỗi phần bảo vệ quy tắc nghiệp vụ của mình. Nhưng sơ đồ kiến trúc chỉ mô tả ý định tại một thời điểm. Khi nhiều người cùng phát triển, một import tiện tay, một lời gọi repository xuyên module hoặc một dependency ngược chiều có thể âm thầm làm ranh giới bị phá vỡ.

**Kiểm thử kiến trúc (Architecture Testing)** biến các quy tắc cấu trúc thành những kiểm tra tự động chạy cùng bộ test của dự án. Nó giúp phát hiện sớm các phụ thuộc sai hướng, vòng phụ thuộc, truy cập vào phần nội bộ của Bounded Context khác và sự rò rỉ của framework vào domain model.

Trong DDD, loại kiểm thử này bảo vệ các quyết định như: Domain không phụ thuộc Infrastructure; Application điều phối use case qua các abstraction; mỗi Bounded Context sở hữu mô hình nội bộ; các context giao tiếp qua contract đã công bố. Nó không thay thế kiểm thử hành vi nghiệp vụ, nhưng giúp kiến trúc đã thống nhất tiếp tục được giữ đúng khi code thay đổi.

## 1. Vì sao cần kiểm thử kiến trúc?

### 1.1. Code vẫn chạy dù kiến trúc đã sai

Giả sử dự án có cấu trúc:

~~~text
ordering/
  domain/
  application/
  adapter/
    web/
    persistence/
billing/
  domain/
  application/
  adapter/
~~~

Ý định thiết kế là:

- Domain chứa mô hình và quy tắc nghiệp vụ.
- Application điều phối use case.
- Adapter kết nối REST, database, message broker và hệ thống bên ngoài.
- Ordering và Billing là hai Bounded Context có mô hình riêng.

Một thay đổi có thể làm xuất hiện phụ thuộc như:

~~~java
// Trong ordering/domain
import billing.adapter.persistence.BillingJpaRepository;
~~~

Hoặc:

~~~java
// Trong ordering/application
import billing.domain.InternalInvoice;
~~~

Ứng dụng vẫn có thể biên dịch và chạy. Tuy nhiên, Ordering đang biết chi tiết lưu trữ hoặc mô hình nội bộ của Billing. Khi Billing đổi schema hoặc thay đổi cách tính hóa đơn, Ordering có thể phải sửa theo.

Nếu không có kiểm tra tự động, vi phạm kiểu này thường chỉ được phát hiện khi một thay đổi lớn đã lan qua nhiều module.

### 1.2. Tài liệu kiến trúc không tự thực thi quy tắc

Một tài liệu có thể nói “Domain không phụ thuộc Infrastructure”. Nhưng compiler không biết đó là quy tắc bắt buộc nếu code không dùng cơ chế module hoặc kiểm tra tương ứng.

Architecture test đưa quy tắc vào CI. Khi một commit tạo dependency trái chiều, test thất bại và chỉ ra lớp nào phụ thuộc vào lớp nào.

### 1.3. Kiến trúc cần được bảo vệ liên tục

Trong quá trình phát triển, quyết định kiến trúc thường bị xói mòn bởi:

- Import một class nội bộ vì tiện tái sử dụng.
- Gọi thẳng implementation thay vì dùng port.
- Đưa annotation ORM vào domain model.
- Tạo dependency vòng giữa các package.
- Dùng Entity của context khác làm kiểu dữ liệu API.
- Để controller truy cập trực tiếp repository.

Kiểm thử kiến trúc biến những quy tắc này thành một phần của Definition of Done.

## 2. Architecture Test là gì?

Architecture test là kiểm thử tự động xác minh cấu trúc và quan hệ phụ thuộc của code so với các quy tắc kiến trúc đã chọn.

Nó thường phân tích:

- Package và module chứa class.
- Class nào phụ thuộc vào class nào.
- Hướng phụ thuộc giữa các layer.
- Vòng phụ thuộc giữa package hoặc slice.
- Quyền truy cập vào package nội bộ.
- Annotation, interface hoặc kiểu được dùng ở một vùng nhất định.
- Ranh giới giữa các Bounded Context.

### 2.1. Architecture Fitness Function

Một Architecture Fitness Function là phép kiểm tra có thể chạy lặp lại để đánh giá một thuộc tính kiến trúc. Ví dụ:

- Các Bounded Context không phụ thuộc vòng.
- Domain không import Spring hoặc JPA.
- Web adapter không gọi trực tiếp persistence adapter.
- Ordering không tham chiếu Billing internal model.
- Các module chỉ phụ thuộc vào API được công bố.

Một fitness function hữu ích phải có kết quả rõ ràng, có thể chạy trong pipeline và gắn với một quyết định kiến trúc có ý nghĩa.

### 2.2. Phân biệt với các loại test khác

| Loại kiểm thử | Câu hỏi chính | Ví dụ |
|---|---|---|
| Unit test | Quy tắc nhỏ có đúng không? | Order không cho submit khi chưa có dòng hàng |
| Integration test | Các thành phần thật phối hợp đúng không? | Repository lưu và tải Order đúng |
| Contract test | Hai bên hiểu cùng một hợp đồng không? | Consumer xử lý đúng schema OrderSubmitted |
| Architecture test | Cấu trúc và phụ thuộc có đúng thiết kế không? | Domain không phụ thuộc JPA |
| End-to-end test | Quy trình người dùng hoàn chỉnh có hoạt động không? | Tạo đơn, thanh toán và giao hàng |

Các loại test này bổ sung cho nhau. Một integration test thành công không chứng minh Bounded Context được tách đúng. Một architecture test thành công cũng không chứng minh nghiệp vụ tính tiền chính xác.

## 3. Chuyển quyết định DDD thành quy tắc có thể kiểm tra

Trước khi viết test, cần xác định ranh giới mà kiến trúc muốn bảo vệ. Không nên bắt đầu bằng một danh sách rule chung chung.

### 3.1. Quy tắc về layer

Một cấu trúc thường gặp:

~~~mermaid
flowchart TD
    A["Inbound Adapter<br/>REST / Message / Job"] --> B["Application<br/>Use Case"]
    B --> C["Domain<br/>Entity / Value Object / Domain Service"]
    B --> D["Ports"]
    E["Outbound Adapter<br/>JPA / Broker / HTTP"] --> D
~~~

Hướng phụ thuộc mong muốn:

- Domain chỉ phụ thuộc vào domain và các thư viện nền tảng thực sự cần thiết.
- Application có thể phụ thuộc Domain và các port mà use case sử dụng.
- Adapter có thể phụ thuộc Application contract và Domain type cần thiết.
- Domain không gọi trực tiếp database, broker hoặc HTTP client.
- Adapter không được trở thành nơi chứa quy tắc nghiệp vụ cốt lõi.

Ví dụ, interface `OrderRepository` có thể được đặt ở application hoặc domain tùy cách tổ chức dự án. Implementation JPA nằm trong persistence adapter và phụ thuộc vào interface đó. Vị trí cụ thể cần nhất quán với kiến trúc đã chọn.

### 3.2. Quy tắc về Bounded Context

Mỗi Bounded Context sở hữu mô hình và ngôn ngữ riêng. Ordering không nên import `billing.domain.Invoice` chỉ để đọc trạng thái hóa đơn.

Thay vào đó, hai context có thể phối hợp qua:

- Integration Event đã công bố.
- API/contract ổn định.
- Published Language.
- Anti-Corruption Layer để chuyển đổi mô hình ngoài.

Architecture test có thể cấm phụ thuộc vào package nội bộ của context khác, đồng thời cho phép phụ thuộc vào package contract đã công bố.

### 3.3. Quy tắc về Aggregate

Aggregate Root là điểm truy cập để thay đổi trạng thái bên trong aggregate. Nếu dự án tổ chức package theo aggregate, có thể bảo vệ package nội bộ để code bên ngoài không sửa trực tiếp Entity con.

Ví dụ:

~~~text
ordering/
  order/
    api/
      OrderId.java
      OrderSummary.java
    internal/
      Order.java
      OrderLine.java
      OrderRepository.java
~~~

Quy ước này chỉ có ý nghĩa nếu code thực sự giữ các thành phần nội bộ trong package và chỉ mở API cần thiết. Architecture test có thể phát hiện dependency vào `internal`, nhưng khả năng truy cập ở compile time nên được tăng cường bằng package visibility hoặc Java Module System khi phù hợp.

Không thể chỉ dựa vào tên package để kết luận aggregate boundary đúng. Ranh giới aggregate vẫn phải được xác định bằng invariant và quy tắc nghiệp vụ.

### 3.4. Quy tắc về domain model

Nếu dự án chọn domain model độc lập với framework, có thể đặt quy tắc:

- Domain không phụ thuộc Spring.
- Domain không phụ thuộc JPA/Hibernate.
- Domain không phụ thuộc servlet, REST hoặc message broker.
- Domain không gọi repository implementation.

Một dự án có thể cố ý dùng annotation persistence trong domain Entity. Khi đó, không nên áp dụng rule “cấm mọi JPA annotation” một cách máy móc; hãy kiểm tra đúng ranh giới đã cam kết.

## 4. Dùng ArchUnit để kiểm thử cấu trúc Java

ArchUnit là thư viện cho phép viết test kiểm tra dependency và cấu trúc của code Java. Quy tắc được viết bằng Java và có thể chạy cùng JUnit.

### 4.1. Thêm dependency

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation("com.tngtech.archunit:archunit-junit5:<version>")
}
~~~

Thay `<version>` bằng phiên bản ArchUnit đã được dự án lựa chọn và quản lý tập trung. Dự án cũng cần cấu hình JUnit 5 như các test khác.

### 4.2. Tổ chức package ví dụ

~~~text
com.acme.shop/
  ordering/
    domain/
    application/
    adapter/
      web/
      persistence/
  billing/
    domain/
    application/
    adapter/
      web/
      persistence/
  contracts/
    billing/
    ordering/
~~~

Package pattern trong ví dụ tiếp theo cần được điều chỉnh theo package thực tế của dự án.

### 4.3. Kiểm tra Domain không phụ thuộc Infrastructure

~~~java
package com.acme.shop.architecture;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

@AnalyzeClasses(
    packages = "com.acme.shop",
    importOptions = ImportOption.DoNotIncludeTests.class
)
class DomainDependencyTest {

    @ArchTest
    static final ArchRule domain_must_not_depend_on_outer_layers =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat().resideInAnyPackage(
                "..application..",
                "..adapter..",
                "..infrastructure..",
                "org.springframework..",
                "jakarta.persistence..",
                "javax.persistence.."
            );
}
~~~

Rule trên kiểm tra dependency tĩnh từ class trong package domain. Nếu một domain class import repository implementation hoặc annotation thuộc các package bị cấm, test sẽ thất bại.

`ImportOption.DoNotIncludeTests` giúp loại các class test khỏi tập được phân tích. Nếu dự án có package test fixture hoặc generated code riêng, hãy cấu hình import option phù hợp.

Các đoạn `@ArchTest` tiếp theo là những field có thể bổ sung vào một class test đã được cấu hình `@AnalyzeClasses`. Đặt các static import ở đầu file test và điều chỉnh package pattern theo dự án.

### 4.4. Kiểm tra hướng phụ thuộc giữa các layer

ArchUnit cung cấp `layeredArchitecture()` để diễn đạt quan hệ layer:

~~~java
import static com.tngtech.archunit.library.Architectures.layeredArchitecture;

@ArchTest
static final ArchRule layers_must_follow_dependency_direction =
    layeredArchitecture()
        .consideringAllDependencies()
        .layer("Domain").definedBy("..domain..")
        .layer("Application").definedBy("..application..")
        .layer("Adapters").definedBy("..adapter..", "..infrastructure..")
        .whereLayer("Domain")
            .mayOnlyBeAccessedByLayers("Application", "Adapters")
        .whereLayer("Application")
            .mayOnlyBeAccessedByLayers("Adapters")
        .whereLayer("Adapters")
            .mayNotBeAccessedByAnyLayer();
~~~

Quy tắc này mô tả dependency đi từ adapter đến application rồi đến domain. Nó kiểm tra layer nào được phép truy cập layer nào.

Để ngăn Domain tự phụ thuộc ngược ra Application/Adapter, kết hợp với rule `domain_must_not_depend_on_outer_layers` ở phần trước. Một số dự án có thêm layer hoặc package dùng chung; cần khai báo rõ thay vì bỏ qua tất cả dependency không khớp.

### 4.5. Kiểm tra package không có dependency cycle

Một dependency cycle khiến thay đổi ở module này có thể kéo theo module kia và làm ranh giới khó tách:

~~~java
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

@ArchTest
static final ArchRule bounded_context_packages_must_be_acyclic =
    slices()
        .matching("com.acme.shop.(*)..")
        .should()
        .beFreeOfCycles();
~~~

Với package pattern này, phần được đặt trong `(*)` đại diện cho slice cấp cao ngay dưới `com.acme.shop`, ví dụ `ordering`, `billing` hoặc `contracts`.

Nếu Ordering phụ thuộc Billing và Billing lại phụ thuộc Ordering, test sẽ chỉ ra chu trình. Cần xem xét lại contract hoặc hướng điều phối. Có thể một workflow application-level điều phối hai context qua event/port mà không để hai domain phụ thuộc trực tiếp vào nhau.

### 4.6. Cấm một Bounded Context truy cập phần nội bộ của context khác

Giả sử Billing công bố contract trong `billing.api` và giữ mô hình nội bộ trong `billing.domain` cùng `billing.adapter.persistence`.

~~~java
@ArchTest
static final ArchRule ordering_must_not_depend_on_billing_internals =
    noClasses()
        .that().resideInAPackage("com.acme.shop.ordering..")
        .should().dependOnClassesThat().resideInAnyPackage(
            "com.acme.shop.billing.domain..",
            "com.acme.shop.billing.application..",
            "com.acme.shop.billing.adapter.."
        );
~~~

Ordering vẫn có thể phụ thuộc vào contract đã công bố, ví dụ `com.acme.shop.billing.api..` hoặc `com.acme.shop.contracts.billing..`, tùy thiết kế. Điều quan trọng là rule chỉ cấm các package nội bộ và để lộ rõ nơi giao tiếp hợp lệ.

Không nên cho phép toàn bộ package `billing..` chỉ vì cần dùng một DTO. Làm vậy sẽ vô hiệu hóa ranh giới mà test đang muốn bảo vệ.

## 5. Kiểm thử quyền truy cập vào Aggregate và module nội bộ

### 5.1. Đóng gói package nội bộ

Nếu các thành phần nội bộ của Order được đặt trong package `ordering.order.internal`, những package khác không nên phụ thuộc trực tiếp vào chúng.

Một rule có thể giới hạn dependency:

~~~java
@ArchTest
static final ArchRule other_modules_must_not_use_order_internals =
    noClasses()
        .that().resideInAnyPackage(
            "com.acme.shop.billing..",
            "com.acme.shop.fulfillment..",
            "com.acme.shop.support.."
        )
        .should().dependOnClassesThat()
        .resideInAPackage("com.acme.shop.ordering.order.internal..");
~~~

Các consumer cần dữ liệu Order nên dùng API/read model đã công bố. Lệnh thay đổi trạng thái phải đi qua hành vi của Aggregate Root hoặc use case tương ứng.

### 5.2. Dùng ngôn ngữ Java để tăng mức bảo vệ

Architecture test là lớp bảo vệ tự động, nhưng Java visibility và module system có thể ngăn vi phạm ngay khi biên dịch:

- Để class/constructor ở package-private khi chỉ package đó được phép sử dụng.
- Chỉ public những API thực sự cần thiết.
- Dùng JPMS `exports` để công bố package và `requires` để khai báo module dependency khi dự án dùng Java Module System.
- Tách module build riêng khi Bounded Context cần ranh giới compile-time mạnh hơn.

Nếu một class nội bộ vẫn public và package được export rộng, test có thể phát hiện dependency sai nhưng compiler vẫn cho phép nó. Kết hợp nhiều lớp bảo vệ sẽ hiệu quả hơn.

### 5.3. Không ép mọi Aggregate thành một package nếu không phù hợp

Package-per-aggregate là một lựa chọn tổ chức, không phải yêu cầu bắt buộc của DDD. Có thể dùng module hoặc package theo năng lực nghiệp vụ. Chỉ viết rule khi quy ước đó phản ánh ranh giới thật của hệ thống.

## 6. Kiểm tra adapter và persistence boundary

### 6.1. Web adapter không gọi thẳng persistence adapter

Một controller nên nhận request, gọi application use case và chuyển kết quả thành response. Nó không nên tự gọi JPA repository implementation.

~~~java
@ArchTest
static final ArchRule web_adapters_must_not_access_persistence_adapters =
    noClasses()
        .that().resideInAPackage("..adapter.web..")
        .should().dependOnClassesThat()
        .resideInAPackage("..adapter.persistence..");
~~~

Rule này giúp ngăn controller bỏ qua application layer và gọi thẳng database adapter. Nếu package dự án dùng tên khác, điều chỉnh pattern tương ứng.

### 6.2. Persistence implementation phụ thuộc vào port

Application hoặc domain có thể khai báo repository port:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Persistence adapter implement port:

~~~java
public final class JpaOrderRepository implements OrderRepository {
    // Chuyển đổi giữa domain model và persistence model.
}
~~~

Kiểm thử kiến trúc có thể bảo đảm domain/application không phụ thuộc vào `JpaOrderRepository`. Nếu cần kiểm tra implementation, có thể viết rule yêu cầu các class adapter implement port hoặc nằm đúng package hạ tầng.

### 6.3. Kiểm tra ORM annotation theo lựa chọn thiết kế

Với domain model thuần Java, có thể cấm JPA annotation trong domain:

~~~java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;

import jakarta.persistence.Entity;

@ArchTest
static final ArchRule jpa_entities_must_stay_in_persistence =
    classes()
        .that().areAnnotatedWith(Entity.class)
        .should().resideInAPackage("..adapter.persistence..");
~~~

Đây là rule dành cho dự án tách persistence model khỏi domain model. Nếu domain Entity cũng là JPA Entity theo chủ đích, rule này không phù hợp và cần được thay bằng các kiểm tra khác.

## 7. Kiểm thử contract và sự cô lập giữa Bounded Context

### 7.1. Chỉ công bố kiểu dữ liệu cần thiết

Một integration contract có thể là:

~~~java
public record OrderSubmittedIntegrationEvent(
        UUID eventId,
        UUID orderId,
        Instant occurredAt,
        List<SubmittedOrderLine> lines) {
}

public record SubmittedOrderLine(
        String productCode,
        BigDecimal quantity,
        BigDecimal agreedUnitPrice,
        String currency) {
}
~~~

Billing hoặc Inventory chỉ cần những dữ liệu có ý nghĩa với use case của chúng. Không gửi toàn bộ `Order` Entity hoặc `OrderLine` nội bộ qua message broker.

### 7.2. Architecture test kiểm tra nơi đặt contract

Có thể kiểm tra contract được đặt trong package/module công khai:

~~~java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;

@ArchTest
static final ArchRule integration_events_must_live_in_contract_packages =
    classes()
        .that().haveSimpleNameEndingWith("IntegrationEvent")
        .should().resideInAPackage("..contracts..");
~~~

Rule minh họa một quy ước của dự án: Integration Event được đặt trong contract package. Nếu contract dùng schema Avro/Protobuf hoặc generated type, hãy chọn quy tắc phù hợp hơn.

Một rule khác có thể cấm consumer phụ thuộc vào domain event nội bộ:

~~~java
@ArchTest
static final ArchRule external_contexts_must_not_use_ordering_domain_events =
    noClasses()
        .that().resideInAPackage("..billing..")
        .should().dependOnClassesThat()
        .resideInAPackage("..ordering.domain.event..");
~~~

Domain Event thường phục vụ nội bộ một domain model. Integration Event là contract được công bố để context khác tiêu thụ. Phân biệt hai loại giúp tránh vô tình biến cấu trúc nội bộ thành API công khai.

### 7.3. Architecture test không thay thế contract test

Architecture test có thể kiểm tra code consumer không import kiểu nội bộ. Nó không xác minh message JSON thực tế tương thích với schema mà producer gửi.

Để kiểm tra payload và compatibility, cần contract test hoặc schema compatibility test riêng.

## 8. Kiểm tra naming convention và vị trí thành phần

Một số quy ước đặt tên có thể được kiểm tra tự động:

- Class kết thúc bằng `Controller` nằm trong web adapter.
- Class kết thúc bằng `JpaRepository` nằm trong persistence adapter.
- Application use case có suffix hoặc package rõ ràng.
- Domain Event nằm trong domain package.
- Integration Event nằm trong contract package.

Ví dụ:

~~~java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.classes;

@ArchTest
static final ArchRule controllers_must_live_in_web_adapter =
    classes()
        .that().haveSimpleNameEndingWith("Controller")
        .should().resideInAPackage("..adapter.web..");
~~~

Naming rule hữu ích khi tên phản ánh một quy ước thật. Nếu dự án dùng functional endpoint, handler hoặc tên khác, không nên ép mọi thành phần vào một suffix.

## 9. Viết test sao cho có ích và dễ bảo trì

### 9.1. Bắt đầu từ một quyết định kiến trúc quan trọng

Không cần viết hàng trăm rule ngay từ đầu. Chọn một vài ranh giới có giá trị:

1. Domain không phụ thuộc framework và infrastructure.
2. Các Bounded Context không phụ thuộc package nội bộ của nhau.
3. Package/module không có dependency cycle.
4. Adapter không bỏ qua application layer.

Khi hệ thống lớn hơn, có thể bổ sung rule cho module, aggregate package, event contract và persistence mapping.

### 9.2. Mỗi rule nên có tên mô tả ý định

Tên `rule1` hoặc `architectureTest` không giúp người đọc hiểu vi phạm. Tên như `ordering_must_not_depend_on_billing_internals` thể hiện ngay ranh giới được bảo vệ.

Thông báo test nên giúp trả lời:

- Class nào vi phạm?
- Nó phụ thuộc vào class/package nào?
- Quy tắc nào bị phá vỡ?
- Hướng sửa dự kiến là gì?

ArchUnit thường in ra dependency path cụ thể. Có thể thêm mô tả bằng `as("...")` để thông báo dễ hiểu hơn.

### 9.3. Không bỏ qua mọi dependency khó chịu

Khi một rule thất bại, đừng lập tức thêm ignore hoặc whitelist rộng. Hãy xác định:

- Dependency có thật sự cần không?
- Có thể chuyển sang port hoặc contract không?
- Package pattern có quá rộng hoặc sai không?
- Đây là vi phạm mới hay technical debt cũ?

Nếu cần ngoại lệ, giới hạn theo class và lý do rõ ràng, kèm người chịu trách nhiệm và kế hoạch loại bỏ khi phù hợp.

### 9.4. Kiểm soát phạm vi class được phân tích

`@AnalyzeClasses` chỉ phân tích class nằm trong phạm vi import và có trên test classpath. Trong dự án nhiều module, một test đặt ở module Ordering có thể không nhìn thấy bytecode của Billing nếu dependency/classpath không bao gồm nó.

Hãy xác minh:

- Package root bao phủ đủ module cần kiểm tra.
- Build test classpath có các module liên quan.
- Generated code và test fixture được loại trừ hoặc đưa vào có chủ đích.
- Rule không vô tình chỉ kiểm tra một phần code.

Một test xanh trên tập class không đầy đủ không chứng minh toàn hệ thống giữ đúng ranh giới.

## 10. Tích hợp architecture test vào CI

Architecture test nên chạy thường xuyên như unit test:

~~~mermaid
flowchart TD
    A["Developer tạo commit / Pull Request"] --> B["Compile"]
    B --> C["Unit Tests"]
    C --> D["Architecture Tests"]
    D --> E["Integration / Contract Tests"]
    E --> F["Build và báo cáo"]
    D -->|Vi phạm ranh giới| G["Fail pipeline + dependency path"]
~~~

Gợi ý triển khai:

- Đặt architecture test trong test source set của module phù hợp.
- Chạy cùng task test trong local và CI.
- Bảo đảm pull request nhận được thông báo vi phạm dễ đọc.
- Không phụ thuộc vào việc developer nhớ chạy một lệnh thủ công.
- Khi rule thay đổi, yêu cầu review quyết định kiến trúc và lý do thay đổi.

Với dự án có nhiều module, có thể có một nhóm architecture test ở cấp module và một nhóm ở cấp toàn ứng dụng. Test cấp module kiểm tra ranh giới nội bộ; test toàn ứng dụng kiểm tra dependency giữa các module.

## 11. Đưa architecture test vào hệ thống legacy

Một hệ thống cũ có thể đã có nhiều dependency cycle và package vi phạm. Nếu bật một rule quá rộng, hàng trăm lỗi xuất hiện cùng lúc khiến đội phát triển khó áp dụng.

### 11.1. Bắt đầu bằng baseline

Ghi nhận trạng thái hiện tại và xác định phạm vi vi phạm. Mục tiêu ban đầu có thể là không tạo thêm vi phạm mới.

### 11.2. Dùng ratchet

Ratchet là cách làm cho tiêu chuẩn chỉ tiến theo hướng tốt hơn:

- Giữ lại các ngoại lệ hiện có có kiểm soát.
- Không cho phép PR tạo thêm dependency cycle.
- Khi sửa một package, loại bỏ các ngoại lệ liên quan.
- Thu hẹp whitelist theo từng đợt.

Không biến baseline thành danh sách bỏ qua vĩnh viễn. Mỗi ngoại lệ cần có lý do và phạm vi cụ thể.

### 11.3. Tách theo lát cắt

Có thể ưu tiên:

1. Ngăn dependency mới từ domain vào infrastructure.
2. Chặn các context mới truy cập package nội bộ.
3. Loại bỏ dependency cycle giữa module có thay đổi thường xuyên.
4. Tách adapter khỏi application/domain.
5. Giảm dần các package dùng chung quá rộng.

Lộ trình phải dựa trên rủi ro và khả năng thay đổi của hệ thống.

## 12. Những gì architecture test không thể chứng minh

Architecture test rất hữu ích nhưng có giới hạn rõ ràng.

### 12.1. Không xác định được Bounded Context đúng về mặt nghiệp vụ

Test có thể kiểm tra package Ordering không import Billing. Nó không thể tự kết luận “Ordering” và “Billing” là hai Bounded Context đúng. Việc đó cần khám phá domain, ngôn ngữ chung, subdomain và quyền sở hữu nghiệp vụ.

### 12.2. Không chứng minh invariant của Aggregate

Một rule có thể bảo đảm mọi thay đổi Order đi qua package `order.internal`. Nó không chứng minh `Order.submit()` kiểm tra đúng điều kiện nghiệp vụ.

Invariant cần unit test/domain test và review mô hình.

### 12.3. Không chứng minh runtime behavior

Architecture test phân tích dependency tĩnh. Nó không chứng minh:

- Message broker gửi đúng event.
- Retry không tạo duplicate.
- Transaction được commit đúng thời điểm.
- Saga xử lý compensation đúng.
- HTTP call có timeout hoặc circuit breaker phù hợp.

Những hành vi này cần integration, contract, component hoặc end-to-end test.

### 12.4. Không phát hiện mọi dependency động

Reflection, service locator, cấu hình runtime, dependency injection bằng tên và truy cập tài nguyên qua string có thể không hiện ra như dependency tĩnh thông thường. Cần kiểm tra cấu hình, runtime behavior và test tích hợp khi những cơ chế này được dùng.

### 12.5. Không nên biến mọi quy ước thành luật cứng

Một số dependency là ngoại lệ có chủ đích. Ví dụ, một context có thể dùng Shared Kernel rất nhỏ hoặc một module có thể cần thư viện nền tảng. Rule quá chặt có thể làm kiến trúc khó tiến hóa.

Hãy bảo vệ những quyết định quan trọng và để lại không gian cho thay đổi có lý do.

## 13. Các sai lầm thường gặp

**Chỉ kiểm tra package name.** Tên package đúng không bảo đảm dependency đúng. Cần kiểm tra class-level dependency và hướng truy cập.

**Cấm mọi dependency giữa các module.** Một số module cần phụ thuộc vào public API hoặc contract. Hãy phân biệt API được công bố với implementation nội bộ.

**Cho phép cả package context khác để tránh test fail.** Điều này làm mất tác dụng của ranh giới. Chỉ cho phép package contract cần thiết.

**Dùng architecture test thay cho unit test.** Test cấu trúc không xác minh hành vi nghiệp vụ. Giữ test cho Entity, Value Object, Aggregate và policy.

**Bật toàn bộ rule trên legacy code mà không có lộ trình.** Nhiều lỗi cũ khiến đội phát triển mất khả năng phân biệt vi phạm mới. Dùng baseline và ratchet.

**Bỏ qua lỗi bằng whitelist rộng.** Ngoại lệ rộng trở thành cửa sau cho dependency mới. Giới hạn class, package và lý do.

**Chỉ chạy architecture test trên một module.** Dependency xuyên module có thể bị bỏ sót nếu classpath không đầy đủ. Xác minh phạm vi import.

**Coi architecture test xanh là kiến trúc hoàn hảo.** Test chỉ kiểm tra các thuộc tính đã được mô tả. Chất lượng domain model vẫn cần chuyên gia và đội phát triển đánh giá.

## 14. Quy trình xây dựng bộ architecture test

1. Vẽ các module, layer và Bounded Context hiện có.
2. Ghi rõ hướng dependency được phép và bị cấm.
3. Xác định public API/contract của từng module.
4. Chọn một số thuộc tính kiến trúc có rủi ro cao để bảo vệ trước.
5. Chọn công cụ phù hợp, ví dụ ArchUnit cho Java.
6. Viết rule có tên và thông báo lỗi diễn đạt đúng quyết định.
7. Chạy test và xác minh classpath bao phủ đủ code.
8. Tích hợp vào CI để mọi thay đổi đều được kiểm tra.
9. Với legacy, lập baseline và ratchet thay vì bỏ qua toàn bộ lỗi.
10. Review ngoại lệ và cập nhật rule khi kiến trúc thay đổi có chủ đích.

~~~mermaid
flowchart TD
    A["Quyết định kiến trúc DDD"] --> B["Diễn đạt thành dependency rule"]
    B --> C["Viết Architecture Test"]
    C --> D["Chạy trên classpath đầy đủ"]
    D --> E{"Rule pass?"}
    E -->|Không| F["Xem dependency path và sửa code hoặc rule"]
    F --> C
    E -->|Có| G["Đưa vào CI"]
    G --> H["Theo dõi vi phạm mới qua mỗi thay đổi"]
~~~

## 15. Checklist kiểm thử kiến trúc cho DDD

**Layer và dependency**

- Domain có tránh phụ thuộc vào adapter và infrastructure không?
- Application có điều phối use case qua port/hợp đồng phù hợp không?
- Web adapter có tránh gọi trực tiếp persistence adapter không?
- Có dependency cycle giữa các layer/package không?

**Bounded Context**

- Context có tránh import domain model nội bộ của context khác không?
- Integration contract có nằm ở vị trí được công bố rõ không?
- Domain Event nội bộ có bị dùng như Integration Event không?
- Các context có phụ thuộc vòng hoặc truy cập database của nhau không?

**Aggregate và module**

- Package nội bộ có được bảo vệ khỏi consumer bên ngoài không?
- Thay đổi aggregate có đi qua Aggregate Root/use case tương ứng không?
- Repository implementation có bị domain/application phụ thuộc trực tiếp không?
- Public API có được giới hạn ở những kiểu cần thiết không?

**Domain independence**

- Domain có bị rò rỉ framework annotation ngoài chủ đích không?
- ORM mapping có làm lộ persistence detail vào module khác không?
- Quy tắc nghiệp vụ có bị đặt trong adapter/controller không?

**Chất lượng bộ test**

- Rule có tên và thông báo lỗi dễ hiểu không?
- Test có chạy trong CI không?
- Classpath có bao phủ đầy đủ các module cần kiểm tra không?
- Ngoại lệ có phạm vi và lý do rõ không?
- Legacy baseline có ngăn vi phạm mới không?
- Các invariant và runtime behavior vẫn được kiểm thử bằng loại test phù hợp không?

Kiểm thử kiến trúc giúp DDD giữ được các ranh giới đã thống nhất trong suốt quá trình phát triển. Khi dependency được kiểm tra tự động, đội ngũ có thể phát hiện sớm sự xâm nhập giữa các layer, Aggregate và Bounded Context, từ đó giữ mô hình dễ hiểu và giảm chi phí thay đổi. Giá trị lớn nhất của bộ test không nằm ở số lượng rule, mà ở việc nó bảo vệ đúng những quyết định kiến trúc có ý nghĩa với nghiệp vụ.
