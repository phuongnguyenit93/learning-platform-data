# Permission decision trace: truy vết căn cứ của quyết định quyền

## 1. Mục tiêu bài học

Trong chương **Permission Semantics** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **permission decision trace** là bản ghi có cấu trúc giải thích một quyết định quyền đã được hình thành như thế nào.

Một trace hữu ích cần trả lời:

> Ai yêu cầu hành động gì, trên dữ liệu nào, theo chính sách và nguồn quyền nào; những điều kiện nào đã được đánh giá và vì sao kết quả cuối cùng là cho phép, từ chối hoặc chưa thể xác định?

Điều này đặc biệt quan trọng khi một người có nhiều grant, scope chồng lấn, hạn mức, delegation hoặc các điều kiện như không được tự duyệt. Một dòng “user có role FINANCE” thường không giải thích được vì sao chính hành động đó được cho phép.

Sau bài học, bạn có thể:

- Phân biệt decision trace với audit nghiệp vụ, log gỡ lỗi và distributed tracing.
- Thiết kế trace gắn với đúng actor, action, đối tượng, revision và nguồn dữ liệu có thẩm quyền.
- Biểu diễn rule khớp, không khớp, chưa đánh giá và lỗi đánh giá mà không tạo kết luận sai.
- Liên kết quyết định quyền với thực thi, rollback, retry, cache và công việc bất đồng bộ.
- Bảo vệ dữ liệu nhạy cảm trong trace và xây dựng các kiểm thử kiểm chứng lời giải thích.

## 2. Vì sao cần truy vết quyết định quyền?

Xét một reviewer được:

~~~text
READ mọi refund của tenant-1.
APPROVE refund của branch-a trong tenant-1, tối đa 20 triệu VND.
~~~

Reviewer yêu cầu approve một refund 50 triệu ở branch-a.

Các thông báo sau đều thiếu hoặc gây hiểu nhầm:

~~~text
Không có quyền.
Đã tìm thấy role REVIEWER.
Đã đánh giá policy.
~~~

Một trace nội bộ tốt phải cho thấy:

~~~text
Danh tính và tenant hợp lệ.
Đối tượng đang xét là refund R, revision 7.
Nguồn số tiền là snapshot phía server: 50 triệu VND.
Grant READ không áp dụng cho action APPROVE.
Grant APPROVE khớp tenant và branch.
Số tiền vượt hạn mức 20 triệu của chính grant đó.
Không có grant cho phép hoàn chỉnh.
Kết quả: DENY.
~~~

Thông tin này giúp phát hiện lỗi triển khai, chẳng hạn lấy scope rộng của quyền READ ghép với action APPROVE, hoặc lấy số tiền client tự khai để kiểm tra nhưng lại duyệt số tiền khác.

Trace cũng giúp trả lời khi điều tra: chính sách nào cho phép, nguồn quyền nào còn hiệu lực, dữ liệu nào đã cũ và liệu hành động đã thực sự được commit hay chưa.

## 3. Phân biệt các loại bằng chứng

| Loại thông tin | Câu hỏi được trả lời | Điều chưa được chứng minh |
|---|---|---|
| Permission decision trace | Vì sao bộ đánh giá đưa ra quyết định quyền? | Command đã commit hoặc hiệu ứng bên ngoài đã xảy ra |
| Audit nghiệp vụ | Ai thực hiện thay đổi nào, với kết quả gì? | Mọi chi tiết bên trong quá trình đánh giá quyền |
| Security event | Có lần thử bị chặn, bất thường hoặc lỗi kiểm soát nào? | Toàn bộ nội dung nghiệp vụ đã được thực hiện |
| Distributed tracing | Request đi qua dịch vụ nào, mất bao lâu, lỗi ở đâu? | Các rule quyền đã được áp dụng đúng |
| Debug log | Chi tiết hỗ trợ chẩn đoán tại thời điểm chạy | Dữ liệu đủ bền vững và có cấu trúc để chứng minh quyết định |

Có thể liên kết các loại bản ghi bằng ID, nhưng không nên xem chúng là một loại bằng chứng duy nhất.

### 3.1. Permit không đồng nghĩa đã thực hiện

Một command có thể được cho phép nhưng sau đó thất bại vì version xung đột, không còn hạn mức nghiệp vụ hoặc transaction rollback.

~~~text
Decision: PERMIT
Command: ROLLED_BACK
Payment: chưa được tạo
~~~

Ngược lại, client timeout sau commit không có nghĩa hành động chưa xảy ra.

Trace phải giải thích quyết định quyền tại thời điểm đánh giá; audit thực thi phải ghi kết quả hành động. Nếu cần chứng minh đã chi trả, còn phải có bằng chứng từ ranh giới thanh toán phù hợp.

### 3.2. Trace không phải một capability

Biết decisionId, traceId hoặc nhìn thấy một trace PERMIT không tự cấp quyền.

Không cho client gửi ID của một quyết định cũ để bỏ qua kiểm tra hiện tại. Quyết định đó có thể thuộc actor, action, đối tượng hoặc revision khác.

Nếu hệ thống có một giao thức chuyển quyết định giữa các dịch vụ, nó phải ràng buộc và xác minh đầy đủ nội dung, nguồn phát hành, hiệu lực và mục đích. Một ID tra cứu hoặc một JSON do client gửi không tạo ra giao thức đó.

## 4. Chuỗi căn cứ cần được giải thích

Một quyết định thường được xây dựng qua các lớp:

~~~text
Ngữ cảnh xác thực
    → chuẩn hóa yêu cầu quyền
    → chọn policy áp dụng
    → lấy facts có thẩm quyền
    → kiểm tra biên và hạn chế bắt buộc
    → xét các grant/rule liên quan
    → kết hợp kết quả
    → trả quyết định và yêu cầu thực thi đi kèm
~~~

### 4.1. Chuẩn hóa yêu cầu quyền

Trace nên gắn với các thành phần:

~~~text
subject: danh tính đã được xác thực
action: hành động nghiệp vụ thực sự sẽ chạy
resource: đối tượng hoặc phạm vi đích
parameters: tham số có ảnh hưởng đến quyền
context: tenant, thời điểm, nguồn quyền và ngữ cảnh liên quan
~~~

Action phải do server ánh xạ tới handler thực tế. Không ghi action=READ chỉ vì client tự khai, trong khi handler lại approve.

Resource và tham số phải tương ứng với dữ liệu sẽ được thực hiện. Nếu kiểm tra số tiền, trace cần phân biệt giá trị đã được server xác nhận với giá trị client đề xuất.

### 4.2. Facts cần cả nội dung cần thiết và nguồn gốc

Một fact có thể là:

~~~text
refund.branchId = branch-a
nguồn: refund snapshot revision 7

reviewer.limit = 20000000 VND
nguồn: grant G2, entitlement version 203

actor không phải người tạo
nguồn: person identity + lịch sử hồ sơ
~~~

Không phải mọi fact đều cần ghi nguyên giá trị vào trace phổ thông. Có thể lưu một kết quả dẫn xuất an toàn và tham chiếu bằng chứng được bảo vệ.

Tuy nhiên, chỉ ghi “đã kiểm tra hạn mức” mà không biết hạn mức thuộc grant nào hoặc số tiền thuộc revision nào sẽ làm mất khả năng giải thích.

### 4.3. Policy version chưa đủ thay cho mọi phiên bản dữ liệu

Cùng một policy có thể cho kết quả khác nhau khi:

- Actor đổi nhóm hoặc mất quyền.
- Delegation hết hạn.
- Resource đổi branch, owner hoặc số tiền.
- Cây tổ chức thay đổi.
- Quyết định phê duyệt trước đó bị vô hiệu theo chính sách.

Trace cần lưu các phiên bản hoặc thời điểm nguồn dữ liệu liên quan, không chỉ version của file policy.

### 4.4. Tính đầy đủ phải được biểu diễn

Nếu bộ đánh giá dừng sớm sau một điều kiện từ chối bắt buộc, các rule phía sau chưa được đánh giá.

Không ghi chúng là PASS chỉ vì không quan sát thấy lỗi. Có thể ghi:

~~~text
tenant-boundary: FAIL
grant-evaluation: NOT_EVALUATED
reason: short-circuited after mandatory boundary failure
~~~

Nếu chỉ lưu một phần trace do giới hạn dung lượng, phải đánh dấu phần bị lược bỏ. Một bản ghi thiếu không được trình bày như toàn bộ căn cứ đã được kiểm tra.

## 5. Biểu diễn kết quả mà không đánh đồng các trường hợp

Bài học dùng một mô hình kết quả nội bộ để minh họa. Tên trạng thái và cách kết hợp phải được đặc tả theo hệ thống thực tế, không giả định mọi policy engine có cùng ngữ nghĩa.

### 5.1. Kết quả cuối cùng

| Kết quả | Ý nghĩa | Tại điểm thực thi |
|---|---|---|
| PERMIT | Đủ căn cứ cho phép theo policy áp dụng | Tiếp tục các điều kiện thực thi bắt buộc |
| DENY | Có căn cứ từ chối hoặc không có grant cho phép phù hợp | Không tạo hiệu ứng của command bị chặn |
| INDETERMINATE | Không thể kết luận vì thiếu facts hoặc lỗi đánh giá | Không mặc định cho phép |

Nếu chưa xác thực được actor, hệ thống có thể chặn ở lớp authentication trước khi có quyết định quyền. Security event cần phản ánh đúng điều đó, không bịa ra một lần policy evaluation với subject chưa xác định.

### 5.2. Kết quả từng rule hoặc grant

| Trạng thái | Cách hiểu trong mô hình minh họa |
|---|---|
| MATCH_PERMIT | Một grant/rule cho phép đã khớp đầy đủ |
| MATCH_DENY | Một điều kiện cấm rõ ràng đã khớp |
| NOT_APPLICABLE | Rule/grant không cấp quyền cho trường hợp này |
| INDETERMINATE | Không đủ dữ liệu hoặc không đánh giá được |
| NOT_EVALUATED | Chưa chạy do short-circuit hoặc lý do được ghi rõ |

Một điều kiện của grant cho phép bị FAIL không nhất thiết là một explicit deny.

Ví dụ grant READ không áp dụng cho APPROVE. Trace nên thể hiện action không khớp, không nói grant READ đã cấm APPROVE trên toàn hệ thống.

Tương tự, grant hạn mức 20 triệu không cho phép khoản 50 triệu; một grant khác có phạm vi và hạn mức phù hợp vẫn có thể cho phép nếu chính sách kết hợp cho phép điều đó.

### 5.3. Ghi rõ cách kết hợp

Chính sách ví dụ được đánh giá theo thứ tự:

~~~text
1. Kiểm tra đầy đủ các biên/hạn chế bắt buộc liên quan.
2. Nếu vi phạm điều kiện cấm bắt buộc: DENY.
3. Nếu điều kiện bắt buộc chưa xác định được: INDETERMINATE.
4. Nếu có một grant cho phép khớp đầy đủ: PERMIT.
5. Nếu không có grant cho phép khớp: DENY.
~~~

Trace cần ghi chính sách kết hợp hoặc phiên bản thực thi tương ứng. Nếu dùng ưu tiên rule, explicit deny hoặc cơ chế khác, lời giải thích phải phản ánh đúng cơ chế đó.

Không được ghi “không có deny” để suy ra Permit khi policy yêu cầu có ít nhất một grant cho phép.

### 5.4. Lý do chính và các điều kiện phụ

Một quyết định có thể có nhiều điều kiện không đạt. Hệ thống có thể chọn một primaryReason ổn định để xử lý, đồng thời giữ các kết quả đã thực sự đánh giá.

Không chọn ngẫu nhiên một reason theo thứ tự của hash map. Thay đổi thứ tự dữ liệu không nên làm thông báo nghiệp vụ và số liệu vận hành biến động vô nghĩa.

Nếu dừng sớm, chỉ nêu những lý do đã biết. Không khẳng định các điều kiện còn lại hợp lệ.

## 6. Một trace nội bộ có cấu trúc

Ví dụ dưới đây mô tả việc approve 50 triệu ở branch-a. Các ID là dữ liệu minh họa; bản ghi đầy đủ thuộc phạm vi nội bộ được bảo vệ.

~~~json
{
  "schemaVersion": 1,
  "decisionId": "dec-701",
  "requestId": "req-501",
  "evaluatedAt": "2026-11-22T03:00:00Z",
  "subject": {
    "accountId": "account-17",
    "personId": "person-17",
    "activeTenantId": "tenant-1"
  },
  "action": "REFUND_APPROVE",
  "resource": {
    "type": "REFUND",
    "id": "refund-88",
    "version": 18,
    "revision": 7
  },
  "policy": {
    "id": "refund-approval",
    "version": 12,
    "combiningRule": "MANDATORY_THEN_ANY_COMPLETE_PERMIT"
  },
  "facts": {
    "resourceSnapshotRef": "refund-88/revision-7",
    "entitlementVersion": 203,
    "branchId": "branch-a",
    "amount": 50000000,
    "currency": "VND"
  },
  "mandatoryChecks": [
    {
      "ruleId": "tenant-boundary",
      "result": "PASS"
    },
    {
      "ruleId": "independent-reviewer",
      "result": "PASS"
    }
  ],
  "grantEvaluations": [
    {
      "grantId": "grant-read-tenant",
      "result": "NOT_APPLICABLE",
      "checks": [
        {
          "name": "action",
          "result": "FAIL",
          "reasonCode": "ACTION_MISMATCH"
        },
        {
          "name": "remaining-conditions",
          "result": "NOT_EVALUATED"
        }
      ]
    },
    {
      "grantId": "grant-approve-branch-a",
      "result": "NOT_APPLICABLE",
      "checks": [
        {
          "name": "scope",
          "result": "PASS"
        },
        {
          "name": "amount-limit",
          "result": "FAIL",
          "reasonCode": "AMOUNT_EXCEEDS_GRANT_LIMIT",
          "limit": 20000000,
          "currency": "VND"
        }
      ]
    }
  ],
  "coverage": {
    "requiredChecks": "COMPLETE",
    "candidateGrantEvaluation": "COMPLETE"
  },
  "outcome": "DENY",
  "primaryReason": "NO_MATCHING_GRANT"
}
~~~

Trace này chứng minh các căn cứ đã được bộ đánh giá ghi nhận, với mức chi tiết được biểu diễn. Nó không tự chứng minh dữ liệu nguồn không thể bị giả mạo; nguồn facts và cơ chế bảo vệ bản ghi vẫn phải đáng tin cậy.

### 6.1. Không phải mọi triển khai cần lưu toàn bộ ví dụ

Một hệ thống có thể tách:

- Bản tóm tắt quyết định bắt buộc để liên kết với nghiệp vụ.
- Trace chi tiết phục vụ điều tra có quyền truy cập chặt hơn.
- Tham chiếu snapshot hoặc nguồn facts được quản lý riêng.

Nếu chỉ giữ kết quả dẫn xuất, hãy nói rõ giới hạn: có thể giải thích quy tắc nào đã không đạt nhưng chưa chắc tái hiện chính xác toàn bộ lần đánh giá cũ.

### 6.2. Gắn schema version với hợp đồng sử dụng

Reason code, kiểu action, trạng thái rule và nghĩa của các trường cần có hợp đồng ổn định.

Một công cụ báo cáo không nên phải phân tích chuỗi văn bản như “reviewer có vẻ thiếu quyền”. Dùng reason code có định nghĩa, còn câu giải thích cho người dùng được dựng theo ngôn ngữ và quyền xem phù hợp.

Các thay đổi schema hoặc ngữ nghĩa cần được quản lý để trace cũ vẫn được đọc đúng.

## 7. Sinh trace từ chính lần đánh giá đang ra quyết định

### 7.1. Tránh đánh giá lần hai chỉ để giải thích

Mẫu xử lý sau có thể tạo lời giải thích sai:

~~~text
Lần 1: evaluate → PERMIT.
Dữ liệu quyền hoặc đối tượng thay đổi.
Lần 2: explain → DENY.
Lưu trace của lần 2 cạnh command đã dùng quyết định lần 1.
~~~

Trace phải được tạo từ chính các facts và nhánh xử lý của lần quyết định được sử dụng.

Một endpoint mô phỏng có thể đánh giá lại chính sách hiện tại, nhưng phải ghi đó là simulation/explanation mới, có ID và thời điểm riêng.

### 7.2. Java minh họa

Mã sau dùng các kiểu giả định và tập grant cho phép. Các hạn chế bắt buộc được kiểm tra trước theo chính sách ví dụ.

TraceRecorder thu thập vào bộ nhớ, không gọi dịch vụ log bên ngoài ở mỗi predicate. Facts là snapshot đã chuẩn hóa; các phép kiểm tra không tạo hiệu ứng nghiệp vụ.

~~~java
Evaluation evaluate(AuthzRequest request, PolicyFacts facts) {
    var trace = TraceRecorder.start(
            decisionIds.next(), request.safeSummary(),
            facts.safeEvidenceRefs());

    try {
        facts.requireTrustedAndSufficient();

        if (!trace.check("tenant-boundary",
                boundaries.allow(request, facts))) {
            trace.skipGrantEvaluation("MANDATORY_BOUNDARY_FAILED");
            return trace.finish(DENY, "OUTSIDE_TENANT");
        }

        if (!trace.check("independent-reviewer",
                duties.isIndependent(request, facts))) {
            trace.skipGrantEvaluation("MANDATORY_RESTRICTION_FAILED");
            return trace.finish(DENY, "DUTY_CONFLICT");
        }

        for (var grant : facts.permitGrants()) {
            trace.startGrant(grant.id());

            if (!trace.check("action",
                    grant.actions().contains(request.action()))) {
                trace.notApplicableAndSkipRest("ACTION_MISMATCH");
                continue;
            }

            if (!trace.check("scope",
                    scopes.matches(grant, request, facts))) {
                trace.notApplicableAndSkipRest("OUTSIDE_GRANT_SCOPE");
                continue;
            }

            if (!trace.check("conditions",
                    conditions.matches(grant, request, facts))) {
                trace.notApplicableAndSkipRest("GRANT_CONDITION_FAILED");
                continue;
            }

            trace.matchedPermit(grant.id());
            trace.skipRemainingGrants("COMPLETE_PERMIT_FOUND");
            return trace.finish(PERMIT, "MATCHING_GRANT");
        }

        return trace.finish(DENY, "NO_MATCHING_GRANT");
    } catch (RequiredFactUnavailable ex) {
        trace.recordFactFailure(ex.safeCode());
        return trace.finish(INDETERMINATE, "REQUIRED_FACT_UNAVAILABLE");
    }
}
~~~

Trong ví dụ, scopes.matches phải kiểm tra cả loại tài nguyên và toàn bộ phạm vi của grant. conditions.matches bao gồm hiệu lực, hạn mức, currency và các điều kiện áp dụng. Các helper phải có hợp đồng rõ ràng; trace không sửa được một predicate đã viết sai.

Mỗi phép kiểm tra dùng đúng kết quả boolean đã tính. Không gọi lại predicate chỉ để lấy chi tiết log.

### 7.3. Những giới hạn của mã minh họa

- Chính sách này dừng khi có một grant cho phép hoàn chỉnh sau các kiểm tra bắt buộc. Grant còn lại được ghi là chưa đánh giá.
- Nếu hệ thống có explicit deny ở nơi khác, không được dùng cùng thứ tự này mà bỏ sót deny.
- Lỗi ngoài nhóm đã biết cần được tầng thực thi xử lý an toàn, không được mặc định thành Permit.
- Nội dung safeSummary và safeEvidenceRefs phải được định nghĩa bằng danh sách trường cho phép.
- Evaluation là kết quả nội bộ có cấu trúc; nó chưa commit command và chưa phát lệnh thanh toán.

Một trace dài nhưng không phản ánh đúng nhánh quyết định vẫn không có giá trị giải thích.

## 8. Liên kết quyết định với điểm thực thi

### 8.1. Điểm thực thi phải dùng đúng kết quả

Mẫu điều kiện sau có thể cho INDETERMINATE đi qua:

~~~text
Nếu decision khác DENY:
    thực hiện command
~~~

Điểm thực thi phải yêu cầu một kết quả Permit hợp lệ theo hợp đồng, đồng thời kiểm tra các ràng buộc và nghĩa vụ đi kèm.

Quyết định phải gắn với đúng:

~~~text
actor và nguồn thẩm quyền
action thực tế
tenant và resource
revision/version liên quan
tham số trọng yếu
policy/facts và hiệu lực áp dụng
~~~

Không evaluate refund R1 rồi execute R2. Không approve amount từ revision 7 bằng quyết định dựa trên revision 6.

### 8.2. Quyết định và kiểm tra nghiệp vụ cần cùng ranh giới nhất quán

Một luồng có thể tổ chức:

~~~text
Bắt đầu transaction
    → khóa/nạp dữ liệu cần bảo vệ
    → thu thập facts có thẩm quyền
    → evaluate và tạo trace
    → yêu cầu Permit, kiểm tra binding và nghĩa vụ
    → kiểm tra version/trạng thái/bất biến nghiệp vụ
    → ghi thay đổi
    → ghi bằng chứng quyết định tối thiểu và audit
    → ghi outbox cần thiết
Commit
    → công bố kết quả thành công
~~~

Cơ chế khóa/version phải bảo vệ các thuộc tính đã dùng để quyết định. Nếu chúng ở dịch vụ ngoài, cần giao thức về độ mới và thu hồi quyền phù hợp; transaction nội bộ không tự khóa nguồn ngoài.

Trace có thể ghi phiên bản dữ liệu đã quan sát, nhưng việc ghi đó không tự ngăn được cuộc đua. Cần cả bằng chứng lẫn cơ chế thực thi.

### 8.3. Nghĩa vụ kèm Permit phải được thực hiện

Một số hệ thống trả quyết định cùng các yêu cầu như:

- Chỉ trả một tập trường được phép.
- Chỉ trả các dòng thuộc scope đã xác định.
- Yêu cầu xác thực tăng cường trước hành động.
- Ghi bằng chứng bắt buộc.
- Áp dụng giới hạn hiệu lực hoặc tham số.

Nếu điểm thực thi bỏ qua các yêu cầu đó, một trace PERMIT có thể trông hợp lệ trong khi dữ liệu trả ra vẫn vượt quyền.

Cần ghi rõ các yêu cầu đã được thực thi hay điểm thực thi đã chặn vì không hỗ trợ. Không sửa trace policy thành “đã từ chối” để che việc policy từng cho phép có điều kiện nhưng enforcement không đáp ứng được.

### 8.4. Bằng chứng bắt buộc và trace chẩn đoán có thể có hợp đồng khác nhau

Với hành động nhạy cảm, hệ thống có thể yêu cầu một bản ghi tối thiểu:

~~~text
decisionId
actor, action, resource và revision
outcome = PERMIT
policy/fact version cần thiết
tham chiếu command/transition
~~~

Bản ghi này cùng audit có thể được commit với thay đổi nghiệp vụ. Nếu không lưu được bằng chứng bắt buộc, transaction không được công bố thành công.

Trace chi tiết phục vụ chẩn đoán có thể được xuất bất đồng bộ. Nếu chỉ là dữ liệu tùy chọn, lỗi xuất nó không nhất thiết phải dừng mọi nghiệp vụ. Hợp đồng phải nêu rõ phần nào bắt buộc, phần nào được phép thiếu và cách phát hiện mất dữ liệu.

Không gọi một hệ thống log từ xa ở từng predicate rồi coi đó là transaction nguyên tử với cơ sở dữ liệu nghiệp vụ.

### 8.5. Trace của lần bị từ chối không được mất vì rollback ngoài ý muốn

Một request Deny không có thay đổi nghiệp vụ để commit. Nếu security event được ghi trong transaction rồi transaction rollback, bản ghi đó cũng có thể mất.

Cần thiết kế đường ghi sự kiện từ chối phù hợp, chẳng hạn ghi sau khi handler đã kết luận hoặc qua cơ chế ghi sự kiện độc lập được bảo vệ. Lỗi ghi trace không được biến Deny thành Permit.

Tương tự, một lần Permit rồi rollback có thể có attempt event ghi:

~~~text
decision = PERMIT
enforcement = BUSINESS_CONFLICT
command = ROLLED_BACK
~~~

Không để bản ghi attempt bị hiểu thành audit thành công.

## 9. Thời điểm và chuỗi quyết định qua nhiều dịch vụ

### 9.1. Quyết định là sự kiện trong một ngữ cảnh thời gian

Trace nên phân biệt các mốc liên quan:

~~~text
factsObservedAt
evaluatedAt
commandCommittedAt
externalEffectConfirmedAt
~~~

Không phải mọi trace đều có cả bốn. Nếu chưa commit hoặc chưa biết kết quả ngoài, không điền một thời điểm giả để làm bản ghi trông đầy đủ.

Một trace Permit hôm qua không chứng minh hôm nay actor còn quyền. Ngược lại, người đó mất quyền hôm nay không tự chứng minh quyết định hôm qua sai.

### 9.2. Một correlationId không thay thế decisionId

Một request có thể đi qua nhiều điểm kiểm tra:

~~~text
Gateway: kiểm tra capability truy cập API
Application: kiểm tra APPROVE theo đối tượng
Worker: kiểm tra EXECUTE theo operation được giao
~~~

Các quyết định khác nhau nên có ID riêng và liên kết được qua requestId, operationId hoặc parentDecisionId khi có quan hệ phù hợp.

CorrelationId giúp tìm chuỗi sự kiện. Nó không chứng minh caller đã được cho phép tại mọi bước và không được dùng để bỏ qua kiểm tra.

Giá trị correlation do bên ngoài gửi cần được xử lý như dữ liệu, không như danh tính hoặc nguồn thẩm quyền.

### 9.3. Ghi đúng actor ở từng bước

Một job có thể do Lan khởi tạo nhưng worker-service là principal thực hiện ở bước sau.

Trace nên phân biệt:

- Principal đang được xác thực tại điểm kiểm tra.
- Người khởi tạo nghiệp vụ.
- Danh tính thực tế và danh tính có hiệu lực khi thao tác thay mặt.
- Nguồn delegation hoặc phạm vi ủy nhiệm.
- Operation và snapshot mà công việc được phép xử lý.

Không ghi worker là Lan nếu worker đang dùng một thẩm quyền dịch vụ khác. Cũng không làm mất người khởi tạo chỉ vì dữ liệu đã đi qua hàng đợi.

Các thuộc tính này phải đến từ ngữ cảnh tin cậy, không từ một trường actorId bất kỳ trong message.

### 9.4. Chấp nhận công việc và thực thi công việc là hai quyết định

Một Permit cho việc tạo job không tự cho phép job thực hiện mọi hành động về sau.

Nếu chính sách yêu cầu đánh giá lại khi worker chạy, trace của lần đánh giá mới phải lưu facts và quyền áp dụng lúc đó. Nếu có quyền ủy nhiệm được chốt cho công việc, cần mô tả phạm vi và hiệu lực của quyền đó.

Khi worker nhận bằng chứng một khoản thanh toán đã xảy ra, ghi nhận sự thật đó khác với xin phép tạo khoản thanh toán mới. Trace phải nêu đúng action để không nhầm giữa đối soát và phát sinh hiệu ứng.

## 10. Cache và idempotency cần giữ nguồn gốc quyết định

### 10.1. Cache hit không phải một lần chạy lại mọi rule

Một bản ghi cache có thể chứa kết quả và tham chiếu trace gốc. Khi sử dụng, phải kiểm tra nó áp dụng cho đúng actor, action, tenant, resource, tham số và các phiên bản/hiệu lực liên quan.

Một cách biểu diễn:

~~~text
decisionId = ID của lần phục vụ quyết định hiện tại
evaluationMode = CACHE_HIT
originDecisionId = quyết định đã tạo cache
sourceEvaluatedAt = thời điểm đánh giá gốc
servedAt = thời điểm sử dụng hiện tại
bindingValidation = kết quả kiểm tra áp dụng cache
~~~

Không sao chép các rule PASS cũ rồi đổi timestamp để tạo ấn tượng chúng vừa được đánh giá lại.

Nếu chỉ kiểm tra cache key mà chưa kiểm chứng các phụ thuộc cần thiết, trace không được khẳng định quyền đã được xác nhận mới.

### 10.2. Replay command không có nghĩa execute lần nữa

Lần đầu có thể:

~~~text
D1: APPROVE → PERMIT
Command C1: COMMITTED
Response: bị mất
~~~

Khi retry cùng khóa và cùng nội dung:

~~~text
D2: kiểm tra quyền hiện tại để đọc kết quả/receipt
Response: trả kết quả của C1
New approval effect: không có
~~~

Trace nên liên kết replay với command và decision gốc, đồng thời phân biệt quyết định quyền truy cập kết quả hiện tại.

Biết idempotency key không phải bằng chứng được xem receipt. Nếu một job chưa hoàn tất thực sự tiếp tục chạy, nó vẫn phải tuân thủ chính sách thực thi của job, không chỉ quy tắc trả receipt.

### 10.3. Không gộp mọi lần thử thành một quyết định

Một command có thể được gửi nhiều lần, bị từ chối một lần rồi được phép sau khi quyền thay đổi.

Giữ các attempt và decision riêng, liên kết bằng định danh phù hợp. Không ghi đè trace Deny cũ bằng Permit mới hoặc đếm mọi retry thành nhiều hành động đã thành công.

## 11. Tái hiện quyết định phục vụ điều tra

Có thể cần chạy bộ đánh giá trên policy và facts lịch sử để kiểm tra kết quả. Muốn tái hiện chính xác, cần biết:

- Phiên bản policy và ngữ nghĩa kết hợp.
- Phiên bản bộ đánh giá và các helper ảnh hưởng kết quả.
- Facts cần thiết, nguồn gốc, kiểu dữ liệu và thời điểm.
- Cách biểu diễn số tiền, currency, thời gian và các quan hệ danh tính.
- Những phần trace/facts đã bị lược bỏ hoặc không còn được lưu.

Một trace chỉ giữ reason code không đủ để hứa tái hiện chính xác mọi quyết định.

Replay điều tra phải dùng môi trường hoặc chế độ đánh giá không tạo hiệu ứng nghiệp vụ. Nó có replayRunId riêng và tham chiếu originalDecisionId; không được phát lệnh chi trả, tạo assignment hay ghi audit giả như một thao tác người dùng mới.

Nếu kết quả khác, cần phân biệt do policy, facts, phiên bản engine hay thiếu bằng chứng, thay vì lập tức kết luận lần gốc sai.

Hash giúp đối chiếu nội dung khi có một tham chiếu đáng tin cậy; riêng việc lưu một hash cạnh dữ liệu không chứng minh được nguồn gốc hoặc chống người có thể sửa cả hai.

## 12. Trace là dữ liệu cần được bảo vệ

### 12.1. Chi tiết giải thích có thể làm lộ chính sách và dữ liệu

Một trace có thể tiết lộ:

- Actor thuộc nhóm nào và có những grant nào.
- Giới hạn phê duyệt của một người hoặc đơn vị.
- Quan hệ quản lý, delegation hoặc danh tính người tạo.
- Tenant, branch và tài nguyên tồn tại.
- Số tiền, phân loại rủi ro hoặc thông tin người thụ hưởng.
- Cấu trúc rule và nhánh ngoại lệ vận hành.

Không trả toàn bộ trace cho mọi caller bị từ chối.

Có thể tách mức hiển thị:

| Người xem | Thông tin phù hợp theo chính sách |
|---|---|
| Caller thông thường | Thông báo an toàn và mã tham chiếu hỗ trợ |
| Nhân viên hỗ trợ trong phạm vi | Kết quả và nhóm lý do cần thiết |
| Người điều tra được cấp quyền | Trace chi tiết, facts và bằng chứng được phép |
| Người quản trị policy | Thông tin phục vụ kiểm tra policy trong scope tương ứng |

Quyền xem trace cần action và scope riêng. Biết decisionId hoặc có quyền xem resource hiện tại không mặc định cho xem toàn bộ lịch sử quyền của những người khác.

### 12.2. Bảo vệ endpoint explain và simulation

Một endpoint cho client tự chọn actorId, resourceId và policy rồi trả toàn bộ lời giải thích có thể trở thành công cụ dò danh tính, đối tượng và quy tắc nội bộ.

Cần kiểm tra quyền của người yêu cầu giải thích, hạn chế dữ liệu mục tiêu và bảo đảm simulation không tạo hiệu ứng nghiệp vụ.

Nếu cho phép giả lập một chủ thể khác để quản trị policy, bản ghi phải thể hiện người chạy mô phỏng và subject giả lập riêng biệt. Không dùng kết quả mô phỏng làm quyết định thật cho một command của subject đó.

### 12.3. Dùng cấu trúc và danh sách trường cho phép

Không tự động dump:

~~~text
toàn bộ token
Authorization header
toàn bộ request/response
raw exception chứa dữ liệu bí mật
toàn bộ entity hoặc hồ sơ nhân sự
~~~

Chọn trường cần thiết, chuẩn hóa kiểu dữ liệu và mã hóa theo định dạng log. Dữ liệu người dùng có ký tự xuống dòng hoặc nội dung giống log không được làm giả một bản ghi khác.

Thay định danh bằng mã giả hoặc hash có thể hỗ trợ giảm lộ dữ liệu, nhưng không tự làm dữ liệu trở nên ẩn danh. Giá trị có miền nhỏ hoặc quan hệ dễ nối vẫn có thể bị suy ra.

### 12.4. Bảo vệ tính toàn vẹn và vòng đời

Cần kiểm soát ai được ghi, đọc, xuất, sửa hoặc xóa trace. Người bị kiểm soát không nên tự thay đổi bằng chứng để che một hành động của mình.

Có thể dùng kho chỉ cho phép ghi thêm, quyền truy cập tách biệt hoặc cơ chế kiểm chứng toàn vẹn theo nhu cầu. Các cơ chế này vẫn cần quản lý nguồn ghi và khóa/đặc quyền liên quan.

Thời hạn giữ trace phải phù hợp mục đích điều tra và chính sách dữ liệu. Nếu facts hoặc policy lịch sử hết thời hạn lưu, công cụ điều tra cần phản ánh rằng không còn đủ dữ liệu để tái hiện đầy đủ.

### 12.5. Giới hạn dung lượng không được cắt mất kiểm soát quyền

Một actor có nhiều grant hoặc liên tục gửi request bị chặn có thể tạo lượng trace lớn.

Nên giới hạn dung lượng bản ghi, số facts được xuất và tốc độ các truy vấn giải thích. Nhưng phải phân biệt:

~~~text
Giới hạn ghi trace:
    có thể lược bớt chi tiết và đánh dấu thiếu

Giới hạn đánh giá policy:
    không được bỏ kiểm tra bắt buộc rồi mặc định Permit
~~~

Nếu không đủ ngân sách để đánh giá điều kiện cần thiết, kết quả phải phản ánh chưa xác định/lỗi theo hợp đồng và không tạo hiệu ứng trái phép.

Sampling có thể dùng cho chi tiết chẩn đoán tùy chọn. Không dùng nó để tuyên bố có bằng chứng tối thiểu cho mọi hành động nhạy cảm nếu thực tế chỉ lưu một phần.

Các bộ đếm vận hành có thể tổng hợp theo action/reason code; tránh đưa mọi resourceId hoặc decisionId thành một nhãn riêng không giới hạn.

## 13. Kiểm thử cả quyết định và lời giải thích

### 13.1. Ma trận tình huống

| Tình huống | Điều phải kiểm chứng |
|---|---|
| Một grant cho phép khớp đầy đủ | Permit và trace chỉ ra đúng grant, action, resource và facts |
| Có READ rộng nhưng APPROVE hẹp | Không ghép scope READ vào APPROVE; trace giữ từng grant riêng |
| Scope đúng nhưng vượt hạn mức | Trace ghi đúng điều kiện thất bại và số tiền có thẩm quyền |
| Grant không khớp action | NOT_APPLICABLE; điều kiện chưa chạy không được ghi PASS |
| Biên tenant thất bại | Deny; các bước bị bỏ qua được ghi NOT_EVALUATED |
| Nguồn quyền không trả lời | Indeterminate/lỗi phù hợp; không cho command thực hiện |
| Policy có kiểm tra bắt buộc trước grant | Không dừng ở một permit sớm rồi bỏ sót hạn chế bắt buộc |
| Short-circuit sau permit hợp lệ | Trace ghi rõ các grant còn lại chưa đánh giá |
| Resource đổi sau lần quan sát cũ | Không áp dụng sai binding; trace gắn dữ liệu thực sự dùng |
| Permit rồi domain conflict | Không có audit commit giả; attempt và rollback được phân biệt |
| Không lưu được bằng chứng tối thiểu bắt buộc | Không commit hành động theo hợp đồng |
| Xuất trace chẩn đoán tùy chọn lỗi | Xử lý đúng chính sách; không mất bằng chứng bắt buộc hoặc mở quyền |
| Deny rồi transaction rollback | Đường ghi security event không vô tình làm mất bằng chứng được yêu cầu |
| Cache hit | Có nguồn quyết định gốc; không giả các rule vừa được chạy lại |
| Retry command đã commit | Liên kết kết quả gốc, không thêm hiệu ứng hoặc giả thêm lần approve |
| Caller đoán/biết decisionId | Không đọc trace ngoài quyền |
| Chạy simulation/replay điều tra | Không tạo thay đổi nghiệp vụ |
| Trace vượt giới hạn dung lượng | Đánh dấu thiếu chi tiết; vẫn đánh giá đầy đủ điều kiện bắt buộc |
| Payload chứa chuỗi bí mật hoặc ký tự điều khiển | Trace theo allowlist, không dump/làm giả bản ghi |
| Worker thực hiện thay người khởi tạo | Principal hiện tại, người khởi tạo và nguồn thẩm quyền được phân biệt |

### 13.2. Đừng chỉ snapshot toàn bộ JSON

Timestamp, ID và thứ tự các mục không có ý nghĩa chính sách có thể thay đổi hợp lệ. Kiểm thử nên xác nhận những quan hệ quan trọng:

~~~text
decisionId của audit tham chiếu đúng evaluation đã dùng
actor/action/resource khớp command
resource revision khớp nội dung được duyệt
grantId khớp nguồn quyền thực sự
facts và reason code giải thích đúng kết quả
không có điều kiện chưa chạy bị ghi PASS
không có hiệu ứng của command bị chặn
~~~

Có thể kiểm tra schema và các trường bắt buộc riêng. Không ràng buộc test vào một thứ tự trình bày tùy ý nếu hợp đồng không yêu cầu thứ tự đó.

### 13.3. Kiểm thử rằng chỉ có một lần đánh giá nguồn facts

Một ca kiểm thử có thể cho nguồn dữ liệu trả hai phiên bản khác nhau nếu bị gọi lại:

~~~text
Lần đọc đầu: amount = 50 triệu, revision 7.
Lần đọc sau: amount = 10 triệu, revision 8.
~~~

Luồng được thiết kế đúng phải dùng snapshot đã chọn và được bảo vệ cho quyết định liên quan; không tạo decision từ phiên bản này rồi giải thích bằng phiên bản khác.

Khi kiểm thử thực thi, cần dùng transaction/version tương ứng để xác nhận nội dung bị thay đổi không vượt qua binding. Chỉ kiểm tra số lần gọi mock không chứng minh concurrency đã được bảo vệ, nhưng giúp phát hiện một đường explain đọc lại ngoài ý định.

### 13.4. Kiểm thử việc thiếu dữ liệu

Xóa một fact bắt buộc, như nguồn hạn mức hoặc quan hệ tenant, rồi yêu cầu approve.

Cần xác nhận:

- Trace nêu fact hoặc nguồn thất bại bằng mã an toàn.
- Không ghi nhầm “không có grant” nếu thực tế chưa đọc được tập grant.
- Enforcement không coi Indeterminate là Permit.
- Không có decision nghiệp vụ, reservation hay outbox của lần approve bị chặn.
- Response không làm lộ chi tiết nguồn quyền nội bộ cho caller ngoài phạm vi.

## 14. Tình huống điều tra: trace nói gì khi số tiền bị thay?

Hùng có hạn mức approve 20 triệu VND tại branch-a. Refund R đang ở revision 7 với số tiền 50 triệu. Client gửi thêm amount=1000 trong body approve.

Một triển khai lỗi có thể kiểm tra 1000 nhưng handler lại approve 50 triệu đã lưu.

Khi điều tra, cần nối các bằng chứng:

~~~text
Command:
  ai gửi, action nào, object nào, expected version nào

Decision trace:
  amount nào được dùng để đánh giá
  nguồn amount là client hay snapshot server
  grant và limit nào được dùng
  revision/facts nào được ghi

Audit thực thi:
  revision nào đã được approve
  số tiền và trạng thái nào đã commit
  decisionId nào được tham chiếu
~~~

Nếu trace dùng 1000 từ client nhưng audit approve revision 7 với 50 triệu, lỗi nằm ở binding giữa quyết định và dữ liệu thực thi. Chỉ đổi thông báo lỗi hoặc thêm log role sẽ không sửa được vấn đề.

Cách thiết kế phù hợp là evaluate trên số tiền có thẩm quyền của đúng snapshot, bảo vệ snapshot khi ghi và chỉ cho command thực thi với binding đó. Trong ví dụ, kết quả phải là không có grant approve phù hợp.

Trace chỉ hữu ích khi nguồn facts được ghi đúng. Một nhãn “DATABASE” do code gán tùy ý không tự chứng minh dữ liệu thật sự đến từ cơ sở dữ liệu; cần kiểm thử và đối chiếu nguồn được bảo vệ.

Nếu trace Deny nhưng có một lần approve thành công, trước hết kiểm tra chúng có cùng attempt/command và cùng binding hay không. Chỉ sau khi xác nhận cùng lần thực thi mới kết luận enforcement đã bỏ qua quyết định; tránh nhầm một Deny mới với một Permit hợp lệ trước đó.

## 15. Khung đặc tả decision trace

Có thể dùng khung sau khi thiết kế:

~~~text
Hành động và điểm đánh giá:
Định danh decision/attempt và cách liên kết command:
Actor, action, resource, revision và tham số trọng yếu:
Nguồn facts và các phiên bản cần giữ:
Policy và ngữ nghĩa kết hợp:

Trạng thái từng rule/grant:
Short-circuit và cách đánh dấu chưa đánh giá:
Outcome, primary reason và coverage:
Nghĩa vụ đi kèm và kết quả enforcement:

Bằng chứng tối thiểu bắt buộc:
Trace chi tiết tùy chọn:
Cách ghi khi Deny, rollback, cache, replay và async:
Quyền đọc trace và mức giải thích cho từng đối tượng:
Redaction, tính toàn vẹn, thời hạn lưu và giới hạn dung lượng:
Ca kiểm thử nối trace với dữ liệu đã commit:
~~~

## 16. Câu hỏi tự kiểm tra

1. Vì sao một trace Permit chưa chứng minh hành động đã commit?
2. Grant không áp dụng khác explicit deny như thế nào?
3. Tại sao rule chưa chạy không được ghi PASS?
4. Ngoài policy version, những phiên bản facts nào ảnh hưởng quyết định của bạn?
5. Nếu explain chạy sau evaluate trên dữ liệu mới, lời giải thích có thể sai ra sao?
6. Cache hit và replay idempotency cần liên kết quyết định gốc thế nào?
7. Caller được biết mã tham chiếu hỗ trợ có đồng nghĩa được xem trace không?
8. Nếu hệ thống ghi trace bị lỗi, phần bằng chứng nào bắt buộc phải tồn tại trước khi công bố hành động thành công?

Một decision trace đáng tin cậy phải nối được **căn cứ đã dùng, quyết định đã trả và lần thực thi tương ứng**. Nó cần đủ rõ để điều tra một lỗi quyền, đồng thời không mở thêm đường đọc dữ liệu hoặc thay thế chính kiểm soát quyền mà nó đang giải thích.
