# Phân biệt truy cập Key-Value, truy vấn SQL++ và tìm kiếm toàn văn trong Spring Data Couchbase

## 1. Mục tiêu và bối cảnh

Trong một ứng dụng dùng **Spring Data Couchbase**, ba yêu cầu có thể đều là “lấy sản phẩm” nhưng cần ba cơ chế truy cập rất khác nhau:

1. “Lấy sản phẩm có mã `product::p-1001`” — đã biết **document ID**.
2. “Lọc sản phẩm thuộc nhóm `headphones`, giá dưới 2 triệu, sắp xếp giá tăng dần” — cần truy vấn theo các **trường có cấu trúc**.
3. “Tìm sản phẩm liên quan đến cụm ‘tai nghe chống ồn’ dù câu mô tả không trùng hoàn toàn” — cần **tìm kiếm trên nội dung văn bản** và xếp hạng liên quan.

Couchbase cung cấp các cách giải quyết tương ứng: **Key-Value (KV)**, **SQL++** và **Full-Text Search (FTS, Search Service)**. Spring Data Couchbase hỗ trợ ánh xạ JSON document sang Java object, Repository, `CouchbaseTemplate` và các API reactive; với trường hợp tìm kiếm toàn văn, ứng dụng có thể tích hợp thêm **Couchbase Java SDK Search API**.

Kết thúc bài học, bạn có thể:

- Chọn đúng đường truy cập theo câu hỏi nghiệp vụ và hiểu vì sao mỗi đường có hiệu năng khác nhau.
- Phân biệt document key, secondary index cho SQL++ và Search index cho FTS.
- Viết ví dụ Java/Spring Data cho KV và SQL++; nhận diện cách gọi Search API.
- Giải thích khác biệt về trả kết quả, sắp xếp, phân trang, độ mới dữ liệu và chi phí vận hành.
- Thiết kế luồng kết hợp Search → KV/SQL++ mà vẫn chú ý quyền truy cập, CAS, TTL và tính nhất quán.

## 2. Một kho dữ liệu, ba cách truy cập

Giả sử bucket `catalog` có một document ID là `product::p-1001` trong collection `_default` của scope `_default`. Body JSON minh họa:

~~~json
{
  "name": "Tai nghe Nova Quiet X",
  "category": "headphones",
  "brand": "Nova",
  "priceVnd": 1590000,
  "inStock": true,
  "description": "Tai nghe không dây chống ồn chủ động, pin 40 giờ.",
  "tags": ["bluetooth", "noise cancelling", "wireless"]
}
~~~

**ID không nằm trong body JSON của ví dụ.** ID là metadata của Couchbase; Spring Data thường ánh xạ thuộc tính gắn `@Id` thành metadata key. Nếu ứng dụng tự thêm trường `id` vào JSON, trường đó không tự trở thành metadata ID.

~~~mermaid
flowchart TD
    A["Ứng dụng Spring"] --> B{"Biết rõ document ID?"}
    B -->|Có| C["KV: Data Service"]
    B -->|"Không; lọc/sắp xếp trường"| D["SQL++: Query Service"]
    B -->|"Không; nội dung ngôn ngữ tự nhiên"| E["FTS: Search Service"]
    C --> F[("JSON documents trong Couchbase")]
    D --> I["Secondary index phù hợp"]
    I --> F
    E --> S["Search index + analyzer"]
    S --> F
~~~

Sơ đồ là cách nhìn về luồng truy cập, không phải mô hình triển khai node bắt buộc. Các service có thể chạy trên những node khác nhau; SQL++ có thể truy cập các index và dữ liệu theo kế hoạch thực thi, còn Search Service sử dụng chỉ mục tìm kiếm của riêng nó.

### 2.1. Bảng so sánh nhanh

| Tiêu chí | KV | SQL++ | FTS |
| --- | --- | --- | --- |
| Câu hỏi | “Document có **ID này** là gì?” | “Document nào **thỏa điều kiện**?” | “Nội dung nào **liên quan** đến từ/cụm từ này?” |
| Đầu vào chính | Collection và key chính xác | Câu lệnh với `WHERE`, `ORDER BY`, `JOIN`, `GROUP BY`… | Query văn bản và tùy chọn tìm kiếm |
| Dịch vụ chính | Data Service | Query Service, thường với Index Service | Search Service |
| Chỉ mục cần dùng | Không cần secondary index cho lookup theo ID | Thường cần secondary index phù hợp | Cần Search index |
| Kết quả điển hình | Một document hoặc không có | Tập hàng (rows) theo điều kiện | Hits có ID, điểm liên quan, có thể có highlight/facet |
| Thứ tự kết quả | Không áp dụng với một key | Do `ORDER BY` quyết định | Thường xếp theo **relevance score**, có thể cấu hình sắp xếp |
| Điểm mạnh | Truy cập trực tiếp với chi phí thấp khi biết key | Lọc, kết hợp, tổng hợp dữ liệu có cấu trúc | Phân tích văn bản, search-as-you-type, ranking theo độ liên quan |
| Giới hạn quan trọng | Không dò tìm theo trường hay từ khóa | `LIKE` không thay thế công cụ tìm kiếm văn bản chuyên dụng | Không là nguồn chính để xác nhận bản ghi/số dư/tồn kho chính xác |
| API Java thường gặp | `Repository.findById`, Template, SDK KV | Derived query, `@Query`, Template hoặc SDK query | SDK Search API; có thể phối hợp với Spring Data |

**Mấu chốt:** Ba cơ chế có thể đọc dữ liệu trong cùng Couchbase cluster, nhưng **chúng giải quyết ba loại câu hỏi khác nhau**. Chọn đường truy cập ngay từ thiết kế API giúp tránh tạo index dư thừa hoặc gửi mọi yêu cầu qua một loại query.

## 3. Key-Value: biết khóa là lấy trực tiếp document

### 3.1. KV hoạt động thế nào?

Để đọc sản phẩm `product::p-1001`, ứng dụng cung cấp **bucket/scope/collection đã chọn** và **ID chính xác**. Couchbase tìm giá trị bằng cơ chế KV; thao tác không cần quét tất cả document hay tra cứu secondary index theo trường `name`.

Ở mức khái niệm:

~~~text
Collection: catalog._default._default
Document ID: product::p-1001

GET (collection, "product::p-1001")
    -> body JSON + metadata, nếu document tồn tại
    -> lỗi/không có dữ liệu, nếu không tồn tại
~~~

KV thường phù hợp với:

- Mở chi tiết sản phẩm, hồ sơ khách hàng, đơn hàng đã biết mã.
- Đọc hoặc cập nhật giỏ hàng theo ID người dùng.
- Lấy session bằng session ID.
- Kiểm tra hoặc xóa một document bằng khóa chính xác.

Một ID như `cart::user-42` có thể được **suy ra** từ ID người dùng khi quy ước nghiệp vụ bảo đảm một giỏ hiện hành cho mỗi người. Tiền tố `cart::` chỉ là quy ước đặt tên do ứng dụng chọn. Truy cập KV yêu cầu **toàn bộ khóa**; biết “các key bắt đầu bằng `cart::`” chưa đủ để thực hiện `get` cho cả nhóm.

### 3.2. CRUD theo key và các thao tác có điều kiện

Ở mức Couchbase KV/SDK, cần phân biệt:

| Thao tác | Ý nghĩa | Ví dụ nghiệp vụ |
| --- | --- | --- |
| `get` | Đọc theo key | Xem chi tiết sản phẩm |
| `insert` | Tạo document khi key chưa tồn tại; trùng key là xung đột | Đăng ký một giỏ duy nhất theo ID |
| `upsert` | Tạo mới hoặc thay thế giá trị theo key | Đồng bộ một trạng thái mà ứng dụng chủ động chấp nhận ghi đè |
| `replace` | Thay document đã tồn tại; có thể kèm CAS | Sửa hồ sơ dựa trên phiên bản vừa đọc |
| `remove` | Xóa theo key | Xóa token hết hạn theo yêu cầu |
| Sub-document operations | Chỉ đọc/sửa một phần cấu trúc JSON ở mức SDK | Cập nhật một đường dẫn trường cụ thể |

Trong Spring Data, `repository.save(entity)` là thao tác trên **entity đã được mapping**; không nên giả định nó luôn có ngữ nghĩa giống hệt mọi lệnh `upsert` ở SDK. Cách xác định entity mới, `@Version` và cấu hình mapping có thể ảnh hưởng xử lý insert/update.

### 3.3. KV nhanh nhưng không “tìm kiếm”

Giả sử request hỏi: “Danh sách sản phẩm của hãng Nova dưới 2 triệu”. Nếu chỉ biết `brand` và `priceVnd`, ứng dụng không thể gọi `get` khi chưa biết key. Hai hướng là dùng SQL++/index để tìm document phù hợp, hoặc thiết kế một danh sách ID phụ được cập nhật theo nghiệp vụ; cách thứ hai đòi hỏi xử lý đồng bộ, tính nhất quán và kích thước danh sách.

**Đừng lạm dụng KV bằng cách tải toàn bộ document rồi lọc trong Java.** Cách đó làm tăng truyền dữ liệu, bộ nhớ, độ trễ và khó mở rộng.

## 4. SQL++: điều kiện có cấu trúc, sắp xếp và tổng hợp

### 4.1. SQL++ tìm theo thuộc tính, không cần biết ID trước

SQL++ (trước đây thường gọi là N1QL) là ngôn ngữ truy vấn tài liệu trong Couchbase. Nó cho phép lọc trường, truy cập trường lồng nhau, sắp xếp, phân trang, nối dữ liệu và tổng hợp.

Ví dụ trong collection `catalog._default._default`:

~~~sql
SELECT META(p).id AS documentId, p.name, p.category, p.priceVnd
FROM `catalog`.`_default`.`_default` AS p
WHERE p.category = $category
  AND p.priceVnd <= $maxPriceVnd
ORDER BY p.priceVnd ASC
LIMIT 20;
~~~

Trong một ứng dụng, `$category` và `$maxPriceVnd` cần được truyền dưới dạng **tham số truy vấn**; không tự ghép chuỗi từ đầu vào người dùng để xây dựng câu SQL++. Giá trị ví dụ: `category = "headphones"` và `maxPriceVnd = 2000000`.

Đây là truy vấn SQL++ minh họa, không khẳng định Spring Data sẽ sinh ra đúng từng ký tự SQL++ này. Khi có mapping đa kiểu trong cùng collection, Spring Data có thể bổ sung điều kiện về discriminator/type.

### 4.2. Chỉ mục SQL++ là gì?

Vì SQL++ cần xác định những document có trường `category` và `priceVnd` tương ứng, **secondary index** giúp Query Service tránh quét toàn bộ dữ liệu ở những kế hoạch truy vấn phù hợp.

~~~sql
CREATE INDEX ix_product_category_price
ON `catalog`.`_default`.`_default`(category, priceVnd);
~~~

Chỉ mục trên là **ví dụ bắt đầu** cho điều kiện lọc theo category và price. Thứ tự trường, độ chọn lọc, `ORDER BY`, projection, điều kiện discriminator và lượng dữ liệu quyết định việc index có thật sự tốt hay không.

Để kiểm tra:

~~~sql
EXPLAIN
SELECT META(p).id AS documentId, p.name, p.priceVnd
FROM `catalog`.`_default`.`_default` AS p
WHERE p.category = "headphones"
  AND p.priceVnd <= 2000000
ORDER BY p.priceVnd ASC
LIMIT 20;
~~~

Cần xem kế hoạch thực tế có dùng index mong muốn, có phát sinh fetch/sort tốn kém hay không. Một index phục vụ truy vấn SQL++ **không tự trở thành Search index cho FTS**. Ngược lại, một Search index không mặc nhiên thay thế mọi secondary index cho `WHERE`/`ORDER BY`.

### 4.3. SQL++ mạnh ở những bài toán nào?

| Yêu cầu | Ví dụ điều kiện SQL++ | Vì sao thích hợp |
| --- | --- | --- |
| Lọc trạng thái | `WHERE status = "PAID"` | So sánh chính xác giá trị |
| Lọc khoảng giá | `priceVnd BETWEEN 500000 AND 2000000` | So sánh có thứ tự |
| Lọc khoảng thời gian | `createdAt >= $from AND createdAt < $to` | Lọc theo khoảng |
| Sắp xếp | `ORDER BY priceVnd ASC` | Thứ tự dữ liệu có cấu trúc |
| Tổng hợp | `GROUP BY category`, `COUNT(*)` | Báo cáo đơn giản hoặc đếm nhóm |
| Kết hợp điều kiện | `category = $c AND inStock = true` | Lọc theo nhiều thuộc tính |

SQL++ cũng có `LIKE` để so khớp mẫu ký tự, nhưng phép tìm chuỗi chứa như `LIKE "%chong on%"` thường không có tính năng tokenizer, analyzer, stemming, từ đồng nghĩa hoặc ranking thích hợp cho trải nghiệm tìm kiếm văn bản tự nhiên. SQL++ vẫn có vai trò trong tìm kiếm nâng cao; chỉ cần hiểu khi nào điều kiện cấu trúc là đủ và khi nào nên dùng Search Service.

### 4.4. Index và phân trang có chi phí

- Một secondary index tiêu tốn dung lượng, CPU và tài nguyên cập nhật mỗi khi document liên quan thay đổi.
- `ORDER BY`, `OFFSET` lớn, bộ lọc độ chọn lọc thấp hoặc index thiếu phù hợp có thể tăng độ trễ.
- Với dữ liệu biến động, phân trang dựa trên `OFFSET` có thể thấy phần tử lặp/bỏ sót giữa các trang; cần chọn chiến lược phân trang theo yêu cầu nhất quán.
- Primary index hữu ích trong một số ngữ cảnh phát triển/khám phá dữ liệu nhưng không nên coi quét rộng là kế hoạch truy vấn mặc định cho production.

## 5. Full-Text Search: tìm theo ngôn ngữ, độ liên quan và trải nghiệm người dùng

### 5.1. FTS giải quyết vấn đề mà so sánh chính xác không giải quyết tốt

Người dùng gõ “tai nghe khử ồn”, trong khi document ghi:

> “Tai nghe không dây chống ồn chủ động, pin 40 giờ.”

Từ khóa người dùng có thể khác biểu thức lưu trong JSON. Công cụ tìm kiếm văn bản cần các bước xử lý **phân tích văn bản** và **xếp hạng liên quan**. Couchbase cung cấp **Search Service** (Full-Text Search/FTS) với **Search index** được cấu hình trên các trường cần tìm.

Tùy cấu hình index/analyzer, FTS có thể hỗ trợ:

- **Tokenization:** chia văn bản thành token có thể tra cứu.
- **Normalization:** xử lý chữ hoa/chữ thường và các dạng ký tự phù hợp.
- **Stemming/language analysis:** xử lý biến thể từ, phụ thuộc ngôn ngữ và analyzer có sẵn.
- **Phrase/boolean/fuzzy/prefix query:** các kiểu khớp từ/cụm từ hay gần đúng, phụ thuộc query và cấu hình.
- **Relevance score:** sắp xếp kết quả theo độ phù hợp thay vì một trường giá cố định.
- **Highlight và facet:** đánh dấu đoạn khớp hoặc tổng hợp số lượng theo nhóm trong giao diện tìm kiếm.

Các khả năng trên **không tự động xuất hiện đầy đủ chỉ vì bật FTS**. Cần cấu hình loại field, analyzer, query và thử nghiệm với ngôn ngữ/dữ liệu thực tế. Với tiếng Việt, nên kiểm tra việc tách từ nhiều âm tiết, dấu, lỗi chính tả và cách người dùng nhập không dấu; không mặc định analyzer mặc định sẽ hiểu các quan hệ ngữ nghĩa như “khử ồn” và “chống ồn”.

### 5.2. Search index khác secondary index

| Điểm khác nhau | Secondary index (SQL++) | Search index (FTS) |
| --- | --- | --- |
| Chỉ mục được thiết kế cho | Điều kiện giá trị, khoảng, thứ tự, truy vấn có cấu trúc | Trường văn bản, token và truy vấn tìm kiếm |
| Ví dụ | Chỉ mục theo `(category, priceVnd)` | Index text của `name`, `description`, `tags` |
| Đường truy cập | Query/Index Service | Search Service |
| Cách tạo/quản lý | Câu lệnh `CREATE INDEX` của SQL++ hoặc cơ chế quản trị tương ứng | Cấu hình Search index trong Search Service qua UI/API/tooling |
| Kết quả | Rows theo projection truy vấn | Search hits có ID, score, metadata tìm kiếm |
| Câu hỏi kiểm tra hiệu năng | Index có được chọn? Có scan/fetch/sort rộng không? | Analyzer có phù hợp? Index có giới hạn field? Score và độ trễ có đạt yêu cầu? |

Không thể dùng câu `CREATE INDEX` ở mục SQL++ để tạo ra chỉ mục FTS chuyên dụng. Index tìm kiếm cần lifecycle riêng: định nghĩa, build, theo dõi trạng thái và kiểm soát tài nguyên.

### 5.3. Search index là bản nhìn phục vụ tìm kiếm

Search index được cập nhật dựa trên thay đổi của dữ liệu nguồn. Sau thao tác ghi thành công vào KV, document có thể **chưa ngay lập tức** xuất hiện trong kết quả tìm kiếm FTS. Tương tự, một document vừa bị xóa có thể còn xuất hiện ngắn hạn trong search hit cho đến khi index bắt kịp.

Vì thế, Search hit thường là **gợi ý định vị một document**, không phải bằng chứng cuối cùng rằng sản phẩm đang còn hàng hay người dùng có quyền xem nó. Với thông tin nhạy cảm hoặc thay đổi nhanh, phải xác minh trên dữ liệu nguồn và áp dụng phân quyền ở ứng dụng/dịch vụ.

## 6. Một ví dụ Spring Data Couchbase cho KV và SQL++

Đặt bucket `catalog` và collection mặc định như ví dụ. Ứng dụng Spring Boot cần khai báo starter Spring Data Couchbase tương thích với phiên bản framework:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
}
~~~

Cấu hình thông dụng (cú pháp tùy phiên bản Spring Boot; luôn kiểm tra tài liệu của stack đang dùng):

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: ${COUCHBASE_USERNAME}
    password: ${COUCHBASE_PASSWORD}
  data:
    couchbase:
      bucket-name: catalog
~~~

Cluster và bucket phải tồn tại, tài khoản cần quyền tương ứng. Không đưa mật khẩu thật vào tệp cấu hình được commit. Với scope/collection riêng, cấu hình mapping và quyền truy cập phải đúng keyspace thực tế.

### 6.1. Định nghĩa entity

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Product {

    @Id
    private String id;

    @Field
    private String name;

    @Field
    private String category;

    @Field
    private long priceVnd;

    @Field
    private String description;

    @Version
    private Long version;

    public Product() {}

    public Product(String id, String name, String category,
                   long priceVnd, String description) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.priceVnd = priceVnd;
        this.description = description;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getCategory() { return category; }
    public void setCategory(String category) {
        this.category = category;
    }

    public long getPriceVnd() { return priceVnd; }
    public void setPriceVnd(long priceVnd) {
        this.priceVnd = priceVnd;
    }

    public String getDescription() { return description; }
    public void setDescription(String description) {
        this.description = description;
    }

    public Long getVersion() { return version; }
    public void setVersion(Long version) {
        this.version = version;
    }
}
~~~

- `@Id` chỉ metadata ID; không mặc định xuất hiện trong JSON body.
- `@Field` ánh xạ thuộc tính Java sang field JSON.
- `@Version` hỗ trợ optimistic locking dựa trên CAS khi sửa cùng document.
- Spring Data có thể lưu thêm metadata phân biệt loại entity (thường là discriminator) trong JSON, tùy cấu hình mapping.

### 6.2. Repository: hai phương thức, hai đường truy cập

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<Product, String> {

    List<Product> findByCategoryAndPriceVndLessThanEqual(
            String category, long maxPriceVnd);
}
~~~

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Optional<Product> getDetail(String productId) {
        return repository.findById("product::" + productId);
    }

    public List<Product> listAffordable(String category, long maxPriceVnd) {
        return repository.findByCategoryAndPriceVndLessThanEqual(
                category, maxPriceVnd);
    }
}
~~~

Hai lời gọi quan trọng:

1. `findById(...)`: lookup theo **document ID**, thường đi theo đường KV; không cần secondary index cho chính key này.
2. `findByCategoryAndPriceVndLessThanEqual(...)`: **derived query** từ tên phương thức; Spring Data sinh truy vấn theo thuộc tính, thường thông qua SQL++ và yêu cầu index phù hợp.

Truy vấn dẫn xuất không đồng nghĩa index tự được tạo tối ưu. Cần kiểm tra câu SQL++ thực tế, phân biệt type nếu collection có nhiều entity, dùng `EXPLAIN` và đo với dữ liệu đủ lớn. Tùy yêu cầu, có thể viết truy vấn rõ ràng bằng `@Query` hoặc `CouchbaseTemplate`.

## 7. Tích hợp Search Service từ ứng dụng Spring

Spring Data Couchbase giúp quản lý entity và nhiều trường hợp truy vấn; khi muốn tính năng FTS chuyên dụng, ứng dụng có thể gọi **Couchbase Java SDK Search API** trên cluster đã cấu hình. API chính xác, phạm vi Search index ở cluster/scope và quyền truy cập phải phù hợp với phiên bản SDK/Server.

### 7.1. Ví dụ gọi Search API

Giả sử quản trị viên đã tạo và build một Search index tên `idx_products_text` trên các field `name`, `description`, `tags` của collection sản phẩm, với analyzer phù hợp. Ví dụ Java SDK 3.x ở mức minh họa:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.search.SearchOptions;
import com.couchbase.client.java.search.SearchQuery;
import com.couchbase.client.java.search.result.SearchResult;
import com.couchbase.client.java.search.result.SearchRow;

public class ProductSearchGateway {
    private final Cluster cluster;

    public ProductSearchGateway(Cluster cluster) {
        this.cluster = cluster;
    }

    public void searchByText(String text) {
        SearchResult result = cluster.searchQuery(
                "idx_products_text",
                SearchQuery.match(text),
                SearchOptions.searchOptions().limit(10)
        );

        for (SearchRow row : result.rows()) {
            String documentId = row.id();
            double score = row.score();
            System.out.println(documentId + " -> " + score);
        }
    }
}
~~~

Đoạn trên cho thấy **query văn bản → Search index → danh sách hit gồm ID và score**; không cần biết trước ID sản phẩm. Trong ứng dụng thực tế, thay `System.out.println` bằng DTO trả về service, có validate input, phân trang, timeout, xử lý lỗi, giới hạn số kết quả và quyền xem.

Lưu ý: một số phiên bản SDK/Server hỗ trợ API tìm kiếm theo **scope** thay vì gọi index cấp cluster; ví dụ trên giả định index và API tương ứng đã được cấu hình đúng. Không suy ra rằng tên index SQL++ ở mục 4 là tên Search index này.

### 7.2. Kết hợp FTS với đọc document thực

Search thường trả về hit/metadata, còn màn hình cần thông tin sản phẩm. Một cách phối hợp:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Spring API
    participant S as Search Service
    participant K as KV / Repository
    U->>A: Tìm "tai nghe chống ồn"
    A->>S: Search index theo text
    S-->>A: Hits (ID, score, có thể highlight)
    A->>K: Đọc document theo các ID phù hợp
    K-->>A: Sản phẩm hiện hành
    A-->>U: Kết quả được phép hiển thị
~~~

Trong thực tế cần lưu ý:

- Nếu gọi `findById` tuần tự cho từng hit, ứng dụng có thể phát sinh **N lượt đọc** và tăng độ trễ. Hãy cân nhắc batch, giới hạn hit, projection hoặc chiến lược fetching phù hợp.
- Giữ thứ tự ranking của Search hits khi ghép dữ liệu; không giả định `findAllById` trả cùng thứ tự đầu vào.
- Document có thể bị xóa hoặc đổi trạng thái giữa thời điểm tìm kiếm và đọc KV; xử lý kết quả thiếu và kiểm tra lại trạng thái.
- Áp dụng **phân quyền/tenant** trước khi trả dữ liệu. Search index và search filter là một phần giải pháp, không tự thay thế authorization.
- Một số giải pháp còn kết hợp SQL++ và chức năng tìm kiếm qua tích hợp Search index/`SEARCH()` khi phiên bản và điều kiện hỗ trợ. Đây là lựa chọn nâng cao cần kiểm thử query plan; không mặc định mọi SQL++ đều tự dùng Search index.

### 7.3. Khi nào không nên dùng FTS?

Nếu câu hỏi chỉ là “document ID này”, FTS làm tăng số bước và yêu cầu index không cần thiết. Nếu cần “tồn kho hiện hành = 3” hay “giá nhỏ hơn 500.000 đồng”, đây là điều kiện dữ liệu cấu trúc; SQL++ hoặc KV có điều kiện thường rõ ràng hơn.

FTS nên giải quyết **truy vấn văn bản và ranking**, không nên là nơi quyết định cuối cùng về giao dịch tài chính, hàng tồn hoặc phân quyền nhạy cảm.

## 8. Consistency: tại sao vừa ghi xong chưa thấy trong kết quả?

Giả sử người quản trị tạo sản phẩm `product::p-1002` và ngay lập tức thử ba thao tác:

~~~text
T0  Ghi document thành công theo KV
T1  GET theo key product::p-1002
T2  SQL++: WHERE category = "headphones"
T3  FTS: tìm "tai nghe chống ồn"
~~~

- **KV theo ID** không phụ thuộc secondary/Search index để tìm document.
- **SQL++** thường sử dụng secondary index. Trạng thái index có thể chưa bắt kịp mutation; query với consistency mặc định có thể không thấy document vừa ghi.
- **FTS** dựa trên Search index có pipeline cập nhật riêng; kết quả Search cũng có thể tạm thời chưa thấy bản ghi mới.

Đây là khác biệt **độ mới của kết quả truy vấn**, không phải dấu hiệu chắc chắn thao tác ghi thất bại.

| Yêu cầu nhất quán | Hướng tiếp cận | Đánh đổi |
| --- | --- | --- |
| Vừa lưu xong phải hiển thị chính document đó | Đọc trực tiếp bằng ID | Cần biết key và quyền truy cập |
| SQL++ phải nhìn thấy mutation gần đây | Cân nhắc scan consistency như `request_plus` hoặc consistency gắn mutation token khi API hỗ trợ | Có thể phải đợi index cập nhật, tăng độ trễ |
| Search phải phản ánh mutation trước đó | Xem cơ chế consistency của Search SDK/Server nếu có, hoặc thiết kế UX chấp nhận thời gian cập nhật | Chi phí chờ hoặc giới hạn khả năng ở phiên bản/hệ thống |
| Tồn kho, số dư phải đúng tại thời điểm chốt | Xác nhận bằng KV/truy cập authoritative và quy tắc concurrency/transaction | Cần thêm logic nghiệp vụ và kiểm soát ghi |

**Không dùng một tùy chọn consistency duy nhất cho cả ba đường truy cập mà không kiểm tra semantics từng API.** Các kiểu và cấu hình trong SDK thay đổi theo phiên bản. Hãy đo độ trễ, timeout và hành vi retry khi yêu cầu “đọc sau ghi” thực sự bắt buộc.

CAS giúp phát hiện **cập nhật đồng thời trên cùng document**. Nó khác việc đợi secondary index hoặc Search index cập nhật. Giao dịch nhiều document cũng không đồng nghĩa mọi index tìm kiếm cập nhật đồng thời với lúc commit. TTL cho phép document tự hết hạn; thời điểm nó biến mất khỏi kết quả index/Search còn phụ thuộc quá trình cập nhật liên quan.

## 9. Chọn đường truy cập theo API và workload

| Chức năng ứng dụng | Phương án thường chọn | Lý do và lưu ý |
| --- | --- | --- |
| `GET /products/{id}` | KV qua `findById` | Đã biết key, tránh tìm kiếm không cần thiết |
| `GET /cart` sau khi biết user ID | KV với quy ước `cart::userId` | Lookup một giỏ, chú ý CAS khi cập nhật |
| `GET /products?category=...&maxPrice=...` | SQL++ + secondary index | Lọc/sắp xếp giá trị có cấu trúc |
| `GET /orders?customerId=...&from=...` | SQL++ + index theo mẫu truy vấn | Điều kiện kết hợp, phân trang |
| `GET /search?q=tai+nghe+chong+on` | FTS Search index | Khớp từ/cụm từ, ranking, analyzer |
| Thanh tìm kiếm có gợi ý khi gõ | FTS với thiết kế prefix/auto-complete phù hợp | Kiểm soát độ trễ, analyzer và độ dài truy vấn |
| Đặt hàng sau khi đã tìm kiếm sản phẩm | KV/transaction ở tầng ghi nghiệp vụ | Kiểm tra giá, tồn kho và concurrency lần cuối |
| Dashboard đếm số đơn theo trạng thái | SQL++ aggregate hoặc mô hình dữ liệu tổng hợp riêng | Cân nhắc lượng dữ liệu và yêu cầu cập nhật thời gian thực |

### 9.1. Decision tree có thể áp dụng trong service

~~~mermaid
flowchart TD
    A{"Request cần tìm gì?"}
    A -->|"Một document đã biết ID"| B["KV: get / repository.findById"]
    A -->|"Tập record theo thuộc tính"| C["SQL++ + index"]
    A -->|"Từ ngữ tự nhiên, relevance"| D["FTS + Search index"]
    D --> E{"Có cần body cập nhật / quyền / tồn kho?"}
    E -->|Có| F["Lấy document theo ID, kiểm tra lại"]
    E -->|Không| G["Dùng metadata/search result phù hợp"]
    C --> H["Xem EXPLAIN và đo query latency"]
    B --> I["Xử lý not-found / CAS khi ghi"]
~~~

Khi một màn hình vừa có search text vừa có bộ lọc giá/tình trạng, có thể dùng FTS với filter phù hợp rồi kiểm tra thông tin hiện hành, hoặc cân nhắc tích hợp SQL++/Search nếu phiên bản hỗ trợ. Kiểm thử trên dữ liệu đại diện để tránh áp dụng nhiều lớp lọc tốn tài nguyên và làm mất tính ổn định của phân trang/ranking.

## 10. Vấn đề vận hành và hiệu năng

| Hiện tượng | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `findById` chậm bất thường | Network, nóng một key, timeout, tài nguyên Data Service, kích thước document | Đo latency KV, traffic, phân bố key và kích thước body |
| SQL++ lọc đơn giản nhưng chậm | Thiếu index, chọn index sai, scan/fetch/sort lớn | `EXPLAIN`, index phù hợp, projection và giới hạn kết quả |
| Search không tìm được cụm từ đúng kỳ vọng | Analyzer, mapping field, từ đồng nghĩa, tiếng Việt có dấu/không dấu | Xem cấu hình Search index và đánh giá trên bộ câu truy vấn thật |
| FTS kết quả thiếu sản phẩm mới | Chỉ mục chưa cập nhật hoặc policy consistency | Theo dõi index freshness, cân nhắc UX hoặc cơ chế consistency |
| FTS có kết quả nhưng API trả sai thứ tự | Khi hydrate document đã mất thứ tự Search hit | Ghép theo ID nhưng giữ ranking từ Search |
| Chi phí ghi/index tăng đột biến | Nhiều secondary/Search index, cập nhật document thường xuyên | Rà soát index không cần thiết, capacity và nhịp ghi |
| Tìm kiếm trả sản phẩm đã ngừng bán | Search result không phải xác nhận trạng thái mới nhất | Lọc lại bằng nguồn dữ liệu hiện hành trước khi quyết định |
| Người dùng thấy kết quả ngoài tenant | Không áp dụng authorization/tenant filter thống nhất | Áp dụng phân quyền ở cả truy vấn và bước trả kết quả |

Ở môi trường sản xuất, cần có các chỉ số tối thiểu: KV latency theo percentile, SQL++ latency và query plan, Search latency/hit count, thời gian cập nhật index, timeout/retry, tốc độ mutation và tài nguyên Data/Query/Index/Search Service. Đặt ngân sách độ trễ và số lượng kết quả cho từng API.

**Reactive API:** `ReactiveCouchbaseRepository` hoặc `ReactiveCouchbaseTemplate` có thể giảm chi phí chiếm luồng khi nhiều I/O đồng thời trong ứng dụng Spring WebFlux. Reactive **không thay thế index**, không sửa một truy vấn SQL++ thiếu index hay cải thiện analyzer FTS. Tránh `block()` trong luồng xử lý reactive và kiểm soát backpressure/số thao tác đồng thời khi kết hợp tìm kiếm với nhiều lượt đọc KV.

## 11. Bài tập thực hành

Một cửa hàng có 100.000 sản phẩm trong Couchbase. Mỗi document có ID, tên, nhãn hàng, danh mục, giá, mô tả và tồn kho. Hãy chọn đường truy cập cho từng yêu cầu:

1. Người dùng nhấp vào sản phẩm `product::p-203`.
2. Người dùng lọc “hàng có sẵn, giá từ 1 đến 3 triệu, hãng Nova”.
3. Người dùng gõ “tai nghe chống ồn đeo êm”; muốn kết quả được xếp theo mức độ phù hợp.
4. Sau khi tìm được sản phẩm, người dùng nhấn “Mua”; hệ thống phải kiểm tra tồn kho hiện tại.
5. Quản trị viên cập nhật mô tả sản phẩm; search chưa thấy mô tả mới ngay.

**Gợi ý lời giải:**

| Yêu cầu | Đường truy cập | Giải thích |
| --- | --- | --- |
| 1 | KV | Có document key chính xác |
| 2 | SQL++ | Lọc giá trị có cấu trúc, cân nhắc index cho hãng, trạng thái và khoảng giá |
| 3 | FTS | Cần phân tích nội dung văn bản và relevance |
| 4 | KV/logic ghi có kiểm soát CAS hoặc transaction | Search result không đại diện cho tồn kho authoritative |
| 5 | Theo dõi cập nhật Search index và consistency/UX | Search index có thể trễ hơn mutation |

**Câu hỏi tự kiểm tra:**

- Secondary index SQL++ có cần cho `repository.findById` không? **Không**, khi truy cập chính xác key.
- Có thể dùng `LIKE` trong SQL++ để tìm chuỗi không? **Có**, nhưng phép so khớp chuỗi không tự cung cấp ranking/analyzer như FTS.
- Search index có giống index theo `(category, priceVnd)` không? **Không**; khác mục đích và cách quản lý.
- FTS có thể trả ID mà không trả đầy đủ JSON body không? **Có**; ứng dụng có thể cần đọc document hoặc dùng thông tin lưu trong search hit theo cấu hình.
- Sau thao tác ghi, KV, SQL++ và FTS có cùng độ mới dữ liệu mặc định không? **Không nên giả định như vậy**.
- Thêm `@Version` cho entity có làm Search index cập nhật tức thời không? **Không**; `@Version` giải quyết optimistic locking/CAS khi ghi.

## 12. Kết luận

Chọn **KV** khi đã biết document ID; chọn **SQL++** khi cần lọc, sắp xếp hoặc tổng hợp các trường có cấu trúc; chọn **FTS** khi cần phân tích nội dung văn bản, khớp từ/cụm từ và xếp hạng liên quan. Đây là ba cách truy cập bổ sung cho nhau trong Couchbase.

Trong tầng truy cập Spring Data Couchbase, `CouchbaseRepository` và `CouchbaseTemplate` phù hợp với entity mapping, KV và nhiều truy vấn SQL++; **Couchbase Java SDK Search API** có thể bổ sung tính năng tìm kiếm toàn văn. Để có hiệu năng và tính đúng đắn, hãy thiết kế bucket/scope/collection, ID và từng loại index theo workload thực tế; kiểm soát độ mới của kết quả, TTL, CAS, giao dịch, phân quyền và việc kiểm tra lại dữ liệu trước các quyết định quan trọng.
