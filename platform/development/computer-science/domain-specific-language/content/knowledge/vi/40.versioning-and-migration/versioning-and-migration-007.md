# Feature flag

**Feature flag** (cờ tính năng) là một cơ chế cho phép bật hoặc tắt một phần hành vi của ứng dụng bằng cấu hình hoặc quyết định tại runtime. Thay vì phải tạo một bản build mới mỗi khi muốn thay đổi tính năng đang hoạt động, hệ thống kiểm tra trạng thái flag rồi chọn nhánh xử lý tương ứng.

Trong chương **Phiên bản và di trú** của DSL, feature flag giúp triển khai thay đổi theo từng giai đoạn, thử nghiệm hành vi mới, chuyển đổi dần giữa hai implementation và khôi phục nhanh khi có sự cố. DSL có thể khai báo flag, default, điều kiện targeting, owner, thời hạn và cách xử lý khi flag không resolve được.

Ví dụ:

~~~text
feature "new-checkout" {
    default = false
    owner = "commerce-team"
    expires = "2027-03-31"
}

workflow Checkout {
    if featureEnabled("new-checkout") {
        run NewCheckoutFlow
    } else {
        run LegacyCheckoutFlow
    }
}
~~~

Đây là cú pháp minh họa. Một hệ thống thực tế có thể lấy trạng thái flag từ file cấu hình, database, control plane hoặc dịch vụ quản lý flag. Điều quan trọng là quyết định flag phải có semantics rõ, được kiểm soát và quan sát được.

## 1. Feature flag là gì?

Feature flag là một điều kiện cấu hình có tên, dùng để quyết định một tính năng hoặc một nhánh hành vi có được thực thi hay không.

~~~text
if featureEnabled("new-search") {
    useNewSearchEngine()
} else {
    useLegacySearchEngine()
}
~~~

Flag có thể được thay đổi mà không cần thay đổi source code, tùy kiến trúc triển khai. Một flag đơn giản có thể chỉ là boolean; flag nâng cao có thể dùng targeting rule, percentage rollout hoặc segment.

### 1.1. Flag và configuration

Configuration thường mô tả giá trị hoặc cách ứng dụng vận hành, ví dụ timeout, endpoint hoặc số worker. Feature flag tập trung vào việc chọn hành vi hoặc phiên bản tính năng.

Một feature flag cũng là configuration, nhưng có vòng đời và yêu cầu quản trị riêng.

### 1.2. Flag và release

Release là phiên bản phần mềm đã được đóng gói và phát hành. Feature flag cho phép code mới có mặt trong release nhưng chỉ được bật cho một nhóm người dùng hoặc môi trường.

Điều này tách thời điểm deploy code khỏi thời điểm công bố tính năng.

### 1.3. Flag và permission

Feature flag quyết định tính năng có được cung cấp theo rollout policy hay không. Permission hoặc authorization quyết định một principal có quyền thực hiện hành động hay không.

Không dùng feature flag thay thế kiểm tra quyền truy cập. Một tính năng đang bật vẫn phải xác thực và authorize request.

### 1.4. Flag và experiment

Experiment thường phân chia người dùng vào các biến thể để đo tác động. Feature flag có thể cung cấp cơ chế phân nhóm, nhưng experiment còn cần assignment stability, metric, hypothesis và phân tích kết quả.

## 2. Vì sao cần feature flag?

Feature flag giúp giảm rủi ro khi thay đổi phần mềm và hỗ trợ nhiều quy trình phát hành.

Các mục đích phổ biến:

- Deploy code trước khi bật tính năng cho người dùng.
- Rollout theo môi trường hoặc nhóm người dùng.
- Bật dần cho tỷ lệ traffic tăng lên.
- Thử nghiệm hai hoặc nhiều biến thể.
- Tắt nhanh tính năng gặp sự cố.
- Chuyển từ implementation cũ sang implementation mới.
- Hỗ trợ migration schema hoặc backend.
- Bật tính năng nội bộ cho nhóm thử nghiệm.
- Quản lý feature có điều kiện theo tenant hoặc region.

### 2.1. Decouple deploy và release

Deploy đưa code vào môi trường. Release làm tính năng có hiệu lực với người dùng. Flag cho phép hai hoạt động này diễn ra ở thời điểm khác nhau.

### 2.2. Controlled rollout

Thay vì bật cho toàn bộ người dùng, có thể bắt đầu với internal users, sau đó một tỷ lệ nhỏ, rồi tăng dần nếu metrics ổn định.

### 2.3. Fast rollback behavior

Nếu nhánh mới gây lỗi, flag có thể được tắt để quay về nhánh cũ mà không cần build và deploy lại, miễn là nhánh cũ vẫn còn trong code và tương thích dữ liệu.

### 2.4. Migration safety

Trong migration, flag có thể điều khiển việc đọc hoặc ghi qua implementation mới, giúp chuyển đổi từng bước và quan sát kết quả.

## 3. Các loại feature flag

Không phải flag nào cũng có cùng mục đích hoặc vòng đời.

| Loại | Mục đích | Vòng đời thường gặp |
|---|---|---|
| Release flag | Giữ tính năng chưa công bố | Ngắn hạn |
| Experiment flag | Chia traffic giữa các biến thể | Theo experiment |
| Operational flag | Điều khiển hành vi vận hành | Có thể dài hạn |
| Kill switch | Tắt nhanh một tính năng hoặc dependency | Cần luôn sẵn sàng |
| Permission flag | Bật khả năng theo gói hoặc entitlement | Dài hạn, cần kiểm tra quyền riêng |
| Migration flag | Điều khiển chuyển đổi dữ liệu hoặc implementation | Có giai đoạn kết thúc |

### 3.1. Release flag

Release flag giữ code mới ở trạng thái tắt cho đến khi đội phát hành sẵn sàng công bố.

### 3.2. Experiment flag

Experiment flag phân phối người dùng vào control và treatment group. Assignment cần ổn định để một người không liên tục đổi biến thể giữa các request.

### 3.3. Operational flag

Operational flag cho phép vận hành điều chỉnh hành vi, ví dụ giảm số worker hoặc tắt một integration đang gặp lỗi.

### 3.4. Kill switch

Kill switch ưu tiên khả năng tắt nhanh. Cần thiết kế đường đọc flag tin cậy và default an toàn khi control plane không truy cập được.

### 3.5. Migration flag

Migration flag điều khiển đọc/ghi giữa hệ thống cũ và mới, hoặc chuyển traffic giữa hai phiên bản backend.

### 3.6. Permission và entitlement

Một entitlement flag có thể biểu diễn tính năng nằm trong gói dịch vụ nào. Tuy nhiên, authorization vẫn phải được thực hiện ở backend; trạng thái hiển thị UI không phải ranh giới bảo mật.

## 4. Boolean flag và multi-variant flag

Boolean flag có hai trạng thái: enabled và disabled. Multi-variant flag trả về một trong nhiều biến thể.

### 4.1. Boolean flag

~~~text
feature "new-invoice" {
    default = false
}
~~~

Boolean phù hợp khi chỉ cần chọn giữa hành vi mới và cũ.

### 4.2. Multi-variant flag

~~~text
feature "search-layout" {
    default = "control"
    variants = ["control", "compact", "expanded"]
}
~~~

Multi-variant flag có thể dùng cho experiment hoặc gradual migration. Cần định nghĩa variant mặc định và behavior khi nhận giá trị không hợp lệ.

### 4.3. Typed flag

Một flag có thể trả số, string hoặc cấu hình có kiểu. Ví dụ:

~~~text
feature "search-limit" {
    type = Integer
    default = 20
}
~~~

Typed flag cần schema, range và validation để tránh giá trị runtime không tương thích.

### 4.4. Không dùng flag thay cho mọi config

Nếu một giá trị thay đổi liên tục và không biểu diễn một quyết định tính năng, có thể phù hợp hơn với configuration thông thường. Quá nhiều flag làm tăng nhánh code và chi phí quản trị.

## 5. Khai báo flag trong DSL

DSL có thể cung cấp declaration block để định nghĩa flag và metadata.

~~~text
feature "new-checkout" {
    type = Boolean
    default = false
    owner = "commerce-team"
    description = "Enable the updated checkout flow"
    category = "release"
    expires = "2027-03-31"
}
~~~

### 5.1. Flag key

Flag key cần duy nhất trong namespace hoặc project. Nên dùng tên mô tả tính năng hoặc mục đích, tránh tên chung như flag1.

### 5.2. Description

Description giải thích flag điều khiển hành vi nào và phạm vi tác động.

### 5.3. Owner

Owner là nhóm hoặc người chịu trách nhiệm bật/tắt, xử lý sự cố và dọn flag sau khi hoàn thành.

### 5.4. Category

Category giúp phân biệt release, experiment, operational và migration flag.

### 5.5. Expiration

Expiration hoặc review date nhắc owner đánh giá flag. Ngày hết hạn không nên tự động xóa flag khi việc xóa có thể thay đổi behavior ngoài dự kiến.

### 5.6. Default value

Default cần được định nghĩa tường minh. Nếu provider không truy cập được, runtime phải có fallback policy rõ ràng.

### 5.7. Scope

Flag có thể có scope global, environment, tenant, user hoặc request. Scope quyết định flag áp dụng cho đối tượng nào và precedence ra sao.

## 6. Đánh giá trạng thái flag

Runtime cần có một API hoặc expression để lấy trạng thái flag.

Ví dụ:

~~~text
if featureEnabled("new-checkout") {
    processNewCheckout()
}
~~~

### 6.1. Boolean evaluation

Hàm evaluation trả true hoặc false theo configuration và targeting rule.

### 6.2. Typed evaluation

Với multi-variant flag, runtime trả variant hoặc typed value. Caller cần xử lý default và unknown variant.

### 6.3. Evaluation context

Evaluation context có thể gồm:

- Environment.
- Tenant ID.
- User ID.
- Region.
- Account plan.
- Application version.
- Request attributes được phép dùng.

Context chỉ nên chứa dữ liệu cần thiết. Không đưa PII hoặc secret vào targeting context nếu không có lý do và kiểm soát phù hợp.

### 6.4. Stable identity

Percentage rollout thường cần một key ổn định như user ID hoặc tenant ID. Nếu dùng random value mới cho mỗi request, cùng người dùng có thể liên tục nhận kết quả khác nhau.

### 6.5. Evaluation consistency

Trong một request hoặc transaction, các lần đọc cùng flag có thể cần trả cùng kết quả. Runtime nên quy định snapshot hoặc evaluation consistency.

### 6.6. Evaluation result metadata

Ngoài giá trị, engine có thể trả reason hoặc metadata như rule nào match, variant được chọn và configuration version. Metadata này hỗ trợ diagnostics nhưng cần redaction.

## 7. Targeting rule

Targeting rule xác định đối tượng nào được bật flag.

Ví dụ:

~~~text
feature "new-checkout" {
    default = false

    targeting {
        environment in ["development", "staging"] -> true
        tenant in ["tenant-alpha", "tenant-beta"] -> true
    }
}
~~~

### 7.1. Environment targeting

Flag có thể bật ở development và staging trước khi bật ở production.

### 7.2. User targeting

Có thể bật cho internal user hoặc tester. Cần dùng identity được xác thực từ backend.

### 7.3. Tenant targeting

Bật tính năng cho một số tenant giúp rollout theo khách hàng hoặc tổ chức.

### 7.4. Region targeting

Một tính năng có thể được bật theo region khi dependency hoặc regulatory requirement khác nhau.

### 7.5. Attribute targeting

Rule có thể dựa trên account plan, client version hoặc thuộc tính nghiệp vụ. Cần validate attribute source và tránh cho client tự gửi giá trị có thể giả mạo.

### 7.6. Rule precedence

Nếu nhiều rule cùng match, DSL cần quy định thứ tự ưu tiên, first-match hoặc cách kết hợp. Nếu không, cùng context có thể tạo kết quả không rõ ràng.

### 7.7. Default rule

Phải có kết quả khi không rule nào match. Default thường được định nghĩa ở flag declaration hoặc policy riêng.

## 8. Percentage rollout

Percentage rollout bật flag cho một tỷ lệ đối tượng.

Ví dụ:

~~~text
feature "new-search" {
    default = false
    rollout {
        percentage = 10
        stickiness = "userId"
    }
}
~~~

### 8.1. Deterministic bucketing

Runtime có thể hash flag key cùng stable identity để đưa đối tượng vào bucket. Cùng identity và cùng rollout configuration sẽ cho bucket ổn định.

### 8.2. Tăng dần tỷ lệ

Một rollout có thể đi từ 1%, 5%, 10%, 25%, 50% đến 100%. Mỗi bước cần có tiêu chí quan sát và điều kiện dừng.

### 8.3. Stickiness

Stickiness xác định đơn vị được phân nhóm: user, tenant, session hoặc device. Chọn key phù hợp với phạm vi trải nghiệm cần ổn định.

### 8.4. Bucket stability

Thay đổi thuật toán hash, salt hoặc bucketing key có thể làm người dùng đổi nhóm. Cần version thuật toán nếu assignment phải ổn định qua release.

### 8.5. Percentage không phải sample size

Tỷ lệ 10% không bảo đảm đủ số người dùng cho phân tích thống kê. Experiment cần tính sample size và thời gian chạy.

### 8.6. Rollout và capacity

Tăng traffic đến backend mới có thể làm quá tải hệ thống dù tỷ lệ phần trăm có vẻ nhỏ. Cần quan sát capacity và dependency load.

## 9. Experiment và variant assignment

Experiment sử dụng flag để phân phối các nhóm đối tượng vào những biến thể khác nhau.

### 9.1. Control và treatment

Control là trải nghiệm chuẩn; treatment là biến thể đang được đánh giá.

~~~text
experiment "checkout-button" {
    variants = {
        control = 50
        green = 25
        compact = 25
    }
    assignmentKey = "userId"
}
~~~

### 9.2. Mutually exclusive experiment

Nếu một người dùng tham gia nhiều experiment có thể ảnh hưởng lẫn nhau, cần namespace hoặc layer để quản lý assignment.

### 9.3. Assignment persistence

Lưu assignment hoặc dùng deterministic bucketing để cùng người dùng tiếp tục ở một variant trong thời gian experiment.

### 9.4. Exposure event

Ghi exposure khi người dùng thực sự được hiển thị hoặc sử dụng treatment, không chỉ khi runtime evaluate flag.

### 9.5. Metric

Experiment cần xác định metric chính, guardrail metric, population và thời gian quan sát trước khi chạy.

### 9.6. Không thay đổi biến thể giữa chừng tùy tiện

Thay tỷ lệ hoặc variant mapping giữa experiment có thể làm assignment thay đổi và ảnh hưởng tính hợp lệ của kết quả. Cần ghi lại configuration revision.

## 10. Flag evaluation và cache

Flag provider có thể nằm trong process hoặc ở dịch vụ từ xa. Cache giúp giảm network call nhưng ảnh hưởng thời gian cập nhật.

### 10.1. Local evaluation

Runtime giữ snapshot flag configuration trong memory và evaluate tại chỗ. Cách này giảm latency và phụ thuộc network khi xử lý request.

### 10.2. Remote evaluation

Runtime gửi context đến service quản lý flag và nhận kết quả. Cách này tập trung policy nhưng tăng network dependency và latency.

### 10.3. Polling

SDK có thể định kỳ lấy configuration mới. Polling đơn giản nhưng thay đổi có độ trễ đến chu kỳ tiếp theo.

### 10.4. Streaming update

Provider có thể đẩy thay đổi đến client qua stream hoặc event channel. Cần reconnect, ordering và snapshot recovery.

### 10.5. Cache TTL

TTL xác định thời gian snapshot được xem là còn hiệu lực. TTL ngắn giúp cập nhật nhanh nhưng tăng tải provider.

### 10.6. Stale configuration

Khi provider unavailable, runtime có thể tiếp tục dùng last-known-good configuration hoặc fallback. Policy phải được chọn theo mức độ rủi ro của flag.

### 10.7. Cache invalidation

Configuration revision hoặc version giúp runtime biết snapshot nào mới hơn và tránh áp dụng event cũ sau event mới.

## 11. Failure mode và default behavior

Feature flag là dependency của ứng dụng. Runtime cần xử lý khi không đọc được provider hoặc nhận configuration không hợp lệ.

### 11.1. Provider unavailable

Các tình huống gồm network timeout, DNS failure, authentication failure, service outage hoặc client chưa load snapshot.

### 11.2. Fail open và fail closed

Fail open cho phép tính năng tiếp tục bật hoặc request tiếp tục đi qua khi evaluation lỗi. Fail closed chọn trạng thái an toàn hơn, thường là disabled hoặc từ chối thao tác.

Không có default đúng cho mọi flag. Ví dụ:

- Một giao diện mới có thể fallback về UI cũ.
- Một thao tác ghi dữ liệu mới có thể cần fail closed.
- Một kill switch cho dependency quan trọng cần có đường tắt đáng tin cậy.

### 11.3. Last-known-good

Runtime có thể giữ snapshot hợp lệ cuối cùng. Cần ghi tuổi snapshot và cảnh báo khi quá cũ.

### 11.4. Unknown flag

Nếu code hỏi flag không được khai báo, runtime cần quy định trả default, báo warning hoặc fail. Với môi trường phát triển, warning có thể giúp phát hiện typo sớm.

### 11.5. Type mismatch

Nếu provider trả string cho flag được khai báo Boolean, runtime cần reject hoặc dùng default theo policy. Không ép kiểu ngầm nếu có thể tạo behavior bất ngờ.

### 11.6. Deterministic fallback

Fallback phải ổn định và được ghi trong declaration hoặc policy. Không nên để mỗi service tự chọn một giá trị fallback khác nhau.

## 12. Kill switch và operational control

Kill switch là flag được thiết kế để tắt nhanh một hành vi có rủi ro hoặc một dependency đang gặp sự cố.

### 12.1. Emergency disable

Kill switch có thể tắt một integration, một endpoint, một workflow hoặc một nhánh xử lý tốn tài nguyên.

### 12.2. Fast propagation

Với kill switch, thời gian từ lúc operator thay đổi đến lúc mọi instance nhận trạng thái mới cần được xác định. Polling chậm có thể không phù hợp với sự cố cần phản ứng nhanh.

### 12.3. Local emergency override

Một runtime có thể hỗ trợ override cục bộ khi control plane không truy cập được. Quyền override cần giới hạn, ghi audit và có cơ chế tự hết hạn.

### 12.4. Fail-safe default

Default của kill switch cần được chọn theo rủi ro. Nếu flag điều khiển một hành động nguy hiểm, khi không thể xác định trạng thái có thể cần dừng hành động.

### 12.5. Test kill switch

Đường tắt phải được kiểm tra định kỳ. Một kill switch chưa từng được thử có thể thất bại đúng lúc cần dùng.

## 13. Feature flag trong migration

Migration thường yêu cầu chuyển dần từ implementation hoặc data model cũ sang mới. Flag giúp điều khiển từng bước.

### 13.1. Branch migration

~~~text
if featureEnabled("new-pricing-engine") {
    result = newPricingEngine.calculate(order)
} else {
    result = legacyPricingEngine.calculate(order)
}
~~~

### 13.2. Shadow read

Hệ thống có thể đọc bằng implementation mới nhưng vẫn dùng kết quả cũ để phục vụ request. Kết quả mới được so sánh và ghi nhận để đánh giá.

### 13.3. Dual write

Trong một số migration, ứng dụng ghi vào hệ thống cũ và mới. Cần xác định thứ tự ghi, xử lý partial failure, idempotency và reconciliation.

### 13.4. Read switch

Sau khi dữ liệu mới được đồng bộ và xác minh, flag có thể chuyển read path sang datastore mới.

### 13.5. Write switch

Write path có thể được chuyển sau khi đã có kế hoạch rollback và xác nhận compatibility.

### 13.6. Remove legacy path

Khi migration hoàn tất và ổn định, xóa flag cùng implementation cũ. Không để hai đường xử lý tồn tại vô thời hạn nếu không còn nhu cầu.

## 14. Backward compatibility và data compatibility

Tắt một flag không đảm bảo hệ thống quay lại trạng thái cũ nếu dữ liệu đã được ghi theo schema mới.

### 14.1. Expand-and-contract

Một migration an toàn thường có các giai đoạn:

1. Expand: thêm field hoặc schema mới nhưng vẫn hỗ trợ schema cũ.
2. Migrate: chuyển dữ liệu và cập nhật consumer.
3. Switch: chuyển traffic sang implementation mới.
4. Contract: loại bỏ field hoặc code cũ sau khi không còn consumer.

### 14.2. Read compatibility

Code mới có thể đọc cả schema cũ và mới trong giai đoạn chuyển đổi. Reference và migration plan cần xác định mapping.

### 14.3. Write compatibility

Nếu cả code cũ và mới cùng ghi, phải bảo đảm format và invariant tương thích. Dual write không tự động bảo đảm consistency.

### 14.4. Rollback compatibility

Trước khi bật flag, cần xác định có thể tắt lại hay không. Nếu code mới đã ghi dữ liệu mà code cũ không đọc được, rollback chỉ bằng flag có thể không an toàn.

### 14.5. Irreversible migration

Nếu migration không thể đảo ngược, cần có backup, recovery plan và approval phù hợp trước khi chuyển traffic.

## 15. Flag dependency và composition

Một tính năng có thể phụ thuộc nhiều flag hoặc capability khác.

### 15.1. Flag dependency

~~~text
feature "new-checkout" {
    requires = ["new-payment-api"]
}
~~~

Nếu new-payment-api bị tắt, new-checkout không được bật.

### 15.2. Dependency graph

~~~text
new-checkout
    |
    v
new-payment-api
    |
    v
payment-token-v2
~~~

### 15.3. Cycle detection

Flag dependency không nên tạo vòng lặp. Compiler hoặc configuration validator có thể phát hiện cycle và báo lỗi.

### 15.4. Composite flag

Composite flag có thể được tính từ nhiều điều kiện:

~~~text
checkoutAvailable =
    featureEnabled("new-checkout")
    and featureEnabled("payment-v2")
    and environment != "maintenance"
~~~

### 15.5. Evaluation order

Nếu dependency có side effect hoặc provider call, cần xác định evaluation order. Tốt hơn nên giữ evaluation thuần và dùng snapshot configuration.

### 15.6. Avoid flag explosion

Quá nhiều flag phụ thuộc lẫn nhau làm behavior khó dự đoán. Có thể gom các điều kiện liên quan vào một capability hoặc policy có tên rõ ràng.

## 16. Flag governance và lifecycle

Feature flag cần owner và kế hoạch kết thúc. Flag tồn tại quá lâu làm tăng số nhánh code và độ phức tạp kiểm thử.

### 16.1. Flag inventory

Một registry có thể lưu:

- Key.
- Description.
- Owner.
- Category.
- Created date.
- Expiration hoặc review date.
- Default.
- Current state.
- Environment scope.
- Related release hoặc migration.

### 16.2. Lifecycle states

Một vòng đời phổ biến:

~~~text
Proposed
   |
   v
Active / Rolling out
   |
   v
Fully enabled
   |
   v
Cleanup scheduled
   |
   v
Removed
~~~

Experiment có thể có trạng thái hoàn tất hoặc archived. Operational flag có thể có vòng đời dài hơn nhưng vẫn cần owner và review.

### 16.3. Expiration

Expiration date là tín hiệu yêu cầu review hoặc cleanup. Hệ thống có thể cảnh báo owner khi đến hạn.

### 16.4. Stale flag

Flag stale là flag không còn cần thiết nhưng vẫn tồn tại trong code hoặc registry. Stale flag làm tăng test matrix và tạo nhánh không được quan sát.

### 16.5. Ownership transfer

Khi team hoặc service owner thay đổi, cần chuyển ownership của flag để không bị bỏ quên.

### 16.6. Change approval

Flag ảnh hưởng thanh toán, bảo mật hoặc dữ liệu quan trọng có thể cần approval trước khi bật ở production.

## 17. Audit và change history

Thay đổi flag có thể làm thay đổi behavior của ứng dụng mà không cần deploy code. Vì vậy cần lịch sử thay đổi.

### 17.1. Audit event

Một event nên ghi:

- Flag key.
- Giá trị trước và sau.
- Environment hoặc scope.
- Actor hoặc service identity.
- Thời điểm.
- Lý do hoặc change ticket.
- Configuration revision.

### 17.2. Who changed what

Audit giúp trả lời ai đã bật flag, khi nào, ở môi trường nào và thay đổi từ trạng thái nào sang trạng thái nào.

### 17.3. Rollback configuration

Có thể khôi phục một revision cấu hình trước đó. Cần xác minh revision cũ vẫn phù hợp với version code hiện tại.

### 17.4. Separation of duties

Người tạo flag có thể khác người phê duyệt hoặc người bật flag production. Quyền nên được giới hạn theo vai trò.

### 17.5. Audit retention

Lịch sử flag cần được giữ theo yêu cầu vận hành và compliance. Không chỉ giữ trạng thái hiện tại nếu cần điều tra incident.

## 18. Security và privacy

Targeting và flag evaluation có thể sử dụng user hoặc tenant attribute. Cần bảo vệ dữ liệu và không để flag trở thành lỗ hổng authorization.

### 18.1. Trusted evaluation context

User ID, tenant ID và role cần đến từ identity context đã xác thực. Không tin trực tiếp giá trị do client tự gửi.

### 18.2. Server-side evaluation

Các quyết định bảo mật hoặc entitlement cần được đánh giá ở server. Client-side flag chỉ nên điều khiển hiển thị và trải nghiệm.

### 18.3. No secret in flag value

Không lưu token, password hoặc private key trong flag value. Flag provider không phải secret manager.

### 18.4. PII minimization

Chỉ truyền attribute cần cho targeting. Không ghi raw user attributes vào evaluation log nếu không cần thiết.

### 18.5. Access control

Giới hạn ai có thể tạo, sửa, bật, tắt và xem targeting rule. Quyền read có thể khác quyền write.

### 18.6. Configuration tampering

Configuration cần được xác thực qua kênh tin cậy, có integrity check hoặc signature khi phù hợp. Client không nên nhận cấu hình từ nguồn không được xác minh.

## 19. Observability và metrics

Flag cần được quan sát để biết nó có được đánh giá, bật và sử dụng đúng như dự kiến hay không.

### 19.1. Evaluation metrics

Có thể theo dõi số lần evaluation, tỷ lệ enabled/disabled, variant distribution, evaluation error và provider latency.

### 19.2. Exposure metrics

Exposure event ghi nhận người dùng thực sự thấy hoặc sử dụng tính năng. Nó khác evaluation count.

### 19.3. Business metrics

Rollout có thể theo dõi conversion, error rate, latency, revenue hoặc metric phù hợp với tính năng.

### 19.4. Guardrail metrics

Guardrail như crash rate, failed transaction hoặc latency giúp phát hiện tác động tiêu cực trong khi rollout.

### 19.5. Correlation

Metrics và trace có thể ghi flag key, variant và config revision để liên kết sự cố với trạng thái rollout.

### 19.6. Cardinality

Không nên dùng user ID hoặc tenant ID làm metric label có cardinality cao. Có thể dùng aggregate hoặc trace attributes có kiểm soát.

## 20. Testing feature flag

Flag tạo nhiều nhánh behavior, vì vậy test cần bao phủ các trạng thái quan trọng.

### 20.1. Test enabled và disabled

Với boolean flag, kiểm tra cả nhánh bật và nhánh tắt.

### 20.2. Test default

Kiểm tra behavior khi flag không được khai báo, provider chưa load hoặc configuration thiếu.

### 20.3. Test targeting

Kiểm tra các context match và không match rule, bao gồm precedence khi nhiều rule cùng đúng.

### 20.4. Test variants

Kiểm tra mọi variant hợp lệ và hành vi với unknown variant.

### 20.5. Test provider failure

Mô phỏng timeout, stale snapshot, invalid payload và authentication failure.

### 20.6. Test deterministic assignment

Kiểm tra cùng identity có nhận cùng bucket trong cùng configuration revision hay không.

### 20.7. Test migration rollback

Kiểm tra việc tắt flag sau khi đã có dữ liệu mới. Đảm bảo implementation cũ có thể đọc dữ liệu hoặc có recovery plan.

### 20.8. Test matrix

Không nên kiểm thử mọi tổ hợp của hàng chục flag nếu không cần. Chọn các combination có dependency hoặc rủi ro cao, đồng thời test invariant quan trọng.

## 21. Flag trong DSL compiler và runtime

Compiler và runtime có thể chia trách nhiệm xử lý flag.

### 21.1. Compile-time declaration

Compiler có thể kiểm tra flag key, type, duplicate declaration, default và dependency graph.

### 21.2. Runtime evaluation

Runtime resolve state theo environment, identity và targeting context.

### 21.3. Static reference checking

Compiler có thể phát hiện code tham chiếu flag chưa được khai báo hoặc khai báo nhưng không được dùng.

### 21.4. Type-safe accessor

DSL có thể sinh accessor có type:

~~~text
flags.newCheckout.enabled(context)
flags.searchLimit.value(context)
~~~

Type-safe accessor giúp giảm typo và type mismatch.

### 21.5. Snapshot semantics

Một execution có thể sử dụng cùng configuration snapshot để tránh flag đổi giữa chừng làm một workflow chạy hai nhánh không nhất quán.

### 21.6. Dynamic refresh

Runtime có thể nhận configuration revision mới. Cần quy định thời điểm revision mới có hiệu lực với request đang chạy và request mới.

## 22. Performance và reliability

Flag evaluation thường nằm trên request path. Nếu thiết kế kém, nó có thể tăng latency hoặc tạo dependency không cần thiết.

### 22.1. Local cache

Local evaluation từ snapshot thường giảm latency và tránh remote call cho mỗi request.

### 22.2. Batch evaluation

Nếu một workflow cần nhiều flag, runtime có thể resolve một context hoặc snapshot chung thay vì gọi provider riêng từng flag.

### 22.3. Avoid repeated evaluation

Nếu cùng một request cần nhiều lần dùng cùng flag, có thể lưu kết quả trong request context để bảo đảm consistency.

### 22.4. Bounded refresh

Polling và streaming cần backoff, jitter và giới hạn reconnect để tránh tạo tải lớn khi provider phục hồi.

### 22.5. Startup readiness

Nếu ứng dụng yêu cầu flag snapshot trước khi nhận traffic, readiness nên chỉ thành công sau khi snapshot hợp lệ đã được load. Nếu cho phép fallback, cần ghi rõ.

### 22.6. Provider redundancy

Flag service có thể cần redundancy, replication và disaster recovery. Tuy nhiên, runtime vẫn nên có behavior xác định khi provider mất kết nối.

## 23. Rollout plan

Rollout nên được thiết kế như một chuỗi bước có điều kiện dừng.

Ví dụ:

~~~text
Internal users
      |
      v
1% production traffic
      |
      v
5% and observe
      |
      v
25% and observe
      |
      v
50% and observe
      |
      v
100% rollout
      |
      v
Remove temporary flag
~~~

### 23.1. Pre-rollout

Kiểm tra code đã deploy, default an toàn, dashboards sẵn sàng, rollback path và owner trực.

### 23.2. Small cohort

Bắt đầu với nhóm nhỏ để quan sát lỗi chức năng và tải.

### 23.3. Guardrail gate

Chỉ tăng tỷ lệ khi error rate, latency và business metric nằm trong ngưỡng đã định.

### 23.4. Pause và rollback

Nếu metric xấu, dừng rollout hoặc tắt flag. Ghi lại configuration revision và lý do.

### 23.5. Completion

Khi đã bật toàn bộ và ổn định, lên kế hoạch xóa flag và nhánh code cũ.

## 24. Flag debt và cleanup

Feature flag tạo thêm nhánh trong code. Nếu không dọn, mỗi thay đổi sau này phải cân nhắc nhiều combination hơn.

### 24.1. Flag debt

Flag debt là chi phí bảo trì do flag tạm thời còn tồn tại lâu, owner không rõ hoặc targeting rule không còn cần thiết.

### 24.2. Cleanup criteria

Một flag có thể được dọn khi:

- Rollout hoàn tất.
- Không còn cần rollback qua flag.
- Data migration đã hoàn tất.
- Metrics ổn định.
- Owner xác nhận nhánh cũ không còn cần.

### 24.3. Remove declaration and branch

Xóa cả flag declaration, accessor, targeting rule, test và documentation liên quan.

### 24.4. Choose permanent behavior

Khi xóa flag, chọn nhánh behavior sẽ trở thành mặc định. Không chỉ xóa điều kiện mà quên kiểm tra side effect và cleanup.

### 24.5. Registry cleanup

Đánh dấu flag archived hoặc removed trong registry để giữ lịch sử và tránh key cũ bị tái sử dụng nhầm.

## 25. Versioning flag configuration

Flag configuration có thể thay đổi độc lập với code release, vì vậy cần version hoặc revision riêng.

### 25.1. Configuration revision

Mỗi thay đổi có thể tạo revision tăng dần hoặc immutable revision ID.

### 25.2. Compatibility with code version

Code version mới có thể tham chiếu flag mới. Nếu config chưa được publish, runtime cần xử lý unknown flag theo policy an toàn.

### 25.3. Rollback revision

Có thể khôi phục revision trước, nhưng cần kiểm tra code hiện tại còn hỗ trợ schema và flag keys trong revision đó.

### 25.4. Schema evolution

Nếu flag provider thay đổi payload schema, SDK và control plane cần versioning để tránh parse sai.

### 25.5. Audit relation

Deployment record và flag revision nên có thể liên kết để điều tra behavior tại một thời điểm.

## 26. DSL example: quản lý rollout và migration

Ví dụ một service chuyển từ pricing engine cũ sang mới:

~~~text
feature "pricing-v2" {
    type = Boolean
    default = false
    owner = "pricing-platform"
    category = "migration"
    expires = "2027-02-28"

    targeting {
        environment == "staging" -> true
        tenant in ["pilot-a", "pilot-b"] -> true
    }

    rollout {
        percentage = 10
        stickiness = "tenantId"
    }
}

service Pricing {
    calculate(order) {
        if featureEnabled("pricing-v2", context) {
            return pricingV2.calculate(order)
        }

        return pricingV1.calculate(order)
    }
}
~~~

Một rollout thực tế có thể thực hiện:

1. Deploy code có cả pricingV1 và pricingV2.
2. Giữ default disabled trong production.
3. Bật ở staging và chạy integration test.
4. Bật cho tenant pilot.
5. Tăng percentage theo guardrail.
6. Theo dõi price difference, latency và error rate.
7. Chuyển 100% khi kết quả ổn định.
8. Xóa pricingV1 và flag sau khi rollback window kết thúc.

### 26.1. Shadow comparison

Trong giai đoạn đầu, có thể tính cả hai kết quả nhưng chỉ trả kết quả cũ:

~~~text
oldResult = pricingV1.calculate(order)
newResult = pricingV2.calculate(order)

recordDifference(oldResult, newResult)
return oldResult
~~~

Shadow execution cần tránh side effect kép. Nếu pricing engine ghi log, tạo event hoặc gọi dịch vụ bên ngoài, cần chế độ read-only hoặc simulation.

### 26.2. Cutover

Khi đã xác nhận kết quả, flag chuyển sang trả kết quả mới. Cần ghi config revision và thời điểm cutover.

### 26.3. Rollback

Nếu pricingV2 có lỗi, tắt flag để quay về pricingV1. Điều này chỉ an toàn nếu dữ liệu và contract vẫn tương thích.

## 27. Troubleshooting feature flag

Khi tính năng không bật như dự kiến, cần tìm nguyên nhân theo từng bước.

### 27.1. Unknown flag

Kiểm tra key, namespace, declaration và configuration đã được publish.

### 27.2. Wrong environment

Kiểm tra environment context thực tế và rule targeting.

### 27.3. User not targeted

Kiểm tra identity, tenant, attributes và rule precedence. Không dùng dữ liệu client chưa xác thực làm căn cứ.

### 27.4. Percentage mismatch

Kiểm tra stable key, hashing algorithm, salt, bucket range và revision.

### 27.5. Stale configuration

Kiểm tra snapshot age, polling interval, stream connection và configuration revision.

### 27.6. Type mismatch

Đối chiếu declared type với provider payload và SDK version.

### 27.7. Cache inconsistency

Kiểm tra instance có đang dùng revision khác nhau không. So sánh metadata và update timestamp.

### 27.8. Flag appears enabled but feature fails

Flag chỉ chọn nhánh code. Vẫn cần kiểm tra dependency, permission, data compatibility và runtime error trong nhánh mới.

## 28. Những sai lầm thường gặp

**Dùng feature flag thay authorization.** Flag không xác định người dùng có quyền thực hiện hành động hay không.

**Không khai báo default.** Khi provider lỗi hoặc flag chưa được publish, behavior có thể khác nhau giữa instance.

**Đánh giá flag qua remote call ở mọi request.** Điều này tăng latency và tạo dependency trực tiếp vào control plane.

**Không dùng stable identity cho rollout.** Người dùng có thể đổi variant liên tục giữa các request.

**Bật percentage mà không theo dõi capacity.** Backend mới có thể quá tải khi traffic tăng.

**Không kiểm tra data compatibility.** Tắt flag sau khi schema mới đã được ghi có thể khiến code cũ không đọc được dữ liệu.

**Dùng dual write mà không reconciliation.** Hai datastore có thể lệch dữ liệu khi một lần ghi thất bại.

**Giữ flag tạm thời quá lâu.** Nhiều nhánh cũ làm tăng chi phí bảo trì và test.

**Không có owner hoặc expiration.** Không ai chịu trách nhiệm kết thúc vòng đời flag.

**Không ghi audit history.** Khó xác định ai thay đổi trạng thái trước incident.

**Để client tự quyết targeting context.** Người dùng có thể giả mạo tenant, role hoặc account plan.

**Thay đổi experiment assignment tùy tiện.** Kết quả đo lường có thể mất tính hợp lệ.

## 29. Ghi nhớ

- Feature flag điều khiển nhánh hành vi tại runtime và giúp tách deploy khỏi release.
- Flag khác permission; authorization vẫn phải được kiểm tra riêng.
- Release, experiment, operational, kill switch, entitlement và migration flag có mục đích và vòng đời khác nhau.
- Flag có thể là boolean, multi-variant hoặc typed value.
- Declaration nên có key, type, default, owner, category, scope và expiration/review date.
- Evaluation context cần dùng identity đáng tin cậy và chỉ chứa attribute cần thiết.
- Targeting rule cần precedence và default behavior rõ ràng.
- Percentage rollout cần deterministic bucketing và stable identity.
- Experiment cần assignment persistence, exposure event, metric và guardrail.
- Local evaluation và cache giảm latency nhưng cần quản lý freshness và invalidation.
- Provider failure cần fallback policy được xác định theo rủi ro.
- Migration flag cần hỗ trợ shadow read, dual write, cutover, rollback và cleanup.
- Data compatibility quyết định rollback có an toàn sau khi ghi dữ liệu mới hay không.
- Flag configuration cần versioning, audit, access control và observability.
- Flag tạm thời cần được dọn sau rollout để giảm flag debt.

## 30. Câu hỏi tự kiểm tra

1. Feature flag là gì và giúp tách deploy khỏi release như thế nào?
2. Feature flag khác permission hoặc authorization ở điểm nào?
3. Phân biệt release flag, experiment flag, operational flag, kill switch và migration flag.
4. Boolean flag, multi-variant flag và typed flag khác nhau như thế nào?
5. Một flag declaration nên có metadata nào?
6. Evaluation context cần những thuộc tính nào và vì sao phải dùng identity đáng tin cậy?
7. Targeting rule và rule precedence hoạt động như thế nào?
8. Deterministic bucketing và stickiness giúp rollout ổn định ra sao?
9. Exposure event khác evaluation event như thế nào?
10. Local evaluation, remote evaluation, polling và streaming có trade-off nào?
11. Fail open, fail closed và last-known-good khác nhau như thế nào?
12. Kill switch cần những đặc tính nào để hữu ích khi có incident?
13. Shadow read và dual write hỗ trợ migration như thế nào?
14. Vì sao rollback qua flag có thể không an toàn sau schema migration?
15. Làm thế nào quản lý flag dependency và phát hiện dependency cycle?
16. Audit history nên lưu những thông tin gì khi flag thay đổi?
17. Những metrics nào cần theo dõi khi rollout?
18. Vì sao cần expiration, owner và cleanup cho temporary flag?
19. Hãy thiết kế rollout plan cho một implementation mới từ staging đến 100% production.
20. Hãy mô tả quy trình kiểm thử và rollback một migration được điều khiển bằng feature flag.
