# Mối liên hệ giữa Spring Data, Elasticsearch và Elasticsearch Java Client

Spring Data Elasticsearch là lớp tích hợp giúp ứng dụng Spring làm việc với Elasticsearch theo cách quen thuộc của hệ sinh thái Spring Data: ánh xạ object Java thành document, khai báo repository, thực hiện CRUD và xây dựng truy vấn. Ở các phiên bản hiện đại, Spring Data Elasticsearch sử dụng Elasticsearch Java Client làm client chính để gửi request đến cụm Elasticsearch.

Ba tên gọi này thuộc ba lớp khác nhau:

- **Elasticsearch** là hệ thống tìm kiếm và phân tích dữ liệu chạy ở phía server. Nó lưu document trong index, lập inverted index và thực thi các thao tác như search, aggregation, indexing và quản lý index.
- **Elasticsearch Java Client** là thư viện Java chính thức do Elastic cung cấp. Nó biểu diễn API của Elasticsearch bằng các request, response và kiểu dữ liệu Java có kiểu rõ ràng, sau đó gửi request qua HTTP transport.
- **Spring Data Elasticsearch** là module tích hợp của Spring Data. Nó cung cấp mapping, repository và các abstraction như ElasticsearchOperations để ứng dụng Spring thao tác với Elasticsearch thuận tiện hơn. Trong dòng phiên bản hiện đại, module này dùng Elasticsearch Java Client ở tầng giao tiếp.

Có thể hình dung quan hệ như sau:

    Ứng dụng Spring Boot
            |
            v
    Spring Data Elasticsearch
    - Repository
    - ElasticsearchOperations
    - Mapping và converter
            |
            v
    Elasticsearch Java Client
    - Request / response có kiểu
    - API cho search, index, update...
            |
            v
    HTTP transport
            |
            v
    Elasticsearch cluster
    - Index
    - Document
    - Search và aggregation

Spring Data Elasticsearch không phải Elasticsearch server, còn Elasticsearch Java Client không phải một repository framework. Chúng phối hợp với nhau ở những tầng khác nhau.

## 1. Spring Data là gì trong mối quan hệ này?

Spring Data là một họ dự án của Spring, cung cấp những cách làm việc với nhiều loại nguồn dữ liệu thông qua các abstraction tương đối nhất quán. Các module cụ thể có thể làm việc với JPA, MongoDB, Redis, Cassandra, Elasticsearch và những hệ thống khác.

Spring Data Elasticsearch là module dành riêng cho Elasticsearch. Nó hiểu mô hình document và API của Elasticsearch, đồng thời tích hợp với các cơ chế chung của Spring Data. Nhờ đó, mã ứng dụng có thể tập trung vào entity và nghiệp vụ tìm kiếm thay vì tự xây dựng mọi HTTP request.

Các trách nhiệm chính của Spring Data Elasticsearch gồm:

1. **Mapping:** chuyển đổi giữa object Java và document JSON của Elasticsearch. Metadata mapping được khai báo bằng các annotation như @Document, @Id và @Field.
2. **Repository:** cung cấp repository interface để thực hiện các thao tác phổ biến và hỗ trợ một số cách tạo truy vấn từ tên phương thức hoặc annotation.
3. **Operations:** cung cấp API cấp cao hơn để lưu, lấy, xóa, tìm kiếm và thực hiện các thao tác trên index.
4. **Query integration:** cho phép xây dựng truy vấn theo abstraction của Spring Data hoặc sử dụng truy vấn native tương ứng với Elasticsearch.
5. **Spring integration:** hỗ trợ dependency injection, cấu hình client, chuyển đổi dữ liệu và tích hợp với vòng đời ứng dụng Spring.

Ví dụ, một class Java có thể biểu diễn document trong index products:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Field(type = FieldType.Text, analyzer = "standard")
        private String name;

        @Field(type = FieldType.Keyword)
        private String category;

        // constructors, getters and setters
    }

Các annotation trên là metadata mà Spring Data Elasticsearch sử dụng khi ánh xạ object. @Document xác định index gắn với entity; @Id đánh dấu trường định danh document; @Field mô tả kiểu trường và các thuộc tính mapping cần thiết.

Từ entity này, ứng dụng có thể khai báo repository:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        List<Product> findByCategory(String category);
    }

Khi ứng dụng gọi productRepository.findByCategory("book"), Spring Data nhận lời gọi repository, diễn giải phương thức theo quy tắc truy vấn của module Elasticsearch, tạo thao tác phù hợp và chuyển thao tác xuống tầng client. Người viết nghiệp vụ không cần tự tạo HTTP request cho trường hợp thông thường.

Repository không phải nơi lưu dữ liệu. Dữ liệu vẫn nằm trong Elasticsearch cluster. Repository là API ở phía ứng dụng, giúp gọi các thao tác dữ liệu theo phong cách Spring Data.

## 2. Elasticsearch Java Client làm nhiệm vụ gì?

Elasticsearch Java Client là thư viện Java chính thức để gọi API của Elasticsearch. Artifact thường dùng trong các ứng dụng hiện đại là co.elastic.clients:elasticsearch-java. Client cung cấp các kiểu request và response tương ứng với API của server, chẳng hạn search, index, update, delete, create index và bulk.

Một client được cấu hình với thông tin kết nối và một transport. Transport chịu trách nhiệm gửi HTTP request, nhận response và chuyển đổi JSON. Trong cấu hình phổ biến, transport dùng REST client ở tầng HTTP và một JSON-P mapper để tuần tự hóa hoặc giải tuần tự hóa dữ liệu.

Quan hệ giữa các thành phần ở tầng này:

    ElasticsearchClient
            |
            v
    ElasticsearchTransport
            |
            v
    HTTP client / REST transport
            |
            v
    Elasticsearch server

Elasticsearch Java Client có những đặc điểm sau:

- API được sinh theo API của Elasticsearch và dùng các kiểu Java cụ thể cho request, response và query.
- Có thể gọi trực tiếp các endpoint mà không cần Spring Data.
- Có thể được dùng trong ứng dụng Java thuần, ứng dụng Spring hoặc những thành phần không dùng repository.
- Không tự cung cấp mô hình repository của Spring Data và không tự hiểu các annotation mapping của Spring Data.

Ví dụ, gọi trực tiếp API search bằng Elasticsearch Java Client:

    SearchResponse<ProductDocument> response =
        elasticsearchClient.search(
            request -> request
                .index("products")
                .query(query -> query
                    .match(match -> match
                        .field("name")
                        .query("spring data")
                    )
                ),
            ProductDocument.class
        );

Đoạn mã trên thể hiện rõ API Elasticsearch: chỉ định index, tạo match query, gửi request và nhận SearchResponse. Ứng dụng cần tự quyết định cách tổ chức request, xử lý response và chuyển kết quả thành mô hình nghiệp vụ.

Tên ProductDocument trong ví dụ là kiểu dữ liệu dùng để giải tuần tự hóa response của Java Client. Java Client sử dụng mapper được cấu hình cho transport; nó không tự áp dụng MappingElasticsearchConverter hoặc các annotation @Field của Spring Data. Vì vậy, khi gọi client trực tiếp, cần bảo đảm kiểu Java và JSON mapping tương thích với document thực tế.

## 3. Spring Data Elasticsearch kết nối với Java Client như thế nào?

Trong các dòng Spring Data Elasticsearch hiện đại, Elasticsearch Java Client là tầng client mà module sử dụng để giao tiếp với server. Spring Data xây dựng abstraction và mapping ở phía trên; Java Client đảm nhiệm việc gọi API ở phía dưới.

Một lời gọi repository thường đi qua các bước:

1. Service gọi một phương thức trên ElasticsearchRepository.
2. Spring Data xử lý phương thức repository và xác định thao tác cần thực hiện.
3. Mapping metadata và converter của Spring Data chuyển đổi dữ liệu Java thành dạng document hoặc chuyển kết quả trả về thành entity.
4. ElasticsearchOperations/ElasticsearchTemplate điều phối thao tác ở tầng Spring Data.
5. Phần tích hợp client tạo request tương ứng và gọi Elasticsearch Java Client.
6. Java Client gửi request qua transport đến Elasticsearch server.
7. Server thực thi thao tác và trả response.
8. Response được chuyển ngược qua tầng Spring Data để tạo kết quả mà service có thể sử dụng.

Luồng tổng quát:

    Service
      |
      v
    ProductRepository
      |
      v
    ElasticsearchOperations / ElasticsearchTemplate
      |
      v
    Spring Data mapping và client integration
      |
      v
    Elasticsearch Java Client
      |
      v
    Elasticsearch cluster

ElasticsearchOperations là abstraction quan trọng khi cần thao tác linh hoạt hơn repository. ElasticsearchTemplate là một implementation phổ biến của abstraction này. Service có thể phụ thuộc vào ElasticsearchOperations để thực hiện truy vấn, trong khi Spring Data vẫn đảm nhiệm mapping và chuyển đổi entity.

Ví dụ dùng NativeQuery qua ElasticsearchOperations:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("spring data")
            )
        )
        .build();

    SearchHits<Product> hits =
        elasticsearchOperations.search(query, Product.class);

NativeQuery cho phép mô tả truy vấn theo cấu trúc API Elasticsearch. Tuy nhiên, lời gọi vẫn đi qua ElasticsearchOperations, nên Spring Data tiếp tục tham gia vào quá trình ánh xạ kết quả sang Product. Đây là điểm khác với việc gọi trực tiếp ElasticsearchClient.

Không phải mọi phương thức Spring Data đều tương ứng một-một với một phương thức repository hay endpoint cụ thể của Java Client. Spring Data có abstraction và quy tắc riêng; nó chuyển yêu cầu ở mức abstraction thành request phù hợp với API của Elasticsearch.

## 4. Ba cách truy cập Elasticsearch trong ứng dụng Spring

Tùy mức độ phức tạp, ứng dụng có thể làm việc ở một trong ba mức sau.

### Repository

Repository phù hợp với CRUD và các truy vấn thường gặp. Nó giúp service ít phụ thuộc vào chi tiết của request Elasticsearch.

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        List<Product> findByCategory(String category);
    }

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        public List<Product> findBooks() {
            return repository.findByCategory("book");
        }
    }

### ElasticsearchOperations

ElasticsearchOperations phù hợp khi cần kiểm soát truy vấn nhiều hơn repository nhưng vẫn muốn sử dụng mapping và abstraction của Spring Data. Các kiểu như Query, NativeQuery, SearchHits và các API trên ElasticsearchOperations giúp thể hiện truy vấn và kết quả rõ ràng.

Mức này hữu ích khi cần truy vấn phức tạp, kết hợp điều kiện, phân trang, sắp xếp, aggregation hoặc xử lý thông tin search hit mà repository method không diễn đạt thuận tiện.

### Elasticsearch Java Client trực tiếp

Tiêm ElasticsearchClient và gọi API trực tiếp khi cần một endpoint hoặc khả năng mà abstraction Spring Data không cung cấp thuận tiện, hoặc khi thành phần đó chủ động làm việc ở mức API Elasticsearch.

    @Service
    public class ProductIndexService {

        private final ElasticsearchClient client;

        public ProductIndexService(ElasticsearchClient client) {
            this.client = client;
        }

        public SearchResponse<ProductDocument> search(String keyword)
                throws IOException {
            return client.search(
                request -> request
                    .index("products")
                    .query(query -> query
                        .match(match -> match
                            .field("name")
                            .query(keyword)
                        )
                    ),
                ProductDocument.class
            );
        }
    }

Khi dùng client trực tiếp, mã ứng dụng phải quản lý rõ hơn các chi tiết của API: index, query, kiểu response, lỗi và cách chuyển dữ liệu về mô hình nghiệp vụ. Spring Data không tự áp dụng converter, quy tắc mapping hoặc các callback của nó cho lời gọi client trực tiếp.

Ba mức này có thể cùng tồn tại trong một ứng dụng. Ví dụ, repository xử lý CRUD, ElasticsearchOperations xử lý truy vấn tìm kiếm của màn hình, còn Java Client trực tiếp xử lý một thao tác quản trị index đặc thù. Nên chọn abstraction theo trách nhiệm của từng thành phần và giữ cách ánh xạ dữ liệu nhất quán.

## 5. Cấu hình và dependency

Với Spring Boot, cách thông dụng là dùng starter:

    dependencies {
        implementation("org.springframework.boot:spring-boot-starter-data-elasticsearch")
    }

Starter đưa Spring Data Elasticsearch và các dependency tích hợp cần thiết vào ứng dụng. Spring Boot quản lý phiên bản theo bộ dependency tương thích của phiên bản Boot đang dùng. Vì vậy, ứng dụng thông thường không cần tự khai báo một phiên bản Elasticsearch Java Client riêng nếu không có lý do cụ thể.

Ví dụ cấu hình địa chỉ cluster trong application.yml:

    spring:
      elasticsearch:
        uris: http://localhost:9200

Thông tin xác thực và TLS cần được cấu hình theo môi trường triển khai; không nên ghi mật khẩu thật vào file cấu hình được commit vào Git. Có thể đưa các giá trị nhạy cảm qua biến môi trường hoặc secret của môi trường chạy.

Khi Spring Boot tự cấu hình Elasticsearch, các bean client và Spring Data operations tương ứng có thể được inject vào service hoặc repository. Nếu yêu cầu kết nối đặc biệt, ứng dụng có thể cung cấp cấu hình client riêng theo cơ chế mà phiên bản Spring Boot và Spring Data đang dùng hỗ trợ.

Nếu không dùng Spring Boot, ứng dụng có thể khai báo trực tiếp Spring Data Elasticsearch và cấu hình client/transport. Khi đó, ứng dụng phải tự quản lý dependency, bean cấu hình, kết nối và phiên bản tương thích.

## 6. Lưu ý về phiên bản và client cũ

Không phải mọi dự án Spring Data Elasticsearch đều sử dụng cùng một client.

- Từ Spring Data Elasticsearch 5.0, module chuyển sang Elasticsearch Java Client mới thuộc package co.elastic.clients.
- Các dòng Spring Data Elasticsearch 4.x trở về trước thường sử dụng Elasticsearch Rest High Level Client thuộc package org.elasticsearch.client.
- Rest High Level Client là API thế hệ trước. Khi bảo trì dự án cũ, cần đọc tài liệu đúng phiên bản và giữ dependency phù hợp với dòng Spring Data đang chạy.

Do đó, không nên lấy ví dụ cấu hình của một dòng Spring Data rồi áp dụng nguyên trạng cho dòng khác. Cần xác định phiên bản Spring Boot, Spring Data Elasticsearch, Elasticsearch Java Client và Elasticsearch server trước khi chọn tài liệu hoặc thay đổi dependency.

Khi dùng Spring Boot, nên ưu tiên bộ phiên bản được Boot dependency management quản lý. Khi nâng cấp, kiểm tra ma trận tương thích của Spring Data Elasticsearch và Elasticsearch thay vì chỉ tăng riêng phiên bản client. Một ứng dụng có thể biên dịch thành công nhưng vẫn gặp lỗi runtime nếu client, transport, server hoặc cấu hình bảo mật không tương thích.

## 7. Những nhầm lẫn thường gặp

### Nhầm Spring Data Elasticsearch với Elasticsearch

Spring Data Elasticsearch chạy trong ứng dụng Java và cung cấp abstraction để truy cập dữ liệu. Elasticsearch là server độc lập, nhận request và lưu trữ/index document. Thêm Spring Data vào project không có nghĩa là đã có một Elasticsearch cluster đang chạy.

### Nghĩ rằng Java Client thay thế Spring Data

Java Client cung cấp API để gọi Elasticsearch. Nó không tự cung cấp repository, entity mapping theo annotation Spring Data hoặc các abstraction của Spring. Nếu ứng dụng chỉ dùng Java Client, ứng dụng phải tự tổ chức những phần đó khi cần.

### Nghĩ rằng Spring Data không cần Java Client

Ở dòng Spring Data Elasticsearch hiện đại, Java Client là tầng giao tiếp chính. Repository và ElasticsearchOperations là API mà ứng dụng sử dụng; chúng vẫn cần một client và transport để request đến server.

### Dùng annotation Spring Data rồi mong Java Client tự hiểu

@Document, @Id và @Field thuộc mô hình mapping của Spring Data Elasticsearch. Lời gọi ElasticsearchClient trực tiếp dùng mapper của Java Client. Không nên giả định Java Client sẽ đọc các annotation Spring Data hoặc tự áp dụng MappingElasticsearchConverter.

### Trộn dependency của nhiều thế hệ client

Thêm RestHighLevelClient vào một ứng dụng đang dùng dòng Spring Data mới có thể tạo ra cấu hình phức tạp hoặc xung đột dependency. Hãy xác định client mà dòng Spring Data đang hỗ trợ và chỉ thêm client khác khi có yêu cầu kiến trúc rõ ràng.

### Không phân biệt text và keyword

Mapping trường trong Elasticsearch ảnh hưởng trực tiếp đến kết quả truy vấn. Trường text thường được phân tích thành token để tìm kiếm toàn văn; trường keyword giữ giá trị phù hợp cho so khớp chính xác, lọc và aggregation. Annotation @Field cần phản ánh cách ứng dụng truy vấn dữ liệu, không chỉ dựa vào kiểu Java.

## 8. Chọn tầng nào cho một yêu cầu?

| Nhu cầu | Tầng nên bắt đầu |
|---|---|
| Lưu, tìm, cập nhật hoặc xóa entity theo cách thông dụng | ElasticsearchRepository |
| Truy vấn nhiều điều kiện, phân trang, aggregation và cần kết quả gắn với entity | ElasticsearchOperations |
| Cần gọi endpoint cụ thể hoặc API mới mà abstraction chưa hỗ trợ thuận tiện | Elasticsearch Java Client |
| Ứng dụng không dùng Spring Data | Elasticsearch Java Client trực tiếp |
| Ứng dụng cần API reactive | ReactiveElasticsearchRepository hoặc ReactiveElasticsearchOperations theo cấu hình reactive của phiên bản đang dùng |

Với ứng dụng reactive, cần dùng API reactive tương ứng của Spring Data Elasticsearch. ElasticsearchClient là client đồng bộ; không nên gọi nó trực tiếp trong luồng reactive rồi xem lời gọi đó tự trở thành non-blocking.

## Kết luận

Elasticsearch là hệ thống tìm kiếm chạy ở phía server. Elasticsearch Java Client là thư viện Java chính thức để gọi API của hệ thống đó. Spring Data Elasticsearch nằm phía trên client, bổ sung mapping, repository và các abstraction phù hợp với ứng dụng Spring.

Khi gọi repository, ứng dụng đi qua Spring Data trước rồi mới đến Java Client và Elasticsearch server. Khi gọi ElasticsearchClient trực tiếp, ứng dụng làm việc gần API của Elasticsearch hơn và tự chịu trách nhiệm nhiều hơn về request, response và mapping. Hiểu rõ ranh giới này giúp chọn đúng tầng cho từng yêu cầu, cấu hình dependency đúng thế hệ và tránh nhầm lẫn giữa annotation của Spring Data với cơ chế chuyển đổi JSON của Java Client.
