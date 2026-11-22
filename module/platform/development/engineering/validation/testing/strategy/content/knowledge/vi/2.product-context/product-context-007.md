# Ghi nhận yêu cầu hợp đồng, kiểm toán và ràng buộc dữ liệu

Một sản phẩm có thể đáp ứng đúng chức năng nhưng vẫn không phù hợp để triển khai nếu vi phạm cam kết với khách hàng, không tạo được bằng chứng kiểm toán hoặc xử lý dữ liệu trái với giới hạn đã thỏa thuận. Vì vậy, khi tìm hiểu bối cảnh sản phẩm, nhóm cần ghi nhận những nghĩa vụ này như các yêu cầu có thể truy vết và kiểm chứng.

Công việc không dừng ở việc lưu bản hợp đồng hoặc chép lại một điều khoản. Nhóm phải hiểu điều khoản áp dụng cho ai, trong tình huống nào, ảnh hưởng đến phần nào của sản phẩm, cần hành vi gì và bằng chứng nào chứng minh nghĩa vụ đã được đáp ứng. Kết quả là một tập hợp yêu cầu rõ ràng để sản phẩm, kỹ thuật, kiểm thử, bảo mật, vận hành và người phụ trách hợp đồng cùng sử dụng.

## 1. Vì sao cần ghi nhận các nghĩa vụ này từ đầu?

Yêu cầu hợp đồng, yêu cầu kiểm toán và ràng buộc dữ liệu thường xuất hiện trong tài liệu khác nhau, do những bên khác nhau quản lý. Chúng có thể nằm trong hợp đồng chính, phụ lục dịch vụ, thỏa thuận xử lý dữ liệu, tài liệu bảo mật, quy định nội bộ, hồ sơ mua sắm hoặc cam kết tích hợp với đối tác.

Nếu nhóm chỉ đọc tài liệu yêu cầu chức năng, các nghĩa vụ quan trọng có thể bị phát hiện quá muộn. Ví dụ:

- Hợp đồng yêu cầu khách hàng được xuất dữ liệu khi chấm dứt dịch vụ, nhưng sản phẩm chưa có định dạng xuất hoặc quy trình bàn giao.
- Khách hàng có quyền kiểm toán, nhưng hệ thống không lưu đủ lịch sử thay đổi quyền truy cập.
- Dữ liệu phải được lưu trong một khu vực địa lý cụ thể, trong khi dịch vụ phân tích hoặc bản sao lưu lại chuyển dữ liệu sang khu vực khác.
- Hợp đồng quy định thời hạn thông báo sự cố, nhưng hệ thống không phát hiện hoặc không phân loại được sự cố liên quan đến dữ liệu.
- Dữ liệu phải được xóa sau khi hết thời hạn lưu trữ, nhưng bản sao trong log, bản sao lưu hoặc môi trường hỗ trợ vẫn còn tồn tại.

Các vấn đề này có thể ảnh hưởng đến khả năng ký kết, nghiệm thu, vận hành, gia hạn hoặc chấm dứt dịch vụ. Ghi nhận sớm giúp nhóm xác định thay đổi sản phẩm, phụ thuộc, bằng chứng và người chịu trách nhiệm trước khi cam kết được đưa vào thực hiện.

## 2. Xác định nguồn và phạm vi nghĩa vụ

Trước khi chuyển một điều khoản thành yêu cầu sản phẩm, hãy xác định nguồn của nó và phạm vi áp dụng. Không phải mọi tài liệu đều có cùng hiệu lực, phiên bản hoặc đối tượng áp dụng.

Các nguồn thường gặp gồm:

| Nguồn | Nội dung cần tìm | Câu hỏi cần xác minh |
|---|---|---|
| Hợp đồng chính | Phạm vi dịch vụ, trách nhiệm các bên, nghiệm thu, chấm dứt và giải quyết vi phạm | Điều khoản áp dụng cho sản phẩm, khách hàng hoặc gói dịch vụ nào? |
| Phụ lục dịch vụ hoặc SLA | Mức sẵn sàng, thời gian phản hồi, hỗ trợ, bảo trì và cách tính chỉ số | Cách đo, khoảng thời gian, ngoại lệ và biện pháp khắc phục được định nghĩa ra sao? |
| Thỏa thuận xử lý dữ liệu | Vai trò của các bên, mục đích xử lý, loại dữ liệu, quyền và nghĩa vụ liên quan | Dữ liệu nào được xử lý, bởi ai, cho mục đích gì và trong thời gian bao lâu? |
| Phụ lục bảo mật | Kiểm soát truy cập, mã hóa, quản lý sự cố, kiểm toán và nhà cung cấp phụ | Bằng chứng hoặc kiểm soát nào được yêu cầu? |
| Tài liệu tích hợp | Giao diện, xác thực, định dạng, giới hạn và trách nhiệm khi trao đổi dữ liệu | Hệ thống nào là nguồn dữ liệu chuẩn và cách xử lý lỗi được thống nhất thế nào? |
| Chính sách và quy định áp dụng | Nghĩa vụ về quyền riêng tư, lưu trữ, bảo vệ dữ liệu, hồ sơ và kiểm soát | Phạm vi pháp lý, khu vực, loại dữ liệu và thời điểm áp dụng là gì? |
| Quy trình nội bộ | Phê duyệt, lưu hồ sơ, phân quyền, xử lý yêu cầu và lưu giữ bằng chứng | Ai có quyền quyết định, thực hiện và xác nhận? |

Hãy ghi lại ít nhất tên tài liệu, mã hoặc số phiên bản, ngày hiệu lực, bên ban hành, bên liên quan, khu vực áp dụng và người sở hữu tài liệu. Với tài liệu có nhiều phụ lục, ghi rõ điều khoản hoặc mục tham chiếu để người khác tìm lại được.

Cần phân biệt ba loại thông tin:

- **Nghĩa vụ đã xác nhận:** nội dung có nguồn rõ ràng và đã được người có thẩm quyền xác nhận cách hiểu.
- **Cách diễn giải cần xác nhận:** điều khoản có thể được hiểu theo nhiều cách hoặc chưa rõ phạm vi áp dụng.
- **Giả định làm việc:** cách hiểu tạm thời để tiếp tục phân tích, có người phụ trách và thời hạn xác minh.

Không tự suy diễn một cam kết kỹ thuật từ câu chữ mơ hồ. Nếu hợp đồng nói “bảo đảm tính sẵn sàng cao”, nhóm cần yêu cầu xác nhận chỉ số, cách đo, chu kỳ và ngoại lệ trước khi biến nó thành ngưỡng nghiệm thu.

## 3. Tách điều khoản thành nghĩa vụ có thể quản lý

Một điều khoản có thể chứa nhiều nghĩa vụ. Hãy tách thành các yêu cầu nguyên tử, mỗi yêu cầu mô tả một kết quả hoặc một kiểm soát có thể kiểm chứng.

Với từng nghĩa vụ, ghi nhận:

| Trường thông tin | Nội dung cần ghi |
|---|---|
| Mã yêu cầu | Mã duy nhất để tham chiếu trong thiết kế, kiểm thử và báo cáo |
| Nguồn | Tên tài liệu, phiên bản, điều khoản hoặc mục |
| Chủ thể | Bên phải thực hiện, bên được hưởng quyền hoặc bên phê duyệt |
| Nghĩa vụ | Hành vi, kết quả hoặc giới hạn phải đáp ứng |
| Điều kiện áp dụng | Sự kiện, loại khách hàng, gói dịch vụ, loại dữ liệu hoặc khu vực kích hoạt nghĩa vụ |
| Thời hạn và ngưỡng | Mốc thời gian, thời lượng, giới hạn, tần suất hoặc chỉ số cụ thể |
| Phạm vi hệ thống | Dịch vụ, thành phần, quy trình, dữ liệu và bên thứ ba bị ảnh hưởng |
| Cách xác minh | Phép kiểm tra, phép đo, rà soát hoặc quy trình xác nhận |
| Bằng chứng | Log, báo cáo, biên bản, cấu hình, kết quả kiểm thử hoặc hồ sơ phê duyệt |
| Chủ sở hữu | Người chịu trách nhiệm diễn giải, triển khai hoặc theo dõi |
| Trạng thái | Đã xác nhận, đang làm rõ, đã triển khai, đã kiểm chứng hoặc được chấp thuận ngoại lệ |

Một yêu cầu tốt dùng ngôn ngữ rõ ràng, tránh các từ như “đầy đủ”, “nhanh”, “an toàn” hoặc “hợp lý” nếu không có tiêu chí cụ thể. Ví dụ, “hệ thống phải lưu lịch sử quản trị” chưa đủ để triển khai. Cần xác định sự kiện nào được ghi, trường thông tin nào bắt buộc, ai được xem, thời hạn lưu, cách bảo vệ và cách xuất bằng chứng.

Khi tách yêu cầu, giữ mối liên hệ với câu chữ gốc. Bản diễn giải kỹ thuật không thay thế điều khoản nguồn. Nếu điều khoản được sửa, nhóm phải biết yêu cầu và kiểm thử nào cần đánh giá lại.

## 4. Ghi nhận yêu cầu hợp đồng

Yêu cầu hợp đồng thường liên quan đến phạm vi dịch vụ, mức chất lượng, hỗ trợ, trách nhiệm, bảo mật, quyền kiểm toán, xử lý dữ liệu và điều kiện kết thúc quan hệ dịch vụ.

### 4.1. Phạm vi và cam kết dịch vụ

Xác định chính xác dịch vụ, chức năng, nhóm khách hàng, khu vực và gói sản phẩm nằm trong cam kết. Một cam kết có thể chỉ áp dụng cho môi trường production, một gói dịch vụ nhất định hoặc một khu vực triển khai.

Với SLA hoặc chỉ số dịch vụ, không chỉ ghi lại con số mục tiêu. Cần làm rõ:

- Chỉ số được đo là gì: thời gian sẵn sàng, độ trễ, thời gian phản hồi hỗ trợ hay thời gian khôi phục.
- Công thức tính và nguồn dữ liệu đo.
- Cửa sổ đo: theo ngày, tuần, tháng hay một khoảng thời gian khác.
- Thành phần và giao dịch nào được đưa vào phép đo.
- Thời gian bảo trì, sự kiện ngoài phạm vi hoặc phụ thuộc bên thứ ba được xử lý ra sao.
- Ngưỡng cảnh báo, quy trình thông báo và biện pháp khắc phục khi không đạt.
- Ai có quyền xác nhận số liệu và giải quyết tranh chấp về phép đo.

Ví dụ, một cam kết về độ sẵn sàng cần xác định điểm quan sát, cách tính tổng thời gian bị gián đoạn, cách loại trừ bảo trì đã thông báo và nơi lưu số liệu. Nếu các yếu tố này chưa rõ, không thể kết luận hai bên đang đo cùng một kết quả.

### 4.2. Trách nhiệm và điểm bàn giao giữa các bên

Lập danh sách các trách nhiệm của nhà cung cấp, khách hàng và bên thứ ba. Chú ý các điểm bàn giao như cấp tài khoản, cung cấp dữ liệu, phê duyệt thay đổi, xử lý yêu cầu hỗ trợ, thông báo sự cố và xác nhận hoàn tất.

Một bảng trách nhiệm có thể dùng các vai trò sau:

- **Thực hiện:** người hoặc nhóm trực tiếp làm công việc.
- **Chịu trách nhiệm cuối cùng:** người có quyền quyết định kết quả.
- **Tham vấn:** bên cung cấp chuyên môn hoặc thông tin đầu vào.
- **Được thông báo:** bên cần nhận trạng thái hoặc kết quả.

Điều quan trọng là không để một nghĩa vụ không có chủ sở hữu. Nếu một quy trình cần cả khách hàng và nhà cung cấp, hãy ghi rõ đầu vào, thời hạn phản hồi và điều kiện chuyển bước của mỗi bên.

### 4.3. Nghiệm thu, hỗ trợ và thay đổi

Điều khoản nghiệm thu cần được chuyển thành tiêu chí có thể quan sát: chức năng nào phải hoạt động, dữ liệu nào phải được chuyển, lỗi nào được phép tồn tại và ai xác nhận kết quả. Ghi rõ thời hạn phản hồi, cách gửi thông báo lỗi và cách xử lý khi hai bên không thống nhất.

Với hỗ trợ và sự cố, cần làm rõ mức độ nghiêm trọng, thời gian phản hồi, kênh liên lạc, thông tin cần cung cấp và cách cập nhật trạng thái. Thời gian phản hồi không đồng nghĩa với thời gian khắc phục; hãy ghi riêng nếu hợp đồng quy định cả hai.

Điều khoản thay đổi cần được nối với quy trình quản lý thay đổi của sản phẩm. Một thay đổi về nơi lưu dữ liệu, nhà cung cấp phụ hoặc giao diện tích hợp có thể yêu cầu đánh giá lại hợp đồng, bảo mật, kiểm thử và thông báo khách hàng.

### 4.4. Quyền kiểm toán và kết thúc dịch vụ

Nếu khách hàng hoặc bên có thẩm quyền được quyền kiểm toán, hãy ghi rõ phạm vi, hình thức, thời hạn thông báo, tần suất, hồ sơ được cung cấp, cách bảo vệ thông tin của khách hàng khác và quy trình xử lý phát hiện.

Với chấm dứt dịch vụ, xác định nghĩa vụ bàn giao, định dạng xuất dữ liệu, thời gian cung cấp, thời hạn lưu sau chấm dứt, quy trình xóa và bằng chứng hoàn tất. Cần xét cả dữ liệu trong hệ thống chính, bản sao, log, bản sao lưu và hệ thống của nhà cung cấp phụ.

## 5. Ghi nhận yêu cầu kiểm toán và khả năng truy vết

Kiểm toán cần bằng chứng đáng tin cậy để trả lời ai đã làm gì, với đối tượng nào, vào thời điểm nào, qua kênh nào và kết quả ra sao. Hệ thống có giao diện quản trị nhưng không lưu lịch sử thay đổi thì vẫn có thể thiếu bằng chứng quan trọng.

### 5.1. Xác định sự kiện cần lưu

Không phải mọi thao tác đều cần ghi cùng mức độ chi tiết. Hãy xác định sự kiện theo rủi ro, nghĩa vụ hợp đồng, yêu cầu quản trị và nhu cầu điều tra.

Những nhóm sự kiện thường cần xem xét:

- Đăng nhập, đăng xuất, xác thực thất bại và thay đổi yếu tố xác thực.
- Tạo, khóa, mở khóa, xóa tài khoản và thay đổi vai trò hoặc quyền.
- Thay đổi cấu hình bảo mật, chính sách, tích hợp và thiết lập tenant.
- Xem, xuất, sửa, xóa hoặc chia sẻ dữ liệu nhạy cảm khi nghĩa vụ yêu cầu theo dõi.
- Thay đổi trạng thái giao dịch hoặc phê duyệt nghiệp vụ quan trọng.
- Thao tác của quản trị viên, nhân viên hỗ trợ và tài khoản dịch vụ.
- Thay đổi cấu hình lưu trữ, thời hạn lưu, nơi xử lý hoặc quy tắc xóa dữ liệu.
- Truy cập và xuất hồ sơ phục vụ kiểm toán.

Đối với mỗi nhóm, hãy xác định hành động cụ thể, đối tượng, mức độ nhạy cảm, lý do ghi nhận và thời hạn lưu.

### 5.2. Thiết kế nội dung của bản ghi kiểm toán

Một bản ghi kiểm toán thường cần đủ trường để tái dựng sự kiện mà không lưu quá nhiều dữ liệu nhạy cảm.

| Trường | Ý nghĩa |
|---|---|
| Mã sự kiện | Định danh duy nhất để tra cứu |
| Thời điểm | Thời gian xảy ra sự kiện, kèm múi giờ hoặc quy ước thời gian thống nhất |
| Chủ thể | Người dùng, quản trị viên, dịch vụ hoặc tiến trình thực hiện |
| Hành động | Loại thao tác được thực hiện |
| Đối tượng | Tài khoản, bản ghi, tài nguyên hoặc cấu hình bị tác động |
| Phạm vi khách hàng | Tenant hoặc miền dữ liệu liên quan, nếu hệ thống đa khách hàng |
| Kết quả | Thành công, thất bại, bị từ chối hoặc trạng thái khác |
| Nguồn thực hiện | Ứng dụng, API, giao diện quản trị hoặc kênh tích hợp |
| Ngữ cảnh truy vết | Mã yêu cầu, phiên hoặc giao dịch để nối các sự kiện liên quan |
| Chi tiết thay đổi | Trường nào thay đổi và giá trị ở mức được phép ghi nhận |
| Lý do | Lý do nghiệp vụ hoặc mã phê duyệt khi cần |

Tránh đưa mật khẩu, token, khóa bí mật hoặc toàn bộ nội dung dữ liệu cá nhân vào log. Khi cần ghi nhận thay đổi, cân nhắc chỉ lưu tên trường, mã tham chiếu hoặc giá trị đã được che bớt. Bằng chứng phải đủ để kiểm toán nhưng không tạo thêm kho dữ liệu nhạy cảm không cần thiết.

### 5.3. Bảo vệ tính toàn vẹn và khả năng truy cập

Bản ghi kiểm toán chỉ có giá trị khi có thể tin cậy và truy xuất trong thời hạn yêu cầu. Hãy xác định:

- Quyền tạo, đọc, xuất, cấu hình và xóa log.
- Cách ngăn người bị ghi nhận tự sửa hoặc xóa dấu vết.
- Cơ chế phát hiện sửa đổi hoặc mất log.
- Đồng bộ thời gian giữa các dịch vụ và cách xử lý sự kiện đến trễ.
- Tính sẵn sàng, sao lưu và khôi phục kho log.
- Phân tách dữ liệu giữa các khách hàng.
- Thời hạn lưu, quy tắc lưu trữ và quy trình xóa.
- Cách cung cấp bằng chứng cho khách hàng hoặc kiểm toán viên mà không tiết lộ dữ liệu của bên khác.

Có thể dùng kho lưu trữ chỉ ghi thêm, kiểm soát quyền nghiêm ngặt, dấu kiểm tra toàn vẹn hoặc cơ chế lưu trữ chống sửa đổi tùy yêu cầu và kiến trúc. Chọn biện pháp tương xứng với mức rủi ro; đồng thời kiểm thử khả năng phát hiện thiếu sự kiện, sai thứ tự, sai thời gian và truy cập trái phép.

## 6. Ghi nhận ràng buộc dữ liệu

Ràng buộc dữ liệu xác định dữ liệu nào được thu thập, sử dụng, lưu, chia sẻ, chuyển vùng, sao lưu, xuất và xóa. Hãy theo dõi dữ liệu xuyên suốt vòng đời, bao gồm bản sao và dữ liệu phát sinh từ dữ liệu gốc.

### 6.1. Phân loại và mục đích sử dụng

Lập danh mục dữ liệu theo nhóm và mức nhạy cảm. Tùy sản phẩm, có thể có dữ liệu công khai, dữ liệu nội bộ, dữ liệu khách hàng, dữ liệu cá nhân, dữ liệu tài chính, dữ liệu xác thực hoặc bí mật kinh doanh.

Với mỗi nhóm, ghi:

- Chủ sở hữu dữ liệu và hệ thống nguồn.
- Chủ thể dữ liệu hoặc khách hàng liên quan.
- Mục đích thu thập và xử lý.
- Trường dữ liệu, mức nhạy cảm và khối lượng dự kiến.
- Thành phần và bên thứ ba có quyền truy cập.
- Cơ sở hoặc thỏa thuận cho phép xử lý.
- Thời hạn lưu và điều kiện xóa.
- Yêu cầu bảo vệ, mã hóa, che dữ liệu và kiểm soát truy cập.

Chỉ thu thập dữ liệu cần thiết cho mục đích đã xác định. Nếu một trường không phục vụ chức năng, nghĩa vụ hoặc mục đích hợp lệ, cần xem xét loại bỏ hoặc giảm độ chi tiết. Mục đích mới như phân tích, huấn luyện mô hình hoặc chia sẻ cho đối tác cần được đánh giá riêng theo thỏa thuận và quy định áp dụng.

### 6.2. Vị trí lưu trữ và luồng chuyển dữ liệu

Ghi nhận nơi dữ liệu được tạo, xử lý, lưu trữ, sao lưu và truy cập từ xa. Sơ đồ luồng dữ liệu nên thể hiện cả dịch vụ chính, hệ thống phân tích, công cụ hỗ trợ, nền tảng log và nhà cung cấp phụ.

Với yêu cầu về khu vực địa lý, cần làm rõ:

- Khu vực nào được phép lưu dữ liệu chính.
- Dữ liệu có thể được xử lý hoặc truy cập từ khu vực khác hay không.
- Bản sao lưu, log, chỉ mục tìm kiếm và dữ liệu phân tích có tuân theo cùng giới hạn không.
- Nhà cung cấp phụ nào tham gia và họ xử lý dữ liệu ở đâu.
- Cách chứng minh cấu hình triển khai và vị trí dữ liệu.
- Quy trình đánh giá và phê duyệt khi cần thay đổi khu vực.

Không thể chỉ kiểm tra vị trí của cơ sở dữ liệu chính rồi kết luận toàn bộ dữ liệu nằm trong khu vực cho phép. Các luồng phụ như giám sát, hỗ trợ và sao lưu cũng cần được đưa vào phạm vi.

### 6.3. Thời hạn lưu, lưu trữ và xóa

Thời hạn lưu có thể khác nhau theo loại dữ liệu, mục đích, hợp đồng và nghĩa vụ áp dụng. Hãy lập lịch lưu giữ theo nhóm dữ liệu, sự kiện bắt đầu tính thời hạn và hành động khi hết hạn.

Phân biệt các trạng thái:

- Dữ liệu đang được sử dụng trong hệ thống chính.
- Dữ liệu đã hết mục đích sử dụng nhưng còn trong thời gian lưu.
- Dữ liệu được lưu trữ để đáp ứng nghĩa vụ hoặc phục vụ điều tra.
- Dữ liệu đang bị tạm hoãn xóa theo quy trình được phê duyệt.
- Dữ liệu đã được xóa hoặc ẩn danh theo tiêu chí đã xác định.

Quy trình xóa phải xét đến bản sao, cache, chỉ mục, kho phân tích, log và bản sao lưu. Với bản sao lưu dạng bất biến, có thể cần quy trình đánh dấu dữ liệu không được phục hồi vào hệ thống hoạt động và để bản sao hết hạn theo chu kỳ đã phê duyệt. Ghi rõ cách xử lý, thời hạn và bằng chứng thay vì tuyên bố “đã xóa” khi mới xóa một bản ghi trong cơ sở dữ liệu chính.

### 6.4. Truy cập, chia sẻ và tính toàn vẹn

Xác định vai trò nào được xem, tạo, sửa, xuất hoặc xóa từng nhóm dữ liệu. Phân quyền cần xét đến tenant, mục đích, ngữ cảnh hỗ trợ và quyền tạm thời. Các thao tác đặc quyền nên có phê duyệt hoặc ghi nhận kiểm toán phù hợp.

Với trao đổi dữ liệu, quy định định dạng, trường bắt buộc, quy tắc xác thực, mã hóa khi truyền, xác thực bên nhận và xử lý lỗi. Với dữ liệu quan trọng, cần xác định yêu cầu về tính đầy đủ, chính xác, nhất quán, thứ tự, chống trùng lặp và khả năng đối soát.

Đối với dữ liệu được xuất hoặc chuyển giao, ghi rõ ai được yêu cầu, ai phê duyệt, định dạng, phạm vi, thời hạn cung cấp và cách bảo vệ tệp trong quá trình bàn giao.

### 6.5. Dữ liệu dùng cho kiểm thử và phát triển

Dữ liệu production có thể chứa thông tin nhạy cảm và không tự động phù hợp để sao chép sang môi trường phát triển hoặc kiểm thử. Xác định nguồn dữ liệu được phép, cách tạo dữ liệu tổng hợp, che dữ liệu, ẩn danh hoặc giảm chi tiết, cũng như cách kiểm soát truy cập và xóa sau khi dùng.

Dữ liệu kiểm thử vẫn phải giữ được đặc tính cần thiết để kiểm tra quy tắc nghiệp vụ, phân quyền, khối lượng và chất lượng dữ liệu. Nếu dùng dữ liệu đã che, hãy xác minh rằng quá trình che không làm mất các quan hệ hoặc mẫu cần thiết cho bài kiểm thử.

## 7. Chuyển nghĩa vụ thành yêu cầu và tiêu chí kiểm chứng

Sau khi ghi nhận nguồn và nghĩa vụ, hãy chuyển chúng thành yêu cầu sản phẩm, yêu cầu vận hành hoặc yêu cầu quy trình. Một nghĩa vụ có thể cần nhiều biện pháp ở các lớp khác nhau.

Ví dụ:

| Nghĩa vụ đã ghi nhận | Yêu cầu có thể triển khai | Cách xác minh | Bằng chứng |
|---|---|---|---|
| Chỉ quản trị viên được phép thay đổi vai trò | API kiểm tra quyền ở phía máy chủ cho mọi thao tác thay đổi vai trò | Thử với vai trò hợp lệ, không hợp lệ và truy cập chéo tenant | Kết quả kiểm thử phân quyền, cấu hình và log sự kiện |
| Khách hàng có quyền xem lịch sử thay đổi quản trị | Hệ thống lưu sự kiện quản trị theo trường đã thống nhất và cung cấp chức năng xuất có kiểm soát | Thực hiện thay đổi, tra cứu theo khoảng thời gian và xuất báo cáo | Bản ghi kiểm toán, báo cáo xuất và lịch sử truy cập báo cáo |
| Dữ liệu phải lưu tại khu vực được thỏa thuận | Cấu hình triển khai, sao lưu và dịch vụ phụ giới hạn trong khu vực được phê duyệt | Rà soát kiến trúc, cấu hình và kiểm tra luồng dữ liệu | Hồ sơ cấu hình, sơ đồ luồng và xác nhận nhà cung cấp |
| Dữ liệu khách hàng phải được xóa sau khi hết thời hạn | Quy trình xóa bao phủ hệ thống chính và các bản sao theo lịch lưu giữ | Tạo dữ liệu thử, kích hoạt điều kiện hết hạn và kiểm tra từng kho | Nhật ký tác vụ, kết quả kiểm tra và biên bản xác nhận |
| Nhà cung cấp phải báo cáo mức sẵn sàng định kỳ | Thu thập chỉ số theo công thức, cửa sổ đo và ngoại lệ đã thống nhất | Đối chiếu dữ liệu giám sát với báo cáo định kỳ | Báo cáo SLA, dữ liệu đo và biên bản rà soát |

Tiêu chí chấp nhận nên mô tả điều kiện đầu vào, hành động, kết quả mong đợi và cách đo. Ví dụ: “Khi một người dùng không có quyền quản trị gửi yêu cầu thay đổi vai trò, hệ thống từ chối thao tác, không thay đổi dữ liệu và ghi nhận sự kiện bị từ chối theo chính sách kiểm toán.”

Đừng dừng ở việc kiểm thử đường đi thành công. Hãy kiểm tra cả trường hợp bị từ chối, lỗi phụ thuộc, thao tác lặp, dữ liệu không hợp lệ, quyền bị thu hồi, hết thời hạn và phục hồi sau sự cố.

## 8. Duy trì ma trận truy vết từ nguồn đến bằng chứng

Ma trận truy vết giúp chứng minh mỗi nghĩa vụ đã được phân tích, triển khai và xác minh. Một dòng có thể nối nguồn hợp đồng với yêu cầu sản phẩm, thành phần, kiểm thử, bằng chứng và người phê duyệt.

Ví dụ về cấu trúc ma trận:

| Mã nghĩa vụ | Nguồn và điều khoản | Yêu cầu sản phẩm | Thành phần hoặc quy trình | Kiểm thử / rà soát | Bằng chứng | Chủ sở hữu |
|---|---|---|---|---|---|---|
| CT-01 | SLA, mục về độ sẵn sàng | Đo và báo cáo chỉ số theo công thức đã thống nhất | Giám sát và báo cáo dịch vụ | Đối chiếu phép tính với dữ liệu sự kiện | Báo cáo SLA và dữ liệu đo | Vận hành dịch vụ |
| AU-02 | Phụ lục kiểm toán | Ghi nhận thay đổi vai trò và quyền | Dịch vụ quản trị và kho audit | Kiểm thử thao tác thành công, thất bại và truy cập trái phép | Log mẫu và kết quả kiểm thử | Bảo mật / kỹ thuật |
| DT-03 | Thỏa thuận dữ liệu | Giới hạn nơi lưu và xử lý dữ liệu | Hạ tầng, sao lưu và nhà cung cấp phụ | Rà soát cấu hình và luồng dữ liệu | Sơ đồ, cấu hình và hồ sơ nhà cung cấp | Chủ sở hữu dữ liệu |
| DT-04 | Điều khoản chấm dứt | Xuất và xóa dữ liệu theo thời hạn | Quy trình rời dịch vụ và tác vụ lưu giữ | Kiểm thử xuất, xóa và xử lý bản sao | Tệp bàn giao, log xóa và xác nhận | Vận hành / hỗ trợ |

Ma trận cần có trạng thái và ngày rà soát. Các trạng thái nên phân biệt rõ: chưa phân tích, đang làm rõ, đã chuyển thành yêu cầu, đã triển khai, đã kiểm chứng, không áp dụng có lý do và ngoại lệ được phê duyệt.

Khi một yêu cầu thay đổi, hãy truy ngược về điều khoản và tiến về các thành phần, bài kiểm thử, hồ sơ và báo cáo bị ảnh hưởng. Khi một bằng chứng hết hạn hoặc cấu hình thay đổi, hãy xác định nghĩa vụ nào cần xác minh lại.

## 9. Xử lý mâu thuẫn, ngoại lệ và thay đổi

Mâu thuẫn có thể xảy ra giữa hai hợp đồng, giữa hợp đồng và kiến trúc hiện tại, giữa thời hạn lưu dữ liệu và yêu cầu xóa, hoặc giữa quyền kiểm toán và nghĩa vụ bảo vệ dữ liệu của khách hàng khác.

Khi phát hiện mâu thuẫn:

1. Ghi lại nguyên văn nguồn liên quan, phiên bản và phạm vi áp dụng.
2. Mô tả hai nghĩa vụ hoặc điều kiện đang xung đột.
3. Xác định dữ liệu, khách hàng, chức năng và thời điểm bị ảnh hưởng.
4. Đánh giá rủi ro nếu tiếp tục theo từng cách hiểu.
5. Chuyển câu hỏi đến người có thẩm quyền về hợp đồng, pháp lý, bảo mật hoặc chủ sở hữu sản phẩm.
6. Ghi lại quyết định, người phê duyệt, căn cứ, ngày hiệu lực và yêu cầu cần cập nhật.
7. Điều chỉnh yêu cầu, kiểm thử, cấu hình và bằng chứng có liên quan.

Không tự giải quyết mâu thuẫn bằng cách chọn điều khoản dễ thực hiện hơn. Nếu chưa có quyết định, giữ trạng thái đang làm rõ, ghi rõ tác động và không trình bày giả định như một nghĩa vụ đã xác nhận.

Ngoại lệ cần có phạm vi, lý do, thời hạn, biện pháp giảm thiểu, người chấp thuận và ngày xem xét lại. Nếu ngoại lệ làm thay đổi cam kết với khách hàng, cần có quy trình phê duyệt và sửa đổi tài liệu tương ứng.

## 10. Ví dụ: nền tảng SaaS phục vụ khách hàng doanh nghiệp

Giả sử một nền tảng SaaS ký hợp đồng cung cấp dịch vụ quản lý hồ sơ cho một khách hàng doanh nghiệp. Đây là ví dụ giả định để minh họa cách chuyển điều khoản thành yêu cầu; các con số và thời hạn dưới đây chỉ là điều kiện của tình huống, không phải chuẩn chung.

Khách hàng yêu cầu báo cáo mức sẵn sàng hằng tháng, lưu lịch sử thao tác quản trị để phục vụ kiểm toán, lưu dữ liệu trong khu vực đã thỏa thuận và hỗ trợ xuất rồi xóa dữ liệu khi chấm dứt dịch vụ.

Nhóm phân tích thành các nghĩa vụ:

| Nghĩa vụ trong tình huống | Câu hỏi cần làm rõ | Quyết định sản phẩm và vận hành |
|---|---|---|
| Báo cáo mức sẵn sàng hằng tháng | Công thức, cửa sổ đo, ngoại lệ và nguồn dữ liệu là gì? | Xác định phép đo, điểm quan sát, lịch tạo báo cáo và người rà soát |
| Lưu lịch sử thao tác quản trị | Sự kiện nào, trường nào, ai được xem và lưu bao lâu? | Thiết kế event schema, quyền truy cập, lưu trữ và xuất log |
| Lưu dữ liệu trong khu vực đã thỏa thuận | Dữ liệu chính, log, backup và dịch vụ phụ có cùng giới hạn không? | Lập sơ đồ luồng dữ liệu và cấu hình vùng cho từng thành phần |
| Xuất và xóa dữ liệu khi chấm dứt | Định dạng, thời hạn, bản sao và xác nhận xóa được xử lý ra sao? | Xây dựng quy trình xuất, bàn giao, lịch xóa và hồ sơ xác nhận |

Với yêu cầu kiểm toán, nhóm có thể kiểm tra một quản trị viên thay đổi vai trò người dùng. Hệ thống cần ghi lại chủ thể, đối tượng, hành động, thời điểm, kết quả và mã truy vết. Sau đó, người có quyền phù hợp có thể tìm và xuất lịch sử theo khoảng thời gian. Bài kiểm thử cần xác minh rằng người dùng thường không thể đọc hoặc sửa log, tenant khác không thể truy cập dữ liệu và thao tác xuất cũng được ghi nhận.

Với yêu cầu lưu trữ theo khu vực, nhóm lập bản đồ từ nơi dữ liệu được tạo đến cơ sở dữ liệu, kho log, sao lưu, công cụ phân tích và nhà cung cấp phụ. Kiểm tra cấu hình triển khai là cần thiết nhưng chưa đủ; cần đối chiếu với kiến trúc thực tế và hồ sơ của nhà cung cấp.

Với yêu cầu kết thúc dịch vụ, nhóm chạy thử quy trình trên một tenant kiểm thử: xác nhận người yêu cầu có thẩm quyền, tạo gói xuất, kiểm tra tính đầy đủ, bàn giao qua kênh bảo vệ, kích hoạt lịch xóa và đối chiếu kết quả ở từng kho dữ liệu. Nếu bản sao lưu còn trong chu kỳ lưu giữ, hồ sơ phải giải thích cách ngăn dữ liệu đã xóa quay lại hệ thống hoạt động và khi nào bản sao hết hạn.

Trước khi nghiệm thu, nhóm tập hợp ma trận truy vết, kết quả kiểm thử, báo cáo dịch vụ, hồ sơ cấu hình, mẫu log và biên bản xác nhận. Người phụ trách hợp đồng và chủ sở hữu sản phẩm xem xét các nghĩa vụ còn mở trước khi xác nhận đáp ứng.

## 11. Tổ chức rà soát và cập nhật trong vòng đời sản phẩm

Yêu cầu hợp đồng và dữ liệu có thể thay đổi khi gia hạn, thêm khu vực triển khai, thay nhà cung cấp phụ, mở tính năng mới hoặc thay đổi mục đích sử dụng dữ liệu. Vì vậy, cần gắn việc rà soát với các sự kiện của vòng đời sản phẩm.

Nên xem lại nghĩa vụ khi:

- Tiếp nhận khách hàng, gói dịch vụ hoặc hợp đồng mới.
- Thay đổi tính năng, kiến trúc, mô hình tenant hoặc luồng dữ liệu.
- Thêm hoặc thay nhà cung cấp phụ, công cụ phân tích hay kênh hỗ trợ.
- Thay đổi khu vực triển khai, sao lưu hoặc nơi truy cập dữ liệu.
- Phát hiện sự cố, yêu cầu kiểm toán hoặc khiếu nại của khách hàng.
- Gia hạn, sửa đổi hoặc chấm dứt hợp đồng.
- Thay đổi quy định áp dụng hoặc chính sách nội bộ.

Mỗi lần rà soát cần ghi ngày, người tham gia, nguồn đã xem, nghĩa vụ thay đổi, quyết định, hành động tiếp theo và thời hạn. Duy trì một nguồn thông tin có kiểm soát phiên bản để nhóm kỹ thuật và vận hành biết yêu cầu hiện hành.

## 12. Bộ hồ sơ tối thiểu và câu hỏi tự kiểm tra

Một bộ hồ sơ đủ dùng thường gồm:

1. Danh mục nguồn và phiên bản tài liệu.
2. Sổ đăng ký nghĩa vụ hợp đồng, kiểm toán và dữ liệu.
3. Danh mục dữ liệu và sơ đồ luồng dữ liệu.
4. Ma trận trách nhiệm và chủ sở hữu.
5. Ma trận truy vết đến yêu cầu, kiểm thử và bằng chứng.
6. Danh sách cách hiểu chưa xác nhận, mâu thuẫn và ngoại lệ.
7. Hồ sơ rà soát, phê duyệt và lịch sử thay đổi.

Trước khi chuyển bối cảnh sang thiết kế hoặc lập kế hoạch kiểm thử, hãy tự hỏi:

- Mỗi nghĩa vụ có nguồn, phiên bản và phạm vi áp dụng rõ ràng chưa?
- Câu chữ mơ hồ đã được làm rõ hoặc đánh dấu là giả định chưa?
- Mỗi nghĩa vụ có người chịu trách nhiệm và thời hạn xử lý chưa?
- Các yêu cầu về SLA có công thức, cửa sổ đo, ngoại lệ và nguồn bằng chứng chưa?
- Sự kiện kiểm toán có đủ thông tin truy vết và được bảo vệ khỏi sửa đổi trái phép không?
- Danh mục dữ liệu đã bao gồm log, bản sao, phân tích, backup và nhà cung cấp phụ chưa?
- Mục đích, quyền truy cập, vị trí, thời hạn lưu, xuất và xóa dữ liệu đã được xác định chưa?
- Mỗi yêu cầu có cách kiểm chứng và bằng chứng có thể truy xuất không?
- Mâu thuẫn và ngoại lệ đã có quyết định được ghi nhận chưa?
- Các thay đổi hợp đồng hoặc kiến trúc có kích hoạt rà soát lại không?

Sơ đồ sau thể hiện đường đi từ nguồn nghĩa vụ đến bằng chứng và quyết định:

~~~mermaid
flowchart TD
    A["Hợp đồng, phụ lục, chính sách và quy định"] --> B["Trích xuất nghĩa vụ và phạm vi"]
    B --> C["Làm rõ cách hiểu, chủ sở hữu và thời hạn"]
    C --> D["Phân loại: hợp đồng, kiểm toán, dữ liệu"]
    D --> E["Chuyển thành yêu cầu có thể kiểm chứng"]
    E --> F["Ánh xạ thành phần, quy trình và kiểm soát"]
    F --> G["Thiết kế kiểm thử và thu thập bằng chứng"]
    G --> H["Rà soát ma trận truy vết"]
    H --> I{"Đã đáp ứng và có bằng chứng?"}
    I -->|Có| J["Nghiệm thu hoặc xác nhận nghĩa vụ"]
    I -->|Chưa| K["Làm rõ, khắc phục hoặc xin phê duyệt ngoại lệ"]
    K --> E
    J --> L["Theo dõi thay đổi và rà soát định kỳ"]
    L --> A
~~~

Ghi nhận tốt yêu cầu hợp đồng, kiểm toán và ràng buộc dữ liệu giúp nhóm biết chính xác mình đã cam kết điều gì, cần bảo vệ dữ liệu ra sao và phải đưa ra bằng chứng nào. Khi các nghĩa vụ được nối với yêu cầu, người chịu trách nhiệm và phép kiểm chứng, chúng trở thành một phần có thể quản lý của bối cảnh sản phẩm thay vì những ghi chú rời rạc chỉ được xem lại khi có sự cố hoặc kiểm toán.

