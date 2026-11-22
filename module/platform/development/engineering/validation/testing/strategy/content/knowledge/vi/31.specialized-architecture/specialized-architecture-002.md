# Thiết kế chiến lược cho ứng dụng Spring Boot nguyên khối

## 1. Đặc điểm kiến trúc và mục tiêu kiểm thử

Ứng dụng Spring Boot nguyên khối (monolithic application) thường được đóng gói và triển khai như một đơn vị, chạy trong một tiến trình ứng dụng hoặc một nhóm instance giống nhau. Các chức năng nghiệp vụ có thể được tổ chức thành package, layer hoặc module bên trong cùng codebase. Chúng thường gọi nhau trực tiếp trong cùng tiến trình và có thể dùng chung cơ sở dữ liệu, transaction manager, cấu hình và vòng đời triển khai.

Đặc điểm này ảnh hưởng trực tiếp tới chiến lược kiểm thử:

- Một thay đổi trong module có thể tác động tới module khác thông qua lời gọi Java, sự kiện nội bộ, transaction hoặc dữ liệu dùng chung.
- Có thể kiểm thử nhiều thành phần trong một tiến trình mà không cần dựng mạng lưới dịch vụ phân tán.
- Ranh giới giữa các module vẫn cần được kiểm tra, dù chúng không phải dịch vụ độc lập.
- Một lỗi ở cấu hình, dependency injection, migration hoặc khởi động ứng dụng có thể ảnh hưởng toàn bộ artifact.
- Kiểm thử với cơ sở dữ liệu thật và các hệ thống bên ngoài vẫn cần thiết để phát hiện khác biệt giữa môi trường kiểm thử và production.

Chiến lược kiểm thử cho ứng dụng nguyên khối vì vậy phải bao phủ cả hành vi bên trong từng module, cách các module phối hợp và khả năng vận hành của toàn bộ ứng dụng. Mục tiêu không phải chạy mọi test ở mức toàn ứng dụng. Hãy chọn đúng mức kiểm thử cho từng rủi ro để có phản hồi nhanh, kết quả đáng tin cậy và chi phí bảo trì hợp lý.

Trong phạm vi module VALIDATION_TESTING_STRATEGY, bài học này tập trung vào cách chuyển đặc điểm của ứng dụng Spring Boot nguyên khối thành lựa chọn kiểm thử, tiêu chí chất lượng và cổng kiểm soát phát hành.

## 2. Bắt đầu từ cấu trúc và luồng phụ thuộc

Trước khi chọn test, cần hiểu ứng dụng được chia thành những phần nào và dữ liệu đi qua hệ thống ra sao. Một cấu trúc thường gặp có thể gồm:

~~~text
com.example.shop
  customer
    api
    application
    domain
    infrastructure
  order
    api
    application
    domain
    infrastructure
  payment
    api
    application
    domain
    infrastructure
  shared
  configuration
~~~

Tên package chỉ là ví dụ. Một dự án có thể dùng cấu trúc layer chung hoặc package theo tính năng. Điều quan trọng là xác định:

1. **Ranh giới nghiệp vụ:** module nào sở hữu quy tắc và dữ liệu của từng nghiệp vụ.
2. **Điểm vào:** REST controller, MVC controller, scheduled job, message listener, command line runner hoặc giao diện khác.
3. **Luồng xử lý:** controller gọi application service nào, domain logic nào được thực hiện và repository nào đọc/ghi dữ liệu.
4. **Ranh giới tích hợp:** lời gọi tới module khác, email, thanh toán, lưu trữ, message broker hoặc API bên ngoài.
5. **Ranh giới transaction:** thao tác nào phải nguyên tử, transaction bắt đầu ở đâu và sự kiện nào được phát sau commit.
6. **Tài nguyên dùng chung:** bảng dữ liệu, cache, thread pool, cấu hình và bean được nhiều module sử dụng.

Có thể lập sơ đồ phụ thuộc ở mức module trước khi lập kế hoạch:

~~~mermaid
flowchart TD
    API["REST / MVC / Job / Listener"] --> APP["Application services"]
    APP --> DOMAIN["Domain model and rules"]
    APP --> REPO["Repository interfaces"]
    REPO --> DB["Database"]
    APP --> PORT["Integration ports"]
    PORT --> EXT["External systems"]
    DOMAIN --> SHARED["Shared value types and policies"]
~~~

Sơ đồ này giúp nhận diện các vị trí nên kiểm thử độc lập và các đường đi cần kiểm thử tích hợp. Ví dụ, quy tắc tính chiết khấu thuộc domain có thể kiểm thử nhanh bằng unit test; việc lưu đơn hàng cần kiểm thử repository với database; luồng tạo đơn từ HTTP tới database cần một số integration test hoặc end-to-end test.

Nếu ứng dụng có module boundaries rõ ràng, hãy ghi lại quy tắc phụ thuộc giữa chúng. Ví dụ, module order có thể gọi public API của customer nhưng không truy cập trực tiếp package repository nội bộ của customer. Những quy tắc này có thể được xác minh tự động bằng kiểm thử kiến trúc.

## 3. Lập hồ sơ rủi ro phù hợp với monolith

Không nên suy ra rằng ứng dụng nguyên khối có rủi ro thấp vì mọi thành phần chạy cùng tiến trình. Rủi ro thường tập trung ở transaction, dữ liệu dùng chung, cấu hình toàn cục, dependency injection, migration và những module có nhiều luồng gọi chéo.

Hãy phân tích thay đổi theo các nhóm sau:

| Khu vực | Rủi ro điển hình | Câu hỏi kiểm thử |
|---|---|---|
| Quy tắc domain | Tính toán sai, vi phạm invariant hoặc xử lý sai biên | Kết quả đúng với dữ liệu biên và tổ hợp điều kiện chưa? |
| Giao tiếp giữa module | Module gọi nhầm API nội bộ hoặc truyền dữ liệu không nhất quán | Hợp đồng và luồng phối hợp có được giữ đúng? |
| Transaction | Ghi một phần, rollback không như mong đợi, sự kiện phát sai thời điểm | Khi một bước lỗi, dữ liệu và side effect có nhất quán? |
| Persistence | Query, mapping hoặc migration sai | Hành vi có đúng với database thực tế và schema mới? |
| Spring configuration | Bean thiếu, bean xung đột, profile hoặc property sai | Context có khởi động với cấu hình của môi trường đích? |
| Tích hợp ngoài | Timeout, lỗi xác thực, phản hồi không hợp lệ | Ứng dụng có xử lý lỗi và retry đúng chính sách? |
| Xử lý nền | Job chạy trùng, listener mất sự kiện hoặc chạy sai thứ tự | Tác vụ có an toàn khi retry và có thể quan sát? |
| Hiệu năng | Query N+1, lock contention, pool cạn | Luồng quan trọng có đáp ứng mục tiêu tải? |
| Bảo mật | Thiếu phân quyền, lộ dữ liệu hoặc cấu hình sai | Người dùng chỉ truy cập được dữ liệu được phép? |

Đánh giá rủi ro nên tính cả khả năng xảy ra và mức độ ảnh hưởng. Ưu tiên test sâu cho luồng thanh toán, phân quyền, dữ liệu tài chính, migration và thao tác không thể hoàn tác. Một thay đổi ở package dùng chung hoặc cấu hình Spring có thể cần kiểm tra rộng hơn thay đổi cô lập trong một module.

Đầu ra của bước này là danh sách rủi ro có chủ sở hữu, mức độ ưu tiên, biện pháp kiểm soát và bằng chứng cần thu thập. Danh sách đó là căn cứ chọn test suite và tiêu chí phát hành.

## 4. Phân tầng kiểm thử cho ứng dụng Spring Boot

Một chiến lược cân bằng thường kết hợp nhiều mức kiểm thử. Các mức không phải những hộp tách biệt tuyệt đối; hãy chọn mức thấp nhất vẫn xác minh được rủi ro cần kiểm soát.

| Mức kiểm thử | Phạm vi | Khi nên dùng | Đặc điểm |
|---|---|---|---|
| Unit test | Một class hoặc một nhóm logic nhỏ | Quy tắc domain, validation, tính toán, quyết định nghiệp vụ | Chạy nhanh, ít phụ thuộc Spring và hạ tầng |
| Module/service test | Một luồng application service và các cộng tác viên được kiểm soát | Điều phối nghiệp vụ trong một module | Xác minh lời gọi, transaction intent và kết quả phối hợp |
| Spring slice test | Một lát cắt như MVC, JPA, JSON hoặc client | Mapping HTTP, repository, serialization, cấu hình một tầng | Nạp một phần ApplicationContext |
| Integration test | Nhiều thành phần thật cùng hoạt động | Repository với DB, transaction, event, tích hợp nội bộ | Có thể dùng Spring context và phụ thuộc thật |
| End-to-end test | Luồng từ điểm vào tới kết quả nghiệp vụ | Các hành trình quan trọng, rủi ro liên module | Gần thực tế nhưng chậm và cần quản lý dữ liệu |
| Architecture test | Quy tắc phụ thuộc và cấu trúc module | Ngăn package phụ thuộc sai hoặc tạo vòng lặp | Chạy nhanh, bảo vệ cấu trúc lâu dài |
| Operational/performance test | Toàn ứng dụng trong điều kiện vận hành | Khởi động, tải, quan sát, phục hồi và triển khai | Thường chạy ở pipeline hoặc môi trường chuyên biệt |

Không có tỷ lệ cố định phù hợp cho mọi dự án. Thông thường, phần lớn trường hợp nên được kiểm tra ở mức unit và module; số lượng slice/integration test đủ để xác minh framework và hạ tầng; chỉ một tập nhỏ end-to-end test bảo vệ các hành trình có giá trị cao. Tỷ lệ cụ thể phải dựa trên chi phí, rủi ro và lịch sử lỗi của sản phẩm.

### 4.1. Unit test cho quy tắc nghiệp vụ

Unit test phù hợp với logic thuần Java không cần khởi động Spring. Ví dụ: tính phí, xác định trạng thái đơn, kiểm tra hạn mức, chọn chính sách hoặc quyết định có cho phép chuyển trạng thái hay không.

~~~java
class ShippingFeePolicyTest {

    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void appliesFreeShippingAtConfiguredThreshold() {
        Money orderTotal = Money.of("500000", "VND");

        Money fee = policy.calculate(orderTotal, Zone.CENTRAL);

        assertThat(fee).isEqualTo(Money.zero("VND"));
    }
}
~~~

Ví dụ chỉ minh họa cách đặt test; kiểu dữ liệu và chính sách thực tế phụ thuộc domain của ứng dụng. Test nên mô tả điều kiện, hành động và kết quả mong đợi. Bao phủ giá trị biên, dữ liệu không hợp lệ, trạng thái không thể chuyển và các trường hợp lỗi quan trọng. Không cần dùng Mockito nếu logic không có cộng tác viên bên ngoài.

### 4.2. Kiểm thử service và phối hợp module

Application service thường điều phối repository, domain service và cổng tích hợp. Có thể kiểm tra nó bằng unit test với cộng tác viên giả lập khi mục tiêu là xác minh nhánh điều phối, thứ tự gọi hoặc phản ứng với lỗi.

Tuy nhiên, không nên mock toàn bộ module lân cận trong mọi test. Nếu tất cả tương tác đều được thay bằng mock, test chỉ xác minh giả định của người viết test mà không phát hiện hợp đồng giữa các module bị phá vỡ. Chọn một số integration test để kiểm tra các module phối hợp thật qua public API của chúng.

### 4.3. Spring slice test

Spring Boot cung cấp các test slice để chỉ nạp phần ApplicationContext cần thiết:

- `@WebMvcTest` tập trung vào MVC layer, controller, binding, validation, serialization và security filter được cấu hình trong lát cắt.
- `@DataJpaTest` tập trung vào entity mapping, repository, query và cấu hình JPA.
- `@JsonTest` tập trung vào serialization/deserialization.
- Các slice khác có thể được dùng cho client hoặc thành phần cụ thể tùy phiên bản Spring Boot và kiến trúc dự án.

Slice test thường nhanh và dễ chẩn đoán hơn việc khởi động toàn ứng dụng. Tuy vậy, chúng không chứng minh mọi bean hoặc cấu hình toàn cục hoạt động cùng nhau. Cần có integration test bổ sung cho các rủi ro liên quan tới cấu hình tổng thể.

### 4.4. Integration test với Spring context

Dùng `@SpringBootTest` khi cần kiểm tra nhiều bean được wiring như ứng dụng thật, transaction, cấu hình hoặc luồng đi qua nhiều tầng. Chỉ chọn những trường hợp có giá trị; nếu mọi test đều khởi động toàn context, thời gian build và chi phí bảo trì sẽ tăng nhanh.

Với kiểm thử HTTP qua server thật, có thể dùng `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` kết hợp HTTP client phù hợp. Với kiểm tra controller mà không cần socket thật, `@WebMvcTest` và MockMvc thường đủ.

## 5. Kiểm thử persistence, transaction và migration

Database thường là ranh giới quan trọng của ứng dụng nguyên khối. Dùng database thay thế trong unit test có thể hữu ích, nhưng không đủ để chứng minh query, kiểu dữ liệu, constraint, isolation và migration tương thích với database production.

Chiến lược persistence nên gồm:

- Unit test cho quy tắc nghiệp vụ trước khi truy cập repository.
- Slice test cho mapping, derived query, JPQL/native query và quy tắc repository.
- Integration test với cùng họ database hoặc phiên bản tương thích với production.
- Kiểm thử migration từ schema đang tồn tại tới schema mới, có dữ liệu đại diện.
- Kiểm tra constraint, index, locking và transaction ở những luồng có rủi ro cao.

Testcontainers có thể khởi chạy database thật trong container cho integration test. Ví dụ, nếu production sử dụng PostgreSQL, hãy ưu tiên kiểm thử repository và migration với PostgreSQL tương thích thay vì chỉ dựa vào H2. Cách cấu hình container và kết nối phụ thuộc phiên bản Spring Boot; các phiên bản mới hỗ trợ cơ chế service connection, trong khi dự án cũ có thể cần cấu hình property động.

### 5.1. Những điểm cần kiểm tra về transaction

Với một nghiệp vụ ghi nhiều bảng, hãy xác minh cả trường hợp thành công và thất bại:

1. Khi mọi bước thành công, dữ liệu liên quan được commit đầy đủ.
2. Khi một bước trong transaction lỗi, dữ liệu phải rollback theo đúng ranh giới đã thiết kế.
3. Lỗi từ dịch vụ ngoài không khiến trạng thái nội bộ rơi vào trạng thái không nhất quán.
4. Sự kiện chỉ được phát ở thời điểm phù hợp với transaction; nếu dùng outbox, kiểm tra bản ghi outbox và quá trình phát sự kiện.
5. Retry không tạo bản ghi hoặc side effect trùng lặp khi nghiệp vụ yêu cầu idempotency.

`@DataJpaTest` thường chạy trong transaction do test quản lý và rollback sau mỗi test. Cơ chế này tiện để cô lập dữ liệu, nhưng không mô phỏng đầy đủ mọi hành vi commit, transaction propagation hoặc xử lý bất đồng bộ. Với test đi qua HTTP server thật, request thường chạy ở thread và transaction riêng; transaction của test không tự động bao bọc request đó. Hãy dọn dữ liệu rõ ràng hoặc dùng database/schema riêng cho test.

### 5.2. Kiểm thử migration

Migration cần được kiểm tra trên trạng thái dữ liệu gần với production:

- Tạo schema từ phiên bản cũ và nạp dữ liệu đại diện.
- Chạy toàn bộ migration theo đúng thứ tự.
- Xác minh dữ liệu cũ được giữ, chuyển đổi hoặc loại bỏ theo yêu cầu.
- Kiểm tra unique constraint, foreign key, index và default value.
- Khởi động ứng dụng với schema mới và thực hiện các thao tác đọc/ghi quan trọng.
- Đánh giá khả năng tương thích giữa phiên bản ứng dụng cũ và schema mới nếu triển khai rolling hoặc cần rollback.

Không chỉ kiểm tra migration trên database rỗng. Những lỗi nghiêm trọng thường xuất hiện khi dữ liệu cũ có giá trị null, trùng lặp, định dạng bất thường hoặc khối lượng lớn.

## 6. Kiểm thử ranh giới module và kiến trúc

Ứng dụng nguyên khối có thể phát triển thành một codebase khó thay đổi nếu các module truy cập trực tiếp package nội bộ của nhau hoặc hình thành vòng phụ thuộc. Kiểm thử kiến trúc giúp biến quy ước thiết kế thành quy tắc có thể thực thi.

Các quy tắc thường gặp:

- Controller chỉ phụ thuộc application service hoặc public interface được cho phép.
- Domain không phụ thuộc Spring MVC, persistence adapter hoặc framework web.
- Module không truy cập repository nội bộ của module khác.
- Không có vòng phụ thuộc giữa các module nghiệp vụ.
- Các class trong package internal không được tham chiếu từ bên ngoài module.
- Thành phần shared không trở thành nơi tập trung mọi logic nghiệp vụ.

Có thể dùng ArchUnit để kiểm tra package và dependency. Ví dụ khái quát:

~~~java
@AnalyzeClasses(packages = "com.example.shop")
class ModuleDependencyTest {

    @ArchTest
    static final ArchRule domainMustNotDependOnWeb =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAPackage("..api..");
}
~~~

Tên package và quy tắc cần được điều chỉnh theo cấu trúc thực tế. Hãy bắt đầu với một số quy tắc quan trọng và dễ hiểu. Nếu quy tắc quá phức tạp hoặc không phản ánh kiến trúc đã thống nhất, nhóm sẽ có xu hướng vô hiệu hóa nó.

Một kiểm thử kiến trúc tốt phát hiện vi phạm sớm trong pull request, kèm thông báo chỉ ra dependency sai. Nó không thay thế review thiết kế, nhưng giúp các ranh giới đã thống nhất không bị phá vỡ âm thầm.

## 7. Kiểm thử tích hợp bên ngoài và xử lý lỗi

Dù là monolith, ứng dụng thường gọi tới payment gateway, email provider, object storage, identity provider hoặc message broker. Không nên phụ thuộc vào dịch vụ thật trong phần lớn test tự động vì độ trễ, dữ liệu và trạng thái bên ngoài khó kiểm soát.

Chọn cách kiểm tra theo mục tiêu:

| Mục tiêu | Cách tiếp cận |
|---|---|
| Kiểm tra logic khi đối tác trả thành công hoặc lỗi | Mock client/port trong unit test |
| Kiểm tra request, response mapping và timeout | Stub HTTP bằng WireMock hoặc MockWebServer |
| Kiểm tra broker hoặc database tương thích | Dùng container hoặc môi trường tích hợp cô lập |
| Kiểm tra hợp đồng API | Contract test với schema hoặc contract được chia sẻ |
| Xác nhận khả năng tương tác thật | Một số test ở môi trường tích hợp/staging có kiểm soát |

Với mỗi tích hợp quan trọng, cần kiểm tra timeout, retry có giới hạn, circuit breaker nếu có, phản hồi không hợp lệ, lỗi xác thực và trạng thái đối tác không sẵn sàng. Retry phải tôn trọng idempotency; không retry mù quáng thao tác có thể tạo giao dịch trùng.

Test phải xác minh cách ứng dụng chuyển lỗi ngoài thành kết quả nghiệp vụ. Ví dụ, khi payment gateway timeout, đơn hàng không được tự động đánh dấu đã thanh toán. Nếu kết quả giao dịch không rõ ràng, ứng dụng cần quy trình truy vấn hoặc đối soát phù hợp.

## 8. Kiểm thử web, bảo mật và xử lý bất đồng bộ

### 8.1. Luồng web và phân quyền

Với REST API hoặc MVC, kiểm tra:

- Request hợp lệ và không hợp lệ, validation và error response.
- Authentication và authorization ở từng vai trò.
- Người dùng không thể đọc hoặc sửa dữ liệu thuộc người dùng khác.
- Mapping giữa DTO và domain không làm mất hoặc lộ trường nhạy cảm.
- Pagination, sorting, filtering và các giới hạn đầu vào.
- Hợp đồng API và tính tương thích của response.

Một test controller chỉ xác minh status code có thể bỏ sót lỗi phân quyền hoặc dữ liệu trả về sai. Với endpoint nhạy cảm, cần assertion về danh tính, quyền và nội dung dữ liệu.

### 8.2. Job, event và xử lý nền

Ứng dụng nguyên khối có thể dùng scheduler, @Async, application event hoặc message listener. Những luồng này cần kiểm thử riêng vì kết quả có thể xuất hiện sau khi request kết thúc.

- Xác minh job chỉ chạy theo lịch hoặc điều kiện dự kiến.
- Kiểm tra tính idempotent khi một job hoặc message được xử lý nhiều lần.
- Kiểm tra lỗi giữa chừng, retry và khả năng tiếp tục.
- Xác minh sự kiện không được phát trước khi dữ liệu cần thiết commit.
- Kiểm tra thứ tự xử lý nếu nghiệp vụ phụ thuộc thứ tự.
- Dùng cơ chế đồng bộ hóa hoặc chờ điều kiện có timeout; tránh sleep cố định khiến test chậm và chập chờn.

Nếu dùng Awaitility hoặc công cụ tương tự, đặt timeout có giới hạn và thông báo rõ điều kiện chưa đạt. Test cần dọn hàng đợi, scheduler state và dữ liệu sau khi chạy.

## 9. Quản lý Spring context, cấu hình và dữ liệu test

Spring TestContext có thể cache ApplicationContext giữa các test có cấu hình tương thích. Điều này giúp giảm thời gian, nhưng các thay đổi cấu hình hoặc context tùy biến quá nhiều có thể làm cache phân mảnh và khiến suite chậm.

Các nguyên tắc nên áp dụng:

- Dùng cấu hình test tối thiểu và tái sử dụng khi cùng mục tiêu.
- Chỉ dùng `@DirtiesContext` khi test thực sự làm thay đổi context và không thể khôi phục trạng thái.
- Tránh thay đổi singleton bean hoặc static state khiến test phụ thuộc thứ tự chạy.
- Tách cấu hình test khỏi cấu hình production; không để test vô tình dùng secret hoặc endpoint thật.
- Dùng profile và property rõ ràng, kiểm tra cấu hình tương ứng môi trường phát hành.
- Không mock framework hoặc Spring container quá sâu; ưu tiên kiểm tra hành vi ở ranh giới cần xác minh.

### 9.1. Dữ liệu kiểm thử

Dữ liệu test phải dễ hiểu, độc lập và có thể tái tạo. Có thể dùng factory, builder hoặc fixture nhỏ thay vì một bộ dữ liệu khổng lồ dùng chung. Mỗi test nên chỉ tạo dữ liệu cần thiết cho hành vi đang kiểm tra.

Với dữ liệu trong database:

- Dùng ID duy nhất hoặc namespace riêng để tránh xung đột khi chạy song song.
- Không phụ thuộc vào thứ tự test hoặc dữ liệu còn lại từ lần chạy trước.
- Dọn dữ liệu sau test nếu transaction rollback không áp dụng.
- Dùng dữ liệu tổng hợp; không sao chép dữ liệu cá nhân production nếu chưa có quy trình bảo vệ và làm sạch.
- Chuẩn bị trường hợp dữ liệu biên như null, chuỗi dài, ký tự Unicode, thời gian và múi giờ.

Với test chạy song song, xác minh rằng database, file, port, container và mock server không dùng chung trạng thái gây tranh chấp. Nếu một test cần tài nguyên độc quyền, hãy cô lập tài nguyên đó hoặc không chạy test ấy song song.

## 10. Tổ chức test suite và cổng kiểm soát CI/CD

Một pipeline hiệu quả phân bố kiểm thử theo thời điểm để nhóm nhận phản hồi phù hợp với chi phí:

~~~mermaid
flowchart TD
    A["Commit / Pull request"] --> B["Compile, static checks, unit tests"]
    B --> C["Architecture and focused slice tests"]
    C --> D["Integration tests with isolated dependencies"]
    D --> E["Build deployable artifact"]
    E --> F["Staging: critical end-to-end and migration checks"]
    F --> G["Release gate and deployment"]
    G --> H["Post-deployment smoke and operational checks"]
~~~

Có thể tổ chức các nhóm test như sau:

| Thời điểm | Bộ kiểm thử | Cổng kiểm soát |
|---|---|---|
| Mỗi commit hoặc pull request | Compile, static analysis, unit test, architecture test | Không merge khi có lỗi bắt buộc |
| Pull request hoặc pipeline chính | Slice test và integration test trọng yếu | Chặn khi hợp đồng, persistence hoặc wiring bị lỗi |
| Trước phát hành | Migration test, end-to-end luồng quan trọng, security/performance theo rủi ro | Chỉ phát hành khi gate đã thống nhất đạt |
| Sau triển khai | Smoke test, health/readiness, metric và log | Tiếp tục rollout khi tín hiệu trong ngưỡng |
| Theo lịch hoặc thay đổi lớn | Kiểm thử tải, phục hồi, tương thích và diễn tập vận hành | Tạo hành động khắc phục và theo dõi rủi ro |

Không nên chạy end-to-end suite đầy đủ trên mọi commit nếu thời gian và độ ổn định không đáp ứng. Hãy giữ một tập nhanh làm phản hồi mặc định, sau đó chạy test rộng hơn ở các mốc phù hợp. Test chậm nhưng có giá trị cao vẫn cần được lên lịch và có chủ sở hữu.

Một test flaky phải được xử lý như vấn đề chất lượng của pipeline. Không che giấu bằng cách retry vô hạn hoặc bỏ qua kết quả. Ghi nhận tần suất, điều kiện tái hiện, người phụ trách và thời hạn sửa; nếu tạm thời quarantine, phải có lý do và kiểm soát rủi ro.

## 11. Tiêu chí chất lượng và chỉ số theo dõi

Chỉ số nên hỗ trợ quyết định cải thiện chứ không trở thành mục tiêu số lượng. Có thể theo dõi:

- Thời gian phản hồi của các nhóm test và thời gian chờ pipeline.
- Tỷ lệ test ổn định, số lần flaky và thời gian xử lý.
- Lỗi được phát hiện ở từng mức kiểm thử và lỗi lọt tới production.
- Rủi ro trọng yếu có test và bằng chứng phù hợp.
- Thời gian từ lúc phát hiện lỗi tới khi có nguyên nhân và bản sửa.
- Thời gian khởi động ứng dụng, tỷ lệ lỗi, độ trễ và mức sử dụng tài nguyên sau triển khai.
- Tỷ lệ migration và deployment thành công, cùng số lần rollback.

Không dùng code coverage đơn lẻ để kết luận chất lượng. Coverage cao không chứng minh assertion có giá trị, dữ liệu biên đã được kiểm tra hoặc tích hợp ngoài hoạt động đúng. Kết hợp coverage với phân tích rủi ro, mutation testing nếu phù hợp, review test và dữ liệu lỗi thực tế.

Tiêu chí phát hành nên nêu rõ test bắt buộc, mức độ lỗi còn mở, tình trạng migration, các chỉ số vận hành và người có thẩm quyền chấp nhận rủi ro. Nếu thiếu bằng chứng ở một luồng trọng yếu, trạng thái nên là chưa đủ điều kiện đánh giá thay vì tự động xem là đạt.

## 12. Ví dụ chiến lược cho ứng dụng quản lý đơn hàng

Giả sử một ứng dụng Spring Boot nguyên khối có các module customer, order, inventory và payment. Khách hàng tạo đơn; hệ thống kiểm tra tồn kho, tính tổng tiền, ghi đơn và khởi tạo thanh toán.

**Rủi ro chính:** giá trị đơn sai, tồn kho bị trừ hai lần, đơn được đánh dấu đã thanh toán khi gateway timeout, hoặc dữ liệu chỉ được ghi một phần.

**Lựa chọn kiểm thử:**

1. Unit test cho quy tắc tính giá, chiết khấu, trạng thái đơn và điều kiện giữ hàng.
2. Service test cho điều phối tạo đơn, xác minh xử lý lỗi từ inventory và payment.
3. Slice test cho controller, validation, JSON mapping và repository.
4. Integration test với database tương thích production để xác minh transaction, unique constraint, locking và migration.
5. Test tích hợp payment gateway bằng stub để kiểm tra success, decline, timeout và phản hồi không hợp lệ.
6. Một số end-to-end test đi qua API thật để xác minh tạo đơn, đọc lại trạng thái và quyền truy cập.
7. Architecture test để ngăn module order truy cập trực tiếp repository nội bộ của payment hoặc inventory.
8. Kiểm thử tải cho luồng tạo đơn và kiểm tra metric về connection pool, query và độ trễ.

**Cổng phát hành:** unit và architecture test phải đạt trên pull request; integration test trọng yếu phải đạt trên pipeline chính; migration và end-to-end test chạy trước phát hành; smoke test và metric được kiểm tra sau triển khai. Nếu payment timeout tạo trạng thái không xác định, nhóm phải xác minh cơ chế đối soát và idempotency trước khi tiếp tục rollout.

Ví dụ này cho thấy chiến lược không cần kiểm thử mọi đường đi bằng một bài end-to-end lớn. Mỗi rủi ro được kiểm tra ở mức phù hợp, còn một số ít luồng tích hợp xác nhận các module vẫn phối hợp đúng như một ứng dụng hoàn chỉnh.

## 13. Những sai lầm thường gặp

- **Dùng `@SpringBootTest` cho mọi test:** làm suite chậm và khó xác định nguyên nhân. Chọn unit, slice hoặc integration test theo rủi ro.
- **Mock toàn bộ module lân cận:** che giấu lỗi hợp đồng giữa các module. Bổ sung test tích hợp cho public interface quan trọng.
- **Chỉ dùng H2 khi production dùng database khác:** bỏ sót khác biệt SQL, kiểu dữ liệu, locking và migration. Kiểm tra với database tương thích production.
- **Cho rằng rollback của test bao phủ mọi transaction:** test qua HTTP, async hoặc commit thực tế có thể không nằm trong transaction của test. Thiết kế cleanup và assertion đúng ranh giới.
- **Kiểm thử migration trên schema rỗng:** không phát hiện lỗi dữ liệu cũ. Dùng dữ liệu đại diện và schema phiên bản trước.
- **Không kiểm tra dependency rule:** package nội bộ bị truy cập chéo và module dần phụ thuộc chặt. Dùng architecture test cho quy tắc cốt lõi.
- **Dùng dữ liệu chung hoặc static state:** test phụ thuộc thứ tự và thất bại khi chạy song song. Cô lập dữ liệu và trạng thái.
- **Chỉ kiểm tra HTTP status:** bỏ sót sai dữ liệu, phân quyền và side effect. Assertion cả kết quả nghiệp vụ và trạng thái lưu trữ.
- **Bỏ qua xử lý nền:** request trả thành công nhưng job hoặc event thất bại sau đó. Kiểm tra kết quả bất đồng bộ với timeout và bằng chứng.
- **Dùng coverage làm thước đo duy nhất:** số dòng được thực thi không phản ánh mức bảo vệ rủi ro. Đánh giá assertion và khoảng trống theo nghiệp vụ.

## 14. Checklist xây dựng chiến lược

- Đã lập bản đồ module, điểm vào, phụ thuộc, transaction và tích hợp ngoài.
- Đã xác định rủi ro trọng yếu theo luồng nghiệp vụ và phạm vi thay đổi.
- Mỗi loại rủi ro có mức kiểm thử phù hợp và bằng chứng cần thu thập.
- Quy tắc domain được kiểm tra nhanh bằng unit test.
- Ranh giới module và dependency rule quan trọng được bảo vệ bằng architecture test.
- Persistence, transaction và migration được kiểm tra với database tương thích production.
- Spring context và cấu hình môi trường được kiểm tra ở mức cần thiết.
- Tích hợp ngoài có test cho success, timeout, lỗi và retry an toàn.
- Job, event và xử lý bất đồng bộ có kiểm tra tính lặp an toàn và kết quả cuối.
- Dữ liệu, container, profile và trạng thái test được cô lập để có thể chạy lặp lại.
- CI/CD có test nhanh cho pull request và test rộng hơn tại các mốc phát hành.
- Tiêu chí go/no-go, chỉ số vận hành và người chấp nhận rủi ro đã rõ ràng.

Chiến lược kiểm thử cho ứng dụng Spring Boot nguyên khối cần phản ánh cấu trúc module, transaction và cách ứng dụng được triển khai như một đơn vị. Khi mỗi rủi ro được kiểm tra ở mức phù hợp, các ranh giới kiến trúc được bảo vệ và bằng chứng được gắn với quyết định phát hành, nhóm có thể duy trì tốc độ phát triển mà vẫn kiểm soát được chất lượng của toàn ứng dụng.
