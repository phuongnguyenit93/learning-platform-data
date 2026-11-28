# Thiết kế user lifecycle: capstone quản lý người dùng từ tiếp nhận đến kết thúc truy cập

User lifecycle là vòng đời của danh tính, tài khoản và khả năng truy cập gắn với một người trong một phạm vi tổ chức. Thiết kế vòng đời không dừng ở hai thao tác “tạo user” và “xóa user”: nó cần xác định nguồn quyết định, thời điểm hiệu lực, quyền được cấp, thay đổi trạng thái và bằng chứng tại các hệ thống đích.

Bài thực hành này xây dựng một thiết kế hoàn chỉnh trên tình huống giả định. Mục tiêu là nối kiến thức IAM thành một luồng có thể triển khai và kiểm tra: từ joiner, mover, leaver đến MFA, session, provisioning, quyền theo tenant, xử lý lỗi và đối soát.

Các mốc thời gian, tên người và policy dưới đây là giả định của bài tập, không phải yêu cầu chung từ một tiêu chuẩn hoặc quy định pháp lý.

## 1. Đề bài và phạm vi hệ thống

Công ty An Bình sử dụng:

| Thành phần | Vai trò trong bài tập |
| --- | --- |
| HR | Nguồn trạng thái quan hệ lao động của nhân viên |
| Cổng đối tác | Nguồn quan hệ cộng tác của người ngoài tổ chức |
| Dịch vụ danh tính và IdP | Quản lý tài khoản, phương tiện xác thực và đăng nhập tập trung |
| Ứng dụng CRM | Quyền theo nhóm kinh doanh và khách hàng được phân công |
| Ứng dụng tài chính | Quyền nhập, xem và duyệt hồ sơ chi phí |
| Bộ điều phối vòng đời | Tính trạng thái mong muốn và đồng bộ tới các đích |
| Kho bằng chứng vận hành | Theo dõi quyết định, hành động, lỗi và kết quả quan sát |

Dùng ba nhân vật tổng hợp:

- **Lan**: bắt đầu là nhân viên kinh doanh, sau đó chuyển sang hỗ trợ khách hàng.
- **Minh**: cộng tác viên có người bảo trợ và ngày kết thúc quan hệ.
- **Hương**: quản trị vận hành, có tài khoản làm việc và khả năng thực hiện tác vụ đặc quyền theo phê duyệt.

Thiết kế phải trả lời được sáu câu hỏi:

1. Ai có thẩm quyền xác lập thay đổi?
2. Tài khoản nào và quan hệ nào bị tác động?
3. Quyền nào cần thêm, giữ hoặc thu hồi?
4. Các thay đổi có hiệu lực từ khi nào?
5. Làm gì khi một đích chậm hoặc thất bại?
6. Bằng chứng nào chứng minh kết quả tại điểm truy cập?

Phạm vi chính là user con người. Workload liên quan được xem xét ở khía cạnh chủ sở hữu và credential cần chuyển giao; không tự biến việc một nhân viên nghỉ việc thành lệnh xóa mọi service account mà người đó từng quản lý.

## 2. Phân biệt người, quan hệ, tài khoản và quyền

Bốn khái niệm này thường bị gộp vào một bản ghi user, gây khó xử lý khi người dùng đổi vai trò hoặc có nhiều quan hệ.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Person/subject | Chủ thể được hệ thống định danh trong phạm vi quản lý | Lan có định danh nội bộ ổn định |
| Relationship | Quan hệ làm căn cứ sử dụng dịch vụ | Hợp đồng lao động hoặc cộng tác |
| Account | Biểu diễn chủ thể tại một hệ thống | Tài khoản IdP, tài khoản CRM |
| Entitlement/grant | Khả năng truy cập được cấp có nguồn gốc | Quyền đọc hồ sơ của nhóm kinh doanh |

Một người có thể có nhiều quan hệ, một quan hệ có thể dẫn tới nhiều tài khoản, và một quyền có thể đến từ nhiều đường cấp.

~~~mermaid
flowchart LR
    P[Chủ thể] --> R1[Quan hệ nhân viên]
    P --> R2[Quan hệ cộng tác khác]
    R1 --> G1[Các grant từ quan hệ nhân viên]
    R2 --> G2[Các grant từ quan hệ cộng tác]
    G1 --> A[Tài khoản và quyền tại các đích]
    G2 --> A
    A --> O[Quan sát truy cập thực tế]
~~~

Ví dụ, kết thúc một quan hệ cộng tác ở tenant A không nhất thiết kết thúc một quan hệ khác còn hợp lệ ở tenant B. Ngược lại, sự kiện bảo mật khóa toàn bộ chủ thể có thể có phạm vi rộng hơn một quan hệ.

Trước mỗi hành động, thiết kế phải chỉ rõ đang tác động ở cấp nào. Không dùng tên hoặc email làm lý do tự động gộp hai người.

## 3. Chọn nguồn có thẩm quyền theo từng loại dữ kiện

Không cần một hệ thống làm nguồn chuẩn cho mọi trường. Cần xác định thẩm quyền theo dữ kiện và phạm vi:

| Dữ kiện | Nguồn có thẩm quyền trong bài tập | Bên không được tự quyết |
| --- | --- | --- |
| Ngày bắt đầu/kết thúc lao động | HR | Connector CRM |
| Người bảo trợ và hạn cộng tác | Cổng đối tác | Người dùng tự khai |
| Nhóm công việc | HR kết hợp ánh xạ đã được phê duyệt | Giá trị role từ form đăng ký |
| Quyền nhạy cảm | Chủ hệ thống và quy trình phê duyệt | Thuộc tính chức danh đơn thuần |
| Tình trạng phương tiện xác thực | Dịch vụ danh tính | Hồ sơ HR |
| Khóa khẩn cấp vì sự cố | Quy trình an ninh được phân quyền | Một job đồng bộ cũ |
| Quyền đã tồn tại tại đích | Đích là nguồn quan sát | Không tự coi đó là quyền được duyệt |

Đích có thể cho biết “Lan đang thuộc nhóm CRM-Sales”, nhưng điều đó không chứng minh membership vẫn phải tồn tại. Bộ điều phối cần so sánh quan sát này với quyết định hiện tại.

Khi nguồn mâu thuẫn, thiết kế cần quy tắc xử lý đã xác định. Ví dụ, thông tin nhân sự đang hoạt động không tự gỡ một lệnh khóa an ninh còn hiệu lực. Người dùng cũng không tự kéo dài quan hệ cộng tác bằng cách sửa ngày hết hạn trên hồ sơ cá nhân.

Các phiên bản dữ liệu chỉ có ý nghĩa trong phạm vi được nguồn định nghĩa. Không so sánh trực tiếp số revision của HR với số revision của cổng đối tác.

## 4. Định danh ổn định và mô hình dữ liệu tối thiểu

Bài tập có thể dùng mô hình khái niệm sau; đây không phải schema chuẩn của một sản phẩm:

~~~yaml
subject:
  subjectId: person-1042

relationship:
  relationshipId: employment-502
  subjectId: person-1042
  organizationId: org-anbinh
  type: EMPLOYEE
  state: ACTIVE
  source: HR
  sourceRecordId: hr-8842
  sourceVersion: 17

targetAccount:
  targetSystem: CRM
  targetTenant: tenant-anbinh
  targetAccountId: crm-user-603
  subjectId: person-1042

grant:
  grantId: grant-771
  relationshipId: employment-502
  permission: crm.customer.read.assigned
  scope: team-sales-a
  origin: job-policy-sales
  approvalReference: approval-230
  state: ACTIVE
~~~

Những điểm cần giải thích trong hồ sơ thiết kế:

- Định danh nội bộ không thay khi người dùng đổi tên hoặc email.
- Mã bản ghi nguồn luôn đi kèm định danh nguồn và phạm vi tổ chức.
- Mapping tài khoản đích được quản lý rõ, tránh tạo trùng khi retry.
- Mỗi grant có căn cứ, phạm vi và điều kiện kết thúc.
- Việc merge, tách hoặc khôi phục danh tính cần một quy trình riêng.

Nếu dùng SCIM, `id` do service provider cấp; `externalId` do provisioning client cấp và có phạm vi provisioning domain. Không mặc định server tự bảo đảm `externalId` duy nhất toàn cầu. [RFC 7643 — Common Attributes](https://www.rfc-editor.org/rfc/rfc7643.html#section-3.1).

Khi một email được cấp cho người mới, mapping không được kéo theo quyền, phiên hoặc tài nguyên riêng của người trước. Một email giống nhau chỉ là dữ kiện cần xử lý, không phải bằng chứng hai bản ghi cùng chủ thể.

## 5. Tách trạng thái nghiệp vụ khỏi trạng thái đồng bộ

Ví dụ trạng thái của **quan hệ**:

~~~text
PLANNED -> ACTIVE -> ENDED
               -> ON_LEAVE -> ACTIVE
~~~

Các chuyển tiếp này không tự mô tả mọi trạng thái tài khoản. Một tài khoản có thể được tạo trước ngày nhận việc nhưng chưa được truy cập nghiệp vụ; một quan hệ đang hoạt động vẫn có thể bị đình chỉ truy cập do sự cố.

Một mô hình tài khoản minh họa:

| Trạng thái | Ý nghĩa trong bài tập |
| --- | --- |
| PENDING | Đang chuẩn bị, chưa đủ điều kiện truy cập nghiệp vụ |
| ACTIVE | Có thể truy cập theo các grant còn hiệu lực |
| SUSPENDED | Bị chặn tạm thời theo quyết định có phạm vi |
| DISABLED | Không được sử dụng cho phạm vi đã kết thúc |
| ARCHIVED | Giữ hồ sơ theo policy, không khôi phục quyền |
| DELETED | Đã xử lý xóa theo ngữ nghĩa và phạm vi xác định |

Tách thêm trạng thái đồng bộ:

~~~text
desired = DISABLED
observed.CRM = DISABLED
observed.Finance = ACTIVE
convergence = PARTIAL_FAILURE
~~~

Kết quả này có nghĩa quyết định đã được xác lập nhưng chưa thực thi đủ. Không đổi `desired` trở lại `ACTIVE` chỉ để làm trạng thái tổng hợp trông đồng nhất.

Với mỗi chuyển tiếp, cần ghi chủ thể khởi tạo, điều kiện trước, mốc hiệu lực, tác động tới grant, phương tiện xác thực, phiên và tài nguyên đang sở hữu. “Đã nhận yêu cầu” khác với “đã chặn truy cập”.

## 6. Joiner: từ hồ sơ được duyệt đến quyền ban đầu

Luồng tiếp nhận Lan có thể được thiết kế như sau:

1. Nhận bản ghi quan hệ đã được nguồn có thẩm quyền xác lập.
2. Kiểm tra định danh, nguồn, thời điểm hiệu lực và khả năng trùng.
3. Tạo hoặc liên kết chủ thể theo quy tắc đã phê duyệt.
4. Tạo tài khoản cần thiết trong trạng thái chuẩn bị.
5. Hoàn tất đăng ký phương tiện xác thực qua luồng được bảo vệ.
6. Tính grant cơ bản theo công việc và phạm vi.
7. Chỉ cấp quyền nhạy cảm khi có căn cứ bổ sung.
8. Cho phép truy cập vào thời điểm đủ điều kiện.
9. Đối chiếu tài khoản và quyền thực tế tại các đích.

Ví dụ, email công việc được tạo trước ngày nhận việc không có nghĩa CRM được mở trước ngày nhận việc. Ngày hiệu lực phải được áp dụng vào quyết định truy cập, không chỉ hiển thị trong hồ sơ.

Thiết kế bước bootstrap phải nói rõ người nhận lời mời được làm gì. Một phiên dùng để hoàn tất enrollment có thể chỉ cho phép đăng ký phương tiện; nó không cần được cấp toàn bộ quyền nghiệp vụ ngay từ đầu.

Không gửi một mật khẩu dùng chung cho người quản lý và người mới. Nếu dùng lời mời, cần xác định thời hạn, phạm vi, cách xác nhận đúng người và điều kiện cấp lại khi lời mời thất bại.

Bộ test joiner cần có hồ sơ hợp lệ, hồ sơ bị hủy trước ngày bắt đầu, tạo tài khoản đích thành công nhưng mất response và lần gửi lại cùng yêu cầu.

## 7. Mover: tính lại quyền thay vì cộng dồn vai trò

Lan chuyển từ kinh doanh sang hỗ trợ khách hàng. Nếu luồng chỉ thêm nhóm mới mà không xét quyền cũ, tài khoản dần tích lũy quyền ngoài nhu cầu.

Trong ví dụ, bộ điều phối tính:

~~~text
desiredGrants =
    các grant còn căn cứ từ những quan hệ hợp lệ
    và các phê duyệt còn hiệu lực
    sau khi áp dụng ràng buộc, phủ định và policy hiện tại
~~~

Sau đó đối chiếu grant hiện có để xác định phần thêm, giữ và gỡ. Không chỉ so sánh hai tên role.

Ví dụ:

| Grant trước chuyển nhóm | Căn cứ sau chuyển nhóm | Hành động |
| --- | --- | --- |
| Đọc khách hàng nhóm kinh doanh | Công việc cũ đã kết thúc | Gỡ theo mốc hiệu lực |
| Xem hồ sơ cá nhân | Quan hệ nhân viên còn hiệu lực | Giữ |
| Xử lý ticket được phân công | Công việc mới | Cấp |
| Quyền đặc biệt có thời hạn | Cần xem lại phê duyệt | Không tự gia hạn |

Cùng một quyền có thể có hai căn cứ cấp còn hiệu lực. Khi gỡ một căn cứ, không xóa mù grant của căn cứ khác; đồng thời không được dùng nguồn cấp không hợp lệ để giữ quyền.

Nếu cần thời gian bàn giao, đó là một grant chuyển tiếp có phạm vi, người duyệt và thời điểm hết hạn. Không giữ vô thời hạn mọi quyền của nhóm cũ.

Với quyền xung đột, chẳng hạn vừa tạo vừa tự duyệt khoản chi, cần quyết định thứ tự gỡ/cấp phù hợp hoặc chặn thao tác nhạy cảm trong lúc chuyển đổi. Không hứa một giao dịch phân tán nguyên tử nếu các đích không hỗ trợ.

## 8. Leaver: kết thúc khả năng truy cập đầu cuối

Khi quan hệ của Minh hết hạn, thiết kế phải xác định chính xác phần cần kết thúc:

- Đăng nhập mới vào phạm vi đã hết hiệu lực.
- Tạo hoặc làm mới phiên và token.
- Quyền đã cấp ở ứng dụng đích.
- Phiên, credential cá nhân và đặc quyền đang tồn tại.
- Job hoặc ủy quyền thay mặt người dùng.
- Khả năng job cũ tự cấp lại quyền.
- Trách nhiệm quản lý tài nguyên cần bàn giao.

Không chỉ đổi cờ tại IdP rồi coi mọi ứng dụng đã chặn. Một ứng dụng có phiên riêng hoặc đường đăng nhập cục bộ có thể vẫn tiếp tục phục vụ người dùng.

NIST phân biệt phiên đăng nhập với access token; token và refresh token có thể còn tồn tại sau khi phiên kết thúc. Vì vậy, bài tập cần liệt kê từng loại khả năng truy cập thay vì coi logout là kết thúc tất cả. [NIST SP 800-63B-4 — Session Management](https://pages.nist.gov/800-63-4/sp800-63b/session/).

Nếu dùng OAuth token revocation, cần xác minh những token và grant chịu tác động, cùng khả năng truyền trạng thái tới điểm sử dụng. RFC 7009 có đề cập độ trễ truyền thông tin vô hiệu hóa trong triển khai. [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.1).

Người vận hành không nên đảo ngược việc thu hồi thành công ở CRM vì ứng dụng tài chính đang lỗi. Thay vào đó, giữ trạng thái mong muốn, theo dõi đích chưa đạt và áp dụng biện pháp hạn chế trong đúng phạm vi được thiết kế.

## 9. Mốc hiệu lực và thời hạn thu hồi

Phải phân biệt:

| Mốc | Ý nghĩa |
| --- | --- |
| Nguồn xác lập quyết định | HR hoặc người bảo trợ ghi nhận thay đổi |
| Effective time | Thời điểm thay đổi phải có hiệu lực về nghiệp vụ |
| Received time | Bộ điều phối nhận sự kiện |
| Applied time | Một đích ghi nhận thay đổi |
| Observed denial | Phép thử quan sát truy cập bị chặn đúng |

Giả định riêng của bài tập: với quan hệ kết thúc lúc T0, An Bình đặt các mục tiêu sau:

| Kết quả | Mục tiêu minh họa |
| --- | --- |
| Chặn tạo truy cập mới qua IdP trong phạm vi kết thúc | T0 + 1 phút |
| Xử lý phiên và credential cá nhân theo danh mục đã chốt | T0 + 5 phút |
| Các ứng dụng đích đạt trạng thái truy cập mong đợi | T0 + 15 phút |
| Đối soát xác nhận không có drift còn mở | T0 + 24 giờ |

Mốc đối soát không gia hạn thời hạn chặn truy cập. Nếu ứng dụng vẫn phục vụ người dùng sau 15 phút, chạy đối soát vào ngày hôm sau không làm kết quả đó trở thành đạt.

Các con số chỉ dùng để luyện tập đặt yêu cầu đo được. Nếu đích hoặc kiến trúc không hỗ trợ, người học cần ghi khoảng trống thiết kế và phương án xử lý, không đổi cách đo để che lỗi.

Sự kiện có thể đến sau effective time. Khi đó, hệ thống cần áp dụng thay đổi ngay khi biết, ghi nhận việc quá hạn và giữ nguyên mốc đo. Không chỉ tính từ lúc connector bắt đầu chạy rồi kết luận đúng hạn.

Với sự kiện tương lai, cần cơ chế thực thi đúng mốc và cơ chế phát hiện lịch bị bỏ lỡ sau restart. Thời gian phải có múi giờ hoặc offset rõ; đồng hồ và độ trễ quan sát cũng cần được xét khi báo cáo.

## 10. Thiết kế sự kiện có thể phát lại và đối chiếu

Một sự kiện minh họa của bài tập:

~~~json
{
  "eventId": "evt-hr-00418",
  "eventType": "RELATIONSHIP_CHANGED",
  "source": "HR",
  "organizationId": "org-anbinh",
  "sourceRecordId": "hr-8842",
  "relationshipId": "employment-502",
  "sourceVersion": 18,
  "effectiveAt": "2027-03-01T17:00:00+07:00",
  "newState": "ENDED",
  "reasonCode": "RELATIONSHIP_END"
}
~~~

Ngày trong ví dụ là dữ liệu giả định. Payload không chứa mật khẩu, token hoặc bản scan giấy tờ.

Hợp đồng sự kiện cần nêu rõ:

- Ai được phát và cách xác thực nguồn.
- Khóa định danh và miền giá trị của revision.
- Sự kiện là trạng thái đầy đủ hay thay đổi từng phần.
- Cách xử lý trường thiếu, schema không được hỗ trợ và chữ ký không hợp lệ.
- Khóa phát hiện trùng và cách tiếp tục công việc chưa hoàn tất.
- Cách lấy trạng thái mới nhất khi nghi ngờ thiếu sự kiện.
- Mốc hiệu lực và quy tắc giải quyết thay đổi có hiệu lực hồi tố.

Nếu nguồn chỉ phát delta, bộ nhận phải có quy tắc phát hiện thiếu revision hoặc cách đọc lại snapshot. Không áp một bản vá lên trạng thái không xác định rồi coi kết quả là chắc chắn đúng.

Mã giả minh họa luồng nội bộ:

~~~text
xác minh nguồn và schema của sự kiện
xác định đúng tổ chức, bản ghi nguồn và quan hệ

trong transaction nội bộ:
    kiểm tra sổ sự kiện đã nhận
    nếu là sự kiện trùng:
        giữ kết quả đã nhận và bảo đảm job còn dang dở được tiếp tục
    nếu là revision cũ theo hợp đồng nguồn:
        ghi nhận bỏ qua, không áp trạng thái cũ
    nếu có khoảng trống không thể giải thích:
        yêu cầu đối soát nguồn, không đoán dữ liệu
    nếu hợp lệ:
        cập nhật snapshot nguồn đã chấp nhận
        tính lại trạng thái mong muốn
        ghi intent đồng bộ cùng revision mong muốn
        ghi sự kiện cần phát vào outbox

ngoài transaction:
    phát công việc tới connector
    theo dõi từng đích đến khi xác minh được kết quả
~~~

Outbox ở đây giúp nối cập nhật trạng thái và việc phát công việc trong thiết kế minh họa. Bên nhận vẫn phải xử lý khả năng gửi lại; không suy ra mọi hệ thống đích tham gia cùng transaction.

Một event trùng không nên tạo tài khoản thứ hai. Nhưng chỉ lưu eventId rồi bỏ mọi lần nhận lại cũng không đủ nếu lần trước mới cập nhật hồ sơ mà chưa hoàn tất đồng bộ.

## 11. Connector, SCIM và việc xác nhận trạng thái tại đích

Mỗi đích cần có hợp đồng rõ:

| Nội dung | Câu hỏi phải trả lời |
| --- | --- |
| Mapping | Tài khoản nào tương ứng với chủ thể và quan hệ? |
| Tạo/cập nhật | Có cách tránh tạo trùng khi mất response không? |
| Vô hiệu hóa | Ngăn những đường truy cập nào? |
| Membership | Xóa nhóm có thực sự gỡ quyền hiệu lực không? |
| Phiên/credential | Có API hoặc cơ chế xử lý riêng không? |
| Readback | Đọc gì để biết kết quả đã áp dụng? |
| Lỗi | Lỗi nào retry, lỗi nào cần người xử lý? |

Trong SCIM, thuộc tính `active` mô tả trạng thái quản trị; ngữ nghĩa cụ thể phụ thuộc service provider. Không mặc định `active: false` đã thu hồi mọi phiên, khóa API hoặc quyền trên dữ liệu. [RFC 7643 — User Resource](https://www.rfc-editor.org/rfc/rfc7643.html#section-4.1.1).

SCIM DELETE có yêu cầu về cách xử lý tài nguyên đã xóa trong giao thức, nhưng service provider có thể không xóa vật lý vĩnh viễn. Vì vậy, xóa tài khoản truy cập và xử lý lưu giữ dữ liệu là hai quyết định cần phân biệt. [RFC 7644 — Deleting Resources](https://www.rfc-editor.org/rfc/rfc7644.html#section-3.6).

Một ví dụ PATCH chỉ để minh họa thao tác SCIM:

~~~http
PATCH /scim/v2/Users/<target-account-id>
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Đường dẫn endpoint là giả định triển khai; connector thực tế cần xác thực và quyền phù hợp. Cú pháp PATCH được mô tả tại [RFC 7644, mục 3.5.2](https://www.rfc-editor.org/rfc/rfc7644.html#section-3.5.2).

Response thành công cần được đối chiếu với trạng thái quản trị và hành vi truy cập quan trọng. Nếu request timeout sau khi đích đã áp dụng, connector nên xác minh trạng thái trước khi quyết định tạo lại hay thực hiện hành động khác.

Trạng thái tổng hợp phải giữ được thông tin “đích A đã đạt, đích B chưa xác minh”. Không ép mọi lỗi thành một nhãn thành công hoặc gửi lại mù cùng một thao tác có tác dụng phụ.

## 12. Chống cấp lại quyền bởi sự kiện và job cũ

Tình huống khó của bài tập:

~~~text
1. Job cấp quyền cho Lan đã được tạo nhưng chưa chạy.
2. HR kết thúc quan hệ; hệ thống tính desired = DISABLED.
3. Connector vô hiệu hóa tài khoản.
4. Job cấp quyền cũ tiếp tục và gửi yêu cầu enable tới đích.
~~~

Chỉ kiểm tra eventId trùng không ngăn được tình huống này. Job cấp quyền có thể là sự kiện khác hoàn toàn hợp lệ tại thời điểm nó được tạo.

Thiết kế connector cần xét revision mong muốn hiện tại trước khi thực hiện và khi ghi nhận kết quả. Nếu đích hỗ trợ cập nhật có điều kiện hoặc cơ chế chặn lệnh cũ, cần sử dụng đúng. Việc xử lý công việc theo từng tài khoản cũng giúp giảm cạnh tranh.

Tuy nhiên, kiểm tra revision ở phía local chưa đủ nếu một lệnh enable cũ đã rời hệ thống và đang được đích xử lý. Request timeout không chứng minh lệnh đã bị hủy.

Với đích không hỗ trợ điều kiện cập nhật phù hợp, bài thiết kế phải nêu cách xử lý lệnh chưa xác định kết quả: dừng phát grant mới trong phạm vi, xác minh lại đích, tiếp tục áp trạng thái mới và giữ kiểm soát chặn truy cập độc lập nếu có. Nếu vẫn không bảo đảm thời hạn đề bài, đó là rủi ro hoặc blocker cần ghi nhận.

Không gắn nhãn hoàn tất chỉ vì lần gọi disable gần nhất trả thành công. Cần biết còn lệnh cũ đang bay, hàng đợi cũ hoặc job đối soát nào có thể làm tài khoản hoạt động trở lại hay không.

## 13. MFA, khôi phục và khóa khẩn cấp

Vòng đời user còn bao gồm vòng đời phương tiện xác thực. NIST SP 800-63B-4 phân biệt việc gắn thêm phương tiện, thay thế, mất hoặc lộ phương tiện và account recovery; đây là các sự kiện cần quản lý riêng. [Authenticator Event Management](https://pages.nist.gov/800-63-4/sp800-63b/events/).

Trong capstone, người học cần thiết kế các đường:

| Sự kiện | Yêu cầu thiết kế trong bài tập |
| --- | --- |
| Đăng ký ban đầu | Xác nhận đúng chủ thể, giới hạn quyền bootstrap |
| Thêm phương tiện | Xác thực theo policy và thông báo phù hợp |
| Mất phương tiện | Xử lý phương tiện cũ và kiểm soát quyền thêm mới |
| Recovery | Có căn cứ khôi phục, không chỉ hỏi tên/email |
| Khóa an ninh | Ngăn luồng HR bình thường tự gỡ khóa |
| Kết thúc quan hệ | Đóng các khả năng truy cập thuộc phạm vi |

Hương có quyền hỗ trợ vận hành không có nghĩa được tùy ý reset MFA của mọi tài khoản đặc quyền. Thiết kế cần xác định phạm vi hỗ trợ, sự kiện cần phê duyệt và bằng chứng hành động.

Khóa an ninh tạm thời cũng không nên làm mất lịch sử trạng thái quan hệ. Khi gỡ khóa, hệ thống tính lại quyền từ căn cứ hiện tại, không khôi phục nguyên một snapshot quyền cũ đã hết hiệu lực trong thời gian khóa.

## 14. Nghỉ tạm thời, quay lại và chuyển giao tài nguyên

Những trường hợp này cần được thiết kế trước, thay vì xử lý bằng thao tác quản trị tùy ý.

**Nghỉ tạm thời:** quan hệ có thể còn tồn tại nhưng một số quyền bị dừng. Cần xác định quyền nào giữ, lịch tiếp tục dự kiến và điều kiện kích hoạt lại. Một ngày dự kiến quay lại không nên tự mở quyền nếu nguồn chưa xác nhận điều kiện cần thiết.

**Quay lại tổ chức:** phải xác nhận đúng chủ thể và quyết định tái sử dụng hay tạo tài khoản theo policy. Nếu tạo quan hệ mới, nguồn cấp quyền cần phản ánh quan hệ mới. Không tự khôi phục mọi đặc quyền của lần làm việc trước.

**Tài nguyên sở hữu:** lập danh sách kho tài liệu, báo cáo định kỳ, tài khoản tích hợp và workload mà người dùng có trách nhiệm quản lý. Xác định ai nhận bàn giao và credential nào cần thay đổi.

Ví dụ, Minh sở hữu lịch xuất báo cáo cho nhóm nhưng job dùng workload identity riêng. Kết thúc tài khoản Minh không nhất thiết xóa workload đó; nhóm cần chuyển trách nhiệm và kiểm tra quyền của workload. Nếu job thay mặt chính Minh thì cần xét quyền thực thi theo policy khác.

**Lưu giữ và xóa:** quyền truy cập có thể đã kết thúc trong khi hồ sơ hoặc bằng chứng vẫn được giữ theo policy đã xác lập. Thiết kế cần nêu phạm vi dữ liệu, người có quyền xử lý và điều kiện kết thúc lưu giữ, không tự chọn một thời hạn chung cho mọi dữ liệu.

## 15. Quan sát, đối soát và trách nhiệm vận hành

Hồ sơ mỗi lần thay đổi nên nối được chuỗi:

~~~text
nguồn quyết định
  -> quan hệ và revision được chấp nhận
  -> trạng thái và grant mong muốn
  -> job theo từng hệ thống đích
  -> kết quả thao tác
  -> readback và thử truy cập
  -> kết luận cùng phần còn mở
~~~

Các chỉ số minh họa:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Thay đổi quá hạn | Không đạt thời hạn theo mốc hiệu lực |
| Đích chưa hội tụ | Desired và observed còn khác |
| Tài khoản mồ côi | Có account nhưng không tìm được căn cứ hợp lệ |
| Grant không rõ nguồn | Không đối chiếu được quyền với quyết định |
| Lỗi connector kéo dài | Cần xử lý ngoài retry tự động |
| Sự kiện cũ cố làm mở quyền | Kiểm tra nguy cơ quay lại trạng thái không phù hợp |
| Quyền hết hạn còn tồn tại | Job hết hạn hoặc việc đồng bộ chưa hiệu lực |

Đối soát là so sánh trạng thái thực tế với trạng thái được quyết định từ nguồn hợp lệ. Không chỉ tìm xem tài khoản có tồn tại ở hai bên hay không.

Khi phát hiện grant do thao tác thủ công, cần xác định nó có phê duyệt còn hiệu lực hay là drift. Không mặc định giữ mọi quyền tìm thấy, cũng không xóa mọi quyền khác baseline mà chưa hiểu nguồn cấp.

Phân công rõ ai chịu trách nhiệm xử lý nguồn sai, connector lỗi, ngoại lệ quyền và xác nhận tác động nghiệp vụ. Một cảnh báo không có chủ xử lý không phải cơ chế khắc phục hoàn chỉnh.

## 16. Bộ ca nghiệm thu tối thiểu cho capstone

Chỉ dùng tài khoản và dữ liệu tổng hợp trong môi trường thực hành. Mỗi ca cần baseline, trigger, kết quả mong đợi và bằng chứng.

| Mã | Tình huống | Điều cần chứng minh |
| --- | --- | --- |
| J01 | Nhận việc trong tương lai | Không mở quyền nghiệp vụ trước mốc |
| J02 | Hủy trước ngày bắt đầu | Lời mời/job cũ không làm tài khoản hoạt động |
| J03 | Tạo đích thành công nhưng mất response | Retry không tạo tài khoản trùng |
| M01 | Chuyển nhóm | Quyền cũ hết căn cứ được gỡ, quyền mới đúng phạm vi |
| M02 | Quyền có hai nguồn cấp | Gỡ đúng căn cứ, không xử lý nhầm nguồn còn hợp lệ |
| L01 | Hết hạn cộng tác | Đăng nhập mới và phiên cũ đạt yêu cầu thời gian |
| L02 | Một ứng dụng đích ngừng hoạt động | Không báo hoàn tất toàn bộ; phần lỗi còn được theo dõi |
| E01 | Sự kiện trùng | Không lặp tác động ngoài dự kiến |
| E02 | Revision cũ tới sau leaver | Không mở lại quyền |
| E03 | Lệnh enable cũ chưa rõ kết quả | Không bỏ qua nguy cơ ghi đè ở đích |
| R01 | Người dùng quay lại | Không tự khôi phục đặc quyền cũ |
| S01 | Khóa an ninh rồi HR cập nhật | Cập nhật thông thường không tự gỡ khóa |
| T01 | Một người có nhiều quan hệ | Kết thúc đúng phạm vi, không ảnh hưởng nhầm |
| O01 | Đối soát phát hiện account mồ côi | Có quyết định và chủ xử lý |
| A01 | Mất phương tiện xác thực | Recovery không tạo đường chiếm tài khoản |

Một ca leaver cần chuẩn bị phiên và credential còn hợp lệ trước T0. Nếu token tự hết hạn trước khi phép thử bắt đầu, kết quả từ chối không chứng minh cơ chế thu hồi đã hoạt động.

Cũng cần tài khoản đối chứng vẫn có quan hệ và quyền hợp lệ. Điều đó giúp phát hiện một luồng vô hiệu hóa nhầm toàn tenant hoặc chặn mọi người khi chỉ một quan hệ kết thúc.

Khi quan sát bằng polling, ghi khoảng lấy mẫu. Lần đầu thấy bị chặn là mốc quan sát, không nhất thiết đúng thời điểm hệ thống thực sự chuyển trạng thái.

## 17. Sản phẩm thiết kế cần bàn giao

Một bộ thiết kế capstone có thể gồm:

1. Phạm vi, giả định và danh mục đường truy cập.
2. Ma trận nguồn có thẩm quyền cùng quy tắc xử lý mâu thuẫn.
3. Mô hình chủ thể, quan hệ, tài khoản, grant và định danh.
4. Bảng chuyển trạng thái với điều kiện và thời điểm hiệu lực.
5. Luồng joiner, mover, leaver, khóa, recovery và quay lại.
6. Hợp đồng sự kiện, xử lý trùng, sai thứ tự và lịch tương lai.
7. Hợp đồng connector và cơ chế xác minh theo từng đích.
8. Mục tiêu thời gian, chỉ số, cảnh báo và trách nhiệm xử lý.
9. Ma trận kiểm thử, dữ liệu tổng hợp và mẫu bằng chứng.
10. Danh sách khoảng trống, ngoại lệ và quyết định còn cần giải quyết.

Ví dụ một dòng bằng chứng:

~~~yaml
scenario: L01
relationshipId: partner-201
desiredRevision: 24
effectiveTime: T0
targets:
  idp:
    result: VERIFIED_DENIED
  crm:
    result: VERIFIED_DISABLED
  finance:
    result: NOT_VERIFIED_CONNECTOR_UNAVAILABLE
overallResult: INCOMPLETE
followUpOwner: iam-operations
~~~

Đây là mẫu báo cáo của bài tập, không phải kết quả đã chạy. Không đổi `INCOMPLETE` thành `PASS` vì phần lớn đích đã đạt.

Một thiết kế có thể nghiệm thu được phải cho phép người khác lần theo một thay đổi cụ thể: nguồn nào quyết định, quyền nào bị tác động, đích nào đã thực thi và còn điểm nào chưa có bằng chứng. Khi đó, user lifecycle trở thành quá trình quản lý truy cập có trách nhiệm và khả năng kiểm chứng, thay vì một tập script tạo/xóa tài khoản.
