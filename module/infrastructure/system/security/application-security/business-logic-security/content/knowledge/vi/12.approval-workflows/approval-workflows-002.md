# Approval reviewer selection: chọn người duyệt theo chính sách nghiệp vụ

## 1. Mục tiêu bài học

Trong chương **Approval Workflows** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **approval reviewer selection** là quá trình xác định ai được giao xem xét và quyết định một yêu cầu cụ thể.

Chọn reviewer không chỉ là tìm một tài khoản có role APPROVER. Hệ thống phải xác định người đó có quyền với đúng đối tượng, đủ hạn mức, thuộc đúng phạm vi tổ chức, không có xung đột lợi ích bị cấm và đáp ứng yêu cầu độc lập với những người khác trong quy trình.

Nếu bước lựa chọn sai, state machine vẫn có thể chạy đúng các trạng thái SUBMITTED → UNDER_REVIEW → APPROVED nhưng phê duyệt không có giá trị nghiệp vụ.

Sau bài học, bạn có thể:

- Phân biệt tập ứng viên, người đủ điều kiện, người được phân công và người thực sự ra quyết định.
- Thiết kế quy tắc lựa chọn dựa trên dữ liệu có thẩm quyền ở server.
- Bảo vệ phân tách nhiệm vụ, phê duyệt nhiều vai trò và số người độc lập.
- Xử lý người vắng mặt, ủy quyền và thay người duyệt mà không hạ chuẩn kiểm soát.
- Ràng buộc assignment với revision, vòng duyệt và phiên bản chính sách.
- Kiểm thử các cách lạm dụng việc chọn người duyệt, kể cả khi có request cạnh tranh.

## 2. Chọn sai reviewer tạo ra lỗ hổng gì?

Xét một yêu cầu chi trả do An tạo. Chính sách yêu cầu quản lý phụ trách ngân sách và một người thuộc tài chính cùng duyệt khi số tiền vượt ngưỡng.

Các lỗi sau đều có thể khiến yêu cầu được “duyệt thành công” sai chính sách:

| Cách triển khai | Cách bị lạm dụng |
|---|---|
| Client gửi approverId và server lưu trực tiếp | Người yêu cầu chỉ định người không đủ thẩm quyền hoặc một tài khoản mình kiểm soát |
| Chỉ kiểm tra role APPROVER | Reviewer không có quyền trên đơn vị, ngân sách hoặc tenant của yêu cầu |
| Chọn quản lý theo departmentId do client cung cấp | Người yêu cầu thay thuộc tính để đi vào nhánh phê duyệt dễ hơn |
| Đếm số tài khoản đã duyệt | Một người dùng nhiều tài khoản hoặc nhiều role để đủ số lượng |
| Khi không có reviewer thì tự duyệt | Người dùng tạo tình huống thiếu reviewer để bỏ qua kiểm soát |
| Cho phép đổi reviewer không giới hạn | Người yêu cầu thử lại cho đến khi gặp người dễ thông qua |
| Giữ assignment cũ sau khi tăng số tiền | Reviewer được giao theo hạn mức thấp nhưng quyết định trên nội dung vượt quyền |
| Ủy quyền cho người tạo yêu cầu | Vòng ủy quyền làm mất quy tắc không tự duyệt |
| Hai người đồng thời thay assignment | Reviewer cũ và reviewer mới đều có thể bỏ phiếu cho cùng một vị trí |

Quyền quản trị hệ thống cũng không mặc nhiên là thẩm quyền duyệt nghiệp vụ. Người cấu hình tài khoản có thể không phải người được phép duyệt khoản chi.

## 3. Phân biệt các khái niệm

| Khái niệm | Ý nghĩa |
|---|---|
| Candidate | Người có thể được xét, ví dụ thành viên nhóm quản lý ngân sách |
| Eligible reviewer | Candidate đáp ứng tất cả điều kiện của yêu cầu và vị trí duyệt tại thời điểm kiểm tra |
| Assignee | Người được giao một vị trí duyệt cụ thể |
| Reviewer | Chủ thể thực hiện việc xem xét; trong API phải xác định rõ có được ra quyết định hay chỉ được góp ý |
| Decision maker | Danh tính được ghi nhận đã approve/reject và được tính vào điều kiện hoàn thành |
| Approval slot | Một vị trí cần được đáp ứng, ví dụ BUSINESS_OWNER hoặc FINANCE |
| Quorum | Số lượng và cơ cấu quyết định hợp lệ cần có để hoàn tất |
| Approval round | Một vòng duyệt gắn với nội dung và điều kiện cụ thể |
| Principal/person identity | Danh tính chuẩn dùng để xác định sự độc lập theo mô hình tổ chức |

Một người có thể đủ điều kiện nhưng chưa được phân công. Ngược lại, người đã được phân công hôm qua có thể không còn đủ điều kiện khi bấm duyệt hôm nay.

Assignment là một phần bằng chứng về định tuyến. Nó không thay thế việc kiểm tra quyền tại thời điểm quyết định.

### 3.1. Xác định đơn vị độc lập trước khi đếm

Nếu yêu cầu nghiệp vụ là “hai người độc lập”, không được mặc định:

~~~text
hai userId khác nhau = hai người độc lập
~~~

Cần dùng quan hệ danh tính có thẩm quyền, chẳng hạn personId trong hệ thống nhân sự, để nhận diện các tài khoản thuộc cùng một người. Không suy luận danh tính từ tên hiển thị hoặc so chuỗi email một cách tùy ý.

Trong một số tổ chức, độc lập còn có nghĩa là khác bộ phận, khác tuyến báo cáo hoặc không tham gia giao dịch. Những điều kiện này phải được đặc tả riêng; hai personId khác nhau mới chỉ đáp ứng yêu cầu “khác người”.

Service account không được tính như một người phê duyệt chỉ vì có role tương tự. Nếu có bước đánh giá tự động, cần mô hình hóa nó như một loại kiểm soát riêng với ý nghĩa được chính sách công nhận.

## 4. Chính sách minh họa

Bài học dùng yêu cầu chi trả nội bộ bằng VND với chính sách giả định sau. Các ngưỡng chỉ phục vụ ví dụ:

| Giá trị yêu cầu | Vị trí duyệt bắt buộc | Điều kiện |
|---|---|---|
| Lớn hơn 0 và không quá 20 triệu | BUSINESS_OWNER | Một người phụ trách ngân sách đúng đơn vị, đủ hạn mức |
| Trên 20 triệu đến 100 triệu | BUSINESS_OWNER và FINANCE | Hai người khác nhau, đúng phạm vi và đủ hạn mức |
| Trên 100 triệu | BUSINESS_OWNER, FINANCE và RISK | Ba người khác nhau, đáp ứng từng thẩm quyền |

Các quy tắc áp dụng cho mọi mức:

- Người tạo và người thụ hưởng bị cấm tham gia quyết định theo chính sách ví dụ.
- Mỗi reviewer thuộc đúng tenant, đang hoạt động và có quyền với đối tượng.
- Assignment gắn với revision của yêu cầu và một approval round.
- Một người không được tính vào hai slot trong cùng round.
- Người yêu cầu không được sửa số tiền, đơn vị hoặc người thụ hưởng trong nội dung đang được duyệt mà vẫn giữ hiệu lực phê duyệt cũ.
- Thiếu người phù hợp thì chuyển sang chờ định tuyến/xử lý ngoại lệ được kiểm soát; không tự giảm số slot.

“Đủ hạn mức” ở đây là đủ cho toàn bộ giá trị yêu cầu theo chính sách, không phải chia giá trị cho số reviewer. Nếu nghiệp vụ có cơ chế đồng phê duyệt hạn mức khác, phải đặc tả cơ chế đó riêng.

Với yêu cầu đa tiền tệ, phải quy định tỷ giá, thời điểm quy đổi và nguồn dữ liệu có thẩm quyền. Không so sánh trực tiếp các con số thuộc hai loại tiền khác nhau.

### 4.1. Dữ liệu nào có thẩm quyền?

| Thuộc tính | Nguồn quyết định |
|---|---|
| Người tạo | Danh tính đã xác thực và bản ghi yêu cầu |
| Tenant | Ngữ cảnh được kiểm chứng, ràng buộc trong truy vấn |
| Số tiền, currency, người thụ hưởng | Revision yêu cầu được server xác thực và lưu |
| Đơn vị chịu ngân sách | Quan hệ ngân sách/đối tượng có thẩm quyền, không chỉ một mã client tự khai |
| Quản lý và tuyến tổ chức | Nguồn tổ chức được hệ thống tin cậy |
| Role, phạm vi, hạn mức | Kho quyền và chính sách được quản lý |
| Quan hệ ủy quyền | Bản ghi ủy quyền hợp lệ, có phạm vi và thời hạn |
| Xung đột lợi ích | Dữ liệu quan hệ được xác minh và khai báo theo chính sách |

Dữ liệu do người dùng nhập có thể là một đề xuất cần xác thực. Nó không tự trở thành cơ sở có thẩm quyền để chọn chính người sẽ duyệt.

Ví dụ, nếu cho phép chọn costCenter, server phải xác minh yêu cầu thực sự được phép dùng cost center đó; nếu không, người dùng có thể chọn đơn vị có tuyến duyệt thuận lợi hơn.

### 4.2. Điều kiện đủ tư cách

Có thể mô tả:

~~~text
eligible(person, requestRevision, slot, context) =
    activeIdentity(person)
    ∧ tenantAllowed(person, requestRevision)
    ∧ qualifiedForSlot(person, slot)
    ∧ objectScopeAllows(person, requestRevision)
    ∧ approvalLimitAllows(person, requestRevision.amount)
    ∧ noForbiddenConflict(person, requestRevision)
    ∧ validDelegationIfUsed(person, slot, context)
    ∧ policyConditionsSatisfied(context)
~~~

Sau đó, bộ chọn còn phải thỏa điều kiện **giữa các reviewer**:

~~~text
mọi slot bắt buộc đều được gán
mọi assignment đều hợp lệ
mỗi người chỉ chiếm số slot được chính sách cho phép
các ràng buộc độc lập giữa người/đơn vị/tuyến báo cáo đều đúng
~~~

Kiểm tra eligible cho từng người riêng lẻ chưa chứng minh cả kế hoạch duyệt hợp lệ.

## 5. Bài toán lựa chọn là bài toán thỏa ràng buộc

Giả sử hai slot bắt buộc có tập người đủ điều kiện:

~~~text
BUSINESS_OWNER: {Lan, Minh}
FINANCE:        {Lan}
~~~

Nếu thuật toán luôn chọn người đầu tiên cho từng slot:

~~~text
BUSINESS_OWNER = Lan
FINANCE = không còn ai khác
~~~

Nó có thể kết luận sai rằng không đủ reviewer, dù có phương án:

~~~text
BUSINESS_OWNER = Minh
FINANCE = Lan
~~~

Với yêu cầu “khác người”, đây có thể được mô hình hóa như bài toán ghép slot với person, mỗi person có sức chứa một. Khi có thêm điều kiện khác bộ phận hoặc quan hệ xung đột giữa người với người, cần bộ giải ràng buộc hoặc tìm kiếm có giới hạn phù hợp với quy mô.

Điều không được làm là cho Lan chiếm cả hai slot chỉ để tránh lỗi thuật toán.

### 5.1. Quy tắc ưu tiên chỉ chạy sau các điều kiện bắt buộc

Giữa nhiều kế hoạch đều hợp lệ, hệ thống có thể ưu tiên theo tải công việc, khu vực, ca trực hoặc thứ tự ổn định. Việc chọn ngẫu nhiên cũng chỉ được thực hiện trong tập đáp ứng cùng mức kiểm soát.

Một reviewer “đang rảnh” không được thay reviewer có thẩm quyền cao hơn nếu người đó thiếu hạn mức hoặc thiếu phạm vi. Thứ tự ưu tiên là cách vận hành trong tập hợp lệ, không phải lý do nới điều kiện đủ tư cách.

Cũng cần hạn chế việc liên tục tính lại kế hoạch do người yêu cầu kích hoạt. Nếu mỗi lần resubmit lại chọn bộ người khác mà không đổi nội dung, tính ngẫu nhiên có thể trở thành đường tìm kiếm reviewer thuận lợi.

### 5.2. Không có kế hoạch hợp lệ là một kết quả nghiệp vụ

Các trường hợp cần phân biệt:

- Không có candidate cho một slot.
- Có candidate nhưng tất cả không đủ điều kiện.
- Mỗi slot có người đủ điều kiện nhưng không có tổ hợp đáp ứng yêu cầu độc lập.
- Nguồn quyền/tổ chức chưa đủ tin cậy hoặc đang không truy cập được.
- Có kế hoạch hợp lệ nhưng tất cả reviewer chưa sẵn sàng xử lý.

Thông thường, hệ thống lưu yêu cầu ở trạng thái chờ định tuyến hoặc cần hỗ trợ. Chưa đủ dữ liệu để chọn reviewer không phải bằng chứng cho phép bỏ qua reviewer.

## 6. Quy trình chọn và lưu assignment ở server

Một luồng định tuyến có thể gồm:

~~~text
Xác thực người yêu cầu định tuyến
    → đọc đúng đối tượng trong tenant
    → khóa/kiểm tra revision và version
    → xác định chính sách áp dụng
    → lấy dữ liệu tổ chức và quyền có thẩm quyền
    → tính tập đủ điều kiện cho từng slot
    → giải ràng buộc của toàn bộ kế hoạch
    → lưu round, assignment, audit và outbox
    → commit
~~~

### 6.1. Bảo vệ dữ liệu được dùng để định tuyến

Số tiền, người thụ hưởng, đơn vị ngân sách hoặc loại giao dịch có thể làm thay đổi tuyến duyệt. Khi bắt đầu round, phải gắn quyết định định tuyến với một revision xác định của các trường này.

Nếu nội dung thay đổi từ 15 triệu lên 150 triệu:

- Không giữ nguyên tuyến chỉ có BUSINESS_OWNER.
- Không áp dụng quyết định đã ký cho revision cũ lên revision mới.
- Tạo revision và round mới hoặc thực hiện quy trình tái phê duyệt được chính sách quy định.
- Giữ lịch sử assignment và quyết định cũ để truy vết.

Nếu có trường không ảnh hưởng đến phê duyệt, như một ghi chú thuần mô tả, chính sách có thể cho phép sửa mà không hủy round. Phải xác định tập trường đó rõ ràng; không để client tự đánh dấu thay đổi là “không quan trọng”.

Một hash của nội dung giúp đối chiếu đúng revision, nhưng không tự xác minh nội dung hợp lệ hoặc cấp thẩm quyền phê duyệt.

### 6.2. Lưu phiên bản chính sách và dữ liệu tổ chức

Một bản ghi round nên giải thích được vì sao các reviewer này được chọn:

~~~text
roundId, requestId, requestRevision
policyId, policyVersion
organizationSnapshotVersion, entitlementSnapshotVersion
requiredSlots, independenceRules
selectedAssignments
routingReason, createdAt, routingActor
~~~

Snapshot phục vụ tính nhất quán và audit. Nó không làm quyền cũ có hiệu lực vô hạn.

Cần phân biệt:

- **Tại định tuyến:** kế hoạch hợp lệ theo dữ liệu và chính sách áp dụng lúc chọn.
- **Tại quyết định:** người thực hiện vẫn đáp ứng điều kiện cần thiết để quyết định được tính.
- **Tại thực thi nghiệp vụ:** tập quyết định còn đáp ứng chính sách về nội dung, hiệu lực và điều kiện giải ngân/thực thi.

Khi chính sách thay đổi, hệ thống phải có quy tắc rõ về round đang mở: áp dụng bản mới, yêu cầu định tuyến lại hay cho phép tiếp tục bản đã chốt trong một phạm vi xác định. Người dùng không được tự gửi policyVersion cũ để chọn chế độ dễ hơn.

Nếu dữ liệu quyền/tổ chức ở dịch vụ ngoài, transaction cơ sở dữ liệu cục bộ không khóa được dịch vụ đó. Phải quy định độ mới dữ liệu, cách kiểm chứng phiên bản và hành vi khi không xác nhận được thẩm quyền. Với yêu cầu thu hồi quyền có hiệu lực ngay, cần cơ chế kiểm tra/phối hợp đáp ứng cam kết đó; chỉ lưu một snapshot cũ là chưa đủ.

### 6.3. Java minh họa tầng định tuyến

Đây là mã phác thảo dùng các interface giả định, không phải chương trình độc lập. Snapshot nội dung và các nguồn quyền trong ví dụ do server cung cấp; giao thức đọc dữ liệu có thẩm quyền phải được triển khai theo yêu cầu nhất quán thực tế.

~~~java
RoutingResult routeReview(Actor actor, RouteCommand cmd) {
    return transactions.required(() -> {
        var request = requests.lockForUpdate(
                actor.tenantId(), cmd.requestId());
        access.requireCanStartRouting(actor, request);

        requireVersion(request, cmd.expectedVersion());
        requireState(request, SUBMITTED);
        requireNoActiveRound(request.id(), request.revision());

        var snapshot = request.approvalSnapshot();
        var policy = policies.requireApplicablePolicy(snapshot);
        var facts = authorities.requireRoutingFacts(snapshot, policy);

        var requirements = policy.requiredSlots(snapshot);
        var candidates = directory.findCandidates(
                request.tenantId(), requirements, facts);

        var eligibleBySlot = eligibility.evaluate(
                candidates, snapshot, requirements, policy, facts);

        var plan = selector.requireFeasiblePlan(
                eligibleBySlot, requirements,
                policy.independenceRules());

        // Kiểm tra toàn kế hoạch trước khi lưu, không chỉ từng người.
        planValidator.requireValid(
                plan, snapshot, requirements, policy, facts);

        var round = ApprovalRound.create(
                roundIds.next(), request.id(), request.revision(),
                policy.version(), facts.versions(), plan);

        rounds.insert(round);
        assignments.insertAll(round.assignments());
        request.markUnderReview(round.id());
        requests.save(request);

        audit.insertRoutingDecision(actor, request, round);
        outbox.insertAssignmentNotifications(round);
        return RoutingResult.from(round);
    });
}
~~~

Các điểm quan trọng:

- Không có tham số reviewerId tự do được lưu trực tiếp vào assignment.
- selector không được giảm requirements khi không tìm thấy lời giải.
- requireFeasiblePlan thất bại thì không có round phê duyệt nửa vời; yêu cầu vẫn chưa được phê duyệt.
- requireState và requireNoActiveRound ngăn việc gọi lại định tuyến để thay bộ reviewer đang hoạt động.
- Các luồng thay đổi cùng request phải dùng cơ chế khóa/version nhất quán.
- Unique constraint nên ngăn nhiều active round trái chính sách và nhiều assignment đang hiệu lực cho cùng slot; nếu mỗi người chỉ được chiếm một slot, cần thêm ràng buộc tương ứng theo personId.
- Notification được phát sau commit qua outbox; nhận email không phải điều kiện cấp quyền.

Nếu API định tuyến hỗ trợ idempotency, receipt phải gắn khóa với nội dung command và trả lại round đã tạo. Nếu chọn trả xung đột cho một request định tuyến lặp, client truy vấn round hiện có; không vì mất response mà chạy lại phép chọn để tạo round mới.

Khi không chọn được reviewer, có thể dùng một transaction riêng theo thiết kế để ghi trạng thái chờ định tuyến và mã lý do. Mã lý do không được diễn giải thành quyền tự động duyệt.

## 7. Lựa chọn từ gợi ý của người dùng

Một số sản phẩm cho người yêu cầu chọn reviewer vì họ biết chuyên môn hoặc đơn vị liên quan. Điều đó vẫn có thể phù hợp nếu gợi ý không trở thành quyền tự cấp.

Có ba mô hình thường gặp:

| Mô hình | Quy tắc an toàn |
|---|---|
| Server tự chọn | Client không quyết định assignment; có thể xem kế hoạch trong phạm vi được phép |
| Client chọn trong danh sách server cấp | Server kiểm tra lại người được chọn tại lúc lưu; danh sách cũ không bảo đảm còn hợp lệ |
| Client đề xuất người ngoài danh sách | Đề xuất đi qua quy trình xác minh có kiểm soát, chưa được tính là assignment có quyền |

Dù dùng mô hình nào, server vẫn phải kiểm tra tenant, object scope, hạn mức, xung đột và tính hợp lệ của cả nhóm.

Không chỉ kiểm tra reviewerId từng xuất hiện trong một response trước đó. Giữa thời điểm hiển thị và lúc submit, quyền, tổ chức, yêu cầu hoặc assignment khác có thể thay đổi.

Nếu cho phép lựa chọn trong tập hợp lệ, cần cân nhắc rủi ro người yêu cầu chủ động chọn người quen để thông qua giao dịch. Chính sách có thể hạn chế một số slot do server phân công độc lập, dù người dùng được đề xuất ở slot khác.

## 8. Vắng mặt, fallback và delegation

### 8.1. Không có mặt khác với không đủ thẩm quyền

Một reviewer có thể đủ tư cách nhưng đang nghỉ. Hệ thống có thể chờ, nhắc việc, chuyển tuyến hoặc dùng người thay thế theo chính sách. Thời gian chờ lâu không tự tạo thẩm quyền cho người khác.

Fallback phải được định nghĩa trước, ví dụ:

~~~text
Quản lý ngân sách được chỉ định
    → quản lý cấp trên có thẩm quyền tương ứng
    → pool dự phòng được phê chuẩn
    → trạng thái cần xử lý ngoại lệ
~~~

Mỗi bước vẫn áp dụng tenant, phạm vi, hạn mức, phân tách nhiệm vụ và yêu cầu độc lập. Chức danh cao hơn trong sơ đồ tổ chức không tự chứng minh đủ quyền nghiệp vụ.

Không dùng “chọn bất kỳ admin nào”, “giảm còn một người” hoặc “hết hạn thì auto-approve” làm nhánh mặc định để giải quyết thiếu reviewer.

### 8.2. Delegation phải là một quyền có phạm vi

Bản ghi ủy quyền có thể cần:

~~~text
delegationId
delegatorPersonId, delegatePersonId
tenantId, allowedScopes, allowedSlots
amountLimit, currencyOrConversionPolicy
validFrom, validUntil
allowSubdelegation
createdBy, approvalEvidence, revokedAt
~~~

Một delegation hợp lệ không chỉ là quan hệ “A chọn B”. Hệ thống phải xác minh A có quyền được ủy quyền trong phạm vi đó, người thiết lập có thẩm quyền và B được phép thực hiện theo mô hình ủy quyền đã chọn.

Có hệ thống yêu cầu B vốn đã có thẩm quyền tương ứng; hệ thống khác cho phép B nhận một năng lực ủy quyền giới hạn. Cả hai đều phải bảo đảm quyền có hiệu lực không vượt phạm vi được phép của chính sách và nguồn ủy quyền.

Các kiểm tra thường cần:

- Delegation còn hiệu lực, chưa bị thu hồi.
- Slot, đối tượng và hạn mức thuộc phạm vi cho phép.
- Người nhận không phải người tạo/người hưởng lợi bị cấm.
- Không tạo vòng ủy quyền hoặc chuỗi vượt độ sâu cho phép.
- Không làm một người được tính thành nhiều người độc lập.
- Lưu cả người thực hiện thực tế và nguồn thẩm quyền được sử dụng.

### 8.3. Kiểm tra lại cả nhóm sau khi thay bằng người được ủy quyền

Ví dụ:

~~~text
BUSINESS_OWNER = Minh
FINANCE = Lan

Minh ủy quyền BUSINESS_OWNER cho Lan.
~~~

Nếu chính sách yêu cầu hai người khác nhau, phương án sau không hợp lệ:

~~~text
BUSINESS_OWNER = Lan, thay Minh
FINANCE = Lan
~~~

Phải tìm người khác cho một slot hoặc giữ trạng thái chờ.

Hai reviewer khác nhau cùng ủy quyền cho một người cũng không tạo thành hai quyết định độc lập. Ngược lại, một nguồn thẩm quyền được chia qua nhiều người có thể vẫn không đáp ứng quy tắc về các nguồn độc lập, nếu chính sách yêu cầu điều đó.

Vì vậy mô hình cần giữ được **người quyết định thực tế**, **nguồn thẩm quyền** và **slot được đáp ứng**, thay vì chỉ lưu một approverId đã bị thay thế.

## 9. Thay reviewer mà không tạo đường lách

### 9.1. Reassignment là một command nghiệp vụ

Thay người duyệt cần có:

- Actor được phép thay assignment trong đúng phạm vi.
- Lý do thuộc chính sách và được audit.
- Version của request/round/assignment để phát hiện dữ liệu cũ.
- Kiểm tra đủ tư cách người thay và ràng buộc toàn nhóm.
- Vô hiệu hóa assignment cũ và tạo assignment mới một cách nguyên tử.
- Notification cho các bên phù hợp sau commit.

Một link hoặc tab cũ của reviewer đã bị thay không được tiếp tục tạo quyết định có hiệu lực. Endpoint quyết định phải kiểm tra assignment đang hoạt động, không chỉ kiểm tra người đó có từng được giao.

### 9.2. Không xóa lịch sử để thay đổi kết quả

Nếu reviewer đã reject, việc thay người không được mặc định xóa quyết định đó rồi tiếp tục tìm một người approve.

Quy trình khiếu nại hoặc xét lại, nếu có, phải xác định:

- Ai được mở lại và vì lý do gì.
- Có cần revision mới hoặc cấp duyệt cao hơn không.
- Những quyết định nào còn hiệu lực.
- Quorum và yêu cầu độc lập của vòng xét lại.
- Giới hạn và khả năng phát hiện việc lặp lại để tìm kết quả thuận lợi.

Giữ quyết định cũ dưới dạng bằng chứng không sửa/xóa tùy ý. Nếu hiệu lực thay đổi, ghi sự kiện hoặc trạng thái hiệu lực riêng để giải thích; không viết lại lịch sử như thể quyết định chưa từng tồn tại.

### 9.3. Chống cuộc đua approve và reassign

Ví dụ reviewer cũ đang bấm duyệt đúng lúc operator thay người. Hai command phải tranh chấp qua cùng cơ chế nhất quán trên round/assignment:

~~~text
Nếu approve thắng:
    quyết định được ghi theo assignment còn hiệu lực
    reassignment phải xử lý lại theo trạng thái mới và chính sách

Nếu reassign thắng:
    assignment cũ mất hiệu lực
    approve dựa trên assignment/version cũ bị từ chối
~~~

Nếu mọi luồng không dùng cùng giao thức khóa/version, cả hai đều có thể cho rằng mình đang xử lý assignment hiện tại.

## 10. Từ assignment đến quyết định có hiệu lực

### 10.1. Endpoint approve phải xác nhận lại điều gì?

Khi nhận command approve, server cần xác định actor từ danh tính đã xác thực rồi kiểm tra tối thiểu:

~~~text
request thuộc đúng tenant và phạm vi actor
assignment thuộc đúng request và round đang xử lý
assignment còn hoạt động và gắn đúng revision
actor là người được phép thực hiện assignment
delegation, nếu có, vẫn hợp lệ cho hành động này
actor còn đủ điều kiện theo chính sách áp dụng
version/trạng thái cho phép nhận quyết định
quyết định chưa được áp dụng trước đó
~~~

Không tin trường reviewerId trong body để quyết định ai vừa duyệt. Cũng không chấp nhận một decisionId cũ như bằng chứng rằng actor hiện có quyền với request khác.

Nếu nhân sự vừa chuyển đơn vị hoặc bị thu hồi quyền trước khi quyết định, assignment cũ không đủ làm căn cứ cho phép approve.

Đối với quyết định đã hợp lệ ở thời điểm được ghi nhận, việc một người mất quyền sau đó có làm mất hiệu lực quyết định cũ hay không là vấn đề chính sách. Phải xử lý bằng quy tắc hiệu lực rõ ràng, giữ nguyên lịch sử và đánh giá lại điều kiện thực thi khi cần; không âm thầm xóa phê duyệt.

### 10.2. Quorum phải kiểm tra cơ cấu, không chỉ số lượng

Biểu thức sau thường không đủ:

~~~sql
SELECT COUNT(*)
FROM approval_decision
WHERE request_id = :request_id
  AND decision = 'APPROVE';
~~~

Nó có thể đếm:

- Quyết định của revision hoặc round cũ.
- Nhiều bản ghi của cùng một người.
- Quyết định qua assignment đã bị vô hiệu hóa.
- Hai tài khoản thuộc cùng một người.
- Đủ số lượng nhưng thiếu FINANCE hoặc RISK.
- Quyết định được tạo từ delegation không còn phù hợp.
- Phiếu approve dù request đã có một reject có quyền phủ quyết theo chính sách.

Một mô hình kiểm tra phù hợp hơn là:

~~~text
Tập quyết định hợp lệ cho đúng round và revision
    → ánh xạ về người thực hiện và nguồn thẩm quyền
    → kiểm tra mọi slot bắt buộc được đáp ứng
    → kiểm tra độc lập và giới hạn tính mỗi người
    → áp dụng quy tắc reject/veto/majority đã đặc tả
    → xác nhận điều kiện hoàn thành round
~~~

Nếu chính sách dùng đa số, đồng thuận hay phủ quyết, phải mô tả rõ. Không suy luận một quy tắc chung chỉ từ tên “approval workflow”.

### 10.3. Thực thi sau duyệt vẫn cần ràng buộc với nội dung

Trước khi chi trả, phát hành quyền hoặc thực hiện thao tác được phê duyệt:

- Revision hiện được thực thi phải là revision mà các quyết định có hiệu lực đã chấp thuận.
- Chính sách về hiệu lực round và thời hạn quyết định phải còn được đáp ứng.
- Không còn điều kiện ngăn thực thi, như request bị hủy hoặc kiểm soát bắt buộc chưa xong.
- Việc mở bước thực thi chỉ xảy ra một lần theo state/version và định danh nghiệp vụ.
- Ý định thực thi, trạng thái và audit liên quan phải được ghi nhất quán.

Một nhóm reviewer được chọn đúng không bảo vệ được khoản chi nếu endpoint chi trả có thể bỏ qua việc kiểm tra round. Mọi đường thực thi, kể cả batch job và công cụ vận hành, phải dùng cùng điều kiện nghiệp vụ.

## 11. Kiểm thử lựa chọn reviewer bằng tình huống lạm dụng

Các tình huống dưới đây hướng dẫn xây dựng kiểm thử cho hệ thống thực. Khi kiểm tra transaction và constraint, cần đọc lại trạng thái đã commit; chỉ kiểm tra danh sách Java trả về chưa đủ.

### 11.1. Ma trận kiểm thử

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Client tự gửi approverId ngoài tập hợp lệ | Không tạo được assignment có hiệu lực |
| Reviewer có role đúng nhưng thuộc tenant khác | Bị loại; không nhận quyền với request |
| Reviewer đúng tenant nhưng sai đơn vị/ngân sách | Bị loại theo object scope |
| Người tạo cũng có role APPROVER | Không được tự duyệt trong chính sách ví dụ |
| Người thụ hưởng nằm trong candidate pool | Bị loại theo quy tắc xung đột lợi ích |
| Một person có hai userId | Không được tính là hai người độc lập |
| Một người có cả BUSINESS_OWNER và FINANCE | Có thể đủ điều kiện từng slot nhưng không được chiếm cả hai nếu chính sách cấm |
| Mỗi slot có ứng viên nhưng không tồn tại tổ hợp độc lập | Không hạ quorum; yêu cầu chờ định tuyến |
| Bộ chọn tham lam bỏ sót phương án hợp lệ | Bộ chọn vẫn tìm được phương án thỏa ràng buộc hoặc báo giới hạn rõ ràng |
| Không có reviewer hoặc nguồn quyền chưa truy cập được | Không auto-approve và không tạo kế hoạch chưa được kiểm chứng |
| Tăng số tiền làm đổi hạn mức/tuyến duyệt | Assignment và quyết định cũ không được áp dụng nguyên trạng cho revision mới |
| Sửa đơn vị để đổi tuyến | Server xác minh quyền và quan hệ nghiệp vụ, không tin thuộc tính tự khai |
| Delegation cho người tạo hoặc người hưởng lợi bị cấm | Không có assignment/decision hợp lệ |
| Hai reviewer cùng ủy quyền cho một người | Không đạt yêu cầu hai người độc lập |
| Delegation hết hạn hoặc bị thu hồi trước approve | Không chấp nhận quyết định qua quyền ủy quyền đó |
| Reviewer mất quyền sau lúc được chọn | Không thể duyệt chỉ nhờ assignment cũ |
| Reviewer cũ dùng link sau reassignment | Không tạo được quyết định có hiệu lực |
| Hai command định tuyến hoặc thay người chạy đồng thời | Không có hai active round/assignment trái quy tắc |
| Gửi lại command định tuyến sau khi mất response | Trả/tra cứu round cũ hoặc báo xung đột; không chọn bộ mới tùy ý |
| Đã reject rồi gọi API thay reviewer | Không xóa kết quả để tiếp tục tìm người approve |
| Lỗi khi ghi assignment/audit/outbox bắt buộc | Không để lại round hoạt động thiếu các thành phần bắt buộc |
| Gọi thẳng bước thực thi chưa đủ quorum | Không tạo hiệu ứng nghiệp vụ |

### 11.2. Kiểm thử thuật toán bằng tập ứng viên nhỏ

Một bộ dữ liệu tối thiểu hữu ích:

~~~text
Slot B: {person-1, person-2}
Slot F: {person-1}
Quy tắc: mỗi person tối đa một slot

Kết quả hợp lệ:
  B = person-2
  F = person-1
~~~

Và một bộ không có lời giải:

~~~text
Slot B: {person-1}
Slot F: {person-1}
Quy tắc: mỗi person tối đa một slot

Kết quả:
  Không có kế hoạch hợp lệ.
  Không được gán person-1 vào cả hai slot.
~~~

Thêm một trường hợp có hai tài khoản cùng personId để xác nhận thuật toán chạy trên đơn vị danh tính nghiệp vụ, không chỉ trên userId.

Những ca này kiểm tra hành vi có ý nghĩa: tìm được kế hoạch hợp lệ khi tồn tại và không tạo kế hoạch vi phạm khi thiếu người. Không cần ràng buộc test vào thứ tự nội bộ của một thuật toán cụ thể nếu chính sách cho phép nhiều lời giải.

### 11.3. Kiểm thử cuộc đua quyết định và thay reviewer

Dùng hai transaction hoặc kết nối độc lập:

1. Tạo assignment A đang hoạt động cho Lan ở version xác định.
2. Cho transaction thứ nhất xử lý approve của Lan.
3. Cho transaction thứ hai thay A bằng assignment B cho Hoa.
4. Điều phối để hai command thật sự cạnh tranh tại điểm kiểm tra/ghi.
5. Đọc lại request, round, assignment và decision sau khi cả hai kết thúc.

Kết quả phải phù hợp với thứ tự đã được tuần tự hóa:

- Approve được nhận khi A còn hiệu lực, rồi lệnh thay người xử lý theo trạng thái mới; hoặc
- A bị thay trước và approve theo A/version cũ bị từ chối.

Không được có hai decision cùng được tính cho một slot chỉ vì hai transaction cùng đọc thấy trạng thái ban đầu.

### 11.4. Kiểm thử nguồn dữ liệu thay đổi

Dừng luồng giữa lúc chọn ứng viên và lúc nhận quyết định, rồi thay đổi một trong các dữ liệu:

- Reviewer bị vô hiệu hóa.
- Hạn mức bị giảm.
- Quan hệ quản lý thay đổi.
- Delegation bị thu hồi.
- Revision hoặc chính sách áp dụng của request thay đổi.

Kiểm chứng rằng cơ chế hiệu lực được thiết kế thực sự chặn quyết định không còn đáp ứng yêu cầu. Nếu hệ thống có cửa sổ đồng bộ quyền, kiểm thử theo đúng cam kết đó và không tuyên bố khả năng thu hồi tức thời mà kiến trúc chưa bảo đảm.

## 12. Audit và phát hiện reviewer shopping

### 12.1. Lưu được lý do chọn, không chỉ kết quả chọn

Audit nên giúp trả lời:

- Chính sách và revision nào tạo ra các slot?
- Reviewer được chọn bằng thẩm quyền trực tiếp hay qua delegation nào?
- Những yêu cầu độc lập nào đã được áp dụng?
- Ai mở round, thay reviewer hoặc cho phép xét lại?
- Người thay có đủ điều kiện tại thời điểm nào và dựa trên nguồn dữ liệu nào?
- Vì sao không chọn được kế hoạch, hoặc vì sao phải dùng fallback?

Không nhất thiết lưu toàn bộ hồ sơ nhân sự hay toàn bộ candidate pool vào mọi bản ghi. Lưu dữ liệu, phiên bản và bằng chứng cần thiết để giải thích quyết định theo chính sách lưu trữ của hệ thống.

Tài khoản bị khóa hoặc người dùng rời tổ chức không nên làm mất khả năng truy vết danh tính đã thực hiện quyết định trước đây.

### 12.2. Những mẫu hành vi đáng theo dõi

- Một người yêu cầu thường xuyên tạo lại request ngay sau khi thấy reviewer.
- Nhiều lần đổi cost center, số tiền hoặc loại giao dịch sát ngưỡng tuyến duyệt.
- Reassignment tập trung bất thường về một người.
- Nhiều nguồn ủy quyền cùng trỏ về một reviewer trong các giao dịch liên quan.
- Tỷ lệ thay người sau reject cao.
- Thường xuyên rơi vào fallback hoặc cơ chế ngoại lệ.
- Một tài khoản vận hành mở lại nhiều vòng duyệt mà không có lý do phù hợp.

Các dấu hiệu này phục vụ điều tra; không tự chứng minh có gian lận.

Chia nhỏ một giao dịch để tránh ngưỡng phê duyệt còn cần quy tắc nhận diện giao dịch liên quan hoặc tổng mức cam kết theo nghiệp vụ. Chọn reviewer đúng cho từng request riêng lẻ không tự giải quyết được việc cố ý tách request.

### 12.3. Giới hạn thông tin được tiết lộ

Danh sách reviewer có thể chứa thông tin tổ chức nhạy cảm. API cần giới hạn theo quyền của người xem và mục đích thao tác, tránh cho phép dò toàn bộ danh bạ hoặc hạn mức cá nhân.

Người yêu cầu có thể nhận thông báo “chưa có tuyến duyệt phù hợp”; người vận hành có quyền mới xem chi tiết rằng thiếu slot nào hoặc điều kiện nào chưa đạt.

Email hoặc notification chỉ dẫn tới đối tượng cần xác thực. Sở hữu đường dẫn không tự cấp quyền duyệt.

## 13. Tình huống thực hành

Mai tạo yêu cầu chi 80 triệu VND. Chính sách yêu cầu BUSINESS_OWNER và FINANCE là hai người khác nhau.

Dữ liệu có thẩm quyền cho biết:

~~~text
BUSINESS_OWNER candidates:
  Mai   → person-M, cũng là người tạo
  Lan   → person-L, đủ phạm vi và hạn mức
  Hùng  → person-H, đủ phạm vi và hạn mức

FINANCE candidates:
  Lan         → person-L
  Lan-admin   → person-L
  Hoa         → person-O, đủ phạm vi và hạn mức
~~~

Các kết luận cần rút ra:

1. Mai bị loại theo quy tắc không tự duyệt.
2. Lan và Lan-admin chỉ là một người khi kiểm tra độc lập.
3. BUSINESS_OWNER = Hùng, FINANCE = Lan là một phương án hợp lệ.
4. BUSINESS_OWNER = Lan, FINANCE = Hoa cũng có thể hợp lệ.
5. BUSINESS_OWNER = Lan, FINANCE = Lan-admin không hợp lệ.

Giả sử đã chọn Hùng và Lan, rồi Hùng ủy quyền cho Lan. Hệ thống không được chỉ thay tên Hùng bằng Lan và giữ nguyên kế hoạch. Nó phải đánh giá lại độc lập; có thể chọn Hoa cho FINANCE nếu chính sách cho phép và Hoa vẫn đủ điều kiện.

Nếu Mai tăng yêu cầu lên 150 triệu, kế hoạch cũ không còn đủ: phải xét thêm RISK, kiểm tra lại hạn mức và gắn quyết định với revision mới. Không được lấy hai phiếu của yêu cầu 80 triệu để thực thi yêu cầu 150 triệu.

Nếu không có người phù hợp, kết quả là chưa đủ điều kiện duyệt, không phải “đã có hai người nên cho qua”.

## 14. Câu hỏi tự kiểm tra

1. Vì sao role APPROVER chưa đủ để chọn reviewer cho một đối tượng?
2. Khi nào hai tài khoản khác nhau vẫn chỉ được tính là một người duyệt?
3. Vì sao kiểm tra từng reviewer riêng lẻ chưa chứng minh cả kế hoạch hợp lệ?
4. Một snapshot chính sách giúp audit như thế nào, và vì sao nó không thay thế kiểm tra quyền khi quyết định?
5. Delegation có thể làm mất yêu cầu độc lập bằng những cách nào?
6. Hệ thống nên làm gì nếu mỗi slot đều có ứng viên nhưng không thể gán những người khác nhau?
7. Sau khi một reviewer reject, vì sao reassignment cần quy trình riêng?
8. Kiểm tra nào phải xuất hiện ở endpoint thực thi để không bỏ qua toàn bộ workflow phê duyệt?

Khi thiết kế, hãy mô tả đủ bốn yếu tố: **ai có thẩm quyền**, **với nội dung nào**, **thông qua nguồn quyền nào** và **được tính vào điều kiện hoàn thành ra sao**. Một reviewer được chọn chỉ có ý nghĩa bảo mật khi tất cả các yếu tố đó cùng được giữ đúng đến lúc quyết định được sử dụng.
