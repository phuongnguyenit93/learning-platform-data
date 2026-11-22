# Chi phí lưu dấu đọc, phát hiện xung đột và thực thi lại

Trong kiểm soát đồng thời lạc quan (Optimistic Concurrency Control — OCC), giao dịch được phép thực hiện phần lớn công việc mà không khóa trước mọi dữ liệu nó sẽ đọc. Hệ thống ghi nhận dữ liệu mà giao dịch đã đọc, dữ liệu mà nó dự định thay đổi, rồi kiểm tra các tập này trước khi công bố kết quả. Nếu một giao dịch khác đã thay đổi dữ liệu theo cách làm mất tính hợp lệ của giao dịch hiện tại, hệ thống hủy giao dịch và có thể yêu cầu chạy lại.

Cách tiếp cận này giảm chi phí chờ khóa khi xung đột hiếm, nhưng tạo ra những chi phí riêng. Hệ thống phải lưu dấu đọc và ghi, duy trì thông tin phiên bản hoặc snapshot, so sánh các tập dữ liệu khi kiểm định, phối hợp nhiều giao dịch cùng kiểm định và xử lý công việc bị lãng phí khi giao dịch phải chạy lại.

Một hệ thống OCC hoạt động tốt khi chi phí ghi nhận và kiểm định thấp hơn chi phí khóa/chờ mà nó tránh được, đồng thời tỷ lệ hủy giao dịch đủ thấp. Khi nhiều giao dịch liên tục đọc và ghi cùng dữ liệu, chi phí kiểm định và retry có thể tăng đến mức làm giảm thông lượng và kéo dài độ trễ.

## 1. Các tập dữ liệu OCC cần theo dõi

Một giao dịch OCC thường có ba giai đoạn khái niệm:

1. **Read phase:** giao dịch đọc dữ liệu và thực hiện tính toán. Hệ thống ghi nhận những gì giao dịch đã đọc.
2. **Validation phase:** trước khi công bố kết quả, hệ thống kiểm tra giao dịch có thể được sắp xếp vào một lịch thực thi tuần tự hợp lệ hay không.
3. **Write phase:** nếu kiểm định thành công, các thay đổi được công bố nguyên tử; nếu thất bại, giao dịch bị hủy.

Trong thời gian thực hiện, hệ thống thường cần ít nhất hai tập thông tin:

- **Read set (RS):** dữ liệu hoặc điều kiện mà kết quả giao dịch phụ thuộc vào.
- **Write set (WS):** dữ liệu mà giao dịch đã thay đổi hoặc dự định thay đổi.

Ví dụ, một giao dịch chuyển tiền đọc số dư của hai tài khoản rồi cập nhật cả hai:

~~~sql
BEGIN;

SELECT balance FROM account WHERE id = 10;
SELECT balance FROM account WHERE id = 20;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

UPDATE account
SET balance = balance + 100
WHERE id = 20;

COMMIT;
~~~

Ở mức khái niệm, tập đọc chứa hai hàng account có id 10 và 20; tập ghi cũng chứa hai hàng đó. Hệ quản trị có thể ghi nhận khóa hàng, phiên bản, timestamp, trang hoặc một biểu diễn nội bộ khác. Tập đọc và tập ghi không nhất thiết là danh sách SQL nguyên văn.

Một giao dịch có thể đọc hàng trăm nghìn hàng nhưng chỉ ghi một hàng. Ngược lại, một giao dịch có thể đọc rất ít nhưng ghi một số lượng lớn hàng. Hai hình dạng này có chi phí lưu dấu và kiểm định rất khác nhau.

### 1.1. Read set ghi nhận điều gì?

Read set phải phản ánh dữ liệu mà kết quả giao dịch phụ thuộc vào. Tùy mô hình OCC, một mục đọc có thể lưu:

- Định danh hàng, khóa hoặc đối tượng dữ liệu.
- Phiên bản đã đọc, chẳng hạn version number, transaction ID hoặc timestamp.
- Phạm vi khóa hoặc điều kiện truy vấn nếu giao dịch phụ thuộc vào một tập hàng.
- Thông tin snapshot hoặc mốc thời gian cần thiết để kiểm định.
- Trạng thái đọc đã được xác thực hay vẫn cần kiểm tra.

Ví dụ, ứng dụng đọc một hàng sản phẩm để tính giá:

~~~sql
SELECT price, discount
FROM product
WHERE id = 501;
~~~

Nếu giao dịch chỉ ghi nhớ rằng nó đã đọc product 501 mà không ghi nhận phiên bản hoặc thông tin đủ để kiểm định, hệ thống khó xác định một giao dịch khác đã thay đổi price hay discount sau thời điểm đọc hay chưa.

Trong một triển khai OCC đơn giản, mỗi lần đọc có thể ghi lại cặp (item_id, version). Ở bước kiểm định, hệ thống xác nhận phiên bản hiện tại vẫn phù hợp với phiên bản giao dịch đã đọc. Các triển khai phức tạp hơn có thể dùng timestamp, commit sequence, dependency tracking hoặc predicate tracking.

### 1.2. Write set ghi nhận điều gì?

Write set mô tả các thay đổi giao dịch muốn công bố. Nó có thể bao gồm:

- Định danh hàng hoặc khóa bị thay đổi.
- Giá trị mới hoặc tham chiếu đến vùng đệm chứa giá trị mới.
- Phiên bản cũ mà giao dịch dựa vào.
- Loại thay đổi: INSERT, UPDATE hoặc DELETE.
- Các chỉ mục và ràng buộc cần được cập nhật.

Ví dụ:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE sku = 'BOOK-01';
~~~

Write set có thể chứa hàng inventory của BOOK-01 và các mục chỉ mục bị ảnh hưởng. Một thay đổi trên hàng cũng có thể làm phát sinh công việc ở bảng liên quan, chỉ mục duy nhất, khóa ngoại hoặc trigger.

Không phải mọi hệ quản trị đều lưu toàn bộ giá trị mới trực tiếp trong một cấu trúc gọi là write set. Một số hệ thống dùng private workspace, version chain hoặc log record. Điều quan trọng là hệ thống phải biết giao dịch định công bố những thay đổi nào để kiểm định và áp dụng chúng đúng cách.

### 1.3. Đọc lại cùng một hàng

Một giao dịch có thể đọc cùng một hàng nhiều lần. Hệ thống có thể loại bỏ mục trùng trong read set và chỉ giữ một phiên bản hoặc một dấu vết đủ đại diện.

Tuy nhiên, việc loại bỏ trùng phải giữ đúng ngữ nghĩa. Nếu giao dịch đọc hai phiên bản khác nhau do mức cô lập cho phép, hoặc một lần đọc là locking/current read trong khi lần khác là snapshot read, không thể tùy tiện gộp chúng thành một mục duy nhất.

Chi phí ghi dấu không chỉ phụ thuộc số câu SELECT. Nó phụ thuộc số mục dữ liệu và số điều kiện thực sự được theo dõi.

## 2. Chi phí lưu dấu đọc và ghi

### 2.1. Chi phí bộ nhớ

Giả sử mỗi mục read set cần lưu định danh và phiên bản. Một giao dịch đọc 100.000 hàng có thể phải lưu 100.000 mục metadata, dù chỉ cập nhật một hàng.

Bộ nhớ dùng cho một giao dịch có thể được mô hình hóa gần đúng:

\[
M_T \approx |RS_T| \times m_r + |WS_T| \times m_w + M_{base}
\]

Trong đó:

- \(|RS_T|\) là số mục trong read set.
- \(|WS_T|\) là số mục trong write set.
- \(m_r\) và \(m_w\) là chi phí metadata trung bình cho mỗi mục đọc/ghi.
- \(M_{base}\) là bộ nhớ cố định cho trạng thái giao dịch, snapshot, con trỏ và cấu trúc quản lý.

Đây chỉ là mô hình ước lượng. Chi phí thực tế phụ thuộc cấu trúc dữ liệu, cách khử trùng, độ dài khóa, allocator, index nội bộ và việc hệ thống có giữ giá trị mới trong private workspace hay không.

Nếu có N giao dịch đồng thời, tổng bộ nhớ theo dõi xấp xỉ tổng bộ nhớ của các giao dịch đang hoạt động:

\[
M_{total} \approx \sum_{T=1}^{N} M_T
\]

Một số giao dịch đọc rộng và sống lâu có thể chiếm nhiều bộ nhớ hơn hàng nghìn giao dịch ngắn. Vì vậy, thời gian tồn tại của giao dịch cũng quan trọng như số hàng nó đọc.

### 2.2. Chi phí CPU khi ghi nhận mỗi lần đọc

Mỗi lần đọc có thể yêu cầu hệ thống:

1. Xác định mục dữ liệu hoặc phạm vi được đọc.
2. Lấy phiên bản hoặc timestamp tương ứng.
3. Kiểm tra mục đó đã có trong read set chưa.
4. Thêm metadata nếu đây là lần đọc mới.
5. Duy trì cấu trúc dữ liệu để tra cứu nhanh khi kiểm định.

Nếu dùng hash set, thao tác thêm và tra cứu trung bình có thể gần O(1), nhưng vẫn có chi phí băm, cấp phát bộ nhớ, va chạm và mở rộng bảng. Nếu dùng cây có thứ tự, chi phí cập nhật thường gần O(log n), đổi lại có thể hỗ trợ truy vấn phạm vi hoặc duyệt có thứ tự.

Với truy vấn đọc hàng triệu bản ghi, chi phí ghi dấu có thể trở thành phần đáng kể của tổng thời gian truy vấn. Một câu SELECT có thể rất nhanh khi chỉ đọc dữ liệu, nhưng khi cần ghi lại toàn bộ read set để kiểm định, nó phát sinh thêm CPU và bộ nhớ.

### 2.3. Chi phí lưu dấu phạm vi và predicate

Theo dõi từng hàng là chưa đủ nếu giao dịch phụ thuộc vào một điều kiện truy vấn.

Ví dụ:

~~~sql
SELECT *
FROM reservation
WHERE room_id = 10
  AND start_time < '2026-12-01 11:00:00'
  AND end_time > '2026-12-01 10:00:00';
~~~

Giao dịch có thể nhận về 0 hàng. Nhưng kết quả rỗng cũng là một kết quả mà nghiệp vụ phụ thuộc vào. Nếu giao dịch khác thêm một cuộc hẹn phù hợp với điều kiện, truy vấn ban đầu đáng lẽ có thể trả về một hàng.

Nếu read set chỉ chứa các hàng đã trả về, trường hợp kết quả rỗng không có mục nào để kiểm định. Hệ thống cần ghi nhận predicate hoặc phạm vi có thể chứa các hàng thỏa điều kiện.

Các cách biểu diễn có thể gồm:

- Predicate hoặc điều kiện truy vấn.
- Khoảng khóa trong chỉ mục.
- Phạm vi trang hoặc dải giá trị.
- Predicate lock hoặc SIREAD metadata.
- Bloom filter hoặc cấu trúc tóm tắt có thể tạo false positive.
- Phiên bản của một hàng đại diện bảo vệ cả tập dữ liệu.

Theo dõi predicate phức tạp hơn theo dõi một hàng. Một điều kiện có thể kết hợp nhiều cột, phép nối, biểu thức, collation và hàm. Hệ thống phải quyết định phạm vi nào cần bảo vệ để tránh bỏ sót xung đột.

### 2.4. Read set lớn do truy vấn rộng

Một số mẫu truy vấn làm read set tăng nhanh:

~~~sql
SELECT *
FROM event
WHERE created_at >= '2026-01-01';
~~~

Nếu bảng có hàng triệu sự kiện, giao dịch có thể đọc một tập dữ liệu rất lớn. Nếu chỉ cần đếm số sự kiện, việc lấy toàn bộ cột và toàn bộ hàng làm tăng I/O, bộ nhớ ứng dụng và metadata theo dõi.

Có thể giảm chi phí bằng cách:

- Chỉ đọc các cột thực sự cần.
- Thu hẹp điều kiện WHERE.
- Dùng chỉ mục phù hợp với điều kiện lọc.
- Tránh giữ giao dịch mở trong lúc xử lý dữ liệu không cần tính nguyên tử.
- Chuyển truy vấn phân tích dài sang luồng hoặc cơ chế đọc phù hợp nếu nghiệp vụ không cần tham gia giao dịch ghi.
- Xem xét tổng hợp dữ liệu bằng một hàng đại diện nếu quy tắc nghiệp vụ cho phép.

Thu hẹp kết quả truy vấn không phải lúc nào cũng thu hẹp predicate cần bảo vệ. Nếu kết quả phụ thuộc vào điều kiện trên toàn bộ phạm vi, hệ thống vẫn phải theo dõi phạm vi đó hoặc một cơ chế tương đương.

### 2.5. Chi phí khi giao dịch sống lâu

Một giao dịch đọc dữ liệu từ đầu rồi giữ trạng thái nhiều phút trước khi xác nhận có thể khiến hệ thống phải duy trì metadata lâu hơn.

Giao dịch sống lâu có thể:

- Giữ read set trong bộ nhớ.
- Giữ snapshot hoặc timestamp cần thiết.
- Khiến hệ thống phải giữ lại phiên bản cũ để phục vụ giao dịch.
- Làm tăng số giao dịch khác cần được xét khi kiểm định.
- Tăng xác suất có giao dịch khác ghi vào dữ liệu đã đọc.
- Tăng khả năng giao dịch phải hủy sau khi đã tốn nhiều công sức.

Trong hệ thống MVCC, snapshot cũ còn có thể làm chậm quá trình dọn dẹp phiên bản cũ. Đây là chi phí liên quan đến quản lý phiên bản, dù không phải mọi triển khai OCC đều có cùng cơ chế lưu phiên bản.

Một giao dịch dài có thể đắt ở cả hai đầu: tốn chi phí duy trì dấu vết và có xác suất bị xung đột cao hơn.

## 3. Độ chi tiết của read set và write set

Hệ thống có thể theo dõi xung đột ở nhiều mức độ chi tiết. Lựa chọn này ảnh hưởng trực tiếp đến chi phí bộ nhớ, CPU và số giao dịch bị hủy.

### 3.1. Theo dõi ở mức hàng

Theo dõi từng hàng giúp phân biệt các giao dịch chỉ đọc hoặc ghi những hàng khác nhau.

Ví dụ, T1 đọc account 10, T2 cập nhật account 20. Nếu hai hàng độc lập và không có ràng buộc liên quan, hệ thống có thể cho cả hai giao dịch tiếp tục.

Ưu điểm:

- Phát hiện xung đột chính xác hơn ở mức hàng.
- Ít hủy nhầm giao dịch không liên quan.
- Dễ liên hệ với dữ liệu nghiệp vụ.

Nhược điểm:

- Nhiều hàng đồng nghĩa nhiều metadata.
- Cần quản lý phiên bản hoặc định danh ổn định.
- Không tự giải quyết phantom nếu chỉ ghi nhận hàng đã tồn tại.

### 3.2. Theo dõi ở mức trang hoặc phạm vi

Thay vì ghi từng hàng, hệ thống có thể theo dõi trang, block, khoảng chỉ mục hoặc phạm vi dữ liệu.

Cách này giảm số mục metadata nhưng làm phạm vi xung đột rộng hơn. Hai giao dịch chạm hai hàng khác nhau trên cùng một trang có thể bị xem là xung đột nếu hệ thống chỉ phân biệt theo trang.

Đây là trade-off giữa chi phí theo dõi và độ chính xác:

| Độ chi tiết | Chi phí metadata | Khả năng hủy nhầm |
|---|---|---|
| Mức hàng | Cao hơn khi nhiều hàng | Thấp hơn |
| Mức trang | Trung bình | Có thể cao hơn |
| Mức bảng | Thấp | Có thể rất cao |
| Predicate/phạm vi | Phụ thuộc độ phức tạp của điều kiện | Phụ thuộc cách xấp xỉ phạm vi |

Một hệ thống có thể kết hợp nhiều mức, chẳng hạn theo dõi hàng khi có thể và nâng lên phạm vi lớn hơn khi metadata vượt ngưỡng.

### 3.3. False positive và false negative

**False positive** xảy ra khi hệ thống xem hai giao dịch có xung đột dù thực tế thay đổi của chúng không làm mất tính đúng đắn của nhau. Ví dụ, hai giao dịch sửa hai hàng khác nhau nhưng cùng nằm trong một vùng theo dõi quá rộng.

False positive làm tăng số lần abort và retry. Nó thường là hệ quả của việc chọn độ chi tiết thô để giảm chi phí metadata.

**False negative** xảy ra khi hệ thống bỏ sót một phụ thuộc thực sự. Ví dụ, read set chỉ ghi các hàng trả về nhưng không ghi predicate, khiến giao dịch thêm mới có thể tạo phantom mà không bị phát hiện.

False negative nguy hiểm hơn vì có thể cho phép lịch thực thi vi phạm tính tuần tự hóa. Một triển khai đúng phải ưu tiên không bỏ sót các phụ thuộc mà mô hình cô lập yêu cầu phát hiện.

### 3.4. Theo dõi phiên bản ở tầng ứng dụng

Một số hệ thống ứng dụng tự triển khai optimistic version checking bằng trường version:

~~~sql
UPDATE product
SET price = 120.00,
    version = version + 1
WHERE id = 501
  AND version = 7;
~~~

Nếu không có hàng nào được cập nhật, phiên bản đã thay đổi từ lúc ứng dụng đọc. Đây là một cách phát hiện cập nhật đồng thời ở mức hàng.

Tuy nhiên, kiểm tra version của từng entity không tự động bảo vệ mọi điều kiện mà giao dịch đã đọc. Nếu giao dịch đọc một tập hàng để tính tổng, nhưng chỉ kiểm tra version của một hàng khi ghi, các thay đổi trên những hàng còn lại có thể không bị phát hiện.

Đặc biệt, một predicate trả về 0 hàng không có version của hàng nào để kiểm tra. Để bảo vệ quy tắc phạm vi, cần cơ chế theo dõi predicate, ràng buộc phù hợp, hàng đại diện hoặc mức cô lập đủ mạnh.

## 4. Phát hiện xung đột ở bước kiểm định

Validation là bước xác định một giao dịch có thể công bố thay đổi mà vẫn giữ được quy tắc tuần tự hóa hay không.

Một cách nhìn phổ biến là so sánh read set và write set của các giao dịch có quan hệ thời gian với nhau. Nếu một giao dịch đã đọc dữ liệu mà giao dịch khác thay đổi theo thứ tự không thể sắp xếp thành lịch tuần tự hợp lệ, một giao dịch cần bị hủy hoặc phải chờ.

### 4.1. Xung đột đọc-ghi

Giả sử T1 đọc account 10. Trong khi T1 đang tính toán, T2 cập nhật account 10 rồi COMMIT.

~~~text
T1: đọc account 10 ở phiên bản V1
T2: ghi account 10 thành V2
T2: COMMIT
T1: chuẩn bị COMMIT
~~~

Nếu T1 công bố kết quả dựa trên V1 mà không kiểm định, kết quả có thể không tương đương với thứ tự thực thi tuần tự mà hệ thống yêu cầu.

Một cách phát hiện cơ bản là kiểm tra xem write set của các giao dịch đã commit sau snapshot của T1 có giao với read set của T1 hay không:

\[
RS(T1) \cap WS(T2) \ne \varnothing
\]

Nếu giao nhau trong khoảng thời gian liên quan, T1 đã đọc một mục bị thay đổi và có thể phải abort. Đây là cách minh họa cho backward validation; điều kiện chính xác còn phụ thuộc thuật toán, timestamp và thứ tự tuần tự mà giao thức chọn.

### 4.2. Xung đột ghi-ghi

Nếu hai giao dịch cùng ghi một mục, hệ thống phải xác định thứ tự công bố và cách xử lý cập nhật đồng thời.

\[
WS(T1) \cap WS(T2) \ne \varnothing
\]

Giao nhau có thể có nghĩa hai giao dịch muốn thay đổi cùng một hàng, cùng một khóa hoặc cùng một mục chỉ mục. Một số giao thức OCC phát hiện và hủy một giao dịch; một số hệ thống dùng version check hoặc khóa ngắn ở giai đoạn ghi để tuần tự hóa việc công bố.

Không phải mọi giao nhau giữa write set đều bắt buộc abort. Ví dụ, một giao thức có thể cho các giao dịch ghi cùng đối tượng theo thứ tự rõ ràng nếu ngữ nghĩa cho phép. Nhưng nó phải có quy tắc xác định kết quả, không được ghi đè tùy ý.

### 4.3. Xung đột đọc-ghi theo hướng ngược

Một giao dịch đang kiểm định có thể ghi một mục mà giao dịch khác đang hoạt động đã đọc. Nếu giao dịch ghi được công bố trước, giao dịch đọc có thể đã dựa trên phiên bản cũ.

\[
WS(T_{new}) \cap RS(T_{active}) \ne \varnothing
\]

Đây là tình huống thường được xem xét trong forward validation. Hệ thống có thể hủy giao dịch đang đọc, hủy giao dịch đang kiểm định hoặc áp dụng quy tắc thứ tự khác tùy giao thức.

Việc chọn giao dịch nào bị hủy ảnh hưởng đến chi phí. Hủy giao dịch gần hoàn tất có thể lãng phí nhiều công việc; hủy giao dịch mới bắt đầu có thể giảm công việc bị mất nhưng có thể gây starvation cho một số giao dịch.

### 4.4. Đọc-đọc thường không tạo xung đột ghi

Hai giao dịch chỉ đọc cùng một phiên bản thường có thể cùng tồn tại. Chỉ riêng:

\[
RS(T1) \cap RS(T2) \ne \varnothing
\]

không đủ để kết luận có xung đột tuần tự hóa. Xung đột thường xuất hiện khi có quan hệ đọc-ghi hoặc ghi-ghi, hoặc khi ràng buộc nghiệp vụ tạo ra phụ thuộc khác.

Dù vậy, đọc-đọc vẫn có thể tốn tài nguyên vì cả hai giao dịch phải ghi dấu cùng một tập dữ liệu riêng của chúng.

## 5. Các cách kiểm định phổ biến

OCC là một họ giao thức. Không có một thuật toán validation duy nhất được mọi hệ quản trị sử dụng. Hai cách trình bày phổ biến là backward validation và forward validation.

### 5.1. Backward validation

Backward validation xem xét các giao dịch đã hoàn tất trong khoảng thời gian giao dịch hiện tại đang thực hiện.

Với giao dịch T đang cần kiểm định, hệ thống tìm các giao dịch U đã commit sau khi T bắt đầu và trước thời điểm T kiểm định. Sau đó, nó so sánh:

\[
RS(T) \cap WS(U)
\]

Nếu có giao nhau, U đã thay đổi dữ liệu mà T từng đọc trong khoảng liên quan. T có thể phải abort vì kết quả của nó dựa trên dữ liệu đã lỗi thời.

Ví dụ:

~~~text
Thời gian ---------------------------------------------------->

T1: START ---- READ(A) ------------------------- VALIDATE
T2:             START ---- WRITE(A) ---- COMMIT
                                      ^
                         T1 phát hiện A đã bị thay đổi
~~~

Ưu điểm của backward validation là nó so sánh với các giao dịch đã commit, tức là những thay đổi đã có kết quả rõ ràng. Tuy nhiên, hệ thống phải tìm được các write set liên quan của các giao dịch trong khoảng thời gian cần kiểm tra.

Nếu có nhiều giao dịch commit giữa lúc T bắt đầu và lúc T kiểm định, số đối tượng cần xét có thể lớn. Các chỉ mục metadata theo khóa hoặc timestamp giúp tránh so sánh toàn bộ mọi tập hợp.

Điều kiện chính xác còn phụ thuộc vào thuật toán OCC. Một số giao thức dùng start, validation và finish timestamp để xác định các giao dịch nào có thể được sắp xếp trước hoặc sau T. Không nên dùng công thức giao tập hợp đơn giản như một đặc tả đầy đủ cho mọi hệ thống.

### 5.2. Forward validation

Forward validation so sánh write set của giao dịch đang kiểm định với read set của các giao dịch khác vẫn đang hoạt động:

\[
WS(T_{validating}) \cap RS(U_{active})
\]

Nếu U đã đọc dữ liệu mà T sắp ghi, kết quả của U có thể trở nên lỗi thời sau khi T công bố thay đổi. Giao thức phải quyết định cách xử lý xung đột.

Các lựa chọn có thể gồm:

- Hủy U để T được commit.
- Hủy T để U tiếp tục.
- Tuần tự hóa việc kiểm định và công bố để xác định giao dịch nào được ưu tiên.
- Dùng thông tin phụ thuộc để xác định lịch thực thi có thể tuần tự hóa hay không.

Forward validation có thể tránh một số công việc so sánh với lịch sử commit dài, nhưng nó cần truy cập metadata của các giao dịch đang hoạt động. Nếu có nhiều giao dịch cùng hoạt động, chi phí quản lý và tìm kiếm read set vẫn đáng kể.

### 5.3. So sánh hai hướng

| Tiêu chí | Backward validation | Forward validation |
|---|---|---|
| Tập giao dịch được xét | Giao dịch đã commit trong khoảng liên quan | Giao dịch đang hoạt động |
| Phép so sánh minh họa | RS của T với WS của giao dịch trước đó | WS của T với RS của giao dịch đang chạy |
| Rủi ro cần phát hiện | T đã đọc dữ liệu bị thay đổi | T sắp ghi dữ liệu mà giao dịch khác đã đọc |
| Chi phí nổi bật | Tìm lịch sử write set liên quan | Tra cứu read set của các giao dịch hoạt động |
| Quyết định abort | Thường hủy giao dịch đang kiểm định khi phát hiện đọc lỗi thời | Có thể chọn hủy giao dịch hiện tại hoặc giao dịch đang hoạt động theo giao thức |

Hai cách này là mô hình giải thích. Một triển khai thực tế có thể kết hợp timestamp, version validation, dependency tracking và cơ chế commit coordination.

### 5.4. Kiểm định phải được phối hợp nguyên tử

Giả sử T1 và T2 cùng kiểm định gần như đồng thời. Cả hai đều đọc một trạng thái cũ và muốn ghi các mục khác nhau nhưng có phụ thuộc đọc-ghi chéo.

Nếu mỗi giao dịch kiểm định độc lập trên cùng một trạng thái chưa được cập nhật, cả hai có thể cùng kết luận hợp lệ rồi cùng commit. Kết quả có thể vi phạm tính tuần tự hóa.

Vì vậy, validation và công bố thay đổi phải được phối hợp. Hệ thống có thể dùng:

- Một thứ tự validation/commit rõ ràng.
- Timestamp hoặc commit sequence được cấp nguyên tử.
- Khóa ngắn hoặc vùng tới hạn tại điểm công bố.
- Dependency graph hoặc cấu trúc theo dõi xung đột.
- Giao thức xác nhận có khả năng xử lý nhiều validator đồng thời.

Điểm phối hợp này có thể trở thành nút cổ chai nếu mọi giao dịch phải tranh một bộ điều phối trung tâm. Tăng song song hóa validation cần bảo đảm tính đúng đắn của thứ tự commit.

## 6. Chi phí phát hiện xung đột

### 6.1. Số lượng giao dịch cần xét

Giả sử một giao dịch T có read set gồm r mục và cần xét c giao dịch đối thủ. Nếu so sánh trực tiếp từng mục của T với write set của từng giao dịch đối thủ, chi phí có thể tăng theo số lượng mục và số giao dịch cần xét.

Một phép so sánh ngây thơ có thể gần:

\[
O(r \times c)
\]

Đây không phải độ phức tạp bắt buộc của mọi thuật toán. Nếu dùng hash set, bitmap, chỉ mục theo khóa, timestamp hoặc cấu trúc tóm tắt, chi phí có thể thấp hơn nhiều. Nhưng khi số mục đọc và số giao dịch đồng thời cùng tăng, validation vẫn cần tài nguyên.

### 6.2. Chỉ mục metadata cho validation

Để tránh duyệt toàn bộ lịch sử giao dịch, hệ thống có thể tổ chức metadata theo:

- Transaction ID hoặc commit timestamp.
- Định danh hàng/khóa.
- Chỉ mục ánh xạ từ item đến các giao dịch đã ghi.
- Danh sách giao dịch đang hoạt động.
- Khoảng thời gian hoặc phạm vi predicate.
- Version chain hoặc commit sequence.

Các cấu trúc này giúp tìm giao dịch liên quan nhanh hơn, nhưng chính chúng cũng cần bộ nhớ, CPU để cập nhật và cơ chế dọn dẹp. Metadata càng chi tiết thì kiểm định càng chính xác nhưng chi phí duy trì có thể tăng.

### 6.3. Chi phí so sánh tập hợp

Read set và write set có thể được lưu dưới dạng hash set, sorted list, bitmap hoặc cấu trúc chuyên biệt.

- **Hash set:** tra cứu giao nhau nhanh trung bình, nhưng cần bộ nhớ cho bảng băm và xử lý va chạm.
- **Sorted list:** có thể so sánh hai tập đã sắp xếp bằng cách duyệt tuyến tính, nhưng cần chi phí sắp xếp hoặc duy trì thứ tự.
- **Bitmap:** hiệu quả khi không gian định danh nhỏ hoặc ánh xạ được thành chỉ số ổn định; có thể tốn bộ nhớ lớn nếu miền dữ liệu thưa.
- **Bloom filter:** tiết kiệm bộ nhớ để kiểm tra khả năng giao nhau, nhưng có false positive. Kết quả dương tính thường cần bước xác minh chính xác nếu không muốn hủy nhầm quá nhiều giao dịch.

Không có cấu trúc nào tốt nhất cho mọi workload. Số lượng mục, độ thưa của dữ liệu, khả năng truy vấn theo phạm vi và giới hạn bộ nhớ đều ảnh hưởng lựa chọn.

### 6.4. Chi phí kiểm định predicate

Predicate tracking thường đắt hơn kiểm tra một khóa cụ thể. Điều kiện có thể chứa khoảng, biểu thức, nhiều cột hoặc phép nối.

Một cách xấp xỉ là nâng predicate lên phạm vi lớn hơn. Ví dụ, truy vấn theo room_id = 10 và khoảng thời gian có thể được theo dõi bằng một phạm vi chỉ mục tương ứng. Nếu hệ thống chỉ có thể theo dõi ở mức bảng, nhiều giao dịch trên các phòng khác nhau có thể bị xem là xung đột dù nghiệp vụ không giao nhau.

Chi phí giảm metadata có thể chuyển thành chi phí abort. Đây là lý do cần đo cả bộ nhớ tracking lẫn tỷ lệ xung đột giả.

### 6.5. Tranh chấp tại điểm validation

Ngay cả khi các phép so sánh riêng lẻ nhanh, nhiều giao dịch cùng đến bước validation có thể tạo ra tranh chấp trên:

- Bộ cấp commit timestamp.
- Hàng đợi commit.
- Bảng metadata giao dịch hoạt động.
- Cấu trúc chỉ mục xung đột.
- Khóa ngắn bảo vệ việc công bố thay đổi.

Một hệ thống có thể có thời gian thực hiện read/write phase rất thấp nhưng commit latency cao vì các giao dịch phải xếp hàng để kiểm định và công bố.

## 7. Chi phí abort và thực thi lại

Nếu validation phát hiện xung đột, giao dịch có thể phải hủy. Phần công việc đã thực hiện trước đó trở thành chi phí lãng phí.

### 7.1. Những gì bị lãng phí?

Một giao dịch bị abort có thể đã tiêu tốn:

- CPU để chạy logic nghiệp vụ.
- I/O để đọc hàng và chỉ mục.
- Bộ nhớ để lưu read set, write set và workspace.
- Thời gian gọi các dịch vụ nội bộ hoặc xử lý dữ liệu trung gian.
- Chi phí serialization/deserialization.
- Chi phí tính toán kết quả mà cuối cùng không được công bố.

Nếu giao dịch bị hủy gần cuối, lượng công việc mất đi có thể gần bằng toàn bộ chi phí của một lần chạy.

### 7.2. Ước lượng số lần thử kỳ vọng

Giả sử mỗi lần chạy có xác suất abort là p, và xác suất này gần như ổn định giữa các lần thử. Xác suất một lần chạy thành công là 1-p.

Số lần thử kỳ vọng cho một giao dịch thành công là:

\[
E[A] = \frac{1}{1-p}
\]

Số lần thử thất bại kỳ vọng trước lần thành công là:

\[
E[F] = \frac{p}{1-p}
\]

Ví dụ:

| Xác suất abort mỗi lần thử | Số lần thử kỳ vọng |
|---:|---:|
| 1% | 1,01 |
| 10% | 1,11 |
| 25% | 1,33 |
| 50% | 2,00 |
| 75% | 4,00 |
| 90% | 10,00 |

Khi tỷ lệ abort tăng cao, số lần chạy lại tăng nhanh. Bảng giả định các lần thử độc lập và xác suất abort không đổi. Trong hệ thống thật, xung đột có thể tương quan theo thời điểm, hot key và tải; retry đồng loạt còn có thể làm xác suất abort tăng thêm.

### 7.3. Ước lượng công việc kỳ vọng

Gọi:

- \(C_e\): chi phí thực hiện một lần thử, bao gồm đọc, tính toán và ghi dấu.
- \(C_v\): chi phí validation cho một lần thử.
- \(C_c\): chi phí công bố khi thành công.

Nếu mỗi lần thử có cùng chi phí \(C_e + C_v\), xác suất abort là p, và chỉ lần thành công phải trả \(C_c\), chi phí kỳ vọng gần đúng:

\[
E[C] \approx \frac{C_e + C_v}{1-p} + C_c
\]

Mô hình này giúp thấy hai nguồn làm OCC đắt lên:

1. \(C_v\) tăng do read set lớn hoặc validation phải xét nhiều giao dịch.
2. p tăng do xung đột thường xuyên, khiến công việc bị lặp lại.

Trong thực tế, lần retry có thể có chi phí khác lần đầu, giao dịch có thể thất bại nhiều lần liên tiếp, và backoff tạo thêm độ trễ. Vì vậy, công thức là mô hình định hướng, không phải dự báo chính xác cho mọi hệ thống.

### 7.4. Retry có thể khuếch đại tải

Khi nhiều giao dịch cùng xung đột, chúng có thể bị abort gần như đồng thời rồi retry ngay. Những lần retry lại đọc cùng dữ liệu nóng và tiếp tục va chạm.

Chu trình này tạo ra retry storm:

~~~text
Tải tăng
  |
  v
Nhiều giao dịch đọc cùng dữ liệu
  |
  v
Validation phát hiện nhiều xung đột
  |
  v
Nhiều giao dịch abort
  |
  v
Các giao dịch retry đồng loạt
  |
  v
Tải và xung đột tiếp tục tăng
~~~

Backoff, jitter và giới hạn số lần retry giúp phá đồng bộ giữa các lần thử. Tuy nhiên, nếu nguyên nhân là một hot key có nhiều writer, chỉ thêm backoff có thể chưa đủ; cần thay đổi mô hình dữ liệu hoặc cách phân phối cập nhật.

### 7.5. Starvation

Một giao dịch dài hoặc ít được ưu tiên có thể liên tục bị abort bởi các giao dịch ngắn hoàn tất trước. Nếu không có chính sách công bằng, giao dịch đó có thể bị starvation.

Một số chiến lược có thể giúp:

- Ưu tiên giao dịch đã thử nhiều lần.
- Giới hạn số lần abort liên tiếp.
- Chuyển giao dịch có xung đột cao sang cơ chế khóa tường minh.
- Chia giao dịch lớn thành đơn vị nhỏ nếu nghiệp vụ cho phép.
- Dùng hàng đợi tuần tự cho một tài nguyên nóng.

Việc ưu tiên phải được thiết kế cùng cơ chế validation. Nếu một giao dịch vẫn có thể bị các giao dịch mới liên tục làm mất hiệu lực, ưu tiên ở tầng ứng dụng chưa chắc giải quyết được starvation.

## 8. Ví dụ: hai giao dịch đặt chỗ cùng đọc một phạm vi

Giả sử phòng 10 không được có hai cuộc hẹn chồng lấn. Hai giao dịch cùng kiểm tra khoảng 10:00–11:00:

~~~sql
-- Giao dịch T1
BEGIN;

SELECT COUNT(*)
FROM reservation
WHERE room_id = 10
  AND start_time < '2026-12-01 11:00:00'
  AND end_time > '2026-12-01 10:00:00';

-- Kết quả: 0
~~~

~~~sql
-- Giao dịch T2
BEGIN;

SELECT COUNT(*)
FROM reservation
WHERE room_id = 10
  AND start_time < '2026-12-01 11:00:00'
  AND end_time > '2026-12-01 10:00:00';

-- Kết quả: 0
~~~

Cả hai giao dịch sau đó thêm cuộc hẹn:

~~~sql
INSERT INTO reservation (room_id, start_time, end_time)
VALUES (10, '2026-12-01 10:00:00', '2026-12-01 11:00:00');
~~~

Nếu chỉ theo dõi các hàng đã trả về, read set của hai truy vấn có thể rỗng. Nhưng hai giao dịch đều phụ thuộc vào điều kiện "không có cuộc hẹn chồng lấn". Hệ thống cần theo dõi predicate hoặc dùng cơ chế khác để bảo vệ quy tắc.

Nếu predicate được ghi nhận chính xác, validation có thể phát hiện một giao dịch đã thêm hàng làm thay đổi kết quả mà giao dịch kia dựa vào. Một giao dịch bị abort, rồi retry sẽ thấy cuộc hẹn đã được xác nhận và từ chối đặt chỗ.

Nếu hệ thống dùng tracking phạm vi quá rộng, ví dụ theo dõi toàn bộ reservation thay vì phòng 10 và khoảng thời gian cụ thể, đặt chỗ ở phòng 11 cũng có thể làm giao dịch bị abort. Đó là false positive do phạm vi theo dõi thô.

Ví dụ này cho thấy chi phí read set không chỉ là số hàng đã đọc. Một truy vấn trả về 0 hàng vẫn có thể cần lưu dấu predicate để phát hiện phantom.

## 9. Đo lường chi phí OCC trong hệ thống thật

Không thể đánh giá OCC chỉ bằng tỷ lệ giao dịch commit. Cần quan sát cả chi phí theo dõi, kiểm định, abort và retry.

### 9.1. Các chỉ số nên thu thập

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Lưu dấu | Kích thước read set trung bình và p95/p99 | Giao dịch đọc rộng đến mức nào |
| Lưu dấu | Kích thước write set | Mức độ ghi và phạm vi công bố |
| Bộ nhớ | Metadata bytes trên mỗi giao dịch | Chi phí theo dõi |
| Validation | Thời gian validation trung bình và p95/p99 | Điểm nghẽn kiểm định |
| Validation | Số giao dịch hoặc mục được so sánh | Khối lượng công việc kiểm tra |
| Xung đột | Abort rate theo nguyên nhân | Mức xung đột và false positive |
| Retry | Số lần thử trung bình trên một commit thành công | Công việc lặp lại |
| Độ trễ | Commit latency p95/p99 | Thời gian ở giai đoạn kiểm định/công bố |
| Tài nguyên | CPU, bộ nhớ và I/O | Chi phí tổng thể |
| Phân bố | Hot key/hot range | Vùng dữ liệu gây xung đột |

Nên phân biệt abort do xung đột thực sự, abort do serialization failure, lỗi nghiệp vụ như UNIQUE violation và lỗi timeout. Gộp tất cả vào một con số làm mất thông tin để quyết định tối ưu.

### 9.2. Đo theo loại giao dịch

Tỷ lệ abort toàn hệ thống có thể che khuất một loại giao dịch gây vấn đề. Hãy phân nhóm theo:

- Loại nghiệp vụ.
- Bảng hoặc nhóm dữ liệu.
- Mẫu truy vấn.
- Độ dài giao dịch.
- Kích thước read/write set.
- Người gọi hoặc luồng xử lý.
- Hot key hoặc phạm vi dữ liệu.

Ví dụ, 99% giao dịch đọc có thể hoàn tất nhanh, trong khi 1% giao dịch cập nhật tồn kho liên tục abort. Trung bình toàn hệ thống có thể trông tốt nhưng nghiệp vụ tồn kho vẫn có độ trễ p99 rất cao.

### 9.3. Đo chi phí retry riêng biệt

Ghi nhận số lần thử cho mỗi giao dịch nghiệp vụ, không chỉ số lần gọi SQL. Một request có thể thực hiện nhiều câu lệnh rồi mới bị abort.

Có thể theo dõi:

- Số lần retry trên mỗi request.
- Tổng thời gian bị mất trong các lần thử thất bại.
- Tỷ lệ request vượt giới hạn retry.
- Số lần retry đồng thời trong cùng một khoảng thời gian.
- Tỷ lệ thành công ở lần đầu so với các lần sau.

Nếu số lần retry tăng theo tải, hệ thống có thể đang bước vào vùng mà OCC không còn hiệu quả với workload hiện tại.

### 9.4. Dùng benchmark có tranh chấp thực tế

Một benchmark chỉ đọc hoặc ghi các khóa ngẫu nhiên phân tán có thể đánh giá quá lạc quan. Cần mô phỏng cả:

- Nhiều giao dịch cập nhật cùng hot key.
- Giao dịch đọc phạm vi rộng rồi ghi một hàng.
- Predicate trả về 0 hàng nhưng có giao dịch khác chèn phantom.
- Giao dịch dài xen kẽ giao dịch ngắn.
- Nhiều giao dịch cùng đến validation và commit.
- Retry với backoff khi tải tăng.

Đo throughput và latency p95/p99 ở nhiều mức contention. So sánh OCC với khóa tường minh hoặc mức cô lập khác trên cùng một workload và cùng điều kiện dữ liệu.

## 10. Giảm chi phí lưu dấu và validation

### 10.1. Thu hẹp read set

Chỉ đọc dữ liệu cần thiết cho quyết định nghiệp vụ. Tránh SELECT * nếu chỉ cần một vài cột. Dùng điều kiện lọc cụ thể và chỉ mục phù hợp.

Tuy nhiên, không được bỏ qua một điều kiện chỉ để giảm read set nếu điều kiện đó cần bảo vệ bất biến dữ liệu. Mục tiêu là loại bỏ các lần đọc không cần thiết, không phải bỏ dấu vết của dữ liệu có ảnh hưởng đến kết quả.

### 10.2. Thu hẹp thời gian giao dịch

Thực hiện tính toán không cần snapshot hoặc tính nguyên tử trước khi mở giao dịch nếu có thể. Đọc dữ liệu cần thiết, thực hiện thay đổi và commit trong khoảng thời gian ngắn.

Giao dịch ngắn giảm:

- Thời gian metadata phải được giữ.
- Số giao dịch đối thủ có thể xuất hiện trong khoảng validation.
- Xác suất read set bị thay đổi.
- Công việc bị lãng phí nếu abort.

### 10.3. Chọn độ chi tiết tracking phù hợp

Theo dõi ở mức hàng có thể giảm false positive nhưng tốn metadata. Theo dõi ở mức trang hoặc bảng giảm metadata nhưng có thể tăng abort.

Cần đo workload để chọn mức phù hợp. Nếu một số truy vấn có read set rất lớn, có thể dùng cơ chế tracking phạm vi hoặc tóm tắt riêng cho các truy vấn đó, miễn là không bỏ sót phụ thuộc cần thiết.

### 10.4. Tối ưu cấu trúc metadata

Các kỹ thuật triển khai có thể gồm:

- Hash set để tra cứu định danh đọc/ghi.
- Bitmap khi định danh có miền nhỏ và dày.
- Chỉ mục theo khóa để tìm giao dịch xung đột.
- Timestamp/commit sequence để bỏ qua lịch sử không liên quan.
- Khử trùng mục đọc.
- Nén hoặc gom nhóm phạm vi liên tiếp.
- Dọn metadata ngay khi không còn giao dịch nào cần tham chiếu đến nó.

Tối ưu metadata phải giữ đúng tính nguyên tử và thứ tự commit. Một cache hoặc cấu trúc tóm tắt bị lỗi thời có thể dẫn đến bỏ sót xung đột.

### 10.5. Dùng ràng buộc cơ sở dữ liệu cho quy tắc phù hợp

Nếu một quy tắc có thể biểu diễn bằng UNIQUE, FOREIGN KEY, CHECK hoặc exclusion constraint, để cơ sở dữ liệu bảo vệ nó thường rõ ràng và an toàn hơn một chuỗi SELECT kiểm tra rồi INSERT ở tầng ứng dụng.

Ràng buộc có thể dùng cơ chế chỉ mục chuyên biệt và phát hiện xung đột ở nơi dữ liệu được ghi. Tuy vậy, ràng buộc cũng có chi phí kiểm tra và có thể tạo chờ khóa; cần thiết kế chỉ mục và xử lý lỗi tương ứng.

### 10.6. Giảm tranh chấp trên hot key

Nếu hàng tồn kho, bộ đếm hoặc tài khoản cụ thể bị cập nhật liên tục, mọi giao dịch có thể cùng tranh một điểm.

Một số hướng thiết kế:

- Gom cập nhật vào hàng đợi và xử lý tuần tự theo khóa nghiệp vụ.
- Chia bộ đếm thành nhiều bucket nếu có thể tổng hợp lại đúng.
- Dùng cập nhật nguyên tử có điều kiện để rút ngắn vùng đọc rồi ghi.
- Tách dữ liệu nóng theo phân vùng nghiệp vụ.
- Dùng khóa tường minh cho tài nguyên nóng nếu việc chờ có kiểm soát rẻ hơn abort liên tục.

Không phải lúc nào phân mảnh cũng phù hợp. Nếu nghiệp vụ cần một số dư duy nhất hoặc giới hạn tồn kho toàn cục, chia nhỏ dữ liệu cần có quy tắc tổng hợp và kiểm soát nhất quán rõ ràng.

## 11. Khi nào chi phí OCC phù hợp?

OCC thường phù hợp khi:

- Xung đột ghi tương đối hiếm.
- Giao dịch ngắn.
- Read/write set nhỏ hoặc vừa.
- Dữ liệu được truy cập phân tán.
- Chi phí chờ khóa cao hơn chi phí kiểm định.
- Ứng dụng có thể retry toàn bộ giao dịch một cách an toàn.

OCC có thể kém phù hợp khi:

- Nhiều giao dịch cùng ghi một hot key.
- Giao dịch đọc phạm vi rất lớn rồi mới ghi.
- Giao dịch kéo dài và có nhiều cơ hội bị thay đổi read set.
- Chi phí tính toán trước commit rất cao.
- Retry có tác dụng phụ khó đảo ngược.
- Validation phải so sánh với lượng lớn giao dịch đồng thời.
- Điểm commit/validation trở thành nút cổ chai.

Khi contention cao, khóa tường minh có thể tốt hơn vì giao dịch chờ sớm trước khi tiêu tốn nhiều CPU cho công việc sẽ bị hủy. Một lựa chọn khác là phân vùng hoặc tuần tự hóa các thao tác trên tài nguyên nóng.

Không nên kết luận OCC tốt hơn hoặc kém hơn khóa chỉ từ tên thuật toán. Hãy so sánh tổng chi phí: theo dõi + validation + commit + abort/retry đối với OCC, và khóa + chờ + deadlock/retry đối với điều khiển bi quan.

## 12. Ví dụ chọn giữa OCC và khóa tường minh

Một dịch vụ quản lý hồ sơ có nhiều giao dịch đọc thông tin khách hàng, nhưng chỉ thỉnh thoảng cập nhật. Các giao dịch thường đọc một vài hàng và chạy ngắn. Trong trường hợp này, chi phí read-set tracking và validation có thể thấp hơn việc khóa hàng từ đầu và khiến các lần đọc khác phải chờ.

Ngược lại, một dịch vụ bán vé có hàng nghìn request cùng tranh vé cuối cùng của một sự kiện. Nếu mọi giao dịch đều đọc trạng thái vé rồi đến validation mới phát hiện xung đột, nhiều giao dịch sẽ tốn công rồi abort. Một hàng đại diện được khóa ngắn, một thao tác cập nhật nguyên tử có điều kiện hoặc hàng đợi tuần tự theo sự kiện có thể hiệu quả hơn.

| Đặc điểm workload | OCC | Khóa tường minh/bi quan |
|---|---|---|
| Nhiều đọc, ít ghi | Thường thuận lợi | Có thể tạo chờ không cần thiết |
| Ghi phân tán, ít giao nhau | Thường thuận lợi | Chi phí khóa vẫn tồn tại |
| Nhiều giao dịch cùng ghi một hàng | Abort/retry có thể tăng mạnh | Chờ có thể dự đoán hơn |
| Giao dịch đọc rất rộng | Read set và validation đắt | Khóa phạm vi có thể cũng đắt |
| Giao dịch dài | Dễ tăng xác suất xung đột | Giữ khóa lâu gây blocking |
| Có thể retry an toàn | Thuận lợi | Vẫn cần xử lý deadlock/timeout |
| Tài nguyên nóng có thứ tự rõ ràng | Có thể tốn công retry | Khóa/queue có thể phù hợp |

## 13. Quy trình phân tích khi OCC chậm hoặc abort nhiều

Khi thấy validation chậm hoặc tỷ lệ abort tăng, có thể điều tra theo trình tự:

1. **Phân nhóm giao dịch:** xác định loại nghiệp vụ nào có read set, write set hoặc thời gian chạy lớn.
2. **Đo kích thước tập hợp:** lấy trung bình và p95/p99 của RS/WS, số predicate hoặc phạm vi được theo dõi.
3. **Đo validation:** xem thời gian kiểm định, số giao dịch đối thủ và số mục phải so sánh.
4. **Phân loại xung đột:** đọc-ghi, ghi-ghi, phantom/predicate, UNIQUE/FK hay serialization failure.
5. **Tìm hot key/range:** xác định dữ liệu bị nhiều giao dịch truy cập cùng lúc.
6. **Đo chi phí retry:** tính số lần thử trên một commit thành công và tổng CPU/I/O bị lãng phí.
7. **Thử điều chỉnh:** thu hẹp read set, rút ngắn giao dịch, thay đổi tracking granularity, bổ sung ràng buộc hoặc dùng khóa cho tài nguyên nóng.
8. **Benchmark lại:** kiểm tra throughput, p95/p99, abort rate, memory và CPU trên cùng tải.

Nếu validation chậm nhưng abort thấp, có thể điểm nghẽn nằm ở cấu trúc metadata hoặc số lượng mục phải so sánh. Nếu validation nhanh nhưng abort cao, cần tìm contention hoặc tracking quá thô. Nếu cả validation và retry đều tăng, workload có thể đã vượt vùng phù hợp của OCC.

## 14. Những nhầm lẫn thường gặp

**“Giao dịch chỉ đọc một hàng nên read set luôn nhỏ.”**

Không chắc. Một câu truy vấn có thể đọc nhiều hàng thông qua join, subquery, trigger hoặc kiểm tra ràng buộc. Phải xem dữ liệu thực sự được truy cập, không chỉ nhìn số câu SELECT.

**“Truy vấn trả về 0 hàng thì không cần lưu dấu đọc.”**

Sai khi kết quả rỗng ảnh hưởng đến quyết định nghiệp vụ. Hệ thống cần theo dõi predicate hoặc cơ chế tương đương để phát hiện hàng mới thỏa điều kiện.

**“Read set càng chính xác thì OCC luôn càng nhanh.”**

Không nhất thiết. Tracking chi tiết giảm false positive nhưng tăng bộ nhớ và CPU. Cần cân bằng chi phí metadata với chi phí abort do phạm vi theo dõi thô.

**“Chỉ cần kiểm tra version của hàng được cập nhật là đủ để bảo đảm serializability.”**

Sai với quy tắc phụ thuộc nhiều hàng hoặc predicate. Version của một hàng không đại diện cho mọi dữ liệu mà giao dịch đã đọc.

**“Validation chỉ là so sánh hai danh sách khóa.”**

Đó là mô hình đơn giản. Validation thực tế còn phải xét timestamp, snapshot, predicate, thứ tự commit, giao dịch đang hoạt động và điều kiện tuần tự hóa của giao thức.

**“Retry luôn làm hệ thống phục hồi tốt hơn.”**

Retry không giới hạn có thể khuếch đại tải và gây starvation. Cần giới hạn, backoff, jitter và thiết kế tác dụng phụ an toàn.

**“Tỷ lệ commit cao chứng minh OCC hoạt động hiệu quả.”**

Chưa đủ. Hệ thống có thể commit thành công nhưng tiêu tốn nhiều CPU, bộ nhớ và lần thử thất bại. Cần đo chi phí trên mỗi giao dịch thành công và độ trễ p95/p99.

## 15. Câu hỏi định hướng khi thiết kế OCC

Khi chọn hoặc tối ưu một cơ chế OCC, hãy trả lời:

- Giao dịch đọc bao nhiêu hàng và bao nhiêu phạm vi?
- Những dữ liệu nào thực sự ảnh hưởng đến kết quả nghiệp vụ?
- Read set có cần ghi nhận predicate để tránh phantom không?
- Hệ thống theo dõi theo hàng, trang, bảng hay phạm vi?
- Metadata được giữ trong bao lâu và được dọn khi nào?
- Validation phải xét bao nhiêu giao dịch đồng thời?
- Nhiều validator được phối hợp commit như thế nào?
- Xung đột nào thường khiến giao dịch abort?
- Tỷ lệ retry và công việc bị lãng phí là bao nhiêu?
- Có hot key hoặc hot range nào nên chuyển sang cơ chế khóa/queue?
- Các tác dụng phụ ngoài cơ sở dữ liệu có an toàn khi retry không?

Chi phí OCC không chỉ nằm ở bước kiểm định. Nó bắt đầu từ lần đọc đầu tiên khi hệ thống ghi dấu dữ liệu, tiếp tục trong suốt thời gian giao dịch tồn tại, tăng lên khi so sánh các giao dịch cạnh tranh và có thể lặp lại nhiều lần nếu giao dịch bị abort. Thiết kế tốt cần giữ read set đủ chính xác để bảo vệ quy tắc, đủ gọn để kiểm định hiệu quả và có chính sách retry phù hợp với mức tranh chấp của dữ liệu.
