# Xác định hệ thống nguồn, người sở hữu và bên sử dụng dữ liệu

Một mô hình dữ liệu chỉ phản ánh đúng nghiệp vụ khi ta biết dữ liệu đến từ đâu, ai chịu trách nhiệm về ý nghĩa và chất lượng của nó, và những hệ thống hoặc nhóm người nào sẽ sử dụng dữ liệu. Một thuộc tính như trạng thái khách hàng, giá sản phẩm hay số lượng tồn kho có thể xuất hiện ở nhiều ứng dụng. Nếu không xác định rõ nguồn có thẩm quyền và trách nhiệm quản lý, các bản sao dễ lệch nhau, nhóm phát triển có thể chọn nhầm dữ liệu để ra quyết định, còn người dùng không biết cần liên hệ ai khi phát hiện sai sót.

Trong phân tích yêu cầu của mô hình dữ liệu, cần khảo sát ba vai trò có liên quan nhưng khác nhau:

- **Hệ thống nguồn (source system):** nơi dữ liệu được tạo ra, ghi nhận hoặc cung cấp cho một luồng xử lý.
- **Người sở hữu dữ liệu (data owner):** người hoặc đơn vị nghiệp vụ chịu trách nhiệm về định nghĩa, quy tắc sử dụng, chất lượng và quyết định quản trị đối với một miền dữ liệu.
- **Bên sử dụng dữ liệu (data consumer):** hệ thống, nhóm nghiệp vụ, đối tác hoặc quy trình nhận dữ liệu để thực hiện một công việc cụ thể.

Ba vai trò này không nhất thiết thuộc cùng một tổ chức hay ứng dụng. Hệ thống CRM có thể là nơi nhân viên nhập thông tin liên hệ, bộ phận chăm sóc khách hàng có thể sở hữu quy tắc về hồ sơ khách hàng, còn hệ thống phân tích và dịch vụ gửi thông báo là những bên tiêu thụ dữ liệu. Phân tích cần làm rõ trách nhiệm và luồng dữ liệu giữa các bên trước khi quyết định thực thể, khóa, quan hệ, bản sao và cách tích hợp.

## 1. Phân biệt nguồn dữ liệu, nguồn có thẩm quyền và nơi lưu trữ

### 1.1. Hệ thống nguồn là gì?

Hệ thống nguồn là hệ thống cung cấp dữ liệu cho một quy trình hoặc hệ thống khác. Nguồn có thể là:

- Ứng dụng nghiệp vụ nơi người dùng tạo hoặc cập nhật dữ liệu.
- Dịch vụ ghi nhận giao dịch, chẳng hạn dịch vụ thanh toán hoặc quản lý đơn hàng.
- Thiết bị, cảm biến hoặc phần mềm vận hành tạo ra dữ liệu tự động.
- Nền tảng đối tác gửi dữ liệu qua API, thông điệp hoặc tệp.
- Kho dữ liệu, hệ thống tham chiếu hoặc bộ dữ liệu đã được xử lý từ nhiều nguồn.
- Một nguồn thủ công như bảng tính, biểu mẫu hoặc tệp nhập liệu được nghiệp vụ quản lý.

Không nên mặc định mọi dữ liệu trong hệ thống nguồn đều chính xác hoặc có thẩm quyền. Một ứng dụng có thể ghi nhận dữ liệu đầu tiên nhưng vẫn cần được kiểm tra, đối chiếu hoặc phê duyệt. Một kho dữ liệu có thể là nguồn tốt cho báo cáo đã chuẩn hóa nhưng không phải nơi phù hợp để cập nhật trạng thái giao dịch.

### 1.2. Phân biệt các khái niệm thường bị nhầm lẫn

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| System of origin | Nơi dữ liệu ban đầu được tạo ra hoặc thu thập | Dữ liệu xuất hiện đầu tiên ở đâu? |
| Source system | Hệ thống cung cấp dữ liệu cho luồng đang xét | Hệ thống nào đang gửi dữ liệu này? |
| System of record | Hệ thống được chỉ định lưu giữ bản ghi có thẩm quyền cho một phạm vi dữ liệu | Nơi nào được quyền xác nhận trạng thái chính thức? |
| Authoritative source | Nguồn được công nhận có thẩm quyền cho một miền, thuộc tính hoặc mục đích cụ thể | Nguồn nào được dùng khi có xung đột? |
| Data warehouse/lake | Nơi tập hợp, lưu trữ và xử lý dữ liệu phục vụ phân tích hoặc các mục đích khác | Dữ liệu đã được biến đổi như thế nào và có độ trễ bao lâu? |
| Data consumer | Hệ thống hoặc người dùng nhận và sử dụng dữ liệu | Ai dùng dữ liệu, dùng để làm gì và cần chất lượng nào? |

Một tổ chức có thể có nhiều hệ thống có thẩm quyền cho các miền dữ liệu khác nhau. Hệ thống bán hàng quản lý trạng thái đơn hàng; hệ thống kho quản lý số lượng thực tế; nhà cung cấp thanh toán là nguồn xác nhận giao dịch thanh toán bên ngoài; nền tảng khách hàng quản lý thông tin liên hệ. Không có một hệ thống duy nhất nhất thiết phải là nguồn có thẩm quyền cho mọi thuộc tính.

Ngay cả trong một miền dữ liệu, thẩm quyền có thể được phân chia theo thuộc tính hoặc theo thời điểm. Ví dụ, hệ thống CRM quản lý tên hiển thị và thông tin liên hệ do khách hàng cung cấp; hệ thống xác minh danh tính quản lý trạng thái xác minh; dịch vụ đăng ký quản lý trạng thái đồng ý nhận thông báo. Khi hai nguồn cung cấp các giá trị khác nhau, phải biết thuộc tính nào do nguồn nào quản lý.

### 1.3. Không đồng nhất nơi nhập dữ liệu với nơi có thẩm quyền

Một nhân viên có thể nhập thông tin khách hàng vào biểu mẫu bán hàng, nhưng hồ sơ chính thức được tạo trong hệ thống khách hàng sau bước kiểm tra trùng lặp. Tương tự, nhân viên kho có thể quét một kiện hàng bằng ứng dụng di động, còn dịch vụ quản lý kho mới là nơi xác nhận số lượng đã nhập.

Cần mô tả riêng:

- Nơi dữ liệu được thu thập.
- Nơi dữ liệu được kiểm tra hoặc phê duyệt.
- Nơi dữ liệu được lưu giữ có thẩm quyền.
- Nơi dữ liệu được sao chép hoặc biến đổi.
- Nơi dữ liệu được dùng để ra quyết định.

Sự phân biệt này giúp tránh việc một bản sao phục vụ hiển thị bị sử dụng làm nguồn cập nhật nghiệp vụ.

## 2. Xác định miền dữ liệu và nguồn có thẩm quyền

### 2.1. Bắt đầu từ miền nghiệp vụ

Trước khi liệt kê ứng dụng, hãy xác định các miền dữ liệu mà nghiệp vụ quan tâm. Ví dụ trong một cửa hàng trực tuyến:

- Khách hàng và hồ sơ liên hệ.
- Sản phẩm và danh mục.
- Giá, khuyến mại và điều kiện bán.
- Đơn hàng và dòng hàng.
- Tồn kho và giữ chỗ.
- Thanh toán và hoàn tiền.
- Vận chuyển và giao nhận.
- Hóa đơn và chứng từ.
- Tài khoản, vai trò và quyền truy cập.

Một miền dữ liệu là nhóm khái niệm có ý nghĩa nghiệp vụ và quy tắc quản lý tương đối thống nhất. Một ứng dụng có thể quản lý nhiều miền; một miền có thể trải qua nhiều ứng dụng. Vì vậy, không nên lấy ranh giới ứng dụng làm ranh giới miền dữ liệu một cách máy móc.

### 2.2. Lập ma trận thẩm quyền

Với mỗi miền, xác định nguồn có thẩm quyền cho các thuộc tính quan trọng, nơi phát sinh, nơi lưu bản chính và cách các hệ thống khác nhận dữ liệu.

Ví dụ:

| Miền/thuộc tính | Nguồn có thẩm quyền | Nơi phát sinh hoặc nhập | Bên sử dụng chính | Ghi chú |
|---|---|---|---|---|
| Hồ sơ liên hệ khách hàng | CRM | Website, nhân viên hỗ trợ | Bán hàng, chăm sóc khách hàng, phân tích | Cần quy tắc hợp nhất hồ sơ trùng |
| Trạng thái xác minh khách hàng | Dịch vụ xác minh | Quy trình xác minh | Đăng ký, thanh toán, kiểm soát rủi ro | CRM chỉ hiển thị bản sao trạng thái |
| Thông tin sản phẩm | PIM hoặc hệ thống danh mục được chỉ định | Nhóm quản lý sản phẩm | Website, tìm kiếm, đơn hàng | Tên và mô tả có thể được sao chép |
| Giá bán đang áp dụng | Dịch vụ quản lý giá | Nhóm định giá | Giỏ hàng, đơn hàng, khuyến mại | Đơn hàng cần giữ giá đã chốt |
| Tồn kho khả dụng | Hệ thống quản lý kho | Kho, điểm bán, tích hợp nhà cung cấp | Đặt hàng, phân bổ, vận hành | Phải phân biệt tồn thực tế và tồn có thể bán |
| Trạng thái đơn hàng | Hệ thống quản lý đơn | Quy trình đặt và xử lý đơn | Khách hàng, kho, vận chuyển, hỗ trợ | Trạng thái giao hàng có thể đến từ đối tác |
| Kết quả thanh toán | Nhà cung cấp thanh toán và sổ giao dịch nội bộ theo quy tắc đối soát | Cổng thanh toán, dịch vụ thanh toán | Đơn hàng, kế toán, hỗ trợ | Phải xác định nguồn xác nhận cuối cùng |
| Sự kiện giao nhận | Đối tác vận chuyển hoặc nền tảng điều phối được chỉ định | Thiết bị quét, đối tác | Khách hàng, hỗ trợ, phân tích | Có thể nhận sự kiện trễ hoặc lặp |

Các tên hệ thống trong bảng là ví dụ để minh họa cách phân tích. Khi áp dụng vào dự án thật, phải thay bằng hệ thống đã được tổ chức xác nhận.

### 2.3. Thẩm quyền có thể phụ thuộc vào thuộc tính và mục đích

Một trường dữ liệu có thể được dùng trong nhiều ngữ cảnh. Ví dụ:

- Địa chỉ mặc định hiện tại của khách hàng do CRM quản lý.
- Địa chỉ giao hàng của một đơn hàng là ảnh chụp được khách hàng xác nhận tại thời điểm đặt.
- Địa chỉ đã dùng để phát hành chứng từ có thể chịu quy tắc lưu giữ riêng.
- Địa chỉ do đối tác vận chuyển chuẩn hóa có thể chỉ là dữ liệu phục vụ giao hàng.

Nếu chỉ nói “CRM là nguồn của địa chỉ”, nhóm phát triển có thể vô tình ghi đè địa chỉ giao dịch lịch sử bằng địa chỉ hiện tại. Hãy xác định ý nghĩa của từng thuộc tính, phạm vi áp dụng và thời điểm giá trị được xem là có hiệu lực.

### 2.4. Xử lý khi nhiều nguồn cùng cung cấp một giá trị

Khi có nhiều nguồn, cần định nghĩa quy tắc giải quyết xung đột. Một số cách thường gặp:

- Một nguồn được chỉ định có thẩm quyền cho thuộc tính đó.
- Một nguồn được ưu tiên theo trạng thái xác minh hoặc mức độ tin cậy.
- Người có trách nhiệm nghiệp vụ phê duyệt giá trị cuối cùng.
- Dữ liệu được giữ thành các quan sát riêng kèm nguồn và thời điểm, sau đó hợp nhất theo quy tắc.
- Giá trị được tính từ nhiều dữ liệu đầu vào thay vì chọn một nguồn duy nhất.

Không nên chọn quy tắc “bản cập nhật mới nhất luôn thắng” nếu các nguồn có độ tin cậy khác nhau, đồng hồ không đồng bộ hoặc bản cập nhật đến muộn. Thời điểm ghi nhận ở một hệ thống cũng không nhất thiết phản ánh thời điểm nghiệp vụ có hiệu lực.

Với mỗi xung đột, cần ghi rõ:

1. Thuộc tính nào bị xung đột.
2. Những nguồn nào có thể gửi giá trị.
3. Nguồn hoặc quy tắc nào có quyền quyết định.
4. Cách xử lý giá trị không hợp lệ hoặc không xác định được nguồn.
5. Ai chịu trách nhiệm giải quyết ngoại lệ.
6. Có cần lưu lại giá trị gốc, nguồn và lịch sử hợp nhất hay không.

## 3. Xác định người sở hữu và trách nhiệm quản trị dữ liệu

### 3.1. Data owner chịu trách nhiệm về quyết định nghiệp vụ

Người sở hữu dữ liệu thường là cá nhân hoặc đơn vị nghiệp vụ chịu trách nhiệm cuối cùng về một miền dữ liệu. Họ hiểu dữ liệu có ý nghĩa gì, được dùng cho mục đích nào và quy tắc nào phải được tuân thủ.

Trách nhiệm có thể bao gồm:

- Phê duyệt định nghĩa và thuật ngữ nghiệp vụ.
- Xác định nguồn có thẩm quyền cho dữ liệu.
- Quyết định quy tắc chất lượng và ngưỡng chấp nhận.
- Phê duyệt quyền truy cập và mục đích chia sẻ.
- Xác định chính sách lưu giữ, sửa sai và xử lý dữ liệu.
- Phân công người quản lý dữ liệu hằng ngày.
- Giải quyết xung đột giữa các đơn vị sử dụng.
- Chấp thuận thay đổi ảnh hưởng đến dữ liệu dùng chung.

Người sở hữu dữ liệu không nhất thiết là người viết mã, quản trị cơ sở dữ liệu hoặc trực tiếp vận hành hệ thống.

### 3.2. Phân biệt các vai trò liên quan

Tên vai trò có thể khác nhau giữa các tổ chức. Điều quan trọng là xác định trách nhiệm thực tế và người có quyền quyết định.

| Vai trò | Trách nhiệm điển hình | Ví dụ |
|---|---|---|
| Data owner | Chịu trách nhiệm nghiệp vụ và phê duyệt quy tắc của miền dữ liệu | Trưởng bộ phận khách hàng chịu trách nhiệm về định nghĩa hồ sơ khách hàng |
| Data steward | Quản lý định nghĩa, chất lượng, phân loại và xử lý vấn đề hằng ngày | Chuyên viên dữ liệu kiểm tra hồ sơ trùng và mã danh mục |
| Data custodian / platform owner | Bảo đảm nền tảng lưu trữ, sao lưu, quyền kỹ thuật và vận hành | Nhóm cơ sở dữ liệu hoặc nền tảng dữ liệu |
| System owner | Chịu trách nhiệm về vòng đời và vận hành một ứng dụng | Chủ sản phẩm hoặc đơn vị vận hành CRM |
| Data producer | Tạo hoặc cung cấp dữ liệu theo hợp đồng đã thống nhất | Dịch vụ đơn hàng phát sự kiện OrderConfirmed |
| Data consumer | Nhận dữ liệu và chịu trách nhiệm sử dụng đúng mục đích | Kho dữ liệu phân tích hoặc dịch vụ giao hàng |
| Security / privacy specialist | Tư vấn và giám sát yêu cầu bảo mật, quyền riêng tư theo chính sách | Nhóm an toàn thông tin hoặc phụ trách quyền riêng tư |

Một người có thể đảm nhiệm nhiều vai trò trong tổ chức nhỏ. Tuy nhiên, cần tránh tình trạng một trách nhiệm quan trọng không có người nhận hoặc mọi quyết định đều mặc nhiên đẩy cho nhóm kỹ thuật.

### 3.3. Phân công quyền quyết định

Có thể dùng ma trận trách nhiệm để làm rõ ai thực hiện, ai chịu trách nhiệm cuối cùng, ai cần được tham vấn và ai cần được thông báo.

| Hoạt động | Data owner | Data steward | System/platform owner | Consumer |
|---|---|---|---|---|
| Phê duyệt định nghĩa nghiệp vụ | Chịu trách nhiệm cuối cùng | Đề xuất và duy trì | Tham vấn kỹ thuật | Tham vấn nhu cầu |
| Chọn nguồn có thẩm quyền | Phê duyệt | Điều phối và ghi nhận | Cung cấp thông tin hệ thống | Nêu nhu cầu sử dụng |
| Định nghĩa quy tắc chất lượng | Phê duyệt | Xây dựng và theo dõi | Triển khai kiểm tra kỹ thuật | Báo lỗi sử dụng |
| Vận hành đường ống dữ liệu | Được thông báo | Theo dõi chất lượng | Chịu trách nhiệm kỹ thuật | Theo dõi đầu ra |
| Cấp quyền sử dụng dữ liệu | Phê duyệt theo chính sách | Kiểm tra mục đích và phân loại | Thực thi quyền kỹ thuật | Yêu cầu quyền |
| Thay đổi schema hoặc hợp đồng | Phê duyệt tác động nghiệp vụ | Điều phối thông báo | Quản lý phát hành | Đánh giá tương thích |

Ma trận cần được điều chỉnh theo cơ cấu tổ chức. Không nên coi việc một nhóm có quyền quản trị cơ sở dữ liệu đồng nghĩa nhóm đó có quyền quyết định ý nghĩa nghiệp vụ hoặc mục đích sử dụng dữ liệu.

### 3.4. Xác định đầu mối khi có sự cố dữ liệu

Khi người dùng báo một khách hàng bị trùng, giá sản phẩm sai hoặc báo cáo lệch số liệu, cần biết ai xử lý phần nào:

- Data steward xác định định nghĩa và chất lượng dữ liệu.
- Data owner quyết định giá trị hoặc quy tắc nghiệp vụ khi có tranh chấp.
- System owner điều tra lỗi nhập liệu hoặc logic ứng dụng nguồn.
- Platform owner điều tra lỗi truyền, lưu trữ, phân quyền hoặc vận hành.
- Consumer xác định ảnh hưởng tới quy trình và cung cấp thông tin tái hiện.

Hãy ghi nhận kênh tiếp nhận, mức độ ưu tiên, thời gian phản hồi và cơ chế chuyển cấp nếu yêu cầu nghiệp vụ cần. Một quy trình xử lý dữ liệu sai không nên phụ thuộc vào việc người dùng biết tên kỹ sư đã xây dựng hệ thống.

## 4. Xác định bên sử dụng và nhu cầu dữ liệu

### 4.1. Lập danh sách consumer theo mục đích

Một dữ liệu có thể được sử dụng bởi nhiều nhóm, nhưng mỗi nhóm có nhu cầu khác nhau. Cần xác định bên tiêu thụ theo công việc họ thực hiện.

| Nhóm consumer | Mục đích | Ví dụ nhu cầu |
|---|---|---|
| Ứng dụng vận hành | Thực hiện giao dịch hoặc quy trình trực tiếp | Kiểm tra tồn kho trước khi xác nhận đơn |
| Ứng dụng hỗ trợ | Hiển thị thông tin để nhân viên xử lý yêu cầu | Xem lịch sử trạng thái đơn hàng |
| Hệ thống tích hợp | Chuyển dữ liệu sang dịch vụ khác | Gửi thông tin đơn đã xác nhận cho đối tác giao hàng |
| Báo cáo quản trị | Theo dõi chỉ số và điều hành | Tổng doanh thu theo ngày hoặc khu vực |
| Phân tích dữ liệu | Tìm xu hướng, dự báo hoặc phân khúc | Phân tích tỷ lệ mua lại của khách hàng |
| Kiểm toán và kiểm soát | Đối chiếu, điều tra và chứng minh hoạt động | Truy nguyên nguồn của một thay đổi |
| Đối tác bên ngoài | Cung cấp dịch vụ theo thỏa thuận | Nhận địa chỉ giao hàng và mã kiện hàng |

Đừng dừng ở tên hệ thống. Với từng consumer, hãy hỏi người dùng hoặc chủ sở hữu quy trình cần dữ liệu để làm quyết định gì, khi nào cần dữ liệu, và điều gì xảy ra nếu dữ liệu thiếu hoặc trễ.

### 4.2. Thu thập yêu cầu sử dụng cụ thể

Mỗi consumer nên được mô tả ít nhất theo các chiều sau:

- **Mục đích:** dữ liệu phục vụ quy trình hoặc quyết định nào?
- **Phạm vi:** cần toàn bộ miền dữ liệu hay chỉ một tập thuộc tính?
- **Độ chi tiết:** cần một bản ghi, một sự kiện, tổng hợp theo ngày hay dữ liệu theo từng dòng?
- **Độ mới:** dữ liệu cần cập nhật tức thời, theo phút, theo giờ hay theo ngày?
- **Lịch sử:** cần trạng thái hiện tại hay cần xem lại các phiên bản và sự kiện?
- **Khối lượng:** số bản ghi, tốc độ phát sinh và thời điểm cao điểm.
- **Độ sẵn sàng:** consumer cần dữ liệu trong thời gian nào và xử lý ra sao khi nguồn ngừng hoạt động?
- **Chất lượng:** cần mức đầy đủ, chính xác, duy nhất và nhất quán nào?
- **Bảo vệ:** ai được truy cập, thuộc tính nào cần che hoặc loại bỏ?
- **Vòng đời:** consumer giữ bản sao bao lâu và xử lý bản sao khi hết mục đích thế nào?

Ví dụ, màn hình xác nhận đơn cần biết tồn kho đủ nhanh để quyết định giữ chỗ. Báo cáo tồn kho cuối ngày có thể chấp nhận dữ liệu theo lô, nhưng phải biết mốc chốt và cách xử lý giao dịch đến muộn. Hai consumer này không nên mặc nhiên dùng chung một cơ chế cập nhật chỉ vì cùng đọc dữ liệu tồn kho.

### 4.3. Phân biệt dữ liệu cần đọc và dữ liệu được phép ghi

Một consumer có thể cần đọc dữ liệu nhưng không có quyền cập nhật nguồn. Ví dụ, dịch vụ phân tích đọc các sự kiện đơn hàng để tạo chỉ số; nó không nên ghi ngược số liệu tổng hợp vào hệ thống quản lý đơn.

Nếu nhiều hệ thống cùng có quyền sửa một thuộc tính, phải xác định cách phối hợp và nguồn quyết định. Nếu không, mô hình dễ xuất hiện nhiều nơi cùng ghi, đồng bộ vòng lặp hoặc cập nhật ghi đè.

Với mỗi luồng dữ liệu, hãy phân loại:

- Chỉ đọc.
- Ghi vào nguồn có thẩm quyền.
- Gửi yêu cầu để nguồn có thẩm quyền thực hiện thay đổi.
- Nhận sự kiện hoặc bản sao chỉ phục vụ đọc.
- Gửi dữ liệu đề xuất để một vai trò khác xác nhận.

## 5. Khảo sát luồng dữ liệu và quan hệ giữa các hệ thống

### 5.1. Vẽ luồng từ nơi tạo đến nơi sử dụng

Sơ đồ luồng dữ liệu giúp nhìn thấy nguồn, bước biến đổi, nơi lưu và consumer. Một sơ đồ khái quát có thể như sau:

~~~mermaid
flowchart LR
    A["Website / Nhân viên"] --> B["CRM"]
    C["Ứng dụng kho"] --> D["Hệ thống quản lý kho"]
    E["Cổng thanh toán"] --> F["Dịch vụ thanh toán"]
    B --> G["Nền tảng tích hợp"]
    D --> G
    F --> G
    G --> H["Dịch vụ đơn hàng"]
    G --> I["Kho dữ liệu"]
    H --> J["Ứng dụng hỗ trợ"]
    H --> K["Đối tác giao hàng"]
    I --> L["Báo cáo và phân tích"]
~~~

Sơ đồ trên chỉ mô tả một khả năng. Dự án thực tế có thể gửi dữ liệu trực tiếp qua API, sự kiện, CDC hoặc tệp. Cần ghi rõ chiều dữ liệu, giao thức, chủ sở hữu và điểm kiểm soát.

Với mỗi mũi tên, hãy trả lời:

- Ai phát dữ liệu và ai nhận?
- Dữ liệu được gửi theo cơ chế nào?
- Đối tượng hoặc sự kiện nào kích hoạt việc gửi?
- Có bước biến đổi, lọc, làm giàu hoặc tổng hợp nào?
- Consumer nhận dữ liệu đầy đủ hay một phần?
- Có lưu bản sao ở đâu?
- Ai theo dõi lỗi và đối soát?
- Làm sao truy nguyên một bản ghi đầu ra về nguồn ban đầu?

### 5.2. Chọn cách tích hợp theo nhu cầu

| Cách trao đổi | Đặc điểm | Phù hợp khi | Điều cần làm rõ |
|---|---|---|---|
| API đồng bộ | Consumer gọi nguồn và nhận phản hồi trong cùng luồng xử lý | Cần kiểm tra hoặc yêu cầu thay đổi ngay | Thời gian phản hồi, giới hạn gọi, lỗi, xác thực, khả năng sẵn sàng |
| Sự kiện / message | Producer phát sự kiện, consumer xử lý độc lập | Cần thông báo thay đổi cho nhiều consumer | Gửi lặp, thứ tự, retry, dead-letter, phiên bản schema |
| CDC | Đọc thay đổi từ nhật ký hoặc cơ chế capture của nguồn | Cần sao chép thay đổi dữ liệu với độ trễ thấp | Ranh giới giao dịch, xóa, thứ tự, quyền truy cập và tải lên nguồn |
| Batch / file | Truyền tập dữ liệu theo lịch hoặc theo lô | Báo cáo, đối soát hoặc tích hợp không cần tức thời | Lịch chạy, định dạng, mã hóa, kiểm tra đầy đủ và xử lý lại |
| Replication | Duy trì bản sao dữ liệu ở hệ thống khác | Cần mở rộng đọc hoặc phục vụ workload riêng | Độ trễ, quyền ghi, failover, sai lệch và trách nhiệm bản sao |

Không có một cách tích hợp phù hợp cho mọi luồng. API có thể đơn giản cho yêu cầu cần phản hồi ngay nhưng tạo phụ thuộc sẵn sàng giữa các hệ thống. Sự kiện giúp giảm phụ thuộc thời điểm nhưng consumer phải xử lý dữ liệu đến trễ hoặc lặp. Batch phù hợp cho một số báo cáo nhưng không đáp ứng quyết định cần dữ liệu mới tức thời.

### 5.3. Ghi nhận điểm biến đổi dữ liệu

Dữ liệu thường được biến đổi trên đường đi: chuẩn hóa tên, đổi mã, quy đổi tiền tệ, loại bỏ dữ liệu nhạy cảm, hợp nhất bản ghi, tính tổng hoặc tạo thuộc tính suy diễn.

Mỗi bước biến đổi cần có:

- Đầu vào và đầu ra.
- Quy tắc chuyển đổi.
- Phiên bản quy tắc hoặc chương trình khi cần tái lập.
- Chủ sở hữu nghiệp vụ phê duyệt ý nghĩa.
- Người chịu trách nhiệm vận hành.
- Cách xử lý dữ liệu không hợp lệ.
- Cách truy nguyên kết quả về nguồn.

Ví dụ, báo cáo doanh thu có thể loại đơn bị hủy, trừ hoàn tiền và quy đổi ngoại tệ theo tỷ giá tại ngày giao dịch. Nếu không lưu định nghĩa và nguồn của các bước này, hai báo cáo cùng mang tên “doanh thu” có thể đưa ra con số khác nhau.

## 6. Xây dựng hợp đồng dữ liệu giữa producer và consumer

### 6.1. Hợp đồng dữ liệu là gì?

Hợp đồng dữ liệu mô tả thỏa thuận giữa bên cung cấp và bên sử dụng về cấu trúc, ý nghĩa, chất lượng, cách phân phối và trách nhiệm vận hành của dữ liệu. Hợp đồng giúp các nhóm hiểu chính xác dữ liệu nào được cung cấp và thay đổi nào có thể ảnh hưởng đến consumer.

Một hợp đồng có thể gồm:

| Thành phần | Nội dung cần thống nhất |
|---|---|
| Tên và mục đích | Tập dữ liệu hoặc sự kiện phục vụ công việc gì |
| Producer và owner | Nhóm cung cấp và người chịu trách nhiệm nghiệp vụ |
| Consumer được phép | Các nhóm hoặc hệ thống được sử dụng |
| Schema | Trường, kiểu dữ liệu, bắt buộc/tùy chọn, cấu trúc lồng nhau |
| Ngữ nghĩa | Định nghĩa nghiệp vụ, đơn vị, múi giờ, mã trạng thái |
| Định danh | Khóa chính, khóa nghiệp vụ, quy tắc duy nhất |
| Chất lượng | Quy tắc hợp lệ, đầy đủ, duy nhất, nhất quán |
| Độ mới | Chu kỳ cập nhật hoặc độ trễ tối đa được chấp nhận |
| Phân phối | API, topic, CDC, bảng chia sẻ hoặc tệp |
| Bảo vệ | Phân loại, quyền, mục đích và giới hạn chia sẻ |
| Lịch sử | Cách biểu diễn cập nhật, xóa, phiên bản và dữ liệu đến muộn |
| Vận hành | Theo dõi, cảnh báo, hỗ trợ và xử lý sự cố |
| Thay đổi | Quy tắc tương thích, thông báo và ngừng hỗ trợ phiên bản |

Hợp đồng có thể được biểu diễn bằng tài liệu, schema registry, API specification hoặc cấu hình máy đọc được. Hình thức không quan trọng bằng việc các bên hiểu và tuân thủ cùng một cam kết.

### 6.2. Định nghĩa rõ ngữ nghĩa trường

Một trường có tên amount chưa đủ rõ. Cần biết:

- Đây là số tiền trước thuế hay sau thuế?
- Đơn vị tiền tệ nào?
- Là số tiền đã thanh toán, số tiền phải thu hay số tiền còn nợ?
- Giá trị âm có ý nghĩa gì?
- Độ chính xác và quy tắc làm tròn ra sao?

Tương tự, trường status cần có danh sách trạng thái, ý nghĩa, điều kiện chuyển trạng thái và khả năng xuất hiện trạng thái mới. Trường timestamp cần xác định múi giờ, thời điểm nghiệp vụ hay thời điểm hệ thống ghi nhận.

Nếu các consumer tự diễn giải trường theo cách riêng, cùng một schema có thể tạo ra các kết quả nghiệp vụ không tương thích.

### 6.3. Quản lý khóa và định danh xuyên hệ thống

Một thực thể có thể có nhiều mã:

- Khóa nội bộ của cơ sở dữ liệu.
- Mã nghiệp vụ hiển thị cho người dùng.
- Mã do đối tác cấp.
- Mã định danh từ hệ thống nguồn.
- Mã được tạo khi hợp nhất các hồ sơ trùng.

Cần xác định khóa nào ổn định, khóa nào chỉ có ý nghĩa trong một hệ thống, và cách ánh xạ giữa chúng. Không nên giả định hai hệ thống có thể dùng cùng một số nguyên làm khóa khách hàng hoặc sản phẩm.

Có thể dùng bảng ánh xạ định danh để liên kết mã nội bộ với mã của các nguồn. Bảng ánh xạ cần lưu loại nguồn, mã bên ngoài, mã nội bộ và các thông tin về hiệu lực hoặc trạng thái khi cần. Ràng buộc duy nhất phải phản ánh đúng phạm vi: một mã có thể duy nhất trong một nguồn nhưng trùng với mã của nguồn khác.

### 6.4. Quản lý thay đổi schema

Khi producer thêm, đổi tên, đổi kiểu hoặc xóa trường, consumer có thể bị lỗi hoặc hiểu sai dữ liệu. Hợp đồng cần định nghĩa:

- Thay đổi nào tương thích ngược?
- Consumer có phải chấp nhận trường mới không?
- Khi nào trường cũ bị ngừng sử dụng?
- Phiên bản nào được hỗ trợ trong thời gian bao lâu?
- Ai được thông báo và thông báo trước bao lâu?
- Cách kiểm thử tương thích trước khi phát hành?
- Làm sao quay lại hoặc xử lý consumer chưa nâng cấp?

Một thay đổi có vẻ nhỏ về kỹ thuật có thể thay đổi ý nghĩa nghiệp vụ. Ví dụ, đổi trạng thái “đã hoàn tất” để bao gồm cả đơn đã giao một phần sẽ ảnh hưởng đến báo cáo và quy trình kế toán. Cần đánh giá cả ngữ nghĩa lẫn cấu trúc.

## 7. Đặt yêu cầu chất lượng dữ liệu theo từng consumer

### 7.1. Các chiều chất lượng cần khảo sát

| Chiều chất lượng | Câu hỏi | Ví dụ kiểm tra |
|---|---|---|
| Chính xác | Giá trị có phản ánh đúng thực tế hoặc quy tắc không? | Tổng tiền khớp với dòng hàng và chính sách giá |
| Đầy đủ | Có thiếu trường hoặc bản ghi bắt buộc không? | Đơn đã xác nhận phải có mã khách hàng và dòng hàng |
| Duy nhất | Có bản ghi trùng trong phạm vi nghiệp vụ không? | Một mã giao dịch thanh toán không bị ghi nhận hai lần |
| Hợp lệ | Giá trị có đúng kiểu, miền giá trị và định dạng không? | Số lượng dương, trạng thái thuộc danh mục hợp lệ |
| Nhất quán | Các trường hoặc hệ thống có mâu thuẫn không? | Tổng số dòng và tổng tiền khớp với đơn |
| Kịp thời | Dữ liệu có đến trước thời điểm consumer cần không? | Sự kiện xác nhận đơn đến dịch vụ giao hàng trong giới hạn đã thống nhất |
| Có thể truy nguyên | Có xác định được nguồn và phép biến đổi không? | Báo cáo chỉ ra nguồn và thời điểm trích xuất |

Không phải mọi consumer cần cùng một mức chất lượng. Báo cáo xu hướng có thể chấp nhận một tỷ lệ bản ghi đến muộn nếu có ghi nhận; hệ thống cấp quyền hoặc thanh toán có thể yêu cầu kiểm tra nghiêm ngặt hơn.

### 7.2. Gắn quy tắc chất lượng với người chịu trách nhiệm

Với mỗi quy tắc, hãy ghi:

- Quy tắc và lý do nghiệp vụ.
- Phạm vi dữ liệu áp dụng.
- Thời điểm kiểm tra.
- Ngưỡng cảnh báo hoặc ngưỡng chặn.
- Nhóm xử lý khi vi phạm.
- Cách sửa dữ liệu và ghi nhận lịch sử.
- Cách xác nhận lỗi đã được khắc phục.

Ví dụ, nếu mã khách hàng bị trùng, hệ thống có thể phát hiện và đưa vào hàng đợi xử lý. Data steward xác định hồ sơ nào cần hợp nhất theo quy tắc đã được owner phê duyệt; nhóm kỹ thuật thực hiện thao tác an toàn và lưu dấu vết. Không nên tự động xóa một hồ sơ chỉ dựa trên việc hai tên hiển thị giống nhau.

### 7.3. Kiểm tra ở nhiều điểm trong luồng

Có thể kiểm tra dữ liệu ở:

1. Nơi nhập hoặc tạo dữ liệu.
2. Nguồn có thẩm quyền trước khi ghi nhận.
3. Điểm tiếp nhận dữ liệu từ nguồn.
4. Sau bước biến đổi.
5. Trước khi công bố cho consumer.
6. Trong quá trình consumer sử dụng.

Kiểm tra tại nguồn giúp ngăn dữ liệu sai đi vào hệ thống. Kiểm tra ở điểm tiếp nhận phát hiện lỗi tích hợp. Kiểm tra sau biến đổi bảo đảm quy tắc chuyển đổi không làm hỏng dữ liệu. Consumer vẫn cần kiểm tra điều kiện cần thiết cho chính quy trình của mình.

Không nên chỉ dựa vào kiểm tra ở báo cáo cuối cùng, vì lúc đó việc tìm nguồn gây lỗi và khắc phục có thể rất tốn kém.

## 8. Quy định truy cập, chia sẻ và bảo vệ dữ liệu

### 8.1. Xác định mục đích và phạm vi chia sẻ

Mỗi consumer cần có mục đích sử dụng được xác nhận. Hãy xác định:

- Consumer cần trường nào và vì sao?
- Có thể dùng dữ liệu tổng hợp hoặc đã ẩn danh không?
- Consumer có cần quyền xem dữ liệu cá nhân không?
- Dữ liệu có được chuyển ra ngoài tổ chức hoặc qua biên giới hệ thống không?
- Consumer được phép lưu bản sao trong bao lâu?
- Có được chia sẻ tiếp cho bên thứ ba không?
- Khi mục đích kết thúc, dữ liệu và bản sao phải được xử lý ra sao?

Nguyên tắc giảm thiểu dữ liệu giúp tránh gửi cả hồ sơ khách hàng khi consumer chỉ cần mã khách hàng và trạng thái đơn hàng.

### 8.2. Mô hình quyền theo vai trò và phạm vi

Quyền truy cập cần gắn với hành động và phạm vi dữ liệu. Ví dụ, một ứng dụng chăm sóc khách hàng có thể được phép đọc tên, thông tin liên hệ và trạng thái đơn hàng trong phạm vi phụ trách; ứng dụng phân tích có thể chỉ nhận dữ liệu đã giả danh; đối tác giao hàng chỉ nhận thông tin cần thiết cho kiện hàng được giao.

Nếu hệ thống có nhiều tổ chức hoặc tenant, cần xác định cách giữ ranh giới dữ liệu trong API, bảng chia sẻ, tác vụ nền và báo cáo. Một consumer được cấp quyền vào một bảng chung vẫn phải bị giới hạn theo phạm vi được phép.

### 8.3. Bảo vệ bản sao và dữ liệu dẫn xuất

Dữ liệu được sao chép sang kho dữ liệu, bộ nhớ đệm, công cụ tìm kiếm, tệp xuất hoặc môi trường kiểm thử vẫn có thể chứa thông tin nhạy cảm. Chính sách cần xác định:

- Thuộc tính nào được phép sao chép.
- Có cần mã hóa, che hoặc giả danh không.
- Ai được truy cập bản sao.
- Thời hạn lưu giữ và cách xóa.
- Cách xử lý dữ liệu trong bản sao lưu.
- Cách kiểm tra việc chia sẻ lại hoặc xuất dữ liệu.

Không nên cho rằng dữ liệu đã rời khỏi hệ thống nguồn thì không còn thuộc trách nhiệm của owner. Cần có cơ chế phối hợp giữa producer, consumer và người quản lý dữ liệu để thực hiện chính sách.

## 9. Xử lý dữ liệu trễ, thiếu, trùng và sai thứ tự

### 9.1. Xác định hành vi khi nguồn gặp sự cố

Mỗi consumer cần biết phải làm gì nếu nguồn không truy cập được, dữ liệu đến chậm hoặc bản ghi không hợp lệ.

Các câu hỏi cần trả lời:

- Có thể tiếp tục công việc bằng dữ liệu gần nhất không?
- Dữ liệu cũ tối đa bao lâu thì không còn được dùng?
- Có cần hiển thị trạng thái “dữ liệu chưa cập nhật” không?
- Yêu cầu có được xếp hàng để thử lại không?
- Ai được thông báo khi nguồn ngừng gửi dữ liệu?
- Khi dịch vụ phục hồi, cách đồng bộ bù và đối soát là gì?

Đối với dữ liệu quan trọng cho quyết định giao dịch, dùng bản sao cũ có thể gây hậu quả. Với một báo cáo xu hướng, có thể tiếp tục hiển thị số liệu gần nhất nhưng cần chỉ rõ thời điểm dữ liệu được cập nhật.

### 9.2. Chống xử lý trùng và xử lý sai thứ tự

Thông điệp hoặc sự kiện có thể được gửi lại khi producer không nhận được xác nhận hoặc consumer gặp lỗi. Consumer cần có cách nhận biết một sự kiện đã được xử lý, thường dựa trên event_id, mã giao dịch hoặc khóa idempotency.

Nếu nhiều sự kiện cho cùng một đối tượng đến sai thứ tự, cần có số phiên bản, sequence hoặc thời điểm nghiệp vụ đủ tin cậy để xác định thứ tự. Không nên chỉ so sánh thời điểm nhận ở consumer vì mạng và hàng đợi có thể làm thay đổi thứ tự.

### 9.3. Xử lý xóa và dữ liệu đến muộn

Một luồng đồng bộ phải mô tả cách biểu diễn bản ghi bị xóa. Nếu chỉ bỏ qua bản ghi, consumer có thể giữ dữ liệu cũ vô thời hạn. Tùy công nghệ, có thể cần tombstone, sự kiện xóa hoặc trạng thái ngừng hiệu lực.

Dữ liệu đến muộn cần được xử lý theo ý nghĩa nghiệp vụ. Một giao dịch ghi nhận hôm nay nhưng có hiệu lực từ ngày trước có thể làm thay đổi báo cáo lịch sử. Hợp đồng cần xác định có cho phép cập nhật lại kỳ đã chốt không, và nếu có thì cần ghi nhận phiên bản hoặc điều chỉnh như thế nào.

## 10. Ví dụ xuyên suốt: hệ thống bán hàng trực tuyến

Giả sử doanh nghiệp có website, CRM, hệ thống quản lý sản phẩm, kho, thanh toán, đơn hàng, giao hàng và nền tảng phân tích.

### 10.1. Xác định nguồn và owner theo miền

| Miền | Nguồn có thẩm quyền | Data owner (ví dụ) | Data steward (ví dụ) |
|---|---|---|---|
| Khách hàng | CRM | Bộ phận quản lý khách hàng | Nhóm vận hành dữ liệu khách hàng |
| Sản phẩm | PIM / danh mục sản phẩm | Bộ phận sản phẩm | Nhóm quản trị danh mục |
| Giá bán | Dịch vụ quản lý giá | Bộ phận định giá | Chuyên viên quản lý giá |
| Tồn kho | Hệ thống quản lý kho | Bộ phận vận hành kho | Nhóm kiểm soát tồn kho |
| Đơn hàng | Dịch vụ quản lý đơn | Bộ phận thương mại điện tử | Nhóm vận hành đơn hàng |
| Thanh toán | Sổ giao dịch nội bộ đối chiếu với nhà cung cấp | Bộ phận tài chính | Nhóm đối soát thanh toán |
| Giao nhận | Nền tảng điều phối hoặc dữ liệu đối tác được xác nhận | Bộ phận logistics | Nhóm theo dõi giao nhận |

Các vai trò trong bảng chỉ là ví dụ. Một dự án phải xác nhận tên đơn vị, người chịu trách nhiệm và phạm vi quyết định cụ thể.

### 10.2. Xác định consumer và nhu cầu

| Consumer | Dữ liệu cần | Độ mới | Quyền ghi |
|---|---|---|---|
| Website | Sản phẩm, giá, tồn kho khả dụng, trạng thái đơn của khách hàng | Tùy thao tác; tồn kho và giá cần đủ mới khi đặt hàng | Gửi yêu cầu tạo đơn; không tự sửa nguồn sản phẩm |
| Ứng dụng kho | Dòng hàng, số lượng cần lấy, thông tin giao nhận cần thiết | Gần thời gian thực cho công việc xử lý đơn | Ghi nhận thao tác kho vào hệ thống kho |
| Dịch vụ giao hàng | Mã kiện, địa chỉ, thông tin liên hệ cần thiết | Khi đơn đủ điều kiện giao | Gửi yêu cầu giao; cập nhật sự kiện giao nhận theo hợp đồng |
| Chăm sóc khách hàng | Hồ sơ khách hàng, đơn hàng, trạng thái thanh toán và giao nhận phù hợp quyền | Gần thời gian thực cho yêu cầu đang xử lý | Gửi yêu cầu điều chỉnh theo quy trình |
| Kho dữ liệu | Sự kiện và dữ liệu nghiệp vụ đã chuẩn hóa | Theo lịch hoặc độ trễ đã thỏa thuận | Chỉ đọc |
| Báo cáo quản trị | Dữ liệu tổng hợp doanh thu, đơn hàng, tồn kho | Theo chu kỳ báo cáo | Chỉ đọc |

### 10.3. Theo dõi một luồng dữ liệu

Khi khách hàng đặt hàng:

1. Website gửi yêu cầu tạo đơn đến dịch vụ quản lý đơn.
2. Dịch vụ quản lý đơn lấy thông tin giá từ nguồn có thẩm quyền và giữ lại giá đã chốt trong đơn.
3. Dịch vụ quản lý đơn yêu cầu hệ thống kho giữ chỗ tồn kho.
4. Dịch vụ thanh toán tạo hoặc xác nhận giao dịch theo hợp đồng với nhà cung cấp.
5. Khi đơn đủ điều kiện, dịch vụ quản lý đơn phát sự kiện cho hệ thống kho, giao hàng và nền tảng phân tích.
6. Hệ thống giao hàng nhận tập dữ liệu tối thiểu cần thiết cho kiện hàng.
7. Nền tảng phân tích nhận sự kiện, chuẩn hóa và lưu nguồn cùng thời điểm xử lý để phục vụ báo cáo.

Trong luồng này, website là nơi khởi tạo yêu cầu, nhưng không phải nguồn có thẩm quyền cho tồn kho hoặc trạng thái thanh toán. Nền tảng phân tích là consumer và có thể trở thành nguồn cung cấp dữ liệu cho báo cáo, nhưng không được tự ý cập nhật trạng thái đơn hàng. Mỗi bên có một trách nhiệm riêng.

### 10.4. Xử lý một sai lệch dữ liệu

Giả sử màn hình hỗ trợ hiển thị khách hàng có hai hồ sơ trùng:

- Data steward kiểm tra quy tắc nhận diện trùng và nguồn tạo hai hồ sơ.
- Data owner xác nhận quy tắc hợp nhất, đặc biệt với các thuộc tính có ý nghĩa nghiệp vụ khác nhau.
- System owner kiểm tra vì sao quy trình tạo hồ sơ không phát hiện bản ghi trùng.
- Các consumer được thông báo về mã hồ sơ chuẩn và cách ánh xạ mã cũ.
- Hệ thống lưu dấu vết hợp nhất để có thể giải thích các tham chiếu trước đó.

Nếu chỉ xóa một hồ sơ trong CRM mà không cập nhật khóa tham chiếu ở đơn hàng, báo cáo hoặc dịch vụ khác, dữ liệu có thể trở nên mồ côi hoặc sai lệch. Vì vậy, xử lý chất lượng phải tính đến toàn bộ luồng và các consumer.

## 11. Chuyển kết quả khảo sát thành yêu cầu mô hình dữ liệu

Sau khi xác định nguồn, owner và consumer, cần chuyển kết quả thành quyết định thiết kế cụ thể.

| Kết quả khảo sát | Quyết định mô hình hoặc tích hợp |
|---|---|
| Miền dữ liệu và định nghĩa | Thực thể, thuộc tính, kiểu dữ liệu và thuật ngữ chuẩn |
| Nguồn có thẩm quyền | Quy tắc tạo/cập nhật, quyền ghi, nguồn tham chiếu |
| Nhiều mã định danh | Khóa nghiệp vụ, khóa nội bộ và bảng ánh xạ mã |
| Nhiều consumer | Mô hình đọc, bản sao, view hoặc data product phù hợp |
| Yêu cầu lịch sử | Bản chụp, bảng phiên bản, sự kiện hoặc dữ liệu thời gian |
| Yêu cầu độ mới | API, sự kiện, CDC, batch hoặc replication |
| Quy tắc chất lượng | Ràng buộc, kiểm tra dữ liệu, cảnh báo và quy trình sửa sai |
| Quyền truy cập | Phân loại, chính sách truy cập, lọc theo vai trò hoặc tenant |
| Biến đổi dữ liệu | Quy tắc ánh xạ, lineage và phiên bản logic |
| Thay đổi hệ thống | Hợp đồng schema, tương thích và kế hoạch chuyển đổi |

### 11.1. Tách dữ liệu chủ, dữ liệu tham chiếu và dữ liệu giao dịch

Khi khảo sát nguồn, cần nhận diện loại dữ liệu:

- **Dữ liệu chủ (master data):** mô tả các đối tượng nghiệp vụ cốt lõi như khách hàng, sản phẩm hoặc nhà cung cấp.
- **Dữ liệu tham chiếu (reference data):** danh mục hoặc mã chuẩn như loại tiền tệ, trạng thái, vùng địa lý hoặc mã đơn vị.
- **Dữ liệu giao dịch (transaction data):** ghi nhận hoạt động phát sinh như đơn hàng, thanh toán, phiếu xuất kho.
- **Dữ liệu sự kiện (event data):** ghi nhận một điều đã xảy ra tại một thời điểm.
- **Dữ liệu phân tích (analytical data):** dữ liệu đã được tổ chức hoặc biến đổi để trả lời câu hỏi phân tích.

Các loại dữ liệu có vòng đời và yêu cầu cập nhật khác nhau. Danh mục tham chiếu có thể cần quy trình phê duyệt và phát hành phiên bản; giao dịch cần giữ dữ kiện tại thời điểm phát sinh; dữ liệu phân tích cần lưu lineage và thời điểm làm mới.

### 11.2. Thiết kế mô hình chuẩn hóa và mô hình phục vụ consumer

Một miền dữ liệu có thể có mô hình chuẩn dùng chung và các mô hình phục vụ từng consumer. Ví dụ, dữ liệu khách hàng chuẩn có thể được lưu theo cấu trúc chuẩn hóa; website cần một mô hình đọc tối ưu cho trang sản phẩm; báo cáo cần bảng tổng hợp theo ngày.

Khi tạo mô hình phục vụ, cần ghi rõ:

- Nguồn nào tạo ra dữ liệu đầu vào.
- Các trường được biến đổi hoặc suy diễn ra sao.
- Consumer nào được sử dụng.
- Độ mới và giới hạn chính xác.
- Cách đồng bộ khi nguồn thay đổi.
- Ai chịu trách nhiệm khi kết quả sai.

Không nên để mỗi consumer tự xây dựng một cách diễn giải riêng nếu có định nghĩa nghiệp vụ dùng chung. Ngược lại, cũng không cần ép mọi consumer dùng chung một cấu trúc vật lý nếu nhu cầu truy vấn khác nhau; điều cần thống nhất là ngữ nghĩa và trách nhiệm dữ liệu.

## 12. Viết tiêu chí chấp nhận cho nguồn, owner và consumer

Các yêu cầu cần có cách kiểm chứng. Một số kịch bản minh họa:

**Kịch bản xác định nguồn có thẩm quyền**

- Given: trạng thái đơn hàng xuất hiện trong dịch vụ đơn hàng và kho dữ liệu.
- When: hai nơi hiển thị trạng thái khác nhau.
- Then: người dùng và hệ thống biết nguồn nào có thẩm quyền cho trạng thái giao dịch, dữ liệu nào chỉ là bản sao và cách kiểm tra thời điểm đồng bộ.

**Kịch bản phân công owner**

- Given: một thuộc tính khách hàng có định nghĩa hoặc giá trị gây tranh chấp.
- When: nhóm kỹ thuật và nhóm chăm sóc khách hàng không thống nhất cách xử lý.
- Then: có owner được chỉ định để quyết định định nghĩa hoặc quy tắc, cùng steward chịu trách nhiệm điều phối xử lý.

**Kịch bản consumer nhận dữ liệu**

- Given: một consumer đăng ký nhận sự kiện đơn hàng đã xác nhận.
- When: producer phát hành sự kiện theo hợp đồng.
- Then: consumer nhận được các trường đã thống nhất, có thể nhận diện sự kiện trùng và biết cách xử lý phiên bản schema.

**Kịch bản thay đổi hợp đồng**

- Given: producer cần đổi tên hoặc ngừng cung cấp một trường.
- When: thay đổi được đề xuất.
- Then: tác động đến consumer được đánh giá, owner phê duyệt thay đổi nghiệp vụ, consumer được thông báo và có thời gian chuyển đổi theo quy định.

**Kịch bản dữ liệu đến trễ**

- Given: báo cáo sử dụng dữ liệu giao dịch theo lô.
- When: một giao dịch đến sau thời điểm chốt lô.
- Then: báo cáo thể hiện thời điểm cập nhật, áp dụng quy tắc điều chỉnh hoặc ghi nhận dữ liệu đến muộn đã được thống nhất.

**Kịch bản truy cập theo mục đích**

- Given: đối tác giao hàng chỉ cần dữ liệu để giao một kiện hàng.
- When: dữ liệu được gửi qua hợp đồng tích hợp.
- Then: đối tác chỉ nhận các trường được phê duyệt cho kiện hàng đó và không nhận toàn bộ hồ sơ khách hàng.

## 13. Lỗi thường gặp khi khảo sát

- **Coi hệ thống đầu tiên nhập dữ liệu là nguồn có thẩm quyền:** bỏ qua bước xác minh, phê duyệt hoặc hợp nhất.
- **Chỉ định một nguồn duy nhất cho cả miền lớn:** không nhận ra thẩm quyền có thể khác nhau theo thuộc tính và mục đích.
- **Coi nhóm kỹ thuật là data owner:** nhầm quyền vận hành nền tảng với trách nhiệm quyết định ý nghĩa nghiệp vụ.
- **Chỉ liệt kê tên consumer:** không biết họ cần trường nào, độ mới, lịch sử và chất lượng ra sao.
- **Cho nhiều hệ thống cùng ghi một thuộc tính:** không có quy tắc giải quyết xung đột hoặc đồng bộ vòng lặp.
- **Không ghi định nghĩa trường:** các consumer hiểu khác nhau về amount, status, date hoặc quantity.
- **Bỏ qua khóa định danh xuyên hệ thống:** ghép nhầm bản ghi hoặc không truy nguyên được đối tượng.
- **Chỉ kiểm tra schema:** dữ liệu đúng kiểu nhưng vẫn có thể sai ý nghĩa, thiếu hoặc đến quá muộn.
- **Không quản lý bản sao:** dữ liệu bị xóa hoặc thay đổi ở nguồn nhưng còn tồn tại ở consumer.
- **Không có quy trình xử lý sự cố:** lỗi dữ liệu được chuyển lòng vòng giữa các nhóm.
- **Không thông báo thay đổi hợp đồng:** producer phát hành schema mới khiến consumer hỏng hoặc diễn giải sai.
- **Xem kho dữ liệu là nguồn giao dịch:** dùng bản sao phân tích có độ trễ để đưa ra quyết định cần trạng thái mới nhất.

## 14. Danh sách kiểm tra khi hoàn tất khảo sát

Trước khi chuyển sang thiết kế chi tiết, hãy xác nhận:

- [ ] Đã liệt kê các miền dữ liệu và định nghĩa nghiệp vụ quan trọng.
- [ ] Đã xác định nơi dữ liệu được tạo, nơi được kiểm tra và nguồn có thẩm quyền.
- [ ] Đã xác định thẩm quyền theo thuộc tính hoặc mục đích khi một miền có nhiều nguồn.
- [ ] Đã có quy tắc xử lý khi các nguồn cung cấp giá trị mâu thuẫn.
- [ ] Đã chỉ định data owner và đầu mối quản lý dữ liệu hằng ngày cho từng miền.
- [ ] Đã phân biệt trách nhiệm nghiệp vụ, quản lý chất lượng và vận hành kỹ thuật.
- [ ] Đã liệt kê consumer, mục đích, trường dữ liệu và quyền đọc/ghi.
- [ ] Đã xác định độ mới, lịch sử, khối lượng, độ sẵn sàng và chất lượng cần thiết cho từng consumer.
- [ ] Đã mô tả các luồng dữ liệu, bước biến đổi và cách truy nguyên.
- [ ] Đã xác định khóa định danh và quy tắc ánh xạ mã giữa các hệ thống.
- [ ] Đã thống nhất hợp đồng dữ liệu, ngữ nghĩa, schema và cách quản lý thay đổi.
- [ ] Đã có quy tắc xử lý dữ liệu trễ, thiếu, trùng, sai thứ tự và bị xóa.
- [ ] Đã xác định quyền truy cập, mục đích chia sẻ và vòng đời của các bản sao.
- [ ] Đã có tiêu chí chấp nhận và đầu mối xử lý sự cố dữ liệu.

Kết quả của bước khảo sát là bản đồ miền dữ liệu, ma trận nguồn có thẩm quyền, danh sách owner và consumer, cùng các hợp đồng và quy tắc trao đổi dữ liệu. Những thông tin này tạo cơ sở để thiết kế thực thể, thuộc tính, khóa, quan hệ, mô hình tích hợp và các ràng buộc phù hợp với cách tổ chức thực sự tạo ra và sử dụng dữ liệu.

