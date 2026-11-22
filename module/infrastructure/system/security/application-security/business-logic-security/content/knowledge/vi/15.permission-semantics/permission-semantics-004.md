# Giao quyền truy cập (Permission intersection)

Một hành động nghiệp vụ thường bị giới hạn bởi nhiều lớp cùng lúc. Người dùng có thể được tạo yêu cầu hoàn tiền, nhưng token chỉ cho phép đọc; dịch vụ gọi thay có thể hoạt động trong một tenant, nhưng đơn hàng thuộc tenant khác. Một lớp cho phép không đủ để vượt qua những ranh giới còn lại.

**Permission intersection** là cách xác định tập hành động còn được phép sau khi áp dụng đồng thời các giới hạn bắt buộc. Hành động chỉ được thực hiện khi nó nằm trong mọi tập quyền có liên quan theo hợp đồng chính sách.

Bài học thuộc chương **Permission Semantics** trong bảo mật logic nghiệp vụ. Trọng tâm là ngữ nghĩa kết hợp quyền: lớp nào lấy giao, lớp nào lấy hợp, cách giữ phạm vi đối tượng và điều kiện đi kèm, cùng cách thực thi quyết định mà không bỏ qua state machine, transaction hay idempotency.

## 1. Ý nghĩa của phép giao quyền

Với hai tập quyền:

```text
Quyền của người dùng:
    {REFUND_VIEW, REFUND_REQUEST_CREATE}

Phạm vi action của token:
    {REFUND_VIEW}

Giao:
    {REFUND_VIEW}
```

Người dùng không thể tạo yêu cầu hoàn tiền bằng token này, dù tài khoản của họ có quyền đó trong một phiên khác.

Trong mô hình đơn giản:

```text
EffectivePermissions = UserPermissions ∩ TokenBoundary
```

Khi có thêm giới hạn:

```text
Effective =
    UserGrants
    ∩ TokenBoundary
    ∩ ServiceBoundary
    ∩ TenantBoundary
    ∩ ResourceBoundary
    ∩ ContextBoundary
```

Mỗi tập phải có ý nghĩa rõ ràng. Một lớp có thể là khả năng của người dùng; lớp khác là trần quyền của token, dịch vụ hoặc phiên thực hiện. Không xem chúng như các nguồn cấp quyền độc lập có thể thay thế nhau.

### 1.1. Quyền không chỉ là tên action

Một quyền thực tế có thể bao gồm:

```text
tenant + action + resource + điều kiện đầu vào + ngữ cảnh
```

Ví dụ:

```text
Được tạo yêu cầu hoàn tiền
cho đơn hàng của chi nhánh HCM trong tenant A,
với số tiền không vượt hạn mức,
khi người gọi và phiên làm việc đáp ứng điều kiện.
```

Nếu chỉ giữ tên `REFUND_REQUEST_CREATE`, hệ thống có thể làm mất giới hạn tenant, chi nhánh hoặc số tiền.

Có thể coi mỗi phần tử của không gian quyền là một thao tác đầy đủ:

```text
x = (subject, tenant, action, resource, input, context)
```

Phép giao trả lời liệu chính thao tác x đó có nằm trong mọi ranh giới bắt buộc hay không. Đây thường là cách diễn đạt chính xác hơn việc giao vài danh sách chuỗi action.

### 1.2. Quyết định quyền và tính hợp lệ nghiệp vụ

Ngay cả khi x nằm trong tập quyền hiệu lực, thao tác vẫn cần đáp ứng các bất biến nghiệp vụ:

- Đơn hàng đang ở trạng thái cho phép yêu cầu hoàn tiền.
- Số tiền yêu cầu hợp lệ và không vượt số còn có thể hoàn.
- Nội dung quan trọng chưa bị thay đổi trái quy trình.
- Các phê duyệt bắt buộc đã có hoặc sẽ được thực hiện ở đúng bước.
- Cạnh tranh và retry không làm tạo trùng kết quả.

Có quyền yêu cầu hoàn tiền không tự tạo quyền phê duyệt hoặc thực hiện chi trả. Tên action phải phản ánh đúng bước nghiệp vụ.

## 2. Phân biệt hợp các grant với giao các ranh giới

Sai lầm thường gặp là dùng một phép kết hợp duy nhất cho mọi nguồn quyền.

### 2.1. Các grant thay thế trong cùng một lớp có thể lấy hợp

Giả sử người dùng được đọc hồ sơ vì là chủ sở hữu **hoặc** vì được phân công xử lý:

```text
UserGrants =
    OwnerGrant
    ∪ AssignmentGrant
    ∪ ExplicitShareGrant
```

Nếu chính sách định nghĩa ba đường cấp quyền này là lựa chọn thay thế, người dùng chỉ cần có một grant phù hợp.

Tương tự, nhiều vai trò thường có thể đóng góp các grant bổ sung. Không nên tự động lấy giao mọi role rồi yêu cầu người dùng phải được từng role riêng lẻ cho phép cùng một hành động.

Một role không cấp quyền cho action không nhất thiết mang nghĩa phủ quyết mọi grant khác. Cần phân biệt “không có grant phù hợp” với một quyết định cấm tường minh.

### 2.2. Các ranh giới bắt buộc lấy giao

Sau khi tính tập grant người dùng, token và dịch vụ có thể tiếp tục giới hạn:

```text
Effective =
    (OwnerGrant ∪ AssignmentGrant ∪ ExplicitShareGrant)
    ∩ TokenBoundary
    ∩ ServiceBoundary
    ∩ TenantBoundary
    ∩ ResourceBoundary
```

Nếu một dịch vụ chỉ được đọc, grant ghi của người dùng không mở rộng khả năng dịch vụ. Nếu token chỉ áp dụng tenant A, quyền người dùng tại tenant B không làm token đó hợp lệ cho B.

### 2.3. Không có một quy tắc kết hợp mặc định cho mọi policy

Một hệ thống có thể định nghĩa luật cấm tường minh, ưu tiên hoặc thuật toán kết hợp khác. Chúng phải được ghi thành hợp đồng.

Trong bài này, mô hình minh họa quy định:

1. Các grant thay thế được hợp trong lớp cấp quyền người dùng.
2. Mọi ranh giới bắt buộc phải cho phép thao tác đang xét.
3. Luật cấm tường minh trong phạm vi áp dụng được xử lý như một veto theo chính sách đã chọn.
4. Thiếu bằng chứng cho phép tại một ranh giới bắt buộc không tạo ra quyền.

Không suy ra rằng mọi policy engine hay mọi hệ thống IAM đều dùng đúng mô hình này. Điều cần bảo vệ là ngữ nghĩa mà ứng dụng đã cam kết.

## 3. Giữ nguyên mối liên hệ giữa action, đối tượng và điều kiện

Giả sử người dùng có hai grant:

| Grant | Action | Phạm vi |
|---|---|---|
| G1 | `REFUND_REQUEST_CREATE` | Đơn chi nhánh HCM |
| G2 | `REFUND_VIEW` | Đơn chi nhánh HN |

Nếu tách ra:

```text
actions   = {REFUND_REQUEST_CREATE, REFUND_VIEW}
resources = {đơn HCM, đơn HN}
```

rồi coi mọi cặp action-resource đều hợp lệ, hệ thống vô tình cho phép tạo yêu cầu hoàn tiền với đơn HN.

Grant phải giữ liên kết:

```text
G1 = {(REFUND_REQUEST_CREATE, đơn thuộc HCM, điều kiện của G1)}
G2 = {(REFUND_VIEW, đơn thuộc HN, điều kiện của G2)}
```

Khi đánh giá, lấy đúng resource và input hiện tại để tìm grant phù hợp. Không làm mất các predicate khi chuẩn hóa hoặc cache quyền.

### 3.1. Ví dụ giao các ranh giới theo cùng một thao tác

Xét thao tác:

```text
Người dùng U tạo yêu cầu hoàn tiền
cho đơn O thuộc tenant A, chi nhánh HCM,
số tiền 400.000 VND.
```

| Ranh giới | Điều kiện áp dụng | Kết quả |
|---|---|---|
| Grant người dùng | Được tạo yêu cầu cho HCM, tối đa 1.000.000 VND | Cho phép |
| Token | Đúng action, tenant A, tối đa 500.000 VND | Cho phép |
| Dịch vụ | Được xử lý action này, tối đa 700.000 VND | Cho phép |
| Tài nguyên | O thuộc tenant A và phạm vi chi nhánh được cấp | Cho phép |
| Ngữ cảnh | Thành viên và phiên làm việc đáp ứng chính sách | Cho phép |

Trên cùng điều kiện, yêu cầu 600.000 VND bị token chặn dù người dùng và dịch vụ có hạn mức cao hơn.

### 3.2. Khi nào được lấy min của hạn mức?

Nếu các lớp đều giới hạn cùng action, cùng loại số tiền, cùng tiền tệ và cùng ngữ cảnh:

```text
EffectiveLimit = min(1.000.000, 500.000, 700.000)
               = 500.000 VND
```

Không lấy min một cách máy móc giữa:

- Hạn mức mỗi giao dịch và tổng hạn mức trong ngày.
- Hai tiền tệ chưa có quy tắc quy đổi.
- Grant áp dụng chi nhánh khác nhau.
- Giới hạn tạo đề nghị và giới hạn phê duyệt.
- Các điều kiện thuộc những nhánh grant thay thế chưa được đánh giá.

Phép tính số chỉ là cách rút gọn sau khi đã xác định các điều kiện có cùng ý nghĩa. Những giới hạn trên tổng mức sử dụng còn cần cơ chế dữ liệu và transaction bảo vệ phạm vi tổng hợp.

## 4. Tập rỗng, thiếu dữ liệu và wildcard

### 4.1. Tập rỗng không phải không giới hạn

Nếu một ranh giới bắt buộc cho phép tập rỗng:

```text
P ∩ ∅ = ∅
```

Không được bỏ qua lớp đó rồi tiếp tục dùng P.

Cần phân biệt:

| Trường hợp | Ý nghĩa cần xử lý |
|---|---|
| Tập quyền rỗng đã được xác định | Không có thao tác nào được lớp đó cho phép |
| Không có ranh giới vì policy nói rõ không áp dụng cho luồng này | Dùng ngữ nghĩa trung tính đã được định nghĩa |
| Không tải được policy | Chưa biết có quyền gì; không suy ra không giới hạn |
| Cấu hình thiếu ranh giới bắt buộc | Lỗi cấu hình hoặc không đủ căn cứ cho phép |
| Kết quả không áp dụng từ một grant thay thế | Có thể xét grant khác trong cùng lớp theo hợp đồng |

Ví dụ, một luồng trực tiếp không có đại diện có thể không cần ranh giới ủy quyền. Việc bỏ lớp đó phải do chính sách phía máy chủ xác định. Một request thiếu trường ủy quyền không tự chứng minh lớp này không cần thiết.

### 4.2. Tránh bẫy kiểm tra trên tập policy rỗng

```java
boolean allowed = boundaries.stream()
        .allMatch(boundary -> boundary.allows(context));
```

Với danh sách rỗng, `allMatch` trả về `true`. Nếu cấu hình hoặc cơ chế chọn policy bị lỗi, hệ thống có thể cho phép mà chưa kiểm tra gì.

Cần xác nhận kế hoạch đánh giá đầy đủ các ranh giới bắt buộc. Chỉ kiểm tra danh sách khác rỗng cũng chưa đủ nếu thiếu riêng TenantBoundary hoặc ResourceBoundary.

### 4.3. Wildcard cần có phạm vi

Một ký hiệu như `*` có thể mang nghĩa “mọi resource trong tenant A” hoặc “mọi action thuộc một nhóm đã xác định”. Nó không mặc nhiên có nghĩa mọi tenant và mọi hành động tương lai.

Phải chuẩn hóa wildcard theo hợp đồng và nguồn có thẩm quyền. Không cho client gửi `resource=*` rồi coi đó là bằng chứng được truy cập tất cả.

## 5. Xây dựng kế hoạch đánh giá có ranh giới rõ ràng

Trước khi tính giao, cần biết những lớp nào bắt buộc cho chính luồng đang xử lý.

Một kế hoạch cho lời gọi thay người dùng có thể gồm:

```text
UserGrantBoundary
TokenBoundary
CallingServiceBoundary
TenantBoundary
ResourceBoundary
DelegationBoundary
ContextBoundary
```

Luồng gọi trực tiếp có thể khác, nhưng sự khác biệt phải do máy chủ chọn theo kiểu xác thực và hợp đồng. Không cho client chọn danh sách lớp muốn bỏ.

### 5.1. Mọi lớp phải đánh giá cùng một thao tác

Ngữ cảnh bất biến có thể gồm:

```text
PermissionContext:
    actor thực sự gọi
    subject nghiệp vụ được đại diện, nếu có
    tenant đã được xác minh
    action cụ thể
    resource và revision đã tải
    input có ảnh hưởng tới quyết định
    thông tin token và dịch vụ đã được xác minh
    thời điểm hoặc phiên bản chính sách cần dùng
```

Không để lớp token kiểm tra đơn A, lớp ownership kiểm tra đơn B rồi handler thực hiện trên đơn C.

Tương tự, nếu một lớp kiểm tra số tiền 100.000 nhưng handler lấy số tiền 900.000 từ một trường khác, các kết quả `ALLOW` không còn chứng minh thao tác thực tế được phép.

### 5.2. Kết quả đánh giá cần có ngữ nghĩa riêng

Có thể biểu diễn:

| Kết quả | Ý nghĩa |
|---|---|
| `ALLOW` | Lớp này cho phép thao tác đang xét, có thể kèm điều kiện phải thực thi |
| `DENY` | Lớp này không cho phép theo ngữ nghĩa đã định nghĩa |
| `NOT_APPLICABLE` | Policy không đưa ra grant hoặc quyết định áp dụng cho ngữ cảnh này |
| `ERROR` | Không thể đánh giá đáng tin cậy |

Trong bộ giao minh họa, mỗi ranh giới đã được xác định là bắt buộc phải trả `ALLOW`. Một kết quả `NOT_APPLICABLE` ở lớp bắt buộc không thể bị bỏ qua như thể đã cho phép.

Bên trong lớp UserGrantBoundary, một grant không áp dụng có thể dẫn tới xét grant tiếp theo. Đây là hai tầng kết hợp khác nhau.

Nếu nguồn policy không sẵn sàng, hệ thống có thể trả lỗi tạm thời theo hợp đồng thay vì lỗi cấm quyền thông thường. Dù phản hồi ra sao, hành động mới không được thực thi khi chưa đủ căn cứ cho phép.

### 5.3. Thứ tự đánh giá và thông tin tiết lộ

Về tập hợp, phép giao có tính giao hoán. Trong triển khai, thứ tự kiểm tra còn ảnh hưởng dữ liệu được tải, chi phí và thông tin có thể bị lộ.

Nên xác thực nguồn gọi và phạm vi tenant trước khi tiết lộ chi tiết tài nguyên. Có thể dừng khi gặp ranh giới chặn, đồng thời ghi lý do nội bộ phù hợp.

Nếu cần thu thập nhiều lý do phục vụ chẩn đoán, không tự động trả toàn bộ trace cho client. Một người ngoài scope không nên nhận tên chủ sở hữu, số dư hoặc cấu trúc policy của đối tượng chỉ vì engine đã đánh giá chúng.

## 6. Ví dụ Java: giao các ranh giới bắt buộc

Đây là mã giả theo cú pháp Java, tập trung vào ngữ nghĩa kết hợp. Các kiểu dữ liệu, kho policy và cơ chế thực thi điều kiện cần được triển khai theo hợp đồng thực tế.

```java
enum BoundaryEffect {
    ALLOW, DENY, NOT_APPLICABLE, ERROR
}

record BoundaryResult(
        BoundaryEffect effect,
        String safeReasonCode,
        String policyVersion,
        List<Obligation> obligations) {}

interface PermissionBoundary {
    String name();
    BoundaryResult evaluate(PermissionContext context);
}

PermissionEvaluation evaluateIntersection(PermissionContext context) {
    EvaluationPlan plan = planProvider.requiredFor(context);

    if (!plan.hasAllRequiredBoundaries()
            || plan.boundaries().isEmpty()) {
        return PermissionEvaluation.denied(
                "INCOMPLETE_AUTHORIZATION_PLAN");
    }

    List<BoundaryEvidence> evidence = new ArrayList<>();
    List<Obligation> obligations = new ArrayList<>();

    for (PermissionBoundary boundary : plan.boundaries()) {
        BoundaryResult result;

        try {
            result = boundary.evaluate(context);
        } catch (PolicyUnavailable unavailable) {
            return PermissionEvaluation.unavailable(
                    "AUTHORIZATION_SOURCE_UNAVAILABLE");
        }

        if (result == null) {
            return PermissionEvaluation.unavailable(
                    "INVALID_BOUNDARY_RESULT");
        }

        evidence.add(BoundaryEvidence.from(boundary, result));

        if (result.effect() != BoundaryEffect.ALLOW) {
            return PermissionEvaluation.notAuthorized(
                    result.effect(), result.safeReasonCode());
        }

        obligations.addAll(result.obligations());
    }

    ObligationPlan obligationPlan =
            obligationComposer.requireCompatible(context, obligations);

    return PermissionEvaluation.authorized(
            context.identity(),
            obligationPlan,
            evidence);
}
```

Các hợp đồng quan trọng:

- `requiredFor` chọn kế hoạch phía máy chủ và xác nhận đủ từng lớp bắt buộc, không chỉ kiểm tra có ít nhất một policy.
- Tất cả boundary nhận cùng một context bất biến, liên kết đúng actor, subject, tenant, action, resource và input.
- `ERROR`, `NOT_APPLICABLE`, `DENY` ở ranh giới bắt buộc đều không tạo một kết quả được phép thực thi.
- `safeReasonCode` là mã theo schema được kiểm soát; dữ liệu chẩn đoán nhạy cảm cần đường xử lý riêng.
- Lỗi lập trình hoặc lỗi nguồn không được chuyển thành `ALLOW` trong nhánh dự phòng.
- `authorized` trả kế hoạch có điều kiện thực thi, không tự gọi nghiệp vụ. Caller phải áp dụng toàn bộ nghĩa vụ trước những tác dụng mà chúng chi phối.
- Context identity giúp liên kết quyết định với thao tác đã đánh giá; nó không tự trở thành token quyền có thể cho client sửa rồi gửi lại.

### 6.1. Hợp grant bên trong một lớp

Logic của UserGrantBoundary có thể được diễn giải:

```java
BoundaryResult evaluateUserGrants(PermissionContext context) {
    List<Grant> grants = grantStore.loadFor(
            context.tenantId(), context.subjectId());

    List<Grant> applicable = grants.stream()
            .filter(grant -> grant.matches(context))
            .toList();

    if (applicable.isEmpty()) {
        return deny("NO_APPLICABLE_USER_GRANT");
    }

    return grantAlternativeComposer.allowFromAlternatives(
            context, applicable);
}
```

Ở đây `matches` phải giữ đủ action, resource và điều kiện của từng grant. Grant không khớp không được coi là một lệnh cấm tường minh phủ quyết mọi grant khác.

`allowFromAlternatives` cần chọn hoặc kết hợp các đường cấp quyền theo ngữ nghĩa đã định nghĩa, giữ lại các điều kiện của đường dùng để cho phép. Nó không được lấy action từ grant này rồi lấy resource hoặc hạn mức không liên quan từ grant khác.

Nếu có luật cấm tường minh, phải đánh giá bằng cơ chế veto đã được xác định. Không trộn lẫn khái niệm “role không cấp action” với “policy cấm action này”.

## 7. Quyết định phải gắn với dữ liệu được sử dụng

Một kết quả giao đúng trên dữ liệu cũ vẫn có thể bị dùng sai nếu nội dung thay đổi trước khi thực hiện.

Ví dụ:

```text
Kiểm tra:
    đơn O, tenant A, chi nhánh HCM, số tiền 400.000

Sau kiểm tra:
    đối tượng hoặc số tiền bị thay đổi

Thực hiện:
    đơn O2 hoặc số tiền 900.000
```

Cần liên kết quyết định với đúng resource, revision và input. Không đánh giá một DTO rồi thực hiện trên entity khác được tải bằng ID từ nguồn chưa kiểm tra.

### 7.1. Ranh giới transaction

Với lệnh tạo yêu cầu hoàn tiền, một luồng có thể là:

1. Xác thực caller và kiểm tra phạm vi truy cập cần thiết.
2. Tải đơn trong tenant đã xác minh, giữ cơ chế kiểm soát cạnh tranh phù hợp.
3. Nhận diện replay của lệnh nếu có; bảo vệ kết quả cũ bằng quyền truy cập hiện tại.
4. Với lệnh mới, dựng context từ đơn và input đã chuẩn hóa.
5. Đánh giá giao các ranh giới quyền.
6. Thực thi các nghĩa vụ của kế hoạch quyền và kiểm tra bất biến nghiệp vụ.
7. Ghi yêu cầu, trạng thái hoặc phần giữ chỗ cần thiết, audit và kết quả idempotency.
8. Commit trước khi công bố thành công; xử lý tích hợp ngoài theo hợp đồng riêng.

Những nguồn như membership, policy hay hạn mức tổng hợp có thể thay đổi độc lập. Khóa một hàng đơn không tự bảo vệ chúng. Nếu cần tính nhất quán chặt, phải phối hợp đúng các tài nguyên và nguồn quyết định.

Một kết quả `ALLOW` không phải quyền vô thời hạn. Phải xác định mốc đánh giá, giới hạn sử dụng và cách xử lý khi quyền bị thu hồi hoặc execution bị trì hoãn.

### 7.2. Phân biệt quyền xem kết quả với quyền thực hiện lệnh mới

Sau lần thành công đầu, trạng thái và version có thể đã đổi. Retry đúng lệnh không nên bị xử lý như một lần tạo mới rồi tự sinh thêm tác dụng.

Ngược lại, biết idempotency key không tạo quyền đọc kết quả. Luồng replay phải kiểm tra quyền phù hợp với việc truy cập kết quả đã có, theo các ranh giới bắt buộc của hành động đó.

Không mặc định dùng nguyên một quyết định tạo mới đã cache để bảo vệ mọi thao tác xem, sửa hoặc phát lại. Mỗi action cần ngữ nghĩa riêng.

## 8. Kết hợp điều kiện và nghĩa vụ theo đúng loại

Kết quả quyền có thể chứa nhiều thứ hơn một giá trị boolean. Một lớp cho phép với hạn mức, bộ lọc, tập trường hoặc bước xác nhận bổ sung.

Không được chỉ lấy `effect=ALLOW` rồi bỏ phần điều kiện còn lại.

### 8.1. Mỗi loại dữ kiện có phép kết hợp riêng

| Dữ kiện đầu ra | Cách kết hợp trong các lớp bắt buộc, khi có cùng ngữ nghĩa |
|---|---|
| Tập action được phép | Lấy giao |
| Phạm vi resource hoặc predicate đọc | Giữ mọi ràng buộc, thường tương ứng phép AND |
| Các trường được phép sửa | Lấy giao các allowlist |
| Hạn mức trên cùng một đại lượng | Lấy giới hạn chặt nhất, có thể là min |
| Yêu cầu xác nhận bổ sung | Phải đáp ứng mọi yêu cầu bắt buộc tương thích |
| Bước phê duyệt bắt buộc | Giữ đủ các yêu cầu, không chỉ các bước xuất hiện ở mọi policy |
| Điều kiện mâu thuẫn hoặc không thực thi được | Không cho phép thao tác theo kế hoạch đó |

Từ “intersection” mô tả việc thu hẹp tập thao tác hợp lệ. Nó không có nghĩa mọi trường dữ liệu đầu ra đều được xử lý bằng phép giao tập hợp.

Ví dụ:

```text
Policy A yêu cầu: xác nhận bổ sung
Policy B yêu cầu: phê duyệt độc lập

Kết quả:
    phải đáp ứng cả hai yêu cầu nếu chúng cùng bắt buộc
```

Nếu lấy giao hai tập tên nghĩa vụ và nhận tập rỗng, hệ thống sẽ bỏ cả hai điều kiện. Đó là lỗi ngữ nghĩa dù mã dùng phép giao đúng về mặt cấu trúc dữ liệu.

### 8.2. Giữ ngoặc khi kết hợp predicate

Giả sử quyền người dùng là owner hoặc được chia sẻ, đồng thời phải trong tenant hiện tại:

```text
TenantBoundary AND (OwnerGrant OR ShareGrant)
```

Nếu chuyển thành một biểu thức không đúng nhóm:

```sql
-- Dễ làm nhánh được chia sẻ vượt khỏi điều kiện tenant.
WHERE tenant_id = :tenant_id
  AND owner_id = :subject_id
   OR shared_with_id = :subject_id
```

thì ý nghĩa không còn như mong muốn.

Biểu thức cần giữ nhóm:

```sql
WHERE tenant_id = :tenant_id
  AND (
        owner_id = :subject_id
        OR shared_with_id = :subject_id
      )
```

Đây là ví dụ giản lược. Quan hệ chia sẻ thực tế còn cần kiểm tra scope, action và hiệu lực riêng. Không dựng điều kiện truy vấn bằng chuỗi tùy ý do client hoặc một nguồn chưa được kiểm chứng cung cấp.

### 8.3. Giao quyền trên trường dữ liệu

Ví dụ:

```text
Grant người dùng cho sửa: {reason, requestedAmount}
Token cho sửa:           {reason}

Hiệu lực:               {reason}
```

Nếu request vẫn gửi `requestedAmount`, endpoint cần xử lý rõ theo hợp đồng, chẳng hạn từ chối trường không được phép. Không âm thầm bỏ mọi thay đổi nhưng vẫn báo đã cập nhật như người dùng mong muốn.

Tập trường cho phép rỗng không có nghĩa được phép sửa tất cả. Các trường quan trọng như tenant, owner, trạng thái phê duyệt hoặc giá do máy chủ tính không được mở ra chỉ vì lớp khác có tên action chung `UPDATE`.

Với phản hồi đọc, các giới hạn cột hoặc masking cũng cần được áp dụng đúng. Một lớp cho phép đọc đối tượng không tự loại bỏ hạn chế về dữ liệu nhạy cảm từ lớp khác.

### 8.4. Điều kiện phải được thực thi ở mốc phù hợp

Một kế hoạch có thể yêu cầu xác nhận trước thao tác, ghi audit cùng commit hoặc chờ phê duyệt trước hành động tiếp theo. Caller phải biết và thực thi đúng mốc của từng nghĩa vụ.

Nếu không có thành phần thực hiện một nghĩa vụ bắt buộc, không trả về quyết định cho phép vô điều kiện. Không lưu điều kiện trong một trường mô tả rồi tiếp tục tác dụng nghiệp vụ như thể điều kiện đã đạt.

## 9. Giữ ngữ nghĩa qua dịch vụ, cache và tác vụ nền

### 9.1. Lời gọi đại diện

Khi dịch vụ S thực hiện thay người dùng U, một mô hình giới hạn có thể là:

```text
Effective(U qua S) =
    UserGrants(U)
    ∩ ServiceBoundary(S)
    ∩ DelegationBoundary(U, S)
    ∩ TokenBoundary
    ∩ TenantBoundary
    ∩ ResourceBoundary
```

Không dùng `UserGrants(U) ∪ ServicePermissions(S)` rồi để tài khoản kỹ thuật mạnh bù cho quyền mà U thiếu.

Thông tin actor, subject, audience hoặc quan hệ đại diện phải được kiểm chứng theo hợp đồng xác thực. Chỉ có header `userId=U` từ một caller không có thẩm quyền không đủ tạo ngữ cảnh đại diện.

Một job chạy bằng danh tính hệ thống riêng có thể có chính sách khác, nhưng phải là luồng được xác định rõ. Không tự đổi danh tính sang hệ thống khi nhánh người dùng bị từ chối.

### 9.2. Cache phải giữ đủ ngữ cảnh

Một quyết định có thể phụ thuộc tenant, actor, subject, action, resource, input và các phiên bản policy hoặc quan hệ.

Cache chỉ theo tên role có thể tái dùng quyền tạo hoàn tiền ở HCM cho đơn HN. Cache chỉ theo resource có thể tái dùng quyết định của người A cho B. Cache bỏ số tiền có thể dùng quyết định cho 100.000 để xử lý 900.000.

Cần chọn khóa, nguồn phiên bản và cơ chế hết hiệu lực phù hợp. Thêm tên `policyVersion` vào khóa không giải quyết được nếu chính phiên bản đang dùng đã cũ mà hệ thống không biết.

Khi quyền bị thu hồi hoặc boundary bị thu hẹp, các kết quả cũ phải được xử lý theo bảo đảm đã công bố. Thông báo vô hiệu cache bất đồng bộ không tự tạo ra bảo đảm thay đổi có hiệu lực tức thì.

### 9.3. Batch và danh sách tài nguyên

Với một batch gồm nhiều đơn, cần đánh giá từng thao tác hoặc tạo một predicate có ngữ nghĩa tương đương đã được chứng minh.

Không kiểm tra:

```text
có ít nhất một đơn trong batch được phép
```

rồi thực hiện trên mọi đơn.

Nếu hợp đồng yêu cầu tất cả cùng thành công, một phần tử không đủ quyền phải được xử lý mà không để lại thay đổi dở dang. Nếu cho phép từng phần tử, kết quả cần phản ánh phạm vi đó và không lộ nội dung của phần tử bị chặn.

Bộ lọc ở endpoint danh sách, tải tài liệu, xuất dữ liệu và tài nguyên con cũng phải giữ giao các ranh giới. Việc endpoint chi tiết được bảo vệ không tự bảo vệ endpoint tổng hợp.

### 9.4. Xử lý bất đồng bộ và thay đổi quyền

Job cần mang các tham chiếu có thẩm quyền tới lệnh, subject, scope và quyết định cần thiết. Không coi message có chữ `authorized=true` là đủ để bỏ mọi kiểm tra tại nơi thực thi.

Phải xác định quyền được kiểm tra tại lúc tiếp nhận hay còn phải kiểm tra lại trước tác dụng bên ngoài. Nếu dùng một execution đã được cấp phép tại mốc trước, cần giữ giới hạn, deadline và quy tắc thu hồi tương ứng.

Lần phát lại message không tạo thêm quyền và không tự cho phép một lần thực hiện mới. Idempotency và ràng buộc nghiệp vụ vẫn cần bảo vệ việc thực thi.

## 10. Những lỗi kết hợp quyền thường gặp

| Cách làm | Hệ quả | Hướng xử lý |
|---|---|---|
| Hợp quyền người dùng với scope token | Token hẹp không còn giới hạn được người dùng | Lấy giao giữa hai ranh giới theo hợp đồng |
| Giao mọi role bất kể ngữ nghĩa | Role bổ sung có thể vô tình làm mất quyền hợp lệ | Hợp các grant thay thế trong đúng lớp |
| Một role không cấp action được coi là cấm toàn cục | Grant hợp lệ từ nhánh khác bị phủ quyết sai | Tách không áp dụng, không có grant và veto tường minh |
| Tách action, resource và điều kiện thành các tập độc lập | Tạo các tổ hợp quyền chưa từng được cấp | Giữ tuple hoặc predicate liên kết đầy đủ |
| Bỏ lớp trả tập rỗng | Tăng quyền khi đáng lẽ không có quyền | Tập rỗng tại lớp bắt buộc phải chặn |
| Policy lỗi thì cho phép theo dữ liệu còn lại | Lỗi phụ thuộc biến thành đường vượt quyền | Không thực thi khi thiếu căn cứ bắt buộc |
| Kiểm tra `allMatch` trên kế hoạch thiếu | Cho phép dù chưa đánh giá đủ lớp | Xác nhận đầy đủ kế hoạch phía máy chủ |
| Chỉ đọc boolean, bỏ nghĩa vụ | Bỏ xác nhận, hạn mức hoặc bước duyệt | Giữ kế hoạch và thực thi điều kiện theo loại |
| Cache bỏ tenant, input hoặc action | Tái dùng quyền sang thao tác khác | Ràng buộc quyết định với đủ ngữ cảnh |
| Tin tài khoản worker có quyền rộng | Tác vụ thay người dùng vượt scope | Giữ quan hệ đại diện và boundary khi xử lý |

### 10.1. Audit quyết định kết hợp

Audit có thể ghi action, resource, subject, tenant, các boundary đã áp dụng, phiên bản policy, kết quả tổng hợp và tham chiếu nghĩa vụ.

Không ghi nguyên token, khóa bí mật hoặc toàn bộ payload nhạy cảm chỉ để giải thích quyết định. Trace nội bộ cần được kiểm soát truy cập; phản hồi cho người gọi chỉ cung cấp mức thông tin phù hợp.

Cần phân biệt:

```text
đã đủ căn cứ quyền cho thao tác được xét
đã thực thi đủ điều kiện bổ sung
đã chấp nhận lệnh nghiệp vụ
đã hoàn tất tác dụng bên ngoài
```

Một dấu vết `ALLOW` không tự chứng minh giao dịch cuối đã thành công. Khi điều tra, phải liên kết quyết định quyền với command, transaction và kết quả thực thi tương ứng.

## 11. Kiểm thử ngữ nghĩa permission intersection

### 11.1. Bảng kết quả của các ranh giới bắt buộc

Với hai lớp bắt buộc:

| Lớp A | Lớp B | Có đủ căn cứ cho phép không? |
|---|---|---|
| ALLOW | ALLOW | Có, còn phải thực thi nghĩa vụ và guard nghiệp vụ |
| ALLOW | DENY | Không |
| DENY | ALLOW | Không |
| DENY | DENY | Không |
| ALLOW | NOT_APPLICABLE | Không trong mô hình lớp bắt buộc |
| ALLOW | ERROR | Không; có thể phản hồi lỗi tạm thời theo hợp đồng |
| Không có đủ lớp trong kế hoạch | Bất kỳ | Không |

Bảng này áp dụng cho các boundary bắt buộc, không áp dụng máy móc cho từng grant thay thế trong một boundary.

### 11.2. Ma trận tình huống nghiệp vụ

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| User có quyền tạo, token chỉ cho đọc | Không tạo yêu cầu |
| Token có action nhưng user không có grant phù hợp | Không dùng token để bù quyền user thiếu |
| Một role cho đọc, role khác cho tạo trong phạm vi phù hợp | Lớp user hợp các grant thay thế đúng ngữ nghĩa |
| Một grant không khớp, grant khác cho phép | Không biến grant không khớp thành veto ngoài ý muốn |
| Có veto tường minh áp dụng theo hợp đồng | Không bị một nhánh grant cho phép làm mất tác dụng |
| Quyền tạo ở HCM và quyền đọc ở HN | Không tạo được yêu cầu cho HN |
| User, token và service có hạn mức khác nhau trên cùng đại lượng | Mọi giới hạn bắt buộc đều được áp dụng |
| Hai hạn mức khác tiền tệ hoặc khác khoảng thời gian | Không rút gọn bằng min khi chưa có nghĩa phù hợp |
| Thiếu ResourceBoundary nhưng các lớp khác cho phép | Phát hiện kế hoạch không đầy đủ |
| Một boundary trả tập rỗng hoặc không áp dụng | Không bỏ qua lớp bắt buộc |
| Nguồn policy lỗi hoặc trả dữ liệu không hợp lệ | Không thực thi hành động mới |
| Hai lớp yêu cầu hai nghĩa vụ khác nhau | Giữ và thực thi cả hai nếu chúng tương thích |
| Tập trường được sửa chỉ giao còn `reason` | Không sửa amount, tenant hoặc trạng thái bằng trường phụ |
| Predicate có nhánh chia sẻ | Không để nhánh OR thoát khỏi điều kiện tenant |
| Dịch vụ mạnh gọi thay user yếu quyền | Không mở rộng user bằng quyền kỹ thuật của dịch vụ |
| Batch có một phần tử ngoài scope | Thực hiện đúng hợp đồng, không cấp quyền từ phần tử khác |
| Input thay đổi sau khi đánh giá | Không dùng quyết định cũ cho thao tác mới |
| Cache cùng resource nhưng khác action hoặc amount | Không tái dùng sai quyết định |
| Replay lệnh đã có kết quả | Không cấp quyền mới và không tạo tác dụng trùng |

### 11.3. Các tính chất có thể dùng để kiểm chứng

**Thu hẹp một ranh giới không được làm tăng quyền.**

Nếu các lớp còn lại và ngữ cảnh không đổi:

```text
B_new ⊆ B_old

thì:
    Effective_new ⊆ Effective_old
```

Ví dụ, token đổi từ cho phép HCM và HN sang chỉ HCM không được khiến user tạo được yêu cầu ở một chi nhánh thứ ba.

**Thêm một ranh giới bắt buộc không được làm tăng quyền.**

```text
Effective_new = Effective_old ∩ AdditionalBoundary
```

Nếu implementation cho phép thêm thao tác sau bước này, cần kiểm tra lỗi dùng union, xử lý tập rỗng hoặc mất điều kiện.

**Grant không liên quan không tạo tổ hợp mới.**

Thêm grant đọc ở HN không được tạo quyền ghi ở HN bằng cách kết hợp với grant ghi tại HCM.

**Thêm grant thay thế không tự làm mất grant cũ trong mô hình hợp thuần túy.**

Tính chất này chỉ áp dụng khi thêm một grant cho phép và không thay đổi veto, điều kiện phân tách nhiệm vụ hoặc policy khác. Nếu có thay đổi các luật đó, phải đánh giá theo ngữ nghĩa đã công bố.

**Hoán đổi thứ tự không làm đổi kết quả quyền khi các boundary là predicate thuần trên cùng context.**

Thứ tự có thể làm khác chi phí hoặc lý do được ghi đầu tiên, nhưng tập thao tác được phép của phép giao phải tương đương. Không áp dụng kiểm tra này cho các thành phần có tác dụng phụ hoặc ngữ nghĩa khác chưa được mô hình hóa.

Có thể xây một tập hữu hạn các thao tác mẫu và đối chiếu kết quả trước, sau mỗi thay đổi. Test cần giữ đủ tenant, resource, input và điều kiện, không chỉ so danh sách tên action.

### 11.4. Kiểm tra điều không được xảy ra khi bị chặn

Với một lệnh mới không đủ quyền:

```text
không tạo yêu cầu nghiệp vụ thành công
không tăng version hoặc thay trạng thái dở dang
không giữ chỗ hạn mức như một lần chấp nhận thành công
không phát outbox báo đã chấp nhận
không gọi hệ thống ngoài từ nhánh bị chặn
không ghi audit giả về kết quả thành công
không bỏ điều kiện để thử lại bằng một nhánh rộng hơn
không trả dữ liệu ngoài scope trong thông báo lỗi
```

Lần từ chối vẫn có thể tạo dấu vết bảo mật theo chính sách. Điều đó phải được phân biệt với việc tạo một yêu cầu hoàn tiền hợp lệ.

### 11.5. Kiểm thử thay đổi đồng thời

Các ca đáng kiểm tra gồm:

- Scope đối tượng hoặc membership bị thu hẹp khi lệnh đang xử lý.
- Nội dung đổi sau khi context được dựng nhưng trước lúc ghi.
- Hạn mức tổng hợp bị hai giao dịch dùng đồng thời.
- Quyết định cache còn tồn tại sau thay đổi policy.
- Job bắt đầu thực thi sau mốc hiệu lực hoặc thu hồi được quy định.

Kỳ vọng phải theo ranh giới nhất quán và mốc đánh giá mà hệ thống đã chọn. Một test chỉ gọi trực tiếp hàm boolean không chứng minh được transaction hoặc cơ chế thu hồi phân tán.

## 12. Bài tập áp dụng

Thiết kế permission intersection cho API tạo yêu cầu hoàn tiền trong hệ thống nhiều tenant, có dịch vụ hỗ trợ gọi thay người dùng.

1. Chia các nguồn thành grant thay thế, ranh giới bắt buộc và veto tường minh nếu có.
2. Viết công thức kết hợp với dấu ngoặc thể hiện rõ lớp nào lấy hợp và lớp nào lấy giao.
3. Thiết kế một context giữ đủ actor, subject, tenant, action, resource, số tiền và tiền tệ.
4. Tạo hai grant có action và chi nhánh khác nhau; chứng minh không xuất hiện tổ hợp quyền ngoài ý định.
5. Xác định hành vi khi boundary rỗng, không áp dụng, bị thiếu hoặc không đánh giá được.
6. Mô tả cách kết hợp hạn mức, trường được sửa và các yêu cầu phê duyệt bổ sung.
7. Chỉ ra mốc đánh giá, transaction và cách xử lý cache hoặc job bất đồng bộ.
8. Viết các ca kiểm thử cho token hẹp hơn user, dịch vụ mạnh hơn user và một policy nguồn bị lỗi.
9. Nêu bằng chứng cần có để giải thích vì sao một lệnh được phép nhưng vẫn bị guard nghiệp vụ chặn.

Một thiết kế đúng cần giữ nguyên ý nghĩa của từng nguồn quyền và chỉ cho phép phần thao tác còn hợp lệ sau mọi ranh giới bắt buộc. Grant, phạm vi và điều kiện phải đi cùng nhau từ lúc đánh giá tới lúc thực thi để một lớp cho phép không vô tình mở rộng những giới hạn của lớp khác.
