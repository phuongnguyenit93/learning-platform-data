# Thuộc tính gốc, thuộc tính suy ra và kết quả tổng hợp

Khi mô hình hóa dữ liệu, cần phân biệt thông tin được ghi nhận trực tiếp với thông tin được tính từ dữ liệu khác và thông tin tóm tắt từ nhiều bản ghi. Ba nhóm này có liên hệ chặt chẽ nhưng có nguồn gốc, quy tắc cập nhật và cách kiểm chứng khác nhau. Nếu nhầm lẫn, hệ thống có thể lưu trùng dữ liệu, tính sai số liệu, làm mất dấu vết nguồn hoặc hiển thị kết quả không nhất quán giữa các màn hình và báo cáo.

Trong phạm vi **DATABASE_DATA_MODELING**, việc phân loại thuộc tính là một phần của quá trình chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng. Người thiết kế cần xác định mỗi giá trị đến từ đâu, ai chịu trách nhiệm, được tính theo quy tắc nào, có thay đổi theo thời gian không và có cần lưu lại kết quả tại thời điểm nghiệp vụ xảy ra không. Những quyết định này ảnh hưởng đến thực thể, quan hệ, ràng buộc, chuẩn hóa và cả lựa chọn cấu trúc lưu trữ quan hệ, document, đồ thị hay phân tích.

Sau bài học, người học có thể:

- Phân biệt thuộc tính gốc, thuộc tính suy ra và kết quả tổng hợp.
- Xác định nguồn sự thật, chủ sở hữu, thời điểm ghi nhận và quy tắc cập nhật của từng thuộc tính.
- Mô tả công thức suy ra và xác định dữ liệu đầu vào cần thiết để kiểm chứng kết quả.
- Phân biệt phép tính trên một đối tượng với phép tổng hợp trên một tập bản ghi.
- Xử lý giá trị thiếu, đơn vị đo, tiền tệ, làm tròn và dữ liệu thay đổi theo thời gian.
- Quyết định khi nào nên tính khi truy vấn, lưu kết quả, dùng snapshot hoặc xây dựng dữ liệu tổng hợp.
- Phát hiện rủi ro lưu trùng, cập nhật lệch và sai lệch giữa dữ liệu chi tiết với số liệu tổng hợp.

## 1. Ba nhóm thông tin trong mô hình dữ liệu

### 1.1. Thuộc tính gốc

**Thuộc tính gốc (base/source attribute)** là giá trị được ghi nhận trực tiếp từ một sự kiện, người dùng, thiết bị, tài liệu hoặc hệ thống có thẩm quyền. Giá trị của nó không được tính ra từ các thuộc tính nghiệp vụ khác trong mô hình đang xét.

Ví dụ:

- `order_placed_at`: thời điểm đơn hàng được tiếp nhận.
- `quantity`: số lượng sản phẩm khách đặt.
- `unit_price_at_order`: đơn giá được chốt cho dòng đơn hàng.
- `payment_received_at`: thời điểm hệ thống nhận xác nhận thanh toán.
- `birth_date`: ngày sinh do người dùng cung cấp hoặc được xác minh từ nguồn có thẩm quyền.
- `temperature_celsius`: số đo trực tiếp từ cảm biến.

Thuộc tính gốc có thể được nhập thủ công, nhận qua API, lấy từ thiết bị hoặc được hệ thống cấp theo quy tắc riêng. Ví dụ, mã đơn hàng do hệ thống sinh không phải kết quả tổng hợp từ các dòng đơn hàng; nó là giá trị định danh được cấp tại thời điểm tạo. “Gốc” nói về nguồn gốc của giá trị trong mô hình, không có nghĩa giá trị luôn bất biến, luôn đúng hoặc nhất thiết do con người nhập.

Một thuộc tính gốc vẫn có thể bị sửa. Số điện thoại liên hệ có thể đổi; địa chỉ hiện tại có thể cập nhật; số lượng đặt có thể điều chỉnh trước một mốc nghiệp vụ. Khi cho phép sửa, cần xác định ai được sửa, điều kiện, thời điểm hiệu lực và có cần lưu giá trị trước đó không.

### 1.2. Thuộc tính suy ra

**Thuộc tính suy ra (derived attribute)** là giá trị được xác định bằng một công thức hoặc quy tắc từ một hay nhiều giá trị khác. Nó không cần được nhập như một sự kiện độc lập, vì có thể tái tính từ dữ liệu nguồn và quy tắc đã xác định.

Ví dụ:

- `line_subtotal = quantity × unit_price_at_order`.
- `age = ngày hiện tại − birth_date` theo quy tắc tính tuổi.
- `duration_minutes = end_time − start_time`.
- `is_overdue = due_date < thời điểm kiểm tra` và khoản phải trả chưa được thanh toán đủ.
- `full_name = given_name + family_name` theo quy tắc định dạng tên.

Thuộc tính suy ra phụ thuộc vào dữ liệu đầu vào và quy tắc. Nếu một đầu vào thay đổi, kết quả có thể thay đổi. Nếu quy tắc thay đổi, cùng một tập đầu vào có thể cho kết quả khác. Vì vậy cần ghi công thức, phạm vi áp dụng, phiên bản quy tắc và thời điểm tính nếu kết quả được lưu.

Không phải mọi giá trị trông như kết quả tính toán đều nên suy ra. Ví dụ, giá bán thực tế được chốt trên đơn có thể bắt nguồn từ bảng giá, khuyến mãi, thuế và quyết định của người bán. Sau khi giao dịch xác nhận, giá đó là một sự kiện đã xảy ra và cần được giữ như dữ liệu gốc của giao dịch. Tính lại từ bảng giá hiện tại có thể làm sai lịch sử.

### 1.3. Kết quả tổng hợp

**Kết quả tổng hợp (aggregate result)** là giá trị được tính từ nhiều bản ghi hoặc nhiều đối tượng theo một phạm vi và phép tổng hợp xác định. Nó thường trả lời câu hỏi về tổng số, số lượng, trung bình, giá trị nhỏ nhất/lớn nhất hoặc một chỉ số theo nhóm.

Ví dụ:

- Tổng doanh thu theo ngày: tổng giá trị các giao dịch đủ điều kiện trong ngày.
- Số đơn hàng theo trạng thái: đếm các đơn thuộc từng trạng thái tại một thời điểm.
- Tổng số lượng đã giao theo sản phẩm: cộng số lượng giao của các dòng giao hàng.
- Điểm trung bình của một khóa học: tính từ các điểm hợp lệ theo quy tắc đánh giá.
- Số dư tồn kho: lượng nhập trừ lượng xuất, điều chỉnh và các biến động được tính đến.

Kết quả tổng hợp là một dạng giá trị được suy ra, nhưng có đặc điểm quan trọng: nó phụ thuộc vào một tập bản ghi, điều kiện lọc, cách nhóm và thời điểm chốt dữ liệu. Cùng một phép `SUM` có thể cho kết quả khác nếu phạm vi thời gian, trạng thái giao dịch hoặc quy tắc loại trừ thay đổi.

### 1.4. So sánh nhanh

| Tiêu chí | Thuộc tính gốc | Thuộc tính suy ra | Kết quả tổng hợp |
|---|---|---|---|
| Nguồn | Ghi nhận trực tiếp từ nguồn có thẩm quyền | Công thức/quy tắc từ dữ liệu đầu vào | Tập bản ghi theo phạm vi và nhóm |
| Phạm vi tính | Một giá trị hoặc một sự kiện | Thường một đối tượng hoặc một quan hệ | Nhiều bản ghi hoặc nhiều đối tượng |
| Ví dụ | Số lượng đặt, thời điểm thanh toán | Thành tiền dòng hàng | Doanh thu theo tháng |
| Khi đầu vào đổi | Giá trị gốc được cập nhật theo quy trình nghiệp vụ | Có thể phải tính lại | Có thể phải tái tổng hợp |
| Cần lưu công thức? | Cần định nghĩa nguồn và quy tắc ghi nhận | Có | Có, gồm điều kiện lọc và nhóm |
| Rủi ro chính | Sai nguồn, nhập sai, mất lịch sử | Công thức không nhất quán hoặc lỗi thời | Phạm vi tổng hợp sai, dữ liệu trễ hoặc đếm trùng |

## 2. Xác định nguồn sự thật cho thuộc tính gốc

Một thuộc tính chỉ có ý nghĩa khi biết nó mô tả điều gì và ai có quyền xác nhận giá trị. Cùng một khái niệm có thể xuất hiện ở nhiều hệ thống, nhưng không phải hệ thống nào cũng là nguồn chính thức.

Ví dụ, tên khách hàng có thể xuất hiện trong CRM, hệ thống bán hàng, hóa đơn và nền tảng hỗ trợ. Cần xác định hệ thống nào quản lý hồ sơ khách, hệ thống nào chỉ lưu bản chụp phục vụ giao dịch và hệ thống nào nhận dữ liệu đồng bộ. Nếu không làm rõ, các nhóm có thể cập nhật cùng một thuộc tính ở nhiều nơi và tạo ra các giá trị mâu thuẫn.

### 2.1. Các câu hỏi để mô tả một thuộc tính gốc

- Giá trị được tạo ra từ hành động hoặc sự kiện nào?
- Ai hoặc hệ thống nào cung cấp giá trị?
- Hệ thống nào là nguồn có thẩm quyền?
- Giá trị được ghi nhận vào thời điểm nào: lúc sự kiện xảy ra hay lúc hệ thống nhận dữ liệu?
- Có cho phép sửa không? Ai được sửa và trong điều kiện nào?
- Khi sửa, có cần lưu giá trị cũ, lý do và người thực hiện không?
- Giá trị có duy nhất hoặc phải tham chiếu đến danh mục nào không?
- Nếu nguồn không gửi giá trị, đó là không áp dụng, chưa biết hay lỗi truyền dữ liệu?

### 2.2. Ví dụ hồ sơ thuộc tính

| Thuộc tính | Nguồn gốc | Chủ sở hữu | Quy tắc cập nhật |
|---|---|---|---|
| `order_placed_at` | Sự kiện tiếp nhận đơn | Dịch vụ đơn hàng | Ghi khi đơn được tạo theo định nghĩa nghiệp vụ; không thay đổi khi chỉnh sửa đơn. |
| `quantity_ordered` | Khách đặt hàng hoặc nhân viên nhập | Dịch vụ đơn hàng | Có thể sửa trước mốc chốt; sau đó điều chỉnh bằng nghiệp vụ có dấu vết. |
| `unit_price_at_order` | Giá và chính sách tại thời điểm xác nhận | Dịch vụ bán hàng | Chốt theo giao dịch; không tự tính lại theo bảng giá hiện tại. |
| `payment_confirmed_at` | Xác nhận từ cổng thanh toán hoặc quầy thu ngân | Dịch vụ thanh toán | Ghi theo nguồn xác nhận; có thể phân biệt thời gian đối tác và thời gian nhận. |
| `customer_current_address` | Hồ sơ khách hàng | CRM hoặc hệ thống hồ sơ được chỉ định | Cập nhật theo quy trình quản lý hồ sơ. |

Các tên hệ thống trong bảng là ví dụ. Trong dự án thực tế, cần xác định đúng nguồn theo kiến trúc và quyền sở hữu dữ liệu của tổ chức.

### 2.3. Không đồng nhất “gốc” với “đáng tin cậy”

Một giá trị được nhập trực tiếp vẫn có thể sai. Ví dụ, nhân viên nhập nhầm số lượng, cảm biến đo sai hoặc hệ thống ngoài gửi dữ liệu trùng. Vì vậy thuộc tính gốc vẫn cần kiểm tra định dạng, miền giá trị, quyền cập nhật, xác thực nguồn và cơ chế xử lý sai lệch.

Hãy phân biệt ba câu hỏi:

1. **Nguồn gốc:** giá trị đến từ đâu?
2. **Tính hợp lệ:** giá trị có thỏa mãn quy tắc không?
3. **Tính có thẩm quyền:** nguồn đó có quyền quyết định giá trị chính thức không?

Một dữ liệu có thể đến từ nguồn gốc rõ ràng nhưng chưa hợp lệ; hoặc hợp lệ về định dạng nhưng không phải nguồn chính thức.

## 3. Xác định thuộc tính suy ra và mô tả công thức

### 3.1. Bắt đầu từ câu hỏi nghiệp vụ

Đừng bắt đầu bằng việc thấy một phép tính trong báo cáo rồi thêm cột tương ứng. Hãy xác định người dùng cần biết điều gì và kết quả được sử dụng cho quyết định nào.

Ví dụ, câu “Đơn hàng còn phải thu bao nhiêu?” cần xác định:

- Tổng số tiền phải trả được xác định từ những thành phần nào?
- Khoản giảm giá và thuế được tính theo quy tắc nào?
- Các khoản thanh toán thành công nào được trừ?
- Khoản hoàn tiền có làm thay đổi số đã thu hay được theo dõi riêng?
- Có tính phí vận chuyển, phí dịch vụ hoặc điều chỉnh thủ công không?
- Kết quả được xem tại thời điểm hiện tại hay tại thời điểm chốt đơn?

Chỉ sau khi làm rõ ý nghĩa, mới xác định công thức. Cùng tên “còn phải thu” có thể được hiểu là số tiền phải thanh toán trước khi giao, số tiền chưa thu tại thời điểm hiện tại hoặc số tiền còn lại sau hoàn tiền.

### 3.2. Mô tả công thức có thể kiểm chứng

Một định nghĩa tốt nên nêu:

- Tên và ý nghĩa nghiệp vụ của kết quả.
- Các thuộc tính đầu vào và nguồn của chúng.
- Công thức hoặc quy tắc tính.
- Đơn vị đo, tiền tệ và quy tắc làm tròn.
- Cách xử lý giá trị thiếu hoặc không hợp lệ.
- Điều kiện áp dụng và trường hợp ngoại lệ.
- Thời điểm tính hoặc thời điểm kết quả có hiệu lực.
- Phiên bản quy tắc nếu công thức có thể thay đổi.

Ví dụ:

```text
Tên: line_net_amount
Ý nghĩa: Số tiền thuần của một dòng đơn hàng tại thời điểm chốt giao dịch.
Đầu vào: quantity_ordered, unit_price_at_order, line_discount_amount.
Công thức: quantity_ordered * unit_price_at_order - line_discount_amount.
Đơn vị: tiền tệ của đơn hàng.
Làm tròn: theo quy tắc tiền tệ và chính sách bán hàng đã xác nhận.
Thời điểm: tính khi dòng đơn được chốt; lưu kết quả giao dịch nếu cần bảo toàn lịch sử.
```

Không để công thức chỉ tồn tại trong mã nguồn hoặc trong suy nghĩ của người phát triển. Khi quy tắc ảnh hưởng đến tiền, quyền lợi, tồn kho hoặc báo cáo, cần có định nghĩa nghiệp vụ được người sở hữu xác nhận.

### 3.3. Phân biệt thuộc tính suy ra ổn định và phụ thuộc thời điểm

Một số thuộc tính suy ra chỉ phụ thuộc dữ liệu đã chốt, ví dụ thành tiền của dòng đơn từ số lượng và đơn giá đã xác nhận. Một số thuộc tính phụ thuộc thời điểm truy vấn, ví dụ tuổi hiện tại, số ngày quá hạn hoặc trạng thái còn hiệu lực.

| Loại | Ví dụ | Điều cần lưu ý |
|---|---|---|
| Suy ra từ dữ liệu giao dịch đã chốt | Thành tiền dòng hàng | Kết quả phải giữ đúng ý nghĩa tại thời điểm giao dịch. |
| Suy ra từ dữ liệu hiện tại | Họ tên hiển thị ghép từ tên và họ | Thay đổi đầu vào làm thay đổi kết quả hiển thị. |
| Suy ra theo thời điểm | Tuổi, số ngày còn lại, hợp đồng đang hiệu lực | Cùng dữ liệu gốc có thể cho kết quả khác theo ngày kiểm tra. |
| Suy ra theo quy tắc phiên bản | Phân loại khách hàng theo ngưỡng chi tiêu | Cần biết ngưỡng nào được áp dụng ở thời điểm nào. |

Ví dụ, tuổi không nên được lưu như một con số cố định nếu mục tiêu là hiển thị tuổi hiện tại. Có thể lưu ngày sinh là thuộc tính gốc và tính tuổi tại thời điểm cần hiển thị. Nếu nghiệp vụ cần tuổi của một người tại ngày ký hợp đồng, kết quả đó phải gắn với ngày ký và quy tắc tính tại thời điểm đó.

## 4. Kết quả tổng hợp: phép tính trên nhiều bản ghi

### 4.1. Phân biệt tính trên một đối tượng và tổng hợp một tập

`line_net_amount` tính trên một dòng đơn hàng. `order_total` có thể là tổng các dòng của một đơn. `monthly_revenue` là tổng hợp doanh thu của nhiều giao dịch trong một tháng. Ba kết quả có thể cùng là số tiền nhưng phạm vi dữ liệu khác nhau.

| Kết quả | Phạm vi | Phép tính minh họa |
|---|---|---|
| Thành tiền dòng | Một dòng đơn hàng | Số lượng × đơn giá − giảm giá dòng |
| Tổng tiền hàng đơn | Các dòng của một đơn | Tổng thành tiền dòng |
| Số đơn trong ngày | Các đơn đủ điều kiện trong ngày | Đếm đơn theo ngày nghiệp vụ |
| Doanh thu theo tháng | Các giao dịch đủ điều kiện trong tháng | Tổng giá trị doanh thu theo định nghĩa |
| Tỷ lệ hoàn tiền | Nhóm giao dịch trong phạm vi xác định | Tổng hoàn tiền / tổng tiền thu đủ điều kiện |

Kết quả tổng hợp luôn cần một phạm vi rõ. “Doanh thu tháng 5” phải nêu tháng theo múi giờ nào, ngày nào được tính, trạng thái nào được đưa vào, có trừ hoàn tiền hay không và doanh thu ghi nhận theo ngày đặt hàng, ngày giao hàng hay ngày thanh toán.

### 4.2. Các phép tổng hợp phổ biến

| Phép tổng hợp | Ý nghĩa | Ví dụ | Lưu ý |
|---|---|---|---|
| `COUNT` | Đếm số bản ghi hoặc số giá trị | Số đơn, số khách có email | Phân biệt đếm tất cả với đếm giá trị không rỗng. |
| `SUM` | Cộng các giá trị | Tổng số lượng đã giao | Cần xác định điều kiện lọc và đơn vị. |
| `AVG` | Tính trung bình | Điểm trung bình | Trung bình đơn giản khác trung bình có trọng số. |
| `MIN` / `MAX` | Giá trị nhỏ nhất/lớn nhất | Ngày giao sớm nhất | Xác định có bỏ qua giá trị thiếu không. |
| `COUNT DISTINCT` | Đếm đối tượng khác nhau | Số khách duy nhất | Cần định nghĩa định danh khách và phạm vi. |
| Tỷ lệ | So sánh hai đại lượng | Tỷ lệ hủy trên tổng đơn | Tử số và mẫu số phải cùng phạm vi phù hợp. |
| Phân vị | Mốc phân bố | Thời gian xử lý ở phân vị 95 | Không đồng nghĩa với trung bình. |

### 4.3. Nhóm dữ liệu trước khi tổng hợp

Kết quả tổng hợp thường được nhóm theo một hoặc nhiều chiều như ngày, sản phẩm, chi nhánh, kênh bán hoặc trạng thái. Mỗi chiều cần định nghĩa rõ:

- Giá trị dùng để nhóm lấy từ đâu?
- Nhóm theo thời điểm tạo, thời điểm ghi nhận hay thời điểm hoàn tất?
- Danh mục có thể đổi tên hoặc phân cấp không?
- Một bản ghi có thể thuộc nhiều nhóm không?
- Các bản ghi không có giá trị chiều được xếp vào nhóm nào?

Ví dụ, doanh thu theo chi nhánh có thể được nhóm theo chi nhánh bán, chi nhánh xuất kho hoặc chi nhánh ghi nhận doanh thu. Nếu đơn được bán tại cửa hàng A nhưng giao từ kho B, cần xác định chiều nào phù hợp với câu hỏi báo cáo.

### 4.4. Kết quả tổng hợp không phải lúc nào cũng là tổng số học đơn giản

Một số chỉ số cần công thức đặc biệt:

- **Tỷ lệ chuyển đổi:** số đơn hoàn tất chia cho số lượt hoặc phiên đủ điều kiện, không phải trung bình tỷ lệ từng ngày nếu quy tắc yêu cầu tỷ lệ toàn kỳ.
- **Giá trị đơn trung bình:** tổng doanh thu chia cho số đơn thuộc phạm vi, không phải tổng giá trị trung bình của mọi dòng hàng.
- **Tồn kho:** số lượng nhập trừ số lượng xuất, cộng/trừ điều chỉnh và các trạng thái giữ hàng theo quy tắc.
- **Điểm trung bình:** có thể cần trọng số theo số tín chỉ, số câu hoặc hệ số đánh giá.

Hãy viết công thức ở dạng tử số, mẫu số, điều kiện lọc và phạm vi. Tên chỉ số không thay thế định nghĩa.

## 5. Ví dụ xuyên suốt: đơn hàng, thanh toán và giao hàng

Giả sử một đơn hàng có nhiều dòng. Mỗi dòng lưu số lượng, đơn giá được chốt và giảm giá dòng. Đơn có thể có phí vận chuyển, thuế và giảm giá toàn đơn. Khách có thể thanh toán nhiều lần; đơn có thể giao thành nhiều đợt và hoàn tiền một phần.

### 5.1. Phân loại thuộc tính

| Thuộc tính | Nhóm | Lý do |
|---|---|---|
| `order_placed_at` | Gốc | Ghi nhận thời điểm tiếp nhận đơn. |
| `quantity_ordered` | Gốc | Số lượng khách yêu cầu tại thời điểm ghi nhận. |
| `unit_price_at_order` | Gốc của giao dịch | Giá được chốt từ chính sách tại thời điểm xác nhận. |
| `line_discount_amount` | Gốc hoặc kết quả được chốt | Có thể do chương trình khuyến mãi quyết định; cần lưu số đã áp dụng cho giao dịch. |
| `line_net_amount` | Suy ra | Tính từ số lượng, đơn giá và giảm giá dòng. |
| `order_merchandise_total` | Tổng hợp | Tổng thành tiền của các dòng hàng trong đơn. |
| `payment_received_total` | Tổng hợp | Tổng các giao dịch thu tiền thành công thuộc phạm vi. |
| `refund_total` | Tổng hợp | Tổng các giao dịch hoàn tiền thành công. |
| `outstanding_amount` | Suy ra/tổng hợp | Tính theo quy tắc phải thu trừ khoản đã thu và điều chỉnh liên quan. |
| `shipped_quantity` | Tổng hợp | Tổng số lượng được ghi nhận trong các lần giao hợp lệ. |
| `is_fully_shipped` | Suy ra | So sánh số lượng đã giao với số lượng cần giao theo quy tắc. |

Một số trường hợp phụ thuộc thiết kế và chính sách. Ví dụ, `line_discount_amount` có thể được tính từ tỷ lệ khuyến mãi nhưng giá trị thực tế được chốt trong giao dịch nên phải giữ như dữ liệu đã áp dụng. `outstanding_amount` có thể thay đổi theo trạng thái thanh toán và hoàn tiền; cần ghi rõ nó là số dư hiện tại hay số dư tại thời điểm chốt.

### 5.2. Công thức và quy tắc minh họa

```text
line_net_amount
    = quantity_ordered * unit_price_at_order
      - line_discount_amount

order_merchandise_total
    = SUM(line_net_amount của các dòng thuộc đơn)

payment_received_total
    = SUM(amount của các giao dịch thu tiền thành công)

refund_total
    = SUM(amount của các giao dịch hoàn tiền thành công)

net_cash_received
    = payment_received_total - refund_total
```

Không nên tự đồng nhất `order_merchandise_total`, `net_cash_received` và `outstanding_amount`. Tổng tiền hàng có thể chưa bao gồm thuế hoặc vận chuyển; tiền đã thu có thể bao gồm khoản đặt cọc; số dư phải thu có thể cần xử lý chiết khấu, phí, điều chỉnh và nghĩa vụ hoàn tiền. Mỗi đại lượng phải có định nghĩa nghiệp vụ riêng.

### 5.3. SQL minh họa cho thuộc tính suy ra và tổng hợp

Tính thành tiền từng dòng:

```sql
SELECT
    order_id,
    order_line_id,
    quantity_ordered,
    unit_price_at_order,
    line_discount_amount,
    quantity_ordered * unit_price_at_order
        - line_discount_amount AS line_net_amount
FROM order_lines;
```

Tính tổng tiền hàng theo đơn:

```sql
SELECT
    order_id,
    SUM(quantity_ordered * unit_price_at_order
        - line_discount_amount) AS order_merchandise_total
FROM order_lines
GROUP BY order_id;
```

Tính số lượng giao theo dòng đơn hàng:

```sql
SELECT
    order_line_id,
    SUM(shipped_quantity) AS shipped_quantity
FROM shipment_lines
WHERE shipment_status IN ('DISPATCHED', 'DELIVERED')
GROUP BY order_line_id;
```

Các truy vấn chỉ là ví dụ. Trong hệ thống thực tế cần xác định rõ trạng thái nào được tính, cách xử lý giao thất bại hoặc bị trả lại, và liệu `DISPATCHED` có được tính là đã giao theo định nghĩa nghiệp vụ hay không. Không sao chép bộ lọc minh họa nếu quy tắc của tổ chức khác.

### 5.4. Tình huống thay đổi và ảnh hưởng đến kết quả

Nếu số lượng đơn được điều chỉnh trước khi xác nhận, `line_net_amount` và tổng tiền hàng có thể cần tính lại. Nếu đơn đã xác nhận, thay đổi số lượng có thể phải được ghi nhận bằng điều chỉnh hoặc hủy một phần để giữ lịch sử. Khi một lần giao bị trả lại, tổng số lượng đã giao ròng có thể khác tổng số lượng từng được bàn giao. Khi hoàn tiền thành công, tổng tiền hoàn tăng nhưng giá trị thanh toán gốc không bị ghi đè.

Các tình huống này cho thấy thuộc tính gốc, thuộc tính suy ra và tổng hợp cần được liên kết bằng quy tắc thời gian. Không thể chỉ nhìn vào công thức toán học mà bỏ qua sự kiện nghiệp vụ.

## 6. Giá trị thiếu, số 0 và tính hợp lệ của phép tính

### 6.1. Không đồng nhất NULL với 0

`NULL` thường biểu thị chưa biết, chưa được cung cấp hoặc không áp dụng tùy ngữ cảnh. Số `0` là một giá trị cụ thể. Ví dụ:

- `discount_amount = 0`: đã xác định không có giảm giá.
- `discount_amount = NULL`: chưa biết hoặc chưa tính giảm giá.
- `shipped_quantity = 0`: đã xác định chưa có số lượng nào được giao.
- `shipped_quantity = NULL`: dữ liệu giao hàng chưa được ghi nhận hoặc không áp dụng.

Nếu gộp hai trường hợp, báo cáo có thể hiểu nhầm dữ liệu chưa đầy đủ là kết quả bằng không. Cần định nghĩa ngữ nghĩa của giá trị thiếu ở từng thuộc tính.

### 6.2. Xác định cách xử lý khi thiếu đầu vào

Với mỗi công thức, hãy hỏi:

- Nếu thiếu một đầu vào, kết quả là chưa xác định, không áp dụng hay có thể tính từ dữ liệu còn lại?
- Có được thay giá trị thiếu bằng 0 không? Căn cứ nghiệp vụ là gì?
- Nếu mẫu số bằng 0, chỉ số tỷ lệ hiển thị thế nào?
- Bản ghi không đủ điều kiện được loại khỏi tập tổng hợp hay được tính vào nhóm riêng?
- Có cần báo chất lượng dữ liệu thay vì trả một con số có vẻ hợp lệ không?

Ví dụ, tỷ lệ hoàn tiền khi không có giao dịch thu tiền trong kỳ không nên tự động hiển thị 0% nếu mẫu số bằng 0. Kết quả có thể là “không xác định” hoặc “không áp dụng” tùy mục tiêu báo cáo.

### 6.3. Đơn vị đo, tiền tệ và độ chính xác

Không cộng các giá trị khác đơn vị hoặc khác tiền tệ nếu chưa có quy tắc quy đổi. Tổng 10 kg và 5 g cần quy đổi về cùng đơn vị. Tổng 100 USD và 100 VND không có ý nghĩa nếu không xác định tỷ giá và thời điểm áp dụng.

Với tiền tệ, cần làm rõ:

- Đơn vị tiền của giao dịch và đơn vị tiền báo cáo.
- Số chữ số thập phân được phép.
- Thời điểm và nguồn tỷ giá nếu quy đổi.
- Làm tròn ở cấp dòng, cấp hóa đơn hay cấp tổng.
- Chênh lệch do làm tròn được xử lý thế nào.

Ví dụ, làm tròn từng dòng trước khi cộng có thể cho kết quả khác với cộng số chính xác rồi làm tròn một lần. Quy tắc phải nhất quán và được xác nhận.

## 7. Thời gian, phiên bản quy tắc và tính tái lập

### 7.1. Kết quả suy ra phụ thuộc vào thời điểm nào?

Một thuộc tính suy ra có thể phụ thuộc vào:

- Thời điểm sự kiện gốc xảy ra.
- Thời điểm hệ thống ghi nhận sự kiện.
- Thời điểm truy vấn hoặc hiển thị.
- Thời điểm chốt kỳ báo cáo.
- Phiên bản quy tắc tính được áp dụng.

Ví dụ, trạng thái “hợp đồng đang hiệu lực” được tính từ ngày bắt đầu, ngày kết thúc và ngày kiểm tra. Cùng một hợp đồng có thể đang hiệu lực hôm nay nhưng không còn hiệu lực vào tháng sau. Nếu báo cáo lịch sử cần biết hợp đồng có hiệu lực tại ngày 15/06, phải tính theo ngày đó chứ không dùng trạng thái hiện tại.

### 7.2. Quy tắc thay đổi theo thời gian

Ngưỡng phân loại khách hàng, chính sách giảm giá, cách tính điểm hoặc quy tắc thuế có thể thay đổi. Nếu chỉ lưu dữ liệu đầu vào mà không biết phiên bản quy tắc, việc tái tính lịch sử có thể cho kết quả khác với kết quả đã được chấp nhận tại thời điểm đó.

Hãy xác định:

- Quy tắc có ngày hiệu lực không?
- Có cần lưu mã hoặc phiên bản quy tắc không?
- Kết quả cũ được giữ nguyên hay được tính lại khi quy tắc đổi?
- Báo cáo lịch sử cần phản ánh quy tắc lúc phát sinh hay quy tắc hiện tại?
- Ai phê duyệt thay đổi công thức?

Một giải pháp thường gặp là lưu dữ liệu gốc, phiên bản quy tắc và kết quả đã chốt cho giao dịch quan trọng. Với chỉ số phân tích có thể tái tạo, hệ thống có thể tính lại từ dữ liệu chi tiết nhưng cần biết phiên bản logic và phạm vi dữ liệu.

### 7.3. Snapshot và dữ liệu hiện tại

**Snapshot** là bản ghi nhận giá trị tại một thời điểm cụ thể. Snapshot hữu ích khi nghiệp vụ cần bảo toàn điều đã được chấp nhận, ví dụ giá bán, địa chỉ giao hàng, thuế suất hoặc điều khoản hợp đồng tại thời điểm ký.

Snapshot không có nghĩa sao chép mọi thuộc tính của đối tượng vào mọi giao dịch. Chỉ lưu những giá trị cần thiết để giải thích, đối soát hoặc thực hiện nghĩa vụ. Hãy xác định mục đích và nguồn của từng giá trị snapshot.

| Dữ liệu | Giá trị hiện tại | Snapshot giao dịch |
|---|---|---|
| Địa chỉ khách | Địa chỉ đang dùng trong hồ sơ khách | Địa chỉ được xác nhận cho đơn tại thời điểm đặt |
| Giá sản phẩm | Giá đang niêm yết | Giá đã chốt trong dòng đơn hàng |
| Thuế suất | Thuế suất đang áp dụng | Thuế suất dùng để tính giao dịch đã phát sinh |
| Tên sản phẩm | Tên hiển thị hiện tại | Tên hoặc mô tả sản phẩm trên chứng từ nếu cần lưu |

## 8. Quyết định tính khi truy vấn hay lưu kết quả

Một thuộc tính suy ra có thể được tính khi cần hoặc được lưu sẵn. Không có lựa chọn đúng cho mọi trường hợp. Quyết định phụ thuộc vào chi phí tính toán, tần suất truy vấn, yêu cầu độ mới, tính tái lập và mức độ quan trọng của kết quả.

### 8.1. Tính khi truy vấn (on-demand)

Hệ thống tính giá trị từ dữ liệu nguồn mỗi khi đọc.

Ưu điểm:

- Tránh lưu bản sao có thể lỗi thời.
- Công thức và dữ liệu nguồn là nơi xác định kết quả.
- Khi dữ liệu nguồn thay đổi, truy vấn sau đó phản ánh giá trị mới theo quy tắc hiện hành.

Hạn chế:

- Truy vấn có thể tốn chi phí khi tập dữ liệu lớn.
- Công thức phức tạp có thể bị lặp ở nhiều truy vấn.
- Kết quả giữa các lần đọc có thể khác nếu dữ liệu nguồn thay đổi.

Phù hợp với kết quả tính nhanh, ít được dùng hoặc cần luôn phản ánh dữ liệu hiện tại.

### 8.2. Lưu kết quả đã tính (stored derived value)

Hệ thống lưu kết quả cùng đối tượng hoặc giao dịch.

Ưu điểm:

- Đọc nhanh và dễ hiển thị.
- Có thể bảo toàn kết quả đã chốt tại thời điểm nghiệp vụ.
- Thuận tiện cho chứng từ hoặc quy trình cần kết quả ổn định.

Hạn chế:

- Có nguy cơ lệch với dữ liệu đầu vào nếu cập nhật không đồng bộ.
- Tăng dữ liệu trùng lặp và quy tắc bảo trì.
- Cần xác định khi nào tính lại, khi nào không được tính lại.

Phù hợp với giá trị giao dịch đã chốt hoặc kết quả được sử dụng như một phần bằng chứng nghiệp vụ.

### 8.3. Lưu kết quả tổng hợp hoặc materialized view

Kết quả tổng hợp có thể được tính trước và lưu thành bảng tổng hợp, materialized view hoặc dữ liệu phục vụ phân tích. Điều này giảm chi phí truy vấn khi số lượng bản ghi lớn, nhưng cần quản lý độ trễ và quá trình làm mới.

Hãy xác định:

- Làm mới theo từng sự kiện, theo lịch hay theo đợt?
- Chấp nhận dữ liệu trễ tối đa bao lâu?
- Khi sự kiện đến muộn hoặc bị sửa, có tái tính kỳ cũ không?
- Có thể đối chiếu số liệu tổng hợp với dữ liệu chi tiết không?
- Ai chịu trách nhiệm khi số liệu tổng hợp lệch?

### 8.4. Bảng lựa chọn

| Tiêu chí | Tính khi truy vấn | Lưu kết quả suy ra | Lưu kết quả tổng hợp |
|---|---|---|---|
| Độ mới | Thường mới theo snapshot truy vấn | Phụ thuộc cơ chế cập nhật | Phụ thuộc lịch làm mới |
| Tốc độ đọc | Có thể chậm nếu tính phức tạp | Nhanh | Nhanh cho truy vấn tổng hợp đã định nghĩa |
| Chi phí ghi | Thấp hơn | Cao hơn do phải cập nhật kết quả | Có chi phí đồng bộ/làm mới |
| Rủi ro lệch | Thấp nếu nguồn và công thức nhất quán | Có nếu không cập nhật đúng | Có nếu dữ liệu tổng hợp chưa làm mới hoặc tính sai phạm vi |
| Phù hợp | Kết quả linh hoạt, ít dùng | Giá trị đã chốt, cần đọc nhanh | Báo cáo lớn, dashboard, phân tích theo chiều |

Không nên lưu một thuộc tính suy ra chỉ vì việc thêm cột dễ dàng. Hãy nêu lý do nghiệp vụ hoặc hiệu năng, quy tắc đồng bộ và cách kiểm chứng trước khi lưu.

## 9. Liên hệ với chuẩn hóa và các mô hình lưu trữ

### 9.1. Mô hình quan hệ

Trong mô hình quan hệ, thuộc tính gốc thường được lưu tại bảng sở hữu dữ liệu. Thuộc tính suy ra có thể được tính bằng truy vấn hoặc lưu có chủ đích. Kết quả tổng hợp có thể được tạo qua `GROUP BY`, view, materialized view hoặc bảng tổng hợp.

Chuẩn hóa giúp giảm lưu lặp các dữ liệu có thể xác định từ quan hệ khác. Ví dụ, không nên lưu tên khách hàng lặp trên mọi dòng đơn hàng nếu chỉ cần tham chiếu hồ sơ khách cho thông tin hiện tại. Tuy nhiên, giá trị lịch sử đã chốt như tên hoặc địa chỉ trên chứng từ có thể cần snapshot vì ý nghĩa nghiệp vụ khác với hồ sơ hiện tại.

Điểm quan trọng là phân biệt dữ liệu lặp không cần thiết với dữ liệu snapshot có chủ đích. Cả hai đều có thể trông như bản sao, nhưng mục đích và quy tắc cập nhật khác nhau.

### 9.2. Mô hình document

Document có thể lưu một đối tượng cùng các thành phần con trong một tài liệu. Ví dụ, một đơn hàng có mảng dòng hàng và giá trị tổng đã chốt. Cách này thuận tiện khi thường đọc toàn bộ đơn. Tuy nhiên, nếu tổng tiền là giá trị suy ra từ các dòng, cần xác định rõ khi thêm, sửa hoặc xóa dòng thì tổng được cập nhật thế nào.

Không nhúng kết quả tổng hợp vào document mà thiếu nguồn và quy tắc làm mới. Nếu các dòng hàng có vòng đời hoặc truy vấn độc lập, cần cân nhắc việc tách collection hoặc lưu quan hệ tham chiếu.

### 9.3. Mô hình đồ thị

Trong mô hình đồ thị, quan hệ giữa các thực thể là trọng tâm. Thuộc tính gốc có thể nằm trên node hoặc edge; một số chỉ số được suy ra từ đường đi hoặc cấu trúc kết nối. Ví dụ, số lượng quan hệ giữa khách hàng và sản phẩm có thể dùng để gợi ý, nhưng kết quả đó phụ thuộc phạm vi dữ liệu và thời điểm tính.

Nếu kết quả tổng hợp được lưu trên node hoặc edge, cần xác định khi thêm/bỏ quan hệ thì chỉ số được cập nhật thế nào. Các chỉ số phụ thuộc toàn mạng có thể tốn kém để tính lại và cần chiến lược cập nhật phù hợp.

### 9.4. Mô hình phân tích

Trong kho dữ liệu, thuộc tính gốc từ hệ thống vận hành thường được đưa vào các bảng sự kiện và chiều. Các phép tổng hợp được tính theo thời gian, sản phẩm, khu vực, kênh hoặc nhóm khách hàng. Cần giữ định nghĩa chỉ số thống nhất giữa dashboard và báo cáo.

Ví dụ, “doanh thu” có thể được tính theo ngày ghi nhận đơn, ngày thanh toán hoặc ngày giao hàng. Nếu mỗi báo cáo tự chọn một cách hiểu, cùng một tên chỉ số sẽ cho các kết quả khác nhau. Từ điển chỉ số cần ghi công thức, bộ lọc, chiều thời gian, múi giờ và quy tắc hoàn/hủy.

## 10. Kiểm soát chất lượng và kiểm chứng kết quả

### 10.1. Kiểm tra công thức với dữ liệu mẫu

Với mỗi thuộc tính suy ra, tạo một tập ví dụ gồm:

- Giá trị bình thường.
- Giá trị biên nhỏ nhất/lớn nhất.
- Giá trị thiếu.
- Giá trị bằng 0 hoặc âm nếu có thể xuất hiện.
- Dữ liệu thay đổi sau khi kết quả được tính.
- Trường hợp quy tắc có phiên bản hoặc ngoại lệ.

Tính kết quả bằng tay cho một vài mẫu và đối chiếu với truy vấn hoặc logic triển khai. Với kết quả tổng hợp, chọn tập bản ghi nhỏ để có thể kiểm tra từng dòng được đưa vào hoặc loại ra.

### 10.2. Đối soát dữ liệu chi tiết và tổng hợp

Một kết quả tổng hợp cần có cách đối chiếu về nguồn. Ví dụ, tổng doanh thu theo ngày phải truy ngược được đến các giao dịch tạo nên con số đó. Khi có sai lệch, nhóm cần xác định được:

- Bản ghi nào được đưa vào tổng hợp?
- Bản ghi nào bị loại và vì sao?
- Bộ lọc hoặc trạng thái nào được áp dụng?
- Dữ liệu có đến muộn hoặc bị cập nhật sau khi chốt không?
- Quy tắc tính hoặc phiên bản công thức nào được dùng?

Không chỉ so sánh tổng cuối cùng. Hãy kiểm tra số lượng bản ghi, tổng giá trị theo nhóm nhỏ và các trường hợp ngoại lệ.

### 10.3. Kiểm tra tính nhất quán của dữ liệu đã lưu

Nếu lưu kết quả suy ra, cần có quy tắc phát hiện khi nó không còn khớp với đầu vào. Có thể dùng truy vấn đối soát định kỳ, kiểm tra trong giao dịch hoặc tái tạo một phần dữ liệu. Cần xác định ngưỡng sai lệch được chấp nhận, người xử lý và cách sửa có lưu dấu vết.

Ví dụ, nếu `order_total` được lưu cùng đơn, có thể tính lại từ các dòng hàng và so sánh. Tuy nhiên, phải dùng đúng quy tắc giảm giá, thuế, phí và thời điểm chốt. Nếu công thức đối soát khác công thức ban đầu, việc so sánh sẽ tạo cảnh báo sai.

## 11. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Coi mọi thuộc tính là dữ liệu nhập trực tiếp | Không nhận ra công thức và nguồn phụ thuộc. | Phân loại nguồn gốc của từng giá trị. |
| Coi mọi kết quả tính toán là có thể tính lại | Làm thay đổi giao dịch lịch sử khi dữ liệu nguồn đổi. | Xác định giá trị nào phải được chốt như bằng chứng. |
| Lưu kết quả suy ra ở nhiều nơi | Các màn hình hoặc báo cáo có thể lệch nhau. | Chỉ định một định nghĩa và nguồn có thẩm quyền. |
| Không ghi công thức và bộ lọc | Không thể giải thích tại sao số liệu khác nhau. | Lập từ điển thuộc tính và chỉ số. |
| Cộng các giá trị khác đơn vị hoặc tiền tệ | Tổng không có ý nghĩa hoặc sai lệch. | Chuẩn hóa đơn vị, tiền tệ và quy tắc quy đổi. |
| Thay NULL bằng 0 tùy tiện | Dữ liệu thiếu bị hiểu thành giá trị thực. | Định nghĩa rõ ngữ nghĩa của giá trị thiếu. |
| Tổng hợp theo trạng thái hiện tại cho báo cáo lịch sử | Kỳ cũ thay đổi khi trạng thái hiện tại đổi. | Xác định thời điểm nghiệp vụ và dữ liệu snapshot/sự kiện. |
| Cập nhật tổng nhưng bỏ sót hoàn tiền hoặc giao trả | Số dư và doanh thu sai. | Liệt kê đầy đủ loại sự kiện và điều kiện được tính. |
| Materialize mà không có quy trình làm mới | Kết quả tổng hợp bị lỗi thời. | Đặt SLA độ mới, cơ chế làm mới và đối soát. |
| Không lưu phiên bản quy tắc | Không tái tạo được kết quả lịch sử. | Gắn phiên bản hoặc thời điểm hiệu lực cho quy tắc. |

## 12. Bộ hồ sơ mô tả thuộc tính và chỉ số

Một bộ từ điển dữ liệu tốt nên cho người đọc biết giá trị đến từ đâu, có ý nghĩa gì và được tính ra sao.

| Trường mô tả | Nội dung |
|---|---|
| Tên thuộc tính/chỉ số | Tên chuẩn dùng trong tài liệu và mô hình. |
| Định nghĩa nghiệp vụ | Giá trị trả lời câu hỏi nào? |
| Phân loại | Gốc, suy ra hay kết quả tổng hợp. |
| Khái niệm sở hữu | Thực thể hoặc quan hệ mà giá trị mô tả. |
| Nguồn/đầu vào | Hệ thống, sự kiện hoặc thuộc tính đầu vào. |
| Chủ sở hữu dữ liệu | Bên chịu trách nhiệm về ý nghĩa và chất lượng. |
| Công thức/bộ lọc | Quy tắc tính, điều kiện, cách nhóm và loại trừ. |
| Đơn vị/miền giá trị | Tiền tệ, đơn vị đo, độ chính xác và miền hợp lệ. |
| Ngữ nghĩa NULL | Chưa biết, không áp dụng, chưa phát sinh hay lỗi. |
| Thời điểm | Thời điểm ghi nhận, tính, chốt hoặc hiệu lực. |
| Phiên bản quy tắc | Phiên bản áp dụng nếu quy tắc thay đổi. |
| Cách lưu | Tính khi đọc, lưu kết quả, snapshot hay tổng hợp vật hóa. |
| Cách kiểm chứng | Ví dụ, truy vấn đối soát và người xác nhận. |

Mẫu ghi nhận:

```text
Tên:
Định nghĩa nghiệp vụ:
Phân loại: ROOT / DERIVED / AGGREGATE
Khái niệm sở hữu:
Nguồn hoặc thuộc tính đầu vào:
Công thức và điều kiện lọc:
Đơn vị và quy tắc làm tròn:
Ý nghĩa của NULL/0:
Thời điểm ghi nhận hoặc tính:
Phiên bản quy tắc:
Cách lưu: ON_DEMAND / STORED / SNAPSHOT / MATERIALIZED
Chủ sở hữu dữ liệu:
Ví dụ hợp lệ và ngoại lệ:
Cách đối soát:
Người xác nhận:
```

## 13. Checklist trước khi chốt thuộc tính và kiểu dữ liệu

- [ ] Mỗi thuộc tính có định nghĩa nghiệp vụ và khái niệm sở hữu rõ ràng.
- [ ] Thuộc tính gốc có nguồn, chủ sở hữu và quy tắc cập nhật.
- [ ] Giá trị được phân biệt giữa dữ liệu ghi nhận và dữ liệu suy ra.
- [ ] Mỗi thuộc tính suy ra có công thức, đầu vào và điều kiện áp dụng.
- [ ] Kết quả tổng hợp có phạm vi, nhóm, bộ lọc và thời điểm rõ ràng.
- [ ] Đã xác định cách xử lý NULL, số 0 và mẫu số bằng 0.
- [ ] Đơn vị đo, tiền tệ, độ chính xác và làm tròn đã được thống nhất.
- [ ] Giá trị đã chốt trong giao dịch được phân biệt với giá trị hiện tại của danh mục.
- [ ] Quy tắc thay đổi có phiên bản hoặc thời điểm hiệu lực khi cần.
- [ ] Quyết định tính khi truy vấn hay lưu kết quả có lý do và cách đối soát.
- [ ] Kết quả tổng hợp có thể truy ngược về dữ liệu chi tiết.
- [ ] Có kiểm tra dữ liệu mẫu bình thường, biên, thiếu và ngoại lệ.
- [ ] Các chỉ số cùng tên có định nghĩa thống nhất giữa hệ thống và báo cáo.
- [ ] Các giả định và câu hỏi mở có người chịu trách nhiệm xác nhận.

## 14. Bài tập thực hành

Một nền tảng giao đồ ăn lưu đơn hàng, dòng món, nhà hàng, tài xế, thanh toán và giao hàng. Một đơn có thể gồm nhiều món, được giảm giá, tính phí giao hàng và thuế. Khách có thể thanh toán nhiều lần do giao dịch lỗi, đơn có thể được giao một phần hoặc hoàn tiền một phần. Quản lý muốn xem tổng doanh thu theo ngày, số đơn theo nhà hàng, giá trị đơn trung bình và tỷ lệ hoàn tiền.

Hãy thực hiện các nhiệm vụ:

1. Liệt kê ít nhất 15 thuộc tính và phân loại thành gốc, suy ra hoặc tổng hợp.
2. Xác định nguồn sự thật và chủ sở hữu của các thuộc tính gốc quan trọng.
3. Viết công thức cho thành tiền dòng món, tổng tiền đơn, số tiền đã thu, số tiền hoàn và số dư còn phải thu.
4. Định nghĩa rõ doanh thu theo ngày: thời điểm ghi nhận, trạng thái đơn, xử lý hủy và hoàn tiền.
5. Viết truy vấn SQL để tính tổng tiền hàng theo đơn và số đơn theo nhà hàng.
6. Phân tích cách xử lý NULL, số 0, tiền tệ, giảm giá và làm tròn.
7. Đề xuất kết quả nào nên tính khi truy vấn, kết quả nào cần snapshot và kết quả nào có thể vật hóa cho báo cáo; nêu lý do.
8. Xây dựng một phép đối soát giữa dữ liệu chi tiết và kết quả tổng hợp.

**Tiêu chí tự đánh giá:** mỗi giá trị có nguồn và ý nghĩa rõ; công thức có thể tính lại từ đầu vào đã xác định; kết quả tổng hợp có phạm vi và bộ lọc; dữ liệu giao dịch lịch sử không bị thay đổi bởi bảng giá hiện tại; chỉ số báo cáo có thể truy ngược về bản ghi nguồn và giải thích được sai lệch.

## Kết luận

Thuộc tính gốc ghi nhận sự kiện hoặc giá trị từ nguồn có thẩm quyền; thuộc tính suy ra được tính theo quy tắc từ dữ liệu đầu vào; kết quả tổng hợp tóm tắt nhiều bản ghi trong một phạm vi xác định. Phân biệt đúng ba nhóm giúp mô hình dữ liệu giữ được nguồn gốc, tính nhất quán và khả năng giải thích. Khi công thức, thời điểm, đơn vị, phiên bản quy tắc và cách đối soát được mô tả rõ, nhóm có thể lựa chọn hợp lý giữa tính khi truy vấn, lưu kết quả giao dịch và vật hóa dữ liệu tổng hợp mà vẫn kiểm chứng được kết quả.
