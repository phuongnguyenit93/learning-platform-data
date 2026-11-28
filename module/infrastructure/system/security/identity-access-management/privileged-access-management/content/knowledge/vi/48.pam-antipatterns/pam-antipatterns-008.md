# Cho vendor quyền không giới hạn

## 1. Anti-pattern này là gì?

Vendor là tổ chức hoặc cá nhân bên ngoài được thuê để triển khai, bảo trì, hỗ trợ hay vận hành một phần hệ thống. Vendor có thể cần quyền đặc biệt để chẩn đoán lỗi, thay cấu hình hoặc thực hiện công việc mà tài khoản thông thường không làm được. Vấn đề xuất hiện khi tổ chức biến nhu cầu làm một công việc cụ thể thành quyền quản trị rộng, tồn tại lâu dài và thiếu kiểm chứng.

**Cho vendor quyền không giới hạn** là anti-pattern trong quản lý truy cập đặc quyền (Privileged Access Management — PAM): phạm vi quyền thực tế của vendor vượt quá nhiệm vụ đã được chấp thuận, hoặc không có giới hạn có thể thực thi về tài nguyên, hành động, thời gian, dữ liệu và đường truy cập.

“Không giới hạn” không nhất thiết có nghĩa là vendor được cấp tài khoản quản trị toàn bộ doanh nghiệp. Một tài khoản chỉ quản trị một ứng dụng vẫn có thể gần như không giới hạn nếu nó được phép xuất toàn bộ dữ liệu, tạo tài khoản mới, tự nâng quyền, thay chính sách hoặc duy trì truy cập sau khi hợp đồng kết thúc.

Ví dụ:

- Nhà cung cấp bảo trì một dịch vụ nhưng được cấp quyền quản trị cả cụm máy chủ.
- Kỹ sư hỗ trợ dùng chung một tài khoản với mọi người trong công ty vendor.
- Quyền được cấp cho một lần xử lý sự cố nhưng không có thời điểm hết hạn.
- Vendor được truy cập qua PAM nhưng vẫn biết mật khẩu để đăng nhập trực tiếp vào máy đích.
- Tổ chức khóa tài khoản trên cổng truy cập, trong khi khóa SSH và phiên đang mở trên hệ thống đích vẫn còn hiệu lực.

Mục tiêu không phải cấm vendor làm việc. Mục tiêu là cung cấp **đủ khả năng để hoàn thành nhiệm vụ, trong một phạm vi kiểm soát được, và chứng minh được quyền đã kết thúc**.

## 2. Vì sao anti-pattern này dễ hình thành?

### 2.1. Bắt đầu từ một ngoại lệ có vẻ hợp lý

Trong một sự cố khẩn cấp, nhóm vận hành có thể cấp quyền cao để vendor xử lý nhanh. Sau khi hệ thống hoạt động trở lại, sự chú ý chuyển sang công việc khác. Quyền tạm thời trở thành quyền thường trực vì không có cơ chế tự hết hạn, người chịu trách nhiệm hoặc bằng chứng phải nộp khi đóng sự cố.

Một vòng lặp thường gặp là:

```text
Sự cố gấp
    → cấp quyền quản trị rộng
    → vendor xử lý thành công
    → giữ quyền để lần sau hỗ trợ nhanh
    → nhiều kỹ sư cùng sử dụng
    → mất khả năng xác định ai làm gì và thu hồi toàn bộ quyền
```

Nếu quyền rộng giúp hoàn thành công việc nhanh hơn, nó dễ được xem là điều kiện kỹ thuật bắt buộc. Tuy nhiên, thành công của một lần xử lý chỉ chứng minh vendor đã thực hiện được công việc; nó không chứng minh mọi quyền đã cấp đều cần thiết.

### 2.2. Thiếu hiểu biết về quyền mà công việc thực sự cần

Đề nghị “cần admin để hỗ trợ” thường gộp nhiều nhu cầu khác nhau:

- Đọc trạng thái và log phục vụ chẩn đoán.
- Khởi động lại một thành phần.
- Thay một tập cấu hình giới hạn.
- Cài bản vá hoặc cập nhật phần mềm.
- Truy cập dữ liệu để tái hiện lỗi.
- Quản lý danh tính và chính sách của chính hệ thống.

Các nhu cầu này có mức rủi ro khác nhau. Không phân rã chúng khiến tổ chức cấp một quyền tổng quát cho toàn bộ quá trình, kể cả những bước chỉ cần đọc.

### 2.3. Nhầm kiểm soát hợp đồng với kiểm soát kỹ thuật

Điều khoản bảo mật và trách nhiệm của vendor giúp xác lập nghĩa vụ, nhưng không tự ngăn một tài khoản truy cập sai tài nguyên hoặc tiếp tục hoạt động sau thời hạn. Tương tự, vendor có uy tín không loại bỏ khả năng một tài khoản, thiết bị hay quy trình nội bộ của họ bị sử dụng sai.

Quyết định tin cậy đối tác cần đi cùng các giới hạn được thực thi trong hệ thống. Cam kết tổ chức và cơ chế kỹ thuật bổ sung cho nhau; không thể dùng một bên thay cho bên kia.

## 3. Đặt quyền vendor trong mô hình PAM

Để kiểm soát một lượt truy cập, cần trả lời tối thiểu sáu câu hỏi:

| Câu hỏi | Thông tin cần xác định | Dấu hiệu thiếu kiểm soát |
| --- | --- | --- |
| Ai đang truy cập? | Cá nhân cụ thể, tổ chức vendor, người bảo trợ nội bộ | Một tài khoản dùng chung, không đối chiếu được người dùng |
| Làm việc gì? | Hành động hoặc quy trình bảo trì được phép | “Toàn quyền để xử lý mọi vấn đề” |
| Trên tài nguyên nào? | Hệ thống, môi trường, tenant hoặc nhóm máy cụ thể | Toàn bộ mạng, mọi môi trường, mọi tài khoản |
| Trong bao lâu? | Cửa sổ được duyệt, thời điểm hết hạn, thời gian nhàn rỗi | Không có hết hạn hoặc chỉ nhắc thu hồi bằng tay |
| Qua đường nào? | Kênh được kiểm soát, danh tính và điều kiện truy cập | Có thể bỏ qua PAM bằng credential đã được chia sẻ |
| Để lại bằng chứng gì? | Yêu cầu, quyết định cấp quyền, phiên và thay đổi | Chỉ có dòng “đã hỗ trợ xong” trong ticket |

Ngoài sáu câu hỏi trên, cần hiểu dữ liệu mà quyền đó có thể tiếp cận. Một hành động “chỉ đọc” vẫn có rủi ro lớn nếu cho phép sao chép dữ liệu nhạy cảm ra ngoài.

### Quyền hiệu dụng mới là điều cần đánh giá

Quyền hiệu dụng là những gì vendor thực sự có thể làm sau khi tổng hợp mọi vai trò, nhóm, tài khoản, credential và đường truy cập liên quan. Nó có thể rộng hơn vai trò được ghi trong yêu cầu.

Ví dụ, vai trò hỗ trợ chỉ cho phép đọc cấu hình nhưng lại đọc được một secret có quyền quản trị. Khi đó khả năng thực tế không dừng ở đọc cấu hình. Tương tự, khả năng sửa chương trình chạy bằng tài khoản đặc quyền có thể gián tiếp tạo ra khả năng thực thi với đặc quyền đó.

Vì vậy, cần đánh giá cả **quyền được cấp trực tiếp** và **khả năng mở rộng quyền thông qua tài nguyên được phép tác động**. Việc đặt tên vai trò là `VendorReadOnly` không đủ chứng minh nó ít quyền.

## 4. Rủi ro đến từ những khoảng trống nào?

### 4.1. Phạm vi ảnh hưởng lớn hơn phạm vi hợp đồng

Vendor được thuê bảo trì ứng dụng A nhưng dùng cùng đường quản trị với ứng dụng B và C. Một thao tác nhầm, cấu hình sai hoặc sự cố danh tính có thể ảnh hưởng nhiều hệ thống không liên quan đến nhiệm vụ.

Phạm vi ảnh hưởng — thường gọi là blast radius — phụ thuộc vào tài nguyên có thể tác động, loại hành động và khả năng đi tiếp từ tài nguyên đầu tiên. Giới hạn địa chỉ mạng không tự giới hạn quyền bên trong máy chủ hoặc ứng dụng đã truy cập được.

### 4.2. Không quy trách nhiệm được cho từng người

Nếu nhiều kỹ sư biết cùng một mật khẩu, log tài khoản đích chỉ cho biết một danh tính kỹ thuật. Khi cần điều tra, tổ chức khó xác định ai là người thao tác, ai phê duyệt, và liệu credential có được sử dụng ngoài phiên hợp lệ hay không.

PAM có thể hỗ trợ ánh xạ người dùng cá nhân sang tài khoản đích được môi giới. Điều đó chỉ có giá trị nếu kênh trực tiếp bị kiểm soát và mỗi lần sử dụng đều gắn với danh tính xác thực. Một mật khẩu dùng chung có thể đăng nhập từ nhiều nơi vẫn làm đứt chuỗi quy trách nhiệm.

### 4.3. Truy cập tồn tại sau khi nhu cầu kết thúc

Những hình thức tồn tại có thể bao gồm:

- Thành viên nhóm đặc quyền không bị xóa.
- Khóa công khai SSH vẫn còn trên máy chủ.
- Token, khóa API hoặc credential dịch vụ có thời hạn dài.
- Phiên đang mở, kết nối được duy trì hoặc job đã được lập lịch.
- Tài khoản phụ, tích hợp hoặc cơ chế ủy quyền do vendor tạo trong quá trình bảo trì.

Khóa một tài khoản ở một lớp không chứng minh các khả năng trên đã biến mất. Cần hiểu cơ chế cấp và thu hồi của từng loại quyền được sử dụng.

### 4.4. Quyền quản trị cho phép làm suy yếu chính kiểm soát

Một vendor vừa vận hành hệ thống vừa có quyền xóa log, sửa chính sách truy cập và quản lý tài khoản sẽ có khả năng tác động đến bằng chứng và hàng rào kiểm soát. Ngay cả khi không có ý định xấu, thao tác bảo trì vẫn có thể làm mất log hoặc vô hiệu hóa cảnh báo.

Phân tách quyền quản trị ứng dụng, quyền quản trị nền tảng PAM và quyền quản lý bằng chứng giúp giảm sự phụ thuộc vào một người hoặc một tài khoản duy nhất.

## 5. Một tình huống minh họa

Giả sử doanh nghiệp An Phú thuê vendor bảo trì bộ xử lý đơn hàng `order-worker` trong môi trường production. Công việc gồm đọc log đã lọc thông tin nhạy cảm, kiểm tra sức khỏe dịch vụ và khởi động lại dịch vụ sau khi thay một tham số được duyệt.

Thiết kế ban đầu cấp cho vendor một tài khoản quản trị máy chủ dùng chung, VPN vào mạng production và mật khẩu không hết hạn. Kỹ sư vendor có thể đăng nhập bất kỳ lúc nào, đọc thư mục của ứng dụng khác và thay cấu hình hệ điều hành.

Quyền thực tế rộng hơn công việc theo nhiều chiều:

| Chiều kiểm soát | Thiết kế ban đầu | Thiết kế theo nhiệm vụ |
| --- | --- | --- |
| Danh tính | Một tài khoản cho cả vendor | Từng kỹ sư, có người bảo trợ nội bộ |
| Tài nguyên | Mọi máy trong vùng VPN được mở | Các instance `order-worker` đã chọn |
| Hành động | Shell quản trị tổng quát | Đọc log được duyệt, kiểm tra sức khỏe, restart có kiểm soát |
| Thời gian | Bất kỳ lúc nào | Cửa sổ bảo trì được duyệt, tự hết hạn |
| Credential | Mật khẩu được chia sẻ | Môi giới truy cập hoặc credential ngắn hạn theo khả năng nền tảng |
| Bằng chứng | Log đăng nhập rời rạc | Ticket, danh tính, phiên, thao tác và kết quả liên kết được |

Nếu thay đổi hệ điều hành là việc phát sinh, tổ chức tạo yêu cầu nâng quyền riêng với phạm vi và thời gian phù hợp. Không mặc nhiên biến vai trò hỗ trợ thường ngày thành quyền quản trị nền tảng lâu dài.

Các tên tài nguyên, vai trò và thời lượng trong bài là ví dụ minh họa. Khi triển khai cần căn cứ vào năng lực phân quyền, hành vi phiên và cơ chế thu hồi của hệ thống thực tế.

## 6. Thiết kế lại bằng least privilege, JIT và JEA

### 6.1. Least privilege: xác định quyền tối thiểu theo công việc

Least privilege là chỉ cấp quyền cần để thực hiện nhiệm vụ. Điểm bắt đầu nên là danh sách thao tác, thay vì một vai trò quản trị có sẵn.

Với ví dụ `order-worker`, có thể phân rã:

1. Xem trạng thái của đúng dịch vụ.
2. Đọc một tập log được chỉ định và kiểm soát nội dung nhạy cảm.
3. Áp dụng thay đổi cấu hình đã được duyệt qua quy trình triển khai.
4. Khởi động lại đúng dịch vụ trong cửa sổ bảo trì.
5. Kiểm tra sức khỏe và bàn giao kết quả.

Sau đó đối chiếu từng thao tác với khả năng phân quyền. Nếu một thao tác chỉ làm được bằng quyền cao hơn, cần ghi rõ lý do, giới hạn thời gian và kiểm soát bù cho thao tác đó.

Không nên tuyên bố đạt least privilege chỉ vì đã chọn vai trò nhỏ nhất trong danh mục. Nếu vai trò nhỏ nhất vẫn quá rộng, cần cân nhắc tách thao tác, xây dựng quy trình môi giới, hoặc để nhân sự nội bộ thực hiện phần đặc quyền.

### 6.2. JIT: chỉ kích hoạt khi có nhu cầu hợp lệ

Just-in-Time access — JIT — hạn chế thời gian quyền tồn tại. Một kỹ sư có danh tính hợp lệ không có nghĩa là luôn có quyền production. Quyền được kích hoạt khi có yêu cầu đáp ứng chính sách, được duyệt nếu cần, và hết hạn theo cơ chế xác định.

Phải phân biệt:

- **Thời hạn quyền:** khoảng thời gian có thể bắt đầu hành động hoặc nhận credential.
- **Thời hạn phiên:** khoảng thời gian kết nối hiện tại còn được sử dụng.
- **Thời hạn credential/token:** thời gian một bằng chứng truy cập được hệ thống đích chấp nhận.

Ba thời hạn có thể khác nhau. Khi thời hạn cấp quyền kết thúc, phiên cũ có thể vẫn hoạt động hoặc token đã cấp vẫn còn hiệu lực, tùy cách hệ thống thực thi. Thiết kế JIT cần xử lý và kiểm tra cả ba.

### 6.3. JEA: giới hạn khả năng trong lúc quyền đang hoạt động

Just Enough Administration — JEA — hướng đến cung cấp đúng thao tác quản trị cần thiết, thay vì một môi trường quản trị tổng quát. Tùy hệ thống, điều này có thể được thực hiện bằng vai trò ứng dụng, endpoint quản trị giới hạn hoặc quy trình được môi giới.

Ví dụ, vendor gọi thao tác “restart `order-worker`” qua một kênh quản trị đã xác thực, thay vì nhận shell toàn quyền. Kênh đó phải cố định tài nguyên và thao tác, kiểm tra đầu vào, đồng thời không mở ra chức năng thực thi lệnh tùy ý.

Một danh sách lệnh được phép không tự bảo đảm giới hạn nếu các lệnh có thể gọi chương trình khác, ghi vào tệp đặc quyền hoặc nhận tham số quá rộng. Phạm vi phải được đánh giá theo khả năng thực tế của toàn bộ quy trình.

JIT và JEA xử lý hai chiều khác nhau: JIT giảm thời gian có quyền, JEA giảm những gì làm được trong khoảng thời gian đó. Chỉ giảm một chiều vẫn có thể để lại rủi ro lớn ở chiều còn lại.

## 7. Các lớp kiểm soát cần phối hợp

### 7.1. Danh tính cá nhân và vòng đời đối tác

Mỗi kỹ sư cần một danh tính quy trách nhiệm được, có tổ chức vendor, người bảo trợ nội bộ và thời điểm rà soát hoặc kết thúc. Xác thực đa yếu tố (MFA) giúp tăng độ tin cậy của đăng nhập nhưng không thay thế giới hạn quyền.

Nếu tích hợp danh tính liên kết với vendor, vẫn cần xác định tổ chức nội bộ kiểm soát ai được vào hệ thống nào. Không nên tự động cấp quyền production cho mọi thành viên của một nhóm phía vendor mà không có chủ sở hữu và điều kiện chấp nhận rõ ràng.

Với nhà thầu phụ, phải biết người thực hiện thực tế và áp dụng quy trình tiếp nhận phù hợp. Không dùng tài khoản của kỹ sư ban đầu để chuyển tiếp quyền cho người khác.

### 7.2. Phân tách môi trường và tài nguyên

Quyền vào môi trường thử nghiệm không mặc nhiên kéo theo quyền production. Quyền bảo trì một tenant hoặc một ứng dụng không mặc nhiên kéo theo tenant hoặc ứng dụng khác.

Đường mạng nên giới hạn đến các điểm truy cập cần thiết. Tuy nhiên, phân đoạn mạng và phân quyền hệ thống đích cần cùng tồn tại: một kết nối đi đúng mạng vẫn có thể thực hiện hành động quá quyền nếu tài khoản đích có đặc quyền rộng.

### 7.3. Vault và credential

Vault giúp quản lý, phân phối và luân chuyển credential, nhưng không tự làm cho tài khoản có ít quyền hơn. Một tài khoản quản trị toàn cục nằm trong vault vẫn là một tài khoản quản trị toàn cục khi được sử dụng.

Ưu tiên tránh tiết lộ credential cho người dùng nếu hạ tầng hỗ trợ môi giới truy cập. Nếu buộc phải cấp credential, cần xác định phạm vi sử dụng, thời hạn, khả năng sao chép và cách vô hiệu hóa sau nhiệm vụ.

Luân chuyển phải tính đến tài khoản dịch vụ và các phụ thuộc hợp lệ. Đổi mật khẩu không có kế hoạch có thể làm gián đoạn hệ thống; không đổi vì sợ gián đoạn lại khiến credential của vendor tồn tại vô hạn. Cần tách danh tính người dùng và danh tính dịch vụ, kiểm kê phụ thuộc rồi chọn quy trình thu hồi phù hợp.

### 7.4. Quản lý phiên và bằng chứng

Mỗi phiên nên liên kết được với cá nhân, yêu cầu đã duyệt, tài nguyên và khoảng thời gian hợp lệ. Tùy loại truy cập, bằng chứng có thể là log lệnh, sự kiện quản trị, nhật ký ứng dụng, bản ghi phiên hoặc kết quả triển khai.

Không phải mọi kênh đều được phản ánh đầy đủ trong một bản ghi màn hình. API, thao tác tự động, truyền tệp và các phiên nền cần được bao phủ bằng nguồn sự kiện phù hợp.

Việc ghi nhận cần có chính sách thông báo, phạm vi, thời hạn lưu và quyền xem phù hợp với tổ chức. Tránh ghi secret hoặc dữ liệu nhạy cảm không cần thiết vào log; người xem bản ghi cũng không nên mặc nhiên có toàn quyền xuất bằng chứng.

### 7.5. Kiểm soát dữ liệu

Nếu vendor chỉ cần xem mã lỗi và thông tin sức khỏe dịch vụ, không nên cấp quyền xem toàn bộ dữ liệu khách hàng. Có thể sử dụng log đã lọc, dữ liệu mẫu hoặc đầu ra chẩn đoán giới hạn khi đáp ứng được mục tiêu công việc.

Chặn tải tệp qua một chức năng của cổng truy cập không chứng minh dữ liệu không thể được sao chép qua kênh khác. Cần xem xét quyền đọc, kênh truyền, công cụ và đường kết nối mà phiên thực sự có.

## 8. Một hợp đồng truy cập có thể kiểm chứng

Trước khi cấp quyền, nên diễn đạt yêu cầu thành dữ liệu cụ thể. Mẫu dưới đây chỉ là **mô hình minh họa**, không phải cấu hình có thể nạp trực tiếp vào sản phẩm PAM.

```yaml
requestId: MAINT-DEMO-104
vendorOrganization: ExampleSupport
namedEngineer: engineer-017
internalSponsor: owner-order-platform
purpose: "Chẩn đoán và khởi động lại order-worker theo thay đổi đã duyệt"
environment: production
targets:
  - order-worker-prod-a
  - order-worker-prod-b
allowedOperations:
  - view_service_health
  - read_approved_diagnostic_logs
  - restart_order_worker
accessWindow:
  maxDurationMinutes: 60
  expiresAutomatically: true
authentication:
  individualIdentity: true
  mfaRequired: true
approval:
  approverRole: production-service-owner
  selfApprovalAllowed: false
session:
  controlledEntryPointRequired: true
  evidenceRequired: true
  terminateAtExpiry: true
completion:
  revokeEntitlement: true
  verifyTargetAccessDenied: true
  reviewCredentialsIssuedDuringSession: true
```

Các điểm cần đọc từ mẫu:

- `namedEngineer` quy trách nhiệm cho một người; tổ chức vendor không thay thế danh tính đó.
- `targets` và `allowedOperations` làm rõ giới hạn tài nguyên và hành động.
- Thời lượng 60 phút là giả định của ví dụ, không phải chuẩn bắt buộc cho mọi nhiệm vụ.
- `selfApprovalAllowed: false` thể hiện phân tách người yêu cầu và người duyệt trong quy trình này.
- `terminateAtExpiry` là hành vi mong muốn cần kiểm chứng bằng cơ chế thực tế. Một cờ trong yêu cầu không đủ để làm phiên tự kết thúc.
- Kiểm tra credential đã cấp giúp phát hiện khả năng truy cập còn tồn tại bên ngoài quyền vừa thu hồi.

Ngoài mẫu, hệ thống triển khai phải có thời điểm bắt đầu/kết thúc xác định, quy tắc xử lý lỗi và người chịu trách nhiệm. Nếu không thể đáp ứng một điều kiện, phải xử lý chênh lệch đó trước khi coi yêu cầu đã được bảo vệ đầy đủ.

## 9. Quy trình vận hành một lượt hỗ trợ vendor

### Bước 1 — Tiếp nhận yêu cầu theo nhiệm vụ

Ghi nhận người thực hiện, mục đích, tài nguyên, môi trường, thao tác dự kiến, cửa sổ thời gian và người bảo trợ. Yêu cầu “mở quyền như lần trước” chưa đủ để xác định phạm vi lần này.

Nếu vendor cần thay đổi thuộc phạm vi ngoài nhiệm vụ hiện tại, ghi nhận thành thay đổi hoặc yêu cầu nâng quyền có thể truy vết. Không mở rộng ngầm vì phiên đã bắt đầu.

### Bước 2 — Đối chiếu quyền cần thiết và phụ thuộc

Xác định quyền tối thiểu đáp ứng từng thao tác. Kiểm tra tài nguyên liên quan như secret, thư mục cấu hình, nhóm đặc quyền hoặc cơ chế triển khai có thể làm tăng quyền hiệu dụng.

Nếu công việc có thể hoàn thành bằng báo cáo chẩn đoán hoặc nhân sự nội bộ thực hiện thao tác cuối, cân nhắc phương án đó. Lựa chọn cần dựa trên khả năng hoàn thành công việc và mức kiểm soát thực tế.

### Bước 3 — Duyệt với thông tin đủ để ra quyết định

Người duyệt cần thấy phạm vi và tác động, không chỉ nút “Approve”. Chủ sở hữu dịch vụ có thể phê duyệt nhu cầu bảo trì; quyền đụng đến nền tảng hoặc dữ liệu ngoài dịch vụ có thể cần chủ sở hữu tương ứng.

Không thiết kế một chuỗi duyệt hình thức mà mọi yêu cầu đều được chấp thuận với cùng quyền rộng. Số lượng người duyệt không thay thế chất lượng thông tin và giới hạn kỹ thuật.

### Bước 4 — Kích hoạt và kiểm tra truy cập

Cấp quyền qua cơ chế được quản lý, xác nhận danh tính và điều kiện truy cập. Kiểm tra vendor vào được đúng đích, làm được thao tác cần thiết và không có quyền ngoài nhiệm vụ theo các phép thử đã chọn.

Cần làm rõ cách kết thúc phiên nếu thao tác kéo dài qua cửa sổ bảo trì. Không để việc hết hạn gây một trạng thái triển khai dở dang mà không có người tiếp nhận, nhưng cũng không gia hạn mặc định vô thời hạn.

### Bước 5 — Thực hiện và theo dõi

Theo dõi sự kiện phù hợp với mức rủi ro: đăng nhập ngoài đích, yêu cầu tăng quyền, tạo danh tính mới, đọc secret không thuộc nhiệm vụ, tắt logging hoặc hoạt động vượt cửa sổ thời gian.

Ghi đủ để liên kết thao tác với thay đổi được duyệt. Nếu hành động vượt phạm vi xuất hiện, cần có người có thẩm quyền tạm dừng phiên và xác minh tình huống theo quy trình của tổ chức.

### Bước 6 — Thu hồi trên các lớp đã cấp

Khi công việc kết thúc, thu hồi quyền kích hoạt, kết thúc phiên theo yêu cầu và xử lý credential đã phát hành. Tùy hệ thống, có thể cần vô hiệu hóa token, xóa khóa hoặc thay credential đã được tiết lộ.

Đối chiếu những thay đổi định danh phát sinh trong phiên, chẳng hạn tài khoản mới hoặc quyền ủy quyền. Không chỉ xử lý tài khoản ban đầu rồi bỏ sót khả năng truy cập được tạo thêm.

### Bước 7 — Xác minh từ hệ thống đích

Thực hiện kiểm tra có kiểm soát để xác nhận khả năng truy cập đã bị từ chối. Đọc bằng chứng thu hồi từ lớp danh tính, PAM và hệ thống đích; kiểm tra phiên đang hoạt động và loại credential có liên quan.

Nếu có độ trễ đồng bộ hoặc cơ chế cache, phải biết thời gian quyền thực sự ngừng có hiệu lực. Trong khoảng đó, trạng thái không nên được ghi là “đã thu hồi hoàn toàn” khi chưa có bằng chứng tương ứng.

### Bước 8 — Đóng nhiệm vụ và lưu bằng chứng

Kết nối yêu cầu, quyết định duyệt, quyền đã cấp, phiên, thay đổi, kiểm tra sức khỏe và xác minh thu hồi. Người sở hữu dịch vụ xác nhận kết quả công việc; người phụ trách truy cập xác nhận vòng đời quyền đã đóng theo phạm vi trách nhiệm.

Đóng ticket hỗ trợ và kết thúc mọi quyền hợp lệ của một vendor là hai việc khác nhau. Một vendor vẫn có hợp đồng hoạt động có thể giữ danh tính đối tác, trong khi quyền production theo từng nhiệm vụ phải hết hạn.

## 10. Kiểm chứng giới hạn bằng các phép thử cụ thể

Kiểm chứng nên diễn ra trong môi trường và cửa sổ được phép. Mục tiêu là xác nhận hàng rào kiểm soát, không mở rộng truy cập để thăm dò ngoài phạm vi.

| Phép thử | Kết quả mong đợi | Bằng chứng cần giữ |
| --- | --- | --- |
| Kỹ sư được duyệt đọc log chẩn đoán của đúng dịch vụ | Cho phép | Danh tính, tài nguyên, quyết định và sự kiện truy cập |
| Cùng kỹ sư truy cập tài nguyên không nằm trong yêu cầu | Từ chối | Sự kiện từ chối và chính sách liên quan |
| Yêu cầu một thao tác quản trị chưa được duyệt | Từ chối hoặc chuyển quy trình nâng quyền | Quyết định và yêu cầu bổ sung nếu có |
| Bắt đầu một phiên mới sau thời hạn | Từ chối | Thời điểm hết hạn và kiểm tra đăng nhập |
| Giữ phiên qua thời hạn | Hành vi đúng chính sách đã chọn, có giới hạn rõ ràng | Sự kiện kết thúc hoặc bằng chứng cơ chế thời hạn phiên |
| Dùng lại credential đã cấp sau khi thu hồi | Bị từ chối sau mốc thu hồi đã xác định | Kết quả xác minh ở hệ thống đích |
| Kỹ sư chưa được tiếp nhận dùng quyền của tổ chức vendor | Từ chối | Danh sách người được chấp thuận và sự kiện từ chối |
| Đi theo đường trực tiếp ngoài điểm truy cập được quản lý | Bị chặn theo thiết kế | Kiểm tra đường truy cập và sự kiện liên quan |

Một phép thử đạt chỉ chứng minh điều kiện đã thử tại thời điểm đó. Cần chọn các phép thử đại diện cho loại quyền, giao thức, hệ thống và đường truy cập thực tế. Sau thay đổi lớn về vai trò hoặc tích hợp, các giả định liên quan cần được kiểm chứng lại.

Với thu hồi, đặc biệt lưu ý sự khác nhau giữa token truy cập, khả năng xin token mới và phiên tại ứng dụng. Vô hiệu hóa một cơ chế không nhất thiết vô hiệu hóa ngay những cơ chế còn lại.

## 11. Giám sát và bằng chứng phục vụ điều tra

### 11.1. Liên kết sự kiện theo một lượt truy cập

Một chuỗi bằng chứng hữu ích có thể gồm:

```text
Yêu cầu bảo trì
    → danh tính kỹ sư đã xác thực
    → quyết định phê duyệt
    → quyền được kích hoạt
    → phiên vào đúng tài nguyên
    → thao tác và thay đổi liên quan
    → kết thúc phiên / thu hồi quyền
    → xác minh hệ thống đích từ chối truy cập
```

Mỗi nguồn log có thể dùng định dạng khác nhau. Cần giữ các định danh đủ để đối chiếu, cùng thời gian được quản lý nhất quán. Nếu thiếu ánh xạ từ tài khoản đích sang người dùng cá nhân, bản ghi dài vẫn không trả lời chắc chắn ai đã thực hiện.

### 11.2. Ví dụ sự kiện tổng hợp

Ví dụ sau biểu diễn dữ liệu minh họa, không phải schema của một công cụ cụ thể:

```json
{
  "eventType": "vendor_access_closed",
  "requestId": "MAINT-DEMO-104",
  "engineerId": "engineer-017",
  "vendorOrganization": "ExampleSupport",
  "sessionId": "session-demo-830",
  "target": "order-worker-prod-a",
  "entitlementRevoked": true,
  "sessionTerminationConfirmed": true,
  "targetReentryTest": "DENIED",
  "evidenceReference": "evidence-demo-104"
}
```

Các trường xác nhận phải được tạo từ kiểm tra và sự kiện thực tế. Việc hệ thống ghi `entitlementRevoked: true` không thay thế kiểm tra ở tài nguyên đích. Không đưa mật khẩu, token hay dữ liệu khách hàng vào sự kiện minh họa hoặc log vận hành.

### 11.3. Những tín hiệu nên điều tra

- Một danh tính vendor đăng nhập tài nguyên không liên quan đến yêu cầu.
- Có thao tác sau thời điểm quyền hoặc phiên lẽ ra phải kết thúc.
- Vendor tạo tài khoản, khóa hoặc cơ chế ủy quyền chưa được duyệt.
- Quyền được gia hạn lặp lại đến mức trở thành thường trực trên thực tế.
- Không có phiên trên PAM nhưng hệ thống đích vẫn ghi nhận truy cập bằng tài khoản dành cho vendor.
- Log quản trị bị ngắt trong lúc có hoạt động đặc quyền.

Mỗi tín hiệu cần có người tiếp nhận và hành động tương ứng. Cảnh báo chỉ được lưu mà không có người xử lý không tạo ra khả năng kiểm soát đầy đủ.

## 12. Xử lý khi phát hiện vendor đang có quyền quá rộng

Không nên chỉ xóa một nhóm rồi coi công việc đã kết thúc. Trước tiên cần biết quyền nào đang tồn tại, ai đang sử dụng và việc thu hồi có ảnh hưởng hệ thống đang chạy hay không.

Một trình tự thực tế:

1. Xác định chủ sở hữu nội bộ và phạm vi hệ thống liên quan.
2. Kiểm kê danh tính, nhóm, tài khoản đích, khóa, token, quyền ủy quyền và phiên vendor đang dùng.
3. Phân biệt quyền hỗ trợ của con người với danh tính dịch vụ đang được ứng dụng sử dụng.
4. Đối chiếu nhu cầu hiện tại với quyền hiệu dụng; xác định các quyền dư và đường bỏ qua kiểm soát.
5. Chọn biện pháp giảm quyền, chuyển thao tác và thay credential theo kế hoạch có thể thực hiện được.
6. Thu hồi hoặc thu hẹp, rồi kiểm tra lại khả năng vận hành hợp lệ và các truy cập cần bị chặn.
7. Lưu bằng chứng kết quả, giao chủ sở hữu cho các phần chưa xử lý và đặt thời hạn cụ thể.

Nếu có dấu hiệu tài khoản bị sử dụng trái phép, áp dụng quy trình ứng phó sự cố của tổ chức. Khi đó cần phối hợp chặn truy cập, bảo toàn bằng chứng và duy trì dịch vụ theo mức độ rủi ro; không chờ một đợt rà soát định kỳ mới xử lý.

Với hệ thống cũ chưa hỗ trợ phân quyền chi tiết, có thể cần biện pháp bù như giới hạn đích, cửa sổ ngắn, phiên có người giám sát hoặc để nhân sự nội bộ thực hiện thao tác đặc quyền. Cần ghi rõ phần quyền còn rộng và kế hoạch cải thiện. Không gọi biện pháp bù là tương đương hoàn toàn với giới hạn quyền ở hệ thống đích.

## 13. Ngoại lệ và hỗ trợ khẩn cấp

Có công việc đòi hỏi quyền rất cao, chẳng hạn khôi phục một thành phần hỏng hoặc cập nhật nền tảng không hỗ trợ vai trò hẹp. Quyền cao không đồng nghĩa bắt buộc phải trở thành quyền không giới hạn.

Một ngoại lệ hợp lý cần xác định:

- Lý do các quyền thông thường không đáp ứng nhiệm vụ.
- Tài nguyên và loại hành động phải mở rộng.
- Người quyết định, người chịu trách nhiệm và người trực theo dõi.
- Thời hạn và điều kiện chấm dứt hoặc gia hạn.
- Cách kiểm soát phiên, credential và bằng chứng.
- Phương án xử lý nếu công việc chưa xong khi quyền hết hạn.
- Cách kiểm chứng truy cập kết thúc và rà soát sau nhiệm vụ.

Break-glass là cơ chế truy cập khẩn cấp được chuẩn bị cho tình huống đặc biệt. Nó không nên trở thành tài khoản hỗ trợ thường ngày của vendor. Nếu cơ chế xác thực hoặc phê duyệt bình thường gặp sự cố, đường khẩn cấp vẫn cần có chủ sở hữu, bằng chứng và quy trình phục hồi kiểm soát sau khi sử dụng.

Khi cần gia hạn, quyết định mới phải dựa trên công việc còn lại. Gia hạn tự động không có giới hạn tổng thể có thể tái tạo quyền thường trực dưới tên “tạm thời”.

## 14. Những cách sửa chỉ làm thay đổi bề ngoài

| Cách làm | Khoảng trống còn lại | Hướng xử lý |
| --- | --- | --- |
| Bật MFA cho tài khoản quản trị rộng | Đăng nhập chắc hơn nhưng quyền vẫn quá lớn | Giới hạn tài nguyên và hành động, kết hợp thời hạn |
| Đưa mật khẩu admin vào vault | Tài khoản đích vẫn có quyền rộng, có thể còn đường dùng trực tiếp | Kiểm soát môi giới, quyền đích và đường truy cập |
| Ghi hình mọi phiên | Có bằng chứng nhưng hành động sai vẫn có thể xảy ra | Kết hợp giới hạn quyền và cơ chế phản ứng |
| Chỉ mở VPN trong giờ làm việc | VPN không mô tả thao tác được phép, phiên khác có thể còn | Phân quyền đích và quản lý thời hạn thực tế |
| Tạo tài khoản riêng cho vendor | Vẫn không phân biệt từng kỹ sư nếu dùng chung | Danh tính cá nhân và ánh xạ đến tài khoản đích |
| Xóa quyền trên cổng đối tác | Token, khóa, phiên hoặc tài khoản phụ có thể tồn tại | Thu hồi theo các lớp đã cấp và kiểm chứng tại đích |
| Yêu cầu nhiều cấp duyệt | Mọi cấp vẫn có thể duyệt cùng một quyền quá rộng | Cung cấp phạm vi cụ thể và lựa chọn ít quyền khả thi |
| Tự động cấp lại quyền sau mỗi lần hết hạn | Quyền tồn tại gần như liên tục | Đánh giá nhu cầu từng lượt, kiểm soát gia hạn và tổng thời lượng |

Các biện pháp như MFA, vault và ghi phiên vẫn hữu ích. Sai lầm là xem một biện pháp riêng lẻ như bằng chứng đủ cho toàn bộ vòng đời truy cập.

## 15. Đo hiệu quả mà không tự đánh lừa mình

Một vài chỉ số có thể giúp theo dõi quá trình cải thiện:

- Tỷ lệ danh tính vendor có người bảo trợ và ngày rà soát hoặc hết hạn hợp lệ.
- Tỷ lệ lượt truy cập production gắn với yêu cầu và danh tính cá nhân.
- Số quyền vendor thường trực, chia theo mức đặc quyền và môi trường.
- Tỷ lệ yêu cầu hoàn thành mà không cần quyền quản trị tổng quát.
- Thời gian từ yêu cầu thu hồi đến khi truy cập thực tế bị chặn ở đích.
- Số lượt hết hạn vẫn còn phiên hoặc credential sử dụng được.
- Số ngoại lệ quá hạn, quyền được gia hạn lặp lại và đường truy cập ngoài kiểm soát.

Mỗi chỉ số cần có mẫu số, phạm vi và nguồn dữ liệu rõ ràng. “100% vendor đi qua PAM” có thể chỉ đúng với một loại giao thức được đo, trong khi API hoặc khóa SSH chưa nằm trong kiểm kê.

Thời gian xử lý yêu cầu cũng cần theo dõi để bảo đảm quy trình hỗ trợ dùng được. Nếu người vận hành phải đi vòng để hoàn thành nhiệm vụ, cần cải thiện quy trình, khả năng phân quyền hoặc công cụ. Không nên dùng việc rút ngắn thời gian bằng cách cấp quyền rộng thường trực làm thước đo thành công duy nhất.

## 16. Bài tập tự kiểm tra

### Tình huống

Một vendor cần điều tra lỗi hàng đợi trên hai máy production trong hai giờ. Hiện tại họ có một tài khoản dùng chung với quyền quản trị toàn bộ mười máy. Tài khoản này cũng đang được một job thu thập log sử dụng. PAM đã ghi phiên nhưng vendor vẫn biết mật khẩu để đăng nhập trực tiếp.

Hãy trả lời:

1. Những chiều nào đang vượt phạm vi nhiệm vụ?
2. Vì sao chưa thể chỉ đổi mật khẩu rồi đóng yêu cầu?
3. Cần tách danh tính và quyền như thế nào?
4. Những bằng chứng nào chứng minh công việc đã hoàn tất và truy cập đã kết thúc?
5. Nếu nền tảng chưa hỗ trợ vai trò thao tác hẹp, nên ghi nhận và xử lý khoảng trống ra sao?

### Gợi ý phân tích

Phạm vi tài nguyên là hai máy nhưng quyền hiện có phủ mười máy; quyền quản trị tổng quát có thể vượt nhu cầu chẩn đoán; tài khoản dùng chung làm mất quy trách nhiệm cá nhân; mật khẩu đã biết mở đường bỏ qua PAM. Nếu không có thời hạn và kiểm tra thu hồi, quyền còn tiếp tục sau hai giờ.

Job thu thập log là một phụ thuộc cần kiểm kê. Đổi mật khẩu đột ngột có thể làm job ngừng hoạt động, nhưng phụ thuộc đó không phải lý do để tiếp tục dùng chung danh tính giữa con người và dịch vụ. Cần tách job sang danh tính dịch vụ riêng với quyền phù hợp, còn kỹ sư dùng danh tính cá nhân và quyền theo nhiệm vụ.

Thiết kế sửa nên giới hạn đúng hai máy, cấp khả năng chẩn đoán cần thiết trong cửa sổ đã duyệt, kiểm soát đường trực tiếp và có kế hoạch cho thao tác phát sinh. Nếu phải dùng quyền cao, ghi nhận ngoại lệ cụ thể cùng kiểm soát bù và thời hạn.

Bằng chứng cần liên kết người thực hiện, yêu cầu, phê duyệt, phiên, kết quả chẩn đoán và thay đổi. Khi kết thúc, xác nhận các quyền đã kích hoạt bị thu hồi, phiên được xử lý theo chính sách, credential liên quan đã được vô hiệu hóa hoặc thay thế khi cần và truy cập tại đích bị từ chối sau mốc thu hồi xác định.

## 17. Các điểm cần ghi nhớ

Vendor cần đủ quyền để hoàn thành công việc, nhưng quyền đó phải được diễn đạt thành giới hạn có thể thực thi và kiểm chứng. Đánh giá theo cá nhân, tài nguyên, hành động, thời gian, đường truy cập và dữ liệu giúp phát hiện những khoảng trống bị che khuất bởi nhãn “tài khoản hỗ trợ”.

Least privilege giới hạn quyền, JIT giới hạn thời gian và JEA giới hạn khả năng quản trị theo nhiệm vụ. Vault, MFA, phân đoạn mạng và quản lý phiên hỗ trợ thiết kế này khi được phối hợp với phân quyền ở tài nguyên đích.

Vòng đời truy cập chỉ đóng khi có bằng chứng các khả năng đã cấp thực sự kết thúc trong phạm vi đã xác định. Một ticket đã đóng, tài khoản bị khóa trên cổng hoặc bản ghi phiên đã lưu riêng lẻ chưa đủ chứng minh điều đó.
