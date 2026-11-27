# Đánh giá static verification và runtime verification

## Mục tiêu của buổi đánh giá

Spring Modulith cung cấp hai thời điểm để kiểm tra mô hình application module:

- **Static verification** chạy trên mô hình được tạo từ mã nguồn và bytecode, thường được gọi trong test bằng **ApplicationModules.verify()**.
- **Runtime verification** kiểm tra mô hình module khi ứng dụng khởi động, thông qua hỗ trợ runtime của Spring Modulith.

Cả hai cùng bảo vệ các quy tắc kiến trúc như không có chu trình phụ thuộc giữa module, không truy cập package nội bộ của module khác và chỉ sử dụng các module được cho phép khi allowlist được khai báo.

Buổi đánh giá này giúp bạn chọn thời điểm kiểm tra phù hợp, phân tích phạm vi bảo vệ của từng cơ chế, thiết kế pipeline CI và quyết định có nên bật kiểm chứng khi ứng dụng khởi động hay không.

## Static verification kiểm tra điều gì?

Static verification thường được gọi trong một bài test kiến trúc:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**ApplicationModules.of(ShopApplication.class)** tạo mô hình module từ ứng dụng. **verify()** thực hiện các kiểm tra kiến trúc trên mô hình đó và ném exception nếu phát hiện vi phạm.

Các quy tắc mặc định quan trọng gồm:

- Không có chu trình ở cấp application module. Đồ thị phụ thuộc giữa các module phải là đồ thị có hướng không chu trình.
- Module chỉ được truy cập kiểu thuộc API package được công bố của module khác. Truy cập package nội bộ của module khác bị từ chối, ngoại trừ trường hợp module được khai báo OPEN.
- Nếu một module khai báo **allowedDependencies**, các phụ thuộc đi ra phải nằm trong danh sách module hoặc named interface được cho phép.
- Nếu jMolecules ArchUnit có trên classpath, các quy tắc kiến trúc DDD tương ứng cũng có thể được thực hiện theo cấu hình verification mặc định.

Static verification dựa trên cấu trúc mã nguồn và các tham chiếu kiểu được phân tích từ bytecode. Vì thế, nó phù hợp để phát hiện sớm một import hoặc lời gọi làm vượt ranh giới module, ngay trong quá trình phát triển và trước khi thay đổi được hợp nhất.

Cần hiểu đúng từ *static*: đây là phân tích cấu trúc phụ thuộc, không phải kiểm tra từ khóa static của Java và cũng không phải một bước kiểm tra cú pháp của compiler. Mã có thể biên dịch thành công nhưng vẫn vi phạm quy tắc module.

## Runtime verification kiểm tra điều gì?

Khi thêm **spring-modulith-runtime** vào ứng dụng, Spring Boot auto-configuration đăng ký các thành phần hỗ trợ mô hình module lúc chạy, trong đó có **RuntimeApplicationModuleVerifier**.

Ví dụ khai báo Gradle:

~~~groovy
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-runtime")
}
~~~

Ví dụ Maven:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-runtime</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Runtime verifier chỉ thực hiện kiểm chứng khi bật thuộc tính:

~~~properties
spring.modulith.runtime.verification-enabled=true
~~~

Khi được bật, Spring Modulith kiểm tra mô hình application module trong quá trình khởi động. Nếu phát hiện vi phạm, quá trình khởi động bị dừng. Nhờ vậy, một artifact triển khai có cấu trúc module không đáp ứng quy tắc đã định sẽ không tiếp tục chạy như thể kiến trúc đã hợp lệ.

Runtime verification đặc biệt hữu ích khi ứng dụng có các thành phần runtime cần mô hình module, khi có custom module detection hoặc khi nhóm muốn thêm một hàng rào kiểm tra ngay tại thời điểm ứng dụng được khởi chạy.

Tuy nhiên, runtime verification vẫn là kiểm tra mô hình cấu trúc module. Nó không phải công cụ theo dõi mọi lời gọi phương thức trong production, không đo quan hệ phụ thuộc phát sinh từ dữ liệu thực tế và không thay thế observability. Nó cũng không tự xác nhận event đã được xử lý thành công, transaction đã commit đúng hay nghiệp vụ trả về kết quả mong muốn.

## So sánh hai thời điểm kiểm chứng

| Tiêu chí | Static verification | Runtime verification |
|---|---|---|
| Thời điểm | Trong test hoặc bước kiểm tra trước khi hợp nhất | Khi ứng dụng khởi động |
| Cách gọi | ApplicationModules.verify() | spring-modulith-runtime và thuộc tính bật verification |
| Đầu vào | Mô hình được tạo từ lớp ứng dụng và bytecode có sẵn | Mô hình module được khởi tạo trong runtime của ứng dụng |
| Phản hồi | Test thất bại, CI có thể chặn thay đổi | Startup thất bại khi phát hiện vi phạm |
| Vị trí phù hợp | Máy phát triển, pull request, CI | Staging, production hoặc môi trường cần xác minh artifact khi khởi động |
| Mục đích chính | Phát hiện sớm vi phạm trong quá trình phát triển | Kiểm tra lại mô hình ở môi trường chạy ứng dụng |
| Giới hạn | Không chứng minh hành vi runtime và nghiệp vụ đúng | Không phải theo dõi động mọi tương tác hay kiểm thử nghiệp vụ |

Hai cơ chế bổ sung cho nhau. Static verification tạo phản hồi nhanh cho nhóm phát triển. Runtime verification xác nhận mô hình module được nạp ở thời điểm khởi động và có thể ngăn ứng dụng chạy khi cấu trúc không hợp lệ.

## Những quy tắc kiến trúc cần được thống nhất

Trước khi chọn cơ chế kiểm chứng, nhóm cần xác định các quy tắc mà hệ thống muốn duy trì.

### 1. Không có chu trình giữa các module

Giả sử **orders** phụ thuộc **catalog**, **catalog** phụ thuộc **pricing**, và **pricing** lại phụ thuộc **orders**. Đồ thị này tạo thành chu trình:

~~~mermaid
flowchart LR
    O["orders"] --> C["catalog"]
    C --> P["pricing"]
    P --> O
~~~

Chu trình khiến các module khó thay đổi độc lập. Static verification có thể phát hiện chu trình từ cấu trúc phụ thuộc; runtime verification có thể kiểm tra lại mô hình đó khi ứng dụng khởi động.

### 2. Chỉ truy cập API được công bố

Một module không nên truy cập repository, entity hoặc service nằm trong package nội bộ của module khác. Nếu cần chia sẻ chức năng, hãy công bố API tại package gốc hoặc named interface.

Ví dụ, **orders** có thể sử dụng **catalog::api**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog::api"
)
package com.acme.shop.orders;
~~~

Khai báo này giới hạn phụ thuộc của orders vào named interface api của catalog. Việc khai báo allowlist không tự công bố package đó; module catalog vẫn phải đánh dấu named interface tương ứng.

### 3. Chỉ phụ thuộc vào module được cho phép

Nếu module khai báo **allowedDependencies**, mọi dependency đi ra phải phù hợp với danh sách đó. Khi thêm một quan hệ mới, nhóm cần xem xét liệu quan hệ đó có phản ánh trách nhiệm nghiệp vụ hay đang làm module gắn chặt hơn.

### 4. Quy tắc DDD và quy tắc bổ sung

Nếu dự án dùng jMolecules ArchUnit, các quy tắc DDD có thể được đưa vào verification. Nhóm cũng có thể đăng ký các quy tắc kiến trúc riêng qua **VerificationOptions**.

Ví dụ, bổ sung một ArchRule vào kiểm chứng:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.VerificationOptions;

var options = VerificationOptions.defaults()
    .withAdditionalVerifications(myArchitectureRule);

ApplicationModules.of(ShopApplication.class).verify(options);
~~~

**myArchitectureRule** là một ArchUnit rule do dự án định nghĩa. Hãy giữ các quy tắc bổ sung có tên rõ ràng, có mục đích cụ thể và được review cùng thay đổi kiến trúc.

## Thiết kế pipeline kiểm chứng

Một pipeline phù hợp có thể đặt static verification ở giai đoạn test bắt buộc:

~~~mermaid
flowchart TD
    A["Developer thay đổi mã nguồn"] --> B["Compile và test"]
    B --> C["Static module verification"]
    C --> D{"Verification PASS?"}
    D -->|"Không"| E["Chặn hợp nhất và sửa vi phạm"]
    D -->|"Có"| F["Build artifact"]
    F --> G["Deploy môi trường kiểm thử"]
    G --> H["Runtime verification khi startup"]
    H --> I{"Startup PASS?"}
    I -->|"Không"| J["Dừng triển khai và điều tra"]
    I -->|"Có"| K["Tiếp tục kiểm tra tích hợp và vận hành"]
~~~

Ở bước test, bài **ModularityTests** cần được chạy trong lệnh test mặc định của dự án. Không đặt nó trong một source set hoặc task mà CI vô tình bỏ qua.

Ở bước runtime, artifact phải có **spring-modulith-runtime** trong runtime classpath và cấu hình bật verification ở môi trường cần kiểm tra. Nếu custom detection strategy được sử dụng, lớp và cấu hình của nó phải có trong production sources để runtime nạp được cùng mô hình mà nhóm đã xác minh.

Không nên xem một pipeline màu xanh là bằng chứng nếu bước static verification không thực sự được thực thi. Tương tự, runtime verification chỉ có tác dụng ở môi trường đã nạp dependency và bật thuộc tính tương ứng.

## Đánh giá việc bật runtime verification ở từng môi trường

Không phải mọi môi trường đều cần cấu hình giống nhau. Hãy chọn dựa trên mục tiêu triển khai:

| Môi trường | Static verification | Runtime verification | Lý do |
|---|---|---|---|
| Máy phát triển | Chạy thường xuyên | Tùy nhu cầu | Phản hồi nhanh khi thay đổi cấu trúc |
| CI pull request | Bắt buộc | Có thể chạy trong smoke test | Chặn vi phạm trước khi hợp nhất |
| Staging | Đã được thực hiện ở CI | Nên bật khi kiểm tra startup | Xác nhận artifact và cấu hình triển khai |
| Production | Đã được thực hiện ở CI | Bật nếu nhóm muốn startup fail-fast | Ngăn ứng dụng khởi động với mô hình module không hợp lệ |

Khi bật runtime verification trong production, hãy hiểu rằng vi phạm sẽ làm ứng dụng không khởi động thành công. Đây là hành vi bảo vệ có chủ đích. Nhóm vận hành cần có log startup và quy trình rollback hoặc khắc phục phù hợp nếu một phiên bản triển khai bị chặn.

Nếu nhóm chưa sẵn sàng để startup bị chặn, có thể bật runtime verification trước ở staging và đưa kết quả vào tiêu chí phát hành. Sau khi quy tắc và cấu hình ổn định, quyết định phạm vi bật trong production.

## Cấu hình runtime và custom module detection

Một ứng dụng có thể dùng custom **ApplicationModuleDetectionStrategy** để chọn module theo naming convention hoặc quy tắc riêng. Nếu chiến lược chỉ nằm trong **src/test/java** và đăng ký trong **src/test/resources**, static verification trong test có thể chạy đúng nhưng runtime không có lớp hoặc cấu hình đó.

Khi runtime cần cùng chiến lược:

- Đặt lớp triển khai trong **src/main/java**.
- Đặt **spring.modulith.detection-strategy** trong **src/main/resources/application.properties**.
- Đảm bảo **spring-modulith-core** có mặt ở compile classpath để biên dịch lớp chiến lược.
- Thêm **spring-modulith-runtime** ở runtime scope nếu dùng runtime support.

Ví dụ cấu hình:

~~~properties
spring.modulith.detection-strategy=com.acme.shop.architecture.BusinessModuleDetectionStrategy
spring.modulith.runtime.verification-enabled=true
~~~

Test và runtime nên dùng cùng quy tắc phát hiện module. Nếu hai môi trường chọn các package khác nhau, nhóm có thể xác minh một kiến trúc trong CI nhưng khởi chạy một mô hình khác ở production.

## Xử lý khi static và runtime cho kết quả khác nhau

Nếu static verification thành công nhưng runtime verification thất bại, hãy so sánh các đầu vào tạo mô hình:

1. Lớp ứng dụng được dùng làm điểm bắt đầu có giống nhau không?
2. Custom detection strategy có nằm trên production classpath không?
3. Cấu hình **spring.modulith.detection-strategy** có được nạp trong profile runtime không?
4. Artifact có chứa các class và package giống với source đã được kiểm tra không?
5. Phiên bản Spring Modulith và các dependency có thống nhất giữa test và runtime không?
6. Có profile hoặc cấu hình triển khai nào làm thay đổi cách phát hiện module không?

Nếu runtime verification thành công nhưng static verification không chạy trong CI, pipeline đang thiếu hàng rào kiểm tra trước khi hợp nhất. Hãy đưa test kiến trúc vào task bắt buộc và xác nhận báo cáo test thể hiện nó đã được thực thi.

Nếu cả hai đều thành công nhưng một luồng nghiệp vụ vẫn lỗi, cần kiểm tra ở lớp phù hợp: unit test, integration test, test module, test transaction, event publication hoặc observability. Không yêu cầu verification kiến trúc chứng minh những điều nằm ngoài phạm vi của nó.

## Phân tích một tình huống thiết kế

Một nhóm phát triển có ba module **orders**, **inventory** và **notifications**:

- **orders** gọi API công khai của **inventory**.
- **notifications** lắng nghe event **OrderCompleted** do **orders** công bố.
- Một thay đổi mới khiến **inventory** import **OrderRepository** từ package nội bộ của **orders**.

Trong quá trình review, static verification phát hiện inventory đang truy cập package nội bộ. Nhóm sửa code để dùng API hoặc event contract được công bố, sau đó test kiến trúc chạy thành công.

Khi deploy staging, runtime verification cũng chạy thành công. Kết quả này cho thấy mô hình module được nạp trong artifact triển khai đáp ứng các quy tắc cấu trúc đã khai báo.

Tuy nhiên, nhóm vẫn cần test tích hợp để xác nhận:
- API inventory trả về kết quả đúng khi đơn hàng có nhiều mặt hàng.
- Listener notifications xử lý event đúng thời điểm.
- Event publication được hoàn tất hoặc retry theo cấu hình.
- Lỗi gửi thông báo không làm sai trạng thái đơn hàng.

Static và runtime verification xác nhận cấu trúc module. Các test và công cụ vận hành còn lại xác nhận hành vi ứng dụng.

## Checklist cho buổi design review

Khi review một thay đổi kiến trúc, hãy trả lời các câu hỏi sau:

**Về quy tắc**
- Các module có tạo thành đồ thị không chu trình không?
- Consumer chỉ sử dụng API công khai hoặc named interface đã công bố không?
- **allowedDependencies** có giới hạn đúng các dependency cần thiết không?
- Có quy tắc DDD hoặc quy tắc kiến trúc bổ sung nào cần chạy không?

**Về static verification**
- Test gọi **ApplicationModules.verify()** có tồn tại không?
- Test có được chạy trong pipeline CI bắt buộc không?
- Báo cáo CI có thể hiện rõ kết quả kiểm chứng không?
- Các vi phạm mới có được sửa tại nguyên nhân không?

**Về runtime verification**
- **spring-modulith-runtime** có trong runtime classpath không?
- **spring.modulith.runtime.verification-enabled** có được bật ở môi trường dự kiến không?
- Custom detection strategy có mặt trong production sources không?
- Nhóm vận hành đã hiểu startup sẽ thất bại khi phát hiện vi phạm chưa?

**Về phạm vi**
- Có test module hoặc integration test cho luồng liên module quan trọng không?
- Có test riêng cho event, transaction và persistence không?
- Có log và observability đủ để điều tra khi startup hoặc luồng nghiệp vụ thất bại không?

## Bài tập vận dụng

Một ứng dụng Spring Boot đã có test sau:

~~~java
@Test
void verifiesModuleStructure() {
    ApplicationModules.of(ShopApplication.class).verify();
}
~~~

Nhóm muốn thêm runtime verification ở staging và production. Ứng dụng đang dùng custom detection strategy trong test source set.

Hãy xây dựng quyết định thiết kế:

1. Xác định những quy tắc static verification hiện đang bảo vệ.
2. Đưa custom detection strategy và cấu hình đăng ký vào production sources nếu runtime cần dùng.
3. Thêm **spring-modulith-runtime** vào runtime classpath.
4. Bật **spring.modulith.runtime.verification-enabled=true** ở staging.
5. Xác nhận staging startup thành công với artifact đã build.
6. Thảo luận rủi ro vận hành nếu production startup bị dừng vì vi phạm kiến trúc.
7. Giữ static verification trong CI và bổ sung integration test cho event/API quan trọng.
8. Quyết định bật runtime verification trong production dựa trên khả năng xử lý startup failure và rollback.

Kết quả mong đợi: nhóm có quyết định rõ về phạm vi static và runtime verification, hiểu rằng hai cơ chế kiểm tra cùng mô hình module ở hai thời điểm khác nhau, và không dùng runtime verification thay cho test hành vi hoặc giám sát vận hành.

## Tiêu chí hoàn tất

Bạn đã nắm được chủ đề khi có thể:

- Giải thích các quy tắc mà **ApplicationModules.verify()** kiểm tra.
- Phân biệt static verification trong test/CI với runtime verification khi ứng dụng khởi động.
- Cấu hình **spring-modulith-runtime** và **spring.modulith.runtime.verification-enabled**.
- Giải thích vì sao custom module detection cần có trong production sources nếu runtime sử dụng.
- Đánh giá tác động của startup failure và chọn môi trường bật runtime verification.
- Xác định những hành vi vẫn cần unit test, integration test, test module và observability kiểm tra riêng.

Tài liệu tham khảo:

- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Runtime Support](https://docs.spring.io/spring-modulith/reference/runtime.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [RuntimeApplicationModuleVerifier API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/runtime/autoconfigure/SpringModulithRuntimeAutoConfiguration.RuntimeApplicationModuleVerifier.html)
