# Thay đổi rule tương thích ngược mà vẫn giữ an toàn nghiệp vụ

Thay ngưỡng phê duyệt từ 20 triệu xuống 5 triệu có thể chỉ là sửa một con số. Trong hệ thống đang chạy, thay đổi đó tác động đến API cũ, các instance chưa cập nhật, worker xử lý hàng đợi, giao dịch đang chờ và cả phiên bản dùng để rollback. Nếu mỗi thành phần hiểu rule khác nhau, một yêu cầu bị instance mới chặn có thể được instance cũ cho qua.

**Backward compatible rule change** là cách thay đổi quy tắc sao cho các thành phần và dữ liệu cần được hỗ trợ vẫn phối hợp có kiểm soát trong quá trình chuyển đổi. Với Business Logic Security, phải chỉ rõ cả hành vi nghiệp vụ và mức bảo vệ nào bắt buộc được giữ ở từng giai đoạn. Tương thích không có nghĩa mọi hành vi từng được cho phép đều phải tiếp tục được cho phép.

Bài thuộc chương **Deployment Operations**, tập trung vào business invariants, state machine, quyền theo đối tượng, transaction, idempotency và kiểm thử lịch triển khai có thể bị lạm dụng. Ví dụ payout dưới đây là fixture kỹ thuật, không phải hướng dẫn tài chính hoặc quy định pháp lý. Các thuật toán là thiết kế minh họa; không giả định một feature flag hoặc công cụ deploy tự cung cấp toàn bộ bảo đảm.

## 1. Tương thích phải được đánh giá ở nhiều lớp

| Lớp | Câu hỏi cần trả lời | Lỗi thường gặp |
|---|---|---|
| API/contract | Client cũ gửi/đọc dữ liệu còn được xử lý rõ nghĩa không? | Thêm trạng thái enum làm client cũ crash |
| Schema/dữ liệu | Binary cũ và mới đọc/ghi dữ liệu lẫn nhau ra sao? | Binary cũ hiểu field thiếu là đã duyệt |
| Event/protocol | Producer mới và consumer cũ phối hợp thế nào? | Consumer bỏ field approval bắt buộc rồi vẫn thực thi |
| Quy tắc nghiệp vụ | Yêu cầu mới và đang chờ áp dụng rule nào? | Lấy rule theo instance ngẫu nhiên nhận request |
| Bảo mật | Sau cutover, đường nào vẫn có thể bỏ qua kiểm tra mới? | Retry sang node cũ để né phê duyệt |
| Rollback | Binary đích còn hiểu dữ liệu và gate hiện hành không? | Hạ code làm mở lại lỗ hổng vừa chặn |

Hai bản chạy đúng khi đứng riêng chưa chứng minh chúng chạy đúng khi cùng tồn tại. Dữ liệu mới cũng có thể làm rollback thất bại dù deploy ban đầu không lỗi. [AWS: Ensuring rollback safety during deployments](https://aws.amazon.com/builders-library/ensuring-rollback-safety-during-deployments/) trình bày vấn đề reader/writer khác phiên bản và kỹ thuật chuẩn bị khả năng đọc trước khi kích hoạt cách ghi mới.

Trong bài, **compatibility** là tập cam kết được viết rõ: phiên bản nào được phục vụ action nào, dữ liệu nào có thể đọc, rule nào được cưỡng chế và rollback tới đâu. Không chỉ là “API vẫn trả 200”.

## 2. Fixture: hạ ngưỡng bắt buộc có người duyệt độc lập

### 2.1. Rule R1 và R2

Một ứng dụng có chức năng tạo yêu cầu chi trả cho người nhận đã đăng ký. Mọi số tiền trong fixture dùng VND theo số đồng, không áp dụng phép quy đổi currency.

| Điều kiện thực thi | Rule R1 | Rule R2 |
|---|---|---|
| Tenant/object access, quyền chức năng | Bắt buộc | Bắt buộc |
| Số tiền và người nhận lấy từ nội dung server đã xác nhận | Bắt buộc | Bắt buộc |
| Revision được duyệt phải khớp nội dung thực thi | Khi cần approval | Khi cần approval |
| Người duyệt độc lập với người tạo | Amount từ 20.000.000 trở lên | Amount từ 5.000.000 trở lên |
| Trạng thái hợp lệ, giữ hạn mức và chống thực thi trùng | Bắt buộc | Bắt buộc |

Ngưỡng dùng phép so sánh `>=`. Ví dụ 5.000.000 cần duyệt theo R2; 4.999.999 không cần điều kiện duyệt theo ngưỡng này, nhưng vẫn phải qua các invariant còn lại. “Không cần người duyệt độc lập theo ngưỡng” không có nghĩa được bỏ authorization.

Fixture có operation ID ổn định và các trạng thái đã tồn tại từ trước:

```text
PENDING -> EXECUTING -> SUCCEEDED
                    -> FAILED, khi biết chắc không có hiệu lực thành công
```

PENDING có thể đang chờ người duyệt hoặc chưa được claim để thực thi. EXECUTING gồm cả trường hợp provider chưa trả kết quả chắc chắn; timeout không tự cho phép chuyển sang FAILED và tạo payout khác.

### 2.2. Chọn rõ semantics cho giao dịch đang dở

Thiết kế của bài chọn quy tắc sau:

- Operation chưa được claim thực thi trước cutover phải qua R2 tại execution gate, dù được tạo theo R1.
- Operation đã được claim thực thi hợp lệ trước cutover tiếp tục theo nghĩa vụ đã chấp nhận và dùng cùng operation ID để đối soát; không tự tạo một lần chi trả mới.
- Operation đã SUCCEEDED giữ nguyên kết quả lịch sử.
- Dữ liệu không đủ chứng minh trạng thái/approval phải được giữ lại để xử lý có kiểm soát; không mặc định là đã được duyệt.

**Execution claim** ở đây là transaction chuyển PENDING sang EXECUTING và ghi ý định gửi provider đã commit, không chỉ là worker đọc được một message. Đây là ranh giới được thiết kế cho fixture, không đồng nghĩa tiền đã được chuyển.

Theo đó, payout 8.000.000 đang PENDING trước cutover sẽ phải chờ duyệt độc lập dưới R2. Payout cùng amount đã được claim trước cutover không bị phát sinh operation mới khi retry sau cutover.

Một sản phẩm có thể chọn semantics khác, nhưng phải có lý do, phạm vi và cách kiểm chứng. Nếu yêu cầu là không được gửi bất kỳ lệnh nào tới provider sau cutover khi thiếu duyệt, gate tại database chưa đủ: cần thêm cơ chế pause/fence/đánh giá ở ranh giới dispatch và xử lý các lệnh đã gửi nhưng chưa rõ kết quả.

### 2.3. Invariant vận hành

```text
BC-01: Không phiên bản nào được bỏ tenant/object access hoặc sửa nội dung nhạy cảm.
BC-02: Operation chưa claim phải theo rule thực thi đang có hiệu lực trong scope.
BC-03: Activation và execution claim có thứ tự xác định, không dựa vào giờ client.
BC-04: Retry/redelivery/rollback không tạo hiệu lực thứ hai cho cùng nghĩa vụ.
BC-05: Không hiểu rule hoặc thiếu bằng chứng không được chuyển thành cho phép.
BC-06: Binary rollback vẫn đọc được dữ liệu và cưỡng chế mức bảo vệ hiện hành.
```

## 3. Phân biệt version của code, contract, rule và dữ liệu

Một nhãn `v2` chung dễ gây nhầm. Nên tách ít nhất:

| Định danh | Ý nghĩa |
|---|---|
| Binary/build version | Code thực sự đang chạy |
| API/event schema version | Cấu trúc và semantics giao tiếp |
| Rule version/hash | Nội dung policy cụ thể, bất biến |
| Activation epoch | Số thế hệ kích hoạt tăng đơn điệu trong scope |
| Resource/content revision | Phiên bản dữ liệu được kiểm tra hoặc được duyệt |
| Operation ID/idempotency binding | Ý định/nghĩa vụ dùng để xử lý retry và hiệu lực |

Binary mới có thể vẫn cưỡng chế R1 khi chưa activation; binary chuẩn bị có thể hiểu cả R1 và R2. Rule mới không nhất thiết cần API major version mới nếu hình dạng và cách xử lý workflow vẫn tương thích với hợp đồng cũ.

Ví dụ bundle rule bất biến có thể được mô tả như sau:

```json
{
  "ruleId": "payout-execution",
  "ruleVersion": "R2",
  "bundleHash": "sha256:<digest-of-canonical-bundle>",
  "formatVersion": 1,
  "requiredCapability": "independent-review-v2",
  "independentReviewThresholdMinor": 5000000,
  "currency": "VND"
}
```

Đây là cấu trúc minh họa, không phải format chuẩn. Bundle được kiểm tra và lưu server-side; client không tự chọn R1 bằng header. Hash chỉ phát hiện nội dung có khớp reference hay không, không tự chứng minh người phát hành được phép thay policy.

Cấu hình activation gắn scope với đúng bundle và epoch, ví dụ TENANT-A, epoch 42, R2. Một lần đánh giá dùng snapshot bundle nhất quán; không đọc ngưỡng từ R2 rồi ghi audit rằng đã dùng R1.

## 4. Mở rộng contract và schema trước khi bật rule

### 4.1. Expand: thêm khả năng đọc nhưng chưa thay hành vi thực thi

Có thể thêm metadata về admission và execution vào operation. Ví dụ DDL PostgreSQL tối giản:

```sql
ALTER TABLE payout_operation
    ADD COLUMN accepted_rule_version text,
    ADD COLUMN accepted_rule_hash text,
    ADD COLUMN execution_rule_version text,
    ADD COLUMN execution_epoch bigint,
    ADD COLUMN review_requirement text;
```

Đây là phác thảo migration, không phải schema hoàn chỉnh để chạy nguyên xi trong production. Tên bảng/cột, kích thước, index, constraint, transaction migration và lock budget phải theo hệ thống thật. Thêm field nullable giúp biểu diễn dữ liệu cũ chưa có bằng chứng, nhưng NULL không được hiểu là đủ quyền hoặc đã duyệt.

PostgreSQL có các mức khóa khác nhau cho `ALTER TABLE`; nhiều thao tác cần khóa mạnh. Vì vậy thay đổi additive vẫn cần kế hoạch thời gian khóa, giám sát và xử lý timeout. Xem [PostgreSQL: ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html).

Một reader mới cần hiểu ít nhất:

```text
metadata có và hợp lệ   -> xử lý theo protocol đã biết
metadata legacy đã biết nguồn gốc -> dùng adapter legacy có phạm vi rõ ràng
metadata thiếu/không rõ -> giữ để phân loại hoặc đối soát; không tự permit
version chưa hỗ trợ    -> không claim hiệu lực, chuyển xử lý có kiểm soát
```

Thêm cột vẫn có thể làm hỏng code dùng `INSERT ... VALUES` không liệt kê tên cột, mapper phụ thuộc thứ tự hoặc serializer quá chặt. Kiểm tra cả cách đọc lẫn cách ghi của các binary còn nằm trong cửa sổ hỗ trợ.

### 4.2. Không bổ sung trạng thái enum theo cách client cũ không hiểu

Với fixture, API cũ đã hiểu PENDING là chưa hoàn tất, có thể chờ xử lý. Vì vậy operation thiếu duyệt dưới R2 vẫn trả trạng thái PENDING; adapter cho client mới có thể cung cấp chi tiết `reviewRequired`, nếu contract của client đó hỗ trợ.

Đây chỉ tương thích nếu PENDING thật sự đã có semantics như vậy. Nếu client cũ hiểu PENDING là “chắc chắn tự động hoàn tất, không có bước người dùng”, cần cập nhật client hoặc version contract; không thể che thay đổi nghiệp vụ bằng đổi tên trạng thái.

Không mặc định mọi client đều bỏ qua JSON field lạ. Kiểm thử client thật hoặc version adapter. Đối với consumer thực thi, việc bỏ qua field bảo mật bắt buộc rồi tiếp tục là đặc biệt nguy hiểm; version không hiểu phải được chặn khỏi execution.

### 4.3. Backfill không được tạo bằng chứng giả

Không điền `accepted_rule_version=R2` hoặc `review_requirement=SATISFIED` cho mọi hàng chỉ để xóa NULL. Nhãn phiên bản không phải bằng chứng approval.

Có thể phân loại dữ liệu bằng nguồn đáng tin cậy: lịch sử operation, thời điểm/epoch authoritative đã ghi, revision, người duyệt và kết quả provider. Với bản ghi legacy không đủ dữ kiện, giữ trạng thái cần xem xét và có tiến trình xử lý riêng.

Backfill theo batch có checkpoint, có thể chạy lại và không ghi đè hàng đã được transaction nghiệp vụ cập nhật. Ví dụ dùng version/điều kiện “metadata vẫn chưa có” tại bước ghi; conflict thì đọc lại. Không để job backfill hồi sinh approval đã bị thu hồi hoặc sửa operation đã SUCCEEDED.

### 4.4. Contract: chỉ thu hẹp sau cửa sổ tương thích

Sau khi các writer/reader cũ đã rút và dữ liệu cần dùng có semantics hợp lệ, mới siết constraint hoặc loại bỏ field/adapter legacy. Cần tính cả worker ngủ lâu, cron job, event bị trì hoãn, DLQ replay và bản backup/restore có thể được đưa lại vào vận hành.

Nếu giữ adapter legacy lâu hơn, nó vẫn phải bị giới hạn khỏi các hành động mới không đủ bằng chứng. “Đọc được dữ liệu cũ” không đồng nghĩa “được thực thi dữ liệu cũ theo rule đã lỗi thời”.

## 5. Tách rollout binary khỏi activation rule

### 5.1. Ba thế hệ binary trong ví dụ

| Binary | Khả năng | Vai trò sau khi R2 active |
|---|---|---|
| B0 cũ | Chỉ hiểu R1, chưa có execution epoch/gate mới | Không được claim payout mới |
| B1 chuẩn bị | Hiểu schema cũ/mới, R1/R2, epoch và cách giữ yêu cầu chờ duyệt | Được phục vụ và là đích rollback an toàn đã kiểm chứng |
| B2 hoàn thiện | Có trải nghiệm/triển khai mới, giữ protocol và gate bắt buộc | Phục vụ chính khi rollout hoàn tất |

B1 phải thật sự có đủ logic cưỡng chế R2 và xử lý dữ liệu R2, không chỉ bỏ qua field chưa hiểu. Nếu B1 thiếu khả năng đó, nó không phải đích rollback phù hợp.

Trình tự khái quát:

```text
R1 đang active
    -> expand schema/protocol
    -> deploy B1, vẫn thực thi R1
    -> kiểm chứng mọi executor và rollback target có khả năng cần thiết
    -> loại B0 khỏi các đường có thể claim thực thi
    -> shadow/canary theo phạm vi được phép
    -> activate R2 tại control plane authoritative
    -> deploy/hoàn tất B2 nếu cần
    -> hết cửa sổ hỗ trợ mới contract legacy
```

Mô hình này áp dụng ý tưởng prepare trước activate vào policy bảo mật. Điểm riêng của fixture là ngoài đọc/ghi dữ liệu, bản chuẩn bị còn phải cưỡng chế được gate thực thi mới.

### 5.2. “100% API đã deploy” chưa đủ

Phải kiểm kê cả consumer, worker chạy theo lịch, retry processor, công cụ quản trị, script hỗ trợ và region ít traffic. Một instance B0 không còn nhận HTTP vẫn có thể đọc message và gọi provider.

Báo cáo capability từ instance có ích cho vận hành nhưng không tự là rào chắn bảo mật. Cần cơ chế khiến executor không đủ khả năng không thể tạo hiệu lực: thu hồi quyền claim/dispatch, tách queue/route hoặc buộc qua execution service/gateway đã hỗ trợ gate. Cách cụ thể phụ thuộc kiến trúc.

Nếu B0 vẫn có credentials gọi provider trực tiếp và không kiểm tra epoch, chỉ nâng một con số `minimumEpoch` trong database sẽ không ngăn nó. Phải xử lý đường đi đó trước activation. Sau activation, hệ thống autoscaling hoặc rollback tự động cũng không được khởi động lại B0 với quyền thực thi.

### 5.3. Feature flag là cơ chế phân phối, không phải nguồn quyền tùy client

Flag có thể chọn bundle cho một cohort server-side hoặc bật chế độ quan sát. Scope/canary assignment phải được xác định từ dữ kiện đã xác minh và giữ ổn định; không để caller đổi header, tenant tự khai hoặc request ID để tìm nhánh dễ hơn.

[OpenFeature: Evaluation Context](https://openfeature.dev/specification/sections/evaluation-context/) mô tả context phục vụ targeting và các mức context có thứ tự ghi đè. Trong thiết kế authorization, phải kiểm soát nguồn và quyền ghi các field đó; context do thư viện nhận không tự là context đã được xác thực.

Không dùng fallback kiểu “flag service lỗi thì trở về R1”. Nếu R2 đã là mức bảo vệ bắt buộc cho scope, fallback chỉ được tiếp tục khi chứng minh có bundle và activation hợp lệ theo semantics đã thiết kế; nếu không, giữ/chặn các execution mới có liên quan.

Một cache bundle bất biến có hash đã xác minh khác với cache activation. Bundle cũ còn trên đĩa không chứng minh R1 vẫn đang có hiệu lực. Eventual consistency của flag delivery không tự thỏa điều kiện cutover đồng nhất.

## 6. Đặt execution gate tại ranh giới nhất quán với activation

### 6.1. Một race mà flag cục bộ không giải quyết

```text
Worker W đọc active=R1 từ cache
Control plane activate R2
Worker W cho payout 8 triệu qua mà không có người duyệt
Worker W commit execution claim
```

Dù cache chỉ chậm vài giây, BC-02 đã bị vi phạm nếu claim diễn ra sau cutover theo semantics của fixture. So sánh timestamp request với giờ deploy cũng không tạo thứ tự nhất quán khi các node có clock khác nhau hoặc request đợi khóa.

Một phương án minh họa là lưu activation authoritative theo tenant trong database và đồng bộ execution claim với cập nhật activation trên cùng hàng. Worker giữ khóa đọc phù hợp trên hàng policy đến hết transaction claim; activation cần khóa cập nhật xung đột trên hàng đó. Các claim R1 đã giữ khóa hoàn tất trước khi activation commit, hoặc worker đọc R2 sau activation.

Với PostgreSQL, `SELECT ... FOR SHARE` và cập nhật hàng có quan hệ khóa cần thiết cho cách tổ chức này; cần dùng đúng transaction/isolation và xử lý lỗi cạnh tranh. Tham khảo [PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html). Đây là một thiết kế mẫu, không phải bảo đảm tự có chỉ vì bật `@Transactional`.

### 6.2. Mã giả của worker đã có khả năng R2

```text
claimExecution(tenantId, operationId, serviceIdentity):
    require trusted service identity and permitted execution scope

    in database transaction:
        activation = lockAuthoritativeTenantPolicy(tenantId)
        bundle = resolveExactImmutableBundle(activation.version, activation.hash)
        require executor supports bundle.requiredCapability

        operation = lockOperation(tenantId, operationId)
        require object access for the requested action

        if operation is already EXECUTING or terminal:
            return authorized existing operation/attempt result

        require operation is PENDING
        facts = loadProtectedBusinessAndApprovalFacts(operation)
        decision = evaluateExecution(bundle, facts)

        if decision requires independent review:
            persist PENDING with internal review requirement and activation epoch
            append audit of HOLD
            return HOLD, without a provider command

        require decision permits execution
        require content, funds, approval and concurrency guards still hold

        create unique execution obligation/attempt identity
        move operation to EXECUTING
        store execution_rule_version, execution_epoch and decision evidence
        append ProviderPayoutRequested outbox using server snapshot
        commit all local changes together

    dispatch only committed provider intent using the same operation identity
```

Các helper ở đây là hợp đồng thiết kế, không phải API thư viện. Nhánh HOLD commit thông tin chờ xử lý có kiểm soát; nó không commit execution claim hoặc lệnh provider. Nếu bundle không hợp lệ hoặc thiếu facts, worker không được biến lỗi thành PERMIT.

Quyền đọc kết quả/replay phải được kiểm tra cả khi operation đã EXECUTING hoặc terminal. Service identity có quyền kỹ thuật xử lý queue cũng không được tự đổi amount, người nhận hoặc revision. Nếu policy yêu cầu kiểm tra lại quyền của requester ban đầu trước execution, facts và cơ chế thu hồi phải đáp ứng yêu cầu đó.

Approval, ACL, hạn mức hoặc balance ở hàng khác không được bảo vệ chỉ bởi khóa hàng policy. Cần khóa/version/conditional update tương ứng cho các invariant đó và giao thức chung giữa mọi writer. Đặt thứ tự khóa nhất quán để giảm deadlock; khi retry do conflict, đọc và đánh giá lại toàn bộ facts cần thiết.

### 6.3. Ranh giới claim khác ranh giới gửi provider

Trong fixture, claim đã commit dưới R1 trước activation được xem là nghĩa vụ đang thực thi và có thể được gửi sau đó. Lựa chọn này phải được ghi rõ vì outbox có thể bị chậm; nó không thỏa yêu cầu chặt hơn “sau thời điểm T không được gửi lệnh thiếu duyệt”.

Nếu cần yêu cầu chặt hơn, điều phối pause dispatch, kiểm kê outbox chưa gửi và đặt gate tại dispatcher/provider gateway theo protocol mới. Các lệnh đã gửi hoặc timeout cần đối soát theo operation, không được mặc định chưa có hiệu lực. Không thể dùng rollback database để thu hồi một lệnh mà provider đã thực hiện.

Trong hệ thống nhiều region/database độc lập, khóa một hàng ở một database không tạo cutover toàn cục. Cần phân scope rõ ràng hoặc có control plane/gate đủ nhất quán cho phạm vi toàn cục đã cam kết. Khi không liên lạc được nguồn quyết định, hành động nhạy cảm cần được giữ/chặn theo policy đã thiết kế.

## 7. Giữ idempotency và nghĩa vụ ổn định qua các phiên bản

### 7.1. Rule version không tự tạo ý định mới

Một request được chấp nhận trước cutover phải tiếp tục được nhận diện sau cutover. Scope như `(tenant, actor, action, key)` cần giữ semantics ổn định. Không đổi action từ `PAYOUT_CREATE` sang `PAYOUT_CREATE_V2` rồi để cùng key sinh operation thứ hai.

Fingerprint biểu diễn ý định: đối tượng/quote, revision, amount, currency và người nhận theo hợp đồng. Rule được server chọn để đánh giá là metadata quyết định; không tự nhét rule hiện tại vào fingerprint làm retry cùng nội dung trở thành request khác sau deploy.

Nếu thật sự đổi semantics command hoặc cách chuẩn hóa, lưu fingerprint/contract version và hỗ trợ đọc binding cũ. Hai dạng biểu diễn chỉ được quy về cùng ý định khi chứng minh tương đương về nghiệp vụ; không bỏ amount hoặc người nhận khỏi fingerprint để dễ tương thích.

### 7.2. Retry phải trả operation cũ, không vượt gate mới

Ví dụ payout 8 triệu được tạo dưới R1 nhưng chưa claim. Sau R2, client retry cùng key/intent:

```text
access check hiện tại
    -> lookup binding cũ
    -> xác nhận cùng ý định
    -> trả cùng operation ID và trạng thái PENDING/chờ duyệt hiện tại
```

Replay của bước tạo không phát sinh execution. Khi worker claim operation đó, gate R2 vẫn yêu cầu approval. Không dùng nhánh “đã accepted dưới R1” làm căn cứ bỏ qua rule hiện hành đối với PENDING.

Nếu operation đã EXECUTING trước cutover, retry theo cùng operation/attempt identity để đối soát hoặc hoàn tất protocol đang thực thi. Không tạo lệnh chi trả khác chỉ vì code hoặc rule đã đổi. Với callback, xác thực nguồn, đối chiếu amount/currency/account và xử lý chuyển trạng thái idempotent.

Idempotency key không thay ràng buộc theo nghĩa vụ. Hai key khác nhau cho cùng khoản phải trả vẫn cần business obligation ID và constraint thích hợp. Uniqueness, reservation và outbox cũng phải tiếp tục có tác dụng khi B1 và B2 ghi đồng thời.

### 7.3. Message cũ không phải giấy phép thực thi cũ

Một message R1 có thể chỉ là tín hiệu “operation này cần được xử lý”. Consumer nạp operation authoritative rồi dùng activation hiện hành để claim nếu còn PENDING; không tin `approved=true` trong message cũ.

Nếu message đại diện cho execution claim đã commit, consumer phải kiểm chứng reference/evidence và tiếp tục đúng nghĩa vụ theo semantics mục 2.2. Không đánh đồng hai loại message rồi áp dụng một adapter mặc định cho phép.

Message không rõ schema/capability được giữ để xử lý, không ack mất nghĩa vụ hoặc dịch ngầm thành lệnh mới. DLQ replay sau vài tuần vẫn phải đi qua các gate hiện hành phù hợp với loại message.

## 8. Shadow và canary để đo thay đổi mà không tạo hiệu lực phụ

Shadow có thể tính R1 và R2 trên cùng facts để phân loại:

| Kết quả | Ý nghĩa cần điều tra |
|---|---|
| Cùng cho phép | Không có khác biệt quan sát được ở case này |
| R1 cho phép, R2 giữ/chặn | Kỳ vọng với payout 5 đến dưới 20 triệu thiếu duyệt, hoặc regression |
| R1 chặn, R2 cho phép | Cần xem đây có phải mở quyền ngoài ý định không |
| Một bên lỗi/thiếu facts | Không so thành “cho phép”; kiểm tra dữ kiện, bundle và capability |

Shadow evaluator không ghi reservation, chuyển state, tiêu thụ approval hoặc gọi provider. Phải dùng cùng facts/time snapshot khi so sánh để tránh quy sai khác biệt dữ liệu thành khác biệt rule.

Canary chọn scope ổn định do server quản lý, ví dụ tenant/nhóm nghĩa vụ đã được chấp thuận. Hệ thống phải biết rule authoritative của scope; không chọn lại ngẫu nhiên theo mỗi request khiến caller retry để tìm R1.

Nếu R2 là biện pháp bắt buộc để chặn lỗ hổng ngay lập tức, không duy trì R1 cho phần traffic còn lại chỉ để thử nghiệm tăng dần. Khi chưa đủ khả năng enforce, có thể cần giữ/chặn action liên quan và triển khai gate trước; kế hoạch khả dụng phải phản ánh điều đó.

Quan sát shadow giúp phát hiện lỗi nhưng không chứng minh không có bypass. Vẫn cần kiểm kê executor, kiểm thử mixed-version và gate tại nơi tạo hiệu lực.

## 9. Runbook chuyển từ R1 sang R2

### 9.1. Điều kiện chuyển từng giai đoạn

Runbook phải gắn với action và scope cụ thể. Bảng sau minh họa một tenant dùng execution gate tại database như mục 6; hệ thống nhiều scope có thể chuyển từng scope khi các điều kiện độc lập thực sự được đáp ứng.

| Giai đoạn | Công việc chính | Bằng chứng cần có trước khi đi tiếp |
|---|---|---|
| Chuẩn bị hợp đồng | Chốt ngưỡng, cách xử lý PENDING/EXECUTING, quyền, revision và thời điểm cutover có hiệu lực | Có danh sách invariant BC-01 đến BC-06 và cách quan sát từng invariant |
| Expand | Thêm cấu trúc dữ liệu và khả năng đọc metadata mới | Các reader/writer còn hỗ trợ đọc/ghi đúng; dữ liệu thiếu không bị hiểu là permit |
| Deploy B1 | Đưa binary hiểu R1/R2, gate và dữ liệu mới lên các executor cần thiết, vẫn giữ activation R1 | Có danh sách executor theo đường gọi; B1 đã được kiểm chứng là đích rollback phù hợp |
| Chặn đường B0 | Rút quyền thực thi của binary không hỗ trợ, xử lý worker ngủ lâu và cấu hình tự khởi động | B0 không còn đường claim hoặc gọi provider ngoài kiểm soát; không chỉ dựa vào báo cáo version |
| Chuẩn bị dữ liệu và lưu lượng | Phân loại legacy, chạy shadow và canary khi phù hợp phạm vi bảo mật | Các khác biệt có giải thích; dữ liệu chưa rõ có nơi giữ và người xử lý; không sinh tác dụng từ shadow |
| Activate R2 | Ghi bundle/hash và epoch mới qua control plane có thẩm quyền, phối hợp với execution claim | Có bản ghi activation đã commit và bằng chứng executor dùng đúng ranh giới nhất quán |
| Theo dõi và hoàn tất B2 | Quan sát quyết định, nghĩa vụ, backlog và provider; mở rộng phạm vi đủ điều kiện | Không có bypass mới; command cũ vẫn nhận diện được; phương án B2 về B1 còn dùng được |
| Contract | Gỡ adapter hoặc siết constraint sau khi hết nhu cầu hỗ trợ | Không còn reader/writer hay đường replay cần semantics cũ, hoặc có adapter bị giới hạn rõ ràng |

Không dùng một khoảng chờ cố định để thay cho xác nhận đã chặn B0. Một worker không phát heartbeat vẫn có thể thức dậy với credentials cũ. Nếu chưa chứng minh được hàng rào thực thi cho scope, giữ action liên quan ở trạng thái có kiểm soát thay vì bật rule rồi hy vọng rollout đã đủ.

Việc activation cũng cần quyền theo action/scope, kiểm tra phiên bản cấu hình nguồn và audit. Hai người vận hành gửi thay đổi đồng thời không được âm thầm ghi đè nhau. Request activation retry sau khi mất response phải tra được cùng kết quả hoặc gặp xung đột rõ ràng; không tạo liên tiếp nhiều lần thay đổi không thể truy nguyên.

### 9.2. Đọc timeline theo commit, không theo lúc request tới

Giả sử tenant đang dùng R1 ở epoch 41. X và Y đều là payout 8.000.000 đồng chưa có người duyệt độc lập. X và Y có operation ID khác nhau và đủ các điều kiện khác của fixture.

| Thứ tự quan sát được | Sự kiện | Ý nghĩa nghiệp vụ |
|---|---|---|
| 1 | Worker X giữ khóa policy R1 và bắt đầu transaction claim | X chưa được coi là đã claim cho tới khi transaction commit |
| 2 | Control plane yêu cầu activate R2 nhưng phải chờ khóa xung đột | Yêu cầu activation đã tới chưa có nghĩa R2 đã có hiệu lực |
| 3 | X commit EXECUTING cùng execution identity và outbox dưới epoch 41 | X trở thành nghĩa vụ đã claim hợp lệ trước cutover theo semantics đã chọn |
| 4 | Activation commit R2, epoch 42 | Đây là ranh giới cutover authoritative của scope trong thiết kế mẫu |
| 5 | Y lấy khóa policy sau đó, dù request Y có thể đã tới từ trước | Y được đánh giá theo R2, giữ PENDING vì chưa đủ duyệt và không có provider intent |
| 6 | Client retry Y hoặc worker nhận lại thông báo về X | Y giữ cùng operation ID và vẫn chờ duyệt; X tiếp tục đúng execution đã có, không sinh payout khác |

Nếu transaction X rollback thay vì commit ở bước 3, X chưa có nghĩa vụ thực thi đã chấp nhận. Khi thử claim lại sau bước 4, X phải đọc R2 và chờ duyệt như Y. Không dùng log “đã bắt đầu chạy” hoặc timestamp message làm bằng chứng thay cho commit.

Nếu thứ tự khóa đảo lại và activation commit trước khi worker X đọc policy, cả X và Y đều phải qua R2. Hai lịch này là hai trường hợp cần kiểm chứng riêng; hệ thống không được có một lịch xen kẽ cho phép claim R1 sau cutover mà không thuộc ngoại lệ đã định nghĩa.

## 10. Rollback binary và thay activation là hai quyết định riêng

### 10.1. B2 về B1 vẫn phải cưỡng chế R2

Khi B2 có lỗi triển khai hoặc hiệu năng, B1 là phương án rollback chỉ khi nó còn đọc được dữ liệu hiện tại và cưỡng chế R2. Activation epoch 42 không tự trở lại 41 khi image thay đổi. Bản rollback phải giữ quyền theo đối tượng, bằng chứng duyệt, execution identity và semantics của operation đang dở.

| Tình trạng | Hướng xử lý phù hợp | Điều phải tránh |
|---|---|---|
| B2 lỗi, B1 hỗ trợ đầy đủ R2 và dữ liệu hiện tại | Rollback binary về B1, giữ activation và hàng rào thực thi | Khôi phục snapshot flag R1 đi kèm image cũ |
| B1 không hiểu field, state hoặc rule mới đã được ghi | Giữ phạm vi bị ảnh hưởng có kiểm soát, sửa tiến hoặc chuẩn bị adapter/binary phù hợp | Cho B1 bỏ qua metadata bảo mật rồi tiếp tục |
| Bundle R2 có lỗi nhưng yêu cầu duyệt mới vẫn bắt buộc | Dùng bundle sửa đúng hoặc giữ các execution mới liên quan trong lúc xử lý | Fallback toàn bộ sang R1 để giảm số yêu cầu bị giữ |
| Provider đã nhận lệnh, local chưa biết kết quả | Giữ operation/execution cũ và đối soát | Reset PENDING, xóa deduplication rồi gửi payout mới |
| Dữ liệu phát sinh dưới R2 không thể đọc bằng B0 | Loại B0 khỏi danh sách rollback | Down migration xóa bằng chứng chỉ để binary cũ khởi động |

Nếu nghiệp vụ thực sự cho phép thay lại policy, đó là một activation mới có lý do và quyền riêng. Epoch vẫn tăng, chẳng hạn 42 sang 43, dù bundle được chọn từng tồn tại trước đây. Không giảm epoch để giả như cutover chưa xảy ra; executor cũ và audit cần phân biệt hai lần activation.

Quyết định chọn lại R1 còn phải đáp ứng mức bảo vệ bắt buộc hiện tại. Việc bundle R1 vẫn đọc được hoặc từng được cho phép không tự chứng minh nó còn an toàn. Một bundle sửa lỗi giữ nguyên yêu cầu bảo mật có thể là lựa chọn phù hợp hơn việc khôi phục toàn bộ hành vi cũ.

### 10.2. Giữ sự thật lịch sử khi phục hồi

Operation đã SUCCEEDED không đổi thành chưa thực hiện vì rule hiện tại sẽ từ chối nó. Operation đã claim dưới rule cũ được xử lý theo cam kết và bằng chứng đã lưu. Dữ liệu thiếu bằng chứng cần được phân loại, không được gắn nhãn approval mới cho một hành động quá khứ.

Nếu phát hiện payout đã được gửi trái invariant, quy trình sửa/bù trừ là một nghiệp vụ riêng: có phạm vi, quyền, định danh chống lặp và audit. Rollback binary không thu hồi được tác dụng ở provider. Cần phân biệt rõ đã khôi phục đường thực thi an toàn với đã giải quyết xong mọi hậu quả trước đó.

Trong phục hồi từ backup, phải xét cả activation, idempotency binding, outbox và kết quả provider sau thời điểm backup. Một bản dữ liệu cũ có thể quên payout đã gửi hoặc khôi phục R1 trong khi credentials hiện tại vẫn cho phép thực thi. Chặn tác dụng mới và đối soát phần chênh lệch trước khi coi bản restore là executor an toàn.

## 11. Kiểm thử lịch nhiều phiên bản và các đường lạm dụng

Các tình huống dưới đây hướng dẫn xây dựng bằng chứng cho hệ thống áp dụng bài học. Chúng không biểu thị rằng đã chạy test, QA hay diễn tập cho một hệ thống cụ thể.

### 11.1. Ma trận tình huống cần có

| Tình huống | Điều cần quan sát để chứng minh an toàn |
|---|---|
| Các amount 4.999.999, 5.000.000, 19.999.999 và 20.000.000 dưới từng rule | Đúng biên `>=`; yêu cầu duyệt khác nhau đúng dự kiến, các quyền và invariant khác vẫn được giữ |
| Cùng operation PENDING đi qua B1 rồi B2 sau activation R2 | Cả hai dùng R2 authoritative; đổi instance không giúp payout 8 triệu thiếu duyệt được claim |
| Client cũ gửi/đọc dữ liệu qua adapter được hỗ trợ | Không crash hoặc hiểu PENDING sai cam kết; thêm field đặc quyền không sửa được rule, tenant hay approval |
| Activation tranh khóa với execution claim | Chỉ có kết quả đúng theo hai thứ tự commit ở mục 9.2; rollback transaction claim không tạo ngoại lệ giả |
| Sửa amount, người nhận hoặc content revision sau duyệt | Không tái dùng approval của nội dung cũ để claim nội dung mới; kiểm tra diễn ra trên facts được bảo vệ |
| Hai operation khác nhau tranh cùng balance hoặc quota | Dù khác binary, tổng reservation/hiệu lực không vượt hạn mức; khóa policy không bị hiểu nhầm là đã khóa balance |
| Retry cùng key từ trước cutover, hoặc đổi fingerprint contract | Cùng ý định tìm lại operation cũ; payload khác bị phát hiện; không sinh payout mới do đổi rule namespace |
| Đổi key để gửi lại cùng nghĩa vụ kinh doanh | Ràng buộc business obligation vẫn ngăn hiệu lực lặp, độc lập với cache idempotency |
| Message R1 tới muộn hoặc replay DLQ | Tín hiệu cho PENDING chịu rule hiện hành; message của claim đã commit tiếp tục đúng execution đã chứng minh |
| Metadata legacy thiếu, bundle không rõ version hoặc hash sai | Không mặc định permit; giữ được dữ liệu và lý do để xử lý, không mất nghĩa vụ do ack/xóa tùy tiện |
| Mất response sau commit hoặc provider thành công rồi worker chết | Cùng operation/execution được khôi phục; không giải phóng nghĩa vụ chưa rõ và không tạo key gửi mới |
| Rollback B2 về B1 trong khi R2 active | B1 giữ gate R2 và đọc được dữ liệu đã ghi; rollback không đổi activation hoặc xóa kết quả chống lặp |
| B0 thức dậy, autoscale lại hoặc dùng đường gọi quản trị cũ | Hàng rào thực tế ngăn claim/dispatch trái protocol, kể cả khi B0 không biết epoch |
| Caller sửa context canary, tenant hoặc rule header | Phạm vi từ dữ kiện đáng tin vẫn quyết định; không tìm được nhánh R1 bằng retry hoặc giả context |
| Mất flag/control plane, cache activation cũ hoặc restore dữ liệu lùi | Không mở execution theo rule yếu hơn chỉ vì lỗi phụ thuộc; đường đối soát nghĩa vụ cũ vẫn có hành vi được định nghĩa |

Ma trận phiên bản phải dùng các cặp thực sự có thể cùng tồn tại: B1/B2 đọc và ghi lẫn nhau, consumer đọc message do producer còn hỗ trợ phát ra, B1 đọc dữ liệu sau khi B2 đã ghi. Với B0 sau cutover, kết quả cần chứng minh là không còn quyền thực thi, không phải B0 tự hiểu được R2.

### 11.2. Đo trạng thái bền và tác dụng, không chỉ response

Một test từ chối claim cần kiểm tra không có transition EXECUTING, reservation trái phép hoặc provider intent mới. Một test retry cần đếm số operation, execution và tác dụng thực tế theo đúng định danh. Audit về nỗ lực bị từ chối vẫn có thể tồn tại theo thiết kế; nó khác lịch sử execution đã commit.

Với race activation/claim, dùng transaction và connection riêng trên database mục tiêu, điều phối bằng barrier hoặc điểm chặn kiểm thử có kiểm soát. Chỉ khởi động hai thread gần nhau rồi ngủ một khoảng không chứng minh đã tạo lịch cạnh tranh cần kiểm tra. Nếu xảy ra deadlock/serialization failure, thử lại theo hợp đồng ứng dụng và kiểm tra kết quả cuối cùng.

Với lỗi bên ngoài, giả lập riêng các ranh giới: trước commit, sau commit trước gửi, sau provider thực hiện trước nhận response, và sau nhận response trước lưu kết quả. Cùng một operation phải khôi phục được theo từng điểm; số lần gửi request có thể lớn hơn một nhưng không được suy từ đó rằng hiệu lực ngoài chắc chắn chỉ có một. Bảo đảm đó còn phụ thuộc định danh và hợp đồng provider.

## 12. Quan sát để giải thích được từng quyết định trong giai đoạn chuyển đổi

### 12.1. Bằng chứng quyết định và activation

Một bản ghi quyết định nên nối được các dữ kiện tối thiểu sau, với quyền đọc và chính sách lưu phù hợp:

```text
scope / tenant / action
operationId / businessObligationId / executionId
binaryVersion / instanceId / region
apiOrEventContractVersion / fingerprintVersion
acceptedRuleVersion / executionRuleVersion / bundleHash
activationEpoch / activationChangeId
resourceRevision / approvedContentRevision / approvalReference
decision = PERMIT | HOLD | DENY | ERROR
reasonCode / evaluatedFactsReference
claimCommitReference / outboxEventId / providerReference
```

Tên trường là minh họa. Tham chiếu phải đủ tìm lại bằng chứng có thẩm quyền, không nhất thiết sao chép toàn bộ dữ liệu cá nhân, tài khoản nhận hoặc request vào log. Nhãn `PERMIT` trong log trước commit không chứng minh execution đã commit; lịch sử cần phân biệt quyết định đánh giá, commit nghĩa vụ và kết quả provider.

Bản ghi thay activation cần chỉ rõ scope, epoch trước/sau, bundle/hash được chọn, identity có thẩm quyền, lý do và kết quả commit. Dùng cùng tham chiếu thay đổi để nối deployment, audit và quyết định worker. Không lấy giá trị dashboard hiện tại để suy ra rule mà operation đã dùng từ trước.

### 12.2. Tín hiệu vận hành gắn với invariant

| Tín hiệu | Câu hỏi cần trả lời | Hướng phản ứng |
|---|---|---|
| Claim mới dùng rule/epoch không hợp lệ theo thứ tự authoritative | Có đường bỏ gate sau cutover không? | Giữ scope bị ảnh hưởng, tìm executor và đối soát claim đã tạo |
| Số HOLD và tuổi operation PENDING theo lý do | Yêu cầu chờ duyệt đúng dự kiến hay mắc kẹt do adapter/policy lỗi? | Phân loại theo reason, xử lý backlog mà không bỏ approval |
| Claim từ binary không còn được phép | B0 hoặc đường quản trị cũ có tái xuất hiện không? | Chặn quyền thực thi thực tế và kiểm tra cấu hình khởi động lại |
| Xung đột fingerprint, execution hoặc nghĩa vụ trùng | Thay version có làm mất liên kết retry không? | Dừng đường gây lặp, giữ binding và đối chiếu tác dụng provider |
| Outbox tồn đọng và execution chưa biết kết quả | Có nghĩa vụ đã commit chưa hoàn tất hoặc mất dấu sau deploy không? | Tiếp tục cùng execution theo protocol và đối soát kết quả |
| Chênh lệch reservation, hạn mức và dữ liệu provider | Việc chuyển rule có làm sai bất biến tài nguyên không? | Cô lập đối tượng liên quan và sửa theo quy trình có audit |

Metric nên dùng nhãn có phạm vi kiểm soát như action, rule, nhóm scope và reason; operation ID chi tiết phù hợp với trace/audit có quyền tra cứu, tránh tạo số lượng chuỗi metric không giới hạn. Ngưỡng cảnh báo và thời gian quan sát phụ thuộc chu kỳ xử lý, độ trễ queue và hợp đồng provider của hệ thống.

Một tỷ lệ lỗi HTTP thấp không loại trừ việc payout sai đã trả thành công. Ngược lại, số HOLD tăng có thể là hiệu quả dự kiến khi R2 bắt đầu yêu cầu duyệt. Cần so với các nhóm bị ảnh hưởng theo thay đổi nghiệp vụ, đồng thời tìm riêng vi phạm bảo mật mới.

## 13. Hồ sơ bàn giao và điều kiện kết thúc chuyển đổi

Hồ sơ chuyển đổi nên đủ ngắn để dùng khi triển khai nhưng đủ cụ thể để người trực vận hành biết đâu là trạng thái an toàn:

```text
Action và scope chuyển đổi:
Invariant bắt buộc, thay đổi hành vi được chấp nhận:
Bundle/version/hash trước và sau; activation epoch/change ID:
Semantics cho PENDING, EXECUTING, terminal và dữ liệu legacy:
Binary/API/event/schema được hỗ trợ trong từng giai đoạn:
Cơ chế chặn executor không đủ capability:
Execution gate và ranh giới cutover authoritative:
Idempotency/fingerprint/obligation binding cần giữ:
Đích rollback binary; cấu hình activation phải giữ:
Điều kiện dừng, chỉ báo theo dõi và người xử lý backlog:
Bằng chứng cho lịch cạnh tranh, replay và lỗi tích hợp:
Điều kiện gỡ adapter hoặc siết constraint:
Các ngoại lệ chưa giải quyết và phạm vi đang bị giữ:
```

Trước khi thu hẹp hỗ trợ legacy, cần kiểm tra các điều kiện sau trên đúng phạm vi:

- [ ] Mọi đường có thể claim/dispatch đều tôn trọng gate; B0 không thể tái xuất hiện với quyền thực thi cũ.
- [ ] B1/B2 và contract còn hỗ trợ hiểu dữ liệu thực tế; metadata thiếu hoặc chưa biết có cách xử lý rõ ràng.
- [ ] PENDING, execution đã commit và kết quả cuối cùng được phân biệt; không dùng tuổi message làm quyền miễn kiểm tra.
- [ ] Binding của cùng ý định và nghĩa vụ được bảo toàn qua retry, rollout, rollback và khôi phục dữ liệu.
- [ ] Có bằng chứng cho cạnh tranh activation/claim, cạnh tranh hạn mức, thay nội dung sau duyệt và mất response.
- [ ] Đích rollback còn dùng được với activation hiện hành; không kèm down migration xóa dữ liệu cần thiết.
- [ ] Backlog, event trì hoãn, cron job, DLQ và đường restore đã được xét trước khi bỏ adapter.
- [ ] Các quyết định HOLD/ngoại lệ có owner và đường xử lý; điều kiện hoàn tất không chỉ là số instance đã cập nhật.

Các ô trên là mẫu áp dụng, chưa phải kết quả đánh giá một hệ thống. Chỉ ghi hoàn tất một điều kiện khi có bằng chứng đúng phạm vi và phiên bản; việc bảo toàn invariant phải tiếp tục được kiểm tra khi thêm trạng thái, đổi provider, thay giao thức retry hoặc mở lại đường thực thi cũ.
