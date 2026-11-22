# Đánh giá độ đại diện và các sai lệch của dữ liệu được chọn

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích độ đại diện của dữ liệu kiểm thử và xác định quần thể mục tiêu theo hành vi, nghiệp vụ và rủi ro cần kiểm tra.
- Phân biệt dữ liệu đại diện với dữ liệu có tần suất giống production, dữ liệu biên và dữ liệu được chọn có chủ đích theo rủi ro.
- Nhận diện sai lệch do chọn mẫu, dữ liệu thuận tiện, survivorship, thời gian, mất cân bằng lớp, thiếu dữ liệu, nhãn và môi trường.
- Chọn nguồn dữ liệu production đã xử lý, dữ liệu tổng hợp, dữ liệu nhân tạo hoặc tập dữ liệu lai theo mục tiêu và giới hạn bảo mật.
- Thiết kế mẫu phân tầng, mẫu theo rủi ro, mẫu biên và mẫu cho các tổ hợp quan trọng.
- Đánh giá phân bố, quan hệ giữa trường dữ liệu, tính toàn vẹn và độ mới để xác định dữ liệu có phù hợp hay không.
- Phát hiện rò rỉ dữ liệu, dữ liệu trùng lặp và các giả định làm sai lệch kết quả kiểm thử.
- Ghi nhận nguồn gốc, tiêu chí chấp nhận, giới hạn và quyết định sử dụng dữ liệu một cách có thể truy vết.

## 1. Vì sao cần đánh giá độ đại diện của dữ liệu?

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, dữ liệu kiểm thử là một phần của bằng chứng xác minh. Dữ liệu quyết định hệ thống đi qua nhánh nào, truy vấn trả về bao nhiêu bản ghi, quy tắc nghiệp vụ được áp dụng ra sao và các thành phần phối hợp trong điều kiện nào. Một bộ test có thể có nhiều ca nhưng vẫn bỏ sót lỗi nếu dữ liệu được chọn quá đơn giản, chỉ phản ánh một nhóm người dùng hoặc không thể hiện những quan hệ xuất hiện trong thực tế.

Ví dụ, một ứng dụng bán hàng được kiểm thử với 20 sản phẩm có giá gần bằng nhau, tất cả đều còn hàng và chỉ dùng một phương thức thanh toán. Bộ test có thể xác nhận luồng đặt hàng cơ bản, nhưng không đại diện cho trường hợp giỏ hàng có nhiều loại sản phẩm, tồn kho thấp, mã giảm giá, địa chỉ khác vùng, thanh toán thất bại hoặc đơn hàng có nhiều trạng thái. Lỗi về tính phí vận chuyển, giới hạn khuyến mại hoặc cập nhật tồn kho có thể không xuất hiện.

Độ đại diện không chỉ là việc dữ liệu trông giống dữ liệu thật. Cần xác định dữ liệu có phản ánh những đặc điểm quan trọng đối với mục tiêu kiểm thử hay không. Một tập dữ liệu nhỏ vẫn có thể đại diện tốt cho một quy tắc cụ thể nếu nó bao phủ đúng các phân vùng, điều kiện và quan hệ cần xác minh. Ngược lại, một bản sao lớn của dữ liệu production vẫn có thể thiếu đại diện nếu dữ liệu đã bị lọc, làm mất các nhóm hiếm hoặc không còn giữ được quan hệ cần thiết.

Đánh giá độ đại diện giúp nhóm:

- Phát hiện các nhóm người dùng, giao dịch, trạng thái hoặc điều kiện chưa được kiểm tra.
- Tránh kết luận sai từ một mẫu quá thuận tiện hoặc quá đồng nhất.
- Phân biệt lỗi của sản phẩm với lỗi do dữ liệu kiểm thử không phù hợp.
- Xác định trường hợp hiếm nhưng có hậu quả lớn cần được đưa vào mẫu có chủ đích.
- Giữ được các quan hệ dữ liệu và trình tự sự kiện cần thiết để kiểm tra hành vi xuyên hệ thống.
- So sánh kết quả giữa các lần chạy, môi trường và phiên bản trên cùng một cơ sở dữ liệu có kiểm soát.

## 2. Độ đại diện là gì?

Độ đại diện (representativeness) mô tả mức độ mà một tập dữ liệu phản ánh những đặc điểm của quần thể mục tiêu có liên quan đến câu hỏi kiểm thử. Quần thể mục tiêu không nhất thiết là toàn bộ dữ liệu production. Nó là nhóm đối tượng, giao dịch, trạng thái hoặc sự kiện mà phép kiểm thử cần đưa ra kết luận.

Ví dụ:

- Khi kiểm tra quy tắc phí vận chuyển, quần thể mục tiêu có thể là các đơn hàng theo vùng giao, trọng lượng, giá trị và loại dịch vụ vận chuyển.
- Khi kiểm tra phân quyền, quần thể mục tiêu có thể là các kết hợp người dùng, vai trò, tenant, tài nguyên và hành động.
- Khi kiểm tra hiệu năng truy vấn, quần thể mục tiêu có thể là dữ liệu với kích thước, độ lệch phân bố, cardinality và tỷ lệ truy cập tương tự tải dự kiến.
- Khi kiểm tra xử lý sự kiện, quần thể mục tiêu có thể là các chuỗi sự kiện đúng thứ tự, trễ, lặp hoặc thiếu.

### 2.1. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Quần thể mục tiêu | Toàn bộ đối tượng hoặc tình huống mà kết luận kiểm thử hướng đến | Hệ thống được kỳ vọng phục vụ nhóm nào và hành vi nào? |
| Khung chọn mẫu | Danh sách hoặc nguồn có thể lấy các phần tử mẫu | Dữ liệu nào thực sự có sẵn để chọn? |
| Mẫu dữ liệu | Tập con được chọn từ khung mẫu hoặc được tạo ra | Mẫu có phản ánh các đặc điểm quan trọng không? |
| Đơn vị mẫu | Đối tượng được chọn, ví dụ người dùng, đơn hàng hoặc phiên | Mỗi phần tử được đếm và chọn theo đơn vị nào? |
| Đặc trưng liên quan | Thuộc tính ảnh hưởng đến hành vi cần kiểm tra | Trường nào làm thay đổi nhánh, kết quả hoặc tải? |
| Sai lệch (bias) | Xu hướng có hệ thống khiến mẫu khác quần thể theo cách ảnh hưởng kết luận | Nhóm nào hoặc điều kiện nào bị thiếu/thừa? |

Không xác định rõ đơn vị mẫu có thể dẫn đến kết luận sai. Ví dụ, 10.000 request có thể đến từ 100 người dùng rất tích cực; con số đó không đại diện cho 10.000 người dùng độc lập. Tương tự, 1.000 đơn hàng có thể chỉ thuộc một tenant hoặc một vùng địa lý.

### 2.2. Độ đại diện phụ thuộc mục tiêu

Không tồn tại một bộ dữ liệu đại diện cho mọi phép kiểm thử. Một tập dữ liệu phù hợp để kiểm tra quy tắc tính thuế có thể quá nhỏ để kiểm tra hiệu năng truy vấn. Dữ liệu phục vụ kiểm tra phân quyền cần nhiều kết hợp vai trò và tài nguyên; dữ liệu phục vụ kiểm tra giao diện có thể cần phân bố thiết bị, ngôn ngữ và trạng thái phiên.

Trước khi chọn dữ liệu, hãy viết rõ câu hỏi kiểm thử. Ví dụ: “Với các đơn hàng có trọng lượng, vùng giao và loại dịch vụ khác nhau, hệ thống có tính đúng phí vận chuyển không?” Câu hỏi này cho biết những đặc trưng nào phải xuất hiện trong dữ liệu. Nếu chỉ lấy ngẫu nhiên đơn hàng mà không xét vùng giao hoặc trọng lượng, mẫu có thể bỏ qua các điều kiện quyết định.

## 3. Đại diện không có nghĩa là sao chép nguyên phân bố production

Một hiểu lầm thường gặp là dữ liệu kiểm thử chỉ đại diện khi tỷ lệ từng loại bản ghi giống hệt production. Điều này không đúng cho mọi mục tiêu.

Nếu mục tiêu là đánh giá tải sử dụng thông thường, tỷ trọng giao dịch có thể cần gần với hành vi thực tế. Nhưng nếu mục tiêu là kiểm tra quy tắc từ chối, giới hạn, quyền truy cập hoặc lỗi hiếm, chỉ lấy mẫu theo tần suất production có thể khiến các trường hợp quan trọng gần như không xuất hiện.

Ví dụ, 99,8% giao dịch thanh toán thành công và 0,2% bị từ chối. Một mẫu ngẫu nhiên nhỏ có thể không có giao dịch bị từ chối nào. Đối với kiểm thử luồng thanh toán, cần chủ động bổ sung các trường hợp từ chối, timeout và callback trễ. Tỷ lệ trong bộ test vì thế có thể khác production, nhưng mẫu vẫn phù hợp với mục tiêu kiểm tra.

Hãy phân biệt:

- **Mẫu theo phân bố sử dụng**: phản ánh tần suất hoặc tỷ lệ hành vi thường gặp, hữu ích cho một số kiểm thử tải và trải nghiệm.
- **Mẫu theo phân vùng**: bảo đảm mỗi nhóm dữ liệu hoặc điều kiện quan trọng có đại diện.
- **Mẫu theo rủi ro**: tăng cường trường hợp hiếm nhưng có hậu quả lớn hoặc dễ phát sinh lỗi.
- **Mẫu biên/đối kháng**: tập trung vào giới hạn, dữ liệu bất thường, đầu vào sai và tổ hợp có thể phá vỡ giả định.

Một bộ dữ liệu kiểm thử chất lượng thường kết hợp các cách chọn này. Tỷ lệ giữa chúng cần được ghi nhận để người đọc hiểu vì sao bộ test không giống tỷ lệ production.

## 4. Xác định các chiều cần đại diện

Những chiều cần xem xét phụ thuộc loại hệ thống và câu hỏi kiểm thử. Không nên chọn dữ liệu chỉ dựa trên một vài trường dễ lấy.

### 4.1. Đối tượng và nhóm người dùng

Hãy xem xét các nhóm có thể có hành vi hoặc quyền khác nhau:

- Người dùng mới, người dùng hoạt động lâu năm và tài khoản không hoạt động.
- Khách chưa đăng nhập, người dùng đã xác thực và người dùng có quyền đặc biệt.
- Người dùng thuộc các tenant, tổ chức hoặc vùng khác nhau.
- Tài khoản bị khóa, hết hạn, chờ xác minh hoặc đã bị thu hồi quyền.
- Người dùng có thiết bị, ngôn ngữ hoặc khả năng truy cập khác nhau.

Không nên chỉ lấy dữ liệu từ nhóm người dùng hoạt động nhiều nhất nếu mục tiêu còn bao gồm onboarding, khôi phục tài khoản hoặc quyền của người dùng ít hoạt động.

### 4.2. Giá trị và phân bố số liệu

Đối với trường số, hãy xem xét:

- Giá trị nhỏ nhất, lớn nhất và vùng phổ biến.
- Giá trị bằng 0, âm, rỗng hoặc không hợp lệ nếu có thể xuất hiện ở đầu vào.
- Các giá trị sát giới hạn và ngay hai phía của giới hạn.
- Phân bố lệch, đuôi dài và ngoại lệ.
- Giá trị lặp lại nhiều và giá trị gần như duy nhất.
- Đơn vị đo, độ chính xác và quy tắc làm tròn.

Ví dụ, số lượng sản phẩm thường nằm trong khoảng 1 đến 3 nhưng hệ thống cho phép tối đa 100. Chỉ lấy các đơn hàng có số lượng 1 hoặc 2 sẽ không kiểm tra được giới hạn, tính toán tổng và hành vi khi giỏ hàng lớn.

### 4.3. Danh mục, trạng thái và quan hệ

Đối với dữ liệu phân loại hoặc trạng thái, hãy đưa vào:

- Các giá trị phổ biến và giá trị hiếm.
- Trạng thái khởi tạo, trung gian, cuối và trạng thái lỗi.
- Các chuyển tiếp hợp lệ và không hợp lệ.
- Các kết hợp giữa loại đối tượng và trạng thái.
- Quan hệ một-một, một-nhiều và nhiều-nhiều.
- Bản ghi không có quan hệ, quan hệ thiếu hoặc quan hệ không hợp lệ nếu hệ thống phải xử lý.

Một bộ dữ liệu chỉ có đơn hàng đã giao sẽ không đủ để kiểm tra hủy đơn, thanh toán đang chờ, hoàn tiền hoặc xử lý giao hàng thất bại.

### 4.4. Thời gian và trình tự

Nhiều quy tắc phụ thuộc thời điểm và thứ tự:

- Dữ liệu mới, cũ và gần hết hạn.
- Đầu/cuối ngày, cuối tháng, năm nhuận và múi giờ.
- Ngày lễ, mùa cao điểm hoặc chu kỳ thanh toán.
- Sự kiện đến đúng thứ tự, đến trễ, lặp hoặc đảo thứ tự.
- Khoảng cách thời gian giữa tạo, cập nhật, thanh toán và hủy.
- Trạng thái kéo dài hoặc không thay đổi trong thời gian dài.

Nếu hệ thống xử lý subscription, bảo hành hoặc token, chỉ dùng dữ liệu có ngày hiện tại gần nhau sẽ bỏ sót nhiều trường hợp hết hạn và chuyển kỳ.

### 4.5. Kênh, nền tảng và môi trường

Với ứng dụng đa nền tảng, dữ liệu có thể cần phản ánh:

- Trình duyệt, hệ điều hành, phiên bản ứng dụng và loại thiết bị.
- Ngôn ngữ, định dạng ngày/giờ, tiền tệ và locale.
- Mạng nhanh, mạng chậm, mất kết nối và chuyển mạng.
- Cấu hình feature flag hoặc phiên bản API.
- Tenant, vùng triển khai và cấu hình môi trường.

Không cần mọi tổ hợp thiết bị và cấu hình đều có mặt trong mọi bộ test. Hãy chọn ma trận đại diện theo lượng sử dụng, khác biệt kỹ thuật và mức độ rủi ro.

### 4.6. Kích thước và đặc điểm vận hành

Đối với kiểm thử hiệu năng hoặc khả năng mở rộng, dữ liệu cần phản ánh:

- Tổng số bản ghi và tốc độ tăng dữ liệu.
- Kích thước payload, tệp và trường văn bản.
- Cardinality của khóa và mức độ trùng lặp.
- Phân bố dữ liệu theo tenant, khách hàng hoặc phân vùng.
- Tỷ lệ đọc/ghi, cập nhật đồng thời và độ nóng của khóa.
- Mức cache hit/miss và tính cục bộ của truy cập.

Một triệu bản ghi có phân bố đều có thể tạo tải khác hẳn một triệu bản ghi tập trung vào một tenant hoặc một khóa nóng. Vì vậy, kích thước tổng không đủ mô tả dữ liệu hiệu năng.

## 5. Nhận diện các dạng sai lệch dữ liệu

Sai lệch có thể xuất hiện ở khâu thu thập, lọc, làm sạch, tạo dữ liệu, chọn mẫu hoặc cấu hình môi trường. Cần phân tích sai lệch nào có thể làm thay đổi kết luận kiểm thử.

### 5.1. Sai lệch chọn mẫu (selection/sampling bias)

Mẫu được lấy từ một nguồn hoặc cách chọn khiến một số nhóm có cơ hội xuất hiện cao hơn nhóm khác. Ví dụ, dữ liệu lấy từ người dùng đăng nhập gần đây sẽ bỏ sót tài khoản cũ, tài khoản bị khóa hoặc người dùng ít hoạt động.

Dấu hiệu:

- Chỉ một tenant, vùng, kênh hoặc loại tài khoản xuất hiện.
- Dữ liệu lấy từ một khoảng thời gian thuận tiện.
- Một số trạng thái không có vì quy trình lọc đã loại bỏ chúng.
- Người tạo dữ liệu chọn các trường hợp dễ tạo hoặc dễ kiểm tra.

### 5.2. Sai lệch sống sót (survivorship bias)

Chỉ giữ những đối tượng còn tồn tại hoặc giao dịch hoàn tất, bỏ qua các đối tượng đã bị hủy, thất bại, xóa hoặc rời khỏi hệ thống. Ví dụ, chỉ lấy đơn hàng giao thành công sẽ không phản ánh lỗi thanh toán, hoàn tiền, giao hàng thất bại hoặc đơn bị hủy.

Để giảm sai lệch, hãy xác định các trạng thái kết thúc và nguyên nhân rời khỏi quy trình, sau đó bảo đảm chúng có mặt nếu thuộc phạm vi kiểm thử.

### 5.3. Sai lệch thuận tiện (convenience bias)

Nhóm chọn dữ liệu dễ truy cập hoặc dễ chuẩn bị thay vì dữ liệu phản ánh mục tiêu. Ví dụ, mọi test dùng một khách hàng, một địa chỉ và một sản phẩm vì fixture đó có sẵn. Dữ liệu thuận tiện hữu ích cho test đơn vị nhỏ, nhưng không nên mặc nhiên đại diện cho hành vi đa dạng.

### 5.4. Sai lệch thời gian (temporal bias)

Mẫu chỉ lấy trong một giai đoạn nên không phản ánh mùa vụ, thay đổi chính sách hoặc hành vi theo thời gian. Ví dụ, dữ liệu đơn hàng trong tháng bình thường không đại diện cho đợt khuyến mại lớn, khi số lượng đơn, tỷ lệ thanh toán và phân bố giỏ hàng có thể thay đổi.

### 5.5. Mất cân bằng lớp (class imbalance)

Một số loại kết quả rất hiếm so với loại phổ biến. Ví dụ, phần lớn yêu cầu là hợp lệ, còn yêu cầu bị từ chối hoặc gian lận chiếm tỷ lệ nhỏ. Mẫu ngẫu nhiên có thể không có đủ trường hợp hiếm để kiểm tra.

Trong kiểm thử phần mềm, cần chủ động đưa các trường hợp hiếm vào bộ test theo rủi ro. Nếu hệ thống có mô hình phân loại hoặc phát hiện bất thường, mất cân bằng còn ảnh hưởng đến cách đánh giá precision, recall và các chỉ số liên quan; cần chọn tập đánh giá phản ánh mục tiêu triển khai và ghi rõ cách lấy mẫu.

### 5.6. Sai lệch do thiếu dữ liệu (missing-data bias)

Trường bị thiếu có thể không xuất hiện ngẫu nhiên. Ví dụ, địa chỉ thiếu ở nhóm khách hàng mới, hoặc trường lý do hủy chỉ có ở giao dịch thất bại. Nếu loại bỏ mọi bản ghi thiếu dữ liệu, nhóm có thể loại luôn những trường hợp cần kiểm tra nhất.

Phân biệt:

- Thiếu do quy tắc nghiệp vụ cho phép.
- Thiếu do người dùng không cung cấp.
- Thiếu do lỗi đồng bộ hoặc nguồn dữ liệu.
- Thiếu do xử lý ẩn danh hoặc lọc dữ liệu.

Không tự điền giá trị mặc định nếu chưa hiểu ý nghĩa của việc thiếu. Dữ liệu null, trường không tồn tại, chuỗi rỗng và giá trị “không biết” có thể mang ngữ nghĩa khác nhau.

### 5.7. Sai lệch đo lường và nhãn (measurement/label bias)

Giá trị được ghi nhận có thể không phản ánh chính xác sự kiện. Ví dụ, thời điểm tạo đơn bị ghi theo múi giờ khác, nhãn “thanh toán thành công” được gán ngay khi nhận request thay vì khi giao dịch được xác nhận, hoặc mã vùng không được chuẩn hóa.

Hãy xác minh nguồn, định nghĩa, đơn vị, thời điểm và quy tắc gán nhãn. Nếu nhãn sai, việc chọn mẫu cân bằng vẫn không tạo ra bằng chứng đúng.

### 5.8. Sai lệch do tạo dữ liệu tổng hợp

Dữ liệu tổng hợp có thể quá sạch, quá đều hoặc thiếu các tương quan và ngoại lệ có thật. Một generator tạo ngày sinh, địa chỉ và số tiền độc lập có thể sinh ra bản ghi hợp lệ về kiểu nhưng không hợp lý về nghiệp vụ. Ví dụ, ngày giao hàng trước ngày đặt hàng hoặc khách hàng ở một quốc gia nhưng dùng mã tiền tệ không phù hợp.

Generator cần bảo toàn các ràng buộc và quan hệ quan trọng, đồng thời tạo được trường hợp biên và dữ liệu bất thường có chủ đích.

### 5.9. Sai lệch môi trường (environment bias)

Dữ liệu có thể đại diện nhưng kết quả vẫn không phản ánh thực tế nếu môi trường khác biệt đáng kể: cấu hình cache, index, phiên bản database, quota, số instance, feature flag hoặc dịch vụ phụ thuộc. Báo cáo cần phân biệt sai lệch dữ liệu với sai lệch môi trường.

### 5.10. Rò rỉ dữ liệu (data leakage)

Rò rỉ xảy ra khi dữ liệu hoặc thông tin không được phép ảnh hưởng đến kết quả kiểm thử, khiến kết quả có vẻ tốt hơn thực tế hoặc không còn độc lập. Trong kiểm thử phần mềm, ví dụ gồm test dùng dữ liệu được tạo từ chính kết quả mong đợi, fixture vô tình chứa trạng thái do test khác tạo, hoặc dữ liệu đầu vào bao gồm thông tin tương lai mà hệ thống tại thời điểm xử lý chưa thể biết.

Với hệ thống học máy, data leakage còn có thể xảy ra khi đặc trưng chứa thông tin được tạo sau thời điểm dự đoán hoặc khi cùng một thực thể xuất hiện trong cả tập huấn luyện và tập đánh giá. Cần xác định đúng thời điểm và ranh giới dữ liệu khi thiết kế test.

## 6. Chọn nguồn dữ liệu phù hợp

Không có nguồn dữ liệu duy nhất phù hợp cho mọi tình huống. Lựa chọn cần cân bằng độ đại diện, quyền sử dụng, tính bảo mật, khả năng tái tạo và chi phí duy trì.

### 6.1. Dữ liệu production đã được xử lý

Có thể dùng bản trích xuất từ production sau khi xử lý dữ liệu nhạy cảm và được phê duyệt theo chính sách.

Ưu điểm:

- Phản ánh được phân bố và một số quan hệ thực tế.
- Có thể giữ được độ lệch, cardinality và mẫu truy cập phức tạp.
- Hữu ích cho kiểm thử hồi quy dữ liệu, migration và hiệu năng khi phù hợp.

Hạn chế:

- Có nguy cơ tái nhận diện nếu chỉ che một vài trường định danh.
- Dữ liệu có thể chứa secret, thông tin cá nhân hoặc nội dung không được phép sao chép.
- Bản trích xuất nhanh lỗi thời và có thể không đại diện cho giai đoạn khác.
- Việc làm sạch có thể phá vỡ quan hệ hoặc phân bố cần kiểm tra.

Không coi việc xóa tên hoặc thay email là đủ để bảo vệ dữ liệu. Nhiều trường kết hợp vẫn có thể nhận diện một cá nhân. Việc sử dụng phải tuân thủ quy trình phê duyệt, tối thiểu hóa dữ liệu và đánh giá nguy cơ tái nhận diện.

### 6.2. Dữ liệu tổng hợp (synthetic data)

Dữ liệu tổng hợp được tạo từ quy tắc, generator hoặc mô hình để mô phỏng những đặc điểm cần thiết mà không sao chép trực tiếp từng bản ghi production.

Ưu điểm:

- Có thể tạo dữ liệu với số lượng và trạng thái xác định.
- Dễ tái lập bằng seed và phiên bản generator.
- Có thể tạo trường hợp hiếm, dữ liệu biên và dữ liệu lỗi có chủ đích.
- Giảm nhu cầu đưa dữ liệu thật vào môi trường test nếu được thiết kế đúng.

Hạn chế:

- Có thể không giữ đúng phân bố hoặc tương quan thực tế.
- Quy tắc generator có thể mã hóa giả định sai.
- Dữ liệu nhìn hợp lệ nhưng không phản ánh hành vi của người dùng thật.
- Cần bảo trì generator khi schema và nghiệp vụ thay đổi.

### 6.3. Dữ liệu nhân tạo theo kịch bản

Nhóm có thể tự tạo tập nhỏ cho một kịch bản cụ thể, chẳng hạn một đơn hàng có ba sản phẩm, một khách hàng bị khóa hoặc một callback bị lặp. Đây là cách hiệu quả cho unit/component test và test hồi quy có mục tiêu.

Tập kịch bản không nhằm mô phỏng toàn bộ quần thể. Hãy ghi rõ mục đích và không dùng một tập nhỏ như vậy để suy luận về phân bố sử dụng hoặc công suất production.

### 6.4. Tập dữ liệu lai

Một tập dữ liệu lai có thể kết hợp:

- Một mẫu đã được xử lý từ dữ liệu thực để giữ phân bố hoặc quan hệ quan trọng.
- Dữ liệu tổng hợp để mở rộng số lượng và tạo nhóm thiếu.
- Kịch bản nhân tạo cho trường hợp biên, lỗi và rủi ro hiếm.
- Dữ liệu chuẩn (golden records) để xác minh kết quả mong đợi.

Khi kết hợp, cần gắn nguồn gốc và phân biệt từng nhóm. Không để bản ghi tổng hợp vô tình được hiểu là quan sát production hoặc ngược lại.

### 6.5. So sánh nguồn dữ liệu

| Nguồn | Phù hợp khi | Rủi ro cần kiểm soát |
|---|---|---|
| Production đã xử lý | Cần giữ phân bố, quan hệ hoặc quy mô thực tế | Tái nhận diện, quyền sử dụng, độ mới và biến dạng do xử lý. |
| Synthetic generator | Cần dữ liệu lớn, tái lập và có thể điều khiển | Sai tương quan, generator lệch và dữ liệu quá sạch. |
| Kịch bản nhân tạo | Kiểm tra quy tắc, lỗi và biên cụ thể | Không đại diện cho tần suất hoặc phân bố toàn hệ thống. |
| Golden dataset | Xác minh kết quả chuẩn và hồi quy | Phạm vi nhỏ, có thể lỗi thời khi quy tắc thay đổi. |
| Tập lai | Cần đồng thời phân bố thực tế và trường hợp rủi ro | Nguồn gốc, quy tắc trộn và tính nhất quán khó quản lý hơn. |

## 7. Thiết kế phương pháp chọn mẫu

Phương pháp chọn mẫu cần phản ánh mục tiêu và cấu trúc của quần thể. Có thể kết hợp nhiều phương pháp trong cùng một bộ dữ liệu.

### 7.1. Lấy mẫu ngẫu nhiên đơn giản

Mỗi phần tử trong khung mẫu có cơ hội được chọn như nhau. Phương pháp này hữu ích khi khung mẫu đầy đủ và quần thể tương đối đồng nhất theo các đặc trưng liên quan.

Hạn chế: nhóm nhỏ hoặc trường hợp hiếm có thể không xuất hiện trong mẫu nhỏ. Nếu cần kiểm tra trạng thái hiếm hoặc rủi ro cao, không nên dựa hoàn toàn vào lấy mẫu ngẫu nhiên.

### 7.2. Lấy mẫu phân tầng (stratified sampling)

Chia quần thể thành các tầng theo đặc trưng quan trọng, sau đó chọn mẫu trong từng tầng. Ví dụ, chia đơn hàng theo vùng giao, loại thanh toán hoặc trạng thái rồi chọn dữ liệu từ mỗi nhóm.

Có hai cách thường gặp:

- **Phân bổ tỷ lệ**: số phần tử mỗi tầng gần với tỷ trọng của tầng trong quần thể.
- **Phân bổ không tỷ lệ**: tăng mẫu ở tầng nhỏ nhưng quan trọng để bảo đảm có đủ trường hợp kiểm tra.

Phân bổ không tỷ lệ hữu ích cho kiểm thử rủi ro. Khi báo cáo thống kê về quần thể, cần lưu trọng số hoặc tỷ lệ lấy mẫu để tránh diễn giải sai tần suất.

### 7.3. Lấy mẫu theo cụm hoặc theo nhóm vận hành

Có thể chọn theo tenant, vùng, phiên, thiết bị hoặc nhóm giao dịch khi dữ liệu có cấu trúc cụm. Tuy nhiên, các phần tử trong cùng cụm thường tương quan; không nên coi chúng như các quan sát độc lập nếu dùng để suy luận thống kê.

### 7.4. Lấy mẫu có chủ đích theo rủi ro

Chọn trực tiếp các trường hợp có hậu quả cao, lịch sử lỗi hoặc điều kiện đặc biệt. Ví dụ: tài khoản bị khóa, giao dịch gần hạn mức, đơn hàng có nhiều loại phí, webhook lặp và cập nhật đồng thời.

Phương pháp này rất phù hợp để tạo bộ hồi quy bảo vệ rủi ro. Nó không đại diện cho tần suất production và không nên được dùng để ước lượng tỷ lệ lỗi tự nhiên nếu không điều chỉnh cách lấy mẫu.

### 7.5. Lấy mẫu biên và trường hợp bất thường

Chọn giá trị nhỏ nhất, lớn nhất, sát giới hạn, giá trị rỗng, dữ liệu sai định dạng hoặc kết hợp bất thường. Trường hợp bất thường cần được phân loại: đầu vào hợp lệ hiếm, đầu vào không hợp lệ mà hệ thống phải từ chối, hay dữ liệu hỏng từ nguồn phụ thuộc.

### 7.6. Lấy mẫu theo tổ hợp

Khi nhiều chiều kết hợp tạo ra số tổ hợp lớn, có thể dùng pairwise hoặc combinatorial testing để chọn một tập con bao phủ các cặp hoặc tổ hợp được xác định. Cách này giảm số lượng nhưng không bảo đảm phát hiện lỗi chỉ xuất hiện ở tổ hợp bậc cao hơn. Các kết hợp có rủi ro đặc biệt cần được thêm riêng.

### 7.7. Lấy mẫu theo thời gian

Chọn dữ liệu từ nhiều khoảng thời gian để phản ánh mùa vụ, thay đổi chính sách và xu hướng. Với hệ thống có trạng thái, cần giữ chuỗi sự kiện theo thời gian thay vì chỉ chọn các bản ghi riêng lẻ.

## 8. Giữ quan hệ và tính toàn vẹn của dữ liệu

Một tập dữ liệu có thể có từng bản ghi hợp lệ nhưng toàn bộ tập lại không hợp lý nếu quan hệ bị phá vỡ.

### 8.1. Quan hệ khóa và tham chiếu

Kiểm tra:

- Khóa chính là duy nhất trong phạm vi yêu cầu.
- Khóa ngoại tham chiếu đến bản ghi tồn tại.
- Quan hệ một-nhiều có số lượng phù hợp.
- Không tạo quan hệ vòng hoặc trạng thái không hợp lệ nếu hệ thống không cho phép.
- Các bản ghi thuộc đúng tenant hoặc chủ sở hữu.

Nếu thay ID để ẩn danh, cần thay đồng bộ ở mọi bảng hoặc sự kiện liên quan. Chỉ thay khóa ở một bảng có thể làm hỏng liên kết và khiến test thất bại vì dữ liệu sai cấu trúc.

### 8.2. Tương quan giữa các trường

Không nên tạo mọi trường độc lập nếu trong thực tế chúng có quan hệ. Ví dụ:

- Mã tiền tệ liên quan đến quốc gia hoặc thị trường.
- Phí vận chuyển liên quan đến vùng, trọng lượng và loại dịch vụ.
- Ngày giao hàng phải sau ngày đặt hàng theo quy tắc nghiệp vụ.
- Trạng thái thanh toán phải tương thích với trạng thái đơn hàng.
- Vai trò và quyền được cấp phụ thuộc vào loại tài khoản hoặc tổ chức.
- Số lượng hàng tồn và số lượng bán không thể tùy ý mâu thuẫn nếu đang kiểm tra tính toàn vẹn.

Generator cần mã hóa những quan hệ này hoặc cố ý tạo dữ liệu vi phạm để kiểm tra cách hệ thống từ chối.

### 8.3. Trình tự sự kiện

Với dữ liệu sự kiện, cần giữ timestamp, sequence, correlation ID và quan hệ giữa event. Nếu chỉ trích xuất trạng thái cuối mà không có lịch sử, nhóm có thể không kiểm tra được retry, xử lý trùng, sự kiện đến trễ hoặc chuyển trạng thái không hợp lệ.

### 8.4. Bất biến dữ liệu

Định nghĩa các bất biến cần giữ, ví dụ:

- Tổng các dòng hàng cộng thuế và phí bằng tổng đơn hàng theo quy tắc làm tròn.
- Mỗi giao dịch thanh toán được liên kết với đúng đơn hàng.
- Một khóa idempotency không tạo nhiều giao dịch thành công.
- Đơn hàng đã hủy không được chuyển thẳng sang đã giao nếu quy tắc không cho phép.
- Mỗi bản ghi thuộc một tenant hợp lệ và không rò rỉ sang tenant khác.

Kiểm tra bất biến trước và sau khi nạp dữ liệu giúp phân biệt lỗi generator với lỗi của hệ thống.

## 9. Đánh giá độ đại diện bằng số liệu

Đánh giá định lượng giúp nhận diện khác biệt giữa mẫu và quần thể, nhưng phải chọn phép đo phù hợp với loại dữ liệu và mục tiêu.

### 9.1. Biến phân loại

So sánh tần suất và tỷ lệ của từng nhóm: trạng thái, phương thức thanh toán, vùng, vai trò, thiết bị hoặc loại giao dịch. Có thể dùng bảng tần suất và biểu đồ cột.

Ví dụ, nếu production có 60% đơn giao tiêu chuẩn, 30% giao nhanh và 10% nhận tại cửa hàng, nhưng mẫu test có 100% giao tiêu chuẩn, mẫu không đại diện cho hành vi lựa chọn dịch vụ giao hàng.

### 9.2. Biến số

So sánh:

- Trung bình và trung vị.
- Độ lệch chuẩn hoặc độ phân tán phù hợp.
- Các phân vị như p5, p50, p90, p95 và p99.
- Min, max và các giá trị sát ngưỡng.
- Histogram hoặc mật độ phân bố.
- Tỷ lệ ngoại lệ và quy tắc xử lý ngoại lệ.

Trung bình giống nhau không bảo đảm phân bố giống nhau. Hai tập có thể cùng trung bình nhưng một tập tập trung quanh giá trị giữa, còn tập kia có hai cụm rất khác nhau.

### 9.3. Dữ liệu thiếu và chất lượng

So sánh tỷ lệ thiếu theo từng trường và theo từng nhóm. Nếu tỷ lệ thiếu chung là 2% nhưng nhóm tài khoản mới có 30% thiếu địa chỉ, số liệu tổng thể có thể che giấu một sai lệch quan trọng.

### 9.4. Tương quan và phân bố kết hợp

Ngoài từng trường riêng lẻ, cần kiểm tra một số cặp hoặc nhóm trường có quan hệ nghiệp vụ. Ví dụ, tỷ lệ giao hàng thất bại theo vùng và loại dịch vụ; tỷ lệ thanh toán từ chối theo phương thức và giá trị giao dịch; số bản ghi theo tenant và trạng thái.

Không thể kết luận mẫu đại diện chỉ từ việc từng cột có phân bố gần giống. Quan hệ giữa các cột có thể đã bị phá vỡ.

### 9.5. Một số phép đo thống kê

Tùy loại dữ liệu, nhóm có thể sử dụng:

- **Kolmogorov–Smirnov (KS)** cho một số so sánh phân bố của biến số liên tục.
- **Chi-square** để kiểm tra khác biệt tần suất giữa các nhóm phân loại khi các giả định phù hợp.
- **Jensen–Shannon divergence** để so sánh hai phân bố xác suất theo cách đối xứng và hữu hạn.
- **Population Stability Index (PSI)** như một chỉ báo thay đổi phân bố trong một số quy trình theo dõi dữ liệu.
- So sánh quantile, histogram, missing rate và các tỷ lệ nghiệp vụ theo phân nhóm.

Không có một ngưỡng thống kê phổ quát để kết luận dữ liệu đủ đại diện cho mọi mục tiêu. Kết quả phụ thuộc kích thước mẫu, cách chia nhóm, giả định thống kê và mức độ quan trọng của khác biệt. Một khác biệt nhỏ về tỷ lệ ở nhóm quyền truy cập có thể quan trọng hơn khác biệt lớn ở trường mô tả không ảnh hưởng hành vi.

### 9.6. Đánh giá drift theo thời gian

Nếu dữ liệu được cập nhật thường xuyên, hãy so sánh các phiên bản hoặc cửa sổ thời gian để phát hiện drift. Drift có thể đến từ thay đổi người dùng, sản phẩm, chính sách, mùa vụ hoặc quy trình thu thập. Khi phân bố thay đổi, cần xác định test data có còn phù hợp với mục tiêu hiện tại không.

## 10. Kiểm tra dữ liệu trước khi đưa vào bộ test

Một quy trình kiểm tra dữ liệu nên gồm cả kiểm tra cấu trúc và kiểm tra ý nghĩa.

### 10.1. Kiểm tra cấu trúc

- Schema, kiểu dữ liệu và trường bắt buộc.
- Định dạng ngày/giờ, số, tiền tệ và mã hóa ký tự.
- Độ dài tối đa, miền giá trị và quy tắc null.
- Khóa chính, khóa ngoại và uniqueness.
- Phiên bản schema và khả năng tương thích.

### 10.2. Kiểm tra ý nghĩa nghiệp vụ

- Các trạng thái có hợp lệ và tương thích nhau không?
- Thứ tự thời gian có hợp lý không?
- Tổng tiền, số lượng và phí có thỏa bất biến không?
- Quan hệ tenant, chủ sở hữu và quyền có chính xác không?
- Giá trị thiếu có mang đúng ngữ nghĩa không?
- Các trường hợp lỗi có được đánh dấu đúng loại không?

### 10.3. Kiểm tra độ đại diện

- Các nhóm mục tiêu có xuất hiện đủ không?
- Các nhóm hiếm có cần tăng mẫu theo rủi ro không?
- Phân bố và tương quan quan trọng có gần với mục tiêu không?
- Có nhóm nào bị loại do bộ lọc hoặc quy trình ẩn danh không?
- Dữ liệu có phản ánh thời gian, mùa vụ hoặc trạng thái cần thiết không?
- Tập dữ liệu có quá sạch hoặc quá đồng nhất không?

### 10.4. Kiểm tra tái lập

- Nguồn, ngày trích xuất, truy vấn và phiên bản generator có được lưu không?
- Có seed hoặc cách tạo lại cùng tập dữ liệu không?
- Dữ liệu có được version hóa hoặc gắn checksum không?
- Có quy trình nạp, reset và cleanup xác định không?
- Thay đổi schema hoặc generator có tạo diff và review không?

## 11. Bảo vệ dữ liệu và quyền riêng tư

Độ đại diện không biện minh cho việc sao chép dữ liệu nhạy cảm không cần thiết. Cần xác định quyền sử dụng, mục đích, phạm vi, nơi lưu trữ và thời hạn giữ dữ liệu.

### 11.1. Giảm thiểu dữ liệu

Chỉ đưa vào những trường cần thiết cho câu hỏi kiểm thử. Nếu test tính phí vận chuyển không cần email hoặc số điện thoại, không nên giữ các trường đó trong bộ dữ liệu. Giảm thiểu giúp hạn chế rủi ro và làm tập dữ liệu dễ quản lý hơn.

### 11.2. Ẩn danh, giả danh và tokenization

- **Ẩn danh (anonymization)** nhằm loại bỏ khả năng liên kết dữ liệu với cá nhân bằng các phương tiện hợp lý trong bối cảnh sử dụng. Cần đánh giá cả tổ hợp trường và dữ liệu phụ trợ có thể dùng để tái nhận diện.
- **Giả danh (pseudonymization)** thay định danh trực tiếp bằng mã khác nhưng vẫn có thể liên kết lại nếu còn bảng ánh xạ hoặc thông tin bổ trợ. Dữ liệu giả danh vẫn cần được bảo vệ như dữ liệu có khả năng định danh.
- **Tokenization** thay giá trị nhạy cảm bằng token và giữ ánh xạ trong hệ thống được kiểm soát. Cần bảo vệ kho ánh xạ và quyền truy cập.

Che tên, email hoặc số điện thoại đơn lẻ không bảo đảm dữ liệu đã ẩn danh. Ngày sinh, mã bưu chính, lịch sử giao dịch và tổ hợp thuộc tính hiếm có thể làm lộ danh tính.

### 11.3. Làm biến dạng có kiểm soát

Có thể tổng quát hóa, làm tròn, xáo trộn hoặc thay thế một số trường để giảm nguy cơ nhận diện. Tuy nhiên, mỗi biến đổi có thể làm sai lệch phân bố hoặc phá vỡ quan hệ. Ví dụ, thay đổi ngày của từng bảng độc lập có thể làm thời điểm thanh toán trước thời điểm tạo đơn.

Hãy xác định trường nào được phép biến đổi, quan hệ nào phải giữ và cách kiểm tra lại sau biến đổi.

### 11.4. Kiểm soát truy cập và vòng đời

- Chỉ người và hệ thống được phê duyệt mới được truy cập tập dữ liệu.
- Phân quyền tối thiểu và ghi nhận truy cập khi cần.
- Mã hóa khi lưu trữ và truyền tải theo chính sách.
- Không đưa dữ liệu nhạy cảm vào log, artifact hoặc báo cáo không được bảo vệ.
- Xác định thời hạn lưu trữ và quy trình xóa an toàn.
- Không tải dữ liệu production vào môi trường cá nhân hoặc công cụ ngoài phạm vi được phép.

## 12. Dữ liệu cho kiểm thử hiệu năng và hệ thống dữ liệu lớn

Đối với kiểm thử hiệu năng, độ đại diện của dữ liệu có thể ảnh hưởng mạnh đến kết quả ngay cả khi tổng số bản ghi giống nhau.

### 12.1. Cardinality và độ lệch phân bố

Một cột có ít giá trị khác nhau (low cardinality) có thể hoạt động khác cột có giá trị gần như duy nhất. Truy vấn theo một khóa rất phổ biến có thể tạo hot partition hoặc contention. Hãy xem xét cả phân bố tổng và các khóa có tần suất cao.

### 12.2. Kích thước và độ dài dữ liệu

Chuỗi ngắn, payload nhỏ và tệp nhẹ có thể không bộc lộ giới hạn bộ nhớ, serialization hoặc truyền tải. Cần có dữ liệu phổ biến và dữ liệu sát giới hạn kích thước, nhưng không dùng dữ liệu bất thường không thuộc phạm vi sử dụng để đại diện cho tải thông thường.

### 12.3. Cache và tính cục bộ

Nếu mọi request đều truy cập cùng một vài bản ghi, cache có thể đạt tỷ lệ hit rất cao. Dữ liệu production có thể phân tán hơn hoặc có một nhóm khóa nóng. Cần mô hình hóa tỷ lệ truy cập lặp, độ mới và cache miss theo mục tiêu.

### 12.4. Tenant và phân vùng

Nếu dữ liệu phân theo tenant, kích thước tenant có thể rất lệch. Một tenant lớn có thể tạo truy vấn, index hoặc hàng đợi khác với hàng trăm tenant nhỏ. Bộ test hiệu năng cần giữ được phân bố kích thước tenant hoặc tạo riêng các kịch bản tenant lớn và tenant nhỏ.

### 12.5. Ghi đồng thời và tranh chấp

Dữ liệu cần phản ánh số người ghi đồng thời, tần suất cập nhật cùng bản ghi, mức trùng khóa và thứ tự giao dịch. Nếu tất cả test dùng ID khác nhau, nhóm có thể bỏ sót contention trên tài nguyên dùng chung.

## 13. Dữ liệu cho hệ thống sử dụng mô hình học máy

Nếu sản phẩm có thành phần học máy, độ đại diện còn cần xét đến phân bố dữ liệu đầu vào, nhãn và sự khác biệt giữa giai đoạn huấn luyện, đánh giá và vận hành.

### 13.1. Phân biệt tập huấn luyện, validation và test

- **Training set** dùng để học tham số mô hình.
- **Validation set** hỗ trợ chọn mô hình hoặc điều chỉnh siêu tham số.
- **Test set** được giữ riêng để đánh giá cuối cùng trên dữ liệu chưa dùng trong quá trình lựa chọn.

Không dùng kết quả trên test set để liên tục điều chỉnh mô hình rồi vẫn xem đó là đánh giá độc lập. Khi test set đã ảnh hưởng đến quyết định phát triển, cần có tập đánh giá mới hoặc quy trình đánh giá độc lập.

### 13.2. Chia dữ liệu đúng theo đơn vị và thời gian

Nếu nhiều bản ghi thuộc cùng một người dùng, thiết bị hoặc tổ chức, chia ngẫu nhiên từng bản ghi có thể làm thông tin của cùng một thực thể xuất hiện ở cả training và test. Cần chia theo nhóm thực thể hoặc theo thời gian tùy mục tiêu triển khai.

Với dự đoán theo thời gian, không dùng đặc trưng được tạo sau thời điểm dự đoán. Dữ liệu tương lai lọt vào tập đầu vào sẽ làm kết quả đánh giá quá lạc quan.

### 13.3. Nhãn và nhóm ít đại diện

Kiểm tra định nghĩa nhãn, chất lượng gán nhãn và tỷ lệ sai nhãn theo nhóm. Đánh giá theo từng nhóm có thể phát hiện hiệu năng không đồng đều bị che khuất bởi chỉ số tổng. Cần chú ý quyền riêng tư, công bằng và quy định khi xử lý thuộc tính nhạy cảm.

### 13.4. Drift và điều kiện vận hành

Phân bố production có thể thay đổi sau khi triển khai. Hãy xác định cách theo dõi drift, nguồn dữ liệu mới và tiêu chí kích hoạt đánh giá lại. Một tập test đại diện cho dữ liệu năm trước không tự động đại diện cho hành vi hiện tại.

## 14. Ví dụ xuyên suốt: đánh giá dữ liệu cho hệ thống đặt hàng

Giả sử nhóm cần kiểm thử quy tắc tính phí, thanh toán, giao hàng và cập nhật trạng thái của một cửa hàng trực tuyến.

### 14.1. Xác định quần thể mục tiêu

Nhóm xác định các đơn hàng thuộc phạm vi thị trường đang hỗ trợ, bao gồm:

- Nhiều vùng giao và loại dịch vụ vận chuyển.
- Nhiều phương thức thanh toán.
- Giá trị đơn hàng thấp, phổ biến, cao và sát giới hạn.
- Giỏ hàng một sản phẩm và nhiều sản phẩm.
- Mã giảm giá hợp lệ, hết hạn, không đủ điều kiện và đã sử dụng.
- Đơn hàng mới, đang chờ thanh toán, đã thanh toán, đã giao, bị hủy và hoàn tiền.
- Sự kiện thanh toán thành công, từ chối, timeout, callback lặp và callback trễ.

### 14.2. Nhận diện sai lệch trong mẫu ban đầu

Mẫu ban đầu lấy từ các đơn hàng giao thành công trong 7 ngày gần nhất. Nhóm nhận thấy:

- Không có đơn bị hủy hoặc hoàn tiền vì bộ lọc chỉ giữ trạng thái hoàn tất.
- Chỉ có một vùng giao vì nguồn lấy mẫu đến từ một kho.
- Gần như không có thanh toán bị từ chối.
- Giá trị đơn hàng tập trung trong khoảng hẹp.
- Không có sự kiện callback trễ hoặc lặp vì nguồn chỉ lưu trạng thái cuối.

Mẫu này có thể hữu ích cho một số kiểm tra hành trình giao thành công, nhưng không đại diện cho toàn bộ rủi ro của luồng đặt hàng.

### 14.3. Thiết kế tập dữ liệu lai

Nhóm có thể xây dựng:

1. Một mẫu đã được xử lý từ dữ liệu thực để giữ phân bố vùng, giá trị đơn và phương thức thanh toán phổ biến.
2. Các bản ghi tổng hợp để bổ sung tenant, vùng và nhóm ít xuất hiện.
3. Kịch bản nhân tạo cho đơn bị từ chối, hủy, hoàn tiền, mã giảm giá hết hạn và callback lặp.
4. Dữ liệu biên cho số lượng, trọng lượng, tổng tiền và giới hạn vận chuyển.
5. Chuỗi sự kiện có timestamp để kiểm tra callback trễ và chuyển trạng thái.

Mỗi nhóm được gắn nguồn gốc và mục đích. Tập dữ liệu dùng cho hiệu năng có thể giữ tỷ lệ hành trình gần thực tế hơn; tập hồi quy rủi ro có thể cố ý tăng tỷ lệ trường hợp lỗi.

### 14.4. Xác minh chất lượng và độ đại diện

Trước khi sử dụng, nhóm kiểm tra:

- Schema, khóa và quan hệ giữa khách hàng, đơn hàng, thanh toán và giao hàng.
- Tỷ lệ vùng giao, phương thức thanh toán và trạng thái so với mục tiêu.
- Phân bố tổng tiền, trọng lượng và số lượng sản phẩm.
- Tính hợp lý của timestamp và trình tự sự kiện.
- Các nhóm rủi ro hiếm đã có dữ liệu riêng chưa.
- Dữ liệu nhạy cảm đã được giảm thiểu và xử lý theo chính sách chưa.
- Generator và mẫu có thể tái tạo bằng phiên bản và seed đã ghi nhận không.

### 14.5. Diễn giải đúng kết quả

Nếu bộ hồi quy có 20% giao dịch bị từ chối trong khi production chỉ có 0,2%, không thể dùng tỷ lệ đó để kết luận tỷ lệ từ chối thực tế. Tỷ lệ cao hơn là có chủ đích để kiểm tra nhánh lỗi. Báo cáo phải phân biệt tập kiểm thử theo rủi ro với workload dùng để mô phỏng tần suất sử dụng.

## 15. Hồ sơ lựa chọn và phê duyệt dữ liệu

Mỗi tập dữ liệu quan trọng nên có hồ sơ để người khác hiểu nó được tạo ra, đại diện cho điều gì và không đại diện cho điều gì.

| Trường | Nội dung cần ghi |
|---|---|
| Dataset ID / phiên bản | Mã định danh và phiên bản tập dữ liệu. |
| Mục tiêu kiểm thử | Yêu cầu, hành trình, rủi ro hoặc chỉ số cần xác minh. |
| Quần thể mục tiêu | Đối tượng và khoảng thời gian được đại diện. |
| Đơn vị mẫu | Người dùng, phiên, giao dịch, bản ghi hoặc chuỗi sự kiện. |
| Nguồn dữ liệu | Production đã xử lý, synthetic, kịch bản nhân tạo, golden hoặc tập lai. |
| Phương pháp chọn | Ngẫu nhiên, phân tầng, theo rủi ro, biên, pairwise hoặc theo thời gian. |
| Đặc trưng quan trọng | Phân bố, quan hệ, trạng thái, kích thước và trường biên. |
| Biến đổi dữ liệu | Ẩn danh, tổng quát hóa, thay ID, chuẩn hóa hoặc tạo bổ sung. |
| Kiểm tra chất lượng | Schema, integrity, missingness, distribution và invariants. |
| Sai lệch đã biết | Nhóm thiếu/thừa, thời gian, nguồn, môi trường hoặc giới hạn khác. |
| Quyền và thời hạn | Cơ sở sử dụng, người được truy cập, nơi lưu và thời hạn xóa. |
| Cách tái tạo | Truy vấn, phiên bản generator, seed, script và checksum. |
| Người sở hữu | Người chịu trách nhiệm cập nhật và xử lý vấn đề. |

Một tập dữ liệu chỉ nên được chấp nhận khi phù hợp với mục tiêu đã nêu, các sai lệch quan trọng được hiểu và những giới hạn không thể khắc phục được ghi nhận.

## 16. Quy trình đánh giá độ đại diện và sai lệch

Nhóm có thể áp dụng quy trình sau:

1. **Xác định câu hỏi kiểm thử**: nêu hành vi, yêu cầu, rủi ro hoặc chỉ số mà dữ liệu cần hỗ trợ.
2. **Định nghĩa quần thể mục tiêu**: xác định đơn vị mẫu, nhóm đối tượng, thời gian và phạm vi vận hành.
3. **Chọn đặc trưng quan trọng**: liệt kê giá trị, trạng thái, quan hệ, trình tự và điều kiện biên ảnh hưởng đến hành vi.
4. **Chọn nguồn dữ liệu**: đánh giá dữ liệu đã xử lý, tổng hợp, nhân tạo, golden hoặc tập lai theo mục tiêu và quyền sử dụng.
5. **Chọn phương pháp lấy mẫu**: kết hợp phân tầng, ngẫu nhiên, theo rủi ro, biên, tổ hợp và thời gian.
6. **Kiểm tra chất lượng và quan hệ**: xác minh schema, ràng buộc, bất biến, timestamp và dữ liệu thiếu.
7. **Đánh giá sai lệch**: so sánh phân bố, nhóm bị thiếu/thừa, drift, nhãn và khác biệt môi trường.
8. **Kiểm tra quyền riêng tư**: xác nhận giảm thiểu dữ liệu, xử lý định danh, quyền truy cập và thời hạn lưu.
9. **Đánh giá khả năng tái lập**: lưu nguồn gốc, phiên bản, seed, truy vấn và cách nạp/cleanup.
10. **Phê duyệt và theo dõi**: ghi nhận giới hạn, người sở hữu và thời điểm cần đánh giá lại.

## 17. Những sai lầm thường gặp

- **Cho rằng dữ liệu lớn thì đại diện**: số lượng nhiều vẫn có thể thiếu nhóm hoặc sai phân bố. Hãy xác định quần thể và đặc trưng liên quan.
- **Chỉ lấy mẫu ngẫu nhiên**: nhóm hiếm hoặc rủi ro cao có thể không xuất hiện. Hãy kết hợp phân tầng và lấy mẫu theo rủi ro.
- **Chỉ lấy giao dịch thành công**: bỏ sót trạng thái lỗi, hủy và hoàn tiền. Hãy xem toàn bộ vòng đời nghiệp vụ.
- **Coi tỷ lệ test phải giống production**: trường hợp hiếm có thể cần được tăng mẫu có chủ đích. Hãy phân biệt workload đại diện và tập hồi quy rủi ro.
- **Tạo từng trường độc lập**: bản ghi đúng kiểu nhưng sai quan hệ nghiệp vụ. Hãy giữ tương quan và bất biến.
- **Loại bỏ mọi dữ liệu thiếu**: có thể xóa mất nhóm cần kiểm tra. Hãy hiểu nguyên nhân và ngữ nghĩa của missingness.
- **Chỉ so sánh trung bình**: khác biệt phân bố và đuôi dài bị che khuất. Hãy xem quantile, histogram và phân nhóm.
- **Ẩn danh bằng cách xóa tên**: tổ hợp thuộc tính vẫn có thể tái nhận diện. Hãy đánh giá nguy cơ và tuân thủ quy trình dữ liệu.
- **Tin tuyệt đối vào synthetic data**: generator có thể mã hóa giả định sai. Hãy so sánh phân bố, tương quan và quy tắc nghiệp vụ.
- **Mất trình tự sự kiện**: chỉ còn trạng thái cuối nên không kiểm tra được retry hoặc callback trễ. Hãy giữ chuỗi sự kiện khi mục tiêu yêu cầu.
- **Không ghi nguồn gốc và phiên bản**: test không tái lập được khi dữ liệu thay đổi. Hãy version hóa và lưu seed/truy vấn.
- **Không đánh giá lại khi hệ thống thay đổi**: dữ liệu cũ có thể không còn đại diện. Hãy theo dõi drift và cập nhật theo mục tiêu.

## 18. Tự kiểm tra

Trước khi chấp nhận một tập dữ liệu cho kiểm thử, hãy tự hỏi:

- Câu hỏi kiểm thử và quần thể mục tiêu đã được xác định rõ chưa?
- Đơn vị mẫu là người dùng, phiên, giao dịch, bản ghi hay chuỗi sự kiện?
- Những đặc trưng nào làm thay đổi hành vi hoặc rủi ro?
- Các nhóm phổ biến, hiếm, biên và trạng thái lỗi có được bao phủ phù hợp không?
- Phương pháp lấy mẫu có tạo sai lệch hoặc loại bỏ nhóm quan trọng không?
- Từng trường và quan hệ giữa các trường có hợp lệ không?
- Dữ liệu có giữ được thời gian, trình tự và bất biến cần thiết không?
- Phân bố và dữ liệu thiếu đã được so sánh theo từng nhóm chưa?
- Có sai lệch do nguồn, thời gian, nhãn, generator hoặc môi trường không?
- Nguồn dữ liệu, biến đổi, quyền sử dụng và thời hạn lưu có được ghi nhận không?
- Có thể tái tạo chính xác cùng phiên bản dữ liệu khi cần điều tra không?
- Các giới hạn và sai lệch còn lại đã được nêu rõ trong báo cáo chưa?

## Kết luận

Độ đại diện của dữ liệu kiểm thử phải được đánh giá theo câu hỏi, quần thể mục tiêu và rủi ro cần xác minh. Một mẫu hữu ích cần bao gồm các đặc trưng, quan hệ, trạng thái và điều kiện thời gian có ảnh hưởng đến hành vi; đồng thời phải nhận diện sai lệch do cách chọn mẫu, dữ liệu thiếu, survivorship, mất cân bằng, generator hoặc môi trường. Không phải mọi bộ test đều cần tái tạo nguyên tỷ lệ production: kiểm thử theo rủi ro có thể chủ động tăng các trường hợp hiếm, miễn là mục đích và cách diễn giải được ghi rõ. Khi kết hợp phương pháp lấy mẫu phù hợp, kiểm tra phân bố và tính toàn vẹn, bảo vệ quyền riêng tư và lưu nguồn gốc dữ liệu, nhóm có thể tạo bằng chứng kiểm thử đáng tin cậy và tái lập được.
