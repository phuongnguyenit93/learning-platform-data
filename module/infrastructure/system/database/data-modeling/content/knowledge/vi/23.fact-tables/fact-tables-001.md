# Tuyên bố độ hạt trước khi chọn khóa và số đo

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phát biểu **độ hạt (*grain*)** của một bảng dữ kiện (*fact table*) thành một câu nghiệp vụ đủ chính xác để người khác kiểm chứng.
- Phân biệt bảng dữ kiện **giao dịch**, **ảnh chụp định kỳ**, **ảnh chụp tích lũy** và **không có số đo**; hiểu vì sao mỗi loại có khóa và cách cập nhật khác nhau.
- Chọn **khóa định danh**, **khóa tham chiếu chiều (*dimension key*)** và **số đo (*measure*)** theo grain, thay vì chọn trước các cột có sẵn rồi cố giải thích ý nghĩa sau.
- Ngăn lỗi nhân số tiền do JOIN nhiều quan hệ 1:N, cộng chỉ số ở sai cấp độ, đếm trùng và tổng hợp sai loại tiền.
- Thiết kế một bảng fact đơn hàng bằng PostgreSQL, làm rõ thời điểm, chiều thay đổi theo lịch sử, tính cộng được của số đo và cách đối soát.
- Đưa ra tiêu chí kiểm tra grain trong lược đồ quan hệ, kho phân tích, document và graph.

Bài thuộc chương **Bảng dữ kiện** của **DATABASE_DATA_MODELING**. Trong mô hình dữ liệu phục vụ phân tích, ta không chỉ chuyển yêu cầu nghiệp vụ thành bảng, khóa, chỉ mục và ràng buộc; ta phải làm rõ **một hàng biểu diễn chính xác sự kiện hay trạng thái gì**. Câu trả lời ấy quyết định cách liên kết chiều, tính tổng, tổ chức lược đồ vật lý và kiểm chứng kết quả.

## 1. Grain là gì, và vì sao phải tuyên bố trước?

**Độ hạt (grain)** là định nghĩa chính xác **một hàng của bảng fact tương ứng với điều gì trong nghiệp vụ**. Nó không phải chỉ là “bảng này có dữ liệu bán hàng” hay “bảng này nhóm theo ngày”. Một tuyên bố tốt cần làm rõ:

1. **Đối tượng hoặc sự kiện:** giao dịch, dòng hàng, lượt thanh toán, sản phẩm tồn kho, ca làm việc...
2. **Mốc thời gian:** thời điểm xảy ra sự kiện, ngày chụp trạng thái hay vòng đời của một quy trình.
3. **Đơn vị lặp:** một dòng cho mỗi thực thể, mỗi sự kiện, mỗi cặp thực thể–thời gian hay mỗi trạng thái kết thúc.
4. **Phạm vi hợp lệ:** đã xác nhận, đã thanh toán, chưa hủy, thuộc tenant nào, được xử lý thế nào khi sửa/hoàn.
5. **Khả năng định danh:** cách xác định hai hàng có đại diện cùng sự thật hay không.

Ví dụ các câu tuyên bố:

- **Giao dịch bán hàng:** “Mỗi hàng là **một dòng hàng duy nhất của một đơn đã xác nhận**, với số lượng, đơn giá và khoản giảm giá được chốt tại thời điểm xác nhận”.
- **Thanh toán:** “Mỗi hàng là **một lần capture thanh toán thành công**, nhận diện bằng capture ID của nguồn thanh toán”.
- **Tồn kho cuối ngày:** “Mỗi hàng là **số tồn cuối ngày của một sản phẩm tại một kho**, theo ngày nghiệp vụ đã quy định”.
- **Tiến độ giao đơn:** “Mỗi hàng đại diện **một đơn hàng**, được cập nhật khi đi qua các mốc đặt, đóng gói, gửi hàng, giao xong”.
- **Sự kiện tham dự:** “Mỗi hàng ghi nhận **một người tham dự một buổi học**; hàng tự nó biểu diễn sự hiện diện, không nhất thiết có cột lượng”.

Chỉ sau khi chốt một trong các câu đó mới có cơ sở chọn khóa, chiều và số đo.

> **Nếu không biết một hàng nghĩa là gì, ta chưa biết COUNT đếm gì, SUM cộng gì, hay UNIQUE phải ngăn trường hợp nào.**

### 1.1. Grain không phải độ lớn của khóa hoặc kích thước dữ liệu

Một bảng có khóa chính **fact_id BIGINT** không có nghĩa grain là “một fact_id”. Đó chỉ là định danh kỹ thuật. Grain phải được diễn đạt bằng **sự kiện nghiệp vụ**.

Một bảng có một triệu hàng không nhất thiết chi tiết hơn bảng có một nghìn hàng; hai bảng có thể bao phủ kỳ và tập dữ liệu khác nhau. Cụm “grain theo ngày” cũng chưa đủ: **mỗi ngày một hàng trên toàn hệ thống**, hay **mỗi ngày × kho × sản phẩm**?

Ví dụ tuyên bố chưa đạt:

> Bảng fact_sales lưu thông tin đơn và sản phẩm.

Tuyên bố có thể kiểm chứng hơn:

> Một hàng **fact_sales_line** tương ứng một **(order_id, line_no)** đã xác nhận lần đầu, lưu số lượng và số tiền của dòng đó; giao dịch điều chỉnh/hoàn sau xác nhận được ghi bằng một sự kiện khác.

Câu thứ hai cho phép xác định khóa nghiệp vụ, mốc thời gian, quy tắc ghi và thứ không thuộc bảng.

## 2. Ví dụ: sai ngay khi chọn số đo ở cấp độ không rõ

Giả sử có hai đơn, cùng dùng VND, **không xét thuế và vận chuyển**:

| Đơn | Dòng | Sản phẩm | Số lượng | Đơn giá đã chốt | Thành tiền dòng trước giảm | Giảm giá phân bổ | Tiền ròng dòng |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| **O-1001** | 1 | A | 2 | 100.000 | 200.000 | 6.000 | 194.000 |
| **O-1001** | 2 | B | 1 | 120.000 | 120.000 | 4.000 | 116.000 |
| **O-1002** | 1 | C | 1 | 90.000 | 90.000 | 0 | 90.000 |

Ở grain **dòng hàng** có **3 hàng**, tổng số lượng bán là **4 đơn vị**, tổng tiền trước giảm **410.000**, tổng giảm **10.000**, tổng tiền ròng **400.000 VND**. Nhưng chỉ có **2 đơn**.

Giả sử bảng **orders** còn lưu:

| order_id | total_items_net |
| --- | ---: |
| O-1001 | 310.000 |
| O-1002 | 90.000 |

Nếu JOIN **orders** với **order_items** rồi SUM **orders.total_items_net**, đơn O-1001 xuất hiện hai lần:

~~~sql
-- Sai: số tiền ở grain đơn bị lặp trên từng dòng hàng.
SELECT SUM(o.total_items_net) AS wrong_total
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.order_id IN ('O-1001', 'O-1002');
-- 310000 + 310000 + 90000 = 710000, sai.
~~~

Đúng là **310.000 + 90.000 = 400.000 VND**, hoặc cộng **net_amount** trên ba dòng nếu từng dòng đã được phân bổ giảm giá nhất quán.

**Lỗi không nằm ở SUM hay JOIN.** Lỗi nằm ở việc mang một số đo **grain đơn hàng** vào tập dữ liệu **grain dòng hàng**, rồi cộng nó như thể mỗi hàng là một đơn độc lập.

Cũng vậy, **COUNT(*) = 3** ở grain dòng hàng không phải “3 đơn”. Khi thật sự cần đếm đơn, có thể dùng **COUNT(DISTINCT order_id)** tại tập dữ liệu phù hợp, hoặc tạo fact ở grain đơn hàng với định nghĩa riêng. Tuy nhiên, các số **distinct** theo nhóm không phải lúc nào cũng cộng được giữa các nhóm.

### 2.1. Một nghiệp vụ có nhiều sự thật hợp lệ nhưng khác grain

Cùng ví dụ có thể có:

- **2 đơn đã xác nhận**: grain một đơn.
- **3 dòng hàng đã xác nhận**: grain một dòng hàng.
- **4 đơn vị sản phẩm bán**: tổng quantity từ grain dòng hàng; đơn vị có thể khác nhau nếu bán theo kg, hộp, chiếc.
- **N lần thanh toán**: grain capture hoặc payment attempt; một đơn có thể nhiều lần capture.
- **M lần giao kiện**: grain shipment hoặc sự kiện giao nhận; một đơn có thể nhiều kiện.

Không thể đặt tất cả các con số ấy vào một bảng mà không làm rõ **mỗi hàng ứng với đơn, dòng, capture hay shipment**. Cách làm đúng có thể là **nhiều fact table có grain khác nhau**, mỗi bảng phục vụ một nhóm phân tích có ngữ nghĩa rõ.

## 3. Quy trình thiết kế: chọn quá trình nghiệp vụ rồi tuyên bố grain

Một quy trình thực dụng cho mô hình chiều (*dimensional modeling*):

1. **Chọn quá trình nghiệp vụ:** xác nhận đơn, capture thanh toán, giao hàng, chụp tồn kho cuối ngày...
2. **Tuyên bố grain:** viết một câu cụ thể cho **mỗi hàng fact**.
3. **Chọn các chiều:** ai, cái gì, ở đâu, khi nào, kênh nào, trạng thái nào **tại grain ấy**.
4. **Chọn số đo:** các lượng/số tiền/đếm **thực sự xác định được tại grain ấy**.
5. **Thiết kế khóa và vật lý:** khóa business/natural, surrogate key, FK tới dimension, partition, index, cơ chế nạp và đối soát.

Các bước phụ thuộc nhau: sau khi có grain, mới biết **mỗi fact row cần gắn đúng một giá trị chiều hay cần một quan hệ nhiều chiều**. Sau khi có thước đo, mới biết cột nào cộng được.

### 3.1. Tuyên bố grain bằng mẫu có thể kiểm thử

Một mẫu ngắn:

~~~text
Tên fact: <fact_name>
Quá trình: <business process>
Một hàng đại diện: một <sự kiện / thực thể / trạng thái>
Phạm vi: <điều kiện nghiệp vụ, tenant, trạng thái được tính>
Mốc thời gian: <event time / snapshot date / milestone>
Khóa nghiệp vụ duy nhất: <các thuộc tính định danh>
Sự kiện sửa/hủy/hoàn: <quy tắc thay thế hoặc bù trừ>
Các chiều khả dụng: <một giá trị tương ứng trên mỗi hàng>
Các số đo: <đơn vị, công thức và tính cộng được>
~~~

Không nhất thiết phải lưu mẫu này thành bảng; cần **ghi được thành hợp đồng** để review lược đồ, truy vấn và pipeline.

### 3.2. Những câu cần hỏi trước khi chốt

- Dòng hàng có thể được sửa sau xác nhận không? Nếu sửa, có **phiên bản dòng** hay **sự kiện điều chỉnh**?
- Một đơn có thể thanh toán thành nhiều capture không?
- Một sản phẩm có thể xuất hiện nhiều dòng trong một đơn do chương trình khuyến mãi hoặc cấu hình không?
- Cần báo cáo theo **ngày xác nhận**, **ngày ghi nhận tiền**, **ngày giao**, hay cả ba?
- Đơn có thể chứa nhiều loại tiền không? Nếu có, quy tắc tổng tiền thế nào?
- Một dòng bán có thể thuộc nhiều mã khuyến mãi hoặc nhiều người bán?
- Báo cáo cần **khách hàng theo trạng thái hiện hành** hay **phân khúc khách tại ngày bán**?

Nếu đáp án thay đổi, grain hoặc cách ánh xạ chiều có thể phải thay đổi. Không nên chọn khóa trước để ép hệ thống trả lời theo cách thuận tiện.

## 4. Bốn loại bảng fact và câu tuyên bố grain điển hình

### 4.1. Transaction fact — một hàng cho một sự kiện hoặc phần tử sự kiện

Ví dụ:

> Một hàng của **fact_order_line** là một dòng đơn được xác nhận lần đầu, nhận diện bởi **(order_id, line_no)**.

Các trường thường có **order_id**, thời điểm xác nhận, product/customer/date key, quantity, gross amount và discount allocated.

**Đặc điểm:** tạo hàng khi sự kiện đã xảy ra, thường giữ lịch sử; phân tích theo ngày, sản phẩm, khách hàng và kênh. Nếu có sự kiện hoàn/hủy sau đó, có thể tạo **fact_return_line** hoặc **fact_adjustment** với grain sự kiện riêng, thay vì âm thầm ghi đè giá trị gốc.

Một transaction fact khác:

> Một hàng của **fact_payment_capture** đại diện một **capture_id** đã được xác nhận bởi nguồn thanh toán.

Nếu một đơn có nhiều capture, **capture_id** mới là định danh phù hợp cho bảng này; **order_id** không duy nhất.

### 4.2. Periodic snapshot fact — một hàng cho một tổ hợp chiều ở mỗi kỳ

Ví dụ:

> Một hàng của **fact_inventory_eod** là lượng tồn **cuối một ngày nghiệp vụ** của **một sản phẩm tại một kho**, tính theo một đơn vị đo đã quy định.

Grain: **(business_date, warehouse_id, product_id)**, cộng thêm tenant/lot nếu nghiệp vụ phân biệt.

**on_hand_quantity = 50** tại cuối thứ Hai và **on_hand_quantity = 55** cuối thứ Ba không có nghĩa “tổng tồn hai ngày = 105”. Tồn kho là **số đo bán cộng được theo sản phẩm/kho tại cùng thời điểm**, nhưng **không cộng được qua thời gian** để ra tồn hiện hành.

Snapshot định kỳ có thể có một hàng **0** cho tổ hợp không còn tồn nếu quy tắc yêu cầu bao phủ tất cả sản phẩm/kho; hoặc chỉ có hàng khi có tồn/hoạt động. Chính sách tạo hàng phải được ghi trong hợp đồng để **vắng hàng** không bị hiểu nhầm là **0**.

### 4.3. Accumulating snapshot fact — một hàng theo vòng đời đối tượng

Ví dụ:

> Một hàng của **fact_order_lifecycle** đại diện **một đơn**, được cập nhật khi có các mốc **đặt, thanh toán, đóng gói, giao, hoàn thành**.

Mỗi hàng có thể chứa **ordered_date_key**, **paid_date_key**, **shipped_date_key**, **delivered_date_key**; một số mốc có thể chưa xảy ra và cần mô hình giá trị chưa biết phù hợp.

Đây là bảng **có cập nhật** và grain một đơn, khác transaction fact ghi mỗi sự kiện. Nếu quy trình có thể quay lại, có nhiều lần thử giao hoặc nhiều lần hoàn thành, phải định nghĩa rõ **mốc nào** được ghi (đầu tiên, cuối cùng, thành công) hoặc dùng fact sự kiện riêng.

### 4.4. Factless fact — sự hiện diện hoặc độ bao phủ là thông tin

Ví dụ:

> Một hàng của **fact_attendance** biểu diễn một **người tham dự một buổi học**.

Các chiều là người, buổi học, địa điểm, thời điểm. **Không cần cột amount**: đếm số hàng đã biểu diễn số lượt tham dự. Có thể lưu một cột hằng **1** để cộng, nhưng không bắt buộc.

Một factless fact khác có thể ghi **các lượt được phép tham dự** (*coverage*) và so với thực tế tham dự. Phải phân biệt **không có hàng** nghĩa là không tham gia, chưa nạp dữ liệu hay không thuộc tập được theo dõi. Không thể suy sự kiện “không tham dự” chỉ bằng việc không tìm thấy hàng khi chưa xác định phạm vi bao phủ.

### 4.5. Bảng so sánh grain

| Loại fact | Tuyên bố mỗi hàng | Khóa nghiệp vụ gợi ý | Cách ghi | Lưu ý số đo |
| --- | --- | --- | --- | --- |
| Transaction | Một dòng đơn đã xác nhận | **(order_id, line_no)** | Append khi sự kiện xảy ra | Quantity/amount thường cộng được nếu cùng đơn vị |
| Transaction payment | Một capture thành công | **capture_id** | Append, chống trùng event | Capture ≠ đơn hàng |
| Periodic snapshot | Một ngày × kho × sản phẩm | **(date, warehouse, product)** | Nạp/đối soát theo kỳ | Tồn kho không cộng qua thời gian |
| Accumulating snapshot | Một đơn trong vòng đời | **order_id** | Cập nhật các milestone | Mốc thời gian chưa xảy ra, thời lượng phải định nghĩa |
| Factless | Một người × buổi tham dự | **(person, session)** | Append sự hiện diện | COUNT hàng, không cần amount |

Đặt cùng một từ **fact** cho các bảng không có nghĩa chúng chia sẻ grain hoặc cơ chế nạp.

## 5. Từ grain sang khóa: surrogate và khóa nghiệp vụ có nhiệm vụ khác

Với **fact_order_line** đã chốt “mỗi dòng hàng của đơn được xác nhận lần đầu”:

- **(order_id, line_no)** là **khóa nghiệp vụ** phân biệt hai dòng. Nếu hệ đa tenant có thể trùng order_id, cần thêm **tenant_id** vào định danh.
- **sales_line_fact_key** có thể là một surrogate ID kỹ thuật cho hàng fact, thuận tiện cho nội bộ pipeline.
- **date_key**, **product_key**, **customer_key** là **khóa chiều (dimension foreign key)**, không phải bằng chứng grain.
- **source_event_id**, **source_version**, **loaded_at** là metadata phục vụ nguồn gốc, chống trùng và vận hành.

**Surrogate key không thay thế unique constraint của grain.** Nếu chỉ có **sales_line_fact_key PRIMARY KEY**, cùng dòng **(O-1001, 1)** có thể được nạp hai lần với hai ID khác nhau. Khi đó SUM(amount) sai, dù mọi khóa chính đều hợp lệ.

Các dimension có thể dùng surrogate key vì một thực thể nghiệp vụ có nhiều **phiên bản lịch sử** (SCD Type 2). Ví dụ **product_id = A** giữ nguyên nhưng thuộc tính danh mục có thể thay đổi; **product_key** tại ngày bán giúp gắn đúng phiên bản chiều.

### 5.1. Degenerate dimension và role-playing date

**order_id** thường nằm trực tiếp trong fact vì cần lọc/truy vết đơn nhưng không nhất thiết có nhiều thuộc tính riêng để xây một dimension chỉ chứa ID. Đây là ví dụ **degenerate dimension**.

Một quy trình có nhiều ngày — xác nhận, thanh toán, giao hàng — có thể có nhiều **date key đóng vai trò khác nhau** vào cùng **dim_date**. Không gộp chúng vào một cột **date_key** thiếu ngữ nghĩa rồi gọi là “ngày giao dịch”.

### 5.2. Khóa của dimension không phải luôn có sẵn lúc sự kiện đến

Một đơn được xác nhận nhưng hệ thống phân tích chưa nhận được bản dimension của sản phẩm hoặc khách. Khi đó cần chính sách **late-arriving dimension**:

- Tạm dùng một **unknown/pending dimension member** có định danh rõ, sau đó cập nhật tham chiếu khi có dữ liệu.
- Tạo **inferred member** tối thiểu với natural ID rồi bổ sung thuộc tính sau.
- Hoặc tạm hoãn nạp fact trong thời hạn được kiểm soát, theo dõi backlog.

**Không tự nối tới bản sản phẩm hiện hành** rồi cho rằng nó đúng với thời điểm giao dịch. Với dimension thay đổi theo thời gian, phải chọn phiên bản hợp lệ tại event time hoặc theo quy tắc nghiệp vụ được công bố.

## 6. Từ grain sang số đo: phân loại khả năng cộng

Một số đo phải trả lời được:

1. Nó được tạo ở **grain nào**?
2. Đơn vị là gì: **chiếc, kg, VND, USD, giây, phần trăm**?
3. Có thể **SUM theo những chiều nào** mà vẫn đúng?
4. Nó là **dòng tiền/sự kiện**, **trạng thái tại thời điểm**, hay **tỷ số đã tính**?

### 6.1. Additive measure — cộng được theo các chiều phù hợp

Trong **fact_order_line**:

- **quantity** có thể cộng trên các dòng khi đơn vị tính tương thích; nếu một dòng là kg và một dòng là chiếc, tổng “4 đơn vị” không có ý nghĩa nếu không phân loại đơn vị.
- **gross_amount** có thể cộng theo ngày/sản phẩm/khách **nếu cùng currency và cùng định nghĩa giá trị**.
- **discount_allocated** có thể cộng nếu mọi khoản giảm đã được phân bổ đúng một lần.
- **net_line_amount = gross_amount − discount_allocated** có thể cộng để ra tổng tiền ròng dòng hàng **trước các thành phần chưa mô hình hóa**.

Nếu cần báo cáo về tiền đã thu, **không coi đơn hàng đã xác nhận là tiền đã capture**. Dùng nguồn thanh toán và fact capture có grain riêng.

### 6.2. Semi-additive measure — chỉ cộng theo một số chiều

**Tồn kho cuối ngày** và **số dư cuối ngày** là ví dụ:

- Cộng số tồn của **các sản phẩm** tại **một ngày** có thể hợp lệ nếu cùng đơn vị và quy tắc tổng.
- Cộng tồn cuối ngày **thứ Hai + thứ Ba** không ra tồn cuối tuần.
- Muốn bình quân tồn theo tuần, cần quy định **AVG theo những ngày có snapshot**, xử lý ngày thiếu và cách gán trọng số.

Một fact periodic snapshot cần gắn ngày rõ ràng; nếu không, truy vấn SUM dễ trả số lớn nhưng vô nghĩa.

### 6.3. Non-additive measure — không cộng trực tiếp

- **Average selling price = SUM(amount) / SUM(quantity)**; không cộng hay lấy trung bình không trọng số của các giá trung bình nhóm.
- **Conversion rate = conversions / eligible_visits**; lưu tử số và mẫu số nếu cần gộp nhóm.
- **Gross margin % = margin_amount / sales_amount**; không cộng phần trăm các sản phẩm.
- **COUNT(DISTINCT customer_id)**; số khách duy nhất từng ngày **không cộng được qua ngày** khi cùng khách xuất hiện nhiều ngày.
- **Median / percentile**; cần dữ liệu phân bố, thuật toán hoặc cấu trúc tổng hợp phù hợp, không thể cộng các percentile con để ra percentile chung.

Một bảng fact tốt thường lưu **các thành phần có thể cộng** thay vì mọi tỷ số được tính sẵn, trừ khi có use case và hợp đồng vận hành rõ.

### 6.4. Tránh số đo “lơ lửng” khác grain

Ví dụ số tiền vận chuyển **shipping_fee** được tính **một lần trên đơn**. Nếu đặt giá trị ấy trên **mỗi dòng hàng** của đơn mà không phân bổ, SUM theo sản phẩm sẽ nhân khoản phí theo số dòng.

Có các phương án hợp lệ:

1. **Giữ shipping_fee tại fact_order** có grain một đơn.
2. **Phân bổ shipping_fee xuống từng dòng** theo quy tắc được nghiệp vụ duyệt, lưu **allocated_shipping_fee** và kiểm tra tổng phân bổ bằng phí ở đơn.
3. **Không gộp chỉ số đó vào fact_order_line**, chỉ phân tích ở cấp đơn hoặc kết hợp hai nguồn ở cấp tổng hợp phù hợp.

Chọn theo câu hỏi báo cáo. Không “copy một trường sang mọi dòng” chỉ để có sẵn mọi cột trong một bảng.

## 7. Thiết kế PostgreSQL cho grain một dòng đơn đã xác nhận

Ta chọn hợp đồng minh họa:

> **fact_sales_line** chứa đúng một hàng cho mỗi **(order_id, line_no)** đã xác nhận lần đầu; tên/giá/số lượng và khoản giảm giá được chốt khi xác nhận; hoàn tiền và điều chỉnh sau đó được mô hình ở fact riêng.

Giả định đơn đã chốt **một loại tiền**, không tính thuế và vận chuyển trong số đo của fact này. Nếu nghiệp vụ thay đổi các điều khoản sau xác nhận, phải phát sự kiện điều chỉnh có grain riêng, không lặng lẽ ghi đè để giữ nguyên định nghĩa ở đây.

### 7.1. Các dimension tối thiểu

~~~sql
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,              -- Ví dụ 20261122
    calendar_date DATE NOT NULL UNIQUE
);

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,            -- Surrogate key
    product_id TEXT NOT NULL,                 -- Natural ID
    product_name TEXT NOT NULL,
    category_name TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    UNIQUE (product_id, effective_from)
);

CREATE TABLE dim_customer (
    customer_key BIGINT PRIMARY KEY,           -- Surrogate key
    customer_id TEXT NOT NULL,
    segment_name TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    UNIQUE (customer_id, effective_from)
);
~~~

**dim_product** và **dim_customer** có cấu trúc minh họa cho SCD Type 2. **UNIQUE (natural_id, effective_from)** ngăn trùng cùng mốc bắt đầu, nhưng **không tự ngăn các khoảng hiệu lực chồng lấn**. Pipeline phải bảo vệ quy tắc không chồng lấn, hoặc dùng exclusion constraint phù hợp trong PostgreSQL sau khi đã xác định cách biểu diễn thời gian và quyền ghi.

Không phải dimension nào cũng buộc dùng SCD Type 2. Nếu nghiệp vụ chỉ cần phân tích theo thông tin hiện hành, có thể dùng Type 1; nếu cần nhóm sản phẩm theo danh mục lúc bán, cần giữ/định vị phiên bản lịch sử. **Grain fact vẫn là dòng đơn**, còn cách quản lý lịch sử là thuộc tính của dimension và phép JOIN theo thời gian.

### 7.2. Fact và ràng buộc grain

~~~sql
CREATE TABLE fact_sales_line (
    sales_line_fact_key BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    source_confirmation_event_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    confirmed_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    customer_key BIGINT NOT NULL
        REFERENCES dim_customer(customer_key),
    currency CHAR(3) NOT NULL,
    quantity NUMERIC(18, 3) NOT NULL CHECK (quantity > 0),
    unit_price_at_confirmation NUMERIC(18, 2) NOT NULL
        CHECK (unit_price_at_confirmation >= 0),
    gross_amount NUMERIC(22, 2) NOT NULL
        CHECK (gross_amount >= 0),
    discount_allocated NUMERIC(22, 2) NOT NULL
        CHECK (discount_allocated >= 0),
    net_amount NUMERIC(22, 2) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_fact_sales_line_grain
        UNIQUE (order_id, line_no),
    CONSTRAINT ck_fact_sales_line_discount
        CHECK (discount_allocated <= gross_amount),
    CONSTRAINT ck_fact_sales_line_net
        CHECK (net_amount = gross_amount - discount_allocated),
    CONSTRAINT ck_fact_sales_line_gross
        CHECK (
            gross_amount = ROUND(
                quantity * unit_price_at_confirmation, 2
            )
        )
);

CREATE INDEX ix_fact_sales_line_date_product
    ON fact_sales_line (confirmed_date_key, product_key);
~~~

**Giải thích thiết kế:**

- **PRIMARY KEY (sales_line_fact_key)** phục vụ định danh kỹ thuật; **UNIQUE (order_id, line_no)** mới diễn đạt grain nghiệp vụ trong phạm vi giả định.
- **source_confirmation_event_id** không unique vì **một sự kiện xác nhận đơn có thể tạo nhiều dòng fact**.
- **confirmed_at** giữ thời điểm gốc; **confirmed_date_key** là ngày nghiệp vụ dùng để nhóm trên **dim_date**. Nếu dùng timezone cụ thể, pipeline phải quy đổi đúng.
- **product_key**/**customer_key** phải chỉ tới phiên bản dimension hợp lệ theo quy tắc đã chốt, không tùy tiện lấy bản mới nhất.
- **gross_amount**, **discount_allocated**, **net_amount** đều ở **grain dòng**; có ràng buộc công thức. Ví dụ dùng **ROUND(..., 2)** để minh họa quy tắc hai chữ số thập phân. Tiền thật có thể dùng **số nguyên đơn vị nhỏ** hoặc scale/làm tròn theo currency.
- **net_amount** ở đây chỉ là **tiền ròng dòng hàng sau giảm giá phân bổ**, không tự bao gồm thuế, vận chuyển hoặc refund.
- **quantity** dùng NUMERIC vì một số nghiệp vụ có lượng lẻ (kg, mét...), nhưng phải ghi **đơn vị đo** hoặc bảo đảm các dòng tổng hợp có cùng đơn vị. Bảng demo giả định cùng cách hiểu khi tính tổng quantity.

### 7.3. Dữ liệu ví dụ và kết quả truy vấn

Để kiểm chứng, giả sử bảng ngày và dimension đã được nạp đúng:

~~~sql
INSERT INTO dim_date (date_key, calendar_date)
VALUES (20261122, DATE '2026-11-22');

INSERT INTO dim_product (
    product_key, product_id, product_name, category_name,
    effective_from, effective_to
) VALUES
    (101, 'A', 'Sản phẩm A', 'Đồ dùng',
        TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL),
    (102, 'B', 'Sản phẩm B', 'Đồ dùng',
        TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL),
    (103, 'C', 'Sản phẩm C', 'Đồ dùng',
        TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL);

INSERT INTO dim_customer (
    customer_key, customer_id, segment_name,
    effective_from, effective_to
) VALUES
    (201, 'C1', 'RETAIL',
        TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL),
    (202, 'C2', 'RETAIL',
        TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL);
~~~

Ba dòng fact theo bảng ở phần 2:

~~~sql
INSERT INTO fact_sales_line (
    order_id, line_no, source_confirmation_event_id,
    confirmed_at, confirmed_date_key,
    product_key, customer_key, currency,
    quantity, unit_price_at_confirmation,
    gross_amount, discount_allocated, net_amount
) VALUES
    ('O-1001', 1, 'confirm-O-1001',
     TIMESTAMPTZ '2026-11-22 08:00:00+07', 20261122,
     101, 201, 'VND', 2, 100000, 200000, 6000, 194000),
    ('O-1001', 2, 'confirm-O-1001',
     TIMESTAMPTZ '2026-11-22 08:00:00+07', 20261122,
     102, 201, 'VND', 1, 120000, 120000, 4000, 116000),
    ('O-1002', 1, 'confirm-O-1002',
     TIMESTAMPTZ '2026-11-22 10:00:00+07', 20261122,
     103, 202, 'VND', 1, 90000, 90000, 0, 90000);
~~~

Truy vấn tại **grain ngày × currency**:

~~~sql
SELECT
    d.calendar_date,
    f.currency,
    COUNT(*) AS order_line_count,
    COUNT(DISTINCT f.order_id) AS distinct_order_count,
    SUM(f.quantity) AS sold_quantity,
    SUM(f.gross_amount) AS gross_amount,
    SUM(f.discount_allocated) AS discount_amount,
    SUM(f.net_amount) AS net_line_amount
FROM fact_sales_line AS f
JOIN dim_date AS d
    ON d.date_key = f.confirmed_date_key
GROUP BY d.calendar_date, f.currency
ORDER BY d.calendar_date, f.currency;
~~~

Kỳ vọng với dữ liệu ví dụ: **1 ngày**, **3 dòng**, **2 đơn khác nhau**, **4 đơn vị**, **410.000 VND gross**, **10.000 VND discount**, **400.000 VND net_line_amount**.

Hãy chú ý **COUNT(DISTINCT order_id)**: theo từng sản phẩm, một đơn nhiều sản phẩm có thể được đếm trong nhiều nhóm. **Cộng số đơn distinct của các sản phẩm không chắc bằng số đơn distinct toàn hệ thống.** Khi báo cáo đổi cấp độ, phải tính distinct theo tập hợp đang xét hoặc dùng fact grain đơn với quy tắc khác.

## 8. Chọn phiên bản chiều theo thời điểm đã tuyên bố

Grain không chỉ định khóa duy nhất; nó còn quyết định **phép nối dimension** có ý nghĩa tại thời điểm nào.

Giả sử sản phẩm A được chuyển từ danh mục **Đồ dùng** sang **Văn phòng phẩm** vào ngày 01/12. Báo cáo tháng 11 có thể hỏi:

1. **Doanh số theo danh mục tại thời điểm bán:** dùng bản **dim_product** hiệu lực khi dòng hàng được xác nhận.
2. **Doanh số lịch sử phân loại theo danh mục hiện hành:** dùng phân loại mới nhất, nhưng phải ghi rõ đó là phép phân loại lại lịch sử.

Hai câu hỏi đều có thể hợp lệ, **không phải cùng một metric**.

Một phép chọn dimension version theo thời điểm:

~~~sql
SELECT
    p.product_key
FROM dim_product AS p
WHERE p.product_id = $1
  AND p.effective_from <= $2::TIMESTAMPTZ
  AND (
      p.effective_to IS NULL
      OR $2::TIMESTAMPTZ < p.effective_to
  );
~~~

Truy vấn **phải trả đúng một hàng** nếu dimension history đầy đủ, không chồng lấn. Nếu trả 0 hàng, đó là dữ liệu chiều đến muộn hoặc khoảng hiệu lực thiếu. Nếu trả nhiều hàng, là lỗi trùng lấn SCD; không chọn đại một version bằng LIMIT 1 rồi âm thầm che lỗi.

Các ranh giới **[effective_from, effective_to)** tránh đếm trùng tại điểm chuyển phiên bản khi hai khoảng liền nhau. Để hỗ trợ phép JOIN này ở quy mô lớn, cần thiết kế pipeline tìm dimension key theo natural key + event time, và kiểm soát hiệu năng/chỉ mục phù hợp.

### 8.1. Ngày nghiệp vụ phải có timezone xác định

Một đơn xác nhận **2026-11-22 00:30 tại Việt Nam** khác ngày UTC của thời điểm đó. Nếu thống kê theo ngày kinh doanh **Asia/Ho_Chi_Minh**, ngày gán vào **dim_date** phải được tính bằng múi giờ này, không mặc định lấy ngày UTC.

Trong PostgreSQL:

~~~sql
SELECT
    (TIMESTAMPTZ '2026-11-22 00:30:00+07'
        AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS business_date;
-- 2026-11-22
~~~

Nếu công ty vận hành đa múi giờ, cần quy định ngày theo **địa điểm bán, đơn vị pháp lý hay báo cáo toàn cầu**. Grain “mỗi ngày” không hoàn chỉnh nếu chưa biết **ngày của đâu**.

## 9. Sai grain khi đưa nhiều quan hệ 1:N vào cùng một fact

Hãy tưởng tượng một đơn có:

- **3 dòng hàng**,
- **2 lần capture thanh toán**,
- **2 kiện giao hàng**.

Một phép JOIN không kiểm soát giữa order, items, captures và shipments có thể tạo đến **3 × 2 × 2 = 12 hàng** cho một đơn. Nếu sau đó SUM số tiền dòng hàng, mỗi dòng có thể bị nhân **4 lần**.

~~~sql
-- MẪU NGUY HIỂM: ba nhánh 1:N được nối trực tiếp.
SELECT
    o.order_id,
    SUM(i.line_amount) AS wrong_amount
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.order_id
JOIN payment_captures AS p ON p.order_id = o.order_id
JOIN shipments AS s ON s.order_id = o.order_id
GROUP BY o.order_id;
~~~

Đây là **đoạn mô tả lỗi**, tên bảng và cột có tính minh họa, không phải schema được tạo ở phần 7. **SUM(DISTINCT i.line_amount)** không phải cách sửa tổng quát: hai dòng hợp lệ có thể có cùng giá trị tiền và bị gộp nhầm.

### 9.1. Cách thiết kế đúng theo grain

- **fact_sales_line**: một dòng đơn đã chốt; không kéo payment/shipment trực tiếp vào grain dòng.
- **fact_payment_capture**: một capture, có capture ID, số tiền capture và timestamp riêng.
- **fact_shipment_event**: một sự kiện giao vận, có shipment/event ID riêng.
- Nếu báo cáo cần ghép, hãy **tổng hợp từng nhánh theo order_id ở cấp phù hợp trước khi JOIN**, hoặc truy vấn các fact riêng qua dimension được thống nhất, kèm quy tắc tránh nhân bản.

Ví dụ tính tổng payment theo đơn rồi nối vào một bảng đơn ở grain một đơn:

~~~sql
WITH capture_by_order AS (
    SELECT order_id, currency,
           SUM(captured_amount) AS captured_total
    FROM payment_captures
    WHERE status = 'SUCCEEDED'
    GROUP BY order_id, currency
)
SELECT
    o.order_id,
    c.currency,
    c.captured_total
FROM orders AS o
LEFT JOIN capture_by_order AS c
    ON c.order_id = o.order_id;
~~~

Nếu một đơn có capture ở nhiều currency, phép JOIN có thể trả **nhiều hàng cho một đơn**. Vì thế, cần giữ **currency** trong grain của tổng payment và không dùng kết quả để cộng số đo order-level một cách tùy tiện. Muốn một hàng/order phải có thêm quy tắc quy đổi hoặc giới hạn nghiệp vụ tương ứng.

## 10. Multi-valued dimension, bridge table và phân bổ

Một dòng bán có thể áp dụng **hai mã khuyến mãi**, một bài viết có thể có nhiều tác giả, một khách có thể thuộc nhiều nhóm cùng lúc. Không thể giả định mỗi fact row chỉ có một giá trị cho mọi chiều.

Ví dụ dòng **O-1001/1** có số tiền net **194.000 VND** và hai khuyến mãi **PROMO-A** cùng **PROMO-B**. Nếu nối qua bảng bridge và SUM trực tiếp net_amount, tổng sẽ thành **388.000**, sai gấp đôi.

Một **bridge table** có thể mô hình nhiều quan hệ, nhưng phép tổng hợp tiền phải dùng quy tắc cụ thể:

- **Chỉ kiểm tra sự hiện diện:** lọc fact bằng EXISTS hoặc DISTINCT fact key, không cộng lặp.
- **Phân bổ tiền cho các khuyến mãi:** lưu **allocation_weight** hoặc số tiền phân bổ sao cho tổng các phần của một fact đúng theo hợp đồng, ví dụ 0,6 + 0,4 = 1.
- **Báo cáo riêng về số lần một khuyến mãi tham gia:** có thể chấp nhận đếm một dòng nhiều lần **nếu chỉ số được định nghĩa là số lượt tham gia khuyến mãi**, không phải doanh thu.

**Không dùng DISTINCT trên amount** để làm biến mất lỗi nhân số. Hai giao dịch khác nhau cùng tiền vẫn phải được tính hai lần.

## 11. Đối soát grain: kiểm tra độc lập với số đo

Một bảng fact có thể trả đúng tổng tiền ngẫu nhiên dù số dòng bị thiếu và thừa bù cho nhau. Vì vậy, đối soát phải tách **grain**, **phạm vi** và **measure**.

### 11.1. Kiểm tra trùng khóa nghiệp vụ

~~~sql
SELECT order_id, line_no, COUNT(*) AS duplicated_rows
FROM fact_sales_line
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

Với unique constraint ở phần 7, truy vấn này phải không trả kết quả nếu mọi ghi đi qua bảng đúng. Nó vẫn hữu ích với staging, file export hoặc kho đích chưa áp ràng buộc.

Nếu fact thực sự có grain **một lần chỉnh sửa dòng**, khóa **(order_id,line_no)** sẽ quá chặt; cần thêm **revision_id/event_id** và viết lại tuyên bố grain. Đó không phải lỗi của UNIQUE mà là khác biệt về nghiệp vụ cần làm rõ.

### 11.2. Kiểm tra khóa chiều và phạm vi ngày

Nếu warehouse không áp FK vật lý để tối ưu nạp, cần kiểm tra tương đương qua pipeline:

~~~sql
SELECT f.order_id, f.line_no
FROM fact_sales_line AS f
LEFT JOIN dim_product AS p
  ON p.product_key = f.product_key
WHERE p.product_key IS NULL;
~~~

Dùng cùng cách để kiểm tra **customer_key**, **date_key**. Còn phải kiểm tra **product_key** trỏ đúng **product_id** và **phiên bản SCD hiệu lực tại confirmed_at**; tồn tại khóa không đủ chứng minh đúng phiên bản.

### 11.3. Đối chiếu số dòng và tổng tiền với nguồn theo cùng grain

Giả sử hệ nguồn có **source_confirmed_order_lines** với **(order_id, line_no, gross_amount, discount_allocated, net_amount)** ở thời điểm xác nhận. Bảng dưới là tên minh họa cho nguồn đã chuẩn hóa, không phải bảng được tạo trong DDL của bài.

~~~sql
WITH source_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS source_line_count,
        SUM(net_amount) AS source_net
    FROM source_confirmed_order_lines
    GROUP BY order_id
),
fact_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS fact_line_count,
        SUM(net_amount) AS fact_net
    FROM fact_sales_line
    GROUP BY order_id
)
SELECT
    COALESCE(s.order_id, f.order_id) AS order_id,
    s.source_line_count,
    f.fact_line_count,
    s.source_net,
    f.fact_net
FROM source_by_order AS s
FULL OUTER JOIN fact_by_order AS f
  ON f.order_id = s.order_id
WHERE s.order_id IS NULL
   OR f.order_id IS NULL
   OR s.source_line_count IS DISTINCT FROM f.fact_line_count
   OR s.source_net IS DISTINCT FROM f.fact_net;
~~~

**FULL OUTER JOIN** phát hiện đơn chỉ có ở nguồn hoặc chỉ có ở fact, ngoài chênh số dòng và số tiền. Tuy nhiên, việc so sánh phải dựa trên **cùng trạng thái đã xác nhận, kỳ dữ liệu, đồng tiền và watermark**. Nếu fact nạp bất đồng bộ, dữ liệu mới commit ở nguồn có thể chưa tới; đó có thể là lag trong giới hạn, không lập tức là lỗi.

Để chắc chắn không tráo dòng mà vẫn khớp tổng, còn cần so theo **(order_id,line_no)** các thuộc tính chi tiết, đơn giá, quantity và fingerprint dữ liệu. Một tổng tiền đúng không bảo đảm mọi dòng đều đúng.

### 11.4. Các ca dữ liệu biên nên có trong bộ kiểm thử

- Đơn **0 dòng** còn ở DRAFT: không được nạp vào fact dòng đã xác nhận.
- Đơn nhiều dòng cùng **product_id**: vẫn là nhiều dòng nếu business line khác nhau.
- Hai dòng có cùng **gross_amount**: không bị mất một dòng bởi SUM(DISTINCT).
- Đơn được xác nhận rồi **hủy/hoàn tiền**: giữ lịch sử fact theo hợp đồng và mô hình điều chỉnh riêng.
- Event xác nhận được gửi lại: không tạo bản ghi trùng grain.
- Một dòng sửa **quantity** trước xác nhận và sau xác nhận: hai thời điểm có quy tắc khác nhau.
- Dữ liệu thiếu dimension hoặc đến muộn: có chính sách inferred/unknown member hoặc retry.
- Khác **currency**, khác **timezone**, sản phẩm đổi danh mục và khách đổi phân khúc.
- Nhiều payment/shipment cho cùng order: không nhân số dòng.
- Tái nạp lịch sử và đối soát sau sửa lỗi: không làm đổi các sự thật đã chốt thiếu chứng cứ.

## 12. Nạp và sửa fact theo đúng grain

### 12.1. Idempotency khi cùng một sự kiện được phát lại

Với grain **(order_id, line_no)**, có thể dùng unique constraint để ngăn chèn trùng:

~~~sql
INSERT INTO fact_sales_line (
    order_id, line_no, source_confirmation_event_id,
    confirmed_at, confirmed_date_key,
    product_key, customer_key, currency,
    quantity, unit_price_at_confirmation,
    gross_amount, discount_allocated, net_amount
)
VALUES (
    'O-1001', 1, 'confirm-O-1001',
    TIMESTAMPTZ '2026-11-22 08:00:00+07', 20261122,
    101, 201, 'VND',
    2, 100000, 200000, 6000, 194000
)
ON CONFLICT (order_id, line_no) DO NOTHING;
~~~

Điều này giúp ngăn thêm hàng giống grain khi retry, nhưng **chưa đủ** để coi pipeline đúng hoàn toàn. Nếu hai event khác nhau có cùng khóa nhưng **quantity hoặc price khác**, **DO NOTHING** sẽ che xung đột. Cần đối chiếu payload, phân loại retry tương đương với **sửa nghiệp vụ**, và báo lỗi/quarantine nếu dữ liệu trái hợp đồng.

Nếu nghiệp vụ cần các phiên bản đã xác nhận nhiều lần, có hai cách mẫu:

- Đổi grain thành **(order_id, line_no, revision_id)** và xác định mỗi revision là một hàng sự kiện, với cách truy vấn trạng thái cuối rõ ràng.
- Giữ fact dòng xác nhận lần đầu, ghi **fact_order_line_adjustment** với grain một event điều chỉnh, tham chiếu dòng gốc và lượng bù.

Không thể sửa một khóa duy nhất rồi giữ nguyên lời tuyên bố grain cũ mà không xác định lại ý nghĩa số đo.

### 12.2. Late-arriving facts, backfill và snapshot nhất quán

Một sự kiện được xác nhận vào hôm trước nhưng đến warehouse hôm nay **thuộc ngày xác nhận**, không mặc nhiên thuộc ngày worker nhận. Có thể lưu cả **confirmed_at** và **loaded_at**; hai mốc phục vụ hai câu hỏi khác nhau.

Khi backfill hàng triệu dòng:

1. Chọn **snapshot/checkpoint** của nguồn và cách thu thay đổi xảy ra trong lúc nạp.
2. Tái tạo khóa dimension theo phiên bản hợp lệ tại event time.
3. Nạp theo grain, chống trùng và so số dòng/số tiền.
4. Bắt kịp dữ liệu mới; không để job backfill cũ ghi đè phiên bản mới nếu thiết kế có cập nhật.
5. Đối soát cùng watermark và chuyển đường đọc sau khi đạt tiêu chí.

Lưu ý fact transaction được định nghĩa như **sự kiện bất biến** có thể append theo grain; periodic snapshot lại có thể cần **tái tính/ghi đè một kỳ** theo chính sách; accumulating snapshot cần **cập nhật milestone**. Chiến lược nạp phải theo **loại fact và grain**, không dùng cùng một MERGE cho mọi bảng.

## 13. Grain điều khiển truy vấn, partition và mô hình vật lý

Sau khi chốt grain/khóa, mới cân nhắc tổ chức vật lý:

- **Partition theo confirmed_date_key** có thể giúp quét theo khoảng ngày hiệu quả khi số dòng rất lớn. Nhưng nếu database yêu cầu **unique constraint trên bảng partitioned phải chứa khóa phân vùng**, cần kiểm tra lại khả năng bảo vệ khóa nghiệp vụ **(order_id,line_no)** trên toàn bộ partition; không được âm thầm bỏ bảo đảm duy nhất.
- **Index (confirmed_date_key, product_key)** phục vụ một số truy vấn theo ngày và sản phẩm, nhưng phải xác minh selectivity, sort và workload; quá nhiều index tăng chi phí nạp.
- **Cluster/columnar warehouse** thường tối ưu quét tổng hợp hơn OLTP row store; có thể lưu cùng grain fact dưới vật lý khác.
- **Materialized view/aggregate table** ở grain **(day, product, currency)** có thể tăng tốc báo cáo, nhưng đó là **bảng dẫn xuất grain cao hơn**, không thay thế nguồn fact dòng.
- **Rollup** chỉ hợp lệ với số đo có phép cộng phù hợp; distinct count, tỷ lệ hoặc trạng thái cuối kỳ cần công thức khác.
- **Cardinality của dimension** và số lượng khóa khác nhau ảnh hưởng kích thước/hiệu năng; không chọn grain thô chỉ để giảm dung lượng nếu câu hỏi nghiệp vụ đòi dòng chi tiết.

### 13.1. Đơn vị lưu trữ và đơn vị phân tích là hai khái niệm khác

Một document **Order** có thể nhúng nhiều **items[]**, nhưng trong phân tích, mỗi phần tử item vẫn có thể là **một fact row ở grain dòng đơn**. Ngược lại, một bảng quan hệ có một hàng mỗi order vẫn có thể không chứa đủ thông tin để phân tích sản phẩm.

Do đó, grain là **ngữ nghĩa logic của một đơn vị quan sát**, không phụ thuộc tuyệt đối vào việc nó nằm ở một row PostgreSQL, một phần tử mảng JSON hay một record trong file Parquet.

## 14. So sánh với relational, document, graph và analytics

| Mô hình | Một “hàng fact” tương ứng điều gì? | Cách biểu diễn | Điều phải giữ |
| --- | --- | --- | --- |
| **Quan hệ OLTP** | Dòng hàng, capture, shipment event… trong bảng nghiệp vụ | PK/FK, transaction, lịch sử sự kiện | Khóa nghiệp vụ, không nhân bản qua JOIN |
| **Dimensional/OLAP** | Một quan sát ở grain đã tuyên bố | Fact + dimension keys + measure | SCD, additivity, lineage, kỳ/timezone |
| **Document** | Đơn chứa mảng items; khi xuất phân tích thì mỗi item có thể là một fact | Embed snapshot hoặc xuất dòng từ array | Không nhân bản items khi xử lý payment/shipment; bảo toàn ID/tiền |
| **Graph** | Một cạnh mua, một sự kiện tương tác hoặc một quan hệ | Edge properties hoặc event node | Phân biệt một edge hiện hành với nhiều event lịch sử, tránh đếm cạnh trùng |
| **Aggregate/read projection** | Một ngày × sản phẩm × tiền tệ hay một nhóm khác | Bảng tổng hợp, materialized view, search analytics | Từ fact nguồn đến nhóm, biết số đo nào cộng được |

Trong **document database**, lựa chọn nhúng items vào Order hợp lý cho đường đọc chi tiết nhưng không biến **order-level total** thành số đo cộng được cho **mỗi item**. Khi **unwind items**, phải phân biệt số đo đơn hàng với số đo dòng.

Trong **graph database**, một quan hệ **Customer–PURCHASED–Product** có thể thiếu phân biệt lần mua, số dòng và thời điểm nếu chỉ giữ một cạnh duy nhất. Nếu muốn đếm giao dịch, cần thực thể/cạnh **PurchaseEvent/OrderLine** có ID và grain phù hợp, không chỉ quan hệ “đã từng mua”.

Trong **analytics**, fact table có grain thấp làm nguồn để tạo nhiều aggregate có grain cao hơn; grain càng thô càng mất khả năng truy vấn những chiều không còn hiện diện. Chọn grain dựa trên tập câu hỏi phải trả lời, quyền riêng tư và chi phí lưu trữ.

## 15. Mẫu hợp đồng grain cho review thiết kế

Một nhóm có thể dùng checklist sau trước khi phê duyệt bảng fact:

| Câu hỏi | Bằng chứng mong muốn |
| --- | --- |
| Quá trình nghiệp vụ là gì? | Xác nhận dòng hàng, capture, tồn kho cuối ngày... |
| Một hàng chính xác là gì? | Một câu mô tả đơn vị quan sát |
| Hàng phát sinh khi nào? | Sự kiện/mốc chụp/kết thúc quy trình |
| Grain có thay đổi khi sửa nghiệp vụ không? | Append, correction hay update milestone |
| Khóa nghiệp vụ là gì? | Tổ hợp tự nhiên và UNIQUE/idempotency |
| Có tenant/đơn vị phân vùng không? | Phạm vi duy nhất thực tế |
| Dimension nào đúng tại hàng đó? | Product/customer/date/warehouse và phiên bản lịch sử |
| Có dimension nhiều giá trị không? | Bridge, filtering hoặc allocation rõ |
| Số đo nào có nghĩa ở grain này? | Đơn vị, công thức, giá trị NULL, cách làm tròn |
| SUM theo các chiều nào đúng? | Additive, semi-additive, non-additive |
| Cần bao nhiêu loại thời gian? | Business event time, snapshot date, loaded time |
| Hoàn/hủy/điều chỉnh sẽ làm gì? | Fact riêng, delta/phiên bản hoặc quy trình được công bố |
| Dữ liệu đến muộn và trùng xử lý thế nào? | Event ID, checkpoint, SCD matching, reconciliation |
| Có cách kiểm tra từ nguồn không? | Count distinct grain, số dòng, số tiền, match từng ID |
| Truy vấn vật lý có đạt SLO không? | Explain, benchmark, partition/index theo workload |

Nếu câu “một hàng là gì” vẫn mơ hồ, **đừng bắt đầu bằng CREATE TABLE hoặc chọn measure**. Hãy làm rõ nghiệp vụ trước; đó là khoản tiết kiệm lớn nhất so với sửa toàn bộ ETL và báo cáo về sau.

## 16. Bài tập vận dụng

### Bài 1 — Chọn grain và khóa cho dòng bán

Hệ thống có một đơn **ORD-88** gồm ba dòng; cùng một sản phẩm có thể xuất hiện hai dòng vì áp chính sách giá khác nhau. Yêu cầu phân tích số lượng và tiền ròng theo sản phẩm tại thời điểm xác nhận.

**Câu hỏi:** Nên chọn grain và khóa nghiệp vụ nào? Dùng **(order_id, product_id)** làm UNIQUE có an toàn không?

### Bài 2 — SUM đơn hàng sau JOIN

Một đơn có ba dòng hàng, **total_items_net = 500.000 VND**. Báo cáo JOIN đơn với dòng và SUM total_items_net được **1.500.000 VND**.

**Câu hỏi:** Lỗi nằm ở đâu? Có hai cách sửa theo grain nào?

### Bài 3 — Tồn kho cuối hai ngày

Kho K có tồn cuối thứ Hai 10 sản phẩm A và cuối thứ Ba 12 sản phẩm A. Nhóm báo cáo “tồn hai ngày” bằng SUM(10+12)=22.

**Câu hỏi:** Số 22 mang nghĩa gì? Muốn báo cáo tồn cuối thứ Ba hoặc bình quân ngày, tính thế nào?

### Bài 4 — Bán hàng và capture không cùng grain

Một đơn có 2 dòng hàng, nhưng cổng thanh toán cho phép 3 capture. Nhóm muốn có một fact với khóa **order_id** và cột **capture_amount**, đồng thời báo cáo theo sản phẩm.

**Câu hỏi:** Có thể biểu diễn đúng mọi capture và mọi sản phẩm chỉ bằng một hàng/order không? Nên chia fact như thế nào?

### Bài 5 — Điểm trung bình theo ngày

Ngày A có 2 dòng bán với tổng tiền 300.000 VND và tổng số lượng 3. Ngày B có 7 dòng với tổng tiền 700.000 VND và tổng số lượng 14. Nhóm lấy **(300.000/3 + 700.000/14)/2** làm giá bán bình quân của toàn kỳ.

**Câu hỏi:** Công thức có đúng không? Giá bình quân đúng theo lượng là bao nhiêu?

### Bài 6 — Sản phẩm đổi danh mục

Ngày 15/11, sản phẩm P ở danh mục A và có một dòng bán. Ngày 01/12, P chuyển sang danh mục B. Báo cáo hỏi “Doanh số tháng 11 theo **danh mục tại thời điểm bán**”.

**Câu hỏi:** Nên dùng dimension hiện tại hay phiên bản SCD hiệu lực lúc bán? Nếu cả hai cách phân loại đều cần, có thể trình bày thế nào?

### Bài 7 — Hai khuyến mãi trên cùng dòng

Một dòng đơn có net_amount 200.000 VND và liên quan hai promotion. JOIN với bridge tạo hai hàng, mỗi hàng giữ net_amount 200.000; báo cáo SUM thành 400.000.

**Câu hỏi:** Sai ở đâu? Hãy đề xuất một cách đếm sự hiện diện và một cách phân bổ tiền.

### Bài 8 — Sự kiện xác nhận bị retry

Nguồn gửi lại cùng một sự kiện chứa các dòng của đơn O-200. Pipeline tạo surrogate fact ID mới mỗi lần nạp và không có UNIQUE theo grain. Tổng tiền bị nhân đôi.

**Câu hỏi:** Vì sao surrogate PK không đủ? Cần khóa nào, và trường hợp cùng khóa nhưng số tiền khác thì xử lý ra sao?

### Gợi ý lời giải

1. Grain **một dòng hàng được chốt**, khóa **(order_id, line_no)** hoặc line ID ổn định; thêm tenant ID nếu cần. **(order_id, product_id)** không an toàn vì một sản phẩm có thể nằm ở nhiều dòng hợp lệ.
2. Số đo order-level bị lặp trên ba dòng. Có thể **tổng hợp orders ở grain một đơn**, hoặc **phân bổ/cộng số đo line-level** nếu điều khoản tiền đã được phân bổ đúng. Không sửa bằng SUM(DISTINCT amount) tổng quát.
3. **22** không phải tồn cuối kỳ; là tổng hai ảnh chụp theo thời gian, thường không hữu ích. Tồn cuối thứ Ba là **12**. Bình quân đơn giản trên hai ngày có đủ snapshot là **(10+12)/2 = 11**, nếu chính sách cho phép bình quân đều theo ngày.
4. Không, vì **order, dòng hàng và capture** là ba grain khác nhau. Dùng **fact_sales_line** và **fact_payment_capture** với capture ID duy nhất; có thể thêm fact đơn/order lifecycle nếu cần. Khi ghép, tổng hợp về cấp phù hợp và tránh nhân dòng.
5. Sai vì trung bình các tỷ số ngày không trọng số theo lượng. Giá bình quân theo đơn vị bán là **(300.000+700.000)/(3+14) ≈ 58.823,53 VND/đơn vị**. Tổng số tiền và số lượng là hai thành phần cần cộng trước khi chia.
6. Dùng **phiên bản dim_product có hiệu lực tại confirmed_at** để báo cáo danh mục lúc bán: A. Nếu cần phân tích theo danh mục hiện hành, xây phép nối/phân loại hiện hành khác và đặt tên hai chỉ số rõ ràng.
7. Join bridge làm một fact row xuất hiện hai lần. Để hỏi có promotion hay không, dùng **EXISTS** hoặc đếm fact key không trùng. Để phân bổ tiền, dùng weight tổng bằng 1, ví dụ 0,6 và 0,4, tạo **120.000** và **80.000 VND** theo chính sách.
8. Surrogate PK chỉ bảo vệ mỗi lần INSERT kỹ thuật, không bảo vệ cùng một dòng nghiệp vụ. Thêm **UNIQUE(order_id,line_no)** hoặc ID dòng thật; kiểm tra retry tương đương. Nếu cùng khóa nhưng payload khác, phải điều tra correction/version thay vì **ON CONFLICT DO NOTHING** che xung đột.

## 17. Ghi nhớ

**Tuyên bố grain là quyết định gốc của một bảng fact.** Nó có trước khóa, số đo, dimension và tối ưu vật lý vì nó nói rõ **một hàng là một sự thật gì**. Khóa phải bảo vệ grain; số đo phải có ý nghĩa tại grain; phép JOIN và SUM phải bảo toàn số hàng, đơn vị và khả năng cộng.

**Một nghiệp vụ có thể cần nhiều fact với grain khác nhau**: dòng bán, capture, giao kiện, tồn kho cuối ngày và tiến độ đơn. Đừng ép mọi sự kiện vào một bảng chỉ vì chúng có chung **order_id** hay **product_id**.

Cách tự kiểm tra ngắn nhất: **“Nếu tôi sao chép một hàng này, điều gì bị đếm hai lần? Nếu tôi gộp hai hàng, sự thật gì bị mất? Nếu tôi SUM cột này qua thời gian hoặc chiều khác, kết quả còn ý nghĩa không?”**. Trả lời được ba câu hỏi ấy là nền tảng để thiết kế dữ liệu phân tích rõ nghĩa, dễ tiến hóa và kiểm chứng.
