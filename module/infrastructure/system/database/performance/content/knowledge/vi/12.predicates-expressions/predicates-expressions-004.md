# Điều kiện thời gian: khoảng nửa mở, múi giờ và tránh biến đổi cột

Truy vấn theo thời gian xuất hiện trong hầu hết hệ thống giao dịch: lấy đơn hàng trong ngày, tìm sự kiện của một tháng, đọc log trong một khoảng giờ hoặc phân trang theo thời điểm tạo. Những điều kiện này có thể trở thành nút thắt hiệu năng nếu truy vấn biến đổi từng giá trị của cột thời gian, dùng sai ranh giới hoặc so sánh các kiểu dữ liệu không tương thích. Kết quả còn có thể sai khi ứng dụng không xử lý đúng múi giờ và giờ mùa hè.

Trong chương **Điều kiện và biểu thức** của module **DATABASE_PERFORMANCE**, bài học này trình bày cách viết điều kiện thời gian bằng khoảng nửa mở, chuyển ranh giới lịch địa phương thành thời điểm chính xác, giữ điều kiện có thể tận dụng chỉ mục và kiểm chứng kế hoạch thực thi. Module rèn phương pháp tối ưu hiệu năng dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, một điều kiện thời gian tốt cần đồng thời bảo toàn ngữ nghĩa nghiệp vụ, giảm lượng dữ liệu phải đọc và hoạt động đúng với độ chính xác của kiểu dữ liệu cùng quy tắc múi giờ.

## 1. Vì sao điều kiện thời gian cần được thiết kế cẩn thận?

Một cột thời gian thường được dùng để lọc theo ngày, giờ, tháng hoặc một khoảng nghiệp vụ. Có thể có hàng triệu hoặc hàng tỷ bản ghi, trong khi truy vấn chỉ cần một ngày hoặc vài phút dữ liệu. Nếu điều kiện không phù hợp với chỉ mục, hệ quản trị có thể phải đọc nhiều trang rồi mới loại bỏ phần lớn hàng.

Một điều kiện thời gian cần trả lời chính xác:

- Khoảng thời gian bắt đầu tại thời điểm nào?
- Ranh giới cuối có được tính vào kết quả không?
- Mốc thời gian thuộc múi giờ nào?
- Cột lưu thời điểm tuyệt đối hay giờ lịch không kèm múi giờ?
- Độ chính xác của cột là giây, mili giây hay micro giây?
- Tham số ứng dụng có cùng kiểu và quy tắc chuyển đổi với cột không?
- Điều kiện có cho phép bộ tối ưu tìm một vùng khóa trong chỉ mục không?
- Truy vấn có thể loại bỏ các phân vùng không liên quan không?

Sai ranh giới có thể làm thiếu hoặc trùng dữ liệu giữa hai lần truy vấn liên tiếp. Sai múi giờ có thể khiến bản ghi rơi vào ngày nghiệp vụ khác. Áp dụng hàm lên cột có thể làm hệ quản trị khó dùng chỉ mục B-tree thông thường. Vì vậy, hiệu năng và tính đúng đắn phải được xem xét cùng nhau.

## 2. Dùng khoảng nửa mở [start, end)

Một cách biểu đạt ổn định cho truy vấn thời gian là dùng khoảng nửa mở:

\[
[start,\ end)
\]

Nghĩa là lấy các giá trị thỏa mãn:

- Giá trị lớn hơn hoặc bằng thời điểm bắt đầu.
- Giá trị nhỏ hơn thời điểm kết thúc.

Trong SQL:

~~~sql
WHERE created_at >= :start_time
  AND created_at <  :end_time
~~~

Cách viết này bao gồm start_time nhưng không bao gồm end_time. Nếu hai khoảng liền nhau, chúng có thể ghép lại mà không bị trùng hoặc bỏ sót ranh giới:

- Khoảng thứ nhất: [2026-04-01 00:00, 2026-04-02 00:00)
- Khoảng thứ hai: [2026-04-02 00:00, 2026-04-03 00:00)

Một bản ghi đúng tại 00:00 ngày 02-04 thuộc khoảng thứ hai, không thuộc khoảng thứ nhất. Mỗi thời điểm chỉ được phân vào một khoảng.

### 2.1. Vì sao không nên kết thúc bằng 23:59:59?

Cách viết sau thường gặp nhưng không an toàn:

~~~sql
WHERE created_at BETWEEN
      TIMESTAMP '2026-04-01 00:00:00'
  AND TIMESTAMP '2026-04-01 23:59:59'
~~~

BETWEEN bao gồm cả hai đầu mút. Điều kiện này có thể bỏ sót bản ghi lúc 23:59:59.500 nếu cột lưu mili giây, hoặc 23:59:59.999999 nếu cột lưu micro giây. Nếu đổi mốc kết thúc thành 23:59:59.999999, truy vấn vẫn phụ thuộc độ chính xác và cách làm tròn của kiểu dữ liệu, driver và hệ quản trị.

Dùng mốc bắt đầu ngày kế tiếp với toán tử nhỏ hơn sẽ tránh phải đoán giá trị cuối cùng có thể biểu diễn:

~~~sql
WHERE created_at >= TIMESTAMP '2026-04-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-04-02 00:00:00'
~~~

Đây là mẫu phù hợp cho khoảng ngày liên tiếp, miễn là hai mốc được tạo theo đúng múi giờ và kiểu dữ liệu của cột.

### 2.2. Vì sao không dùng BETWEEN cho hai đầu mút?

BETWEEN tương đương với điều kiện lớn hơn hoặc bằng đầu dưới và nhỏ hơn hoặc bằng đầu trên. Nó phù hợp khi nghiệp vụ thật sự muốn bao gồm cả hai giá trị biên. Với các khoảng thời gian liền nhau, đầu cuối bao gồm có thể làm một bản ghi ở ranh giới được tính hai lần.

Nếu cần chia dữ liệu theo ngày, giờ hoặc tháng, khoảng nửa mở thường dễ ghép, dễ phân trang và ít phụ thuộc độ chính xác hơn.

## 3. Tạo ranh giới ngày từ múi giờ nghiệp vụ

Một ngày trên lịch không phải lúc nào cũng tương đương 24 giờ tuyệt đối. Ngày được hiểu theo múi giờ nghiệp vụ. Ví dụ, báo cáo doanh thu ngày tại Việt Nam thường cần tính từ nửa đêm theo múi giờ **Asia/Ho_Chi_Minh** đến nửa đêm ngày kế tiếp theo cùng múi giờ.

Quy trình nên là:

1. Nhận ngày lịch mà nghiệp vụ yêu cầu.
2. Xác định múi giờ nghiệp vụ.
3. Tạo thời điểm bắt đầu ngày tại múi giờ đó.
4. Tạo thời điểm bắt đầu ngày kế tiếp tại cùng múi giờ.
5. Chuyển cả hai mốc thành kiểu thời điểm phù hợp với cột và hệ quản trị.
6. Truy vấn theo điều kiện lớn hơn hoặc bằng start và nhỏ hơn end.

Không nên lấy thời điểm bắt đầu rồi cộng cố định 24 giờ để suy ra ngày kế tiếp trong mọi múi giờ. Ở các vùng có chuyển đổi giờ mùa hè (DST), một ngày địa phương có thể dài 23 hoặc 25 giờ. Hãy cộng một ngày lịch trong múi giờ rồi chuyển mỗi ranh giới thành instant tương ứng.

### 3.1. Ví dụ với Java

~~~java
LocalDate businessDate = LocalDate.of(2026, 4, 1);
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInstant = businessDate
    .atStartOfDay(businessZone)
    .toInstant();

Instant endInstant = businessDate
    .plusDays(1)
    .atStartOfDay(businessZone)
    .toInstant();

PreparedStatement statement = connection.prepareStatement("""
    SELECT order_id, created_at, total
    FROM orders
    WHERE created_at >= ?
      AND created_at < ?
    """);

statement.setTimestamp(1, Timestamp.from(startInstant));
statement.setTimestamp(2, Timestamp.from(endInstant));
~~~

Ví dụ này minh họa khi cột được quy ước lưu instant theo UTC và driver ánh xạ Timestamp theo cách tương thích với quy ước đó. JDBC driver, kiểu cột và cấu hình session có thể ảnh hưởng cách chuyển đổi. Hãy xác nhận hợp đồng thời gian giữa ứng dụng, driver và hệ quản trị; không giả định mọi cột TIMESTAMP có cùng ngữ nghĩa.

Với cột và driver hỗ trợ kiểu có offset hoặc instant, có thể bind OffsetDateTime hay kiểu tương ứng theo JDBC và tài liệu của nền tảng. Điều quan trọng là tính hai ranh giới bằng múi giờ nghiệp vụ trước, sau đó bind tham số có kiểu rõ ràng.

### 3.2. Múi giờ trong dữ liệu

Cần phân biệt:

- **Instant:** một thời điểm tuyệt đối trên dòng thời gian.
- **Local date/time:** ngày hoặc giờ trên lịch, không tự xác định được instant nếu thiếu múi giờ.
- **Offset:** độ lệch so với UTC tại một thời điểm, ví dụ +07:00.
- **Time zone:** quy tắc lịch sử và tương lai của một vùng, có thể thay đổi theo luật và DST.

Một timestamp không có thông tin múi giờ có thể chỉ là giờ lịch theo quy ước ứng dụng. Nếu nhiều dịch vụ ghi dữ liệu theo múi giờ khác nhau vào cùng một cột không có quy ước rõ ràng, việc so sánh và báo cáo sẽ dễ sai.

Hãy xác định một quy ước thống nhất: lưu instant theo UTC hoặc lưu local time kèm thông tin vùng/offset cần thiết. Dù chọn cách nào, phải ghi rõ quy tắc ở ranh giới ứng dụng và khi truy vấn.

## 4. Tránh biến đổi cột thời gian trong điều kiện lọc

Một truy vấn thường được viết để lấy dữ liệu trong một ngày bằng cách áp dụng hàm lên từng giá trị cột:

~~~sql
WHERE DATE(created_at) = :target_date
~~~

Hoặc:

~~~sql
WHERE CAST(created_at AS DATE) = :target_date
~~~

Vấn đề là chỉ mục B-tree thông thường lưu khóa theo giá trị created_at, trong khi điều kiện lại so sánh kết quả của DATE(created_at) hoặc phép CAST. Bộ tối ưu có thể không chuyển biểu thức này thành một vùng tìm kiếm trên chỉ mục gốc. Hệ quản trị có thể phải tính hàm cho nhiều hàng rồi lọc.

Một cách biểu đạt theo khoảng thường dễ tận dụng chỉ mục hơn:

~~~sql
WHERE created_at >= :day_start
  AND created_at <  :next_day_start
~~~

Khi chỉ mục có khóa created_at, hệ quản trị có thể tìm vị trí bắt đầu và đọc đến trước mốc kết thúc. Đây thường được gọi là điều kiện có thể tìm kiếm bằng chỉ mục (sargable predicate).

Không phải mọi hàm trên cột đều chắc chắn làm mất chỉ mục trong mọi hệ quản trị. Bộ tối ưu có thể biến đổi một số biểu thức hoặc dùng expression index, computed-column index, function-based index hay cơ chế tương đương. Tuy nhiên, điều kiện theo khoảng là lựa chọn tổng quát dễ kiểm soát khi truy vấn lọc theo thời gian liên tục.

### 4.1. Phân biệt hàm trên tham số và hàm trên cột

Hàm áp dụng lên tham số đã tính trước thường không cản trở việc tìm kiếm theo cột:

~~~sql
WHERE created_at >= :start_time
  AND created_at <  :end_time
~~~

Ứng dụng có thể tính start_time và end_time trước khi gửi SQL. Ngược lại, nếu SQL phải tính DATE(created_at) cho từng hàng, điều kiện có thể khó sử dụng chỉ mục gốc.

Điều này không có nghĩa là không bao giờ được dùng hàm trong SQL. Hãy xác định biểu thức có nằm trên cột được lập chỉ mục hay không, hệ quản trị có chỉ mục biểu thức tương ứng hay không và kế hoạch thực tế cho thấy điều gì.

### 4.2. Truy vấn theo tháng

Tránh tạo ngày cuối tháng bằng cách đoán số ngày hoặc gắn thời điểm cuối ngày. Hãy tính ngày đầu tháng hiện tại và ngày đầu tháng tiếp theo trong ứng dụng hoặc bằng phép toán ngày được hệ quản trị hỗ trợ:

~~~sql
WHERE created_at >= :month_start
  AND created_at <  :next_month_start
~~~

Ví dụ, tháng 4 bắt đầu tại 2026-04-01 00:00 và kết thúc trước 2026-05-01 00:00 theo múi giờ nghiệp vụ đã chọn. Cách này tự xử lý tháng có 28, 29, 30 hoặc 31 ngày, miễn là các ranh giới được tạo đúng theo lịch.

## 5. Kiểu dữ liệu và chuyển đổi ngầm

Điều kiện có thể mất khả năng tận dụng chỉ mục hoặc tạo kết quả sai nếu hai vế so sánh có kiểu dữ liệu khác nhau và hệ quản trị phải chuyển đổi.

Ví dụ, cột created_at có kiểu timestamp nhưng tham số được bind như chuỗi văn bản. Hệ quản trị có thể chuyển đổi tham số, chuyển đổi cột hoặc áp dụng quy tắc so sánh theo kiểu dữ liệu và thứ tự ưu tiên kiểu riêng của nó.

Hãy ưu tiên:

- Bind tham số với kiểu tương ứng cột.
- Tránh truyền ngày giờ dưới dạng chuỗi tùy định dạng locale.
- Không dựa vào cách parse ngày tháng mặc định của session.
- Tránh ép kiểu trên cột trong điều kiện nếu không cần.
- Kiểm tra kế hoạch để biết có cast hoặc conversion gây ảnh hưởng không.
- Xác định rõ độ chính xác của timestamp và offset/múi giờ.

Ví dụ với JDBC, thay vì nối chuỗi ngày vào SQL, hãy dùng PreparedStatement và bind giá trị thời gian đã được tạo từ kiểu ngày giờ có cấu trúc. Điều này giảm lỗi định dạng, tránh SQL injection và giúp driver truyền kiểu dữ liệu rõ ràng hơn.

Không nên tự động cast mọi tham số sang kiểu cột mà chưa hiểu ngữ nghĩa. Ví dụ, chuyển một local timestamp thành UTC đòi hỏi biết múi giờ nguồn. Một phép cast đúng kiểu nhưng sai múi giờ vẫn tạo kết quả sai.

## 6. Độ chính xác timestamp và ranh giới truy vấn

Các hệ quản trị và kiểu dữ liệu có thể lưu độ chính xác khác nhau: giây, mili giây, micro giây hoặc mức khác. Driver cũng có thể làm tròn hoặc cắt phần thập phân khi bind tham số.

Khoảng nửa mở giúp tránh phải tạo mốc cuối cùng với độ chính xác tối đa của cột. Thay vì kết thúc tại 23:59:59.999999, hãy dùng mốc đầu ngày tiếp theo và toán tử nhỏ hơn.

Cần kiểm tra các tình huống:

- Cột lưu mili giây nhưng ứng dụng gửi micro giây.
- Driver làm tròn giá trị có độ chính xác vượt quá cột.
- Hệ quản trị chuẩn hóa hoặc cắt phần thập phân.
- Tham số được tạo từ đồng hồ ứng dụng có độ chính xác khác dữ liệu nguồn.
- Hai khoảng truy vấn liên tiếp có cùng một mốc end/start nhưng một bên dùng toán tử nhỏ hơn hoặc bằng gây trùng hàng.

Nếu dùng keyset pagination theo thời gian, chỉ dựa vào created_at có thể không đủ khi nhiều hàng có cùng timestamp. Hãy thêm khóa duy nhất làm tiêu chí phụ để tạo thứ tự ổn định, ví dụ:

~~~sql
WHERE created_at < :last_created_at
   OR (created_at = :last_created_at AND order_id < :last_order_id)
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Điều kiện tiếp trang phải phù hợp với hướng sắp xếp và kiểu khóa. Với chỉ mục nhiều cột, thứ tự (created_at DESC, order_id DESC) có thể hỗ trợ mẫu truy vấn này tùy hệ quản trị và kế hoạch.

## 7. Thiết kế chỉ mục cho điều kiện thời gian

Một điều kiện thời gian sargable chỉ là một phần của thiết kế truy cập. Cần xem các điều kiện khác trong workload.

Ví dụ:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant
  AND status = :status
  AND created_at >= :start_time
  AND created_at <  :end_time
ORDER BY created_at DESC;
~~~

Một chỉ mục B-tree ứng viên có thể là:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Ý tưởng:

- tenant_id và status có điều kiện bằng.
- created_at có điều kiện khoảng.
- created_at cũng hỗ trợ thứ tự kết quả trong vùng tiền tố tenant/status.
- Hệ quản trị có thể đọc vùng khóa liên quan thay vì quét toàn bảng.

Thứ tự cột cần dựa trên workload, độ chọn lọc và các truy vấn khác. Nếu nhiều truy vấn chỉ lọc tenant_id và khoảng created_at mà không có status, chỉ mục (tenant_id, created_at) có thể phù hợp hơn cho nhóm đó. Không nên thêm mọi hoán vị cột; hãy đo tần suất và chi phí đọc/ghi.

### 7.1. Điều kiện thời gian ở cột đầu hay cột sau?

Nếu truy vấn chỉ lọc theo khoảng created_at trên toàn bảng, chỉ mục bắt đầu bằng created_at thường tạo đường tìm kiếm trực tiếp. Nếu truy vấn lọc tenant_id bằng trước rồi mới lọc thời gian, chỉ mục (tenant_id, created_at) thường phù hợp với tiền tố.

Nếu cột thời gian nằm sau một cột không có điều kiện, vùng tìm kiếm có thể rộng hơn hoặc không liên tục. Hãy xem leftmost-prefix, số hàng được đọc và điều kiện nào thực sự trở thành index condition trong kế hoạch.

### 7.2. Chỉ mục bao phủ

Nếu truy vấn chỉ cần một số cột, có thể cân nhắc cột INCLUDE hoặc cơ chế bao phủ của hệ quản trị để giảm lookup về bảng. Tuy nhiên, cột bao phủ làm chỉ mục rộng hơn và tăng chi phí ghi. Với cột payload lớn, không nên thêm chỉ để tránh một vài lần đọc bảng nếu lợi ích không đáng kể.

## 8. Điều kiện thời gian và partition pruning

Bảng lớn thường được phân vùng theo thời gian, ví dụ mỗi tháng hoặc mỗi ngày. Truy vấn có điều kiện khoảng rõ ràng trên khóa phân vùng có thể cho phép hệ quản trị loại bỏ những phân vùng nằm ngoài khoảng cần đọc.

Ví dụ bảng events phân vùng theo created_at:

~~~sql
SELECT event_id, event_type
FROM events
WHERE created_at >= :start_time
  AND created_at <  :end_time;
~~~

Nếu ranh giới tham số tương thích với khóa phân vùng, hệ quản trị có thể chỉ truy cập các phân vùng giao với khoảng đó. Đây là partition pruning.

Nếu viết điều kiện thành:

~~~sql
WHERE DATE(created_at) = :target_date
~~~

khả năng pruning có thể giảm hoặc phụ thuộc vào việc hệ quản trị có thể suy luận ranh giới từ biểu thức hay không. Điều kiện trực tiếp trên khóa phân vùng thường dễ được tối ưu hơn.

Cần xem kế hoạch để xác nhận số phân vùng được truy cập. Không phải mọi hệ quản trị đều pruning theo cùng cách; một số hỗ trợ pruning lúc lập kế hoạch, một số còn có thể pruning lúc thực thi dựa trên tham số. Kiểu tham số và biểu thức có thể ảnh hưởng kết quả.

## 9. Tổng hợp theo ngày mà vẫn lọc bằng khoảng

Có trường hợp ứng dụng cần nhóm dữ liệu theo ngày hoặc tháng. Khi đó, phép chuyển đổi thời gian trong SELECT hoặc GROUP BY có thể hợp lý, nhưng điều kiện WHERE vẫn nên giới hạn vùng dữ liệu bằng khoảng trước.

Ví dụ:

~~~sql
SELECT DATE(created_at) AS order_day, COUNT(*)
FROM orders
WHERE created_at >= :start_time
  AND created_at <  :end_time
GROUP BY DATE(created_at)
ORDER BY order_day;
~~~

Ở đây, điều kiện WHERE giới hạn các hàng được đọc. Hàm DATE được dùng để gom nhóm kết quả. Cách nhóm ngày cần được xác định theo múi giờ nghiệp vụ. Nếu created_at lưu instant UTC nhưng báo cáo theo giờ Việt Nam, nhóm theo DATE(created_at) trong UTC có thể không đúng ngày địa phương.

Một số hệ quản trị hỗ trợ biểu thức chuyển múi giờ trong GROUP BY hoặc kiểu dữ liệu có ngữ nghĩa múi giờ riêng. Hãy chuyển instant sang múi giờ nghiệp vụ trước khi lấy ngày lịch, và kiểm tra việc nhóm không làm thay đổi điều kiện lọc có thể dùng chỉ mục.

## 10. Múi giờ và giờ mùa hè (DST)

DST là nguồn lỗi phổ biến khi tính khoảng thời gian bằng phép cộng cố định. Tại vùng có chuyển đổi giờ mùa hè, đồng hồ địa phương có thể nhảy qua một giờ hoặc lặp lại một giờ. Vì vậy:

- Một ngày lịch có thể dài 23 hoặc 25 giờ.
- Một giờ địa phương có thể không tồn tại khi đồng hồ nhảy tới.
- Một giờ địa phương có thể xuất hiện hai lần khi đồng hồ lùi.
- Offset UTC của một vùng có thể thay đổi theo ngày và quy định pháp luật.

Nếu nghiệp vụ dùng ngày lịch địa phương, hãy dùng thư viện timezone database để tính đầu ngày và đầu ngày kế tiếp. Không tự gắn offset cố định cho mọi ngày nếu vùng có DST hoặc quy định thay đổi.

Ví dụ, dùng ZoneId trong Java:

~~~java
LocalDate date = LocalDate.of(2026, 11, 1);
ZoneId zone = ZoneId.of("America/New_York");

Instant start = date.atStartOfDay(zone).toInstant();
Instant end = date.plusDays(1).atStartOfDay(zone).toInstant();
~~~

Ví dụ minh họa cách tạo ranh giới ngày theo vùng. Ngày cụ thể có DST hay không tùy năm và vùng. Thư viện thời gian xử lý quy tắc của vùng thay vì giả định một ngày luôn có 24 giờ.

Nếu ứng dụng cần truy vấn theo một khoảng giờ địa phương có thể mơ hồ hoặc không tồn tại, nghiệp vụ phải xác định cách xử lý: chọn offset sớm/muộn, từ chối đầu vào hay yêu cầu người dùng chỉ rõ offset. Không thể suy ra duy nhất một instant từ local date-time trong những trường hợp đó.

## 11. Phân biệt thời gian sự kiện và thời gian ghi nhận

Một bảng có thể lưu nhiều loại thời gian:

- occurred_at: thời điểm sự kiện thực sự xảy ra.
- created_at: thời điểm bản ghi được tạo trong hệ thống.
- received_at: thời điểm hệ thống nhận sự kiện.
- processed_at: thời điểm xử lý hoàn tất.
- business_date: ngày nghiệp vụ theo lịch địa phương.

Không nên thay thế lẫn nhau. Sự kiện có thể xảy ra ở thiết bị offline rồi được gửi lên sau vài giờ. Nếu báo cáo theo thời điểm xảy ra, lọc created_at sẽ cho kết quả khác. Nếu tính SLA xử lý, cần so sánh received_at với processed_at.

Khi thiết kế chỉ mục, hãy chọn đúng cột thời gian theo câu hỏi nghiệp vụ. Một chỉ mục trên created_at không tự động hỗ trợ truy vấn lọc occurred_at. Nếu workload quan trọng cần cả hai loại thời gian, hãy đo và thiết kế theo từng mẫu truy vấn.

## 12. Ví dụ xuyên suốt: lấy đơn hàng trong một ngày địa phương

Giả sử hệ thống lưu created_at như một instant theo quy ước UTC. Người dùng yêu cầu xem đơn hàng trong ngày 01-04-2026 theo múi giờ Asia/Ho_Chi_Minh.

### Bước 1: Xác định ngày và múi giờ

Ngày đầu vào là 2026-04-01. Múi giờ nghiệp vụ là Asia/Ho_Chi_Minh. Không lấy ngày UTC trực tiếp vì ngày địa phương có thể lệch so với UTC.

### Bước 2: Tạo hai ranh giới

Tính nửa đêm địa phương của ngày được chọn và nửa đêm địa phương ngày tiếp theo, rồi chuyển cả hai thành instant. Với Việt Nam, offset hiện tại là UTC+07:00; ứng dụng vẫn nên dùng tên vùng thay vì hard-code offset nếu cần phản ánh quy tắc vùng theo thời gian.

### Bước 3: Bind tham số có kiểu

Không nối chuỗi ngày vào SQL. Dùng PreparedStatement và bind hai instant theo cách tương thích với kiểu cột và JDBC driver.

### Bước 4: Viết điều kiện nửa mở

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :start_instant
  AND created_at <  :end_instant
ORDER BY created_at DESC;
~~~

### Bước 5: Kiểm tra chỉ mục và kế hoạch

Nếu workload luôn lọc theo tenant_id rồi đến khoảng created_at, chỉ mục (tenant_id, created_at) là một ứng viên để đánh giá. Dùng EXPLAIN để xem có range scan phù hợp, có sort bổ sung hay không và số hàng phải đọc.

### Bước 6: Kiểm tra kết quả biên

Tạo hoặc tìm bản ghi tại đúng start, ngay trước end và đúng end. Kết quả mong đợi:

- Bản ghi tại start được lấy.
- Bản ghi ngay trước end được lấy nếu nó nằm trong kiểu dữ liệu và độ chính xác hợp lệ.
- Bản ghi đúng tại end không được lấy; nó thuộc ngày tiếp theo.

### Bước 7: Đo dưới workload đại diện

So sánh p50, p95, p99, số hàng đọc, I/O, CPU và kế hoạch với nhiều tenant hoặc ngày có lượng dữ liệu khác nhau. Đừng chỉ đo một ngày ít dữ liệu rồi kết luận chỉ mục phù hợp cho mọi ngày.

## 13. Quy trình điều tra điều kiện thời gian chậm hoặc sai kết quả

Khi một truy vấn thời gian chậm hoặc trả về dữ liệu không đúng, có thể đi theo trình tự:

1. **Xác định ngữ nghĩa:** truy vấn theo instant, ngày địa phương hay giờ lịch? Múi giờ nghiệp vụ là gì?
2. **Xác định kiểu cột:** timestamp có/không có timezone, date, datetime hoặc kiểu riêng của hệ quản trị?
3. **Xác định độ chính xác:** cột và driver giữ đến mili giây, micro giây hay độ chính xác khác?
4. **Kiểm tra ranh giới:** dùng >= start và < end hay có đầu mút bị bao gồm hai lần?
5. **Kiểm tra chuyển đổi:** hàm hoặc CAST có đang áp dụng lên cột không? Tham số có cùng kiểu không?
6. **Kiểm tra kế hoạch:** điều kiện có trở thành index range condition hoặc partition pruning không?
7. **Kiểm tra số hàng:** estimated rows có gần actual rows không? Khoảng truy vấn có chọn lọc không?
8. **Kiểm tra chỉ mục:** thứ tự cột có khớp điều kiện bằng, khoảng và ORDER BY không?
9. **Kiểm tra tải:** CPU, I/O, lock wait, số trang đọc và phân vị có thay đổi không?
10. **Thử nghiệm:** so sánh điều kiện cũ và mới trên dữ liệu đại diện, xác nhận kết quả giống về ngữ nghĩa.

Khi thay đổi điều kiện, hãy kiểm tra dữ liệu ở các mốc biên, ngày chuyển DST, đầu/cuối tháng và khoảng có độ chính xác cao. Một truy vấn nhanh nhưng bỏ sót bản ghi ở cuối ngày không phải là tối ưu hợp lệ.

## 14. Các sai lầm thường gặp

- **Dùng BETWEEN cho khoảng ngày liền nhau.** Đầu cuối bao gồm có thể làm trùng hàng ở ranh giới.
- **Dùng 23:59:59 làm thời điểm cuối ngày.** Cách này phụ thuộc độ chính xác timestamp và có thể bỏ sót phần thập phân.
- **Áp dụng DATE hoặc CAST lên cột trong WHERE.** Điều kiện có thể không tận dụng được chỉ mục thông thường.
- **Cộng cố định 24 giờ để tìm ngày kế tiếp.** Ngày địa phương ở vùng DST có thể dài 23 hoặc 25 giờ.
- **Dùng offset cố định thay cho múi giờ nghiệp vụ.** Quy tắc vùng có thể thay đổi theo thời gian.
- **Bind timestamp dưới dạng chuỗi.** Định dạng và locale của session có thể gây chuyển đổi sai hoặc không nhất quán.
- **Bỏ qua độ chính xác của cột và driver.** Làm tròn hoặc cắt timestamp có thể thay đổi kết quả tại biên.
- **Nhóm ngày theo UTC khi nghiệp vụ cần ngày địa phương.** Kết quả báo cáo có thể bị lệch ngày.
- **Chỉ mục không khớp tiền tố.** Cột thời gian ở vị trí không phù hợp có thể khiến vùng quét rộng.
- **Chỉ kiểm tra tốc độ mà không kiểm tra dữ liệu biên.** Hiệu năng phải đi cùng tính đúng đắn.

## 15. Checklist thiết kế điều kiện thời gian

- [ ] Đã xác định truy vấn cần instant, ngày lịch hay giờ địa phương.
- [ ] Đã xác định múi giờ nghiệp vụ và quy ước lưu trữ của cột.
- [ ] Đã tạo ranh giới bằng lịch và timezone database phù hợp.
- [ ] Đã dùng khoảng nửa mở >= start và < end cho các khoảng liên tiếp.
- [ ] Không dùng mốc cuối ngày dựa trên 23:59:59 hoặc độ chính xác giả định.
- [ ] Đã tránh biến đổi cột trong WHERE nếu có thể dùng điều kiện khoảng.
- [ ] Tham số được bind với kiểu dữ liệu tương thích.
- [ ] Đã kiểm tra độ chính xác timestamp và hành vi làm tròn của driver.
- [ ] Đã xem khả năng range scan và partition pruning trong kế hoạch.
- [ ] Thứ tự chỉ mục phù hợp với điều kiện bằng, điều kiện khoảng và ORDER BY.
- [ ] Đã kiểm tra ngày có DST, đầu/cuối tháng và các mốc biên.
- [ ] Đã xác nhận không bỏ sót hoặc lấy trùng bản ghi.
- [ ] Đã đo lại độ trễ, số hàng đọc, I/O và phân vị trên workload đại diện.

## 16. Nguyên tắc cần ghi nhớ

Điều kiện thời gian nên biểu đạt chính xác khoảng nghiệp vụ và giữ khả năng truy cập dữ liệu hiệu quả. Khoảng nửa mở >= start và < end giúp ghép các khoảng liên tiếp mà không trùng hoặc bỏ sót ranh giới, đồng thời tránh phải đoán giá trị cuối cùng theo độ chính xác timestamp.

Hãy tạo ranh giới ngày theo múi giờ nghiệp vụ, xử lý DST bằng thư viện thời gian phù hợp, bind tham số đúng kiểu và tránh áp dụng hàm lên cột trong điều kiện lọc khi có thể dùng khoảng trực tiếp. Sau đó đọc kế hoạch để xác nhận range scan hoặc partition pruning, đo số hàng và I/O, rồi kiểm tra các giá trị biên. Một điều kiện thời gian tốt phải vừa trả đúng dữ liệu vừa giúp hệ quản trị đọc ít dữ liệu cần thiết hơn.
