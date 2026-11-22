# Đánh giá confidentiality, integrity, availability và business loss

## 1. Vì sao cần đánh giá cả CIA và tổn thất kinh doanh?

Một API có thể yêu cầu đăng nhập, chạy qua HTTPS và vẫn gây ra sự cố nghiêm trọng. Người dùng đã xác thực có thể đọc hồ sơ của người khác; một yêu cầu hợp lệ về mặt cú pháp có thể sửa giá trị hóa đơn; một endpoint không trả dữ liệu nhạy cảm vẫn có thể làm cạn tài nguyên khiến toàn bộ dịch vụ ngừng hoạt động.

Vì vậy, khi thiết kế bảo mật API, cần đánh giá tác động của từng tình huống đe dọa đối với:

- **Confidentiality (tính bí mật):** dữ liệu hoặc thông tin chỉ được tiết lộ cho chủ thể được phép.
- **Integrity (tính toàn vẹn):** dữ liệu, trạng thái và kết quả xử lý chỉ được thay đổi theo cách hợp lệ, có thẩm quyền và có thể kiểm chứng.
- **Availability (tính sẵn sàng):** API và các phụ thuộc cần thiết có thể phục vụ đúng đối tượng, trong thời gian và mức chất lượng chấp nhận được.
- **Business loss (tổn thất kinh doanh):** hậu quả thực tế đối với tiền, hoạt động, khách hàng, nghĩa vụ pháp lý, uy tín và mục tiêu của tổ chức.

CIA là cách phân loại thuộc tính an toàn bị ảnh hưởng. Business loss diễn tả điều tổ chức thực sự phải chịu khi thuộc tính đó bị xâm phạm. Hai lớp đánh giá bổ sung cho nhau. Một sự cố có thể ảnh hưởng nhiều thuộc tính CIA cùng lúc và tạo ra nhiều loại tổn thất kinh doanh.

Ví dụ, một API cho phép hoàn tiền có thể bị gọi lặp lại. Việc này làm sai lệch số dư hoặc tạo nhiều giao dịch hoàn tiền, tức ảnh hưởng integrity. Tổ chức có thể mất tiền, phải đối soát thủ công, xử lý khiếu nại và chịu trách nhiệm theo hợp đồng. Nếu endpoint bị khai thác với lưu lượng lớn, nó còn có thể làm giảm availability của dịch vụ thanh toán.

Trong phạm vi **SECURITY_API_SECURITY**, việc đánh giá phải gắn với từng endpoint, đối tượng dữ liệu và luồng nghiệp vụ. Không thể kết luận API an toàn chỉ vì người gọi đã đăng nhập hoặc kết nối được mã hóa.

Sau bài học này, người học có thể:

1. Phân biệt confidentiality, integrity và availability trong ngữ cảnh API.
2. Chuyển một điểm yếu kỹ thuật thành kịch bản đe dọa và hậu quả kinh doanh cụ thể.
3. Đánh giá tác động theo dữ liệu, người dùng, trạng thái nghiệp vụ và phạm vi ảnh hưởng.
4. Ước lượng mức độ nghiêm trọng và ưu tiên xử lý có căn cứ.
5. Liên kết kết quả đánh giá với xác thực, phân quyền, validation, giới hạn tài nguyên, bảo vệ dữ liệu, kiểm thử và giám sát.

## 2. Đơn vị đánh giá: endpoint, đối tượng và hành động

Đánh giá ở cấp tên API hoặc toàn bộ hệ thống thường quá rộng. Cần mô tả một hoạt động cụ thể bằng các thành phần sau:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Endpoint và method | API nào được gọi? GET, POST, PATCH hay DELETE? |
| Actor | Ai gọi: khách hàng, nhân viên, quản trị viên, dịch vụ nội bộ hay đối tác? |
| Object | Đối tượng nào bị đọc hoặc thay đổi: hồ sơ, đơn hàng, hóa đơn, tệp, tài khoản hay giao dịch? |
| Action | Actor đang xem, tạo, sửa, xóa, phê duyệt, xuất hay hoàn tác điều gì? |
| Scope | Đối tượng thuộc người dùng, tenant, phòng ban hay tổ chức nào? |
| State | Đối tượng đang ở trạng thái nào và hành động có hợp lệ ở trạng thái đó không? |
| Context | Yêu cầu đến từ đâu, theo phiên nào, có giới hạn nào và có phụ thuộc nào? |
| Outcome | Thành công hoặc thất bại sẽ làm thay đổi dữ liệu, tiền, quyền hay hoạt động nào? |

Ví dụ, mô tả “API hóa đơn” chưa đủ để đánh giá. Cần tách ít nhất các thao tác:

| Thao tác | Đối tượng | Thuộc tính cần chú ý |
|---|---|---|
| Xem hóa đơn | Hóa đơn của một khách hàng hoặc tenant | Confidentiality |
| Sửa địa chỉ nhận hóa đơn | Thông tin hóa đơn | Integrity |
| Phê duyệt hóa đơn | Trạng thái và quyền phê duyệt | Integrity, business loss |
| Xuất hàng loạt hóa đơn | Tập dữ liệu lớn | Confidentiality, availability |
| Tạo lại báo cáo hóa đơn | Công việc tính toán và hệ thống lưu trữ | Availability, integrity |
| Hủy hoặc hoàn tiền | Giao dịch và trạng thái thanh toán | Integrity, business loss |

Cùng một endpoint có thể cần đánh giá nhiều kịch bản. Ngược lại, một kịch bản có thể đi qua nhiều endpoint. Chẳng hạn, kẻ tấn công đọc thông tin khách hàng bằng API tìm kiếm, lấy mã đối tượng, sau đó gọi API tải tệp để lấy tài liệu riêng tư. Đánh giá phải theo cả chuỗi hành động thay vì chỉ xem từng request độc lập.

### 2.1. Xác định tài sản và chủ sở hữu

Tài sản không chỉ là bảng dữ liệu. Trong một API, tài sản có thể bao gồm:

- Dữ liệu cá nhân, thông tin xác thực, hồ sơ tài chính và tài liệu riêng tư.
- Quyền sở hữu, vai trò, chính sách truy cập và cấu hình tenant.
- Trạng thái đơn hàng, giao dịch, hóa đơn, hạn mức và số dư.
- Khả năng xử lý request, hàng đợi, kết nối cơ sở dữ liệu và dịch vụ phụ thuộc.
- Nhật ký kiểm toán, bằng chứng giao dịch và dữ liệu phục vụ đối soát.
- Quy trình nghiệp vụ mà API đang tự động hóa.

Với mỗi tài sản, hãy xác định ai sở hữu, ai được sử dụng, ai có thể phê duyệt thay đổi và ai chịu trách nhiệm khi tài sản bị xâm phạm. Một người dùng có thể được phép xem hồ sơ của mình nhưng không có quyền xem hồ sơ của người khác trong cùng tenant. Một nhân viên hỗ trợ có thể được phép tra cứu một số trường nhưng không được phép tải toàn bộ dữ liệu định danh.

### 2.2. Xác định ranh giới tin cậy

Ranh giới tin cậy là nơi dữ liệu hoặc quyền hạn đi từ một miền kiểm soát sang miền khác. Trong kiến trúc API, các ranh giới thường gặp gồm:

- Internet đến API Gateway hoặc reverse proxy.
- API Gateway đến dịch vụ nghiệp vụ.
- Dịch vụ này đến dịch vụ khác.
- Tenant này đến tenant khác.
- Người dùng cuối đến nhân viên vận hành.
- Hệ thống nội bộ đến dịch vụ bên thứ ba.
- Dữ liệu do khách hàng nhập đến truy vấn cơ sở dữ liệu, bộ dựng URL, hệ thống tệp hoặc hàng đợi.

Một request đã qua gateway vẫn có thể không đáng tin cậy ở tầng nghiệp vụ. Token hợp lệ chứng minh một danh tính hoặc quyền truy cập ở một phạm vi nhất định; nó không tự chứng minh người gọi có quyền với object cụ thể, thuộc tính cụ thể hay chuyển trạng thái nghiệp vụ cụ thể.

## 3. Đánh giá confidentiality — tính bí mật

Confidentiality bị xâm phạm khi dữ liệu được tiết lộ cho người hoặc hệ thống không được phép. Với API, rủi ro thường nằm ở việc xác định sai phạm vi dữ liệu, phân quyền thiếu chi tiết hoặc trả về nhiều thông tin hơn mức cần thiết.

### 3.1. Các câu hỏi đánh giá

Với mỗi endpoint có thể đọc, tìm kiếm, tải hoặc xuất dữ liệu, hãy hỏi:

1. Dữ liệu nào được trả về? Có trường nhạy cảm, dữ liệu định danh, dữ liệu tài chính, bí mật hệ thống hoặc dữ liệu nội bộ không?
2. Actor có được xem đúng object này không? Quyền có được kiểm tra ở từng object hay chỉ kiểm tra vai trò chung?
3. Actor có được xem mọi thuộc tính của object không? Có trường nào chỉ dành cho chủ sở hữu, bộ phận chuyên trách hoặc dịch vụ nội bộ không?
4. Có thể thay đổi ID, mã tham chiếu, bộ lọc, tenant ID hoặc tham số phân trang để đọc dữ liệu của người khác không?
5. Endpoint tìm kiếm, thống kê, export hoặc autocomplete có làm lộ dữ liệu qua kết quả tổng hợp, metadata hay gợi ý không?
6. Dữ liệu có xuất hiện trong log, thông báo lỗi, URL, cache, trace hoặc file tải xuống không?
7. Một người dùng có thể kết hợp nhiều phản hồi nhỏ để suy ra thông tin lớn hơn không?

### 3.2. Kịch bản thường gặp

**Truy cập object ngoài phạm vi (BOLA/IDOR).** Người dùng đã đăng nhập gọi GET /orders/123. Hệ thống kiểm tra token hợp lệ nhưng không kiểm tra đơn hàng 123 có thuộc người dùng hoặc tenant của người gọi hay không. Người dùng thay ID thành 124 và đọc được đơn hàng của người khác.

**Lộ thuộc tính quá mức.** API trả toàn bộ object người dùng, gồm cả trường nội bộ như trạng thái xác minh, ghi chú hỗ trợ, mã định danh nội bộ hoặc thông tin không cần cho giao diện. Frontend chỉ ẩn trường không có nghĩa API đã bảo vệ trường đó.

**Tìm kiếm và export không giới hạn phạm vi.** API cho phép tìm kiếm theo email hoặc tải danh sách khách hàng. Phân quyền chỉ kiểm tra chức năng “được phép tìm kiếm”, không kiểm tra tenant, bộ phận hoặc phạm vi bản ghi. Một tài khoản thông thường có thể trích xuất dữ liệu của toàn tổ chức.

**Rò rỉ qua lỗi và log.** Thông báo lỗi chứa câu truy vấn, đường dẫn nội bộ, token hoặc dữ liệu request. Log được gửi đến một nền tảng mà nhiều nhóm có thể truy cập, khiến dữ liệu nhạy cảm lan sang một miền tin cậy khác.

**SSRF dẫn đến truy cập dữ liệu nội bộ.** API nhận URL để tải ảnh hoặc kiểm tra webhook. Nếu máy chủ gửi request đến địa chỉ nội bộ mà không kiểm soát đích đến, kẻ tấn công có thể lợi dụng máy chủ làm trung gian đọc metadata hoặc tài nguyên nội bộ. Tác động confidentiality có thể lớn hơn dữ liệu mà endpoint ban đầu xử lý.

### 3.3. Đánh giá phạm vi lộ lọt

Không nên chỉ ghi “lộ dữ liệu”. Hãy mô tả:

- Loại dữ liệu và độ nhạy của dữ liệu.
- Số lượng object hoặc số lượng chủ thể có thể bị ảnh hưởng.
- Phạm vi tenant, tổ chức, khu vực hoặc môi trường.
- Người nhận dữ liệu trái phép và khả năng họ lưu giữ, sao chép hoặc chia sẻ dữ liệu.
- Dữ liệu có thể được dùng để chiếm tài khoản, lừa đảo, cạnh tranh hoặc truy cập sâu hơn hay không.
- Thời gian dữ liệu có thể bị truy cập và khả năng xác định những bản ghi đã bị xem.

Một API chỉ làm lộ một trường có thể vẫn nghiêm trọng nếu trường đó là mã khôi phục, số tài khoản hoặc dữ liệu giúp vượt qua bước xác minh. Ngược lại, số lượng bản ghi lớn không tự động quyết định mức độ nghiêm trọng nếu dữ liệu đã công khai và không tạo ra hậu quả bổ sung. Cần đánh giá cả tính nhạy cảm, khả năng kết hợp và mục đích sử dụng dữ liệu.

## 4. Đánh giá integrity — tính toàn vẹn

Integrity bị xâm phạm khi dữ liệu hoặc trạng thái bị tạo, sửa, xóa, sắp xếp hay xử lý theo cách trái phép hoặc không đúng quy tắc. Với API nghiệp vụ, tác động thường vượt ra ngoài bản ghi bị sửa vì các hệ thống khác có thể tin và tiếp tục sử dụng kết quả đó.

### 4.1. Các câu hỏi đánh giá

Với endpoint ghi hoặc kích hoạt hành động, hãy hỏi:

1. Ai được phép tạo, sửa, xóa hoặc phê duyệt object?
2. Quyền có được kiểm tra cho đúng object và đúng hành động không?
3. Người gọi có thể tự gán các trường nhạy cảm như ownerId, tenantId, role, price, balance, status hoặc approvedBy không?
4. Giá trị có được kiểm tra theo quy tắc nghiệp vụ và trạng thái hiện tại không?
5. Có thể bỏ qua bước phê duyệt, chuyển trạng thái không hợp lệ hoặc gọi hành động theo thứ tự sai không?
6. Request có thể bị phát lại, gửi đồng thời hoặc xử lý nhiều lần không?
7. Có cơ chế chống cập nhật mất dữ liệu, kiểm soát phiên bản và ghi nhận audit không?
8. Khi một bước thất bại, hệ thống có khôi phục hoặc đối soát được trạng thái không?

### 4.2. Kịch bản thường gặp

**Sửa object ngoài quyền.** Người dùng có quyền cập nhật hồ sơ của mình nhưng có thể thay ownerId trong payload để chuyển quyền sở hữu hoặc sửa hồ sơ của người khác.

**Mass assignment.** API ánh xạ trực tiếp payload vào entity. Client gửi thêm role, isAdmin, creditLimit hoặc status dù giao diện không cung cấp các trường này. Nếu server không có allowlist thuộc tính được phép cập nhật, người gọi có thể thay đổi trường đặc quyền.

**Bỏ qua quy trình nghiệp vụ.** Một đơn hàng chỉ được hoàn tiền sau khi đã thanh toán và chưa bị hoàn tiền. Nếu endpoint chỉ nhận orderId và amount mà không kiểm tra trạng thái, người gọi có thể hoàn tiền cho đơn chưa đủ điều kiện hoặc hoàn tiền nhiều lần.

**Thay đổi giá hoặc số lượng ở phía client.** Server tin đơn giá, tổng tiền, chiết khấu hoặc số lượng do client gửi. Kẻ tấn công thay giá trị trong request và tạo giao dịch với số tiền sai.

**Replay hoặc xử lý đồng thời.** Một request hoàn tiền hợp lệ được gửi lại nhiều lần. Nếu hệ thống không dùng idempotency key, khóa nghiệp vụ hoặc kiểm soát trạng thái nguyên tử, nhiều giao dịch có thể được tạo.

**Sửa dữ liệu tham chiếu.** Một API cho phép thay đổi accountId hoặc beneficiaryId nhưng không xác minh quan hệ giữa tài khoản nguồn, người yêu cầu và người thụ hưởng. Giao dịch có thể được chuyển sang đối tượng ngoài ý muốn.

### 4.3. Đánh giá tính đúng đắn của nghiệp vụ

Integrity không chỉ là “dữ liệu trong cơ sở dữ liệu có bị sửa hay không”. Cần kiểm tra cả tính hợp lệ của chuyển trạng thái và kết quả được các hệ thống khác tin dùng.

Ví dụ, một bản ghi hóa đơn có thể đúng định dạng nhưng sai về nghiệp vụ: hóa đơn đã hủy vẫn được thanh toán; một khoản giảm giá vượt hạn mức vẫn được chấp nhận; một nhân viên tự phê duyệt giao dịch do chính mình tạo. Các trường hợp này đều là vấn đề integrity.

Với từng thao tác ghi, hãy mô tả:

- Trạng thái trước hành động.
- Điều kiện để hành động được phép.
- Actor hoặc vai trò có thẩm quyền.
- Dữ liệu được phép thay đổi.
- Trạng thái sau hành động.
- Tác động phụ đến số dư, tồn kho, thông báo, báo cáo và hệ thống tích hợp.
- Cách phát hiện, ngăn chặn hoặc khôi phục khi xử lý sai.

## 5. Đánh giá availability — tính sẵn sàng

Availability bị ảnh hưởng khi API không thể phục vụ yêu cầu hợp lệ trong thời gian hoặc chất lượng cần thiết. Không nhất thiết phải làm máy chủ ngừng hoàn toàn; độ trễ tăng, hàng đợi bị nghẽn, một chức năng cốt lõi không hoạt động hoặc một nhóm khách hàng không thể sử dụng dịch vụ cũng có thể là sự cố availability.

### 5.1. Các câu hỏi đánh giá

1. Endpoint tiêu tốn CPU, bộ nhớ, kết nối, I/O, băng thông hoặc chi phí dịch vụ bên thứ ba ở mức nào?
2. Request có thể yêu cầu kích thước trang, số lượng bản ghi, độ sâu truy vấn hoặc thời gian xử lý không giới hạn không?
3. Có giới hạn tốc độ theo actor, token, IP, tenant và loại thao tác không?
4. Có thể mở nhiều kết nối, gửi request đồng thời hoặc giữ tài nguyên trong thời gian dài không?
5. Endpoint có gọi dịch vụ bên ngoài, tải URL, giải nén tệp hoặc chạy tác vụ tốn kém không?
6. Một tenant có thể tiêu thụ phần lớn tài nguyên dùng chung và làm ảnh hưởng tenant khác không?
7. Khi phụ thuộc bị chậm hoặc lỗi, timeout, retry và circuit breaker có kiểm soát không?
8. Mức tải tối đa, thời gian phục hồi và mục tiêu dịch vụ có được xác định không?

### 5.2. Kịch bản thường gặp

**Unrestricted resource consumption.** API cho phép pageSize rất lớn, truy vấn tùy ý hoặc export hàng triệu bản ghi trong một request. Một số ít người dùng có thể làm cạn bộ nhớ, CPU hoặc kết nối cơ sở dữ liệu.

**Thiếu giới hạn tốc độ.** Endpoint gửi OTP, gửi email, tìm kiếm hoặc tạo báo cáo không có giới hạn phù hợp. Kẻ tấn công có thể làm tăng chi phí, làm nghẽn dịch vụ hoặc khiến chức năng bị khóa vì quota của nhà cung cấp bị sử dụng hết.

**Tác vụ đồng bộ quá nặng.** Request HTTP giữ kết nối trong khi server tải tệp, xử lý ảnh hoặc gọi nhiều dịch vụ. Một lượng nhỏ request chậm có thể giữ hết worker và làm các request bình thường phải chờ.

**Retry storm.** Dịch vụ phụ thuộc chậm, nhiều tầng cùng retry ngay lập tức. Số request tăng theo cấp số nhân và làm hệ thống phục hồi chậm hơn.

**SSRF hoặc outbound request không kiểm soát.** Một endpoint tải URL cho phép truy cập đích không giới hạn. Kẻ tấn công có thể khiến server thực hiện nhiều request tới dịch vụ nội bộ hoặc bên ngoài, tiêu tốn kết nối và tài nguyên.

**Noisy neighbor giữa các tenant.** Một tenant chạy báo cáo nặng liên tục và chiếm hàng đợi dùng chung. Các tenant khác bị ảnh hưởng dù họ không thực hiện hành vi bất thường.

### 5.3. Đánh giá theo chức năng và thời gian

Availability cần gắn với yêu cầu vận hành cụ thể. Hãy xác định:

- Chức năng nào là cốt lõi và chức năng nào có thể trì hoãn.
- Số lượng người dùng, tenant hoặc giao dịch bị ảnh hưởng.
- Thời gian gián đoạn hoặc suy giảm có thể chấp nhận.
- Mùa vụ, thời điểm cao điểm hoặc hạn chót nghiệp vụ.
- Phụ thuộc nào tạo thành điểm lỗi chung.
- Có thể chuyển sang chế độ suy giảm, hàng đợi hoặc quy trình thủ công không.
- Thời gian phục hồi và khả năng xử lý backlog sau khi dịch vụ hoạt động lại.

Một API báo cáo có thể chấp nhận xử lý chậm vài phút, trong khi API xác nhận thanh toán có thể cần phản hồi nhanh và nhất quán. Không nên áp dụng cùng một mức availability cho mọi endpoint.

## 6. Business loss — chuyển tác động kỹ thuật thành hậu quả kinh doanh

CIA cho biết thuộc tính nào bị ảnh hưởng. Business loss trả lời câu hỏi: “Nếu kịch bản này xảy ra, tổ chức, khách hàng hoặc đối tác sẽ mất gì?”

Một kịch bản có thể tạo ra nhiều hậu quả cùng lúc. Ví dụ, việc sửa sai số dư ảnh hưởng integrity, tạo thất thoát tài chính, phát sinh chi phí đối soát, trì hoãn thanh toán và làm giảm niềm tin của khách hàng.

### 6.1. Các nhóm tổn thất

| Nhóm tổn thất | Nội dung cần xem xét | Ví dụ trong API |
|---|---|---|
| Tài chính trực tiếp | Tiền bị mất, hoàn tiền sai, gian lận, tăng chi phí hạ tầng hoặc phí nhà cung cấp | API hoàn tiền bị gọi lặp |
| Vận hành | Gián đoạn quy trình, backlog, xử lý thủ công, mất năng suất | API tạo đơn lỗi khiến nhân viên nhập lại |
| Khách hàng | Mất dữ liệu, gián đoạn dịch vụ, giao dịch sai, mất quyền kiểm soát tài khoản | Người dùng xem được hóa đơn của khách hàng khác |
| Pháp lý và tuân thủ | Vi phạm nghĩa vụ bảo vệ dữ liệu, lưu trữ, thông báo hoặc hợp đồng | Export dữ liệu cá nhân trái phép |
| Uy tín và thương hiệu | Mất niềm tin, khiếu nại, báo chí hoặc đối tác đánh giá tiêu cực | Thông tin tài chính bị lộ |
| Đối tác và chuỗi cung ứng | Vi phạm SLA, mất kết nối, ảnh hưởng hệ thống tích hợp | API đối tác bị quá tải kéo theo giao dịch liên quan thất bại |
| An toàn và con người | Quyết định sai có thể gây hại cho cá nhân hoặc tài sản | API điều khiển thiết bị hoặc quy trình có tác động vật lý |
| Chiến lược | Mất lợi thế cạnh tranh, lộ kế hoạch, gián đoạn sản phẩm hoặc mất cơ hội kinh doanh | API nội bộ làm lộ dữ liệu giá và hợp đồng |

Không phải hệ thống nào cũng có tất cả nhóm tổn thất. Hãy chọn các nhóm thực sự liên quan đến nghiệp vụ, đồng thời hỏi chủ sở hữu nghiệp vụ khi chưa rõ mức độ hậu quả.

### 6.2. Đặt câu hỏi theo chuỗi hậu quả

Một cách hữu ích là đi từ sự kiện kỹ thuật đến tác động cuối cùng:

1. **Sự kiện:** điều gì có thể xảy ra? Ví dụ, người dùng tenant A đọc được hóa đơn của tenant B.
2. **Tài sản bị ảnh hưởng:** dữ liệu, tiền, quyền, trạng thái hay năng lực xử lý nào bị tác động?
3. **Chủ thể chịu ảnh hưởng:** khách hàng, nhân viên, đối tác hay tổ chức nào?
4. **Hậu quả tức thời:** dữ liệu bị tiết lộ, giao dịch sai, dịch vụ chậm hay quy trình bị dừng?
5. **Hậu quả tiếp theo:** dữ liệu bị sử dụng để lừa đảo, đối soát bị sai, nghĩa vụ thông báo phát sinh hay hệ thống phụ thuộc tiếp tục nhận dữ liệu sai?
6. **Khả năng phục hồi:** có thể thu hồi dữ liệu đã lộ không, đảo ngược giao dịch không, khôi phục từ backup không, hay phải thông báo và bồi thường?
7. **Bằng chứng:** tổ chức có thể xác định ai đã truy cập, bản ghi nào bị ảnh hưởng và thời điểm xảy ra không?

Hãy phân biệt hậu quả có thể đảo ngược và không thể đảo ngược. Có thể khôi phục một bản ghi bị xóa từ backup, nhưng không thể đảm bảo người nhận trái phép xóa mọi bản sao của dữ liệu đã tải xuống. Có thể hoàn tác một giao dịch nội bộ, nhưng việc khách hàng đã nhận thông báo sai hoặc đối tác đã hành động theo dữ liệu sai có thể khó khắc phục hơn.

### 6.3. Không đánh giá business loss chỉ bằng số tiền

Tổn thất tài chính trực tiếp thường dễ hình dung, nhưng không đại diện đầy đủ cho mức độ nghiêm trọng. Một sự cố không làm mất tiền ngay vẫn có thể gây hậu quả pháp lý, ảnh hưởng quyền riêng tư hoặc khiến tổ chức không thể chứng minh tính chính xác của giao dịch.

Ngược lại, không nên tự suy đoán mức phạt, nghĩa vụ pháp lý hoặc số tiền thiệt hại nếu chưa có căn cứ. Ghi rõ điều đã biết, giả định cần xác minh và người có thẩm quyền xác nhận. Khi có quy định hoặc hợp đồng cụ thể, hãy tham chiếu đúng phạm vi áp dụng và phiên bản đang hiệu lực.

## 7. Chấm điểm tác động và ưu tiên rủi ro

Chấm điểm giúp các nhóm kỹ thuật và nghiệp vụ thảo luận trên cùng một cơ sở. Điểm số không thay thế phân tích kịch bản và không phải phép đo chính xác tuyệt đối.

### 7.1. Thang tác động tham khảo

Có thể dùng thang 1–5 cho từng thuộc tính và nhóm business loss. Tổ chức nên hiệu chỉnh mô tả theo dữ liệu, nghĩa vụ và mức chịu đựng rủi ro của mình.

| Mức | Mô tả tác động tham khảo |
|---|---|
| 1 — Không đáng kể | Phạm vi rất nhỏ; không có dữ liệu nhạy cảm hoặc giao dịch quan trọng; xử lý nhanh theo quy trình thông thường |
| 2 — Thấp | Ảnh hưởng giới hạn đến một số người dùng hoặc chức năng phụ; có cách khôi phục đơn giản; chi phí xử lý thấp |
| 3 — Trung bình | Ảnh hưởng rõ rệt đến một nhóm khách hàng, tenant hoặc quy trình; cần điều tra và khắc phục có phối hợp |
| 4 — Cao | Ảnh hưởng lớn hoặc kéo dài; có thể gây thiệt hại tài chính đáng kể, vi phạm nghĩa vụ, gián đoạn chức năng quan trọng hoặc cần ứng phó sự cố chính thức |
| 5 — Nghiêm trọng | Ảnh hưởng diện rộng hoặc hệ quả khó đảo ngược; đe dọa hoạt động cốt lõi, quyền lợi quan trọng, nghĩa vụ pháp lý hoặc an toàn con người |

Khi chấm, ghi rõ lý do. Ví dụ, “4 — Cao vì có thể lộ dữ liệu tài chính của nhiều tenant và không thể thu hồi bản sao đã tải xuống” có giá trị hơn chỉ ghi “Impact = 4”.

### 7.2. Đánh giá riêng từng chiều

Không nên cộng hoặc lấy trung bình các điểm CIA để che khuất một tác động nghiêm trọng. Nếu confidentiality là 5, integrity là 1 và availability là 1, điểm trung bình thấp không làm cho việc lộ dữ liệu nghiêm trọng trở nên an toàn.

Có thể lưu kết quả dưới dạng vector:

- Confidentiality: mức tác động và lý do.
- Integrity: mức tác động và lý do.
- Availability: mức tác động và lý do.
- Business loss: từng nhóm tổn thất liên quan, mức tác động và lý do.
- Overall impact: mức tác động tổng thể được chọn theo quy tắc ưu tiên đã thống nhất, thường cần xem xét chiều nghiêm trọng nhất và các hậu quả kết hợp.

Một số hậu quả kết hợp có thể làm mức tổng thể cao hơn từng chiều riêng lẻ. Ví dụ, dữ liệu bị sửa sai đồng thời làm mất khả năng đối soát, gây thất thoát tài chính và khiến nhiều hệ thống tích hợp tiếp tục xử lý dữ liệu sai.

### 7.3. Phân biệt impact và likelihood

**Impact** mô tả hậu quả nếu kịch bản xảy ra. **Likelihood** mô tả khả năng kịch bản xảy ra trong bối cảnh cụ thể. Hai khái niệm không được đánh đồng.

Likelihood có thể phụ thuộc vào:

- Khả năng tiếp cận endpoint và điều kiện xác thực.
- Mức độ dễ khai thác và kiến thức cần thiết.
- Mức độ phổ biến của lỗi trong các endpoint tương tự.
- Khả năng tự động hóa, lặp lại và mở rộng phạm vi.
- Các kiểm soát hiện có và khả năng bị vượt qua.
- Tín hiệu từ kiểm thử, log, sự cố trước đây và threat intelligence phù hợp.

Một lỗi có impact cao vẫn cần ưu tiên dù likelihood chưa được xác định chắc chắn. Khi thiếu bằng chứng, ghi “chưa đủ dữ liệu” thay vì tự đặt một xác suất chính xác.

Nếu tổ chức sử dụng thang 1–5 cho likelihood và impact, có thể dùng tích hai điểm để hỗ trợ sắp xếp ban đầu:

Risk score = Likelihood × Impact

Điểm này chỉ là công cụ phân loại. Cần giữ lại kịch bản, lý do chấm, độ tin cậy của dữ liệu và các yếu tố có thể khiến kết quả thay đổi. Không dùng điểm tích để tự động hạ mức của kịch bản có hậu quả pháp lý, an toàn hoặc không thể đảo ngược.

### 7.4. Inherent risk và residual risk

- **Inherent risk** là rủi ro trước khi tính đến các kiểm soát cụ thể.
- **Residual risk** là rủi ro còn lại sau khi xem xét thiết kế, phạm vi và hiệu quả thực tế của các kiểm soát.

Không nên giảm residual risk chỉ vì tài liệu thiết kế nói rằng đã có kiểm soát. Cần kiểm tra kiểm soát có được áp dụng ở đúng endpoint, đúng object, đúng luồng và có thể bị bỏ qua hay không. Ví dụ, gateway có rate limit không đảm bảo endpoint export đã được bảo vệ nếu giới hạn chỉ áp dụng theo IP và một token có thể gọi nhiều đường dẫn khác nhau.

## 8. Ví dụ xuyên suốt: API hoàn tiền cho đơn hàng

Giả sử một nền tảng thương mại điện tử cung cấp endpoint POST /v1/orders/{orderId}/refund. Người dùng hỗ trợ có thể khởi tạo hoàn tiền theo chính sách; một số giao dịch cần người quản lý phê duyệt. Dịch vụ hoàn tiền gọi cổng thanh toán bên ngoài và cập nhật trạng thái đơn hàng.

### 8.1. Xác định luồng nghiệp vụ hợp lệ

Một luồng hợp lệ có thể gồm:

1. Xác định người gọi và vai trò.
2. Kiểm tra người gọi thuộc bộ phận và phạm vi được phép xử lý đơn hàng.
3. Đọc trạng thái hiện tại của đơn hàng và giao dịch thanh toán.
4. Kiểm tra điều kiện hoàn tiền, số tiền tối đa, thời hạn và lý do.
5. Yêu cầu phê duyệt nếu vượt ngưỡng.
6. Gửi yêu cầu đến cổng thanh toán với mã tham chiếu duy nhất.
7. Cập nhật trạng thái theo kết quả đã xác nhận.
8. Ghi audit event và cung cấp thông tin cho đối soát.

Mô tả này tạo cơ sở để tìm những điểm có thể bị bỏ qua hoặc thao túng.

### 8.2. Các kịch bản theo CIA và business loss

| Kịch bản | CIA bị ảnh hưởng | Business loss có thể phát sinh |
|---|---|---|
| Nhân viên thay orderId và xem được thông tin đơn hàng ngoài phạm vi | Confidentiality | Lộ thông tin khách hàng, khiếu nại, nghĩa vụ xử lý dữ liệu |
| Người gọi tự gửi amount lớn hơn số tiền đủ điều kiện | Integrity | Hoàn tiền sai, thất thoát tiền, đối soát và thu hồi phức tạp |
| Người gọi tự gửi approvedBy hoặc status | Integrity | Bỏ qua phê duyệt, mất kiểm soát nội bộ, khó xác định trách nhiệm |
| Request hợp lệ bị phát lại nhiều lần | Integrity, availability | Hoàn tiền trùng, tăng tải cổng thanh toán, chi phí điều tra |
| Endpoint không giới hạn số request và gọi cổng thanh toán đồng bộ | Availability | Dịch vụ chậm, quota bị tiêu thụ, giao dịch khác bị ảnh hưởng |
| Log lưu toàn bộ thông tin thanh toán hoặc dữ liệu cá nhân | Confidentiality | Mở rộng phạm vi lộ dữ liệu, chi phí ứng phó và nghĩa vụ thông báo |

### 8.3. Kiểm soát cần đánh giá

**Xác thực:** xác định đúng danh tính người gọi hoặc dịch vụ gọi. Không dùng một danh tính kỹ thuật dùng chung cho mọi hành động nếu cần truy vết trách nhiệm.

**Phân quyền chức năng:** chỉ vai trò phù hợp mới được khởi tạo hoặc phê duyệt hoàn tiền. Người tạo giao dịch có thể bị cấm tự phê duyệt theo nguyên tắc phân tách nhiệm vụ.

**Phân quyền object:** kiểm tra đơn hàng thuộc đúng tenant, khách hàng hoặc phạm vi bộ phận mà người gọi được xử lý. Không tin orderId do client gửi chỉ vì token hợp lệ.

**Phân quyền thuộc tính:** client không được tự gán approvedBy, approvalStatus, refundStatus hoặc các trường hệ thống. Server tự xác định các trường này từ danh tính và quy trình được xác thực.

**Validation nghiệp vụ:** số tiền hoàn không vượt phần đã thanh toán còn đủ điều kiện; đơn hàng phải ở trạng thái hợp lệ; lý do hoàn tiền và thời hạn phải được kiểm tra ở server.

**Idempotency và đồng thời:** dùng khóa idempotency có phạm vi và thời hạn phù hợp; lưu trạng thái xử lý; bảo đảm một yêu cầu logic không tạo nhiều giao dịch hoàn tiền. Xử lý cập nhật trạng thái cần an toàn trước request đồng thời.

**Bảo vệ tài nguyên:** giới hạn tốc độ, kích thước request và số tác vụ đang chạy; đặt timeout cho cổng thanh toán; kiểm soát retry; tách công việc dài sang hàng đợi khi phù hợp.

**Bảo vệ dữ liệu:** chỉ trả các trường cần thiết; không ghi thông tin thanh toán hoặc bí mật vào log; mã hóa dữ liệu khi truyền và khi lưu theo yêu cầu của hệ thống.

**Kiểm thử và giám sát:** kiểm thử truy cập chéo object, thay đổi thuộc tính, bỏ qua phê duyệt, replay, request đồng thời và giới hạn tải. Giám sát số lần hoàn tiền bất thường, tỷ lệ lỗi, độ trễ, retry và chênh lệch đối soát.

### 8.4. Kết quả đánh giá mẫu

| Trường | Kết quả minh họa |
|---|---|
| Asset | Tiền hoàn, trạng thái đơn hàng, thông tin khách hàng và audit trail |
| Threat scenario | Nhân viên gọi lại request hoàn tiền với cùng orderId và amount |
| Weakness giả định | Không có idempotency; trạng thái được kiểm tra trước khi gọi cổng thanh toán nhưng không khóa hoặc cập nhật nguyên tử |
| CIA | Integrity: Cao; Availability: Trung bình |
| Business loss | Hoàn tiền trùng, thất thoát tài chính, đối soát thủ công, khiếu nại khách hàng |
| Impact | 4 — Cao, nếu có thể lặp trên nhiều đơn hàng |
| Likelihood | Chấm theo khả năng tiếp cận, khả năng tự động hóa và kết quả kiểm thử; không suy đoán khi thiếu dữ liệu |
| Existing controls | Xác thực, vai trò hỗ trợ, kiểm tra trạng thái đơn hàng |
| Control gap | Chưa chống replay và chưa bảo đảm xử lý nguyên tử |
| Evidence cần có | Mã xử lý giao dịch, log đã che dữ liệu nhạy cảm, kiểm thử request lặp/đồng thời và báo cáo đối soát |
| Treatment | Bổ sung idempotency, ràng buộc trạng thái và kiểm thử cạnh tranh; cảnh báo khi có giao dịch trùng |

Đây là ví dụ giả định để minh họa phương pháp. Điểm số và kiểm soát thực tế phải được xác nhận bằng thiết kế, mã nguồn, cấu hình và quy trình của hệ thống cụ thể.

## 9. Liên kết đánh giá với các lớp bảo vệ API

Kết quả CIA và business loss chỉ hữu ích khi chuyển thành yêu cầu kiểm soát có thể triển khai và kiểm chứng.

| Lớp bảo vệ | Câu hỏi thiết kế | Rủi ro được giảm thiểu |
|---|---|---|
| Authentication | Ai đang gọi? Danh tính có được xác minh và gắn với phiên hoặc dịch vụ phù hợp không? | Giảm truy cập từ chủ thể chưa xác thực |
| Function-level authorization | Actor có được phép thực hiện loại hành động này không? | Giảm lạm dụng chức năng đặc quyền |
| Object-level authorization | Actor có quyền với đúng object và đúng tenant không? | Giảm BOLA/IDOR và lộ hoặc sửa dữ liệu ngoài phạm vi |
| Property-level authorization | Actor có được đọc hoặc sửa từng trường không? | Giảm excessive data exposure và mass assignment |
| Workflow authorization | Hành động có hợp lệ ở trạng thái hiện tại và đúng thứ tự không? | Giảm bỏ qua quy trình, phê duyệt sai và gian lận |
| Input validation | Dữ liệu có đúng kiểu, phạm vi, định dạng và quy tắc nghiệp vụ không? | Giảm dữ liệu sai, injection và thao túng nghiệp vụ |
| SSRF protection | Server có thể kết nối tới đích nào? URL, DNS, redirect và địa chỉ IP được kiểm soát ra sao? | Giảm truy cập tài nguyên nội bộ và lạm dụng outbound request |
| Resource protection | Request tiêu tốn tài nguyên nào và giới hạn ở đâu? | Giảm cạn kiệt tài nguyên, tăng chi phí và gián đoạn |
| Data protection | Dữ liệu nào được trả về, lưu trữ, truyền, log và cache? | Giảm lộ lọt và mở rộng phạm vi sự cố |
| Testing | Kiểm thử có bao gồm actor khác nhau, object khác nhau, tenant khác nhau và trạng thái khác nhau không? | Phát hiện lỗi phân quyền và lỗi nghiệp vụ |
| Monitoring | Có thể phát hiện hành vi bất thường và tái dựng sự kiện không? | Giảm thời gian phát hiện, điều tra và phục hồi |

### 9.1. Xác thực không thay thế phân quyền

Xác thực trả lời “ai đang gọi?”. Phân quyền trả lời “người này được làm gì, trên object nào, với trường nào và trong điều kiện nào?”. Một token hợp lệ không tự cấp quyền đọc mọi hồ sơ hoặc phê duyệt mọi giao dịch.

Kiểm tra quyền nên được thực hiện ở phía server trên mỗi request và gắn với dữ liệu thực tế. Không dựa vào việc frontend ẩn nút, client gửi tenantId, hoặc gateway đã xác thực token để kết luận object thuộc phạm vi của người gọi.

### 9.2. Validation phải bao gồm quy tắc nghiệp vụ

Kiểm tra schema là cần thiết nhưng chưa đủ. Giá trị có thể đúng kiểu và vẫn sai nghiệp vụ. Ví dụ, amount là số dương nhưng vượt số tiền đã thanh toán; status là một enum hợp lệ nhưng không được phép chuyển từ trạng thái hiện tại; callback URL đúng định dạng nhưng trỏ đến mạng nội bộ.

Hãy kiểm tra cả cú pháp, ngữ nghĩa, quan hệ giữa các trường, trạng thái hiện tại và quyền của actor. Dữ liệu quan trọng cần được tính hoặc xác nhận ở server từ nguồn đáng tin cậy.

### 9.3. Chống SSRF theo luồng dữ liệu

Nếu API nhận URL hoặc dữ liệu có thể dẫn đến outbound request, cần xác định rõ:

- Thành phần nào thực hiện request và bằng quyền mạng nào.
- Giao thức và cổng nào được phép.
- Có chặn loopback, link-local, private address và địa chỉ metadata không.
- DNS có thể thay đổi giữa lúc kiểm tra và kết nối không.
- Redirect có bị theo dõi không; nếu có, từng đích mới có được kiểm tra lại không.
- Có giới hạn thời gian, kích thước phản hồi, số redirect và số kết nối không.
- Dịch vụ có thể truy cập những mạng nội bộ nào; có egress policy để giới hạn phạm vi không.

Kiểm tra chuỗi URL một lần rồi tin kết quả là chưa đủ nếu DNS hoặc redirect có thể thay đổi đích thực tế. Kiểm soát nên áp dụng ở cả tầng ứng dụng và mạng khi phù hợp.

### 9.4. Chống lạm dụng tài nguyên

Không chỉ đặt một giới hạn request chung. Hãy xem xét giới hạn theo:

- Danh tính, token, IP, tenant và nhóm endpoint.
- Kích thước body, số lượng phần tử, page size và thời gian xử lý.
- Số tác vụ đồng thời, số lần thử lại và số kết nối outbound.
- Chi phí của thao tác, chẳng hạn export, tìm kiếm phức tạp hoặc gửi thông báo.
- Hạn mức theo thời gian và khả năng công bằng giữa các tenant.

Rate limit cần có phản hồi rõ ràng, quan sát được và phù hợp với đặc tính nghiệp vụ. Một ngưỡng quá thấp có thể tự gây gián đoạn cho khách hàng hợp lệ; một ngưỡng quá cao có thể không bảo vệ được tài nguyên đắt tiền.

## 10. Kiểm thử và thu thập bằng chứng

Đánh giá chỉ dựa trên tài liệu thiết kế dễ bỏ sót khác biệt giữa dự kiến và triển khai. Cần kết hợp nhiều nguồn bằng chứng:

- Đặc tả API và schema request/response.
- Sơ đồ luồng dữ liệu, ranh giới tin cậy và danh sách dịch vụ phụ thuộc.
- Quy tắc nghiệp vụ, ma trận vai trò và ma trận quyền theo object.
- Mã nguồn xử lý phân quyền, validation và chuyển trạng thái.
- Cấu hình gateway, rate limit, timeout, retry, cache và egress.
- Kết quả kiểm thử bảo mật, kiểm thử tích hợp và kiểm thử tải.
- Log, metric, audit event, cảnh báo và hồ sơ sự cố.
- Phỏng vấn chủ sở hữu nghiệp vụ, vận hành, bảo mật và pháp chế khi cần.

### 10.1. Ma trận kiểm thử tối thiểu

Với mỗi endpoint, hãy chọn các trường hợp đại diện:

| Chiều kiểm thử | Trường hợp cần thử |
|---|---|
| Danh tính | Không token, token hết hạn, token sai audience, tài khoản bị khóa |
| Chức năng | Vai trò không có quyền gọi hành động |
| Object | ID của người khác, tenant khác, object đã xóa hoặc không tồn tại |
| Thuộc tính | Gửi thêm trường nhạy cảm, sửa trường ngoài allowlist, đọc trường không được phép |
| Workflow | Chuyển trạng thái sai, bỏ qua phê duyệt, thao tác sai thứ tự |
| Input | Giá trị biên, dữ liệu thiếu, kiểu sai, payload lớn, URL bất thường |
| Replay và concurrency | Gửi lại cùng request, gửi đồng thời, timeout rồi retry |
| Availability | Tốc độ cao, page size lớn, tác vụ dài, phụ thuộc chậm hoặc lỗi |
| Data leakage | Lỗi, log, cache, export và response chứa dữ liệu ngoài phạm vi |

Thực hiện kiểm thử trong môi trường và phạm vi được phép. Dùng dữ liệu thử nghiệm phù hợp, ghi lại điều kiện tái hiện và tránh tạo giao dịch hoặc tác động thật ngoài kế hoạch kiểm thử.

### 10.2. Bằng chứng cần gắn với kết luận

Mỗi phát hiện nên có:

- Endpoint, method, actor và object liên quan.
- Request hoặc điều kiện tái hiện đã loại bỏ bí mật và dữ liệu cá nhân.
- Kết quả thực tế và kết quả mong đợi.
- Tài sản và thuộc tính CIA bị ảnh hưởng.
- Hậu quả kinh doanh có căn cứ hoặc giả định cần xác minh.
- Mức tác động, likelihood, độ tin cậy và lý do.
- Kiểm soát hiện có, khoảng trống và khuyến nghị xử lý.
- Người hoặc nhóm chịu trách nhiệm xác nhận rủi ro còn lại.

Không đưa token, mật khẩu, khóa bí mật hoặc dữ liệu cá nhân thật vào báo cáo nếu không cần thiết. Nếu cần minh họa, dùng dữ liệu giả lập hoặc che thông tin.

## 11. Giám sát sau khi triển khai

Kiểm soát có thể suy giảm khi endpoint mới được thêm, quyền thay đổi, tenant tăng lên hoặc phụ thuộc bên ngoài thay đổi. Cần theo dõi cả tín hiệu kỹ thuật và tín hiệu nghiệp vụ.

**Tín hiệu confidentiality:**

- Một actor đọc nhiều object bất thường hoặc liên tục truy cập object ngoài phạm vi.
- Tăng đột biến số lượng bản ghi được export.
- Truy cập chéo tenant hoặc truy cập trường nhạy cảm không thường lệ.
- Lỗi phân quyền tăng hoặc có nhiều lần dò ID.

**Tín hiệu integrity:**

- Tỷ lệ cập nhật thất bại, xung đột phiên bản hoặc chuyển trạng thái không hợp lệ.
- Giao dịch trùng, số tiền bất thường hoặc sai lệch đối soát.
- Thay đổi quyền, owner, tenant hoặc thuộc tính đặc quyền.
- Hành động nhạy cảm không có audit event hoặc thiếu người phê duyệt.

**Tín hiệu availability:**

- Độ trễ p95/p99, tỷ lệ lỗi, số request đồng thời và độ dài hàng đợi.
- CPU, bộ nhớ, connection pool, I/O và băng thông.
- Retry, timeout, circuit breaker và lỗi dịch vụ phụ thuộc.
- Mức tiêu thụ quota hoặc chi phí của dịch vụ bên thứ ba.
- Chênh lệch tải giữa các tenant.

**Tín hiệu business loss:**

- Tỷ lệ hoàn tiền, hủy đơn, khiếu nại hoặc giao dịch phải xử lý thủ công.
- Số khách hàng hoặc đối tác bị ảnh hưởng.
- Chênh lệch tài chính và thời gian đối soát.
- Sự cố SLA, thời gian gián đoạn và thời gian phục hồi.
- Số lượng dữ liệu cần xác định phạm vi, thu hồi hoặc thông báo.

Log và metric cần được thiết kế có chủ đích. Ghi đủ thông tin để điều tra nhưng không ghi bí mật hoặc toàn bộ payload nhạy cảm. Dùng correlation ID để liên kết các bước trong một luồng, đồng thời kiểm soát quyền truy cập, thời hạn lưu và tính toàn vẹn của audit log.

## 12. Những lỗi thường gặp khi đánh giá

1. **Chỉ đánh giá ở cấp hệ thống.** Kết luận “hệ thống có xác thực” không chứng minh từng endpoint kiểm tra đúng object và hành động.
2. **Chỉ ghi CIA mà không ghi hậu quả.** Nhãn “confidentiality: high” chưa cho biết dữ liệu nào lộ, ai bị ảnh hưởng và tổ chức phải làm gì.
3. **Gộp mọi tác động thành một điểm trung bình.** Điểm trung bình có thể che khuất một chiều có hậu quả rất nghiêm trọng.
4. **Coi mọi dữ liệu có cùng độ nhạy.** Email công khai, mã khôi phục và thông tin thanh toán có mức tác động khác nhau.
5. **Tin vào client hoặc gateway.** Tenant ID, owner ID, giá trị tiền và trạng thái do client gửi phải được xác minh ở server.
6. **Chỉ kiểm tra quyền ở chức năng.** Có quyền gọi API không đồng nghĩa có quyền với mọi object hoặc mọi thuộc tính.
7. **Bỏ qua chuỗi endpoint.** Nhiều endpoint riêng lẻ có vẻ ít rủi ro nhưng khi kết hợp có thể tạo thành luồng khai thác hoàn chỉnh.
8. **Đồng nhất availability với máy chủ còn chạy.** Một dịch vụ phản hồi nhưng quá chậm để hoàn tất giao dịch vẫn có thể không đáp ứng yêu cầu nghiệp vụ.
9. **Chấm likelihood theo cảm giác.** Điểm cần dựa trên điều kiện tiếp cận, khả năng khai thác, kiểm thử và dữ liệu quan sát.
10. **Coi kiểm soát trên giấy là hiệu quả.** Cần xác minh kiểm soát thực sự áp dụng cho đúng endpoint và có thể phát hiện khi bị vượt qua.
11. **Bỏ qua khả năng phục hồi.** Backup không tự giải quyết được dữ liệu đã bị tải xuống, giao dịch đã được bên ngoài thực hiện hoặc niềm tin đã mất.
12. **Không cập nhật đánh giá.** Thay đổi API, schema, vai trò, tenant, phụ thuộc hoặc quy trình có thể làm thay đổi tác động và likelihood.

## 13. Checklist đánh giá cho một endpoint

Trước khi kết thúc đánh giá, hãy xác nhận các câu hỏi sau đã có câu trả lời hoặc được ghi rõ là chưa xác định:

- [ ] Đã xác định endpoint, method, actor, object, action, tenant và trạng thái nghiệp vụ.
- [ ] Đã xác định chủ sở hữu tài sản và dữ liệu nhạy cảm liên quan.
- [ ] Đã mô tả ít nhất các kịch bản confidentiality, integrity và availability có liên quan.
- [ ] Đã kiểm tra phân quyền chức năng, object và thuộc tính.
- [ ] Đã kiểm tra quy tắc nghiệp vụ, chuyển trạng thái, replay và request đồng thời.
- [ ] Đã xem xét validation, SSRF, giới hạn tài nguyên và phụ thuộc bên ngoài.
- [ ] Đã chuyển tác động kỹ thuật thành hậu quả kinh doanh cụ thể.
- [ ] Đã ghi mức impact, likelihood, độ tin cậy và căn cứ chấm điểm.
- [ ] Đã phân biệt inherent risk và residual risk.
- [ ] Đã xác minh hiệu quả kiểm soát bằng kiểm thử hoặc bằng chứng triển khai.
- [ ] Đã xác định log, metric, audit event và tín hiệu cần giám sát.
- [ ] Đã ghi người chịu trách nhiệm xử lý và tiêu chí chấp nhận rủi ro còn lại.

## 14. Kết luận

Đánh giá confidentiality, integrity, availability và business loss là bước chuyển từ việc liệt kê điểm yếu kỹ thuật sang hiểu rõ một API có thể gây ra hậu quả gì. Confidentiality tập trung vào ai có thể biết dữ liệu; integrity tập trung vào ai có thể thay đổi dữ liệu và trạng thái; availability tập trung vào khả năng duy trì dịch vụ; business loss mô tả thiệt hại thực tế đối với tổ chức và các bên liên quan.

Một đánh giá có chất lượng luôn gắn với endpoint, object, actor và luồng nghiệp vụ cụ thể. Nó nêu rõ kịch bản, phạm vi ảnh hưởng, căn cứ chấm điểm, kiểm soát hiện có, khoảng trống và bằng chứng cần thu thập. Từ đó, nhóm phát triển có thể thiết kế phân quyền đúng mức, kiểm tra dữ liệu và trạng thái ở server, giới hạn tài nguyên, bảo vệ dữ liệu, kiểm thử các đường đi bất thường và giám sát những tín hiệu có ý nghĩa.

Mục tiêu cuối cùng không phải tạo ra một con số rủi ro đẹp mắt. Mục tiêu là hiểu điều gì có thể xảy ra, ai sẽ chịu ảnh hưởng, tổ chức có thể mất gì và cần kiểm soát nào để giảm rủi ro đến mức được chấp nhận.

