# Thiết kế kịch bản từ giao dịch nghiệp vụ và tỷ lệ đọc ghi

Một bài kiểm thử hiệu năng cơ sở dữ liệu chỉ có ý nghĩa khi tải thử phản ánh cách ứng dụng thật sử dụng dữ liệu. Chạy một câu SELECT lặp lại hàng nghìn lần có thể đo được một đường truy cập cụ thể, nhưng không mô phỏng đầy đủ hệ thống bán hàng, ngân hàng hoặc quản lý kho. Trong thực tế, người dùng thực hiện nhiều loại giao dịch: tìm kiếm, xem chi tiết, tạo đơn, thanh toán, cập nhật trạng thái, hủy giao dịch và chạy báo cáo. Mỗi loại có số lần xuất hiện, số câu SQL, số hàng đọc/ghi, thời gian xử lý và mức độ đồng thời khác nhau.

Thiết kế kịch bản kiểm thử bắt đầu từ giao dịch nghiệp vụ, xác định tỷ trọng từng loại giao dịch, chuyển tỷ trọng đó thành tốc độ tải và mô hình đọc/ghi, rồi tạo dữ liệu và lịch chạy phù hợp. Nếu tỷ lệ đọc/ghi hoặc phân bố giao dịch sai, kết quả có thể dẫn đến quyết định sai về chỉ mục, bộ nhớ, I/O, connection pool và năng lực mở rộng.

Bài học thuộc chương **Kiểm thử hiệu năng** của module DATABASE_PERFORMANCE. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, kịch bản cần mô tả đúng giao dịch, tỷ lệ đọc ghi, dữ liệu được truy cập, tải đồng thời và số đo dùng để xác nhận kết quả.

## 1. Bắt đầu từ giao dịch nghiệp vụ

Giao dịch nghiệp vụ (business transaction) là một hành động mà người dùng hoặc hệ thống thực hiện để hoàn thành một mục tiêu nghiệp vụ. Nó có thể bao gồm nhiều request, nhiều câu SQL và một hoặc nhiều ranh giới transaction ở database.

Ví dụ trong một cửa hàng trực tuyến:

- Tìm kiếm sản phẩm.
- Xem thông tin và tồn kho của một sản phẩm.
- Thêm sản phẩm vào giỏ.
- Đặt hàng.
- Thanh toán.
- Cập nhật trạng thái giao hàng.
- Xem lịch sử đơn hàng.
- Chạy báo cáo doanh thu.

Không nên đồng nhất ba khái niệm:

| Khái niệm | Ví dụ | Ý nghĩa khi kiểm thử |
| --- | --- | --- |
| Hành động người dùng | Người mua đặt hàng | Đơn vị mô tả mục tiêu nghiệp vụ |
| Request/API | POST /orders | Một lần gọi từ client đến ứng dụng |
| Database transaction | Đọc tồn kho, ghi đơn, trừ tồn kho và commit | Đơn vị commit/rollback nhất quán ở database |
| SQL statement | SELECT, INSERT, UPDATE | Một thao tác SQL bên trong transaction |

Một lần đặt hàng có thể là một request, một transaction database và nhiều câu SQL. Một luồng đăng nhập có thể gồm nhiều request nhưng không nhất thiết dùng chung một transaction database. Khi xây dựng kịch bản, phải ghi rõ đang đếm đơn vị nào để tránh nhầm transaction rate với request rate hoặc statement rate.

### 1.1. Lập danh mục giao dịch

Liệt kê các giao dịch quan trọng theo tần suất và tác động:

| Nhóm | Giao dịch | Đặc điểm |
| --- | --- | --- |
| Đọc đơn giản | Xem chi tiết sản phẩm, hồ sơ | Ít thao tác, thường có thể dùng cache |
| Đọc có lọc | Tìm kiếm, lọc đơn hàng | Có điều kiện lọc, sort, pagination |
| Đọc tổng hợp | Dashboard, báo cáo | Quét nhiều hàng, GROUP BY, sort |
| Ghi đơn giản | Cập nhật địa chỉ, trạng thái | Ít hàng nhưng cần log và lock |
| Ghi nhiều bước | Checkout, thanh toán | Kết hợp đọc kiểm tra và nhiều thao tác ghi |
| Tác vụ nền | Đồng bộ, import, cleanup | Có thể chạy theo batch và tạo tải đột biến |

Không phải giao dịch nào cũng cần đưa vào mọi bài test. Hãy ưu tiên các giao dịch chiếm phần lớn lưu lượng, ảnh hưởng trực tiếp đến SLA, hoặc có nguy cơ tạo nút thắt như checkout, báo cáo lớn và batch cập nhật.

### 1.2. Mô tả luồng nghiệp vụ

Với mỗi giao dịch, ghi lại:

- Điều kiện bắt đầu và điều kiện kết thúc.
- Các bước ứng dụng thực hiện.
- Các câu SQL chính hoặc nhóm thao tác đọc/ghi.
- Ranh giới transaction và isolation level.
- Số hàng thường đọc, thêm, sửa hoặc xóa.
- Khóa dữ liệu được truy cập.
- Các bước có thể chờ dịch vụ ngoài hoặc người dùng.
- Kết quả cần đúng sau commit hoặc rollback.

Ví dụ luồng checkout:

~~~text
Người mua xác nhận giỏ hàng
          |
          v
Đọc giỏ hàng và giá hiện tại
          |
          v
Kiểm tra tồn kho
          |
          v
BEGIN DATABASE TRANSACTION
  Tạo order
  Tạo order items
  Giữ/trừ tồn kho
  Ghi payment intent hoặc trạng thái chờ
COMMIT
          |
          v
Gửi sự kiện / trả kết quả
~~~

Sơ đồ cần phản ánh đúng hệ thống thực tế. Nếu thanh toán qua cổng bên ngoài diễn ra sau khi database commit, không đưa thời gian chờ cổng thanh toán vào transaction database. Nếu nghiệp vụ dùng saga hoặc outbox, mô tả các ranh giới đó để bài test tạo đúng trạng thái và tải.

## 2. Xác định tỷ trọng giao dịch

Tỷ trọng giao dịch cho biết mỗi loại nghiệp vụ chiếm bao nhiêu phần trong tổng số giao dịch được chọn làm đơn vị đo. Các tỷ trọng phải có cùng mẫu số và cộng lại thành 100%.

Ví dụ một workload ứng dụng thương mại điện tử:

| Giao dịch | Tỷ trọng |
| --- | ---: |
| Tìm kiếm sản phẩm | 35% |
| Xem chi tiết sản phẩm | 30% |
| Xem lịch sử đơn hàng | 15% |
| Thêm vào giỏ | 8% |
| Checkout | 7% |
| Cập nhật hồ sơ | 3% |
| Hủy đơn | 2% |
| **Tổng** | **100%** |

Tỷ trọng này chỉ là ví dụ. Trong hệ thống thực, hãy lấy từ access log, APM, telemetry, thống kê API hoặc dữ liệu quan sát được trong một khoảng thời gian đại diện. Nếu dùng log production, cần loại bỏ thông tin nhận dạng và dữ liệu nhạy cảm trước khi đưa vào môi trường kiểm thử.

### 2.1. Dùng tỷ trọng theo số lần xảy ra

Nếu tổng tốc độ giao dịch nghiệp vụ là T transaction/giây và loại i chiếm tỷ trọng p_i, tốc độ của loại đó là:

\[
T_i = T \times p_i
\]

Với T = 200 giao dịch/giây và checkout chiếm 7%:

\[
T_{\text{checkout}} = 200 \times 0,07 = 14
\]

Kịch bản cần tạo trung bình 14 checkout mỗi giây. Các giao dịch khác được tính tương tự.

### 2.2. Tỷ trọng trung bình có thể che giấu đỉnh tải

Tỷ trọng theo cả ngày có thể khác đáng kể so với giờ cao điểm. Ví dụ:

- Ban ngày: tìm kiếm và xem sản phẩm chiếm phần lớn.
- Giờ ăn trưa: lượng truy vấn xem menu và đặt hàng tăng.
- Cuối ngày: checkout và thanh toán tăng.
- Đợt khuyến mại: tìm kiếm, thêm giỏ và checkout cùng tăng mạnh.
- Ban đêm: báo cáo, import và đồng bộ chạy nhiều hơn.

Nên xây dựng nhiều profile thay vì dùng một tỷ trọng duy nhất:

| Profile | Mục tiêu |
| --- | --- |
| Normal | Tải thường ngày và tỷ trọng trung bình |
| Peak business | Tỷ trọng và tốc độ trong giờ cao điểm |
| Read-heavy | Hệ thống thiên về tìm kiếm, tra cứu hoặc dashboard |
| Write-heavy | Checkout, ingest hoặc cập nhật hàng loạt |
| Mixed peak | Đọc, ghi và tác vụ nền cùng hoạt động |
| Recovery/batch | Tải sau khi hệ thống khôi phục hoặc chạy tác vụ nền |

Profile phải gắn với mục tiêu kiểm thử. Không nên trộn các profile thành một tỷ lệ trung bình nếu việc đó làm mất đỉnh tải hoặc che giấu tranh chấp.

## 3. Tỷ lệ đọc/ghi có nhiều cách định nghĩa

Một trong những lỗi phổ biến là nói workload “80% đọc, 20% ghi” mà không giải thích mẫu số. Có ít nhất bốn cách đo khác nhau:

1. **Tỷ lệ giao dịch nghiệp vụ:** bao nhiêu phần trăm giao dịch là loại chỉ đọc, chỉ ghi hoặc hỗn hợp.
2. **Tỷ lệ SQL statement:** số câu SELECT so với INSERT/UPDATE/DELETE.
3. **Tỷ lệ hàng:** số hàng được đọc so với số hàng được thêm, sửa hoặc xóa.
4. **Tỷ lệ byte/I/O:** lượng dữ liệu đọc so với lượng dữ liệu ghi xuống storage.

Các tỷ lệ này không thể thay thế cho nhau. Một SELECT có thể đọc hàng triệu hàng; một UPDATE có thể sửa một hàng nhưng tạo log và page write đáng kể. Một transaction checkout có thể chạy nhiều SELECT rồi chỉ một INSERT và một UPDATE.

### 3.1. Tỷ lệ theo loại giao dịch

Phân loại mỗi business transaction:

- Read-only: chỉ đọc dữ liệu.
- Write-only: chỉ ghi dữ liệu, ít gặp trong luồng nghiệp vụ vì thường cần kiểm tra trước.
- Read-write: đọc để xác minh rồi ghi.
- Analytical: đọc nhiều hàng, tổng hợp hoặc sort.
- Background: batch đọc và ghi theo lô.

Tỷ trọng read-only so với read-write giúp mô tả tính chất nghiệp vụ, nhưng chưa cho biết số câu SQL hoặc lượng I/O thực tế.

### 3.2. Tỷ lệ theo SQL statement

Với từng loại giao dịch, đếm số SELECT, INSERT, UPDATE và DELETE trung bình trong một lần thực hiện. Sau đó nhân với tốc độ của loại giao dịch.

Nếu loại giao dịch i chạy T_i lần mỗi giây và phát sinh trung bình r_i câu đọc, w_i câu ghi, ta có:

\[
R = \sum_i T_i \times r_i
\]

\[
W = \sum_i T_i \times w_i
\]

Tỷ trọng statement đọc:

\[
P_R = \frac{R}{R+W} \times 100\%
\]

Tỷ trọng statement ghi:

\[
P_W = \frac{W}{R+W} \times 100\%
\]

Đây là số statement theo phân loại của kịch bản, không phải tỷ lệ byte đọc/ghi ở storage.

### 3.3. Tỷ lệ theo hàng và byte

Một câu SELECT có thể trả 10 hàng hoặc 10 triệu hàng. Một UPDATE có thể sửa một hàng nhỏ hoặc cập nhật hàng triệu bản ghi. Vì vậy, cần ghi thêm:

- Rows returned và rows examined.
- Rows inserted, updated và deleted.
- Bytes returned qua mạng.
- Logical reads và physical reads.
- Data bytes written, log bytes generated và flush count.

Nếu mục tiêu là sizing storage hoặc đánh giá I/O, tỷ lệ statement không đủ. Phải đo lượng byte và loại I/O theo database engine.

## 4. Tính read/write mix từ danh mục giao dịch

Giả sử workload có 100 giao dịch nghiệp vụ mỗi giây:

| Giao dịch | Tỷ trọng | Tốc độ | SELECT trung bình | DML trung bình |
| --- | ---: | ---: | ---: | ---: |
| Tìm kiếm sản phẩm | 60% | 60/s | 4 | 0 |
| Xem lịch sử đơn | 25% | 25/s | 3 | 0 |
| Checkout | 10% | 10/s | 5 | 3 |
| Cập nhật hồ sơ | 5% | 5/s | 2 | 2 |

Số SELECT mỗi giây:

\[
R = 60 \times 4 + 25 \times 3 + 10 \times 5 + 5 \times 2 = 375
\]

Số DML mỗi giây:

\[
W = 60 \times 0 + 25 \times 0 + 10 \times 3 + 5 \times 2 = 40
\]

Tỷ trọng statement đọc:

\[
P_R = \frac{375}{375+40} \approx 90,36\%
\]

Tỷ trọng statement ghi:

\[
P_W = \frac{40}{375+40} \approx 9,64\%
\]

Tỷ lệ đọc/ghi theo số statement xấp xỉ 9,375:1. Trong khi đó, 15% giao dịch nghiệp vụ là checkout hoặc cập nhật hồ sơ có thao tác ghi. Hai cách nhìn cho hai câu trả lời khác nhau vì mẫu số khác nhau.

Con số trên vẫn chưa mô tả lượng hàng hoặc byte. Nếu mỗi lần tìm kiếm đọc 20.000 hàng để trả 20 kết quả, chi phí đọc có thể lớn hơn nhiều so với số SELECT gợi ý. Nếu checkout cập nhật tồn kho và tạo nhiều index entry, chi phí ghi cũng lớn hơn số DML statement.

## 5. Xác định nội dung đọc và ghi của từng giao dịch

Với mỗi giao dịch, cần lập bảng thao tác ở database:

| Thuộc tính | Câu hỏi |
| --- | --- |
| SQL statements | Có bao nhiêu SELECT, INSERT, UPDATE, DELETE? |
| Rows examined | Database phải kiểm tra bao nhiêu hàng? |
| Rows returned | Ứng dụng nhận bao nhiêu hàng? |
| Rows changed | Có bao nhiêu hàng được thêm, sửa hoặc xóa? |
| Tables/indexes | Những bảng và chỉ mục nào được truy cập? |
| Locking | Có khóa hàng, khóa trang hoặc khóa metadata không? |
| Logging | Mỗi lần commit tạo khoảng bao nhiêu log? |
| Transaction duration | Transaction mở trong bao lâu? |
| Data locality | Truy cập một partition, shard hay nhiều node? |

Ví dụ giao dịch checkout có thể gồm:

1. Đọc giỏ hàng và giá sản phẩm.
2. Đọc tồn kho.
3. Ghi order header.
4. Ghi order items.
5. Cập nhật tồn kho.
6. Ghi payment/outbox record.
7. Commit.

Các bước kiểm tra có thể là SELECT nhưng vẫn nằm trong một transaction read-write. Nếu nhiều checkout cùng cập nhật một sản phẩm nóng, phần UPDATE tồn kho có thể tạo lock contention dù tỷ trọng statement ghi nhỏ.

## 6. Chọn mô hình tải: open workload và closed workload

Kịch bản phải mô tả cách request đến database hoặc ứng dụng.

### 6.1. Closed workload (mô hình người dùng đồng thời)

Mỗi virtual user thực hiện một giao dịch, chờ kết quả, nghỉ theo think time rồi mới bắt đầu giao dịch tiếp theo. Số người dùng được giữ cố định.

~~~text
Virtual user:
  Gửi request
      |
  Chờ response
      |
  Think time
      |
  Gửi request tiếp theo
~~~

Mô hình này phù hợp khi số người dùng đang hoạt động là yếu tố kiểm soát tải. Khi hệ thống chậm, mỗi user hoàn tất ít giao dịch hơn và tự giảm tốc độ gửi request. Vì thế closed workload có thể che giấu hiện tượng hàng đợi tăng khi thời gian phản hồi tăng.

### 6.2. Open workload (mô hình tốc độ đến)

Request được phát sinh theo tốc độ mục tiêu, không phụ thuộc request trước đã hoàn tất hay chưa. Ví dụ, hệ thống nhận 200 giao dịch mỗi giây bất kể latency hiện tại.

~~~text
Load scheduler
   |    |    |    |
   v    v    v    v
 Request arrivals theo lịch
   |    |    |    |
   +----+----+----+
          |
          v
      Database
~~~

Mô hình này phù hợp với hệ thống nhận sự kiện, API có arrival rate xác định hoặc workload cần kiểm tra khả năng duy trì một tốc độ đến. Khi database chậm, request đang chờ có thể tăng. Công cụ test phải giới hạn queue và phát hiện load generator không đủ khả năng tạo tải mục tiêu.

### 6.3. Chọn mô hình phù hợp

| Đặc điểm hệ thống | Mô hình nên cân nhắc |
| --- | --- |
| Người dùng tương tác, chờ kết quả rồi thao tác tiếp | Closed workload |
| Event hoặc request đến theo tốc độ gần cố định | Open workload |
| Kiểm tra số session đồng thời tối đa | Closed workload |
| Kiểm tra khả năng chịu arrival rate và queueing | Open workload |
| Mô phỏng hỗn hợp người dùng và batch | Kết hợp profile có kiểm soát |

Không có mô hình nào luôn đúng. Có thể cần cả hai để đánh giá các góc nhìn khác nhau. Khi báo cáo kết quả, phải nêu rõ mô hình và cách công cụ điều khiển tải.

## 7. Think time và thời gian xử lý ngoài database

Think time là khoảng thời gian người dùng hoặc hệ thống chờ giữa các giao dịch. Ví dụ, sau khi xem sản phẩm, người dùng mất vài giây để đọc rồi mới thêm vào giỏ.

Nếu bỏ toàn bộ think time, kịch bản có thể tạo ra một vòng lặp request liên tục không giống người dùng thật. Nếu đặt think time quá lớn, tải phát ra thấp hơn dự kiến.

Phân biệt:

- **Think time:** thời gian người dùng suy nghĩ hoặc tương tác.
- **Pacing:** khoảng chờ được thêm để điều khiển tốc độ lặp của một virtual user.
- **Response time:** thời gian từ lúc gửi request đến lúc nhận response theo định nghĩa đo.
- **Database time:** thời gian database thực hiện hoặc chờ trong quá trình phục vụ request.
- **Application processing:** thời gian ứng dụng xử lý trước/sau khi gọi database.

Ví dụ một user:

- Response time trung bình: 300 ms.
- Think time: 2.700 ms.
- Chu kỳ một giao dịch: khoảng 3 giây.

Một user có thể tạo khoảng 1/3 giao dịch mỗi giây trong điều kiện ổn định. 100 user có thể tạo xấp xỉ 33 giao dịch/giây, nhưng con số thực phụ thuộc thời gian phản hồi, pacing và luồng nghiệp vụ.

## 8. Liên hệ giữa tốc độ tải và số người dùng đồng thời

Định luật Little mô tả quan hệ trong hệ thống ổn định:

\[
L = \lambda \times W
\]

Trong đó:

- L: số request hoặc transaction trung bình đang ở trong hệ thống.
- λ: tốc độ đến trung bình, ví dụ request/giây.
- W: thời gian lưu lại trung bình trong hệ thống, tính bằng giây.

Nếu hệ thống nhận 120 transaction/giây và thời gian phản hồi trung bình là 0,25 giây:

\[
L = 120 \times 0,25 = 30
\]

Trung bình có khoảng 30 transaction đang được xử lý hoặc chờ trong hệ thống. Đây không nhất thiết là 30 database connection; request có thể chờ ở web tier, connection pool, queue hoặc database.

Với mô hình closed workload có N user, response time R và think time Z, throughput gần đúng:

\[
X \approx \frac{N}{R+Z}
\]

Ví dụ 100 user, response time 0,5 giây và think time 2 giây:

\[
X \approx \frac{100}{0,5+2} = 40
\]

giao dịch mỗi giây. Khi response time tăng, throughput của mô hình closed có thể giảm dù số user không đổi.

Các công thức dùng thời gian trung bình và giả định hệ thống ổn định. Khi hàng đợi tăng không giới hạn, timeout xảy ra hoặc tải thay đổi nhanh, không nên dùng chúng như dự báo chính xác.

## 9. Mô hình hóa dữ liệu được truy cập

Tỷ lệ đọc/ghi đúng vẫn chưa đủ nếu dữ liệu thử không phản ánh phân bố thật. Kịch bản cần mô phỏng:

- Số lượng khách hàng, sản phẩm, đơn hàng và tài khoản.
- Phân bố số đơn trên mỗi khách hàng.
- Tỷ lệ khách hàng hoạt động và không hoạt động.
- Số sản phẩm nóng và mức độ phổ biến.
- Phân bố trạng thái đơn hàng.
- Thời gian dữ liệu và tỷ lệ truy vấn dữ liệu gần đây.
- Số tenant và chênh lệch kích thước tenant.
- Giá trị NULL, dữ liệu hiếm và dữ liệu lệch.

Nếu mọi virtual user truy cập cùng một customer_id hoặc product_id, test có thể tạo hot key không tồn tại trong workload thật. Ngược lại, nếu mọi user dùng khóa hoàn toàn ngẫu nhiên, test có thể bỏ qua hotspot do một nhóm người dùng hoặc sản phẩm phổ biến.

### 9.1. Phân bố đồng đều và phân bố lệch

Phân bố đồng đều dễ tạo nhưng thường không đại diện cho dữ liệu thực. Nhiều hệ thống có phân bố long-tail: một số khách hàng hoặc sản phẩm chiếm phần lớn lượt truy cập, phần còn lại có tần suất thấp.

Hãy tạo dữ liệu có:

- Nhóm phổ biến (hot keys).
- Nhóm trung bình.
- Nhóm hiếm.
- Một số tenant hoặc khách hàng rất lớn.
- Dữ liệu mới và dữ liệu cũ.

Tỷ lệ giữa các nhóm nên lấy từ telemetry hoặc thống kê dữ liệu đã được ẩn danh. Nếu không có dữ liệu thực, ghi rõ giả định và chạy thêm các profile skew khác nhau.

### 9.2. Working set và cache

Working set là tập dữ liệu được truy cập lặp lại trong một khoảng thời gian. Nếu toàn bộ test chỉ truy cập vài trăm hàng, cache có thể giữ tất cả và làm workload trở nên memory-resident. Kết quả đó khác với production có working set lớn hơn RAM.

Kịch bản nên chỉ rõ:

- Kích thước dataset so với buffer cache.
- Tỷ lệ truy vấn vào dữ liệu nóng và dữ liệu lạnh.
- Thứ tự chạy và mức tái sử dụng khóa.
- Test warm cache hay cold cache.
- Cache có được giữ ổn định giữa các lần chạy hay không.

Không xóa cache tùy tiện giữa các lần test. Cold-cache test và warm-cache test trả lời hai câu hỏi khác nhau; phải ghi rõ điều kiện.

## 10. Tạo dữ liệu và trạng thái nghiệp vụ hợp lệ

Giao dịch ghi cần dữ liệu và trạng thái phù hợp. Ví dụ checkout không thể luôn thành công nếu tồn kho đã hết; thanh toán không thể lặp lại trên một đơn đã hoàn tất nếu hệ thống chống giao dịch trùng.

Kịch bản cần xác định:

- Dữ liệu seed ban đầu.
- Tỷ lệ bản ghi mới so với bản ghi cũ.
- Cách tạo khóa duy nhất cho mỗi virtual user.
- Quy tắc chuyển trạng thái.
- Tỷ lệ giao dịch thành công, bị từ chối và retry.
- Cách reset hoặc dọn dữ liệu sau test.
- Cách tránh hai virtual user ghi đè cùng một bản ghi ngoài chủ đích.

Không dùng một tập khóa nhỏ cho hàng nghìn user nếu điều đó tạo contention nhân tạo. Nhưng cũng không dùng khóa duy nhất hoàn toàn nếu production thực sự có hot key. Mục tiêu là tái hiện phân bố truy cập có ý nghĩa.

### 10.1. Idempotency và retry

Trong hệ thống thực, client có thể retry khi timeout. Nếu request ghi không idempotent, retry có thể tạo đơn hoặc thanh toán trùng. Kịch bản cần dùng idempotency key hoặc cơ chế tương đương giống ứng dụng thật.

Phải đo riêng:

- Request ban đầu.
- Retry do timeout hoặc lỗi tạm thời.
- Giao dịch thành công sau retry.
- Giao dịch bị từ chối hoặc rollback.

Không tự động tính retry như một giao dịch nghiệp vụ mới nếu mục tiêu là đo tỷ trọng nghiệp vụ. Tuy nhiên, retry vẫn tạo request và SQL load, nên cần ghi nhận trong tổng tải database.

## 11. Thiết kế tỷ lệ đọc/ghi cho nhiều loại workload

Không có một read/write ratio chuẩn cho mọi ứng dụng. Hãy tạo profile theo mục tiêu:

### Read-heavy

Ví dụ hệ thống tra cứu sản phẩm hoặc dashboard:

- Nhiều SELECT có filter, sort và pagination.
- Một phần truy vấn đọc tổng hợp.
- Ghi nhỏ từ cập nhật hồ sơ hoặc trạng thái.
- Working set và cache hit có ảnh hưởng lớn.

### Write-heavy

Ví dụ ingest event hoặc hệ thống giao dịch:

- Nhiều INSERT/UPDATE.
- Transaction log/WAL/redo và commit latency quan trọng.
- Index maintenance và page contention có thể tăng.
- Batch size và concurrency ảnh hưởng throughput.

### Mixed OLTP

Ví dụ bán hàng:

- Tìm kiếm và xem dữ liệu.
- Checkout đọc kiểm tra rồi ghi nhiều bảng.
- Cập nhật trạng thái và hủy đơn.
- Báo cáo chạy đồng thời nhưng có thể cần giới hạn riêng.

### Mixed OLTP + analytics

Một hệ thống có cả giao dịch và báo cáo cần mô phỏng:

- Tải OLTP nền.
- Báo cáo chạy theo lịch hoặc đột xuất.
- Batch import/cleanup.
- Tác động cạnh tranh CPU, I/O, memory, temp và connection.

Không chỉ chạy workload đọc riêng rồi workload ghi riêng nếu production chạy đồng thời cả hai. Bài test riêng hữu ích để phân lập nguyên nhân; bài mixed workload cần thiết để đánh giá tác động tổng hợp.

## 12. Xây dựng profile tải và các giai đoạn kiểm thử

Một profile có thể mô tả:

| Thành phần | Giá trị cần định nghĩa |
| --- | --- |
| Transaction mix | Tỷ trọng từng giao dịch nghiệp vụ |
| Read/write mix | Số SQL đọc/ghi, hàng và byte dự kiến |
| Arrival rate | Số giao dịch hoặc request đến mỗi giây |
| Concurrency | Số user, request hoặc transaction đồng thời |
| Think time/pacing | Khoảng nghỉ giữa các giao dịch |
| Dataset | Kích thước, phân bố và working set |
| Duration | Thời gian ramp, steady-state và soak |
| Success criteria | SLA, throughput, error rate và giới hạn tài nguyên |

Các giai đoạn thường dùng:

1. **Smoke test:** tải nhỏ để xác nhận script, dữ liệu và luồng nghiệp vụ đúng.
2. **Baseline:** đo ở mức tải bình thường, dùng làm mốc so sánh.
3. **Ramp-up:** tăng tải theo từng bước để quan sát xu hướng.
4. **Steady-state:** giữ tải mục tiêu đủ lâu để đo ổn định.
5. **Peak/spike:** mô phỏng đỉnh hoặc tăng tải đột ngột.
6. **Soak:** giữ tải trong thời gian dài để phát hiện tích tụ connection, memory, lock hoặc log.
7. **Ramp-down/recovery:** giảm tải và quan sát hệ thống phục hồi.

Không phải mọi test đều cần tất cả giai đoạn. Chọn theo câu hỏi cần trả lời và khả năng môi trường. Một test quá ngắn có thể chỉ đo cache nóng hoặc burst; một test quá dài có thể làm dữ liệu thay đổi khiến các lần so sánh không còn tương đương.

## 13. Ví dụ hoàn chỉnh: workload cửa hàng trực tuyến

Giả sử mục tiêu là đánh giá database ở giờ cao điểm. Đơn vị tải được chọn là business transaction hoàn tất ở tầng API.

### 13.1. Transaction mix

| Giao dịch | Tỷ trọng | Đặc điểm |
| --- | ---: | --- |
| Search | 35% | Đọc nhiều, filter và sort |
| Product detail | 25% | Đọc một sản phẩm và tồn kho hiển thị |
| Cart update | 10% | Đọc giỏ, ghi dòng giỏ |
| Checkout | 12% | Nhiều SELECT và DML trong transaction |
| Order history | 12% | Đọc theo customer, phân trang |
| Cancel order | 3% | Đọc trạng thái và cập nhật đơn/tồn kho |
| Profile update | 3% | Đọc và cập nhật hồ sơ |
| **Tổng** | **100%** | |

### 13.2. Tốc độ tải mục tiêu

Mục tiêu là 250 business transaction/giây. Tốc độ mỗi loại:

| Giao dịch | Tốc độ mục tiêu |
| --- | ---: |
| Search | 87,5/s |
| Product detail | 62,5/s |
| Cart update | 25/s |
| Checkout | 30/s |
| Order history | 30/s |
| Cancel order | 7,5/s |
| Profile update | 7,5/s |

Các tốc độ phân số là giá trị trung bình theo thời gian. Load generator cần phân phối request sao cho tỷ trọng dài hạn gần mục tiêu; không nhất thiết phải gửi nửa giao dịch trong một giây riêng lẻ.

### 13.3. Read/write mix

Đội kiểm thử đo trên mỗi lần thực hiện:

| Giao dịch | SELECT | DML |
| --- | ---: | ---: |
| Search | 2 | 0 |
| Product detail | 2 | 0 |
| Cart update | 2 | 1 |
| Checkout | 5 | 3 |
| Order history | 2 | 0 |
| Cancel order | 2 | 2 |
| Profile update | 1 | 1 |

Số SELECT mỗi giây:

\[
87,5 \times 2 + 62,5 \times 2 + 25 \times 2 + 30 \times 5 + 30 \times 2 + 7,5 \times 2 + 7,5 \times 1
= 582,5
\]

Số DML mỗi giây:

\[
25 \times 1 + 30 \times 3 + 7,5 \times 2 + 7,5 \times 1 = 137,5
\]

Tỷ trọng statement đọc:

\[
\frac{582,5}{582,5+137,5} \approx 80,90\%
\]

Tỷ trọng statement ghi:

\[
\frac{137,5}{582,5+137,5} \approx 19,10\%
\]

Đây là statement mix dự kiến. Để đánh giá storage, cần đo thêm rows examined, rows changed, logical/physical reads, log bytes và temp I/O.

### 13.4. Dữ liệu và hành vi user

- 2 triệu khách hàng, trong đó một nhóm nhỏ hoạt động thường xuyên.
- 500.000 sản phẩm, có nhóm sản phẩm phổ biến chiếm phần lớn lượt xem.
- 50 triệu đơn hàng lịch sử.
- Một số khách hàng doanh nghiệp có lượng đơn lớn hơn nhiều mức trung bình.
- Search dùng từ khóa theo phân bố phổ biến/hiếm, không dùng một từ khóa cố định.
- Checkout dùng cart và inventory hợp lệ, tránh tái sử dụng order ID.
- Có think time cho luồng xem sản phẩm, nhưng API arrival rate được điều khiển riêng ở profile open workload.

### 13.5. Lịch chạy

- Smoke: 2 phút ở tải nhỏ.
- Baseline: 10 phút ở 50 transaction/giây.
- Ramp-up: tăng theo 50, 100, 150, 200, 250 transaction/giây.
- Steady-state: giữ 250 transaction/giây trong 30 phút.
- Peak: tăng lên 350 transaction/giây trong 5 phút nếu mục tiêu có kiểm tra burst.
- Soak: giữ mức tải dự kiến dài hạn trong 2 giờ.

Các thời lượng trên chỉ là ví dụ; thời gian thực cần phù hợp môi trường và mục tiêu kiểm thử.

### 13.6. Chỉ số xác nhận

- Tỷ trọng giao dịch thực tế gần tỷ trọng mục tiêu.
- Request/transaction rate đạt mức phát ra và hoàn tất.
- p50/p95/p99 theo từng giao dịch.
- Tỷ lệ lỗi, timeout, retry và rollback.
- SQL statement rate và read/write mix thực tế.
- Rows examined, rows changed và logical/physical reads.
- Lock wait, deadlock và transaction duration.
- CPU, memory, I/O, log flush, temp spill và connection pool wait.

Nếu tổng throughput đạt 250 nhưng checkout có p99 vượt SLA hoặc tỷ lệ rollback tăng, không thể kết luận workload đạt yêu cầu chỉ dựa trên con số throughput tổng.

## 14. Tách tải ứng dụng khỏi tải trực tiếp database

Có hai cách tổ chức test thường gặp:

### End-to-end load test

Gửi request qua API hoặc ứng dụng như người dùng thật. Cách này bao gồm network, application server, connection pool, cache ứng dụng và database. Nó trả lời hệ thống hoàn chỉnh chịu tải ra sao.

### Database-focused workload test

Phát SQL hoặc transaction trực tiếp tới database bằng driver hoặc công cụ chuyên dụng. Cách này giúp kiểm tra database trong điều kiện có thể kiểm soát, nhưng bỏ qua một phần chi phí ứng dụng và cách ứng dụng quản lý connection.

Hai cách bổ sung cho nhau:

- End-to-end phát hiện nút thắt ở toàn chuỗi.
- Database-focused giúp phân lập chi phí SQL, lock, I/O và transaction.

Nếu chạy trực tiếp SQL, phải giữ cùng tham số, tỷ trọng, transaction boundary và dữ liệu như ứng dụng. Nếu không, kết quả không đại diện cho workload thật.

## 15. Tính đúng đắn của giao dịch trong khi tạo tải

Load test phải tạo tải có ý nghĩa nghiệp vụ. Một kịch bản tạo hàng nghìn request nhưng hầu hết bị lỗi do dữ liệu không hợp lệ sẽ không kiểm tra được hành vi database mong muốn.

Với mỗi transaction:

- Kiểm tra điều kiện trước khi ghi.
- Dùng khóa duy nhất hoặc idempotency key phù hợp.
- Xác nhận commit/rollback và kết quả trả về.
- Ghi nhận lỗi nghiệp vụ riêng với lỗi hạ tầng.
- Đảm bảo dữ liệu được tạo không phá hỏng các lần chạy tiếp theo.
- Có chiến lược cleanup sau test.

Nếu test tạo dữ liệu mới liên tục, kích thước database tăng trong suốt bài test. Cần theo dõi kích thước bảng, index, partition, log và tỷ lệ cache. Có thể reset dataset giữa các lần chạy hoặc dùng một tập dữ liệu tăng trưởng được kiểm soát.

### Đọc và ghi phải có phụ thuộc thực tế

Không nên tạo các UPDATE độc lập hoàn toàn nếu production thường đọc trạng thái trước khi cập nhật. Cũng không nên cho tất cả user cập nhật cùng một hàng nếu production dùng nhiều khóa khác nhau. Mô phỏng phụ thuộc thực giúp phát hiện lock contention, deadlock và hot key đúng mức.

## 16. Các sai lầm thường gặp khi thiết kế kịch bản

### Chỉ chạy một câu SELECT

Một truy vấn đơn lẻ hữu ích để đo plan nhưng không đại diện cho transaction mix, concurrency và read/write interaction của ứng dụng.

### Dùng tỷ lệ đọc/ghi không có mẫu số

80/20 theo business transaction khác 80/20 theo SQL statement, rows hoặc bytes. Luôn nêu cách tính.

### Dùng cùng một dữ liệu cho mọi user

Điều này có thể tạo hotspot nhân tạo, cache hit bất thường và lock contention không đại diện. Dùng phân bố khóa phù hợp workload.

### Dùng dữ liệu quá nhỏ

Toàn bộ working set có thể nằm trong cache; index và execution plan có thể khác khi dữ liệu tăng. Dataset phải đủ gần quy mô mục tiêu hoặc có profile scale rõ ràng.

### Bỏ qua giao dịch hỗn hợp

Chạy read-only và write-only riêng không cho biết ảnh hưởng lẫn nhau khi production chạy đồng thời.

### Bỏ qua think time hoặc pacing

Load generator có thể tạo tải cao hơn hoặc thấp hơn nhiều so với mục tiêu.

### Không phân biệt open và closed workload

Closed workload có thể tự giảm arrival rate khi server chậm; open workload giữ tốc độ đến và làm lộ queueing. Chọn sai mô hình có thể che giấu saturation.

### Chỉ báo cáo throughput tổng

Một loại giao dịch chậm có thể bị che bởi nhiều giao dịch đọc nhanh. Phải đo theo từng transaction class và percentile.

### Để load generator trở thành nút thắt

CPU, network hoặc số worker của máy phát tải không đủ có thể làm request rate thực tế thấp hơn cấu hình. Theo dõi cả load generator và database.

## 17. Quy trình thiết kế kịch bản từ đầu đến cuối

1. **Xác định mục tiêu:** kiểm tra SLA, capacity, regression, scaling hay khả năng chịu đỉnh.
2. **Lập danh mục giao dịch:** chọn các luồng nghiệp vụ quan trọng và xác định đơn vị đếm.
3. **Mô tả từng luồng:** bước ứng dụng, SQL, transaction boundary, dữ liệu đọc/ghi và kết quả đúng.
4. **Đo tỷ trọng:** lấy tần suất từ telemetry/log hoặc ghi rõ giả định.
5. **Tính transaction mix:** chuyển tỷ trọng thành tốc độ mỗi loại theo tải mục tiêu.
6. **Tính read/write mix:** đếm SQL, rows và bytes riêng; không dùng một tỷ lệ cho mọi mục tiêu.
7. **Chọn mô hình tải:** open/closed, think time, pacing và concurrency.
8. **Thiết kế dữ liệu:** kích thước, working set, hot keys, long-tail, tenant và trạng thái nghiệp vụ.
9. **Thiết kế profile:** normal, peak, read-heavy, write-heavy, mixed và batch nếu cần.
10. **Xác định lịch chạy:** smoke, baseline, ramp-up, steady-state, spike, soak và recovery.
11. **Đặt tiêu chí đúng/sai:** SLA theo giao dịch, lỗi, retry, rollback và kiểm tra dữ liệu sau test.
12. **Chạy thử nhỏ:** xác nhận script, tỷ trọng, dữ liệu và công cụ tạo tải.
13. **Đo tải mục tiêu:** ghi nhận ứng dụng, database, hệ điều hành và load generator.
14. **Đối chiếu thực tế:** kiểm tra tỷ trọng, read/write mix, concurrency và thời gian giữ transaction có đạt mô hình không.
15. **Lưu kịch bản:** phiên bản SQL, dữ liệu, driver, cấu hình, profile và seed để có thể lặp lại.

## 18. Nguyên tắc cần ghi nhớ

- Kịch bản kiểm thử phải bắt đầu từ giao dịch nghiệp vụ và luồng dữ liệu thật.
- Phân biệt business transaction, API request, database transaction và SQL statement.
- Tỷ trọng giao dịch cần có cùng mẫu số và cộng thành 100%.
- Tỷ lệ đọc/ghi theo giao dịch, statement, hàng và byte là các đại lượng khác nhau.
- Tính tốc độ mỗi loại giao dịch từ transaction rate mục tiêu và tỷ trọng đã xác định.
- Ghi số SELECT/DML, rows examined, rows changed, bytes, logical/physical reads và log volume khi cần sizing.
- Chọn open hay closed workload theo cách request đến thực tế; mô tả think time và pacing.
- Dùng phân bố dữ liệu, hot key và working set gần với production để tránh kết quả sai lệch.
- Kiểm thử mixed workload để phát hiện tương tác giữa đọc, ghi, batch và báo cáo.
- Đánh giá từng transaction class bằng throughput, p95/p99, lỗi và tính đúng đắn, không chỉ nhìn throughput tổng.
- Lưu profile và dữ liệu để các lần kiểm thử có thể lặp lại và so sánh công bằng.

Một kịch bản tốt biến hành vi nghiệp vụ thành tải có thể đo và lặp lại. Khi mô tả rõ transaction mix, tỷ lệ đọc ghi, tốc độ đến, think time, dữ liệu và ranh giới transaction, nhóm kiểm thử có thể tái hiện tải gần thực tế hơn. Kết hợp kết quả theo từng loại giao dịch với execution plan, I/O, bộ nhớ và lock metrics giúp xác định đúng nút thắt và kiểm chứng tác động của các điều chỉnh hiệu năng.
