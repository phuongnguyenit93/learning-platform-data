# Khi nên dùng Elasticsearch và khi nên chọn công cụ khác

Elasticsearch phù hợp khi ứng dụng cần tìm kiếm trên nội dung với chất lượng và tốc độ cao: hiểu từ khóa, xếp hạng kết quả theo mức độ liên quan, kết hợp nhiều bộ lọc, gợi ý khi người dùng đang nhập và xử lý dữ liệu tìm kiếm trên nhiều máy. Tuy nhiên, Elasticsearch không tự động là lựa chọn tốt nhất cho mọi thao tác đọc dữ liệu. Nếu nhu cầu chủ yếu là CRUD, truy vấn quan hệ, giao dịch cần tính nhất quán mạnh hoặc tìm kiếm đơn giản trên một tập dữ liệu nhỏ, cơ sở dữ liệu hiện có thường là lựa chọn gọn và an toàn hơn.

Quyết định nên dựa trên loại truy vấn, yêu cầu nhất quán, quy mô, chi phí vận hành và khả năng của hệ thống hiện tại. Số lượng bản ghi lớn tự nó chưa đủ để kết luận rằng cần Elasticsearch.

## 1. Hiểu đúng vai trò của Elasticsearch

Elasticsearch là một công cụ tìm kiếm và phân tích phân tán, xây dựng trên Apache Lucene. Nó nhận tài liệu, lập chỉ mục nội dung và cung cấp API để tìm kiếm, lọc, sắp xếp, tổng hợp dữ liệu. Chỉ mục tìm kiếm được tổ chức để tìm các thuật ngữ hiệu quả, đặc biệt với truy vấn toàn văn.

Một cơ sở dữ liệu quan hệ thường lưu dữ liệu chuẩn hóa để bảo đảm ràng buộc và giao dịch. Một chỉ mục Elasticsearch thường được thiết kế theo cách đọc: chứa những trường cần thiết cho các màn hình và truy vấn tìm kiếm, có thể lặp lại một phần dữ liệu từ nhiều bảng để tránh phải join khi truy vấn.

Trong nhiều hệ thống nghiệp vụ, kiến trúc hợp lý là:

~~~text
Ứng dụng ghi dữ liệu
        |
        v
Cơ sở dữ liệu chính
(nguồn dữ liệu có thẩm quyền)
        |
        | sự kiện / outbox / CDC / tiến trình đồng bộ
        v
Elasticsearch
(chỉ mục phục vụ tìm kiếm)
        |
        v
API tìm kiếm và giao diện người dùng
~~~

Theo mô hình này, cơ sở dữ liệu chính vẫn chịu trách nhiệm về dữ liệu nghiệp vụ và giao dịch. Elasticsearch giữ một bản chiếu được tối ưu cho truy vấn. Khi dữ liệu nguồn thay đổi, chỉ mục được cập nhật sau đó; vì vậy có thể tồn tại một khoảng trễ ngắn giữa lúc ghi và lúc tìm thấy dữ liệu mới.

Elasticsearch có thể nhận thao tác ghi, cập nhật và xóa tài liệu. Điều đó không có nghĩa nó luôn nên thay thế cơ sở dữ liệu giao dịch. Cập nhật tài liệu trong chỉ mục có chi phí lập chỉ mục, khả năng nhìn thấy thay đổi còn phụ thuộc refresh, và mô hình dữ liệu của nó không cung cấp cùng cách dùng khóa ngoại, join quan hệ và giao dịch nhiều bản ghi như cơ sở dữ liệu quan hệ.

## 2. Những trường hợp Elasticsearch phát huy hiệu quả

### 2.1. Tìm kiếm toàn văn là chức năng quan trọng

Nên cân nhắc Elasticsearch khi người dùng tìm theo từ hoặc cụm từ trong nhiều trường văn bản, chẳng hạn tên sản phẩm, mô tả, thương hiệu, mã danh mục và nội dung bài viết. Hệ thống cần phân tích văn bản trước khi lập chỉ mục và truy vấn, thay vì chỉ so sánh chuỗi chính xác.

Ví dụ, trang thương mại điện tử có thể cần:

- Tìm sản phẩm theo tên và mô tả.
- Ưu tiên kết quả có từ khóa trong tên hơn trong phần mô tả.
- Hỗ trợ tìm cụm từ, từ gần đúng hoặc các biến thể được cấu hình.
- Kết hợp từ khóa với điều kiện giá, thương hiệu, tình trạng còn hàng và danh mục.
- Sắp xếp theo độ liên quan, sau đó theo giá hoặc thời gian cập nhật.

Elasticsearch cho phép điều chỉnh cách phân tích văn bản, trọng số từng trường và cách tính điểm phù hợp với trải nghiệm tìm kiếm.

### 2.2. Cần xếp hạng theo mức độ liên quan

Một truy vấn tìm kiếm tốt thường không chỉ trả về những bản ghi có chứa chuỗi được nhập. Nó còn cần quyết định kết quả nào phù hợp hơn.

Ví dụ, khi người dùng tìm “máy ảnh du lịch”, sản phẩm có cả hai từ trong tên có thể nên đứng trước sản phẩm chỉ nhắc đến chúng trong mô tả. Điểm liên quan có thể kết hợp:

- Mức độ khớp của từ khóa.
- Trường chứa nội dung khớp.
- Độ hiếm của thuật ngữ trong tập tài liệu.
- Trọng số nghiệp vụ được cấu hình.
- Các tín hiệu bổ sung như độ phổ biến hoặc thời gian.

Nếu ứng dụng chỉ cần tìm chính xác theo mã hoặc ID, cơ chế xếp hạng này có thể không đem lại lợi ích đáng kể.

### 2.3. Bộ lọc và thống kê đi cùng tìm kiếm

Elasticsearch hữu ích khi trang kết quả cần đồng thời lọc và hiển thị số lượng theo từng nhóm. Ví dụ, người dùng tìm laptop rồi lọc theo hãng, khoảng giá, RAM, kích thước màn hình và tình trạng hàng; giao diện cũng cần biết mỗi hãng hoặc khoảng giá còn bao nhiêu kết quả.

Các truy vấn có thể kết hợp điều kiện văn bản, điều kiện lọc chính xác, sắp xếp và aggregations. Đây là lợi thế khi bộ lọc thay đổi linh hoạt theo loại dữ liệu và phải chạy trên cùng tập kết quả.

### 2.4. Cần gợi ý, tự hoàn thành hoặc chịu được lỗi gõ

Các tính năng như gợi ý truy vấn, autocomplete, tìm tiền tố, fuzzy matching, đồng nghĩa và phân tích ngôn ngữ có thể là lý do hợp lý để dùng một search engine. Chúng đặc biệt có giá trị khi tìm kiếm là luồng tương tác chính của sản phẩm và chất lượng kết quả ảnh hưởng trực tiếp đến khả năng tìm thấy nội dung.

Những khả năng này cần được thiết kế bằng analyzer, tokenizer, filter và mapping phù hợp với ngôn ngữ và dữ liệu thực tế. Chỉ cài Elasticsearch rồi dùng truy vấn mặc định không bảo đảm kết quả tiếng Việt sẽ tốt. Cần thử với các trường hợp dấu tiếng Việt, cách viết hoa, từ ghép, lỗi gõ và từ đồng nghĩa mà người dùng thật sự sử dụng.

### 2.5. Có mô hình đọc riêng và cần mở rộng tìm kiếm

Khi nhiều nguồn dữ liệu cần được kết hợp thành một tài liệu phục vụ tìm kiếm, Elasticsearch có thể làm nơi lưu read model đã làm phẳng. Ví dụ, tài liệu sản phẩm có thể chứa tên sản phẩm, tên thương hiệu, tên danh mục và thông tin tồn kho cần hiển thị.

Mô hình tài liệu này giúp truy vấn tìm kiếm tránh nhiều phép join. Nó phù hợp khi đội ngũ chấp nhận xây dựng quy trình đồng bộ và xử lý dữ liệu trùng lặp. Khả năng phân tán shard và replica cũng hỗ trợ mở rộng lưu trữ, khả năng đọc và tính sẵn sàng, nhưng vẫn cần thiết kế dung lượng và vận hành cụm đúng cách.

### 2.6. Tìm kiếm và phân tích dữ liệu vận hành

Elasticsearch cũng có thể phù hợp với việc tra cứu log, sự kiện hoặc dữ liệu quan sát theo thời gian, đặc biệt khi cần tìm kiếm văn bản kết hợp bộ lọc theo dịch vụ, mức độ, thời gian và thuộc tính. Tuy nhiên, cần xác định rõ yêu cầu lưu giữ, khối lượng ingest, chi phí lưu trữ và nhu cầu phân tích. Một hệ thống phân tích cột chuyên dụng có thể phù hợp hơn nếu trọng tâm là truy vấn phân tích rất lớn thay vì tìm kiếm tương tác.

## 3. Những trường hợp nên chọn công cụ khác

### 3.1. Ứng dụng chủ yếu là CRUD và truy vấn chính xác

Nếu màn hình chỉ tải một bản ghi theo ID, lọc theo vài cột, sắp xếp theo ngày hoặc phân trang danh sách, cơ sở dữ liệu hiện tại thường đã làm tốt. B-tree index, composite index và thiết kế truy vấn phù hợp có thể đáp ứng hiệu năng mà không cần thêm một cụm tìm kiếm.

Thêm Elasticsearch cho trường hợp này khiến hệ thống phải duy trì hai nơi lưu dữ liệu, đồng bộ khi ghi và xóa, xử lý lỗi đồng bộ, giám sát cụm và trả thêm chi phí hạ tầng. Nếu không có nhu cầu tìm kiếm đặc thù, phần phức tạp đó không tạo ra đủ giá trị.

### 3.2. Giao dịch và tính nhất quán là ưu tiên hàng đầu

Các nghiệp vụ như thanh toán, chuyển tiền, đặt chỗ có giới hạn, cập nhật số dư hoặc quản lý tồn kho cần các ràng buộc và giao dịch rõ ràng. Cơ sở dữ liệu giao dịch nên giữ vai trò nguồn dữ liệu có thẩm quyền.

Nếu một thay đổi phải được xác nhận ngay và mọi lần đọc tiếp theo phải thấy trạng thái mới, không nên dựa vào chỉ mục tìm kiếm được đồng bộ bất đồng bộ làm nơi kiểm tra quyết định cuối cùng. Có thể dùng Elasticsearch để tìm và lọc ứng viên, sau đó đọc hoặc xác nhận trạng thái quan trọng từ cơ sở dữ liệu chính.

### 3.3. Truy vấn cần nhiều quan hệ và join phức tạp

Nếu phần lớn truy vấn cần join nhiều bảng, áp dụng ràng buộc khóa ngoại hoặc tính toán trên dữ liệu chuẩn hóa, cơ sở dữ liệu quan hệ thường tự nhiên hơn. Elasticsearch hỗ trợ quan hệ theo một số cách, nhưng không thay thế mô hình join tổng quát của SQL. Nhúng hoặc lặp lại dữ liệu trong tài liệu tìm kiếm có thể tăng tốc đọc, đồng thời làm cho việc cập nhật và đồng bộ phức tạp hơn.

### 3.4. Quy mô và yêu cầu tìm kiếm còn đơn giản

Với tập dữ liệu nhỏ, ít người dùng và tìm kiếm đơn giản, dùng tính năng tìm kiếm toàn văn của cơ sở dữ liệu có thể đủ. Không có một ngưỡng số lượng bản ghi cố định để quyết định chuyển sang Elasticsearch. Cần đo thời gian phản hồi, tải truy vấn, độ trễ ghi, kích thước dữ liệu và mức độ phức tạp của truy vấn trên hạ tầng thực tế.

Một bảng có vài triệu dòng với truy vấn được đánh chỉ mục tốt có thể hoạt động ổn định trong cơ sở dữ liệu quan hệ. Ngược lại, một tập dữ liệu nhỏ vẫn có thể cần search engine nếu yêu cầu về relevance, autocomplete hoặc phân tích ngôn ngữ rất cao.

### 3.5. Đội ngũ chưa sẵn sàng vận hành thêm một hệ thống

Elasticsearch cần theo dõi dung lượng heap, CPU, disk, shard, replica, indexing rate, query latency, cluster health, snapshot và phục hồi. Cần có kế hoạch phân quyền, bảo mật mạng, nâng cấp phiên bản và xử lý sự cố.

Nếu đội ngũ không có nhu cầu tìm kiếm đủ mạnh hoặc chưa có năng lực vận hành, nên bắt đầu bằng công cụ đã có trong hệ thống hoặc một dịch vụ được quản lý phù hợp. Chỉ thêm cụm Elasticsearch khi lợi ích sản phẩm và khả năng vận hành đã được xác nhận.

## 4. So sánh các lựa chọn phổ biến

| Công cụ | Nên bắt đầu từ đây khi | Điểm cần cân nhắc |
|---|---|---|
| PostgreSQL hoặc cơ sở dữ liệu quan hệ hiện có | CRUD, lọc chính xác, join, giao dịch; tìm kiếm toàn văn ở mức vừa phải | Cần thiết kế index và truy vấn; tính năng tìm kiếm ngôn ngữ có giới hạn riêng |
| PostgreSQL Full Text Search và trigram | Ứng dụng dùng PostgreSQL, cần tìm từ trong văn bản, tìm gần đúng hoặc tìm chuỗi con ở mức phù hợp | Cần cấu hình tsvector, dictionary, GIN/GiST và kiểm thử chất lượng ngôn ngữ |
| Full-text search của MySQL hoặc hệ quản trị đang dùng | Dữ liệu và ứng dụng đã ở trong hệ quản trị đó, yêu cầu tìm kiếm tương đối cơ bản | Khả năng phân tích, xếp hạng và tùy biến phụ thuộc hệ quản trị và phiên bản |
| MongoDB Atlas Search | Dữ liệu chính đã ở MongoDB và muốn tích hợp tìm kiếm vào hệ sinh thái đó | Phụ thuộc dịch vụ, kiến trúc triển khai và chi phí của nền tảng |
| Meilisearch hoặc Typesense | Cần trải nghiệm tìm kiếm ứng dụng đơn giản, thiết lập nhanh, autocomplete và lọc phổ biến | Cần kiểm tra khả năng tùy biến, quy mô, vận hành và giới hạn tính năng của từng sản phẩm |
| Apache Solr | Cần nền tảng tìm kiếm dựa trên Lucene với khả năng cấu hình và hệ sinh thái Solr | Cần đánh giá năng lực vận hành và mức độ phù hợp với hệ thống hiện tại |
| OpenSearch | Cần search/analytics engine tương thích với nhiều khái niệm và API thuộc hệ sinh thái Elasticsearch | Không nên giả định mọi phiên bản, plugin hoặc API đều tương thích hoàn toàn; phải kiểm tra ma trận tương thích |
| ClickHouse hoặc kho dữ liệu phân tích | Trọng tâm là tổng hợp và phân tích khối lượng dữ liệu lớn theo cột | Không phải lựa chọn thay thế trực tiếp cho tìm kiếm toàn văn tương tác |

Tên công cụ trong bảng là các hướng để đánh giá, không phải lời khuyên thay thế máy móc. Hãy so sánh bằng một bộ truy vấn đại diện, dữ liệu gần với thực tế, yêu cầu vận hành và tổng chi phí sở hữu.

## 5. Bảng quyết định theo nhu cầu

| Nhu cầu chính | Lựa chọn khởi đầu hợp lý | Khi nào nên đánh giá Elasticsearch |
|---|---|---|
| Đọc theo ID, CRUD, cập nhật nghiệp vụ | Cơ sở dữ liệu chính | Khi có thêm chức năng tìm kiếm thực sự phức tạp |
| Lọc theo vài cột và phân trang | Index của cơ sở dữ liệu | Khi truy vấn văn bản, relevance và nhiều bộ lọc trở thành điểm nghẽn |
| Tìm toàn văn cơ bản trong một ứng dụng PostgreSQL | PostgreSQL Full Text Search | Khi cần analyzer, ranking, autocomplete hoặc quy mô tìm kiếm vượt khả năng hiện tại |
| Tìm sản phẩm với relevance, facets và gợi ý | Elasticsearch hoặc search service phù hợp | Ngay từ giai đoạn thiết kế nếu tìm kiếm là tính năng cốt lõi |
| Giao dịch cần trạng thái mới nhất và ràng buộc chặt | Cơ sở dữ liệu giao dịch | Dùng như chỉ mục phụ để tìm ứng viên, không làm nguồn xác nhận giao dịch |
| Phân tích số liệu tổng hợp rất lớn | Kho dữ liệu hoặc OLAP phù hợp | Khi cần thêm tìm kiếm tương tác trên log hoặc tài liệu |
| Tìm kiếm đơn giản, đội ngũ nhỏ, ít yêu cầu tùy biến | Công cụ hiện có hoặc dịch vụ tìm kiếm gọn nhẹ | Khi đo đạc chứng minh các lựa chọn đó không đáp ứng |

Có thể dùng chuỗi câu hỏi sau để quyết định:

1. Người dùng có thực sự cần tìm trong nội dung văn bản, xếp hạng theo độ liên quan, autocomplete hoặc fuzzy search không?
2. Cơ sở dữ liệu hiện tại có đáp ứng được bằng index và full-text search sau khi đo đạc không?
3. Có chấp nhận độ trễ đồng bộ giữa dữ liệu chính và chỉ mục tìm kiếm không?
4. Có thể xây dựng quy trình cập nhật, xóa, retry và tái lập chỉ mục đáng tin cậy không?
5. Đội ngũ có thể bảo mật, giám sát, sao lưu và vận hành thêm một hệ thống không?

Nếu câu trả lời cho nhu cầu tìm kiếm đặc thù là “không”, hãy ưu tiên công cụ hiện có. Nếu nhu cầu đó là “có”, các lựa chọn đơn giản đã được đo đạc nhưng không đáp ứng, và đội ngũ chấp nhận mô hình đồng bộ cùng chi phí vận hành, Elasticsearch là ứng viên đáng thử nghiệm.

## 6. Điều cần tính đến khi tích hợp bằng Spring Data Elasticsearch

Spring Data Elasticsearch giúp ứng dụng Java ánh xạ đối tượng, làm việc với index và xây dựng truy vấn qua các abstraction quen thuộc. Nó không làm thay đổi bản chất phân tán, gần thời gian thực và hướng tìm kiếm của Elasticsearch. Dùng repository không có nghĩa là có thể coi Elasticsearch như một cơ sở dữ liệu quan hệ khác.

### 6.1. Xác định nguồn dữ liệu có thẩm quyền

Trước khi tạo repository, hãy xác định hệ thống nào sở hữu dữ liệu. Với ứng dụng nghiệp vụ thông thường, cơ sở dữ liệu chính lưu trạng thái chuẩn; Elasticsearch lưu tài liệu phục vụ tìm kiếm. API ghi nghiệp vụ nên cập nhật nguồn dữ liệu chính, sau đó phát sự kiện hoặc ghi outbox để tiến trình đồng bộ cập nhật chỉ mục.

Tránh mô hình ghi trực tiếp vào hai nơi theo hai lời gọi độc lập mà không có cơ chế phục hồi. Nếu ghi vào cơ sở dữ liệu thành công nhưng ghi Elasticsearch thất bại, hai nơi sẽ lệch nhau. Outbox, CDC hoặc một hàng đợi có retry và xử lý idempotent giúp quản lý tình huống đó tốt hơn.

### 6.2. Thiết kế tài liệu và mapping theo truy vấn

Một tài liệu nên chứa những trường mà truy vấn tìm kiếm cần dùng. Phân biệt trường văn bản cần phân tích với trường cần so khớp chính xác, lọc hoặc sắp xếp. Ví dụ, tên sản phẩm có thể cần kiểu text để tìm kiếm và một trường keyword riêng để sort hoặc aggregation.

Mapping và analyzer ảnh hưởng trực tiếp đến cách dữ liệu được lập chỉ mục. Thay đổi kiểu trường hoặc cách phân tích thường đòi hỏi tạo index mới và reindex dữ liệu, rồi chuyển alias sang index mới. Vì vậy cần xem mapping là một phần thiết kế dữ liệu có phiên bản, không phải cấu hình có thể thay đổi tùy ý sau khi đã có dữ liệu.

### 6.3. Thiết kế đồng bộ và xử lý lỗi

Quy trình đồng bộ cần xác định cách xử lý:

- Tạo mới, cập nhật và xóa tài liệu.
- Sự kiện đến trễ hoặc đến sai thứ tự.
- Retry khi Elasticsearch tạm thời không sẵn sàng.
- Ghi trùng sự kiện mà không tạo sai trạng thái.
- Tài liệu lỗi mapping hoặc dữ liệu không hợp lệ.
- Tái lập chỉ mục khi mapping hoặc analyzer thay đổi.

Với dữ liệu lớn, bulk indexing thường hiệu quả hơn gửi từng tài liệu riêng lẻ. Cần theo dõi số lượng tài liệu chờ đồng bộ và thời gian trễ để phát hiện chỉ mục tụt lại phía sau nguồn dữ liệu.

### 6.4. Chú ý phân trang và truy vấn lớn

Phân trang sâu bằng offset lớn có thể tốn tài nguyên vì search engine phải xem xét nhiều kết quả trước vị trí cần trả về. Với luồng duyệt kết quả lớn, hãy đánh giá search_after và cách giữ thứ tự sắp xếp ổn định. Cũng cần giới hạn kích thước trang, trường trả về và phạm vi truy vấn để tránh một yêu cầu tìm kiếm gây tải quá lớn.

### 6.5. Quản lý phiên bản và vận hành

Chọn phiên bản Spring Boot, Spring Data Elasticsearch và Elasticsearch theo ma trận tương thích của đúng release train đang dùng. Không nên chọn phiên bản client hoặc server độc lập chỉ vì đó là phiên bản mới nhất.

Trong môi trường triển khai, cần cấu hình xác thực, TLS, quyền truy cập theo nhu cầu, snapshot, cảnh báo cluster health, dung lượng đĩa, heap, shard và độ trễ truy vấn. Với dịch vụ được quản lý, một phần trách nhiệm vận hành được chuyển cho nhà cung cấp nhưng chi phí, giới hạn và trách nhiệm bảo mật vẫn cần được đánh giá.

## 7. Ví dụ: quyết định cho chức năng tìm kiếm sản phẩm

Giả sử một cửa hàng trực tuyến có bảng sản phẩm, thương hiệu, danh mục và tồn kho trong PostgreSQL. Ban đầu, trang quản trị cần tìm sản phẩm theo ID, lọc theo trạng thái và sắp xếp theo ngày cập nhật. Những truy vấn đó nên chạy trực tiếp trên PostgreSQL với index phù hợp.

Sau đó, cửa hàng xây dựng trang tìm kiếm cho khách hàng. Người dùng muốn nhập một cụm từ tự nhiên, tìm trong tên và mô tả, nhận gợi ý ngay khi nhập, sửa lỗi gõ, lọc theo thương hiệu và khoảng giá, xem số lượng sản phẩm theo từng bộ lọc, đồng thời ưu tiên kết quả phù hợp nhất. Đây là lúc Elasticsearch có thể đem lại giá trị rõ ràng.

Thiết kế có thể là:

- PostgreSQL tiếp tục lưu sản phẩm và trạng thái tồn kho có thẩm quyền.
- Một tài liệu tìm kiếm được tạo từ các trường cần thiết của sản phẩm, thương hiệu và danh mục.
- Sự kiện thay đổi sản phẩm được chuyển qua outbox hoặc CDC đến tiến trình cập nhật Elasticsearch.
- API tìm kiếm truy vấn Elasticsearch để lấy danh sách ID và thông tin hiển thị cần thiết.
- Với thao tác đặt hàng, hệ thống kiểm tra giá và tồn kho hiện tại trong PostgreSQL trước khi xác nhận.

Khi đó Elasticsearch chịu trách nhiệm tìm sản phẩm phù hợp; cơ sở dữ liệu chính vẫn chịu trách nhiệm xác nhận giao dịch. Nếu cửa hàng không triển khai gợi ý, relevance hay bộ lọc phức tạp, và tìm kiếm PostgreSQL vẫn đáp ứng thời gian phản hồi mục tiêu, việc thêm Elasticsearch có thể chưa cần thiết.

## 8. Những sai lầm thường gặp

- **Chọn Elasticsearch chỉ vì dữ liệu lớn:** quy mô cần được đo cùng kiểu truy vấn và khả năng index của hệ quản trị hiện có.
- **Dùng Elasticsearch làm nơi lưu trạng thái giao dịch duy nhất:** cần cân nhắc giao dịch, ràng buộc và tính nhất quán của nghiệp vụ.
- **Đồng bộ bằng hai lời gọi ghi độc lập:** lỗi giữa hai lời gọi có thể làm dữ liệu lệch nhau; cần cơ chế retry và đối soát.
- **Đưa toàn bộ bảng vào một index mà không có mục tiêu truy vấn:** tài liệu nên được thiết kế theo nhu cầu tìm kiếm, có cân nhắc chi phí lặp dữ liệu.
- **Không kiểm thử analyzer với tiếng Việt:** chất lượng tìm kiếm phụ thuộc cách phân tích từ và bộ dữ liệu truy vấn thực tế.
- **Coi repository abstraction là bảo đảm tương thích:** mapping, query, refresh, phân trang và phiên bản server vẫn cần được hiểu rõ.
- **Bỏ qua chi phí vận hành:** cụm tìm kiếm cần tài nguyên, giám sát, sao lưu, nâng cấp và quy trình khôi phục.

Elasticsearch đáng dùng khi chức năng tìm kiếm có yêu cầu rõ ràng về toàn văn, relevance, gợi ý, bộ lọc và khả năng mở rộng, đồng thời kiến trúc có thể chấp nhận đồng bộ chỉ mục và vận hành thêm một hệ thống. Với CRUD, giao dịch, truy vấn quan hệ hoặc tìm kiếm cơ bản, hãy bắt đầu từ cơ sở dữ liệu đang có và đo hiệu năng trước. Công cụ phù hợp là công cụ đáp ứng yêu cầu thực tế với tổng độ phức tạp và chi phí có thể kiểm soát.
