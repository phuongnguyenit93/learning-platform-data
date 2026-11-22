# Đọc ngẫu nhiên, đọc tuần tự và chi phí truy xuất bổ sung về bảng

## Vì sao kiểu truy cập dữ liệu ảnh hưởng đến hiệu năng?

Một truy vấn có thể tìm đúng vài hàng bằng chỉ mục nhưng vẫn chậm vì phải quay lại bảng để lấy các cột còn thiếu. Một truy vấn khác có thể quét hàng triệu hàng nhưng hoàn tất nhanh vì dữ liệu được đọc tuần tự, nằm sẵn trong bộ nhớ hoặc được hệ quản trị đọc trước theo lô. Vì vậy, số hàng kết quả và tên toán tử trong kế hoạch thực thi chưa đủ để đánh giá chi phí truy cập dữ liệu.

Cần hiểu ba khái niệm có liên quan:

- **Đọc tuần tự (sequential read):** đọc các trang dữ liệu theo thứ tự gần nhau, thường tận dụng locality và khả năng đọc trước.
- **Đọc ngẫu nhiên (random read):** truy cập các trang phân tán, thứ tự truy cập khó dự đoán hoặc không liền kề trong vùng lưu trữ.
- **Truy xuất bổ sung về bảng (table lookup hoặc row fetch):** sau khi tìm thấy khóa trong chỉ mục, hệ quản trị phải đọc thêm trang của bảng hoặc cấu trúc lưu trữ chính để lấy hàng đầy đủ.

Đọc ngẫu nhiên thường có chi phí cao hơn đọc tuần tự trên thiết bị có độ trễ seek lớn như ổ đĩa cơ. Trên SSD và NVMe, chênh lệch có thể nhỏ hơn đáng kể, nhưng truy cập phân tán vẫn có thể gây nhiều I/O request, tăng độ trễ, giảm hiệu quả đọc trước và tạo áp lực lên hàng đợi. Nếu trang đã ở trong buffer cache, một lần truy cập ngẫu nhiên có thể chỉ là thao tác bộ nhớ; vì thế không thể đánh giá đường truy cập chỉ bằng giả định rằng mỗi lookup đều đọc đĩa.

Trong tối ưu hiệu năng cơ sở dữ liệu, mục tiêu là giảm tổng chi phí để có được dữ liệu cần thiết: số trang phải đọc, số lần truy xuất, mức độ locality, thời gian chờ I/O, CPU, bộ nhớ và chi phí duy trì chỉ mục. Bài học này kết nối các khái niệm đó với thiết kế chỉ mục, kế hoạch thực thi, thống kê tải và kiểm chứng sau điều chỉnh.

## Trang dữ liệu, buffer cache và đường đi của một lần đọc

### Cơ sở dữ liệu đọc theo trang

Hệ quản trị thường tổ chức dữ liệu thành các đơn vị trang (page hoặc block). Một trang chứa nhiều hàng hoặc mục chỉ mục. Khi truy vấn cần một hàng, hệ quản trị phải tìm trang chứa hàng đó, bảo đảm trang có trong bộ nhớ, rồi đọc dữ liệu cần thiết.

Nếu trang đã nằm trong buffer cache, hệ quản trị có thể phục vụ yêu cầu mà không cần đọc thiết bị lưu trữ ở thời điểm đó. Nếu trang chưa có, hệ quản trị yêu cầu đọc từ tầng lưu trữ; hệ điều hành hoặc bộ điều khiển thiết bị cũng có thể có cache riêng. Vì vậy, số lần truy cập trang logic và số lần đọc vật lý không nhất thiết bằng nhau.

Các thuật ngữ thường gặp:

- **Logical read / buffer hit:** truy cập một trang đã có trong vùng đệm của hệ quản trị.
- **Physical read / buffer read:** hệ quản trị phải nạp trang từ tầng lưu trữ vào vùng đệm; điều này không luôn đồng nghĩa thiết bị vật lý phải truy cập vì cache bên dưới có thể đáp ứng.
- **Read-ahead / prefetch:** hệ quản trị hoặc tầng lưu trữ đọc trước các trang có khả năng sắp được sử dụng.
- **Cache miss:** trang cần thiết chưa nằm trong cache phù hợp, dẫn đến phải lấy từ tầng lưu trữ hoặc tầng cache thấp hơn.

Khi đọc số liệu, hãy dùng đúng định nghĩa của hệ quản trị. Một chỉ số “read” trong công cụ này có thể không cùng ý nghĩa với “physical disk read” trong công cụ khác.

### Locality và khả năng đọc trước

Locality mô tả mức độ gần nhau của các truy cập dữ liệu. Có hai dạng thường được nhắc đến:

- **Locality theo không gian:** các trang cần đọc nằm gần nhau trong thứ tự lưu trữ hoặc thứ tự truy cập.
- **Locality theo thời gian:** cùng một trang hoặc vùng dữ liệu được truy cập lặp lại trong một khoảng thời gian ngắn.

Đọc tuần tự tận dụng locality theo không gian. Khi hệ quản trị phát hiện truy vấn sẽ đi qua một dải trang, nó có thể đọc trước nhiều trang và giảm số lần phải khởi tạo yêu cầu I/O riêng lẻ. Cache tận dụng locality theo thời gian khi các trang được tái sử dụng.

Truy cập chỉ mục có thể tận dụng locality theo không gian ở các trang lá liền kề, nhưng việc quay về bảng lấy từng hàng có thể làm mất tính liên tục đó. Đây là lý do một truy vấn có Index Seek vẫn có thể chậm khi số hàng phù hợp lớn và mỗi hàng cần một lần truy xuất riêng.

### Từ truy vấn đến thiết bị lưu trữ

Một đường đọc đơn giản có thể gồm:

~~~mermaid
flowchart TD
    A[Câu SQL và kế hoạch thực thi] --> B[Tìm trang hoặc khóa cần thiết]
    B --> C{Trang đã ở buffer cache?}
    C -->|Có| D[Đọc dữ liệu từ bộ nhớ]
    C -->|Không| E[Yêu cầu đọc từ tầng lưu trữ]
    E --> F[Read-ahead, cache hệ điều hành hoặc thiết bị]
    F --> G[Nạp trang vào buffer cache]
    G --> D
    D --> H[Lọc hàng và trả kết quả]
~~~

Sơ đồ là mô hình khái quát. Chi tiết phụ thuộc hệ quản trị, loại lưu trữ, cache và cơ chế I/O. Một số hệ thống có I/O bất đồng bộ, nhiều hàng đợi và đọc song song; đường đi thực tế có thể phức tạp hơn.

## Đọc tuần tự và đọc ngẫu nhiên

### Đọc tuần tự

Đọc tuần tự đi qua các trang theo thứ tự tương đối liên tục. Ví dụ, quét bảng lớn để tính tổng doanh thu theo tháng có thể đọc nhiều trang liên tiếp. Hệ quản trị có thể thực hiện read-ahead và xử lý các trang theo lô.

Đọc tuần tự thường phù hợp khi:

- Truy vấn cần một tỷ lệ lớn hàng trong bảng.
- Bảng nhỏ hoặc số trang cần đọc ít.
- Chỉ mục không giúp thu hẹp đáng kể tập hàng.
- Dữ liệu được tổ chức thuận lợi cho việc đọc theo phạm vi.
- Chi phí đọc liên tục thấp hơn nhiều lần truy xuất rời rạc.

Ví dụ:

~~~sql
SELECT status, COUNT(*)
FROM orders
GROUP BY status;
~~~

Nếu truy vấn cần kiểm tra hầu hết đơn hàng, quét tuần tự có thể là lựa chọn hợp lý. Việc tạo chỉ mục chỉ để tránh thao tác scan có thể không cải thiện hiệu năng, thậm chí tăng chi phí cập nhật dữ liệu.

### Đọc ngẫu nhiên

Đọc ngẫu nhiên xảy ra khi truy vấn cần các trang phân tán hoặc truy cập chúng theo thứ tự không liền kề. Một chỉ mục có thể xác định chính xác các hàng cần đọc, nhưng nếu những hàng này nằm ở nhiều trang khác nhau thì hệ quản trị phải lấy nhiều trang riêng lẻ.

Ví dụ:

~~~sql
SELECT order_id, customer_id, shipping_address
FROM orders
WHERE status = 'READY';
~~~

Nếu chỉ mục trên status tìm được 30.000 mục nhưng các hàng tương ứng nằm rải rác khắp bảng, việc lấy shipping_address từ bảng có thể cần nhiều lần truy xuất trang. Số hàng trả về chỉ là 30.000, nhưng số trang cần truy cập có thể lớn hơn nhiều so với dự đoán ban đầu.

### So sánh theo loại thiết bị

| Đặc điểm | HDD | SSD SATA | SSD NVMe |
|---|---|---|---|
| Độ trễ truy cập ngẫu nhiên | Thường cao do thời gian seek và quay đĩa | Thấp hơn HDD đáng kể | Thường rất thấp |
| Đọc tuần tự | Có lợi thế rõ khi đọc vùng liền kề | Thông lượng cao | Thông lượng và khả năng xử lý song song cao |
| Truy cập phân tán | Dễ gây nhiều lần seek | Vẫn tạo nhiều request và chi phí quản lý | Vẫn chịu giới hạn độ trễ, queue và IOPS |
| Đọc trước | Có thể cải thiện hiệu quả rất rõ | Vẫn hữu ích | Có thể hữu ích nhưng cần đo theo workload |
| Yếu tố cần quan sát | Seek, throughput, queue | IOPS, latency, queue, throughput | Queue depth, IOPS, latency, throughput và giới hạn thiết bị |

Bảng này mô tả xu hướng chung, không phải cam kết hiệu năng. Thiết bị, firmware, controller, RAID, filesystem, virtualization, cloud volume và mức tải đồng thời có thể làm kết quả thay đổi. Trên SSD, random read không đương nhiên rẻ bằng zero cost; nhiều request nhỏ vẫn có thể tạo overhead và cạnh tranh hàng đợi.

### Không đồng nhất scan với đọc tuần tự và seek với đọc ngẫu nhiên

Quét bảng thường có xu hướng đọc tuần tự, nhưng không phải lúc nào cũng hoàn toàn tuần tự ở tầng vật lý. Phân vùng, phân mảnh, lưu trữ phân tán và đọc song song có thể thay đổi thứ tự thực tế.

Index Seek thường định vị nhanh một vùng khóa, nhưng phần lấy hàng sau đó có thể là truy cập ngẫu nhiên. Ngược lại, Index Scan trên các trang lá liền kề có thể đọc khá tuần tự. Tên toán tử mô tả chiến lược logic của hệ quản trị; muốn hiểu I/O phải xem trang, số lần truy cập, buffer hit/read và thời gian chờ.

## Chi phí truy xuất bổ sung về bảng

### Từ chỉ mục về hàng dữ liệu

Chỉ mục thường chứa khóa tìm kiếm và thông tin định vị hàng. Nếu truy vấn cần cột không có trong chỉ mục, hệ quản trị phải lấy thêm dữ liệu từ bảng hoặc cấu trúc clustered tương ứng.

Tên thao tác khác nhau theo hệ quản trị:

- SQL Server có thể hiển thị Key Lookup hoặc RID Lookup.
- PostgreSQL có thể thực hiện Index Scan rồi heap fetch; Index Only Scan có thể tránh heap access khi visibility map cho phép.
- InnoDB dùng secondary index chứa khóa chính để tra cứu clustered index khi cần cột không có trong secondary index.

Dù tên khác nhau, bản chất là đường truy cập gồm hai phần: tìm mục chỉ mục và lấy dữ liệu hàng. Chi phí phần thứ hai có thể lớn hơn phần đầu nếu số hàng phù hợp cao.

### Ví dụ về lookup lặp lại

Giả sử bảng orders có 8 triệu hàng và chỉ mục trên status. Truy vấn lấy các đơn READY cùng địa chỉ giao hàng:

~~~sql
SELECT order_id, status, shipping_address
FROM orders
WHERE status = 'READY';
~~~

Kế hoạch có thể:

1. Tìm các mục status = 'READY' trong chỉ mục.
2. Lấy row locator hoặc khóa chính từ mỗi mục.
3. Truy xuất hàng trong bảng để lấy shipping_address.
4. Trả kết quả.

Nếu có 50.000 hàng READY nằm trên nhiều trang phân tán, bước 3 có thể phát sinh nhiều lượt truy cập. Trong trường hợp cache nóng, nhiều lượt này có thể là buffer hit; trong trường hợp cache lạnh, chúng có thể gây nhiều lần đọc từ tầng lưu trữ.

Để đánh giá, không chỉ đếm số hàng kết quả. Cần xem:

- Số mục chỉ mục được đọc.
- Số lần lookup hoặc heap fetch.
- Số trang bảng khác nhau được truy cập.
- Logical reads và physical/buffer reads.
- Thời gian chờ I/O và cache hit.
- Số hàng bị loại bởi residual predicate.
- Tỷ lệ dữ liệu cần lấy thêm so với dữ liệu đã có trong chỉ mục.

### Vì sao lookup nhiều có thể đắt?

Một lần lookup có thể phải định vị trang, kiểm tra trạng thái phiên bản hàng, đọc dữ liệu và xử lý khóa hoặc visibility. Khi lặp hàng chục nghìn lần, chi phí cộng dồn có thể lớn. Nếu các hàng nằm rải rác, khả năng đọc trước giảm và thiết bị phải xử lý nhiều yêu cầu phân tán.

Tuy nhiên, không nên mặc định một lookup luôn tương ứng một lần đọc đĩa. Nhiều hàng có thể nằm cùng một trang; trang có thể được cache; engine có thể gom hoặc sắp xếp truy cập; thiết bị có thể xử lý nhiều yêu cầu song song. Đánh giá phải dựa trên số trang và số liệu thực tế thay vì nhân số hàng với một hằng số giả định.

### Số hàng và số trang quan trọng hơn chỉ số hàng đơn lẻ

Một truy vấn trả về 10.000 hàng không nhất thiết cần 10.000 lần đọc trang. Nếu các hàng nằm trên 100 trang liên tiếp, đường đọc có thể hiệu quả. Một truy vấn chỉ trả về 2.000 hàng cũng có thể tốn kém nếu mỗi hàng nằm trên một trang khác nhau và cache không chứa các trang đó.

Vì vậy, hãy phân biệt:

- Số hàng (rows): số bản ghi được xử lý hoặc trả về.
- Số trang (pages/blocks): số đơn vị lưu trữ được truy cập.
- Số lần đọc logic: số lần trang được yêu cầu từ buffer manager.
- Số lần đọc vật lý hoặc buffer read: số lần trang cần được nạp từ tầng thấp hơn theo cách hệ quản trị báo cáo.
- I/O request và I/O latency: số yêu cầu tới tầng lưu trữ và thời gian đáp ứng.

Số liệu cụ thể có thể được báo cáo ở các cấp khác nhau. Không cộng hoặc so sánh chúng nếu chưa hiểu phạm vi và định nghĩa.

## Tính chọn lọc và điểm cân bằng giữa chỉ mục với quét bảng

### Độ chọn lọc của điều kiện

Độ chọn lọc (selectivity) mô tả tỷ lệ hàng thỏa một điều kiện. Điều kiện rất chọn lọc trả về ít hàng so với tổng số hàng; điều kiện ít chọn lọc trả về tỷ lệ lớn.

Ví dụ trên bảng 10 triệu hàng:

- Điều kiện theo khóa chính trả về 1 hàng: thường phù hợp với tìm kiếm chỉ mục.
- Điều kiện trả về 500 hàng: chỉ mục có thể hiệu quả, tùy số trang và cột cần lấy.
- Điều kiện trả về 7 triệu hàng: quét tuần tự có thể rẻ hơn nhiều lookup rời rạc.

Các con số này chỉ minh họa. Điểm cân bằng phụ thuộc độ rộng hàng, độ rộng chỉ mục, phân bố vật lý, buffer cache, thiết bị, mức concurrency, số cột cần lấy và khả năng đọc song song.

### Tipping point

Tipping point là điểm mà tại đó chi phí của đường truy cập dùng chỉ mục cộng với lookup vượt chi phí quét bảng hoặc một đường truy cập khác. Khi tỷ lệ hàng phù hợp tăng, optimizer có thể chuyển từ Index Seek/Lookup sang scan.

Không có một tỷ lệ cố định áp dụng cho mọi bảng. Với bảng có hàng rộng và dữ liệu phân tán, lookup có thể trở nên đắt từ tỷ lệ khá thấp. Với bảng có hàng nhỏ, cache nóng và chỉ mục bao phủ, truy cập chỉ mục có thể vẫn có lợi ở tỷ lệ cao hơn.

Một mô hình khái quát:

~~~text
Chi phí đường chỉ mục
  = chi phí tìm kiếm chỉ mục
  + chi phí đọc các trang lá
  + chi phí truy xuất hàng còn thiếu
  + chi phí lọc và sắp xếp

Chi phí đường quét
  = chi phí đọc các trang bảng cần thiết
  + chi phí kiểm tra điều kiện
  + chi phí xử lý kết quả
~~~

Optimizer ước lượng các thành phần này dựa trên thống kê và mô hình chi phí. Nếu ước lượng số hàng hoặc số trang sai, nó có thể chọn đường truy cập không phù hợp.

### Vì sao số liệu thống kê quan trọng?

Thống kê về phân bố giá trị, số hàng, số trang và mức tương quan giữa thứ tự khóa với thứ tự vật lý giúp optimizer ước lượng số hàng và chi phí. Khi thống kê lỗi thời hoặc không mô tả được dữ liệu lệch, optimizer có thể nghĩ rằng điều kiện trả về ít hàng trong khi thực tế trả về rất nhiều.

Hãy kiểm tra Estimated Rows so với Actual Rows trong kế hoạch thực thi. Nếu chênh lệch lớn, xem thời điểm cập nhật thống kê, histogram, dữ liệu skew, correlation và độ nhạy tham số. Không nên tạo thêm chỉ mục trước khi hiểu vì sao optimizer đánh giá sai hoặc chọn đường truy cập hiện tại.

## Những yếu tố làm thay đổi chi phí truy xuất

### Độ rộng hàng và số cột cần lấy

Một hàng rộng chứa nhiều cột hoặc cột lớn có thể chiếm nhiều byte và làm số hàng trên mỗi trang giảm. Truy vấn SELECT * thường phải lấy nhiều dữ liệu hơn cần thiết, làm tăng I/O, truyền mạng và bộ nhớ. Nếu chỉ mục chứa đủ các cột nhỏ mà truy vấn cần, nó có thể giảm số trang phải đọc.

Tuy nhiên, đưa cột lớn như JSON, text hoặc địa chỉ dài vào chỉ mục có thể làm chỉ mục phình to. Hãy chỉ chọn cột cần thiết và đo lợi ích so với chi phí duy trì chỉ mục.

### Phân mảnh và mức tương quan vật lý

Khi thứ tự khóa chỉ mục tương quan tốt với vị trí vật lý của hàng, các lần truy xuất có thể tập trung trên ít trang hơn. Khi hàng phân tán, cùng một khoảng khóa có thể cần đọc nhiều trang rời rạc.

Một số hệ quản trị cung cấp thống kê về correlation hoặc fragmentation. Những chỉ số này cần được hiểu theo đúng engine. Reorganize, rebuild hoặc clustering có thể thay đổi cách dữ liệu được sắp xếp, nhưng cũng tiêu thụ I/O, CPU, log, dung lượng tạm và có thể khóa bảng. Không thực hiện chỉ vì một con số fragmentation cao mà chưa chứng minh tác động lên workload.

### Buffer cache và working set

Working set là tập trang thường được workload sử dụng trong một khoảng thời gian. Nếu working set vừa với cache, nhiều truy vấn có thể được phục vụ từ bộ nhớ. Nếu working set lớn hơn cache, các trang nóng có thể bị đẩy ra, làm tăng cache miss và đọc từ tầng lưu trữ.

Một truy vấn có thể chạy rất nhanh sau lần đầu vì dữ liệu đã được cache. Đo lần đầu và lần sau mà không ghi nhận trạng thái cache có thể dẫn đến kết luận sai. Không xóa cache production chỉ để đo cache lạnh; hãy dùng môi trường thử nghiệm hoặc phương pháp kiểm thử được kiểm soát.

### Concurrency và hàng đợi I/O

Ngay cả khi một truy vấn có số trang đọc không lớn, nhiều truy vấn đồng thời có thể cạnh tranh cùng thiết bị lưu trữ. I/O latency tăng có thể do hàng đợi, giới hạn IOPS hoặc throughput, tác vụ nền, backup, checkpoint hay các workload khác.

Đọc ngẫu nhiên thường tạo nhiều request nhỏ; đọc tuần tự có thể tạo request lớn và tận dụng throughput. Nhưng khi concurrency cao, cả hai kiểu đều có thể bị giới hạn. Hãy xem IOPS, throughput, average/p95 latency, queue depth, CPU wait và số phiên đang chờ I/O cùng lúc.

### Đọc song song và prefetch

Hệ quản trị có thể dùng parallel scan hoặc prefetch để tăng hiệu quả. Một thao tác quét tuần tự không nhất thiết chỉ dùng một luồng. Một số engine có thể gom các lần truy xuất hoặc đọc trước vùng dữ liệu dự kiến sẽ cần.

Parallelism có thể giảm thời gian một truy vấn nhưng làm tăng tổng tài nguyên tiêu thụ và ảnh hưởng các truy vấn khác. Đừng chỉ nhìn thời gian truy vấn đơn lẻ; hãy đánh giá throughput và độ trễ toàn workload.

## Cách giảm chi phí truy xuất bổ sung

### Tạo chỉ mục bao phủ khi có bằng chứng

Chỉ mục bao phủ chứa các cột cần thiết cho truy vấn, giúp giảm hoặc loại bỏ một số lần truy xuất hàng bổ sung. Ví dụ, nếu truy vấn chỉ cần customer_id, status, created_at và order_id, một chỉ mục ghép phù hợp có thể cung cấp đủ dữ liệu.

Cần cân nhắc:

- Điều kiện lọc và thứ tự sắp xếp.
- Thứ tự cột trong chỉ mục ghép.
- Số hàng và số trang thực tế được truy cập.
- Độ rộng của các cột bổ sung.
- Tần suất INSERT/UPDATE/DELETE.
- Dung lượng lưu trữ và tác động đến cache.
- Khả năng index-only hoặc covering access của engine.

Chỉ mục bao phủ không phải lúc nào cũng tránh hoàn toàn việc đọc bảng. PostgreSQL có thể cần heap fetch nếu visibility map không xác nhận các tuple trên trang đều hiển thị. Các engine khác cũng có điều kiện riêng.

### Giảm số hàng trước khi lookup

Nếu truy vấn có thể lọc chính xác hơn ở bước chỉ mục hoặc ở một bước trước join, số lần truy xuất hàng có thể giảm. Hãy kiểm tra residual predicate, thứ tự join và điều kiện lọc. Đừng thay đổi ngữ nghĩa truy vấn chỉ để làm số hàng giảm.

Ví dụ, chỉ lấy 50 đơn hàng mới nhất trước khi lấy cột lớn có thể giảm lượng dữ liệu cần truy xuất, nếu nghiệp vụ thực sự chỉ cần trang đó. Cần đảm bảo LIMIT và ORDER BY có thứ tự ổn định, đồng thời truy vấn con không làm thay đổi kết quả nghiệp vụ.

### Chỉ lấy cột cần dùng

Thay SELECT * bằng danh sách cột cần thiết giúp giảm byte đọc, byte truyền và bộ nhớ sử dụng. Nếu cột lớn không cần thiết cho mọi màn hình, có thể tải chúng ở bước riêng khi người dùng mở chi tiết. Thiết kế này chỉ phù hợp khi mô hình ứng dụng chấp nhận thêm một lần gọi và không làm tăng tổng độ trễ đáng kể.

### Gom truy cập theo trang hoặc theo lô

Nếu ứng dụng cần nhiều hàng, lấy dữ liệu theo lô và xử lý theo thứ tự phù hợp có thể giảm overhead so với hàng nghìn lần gọi riêng lẻ. Tuy nhiên, batching cần cân nhắc kích thước lô, memory footprint, transaction duration, lock duration và tính nhất quán dữ liệu.

Một số engine tự tối ưu đường đọc hoặc prefetch; không nên tự viết cơ chế gom dữ liệu phức tạp trước khi đo. Hãy kiểm tra kế hoạch và trace để biết lookup đang diễn ra ở database hay do ứng dụng phát sinh N+1 query.

### Cân nhắc clustering hoặc phân vùng

Tổ chức dữ liệu gần nhau theo khóa truy cập thường xuyên có thể cải thiện locality. Clustered index, CLUSTER, partitioning hoặc cơ chế sắp xếp vật lý có thể giúp một số workload đọc theo phạm vi.

Các thay đổi này có chi phí và giới hạn:

- Tái tổ chức dữ liệu có thể cần khóa hoặc tạo bản sao tạm.
- Dữ liệu mới ghi có thể dần làm mất trật tự vật lý.
- Chỉ một thứ tự vật lý có thể được ưu tiên tại một thời điểm đối với một bảng.
- Partitioning chỉ giúp khi điều kiện truy vấn cho phép partition pruning.
- Truy vấn khác có thể không được lợi hoặc thậm chí bị ảnh hưởng.

Hãy chọn theo mẫu truy cập quan trọng nhất và đo trên toàn workload.

## Ví dụ phân tích trước và sau

Một API tra cứu đơn hàng theo trạng thái trả về địa chỉ giao hàng. Bảng orders có 12 triệu hàng. Chỉ mục hiện tại là (status), trong khi truy vấn cần order_id, created_at và shipping_address.

Kế hoạch cho thấy chỉ mục tìm được 90.000 hàng READY, sau đó truy xuất hàng nhiều lần. Trong giờ cao điểm, p95 tăng và buffer reads cao. Nhóm đưa ra giả thuyết rằng lookup phân tán đang tạo nhiều truy cập bổ sung.

Trước khi thay đổi, nhóm đo:

| Chỉ số | Trước điều chỉnh |
|---|---:|
| Hàng thỏa điều kiện | 90.000 |
| Số lần lookup | 90.000 |
| Buffer/logical reads | 185.000 |
| p95 truy vấn | 420 ms |
| p99 truy vấn | 910 ms |
| CPU trung bình trong phép đo | 58% |

Nhóm thử một chỉ mục ứng viên theo mẫu truy vấn và đánh giá khả năng lấy các cột nhỏ từ chỉ mục. shipping_address là cột rộng nên không đưa ngay vào chỉ mục. Thay vào đó, nhóm kiểm tra xem API có cần địa chỉ trong mọi kết quả hay chỉ cần khi mở chi tiết. Sau khi điều chỉnh truy vấn và luồng lấy dữ liệu, phép đo đại diện cho kết quả:

| Chỉ số | Trước điều chỉnh | Sau điều chỉnh |
|---|---:|---:|
| Hàng cần lấy ở danh sách | 90.000 | 90.000 |
| Lookup ở truy vấn danh sách | 90.000 | 0 |
| Buffer/logical reads | 185.000 | 42.000 |
| p95 truy vấn danh sách | 420 ms | 105 ms |
| p99 truy vấn danh sách | 910 ms | 240 ms |
| Chi phí ghi do chỉ mục mới | Baseline | Tăng nhẹ |

Các con số chỉ minh họa. Kết quả thực tế phải được đo trên dữ liệu và workload của hệ thống. Nhóm cần kiểm tra thêm lần tải địa chỉ chi tiết, tổng số request của ứng dụng, tính nhất quán giữa hai lần đọc, dung lượng chỉ mục, thời gian ghi và tác động lên truy vấn khác. Nếu ứng dụng phải thực hiện thêm một truy vấn cho từng hàng, N+1 query có thể làm mất toàn bộ lợi ích.

## Quy trình đo và kiểm chứng

Khi nghi ngờ đọc ngẫu nhiên hoặc lookup làm truy vấn chậm, thực hiện theo thứ tự:

1. **Chọn truy vấn đại diện.** Ghi fingerprint, tham số, số hàng kết quả, tần suất và concurrency.
2. **Lấy kế hoạch thực thi.** Xác định scan, seek, lookup, heap fetch, bitmap, join và số lần lặp.
3. **So sánh hàng với trang.** Ghi Estimated Rows, Actual Rows, Rows Read, logical reads, physical/buffer reads và số trang nếu có.
4. **Đo thời gian I/O.** Theo dõi I/O latency, queue depth, IOPS, throughput và trạng thái cache.
5. **Xác định locality.** Xem hàng cần lấy có nằm trên ít trang hay phân tán, chỉ mục có bao phủ được cột cần thiết không.
6. **Viết giả thuyết.** Nêu rõ thao tác nào tạo chi phí, dự kiến thay đổi nào sẽ giảm số trang hoặc số lookup.
7. **Thử một thay đổi.** Có thể thay đổi chỉ mục, cột truy vấn, cách phân trang, clustering hoặc cách lấy dữ liệu.
8. **Chạy lại cùng workload.** Giữ dữ liệu, tham số, concurrency và cách đo tương đương.
9. **Đánh giá tác động phụ.** Kiểm tra chi phí ghi, dung lượng, cache, lock wait và các truy vấn khác.
10. **Theo dõi production có kiểm soát.** Quan sát đủ thời gian để phát hiện thay đổi do dữ liệu và workload tăng.

Không kết luận chỉ từ một lần chạy. Lặp lại phép đo để hiểu dao động do cache, checkpoint, tác vụ nền và hàng đợi. Không xóa cache hoặc tạo tải nặng trên production chỉ để ép xuất hiện random read.

## Những sai lầm thường gặp

- **Cho rằng mọi random read đều chậm:** SSD/NVMe và cache có thể làm giảm đáng kể chi phí, nhưng vẫn cần đo IOPS, latency và queue.
- **Cho rằng scan luôn là đọc tuần tự tối ưu:** dữ liệu có thể phân mảnh, phân vùng hoặc bị cạnh tranh I/O.
- **Đếm hàng thay cho đếm trang:** nhiều hàng cùng trang có chi phí khác nhiều hàng nằm trên các trang riêng biệt.
- **Coi mỗi lookup là một lần đọc đĩa:** trang có thể được cache hoặc nhiều hàng có thể nằm cùng trang.
- **Chỉ nhìn số hàng trả về:** bỏ qua số hàng đọc, residual filter và số trang phải truy cập.
- **Tạo chỉ mục bao phủ quá rộng:** tăng dung lượng, chi phí ghi và áp lực cache.
- **Không xem xét cột lớn:** đưa JSON, text hoặc dữ liệu dài vào chỉ mục có thể làm chỉ mục phình to.
- **Bỏ qua workload ghi:** cải thiện đọc có thể làm INSERT/UPDATE/DELETE chậm hơn.
- **Đo khi cache không ổn định:** so sánh một lần cache nóng với một lần cache lạnh dẫn đến kết luận sai.
- **Không kiểm tra N+1 query:** chuyển lookup về ứng dụng có thể tạo thêm nhiều round trip.
- **Tái tổ chức dữ liệu theo một truy vấn duy nhất:** có thể làm workload khác mất locality hoặc tăng chi phí bảo trì.

## Checklist đánh giá chi phí đọc

- [ ] Xác định truy vấn cần bao nhiêu hàng và bao nhiêu cột.
- [ ] Phân biệt logical reads, buffer reads và physical I/O theo hệ quản trị.
- [ ] Kiểm tra số trang được đọc và mức độ locality.
- [ ] Xác định đường truy cập là tuần tự, ngẫu nhiên hay kết hợp.
- [ ] Kiểm tra số lần lookup/heap fetch và số vòng lặp.
- [ ] So sánh số hàng đọc với số hàng trả về.
- [ ] Đánh giá độ chọn lọc và tipping point giữa lookup với scan.
- [ ] Kiểm tra trạng thái cache, I/O latency, IOPS, throughput và queue.
- [ ] Cân nhắc chỉ mục bao phủ, cột lớn, clustering và batching.
- [ ] Đo lại cả workload đọc và ghi sau thay đổi.

Đọc ngẫu nhiên, đọc tuần tự và truy xuất bổ sung về bảng là những phần của cùng một đường đi dữ liệu. Một chỉ mục chỉ giúp định vị hàng; hiệu năng cuối cùng còn phụ thuộc số trang cần lấy, vị trí của chúng, cache, thiết bị lưu trữ và số lần truy cập bổ sung. Khi kết hợp kế hoạch thực thi với thống kê trang, I/O, độ chọn lọc và workload thực tế, nhóm có thể quyết định khi nào nên dùng chỉ mục, khi nào nên chấp nhận scan và cách giảm chi phí đọc mà không làm suy giảm các thao tác ghi.