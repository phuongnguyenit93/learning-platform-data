# Workflow state transition — Đặc tả chuyển trạng thái nghiệp vụ an toàn

## 1. Mục tiêu bảo mật của chuyển trạng thái

**Workflow state transition** là việc một đối tượng nghiệp vụ chuyển từ trạng thái hiện tại sang trạng thái khác khi một hành động hoặc sự kiện đáp ứng các điều kiện đã quy định.

Ví dụ, một yêu cầu chi tiền đi từ bản nháp tới gửi duyệt, được phê duyệt, thực thi và hoàn tất. Mỗi bước đại diện cho các điều kiện nghiệp vụ khác nhau. Nếu hệ thống cho phép bỏ qua bước duyệt, sử dụng một phê duyệt cho nội dung đã sửa hoặc thực thi lại một yêu cầu, kiểm tra đăng nhập ở endpoint vẫn chưa đủ bảo vệ quy trình.

Trong module đặc tả yêu cầu bảo mật, mục tiêu là chuyển các rủi ro này thành yêu cầu cụ thể: ai được làm gì, từ trạng thái nào, trên dữ liệu nào, với bằng chứng nào và kết quả nào được chấp nhận.

Sau bài học, người đọc có thể:

- Xác định trạng thái, hành động, điều kiện bảo vệ và bất biến nghiệp vụ.
- Viết ma trận chuyển trạng thái có quyền, điều kiện dữ liệu và hiệu ứng rõ ràng.
- Đặc tả xử lý yêu cầu đồng thời, gửi lại và sự kiện bất đồng bộ.
- Liên kết yêu cầu với mô hình đe dọa, quyết định kiến trúc và tiêu chí nghiệm thu.

Các vai trò, trạng thái và ngưỡng tiền trong bài là ví dụ của một hệ thống giả định. Chúng không thay thế quy trình nghiệp vụ hoặc chính sách kiểm soát nội bộ của một tổ chức cụ thể.

## 2. Phân biệt trạng thái, hành động và bằng chứng

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| State — trạng thái | Đối tượng hiện đang ở giai đoạn nào? | Yêu cầu đang chờ duyệt. |
| Command — lệnh | Chủ thể yêu cầu hệ thống làm gì? | Gửi duyệt, ghi nhận phê duyệt hoặc bắt đầu thực thi. |
| Event — sự kiện | Điều gì đã xảy ra và nguồn nào xác nhận? | Nhà cung cấp xác nhận giao dịch hoàn tất. |
| Guard — điều kiện bảo vệ | Điều kiện nào phải đúng để chấp nhận hành động? | Đúng tenant, có quyền, đủ phê duyệt và chưa bắt đầu thực thi. |
| Effect — hiệu ứng | Dữ liệu hoặc công việc nào phát sinh khi hành động được chấp nhận? | Tạo ý định thực thi và sự kiện audit. |
| Invariant — bất biến | Điều gì phải luôn đúng qua mọi đường xử lý? | Người tạo không được tự phê duyệt yêu cầu của mình. |

Một chuỗi ký tự trạng thái do client gửi không phải bằng chứng rằng quy trình đã hoàn thành bước trước. Tương tự, sự kiện có tên “hoàn tất” không đủ tin cậy nếu nguồn gửi, định danh giao dịch và nội dung chưa được xác minh.

Cần phân biệt:

- **Bằng chứng phê duyệt:** ai đã duyệt, có quyền theo chính sách nào, duyệt phiên bản nội dung nào và vào thời điểm nào.
- **Trạng thái được phê duyệt:** kết quả hệ thống đánh giá rằng các bằng chứng đủ điều kiện để đi tiếp.
- **Quyền thực hiện bước kế tiếp:** điều kiện riêng của người hoặc dịch vụ đang yêu cầu hành động.

Có bằng chứng đã duyệt không có nghĩa mọi chủ thể đều được thực thi. Một người có quyền gọi chức năng thực thi cũng không được bỏ qua điều kiện của đối tượng.

## 3. Bắt đầu từ tài sản, tác động và mô hình đe dọa

Giả sử hệ thống nhiều tenant quản lý yêu cầu chi tiền. Các tài sản cần bảo vệ gồm nội dung yêu cầu, quyết định phê duyệt, quyền thực thi, kết quả giao dịch và dấu vết audit.

| Kịch bản rủi ro | Hậu quả | Hướng chuyển thành yêu cầu |
|---|---|---|
| Client gọi thẳng chức năng thực thi từ bản nháp | Bỏ qua kiểm soát phê duyệt. | Chỉ chấp nhận các chuyển trạng thái đã cho phép và kiểm tra trạng thái phía máy chủ. |
| Người tạo tự duyệt yêu cầu | Mất phân tách nhiệm vụ. | Ràng buộc chủ thể duyệt khác người tạo và có vai trò phù hợp. |
| Sửa người nhận hoặc số tiền sau khi được duyệt | Dùng phê duyệt cho nội dung khác. | Ràng buộc phê duyệt với phiên bản nội dung; thay đổi trọng yếu làm mất hiệu lực phê duyệt. |
| Hai thao tác cùng dựa trên trạng thái cũ | Vừa thu hồi vừa thực thi, hoặc thực thi nhiều lần. | Chấp nhận thay đổi theo phiên bản và bảo đảm tính nguyên tử. |
| Gửi lại sau khi không nhận được phản hồi | Tạo thêm ý định thực thi hoặc hiệu ứng nghiệp vụ. | Hợp đồng idempotency và khả năng tra cứu kết quả. |
| Sự kiện hoàn tất giả hoặc đến sai thứ tự | Đánh dấu hoàn tất khi chưa có kết quả đúng. | Xác minh nguồn, liên kết giao dịch, kiểm tra trạng thái và loại sự kiện. |
| Đường quản trị hoặc xử lý hàng loạt bỏ qua luật | Quy tắc chỉ đúng ở một endpoint. | Áp cùng bất biến trên mọi đường thay đổi nghiệp vụ. |
| Người thuộc tenant khác thao tác trên ID đoán được | Thay đổi hoặc đọc dữ liệu ngoài phạm vi quyền. | Ràng buộc tenant và quyền đối tượng trong mọi hành động. |

Chuỗi truy vết nên giữ dạng:

> Rủi ro → bất biến hoặc điều kiện chuyển → yêu cầu → điểm thực thi trong kiến trúc → ca kiểm thử → bằng chứng.

Ẩn nút trên giao diện giúp người dùng hiểu quy trình nhưng không thực thi được toàn bộ chính sách. Các bất biến phải được kiểm soát tại nơi máy chủ chấp nhận và cam kết thay đổi.

## 4. Xây dựng mô hình trạng thái có ngữ nghĩa rõ ràng

### 4.1. Bộ trạng thái của ví dụ

| Trạng thái | Ý nghĩa nghiệp vụ |
|---|---|
| DRAFT | Nội dung đang được chuẩn bị, chưa đủ điều kiện thực thi. |
| SUBMITTED | Nội dung đã gửi duyệt, chờ đủ quyết định phê duyệt. |
| APPROVED | Đã có đủ bằng chứng duyệt cho phiên bản nội dung đang xét. |
| EXECUTING | Đã chấp nhận ý định thực thi; kết quả bên ngoài đang được xử lý. |
| RECONCILING | Chưa đủ bằng chứng kết luận kết quả; cần tra cứu hoặc đối soát. |
| COMPLETED | Có bằng chứng tin cậy xác nhận kết quả thành công đúng nội dung. |
| REJECTED | Quyết định duyệt đã từ chối yêu cầu. |
| CANCELLED | Đã hủy trước khi chấp nhận thực thi theo điều kiện cho phép. |
| FAILED | Có bằng chứng đủ để kết luận lần thực thi không thành công theo hợp đồng. |

REJECTED, CANCELLED, FAILED và COMPLETED là trạng thái kết thúc của phiên workflow trong ví dụ. Nếu nghiệp vụ cần làm lại, phải có hành động hoặc workflow mới được đặc tả, có liên kết truy vết; không sửa trực tiếp bản ghi kết thúc để xóa lịch sử.

Timeout hoặc mất phản hồi không tự chứng minh thực thi thất bại. Khi chưa rõ kết quả, cần dùng RECONCILING thay vì mặc định chuyển FAILED và cho tạo một lần thực thi mới.

### 4.2. Sơ đồ các đường chuyển được phép

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SUBMITTED: gửi duyệt
    DRAFT --> CANCELLED: hủy
    SUBMITTED --> DRAFT: thu hồi để sửa
    SUBMITTED --> APPROVED: đủ phê duyệt
    SUBMITTED --> REJECTED: từ chối
    SUBMITTED --> CANCELLED: hủy
    APPROVED --> DRAFT: thu hồi để sửa
    APPROVED --> CANCELLED: hủy trước thực thi
    APPROVED --> EXECUTING: chấp nhận thực thi
    EXECUTING --> COMPLETED: xác nhận thành công
    EXECUTING --> FAILED: xác nhận không thành công
    EXECUTING --> RECONCILING: chưa rõ kết quả
    RECONCILING --> COMPLETED: đối soát thành công
    RECONCILING --> FAILED: đối soát không thành công
~~~

Sơ đồ thể hiện các đường đi, chưa thể hiện đủ quyền và guard. Mỗi đường cần ma trận điều kiện tương ứng. Mọi đường không được đặc tả đều bị từ chối mặc định.

Việc ghi thêm một phê duyệt có thể chưa làm đổi SUBMITTED nếu chưa đủ số người duyệt. Đây vẫn là một thay đổi nghiệp vụ cần kiểm soát quyền, phiên bản, chống lặp và audit.

## 5. Viết bất biến trước khi viết endpoint

Trong ví dụ, các bất biến chính gồm:

1. Mọi yêu cầu và bằng chứng liên quan thuộc đúng tenant; chủ thể chỉ tác động trong phạm vi được phép.
2. Người tạo không được tự tạo bằng chứng phê duyệt có hiệu lực cho yêu cầu của mình.
3. Chỉ nội dung đã được duyệt đúng phiên bản mới có thể được thực thi.
4. Không tạo ý định thực thi mới từ DRAFT, SUBMITTED hoặc trạng thái kết thúc.
5. Một yêu cầu chỉ có một ý định thực thi logic; gửi lại hoặc nhận lại thông điệp không được tạo thêm ý định.
6. COMPLETED chỉ được thiết lập khi có bằng chứng thành công tin cậy, khớp yêu cầu và giao dịch.
7. Khi đã chấp nhận thực thi, không được dùng hành động hủy trước thực thi để giả vờ rằng công việc bên ngoài chưa tồn tại.
8. Mọi thay đổi được chấp nhận phải có bằng chứng audit theo chính sách; đường xử lý lỗi không được âm thầm bỏ quy tắc.

Bất biến phải áp dụng qua API, giao diện quản trị, tác vụ nền, nhập dữ liệu, xử lý hàng loạt và consumer nhận sự kiện. Không nên có một đường “nội bộ” được bỏ qua tất cả điều kiện chỉ vì người gọi là dịch vụ.

### 5.1. Tách phiên bản workflow khỏi phiên bản nội dung

Hai loại phiên bản có mục đích khác nhau:

| Giá trị | Khi nào thay đổi? | Mục đích |
|---|---|---|
| workflow_version | Mỗi thay đổi nghiệp vụ được chấp nhận, kể cả ghi thêm phê duyệt hoặc đổi trạng thái. | Phát hiện hành động dựa trên ảnh chụp cũ và xử lý cạnh tranh. |
| content_revision | Khi sửa trường nội dung có ảnh hưởng tới quyết định duyệt. | Xác định nội dung nào đã được phê duyệt. |
| approved_content_revision | Khi đánh giá đủ bằng chứng phê duyệt cho một phiên bản nội dung. | Liên kết quyết định duyệt với nội dung được phép thực thi. |

Một lần đổi trạng thái làm tăng workflow_version không nhất thiết làm thay đổi content_revision. Nếu dùng chung một số phiên bản cho cả hai mục đích mà không có ngữ nghĩa rõ ràng, hệ thống có thể vô hiệu hóa nhầm hoặc giữ hiệu lực nhầm một phê duyệt.

Trường trọng yếu phải được liệt kê, chẳng hạn số tiền, đơn vị tiền tệ, người nhận, tài khoản nhận và tài liệu làm căn cứ duyệt. Không để client tự khai rằng một thay đổi là “không trọng yếu”.

### 5.2. Ràng buộc phê duyệt theo nội dung và chính sách

Trong ví dụ, yêu cầu dưới 100 triệu VND cần một người duyệt hợp lệ; từ 100 triệu VND trở lên cần hai người duyệt phân biệt. Mọi người duyệt đều phải khác người tạo.

Đặc tả phải xác định cách biểu diễn số tiền, quy tắc so sánh, đơn vị tiền tệ và các ngưỡng khác nếu có. Không so sánh một giá trị chưa được chuẩn hóa hoặc để client chọn chính sách duyệt.

Bằng chứng phê duyệt cần gắn với content_revision và phiên bản chính sách phù hợp. Chính sách phải nói rõ thời hạn hiệu lực, cách xử lý khi quyền của người duyệt bị thu hồi hoặc khi chính sách thay đổi. Không mặc định rằng một quyết định từ quá khứ luôn đủ điều kiện cho thực thi hiện tại.

Nếu thay đổi nội dung trọng yếu, yêu cầu phải trở về DRAFT theo hành động được phép và các phê duyệt cũ không còn đủ điều kiện thực thi. Lịch sử phê duyệt được giữ để truy vết, không bị xóa để làm như chưa từng tồn tại.

## 6. Ma trận chuyển trạng thái là hợp đồng nghiệp vụ

| Từ → đến | Hành động và chủ thể | Guard chính | Hiệu ứng bắt buộc |
|---|---|---|---|
| DRAFT → SUBMITTED | Người tạo gửi duyệt. | Đúng tenant, có quyền, nội dung đầy đủ và hợp lệ. | Cố định phiên bản nội dung gửi duyệt; ghi audit. |
| SUBMITTED → SUBMITTED | Người duyệt ghi thêm quyết định nhưng chưa đủ số lượng. | Khác người tạo, đúng vai trò, chưa có quyết định trùng có hiệu lực. | Lưu bằng chứng, tăng workflow_version; chưa cho thực thi. |
| SUBMITTED → APPROVED | Hệ thống đánh giá đã đủ quyết định hợp lệ. | Đủ người duyệt phân biệt cho đúng content_revision và chính sách. | Lưu tập bằng chứng cùng approved_content_revision. |
| SUBMITTED → REJECTED | Người có quyền duyệt từ chối. | Quyết định được phép theo chính sách và phiên bản hiện tại. | Ghi người từ chối, lý do và bằng chứng; kết thúc phiên workflow. |
| SUBMITTED hoặc APPROVED → DRAFT | Người tạo thu hồi để sửa. | Chưa chấp nhận ý định thực thi; có quyền thu hồi và đúng phiên bản. | Làm mất hiệu lực duyệt cho thực thi tiếp theo; giữ lịch sử. |
| DRAFT, SUBMITTED hoặc APPROVED → CANCELLED | Chủ thể có quyền hủy tương ứng với từng giai đoạn. | Chưa chấp nhận thực thi; đúng tenant và phiên bản. | Ghi lý do hủy; ngăn bước thực thi sau đó. |
| APPROVED → EXECUTING | Chủ thể thực thi được phân quyền. | Phê duyệt còn hiệu lực, khớp nội dung và đủ mọi điều kiện thực thi. | Tạo một ý định thực thi logic, ghi audit và thông điệp xử lý. |
| EXECUTING → RECONCILING | Dịch vụ xử lý kết quả không thể kết luận. | Có lần thực thi đang được theo dõi và thiếu bằng chứng kết quả cuối. | Giữ định danh lần thực thi; không tạo lần mới vì timeout. |
| EXECUTING hoặc RECONCILING → COMPLETED | Dịch vụ xử lý bằng chứng đáng tin cậy. | Nguồn xác minh được, khớp giao dịch, số tiền, đơn vị tiền tệ và người nhận theo hợp đồng. | Lưu bằng chứng thành công và kết quả nghiệp vụ. |
| EXECUTING hoặc RECONCILING → FAILED | Dịch vụ xử lý bằng chứng kết luận không thành công. | Bằng chứng đủ để loại trừ trường hợp kết quả vẫn chưa rõ theo hợp đồng. | Lưu kết luận và căn cứ; không tự mở lại workflow. |

Cụm “có quyền hủy” trong tài liệu thực tế phải được triển khai thành vai trò và điều kiện cụ thể cho từng trạng thái. Không để một ô ma trận mơ hồ trở thành quyền hủy chung cho mọi người.

Guard cần dựa trên dữ liệu máy chủ và nguồn chính sách tin cậy. Quyền đối tượng, quyền hành động, trạng thái hiện tại, nội dung và phiên bản phải được kiểm tra cùng nhau; biết ID của đối tượng không chứng minh quyền thay đổi.

## 7. Chống tranh chấp và thay đổi dựa trên trạng thái cũ

### 7.1. Vấn đề kiểm tra trước, cập nhật sau

Một cách xử lý dễ sai là đọc trạng thái APPROVED, kiểm tra quyền, rồi cập nhật EXECUTING ở một bước tách rời mà không bảo vệ dữ liệu giữa hai bước. Trong khoảng trống, người tạo có thể đã thu hồi yêu cầu về DRAFT.

Yêu cầu cần ràng buộc rằng việc kiểm tra trạng thái, phiên bản và dữ liệu quyết định chuyển trạng thái phải còn đúng tại thời điểm cam kết thay đổi. Có thể dùng khóa, cập nhật có điều kiện, kiểm soát phiên bản hoặc cơ chế tương đương; cách triển khai phải được chứng minh bằng phép thử cạnh tranh.

Ví dụ hai lệnh cùng dùng workflow_version bằng 17:

~~~text
Hiện tại: APPROVED, workflow_version = 17

Lệnh A: thu hồi để sửa, dựa trên phiên bản 17
Lệnh B: bắt đầu thực thi, dựa trên phiên bản 17

Nếu A được cam kết trước:
  trạng thái thành DRAFT, phiên bản thành 18
  B không được thực thi dựa trên ảnh chụp phiên bản 17

Nếu B được cam kết trước:
  trạng thái thành EXECUTING, phiên bản thành 18
  A không được tiếp tục dùng hành động hủy hoặc thu hồi trước thực thi
~~~

Hai lệnh khác nhau không được cùng tạo ra các kết quả trái bất biến từ cùng một phiên bản. Việc retry cùng một lệnh đã được chấp nhận là trường hợp riêng, cần hợp đồng idempotency.

### 7.2. Đơn vị thay đổi phải bao trùm các dữ liệu liên quan

Với bước bắt đầu thực thi, chỉ cập nhật trạng thái mà không tạo được ý định xử lý có thể làm đối tượng mắc kẹt. Ngược lại, phát thông điệp xử lý trước khi cập nhật trạng thái được cam kết có thể khởi chạy công việc cho một thay đổi đã thất bại.

Mã giả minh họa một đơn vị xử lý cục bộ:

~~~text
trong một đơn vị giao dịch phù hợp:
  lấy đối tượng theo tenant tin cậy và định danh yêu cầu
  xác minh quyền hiện hành theo chính sách của hành động

  nếu tìm thấy cùng lệnh đã được xử lý:
    kiểm tra nội dung khớp và quyền đọc kết quả hiện tại
    trả biên nhận theo hợp đồng, không thực hiện hiệu ứng mới
  ngược lại:
    kiểm tra workflow_version và trạng thái hiện tại
    đánh giá guard trên dữ liệu có thẩm quyền
    tính trạng thái, bằng chứng và hiệu ứng cần ghi
    ghi thay đổi nghiệp vụ
    ghi biên nhận chống lặp
    ghi audit bắt buộc
    ghi ý định xử lý bất đồng bộ nếu hành động cần

sau khi giao dịch đã cam kết:
  chuyển ý định đã lưu tới thành phần xử lý theo hợp đồng
~~~

Đây là mô tả ngữ nghĩa, không phải API của một thư viện. Nếu quyền được cung cấp bởi dịch vụ bên ngoài, phải xác định mốc đánh giá quyền, độ trễ thu hồi được chấp nhận và cách ràng buộc quyết định đó với lệnh. Một khóa trên bản ghi nghiệp vụ không tự làm quyết định quyền ở mọi hệ thống trở thành đồng thời tuyệt đối.

Việc ghi ý định và chuyển thông điệp có thể dùng cơ chế như transactional outbox. Ý định được ghi cùng giao dịch không có nghĩa thông điệp chỉ được giao một lần; consumer vẫn cần xử lý trùng và theo dõi kết quả.

### 7.3. Không dùng rollback cục bộ để diễn giải tác động bên ngoài

Giao dịch cơ sở dữ liệu cục bộ không thể tự hoàn tác một hoạt động đã được hệ thống ngoài chấp nhận. Khi đã thực thi, hành vi hoàn tiền hoặc bù trừ cần một workflow riêng, quyền riêng và bằng chứng riêng.

Không chuyển COMPLETED về APPROVED để “làm lại”, không xóa dấu vết thực thi và không đặt CANCELLED để che một giao dịch bên ngoài vẫn đang chạy. Những thao tác đó làm trạng thái không còn phản ánh thực tế nghiệp vụ.

## 8. Gửi lại, thông điệp trùng và kết quả đến muộn

### 8.1. Hợp đồng idempotency cho lệnh

Một lệnh có thể được gửi lại vì client mất phản hồi, proxy ngắt kết nối hoặc tác vụ nền chạy lại. Đặc tả phải nói rõ:

- Phạm vi khóa: tenant, đối tượng, loại hành động và các thông tin cần thiết để phân biệt lệnh.
- Cách xác định nội dung tương đương bằng biểu diễn chuẩn hóa do máy chủ kiểm soát.
- Cùng khóa nhưng nội dung khác phải được xử lý như xung đột.
- Thời gian lưu biên nhận và hành vi khi thời hạn đó hết.
- Kết quả trả về khi lệnh đầu đã cam kết nhưng client chưa nhận được.
- Quyền cần kiểm tra trước khi trả biên nhận hoặc kết quả đã lưu.
- Cách bảo đảm biên nhận chống lặp không tách rời hiệu ứng nghiệp vụ.

Một lần gửi lại cùng lệnh có thể mang expected workflow_version cũ vì chính lệnh đầu đã tăng phiên bản. Hợp đồng cần nhận diện biên nhận phù hợp trước khi kết luận đây là một lệnh mới dựa trên trạng thái cũ. Tuy nhiên, không được trả dữ liệu đã lưu cho người hiện không còn quyền đọc.

Dùng khóa mới cho cùng đối tượng không được bỏ qua guard. Nếu đối tượng đã EXECUTING hoặc kết thúc, một lệnh thực thi mới vẫn phải bị ngăn theo mô hình trạng thái.

### 8.2. Sự kiện từ hệ thống ngoài

Một callback hoặc thông điệp kết quả phải được xử lý như đầu vào chưa đủ tin cậy cho tới khi xác minh:

1. Nguồn gửi và tính toàn vẹn của thông điệp theo cơ chế đã được phê duyệt.
2. Định danh bên cung cấp, giao dịch và ý định thực thi liên quan.
3. Tenant và đối tượng được suy ra từ liên kết máy chủ quản lý.
4. Các thuộc tính kết quả cần khớp, chẳng hạn số tiền, đơn vị tiền tệ và người nhận.
5. Tính duy nhất hoặc quy tắc chống xử lý trùng.
6. Trạng thái hiện tại có chấp nhận loại sự kiện đó hay không.

Không dùng tenant hoặc ID trong payload làm căn cứ duy nhất để chọn bản ghi cần cập nhật. Cần đối chiếu với ý định thực thi đã được hệ thống ghi nhận.

Nếu nhận lại cùng sự kiện hoàn tất, hệ thống không được tạo thêm hiệu ứng. Nếu đã COMPLETED rồi mới nhận một sự kiện cũ nói “đang xử lý” hoặc một lỗi tạm thời, không được tự lùi trạng thái.

Sự kiện mâu thuẫn hoặc không khớp cần được ghi nhận và đưa vào quy trình đối soát. Không chọn kết quả chỉ theo thứ tự nhận thông điệp nếu thứ tự đó không chứng minh trình tự nghiệp vụ.

### 8.3. Kết quả chưa rõ cần thời hạn xử lý riêng

Khi mất phản hồi từ bên thực thi, RECONCILING biểu thị thiếu bằng chứng kết luận. Cần quy định cách tra cứu, chu kỳ kiểm tra, quyền can thiệp và thời hạn cảnh báo.

Ví dụ, nếu đối tượng ở RECONCILING quá năm phút, hệ thống phát cảnh báo trong 60 giây tiếp theo. Đây là ngưỡng theo dõi minh họa; hết năm phút không tự biến thành bằng chứng để chuyển FAILED.

Nếu bên ngoài hỗ trợ chống lặp, cần ràng buộc định danh dùng lại với một ý định nghiệp vụ. Nếu không có khả năng đó, phải có giới hạn retry và cơ chế xác định kết quả trước khi thực hiện lại. Không tuyên bố bảo đảm hiệu ứng bên ngoài chỉ xảy ra một lần chỉ vì đã chống lặp thông điệp nội bộ.

## 9. Bộ yêu cầu chuyển trạng thái mẫu

### SR-WF-001 — Tập chuyển được phép và từ chối mặc định

Máy chủ chỉ chấp nhận các hành động và đường chuyển được khai báo trong mô hình nghiệp vụ đã phê duyệt. Các đường không khai báo phải bị từ chối mà không làm thay đổi dữ liệu hoặc tạo công việc thực thi.

Client không được đặt tùy ý trạng thái đích qua cập nhật trường thông thường. Luật áp dụng cho API, xử lý hàng loạt, giao diện quản trị và tác vụ nền.

Bằng chứng nghiệm thu gồm thử các đường được phép và các đường bỏ bước như DRAFT tới EXECUTING hoặc COMPLETED, kể cả qua đường cập nhật khác với giao diện chính.

### SR-WF-002 — Quyền hành động và phạm vi đối tượng

Mỗi lệnh phải kiểm tra tenant, quyền truy cập đối tượng, quyền hành động và điều kiện phân tách nhiệm vụ theo chính sách có hiệu lực.

Nguồn tenant và chủ thể phải được xác lập từ ngữ cảnh tin cậy. Giá trị do client khai không được mở rộng phạm vi quyền. Chính sách về hiệu lực quyết định quyền và độ trễ thu hồi phải được ghi rõ.

Bằng chứng phải có tài khoản không có quyền, tài khoản đã bị thu hồi quyền và tài khoản tenant khác. Phản hồi từ chối không được tiết lộ nội dung nghiệp vụ ngoài quyền.

### SR-WF-003 — Phê duyệt gắn với đúng phiên bản nội dung

Mỗi bằng chứng phê duyệt có hiệu lực phải gắn với chủ thể, content_revision và chính sách được dùng để đánh giá.

Trong ví dụ, ngưỡng dưới 100 triệu VND cần một người duyệt; từ ngưỡng đó trở lên cần hai người duyệt phân biệt. Người tạo không được tính vào tập người duyệt. Hai bản ghi hoặc hai lần gửi từ cùng một chủ thể không được tính thành hai người.

Sửa trường trọng yếu phải theo hành động thu hồi để sửa hoặc hành động tương đương đã đặc tả, làm mất hiệu lực phê duyệt đối với nội dung mới. Không được chỉnh trực tiếp nội dung đã duyệt rồi giữ nguyên điều kiện thực thi.

Bằng chứng phải bao gồm đúng biên ngưỡng, sửa số tiền, đổi người nhận và gửi lại quyết định duyệt của cùng một người.

### SR-WF-004 — Kiểm soát cạnh tranh và cam kết nguyên tử

Mỗi lệnh mới thay đổi nghiệp vụ phải mang hoặc sử dụng một căn cứ phiên bản phù hợp. Trạng thái, phiên bản và guard trên dữ liệu nghiệp vụ phải còn đúng khi thay đổi được cam kết.

Các thay đổi liên quan gồm trạng thái, bằng chứng duyệt, biên nhận lệnh, audit bắt buộc và ý định thực thi phải được bảo đảm nhất quán bằng một đơn vị giao dịch hoặc cơ chế tương đương đã được chứng minh.

Khi thu hồi và thực thi cùng cạnh tranh trên một phiên bản, không được chấp nhận cả hai hiệu ứng trái nhau. Lệnh thua cạnh tranh không được tạo thông điệp thực thi hoặc để lại thay đổi từng phần.

### SR-WF-005 — Một ý định thực thi logic và gửi lại an toàn

Mỗi yêu cầu trong ví dụ chỉ có một ý định thực thi logic. Các lần gửi lại cùng lệnh trong thời gian giữ biên nhận phải liên kết với kết quả của lệnh đầu, không tạo thêm ý định.

Trong ví dụ, biên nhận chống lặp được giữ tối thiểu 24 giờ kể từ khi lệnh được chấp nhận. Sau thời hạn lưu, nếu không còn biên nhận, hệ thống trả trạng thái hiện tại theo quyền đọc và hợp đồng tra cứu; không tự thực hiện lại lệnh chỉ vì thiếu biên nhận.

Ngay cả khi biên nhận đã hết hạn, guard theo trạng thái và ràng buộc duy nhất của ý định thực thi vẫn phải ngăn tạo ý định thứ hai cho cùng yêu cầu. Chống lặp ở tầng truyền không thay thế bất biến nghiệp vụ.

### SR-WF-006 — Xác minh kết quả và xử lý trạng thái chưa rõ

Chỉ nguồn được phép và bằng chứng khớp với ý định đã lưu mới được làm đối tượng chuyển sang COMPLETED hoặc FAILED.

Mất phản hồi, timeout hoặc lỗi tạm thời không đủ chứng minh FAILED. Trường hợp thiếu căn cứ phải được theo dõi ở RECONCILING theo hợp đồng.

Sự kiện trùng, đến muộn hoặc mâu thuẫn phải được xử lý theo chính sách mà không tự lùi trạng thái kết thúc hoặc khởi chạy thực thi mới. Can thiệp thủ công cần quyền và bằng chứng riêng, không dùng cập nhật trực tiếp để bỏ qua kiểm soát.

### SR-WF-007 — Audit và khả năng tái dựng quyết định

Mỗi thay đổi được chấp nhận phải để lại bằng chứng về đối tượng, tenant, hành động, trạng thái trước và sau, phiên bản trước và sau, chủ thể, thời điểm, chính sách và liên kết bằng chứng liên quan.

Audit bắt buộc phải được lưu nhất quán với thay đổi nghiệp vụ theo cơ chế đã phê duyệt. Nếu kênh audit tập trung chưa nhận được, chỉ được hoàn tất khi cơ chế lưu bền vững dự phòng đáp ứng chính sách.

Các lần từ chối cần ghi lý do phù hợp cho điều tra mà không lộ bí mật. Audit không được chứa token, mật khẩu hoặc toàn bộ dữ liệu nhạy cảm không cần thiết.

## 10. Ma trận kiểm thử có mục tiêu nghiệp vụ

| Nhóm kiểm thử | Kịch bản | Kết quả cần chứng minh |
|---|---|---|
| Đường đi hợp lệ | Tạo, gửi duyệt, đủ quyết định, thực thi và nhận kết quả. | Từng bước đáp ứng guard; bằng chứng gắn đúng đối tượng và nội dung. |
| Bỏ bước | Gọi thực thi trực tiếp từ DRAFT hoặc tự gửi trạng thái COMPLETED. | Không đổi trạng thái, không tạo ý định và không phát sinh hiệu ứng ngoài. |
| Phân tách nhiệm vụ | Người tạo tự duyệt hoặc một người duyệt gửi nhiều lần. | Không tạo đủ điều kiện bằng quyết định không hợp lệ hoặc trùng chủ thể. |
| Nội dung thay đổi | Thu hồi, đổi người nhận, rồi cố dùng phê duyệt cũ. | Nội dung mới chưa đủ điều kiện thực thi; lịch sử cũ còn nhưng không được tái dùng sai. |
| Tranh chấp | Thu hồi và thực thi cùng dùng một workflow_version. | Chỉ một thay đổi mới được cam kết; không có hiệu ứng từng phần của lệnh thua. |
| Gửi lại | Làm mất phản hồi sau khi lệnh đã cam kết, rồi gửi lại cùng khóa. | Trả biên nhận theo hợp đồng; không tạo ý định thứ hai. |
| Xung đột khóa | Dùng cùng khóa với nội dung khác. | Từ chối xung đột; không biến nội dung mới thành kết quả lệnh cũ. |
| Tenant và quyền | Dùng chủ thể khác tenant hoặc đã bị thu hồi quyền. | Không thay đổi, không đọc được dữ liệu hoặc biên nhận ngoài quyền. |
| Sự kiện kết quả | Gửi sự kiện trùng, muộn, sai giao dịch hoặc không xác minh được nguồn. | Không hoàn tất sai, không lùi trạng thái và không tái thực thi. |
| Lỗi từng phần | Gây lỗi trước cam kết hoặc trước lúc chuyển thông điệp đã lưu. | Không có trạng thái thiếu ý định; công việc đã lưu được xử lý lại an toàn. |
| Đối soát | Mất kết quả rồi nhận bằng chứng thành công muộn. | RECONCILING được giải quyết đúng, không có lần thực thi mới vì timeout. |

Ví dụ kịch bản cạnh tranh:

~~~gherkin
Feature: Thu hồi và thực thi không cùng thắng trên một phiên bản

  Scenario: Hai lệnh khác nhau cùng dựa trên bản đã duyệt
    Given yêu cầu thuộc tenant A đang APPROVED ở workflow_version 17
    And phê duyệt khớp content_revision hiện tại
    And người tạo có quyền thu hồi và người thực thi có quyền thực thi
    When hai lệnh thu hồi và thực thi cạnh tranh trên phiên bản 17
    Then chỉ một thay đổi nghiệp vụ mới được cam kết từ phiên bản đó
    And nếu thu hồi thắng thì không có ý định thực thi
    And nếu thực thi thắng thì thu hồi trước thực thi bị từ chối
    And lệnh không được chấp nhận không để lại hiệu ứng từng phần
    And audit đủ để xác định quyết định đã được cam kết
~~~

Kiểm thử cạnh tranh phải điều khiển được điểm giao nhau giữa đọc dữ liệu, đánh giá điều kiện và cam kết. Chỉ gửi hai request liên tiếp rồi thấy thành công không chứng minh đã bao phủ tranh chấp.

Cần kiểm tra bằng chứng ở dữ liệu nghiệp vụ, ý định xử lý và kết quả bên ngoài trong môi trường thử, thay vì chỉ so mã phản hồi. Với hệ thống ngoài mô phỏng, phải ghi giới hạn của mô hình; mô phỏng không tự chứng minh mọi hành vi của nhà cung cấp thực.

## 11. Audit và phục hồi không làm mất sự thật nghiệp vụ

Audit cần cho phép trả lời: ai yêu cầu hành động, dựa trên nội dung nào, hệ thống kiểm tra gì, quyết định nào được cam kết và hiệu ứng nào đang chờ hoặc đã hoàn thành.

Không chỉ ghi “cập nhật thành công”. Hai yêu cầu có cùng trạng thái cuối có thể có lịch sử hoàn toàn khác nhau, chẳng hạn đi qua đủ phê duyệt hoặc được sửa trực tiếp bởi một công cụ quản trị.

Cần phân biệt:

- **Lệnh bị từ chối:** không thay đổi nghiệp vụ, nhưng có thể cần dấu vết điều tra.
- **Lệnh đã cam kết:** thay đổi và bằng chứng bắt buộc đã được ghi.
- **Thông điệp đã chuyển:** thành phần xử lý đã nhận công việc; chưa chứng minh hiệu ứng hoàn tất.
- **Hiệu ứng đã xác nhận:** có bằng chứng kết quả nghiệp vụ theo hợp đồng.
- **Kết quả chưa rõ:** cần đối soát; không được diễn giải thành chưa thực hiện.

Khi khôi phục dữ liệu từ bản sao cũ, hệ thống có thể quay về trạng thái chưa phản ánh tác động đã xảy ra ở bên ngoài. Trước khi cho xử lý tiếp, cần đối soát ý định, giao dịch và bằng chứng để tránh thực thi lại.

Các công cụ sửa sai phải dùng hành động nghiệp vụ có quyền và audit. Nếu cần ngoại lệ quản trị, đặc tả phải nêu ai được dùng, điều kiện, bằng chứng bổ sung và cơ chế giám sát. Không có quyền “sửa status tùy ý” chỉ vì người thao tác là quản trị viên.

## 12. Những cách viết dễ gây hiểu sai

| Cách viết chưa đủ | Điểm thiếu | Cách làm rõ |
|---|---|---|
| “Chỉ người được phân quyền mới đổi trạng thái.” | Chưa có trạng thái nguồn, guard hoặc quyền trên đối tượng. | Viết ma trận chủ thể, hành động, trạng thái và điều kiện dữ liệu. |
| “Ẩn nút thực thi khi chưa duyệt.” | API và các đường xử lý khác có thể vẫn chấp nhận. | Kiểm soát ở máy chủ trên mọi đường thay đổi. |
| “Có hai bản ghi duyệt là đủ.” | Hai bản ghi có thể cùng người hoặc cho nội dung khác. | Đếm chủ thể phân biệt và đối chiếu phiên bản nội dung. |
| “Đã APPROVED thì được thực thi.” | Nội dung, hiệu lực bằng chứng hoặc quyền có thể đã thay đổi. | Đánh giá lại điều kiện thực thi theo chính sách. |
| “Kiểm tra trạng thái rồi cập nhật.” | Có khoảng trống cạnh tranh. | Ràng buộc kiểm tra và cam kết bằng cơ chế nguyên tử phù hợp. |
| “Timeout thì đánh dấu FAILED và thử lại.” | Hiệu ứng bên ngoài có thể đã xảy ra. | Dùng trạng thái chưa rõ, định danh thực thi và đối soát. |
| “Giao thông điệp một lần nên không thể thực thi trùng.” | Retry hoặc lỗi giữa các hệ thống có thể tạo trùng hiệu ứng. | Đặc tả idempotency và bất biến ở từng ranh giới. |
| “Sự kiện cuối cùng nhận được là sự thật mới nhất.” | Thông điệp có thể sai thứ tự hoặc không đáng tin cậy. | Xác minh nguồn, nội dung, trạng thái và quy tắc đối soát. |
| “Quản trị viên được sửa trực tiếp để xử lý sự cố.” | Có thể bỏ qua phân tách nhiệm vụ và làm mất lịch sử. | Có quy trình sửa sai, quyền và audit cụ thể. |

## 13. Duy trì yêu cầu trong vòng đời phát triển

Khi phân tích nghiệp vụ, xác định ý nghĩa từng trạng thái, điều kiện kết thúc và các bước không được bỏ qua. Khi mô hình hóa đe dọa, đưa vào sửa nội dung sau duyệt, tranh chấp, replay, giả sự kiện và đường quản trị.

Khi thiết kế, liên kết từng yêu cầu SR-WF với điểm kiểm soát quyền, giao dịch dữ liệu, biên nhận lệnh, ý định xử lý và consumer kết quả. Khi phát triển, tập trung luật nghiệp vụ hoặc áp một cơ chế nhất quán để các đường xử lý không diễn giải khác nhau.

Khi nghiệm thu, kiểm tra cả đường hợp lệ lẫn các chuyển không được phép, thay đổi đồng thời và lỗi từng phần. Khi vận hành, theo dõi đối tượng mắc kẹt, RECONCILING kéo dài, ý định chưa được xử lý và các can thiệp quản trị.

Mỗi thay đổi trạng thái hoặc chính sách cần đánh giá lại ma trận và bằng chứng. Thêm một đường “duyệt nhanh”, thay ngưỡng tiền hoặc cho sửa tài khoản nhận sau duyệt có thể làm mất hiệu lực những kiểm thử trước đó.

Bài tập áp dụng: thiết kế workflow hoàn tiền với các bước yêu cầu, duyệt, thực thi và xác nhận. Hãy liệt kê bất biến, quyền chuyển, trường trọng yếu, cách xử lý hai lệnh cạnh tranh, gửi lại sau mất phản hồi và sự kiện thành công đến muộn. Với mỗi yêu cầu, nêu một rủi ro, một điểm thực thi trong kiến trúc và bằng chứng đủ để quyết định đạt hoặc không đạt.

