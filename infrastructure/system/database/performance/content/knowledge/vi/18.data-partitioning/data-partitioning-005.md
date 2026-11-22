# Chi phí lập kế hoạch và quản lý khi có quá nhiều phân vùng

Phân vùng dữ liệu (partitioning) chia một bảng logic lớn thành nhiều phần vật lý nhỏ hơn theo một khóa như thời gian, khách hàng hoặc khu vực. Khi truy vấn có điều kiện phù hợp với khóa phân vùng, hệ quản trị có thể loại bỏ các phân vùng không liên quan (partition pruning), giảm lượng dữ liệu phải đọc và giúp quản lý vòng đời dữ liệu thuận tiện hơn. Tuy nhiên, mỗi phân vùng cũng là một đối tượng cần được lập kế hoạch, quản lý metadata, thống kê, chỉ mục và bảo trì. Nếu chia quá nhỏ, số lượng phân vùng tăng cao có thể làm thời gian lập kế hoạch, bộ nhớ, chi phí DDL và công việc vận hành tăng lên.

Bài học thuộc chương **Phân vùng dữ liệu** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, thiết kế phân vùng cần cân bằng lợi ích pruning và quản lý dữ liệu với chi phí lập kế hoạch, thực thi, bảo trì và vận hành trên toàn workload.

## 1. Phân vùng giải quyết vấn đề gì?

Phân vùng cho phép chia một bảng lớn thành nhiều phần theo quy tắc xác định. Ứng dụng vẫn truy vấn bảng logic như một bảng, còn hệ quản trị chọn các phân vùng liên quan khi có thể chứng minh điều kiện truy vấn chỉ cần một phần dữ liệu.

Các mục tiêu phổ biến:

- **Partition pruning:** bỏ qua phân vùng không thể chứa hàng thỏa điều kiện.
- **Quản lý vòng đời:** xóa hoặc lưu trữ dữ liệu cũ bằng cách detach/drop partition thay vì xóa hàng triệu hàng riêng lẻ, nếu hệ quản trị hỗ trợ thao tác phù hợp.
- **Tách phạm vi bảo trì:** chạy index rebuild, vacuum, analyze, backup hoặc tác vụ dữ liệu trên từng phần.
- **Phân phối dữ liệu:** tổ chức dữ liệu theo thời gian, tenant, khu vực hoặc dải khóa để hỗ trợ kiến trúc lưu trữ và truy cập.
- **Tăng khả năng song song:** một số hệ quản trị có thể xử lý các phân vùng độc lập song song trong các kế hoạch phù hợp.

Phân vùng không tự động làm truy vấn nhanh hơn. Nếu truy vấn không lọc theo khóa phân vùng, hệ quản trị có thể phải truy cập nhiều hoặc tất cả phân vùng. Khi đó, truy vấn phải trả thêm chi phí quản lý nhiều đối tượng mà không nhận được lợi ích pruning tương ứng.

## 2. Vì sao quá nhiều phân vùng làm tăng chi phí?

Mỗi phân vùng thường có metadata, constraint, thống kê, chỉ mục và trạng thái quản lý riêng. Khi số phân vùng tăng, hệ quản trị và nhóm vận hành phải xử lý nhiều đối tượng hơn.

Các loại chi phí chính gồm:

1. **Lập kế hoạch truy vấn:** bộ tối ưu phải xem xét cấu trúc phân vùng, xác định phân vùng có thể liên quan và xây dựng kế hoạch cho các phần còn lại.
2. **Metadata và bộ nhớ:** cache metadata, relation descriptors, thông tin constraint, index và thống kê cần không gian bộ nhớ và công việc quản lý.
3. **Khởi tạo thực thi:** executor có thể cần mở, khởi tạo hoặc quản lý nhiều đối tượng phân vùng, dù một số phân vùng sau đó bị loại bỏ ở runtime.
4. **Khóa và đồng thời:** truy vấn hoặc thao tác DDL có thể tương tác với nhiều đối tượng quan hệ hơn, làm tăng phạm vi quản lý khóa hoặc tranh chấp metadata tùy hệ quản trị.
5. **Thống kê và tối ưu:** thu thập, lưu trữ và sử dụng thống kê cho nhiều phân vùng làm tăng công việc quản trị; thống kê từng phân vùng quá nhỏ cũng có thể kém đại diện.
6. **Bảo trì chỉ mục:** mỗi phân vùng có thể có index riêng hoặc index được quản lý qua bảng cha, khiến số đối tượng index tăng theo.
7. **Vận hành và triển khai:** tạo, attach, detach, archive, backup, restore, kiểm tra quyền và giám sát trở nên phức tạp hơn.

Chi phí không tăng theo một công thức chung cho mọi hệ quản trị. Số phân vùng, số phân vùng được truy cập, loại partition key, kế hoạch generic/custom, cấu trúc index, phiên bản và đặc điểm workload đều có ảnh hưởng.

## 3. Phân biệt số phân vùng tồn tại và số phân vùng được truy cập

Hai con số này có ý nghĩa khác nhau:

- **Tổng số phân vùng:** tất cả các phân vùng được định nghĩa cho bảng.
- **Số phân vùng ứng viên:** các phân vùng mà bộ tối ưu phải xem xét dựa trên thông tin có sẵn khi lập kế hoạch.
- **Số phân vùng được giữ lại:** các phân vùng không bị pruning sau khi áp dụng điều kiện ở giai đoạn lập kế hoạch hoặc khởi tạo thực thi.
- **Số phân vùng thực sự được đọc:** các phân vùng có toán tử thực thi và đọc dữ liệu trong lần chạy cụ thể.

Một bảng có hàng nghìn phân vùng nhưng truy vấn chỉ chạm một vài phân vùng vẫn có thể có chi phí lập kế hoạch đáng kể nếu hệ quản trị phải xem xét nhiều metadata. Ngược lại, một bảng có ít phân vùng nhưng truy vấn đọc tất cả các phần có thể tốn nhiều I/O và CPU dù chi phí lập kế hoạch thấp.

Vì vậy, không chỉ đếm phân vùng. Hãy đo riêng thời gian lập kế hoạch, thời gian thực thi, số phân vùng bị loại, số phân vùng được truy cập và lượng dữ liệu thực tế đọc.

## 4. Partition pruning và các giai đoạn thực hiện

Partition pruning là quá trình loại bỏ phân vùng không thể chứa kết quả theo điều kiện truy vấn. Tùy hệ quản trị, việc pruning có thể xảy ra ở nhiều thời điểm.

### 4.1. Pruning tại thời điểm lập kế hoạch

Khi giá trị khóa phân vùng đã biết lúc tối ưu, bộ tối ưu có thể xác định phân vùng liên quan trước khi thực thi. Ví dụ bảng partition theo tháng và truy vấn lọc một khoảng thời gian chỉ nằm trong tháng 10 có thể loại các partition tháng khác.

```sql
SELECT event_id, created_at
FROM events
WHERE created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-01 00:00:00';
```

Điều kiện nửa mở `[đầu tháng, đầu tháng kế tiếp)` giúp xác định ranh giới rõ ràng. Nếu khóa phân vùng là `created_at`, hệ quản trị có thể xác định các partition tháng cần xem xét.

### 4.2. Pruning tại thời điểm thực thi

Với truy vấn tham số hóa hoặc prepared statement, giá trị thực tế có thể chỉ được biết khi câu lệnh chạy. Một số hệ quản trị có thể trì hoãn pruning đến lúc khởi tạo executor hoặc trong quá trình thực thi.

Ví dụ:

```sql
SELECT event_id, created_at
FROM events
WHERE created_at >= :from_time
  AND created_at < :to_time;
```

Nếu kế hoạch được lập trước khi biết `:from_time` và `:to_time`, bộ tối ưu có thể giữ một kế hoạch tổng quát. Hệ quản trị hỗ trợ runtime pruning có thể vẫn loại các phân vùng không cần sau khi nhận tham số. Khả năng này và cách hiển thị trong execution plan khác nhau theo sản phẩm và phiên bản.

### 4.3. Pruning trong quá trình thực thi

Một số kế hoạch có điều kiện phụ thuộc giá trị được tạo ra từ toán tử bên ngoài, ví dụ nested loop với khóa phân vùng lấy từ hàng đầu vào. Hệ quản trị có thể thay đổi tập phân vùng cần truy cập theo từng giá trị. Cách này có thể hữu ích nhưng cũng làm số lần khởi tạo hoặc kiểm tra partition tăng nếu đầu vào chứa rất nhiều giá trị khác nhau.

### 4.4. Điều kiện làm pruning kém hiệu quả

Các yếu tố thường làm giảm khả năng pruning:

- Không có predicate trên khóa phân vùng.
- Điều kiện không thể được bộ tối ưu chứng minh tương thích với partition bounds.
- Áp hàm hoặc ép kiểu không phù hợp lên cột phân vùng.
- Dùng biểu thức hoặc phép chuyển đổi khiến hệ quản trị khó suy ra khoảng giá trị.
- Truy vấn yêu cầu phạm vi rộng, thực sự bao phủ nhiều phân vùng.
- Kế hoạch generic hoặc cơ chế tham số hóa không tận dụng được thông tin cần thiết ở giai đoạn lập kế hoạch, tùy sản phẩm.

Hãy kiểm tra execution plan để xác nhận pruning thật sự diễn ra. Việc bảng đã được partition không có nghĩa mọi truy vấn đều tự động hưởng lợi.

## 5. Chi phí lập kế hoạch và chi phí thực thi

Thời gian phản hồi truy vấn có thể gồm nhiều thành phần: parse/compile, lập kế hoạch, khởi tạo executor, đọc dữ liệu, xử lý toán tử, chờ khóa/I/O và truyền kết quả. Trong một số ứng dụng, thời gian lập kế hoạch chỉ là phần nhỏ; với truy vấn ngắn được gọi hàng nghìn lần mỗi giây trên bảng có rất nhiều phân vùng, chi phí lập kế hoạch có thể chiếm tỷ lệ đáng kể.

Phân biệt:

- **Planning time:** thời gian bộ tối ưu tạo kế hoạch.
- **Execution time:** thời gian thực thi kế hoạch theo cách đo của hệ quản trị.
- **Application latency:** thời gian ứng dụng quan sát, có thể gồm lấy kết nối, hàng đợi, mạng, chuyển đổi dữ liệu và các bước ngoài DB.

Nếu planning time tăng nhưng execution time gần như không đổi, tối ưu scan hoặc tăng I/O chưa chắc giải quyết đúng vấn đề. Cần xem số lượng partition metadata mà planner phải xử lý, khả năng pruning và tần suất truy vấn. Nếu execution time cao do truy cập nhiều partition, cần xem lại predicate, partition key, index và phạm vi dữ liệu.

### 5.1. Chi phí lặp lại của truy vấn ngắn

Một truy vấn chỉ đọc một hàng có thể có execution time rất nhỏ. Nhưng nếu câu lệnh được lập kế hoạch lại liên tục, tổng chi phí planning trên toàn hệ thống có thể đáng kể.

Ví dụ giả định:

- Planning time trung bình: 4 ms.
- Execution time trung bình: 1 ms.
- Tần suất: 500 lần/giây.

Nếu mỗi lần đều lập kế hoạch mới, chi phí CPU lập kế hoạch tích lũy có thể lớn hơn công việc thực thi. Đây là ví dụ minh họa, không phải dự báo chính xác về CPU hoặc throughput; cần đo thực tế và xác định hệ quản trị có tái sử dụng prepared plan hay không.

### 5.2. Prepared statement và generic plan

Prepared statement có thể giảm chi phí parse/plan bằng cách tái sử dụng kế hoạch. Tuy nhiên, kế hoạch tổng quát không luôn tối ưu cho mọi tham số. Với phân vùng, tham số hóa có thể ảnh hưởng việc pruning ở thời điểm lập kế hoạch; runtime pruning có thể bù lại trong các hệ quản trị hỗ trợ.

Khi đánh giá, hãy thử:

- Giá trị tham số thuộc một partition.
- Khoảng tham số đi qua ranh giới hai hoặc nhiều partition.
- Tham số có giá trị phổ biến và hiếm.
- Prepared statement được tái sử dụng và truy vấn chạy trực tiếp với literal.
- Kế hoạch custom và generic nếu hệ quản trị cung cấp khả năng quan sát hoặc điều khiển.

Không tắt plan cache hoặc ép tái biên dịch chỉ để cải thiện pruning mà chưa đo chi phí compile và tác động lên workload.

## 6. Quá nhiều phân vùng làm tăng chi phí quản lý

Ngoài planner, mỗi partition tạo ra công việc quản trị cụ thể.

### 6.1. Metadata và catalog

Mỗi partition có thể cần thông tin về schema, constraint, index, quyền, storage, thống kê và quan hệ với bảng cha. Khi số lượng tăng, thao tác đọc metadata, cache object và quản lý catalog có thể nặng hơn. Một số công cụ quản trị cũng cần liệt kê và kiểm tra tất cả partition, khiến thao tác tưởng như đơn giản trở nên chậm.

### 6.2. Chỉ mục trên từng partition

Với nhiều hệ quản trị, chỉ mục trên bảng partitioned được triển khai thành các index tương ứng ở partition con hoặc có cơ chế local/global index riêng. Khi số partition tăng, số đối tượng index và thao tác quản lý index cũng tăng.

Các hệ quản trị không giống nhau:

- PostgreSQL hỗ trợ partitioned index trên bảng cha, với index con tương ứng trên các partition.
- Oracle phân biệt local và global indexes; thao tác partition maintenance có thể tác động đến tính hợp lệ của global index tùy thao tác và tùy chọn.
- SQL Server hỗ trợ partitioned tables/indexes và partition alignment; cấu hình index ảnh hưởng khả năng chuyển đổi partition hiệu quả.
- MySQL partitioning có các quy tắc và giới hạn riêng theo storage engine, loại khóa và index.

Không áp dụng quy tắc quản lý index của một hệ quản trị cho hệ khác. Cần kiểm tra cách index được tạo, cập nhật, rebuild, attach/detach và phục hồi trên phiên bản đang dùng.

### 6.3. Thống kê và phân tích dữ liệu

Bộ tối ưu cần thống kê để ước lượng số hàng. Khi partition quá nhỏ, mỗi phần có ít hàng và histogram có thể không đủ đại diện cho phân bố dữ liệu. Khi dữ liệu lệch mạnh giữa các partition, thống kê tổng hợp và thống kê từng partition có thể kể những câu chuyện khác nhau.

Ví dụ partition theo tháng: tháng hiện tại có nhiều bản ghi `status = 'PENDING'`, trong khi các tháng cũ gần như không còn. Một truy vấn chỉ đọc tháng hiện tại có thể cần thống kê phản ánh phân bố cục bộ. Nếu hệ quản trị chỉ dựa trên thống kê tổng thể hoặc thống kê đã cũ, cardinality estimate có thể sai.

Hãy theo dõi thời điểm analyze, số mẫu, độ mới thống kê, phân bố theo partition và sai lệch giữa estimated rows với actual rows. Việc cập nhật thống kê cho hàng trăm hoặc hàng nghìn partition cũng là một công việc vận hành cần tính đến.

### 6.4. Vacuum, cleanup và tác vụ nền

Ở hệ quản trị dùng MVCC, từng partition có thể cần vacuum hoặc cleanup riêng. Nhiều partition hoạt động đồng thời có thể tạo nhiều tác vụ bảo trì và metadata để theo dõi. Một partition quá nhỏ nhưng có tần suất cập nhật cao vẫn cần bảo trì; partition quá cũ ít thay đổi có thể cần chính sách khác.

Hãy phân loại partition theo vòng đời: đang ghi, còn hoạt động, chỉ đọc, đã lưu trữ. Chính sách autovacuum, analyze, backup, compression và retention nên phản ánh trạng thái đó thay vì áp một cấu hình giống nhau cho tất cả nếu hệ quản trị cho phép.

### 6.5. DDL và vòng đời partition

Tạo partition, attach, detach, split, merge, drop hoặc archive có thể tác động metadata, lock và index. Nếu có quá nhiều partition, việc tạo lịch partition mới, kiểm tra partition thiếu, cập nhật quyền, đồng bộ constraint và theo dõi index trở thành một quy trình dài.

Đặc biệt, tạo partition quá nhỏ theo từng ngày/giờ hoặc từng tenant có thể khiến số lượng tăng nhanh hơn dự kiến. Cần ước tính số partition trong toàn bộ thời gian lưu giữ, không chỉ số partition đang hoạt động.

## 7. Chọn độ hạt phân vùng (partition granularity)

Độ hạt là kích thước logic của mỗi partition, ví dụ theo ngày, tuần, tháng, quý hoặc theo một khoảng ID. Độ hạt nhỏ giúp thao tác retention và pruning chi tiết hơn, nhưng làm số partition tăng. Độ hạt lớn giảm số đối tượng nhưng truy vấn có thể phải đọc phạm vi dữ liệu rộng hơn.

Ví dụ với dữ liệu giữ trong 5 năm:

| Độ hạt | Số partition thời gian xấp xỉ | Đặc điểm |
|---|---:|---|
| Theo ngày | 1.826 | Rất chi tiết; nhiều đối tượng và thao tác tạo/bảo trì |
| Theo tuần | 261 | Ít partition hơn; retention và truy vấn theo ngày có thể chạm nhiều phần hơn |
| Theo tháng | 60 | Dễ quản lý; truy vấn hẹp theo ngày vẫn có thể đọc partition tháng chứa ngày đó |
| Theo quý | 20 | Số lượng thấp; truy vấn theo tháng/ngày có thể quét phần lớn quý |

Con số chỉ mang tính ước lượng, không tính partition mặc định, partition tương lai, subpartition hoặc phần lưu trữ ngoài. Cần tính cả thời gian lưu giữ, số tenant, số vùng và chiến lược subpartition.

### 7.1. Chọn theo phân bố truy vấn

Nếu phần lớn truy vấn lấy dữ liệu một tháng, partition theo tháng có thể phù hợp. Nếu hệ thống thường xuyên xóa dữ liệu theo ngày và truy vấn ngày cụ thể với khối lượng rất lớn, partition theo ngày có thể đáng thử. Nếu dữ liệu ghi gần theo thứ tự thời gian và truy vấn đọc khoảng rộng, partition theo tháng hoặc tuần có thể cân bằng số đối tượng và pruning.

Không nên chọn partition granularity chỉ dựa vào kích thước bảng. Cần xem:

- Tỷ lệ truy vấn lọc theo khóa phân vùng.
- Độ rộng khoảng truy vấn phổ biến.
- Tần suất xóa/retention và yêu cầu lưu trữ.
- Số hàng và kích thước mỗi partition.
- Tỷ lệ ghi mới so với đọc dữ liệu cũ.
- Số partition được truy cập trung bình và ở p95/p99.
- Chi phí tạo, attach/detach và backup.

### 7.2. Tránh phân vùng theo từng giá trị có cardinality quá cao

Partition theo `customer_id` cho hàng triệu khách hàng có thể tạo số partition rất lớn nếu mỗi khách hàng là một partition. Thường nên dùng hash partitioning với số bucket giới hạn hoặc chiến lược khác phù hợp, nếu mục tiêu là phân phối dữ liệu. Nhưng hash partitioning có thể không hỗ trợ retention theo thời gian một cách đơn giản.

Subpartition theo nhiều chiều có thể làm số partition tăng theo tích số lượng của từng chiều. Ví dụ 60 tháng nhân với 32 hash buckets tạo 1.920 leaf partitions. Trước khi thiết kế nhiều tầng, hãy tính tổng số leaf partition và các đối tượng index tương ứng.

## 8. Ví dụ ước tính số partition và đối tượng liên quan

Giả sử bảng sự kiện giữ 3 năm, chia theo tháng, mỗi tháng có 8 hash subpartition theo tenant bucket.

Số partition lá xấp xỉ:

```text
36 tháng × 8 bucket = 288 leaf partitions
```

Nếu mỗi leaf partition có 4 index, có thể có khoảng:

```text
288 × 4 = 1.152 partition-level index objects
```

Đây chỉ là cách ước tính quy mô đối tượng; hệ quản trị có thể trình bày index cha/con và metadata khác nhau. Ngoài 288 partition hiện tại, còn có thể cần partition tương lai, default partition, staging hoặc partition dành cho dữ liệu đến muộn.

Nếu đổi từ 8 sang 64 bucket, số leaf partitions tăng lên 2.304 và số index con theo giả định trên tăng lên 9.216. Việc chia nhỏ có thể phân phối dữ liệu tốt hơn nhưng làm tăng mạnh số đối tượng quản lý. Cần chứng minh lợi ích về song song, contention hoặc phân phối lưu trữ đủ lớn để bù chi phí đó.

## 9. Chọn partition key và predicate để pruning hiệu quả

Partition key nên liên quan trực tiếp đến các điều kiện truy vấn phổ biến và vòng đời dữ liệu. Với dữ liệu sự kiện, `created_at` thường phù hợp nếu truy vấn và retention theo thời gian. Với dữ liệu tenant, `tenant_id` có thể hữu ích nếu truy vấn luôn lọc tenant, nhưng cần xem số tenant và cách phân phối.

Các nguyên tắc:

- Chọn cột có ý nghĩa ổn định và được dùng trong predicate thường xuyên.
- Dùng kiểu dữ liệu và biểu thức truy vấn tương thích với partition bounds.
- Tránh biến đổi khóa phân vùng bằng hàm nếu hệ quản trị không thể suy ra phạm vi.
- Với range partitioning, xác định rõ biên đầu/cuối và múi giờ.
- Với hash partitioning, xác định số bucket theo nhu cầu phân phối và giới hạn đối tượng.
- Đảm bảo ứng dụng luôn truyền predicate phân vùng khi có thể.

Ví dụ nên dùng khoảng nửa mở:

```sql
WHERE created_at >= :start_time
  AND created_at < :end_time
```

Thay vì:

```sql
WHERE DATE(created_at) = :event_date
```

Biểu thức đầu thường dễ đối chiếu với range bounds và chỉ mục B-tree hơn. Nếu cần lọc theo ngày lịch trong múi giờ nghiệp vụ, hãy tính `start_time` và `end_time` đúng múi giờ ở tầng ứng dụng hoặc dùng biểu thức được hệ quản trị hỗ trợ, sau đó kiểm tra pruning.

## 10. Subpartitioning: khi nào có lợi và khi nào quá mức?

Subpartitioning chia mỗi partition cấp cao thành các phần nhỏ hơn, ví dụ range theo tháng rồi hash theo tenant. Nó có thể giúp phân phối dữ liệu trong mỗi tháng, hỗ trợ song song hoặc giảm contention trong một số kiến trúc.

Nhưng số leaf partition thường là tích của các nhánh. Nếu 120 tháng chia thành 16 hash bucket, hệ thống có 1.920 leaf partitions. Nếu tiếp tục chia theo khu vực thành 8 phần, số leaf có thể thành 15.360.

Trước khi dùng subpartitioning, hãy xác định:

- Vấn đề nào chưa được giải quyết bởi một chiều partition?
- Truy vấn có lọc theo cả hai khóa không?
- Có thật sự cần phân phối dữ liệu hoặc quản lý độc lập theo chiều thứ hai không?
- Số leaf partition và index object sau nhiều năm là bao nhiêu?
- Hệ quản trị có hỗ trợ pruning qua các cấp và runtime pruning như mong muốn không?
- Công cụ backup, restore, monitoring và migration có xử lý được quy mô đó không?

Nếu chiều thứ hai chỉ giúp một số ít truy vấn, có thể chỉ mục ghép hoặc sharding ở tầng kiến trúc phù hợp hơn so với tạo thêm hàng nghìn partition.

## 11. Theo dõi chi phí partitioning bằng số liệu

Không có một ngưỡng số partition tối đa đúng cho mọi hệ quản trị. Cần theo dõi xu hướng và tác động của số partition lên planning, execution và maintenance.

### 11.1. Chỉ số truy vấn

| Chỉ số | Ý nghĩa |
|---|---|
| Planning time | Thời gian lập kế hoạch trước khi thực thi |
| Execution time | Thời gian chạy các toán tử của kế hoạch |
| Application latency | Độ trễ ứng dụng quan sát, gồm cả phần ngoài DB |
| Partitions pruned | Số partition bị loại khỏi truy vấn |
| Partitions scanned/accessed | Số partition thực sự được mở hoặc đọc |
| Rows estimated/actual | Sai lệch cardinality ở từng partition/toán tử |
| Logical/physical reads | Số trang đọc từ cache và lưu trữ theo hệ quản trị |
| Planning CPU/memory | Tài nguyên dùng trong giai đoạn lập kế hoạch nếu đo được |
| Lock/wait time | Chờ do metadata, relation lock, I/O hoặc tài nguyên khác |

Theo dõi cả trung bình và phân vị cao. Một số truy vấn chỉ chạm một partition có thể nhanh, trong khi báo cáo tổng hợp qua nhiều partition gây planning time hoặc execution time cao. Phân nhóm theo mẫu truy vấn sẽ giúp xác định loại workload nào chịu tác động.

### 11.2. Chỉ số quản lý và bảo trì

- Tổng số partition, số partition hoạt động và số partition rỗng.
- Số partition có dữ liệu và kích thước trung bình/nhỏ nhất/lớn nhất.
- Số index object và kích thước index theo partition.
- Thời gian tạo partition mới, attach/detach/drop và thời gian chờ khóa.
- Thời gian analyze/vacuum/rebuild và số lỗi bảo trì.
- Tần suất partition thiếu hoặc dữ liệu rơi vào default partition.
- Thời gian backup, restore, archive và kiểm tra tính toàn vẹn.
- Mức tăng metadata/catalog và bộ nhớ cache đối tượng nếu hệ quản trị cung cấp số liệu.

### 11.3. Đo trước và sau khi thay đổi granularity

Nếu giảm độ hạt từ tháng xuống ngày, không chỉ đo truy vấn ngày. Hãy đo:

1. Truy vấn một ngày và một khoảng nhiều ngày.
2. Truy vấn không có predicate trên partition key.
3. Truy vấn prepared statement với tham số đại diện.
4. Truy vấn tổng hợp toàn bộ thời gian lưu giữ.
5. Thao tác insert/update và truy vấn ghi đồng thời.
6. Thời gian planning, execution và các tác vụ bảo trì.

Giữ cùng dữ liệu, thống kê, cấu hình và tải. Nếu không thể giữ nguyên, ghi lại sai khác để tránh quy kết sai tác động cho số partition.

## 12. Đọc execution plan khi có nhiều partition

Kế hoạch thực thi cần cho biết bảng partitioned được xử lý như thế nào. Tên toán tử và cách hiển thị tùy hệ quản trị, nhưng hãy tìm:

- Danh sách partition được giữ lại hoặc bị loại.
- Partition pruning diễn ra ở planning hay execution.
- Số partition scan và số hàng đọc ở từng partition.
- Có scan nhiều partition rỗng hoặc không liên quan không.
- Có index seek/scan phù hợp trong từng partition không.
- Có sort/hash/aggregate lặp lại theo từng partition rồi mới tổng hợp không.
- Có parallel append, partition-wise join hoặc partition-wise aggregate nếu hệ quản trị hỗ trợ không.
- Estimated rows có phản ánh phân bố khác nhau giữa các partition không.

Trong PostgreSQL, `EXPLAIN (ANALYZE, BUFFERS)` có thể cho biết thời gian planning/execution, số liệu buffer và thông tin pruning tùy phiên bản/kế hoạch. Hãy dùng trong môi trường phù hợp vì `ANALYZE` thực thi câu lệnh. Với các hệ quản trị khác, dùng công cụ execution plan và thống kê runtime tương ứng.

Ví dụ minh họa PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM events
WHERE created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at < TIMESTAMP '2026-11-01 00:00:00';
```

So sánh kế hoạch khi truy vấn một tháng, nhiều tháng và toàn bộ bảng. Nếu planning time tăng theo tổng số partition trong khi số partition được đọc nhỏ, đó là tín hiệu cần điều tra chi phí lập kế hoạch/metadata. Nếu nhiều partition thực sự được đọc, cần xem phạm vi truy vấn và thiết kế khóa phân vùng.

## 13. Các chiến lược giảm chi phí khi số partition lớn

### 13.1. Tăng độ hạt khi phân vùng quá nhỏ

Nếu partition theo ngày nhưng truy vấn và retention chủ yếu theo tháng, có thể thử gộp thành partition theo tuần hoặc tháng. Số đối tượng giảm, nhưng truy vấn hẹp có thể phải đọc phạm vi rộng hơn. Phải so sánh cả pruning, I/O, planning time và chi phí retention.

### 13.2. Dùng partitioning kết hợp index phù hợp

Partitioning giảm phạm vi dữ liệu ở cấp partition; index giảm phạm vi trong từng partition. Hai cơ chế bổ sung cho nhau. Ví dụ truy vấn một tenant trong một tháng có thể prune theo thời gian rồi seek theo `tenant_id` trong partition còn lại.

Không nên tạo một partition cho mỗi tenant nếu index ghép `(tenant_id, created_at)` trong partition theo tháng đã đáp ứng workload. Hãy đo số partition được truy cập và lượng dữ liệu đọc trước khi tăng số chiều phân vùng.

### 13.3. Giới hạn số partition được tạo trước

Không cần tạo trước vô hạn partition tương lai. Có thể tự động tạo trước một khoảng hợp lý, theo dõi partition sắp tới và có quy trình tạo bổ sung. Tuy nhiên, không để dữ liệu ghi rơi vào default partition ngoài dự kiến hoặc làm giao dịch thất bại khi partition mới chưa tồn tại.

### 13.4. Tự động hóa vòng đời partition

Dùng lịch tạo, attach, detach, archive và drop partition có kiểm soát. Quy trình nên kiểm tra:

- Partition tiếp theo đã tồn tại trước thời điểm cần ghi.
- Bounds không chồng lấn và không tạo khoảng trống ngoài chủ ý.
- Index và constraint cần thiết đã sẵn sàng.
- Quyền, compression, storage tier và chính sách backup đúng.
- Dữ liệu đến muộn được xử lý theo quy tắc đã định.
- Thao tác detach/drop có thời gian chờ khóa và phương án khôi phục.

Tự động hóa giúp giảm thao tác thủ công nhưng cần idempotent, có log, cảnh báo và kiểm tra sau thực hiện.

### 13.5. Đánh giá partition-wise operations

Một số hệ quản trị có thể thực hiện join hoặc aggregate theo từng partition khi hai phía có cách phân vùng tương thích. Điều này có thể giảm dữ liệu trao đổi hoặc hỗ trợ song song. Nhưng nếu số partition quá nhiều, số nhánh kế hoạch và công việc khởi tạo cũng tăng. Hãy xác nhận execution plan có thật sự sử dụng partition-wise join/aggregate và lợi ích vượt chi phí hay không.

## 14. Khác biệt cần biết giữa các hệ quản trị

Khả năng partitioning và giới hạn thực tế khác nhau đáng kể. Bảng sau chỉ là định hướng, không thay thế tài liệu đúng phiên bản.

| Hệ quản trị | Điểm cần xem xét |
|---|---|
| PostgreSQL | Declarative partitioning, pruning ở planning/runtime, partitioned indexes, thống kê và chi phí catalog/relcache; số partition lớn có thể làm planning và metadata nặng |
| MySQL | Partition pruning theo partition expression, giới hạn số partition và quy tắc liên quan engine/unique key; kiểm tra giới hạn phiên bản và khả năng index trên partitioned table |
| SQL Server | Partition function/scheme, partition elimination, aligned/nonaligned indexes, statistics và tác động của partition-level maintenance |
| Oracle | Range/list/hash/composite partitioning, local/global indexes, partition pruning, partition maintenance operations và statistics ở cấp partition/global |

Không có một con số “an toàn” chung cho số partition. Ngưỡng vận hành phụ thuộc phiên bản, phần cứng, số truy vấn, mức độ pruning, số index, số partition được mở và công cụ quản trị. Hãy dùng số liệu từ môi trường thật hoặc benchmark tương đương để xác định giới hạn phù hợp.

## 15. Ví dụ thực hành: bảng sự kiện theo tháng

Giả sử bảng `events` lưu sự kiện trong 7 năm. Truy vấn phổ biến gồm:

- Lấy sự kiện của một ngày hoặc một tháng.
- Tra cứu một `event_id` cụ thể.
- Báo cáo tổng hợp toàn bộ một quý.
- Xóa dữ liệu quá thời hạn lưu trữ.

Một thiết kế ban đầu có thể partition theo tháng trên `created_at`, đồng thời tạo B-tree index trên `event_id` nếu cần point lookup. Truy vấn khoảng thời gian dùng điều kiện nửa mở để hỗ trợ pruning.

Với 7 năm, số partition tháng xấp xỉ 84. Nếu chia theo ngày, số partition xấp xỉ 2.557. Phân vùng theo ngày có thể giúp drop dữ liệu theo ngày, nhưng nếu retention theo tháng và phần lớn truy vấn theo tháng thì số partition tăng thêm có thể không mang lại lợi ích tương xứng.

Quy trình đánh giá:

1. Thu thập tỷ lệ truy vấn theo ngày, tháng, quý và truy vấn theo `event_id`.
2. Đo planning time, execution time và application latency trước thay đổi.
3. Lấy kế hoạch cho truy vấn một ngày, một tháng, một quý và toàn thời gian.
4. Ghi số partition được prune, số partition được truy cập, số hàng và buffer/page đọc.
5. So sánh phương án tháng với ngày trên bản sao dữ liệu có kích thước và phân bố đại diện.
6. Đo insert throughput, chi phí index, thời gian analyze/vacuum hoặc maintenance.
7. Đo thời gian tạo/detach/drop partition và backup/restore.
8. Chọn granularity có tổng chi phí phù hợp với SLO, retention và khả năng vận hành.

Nếu truy vấn theo ngày nhanh hơn nhưng planning time, số index object và maintenance tăng mạnh, thiết kế theo ngày có thể không phải lựa chọn tốt nhất. Nếu thao tác xóa theo ngày là yêu cầu bắt buộc và khối lượng dữ liệu rất lớn, lợi ích vận hành có thể bù phần chi phí đó. Quyết định cần dựa trên yêu cầu thật, không chỉ một benchmark truy vấn đọc.

## 16. Kế hoạch thay đổi khi hệ thống đã có nhiều partition

Không nên đổi granularity hoặc partition key trực tiếp trên hệ thống lớn mà chưa lập kế hoạch di chuyển. Một quy trình có kiểm soát gồm:

1. **Đánh giá hiện trạng:** số partition, kích thước, index, constraint, thống kê, truy vấn và thời gian maintenance.
2. **Xác định mục tiêu:** giảm planning time, giảm đối tượng, cải thiện pruning hay đơn giản hóa retention.
3. **Thiết kế mô hình đích:** partition key, granularity, số leaf partition, index và chính sách dữ liệu đến muộn.
4. **Thử nghiệm chuyển đổi:** dùng snapshot dữ liệu và workload đại diện; đo thời gian copy/repartition, dung lượng tạm và tải phát sinh.
5. **Lập phương án đồng bộ:** xác định cách bắt kịp thay đổi phát sinh trong lúc chuyển dữ liệu.
6. **Chuẩn bị cutover và rollback:** xác định thời gian khóa, kiểm tra constraint, đối chiếu số hàng và cách quay lại.
7. **Triển khai theo giai đoạn:** chuyển một phạm vi nhỏ trước nếu kiến trúc cho phép.
8. **Theo dõi sau chuyển đổi:** planning, pruning, latency, throughput, I/O, maintenance và lỗi partition.

Một thay đổi phân vùng có thể ảnh hưởng khóa, index, constraint, replication, CDC, backup và công cụ ETL. Phải kiểm tra các thành phần phụ thuộc trước khi triển khai.

## 17. Những sai lầm thường gặp

- **Chia theo ngày hoặc giờ mặc định:** số partition tăng rất nhanh dù workload không cần độ hạt đó.
- **Partition theo cardinality quá cao:** tạo một partition cho mỗi tenant hoặc khóa có hàng triệu giá trị.
- **Chỉ nhìn số partition được đọc:** bỏ qua planning time và metadata phải xem xét.
- **Không kiểm tra pruning:** partition tồn tại nhưng predicate không giúp loại bỏ phần không liên quan.
- **Dùng hàm trên partition key:** làm điều kiện khó khớp với partition bounds hoặc index.
- **Tạo subpartition theo tích nhiều chiều:** số leaf partition và index object tăng vượt khả năng vận hành.
- **Bỏ qua thống kê cục bộ:** phân bố dữ liệu khác nhau giữa các partition làm cardinality estimate sai.
- **Không tự động hóa partition tương lai:** insert thất bại hoặc dữ liệu rơi vào default partition ngoài dự kiến.
- **Không kiểm tra local/global index:** thao tác detach/drop có thể làm index mất hiệu lực hoặc cần bảo trì theo cách riêng.
- **Đo một truy vấn duy nhất:** bỏ qua workload tổng hợp, ghi, prepared statement và maintenance.
- **Cho rằng partitioning thay thế indexing:** mỗi partition vẫn có thể cần index để truy cập hàng hiệu quả.

## 18. Bài tập tự kiểm tra

### Bài tập 1: Chọn granularity

Một bảng log giữ 4 năm. 80% truy vấn đọc dữ liệu theo tháng, retention xóa theo tháng, một số truy vấn điều tra đọc theo giờ.

**Câu hỏi:** nên bắt đầu đánh giá partition theo ngày hay tháng? Những chỉ số nào cần so sánh?

**Gợi ý trả lời:** partition theo tháng là giả thuyết ban đầu hợp lý vì khớp phần lớn truy vấn và retention. Cần benchmark truy vấn theo giờ để xem chi phí đọc trong partition tháng, đồng thời so sánh planning time, số partition, I/O, insert throughput, index object và maintenance với phương án ngày. Không quyết định chỉ dựa vào số hàng.

### Bài tập 2: Nhiều partition nhưng chỉ đọc một phần nhỏ

Một bảng có 2.000 partition. Truy vấn lọc một tháng và chỉ đọc một partition, nhưng planning time tăng từ 5 ms lên 80 ms sau khi số partition tăng.

**Câu hỏi:** cần điều tra điều gì?

**Gợi ý trả lời:** xác định planning time có tăng theo tổng số partition hoặc metadata hay không; kiểm tra partition bounds, số partition ứng viên, prepared/generic plan, thống kê, index object và phiên bản hệ quản trị. Đo riêng planning và execution, thử granularity lớn hơn trên môi trường tương đương và xác nhận pruning vẫn đúng.

### Bài tập 3: Subpartitioning theo tenant

Một bảng đã partition theo tháng. Nhóm muốn thêm 64 hash subpartition theo `tenant_id` vì có nhiều tenant.

**Câu hỏi:** cần tính gì trước khi thay đổi?

**Gợi ý trả lời:** tính tổng leaf partition trong toàn thời gian lưu giữ, số index object, chi phí planning, maintenance, backup/restore và số partition truy cập mỗi truy vấn. Xác nhận truy vấn có lọc tenant và hệ quản trị có pruning qua cả hai cấp. So sánh với phương án chỉ mục ghép `(tenant_id, created_at)` trong partition tháng.

### Bài tập 4: Prepared statement và pruning

Truy vấn tham số hóa lọc `created_at` trong khoảng thời gian nhưng kế hoạch không hiển thị rõ partition pruning tại lúc lập kế hoạch.

**Câu hỏi:** cần kiểm tra gì trước khi kết luận pruning không hoạt động?

**Gợi ý trả lời:** kiểm tra hệ quản trị có runtime pruning hay không, xem actual plan với giá trị tham số cụ thể, so sánh prepared statement và literal, thử khoảng một partition và nhiều partition. Đọc tài liệu đúng phiên bản và đo số partition thực sự được truy cập.

### Checklist trước khi triển khai thiết kế partition

- [ ] Partition key phù hợp với predicate và vòng đời dữ liệu.
- [ ] Granularity được chọn theo workload, retention và kích thước dữ liệu.
- [ ] Đã ước tính tổng số partition trong toàn bộ thời gian lưu giữ.
- [ ] Đã tính số leaf partition khi dùng subpartitioning.
- [ ] Đã ước tính số index object và chi phí metadata.
- [ ] Đã xác nhận pruning ở planning/runtime bằng execution plan.
- [ ] Đã đo planning time riêng với execution time.
- [ ] Đã kiểm tra prepared statement, generic plan và nhóm tham số đại diện.
- [ ] Thống kê và bảo trì theo partition có kế hoạch rõ ràng.
- [ ] Tự động hóa tạo, attach, detach, archive và drop partition có kiểm soát.
- [ ] Đã đánh giá tác động lên ghi, khóa, backup, restore, replication và ETL.
- [ ] Có phương án migration, cutover, đối chiếu dữ liệu và rollback.

Phân vùng có giá trị khi nó loại bỏ được dữ liệu không cần đọc hoặc đơn giản hóa vòng đời dữ liệu ở mức đủ lớn để bù chi phí quản lý. Quá nhiều partition có thể làm planning, metadata, index, thống kê, bảo trì và vận hành trở nên nặng nề dù mỗi truy vấn chỉ đọc một vài phần. Hãy đo riêng số partition được xem xét, được prune và thực sự truy cập; cân bằng độ hạt với mẫu truy vấn và retention; sau đó xác nhận trên workload đại diện trước khi triển khai.
