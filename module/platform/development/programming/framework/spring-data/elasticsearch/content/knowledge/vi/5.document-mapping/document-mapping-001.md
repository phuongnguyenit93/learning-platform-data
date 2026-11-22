# @Document, indexName và phạm vi tự tạo index

Trong Spring Data Elasticsearch, @Document khai báo cách một lớp Java đại diện cho document được lưu trong Elasticsearch. Thuộc tính indexName xác định index mà các thao tác với entity hướng đến. Annotation này còn chứa tùy chọn createIndex, quyết định repository infrastructure có tự tạo index khi khởi tạo hay không.

Ba khái niệm cần phân biệt:

- **Entity mapping:** mô tả cách thuộc tính Java được chuyển thành trường trong document và mapping của Elasticsearch.
- **Index target:** xác định index hoặc tên đích mà Spring Data sử dụng cho entity.
- **Index lifecycle:** quyết định khi nào index được tạo, cấu hình settings và mapping ra sao, ai chịu trách nhiệm thay đổi hoặc xóa index.

@Document kết nối entity với metadata của Elasticsearch. Nó không thay thế việc thiết kế mapping, quản lý phiên bản index hoặc quy trình triển khai dữ liệu trong môi trường production.

## 1. Vai trò của @Document

@Document thuộc package org.springframework.data.elasticsearch.annotations. Đặt annotation này trên lớp entity để Spring Data biết lớp đó được lưu dưới dạng document trong Elasticsearch.

Ví dụ:

~~~java
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

    // constructors, getters and setters
}
~~~

Trong ví dụ:

- @Document đánh dấu lớp Product là kiểu document được Spring Data Elasticsearch quản lý.
- indexName chỉ định index đích là products.
- @Id ánh xạ thuộc tính id thành Elasticsearch document ID (_id).
- @Field cung cấp thông tin mapping cho từng trường, chẳng hạn Text để tìm kiếm toàn văn và Keyword để lọc hoặc so khớp chính xác.

@Document cung cấp metadata cho converter, repository và các API thao tác index. Khi lưu entity, Spring Data dùng metadata này để xác định nơi ghi và cách chuyển đối tượng Java thành document. Khi đọc kết quả, converter sử dụng metadata để chuyển document trở lại entity.

Annotation không có nghĩa Elasticsearch sẽ tạo index ngay khi JVM tải lớp Java. Việc tạo index phụ thuộc vào cơ chế khởi tạo repository hoặc lời gọi quản lý index được thực hiện trong ứng dụng.

## 2. indexName xác định đích lưu trữ

indexName là tên index Elasticsearch mà entity hướng đến. Đây là metadata quan trọng vì các thao tác repository thường dựa trên entity type để tìm index tương ứng.

~~~java
@Document(indexName = "products")
public class Product {
    // fields
}
~~~

Khi repository được khai báo:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

Repository biết Product được gắn với index products thông qua metadata của @Document. Ứng dụng không cần lặp lại tên index trong mỗi lời gọi CRUD thông thường.

### 2.1. Tên index phải tuân theo quy tắc Elasticsearch

Elasticsearch có quy tắc đặt tên index riêng. Tên index phải viết thường; không được chứa một số ký tự bị cấm như dấu cách, dấu gạch chéo, dấu phẩy hoặc các ký tự điều khiển. Vì vậy nên dùng tên đơn giản, ổn định và có quy ước nhất quán.

Ví dụ:

| Tên | Nhận xét |
|---|---|
| products | Tên đơn giản, hợp lệ |
| order-events | Có thể dùng dấu gạch ngang |
| customer_profiles | Có thể dùng dấu gạch dưới |
| Products | Không phù hợp vì có chữ hoa |
| product search | Không hợp lệ vì có khoảng trắng |

Nên đặt tên theo loại dữ liệu hoặc mục đích tìm kiếm, không đặt tên theo tên class Java một cách máy móc. Tên index là một phần của hợp đồng triển khai và có thể tồn tại lâu hơn tên class trong mã nguồn.

### 2.2. indexName không phải tên bảng quan hệ

Index Elasticsearch không tương đương hoàn toàn với bảng SQL. Index chứa các document JSON được tổ chức thành shard và được lập chỉ mục theo mapping. Nó không cung cấp mô hình bảng, khóa ngoại và join tổng quát giống cơ sở dữ liệu quan hệ.

Vì vậy indexName = "products" chỉ xác định đích document trong Elasticsearch. Nó không tạo bảng products trong PostgreSQL hoặc MySQL và cũng không tự thiết lập quan hệ với entity JPA.

Nếu cùng một lớp Java được dùng cho nhiều mục đích lưu trữ, cần phân biệt rõ metadata của từng công nghệ. @Document thuộc Spring Data Elasticsearch; @Entity thuộc JPA. Không nên giả định hai annotation này có cùng lifecycle hoặc cùng quy tắc tạo cấu trúc dữ liệu.

### 2.3. Một entity và nhiều index

Một khai báo @Document(indexName = "...") thường mô tả một đích mặc định cho entity. Nếu ứng dụng cần lưu hoặc truy vấn cùng kiểu dữ liệu theo nhiều index, chẳng hạn index theo tháng hoặc theo tenant, có thể dùng các API cấp thấp hơn để chỉ định IndexCoordinates cho thao tác cụ thể.

Ví dụ với ElasticsearchOperations:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void saveToArchive(Product product) {
        operations.save(
                product,
                IndexCoordinates.of("products-archive")
        );
    }
}
~~~

Tên index truyền vào thao tác cụ thể sẽ là đích của thao tác đó. Cần quản lý rõ index nào được ghi, index nào được đọc và cách truy vấn nhiều index để tránh dữ liệu bị phân tán ngoài dự kiến.

Không nên biến việc chọn index động thành logic rải rác trong controller hoặc repository. Hãy đặt quy tắc định tuyến index trong một service có thể kiểm soát và kiểm thử.

## 3. createIndex và phạm vi tự tạo index

@Document có thuộc tính createIndex. Trong các phiên bản Spring Data Elasticsearch hiện hành, giá trị mặc định của thuộc tính này là true.

~~~java
@Document(
    indexName = "products",
    createIndex = true
)
public class Product {
    // fields
}
~~~

Khi Spring Data Elasticsearch khởi tạo repository infrastructure và xử lý entity metadata, tùy chọn này cho phép framework tự tạo index nếu index chưa tồn tại. Việc tạo index có thể sử dụng mapping được suy ra từ entity metadata và các annotation như @Field.

Điểm quan trọng là phạm vi của tùy chọn:

- createIndex = true cho phép cơ chế bootstrap repository tạo index khi cần.
- Nó không có nghĩa mỗi lần gọi save() đều tạo lại index.
- Nó không có nghĩa thay đổi class Java sẽ tự động sửa mọi mapping của index đang tồn tại.
- Nó không thay thế quy trình quản lý settings, mapping migration và index lifecycle của hệ thống.

Hành vi cụ thể còn phụ thuộc phiên bản Spring Data Elasticsearch và cách ứng dụng khởi tạo repository. Cần đối chiếu tài liệu của release train mà dự án đang sử dụng.

### 3.1. Khi index chưa tồn tại

Giả sử ứng dụng khai báo:

~~~java
@Document(indexName = "products", createIndex = true)
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;
}
~~~

Nếu repository được khởi tạo và index products chưa tồn tại, cơ chế bootstrap có thể tạo index cùng mapping dựa trên metadata của entity. Sau đó repository có thể thực hiện các thao tác với index đó.

Luồng khái niệm:

~~~text
Spring application khởi động
          |
          v
Repository infrastructure khởi tạo
          |
          v
Đọc metadata @Document
          |
          v
Kiểm tra index theo indexName
          |
          +---- Index đã tồn tại ----> Dùng index hiện có
          |
          +---- Index chưa tồn tại --> Tạo index và mapping
                                      nếu createIndex = true
~~~

Đây là cơ chế thuận tiện cho ví dụ học tập, môi trường phát triển hoặc ứng dụng có mapping đơn giản và ổn định.

### 3.2. Khi index đã tồn tại

Nếu index products đã tồn tại, framework không cần tạo lại index. Việc khai báo thêm thuộc tính Java hoặc thay đổi @Field không đồng nghĩa mapping cũ được tự động thay thế.

Ví dụ, index hiện tại có trường name được mapping là keyword, nhưng entity mới khai báo:

~~~java
@Field(type = FieldType.Text)
private String name;
~~~

Chỉ sửa annotation trong mã nguồn không biến mapping hiện có thành text. Elasticsearch không cho phép tùy ý đổi một số kiểu mapping của field đã được lập chỉ mục, vì điều đó có thể làm thay đổi cách lưu và tìm kiếm dữ liệu.

Khi mapping cần thay đổi, thường phải thiết kế migration: tạo index mới với mapping đúng, chuyển hoặc reindex dữ liệu, kiểm tra kết quả rồi chuyển alias hoặc ứng dụng sang index mới. Không nên dựa vào createIndex = true để tự xử lý migration.

### 3.3. Khi đặt createIndex = false

Nếu không muốn repository bootstrap tự tạo index, hãy khai báo:

~~~java
@Document(
    indexName = "products",
    createIndex = false
)
public class Product {
    // fields
}
~~~

Khi đó, việc tạo index thuộc trách nhiệm của một quy trình khác, chẳng hạn:

- Script triển khai hoặc migration chạy trước khi ứng dụng khởi động.
- Hạ tầng provisioning tạo index, settings, mapping và alias.
- Một thành phần quản trị index chuyên biệt trong ứng dụng.
- Quy trình vận hành được kiểm soát bởi đội ngũ nền tảng dữ liệu.

createIndex = false chỉ điều khiển hành vi tự tạo index trong repository bootstrap. Nó không cấm ứng dụng gọi API quản lý index một cách tường minh. Nếu index chưa tồn tại mà ứng dụng bắt đầu ghi hoặc tìm kiếm, thao tác có thể thất bại cho đến khi index được tạo.

## 4. Tự tạo index và chủ động quản lý index là hai cách vận hành khác nhau

Có thể chia trách nhiệm tạo index thành hai mô hình.

| Mô hình | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Repository bootstrap tự tạo | @Document(createIndex = true) cho phép Spring Data tạo index khi repository khởi tạo nếu index chưa tồn tại | Học tập, phát triển, ứng dụng nhỏ, mapping đơn giản |
| Chủ động provisioning | createIndex = false; migration hoặc quy trình triển khai tạo index trước | Production, mapping phức tạp, cần kiểm soát settings, alias và lịch sử thay đổi |

### 4.1. Dùng IndexOperations để tạo index có chủ đích

Spring Data Elasticsearch cung cấp IndexOperations để kiểm tra và quản lý index. Có thể lấy đối tượng này từ ElasticsearchOperations theo entity type:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.IndexOperations;
import org.springframework.stereotype.Component;

@Component
public class ProductIndexInitializer {

    private final ElasticsearchOperations operations;

    public ProductIndexInitializer(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void initialize() {
        IndexOperations indexOperations =
                operations.indexOps(Product.class);

        if (!indexOperations.exists()) {
            indexOperations.createWithMapping();
        }
    }
}
~~~

indexOps(Product.class) lấy thông tin index từ metadata của Product, bao gồm indexName. exists() kiểm tra index đích đã tồn tại hay chưa. createWithMapping() tạo index cùng mapping được xây dựng từ entity metadata.

Đây là ví dụ minh họa cho việc ứng dụng chủ động gọi API tạo index. Trong hệ thống nhiều instance, không nên để mọi instance đồng thời chạy một quy trình tạo index không có điều phối. Hãy dùng migration hoặc một bước triển khai chạy một lần, hoặc có cơ chế xử lý tranh chấp và lỗi khởi tạo phù hợp.

Nếu cần settings riêng như analyzer, số shard, replica hoặc cấu hình lưu trữ, hãy chuẩn bị settings cùng mapping trong bước provisioning. createWithMapping() tiện lợi khi dùng mapping từ entity và cấu hình mặc định; nó không tự thay thế một bộ cấu hình index production đầy đủ.

### 4.2. Vì sao không nên xóa rồi tạo lại index mỗi lần khởi động?

Index có thể chứa dữ liệu nghiệp vụ và được nhiều instance ứng dụng sử dụng. Nếu mỗi lần khởi động đều xóa rồi tạo lại:

- Dữ liệu đã lập chỉ mục có thể bị mất.
- Các instance đang chạy có thể gặp lỗi truy vấn hoặc ghi.
- Quá trình khởi động có thể kéo dài do phải nạp lại dữ liệu.
- Một lần deploy ứng dụng có thể vô tình trở thành thao tác phá hủy dữ liệu.

Khởi tạo index cần có tính idempotent: chạy lại không làm mất dữ liệu hoặc thay đổi trạng thái ngoài dự kiến. Với production, hãy tách rõ bước kiểm tra, tạo index mới, reindex và chuyển alias.

## 5. @Document kết hợp với mapping của entity

@Document xác định index và các tùy chọn cấp document/index. Mapping của các trường được mô tả bằng metadata entity, đặc biệt là @Field.

Ví dụ:

~~~java
@Document(indexName = "articles", createIndex = true)
public class Article {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String content;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Date)
    private Instant publishedAt;
}
~~~

Trong ví dụ:

- title và content là trường văn bản, phù hợp cho truy vấn toàn văn.
- status là keyword, phù hợp cho điều kiện lọc chính xác và aggregation.
- publishedAt được ánh xạ thành kiểu ngày tháng để sắp xếp hoặc lọc theo thời gian.

Mapping được suy ra từ entity metadata khi Spring Data tạo mapping. Tuy nhiên, mapping tự suy ra không phải lúc nào cũng đáp ứng yêu cầu tìm kiếm. Analyzer, normalizer, multi-fields, dynamic mapping và các thiết lập đặc biệt có thể cần được khai báo rõ trong mapping hoặc settings.

Khi thiết kế mapping, cần xuất phát từ truy vấn thực tế:

| Nhu cầu | Hướng mapping thường dùng |
|---|---|
| Tìm từ trong nội dung | text với analyzer phù hợp |
| Lọc theo trạng thái hoặc mã | keyword |
| Sắp xếp theo thời điểm | date |
| Lọc hoặc tính toán số | Kiểu số phù hợp như integer, long, double |
| Tìm văn bản nhưng vẫn sort theo giá trị nguyên bản | text kết hợp multi-field keyword nếu cần |

Không nên chỉ dựa vào kiểu Java để suy luận toàn bộ hành vi tìm kiếm. Hãy xác định rõ mapping được tạo ra và kiểm tra nó trên index thực tế.

## 6. Dùng alias và index có phiên bản

Trong production, tên index vật lý có thể mang phiên bản, ví dụ products-v1, products-v2. Ứng dụng có thể làm việc thông qua alias ổn định như products-read hoặc products-write, còn đội ngũ vận hành quản lý việc alias trỏ đến index vật lý nào.

Ví dụ kiến trúc:

~~~text
Spring Data entity
indexName = "products-write"
          |
          v
      write alias
          |
          v
    products-v2

read alias
          |
          v
    products-v2
~~~

Trong mô hình alias-managed, index được tạo trước bằng migration hoặc deployment. Entity có thể tham chiếu alias ổn định, nhưng nên tắt tự tạo index trong repository bootstrap:

~~~java
@Document(
    indexName = "products-write",
    createIndex = false
)
public class Product {
    // fields
}
~~~

Nếu alias chưa tồn tại mà cơ chế bootstrap cố tạo index theo tên products-write, ứng dụng có thể vô tình tạo một index thật mang tên alias dự kiến. Vì vậy cần thống nhất ai tạo alias, ai tạo index vật lý và thứ tự các bước triển khai.

Một quy trình chuyển phiên bản có thể gồm:

1. Tạo products-v2 với settings và mapping mới.
2. Reindex dữ liệu từ index hiện tại sang products-v2.
3. Kiểm tra số lượng document và các truy vấn quan trọng.
4. Chuyển alias đọc/ghi sang index mới theo một thao tác alias có kiểm soát.
5. Chỉ xóa index cũ sau thời gian xác nhận và theo chính sách lưu giữ.

Alias cho phép thay đổi index vật lý mà ứng dụng vẫn dùng một tên logic ổn định. Nó không tự thực hiện migration dữ liệu hoặc bảo đảm hai index tương thích.

## 7. Chọn phạm vi tự tạo index theo môi trường

Một cấu hình thuận tiện ở local có thể không phù hợp production. Hãy chọn lifecycle dựa trên mức độ kiểm soát cần thiết.

| Môi trường | Cách tiếp cận có thể chọn | Lý do |
|---|---|---|
| Local learning | createIndex = true | Giảm thao tác chuẩn bị ban đầu |
| Integration test | Tạo index trong bước setup và xóa trong teardown của test | Mỗi lần chạy có trạng thái dữ liệu rõ ràng |
| Development dùng chung | Tạo index bằng migration hoặc script có kiểm soát | Tránh nhiều instance cùng thay đổi schema |
| Staging | Dùng cùng quy trình provisioning như production | Phát hiện lỗi mapping và migration trước khi phát hành |
| Production | Thường dùng createIndex = false, tạo index bằng deployment/migration | Kiểm soát settings, mapping, quyền và thời điểm thay đổi |

Không có một giá trị createIndex phù hợp cho mọi dự án. Điều quan trọng là xác định rõ quy trình nào có quyền tạo index và quy trình nào có quyền thay đổi mapping.

## 8. Các lỗi thường gặp

### 8.1. Nghĩ rằng @Document tự tạo index ngay khi khai báo

Annotation chỉ cung cấp metadata. Index được tạo khi repository bootstrap hoặc code quản lý index thực sự chạy theo cấu hình tương ứng. Nếu ứng dụng không khởi tạo repository và cũng không gọi API tạo index, chỉ khai báo entity không đủ để bảo đảm index xuất hiện.

### 8.2. Nghĩ rằng đổi indexName sẽ di chuyển dữ liệu

Đổi từ products-v1 sang products-v2 chỉ thay đổi đích mà entity hướng đến. Spring Data không tự sao chép document từ index cũ sang index mới. Cần reindex hoặc một quy trình migration riêng.

### 8.3. Nghĩ rằng createIndex = false cấm mọi thao tác tạo index

Thuộc tính này điều khiển repository bootstrap. Code ứng dụng vẫn có thể gọi IndexOperations.create() hoặc createWithMapping(), và script triển khai vẫn có thể tạo index.

### 8.4. Nghĩ rằng createIndex = true tự cập nhật mapping

Tạo index khi index chưa tồn tại và cập nhật mapping của index đã tồn tại là hai việc khác nhau. Thay đổi mapping cần được xem xét theo khả năng cập nhật của Elasticsearch; một số thay đổi đòi hỏi index mới và reindex.

### 8.5. Dùng alias nhưng quên tắt tự tạo index

Nếu indexName là tên alias, repository bootstrap có thể tạo index mang chính tên đó khi alias chưa tồn tại. Trong mô hình alias-managed, cần tạo alias trước và để quy trình triển khai quản lý index vật lý.

### 8.6. Để nhiều instance cùng chạy migration

Nhiều instance cùng kiểm tra index chưa tồn tại rồi cùng tạo có thể phát sinh race condition. Hãy để một bước triển khai chuyên trách tạo index hoặc dùng cơ chế điều phối thích hợp.

## 9. Quy trình lựa chọn thực tế

Khi thêm entity Elasticsearch mới, có thể đi theo trình tự:

1. Xác định dữ liệu và các truy vấn mà entity phục vụ.
2. Chọn indexName ổn định, hợp lệ và có quy ước rõ ràng.
3. Khai báo @Document cùng @Id, @Field cho những trường cần mapping tường minh.
4. Xác định index được tạo trong repository bootstrap hay bởi migration/deployment.
5. Nếu dùng bootstrap, đánh giá createIndex = true và mapping được sinh ra.
6. Nếu dùng provisioning riêng, đặt createIndex = false và tạo settings/mapping trước khi ứng dụng truy cập.
7. Kiểm tra mapping thật trong Elasticsearch, thử truy vấn đại diện và xác nhận thao tác CRUD.
8. Lập quy trình thay đổi mapping, reindex và chuyển alias khi cấu trúc dữ liệu tiến hóa.

Một lựa chọn điển hình cho bài học hoặc ứng dụng nhỏ:

~~~java
@Document(indexName = "products", createIndex = true)
public class Product {
    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;
}
~~~

Một lựa chọn điển hình cho production có migration quản lý index:

~~~java
@Document(indexName = "products-write", createIndex = false)
public class Product {
    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;
}
~~~

Trong ví dụ thứ hai, pipeline triển khai chịu trách nhiệm tạo index vật lý, mapping và alias trước khi ứng dụng bắt đầu nhận lưu lượng.

## 10. Kết luận

@Document khai báo metadata Elasticsearch cho entity; indexName xác định index hoặc tên đích mà các thao tác với entity sử dụng. createIndex kiểm soát việc repository bootstrap có tự tạo index khi index chưa tồn tại hay không và mặc định thường là true.

Với môi trường học tập hoặc ứng dụng nhỏ, tự tạo index giúp bắt đầu nhanh. Với production, mapping phức tạp, alias hoặc quy trình triển khai nhiều phiên bản, nên quản lý index bằng migration/provisioning có kiểm soát và thường đặt createIndex = false.

Hãy xem việc tạo index, định nghĩa mapping và migration là một phần của lifecycle dữ liệu. @Document giúp Spring Data hiểu entity; nó không tự quyết định toàn bộ chiến lược vận hành Elasticsearch cho ứng dụng.
