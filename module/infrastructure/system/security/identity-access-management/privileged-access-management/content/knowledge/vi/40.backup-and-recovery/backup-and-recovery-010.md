# Audit backup access

## 1. Vì sao quyền truy cập backup cần được kiểm toán riêng?

Một bản backup có thể chứa gần như toàn bộ dữ liệu mà hệ thống sản xuất đang bảo vệ bằng nhiều lớp kiểm soát. Khi dữ liệu được khôi phục, tải xuống hoặc gắn vào một máy khác, các quyền của ứng dụng gốc không nhất thiết còn áp dụng. Người không thể đọc dữ liệu qua ứng dụng vẫn có thể đọc dữ liệu từ một bản khôi phục nếu được cấp quyền quá rộng ở tầng backup.

Trong quản lý truy cập đặc quyền, **audit backup access** là việc thu thập, liên kết và đánh giá bằng chứng về những chủ thể có thể hoặc đã tiếp cận bản sao lưu, chức năng khôi phục và những thành phần bảo vệ bản sao đó. Mục tiêu không chỉ là tìm người đăng nhập vào phần mềm backup, mà còn xác định người có khả năng biến một bản sao thành dữ liệu đọc được, làm mất khả năng khôi phục hoặc che giấu thao tác.

Một cuộc kiểm toán cần trả lời được các câu hỏi:

- Ai được phép truy cập, bằng danh tính nào và qua đường truy cập nào?
- Quyền đó có giới hạn đúng tài nguyên, hành động, môi trường và thời gian không?
- Ai đã xem, đọc, khôi phục, xuất, thay đổi hoặc xóa; thao tác đã thành công đến mức nào?
- Hoạt động có gắn với yêu cầu được duyệt và có tuân thủ phạm vi được duyệt không?
- Bằng chứng có đủ tin cậy để kết luận, kể cả khi nền tảng PAM hoặc backup bị sự cố không?

Ví dụ, một kỹ sư được phép khôi phục cơ sở dữ liệu vào môi trường kiểm thử trong hai giờ không đương nhiên được phép tải bản backup về máy cá nhân, cấp quyền đọc cho một dịch vụ khác hoặc thay đổi chính sách giữ bản sao.

Trong bài này, PAM bao gồm các kiểm soát như định danh quản trị riêng, least privilege, cấp quyền đúng lúc (JIT), giới hạn thao tác theo nhiệm vụ (JEA), vault, giám sát phiên và thu hồi quyền. Audit kiểm tra hiệu quả thực tế của những kiểm soát đó bằng bằng chứng. Một phiên PAM có bản ghi hình là một nguồn bằng chứng, chưa phải toàn bộ bằng chứng về backup.

## 2. Xác định đầy đủ bề mặt truy cập

### 2.1. Phân biệt ba nhóm khả năng đặc quyền

| Nhóm khả năng | Ví dụ | Rủi ro cần kiểm toán |
|---|---|---|
| Đọc hoặc đưa dữ liệu ra ngoài | Đọc đối tượng backup, tải archive, mount snapshot, restore vào máy khác | Lộ dữ liệu, tạo bản sao ngoài phạm vi kiểm soát |
| Làm thay đổi khả năng khôi phục | Xóa bản sao, giảm retention, loại bỏ bảo vệ, vô hiệu hóa job, thay catalog | Mất dữ liệu khôi phục, kéo dài gián đoạn |
| Thay đổi cơ chế bảo vệ và bằng chứng | Cấp quyền đọc, đổi cấu hình vault, dùng khóa giải mã, dừng audit hoặc sửa nơi nhận log | Mở đường truy cập, che giấu hoạt động, làm sai kết luận |

Một người chỉ nhìn thấy catalog có thể chưa đọc được nội dung, nhưng tên hệ thống, lịch backup và cấu trúc tài nguyên vẫn có thể nhạy cảm. Ngược lại, người đọc được đối tượng lưu trữ và dùng được khóa phù hợp có thể không cần đăng nhập vào console backup.

Không nên gộp tất cả vào nhãn “backup administrator”. Cần tách từng khả năng và kiểm tra quyền hiệu lực.

### 2.2. Kiểm kê các đường truy cập thực tế

Bắt đầu từ đường đi của bản sao, không chỉ từ giao diện quản trị:

~~~text
Người / workload
    ├── PAM → console hoặc API backup → restore / export
    ├── API lưu trữ → đọc trực tiếp object hoặc snapshot
    ├── máy chủ / hypervisor → mount volume hoặc đọc file cục bộ
    ├── dịch vụ khóa → giải mã vật liệu cần cho khôi phục
    └── kho offline → nhận, vận chuyển, nạp và đọc media

Mỗi nhánh cần có chủ thể, quyết định cấp quyền và bằng chứng riêng.
~~~

Các đường dễ bị bỏ sót gồm:

- Console của storage, hypervisor và hệ thống snapshot.
- Tài khoản cục bộ hoặc tài khoản khẩn cấp khi hệ thống định danh trung tâm không hoạt động.
- API token của scheduler, agent, công cụ di chuyển dữ liệu và pipeline khôi phục.
- Đường dẫn chia sẻ mạng, thư mục staging và volume tạm sau restore.
- Bản sao chép liên vùng, tài khoản lưu trữ thứ hai và archive lâu dài.
- Khóa, credential và recovery material được giữ để phục hồi khi vault chính bị mất.
- Media offline được xuất kho và xử lý thủ công.
- Dịch vụ hỗ trợ của bên thứ ba được cấp quyền trong một cửa sổ bảo trì.

Mỗi đường phải được đánh dấu là có quan sát, quan sát một phần hoặc chưa có bằng chứng. Không có log tại một đường truy cập không chứng minh đường đó chưa được sử dụng.

### 2.3. Ma trận phạm vi kiểm toán

| Thành phần | Hoạt động cần thấy | Nguồn bằng chứng có thể dùng |
|---|---|---|
| Nền tảng backup | Đăng nhập, đọc catalog, tạo restore, export, xóa, đổi retention | Audit event và lịch sử job của nền tảng |
| Kho lưu trữ | Đọc/ghi/xóa đối tượng, thay policy, thay quyền hoặc nơi replication | Log truy cập dữ liệu và log quản trị storage |
| Dịch vụ khóa | Dùng khóa để giải mã, đổi grant, vô hiệu hóa hoặc lên lịch hủy khóa | Audit của dịch vụ quản lý khóa |
| PAM và định danh | Yêu cầu quyền, phê duyệt, cấp quyền, phiên, thu hồi, break-glass | Ledger cấp quyền, log định danh, metadata phiên |
| Máy đích restore | Nhận dữ liệu, mount, mở dịch vụ, truy cập bản khôi phục | Log hệ điều hành, storage và ứng dụng tại đích |
| Hệ thống audit | Thay cấu hình thu thập, mất kết nối, thay retention, truy cập/xóa log | Audit quản trị collector và kho bằng chứng |
| Media offline | Xuất/nhập kho, bàn giao, mở niêm phong, sử dụng và hoàn trả | Biên bản bàn giao và dấu vết truy cập kho |

Khả năng ghi log phụ thuộc sản phẩm, cách triển khai và cấu hình. Phải xác minh từng nguồn có ghi đúng loại thao tác cần dùng trước khi thiết kế phát hiện dựa vào nguồn đó.

## 3. Tách kiểm toán quyền khỏi kiểm toán hoạt động

Hai loại kiểm tra này bổ sung cho nhau nhưng không thay thế nhau.

**Kiểm toán quyền** trả lời ai có thể làm gì tại thời điểm được kiểm tra. Nó cần xem quyền trực tiếp, quyền qua nhóm, role có thể assume, trust policy, điều kiện cấp quyền và các quyền quản trị giúp tự mở rộng khả năng.

**Kiểm toán hoạt động** trả lời đã có thao tác gì xảy ra. Nó cần sự kiện thực tế, kết quả, tài nguyên, thời gian, chuỗi thực thi và danh tính liên quan.

Một tài khoản không sử dụng quyền trong ba tháng vẫn có thể là rủi ro lớn nếu luôn có quyền xuất mọi backup. Ngược lại, việc role được thu hồi hôm nay không giải thích được quyền hiệu lực của một lần restore xảy ra tuần trước.

Cần giữ bằng chứng cấu hình và cấp quyền theo thời điểm, chẳng hạn:

- Phiên bản role hoặc policy được áp dụng.
- Thành viên nhóm và quan hệ ủy quyền tại thời điểm thao tác.
- Grant JIT được phê duyệt, thời điểm có hiệu lực và hết hạn.
- Thuộc tính phạm vi: backup set, môi trường nguồn, đích khôi phục và hành động.
- Kết quả thu hồi quyền thực tế, không chỉ thời điểm gửi yêu cầu thu hồi.

Nếu chỉ còn trạng thái hiện tại, phải ghi rõ hạn chế khi đánh giá sự kiện quá khứ. Không tự suy ra rằng quyền hôm nay cũng là quyền khi sự kiện xảy ra.

## 4. Liên kết danh tính con người, tài khoản đặc quyền và workload

### 4.1. Truy vết chủ thể xuyên suốt chuỗi

Một yêu cầu restore có thể bắt đầu từ người vận hành, được PAM cấp role, rồi được dịch vụ backup thực thi bất đồng bộ bằng service account. Log storage sau đó có thể chỉ ghi service account.

Cần phân biệt:

- **Requesting identity**: danh tính yêu cầu công việc.
- **Approving identity**: danh tính phê duyệt.
- **Effective principal**: chủ thể thực sự gọi API hoặc truy cập dữ liệu tại một bước.
- **Delegation chain**: chuỗi ủy quyền giữa người, role, dịch vụ và hệ thống đích.
- **Session hoặc credential instance**: phiên hay credential cụ thể được dùng.

Không ghi “người A tải dữ liệu” chỉ vì A yêu cầu job, trong khi nguồn dữ liệu mới xác nhận dịch vụ B thực hiện. Kết luận chính xác hơn là A khởi tạo operation, B thực thi bước đọc và dữ liệu được đưa tới đích C theo chuỗi bằng chứng đã liên kết.

Tài khoản dùng chung làm giảm khả năng quy trách nhiệm. Nếu chưa loại bỏ được, việc checkout credential, định danh người nhận, thời gian sử dụng và phiên liên quan phải có bằng chứng; mức độ chắc chắn vẫn phụ thuộc khả năng truy cập ngoài cơ chế checkout đó.

### 4.2. Các khóa tương quan nên có

| Định danh | Vai trò |
|---|---|
| event_id | Nhận diện một sự kiện để phát hiện trùng lặp |
| request_id | Liên kết với yêu cầu nghiệp vụ hoặc ticket |
| grant_id và grant_snapshot_id | Liên kết quyền được cấp và phiên bản bằng chứng phạm vi |
| operation_id | Liên kết toàn bộ một công việc restore/export/xóa |
| attempt_id | Phân biệt từng lần thực thi hoặc retry của operation |
| session_id | Liên kết phiên PAM, khi thao tác có đi qua phiên đó |
| source_request_id | Liên kết với mã yêu cầu gốc của hệ thống phát sinh |
| resource_id và destination_id | Xác định bản sao nguồn và đích xử lý |

Không phải mọi nguồn đều cung cấp đủ trường. Với nguồn thiếu correlation ID, có thể ghép theo các thuộc tính như principal, tài nguyên, mã job và thời gian, nhưng phải ghi rõ đó là liên kết suy luận và mức độ tin cậy.

Địa chỉ IP và tên hiển thị có ích để điều tra, song không nên làm khóa định danh duy nhất. NAT, đổi tên tài khoản, proxy và workload tái tạo có thể làm cách ghép này sai lệch.

## 5. Thiết kế sự kiện audit có thể sử dụng được

### 5.1. Nội dung tối thiểu

Một sự kiện hữu ích thường cần:

- Nguồn phát sinh, phiên bản schema và định danh sự kiện.
- Thời điểm sự kiện xảy ra và thời điểm hệ thống thu thập nhận được.
- Principal hiệu lực, nguồn xác thực và thông tin ủy quyền nếu có.
- Hành động cụ thể, loại tài nguyên, định danh tài nguyên và môi trường.
- Kết quả: được yêu cầu, bị từ chối, đã bắt đầu, hoàn tất, thất bại hoặc một phần.
- Mã yêu cầu/job/operation để liên kết các bước.
- Phạm vi quyền và quyết định cho phép hoặc từ chối nếu nguồn có cung cấp.
- Đích restore/export hoặc nơi dữ liệu được đưa tới.
- Trường tham chiếu bằng chứng gốc để có thể kiểm tra lại.

Đối với thay đổi chính sách, cần biết trường cấu hình nào thay đổi, giá trị trước/sau phù hợp để audit và chủ thể thực hiện. Không ghi nguyên policy hoặc cấu hình nếu chúng chứa bí mật chưa được loại bỏ.

### 5.2. Ví dụ sự kiện chuẩn hóa

Ví dụ dưới đây là schema minh họa, không phải định dạng bắt buộc của một sản phẩm:

~~~json
{
  "schema_version": "1",
  "event_id": "evt-demo-0042",
  "event_type": "backup.export.completed",
  "occurred_at": "2026-10-12T03:18:24Z",
  "received_at": "2026-10-12T03:18:31Z",
  "source_system": "backup-service-demo",
  "source_request_id": "src-req-662",
  "request_id": "REQ-DEMO-104",
  "grant_id": "grant-demo-104",
  "grant_snapshot_id": "grant-demo-104-v1",
  "operation_id": "op-demo-77",
  "attempt_id": "attempt-1",
  "session_id": "pam-session-demo-19",
  "requesting_identity": "user-demo-17",
  "effective_principal": "backup-export-worker-demo",
  "delegation_reference": "delegation-demo-77",
  "resource": {
    "id": "backup-set-demo-20261012",
    "environment": "production",
    "classification": "restricted"
  },
  "destination": {
    "id": "recovery-staging-demo",
    "environment": "recovery-test"
  },
  "action": "export",
  "result": "success",
  "bytes_transferred": 734003200,
  "evidence_reference": "audit-source-demo/evt-demo-0042"
}
~~~

Sự kiện này giúp đối chiếu một lần export với quyền và yêu cầu liên quan. Nó chưa tự chứng minh đích staging đã được dọn sạch, người dùng không tiếp tục sao chép dữ liệu hoặc mọi bước giải mã đều hợp lệ.

Cần xác định rõ bytes_transferred là số byte nào: dữ liệu thực đọc, dữ liệu nén hay số byte được gửi tới đích. Không cộng số byte từ nhiều lớp log mà chưa biết chúng có phản ánh cùng một lần truyền hay không.

### 5.3. Không biến log thành một bản sao dữ liệu nhạy cảm

Không đưa vào log:

- Mật khẩu, token, private key, recovery key hoặc giá trị secret.
- URL chứa credential, chữ ký truy cập hoặc token có thể tái sử dụng.
- Dữ liệu nghiệp vụ được khôi phục, nội dung file và bản dump.
- Output lệnh hoặc bản ghi phiên chứa bí mật mà chưa có cơ chế kiểm soát phù hợp.

Ưu tiên định danh ổn định và tham chiếu tới nguồn được phân quyền. Bản thân log vẫn có thể chứa tên hệ thống, người dùng và thông tin nhạy cảm nên cần quyền truy cập, retention và cơ chế xuất bằng chứng riêng.

Che thông tin nhạy cảm phải giữ được khả năng điều tra cần thiết. Nếu dùng định danh thay thế, bảng ánh xạ phải được bảo vệ và việc mở ánh xạ phải được ghi nhận.

## 6. Chứng minh một chuỗi thao tác, không chỉ một lần đăng nhập

Một chuỗi restore có thể được biểu diễn như sau:

~~~text
Yêu cầu được tạo
  → phạm vi được phê duyệt
  → quyền được cấp
  → danh tính đặc quyền được sử dụng
  → job được chấp nhận
  → dữ liệu nguồn được đọc / khóa được sử dụng
  → dữ liệu xuất hiện tại đích
  → kiểm tra kết quả
  → kết thúc quyền và phiên
  → xử lý bản sao tạm theo yêu cầu
~~~

Mỗi mũi tên là một liên kết cần bằng chứng. Các bước có thể diễn ra ở nhiều hệ thống và không nhất thiết tạo log theo đúng thứ tự nhận tại collector.

Những phân biệt quan trọng:

| Bằng chứng quan sát được | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| Đăng nhập console thành công | Một danh tính đã xác thực vào console | Đã đọc nội dung backup |
| API chấp nhận yêu cầu restore | Yêu cầu đã được tiếp nhận | Restore đã hoàn tất |
| Job báo thành công | Nền tảng báo hoàn tất theo định nghĩa job | Mọi dữ liệu tại đích đều an toàn hoặc đã được dọn |
| Storage ghi nhận đọc object | Principal đã thực hiện thao tác đọc được ghi nhận | Principal con người cuối cùng là ai nếu thiếu chuỗi ủy quyền |
| Dịch vụ khóa ghi nhận giải mã | Có thao tác dùng khóa được ghi nhận | Toàn bộ dữ liệu giải mã đã được đọc hoặc xuất |
| Yêu cầu thu hồi được gửi | Hệ thống đã nhận yêu cầu thu hồi | Quyền/token/phiên đã hết hiệu lực ở mọi tầng |

Với job bất đồng bộ, cần quy định rõ grant cấp quyền khởi tạo hay cấp quyền cho toàn bộ thời gian thực thi. Nếu job được phép tiếp tục sau khi cửa sổ khởi tạo kết thúc, bằng chứng phải thể hiện chính sách đó và deadline riêng của job. Không tự coi mọi sự kiện sau giờ hết grant là vi phạm, cũng không mặc nhiên cho phép job chạy vô thời hạn.

Retry phải giữ liên kết operation nhưng có attempt riêng. Job thất bại vẫn có thể đã đọc dữ liệu hoặc tạo bản sao một phần; trạng thái thất bại không xóa nghĩa vụ kiểm tra dữ liệu đã được đưa ra.

## 7. Bảo vệ độ tin cậy của bằng chứng

### 7.1. Tách quyền vận hành khỏi quyền làm mất dấu vết

Một backup administrator có thể cần quản lý job nhưng không nên mặc nhiên có quyền sửa hoặc xóa bản ghi audit của chính mình.

Thiết kế có thể gồm:

- Chuyển log tới miền quản trị hoặc tài khoản lưu trữ có quyền tách biệt.
- Collector có quyền nhận/ghi cần thiết, không có quyền sửa lịch sử tùy ý.
- Người điều tra có quyền đọc theo vụ việc, không kiêm quyền vô hiệu hóa thu thập.
- Mọi thay đổi pipeline audit, quyền đọc log và chính sách retention đều được audit.
- Cơ chế bảo vệ bản ghi chống sửa/xóa phù hợp với yêu cầu và khả năng nền tảng.

“Tách biệt” phải kiểm tra bằng quyền hiệu lực. Hai role tên khác nhau nhưng cùng một nhóm quản trị có thể tự cấp cả hai quyền chưa tạo ra sự phân tách thực chất.

Cơ chế lưu bất biến cũng cần được kiểm tra theo cấu hình thực tế: ai có thể thay policy, thay thời gian giữ, quản lý khóa mã hóa và tác động đến các bản ghi đã có. Không suy ra mức bảo vệ chỉ từ nhãn sản phẩm.

### 7.2. Kiểm tra tính toàn vẹn và nguồn gốc

Hash của file bằng chứng giúp phát hiện file thay đổi sau lúc tính hash. Hash đơn lẻ không chứng minh ai tạo file hoặc file đã phản ánh đủ sự kiện từ hệ thống nguồn.

Gói bằng chứng nên lưu:

- Nguồn và phương pháp trích xuất.
- Người hoặc workload thực hiện trích xuất.
- Khoảng thời gian, múi giờ và bộ lọc.
- Số lượng bản ghi và thông tin phân trang.
- Hash, thời điểm tạo và nơi lưu kết quả.
- Cách bảo vệ manifest hoặc chữ ký nếu có.
- Lịch sử bàn giao khi chuyển cho người điều tra khác.

Nếu một người có thể sửa cả file lẫn manifest hash mà không để lại dấu vết, kiểm tra hash sẽ không giải quyết được rủi ro đó.

### 7.3. Tính đầy đủ và thời gian

Theo dõi riêng sức khỏe của nguồn log:

- Lần cuối nhận sự kiện hoặc heartbeat từ nguồn.
- Độ trễ thu thập, hàng đợi, lỗi gửi và số bản ghi bị loại bỏ.
- Thiếu sequence hoặc thiếu trang khi nguồn có hỗ trợ kiểm tra.
- Thay đổi schema, lỗi parse và trường bắt buộc bị rỗng.
- Tình trạng đồng bộ thời gian của hệ thống phát sinh.

Cửa sổ “không có hoạt động” chỉ có ý nghĩa nếu nguồn vẫn được quan sát. Khi nguồn bị mất log trong một giờ, kết luận thích hợp là chưa đủ bằng chứng cho một giờ đó.

Giữ cả occurred_at và received_at. Khi đồng hồ nguồn sai lệch, cần ghi rõ độ bất định; không ép một thứ tự chính xác từ các timestamp chưa đủ tin cậy.

## 8. Kiểm toán least privilege, JIT và JEA cho backup

### 8.1. Đánh giá quyền theo hành động và tài nguyên

Một role quá rộng thường chứa nhiều khả năng không liên quan trực tiếp đến nhiệm vụ. Cần kiểm tra riêng quyền:

- Xem metadata.
- Đọc nội dung hoặc tải bản sao.
- Khởi tạo restore.
- Chọn hoặc thay đích restore.
- Mount snapshot và truy cập dữ liệu sau mount.
- Sử dụng khóa cần cho khôi phục.
- Xóa, thay retention hoặc thay cơ chế bảo vệ.
- Cấp quyền cho principal khác.
- Thay cấu hình audit.

Ví dụ một role hỗ trợ diễn tập có thể được restore đúng backup set vào đúng recovery network, nhưng không được export tùy ý, restore vào production hoặc thay retention. JEA có ích khi giới hạn được thao tác và tham số ở đường thực thi thực tế; một menu hạn chế không đủ nếu cùng tài khoản vẫn gọi được API rộng hơn.

### 8.2. Bằng chứng về một grant JIT

Một grant nên gắn với tối thiểu:

| Thuộc tính | Câu hỏi audit |
|---|---|
| Người nhận hoặc workload nhận quyền | Có khớp principal hoặc chuỗi ủy quyền đã cho phép không? |
| Hành động | Restore có bị dùng thành export hoặc delete không? |
| Tài nguyên nguồn | Có bao phủ đúng backup set hoặc snapshot không? |
| Đích và môi trường | Dữ liệu có đi tới nơi đã duyệt không? |
| Thời gian | Thao tác có tuân thủ chính sách thời gian của grant/job không? |
| Người duyệt và điều kiện | Có đúng thẩm quyền, có xung đột vai trò không? |
| Phiên bản phạm vi | Có bằng chứng phạm vi tại thời điểm thao tác không? |
| Kết thúc | Quyền, phiên và credential còn hiệu lực đến khi nào? |

Cần kiểm tra quyền hiệu lực sau thu hồi, nhất là token đã phát hành, phiên đang mở, credential được cache và đường truy cập trực tiếp vào storage. “Role đã bị gỡ khỏi người dùng” không tự chứng minh mọi khả năng truy cập đã chấm dứt.

### 8.3. Service account cũng cần audit

Không áp dụng mô hình phê duyệt thủ công cho từng lần đọc nội bộ nếu kiến trúc yêu cầu workload hoạt động liên tục. Thay vào đó, cần kiểm tra chủ sở hữu, chức năng, phạm vi quyền, ràng buộc nguồn thực thi, vòng đời credential và lịch chạy kỳ vọng.

Phân biệt:

- Workload backup định kỳ được phép đọc nguồn để tạo bản sao.
- Workload restore theo yêu cầu được phép đưa dữ liệu tới một đích cụ thể.
- Tài khoản hỗ trợ có quyền vận hành tương tác.

Dùng chung một principal cho cả ba làm khó việc tách hành vi bình thường và đặc quyền phát sinh.

## 9. Quy trình thực hiện một cuộc audit

### Bước 1 — Chốt câu hỏi, phạm vi và thời gian

Xác định hệ thống, backup set, tài khoản, môi trường, khoảng thời gian và loại hành động cần đánh giá. Ghi rõ có bao gồm đường trực tiếp, khóa giải mã, bản sao thứ cấp và media offline hay không.

Chọn tiêu chí từ chính sách nội bộ đã được phê duyệt. Những mốc thời gian trong ví dụ đào tạo không tự trở thành yêu cầu vận hành.

### Bước 2 — Lập bản đồ quyền và đường truy cập

Đọc danh sách quyền, quan hệ nhóm, service account, cơ chế JIT/JEA, break-glass và các đường quản trị ngoài PAM. Xác định ai có thể tự cấp thêm quyền hoặc vô hiệu hóa log.

Đánh dấu các quyền thường trực cần giải thích và những đường không có quan sát đầy đủ.

### Bước 3 — Xác nhận bằng chứng có đủ dùng

Kiểm tra coverage, sức khỏe nguồn, độ trễ, retention, timezone và cách liên kết ID. Thử một thao tác kiểm soát trong môi trường được phép để xác nhận sự kiện cần thiết thực sự xuất hiện.

Một nguồn có nhiều bản ghi không bảo đảm đã ghi thao tác đọc dữ liệu. Log quản trị và log truy cập dữ liệu có thể có phạm vi khác nhau.

### Bước 4 — Thu thập và chuẩn hóa

Giữ bản gốc theo cơ chế được phép; tạo bản chuẩn hóa để phân tích. Giữ liên kết tới nguồn, bảo toàn timezone gốc và tránh loại bỏ bản ghi chỉ vì chưa parse được.

Chống trùng theo định danh nguồn phù hợp. Không gộp mọi retry thành một lần rồi làm mất chi tiết về số lần truy cập.

### Bước 5 — Đối chiếu quyền, yêu cầu và hoạt động

Với mỗi operation được chọn, đối chiếu:

1. Yêu cầu và người duyệt.
2. Grant hoặc quyền workload hợp lệ.
3. Principal hiệu lực và chuỗi ủy quyền.
4. Hành động, tài nguyên, đích và thời gian.
5. Kết quả tại nền tảng backup và tầng dữ liệu.
6. Thu hồi quyền và xử lý bản sao tạm.
7. Tính đầy đủ của các nguồn bằng chứng liên quan.

Nếu lấy mẫu, ghi phương pháp và giới hạn. Có thể ưu tiên các hành động rủi ro cao như export, thay retention và break-glass, đồng thời lấy mẫu hoạt động bình thường. Kết quả từ một mẫu không tự chứng minh mọi operation còn lại đều tuân thủ.

### Bước 6 — Phân loại kết quả

Dùng ba trạng thái rõ ràng:

- **Phù hợp**: bằng chứng đủ và đáp ứng tiêu chí đã chọn.
- **Không phù hợp**: bằng chứng cho thấy vi phạm một tiêu chí cụ thể.
- **Chưa đủ bằng chứng**: thiếu nguồn, thiếu liên kết hoặc không chứng minh được điều kiện cần thiết.

Tách lỗi kiểm soát khỏi khoảng trống quan sát. Một lần export không có approval trong dữ liệu thu thập là ứng viên cần điều tra; chỉ kết luận “không được duyệt” khi đã kiểm tra nguồn phê duyệt và chất lượng liên kết.

### Bước 7 — Theo dõi khắc phục và kiểm tra lại

Mỗi phát hiện cần chủ sở hữu, mức ưu tiên, phạm vi ảnh hưởng, việc khắc phục và tiêu chí đóng. Kiểm tra lại bằng chứng sau sửa, chẳng hạn quyền đã được thu hẹp và một lần truy cập vượt phạm vi bị từ chối đồng thời được ghi log.

Không đóng phát hiện chỉ vì có ticket “đã xử lý”.

## 10. Phát hiện dấu hiệu cần điều tra

### 10.1. Các tình huống đáng chú ý

| Dấu hiệu | Giả thuyết cần kiểm tra | Bằng chứng bổ sung |
|---|---|---|
| Export thành công nhưng chưa ghép được grant | Thiếu phê duyệt, sai correlation hoặc đường ngoài quy trình | Nguồn approval, ledger PAM, quyền workload |
| Restore sang đích khác phạm vi | Sai cấu hình, yêu cầu thay đổi hoặc đưa dữ liệu ra ngoài | Phiên bản grant, đích thực tế, lịch sử thay đổi job |
| Nhiều thao tác bị từ chối rồi có thao tác thành công | Thử quyền, lỗi vận hành hoặc leo thang quyền | Role changes, chuỗi phiên, nội dung yêu cầu |
| Đổi retention gần lúc xóa bản sao | Thay đổi hợp lệ hoặc phá khả năng khôi phục | Quyết định duyệt, diff cấu hình, kết quả xóa |
| Log ngừng trong khi API backup vẫn hoạt động | Sự cố thu thập hoặc tác động vào audit | Collector, cấu hình audit, nguồn độc lập |
| Dùng khóa từ principal không quen thuộc | Workload mới, cấu hình sai hoặc sử dụng trái phép | Grant khóa, nguồn gọi, operation liên quan |
| Nhiều dữ liệu được đọc ngoài lịch thường lệ | Diễn tập, phục hồi sự cố hoặc truy xuất bất thường | Incident record, lịch bảo trì, đích dữ liệu |
| Break-glass kết thúc nhưng vẫn còn quyền đọc | Thu hồi chưa đủ hoặc credential còn sống | Token/phiên, policy storage, kiểm thử truy cập |

Những dấu hiệu này không phải kết luận về ý định của người dùng. Phải kiểm tra ngữ cảnh, thay đổi được duyệt và chất lượng dữ liệu.

### 10.2. Ví dụ đối chiếu phạm vi bằng SQL

Giả sử pipeline đã chuẩn hóa một tập sự kiện hoàn tất thành công và một tập snapshot grant bất biến. Ví dụ chỉ xét export có grant áp dụng theo thời điểm thao tác; chính sách cho job bất đồng bộ khác phải được xử lý riêng.

~~~sql
SELECT
    e.event_id,
    e.operation_id,
    e.effective_principal,
    e.resource_id,
    e.destination_id,
    e.occurred_at
FROM backup_audit_event e
LEFT JOIN approved_grant_snapshot g
    ON g.grant_snapshot_id = e.grant_snapshot_id
WHERE e.action = 'export'
  AND e.result = 'success'
  AND e.occurred_at >= :window_start
  AND e.occurred_at <  :window_end
  AND (
       g.grant_snapshot_id IS NULL
       OR g.approved <> 1
       OR g.approved IS NULL
       OR g.execution_principal IS NULL
       OR e.effective_principal IS NULL
       OR g.execution_principal <> e.effective_principal
       OR g.allowed_action IS NULL
       OR g.allowed_action <> e.action
       OR g.resource_id IS NULL
       OR e.resource_id IS NULL
       OR g.resource_id <> e.resource_id
       OR g.destination_id IS NULL
       OR e.destination_id IS NULL
       OR g.destination_id <> e.destination_id
       OR g.valid_from IS NULL
       OR g.valid_until IS NULL
       OR e.occurred_at <  g.valid_from
       OR e.occurred_at >= g.valid_until
  );
~~~

Điều kiện minh họa dùng khoảng thời gian nửa mở: gồm valid_from, không gồm valid_until. Tất cả thời điểm phải được chuẩn hóa và có kiểu dữ liệu thời gian phù hợp.

Các giả định phải kiểm tra trước khi dùng:

- Mỗi grant_snapshot_id xác định duy nhất một bản ghi phạm vi.
- execution_principal đã phản ánh đúng principal thực thi được ủy quyền; không ghép tùy tiện người yêu cầu với tài khoản dịch vụ.
- Tài nguyên và đích trong mô hình là một giá trị cụ thể. Grant nhiều tài nguyên cần bảng phạm vi hoặc phép đối chiếu tương ứng.
- approval là trạng thái có hiệu lực cho sự kiện, không phải một trường hiện tại có thể bị chỉnh mà mất lịch sử.
- Có kiểm soát riêng với bản ghi thiếu occurred_at, ngoài khoảng kiểm toán hoặc lỗi parse.
- Nguồn sự kiện và snapshot đã được kiểm tra tính đầy đủ.

Kết quả truy vấn là danh sách cần đối chiếu. Nó không thay thế cơ chế chặn truy cập và không đủ để kết luận toàn bộ hệ thống tuân thủ khi không trả về dòng nào.

## 11. Audit trong sự cố và truy cập break-glass

Khi hệ thống định danh, vault hoặc mạng chính bị lỗi, quy trình khôi phục có thể phải dùng đường khẩn cấp. Đường này vẫn cần định danh, phạm vi và bằng chứng phù hợp với khả năng hoạt động trong sự cố.

Một quy trình có thể yêu cầu:

- Ghi nhận sự cố, người kích hoạt và lý do.
- Giới hạn credential khẩn cấp theo vai trò khôi phục.
- Ghi thao tác tại nguồn ngay cả khi chưa chuyển được về trung tâm.
- Gắn nhãn hoạt động break-glass và giữ liên kết incident.
- Đối chiếu sau khi kết nối được khôi phục.
- Thu hồi phiên/quyền tạm, xử lý credential và xác minh kết quả.
- Kiểm tra độc lập bởi người không thực hiện thao tác.

Việc vận hành khi hệ thống audit không sẵn sàng cần được quy định trước: thao tác nào phải chặn, thao tác nào được tiếp tục theo quyền khẩn cấp và bằng chứng thay thế nào phải giữ. Không tự quyết định mọi hoạt động được phép bỏ audit chỉ vì cần đạt RTO.

Nếu dùng buffer cục bộ, cần biết dung lượng, thời gian giữ, quyền sửa/xóa và hành vi khi đầy. Sau kết nối, phải phân biệt thời gian xảy ra với thời gian gửi lại và kiểm tra phần bị mất.

Bằng chứng tái dựng từ ticket, lịch sử job và biên bản sau sự cố có giá trị, nhưng phải ghi rõ nguồn và độ chắc chắn. Không tạo lại các “sự kiện gốc” giả như thể đã được ghi nhận ngay tại thời điểm thao tác.

## 12. Tình huống: restore đúng yêu cầu nhưng phát sinh bản sao ngoài phạm vi

Đội vận hành cần khôi phục backup-set-demo vào recovery-test để kiểm tra khả năng phục hồi. Yêu cầu đã được duyệt cho restore tới recovery-target-A, trong một cửa sổ diễn tập xác định.

Quan sát được:

1. Người vận hành nhận grant JIT và mở phiên PAM.
2. Nền tảng backup khởi tạo restore tới recovery-target-A.
3. Job báo hoàn tất, máy đích xác nhận đã nhận dữ liệu.
4. Một API storage ghi nhận cùng chuỗi principal xuất một archive tới staging-B.
5. Grant chỉ cho phép restore tới recovery-target-A.
6. Sau diễn tập, phiên PAM kết thúc nhưng policy của staging-B còn cho phép đọc archive.

Đánh giá:

- Restore ban đầu có thể phù hợp nếu toàn bộ phạm vi và thời gian đã được đối chiếu.
- Export là một thao tác khác, cần kiểm tra có yêu cầu và quyền hợp lệ riêng không.
- Kết thúc phiên PAM không chứng minh archive tại staging-B đã mất khả năng truy cập.
- Cần xác định ai có thể đọc staging-B, archive đã được đọc hay sao chép tiếp chưa và bằng chứng có đầy đủ không.
- Nếu nguồn approval đầy đủ xác nhận không có phép export, có cơ sở ghi nhận thao tác vượt phạm vi.
- Nếu log staging-B bị thiếu trong một khoảng, phải ghi nhận chưa xác định được hoạt động trong khoảng đó.

Hướng khắc phục được chọn theo phát hiện thực tế: thu hẹp quyền export, ràng buộc đích, tách principal restore và export nếu cần, quản lý vòng đời staging, kiểm tra thu hồi quyền và bổ sung log truy cập dữ liệu tại đích.

Tình huống cho thấy kiểm toán phải đi theo vòng đời dữ liệu. Chỉ đọc bản ghi phiên và trạng thái job sẽ bỏ lỡ bản sao phát sinh sau restore.

## 13. Bài thực hành xây dựng gói bằng chứng

Thực hành trong môi trường lab được phép, dùng dữ liệu tổng hợp. Mục tiêu là chứng minh khả năng quan sát và đối chiếu, không cần bản backup chứa dữ liệu thật.

### 13.1. Thiết lập phạm vi

Chuẩn bị một backup set thử nghiệm, một đích restore được phép và một đích khác nằm ngoài phạm vi grant. Định nghĩa role có quyền restore giới hạn, role audit chỉ đọc bằng chứng và một yêu cầu diễn tập.

Ghi trước kỳ vọng:

| Thao tác thử | Kết quả kiểm soát mong đợi | Bằng chứng mong đợi |
|---|---|---|
| Restore đúng nguồn và đích | Được phép | Grant, job, dữ liệu tại đích và liên kết principal |
| Restore sang đích không được phép | Bị từ chối | Quyết định từ chối, principal, nguồn và đích yêu cầu |
| Export ngoài phạm vi | Bị từ chối | Sự kiện ở đường thực thi export |
| Truy cập bằng quyền tạm sau khi kết thúc | Bị từ chối theo chính sách | Bằng chứng thu hồi và kết quả thử |
| Người vận hành thử sửa pipeline audit | Bị từ chối nếu role không có quyền | Audit quản trị liên quan |
| Nguồn log bị gián đoạn có kiểm soát | Phát hiện khoảng trống | Health event, độ trễ và kết quả gửi lại nếu có |

Không giả định hệ thống đã đáp ứng mọi kỳ vọng. Nếu thao tác ngoài phạm vi được phép hoặc không sinh được bằng chứng, ghi nhận như một kết quả thực hành cần xử lý.

### 13.2. Thực hiện và đối chiếu

Thực hiện từng tình huống, lưu ID phát sinh rồi ghép chuỗi operation. Phân biệt lỗi của bài thử với lỗi kiểm soát: chẳng hạn đích không tồn tại gây thất bại khác với việc hệ thống từ chối vì thiếu quyền.

Đối với thao tác bị từ chối, kiểm tra có hiệu ứng một phần trước khi bị chặn hay không khi kiến trúc cho phép nhiều bước. Đối với restore thành công, kiểm tra cả dữ liệu tạm và quyền truy cập sau restore.

### 13.3. Đầu ra cần có

Một gói bằng chứng thực hành nên chứa:

- Phạm vi, sơ đồ đường truy cập và những đường chưa được quan sát.
- Bản quyền hiệu lực hoặc snapshot grant liên quan.
- Sự kiện nguồn và bảng chuẩn hóa có correlation ID.
- Timeline có đánh dấu sự kiện suy luận và khoảng thời gian thiếu log.
- Kết quả từng phép thử cùng tiêu chí đánh giá.
- Manifest trích xuất, hash và giới hạn của bằng chứng.
- Phát hiện, chủ sở hữu khắc phục và cách kiểm tra lại.

Không đưa credential hoặc nội dung backup vào gói. Nếu thiếu một nguồn, mô tả tác động của việc thiếu đó tới kết luận thay vì điền một giá trị suy đoán.

## 14. Viết phát hiện audit rõ ràng

Một phát hiện có thể dùng cấu trúc:

~~~text
Mã: AUD-BACKUP-DEMO-01
Tiêu chí:
  Role diễn tập chỉ được restore tới recovery-target-A.

Quan sát:
  Operation op-demo-77 có sự kiện export thành công tới staging-B.
  Snapshot grant liên quan không bao gồm hành động và đích này.

Bằng chứng:
  Tham chiếu sự kiện backup, storage và grant snapshot.
  Khoảng thời gian, phương pháp trích xuất và manifest tương ứng.

Ảnh hưởng:
  Dữ liệu có thể tồn tại ở một đích ngoài phạm vi kiểm soát của diễn tập.

Giới hạn:
  Chưa đủ log để kết luận archive đã được đọc bởi principal khác.

Khắc phục:
  Ràng buộc quyền và đích export; xử lý vòng đời staging;
  xác minh quyền còn lại và kiểm thử lại.

Tiêu chí đóng:
  Thao tác vượt phạm vi bị từ chối và có bằng chứng;
  quyền/bản sao tạm được xử lý theo quyết định đã duyệt.
~~~

Phân biệt “có thể tiếp cận dữ liệu” với “đã đọc dữ liệu”; phân biệt “không tìm thấy phê duyệt” với “đã chứng minh không có phê duyệt”. Mức độ kết luận phải tương ứng với chất lượng bằng chứng.

## 15. Đánh giá chất lượng chương trình audit backup access

Những số đo hữu ích gồm tỷ lệ operation liên kết được yêu cầu/grant, tỷ lệ đường truy cập có log phù hợp, độ trễ phát hiện mất nguồn, số quyền thường trực chưa có lý do và tỷ lệ thu hồi được xác minh.

Mỗi số đo cần có mẫu số và định nghĩa. “100% operation đã được audit” có thể gây hiểu nhầm nếu operation chỉ lấy từ console trong khi đường đọc storage trực tiếp chưa được thống kê.

Một chương trình audit tốt chứng minh được ba điều: quyền được cấp có giới hạn, hoạt động thực tế được đối chiếu với giới hạn đó và bằng chứng đủ tin cậy để đánh giá. Khi một trong ba điều chưa chứng minh được, kết quả cần thể hiện rõ khoảng trống cùng cách khắc phục.

Đối với backup, phạm vi kiểm toán kéo dài tới cả nơi dữ liệu được khôi phục, bản sao tạm, khóa và đường truy cập khẩn cấp. Đó là cách giữ mục tiêu khôi phục của hệ thống gắn với least privilege và khả năng quy trách nhiệm trong PAM.
