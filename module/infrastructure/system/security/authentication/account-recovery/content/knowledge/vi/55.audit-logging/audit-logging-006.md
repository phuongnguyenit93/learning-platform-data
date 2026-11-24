# Audit access control

## 1. Nhật ký khôi phục cũng là tài nguyên nhạy cảm

Audit của luồng khôi phục tài khoản có thể cho biết ai yêu cầu đặt lại mật khẩu, thời điểm thay MFA, phương thức nào bị thu hồi, nhân viên nào phê duyệt và phiên nào bị xử lý. Những dữ liệu này giúp điều tra, nhưng cũng có thể hỗ trợ kẻ tấn công tìm tài khoản dễ chiếm hoặc theo dõi người dùng.

Nếu người thực hiện một thay đổi trái phép có thể xóa dấu vết, giá trị điều tra giảm mạnh. Nếu nhân viên hỗ trợ được đọc toàn bộ hồ sơ khôi phục chỉ vì có quyền xử lý một ticket, hệ thống lại tạo ra một nguồn rò rỉ khác.

Audit access control là thiết kế quyền đối với cả dữ liệu audit và các chức năng vận hành nó: tiếp nhận, ghi, đọc, tìm kiếm, xuất, thay chính sách và xóa theo vòng đời.

[OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#protection) yêu cầu bảo vệ log khỏi truy cập, thay đổi và xóa trái phép; hạn chế quyền đọc và ghi nhận hoạt động truy cập. Trong module khôi phục, điều đó cần được cụ thể hóa đến từng loại hành động và phạm vi dữ liệu.

Ba câu hỏi nền tảng là:

- Ai được phép thực hiện hành động nào trên dữ liệu nào?
- Thành phần nào thực sự kiểm tra và thực thi quyền?
- Ai có thể phát hiện khi quyền bị lạm dụng hoặc cấu hình bị thay đổi?

Mã hóa dữ liệu hoặc đặt log trong mạng nội bộ có ích, nhưng không tự trả lời đầy đủ những câu hỏi này.

## 2. Tách quyền theo hành động

Một quyền chung như `AUDIT_ADMIN` dễ gom quá nhiều khả năng vào cùng người dùng hoặc dịch vụ.

| Hành động | Ví dụ quyền minh họa | Giới hạn cần xác định |
| --- | --- | --- |
| Gửi sự kiện | `audit.emit` | Nguồn phát, loại sự kiện, tenant và cấu trúc được phép |
| Ghi vào kho đích | `audit.append` | Chỉ thành phần thu nhận có trách nhiệm ghi |
| Đọc bản tóm tắt | `audit.read.summary` | Trường đã giảm nhạy cảm, tài khoản và khoảng thời gian phù hợp |
| Đọc chi tiết | `audit.read.detail` | Hồ sơ điều tra, loại dữ liệu và mục đích được cho phép |
| Tìm kiếm | `audit.search` | Phạm vi hàng, trường, bộ lọc và giới hạn truy vấn |
| Xuất dữ liệu | `audit.export` | Tập dữ liệu, nơi nhận, thời hạn và phê duyệt nếu cần |
| Quản lý chính sách | `audit.policy.manage` | Quy trình thay đổi và phân tách trách nhiệm |
| Xóa theo vòng đời | `audit.retention.execute` | Chính sách lưu trữ có thẩm quyền, không xóa tùy ý theo event ID |

Các tên quyền chỉ là ví dụ. Tách quyền trong tài liệu chưa đủ nếu backend vẫn dùng một credential có toàn quyền và bỏ qua kiểm tra.

Quyền đọc không tự bao gồm quyền xuất hàng loạt. Quyền phát sự kiện cũng không tự bao gồm quyền xem các sự kiện đã lưu. Quyền quản trị ứng dụng recovery không mặc nhiên phải bao gồm sửa hoặc xóa audit.

## 3. Xây dựng vai trò từ nhu cầu công việc

Một ma trận minh họa:

| Chủ thể | Khả năng hợp lý trong ví dụ | Khả năng không được cấp mặc định |
| --- | --- | --- |
| Dịch vụ recovery | Phát sự kiện thuộc phạm vi mình quản lý | Tìm kiếm toàn kho hoặc xóa sự kiện |
| Bộ thu audit | Kiểm tra nguồn và ghi sự kiện hợp lệ | Cấp quyền khôi phục tài khoản |
| Nhân viên hỗ trợ | Xem tóm tắt các hồ sơ được giao | Đọc toàn bộ thông tin điều tra của mọi tenant |
| Điều tra viên bảo mật | Tra cứu chi tiết trong phạm vi được phê duyệt | Sửa kết quả recovery hoặc tự xóa dấu vết |
| Hệ thống phát hiện tự động | Đọc tập trường cần cho quy tắc phát hiện | Tải toàn bộ tài liệu xác minh danh tính |
| Người vận hành nền tảng | Quản lý hạ tầng theo nhiệm vụ | Tự động có quyền đọc mọi nội dung audit |
| Dịch vụ vòng đời | Xử lý dữ liệu hết thời hạn theo chính sách | Xóa riêng một sự kiện đang gây bất lợi cho người quản trị |

Không phải sản phẩm nào cũng có từng vai trò riêng. Với đội nhỏ, một người có thể đảm nhiệm nhiều công việc, nhưng các hành động nhạy cảm vẫn cần được phân biệt trong cơ chế quyền, thời điểm sử dụng và dấu vết kiểm soát.

[OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html#recommendations) khuyến nghị quyền tối thiểu, mặc định từ chối và kiểm tra quyền trên từng request. Áp dụng ở đây nghĩa là có vai trò hỗ trợ chưa đủ; người dùng còn phải được phép truy cập đúng sự kiện hoặc đúng hồ sơ.

Các ma trận và schema bên dưới là đề xuất thiết kế cho bài học, không phải định dạng bắt buộc của OWASP.

## 4. Quyết định quyền cần có phạm vi dữ liệu

Vai trò trả lời một phần câu hỏi. Phạm vi còn phụ thuộc các thuộc tính và quan hệ khác:

- Tenant của principal và tenant của dữ liệu.
- Tài khoản hoặc recovery request nằm trong hồ sơ được giao.
- Loại sự kiện, mức nhạy cảm và tập trường cần đọc.
- Khoảng thời gian cần điều tra.
- Mục đích truy cập và tham chiếu công việc.
- Trạng thái phê duyệt, thời hạn của quyền tạm thời.
- Mức xác thực và những điều kiện môi trường mà chính sách yêu cầu.

Một ticket ID do người dùng nhập không tự chứng minh họ được giao ticket. Hệ thống phải đối chiếu quan hệ đó với nguồn có thẩm quyền.

Tương tự, tham số `tenantId` là phạm vi được yêu cầu, không phải bằng chứng người gọi có quyền ở tenant đó. Không để người dùng đổi query parameter rồi xem lịch sử khôi phục của đơn vị khác.

Một mô hình quyết định có thể là:

```text
cho phép đọc chi tiết khi:
  principal đã được xác thực theo yêu cầu
  AND có quyền audit.read.detail
  AND tập tenant được phép chứa tenant của sự kiện
  AND hồ sơ được giao bao phủ tài khoản hoặc request
  AND thời điểm sự kiện nằm trong phạm vi được cấp
  AND quyền tạm thời, nếu được dùng, chưa hết hạn
```

Đây là biểu thức minh họa, không phải mọi điều kiện bắt buộc của mọi hệ thống. Quyền điều tra xuyên tenant có thể tồn tại, nhưng phải là phạm vi được cấp rõ ràng và được kiểm soát.

Không chỉ kiểm tra trang danh sách. Endpoint đọc một event theo ID, tải file xuất, xem alert, truy vấn dashboard và đọc bản lưu trữ cũng phải áp dụng phạm vi tương ứng.

## 5. Thực thi quyền trước khi dữ liệu vượt ranh giới

Một thiết kế nguy hiểm là tìm tất cả sự kiện, trả chúng cho trình duyệt rồi mới ẩn các hàng không thuộc tenant. Dữ liệu đã rời máy chủ trước khi kiểm soát có tác dụng.

Cần giới hạn tập dữ liệu trong đường đọc có thẩm quyền và giới hạn trường trước khi gửi ra ngoài ranh giới được phép.

Mã giả:

```text
principal = lấy_danh_tính_đã_được_kiểm_tra()
requestedScope = đọc_và_kiểm_tra_phạm_vi_yêu_cầu()

decision = policy.authorize(
  principal,
  action = READ_AUDIT_DETAIL,
  requestedScope
)

nếu decision bị từ chối:
  ghi sự kiện truy cập bị từ chối với dữ liệu tối thiểu
  trả phản hồi phù hợp

events = repository.query(
  phạm_vi_hàng = decision.allowedScope,
  tập_trường = decision.allowedFields,
  bộ_lọc_hợp_lệ,
  giới_hạn_kết_quả
)

ghi dấu vết truy cập được chấp nhận
trả events đã được chiếu theo tập trường được phép
```

`allowedScope` phải do policy engine hoặc logic có thẩm quyền tạo, không phải một đối tượng do client gửi nguyên vào repository. Mọi đường tìm kiếm phải giữ điều kiện phạm vi khi ghép thêm bộ lọc.

Cursor phân trang cũng cần được ràng buộc với truy vấn và người được phép dùng, hoặc được kiểm tra lại khi sử dụng. Không để một cursor trở thành đường vượt phạm vi dữ liệu.

Chỉ số tổng, gợi ý tìm kiếm và thông báo lỗi cũng có thể tiết lộ tài khoản hoặc sự kiện tồn tại. Giới hạn chúng theo quyền; không trả tổng số sự kiện toàn hệ thống rồi chỉ che danh sách chi tiết.

ID khó đoán giúp giảm dò tìm, nhưng không thay thế kiểm tra quyền đối tượng.

## 6. Tập trường được đọc phải phù hợp với mục đích

Hai người có quyền xem cùng sự kiện chưa chắc cần cùng nội dung.

Ví dụ, nhân viên hỗ trợ có thể cần biết “yêu cầu bị từ chối vì chưa đủ điều kiện” và bước người dùng cần làm tiếp. Họ không nhất thiết cần xem toàn bộ tín hiệu rủi ro, quy tắc chống gian lận hoặc dữ liệu liên quan đến người khác.

Một cách chia lớp:

| Lớp hiển thị | Dữ liệu có thể phù hợp | Dữ liệu cần hạn chế thêm |
| --- | --- | --- |
| Lịch sử cho chủ tài khoản | Loại thay đổi, thời điểm, chỉ dẫn báo cáo | Danh tính nhân viên nội bộ, tín hiệu phát hiện chi tiết |
| Tóm tắt hỗ trợ | Trạng thái, mã tham chiếu, lý do đã được diễn giải an toàn | Dữ liệu điều tra ngoài hồ sơ và quy tắc chống lạm dụng nhạy cảm |
| Chi tiết điều tra | Actor, subject, quan hệ phê duyệt, ngữ cảnh đã được cho phép | Bằng chứng danh tính nguyên bản nếu không cần cho nhiệm vụ |
| Phát hiện tự động | Các thuộc tính phục vụ quy tắc | Toàn bộ profile hoặc nội dung hồ sơ không cần thiết |

Đây là lựa chọn thiết kế theo mục đích, không phải lời khẳng định mọi trường ở cột cuối luôn bị cấm.

Không nên ghi token, OTP, mật khẩu, seed MFA hoặc private key vào audit rồi dựa vào phân quyền để bảo vệ chúng. Giảm dữ liệu ngay từ lúc tạo sự kiện giúp giảm hậu quả khi quyền đọc bị lạm dụng.

Nếu phải đối chiếu bằng chứng danh tính trong kho riêng, quyền đọc audit không nên tự động cấp quyền tải bằng chứng. Tham chiếu hồ sơ là dữ liệu liên kết, không phải capability cấp quyền xem mọi tài liệu.

Che dữ liệu ở giao diện chỉ có giá trị khi API và kho dữ liệu cũng thực thi tập trường tương ứng. Không gửi trường đầy đủ rồi dùng CSS hoặc JavaScript để ẩn.

## 7. Quyền ghi và quản trị không được làm mất dấu vết

Dịch vụ recovery thường cần phát sự kiện nhưng không cần có quyền sửa hoặc xóa lịch sử đã lưu. Một credential phát sự kiện bị lộ sẽ gây hậu quả lớn hơn nếu đồng thời cho phép đọc toàn kho và dọn sạch dấu vết.

Tại lớp tiếp nhận, cần xác thực nguồn phát, kiểm tra loại sự kiện và đối chiếu phạm vi tenant phù hợp với nguồn. Không chỉ tin `tenantRef` hoặc `producer` trong payload.

Tuy nhiên, nguồn phát đã được xác thực vẫn có thể phát dữ liệu sai nếu ứng dụng bị chiếm hoặc có lỗi. Quyền append không tự chứng minh nội dung đúng. Cần giữ thông tin nguồn tiếp nhận và có khả năng đối chiếu với dữ liệu nghiệp vụ hoặc những nguồn độc lập.

Những ranh giới cần xem xét gồm:

- Quyền phát sự kiện qua API hoặc message broker.
- Quyền ghi tại cơ sở dữ liệu hoặc kho đối tượng.
- Quyền thay cấu hình thu thập và bộ lọc.
- Quyền sửa policy của SIEM hoặc hệ thống tìm kiếm.
- Quyền thay khóa mã hóa, chính sách lưu giữ và bản sao lưu.
- Quyền vô hiệu hóa cảnh báo về việc logging bị dừng.

Nếu ứng dụng chỉ bị hạn chế ở API audit nhưng vẫn giữ credential quản trị cơ sở dữ liệu, ranh giới đó chưa đủ.

Một đính chính cần có nguồn, lý do và liên kết với sự kiện gốc theo chính sách. Không để thao tác “sửa lỗi log” trở thành quyền âm thầm đổi actor, outcome hoặc thời điểm của một thay đổi khôi phục.

## 8. Kiểm soát tìm kiếm và xuất dữ liệu

Tìm kiếm diện rộng và xuất file làm tăng lượng dữ liệu có thể bị lấy ra trong một lần. Chúng cần quyết định quyền riêng, giới hạn khối lượng và dấu vết truy cập phù hợp.

Một yêu cầu xuất nên xác định rõ:

```yaml
exportPurpose: incident-investigation
caseRef: case_example_72
tenantScope:
  - tenant_example_3
accountScope:
  - acct_example_19
eventTimeFrom: "2026-11-20T00:00:00Z"
eventTimeTo: "2026-11-25T00:00:00Z"
fieldProfile: recovery-investigation-restricted
approvalRef: approval_example_12
```

Các giá trị chỉ là ví dụ. Backend phải kiểm tra mục đích, hồ sơ, phạm vi và phê duyệt; người dùng tự điền đúng tên trường không tạo ra quyền.

Cần kiểm tra quyền khi tạo yêu cầu xuất và tại các thời điểm sử dụng tiếp theo theo chính sách. Một job chạy lâu không nên tiếp tục lấy dữ liệu mới ngoài quyền đã được cấp vì chỉ kiểm tra một lần lúc nhấn nút.

Tập kết quả hoặc snapshot được xuất phải có phạm vi và quyền đọc rõ ràng. Khi quyền người dùng bị thu hồi, cần biết cơ chế nào chặn tải lại file và cơ chế nào xử lý bản sao đã được tải xuống.

File xuất là một bản sao của dữ liệu nhạy cảm. Hạn chế nơi lưu, người nhận và thời gian tồn tại; không để file trong thư mục công khai hoặc gửi kèm tùy ý tới địa chỉ do người gọi khai báo.

Một URL có chữ ký hoặc một mã tải xuống có thể mang quyền truy cập riêng. Nếu dùng, cần giới hạn tài nguyên, thời hạn và cách phân phối theo chính sách. Không tuyên bố việc thu hồi quyền trong ứng dụng tự động làm mọi liên kết đã cấp hết hiệu lực nếu cơ chế lưu trữ không hỗ trợ điều đó.

Dashboard, cảnh báo, cache, bản sao lưu và dữ liệu đã chuyển sang SIEM cũng cần được bảo vệ. Quyền của kho gốc không tự đi theo bản sao sang hệ thống khác.

## 9. Ghi dấu vết truy cập audit mà không tạo vòng lặp vô hạn

Cần biết ai đã xem, tìm kiếm hoặc xuất lịch sử khôi phục. Một bản ghi truy cập có thể chứa:

- Principal thực hiện và nguồn xác thực.
- Hành động đọc, tìm kiếm, xuất hoặc quản trị.
- Hồ sơ công việc và phạm vi dữ liệu.
- Quyết định cho phép hoặc từ chối, kèm phiên bản policy.
- Thời điểm, mã request và lượng kết quả phù hợp để theo dõi.
- Tham chiếu phê duyệt hoặc quyền tạm thời nếu có.

Không sao chép toàn bộ kết quả truy vấn vào bản ghi truy cập. Nếu query chứa dữ liệu nhạy cảm, chỉ giữ dạng đã chuẩn hóa hoặc tham chiếu được bảo vệ theo nhu cầu.

Việc đọc nhật ký truy cập cũng cần được kiểm soát và ghi nhận. Tuy nhiên, triển khai không nên đồng bộ tự gọi lại chính endpoint đang được giám sát cho từng thao tác ghi, dẫn đến vòng lặp không kết thúc.

Có thể dùng một luồng meta-audit được phân tách hợp lý, với cơ chế ghi không gây đệ quy và quyền quản trị rõ ràng. Tên gọi “meta-audit” không có nghĩa dữ liệu đó được miễn bảo vệ.

Theo dõi các dấu hiệu như truy vấn vượt phạm vi hồ sơ, xuất dữ liệu bất thường, nhiều lần bị từ chối hoặc thay đổi quyền ngay trước khi tra cứu. Các dấu hiệu là cơ sở điều tra, không tự chứng minh người dùng đã lạm dụng.

## 10. Quyền khẩn cấp và vòng đời quyền

Khi điều tra chiếm đoạt tài khoản, có thể cần truy cập gấp. Quyền khẩn cấp nên có phạm vi, thời hạn và trách nhiệm rõ ràng thay vì một tài khoản toàn quyền luôn bật.

Một quy trình minh họa:

1. Người xử lý xác thực theo yêu cầu của quyền nhạy cảm.
2. Ghi lý do khẩn cấp và hồ sơ sự cố.
3. Cấp quyền tạm thời đủ cho phạm vi cần thiết.
4. Phê duyệt độc lập nếu chính sách yêu cầu, hoặc thực hiện cơ chế khẩn cấp đã được định nghĩa.
5. Ghi và giám sát mọi hành động sử dụng quyền.
6. Thu hồi khi hết hạn hoặc khi nhiệm vụ kết thúc, rồi đối chiếu hoạt động.

Không cho người dùng tự nhập `emergency=true` để bỏ qua kiểm tra. Quyền khẩn cấp phải đến từ cơ chế cấp quyền có thẩm quyền.

Quyền đọc khẩn cấp không mặc nhiên có quyền sửa hoặc xóa audit. Người quản lý recovery không nên có thể tự cấp quyền, thực hiện thay đổi, xóa dấu vết và tắt giám sát trong cùng một chuỗi không có kiểm soát độc lập.

Đối với quyền thường xuyên, cần xử lý thay đổi vai trò, chuyển nhóm và nghỉ việc. Không chỉ gỡ một nút trên giao diện; phải xử lý session, credential dịch vụ, quyền tại SIEM và các đường truy cập còn tồn tại theo cơ chế thực tế.

Quyền có thời hạn cần được thực thi tại nơi truy cập dữ liệu. Một nhãn “hết hạn” trên ticket không đủ nếu credential lưu trữ vẫn còn hiệu lực.

## 11. Lưu giữ, xóa và tính sẵn sàng

Kiểm soát audit không có nghĩa giữ mọi thứ vĩnh viễn hoặc cấm mọi thao tác xóa. Cần một quy trình vòng đời riêng, với chính sách lưu giữ phù hợp và quyền thực thi giới hạn.

Dịch vụ vòng đời có thể xử lý dữ liệu đã đủ điều kiện theo chính sách. Quyền đó khác với việc một người tùy chọn event ID rồi xóa những sự kiện liên quan đến mình.

Nếu dữ liệu đang thuộc diện cần giữ lại theo quyết định có thẩm quyền, thao tác vòng đời phải tôn trọng trạng thái đó. Thời hạn cụ thể cần được xác định theo yêu cầu của tổ chức, không suy ra từ một con số mặc định trong ví dụ kỹ thuật.

Mã hóa và cơ chế phát hiện sửa đổi hỗ trợ bảo vệ, nhưng phải xem cả quyền truy cập khóa, bản sao và cấu hình lưu trữ. Kho chỉ đọc không tự ngăn người có quyền lấy dữ liệu ra ngoài.

Giới hạn truy vấn, phân trang và ngân sách xuất còn giúp bảo vệ tính sẵn sàng. Một truy vấn được phép về mặt dữ liệu vẫn có thể cần bị giới hạn nếu làm cạn tài nguyên phục vụ điều tra.

Khi dịch vụ phân quyền không hoạt động, không tự trả toàn bộ dữ liệu để “không cản hỗ trợ”. Khi hệ thống thu log gặp lỗi, cần cơ chế xử lý đã được thiết kế cho từng tác vụ; không tự xóa audit, mở rộng quyền hoặc bỏ dấu vết để khắc phục tạm thời.

## 12. Tình huống áp dụng

### Nhân viên hỗ trợ bị đổi tenant trong URL

Nhân viên được giao hồ sơ ở tenant A sửa đường dẫn sang tenant B. Máy chủ đối chiếu phạm vi từ principal và quan hệ hồ sơ, từ chối dữ liệu ngoài quyền. Endpoint đọc theo event ID và tải file xuất áp dụng cùng ranh giới.

### Dịch vụ recovery bị lộ credential phát sự kiện

Credential phát chỉ cho phép phạm vi sự kiện cần thiết, không có quyền truy vấn hoặc xóa kho. Hệ thống vẫn cần xem khả năng phát dữ liệu giả, đánh dấu nguồn và đối chiếu sự kiện; quyền ghi giới hạn không bảo đảm nguồn bị chiếm luôn nói đúng.

### Điều tra viên cần xuất dữ liệu gấp

Quyền tạm thời cho đúng hồ sơ và khoảng thời gian được cấp theo quy trình khẩn cấp. File xuất có kiểm soát riêng và các lần truy cập được ghi nhận. Hết thời hạn, quyền tải tiếp phải được xử lý theo cơ chế thực tế của nơi lưu.

### Quản trị viên muốn xóa một sự kiện bất lợi

Quyền quản trị recovery không cho phép xóa riêng audit. Nếu dữ liệu sai, sử dụng quy trình đính chính có dấu vết. Nếu dữ liệu hết thời hạn, dùng quy trình vòng đời có thẩm quyền, không dùng xóa tùy ý để thay đổi lịch sử.

Audit access control giữ giá trị điều tra của luồng khôi phục bằng cách ràng buộc từng hành động với người được phép, phạm vi dữ liệu và mục đích phù hợp. Các ranh giới đó cần tiếp tục có hiệu lực khi dữ liệu được tìm kiếm, sao chép, xuất hoặc quản trị ở hệ thống khác.