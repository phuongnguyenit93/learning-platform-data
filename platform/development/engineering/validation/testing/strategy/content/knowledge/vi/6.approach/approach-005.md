# Kiểm thử dựa trên kinh nghiệm và giả thuyết về lỗi

Kiểm thử dựa trên kinh nghiệm là cách thiết kế và thực hiện kiểm thử bằng cách vận dụng kiến thức, trực giác nghề nghiệp, hiểu biết về sản phẩm và những bài học từ các lỗi đã xảy ra. Người kiểm thử dùng kinh nghiệm để nhận ra khu vực dễ sai, đặt câu hỏi về những giả định chưa rõ và thử những tình huống mà tài liệu yêu cầu hoặc bộ kiểm thử hiện có có thể chưa đề cập.

Một kỹ thuật tiêu biểu của cách tiếp cận này là **dự đoán lỗi (error guessing)**. Người kiểm thử dựa trên hiểu biết về hệ thống và các kiểu lỗi thường gặp để dự đoán điều gì có thể sai, sau đó thiết kế thao tác hoặc dữ liệu nhằm làm lộ lỗi đó. Ví dụ, khi kiểm tra chức năng đăng nhập, người kiểm thử có thể thử gửi biểu mẫu nhiều lần, nhập chuỗi rất dài, dùng tài khoản bị khóa, gửi yêu cầu đồng thời hoặc ngắt kết nối ngay sau khi gửi thông tin.

Cách tiếp cận này đặc biệt hữu ích khi yêu cầu chưa đầy đủ, hệ thống phức tạp, thời gian kiểm thử hạn chế hoặc nhóm có lịch sử lỗi phong phú. Nó giúp phát hiện những vấn đề khó mô tả thành quy tắc từ đầu. Tuy nhiên, kết quả phụ thuộc vào chất lượng kinh nghiệm và khả năng suy luận của người thực hiện. Vì vậy, kiểm thử dựa trên kinh nghiệm cần được tổ chức có chủ đích, ghi nhận được bằng chứng và kết hợp với các kỹ thuật kiểm thử khác.

## 1. Bản chất của kiểm thử dựa trên kinh nghiệm

Các kỹ thuật kiểm thử theo đặc tả thường bắt đầu từ yêu cầu, mô hình hoặc quy tắc đã được mô tả. Kiểm thử dựa trên kinh nghiệm bổ sung một nguồn thông tin khác: những gì người kiểm thử đã học được từ việc xây dựng, sử dụng, vận hành và điều tra lỗi của hệ thống.

Nguồn kinh nghiệm có thể đến từ:

- Hiểu biết về nghiệp vụ, người dùng và các tình huống sử dụng thực tế.
- Kiến thức về kiến trúc, công nghệ, framework, cơ sở dữ liệu và giao thức.
- Những lỗi từng xuất hiện trong sản phẩm hoặc các hệ thống tương tự.
- Các sự cố vận hành, phản hồi hỗ trợ khách hàng và khiếu nại của người dùng.
- Những thay đổi gần đây, khu vực mã nguồn phức tạp hoặc phụ thuộc khó kiểm soát.
- Các quy luật về lỗi thường gặp trong thiết kế giao diện, xử lý dữ liệu, phân quyền và tích hợp.
- Trực giác được hình thành qua nhiều lần thiết kế, thực hiện và phân tích kiểm thử.

Kinh nghiệm không chỉ là số năm làm việc. Một người làm lâu năm nhưng ít tiếp xúc với một lĩnh vực có thể không dự đoán tốt lỗi đặc thù của lĩnh vực đó. Ngược lại, một thành viên mới có thể phát hiện giả định khó hiểu hoặc hành vi bất thường vì họ nhìn hệ thống bằng góc nhìn ít bị ảnh hưởng bởi thói quen cũ.

Do đó, nhóm nên kết hợp nhiều góc nhìn: người hiểu nghiệp vụ, người phát triển, người kiểm thử, người vận hành và người trực tiếp sử dụng sản phẩm. Sự đa dạng này làm tăng khả năng nhận diện các kiểu lỗi khác nhau.

### Khi nào cách tiếp cận này có giá trị?

Kiểm thử dựa trên kinh nghiệm thường hữu ích trong các tình huống:

- Yêu cầu còn thiếu chi tiết hoặc chưa mô tả hết hành vi ngoại lệ.
- Cần kiểm tra nhanh một thay đổi hoặc một bản dựng mới.
- Sản phẩm có nhiều tương tác và trạng thái khó liệt kê hết.
- Nhóm có dữ liệu về lỗi cũ hoặc sự cố thực tế.
- Một chức năng mới có hành vi chưa quen thuộc và cần khám phá.
- Các bộ kiểm thử định sẵn chưa bao phủ được những giả định hoặc ranh giới bất thường.
- Cần tìm hiểu sản phẩm trước khi hoàn thiện kế hoạch kiểm thử chi tiết.

Cách tiếp cận này cũng hữu ích sau khi sửa lỗi. Người kiểm thử có thể dựa vào nguyên nhân gốc và những điều kiện từng làm lỗi xuất hiện để tìm thêm trường hợp liên quan, thay vì chỉ chạy lại đúng một tình huống đã tái hiện lỗi.

## 2. Phân biệt kiểm thử dựa trên kinh nghiệm với các cách tiếp cận khác

Các cách tiếp cận kiểm thử bổ sung cho nhau. Không nên xem kinh nghiệm là sự thay thế cho yêu cầu, thiết kế kiểm thử hoặc kiểm thử tự động.

| Cách tiếp cận | Nguồn định hướng chính | Cách lựa chọn kiểm thử |
|---|---|---|
| Dựa trên đặc tả | Yêu cầu, tiêu chí chấp nhận, mô hình và quy tắc | Xây dựng trường hợp từ hành vi được mô tả |
| Dựa trên cấu trúc | Mã nguồn, kiến trúc và luồng điều khiển | Chọn kiểm thử để thực thi các cấu trúc hoặc nhánh cần thiết |
| Dựa trên kinh nghiệm | Kiến thức, trực giác, lịch sử lỗi và hiểu biết thực tế | Dự đoán điểm yếu, khám phá hành vi và thử các tình huống có khả năng gây lỗi |

Ví dụ, với chức năng chuyển tiền:

- Dựa trên đặc tả, nhóm kiểm tra số tiền hợp lệ, hạn mức và quy tắc số dư.
- Dựa trên cấu trúc, nhóm xem xét các nhánh xử lý trong mã chuyển tiền và điều kiện lỗi.
- Dựa trên kinh nghiệm, người kiểm thử thử gửi cùng yêu cầu nhiều lần, chuyển tiền đồng thời từ hai phiên, ngắt mạng sau khi xác nhận hoặc dùng số tiền có độ chính xác bất thường.

Một kiểm thử có thể đồng thời xuất phát từ nhiều cách tiếp cận. Người kiểm thử có thể dự đoán lỗi gửi lặp từ kinh nghiệm, rồi chuyển tình huống đó thành trường hợp kiểm thử có thể tái tạo và tự động hóa. Điều quan trọng là hiểu nguồn gốc giả thuyết để biết vì sao kiểm thử được chọn và rủi ro nào đang được kiểm tra.

## 3. Dự đoán lỗi là gì?

Dự đoán lỗi là kỹ thuật trong đó người kiểm thử dùng kinh nghiệm và hiểu biết về những sai sót có khả năng xảy ra để chủ động tạo tình huống kiểm thử. Thay vì chờ một danh sách trường hợp được cung cấp, người kiểm thử tự đặt câu hỏi: “Điều gì có thể bị làm sai ở đây?” và “Tôi có thể thao tác thế nào để làm lộ vấn đề đó?”

Một dự đoán tốt thường dựa trên một giả thuyết có thể kiểm chứng. Ví dụ:

- Giả thuyết: hệ thống không xử lý đúng khi người dùng nhấn nút gửi hai lần.
- Thao tác: gửi cùng yêu cầu liên tiếp hoặc đồng thời.
- Kết quả mong đợi: chỉ có một giao dịch hợp lệ được ghi nhận, hoặc hệ thống trả về cùng kết quả theo cơ chế idempotency.
- Bằng chứng: phản hồi API, bản ghi giao dịch và trạng thái dữ liệu sau thao tác.

Giả thuyết không nhất thiết phải đúng. Mục đích là tạo một phép thử có khả năng xác nhận hoặc bác bỏ nhận định. Nếu không có lỗi, kết quả vẫn cung cấp thông tin về hành vi của hệ thống trong điều kiện đã thử.

### Các nguồn hình thành giả thuyết lỗi

**Lỗi đã từng xảy ra.** Nếu một phiên bản trước từng làm mất dữ liệu khi người dùng rời trang giữa lúc lưu, hãy kiểm tra lại tình huống này ở những chức năng có cơ chế lưu tương tự.

**Lỗi phổ biến theo công nghệ.** Hệ thống web có thể gặp lỗi trạng thái phiên, xử lý bộ nhớ đệm, mã hóa đầu vào hoặc yêu cầu đồng thời. Hệ thống phân tán có thể gặp thông điệp lặp, đến sai thứ tự, timeout hoặc lỗi một phần.

**Đặc điểm nghiệp vụ.** Hệ thống tài chính cần chú ý làm tròn, dấu âm, đơn vị tiền và giao dịch lặp. Hệ thống đặt lịch cần chú ý múi giờ, thời gian chuyển đổi mùa, đặt trùng và khoảng thời gian sát nhau.

**Đặc điểm triển khai.** Một thay đổi về cấu hình, quyền truy cập, phiên bản thư viện hoặc thứ tự triển khai có thể tạo lỗi chỉ xuất hiện trong một môi trường nhất định.

**Hành vi người dùng.** Người dùng có thể nhấn nút nhiều lần, nhập dữ liệu bất thường, mở nhiều tab, quay lại trang trước, bỏ dở quy trình hoặc thao tác theo thứ tự không phổ biến.

**Dấu hiệu từ hệ thống.** Log có cảnh báo lặp lại, thời gian phản hồi tăng, lỗi chỉ xảy ra ở một nhóm người dùng hoặc dữ liệu có trạng thái không nhất quán đều có thể gợi ý giả thuyết mới.

## 4. Một quy trình thực hiện dự đoán lỗi

Dự đoán lỗi có thể diễn ra tự do trong một phiên khám phá, nhưng vẫn nên có quy trình để giữ trọng tâm và giúp nhóm học hỏi từ kết quả.

### Bước 1: Hiểu mục tiêu và ranh giới của chức năng

Tìm hiểu chức năng đang làm gì, ai sử dụng, dữ liệu nào được xử lý, trạng thái nào có thể thay đổi và thành phần nào tham gia. Xác định các giả định chưa rõ hoặc điểm có thể gây hậu quả lớn nếu sai.

Ví dụ, với chức năng cập nhật địa chỉ giao hàng, cần hiểu địa chỉ được lưu vào hồ sơ hay đơn hàng, thời điểm nào địa chỉ bị khóa, vai trò nào được phép sửa và dữ liệu có được đồng bộ sang dịch vụ vận chuyển hay không.

### Bước 2: Thu thập dấu hiệu và kinh nghiệm liên quan

Xem lại lỗi cũ, sự cố, phản hồi hỗ trợ, thay đổi mã nguồn, log và các vấn đề thường gặp ở công nghệ đang sử dụng. Trao đổi với người phát triển hoặc người hiểu nghiệp vụ để nhận diện những điểm dễ sai.

Không cần đọc mọi tài liệu. Hãy tập trung vào thông tin có thể làm thay đổi giả thuyết hoặc thứ tự ưu tiên.

### Bước 3: Liệt kê các giả thuyết lỗi

Viết giả thuyết ngắn gọn và cụ thể. Một giả thuyết có thể nêu:

- Điều kiện hoặc thao tác gây lỗi.
- Hành vi sai có thể xuất hiện.
- Hậu quả đối với người dùng hoặc dữ liệu.
- Lý do nghi ngờ, chẳng hạn lỗi tương tự trong quá khứ hoặc logic xử lý phức tạp.

Ví dụ: “Nếu người dùng gửi yêu cầu cập nhật hồ sơ đồng thời từ hai thiết bị, bản cập nhật đến sau có thể ghi đè dữ liệu mới hơn mà không có cảnh báo.”

### Bước 4: Xếp thứ tự ưu tiên

Ưu tiên giả thuyết dựa trên tác động, khả năng xảy ra, mức độ phơi nhiễm và khả năng phát hiện. Các giả thuyết liên quan đến mất dữ liệu, lộ thông tin, giao dịch sai hoặc không thể phục hồi thường cần được thử sớm.

Nếu thời gian ngắn, hãy chọn các phép thử có khả năng cung cấp bằng chứng lớn nhất. Không cần cố thực hiện tất cả dự đoán chỉ vì chúng đã được liệt kê.

### Bước 5: Thiết kế thao tác và kết quả mong đợi

Mỗi giả thuyết cần một cách kiểm tra có thể thực hiện. Xác định dữ liệu đầu vào, trạng thái ban đầu, thao tác, điều kiện môi trường và bằng chứng cần quan sát.

Kết quả mong đợi cần đủ rõ để phân biệt hành vi đúng với sai. Nếu chưa biết hành vi nào được chấp nhận, hãy ghi nhận đây là câu hỏi cần xác minh với người phụ trách sản phẩm hoặc kỹ thuật.

### Bước 6: Thực hiện và quan sát

Chạy phép thử, quan sát giao diện, phản hồi API, trạng thái dữ liệu, log, metric hoặc thông điệp giữa các dịch vụ. Khi phát hiện dấu hiệu bất thường, thử tái hiện với điều kiện được kiểm soát để phân biệt lỗi sản phẩm với sự cố môi trường hoặc dữ liệu thử nghiệm.

### Bước 7: Ghi nhận kết quả và mở rộng có trọng điểm

Nếu tìm thấy lỗi, lưu các bước tái hiện, dữ liệu, môi trường, kết quả thực tế, kết quả mong đợi và bằng chứng. Nếu không tìm thấy lỗi, ghi lại điều kiện đã thử và giới hạn của phép thử.

Từ kết quả, có thể mở rộng sang các trường hợp liên quan. Ví dụ, nếu gửi lặp không tạo giao dịch trùng nhưng một yêu cầu đến sau lại cập nhật trạng thái sai, hãy thử thêm các thứ tự thông điệp và tình huống phản hồi chậm.

## 5. Các nhóm giả thuyết lỗi thường dùng

Một danh sách gợi ý giúp người kiểm thử khởi đầu nhanh hơn. Danh sách này không phải checklist bắt buộc; cần chọn mục phù hợp với chức năng và kiến trúc.

### Đầu vào và dữ liệu

- Bỏ trống trường bắt buộc.
- Nhập chuỗi quá dài hoặc quá ngắn.
- Dùng ký tự Unicode, dấu tiếng Việt, khoảng trắng đầu/cuối hoặc ký tự điều khiển.
- Nhập số âm, số 0, số rất lớn, số thập phân hoặc định dạng không hợp lệ.
- Dùng ngày không tồn tại, ngày nhuận, múi giờ khác hoặc thời điểm sát ranh giới.
- Gửi dữ liệu sai kiểu, thiếu trường hoặc có trường thừa.
- Dùng dữ liệu trùng lặp, dữ liệu cũ hoặc tham chiếu đến đối tượng đã bị xóa.
- Thay đổi dữ liệu sau khi màn hình đã tải nhưng trước khi gửi.

### Trạng thái và trình tự thao tác

- Thực hiện thao tác khi đối tượng ở trạng thái không phù hợp.
- Nhấn gửi nhiều lần hoặc làm mới trang ngay sau thao tác.
- Quay lại trang trước rồi gửi lại biểu mẫu.
- Mở cùng đối tượng trong nhiều tab hoặc thiết bị.
- Thực hiện hai cập nhật đồng thời.
- Gửi yêu cầu theo thứ tự khác dự kiến.
- Hủy quy trình ở giữa và tiếp tục lại sau đó.
- Thực hiện thao tác sau khi phiên đăng nhập hết hạn.

### Quyền và bảo mật

- Truy cập tài nguyên của người dùng khác bằng cách thay mã định danh.
- Gọi trực tiếp API dù giao diện không hiển thị nút thao tác.
- Dùng tài khoản bị khóa, hết hạn hoặc thiếu quyền.
- Thử thay đổi vai trò hoặc thuộc tính nhạy cảm trong yêu cầu.
- Sử dụng token cũ sau khi đăng xuất hoặc thu hồi quyền.
- Kiểm tra dữ liệu nhạy cảm có xuất hiện trong thông báo, log hoặc phản hồi lỗi không.

Các phép thử bảo mật cần được thực hiện trong môi trường và phạm vi được phép, với dữ liệu thử nghiệm phù hợp.

### Tích hợp và phụ thuộc

- Dịch vụ ngoài không phản hồi.
- Phản hồi đến muộn hoặc đến sai thứ tự.
- Nhận cùng một thông điệp nhiều lần.
- Kết nối bị ngắt sau khi dịch vụ đã xử lý nhưng trước khi phía gọi nhận phản hồi.
- Dữ liệu giữa hai dịch vụ không đồng bộ.
- Một dịch vụ thành công trong khi dịch vụ khác thất bại.
- Hết thời gian chờ, retry liên tiếp hoặc circuit breaker chuyển trạng thái.
- Dịch vụ phụ thuộc trả dữ liệu thiếu, sai định dạng hoặc không còn tương thích.

### Giao diện và trải nghiệm

- Thay đổi kích thước cửa sổ hoặc xoay thiết bị trong lúc thao tác.
- Dùng bàn phím thay cho chuột.
- Nhấn nút liên tục khi giao diện đang tải.
- Làm mới hoặc đóng trang giữa một thao tác.
- Mất kết nối rồi kết nối lại.
- Dùng trình duyệt hoặc phiên bản nằm trong phạm vi hỗ trợ.
- Nhập nội dung dài làm tràn bố cục hoặc che mất nút thao tác.
- Kiểm tra thông báo lỗi có chỉ rõ cách khắc phục hay không.

### Hiệu năng và tài nguyên

- Tạo nhiều bản ghi hoặc tải tập dữ liệu lớn.
- Thực hiện nhiều yêu cầu đồng thời.
- Giữ phiên làm việc lâu và lặp lại thao tác.
- Gửi yêu cầu trong lúc hệ thống đang bận.
- Kiểm tra hành vi khi bộ nhớ, kết nối hoặc dung lượng gần giới hạn.
- Thử tải tăng đột ngột và giảm đột ngột.
- Quan sát thời gian phản hồi khi bộ nhớ đệm chưa có dữ liệu và khi đã có dữ liệu.

Không phải mọi tình huống trong danh sách đều là lỗi. Chúng là gợi ý để hình thành giả thuyết; kết quả mong đợi phải dựa trên yêu cầu, hợp đồng và thiết kế của hệ thống.

## 6. Ví dụ thực tế: dự đoán lỗi cho chức năng đăng nhập

Giả sử ứng dụng cho phép người dùng đăng nhập bằng email và mật khẩu. Yêu cầu cơ bản nêu rằng người dùng hợp lệ có thể đăng nhập và người dùng không hợp lệ nhận thông báo lỗi.

Nếu chỉ kiểm tra một tài khoản hợp lệ và một mật khẩu sai, nhóm có thể bỏ sót nhiều hành vi quan trọng. Người kiểm thử có kinh nghiệm sẽ đặt thêm giả thuyết.

| Giả thuyết | Cách thử | Kết quả mong đợi |
|---|---|---|
| Email không được chuẩn hóa nhất quán | Nhập email có chữ hoa hoặc khoảng trắng đầu/cuối | Hệ thống xử lý theo quy tắc đã công bố và không tạo nhầm tài khoản |
| Có thể gửi nhiều yêu cầu đăng nhập liên tiếp | Nhấn nút đăng nhập nhiều lần hoặc gửi yêu cầu đồng thời | Không tạo nhiều phiên bất thường; giới hạn thử sai được áp dụng đúng |
| Thông báo lỗi tiết lộ tài khoản có tồn tại | Thử email không tồn tại và mật khẩu sai | Thông báo không làm lộ thông tin tài khoản ngoài chính sách |
| Phiên cũ vẫn dùng được sau đăng xuất | Đăng nhập, sao chép token, đăng xuất rồi thử token cũ | Token bị vô hiệu hóa theo chính sách phiên |
| Khóa tài khoản không được áp dụng nhất quán | Thử đăng nhập với tài khoản đã bị khóa | Hệ thống từ chối và không tạo phiên |
| Phiên có thể bị ghi nhận dù phản hồi lỗi | Ngắt kết nối trong lúc đăng nhập rồi kiểm tra trạng thái phiên | Trạng thái phiên nhất quán và có thể xác định kết quả |
| Giao diện xử lý sai khi nhập dài | Nhập email hoặc mật khẩu rất dài | Giao diện vẫn kiểm soát dữ liệu và phản hồi phù hợp |
| Kiểm tra giới hạn thử sai có thể bị né qua nhiều địa chỉ | Thử theo cách mô phỏng phù hợp với chính sách bảo mật | Cơ chế giới hạn được áp dụng đúng theo thiết kế |

Bảng trên minh họa cách biến trực giác thành giả thuyết có thể kiểm chứng. Một số kết quả, chẳng hạn chuẩn hóa email hoặc chính sách vô hiệu hóa phiên, phụ thuộc vào yêu cầu sản phẩm. Người kiểm thử cần xác nhận quy tắc trước khi kết luận đó là lỗi.

## 7. Ví dụ thực tế: dự đoán lỗi trong giao dịch thanh toán

Với giao dịch thanh toán, những lỗi nghiêm trọng thường liên quan đến việc yêu cầu được xử lý nhiều lần, trạng thái không nhất quán hoặc kết quả từ nhà cung cấp đến muộn.

Một số giả thuyết có thể gồm:

- Người dùng nhấn nút thanh toán hai lần tạo hai giao dịch.
- Nhà cung cấp đã trừ tiền nhưng ứng dụng hết thời gian chờ và đánh dấu giao dịch thất bại.
- Thông báo thanh toán thành công được gửi lại nhiều lần làm đơn hàng cập nhật lặp.
- Thông báo thất bại đến sau thông báo thành công làm trạng thái bị ghi đè.
- Người dùng hủy đơn trong lúc giao dịch đang xử lý.
- Dịch vụ đơn hàng cập nhật thành công nhưng dịch vụ kho không nhận được sự kiện.
- Số tiền gửi sang nhà cung cấp khác với tổng tiền hiển thị do làm tròn hoặc áp dụng ưu đãi.
- Một yêu cầu cũ được gửi lại sau khi đơn hàng đã chuyển sang trạng thái khác.

Có thể mô tả một giả thuyết theo cấu trúc:

~~~text
Giả thuyết:
Nếu nhà cung cấp đã xử lý thanh toán nhưng phản hồi bị mất,
hệ thống có thể đánh dấu đơn hàng thất bại dù tiền đã được trừ.

Thiết lập:
- Tạo đơn hàng thử nghiệm.
- Dùng phương thức thanh toán trong môi trường sandbox.
- Có thể mô phỏng timeout sau khi nhà cung cấp nhận yêu cầu.

Thực hiện:
1. Gửi yêu cầu thanh toán.
2. Cho nhà cung cấp xử lý thành công.
3. Ngắt phản hồi trước khi ứng dụng nhận được kết quả.
4. Kiểm tra trạng thái đơn và giao dịch.
5. Thực hiện cơ chế truy vấn hoặc đối soát theo thiết kế.

Kết quả mong đợi:
- Không tạo giao dịch thanh toán thứ hai ngoài ý muốn.
- Trạng thái cuối cùng phản ánh đúng kết quả của nhà cung cấp.
- Có bằng chứng để nhân viên vận hành điều tra và đối soát.
~~~

Phép thử này không chỉ kiểm tra một phản hồi API. Nó xem xét sự nhất quán giữa các hệ thống và cách sản phẩm xử lý trạng thái không chắc chắn. Nếu phát hiện vấn đề, nhóm cần điều tra cơ chế idempotency, đối soát, xử lý sự kiện và cập nhật trạng thái.

## 8. Kết hợp dự đoán lỗi với kiểm thử thăm dò

Kiểm thử thăm dò là cách người kiểm thử đồng thời học về hệ thống, thiết kế kiểm thử và thực hiện kiểm thử. Người kiểm thử có thể bắt đầu từ một mục tiêu hoặc phiên khám phá, sau đó điều chỉnh hướng đi dựa trên những gì quan sát được.

Dự đoán lỗi có thể cung cấp giả thuyết khởi đầu cho một phiên kiểm thử thăm dò. Trong phiên đó, người kiểm thử thử các tình huống, quan sát phản hồi và phát triển giả thuyết mới.

Ví dụ, khi khám phá chức năng chỉnh sửa hồ sơ:

1. Mục tiêu là xác minh người dùng có thể cập nhật thông tin cá nhân an toàn.
2. Giả thuyết ban đầu là hai phiên chỉnh sửa đồng thời có thể ghi đè dữ liệu.
3. Người kiểm thử mở cùng hồ sơ ở hai phiên và thay đổi các trường khác nhau.
4. Quan sát xem dữ liệu nào được lưu, có cảnh báo xung đột hay không.
5. Từ kết quả, mở rộng sang trường hợp một phiên đã hết hạn hoặc người dùng khác cập nhật cùng bản ghi.
6. Ghi nhận phát hiện và tạo trường hợp hồi quy nếu có lỗi.

Để phiên khám phá không trở nên tùy tiện, có thể dùng **charter** (nhiệm vụ khám phá) gồm mục tiêu, phạm vi, thời lượng, dữ liệu cần chuẩn bị và những câu hỏi cần trả lời.

Ví dụ charter:

~~~text
Mục tiêu:
Khám phá cách hệ thống xử lý cập nhật hồ sơ đồng thời.

Phạm vi:
API cập nhật hồ sơ và giao diện chỉnh sửa thông tin cá nhân.

Tập trung:
- Hai phiên cùng sửa một hồ sơ.
- Một phiên lưu sau khi dữ liệu đã bị thay đổi.
- Phiên đăng nhập hết hạn trong lúc chỉnh sửa.
- Phản hồi chậm hoặc gửi lại yêu cầu.

Bằng chứng:
- Giá trị dữ liệu trước và sau.
- Phản hồi API và thông báo giao diện.
- Log liên quan đến cập nhật.

Thời lượng:
45 phút.
~~~

Sau phiên khám phá, nhóm nên trao đổi ngắn về những gì đã học, rủi ro mới phát hiện, giả thuyết chưa kiểm tra và trường hợp nào cần được tự động hóa.

## 9. Ghi nhận và chuyển phát hiện thành kiểm thử hồi quy

Một phát hiện từ kinh nghiệm chỉ tạo giá trị lâu dài khi nhóm lưu lại đủ thông tin để người khác hiểu, tái hiện và sử dụng.

Khi ghi nhận một lỗi, nên có:

- Mô tả hành vi sai và ảnh hưởng.
- Các bước tái hiện theo thứ tự.
- Dữ liệu đầu vào và trạng thái ban đầu.
- Môi trường, phiên bản và cấu hình liên quan.
- Kết quả thực tế và kết quả mong đợi.
- Log, ảnh chụp, phản hồi API hoặc bằng chứng khác.
- Tần suất tái hiện và điều kiện khiến lỗi xuất hiện.
- Giả thuyết nguyên nhân nếu đã có bằng chứng.

Sau khi lỗi được sửa, hãy xác định mức kiểm thử phù hợp để ngăn lỗi quay lại. Nếu lỗi nằm trong một quy tắc tính toán, có thể thêm kiểm thử đơn vị. Nếu lỗi xảy ra giữa hai dịch vụ, có thể thêm kiểm thử hợp đồng hoặc tích hợp. Nếu lỗi chỉ xuất hiện trong hành trình hoàn chỉnh, có thể cần một kiểm thử đầu cuối đại diện.

Không phải mọi phát hiện thăm dò đều cần chuyển thành một kiểm thử tự động riêng. Có thể hợp nhất những trường hợp tương đương, dùng kiểm thử ở cấp độ thấp hơn hoặc giữ lại một charter để khám phá định kỳ. Cần cân nhắc giá trị bảo vệ so với thời gian chạy và chi phí bảo trì.

## 10. Những giới hạn và rủi ro của cách tiếp cận dựa trên kinh nghiệm

Kinh nghiệm có giá trị nhưng cũng có thể tạo ra điểm mù.

### Thiên kiến xác nhận

Người kiểm thử có thể chỉ tìm những gì phù hợp với suy đoán ban đầu và bỏ qua dấu hiệu trái ngược. Để giảm rủi ro, hãy ghi giả thuyết trước khi thử, tìm cả bằng chứng ủng hộ và bác bỏ, đồng thời mời người khác xem xét những giả định quan trọng.

### Phụ thuộc vào cá nhân

Nếu chỉ một người biết các lỗi cũ hoặc hiểu những góc khuất của hệ thống, kiến thức có thể mất đi khi người đó chuyển nhóm. Hãy ghi lại bài học, tổ chức phiên chia sẻ và để nhiều thành viên cùng thực hiện các phiên khám phá.

### Bỏ sót vì thiếu kinh nghiệm

Người mới có thể chưa biết những kiểu lỗi đặc thù của công nghệ hoặc nghiệp vụ. Có thể hỗ trợ bằng checklist dựa trên sự cố, hướng dẫn theo cặp và các buổi xem lại lỗi đã xảy ra. Checklist nên được cập nhật, không biến thành danh sách cứng thay thế suy nghĩ.

### Kết quả khó lặp lại

Một thao tác khám phá có thể phụ thuộc vào thời điểm, dữ liệu, trạng thái môi trường hoặc trình tự thao tác. Khi phát hiện vấn đề, cần thu hẹp điều kiện và ghi lại đủ thông tin để tái hiện. Nếu chưa tái hiện được, hãy mô tả mức độ chắc chắn thay vì khẳng định nguyên nhân.

### Bao phủ không có hệ thống

Kiểm thử tự do có thể dành quá nhiều thời gian cho khu vực quen thuộc và bỏ qua những chức năng ít được chú ý. Cần kết hợp charter, ma trận rủi ro, bản đồ hành trình và các kỹ thuật dựa trên đặc tả để theo dõi khoảng trống.

### Dự đoán sai hoặc quá nhiều

Không phải mọi khả năng tưởng tượng đều đáng kiểm tra. Nếu danh sách giả thuyết quá dài, nhóm sẽ mất trọng tâm. Hãy ưu tiên theo hậu quả, khả năng xảy ra và chi phí kiểm tra; bỏ qua hoặc ghi nhận riêng những giả thuyết ít liên quan.

### Nhầm hành vi bất ngờ với lỗi

Một hành vi có vẻ lạ chưa chắc vi phạm yêu cầu. Cần xác minh kỳ vọng với đặc tả, người phụ trách nghiệp vụ hoặc thiết kế đã thống nhất. Nếu yêu cầu chưa rõ, ghi nhận đó là điểm cần làm rõ thay vì tự đặt quy tắc.

## 11. Nâng cao chất lượng dự đoán lỗi trong nhóm

Khả năng dự đoán lỗi có thể được cải thiện bằng cách biến kinh nghiệm cá nhân thành tri thức chung.

**Tổ chức hồi cứu lỗi.** Sau sự cố, không chỉ sửa lỗi mà còn hỏi vì sao lỗi không được phát hiện, giả định nào đã sai và tình huống tương tự có thể xuất hiện ở đâu.

**Duy trì danh mục kiểu lỗi.** Ghi nhận các nhóm lỗi thường gặp theo sản phẩm hoặc công nghệ, chẳng hạn dữ liệu trùng, phân quyền sai, timeout, chuyển đổi múi giờ, làm tròn tiền và xử lý trạng thái không đồng bộ.

**Chia sẻ tri thức theo cặp.** Ghép người hiểu nghiệp vụ với người hiểu kỹ thuật hoặc ghép người có kinh nghiệm với thành viên mới để cùng xây dựng giả thuyết và thực hiện kiểm thử.

**Dùng nhiều góc nhìn.** Người phát triển có thể dự đoán lỗi từ cấu trúc mã; người kiểm thử từ hành vi và lịch sử lỗi; người vận hành từ log và sự cố; người dùng từ những cách sử dụng thực tế.

**Cập nhật checklist có chọn lọc.** Khi một kiểu lỗi lặp lại, bổ sung gợi ý vào checklist phù hợp. Định kỳ loại bỏ mục không còn liên quan hoặc chuyển chúng thành kiểm thử tự động khi có thể.

**Đánh giá hiệu quả bằng kết quả.** Theo dõi loại lỗi được phát hiện, mức độ nghiêm trọng, thời gian tìm ra vấn đề và khả năng tái hiện. Không dùng số lượng giả thuyết hoặc số lỗi tìm được làm mục tiêu đơn lẻ; điều đó có thể khuyến khích kiểm tra nhiều tình huống ít giá trị.

## 12. Mẫu ghi nhận giả thuyết dự đoán lỗi

Nhóm có thể sử dụng mẫu sau trong buổi lập kế hoạch hoặc phiên kiểm thử thăm dò:

| Trường | Nội dung |
|---|---|
| Chức năng hoặc luồng | Khu vực đang được kiểm tra |
| Giả thuyết lỗi | Điều gì có thể sai và trong điều kiện nào |
| Cơ sở dự đoán | Lỗi cũ, hiểu biết nghiệp vụ, thay đổi gần đây hoặc đặc điểm kỹ thuật |
| Tác động | Hậu quả nếu giả thuyết xảy ra |
| Mức ưu tiên | Cao, trung bình hoặc thấp theo rủi ro |
| Thiết lập | Môi trường, dữ liệu và trạng thái ban đầu |
| Thao tác | Các bước dùng để kiểm chứng |
| Kết quả mong đợi | Hành vi đúng theo yêu cầu hoặc quy tắc đã xác nhận |
| Kết quả thực tế | Điều đã quan sát được |
| Bằng chứng | Log, phản hồi, ảnh chụp, dữ liệu hoặc mã lỗi |
| Hành động tiếp theo | Báo lỗi, làm rõ yêu cầu, tạo hồi quy hoặc theo dõi thêm |

Ví dụ một bản ghi ngắn:

| Trường | Ví dụ |
|---|---|
| Chức năng hoặc luồng | Cập nhật địa chỉ giao hàng |
| Giả thuyết lỗi | Hai phiên cập nhật đồng thời có thể ghi đè dữ liệu mà không báo xung đột |
| Cơ sở dự đoán | Chức năng mới dùng cơ chế cập nhật toàn bộ bản ghi |
| Tác động | Đơn hàng có thể giao đến địa chỉ sai |
| Mức ưu tiên | Cao |
| Thiết lập | Một tài khoản, hai phiên, cùng một đơn thử nghiệm |
| Thao tác | Mở hai phiên, sửa địa chỉ khác nhau và lưu lần lượt |
| Kết quả mong đợi | Hệ thống bảo vệ cập nhật theo quy tắc, phát hiện xung đột hoặc áp dụng phiên bản mới nhất có chủ đích |
| Kết quả thực tế | Ghi nhận sau khi thực hiện |
| Bằng chứng | Phản hồi API, dữ liệu đơn hàng và log cập nhật |
| Hành động tiếp theo | Điều tra cơ chế cập nhật và bổ sung kiểm thử hồi quy nếu có lỗi |

Kết quả mong đợi trong ví dụ cần được xác nhận theo thiết kế sản phẩm. Một hệ thống có thể chọn từ chối cập nhật xung đột hoặc áp dụng chính sách ghi đè có kiểm soát; điều quan trọng là hành vi phải rõ ràng và không làm mất dữ liệu ngoài ý muốn.

## Kết luận

Kiểm thử dựa trên kinh nghiệm giúp nhóm tận dụng hiểu biết về nghiệp vụ, công nghệ, người dùng và lịch sử lỗi để phát hiện những tình huống mà đặc tả hoặc bộ kiểm thử định sẵn có thể bỏ sót. Dự đoán lỗi biến kinh nghiệm thành giả thuyết có thể kiểm chứng: xác định điều gì có thể sai, tạo điều kiện để thử, quan sát bằng chứng và mở rộng khi có dấu hiệu liên quan.

Để cách tiếp cận này tạo giá trị bền vững, nhóm cần ưu tiên giả thuyết theo rủi ro, ghi nhận kết quả có thể tái hiện, chia sẻ tri thức và chuyển những phát hiện quan trọng thành kiểm thử hồi quy phù hợp. Khi kết hợp với kiểm thử dựa trên đặc tả, cấu trúc và kiểm thử thăm dò, kinh nghiệm trở thành nguồn bổ sung mạnh mẽ giúp chiến lược kiểm thử bao quát thực tế hơn.
