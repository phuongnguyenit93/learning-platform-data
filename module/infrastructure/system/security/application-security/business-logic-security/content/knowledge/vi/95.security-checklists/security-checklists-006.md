# Release review checklist — Bảo mật logic nghiệp vụ

## 1. Mục tiêu của buổi release review

Release review là điểm kiểm soát trước khi đưa một thay đổi vào vận hành. Với bảo mật logic nghiệp vụ, câu hỏi trung tâm là: **sau thay đổi này, hệ thống có còn giữ đúng các quy tắc nghiệp vụ khi người gọi cố tình thao tác ngoài luồng dự kiến không?**

Một API trả về đúng mã HTTP, giao diện chạy trơn tru hoặc bộ kiểm thử thông thường chạy thành công chưa đủ trả lời câu hỏi đó. Người dùng có thể tự gửi yêu cầu, đổi định danh đối tượng, gọi lại bước cũ, gửi đồng thời hai thao tác hoặc giữ một yêu cầu từ phiên bản trước rồi phát lại sau khi triển khai.

Checklist này dùng để đánh giá thay đổi thuộc module bảo mật logic nghiệp vụ: bảo vệ quy trình phê duyệt, giá và hạn mức, quyền theo đối tượng, thao tác chuyển trạng thái, transaction, idempotency và các đường xử lý đồng bộ lẫn bất đồng bộ. Nó không thay thế đánh giá nghiệp vụ hoặc toàn bộ quy trình phát hành của tổ chức.

**Kết quả cần có** là một quyết định có bằng chứng: được phát hành, được phát hành với giới hạn đã phê duyệt, hoặc bị chặn cho đến khi xử lý xong vấn đề cụ thể.

## 2. Khi nào phải dùng checklist?

Áp dụng checklist khi phát hành một thay đổi có thể ảnh hưởng đến điều kiện thực hiện hành động hoặc kết quả kinh doanh, kể cả khi thay đổi không sửa trực tiếp mã kiểm tra bảo mật.

Ví dụ:

- Thêm API duyệt, hủy, thanh toán, hoàn tiền hoặc xuất dữ liệu.
- Đổi cách tính giá, giảm giá, phí, hạn mức hoặc điều kiện hưởng ưu đãi.
- Bổ sung vai trò, chia sẻ đối tượng, chuyển chủ sở hữu hoặc hỗ trợ nhiều tenant.
- Thay transaction, khóa, xử lý đồng thời, cache hoặc cách đọc dữ liệu.
- Chuyển xử lý sang hàng đợi; thêm retry, webhook hoặc tác vụ định kỳ.
- Sửa schema, chuyển đổi dữ liệu, bật feature flag hoặc thay đổi cấu hình nghiệp vụ.

Đánh giá theo mức độ ảnh hưởng của thay đổi. Một mục không áp dụng được phép ghi **N/A**, nhưng phải có lý do gắn với phạm vi thực tế. Không bỏ qua toàn bộ checklist chỉ vì bản phát hành được gọi là “sửa nhỏ”.

## 3. Hồ sơ đầu vào và cách ghi bằng chứng

Trước buổi review, chuẩn bị mô tả thay đổi, sơ đồ luồng bị ảnh hưởng, các quy tắc phải giữ và kết quả kiểm thử tương ứng. Mỗi mục kiểm tra nên có một dòng ghi nhận như sau:

| Trường | Nội dung cần ghi |
| --- | --- |
| Mục kiểm tra | Mã mục và quy tắc đang được kiểm soát |
| Phạm vi | Endpoint, lệnh, worker, webhook hoặc dữ liệu liên quan |
| Kết quả | PASS, FAIL hoặc N/A |
| Bằng chứng | Liên kết nội bộ đến thay đổi, kết quả kiểm thử, log đã che dữ liệu nhạy cảm hoặc báo cáo |
| Người chịu trách nhiệm | Người có thể giải thích và xử lý phát hiện |
| Việc còn lại | Điều kiện đóng lỗi, hạn xử lý và người chấp thuận nếu có ngoại lệ |

PASS cần thể hiện cả hành vi mong đợi lẫn trạng thái dữ liệu sau thao tác. Một ảnh chụp giao diện báo lỗi không chứng minh rằng số dư, tồn kho hoặc trạng thái phê duyệt chưa bị thay đổi ở phía sau.

Một bằng chứng tốt thường gồm:

1. Trạng thái ban đầu và danh tính người thực hiện.
2. Yêu cầu hoặc chuỗi hành động được gửi.
3. Phản hồi quan sát được.
4. Trạng thái cuối trong nguồn dữ liệu có thẩm quyền.
5. Tác động phụ: thông điệp, khoản thu, email, thay đổi hạn mức hoặc audit event.

Không đưa token truy cập, khóa bí mật, thông tin thanh toán đầy đủ hoặc dữ liệu cá nhân không cần thiết vào hồ sơ review.

## 4. Bối cảnh mẫu xuyên suốt

Giả sử hệ thống có quy trình đơn hàng:

~~~text
DRAFT → SUBMITTED → APPROVED → PAYMENT_PENDING → PAID → FULFILLED
                      │                │
                      └→ CANCELLED     └→ PAYMENT_FAILED
~~~

Đây là sơ đồ rút gọn; điều kiện hủy, thử thanh toán lại và hoàn tiền phải được đặc tả riêng. Không suy ra một chuyển trạng thái được phép chỉ vì tên trạng thái có vẻ hợp lý.

Các quy tắc ví dụ:

- Tổng tiền phải được máy chủ tính từ dữ liệu có thẩm quyền.
- Người duyệt phải có quyền trên đúng đơn và đúng tenant.
- Người tạo không được tự duyệt nếu quy trình yêu cầu phân tách nhiệm vụ.
- Sửa các trường ảnh hưởng đến phê duyệt làm mất hiệu lực phê duyệt cũ.
- Một đơn chỉ có tối đa một khoản thu thành công cho nghĩa vụ thanh toán ban đầu.
- Tổng số tiền hoàn thành công cộng phần đã giữ chỗ cho yêu cầu hoàn đang xử lý không vượt quá số tiền có thể hoàn.
- Một hành động bị từ chối không được để lại thay đổi nghiệp vụ dở dang.

Các quy tắc này là ví dụ để minh họa cách review. Nhóm triển khai phải ghi quy tắc cụ thể của sản phẩm, gồm cả các trường hợp ngoại lệ được nghiệp vụ cho phép.

## 5. Checklist A — Phạm vi thay đổi và bề mặt có thể bị lạm dụng

- [ ] **A1.** Liệt kê toàn bộ điểm vào bị ảnh hưởng: API công khai, API nội bộ, giao diện quản trị, batch, import, webhook, hàng đợi và tác vụ định kỳ.
- [ ] **A2.** Mô tả các tài sản nghiệp vụ cần bảo vệ: tiền, tồn kho, hạn mức, quyền phê duyệt, dữ liệu hoặc quyền hưởng ưu đãi.
- [ ] **A3.** Chỉ rõ trường nào do người gọi cung cấp và trường nào máy chủ quyết định.
- [ ] **A4.** Ghi các phụ thuộc: dịch vụ giá, cổng thanh toán, kho, danh tính, chính sách quyền và cấu hình.
- [ ] **A5.** Đã xét đường xử lý cũ còn hoạt động trong giai đoạn triển khai và các yêu cầu được tạo trước release.
- [ ] **A6.** Có người chịu trách nhiệm nghiệp vụ xác nhận những thay đổi về quy tắc hoặc ngoại lệ.

**Câu hỏi kiểm tra:** Nếu người dùng bỏ qua giao diện và chỉ gọi API, họ còn đường nào để tạo ra cùng tác động nghiệp vụ?

Một endpoint mới kiểm tra đủ điều kiện không giúp bảo vệ toàn bộ quy trình nếu endpoint cũ, import hoặc worker vẫn cho phép sửa thẳng trạng thái cuối. Các điểm vào có thể dùng cơ chế khác nhau, nhưng phải cùng bảo vệ quy tắc tương ứng.

## 6. Checklist B — Business invariants và dữ liệu có thẩm quyền

Business invariant là điều kiện phải luôn đúng ở các ranh giới nghiệp vụ đã xác định. Với xử lý bất đồng bộ, cần nói rõ điều kiện nào phải đúng ngay sau commit và điều kiện nào được hoàn tất sau, trong khoảng thời gian và cơ chế phục hồi nào.

| Mã | Điều cần xác nhận | Bằng chứng phù hợp |
| --- | --- | --- |
| B1 | Mỗi quy tắc quan trọng được viết thành điều kiện có thể kiểm tra | Đặc tả điều kiện, dữ liệu đầu vào và ranh giới áp dụng |
| B2 | Máy chủ tính hoặc xác thực lại giá, phí, thuế, hạn mức và điều kiện ưu đãi | Ca sửa giá, số lượng, tiền tệ hoặc mã ưu đãi trong request |
| B3 | Số âm, số bằng không, giá trị quá lớn và độ chính xác số học được xử lý theo quy tắc | Ca biên về số lượng, số tiền và làm tròn |
| B4 | Quy tắc tổng hợp được giữ khi có nhiều bản ghi liên quan | Ca hoàn tiền nhiều lần, dùng ưu đãi nhiều đơn hoặc vượt tổng hạn mức |
| B5 | Thay đổi dữ liệu quan trọng làm vô hiệu quyết định cũ khi cần | Ca sửa đơn sau duyệt hoặc thay giá trị đã được ký duyệt |
| B6 | Lỗi phụ thuộc không biến thành chấp nhận vô điều kiện | Ca timeout hoặc lỗi đọc chính sách, giá và hạn mức |
| B7 | Cấu hình nghiệp vụ có kiểm soát quyền và được kiểm tra tính hợp lệ | Ca nhập cấu hình sai hoặc thay cấu hình trong lúc xử lý |

### Ví dụ: sửa giá từ phía client

~~~json
{
  "orderId": "O-663",
  "quantity": 3,
  "unitPrice": 1,
  "approved": true,
  "total": 3
}
~~~

Review phải xác định endpoint có chấp nhận những trường như `unitPrice`, `approved` hoặc `total` không. Nếu người gọi không có quyền quyết định chúng, máy chủ phải từ chối hoặc bỏ qua theo hợp đồng API rõ ràng, rồi lấy giá và trạng thái từ nguồn có thẩm quyền.

Nếu sản phẩm cho phép sửa giá bằng quyền đặc biệt, đó là một thao tác nghiệp vụ riêng: cần kiểm tra quyền, phạm vi, giới hạn và ghi nhận lý do. Không dùng chung khả năng đó với API cập nhật đơn thông thường.

Với báo giá có thời hạn, xác nhận rõ giá được cố định từ thời điểm nào, hết hạn ra sao và dữ liệu nào gắn với báo giá. “Luôn lấy giá mới nhất” cũng có thể sai nếu hợp đồng nghiệp vụ cam kết giữ giá trong một khoảng thời gian.

## 7. Checklist C — State machine và quy trình phê duyệt

- [ ] **C1.** Có danh sách trạng thái và bảng chuyển trạng thái được phép.
- [ ] **C2.** Mỗi chuyển trạng thái có actor, tiền điều kiện và tác động phụ được xác định.
- [ ] **C3.** Máy chủ kiểm tra trạng thái hiện tại từ nguồn có thẩm quyền.
- [ ] **C4.** Không có API cập nhật chung cho phép sửa trực tiếp các trường như `status`, `approvedBy`, `paidAt` hoặc `approvalVersion` ngoài luồng được phép.
- [ ] **C5.** Không thể nhảy bước, lùi bước hoặc gọi lại một bước để nhận thêm lợi ích.
- [ ] **C6.** Quy tắc phân tách nhiệm vụ được kiểm tra nếu áp dụng.
- [ ] **C7.** Phê duyệt gắn với đúng phiên bản hoặc nội dung cần phê duyệt.
- [ ] **C8.** Có quyết định rõ với phê duyệt hết hạn, bị thu hồi hoặc mất hiệu lực.
- [ ] **C9.** Callback, worker và tác vụ quản trị tuân theo cùng quy tắc chuyển trạng thái.
- [ ] **C10.** Hai hành động cạnh tranh không thể cùng thành công khi kết quả của chúng loại trừ nhau.

Bảng chuyển trạng thái ví dụ:

| Hành động | Trạng thái nguồn | Điều kiện bổ sung | Trạng thái đích |
| --- | --- | --- | --- |
| Gửi duyệt | DRAFT | Dữ liệu bắt buộc đầy đủ | SUBMITTED |
| Duyệt | SUBMITTED | Có quyền duyệt; đáp ứng phân tách nhiệm vụ | APPROVED |
| Khởi tạo thanh toán | APPROVED | Phê duyệt còn hiệu lực; số tiền đã được xác định | PAYMENT_PENDING |
| Xác nhận thanh toán | PAYMENT_PENDING | Sự kiện hợp lệ; đúng giao dịch, số tiền và tiền tệ | PAID |
| Giao hàng | PAID | Đủ điều kiện giao và chưa thực hiện tác động này | FULFILLED |

**Ca cần chứng minh:** người tạo gửi duyệt đơn, người khác duyệt, sau đó người tạo sửa số lượng. Hành vi phải khớp đặc tả: hoặc chặn sửa, hoặc hủy hiệu lực phê duyệt và yêu cầu duyệt lại. Không được giữ phê duyệt cũ cho nội dung mới mà người duyệt chưa xem.

## 8. Checklist D — Quyền theo đối tượng, tenant và hành động

Xác thực người gọi chỉ trả lời họ là ai. Release review còn phải xác nhận họ có được thực hiện hành động cụ thể trên đối tượng cụ thể trong ngữ cảnh hiện tại hay không.

- [ ] **D1.** Quyền được kiểm tra ở máy chủ cho từng hành động nghiệp vụ.
- [ ] **D2.** Các định danh trong path, query, body và bản ghi con đều được kiểm tra quan hệ sở hữu hoặc phạm vi truy cập.
- [ ] **D3.** Tenant đáng tin cậy được suy ra từ ngữ cảnh đã xác thực và được kiểm tra với đối tượng; không tin một `tenantId` tùy ý từ client.
- [ ] **D4.** Vai trò chung như “manager” không tự động cho quyền trên mọi đối tượng.
- [ ] **D5.** Có kiểm tra quyền ở mức trường khi một số thuộc tính nhạy cảm cần quyền riêng.
- [ ] **D6.** Batch và import kiểm tra từng đối tượng; cách xử lý thành công một phần được định nghĩa rõ.
- [ ] **D7.** Quyền tạm thời, chia sẻ, chuyển chủ sở hữu và thu hồi quyền có hành vi đã xác định.
- [ ] **D8.** Worker xác định rõ quyền dựa trên ủy quyền đã được ghi nhận hay kiểm tra lại quyền hiện tại, theo chính sách của thao tác.
- [ ] **D9.** Truy cập bị từ chối không làm lộ dữ liệu hoặc gây tác động phụ không được phép.
- [ ] **D10.** Tài khoản dịch vụ có phạm vi phù hợp; việc dùng tài khoản dịch vụ không bỏ qua kiểm tra ngữ cảnh nghiệp vụ.

Ma trận thử tối thiểu:

| Danh tính và mục tiêu | Ví dụ cần thử |
| --- | --- |
| Người sở hữu, đúng tenant | Thực hiện hành động hợp lệ trên đơn của mình |
| Người khác, cùng tenant | Thay ID để sửa hoặc đọc đơn không được chia sẻ |
| Người có vai trò phù hợp, sai tenant | Duyệt đơn của tenant khác |
| Người từng có quyền | Gọi lại sau khi bị thu hồi hoặc chuyển chủ sở hữu |
| Người có quyền đọc | Thử hành động sửa, duyệt, hủy hoặc hoàn tiền |
| Tài khoản dịch vụ | Gửi lệnh thiếu ngữ cảnh hoặc có đối tượng ngoài phạm vi |

ID khó đoán không phải bằng chứng phân quyền. Kiểm thử cần dùng ID có thật của một đối tượng mà người gọi không được phép thao tác.

## 9. Checklist E — Transaction, cạnh tranh và giới hạn nhất quán

Một mẫu lỗi điển hình là “đọc điều kiện, thấy hợp lệ, rồi cập nhật” trong khi một yêu cầu khác có thể thay đổi điều kiện ở giữa. Kiểm tra đúng trong từng request vẫn có thể cho kết quả sai khi chúng chạy đồng thời.

- [ ] **E1.** Chỉ rõ dữ liệu nào phải thay đổi nguyên tử trong cùng một transaction.
- [ ] **E2.** Kiểm tra và cập nhật điều kiện quan trọng được bảo vệ bằng cơ chế cạnh tranh phù hợp.
- [ ] **E3.** Có xử lý xung đột: từ chối, đọc lại và đánh giá lại, hoặc retry có giới hạn.
- [ ] **E4.** Constraint ở cơ sở dữ liệu bảo vệ các điều kiện phù hợp như duy nhất một bản ghi theo khóa nghiệp vụ.
- [ ] **E5.** Quy tắc trải trên nhiều hàng có cơ chế bảo vệ riêng; không coi kiểm tra từng hàng là đủ.
- [ ] **E6.** Không dựa vào cache hoặc replica có độ trễ để quyết định điều kiện cần nhất quán tức thời.
- [ ] **E7.** Kiểm thử lỗi giữa chừng chứng minh dữ liệu không dở dang sau rollback.
- [ ] **E8.** Tác động ngoài cơ sở dữ liệu có chiến lược nhất quán và phục hồi được mô tả.
- [ ] **E9.** Retry không lặp lại tác động không thể rollback.
- [ ] **E10.** Cơ chế khóa hoạt động đúng khi chạy nhiều instance; không chỉ khóa trong bộ nhớ một tiến trình.

### Ví dụ: hai lần duyệt cạnh tranh

Cập nhật có điều kiện có thể dùng làm một phần của cơ chế kiểm soát:

~~~sql
UPDATE orders
SET status = 'APPROVED',
    approved_by = :actor_id,
    version = version + 1
WHERE id = :order_id
  AND tenant_id = :tenant_id
  AND status = 'SUBMITTED'
  AND version = :expected_version;
~~~

Ứng dụng phải kiểm tra số hàng được cập nhật. Kết quả bằng 0 nghĩa là điều kiện không còn đúng hoặc đối tượng không khớp phạm vi; không được tiếp tục phát tác động như thể đã duyệt thành công.

Đoạn SQL minh họa không thay thế kiểm tra quyền hoặc phân tách nhiệm vụ. Nếu điều kiện phụ thuộc dữ liệu khác, cơ chế transaction, khóa hoặc kiểm soát phiên bản phải bảo vệ cả phần dữ liệu liên quan theo quy tắc đã chọn.

### Ví dụ: hai yêu cầu hoàn tiền

Một khoản thanh toán có thể hoàn tối đa 1.000.000 đồng. Hai yêu cầu hoàn 700.000 đồng cùng đọc số tiền đã hoàn bằng 0. Nếu cả hai chỉ kiểm tra độc lập rồi ghi, tổng hoàn có thể thành 1.400.000 đồng.

Review cần bằng chứng rằng hệ thống giữ chỗ hoặc cập nhật hạn mức hoàn một cách nguyên tử trước khi tạo tác động bên ngoài. Khi yêu cầu thất bại, phần giữ chỗ chỉ được giải phóng sau khi xác định trạng thái thực tế; timeout không tự chứng minh rằng bên thanh toán chưa hoàn tiền.

## 10. Checklist F — Idempotency, replay và yêu cầu trùng

Idempotency của một lệnh nghiệp vụ nhằm bảo đảm việc gửi lại cùng một ý định thao tác không tạo thêm tác động ngoài ý muốn. Nó không cho phép bỏ qua xác thực, quyền hoặc điều kiện nghiệp vụ.

- [ ] **F1.** Đã chỉ rõ thao tác nào cần chống thực hiện trùng: tạo thanh toán, hoàn tiền, nhận ưu đãi, trừ kho hoặc phát hành quyền lợi.
- [ ] **F2.** Phạm vi khóa có gắn với tenant, chủ thể hoặc phạm vi quyền phù hợp và loại thao tác.
- [ ] **F3.** Cùng khóa nhưng payload khác bị phát hiện theo quy tắc chuẩn hóa đã định nghĩa.
- [ ] **F4.** Việc giành quyền xử lý khóa là nguyên tử và hoạt động giữa nhiều instance.
- [ ] **F5.** Có mô hình trạng thái cho yêu cầu đang xử lý, thành công, thất bại đã biết và kết quả chưa xác định.
- [ ] **F6.** Gửi trùng khi yêu cầu đầu đang chạy có phản hồi đã xác định.
- [ ] **F7.** Sau crash hoặc timeout, retry có thể tìm lại kết quả hoặc đối soát an toàn.
- [ ] **F8.** Thời gian lưu khóa phù hợp cửa sổ retry, callback trễ và rủi ro phát lại.
- [ ] **F9.** Sau khi khóa hết hạn, quy tắc nghiệp vụ vẫn ngăn tác động không hợp lệ.
- [ ] **F10.** Việc đọc lại kết quả cũ vẫn kiểm tra quyền truy cập của người gọi hiện tại.
- [ ] **F11.** Có kiểm soát hành vi đổi khóa để lặp lợi ích chỉ được nhận một lần.
- [ ] **F12.** Khóa phía nhà cung cấp và mã tham chiếu nghiệp vụ được dùng phù hợp khi gọi hệ thống ngoài.

Phân biệt hai lớp bảo vệ:

| Lớp | Tình huống cần xử lý |
| --- | --- |
| Khóa idempotency | Client retry cùng yêu cầu sau khi mất phản hồi |
| Quy tắc nghiệp vụ hoặc khóa duy nhất theo nghiệp vụ | Client cố tình dùng khóa mới để thanh toán lại cùng nghĩa vụ hoặc nhận lại quyền lợi |

Cùng một khóa với cùng payload có thể trả lại kết quả đã lưu theo hợp đồng API. Cùng khóa với payload khác cần được xử lý như xung đột theo hợp đồng, không âm thầm tái sử dụng kết quả không tương ứng.

Không dùng cơ chế “lưu khóa sau khi xong” như bảo vệ duy nhất. Hai yêu cầu có thể cùng chưa thấy khóa, cùng tạo tác động rồi mới ghi kết quả. Tương tự, lưu khóa trong cơ sở dữ liệu không tự tạo ra transaction nguyên tử với cổng thanh toán. Cần kết hợp điều phối, khóa của nhà cung cấp nếu có, trạng thái trung gian và đối soát.

## 11. Checklist G — Worker, webhook và tác động ngoài hệ thống

- [ ] **G1.** Webhook được xác thực nguồn theo cơ chế tích hợp; nội dung vẫn được đối chiếu với dữ liệu nghiệp vụ.
- [ ] **G2.** Event hoặc callback bị gửi trùng không tạo thêm tác động.
- [ ] **G3.** Event đến sai thứ tự hoặc đến trễ không làm lùi trạng thái trái quy tắc.
- [ ] **G4.** Sự kiện thanh toán khớp giao dịch, đơn hàng, tài khoản nhận, số tiền và tiền tệ theo hợp đồng tích hợp.
- [ ] **G5.** Worker kiểm tra điều kiện tại thời điểm thực hiện theo chính sách đã định nghĩa.
- [ ] **G6.** Thông điệp chỉ chứa dữ liệu cần thiết; định danh đối tượng không được coi là giấy phép thao tác.
- [ ] **G7.** Retry và xử lý hàng đợi lỗi không vô hạn tạo lại tác động.
- [ ] **G8.** Outbox, inbox hoặc cơ chế tương đương có ranh giới commit và xử lý trùng rõ ràng.
- [ ] **G9.** Có cách tìm và xử lý trạng thái chưa xác định khi hệ thống ngoài đã nhận yêu cầu nhưng ứng dụng chưa lưu kết quả.
- [ ] **G10.** Thao tác đối soát, bù trừ hoặc chạy lại thông điệp có quyền và audit phù hợp.

Outbox có thể giúp ghi thay đổi nghiệp vụ và ý định phát thông điệp trong cùng transaction cơ sở dữ liệu. Relay vẫn có thể phát lại thông điệp, nên phía nhận cần xử lý trùng phù hợp. Không dùng nhãn “exactly once” làm bằng chứng nếu chưa chỉ rõ ranh giới mà bảo đảm đó thực sự áp dụng.

Một trường hợp cần đưa vào review: cổng thanh toán đã thu tiền, ứng dụng timeout trước khi nhận phản hồi. Hành vi an toàn phải phân biệt “kết quả chưa biết” với “thanh toán thất bại”, rồi truy vấn hoặc đối soát trước khi tạo một lần thu mới.

## 12. Checklist H — Kiểm thử các tình huống lạm dụng logic

Mỗi quy tắc quan trọng cần có ca hợp lệ và ca cố tình vi phạm. Khi có xử lý đồng thời, bằng chứng phải thể hiện các yêu cầu thực sự chồng lấn tại điểm tranh chấp; gửi nhanh hai request tuần tự chưa chứng minh được điều đó.

| Kịch bản | Cách gây tác động | Điều cần quan sát |
| --- | --- | --- |
| Bỏ bước phê duyệt | Gọi thẳng lệnh thanh toán hoặc giao hàng từ DRAFT | Từ chối; trạng thái và tác động phụ không đổi |
| Sửa giá | Thay giá, tổng tiền hoặc phần trăm giảm trong request | Quyết định dựa trên quy tắc và nguồn dữ liệu có thẩm quyền |
| Đổi đối tượng | Thay ID đơn, dòng đơn hoặc bản ghi cha | Không truy cập hoặc sửa ngoài phạm vi quyền |
| Tự duyệt | Người tạo gọi lệnh duyệt khi quy tắc cấm | Bị từ chối và không lưu phê duyệt |
| Sửa sau duyệt | Đổi nội dung đã được phê duyệt | Chặn hoặc yêu cầu duyệt lại đúng đặc tả |
| Gửi trùng | Cùng khóa, cùng payload, chạy đồng thời | Một tác động nghiệp vụ; phản hồi phù hợp hợp đồng |
| Xung đột khóa | Cùng khóa, khác số tiền hoặc đối tượng | Xung đột được phát hiện |
| Đổi khóa | Nhiều khóa cho lợi ích chỉ được nhận một lần | Quy tắc nghiệp vụ vẫn ngăn nhận thêm |
| Race hạn mức | Hai yêu cầu cùng sử dụng phần hạn mức cuối | Tổng sử dụng hoặc giữ chỗ không vượt giới hạn |
| Hủy và thanh toán | Hai hành động cạnh tranh trên cùng đơn | Kết quả theo chính sách; không tạo trạng thái mâu thuẫn |
| Quyền bị thu hồi | Xếp việc rồi thu hồi trước khi worker chạy | Hành vi đúng chính sách quyền của tác vụ |
| Callback cũ | Gửi lại sự kiện thành công sau hủy hoặc hoàn | Không làm lùi trạng thái hoặc cấp lại quyền lợi |
| Mất phản hồi | Tạo tác động rồi ngắt kết nối | Retry tìm lại hoặc đối soát kết quả, không nhân đôi |
| Lỗi giữa transaction | Gây lỗi sau cập nhật một phần | Dữ liệu cùng transaction rollback đúng |
| Lỗi sau commit | Gây lỗi trước khi thông điệp được chuyển đi | Ý định xử lý còn bền vững và có thể tiếp tục |
| Triển khai xen phiên bản | Request đi qua phiên bản cũ và mới | Không xuất hiện đường bỏ qua quy tắc mới |

### Những điều phải kiểm tra ngoài phản hồi HTTP

- Số bản ghi nghiệp vụ và trạng thái cuối.
- Tổng số tiền đã thu, đã hoàn hoặc đang giữ chỗ.
- Số lượng tồn kho và hạn mức còn lại.
- Số thông điệp, quyền lợi hoặc lần giao hàng thực tế được tạo.
- Audit event có thể nối với actor và thao tác.
- Khả năng tiếp tục xử lý sau khi khởi động lại tiến trình.

Dùng dữ liệu và môi trường kiểm thử được phép, đặc biệt khi tích hợp có thể tạo khoản thu hoặc tác động thật. Hồ sơ release phải phân biệt bằng chứng chạy thật trong môi trường thử với kết quả từ mock; mock không chứng minh đầy đủ hành vi retry của nhà cung cấp.

## 13. Checklist I — Migration, feature flag và tương thích triển khai

- [ ] **I1.** Dữ liệu hiện có đáp ứng invariant mới hoặc có phương án chuyển đổi, cách ly hay từ chối thao tác rõ ràng.
- [ ] **I2.** Migration và backfill không tự ý hợp thức hóa trạng thái đã vi phạm.
- [ ] **I3.** Có cách xử lý đối tượng đang nằm giữa quy trình khi triển khai.
- [ ] **I4.** Phiên bản ứng dụng cùng tồn tại không ghi dữ liệu trái quy tắc của nhau.
- [ ] **I5.** Worker cũ, thông điệp cũ và lịch chạy cũ đã được xét đến.
- [ ] **I6.** Bật hoặc tắt feature flag không tạo đường đi tắt qua kiểm tra bắt buộc.
- [ ] **I7.** Cấu hình mặc định khi thiếu hoặc đọc lỗi được xác định cho từng hành động nhạy cảm.
- [ ] **I8.** Kế hoạch rollback ứng dụng xét khả năng đọc dữ liệu và trạng thái do phiên bản mới tạo.
- [ ] **I9.** Thao tác không thể đảo ngược có phương án dừng, đối soát hoặc bù trừ.
- [ ] **I10.** Các thay đổi quyền và cấu hình vận hành có người chịu trách nhiệm.

**Ví dụ:** phiên bản mới bắt buộc lưu `approvalVersion`, còn phiên bản cũ cho phép thanh toán khi chỉ thấy `status = APPROVED`. Trong giai đoạn cùng tồn tại, request qua phiên bản cũ có thể bỏ qua invariant mới.

Kế hoạch phát hành phải giải quyết khoảng chuyển tiếp đó, chẳng hạn triển khai kiểm tra tương thích trước, chuyển dữ liệu theo quy tắc đã xác nhận, rồi mới bật hành vi phụ thuộc invariant mới. Cách cụ thể phụ thuộc hệ thống; điều cần chứng minh là không có cửa sổ cho phép vượt quy tắc.

Rollback mã không tự hoàn lại khoản tiền đã thu, hàng đã giao hoặc quyền lợi đã cấp. Hồ sơ cần tách rõ thao tác kỹ thuật có thể khôi phục và tác động nghiệp vụ phải xử lý bằng đối soát hoặc bù trừ.

## 14. Checklist J — Quan sát, dừng tác động và ứng phó

- [ ] **J1.** Audit ghi đủ actor, tenant, đối tượng, hành động, thời điểm và kết quả; có tham chiếu để nối các bước.
- [ ] **J2.** Thay đổi trạng thái quan trọng có dấu vết phù hợp, gồm trước và sau khi cần.
- [ ] **J3.** Ghi nhận được việc từ chối do sai quyền, sai trạng thái, xung đột phiên bản hoặc xung đột idempotency.
- [ ] **J4.** Có chỉ số phát hiện invariant bị vi phạm và tác động trùng.
- [ ] **J5.** Cảnh báo có ngưỡng, cửa sổ đo và người tiếp nhận cụ thể.
- [ ] **J6.** Có cách tạm dừng hành động gây thiệt hại, kèm quy trình xử lý yêu cầu đang chạy.
- [ ] **J7.** Có cách xác định đối tượng bị ảnh hưởng và đối soát với hệ thống ngoài.
- [ ] **J8.** Quyền truy cập log, audit và công cụ sửa dữ liệu được kiểm soát.
- [ ] **J9.** Dữ liệu nhạy cảm trong log được giảm thiểu và che phù hợp.
- [ ] **J10.** Runbook nêu người xử lý, cách dừng, cách phục hồi và điều kiện mở lại.

Các tín hiệu hữu ích:

| Tín hiệu | Ý nghĩa cần điều tra |
| --- | --- |
| Nhiều lần chuyển trạng thái bị từ chối trên cùng đối tượng | Có thể là thử bỏ bước, client lỗi hoặc callback sai thứ tự |
| Một khóa idempotency đi cùng nhiều payload | Có thể là lạm dụng hoặc lỗi client |
| Tổng hoàn và giữ chỗ vượt số tiền cho phép | Invariant có khả năng đã bị phá vỡ |
| Nhiều khoản thu thành công cho cùng nghĩa vụ | Có thể có tác động trùng cần dừng và đối soát |
| Tác vụ ở trạng thái chưa xác định quá lâu | Cần đối soát hoặc can thiệp theo runbook |
| Tăng truy cập chéo tenant bị từ chối | Có thể là dò quyền hoặc lỗi tích hợp |

Một tín hiệu đơn lẻ chưa xác định được nguyên nhân tấn công. Theo dõi giúp phát hiện và xử lý; nó không thay thế việc ngăn vi phạm trước khi commit hoặc trước khi tạo tác động ngoài hệ thống.

## 15. Quy tắc ra quyết định phát hành

Quyết định dựa trên mức ảnh hưởng và bằng chứng đã có, không dựa vào số lượng ô đã đánh dấu.

### Chặn phát hành

Chặn khi còn một trong các vấn đề liên quan đến phạm vi release:

- Chưa xác định được invariant cho hành động có tác động quan trọng.
- Có đường bỏ qua phê duyệt, sửa giá trái quyền hoặc thao tác chéo đối tượng/tenant.
- Có thể làm vượt hạn mức, tạo khoản thu trùng hoặc cấp quyền lợi trùng.
- Race condition đã biết có thể phá vỡ quy tắc nghiệp vụ.
- Không xử lý được retry sau trạng thái kết quả chưa xác định.
- Migration, rollback hoặc giai đoạn cùng tồn tại phiên bản tạo đường vượt kiểm soát.
- Thiếu bằng chứng cho một kiểm soát trọng yếu mà release phụ thuộc vào.

Không dùng ghi chú “đã biết rủi ro” để chuyển một lỗi trọng yếu thành PASS.

### Phát hành với giới hạn đã được phê duyệt

Chỉ cân nhắc nếu phần có rủi ro được cô lập bằng biện pháp thực sự ngăn tác động tương ứng, và phần được bật vẫn đáp ứng các quy tắc bắt buộc.

Ví dụ: vô hiệu hóa endpoint hoàn tiền mới trong khi phát hành phần đọc lịch sử, đồng thời xác minh rằng mọi đường gọi endpoint đó đều bị chặn phía máy chủ. Chỉ ẩn nút trên giao diện không đủ cô lập chức năng.

Ghi rõ phạm vi giới hạn, người có thẩm quyền chấp thuận, thời hạn, cách theo dõi và điều kiện mở lại. Nếu tổ chức không có cơ chế chấp thuận ngoại lệ phù hợp, giữ quyết định chặn phần thay đổi đó.

### Được phát hành

Có thể thông qua khi:

- Các mục áp dụng có bằng chứng phù hợp.
- Không còn phát hiện chặn phát hành.
- Các mục N/A có lý do được người chịu trách nhiệm xác nhận.
- Quy tắc triển khai, quan sát, dừng và phục hồi đủ cụ thể để vận hành.
- Chủ sở hữu nghiệp vụ, kỹ thuật và các bên liên quan đã chấp thuận theo quy trình của tổ chức.

## 16. Mẫu biên bản release review

~~~text
Mã release / thay đổi:
Phạm vi chức năng:
Luồng nghiệp vụ và dữ liệu bị ảnh hưởng:
Người chịu trách nhiệm nghiệp vụ:
Người chịu trách nhiệm kỹ thuật:
Người phụ trách vận hành:

Invariant trọng yếu:
- Mô tả điều kiện:
- Ranh giới cần bảo đảm:
- Cơ chế bảo vệ:
- Bằng chứng:

Quyền theo đối tượng và tenant:
Chuyển trạng thái mới hoặc bị thay đổi:
Transaction và kiểm soát cạnh tranh:
Idempotency, callback trùng và kết quả chưa xác định:
Tác động ngoài hệ thống và cách đối soát:
Migration, cùng tồn tại phiên bản và rollback:

Kết quả theo nhóm A–J:
- PASS:
- FAIL:
- N/A và lý do:

Phát hiện chặn phát hành:
- Vấn đề:
- Tác động nghiệp vụ:
- Chủ sở hữu:
- Điều kiện đóng:

Giới hạn hoặc ngoại lệ được chấp thuận, nếu có:
- Phạm vi:
- Biện pháp ngăn tác động:
- Người chấp thuận:
- Thời hạn:
- Điều kiện mở lại:

Kế hoạch triển khai và chỉ số theo dõi:
Điều kiện dừng:
Người tiếp nhận cảnh báo:
Cách xử lý yêu cầu đang chạy:
Cách đối soát hoặc bù trừ:

Quyết định:
Người quyết định:
Thời điểm:
Liên kết bằng chứng:
~~~

## 17. Ví dụ kết luận review một thay đổi hoàn tiền

**Thay đổi:** thêm API hoàn tiền một phần và xử lý qua worker.

**Phát hiện:** khóa idempotency đã hoạt động cho cùng một request, nhưng hai request dùng khóa khác nhau có thể cùng vượt qua bước kiểm tra số tiền còn được hoàn. Worker còn đánh dấu thất bại ngay khi cổng thanh toán timeout.

**Quyết định:** chặn phát hành chức năng hoàn tiền mới.

**Điều kiện để xem xét lại:**

1. Có cơ chế giữ chỗ hạn mức hoàn một cách nguyên tử, gồm các yêu cầu đang xử lý.
2. Hai yêu cầu cạnh tranh không làm tổng hoàn và giữ chỗ vượt số tiền được phép.
3. Timeout được lưu thành kết quả chưa xác định và có luồng đối soát.
4. Retry sau crash không tạo tác động hoàn lần hai.
5. Có bằng chứng thử quyền trên đúng đối tượng, callback trùng và callback đến trễ.
6. Có chỉ số theo dõi tồn đọng, công cụ đối soát và người chịu trách nhiệm xử lý.

Ví dụ này cho thấy vì sao đánh dấu “có transaction” và “có idempotency” chưa đủ. Review phải nối từng cơ chế với quy tắc mà nó bảo vệ và tình huống có thể làm quy tắc đó bị phá vỡ.

## 18. Các lỗi thường gặp khi dùng checklist

| Lỗi review | Cách thực hiện phù hợp |
| --- | --- |
| Chỉ xem giao diện | Gửi trực tiếp các yêu cầu ngoài thứ tự và ngoài quyền |
| Chỉ kiểm tra vai trò | Kiểm tra thêm đối tượng, tenant, hành động và ngữ cảnh |
| Chỉ đọc mã kiểm tra | Đối chiếu cả kết quả dữ liệu và tác động phụ |
| Chỉ thử từng request riêng | Thử yêu cầu cạnh tranh tại điểm tranh chấp |
| Tin idempotency giải quyết mọi lần lặp | Kiểm tra cả khóa request lẫn quy tắc duy nhất theo nghiệp vụ |
| Coi timeout là thất bại chắc chắn | Ghi nhận kết quả chưa xác định và đối soát |
| Chỉ rollback ứng dụng | Xét dữ liệu mới, thông điệp đang chạy và tác động bên ngoài |
| Đánh N/A không có lý do | Gắn lý do với phạm vi và chỉ rõ người xác nhận |
| Dùng cảnh báo để chấp nhận lỗi invariant | Sửa hoặc cô lập đường gây vi phạm trước khi bật |
| Dùng bộ checklist cố định cho mọi release | Chọn mục theo phạm vi, bổ sung kịch bản từ thay đổi cụ thể |

Một buổi release review hữu ích phải cho phép người khác trả lời ba câu hỏi bằng bằng chứng: quy tắc nào cần được giữ, ai hoặc tình huống nào có thể phá vỡ nó, và cơ chế nào đã được chứng minh là giữ được quy tắc đó trong phạm vi phát hành.
