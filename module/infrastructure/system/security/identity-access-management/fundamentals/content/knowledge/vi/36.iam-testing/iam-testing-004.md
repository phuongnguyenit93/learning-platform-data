# Authorization matrix test

## 1. Kiểm thử ma trận phân quyền là gì?

**Authorization matrix test** là cách biểu diễn và kiểm thử các quyết định truy cập bằng một tập trường hợp có cấu trúc: chủ thể nào, thực hiện hành động nào, trên tài nguyên nào, trong ngữ cảnh và trạng thái nào, thì phải được cho phép hay từ chối.

Một ma trận đơn giản có hàng là role và cột là hành động. Tuy nhiên, quyền thực tế thường còn phụ thuộc tenant, quan hệ sở hữu, phạm vi được giao, trạng thái tài nguyên, hiệu lực membership, thời gian hoặc mức bảo đảm xác thực. Vì vậy ma trận cần đủ thông tin để không biến một quyền có điều kiện thành một dấu “được phép” chung cho mọi tình huống.

Ví dụ, role `editor` có thể sửa một tài liệu nháp được giao trong tenant của mình. Câu “editor được sửa tài liệu” chưa đủ để kiểm thử: cùng role đó phải bị từ chối khi sửa tài liệu của tenant khác, tài liệu đã xuất bản hoặc tài liệu không được giao.

Mục tiêu của ma trận là kiểm chứng cả hai phía:

- Truy cập hợp lệ thực hiện được đúng hành động và đúng phạm vi.
- Truy cập không hợp lệ bị chặn, không làm lộ dữ liệu hoặc tạo tác động nghiệp vụ ngoài ý muốn.

Chỉ kiểm thử các trường hợp allow sẽ bỏ sót nhiều lỗi vượt quyền. Chỉ kiểm thử deny cũng không đủ, vì một hệ thống luôn từ chối có thể làm toàn bộ test âm tính đạt trong khi người dùng hợp lệ không làm được việc.

## 2. Phân biệt xác thực, phân quyền và kết quả nghiệp vụ

Để kiểm tra authorization, trước hết cần bảo đảm test thật sự đi tới điểm phân quyền. Một request thiếu token bị chặn ở bước authentication không chứng minh kiểm tra tenant hoặc ownership đã hoạt động.

| Kết quả quan sát | Có thể xảy ra vì | Điều chưa được chứng minh |
| --- | --- | --- |
| Không có phiên/credential được chấp nhận | Authentication thất bại | Policy quyền trên tài nguyên đúng |
| Request bị chặn bởi CSRF hoặc validation | Kiểm tra trước nghiệp vụ thất bại | Điều kiện RBAC/ABAC đã được đánh giá |
| Policy đưa ra deny hợp lệ | Không đáp ứng quyền hoặc điều kiện | Mọi tác động dữ liệu đều đã được ngăn |
| Policy allow nhưng thao tác lỗi | Hợp lệ về quyền, lỗi ở bước nghiệp vụ | Luồng người dùng đã hoạt động thành công |
| HTTP 200 | Có thể thành công, trang lỗi hoặc phản hồi đã bị lọc | Caller nhận đúng dữ liệu và không có dữ liệu thừa |

Mỗi lớp kiểm thử cần có oracle phù hợp, tức nguồn xác định kết quả mong muốn. Với test policy, oracle là quyết định quyền. Với test API hoặc đầu cuối, còn cần kiểm tra phản hồi, dữ liệu và các tác động liên quan.

Không coi mọi phản hồi 403 hoặc 404 là bằng chứng test quyền đã đạt. Một 404 do fixture không tồn tại khác với 404 được chủ đích dùng để che giấu tài nguyên không được phép xem. Cần thiết lập tài nguyên đúng và có bằng chứng request đi qua đường kiểm soát dự kiến.

## 3. Đặc tả một ô ma trận đủ thông tin

Có thể mô hình hóa một trường hợp như sau:

```text
Case = (
  subject và role/membership đã xác minh,
  action,
  resource cùng thuộc tính có thẩm quyền,
  context,
  trạng thái vòng đời và phiên bản policy,
  expected decision,
  expected response và business effects
)
```

Các chiều thường cần xem xét:

| Chiều | Ví dụ giá trị |
| --- | --- |
| Loại chủ thể | Người dùng, workload, principal đại diện |
| Role/quyền | Không có role, reader, editor, approver, tổ hợp role |
| Tenant | Cùng tenant, khác tenant, membership đã thu hồi |
| Quan hệ tài nguyên | Được giao, không được giao, là tác giả, không phải tác giả |
| Hành động | Đọc, sửa, xuất bản, cấp quyền, thao tác hàng loạt |
| Trạng thái tài nguyên | Nháp, đã xuất bản, lưu trữ |
| Trạng thái tài khoản | Hoạt động, vô hiệu hóa, đang chấm dứt |
| Ngữ cảnh | Đủ độ mới xác thực, thiếu thuộc tính bắt buộc, policy cache cũ |
| Đường truy cập | API công khai, service, job nền, export, tìm kiếm |

Không phải mọi bài toán đều cần mọi chiều. Hãy xuất phát từ policy và các đường tiếp cận tài nguyên thực tế. Một chiều bị bỏ khỏi ma trận cần là quyết định có lý do, không phải vì framework khó tạo fixture cho nó.

## 4. Xây dựng một policy minh họa trước khi lập expected

Xét một ứng dụng tài liệu đa tenant có bốn role độc lập: `reader`, `editor`, `approver`, `tenant_admin`. Tài liệu có các trạng thái `DRAFT`, `PUBLISHED`, `ARCHIVED` và có tác giả cùng danh sách người được giao.

Để tránh mơ hồ, policy minh họa được xác định như sau:

1. Chủ thể phải đã được xác thực, tài khoản đang hoạt động và có membership còn hiệu lực trong tenant đang truy cập.
2. Mọi role trong ví dụ chỉ có phạm vi tenant; `tenant_admin` không phải quản trị toàn cục. Tài nguyên khác tenant bị từ chối với cả bốn role.
3. `reader` được đọc tài liệu `PUBLISHED` trong tenant của mình.
4. `editor` được đọc tài liệu được giao ở trạng thái `DRAFT` hoặc `PUBLISHED`, và được sửa tài liệu được giao ở trạng thái `DRAFT`.
5. `approver` được đọc tài liệu được giao ở trạng thái `DRAFT` hoặc `PUBLISHED`, và được xuất bản tài liệu được giao ở trạng thái `DRAFT` nếu mình không phải tác giả.
6. `tenant_admin` được đọc mọi trạng thái tài liệu trong tenant, sửa mọi tài liệu `DRAFT` trong tenant và xuất bản tài liệu `DRAFT` nếu mình không phải tác giả; không bắt buộc quan hệ được giao cho role này.
7. Với mọi role và tổ hợp role, không được tự xuất bản tài liệu do chính mình làm tác giả. Role không có quyền ở trên không tự thừa hưởng quyền của role khác.
8. Khi có nhiều role hợp lệ, một quyền allow từ role có thể cho phép thao tác sau khi thỏa các ràng buộc chung. Các điều kiện chặn chung như khác tenant, tài khoản vô hiệu hóa hoặc tự xuất bản vẫn phải có hiệu lực.
9. Hành động không được định nghĩa hoặc dữ liệu bắt buộc không đủ để đánh giá thì không được tự chuyển thành allow.

Đây là chính sách giả định phục vụ bài học, không phải mô hình quyền mặc định cho mọi hệ thống tài liệu. Các tổ chức khác có thể chọn quyền khác; điều cần giữ là expected được lấy từ một hợp đồng rõ ràng và có thẩm quyền.

## 5. Ma trận role × action là điểm bắt đầu

Với các ràng buộc chung ở trên, bảng rút gọn là:

| Role | Read | Edit | Publish |
| --- | --- | --- | --- |
| Không có role phù hợp | Deny | Deny | Deny |
| `reader` | Allow khi `PUBLISHED` | Deny | Deny |
| `editor` | Allow khi được giao và `DRAFT/PUBLISHED` | Allow khi được giao và `DRAFT` | Deny |
| `approver` | Allow khi được giao và `DRAFT/PUBLISHED` | Deny | Allow khi được giao, `DRAFT`, không phải tác giả |
| `tenant_admin` | Allow trong tenant | Allow khi `DRAFT` trong tenant | Allow khi `DRAFT` trong tenant, không phải tác giả |

Một dấu allow có điều kiện phải được mở thành nhiều trường hợp kiểm thử. Bảng này chưa kiểm tra hết các ranh giới: một reader đọc tài liệu đã xuất bản của tenant khác vẫn phải bị từ chối; một tenant admin cũng không được tự xuất bản tài liệu do mình làm tác giả.

Không để ô trống mang nghĩa ngầm. Ô có thể được định nghĩa là deny, chưa đặc tả hoặc không áp dụng, nhưng mỗi trạng thái phải có nghĩa rõ và được xử lý trong báo cáo. “Chưa đặc tả” không phải “được phép bỏ qua mà vẫn tính đủ coverage”.

## 6. Mở thành bảng test case cụ thể

Giả sử các tài khoản đều đã xác thực và đang hoạt động, trừ hàng ghi rõ khác. Mỗi tài liệu dùng ID riêng có fixture tồn tại trong test.

| ID | Role | Tenant tài liệu | Trạng thái | Được giao? | Là tác giả? | Hành động | Expected |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M01 | `reader` | Cùng | `PUBLISHED` | Không | Không | Read | Allow |
| M02 | `reader` | Cùng | `DRAFT` | Có | Không | Read | Deny |
| M03 | `reader` | Khác | `PUBLISHED` | Không | Không | Read | Deny |
| M04 | `editor` | Cùng | `DRAFT` | Có | Có | Edit | Allow |
| M05 | `editor` | Cùng | `DRAFT` | Không | Có | Edit | Deny |
| M06 | `editor` | Cùng | `PUBLISHED` | Có | Có | Edit | Deny |
| M07 | `editor` | Khác | `DRAFT` | Có | Có | Edit | Deny |
| M08 | `approver` | Cùng | `DRAFT` | Có | Không | Publish | Allow |
| M09 | `approver` | Cùng | `DRAFT` | Có | Có | Publish | Deny |
| M10 | `approver` | Cùng | `DRAFT` | Không | Không | Publish | Deny |
| M11 | `approver` | Cùng | `PUBLISHED` | Có | Không | Publish | Deny |
| M12 | `tenant_admin` | Cùng | `ARCHIVED` | Không | Không | Read | Allow |
| M13 | `tenant_admin` | Khác | `DRAFT` | Không | Không | Edit | Deny |
| M14 | `tenant_admin` | Cùng | `DRAFT` | Không | Có | Publish | Deny |
| M15 | `editor + approver` | Cùng | `DRAFT` | Có | Có | Publish | Deny |
| M16 | `tenant_admin`, tài khoản vô hiệu hóa | Cùng | `DRAFT` | Có | Không | Edit | Deny |

Các hàng như M04/M05 chỉ thay đổi quan hệ được giao, còn M08/M09 chỉ thay đổi quan hệ tác giả. Những cặp này giúp xác định một điều kiện cụ thể có thật sự ảnh hưởng tới quyết định hay không.

Bảng là một tập ví dụ, không phải tuyên bố đã bao phủ đầy đủ policy. Còn cần các ca membership hết hiệu lực, hành động chưa định nghĩa, thuộc tính thiếu, tổ hợp role khác và những đường truy cập bổ sung của ứng dụng.

## 7. Chọn dữ liệu thử để test không đạt giả

### 7.1. Dùng tài nguyên tồn tại và phân biệt rõ phạm vi

Chuẩn bị ít nhất các tài khoản và tài liệu khác nhau ở tenant A và B. Không dùng một tài khoản toàn quyền cho mọi ca. Không để tài liệu “khác tenant” thực tế không tồn tại, vì API có thể trả not found trước khi kiểm tra quyền.

Trong một ca âm tính, kiểm tra fixture bằng kênh setup được phép hoặc helper đọc trạng thái test, không bằng credential của chính người đang bị hạn chế. Đặt quan hệ được giao, tác giả và trạng thái một cách tường minh.

### 7.2. Tách dữ liệu có thẩm quyền khỏi dữ liệu client tự khai

Tenant và tác giả của tài nguyên cần đến từ dữ liệu server hoặc nguồn được tin cậy. Bổ sung ca client sửa `tenantId`, `ownerId`, `role` hoặc `userId` trong body/header để bảo đảm các giá trị đó không ghi đè security context hay thuộc tính tài nguyên.

Nếu endpoint hỗ trợ lựa chọn tenant, server vẫn phải kiểm tra membership và phạm vi tài nguyên. Một tenant ID có trong URL là lựa chọn đầu vào, không phải bằng chứng caller được truy cập tenant đó.

### 7.3. Cô lập và đặt lại trạng thái

Một ca allow có thể sửa tài liệu sang `PUBLISHED`, làm ca edit phía sau bị deny vì trạng thái đã đổi. Mỗi ca cần fixture riêng hoặc cơ chế đặt lại dữ liệu được kiểm soát. Không để thứ tự chạy quyết định expected.

Tương tự, cache quyền, session, membership và thông điệp bất đồng bộ có thể làm các ca ảnh hưởng nhau. Mỗi lượt kiểm thử cần biết phiên bản policy, trạng thái khởi đầu và cách làm sạch dữ liệu thử trong đúng phạm vi.

## 8. Kiểm thử ở nhiều lớp để bao phủ cả quyết định và thực thi

### 8.1. Policy unit test

Đưa tuple subject/action/resource/context vào engine hoặc hàm quyết định rồi kiểm tra `allow`, `deny` và nghĩa vụ liên quan. Lớp này phù hợp để chạy nhiều tổ hợp, kiểm tra điều kiện biên và ràng buộc chung.

Không mock chính quyết định quyền thành giá trị expected rồi gọi đó là policy test. Nếu cần stub một nguồn thuộc tính, stub dữ liệu đầu vào cụ thể để policy thật vẫn phải xử lý điều kiện đang được kiểm tra.

### 8.2. Service hoặc PEP integration test

Kiểm tra service gửi đúng thông tin đến điểm quyết định và thực thi kết quả trước khi đọc/ghi dữ liệu. Trường hợp policy deny nhưng service vẫn lưu thay đổi là lỗi thực thi mà policy unit test không phát hiện.

Nếu policy trả thêm nghĩa vụ như chỉ được trả một số trường, service phải thực hiện nghĩa vụ đó. Không coi `allow` là quyền bỏ qua mọi ràng buộc còn lại.

### 8.3. API hoặc kiểm thử đầu cuối

Sử dụng cơ chế xác thực phù hợp với môi trường thử và gọi endpoint thật trong phạm vi được kiểm soát. Lớp này kiểm tra việc mapping role, tenant, phương thức HTTP, bộ lọc bảo mật và truy cập tài nguyên có khớp thiết kế hay không.

Test dùng principal mock có thể rất hữu ích ở một lớp, nhưng không chứng minh hệ thống thật ánh xạ claims đúng hoặc từ chối token sai audience. Cần ghi rõ lớp test và phần nào được thay thế, thay vì gộp kết quả thành một tuyên bố bao phủ mọi ranh giới.

Một luồng xác thực thất bại do test fixture không hợp lệ cần được sửa hoặc báo lỗi môi trường; không được tính là một ca deny quyền đã đạt.

## 9. Assertion phải kiểm tra cả kết quả lẫn tác động

### 9.1. Với ca được phép

Kiểm tra thao tác thành công đúng đối tượng và phạm vi. Với edit, đọc lại giá trị đã lưu; với publish, kiểm tra trạng thái và sự kiện nghiệp vụ đúng. Với read, kiểm tra ID, tenant và tập trường trả về, không chỉ mã 200.

### 9.2. Với ca bị từ chối

Kiểm tra phản hồi theo hợp đồng của endpoint, không lộ dữ liệu nhạy cảm và không có tác động nghiệp vụ được bảo vệ. Với một lệnh ghi, có thể cần xác minh:

- Bản ghi không thay đổi, kể cả version hoặc trạng thái có ý nghĩa nghiệp vụ.
- Không tạo tác vụ, thông điệp outbox, thông báo hoặc bản xuất dữ liệu trái phép.
- Không cấp credential, role hoặc session đặc quyền ngoài ý muốn.
- Có sự kiện audit từ chối nếu thiết kế yêu cầu, với dữ liệu tối thiểu phù hợp.

Không yêu cầu “không có bất kỳ side effect nào” một cách mơ hồ: audit bảo mật, metric hoặc bộ đếm chống lạm dụng có thể là tác động được chủ đích. Cần phân biệt tác động nghiệp vụ bị cấm với bằng chứng vận hành được phép.

### 9.3. Ví dụ ca test dưới dạng dữ liệu

```yaml
id: M09
policyVersion: document-policy-v3
subject:
  fixture: approver_author_tenant_a
  accountState: ACTIVE
action: document.publish
resource:
  fixture: assigned_draft_by_same_author
expected:
  decision: DENY
  publicResponse: forbidden_by_endpoint_contract
  businessState: UNCHANGED
  businessEvents: NONE
  securityAudit: denial_recorded
```

Schema này chỉ minh họa dữ liệu kiểm thử. Fixture phải thật sự tạo quan hệ “người duyệt chính là tác giả”, và giá trị phản hồi cụ thể phải theo hợp đồng API của hệ thống. Không suy ra kết quả từ tên fixture nếu dữ liệu khởi tạo không đúng.

Một trình tự kiểm thử khái niệm:

```text
given: tạo subject, membership và tài liệu theo ca
given: xác minh trạng thái khởi đầu bằng helper test được phép
when:  thực hiện thao tác bằng danh tính của subject
then:  kiểm tra kết quả theo lớp test
then:  đọc lại tài nguyên và tác động liên quan
then:  kiểm tra bằng chứng kiểm soát, không ghi raw credential
```

Đây là pseudo-code cho thiết kế test, không phải lời gọi API của một framework cụ thể.

## 10. Bao phủ RBAC, ABAC và tổ hợp điều kiện

### 10.1. Role đơn chưa đủ

Kiểm tra cả không có role, role không liên quan, role cùng tên nhưng khác tenant/phạm vi, role đã bị thu hồi và nhiều role cùng lúc. Các ràng buộc như không tự phê duyệt phải giữ hiệu lực ngay cả khi một role khác cho phép thao tác tương tự.

Theo policy minh họa, thêm `approver` cho một tác giả vốn là `editor` không làm tác giả được tự xuất bản. Đây là một ca quan trọng về phân tách nhiệm vụ; chỉ chạy từng role riêng sẽ không kiểm chứng được nó.

### 10.2. Thuộc tính thiếu hoặc không đáng tin

Thử các trường hợp tenant không xác định, trạng thái tài nguyên không được hỗ trợ, membership chưa được xác minh hoặc nguồn thuộc tính không trả đủ dữ liệu. Expected phải lấy từ hợp đồng xử lý lỗi của policy; không mặc định thiếu dữ liệu nghĩa là bỏ qua điều kiện.

Nếu engine phân biệt `deny` với `indeterminate` hoặc `error`, kiểm tra đúng quyết định của engine và cách PEP xử lý. PEP có thể chặn khi lỗi, nhưng không được ghi nhầm lỗi phụ thuộc thành deny chính sách thông thường nếu hợp đồng quan sát yêu cầu phân biệt.

### 10.3. Quy mô tổ hợp và chọn ca theo rủi ro

Chỉ với 4 role đơn, 3 hành động, 2 quan hệ tenant, 2 trạng thái được giao, 3 trạng thái tài liệu và 2 quan hệ tác giả đã có:

```text
4 × 3 × 2 × 2 × 3 × 2 = 288 tổ hợp trước khi xét tính khả thi
```

Còn tài khoản, membership, tổ hợp role, phiên và các đường API chưa nằm trong phép đếm này. Không phải mọi tổ hợp đều khả thi; những ca loại ra cần có lý do, còn những ca cùng kết quả chưa chắc là dư thừa nếu kiểm tra các ranh giới khác nhau.

Có thể dùng sinh ca theo dữ liệu hoặc kỹ thuật giảm tổ hợp cho vùng ít rủi ro, nhưng phải giữ đầy đủ các invariant quan trọng như cách ly tenant, quyền đặc quyền và phân tách nhiệm vụ. Bao phủ từng cặp điều kiện không tự chứng minh một lỗi cần ba hay nhiều điều kiện đồng thời sẽ bị phát hiện.

## 11. Kiểm tra invariant và tính nhạy của bộ test

Một số invariant cho policy minh họa:

| Invariant | Ý nghĩa kiểm thử |
| --- | --- |
| Role tenant không vượt sang tenant khác | Mọi hành động trên tài nguyên khác tenant đều không được phép |
| Tài khoản vô hiệu hóa không thực hiện thao tác được bảo vệ | Role nhiều quyền không vượt qua trạng thái vòng đời |
| Không tự xuất bản | Kết hợp role không phá phân tách nhiệm vụ |
| Edit chỉ trên `DRAFT` | Đổi trạng thái tài nguyên có thể làm quyền cũ không còn phù hợp |
| Không có grant phù hợp thì không allow | Phát hiện quyền mặc định quá rộng |

Property-based test có thể sinh nhiều fixture phù hợp với một invariant. Tuy nhiên, cần tránh để bộ sinh chỉ tạo dữ liệu mà implementation vốn đã xử lý tốt. Expected cần dựa trên policy, không gọi lại chính hàm production để tính expected rồi so sánh với nó.

Mutation testing có thể kiểm tra độ nhạy của bộ test trong môi trường phù hợp: nếu tạm bỏ điều kiện tenant, điều kiện tác giả hoặc kiểm tra trạng thái trong một bản đột biến, có ca test nào thất bại không? Nếu không, coverage hiện tại có thể chưa chứng minh được ràng buộc đó.

Đây là kỹ thuật đánh giá bộ test có kiểm soát, không phải thay đổi policy ở hệ thống đang phục vụ. Không được giữ bản đột biến hoặc cơ chế bypass trong cấu hình triển khai thật.

## 12. Những đường truy cập dễ bị bỏ quên

### 12.1. Collection, tìm kiếm và export

Kiểm tra từng bản ghi riêng chưa chứng minh endpoint list chỉ trả bản ghi được phép. Cần xét bộ lọc, phân trang, tìm kiếm, tổng số, aggregation và export. Một response có thể không chứa nội dung tài liệu nhưng vẫn làm lộ sự tồn tại hoặc số lượng tài liệu ngoài phạm vi.

Expected cho collection phải nêu rõ tập dữ liệu được phép, không chỉ “API trả thành công”. Các trường nhạy cảm và metadata cũng cần được xét theo policy của ứng dụng.

### 12.2. Bulk và quan hệ cha/con

Một lệnh bulk có thể chứa cả tài nguyên được phép lẫn không được phép. Hợp đồng phải xác định từ chối toàn bộ hay cho phép kết quả một phần. Test cần kiểm tra đúng tính nguyên tử, phản hồi và từng thay đổi, thay vì chấp nhận bất kỳ lỗi nào là đạt.

Với đường dẫn như tenant/course/document, kiểm tra tài liệu thật sự thuộc course và tenant được nêu. Đổi một ID ở path không được làm service kiểm tra quyền trên đối tượng cha hợp lệ nhưng ghi vào đối tượng con ngoài phạm vi.

### 12.3. Endpoint thay thế và đường nội bộ

Cùng một thao tác có thể có route cũ, route quản trị, phương thức HTTP khác, job nền hoặc consumer. Ma trận cần được ánh xạ đến các điểm thực thi tương ứng; ẩn nút trên UI hoặc kiểm tra ở gateway không chứng minh đường nội bộ đã được bảo vệ.

Với workload đại diện người dùng, kiểm tra cả quyền của workload và quan hệ delegation theo thiết kế. Không cho một `userId` tự khai trong message thay thế bằng chứng về subject được đại diện.

## 13. Kiểm thử thay đổi quyền và thời gian

### 13.1. Thu hồi role hoặc membership

Một ca hữu ích có chuỗi trạng thái:

```text
Có quyền → thao tác hợp lệ thành công
  → thu hồi tại nguồn có thẩm quyền
  → quan sát trạng thái được phân phối theo hợp đồng
  → thao tác bằng credential/phiên cũ bị xử lý đúng
```

Nếu thiết kế có cửa sổ hiệu lực của token hoặc cache, expected phải nêu mốc thời gian và cơ chế áp dụng. Không viết test đòi thu hồi tức thời khi kiến trúc chỉ bảo đảm sau một khoảng xác định; cũng không thay expected bằng “eventually đúng” vô thời hạn để che độ trễ thu hồi.

### 13.2. Điều kiện biên và tính ổn định

Với policy theo thời gian, dùng đồng hồ điều khiển được ở lớp test phù hợp để kiểm tra trước, tại và sau mốc hiệu lực. Ở lớp tích hợp có đồng bộ thật, chờ điều kiện với timeout hữu hạn và báo trạng thái chưa hội tụ; tránh dùng thời gian ngủ cố định làm bằng chứng đã đồng bộ.

### 13.3. Thay đổi đồng thời

Kiểm tra các tình huống quyền bị thu hồi hoặc trạng thái tài nguyên đổi giữa lúc đọc và lúc ghi. Thiết kế phải xác định quyết định nào gắn với trạng thái nào, có kiểm tra lại hoặc cơ chế concurrency phù hợp hay không.

Ma trận tĩnh có thể không phát hiện lỗi time-of-check/time-of-use. Cần bổ sung ca có trình tự kiểm soát được cho hành động rủi ro cao, và xác minh không ghi được bằng một quyết định đã không còn phù hợp theo hợp đồng.

## 14. Duy trì ma trận như một phần của hợp đồng quyền

Mỗi ca nên có ID, liên kết với quy tắc nghiệp vụ, phiên bản policy và lớp kiểm thử. Khi có endpoint, role, trạng thái tài nguyên hoặc tenant model mới, cập nhật cả quyền được phép lẫn các ranh giới phải từ chối.

Báo cáo coverage nên nói rõ những gì đã bao phủ: role-action, ranh giới tenant, ownership/assignment, trạng thái, tổ hợp role, vòng đời và đường thực thi. Một con số code coverage cao không thay thế được coverage của các quy tắc quyền.

Khi implementation và expected khác nhau, đối chiếu đặc tả và người chịu trách nhiệm policy. Không cập nhật expected theo kết quả hiện tại chỉ để test xanh. Tương tự, không sao chép nguyên các nhánh điều kiện production sang một bộ sinh expected rồi coi đó là oracle độc lập.

Thông tin lỗi test cần đủ để tái hiện bằng fixture, case ID, phiên bản policy và kết quả quan sát. Không đính kèm raw token, mật khẩu, secret hoặc dữ liệu người dùng thật vào log kiểm thử. Dùng danh tính và tài nguyên chuyên dụng của môi trường phù hợp.

Authorization matrix test có giá trị khi chuyển một chính sách quyền rõ ràng thành các trường hợp có thể kiểm chứng. Kiểm tra đồng thời allow, deny, dữ liệu trả về, tác động nghiệp vụ và các ranh giới vòng đời giúp bộ test phát hiện cả lỗi cấp quyền quá rộng lẫn lỗi cản trở truy cập hợp lệ.
