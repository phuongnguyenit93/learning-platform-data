# Xác định thực thể, quan hệ và các câu hỏi nghiệp vụ cần trả lời

## 1. Vì sao phải bắt đầu từ nghiệp vụ?

Khi xây dựng hệ thống sử dụng cơ sở dữ liệu NoSQL, câu hỏi đầu tiên không nên là “Tạo những collection hoặc bảng nào?”, mà là **“Hệ thống phải trả lời câu hỏi gì, cho ai, từ dữ liệu nào và với tốc độ ra sao?”**. Cùng một tập dữ liệu về khách hàng, sản phẩm và đơn hàng có thể được tổ chức rất khác nhau nếu ứng dụng chủ yếu tra cứu chi tiết đơn hàng, hiển thị lịch sử mua sắm, phân tích doanh thu hay theo dõi trạng thái giao hàng theo thời gian thực.

Ba hoạt động cần thực hiện trước khi quyết định cấu trúc lưu trữ là:

1. **Xác định thực thể:** Những đối tượng hoặc sự kiện nào có danh tính, thuộc tính và vòng đời cần quản lý?
2. **Xác định quan hệ:** Các thực thể liên kết với nhau như thế nào, với số lượng, tính bắt buộc và quy tắc thay đổi ra sao?
3. **Xác định câu hỏi nghiệp vụ:** Người dùng cần tìm kiếm, lọc, sắp xếp, tổng hợp và cập nhật thông tin gì?

Đây là bước phân tích miền nghiệp vụ, chưa phải bước chọn MongoDB, DynamoDB, Cassandra, Redis, cơ sở dữ liệu đồ thị hay thiết kế khóa cụ thể. Trong NoSQL, **mô hình dữ liệu thường được định hướng bởi cách truy cập dữ liệu**; vì vậy cần hiểu cả thực thể, quan hệ và truy vấn trước khi quyết định nhúng dữ liệu, tham chiếu hoặc tạo mô hình đọc chuyên biệt.

Sau bài học, bạn có thể lập một danh mục thực thể, mô tả quan hệ và tính toàn vẹn dữ liệu, xây dựng danh mục câu hỏi nghiệp vụ có thể chuyển thành truy vấn, đồng thời dùng các kết quả đó để chuẩn bị cho bước thiết kế mô hình và nạp dữ liệu.

## 2. Tình huống xuyên suốt: Hệ thống bán hàng trực tuyến

Giả sử một doanh nghiệp vận hành website bán hàng với các chức năng:

- Khách hàng đăng ký tài khoản, cập nhật hồ sơ và đặt nhiều đơn hàng.
- Mỗi đơn hàng chứa một hoặc nhiều sản phẩm, có số lượng và giá bán tại thời điểm đặt.
- Một đơn hàng có thể trải qua nhiều lần thử thanh toán; có thể thành công hoặc thất bại.
- Nhân viên chăm sóc khách hàng tra cứu đơn hàng và tiến trình xử lý.
- Bộ phận vận hành quản lý tồn kho theo kho hàng.
- Bộ phận kinh doanh theo dõi doanh thu, số đơn và nhóm sản phẩm bán chạy.

Đầu vào có thể đến từ hệ thống đặt hàng, danh mục sản phẩm, cổng thanh toán và hệ thống quản lý kho. Dữ liệu giữa các nguồn có thể cập nhật không đồng thời. Cần phân biệt rõ dữ liệu nguồn nào có thẩm quyền cho từng trường, đặc biệt đối với trạng thái thanh toán, giá bán và số lượng tồn.

Hãy coi đây là tình huống minh họa: những quyết định về truy vấn, giới hạn thời gian phản hồi và cách lưu trữ trong bài cần được xác nhận lại với nghiệp vụ của hệ thống thực tế.

## 3. Xác định thực thể từ quy trình và ngôn ngữ nghiệp vụ

### 3.1. Thế nào là một thực thể?

**Thực thể (entity)** là một đối tượng, khái niệm hoặc sự kiện mà hệ thống cần nhận diện, lưu thuộc tính, theo dõi thay đổi hoặc truy vấn độc lập. Một thực thể thường có:

- **Định danh:** Mã khách hàng, mã đơn hàng, mã sản phẩm hoặc định danh sự kiện.
- **Thuộc tính:** Tên, trạng thái, thời điểm, số tiền, số lượng và các đặc điểm liên quan.
- **Vòng đời:** Thời điểm được tạo, được cập nhật, hoàn tất hoặc ngừng hiệu lực.
- **Quy tắc nghiệp vụ:** Điều kiện hợp lệ và các hành động được phép thực hiện.

Không phải mọi danh từ xuất hiện trong yêu cầu đều phải trở thành một collection riêng. “Màu sắc” có thể chỉ là thuộc tính của biến thể sản phẩm; “địa chỉ giao hàng” có thể là một cấu trúc dữ liệu nằm trong đơn hàng; “lần thử thanh toán” lại có thể cần một bản ghi riêng vì tồn tại nhiều lần và cần được tra cứu để đối soát.

### 3.2. Phương pháp tìm thực thể

Đọc một mô tả nghiệp vụ và đánh dấu:

1. **Danh từ:** Ai hoặc cái gì cần được quản lý? Ví dụ: khách hàng, đơn hàng, sản phẩm, kho.
2. **Động từ:** Điều gì xảy ra giữa chúng? Ví dụ: đặt, chứa, thanh toán, lưu kho, giao.
3. **Sự kiện có ý nghĩa:** Khi nào sự việc diễn ra? Ví dụ: đặt hàng, thanh toán thất bại, xác nhận giao.
4. **Câu hỏi cần tra cứu:** Có cần tìm hoặc thống kê đối tượng đó độc lập với đối tượng khác không?
5. **Quy tắc định danh:** Hai bản ghi có thể cùng tên nhưng vẫn là hai đối tượng khác nhau không?

Ví dụ, từ câu “Khách hàng đặt đơn hàng chứa nhiều sản phẩm; mỗi lần thanh toán được ghi nhận để đối soát”, ta tìm được các thực thể ứng viên **Khách hàng**, **Đơn hàng**, **Sản phẩm**, **Dòng đơn hàng** và **Lần thanh toán**. “Chứa” và “thanh toán” gợi ý quan hệ; “đối soát” cho thấy các lần thử thanh toán cần có lịch sử riêng.

### 3.3. Danh mục thực thể ứng viên

| Thực thể | Định danh đề xuất | Thuộc tính nghiệp vụ cốt lõi | Quy tắc hoặc lưu ý |
|---|---|---|---|
| Khách hàng | customerId | Tên, thông tin liên hệ, trạng thái tài khoản | Thông tin cá nhân có thể thay đổi; cần quyền truy cập phù hợp |
| Sản phẩm | productId; SKU cho từng biến thể bán | Tên, danh mục, giá hiện tại, trạng thái bán | Giá hiện tại khác với giá đã bán trong đơn cũ |
| Đơn hàng | orderId | Khách hàng, thời điểm đặt, trạng thái, tổng tiền | Tổng tiền phải được xác định theo một quy tắc tính nhất quán |
| Dòng đơn hàng | orderId + lineId | Sản phẩm, SKU, số lượng, đơn giá tại thời điểm mua | Hai dòng có thể tham chiếu cùng sản phẩm nhưng thuộc các đơn khác nhau |
| Lần thanh toán | paymentAttemptId | Đơn hàng, nhà cung cấp, số tiền, trạng thái, thời điểm | Một đơn hàng có thể có nhiều lần thử; phải xử lý thông báo lặp |
| Kho | warehouseId | Tên kho, địa điểm, trạng thái hoạt động | Một sản phẩm có thể được lưu ở nhiều kho |
| Tồn kho | warehouseId + SKU | Số lượng khả dụng, số lượng giữ chỗ, thời điểm cập nhật | Cần thống nhất ý nghĩa các loại số lượng |
| Sự kiện đơn hàng | orderEventId | Đơn hàng, loại sự kiện, thời điểm, nguồn phát sinh | Lịch sử thường tăng dần theo thời gian |

Danh mục này là mô hình khái niệm. Một thực thể có thể trở thành collection riêng, phần tử nhúng, bản ghi sự kiện hoặc một dạng lưu trữ khác tùy các câu hỏi truy vấn. Không nên đồng nhất **“thực thể”** với **“bảng/collection vật lý”**.

### 3.4. Phân biệt thực thể, thuộc tính, giá trị và sự kiện

| Mô tả | Phân loại ban đầu | Lý do |
|---|---|---|
| “Khách hàng Nguyễn A” | Một bản thể của Khách hàng | Có định danh và nhiều thuộc tính |
| “Số điện thoại của khách hàng” | Thuộc tính | Thường phụ thuộc vào Khách hàng |
| “Đơn hàng đang chờ giao” | Đơn hàng và giá trị trạng thái | “Chờ giao” là một trạng thái, không tự động là thực thể |
| “Thanh toán lần thứ hai thất bại” | Sự kiện hoặc bản ghi lần thanh toán | Cần thời điểm, mã giao dịch, trạng thái và khả năng đối soát |
| “Địa chỉ giao được chọn khi đặt hàng” | Giá trị chụp tại thời điểm đặt | Nên giữ lịch sử ngay cả khi khách hàng sửa địa chỉ hồ sơ |
| “Danh mục sản phẩm” | Thực thể hoặc thuộc tính tùy nhu cầu | Nếu có phân cấp, quyền quản trị và truy vấn độc lập, nên coi là thực thể |

**Câu hỏi kiểm tra:** Đối tượng có danh tính riêng không? Có được tạo, sửa, hủy, truy vấn hoặc phân quyền độc lập không? Có nhiều bản ghi liên quan tới một đối tượng cha không? Nếu câu trả lời là “có”, đối tượng xứng đáng được xem xét như một thực thể riêng ở mức khái niệm.

## 4. Xác định quan hệ, lực lượng và quy tắc toàn vẹn

### 4.1. Ba kiểu lực lượng quan hệ thường gặp

- **Một – một (1:1):** Một tài khoản có tối đa một hồ sơ cấu hình hiện hành; quan hệ có thể tùy chọn nếu hồ sơ chưa được tạo.
- **Một – nhiều (1:N):** Một khách hàng có nhiều đơn hàng; mỗi đơn hàng thuộc về một khách hàng trong tình huống đã định.
- **Nhiều – nhiều (N:M):** Một đơn hàng có nhiều sản phẩm và một sản phẩm xuất hiện trong nhiều đơn hàng. **Dòng đơn hàng** biểu diễn mỗi lần sản phẩm xuất hiện trong đơn, cùng số lượng và đơn giá.

Ngoài lực lượng, phải xác định **tính bắt buộc**. Chẳng hạn, một khách hàng có thể chưa có đơn hàng; nhưng một đơn đã được chấp nhận phải có ít nhất một dòng đơn. Một đơn có thể chưa có lần thử thanh toán nào nếu đang chờ người mua thực hiện.

### 4.2. Sơ đồ quan hệ khái niệm

~~~mermaid
erDiagram
    KHACH_HANG ||--o{ DON_HANG : dat
    DON_HANG ||--|{ DONG_DON_HANG : gom
    SAN_PHAM ||--o{ DONG_DON_HANG : xuat_hien_trong
    DON_HANG ||--o{ LAN_THANH_TOAN : co
    DON_HANG ||--o{ SU_KIEN_DON_HANG : phat_sinh
    KHO ||--o{ TON_KHO : quan_ly
    SAN_PHAM ||--o{ TON_KHO : duoc_luu_tai
~~~

Sơ đồ cho biết **quan hệ nghiệp vụ**, chưa bắt buộc hệ thống NoSQL phải dùng các collection đúng như mỗi khối trong hình. Ví dụ, dòng đơn hàng có thể được nhúng trong tài liệu đơn hàng, nhưng vẫn là một khái niệm riêng cần được xác định.

### 4.3. Mỗi quan hệ cần mô tả thêm điều gì?

Với từng quan hệ, ghi lại ít nhất:

| Khía cạnh | Câu hỏi cần chốt | Ví dụ |
|---|---|---|
| Lực lượng và tùy chọn | Một bản ghi liên quan bao nhiêu bản ghi? Có được rỗng không? | Một đơn có 1..N dòng; một khách có 0..N đơn |
| Chủ sở hữu vòng đời | Xóa hoặc đóng đối tượng cha thì đối tượng con ra sao? | Đóng tài khoản không có nghĩa được xóa lịch sử đơn đã hoàn tất |
| Tốc độ tăng | Số phần tử con có giới hạn tự nhiên không? | Dòng đơn thường hữu hạn; sự kiện theo thời gian có thể tăng liên tục |
| Tần suất thay đổi | Dữ liệu con đổi cùng hay độc lập với dữ liệu cha? | Giá danh mục thay đổi độc lập với lịch sử đơn |
| Nhu cầu đọc | Có thường cần lấy cùng lúc cả cha và con không? | Màn chi tiết đơn cần tổng đơn cùng các dòng |
| Nhất quán | Những giá trị nào phải đồng bộ tức thời? | Quy tắc trừ tồn kho hoặc giữ chỗ phải được xác định rõ |
| Phạm vi truy cập | Ai được xem hoặc sửa mối liên hệ? | Chỉ người có quyền mới được xem thông tin khách hàng |

Đặc biệt cần phân biệt **quan hệ hiện tại** và **dữ liệu lịch sử**. Sản phẩm có thể đổi tên hoặc giá, nhưng hóa đơn hoặc đơn hàng cũ vẫn phải hiển thị tên và giá tại thời điểm mua. Quan hệ tới sản phẩm gốc giúp quản trị, còn bản chụp giá bán giúp bảo toàn lịch sử.

### 4.4. Quan hệ trong NoSQL không đồng nghĩa với JOIN

Trong mô hình quan hệ, bảng thường được chuẩn hóa và kết hợp qua khóa ngoại. Với NoSQL, có thể:

- **Nhúng (embed):** Lưu một nhóm dữ liệu con trong cùng tài liệu nếu được đọc cùng nhau và có quy mô được kiểm soát.
- **Tham chiếu (reference):** Lưu định danh liên quan, đọc đối tượng ở vị trí khác khi cần.
- **Phi chuẩn hóa có chủ đích:** Sao chép một số thuộc tính phục vụ đường đọc quan trọng, kèm quy tắc cập nhật rõ ràng.
- **Tạo mô hình đọc/tổng hợp riêng:** Chuẩn bị sẵn dữ liệu thống kê hoặc tìm kiếm khi cần nhiều bản ghi và hiệu năng ổn định.

Không có một lựa chọn mặc định đúng cho tất cả hệ thống NoSQL. Việc hỗ trợ giao dịch, truy vấn liên tài liệu, khóa phân vùng, chỉ mục và giới hạn kích thước khác nhau theo công nghệ.

## 5. Chuyển mục tiêu kinh doanh thành câu hỏi có thể truy vấn

Một yêu cầu như “Xem doanh thu” còn quá chung chung để thiết kế dữ liệu. Cần hỏi tiếp:

- **Người sử dụng:** Nhân viên bán hàng, hỗ trợ khách hàng, kế toán hay lãnh đạo?
- **Đơn vị kết quả:** Một đơn, một khách hàng, một sản phẩm, một ngày hay một cửa hàng?
- **Điều kiện lọc:** Thời gian, trạng thái, danh mục, kênh bán, vùng địa lý?
- **Cách sắp xếp và phân trang:** Mới nhất trước, top 10, tải tiếp theo con trỏ?
- **Ý nghĩa chỉ số:** Doanh thu tính khi đặt hàng hay khi thanh toán thành công? Có trừ hoàn tiền và hủy đơn không?
- **Tần suất và quy mô:** Bao nhiêu yêu cầu mỗi giây? Bao nhiêu bản ghi cần đọc? Dữ liệu tăng thế nào?
- **Độ mới, độ trễ và nhất quán:** Phải thấy ngay kết quả mới, hay cho phép trễ vài phút?
- **Phân quyền và dữ liệu nhạy cảm:** Người dùng chỉ được xem đơn của chính mình hay được xem toàn hệ thống?

Một câu hỏi nghiệp vụ đủ rõ sẽ tạo thành **mẫu truy cập dữ liệu (access pattern)** có thể kiểm tra. Ví dụ:

> “Khi khách hàng mở trang Lịch sử mua hàng, hiển thị 20 đơn gần nhất thuộc khách hàng đã xác thực, sắp xếp giảm dần theo thời gian đặt, cho phép tải trang tiếp theo; chỉ trả về mã đơn, ngày đặt, tổng tiền và trạng thái.”

Câu mô tả này cung cấp khóa lọc, cách sắp xếp, số bản ghi, dữ liệu trả về và yêu cầu phân quyền. Nó hữu ích hơn nhiều so với câu “Lấy danh sách đơn hàng”.

### 5.1. Danh mục câu hỏi nghiệp vụ mẫu

Các mục tiêu thời gian bên dưới chỉ là **giả định minh họa để thảo luận**, không phải cam kết hiệu năng chung của NoSQL.

| Mã | Câu hỏi nghiệp vụ | Điều kiện và kết quả mong muốn | Ưu tiên và độ mới gợi ý |
|---|---|---|---|
| Q01 | Khách hàng đã đặt những đơn nào gần đây? | customerId; 20 đơn/trang; sắp theo placedAt giảm dần | Cao; cập nhật gần tức thời |
| Q02 | Chi tiết đơn hàng này gồm gì? | orderId; thông tin đơn, dòng hàng, giá bán, địa chỉ giao tại lúc đặt | Cao; chính xác với đơn đã ghi |
| Q03 | Đơn hàng đang ở giai đoạn nào? | orderId; trạng thái hiện tại, thời điểm đổi và sự kiện gần nhất | Cao; độ mới theo yêu cầu vận hành |
| Q04 | Có bao nhiêu đơn đã thanh toán theo ngày? | Khoảng ngày, kênh bán; số đơn và tổng tiền đã thanh toán | Trung bình; có thể cập nhật theo lô |
| Q05 | Sản phẩm nào bán nhiều nhất trong 30 ngày? | Khoảng ngày, danh mục; tổng số lượng bán, top N | Trung bình; có thể trễ vài phút |
| Q06 | Những lần thanh toán nào thất bại cần kiểm tra? | Trạng thái thất bại, khoảng thời gian, nhà cung cấp | Cao với đội đối soát; gần tức thời |
| Q07 | SKU nào có lượng khả dụng dưới ngưỡng? | warehouseId, ngưỡng tồn; danh sách SKU, số lượng còn | Cao cho vận hành kho; độ mới phải chốt |
| Q08 | Khách hàng cần hỗ trợ có những đơn nào? | Tìm khách theo định danh được phép, rồi lấy đơn gần đây | Cao; cần kiểm soát quyền truy cập |
| Q09 | Đơn hàng đã trải qua những sự kiện nào? | orderId; chuỗi sự kiện theo thời gian, phân trang nếu dài | Trung bình; lịch sử phải đầy đủ |

Các câu hỏi **tra cứu giao dịch** (Q01–Q03, Q06, Q07) thường khác bản chất với câu hỏi **phân tích tổng hợp** (Q04–Q05). Điều đó có thể dẫn tới nhiều mô hình đọc, chỉ mục hoặc hệ thống phân tích riêng, dù tất cả đều xuất phát từ một miền nghiệp vụ.

### 5.2. Định nghĩa chỉ số để tránh kết quả mâu thuẫn

Hai nhóm có thể cùng nói “doanh thu ngày hôm nay” nhưng tính khác nhau. Trước khi thiết kế dữ liệu phải thống nhất:

- **Mốc thời gian:** Theo thời điểm đặt đơn, thanh toán thành công hay hoàn tất giao hàng?
- **Múi giờ báo cáo:** Ngày theo giờ Việt Nam hay UTC? Nên lưu thời điểm theo một chuẩn thống nhất (ví dụ UTC), sau đó chuyển theo múi giờ báo cáo.
- **Trạng thái hợp lệ:** Tính đơn thanh toán thành công, đơn đã hoàn tiền hay đơn hủy như thế nào?
- **Cơ cấu số tiền:** Tính thuế, phí giao hàng, giảm giá, hoàn tiền ra sao?
- **Khóa định danh chống đếm trùng:** Một đơn thanh toán nhiều lần thử chỉ được tính mấy lần?

Ví dụ, một định nghĩa có thể là: **“Doanh thu thanh toán theo ngày = tổng số tiền thu thành công, trừ tổng số tiền hoàn trong ngày ghi nhận, theo múi giờ Asia/Ho_Chi_Minh.”** Đây chỉ là một cách định nghĩa; doanh nghiệp cần phê duyệt trước khi dùng làm công thức tính chính thức.

## 6. Lập ma trận truy vấn gắn với dữ liệu

Sau khi có danh mục câu hỏi, nối từng câu hỏi với thực thể, điều kiện tìm kiếm và cách truy cập dự kiến.

| Truy vấn | Thực thể chính | Khóa lọc / sắp xếp | Dữ liệu cần trả về | Hướng thiết kế ban đầu |
|---|---|---|---|---|
| Q01 | Đơn hàng | customerId + placedAt giảm dần | Thông tin tóm tắt đơn | Cấu trúc/chỉ mục phục vụ lịch sử theo khách |
| Q02 | Đơn hàng, dòng đơn | orderId | Một đơn và toàn bộ dòng hàng | Nhúng các dòng có giới hạn vào đơn là một ứng viên |
| Q03 | Đơn hàng, sự kiện | orderId + thời gian sự kiện | Trạng thái hiện hành và lịch sử | Trạng thái trên đơn; lịch sử có thể lưu riêng |
| Q04 | Đơn hàng, thanh toán | paidAt + trạng thái/kênh | Tổng số đơn, tổng tiền theo ngày | Cân nhắc bản ghi tổng hợp theo ngày |
| Q05 | Dòng đơn, sản phẩm | Khoảng ngày + danh mục | Top SKU theo số lượng | Tổng hợp theo sự kiện bán hoặc mô hình phân tích |
| Q06 | Lần thanh toán | status + thời điểm + nhà cung cấp | Các giao dịch cần kiểm tra | Truy vấn theo trạng thái và khoảng thời gian |
| Q07 | Tồn kho | warehouseId + availableQty | SKU dưới ngưỡng | Đường đọc theo kho và số lượng khả dụng |
| Q08 | Khách hàng, đơn hàng | Định danh liên hệ → customerId | Hồ sơ được phép xem và đơn liên quan | Có thể cần bước tìm khách riêng trước Q01 |
| Q09 | Sự kiện đơn hàng | orderId + occurredAt | Lịch sử theo trình tự | Lưu và truy vấn sự kiện theo đơn |

Ma trận giúp phát hiện những câu hỏi chưa có trường dữ liệu tương ứng. Ví dụ, muốn lọc doanh thu theo **kênh bán** nhưng trên đơn hàng lại chưa xác định thuộc tính kênh bán thì phải bổ sung ngay vào mô hình khái niệm. Muốn phân tích theo **danh mục tại thời điểm mua** phải quyết định lưu bản chụp danh mục, hay chấp nhận kết quả đổi khi sản phẩm được chuyển danh mục.

Các tổ hợp khóa trong ma trận chỉ là **khóa truy cập logic**. Khi chọn cơ sở dữ liệu cụ thể, ta còn phải xác định chỉ mục, khóa phân vùng, thứ tự trường, chiến lược phân trang, cân bằng tải đọc/ghi và giới hạn dung lượng.

## 7. Từ quan hệ nghiệp vụ đến một mô hình tài liệu NoSQL

Phần này minh họa một khả năng với **cơ sở dữ liệu tài liệu**. Nó không phải cấu trúc bắt buộc cho mọi hệ thống NoSQL.

### 7.1. Tài liệu đơn hàng chứa dữ liệu thường được đọc cùng nhau

~~~json
{
  "_id": "ord-1052",
  "customerId": "cus-017",
  "placedAt": "2026-10-12T07:15:00Z",
  "status": "PAID",
  "salesChannel": "WEB",
  "currency": "VND",
  "shippingAddress": {
    "recipientName": "Nguyen A",
    "city": "Ha Noi",
    "addressLine": "Dia chi minh hoa"
  },
  "items": [
    {
      "lineId": "1",
      "productId": "prd-142",
      "sku": "SKU-142-BL",
      "nameAtPurchase": "Ao thun xanh",
      "unitPrice": 220000,
      "quantity": 2,
      "lineTotal": 440000
    }
  ],
  "shippingFee": 20000,
  "totalAmount": 460000,
  "paymentSummary": {
    "status": "SUCCEEDED",
    "paidAt": "2026-10-12T07:16:10Z"
  }
}
~~~

Ví dụ trên thể hiện các quyết định:

1. **customerId** tham chiếu khách hàng, giúp hiển thị lịch sử đặt hàng và tránh sao chép toàn bộ hồ sơ vào mọi đơn.
2. **items** được nhúng vì màn chi tiết đơn thường cần đọc đồng thời thông tin đơn và dòng hàng. Chỉ phù hợp nếu số dòng và kích thước đơn có giới hạn thực tế.
3. **nameAtPurchase** và **unitPrice** là bản chụp lúc đặt hàng để lịch sử không thay đổi theo danh mục sản phẩm hiện tại.
4. **shippingAddress** là địa chỉ đã sử dụng cho đơn đó, không phụ thuộc vào việc khách hàng sửa địa chỉ mặc định sau này.
5. **paymentSummary** phục vụ màn hình đơn hàng. Các lần thử thanh toán chi tiết có thể nằm trong tập dữ liệu riêng để đối soát.
6. Số tiền VND dùng số nguyên theo đơn vị đồng để tránh các lỗi làm tròn phổ biến của số thực khi tính tiền; nếu có nhiều loại tiền tệ, phải xác định đơn vị nhỏ nhất theo từng loại tiền.

Không được mặc định rằng trường **status** và **paymentSummary.status** tự đồng bộ. Cần có luồng cập nhật, cơ chế xử lý sự kiện lặp và quy tắc phục hồi khi cập nhật dở dang.

### 7.2. Các lần thanh toán thường cần lịch sử riêng

~~~json
{
  "_id": "pay-2031",
  "orderId": "ord-1052",
  "attemptNumber": 2,
  "provider": "payment-provider",
  "providerTransactionId": "txn-demo-882",
  "amount": 460000,
  "currency": "VND",
  "status": "SUCCEEDED",
  "occurredAt": "2026-10-12T07:16:10Z"
}
~~~

Đặt các lần thanh toán riêng giúp truy vấn Q06, giữ lịch sử và xử lý số lần thử không biết trước. Tùy công nghệ và yêu cầu, có thể áp đặt ràng buộc duy nhất đối với định danh giao dịch từ nhà cung cấp để chống ghi trùng.

### 7.3. Khi nào nên nhúng, khi nào nên tham chiếu?

| Tiêu chí | Cân nhắc nhúng | Cân nhắc tham chiếu hoặc lưu riêng |
|---|---|---|
| Mẫu đọc | Cha và con gần như luôn được đọc cùng | Con thường được truy vấn độc lập |
| Số phần tử con | Có giới hạn nhỏ, có thể dự đoán | Tăng liên tục hoặc có thể rất lớn |
| Nhịp cập nhật | Thường cập nhật trong cùng nghiệp vụ | Thay đổi độc lập, nhiều tác nhân cập nhật |
| Vòng đời | Con phụ thuộc nhiều vào cha | Con có thời gian lưu giữ và quyền truy cập riêng |
| Trùng lặp | Chụp dữ liệu lịch sử là chủ đích | Dữ liệu chuẩn cần đồng bộ giữa nhiều đối tượng |
| Kích thước | Nằm trong giới hạn tài liệu và hiệu quả đọc | Có nguy cơ phình to, cập nhật hoặc truyền dữ liệu tốn kém |

Ví dụ: nhúng vài dòng hàng trong đơn có thể hợp lý; nhúng **mọi đơn hàng** vào tài liệu khách hàng dễ dẫn đến một mảng không giới hạn, gây khó phân trang và cập nhật. Tương tự, không nên nhúng vô hạn mọi sự kiện vận chuyển trong một tài liệu nếu lịch sử tăng liên tục.

### 7.4. Không phải NoSQL nào cũng dùng tài liệu

- Với **key–value**, cần thiết kế cách tạo khóa và nhóm dữ liệu theo thao tác đọc/ghi.
- Với **wide-column**, lựa chọn khóa phân vùng và thứ tự sắp xếp phải bám sát bộ lọc và đường truy vấn thường gặp.
- Với **graph database**, quan hệ nhiều bước (ví dụ mạng lưới người giới thiệu, liên kết gian lận) có thể được thể hiện bằng đỉnh và cạnh; cần xác định loại cạnh và hướng duyệt.
- Với **document database**, cấu trúc nhúng và tham chiếu thường là quyết định nổi bật.

Vì thế, đầu ra của bài học nên **độc lập công nghệ**: thực thể, quan hệ, ràng buộc và câu hỏi truy vấn. Thiết kế vật lý mới là bước tiếp theo.

## 8. Chốt chất lượng và nguồn gốc dữ liệu trước khi tải

Phân tích thực thể và truy vấn còn giúp phát hiện dữ liệu cần được lấy từ đâu, có đáng tin hay không và phải chuyển đổi thế nào khi nạp vào NoSQL.

### 8.1. Bảng ánh xạ từ nguồn dữ liệu

| Dữ liệu đích | Nguồn nghiệp vụ | Định danh nối ghép | Điều cần kiểm tra |
|---|---|---|---|
| Khách hàng | Hệ thống tài khoản | customerId | Trùng định danh; liên hệ thiếu/không hợp lệ |
| Sản phẩm | Danh mục sản phẩm | productId, SKU | SKU trùng; sản phẩm ngừng bán; phân cấp danh mục |
| Đơn hàng | Dịch vụ đặt hàng | orderId | Đơn thiếu khách, thiếu dòng hàng, tổng tiền sai |
| Thanh toán | Cổng thanh toán | providerTransactionId, orderId | Callback lặp, thanh toán đến muộn, trạng thái mâu thuẫn |
| Tồn kho | Hệ thống kho | warehouseId + SKU | Số lượng âm, bản cập nhật cũ, nhiều nguồn cùng sửa |
| Sự kiện đơn hàng | Dịch vụ vận hành | orderEventId, orderId | Thời gian sai, thiếu sự kiện, sự kiện đến sai thứ tự |

Không phải nguồn nào cũng “đúng” cho mọi trường. Ví dụ, cổng thanh toán có thể là nguồn xác nhận giao dịch đã thành công; hệ thống đặt hàng lại là nguồn xác định danh sách sản phẩm và giá đã chốt. Nếu hai hệ thống bất đồng, cần quy tắc hòa giải và người chịu trách nhiệm.

### 8.2. Quy tắc dữ liệu cần ghi nhận

1. **Khóa ổn định:** Chọn định danh không thay đổi theo tên hiển thị, số điện thoại hay vị trí bản ghi trong tệp nguồn.
2. **Kiểu và đơn vị:** Quy định số tiền, số lượng, múi giờ, dạng thời gian, mã trạng thái, cách biểu diễn giá trị trống.
3. **Tính duy nhất và chống nạp trùng:** Xác định khóa nghiệp vụ và cơ chế xử lý khi tải lại cùng bản ghi hoặc nhận cùng sự kiện nhiều lần.
4. **Tính đầy đủ:** Chốt trường bắt buộc cho từng trạng thái nghiệp vụ. Chẳng hạn, đơn đã xác nhận phải có ít nhất một dòng hợp lệ.
5. **Tham chiếu hợp lệ:** Quyết định cách xử lý dòng đơn trỏ đến SKU không còn tồn tại hoặc bản ghi thanh toán trỏ tới đơn chưa được đồng bộ.
6. **Dữ liệu đến muộn:** Xử lý cập nhật đến không theo thứ tự thời gian; không để sự kiện cũ ghi đè trạng thái mới mà không có quy tắc.
7. **Lịch sử và thời hạn lưu:** Dữ liệu nào phải giữ để đối soát, dữ liệu nào có thể xóa theo chính sách và yêu cầu pháp lý áp dụng?
8. **Bảo mật:** Phân loại dữ liệu cá nhân, giới hạn trường được truy cập, che hoặc mã hóa dữ liệu phù hợp; không đưa dữ liệu nhạy cảm vào nhật ký không được bảo vệ.

Các quy tắc này quyết định cách làm sạch, chuyển đổi và tải dữ liệu sau này. Ví dụ, nếu không biết khóa nào dùng để chống trùng, việc nhập lại một tệp đơn hàng có thể tạo ra đơn giả trùng và làm sai thống kê.

## 9. Quy trình thực hành theo từng bước

### Bước 1. Xác định ranh giới và mục tiêu

Nêu rõ hệ thống phục vụ ai, bao gồm nghiệp vụ nào và không bao gồm nghiệp vụ nào. Ví dụ, phiên bản đầu chỉ phục vụ đặt hàng, thanh toán, tra cứu lịch sử và báo cáo doanh thu; quản lý vận chuyển liên tỉnh có thể thuộc hệ thống khác nhưng cung cấp sự kiện trạng thái.

### Bước 2. Phác họa luồng nghiệp vụ

Viết các hành động theo trình tự:

~~~text
Khach xem san pham
    -> Tao don hang
    -> Ghi nhan cac dong hang va gia ban
    -> Thu thanh toan
    -> Xac nhan thanh toan
    -> Cap nhat trang thai / ton kho theo quy tac
    -> Khach tra cuu don
    -> Nhan vien va bao cao doc du lieu
~~~

Mỗi mũi tên là một cơ hội phát hiện thực thể, sự kiện, liên kết hoặc quy tắc cập nhật còn thiếu. Nếu giao hàng và hoàn tiền có trong phạm vi, bổ sung các nhánh sự kiện tương ứng.

### Bước 3. Tạo bảng thực thể và từ điển thuật ngữ

Với mỗi ứng viên, ghi:

- Tên nghiệp vụ thống nhất và mô tả ngắn.
- Khóa định danh, thuộc tính bắt buộc và thuộc tính tùy chọn.
- Chủ sở hữu dữ liệu, nguồn dữ liệu, quy tắc tạo và cập nhật.
- Trạng thái hợp lệ cùng các chuyển trạng thái được phép.
- Khả năng tăng trưởng và thời hạn cần lưu giữ.

Làm rõ các cặp dễ nhầm như **“đơn đã đặt”** với **“đơn đã thanh toán”**, **“số lượng trên kệ”** với **“số lượng khả dụng”**, **“giá niêm yết”** với **“giá tại lúc mua”**.

### Bước 4. Vẽ quan hệ và kiểm tra các trường hợp biên

Ghi các quan hệ 1:1, 1:N, N:M, tính bắt buộc và vòng đời. Kiểm tra những tình huống như: khách chưa từng mua hàng, đơn bị hủy, một thanh toán được gửi lại hai lần, sản phẩm bị gỡ khỏi danh mục, hàng có nhiều kho, dữ liệu nguồn đến muộn.

Nếu một quan hệ có nhiều thuộc tính riêng (ví dụ số lượng và giá bán giữa Đơn hàng và Sản phẩm), mô tả rõ thực thể liên kết **Dòng đơn hàng**.

### Bước 5. Phỏng vấn người sử dụng để viết câu hỏi nghiệp vụ

Yêu cầu mỗi nhóm mô tả màn hình, báo cáo hoặc quyết định mà họ thực sự cần. Chuyển câu mô tả thành một dòng trong danh mục truy vấn:

| Trường cần ghi | Ví dụ |
|---|---|
| Mã và tên truy vấn | Q01 – Lịch sử đơn theo khách |
| Vai trò dùng | Khách hàng đã đăng nhập |
| Đầu vào | customerId từ phiên đăng nhập; con trỏ trang |
| Điều kiện | Chỉ đơn thuộc khách đó |
| Sắp xếp | placedAt giảm dần; orderId làm khóa phụ khi cần |
| Kết quả | 20 bản ghi: orderId, placedAt, totalAmount, status |
| Tần suất và quy mô | Ước lượng từ lượt truy cập, số đơn/khách |
| Yêu cầu chất lượng | Độ mới, thời gian phản hồi và quyền xem do nghiệp vụ xác nhận |

Các ước lượng phải được ghi rõ là giả định nếu chưa có số liệu đo đạc. Với truy vấn doanh thu, bổ sung công thức đo lường và cách xử lý hủy/hoàn tiền.

### Bước 6. Ưu tiên đường đọc/ghi và xem xét phương án lưu

Đánh dấu truy vấn nào chi phối trải nghiệm người dùng, truy vấn nào cần đọc rất nhiều bản ghi, thao tác nào cập nhật thường xuyên. Từ đó đề xuất các phương án nhúng, tham chiếu, chỉ mục hoặc tổng hợp. Đánh giá cả **chi phí ghi và đồng bộ** do phi chuẩn hóa, không chỉ tốc độ đọc.

### Bước 7. Xác nhận bằng dữ liệu mẫu

Lấy vài trường hợp đại diện và các trường hợp biên, viết kết quả kỳ vọng cho từng câu hỏi. Chẳng hạn, một đơn có hai lần thử thanh toán (một thất bại, một thành công) phải xuất hiện **một lần** trong danh sách đơn và có **hai bản ghi** trong lịch sử thanh toán. Nếu không thể diễn đạt kết quả kỳ vọng, mô hình khái niệm hoặc định nghĩa truy vấn vẫn còn thiếu.

## 10. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chuyển nguyên sơ đồ SQL thành các collection rồi mới nghĩ tới cách đọc | Truy vấn cần nhiều lần lấy dữ liệu hoặc xử lý ứng dụng phức tạp | Liệt kê đường truy cập trước, sau đó chọn cách lưu |
| Nhúng mọi quan hệ vì cho rằng NoSQL không có liên kết | Tài liệu phình to, khó phân trang, đồng bộ và quản lý lịch sử | Xem lực lượng, độ tăng, vòng đời và tần suất đọc |
| Sao chép giá hiện tại vào đơn mà không chụp giá lúc mua | Đơn cũ bị thay đổi giá trị khi danh mục cập nhật | Lưu dữ liệu lịch sử cần bất biến trong đơn |
| Gộp mọi lần thanh toán thành một trạng thái duy nhất | Mất khả năng đối soát lỗi và truy vết | Lưu lịch sử lần thử, tạo bản tóm tắt riêng nếu cần |
| Viết câu hỏi “xem sản phẩm bán chạy” mà không xác định thước đo | Các nhóm đưa ra con số khác nhau | Chốt thời gian, trạng thái, công thức và mức chi tiết |
| Không có khóa chống trùng khi tải dữ liệu | Bản ghi và chỉ số bị nhân đôi khi nhập lại | Xác định định danh nguồn và quy tắc ghi idempotent |
| Không tính tới khối lượng và phân trang | Truy vấn trả về tập dữ liệu quá lớn | Giới hạn kết quả, đặt khóa sắp xếp ổn định và thiết kế phân trang |
| Đánh đồng quan hệ nghiệp vụ với ràng buộc được CSDL tự bảo đảm | Có bản ghi mồ côi hoặc trạng thái không đồng bộ | Xác định lớp chịu trách nhiệm kiểm tra và phục hồi |
| Tối ưu báo cáo tổng hợp bằng cách quét toàn bộ dữ liệu giao dịch mỗi lần | Tăng tải và độ trễ khi dữ liệu lớn | Xem xét tổng hợp định kỳ, theo sự kiện hoặc kho phân tích riêng |

## 11. Bài tập vận dụng

**Bối cảnh:** Một nền tảng cho thuê xe cần quản lý khách thuê, xe, điểm nhận/trả, lượt đặt xe, các khoản thanh toán và trạng thái xe. Khách muốn xem các lượt đặt gần nhất; nhân viên muốn biết xe nào đang được thuê; kế toán muốn xem doanh thu theo tháng.

**Yêu cầu:**

1. Liệt kê tối thiểu sáu thực thể ứng viên, khóa định danh và hai thuộc tính quan trọng của mỗi thực thể.
2. Xác định các quan hệ 1:N và N:M (nếu có). Nêu một quan hệ cần lưu bản chụp dữ liệu để giữ lịch sử.
3. Viết ít nhất bốn câu hỏi nghiệp vụ đầy đủ đầu vào, điều kiện lọc, sắp xếp hoặc tổng hợp và kết quả.
4. Chọn một mẫu truy cập và giải thích khi nào nên nhúng, khi nào nên tham chiếu dữ liệu liên quan.

**Gợi ý lời giải:**

- Các thực thể có thể gồm **Khách thuê** (customerId, tên, liên hệ), **Xe** (vehicleId, biển số, loại xe), **Điểm giao nhận** (locationId, tên, khu vực), **Lượt đặt** (bookingId, thời gian nhận, thời gian trả), **Khoản thanh toán** (paymentId, số tiền, trạng thái), **Sự kiện trạng thái xe** (eventId, thời gian, loại trạng thái). Có thể bổ sung hợp đồng, phiếu bàn giao hoặc định giá.
- Một khách thuê có nhiều lượt đặt; một xe có nhiều lượt đặt **theo thời gian** nhưng quy tắc nghiệp vụ không được cho phép các khoảng thuê xác nhận chồng lấp của cùng xe. Một lượt đặt có thể có nhiều khoản thanh toán. Lượt đặt nên lưu **giá đã chốt** và **điểm nhận/trả đã chọn** tại thời điểm xác nhận.
- Ví dụ câu hỏi cụ thể: “Hiển thị 10 lượt đặt gần nhất của khách đã đăng nhập, sắp giảm theo createdAt”; “Tìm xe đang có lượt thuê hiệu lực tại thời điểm T trong điểm giao nhận L”; “Tổng số tiền thanh toán thành công theo tháng và điểm giao nhận trong khoảng ngày A–B”; “Liệt kê các thanh toán thất bại theo thời điểm và nhà cung cấp”.
- Màn chi tiết lượt đặt thường cần các thông tin giá và điều kiện đã chốt cùng lúc, nên có thể nhúng một bản chụp ngắn. Lịch sử trạng thái xe phát sinh liên tục có thể lưu riêng và liên kết qua vehicleId. Chọn mô hình cuối cùng sau khi đo kích thước, tần suất truy vấn và yêu cầu nhất quán.

Lời giải có nhiều khả năng hợp lệ. Điểm quan trọng là **giải thích bằng quan hệ, vòng đời và mẫu truy cập**, thay vì chỉ liệt kê collection.

## 12. Bộ tài liệu đầu ra trước khi thiết kế và nạp dữ liệu

Kết thúc bước phân tích, nhóm nên có bốn hiện vật có thể dùng chung:

1. **Danh mục thực thể và từ điển dữ liệu:** Tên, mô tả, định danh, thuộc tính, nguồn gốc, người chịu trách nhiệm và quy tắc nghiệp vụ.
2. **Sơ đồ quan hệ khái niệm:** Lực lượng, tính bắt buộc, vòng đời, dữ liệu lịch sử và các điểm đòi hỏi nhất quán.
3. **Danh mục câu hỏi nghiệp vụ:** Vai trò, đầu vào, lọc, sắp xếp, phân trang, tổng hợp, tần suất, độ mới, độ trễ, mức ưu tiên và quyền truy cập.
4. **Ma trận truy vấn – dữ liệu – nguồn:** Câu hỏi nào cần thực thể và trường nào, dữ liệu từ hệ thống nào, các quy tắc chất lượng và xử lý trùng lặp trước khi tải.

Những hiện vật này là cầu nối giữa người hiểu nghiệp vụ và người triển khai hệ thống. Chúng giúp lựa chọn kiểu cơ sở dữ liệu NoSQL, thiết kế cấu trúc lưu, chỉ mục và quy trình nạp dữ liệu dựa trên nhu cầu có thể kiểm chứng. Khi nghiệp vụ thay đổi, cập nhật câu hỏi và quy tắc trước, rồi mới đánh giá tác động tới mô hình dữ liệu.
