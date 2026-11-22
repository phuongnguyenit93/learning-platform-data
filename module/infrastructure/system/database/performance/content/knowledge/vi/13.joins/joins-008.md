# Tràn bộ nhớ ở phép nối băm và ảnh hưởng của phân bố khóa

Hash Join là thuật toán kết hợp hai tập dữ liệu bằng cách xây dựng bảng băm từ một phía rồi dò tìm các khóa tương ứng ở phía còn lại. Thuật toán này thường hiệu quả khi kết hợp các tập dữ liệu lớn mà không có chỉ mục phù hợp cho Nested Loop. Tuy nhiên, hiệu năng có thể suy giảm mạnh nếu bảng băm vượt ngân sách bộ nhớ hoặc khóa join phân bố lệch. Khi đó hệ quản trị có thể phải chia dữ liệu thành nhiều batch, ghi dữ liệu tạm ra đĩa, hoặc để một partition hay worker xử lý nhiều công việc hơn phần còn lại.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần phân biệt **tràn bộ nhớ (spill)** với **lệch phân bố khóa (key skew)**. Spill có thể xuất hiện chỉ vì phía build lớn hơn dự đoán hoặc hàng quá rộng, ngay cả khi khóa phân bố đều. Skew có thể làm một số bucket, partition hoặc worker trở nên quá tải; khi khóa xuất hiện nhiều lần ở cả hai phía, nó còn có thể làm số hàng kết quả tăng theo tích số lần xuất hiện. Hai hiện tượng có thể xảy ra cùng lúc và làm khuếch đại tác động của nhau.

Bài học này hướng dẫn đọc kế hoạch Hash Join, hiểu ngân sách bộ nhớ, nhận diện batch và I/O tạm, đo độ lệch của khóa, tìm nguyên nhân từ thống kê và thiết kế truy vấn, rồi xác minh điều chỉnh trên workload đại diện.

## 1. Cách Hash Join hoạt động

Hash Join thường có hai đầu vào:

- **Build side:** hệ quản trị đọc một tập dữ liệu và xây dựng bảng băm trong bộ nhớ dựa trên khóa join.
- **Probe side:** hệ quản trị đọc tập dữ liệu còn lại, băm khóa của từng hàng rồi tra bảng băm để tìm hàng khớp.

Với phép nối bằng, quy trình khái quát như sau:

1. Đọc các hàng của build side.
2. Tính giá trị hash từ khóa join.
3. Đưa hàng hoặc phần dữ liệu cần thiết vào bucket tương ứng trong hash table.
4. Đọc từng hàng ở probe side và tính hash của khóa.
5. Tra bucket tương ứng, so sánh lại giá trị khóa để xác nhận khớp.
6. Phát ra các hàng kết quả và áp dụng các điều kiện còn lại theo kế hoạch.

Hash chỉ giúp tìm vùng ứng viên. Hệ quản trị vẫn phải so sánh giá trị khóa thực tế để xử lý va chạm hash và bảo đảm kết quả đúng.

Ví dụ, cần nối khách hàng với đơn hàng:

~~~sql
SELECT c.customer_id, c.customer_name, o.order_id, o.total_amount
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region_id = 7;
~~~

Nếu optimizer chọn customers sau khi lọc làm build side, nó tạo bảng băm theo customer_id. Sau đó orders là probe side; mỗi đơn hàng tra cứu khách hàng tương ứng. Trong kế hoạch văn bản, toán tử Hash thường biểu thị bước xây dựng bảng băm, còn Hash Join biểu thị bước dò và kết hợp.

Không được suy ra build side chỉ từ thứ tự bảng trong mệnh đề FROM. Optimizer có thể đổi thứ tự join hoặc chọn đầu vào khác tùy cardinality, ràng buộc, kiểu join và chi phí. Với outer join, semi join hoặc anti join, ràng buộc ngữ nghĩa cũng giới hạn các phép đổi thứ tự.

## 2. Vì sao Hash Join cần bộ nhớ?

Bảng băm cần giữ thông tin về các hàng ở build side để probe side có thể tra cứu. Dung lượng cần thiết không chỉ bằng số byte dữ liệu gốc. Nó còn gồm cấu trúc bucket, con trỏ, thông tin hash, căn chỉnh bộ nhớ, dữ liệu khóa và phần payload cần trả về hoặc kiểm tra.

Có thể hình dung gần đúng:

\[
M_{hash}\approx N_{build}\times(W_{row}+H_{entry})\times F
\]

Trong đó:

- \(N_{build}\) là số hàng phía build.
- \(W_{row}\) là độ rộng dữ liệu cần lưu cho mỗi hàng.
- \(H_{entry}\) là phần overhead cho mỗi mục trong bảng băm.
- \(F\) là hệ số phụ thuộc cách cài đặt, bucket, căn chỉnh và cấu trúc dữ liệu.

Đây là mô hình giải thích, không phải công thức chính xác để dự báo dung lượng của mọi hệ quản trị. Hệ quản trị có thể lưu toàn bộ hàng, chỉ các cột cần thiết, hoặc biểu diễn khác tùy thuật toán.

Hai yếu tố thường làm tăng nhu cầu bộ nhớ:

1. **Cardinality build side lớn hơn dự kiến:** optimizer ước lượng ít hàng nhưng thực tế phải đưa nhiều hàng vào hash table.
2. **Hàng rộng:** truy vấn mang theo nhiều cột lớn, chẳng hạn TEXT, JSON hoặc payload không cần thiết cho điều kiện join, làm tăng bộ nhớ và I/O.

Ngoài ra, nhiều Hash Join hoặc các toán tử sort/hash khác có thể cùng hoạt động trong một truy vấn. Nhiều truy vấn đồng thời cũng có thể yêu cầu bộ nhớ cùng lúc. Vì vậy, tăng ngân sách cho một toán tử có thể ảnh hưởng đến khả năng phục vụ tổng thể.

## 3. Spill và cơ chế chia batch

Nếu bảng băm không thể nằm gọn trong ngân sách bộ nhớ được cấp, nhiều hệ quản trị chuyển sang chiến lược chia dữ liệu thành các partition hoặc batch. Ý tưởng tổng quát:

1. Dùng hàm hash để phân chia build side thành các nhóm.
2. Ghi những nhóm chưa thể xử lý vào vùng lưu trữ tạm.
3. Phân chia probe side theo cùng quy tắc để các hàng có khả năng khớp nằm trong cùng nhóm.
4. Nạp từng nhóm cần xử lý vào bộ nhớ, xây dựng bảng băm và dò nhóm tương ứng.
5. Lặp lại cho các batch còn lại.

Khi phải ghi và đọc dữ liệu tạm, Hash Join phát sinh thêm I/O, chi phí tuần tự hóa, cấp phát bộ nhớ và thời gian xử lý. Nếu hệ quản trị phải chia nhiều batch hoặc xử lý nhiều lượt, độ trễ có thể tăng rõ rệt so với trường hợp bảng băm nằm hoàn toàn trong RAM.

### Phân biệt spill với việc dùng nhiều bucket

Số bucket là cấu trúc chia vùng tra cứu trong hash table. Số batch là số nhóm dữ liệu được xử lý theo từng lượt do giới hạn bộ nhớ. Có nhiều bucket không đồng nghĩa với spill. Trong kế hoạch PostgreSQL, Hash node có thể hiển thị Buckets, Batches và Memory Usage. Khi Batches lớn hơn 1, hash join đang dùng cơ chế nhiều batch; hãy xem thêm thống kê temp read/write để xác nhận lượng I/O tạm phát sinh.

Một ví dụ đầu ra minh họa:

~~~text
Hash Join
  Hash Cond: (orders.customer_id = customers.customer_id)
  -> Seq Scan on orders
       actual rows=12000000
  -> Hash
       Buckets: 262144
       Batches: 16
       Memory Usage: 8192kB
       -> Seq Scan on customers
            actual rows=1800000
~~~

Các con số chỉ minh họa. Batches bằng 16 cho thấy hash join được chia thành nhiều batch. Cần đọc thêm BUFFERS, temp read/write, thời gian và số hàng thực tế để hiểu chi phí spill trong lần chạy đó.

### Spill không phải lúc nào cũng là lỗi

Một truy vấn phân tích có thể cần kết hợp lượng dữ liệu lớn hơn ngân sách bộ nhớ hợp lý. Chia batch và dùng tệp tạm là cơ chế cho phép truy vấn hoàn tất mà không giữ toàn bộ dữ liệu trong RAM. Điều cần đánh giá là chi phí I/O tạm có chấp nhận được không, truy vấn có đáp ứng mục tiêu thời gian không và có gây áp lực lên các workload khác không.

## 4. Key skew là gì?

Phân bố khóa join bị lệch khi một số giá trị xuất hiện thường xuyên hơn nhiều so với phần còn lại. Ví dụ, bảng events có hàng triệu bản ghi nhưng một tenant hoặc một customer tạo ra tỷ lệ dữ liệu rất lớn. NDV có thể cao, nhưng một vài giá trị vẫn chiếm phần đáng kể của bảng.

Nếu hệ thống hash theo khóa, các hàng có cùng giá trị khóa sẽ được đưa về cùng bucket hoặc partition theo quy tắc hash. Một khóa rất phổ biến có thể khiến một bucket hoặc batch chứa nhiều hàng hơn các nhóm khác. Trong xử lý song song, một worker có thể nhận nhiều dữ liệu hơn, trở thành nút chậm nhất và kéo dài thời gian hoàn tất của toàn bộ truy vấn.

Skew có thể ảnh hưởng theo nhiều cách:

- **Build-side skew:** một số khóa chiếm nhiều hàng trong hash table. Hash table có thể lớn hơn dự kiến hoặc một số partition chứa lượng dữ liệu vượt trội.
- **Probe-side skew:** một số khóa xuất hiện dày đặc ở phía dò, làm nhiều hàng liên tục tra cùng một vùng hash và có thể tạo ra rất nhiều kết quả.
- **Partition skew:** khi chia batch theo hash, các khóa phổ biến hoặc va chạm phân phối có thể làm một batch lớn hơn hẳn các batch còn lại.
- **Parallel skew:** các worker nhận lượng hàng hoặc lượng kết quả khác nhau, khiến một số worker hoàn tất sớm trong khi worker khác còn xử lý lâu.
- **Join multiplicity:** nếu một khóa xuất hiện nhiều lần ở cả hai phía, số hàng kết quả cho khóa đó có thể tăng theo tích số lần xuất hiện.

### Công thức số hàng kết quả theo khóa

Với phép equijoin thông thường, gọi \(L(k)\) là số hàng phía trái có khóa \(k\), và \(R(k)\) là số hàng phía phải có khóa \(k\). Số hàng kết quả của riêng khóa đó là:

\[
J(k)=L(k)\times R(k)
\]

Tổng số hàng join có thể biểu diễn:

\[
J=\sum_{k}L(k)\times R(k)
\]

Ví dụ, khóa customer_id = 42 có 80.000 hàng ở bảng events và 6.000 hàng ở bảng sessions. Join theo customer_id sẽ tạo:

\[
80.000\times6.000=480.000.000\text{ hàng}
\]

Đây có thể là kết quả đúng theo ngữ nghĩa SQL, dù số hàng đầu ra rất lớn. Nếu nghiệp vụ chỉ cần xác định khách hàng có hoạt động hay không, EXISTS hoặc semi join có thể thể hiện đúng yêu cầu hơn và tránh tạo mọi cặp hàng. Không được thay đổi phép join thành EXISTS nếu ứng dụng cần đầy đủ từng cặp kết quả.

Với phép so sánh bằng thông thường, NULL không khớp với NULL. Nếu dùng toán tử so sánh NULL-safe hoặc điều kiện khác, phải đánh giá lại ngữ nghĩa và công thức.

## 5. Phân biệt memory pressure và key skew

Hai hiện tượng có thể đi cùng nhau nhưng nguyên nhân và cách xử lý khác nhau.

| Dấu hiệu | Vượt ngân sách bộ nhớ | Lệch phân bố khóa |
|---|---|---|
| Nguyên nhân chính | Build side lớn, hàng rộng, memory grant thấp hoặc nhiều toán tử cạnh tranh | Một số khóa có tần suất vượt trội hoặc phân phối giữa worker/batch mất cân bằng |
| Dấu hiệu kế hoạch | Nhiều batch, temp read/write, spill warning, hash memory đạt giới hạn | Một số partition/worker xử lý lâu hoặc nhiều hàng hơn; hot key có số lần xuất hiện cao |
| Có thể xảy ra khi khóa phân bố đều? | Có | Không cần; skew đòi hỏi phân bố không đều |
| Có thể xảy ra khi hash table nhỏ? | Thường ít khả năng gây spill do bộ nhớ | Có thể vẫn có skew ở probe side hoặc số hàng kết quả |
| Hướng điều tra | Cardinality, row width, memory grant, giới hạn bộ nhớ và concurrency | Tần suất khóa, MCV, NDV, phân bố theo partition và số hàng kết quả theo khóa |

Nếu chỉ tăng bộ nhớ mà không xử lý skew, một partition nóng hoặc lượng kết quả khổng lồ vẫn có thể làm truy vấn chậm. Nếu chỉ phân phối lại khóa mà build side vẫn quá lớn, hash table vẫn có thể spill.

## 6. Đọc bằng chứng spill trong execution plan

Không nên kết luận có spill chỉ từ việc thấy Hash Join. Cần xem thuộc tính và thống kê thực tế mà hệ quản trị cung cấp.

### PostgreSQL

Với truy vấn đọc trong môi trường phù hợp, có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT ...
FROM ...
JOIN ... ON ...;
~~~

Các điểm cần xem:

- **Hash:** Buckets, Batches và Memory Usage.
- **Hash Join:** số hàng thực tế, thời gian và điều kiện Hash Cond.
- **BUFFERS:** shared hit/read và temp read/written nếu có.
- **Estimated rows so với actual rows:** sai lệch cardinality có thể khiến hệ quản trị dự trù hash table quá nhỏ.
- **Loops:** toán tử có thể được gọi nhiều lần trong một kế hoạch lồng nhau.

Khi Batches lớn hơn 1, hash join dùng nhiều batch. Temp blocks read/written cho biết hoạt động trên dữ liệu tạm; cần đọc tổng thể vì temp I/O cũng có thể đến từ Sort, Materialize hoặc toán tử khác.

PostgreSQL dùng work_mem làm giới hạn bộ nhớ cho một số thao tác sort/hash; giới hạn hash có thể chịu ảnh hưởng của hash_mem_multiplier tùy phiên bản. work_mem không phải ngân sách duy nhất cho cả máy chủ hay cả truy vấn. Một truy vấn có thể có nhiều thao tác cần bộ nhớ và nhiều truy vấn có thể chạy đồng thời. Tăng work_mem toàn cục thiếu kiểm soát có thể làm tổng RAM tiêu thụ tăng mạnh.

### SQL Server

Trong Actual Execution Plan, xem:

- Hash Match operator và loại join.
- MemoryGrantInfo: requested, granted, used hoặc max used tùy công cụ.
- Cảnh báo spill trên Hash Match, thông tin spill level và dữ liệu ghi ra tempdb nếu được hiển thị.
- Estimated Number of Rows, Actual Number of Rows và Actual Number of Executions.
- Các thuộc tính liên quan đến parallelism và phân phối hàng giữa worker.

Memory grant được tính từ ước lượng cardinality và độ rộng hàng cùng yêu cầu của các operator cần bộ nhớ. Nếu ước lượng thấp, grant có thể không đủ; nếu ước lượng cao, truy vấn có thể giữ nhiều bộ nhớ hơn cần thiết và làm các truy vấn khác phải chờ grant.

SQL Server có các cơ chế như memory grant feedback ở những phiên bản và tình huống hỗ trợ, giúp điều chỉnh grant qua các lần thực thi. Cơ chế này không thay thế việc sửa thống kê sai, kiểm tra parameter sensitivity hoặc xử lý key skew.

### MySQL

MySQL có thể sử dụng hash join cho một số kế hoạch và phiên bản. Khi đọc EXPLAIN ANALYZE, hãy xem iterator Hash Join, số hàng và thời gian ở từng iterator, đồng thời kiểm tra log/metric tài nguyên tạm theo phiên bản. Cách quản lý bộ nhớ và spill của hash join khác các hệ quản trị khác; không áp dụng trực tiếp diễn giải Buckets/Batches của PostgreSQL.

### Oracle

Oracle có thể dùng hash join với workarea trong PGA. Khi workarea không đủ, thao tác có thể chuyển sang one-pass hoặc multi-pass và dùng temporary tablespace. Các view hiệu năng như V$SQL_WORKAREA, V$SQL_WORKAREA_ACTIVE và thống kê thực thi có thể hỗ trợ điều tra, tùy quyền truy cập và phiên bản.

Tên trường, công cụ và chi tiết thuật toán thay đổi theo hệ quản trị. Luôn đối chiếu tài liệu của phiên bản đang chạy và đọc toàn bộ kế hoạch thay vì chỉ nhìn một operator.

## 7. Đo phân bố khóa và tìm hot key

NDV cho biết có bao nhiêu giá trị khác nhau, nhưng không mô tả đầy đủ tần suất của từng giá trị. Hai bảng có cùng NDV vẫn có thể có phân bố rất khác nhau: một bảng phân bố gần đều, bảng còn lại có một khóa chiếm 40% số hàng.

Để phát hiện skew, cần kiểm tra:

- Tần suất của các khóa phổ biến nhất ở build side.
- Tần suất của các khóa phổ biến nhất ở probe side.
- Tỷ lệ hàng của khóa phổ biến nhất so với tổng hàng.
- Chênh lệch giữa khóa lớn nhất, trung vị và các phân vị tần suất.
- Số hàng kết quả dự kiến của các khóa phổ biến khi join hai phía.
- Mức phân phối hàng giữa worker hoặc partition nếu công cụ cung cấp.

Ví dụ kiểm tra top key trong PostgreSQL/MySQL:

~~~sql
SELECT customer_id, COUNT(*) AS row_count
FROM events
GROUP BY customer_id
ORDER BY row_count DESC
LIMIT 20;
~~~

Chạy truy vấn tương tự trên bảng phía còn lại để so sánh. Với SQL Server có thể dùng TOP thay cho LIMIT. Trên bảng lớn, truy vấn GROUP BY có thể tự tiêu tốn nhiều CPU, bộ nhớ và I/O; hãy dùng replica phân tích, mẫu dữ liệu, khoảng thời gian giới hạn hoặc cơ chế thống kê sẵn có nếu cần.

Một chỉ số sàng lọc đơn giản:

\[
SkewRatio=\frac{\text{Tần suất khóa lớn nhất}}{\text{Tần suất trung bình}}
\]

Nếu tỷ lệ này rất lớn, phân phối có thể bị lệch mạnh. Tuy nhiên, chỉ số này phụ thuộc cách xác định tập khóa và có thể bị ảnh hưởng bởi giá trị NULL hoặc các khóa không xuất hiện ở cả hai phía. Hãy xem thêm top-N và phân phối đầy đủ hơn khi cần.

### Ví dụ dữ liệu lệch

Giả sử bảng events có 20 triệu hàng và 10.000 customer_id. Một khách hàng có 7 triệu hàng, 9.999 khách hàng còn lại chia nhau 13 triệu hàng. NDV cao không làm mất đi sự thật rằng một khóa duy nhất chiếm 35% bảng.

Nếu bảng sessions cũng có nhiều hàng cho customer_id đó, join theo customer_id có thể tạo ra lượng kết quả rất lớn. Nếu hai phía đều có hàng triệu hàng cho cùng khóa, công việc tạo kết quả có thể vượt xa chi phí xây dựng hash table.

## 8. Tại sao thống kê có thể che khuất skew?

Optimizer thường dùng số hàng, NDV, histogram, most common values (MCV) và các thống kê khác để dự đoán cardinality. Nếu thống kê không cập nhật hoặc không giữ đủ thông tin về giá trị phổ biến, optimizer có thể giả định phân bố đều hoặc đánh giá thấp hot key.

Các nguyên nhân thường gặp:

- Thống kê được thu thập trước khi dữ liệu thay đổi lớn.
- Mẫu thống kê bỏ sót giá trị hiếm nhưng có tần suất cao trong một phân vùng.
- Số bucket hoặc statistics target không đủ để mô tả độ lệch.
- Khóa join gồm nhiều cột nhưng thống kê từng cột riêng lẻ không mô tả được tương quan.
- Dữ liệu mới nằm ngoài phạm vi histogram.
- Phân bố khác nhau đáng kể giữa các tenant, vùng hoặc khoảng thời gian.
- Optimizer dùng giả định độc lập cho các predicate hoặc giả định khóa có phân bố gần đều.

Kiểm tra estimated rows và actual rows ở cả hai đầu vào của Hash Join. Nếu build side được ước lượng thấp, hash table có thể vượt bộ nhớ. Nếu số hàng mỗi phía gần đúng nhưng một khóa tạo lượng kết quả quá lớn, vấn đề có thể nằm ở phân bố khóa và join multiplicity.

Thống kê MCV có thể giúp nhận diện giá trị phổ biến. Thống kê nhiều cột có thể mô tả NDV tổ hợp hoặc một số phụ thuộc giữa cột nếu hệ quản trị hỗ trợ. Tuy nhiên, thống kê không tự loại bỏ hot key và không làm giảm số hàng kết quả hợp lệ của phép join.

## 9. Các biện pháp giảm spill do bộ nhớ

Biện pháp phù hợp phụ thuộc vào lý do hash table vượt giới hạn.

### 9.1. Giảm số hàng ở build side

Đẩy điều kiện lọc xuống trước Hash Join khi ngữ nghĩa cho phép. Chỉ đọc những hàng cần thiết cho kết quả:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.region_id = 7
  AND c.is_active = TRUE;
~~~

Nếu điều kiện lọc trên customers có thể áp dụng trước khi xây dựng hash table, số hàng build có thể giảm. Optimizer thường tự đẩy predicate khi có thể, nhưng hàm, subquery, outer join hoặc điều kiện phụ thuộc có thể giới hạn phép biến đổi. Hãy xác nhận trong kế hoạch.

### 9.2. Giảm độ rộng hàng

Không chọn các cột không cần thiết ở phía build. Ví dụ, thay SELECT * bằng danh sách cột cần dùng. Nếu hash join chỉ cần customer_id để đối chiếu và một vài cột để trả kết quả, việc mang theo payload lớn không cần thiết có thể làm tăng memory footprint.

~~~sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Một số optimizer có thể tự loại bỏ cột không cần thiết; việc viết rõ danh sách cột vẫn giúp tránh truyền dữ liệu lớn không cần thiết qua các operator.

### 9.3. Kiểm tra lại thứ tự join và build side

Build side thường nên là tập dữ liệu nhỏ hơn sau khi lọc, nhưng quyết định thực tế do optimizer và ngữ nghĩa phép nối chi phối. Hãy xem nhánh dưới Hash trong kế hoạch, số hàng và độ rộng của nó. Nếu optimizer chọn build side lớn do thống kê sai, cập nhật thống kê hoặc cải thiện ước lượng có thể giúp lựa chọn tốt hơn.

Không ép đổi build side hoặc join order bằng hint trước khi có bằng chứng. Hint có thể hữu ích trong một số tình huống đã được kiểm chứng, nhưng có thể trở nên bất lợi khi dữ liệu thay đổi.

### 9.4. Cân nhắc ngân sách bộ nhớ

Nếu kế hoạch đúng, build side thực sự cần nhiều bộ nhớ và máy chủ còn đủ RAM, có thể đánh giá tăng memory grant hoặc giới hạn bộ nhớ cho thao tác phù hợp. Cần kiểm tra số truy vấn đồng thời, số operator cần bộ nhớ và mức sử dụng RAM của toàn hệ thống.

Với PostgreSQL, điều chỉnh work_mem hoặc hash_mem_multiplier cần xét phạm vi cấu hình, số operator và parallel workers. Với SQL Server, kiểm tra memory grant, Resource Governor nếu được sử dụng và memory grant feedback. Với Oracle, kiểm tra PGA workarea policy và áp lực temporary tablespace. Với MySQL, xem cơ chế và giới hạn của phiên bản đang dùng.

Không tăng bộ nhớ toàn cục chỉ vì một truy vấn spill. Một thay đổi có thể giúp truy vấn đơn lẻ nhưng gây cạn RAM khi nhiều truy vấn đồng thời.

### 9.5. Xem lại chiến lược truy cập dữ liệu

Nếu một đầu vào có thể thu hẹp rất mạnh bằng chỉ mục, optimizer có thể chọn một kế hoạch khác. Tuy nhiên, index không tự động loại bỏ nhu cầu Hash Join; một truy vấn cần kết hợp hai tập lớn vẫn có thể cần hash. Hãy so sánh Nested Loop, Merge Join và Hash Join theo cardinality, thứ tự dữ liệu, chỉ mục và chi phí thực tế.

## 10. Các biện pháp xử lý key skew

Skew cần được xử lý theo nguyên nhân và ngữ nghĩa nghiệp vụ. Tăng bộ nhớ đơn thuần có thể giảm spill nhưng không loại bỏ mất cân bằng hoặc số hàng kết quả quá lớn.

### 10.1. Dùng đầy đủ khóa join

Nếu customer_id chỉ duy nhất trong phạm vi tenant, join chỉ bằng customer_id có thể kết hợp dữ liệu của các tenant khác nhau và tạo kết quả thừa:

~~~sql
-- Có thể thiếu thành phần khóa nếu customer_id chỉ duy nhất theo tenant
ON events.customer_id = profiles.customer_id

-- Nếu quan hệ nghiệp vụ xác định khóa gồm cả hai cột
ON events.tenant_id = profiles.tenant_id
AND events.customer_id = profiles.customer_id
~~~

Chỉ bổ sung tenant_id khi đó thực sự là một phần của khóa nghiệp vụ. Không thêm điều kiện chỉ để giảm số hàng nếu điều kiện đó thay đổi ý nghĩa quan hệ.

### 10.2. Giảm dữ liệu trước khi join

Nếu chỉ cần tổng hợp theo customer_id, có thể tổng hợp trước khi join thay vì kết hợp mọi hàng chi tiết:

~~~sql
WITH event_counts AS (
    SELECT customer_id, COUNT(*) AS event_count
    FROM events
    WHERE event_time >= TIMESTAMP '2026-01-01 00:00:00'
    GROUP BY customer_id
)
SELECT p.customer_id, p.customer_name, e.event_count
FROM profiles AS p
JOIN event_counts AS e
  ON e.customer_id = p.customer_id;
~~~

Việc tổng hợp trước chỉ tương đương khi yêu cầu nghiệp vụ cần kết quả tổng hợp đó. Nếu cần từng cặp event và profile, không thể thay bằng số đếm mà vẫn giữ nguyên kết quả.

### 10.3. Dùng EXISTS khi chỉ cần kiểm tra sự tồn tại

Nếu mục tiêu là tìm profile có ít nhất một event, JOIN có thể tạo nhiều hàng lặp:

~~~sql
SELECT p.customer_id, p.customer_name
FROM profiles AS p
WHERE EXISTS (
    SELECT 1
    FROM events AS e
    WHERE e.customer_id = p.customer_id
);
~~~

EXISTS thể hiện yêu cầu tồn tại và optimizer có thể dùng semi join. Nó tránh yêu cầu phát ra mọi cặp hàng khớp. Chỉ dùng khi kết quả nghiệp vụ cần mỗi profile một lần.

### 10.4. Xử lý hot key riêng khi có thể bảo toàn ngữ nghĩa

Một số workload có vài khóa cực nóng. Có thể tách tập khóa phổ biến thành một nhánh xử lý riêng và xử lý phần còn lại bằng nhánh khác, nhưng cách này phức tạp và cần tránh trùng hoặc bỏ sót hàng.

Ví dụ khái niệm:

1. Xác định tập hot key từ thống kê hoặc đo đạc.
2. Viết nhánh xử lý hot key với chiến lược phù hợp, có thể pre-aggregate hoặc phân vùng theo một thuộc tính bổ sung nếu nghiệp vụ cho phép.
3. Viết nhánh xử lý các key còn lại.
4. Kết hợp kết quả bằng UNION ALL khi hai tập được chứng minh không giao nhau.
5. Kiểm tra kết quả trên dữ liệu có hot key và dữ liệu thông thường.

Không tự ý chia một khóa nóng thành nhiều khóa giả bằng cách thêm salt nếu phía đối diện không được nhân bản hoặc phân phối tương ứng. Salting chỉ là kỹ thuật phân tán cần thiết kế hai phía và logic loại trùng cẩn thận; áp dụng sai sẽ làm mất hoặc nhân bản kết quả.

### 10.5. Phân vùng và phân phối song song

Nếu dữ liệu được partition theo một thuộc tính có tương quan với workload, partition pruning hoặc partition-wise join có thể giảm dữ liệu cần xử lý. Tuy nhiên, nếu một partition chứa phần lớn hot key, phân vùng không cân bằng có thể chỉ chuyển skew sang tầng lưu trữ.

Trong hệ phân tán, có thể phân phối theo composite key, salting hoặc xử lý hot key riêng. Cần cân nhắc chi phí shuffle, nhân bản dữ liệu, tính nhất quán và lượng kết quả. Với một máy chủ quan hệ đơn lẻ, không nên mặc định các kỹ thuật phân tán đều có ích.

## 11. Parallel Hash Join và worker imbalance

Song song hóa có thể tăng throughput khi mỗi worker xử lý phần dữ liệu tương đối cân bằng. Nếu khóa phân bố lệch, một worker có thể nhận nhiều hàng hoặc tạo nhiều kết quả hơn. Những worker khác hoàn tất sớm nhưng truy vấn vẫn phải chờ worker chậm nhất.

Các dấu hiệu:

- Số hàng hoặc thời gian xử lý khác biệt lớn giữa workers.
- Một partition có số hàng hoặc kích thước lớn hơn đáng kể.
- Thời gian chờ ở bước gather/exchange tăng.
- Hash partition hoặc batch nóng có nhiều I/O hơn phần còn lại.
- CPU của một worker cao kéo dài trong khi các worker khác nhàn rỗi.

Hãy xem thống kê per-worker nếu hệ quản trị cung cấp. Với PostgreSQL, EXPLAIN ANALYZE có thể hiển thị thông tin worker và số liệu theo worker cho kế hoạch song song. Với SQL Server, actual plan có thể cho thấy phân phối hàng và cảnh báo parallelism. Tên thuộc tính thay đổi theo phiên bản.

Không phải mọi chênh lệch worker đều do key skew. Dữ liệu phân vùng không đều, độ rộng hàng, predicate khác nhau, I/O chậm hoặc scheduling cũng có thể tạo mất cân bằng. Cần đối chiếu số hàng, thời gian, tài nguyên và partition key.

## 12. Ví dụ điều tra Hash Join spill và skew

Giả sử hệ thống phân tích hoạt động người dùng có hai bảng:

- events: nhiều hàng cho mỗi customer_id.
- sessions: nhiều hàng cho mỗi customer_id.

Truy vấn:

~~~sql
SELECT e.customer_id, e.event_id, s.session_id
FROM events AS e
JOIN sessions AS s
  ON s.customer_id = e.customer_id
WHERE e.event_time >= TIMESTAMP '2026-10-01 00:00:00';
~~~

Actual plan cho thấy Hash Join có nhiều batch và temp I/O tăng. Đồng thời, một số worker xử lý lâu hơn nhiều.

Quy trình điều tra:

1. **Kiểm tra build side.** Xác định nhánh được đưa vào Hash, số hàng ước lượng/thực tế và độ rộng hàng.
2. **Kiểm tra spill.** Xem Batches, Memory Usage, temp read/write hoặc spill warning tùy DBMS.
3. **Kiểm tra cardinality.** Nếu actual rows phía build cao hơn estimate nhiều lần, kiểm tra thống kê và điều kiện lọc theo event_time.
4. **Đo tần suất khóa.** Lấy top customer_id ở cả events và sessions trong cùng phạm vi thời gian.
5. **Tính join multiplicity.** Với các khóa phổ biến, ước lượng L(k) × R(k) để biết liệu số hàng kết quả có tự nó quá lớn không.
6. **Kiểm tra worker distribution.** Xác định worker chậm có xử lý khóa hoặc partition nóng hay đang chịu I/O khác biệt.
7. **Đặt giả thuyết riêng.** Ví dụ: “Spill do build side rộng và ước lượng thấp”; “một customer_id chiếm tỷ lệ lớn ở cả hai bảng”; hoặc “predicate thời gian không thu hẹp dữ liệu trước khi hash”.
8. **Thử thay đổi có kiểm soát.** Có thể giảm cột mang theo, lọc sớm, cập nhật thống kê, dùng khóa join đầy đủ, pre-aggregate nếu đúng nghiệp vụ hoặc điều chỉnh memory grant trong giới hạn an toàn.
9. **Đo lại.** So sánh số batch, temp I/O, memory, thời gian, CPU, worker imbalance và số hàng kết quả. Xác nhận tập kết quả không đổi.

Nếu spill giảm sau khi tăng bộ nhớ nhưng worker imbalance vẫn lớn, nguyên nhân skew vẫn còn. Nếu số batch giảm nhưng số hàng đầu ra vẫn khổng lồ do L(k) × R(k), cần xem lại yêu cầu join hoặc khả năng giảm dữ liệu trước join. Nếu estimated rows vẫn sai, cần tiếp tục sửa thống kê hoặc mô hình ước lượng.

## 13. Những sai lầm thường gặp

- **Thấy Hash Join là kết luận thiếu chỉ mục.** Hash Join có thể là thuật toán tốt nhất cho hai tập dữ liệu lớn.
- **Thấy nhiều batch là kết luận key skew.** Nhiều batch thường phản ánh giới hạn bộ nhớ; skew là một nguyên nhân khác có thể làm phân bố batch mất cân bằng.
- **Tăng bộ nhớ mà không xem concurrency.** Nhiều truy vấn đồng thời có thể nhân mức sử dụng RAM.
- **Chỉ xem NDV.** NDV cao không chứng minh phân phối đều; cần MCV hoặc tần suất top key.
- **Chỉ đo khóa ở một phía.** Skew và join multiplicity phụ thuộc tần suất ở cả hai phía.
- **Bỏ qua số hàng đầu ra.** Hash table có thể nhỏ nhưng join vẫn tạo lượng kết quả rất lớn.
- **Thêm cột vào khóa join mà không kiểm tra nghiệp vụ.** Điều kiện mới có thể làm mất kết quả hợp lệ.
- **Dùng EXISTS thay JOIN dù cần từng cặp hàng.** Hai dạng có ngữ nghĩa khác nhau.
- **Salting khóa nóng một phía.** Nếu không xử lý phía còn lại và bảo toàn kết quả, kỹ thuật có thể làm mất hoặc nhân bản hàng.
- **Coi memory grant feedback là giải pháp đầy đủ.** Cơ chế tự điều chỉnh grant không sửa mọi lỗi thống kê, parameter sensitivity hoặc skew.
- **Cộng thời gian các operator.** Thời gian ở nút cha có thể bao gồm thời gian nút con; hãy dùng tổng thời gian truy vấn và số liệu từng operator theo đúng quy ước.

## 14. Checklist chẩn đoán và xác minh

- [ ] Đã xác định đúng Hash node/build side và probe side.
- [ ] Đã so sánh estimated rows với actual rows ở cả hai đầu vào.
- [ ] Đã kiểm tra độ rộng hàng và các cột thực sự cần cho join.
- [ ] Đã xem số bucket, batch, memory usage và temp I/O hoặc spill warning.
- [ ] Đã phân biệt spill do thiếu ngân sách với skew do phân bố khóa.
- [ ] Đã đo top key và tần suất ở cả hai phía join.
- [ ] Đã kiểm tra NDV, MCV, histogram, thống kê nhiều cột và độ mới của thống kê.
- [ ] Đã ước lượng join multiplicity cho các khóa phổ biến.
- [ ] Đã kiểm tra worker/partition imbalance nếu có parallelism.
- [ ] Đã xem xét lọc sớm, giảm row width, pre-aggregate hoặc EXISTS chỉ khi ngữ nghĩa cho phép.
- [ ] Đã đánh giá memory grant cùng số truy vấn đồng thời và giới hạn RAM.
- [ ] Đã đo lại thời gian, CPU, I/O tạm, số batch, độ trễ và workload liên quan.
- [ ] Đã xác nhận kết quả truy vấn và tính đúng đắn dữ liệu không thay đổi.

Hash Join spill cho biết bảng băm hoặc quá trình xử lý vượt ngân sách bộ nhớ và phải dùng dữ liệu tạm; key skew cho biết một số khóa tạo ra phân bố công việc không cân bằng. Chẩn đoán đúng cần xem build side, cardinality, row width, batch, temp I/O, tần suất khóa ở cả hai phía và số hàng kết quả theo từng khóa. Khi điều chỉnh lọc, thống kê, cấu trúc join hoặc ngân sách bộ nhớ, hãy đo lại trong điều kiện tải tương đương và kiểm tra ngữ nghĩa kết quả. Nhờ đó, thay đổi hiệu năng được chứng minh bằng dữ liệu thay vì chỉ dựa vào việc Hash Join biến mất hoặc số batch giảm.
