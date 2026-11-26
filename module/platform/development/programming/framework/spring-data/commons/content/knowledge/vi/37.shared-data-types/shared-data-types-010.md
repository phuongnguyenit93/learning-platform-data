# Ranh giới giữa kiểu giá trị dùng chung và engine tìm kiếm của store

Một ứng dụng tạo được `Range`, `Point` hoặc `Vector` chưa chứng minh kho dữ liệu có thể tìm kiếm theo kiểu đó. Kiểu Java mô tả giá trị và ý định; query translator, mapping, driver, index và engine của store mới quyết định cách thực thi.

Bài học thuộc chương **Kiểu dữ liệu dùng chung** của module **SPRING_DATA_COMMONS**. Mục tiêu là sử dụng abstraction chung của Spring Data mà vẫn nhận biết những quyết định phải đặt ở mô-đun lưu trữ hoặc ứng dụng: ngữ nghĩa cận, hệ tọa độ, embedding, score, điều kiện lọc, phân trang và khả năng truy vấn thực tế.

## 1. Bốn lớp trách nhiệm trong một truy vấn

Có thể nhìn một yêu cầu tìm kiếm qua bốn lớp:

```text
Ý định của ứng dụng
    |
    v
Kiểu giá trị và hợp đồng Java
    |
    v
Mapping + dịch truy vấn của store module
    |
    v
Driver + database/search engine + index
```

Ví dụ “tìm 10 sản phẩm gần một query embedding, trong khoảng giá đã chọn” cần nhiều quyết định:

| Lớp | Quyết định |
| --- | --- |
| Ứng dụng | Phạm vi tenant, khoảng giá, model tương thích, ý nghĩa “gần” |
| Commons | Dùng kiểu như `Range`, `Vector`, kiểu kết quả phù hợp |
| Store module | Chuyển điều kiện sang ngôn ngữ truy vấn, chuyển kiểu dữ liệu |
| Engine/index | Chọn ứng viên, áp dụng thuật toán tìm kiếm, trả dữ liệu và score |

Commons giúp các lớp giao tiếp bằng những kiểu quen thuộc. Nó không cung cấp một engine tìm kiếm thay thế cho mọi database.

Cũng cần tránh suy luận ngược: hai store sử dụng cùng một lớp Vector không có nghĩa chúng có cùng index, cùng thuật toán, cùng thang điểm hoặc cùng chi phí truy vấn.

## 2. Kiểu dùng chung cam kết điều gì?

| Kiểu hoặc abstraction | Thể hiện trong Java | Không tự cung cấp |
| --- | --- | --- |
| `Range<T>` | Hai cận và ngữ nghĩa nhận/loại giá trị biên | Query range cho mọi property trên mọi store |
| `Point` | Giá trị tọa độ x, y | Toàn bộ quy ước hệ tọa độ và index không gian |
| `Distance` | Độ lớn gắn với metric | Engine tính khoảng cách từ mọi loại tọa độ |
| `Vector` | Dãy số có số chiều cố định | Model tạo embedding và index vector |
| `Score` | Giá trị điểm gắn với ngữ nghĩa scoring | Một thang điểm thống nhất cho mọi engine |
| `GeoResults<T>`, `SearchResults<T>` | Nội dung và metadata của kết quả tương ứng | Khả năng sinh ra kết quả đó từ mọi repository |
| `Pageable`, `Sort` | Ý định phân trang và sắp xếp | Mọi chế độ phân trang hoặc mọi khóa sort đều hợp lệ |

Một số kiểu có thao tác Java hữu ích, chẳng hạn `Range.contains`. Thao tác đó vẫn không phải một truy vấn chạy trong database và không cho biết index nào sẽ được dùng.

Tài liệu Commons lưu ý rằng từ khóa query và kiểu kết quả phải được đối chiếu với từng store. Có thể xem [query keywords](https://docs.spring.io/spring-data/commons/reference/repositories/query-keywords-reference.html) và [query return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html). Các wrapper geospatial chỉ có ý nghĩa thực thi trên những store có khả năng truy vấn tương ứng.

## 3. Tạo đối tượng, lưu dữ liệu và tìm kiếm là ba mức khác nhau

### 3.1. Mức một: biểu diễn giá trị

```java
Range<Integer> quantity = Range.rightOpen(10, 20);
Vector query = Vector.of(0.2f, -0.1f, 0.7f);
```

Đoạn mã này chứng minh ứng dụng có API tương ứng trên classpath và tạo được các đối tượng Java.

Nó chưa chứng minh:

- Một entity có field cùng kiểu sẽ được mapping đúng.
- Driver truyền được biểu diễn native mà database yêu cầu.
- Repository factory hiểu một chữ ký query cụ thể.
- Database đã có cấu hình và index để tìm kiếm.
- Kết quả trả về đáp ứng hợp đồng nghiệp vụ.

### 3.2. Mức hai: mapping và lưu trữ

Một converter có thể chuyển một kiểu Java thành mảng số, document, chuỗi hoặc kiểu native. Đọc lại được cùng dữ liệu là một bằng chứng về đường mapping.

Nhưng lưu Vector thành một mảng số chưa biến mảng đó thành index vector. Lưu Point thành hai số chưa chứng minh engine dùng đúng mô hình địa lý để tìm điểm gần nhất.

### 3.3. Mức ba: thực thi truy vấn có ngữ nghĩa

Một query có thể cần:

```text
Kiểu dữ liệu native đúng
    + toán tử đúng
    + phiên bản server hỗ trợ
    + index hoặc cấu hình tìm kiếm thích hợp
    + tham số query đúng
```

Khi một trong các thành phần này thiếu, hành vi có thể là lỗi, truy vấn chậm hoặc một cách thực thi khác với kỳ vọng. Không dùng việc save thành công làm bằng chứng rằng mọi chức năng tìm kiếm đã sẵn sàng.

## 4. Ví dụ Range: cùng ngữ nghĩa Java, khả năng dịch tùy store

### 4.1. Ý nghĩa của khoảng phải được giữ nguyên

```java
import org.springframework.data.domain.Range;

Range<Integer> quantities = Range.rightOpen(10, 20);
```

Ý định là:

```text
quantity >= 10 AND quantity < 20
```

Một translator đúng cho hợp đồng này phải phân biệt cận trên mở với cận trên đóng. Không thể thay bằng một biểu thức nhận cả hai đầu rồi coi là tương đương.

Cũng cần xác định cách xử lý cận không giới hạn, giá trị null của property và kiểu dữ liệu thực tế của field.

### 4.2. Một ví dụ được hỗ trợ bởi Spring Data MongoDB

Trong phiên bản Spring Data MongoDB có hỗ trợ chữ ký này, có thể khai báo:

```java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.domain.Range;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.repository.MongoRepository;

@Document("stock_items")
record StockItem(
        @Id String id,
        Integer quantity) {
}

interface StockRepository
        extends MongoRepository<StockItem, String> {

    List<StockItem> findByQuantityBetween(
            Range<Integer> quantity);
}
```

Ví dụ giả định Java 17 trở lên, store module và kết nối MongoDB đã được cấu hình, repository được phát hiện và quantity được lưu theo kiểu số phù hợp.

Với:

```java
repository.findByQuantityBetween(
        Range.rightOpen(10, 20));
```

translator của mô-đun hỗ trợ chọn các toán tử cận tương ứng. Tài liệu MongoDB nêu riêng cách `Between` nhận `Range` và quyết định `$gt`, `$gte`, `$lt`, `$lte`; xem [MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html).

Đây là bằng chứng của một đường tích hợp trong một mô-đun cụ thể. Không chuyển chữ ký đó sang một repository của store khác rồi mặc định có cùng hỗ trợ.

Việc query đúng về giá trị còn khác với việc có kế hoạch truy vấn hiệu quả. Kiểu field, phân bố dữ liệu và cấu hình index vẫn thuộc phần cần đánh giá ở store.

## 5. Ví dụ địa lý: Point và Distance chưa định nghĩa toàn bộ phép tìm gần

Có thể tạo các giá trị:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

Point reference = new Point(106.7009, 10.7769);
Distance radius = new Distance(3, Metrics.KILOMETERS);
```

Trong ví dụ này, ứng dụng chủ động quy ước tọa độ đầu là kinh độ, tọa độ sau là vĩ độ trong hệ tọa độ địa lý đã chọn.

Tuy nhiên, riêng constructor `Point(x, y)` không mang theo toàn bộ quyết định về hệ quy chiếu, thứ tự tọa độ của một format native hoặc cách engine tính khoảng cách. `Distance` gắn độ lớn với metric; không tự triển khai một truy vấn tìm mọi địa điểm trong bán kính.

Hợp đồng của hai lớp được mô tả trong [Point API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/Point.html) và [Distance API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/Distance.html).

Trước khi thực thi, cần biết:

| Câu hỏi | Vì sao ảnh hưởng kết quả? |
| --- | --- |
| Store đang nhận tọa độ theo format nào? | Cùng hai con số có thể được diễn giải khác |
| Có đúng hệ tọa độ và đơn vị không? | Không được so độ góc với kilometer như cùng đại lượng |
| Dùng mô hình phẳng hay địa lý? | Ngữ nghĩa khoảng cách khác nhau |
| Toán tử yêu cầu index gì? | Khả năng thực thi và chi phí có thể phụ thuộc index |
| Khoảng cách trả về theo đơn vị nào? | Client phải đọc đúng metadata |

Một `GeoResults<T>` có thể mang nội dung và thông tin khoảng cách. Wrapper này không tự tạo index không gian hoặc sửa dữ liệu tọa độ đã lưu sai.

## 6. Ví dụ vector: biểu diễn embedding không phải engine similarity

Một Vector cho biết tọa độ và số chiều:

```java
import org.springframework.data.domain.Vector;

Vector embedding = Vector.of(
        0.2f,
        -0.1f,
        0.7f);

int dimensions = embedding.size(); // 3
```

Các số chỉ dùng minh họa, không gắn với một model thật.

Để tìm kiếm ngữ nghĩa, còn cần:

- Model hoặc cặp encoder tạo query và tài liệu trong không gian tương thích.
- Dimension, kiểu số và quy tắc chuẩn hóa phù hợp.
- Mapping hoặc converter được store hỗ trợ.
- Index vector và hàm đo đã được cấu hình.
- Query API, giới hạn kết quả và điều kiện lọc hợp lệ.
- Chính sách khi dữ liệu hoặc index chưa đồng bộ.

Cùng số chiều không chứng minh hai embedding từ hai model khác nhau có thể so sánh. Chuyển mảng double sang float cũng không tự biến dữ liệu thành một dạng index mới.

Hạ tầng vector search có thể sử dụng nhiều kiểu biểu diễn và khả năng thực thi riêng. Ví dụ, tài liệu Spring Data MongoDB mô tả index, các tham số query và giới hạn riêng của đường tìm kiếm này; xem [MongoDB Vector Search](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/vector-search.html).

Không dùng `Vector.of` hoặc một annotation mapping như bằng chứng rằng engine đã sinh embedding hay tự xây toàn bộ cấu hình tìm kiếm.

## 7. Score và kiểu kết quả không xóa khác biệt của engine

### 7.1. Một con số giống nhau chưa có cùng ý nghĩa

Giả sử hai hệ thống cùng trả số 0.8. Nó có thể là:

```text
Một similarity đã chuẩn hóa
Một distance sau phép biến đổi
Một điểm relevance theo cấu hình engine
```

Không mặc định đó là xác suất 80% nội dung đúng, và không mặc định ngưỡng 0.8 có thể chuyển nguyên từ engine này sang engine khác.

`Score` mang giá trị và ngữ nghĩa scoring liên quan. Điểm cao hơn có thể thể hiện similarity cao hơn hoặc distance lớn hơn tùy hàm. Xem [Score API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Score.html).

Thông tin về hàm tính điểm mà ứng dụng nhận được cũng phụ thuộc store. Một wrapper không tự suy ra thông tin mà engine không trả về hoặc không thể hiện qua query/index.

### 7.2. Wrapper kết quả giúp tổ chức dữ liệu

`SearchResults<T>` tổ chức các kết quả có nội dung và score tương ứng; nó không phải bộ máy tự so sánh toàn bộ dữ liệu.

Một mô-đun cũng có thể có wrapper riêng với metadata chuyên biệt. Khi chuyển sang DTO chung của ứng dụng, phải quyết định thông tin nào được giữ, thông tin nào được công bố và score được giải thích theo hợp đồng nào.

Không ép một kiểu kết quả tìm kiếm thành `Page<T>` có tổng số bản ghi chính xác nếu đường tìm kiếm chỉ cung cấp top-k. Tổng số phần tử đã nhận không tự trở thành tổng số kết quả của toàn bộ truy vấn.

### 7.3. Sort theo property khác xếp hạng relevance

`Sort.by("title")` diễn tả thứ tự theo thuộc tính title nếu store/query hỗ trợ. Nó không tự có nghĩa “sắp theo relevance rồi dùng title để phân định”.

Tương tự, `Sort.by("score")` không tự biến metadata score ngoài domain thành một property mà mọi translator đều hiểu. Phải xem query API cụ thể hỗ trợ thứ tự nào và nó tương tác với ranking ra sao.

Commons mô tả các abstraction cho vector search, nhưng lưu ý phần thực thi gắn với khả năng store; xem [Vector Search của Commons](https://docs.spring.io/spring-data/commons/reference/repositories/vector-search.html).

## 8. Thiết kế hợp đồng tìm kiếm của ứng dụng

Một cách giữ ranh giới rõ ràng là mô tả yêu cầu nghiệp vụ qua một cổng truy vấn, rồi cài đặt bằng store cụ thể.

Ví dụ sau dùng Java 17 trở lên và Commons 4.0 trở lên vì có `SearchResults`:

```java
import java.math.BigDecimal;

import org.springframework.data.domain.Range;
import org.springframework.data.domain.SearchResults;
import org.springframework.data.domain.Vector;

record CatalogSearchCriteria(
        String trustedTenantId,
        Range<BigDecimal> priceRange,
        Vector queryVector,
        String embeddingSpaceId,
        int topK) {
}

record CatalogItem(
        String id,
        String title) {
}

interface CatalogSearchPort {
    SearchResults<CatalogItem> search(
            CatalogSearchCriteria criteria);
}
```

Đây là interface do ứng dụng định nghĩa, không tự có implementation chỉ nhờ tên `search`. Store adapter phải thực hiện query hoặc ủy quyền tới repository/template/client được hỗ trợ.

Hợp đồng cần được diễn giải rõ:

| Giá trị | Trách nhiệm |
| --- | --- |
| trustedTenantId | Service xác định từ ngữ cảnh hợp lệ, không nhận tùy ý từ client |
| priceRange | Ứng dụng xác minh cận; adapter giữ đúng ngữ nghĩa khi dịch |
| queryVector | Có dimension và dữ liệu phù hợp |
| embeddingSpaceId | Chọn đúng model/index hoặc cấu hình đã được quản lý |
| topK | Có giới hạn của ứng dụng và hợp lệ với engine |

Ví dụ record chưa tự validation các điều kiện trên. Chúng phải được áp dụng tại nơi tạo yêu cầu và tại ranh giới adapter cần thiết.

Luồng adapter có thể là:

```text
Nhận yêu cầu đã kiểm tra
    -> Xác nhận khả năng store và cấu hình index
    -> Dịch Range thành điều kiện native
    -> Gắn phạm vi tenant vào đúng đường lọc
    -> Truyền query vector theo kiểu driver hỗ trợ
    -> Thực thi search với giới hạn phù hợp
    -> Đọc nội dung, score và metadata
    -> Chuyển thành hợp đồng kết quả của ứng dụng
```

Nếu không thể giữ một yêu cầu bắt buộc, adapter phải báo giới hạn hoặc dùng chiến lược thay thế đã được thiết kế tường minh. Không âm thầm bỏ điều kiện chỉ để query chạy được.

## 9. Thứ tự lọc và tìm top-k có thể thay đổi kết quả

Giả sử score lớn hơn là tốt hơn trong một query cụ thể:

| Bản ghi | Tenant | Score |
| --- | --- | --- |
| A | Khác tenant hiện tại | 0.99 |
| B | Khác tenant hiện tại | 0.98 |
| C | Tenant hiện tại | 0.95 |
| D | Tenant hiện tại | 0.90 |

Hai cách làm không tương đương:

```text
Lấy top 2 toàn hệ thống
    -> A, B
    -> Lọc tenant hiện tại
    -> Không còn kết quả

Lọc tenant hiện tại trong phạm vi tìm kiếm
    -> C, D
    -> Lấy top 2
    -> C, D
```

Không thay thế lọc trước tìm kiếm bằng lọc sau top-k rồi vẫn hứa cùng hợp đồng “hai kết quả tốt nhất trong tenant”.

Khả năng kết hợp filter với truy vấn vector hoặc geospatial phụ thuộc engine và đường query cụ thể. Nếu một backend không đáp ứng yêu cầu lọc bắt buộc, ứng dụng phải xử lý giới hạn này ở kiến trúc truy vấn.

Tương tự, một thuật toán tìm gần đúng không tự có cùng cam kết với phép tính exact trên toàn bộ tập dữ liệu. Cần công bố yêu cầu chất lượng và đánh giá trên tập dữ liệu phù hợp; tên Vector không quyết định thuật toán đó.

## 10. Những đường thay thế dễ làm sai hợp đồng

### 10.1. Tải tất cả rồi tìm trong Java

Có thể viết chương trình nhỏ tải dữ liệu và kiểm tra `Range.contains` hoặc tính khoảng cách thủ công. Cách làm đó hữu ích để hiểu ngữ nghĩa hoặc xây dữ liệu đối chiếu nhỏ.

Nhưng nó không tự là đường thay thế tương đương cho truy vấn có index:

- Dữ liệu phải được đọc và truyền về trước khi lọc.
- Chi phí tăng theo lượng dữ liệu cần xét.
- Điều kiện phân trang có thể bị áp dụng trước bộ lọc.
- Phạm vi snapshot và cập nhật đồng thời có thể khác.
- Metadata tổng có thể không còn khớp danh sách.

Nếu chỉ tải một Page rồi lọc trong Java, các phần tử phù hợp ở trang khác không được xét. Kết quả không thể được gọi là toàn bộ kết quả của bộ lọc chỉ vì sử dụng cùng một Range.

### 10.2. Giả lập tìm kiếm ngữ nghĩa bằng phép bằng dữ liệu

So sánh hai mảng số bằng nhau không phải truy vấn similarity. Query by Example hoặc derived query equality không tự trở thành nearest-neighbor search.

Tương tự, một phép chứa chuỗi không tự tương đương full-text search với tokenizer, analyzer, cấu hình ngôn ngữ và ranking của engine. Nếu đổi cơ chế, phải kiểm tra lại ngữ nghĩa mà API đã hứa.

### 10.3. Dùng converter như bằng chứng về khả năng tìm kiếm

Converter giải quyết biểu diễn và chuyển kiểu. Nó không tự thêm toán tử, tạo index hoặc chọn thuật toán.

Ở Spring Data Elasticsearch, tài liệu còn tách rõ `IndexOperations`, `DocumentOperations` và `SearchOperations`; xem [Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html). Sự phân tách này cho thấy quản lý index, lưu tài liệu và tìm kiếm là các nhóm trách nhiệm khác nhau ngay cả trong cùng một mô-đun.

## 11. Phiên bản và metadata vận hành là một phần của khả năng thực tế

### 11.1. Kiểm tra từng API, không chỉ tên dự án Spring Data

Một số mốc cần biết:

| API Commons | Mốc được công bố |
| --- | --- |
| Vector | 3.5 |
| SearchResults | 4.0 |
| Score | 4.0 |

Các mốc nằm trong [Vector API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Vector.html), [SearchResults API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/SearchResults.html) và [Score API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Score.html).

Có Vector trong 3.5 không chứng minh ví dụ dùng SearchResults của 4.x sẽ biên dịch. Có class trên classpath cũng không chứng minh driver hoặc server có tính năng tương ứng.

Các mô-đun Spring Data có thể có số phiên bản khác nhau. Sử dụng bộ dependency tương thích theo cơ chế quản lý của dự án; không nâng riêng một artifact chỉ để có một import mới mà bỏ qua phần còn lại. Cách quản lý phiên bản được mô tả trong [Dependencies của Commons](https://docs.spring.io/spring-data/commons/reference/dependencies.html).

### 11.2. Theo dõi đúng metadata cho từng loại dữ liệu

Một đường truy vấn có thể cần biết:

```text
Khoảng thời gian -> kiểu thời gian, múi giờ, độ chính xác
Dữ liệu địa lý   -> hệ tọa độ, thứ tự tọa độ, đơn vị
Embedding       -> model/revision, dimension, normalization, phiên bản nội dung
Search index    -> schema, cấu hình metric/analyzer, trạng thái sẵn sàng
```

Metadata auditing như thời điểm tạo hoặc người sửa giúp theo dõi domain. Nó không tự cho biết search index đã đồng bộ, embedding thuộc đúng thế hệ model hay một bộ analyzer đã được áp dụng lại cho dữ liệu cũ.

Một lệnh ghi thành công và thời điểm kết quả xuất hiện trong một đường tìm kiếm cũng có thể thuộc hai cơ chế khác nhau. Cần theo hợp đồng của store về khả năng nhìn thấy dữ liệu, thay vì suy ra từ một wrapper Commons.

## 12. Chọn bằng chứng phù hợp với điều muốn xác nhận

| Bằng chứng | Xác nhận được | Chưa xác nhận được |
| --- | --- | --- |
| Tạo được value object trong Java | API và biểu diễn đầu vào tồn tại | Mapping và query của store |
| Ghi rồi đọc lại dữ liệu | Đường chuyển kiểu hoạt động ở tình huống đó | Index hoặc ranking đúng |
| Repository được khởi tạo | Factory chấp nhận cấu hình/chữ ký ở bước khởi tạo | Mọi trường hợp chạy query đều hợp lệ |
| Query trả một danh sách | Có một đường thực thi trả dữ liệu | Đúng cận, phạm vi, metric và hiệu năng |
| Đối chiếu dữ liệu tại biên | Ngữ nghĩa điều kiện ở những giá trị quan trọng | Khả năng vận hành ở dữ liệu lớn |
| Quan sát query và kế hoạch/index | Cách engine thực thi trong môi trường đó | Chất lượng ranking cho mọi nội dung |
| Đánh giá kết quả tìm kiếm theo tập mẫu | Mức phù hợp của ranking theo mục tiêu | Tự động áp dụng cho model/index khác |

Với Range, ưu tiên các giá trị đúng cận và ngay ngoài cận. Với geospatial, dùng điểm có vị trí và khoảng cách đã biết theo hệ quy chiếu được chọn. Với vector search, dùng dữ liệu và query tương thích model, kiểm tra phạm vi lọc và cách diễn giải score.

Kiểu dùng chung giúp diễn đạt yêu cầu bằng một ngôn ngữ Java rõ ràng. Việc đáp ứng yêu cầu đó vẫn phải được chứng minh tại đường mapping, query và engine của store mà ứng dụng thực sự sử dụng.
