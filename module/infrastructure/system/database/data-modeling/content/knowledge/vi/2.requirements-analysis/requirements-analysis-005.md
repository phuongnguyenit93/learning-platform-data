# Liệt kê thao tác đọc, ghi, tìm kiếm, tổng hợp và tần suất thực hiện

## 1. Vì sao phải khảo sát workload?

Khi chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu, việc xác định thực thể và quan hệ mới chỉ trả lời câu hỏi dữ liệu gồm những gì. Thiết kế còn phải trả lời dữ liệu được truy cập như thế nào, bởi ai, vào thời điểm nào, với quy mô bao nhiêu và yêu cầu phản hồi ra sao.

Tập hợp các thao tác mà hệ thống thực hiện trên dữ liệu được gọi là **workload**. Workload bao gồm thao tác đọc, ghi, tìm kiếm, tổng hợp, các tác vụ nền và những đợt xử lý theo lô. Nó ảnh hưởng trực tiếp đến cách tổ chức dữ liệu, khóa, chỉ mục, ranh giới giao dịch, chiến lược lưu trữ và cách mở rộng hệ thống.

Ví dụ, một hệ thống bán hàng có thể lưu khách hàng, sản phẩm, đơn hàng và tồn kho. Nhưng chỉ biết các thực thể này chưa đủ để thiết kế. Cần biết hệ thống thường tra cứu đơn hàng theo mã hay theo khách hàng, tìm sản phẩm theo tên hay nhiều bộ lọc, cập nhật tồn kho đồng thời ra sao và báo cáo doanh thu được tính theo thời gian thực hay theo lịch.

Mục tiêu của bước khảo sát là tạo được danh mục thao tác có thể kiểm chứng. Mỗi thao tác cần gắn với một mục đích nghiệp vụ, mẫu truy cập dữ liệu, tần suất, quy mô dữ liệu, yêu cầu độ trễ và yêu cầu nhất quán.

## 2. Phân biệt thao tác nghiệp vụ và thao tác cơ sở dữ liệu

Một hành động nghiệp vụ có thể tạo ra nhiều thao tác cơ sở dữ liệu. Chẳng hạn, nghiệp vụ tạo đơn hàng có thể gồm:

1. Đọc thông tin khách hàng và kiểm tra trạng thái tài khoản.
2. Đọc giá và trạng thái bán của từng sản phẩm.
3. Kiểm tra và giữ số lượng tồn kho.
4. Ghi đơn hàng và các dòng hàng.
5. Ghi lịch sử trạng thái hoặc sự kiện cần xử lý tiếp.

Vì vậy, không nên xem một lần gọi API hoặc một lần người dùng bấm nút là một thao tác dữ liệu duy nhất. Khi ước lượng tải, cần ghi nhận cả số lần thực hiện nghiệp vụ lẫn số thao tác đọc/ghi mà mỗi nghiệp vụ tạo ra. Cách nhìn này giúp tránh đánh giá thấp tải do một yêu cầu nghiệp vụ kích hoạt nhiều truy vấn hoặc nhiều lần cập nhật.

Cũng cần phân biệt thao tác đồng bộ với tác vụ nền. Gửi thông báo, đồng bộ dữ liệu sang hệ thống khác, tạo báo cáo định kỳ và dọn dữ liệu hết hạn có thể không xuất hiện trong luồng giao diện chính, nhưng vẫn tạo tải đáng kể lên hệ thống dữ liệu.

## 3. Phân loại các thao tác truy cập dữ liệu

### 3.1. Đọc dữ liệu

Thao tác đọc lấy dữ liệu đã lưu mà không làm thay đổi trạng thái nghiệp vụ. Cần phân loại theo cách xác định bản ghi và hình dạng kết quả.

| Mẫu đọc | Ví dụ nghiệp vụ | Đặc điểm cần ghi nhận |
|---|---|---|
| Tra cứu một bản ghi | Lấy đơn hàng theo mã đơn | Khóa tra cứu, số bản ghi trả về, có cần tải dữ liệu liên quan không |
| Tra cứu theo khóa thay thế | Tìm khách hàng theo email hoặc số điện thoại | Tính duy nhất, khả năng thay đổi của giá trị tra cứu |
| Liệt kê theo điều kiện | Xem đơn hàng của một khách hàng | Bộ lọc, phạm vi thời gian, số kết quả |
| Đọc theo khoảng | Lấy giao dịch trong một khoảng ngày | Biên khoảng, thứ tự sắp xếp, kích thước trang |
| Đọc quan hệ | Lấy các dòng hàng của một đơn | Số quan hệ cần duyệt, số lượng bản ghi con |
| Đọc chi tiết tổng hợp | Xem trang chi tiết đơn hàng kèm khách hàng và sản phẩm | Số nguồn dữ liệu, cách ghép dữ liệu, mức nhất quán cần có |

Với mỗi thao tác đọc, hãy xác định các điều kiện lọc, trường sắp xếp, phân trang và dữ liệu liên quan cần trả về. Hai truy vấn cùng đọc bảng đơn hàng có thể có đặc tính rất khác nhau: tra cứu theo mã đơn thường tìm một bản ghi, trong khi liệt kê đơn hàng theo khách hàng và thời gian có thể quét một tập dữ liệu lớn.

Ví dụ, danh sách đơn hàng gần đây của một khách hàng có thể dùng truy vấn:

```sql
SELECT id, status, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC
LIMIT :page_size;
```

Mẫu truy cập ở đây gồm điều kiện bằng trên `customer_id`, điều kiện khoảng trên `created_at`, sắp xếp giảm dần theo thời gian và giới hạn số kết quả. Đây là thông tin hữu ích khi đánh giá khóa và chỉ mục sau này.

### 3.2. Ghi dữ liệu

Ghi dữ liệu làm thay đổi trạng thái hoặc bổ sung thông tin mới. Những dạng phổ biến gồm:

- **Insert:** tạo khách hàng, đơn hàng, dòng hàng hoặc bản ghi lịch sử.
- **Update:** đổi địa chỉ, trạng thái đơn, giá hoặc số lượng tồn kho.
- **Delete:** xóa dữ liệu theo yêu cầu nghiệp vụ hoặc chính sách lưu giữ.
- **Upsert:** tạo mới nếu chưa tồn tại hoặc cập nhật nếu đã tồn tại.
- **Batch write:** nhập dữ liệu, đồng bộ nhiều bản ghi hoặc xử lý một lô giao dịch.
- **Append-only:** ghi sự kiện, nhật ký hoặc lịch sử thay đổi mà không sửa bản ghi cũ.

Không chỉ đếm số lần ghi, cần xác định mỗi lần ghi tác động lên bao nhiêu bản ghi và có bao nhiêu thực thể phải thay đổi cùng nhau. Một giao dịch tạo đơn hàng có thể phải ghi đơn, dòng hàng và thao tác giữ tồn kho trong cùng một ranh giới nhất quán.

Các câu hỏi quan trọng gồm:

- Bản ghi có được tạo một lần hay cập nhật liên tục?
- Một lần ghi thay đổi một hàng hay nhiều hàng?
- Những thay đổi nào phải thành công hoặc thất bại cùng nhau?
- Có nhiều người dùng hoặc tiến trình cập nhật cùng một dữ liệu không?
- Có cần chống ghi trùng khi yêu cầu được gửi lại không?
- Dữ liệu bị xóa vật lý, đánh dấu đã xóa hay chuyển sang vùng lưu trữ khác?

Các câu trả lời này giúp nhận diện nhu cầu giao dịch, kiểm soát tranh chấp ghi, tính idempotent và chính sách lưu lịch sử.

### 3.3. Tìm kiếm dữ liệu

Tìm kiếm thường kết hợp nhiều điều kiện và có thể yêu cầu sắp xếp theo mức độ phù hợp. Cần phân biệt rõ tìm kiếm với tra cứu một bản ghi hoặc lọc danh sách thông thường.

| Kiểu tìm kiếm | Ví dụ | Đặc điểm cần khảo sát |
|---|---|---|
| Chính xác | Tìm sản phẩm theo SKU | Giá trị có duy nhất không, có chuẩn hóa chữ hoa/thường không |
| Tiền tố | Tìm tên bắt đầu bằng một chuỗi | Có cần gợi ý khi người dùng đang nhập không |
| Toàn văn | Tìm sản phẩm theo mô tả | Ngôn ngữ, tách từ, dấu tiếng Việt, độ liên quan |
| Nhiều bộ lọc | Lọc sản phẩm theo danh mục, giá và trạng thái | Số lượng bộ lọc, tổ hợp thường dùng, độ chọn lọc |
| Tìm kiếm có sắp xếp | Tìm sản phẩm rồi sắp xếp theo giá hoặc độ phổ biến | Trường sắp xếp, phân trang, thứ tự ổn định |
| Tìm kiếm theo phạm vi | Tìm địa điểm trong bán kính hoặc vùng | Dữ liệu không gian, đơn vị đo, độ chính xác |

Cần ghi lại người dùng thường tìm theo trường nào, có kết hợp nhiều bộ lọc hay không, kết quả cần xếp hạng thế nào và dữ liệu mới phải xuất hiện trong kết quả sau bao lâu. Nếu tìm kiếm toàn văn có yêu cầu riêng về độ liên quan hoặc gợi ý, nó có thể cần cách tổ chức dữ liệu và cơ chế lập chỉ mục khác với truy vấn quan hệ thông thường.

### 3.4. Tổng hợp dữ liệu

Tổng hợp biến nhiều bản ghi thành số liệu hoặc nhóm kết quả. Các phép tổng hợp phổ biến gồm đếm, tính tổng, trung bình, giá trị nhỏ nhất/lớn nhất, nhóm theo thuộc tính và tính theo cửa sổ thời gian.

Ví dụ, báo cáo doanh thu theo ngày có thể được tính từ các đơn đã thanh toán:

```sql
SELECT DATE_TRUNC('day', created_at) AS day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= :from_time
  AND created_at < :to_time
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY day;
```

Khi khảo sát một truy vấn tổng hợp, cần xác định:

- Phạm vi dữ liệu phải đọc: toàn bộ lịch sử, một khoảng thời gian hay một nhóm đối tượng.
- Chiều nhóm: ngày, tháng, cửa hàng, khách hàng, sản phẩm hoặc trạng thái.
- Tần suất làm mới: theo từng yêu cầu, mỗi vài phút, mỗi giờ hay mỗi ngày.
- Mức dữ liệu mới được chấp nhận: số liệu phải cập nhật ngay hay có thể trễ một khoảng thời gian.
- Kiểu sử dụng: dashboard tương tác, báo cáo định kỳ, xuất tệp hay phân tích tùy ý.

Truy vấn tổng hợp trên tập dữ liệu lớn có thể cạnh tranh tài nguyên với giao dịch trực tuyến. Yêu cầu về độ mới của số liệu giúp xác định có thể tổng hợp trực tiếp khi đọc, tính trước kết quả hay chuyển một phần xử lý sang luồng phân tích riêng.

## 4. Lập danh mục workload

Sau khi phân loại, ghi từng thao tác thành một dòng trong danh mục. Mỗi dòng nên mô tả một mẫu truy cập đủ cụ thể để có thể ước lượng và kiểm chứng.

| Trường thông tin | Nội dung cần ghi |
|---|---|
| Mã thao tác | Mã ngắn để trao đổi và truy vết, ví dụ R-01 hoặc W-02 |
| Tác nhân và mục đích | Ai thực hiện, nhằm hoàn thành nghiệp vụ nào |
| Loại thao tác | Đọc, ghi, tìm kiếm, tổng hợp hoặc tác vụ nền |
| Mẫu truy cập | Khóa tra cứu, bộ lọc, quan hệ cần đọc, trường sắp xếp |
| Quy mô kết quả | Một bản ghi, một trang, hàng nghìn bản ghi hay toàn bộ tập dữ liệu |
| Tần suất | Lần/giây, lần/phút, lần/giờ, lần/ngày hoặc số lô trong một kỳ |
| Tải cao điểm | Tần suất trong khung giờ hoặc sự kiện bận nhất |
| Độ trễ mục tiêu | Thời gian phản hồi mong muốn, có thể mô tả bằng p95 hoặc p99 |
| Nhất quán và độ mới | Có cần đọc thấy ngay dữ liệu vừa ghi không; dữ liệu tổng hợp được phép trễ bao lâu |
| Mức quan trọng | Hậu quả khi thao tác chậm, thất bại hoặc trả dữ liệu cũ |

Ví dụ minh họa dưới đây dùng một hệ thống bán hàng giả định. Các con số chỉ giúp minh họa cách ghi nhận, không phải số liệu mặc định cho mọi hệ thống.

| Mã | Nghiệp vụ và loại thao tác | Tần suất trung bình | Cao điểm | Yêu cầu chính |
|---|---|---:|---:|---|
| R-01 | Tra cứu đơn theo mã, đọc | 30 lần/giây | 120 lần/giây | Trả một đơn và trạng thái mới nhất |
| R-02 | Liệt kê đơn theo khách hàng, đọc | 8 lần/giây | 32 lần/giây | Sắp xếp theo thời gian, phân trang |
| S-01 | Tìm sản phẩm theo từ khóa và bộ lọc | 5 lần/giây | 25 lần/giây | Kết quả phù hợp, phản hồi nhanh |
| W-01 | Tạo đơn và giữ tồn kho, ghi giao dịch | 3 giao dịch/giây | 15 giao dịch/giây | Các thay đổi liên quan phải nhất quán |
| W-02 | Cập nhật trạng thái giao hàng, ghi | 2 lần/giây | 10 lần/giây | Kiểm soát chuyển trạng thái hợp lệ |
| A-01 | Tính doanh thu theo ngày, tổng hợp | 1 lần/5 phút | Tăng khi mở báo cáo | Số liệu được phép trễ tối đa theo yêu cầu |

Danh mục cần đủ chi tiết để nhóm thiết kế có thể hình dung cách truy cập dữ liệu mà không phải suy đoán từ tên chức năng. Nếu một chức năng có nhiều đường truy cập đáng kể, hãy tách thành nhiều dòng. Chẳng hạn, màn hình đơn hàng có thể có một truy vấn đếm tổng số đơn và một truy vấn lấy trang đơn; hai truy vấn này có thể có chi phí và cách tối ưu khác nhau.

## 5. Định lượng tần suất và tải

### 5.1. Dùng đơn vị phù hợp

Chọn đơn vị thể hiện đúng bản chất của thao tác:

- **QPS (queries per second):** số truy vấn mỗi giây, phù hợp với thao tác đọc hoặc tìm kiếm.
- **TPS (transactions per second):** số giao dịch mỗi giây, phù hợp khi một nghiệp vụ gồm nhiều thao tác dữ liệu cần hoàn tất cùng nhau.
- **Lần/phút, lần/giờ hoặc lần/ngày:** phù hợp với tác vụ định kỳ hoặc thao tác có tần suất thấp.
- **Số bản ghi/lô:** phù hợp với nhập dữ liệu, đồng bộ và xử lý theo batch.

Không nên cộng trực tiếp các đơn vị khác nhau. Hãy quy đổi về cùng khoảng thời gian khi cần so sánh tổng tải, đồng thời vẫn giữ thông tin về kích thước lô và số thao tác bên trong mỗi giao dịch.

### 5.2. Phân biệt trung bình và cao điểm

Tần suất trung bình cho biết mức sử dụng thường ngày, nhưng không mô tả được khả năng chịu tải khi có nhiều người dùng cùng hoạt động. Cần khảo sát ít nhất:

- Trung bình trong ngày hoặc trong một kỳ đại diện.
- Cao điểm theo giờ, ngày trong tuần, mùa vụ hoặc chiến dịch.
- Đỉnh ngắn hạn khi có sự kiện, thông báo hoặc nhập dữ liệu hàng loạt.
- Mức tăng trưởng dự kiến của người dùng, dữ liệu và số thao tác.

Nếu một truy vấn có trung bình 30 lần/giây và cao điểm 120 lần/giây thì hệ số cao điểm là:

```text
Hệ số cao điểm = Tần suất cao điểm / Tần suất trung bình
               = 120 / 30
               = 4
```

Hệ số này giúp nhận diện khoảng cách giữa tải bình thường và tải cần chuẩn bị. Khi có log thực tế, nên đo theo các cửa sổ thời gian ngắn phù hợp với đặc tính hệ thống; một giá trị trung bình theo ngày có thể che khuất các đợt tăng tải kéo dài vài phút.

### 5.3. Ước lượng từ số người dùng và hành vi

Khi chưa có hệ thống để đo, có thể lập ước lượng ban đầu từ hành vi:

```text
Số thao tác trong kỳ
  = Số người dùng hoạt động
  × Số lần thực hiện nghiệp vụ trên mỗi người
  × Số thao tác dữ liệu cho mỗi nghiệp vụ

Tần suất trung bình
  = Số thao tác trong kỳ / Số giây của kỳ
```

Ví dụ, nếu có 2.000 người dùng hoạt động trong một giờ, mỗi người trung bình mở danh sách đơn 6 lần và mỗi lần mở tạo ra 2 truy vấn dữ liệu, tổng số truy vấn ước tính là:

```text
2.000 × 6 × 2 = 24.000 truy vấn/giờ
24.000 / 3.600 ≈ 6,67 truy vấn/giây
```

Đây chỉ là ước lượng. Kết quả thực tế có thể khác do cache, tải trước dữ liệu, retry, phân trang, thao tác nền và khác biệt hành vi giữa các nhóm người dùng. Cần ghi rõ giả định nào đã được dùng để có thể điều chỉnh khi có dữ liệu đo.

### 5.4. Đo độ trễ và mức đồng thời

Tần suất cần đi cùng độ trễ. Một truy vấn 10 lần/giây nhưng mỗi lần đọc hàng triệu bản ghi có thể gây áp lực lớn hơn một truy vấn 100 lần/giây trả về một bản ghi nhỏ.

Không nên chỉ dùng thời gian trung bình. Các phân vị như **p95** và **p99** cho biết thời gian mà 95% hoặc 99% yêu cầu hoàn tất trong giới hạn đó, giúp phát hiện nhóm yêu cầu chậm ở đuôi phân phối.

Có thể ước lượng số yêu cầu đang xử lý đồng thời bằng định luật Little:

```text
Số yêu cầu đang xử lý ≈ Tốc độ yêu cầu × Thời gian xử lý trung bình
```

Ví dụ, với 120 yêu cầu/giây và thời gian xử lý trung bình 0,2 giây, số yêu cầu đang xử lý tại một thời điểm vào khoảng 24. Đây là ước lượng cho luồng yêu cầu; số kết nối và mức đồng thời ở cơ sở dữ liệu còn phụ thuộc connection pool, cache, hàng đợi và cách ứng dụng thực thi truy vấn.

### 5.5. Ghi nhận quy mô và tính chọn lọc

Ngoài tần suất, mỗi mẫu truy cập cần có thông tin về lượng dữ liệu:

- Tổng số bản ghi hiện tại và số bản ghi dự kiến tăng thêm theo ngày, tháng hoặc năm.
- Số bản ghi được đọc, trả về hoặc cập nhật trong một lần thao tác.
- Tỷ lệ bản ghi thỏa điều kiện lọc so với tập dữ liệu được xét.
- Kích thước trung bình của bản ghi và kết quả trả về.
- Thời gian lưu giữ, tốc độ thay đổi và nhu cầu truy vấn dữ liệu cũ.

Một bộ lọc trả về 5 bản ghi từ 10 triệu bản ghi có đặc tính khác với bộ lọc trả về 500 nghìn bản ghi. Tính chọn lọc của điều kiện và kích thước kết quả giúp đánh giá hiệu quả truy vấn và nhu cầu chỉ mục ở bước thiết kế tiếp theo.

## 6. Thu thập dữ liệu khảo sát

Khi hệ thống đã vận hành, ưu tiên số liệu quan sát được từ log ứng dụng, thống kê truy vấn, công cụ giám sát cơ sở dữ liệu và distributed tracing. Nên thu thập cả tên thao tác nghiệp vụ, mẫu truy vấn, thời gian thực hiện, số lần gọi, số bản ghi đọc/ghi và lỗi hoặc retry.

Khi hệ thống chưa có dữ liệu thực tế, có thể kết hợp:

1. **Phỏng vấn người dùng và chủ nghiệp vụ:** xác định thao tác thường dùng, thời điểm cao điểm, báo cáo quan trọng và hậu quả khi dữ liệu chậm.
2. **Đi qua từng quy trình:** theo dõi từ lúc bắt đầu nghiệp vụ đến khi hoàn tất, ghi lại mọi lần đọc và ghi dữ liệu.
3. **Xem mẫu đầu vào và đầu ra:** kiểm tra bộ lọc, trường sắp xếp, phân trang và kích thước kết quả mà chức năng thực sự cần.
4. **Ước lượng theo nhóm người dùng:** phân biệt người dùng thường, quản trị viên, nhân viên vận hành và tiến trình tự động.
5. **Đối chiếu với dữ liệu đo:** khi có bản chạy thử hoặc hệ thống thật, so sánh ước lượng với số liệu để cập nhật giả định.

Trong tài liệu khảo sát, nên đánh dấu nguồn của từng con số là **đã đo**, **ước lượng** hay **mục tiêu yêu cầu**. Không nên trình bày một con số phỏng đoán như dữ liệu thực tế. Với ước lượng, ghi rõ giả định và khoảng bất định nếu có.

## 7. Dùng workload để định hướng mô hình dữ liệu

Danh mục workload là đầu vào cho các quyết định mô hình hóa, nhưng không tự động quyết định một loại cơ sở dữ liệu hoặc một cấu trúc duy nhất.

- Nếu hệ thống thường xuyên đọc theo một khóa ổn định, cần xác định khóa tra cứu và tính duy nhất của nó.
- Nếu hệ thống thường liệt kê theo một thực thể kèm điều kiện thời gian, cần mô tả thứ tự, phạm vi và cách phân trang.
- Nếu nhiều thao tác ghi phải bảo toàn cùng một quy tắc nghiệp vụ, cần xác định các thực thể và thay đổi thuộc cùng giao dịch.
- Nếu tìm kiếm kết hợp toàn văn, nhiều bộ lọc và xếp hạng, cần đánh giá riêng yêu cầu tìm kiếm và độ mới của chỉ mục.
- Nếu báo cáo quét lượng dữ liệu lớn, cần xác định độ mới chấp nhận được để lựa chọn cách tính trực tiếp, tính trước hoặc xử lý phân tích.
- Nếu một số thao tác đọc rất phổ biến nhưng cần dữ liệu từ nhiều quan hệ, cần cân nhắc chi phí ghép dữ liệu và khả năng duy trì dữ liệu dẫn xuất.

Ví dụ, màn hình chi tiết đơn hàng có thể cần dữ liệu từ đơn hàng, khách hàng và dòng hàng. Trong khi đó, báo cáo doanh thu cần quét nhiều đơn hàng theo khoảng thời gian và nhóm kết quả. Cả hai cùng sử dụng dữ liệu đơn hàng nhưng có mục đích và đặc tính tải khác nhau. Thiết kế tốt phải xem xét đồng thời workload, quy tắc nhất quán, khả năng tiến hóa và chi phí duy trì dữ liệu.

## 8. Những sai sót thường gặp

- Chỉ liệt kê CRUD mà không mô tả điều kiện lọc, sắp xếp, phân trang và quan hệ cần đọc.
- Đếm số lần người dùng thao tác nhưng bỏ qua nhiều truy vấn được tạo ra trong một nghiệp vụ.
- Chỉ ước lượng tải trung bình, bỏ qua cao điểm, mùa vụ và tác vụ batch.
- Bỏ quên tác vụ nền, retry, đồng bộ, báo cáo và quy trình quản trị.
- Gộp truy vấn giao dịch ngắn với truy vấn phân tích dài vào cùng một nhóm.
- Chỉ ghi tần suất mà không ghi kích thước dữ liệu, số bản ghi trả về và độ trễ mục tiêu.
- Dùng con số ước lượng nhưng không ghi nguồn hoặc giả định.
- Tối ưu mô hình cho một truy vấn hiếm gặp mà làm tăng đáng kể chi phí của các thao tác thường xuyên.

## 9. Checklist hoàn tất khảo sát

Trước khi chuyển sang bước thiết kế chi tiết, hãy xác nhận:

- [ ] Các thao tác đọc, ghi, tìm kiếm và tổng hợp chính đã được liệt kê.
- [ ] Mỗi thao tác có mục đích nghiệp vụ, tác nhân và mẫu truy cập cụ thể.
- [ ] Đã mô tả khóa tra cứu, bộ lọc, sắp xếp, phân trang và quan hệ cần đọc.
- [ ] Đã phân biệt số lần nghiệp vụ với số thao tác dữ liệu phát sinh.
- [ ] Có tần suất trung bình, cao điểm và chu kỳ chạy cho tác vụ định kỳ.
- [ ] Có ước lượng quy mô dữ liệu, kích thước kết quả và tốc độ tăng trưởng.
- [ ] Có mục tiêu độ trễ, mức đồng thời và yêu cầu nhất quán hoặc độ mới.
- [ ] Các số liệu đã được phân biệt rõ giữa đo thực tế, ước lượng và mục tiêu.
- [ ] Những giả định chưa chắc chắn đã được ghi lại để xác minh.

Một danh mục workload rõ ràng giúp nhóm thiết kế chuyển nhu cầu nghiệp vụ thành các mẫu truy cập dữ liệu cụ thể. Từ đó, việc lựa chọn khóa, quan hệ, chỉ mục, ranh giới giao dịch và cấu trúc lưu trữ có căn cứ hơn, đồng thời có tiêu chí để kiểm chứng khi hệ thống phát triển.

