# Bắt đầu từ câu hỏi phân tích, quy trình nghiệp vụ và độ hạt

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, thiết kế dữ liệu không chỉ là chuyển thực thể và quan hệ thành bảng, khóa và chỉ mục. Khi xây dựng hệ thống phân tích, câu hỏi đầu tiên **không nên** là “nguồn có những bảng nào để sao chép?”, mà là “**người dùng muốn ra quyết định gì, sự kiện nghiệp vụ nào tạo ra số liệu, và một dòng dữ liệu phân tích đại diện cho điều gì?**”

Bài học thuộc chương **Mô hình phân tích** này giúp bạn:

- Đi từ **câu hỏi phân tích** tới định nghĩa KPI, quy trình nghiệp vụ, dữ liệu cần thu thập và giới hạn của câu trả lời.
- Chọn đúng **độ hạt** (*grain*) của bảng sự kiện (*fact table*) trước khi chọn số đo và chiều phân tích.
- Phân biệt **transaction fact**, **periodic snapshot**, **accumulating snapshot** và **factless fact**.
- Xác định **measure**, **dimension**, khóa nghiệp vụ, khóa thay thế và ngữ nghĩa thời gian.
- Tránh các lỗi **đếm trùng, nhân doanh thu khi JOIN, cộng sai số dư hoặc tính trung bình sai**.
- Phác thảo star schema, SQL truy vấn KPI, phép thử chất lượng dữ liệu và đối soát với nguồn.
- So sánh mô hình phân tích với mô hình giao dịch, document và đồ thị để chọn cấu trúc phù hợp, dễ kiểm chứng và tiến hóa.

## 1. Ba quyết định phải chốt theo đúng thứ tự

Một luồng thiết kế phân tích vững chắc:

~~~text
Câu hỏi quyết định
    ↓
Quy trình nghiệp vụ và sự kiện đo lường
    ↓
Độ hạt: chính xác một dòng fact đại diện cho điều gì?
    ↓
Measures và dimensions phù hợp với độ hạt
    ↓
Lược đồ, nguồn dữ liệu, khóa và quy tắc lịch sử
    ↓
Truy vấn, đối soát, kiểm thử và tối ưu vật lý
~~~

Không nên đảo ngược thành:

~~~text
Có bảng orders, customers, products
    ↓
JOIN tất cả
    ↓
Đặt tên kết quả là "data mart"
    ↓
Hy vọng mọi KPI đều tính đúng
~~~

Cách thứ hai dễ làm lẫn lộn **một đơn hàng** với **một dòng hàng**, **một khoản thanh toán**, **một lần giao hàng** hoặc **một lần hoàn trả**. Những đối tượng đó đều liên quan cùng đơn hàng nhưng không có cùng độ hạt.

> Nguyên tắc trung tâm: **Khai báo độ hạt bằng một câu rõ ràng trước khi chọn các cột cho bảng fact.**

## 2. Bắt đầu bằng câu hỏi kinh doanh, không bắt đầu bằng tên bảng

Giả sử nhà bán lẻ muốn xem hiệu quả kinh doanh. Các yêu cầu ban đầu:

1. Doanh số đặt hàng theo tháng và danh mục sản phẩm là bao nhiêu?
2. Số lượng đơn được đặt mỗi ngày là bao nhiêu?
3. Tỷ lệ đơn giao đúng hẹn của từng đơn vị vận chuyển là bao nhiêu?
4. Doanh thu ròng sau hoàn trả là bao nhiêu?
5. Tỷ lệ chuyển đổi từ lượt truy cập sang mua hàng là bao nhiêu?

Năm câu hỏi này **không cùng một fact table** và có thể không cùng nguồn dữ liệu.

| Câu hỏi | Quy trình nghiệp vụ | Đối tượng được đếm/đo | Vấn đề cần định nghĩa |
|---|---|---|---|
| Giá trị hàng được đặt theo tháng, danh mục | Đặt hàng | Dòng hàng tại thời điểm đơn được xác nhận | Giá trước/sau giảm giá? Thuế, phí giao hàng, tiền tệ? |
| Số đơn theo ngày | Đặt hàng | Một đơn hàng được xác nhận | Có tính đơn hủy sau đó không? Ngày tạo hay ngày xác nhận? |
| Tỷ lệ giao đúng hẹn | Thực hiện giao hàng | Đơn giao, kiện hàng hay chuyến giao? | Một đơn có nhiều kiện; mốc hứa hẹn và thời điểm hoàn tất? |
| Giá trị ròng sau trả hàng | Bán hàng và hoàn trả | Giao dịch bán và giao dịch hoàn riêng | Dựa trên ngày bán hay ngày hoàn? Khoản trả một phần? |
| Tỷ lệ chuyển đổi | Duyệt web và mua hàng | Phiên truy cập, người dùng hay lượt xem? | Cửa sổ quy đổi, bot, nhiều thiết bị và nhận dạng khách? |

Chẳng hạn, bảng **dòng hàng khi xác nhận đơn** có thể trả lời câu hỏi thứ nhất. Nó **không** đủ để tính chính xác tỷ lệ chuyển đổi nếu không có dữ liệu lượt truy cập hoặc phiên làm **mẫu số**.

### Định nghĩa KPI trước khi triển khai

Một KPI cần ít nhất:

| Thuộc tính KPI | Câu hỏi phải trả lời |
|---|---|
| Tên và mục đích | Chỉ số này hỗ trợ quyết định nào? |
| Tử số và mẫu số | Đếm cái gì; có cần chia hay không? |
| Tập sự kiện | Sự kiện nào thuộc phạm vi, sự kiện nào bị loại? |
| Ngày/giờ | Lấy thời điểm xảy ra, ghi nhận, thanh toán hay giao xong? |
| Độ hạt | Một hàng dữ liệu gốc đại diện cho gì? |
| Chiều phân tích | Theo sản phẩm, khách, địa bàn, kênh, ngày nào? |
| Tiền tệ/đơn vị | Có thể cộng trực tiếp hay cần đổi đơn vị? |
| Lịch sử | Nhóm theo danh mục hiện tại hay danh mục tại lúc mua? |
| Độ trễ dữ liệu | Báo cáo cập nhật tức thời, theo giờ hay mỗi ngày? |
| Quy tắc chỉnh sửa | Sự kiện đến muộn, hủy, hoàn, điều chỉnh xử lý ra sao? |

Ví dụ: “doanh thu” có thể được dùng để chỉ **giá trị đơn đặt**, **giá trị đã thanh toán**, **giá trị đã ghi nhận kế toán** hoặc **giá trị sau hoàn trả**. Chúng không tự động bằng nhau. Trong ví dụ dưới đây, ta sẽ dùng tên chính xác **giá trị hàng được đặt sau giảm giá** (*booked merchandise amount*) để tránh khẳng định sai đây là doanh thu kế toán.

## 3. Xác định quy trình nghiệp vụ và sự kiện thực sự tạo số liệu

Một đơn hàng có thể trải qua các giai đoạn:

~~~mermaid
flowchart LR
    A["Tạo giỏ"] --> B["Xác nhận đơn"]
    B --> C["Thanh toán"]
    C --> D["Đóng gói / giao"]
    D --> E["Giao thành công"]
    E --> F["Có thể hoàn hàng"]
~~~

Mỗi bước có thể có thời điểm, khóa, mức hạt và số đo riêng:

| Quy trình | Ví dụ sự kiện | Fact có thể cần |
|---|---|---|
| Đặt hàng | Xác nhận một đơn gồm nhiều dòng | `fact_order_lines`, `fact_orders` tùy câu hỏi |
| Thanh toán | Một lần capture/hoàn tiền | `fact_payment_transactions` |
| Thực hiện đơn | Kiện hàng được xuất kho/giao | `fact_shipments` hoặc snapshot quy trình giao |
| Hoàn trả | Một dòng hàng được hoàn một phần | `fact_return_lines` |
| Tồn kho | Số lượng tồn tại cuối ngày của một kho–sản phẩm | `fact_inventory_daily` |
| Duyệt web | Một lần xem trang hoặc một phiên truy cập | `fact_pageviews` hoặc `fact_sessions` |

**Quy trình nghiệp vụ** không nhất thiết tương ứng một bảng nguồn. Ví dụ, sự kiện xác nhận đơn có thể được tạo từ một transaction ghi vào `orders` và `order_items`, phát qua event stream, rồi bổ sung dữ liệu khách/sản phẩm. Ngược lại, một bảng nguồn `orders` có thể lưu cả thời điểm xác nhận, thanh toán, đóng gói và giao hàng; nhưng các phép đo ở từng bước vẫn có ngữ nghĩa khác nhau.

### Một quy trình, nhiều loại thời gian

Đừng gọi tất cả là `date`. Ví dụ:

- `created_at`: đơn được khởi tạo, có thể chưa xác nhận.
- `confirmed_at`: đơn được đặt/xác nhận.
- `paid_at`: khoản thanh toán được xác nhận.
- `shipped_at`: hàng bắt đầu vận chuyển.
- `delivered_at`: hoàn tất giao.
- `ingested_at`: hệ phân tích nhận được dữ liệu, **không nhất thiết là thời điểm nghiệp vụ xảy ra**.

Một câu hỏi “giá trị hàng đặt theo tháng” cần chỉ định rõ tháng của `confirmed_at` hay một mốc khác. Sử dụng tháng của `ingested_at` có thể làm dịch chuyển các giao dịch đến muộn sang kỳ sai.

## 4. Độ hạt (*grain*) là hợp đồng của bảng fact

**Độ hạt** trả lời câu: **“Chính xác một dòng của bảng này đại diện cho một đối tượng, sự kiện hoặc lát cắt thời gian nào?”**

Ví dụ:

~~~text
fact_order_lines:
    Một dòng ứng với một (order_id, line_no)
    tại thời điểm đơn được xác nhận lần đầu.

fact_payments:
    Một dòng ứng với một giao dịch tiền thực tế
    có payment_transaction_id duy nhất.

fact_inventory_daily:
    Một dòng ứng với một (snapshot_date, warehouse_id, product_id)
    tại thời điểm chốt tồn kho trong ngày.
~~~

Đây không chỉ là lời mô tả: độ hạt quyết định **khóa duy nhất**, số dòng được phép tồn tại, nghĩa của measure, cách JOIN và các phép kiểm thử.

### Tại sao phải ghi cả thời điểm vào câu khai báo?

“Một dòng cho một đơn hàng” chưa đủ nếu bản ghi được cập nhật nhiều lần:

- Bảng **trạng thái hiện hành**: mỗi đơn một dòng, giá trị thay đổi theo thời gian.
- Bảng **sự kiện chuyển trạng thái**: mỗi lần thay đổi trạng thái một dòng.
- Bảng **snapshot hằng ngày**: mỗi đơn một dòng **mỗi ngày**.
- Bảng **accumulating snapshot**: mỗi đơn một dòng với nhiều mốc thời gian được cập nhật khi quy trình tiến triển.

Tất cả có thể chứa `order_id`, nhưng **độ hạt và ý nghĩa phân tích khác nhau**.

### Một bảng fact chỉ nên có một độ hạt

Không đưa các số đo ở mức **toàn đơn hàng** vào từng dòng của bảng fact ở mức **dòng đơn** rồi vô tư `SUM`. Ví dụ `order_shipping_fee = 40.000` cho đơn có ba dòng: nếu chép 40.000 vào cả ba dòng, `SUM(order_shipping_fee)` tạo thành 120.000, gấp ba giá trị thật.

Những lựa chọn đúng hơn:

1. Giữ phí vận chuyển ở **fact cấp đơn**.
2. Nếu nghiệp vụ cần phân bổ phí về từng dòng, định nghĩa **quy tắc phân bổ** rõ ràng (theo tỷ trọng giá trị, khối lượng, số lượng...) và đặt tên `allocated_shipping_fee`; kiểm tra tổng phân bổ bằng phí toàn đơn.
3. Tạo truy vấn từ hai fact ở **mức tổng hợp tương thích** trước khi ghép, không JOIN thẳng các dòng chi tiết khác độ hạt.

## 5. Ví dụ từng bước: giá trị hàng đặt theo danh mục và tháng

Đặt yêu cầu:

> “Với các đơn được xác nhận, xem tổng **giá trị hàng sau giảm giá** theo tháng xác nhận đơn và danh mục sản phẩm **tại thời điểm đặt**. Không tính phí vận chuyển, thuế, thanh toán hay hoàn trả. Báo cáo chốt theo múi giờ kinh doanh đã quy định.”

Giả định nghiệp vụ:

- `order_id` là duy nhất trong phạm vi hệ thống được xét.
- `line_no` duy nhất **trong một đơn**.
- Tại thời điểm xác nhận đơn, mỗi dòng có một sản phẩm, số lượng, đơn giá và chiết khấu dòng.
- Một dòng đơn được ghi nhận **một lần ở thời điểm xác nhận**; nếu có sửa/hủy/hoàn về sau, dữ liệu điều chỉnh đi vào các quy trình/fact phù hợp, không âm thầm viết đè sự kiện lịch sử.
- Các khoản tiền trong ví dụ dùng **cùng một đơn vị tiền tệ**, với quy tắc làm tròn đã thống nhất.

### 5.1. Từ câu hỏi tới độ hạt

Độ hạt phù hợp:

~~~text
Một dòng fact_order_lines =
    một dòng hàng (order_id, line_no)
    trong một đơn đã được xác nhận,
    được ghi nhận theo thông tin tại thời điểm xác nhận.
~~~

**Khóa nghiệp vụ của dòng fact** là `(order_id, line_no)` theo giả định này.

### 5.2. Chọn chiều (*dimensions*)

| Dimension | Ý nghĩa | Câu hỏi hỗ trợ |
|---|---|---|
| Ngày xác nhận đơn | Ngày kinh doanh rút ra từ `confirmed_at` | Theo tháng/quý/ngày |
| Sản phẩm | Định danh và thuộc tính sản phẩm | Theo sản phẩm/danh mục |
| Khách hàng | Khách gắn với đơn tại thời điểm xác nhận | Theo phân khúc/địa bàn |
| Cửa hàng/kênh (nếu có) | Nguồn bán/đơn vị kinh doanh | Theo kênh, cửa hàng |
| `order_id` | Định danh giao dịch phục vụ drill-through | Đếm đơn distinct, tra soát |

`order_id` thường được giữ ngay trong fact như **degenerate dimension** (*chiều suy biến*): nó có giá trị dùng để lọc, nhóm và tra cứu nhưng không nhất thiết cần một bảng dimension chỉ chứa mỗi khóa.

**Chú ý lịch sử:** để báo cáo theo danh mục sản phẩm **tại thời điểm đặt**, phải lưu được phiên bản dimension tại thời điểm sự kiện (chẳng hạn SCD Type 2), hoặc snapshot thuộc tính có kiểm soát. Một `dim_product` chỉ chứa danh mục **hiện tại** sẽ khiến báo cáo lịch sử bị phân loại lại khi sản phẩm đổi danh mục.

### 5.3. Chọn số đo (*measures*)

Ví dụ:

~~~text
quantity
unit_price_at_order
line_discount_amount
booked_amount = quantity × unit_price_at_order
                - line_discount_amount
~~~

`booked_amount` là giá trị hàng được đặt sau giảm giá, **không tự động là tiền đã nhận hoặc doanh thu đã ghi nhận**. Nếu đơn hủy sau khi xác nhận, dòng fact đặt hàng ban đầu vẫn tồn tại theo định nghĩa, còn báo cáo **doanh thu ròng** cần quy tắc xử lý hủy/hoàn và các fact khác.

### 5.4. Dữ liệu minh họa

| order_id | line_no | confirmed_day | category_at_order | quantity | unit_price | line_discount | booked_amount |
|---|---:|---|---|---:|---:|---:|---:|
| D01 | 1 | 2026-11-01 | Sách | 2 | 100.000 | 0 | 200.000 |
| D01 | 2 | 2026-11-01 | Phụ kiện | 1 | 50.000 | 10.000 | 40.000 |
| D02 | 1 | 2026-11-02 | Sách | 1 | 150.000 | 0 | 150.000 |

Với ba dòng trên:

- **Tổng giá trị hàng được đặt:** \(200.000+40.000+150.000=390.000\).
- **Số dòng hàng:** 3.
- **Số đơn được xác nhận:** 2, không phải 3.
- **Giá trị hàng đặt thuộc danh mục Sách:** \(200.000+150.000=350.000\).
- **Số sản phẩm/đơn vị được đặt:** \(2+1+1=4\), nếu đơn vị `quantity` đồng nhất và phép cộng có ý nghĩa.

Đây là minh họa cho sự khác nhau giữa **đếm dòng**, **đếm đơn** và **cộng giá trị tiền** trên cùng độ hạt.

## 6. Các loại fact table và cách chọn đúng

### 6.1. Transaction fact — một dòng cho một giao dịch/sự kiện

Ví dụ:

~~~text
fact_payment_transactions(
    payment_transaction_id,
    order_id,
    transaction_time,
    transaction_type,
    amount
)
~~~

**Grain:** một giao dịch capture, refund hoặc điều chỉnh có ID riêng. Một đơn có thể có **nhiều** giao dịch thanh toán, nên không được coi `order_id` là khóa duy nhất.

Phù hợp khi câu hỏi là “đã phát sinh bao nhiêu giao dịch, số tiền di chuyển bao nhiêu và khi nào?”. Nếu cùng một giao dịch bị nguồn gửi lại, xử lý nạp dữ liệu phải **idempotent** theo định danh giao dịch.

### 6.2. Periodic snapshot — một dòng cho mỗi đối tượng trong mỗi kỳ

Ví dụ:

~~~text
fact_inventory_daily(
    snapshot_date_key,
    warehouse_key,
    product_key,
    on_hand_quantity
)
~~~

**Grain:** một `(ngày chốt, kho, sản phẩm)` ở thời điểm chốt đã quy định.

Phù hợp cho tồn kho cuối ngày, số dư tài khoản cuối tháng, số lượng khách hàng hoạt động tại kỳ. Dữ liệu có thể có **kỳ không có giao dịch** nhưng vẫn cần một snapshot để thể hiện trạng thái.

**Không cộng tồn kho qua các ngày** nếu mục đích là tồn kho tại một thời điểm. Ví dụ tồn kho 10 đơn vị cuối thứ Hai và 10 đơn vị cuối thứ Ba **không có nghĩa** tồn kho 20 đơn vị.

### 6.3. Accumulating snapshot — một dòng đại diện cho tiến trình nhiều mốc

Ví dụ:

~~~text
fact_order_fulfillment(
    order_id,
    confirmed_date_key,
    packed_date_key,
    shipped_date_key,
    delivered_date_key,
    promised_delivery_date_key
)
~~~

**Grain:** một **đơn vị quy trình fulfillment** xuyên suốt các mốc, ví dụ một đơn hàng nếu nghiệp vụ bảo đảm một đơn có đúng một luồng giao, hoặc một **kiện hàng** nếu đơn có thể giao nhiều kiện.

Một dòng **được cập nhật** khi quy trình tiến triển; phù hợp để tính thời gian xử lý giữa các mốc. Chọn sai đối tượng theo dõi là lỗi thường gặp: nếu một đơn có ba kiện giao ba ngày khác nhau, `order_id` **không** còn đủ làm grain cho “một lượt giao hàng”.

### 6.4. Factless fact — ghi nhận một sự kiện/quan hệ không có measure số

Ví dụ:

~~~text
fact_event_attendance(
    event_id,
    participant_id,
    attendance_date_key
)
~~~

**Grain:** một sự kiện tham dự hợp lệ của một người ở một hoạt động theo quy tắc định danh đã xác nhận. Có thể đếm số lượt tham dự bằng `COUNT(*)`; không bắt buộc có cột tiền hay số lượng.

Factless fact cũng có thể ghi **coverage** (những tổ hợp được phép xảy ra), dùng để đối chiếu với sự kiện thực tế; phải phân biệt rõ “có quyền tham dự” và “đã tham dự”.

### Bảng so sánh nhanh

| Loại fact | Một dòng là gì? | Thay đổi theo thời gian | Ví dụ measure |
|---|---|---|---|
| Transaction | Một sự kiện/chi tiết giao dịch | Thường thêm sự kiện mới | `amount`, `quantity` |
| Periodic snapshot | Một đối tượng ở một kỳ chốt | Thêm snapshot cho kỳ mới | `on_hand_quantity`, `balance` |
| Accumulating snapshot | Một trường hợp quy trình theo nhiều mốc | Cập nhật cùng dòng khi đạt mốc | `days_to_ship`, `days_to_deliver` |
| Factless | Một sự kiện/quan hệ không cần measure số | Thường thêm hoặc cập nhật trạng thái theo định nghĩa | Đếm sự kiện bằng `COUNT(*)` |

**Quy tắc lựa chọn:** chọn cấu trúc theo **câu hỏi thời gian và độ hạt**, không theo việc bảng nguồn trông giống “transaction” hay “snapshot”.

## 7. Measures: cộng được hay không phụ thuộc độ hạt

Không phải cột số nào cũng cộng được. Trong mô hình phân tích, cần phân biệt:

| Measure | Loại tính cộng | Hướng xử lý |
|---|---|---|
| `booked_amount` ở dòng đặt hàng | **Additive** theo các chiều phù hợp khi cùng tiền tệ và không nhân bản dòng | `SUM(booked_amount)` |
| `quantity` | Thường additive khi đơn vị đo tương thích | `SUM(quantity)`, tránh cộng kg với cái |
| `on_hand_quantity` cuối ngày | **Semi-additive**: cộng được theo kho/sản phẩm trong cùng thời điểm, không cộng xuyên ngày | Lấy ngày chốt phù hợp rồi `SUM` |
| `account_balance` | Semi-additive qua một số chiều, không qua thời gian | Điểm cuối kỳ hoặc diễn biến có định nghĩa |
| `unit_price` | **Non-additive** | Tính theo ngữ cảnh, không `SUM(unit_price)` |
| `discount_rate` | Non-additive | Không cộng hoặc lấy trung bình tùy tiện các tỷ lệ |
| `distinct_customers` | Không cộng trực tiếp qua các tập trùng nhau | `COUNT(DISTINCT customer_id)` trên phạm vi phù hợp |
| `conversion_rate` | Tỷ lệ không cộng được | Tính tổng tử số / tổng mẫu số tương thích |

### Ví dụ trung bình đúng

Hai dòng hàng:

~~~text
Dòng 1: quantity = 1, unit_price = 100
Dòng 2: quantity = 9, unit_price = 10
~~~

Trung bình đơn giá **không trọng số** là \((100+10)/2=55\), nhưng đơn giá bình quân **theo số lượng** là:

\[
\frac{1\times100+9\times10}{1+9}=\frac{190}{10}=19.
\]

Hai chỉ số trả lời hai câu hỏi khác nhau. Với `line_discount_amount`, đơn giá thực thu trên một đơn vị có thể được xác định theo cách khác nữa; cần định nghĩa trước khi xây KPI.

### Một ví dụ về tỷ lệ chuyển đổi

Nếu kênh A có 10 đơn từ 100 phiên truy cập và kênh B có 5 đơn từ 10 phiên, tỷ lệ tương ứng là 10% và 50%. Tỷ lệ tổng **không phải** trung bình đơn giản 30%, mà:

\[
\frac{10+5}{100+10}\approx13{,}64\%.
\]

Ví dụ chỉ hợp lệ khi “đơn” và “phiên” đã được gắn với cùng phạm vi quy đổi; nếu một phiên tạo nhiều đơn hoặc có cửa sổ quy đổi nhiều ngày, cần sửa định nghĩa tử số và quy tắc gán nguồn. **Không thể tính một tỷ lệ đúng chỉ bằng phép chia hai bảng không có ngữ nghĩa tương thích.**

## 8. Thiết kế star schema từ grain đã chọn

Một **star schema** thường có fact ở giữa, nối trực tiếp đến các dimension mô tả ngữ cảnh:

~~~mermaid
flowchart LR
    D["dim_date"] --> F["fact_order_lines"]
    C["dim_customer"] --> F
    P["dim_product"] --> F
    F --> O["order_id, line_no\n(booked_amount, quantity, discount)"]
~~~

**Fact** giữ khóa tới dimension và các measure của **một sự kiện ở grain đã khai báo**. **Dimension** giữ những thuộc tính phục vụ lọc, nhóm và hiển thị như danh mục sản phẩm, nhóm khách, vùng địa lý.

### Surrogate key và business key

- `product_id` là **khóa nghiệp vụ** ổn định trong nguồn theo phạm vi đã xác nhận.
- `product_key` là **khóa thay thế** (*surrogate key*) của bản ghi dimension trong kho phân tích.
- Khi cần **lịch sử SCD Type 2**, cùng một `product_id` có thể có nhiều phiên bản dimension, mỗi phiên bản có một `product_key` khác nhau.
- `(order_id,line_no)` vẫn có thể là **business key của dòng fact**, dù dimension dùng surrogate key.

Không dùng surrogate key để che lấp việc **khóa nghiệp vụ bị trùng không hợp lệ**. Cần kiểm thử duy nhất theo grain.

### Ví dụ DDL PostgreSQL đơn giản

Đoạn SQL dưới đây dùng **dimension Type 1** (chứa trạng thái hiện hành) để trình bày cấu trúc cơ bản. Nếu cần báo cáo danh mục **tại thời điểm đặt**, phải áp dụng cách xử lý lịch sử ở phần tiếp theo; không nên đọc nhầm `category_name` hiện tại thành danh mục lịch sử.

~~~sql
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,       -- Ví dụ: 20261101
    calendar_date DATE NOT NULL UNIQUE,
    calendar_year INTEGER NOT NULL,
    calendar_month INTEGER NOT NULL CHECK (calendar_month BETWEEN 1 AND 12)
);

CREATE TABLE dim_customer (
    customer_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id VARCHAR(40) NOT NULL UNIQUE,
    customer_segment VARCHAR(80)
);

CREATE TABLE dim_product (
    product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id VARCHAR(40) NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    category_name VARCHAR(120) NOT NULL
);

CREATE TABLE fact_order_lines (
    order_id VARCHAR(40) NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    confirmed_date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key BIGINT NOT NULL REFERENCES dim_customer(customer_key),
    product_key BIGINT NOT NULL REFERENCES dim_product(product_key),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_order NUMERIC(18,2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    line_discount_amount NUMERIC(18,2) NOT NULL
        CHECK (line_discount_amount >= 0),
    booked_amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    CHECK (line_discount_amount <= quantity * unit_price_at_order),
    CHECK (booked_amount =
           quantity * unit_price_at_order - line_discount_amount)
);

CREATE INDEX idx_fact_order_lines_date_product
    ON fact_order_lines (confirmed_date_key, product_key);
~~~

Đây là **mô hình minh họa**, không tự giải quyết mọi yêu cầu:

- `NUMERIC` và công thức giả định quy tắc làm tròn phù hợp; thuế, phí vận chuyển, hủy, hoàn không nằm trong `booked_amount` này.
- Một tiền tệ duy nhất được giả định. Nếu có nhiều tiền tệ, cần `currency_code` và chiến lược quy đổi có tỷ giá/thời điểm được xác nhận.
- `customer_id` và `product_id` được giả định là duy nhất toàn phạm vi dimension; nếu nguồn có nhiều tenant, khóa phải thêm phạm vi hoặc được chuẩn hóa định danh toàn cục.
- `fact_order_lines` lưu bản ghi **tại xác nhận đơn**; nếu nguồn chỉ có trạng thái hiện hành bị cập nhật, cần xây dựng pipeline/sự kiện phù hợp để không làm sai lịch sử.
- Chỉ mục thực tế cần dựa trên các truy vấn, độ chọn lọc và kế hoạch thực thi; không tự tạo một index cho mọi khóa ngoại mà chưa đo.

### Truy vấn tổng giá trị hàng đặt theo tháng và danh mục

~~~sql
SELECT
    DATE_TRUNC('month', d.calendar_date)::date AS order_month,
    p.category_name,
    SUM(f.booked_amount) AS booked_amount,
    SUM(f.quantity) AS units_ordered,
    COUNT(*) AS order_lines,
    COUNT(DISTINCT f.order_id) AS orders_with_this_category
FROM fact_order_lines AS f
JOIN dim_date AS d
  ON d.date_key = f.confirmed_date_key
JOIN dim_product AS p
  ON p.product_key = f.product_key
GROUP BY
    DATE_TRUNC('month', d.calendar_date)::date,
    p.category_name
ORDER BY order_month, p.category_name;
~~~

`orders_with_this_category` đếm số **đơn có ít nhất một dòng trong danh mục đó**. Một đơn có dòng ở hai danh mục sẽ được đếm trong **cả hai nhóm**. Vì vậy **không được cộng số đơn của từng danh mục** để suy ra tổng số đơn toàn hệ thống nếu các nhóm có thể chồng nhau.

Tương tự, với `dim_product` Type 1, danh mục trong truy vấn là **danh mục hiện tại**. Muốn giữ lịch sử tại lúc đặt, cần phiên bản dimension đúng thời điểm.

## 9. Lịch sử dimension: trả lời “tại thời điểm đó” hay “như hiện nay”?

Giả sử sản phẩm `SP01` từng thuộc danh mục “Phụ kiện”, rồi được chuyển sang “Điện tử”.

Hai báo cáo đều có thể hợp lệ:

1. **Theo danh mục hiện tại:** toàn bộ giao dịch cũ của `SP01` được nhóm vào “Điện tử”.
2. **Theo danh mục tại lúc đặt:** giao dịch cũ trước thời điểm chuyển vẫn nằm ở “Phụ kiện”.

Nếu yêu cầu là câu thứ hai, dimension Type 1 không đủ thông tin nếu ghi đè category.

### SCD Type 2 cho thuộc tính lịch sử

Ví dụ các phiên bản:

| product_key | product_id | category_name | valid_from | valid_to |
|---:|---|---|---|---|
| 101 | SP01 | Phụ kiện | 2025-01-01 | 2026-07-01 |
| 205 | SP01 | Điện tử | 2026-07-01 | vô hạn |

Quy ước khoảng hiệu lực là **nửa mở**:

\[
[\text{valid\_from},\text{valid\_to})
\]

tức là bao gồm đầu, không bao gồm cuối. Không được có hai phiên bản cùng `product_id` có khoảng hiệu lực **chồng lấn** trong ngữ cảnh một lịch sử tuyến tính.

Khi nạp một dòng fact có `confirmed_at = 2026-06-15`, tra cứu phiên bản `product_key = 101`; với dòng có `confirmed_at = 2026-08-10`, dùng `product_key = 205`.

**Điểm quan trọng:** `product_key` trong fact phải được gắn với **phiên bản đúng thời điểm nghiệp vụ**. Một JOIN chỉ theo `product_id` với toàn bộ bảng phiên bản SCD2 có thể nhân một dòng fact thành nhiều dòng.

Ví dụ tra cứu phiên bản từ staging:

~~~sql
SELECT
    s.order_id,
    s.line_no,
    v.product_key
FROM staging_confirmed_order_lines AS s
JOIN dim_product_version AS v
  ON v.product_id = s.product_id
 AND s.confirmed_at >= v.valid_from
 AND (v.valid_to IS NULL OR s.confirmed_at < v.valid_to);
~~~

Truy vấn trên **chỉ là minh họa nguyên tắc tra cứu**; bảng `dim_product_version` cần được định nghĩa, kiểm soát duy nhất phiên bản phù hợp và xử lý giao dịch tới muộn. Nếu một sự kiện không khớp phiên bản nào hoặc khớp nhiều phiên bản, đó là vấn đề chất lượng dữ liệu cần xử lý trước khi tổng hợp, không phải lý do chấp nhận nhân doanh thu.

### Thời gian sự kiện và thời gian nạp

Một đơn xác nhận ngày 31/10 nhưng pipeline nhận ngày 02/11 phải được xử lý theo **ngày xác nhận** nếu báo cáo theo thời điểm đặt, chứ không tự chuyển sang tháng 11. Cần thiết kế watermark, cửa sổ dữ liệu đến muộn và cơ chế chạy lại số liệu đã công bố khi thích hợp.

Nếu thông tin về danh mục tại thời điểm quá khứ cũng được chỉnh sửa hồi tố, bài toán còn có thể cần quản lý **thời gian hiệu lực nghiệp vụ** và **thời gian hệ thống biết được sự thật đó**. Không đồng nhất “lịch sử Type 2” với giải pháp hoàn chỉnh cho mọi biến động thời gian.

## 10. Bus matrix: dùng chung chiều giữa các quy trình

Khi đã biết các quy trình và độ hạt, lập **bus matrix** để thấy những dimension có thể dùng chung (*conformed dimensions*).

| Quy trình / fact | Ngày | Khách hàng | Sản phẩm | Cửa hàng | Đơn vị vận chuyển | Phương thức thanh toán |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Dòng hàng được xác nhận | ✓ | ✓ | ✓ | ✓ |  |  |
| Giao dịch thanh toán | ✓ | ✓ |  | ✓ |  | ✓ |
| Kiện hàng được giao | ✓ | ✓ | Có thể qua dòng hàng | ✓ | ✓ |  |
| Dòng hàng hoàn trả | ✓ | ✓ | ✓ | ✓ | Có thể |  |
| Tồn kho cuối ngày | ✓ |  | ✓ | ✓ / kho |  |  |
| Sự kiện phiên truy cập | ✓ | Có thể chưa biết | Có thể theo lượt xem | Kênh |  |  |

Đánh dấu “có thể” không có nghĩa được JOIN trực tiếp một dimension mà pipeline không ghi nhận. Ví dụ một giao dịch thanh toán của toàn đơn không nhất thiết gắn với **một sản phẩm**; phải có quy tắc phân bổ nếu muốn phân tích thanh toán theo danh mục sản phẩm.

**Conformed dimension** đòi hỏi định nghĩa khóa, thuộc tính và phạm vi nhất quán giữa các fact. Nếu `store_id` trong một quy trình là cửa hàng bán, nhưng trong quy trình khác là kho giao, không nên gộp hai vai trò chỉ vì tên cột giống nhau.

### Role-playing dimensions

Một `dim_date` có thể được dùng ở nhiều vai trò:

~~~text
confirmed_date_key  → dim_date
paid_date_key       → dim_date
shipped_date_key    → dim_date
delivered_date_key  → dim_date
~~~

Khi truy vấn, dùng alias khác nhau cho từng vai trò. Mỗi ngày có **nghĩa nghiệp vụ riêng**. Không gộp tất cả vào một `date_key` chung nếu câu hỏi cần nhiều mốc.

## 11. Tránh lỗi JOIN nhân bản số liệu (*fanout*)

Giả sử fact dòng hàng có một dòng:

~~~text
order_id = D01, line_no = 1, customer_id = KH01, booked_amount = 200000
~~~

Trong bảng địa chỉ khách hàng, `KH01` có ba địa chỉ. Nếu JOIN thẳng:

~~~sql
SELECT SUM(f.booked_amount)
FROM fact_order_lines AS f
JOIN dim_customer AS c
  ON c.customer_key = f.customer_key
JOIN customer_addresses AS a
  ON a.customer_id = c.customer_id;
~~~

Ở đây `customer_addresses` là bảng ví dụ bổ sung, chứa nhiều địa chỉ cho một khách. Dòng doanh số có thể **nhân thành ba** và tổng bị sai. Câu lệnh còn có thể làm **mất** các dòng khách không có địa chỉ nếu là `INNER JOIN`.

Vấn đề không được giải quyết chỉ bằng `SUM(DISTINCT booked_amount)`: hai dòng hàng thực sự khác nhau hoàn toàn có thể cùng giá trị tiền, nên `DISTINCT` trên measure sẽ **loại nhầm giá trị hợp lệ**.

### Cách xử lý đúng

Trước khi JOIN, phải xác nhận phía dimension là **duy nhất tại grain join**. Ví dụ:

- Với dimension khách hàng Type 1, `customer_key` phải định danh đúng **một dòng**.
- Với địa chỉ mặc định, cần xác nhận **tối đa một địa chỉ mặc định theo khách và thời điểm**, rồi chọn phiên bản phù hợp trước khi JOIN.
- Với một quan hệ nhiều-nhiều thực sự, có thể cần **bridge table**, quy tắc phân bổ hoặc tổng hợp từng phía ở grain tương thích.
- Với hai fact khác độ hạt, thường nên **tổng hợp độc lập** theo các chiều dùng chung rồi ghép các kết quả tổng hợp ở một grain được định nghĩa.

**Không dùng `DISTINCT` như miếng vá chung cho mọi lỗi fanout.** Nó có thể che lỗi mô hình thay vì sửa lỗi.

### Ví dụ hai quy trình không thể JOIN trực tiếp

`fact_order_lines`: 3 dòng cho đơn D01.

`fact_payment_transactions`: 2 lần thanh toán cho đơn D01.

JOIN hai bảng trên `order_id` sẽ tạo \(3\times2=6\) dòng. `SUM(fact_order_lines.booked_amount)` bị lặp hai lần; `SUM(payment_amount)` bị lặp ba lần.

Một hướng đúng nếu muốn so **tổng giá trị đặt và tổng tiền thanh toán theo đơn**:

~~~sql
WITH booked_by_order AS (
    SELECT order_id, SUM(booked_amount) AS booked_amount
    FROM fact_order_lines
    GROUP BY order_id
),
paid_by_order AS (
    SELECT order_id, SUM(payment_amount) AS payment_amount
    FROM fact_payment_transactions
    WHERE transaction_type = 'CAPTURE'
    GROUP BY order_id
)
SELECT
    b.order_id,
    b.booked_amount,
    p.payment_amount
FROM booked_by_order AS b
LEFT JOIN paid_by_order AS p
  ON p.order_id = b.order_id;
~~~

Trong ví dụ này, `payment_amount` và `transaction_type` là các cột **giả định của fact thanh toán**, không nằm trong DDL `fact_order_lines` ở trên. Quy tắc thanh toán có thể còn cả refund/reversal, nhiều tiền tệ hoặc trường hợp chưa capture; không tự suy “booked = paid”.

## 12. Thiết kế kiểm thử dữ liệu ngay từ grain

Một fact đáng tin cậy cần có những **bất biến kiểm chứng được**.

### 12.1. Một khóa nghiệp vụ chỉ một dòng tại grain đã khai báo

~~~sql
SELECT order_id, line_no, COUNT(*) AS row_count
FROM fact_order_lines
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

Với DDL có `PRIMARY KEY(order_id,line_no)`, truy vấn thông thường không trả dòng nào nếu ràng buộc đang hoạt động; nó đặc biệt hữu ích khi kiểm tra **staging trước khi nạp** hoặc dữ liệu từ hệ không cưỡng chế khóa.

Nếu trong tương lai nghiệp vụ cho phép một dòng được sửa nhiều phiên bản, đừng đơn giản bỏ `UNIQUE`: hãy định nghĩa lại grain, ví dụ **một dòng mỗi phiên bản** với `revision_no`, hoặc giữ fact gốc bất biến và ghi event điều chỉnh riêng.

### 12.2. Kiểm tra số tiền theo công thức nghiệp vụ

~~~sql
SELECT
    order_id, line_no,
    quantity, unit_price_at_order,
    line_discount_amount, booked_amount
FROM fact_order_lines
WHERE booked_amount <>
      quantity * unit_price_at_order - line_discount_amount;
~~~

Ví dụ này dùng công thức đã nêu cho **một tiền tệ và quy tắc làm tròn đơn giản**. Hệ thống có tiền tệ khác nhau, khuyến mãi nhiều cấp, thuế hay phí phân bổ phải thay công thức bằng định nghĩa KPI đã phê duyệt.

### 12.3. Kiểm tra tham chiếu dimension

~~~sql
SELECT f.order_id, f.line_no, f.product_key
FROM fact_order_lines AS f
LEFT JOIN dim_product AS p
  ON p.product_key = f.product_key
WHERE p.product_key IS NULL;
~~~

Với khóa ngoại đang được thực thi, trường hợp này thường không xuất hiện. Trong kho dữ liệu nơi FK không được cưỡng chế, hoặc khi dimension nạp chậm hơn fact, phép thử này rất quan trọng. Không nên **âm thầm bỏ các dòng fact không khớp** khi tính KPI: sẽ làm doanh số thiếu mà không có cảnh báo.

### 12.4. Đối soát nguồn với fact

Giả sử nguồn giao dịch có bảng `staging_confirmed_order_lines` với cùng grain và chứa những dòng đã xác nhận. Trước tiên phải **chuẩn hóa khóa, lọc trạng thái, xử lý trùng do nạp lại**. Sau đó mới so:

~~~sql
WITH source_totals AS (
    SELECT
        CAST(confirmed_at AS DATE) AS confirmed_day,
        COUNT(*) AS source_lines,
        SUM(quantity * unit_price_at_order - line_discount_amount)
            AS source_booked
    FROM staging_confirmed_order_lines
    GROUP BY CAST(confirmed_at AS DATE)
),
fact_totals AS (
    SELECT
        d.calendar_date AS confirmed_day,
        COUNT(*) AS fact_lines,
        SUM(f.booked_amount) AS fact_booked
    FROM fact_order_lines AS f
    JOIN dim_date AS d
      ON d.date_key = f.confirmed_date_key
    GROUP BY d.calendar_date
)
SELECT
    COALESCE(s.confirmed_day, f.confirmed_day) AS confirmed_day,
    s.source_lines,
    f.fact_lines,
    s.source_booked,
    f.fact_booked
FROM source_totals AS s
FULL OUTER JOIN fact_totals AS f
  ON f.confirmed_day = s.confirmed_day
WHERE s.source_lines IS DISTINCT FROM f.fact_lines
   OR s.source_booked IS DISTINCT FROM f.fact_booked;
~~~

**Giới hạn của ví dụ:** `CAST(confirmed_at AS DATE)` phụ thuộc timezone phiên DB. Phải chuẩn hóa ngày nguồn và `dim_date` theo **cùng múi giờ nghiệp vụ** trước khi dùng đối soát thật. Ngoài ra, phải thống nhất độ trễ nạp, thời điểm chốt, dữ liệu đến muộn, currency, filter hủy và quy tắc làm tròn. Khi các điều kiện này chưa đồng nhất, chênh lệch chưa chắc là lỗi fact.

### 12.5. Kiểm tra chất lượng dimension lịch sử

Với dimension SCD Type 2, tối thiểu kiểm tra:

- Một business key không có **hai khoảng hiệu lực chồng lấn** trong cùng phạm vi.
- Mỗi sự kiện được gán **đúng một phiên bản dimension** tại thời điểm sự kiện.
- Sự kiện không tìm thấy phiên bản có chiến lược xử lý rõ: quarantine, unknown member có theo dõi hoặc backfill.
- Khóa business không bị tái sử dụng ngoài phạm vi đã định nghĩa.

Một “unknown dimension” có thể giúp không mất dòng fact khi dữ liệu chiều tới muộn, nhưng **không được coi dữ liệu chưa phân loại là đúng** hoặc bỏ qua công việc cập nhật lại sau đó.

## 13. Chuyển yêu cầu thành tài liệu thiết kế có thể review

Một mẫu tài liệu ngắn cho từng fact:

| Thành phần | Ví dụ cho `fact_order_lines` |
|---|---|
| **Câu hỏi ưu tiên** | Giá trị hàng đặt sau giảm giá theo tháng/danh mục |
| **Quy trình** | Xác nhận đơn hàng |
| **Grain** | Một dòng cho mỗi `(order_id,line_no)` tại xác nhận đơn |
| **Sự kiện kích hoạt** | Đơn được xác nhận thành công |
| **Business key** | `order_id + line_no` |
| **Measures** | `quantity`, `line_discount_amount`, `booked_amount` |
| **Dimensions** | Ngày xác nhận, khách, sản phẩm tại thời điểm đặt |
| **Định nghĩa tiền** | Một tiền tệ báo cáo; loại trừ thuế, phí và hoàn trả |
| **Nguồn** | Sự kiện/ảnh chụp xác nhận đơn được kiểm soát |
| **Lịch sử** | Gắn phiên bản dimension đúng thời điểm |
| **Độ trễ** | Ví dụ nạp theo giờ, có xử lý dữ liệu đến muộn |
| **Kiểm thử** | Unique grain, amount formula, FK, đối soát nguồn |
| **Không dùng để trả lời** | Doanh thu kế toán, tỷ lệ chuyển đổi web nếu thiếu nguồn |

Đây là hợp đồng giữa nghiệp vụ, data engineer, analyst và nhóm vận hành. Khi một KPI đổi định nghĩa, có thể truy ra những fact, truy vấn và phép thử nào cần thay đổi.

### Những câu hỏi cần hỏi trước khi chốt

1. Cần **số liệu hiện tại** hay **đã xảy ra tại thời điểm nào đó**?
2. Tính trên **đơn**, **dòng đơn**, **thanh toán**, **lượt giao**, **lần hoàn**, hay **snapshot tồn kho**?
3. Có thực thể nào có thể xuất hiện **nhiều lần** trong một quy trình?
4. Số đo có thể cộng qua thời gian/chiều nào và không cộng qua chiều nào?
5. Mã định danh có duy nhất toàn hệ thống hay theo tenant/cửa hàng?
6. Lịch sử dimension cần tại thời điểm giao dịch hay theo phân loại hiện hành?
7. Dữ liệu tới muộn, bị sửa hoặc bị hủy sẽ xuất hiện thế nào trong báo cáo?
8. Có báo cáo nào đòi **mẫu số** nhưng nguồn mới chỉ có tử số?
9. Mốc đối soát nào chứng minh số liệu là đúng?
10. Truy vấn nào là quan trọng nhất để chọn partition, index, cluster hay materialization?

## 14. Tránh sao chép mô hình OLTP trực tiếp thành data mart

Hệ giao dịch (OLTP) thường tổ chức dữ liệu để **ghi đúng trạng thái hiện hành, tránh dư thừa và thực thi ràng buộc**. Hệ phân tích thường tổ chức quanh **quy trình và độ hạt đo lường**, tối ưu cho truy vấn tổng hợp theo nhiều chiều.

Ví dụ:

~~~text
OLTP:
    orders
    order_items
    customers
    products
    payments
    shipments

Analytics:
    fact_order_lines
    fact_payment_transactions
    fact_shipments / fulfillment_snapshot
    dim_customer
    dim_product
    dim_date
~~~

Không phải mọi bảng OLTP đều trở thành một fact hoặc dimension tương ứng. Cần xác định **sự kiện nào là dữ liệu phân tích** và **quan hệ nào có thể JOIN mà không làm sai grain**.

### Star schema, snowflake và bảng rộng

| Cách tổ chức | Thế mạnh | Điểm cần kiểm soát |
|---|---|---|
| **Star schema** | Fact–dimension rõ, dễ GROUP BY theo chiều, mức hạt đo lường minh bạch | Lịch sử dimension, fanout, conformed dimensions |
| **Snowflake** | Chuẩn hóa sâu một số dimension, chia sẻ phân cấp | Tăng số JOIN và phức tạp truy vấn |
| **One big table / bảng rộng** | Thuận tiện cho một số truy vấn cụ thể hoặc engine dạng cột | Lặp thuộc tính chiều, khó xử lý SCD, fanout khi trộn grain |
| **Data mart theo KPI** | Tối ưu báo cáo quan trọng, preaggregation | Phải ghi rõ nguồn, công thức, thời điểm làm mới |

Không có lựa chọn đúng cho mọi hệ thống. Điểm bất biến là **grain và KPI không được mơ hồ**, bất kể dữ liệu cuối cùng lưu trong nhiều bảng sao, một bảng rộng hay một mô hình phục vụ riêng.

### Document, đồ thị và phân tích

- **Document:** đơn hàng có thể chứa mảng dòng hàng để phục vụ đọc nguyên đơn; khi phân tích số tiền theo sản phẩm, phải **mở rộng mảng đúng grain**, không nhân tiền cấp đơn lên từng dòng.
- **Đồ thị:** quan hệ nhiều bước có thể phù hợp cho phân tích mạng lưới, nhưng số lượng đường đi không nhất thiết bằng số lượng giao dịch. Cần định nghĩa đối tượng đang đếm và tránh đường đi trùng.
- **Quan hệ chuẩn hóa:** thích hợp làm nguồn giao dịch có khóa/ràng buộc rõ; mô hình phân tích có thể chuyển đổi sang fact–dimension.
- **Kho phân tích dạng cột:** phù hợp quét và tổng hợp khối lượng lớn, nhưng vẫn cần định nghĩa khóa, grain và kiểm soát chất lượng ngay cả khi hệ quản trị không cưỡng chế FK.

Sự khác biệt về nơi lưu trữ không thay thế tư duy **quy trình → độ hạt → số đo → chiều**.

## 15. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Bắt đầu từ danh sách bảng nguồn | Mô hình thiếu câu hỏi đo lường | Viết câu hỏi/KPI và quy trình trước |
| Ghi “một dòng cho đơn hàng” khi fact thực tế ở mức dòng hàng | Đếm đơn và doanh số sai | Khai báo grain bằng khóa và thời điểm |
| Trộn sự kiện đặt hàng, thanh toán, hoàn trả thành một measure chưa định nghĩa | Nhầm booked amount với doanh thu ròng | Tách quy trình, định nghĩa điều chỉnh |
| JOIN hai fact chi tiết trên `order_id` | Nhân số dòng theo tích số lượng | Tổng hợp từng fact ở grain tương thích trước |
| Cộng `inventory_on_hand` của nhiều ngày | Đếm trùng số dư | Chọn kỳ snapshot và quy tắc tổng hợp |
| Lấy trung bình các tỷ lệ nhóm | KPI tổng lệch do mẫu số khác nhau | Tính từ tổng tử số/tổng mẫu số |
| JOIN dimension SCD2 chỉ theo business key | Nhân fact khi có nhiều phiên bản chiều | JOIN theo surrogate key hoặc thời gian hiệu lực |
| Dùng thuộc tính hiện tại cho câu hỏi lịch sử mà không thông báo | Báo cáo quá khứ bị phân loại lại | Chọn Type 1, Type 2 hay snapshot có chủ đích |
| Dùng `SUM(DISTINCT amount)` để sửa fanout | Xóa nhầm hai giao dịch thật cùng số tiền | Sửa khóa JOIN và grain |
| Lấy `ingested_at` thay cho ngày nghiệp vụ | Dữ liệu đến muộn rơi vào sai kỳ | Phân biệt event time và load time |
| Bỏ dòng không tìm thấy dimension | KPI thiếu mà không biết nguyên nhân | Giám sát late dimension, unknown và backfill |
| Coi một lần thanh toán tương đương một đơn | Thiếu/hơn số tiền khi trả nhiều đợt | Chọn grain transaction và định nghĩa aggregation |
| Đếm khách hàng bằng cách cộng `COUNT(DISTINCT)` các tháng | Một khách hoạt động nhiều tháng bị tính nhiều lần | Tính distinct trên toàn khoảng quan tâm |

## 16. Bài luyện tập có lời giải

### Bài 1 — Chọn grain cho giá trị hàng đặt

Một đơn D01 có ba dòng hàng, mỗi dòng có sản phẩm, số lượng, giá khác nhau. Yêu cầu “giá trị hàng đặt theo danh mục sản phẩm và tháng xác nhận đơn”. Grain fact nào phù hợp?

**Lời giải:** Một dòng cho **mỗi `(order_id,line_no)` tại thời điểm xác nhận** nếu các dòng không có phiên bản riêng ở cùng thời điểm. Fact cần dimension ngày xác nhận và sản phẩm/danh mục đúng thời điểm, cùng `quantity`, `unit_price_at_order`, `line_discount_amount` và measure đã định nghĩa. Fact cấp đơn không đủ để phân bổ giá trị theo danh mục nếu một đơn có nhiều danh mục.

### Bài 2 — Số đơn khác số dòng hàng

Một fact dòng hàng chứa D01 có ba dòng, D02 có một dòng. `COUNT(*)` và `COUNT(DISTINCT order_id)` trả kết quả bao nhiêu?

**Lời giải:** `COUNT(*) = 4` dòng hàng, còn `COUNT(DISTINCT order_id) = 2` đơn. Nếu GROUP BY danh mục, một đơn có thể xuất hiện ở nhiều danh mục; không cộng số đơn distinct giữa các nhóm để suy ra tổng.

### Bài 3 — Chọn loại fact cho tồn kho

Nhà quản lý muốn xem số lượng còn trong mỗi kho vào cuối mỗi ngày, kể cả hôm không có nhập/xuất. Chọn loại fact nào?

**Lời giải:** **Periodic snapshot** với grain `(snapshot_date,warehouse_id,product_id)`, tại mốc chốt đã thống nhất. Tồn kho là measure **semi-additive**: có thể tổng hợp theo kho/sản phẩm ở cùng thời điểm, nhưng không cộng số tồn của nhiều ngày để thành tồn kho “cả tháng”.

### Bài 4 — Quy trình giao nhiều kiện

Một đơn được đóng thành ba kiện; hai kiện giao hôm nay, một kiện giao ngày mai. Nếu KPI là tỷ lệ kiện giao đúng hẹn, grain nào nên dùng?

**Lời giải:** Grain ở **cấp kiện hàng/lượt giao** theo cách nghiệp vụ định danh, không phải một dòng cấp đơn. Cần `shipment_id` hoặc định danh kiện, ngày hứa giao và ngày giao tương ứng. Một accumulating snapshot cấp kiện có thể phù hợp nếu cần theo dõi nhiều mốc.

### Bài 5 — Fanout giữa đơn và thanh toán

Đơn D01 có ba dòng đặt hàng, hai giao dịch capture. JOIN fact dòng hàng với fact thanh toán theo `order_id` tạo bao nhiêu dòng? Có được SUM hai measure trực tiếp không?

**Lời giải:** Tạo \(3\times2=6\) dòng. Không được SUM trực tiếp vì measure của mỗi phía bị nhân lặp. Tổng hợp tiền đặt theo đơn và capture theo đơn **độc lập**, rồi JOIN hai tổng theo `order_id`; sau đó mới tiếp tục phân tích theo chiều phù hợp.

### Bài 6 — Phân loại lịch sử danh mục

Sản phẩm SP01 đổi từ “Phụ kiện” sang “Điện tử” vào tháng 7. Báo cáo tháng 6 phải giữ danh mục đã có khi mua. Dimension nên được xử lý thế nào?

**Lời giải:** Dùng **SCD Type 2** hoặc snapshot thuộc tính đúng thời điểm, gắn fact tháng 6 với phiên bản danh mục “Phụ kiện”. Không JOIN bảng phiên bản chỉ theo `product_id` vì có thể nhân dòng; cần surrogate key đã resolve đúng thời điểm hoặc điều kiện hiệu lực không chồng lấn.

### Bài 7 — Số đơn thanh toán thành công

Nguồn thanh toán có các giao dịch `CAPTURE`, `REFUND` và `RETRY`. Yêu cầu “số đơn đã thanh toán thành công” có thể dùng `COUNT(*)` trên fact giao dịch không?

**Lời giải:** Không. Một đơn có thể có nhiều lần capture, retry hoặc refund. Cần định nghĩa **đã thanh toán thành công** là gì, lọc trạng thái giao dịch đúng, xác định thời điểm và dùng logic theo **đơn** (có thể tổng hợp payment theo `order_id`) thay vì đếm số giao dịch.

### Bài 8 — Tỷ lệ chuyển đổi thiếu mẫu số

Nhóm phân tích có `fact_orders` nhưng không có bảng phiên truy cập. Có thể tính chính xác conversion rate từ phiên sang đơn không?

**Lời giải:** Không. Fact đơn chỉ cung cấp một phía của bài toán. Cần có **dữ liệu phiên hoặc người dùng** với định nghĩa tập truy cập đủ điều kiện, cửa sổ quy đổi và cách gắn đơn vào phiên/kênh; không được dùng số khách hàng trong orders làm mẫu số thay thế nếu đó là định nghĩa khác.

### Bài 9 — Chọn measure có thể cộng

Hai dòng có `(quantity=1, unit_price=100)` và `(quantity=9, unit_price=10)`. Đơn giá bình quân **theo số lượng** bằng bao nhiêu?

**Lời giải:** \((1\times100+9\times10)/(1+9)=19\). Trung bình số học của hai giá là 55 nhưng không phản ánh trọng số số lượng. Nêu rõ có tính giảm giá, thuế, đơn vị tiền tệ hay không.

### Bài 10 — Yêu cầu chưa rõ ngày

Kinh doanh hỏi “doanh số tháng 10”. Dữ liệu có `created_at`, `confirmed_at`, `paid_at` và `ingested_at`. Bạn nên chốt điều gì trước khi viết truy vấn?

**Lời giải:** Xác nhận “doanh số” là giá trị đặt, thanh toán hay ghi nhận; kỳ tháng tính theo **mốc sự kiện nào**, múi giờ nào, trạng thái hủy/hoàn nào, cách xử lý sự kiện đến muộn và thời điểm chốt báo cáo. Sau đó mới chọn fact và dimension ngày phù hợp.

## 17. Checklist trước khi chốt mô hình phân tích

- [ ] Câu hỏi phân tích và **quyết định nghiệp vụ** đã được mô tả cụ thể.
- [ ] KPI có định nghĩa tử số, mẫu số, tập sự kiện, thời điểm và loại trừ rõ ràng.
- [ ] Đã xác định **quy trình nghiệp vụ** tạo ra sự kiện/đối tượng cần đo.
- [ ] **Grain** của mỗi fact được viết thành một câu kiểm chứng được và có khóa phù hợp.
- [ ] Không trộn measures của **nhiều grain** trong cùng fact mà thiếu quy tắc phân bổ.
- [ ] Đã chọn transaction, periodic snapshot, accumulating snapshot hoặc factless fact theo câu hỏi.
- [ ] Mỗi measure được phân loại **additive/semi-additive/non-additive** cùng các giới hạn tiền tệ và đơn vị.
- [ ] Dimension có định nghĩa, khóa và phạm vi dùng chung; mốc thời gian có vai trò rõ.
- [ ] Đã quyết định phân tích theo thuộc tính **hiện tại hay tại thời điểm sự kiện**.
- [ ] JOIN fact–dimension bảo đảm **đúng một phiên bản** hoặc quy tắc bridge/phân bổ phù hợp.
- [ ] Không JOIN hai fact nhiều dòng mà chưa tổng hợp về grain tương thích.
- [ ] Pipeline có xử lý event đến muộn, trùng sự kiện, điều chỉnh và nạp lại idempotent.
- [ ] Có kiểm thử duy nhất theo grain, ràng buộc measure, tham chiếu dimension và đối soát số liệu nguồn.
- [ ] Đã kiểm tra mô hình trên các câu hỏi thật, bao gồm **trường hợp không thể trả lời bằng nguồn hiện có**.
- [ ] Thiết kế vật lý, chỉ mục/phân vùng và data mart được chọn dựa trên workload, không làm mờ grain.

**Ghi nhớ:** Một mô hình phân tích tốt không bắt đầu bằng câu “có những bảng nào?” mà bằng **“cần trả lời câu hỏi nào, quy trình nào tạo ra sự thật đó, và một dòng fact đại diện chính xác cho điều gì?”**. Chốt ba điều ấy trước, bạn mới có thể chọn measure, dimension, khóa và lịch sử một cách nhất quán, tránh JOIN nhân số liệu và xây báo cáo có thể đối soát.
