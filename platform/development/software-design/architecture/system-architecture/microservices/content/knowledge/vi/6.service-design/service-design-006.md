# Giới hạn phụ thuộc thư viện và mô hình miền dùng chung trong Microservices

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Thiết kế dịch vụ.
>
> **Mục tiêu:** hiểu vì sao chia sẻ thư viện và domain model có thể khiến các microservice phụ thuộc chặt chẽ; phân biệt thư viện nền tảng, hợp đồng giao tiếp và mô hình nghiệp vụ nội bộ; thiết kế dependency, versioning, contract và lớp chuyển đổi để các dịch vụ thực sự có thể thay đổi, kiểm thử và triển khai độc lập.

## 1. Vì sao “dùng chung code” trở thành một quyết định kiến trúc?

Trong một ứng dụng đơn khối, tái sử dụng class thường là lựa chọn thuận tiện. Nhiều module cùng tham chiếu một thư viện và cùng được build, kiểm thử, phát hành trong một artifact. Khi một model thay đổi, nhóm có thể sửa tất cả caller trong một lần triển khai.

Với microservices, mỗi dịch vụ có thể sở hữu mô hình dữ liệu, quy tắc nghiệp vụ và lịch phát hành khác nhau. Nếu Order Service, Payment Service và Billing Service cùng import một JAR chứa entity, enum và service interface nội bộ, một thay đổi tưởng như nhỏ có thể buộc cả ba dịch vụ nâng version, sửa mã, chạy integration test và phát hành theo một lịch chung. Hệ thống khi ấy có nhiều deployment nhưng vẫn là **một khối thay đổi liên kết chặt**.

Ví dụ một thư viện chung:

~~~text
shared-domain.jar
  ├─ CustomerEntity
  ├─ OrderEntity
  ├─ PaymentEntity
  ├─ PaymentStatus
  ├─ InventoryReservation
  ├─ CustomerRepository
  └─ BusinessRules
          |
          +--> Order Service
          +--> Payment Service
          +--> Billing Service
          +--> Notification Service
~~~

Nếu Payment cần bổ sung trạng thái AUTHORIZE_PENDING, mọi consumer phụ thuộc enum, serialization hoặc switch exhaustive có thể phải cập nhật. Một yêu cầu thay đổi chỉ thuộc Payment lại lan sang các miền nghiệp vụ khác. Nếu những service cùng dùng entity JPA, thay đổi mapping hoặc schema có thể làm hỏng cả code lẫn hành vi runtime.

Bài học không phải **“cấm mọi thư viện chung”**. Thư viện dùng chung có giá trị khi nó chứa năng lực ổn định, phi nghiệp vụ hoặc hợp đồng công khai được quản trị rõ. Mục tiêu là **khống chế phạm vi, chiều phụ thuộc, mức cam kết tương thích và vòng đời phát hành** của thứ được chia sẻ.

## 2. Ba khái niệm không nên nhập làm một

### 2.1. Shared technical library — thư viện kỹ thuật

Chứa công cụ hoặc cơ chế được nhiều service sử dụng, chẳng hạn:

- Thu thập tracing và metrics theo chuẩn thống nhất.
- Logging có cấu trúc, correlation ID và quy tắc che thông tin nhạy cảm.
- HTTP client middleware cơ bản cho timeout, retry có giới hạn và authentication.
- Bộ tiện ích serialization hoặc kiểm tra schema có phạm vi rõ.
- Cấu hình cơ bản cho OpenTelemetry, health checks hoặc xác thực token.

Một thư viện kỹ thuật tốt không tự quyết định ý nghĩa của “đơn đã thanh toán”, “khách hàng hợp lệ” hay “số hàng còn khả dụng”. Nó cũng không âm thầm gọi nhiều service khác để thực hiện chính sách nghiệp vụ. Thư viện kỹ thuật nên là **cơ chế**, còn việc áp dụng cơ chế vào domain là trách nhiệm của service sử dụng.

### 2.2. Public contract — hợp đồng giao tiếp công khai

Đây là thông tin mà **bên sở hữu API hoặc event chủ động cam kết với consumer**:

- Đường dẫn, method, request, response, HTTP status, error semantics của API.
- Schema của integration event, tên và ý nghĩa sự kiện, khóa định danh, version.
- Các định nghĩa ID, format thời gian, quy tắc idempotency và mức consistency.
- Chính sách tương thích, thời gian deprecation và cách consumer phát hiện thay đổi.

Contract có thể được mô tả bằng OpenAPI, AsyncAPI, JSON Schema, Protobuf/Avro hoặc tài liệu schema phù hợp. Một phần code DTO/client có thể được **generate** từ contract đã công bố.

Contract không phải là bản sao toàn bộ class nội bộ. Provider có quyền đổi database, entity, thuật toán và aggregate mà không làm thay đổi hợp đồng đã cam kết. Consumer chỉ cần hiểu phần **có thể quan sát và được hỗ trợ**.

### 2.3. Domain model nội bộ — mô hình nghiệp vụ của một bounded context

Domain model gồm entity, value object, aggregate, domain service, state machine, invariant và ngôn ngữ riêng trong phạm vi nghiệp vụ.

Ví dụ trong Payment:

~~~text
Payment Context
  PaymentAggregate
  PaymentAttempt
  Authorization
  Capture
  Refund
  PaymentPolicy
  PaymentRepository
~~~

Những loại này giúp Payment bảo vệ quy tắc của chính nó. Order không nên phải import PaymentAggregate để kiểm tra xem một đơn đã được thanh toán chưa. Order có thể tiêu thụ một **kết quả nghiệp vụ công khai**, ví dụ PaymentAuthorized, hoặc truy vấn một status API có nghĩa rõ.

Ranh giới an toàn được mô tả như sau:

~~~text
    Payment Service                                  Order Service
+-------------------------+                    +----------------------+
| Domain nội bộ           |                    | Domain nội bộ        |
| Aggregate, policy       |                    | Order, order state  |
| Repository, JPA entity  |                    +-----------^----------+
+------------+------------+                                |
             |                                             |
             v                                             |
+-------------------------+                    +-----------+----------+
| Adapter xuất hợp đồng   |--- API/Event ----->| Adapter/ACL tiêu thụ |
| Public DTO, schema      |                    | Mapping sang Order   |
+-------------------------+                    +----------------------+

Không có import trực tiếp từ Order vào Payment domain/persistence.
~~~

**Đường biên quan trọng:** chia sẻ *hình dạng dữ liệu công khai* có thể hợp lý; chia sẻ *mô hình và quyền ra quyết định nội bộ* thường tạo coupling nguy hiểm.

## 3. Các dạng phụ thuộc phát sinh từ thư viện chung

Chỉ nhìn danh sách dependency trong Gradle/Maven chưa đủ. Một thư viện dùng chung có thể tạo nhiều loại liên kết.

### 3.1. Compile-time coupling

Consumer import trực tiếp class, method hoặc enum từ thư viện. Provider thay đổi chữ ký method hoặc type có thể khiến consumer build không qua.

Ví dụ:

~~~java
// Shared domain model: ví dụ cần tránh
public enum PaymentStatus {
    NEW, AUTHORIZED, CAPTURED, FAILED
}
~~~

Nếu một consumer dùng switch expression liệt kê mọi trạng thái rồi thư viện thêm một giá trị, consumer có thể phải sửa dù nghiệp vụ của nó chỉ cần biết “được phép hoàn tất đơn hay chưa”. Chia sẻ enum nội bộ biến chi tiết Payment thành một cam kết mặc định với tất cả service.

### 3.2. Semantic coupling

Code vẫn compile nhưng cách hiểu dữ liệu thay đổi. Ví dụ provider đổi định nghĩa trạng thái PAID từ “đã authorize” sang “đã settle”. Dù JSON vẫn là chuỗi PAID, Order có thể chuyển trạng thái sai vì dựa vào semantics cũ.

Semantic coupling còn xuất hiện khi một field amount thay đổi từ đơn vị đồng sang đơn vị cent, một timezone bị ngầm thay đổi hoặc một giá trị null bắt đầu mang nghĩa “chưa biết” thay vì “không tồn tại”.

**Tương thích cú pháp chưa đủ**: contract phải nói rõ ý nghĩa và những bất biến mà consumer được phép dựa vào.

### 3.3. Release coupling

Khi nâng một shared JAR buộc nhiều service phát hành đồng thời, lợi ích deploy độc lập suy giảm. Có thể gây ra:

- Cửa sổ phát hành bị phụ thuộc vào nhiều team.
- Provider phải giữ tương thích với consumer chưa nâng.
- Một bản phát hành nhỏ yêu cầu test toàn hệ.
- Hệ thống khó rollback nếu một service mới đã tạo dữ liệu mà phiên bản cũ không đọc được.

### 3.4. Transitive-dependency coupling

Một thư viện chung có thể kéo theo Spring Data, JPA provider, JSON library, HTTP client, framework web và nhiều thành phần không cần thiết. Hai service dùng các phiên bản khác nhau của phụ thuộc bắc cầu có thể gặp lỗi classpath, serialization hoặc runtime.

Ví dụ một thư viện chỉ nhằm chia sẻ Money DTO nhưng lại import toàn bộ module database và auth. Khi đó một thay đổi dependency hoặc lỗ hổng bảo mật trong module không liên quan cũng lan tới những service chỉ cần một kiểu dữ liệu.

### 3.5. Data/transaction coupling ẩn

Shared entity và repository có thể dẫn đến việc nhiều service truy cập cùng một database schema, trực tiếp sửa bảng của nhau. Khi đó ranh giới sở hữu dữ liệu bị phá vỡ dù mỗi service có deployment riêng.

Một shared JPA entity không phải hợp đồng dữ liệu an toàn giữa các service. Nó chứa mapping nội bộ, lifecycle, lazy loading, cascade và assumptions về transaction mà consumer khác không nên biết.

### 3.6. Operational coupling

Một shared library có thể âm thầm tự tạo thread pool, kết nối broker, cache toàn cục, metrics với cardinality rất cao hoặc retry không giới hạn. Bản nâng version có thể làm thay đổi tải hoặc failure mode của nhiều service cùng lúc.

Đối với thư viện nền tảng, phải công bố hành vi runtime: pool, timeout, retry, resource usage, telemetry, bảo mật và khả năng tắt tính năng. “Dùng chung thư viện” còn là **chia sẻ rủi ro vận hành**.

## 4. Vì sao mô hình miền dùng chung thường nguy hiểm?

### 4.1. Cùng một từ có thể có nhiều nghĩa

Trong Domain-Driven Design, **bounded context** xác định nơi một mô hình có ngôn ngữ và quy tắc nhất quán. Một danh từ xuất hiện ở nhiều nơi không có nghĩa nó phải dùng cùng một class.

Ví dụ từ “Customer”:

| Context | Customer có ý nghĩa gì? | Thông tin trọng tâm |
| --- | --- | --- |
| CRM | Người hoặc tổ chức được chăm sóc | Liên hệ, kênh tương tác, lead status |
| Billing | Bên chịu trách nhiệm tài chính | Pháp nhân, địa chỉ xuất hóa đơn, mã thuế |
| Delivery | Bên nhận hàng thực tế | Người nhận, địa chỉ giao, hướng dẫn giao |
| Identity | Chủ thể có thể đăng nhập | Định danh, credentials, quyền truy cập |

Một UniversalCustomer với hàng chục field, validation và enum chung sẽ phải thay đổi vì rất nhiều lý do không liên quan. Mỗi context phải hiểu tất cả field, dù chỉ cần một phần nhỏ. Trường address được sửa ở CRM có thể không hợp lệ theo quy tắc Billing; việc ép dùng chung một class không giải quyết sự khác biệt ngữ nghĩa.

**Cách tốt hơn:** mỗi bounded context sở hữu mô hình riêng; trao đổi bằng identifier và các thông điệp có mục đích, rồi ánh xạ vào mô hình của chính consumer.

### 4.2. Trùng tên không đồng nghĩa trùng invariant

Product trong Catalog có thể là mô tả hiện tại. ProductSnapshot trong Order là thông tin đã dùng khi khách đặt đơn; nó không được thay đổi ngược theo mọi chỉnh sửa Catalog. InventorySku lại chứa lượng có thể bán và reservation, không nhất thiết cùng vòng đời với Product.

Nếu cả ba dùng chung ProductEntity, thay đổi mô tả từ Catalog có thể bị hiểu nhầm là thay đổi lịch sử đơn hàng, còn tính toán tồn kho có thể bị kéo vào model chỉ dành cho hiển thị.

~~~text
Catalog: ProductDetails (bản thông tin hiện tại)
       |
       +-- PublishedProductInfo --> Order: PurchasedItemSnapshot
       |
       +-- ProductReference -----> Inventory: StockItem/SKU

Dữ liệu được trao đổi theo contract.
Mỗi context quyết định cách biểu diễn nội bộ phù hợp.
~~~

### 4.3. Shared domain model có thể làm mất quyền sở hữu

Nếu Payment và Order cùng tham chiếu một class Payment và cả hai có quyền thay đổi trạng thái, “ai quyết định giao dịch thành công?” trở nên mơ hồ. Việc dùng chung class không tạo transaction phân tán và cũng không bảo đảm các bản sao đồng bộ.

Cần xác định:

- Dịch vụ nào là **source of truth**?
- Dịch vụ nào được ghi và xác nhận trạng thái?
- Dịch vụ khác được phép giữ snapshot/cache nào?
- Mức độ trễ chấp nhận là bao nhiêu?
- Khi có xung đột hoặc dữ liệu đến sai thứ tự, ai có thẩm quyền quyết định?
- Khi provider ngừng hoạt động, consumer có được quyết định thay hay chỉ được chờ?

Khi boundary ownership rõ, DTO có thể trông giống nhau nhưng vẫn đại diện cho **hai trách nhiệm khác nhau**. Một ít mapping là chi phí hợp lý để giữ tự chủ.

## 5. Nguyên tắc phân loại thứ nên và không nên chia sẻ

| Thành phần | Khuyến nghị mặc định | Lý do |
| --- | --- | --- |
| Logging/tracing primitives | Có thể dùng thư viện nền tảng nhỏ | Cơ chế lặp lại, tương đối ổn định |
| Authentication/token validation helpers | Có thể chia sẻ nếu quản trị bảo mật và version chặt | Tránh các cách triển khai bảo mật lệch chuẩn |
| HTTP client retry/timeout middleware | Có thể chia sẻ cơ chế; policy do từng service quyết định | Chính sách retry phụ thuộc idempotency của nghiệp vụ |
| OpenAPI/AsyncAPI/schema đã công bố | Nên có nguồn contract rõ, có thể generate code | Tách API công khai khỏi implementation |
| DTO public của một provider | Chia sẻ có kiểm soát hoặc generate per-provider | Consumer phải chỉ phụ thuộc đúng contract cần dùng |
| Domain entities, aggregate, repository | Không đưa vào thư viện dùng chung xuyên service | Ràng buộc owner, persistence và invariant |
| JPA entities/ORM mapping | Không dùng làm public API | Cấu trúc DB và lifecycle nội bộ bị lộ |
| Internal service interfaces | Không lấy làm contract phân tán mặc định | Interface gọi nội bộ không mô tả timeout, network failure |
| Business policies và workflow state machine | Giữ trong context có owner | Tránh nhiều nơi cùng quyết định một quy tắc |
| Common utility quá rộng | Tránh; chia nhỏ theo trách nhiệm | Dễ kéo dependency và release coupling |
| Test fixtures nội bộ | Giữ theo service; contract fixtures có thể công bố riêng | Tránh consumer phụ thuộc cấu trúc nội bộ |
| Error wire format chung | Có thể chuẩn hóa dạng envelope cơ bản | Mã lỗi, nguyên nhân và recovery vẫn thuộc API owner |
| Identifiers/Time/Currency primitives | Chỉ chia sẻ nếu ý nghĩa thực sự đồng nhất, được chuẩn hóa rõ | Cùng tên kiểu không chứng minh cùng semantics |

“Khuyến nghị mặc định” không thay thế đánh giá thực tế. Một tổ chức có thể có kernel domain dùng chung giữa **một vài bounded context hợp tác rất chặt**. Quyết định đó cần được chủ động quản trị như một ranh giới đồng sở hữu, với lịch thay đổi và cơ chế kiểm thử chung. Nếu mục tiêu là deploy độc lập, chia sẻ càng nhiều domain behavior thì chi phí phối hợp càng lớn.

## 6. Thiết kế thư viện kỹ thuật dùng chung đúng phạm vi

### 6.1. Trách nhiệm nhỏ và rành mạch

Một thư viện tốt nên giải quyết **một nhóm cơ chế**:

~~~text
platform-telemetry
  - trace propagation
  - metrics registration
  - structured log correlation

platform-http
  - cấu hình client cơ bản
  - connection pooling / deadline primitives
  - hook cho retry policy do caller chọn

platform-security
  - token parsing/verification theo chuẩn tổ chức
  - chuẩn hóa lỗi kỹ thuật
~~~

Tránh một artifact “common-core” chứa thêm CustomerEntity, OrderService, PaymentState và helper gửi email. Khi consumer chỉ muốn correlation ID mà phải kéo theo toàn bộ database stack, thư viện đang vượt ranh giới trách nhiệm.

### 6.2. Không quyết định chính sách nghiệp vụ thay consumer

Thư viện HTTP có thể hỗ trợ retry exponential backoff và jitter. Nhưng **không nên tự động retry mọi POST** vì có thể gửi yêu cầu trừ tiền hai lần. Payment Client phải quyết định khi nào được retry và idempotency key nào phải được gửi.

Thư viện cache có thể hỗ trợ TTL và invalidation API, nhưng không tự định nghĩa “tồn kho được phép cũ 30 giây”. Inventory và Order cần quyết định freshness theo invariant.

Thư viện xác thực token có thể xác minh signature, issuer, audience; nhưng chính sách “ai được hoàn tiền quá hạn mức?” thuộc Billing/Payment owner, không thuộc một utility chung không biết domain.

### 6.3. Giữ API public tối giản, implementation ẩn

Công bố interface nhỏ và những điểm mở rộng thực sự cần. Tránh export hàng loạt class nội bộ hoặc cấu hình public không ổn định. Một thư viện dễ nâng cấp khi:

- Public API nhỏ, document rõ và có chính sách tương thích.
- Default behavior thay đổi có kiểm soát.
- Dependency nặng được cô lập theo module tùy chọn.
- Không yêu cầu mỗi service cùng chọn một phiên bản framework vì một helper nhỏ.
- Có release notes, migration guide và thời hạn hỗ trợ version.
- Có tests thực tế cho behavior đã công bố, không chỉ kiểm tra class tồn tại.

### 6.4. Kiểm soát phụ thuộc bắc cầu

Trong Gradle, cần phân biệt dependency chỉ dùng nội bộ với type thực sự xuất hiện trên public API. Chỉ public API bắt buộc lộ type của một dependency mới có lý do đưa dependency đó vào API surface của library. Nếu không, giữ implementation detail ở phạm vi hẹp.

Ví dụ minh họa cho một thư viện Java:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    // Consumer không cần thấy implementation chi tiết này.
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.17.2'

    // Chỉ dùng api(...) nếu type bên dưới thật sự xuất hiện
    // trong public signatures của thư viện.
}
~~~

Version trên chỉ mang tính minh họa; dự án thực tế cần dùng bộ version được hỗ trợ và chính sách quản trị dependency. Không nên sao chép version ví dụ vào production mà bỏ qua kiểm tra tương thích và bản vá bảo mật.

**Dependency constraints/BOM/version catalog** giúp quản lý version nhất quán ở cấp tổ chức, nhưng không biến business domain thành một shared library. BOM là cách điều phối dependency nền tảng; quyền sở hữu model nghiệp vụ vẫn thuộc từng service.

## 7. Giới hạn chiều phụ thuộc giữa các service

### 7.1. Phụ thuộc contract, không phụ thuộc implementation

Thiết kế nên hướng tới:

~~~text
 Order Service
    |
    +--> Public Payment Contract (schema/DTO)
    |            ^
    |            |
    |       Payment Service
    |
    +--> Platform Telemetry

Không:
 Order Service --> PaymentServiceImpl
 Order Service --> PaymentRepository
 Order Service --> PaymentEntity
 Order Service --> PaymentInternalConfiguration
~~~

Điều này có thể thực hiện bằng cách công bố schema riêng hoặc artifact contract riêng, đồng thời giữ domain và persistence không xuất hiện trong artifact ấy.

### 7.2. Không biến monorepo thành compile-time dependency graph xuyên service

Nhiều service cùng nằm trong một repository **không buộc** phải import project Gradle của nhau. Ví dụ, Order không nên phụ thuộc trực tiếp vào module triển khai Payment chỉ để lấy một DTO.

~~~groovy
// Ví dụ cần tránh nếu payment-service là toàn bộ ứng dụng khác:
dependencies {
    implementation project(':payment-service')
}
~~~

Cách phụ thuộc này có thể kéo theo controllers, domain, repositories, configuration và dependency bắc cầu. Nó làm Order khó build độc lập và che giấu ranh giới runtime.

Phương án kiểm soát hơn:

~~~groovy
// Artifact contract nhỏ, được phát hành và version độc lập.
dependencies {
    implementation 'com.example.contracts:payment-api:2.3.1'
    implementation 'com.example.platform:telemetry:1.5.0'
}
~~~

Một lựa chọn khác là không share JAR DTO, mà generate client từ OpenAPI/Protobuf schema do Payment phát hành. Điều quan trọng không nằm ở “có JAR hay không”, mà ở **artifact đó chỉ chứa hợp đồng được hỗ trợ và có vòng đời phát hành rõ**.

### 7.3. Domain layer không phụ thuộc hạ tầng và model dịch vụ khác

Ngay trong một service, có thể thiết kế dependency direction:

~~~text
HTTP Controller / Message Consumer
          |
          v
 Application Use Case
          |
          v
 Domain Model + Domain Policies
          ^
          |
 Infrastructure Adapter (implements ports)

Integration Adapter -> External Contract -> Other Service
~~~

Domain model của Order nên làm việc bằng các khái niệm của Order, không tham chiếu thẳng DTO của Payment hoặc annotation của HTTP. Adapter nhận DTO Payment, chuyển thành một kết quả có nghĩa với Order, sau đó application service xử lý chuyển trạng thái.

Nhờ vậy thay đổi phương thức giao tiếp (REST sang message, một provider sang provider khác) không bắt buộc viết lại toàn bộ domain logic.

## 8. Ví dụ Java: shared JPA entity là một anti-pattern

Xét thiết kế không phù hợp:

~~~java
// Thư viện chung được cả Order và Payment import:
package com.example.shared.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "payments")
public class PaymentEntity {
    @Id
    private String id;
    private String orderId;
    private String status;

    // Getter/setter và mapping persistence thuộc Payment...
}
~~~

~~~java
// Trong Order Service — phụ thuộc vào implementation Payment.
package com.example.order;

import com.example.shared.domain.PaymentEntity;

public class OrderPaymentDecision {
    public boolean mayConfirm(PaymentEntity payment) {
        return "CAPTURED".equals(payment.getStatus());
    }
}
~~~

Ở đây Order biết tên bảng và kiểu entity nội bộ của Payment. Shared class chứa annotation persistence, làm consumer bị kéo gần đến cấu trúc database. Nếu Payment đổi thành nhiều payment attempts, thay đổi trạng thái hoặc tách table, Order có thể bị ảnh hưởng dù nhiệm vụ của Order không đổi.

Thiết kế tốt hơn tách contract ra khỏi domain entity.

~~~java
// Payment công bố một response DTO theo hợp đồng.
package com.example.payment.api;

import java.time.Instant;

public record PaymentDecisionResponse(
    String paymentId,
    String orderId,
    String result,
    Instant decidedAt
) {}
~~~

Đây vẫn chỉ là DTO của **public API**; nội bộ Payment có thể dùng aggregate, enum và entity khác.

~~~java
// Order sở hữu biểu diễn nghiệp vụ của riêng mình.
package com.example.order.domain;

public enum PaymentOutcome {
    APPROVED,
    DECLINED,
    UNRESOLVED
}
~~~

~~~java
// Lớp chuyển đổi nằm ở adapter của Order.
package com.example.order.integration;

import com.example.order.domain.PaymentOutcome;
import com.example.payment.api.PaymentDecisionResponse;

public final class PaymentOutcomeMapper {
    public PaymentOutcome map(PaymentDecisionResponse response) {
        return switch (response.result()) {
            case "AUTHORIZED" -> PaymentOutcome.APPROVED;
            case "DECLINED" -> PaymentOutcome.DECLINED;
            default -> PaymentOutcome.UNRESOLVED;
        };
    }
}
~~~

Ví dụ minh họa quy tắc chuyển đổi, không phải khẳng định mọi nghiệp vụ đều được xác nhận đơn sau khi AUTHORIZE; ứng dụng cần xác định điểm cam kết của mình. Cái quan trọng là Order **sở hữu quyết định nghiệp vụ của Order** và không mang enum/entity nội bộ của Payment vào domain.

Khi Payment thêm trạng thái REVIEWING, Order có thể tạm ánh xạ thành UNRESOLVED và hiển thị PENDING theo contract, trong khi các bản service mới/cũ cùng chạy. Nhưng provider vẫn phải công bố rõ các trạng thái mới và cam kết tương thích; một nhánh default không thay thế việc trao đổi về semantics.

### 8.1. Anti-corruption layer (ACL)

Trong DDD, **anti-corruption layer** là lớp bảo vệ ngôn ngữ domain của consumer khỏi mô hình external provider. Nó có thể gồm:

- Adapter HTTP/gRPC/message và schema parsing.
- Mapper từ external DTO sang đối tượng/khái niệm nội bộ.
- Chuyển đổi đơn vị tiền, timezone, identifier, trạng thái.
- Định nghĩa cách diễn giải lỗi, timeout, dữ liệu thiếu hoặc version lạ.
- Chống việc một field nội bộ của provider trở thành ràng buộc trực tiếp lên consumer.

ACL không phải một service trung gian bắt buộc phải triển khai riêng. Thường nó chỉ là **một phần code bên trong consumer**. Tạo “global mapping service” cho mọi domain có thể lại sinh thêm network coupling và điểm lỗi chung.

## 9. Contract DTO: nên chia sẻ bao nhiêu?

### 9.1. Contract nhỏ, phù hợp use case

Một public response nên thể hiện thông tin mà consumer cần và provider cam kết hỗ trợ, không serialize toàn bộ object graph của entity.

Ví dụ Order chỉ cần biết một payment có được authorize cho một order nhất định hay không, chứ không cần thông tin secret token, trạng thái nội bộ của từng gateway attempt và lịch sử retry.

~~~json
{
  "paymentId": "pay-482",
  "orderId": "ord-912",
  "decision": "AUTHORIZED",
  "decisionVersion": 4,
  "decidedAt": "2026-11-11T08:00:00Z"
}
~~~

Contract cần nêu rõ **AUTHORIZED** nghĩa gì, trong bao lâu có hiệu lực, bên nào được phép quyết định và consumer phải làm gì nếu không biết trạng thái.

### 9.2. Không cho mọi service dùng một “GlobalDomainTypes” quá lớn

Một package chứa Customer, Product, Order, Payment, Stock, Shipment và tất cả enum dưới tên global-contract thường khiến mọi service phụ thuộc cùng một version khổng lồ. Mỗi lần một provider đổi hợp đồng, những consumer không liên quan có thể nhận bản nâng bắt buộc.

Tách contract theo **provider hoặc năng lực công bố**, ví dụ:

~~~text
contracts/
  payment-api
  inventory-api
  order-events
  customer-identity-api
~~~

Consumer chỉ phụ thuộc thứ nó thật sự dùng. Contract vẫn có thể được lưu trong cùng repository để dễ quản lý, nhưng nên version/phát hành theo phạm vi thay đổi, không tự động nâng mọi service.

### 9.3. Shared DTO và schema-first: hai lựa chọn khác nhau

**Shared DTO JAR:** thuận tiện trong hệ Java đồng nhất, type-safe, build nhanh; cần kỷ luật để không đưa implementation vào artifact và tránh cập nhật phụ thuộc theo dây chuyền.

**Schema-first + generated client:** giảm lệ thuộc ngôn ngữ, có thể kiểm tra contract rõ ràng bằng OpenAPI/Protobuf/AsyncAPI; nhưng vẫn có coupling về wire protocol và semantics, đồng thời phải quản lý code generation, compatibility và toolchain.

**Manual DTO trong consumer:** giảm compile dependency vào provider library, mỗi service tự mô hình hóa dữ liệu nhận; phù hợp contract nhỏ hoặc khi muốn tránh shared artifact, nhưng cần kiểm thử để phát hiện drift.

Không có một công thức cho mọi tổ chức. Hãy chọn theo số consumer, ngôn ngữ lập trình, khả năng quản trị schema, tốc độ phát hành và chi phí đồng bộ.

## 10. Tương thích contract và tiến hóa phiên bản

### 10.1. Tương thích theo hành vi, không chỉ theo kiểu dữ liệu

Giả sử Payment đang trả:

~~~json
{
  "paymentId": "pay-482",
  "decision": "AUTHORIZED"
}
~~~

Một bản mới thêm trường tùy chọn:

~~~json
{
  "paymentId": "pay-482",
  "decision": "AUTHORIZED",
  "reasonCode": null
}
~~~

Nếu consumer được thiết kế bỏ qua field lạ và hợp đồng mới không thay đổi semantics cũ, đây có thể là additive change. Nhưng một số decoder strict sẽ từ chối field lạ: provider phải **kiểm thử bằng consumer thực tế**, không chỉ tin rằng JSON “thường” linh hoạt.

Các thay đổi dễ gây đứt gãy:

- Đổi tên/xóa field mà client cũ đang dùng.
- Đổi kiểu number thành string hoặc đổi đơn vị từ VND sang xu mà không đổi contract.
- Đổi ý nghĩa của AUTHORIZE/CAPTURE/PAID dù enum vẫn giữ nguyên.
- Thêm giá trị enum khi consumer dùng switch exhaustive không có unknown handling.
- Chuyển một field từ optional sang required đối với request cũ.
- Thay đổi idempotency, timeout semantics hoặc cách trả lỗi mà consumer phụ thuộc.
- Xóa event hoặc thay đổi khóa dùng để phân vùng message.
- Thay đổi quy tắc null, rỗng, absent mà không công bố.

**SemVer** giúp giao tiếp mức độ thay đổi của artifact khi đội tuân thủ quy ước, nhưng chỉ tăng major version không khiến consumer tự tương thích; cũng không bảo đảm semantic contract thực sự ổn định. Cần regression tests và migration plan.

### 10.2. Expand → migrate → contract

Một chiến lược tiến hóa interface:

1. **Expand:** provider hỗ trợ cả dạng cũ và mới, thêm field hoặc endpoint mới; giữ contract cũ hoạt động.
2. **Migrate:** consumer nâng để hiểu dạng mới, từng phiên bản được triển khai độc lập trong khoảng tương thích.
3. **Contract:** sau khi xác minh không còn consumer dùng dạng cũ và hết thời hạn hỗ trợ, mới gỡ field/endpoint cũ.

Áp dụng tương tự với database migration trong nội bộ provider: mở rộng schema, chuyển dữ liệu, hỗ trợ đọc/ghi trong giai đoạn trộn version rồi mới xóa cấu trúc cũ. Đừng thay đổi internal table như thể đó là hợp đồng mà mọi service cùng triển khai.

### 10.3. Versioning cho integration events

Một event công khai là **lời khai rằng một sự kiện nghiệp vụ đã xảy ra**. Consumer có thể xử lý trễ hoặc replay sau vài ngày. Vì vậy cần mô tả:

- Event ID, event type và schema/version.
- Aggregate/entity identifier, thời điểm và nguồn phát.
- Ý nghĩa từng trường và kiểu dữ liệu, timezone/đơn vị.
- Khả năng event đến trễ, đến lặp hoặc sai thứ tự.
- Cơ chế chuyển đổi event cũ khi consumer nâng version.
- Chính sách deprecation và thời gian lưu/replay.

Ví dụ:

~~~json
{
  "eventId": "evt-101",
  "eventType": "PaymentAuthorized",
  "schemaVersion": 2,
  "paymentId": "pay-482",
  "orderId": "ord-912",
  "occurredAt": "2026-11-11T08:00:00Z"
}
~~~

Không công bố toàn bộ PaymentAggregate đã serialize như một event chung cho mọi consumer. Nếu aggregate nội bộ có thêm trạng thái hoặc thay đổi mối quan hệ entity, consumer sẽ không bị buộc chỉnh sửa theo.

### 10.4. Cùng một API có thể có nhiều consumer version

Trong lúc rolling/canary deployment, provider v2 có thể phục vụ Order v1 và Order v2 cùng lúc. Do đó:

~~~text
Provider Payment v2
  ├─ Consumer Order v1
  ├─ Consumer Order v2
  └─ Consumer Billing v1
~~~

Muốn deploy độc lập, hệ thống cần kiểm tra contract với **những phiên bản consumer đang được hỗ trợ**, không chỉ với mã mới nhất ở nhánh main. Consumer-driven contract test và producer compatibility checks giúp phát hiện provider vô tình làm hỏng client đã triển khai.

## 11. Tránh dùng shared enum, exception và state machine quá rộng

### 11.1. Shared enum

Một shared enum PaymentStatus thường vô tình trở thành danh sách tất cả trạng thái nội bộ Payment. Consumer dùng tất cả giá trị trong switch và bị phụ thuộc khi provider thêm trạng thái cho một gateway mới.

Nếu contract công bố một trường decision, hãy định nghĩa **tập trạng thái được cam kết ở cấp API** và quy tắc với giá trị tương lai. Consumer nên có phản ứng an toàn với trạng thái chưa nhận biết, ví dụ UNKNOWN/PENDING, nếu nghiệp vụ cho phép.

### 11.2. Shared exception

Exception Java nội bộ của provider không truyền trực tiếp qua ranh giới HTTP/message. Chia sẻ class PaymentTimeoutException giữa service có thể khiến consumer hiểu nhầm rằng remote call tuân theo exception semantics của gọi trong tiến trình.

Hãy phân biệt:

- Lỗi network/timeout và trạng thái **không chắc request đã được xử lý hay chưa**.
- Lỗi xác thực/ủy quyền.
- Kết quả nghiệp vụ bị từ chối (ví dụ insufficient funds).
- Lỗi validation do request không hợp lệ.
- Sự cố tạm thời có thể retry an toàn theo contract.

Public error code cần document rõ; consumer chuyển nó về trạng thái nghiệp vụ riêng trong ACL.

### 11.3. Shared state machine

Một state machine của Payment có thể khác state machine của Order. Một Order ở trạng thái CONFIRMED không nhất thiết tương đương Payment ở trạng thái CAPTURED; có thể phải xét reservation và chính sách giao hàng.

Nếu dùng chung một class UniversalTransactionState cho cả hai, một thay đổi gateway payment có thể kéo theo thay đổi order lifecycle. Đúng hơn là mỗi context định nghĩa trạng thái của mình và **event/contract mô tả điều kiện để context kia chuyển trạng thái**.

## 12. Tránh shared “BusinessUtils” và shared domain service

Đôi khi nhóm tách business rules thành thư viện để tránh lặp code:

~~~text
common-business.jar
  calculateDiscount
  reserveInventory
  validateRefund
  changeOrderStatus
  verifyCustomerLimit
~~~

Thoạt nhìn có lợi vì “một nơi sửa”. Nhưng ai sở hữu chính sách? Nếu Discount thay đổi vì chiến dịch marketing và Refund vì quy tắc tài chính, hai chính sách có vòng đời khác nhau. Khi nhiều service gọi trực tiếp các hàm đó, thư viện trở thành nơi tập trung invariant mà không có owner runtime rõ.

Hướng khắc phục:

- Chính sách discount thuộc Pricing/Promotion owner; API hoặc published quote công bố kết quả.
- Refund thuộc Payment/Billing owner; bên khác gửi command theo contract.
- Inventory bảo vệ invariant số lượng; service khác không tự tính reservation.
- Các utility kỹ thuật như canonical JSON encoding hoặc trace propagation có thể chia sẻ nếu thực sự phi nghiệp vụ.

**Trùng một vài dòng adapter ở hai service có thể là sự tách biệt có chủ đích.** DRY (Don't Repeat Yourself) không nên được hiểu là “mọi đoạn code giống nhau phải dùng một JAR”. Kiến thức nghiệp vụ có owner cần một nguồn quyết định rõ; các biểu diễn khác nhau trong những bounded context có thể cùng tồn tại.

## 13. Quản trị phiên bản thư viện chung

Ngay cả khi thư viện chỉ chứa kỹ thuật, nó vẫn cần vòng đời phát hành riêng.

### 13.1. Version pinning và dependency management

Nên dùng phiên bản có thể tái lập trong mỗi service; kiểm soát cập nhật qua pull request hoặc cơ chế quản trị tương đương. Đừng để một bản common library tự động cập nhật sang hành vi mới chỉ vì pipeline resolve “latest”.

Quản trị version có thể dùng BOM, Gradle version catalog, dependency locking và công cụ kiểm tra lỗ hổng. Trách nhiệm là:

1. Biết service đang dùng version nào.
2. Biết public API và runtime behavior thay đổi gì ở version mới.
3. Có test xác nhận version mới không phá use case chính.
4. Có cách rollback/roll forward rõ.
5. Có kế hoạch vá lỗ hổng không đòi phát hành đồng loạt nếu không cần.

Đừng khóa cứng mọi service vào một phiên bản JAR chỉ để đơn giản hóa bảng dependency. Nếu các service không thể tự nâng khi contract tương thích, kiến trúc đang chịu release coupling đáng kể.

### 13.2. Nhỏ và ít dependency

Với một artifact contract thuần DTO/schema, nên tránh kéo theo database driver, servlet container, message broker runtime hoặc toàn bộ Spring application starter. Một DTO library nhẹ có thể chỉ cần các loại ngôn ngữ chuẩn và schema runtime thật sự cần.

Nếu code generation tạo ra nhiều library phụ thuộc, có thể dùng published schema làm nguồn hợp đồng và đặt generated code trong phạm vi consumer để giảm transitive dependencies.

### 13.3. Bảo mật và supply chain

Shared JAR được import rộng có mức ảnh hưởng lớn khi có bug hoặc CVE. Cần chú ý dependency inventory/SBOM, provenance của artifact, quét lỗ hổng, kiểm soát nguồn artifact, quyền publish và review thay đổi nhạy cảm.

Thư viện logging dùng chung không nên mặc định ghi token, access key, chi tiết thanh toán hoặc PII. Thư viện security phải có owner và chu kỳ vá được ưu tiên; một thư viện domain chung chứa dữ liệu nhạy cảm không tự làm việc tuân thủ dễ hơn.

### 13.4. Governance không làm mất tự chủ

Một platform team có thể cung cấp logging/tracing/CI library chuẩn, còn mỗi product team quyết định thời điểm nâng trong một khoảng hỗ trợ. Thiết kế tốt giúp **hỗ trợ nhiều version có chủ đích** và cung cấp migration guide thay vì yêu cầu toàn bộ service nâng trong cùng ngày.

Một contract quan trọng thay đổi có thể cần thông báo hoặc phối hợp với consumer. Phối hợp có kế hoạch là bình thường; dấu hiệu đáng lo là **mọi thay đổi nhỏ đều cần phối hợp dù service khác không có lý do nghiệp vụ liên quan**.

## 14. Test ranh giới dependency và contract

### 14.1. Kiểm tra dependency graph

Trong CI, có thể kiểm tra rằng một service không có dependency compile/runtime trực tiếp tới implementation module của service khác:

~~~text
Cho phép:
  order-service -> order-domain
  order-service -> payment-api-contract
  order-service -> telemetry-core

Cấm:
  order-service -> payment-service
  order-service -> payment-persistence
  order-service -> shared-jpa-all
~~~

Có thể dùng Gradle dependency insight/dependency reports hoặc script kiểm tra dependency graph. Nếu dùng monorepo, áp dụng quy tắc tương tự cho project dependencies để tránh import vô tình.

### 14.2. Kiểm tra import/package boundary

Trong Java, ArchUnit có thể phát hiện một số vi phạm package dependency. Ví dụ minh họa:

~~~java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import org.junit.jupiter.api.Test;

class OrderBoundaryTest {

    @Test
    void domainMustNotDependOnPaymentInternals() {
        JavaClasses classes =
            new ClassFileImporter().importPackages("com.example.order");

        noClasses()
            .that().resideInAPackage("..order.domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage(
                "..payment.persistence..",
                "..payment.domain.internal.."
            )
            .check(classes);
    }
}
~~~

Kiểm tra này chỉ là một lớp bảo vệ code import; nếu dependency nằm trong JSON semantics, database hoặc coordinated release, ArchUnit không thấy được. Cần kiểm soát ở nhiều tầng.

### 14.3. Contract tests

Provider cần chứng minh response, status, error và event vẫn phù hợp contract đã công bố. Consumer cần chứng minh mapper/adapter xử lý các trường hợp:

- Giá trị hợp lệ, missing/optional field và unknown enum khi contract cho phép.
- Network timeout, response mất sau commit, lỗi 4xx/5xx.
- Dữ liệu cũ/mới khi rollout trộn phiên bản.
- Event duplicate, out-of-order và replay.
- Thay đổi semantics làm ảnh hưởng hành vi, không chỉ parsing.
- Chuyển trạng thái UNKNOWN/PENDING an toàn khi chưa đủ bằng chứng.

Consumer-driven contract tests hữu ích khi provider có nhiều client. Tuy nhiên nếu chỉ chạy contract tests với phiên bản consumer mới nhất, hệ thống vẫn có thể phá những consumer cũ còn đang hoạt động.

### 14.4. Tests cho shared technical libraries

Một thư viện retry chung cần test behavior khi deadline hết, backoff, jitter, cancellation, số lần thử tối đa và điều kiện thao tác idempotent. Một thư viện serialization cần test schema/encoding/unknown fields. Một thư viện security cần test các loại token và tình huống từ chối truy cập.

Đừng chỉ kiểm tra library được build thành công; hãy xác nhận các **cam kết công khai** của nó. Với thư viện phiên bản mới, chạy ít nhất integration check tại những service chịu ảnh hưởng đáng kể.

### 14.5. Test độc lập là một thước đo ranh giới

Nếu unit/component tests của Order phải dựng Payment database và payment JPA entities thì Order có thể đang phụ thuộc quá sâu. Với contract tốt, Order có thể test domain bằng fake PaymentPort hoặc adapter stub, rồi test integration ở một tầng phù hợp.

Điều đó không loại bỏ integration/E2E tests, nhưng giảm nhu cầu dựng toàn bộ hệ thống cho mọi thay đổi nhỏ.

## 15. Tình huống thực tế: Order, Payment và Billing

Giả sử một hệ thống thương mại điện tử có ba bounded contexts:

- **Order:** vòng đời đơn hàng, giá trị đơn tại lúc chốt, trạng thái hủy/hoàn tất.
- **Payment:** yêu cầu thanh toán, authorize/capture/refund và giao tiếp gateway.
- **Billing:** xuất hóa đơn, thuế, điều chỉnh hóa đơn và nghĩa vụ tài chính.

### 15.1. Thiết kế quá phụ thuộc

~~~text
shared-commerce-model.jar
  CustomerEntity
  OrderEntity
  PaymentEntity
  InvoiceEntity
  PaymentStatusEnum
  TaxPolicy
  RefundPolicy
  RepositoryInterfaces

Order ----+
Payment --+--> shared-commerce-model.jar
Billing --+
~~~

Bài toán xuất hóa đơn thêm trạng thái ISSUED_CORRECTED có thể làm thư viện chung tăng version. Billing nâng bản mới, Payment cũng cần nâng vì cùng shared artifact, Order có thể gặp runtime mismatch dù không hề liên quan đến hóa đơn. Nếu các service dùng chung JPA entity, thay đổi database còn dễ phá coupling sâu hơn.

### 15.2. Thiết kế có owner và contract rõ

~~~text
Order Service
  Domain: OrderAggregate, OrderLineSnapshot
  Public: OrderConfirmed event

Payment Service
  Domain: PaymentAggregate, Attempt, Refund
  Public: AuthorizePayment API, PaymentAuthorized event

Billing Service
  Domain: InvoiceAggregate, TaxPolicy
  Public: IssueInvoice command, InvoiceIssued event

Nền tảng chung:
  telemetry library
  security primitives
  schema registry / contract tooling

Không có shared Order/Payment/Invoice entity.
~~~

Order nhận trạng thái payment qua public contract và cập nhật Order theo quy tắc riêng. Billing tạo Invoice từ dữ liệu có thẩm quyền hoặc immutable snapshot phù hợp contract. Payment không cần biết cách Billing tính thuế, miễn contract tích hợp được thỏa mãn.

### 15.3. Thay đổi nghiệp vụ được cô lập ra sao?

**Thay đổi 1 — Gateway thanh toán hỗ trợ nhiều payment attempts.** Payment sửa entity/aggregate nội bộ. Nếu public contract vẫn báo AUTHORIZE_PENDING, AUTHORIZED, DECLINED theo semantics ổn định, Order không cần sửa.

**Thay đổi 2 — Billing thêm chứng từ điều chỉnh.** Billing cập nhật schema và quy tắc nghiệp vụ; public event InvoiceAdjusted có thể được bổ sung theo chính sách version. Payment không cần import InvoiceAdjustmentEntity.

**Thay đổi 3 — Order hiển thị trạng thái “đang xác minh thanh toán”.** Order mapper có thể ánh xạ trạng thái PENDING từ contract; owner Order quyết định UI/status. Provider không cần viết lại internal PaymentState chỉ để dùng cùng enum với Order.

**Thay đổi 4 — Thay framework database của Payment.** Các service khác không phải nâng JPA/Hibernate dependency nếu Payment chỉ công bố API/event không có annotation persistence.

### 15.4. Phần phối hợp vẫn cần thiết

Luồng nghiệp vụ liên miền không biến mất:

~~~text
1. Order tạo đơn PENDING.
2. Order yêu cầu Payment authorize với idempotency key.
3. Payment xác nhận kết quả có bằng chứng.
4. Order chuyển trạng thái phù hợp.
5. Billing nhận sự kiện đủ điều kiện phát hành hóa đơn.
6. Notification gửi thông báo sau commit.
~~~

Các điểm cần phối hợp là contract, trạng thái PENDING/UNKNOWN, retry, outbox, idempotency và reconciliation. Khi Payment timeout nhưng đã charge thành công, Order phải truy vấn/đối soát bằng ID ổn định thay vì tự gọi lại bằng một transaction mới.

Ranh giới tốt không có nghĩa **không còn communication**; nó có nghĩa communication đi qua giao thức công khai, thuộc quyền sở hữu rõ và có hành vi lỗi được kiểm soát.

## 16. Trường hợp đặc biệt: shared kernel trong DDD

DDD có khái niệm **Shared Kernel**: một phần mô hình được hai bounded context cùng chia sẻ và đồng sở hữu. Đây là lựa chọn có thể hợp lý khi hai context hợp tác chặt chẽ, có ngữ nghĩa thực sự giống nhau và hai nhóm chấp nhận điều phối thay đổi ở phần dùng chung.

Tuy nhiên cần phân biệt:

- **Shared Kernel có chủ đích:** tập nhỏ các khái niệm/giá trị rất ổn định; các owner cùng quản trị và kiểm thử.
- **Global domain model vô tình:** mọi service import một bộ entities vì thuận tiện, không có ranh giới và governance rõ.

Nếu áp dụng Shared Kernel, hãy ghi cụ thể:

1. Nó gồm những type/quy tắc nào, tại sao không thể để riêng?
2. Những context và consumer nào được phép phụ thuộc?
3. Ai duyệt thay đổi semantics?
4. Cách xác nhận compatibility với các consumer?
5. Version và deprecation policy?
6. Khi domain tách hướng phát triển, kế hoạch tách kernel là gì?

Ví dụ một số tổ chức có thể có một mô hình định danh nghiệp vụ cốt lõi rất ổn định giữa hai subsystem. Nhưng **ngay cả Money** cũng cần thận trọng: Billing có thể cần nguyên tắc làm tròn theo luật thuế; Pricing tính khuyến mại với độ chính xác khác; Payment làm việc với đơn vị nhỏ nhất theo gateway. Cùng dùng BigDecimal và currency code chưa chắc cùng có toàn bộ semantics.

## 17. Quy trình quyết định trước khi tạo shared library

Mỗi khi ai đó đề xuất “đưa phần này vào common”, cần lần lượt hỏi:

**1. Đây là kiến thức nghiệp vụ hay cơ chế kỹ thuật?** Nếu là quyết định nghiệp vụ có owner rõ, để trong bounded context. Nếu là cơ chế phi domain, có thể chia sẻ.

**2. Có thật sự một nghĩa chung không?** Cùng tên Customer/Status/Money chưa đủ. So sánh invariant, lifecycle, đơn vị, dữ liệu và quyền quyết định.

**3. Ai có quyền thay đổi?** Nếu một thay đổi bình thường ở một team buộc nhiều team cập nhật version, library tạo release coupling. Có kế hoạch tương thích không?

**4. Consumer cần bao nhiêu phần?** Nếu chỉ dùng một DTO mà phải import cả ORM/framework/database, hãy cắt artifact nhỏ hoặc dùng schema generation.

**5. Có contract công khai thay thế được không?** Thay vì share repository/entity, dùng API/event theo ý định. Thay vì share business rules, để owner trả kết quả.

**6. Nâng version có rủi ro gì?** Chú ý transitive dependencies, behavioral defaults, deserialization, unknown values, security và rollback.

**7. Có thể lặp lại một đoạn adapter nhỏ không?** Nếu duplication chỉ là ánh xạ mỏng tại hai consumer, giữ code riêng có thể giảm coupling tổng thể.

**8. Có cách cưỡng chế ranh giới không?** Dependency rules, package/module boundaries, code review, contract tests và documentation phải chứng minh service không import implementation của nhau.

**9. Khi một service ngừng hoạt động thì sao?** Shared code không giải quyết network failure. Timeout, idempotency, partial success và stale data vẫn cần được thiết kế.

**10. Nếu một ngày tách service sang ngôn ngữ khác thì sao?** Public schema và semantics phải sống độc lập với Java JAR; nếu “hợp đồng” chỉ tồn tại dưới dạng entity JPA, ranh giới chưa đủ rõ.

Một quyết định nên được ghi trong ADR hoặc thiết kế nội bộ để người đến sau hiểu tại sao dùng chung và khi nào phải xem xét lại.

## 18. Mẫu ADR rút gọn cho shared library

~~~markdown
# ADR: Có nên dùng shared payment-contract?

Bối cảnh:
- Order cần đọc kết quả authorize từ Payment.
- Payment có domain entity, gateway adapters và state machine riêng.

Quyết định:
- Payment sở hữu OpenAPI schema cho endpoint payment decision.
- Public contract chỉ gồm paymentId, orderId, decision, decidedAt.
- Order ánh xạ response về PaymentOutcome nội bộ.
- Không chia sẻ PaymentEntity hoặc PaymentRepository.

Quy tắc dependency:
- Order được dùng generated client hoặc payment-api-contract.
- Order không được import payment-service implementation.
- Contract artifact không chứa JPA/Spring Data/database driver.

Tương thích:
- Thay đổi additive trong cửa sổ hỗ trợ, kiểm thử consumer cũ.
- Mã trạng thái mới phải có hành vi fallback và thông báo semantics.
- Breaking changes phải có kế hoạch migrate/deprecate.

Bằng chứng:
- Independent builds, contract tests, dependency scan.
- Không cần coordinated deployment cho thay đổi entity nội bộ.

Hệ quả:
- Phải duy trì adapter/mapper và contract release.
- Đổi lại giảm coupling compile-time, schema và release.
~~~

ADR không cần quá dài; quan trọng là **quyết định, ranh giới bị cấm, cách tương thích và hệ quả** được ghi rõ.

## 19. Cách cải tiến hệ đang lạm dụng shared domain model

Với hệ thống đã có shared-model.jar dùng rộng, nên tách theo từng bước có kiểm soát.

### Bước 1 — Lập bản đồ dependency hiện tại

Ghi service nào import type nào, dùng ở public API, domain, persistence hay chỉ trong tests. Phân loại type:

- Pure technical utility.
- Public contract thực sự.
- Domain model có owner.
- Persistence/framework implementation.
- Test-only fixtures.
- Shared policy chưa rõ owner.

Xác định những thay đổi gần đây khiến nhiều service phải cùng nâng thư viện và những sự cố serialization/version đã xảy ra.

### Bước 2 — Quy định data ownership và trách nhiệm

Với mỗi entity và rule quan trọng, chọn owner có thẩm quyền. PaymentEntity thuộc Payment; InvoiceEntity thuộc Billing; StockReservation thuộc Inventory. Nếu một type có nhiều owner và nhiều nghĩa khác nhau, cần tách ngôn ngữ ngay cả khi tên field giống nhau.

### Bước 3 — Công bố contract trước khi đổi consumer

Tạo API/event/schema do owner quản lý, có mô tả state và failure semantics. Nếu cần chuyển từ shared entity sang public DTO, đầu tiên provider hỗ trợ contract mới trong khi consumer cũ còn hoạt động.

### Bước 4 — Tạo ACL và bản model riêng ở consumer

Thay import entity bằng adapter/mapper, domain type nội bộ hoặc snapshot có owner rõ. Consumer không cần sửa toàn bộ code trong một lần: có thể chuyển từng use case, theo dõi trạng thái migration.

### Bước 5 — Cắt dependency theo artifact

Tách telemetry/security utilities và contract thành những artifact nhỏ. Xóa reference tới implementation module, ORM và database package khi consumer đã chuyển. Quản lý version per-service, không ép nâng tất cả cùng lúc.

### Bước 6 — Kiểm tra tương thích và triển khai theo giai đoạn

Chạy unit/component tests, contract compatibility tests, integration tests cho critical paths; triển khai provider/consumer theo thứ tự tương thích. Kiểm tra rolling versions và kết quả rollback.

### Bước 7 — Gỡ shared domain model cũ khi không còn consumer

Chỉ xóa entity/enum/utility cũ sau khi xác minh không còn consumer phụ thuộc và không còn event/dữ liệu lưu trữ cần decoder cũ. Với event replay hoặc dữ liệu dài hạn, có thể cần giữ schema cũ và cơ chế chuyển đổi lâu hơn thời gian tồn tại của code.

Quá trình này **không cần triển khai lại toàn hệ thống trong một lần**. Mục tiêu là giảm coupling theo các luồng thay đổi thường xuyên và những invariant quan trọng nhất.

## 20. Các sai lầm thường gặp

### 20.1. “Các service đều viết bằng Java, cứ dùng chung entity cho type-safe”

Type safety của compiler không đảm bảo tương thích semantically trên mạng. Shared JPA entity làm lộ schema và lifecycle, còn compile dependency cản trở phát hành độc lập. Type-safe DTO public có thể hữu ích nếu artifact chỉ là contract và có version policy.

### 20.2. “Mọi logic giống nhau phải đưa vào common theo DRY”

Hai context có thể tình cờ cùng công thức hiện tại nhưng khác chính sách thay đổi tương lai. Đưa cả hai vào common có thể khiến một sửa đổi nghiệp vụ sai cho context còn lại. Hãy chia sẻ **cơ chế thực sự chung và ổn định**, giữ quyết định nghiệp vụ tại owner.

### 20.3. “Chỉ cần SemVer là không phải phối hợp”

SemVer là tín hiệu version, không thay cho behavioral compatibility tests. Provider có thể thêm một giá trị enum mà consumer cũ không xử lý, hoặc đổi nghĩa một trạng thái dù JSON schema không đổi. Cần kiểm tra các contract đang được sử dụng thực tế.

### 20.4. “Chuyển library sang REST là hết coupling”

Một hệ có thể bỏ shared JAR nhưng tạo hàng chục sync API calls, cùng định nghĩa data model chi tiết hoặc deploy đồng loạt. Coupling chuyển từ compile-time sang network/runtime. Vẫn phải thiết kế coarse-grained business API, data ownership và failure handling.

### 20.5. “Bỏ contract artifact, copy toàn bộ DTO để tự chủ”

Copy public schema mà không có contract owner và tests có thể gây drift. Muốn tự chủ, phải có **một nguồn hợp đồng công khai**, còn consumer có thể dùng DTO/mapper riêng được kiểm tra tương thích với nguồn đó.

### 20.6. “Shared technical library không thể ảnh hưởng nghiệp vụ”

Một thư viện mặc định retry tất cả POST, đổi serialization timezone hoặc ghi log thông tin nhạy cảm có thể ảnh hưởng thẳng tới tính đúng đắn, bảo mật và chi phí vận hành. Public behavior của thư viện kỹ thuật cần được kiểm soát như một sản phẩm dùng chung.

### 20.7. “Cứ thay đổi entity là phải phát hành tất cả service”

Đó là dấu hiệu entity đã bị nâng thành contract ngầm. Việc thay đổi persistence nội bộ nên được cô lập bởi API/event public, expand–contract migration và compatibility window.

### 20.8. “Dùng chung Money/Customer/Product chắc chắn an toàn vì tên giống nhau”

Cùng identifier hoặc field không chứng minh cùng ngữ nghĩa, invariant và vòng đời. Hãy xác định bounded context và contract mapping trước khi chọn shared value object hay shared kernel.

### 20.9. “Microservice bắt buộc có một repo riêng thì mới độc lập”

Repo chung vẫn có thể duy trì module boundary, independent build và release/version rõ. Repo riêng cũng không bảo vệ được khi các service dùng chung domain JAR hoặc database. **Dependency direction và ownership quan trọng hơn số repository**.

### 20.10. “Không được có bất kỳ shared library nào”

Cấm tuyệt đối có thể khiến từng service tự viết lại cơ chế xác thực, logging, schema validation và xử lý lỗi kỹ thuật với chất lượng không đồng đều. Dùng chung có kiểm soát sẽ hữu ích khi ranh giới nhỏ, ít thay đổi và chi phí phối hợp thấp.

## 21. Bài tập thực hành

### Bài 1 — Phân loại các thành phần dùng chung

Một team đề xuất thư viện platform-common gồm:

~~~text
JwtVerifier
TraceContext
PaymentEntity
CustomerEntity
Money
CurrencyCode
HttpRetryExecutor
DiscountPolicy
PaymentStatus
ErrorEnvelope
JsonMapper
InventoryReservation
~~~

Hãy phân loại mỗi loại thành: kỹ thuật có thể chia sẻ; public contract cần quản trị; domain model giữ tại owner; loại cần phân tích thêm vì semantics tùy context. Nêu lý do dựa trên invariant, thay đổi và dependency bắc cầu.

Gợi ý: JwtVerifier và TraceContext thiên về cơ chế; PaymentEntity và InventoryReservation thiên về domain/persistence; Money, CurrencyCode, ErrorEnvelope phải kiểm tra nghĩa và phạm vi công khai trước khi kết luận.

### Bài 2 — Xử lý thay đổi không tương thích

Payment API trước đây chỉ trả AUTHORIZED hoặc DECLINED. Provider muốn bổ sung REVIEWING. Order v1 có switch expression exhaustive, Order v2 đã hỗ trợ PENDING. Hãy lập kế hoạch có thể deploy v2 provider khi Order v1 vẫn chạy:

1. Mở rộng contract nào và cách consumer cũ xử lý unknown?
2. Nếu Order v1 không thể xử lý trạng thái mới, provider có thể dùng cơ chế chuyển đổi hoặc giữ semantics cũ trong compatibility window nào?
3. Contract test phải chạy trên những version nào?
4. Khi nào được gỡ đường tương thích cũ?
5. Cần thể hiện điều gì cho người dùng nếu kết quả thanh toán chưa chắc chắn?

### Bài 3 — Refactor shared JPA entity

Order đang import PaymentEntity và kiểm tra cột status. Payment đổi từ một PaymentEntity sang PaymentAggregate gồm nhiều PaymentAttempt. Hãy đề xuất:

- Public API hoặc event đủ cho Order.
- Domain type của Order và ACL mapping.
- Quy tắc khi timeout hoặc nhận event lặp.
- Những dependency cần gỡ trong Gradle.
- Kiểm thử hợp đồng và thứ tự triển khai để không làm gián đoạn checkout.

### Bài 4 — Đánh giá một shared kernel

CRM và Billing muốn dùng chung Customer. Hãy viết hai bản model với ngữ nghĩa khác nhau, tìm phần giao nhau thực sự ổn định, rồi quyết định có cần shared kernel không. Giải thích ai là owner của địa chỉ xuất hóa đơn, địa chỉ liên hệ, định danh pháp lý và cách đổi địa chỉ theo thời gian.

### Bài 5 — Kiểm tra “independent deployment”

Giả sử một PR thay đổi internal Payment DB schema nhưng Order và Billing đều bị buộc nâng thư viện và deploy lại. Hãy tìm nguyên nhân:

- Shared entity hoặc repository?
- DTO public chứa persistence type?
- Version artifact quá rộng?
- Consumer phụ thuộc enum/state machine nội bộ?
- Contract không có compatibility window?

Đề xuất ít nhất một sửa đổi để lần thay đổi database kế tiếp **chỉ cần triển khai Payment** nếu public behavior không đổi.

## 22. Câu hỏi tự kiểm tra

1. Phân biệt shared technical library, public contract và internal domain model. Tại sao ba thứ có vòng đời khác nhau?
2. Tại sao chia sẻ một JPA entity xuyên service có thể phá vỡ data ownership?
3. Compile-time, semantic, transitive, release và runtime coupling khác nhau thế nào?
4. Vì sao Customer trong CRM không nhất thiết giống Customer trong Billing?
5. Khi nào một DTO contract JAR hữu ích, và khi nào nên dùng schema-first/generated client?
6. Vì sao shared enum nội bộ dễ làm consumer phụ thuộc vào chi tiết provider?
7. “Một thay đổi additive trong JSON chắc chắn backward compatible” đúng hay sai? Tại sao?
8. Nếu một thư viện retry tự gửi lại POST thanh toán, rủi ro là gì và policy retry thuộc ai?
9. Vì sao shared domain model không tự bảo đảm transaction giữa nhiều service?
10. Một shared kernel có chủ đích khác global-domain-model vô tình ở những điểm nào?
11. Nếu giữ mỗi service trong repo riêng nhưng tất cả cùng dùng một database schema, đã có độc lập kiến trúc chưa?
12. Contract tests có thể chứng minh điều gì và không thể thay thế kiểm thử nào?
13. Tại sao consumer cần ACL khi dùng API của service khác?
14. “Không được lặp code” có phải nguyên tắc tuyệt đối khi thiết kế microservices không?
15. Khi muốn tách shared-model.jar hiện tại, vì sao nên công bố contract và di chuyển consumer trước khi xóa model cũ?

## 23. Ghi nhớ chính

- **Thư viện dùng chung là một dependency kiến trúc**, không chỉ là tiện ích giảm số dòng code. Cần đánh giá khả năng thay đổi, nâng version và lỗi lan truyền.
- **Giữ domain entities, aggregates, repositories và invariants trong context có owner.** Đừng để một shared JAR trở thành nơi sở hữu nghiệp vụ cho toàn hệ.
- **Công bố API/event theo nhu cầu nghiệp vụ**, chỉ chia sẻ schema/DTO public có phạm vi nhỏ, version và semantics rõ. Consumer chuyển dữ liệu về model của mình qua ACL.
- **Chia sẻ cơ chế kỹ thuật thật sự ổn định** như tracing hay token verification khi có lợi ích rõ, nhưng để chính sách retry, data freshness và quyết định nghiệp vụ cho từng service.
- **Giảm cả compile-time, data, runtime, release và operational coupling.** Bỏ shared JAR mà tăng hàng chục synchronous calls chưa chắc tốt hơn.
- **Kiểm soát dependency bắc cầu, bảo mật, version pinning và contract compatibility.** Thay đổi provider nên tương thích với consumer đang vận hành trong khoảng hỗ trợ đã công bố.
- **Cho phép trùng lặp biểu diễn nhỏ khi các bounded context có nghĩa khác nhau.** Dùng chung quá mức có thể tốn kém hơn việc duy trì vài mapping/DTO riêng.
- **Một ranh giới tốt cho phép provider đổi implementation và schema nội bộ mà consumer không phải cập nhật**, miễn các cam kết public contract và semantics vẫn được giữ.
- **Đo hiệu quả bằng việc thay đổi và phát hành thực tế:** một thay đổi nội bộ của Payment có buộc Order/Billing sửa và deploy không? Nếu có, hãy truy ngược dependency và xác định ranh giới cần cải thiện.

**Câu hỏi cuối cùng:** *Nếu ngày mai một service thay toàn bộ database, framework hoặc thuật toán nội bộ nhưng không đổi kết quả công khai, các service khác có cần biết và nâng version hay không?* Câu trả lời phản ánh rất rõ chất lượng giới hạn thư viện và mô hình dùng chung.
