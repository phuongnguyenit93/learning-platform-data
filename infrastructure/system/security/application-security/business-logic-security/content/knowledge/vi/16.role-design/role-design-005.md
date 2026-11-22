# Khoảng thời gian kích hoạt vai trò (Role activation period)

Một người được gán vai trò không nhất thiết được sử dụng mọi quyền của vai trò đó vào mọi thời điểm. Nhân viên có thể được gán vai trò phê duyệt dài hạn, nhưng chỉ được kích hoạt nó trong một phiên cụ thể, sau khi đáp ứng điều kiện và trong một khoảng thời gian giới hạn.

Nếu hệ thống chỉ kiểm tra lúc đăng nhập rồi giữ danh sách role trong phiên nhiều giờ, người dùng có thể tiếp tục duyệt sau khi khoảng kích hoạt đã hết. Một tác vụ nền, token cũ hoặc kết quả cache cũng có thể kéo dài quyền ngoài phạm vi được cấp nếu không giữ đúng ngữ nghĩa thời gian.

Bài học thuộc chương **Role Design** trong bảo mật logic nghiệp vụ. Trọng tâm là định nghĩa, cấp và thực thi khoảng kích hoạt vai trò; bảo vệ quyền theo đối tượng, trạng thái và các bất biến nghiệp vụ khi có hết hạn, thu hồi, cạnh tranh hoặc retry.

## 1. Phân biệt các loại thời hạn

Những mốc sau có thể cùng tồn tại nhưng không thay thế nhau:

| Khái niệm | Ý nghĩa |
|---|---|
| Thời hạn gán vai trò | Người dùng được gán hoặc đủ điều kiện sử dụng vai trò trong khoảng nào |
| Khoảng kích hoạt vai trò | Vai trò được đưa vào tập quyền có thể dùng trong phiên hoặc ngữ cảnh nào, từ lúc nào đến lúc nào |
| Thời hạn phiên | Phiên xác thực còn được chấp nhận trong bao lâu |
| Thời hạn token | Token có thể được chấp nhận theo hợp đồng xác thực trong khoảng nào |
| Lịch hoạt động | Vai trò hoặc hành động chỉ được dùng trong các ca, ngày hoặc khoảng lịch được định nghĩa |
| Deadline của thao tác | Lệnh đã được chấp nhận phải bắt đầu hoặc hoàn tất trước mốc nào |

Ví dụ:

```text
Gán vai trò APPROVER:        09:00 → 17:00
Kích hoạt trong phiên S:     10:15 → 10:30
Phiên S:                    08:00 → 18:00
Token đang dùng:            10:10 → 10:25

Khoảng có thể dùng quyền qua token này:
                            10:15 → 10:25
```

Token còn hiệu lực không kéo dài activation. Activation còn hiệu lực cũng không làm token đã hết hạn trở nên hợp lệ.

### 1.1. Vai trò hợp lệ chưa phải quyền trên mọi đối tượng

Vai trò `APPROVER` đang hoạt động có thể cho một khả năng nền. Khi duyệt đơn cụ thể, vẫn phải kiểm tra:

- Đúng tenant, đơn vị hoặc phạm vi được cấp.
- Đúng đối tượng và loại hành động.
- Người duyệt đủ hạn mức.
- Nội dung và trạng thái cho phép quyết định.
- Không tự duyệt hoặc vi phạm phân tách nhiệm vụ.
- Không tạo quyết định hoặc tác dụng nghiệp vụ trùng.

Khoảng kích hoạt là một ranh giới bổ sung. Nó không làm mất các điều kiện còn lại.

### 1.2. Vai trò hết hạn không nhất thiết khóa mọi quyền khác

Một người có thể vừa là nhân viên thông thường vừa có khả năng kích hoạt vai trò phê duyệt. Khi activation phê duyệt hết hạn, họ có thể vẫn được sửa bản nháp của mình bằng một grant khác hợp lệ.

Hệ thống cần loại bỏ các grant không còn đủ điều kiện cho hành động đang xét, rồi kết hợp những grant còn lại theo chính sách. Không mặc định một activation hết hạn sẽ cấm mọi thao tác không liên quan.

Ngược lại, action cần vai trò phê duyệt đang kích hoạt không được dự phòng bằng một role khác không có thẩm quyền tương ứng.

## 2. Định nghĩa hợp đồng kích hoạt trước khi triển khai

Một chính sách kích hoạt cần trả lời rõ:

| Câu hỏi | Ví dụ về quyết định cần có |
|---|---|
| Ai được kích hoạt? | Người có assignment còn hiệu lực trong tenant |
| Kích hoạt ở đâu? | Một phiên, một thiết bị hoặc ngữ cảnh được định danh theo mô hình |
| Cần điều kiện gì? | Xác nhận bổ sung, lý do, phê duyệt hoặc điều kiện rủi ro theo chính sách |
| Bắt đầu khi nào? | Ngay khi cấp hoặc một thời điểm tương lai được phép |
| Tối đa bao lâu? | Thời lượng do policy quy định và bị giới hạn bởi các thời hạn liên quan |
| Có tự gia hạn không? | Chỉ nếu có chính sách rõ; hoạt động của người dùng không mặc nhiên kéo dài quyền |
| Thu hồi ảnh hưởng gì? | Lệnh mới, phiên khác, token cũ và execution đang chờ |
| Mốc kiểm tra quyền là gì? | Khi chấp nhận lệnh, khi bắt đầu tác dụng hay nhiều mốc |
| Có được kích hoạt đồng thời role xung đột không? | Theo ràng buộc phân tách nhiệm vụ |

Các con số như 10 hoặc 30 phút chỉ có ý nghĩa khi gắn với nhu cầu và rủi ro đã được xác định. Không có một thời lượng chung phù hợp cho mọi vai trò.

### 2.1. Phạm vi activation cần được lưu rõ

Một bản ghi có thể gồm:

```text
activationId
tenantId
subjectId
roleId
assignmentId
sessionId hoặc executionContextId
notBefore
expiresAt
status hoặc dấu mốc thu hồi
assignmentVersion
activationVersion
policyVersion
căn cứ xác nhận hoặc phê chuẩn nếu có
```

Không chỉ lưu `user.activeRole = APPROVER` nếu mục tiêu là giới hạn riêng một phiên. Cờ toàn cục có thể làm vai trò được kích hoạt ngoài ý muốn ở trình duyệt khác hoặc một ứng dụng khác của cùng người.

Client có thể gửi activationId để chọn ngữ cảnh. Máy chủ vẫn phải tải và kiểm tra rằng bản ghi thuộc đúng người, tenant, role và phiên hiện tại.

### 2.2. Thời lượng đề nghị là đầu vào chưa có thẩm quyền

Người dùng có thể đề nghị một khoảng thời gian, nhưng máy chủ phải giới hạn theo policy và assignment hiện tại.

Ví dụ, người dùng đề nghị kích hoạt đến 10:45 trong khi assignment hết lúc 10:20. API có thể từ chối hoặc cấp một khoảng ngắn hơn theo hợp đồng; không được kéo assignment dài thêm để đáp ứng đề nghị.

Nếu hệ thống thu hẹp khoảng, phản hồi phải cho biết mốc thực sự được cấp. Giao diện không được tiếp tục hiển thị thời lượng người dùng đã xin như thể đó là quyền đã có.

## 3. Mô hình thời gian và trạng thái

### 3.1. Dùng khoảng nửa mở

Một quy ước dễ kiểm chứng:

```text
notBefore <= decisionTime < expiresAt
```

Tại đúng `notBefore`, activation có thể bắt đầu dùng. Tại đúng `expiresAt`, một lần sử dụng mới không còn hợp lệ.

Quy ước phải nhất quán giữa API, cơ sở dữ liệu, cache, worker và kiểm thử. Tránh một tầng dùng `<= expiresAt` còn tầng khác dùng `< expiresAt`.

Khoảng có đầu bằng cuối hoặc đầu sau cuối không phải một activation có thời lượng hợp lệ.

### 3.2. Giao các khoảng bắt buộc

Với các khoảng liên tục có cùng ngữ nghĩa:

```text
effectiveStart = max(
    assignmentStart,
    activationStart,
    sessionStart,
    tokenStart,
    applicableScheduleStart
)

effectiveEnd = min(
    assignmentEnd,
    activationEnd,
    sessionEnd,
    tokenEnd,
    applicableScheduleEnd
)
```

Chỉ có khoảng dùng được nếu `effectiveStart < effectiveEnd` và thời điểm kiểm tra nằm trong khoảng đó.

Các lớp không áp dụng phải do policy xác định tường minh. Thiếu dữ liệu thời hạn vì không tải được không tự có nghĩa vô hạn.

Nếu lịch cho phép nhiều khoảng rời nhau, cần giữ tập các khoảng đó. Không lấy mốc đầu sớm nhất và mốc cuối muộn nhất rồi vô tình cho phép cả khoảng nghỉ giữa ca.

### 3.3. Nhãn trạng thái không thay thế điều kiện thời gian

Một mô hình có thể có:

| Nhãn | Ý nghĩa |
|---|---|
| REQUESTED | Đang xin, chưa được dùng |
| SCHEDULED | Đã cấp nhưng chưa đến mốc bắt đầu |
| ACTIVE | Được cấp để sử dụng, vẫn phải kiểm tra thời gian và các ranh giới |
| REVOKED | Đã bị thu hồi |
| EXPIRED | Đã hết hiệu lực thời gian theo mô hình |

Một số nhãn có thể được tính từ dữ liệu thay vì cập nhật bằng job. Dù chọn cách nào, request đến sau `expiresAt` phải bị chặn ngay cả khi cột status vẫn là `ACTIVE`.

Job nền có thể dọn dữ liệu hoặc cập nhật giao diện. Nó không nên là nguồn duy nhất quyết định quyền đã hết hay chưa.

## 4. Cấp và gia hạn activation có kiểm soát

Một luồng kích hoạt có thể gồm:

1. Xác thực người gọi, phiên và tenant.
2. Tải assignment có thẩm quyền cho đúng role.
3. Kiểm tra người gọi có đủ điều kiện kích hoạt và đã đáp ứng yêu cầu bổ sung.
4. Kiểm tra các role đang hoạt động có xung đột theo policy không.
5. Tính khoảng thực sự được cấp từ đề nghị và mọi giới hạn liên quan.
6. Ghi activation, căn cứ, audit và kết quả idempotency trong ranh giới nhất quán.
7. Trả activationId và các mốc thực sự được cấp sau commit.

Quyền gửi lệnh kích hoạt cần được định nghĩa riêng. Không yêu cầu người dùng phải đang dùng chính role đặc quyền đó mới có thể xin kích hoạt, nhưng cũng không cho một người bất kỳ chọn roleId rồi tự cấp assignment.

### 4.1. Gán vai trò và kích hoạt là hai quyết định khác nhau

Nếu assignment đã bị thu hồi hoặc hết hạn, endpoint kích hoạt không được tự cấp lại assignment.

Nếu policy yêu cầu phê chuẩn trước, việc tạo một đề nghị kích hoạt chưa cấp quyền. Phải phân biệt trạng thái đang xin với activation đã được phát hành hợp lệ.

Vai trò và giới hạn lấy từ policy phía máy chủ. Những trường như `approved=true`, `role=SUPER_ADMIN` hoặc `expiresAt` do client gửi không tự trở thành dữ kiện có thẩm quyền.

### 4.2. Kích hoạt đồng thời các role xung đột

Nếu policy cấm đồng thời hai role trong một phiên, hai lệnh kích hoạt cần phối hợp trên cùng phạm vi session để không cùng thấy “chưa có role xung đột”.

Nếu cấm theo một con người trên mọi phiên, chỉ khóa từng session là chưa đủ. Cơ chế phối hợp phải bao phủ đúng chủ thể và phạm vi mà quy tắc định nghĩa.

Dù có thể tắt role lập lệnh rồi bật role duyệt, lịch sử hành động trên giao dịch vẫn phải được xét. Chuyển activation không xóa việc người đó đã lập nội dung và không tự cho phép họ duyệt chính giao dịch của mình.

### 4.3. Gia hạn không phải một request thông thường

Một request dùng quyền không nên tự kéo dài `expiresAt` nếu chính sách không cho phép.

Nếu hỗ trợ gia hạn, cần kiểm tra lại assignment, phiên, điều kiện bổ sung, xung đột và giới hạn thời gian. Một cơ chế thời hạn trượt còn cần quy định giới hạn tuyệt đối nếu không muốn hoạt động liên tục giữ quyền vô hạn.

Có thể tạo activation mới hoặc ghi thay đổi có version và audit theo mô hình. Không để hai request gia hạn cạnh tranh làm thời hạn vượt quá giới hạn mà mỗi request riêng lẻ đã được kiểm tra.

Retry cùng lệnh kích hoạt hoặc gia hạn phải trả kết quả đã lưu, không tính lại điểm kết thúc từ thời gian retry rồi cấp thêm thời lượng.

## 5. Ví dụ Java: kiểm tra khoảng hiệu lực

Các đoạn mã dùng kiểu thời gian của Java để minh họa quy tắc, chưa phải một ứng dụng đầy đủ.

```java
record TimeWindow(
        Instant fromInclusive,
        Instant untilExclusive) {

    TimeWindow {
        Objects.requireNonNull(fromInclusive);
        Objects.requireNonNull(untilExclusive);

        if (!fromInclusive.isBefore(untilExclusive)) {
            throw new IllegalArgumentException("INVALID_TIME_WINDOW");
        }
    }

    boolean contains(Instant instant) {
        return !instant.isBefore(fromInclusive)
                && instant.isBefore(untilExclusive);
    }

    static Optional<TimeWindow> intersect(
            List<TimeWindow> requiredWindows) {

        if (requiredWindows.isEmpty()) {
            throw new IllegalArgumentException("MISSING_TIME_BOUNDARIES");
        }

        Instant start = requiredWindows.get(0).fromInclusive();
        Instant end = requiredWindows.get(0).untilExclusive();

        for (TimeWindow window : requiredWindows) {
            if (window.fromInclusive().isAfter(start)) {
                start = window.fromInclusive();
            }
            if (window.untilExclusive().isBefore(end)) {
                end = window.untilExclusive();
            }
        }

        if (!start.isBefore(end)) {
            return Optional.empty();
        }

        return Optional.of(new TimeWindow(start, end));
    }
}
```

Các lớp cần dùng nằm trong `java.time` và `java.util`. Logic không phụ thuộc múi giờ hiển thị vì các mốc đã được quy về thời điểm xác định.

Hàm chỉ nhận những khoảng liên tục bắt buộc đã được chọn đúng. Nó không tự quyết định lớp nào được bỏ, xử lý lịch nhiều ca hay xác minh dữ liệu đầu vào có thẩm quyền.

Một assignment không giới hạn thời gian cần cách biểu diễn được policy cho phép rõ ràng. Không đổi mọi trường null hoặc lỗi tải dữ liệu thành một khoảng vô hạn.

### 5.1. Kiểm tra activation trong đúng ngữ cảnh

Mã giả ở ranh giới phân quyền:

```java
ActivatedRoleEvidence requireActiveRole(
        RoleUseContext context,
        RoleAssignment assignment,
        RoleActivation activation) {

    bindings.requireMatch(
            context, assignment, activation);

    assignment.requireIssuedAndNotRevoked();
    activation.requireIssuedAndNotRevoked();

    rolePolicy.requireAcceptedPolicyContext(
            assignment, activation, context);

    // Builder xác nhận đủ từng ranh giới cần có cho luồng này.
    List<TimeWindow> windows = timeBoundaries.requiredFor(
            context, assignment, activation);

    TimeWindow effective = TimeWindow.intersect(windows)
            .orElseThrow(() ->
                    new RoleUnavailable("NO_EFFECTIVE_ACTIVATION_WINDOW"));

    Instant decisionTime = authoritativeClock.instant();

    if (!effective.contains(decisionTime)) {
        throw new RoleUnavailable("ROLE_NOT_ACTIVE_AT_DECISION_TIME");
    }

    return new ActivatedRoleEvidence(
            activation.id(),
            assignment.id(),
            context.identity(),
            decisionTime,
            effective.untilExclusive());
}
```

Hợp đồng triển khai:

- `bindings` kiểm tra tenant, subject, role, assignment, session hoặc context và các quan hệ đại diện phù hợp.
- Danh tính, phiên và token trong context đã được xác minh; body không tự chọn một người khác để kiểm tra.
- “Issued and not revoked” xác nhận quyền đã được cấp hợp lệ và chưa bị thu hồi. Thời gian vẫn được kiểm tra riêng, không phụ thuộc job chuyển nhãn.
- `requiredFor` xác nhận đủ các lớp cần thiết, không chỉ trả một danh sách khác rỗng bất kỳ.
- `authoritativeClock` là nguồn thời gian phía hệ thống được chọn theo yêu cầu nhất quán, không lấy từ giờ trình duyệt hay header client.
- Dữ liệu đã tải phải được bảo vệ hoặc kiểm chứng theo ranh giới nhất quán yêu cầu. Hàm thuần không tự giải quyết thu hồi đồng thời.
- Evidence gắn với context và mốc đánh giá; không phải một quyền mới để client sửa rồi dùng vô thời hạn.

Với lịch rời rạc, lớp chọn lịch cần xác định khoảng cho phép chứa thời điểm đang xét hoặc từ chối nếu không có. Nếu việc chọn lịch và kiểm tra cách nhau đủ lâu để qua một biên, phải đánh giá lại phù hợp thay vì giữ một kết luận cũ.

## 6. Kiểm tra ở mốc sử dụng quyền

Chỉ kiểm tra lúc login hoặc lúc tạo activation sẽ bỏ sót những request đến sau khi hết hạn.

Một lệnh phê duyệt có thể đi theo luồng:

```text
Xác thực request và phạm vi
    → tải hồ sơ cùng dữ kiện quyền cần thiết
    → kiểm tra role đang kích hoạt trong context
    → kiểm tra quyền trên đối tượng, hạn mức và phân tách nhiệm vụ
    → kiểm tra trạng thái, revision và điều kiện nghiệp vụ
    → ghi quyết định cùng audit, outbox nếu có
    → commit
```

Mọi đường có thể ghi quyết định, gồm HTTP, consumer, công cụ quản trị và job, đều cần một mô hình thẩm quyền phù hợp. Không để consumer chỉ thấy tên role trong message rồi coi quyền còn hiệu lực.

### 6.1. Chọn rõ mốc đánh giá

Một request có thể đi qua nhiều thời điểm:

```text
nhận request
    → chờ khóa
    → đánh giá quyền
    → ghi dữ liệu
    → commit
    → worker bắt đầu tác dụng bên ngoài
```

Role có thể hết hạn giữa những mốc này. Cần định nghĩa mốc nào có ý nghĩa với từng hành động.

Trong ví dụ hàm Java, hiệu lực được kiểm tra tại thời điểm quyết định quyền sau khi đã chuẩn bị dữ kiện. Nếu transaction còn chờ hoặc tác dụng xảy ra muộn hơn, không được diễn giải rằng hàm đã chứng minh quyền hợp lệ ở mọi mốc tương lai.

Nếu policy yêu cầu quyền còn hiệu lực trước điểm thực thi quan trọng, cần một cổng kiểm tra hoặc cơ chế cấp phép có deadline phù hợp tại điểm đó. Chỉ thêm một lần so sánh ở đầu request không tạo ra bảo đảm “còn quyền tại commit” hay “còn quyền khi dịch vụ ngoài thực hiện”.

### 6.2. Request bắt đầu sớm nhưng dùng quyền muộn

Giả sử activation hết lúc 10:30. Request đến 10:29:59 nhưng chờ khóa đến 10:30:05.

Nếu policy kiểm tra tại mốc quyết định sau khi lấy khóa, request phải bị chặn. Không dùng thời điểm nhận request để kéo dài quyền, trừ khi hợp đồng thực sự đã chọn mốc đó và bảo vệ các hệ quả tương ứng.

Nguồn thời gian cũng cần đúng ngữ nghĩa: thời điểm bắt đầu transaction và thời điểm thực tế khi đánh giá có thể không giống nhau tùy công nghệ. Adapter thời gian phải cung cấp mốc mà policy yêu cầu.

### 6.3. Hết hạn không tự xóa quyết định lịch sử

Một quyết định được chấp nhận hợp lệ trong khoảng được phép vẫn có lịch sử của nó sau khi role hết hạn. Không tự đổi quyết định đó thành “chưa từng được duyệt”.

Hành động tiếp theo có thể cần một quyền hoặc activation hiện tại khác. Việc một người đã duyệt lúc trước không cho phép họ thực hiện mọi bước về sau.

Nếu có quy trình hủy hoặc vô hiệu quyết định, cần thực hiện qua hành động có thẩm quyền và audit tương ứng.

## 7. Cạnh tranh, thu hồi và idempotency

### 7.1. Thu hồi có thể xảy ra trước mốc hết hạn

Role chưa đến `expiresAt` vẫn có thể mất khả năng sử dụng vì:

- Assignment bị thu hồi.
- Activation bị tắt hoặc thu hồi.
- Phiên bị kết thúc.
- Người dùng mất membership cần thiết.
- Chính sách thay đổi làm activation cũ không còn được chấp nhận.

Do đó, phép so thời gian chỉ là một phần kiểm tra. Mốc kết thúc trong tương lai không chứng minh quyền hiện vẫn được cấp.

Cần xác định bảo đảm thu hồi: có hiệu lực tại nguồn quyền, tại mọi request mới hay sau một độ trễ được chấp nhận. Không hứa thu hồi tức thì nếu kiến trúc chỉ kiểm tra token tự chứa hoặc cache có thời gian sống.

### 7.2. Phối hợp đúng phạm vi dữ liệu

Các lệnh kích hoạt, gia hạn, thu hồi và sử dụng có thể cạnh tranh. Nếu việc dùng quyền cần được chặn sau khi thu hồi đã có hiệu lực, chúng phải phối hợp qua khóa, version, thế hệ quyền hoặc cơ chế tương ứng.

Khóa riêng đối tượng nghiệp vụ không tự khóa activation hoặc assignment. Khóa riêng activation cũng không ngăn một đường khác sửa assignment mà không tuân thủ giao thức.

Nếu chạm nhiều aggregate, cần thứ tự khóa nhất quán và mô hình rõ cho nguồn quyền ngoài cơ sở dữ liệu cục bộ. Một transaction không tự làm mọi dữ kiện từ hệ thống danh tính bên ngoài trở nên nguyên tử.

Khi có version, một thay đổi thu hồi hoặc gia hạn phải làm version hoặc generation liên quan thay đổi theo hợp đồng. Không để một lần gia hạn dựa trên bản cũ ghi đè việc thu hồi đã được chấp nhận.

### 7.3. Cấp lại và gia hạn cùng lúc

Hai lệnh gia hạn đều có thể đọc cùng một điểm kết thúc rồi tính thời lượng theo những cách khác nhau. Nếu chỉ cộng thời gian tùy ý, kết quả có thể vượt giới hạn.

Policy nên xác định điểm neo, khoảng tối đa và điều kiện gia hạn; phép ghi cần kiểm tra version cùng các trạng thái liên quan. Cấp lại sau khi hết hạn có thể là một activation mới với căn cứ mới, không phải âm thầm sửa lịch sử.

Một assignment sắp hết hạn vẫn là giới hạn trên nếu chính sách không cho phép giữ activation vượt assignment. Không tự kéo dài cả hai bản ghi từ lệnh gia hạn activation.

### 7.4. Retry không gia tăng thời hạn hoặc tác dụng

Với cùng lệnh kích hoạt và cùng fingerprint, retry cần trả lại activationId cùng khoảng đã cấp. Nó không được tạo activation mới bắt đầu từ thời điểm gửi lại.

Với lệnh nghiệp vụ đã được chấp nhận khi role hợp lệ, replay không phải một lần sử dụng mới để tạo thêm quyết định. Quyền xem kết quả cũ phải được kiểm tra theo action đọc kết quả và trạng thái xác thực hiện tại.

Nếu lệnh trước có kết quả commit chưa rõ, cần đối soát bằng định danh ổn định. Không vừa báo quyền hết hạn vừa tự thực hiện lại tác dụng bằng một danh tính kỹ thuật rộng quyền.

## 8. Token, phiên và cache không được kéo dài activation

### 8.1. Token còn hạn nhưng role đã hết khoảng dùng

Một token có thể sống lâu hơn activation. Nếu ứng dụng chỉ kiểm tra token và thấy claim `APPROVER`, nó có thể chấp nhận thao tác sau khi role không còn hoạt động.

Các cách thiết kế có thể gồm:

- Kiểm tra activation và assignment tại nguồn có thẩm quyền khi dùng quyền.
- Liên kết token với activationId và giới hạn quyền đặc biệt bằng mốc kết thúc tương ứng.
- Kiểm tra thế hệ quyền hoặc cơ chế thu hồi theo bảo đảm của hệ thống.
- Dùng thời hạn và cache phù hợp với mức lỗi thời được chấp nhận.

Những cách này có bảo đảm khác nhau. Token ký đúng chứng minh một số dữ kiện về nguồn phát hành; nó không tự phản ánh mọi thay đổi đã xảy ra sau khi phát hành.

Nếu cần thu hồi trước hạn, chỉ rút ngắn thời hạn token không tự tạo hiệu lực ngay lập tức. Thiết kế phải có cơ chế đáp ứng đúng yêu cầu đó hoặc công bố giới hạn tương ứng.

### 8.2. Refresh phiên không tự refresh vai trò đặc quyền

Gia hạn token hoặc duy trì phiên có thể phục vụ quyền thông thường. Nó không nên tự đẩy `expiresAt` của activation ra xa hơn.

Khi phát token mới, cần xét activation hiện tại và chỉ đưa vào những khả năng còn được phép theo hợp đồng. Không chép nguyên danh sách role đặc quyền từ token cũ mà bỏ qua mốc đã hết.

Ngược lại, nếu người dùng xin một activation mới hợp lệ, việc cấp cần đi qua luồng kiểm tra, version và audit tương ứng. Không coi thao tác refresh thông thường là đã đáp ứng mọi yêu cầu kích hoạt.

### 8.3. Giới hạn cache theo mốc gần nhất

Giả sử một quyết định ALLOW được cache. Thời gian sống của nó không nên vượt mốc hiệu lực đã biết:

```text
remaining = effectiveEnd - currentAuthoritativeTime

nếu remaining <= 0:
    không dùng quyết định như một quyền còn hiệu lực

ngược lại:
    cacheTtl <= min(configuredTtl, remaining)
```

`effectiveEnd` là giới hạn gần nhất trong những boundary áp dụng, không chỉ riêng activationEnd.

Khóa cache cần giữ đúng tenant, subject, session, role, action và những phiên bản hoặc thuộc tính mà quyết định phụ thuộc. Một activation của phiên S1 không được tự dùng để mở quyền ở S2 nếu policy giới hạn theo phiên.

TTL vẫn chưa giải quyết thu hồi sớm. Cần phối hợp invalidation hoặc kiểm chứng phiên bản theo mức nhất quán đã chọn. Khi một nguồn kiểm tra lỗi, không đổi sang coi role hoạt động vô thời hạn.

## 9. Tác vụ nền và hành động kéo dài

### 9.1. Chọn mô hình thẩm quyền cho execution

Hai mô hình sau có ý nghĩa khác nhau:

| Mô hình | Điều cần bảo vệ |
|---|---|
| Quyền được kiểm tra khi chấp nhận một execution có phạm vi xác định | Lưu căn cứ, đối tượng, nội dung, định danh thao tác, deadline và quy tắc hủy nếu có |
| Quyền người dùng phải còn hiệu lực trước tác dụng quan trọng | Worker phải kiểm tra lại theo chính sách tại mốc đó; hết hạn dẫn tới chờ hoặc từ chối phù hợp |

Không vô tình đổi từ mô hình thứ hai sang thứ nhất chỉ vì công việc đi qua message queue.

Worker cũng cần danh tính và quyền kỹ thuật phù hợp. Một message có `roleActive=true` không tự chứng minh nó được tạo bởi nguồn có thẩm quyền hay còn đáp ứng điều kiện hiện tại.

### 9.2. Vai trò hết hạn khi công việc đang chờ

Nếu policy yêu cầu role còn hoạt động khi worker bắt đầu, một execution chờ quá lâu phải được xử lý theo hợp đồng: dừng, cần cấp phép lại hoặc chuyển xử lý có thẩm quyền.

Nếu policy cho phép execution đã được chấp nhận tiếp tục, phải giữ đúng phạm vi đã cấp. Không cho nó lấy thêm đối tượng mới, tăng số tiền hoặc mở thêm một action sau khi activation của người dùng đã hết.

Thu hồi có chặn execution đang chờ hay không cũng cần được quy định riêng. Thu hồi không tự đảo ngược một tác dụng bên ngoài đã xảy ra.

### 9.3. Batch không có nghĩa được dùng quyền mãi

Một batch lớn có thể kéo dài qua mốc hết activation. Nếu mỗi phần tử là một hành động mới cần quyền hiện tại, cần kiểm tra theo mốc tương ứng cho từng hành động.

Nếu batch là một lệnh hữu hạn đã được cấp phép ở mốc tiếp nhận, cần chốt phạm vi và giới hạn của batch. Không để worker tiếp tục thêm ID hoặc dữ liệu mới từ một danh sách có thể sửa sau đó.

Retry kỹ thuật cần giữ executionId và cơ chế idempotency. Không dùng mỗi lần retry để xin hoặc ngầm tạo một activation mới.

## 10. Múi giờ, lịch làm việc và đồng hồ

### 10.1. Lưu thời điểm rõ ràng, hiển thị theo ngữ cảnh

Một mốc tuyệt đối nên có biểu diễn không mơ hồ. Ví dụ:

```text
09:00 với offset +07:00
    tương ứng
02:00Z cùng ngày
```

Trong Java, `Instant` phù hợp để biểu diễn một thời điểm tuyệt đối. Múi giờ cần được xử lý khi nhận lịch địa phương hoặc hiển thị cho người dùng.

Không để việc đổi timezone của trình duyệt hoặc profile cá nhân tự làm thay đổi khoảng được policy cấp.

### 10.2. Lịch lặp cần thêm quy tắc

Một lịch “08:00 đến 17:00 theo giờ địa phương” cần xác định vùng thời gian và lịch áp dụng. Ca 22:00 đến 06:00 đi qua ngày kế tiếp; nhiều ca trong ngày tạo các khoảng rời nhau.

Ở vùng có thay đổi giờ theo mùa, một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần. Policy và lớp chuyển đổi phải có cách xử lý rõ; không để lựa chọn mặc định của một thư viện vô tình quyết định ai có quyền.

Có thể chuyển từng lần xuất hiện thành các khoảng thời điểm xác định theo phiên bản lịch cần dùng. Cần lưu đủ ngữ cảnh để giải thích activation đã được giới hạn theo lịch nào.

### 10.3. Chọn nguồn thời gian và khả năng kiểm thử

Không dùng giờ do client gửi làm nguồn quyết định hiệu lực. Các node cần nguồn thời gian và quy tắc độ lệch phù hợp yêu cầu; những bất thường đồng hồ cần có khả năng quan sát.

Thời gian đo độ trễ trong một tiến trình và thời điểm lịch có mục đích khác nhau. Một bộ đếm elapsed không tự biểu diễn được mốc hết hạn dùng chung qua nhiều dịch vụ.

Trong mã, nên truyền một clock hoặc cổng thời gian để test có thể điều khiển mốc bắt đầu, sát hạn và sau hạn. Đồng hồ giả là công cụ kiểm thử, không phải một trường đầu vào công khai cho người gọi chọn giờ họ muốn.

## 11. Audit và phản hồi cho người dùng

Lịch sử cần cho biết:

- Ai được gán role, ai kích hoạt và trong tenant nào.
- Activation gắn với phiên hoặc ngữ cảnh nào.
- Khoảng đề nghị và khoảng thực sự được cấp.
- AssignmentVersion, policyVersion và căn cứ bổ sung có liên quan.
- Ai gia hạn, thu hồi hoặc tắt activation.
- Lệnh nhạy cảm đã dùng activation nào và tại mốc đánh giá nào.

Không ghi nguyên token, cookie phiên hoặc khóa bí mật. Nếu cần liên kết phiên trong audit, dùng tham chiếu không phải thông tin xác thực có thể bị dùng lại.

Sự kiện hết hạn do job ghi muộn cần phân biệt mốc hiệu lực kết thúc với mốc hệ thống ghi nhận sự kiện. Không diễn giải rằng quyền vẫn hợp lệ đến lúc job chạy.

Giao diện có thể hiển thị role đang dùng, countdown và nút xin kích hoạt lại. Countdown hỗ trợ trải nghiệm, còn máy chủ vẫn kiểm tra trên mỗi hành động cần quyền.

Khi role hết hạn, phản hồi nên chỉ rõ cần kích hoạt lại hoặc xác thực phù hợp nếu người gọi được biết. Không tự gửi lại một quyết định nhạy cảm sau khi người dùng kích hoạt lại mà bỏ qua việc họ cần xác nhận nội dung đã thay đổi.

Thành công trong quá khứ không nên bị hiển thị thành thất bại chỉ vì role hiện đã hết hạn. Cần phân biệt kết quả lệnh đã commit, trạng thái quyền hiện tại và quyền thực hiện lệnh mới.

## 12. Kiểm thử khoảng kích hoạt vai trò

### 12.1. Kiểm thử các biên thời gian

Với khoảng `[10:15, 10:30)` theo quy ước đã chọn:

| Thời điểm đánh giá | Kết quả đối với điều kiện thời gian |
|---|---|
| Trước 10:15 | Chưa được dùng |
| Đúng 10:15 | Có thể dùng nếu các điều kiện khác đạt |
| Giữa khoảng | Có thể dùng nếu các điều kiện khác đạt |
| Ngay trước 10:30 theo độ phân giải được hỗ trợ | Vẫn trong khoảng |
| Đúng 10:30 | Không còn cho phép lần dùng mới |
| Sau 10:30 dù status còn ACTIVE | Không còn cho phép lần dùng mới |

Kiểm thử độ phân giải cần phù hợp cách lưu và so sánh thời gian giữa ứng dụng với cơ sở dữ liệu. Tránh test dùng một độ chính xác mà tầng lưu trữ không giữ được.

Với nhiều boundary, lần lượt cho từng lớp kết thúc sớm nhất để kiểm tra hệ thống lấy đúng giới hạn. Cần có cả các khoảng không giao nhau và các khoảng chỉ chạm tại một mốc.

### 12.2. Ma trận tình huống lạm dụng

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Có assignment nhưng chưa có activation bắt buộc | Không dùng quyền của role |
| Activation còn hạn nhưng assignment đã hết | Bị giới hạn bởi assignment |
| Token còn hạn nhưng activation đã hết | Không dùng tên role cũ để tiếp tục |
| Activation còn hạn nhưng token hoặc phiên không được chấp nhận | Không cho phép bằng activation riêng lẻ |
| Client gửi expiresAt xa hơn mốc được cấp | Không mở rộng quyền |
| Client sửa giờ máy hoặc header thời gian | Không thay đổi nguồn thời gian có thẩm quyền |
| Dùng activation của subject hoặc tenant khác | Từ chối theo binding |
| Dùng activation của phiên S1 ở S2 | Áp dụng đúng giới hạn theo phiên đã định nghĩa |
| Gọi refresh sau khi activation hết | Không tự kích hoạt lại role đặc quyền |
| Retry cùng lệnh kích hoạt | Trả cùng activation và khoảng đã cấp, không cộng thời lượng |
| Hai lệnh gia hạn cùng lúc | Không vượt trần hoặc ghi đè thu hồi |
| Hai role xung đột được kích hoạt đồng thời | Chỉ chấp nhận tổ hợp mà policy cho phép |
| Người lập tắt role rồi bật role duyệt | Lịch sử phân tách nhiệm vụ trên giao dịch vẫn được kiểm tra |
| Cache ALLOW tồn tại sau effectiveEnd | Không tiếp tục dùng như quyền còn hiệu lực |
| Job nền đến sau mốc bắt buộc phải còn quyền | Dừng hoặc xin cấp phép lại theo hợp đồng |
| Batch kéo dài qua hạn | Giữ đúng ngữ nghĩa mỗi hành động hoặc phạm vi batch đã được cấp |
| Một role đặc quyền hết hạn nhưng role thường còn hợp lệ | Không khóa nhầm quyền không liên quan |
| Không tải được dữ liệu activation hoặc policy cần thiết | Không mặc định quyền vô hạn |
| Lịch có khoảng nghỉ giữa ca | Không gộp thành một khoảng dài bao trùm cả giờ nghỉ |
| Activation bị thu hồi trước hạn | Cơ chế kiểm chứng đáp ứng đúng bảo đảm thu hồi đã công bố |

### 12.3. Cạnh tranh và điểm chèn lỗi

Các ca tích hợp có giá trị:

1. Request đến trước hạn nhưng chỉ lấy được khóa sau hạn.
2. Thu hồi activation đồng thời với lệnh nhạy cảm.
3. Thu hồi assignment đồng thời với một lần kích hoạt mới.
4. Gia hạn đồng thời với thu hồi.
5. Hai lệnh kích hoạt role xung đột trong cùng phạm vi kiểm soát.
6. Lỗi sau lưu activation nhưng trước ghi audit hoặc kết quả idempotency.
7. Commit thành công rồi mất phản hồi kích hoạt.
8. Cache chưa nhận thông báo thu hồi.
9. Worker chờ qua deadline rồi mới tới điểm thực thi.

Với mỗi trường hợp, phải xác định thứ tự hoặc mốc nào quyết định kết quả. Nếu chính sách chỉ bảo đảm quyền tại mốc chấp nhận cục bộ, test không nên giả định nó đã bảo đảm tới mọi tác dụng bên ngoài.

Dùng cơ sở dữ liệu và cơ chế phối hợp có đặc tính phù hợp môi trường triển khai khi kiểm thử khóa và transaction. Hàm `contains` đúng không chứng minh toàn bộ luồng thu hồi đồng thời đúng.

### 12.4. Kiểm tra điều không được xảy ra khi bị chặn

Với một lần sử dụng mới không đủ quyền thời gian:

```text
không ghi quyết định phê duyệt thành công
không thay trạng thái nghiệp vụ dở dang
không tạo execution hoặc outbox được chấp nhận trái quyền
không gia hạn activation như tác dụng phụ của request
không cấp lại assignment đã hết hoặc bị thu hồi
không chuyển sang tài khoản kỹ thuật để bỏ qua điều kiện
không ghi audit thành công giả
không xóa quyết định hợp lệ đã tồn tại từ trước
```

Lần từ chối có thể được ghi vào luồng quan sát phù hợp. Nếu transaction rollback, dấu vết thành công tương ứng không được tồn tại như một kết quả đã commit.

Với lệnh kích hoạt thất bại, kiểm tra không có activation hiệu lực mới và không có quyền bị mở ở các phiên khác.

### 12.5. Kiểm thử bằng clock điều khiển được

Tách các kiểm thử theo mục đích:

- Kiểm thử khoảng: đầu, cuối, không giao và nhiều boundary.
- Kiểm thử binding: đúng người, tenant, role, assignment và session.
- Kiểm thử policy: thời lượng tối đa, điều kiện bổ sung và role xung đột.
- Kiểm thử tích hợp: khóa, commit, thu hồi, token và cache.
- Kiểm thử execution: hàng đợi, deadline, retry và kết quả chưa rõ.

Không dùng chờ thật nhiều phút để kiểm tra một mốc hết hạn đơn giản. Clock điều khiển được giúp test ổn định, còn các kiểm thử tích hợp vẫn cần xác nhận adapter và nguồn thời gian thực tế tuân thủ ngữ nghĩa đã chọn.

## 13. Bài tập áp dụng

Thiết kế vai trò phê duyệt chỉ được dùng sau khi kích hoạt trong một phiên cụ thể.

1. Phân biệt assignment, activation, phiên, token và deadline của execution.
2. Chọn quy ước đầu khoảng, cuối khoảng và nguồn thời gian có thẩm quyền.
3. Tính khoảng hiệu lực khi mỗi boundary có một mốc kết thúc khác nhau.
4. Thiết kế lệnh kích hoạt, gia hạn và thu hồi; xác định dữ liệu nào máy chủ phải tự quyết định.
5. Mô tả cách xử lý hai role xung đột và việc đổi role để thử tự duyệt.
6. Định nghĩa mốc kiểm tra khi request chờ khóa và khi worker xử lý muộn.
7. Chỉ ra cách token refresh, cache và phiên khác chịu ảnh hưởng của activation.
8. Chọn transaction, version và dữ liệu audit để giải thích một lần dùng quyền.
9. Viết ca kiểm thử đúng mốc expiresAt, retry sau mất phản hồi và gia hạn đồng thời với thu hồi.

Một khoảng kích hoạt có ý nghĩa khi hệ thống giữ được giới hạn đó từ lúc cấp tới đúng điểm sử dụng mà chính sách quy định. Thời hạn cần gắn với đúng chủ thể, phiên và vai trò, đồng thời tiếp tục chịu mọi ràng buộc về đối tượng, trạng thái, phân tách nhiệm vụ và tính nhất quán của hành động nghiệp vụ.
