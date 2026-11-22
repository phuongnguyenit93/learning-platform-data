# Phân biệt định danh, tên hiển thị và thuộc tính có thể thay đổi

Khi mô hình hóa dữ liệu, cần phân biệt ba câu hỏi: **đây là đối tượng nào**, **người dùng gọi hoặc nhìn thấy đối tượng đó bằng tên gì**, và **đối tượng hiện có những đặc điểm nào**. Ba câu hỏi này liên quan với nhau nhưng không đồng nghĩa. Một khách hàng có thể đổi tên, đổi email hoặc chuyển địa chỉ mà vẫn là cùng một khách hàng. Nếu dùng tên hoặc email làm khóa chính, thay đổi bình thường của nghiệp vụ có thể buộc hệ thống cập nhật hàng loạt khóa ngoại và làm đứt lịch sử.

Trong **data modeling**, định danh giúp nhận biết một thực thể xuyên suốt vòng đời của nó. Tên hiển thị giúp con người tìm và hiểu thực thể. Thuộc tính mô tả trạng thái hoặc đặc điểm có thể thay đổi theo thời gian. Thiết kế tốt giữ định danh ổn định, thể hiện rõ các quy tắc duy nhất và lưu lịch sử khi nghiệp vụ cần biết giá trị đã thay đổi ra sao.

Bài học dùng hệ thống bán hàng làm ví dụ. Một khách hàng có mã nội bộ, tên hiển thị, tên pháp lý, email, số điện thoại và địa chỉ. Khách hàng có thể đổi nhiều thuộc tính trong số đó; đơn hàng đã phát sinh vẫn phải trỏ đúng khách hàng và giữ được thông tin cần thiết tại thời điểm giao dịch.

## 1. Ba khái niệm cần tách biệt

### 1.1. Định danh trả lời “đây là đối tượng nào?”

Định danh là giá trị hoặc tập giá trị dùng để phân biệt một thực thể với các thực thể khác trong một phạm vi xác định. Định danh tốt giúp hệ thống tiếp tục nhận ra cùng một đối tượng khi tên, địa chỉ, trạng thái hoặc những đặc điểm mô tả thay đổi.

Ví dụ, khách hàng có customer_id bằng 4821 có thể đổi tên hiển thị từ “Nguyễn Minh An” thành “Minh An Nguyễn”. Các đơn hàng cũ vẫn tham chiếu customer_id 4821, vì việc đổi tên không tạo ra một khách hàng mới.

Trong mô hình quan hệ, khóa chính thường được dùng làm định danh bản ghi. Tuy nhiên, cần phân biệt:

- **Identity của thực thể:** khái niệm nghiệp vụ về việc đối tượng có còn là cùng một đối tượng qua thời gian hay không.
- **Identifier:** giá trị được dùng để nhận diện đối tượng, ví dụ customer_id, mã hợp đồng hoặc mã từ hệ thống đối tác.
- **Primary key:** khóa được chọn để định danh duy nhất một hàng trong bảng.
- **Candidate key:** tập thuộc tính tối thiểu có thể xác định duy nhất một hàng theo quy tắc dữ liệu.

Một bảng có thể có nhiều candidate key nhưng chỉ chọn một primary key. Một mã bên ngoài có thể là candidate key trong phạm vi nhà cung cấp, nhưng không nhất thiết phù hợp làm khóa chính nội bộ.

### 1.2. Tên hiển thị trả lời “con người gọi đối tượng này là gì?”

Tên hiển thị phục vụ giao diện, tìm kiếm, trao đổi và báo cáo. Nó có thể trùng giữa nhiều đối tượng, có thể thay đổi, có thể có nhiều cách viết và có thể phụ thuộc ngôn ngữ hoặc ngữ cảnh.

Ví dụ:

- Hai khách hàng khác nhau có thể cùng tên “Nguyễn Văn An”.
- Một khách hàng có thể dùng tên gọi thân mật trong giao diện nhưng tên pháp lý trên hóa đơn.
- Một sản phẩm có thể có tên ngắn trong danh sách và tên đầy đủ trong trang chi tiết.
- Một tổ chức có thể đổi tên thương mại mà vẫn giữ nguyên tư cách pháp nhân.

Vì vậy, tên hiển thị thường không phải khóa định danh. Nếu nghiệp vụ yêu cầu tên duy nhất trong một phạm vi, hãy thể hiện quy tắc đó bằng ràng buộc phù hợp; vẫn cần xem xét tên có thể đổi hay không và việc đổi tên ảnh hưởng đến tham chiếu thế nào.

### 1.3. Thuộc tính mô tả có thể thay đổi

Thuộc tính mô tả đặc điểm của thực thể: email, số điện thoại, địa chỉ, trạng thái, phân loại, ngày sinh, màu sắc hoặc giá hiện tại. Một số thuộc tính gần như ổn định, một số thay đổi thường xuyên, một số chỉ đúng trong một khoảng thời gian.

Không nên giả định mọi thuộc tính đều có vòng đời giống nhau. Địa chỉ giao hàng trên đơn hàng đã hoàn tất là snapshot lịch sử; địa chỉ liên hệ hiện tại của khách hàng là thuộc tính có thể cập nhật. Cả hai có thể chứa cùng một chuỗi địa chỉ nhưng mang ý nghĩa và quy tắc thay đổi khác nhau.

| Thành phần | Câu hỏi | Ví dụ khách hàng | Đặc tính thường gặp |
|---|---|---|---|
| Định danh | Đối tượng nào? | customer_id = 4821 | Ổn định trong phạm vi và vòng đời đã định nghĩa |
| Tên hiển thị | Hiển thị hoặc gọi ra sao? | “Minh An Nguyễn” | Có thể trùng, đổi, dịch hoặc định dạng lại |
| Thuộc tính mô tả | Đối tượng có đặc điểm gì? | Email, số điện thoại, địa chỉ | Có thể thay đổi; cần quy tắc miền giá trị |
| Snapshot | Giá trị nào đúng tại một sự kiện? | Tên và địa chỉ trên hóa đơn | Giữ nguyên theo sự kiện đã chốt |

## 2. Vì sao định danh cần ổn định?

Một thực thể thường được tham chiếu từ nhiều nơi. Khách hàng có thể được tham chiếu bởi đơn hàng, hóa đơn, thanh toán, phiếu hỗ trợ và chương trình thành viên. Nếu khóa tham chiếu dựa trên thuộc tính có thể đổi, một thay đổi đơn giản sẽ lan qua nhiều bảng và nhiều hệ thống.

Hãy xét mô hình dùng email làm khóa chính:

~~~mermaid
flowchart TD
    E[email làm khóa chính] --> O[orders.customer_email]
    E --> P[payments.customer_email]
    E --> S[support_cases.customer_email]
    C[Khách hàng đổi email] --> U[Phải cập nhật mọi tham chiếu]
    U --> R[Nguy cơ thiếu cập nhật và đứt lịch sử]
~~~

Nếu khách hàng đổi email, hệ thống phải cập nhật mọi nơi tham chiếu đến email. Một tiến trình import hoặc tích hợp bên ngoài có thể vẫn gửi email cũ. Nếu cập nhật không nguyên tử, một phần dữ liệu có thể trỏ đến email mới và phần còn lại vẫn trỏ đến email cũ.

Với khóa nội bộ ổn định, quan hệ chỉ tham chiếu customer_id. Email được cập nhật như một thuộc tính hoặc một thông tin liên hệ có vòng đời riêng. Các đơn hàng không cần thay đổi khóa ngoại.

Định danh ổn định còn có ích khi:

- Tên hoặc mã hiển thị thay đổi theo chính sách.
- Một đối tượng có nhiều tên, biệt danh hoặc ngôn ngữ.
- Dữ liệu được đồng bộ qua nhiều hệ thống.
- Cần lưu lịch sử thay đổi và kiểm toán.
- Cần gộp các bản ghi trùng nhưng vẫn bảo toàn tham chiếu cũ.
- Đối tượng được tham chiếu bởi sự kiện hoặc tài liệu trong thời gian dài.

Ổn định không có nghĩa là identifier phải được công khai mãi mãi. Nó có nghĩa là hệ thống có quy tắc rõ để nhận biết cùng một thực thể trong phạm vi đã chọn.

## 3. Các loại định danh và phạm vi sử dụng

### 3.1. Khóa thay thế (surrogate key)

Khóa thay thế là định danh kỹ thuật do hệ thống tạo ra, không mang ý nghĩa nghiệp vụ trực tiếp. Ví dụ:

- Số nguyên tăng dần: customer_id = 4821.
- UUID: 550e8400-e29b-41d4-a716-446655440000.
- ULID hoặc một định dạng định danh có thứ tự thời gian.

Ưu điểm:

- Không thay đổi khi tên, email, mã hiển thị hoặc thuộc tính nghiệp vụ thay đổi.
- Không phụ thuộc quy tắc cấp mã của bộ phận nghiệp vụ hoặc hệ thống ngoài.
- Khóa ngoại thường ngắn và dễ tham chiếu.
- Có thể tạo đối tượng trước khi biết đủ thuộc tính nghiệp vụ.

Chi phí:

- Cần thêm một trường và cơ chế sinh giá trị.
- Không tự bảo đảm tính duy nhất của các thuộc tính nghiệp vụ.
- Người dùng không thể hiểu đối tượng chỉ từ mã nội bộ.
- Có thể cần bảng ánh xạ khi tích hợp với hệ thống ngoài.

Khóa thay thế phù hợp làm primary key trong nhiều mô hình giao dịch. Tuy nhiên, vẫn cần unique constraint cho mã hợp đồng, mã sản phẩm hoặc email nếu nghiệp vụ yêu cầu duy nhất.

### 3.2. Khóa tự nhiên (natural key)

Khóa tự nhiên là thuộc tính hoặc tập thuộc tính có ý nghĩa ngoài đời và được nghiệp vụ dùng để nhận diện đối tượng, ví dụ:

- Mã VIN của một phương tiện.
- Mã ISBN của một ấn phẩm.
- Mã số thuế trong phạm vi cơ quan cấp.
- Mã hợp đồng do tổ chức phát hành.

Khóa tự nhiên có thể hữu ích khi nó ổn định, duy nhất, được quản lý bởi nguồn có thẩm quyền và không thay đổi trong vòng đời cần lưu. Tuy nhiên, cần kiểm tra kỹ phạm vi duy nhất, quy tắc cấp lại, sửa sai và khả năng tái sử dụng.

Một mã số thuế hoặc mã doanh nghiệp có thể cần gắn với quốc gia/cơ quan cấp. Một mã sản phẩm có thể chỉ duy nhất trong một nhà cung cấp. Nếu bỏ qua phạm vi, hệ thống có thể coi hai mã giống nhau là cùng một đối tượng dù chúng thuộc hai nguồn khác nhau.

Khóa tự nhiên có thể được lưu bằng unique constraint và dùng để tra cứu, trong khi primary key nội bộ vẫn là khóa thay thế. Cách này giảm sự phụ thuộc của các khóa ngoại vào quy tắc nghiệp vụ có thể thay đổi.

### 3.3. Khóa ghép (composite key)

Khóa ghép kết hợp nhiều thuộc tính để xác định duy nhất một hàng. Ví dụ, mã sản phẩm có thể chỉ duy nhất trong từng cửa hàng:

**(store_id, local_product_code)**

Một dòng đơn hàng có thể được định danh bằng:

**(order_id, line_number)**

Khóa ghép phản ánh đúng phạm vi nghiệp vụ. Nhưng khi nhiều bảng khác phải tham chiếu đến bản ghi đó, khóa ngoại sẽ chứa nhiều cột. Nếu một thành phần có thể đổi, các tham chiếu trở nên phức tạp.

Có thể dùng khóa thay thế làm primary key và vẫn đặt unique constraint trên tổ hợp tự nhiên. Quyết định phụ thuộc vào số lượng quan hệ, tính ổn định của các thành phần và khả năng đọc hiểu mô hình.

### 3.4. Định danh từ hệ thống bên ngoài

Một khách hàng có thể có ID trong CRM, ID trong nền tảng thanh toán và ID trong hệ thống kế toán. Những ID này không nên bị coi là cùng một không gian định danh.

Hãy lưu định danh ngoài kèm nguồn phát hành:

| Nguồn | Giá trị ngoài | Thực thể nội bộ |
|---|---|---|
| CRM-A | C-00981 | customer_id = 4821 |
| Payment-B | cus_7ab12 | customer_id = 4821 |
| ERP-C | BP-1045 | customer_id = 4821 |

C-00981 chỉ duy nhất trong CRM-A, không nhất thiết duy nhất trên toàn hệ thống. Vì vậy, cặp (issuer, external_id) mới là định danh tích hợp phù hợp. Một thực thể nội bộ có thể có nhiều định danh ngoài.

### 3.5. So sánh các lựa chọn

| Loại định danh | Khi phù hợp | Rủi ro cần quản lý |
|---|---|---|
| Số nguyên tăng dần | Cơ sở dữ liệu tập trung, quan hệ nội bộ nhiều | Có thể đoán được; không phải cơ chế phân quyền |
| UUID/ULID | Tạo ID phân tán, đồng bộ nhiều nút hoặc cần ID toàn cục | Kích thước index, thứ tự sinh và cách biểu diễn |
| Khóa tự nhiên | Mã nghiệp vụ ổn định, có nguồn cấp rõ ràng | Đổi mã, tái sử dụng, phạm vi duy nhất |
| Khóa ghép | Định danh phụ thuộc phạm vi hoặc quan hệ | Khóa ngoại dài và khó thay đổi thành phần |
| ID bên ngoài | Tích hợp với hệ thống khác | Trùng giá trị giữa nguồn, thay đổi theo nhà cung cấp |

Không có một loại định danh tốt nhất cho mọi trường hợp. Hãy chọn dựa trên vòng đời thực thể, phạm vi duy nhất, số lượng tham chiếu và cách tích hợp.

## 4. Tên hiển thị không phải định danh

### 4.1. Tên có thể trùng

Hai người có thể cùng họ tên. Hai tổ chức có thể có tên thương mại giống nhau ở hai quốc gia. Hai sản phẩm có thể có cùng tên phổ thông nhưng khác nhà sản xuất hoặc phiên bản.

Nếu dùng tên làm khóa, hệ thống phải giả định một điều không đúng: mỗi tên chỉ thuộc về một đối tượng. Việc thêm ràng buộc UNIQUE trên tên có thể ngăn dữ liệu hợp lệ; bỏ ràng buộc lại khiến tên không thể dùng làm tham chiếu duy nhất.

Tên vẫn có thể được tìm kiếm hoặc lập chỉ mục. Điều đó không khiến nó trở thành định danh. Tìm kiếm tên thường trả về một hoặc nhiều kết quả; người dùng có thể cần thêm ngữ cảnh để chọn đúng thực thể.

### 4.2. Tên có thể đổi và có nhiều dạng

Tên có thể thay đổi do:

- Cá nhân đổi tên hoặc dùng tên khác trong giao tiếp.
- Tổ chức đổi tên thương mại hoặc tái cấu trúc.
- Sản phẩm được đổi tên khi tái định vị.
- Chuẩn hóa chính tả, dấu câu hoặc cách viết.
- Dịch tên sang ngôn ngữ khác.
- Giao diện rút gọn tên để phù hợp không gian hiển thị.

Một thực thể có thể cần nhiều loại tên:

- Tên pháp lý.
- Tên thương mại.
- Tên hiển thị.
- Tên viết tắt.
- Bí danh hoặc tên cũ.
- Tên theo từng ngôn ngữ.

Không nên gom mọi ý nghĩa vào một cột name nếu hệ thống phải phân biệt các trường hợp này. Hãy đặt tên trường theo mục đích và xác định loại tên nào được dùng trên hợp đồng, hóa đơn, tìm kiếm hoặc giao diện.

### 4.3. Chuẩn hóa tên để tìm kiếm

Chuẩn hóa tên có thể giúp tìm kiếm nhất quán, nhưng cần tách giá trị gốc khỏi giá trị dùng để tìm kiếm. Ví dụ, hệ thống có thể lưu tên hiển thị nguyên bản và một dạng chuẩn hóa để tìm kiếm không phân biệt chữ hoa/thường hoặc khoảng trắng.

Không nên ghi đè tên gốc bằng kết quả chuẩn hóa nếu định dạng gốc có ý nghĩa. Dấu tiếng Việt, dấu câu, khoảng trắng, chữ viết tắt và thứ tự họ tên có thể mang thông tin cần giữ.

Chuẩn hóa Unicode, collation và so sánh không phân biệt hoa thường phụ thuộc hệ quản trị và yêu cầu ngôn ngữ. Cần xác định rõ quy tắc tìm kiếm thay vì tự giả định hai chuỗi có cách mã hóa khác nhau là khác người hoặc cùng người.

### 4.4. Tên duy nhất vẫn cần khóa riêng

Một số miền nghiệp vụ có tên hoặc mã hiển thị duy nhất trong phạm vi, ví dụ username duy nhất trên một nền tảng hoặc slug duy nhất trong một website. Khi đó:

- Đặt unique constraint đúng phạm vi.
- Xác định quy tắc chuẩn hóa và so sánh.
- Xác định ai được đổi giá trị.
- Xử lý URL cũ hoặc alias khi đổi tên.
- Giữ định danh nội bộ ổn định để các quan hệ không phụ thuộc slug.

Tên duy nhất có thể là candidate key trong một thời điểm, nhưng nếu được phép đổi thì vẫn không phải lựa chọn tốt cho khóa chính lâu dài.

## 5. Thuộc tính có thể thay đổi và vòng đời giá trị

### 5.1. Phân loại theo mức độ ổn định

Khi thiết kế thuộc tính, hãy phân loại theo vòng đời:

| Nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Định danh ổn định | customer_id | Không đổi khi cập nhật hồ sơ |
| Thuộc tính tương đối ổn định | Ngày thành lập, ngày sinh | Có thể sửa khi phát hiện sai; cân nhắc audit |
| Thuộc tính thường xuyên thay đổi | Email, số điện thoại, địa chỉ | Cập nhật có kiểm soát; có thể lưu lịch sử |
| Trạng thái hiện tại | Active, suspended | Quy định chuyển trạng thái và quyền thay đổi |
| Snapshot theo sự kiện | Tên trên hóa đơn đã phát hành | Giữ giá trị tại thời điểm sự kiện |
| Dữ liệu dẫn xuất | Số đơn hàng, điểm thành viên | Tính lại được hoặc cần cơ chế đồng bộ |

Phân loại này giúp quyết định nên cập nhật tại chỗ, lưu bảng lịch sử, tạo sự kiện hay chụp snapshot.

### 5.2. Cập nhật thuộc tính không làm đổi identity

Ví dụ, khách hàng đổi số điện thoại:

~~~sql
UPDATE customers
SET phone_number = '+84-900-123-456',
    updated_at = now()
WHERE customer_id = 4821;
~~~

Các bảng orders, invoices và support_cases tiếp tục tham chiếu customer_id 4821. Không cần thay đổi các khóa ngoại chỉ vì số điện thoại đã đổi.

Nếu một thuộc tính được dùng trong tích hợp hoặc tra cứu, cần cập nhật các bản sao hoặc chỉ mục tìm kiếm theo chính sách. Nhưng quan hệ nội bộ vẫn nên dựa vào định danh ổn định.

### 5.3. Lưu lịch sử khi cần biết giá trị cũ

Chỉ lưu giá trị hiện tại là đủ nếu nghiệp vụ chỉ cần biết thông tin mới nhất. Nếu cần trả lời “địa chỉ nào có hiệu lực tại thời điểm giao hàng?” hoặc “ai đổi tên pháp lý và khi nào?”, cần mô hình lịch sử.

Có thể dùng bảng lịch sử:

~~~sql
CREATE TABLE customer_name_history (
    customer_name_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    name_type VARCHAR(30) NOT NULL,
    name_value VARCHAR(200) NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    changed_by VARCHAR(100),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

valid_from và valid_to biểu diễn khoảng thời gian giá trị có hiệu lực. Cần quy định khoảng thời gian đóng/mở ở hai đầu và cách bảo đảm không có hai tên cùng loại hiệu lực chồng lấn nếu nghiệp vụ không cho phép.

Một bảng audit log lại trả lời câu hỏi khác: ai đã thực hiện thay đổi nào, vào thời điểm nào, giá trị trước và sau là gì. Lịch sử hiệu lực và audit log có thể cùng tồn tại nhưng không nên nhầm lẫn. Lịch sử hiệu lực mô tả sự thật nghiệp vụ theo thời gian; audit mô tả hoạt động thay đổi dữ liệu.

### 5.4. Snapshot theo giao dịch

Hóa đơn đã phát hành cần giữ tên pháp lý và địa chỉ tại thời điểm phát hành. Nếu hóa đơn chỉ tham chiếu khách hàng rồi luôn đọc tên hiện tại, việc khách hàng đổi tên hoặc địa chỉ có thể làm hóa đơn cũ hiển thị sai lịch sử.

Một mô hình có thể lưu:

- invoice.customer_id để tham chiếu thực thể khách hàng.
- invoice.customer_name_snapshot để giữ tên trên hóa đơn.
- invoice.billing_address_snapshot để giữ địa chỉ lập hóa đơn.
- invoice.issued_at để xác định thời điểm phát hành.

Snapshot không phải bản sao thừa nếu nó có ý nghĩa “giá trị đã được chốt trong sự kiện này”. Cần ghi rõ trường nào là snapshot và không tự động cập nhật theo hồ sơ hiện tại.

## 6. Thiết kế schema minh họa

Ví dụ sau tách định danh khách hàng khỏi tên, email và định danh bên ngoài. Cú pháp minh họa theo PostgreSQL.

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    legal_name VARCHAR(250),
    phone_number VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customer_emails (
    customer_email_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    email_address VARCHAR(320) NOT NULL,
    email_normalized VARCHAR(320) NOT NULL,
    verified_at TIMESTAMPTZ,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE customer_external_ids (
    customer_external_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    issuer VARCHAR(80) NOT NULL,
    external_id VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (issuer, external_id)
);

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    order_number VARCHAR(40) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE invoices (
    invoice_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    customer_name_snapshot VARCHAR(250) NOT NULL,
    billing_address_snapshot TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL
);
~~~

Mô hình này thể hiện một số quyết định:

- customer_id là định danh nội bộ ổn định.
- display_name và legal_name có mục đích khác nhau và có thể thay đổi.
- Email được tách thành thực thể liên hệ vì khách hàng có thể có nhiều email và lịch sử xác minh riêng.
- (issuer, external_id) định danh một mã ngoài trong phạm vi nguồn phát hành.
- Đơn hàng tham chiếu khách hàng bằng khóa nội bộ.
- Hóa đơn giữ snapshot tên và địa chỉ tại thời điểm phát hành.

Ví dụ chưa thêm mọi quy tắc cần thiết. Nếu email phải duy nhất trên toàn hệ thống, cần thêm unique constraint phù hợp với chính sách chuẩn hóa và trạng thái hoạt động. Nếu chỉ một email được đánh dấu primary cho mỗi khách hàng, có thể dùng partial unique index trên customer_id với điều kiện is_primary. Nếu email có thể được chuyển từ tài khoản này sang tài khoản khác, cần định nghĩa chính sách thu hồi, xác minh và thời điểm hiệu lực.

### 6.1. Tên và email có phải duy nhất không?

Đây là quyết định nghiệp vụ, không phải mặc định kỹ thuật:

- Tên hiển thị thường không duy nhất.
- Tên pháp lý có thể trùng hoặc thay đổi theo giấy tờ.
- Email có thể được yêu cầu duy nhất cho tài khoản đăng nhập, nhưng không nhất thiết duy nhất cho một khách hàng tổ chức hoặc hồ sơ người nhận.
- Số điện thoại có thể được chia sẻ trong gia đình hoặc nhóm.
- Mã bên ngoài chỉ duy nhất trong phạm vi nguồn phát hành.

Nếu cần duy nhất, hãy xác định rõ phạm vi: toàn hệ thống, trong một tenant, trong một quốc gia, trong một loại tài khoản hay chỉ trong các bản ghi đang hoạt động. Unique constraint phải phản ánh đúng phạm vi đó.

### 6.2. Thay đổi email mà không đổi khóa ngoại

Khi khách hàng cập nhật email, hệ thống xác minh email mới rồi thêm hoặc kích hoạt thông tin liên hệ mới. Các đơn hàng tiếp tục dùng customer_id. Nếu cần giữ lịch sử email cũ, có thể đánh dấu email cũ không còn hoạt động hoặc lưu khoảng thời gian hiệu lực.

Không nên thay customer_id bằng email mới hoặc cập nhật mọi khóa ngoại theo email. Điều đó trộn lẫn thông tin liên hệ với identity của thực thể.

## 7. Phạm vi và tính duy nhất của định danh

### 7.1. Định danh toàn cục và định danh theo phạm vi

Một mã có thể duy nhất trong một phạm vi nhưng trùng ở phạm vi khác. Ví dụ:

- Mã nhân viên duy nhất trong một công ty, không phải toàn tập đoàn.
- Mã sản phẩm duy nhất trong một cửa hàng, không phải trên toàn sàn.
- Số hợp đồng duy nhất trong từng năm hoặc từng chi nhánh.
- ID người dùng duy nhất trong một tenant.

Khi phạm vi là một phần của identity nghiệp vụ, cần đưa nó vào candidate key hoặc mô hình quan hệ. Ví dụ, (tenant_id, local_user_code) có thể là unique key. Khóa thay thế user_id vẫn có thể được dùng làm primary key để tham chiếu nội bộ.

### 7.2. Định danh có thể được cấp lại hoặc tái sử dụng

Một số mã hiển thị được tái sử dụng sau khi đối tượng bị xóa hoặc hết hiệu lực. Nếu mã đó xuất hiện trong dữ liệu lịch sử, việc tái sử dụng có thể khiến tham chiếu cũ trở nên mơ hồ.

Hãy xác định:

- Mã có được tái sử dụng không?
- Khi nào mã được xem là hết hiệu lực?
- Mã có cần duy nhất xuyên suốt lịch sử không?
- Nếu mã được cấp lại, cần phân biệt bằng thời gian hoặc issuer không?
- Các hệ thống tích hợp lưu mã hay lưu ID nội bộ?

Định danh nội bộ thường không nên tái sử dụng. Một hàng bị xóa vật lý rồi một hàng mới nhận lại cùng ID có thể làm dữ liệu cũ trỏ nhầm sang thực thể mới. Với dữ liệu nghiệp vụ cần lưu lịch sử, thường nên ngừng hoạt động hoặc lưu trữ bản ghi thay vì xóa rồi tái cấp định danh.

### 7.3. Định danh không phải cơ chế bảo mật

ID tăng dần có thể đoán được; UUID khó đoán hơn nhưng không tự động chứng minh người gọi có quyền truy cập. Quyền truy cập phải được kiểm tra theo người dùng, tenant và quan hệ sở hữu. Không được coi việc che giấu ID là cơ chế phân quyền.

Nếu API công khai cần một mã tham chiếu khó đoán hoặc ổn định, có thể dùng public identifier riêng. Mã công khai vẫn phải được kiểm tra quyền trên từng đối tượng. Có thể giữ internal primary key và public ID như hai trường có mục đích khác nhau.

## 8. Khi thực thể đổi, gộp hoặc tách

### 8.1. Đổi tên không tạo thực thể mới

Nếu cùng một tổ chức đổi tên thương mại, identity có thể vẫn giữ nguyên. Cập nhật tên hiện tại, lưu lịch sử nếu cần và giữ các quan hệ. Đừng tạo tổ chức mới chỉ vì tên hiển thị thay đổi.

Tuy nhiên, nếu một tổ chức pháp lý chấm dứt và một pháp nhân mới được thành lập, nghiệp vụ có thể coi đó là hai thực thể khác nhau dù tên gần giống. Việc xác định identity cần dựa trên ý nghĩa nghiệp vụ, không chỉ dựa vào chuỗi tên.

### 8.2. Gộp hai bản ghi trùng (merge)

Trong thực tế có thể tạo hai hồ sơ cho cùng một khách hàng. Sau khi xác minh trùng, hệ thống có thể chọn một bản ghi làm bản ghi chuẩn, chuyển quan hệ và giữ ánh xạ từ ID cũ sang ID chuẩn.

Quy trình gộp cần:

1. Xác minh hai bản ghi thực sự đại diện cùng một thực thể.
2. Chọn bản ghi chuẩn và xác định cách kết hợp thuộc tính.
3. Chuyển các quan hệ phụ thuộc trong transaction hoặc quy trình có thể phục hồi.
4. Giữ lịch sử ID cũ và thông tin ai phê duyệt việc gộp.
5. Xử lý các định danh ngoài và các bản ghi trùng lặp.
6. Cập nhật hệ thống tích hợp và chỉ mục tìm kiếm.
7. Kiểm tra các đơn hàng, hóa đơn và báo cáo sau khi gộp.

Không nên xóa một ID cũ rồi quên nó. Một bảng alias hoặc mapping có thể lưu old_customer_id, canonical_customer_id, thời điểm và lý do. Các tham chiếu cũ từ hệ thống ngoài có thể cần được giải quyết qua ánh xạ này.

### 8.3. Tách một bản ghi thành nhiều thực thể

Ngược lại, một hồ sơ có thể chứa dữ liệu của hai người hoặc hai tổ chức bị nhập nhầm. Tách bản ghi cần xác định dữ liệu nào thuộc về từng thực thể và quan hệ lịch sử nào cần phân chia.

Không phải mọi giao dịch đều có thể tự động chia đôi. Một hóa đơn đã phát hành có thể vẫn thuộc về chủ thể ký tại thời điểm đó. Cần lưu quyết định sửa dữ liệu, giữ bằng chứng và không thay đổi lịch sử sự kiện một cách âm thầm.

### 8.4. Khử trùng lặp không đồng nghĩa với gộp identity

Hai hồ sơ có cùng tên và địa chỉ chưa chắc là một người. Hai khách hàng cùng email có thể là một gia đình dùng chung hộp thư hoặc một doanh nghiệp có nhiều người liên hệ. Matching có thể tạo danh sách nghi vấn, nhưng việc gộp cần dựa trên quy tắc và bằng chứng.

Hãy phân biệt:

- **Exact match:** khớp chính xác theo identifier được tin cậy trong đúng phạm vi.
- **Probabilistic match:** ước lượng khả năng trùng dựa trên nhiều thuộc tính.
- **Merge decision:** quyết định nghiệp vụ đã xác minh rằng hai hồ sơ cùng một thực thể.

Không nên tự động gộp chỉ dựa trên tên gần giống hoặc một thuộc tính có thể chia sẻ.

## 9. Những lỗi thiết kế thường gặp

**Dùng tên làm primary key.** Tên có thể trùng và thay đổi. Hãy dùng định danh ổn định, lưu tên như thuộc tính mô tả.

**Dùng email làm khóa ngoại ở mọi bảng.** Email có thể đổi, bị thu hồi hoặc dùng chung. Hãy tham chiếu bằng ID nội bộ; lưu email theo chính sách liên hệ và đăng nhập.

**Cho rằng unique đồng nghĩa với immutable.** Một thuộc tính có thể duy nhất ở hiện tại nhưng vẫn được phép đổi. Unique constraint bảo vệ tính duy nhất, không tự bảo đảm giá trị bất biến.

**Dùng một trường name cho mọi mục đích.** Tên pháp lý, tên thương mại, tên hiển thị và tên cũ có ý nghĩa khác nhau. Hãy đặt tên theo mục đích.

**Đưa ý nghĩa nghiệp vụ vào ID kỹ thuật.** Mã như HN-2026-00042 có thể chứa chi nhánh và năm. Khi tổ chức hoặc quy tắc đánh số đổi, ID trở nên khó duy trì. Nếu cần mã dễ đọc, lưu nó thành business identifier có quy tắc riêng.

**Coi ID bên ngoài là toàn cục.** 12345 từ hai nhà cung cấp có thể là hai đối tượng khác nhau. Luôn lưu issuer hoặc namespace.

**Ghi đè lịch sử bằng giá trị mới.** Nếu hóa đơn, hợp đồng hoặc sự kiện cần phản ánh trạng thái tại thời điểm phát sinh, hãy lưu snapshot hoặc lịch sử hiệu lực.

**Tự động gộp theo tên.** Tên giống nhau không chứng minh cùng identity. Cần xác minh theo nhiều tín hiệu và quy trình phê duyệt.

**Tái sử dụng khóa đã xóa.** Điều này có thể khiến tham chiếu lịch sử trỏ nhầm. Nên giữ ID ổn định và quản lý trạng thái lưu trữ/ngừng hoạt động.

**Dùng ID khó đoán thay cho kiểm tra quyền.** UUID không thay thế authorization. Mỗi truy vấn vẫn phải xác minh quyền trên thực thể được yêu cầu.

## 10. Quy trình quyết định định danh

Khi tạo mô hình cho một thực thể, có thể thực hiện theo các bước:

1. **Định nghĩa thực thể:** đối tượng nghiệp vụ là gì, ranh giới với các khái niệm gần nó ra sao?
2. **Xác định identity:** khi nào hai bản ghi là cùng một đối tượng, khi nào là hai đối tượng khác nhau?
3. **Liệt kê candidate identifier:** mã nội bộ, mã nghiệp vụ, mã ngoài hoặc tổ hợp thuộc tính nào có thể nhận diện?
4. **Kiểm tra độ ổn định:** identifier có thể đổi, cấp lại, tái sử dụng hoặc trùng giữa các phạm vi không?
5. **Chọn primary key:** chọn khóa phù hợp cho quan hệ nội bộ và giữ các quy tắc duy nhất khác bằng constraint.
6. **Phân loại tên và thuộc tính:** tên hiển thị, tên pháp lý, liên hệ, trạng thái và snapshot có mục đích riêng không?
7. **Xác định lịch sử:** chỉ cần giá trị hiện tại hay cần biết ai đổi, khi nào và giá trị có hiệu lực trong khoảng nào?
8. **Xác định phạm vi duy nhất:** toàn hệ thống, tenant, issuer, chi nhánh hay một khoảng thời gian?
9. **Thiết kế xử lý thay đổi:** đổi tên, đổi mã, gộp, tách, ngừng hoạt động và xóa được xử lý ra sao?
10. **Kiểm chứng:** thử trùng tên, đổi email, thay mã ngoài, merge, split và truy vấn lịch sử.

Quyết định nên được ghi lại cùng giả định và lý do. Nếu quy tắc nghiệp vụ thay đổi, nhóm có thể đánh giá tác động thay vì phải suy luận từ cấu trúc bảng.

## 11. Checklist đánh giá mô hình

Trước khi chốt thiết kế, hãy tự hỏi:

- [ ] Định nghĩa thực thể và ranh giới identity đã rõ.
- [ ] Primary key ổn định qua các thay đổi tên và thuộc tính.
- [ ] Candidate key và quy tắc duy nhất được xác định theo đúng phạm vi.
- [ ] Tên hiển thị được phân biệt với tên pháp lý, alias hoặc tên theo ngôn ngữ khi cần.
- [ ] Các thuộc tính có thể thay đổi không bị dùng làm khóa ngoại dài hạn.
- [ ] ID bên ngoài được lưu kèm issuer hoặc namespace.
- [ ] Quy tắc chuẩn hóa và so sánh tên/email/mã đã được thống nhất.
- [ ] Snapshot và lịch sử được lưu cho dữ liệu cần kiểm toán hoặc tái hiện sự kiện.
- [ ] Quy trình merge, split, alias và ngừng hoạt động được xác định.
- [ ] Việc tái sử dụng identifier có chính sách rõ ràng.
- [ ] API không dựa vào tính khó đoán của ID để thay thế phân quyền.
- [ ] Có kiểm thử đổi tên, đổi email, trùng tên, trùng ID ngoài và thay đổi trạng thái.

## Kết luận

Định danh, tên hiển thị và thuộc tính mô tả phục vụ ba mục đích khác nhau. Định danh trả lời thực thể nào đang được tham chiếu; tên giúp con người nhận biết và giao tiếp; thuộc tính mô tả đặc điểm hiện tại hoặc giá trị tại một thời điểm. Trộn ba khái niệm này làm mô hình dễ bị đứt quan hệ khi dữ liệu thay đổi và khiến lịch sử giao dịch khó tin cậy.

Hãy chọn identifier dựa trên identity và phạm vi duy nhất của thực thể. Dùng khóa ổn định cho các quan hệ nội bộ, đặt unique constraint cho mã nghiệp vụ khi cần, và lưu ID bên ngoài cùng nguồn phát hành. Tách tên theo mục đích, phân loại thuộc tính theo vòng đời, giữ snapshot hoặc lịch sử khi nghiệp vụ yêu cầu. Khi thực thể được đổi tên, gộp hoặc tách, xử lý có kiểm soát để mọi tham chiếu và sự kiện lịch sử vẫn giữ đúng ý nghĩa.
