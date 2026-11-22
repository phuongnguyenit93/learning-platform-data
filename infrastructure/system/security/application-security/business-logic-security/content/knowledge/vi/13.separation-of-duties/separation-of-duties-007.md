# Duty separation testing: kiểm thử phân tách nhiệm vụ

## 1. Kiểm thử phải chứng minh điều gì?

Một hệ thống có hai role `REQUESTER` và `APPROVER`, có nút duyệt riêng và có kiểm thử rằng người có role duyệt gọi API thành công. Những điều đó chưa chứng minh hệ thống đã phân tách nhiệm vụ.

Người lập vẫn có thể tự duyệt qua tài khoản phụ, dùng ngữ cảnh ủy quyền, thay owner trước khi duyệt, gửi batch chứa hồ sơ của mình hoặc đi qua endpoint quản trị không chạy cùng policy. Hai request đồng thời cũng có thể vượt qua một điều kiện mà kiểm thử tuần tự luôn thấy đúng.

**Duty separation testing** là việc kiểm chứng rằng các nhiệm vụ xung đột không được thực hiện hoặc được tính cho cùng chủ thể, trong đúng phạm vi mà chính sách yêu cầu, qua mọi đường thực thi liên quan.

Trong bảo vệ logic nghiệp vụ, kiểm thử cần quan sát cả:

- Quyết định cho phép hoặc từ chối.
- Trạng thái và căn cứ nghiệp vụ sau lệnh.
- Danh tính thực tế được ghi nhận và được tính vào quorum.
- Tác động như phiếu duyệt, sự kiện cho phép thực thi hoặc operation chi trả.
- Tính đúng đắn khi có gửi lại, thay đổi quyền và xử lý đồng thời.

Một response lỗi không đủ chứng minh thao tác bị chặn. Ngược lại, một hệ thống từ chối mọi người cũng không đạt yêu cầu: người độc lập và đủ quyền vẫn phải hoàn thành quy trình hợp lệ.

## 2. Chuyển chính sách thành bất biến có thể kiểm tra

Không bắt đầu bằng câu hỏi “đã gọi hàm `checkSeparation` chưa?”. Hãy bắt đầu từ điều kiện nghiệp vụ mà hệ thống phải giữ.

### 2.1. Chính sách minh họa của bài

Xét một quy trình đề nghị chi trả nội bộ với các quy tắc sau:

| Mã | Quy tắc |
|---|---|
| `SOD-01` | Người khởi xướng và người sửa căn cứ trọng yếu không được duyệt chính căn cứ đó |
| `SOD-02` | Hồ sơ cần một người duyệt ngân sách và một người duyệt tài chính; hai người phải khác danh tính và đều độc lập với bên lập |
| `SOD-03` | Trong cùng tenant, một người không được đồng thời nắm quyền hiệu lực của hai vai trò quản trị xung đột `POLICY_EDITOR` và `EXCEPTION_AUTHORIZER` |
| `SOD-04` | Nếu dùng cấu hình kiểm soát thực thi chặt, người phát lệnh chi trả còn phải khác những người duyệt được tính |
| `SOD-05` | Tài khoản phụ, service tạo hộ và ủy quyền không được che quan hệ danh tính làm phát sinh xung đột |
| `SOD-06` | Chỉ quyết định đúng basis và vòng duyệt hiện tại được dùng để kết luận đủ điều kiện |
| `SOD-07` | Mọi đường ghi quyết định phải giữ cùng các bất biến; dữ liệu client không được tự sửa nguồn gốc |

Các quy tắc trên là ví dụ để thiết kế kiểm thử. `SOD-04` là một cấu hình bổ sung, không phải hệ quả bắt buộc của mọi quy trình maker–checker.

Phân biệt rõ hai phạm vi kiểm tra:

- **Ở lúc cấp quyền:** một danh tính không được nhận tổ hợp quyền xung đột mà chính sách cấm.
- **Ở lúc thực hiện nhiệm vụ:** một người có thể giữ quyền tạo và duyệt, nhưng không được duyệt hồ sơ do mình lập.

Nếu hệ thống còn giới hạn các role được kích hoạt trong cùng phiên, cần kiểm thử giới hạn đó riêng. Không coi việc đổi phiên đăng nhập là đã xóa lịch sử tham gia một hồ sơ.

### 2.2. Viết bất biến độc lập với code sản phẩm

Với một căn cứ duyệt `b`, gọi:

```text
M(b): tập danh tính bị loại do tham gia lập căn cứ b
R(d): các danh tính phải xét của bên thực hiện quyết định d

quyết định độc lập khi:
    M(b) giao R(d) là tập rỗng
```

Với tập phiếu được tính vào quorum:

```text
mọi phiếu đều đúng tenant, basis và vòng duyệt
AND mọi người duyệt đều độc lập với bên lập
AND đủ người khác danh tính
AND đủ vai trò theo chính sách
```

“Đủ vai trò” phải gắn với những người độc lập. Một người giữ cả hai role không được dùng làm cả hai người duyệt khi policy yêu cầu hai người.

Kỳ vọng trong test nên được suy ra từ các quy tắc này hoặc bảng tình huống đã được thống nhất. Không gọi chính hàm phân quyền đang được kiểm thử để tính `expectedAllowed`, vì test có thể lặp lại nguyên lỗi của implementation.

## 3. Thiết kế fixture có khả năng bộc lộ đường vòng

Fixture chỉ có một requester và một approver thường bỏ sót vấn đề danh tính. Cần tạo dữ liệu mà account, người, role và phạm vi không trùng nhau một cách quá thuận tiện.

### 3.1. Bộ chủ thể minh họa

| Chủ thể | Tài khoản | Danh tính người | Quyền/phạm vi đáng chú ý |
|---|---|---|---|
| An | `an-main` | `person-A` | Có quyền lập và quyền duyệt ngân sách trong tenant T1 |
| An qua tài khoản khác | `an-admin` | `person-A` | Có quyền quản trị hoặc duyệt nhưng vẫn là cùng người |
| Bình | `binh-budget` | `person-B` | Duyệt ngân sách trong phạm vi của hồ sơ |
| Tài khoản khác của Bình | `binh-finance` | `person-B` | Duyệt tài chính, dùng để thử đếm một người hai lần |
| Chi | `chi-finance` | `person-C` | Duyệt tài chính, độc lập với An và Bình |
| Dũng | `dung-other-dept` | `person-D` | Có role duyệt nhưng ngoài phòng ban được phép |
| Người ở tenant khác | `reviewer-t2` | `person-X` | Có quyền tương tự nhưng chỉ trong T2 |
| Service tạo hộ | `request-service` | Không tự giả thành người duyệt | Ngữ cảnh khởi xướng được xác minh có thể là An |

Thêm ít nhất một tài khoản không phân giải được danh tính người khi chính sách bắt buộc phải biết danh tính đó. Test phải xác nhận hệ thống không coi thiếu dữ liệu là “không trùng với maker”.

### 3.2. Bộ hồ sơ cần có

- `P-A`: An khởi xướng, basis `B1`, vòng `R1`, đang chờ duyệt.
- `P-B`: Bình khởi xướng, để chứng minh An vẫn có thể duyệt hồ sơ của người khác nếu đủ điều kiện.
- Một hồ sơ ngoài phòng ban và một hồ sơ ở T2.
- Một hồ sơ do service tạo hộ An, có nguồn khởi xướng đã xác minh.
- Một hồ sơ có basis mới sau khi người khác sửa số tiền hoặc người nhận.
- Một hồ sơ đã kết thúc và một vòng duyệt cũ có phiếu lịch sử.

Không dùng dữ liệu cá nhân thật chỉ để tạo fixture. Quan trọng là quan hệ giữa các định danh và thuộc tính, không phải tên giống môi trường thật.

### 3.3. Thiết lập qua đường tin cậy

Ở unit test, có thể dựng ngữ cảnh danh tính trực tiếp để cô lập policy. Ở integration/API test, cần thêm kiểm thử đường xác thực và ánh xạ thực sự được ứng dụng dùng.

Nếu harness luôn chèn sẵn `personIdentityId` đúng rồi bỏ qua toàn bộ middleware, test không chứng minh được ứng dụng có chống giả mạo trường hoặc header danh tính hay không.

Fixture nên ghi rõ nguồn tạo dữ liệu: qua API nghiệp vụ, qua thành phần cấp danh tính hay qua seed kiểm thử. Những dữ liệu không thể tồn tại hợp lệ trong hệ thống cần được đánh dấu là trường hợp cố ý kiểm tra lỗi hoặc dữ liệu hỏng.

## 4. Ma trận cho phép và từ chối

### 4.1. Cô lập từng nguyên nhân

Một test tự duyệt tốt phải cho người lập đủ role, hạn mức, trạng thái và phạm vi; chỉ còn điều kiện độc lập là không đạt. Nếu người lập vốn không có role duyệt, response từ chối không chứng minh `SOD-01` đang hoạt động.

Tương tự, khi thử sai tenant, hãy tránh dùng token đã hết hạn khiến request bị chặn từ lớp xác thực trước khi tới kiểm tra phạm vi.

| Trường hợp | Điều kiện được giữ hợp lệ | Điều kiện cố ý vi phạm | Kỳ vọng |
|---|---|---|---|
| An duyệt `P-A` | Role, hạn mức, trạng thái, tenant | Là người lập | Từ chối; không có phiếu được tính |
| `an-admin` duyệt `P-A` | Quyền hành động và phạm vi | Cùng danh tính maker | Từ chối theo cùng quy tắc |
| Bình duyệt ngân sách `P-A` | Tất cả điều kiện của phiếu đầu | Chưa đủ phiếu tài chính | Nhận phiếu, hồ sơ chưa được kết luận đủ duyệt |
| Chi duyệt tài chính sau Bình | Đủ căn cứ và quyền | Không có vi phạm | Đạt quorum của ví dụ |
| `binh-finance` làm phiếu thứ hai | Đúng role tài chính | Cùng người với phiếu đầu | Không tăng số người độc lập |
| Dũng duyệt `P-A` | Khác maker, có role | Ngoài phòng ban | Từ chối vì phạm vi |
| Người T2 duyệt `P-A` | Khác maker, role tương tự | Sai tenant | Không truy cập/duyệt được |
| An duyệt ngân sách `P-B` | Đủ quyền và độc lập với maker | Không có vi phạm | Được nhận phiếu nếu các điều kiện khác đạt |

### 4.2. Kiểm tra kết quả theo hợp đồng, không chỉ một mã HTTP

Ứng dụng có thể dùng `403` cho vi phạm độc lập, `409` cho phiếu trùng hoặc version cũ, và `404` để che sự tồn tại của hồ sơ ngoài phạm vi. Cần chọn hợp đồng cụ thể và kiểm thử nhất quán.

Không nên cho test chấp nhận mọi lỗi bất kỳ. Một `500` do null pointer không chứng minh tính độc lập đã được bảo vệ đúng cách. Tuy nhiên, khi mô phỏng dịch vụ policy không khả dụng, một lỗi dịch vụ có thể là phản hồi đúng miễn không có quyết định nghiệp vụ trái phép.

## 5. Kiểm thử phân tách khi cấp và kích hoạt quyền

### 5.1. Xét quyền hiệu lực, không chỉ role gán trực tiếp

Với `SOD-03`, cần thử:

- Cấp `EXCEPTION_AUTHORIZER` cho người đã có `POLICY_EDITOR` trực tiếp.
- Một role được kế thừa từ group hoặc role cấp cao hơn.
- Hai tài khoản cùng người giữ mỗi tài khoản một role xung đột.
- Cấp role qua batch, import hoặc công cụ quản trị.
- Sửa quan hệ group khiến một người đột nhiên có cả hai quyền hiệu lực.
- Thu hồi một role rồi cấp role còn lại qua luồng hợp lệ.

Một kiểm tra chỉ nhìn bảng gán role trực tiếp có thể bỏ sót quyền kế thừa. Nếu policy áp dụng ở cấp người trong tenant, hai account khác nhau không được tách khỏi phép kiểm tra tổng hợp đó.

### 5.2. Phạm vi phải đúng

Nếu quy tắc xung đột chỉ áp dụng trong cùng tenant, cần có positive test cho hai vai trò thuộc hai tenant khác nhau khi nghiệp vụ cho phép. Nếu quy tắc áp dụng toàn tổ chức, test phải chứng minh đổi tenant không làm mất xung đột.

Không biến một quy tắc theo hồ sơ thành lệnh cấm toàn cục. An có thể bị cấm duyệt `P-A` nhưng vẫn được duyệt `P-B`; test cần giữ được sự khác biệt đó.

### 5.3. Phiên đăng nhập không xóa lịch sử nhiệm vụ

Nếu có cơ chế kích hoạt role theo phiên, kiểm thử việc kích hoạt hai role xung đột trong cùng phiên theo hợp đồng. Đồng thời kiểm thử rằng đăng xuất, tạo phiên mới hoặc đổi thiết bị không cho maker duyệt hồ sơ cũ khi quy tắc dựa trên lịch sử đối tượng.

Tách vai trò đang hoạt động và tách nhiệm vụ theo hồ sơ là hai điều kiện khác nhau; vượt qua điều kiện thứ nhất không chứng minh đã thỏa mãn điều kiện thứ hai.

## 6. Kiểm thử lúc thực hiện nhiệm vụ và các đường ghi thay thế

### 6.1. Danh tính và đại diện

Các tình huống cần làm rõ gồm:

- Maker dùng tài khoản phụ có đủ role để duyệt.
- Maker dùng ngữ cảnh đại diện cho người khác.
- Người khác duyệt thay một bên có xung đột, theo cách policy quy định phải xét cả hai danh tính.
- Người dùng khởi xướng qua service rồi chính người đó duyệt.
- Service thiếu nguồn khởi xướng bắt buộc nhưng tập maker lại được trả rỗng.
- Chế độ hỗ trợ/impersonation che mất danh tính thao tác thật.
- Header hoặc body giả `actorId`, `onBehalfOf`, `createdBy` hoặc `approvedBy`.

Kỳ vọng phụ thuộc quy tắc đại diện đã công bố. Test cần chứng minh không thể dùng dữ liệu tự khai để thay tập danh tính mà policy phải xét.

### 6.2. Kiểm tra mọi bề mặt có thể ghi quyết định

Lập danh sách các đường nghiệp vụ thực sự tồn tại:

| Đường thực thi | Điều cần kiểm chứng |
|---|---|
| Endpoint duyệt chuyên biệt | Chạy đủ kiểm tra quyền, độc lập, basis và trạng thái |
| Endpoint sửa tổng quát | Không cho gán trực tiếp trạng thái hoặc người duyệt để vượt lệnh nghiệp vụ |
| Batch | Xét từng đối tượng; không chỉ xét role hoặc hồ sơ đầu tiên |
| Import quyết định | Xác minh nguồn và danh tính; không mặc định tin mọi dòng nhập |
| Công cụ quản trị | Không có đường bỏ qua policy ngoài ngoại lệ được thiết kế |
| Worker/service | Quyền hẹp và nguồn gốc đúng; không giả thành người duyệt độc lập |

Không cần dựng endpoint không tồn tại chỉ để hoàn thành một checklist. Mục tiêu là bao phủ toàn bộ đường ghi đang có và thêm kiểm thử khi xuất hiện đường mới.

### 6.3. Batch cần kết quả phù hợp từng phần tử

Tạo batch gồm hồ sơ hợp lệ của đồng nghiệp, hồ sơ do chính người gọi lập và hồ sơ ngoài phạm vi. Với chế độ toàn bộ hoặc không phần nào, không được commit quyết định cho phần tử nào nếu hợp đồng yêu cầu rollback toàn batch.

Với chế độ kết quả từng phần, mỗi phần tử cần outcome, transaction và idempotency phù hợp. Không được trả một kết quả chung “thành công” che việc có phần tử bị tự duyệt hoặc bỏ qua kiểm tra.

## 7. Kiểm thử căn cứ, lịch sử và quorum

### 7.1. Nguồn gốc không bị xóa bởi đổi owner

Chuỗi `create → transferOwner → approveAsCreator` phải tiếp tục bị chặn nếu chính sách giữ người khởi xướng trong tập maker. Test cần kiểm tra cả nguồn gốc được lưu và tác động của lệnh duyệt, không chỉ xem trường owner sau cùng.

Nếu clone/import tiếp tục cùng một nghĩa vụ, kiểm thử việc giữ nguồn gốc theo quy tắc của hệ thống. Nếu là đề nghị mới thật sự, kỳ vọng phải dựa vào định nghĩa maker của đề nghị mới; không tự áp dụng một quy tắc kế thừa vô hạn.

### 7.2. Người sửa căn cứ trọng yếu

Tạo hồ sơ của An, cho Bình sửa tài khoản nhận tiền rồi Bình duyệt. Theo `SOD-01` của ví dụ, Bình đã trở thành maker của căn cứ mới và phải bị loại.

Thêm một positive test: Bình chỉ thêm bình luận không ảnh hưởng căn cứ rồi duyệt, nếu policy cho phép. Test này ngăn implementation đơn giản hóa quá mức thành “ai từng chạm vào hồ sơ đều không được duyệt”.

### 7.3. Không trộn quyết định của các vòng

Tạo một phiếu ở basis `B1`, đổi nội dung sang `B2` và mở vòng mới. Phiếu cũ vẫn tồn tại trong lịch sử nhưng không được tính cho quorum của `B2` khi policy không cho kế thừa.

Thử các tổ hợp:

```text
Bình duyệt ngân sách B1 + Chi duyệt tài chính B2
hai phiếu cùng người ở hai role
hai người khác nhau nhưng cùng một role
phiếu đã bị thay thế + phiếu hiện tại
phiếu hợp lệ + phiếu của maker
```

Không tổ hợp nào được tự đạt quorum chỉ vì có hai hàng dữ liệu mang giá trị `APPROVE`.

### 7.4. Positive test cho quorum hợp lệ

Cho Bình duyệt ngân sách và Chi duyệt tài chính trên cùng basis/vòng, với quyền và bằng chứng hợp lệ. Hệ thống phải tiến tới kết quả duyệt theo hợp đồng.

Kiểm tra cả việc chưa hoàn tất sau phiếu đầu và hoàn tất sau phiếu thứ hai. Điều này phát hiện lỗi đánh dấu đã duyệt quá sớm, cũng như lỗi luôn chặn do kiểm tra độc lập quá rộng.

## 8. Chọn tầng kiểm thử và viết assertion có ý nghĩa

| Tầng | Phù hợp để chứng minh | Giới hạn |
|---|---|---|
| Unit policy | Tổ hợp danh tính, role, quan hệ maker và scope | Không chứng minh đường API thực sự gọi policy |
| Application service | Thứ tự nghiệp vụ, phối hợp repository, lỗi và quyết định | Mock có thể che transaction/constraint thực tế |
| Integration với cơ sở dữ liệu | Ràng buộc, rollback, khóa, version, cạnh tranh | Chưa chứng minh đầy đủ xác thực đầu vào |
| API | Danh tính, tenant, DTO, đường ghi và nội dung response | Không thay mọi kiểm thử cạnh tranh có điều khiển |
| Luồng đầu cuối chọn lọc | Tính liền mạch của tạo–duyệt–thực thi | Chậm và khó chẩn đoán nếu dùng cho mọi tổ hợp |

Chọn tầng theo điều cần chứng minh. Không cần lặp toàn bộ ma trận ở mọi tầng; ưu tiên unit cho tổ hợp thuần, integration cho tính nguyên tử và API cho ranh giới tin cậy.

### 8.1. Ví dụ Java: maker bị chặn dù đủ quyền nền

Mã sau minh họa phong cách kiểm thử với assertion dạng JUnit. `fixtures`, `api` và `probe` là test harness của ứng dụng, không phải API của thư viện có sẵn.

```java
@Test
void creatorCannotApproveOwnBasisEvenWithApprovalRole() {
    Scenario s = fixtures.inReview(
            "person-A", "REQUESTER", "BUDGET_REVIEWER");

    BusinessProjection before = probe.businessProjection(s.requestId());
    Set<DecisionId> decisionsBefore = probe.acceptedDecisionIds(s.roundId());
    Set<OperationId> operationsBefore = probe.paymentOperationIds(s.requestId());

    ApiResponse response = api.as(s.creator()).approve(
            s.requestId(),
            new ApprovalInput(s.version(), s.basisId(), "BUDGET"));

    assertEquals(403, response.status());
    assertEquals("SELF_APPROVAL_NOT_ALLOWED", response.errorCode());
    assertEquals(before, probe.businessProjection(s.requestId()));
    assertEquals(decisionsBefore, probe.acceptedDecisionIds(s.roundId()));
    assertEquals(operationsBefore, probe.paymentOperationIds(s.requestId()));
    assertFalse(probe.hasNewApprovalGrantedEvent(response.correlationId()));
}
```

`BusinessProjection` chỉ chứa dữ liệu nghiệp vụ cần bất biến, như state, basis và kết quả duyệt. Không so toàn bộ cơ sở dữ liệu trước/sau, vì audit từ chối hoặc bộ đếm vận hành có thể được ghi hợp lệ.

Test này cố ý cấp quyền duyệt cho creator. Nếu bỏ role đó khỏi fixture, test có thể vẫn xanh dù kiểm tra tự duyệt đã bị xóa.

### 8.2. Ví dụ Java: hai người hợp lệ hoàn thành quorum

```java
@Test
void twoIndependentReviewersCanCompleteRequiredRoles() {
    Scenario s = fixtures.requestByAnWithIndependentReviewers();

    ApiResponse first = api.as(s.binhBudget()).approve(
            s.requestId(),
            new ApprovalInput(s.version(), s.basisId(), "BUDGET"));

    assertEquals(200, first.status());
    assertEquals("IN_REVIEW", first.state());
    assertEquals(1, probe.distinctAcceptedReviewerCount(s.roundId()));

    ApiResponse second = api.as(s.chiFinance()).approve(
            s.requestId(),
            new ApprovalInput(first.version(), s.basisId(), "FINANCE"));

    assertEquals(200, second.status());
    assertEquals("APPROVED", second.state());
    assertEquals(2, probe.distinctAcceptedReviewerCount(s.roundId()));
    assertEquals(s.basisId(), probe.approvedBasisId(s.requestId()));
}
```

Ví dụ chọn hợp đồng trả `200` cho cả phiếu trung gian và kết quả đủ duyệt. Tên bước trong lệnh biểu thị ý định; server vẫn phải xác minh người gọi có quyền ở bước đó, không tin role do client tự chọn.

Thêm biến thể thay `s.chiFinance()` bằng tài khoản tài chính của Bình. Sau khi xử lý theo hợp đồng phiếu trùng/xung đột của ứng dụng, số người được tính vẫn phải là một và hồ sơ chưa được đánh dấu đủ quorum.

### 8.3. Quan sát ở ranh giới tác động

Dùng cơ sở dữ liệu để kiểm tra quyết định đã commit và dùng fake/spy ở cổng phát tác động khi cần. Không chỉ assert hàm validator được gọi một lần; một đường khác có thể vẫn phát sự kiện hoặc cập nhật trạng thái trái phép.

Với thông điệp có thể được gửi lại, phân biệt số lần gửi vật lý với số tác động nghiệp vụ. Nhiều lần truyền cùng operation có thể hợp lệ trong cơ chế phát ít nhất một lần; điều cần giữ là không có nghĩa vụ hoặc khoản chi trùng ngoài ý muốn.

## 9. Kiểm thử cạnh tranh bằng lịch chạy có điều khiển

Gửi một nghìn request ngẫu nhiên mà không thấy lỗi không chứng minh các interleaving nguy hiểm đã xảy ra. Cần điều khiển thời điểm đọc, kiểm tra và commit.

### 9.1. Hai tài khoản cùng người gửi hai phiếu

Cho hai transaction, mỗi transaction dùng một account của Bình và chọn một vai trò khác nhau:

```text
T1: đọc vòng R1 và kiểm tra chưa có phiếu của person-B
T2: đọc vòng R1 và kiểm tra chưa có phiếu của person-B
T1: ghi phiếu ngân sách
T2: ghi phiếu tài chính
```

Bất biến: không được có hai phiếu cùng danh tính được tính thành hai người. Tùy cơ chế version/khóa/constraint, một transaction có thể phải chờ hoặc thất bại; sau đó gửi lại cũng không được tăng số người độc lập.

Nếu transaction thứ hai bị lỗi version trước khi chạm điều kiện trùng danh tính, cần thêm lần gửi lại với version mới để chứng minh policy danh tính vẫn chặn. Nếu không, test chỉ chứng minh kiểm soát version.

### 9.2. Hai giao dịch cấp role xung đột

Ví dụ mỗi giao dịch nhìn thấy người dùng chưa có role đối nghịch:

```text
T1: kiểm tra không có EXCEPTION_AUTHORIZER
T2: kiểm tra không có POLICY_EDITOR
T1: cấp POLICY_EDITOR
T2: cấp EXCEPTION_AUTHORIZER
```

Hai hàng role khác nhau có thể không vi phạm constraint duy nhất thông thường. Đây là trường hợp cần kiểm chứng cơ chế bảo vệ bất biến tổng hợp, không chỉ khóa một hàng gán role chưa tồn tại.

Sau khi cả hai transaction kết thúc, không được tồn tại đồng thời hai quyền hiệu lực bị cấm. Ít nhất một lần cấp phải bị từ chối/rollback hoặc được giải quyết theo giao thức đã thiết kế trước khi hệ thống cho dùng tổ hợp đó.

### 9.3. Sửa căn cứ trong lúc duyệt

Chặn transaction duyệt sau khi đọc maker/basis, rồi cho một transaction khác sửa người nhận hoặc số tiền. Sau khi giải phóng điểm chặn, hệ thống phải không duyệt căn cứ mới dựa trên dữ liệu maker cũ.

Kiểm tra các đường sửa bảng con. Khóa hàng request không đủ nếu dòng hàng hoặc sổ người đóng góp có thể đổi mà không tham gia cùng giao thức khóa/version.

### 9.4. Không áp một kỳ vọng cho mọi mô hình quorum

Với hai người độc lập cùng gửi phiếu hợp lệ, có hệ thống nhận được cả hai sau khi tuần tự hóa; có hệ thống buộc request dùng version cũ nhận xung đột rồi người dùng gửi lại. Cả hai có thể phù hợp hợp đồng.

Không viết assertion “mọi hai request đồng thời chỉ được một request thành công” cho toàn bộ quy trình. Điều cần giữ là không mất phiếu hợp lệ đã commit, không tính người trùng và không kết luận đủ duyệt sai.

### 9.5. Cách đồng bộ test

Dùng barrier, latch hoặc hook kiểm thử ở ranh giới thích hợp, hai kết nối/transaction riêng và timeout hữu hạn. Không dùng `sleep` tùy ý làm bằng chứng về thứ tự.

Khi có khóa, tránh dựng barrier yêu cầu transaction đang bị khóa phải tới được điểm mà nó không thể tới. Test cần hiểu cơ chế dự kiến để không tạo deadlock do chính harness.

## 10. Transaction, idempotency và các điểm lỗi

### 10.1. Quyết định không được commit một phần

Chèn lỗi có kiểm soát sau khi ghi phiếu nhưng trước cập nhật quorum, sau cập nhật trạng thái nhưng trước audit/outbox bắt buộc, và ngay trước commit.

Kiểm tra rollback của các ghi cần nguyên tử. Không được có hồ sơ `APPROVED` nhưng thiếu một quyết định bắt buộc, hoặc có sự kiện cho phép chi trả trong khi transaction duyệt đã rollback.

Các log từ chối có thể được lưu ngoài transaction nghiệp vụ theo thiết kế; chúng không phải tác động phê duyệt trái phép.

### 10.2. Mất response sau commit

Cho lệnh duyệt commit rồi mô phỏng mất response. Client gửi lại cùng key và nội dung. Kỳ vọng là trả kết quả theo hợp đồng, không thêm phiếu và không phát sinh một ý định thực thi mới.

Tiếp tục thử:

- Cùng key nhưng khác basis, bước hoặc nội dung có ý nghĩa.
- Cùng chuỗi key ở tenant hoặc chủ thể khác.
- Khác key nhưng cùng danh tính và vòng duyệt.
- Replay sau khi quyền xem/nhận kết quả đã bị thu hồi.

Nhánh replay phải kiểm tra quyền nhận kết quả hiện tại theo chính sách, nhưng không thực hiện lại transition như một lệnh mới. Nếu nguồn trạng thái đã đổi sau thành công, không mặc định coi đó là lỗi cần tạo approval mới.

### 10.3. Dịch vụ phụ thuộc bị lỗi

Mô phỏng không phân giải được danh tính, không tải được quan hệ ủy quyền, timeout khi đọc policy hoặc dữ liệu nguồn gốc bị thiếu. Không trường hợp nào được biến thành “không tìm thấy xung đột nên cho phép”.

Cần phân biệt lỗi không đủ quyền với lỗi dịch vụ tạm thời trong response theo hợp đồng. Bất biến chung vẫn là không có quyết định hoặc tác động được chấp nhận khi điều kiện bắt buộc chưa xác lập.

### 10.4. Thu hồi quyền trong lúc yêu cầu đang chạy

Trước tiên phải biết hệ thống cam kết gì: kiểm tra tại thời điểm nào, độ trễ cache bao lâu, và có yêu cầu tuần tự hóa với giao dịch thu hồi hay không.

Nếu cam kết rất chặt, kiểm thử lịch chạy thu hồi commit trước khi giao dịch duyệt commit nhưng giao dịch duyệt đã đọc quyền cũ. Nếu thiết kế chỉ bảo đảm ở thời điểm nhận lệnh hoặc chấp nhận độ trễ xác định, test phải đo và xác nhận đúng giới hạn đó.

Không viết một kiểm thử khẳng định “thu hồi tức thời” trong khi implementation phụ thuộc kho quyền bên ngoài đồng bộ trễ và chưa có giao thức hỗ trợ cam kết đó.

## 11. Kiểm thử theo mô hình và tính chất

### 11.1. Mô hình nhỏ làm oracle

Có thể tạo một mô hình tham chiếu chỉ chứa danh tính, tập maker, basis, vòng duyệt và các phiếu được chấp nhận. Mô hình dùng chính sách đã thống nhất, không gọi lại repository hay evaluator sản phẩm.

Sinh chuỗi lệnh như:

```text
create
submit
switchAccount
delegate
transferOwner
editMaterialInput
approveBudget
approveFinance
retryLastCommand
startExecution
```

Sau mỗi bước, đối chiếu kết quả và trạng thái quan sát được với mô hình. Lưu seed và rút gọn chuỗi lỗi để có thể tái hiện một phản ví dụ nhỏ.

Mô hình tham chiếu nên đơn giản hơn sản phẩm. Nếu sao chép cùng cấu trúc và điều kiện từ code thật, hai bên có thể cùng sai và test vẫn xanh.

### 11.2. Các tính chất quan trọng

- Một danh tính thuộc tập maker của basis không xuất hiện trong tập người duyệt được tính cho basis đó.
- Quorum yêu cầu hai người không thể được đáp ứng bởi một danh tính, bất kể số tài khoản hoặc số role.
- Đổi owner không xóa quan hệ maker mà policy yêu cầu giữ.
- Phiếu của vòng hoặc basis cũ không tự được tính cho vòng mới.
- Gửi lại cùng một ý định không làm tăng số người độc lập.
- Trạng thái đủ duyệt chỉ xuất hiện khi có tập quyết định đáp ứng đồng thời tính độc lập và yêu cầu vai trò.
- Một người độc lập, đủ quyền, không bị chặn toàn cục chỉ vì họ từng là maker của hồ sơ khác.

### 11.3. Kiểm thử biến đổi dữ liệu có giữ điều kiện

Một số phép biến đổi giúp phát hiện code dựa nhầm thuộc tính:

| Biến đổi | Kết quả cần giữ khi các điều kiện liên quan khác không đổi |
|---|---|
| Đổi tên hiển thị hoặc email | Quan hệ độc lập không thay đổi |
| Dùng account khác của cùng người, giữ quyền/ngữ cảnh tương ứng | Không biến maker thành người độc lập |
| Đổi thứ tự các phiếu độc lập, cập nhật version đúng hợp đồng | Kết luận quorum cuối cùng không thay đổi |
| Thêm bình luận không ảnh hưởng căn cứ | Không tự biến người bình luận thành maker nếu policy không quy định |
| Chuyển owner | Không mất lịch sử người lập |
| Đổi tenant của cả fixture hợp lệ một cách nhất quán | Không phụ thuộc ID tenant được viết cứng |

Các điều kiện giữ nguyên rất quan trọng. Hai account có quyền khác nhau có thể nhận kết quả tổng thể khác nhau dù cùng một người; điều cần so ở ví dụ đó là tính độc lập, không mặc định mọi kiểm tra quyền đều giống hệt.

## 12. Kiểm tra độ mạnh của bộ test

Một bộ test nhiều dòng chưa chắc phát hiện được lỗi quan trọng. Có thể đánh giá bằng cách tạo các biến thể sai có kiểm soát trong môi trường kiểm thử và xem test phù hợp có thất bại không.

### 12.1. Các lỗi cần bộ test phát hiện

| Biến thể lỗi | Test đáng lẽ phải phát hiện |
|---|---|
| Xóa điều kiện giao tập maker–reviewer | Người lập đủ role tự duyệt |
| So account ID thay danh tính người | Tài khoản phụ của maker hoặc reviewer trùng người |
| Đếm số hàng thay số người và vai trò hợp lệ | Một người qua hai account/role làm đủ quorum |
| Dùng owner hiện tại thay nguồn khởi xướng | Chuyển owner rồi tự duyệt |
| Tin `createdBy` hoặc `onBehalfOf` trong body | Giả dữ liệu nguồn gốc qua API |
| Bỏ qua basis/vòng khi lấy phiếu | Trộn phiếu cũ với phiếu mới |
| Bỏ policy ở endpoint admin hoặc batch | Kiểm thử cùng bất biến qua đường ghi đó |
| Bắt exception policy rồi trả allow | Lỗi kho quyền/danh tính vẫn không được tạo quyết định |
| Bỏ điều kiện chống cạnh tranh | Lịch hai tài khoản cùng người hoặc hai role xung đột |

Không cần giữ mọi biến thể lỗi trong code chính. Mục tiêu là biết bộ test có nhạy với những lỗi mà nó tuyên bố bảo vệ hay không.

### 12.2. Tránh assertion chỉ phản chiếu implementation

`verify(policy).calledOnce()` có thể hữu ích để chẩn đoán phối hợp thành phần, nhưng không chứng minh policy đúng hoặc không có tác động đã diễn ra trước khi policy chạy.

Các assertion như state, tập phiếu được tính, danh tính, basis và operation kiểm tra ý nghĩa nghiệp vụ trực tiếp hơn. Không viết test cho từng dòng setter nếu chúng không tạo thêm khả năng phát hiện vi phạm.

### 12.3. Tập trung vào rủi ro và phản ví dụ

Ưu tiên các trường hợp mà một lỗi sẽ cho phép tự duyệt, đếm trùng người hoặc thực thi khi chưa có người độc lập. Dùng parameterized test cho các tổ hợp thực sự song song, tránh sao chép nhiều test chỉ khác tên.

Khi có lỗi thực tế, thêm một regression test tái hiện đường vòng nhỏ nhất nhưng giữ ranh giới gây lỗi. Nếu lỗi nằm ở middleware làm mất người khởi xướng, một unit test chỉ đưa sẵn đúng maker vào policy sẽ không ngăn lỗi đó quay lại.

## 13. Quan sát, bằng chứng chạy test và tích hợp kiểm tra

### 13.1. Bằng chứng kết quả cần nối được với bất biến

Khi một test thất bại, báo cáo nên có mã quy tắc, chủ thể chuẩn hóa, request/basis/vòng, lịch chạy liên quan và trạng thái/tác động thực tế. Với test sinh ngẫu nhiên, cần seed và chuỗi lệnh đã rút gọn.

Không ghi token đăng nhập, credential, resume secret hoặc dữ liệu nhạy cảm không cần thiết vào báo cáo. Có thể dùng định danh fixture và correlation ID để truy vết.

Một ảnh chụp nút duyệt bị ẩn không phải bằng chứng đủ về kiểm soát phía server. Kết quả hữu ích phải chỉ ra request bị xử lý thế nào và trạng thái/tác động sau đó ra sao.

### 13.2. Audit từ chối cần được thử đúng cách

Nếu hệ thống yêu cầu ghi nhận tự duyệt bị chặn, kiểm tra sự kiện audit xuất hiện theo độ trễ được công bố và chứa đúng chủ thể, đối tượng và mã lý do. Không buộc audit từ chối phải nằm trong transaction vốn sẽ rollback.

Audit không được làm lộ thông tin hồ sơ ngoài quyền. Với người sai tenant, phản hồi và log được hiển thị cho người đó phải tuân thủ phạm vi truy cập; dữ liệu chẩn đoán nội bộ cũng cần quyền thích hợp.

### 13.3. Bố trí kiểm tra trong luồng phát triển

Có thể chạy nhanh unit policy và API test trọng yếu khi thay quyền hoặc luồng duyệt; chạy integration về khóa/constraint trên cấu hình cơ sở dữ liệu phù hợp; chạy các chuỗi mô hình rộng hơn theo năng lực của hệ thống kiểm thử.

Tần suất cụ thể tùy dự án. Các kiểm tra bắt buộc cho một thay đổi phải thực sự được chạy trước khi kết luận đạt; không ghi một test chưa chạy thành bằng chứng thành công.

Đặc biệt xem lại phạm vi test khi thêm endpoint ghi quyết định, thêm nguồn import, thay mô hình danh tính, thêm ủy quyền, đổi policy quorum hoặc thay cơ chế transaction. Những thay đổi này có thể mở đường vòng dù hàm kiểm tra không tự duyệt không đổi.

### 13.4. Phân biệt nội dung bài học với kết quả chạy thực tế

Các bảng và đoạn mã trong bài là hướng dẫn thiết kế kiểm thử. Muốn tuyên bố một hệ thống đạt kiểm soát, cần có fixture, cấu hình, phiên bản code và kết quả chạy của chính hệ thống đó.

Một báo cáo hữu ích nên nêu những bất biến đã kiểm chứng, đường thực thi đã bao phủ, các cam kết nhất quán được giả định và khoảng trống còn lại. Không chỉ dùng tỷ lệ coverage hoặc số test xanh làm kết luận về phân tách nhiệm vụ.

## 14. Bài thực hành và tự rà soát

Với một workflow có hai cấp duyệt, hãy chọn các hành động tạo, sửa căn cứ, duyệt từng cấp, chuyển owner và thực thi. Viết chính sách ai bị loại ở từng hành động trước khi viết test.

Sau đó xây một tập kiểm thử gồm:

1. Maker đủ role nhưng bị chặn trên hồ sơ của mình.
2. Hai account cùng người không tạo được tính độc lập giả.
3. Hai người độc lập đúng vai trò hoàn tất được luồng hợp lệ.
4. Tạo hộ và ủy quyền giữ đúng danh tính phải xét.
5. Đổi owner hoặc sửa căn cứ không làm mất điều kiện nguồn gốc.
6. API chuyên biệt, API tổng quát, batch và đường quản trị đang có đều giữ cùng bất biến.
7. Lịch cạnh tranh chứng minh không ghi/đếm trùng người và không cấp tổ hợp quyền xung đột.
8. Lỗi transaction và gửi lại sau commit không tạo quyết định hay tác động thừa.

Tự kiểm tra thêm: mỗi test có cô lập được quy tắc đang xét không, có assertion về dữ liệu/tác động không, có positive case ngăn chặn quá mức không, và có thể tái hiện thất bại mà không dựa vào timing ngẫu nhiên không?

Kiểm thử phân tách nhiệm vụ có giá trị khi chứng minh được ai đã làm gì, trên căn cứ nào và vì sao những chủ thể đó đáp ứng tính độc lập mà chính sách yêu cầu. Kết luận đó phải còn đúng qua tài khoản phụ, ủy quyền, thay đổi hồ sơ, gửi lại yêu cầu và xử lý đồng thời.
