# Xác định loại dữ liệu và trạng thái cần cho từng mục tiêu

Trong module **VALIDATION_TESTING_STRATEGY**, dữ liệu kiểm thử là một phần của thiết kế kiểm thử. Một trường hợp kiểm thử chỉ có ý nghĩa khi dữ liệu và trạng thái ban đầu phù hợp với mục tiêu cần xác minh. Cùng một API, màn hình hoặc quy trình có thể cho kết quả khác nhau tùy dữ liệu, quyền của người dùng, trạng thái đối tượng, thời điểm và quan hệ với các bản ghi khác.

Vì vậy, không nên chọn dữ liệu chỉ vì dễ tạo hoặc đang có sẵn. Cần xác định **loại dữ liệu nào** và **trạng thái nào** cần có để kiểm tra một hành vi cụ thể. Ví dụ, để xác nhận quy tắc hủy đơn, dữ liệu đơn hàng ở trạng thái chờ thanh toán, đã xác nhận, đang giao và đã hoàn tất có thể dẫn đến các kết quả khác nhau. Để kiểm tra quyền truy cập, cùng một bản ghi cần được thử với người sở hữu, người dùng cùng tổ chức và người dùng ngoài phạm vi.

Bài học này trình bày cách bắt đầu từ mục tiêu kiểm thử, phân loại dữ liệu, xác định trạng thái và quan hệ cần thiết, chọn nguồn tạo dữ liệu, quản lý vòng đời và cô lập dữ liệu, cũng như xây dựng ma trận dữ liệu có thể truy vết. Mục tiêu là tạo được dữ liệu đủ đại diện để kiểm chứng hành vi và rủi ro, có thể lặp lại, an toàn và phù hợp với môi trường.

## 1. Bắt đầu từ mục tiêu kiểm thử

### 1.1. Dữ liệu phục vụ một câu hỏi kiểm thử

Trước khi tạo hoặc chọn dữ liệu, hãy viết rõ điều cần xác minh. Một mục tiêu tốt mô tả hành vi hoặc quy tắc cần được chứng minh.

Ví dụ:

- Xác nhận khách hàng đủ điều kiện có thể đặt sản phẩm còn hàng.
- Xác nhận hệ thống từ chối số lượng lớn hơn tồn kho khả dụng.
- Xác nhận đơn đã giao không thể bị hủy theo luồng hủy thông thường.
- Xác nhận người dùng không thể xem dữ liệu thuộc tenant khác.
- Xác nhận cùng một yêu cầu thanh toán được gửi lại không tạo giao dịch trùng.
- Xác nhận báo cáo tính đúng doanh thu khi có đơn hoàn tiền một phần.

Từ mục tiêu, xác định dữ liệu đầu vào, dữ liệu tham chiếu, trạng thái ban đầu, hành động và kết quả cần quan sát. Không bắt đầu bằng một bộ dữ liệu lớn rồi tìm cách dùng nó cho mọi kiểm thử; cách đó thường tạo ra nhiều dữ liệu thừa và khó biết trường hợp nào đang kiểm tra quy tắc nào.

### 1.2. Phân biệt mục tiêu, dữ liệu và trạng thái

Ba khái niệm cần được ghi riêng:

- **Mục tiêu kiểm thử:** điều cần chứng minh hoặc rủi ro cần phát hiện.
- **Loại dữ liệu:** bản chất và đặc điểm của dữ liệu được sử dụng, chẳng hạn dữ liệu hợp lệ, biên, không hợp lệ, dữ liệu tham chiếu hoặc dữ liệu giao dịch.
- **Trạng thái dữ liệu/đối tượng:** tình trạng tại thời điểm kiểm thử, chẳng hạn mới tạo, đã xác nhận, hết hạn, bị khóa, đã xóa hoặc đang xử lý.

Ví dụ với mục tiêu “người dùng chỉ được hủy đơn của mình”:

- Loại dữ liệu: hai đơn hàng hợp lệ, thuộc hai khách hàng khác nhau.
- Trạng thái: cả hai đơn đang ở trạng thái cho phép hủy.
- Tác nhân: khách A.
- Kiểm tra: khách A hủy đơn của mình thành công, nhưng không thể hủy đơn của khách B.
- Bằng chứng: trạng thái đơn A thay đổi; đơn B không đổi; API không tiết lộ dữ liệu ngoài quyền.

Nếu chỉ tạo một đơn hợp lệ và kiểm tra nút Hủy, chưa thể chứng minh quy tắc quyền sở hữu.

### 1.3. Tách tiền điều kiện khỏi dữ liệu đầu vào

Tiền điều kiện mô tả bối cảnh phải tồn tại trước khi thực hiện. Dữ liệu đầu vào là giá trị hoặc thông tin được cung cấp trong thao tác.

Ví dụ kiểm thử đặt lịch:

- Tiền điều kiện: người dùng đã đăng nhập, dịch vụ đang hoạt động, khung giờ còn chỗ.
- Dữ liệu đầu vào: ngày, giờ, loại dịch vụ và thông tin người đặt.
- Hành động: gửi yêu cầu đặt lịch.
- Kết quả mong đợi: lịch được tạo và số chỗ giảm đúng một.

Một số dữ liệu vừa là tiền điều kiện vừa là đối tượng cần quan sát. Ví dụ, số chỗ ban đầu là tiền điều kiện; số chỗ sau khi đặt là kết quả cần xác minh. Ghi rõ thời điểm đọc để tránh nhầm dữ liệu trước và sau thao tác.

## 2. Phân loại dữ liệu theo mục đích sử dụng

Một bộ kiểm thử thường cần nhiều loại dữ liệu. Không có một phân loại duy nhất phù hợp cho mọi sản phẩm; có thể kết hợp các nhóm dưới đây.

### 2.1. Dữ liệu hợp lệ (valid data)

Dữ liệu hợp lệ đáp ứng schema, quy tắc nghiệp vụ và điều kiện của hành động đang kiểm thử.

Ví dụ:

- Email đúng định dạng và chưa được đăng ký.
- Sản phẩm đang kinh doanh và còn tồn kho.
- Ngày đặt lịch nằm trong khoảng được phép.
- Người dùng có quyền trên tài nguyên.
- Số lượng và giá trị giao dịch nằm trong giới hạn hợp lệ.

Dữ liệu hợp lệ thường dùng để kiểm tra luồng thành công. Tuy nhiên, “hợp lệ” phụ thuộc ngữ cảnh. Một tài khoản có thể hợp lệ để đăng nhập nhưng không đủ quyền phê duyệt giao dịch. Một đơn hàng có thể hợp lệ về cấu trúc nhưng không đủ điều kiện hủy.

### 2.2. Dữ liệu không hợp lệ (invalid data)

Dữ liệu không hợp lệ vi phạm một hoặc nhiều điều kiện được quy định.

Ví dụ:

- Thiếu trường bắt buộc.
- Sai kiểu, sai định dạng hoặc vượt giới hạn.
- Số lượng bằng 0 hoặc âm khi quy tắc yêu cầu số dương.
- Mã giảm giá hết hạn hoặc không tồn tại.
- Ngày kết thúc đứng trước ngày bắt đầu.
- ID tham chiếu đến đối tượng không tồn tại.
- Giá trị trạng thái không thuộc tập cho phép.

Khi kiểm thử dữ liệu không hợp lệ, nên thay đổi một yếu tố chính mỗi lần để xác định rõ quy tắc bị vi phạm. Sau đó bổ sung trường hợp kết hợp nếu cần xác minh hệ thống xử lý nhiều lỗi cùng lúc ra sao.

### 2.3. Dữ liệu biên (boundary data)

Dữ liệu biên nằm tại hoặc sát ranh giới của một quy tắc. Lỗi thường xuất hiện ở điều kiện lớn hơn/nhỏ hơn, số lượng tối thiểu/tối đa, thời hạn hoặc độ dài.

Ví dụ, nếu số lượng được phép từ 1 đến 10, các giá trị cần cân nhắc gồm 0, 1, 2, 9, 10 và 11. Nếu chính sách cho phép hủy trước giờ hẹn ít nhất 12 giờ, hãy kiểm tra ngay dưới 12 giờ, đúng 12 giờ và ngay trên 12 giờ theo đơn vị thời gian phù hợp.

Dữ liệu biên cần ghi rõ đơn vị, cách làm tròn, múi giờ và việc ranh giới có bao gồm hay không. Không nên tự suy diễn điều kiện tại biên nếu yêu cầu chưa được xác nhận.

### 2.4. Dữ liệu tham chiếu và dữ liệu danh mục

Dữ liệu tham chiếu (reference data) mô tả các giá trị được nhiều giao dịch sử dụng, ví dụ:

- Loại sản phẩm, nhóm dịch vụ và danh mục.
- Mã tiền tệ, đơn vị đo và khu vực.
- Vai trò, nhóm quyền và loại tài khoản.
- Trạng thái được phép và mã phân loại.
- Thuế suất, chính sách phí hoặc cấu hình theo vùng.

Dữ liệu tham chiếu cần nhất quán với phiên bản và cấu hình của môi trường. Một kiểm thử có thể thất bại vì danh mục hoặc mã vùng chưa được nạp, chứ không phải vì logic của chức năng sai.

### 2.5. Dữ liệu giao dịch và dữ liệu lịch sử

Dữ liệu giao dịch (transactional data) phát sinh từ hoạt động nghiệp vụ, chẳng hạn đơn hàng, thanh toán, đặt lịch, yêu cầu hỗ trợ hoặc bản ghi kiểm toán.

Dữ liệu lịch sử có thể cần để kiểm tra:

- Truy vấn và báo cáo theo khoảng thời gian.
- Đọc dữ liệu được tạo bởi phiên bản cũ.
- Chuyển đổi hoặc migration.
- Trạng thái đã hoàn tất, đã hủy hoặc đã lưu trữ.
- Đối soát và tính toán theo lịch sử giao dịch.

Cần xác định dữ liệu lịch sử có còn được chỉnh sửa hay chỉ được đọc, có chịu quy tắc mới hay giữ nguyên cách diễn giải tại thời điểm tạo.

### 2.6. Dữ liệu quan hệ và dữ liệu phụ thuộc

Nhiều hành vi không thể kiểm tra bằng một bản ghi đơn lẻ. Cần tạo các quan hệ như:

- Khách hàng – đơn hàng – dòng sản phẩm.
- Người dùng – vai trò – quyền – tenant.
- Đơn hàng – thanh toán – hoàn tiền.
- Lịch hẹn – khung giờ – nhân viên – địa điểm.
- Sự kiện – consumer – kết quả xử lý.

Ví dụ, để kiểm tra tổng tiền đơn hàng, cần có đơn, các dòng sản phẩm, giá áp dụng, giảm giá, thuế và phí. Nếu thiếu một quan hệ, kết quả có thể không đại diện cho tình huống thực.

### 2.7. Dữ liệu nhạy cảm và dữ liệu cần bảo vệ

Dữ liệu có thể chứa thông tin cá nhân, tài chính, xác thực, bí mật kinh doanh hoặc dữ liệu được quy định bảo vệ. Phân loại dữ liệu theo mức nhạy cảm trước khi dùng.

Các cách tạo dữ liệu thường gặp:

- Dữ liệu tổng hợp được tạo mới.
- Dữ liệu giả lập với định danh không thuộc người thật.
- Dữ liệu đã ẩn danh hoặc biến đổi theo quy trình được phê duyệt.
- Dữ liệu sản xuất được cấp quyền sử dụng trong phạm vi đặc biệt, có kiểm soát.

Không sao chép dữ liệu sản xuất vào môi trường kiểm thử chỉ vì thuận tiện. Cần tuân thủ chính sách, quyền truy cập, mục đích sử dụng, vị trí lưu trữ và thời hạn lưu. Che tên hoặc email chưa chắc đã ẩn danh nếu các trường khác vẫn có thể liên kết để nhận diện cá nhân.

## 3. Phân loại trạng thái cần kiểm tra

Loại dữ liệu cho biết dữ liệu có đặc điểm gì; trạng thái cho biết đối tượng đang ở giai đoạn hoặc tình trạng nào. Cùng một bản ghi có thể hợp lệ về cấu trúc nhưng ở trạng thái không cho phép thao tác.

### 3.1. Trạng thái vòng đời

Một đối tượng nghiệp vụ thường đi qua nhiều trạng thái:

- Chưa tồn tại.
- Đã tạo hoặc mới khởi tạo.
- Đang chờ xác nhận.
- Đã xác nhận hoặc đang hoạt động.
- Đang xử lý.
- Hoàn tất.
- Bị từ chối.
- Bị hủy.
- Hết hạn.
- Bị khóa hoặc tạm ngưng.
- Đã lưu trữ hoặc xóa mềm.

Không phải đối tượng nào cũng có đủ các trạng thái này. Hãy dùng mô hình trạng thái được định nghĩa cho miền nghiệp vụ và xác định trạng thái nào liên quan đến mục tiêu kiểm thử.

### 3.2. Trạng thái hợp lệ và trạng thái không cho phép thao tác

Với mỗi hành động, lập bảng trạng thái hiện tại và kết quả được phép.

Ví dụ với đơn hàng:

| Trạng thái hiện tại | Hành động hủy | Kết quả cần xác minh |
|---|---|---|
| DRAFT | Hủy | Hủy hoặc xóa bản nháp theo chính sách |
| PENDING_PAYMENT | Hủy | Chuyển trạng thái và giải phóng giữ chỗ nếu có |
| CONFIRMED | Hủy | Cho phép hoặc yêu cầu quy trình hủy riêng |
| SHIPPED | Hủy | Từ chối hoặc chuyển sang quy trình trả hàng |
| COMPLETED | Hủy | Không cho hủy theo luồng thông thường |
| CANCELLED | Hủy lần nữa | Hành vi lặp phải nhất quán, không tạo tác dụng phụ mới |

Bảng chỉ minh họa cách tổ chức. Trạng thái và hành động thực tế phải được xác nhận theo quy tắc của sản phẩm.

### 3.3. Trạng thái theo thời gian

Một số quy tắc phụ thuộc vào thời điểm:

- Chưa đến hạn, đúng hạn hoặc quá hạn.
- Token còn hiệu lực hoặc hết hạn.
- Phiên đăng nhập đang hoạt động hoặc đã hết hạn.
- Khuyến mãi chưa bắt đầu, đang hiệu lực hoặc đã kết thúc.
- Lịch hẹn trong tương lai, đang diễn ra hoặc đã qua.
- Dữ liệu mới, cũ hoặc quá thời gian lưu trữ.

Khi tạo dữ liệu theo thời gian, tránh phụ thuộc vào đồng hồ thực của máy nếu có thể kiểm soát clock hoặc dùng timestamp cố định trong môi trường thử. Ghi rõ múi giờ và thời điểm tham chiếu để kết quả có thể tái tạo.

### 3.4. Trạng thái về quyền và sở hữu

Đối với kiểm thử phân quyền, trạng thái không chỉ là trạng thái nghiệp vụ mà còn gồm quan hệ giữa người gọi và tài nguyên:

- Người sở hữu.
- Người cùng tổ chức hoặc tenant.
- Người được chia sẻ quyền.
- Người có vai trò quản trị.
- Người không có quyền.
- Tài khoản bị khóa hoặc thu hồi quyền.
- Tài khoản đã đăng nhập nhưng phiên hoặc token không còn hợp lệ.

Một ma trận dữ liệu quyền cần có cả người gọi và tài nguyên. Chỉ tạo nhiều tài khoản mà không xác định quan hệ sở hữu sẽ khó kiểm tra đúng phạm vi truy cập.

### 3.5. Trạng thái xử lý bất đồng bộ và không chắc chắn

Với hệ thống dùng hàng đợi hoặc dịch vụ ngoài, đối tượng có thể ở trạng thái:

- Đang chờ xử lý.
- Đã gửi nhưng chưa nhận phản hồi.
- Đang thử lại.
- Xử lý thành công.
- Thất bại có thể thử lại.
- Thất bại cuối cùng.
- Kết quả chưa xác định do timeout.
- Đang đối soát hoặc chờ can thiệp.

Các trạng thái này quan trọng khi kiểm thử retry, idempotency, webhook và phục hồi. Không nên giả định một thao tác timeout đồng nghĩa với việc chưa có tác dụng phụ. Dữ liệu cần đủ để xác định liệu hệ thống đã xử lý, đang xử lý hay chưa xử lý.

## 4. Liên kết mục tiêu với loại dữ liệu và trạng thái

### 4.1. Ma trận mục tiêu – dữ liệu – trạng thái

Một ma trận giúp chuyển mục tiêu kiểm thử thành các bộ dữ liệu có chủ đích.

| Mục tiêu kiểm thử | Loại dữ liệu cần có | Trạng thái cần có | Kết quả chính cần quan sát |
|---|---|---|---|
| Tạo đơn thành công | Khách và sản phẩm hợp lệ, tồn kho đủ | Sản phẩm đang bán, giỏ hợp lệ | Đơn được tạo và tổng tiền đúng |
| Từ chối vượt tồn kho | Sản phẩm có tồn kho giới hạn, số lượng vượt mức | Sản phẩm đang bán nhưng không đủ hàng | Không xác nhận đơn vượt số lượng |
| Kiểm tra giới hạn số lượng | Dữ liệu tại min/max và sát biên | Sản phẩm còn khả dụng | Chấp nhận hoặc từ chối đúng tại biên |
| Hủy đơn theo chính sách | Đơn có thông tin thanh toán và giao hàng | Các trạng thái trước/sau giao hàng | Chuyển trạng thái và tác dụng phụ đúng |
| Kiểm tra quyền truy cập | Nhiều người dùng và tài nguyên có chủ sở hữu | Tài khoản hoạt động, bị khóa hoặc thiếu quyền | Cho phép đúng phạm vi và từ chối phần còn lại |
| Retry thanh toán | Yêu cầu có idempotency key và giao dịch tham chiếu | Thành công, timeout, đang xử lý hoặc chưa xác định | Không tạo giao dịch trùng |
| Báo cáo doanh thu | Đơn, thanh toán, hủy và hoàn tiền | Hoàn tất, hoàn một phần, hủy | Tổng hợp đúng theo quy tắc |
| Migration dữ liệu | Bản ghi cũ, thiếu trường hoặc giá trị cũ | Trạng thái trước migration | Dữ liệu sau chuyển đổi giữ đúng ý nghĩa |

Ma trận này là điểm khởi đầu. Với mục tiêu quan trọng, có thể cần nhiều bộ dữ liệu để tách từng quy tắc và từng trạng thái.

### 4.2. Xác định dữ liệu tối thiểu để chứng minh một quy tắc

Dùng tập dữ liệu nhỏ nhất vẫn đủ chứng minh hành vi. Ví dụ, để xác nhận một người không thể xem đơn của người khác, chỉ cần:

- Hai người dùng khác nhau.
- Hai đơn hàng có quan hệ sở hữu rõ.
- Một phiên xác thực của người dùng thứ nhất.
- Một yêu cầu đọc đơn của chính họ và một yêu cầu đọc đơn của người còn lại.

Tập dữ liệu này dễ hiểu và cô lập mục tiêu. Khi cần kiểm tra nhiều tenant, vai trò hoặc trạng thái tài khoản, mở rộng thành ma trận riêng.

### 4.3. Tránh dữ liệu thừa và phụ thuộc ngầm

Dữ liệu thừa làm tăng thời gian chuẩn bị và gây khó chẩn đoán. Phụ thuộc ngầm xuất hiện khi kiểm thử chỉ chạy được vì một bản ghi cũ, một tài khoản chia sẻ hoặc thứ tự chạy trước đó.

Để hạn chế:

- Ghi rõ bản ghi nào được tạo bởi kiểm thử.
- Khai báo quan hệ và tiền điều kiện.
- Tạo dữ liệu theo từng lần chạy hoặc từng test case khi cần.
- Không dựa vào ID cố định nếu môi trường có thể bị làm mới.
- Không giả định dữ liệu từ kiểm thử khác vẫn tồn tại.
- Xác minh dữ liệu trước khi chạy và sau khi dọn.

## 5. Chọn nguồn và phương pháp tạo dữ liệu

### 5.1. Dữ liệu tổng hợp

Dữ liệu tổng hợp được tạo mới để phục vụ kiểm thử, không sao chép trực tiếp thông tin cá nhân thật.

Ưu điểm:

- Có thể tạo theo tình huống và giá trị biên.
- Dễ lặp lại và cô lập.
- Có thể tạo khối lượng lớn.
- Giảm rủi ro lộ dữ liệu nếu được thiết kế đúng.

Giới hạn:

- Có thể không phản ánh phân bố, độ lệch hoặc quan hệ phức tạp của dữ liệu thực.
- Có thể bỏ sót đặc điểm dữ liệu cũ hoặc dữ liệu lỗi.
- Cần hiểu quy tắc để tạo dữ liệu có tính đại diện.

Dữ liệu tổng hợp cần tuân thủ schema và các bất biến nghiệp vụ. Một tập dữ liệu ngẫu nhiên nhưng không nhất quán không giúp kiểm thử tốt.

### 5.2. Dữ liệu đã ẩn danh hoặc biến đổi

Khi cần đặc tính gần với dữ liệu thực, tổ chức có thể dùng dữ liệu đã được ẩn danh, giả danh hoặc biến đổi theo quy trình được phê duyệt.

Cần xem xét:

- Khả năng tái nhận diện khi kết hợp nhiều trường.
- Quan hệ giữa các bản ghi có được bảo toàn không.
- Phân bố và giá trị biên có còn đại diện không.
- Dữ liệu có giữ được ràng buộc tham chiếu không.
- Các trường nhạy cảm có được xử lý đúng chính sách không.
- Ai có quyền tạo, truy cập và lưu bản dữ liệu.

Không nên tự coi dữ liệu đã che một vài trường là dữ liệu an toàn. Việc xử lý cần tuân theo quy định và hướng dẫn của tổ chức.

### 5.3. Fixture, factory và builder

Các kỹ thuật phổ biến để tạo dữ liệu:

- **Fixture:** tập dữ liệu được chuẩn bị trước, thường dùng cho tình huống ổn định.
- **Factory:** hàm hoặc công cụ tạo đối tượng với giá trị mặc định hợp lệ và cho phép tùy chỉnh.
- **Builder:** cách xây dựng đối tượng phức tạp qua các bước có tên rõ.
- **Seed data:** dữ liệu tham chiếu ban đầu được nạp vào môi trường.
- **Generator:** công cụ sinh dữ liệu theo quy tắc hoặc phân bố.

Ví dụ giả mã:

```text
order = OrderFactory.create(
    customer = CustomerFactory.active(),
    status = PENDING_PAYMENT,
    items = [ProductFactory.inStock(quantity = 3)],
    payment = PaymentFactory.notStarted()
)
```

Cách tạo này giúp người đọc hiểu trạng thái và mục đích của dữ liệu. Factory nên tạo dữ liệu hợp lệ mặc định; các trường hợp sai hoặc biên nên được thể hiện rõ trong test case thay vì bị ẩn trong cấu hình khó hiểu.

### 5.4. Dùng API tạo dữ liệu khi phù hợp

Tạo dữ liệu qua API nghiệp vụ có thể giúp bảo đảm các quy tắc và quan hệ được áp dụng như hệ thống thật. Tuy nhiên, cách này có thể chậm và khó tạo trạng thái đặc biệt.

Có thể kết hợp:

- API hoặc giao diện để tạo đối tượng ở trạng thái hợp lệ thông thường.
- Cơ chế test-only hoặc fixture được phê duyệt để tạo trạng thái hiếm.
- API quản trị hoặc công cụ seed để chuẩn bị dữ liệu tham chiếu.
- Truy vấn read-only để xác minh kết quả.

Không nên ghi trực tiếp vào cơ sở dữ liệu để tạo trạng thái nếu thao tác đó bỏ qua bất biến quan trọng hoặc không được phép. Nếu cần tạo trạng thái đặc biệt bằng cách trực tiếp, phải ghi rõ giới hạn và bảo đảm dữ liệu vẫn nhất quán.

### 5.5. Dữ liệu từ hệ thống bên ngoài

Với API đối tác hoặc sandbox, dữ liệu có thể do nhà cung cấp kiểm soát. Cần xác định:

- Bộ tài khoản và giá trị thử được hỗ trợ.
- Các phản hồi đặc biệt hoặc mã lỗi có thể kích hoạt.
- Cách làm mới trạng thái.
- Giới hạn số lần gọi.
- Thời gian lưu dữ liệu và giao dịch thử.
- Sự khác biệt giữa sandbox và sản xuất.

Nếu sandbox không hỗ trợ một tình huống, có thể dùng service virtualization để kiểm tra logic ứng dụng và ghi rõ phần tích hợp chưa được xác nhận.

## 6. Quản lý trạng thái và chuyển trạng thái

### 6.1. Mô hình hóa trạng thái trước khi tạo dữ liệu

Với đối tượng có vòng đời, lập sơ đồ hoặc bảng chuyển trạng thái. Ví dụ:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> PendingPayment: Submit
    PendingPayment --> Confirmed: PaymentSuccess
    PendingPayment --> Cancelled: Cancel
    Confirmed --> Processing: StartFulfillment
    Processing --> Shipped: Dispatch
    Shipped --> Completed: DeliveryConfirmed
    Confirmed --> Cancelled: CancelAllowed
    Completed --> [*]
    Cancelled --> [*]
~~~

Sơ đồ chỉ minh họa một luồng đơn giản. Mô hình thật có thể có trạng thái thất bại, hoàn tiền, trả hàng hoặc chờ đối soát. Hãy xác định rõ trạng thái hợp lệ, sự kiện chuyển đổi và tác nhân được phép.

### 6.2. Chuẩn bị dữ liệu cho từng trạng thái

Có thể tạo một bộ dữ liệu đại diện:

| ID dữ liệu | Đối tượng | Trạng thái ban đầu | Mục tiêu kiểm thử |
|---|---|---|---|
| ORD-01 | Đơn hàng | DRAFT | Kiểm tra gửi đơn |
| ORD-02 | Đơn hàng | PENDING_PAYMENT | Kiểm tra thanh toán hoặc hủy |
| ORD-03 | Đơn hàng | CONFIRMED | Kiểm tra xử lý và hủy theo chính sách |
| ORD-04 | Đơn hàng | SHIPPED | Kiểm tra không hủy theo luồng thông thường |
| ORD-05 | Đơn hàng | COMPLETED | Kiểm tra hành vi sau hoàn tất |
| ORD-06 | Đơn hàng | CANCELLED | Kiểm tra thao tác lặp và tính bất biến |

Không cần tạo tất cả trạng thái cho mọi test case. Chọn những trạng thái có thể thay đổi kết quả của hành động đang kiểm tra.

### 6.3. Kiểm tra chuyển trạng thái hợp lệ và không hợp lệ

Với mỗi trạng thái, kiểm tra:

- Sự kiện nào được phép?
- Vai trò nào được thực hiện?
- Điều kiện dữ liệu nào phải thỏa?
- Trạng thái đích là gì?
- Có tác dụng phụ nào phải xảy ra?
- Sự kiện lặp có tạo thêm tác dụng phụ không?
- Chuyển trạng thái không hợp lệ được từ chối ra sao?

Một bảng chuyển trạng thái có thể trở thành nguồn tạo test case. Cần kiểm tra cả trạng thái đích và dữ liệu liên quan, không chỉ response của API.

### 6.4. Trạng thái dữ liệu không nhất quán hoặc một phần

Một số tình huống cần dữ liệu có trạng thái trung gian hoặc không nhất quán có kiểm soát:

- Đơn đã tạo nhưng thanh toán chưa có kết quả.
- Giao dịch đã xử lý nhưng webhook chưa đến.
- Event đã phát nhưng consumer chưa cập nhật dữ liệu.
- Một phần bản ghi đã được ghi trước khi bước sau thất bại.
- Bản ghi tham chiếu đã bị xóa hoặc chuyển trạng thái.
- Cache chứa giá trị cũ so với database.

Các trường hợp này hữu ích cho kiểm thử phục hồi, đối soát và tính nhất quán. Cần tạo trong môi trường riêng và có cách dọn, vì dữ liệu không nhất quán có thể ảnh hưởng các kiểm thử khác.

## 7. Bao phủ dữ liệu mà không tạo tổ hợp quá lớn

### 7.1. Phân vùng tương đương

Chia dữ liệu thành các nhóm được kỳ vọng xử lý giống nhau, rồi chọn đại diện.

Ví dụ, số lượng mua hợp lệ từ 1 đến 10:

- Nhóm không hợp lệ thấp: nhỏ hơn 1.
- Nhóm hợp lệ: từ 1 đến 10.
- Nhóm không hợp lệ cao: lớn hơn 10.

Chọn một hoặc nhiều đại diện trong từng nhóm, sau đó bổ sung kiểm tra biên khi rủi ro yêu cầu.

### 7.2. Phân tích giá trị biên

Với giới hạn từ 1 đến 10, có thể kiểm tra 0, 1, 2, 9, 10 và 11. Với thời hạn, cần kiểm tra trước, đúng tại và sau ngưỡng. Với trường văn bản, cần kiểm tra độ dài 0, giới hạn tối đa và vượt giới hạn.

### 7.3. Bảng quyết định

Khi kết quả phụ thuộc nhiều điều kiện, dùng bảng quyết định để tránh bỏ sót tổ hợp.

Ví dụ áp dụng mã giảm giá:

| Khách đủ điều kiện | Mã còn hiệu lực | Đơn đạt giá trị tối thiểu | Kết quả |
|---|---|---|---|
| Có | Có | Có | Áp dụng mã |
| Có | Có | Không | Từ chối do chưa đạt giá trị tối thiểu |
| Có | Không | Có | Từ chối do mã hết hạn |
| Không | Có | Có | Từ chối do nhóm khách không đủ điều kiện |
| Không | Không | Không | Từ chối; kiểm tra thứ tự hoặc ưu tiên thông báo theo quy tắc |

Không phải mọi tổ hợp đều cần một test riêng nếu có thể chứng minh bằng kỹ thuật phù hợp. Nhưng các điều kiện và ưu tiên lỗi phải được thống nhất.

### 7.4. Pairwise và tổ hợp theo rủi ro

Khi có nhiều chiều dữ liệu như vai trò, trình duyệt, trạng thái, khu vực và phương thức thanh toán, toàn bộ tổ hợp có thể tăng rất nhanh. Có thể dùng pairwise hoặc thiết kế tổ hợp theo rủi ro để bảo đảm các cặp giá trị quan trọng xuất hiện ít nhất một lần.

Pairwise không thay thế kiểm thử các tổ hợp có hậu quả cao. Nếu một quy tắc phụ thuộc vào ba điều kiện cùng lúc hoặc một tổ hợp cụ thể có rủi ro nghiêm trọng, cần thêm trường hợp có chủ đích.

### 7.5. Bao phủ theo trạng thái và chuyển đổi

Với đối tượng có vòng đời, cân nhắc các mức:

- Bao phủ mọi trạng thái quan trọng.
- Bao phủ mọi chuyển đổi hợp lệ.
- Bao phủ các chuyển đổi không hợp lệ có rủi ro cao.
- Bao phủ sự kiện lặp hoặc đồng thời.
- Bao phủ trạng thái phục hồi và trạng thái chưa xác định.

Không nhất thiết kiểm tra mọi đường đi có thể có nếu số lượng quá lớn. Ưu tiên đường đi ảnh hưởng đến dữ liệu, quyền, tiền hoặc hành trình cốt lõi.

## 8. Quản lý vòng đời dữ liệu kiểm thử

### 8.1. Tạo, sử dụng, làm mới và dọn dữ liệu

Một vòng đời cơ bản:

~~~mermaid
flowchart TD
    A[Xác định mục tiêu và yêu cầu dữ liệu] --> B[Tạo hoặc nạp dữ liệu]
    B --> C[Kiểm tra tiền điều kiện]
    C --> D[Thực thi test]
    D --> E[Thu thập bằng chứng]
    E --> F{Cần giữ lại?}
    F -- Có --> G[Đánh dấu và bảo vệ dữ liệu]
    F -- Không --> H[Dọn hoặc đặt lại trạng thái]
    G --> I[Rà soát thời hạn lưu]
    H --> J[Kiểm tra không còn tác dụng phụ]
~~~

Dữ liệu nên được tạo ngay trước khi cần hoặc lấy từ fixture được quản lý. Sau khi chạy, dọn dữ liệu theo chính sách và xác nhận việc dọn không xóa nhầm dữ liệu dùng chung.

### 8.2. Cô lập giữa các test case

Để tránh phụ thuộc và xung đột:

- Dùng định danh duy nhất theo test run.
- Tạo tài khoản hoặc tenant riêng khi cần.
- Không dùng chung một đơn hàng có trạng thái bị thay đổi giữa nhiều test.
- Đặt lại trạng thái trước mỗi trường hợp cần dữ liệu ban đầu.
- Tránh phụ thuộc vào thứ tự thực thi.
- Quản lý khóa hoặc giới hạn tài nguyên khi chạy song song.
- Ghi quan hệ giữa dữ liệu và test ID.

Nếu một test cần dữ liệu do test khác tạo, hãy xem đó là một chuỗi có chủ đích và ghi rõ phụ thuộc; nếu không, mỗi test nên tự chuẩn bị điều kiện của mình.

### 8.3. Dọn dữ liệu an toàn

Cần xác định:

- Dữ liệu nào được phép xóa.
- Dữ liệu nào phải giữ để điều tra.
- Có thể dùng API dọn dữ liệu hay cần quy trình quản trị.
- Quan hệ phụ thuộc có khiến xóa một bản ghi ảnh hưởng bản ghi khác không.
- Dữ liệu có đang được test chạy song song sử dụng không.
- Có thời hạn lưu và quyền truy cập phù hợp không.

Ưu tiên xóa theo mã test run hoặc namespace riêng. Không chạy lệnh dọn trên dữ liệu sản xuất hoặc dữ liệu dùng chung nếu không có phê duyệt và phạm vi chính xác.

### 8.4. Dữ liệu không ổn định theo thời gian

Dữ liệu có thể tự thay đổi do job nền, đồng bộ, lịch hết hạn hoặc người dùng khác. Để kiểm soát:

- Dùng clock giả lập hoặc timestamp cố định nếu hệ thống hỗ trợ.
- Tắt hoặc cô lập job nền trong test chuyên biệt khi phù hợp.
- Chọn khoảng thời gian đủ xa ngưỡng nếu mục tiêu không phải kiểm tra biên.
- Ghi thời điểm tạo và thời hạn hiệu lực.
- Kiểm tra trạng thái ngay trước khi chạy.
- Dùng cơ chế khóa hoặc snapshot khi cần bảo đảm tính nhất quán.

## 9. Dữ liệu cho kiểm thử tích hợp, E2E và hiệu năng

### 9.1. Kiểm thử tích hợp

Dữ liệu tích hợp cần phản ánh quan hệ giữa các dịch vụ:

- ID và khóa tham chiếu nhất quán.
- Schema và phiên bản hợp đồng phù hợp.
- Trạng thái giữa provider và consumer có thể đối soát.
- Dữ liệu đầu vào bao phủ phản hồi thành công và lỗi.
- Có mã tương quan để truy vết.
- Có dữ liệu cho timeout, retry và sự kiện lặp nếu cần.

Khi một dịch vụ được mock, cần ghi rõ dữ liệu và hành vi nào do mock tạo ra.

### 9.2. Kiểm thử E2E

Dữ liệu E2E nên đại diện cho hành trình thực tế và đủ độc lập để chạy lặp lại:

- Người dùng có vai trò và quyền phù hợp.
- Đối tượng nghiệp vụ có quan hệ đầy đủ.
- Dịch vụ phụ thuộc ở trạng thái đã biết.
- Dữ liệu có thể nhận diện theo lần chạy.
- Có thể xác minh kết quả cuối tại nguồn có thẩm quyền.
- Có cách dọn hoặc đặt lại trạng thái.

Không nên dùng một bộ dữ liệu lớn dùng chung cho tất cả hành trình nếu các kịch bản có thể thay đổi lẫn nhau.

### 9.3. Kiểm thử hiệu năng

Dữ liệu hiệu năng cần đại diện cho kích thước, phân bố và quan hệ dữ liệu mà hệ thống sẽ xử lý. Một cơ sở dữ liệu chỉ có vài bản ghi không phản ánh chi phí truy vấn trên dữ liệu lớn.

Cần xem xét:

- Số lượng bản ghi và phân bố theo thời gian.
- Tỷ lệ dữ liệu nóng/lạnh.
- Độ dài và độ đa dạng của trường.
- Mức độ liên kết giữa bảng hoặc đối tượng.
- Tỷ lệ đọc/ghi và mẫu truy vấn.
- Trạng thái cache và dữ liệu tham chiếu.
- Tác động của dữ liệu trùng, lệch hoặc phân bố không đồng đều.

Không dùng dữ liệu cá nhân thật chỉ để đạt kích thước. Có thể sinh dữ liệu tổng hợp theo phân bố và quan hệ gần với thực tế, đồng thời ghi rõ giới hạn của mô hình.

## 10. Ví dụ tổng hợp: kiểm tra đơn hàng và hoàn tiền

Giả sử mục tiêu là xác nhận hệ thống tính đúng số tiền hoàn và không hoàn vượt số tiền đã thu.

### 10.1. Xác định loại dữ liệu

Cần có:

- Khách hàng hợp lệ và tài khoản có quyền yêu cầu hoàn.
- Đơn hàng có một hoặc nhiều dòng sản phẩm.
- Giá, thuế, phí và chiết khấu.
- Giao dịch thanh toán gốc.
- Một hoặc nhiều giao dịch hoàn trước đó.
- Chính sách hoàn tiền theo trạng thái và loại sản phẩm.

### 10.2. Xác định trạng thái

| Bộ dữ liệu | Trạng thái đơn | Trạng thái thanh toán | Mục tiêu |
|---|---|---|---|
| REF-01 | CONFIRMED | CAPTURED | Hoàn toàn phần khi đủ điều kiện |
| REF-02 | COMPLETED | CAPTURED | Kiểm tra chính sách sau hoàn tất |
| REF-03 | CONFIRMED | PARTIALLY_REFUNDED | Hoàn tiếp phần còn lại |
| REF-04 | CANCELLED | REFUNDED | Không hoàn vượt số đã thu |
| REF-05 | CONFIRMED | PENDING | Từ chối hoặc chờ kết quả thanh toán theo chính sách |
| REF-06 | CONFIRMED | REFUND_PENDING | Kiểm tra retry và đối soát |

### 10.3. Tạo dữ liệu và kết quả mong đợi

Giả sử đơn có tổng số tiền đã thu là 500.000, đã hoàn 100.000 và số tiền còn đủ điều kiện hoàn tối đa là 400.000 theo chính sách.

Các trường hợp:

- Yêu cầu hoàn 200.000: chấp nhận nếu các điều kiện khác hợp lệ; tổng đã hoàn thành 300.000.
- Yêu cầu hoàn 400.000 tiếp theo: từ chối nếu vượt phần còn lại.
- Gửi lại cùng yêu cầu sau timeout: không tạo giao dịch hoàn trùng.
- Giao dịch hoàn đang chờ: không tính là hoàn tất nếu hợp đồng phân biệt trạng thái pending và completed.
- Người không có quyền: từ chối và không làm thay đổi giao dịch.

Kết quả cần đối chiếu giữa đơn hàng, giao dịch gốc, giao dịch hoàn và báo cáo. Chỉ kiểm tra thông báo “Yêu cầu hoàn thành công” là chưa đủ.

## 11. Ghi nhận dữ liệu và khả năng truy vết

### 11.1. Mẫu danh mục dữ liệu kiểm thử

| Trường | Ý nghĩa |
|---|---|
| Data ID | Mã dữ liệu duy nhất |
| Test objective / Test ID | Mục tiêu hoặc trường hợp sử dụng dữ liệu |
| Data type | Hợp lệ, không hợp lệ, biên, tham chiếu, giao dịch, nhạy cảm... |
| Entity | Đối tượng nghiệp vụ |
| Initial state | Trạng thái trước khi chạy |
| Relationships | Quan hệ với người dùng hoặc đối tượng khác |
| Source | Tổng hợp, fixture, factory, API, sandbox hoặc nguồn được phê duyệt |
| Environment | Môi trường được phép sử dụng |
| Expected transition | Trạng thái mong đợi sau hành động |
| Evidence | Cách xác minh dữ liệu và kết quả |
| Owner | Người hoặc nhóm chịu trách nhiệm |
| Lifecycle | Cách tạo, làm mới, giữ lại và dọn |
| Sensitivity | Mức phân loại và biện pháp bảo vệ |

### 11.2. Liên kết dữ liệu với kiểm thử

Một chuỗi truy vết hữu ích:

~~~text
Mục tiêu kiểm thử
    -> Quy tắc nghiệp vụ
        -> Loại dữ liệu và trạng thái
            -> Test data ID
                -> Test case
                    -> Kết quả và bằng chứng
~~~

Ví dụ:

| Mục tiêu | Dữ liệu | Trạng thái | Test case | Bằng chứng |
|---|---|---|---|---|
| Không mua vượt tồn kho | Sản phẩm có 2 đơn vị, yêu cầu 3 | ACTIVE / IN_STOCK | TC-INV-02 | Response và tồn kho sau chạy |
| Không hủy đơn đã giao | Đơn có người nhận và mã vận đơn | SHIPPED | TC-ORD-08 | Trạng thái không đổi và lỗi theo hợp đồng |
| Không truy cập tenant khác | Hai tenant và hai tài khoản | ACTIVE | TC-AUTH-05 | Không có dữ liệu trả về và bản ghi không đổi |
| Không hoàn trùng | Một giao dịch gốc và idempotency key | REFUND_PENDING | TC-PAY-11 | Số giao dịch hoàn và trạng thái cuối |

### 11.3. Ghi phiên bản và khả năng tái tạo

Để tái hiện một lần chạy, lưu các thông tin cần thiết:

- Phiên bản ứng dụng và schema.
- Phiên bản fixture hoặc factory.
- Mã test run và Data ID.
- Môi trường, cấu hình và thời điểm.
- Seed hoặc cách tạo dữ liệu.
- Trạng thái trước và sau.
- Mã tương quan hoặc tham chiếu bằng chứng.

Không lưu secret hoặc dữ liệu nhạy cảm trong repository nếu không được phép. Có thể lưu cách tạo dữ liệu và ID tham chiếu trong khi dữ liệu thực được quản lý ở hệ thống bảo mật phù hợp.

## 12. Những sai lầm thường gặp

1. **Dùng một bộ dữ liệu cho mọi mục tiêu:** dữ liệu không thể hiện đúng điều kiện của từng quy tắc.
2. **Chỉ tạo dữ liệu hợp lệ:** bỏ sót dữ liệu biên, không hợp lệ và trạng thái bất thường.
3. **Không phân biệt loại dữ liệu với trạng thái:** biết giá trị nhưng không biết đối tượng đang ở giai đoạn nào.
4. **Bỏ qua quan hệ giữa bản ghi:** kiểm thử từng đối tượng riêng lẻ nhưng không xác minh ràng buộc nghiệp vụ.
5. **Dùng dữ liệu cố định chia sẻ:** các test ghi đè hoặc làm thay đổi trạng thái của nhau.
6. **Phụ thuộc vào thứ tự chạy:** test chỉ đạt khi một test khác đã tạo dữ liệu trước đó.
7. **Dùng dữ liệu sản xuất không kiểm soát:** tạo rủi ro về quyền riêng tư, bảo mật và tuân thủ.
8. **Tạo trạng thái bằng cách bỏ qua bất biến:** dữ liệu test không thể tồn tại trong điều kiện thực tế nhưng lại được dùng làm bằng chứng.
9. **Không kiểm tra dữ liệu trước khi chạy:** môi trường thay đổi khiến tiền điều kiện không còn đúng.
10. **Không dọn dữ liệu:** làm ô nhiễm môi trường và gây lỗi cho các lần chạy sau.
11. **Dùng dữ liệu quá nhỏ cho kiểm thử hiệu năng:** kết quả không đại diện cho quy mô thực tế.
12. **Không ghi nguồn và phiên bản dữ liệu:** không thể tái tạo hoặc giải thích kết quả.

## 13. Checklist xác định loại dữ liệu và trạng thái cần cho từng mục tiêu

- [ ] Mục tiêu kiểm thử và quy tắc cần xác minh đã được mô tả rõ.
- [ ] Đã xác định tiền điều kiện, dữ liệu đầu vào và kết quả cần quan sát.
- [ ] Đã phân loại dữ liệu hợp lệ, không hợp lệ, biên và dữ liệu tham chiếu cần thiết.
- [ ] Đã xác định dữ liệu giao dịch, lịch sử và quan hệ giữa các đối tượng.
- [ ] Đã liệt kê trạng thái ban đầu và trạng thái đích liên quan.
- [ ] Đã xem xét trạng thái theo thời gian, quyền sở hữu, xử lý bất đồng bộ và trạng thái chưa xác định.
- [ ] Dữ liệu được chọn đủ để chứng minh mục tiêu nhưng không có phụ thuộc thừa.
- [ ] Nguồn dữ liệu, fixture, factory hoặc cách sinh dữ liệu được xác định.
- [ ] Dữ liệu nhạy cảm được phân loại và xử lý theo chính sách.
- [ ] Dữ liệu được cô lập giữa các test case và lần chạy song song.
- [ ] Có quy trình tạo, làm mới, giữ lại và dọn dữ liệu an toàn.
- [ ] Đã chọn kỹ thuật bao phủ phù hợp như phân vùng tương đương, giá trị biên hoặc bảng quyết định.
- [ ] Dữ liệu tích hợp, E2E và hiệu năng có tính đại diện phù hợp với mục tiêu.
- [ ] Data ID được liên kết với test case, trạng thái và bằng chứng.
- [ ] Có đủ thông tin để tái tạo kết quả và điều tra sai lệch.

Xác định đúng loại dữ liệu và trạng thái giúp mỗi trường hợp kiểm thử phản ánh một điều kiện nghiệp vụ cụ thể. Khi dữ liệu được chọn từ mục tiêu, có quan hệ và vòng đời rõ ràng, được cô lập và truy vết đầy đủ, nhóm có thể kiểm tra hành vi chính xác hơn, tái tạo lỗi dễ hơn và đưa ra kết luận chất lượng có căn cứ.
