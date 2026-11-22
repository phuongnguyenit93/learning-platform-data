# Ảnh hưởng của độ rộng hàng và tính cục bộ dữ liệu đến đường truy cập

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích độ rộng hàng ảnh hưởng thế nào đến mật độ trang, kích thước bảng, chỉ mục và hiệu quả bộ nhớ đệm.
- Phân biệt tính cục bộ theo không gian, thời gian và thứ tự truy cập; nhận biết truy cập tuần tự và truy cập ngẫu nhiên.
- Đọc kế hoạch thực thi để đánh giá đường truy cập có phù hợp với độ rộng hàng và cách dữ liệu được bố trí hay không.
- Cân nhắc projection, chỉ mục bao phủ, khóa phân cụm, phân vùng và tách dữ liệu lớn để cải thiện hiệu năng.
- Thiết kế phép đo trước/sau dựa trên workload thực tế, đồng thời đánh giá chi phí ghi và lưu trữ.

## 1. Đường truy cập dữ liệu phụ thuộc vào cách dữ liệu được lưu

Đường truy cập (access path) là cách hệ quản trị tìm, đọc và trả về các hàng đáp ứng một câu truy vấn. Bộ tối ưu có thể chọn quét bảng, tìm qua chỉ mục, quét một vùng chỉ mục, kết hợp nhiều chỉ mục hoặc dùng một phương án khác tùy hệ quản trị.

Quyết định này không chỉ phụ thuộc vào điều kiện `WHERE`. Nó còn phụ thuộc số hàng cần đọc, số byte phải chuyển, số trang dữ liệu nằm trên đĩa hoặc trong bộ nhớ đệm, thứ tự vật lý của các hàng và khả năng các hàng cần thiết nằm gần nhau.

Trong module DATABASE_PERFORMANCE, khi đánh giá chỉ mục và SQL cần xem cả cơ chế lưu trữ. Hai bảng có cùng số hàng và cùng truy vấn có thể có hiệu năng rất khác nếu một bảng chứa các hàng ngắn, còn bảng kia chứa nhiều cột rộng, payload lớn hoặc dữ liệu được ghi theo thứ tự không phù hợp với mẫu truy cập.

**Độ rộng hàng** là lượng không gian mà một hàng chiếm trong cấu trúc lưu trữ, bao gồm dữ liệu cột và phần overhead của hệ quản trị. **Tính cục bộ dữ liệu** mô tả mức độ các dữ liệu thường được truy cập cùng nhau nằm gần nhau trong bộ nhớ hoặc trên thiết bị lưu trữ.

## 2. Độ rộng hàng và mật độ trang

Cơ sở dữ liệu thường đọc và ghi dữ liệu theo đơn vị trang (page hoặc block), thay vì đọc riêng từng hàng. Một trang có kích thước cố định theo cấu hình hoặc kiến trúc của hệ quản trị. Nhiều hàng có thể nằm trong một trang.

Số hàng chứa được trong một trang phụ thuộc vào:

- Dung lượng trang có thể dùng cho dữ liệu sau khi trừ page header và cấu trúc quản lý trang.
- Kích thước trung bình của hàng, gồm tuple/record header, null bitmap, offset hoặc slot, alignment và dữ liệu cột.
- Phần dung lượng được giữ trống để hỗ trợ cập nhật hoặc giảm page split.
- Cách hệ quản trị lưu dữ liệu biến độ dài, dữ liệu lớn và phiên bản hàng.

Vì vậy, hàng càng rộng thì số hàng trên mỗi trang thường càng giảm. Bảng cần nhiều trang hơn để chứa cùng số bản ghi, làm tăng dung lượng lưu trữ và số trang phải đọc khi quét một tập dữ liệu.

### Ước lượng mật độ trang

Để hình dung, giả sử một trang 8 KiB có khoảng 7,5 KiB dành cho các hàng sau khi trừ phần quản lý. Nếu một hàng cùng overhead chiếm trung bình 200 byte, trang có thể chứa xấp xỉ 38 hàng. Nếu hàng chiếm 800 byte, trang chỉ chứa khoảng 9 hàng.

Đây là phép tính minh họa. Số thực tế phụ thuộc page header, slot/line pointer, alignment, fill factor, độ dài biến đổi, nén và cơ chế lưu trữ của hệ quản trị.

| Kích thước hàng minh họa | Số hàng ước lượng mỗi trang | Trang cần cho 100.000 hàng (ước lượng) |
| ---: | ---: | ---: |
| 200 byte | 38 | 2.632 |
| 400 byte | 19 | 5.264 |
| 800 byte | 9 | 11.112 |

Khi hàng rộng gấp bốn lần, số trang cần thiết trong ví dụ tăng hơn bốn lần do cách làm tròn và dung lượng trang cố định. Trong thực tế, việc tăng số trang có thể kéo theo nhiều I/O hơn, chiếm thêm buffer pool và làm giảm số hàng hữu ích nằm trong cache.

### Hệ quả đối với quét bảng

Với full table scan, hệ quản trị phải đọc các trang chứa toàn bộ hàng của bảng. Hàng rộng làm tăng tổng số byte cần đọc ngay cả khi truy vấn chỉ dùng một vài cột. Nếu truy vấn trả về nhiều hàng, dữ liệu lớn còn làm tăng chi phí truyền kết quả qua mạng và xử lý ở ứng dụng.

Với truy vấn chỉ cần một vài cột, câu `SELECT *` có thể buộc hệ thống đọc và chuyển các cột không cần thiết. Projection rõ ràng giúp giảm dữ liệu trả về; nếu chỉ mục chứa đủ các cột cần thiết, hệ quản trị có thể tránh đọc một phần hoặc toàn bộ trang dữ liệu chính, tùy loại chỉ mục và hệ quản trị.

## 3. Độ rộng hàng ảnh hưởng đến chỉ mục

Không phải mọi chỉ mục đều lưu toàn bộ hàng. Một chỉ mục thường lưu khóa, thông tin định vị hàng hoặc các cột được thêm vào để bao phủ truy vấn. Cấu trúc cụ thể khác nhau giữa heap table, clustered index và clustered table.

Độ rộng khóa chỉ mục có ảnh hưởng trực tiếp đến số mục có thể chứa trong trang chỉ mục. Khóa rộng làm giảm số mục mỗi trang, khiến cây B-tree có thể cần nhiều trang hơn, giảm fan-out và tăng kích thước chỉ mục. Điều này ảnh hưởng đến cache, I/O và chi phí duy trì chỉ mục.

Ở một số hệ quản trị, chỉ mục phụ còn lưu khóa của chỉ mục clustered hoặc row locator. Ví dụ, InnoDB lưu khóa chính trong các nút lá của secondary index; SQL Server dùng clustered key làm row locator trong nonclustered index. Vì vậy, khóa chính quá rộng có thể làm tất cả chỉ mục phụ lớn hơn.

Với chỉ mục bao phủ (covering index), các cột truy vấn cần có thể được lấy trực tiếp từ chỉ mục. Điều này giảm lượt tra cứu hàng trong bảng, nhưng thêm cột vào chỉ mục làm mỗi mục rộng hơn, tăng dung lượng, chi phí ghi và bộ nhớ cache.

Ví dụ, truy vấn:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC;
```

có thể được hỗ trợ bởi một chỉ mục trên `(customer_id, created_at)` và cột `total_amount` được include hoặc lưu ở phần lá nếu hệ quản trị hỗ trợ. Chỉ mục như vậy có thể tránh lookup cho một số kế hoạch, nhưng quyết định thêm cột cần dựa trên tần suất truy vấn, kích thước cột và chi phí cập nhật.

Không nên đưa mọi cột vào chỉ mục với mục tiêu tránh lookup. Một cột JSON hoặc văn bản dài có thể làm chỉ mục tăng rất lớn. Hãy cân nhắc chỉ mục bao phủ hẹp, truy vấn đọc riêng payload lớn hoặc tách phần dữ liệu ít được dùng.

## 4. Dữ liệu lớn và lưu trữ ngoài hàng

Nhiều hệ quản trị có cơ chế lưu giá trị lớn ngoài vùng hàng chính hoặc trên các trang overflow. PostgreSQL dùng TOAST cho một số giá trị lớn; InnoDB có thể lưu một phần dữ liệu lớn ở trang overflow/off-page; SQL Server có cơ chế row-overflow và LOB storage.

Các cơ chế này giúp hàng chính không phải chứa toàn bộ payload lớn, nhưng truy cập cột lớn có thể cần thêm lần đọc trang và bước giải mã hoặc tái dựng giá trị. Hàng metadata ngắn có thể được đọc nhanh mà không cần tải payload, trong khi `SELECT *` hoặc projection chứa cột LOB có thể phát sinh nhiều I/O hơn.

Ví dụ, bảng tài liệu có các cột `document_id`, `owner_id`, `created_at`, `title` và `body`. Danh sách tài liệu thường chỉ cần ID, tiêu đề và ngày tạo. Nếu truy vấn danh sách luôn lấy cả `body`, nó có thể đọc dữ liệu ngoài hàng cho mọi bản ghi dù giao diện không hiển thị nội dung.

Có thể tách payload lớn sang bảng chi tiết hoặc chỉ truy xuất nó khi người dùng mở tài liệu. Việc tách bảng làm tăng số lần join hoặc truy vấn khi cần toàn bộ dữ liệu, do đó cần dựa trên tỷ lệ đọc metadata so với payload và yêu cầu nhất quán.

## 5. Tính cục bộ dữ liệu là gì?

Tính cục bộ (locality) mô tả xu hướng các lần truy cập tiếp theo dùng dữ liệu gần với dữ liệu vừa được truy cập. Có ba khía cạnh thường gặp:

- **Cục bộ theo thời gian (temporal locality):** dữ liệu vừa được truy cập có khả năng được truy cập lại sớm. Ví dụ, trang sản phẩm bán chạy được nhiều request đọc liên tục.
- **Cục bộ theo không gian (spatial locality):** dữ liệu nằm gần nhau có khả năng được truy cập trong cùng một thao tác. Ví dụ, các bản ghi giao dịch cùng tài khoản hoặc cùng khoảng thời gian nằm trên các trang gần nhau.
- **Cục bộ theo thứ tự (sequential locality):** workload truy cập dữ liệu theo thứ tự liên tiếp, chẳng hạn đọc một khoảng khóa hoặc quét theo ngày.

Locality tốt giúp tận dụng buffer pool và cache của hệ điều hành, giảm số lần đọc vật lý và tăng hiệu quả read-ahead hoặc prefetch khi hệ quản trị hỗ trợ. Locality kém khiến cùng một lượng hàng phải được lấy từ nhiều trang rải rác, tạo truy cập ngẫu nhiên và giảm hiệu quả cache.

Locality không chỉ là vị trí vật lý trên đĩa. Trang có thể đã ở trong buffer pool; khi đó truy cập ngẫu nhiên vẫn có chi phí CPU, latch, cache miss ở CPU hoặc quản lý buffer, nhưng không nhất thiết tạo I/O vật lý. Vì vậy, cần phân biệt logical reads với physical reads.

## 6. Truy cập tuần tự và truy cập ngẫu nhiên

### Truy cập tuần tự

Truy cập tuần tự đọc các trang hoặc hàng theo thứ tự gần liên tiếp. Ví dụ, báo cáo lấy toàn bộ đơn hàng của một tháng khi dữ liệu được tổ chức tương đối gần theo thời gian.

Ưu điểm thường gặp:

- Có thể tận dụng read-ahead và I/O theo lô.
- Ít phải nhảy giữa các vùng dữ liệu hơn khi bố trí vật lý phù hợp.
- Phù hợp với truy vấn đọc tỷ lệ lớn dữ liệu hoặc quét theo phạm vi.

### Truy cập ngẫu nhiên

Truy cập ngẫu nhiên cần tìm các hàng nằm ở nhiều trang phân tán, thường qua một chỉ mục hoặc các khóa không có tương quan với thứ tự lưu trữ.

Ví dụ, một truy vấn tìm 5.000 khách hàng trong bảng có 20 triệu hàng bằng một tập khóa ngẫu nhiên có thể phải chạm vào hàng nghìn trang khác nhau. Dù số hàng kết quả nhỏ so với toàn bảng, lượng trang phải đọc vẫn có thể lớn.

Truy cập ngẫu nhiên không luôn xấu. Nếu các trang đã ở trong cache, số hàng ít, hoặc thiết bị lưu trữ có độ trễ thấp, index seek kết hợp lookup vẫn có thể nhanh hơn quét toàn bảng. Bộ tối ưu cần cân bằng số trang dự kiến, cache, độ chọn lọc, chi phí CPU và kiểu I/O.

| Đặc điểm | Quét tuần tự | Truy cập ngẫu nhiên qua chỉ mục |
| --- | --- | --- |
| Mẫu đọc | Nhiều trang liên tiếp | Các trang có thể phân tán |
| Phù hợp khi | Đọc tỷ lệ lớn dữ liệu hoặc xử lý theo phạm vi | Đọc số lượng nhỏ hàng có thể định vị chính xác |
| Lợi thế | Read-ahead, I/O theo lô và chi phí định vị thấp | Tránh đọc các hàng không liên quan khi điều kiện chọn lọc cao |
| Rủi ro | Đọc nhiều dữ liệu không cần thiết nếu phạm vi rộng | Nhiều random lookup khi hàng cần thiết nằm rải rác |

## 7. Mối quan hệ giữa clustering và locality

Clustering mô tả mức độ thứ tự vật lý của hàng tương quan với khóa hoặc chiều truy cập. Khi các hàng thường được truy vấn cùng nhau nằm gần nhau, range scan có thể đọc ít trang và tận dụng locality tốt hơn.

Ví dụ, bảng sự kiện được ghi và truy vấn chủ yếu theo `event_time`. Nếu các hàng gần nhau theo thời gian được lưu gần nhau, truy vấn một khoảng thời gian có thể đọc một vùng trang tương đối liên tục.

Ngược lại, nếu dữ liệu được chèn theo thời gian nhưng truy vấn chủ yếu theo `customer_id`, các sự kiện của một khách hàng có thể nằm rải rác trên nhiều trang. Một chỉ mục trên `customer_id` vẫn có thể tìm đúng hàng, nhưng việc lấy dữ liệu từ bảng có thể cần nhiều lần truy cập trang nếu hàng không được sắp gần nhau theo chiều đó.

Chỉ có thể tối ưu thứ tự vật lý theo một số chiều nhất định. Sắp xếp theo thời gian có thể tốt cho báo cáo thời gian nhưng không nhất thiết tốt cho tra cứu theo khách hàng. Các chỉ mục phụ tạo thêm đường truy cập thay thế, song cũng làm tăng chi phí ghi và lưu trữ.

### Cách tổ chức khác nhau giữa hệ quản trị

- **InnoDB:** bảng được tổ chức theo clustered index, thường là khóa chính. Các hàng nằm ở các lá của clustered index; secondary index chứa khóa chính để tìm hàng. Khóa chính ngắn và ổn định thường giúp giảm kích thước các chỉ mục phụ.
- **SQL Server:** bảng có thể là heap hoặc clustered table. Clustered index xác định thứ tự các hàng ở cấp lá; nonclustered index dùng row locator để tìm hàng hoặc có thể bao phủ truy vấn bằng included columns.
- **PostgreSQL:** bảng heap không tự duy trì thứ tự vật lý theo một chỉ mục. `CLUSTER` có thể sắp lại bảng theo chỉ mục tại thời điểm chạy, nhưng các lần ghi sau không bảo đảm duy trì thứ tự đó. Chỉ mục và heap cần được xem xét riêng khi đánh giá locality.

Không nên áp dụng một quy tắc về clustering cho mọi hệ quản trị. Hãy xác định bảng là heap hay clustered, row locator được lưu ra sao và thao tác bảo trì có giữ được thứ tự vật lý hay không.

## 8. Độ rộng hàng kết hợp với locality trong buffer cache

Buffer pool có dung lượng hữu hạn. Khi hàng rộng làm bảng và chỉ mục chiếm nhiều trang hơn, cùng một dung lượng bộ nhớ chứa được ít hàng hữu ích hơn. Nếu workload thường xuyên truy cập một tập dữ liệu lớn, cache có thể bị thay thế liên tục.

Ví dụ, một bảng có 10 triệu hàng với hàng trung bình 300 byte cần ít trang hơn đáng kể so với cùng số hàng có kích thước 1.200 byte. Nếu ứng dụng chỉ cần bốn cột nhỏ nhưng truy vấn thường xuyên lấy cả hàng, cache sẽ dành nhiều không gian cho payload ít được dùng.

Locality theo thời gian giúp giữ lại các trang nóng. Locality theo không gian giúp một lần đọc trang đưa vào cache nhiều hàng có khả năng được truy cập tiếp theo. Khi hàng rộng, số hàng lân cận trên một trang giảm, nên một lần nạp trang có thể mang lại ít hàng hữu ích hơn.

Đánh giá cache hit ratio một mình có thể gây hiểu nhầm. Cần xem cả số logical reads, physical reads, bytes đọc, số trang được truy cập và độ trễ. Một tỷ lệ hit cao vẫn có thể đi kèm lượng logical reads rất lớn nếu truy vấn phải quét nhiều trang đã nằm trong cache.

## 9. Ảnh hưởng đến cập nhật, MVCC và page split

Độ rộng hàng và cách bố trí dữ liệu ảnh hưởng cả đường ghi.

- Hàng rộng cần nhiều byte hơn trong log ghi trước (WAL/transaction log) khi nội dung thay đổi hoặc khi phải ghi một phiên bản mới.
- Hàng có cột biến độ dài có thể cần di chuyển hoặc lưu phần dữ liệu ở trang khác khi kích thước thay đổi.
- Trang có ít khoảng trống dễ phải phân trang (page split) hoặc di chuyển hàng khi cần chèn/cập nhật.
- Nhiều chỉ mục chứa khóa rộng hoặc cột include rộng làm tăng số trang cần cập nhật cho mỗi thao tác ghi.

Trong hệ thống dùng MVCC như PostgreSQL, cập nhật thường tạo phiên bản tuple mới. Nếu trang cũ còn chỗ và điều kiện HOT update được đáp ứng, PostgreSQL có thể tránh cập nhật một số chỉ mục. Nếu không có đủ chỗ hoặc cột được cập nhật nằm trong chỉ mục, việc cập nhật có thể tạo thêm công việc cho chỉ mục và vacuum.

Fill factor là một trong các cách giữ lại khoảng trống trong trang hoặc chỉ mục để hỗ trợ cập nhật và giảm một số page split. Giá trị thấp hơn có thể cải thiện một số workload ghi nhưng làm tăng kích thước lưu trữ và số trang đọc. Đây không phải tham số nên giảm tùy tiện; hãy đo theo kiểu cập nhật và mức tăng trưởng dữ liệu.

## 10. Thiết kế hàng và projection theo workload

### Chỉ lấy các cột cần thiết

Tránh `SELECT *` trong các đường truy cập thường xuyên nếu ứng dụng chỉ cần một phần dữ liệu. Projection rõ ràng giúp giảm số byte đọc và truyền, đồng thời tăng khả năng xây dựng chỉ mục bao phủ vừa đủ.

```sql
-- Lấy mọi cột dù màn hình danh sách chỉ cần vài trường
SELECT *
FROM documents
WHERE owner_id = ?
ORDER BY created_at DESC;

-- Chỉ lấy các trường cần hiển thị
SELECT document_id, title, created_at
FROM documents
WHERE owner_id = ?
ORDER BY created_at DESC;
```

Nếu `documents` có cột body rất lớn, truy vấn thứ hai có thể tránh tải payload khi hệ quản trị có thể đọc các cột cần thiết từ đường truy cập phù hợp.

### Tách phần dữ liệu ít được truy cập

Với bảng có nhiều metadata nhỏ và một số cột payload lớn ít khi đọc, có thể tách payload sang bảng chi tiết. Cách này làm hàng chính hẹp hơn và giúp các truy vấn phổ biến đọc ít byte hơn.

Ví dụ:

```sql
CREATE TABLE document_summary (
    document_id BIGINT PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE document_body (
    document_id BIGINT PRIMARY KEY,
    body TEXT NOT NULL
);
```

Luồng danh sách chỉ đọc `document_summary`; luồng xem nội dung mới truy vấn `document_body`. Thiết kế này có thể giảm I/O cho danh sách nhưng tăng số lần truy vấn hoặc join khi cần toàn bộ tài liệu. Cần đánh giá tỷ lệ hai loại thao tác, yêu cầu transaction và chi phí lưu trữ.

### Chọn khóa phân cụm và thứ tự chỉ mục

Chọn khóa dựa trên các mẫu truy cập phổ biến, tính duy nhất, độ rộng khóa, tính ổn định và thứ tự range scan cần hỗ trợ. Khóa tăng tuần tự có thể giúp chèn ở cuối cây chỉ mục trong một số thiết kế, nhưng cũng có thể tạo điểm nóng ghi ở trang cuối khi concurrency cao. Khóa ngẫu nhiên có thể phân tán ghi nhưng tăng page split và giảm locality cho range scan.

Với composite index, thứ tự cột quan trọng. Chỉ mục `(customer_id, created_at)` phù hợp với truy vấn lọc theo khách hàng và sắp xếp hoặc lọc theo thời gian trong phạm vi khách hàng. Nó không nhất thiết thay thế chỉ mục bắt đầu bằng `created_at` cho báo cáo thời gian toàn hệ thống.

## 11. Khi nào nên dùng index scan, bitmap scan hoặc sequential scan?

Bộ tối ưu ước lượng chi phí của các đường truy cập dựa trên thống kê, độ chọn lọc, số trang, độ tương quan và cấu hình chi phí.

- **Index seek/scan:** thường có lợi khi điều kiện chọn lọc cao và có thể định vị một số ít hàng hoặc một vùng chỉ mục.
- **Index lookup/heap fetch:** sau khi tìm khóa trong chỉ mục, hệ quản trị cần truy cập hàng ở bảng. Nếu các hàng phân tán, số lần đọc trang có thể lớn.
- **Bitmap heap scan:** một số hệ quản trị như PostgreSQL có thể gom các vị trí hàng thành bitmap và thăm trang heap theo thứ tự để giảm truy cập ngẫu nhiên khi số hàng kết quả ở mức trung bình.
- **Sequential/table scan:** có thể tốt hơn khi cần phần lớn hàng, hàng rộng, chỉ mục không đủ bao phủ hoặc chi phí lookup cao.

Không nên ép dùng index scan chỉ vì có chỉ mục. Với hàng rộng và dữ liệu phân tán, quét bảng một lần có thể rẻ hơn hàng nghìn lần tra cứu trang ngẫu nhiên. Ngược lại, nếu chỉ cần vài hàng và index có độ chọn lọc tốt, quét toàn bảng sẽ đọc thừa nhiều dữ liệu.

## 12. Cách đo độ rộng hàng và locality

Đo theo một query fingerprint và workload cụ thể. Thu thập cả số hàng, số trang và số byte để hiểu đường truy cập thực sự.

### Chỉ số cần quan sát

- Kích thước bảng, chỉ mục và số trang dữ liệu.
- Kích thước hàng trung bình và phân bố kích thước, đặc biệt với cột biến độ dài.
- Số hàng trên mỗi trang hoặc page density nếu hệ quản trị cung cấp.
- Số logical reads, physical reads và bytes đọc.
- Số lần index lookup/heap fetch và số trang khác nhau được truy cập.
- Độ tương quan giữa thứ tự khóa và thứ tự vật lý nếu hệ quản trị cung cấp.
- Cache hit, read-ahead, page split, fragmentation hoặc bloat.
- Thời gian CPU, thời gian chờ I/O, độ trễ p50/p95/p99 và throughput.

### Ví dụ với PostgreSQL

`EXPLAIN (ANALYZE, BUFFERS)` cho biết số dòng thực tế, thời gian và hoạt động buffer của kế hoạch:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT document_id, title, created_at
FROM document_summary
WHERE owner_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

Đọc `shared hit` và `shared read` để phân biệt trang được lấy từ shared buffers với trang phải đọc vào shared buffers trong lần chạy. Các trường này không đồng nghĩa trực tiếp với số lần đọc vật lý từ thiết bị vì hệ điều hành cũng có cache. So sánh actual rows, loops, heap fetches nếu là index-only scan và các nút sort hoặc bitmap.

PostgreSQL có thống kê cột như `pg_stats.correlation` để phản ánh tương quan giữa thứ tự giá trị cột và thứ tự vật lý của hàng. Giá trị gần 1 hoặc -1 cho thấy thứ tự có tương quan mạnh theo một chiều; giá trị gần 0 cho thấy ít tương quan. Đây là tín hiệu thống kê, không phải phép đo đầy đủ về thời gian I/O hoặc locality trong mọi workload.

### Ví dụ với SQL Server

Trong SQL Server, có thể dùng actual execution plan cùng `SET STATISTICS IO, TIME ON` để xem logical reads, physical reads (nếu có), read-ahead reads và CPU/elapsed time:

```sql
SET STATISTICS IO, TIME ON;

SELECT TOP (50)
    DocumentId, Title, CreatedAt
FROM dbo.DocumentSummary
WHERE OwnerId = 42
ORDER BY CreatedAt DESC;

SET STATISTICS IO, TIME OFF;
```

Trong actual plan, kiểm tra scan/seek, key lookup, số hàng thực tế, số lần thực thi và operator có spill. Các DMV và báo cáo index có thể cung cấp thêm page count, page density hoặc fragmentation; hãy đọc đúng ngữ nghĩa của chỉ số theo phiên bản SQL Server.

### Đo trong điều kiện có thể so sánh

Chạy nhiều lần để phân biệt cold cache và warm cache. Không xóa cache trên môi trường sản xuất chỉ để tạo một phép đo cold cache. Dùng môi trường kiểm thử hoặc phương pháp kiểm soát có phê duyệt, ghi lại trạng thái cache và cùng điều kiện dữ liệu.

## 13. Quy trình điều tra và cải thiện access path

1. **Xác định truy vấn và mục tiêu.** Chọn nhóm nghiệp vụ, query fingerprint, số lần gọi và mục tiêu độ trễ hoặc I/O.
2. **Đo đường cơ sở.** Ghi p50/p95/p99, throughput, CPU, logical/physical reads, số trang, bytes và trạng thái cache.
3. **Kiểm tra projection và kích thước hàng.** Xác định truy vấn có lấy cột không cần thiết, payload lớn hoặc nhiều hàng hơn cần thiết không.
4. **Đọc execution plan.** Kiểm tra scan/seek, lookup, bitmap, sort, join, actual rows, estimated rows và số trang đọc.
5. **Đánh giá locality.** Xác định các hàng thường truy cập cùng nhau có nằm gần nhau không; xem clustering, correlation, khóa nóng và phân bố tham số.
6. **Chọn thay đổi nhỏ.** Có thể thu hẹp projection, thêm chỉ mục hẹp, thay đổi thứ tự khóa, tách payload, phân vùng hoặc điều chỉnh fill factor.
7. **Chạy lại cùng workload.** Giữ nguyên dữ liệu, tham số, tốc độ đến, concurrency và trạng thái cache tương đương.
8. **Đánh giá tác động phụ.** Kiểm tra dung lượng chỉ mục, thời gian ghi, WAL/transaction log, page split, vacuum/bloat và hiệu năng truy vấn khác.
9. **Theo dõi dài hạn.** Xác nhận lợi ích còn tồn tại khi dữ liệu tăng, phân bố thay đổi và các tác vụ nền chạy đồng thời.

Ví dụ: một endpoint danh sách đơn hàng chỉ hiển thị 20 bản ghi nhưng truy vấn lấy `SELECT *` từ bảng có cột JSON lớn. Trước tiên hãy đo bytes đọc và số trang; sau đó đổi projection và kiểm tra kế hoạch. Nếu truy vấn vẫn phải lookup nhiều hàng, thử một chỉ mục hẹp trên `(customer_id, created_at)` và chỉ bao phủ các cột nhỏ thực sự cần. Đo lại thời gian đọc và chi phí ghi trước khi giữ chỉ mục.

## 14. Những sai lầm thường gặp

- **Cho rằng index seek luôn nhanh hơn scan.** Hàng cần đọc có thể nằm trên nhiều trang rải rác, tạo nhiều lookup ngẫu nhiên.
- **Chỉ đếm số hàng mà bỏ qua số byte.** Hai truy vấn trả cùng số hàng có thể có chi phí rất khác khi độ rộng hàng khác nhau.
- **Dùng `SELECT *` trong đường truy cập phổ biến.** Dữ liệu lớn hoặc cột ít dùng làm tăng số byte đọc và truyền.
- **Đưa mọi cột vào covering index.** Chỉ mục rộng làm tăng lưu trữ, cache footprint và chi phí ghi.
- **Chọn khóa phân cụm theo một truy vấn duy nhất.** Thứ tự vật lý tối ưu cho một chiều có thể không tốt cho chiều truy cập khác.
- **Đồng nhất logical read với physical I/O.** Trang có thể được phục vụ từ cache dù truy vấn vẫn phải xử lý nhiều logical reads.
- **Bỏ qua dữ liệu ngoài hàng.** Cột LOB hoặc payload lớn có thể tạo thêm I/O dù hàng chính nhìn có vẻ nhỏ.
- **Giảm fill factor mà không đo.** Giữ nhiều chỗ trống làm tăng số trang và có thể tăng chi phí đọc.
- **Đánh giá locality chỉ bằng một lần chạy.** Cache nóng, dữ liệu nhỏ hoặc workload không đại diện có thể che giấu truy cập ngẫu nhiên.

## 15. Danh sách kiểm tra khi thiết kế đường truy cập

- [ ] Đã đo kích thước hàng và số trang của bảng, chỉ mục quan trọng.
- [ ] Truy vấn chỉ lấy các cột cần thiết cho nghiệp vụ.
- [ ] Cột lớn hoặc ít dùng được đánh giá riêng về cách lưu và thời điểm truy xuất.
- [ ] Khóa chỉ mục có độ rộng phù hợp và hỗ trợ thứ tự truy cập phổ biến.
- [ ] Đã cân nhắc tác động của khóa chính lên kích thước chỉ mục phụ.
- [ ] Execution plan được đánh giá bằng actual rows và số trang đọc.
- [ ] Đã phân biệt logical reads, physical reads và cache hit.
- [ ] Đã xem xét locality, clustering/correlation và phân bố dữ liệu.
- [ ] Đã đo truy cập tuần tự và ngẫu nhiên với workload đại diện.
- [ ] Chỉ mục bao phủ chỉ chứa các cột có lợi rõ ràng.
- [ ] Thay đổi đã được kiểm tra cả hiệu năng đọc, ghi, dung lượng và bảo trì.
- [ ] Phép đo trước/sau dùng điều kiện tương đương và được theo dõi sau triển khai.

## Kết luận

Độ rộng hàng quyết định một phần mật độ trang, kích thước bảng và chỉ mục, lượng dữ liệu đi qua cache và số byte phải đọc hoặc ghi. Tính cục bộ quyết định các hàng thường được truy cập cùng nhau có thể được phục vụ từ ít trang gần nhau hay phải tìm qua nhiều trang rải rác. Vì vậy, đường truy cập tốt phụ thuộc đồng thời vào độ chọn lọc, độ rộng hàng, cấu trúc chỉ mục, thứ tự lưu trữ và mẫu workload. Hãy đo số trang, logical/physical reads, bytes, cache và execution plan; sau đó điều chỉnh projection, chỉ mục, clustering hoặc cách tách payload và kiểm chứng cả lợi ích đọc lẫn chi phí ghi.
