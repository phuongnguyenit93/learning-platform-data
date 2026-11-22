# Phân chia DocumentOperations, SearchOperations và IndexOperations

Spring Data Elasticsearch cung cấp nhiều abstraction để ứng dụng Java làm việc với Elasticsearch. Ba abstraction thường gặp là DocumentOperations, SearchOperations và IndexOperations. Chúng cùng liên quan đến dữ liệu trong index nhưng phục vụ ba nhóm công việc khác nhau:

- **DocumentOperations:** tạo, đọc, cập nhật và xóa document; hỗ trợ các thao tác ghi theo lô.
- **SearchOperations:** xây dựng và thực hiện truy vấn tìm kiếm, đếm kết quả, phân trang và nhận metadata của search hit.
- **IndexOperations:** quản lý chính index như tạo/xóa index, đọc hoặc cập nhật mapping, settings, alias và refresh.

ElasticsearchOperations là facade tổng hợp để ứng dụng sử dụng các thao tác document và search, đồng thời cung cấp cách lấy IndexOperations cho một index cụ thể. Hiểu ranh giới này giúp đặt logic đúng tầng: lưu entity không phải là tạo index, tìm document không phải là đọc mapping, và quản lý index không phải là xử lý từng document.

## 1. Nhìn tổng thể các abstraction

Có thể hình dung quan hệ giữa các thành phần như sau:

~~~text
                 ElasticsearchOperations
                   /                 \
                  /                   \
       DocumentOperations          SearchOperations
       - save / get                - search
       - exists / delete            - count
       - bulk write                 - paging / scroll
                  \                   /
                   \                 /
                    ElasticsearchTemplate
                            |
                            | indexOps(...)
                            v
                     IndexOperations
                     - create / delete
                     - mapping / settings
                     - aliases / refresh
~~~

Sơ đồ thể hiện cách phân chia trách nhiệm ở mức API. DocumentOperations và SearchOperations là các nhóm thao tác được cung cấp qua ElasticsearchOperations. IndexOperations là abstraction riêng được lấy từ ElasticsearchOperations bằng indexOps(...), vì nó làm việc với metadata và lifecycle của index.

Các interface cụ thể và một số chữ ký phương thức có thể thay đổi theo release train của Spring Data Elasticsearch. Khi áp dụng, hãy đối chiếu Javadoc của phiên bản đang dùng. Ý nghĩa phân chia trách nhiệm vẫn là cơ sở để chọn đúng API.

## 2. ElasticsearchOperations là điểm truy cập tổng hợp

Trong ứng dụng, có thể inject ElasticsearchOperations để sử dụng các thao tác cấp cao mà không phải tự tạo và quản lý Elasticsearch Java Client ở mọi service.

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

ElasticsearchOperations làm việc với entity metadata của Spring Data, vì vậy các thao tác theo entity type có thể dùng thông tin từ @Document, @Id và @Field. Nó cũng cho phép chỉ định IndexCoordinates khi một thao tác cần nhắm đến index cụ thể.

Facade này phù hợp khi service cần phối hợp lưu document, tìm kiếm và thao tác index trong cùng một luồng nghiệp vụ. Nếu một service chỉ cần tìm kiếm, có thể phụ thuộc vào abstraction hẹp hơn nếu phiên bản và cấu hình ứng dụng cho phép inject implementation tương ứng; tuy nhiên trong nhiều ứng dụng, ElasticsearchOperations là điểm truy cập phổ biến và thuận tiện.

## 3. DocumentOperations: thao tác trên từng document

DocumentOperations tập trung vào document đã được lập chỉ mục. Các thao tác thường dùng gồm:

| Thao tác | Mục đích |
|---|---|
| save | Tạo mới hoặc ghi lại document theo ID |
| get | Lấy một document theo ID |
| exists | Kiểm tra document theo ID có tồn tại không |
| delete | Xóa document theo ID |
| bulk operations | Ghi hoặc cập nhật nhiều document trong một đợt |

Đây là abstraction phù hợp cho các luồng đồng bộ một entity hoặc thực hiện CRUD theo ID. Nó không chịu trách nhiệm tạo index template, đặt số shard hay quản lý retention.

### 3.1. Lưu một document

Ví dụ entity:

~~~java
import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    // constructors, getters and setters
}
~~~

Service có thể lưu entity:

~~~java
public Product save(Product product) {
    return operations.save(product);
}
~~~

Spring Data sử dụng metadata của Product để xác định index đích và chuyển entity thành document. Thuộc tính @Id được dùng làm Elasticsearch document ID. Tên index mặc định đến từ metadata @Document, trừ khi thao tác được truyền IndexCoordinates khác.

### 3.2. Lưu vào index được chỉ định

Nếu cùng kiểu entity cần ghi vào một index cụ thể, có thể truyền IndexCoordinates:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public Product saveToArchive(Product product) {
    return operations.save(
            product,
            IndexCoordinates.of("products-archive")
    );
}
~~~

IndexCoordinates là đối tượng mô tả index hoặc tên đích mà thao tác sẽ sử dụng. Nó hữu ích với index theo phiên bản, alias hoặc trường hợp một entity được lưu vào nhiều index. Cần quản lý quy tắc chọn index tập trung để tránh mỗi service tự chọn tên khác nhau.

### 3.3. Đọc document theo ID

~~~java
public Product findById(String id) {
    return operations.get(id, Product.class);
}
~~~

Nếu cần chỉ định index:

~~~java
public Product findInArchive(String id) {
    return operations.get(
            id,
            Product.class,
            IndexCoordinates.of("products-archive")
    );
}
~~~

Phương thức get đọc một document theo ID. Nó phù hợp khi đã biết document ID và không cần chạy truy vấn tìm kiếm theo điều kiện.

### 3.4. Kiểm tra và xóa document

~~~java
public boolean exists(String id) {
    return operations.exists(id, Product.class);
}

public String delete(String id) {
    return operations.delete(id, Product.class);
}
~~~

Các overload chính xác có thể khác nhau giữa phiên bản. Cần chọn overload phù hợp với entity type hoặc IndexCoordinates. Nếu dùng custom routing, thao tác đọc, cập nhật hoặc xóa cũng phải truyền routing nhất quán theo metadata và API tương ứng.

### 3.5. Ghi theo lô

Khi cần nạp nhiều document, bulk operation thường hiệu quả hơn gọi save từng document tuần tự. Spring Data Elasticsearch cung cấp các API bulk qua operations; cách tạo IndexQuery, UpdateQuery hoặc đối tượng bulk cụ thể phụ thuộc phiên bản.

Ví dụ ý tưởng:

~~~java
public void saveAll(List<Product> products) {
    operations.save(products);
}
~~~

Với danh sách lớn, hãy chia thành batch có kích thước phù hợp và kiểm tra kết quả từng item nếu API bulk trả về lỗi theo từng document. Một request bulk có thể được xử lý một phần; không nên coi HTTP request thành công là bằng chứng mọi document đều được ghi.

## 4. SearchOperations: tìm kiếm document theo điều kiện

SearchOperations tập trung vào truy vấn trên index. Nó phù hợp khi ứng dụng cần tìm theo nhiều field, kết hợp điều kiện, xếp hạng, phân trang hoặc nhận thông tin của từng search hit.

Các khả năng thường gặp:

- Thực hiện search query.
- Đếm số document thỏa điều kiện.
- Phân trang và sắp xếp.
- Truy vấn theo Criteria hoặc query native.
- Nhận SearchHits chứa nội dung entity cùng score và metadata.
- Dùng scroll hoặc cơ chế duyệt kết quả lớn khi phù hợp với phiên bản.

SearchOperations không thay thế DocumentOperations. Một search query trả về danh sách hit; một get theo ID là thao tác định vị document cụ thể.

### 4.1. Tạo query bằng Criteria

Ví dụ tìm sản phẩm thuộc danh mục electronics và có giá lớn hơn 100:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public SearchHits<Product> searchExpensiveElectronics() {
    Criteria criteria = new Criteria("category").is("electronics")
            .and("price").greaterThan(100);

    Query query = new CriteriaQuery(criteria);

    return operations.search(query, Product.class);
}
~~~

CriteriaQuery giúp biểu diễn điều kiện truy vấn bằng Java. Nó phù hợp với những bộ lọc đơn giản hoặc vừa phải. Với logic tìm kiếm phức tạp, nhiều nhánh bool, scoring hoặc cú pháp Elasticsearch chuyên biệt, query native có thể dễ kiểm soát hơn.

### 4.2. Chỉ định index cho search

~~~java
public SearchHits<Product> searchArchive(Query query) {
    return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products-archive")
    );
}
~~~

Việc truyền IndexCoordinates giúp truy vấn một index hoặc alias cụ thể. Nếu alias trỏ đến nhiều index, Elasticsearch sẽ tìm trên các index mà alias bao phủ. Cần kiểm tra mapping giữa các index có tương thích với field trong query hay không.

### 4.3. SearchHits và SearchHit

SearchOperations thường trả SearchHits<T> khi cần giữ thông tin đầy đủ của kết quả tìm kiếm. Mỗi SearchHit<T> có thể cung cấp:

- Content đã được chuyển thành entity Java.
- Document ID.
- Score liên quan đến truy vấn.
- Tên index và routing nếu có.
- Highlight fields hoặc metadata tìm kiếm khác tùy query và phiên bản.

Ví dụ:

~~~java
SearchHits<Product> hits = operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();

    System.out.println(product.getId());
    System.out.println(product.getName());
    System.out.println(hit.getScore());
}
~~~

Nếu chỉ cần nội dung entity, có thể chuyển SearchHits thành danh sách content qua API tiện ích phù hợp. Nếu giao diện cần hiển thị độ liên quan, highlight hoặc thông tin phân trang, hãy giữ SearchHits để không làm mất metadata.

### 4.4. Count và phân trang

Khi chỉ cần biết có bao nhiêu document thỏa điều kiện, dùng count thay vì search rồi tải toàn bộ kết quả về ứng dụng:

~~~java
long count = operations.count(query, Product.class);
~~~

Khi cần phân trang, cấu hình Pageable trong query và đọc thông tin trang từ kết quả hoặc dùng repository method trả Page theo abstraction phù hợp. Với offset sâu, cân nhắc giới hạn kết quả và cơ chế search_after cho luồng duyệt lớn. API cụ thể phụ thuộc phiên bản Spring Data Elasticsearch.

## 5. IndexOperations: quản lý index và metadata của index

IndexOperations làm việc ở cấp index, không phải cấp document. Nó được lấy thông qua ElasticsearchOperations:

~~~java
import org.springframework.data.elasticsearch.core.IndexOperations;

IndexOperations indexOperations =
        operations.indexOps(Product.class);
~~~

Hoặc chỉ định tên index:

~~~java
IndexOperations archiveIndexOperations =
        operations.indexOps(IndexCoordinates.of("products-archive"));
~~~

Nhóm công việc thường gặp:

| Thao tác | Mục đích |
|---|---|
| exists | Kiểm tra index có tồn tại |
| create / createWithMapping | Tạo index, có thể kèm mapping |
| delete | Xóa index |
| getMapping | Đọc mapping thực tế |
| putMapping | Cập nhật mapping trong phạm vi Elasticsearch cho phép |
| getSettings | Đọc settings |
| refresh | Yêu cầu refresh index |
| alias operations | Đọc, thêm hoặc xóa alias |
| stats | Đọc thống kê index nếu API phiên bản hỗ trợ |

IndexOperations không lưu Product và không tìm Product theo nội dung. Nó quản lý cấu trúc và trạng thái của index chứa các document.

### 5.1. Kiểm tra index và tạo index

~~~java
public void ensureProductIndex() {
    IndexOperations indexOperations =
            operations.indexOps(Product.class);

    if (!indexOperations.exists()) {
        indexOperations.createWithMapping();
    }
}
~~~

createWithMapping tạo index cùng mapping được Spring Data suy ra từ entity metadata. Đây là cách thuận tiện cho môi trường học tập hoặc ứng dụng có mapping đơn giản.

Trong production, việc tạo index thường thuộc pipeline triển khai hoặc migration chuyên trách. Khi đó entity có thể khai báo createIndex = false để repository bootstrap không tự tạo index. IndexOperations vẫn có thể được dùng bởi bước provisioning có kiểm soát.

Không nên gọi delete rồi create index mỗi lần ứng dụng khởi động. Index có thể chứa dữ liệu quan trọng và được nhiều instance dùng chung.

### 5.2. Đọc mapping và settings

~~~java
public void inspectProductIndex() {
    IndexOperations indexOperations =
            operations.indexOps(Product.class);

    Map<String, Object> mapping = indexOperations.getMapping();
    Map<String, Object> settings = indexOperations.getSettings();

    System.out.println(mapping);
    System.out.println(settings);
}
~~~

Mapping cho biết kiểu field, analyzer, multi-fields, object/nested và các metadata liên quan. Settings cho biết số shard, replica, refresh interval và cấu hình index khác.

Mapping đọc được từ index là cấu hình thực tế. Mapping tạo từ entity bằng createMapping() chỉ là cấu hình Spring Data suy ra từ metadata Java. Hai cấu trúc có thể khác nhau nếu index được tạo bởi template, migration, dynamic mapping hoặc một phiên bản ứng dụng trước.

### 5.3. Cập nhật mapping

Nếu cần thêm field mới và Elasticsearch cho phép, có thể tạo mapping từ entity hoặc định nghĩa mapping tường minh rồi dùng API cập nhật tương ứng:

~~~java
IndexOperations indexOperations =
        operations.indexOps(Product.class);

Document mapping = indexOperations.createMapping();
indexOperations.putMapping(mapping);
~~~

Ví dụ trên minh họa luồng API. Không nên áp dụng nguyên trạng mà chưa kiểm tra mapping được sinh ra và khả năng tương thích với index đang có. Elasticsearch không cho phép đổi tùy ý kiểu của field đã được lập chỉ mục. Một số thay đổi cần tạo index mới, reindex dữ liệu và chuyển alias.

### 5.4. Refresh index

Elasticsearch là hệ thống near real-time. Document vừa ghi có thể chưa xuất hiện ngay trong search cho đến khi index được refresh.

Trong tình huống kiểm thử cần đọc ngay sau khi ghi, có thể dùng refresh policy phù hợp hoặc gọi refresh qua IndexOperations:

~~~java
operations.indexOps(Product.class).refresh();
~~~

Refresh chủ động có chi phí. Không nên gọi refresh sau mỗi lần save trong production chỉ để ép search nhìn thấy document ngay lập tức. Hãy chọn refresh policy dựa trên yêu cầu độ trễ và thông lượng ghi.

## 6. So sánh ranh giới trách nhiệm

| Câu hỏi hoặc nhu cầu | Abstraction phù hợp | Ví dụ |
|---|---|---|
| Lưu một Product | DocumentOperations | save(product) |
| Lấy Product theo ID | DocumentOperations | get(id, Product.class) |
| Xóa document theo ID | DocumentOperations | delete(id, Product.class) |
| Ghi nhiều document | DocumentOperations | bulk/saveAll |
| Tìm Product theo điều kiện | SearchOperations | search(query, Product.class) |
| Đếm kết quả | SearchOperations | count(query, Product.class) |
| Phân trang và đọc score | SearchOperations | SearchHits / Pageable |
| Kiểm tra index có tồn tại | IndexOperations | exists() |
| Tạo index và mapping | IndexOperations | createWithMapping() |
| Đọc mapping/settings | IndexOperations | getMapping(), getSettings() |
| Quản lý alias | IndexOperations | alias operations |
| Refresh index | IndexOperations | refresh() |

Một cách nhớ đơn giản:

- DocumentOperations làm việc với một document hoặc nhóm document.
- SearchOperations làm việc với tập kết quả được xác định bởi query.
- IndexOperations làm việc với cấu trúc và vòng đời của index.

## 7. Repository và Operations khác nhau như thế nào?

Spring Data Elasticsearch còn cung cấp repository abstraction, ví dụ ElasticsearchRepository<Product, String>. Repository giúp ứng dụng khai báo CRUD và query method theo entity type.

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByStatus(String status);
}
~~~

Repository phù hợp cho các thao tác phổ biến, dễ biểu đạt bằng method name hoặc @Query. Khi cần kiểm soát query phức tạp, chỉ định index động, đọc metadata hit hoặc thao tác bulk chuyên biệt, ElasticsearchOperations và các abstraction liên quan linh hoạt hơn.

Hai cách tiếp cận có thể cùng tồn tại trong một ứng dụng:

- Repository phục vụ các use case CRUD và truy vấn thông thường.
- ElasticsearchOperations phục vụ search nâng cao, bulk, truy vấn động hoặc xử lý metadata.
- IndexOperations phục vụ quản lý index trong bước provisioning hoặc công cụ quản trị.

Không cần thay toàn bộ repository bằng Operations. Hãy chọn API theo mức độ kiểm soát mà use case cần.

## 8. Ví dụ tổ chức service theo từng abstraction

Một service tìm kiếm sản phẩm có thể dùng SearchOperations thông qua ElasticsearchOperations:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> searchByCategory(String category) {
        Criteria criteria = new Criteria("category").is(category);
        Query query = new CriteriaQuery(criteria);
        return operations.search(query, Product.class);
    }
}
~~~

Một service quản lý document có thể dùng các thao tác CRUD:

~~~java
@Service
public class ProductDocumentService {

    private final ElasticsearchOperations operations;

    public ProductDocumentService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Product save(Product product) {
        return operations.save(product);
    }

    public Product get(String id) {
        return operations.get(id, Product.class);
    }

    public String delete(String id) {
        return operations.delete(id, Product.class);
    }
}
~~~

Một thành phần khởi tạo index có thể dùng IndexOperations:

~~~java
@Component
public class ProductIndexProvisioner {

    private final ElasticsearchOperations operations;

    public ProductIndexProvisioner(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createIfMissing() {
        IndexOperations indexOperations =
                operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

Trong hệ thống production, ProductIndexProvisioner nên được gọi từ bước triển khai hoặc quy trình quản trị được điều phối, thay vì để nhiều instance ứng dụng tự ý tạo hoặc thay đổi index đồng thời.

## 9. Chọn IndexCoordinates hay entity class?

IndexOperations và các thao tác document/search thường có thể nhận entity class hoặc IndexCoordinates.

Dùng entity class khi:

- Index đích được xác định bởi @Document.
- Mapping và conversion cần dựa trên entity metadata.
- Ứng dụng làm việc với một index mặc định cho entity.

Dùng IndexCoordinates khi:

- Cần truy cập alias hoặc index cụ thể.
- Cùng kiểu entity được lưu ở nhiều index.
- Có index vật lý theo phiên bản hoặc archive.
- Muốn thao tác với một index không gắn trực tiếp với entity class.

Ví dụ:

~~~java
IndexOperations byEntity =
        operations.indexOps(Product.class);

IndexOperations byName =
        operations.indexOps(IndexCoordinates.of("products-v2"));
~~~

Khi dùng IndexCoordinates, hãy bảo đảm entity mapping tương thích với index được chỉ định. Chỉ thay tên index không làm cho schema của hai index trở nên giống nhau.

## 10. Các điểm cần chú ý về phiên bản và cấu hình

Spring Data Elasticsearch đã thay đổi theo thời gian cùng với Elasticsearch client. Một số khác biệt có thể gặp:

- Tên concrete template hoặc client được dùng bên dưới.
- Chữ ký method, overload và kiểu trả về.
- API tạo query, NativeQuery, CriteriaQuery và bulk.
- Cách cấu hình client, mapping context và custom conversions.
- Một số thao tác scroll hoặc index administration có thể thay đổi hoặc được khuyến nghị thay thế.

Vì vậy, không nên sao chép một ví dụ từ tài liệu của release train khác mà không kiểm tra dependency thực tế. Hãy xác nhận phiên bản Spring Boot, Spring Data Elasticsearch, Elasticsearch Java Client và Elasticsearch server đang sử dụng.

Các abstraction có thể giữ tên và mục tiêu tương tự nhưng method signature cụ thể vẫn có thể khác. Nếu IDE báo không tìm thấy method, hãy kiểm tra API của dependency đã resolve thay vì thay thế bằng một method có tên gần giống từ phiên bản khác.

## 11. Những lỗi thiết kế thường gặp

### 11.1. Dùng IndexOperations để lưu document

IndexOperations quản lý index metadata. Lưu entity phải dùng DocumentOperations, ElasticsearchOperations hoặc repository. Nhầm hai tầng khiến service phức tạp và khó hiểu.

### 11.2. Dùng DocumentOperations để tìm kiếm toàn văn

get theo ID không thay thế search query. Nếu cần lọc theo nhiều field, xếp hạng hoặc phân trang, hãy dùng SearchOperations.

### 11.3. Tạo index trong mỗi request nghiệp vụ

Kiểm tra và tạo index không nên nằm trong đường đi của mọi request save/search. Index lifecycle là trách nhiệm provisioning; thực hiện lặp lại gây thêm độ trễ và có thể tạo race condition.

### 11.4. Coi save là bằng chứng document đã tìm thấy ngay

Elasticsearch near real-time. Sau save, document có thể chưa xuất hiện trong search cho đến lần refresh tiếp theo. Nếu cần xác nhận theo ID, dùng thao tác get hoặc tồn tại phù hợp; nếu cần search ngay trong test, điều khiển refresh một cách có chủ đích.

### 11.5. Coi mapping sinh từ entity là mapping thực tế

createMapping() phản ánh metadata Java hiện tại. getMapping() phản ánh index đang chạy. Cần đọc mapping thật khi điều tra lỗi hoặc trước khi migration.

### 11.6. Dùng alias như thể đó là index vật lý

Alias có thể trỏ đến một hoặc nhiều index và có thể xác định write index. Khi quản lý index, cần kiểm tra alias target để tránh xóa hoặc restore nhầm đích.

### 11.7. Bỏ qua lỗi theo từng item của bulk

Bulk request có thể chứa item thành công và item thất bại. Hãy đọc kết quả item và retry có chọn lọc; không retry mù quáng toàn bộ batch nếu thao tác có thể gây tác dụng phụ.

## 12. Kiểm thử theo từng abstraction

Mỗi nhóm API cần kiểm thử đúng trách nhiệm:

**DocumentOperations**

- Save tạo hoặc cập nhật document đúng ID.
- Get trả entity đúng kiểu.
- Exists phản ánh document tồn tại.
- Delete xóa đúng document và routing nếu có.
- Bulk kiểm tra kết quả từng item và xử lý lỗi.

**SearchOperations**

- Query trả đúng tập kết quả.
- Mapping text/keyword cho kết quả phù hợp.
- Sort, score, highlight và phân trang được giữ đúng.
- Count phù hợp với điều kiện query.
- Query qua alias tìm trên đúng index cần thiết.

**IndexOperations**

- Exists phản ánh đúng trạng thái index.
- Create tạo đúng mapping/settings mong đợi.
- GetMapping và getSettings đọc được cấu hình thực tế.
- Alias được trỏ đúng index và write index.
- Refresh được dùng đúng nơi cần kiểm soát khả năng nhìn thấy dữ liệu.

Các bài kiểm thử tích hợp nên dùng Elasticsearch tương thích với phiên bản client của dự án. Mock interface có thể kiểm tra việc service gọi đúng abstraction, nhưng không thể xác nhận mapping, query DSL hoặc hành vi shard thực tế.

## 13. Kết luận

DocumentOperations, SearchOperations và IndexOperations chia API Spring Data Elasticsearch theo đối tượng mà ứng dụng đang thao tác. DocumentOperations xử lý CRUD và bulk document; SearchOperations thực hiện query và trả kết quả tìm kiếm; IndexOperations quản lý index, mapping, settings, alias và refresh.

ElasticsearchOperations cung cấp facade tổng hợp cho document và search, đồng thời cho phép lấy IndexOperations qua indexOps(...). Repository vẫn phù hợp cho CRUD và query method phổ biến; Operations hữu ích khi cần kiểm soát truy vấn, index đích hoặc metadata kết quả.

Hãy chọn abstraction theo trách nhiệm của use case: thao tác document, tìm kiếm một tập kết quả hay quản lý cấu trúc index. Giữ ranh giới này rõ ràng giúp service dễ đọc, dễ kiểm thử và tránh trộn logic nghiệp vụ với lifecycle của Elasticsearch.
