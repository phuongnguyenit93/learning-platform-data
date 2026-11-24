# Explicit rule composition — Ghép quy tắc nghiệp vụ tường minh

Bài học thuộc chương **Implementation Patterns** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Nội dung tập trung vào cách ghép các quy tắc thành một quyết định có cấu trúc rõ ràng để chống bỏ qua phê duyệt, thao tác sai quyền, sửa dữ liệu quan trọng và gửi lệnh trùng.

Từng rule có thể đúng khi đứng riêng nhưng policy tổng vẫn sai. Ví dụ, hệ thống đã có kiểm tra tenant và trạng thái, rồi bổ sung ngoại lệ supervisor bằng một nhánh `OR` ở ngoài cùng. Ngoại lệ đó có thể vô tình miễn cả tenant, trạng thái và quy tắc người tạo không tự duyệt.

**Explicit rule composition** là cách định nghĩa tường minh các rule tham gia, toán tử kết hợp, phạm vi của ngoại lệ, cách xử lý kết quả chưa xác định và vị trí cưỡng chế quyết định. Nó không đòi hỏi một thư viện hay rule engine cụ thể. Có thể bắt đầu bằng các hàm Java có tên và một cấu trúc ghép đủ nhỏ để review được.

Mục tiêu của bài là thiết kế **policy tổng**, không chỉ trừu tượng hóa một điều kiện thành predicate. Ví dụ dùng Java 21; transaction và repository ở phần use case là hợp đồng minh họa cần hiện thực trong ứng dụng.

Sau bài học, bạn cần có thể:

- Viết policy thành cây có nhóm bắt buộc và nhóm lựa chọn rõ ràng.
- Phân biệt điều kiện đạt, không đạt và chưa có đủ dữ kiện để kết luận.
- Giới hạn ngoại lệ vào đúng rule được thay thế.
- Giữ việc đánh giá thuần, tách khỏi mutation và tác động ngoài.
- Bảo vệ quyết định trước cạnh tranh dữ liệu, retry và đường gọi nội bộ.
- Kiểm thử cả cấu trúc ghép rule lẫn kết quả bền vững của use case.

## 1. Quy tắc riêng lẻ chưa đủ tạo thành một policy an toàn

Giả sử một hệ thống duyệt yêu cầu hoàn tiền. Checker thông thường được xử lý request trong chi nhánh được phân công. Supervisor được xử lý mọi chi nhánh trong tenant của mình. Cả hai vẫn cần có quyền duyệt, không được là maker, không vượt hạn mức và chỉ duyệt nội dung đang chờ.

Một biểu thức dễ viết nhưng sai:

~~~text
(đúng tenant AND được phân công AND đang chờ duyệt) OR là supervisor
~~~

Biểu thức này cho supervisor đi thẳng tới kết quả cho phép. Chỉ thêm rule `đúng tenant` vào danh sách code chưa chứng minh rule đó bắt buộc trên mọi đường cho phép.

Một cấu trúc phù hợp hơn:

~~~text
đúng tenant
AND membership đang hoạt động
AND có quyền refund.approve
AND checker khác maker
AND kiểm tra rủi ro không chặn
AND (được phân công chi nhánh OR supervisor trong scope)
AND số tiền nằm trong thẩm quyền
AND request đang chờ duyệt
AND version và nội dung khớp lần xem xét
AND còn thời hạn duyệt
~~~

Ngoại lệ supervisor chỉ thay thế điều kiện phân công chi nhánh. Nó không thay thế các điều kiện còn lại.

OWASP khuyến nghị mặc định từ chối khi chưa có quyền cho phép rõ ràng và kiểm tra quyền trên từng request. Cách ghép policy phải giữ được hai tính chất đó cả khi bổ sung đường vào hoặc nhánh ngoại lệ. [OWASP: Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html#deny-by-default).

### 1.1. Hợp đồng của một lần đánh giá

Trước khi viết composer, cần mô tả được:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Subject | Actor nào được xác minh, đang hành động trong tenant nào? |
| Action | Đang duyệt, sửa, hủy hay thực thi hoàn tiền? |
| Resource | Request nào, revision nào và dữ liệu trọng yếu nào? |
| Context | Thời điểm, membership, scope và policy version nào? |
| Combination | Rule nào bắt buộc, nhánh nào là lựa chọn, điều gì phủ quyết? |
| Enforcement | Kết quả được dùng ở đâu trước mutation, với cơ chế đồng thời nào? |
| Failure | Thiếu rule, lỗi facts, kết quả unknown hoặc cấu hình rỗng dẫn đến đâu? |

Không dùng chung một policy mơ hồ tên `canProcess` cho mọi action. Người được đọc hoặc hủy request không mặc nhiên được duyệt hay đánh dấu chuyển tiền thành công.

## 2. Viết cây quyết định và bất biến trước khi viết vòng lặp

### 2.1. Tách các nhóm có ý nghĩa

Một cây minh họa cho action `refund.approve`:

~~~text
refund.approve.v1 : ALL
├── scope : ALL
│   ├── tenantMatches
│   ├── activeMembership
│   └── approvePermission
├── separation : checkerDifferentFromMaker
├── risk : clearForApproval
├── assignment : ANY
│   ├── assignedToBranch
│   └── supervisorInTenant
├── money : withinApprovalLimit
└── transition : ALL
    ├── pendingApproval
    ├── rowVersionMatches
    ├── reviewedContentMatches
    └── beforeApprovalDeadline
~~~

`ALL` nghĩa là mọi điều kiện con phải đạt. `ANY` nghĩa là ít nhất một nhánh con đủ để đạt nhóm đó. Những quy tắc phủ quyết như "request bị chặn rủi ro" phải nằm trong nhóm bắt buộc, không nằm như một lựa chọn có thể bị nhánh allow khác bỏ qua.

Cây này cũng giúp xác định rule nào cần facts nào. Rule hạn mức cần tiền/currency phía server và grant của actor; rule checker độc lập cần person identity đáng tin; rule version cần dữ liệu server và version client đã xem.

### 2.2. Những điều nên trở thành bất biến có thể kiểm thử

~~~text
Nếu tenant không khớp thì không có đường nào cho phép duyệt.
Nếu checker là maker thì supervisor cũng không tự duyệt được.
Nếu rủi ro bắt buộc chưa được xác định thì không tạo approval.
Nếu content version thay đổi thì quyết định cũ không dùng cho nội dung mới.
Nếu policy không tồn tại hoặc cấu hình không hợp lệ thì không tạo tác động.
Chỉ một quyết định đạt toàn bộ policy mới đi tới transition được bảo vệ.
~~~

Một bất biến không chỉ là dòng trong tài liệu. Nó phải được giữ bởi cây policy, đường gọi use case và cơ chế ghi dữ liệu tương ứng.

### 2.3. Tránh phụ thuộc vào thứ tự tình cờ

Một vòng lặp trả về `true` khi gặp rule allow đầu tiên có thể bỏ qua rule cấm phía sau. Một vòng lặp khác chỉ trả về `false` khi gặp deny sẽ có ngữ nghĩa khác. Thứ tự đăng ký bean, thứ tự `HashMap` hoặc filter loại bỏ một rule không được âm thầm quyết định quyền.

Nếu dùng chiến lược "rule đầu tiên khớp quyết định kết quả", phải định nghĩa priority, cách khớp, fallback và cách phát hiện rule bị che. Trong ví dụ của bài, các nhóm được định nghĩa bằng ALL/ANY rõ ràng; không dùng first-match để quyết định giữa scope bắt buộc với ngoại lệ supervisor.

## 3. Định nghĩa ngữ nghĩa cho PASS, FAIL và UNKNOWN

Một rule điều kiện trả về:

- `PASS`: đã có dữ kiện hợp lệ chứng minh điều kiện thỏa.
- `FAIL`: đã có dữ kiện hợp lệ chứng minh điều kiện không thỏa.
- `UNKNOWN`: chưa thể kết luận theo hợp đồng, chẳng hạn kết quả đánh giá rủi ro cần thiết chưa sẵn sàng.

Đây là kết quả của **điều kiện**, chưa phải quyền được tạo tác động. Chỉ `PASS` ở root của policy action hợp lệ mới cho phép use case đi tiếp. `FAIL` và `UNKNOWN` đều dừng trước mutation, dù có thể được ánh xạ thành các lỗi vận hành khác nhau.

### 3.1. Bảng ghép cho hai rule

| A | B | ALL(A, B) | ANY(A, B) |
|---|---|---|---|
| PASS | PASS | PASS | PASS |
| PASS | FAIL | FAIL | PASS |
| PASS | UNKNOWN | UNKNOWN | PASS |
| FAIL | PASS | FAIL | PASS |
| FAIL | FAIL | FAIL | FAIL |
| FAIL | UNKNOWN | FAIL | UNKNOWN |
| UNKNOWN | PASS | UNKNOWN | PASS |
| UNKNOWN | FAIL | FAIL | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

| A | NOT(A) |
|---|---|
| PASS | FAIL |
| FAIL | PASS |
| UNKNOWN | UNKNOWN |

Trong nhóm ANY của những phương án **đủ và thay thế được cho nhau**, một nhánh PASS đủ để nhóm PASS dù nhánh khác UNKNOWN. Vì vậy, đặt kiểm tra rủi ro bắt buộc vào cùng ANY với supervisor là sai mô hình: supervisor PASS sẽ che UNKNOWN của rủi ro. Chuyển kiểm tra đó thành điều kiện ALL ở ngoài nhóm lựa chọn.

Fail closed không có nghĩa là bất kỳ UNKNOWN ở mọi nhánh không liên quan đều phải làm hỏng mọi quyết định. Nó đòi hỏi không tạo tác động khi chưa chứng minh đủ những điều kiện mà policy thật sự yêu cầu. Chính cấu trúc cây xác định điều gì là bắt buộc.

### 3.2. Danh sách rỗng và rule không áp dụng

Trong đại số boolean, phép AND trên tập rỗng có thể được định nghĩa là true. Với composer bảo mật của bài, **ALL rỗng và ANY rỗng đều là lỗi cấu hình**. Một lỗi load rule không được biến policy thành nhóm rỗng rồi trả PASS.

Không có policy cho action cũng dẫn tới từ chối trước tác động. Không mặc định `null`, rule không nhận diện hoặc rule bị bỏ qua thành PASS. Nếu cần trạng thái "không áp dụng", hãy định nghĩa riêng phạm vi và cách kết hợp; không dùng nó lẫn với FAIL hoặc UNKNOWN.

Trong thiết kế nhỏ, thường dễ review hơn nếu chọn đúng policy theo action trước rồi đánh giá một cây không rỗng, thay vì để từng rule tự biến mất trong lúc chạy.

### 3.3. Lỗi lập trình khác dữ kiện chưa xác định

Một adapter có thể ánh xạ trạng thái nghiệp vụ "chưa có kết quả rủi ro" thành UNKNOWN. Null bất ngờ, exception do bug hoặc cấu hình không hợp lệ không nên được bắt hàng loạt rồi đổi thành PASS. Chúng phải làm use case thất bại an toàn trước mutation và được ghi nhận đúng loại lỗi.

Đặc biệt, không bắt lỗi `isBlocked()` thành `false` rồi phủ định thành "không bị chặn". NOT phải giữ UNKNOWN là UNKNOWN; lỗi chưa được mô hình hóa phải thoát tới ranh giới xử lý lỗi thay vì cấp quyền.

## 4. Composer Java nhỏ với cây kết quả rõ ràng

Mã sau là tiện ích do ứng dụng định nghĩa, không phải API tiêu chuẩn của một rule engine. Nó hiện thực đúng bảng trên, giữ kết quả theo cấu trúc cây và đánh giá đầy đủ các nhánh con trên facts đã có trong bộ nhớ.

~~~java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public final class Rules {
    private Rules() {}

    public enum Verdict { PASS, FAIL, UNKNOWN }

    public record Evaluation(
            String ruleId,
            Verdict verdict,
            List<Evaluation> children) {
        public Evaluation {
            requireId(ruleId);
            Objects.requireNonNull(verdict, "verdict");
            children = List.copyOf(children);
        }
    }

    @FunctionalInterface
    public interface Rule<C> {
        Evaluation evaluate(C context);
    }

    public static <C> Rule<C> leaf(
            String id, Function<C, Verdict> evaluator) {
        requireId(id);
        Objects.requireNonNull(evaluator, "evaluator");
        return context -> new Evaluation(id,
                Objects.requireNonNull(evaluator.apply(
                        Objects.requireNonNull(context, "context")), "result"),
                List.of());
    }

    public static <C> Rule<C> allOf(String id, List<Rule<C>> children) {
        List<Rule<C>> snapshot = checkedChildren(id, children);
        return context -> {
            Objects.requireNonNull(context, "context");
            List<Evaluation> results = snapshot.stream()
                    .map(child -> child.evaluate(context)).toList();
            Verdict combined = results.stream()
                    .anyMatch(e -> e.verdict() == Verdict.FAIL)
                    ? Verdict.FAIL
                    : results.stream()
                            .anyMatch(e -> e.verdict() == Verdict.UNKNOWN)
                            ? Verdict.UNKNOWN : Verdict.PASS;
            return new Evaluation(id, combined, results);
        };
    }

    public static <C> Rule<C> anyOf(String id, List<Rule<C>> children) {
        List<Rule<C>> snapshot = checkedChildren(id, children);
        return context -> {
            Objects.requireNonNull(context, "context");
            List<Evaluation> results = snapshot.stream()
                    .map(child -> child.evaluate(context)).toList();
            Verdict combined = results.stream()
                    .anyMatch(e -> e.verdict() == Verdict.PASS)
                    ? Verdict.PASS
                    : results.stream()
                            .anyMatch(e -> e.verdict() == Verdict.UNKNOWN)
                            ? Verdict.UNKNOWN : Verdict.FAIL;
            return new Evaluation(id, combined, results);
        };
    }

    public static <C> Rule<C> not(String id, Rule<C> child) {
        requireId(id);
        Objects.requireNonNull(child, "child");
        return context -> {
            Evaluation result = child.evaluate(
                    Objects.requireNonNull(context, "context"));
            Verdict combined = switch (result.verdict()) {
                case PASS -> Verdict.FAIL;
                case FAIL -> Verdict.PASS;
                case UNKNOWN -> Verdict.UNKNOWN;
            };
            return new Evaluation(id, combined, List.of(result));
        };
    }

    private static <C> List<Rule<C>> checkedChildren(
            String id, List<Rule<C>> children) {
        requireId(id);
        List<Rule<C>> snapshot = List.copyOf(children);
        if (snapshot.isEmpty()) {
            throw new IllegalArgumentException("Rule group must not be empty");
        }
        return snapshot;
    }

    private static void requireId(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Rule ID is required");
        }
    }
}
~~~

`List.copyOf` tạo danh sách không sửa được và không chấp nhận phần tử null. Nó không tự làm các object mutable bên trong trở nên immutable; leaf vẫn phải giữ hợp đồng không sửa context và không bắt dữ liệu request vào trạng thái dùng chung. [Java SE 21: List](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#unmodifiable).

Java `Predicate.and/or` có short-circuit. Composer trong bài chủ động đánh giá đầy đủ để giữ cây kết quả nội bộ, nên không thể thay trực tiếp bằng các predicate boolean rồi giả định có cùng trace. [Java SE 21: Predicate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/function/Predicate.html).

Mỗi leaf phải thuần: không gọi HTTP, không truy vấn database, không ghi audit bắt buộc và không tạo tác động nghiệp vụ. Nếu rule cần dữ liệu ngoài, resolver tải dữ liệu trước theo quyền và hợp đồng nhất quán đã thiết kế. Nếu một leaf ném exception, composer không trả kết quả cho phép; caller phải dừng an toàn trước mutation.

Đây là skeleton để minh họa ngữ nghĩa. Nó chưa có loader cấu hình, kiểm tra ID trùng, giới hạn độ sâu, timeout resolver hay hệ thống quản trị policy. Những năng lực đó cần thêm khi có yêu cầu thực tế.

## 5. Xây facts cho đúng actor, đối tượng và lần quyết định

Một cây tường minh vẫn có thể trả kết quả sai nếu dùng facts do client giả mạo. Context phải được resolver phía server xây từ danh tính đã xác minh, request đúng scope, grant và dữ liệu liên quan có thẩm quyền.

| Nhóm dữ liệu | Nguồn và ràng buộc |
|---|---|
| Actor/person/tenant | Principal đã xác minh kết hợp mapping danh tính và membership; tenant được chọn phải được phép |
| Grant, supervisor và hạn mức | Grant/policy store hoặc claim được chấp nhận theo hợp đồng hiệu lực; không lấy role/hạn mức từ body |
| Phân công chi nhánh | Quan hệ của actor với chi nhánh của chính request đang xét, trong tenant tương ứng |
| Số tiền, currency, maker, state, version | Request được tải phía server; không lấy số tiền client gửi làm sự thật để duyệt |
| Expected version | Command chưa đáng tin, chỉ dùng đối chiếu với dữ liệu server |
| Rủi ro | Kết quả từ nguồn có thẩm quyền, gắn request/revision và thời hạn hiệu lực phù hợp |
| Thời điểm đánh giá | Clock phía server, lấy nhất quán cho một quyết định |

Một mô hình facts tối thiểu, đặt cùng package với các lớp ví dụ:

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record ApprovalFacts(
        ActorScope actor,
        RefundView refund,
        long expectedRowVersion,
        long reviewedContentVersion,
        Instant evaluatedAt,
        RiskState riskState) {
    public enum RiskState { CLEAR, BLOCKED, UNKNOWN }

    public ApprovalFacts {
        Objects.requireNonNull(actor, "actor");
        Objects.requireNonNull(refund, "refund");
        Objects.requireNonNull(evaluatedAt, "evaluatedAt");
        Objects.requireNonNull(riskState, "riskState");
        if (expectedRowVersion < 0 || reviewedContentVersion < 0) {
            throw new IllegalArgumentException("Invalid expected version");
        }
    }

    public record ActorScope(
            UUID tenantId,
            UUID personId,
            boolean activeMember,
            boolean approveGranted,
            boolean assignedToBranch,
            boolean supervisorInTenant,
            long limitMinor,
            String limitCurrency) {
        public ActorScope {
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(personId, "personId");
            Objects.requireNonNull(limitCurrency, "limitCurrency");
            if (limitMinor < 0) {
                throw new IllegalArgumentException("Invalid approval limit");
            }
        }
    }

    public record RefundView(
            UUID requestId,
            UUID tenantId,
            UUID makerPersonId,
            String state,
            long rowVersion,
            long contentVersion,
            long amountMinor,
            String currency,
            Instant approvalDeadline) {
        public RefundView {
            Objects.requireNonNull(requestId, "requestId");
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(makerPersonId, "makerPersonId");
            Objects.requireNonNull(state, "state");
            Objects.requireNonNull(currency, "currency");
            Objects.requireNonNull(approvalDeadline, "approvalDeadline");
            if (rowVersion < 0 || contentVersion < 0 || amountMinor <= 0) {
                throw new IllegalArgumentException("Invalid refund snapshot");
            }
        }
    }
}
~~~

`ActorScope` là snapshot cho **request đang xét**. `assignedToBranch` không phải cờ tái sử dụng cho mọi request của actor. Resolver phải ràng buộc nó với đúng request/branch/tenant, đồng thời xác minh `supervisorInTenant` trong scope đó.

Các boolean trong mẫu biểu diễn kết quả đã được giải quyết. Nếu không tải được membership hoặc grant thì resolver phải dừng hoặc trả lỗi rõ ràng; không điền giá trị mặc định tùy tiện. Riêng trạng thái rủi ro chưa xác định được mô hình hóa bằng enum để minh họa UNKNOWN. Record không tự xác minh dữ liệu và không nên được bind trực tiếp từ HTTP body.

Tiền là số nguyên đơn vị nhỏ nhất theo hợp đồng currency của ứng dụng. So sánh chỉ hợp lệ khi currency khớp. Mẫu không thực hiện quy đổi và không mặc định mọi tiền tệ có hai chữ số thập phân.

## 6. Viết policy tổng theo đúng cây đã thiết kế

Lớp sau dùng `Rules` và `ApprovalFacts` ở trên. Các ID ngắn là mã nội bộ cho cây quyết định, không phải nội dung được gửi nguyên vẹn tới client.

~~~java
import java.util.List;
import java.util.function.Predicate;

public final class RefundApprovalPolicy {
    private RefundApprovalPolicy() {}

    public static final String ID = "refund.approve.v1";

    private static Rules.Rule<ApprovalFacts> check(
            String id, Predicate<ApprovalFacts> predicate) {
        return Rules.leaf(id, facts -> predicate.test(facts)
                ? Rules.Verdict.PASS : Rules.Verdict.FAIL);
    }

    private static final Rules.Rule<ApprovalFacts> ROOT = Rules.allOf(ID,
            List.of(
                Rules.allOf("scope", List.of(
                    check("tenantMatches", f -> f.actor().tenantId()
                            .equals(f.refund().tenantId())),
                    check("activeMembership", f -> f.actor().activeMember()),
                    check("approvePermission", f -> f.actor().approveGranted())
                )),
                check("checkerDifferentFromMaker", f -> !f.actor().personId()
                        .equals(f.refund().makerPersonId())),
                Rules.<ApprovalFacts>leaf("clearForApproval", f ->
                        switch (f.riskState()) {
                            case CLEAR -> Rules.Verdict.PASS;
                            case BLOCKED -> Rules.Verdict.FAIL;
                            case UNKNOWN -> Rules.Verdict.UNKNOWN;
                        }),
                Rules.anyOf("assignment", List.of(
                    check("assignedToBranch", f -> f.actor().assignedToBranch()),
                    check("supervisorInTenant", f -> f.actor().supervisorInTenant())
                )),
                check("withinApprovalLimit", f -> f.actor().limitCurrency()
                        .equals(f.refund().currency())
                        && f.refund().amountMinor() <= f.actor().limitMinor()),
                Rules.allOf("transition", List.of(
                    check("pendingApproval", f ->
                            "PENDING_APPROVAL".equals(f.refund().state())),
                    check("rowVersionMatches", f ->
                            f.refund().rowVersion() == f.expectedRowVersion()),
                    check("reviewedContentMatches", f ->
                            f.refund().contentVersion() == f.reviewedContentVersion()),
                    check("beforeApprovalDeadline", f ->
                            f.evaluatedAt().isBefore(f.refund().approvalDeadline()))
                ))
            ));

    public static Rules.Evaluation evaluate(ApprovalFacts facts) {
        return ROOT.evaluate(facts);
    }
}
~~~

### 6.1. Những điều cấu trúc này làm rõ

Supervisor chỉ nằm trong nhóm `assignment`. Root vẫn yêu cầu tenant, membership, grant, checker độc lập, rủi ro, hạn mức và transition. Nếu supervisor là maker, `checkerDifferentFromMaker` FAIL khiến root FAIL dù assignment PASS.

Nếu rủi ro UNKNOWN và các nhóm khác đều PASS, root UNKNOWN. Caller không được diễn giải UNKNOWN là "không phát hiện vấn đề". Nếu một điều kiện bắt buộc khác đã FAIL thì root FAIL theo bảng, nhưng cây kết quả vẫn giữ trạng thái UNKNOWN của nhánh rủi ro cho chẩn đoán nội bộ.

Deadline là biên loại trừ: tại đúng `approvalDeadline`, rule không đạt. State không nhận diện không thỏa `PENDING_APPROVAL`. Version đúng chỉ chứng minh điều kiện đối chiếu dữ liệu, không cấp quyền cho caller.

### 6.2. Nơi nào được thay đổi policy?

Trong mẫu, root được ghép ở một nơi và không nhận thêm nhánh từ payload. Muốn thêm ngoại lệ phải thay đúng cây, giữ các điều kiện bắt buộc và cập nhật version/tests thích hợp.

Nếu có luồng khẩn cấp thực sự cần vượt một quy tắc, hãy mô hình hóa action/transition đó với quyền, thời hạn, lý do và bằng chứng riêng. Một `or(isAdmin)` ở cuối policy bình thường không mô tả đủ phạm vi ngoại lệ.

Một nhánh được thêm bằng OR có xu hướng mở rộng tập trường hợp cho phép; một điều kiện bắt buộc thêm bằng AND có xu hướng thu hẹp tập đó. Khi review thay đổi, cần xác định rõ những trường hợp nào mới được phép hoặc mới bị từ chối, thay vì chỉ xem rule mới có chạy hay không.

## 7. Cưỡng chế quyết định trước mutation và giữ tính nhất quán

### 7.1. Đường gọi use case

Pseudocode sau biểu diễn một lần duyệt mới. `transactions.required`, resolver, aggregate, repository và exception là các hợp đồng ứng dụng tự hiện thực, không phải một ứng dụng Spring hoàn chỉnh:

~~~java
public ApprovalReceipt approve(ApproveCommand command) {
    return transactions.required(() -> {
        VerifiedCaller caller = identity.requireCurrentCaller();
        RefundRequest request = refunds
                .lockByTenantAndId(caller.tenantId(), command.requestId())
                .orElseThrow(RequestNotVisibleException::new);

        ApprovalFacts facts = factsResolver.resolve(
                caller, request.toSnapshot(), command, clock.instant());
        Rules.Evaluation result = RefundApprovalPolicy.evaluate(facts);

        if (result.verdict() == Rules.Verdict.UNKNOWN) {
            throw new ApprovalDecisionUnavailableException();
        }
        if (result.verdict() != Rules.Verdict.PASS) {
            throw new ApprovalRejectedException();
        }

        ApprovalReceipt receipt = request.approve(
                caller.personId(),
                facts.refund().contentVersion(),
                facts.evaluatedAt());

        refunds.save(request);
        evidence.append(receipt, result);
        return receipt;
    });
}
~~~

Hợp đồng của resolver phải bảo đảm actor trong facts đúng caller, resource đúng aggregate đang ghi, expected version đúng command và dữ liệu quyền được xác minh. Không lấy một `ApprovalFacts` do client gửi rồi dùng trực tiếp. `request.approve` tiếp tục bảo vệ transition và bất biến miền mà aggregate sở hữu; không cung cấp setter trạng thái công khai để mọi đường khác bỏ qua điều kiện.

`transactions.required` phải chạy phần thân trong transaction với rollback khi lỗi theo thiết kế. Request, approval và evidence thành công của mẫu dùng cùng tài nguyên giao dịch. Nếu evidence là HTTP call tới nơi khác, transaction database không tự làm hai nơi commit nguyên tử.

Controller, batch và consumer phải đi qua use case này hoặc ranh giới tương đương có cùng guard. Việc UI vô hiệu hóa nút chỉ hỗ trợ trải nghiệm; caller có thể tự gửi command. Quyền route tổng quát cũng chưa thay thế quyền trên đúng request.

OWASP mô tả việc bảo vệ thứ tự các bước, dữ liệu giao dịch và kiểm tra gắn với lúc thực thi để tránh bỏ bước hoặc thay dữ liệu sau khi chấp thuận. Trong ví dụ, approval phải gắn với revision được duyệt và mọi bước thực thi sau đó phải kiểm tra bằng chứng thích hợp. [OWASP: Transaction Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html#25-application-should-control-which-transaction-state-transitions-are-allowed).

### 7.2. Quyết định đúng với snapshot cũ vẫn có thể gây cập nhật sai

~~~text
T1 đọc request 100 và nhận PASS.
T2 sửa số tiền thành 1.000 hoặc đổi người nhận, rồi commit.
T1 dùng PASS cũ để duyệt request hiện tại mà không ràng buộc version.
~~~

Cây rule không tự ngăn được khoảng hở này. Cần khóa/version/conditional write phù hợp để ràng buộc quyết định với chính dữ liệu được ghi.

Với PostgreSQL, row lock `FOR UPDATE` ngăn các thao tác ghi/khóa xung đột trên hàng đó cho đến hết transaction. Cần xử lý các lỗi cạnh tranh theo isolation thật; khóa một hàng không tự khóa mọi dữ liệu tham chiếu. [PostgreSQL 18: Row-Level Locks](https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-ROWS).

Nếu dùng optimistic locking hoặc conditional write, phải kiểm tra version/state ở write và kiểm tra kết quả cập nhật. Nếu write không còn khớp, không commit approval thành công; cần rollback phần ghi liên quan và quyết định lại trên facts mới theo hợp đồng retry.

Mọi sửa đổi trọng yếu như số tiền, currency, người nhận phải tăng content version hoặc tạo revision mới. Approval lưu đúng request/tenant/content version và snapshot tương ứng. Chỉ tăng version cho một số đường sửa sẽ để lại đường bypass dù rule `reviewedContentMatches` nhìn đúng.

### 7.3. Những dữ liệu khác cũng có thể thay đổi

| Dữ liệu | Điều cần bảo vệ ngoài cây rule |
|---|---|
| Membership/grant/phân công | Xác định thời điểm quyền có hiệu lực và phối hợp thu hồi với quyết định/cập nhật khi cần |
| Hạn mức tổng dùng chung | Reservation, cập nhật có điều kiện hoặc cơ chế đồng thời cho tài nguyên tổng; không chỉ khóa từng request |
| Kết quả rủi ro | Ràng buộc request/revision, nguồn và thời hạn hiệu lực; kết quả cũ không được dùng tùy ý |
| Deadline | Quyết định thời hạn xét tại đánh giá, commit hay thực thi; một `evaluatedAt` không tự bảo đảm mọi mốc đều còn hạn |
| Policy/config version | Chọn snapshot policy nhất quán cho quyết định và ghi bằng chứng version đã dùng |

Nếu cần dữ liệu từ dịch vụ ngoài, tránh để các leaf tự gọi remote khi đang giữ lock. Có thể tải trước kết quả gắn revision rồi kiểm tra lại binding/version/expiry trong transaction, hoặc chọn thiết kế khác có hợp đồng nhất quán rõ ràng. Đưa một kết quả cũ vào record không làm nó tự trở thành dữ liệu hiện thời.

Duyệt và thực thi hoàn tiền là các action khác nhau. Một event `RefundApproved` không tự cho phép consumer bỏ mọi guard của bước thực thi hoặc đổi người nhận. Nếu cần outbox, ghi ý định cùng transaction; tác động provider vẫn cần cơ chế thực thi, chống trùng và đối soát riêng.

## 8. Tách kết quả policy, nghĩa vụ thực hiện và giải thích

### 8.1. Trace không phải response public

Một cây kết quả có thể giúp người vận hành thấy root FAIL vì `checkerDifferentFromMaker`, trong khi assignment PASS nhờ supervisor. Nó cũng giúp phân biệt root UNKNOWN do rủi ro chưa có kết quả với một lần từ chối vì thiếu quyền.

Không trả cây này nguyên vẹn cho caller. Ngay cả khi trace chỉ có ID và verdict, nó vẫn có thể tiết lộ policy hoặc trạng thái của một request ngoài scope. Chọn thông điệp public theo quyền được biết của caller, còn thông tin chi tiết nằm trong kênh nội bộ có phân quyền.

Không gom mọi leaf FAIL thành danh sách "lý do từ chối" mà bỏ cấu trúc. Trong `ANY(assignedToBranch, supervisorInTenant)`, nhánh phân công FAIL không phải lỗi tổng nếu supervisor PASS. Ngược lại, một leaf bắt buộc UNKNOWN cần được giữ nguyên ý nghĩa dù các leaf khác đã PASS.

Với composer đánh giá đầy đủ, mọi leaf được gọi trên facts đã có, trừ khi một lỗi khiến evaluation dừng. Nếu chuyển sang short-circuit để tối ưu, trace phải phân biệt node chưa đánh giá với node đã FAIL/UNKNOWN. Không ghi giả rằng một kiểm tra đã chạy.

### 8.2. Nghĩa vụ bắt buộc cần được cưỡng chế

Một policy có thể yêu cầu phê duyệt thứ hai, xác nhận gần đây hoặc lưu bằng chứng trước khi hoàn tất. Không coi việc trả PASS kèm chuỗi "cần thêm approval" là đã bảo vệ tác động nếu caller vẫn tiếp tục ghi trạng thái thành công.

Có thể mô hình hóa bằng điều kiện bắt buộc trên bằng chứng đã xác minh, hoặc một bước workflow riêng có guard. Nếu obligation là lưu evidence thành công trong cùng transaction, khi ghi evidence thất bại phải xử lý theo hợp đồng rollback của luồng đó.

Một điều kiện thuần không nên tự tạo reservation, gửi notification hay ghi approval. Khi rule B phụ thuộc việc rule A vừa tạo dữ liệu, đó đã là orchestration có tác động và cần workflow/transaction riêng. Đừng giấu thứ tự các tác động đó trong ALL hoặc ANY.

### 8.3. Audit đúng với kết quả cuối

Evidence thành công nên gắn action, actor thực, tenant, request/revision, thời điểm, policy version và những version nguồn quan trọng cần truy vết. Trace bổ sung cách policy đã được đánh giá; nó không thay thế snapshot hoặc binding của approval với nội dung trọng yếu.

Sự kiện từ chối cần cơ chế giữ lại sau rollback nếu hệ thống yêu cầu điều tra. Không trông chờ bản ghi cùng transaction bị rollback vẫn còn tồn tại. Không log token, secret hoặc toàn bộ payload nhạy cảm chỉ để giải thích quyết định.

Hợp đồng lỗi cần phân biệt thiếu quyền, state/version conflict, dữ kiện chưa sẵn sàng và lỗi hạ tầng ở mức phù hợp. Không đổi tất cả thành HTTP 200, cũng không che mọi lỗi bằng một mã 403 duy nhất. Một lần bị từ chối có thể tạo security event theo thiết kế nhưng không được tạo approval thành công hoặc tác động provider ngoài ý muốn.

## 9. Retry, policy động và thay đổi phiên bản

### 9.1. Không tái sử dụng PASS như một quyền vĩnh viễn

Không cache quyết định chỉ theo request ID. Caller khác, tenant khác, revision mới, grant mới hoặc deadline đã qua có thể có kết quả khác. Nếu cần cache, xác định đầy đủ binding và giới hạn độ cũ được chấp nhận; vẫn bảo vệ các guard nhạy cảm tại cập nhật.

Với một command đã hoàn tất, retry có thể muốn trả receipt cũ. Policy cho **tạo lần duyệt mới** yêu cầu trạng thái chờ, nên không nên dùng nguyên nó để quyết định **đọc lại receipt của lệnh đã hoàn tất**. Nhánh replay có kiểm tra authentication, tenant, action/key scope, fingerprint và quyền truy cập kết quả riêng.

Một rule `notProcessedYet` không claim idempotency key. Hai request đồng thời đều có thể đọc thấy chưa xử lý. Ledger cần unique constraint/cơ chế claim và transaction phù hợp để ràng buộc key, fingerprint, mutation và kết quả. Cùng key nhưng đổi command phải bị xử lý theo hợp đồng xung đột; key từ actor khác không được mở quyền đọc receipt.

Nếu retry sau conflict thực hiện lại quyết định, phải tải facts/version cần thiết và áp dụng hợp đồng policy đã chọn. Nếu hệ thống cho phép tiếp tục theo một quyết định đã chấp nhận trước đó, bằng chứng và giới hạn hiệu lực của quyết định đó phải rõ ràng. Không để retry tự chọn một chính sách khác lần chạy đầu mà không có thiết kế.

### 9.2. Cấu hình động không được xóa ranh giới bắt buộc

Một bộ cấu hình chỉ cho đổi ngưỡng tiền hoặc chi nhánh không đồng nghĩa cho quyền sửa toàn bộ root. Có thể tách:

~~~text
root = ALL(
  mandatoryScopeAndIdentity,
  configuredEligibility,
  mandatoryWorkflowAndVersion
)
~~~

Loader cần từ chối rule/toán tử không nhận diện, nhóm rỗng, tham chiếu vòng, ID trùng gây mơ hồ và cấu hình thiếu thành phần bắt buộc. Giới hạn độ sâu, số node và chi phí resolve facts. Client không được gửi biểu thức tùy ý để thực thi như mã đặc quyền.

Skeleton `Rules` trong bài không tự kiểm tra tất cả các điều kiện cấu hình đó. Nếu dùng cấu hình ngoài, cần parser/compiler có hợp đồng và validation riêng trước khi kích hoạt cây.

Một policy đang dùng nên được chọn theo snapshot version nhất quán. Không ghép nửa cây từ version cũ với nửa cây từ version mới trong cùng quyết định. Kiểm soát ai có thể phát hành policy và ghi nhận thay đổi có thể mở quyền; việc rollback policy cũng là một thay đổi quyền cần đánh giá.

### 9.3. Review theo tập trường hợp được phép

Khi thêm nhánh hoặc đổi toán tử, hãy mô tả tác động cụ thể:

| Thay đổi | Điều cần xem xét |
|---|---|
| Thêm một nhánh vào ANY | Nhóm có thêm cách đạt; nhánh mới có được thay thế mọi nhánh cũ không? |
| Xóa một điều kiện khỏi ALL | Có bỏ mất bất biến bắt buộc trên mọi đường cho phép không? |
| Di chuyển một rule từ root vào nhánh supervisor | Có khiến checker hoặc supervisor đi vòng kiểm tra đó không? |
| Đổi UNKNOWN thành FAIL ở leaf | Có bị NOT biến thành PASS hoặc làm sai chẩn đoán không? |
| Tối ưu thứ tự đánh giá | Chỉ được giữ nguyên quyết định khi facts và rule thuần; trace/chi phí có thay đổi gì? |
| Đổi policy version nhưng dùng lại receipt/cache cũ | Binding của quyết định cũ có còn được chấp nhận theo workflow không? |

Với điều kiện thuần và cùng facts, thứ tự các con của ALL/ANY không đổi verdict theo bảng đã định nghĩa. Điều đó không tự đúng với vòng lặp first-match hoặc rule có side effect.

## 10. Kiểm thử cả phép ghép và ranh giới nghiệp vụ

### 10.1. Kiểm tra ngữ nghĩa composer

Ví dụ JUnit Jupiter sau cần cả hỗ trợ test thông thường và parameterized tests. Các lớp đặt cùng package với `Rules`. Mục tiêu là kiểm tra bảng kết hợp, UNKNOWN qua NOT và cấu hình rỗng, không phụ thuộc database.

~~~java
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RulesCompositionTest {
    private Rules.Rule<String> constant(String id, Rules.Verdict value) {
        return Rules.leaf(id, context -> value);
    }

    @ParameterizedTest
    @CsvSource({
        "PASS, PASS, PASS, PASS",
        "PASS, FAIL, FAIL, PASS",
        "PASS, UNKNOWN, UNKNOWN, PASS",
        "FAIL, PASS, FAIL, PASS",
        "FAIL, FAIL, FAIL, FAIL",
        "FAIL, UNKNOWN, FAIL, UNKNOWN",
        "UNKNOWN, PASS, UNKNOWN, PASS",
        "UNKNOWN, FAIL, FAIL, UNKNOWN",
        "UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN"
    })
    void combinesAccordingToContract(
            Rules.Verdict a, Rules.Verdict b,
            Rules.Verdict expectedAll, Rules.Verdict expectedAny) {
        var children = List.of(constant("a", a), constant("b", b));
        assertEquals(expectedAll,
                Rules.allOf("all", children).evaluate("facts").verdict());
        assertEquals(expectedAny,
                Rules.anyOf("any", children).evaluate("facts").verdict());
    }

    @Test
    void negatingUnknownDoesNotGrantPermission() {
        var rule = Rules.not("notBlocked",
                constant("blocked", Rules.Verdict.UNKNOWN));
        assertEquals(Rules.Verdict.UNKNOWN,
                rule.evaluate("facts").verdict());
    }

    @Test
    void emptyGroupsAreConfigurationErrors() {
        assertThrows(IllegalArgumentException.class,
                () -> Rules.<String>allOf("emptyAll", List.of()));
        assertThrows(IllegalArgumentException.class,
                () -> Rules.<String>anyOf("emptyAny", List.of()));
    }
}
~~~

### 10.2. Kiểm tra cấu trúc policy bằng ca nghiệp vụ

Một composer đúng vẫn có thể nhận một cây sai. Bộ test sau dùng các kiểu ở phần 5–6, kiểm tra ngoại lệ supervisor trong chính policy tổng. UUID cố định là dữ liệu fixture.

~~~java
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RefundApprovalPolicyTest {
    private static final UUID TENANT_A = new UUID(0, 1);
    private static final UUID TENANT_B = new UUID(0, 2);
    private static final UUID MAKER = new UUID(0, 3);
    private static final UUID CHECKER = new UUID(0, 4);
    private static final UUID REQUEST = new UUID(0, 5);
    private static final Instant NOW = Instant.parse("2026-11-23T03:00:00Z");

    private Rules.Verdict decide(UUID actorTenant, UUID person,
            boolean assigned, boolean supervisor, ApprovalFacts.RiskState risk) {
        var actor = new ApprovalFacts.ActorScope(
                actorTenant, person, true, true,
                assigned, supervisor, 10_000, "VND");
        var refund = new ApprovalFacts.RefundView(
                REQUEST, TENANT_A, MAKER, "PENDING_APPROVAL",
                4, 7, 5_000, "VND", NOW.plusSeconds(60));
        var facts = new ApprovalFacts(actor, refund, 4, 7, NOW, risk);
        return RefundApprovalPolicy.evaluate(facts).verdict();
    }

    @Test
    void assignmentAndSupervisorAreAlternativesWithinMandatoryScope() {
        assertEquals(Rules.Verdict.PASS, decide(TENANT_A, CHECKER,
                true, false, ApprovalFacts.RiskState.CLEAR));
        assertEquals(Rules.Verdict.PASS, decide(TENANT_A, CHECKER,
                false, true, ApprovalFacts.RiskState.CLEAR));
        assertEquals(Rules.Verdict.FAIL, decide(TENANT_A, CHECKER,
                false, false, ApprovalFacts.RiskState.CLEAR));
    }

    @Test
    void supervisorCannotBypassTenantOrMakerSeparation() {
        assertEquals(Rules.Verdict.FAIL, decide(TENANT_B, CHECKER,
                false, true, ApprovalFacts.RiskState.CLEAR));
        assertEquals(Rules.Verdict.FAIL, decide(TENANT_A, MAKER,
                false, true, ApprovalFacts.RiskState.CLEAR));
    }

    @Test
    void supervisorCannotBypassRiskResult() {
        assertEquals(Rules.Verdict.UNKNOWN, decide(TENANT_A, CHECKER,
                false, true, ApprovalFacts.RiskState.UNKNOWN));
        assertEquals(Rules.Verdict.FAIL, decide(TENANT_A, CHECKER,
                false, true, ApprovalFacts.RiskState.BLOCKED));
    }
}
~~~

### 10.3. Ma trận bổ sung trước khi dùng trong ứng dụng

| Tình huống | Điều cần chứng minh |
|---|---|
| Caller có role nhưng membership/grant không còn hiệu lực | Không đi vòng bằng supervisor hoặc dữ liệu client |
| Hai account thuộc cùng person identity | Không vượt checker độc lập |
| Số tiền bằng hạn mức và vượt một đơn vị nhỏ nhất | Biên so sánh đúng; khác currency không được coi như cùng đơn vị |
| Đúng deadline hoặc sau deadline | Không đạt rule thời gian của mẫu |
| Version state hoặc content cũ | Không duyệt dữ liệu mới bằng quyết định cũ |
| Đổi số tiền/người nhận qua endpoint khác | Content version/binding thay đổi theo hợp đồng, approval cũ không tự còn hiệu lực |
| Không có policy, cấu hình rỗng, leaf lỗi hoặc trả null | Không có approval/tác động ngoài được tạo |
| Đổi thứ tự các leaf thuần | Verdict giữ nguyên; trace ghi đúng thứ tự thật |
| Hai transaction duyệt cùng revision | Số approval và transition không vượt bất biến đã thiết kế |
| Hai request tiêu phần hạn mức tổng cuối | Hạn mức tổng không bị vượt vì race |
| Retry cùng key nhưng đổi fingerprint | Không tạo tác động mới trái hợp đồng |
| Replay receipt từ actor/tenant khác | Không lộ kết quả riêng tư |
| Gọi bằng batch/consumer hoặc API quản trị | Đi qua ranh giới cưỡng chế tương ứng |
| Save/evidence thất bại | Không commit approval hoặc trạng thái thành công một phần trong mẫu cùng database |

Khi kiểm tra concurrency, cần tạo hai transaction có lịch xen kẽ được điều phối. Hai lần gọi tuần tự không chứng minh race đã được chặn. Khi kiểm tra rollback/commit, đọc lại bằng transaction hoặc connection mới phù hợp, tránh kết luận từ entity còn trong persistence context của test.

Mỗi ca từ chối nên quan sát state/version, approval, outbox và provider liên quan. Việc nhận exception đúng loại chưa chứng minh hệ thống không tạo tác động trước đó.

Các đoạn Java trong bài là ví dụ phục vụ học tập; chúng chưa được biên dịch hoặc chạy trong một dự án ứng dụng cụ thể ở bước biên soạn này.

## 11. Bài thực hành: bổ sung phê duyệt thứ hai mà không mở đường bypass

Yêu cầu mới: request vượt một ngưỡng nghiệp vụ cần hai checker độc lập. Supervisor vẫn chỉ thay thế điều kiện phân công chi nhánh, không được miễn tenant, rủi ro, thẩm quyền hay yêu cầu hai người.

1. Vẽ cây policy cho action thêm một approval và policy cho action thực thi hoàn tiền. Nêu rõ tại bước nào phải đủ số approval, tránh yêu cầu đủ hai approval trước khi được tạo approval đầu tiên.
2. Xác định dữ liệu có thẩm quyền: revision, danh tính từng checker, phân công, hạn mức và ngưỡng cần hai người. Nêu cách vô hiệu hóa bằng chứng khi dữ liệu trọng yếu đổi.
3. Viết các nhánh bắt buộc và ngoại lệ. Giải thích vì sao thêm `ANY(supervisor, secondApprovalExists)` ở root là sai yêu cầu.
4. Chọn cơ chế đồng thời để hai request trùng không tạo hai approval từ cùng người hoặc làm bước thực thi diễn ra hai lần.
5. Bổ sung ca maker có role supervisor, hai account cùng person identity, sửa người nhận giữa hai lần duyệt, rủi ro UNKNOWN và retry sau khi đã ghi approval.
6. Thiết kế trace/evidence nội bộ, response public và quyền đọc receipt khi replay. Chỉ ra những dữ liệu không nên đưa vào log.

Một thiết kế hoàn chỉnh cần mô tả được cây rule, nguồn facts, ngữ nghĩa lỗi, thời điểm quyết định có hiệu lực và nơi giữ bất biến khi ghi. Khi mỗi nhánh cho phép đều chứng minh đủ các điều kiện bắt buộc, việc thêm ngoại lệ hoặc thay đổi workflow mới có cơ sở để review và kiểm thử.
