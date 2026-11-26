Câu 1. Ứng dụng Spring Boot muốn dùng Spring Data Elasticsearch, starter nào phù hợp?
A. Thêm `spring-boot-starter-data-mongodb` để chạy truy vấn.
B. Thêm `spring-boot-starter-data-rest` để triển khai search.
C. Thêm `spring-boot-starter-data-elasticsearch`.
D. Thêm `spring-boot-starter-data-jpa` để tạo index search.
Đáp án đúng: C

Câu 2. Annotation nào thường dùng để ánh xạ Java entity vào index Elasticsearch?
A. Đặt `@Entity(name = "products")` để map index document.
B. Đặt `@Document(indexName = "products")` trên class entity.
C. Đặt `@Collection("products")` để khai báo index name.
D. Đặt `@Table(name = "products")` để tạo mapping search.
Đáp án đúng: B

Câu 3. Trong entity Elasticsearch, `@Id` ánh xạ giá trị nào của document?
A. Định danh document được Elasticsearch lưu ở `_id`.
B. Giá trị routing để phân phối document giữa các shard.
C. Giá trị sequence number dùng kiểm soát ghi đồng thời.
D. Định danh shard primary đang lưu document trong index.
Đáp án đúng: A

Câu 4. Trường tên sản phẩm cần tìm theo từ khóa được phân tích; mapping nào phù hợp?
A. Dùng `@Field(type = FieldType.Text)` cho tên sản phẩm.
B. Dùng `@Field(type = FieldType.Keyword)` để phân tách token.
C. Dùng `@Field(type = FieldType.Long)` để lập inverted index.
D. Dùng `@Field(type = FieldType.Boolean)` để phân tích tên.
Đáp án đúng: A

Câu 5. Trường SKU cần lọc chính xác và nhóm theo mã; mapping nào phù hợp?
A. Dùng trường kiểu `date` để nhóm SKU theo thời điểm nhập.
B. Dùng trường kiểu `text` rồi tìm nguyên chuỗi bằng `term`.
C. Dùng trường kiểu `keyword` để đối sánh SKU nguyên giá trị.
D. Dùng trường kiểu `nested` để lưu mã SKU như mảng object.
Đáp án đúng: C

Câu 6. Analyzer của field `text` chủ yếu làm gì trong giai đoạn indexing?
A. Phân phối document vào shard theo tần suất token xuất hiện.
B. Đồng bộ mapping của index sang bảng quan hệ trong SQL.
C. Tách và chuẩn hóa văn bản thành token cho inverted index.
D. Tạo document ID ổn định từ chuỗi trước khi lưu vào index.
Đáp án đúng: C

Câu 7. Tìm nội dung trên field `description` kiểu `text`, truy vấn nào thường phù hợp?
A. Dùng `match` query để phân tích văn bản được tìm.
B. Dùng `ids` query để tìm cụm từ từ document ID.
C. Dùng `term` query để phân tích rồi ghép các từ.
D. Dùng `exists` query để tính độ tương đồng văn bản.
Đáp án đúng: A

Câu 8. Với field `status` kiểu `keyword`, muốn lọc chính xác `ACTIVE` nên dùng gì?
A. Dùng `term` query với `status=ACTIVE` trong filter.
B. Dùng `wildcard` query với `status=*IVE` để lọc chính xác.
C. Dùng `prefix` query với `status=A` để tìm đúng ACTIVE.
D. Dùng `exists` query trên `status` để lấy giá trị ACTIVE.
Đáp án đúng: A

Câu 9. Trong bool query, trường hợp nào nên đưa điều kiện vào `filter` thay vì `must`?
A. Khi điều kiện phải xét similarity và xếp hạng kết quả.
B. Khi điều kiện cần tính điểm cho bộ lọc giá sản phẩm.
C. Khi điều kiện cần boost điểm tương đồng BM25 của tài liệu.
D. Khi điều kiện lọc không cần tác động đến điểm `_score`.
Đáp án đúng: D

Câu 10. Muốn bỏ các document có `deleted=true` khỏi kết quả, thành phần bool nào phù hợp?
A. Đặt `term deleted=true` trong nhánh `filter`.
B. Đặt `term deleted=true` trong nhánh `should`.
C. Đặt `term deleted=true` trong nhánh `must`.
D. Đặt `term deleted=true` trong nhánh `must_not`.
Đáp án đúng: D

Câu 11. Bool query có `must`, nhưng yêu cầu ít nhất một `should` phải khớp; cần gì?
A. Đặt `min_score=1` cho bool query.
B. Đặt `minimum_should_match=1` cho bool query.
C. Đặt `track_total_hits=1` cho bool query.
D. Đặt `terminate_after=1` cho bool query.
Đáp án đúng: B

Câu 12. Tìm ở title và description nhưng muốn title được ưu tiên xếp hạng, nên làm gì?
A. Boost field `title` trong `multi_match` cao hơn description.
B. Giảm `size` của search result để ưu tiên điểm của title.
C. Đổi description sang keyword rồi Elasticsearch boost title.
D. Đưa title vào bool filter để tăng điểm relevance BM25.
Đáp án đúng: A

Câu 13. Muốn lọc sản phẩm có giá từ 100 đến 300, query nào phù hợp?
A. Dùng `wildcard` để đối sánh tiền tố chuỗi giá.
B. Dùng `terms` để liệt kê hai giá trị 100 và 300.
C. Dùng `range` với `gte=100` và `lte=300` trên price.
D. Dùng `match_phrase` với cặp số 100, 300 và slop.
Đáp án đúng: C

Câu 14. Document có mảng `variants` gồm color và size; cần khớp cả hai trên cùng phần tử, dùng gì?
A. Mapping `text` rồi match phrase trên mảng JSON.
B. Mapping `flattened` rồi match riêng từng field con.
C. Mapping `nested` cùng `nested` query trên path variants.
D. Mapping `object` thường rồi bool must trên hai field con.
Đáp án đúng: C

Câu 15. Repository cho entity `Product` có ID kiểu `String` nên khai báo thế nào?
A. Cho interface kế thừa `CassandraRepository<Product, String>`.
B. Kế thừa `ElasticsearchRepository<Product, String>`.
C. Cho interface kế thừa `JpaRepository<Product, String>`.
D. Cho interface kế thừa `MongoRepository<Product, String>`.
Đáp án đúng: B

Câu 16. Khi cần dựng Elasticsearch DSL phức tạp trong Spring Data, lựa chọn nào phù hợp?
A. Dùng repository JPA `Specification` để biên dịch Query DSL.
B. Dùng MongoDB `Aggregation` rồi thực thi bằng JdbcTemplate.
C. Dùng `NativeQuery` và thực thi bằng `ElasticsearchOperations`.
D. Dùng JPA `CriteriaBuilder` rồi truyền thẳng cho client Elastic.
Đáp án đúng: C

Câu 17. `ElasticsearchOperations.search(query, Product.class)` thường trả về kiểu nào?
A. `SearchHits<Product>` chứa nội dung và metadata hit.
B. `Mono<Product>` trả một document và bỏ metadata search.
C. `ResultSet<Product>` trả các row từ shard dưới dạng SQL.
D. `Page<Product>` chứa cursor JDBC và row của database.
Đáp án đúng: A

Câu 18. UI cần hiển thị đoạn văn khớp từ khóa, nên dùng tính năng nào?
A. Đặt `_source=false` để server tự tô đậm đoạn khớp.
B. Dùng `terms aggregation` để nhận vị trí ký tự khớp.
C. Dùng `search_after` để server tự chọn đoạn văn nổi bật.
D. Yêu cầu highlighting rồi lấy đoạn highlight từ `SearchHit`.
Đáp án đúng: D

Câu 19. Muốn đếm số sản phẩm theo category kiểu keyword, aggregation nào phù hợp?
A. Chọn `avg` aggregation trên trường category.
B. Chọn `terms` aggregation trên trường category.
C. Chọn `date_histogram` aggregation trên category.
D. Chọn `geo_bounds` aggregation trên field category.
Đáp án đúng: B

Câu 20. Để nhóm số đơn hàng theo ngày từ trường `created_at` kiểu date, nên dùng gì?
A. Chọn `terms` aggregation theo timestamp nguyên bản.
B. Chọn `top_hits` aggregation để tạo bucket theo ngày.
C. Chọn `date_histogram` aggregation với interval ngày.
D. Chọn `bucket_sort` aggregation để chia khoảng ngày.
Đáp án đúng: C

Câu 21. Cần giá trung bình của sản phẩm trong từng category, thiết kế nào phù hợp?
A. Dùng `sum` category và `terms` price để tạo giá trị bình quân.
B. Dùng `terms` category với `avg` price trong từng bucket.
C. Dùng `min` category và `max` price để suy ra giá trung bình.
D. Dùng `value_count` category với `top_hits` tính bình quân.
Đáp án đúng: B

Câu 22. Với kết quả tìm kiếm sâu, vì sao `from` cộng `size` có thể tốn kém?
A. Search được chuyển thành bulk indexing khi offset lớn.
B. Cluster phải xây dựng lại mapping khi offset tăng.
C. Node cần chạy reindex theo độ sâu của từng trang kết quả.
D. Shard phải giữ nhiều hit trước khi lấy trang được yêu cầu.
Đáp án đúng: D

Câu 23. Phân trang sâu trên tập dữ liệu thay đổi liên tục, cách nào phù hợp hơn?
A. Dùng `scroll` làm API mặc định cho phân trang tương tác.
B. Chỉ đặt `size` với sort score, không cần state giữa trang.
C. Tiếp tục tăng `from` vô hạn và bỏ sort nếu có PIT.
D. Dùng `search_after` với PIT và sort xác định thứ tự.
Đáp án đúng: D

Câu 24. Vì sao document vừa được index có thể chưa xuất hiện khi search ngay?
A. Document thường cần một lần refresh để được search thấy.
B. Document phải đợi force merge của mọi shard trên cluster.
C. Document cần được reindex sang alias trước khi được tìm.
D. Index phải snapshot trước khi cho phép truy vấn nội dung.
Đáp án đúng: A

Câu 25. Với yêu cầu index dùng `refresh=wait_for`, điều gì xảy ra?
A. Request tắt refresh và trả thành công ngay từ translog.
B. Request chờ refresh để document được thấy qua search.
C. Request chờ snapshot index hoàn tất mới ghi document.
D. Request buộc Elasticsearch force merge trước khi trả kết quả.
Đáp án đúng: B

Câu 26. Bulk API trả response thành công ở HTTP level; vẫn phải kiểm tra gì?
A. Trường `errors` chỉ trong request mà không xét phản hồi.
B. Lỗi của từng item vì bulk có thể thành công một phần.
C. Độ dài batch vì HTTP success đồng nghĩa không có item lỗi.
D. Thời gian `took` vì nó xác nhận mọi item đã index xong.
Đáp án đúng: B

Câu 27. Hai writer cập nhật cùng document; cơ chế nào giúp tránh lost update?
A. Dùng `refresh=true` để biến update thành một transaction.
B. Dùng `_score` cao hơn để chọn writer được phép commit.
C. Dùng `search_after` để sắp thứ tự mutation của writer.
D. Dùng optimistic concurrency với `_seq_no` và `_primary_term`.
Đáp án đúng: D

Câu 28. Khi cần đổi kiểu mapping field không tương thích trong index hiện có, nên rollout thế nào?
A. Tạo index mới, reindex rồi chuyển alias có kiểm soát.
B. Chỉ xóa cache search để field type mới có hiệu lực.
C. Đặt số replica khác rồi Elasticsearch đổi mapping theo.
D. Đổi type trực tiếp trên mapping cũ mà giữ nguyên document.
Đáp án đúng: A

Câu 29. DB là nguồn dữ liệu chuẩn, Elasticsearch phục vụ search; đồng bộ thế nào đáng tin cậy?
A. Giảm thời gian refresh để tự đồng bộ các row đã thay đổi.
B. Ghi outbox cùng transaction DB rồi cập nhật index bất đồng bộ.
C. Ghi Elasticsearch trước và coi DB đã được ghi thành công.
D. Dùng `@Transactional` để DB và search index commit nguyên tử.
Đáp án đúng: B

Câu 30. Khi replay cùng một event cập nhật search index, thiết kế nào hạn chế dữ liệu trùng?
A. Đổi alias cho mỗi event để Elasticsearch xóa các ID cũ.
B. Tăng số primary shard để những event giống nhau không trùng.
C. Tạo ID ngẫu nhiên cho mỗi event để tránh đụng dữ liệu.
D. Dùng document ID ổn định cùng kiểm soát thứ tự phiên bản.
Đáp án đúng: D

Câu 31. Muốn kiểm thử analyzer, mapping và DSL query với hành vi thực tế, chọn cách nào?
A. Chỉ kiểm tra annotation của entity mà không tạo index.
B. Dùng H2 và `LIKE` để xác thực search score của BM25.
C. Chỉ mock repository rồi coi như analyzer đã hoạt động đúng.
D. Chạy Elasticsearch trong Testcontainers và assert search.
Đáp án đúng: D

Câu 32. Khi latency search và indexing tăng, tín hiệu nào hữu ích để chẩn đoán?
A. Xem HTTP response size mà bỏ qua shard và search queue.
B. Xem thời gian Maven build và kích thước source tree.
C. Xem p95 latency, shard, refresh, rejection và heap.
D. Xem số controller, class Java và độ dài source code.
Đáp án đúng: C
