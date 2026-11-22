# Đánh giá tác động khi yêu cầu, kiến trúc hoặc thành phần phụ thuộc thay đổi

Trong module **VALIDATION_TESTING_STRATEGY**, thay đổi là điều bình thường trong suốt vòng đời sản phẩm. Yêu cầu nghiệp vụ được làm rõ, kiến trúc được điều chỉnh, thư viện được nâng cấp, API của đối tác thay đổi, cấu hình được cập nhật hoặc một thành phần được thay thế. Mỗi thay đổi có thể ảnh hưởng đến hành vi đã được kiểm thử, các giả định của test case, dữ liệu, môi trường và rủi ro vận hành. Nếu nhóm chỉ kiểm tra phần mã vừa sửa mà không đánh giá tác động lan truyền, lỗi có thể xuất hiện ở những chức năng tưởng như không liên quan.

**Đánh giá tác động thay đổi (change impact analysis)** là hoạt động xác định những yêu cầu, thành phần, giao diện, dữ liệu, kiểm thử và hoạt động vận hành có thể bị ảnh hưởng bởi một thay đổi, sau đó quyết định phạm vi xác minh phù hợp. Mục đích không phải dự đoán chính xác mọi lỗi có thể xảy ra, mà là tạo căn cứ có hệ thống để biết điều gì cần xem xét, kiểm thử lại, cập nhật hoặc theo dõi.

Bài học này trình bày cách phân loại thay đổi, xác định phạm vi trực tiếp và gián tiếp, phân tích phụ thuộc, đánh giá rủi ro, lựa chọn kiểm thử hồi quy, cập nhật truy vết và quản lý thay đổi trong quy trình phát triển. Mục tiêu là giúp nhóm đưa ra quyết định kiểm thử dựa trên tác động thực tế, giảm bỏ sót rủi ro và tránh chạy lại toàn bộ bộ kiểm thử một cách máy móc.

## 1. Hiểu mục tiêu của change impact analysis

### 1.1. Vì sao một thay đổi có thể ảnh hưởng rộng?

Một thay đổi thường xuất phát từ một điểm nhưng đi qua nhiều lớp:

- Thay đổi yêu cầu có thể làm đổi quy tắc nghiệp vụ, giao diện, API, dữ liệu và báo cáo.
- Thay đổi kiến trúc có thể ảnh hưởng luồng giao tiếp, tính nhất quán, bảo mật, khả năng phục hồi và hiệu năng.
- Nâng cấp thư viện có thể làm đổi hành vi mặc định, API, serialization hoặc xử lý lỗi.
- Thay đổi schema có thể ảnh hưởng ứng dụng, migration, consumer, báo cáo và dữ liệu lịch sử.
- Thay đổi cấu hình có thể làm đổi timeout, retry, quyền, cache hoặc feature flag.
- Thay đổi dịch vụ bên ngoài có thể ảnh hưởng hợp đồng, giới hạn gọi, xác thực và cách xử lý lỗi.

Một thay đổi nhỏ về tên trường API có thể tác động đến nhiều consumer. Một thay đổi lớn về cấu trúc nội bộ có thể không làm đổi hành vi bên ngoài nếu ranh giới hợp đồng được giữ nguyên. Vì vậy, kích thước diff hoặc số file thay đổi không đủ để xác định phạm vi kiểm thử.

### 1.2. Những câu hỏi cần trả lời

Với mỗi change request, nhóm cần xác định:

1. Điều gì đang thay đổi và lý do thay đổi là gì?
2. Hành vi hoặc giả định nào sẽ khác trước?
3. Những thành phần, giao diện và dữ liệu nào phụ thuộc vào phần thay đổi?
4. Yêu cầu và rủi ro nào bị ảnh hưởng?
5. Kiểm thử hiện có nào không còn phù hợp hoặc cần chạy lại?
6. Cần tạo test case mới hay cập nhật dữ liệu, môi trường và oracle?
7. Có tác động đến tương thích, bảo mật, hiệu năng hoặc vận hành không?
8. Bằng chứng nào cần có trước khi chấp nhận thay đổi hoặc phát hành?

### 1.3. Đầu ra của đánh giá tác động

Một đánh giá có thể tạo ra các đầu ra sau:

- Danh sách yêu cầu, quy tắc và tiêu chí chất lượng bị ảnh hưởng.
- Danh sách thành phần, service, API, schema và dependency liên quan.
- Danh sách test case cần cập nhật, bổ sung hoặc chạy lại.
- Rủi ro mới và mức ưu tiên xác minh.
- Các giả định, giới hạn và khu vực chưa rõ.
- Kế hoạch kiểm thử, dữ liệu và môi trường.
- Người chịu trách nhiệm và tiêu chí hoàn tất.
- Quyết định chấp nhận, hoãn hoặc từ chối thay đổi.

Đánh giá tác động không nhất thiết là tài liệu dài. Với thay đổi nhỏ, một bản ghi ngắn có liên kết truy vết có thể đủ. Với thay đổi kiến trúc, dữ liệu hoặc bảo mật, cần phân tích sâu và có review của các vai trò liên quan.

## 2. Phân loại thay đổi cần đánh giá

### 2.1. Thay đổi yêu cầu (requirement change)

Có thể gồm:

- Thêm, sửa hoặc loại bỏ chức năng.
- Thay đổi quy tắc nghiệp vụ hoặc điều kiện chấp nhận.
- Thay đổi vai trò, quyền hoặc nhóm người dùng.
- Thay đổi giới hạn, ngưỡng hoặc cách tính.
- Thay đổi hành trình, thông báo hoặc giao diện.
- Thay đổi yêu cầu phi chức năng như latency, availability hoặc retention.

Cần xác định yêu cầu cũ nào bị thay thế, yêu cầu nào vẫn còn hiệu lực và các hành trình liên quan. Một thay đổi về quy tắc hoàn tiền có thể ảnh hưởng đơn hàng, thanh toán, ledger, báo cáo, API và hỗ trợ khách hàng.

### 2.2. Thay đổi kiến trúc (architecture change)

Ví dụ:

- Tách một service thành nhiều service.
- Chuyển từ xử lý đồng bộ sang bất đồng bộ.
- Thay database hoặc message broker.
- Thêm cache, gateway hoặc lớp điều phối.
- Thay đổi mô hình lưu trữ hoặc phân vùng dữ liệu.
- Chuyển từ triển khai đơn vùng sang nhiều vùng.
- Thay đổi cơ chế xác thực hoặc phân quyền.

Đánh giá cần xem xét các ranh giới mới, giao tiếp giữa thành phần, transaction, consistency, failure mode, observability và cách triển khai. Kiểm thử từng thành phần riêng lẻ có thể không phát hiện lỗi do giao tiếp hoặc trạng thái phân tán.

### 2.3. Thay đổi thành phần phụ thuộc (dependency change)

Dependency có thể là:

- Thư viện trực tiếp hoặc bắc cầu.
- Runtime, framework hoặc hệ điều hành nền.
- API hoặc SDK của nhà cung cấp.
- Dịch vụ SaaS hoặc hệ thống đối tác.
- Container base image.
- Công cụ build, test runner hoặc plugin.
- Phiên bản database driver, broker client hoặc serializer.

Không chỉ xem số phiên bản. Cần đọc thay đổi tương thích, thay đổi mặc định, cảnh báo bảo mật, yêu cầu runtime và các API đã bị loại bỏ. Một nâng cấp patch có thể sửa lỗi bảo mật nhưng cũng có thể thay đổi hành vi ở trường hợp biên.

### 2.4. Thay đổi dữ liệu và hợp đồng

Ví dụ:

- Thêm, xóa hoặc đổi kiểu trường.
- Thay đổi enum hoặc giá trị mặc định.
- Thay đổi format timestamp hoặc tiền tệ.
- Thay đổi schema event.
- Thay đổi API request/response.
- Thay đổi quy tắc validation.
- Migration hoặc chuyển đổi dữ liệu lịch sử.

Các thay đổi này cần kiểm tra tương thích giữa phiên bản cũ và mới, dữ liệu cũ và mới, producer và consumer, cũng như khả năng rollback hoặc forward recovery.

### 2.5. Thay đổi cấu hình và môi trường

Các thay đổi có thể nằm ngoài mã nguồn:

- Timeout, retry và circuit breaker.
- Feature flag và rollout percentage.
- Resource limit và autoscaling.
- Cache TTL và connection pool.
- Secret, certificate và trust store.
- Network policy, DNS và endpoint.
- Locale, timezone và lịch chạy.
- Quyền service account và access policy.

Một cấu hình sai có thể tạo ra hành vi khác mà unit test không phát hiện. Cần xác minh cấu hình hiệu lực trong môi trường triển khai, không chỉ file cấu hình trong repository.

### 2.6. Thay đổi kiểm thử và công cụ

Cũng cần đánh giá tác động khi:

- Thay test framework hoặc phiên bản browser driver.
- Thay test data factory hoặc seed.
- Thay môi trường test hoặc cách provisioning.
- Thay assertion, oracle hoặc tiêu chí pass.
- Thay chiến lược mock/service virtualization.
- Thay công cụ thu thập metrics hoặc báo cáo.

Một thay đổi ở test infrastructure có thể làm kết quả khác đi dù sản phẩm không đổi. Cần phân biệt lỗi sản phẩm với thay đổi trong phương pháp đo.

## 3. Xác định phạm vi tác động trực tiếp và gián tiếp

### 3.1. Tác động trực tiếp

Tác động trực tiếp là phần được sửa hoặc phần có giao diện thay đổi rõ ràng. Ví dụ, đổi trường `customerId` thành `accountId` trong API ảnh hưởng trực tiếp đến:

- Controller hoặc endpoint phát sinh thay đổi.
- DTO hoặc schema.
- Validation và serialization.
- Tài liệu API.
- Test case gọi endpoint.
- Consumer sử dụng trường đó.

Các thành phần trực tiếp thường dễ xác định từ change request, diff, schema hoặc sơ đồ kiến trúc.

### 3.2. Tác động gián tiếp

Tác động gián tiếp xảy ra qua quan hệ phụ thuộc hoặc luồng dữ liệu. Cùng thay đổi API có thể ảnh hưởng:

- Mobile app hoặc frontend chưa được cập nhật.
- Integration partner.
- Event consumer.
- Báo cáo đọc dữ liệu đã chuyển đổi.
- Job nền sử dụng trường cũ.
- Log, alert hoặc dashboard dựa vào tên thuộc tính.
- Script vận hành hoặc data export.

Tác động gián tiếp thường là nơi dễ bỏ sót nhất. Cần lần theo dependency và luồng nghiệp vụ, không dừng ở file đã thay đổi.

### 3.3. Lần theo luồng từ đầu đến cuối

Với một thay đổi, hãy xác định:

- Nguồn dữ liệu hoặc hành động bắt đầu.
- Các thành phần xử lý trung gian.
- Giao diện hoặc event qua từng ranh giới.
- Nơi lưu trạng thái.
- Consumer hoặc tác vụ nền.
- Kết quả hiển thị hoặc tác dụng phụ cuối cùng.

Ví dụ, thay đổi quy tắc giá sản phẩm có thể đi qua catalog, cart, pricing service, order, payment, invoice, refund và báo cáo doanh thu. Chỉ kiểm thử màn hình sản phẩm sẽ không đủ để xác nhận toàn bộ tác động.

### 3.4. Phân biệt phạm vi thay đổi với phạm vi kiểm thử

Phạm vi code diff cho biết những gì được sửa. Phạm vi kiểm thử cần bao gồm các hành vi có nguy cơ bị ảnh hưởng, kể cả thành phần không thay đổi mã.

Ví dụ, thay đổi cách tạo event có thể không sửa consumer nhưng consumer vẫn cần được kiểm tra vì schema hoặc thứ tự event có thể thay đổi. Ngược lại, một file tài liệu nội bộ được sửa không nhất thiết yêu cầu chạy toàn bộ E2E.

## 4. Phân tích phụ thuộc và quan hệ giữa các thành phần

### 4.1. Các loại phụ thuộc

Có thể phân loại:

- **Compile-time dependency:** thư viện hoặc module cần để build.
- **Runtime dependency:** dịch vụ, database, broker hoặc runtime cần khi chạy.
- **Data dependency:** thành phần đọc/ghi cùng dữ liệu hoặc schema.
- **Contract dependency:** API, event hoặc giao thức giữa producer và consumer.
- **Configuration dependency:** biến môi trường, secret, feature flag và policy.
- **Operational dependency:** scheduler, backup, monitoring, deployment và runbook.
- **Human/process dependency:** phê duyệt, chủ sở hữu và quy trình hỗ trợ.

Phân loại giúp nhóm tìm đúng người và đúng loại kiểm thử khi thay đổi một thành phần.

### 4.2. Dùng dependency graph

Sơ đồ phụ thuộc giúp nhìn thấy đường lan truyền:

~~~mermaid
flowchart TD
    A[Pricing Rule] --> B[Pricing Service]
    B --> C[Cart API]
    B --> D[Order API]
    D --> E[Payment Service]
    D --> F[Order Event]
    F --> G[Notification Consumer]
    F --> H[Analytics Consumer]
    E --> I[Payment Provider]
    D --> J[Invoice / Reporting]
~~~

Nếu thay đổi ở Pricing Rule, cần xem xét các consumer và kết quả cuối có sử dụng giá hay không. Sơ đồ này là minh họa; hệ thống thật cần được lập theo dependency và luồng dữ liệu thực tế.

### 4.3. Đánh giá mức phụ thuộc

Với mỗi quan hệ, xác định:

- Thành phần nào gọi hoặc đọc thành phần nào?
- Giao diện có version hoặc contract không?
- Quan hệ là đồng bộ hay bất đồng bộ?
- Có retry, cache hoặc queue không?
- Consumer có thể chạy phiên bản cũ không?
- Có thể triển khai độc lập không?
- Khi provider lỗi, consumer phản ứng thế nào?
- Có dữ liệu được lưu theo format cũ không?

Đặc biệt chú ý các phụ thuộc không thể nhìn thấy từ source code, như cấu hình runtime, scheduled job, đối tác hoặc dashboard vận hành.

### 4.4. Xác định chủ sở hữu phụ thuộc

Danh sách dependency cần có owner hoặc nhóm chịu trách nhiệm. Nếu một thay đổi ảnh hưởng đến dịch vụ ngoài nhóm, cần có đầu mối xác nhận contract, môi trường, thời gian kiểm thử và cách xử lý khi không thể kiểm tra trực tiếp.

Không nên giả định một thành phần ít được nhắc đến là không còn được sử dụng. Cần xác minh qua cấu hình, traffic, consumer registry hoặc người sở hữu.

## 5. Đánh giá tác động đến yêu cầu, test và dữ liệu

### 5.1. Truy vết từ yêu cầu đến test case

Liên kết thay đổi với:

- Requirement ID.
- Acceptance criteria.
- Business rule.
- Risk record.
- Test condition.
- Test case và test suite.
- Test data.
- Evidence và defect.

Nếu yêu cầu thay đổi nhưng test case không được cập nhật, bộ kiểm thử có thể tiếp tục xác minh quy tắc cũ và tạo kết quả pass sai nghĩa.

### 5.2. Phân loại test case bị ảnh hưởng

Có thể chia thành:

- **Must update:** test case hoặc expected result đã lỗi thời.
- **Must add:** cần test mới cho hành vi hoặc rủi ro mới.
- **Must rerun:** test hiện tại vẫn hợp lệ nhưng cần chạy lại trên bản thay đổi.
- **Review only:** cần xem xét để xác nhận không bị ảnh hưởng.
- **No impact with rationale:** không cần chạy lại, có lý do và bằng chứng hỗ trợ.

Không nên đánh dấu “không ảnh hưởng” chỉ vì test case không nằm trong thư mục hoặc module được sửa. Cần xem xét dependency và hành vi.

### 5.3. Đánh giá test oracle

Thay đổi yêu cầu có thể làm expected result thay đổi. Cần xác minh:

- Kết quả mong đợi mới là gì?
- Quy tắc cũ còn áp dụng cho dữ liệu lịch sử không?
- Có ngoại lệ hoặc điều kiện chuyển tiếp không?
- Có thay đổi thông báo, mã lỗi hoặc response không?
- Ai phê duyệt cách diễn giải nghiệp vụ?

Nếu test oracle chưa được cập nhật, chạy test cũ có thể báo fail giả hoặc pass sai.

### 5.4. Đánh giá dữ liệu kiểm thử

Cần xem xét:

- Dữ liệu cũ có còn hợp lệ không?
- Factory hoặc fixture có tạo đúng schema mới không?
- Giá trị biên mới nào cần bổ sung?
- Có cần dữ liệu lịch sử hoặc dữ liệu chuyển đổi không?
- Quan hệ giữa các bản ghi có thay đổi không?
- Có dữ liệu nhạy cảm hoặc quyền truy cập mới không?
- Có cần seed lại hoặc migration trong môi trường test không?

Một thay đổi enum có thể yêu cầu cập nhật dữ liệu test, parser, assertion, report và consumer. Nếu chỉ sửa test case mà không cập nhật fixture, lỗi có thể phát sinh ở bước chuẩn bị thay vì hành vi sản phẩm.

## 6. Đánh giá rủi ro do thay đổi

### 6.1. Các yếu tố rủi ro

Mỗi tác động nên được xem xét theo:

- Mức hậu quả nếu hành vi sai.
- Khả năng lỗi phát sinh.
- Phạm vi lan truyền qua dependency.
- Độ phức tạp và độ mới của thay đổi.
- Mức độ không chắc chắn hoặc thiếu hiểu biết.
- Khả năng phát hiện lỗi trước khi ảnh hưởng người dùng.
- Khả năng rollback hoặc phục hồi.
- Mức độ quan trọng của dữ liệu và quy trình.

Thay đổi ở thành phần dùng chung, API công khai, xác thực, dữ liệu tài chính hoặc migration thường cần mức xem xét cao hơn một thay đổi nội dung cô lập.

### 6.2. Ma trận tác động

Một bảng đơn giản:

| Thành phần / khu vực | Mức tác động | Lý do | Kiểm tra đề xuất |
|---|---|---|---|
| Pricing service | Cao | Quy tắc tính giá thay đổi trực tiếp | Unit, boundary, integration |
| Cart API | Cao | Trả giá và tổng tiền mới | Contract, API, E2E |
| Payment | Trung bình/cao | Số tiền gửi đi có thể thay đổi | Integration, reconciliation |
| Invoice | Trung bình | Có thể dùng giá đã chốt | Regression và data check |
| Analytics | Trung bình | Event hoặc field thay đổi | Contract và consumer test |
| Notification | Thấp/trung bình | Nội dung có thể hiển thị giá | Review và targeted test |

Mức tác động không phải kết luận cuối cùng về severity. Nó giúp xác định vùng cần đánh giá và kiểm thử.

### 6.3. Chấm điểm rủi ro có kiểm soát

Có thể dùng thang định tính hoặc điểm số cho:

- Impact (I).
- Likelihood (L).
- Propagation (P).
- Uncertainty (U).

Ví dụ công thức minh họa:

```
Change risk score = I × L × P × U
```

Nếu dùng thang 1–5 cho từng chiều, điểm số giúp sắp xếp những thay đổi cần review sâu. Tuy nhiên, điểm số không phải xác suất chính xác và không thay thế phán đoán chuyên môn. Cần ghi định nghĩa thang, người đánh giá và lý do; một rủi ro bảo mật trọng yếu có thể cần xử lý ngay dù điểm tổng không cao.

### 6.4. Độ không chắc chắn là tín hiệu cần điều tra

Khi không biết dependency nào sử dụng interface hoặc không rõ dữ liệu lịch sử có còn được đọc, không nên mặc định tác động thấp. Ghi giả định và tạo hành động xác minh:

- Tìm consumer hoặc owner.
- Kiểm tra traffic và log.
- Xem contract hoặc schema registry.
- Chạy thử trong môi trường cô lập.
- Thực hiện review kiến trúc.
- Bổ sung kiểm thử khám phá có mục tiêu.

Độ không chắc chắn cao có thể làm tăng phạm vi review ngay cả khi diff nhỏ.

## 7. Chọn phạm vi kiểm thử hồi quy theo tác động

### 7.1. Không chạy lại mọi thứ một cách máy móc

Regression testing nhằm xác nhận thay đổi không làm hỏng hành vi đã có. Phạm vi nên dựa trên:

- Thành phần trực tiếp thay đổi.
- Dependency và consumer liên quan.
- Hành trình nghiệp vụ bị ảnh hưởng.
- Rủi ro và hậu quả.
- Lịch sử lỗi ở vùng tương tự.
- Mức độ bao phủ của test hiện có.
- Chi phí và thời gian chạy.
- Mức độ đại diện của môi trường.

Một thay đổi nhỏ ở thư viện xác thực dùng chung có thể cần regression rộng. Một thay đổi nội dung tĩnh cô lập có thể chỉ cần kiểm tra hẹp.

### 7.2. Các lớp kiểm thử cần cân nhắc

| Lớp kiểm thử | Khi nên xem xét |
|---|---|
| Unit/component | Logic, thuật toán, validation hoặc component thay đổi |
| API/contract | Schema, endpoint, event hoặc dependency interface thay đổi |
| Integration | Giao tiếp, transaction, persistence hoặc retry bị ảnh hưởng |
| System/E2E | Hành trình xuyên hệ thống hoặc quy tắc đầu-cuối thay đổi |
| Data migration | Schema, dữ liệu lịch sử hoặc format thay đổi |
| Performance | Hot path, truy vấn, serialization, cache hoặc tải thay đổi |
| Security | Auth, authorization, crypto, dependency hoặc trust boundary thay đổi |
| Resilience | Retry, timeout, queue, failover hoặc dependency behavior thay đổi |
| Accessibility/UI | Giao diện, component hoặc hành trình người dùng thay đổi |

Không phải mọi thay đổi đều cần mọi lớp. Cần ghi lý do lựa chọn và khoảng trống còn lại.

### 7.3. Regression selection theo dependency

Có thể bắt đầu từ component thay đổi, lần theo graph đến các consumer, rồi chọn test bao phủ những đường đi quan trọng. Bổ sung:

- Test trực tiếp của component.
- Contract test ở ranh giới.
- Integration test cho các kết nối bị ảnh hưởng.
- E2E cho hành trình có hậu quả cao.
- Test dữ liệu và migration.
- Non-functional test khi thuộc tính bị tác động.

Nếu dependency graph không đầy đủ, cần mở rộng review hoặc dùng smoke/regression rộng hơn cho đến khi hiểu rõ phạm vi.

### 7.4. Ưu tiên test theo rủi ro

Ưu tiên chạy trước:

1. Hành vi cốt lõi và rủi ro nghiêm trọng.
2. Contract công khai và tương thích.
3. Dữ liệu, phân quyền và giao dịch.
4. Các đường đi trực tiếp bị thay đổi.
5. Consumer và tích hợp gián tiếp.
6. Các trường hợp biên và lỗi đã từng xuất hiện.
7. Các kiểm tra ít rủi ro hơn theo nguồn lực còn lại.

Thứ tự thực thi không có nghĩa bỏ qua các kiểm tra bắt buộc. Nếu test quan trọng bị blocked, cần ghi rõ và đánh giá ảnh hưởng đến quyết định release.

## 8. Đánh giá tác động theo từng loại thay đổi

### 8.1. Khi yêu cầu nghiệp vụ thay đổi

Ví dụ, chính sách hủy đơn thay đổi từ “được hủy trước khi giao” thành “chỉ được hủy trước khi xác nhận”.

Cần đánh giá:

- Các trạng thái đơn và chuyển trạng thái.
- Quyền người dùng và vai trò hỗ trợ.
- UI, API và thông báo lỗi.
- Tồn kho, thanh toán và hoàn tiền.
- Job nền hoặc event xử lý hủy.
- Báo cáo và dữ liệu lịch sử.
- Test case cho trạng thái hợp lệ, không hợp lệ và biên thời gian.

Test mới cần bao phủ trạng thái CONFIRMED, SHIPPED và các trường hợp retry hoặc thao tác đồng thời nếu liên quan.

### 8.2. Khi kiến trúc thay đổi

Ví dụ, chuyển xử lý thông báo từ đồng bộ sang event-driven.

Cần đánh giá:

- Thời điểm response được trả về.
- Event schema và version.
- Broker, queue và consumer.
- Retry, duplicate, ordering và dead-letter.
- Trạng thái accepted so với delivered.
- Observability và correlation ID.
- Cách xử lý khi consumer dừng hoặc backlog tăng.
- Khả năng triển khai phiên bản cũ và mới cùng lúc.

Bộ test cần bổ sung contract, integration, asynchronous behavior, idempotency và resilience. Chỉ kiểm tra API trả 202 không chứng minh thông báo đã được xử lý đúng.

### 8.3. Khi dependency được nâng cấp

Ví dụ, nâng cấp database driver hoặc thư viện JSON.

Cần đánh giá:

- API bị thay đổi hoặc loại bỏ.
- Hành vi serialization/deserialization.
- Default timeout, pooling hoặc retry.
- Hiệu năng và bộ nhớ.
- Xử lý exception và transaction.
- Tương thích runtime và hệ điều hành.
- CVE và license.
- Các component dùng chung dependency.

Có thể dùng unit/contract test, integration test với database hoặc service thật trong môi trường test, cùng performance test nếu dependency nằm trên đường xử lý quan trọng.

### 8.4. Khi schema hoặc API thay đổi

Ví dụ, đổi trường response từ số nguyên sang chuỗi hoặc đổi enum.

Cần đánh giá:

- Consumer hiện tại và phiên bản cũ.
- Mobile app có thể cập nhật chậm.
- Event đã lưu hoặc message đang nằm trong queue.
- Dữ liệu lịch sử.
- SDK và tài liệu API.
- Validation, parsing và report.
- Kế hoạch versioning và deprecation.

Kiểm tra tương thích ngược và tiến. Nếu không thể duy trì tương thích, cần kế hoạch version mới, thời gian chuyển đổi và cách xử lý consumer chưa nâng cấp.

### 8.5. Khi cấu hình hoặc hạ tầng thay đổi

Ví dụ, giảm timeout hoặc thay đổi autoscaling.

Cần đánh giá:

- Tỷ lệ timeout và retry.
- Load shedding và backpressure.
- Connection pool.
- Queue backlog.
- Resource limit và startup.
- Hành vi khi tải đột biến.
- Alert và autoscaling policy.
- Chi phí và năng lực phục hồi.

Kiểm thử nên có cấu hình gần với mục tiêu và các tình huống tải/lỗi phù hợp. Unit test không đủ để xác nhận autoscaling hoặc network policy.

## 9. Quản lý thay đổi trong vòng đời phát triển

### 9.1. Quy trình change impact analysis

Một quy trình gợi ý:

1. **Tiếp nhận thay đổi:** ghi lý do, mục tiêu, phạm vi và người yêu cầu.
2. **Xác định baseline:** phiên bản yêu cầu, kiến trúc, API, schema và test hiện tại.
3. **Phân loại thay đổi:** requirement, architecture, dependency, data, configuration hoặc test infrastructure.
4. **Lần theo tác động:** tìm thành phần trực tiếp, gián tiếp và owner.
5. **Đánh giá rủi ro:** hậu quả, khả năng, lan truyền và độ không chắc chắn.
6. **Lập kế hoạch xác minh:** test mới, test cập nhật, regression, môi trường và dữ liệu.
7. **Review và phê duyệt:** các owner liên quan xác nhận phạm vi và tiêu chí.
8. **Thực thi và thu thập bằng chứng:** chạy kiểm thử theo kế hoạch.
9. **Đánh giá kết quả:** cập nhật defect, risk và quyết định.
10. **Đóng thay đổi:** cập nhật tài liệu, truy vết và bài học.

~~~mermaid
flowchart TD
    A[Change request] --> B[Phân loại và xác định baseline]
    B --> C[Lần theo dependency và luồng dữ liệu]
    C --> D[Đánh giá impact và risk]
    D --> E[Chọn test scope và evidence]
    E --> F[Review / Approval]
    F --> G[Implement và test]
    G --> H{Tiêu chí đạt?}
    H -- Không --> I[Defect / Mitigation / Rework]
    I --> G
    H -- Có --> J[Cập nhật traceability và release record]
~~~

### 9.2. Cổng review cho thay đổi rủi ro cao

Với thay đổi ảnh hưởng API công khai, dữ liệu, bảo mật hoặc kiến trúc, review nên có:

- Người sở hữu thành phần bị thay đổi.
- Owner của consumer hoặc dependency.
- QA/test lead.
- Kiến trúc sư hoặc platform owner khi cần.
- Security/data owner khi có liên quan.
- Product hoặc business owner nếu quy tắc thay đổi.

Review cần xác nhận tác động đã được nhận diện, kiểm thử đủ, phương án triển khai và phục hồi phù hợp.

### 9.3. Quản lý thay đổi khẩn cấp

Emergency change có thể cần rút ngắn quy trình nhưng không nên bỏ qua đánh giá rủi ro cốt lõi. Tối thiểu cần:

- Lý do khẩn cấp và phạm vi.
- Thành phần, dữ liệu và người dùng bị ảnh hưởng.
- Kiểm thử tối thiểu bắt buộc.
- Phương án rollback hoặc recovery.
- Người có quyền phê duyệt.
- Theo dõi sau triển khai.
- Review sau thay đổi để bổ sung bằng chứng và cập nhật tài liệu.

Sau khi ổn định, hoàn thiện truy vết và kiểm thử hồi quy còn thiếu.

## 10. Tài liệu hóa và truy vết quyết định

### 10.1. Mẫu Change Impact Record

| Trường | Nội dung |
|---|---|
| Change ID | Mã thay đổi |
| Summary | Mô tả ngắn thay đổi |
| Reason | Lý do và mục tiêu |
| Baseline | Phiên bản yêu cầu, code, schema hoặc kiến trúc |
| Change type | Requirement, architecture, dependency, data, config... |
| Direct impact | Thành phần và giao diện thay đổi trực tiếp |
| Indirect impact | Consumer, luồng dữ liệu và quy trình liên quan |
| Requirements / Risks | Yêu cầu và rủi ro bị ảnh hưởng |
| Dependencies / Owners | Thành phần phụ thuộc và owner |
| Test impact | Test cần thêm, sửa, chạy lại hoặc review |
| Data / Environment | Dữ liệu và môi trường cần chuẩn bị |
| Compatibility | Tương thích cũ/mới và kế hoạch chuyển đổi |
| Deployment / Recovery | Cách triển khai, rollback hoặc recovery |
| Evidence | Kết quả cần thu thập |
| Assumptions / Gaps | Giả định và điều chưa xác minh |
| Decision | Chấp nhận, hoãn hoặc từ chối |
| Approvers | Người review và phê duyệt |

### 10.2. Duy trì traceability

Chuỗi truy vết có thể là:

```text
Change ID
  -> Requirement / Architecture / Dependency
    -> Impacted component and interface
      -> Risk
        -> Test case / Test suite
          -> Test run and evidence
            -> Defect / Decision
              -> Release record
```

Truy vết giúp trả lời tại sao một test được chọn, test nào cần cập nhật khi thay đổi tiếp theo và bằng chứng nào hỗ trợ quyết định.

### 10.3. Ghi lại lý do không kiểm thử một khu vực

Nếu đánh giá cho rằng một khu vực không bị ảnh hưởng, ghi:

- Khu vực đã xem xét.
- Quan hệ dependency được kiểm tra.
- Lý do không có tác động.
- Bằng chứng hoặc giả định hỗ trợ.
- Người review nếu rủi ro đáng kể.

Điều này giúp tránh việc “không chạy test” bị hiểu là quên hoặc bỏ sót.

## 11. Đo lường hiệu quả đánh giá tác động

Có thể theo dõi:

- Tỷ lệ thay đổi có impact analysis trước khi triển khai.
- Số lỗi phát sinh do tác động gián tiếp bị bỏ sót.
- Tỷ lệ test case phải cập nhật sau thay đổi.
- Số regression test phát hiện lỗi liên quan.
- Số thay đổi phải rollback hoặc hotfix.
- Thời gian từ change request đến quyết định test scope.
- Số dependency không có owner hoặc contract rõ.
- Tỷ lệ change record có traceability đầy đủ.
- Tỷ lệ emergency change có post-review.

Không dùng các chỉ số này để khuyến khích tạo tài liệu hình thức. Mục tiêu là phát hiện điểm mù, cải thiện dependency mapping và giảm chi phí lỗi do thay đổi.

### 11.1. Đánh giá chất lượng impact analysis

Một impact analysis tốt:

- Xác định đúng baseline và phạm vi.
- Bao gồm tác động trực tiếp và gián tiếp.
- Lần theo dependency quan trọng.
- Có đánh giá rủi ro và độ không chắc chắn.
- Chọn test scope có lý do.
- Ghi giả định và khoảng trống.
- Có owner và người review.
- Liên kết được với bằng chứng sau kiểm thử.

### 11.2. Học từ lỗi bị bỏ sót

Khi lỗi xuất hiện sau thay đổi, xem lại:

- Dependency nào chưa được nhận diện?
- Test case nào đã lỗi thời?
- Có consumer hoặc dữ liệu lịch sử nào bị bỏ qua?
- Rủi ro có bị đánh giá thấp vì thiếu thông tin không?
- Test environment có đại diện không?
- Có bằng chứng nhưng không được xem xét không?
- Có thay đổi cấu hình ngoài quy trình không?

Cập nhật graph, checklist, test suite hoặc quy trình review để giảm khả năng lặp lại.

## 12. Ví dụ tổng hợp: thay đổi hợp đồng API

Giả sử một API đơn hàng đổi trường `totalAmount` từ số thập phân sang cấu trúc gồm `value` và `currency`.

### 12.1. Xác định tác động

**Trực tiếp:**

- Order API schema và serializer.
- Validation và response mapping.
- Unit và API tests.
- Tài liệu hợp đồng.

**Gián tiếp:**

- Web và mobile clients.
- Payment service.
- Invoice/reporting.
- Event consumers.
- Data export và analytics.
- Test fixtures và mock server.

### 12.2. Rủi ro

- Consumer cũ không parse được response mới.
- Tiền tệ bị mất hoặc dùng sai currency.
- Phép tính làm tròn thay đổi.
- Event đã nằm trong queue vẫn dùng schema cũ.
- Báo cáo lịch sử diễn giải sai dữ liệu.
- Mock không phản ánh contract mới.

### 12.3. Kế hoạch kiểm thử

- Unit test cho mapping, validation và rounding.
- Contract test với consumer được hỗ trợ.
- Integration test giữa Order và Payment.
- E2E tạo đơn và thanh toán với nhiều currency nếu phạm vi hỗ trợ.
- Test dữ liệu lịch sử và event cũ.
- Test compatibility khi phiên bản cũ và mới chạy song song.
- Regression báo cáo và export.
- Kiểm tra log, metrics và alert cho lỗi parse.

### 12.4. Điều kiện chấp nhận thay đổi

- Contract version và deprecation được xác định.
- Consumer quan trọng đã được kiểm tra.
- Dữ liệu và event lịch sử có cách diễn giải rõ.
- Các test bắt buộc đạt trên artifact mục tiêu.
- Kế hoạch rollout và rollback/recovery được review.
- Giới hạn hoặc consumer chưa xác minh được ghi rõ.

## 13. Những sai lầm thường gặp

1. **Chỉ xem code diff:** bỏ qua consumer, dữ liệu và phụ thuộc gián tiếp.
2. **Đánh giá tác động theo số file:** thay đổi ít dòng vẫn có thể ảnh hưởng nhiều hệ thống.
3. **Không cập nhật test oracle:** test tiếp tục kiểm tra quy tắc cũ.
4. **Chỉ chạy test của component sửa:** bỏ sót contract và hành trình xuyên hệ thống.
5. **Bỏ qua dữ liệu lịch sử:** phiên bản mới hoạt động với dữ liệu mới nhưng lỗi với dữ liệu cũ.
6. **Không xác định owner dependency:** không biết ai xác nhận tương thích.
7. **Coi nâng cấp patch luôn an toàn:** bỏ qua thay đổi mặc định hoặc hành vi thư viện.
8. **Không kiểm tra cấu hình hiệu lực:** chỉ review file trong repository.
9. **Dùng risk score máy móc:** điểm số che giấu rủi ro trọng yếu hoặc thiếu căn cứ.
10. **Bỏ qua độ không chắc chắn:** giả định khu vực chưa hiểu là không bị ảnh hưởng.
11. **Chạy toàn bộ suite không có mục tiêu:** tốn thời gian mà không ưu tiên đường đi rủi ro.
12. **Không ghi lý do bỏ qua regression:** không thể giải thích phạm vi đã xác minh.
13. **Emergency change không có hậu kiểm:** truy vết và test còn thiếu sau triển khai.
14. **Không cập nhật dependency graph:** impact analysis sau tiếp tục bỏ sót cùng khu vực.

## 14. Checklist đánh giá tác động khi yêu cầu, kiến trúc hoặc thành phần phụ thuộc thay đổi

- [ ] Change request có ID, mục tiêu, lý do và owner.
- [ ] Baseline yêu cầu, kiến trúc, API, schema và dependency được xác định.
- [ ] Thay đổi được phân loại theo loại và phạm vi.
- [ ] Tác động trực tiếp và gián tiếp được lần theo.
- [ ] Dependency, consumer, data flow và owner liên quan được xác định.
- [ ] Requirement, acceptance criteria và test oracle được xem xét.
- [ ] Dữ liệu, fixture, migration và trạng thái lịch sử được đánh giá.
- [ ] Tương thích cũ/mới và triển khai song song được xem xét.
- [ ] Rủi ro về chức năng, bảo mật, dữ liệu, hiệu năng và vận hành được đánh giá.
- [ ] Độ không chắc chắn và giả định được ghi rõ.
- [ ] Test được phân loại thành update, add, rerun, review hoặc no impact with rationale.
- [ ] Regression scope được chọn theo dependency và rủi ro.
- [ ] Môi trường và bằng chứng cần thu thập được xác định.
- [ ] Các owner và vai trò review/phê duyệt được phân công.
- [ ] Kế hoạch rollout, rollback hoặc recovery được xem xét khi cần.
- [ ] Kết quả test và quyết định được liên kết với Change ID.
- [ ] Khu vực không kiểm thử có lý do và giới hạn rõ ràng.
- [ ] Sau thay đổi có review lỗi bỏ sót và cập nhật quy trình.

Đánh giá tác động giúp nhóm nhìn vượt ra ngoài phần vừa thay đổi để hiểu những hành vi, thành phần và rủi ro có thể bị ảnh hưởng. Khi dependency được lần theo, test scope được chọn theo rủi ro, giả định được ghi rõ và kết quả được truy vết đến change request, nhóm có thể kiểm thử tập trung hơn mà vẫn bảo vệ các chức năng và thuộc tính chất lượng quan trọng.
