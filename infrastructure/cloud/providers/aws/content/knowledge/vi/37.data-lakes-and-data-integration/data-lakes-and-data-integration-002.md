# Phân vùng dữ liệu và định dạng Parquet, ORC

Một data lake trên Amazon S3 có thể chứa hàng tỷ bản ghi từ giao dịch, ứng dụng, thiết bị và hệ thống phân tích. Nếu mỗi truy vấn phải liệt kê và đọc toàn bộ object, thời gian xử lý và chi phí scan sẽ tăng nhanh. Hai kỹ thuật quan trọng giúp tổ chức dữ liệu hiệu quả là **partitioning** và **columnar storage**.

**Partitioning** chia dataset thành các nhóm vật lý theo những thuộc tính thường được dùng để lọc, chẳng hạn ngày, khu vực hoặc loại sự kiện. Query engine có thể bỏ qua partition không liên quan thay vì đọc tất cả dữ liệu. **Apache Parquet** và **Apache ORC** là các định dạng lưu trữ dạng cột, cho phép engine chỉ đọc những cột và block cần thiết, đồng thời tận dụng encoding, compression và statistics để giảm I/O.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, các kỹ thuật này thường được dùng cùng Amazon S3, AWS Glue Data Catalog, AWS Glue ETL, Amazon Athena, Amazon EMR và các công cụ phân tích khác. Người học cần biết cách chọn partition key, tổ chức S3 prefix, chọn Parquet hay ORC, quản lý metadata, xử lý small files và kiểm chứng hiệu năng. Mục tiêu là xây dựng data lake có thể mở rộng, dễ truy vấn, an toàn và kiểm soát được chi phí.

## 1. Vì sao phải partition dữ liệu?

Giả sử bảng giao dịch có 5 TB dữ liệu trong S3. Người dùng thường truy vấn doanh thu của một ngày hoặc một tháng. Nếu dữ liệu không được phân vùng, Athena có thể phải đọc một lượng lớn file để tìm những bản ghi trong khoảng thời gian đó. Nếu dataset được phân vùng theo năm, tháng và ngày, truy vấn có điều kiện thời gian có thể chỉ đọc các prefix phù hợp.

Partitioning có ba lợi ích chính:

- **Giảm dữ liệu phải scan:** query engine loại bỏ partition không khớp điều kiện lọc.
- **Tổ chức dữ liệu:** dữ liệu được chia thành các vùng dễ quản lý theo thời gian, tenant, khu vực hoặc loại nghiệp vụ.
- **Hỗ trợ lifecycle và vận hành:** có thể áp dụng retention, archive hoặc xử lý lại theo từng nhóm dữ liệu.

Partitioning cũng có chi phí. Quá nhiều partition làm tăng số object, metadata và thời gian lập kế hoạch query. Quá ít partition khiến query phải đọc nhiều dữ liệu không cần thiết. Mục tiêu là chọn mức phân vùng phù hợp với cách truy vấn thực tế.

## 2. Partition key là gì?

Partition key là thuộc tính dùng để chia dataset thành các partition. Trong Hive-style layout thường dùng với Athena và Glue, giá trị partition được biểu diễn trong đường dẫn S3 theo dạng key=value.

Ví dụ dataset orders được phân vùng theo năm, tháng và ngày:

~~~text
s3://company-data-lake/curated/orders/
  year=2026/
    month=11/
      day=20/
        part-00000.parquet
        part-00001.parquet
~~~

Các partition key có thể được chọn từ cột sẵn có hoặc được tạo trong quá trình ETL. Ví dụ, từ cột event_timestamp có thể tạo các cột year, month và day. Khi query, engine dùng điều kiện trên các cột partition để xác định prefix cần đọc.

### Partition key tốt thường có đặc điểm

- Xuất hiện thường xuyên trong điều kiện lọc của query.
- Có cardinality thấp hoặc vừa phải.
- Chia dữ liệu thành các nhóm có kích thước đủ lớn.
- Ít thay đổi và có quy tắc chuẩn hóa rõ ràng.
- Phù hợp với retention và cách nạp dữ liệu.

Ngày, tháng, khu vực, loại sự kiện hoặc business unit thường là ứng viên tốt. User ID, order ID hoặc session ID thường có cardinality quá cao để làm partition key chính.

## 3. Cardinality và trade-off giữa quá nhiều với quá ít partition

Cardinality là số lượng giá trị khác nhau của một thuộc tính. Nếu partition theo ngày, một năm có khoảng 365 giá trị. Nếu partition theo customer_id với hàng triệu khách hàng, số partition có thể tăng tới hàng triệu.

| Thiết kế | Hệ quả thường gặp |
|---|---|
| Không partition | Query có thể scan nhiều dữ liệu; ít metadata partition |
| Partition theo năm | Ít partition nhưng query theo ngày vẫn đọc nhiều dữ liệu |
| Partition theo năm/tháng/ngày | Hữu ích cho query theo thời gian, nhưng số partition tăng theo thời gian |
| Partition theo customer_id | Cardinality cao, tạo nhiều partition nhỏ và metadata lớn |
| Partition theo ngày và region | Có thể cân bằng nếu query thường lọc theo cả hai thuộc tính |

Không có một số lượng partition tối ưu áp dụng cho mọi dataset. Hãy ước tính số partition theo thời gian lưu trữ, số giá trị của mỗi key và lượng dữ liệu trung bình mỗi partition.

Ví dụ, nếu một ngày chỉ có 20 MB dữ liệu nhưng lại tạo hàng nghìn partition theo customer, hệ thống sẽ sinh nhiều file nhỏ. Chi phí metadata, listing và scheduling có thể lớn hơn lợi ích của partition pruning.

## 4. Chọn partition key theo query pattern

Không chọn partition key chỉ vì cột đó tồn tại trong schema. Hãy phân tích các truy vấn thường gặp:

| Query pattern | Partition key có thể cân nhắc |
|---|---|
| Báo cáo doanh thu theo ngày | year, month, day |
| Phân tích theo quốc gia | country hoặc region |
| Theo dõi loại sự kiện | event_type nếu số loại hữu hạn |
| Báo cáo theo business unit | business_unit nếu số đơn vị vừa phải |
| Truy vấn khách hàng cụ thể | Không nhất thiết partition theo customer_id; cân nhắc bucketing, sort hoặc index phù hợp |
| Kết hợp thời gian và khu vực | year/month/day + region nếu số tổ hợp và kích thước partition hợp lý |

Một quy trình thực tế:

1. Thu thập query log và xác định các predicate thường dùng.
2. Xếp hạng thuộc tính theo tần suất lọc và mức giảm dữ liệu dự kiến.
3. Ước tính cardinality và kích thước dữ liệu cho mỗi partition.
4. Tạo thử layout trên một tập dữ liệu đại diện.
5. Chạy benchmark với query thực tế.
6. Theo dõi số partition, số file và thời gian lập kế hoạch query.

Nếu người dùng thường truy vấn khoảng thời gian 7 ngày và khu vực, partition theo date và region có thể hữu ích. Nhưng nếu mỗi ngày có hàng trăm khu vực rất nhỏ, cần xem xét chỉ partition theo date rồi dùng sort/order hoặc bucketing cho region.

## 5. Partition pruning hoạt động như thế nào?

Partition pruning là quá trình query engine loại bỏ các partition không cần thiết dựa trên predicate của query. Ví dụ bảng có partition key year, month và day; query lọc đúng một ngày có thể chỉ đọc prefix tương ứng.

~~~sql
SELECT
    region,
    SUM(total_amount) AS revenue
FROM curated_orders
WHERE year = '2026'
  AND month = '11'
  AND day = '20'
GROUP BY region;
~~~

Nếu bảng được partition đúng và metadata sẵn sàng, Athena có thể chỉ đọc dữ liệu trong partition năm 2026, tháng 11, ngày 20. Nếu query chỉ lọc cột event_timestamp nhưng không lọc các partition key, Hive-style table không tự suy ra quan hệ giữa timestamp và các partition key. Khi đó query có thể đọc nhiều partition hơn cần thiết.

Ví dụ, nếu event_timestamp nằm trong ngày 20 tháng 11 nhưng bảng partition theo year/month/day, query nên có cả điều kiện partition và điều kiện timestamp:

~~~sql
SELECT COUNT(*)
FROM curated_orders
WHERE year = '2026'
  AND month = '11'
  AND day = '20'
  AND event_timestamp >= TIMESTAMP '2026-11-20 10:00:00'
  AND event_timestamp <  TIMESTAMP '2026-11-20 12:00:00';
~~~

Điều kiện timestamp bảo đảm logic nghiệp vụ chính xác; điều kiện partition giúp Athena loại bỏ prefix không liên quan.

### Partition key trong Glue/Athena thường dùng kiểu STRING

AWS khuyến nghị dùng kiểu STRING cho partition key của Hive-style table trong Athena để tối ưu xử lý partition. Giá trị như năm, tháng và ngày vẫn có thể biểu diễn dưới dạng chuỗi có padding, ví dụ month='03'. Cột dữ liệu nghiệp vụ gốc có thể giữ kiểu DATE hoặc TIMESTAMP riêng.

## 6. Quản lý partition metadata bằng AWS Glue Data Catalog

AWS Glue Data Catalog lưu metadata về database, table, schema, location và partition. Athena sử dụng metadata này để xác định file nào thuộc table và partition nào cần đọc.

Có nhiều cách quản lý partition:

- Tạo partition bằng Glue API hoặc Athena DDL.
- Dùng AWS Glue crawler để phát hiện schema và partition.
- Dùng CTAS để tạo table và partition cùng lúc.
- Dùng partition projection trong Athena để tính partition từ table properties thay vì đăng ký từng partition.

Crawler thuận tiện cho việc khám phá dữ liệu, nhưng không phải lúc nào cũng là lựa chọn tốt nhất cho pipeline production. Với schema và layout đã biết, việc quản lý metadata tường minh trong ETL hoặc Glue API có thể dễ kiểm soát hơn.

### MSCK REPAIR TABLE

Với Hive-style partition layout, Athena có lệnh MSCK REPAIR TABLE để phát hiện partition mới trong S3 và thêm metadata vào Glue Data Catalog.

~~~sql
MSCK REPAIR TABLE curated_orders;
~~~

Lệnh này có giới hạn:

- Có thể mất nhiều thời gian khi có nhiều prefix.
- Chủ yếu thêm partition mới; không tự xóa metadata partition cũ đã bị xóa khỏi S3.
- Có thể quét cả folder con và vô tình phát hiện partition của dataset khác nếu dùng chung prefix.
- Có hạn chế về cách viết hoa/thường và cấu trúc S3 path.

Với dataset lớn, cân nhắc quản lý partition qua Glue API, crawler có kiểm soát, partition index hoặc projection thay vì chạy MSCK REPAIR TABLE thường xuyên.

## 7. Glue partition indexes và partition projection

Khi bảng có hàng chục nghìn hoặc nhiều partition, việc lấy metadata từ Glue Data Catalog có thể trở thành phần đáng kể trong thời gian lập kế hoạch query. AWS có hai cơ chế cần phân biệt:

| Cơ chế | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Glue partition index | Tạo index trên các partition key để lọc tập con partition trong Data Catalog | Bảng có partition đã đăng ký và cần tối ưu GetPartitions |
| Athena partition projection | Khai báo quy tắc/range partition trong table properties để Athena tự tính partition | Dataset có quy luật partition rõ ràng, đặc biệt khi số partition lớn |

### Glue partition index

Partition index được tạo trên một thứ tự các partition key. Khi GetPartitions có expression phù hợp và dùng key đầu tiên của index, Glue có thể lấy subset partition thay vì tải toàn bộ danh sách. Tối đa ba partition index có thể được tạo cho một table theo tài liệu Glue hiện hành.

Đối với Athena, cần bật partition filtering trên table bằng property:

~~~sql
ALTER TABLE curated_orders
SET TBLPROPERTIES ('partition_filtering.enabled' = 'true');
~~~

Index cần ở trạng thái ACTIVE và query/filter phải phù hợp với thứ tự key. Đây là tối ưu cho việc truy xuất metadata; nó không thay đổi cách file dữ liệu được partition trên S3.

### Partition projection

Partition projection cho phép Athena tính giá trị và location của partition từ table properties. Ví dụ, bảng có year từ 2020 tới 2030, month từ 01 tới 12 và day từ 01 tới 31. Athena có thể xác định partition cần thiết mà không phải gọi Glue GetPartitions để lấy danh sách đã đăng ký.

Projection có thể giảm thời gian truy xuất metadata và loại bỏ công việc đăng ký partition thủ công. Tuy nhiên, khi bật projection, Athena bỏ qua partition metadata đã đăng ký trong Glue Data Catalog cho table đó. Cấu hình range và template phải khớp layout S3.

Projection có thể kém hiệu quả với dataset thưa (sparse), tức là nhiều tổ hợp partition được dự đoán nhưng không thực sự có dữ liệu. Vì vậy, không bật projection chỉ vì số partition lớn; cần benchmark với pattern truy vấn thực tế.

## 8. Partitioning khác bucketing như thế nào?

Partitioning chia dữ liệu thành các directory/prefix theo giá trị partition key. Bucketing chia dữ liệu thành số bucket cố định dựa trên hash của một hoặc nhiều cột.

| Tiêu chí | Partitioning | Bucketing |
|---|---|---|
| Cách chia | Theo giá trị key và thường tạo prefix riêng | Theo hash, số bucket được cấu hình |
| Cardinality | Nên thấp hoặc vừa | Có thể dùng cột cardinality cao hơn |
| Mục tiêu | Loại bỏ nhóm dữ liệu không liên quan trước khi đọc file | Phân bố dữ liệu, hỗ trợ một số join/parallel processing |
| Cấu trúc S3 | Thường có key=value directory | File được ghi theo bucket id trong partition |
| Ví dụ | year=2026/month=11 | bucket theo customer_id với 32 bucket |

Không nên tạo partition cho mọi customer_id chỉ để tăng tốc truy vấn khách hàng. Có thể partition theo ngày, sau đó bucketing theo customer_id nếu engine và workload hưởng lợi. Athena hỗ trợ bucketing trong một số định dạng/table type, nhưng cần kiểm tra compatibility và giới hạn CTAS hiện hành.

Với Iceberg table, partition transform như year(timestamp), month(timestamp), day(timestamp) và bucket(column, n) được khai báo qua cơ chế partitioning của Iceberg; không dùng Hive partitioned_by như thể hai mô hình hoàn toàn giống nhau.

## 9. Vấn đề small files

Một dataset có hàng triệu file nhỏ thường truy vấn chậm hơn dự kiến dù tổng dung lượng không lớn. Mỗi file tạo overhead cho listing, metadata, open/close, scheduling và xử lý footer. Với định dạng cột, file quá nhỏ còn làm giảm lợi ích của row group hoặc stripe.

Nguyên nhân thường gặp:

- Streaming hoặc micro-batch ghi file liên tục với batch quá nhỏ.
- Quá nhiều partition, mỗi partition chỉ có vài MB dữ liệu.
- ETL ghi ra nhiều file theo số lượng worker mà không compact.
- INSERT INTO chạy thường xuyên tạo nhiều file nhỏ.

AWS Athena mô tả default Parquet block/row-group size là 128 MB và ORC stripe size là 64 MB. Đây là kích thước cấu trúc nội bộ, không phải yêu cầu mọi file phải đúng bằng các con số này. Kích thước file mục tiêu thường cần được benchmark; dataset phân tích thường hưởng lợi từ file đủ lớn để giảm overhead nhưng không quá lớn làm giảm parallelism.

### Biện pháp xử lý

1. Gom batch trước khi ghi.
2. Dùng Spark repartition/coalesce hợp lý trước khi write.
3. Compact file nhỏ theo partition.
4. Tránh partition cardinality cao.
5. Theo dõi số file trung bình trên mỗi partition.
6. Dùng Iceberg compaction hoặc cơ chế rewrite data files nếu table format hỗ trợ.

Không compact toàn bộ data lake mỗi lần nạp dữ liệu. Xử lý theo partition hoặc khoảng thời gian bị ảnh hưởng để kiểm soát chi phí và tránh ghi lại dữ liệu không cần thiết.

## 10. Định dạng columnar storage là gì?

Định dạng row-oriented lưu các trường của một bản ghi gần nhau. Định dạng columnar lưu giá trị theo từng cột hoặc nhóm cột. Với truy vấn phân tích thường chỉ đọc một phần schema, columnar storage có thể giảm lượng dữ liệu phải đọc và giải nén.

Ví dụ bảng orders có các cột:

| order_id | customer_id | order_date | region | total_amount | status |
|---|---|---|---|---:|---|
| O-001 | C-01 | 2026-11-20 | north | 120.50 | PAID |
| O-002 | C-02 | 2026-11-20 | south | 75.00 | PENDING |
| O-003 | C-03 | 2026-11-20 | north | 240.00 | PAID |

Query chỉ cần region và total_amount. Với columnar format, engine có thể đọc các column chunk tương ứng thay vì giải nén toàn bộ order_id, customer_id, order_date và status.

Các lợi ích:

- Column pruning: chỉ đọc cột được query yêu cầu.
- Compression theo cột: giá trị cùng kiểu thường có pattern tương tự và nén tốt.
- Encoding: dictionary, run-length hoặc delta encoding có thể giảm kích thước.
- Statistics: min/max, null count hoặc metadata khác hỗ trợ bỏ qua block không phù hợp.
- Predicate pushdown: điều kiện lọc có thể được áp dụng gần tầng đọc dữ liệu để giảm I/O.

## 11. Apache Parquet là gì?

Apache Parquet là định dạng columnar storage mở, được dùng rộng rãi trong hệ sinh thái Spark, Hadoop, Athena, Glue, Trino và nhiều công cụ phân tích khác. Parquet được thiết kế để lưu schema và dữ liệu theo nhóm cột, hỗ trợ compression và encoding.

### Cấu trúc Parquet

Một file Parquet thường gồm:

- **Row groups:** nhóm các hàng trong file; mỗi row group chứa dữ liệu của nhiều cột.
- **Column chunks:** dữ liệu của một cột trong một row group.
- **Pages:** đơn vị dữ liệu và encoding bên trong column chunk.
- **File metadata/footer:** schema, vị trí row group/column chunk, statistics và metadata khác.

~~~mermaid
flowchart TD
    A[Parquet file] --> B[File metadata / Footer]
    A --> C[Row group 1]
    A --> D[Row group 2]
    C --> E[Column chunk: order_id]
    C --> F[Column chunk: region]
    C --> G[Column chunk: amount]
    E --> H[Pages]
    F --> I[Pages]
    G --> J[Pages]
~~~

Khi query chỉ cần region và amount, engine có thể bỏ qua column chunk của order_id. Statistics trong footer hoặc metadata row group có thể giúp bỏ qua nhóm dữ liệu không thỏa predicate.

### Khi nào Parquet phù hợp?

- Dataset cần chia sẻ giữa nhiều query engine và framework.
- Workload phân tích thường chọn một tập cột từ schema rộng.
- Cần tương thích tốt với Spark, Athena, Glue, EMR và các công cụ khác.
- Có schema phức tạp hoặc nested data cần interoperability.
- Muốn cân bằng compression, scan performance và ecosystem support.

## 12. Apache ORC là gì?

Apache ORC (Optimized Row Columnar) là định dạng columnar được phát triển trong hệ sinh thái Hadoop/Hive. ORC tổ chức dữ liệu theo stripes, có index và statistics để hỗ trợ đọc chọn lọc, compression và predicate filtering.

### Cấu trúc ORC

Một file ORC thường gồm:

- **Stripes:** nhóm hàng được lưu theo cột.
- **Index data:** thông tin phục vụ định vị và bỏ qua dữ liệu không cần thiết.
- **Data streams:** các stream dữ liệu cột đã encode/compress.
- **Stripe footer:** metadata cho từng stripe.
- **File footer và postscript:** schema, danh sách stripe, compression và metadata cấp file.

~~~mermaid
flowchart TD
    A[ORC file] --> B[Postscript]
    A --> C[File footer]
    A --> D[Stripe 1]
    A --> E[Stripe 2]
    D --> F[Stripe index]
    D --> G[Column data streams]
    D --> H[Stripe footer]
    E --> I[Stripe index]
    E --> J[Column data streams]
    E --> K[Stripe footer]
~~~

ORC có index và statistics ở nhiều cấp để engine xác định stripe hoặc vùng dữ liệu cần đọc. Trong một số workload, ORC có thể tạo file nhỏ hơn Parquet và truy vấn nhanh hơn; kết quả phụ thuộc schema, compression, engine và query.

### Khi nào ORC phù hợp?

- Workload dựa nhiều vào Hive hoặc hệ sinh thái Hadoop.
- Dataset có complex types như struct, map và list.
- Benchmark cho thấy ORC giảm dung lượng hoặc scan time tốt hơn.
- Công cụ ETL và query engine trong tổ chức hỗ trợ ORC đầy đủ.

## 13. So sánh Parquet và ORC

| Tiêu chí | Parquet | ORC |
|---|---|---|
| Kiểu lưu trữ | Columnar | Columnar |
| Cấu trúc chính | Row groups, column chunks, pages | Stripes, indexes, data streams |
| Metadata | Footer chứa schema, row group và column metadata | File footer, stripe footer, indexes và postscript |
| Compression | Hỗ trợ nhiều codec, tùy writer/reader | Hỗ trợ nhiều codec, tùy writer/reader |
| Predicate pushdown | Có, dựa trên statistics và metadata | Có, dựa trên indexes và statistics |
| Ecosystem | Rộng, phổ biến trong Spark, Arrow và nhiều engine | Mạnh trong Hive/Hadoop và các engine hỗ trợ ORC |
| Complex/nested types | Hỗ trợ nested schema | Hỗ trợ struct, map, list và complex types |
| File size | Phụ thuộc dữ liệu và codec | Thường có thể nhỏ hơn trong một số workload |
| Lựa chọn | Thường là mặc định an toàn khi cần interoperability rộng | Chọn khi hệ sinh thái hoặc benchmark cho thấy lợi thế |

Không có định dạng thắng trong mọi trường hợp. AWS Athena mô tả ORC thường tạo file nhỏ hơn và ORC indexes có thể tăng tốc query; Parquet hỗ trợ nhiều loại query và tương thích rộng. Cần benchmark trên dữ liệu thật, không chọn dựa trên tên định dạng hoặc một bài benchmark tổng quát.

## 14. Compression và encoding

Compression giảm số byte lưu ở S3 và số byte cần đọc trước khi giải nén. Encoding tận dụng đặc điểm của dữ liệu để biểu diễn hiệu quả hơn trước hoặc cùng compression.

Ví dụ:

- Dictionary encoding: lưu giá trị lặp bằng mã số và dictionary.
- Run-length encoding: lưu chuỗi giá trị giống nhau bằng giá trị và số lần lặp.
- Delta encoding: lưu chênh lệch giữa các giá trị tăng/giảm đều.
- Bit packing: lưu số nguyên trong số bit cần thiết.

### Codec phổ biến trong Athena

| Format | Codec có thể dùng khi ghi qua Athena CTAS | Ghi chú |
|---|---|---|
| Parquet | GZIP, SNAPPY, ZSTD theo hỗ trợ writer hiện hành | GZIP là mặc định CTAS truyền thống; kiểm tra engine/property khi dùng ZSTD |
| ORC | LZ4, SNAPPY, ZLIB, ZSTD | ZLIB là mặc định ORC CTAS |

Compression mạnh hơn thường giảm storage và bytes scanned nhưng có thể tăng CPU khi nén/giải nén. Snappy thường ưu tiên tốc độ; GZIP/ZLIB có thể cho tỷ lệ nén cao hơn; ZSTD có thể cân bằng tốc độ và tỷ lệ nén. Kết quả phụ thuộc dữ liệu, cardinality và engine.

Không dùng codec mà writer và reader trong pipeline không cùng hỗ trợ. Athena có thể đọc một số codec Parquet như LZ4/LZO nhưng không hỗ trợ ghi Parquet với các codec đó theo tài liệu hiện hành.

## 15. Schema evolution

Data lake thường thay đổi schema theo thời gian: thêm cột, đổi kiểu, đổi tên, thay nested structure hoặc bổ sung giá trị enum. Parquet và ORC lưu schema trong file metadata, vì vậy schema evolution cần được quản lý cẩn thận.

Các thay đổi thường gặp:

| Thay đổi | Rủi ro | Hướng xử lý |
|---|---|---|
| Thêm nullable column | File cũ không có cột mới | Kiểm tra cách engine trả NULL cho file cũ |
| Đổi kiểu số | Mất chính xác hoặc cast lỗi | Dùng migration có kiểm thử và kiểm soát precision |
| Đổi tên cột | Reader có thể coi là cột mới | Dùng alias/view hoặc rewrite có kế hoạch |
| Thay nested structure | Reader khác nhau có thể xử lý khác | Version schema và test cross-engine |
| Thay timestamp timezone | Lệch thời gian hoặc partition | Chuẩn hóa UTC và quy tắc chuyển đổi |

Không giả định mọi thay đổi schema đều tương thích ngược. Cần có schema registry hoặc metadata contract, kiểm thử reader/writer và kế hoạch xử lý file cũ. Với Hive-style table, Glue Data Catalog schema có thể cần cập nhật riêng; schema trong catalog và schema thực tế của file phải nhất quán theo quy tắc engine.

## 16. Chọn partition và format cùng nhau

Partitioning và columnar format tối ưu hai tầng khác nhau:

- Partitioning giảm số prefix hoặc nhóm file phải xét.
- Columnar format giảm số cột và block cần đọc bên trong file được chọn.

Ví dụ query doanh thu một ngày, một khu vực:

~~~sql
SELECT region, SUM(total_amount)
FROM orders
WHERE year = '2026'
  AND month = '11'
  AND day = '20'
  AND region = 'north'
GROUP BY region;
~~~

Partition theo ngày có thể giảm số folder cần đọc. Parquet/ORC cho phép engine chỉ đọc region và total_amount, đồng thời dùng statistics để bỏ qua row group/stripe không phù hợp.

Không nên partition theo mọi cột trong WHERE. Một cột có cardinality cao có thể tốt hơn khi nằm trong file để engine lọc bằng statistics hoặc bucketing. Thiết kế phải cân bằng số partition, kích thước file và khả năng pruning.

## 17. Tạo Parquet partitioned table bằng Athena CTAS

Athena CTAS có thể chuyển dữ liệu từ CSV/JSON sang Parquet, nén và partition trong một truy vấn.

Ví dụ nguồn raw_orders có cột order_id, event_timestamp, region và total_amount:

~~~sql
CREATE TABLE curated_orders_parquet
WITH (
    format = 'PARQUET',
    write_compression = 'SNAPPY',
    partitioned_by = ARRAY['year', 'month', 'day'],
    external_location = 's3://company-data-lake/curated/orders-parquet/'
)
AS
SELECT
    order_id,
    event_timestamp,
    region,
    total_amount,
    CAST(year(event_timestamp) AS VARCHAR) AS year,
    LPAD(CAST(month(event_timestamp) AS VARCHAR), 2, '0') AS month,
    LPAD(CAST(day(event_timestamp) AS VARCHAR), 2, '0') AS day
FROM raw_orders;
~~~

Lưu ý quan trọng:

- Các partition columns phải nằm cuối danh sách SELECT theo đúng thứ tự khai báo trong partitioned_by.
- Athena CTAS giới hạn 100 partition/bucket combinations được tạo trong một query. Nếu dữ liệu vượt giới hạn, chia thành nhiều batch hoặc dùng quy trình ETL phù hợp.
- external_location phải là prefix S3 chưa chứa dữ liệu đích theo điều kiện CTAS.
- Tên database/table và location cần tuân thủ quy ước của tổ chức.
- Query trên là ví dụ; kiểm tra kiểu dữ liệu và hàm date theo engine version đang sử dụng.

Sau khi chạy CTAS, Athena tạo file và đăng ký table/partition metadata trong Glue Data Catalog.

## 18. Tạo ORC partitioned table bằng Athena CTAS

Để ghi cùng dataset dưới dạng ORC:

~~~sql
CREATE TABLE curated_orders_orc
WITH (
    format = 'ORC',
    write_compression = 'ZSTD',
    partitioned_by = ARRAY['year', 'month', 'day'],
    external_location = 's3://company-data-lake/curated/orders-orc/'
)
AS
SELECT
    order_id,
    event_timestamp,
    region,
    total_amount,
    CAST(year(event_timestamp) AS VARCHAR) AS year,
    LPAD(CAST(month(event_timestamp) AS VARCHAR), 2, '0') AS month,
    LPAD(CAST(day(event_timestamp) AS VARCHAR), 2, '0') AS day
FROM raw_orders;
~~~

CTAS dùng write_compression để chỉ định codec. Với ORC, ZLIB là mặc định nếu không chỉ định; với Parquet, GZIP là mặc định theo tài liệu Athena CTAS. Có thể dùng SNAPPY hoặc ZSTD khi phù hợp và được writer hỗ trợ.

Không ghi Parquet và ORC vào cùng prefix. Mỗi table nên có location riêng để tránh crawler hoặc query engine đọc nhầm file có định dạng khác.

## 19. Query và kiểm tra partition pruning

Query nên lọc trực tiếp partition key:

~~~sql
SELECT
    region,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM curated_orders_parquet
WHERE year = '2026'
  AND month = '11'
  AND day BETWEEN '01' AND '07'
GROUP BY region;
~~~

Kiểm tra danh sách partition:

~~~sql
SHOW PARTITIONS curated_orders_parquet;
~~~

Kiểm tra query plan hoặc thông tin query execution trong Athena để xác định số bytes scanned và partition được chọn. So sánh với query không có partition predicate để thấy mức giảm dữ liệu.

### Tránh predicate không phù hợp

Nếu partition key là chuỗi year/month/day, đừng chỉ lọc một biểu thức trên timestamp gốc và mong Athena tự suy ra partition. Hãy thêm điều kiện partition tương ứng. Đảm bảo format giá trị thống nhất, ví dụ month luôn có hai chữ số để tránh partition '2' và '02' bị tách thành hai nhóm.

## 20. Partition projection cho dataset theo thời gian

Với dataset theo thời gian có quy luật rõ ràng, partition projection có thể giảm chi phí metadata. Ví dụ table có year từ 2024 tới 2030, month từ 01 tới 12 và day từ 01 tới 31.

Table properties minh họa:

~~~sql
ALTER TABLE curated_orders_parquet
SET TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.year.type' = 'integer',
  'projection.year.range' = '2024,2030',
  'projection.month.type' = 'integer',
  'projection.month.range' = '1,12',
  'projection.month.digits' = '2',
  'projection.day.type' = 'integer',
  'projection.day.range' = '1,31',
  'projection.day.digits' = '2',
  'storage.location.template' = 's3://company-data-lake/curated/orders-parquet/year=${year}/month=${month}/day=${day}/'
);
~~~

Các property trên chỉ là minh họa cấu hình; template phải khớp chính xác layout thực tế và kiểu/range partition. Projection tính cả những tổ hợp partition không tồn tại, vì vậy có thể kém hiệu quả với dataset sparse hoặc dữ liệu không đều. Khi bật projection, Athena bỏ qua partition metadata đã đăng ký trong Glue Catalog cho table.

## 21. AWS Glue ETL và compact file

AWS Glue ETL có thể đọc dữ liệu raw, chuẩn hóa schema, tạo partition columns và ghi Parquet/ORC lên S3. Với Spark, cần cân nhắc số partition của DataFrame, số output file và cách phân bố dữ liệu.

Ví dụ PySpark minh họa:

~~~python
from pyspark.sql import functions as F

source = spark.read.json("s3://company-data-lake/raw/orders/")

curated = (
    source
    .withColumn("event_date", F.to_date("event_timestamp"))
    .withColumn("year", F.date_format("event_date", "yyyy"))
    .withColumn("month", F.date_format("event_date", "MM"))
    .withColumn("day", F.date_format("event_date", "dd"))
    .select(
        "order_id",
        "event_timestamp",
        "region",
        "total_amount",
        "year",
        "month",
        "day"
    )
)

(
    curated
    .repartition("year", "month", "day")
    .write
    .mode("append")
    .format("parquet")
    .option("compression", "snappy")
    .partitionBy("year", "month", "day")
    .save("s3://company-data-lake/curated/orders/")
)
~~~

Ví dụ cần được điều chỉnh theo Glue version, Spark configuration và kích thước dữ liệu. repartition theo key có thể gây shuffle lớn hoặc skew; không nên áp dụng mù quáng. Có thể repartition theo số lượng file mục tiêu, dùng coalesce khi giảm partition và xử lý hot key riêng.

### Compact

Một job compact có thể đọc file nhỏ trong một khoảng thời gian, hợp nhất thành file lớn hơn rồi ghi lại partition đó. Cần tránh để job đọc và ghi cùng prefix trong lúc query đang chạy nếu có nguy cơ thấy trạng thái dữ liệu không nhất quán. Dùng staging prefix và quy trình publish/replace có kiểm soát khi cần.

## 22. Partition pruning, projection và index: chọn cơ chế nào?

| Tình huống | Cơ chế nên xem xét |
|---|---|
| Bảng có vài trăm hoặc vài nghìn partition | Partition pruning thông thường có thể đủ |
| Glue GetPartitions chậm với partition đã đăng ký | Glue partition index và partition filtering |
| Partition được sinh theo quy tắc liên tục, dễ tính | Athena partition projection |
| Dataset sparse, nhiều tổ hợp dự đoán không có dữ liệu | Cân nhắc index hoặc quản lý partition metadata tường minh |
| Partition key không có trong predicate | Sửa query hoặc xem lại layout; projection không tự thay thế điều kiện lọc |
| Số file quá nhiều trong từng partition | Compact files; index/projection không giải quyết small files |

Partition pruning vẫn diễn ra khi partition projection được bật. Projection chỉ thay cách Athena lấy/định nghĩa partition metadata. Glue partition index tối ưu thao tác lọc metadata trong Data Catalog; nó không nén file hoặc giảm số file.

## 23. Chọn Parquet hay ORC trong AWS

Một quy trình lựa chọn:

1. Xác định query engine: Athena, Spark, Hive, EMR, Trino hoặc nhiều engine.
2. Xác định schema: flat hay nested, số cột, kiểu dữ liệu và tần suất schema change.
3. Xác định query pattern: column projection, filter, join và aggregation.
4. Tạo hai bản sample Parquet và ORC với compression tương đương.
5. Chạy cùng bộ query, cùng engine version và cùng cấu hình.
6. So sánh bytes scanned, execution time, CPU, memory và storage size.
7. Kiểm tra interoperability giữa writer và reader.

Parquet thường là lựa chọn mặc định tốt khi cần tương thích rộng. ORC đáng thử khi workload dựa vào Hive hoặc benchmark cho thấy lợi ích về dung lượng/index. Nếu hệ thống đã chuẩn hóa một format và hiệu năng đáp ứng SLO, không nên chuyển format chỉ để chạy theo xu hướng.

## 24. Data lake layout và vùng dữ liệu

Một data lake có thể tổ chức theo các vùng:

| Vùng | Mục tiêu | Format thường gặp |
|---|---|---|
| Raw/Bronze | Giữ dữ liệu gần nguồn, phục vụ replay và audit | JSON, CSV, Avro hoặc raw source format |
| Curated/Silver | Chuẩn hóa schema, kiểu dữ liệu, chất lượng và partition | Parquet hoặc ORC |
| Analytics/Gold | Dataset phục vụ BI, dashboard và query nghiệp vụ | Parquet, ORC hoặc table format như Iceberg |

Không bắt buộc mọi vùng phải dùng cùng format. Raw có thể giữ nguyên dữ liệu gốc để tái xử lý; curated và analytics thường dùng columnar format để giảm scan và chi phí.

Đối với dataset cần update/delete, transaction, time travel hoặc schema/partition evolution, cần đánh giá table format như Apache Iceberg. Parquet và ORC là file format; Iceberg là table format quản lý metadata, snapshot và data files. Hai khái niệm này bổ trợ nhau chứ không phải đối thủ trực tiếp.

## 25. Bảo mật và governance cho partitioned data lake

Partition path có thể chứa thông tin nhạy cảm như tenant, region hoặc business unit. Không nên coi prefix S3 là ranh giới bảo mật duy nhất.

Các điểm cần kiểm soát:

- IAM policy và S3 bucket policy theo least privilege.
- AWS Lake Formation để quản lý quyền database, table, column và row-level filtering khi phù hợp.
- KMS encryption và key policy.
- Glue Data Catalog permission và resource link nếu chia sẻ cross-account.
- CloudTrail để audit thao tác catalog, bucket và query.
- Tag và owner cho database/table/partition.
- Retention, lifecycle và xóa dữ liệu theo chính sách.

Nếu partition key chứa tenant ID, cần xác định quyền truy cập dữ liệu của từng tenant. Việc query có predicate tenant_id không tự bảo đảm người dùng không thể bỏ predicate và đọc tenant khác. Dùng governance control phù hợp thay vì dựa vào quy ước query.

## 26. Hiệu năng và chi phí truy vấn Athena

Athena tính phí chủ yếu theo lượng dữ liệu được scan đối với pricing theo query. Partitioning và columnar format có thể giảm bytes scanned:

- Partition pruning loại bỏ prefix không cần đọc.
- Columnar projection chỉ đọc các cột được query yêu cầu.
- Compression giảm số byte lưu và đọc.
- Statistics/predicate pushdown có thể bỏ qua row group hoặc stripe không khớp.
- File size hợp lý giảm metadata overhead và cải thiện parallelism.

Tuy nhiên, quá nhiều partition hoặc file nhỏ có thể làm tăng planning time. Compression mạnh có thể tăng CPU giải nén. Query không lọc partition key có thể scan dữ liệu lớn dù table đã partition.

Theo dõi:

- Data scanned per query.
- Query planning time và execution time.
- Số partition được chọn.
- Số file và kích thước file trung bình.
- Bytes read và compression ratio.
- Glue GetPartitions latency.
- Số lỗi schema/SerDe và file hỏng.

Tối ưu phải dựa trên cả chi phí scan lẫn chi phí vận hành ETL/compaction/catalog.

## 27. Ví dụ thiết kế: data lake giao dịch

Một doanh nghiệp nhận 500 GB event/ngày. BI thường truy vấn doanh thu theo ngày, region và product category; đội data science đôi khi cần phân tích customer_id trên nhiều tháng.

### Thiết kế đề xuất ban đầu

- Raw: lưu JSON gốc theo ngày nhận dữ liệu để replay.
- Curated: chuẩn hóa timestamp về UTC, kiểu decimal cho tiền, schema version và deduplication.
- Partition curated theo year/month/day; cân nhắc thêm region nếu số region nhỏ và query thường lọc theo region.
- Dùng Parquet với Snappy hoặc ZSTD sau khi benchmark.
- Giữ customer_id trong file, không partition theo customer_id do cardinality cao.
- Compact file nhỏ theo partition hằng ngày.
- Glue Data Catalog lưu schema và partition; dùng projection hoặc partition index nếu metadata trở thành bottleneck.
- Athena query phải có predicate year/month/day; query phân tích customer có thể dùng bucketing hoặc layout riêng nếu benchmark chứng minh hiệu quả.

### Sơ đồ dữ liệu

~~~mermaid
flowchart LR
    A[Application events] --> B[S3 Raw JSON]
    B --> C[AWS Glue ETL]
    C --> D[Schema validation and dedup]
    D --> E[Partition by date / optional region]
    E --> F[Parquet or ORC files]
    F --> G[Glue Data Catalog]
    G --> H[Amazon Athena]
    G --> I[Amazon EMR / Spark]
~~~

### Kiểm chứng

1. Chọn một tuần dữ liệu đại diện.
2. Tạo hai bản curated: Parquet và ORC.
3. Chạy bộ query BI giống nhau.
4. So sánh bytes scanned, planning time, execution time và file size.
5. Kiểm tra query theo ngày, theo region và query customer_id nhiều tháng.
6. Tăng quy mô lên một tháng rồi đánh giá số partition, số file và Glue metadata.
7. Chọn layout/format phù hợp và ghi lại lý do trong kiến trúc.

## 28. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Query scan nhiều dữ liệu dù table đã partition | Thiếu predicate trên partition key hoặc key không khớp | Thêm điều kiện partition, kiểm tra S3 path và table metadata |
| Không thấy partition mới | Glue metadata chưa cập nhật | Dùng Glue API, crawler hoặc MSCK REPAIR TABLE trong phạm vi phù hợp |
| Query planning chậm | Quá nhiều partition và GetPartitions tốn thời gian | Glue partition index/filtering hoặc partition projection |
| Projection query chậm | Dataset sparse, range quá rộng hoặc template sai | Thu hẹp range, benchmark, cân nhắc metadata tường minh |
| Số file rất lớn | Micro-batch nhỏ hoặc partition cardinality cao | Compact và xem lại partition key |
| Một partition quá lớn | Partition key quá thô hoặc hot key | Thêm key có cardinality hợp lý hoặc bucketing |
| Query không đọc được Parquet/ORC | Schema mismatch, codec hoặc file hỏng | Kiểm tra writer version, schema và compression support |
| Sai dữ liệu sau schema change | Reader/writer không tương thích | Version schema, cast có kiểm soát và rewrite nếu cần |
| CTAS báo quá nhiều open partitions | Một query tạo hơn 100 partition/bucket combinations | Chia CTAS/INSERT INTO thành nhiều batch |
| Partition month bị tách thành '2' và '02' | Không chuẩn hóa giá trị partition | Dùng zero-padding và sửa metadata/layout |
| Glue crawler đổi schema ngoài ý muốn | Crawler infer schema từ file không đồng nhất | Đặt schema tường minh, classifier và schema change policy |

## 29. Checklist thiết kế partition và columnar format

- [ ] Đã phân tích query pattern và predicate phổ biến.
- [ ] Partition key có cardinality phù hợp và kích thước partition đủ lớn.
- [ ] S3 prefix tuân theo một quy tắc thống nhất, không trộn dataset.
- [ ] Partition key dùng kiểu STRING và giá trị được chuẩn hóa.
- [ ] Query có predicate trên partition key để tận dụng pruning.
- [ ] Số partition và số file được theo dõi.
- [ ] Có chiến lược Glue Catalog partition registration.
- [ ] Đã đánh giá Glue partition index hoặc Athena partition projection khi metadata lớn.
- [ ] Projection template/range phù hợp với layout và mức độ sparse.
- [ ] Đã benchmark Parquet và ORC trên dữ liệu/query đại diện.
- [ ] Compression codec được hỗ trợ bởi tất cả writer/reader trong pipeline.
- [ ] Row group/stripe và file size không quá nhỏ.
- [ ] Có job compact cho small files và tránh rewrite toàn dataset không cần thiết.
- [ ] Schema evolution có versioning và kiểm thử cross-engine.
- [ ] Retention, lifecycle, encryption, IAM và Lake Formation được cấu hình.
- [ ] Theo dõi bytes scanned, planning time, execution time và chi phí ETL.

## 30. Ghi nhớ

Partitioning chia dataset thành các prefix dựa trên thuộc tính thường được dùng để lọc. Chọn partition key có cardinality hợp lý, kích thước partition đủ lớn và phù hợp với query pattern. Partition pruning giúp bỏ qua prefix không liên quan; Glue partition index và Athena partition projection tối ưu cách lấy metadata trong những tình huống khác nhau.

Parquet và ORC là định dạng columnar giúp giảm dữ liệu phải đọc nhờ column pruning, compression, encoding, statistics và predicate pushdown. Parquet có ecosystem rộng; ORC thường có lợi thế trong một số workload Hive/analytics và có thể tạo file nhỏ hơn. Chỉ benchmark trên dữ liệu và query thực tế mới xác định được định dạng phù hợp.

Thiết kế tốt phải kết hợp partition, file size, schema, compression, Glue metadata và governance. Tránh partition cardinality quá cao, small files, schema drift và query không lọc partition key. Theo dõi bytes scanned, planning time và chi phí ETL để duy trì data lake có hiệu năng ổn định khi dữ liệu tăng trưởng.

## Tài liệu tham khảo

- [Partition Your Data - Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/partitions.html)
- [What Is Partitioning? - Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/ctas-partitioning-and-bucketing-what-is-partitioning.html)
- [Use Partition Projection with Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/partition-projection.html)
- [Optimize Data - Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/performance-tuning-data-optimization-techniques.html)
- [Optimize Tables and File Sizes - Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/performance-tuning-s3-throttling-optimizing-your-tables.html)
- [Use Columnar Storage Formats - Amazon Athena](https://docs.aws.amazon.com/athena/latest/ug/columnar-storage.html)
- [Use Compression in Athena](https://docs.aws.amazon.com/athena/latest/ug/compression-formats.html)
- [Create a Table from Query Results (CTAS)](https://docs.aws.amazon.com/athena/latest/ug/ctas.html)
- [CTAS Examples](https://docs.aws.amazon.com/athena/latest/ug/ctas-examples.html)
- [CTAS Considerations and Limitations](https://docs.aws.amazon.com/athena/latest/ug/ctas-considerations-limitations.html)
- [Use CTAS and INSERT INTO for ETL and Data Analysis](https://docs.aws.amazon.com/athena/latest/ug/ctas-insert-into-etl.html)
- [Work Around the 100 Partition Limit](https://docs.aws.amazon.com/athena/latest/ug/ctas-insert-into.html)
- [AWS Glue Partition Indexes](https://docs.aws.amazon.com/glue/latest/dg/partition-indexes.html)
- [Optimize Athena with Glue Partition Indexing and Filtering](https://docs.aws.amazon.com/athena/latest/ug/glue-best-practices-partition-index.html)
- [AWS Glue Data Catalog](https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html)
