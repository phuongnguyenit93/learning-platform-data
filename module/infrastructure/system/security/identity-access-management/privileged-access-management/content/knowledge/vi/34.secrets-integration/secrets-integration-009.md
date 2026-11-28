# Không ghi secret vào ticket

## 1. Ticket lưu yêu cầu và bằng chứng, vault bảo vệ secret

Trong quy trình quản lý truy cập đặc quyền (PAM), ticket thường ghi nhận lý do cần quyền, tài nguyên đích, người phê duyệt và kết quả thực hiện. Secret là dữ liệu có thể dùng để xác thực hoặc khôi phục khả năng truy cập, chẳng hạn mật khẩu quản trị, private key, API token, refresh token, mã khôi phục hoặc một URL chứa thông tin xác thực.

Nguyên tắc của bài học này là: **ticket tham chiếu đến quy trình cấp quyền và bằng chứng sử dụng quyền; giá trị secret được giữ trong hệ thống quản lý secret có kiểm soát**. Người phê duyệt không cần biết mật khẩu để quyết định có cho phép một thao tác bảo trì hay không. Người kiểm toán cũng không cần thấy token để xác minh thao tác đã được phê duyệt, thực hiện và kết thúc đúng hạn.

Ví dụ, kỹ sư cần khởi động lại một dịch vụ sản xuất. Ticket có thể chứa mã tài sản, thao tác được phép, cửa sổ bảo trì, vai trò JIT/JEA và mã phiên PAM. Không cần dán mật khẩu của tài khoản quản trị vào phần mô tả hoặc bình luận để đồng nghiệp “tiện đăng nhập”.

Đây là một phần của tích hợp secrets: hệ thống ticket quản lý công việc; PAM quản lý việc nâng quyền và phiên; vault hoặc secrets manager quản lý credential. Ba hệ thống có thể liên kết qua mã tham chiếu và sự kiện kiểm toán, nhưng không vì tích hợp mà sao chép secret sang mọi hệ thống.

## 2. Vì sao ticket là nơi dễ làm secret lan rộng?

Ticket không chỉ là một trang mà người tạo đang nhìn thấy. Tùy cách triển khai, nội dung có thể được đưa vào thông báo email, ứng dụng chat, chỉ mục tìm kiếm, webhook, công cụ báo cáo, file xuất, hệ thống phân tích và bản sao lưu. Một bình luận chứa secret có thể đã được phát tán trước khi người tạo kịp chỉnh sửa.

Các nhóm có quyền đọc ticket cũng có thể rộng hơn nhóm được phép dùng credential. Người theo dõi thay đổi, nhóm hỗ trợ nhà cung cấp hoặc người quản lý dự án có lý do đọc tình trạng công việc, nhưng không nhất thiết có quyền truy cập máy chủ sản xuất.

Việc đặt secret trong ticket làm hỏng nhiều kiểm soát PAM:

- **Least privilege:** quyền xem tiến độ trở thành quyền biết credential.
- **JIT:** secret còn trong ticket sau khi cửa sổ nâng quyền đã hết.
- **Truy vết cá nhân:** nhiều người có thể sao chép một credential chung, khiến việc quy trách nhiệm khó hơn.
- **Thu hồi:** đóng ticket hoặc bỏ người theo dõi không làm mất hiệu lực những bản secret đã được sao chép.
- **Luân chuyển:** một credential cũ xuất hiện trong lịch sử trao đổi có thể bị nhầm là credential đang được phê duyệt.

Ẩn ticket khỏi giao diện công khai không biến nó thành vault. Ticket nội bộ, ticket riêng tư và ghi chú chỉ dành cho nhân viên hỗ trợ vẫn cần tuân theo nguyên tắc này.

## 3. Nhận diện secret và dữ liệu tham chiếu

Không chỉ trường mang tên `password` mới là secret. Trước khi gửi nội dung, hãy hỏi: “Nếu người không có quyền nhận được giá trị này, họ có thể đăng nhập, giả mạo, khôi phục tài khoản hoặc đổi lấy quyền truy cập không?” Nếu có, giá trị đó phải được xử lý như secret.

| Dữ liệu dự định đưa vào ticket | Cách xử lý |
| --- | --- |
| Mật khẩu quản trị, service account password | Không đưa giá trị vào ticket; cấp quyền qua vault/PAM |
| Private key, passphrase, client secret | Không đính kèm file hoặc dán nội dung; quản lý trong kho secret |
| Access token, session cookie, refresh token, mã khôi phục | Không ghi vào ticket; tránh cả header hoặc URL chứa các giá trị này |
| Signed URL hoặc link một lần mà người giữ link có thể truy cập | Xử lý như thông tin cấp quyền trong thời gian còn hiệu lực; không dùng làm liên kết ticket thông thường |
| Mã ticket, mã yêu cầu cấp quyền, mã phiên PAM | Có thể dùng để liên kết bằng chứng nếu bản thân mã không cho phép xác thực hoặc truy cập dữ liệu |
| Mã định danh credential hoặc đường dẫn logic trong vault | Chỉ đưa vào khi chính sách phân loại cho phép; dùng mã gián tiếp nếu tên đường dẫn làm lộ kiến trúc nhạy cảm |
| Thời điểm cấp/thu hồi, vai trò được cấp, kết quả thao tác | Là dữ liệu quy trình, vẫn phải giới hạn người đọc phù hợp |

Một URL đến giao diện vault chỉ phù hợp nếu người mở vẫn phải xác thực và được kiểm tra quyền độc lập. Nếu URL chứa token truy cập trong query string hoặc là bearer link, nó cũng mang giá trị cấp quyền và không phải tham chiếu an toàn.

Tên tài khoản, hostname và đường dẫn vault không nhất thiết là secret, nhưng có thể là thông tin nhạy cảm. Không đưa chúng vào ticket rộng quyền chỉ vì chúng không phải mật khẩu. Có thể dùng `asset-id` và `credential-ref` để bộ phận được phép tra cứu trong hệ thống chuyên trách.

## 4. Thiết kế luồng ticket → PAM → vault

Luồng cấp quyền cần kiểm tra quyền tại hệ thống PAM/vault, thay vì coi một nội dung được dán vào ticket là bằng chứng đủ để lấy secret.

```mermaid
sequenceDiagram
    participant U as Người thực hiện
    participant T as Hệ thống ticket
    participant A as Người phê duyệt
    participant P as PAM
    participant V as Vault
    participant R as Tài nguyên đích
    U->>T: Tạo yêu cầu, phạm vi và thời gian
    A->>T: Phê duyệt yêu cầu
    U->>P: Xin quyền kèm mã ticket
    P->>T: Kiểm tra trạng thái và phạm vi được duyệt
    P->>P: Xác thực người dùng và kiểm tra chính sách
    P->>V: Lấy credential theo danh tính dịch vụ được cấp quyền
    V-->>P: Credential trong kênh được bảo vệ
    P->>R: Thiết lập phiên/thao tác đã giới hạn
    P-->>T: Mã phiên, thời hạn và kết quả; không có secret
```

Sơ đồ thể hiện một phương án broker phiên, không phải giả định rằng mọi sản phẩm đều hỗ trợ cùng một giao thức. Với phương án này, người thực hiện có thể thao tác qua PAM mà không thấy credential gốc. Nếu ứng dụng cần lấy secret trực tiếp, ứng dụng dùng danh tính workload và quyền truy cập vault được cấp riêng; ticket không đóng vai trò vận chuyển secret.

Ở phương án checkout cho con người, chỉ người được cấp quyền mới lấy credential từ vault trong thời hạn cho phép. Họ không được chuyển tiếp credential qua ticket sau khi lấy. Khi kết thúc, quy trình thực hiện check-in, thu hồi hoặc luân chuyển theo chính sách và khả năng của hệ thống đích.

Các ràng buộc cần được kiểm tra ở phía hệ thống:

1. Người xin quyền khớp với người hoặc nhóm đã được phê duyệt.
2. Tài nguyên, môi trường và thao tác khớp phạm vi ticket.
3. Yêu cầu chưa bị hủy và vẫn trong cửa sổ thời gian cho phép.
4. Danh tính dùng để gọi vault chỉ có quyền cần thiết cho luồng tích hợp.
5. Phản hồi về ticket chỉ chứa các trường đã được cho phép; không chép nguyên phản hồi từ vault.

Không nhận một chuỗi tự khai như `approved=true` từ người gửi rồi cấp quyền. Tích hợp phải xác minh trạng thái từ nguồn có thẩm quyền; các sự kiện webhook cần được xác thực theo cơ chế mà nền tảng hỗ trợ, đồng thời đối chiếu phạm vi trước khi thực hiện hành động đặc quyền.

## 5. Mẫu ticket an toàn

Một ticket tốt trả lời được ai, cần làm gì, ở đâu, trong bao lâu, ai duyệt và bằng chứng nằm ở đâu. Ví dụ dưới đây là mẫu dữ liệu minh họa, không phải cấu hình của một sản phẩm cụ thể:

```yaml
request_id: CHG-DEMO-024
purpose: Khởi động lại dịch vụ xử lý báo cáo sau cập nhật cấu hình
environment: production
asset_ref: ASSET-DEMO-017
requester_ref: USER-DEMO-042
access:
  pam_role: report-service-restart
  allowed_actions:
    - restart-report-service
    - read-service-health
  duration_minutes: 30
  credential_ref: CRED-DEMO-008
approval:
  change_approval_ref: APR-DEMO-051
  access_approval_ref: APR-DEMO-052
evidence:
  pam_session_ref: SESSION-DEMO-063
  validation_result: Dịch vụ hoạt động và health check đạt yêu cầu
  access_end_result: Quyền JIT đã kết thúc
```

Các mã trong ví dụ chỉ phục vụ tra cứu và không có khả năng xác thực. Khi áp dụng thực tế, tổ chức phải đánh giá độ nhạy cảm của từng trường và giới hạn người xem. Không thêm trường `password`, `token`, `private_key` hoặc `vault_response` để hỗ trợ xử lý nhanh.

Trạng thái hoàn tất nên phản ánh bằng chứng thực tế. Nếu quyền JIT đã hết nhưng phiên vẫn mở, hoặc check-in đã thực hiện nhưng chưa xác nhận luân chuyển, không ghi chung là “đã thu hồi toàn bộ”. Có thể ghi rõ kết quả từng phần và mã sự kiện để người có quyền kiểm tra.

Một bình luận hỗ trợ cũng có thể ngắn gọn mà đầy đủ:

> Yêu cầu truy cập đã được duyệt theo APR-DEMO-052. Người thực hiện mở PAM và yêu cầu vai trò report-service-restart với mã CHG-DEMO-024. Cửa sổ truy cập là 30 phút. Sau thao tác, ghi mã phiên và kết quả kiểm tra dịch vụ vào ticket. Không gửi credential qua bình luận hoặc file đính kèm.

## 6. Những đường rò rỉ thường bị bỏ sót

### 6.1. Log và lệnh chẩn đoán

Output gỡ lỗi có thể chứa header `Authorization`, cookie, chuỗi kết nối, biến môi trường hoặc request body. Dán toàn bộ output vào ticket rồi mới tìm cách che dữ liệu làm tăng nguy cơ phát tán. Hãy chọn phần cần thiết, loại bỏ các trường nhạy cảm và xem lại bản đã làm sạch trước khi tải lên.

Ví dụ nội dung chẩn đoán nên thể hiện cấu trúc thay vì giá trị:

```text
request_id: REQ-DEMO-076
method: POST
endpoint: /internal/report/restart
authorization: [REDACTED]
response_status: 403
reason: Vai trò hiện tại không có quyền restart-report-service
```

Không đính kèm bản gốc chứa token cạnh bản đã làm sạch. Với chuỗi kết nối, nên đưa riêng tên loại kết nối, mã endpoint và lỗi cần phân tích; tránh giữ credential trong một URI rồi chỉ che phần dễ nhìn thấy.

### 6.2. Ảnh chụp, video và file nén

Ảnh màn hình có thể chụp cả ô secret đang mở, clipboard manager hoặc token trên thanh địa chỉ. File nén có thể chứa `.env`, cấu hình có credential hoặc dump không được kiểm tra. Video ghi lại phiên làm việc cũng có thể thu được secret nếu người dùng từng hiển thị nó.

Ưu tiên tái hiện lỗi trong môi trường thử nghiệm với dữ liệu giả, hoặc chụp lại màn hình sau khi đã loại bỏ dữ liệu nhạy cảm. Nếu bắt buộc xử lý ảnh, cần làm sạch bằng cách không thể khôi phục trong bản xuất và xác minh chính file sẽ gửi. Che bằng một lớp có thể gỡ bỏ hoặc chỉ cắt giao diện hiển thị không bảo đảm dữ liệu gốc đã biến mất khỏi file.

### 6.3. Tích hợp tự động

Một connector có thể vô tình đưa secret vào ticket khi ghi nguyên response body, exception hoặc context của job. Thiết kế phản hồi theo danh sách trường được phép thường dễ kiểm soát hơn việc gửi mọi trường rồi cố tìm từ khóa nhạy cảm để xóa.

Ví dụ phản hồi của connector có thể chỉ gồm:

```json
{
  "requestRef": "CHG-DEMO-024",
  "accessRequestRef": "ACCESS-DEMO-091",
  "state": "APPROVED",
  "sessionRef": "SESSION-DEMO-063",
  "credentialDeliveredToTicket": false
}
```

Trường cuối chỉ mô tả hợp đồng của ví dụ, không tự chứng minh hệ thống an toàn. Cần kiểm tra cả đường lỗi: timeout, retry, lỗi xác thực và lỗi parse dữ liệu cũng không được làm log hoặc bình luận chứa secret. Không đưa token của connector vào ticket để nhóm khác “test hộ”.

## 7. Khi người hỗ trợ yêu cầu gửi credential

Yêu cầu hỗ trợ hợp lệ không đồng nghĩa với việc mọi người tham gia ticket đều được phép nhận secret. Người xử lý có thể cần thông tin cấu hình đã làm sạch, mã lỗi, khoảng thời gian, mã phiên hoặc quyền truy cập được cấp riêng.

Thực hiện theo thứ tự sau:

1. Làm rõ thao tác cần hỗ trợ và bằng chứng thực sự cần thiết.
2. Gửi dữ liệu đã loại bỏ secret hoặc cung cấp bằng chứng qua hệ thống có quyền đọc phù hợp.
3. Nếu cần truy cập trực tiếp, tạo yêu cầu cấp quyền cho đúng người, đúng tài nguyên và thời hạn; dùng PAM hoặc cơ chế truy cập được tổ chức phê duyệt.
4. Nếu việc chia sẻ secret là yêu cầu không tránh được của một quy trình đã được phê duyệt, dùng cơ chế chuyển giao secret chuyên dụng với kiểm soát người nhận, thời hạn và kiểm toán. Ticket chỉ ghi mã tham chiếu của việc chuyển giao.

Không chuyển secret sang email hoặc chat chỉ để tránh ghi trong ticket. Đây vẫn là việc phát tán credential sang nơi không có cùng kiểm soát. Một file mã hóa đính kèm ticket cũng không tự giải quyết vấn đề nếu mật khẩu giải mã được gửi trong cùng luồng hoặc quyền giải mã rộng hơn quyền sử dụng credential.

Trường hợp break-glass vẫn phải lấy credential qua kênh khẩn cấp đã được chuẩn bị. Ticket có thể được bổ sung bằng chứng sau theo quy trình ứng phó, nhưng không trở thành nơi lưu mật khẩu khẩn cấp.

## 8. Nếu secret đã bị dán nhầm vào ticket

Chỉnh sửa bình luận là bước hạn chế phát tán tiếp, không phải bằng chứng secret chưa bị lộ. Xử lý sự cố phải xem xét cả giá trị credential, nơi đã nhận nội dung và các hoạt động sau thời điểm phát tán.

### Bước 1 — Hạn chế tiếp tục lan truyền

Thông báo qua kênh ứng phó được chỉ định, hạn chế quyền đọc ticket nếu được phép và ngăn thông báo/tích hợp tiếp tục phân phối dữ liệu khi khả thi. Không trả lời bằng cách trích dẫn lại đoạn chứa secret. Ghi nhận mã ticket, mã bình luận hoặc attachment và thời điểm, thay vì sao chép giá trị secret sang một ticket sự cố khác.

### Bước 2 — Thu hồi hoặc luân chuyển tại nguồn

Xác định loại credential và chủ sở hữu để chọn biện pháp phù hợp:

| Loại dữ liệu bị lộ | Việc cần phối hợp thực hiện |
| --- | --- |
| Access token hoặc session cookie | Thu hồi token/phiên theo khả năng hệ thống; xác minh phiên còn hiệu lực nào cần chấm dứt |
| Mật khẩu service account | Luân chuyển có kiểm soát, cập nhật bên sử dụng và xác nhận credential cũ hết hiệu lực |
| Private key | Thay khóa, gỡ quyền tin cậy đối với public key tương ứng ở các đích liên quan |
| Client secret hoặc API key | Tạo giá trị thay thế, chuyển bên sử dụng và vô hiệu hóa giá trị cũ theo mức độ khẩn cấp |
| Mã khôi phục | Hủy hoặc cấp lại bộ mã theo khả năng của hệ thống |

Không giả định đổi mật khẩu sẽ kết thúc mọi phiên hoặc token đã cấp trước đó. Kiểm tra cơ chế của hệ thống đích và thực hiện thu hồi phiên riêng khi cần. Với service account, phối hợp để giảm gián đoạn; nếu có dấu hiệu bị khai thác, mức độ khẩn cấp có thể yêu cầu vô hiệu hóa ngay theo quyết định của nhóm ứng phó.

### Bước 3 — Làm sạch nơi lưu và các bản đã phân phối

Phối hợp quản trị hệ thống ticket để xử lý nội dung, attachment và lịch sử theo quyền hạn, tính năng của nền tảng và yêu cầu lưu giữ. Kiểm tra email, chat, webhook, file xuất hoặc hệ thống bên nhận đã liên quan. Không khẳng định “đã xóa mọi bản sao” nếu chưa có bằng chứng; bản sao lưu và lịch sử bất biến có thể cần được bảo vệ, giới hạn truy cập và xử lý theo chính sách lưu giữ.

### Bước 4 — Điều tra và lưu bằng chứng không chứa secret

Rà soát quyền đọc, người nhận thông báo, sự kiện truy cập ticket, audit vault/PAM và log hệ thống đích trong khoảng thời gian liên quan. Đối chiếu lần sử dụng credential với danh tính, phiên và phạm vi được phép. Không có log đọc ticket không đồng nghĩa với không có người xem hoặc không có bản sao.

Ticket sự cố nên ghi thời điểm phát hiện, mã credential, biện pháp thu hồi/luân chuyển, thời điểm giá trị cũ hết hiệu lực, phạm vi kiểm tra và kết luận có căn cứ. Nếu cần giữ chứng cứ gốc có secret, lưu trong kho bằng chứng được kiểm soát theo quy trình ứng phó, không đính kèm lại vào ticket thông thường.

### Bước 5 — Sửa điểm gây phát tán

Xác định nguyên nhân: mẫu ticket yêu cầu mật khẩu, connector trả toàn bộ response, log debug có header hay thao tác thủ công. Sửa đúng điểm đó và kiểm tra lại bằng dữ liệu giả. Việc chỉ nhắc người dùng cẩn thận hơn không khắc phục được một tích hợp tự động vẫn ghi secret ở đường lỗi.

## 9. Kiểm chứng quy trình bằng dữ liệu giả

Không dùng credential đang hoạt động để thử xem bộ lọc có chặn hay không. Trong môi trường thử nghiệm, dùng các chuỗi giả đã biết và kiểm tra cả mô tả, bình luận, attachment, notification và payload tích hợp.

Các tình huống thử cần gắn với hành vi mong đợi:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Tạo yêu cầu truy cập mới | Ticket chỉ chứa phạm vi, thời hạn, phê duyệt và mã tham chiếu |
| Mở liên kết đến PAM/vault khi chưa có quyền | Hệ thống vẫn yêu cầu xác thực và kiểm tra quyền; mã ticket không tự cấp truy cập |
| Ticket được duyệt nhưng đã hết cửa sổ | PAM từ chối cấp quyền mới theo chính sách thời gian |
| Connector lỗi khi nhận payload có chuỗi giả giống secret | Ticket và log vận hành không hiển thị giá trị giả đó |
| Gửi output chẩn đoán đã làm sạch | Chỉ phần cần phân tích còn lại; không kèm bản gốc chứa dữ liệu nhạy cảm |
| Kết thúc công việc | Có bằng chứng quyền/phiên đã kết thúc và kết quả xử lý credential phù hợp |

Secret scanning có thể hỗ trợ phát hiện một số mẫu, nhưng không nhận diện được mọi mật khẩu, khóa tự đặt hoặc secret nằm trong ảnh. Bộ lọc là một lớp bảo vệ bổ sung; thiết kế ticket và hợp đồng tích hợp vẫn phải tránh nhận secret ngay từ đầu. Khi phát hiện, thông báo cũng không nên lặp lại toàn bộ giá trị vừa bị phát hiện.

## 10. Tình huống thực hành

Nhóm vận hành nhận ticket báo dịch vụ không kết nối được cơ sở dữ liệu. Một thành viên đề nghị gửi file cấu hình thực tế và mật khẩu service account để kiểm tra nhanh.

Cách xử lý phù hợp là cung cấp lỗi đã làm sạch, mã tài sản và mã cấu hình; giữ credential trong vault. Người cần chẩn đoán được cấp vai trò phù hợp trong thời gian giới hạn, qua PAM hoặc danh tính workload được phê duyệt. Nếu cần thay secret, ticket liên kết tới yêu cầu luân chuyển và ghi lại kết quả kiểm tra kết nối; không ghi giá trị cũ hoặc mới.

Nếu file cấu hình chứa mật khẩu đã được đính kèm trước đó, việc gỡ file chỉ là một phần xử lý. Nhóm còn phải đánh giá phạm vi phân phối, luân chuyển credential, cập nhật bên sử dụng, xác nhận giá trị cũ không còn dùng được và xem xét hoạt động trong khoảng thời gian bị lộ.

Sau bài thực hành, người học cần giải thích được ba điều: tại sao quyền xem ticket không đồng nghĩa quyền biết credential; thông tin nào đủ để phê duyệt và kiểm toán mà không lộ secret; và vì sao chỉnh sửa ticket không thay thế việc thu hồi hoặc luân chuyển credential đã phát tán.
