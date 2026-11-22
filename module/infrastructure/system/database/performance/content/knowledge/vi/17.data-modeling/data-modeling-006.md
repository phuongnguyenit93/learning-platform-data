# Dữ liệu thời gian, độ chính xác số và chi phí chuyển đổi

Mô hình dữ liệu ảnh hưởng trực tiếp đến độ chính xác kết quả và hiệu năng truy vấn. Một cột thời gian có thể lưu một thời điểm tuyệt đối, một giờ lịch địa phương hoặc một ngày nghiệp vụ. Một cột số có thể lưu giá trị thập phân chính xác hoặc số dấu phẩy động gần đúng. Khi ứng dụng và cơ sở dữ liệu dùng kiểu dữ liệu không tương thích, hệ quản trị có thể phải chuyển đổi giá trị, làm thay đổi kết quả ở ranh giới, tăng chi phí CPU hoặc khiến chỉ mục khó được tận dụng.

Trong chương **Mô hình dữ liệu** của module **DATABASE_PERFORMANCE**, bài học này giải thích cách chọn kiểu dữ liệu thời gian và số, quản lý độ chính xác, kiểm soát làm tròn và hiểu chi phí chuyển đổi. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng sau điều chỉnh. Vì vậy, mô hình dữ liệu cần giữ đúng ý nghĩa nghiệp vụ, hỗ trợ truy vấn có thể tìm kiếm bằng chỉ mục và tránh chuyển đổi lặp không cần thiết.

## 1. Kiểu dữ liệu là một phần của hợp đồng dữ liệu

Khi khai báo cột, kiểu dữ liệu xác định những giá trị nào có thể lưu, cách so sánh, cách tính toán, độ chính xác và cách hệ quản trị biểu diễn dữ liệu. Ứng dụng cũng có kiểu tương ứng trong ngôn ngữ lập trình và driver kết nối.

Một hợp đồng dữ liệu tốt phải thống nhất các yếu tố:

- Ý nghĩa nghiệp vụ của giá trị.
- Miền giá trị hợp lệ và giới hạn lớn nhất/nhỏ nhất.
- Đơn vị đo, chẳng hạn giây, mili giây, mét, gram hoặc đơn vị tiền.
- Độ chính xác và quy tắc làm tròn.
- Múi giờ hoặc quy ước thời gian.
- Kiểu dữ liệu ở database, ứng dụng, message và API.
- Cách chuyển đổi khi đọc, ghi, so sánh và nối dữ liệu.

Ví dụ, cột amount có thể biểu diễn số tiền theo đơn vị tiền tệ với hai chữ số thập phân, hoặc lưu số tiền theo đơn vị nhỏ nhất dưới dạng số nguyên. Hai cách đều có thể đúng nếu quy ước rõ ràng. Nếu ứng dụng gửi số dấu phẩy động vào cột thập phân mà không kiểm soát chuyển đổi, giá trị có thể bị làm tròn khác mong đợi.

Tương tự, created_at có thể là thời điểm tuyệt đối của một sự kiện hoặc giờ địa phương do người dùng nhập. Nếu hai ý nghĩa này dùng chung một cột mà không có quy ước, truy vấn theo ngày, sắp xếp và đối chiếu giữa dịch vụ có thể sai.

## 2. Phân biệt thời điểm tuyệt đối, ngày và giờ địa phương

Các giá trị thời gian không có cùng ngữ nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Instant | Một thời điểm duy nhất trên dòng thời gian | Sự kiện được ghi nhận lúc một thời điểm UTC |
| Local date | Ngày lịch không có giờ hoặc múi giờ | Ngày sinh 1995-08-12 |
| Local time | Giờ trên đồng hồ không có ngày hoặc múi giờ | Cửa hàng mở lúc 09:00 |
| Local date-time | Ngày và giờ lịch, chưa xác định instant nếu thiếu múi giờ | Cuộc hẹn lúc 09:30 ngày 2026-05-12 tại một địa điểm |
| Offset date-time | Ngày giờ kèm độ lệch UTC tại thời điểm đó | 2026-05-12T09:30+07:00 |
| Zoned date-time | Ngày giờ gắn với quy tắc của vùng thời gian | 2026-05-12T09:30 tại Asia/Ho_Chi_Minh |
| Duration | Khoảng thời gian trôi qua | 90 giây |
| Period | Khoảng theo lịch | Một tháng hoặc ba ngày lịch |

Một Instant xác định duy nhất một thời điểm. Local date-time như 09:30 không đủ thông tin để xác định thời điểm tuyệt đối nếu chưa biết múi giờ và quy tắc vùng. Offset như +07:00 xác định độ lệch tại một thời điểm, nhưng không chứa toàn bộ quy tắc lịch sử hoặc tương lai của vùng.

Hãy chọn kiểu cột theo ý nghĩa:

- Thời điểm sự kiện hoặc thời điểm tạo bản ghi: lưu instant theo một quy ước rõ ràng.
- Ngày sinh, ngày hóa đơn hoặc ngày nghỉ: dùng kiểu DATE nếu không cần giờ.
- Giờ mở cửa hằng ngày: dùng kiểu TIME nếu không gắn với ngày cụ thể.
- Lịch hẹn địa phương: lưu ngày giờ và vùng/offset theo yêu cầu nghiệp vụ.
- Thời lượng xử lý: dùng kiểu duration phù hợp hoặc số có đơn vị được định nghĩa rõ.

Không lưu mọi giá trị vào chuỗi văn bản. Chuỗi làm mất khả năng kiểm tra miền giá trị và khiến việc sắp xếp, so sánh, tính khoảng hoặc dùng chỉ mục phụ thuộc định dạng và chuyển đổi.

## 3. Lưu thời điểm tuyệt đối và quy ước UTC

Một mô hình phổ biến là lưu thời điểm sự kiện theo UTC, sau đó chuyển sang múi giờ nghiệp vụ khi hiển thị hoặc tính ngày báo cáo. Cách này giúp so sánh các sự kiện từ nhiều vùng và sắp xếp theo cùng một dòng thời gian.

Tuy nhiên, tên kiểu dữ liệu và cách lưu timezone khác nhau giữa hệ quản trị. Ví dụ, PostgreSQL có TIMESTAMP WITH TIME ZONE và TIMESTAMP WITHOUT TIME ZONE; MySQL có TIMESTAMP và DATETIME với hành vi khác nhau; SQL Server có datetime2 và datetimeoffset. Không được suy luận ngữ nghĩa chỉ từ tên kiểu.

Trước khi chọn kiểu, hãy xác định:

- Database lưu instant hay local wall-clock time?
- Session timezone có ảnh hưởng khi đọc/ghi không?
- Driver gửi và nhận giá trị theo timezone nào?
- Dữ liệu có cần giữ offset gốc do người dùng cung cấp không?
- Có cần lưu tên vùng như Asia/Ho_Chi_Minh để tái tạo quy tắc địa phương không?

Nếu cần giữ cả instant và vùng lịch gốc, có thể lưu instant cùng zone identifier riêng. Offset đơn lẻ có thể không đủ để tái tạo quy tắc DST hoặc thay đổi luật trong tương lai.

## 4. Ngày lịch không phải lúc nào cũng là 24 giờ

Ngày địa phương ở vùng có giờ mùa hè (DST) có thể dài 23 hoặc 25 giờ. Một giờ trên đồng hồ có thể không tồn tại hoặc xuất hiện hai lần khi đồng hồ đổi giờ. Vì vậy, không nên tính ngày kế tiếp bằng cách cộng cố định 24 giờ vào instant bắt đầu nếu nghiệp vụ cần ranh giới ngày lịch địa phương.

Trong Java, dùng thư viện java.time để tạo ranh giới:

~~~java
LocalDate businessDate = LocalDate.of(2026, 5, 12);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant start = businessDate.atStartOfDay(zone).toInstant();
Instant end = businessDate.plusDays(1).atStartOfDay(zone).toInstant();
~~~

Sau đó truy vấn theo khoảng nửa mở:

~~~sql
WHERE created_at >= :start_instant
  AND created_at <  :end_instant
~~~

Ví dụ này giả định cột và JDBC driver thống nhất cách biểu diễn instant. Hãy bind tham số theo kiểu được driver và database hỗ trợ, đồng thời kiểm tra timezone của session. Với các vùng DST, phép cộng một ngày lịch trong ZoneId xử lý ranh giới theo quy tắc vùng.

## 5. Độ chính xác của kiểu thời gian

Kiểu thời gian có thể hỗ trợ số chữ số thập phân khác nhau. Một hệ quản trị có thể lưu giây, mili giây, micro giây hoặc độ chính xác khác tùy kiểu và cấu hình. Driver hoặc ứng dụng cũng có thể có độ chính xác khác database.

Các tình huống thường gây lỗi:

- Ứng dụng tạo timestamp đến nano giây nhưng cột chỉ lưu micro giây.
- Driver làm tròn hoặc cắt phần thập phân khi bind.
- Hai hệ thống ghi cùng sự kiện với độ chính xác khác nhau.
- Phân trang theo timestamp nhưng nhiều hàng có cùng giá trị sau khi làm tròn.
- So sánh timestamp có độ chính xác khác nhau tại ranh giới.

Không nên giả định database luôn làm tròn theo cùng một quy tắc. Hãy kiểm tra tài liệu của kiểu dữ liệu và driver, sau đó thử với giá trị có phần thập phân ngay dưới, đúng tại và ngay trên độ chính xác được hỗ trợ.

### 5.1. Khoảng nửa mở tránh phụ thuộc giá trị cuối cùng

Khi truy vấn theo ngày hoặc khoảng liên tiếp, dùng:

~~~sql
WHERE occurred_at >= :start_time
  AND occurred_at <  :end_time
~~~

Tránh tạo thời điểm cuối ngày như 23:59:59.999999 vì kiểu cột có thể lưu độ chính xác khác. Khoảng nửa mở không cần biết giá trị cuối cùng có thể biểu diễn; nó chỉ cần ranh giới đầu của khoảng kế tiếp.

Cách này cũng tránh việc một bản ghi ở ranh giới bị tính hai lần khi hai khoảng liền nhau. Đầu mút bắt đầu được bao gồm, đầu mút kết thúc không được bao gồm.

## 6. Độ chính xác số: chính xác và gần đúng

Các kiểu số thường chia thành hai nhóm:

- **Số thập phân chính xác:** DECIMAL hoặc NUMERIC, thường dùng cho tiền, số lượng cần độ chính xác thập phân và các phép tính cần quy tắc làm tròn rõ ràng.
- **Số dấu phẩy động gần đúng:** FLOAT, REAL hoặc DOUBLE PRECISION, biểu diễn số theo định dạng nhị phân với độ chính xác hữu hạn.

Số thập phân như 0.1 thường không có biểu diễn nhị phân hữu hạn chính xác. Do đó, phép tính dấu phẩy động có thể tạo ra kết quả như 0.30000000000000004 thay vì 0.3. Đây không nhất thiết là lỗi của hệ quản trị; đó là đặc tính của biểu diễn số gần đúng.

Ví dụ:

~~~sql
SELECT
    CAST(0.1 AS DOUBLE PRECISION)
  + CAST(0.2 AS DOUBLE PRECISION);
~~~

Kết quả có thể gần 0.3 nhưng không nhất thiết bằng chính xác 0.3. Với dữ liệu tài chính hoặc quy tắc cần so sánh chính xác, dùng kiểu thập phân phù hợp và quy tắc scale rõ ràng.

Không dùng FLOAT chỉ vì nó có vẻ gọn hoặc nhanh hơn. Cũng không dùng NUMERIC với precision cực lớn cho mọi cột nếu workload không cần; kiểu số rộng có thể làm tăng dung lượng và chi phí tính toán. Hãy chọn theo miền giá trị, độ chính xác nghiệp vụ và đo đạc.

## 7. Chọn precision và scale cho DECIMAL/NUMERIC

DECIMAL(p, s) hoặc NUMERIC(p, s) thường mô tả:

- p: tổng số chữ số được phép.
- s: số chữ số ở phần thập phân.
- Số chữ số phần nguyên tối đa thường là p - s.

Ví dụ NUMERIC(18, 2) cho phép tối đa 16 chữ số phần nguyên và 2 chữ số thập phân, theo giới hạn của hệ quản trị.

Không chọn precision tùy ý. Cần xác định:

- Giá trị lớn nhất có thể phát sinh.
- Số chữ số thập phân cần giữ.
- Có cần hỗ trợ tiền tệ với số chữ số thập phân khác nhau không?
- Kết quả trung gian của phép nhân hoặc tổng có thể lớn đến đâu?
- Quy tắc làm tròn được áp dụng ở bước nào?
- Hệ quản trị xử lý overflow và scale khi CAST như thế nào?

Ví dụ, amount NUMERIC(18,2) có thể phù hợp với một loại tiền tệ thông thường, nhưng không phải mọi đơn vị tiền đều có cùng số chữ số thập phân. Nếu hệ thống đa tiền tệ, cần lưu currency code và quy tắc scale tương ứng, hoặc dùng mô hình lưu đơn vị nhỏ nhất theo từng currency.

## 8. Lưu tiền và các giá trị cần chính xác

Đối với tiền, tránh dùng số dấu phẩy động gần đúng làm kiểu lưu trữ chính nếu nghiệp vụ yêu cầu kết quả chính xác đến đơn vị tiền nhỏ nhất.

Hai cách phổ biến:

1. Dùng DECIMAL/NUMERIC với precision và scale được thiết kế phù hợp.
2. Lưu số nguyên theo đơn vị nhỏ nhất của currency, ví dụ cent hoặc đơn vị minor unit, kèm currency code.

Cách lưu số nguyên chỉ phù hợp khi scale của đơn vị được quản lý rõ. Một số currency không dùng hai chữ số thập phân; một số nghiệp vụ còn có quy tắc scale cho tỷ giá, thuế hoặc giá đơn vị khác với số tiền thanh toán cuối cùng.

Trong Java, dùng BigDecimal cho phép tính thập phân chính xác và chỉ rõ quy tắc làm tròn:

~~~java
BigDecimal unitPrice = new BigDecimal("19.95");
BigDecimal quantity = new BigDecimal("3");

BigDecimal lineTotal = unitPrice.multiply(quantity);
BigDecimal tax = lineTotal
    .multiply(new BigDecimal("0.10"))
    .setScale(2, RoundingMode.HALF_UP);
~~~

Khởi tạo BigDecimal từ chuỗi thập phân giúp tránh đưa sai số nhị phân của double vào giá trị ban đầu. Không nên dùng new BigDecimal(0.1) khi muốn biểu diễn chính xác 0.1 thập phân.

Quy tắc làm tròn phải được thống nhất giữa ứng dụng và database. Nếu database làm tròn mỗi dòng còn ứng dụng chỉ làm tròn tổng cuối cùng, kết quả có thể khác. Cần xác định làm tròn ở cấp đơn giá, dòng hàng, hóa đơn hay tổng thanh toán.

## 9. Tràn số, làm tròn và kiểu kết quả của phép tính

Ngay cả khi mỗi giá trị đầu vào nằm trong miền hợp lệ, phép tính trung gian có thể vượt giới hạn kiểu dữ liệu. Ví dụ, nhân số lượng lớn với đơn giá hoặc tổng hàng triệu giao dịch có thể vượt precision ban đầu.

Khi thiết kế, hãy xem:

- Kiểu kết quả của phép nhân và phép chia.
- Scale được giữ hoặc suy ra như thế nào.
- SUM có dùng kiểu kết quả rộng hơn kiểu cột không.
- Overflow có gây lỗi, wraparound hay chuyển đổi theo cách riêng không.
- ROUND và CAST được áp dụng trước hay sau phép tổng hợp.
- Giá trị NULL ảnh hưởng đến phép tính ra sao.

Không giả định mọi hệ quản trị suy ra precision/scale giống nhau. Hãy đọc tài liệu của nền tảng và kiểm tra kiểu kết quả bằng truy vấn mẫu. Với các phép tính quan trọng, có thể CAST sang precision phù hợp trước khi tính hoặc tại điểm tổng hợp, nhưng phải bảo đảm không làm mất thông tin cần thiết.

Ví dụ:

~~~sql
SELECT SUM(CAST(quantity AS NUMERIC(18, 0))
         * CAST(unit_price AS NUMERIC(18, 4)))
FROM order_items;
~~~

Đây chỉ là minh họa việc chọn kiểu rõ ràng; precision thực tế phải dựa trên miền giá trị và giới hạn của hệ quản trị. Không copy precision trong ví dụ vào production mà chưa tính giới hạn tối đa.

## 10. Chi phí chuyển đổi kiểu dữ liệu

Chuyển đổi kiểu có thể phát sinh ở nhiều vị trí:

- Khi đọc dữ liệu từ database vào driver.
- Khi bind tham số vào câu SQL.
- Khi so sánh cột với literal hoặc tham số khác kiểu.
- Khi nối hai bảng có cột khóa khác kiểu.
- Khi tính toán giữa các kiểu số khác nhau.
- Khi sắp xếp hoặc nhóm theo biểu thức đã chuyển đổi.
- Khi chuyển timezone hoặc format thời gian trong truy vấn.

Một lần chuyển đổi không nhất thiết là nút thắt. Chuyển đổi một tham số một lần thường nhỏ hơn việc chuyển đổi hàng triệu giá trị cột. Điều cần chú ý là chuyển đổi có bị lặp theo từng hàng hay làm thay đổi đường truy cập dữ liệu hay không.

Ví dụ, so sánh cột số nguyên với tham số văn bản có thể khiến hệ quản trị phải chuyển đổi một phía theo quy tắc ưu tiên kiểu. Tùy hệ quản trị, phép chuyển đổi có thể được áp dụng lên cột và làm điều kiện khó tận dụng chỉ mục. Một số hệ quản trị có thể tự chuyển tham số sang kiểu cột và vẫn dùng index seek. Không nên suy đoán; hãy đọc kế hoạch và kiểm tra implicit conversion.

### 10.1. Chuyển đổi trên cột và trên tham số

Giả sử cột customer_id có kiểu BIGINT. Cách bind tham số đúng kiểu:

~~~sql
WHERE customer_id = :customer_id
~~~

Ứng dụng bind :customer_id dưới dạng BIGINT hoặc kiểu số tương thích. Nếu ứng dụng gửi chuỗi tùy định dạng, hệ quản trị có thể phải parse hoặc chuyển đổi.

Nếu truy vấn viết:

~~~sql
WHERE CAST(customer_id AS VARCHAR(30)) = :customer_id_text
~~~

hệ quản trị có thể phải tính CAST cho nhiều hàng, làm giảm khả năng dùng chỉ mục thông thường trên customer_id. Nếu cần tìm theo chuỗi, hãy parse và xác thực chuỗi thành BIGINT trước khi bind, nếu ngữ nghĩa cho phép.

Có ngoại lệ: nếu đã tạo expression index hoặc computed-column index đúng biểu thức, hệ quản trị có thể dùng chỉ mục đó. Nhưng đây là quyết định thiết kế riêng, cần đo và duy trì đồng bộ.

### 10.2. Chuyển đổi ngầm trong JOIN

Hai bảng có khóa nối cùng ý nghĩa nhưng khác kiểu có thể gây chuyển đổi trong phép nối:

~~~sql
SELECT ...
FROM orders AS o
JOIN customers AS c
  ON o.customer_id = c.customer_code;
~~~

Nếu o.customer_id là BIGINT còn c.customer_code là VARCHAR, hệ quản trị có thể phải chuyển đổi một phía. Điều này có thể tăng CPU, làm sai thứ tự so sánh với dữ liệu không hợp lệ hoặc cản trở index lookup.

Mô hình tốt nên dùng cùng kiểu dữ liệu, cùng quy tắc collation và cùng miền giá trị cho các khóa liên kết. Nếu không thể thay đổi ngay, hãy xác định quy tắc chuyển đổi rõ ràng, kiểm tra dữ liệu không hợp lệ và đánh giá kế hoạch.

## 11. Sargability và chỉ mục

Một predicate sargable là điều kiện có thể được chuyển thành vùng tìm kiếm hoặc điều kiện truy cập hiệu quả trên chỉ mục. Kiểu dữ liệu và phép chuyển đổi ảnh hưởng trực tiếp đến khả năng này.

Ví dụ, nếu created_at có chỉ mục B-tree, điều kiện sau thường thuận lợi:

~~~sql
WHERE created_at >= :start_time
  AND created_at <  :end_time
~~~

Điều kiện sau có thể khó dùng chỉ mục gốc:

~~~sql
WHERE CAST(created_at AS DATE) = :target_date
~~~

Tương tự, với số:

~~~sql
WHERE amount >= :minimum_amount
~~~

thường dễ tận dụng chỉ mục hơn khi cột được bọc trong biểu thức chuyển đổi:

~~~sql
WHERE CAST(amount AS VARCHAR(40)) = :amount_text
~~~

Một số biểu thức có thể được hỗ trợ bằng expression index, computed column được lập chỉ mục hoặc function-based index. Nhưng nếu workload thường truy vấn theo một kiểu chuẩn, lưu dữ liệu đúng kiểu ngay từ đầu thường đơn giản hơn.

Đừng chỉ kiểm tra xem tên index có xuất hiện trong EXPLAIN hay không. Hãy xem điều kiện nào được dùng để tìm kiếm, điều kiện nào chỉ là filter, số hàng được đọc và số hàng trả về.

## 12. Kiểu dữ liệu trong phép JOIN, UNION và so sánh

Các phép kết hợp dữ liệu đòi hỏi kiểu tương thích:

- JOIN trên khóa có cùng kiểu và quy tắc so sánh.
- UNION/UNION ALL phải xác định kiểu kết quả chung cho từng cột.
- CASE có nhiều nhánh cần kiểu kết quả tương thích.
- COALESCE có thể kích hoạt quy tắc chuyển kiểu giữa các đối số.
- So sánh số nguyên với decimal hoặc float cần hiểu độ chính xác và thứ tự ưu tiên kiểu.
- So sánh chuỗi cần xét collation và chuẩn hóa.

Ví dụ, UNION giữa cột timestamp và chuỗi ngày có thể khiến hệ quản trị chuyển đổi theo quy tắc riêng hoặc báo lỗi. Hãy CAST rõ ràng tại ranh giới khi cần, thay vì để kiểu kết quả phụ thuộc vào thứ tự nhánh hoặc cấu hình session.

Nếu UNION ALL kết hợp hàng triệu dòng, chuyển đổi kiểu có thể được thực hiện trên lượng dữ liệu lớn. Chuẩn hóa kiểu trong các nguồn hoặc staging table có thể giảm công việc lặp, nhưng phải tính cả chi phí chuẩn hóa và lưu trữ.

## 13. Chuẩn hóa, đơn vị đo và mã hóa giá trị

Kiểu dữ liệu chỉ là một phần; đơn vị và quy ước cũng cần rõ ràng. Một cột duration có thể lưu mili giây nhưng tên cột không thể hiện điều đó. Một cột distance có thể là mét ở dịch vụ này và kilomet ở dịch vụ khác. Một giá trị tiền có thể được hiểu là đơn vị chính hoặc đơn vị nhỏ nhất.

Các quy ước nên được thể hiện bằng:

- Tên cột có đơn vị khi cần, ví dụ duration_ms hoặc amount_minor.
- Kiểu dữ liệu phù hợp với miền giá trị.
- Currency code, unit code hoặc metadata tương ứng.
- Quy tắc scale và rounding được ghi trong hợp đồng dữ liệu.
- Quy tắc timezone cho các cột thời gian.
- Kiểm tra constraint cho giá trị nằm trong miền hợp lệ.

Không nên mã hóa giá trị số thành chuỗi có dấu phân cách hàng nghìn hoặc dấu phẩy thập phân theo locale. Ví dụ "1.234,50" là định dạng hiển thị, không phải dạng lưu trữ số ổn định. Lưu số theo kiểu numeric rồi định dạng ở tầng trình bày.

## 14. Chi phí lưu trữ, chỉ mục và bộ nhớ

Kiểu dữ liệu rộng hơn có thể làm tăng kích thước hàng, chỉ mục, trang dữ liệu và lượng dữ liệu truyền. Điều này ảnh hưởng đến cache, I/O, backup và replication. Tuy nhiên, cách lưu vật lý của từng kiểu phụ thuộc hệ quản trị, precision, scale, encoding và cấu trúc hàng.

Một số nguyên có thể nhỏ gọn hơn một decimal precision lớn, nhưng nếu phải chuyển đổi liên tục hoặc không đủ miền giá trị thì lựa chọn đó có thể gây lỗi hoặc chi phí ứng dụng. Timestamp precision cao có thể cần thêm dung lượng ở một số nền tảng, nhưng không thể khẳng định mọi database đều tăng kích thước theo cùng cách.

Khi chọn kiểu, hãy cân nhắc:

- Miền giá trị cần hỗ trợ.
- Precision/scale thật sự cần.
- Số cột và số hàng của bảng.
- Cột có nằm trong chỉ mục hoặc khóa nối không.
- Kích thước index entry và độ rộng hàng.
- Tần suất đọc/ghi và lượng dữ liệu truyền.
- Chi phí chuyển đổi giữa database và ứng dụng.

Đo kích thước bảng và chỉ mục trước/sau khi thay đổi kiểu. Với bảng lớn, một thay đổi kiểu có thể cần rewrite dữ liệu, rebuild index, khóa hoặc tạo tải I/O lớn tùy hệ quản trị. Phải đọc tài liệu migration và thử trên dữ liệu đại diện.

## 15. Lựa chọn kiểu trong Java và JDBC

Ứng dụng Java nên dùng kiểu có ngữ nghĩa tương ứng thay vì ép mọi giá trị thành String, long hoặc double.

| Ý nghĩa | Kiểu Java thường phù hợp | Lưu ý |
|---|---|---|
| Ngày lịch | LocalDate | Không chứa giờ hoặc múi giờ |
| Giờ địa phương | LocalTime | Không xác định instant |
| Ngày giờ địa phương | LocalDateTime | Cần zone/offset để xác định instant |
| Thời điểm tuyệt đối | Instant | Phù hợp biểu diễn thời điểm trên dòng thời gian |
| Ngày giờ có offset | OffsetDateTime | Mang offset tại thời điểm đó |
| Vùng thời gian | ZoneId | Chứa định danh vùng và quy tắc timezone database |
| Tiền hoặc số thập phân chính xác | BigDecimal | Chọn scale và rounding rõ ràng |
| Số nguyên trong miền giới hạn | long hoặc BigInteger | Kiểm tra overflow và đơn vị |
| Số gần đúng | double | Dùng khi sai số được chấp nhận |

Khi bind JDBC, ưu tiên phương thức và kiểu tương ứng với cột, ví dụ setBigDecimal cho NUMERIC/DECIMAL, setLong cho BIGINT và các kiểu temporal được driver hỗ trợ. Cách ánh xạ chính xác phụ thuộc phiên bản JDBC driver và hệ quản trị.

Tránh lấy một LocalDateTime rồi tự gắn UTC nếu giá trị thực sự là giờ địa phương ở một vùng khác. Cần chuyển đổi qua ZoneId đúng. Tương tự, không chuyển BigDecimal sang double chỉ để truyền tham số nếu yêu cầu chính xác thập phân.

## 16. Migration khi thay đổi kiểu dữ liệu

Thay đổi kiểu dữ liệu trên bảng lớn cần được xem như một thay đổi vận hành, không chỉ là sửa một dòng DDL.

Các bước cần cân nhắc:

1. Xác định kiểu cũ, kiểu mới và miền giá trị.
2. Kiểm tra dữ liệu hiện tại có chuyển đổi được không.
3. Xác định quy tắc làm tròn, cắt phần thập phân, timezone và xử lý NULL.
4. Kiểm tra constraint, index, foreign key, view, procedure và ứng dụng phụ thuộc.
5. Ước lượng kích thước mới và thời gian chuyển đổi.
6. Xem việc ALTER có rewrite bảng, rebuild index hoặc khóa truy cập không.
7. Thử trên bản sao dữ liệu gần với production.
8. Chọn chiến lược migration: trực tiếp, cột mới và backfill, hoặc dual-write có kiểm soát.
9. Đối chiếu số hàng, tổng, min/max và các giá trị biên sau chuyển đổi.
10. Triển khai ứng dụng và schema theo thứ tự tương thích.
11. Theo dõi kế hoạch truy vấn, lỗi conversion, CPU và I/O.
12. Có phương án rollback hoặc phục hồi dữ liệu.

Với bảng lớn, chiến lược thêm cột mới, backfill theo batch rồi chuyển đọc/ghi có thể giảm thời gian khóa dài, nhưng làm tăng độ phức tạp và cần xử lý đồng bộ giữa hai cột. Không áp dụng máy móc; hãy xem khả năng online DDL và giới hạn của hệ quản trị.

## 17. Kiểm chứng tính đúng đắn và hiệu năng

Sau khi chuẩn hóa kiểu dữ liệu hoặc thay đổi precision, cần kiểm tra cả dữ liệu và kế hoạch.

### 17.1. Kiểm tra dữ liệu

- Số hàng trước/sau.
- Giá trị NULL và giá trị mặc định.
- Min/max và các giá trị sát giới hạn.
- Giá trị có phần thập phân tại ranh giới scale.
- Timestamp ở đầu/cuối ngày và quanh DST.
- Các bản ghi có cùng timestamp.
- Khóa nối và số hàng khớp giữa các bảng.
- Tổng số tiền hoặc tổng số lượng trước/sau.
- Giá trị vượt miền hoặc không parse được.

Đối với số thập phân, tạo test cho giá trị đúng scale, nhiều chữ số hơn scale, giá trị âm, giá trị lớn nhất và kết quả phép chia. Xác nhận quy tắc rounding thực sự được áp dụng như hợp đồng nghiệp vụ.

Đối với thời gian, test instant UTC, giờ địa phương, offset khác nhau, ngày DST, ngày nhuận và mốc precision thấp/cao. Không chỉ kiểm tra một timestamp thông thường.

### 17.2. Kiểm tra kế hoạch và workload

Dùng EXPLAIN hoặc công cụ tương đương để xem:

- Có implicit conversion trên cột hay không.
- Điều kiện có còn là index seek/range scan không.
- JOIN có chuyển sang thuật toán hoặc thứ tự khác không.
- Estimated rows có sai lệch đáng kể không.
- Sort, hash và spill có thay đổi không.
- Partition pruning có còn hoạt động không.
- Số trang đọc, CPU và elapsed time thay đổi thế nào.

Đo trước/sau với cùng tham số và dữ liệu đại diện. Theo dõi p50, p95, p99, thông lượng và tỷ lệ lỗi. Một thay đổi có thể làm một truy vấn nhanh hơn nhưng ảnh hưởng các truy vấn khác dùng chung cột hoặc chỉ mục.

## 18. Ví dụ xuyên suốt: chuẩn hóa cột thời gian và số tiền

Giả sử bảng orders đang có:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    created_at_text VARCHAR(40),
    amount_text VARCHAR(40)
);
~~~

Dữ liệu thời gian và số tiền được lưu dưới dạng chuỗi. Ứng dụng phải parse chúng, và truy vấn thường viết:

~~~sql
SELECT order_id, amount_text
FROM orders
WHERE CAST(created_at_text AS TIMESTAMP) >= :start_time
  AND CAST(created_at_text AS TIMESTAMP) < :end_time;
~~~

Điều kiện này có thể buộc database chuyển đổi từng giá trị, phụ thuộc định dạng, locale và khả năng optimizer. Chỉ mục trên created_at_text không tự động tương đương chỉ mục trên timestamp đã chuyển đổi.

Một mô hình đích có thể là:

~~~sql
CREATE TABLE orders_new (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP,
    amount NUMERIC(18, 2)
);
~~~

Kiểu TIMESTAMP ở ví dụ chỉ là minh họa. Nếu created_at biểu diễn instant, hãy chọn kiểu và quy ước timezone phù hợp với hệ quản trị. Nếu amount có nhiều currency, lưu thêm currency code và áp dụng scale theo quy tắc nghiệp vụ.

Quy trình chuyển đổi:

1. Phân tích định dạng chuỗi cũ và xác định timezone nguồn.
2. Kiểm tra chuỗi sai định dạng, giá trị NULL và giá trị vượt miền.
3. Chuyển thành kiểu thời gian và NUMERIC theo quy tắc được thống nhất.
4. Đối chiếu số hàng và tổng tiền theo nhóm.
5. Tạo chỉ mục trên cột thời gian mới nếu workload cần.
6. Viết truy vấn dùng tham số kiểu tương ứng và khoảng nửa mở.
7. So sánh kế hoạch, số hàng đọc, CPU, I/O và phân vị.
8. Chuyển ứng dụng sang cột mới khi dữ liệu đã được xác nhận.

Truy vấn sau khi chuẩn hóa:

~~~sql
SELECT order_id, amount
FROM orders_new
WHERE created_at >= :start_time
  AND created_at < :end_time;
~~~

Nếu tạo chỉ mục B-tree trên created_at, điều kiện trực tiếp có thể cho phép range scan. Tuy nhiên, nếu phần lớn bảng nằm trong khoảng truy vấn, optimizer vẫn có thể chọn sequential scan. Hãy để kế hoạch và số liệu thực tế quyết định hiệu quả.

## 19. Các sai lầm thường gặp

- **Lưu thời gian dưới dạng chuỗi.** So sánh và sắp xếp có thể phụ thuộc định dạng, locale và chuyển đổi.
- **Nhầm LocalDateTime với Instant.** Giờ địa phương không tự xác định thời điểm tuyệt đối.
- **Giả định mọi TIMESTAMP đều lưu UTC.** Ngữ nghĩa phụ thuộc hệ quản trị, kiểu cột và session.
- **Cộng cố định 24 giờ để tạo ngày kế tiếp.** Ngày lịch ở vùng DST có thể dài 23 hoặc 25 giờ.
- **Dùng FLOAT cho tiền cần chính xác.** Sai số nhị phân có thể ảnh hưởng so sánh và tổng.
- **Chọn precision/scale quá nhỏ.** Giá trị có thể bị làm tròn hoặc tràn số.
- **Chọn precision quá lớn không có lý do.** Có thể tăng dung lượng và chi phí tính toán.
- **Để implicit conversion trong JOIN.** Hai khóa cùng ý nghĩa nhưng khác kiểu có thể làm tăng CPU hoặc giảm khả năng dùng index.
- **CAST cột trong WHERE.** Có thể làm điều kiện mất khả năng tìm kiếm bằng chỉ mục gốc.
- **Chuyển đổi bằng chuỗi phụ thuộc locale.** Cùng một chuỗi có thể được hiểu khác giữa môi trường.
- **Chỉ kiểm tra dữ liệu thông thường.** Lỗi thường xuất hiện ở ranh giới precision, overflow, NULL và DST.
- **Chỉ đo một truy vấn.** Thay đổi kiểu có thể ảnh hưởng toàn bộ workload dùng chung cột.

## 20. Checklist mô hình hóa thời gian và số

- [ ] Ý nghĩa của từng cột thời gian đã rõ: instant, local date, local time hay duration.
- [ ] Quy ước timezone và session được xác định.
- [ ] Ranh giới ngày được tạo theo lịch và múi giờ nghiệp vụ.
- [ ] Precision timestamp phù hợp với nguồn dữ liệu và driver.
- [ ] Khoảng thời gian liên tiếp dùng ranh giới nửa mở khi phù hợp.
- [ ] Tiền và giá trị thập phân chính xác dùng DECIMAL/NUMERIC hoặc số nguyên theo đơn vị nhỏ nhất có quy ước.
- [ ] Precision, scale và miền giá trị được tính cho cả kết quả trung gian.
- [ ] Quy tắc làm tròn và xử lý overflow được thống nhất.
- [ ] Các cột khóa JOIN dùng kiểu dữ liệu và quy tắc so sánh tương thích.
- [ ] Tham số được bind đúng kiểu; không phụ thuộc chuỗi locale.
- [ ] Không có implicit conversion không mong muốn trên cột được lập chỉ mục.
- [ ] Kế hoạch vẫn tận dụng index range scan hoặc partition pruning khi phù hợp.
- [ ] Migration đã được thử với dữ liệu đại diện và có phương án phục hồi.
- [ ] Đã kiểm tra giá trị biên, DST, NULL, precision và overflow.
- [ ] Đã đo p50/p95/p99, CPU, I/O, số hàng đọc và tác động lên workload liên quan.

## 21. Nguyên tắc cần ghi nhớ

Kiểu dữ liệu phải phản ánh đúng ý nghĩa nghiệp vụ và miền giá trị. Thời điểm tuyệt đối, ngày địa phương, giờ lịch và thời lượng cần được phân biệt; số thập phân chính xác và số dấu phẩy động gần đúng cần được chọn theo yêu cầu tính toán. Precision, scale, timezone và quy tắc làm tròn phải được thống nhất giữa database, ứng dụng và driver.

Chuyển đổi kiểu có thể cần thiết, nhưng chuyển đổi lặp trên hàng triệu giá trị hoặc chuyển đổi ngầm trong điều kiện lọc và JOIN có thể làm tăng CPU và cản trở sử dụng chỉ mục. Hãy chuẩn hóa kiểu ở ranh giới dữ liệu, bind tham số đúng kiểu, giữ điều kiện có thể tìm kiếm và kiểm tra kế hoạch thực thi. Mọi thay đổi mô hình cần được xác nhận bằng kiểm tra giá trị biên, tính đúng đắn, dung lượng và hiệu năng trên workload đại diện.
