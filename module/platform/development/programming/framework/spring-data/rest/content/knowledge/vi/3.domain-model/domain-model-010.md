# Phân biệt hành vi chung của REST exporter và đặc điểm riêng của kho dữ liệu

## Mục tiêu

Spring Data REST giúp công bố Spring Data repository thành các tài nguyên HTTP theo một quy ước thống nhất. Tuy nhiên, cùng một URL hoặc HTTP method không làm cho các database có cùng mô hình dữ liệu, khả năng truy vấn hay cách bảo đảm tính nhất quán.

Bài này phân tách ba phần thường bị nhầm lẫn:

1. Hành vi do Spring Data REST exporter cung cấp khi xuất repository.
2. Hành vi do Spring Data module cụ thể cung cấp khi triển khai repository.
3. Hành vi do database hoặc data store quyết định.

Phân biệt được ba phần này giúp thiết kế API, điều tra lỗi và đánh giá việc chuyển đổi data store chính xác hơn.

## 1. Kiến trúc và ranh giới trách nhiệm

Một request đi qua các lớp theo luồng khái quát sau:

~~~text
HTTP client
    |
    v
Spring Data REST exporter
    |  - phát hiện repository được phép export
    |  - tạo collection, item và search resource
    |  - ánh xạ HTTP request vào repository method
    |  - chuyển đổi representation và HAL links
    |  - áp dụng cấu hình exposure và REST events
    |
    v
Spring Data repository abstraction
    |
    v
Spring Data module tương ứng
    |  - mapping domain object
    |  - tạo và thực thi truy vấn
    |  - xử lý ID và quan hệ theo store
    |  - tích hợp transaction, paging và sorting
    |
    v
Database / data store
       - schema và kiểu dữ liệu
       - index và query plan
       - transaction và consistency
       - giới hạn truy vấn và khả năng lưu trữ
~~~

**Spring Data REST exporter** tập trung vào cách repository được trình bày qua HTTP. Nó cung cấp URL, HTTP method, representation, liên kết và các điểm tùy chỉnh REST.

**Spring Data module** nối repository abstraction với công nghệ lưu trữ cụ thể. Spring Data JPA, MongoDB, Cassandra và Neo4j có mapping, query derivation và khả năng riêng.

**Database** thực thi truy vấn và áp dụng các ràng buộc cuối cùng. Ví dụ, database quan hệ có thể dùng khóa ngoại và join; document database lưu document; Cassandra tổ chức dữ liệu theo partition; Neo4j lưu node và relationship.

Do đó, Spring Data REST có thể tạo API với cấu trúc tương tự trên các repository khác nhau, nhưng không chuẩn hóa toàn bộ hành vi của database phía sau.

## 2. Các hành vi chung của REST exporter

### 2.1. Phát hiện repository và tạo resource

Giả sử ứng dụng có repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PersonRepository
        extends CrudRepository<Person, String> {
}
~~~

Khi repository được phát hiện và được phép export, Spring Data REST thường tạo hai loại resource:

- Collection resource đại diện cho tập hợp: /people
- Item resource đại diện cho một phần tử: /people/{id}

Tên resource mặc định được suy ra từ domain type. Có thể chỉ định đường dẫn và tên quan hệ collection rõ ràng:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people"
)
public interface PersonRepository
        extends CrudRepository<Person, String> {
}
~~~

Nếu cấu hình base path là /api, collection resource có đường dẫn /api/people.

Việc repository được export phụ thuộc cấu hình phát hiện repository và trạng thái exported. Có thể ẩn toàn bộ repository bằng cách đặt exported = false trên @RepositoryRestResource. Có thể ẩn riêng một phương thức bằng @RestResource(exported = false).

Đây là quyết định công bố API. Nó không thay đổi schema hay cách lưu dữ liệu.

### 2.2. Ánh xạ HTTP method

Với repository có các phương thức CRUD tương ứng, exporter có thể cung cấp những thao tác HTTP quen thuộc:

| Resource | HTTP method | Vai trò |
|---|---|---|
| /api/people | GET | Đọc collection |
| /api/people | POST | Tạo resource |
| /api/people/{id} | GET | Đọc một resource |
| /api/people/{id} | PUT | Thay thế trạng thái resource |
| /api/people/{id} | PATCH | Cập nhật một phần resource |
| /api/people/{id} | DELETE | Xóa resource |

Bảng này mô tả ánh xạ REST phổ biến. Các method thực tế phụ thuộc repository interface, phương thức nào được export, cấu hình và khả năng của Spring Data module.

Ví dụ, nếu repository không cung cấp thao tác xóa hoặc phương thức xóa bị ẩn, exporter không thể cung cấp thao tác DELETE tương ứng chỉ bằng cách tạo URL. Tương tự, một repository chỉ đọc không nên được hiểu là có đầy đủ CRUD.

Exporter ánh xạ request sang lời gọi repository. Nó không tự thêm quy tắc nghiệp vụ như “chỉ chủ sở hữu mới được sửa”, “không được xóa người đang có đơn hàng” hoặc “email phải duy nhất”. Các quy tắc này cần được thực thi ở tầng phù hợp bằng validation, service, security hoặc constraint của database.

### 2.3. HAL và hypermedia

Spring Data REST mặc định dùng HAL JSON để biểu diễn resource. Một response có thể có:

- _links: các liên kết tới resource hiện tại, collection, search hoặc resource liên quan.
- _embedded: các phần tử được nhúng trong representation collection.
- page: thông tin phân trang khi repository hỗ trợ paging.

Client có thể bắt đầu từ root URL, đọc liên kết collection rồi tiếp tục theo các liên kết self hoặc quan hệ. Cách tiếp cận này giảm phụ thuộc vào việc client phải tự ghép mọi URL.

HAL là định dạng biểu diễn resource và liên kết. HAL không quy định entity phải lưu trong bảng, document hay graph. Cùng một loại link trong HTTP có thể trỏ tới dữ liệu được lưu bằng các mô hình hoàn toàn khác nhau.

### 2.4. Search resource và query method

Spring Data REST có thể công bố các query method của repository dưới tài nguyên search. Ví dụ:

~~~java
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends CrudRepository<Person, String> {

    @RestResource(path = "by-email", rel = "by-email")
    Optional<Person> findByEmail(
            @Param("email") String email
    );
}
~~~

Endpoint có thể được gọi như sau:

~~~http
GET /api/people/search/by-email?email=linh@example.com
~~~

Exporter chịu trách nhiệm tạo search resource, đặt path và chuyển query parameter vào lời gọi repository. Việc Spring Data module có thể tạo và thực thi query đó hay không phụ thuộc mapping và khả năng truy vấn của store.

Tên method theo quy ước không bảo đảm mọi store hỗ trợ cùng một toán tử. Ví dụ, phép so khớp chuỗi, tìm kiếm không phân biệt hoa thường, truy vấn collection hoặc kết hợp nhiều điều kiện có thể có giới hạn khác nhau giữa JPA, MongoDB và Cassandra.

### 2.5. Projection, event, validation và bảo mật

REST exporter còn cung cấp các điểm mở rộng cho representation và vòng đời request:

- **Projection và excerpt:** điều chỉnh các thuộc tính được hiển thị trong representation.
- **REST events:** cho phép ứng dụng phản ứng trước hoặc sau các thao tác tạo, lưu, cập nhật hay xóa.
- **Validation:** tích hợp các validator của ứng dụng khi dữ liệu được ghi.
- **Repository exposure:** kiểm soát repository hoặc method nào được công bố.
- **Security integration:** kết hợp Spring Security để kiểm soát người dùng và quyền truy cập.

Các tiện ích này tác động đến cách API công khai và xử lý request. Chúng không thay thế index, transaction, consistency level, partition key hay cơ chế quan hệ của data store.

## 3. Đặc điểm riêng của từng Spring Data module

### 3.1. Spring Data JPA: entity và quan hệ trong database quan hệ

JPA ánh xạ domain object thành entity và bảng. Ví dụ:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "people")
public class Person {

    @Id
    private String id;

    @Column(nullable = false)
    private String email;

    protected Person() {
    }

    public Person(String id, String email) {
        this.id = id;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Các đặc điểm thuộc JPA và database quan hệ:

- @Entity và @Table ánh xạ lớp Java tới bảng.
- @Id xác định khóa chính; @Column mô tả một số thuộc tính của cột.
- Quan hệ có thể được khai báo bằng @ManyToOne, @OneToMany, @OneToOne hoặc @ManyToMany.
- Hibernate quản lý persistence context, dirty checking, cascade và fetch strategy.
- Spring Data JPA hỗ trợ derived query, JPQL và native query.
- Transaction và locking phụ thuộc JPA provider, cấu hình transaction và database.
- Database có thể thực thi join, constraint, index và khóa ngoại theo schema.

REST exporter có thể biểu diễn một association bằng liên kết HAL. Tuy nhiên, link HTTP không quyết định quan hệ có cascade hay không, có được tải lazy hay không, hoặc database có ràng buộc khóa ngoại như thế nào.

### 3.2. Spring Data MongoDB: document và collection

MongoDB lưu document trong collection. Domain type thường dùng @Document và @Id:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("people")
public class Person {

    @Id
    private String id;

    private String email;

    public Person() {
    }

    public Person(String id, String email) {
        this.id = id;
        this.email = email;
    }

    public String getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Các đặc điểm thuộc MongoDB và Spring Data MongoDB:

- @Document ánh xạ domain type tới collection.
- Object được chuyển thành document với các field tương ứng.
- Dữ liệu liên quan có thể được nhúng trong document hoặc lưu tham chiếu; không mặc định có join và khóa ngoại như relational database.
- Query method được chuyển thành truy vấn MongoDB theo khả năng của module.
- Index, aggregation, sharding và transaction phụ thuộc MongoDB deployment cùng cấu hình.
- @Version có thể hỗ trợ optimistic locking theo khả năng của module.

Exporter vẫn có thể tạo collection resource, item resource, search link và HAL representation. Nó không chuyển reference của MongoDB thành association có khóa ngoại hay join SQL.

### 3.3. Spring Data Cassandra: partition và query model

Cassandra tổ chức dữ liệu theo table, partition key và clustering column. Domain type thường dùng @Table và @PrimaryKey:

~~~java
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("people")
public class Person {

    @PrimaryKey
    private String id;

    private String email;
}
~~~

Các đặc điểm thuộc Cassandra và Spring Data Cassandra:

- Partition key quyết định dữ liệu được phân vùng như thế nào.
- Clustering column quyết định cách sắp xếp dữ liệu bên trong partition.
- CQL có quy tắc về điều kiện truy vấn; không thể mặc định truy vấn tùy ý như SQL trên database quan hệ.
- Cassandra không cung cấp join và foreign key theo mô hình relational.
- Query method cần phù hợp với primary key, partition design và khả năng của CQL.
- Paging, consistency level và replication có semantics riêng.

Một method có thể được công bố thành search URL nhưng điều đó không chứng minh Cassandra thực hiện được truy vấn tùy ý phía sau. Thiết kế repository phải theo query model của Cassandra. Đặc biệt, truy vấn không phù hợp partition key có thể bị từ chối hoặc cần cấu hình cho phép filtering với chi phí cao.

### 3.4. Spring Data Neo4j: node và relationship

Neo4j lưu dữ liệu dạng graph gồm node và relationship. Domain type thường dùng @Node; các quan hệ được mapping bằng annotation relationship tương ứng.

Các đặc điểm thuộc Neo4j và Spring Data Neo4j:

- Domain model mô tả node và relationship.
- Query có thể cần pattern matching hoặc traversal qua graph.
- Độ sâu traversal, số lượng node và cấu trúc graph ảnh hưởng đến chi phí truy vấn.
- Query language và mapping do Spring Data Neo4j cùng Neo4j quyết định.
- Transaction và các quy tắc truy cập graph thuộc module và database.

Exporter có thể xuất repository thành resource HTTP, nhưng representation REST không làm graph trở thành mô hình bảng và khóa ngoại.

## 4. Bảng phân định trách nhiệm

| Khía cạnh | REST exporter | JPA | MongoDB | Cassandra | Neo4j |
|---|---|---|---|---|---|
| URL collection/item | Tạo theo repository và cấu hình | Không quyết định | Không quyết định | Không quyết định | Không quyết định |
| HAL và link | Biểu diễn resource/link | Metadata entity/association | Metadata document/reference | Metadata repository/entity | Metadata node/relationship |
| HTTP CRUD | Ánh xạ request sang method được export | Thực thi qua JPA | Thực thi qua MongoDB module | Thực thi qua Cassandra module | Thực thi qua Neo4j module |
| Mapping | Không định nghĩa schema store | Entity, table, column | Document, collection, field | Table, partition/clustering key | Node, relationship |
| Query | Công bố query method | JPQL/SQL, derived query | Mongo query, derived query | CQL và giới hạn partition | Graph query |
| Quan hệ | Có thể biểu diễn bằng link | Association, join, khóa ngoại | Embedded document hoặc reference | Thiết kế theo query model | Relationship trong graph |
| Paging/sorting | Chuyển tham số REST khi được hỗ trợ | Theo query và database | Theo query và database | Theo paging/query model của Cassandra | Theo query và module |
| Transaction/consistency | Không định nghĩa semantics của store | Theo JPA/database | Theo MongoDB deployment | Theo consistency level/replication | Theo Neo4j |

Bảng trên phân loại trách nhiệm. Khả năng cụ thể còn phụ thuộc phiên bản Spring Data, repository interface, driver và cấu hình database.

## 5. Cùng hợp đồng REST không có nghĩa cùng semantics

Một repository có thể giữ hình dạng gần giống nhau giữa các store:

~~~java
import java.util.Optional;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people"
)
public interface PersonRepository
        extends CrudRepository<Person, String> {

    @RestResource(path = "by-email", rel = "by-email")
    Optional<Person> findByEmail(
            @Param("email") String email
    );
}
~~~

Với base path /api, client có thể nhìn thấy các đường dẫn như:

~~~text
GET    /api/people
POST   /api/people
GET    /api/people/{id}
PUT    /api/people/{id}
PATCH  /api/people/{id}
DELETE /api/people/{id}
GET    /api/people/search/by-email?email=...
~~~

Đây là ví dụ về hình dạng API. Nó không phải project độc lập chạy được với mọi store. Khi dùng JPA, Person cần mapping JPA; khi dùng MongoDB, Person cần mapping document; khi dùng Cassandra, mapping phải phù hợp primary key; khi dùng Neo4j, domain model phải phù hợp graph.

Ngay cả khi URL không đổi, các yếu tố sau vẫn có thể khác:

- Kiểu ID và cách sinh ID.
- Query method nào được hỗ trợ và cách xử lý chuỗi, null hoặc collection.
- Quan hệ được lưu thành association, embedded document, reference hay graph relationship.
- Paging, sorting, thứ tự kết quả và chi phí truy vấn.
- Transaction boundary, locking, concurrency và consistency.
- Index và giới hạn truy vấn do store áp đặt.

Vì thế, giữ được URL không đồng nghĩa có thể đổi database chỉ bằng cách thay dependency. Việc chuyển store có thể đòi hỏi đổi domain mapping, repository method, query, index, transaction và cách tổ chức dữ liệu.

## 6. Cách xác định lỗi nằm ở exporter hay data store

Giả sử client gọi:

~~~http
GET /api/people/search/by-email?email=linh@example.com
~~~

Có thể điều tra theo thứ tự từ ngoài vào trong:

1. **REST exporter:** repository có được export không? Root HAL có search link không? Path, relation name và query parameter có đúng không? Method có bị ẩn bằng exported = false không?
2. **Repository abstraction:** method có nằm trên repository được phát hiện không? Kiểu tham số và kiểu trả về có phù hợp không?
3. **Spring Data module:** thuộc tính có đúng tên mapping không? Module có hỗ trợ derived query và phép so khớp đang dùng không? Có cần query tường minh không?
4. **Data store:** field hoặc column có tồn tại không? Index có phù hợp không? Query có vi phạm partition key, schema hoặc giới hạn của database không?

Một số tình huống thường gặp:

- **Collection trả chậm:** exporter có thể đã gọi thao tác đọc collection đúng cách; cần kiểm tra paging, lượng dữ liệu, index và query plan của store.
- **Search URL trả 404:** kiểm tra search method có được export, path có đúng và repository có được phát hiện không.
- **Search URL tồn tại nhưng query lỗi:** kiểm tra derived query, mapping và khả năng của module; URL được tạo thành công không bảo đảm query được database hỗ trợ.
- **Item URL không tìm thấy dữ liệu:** kiểm tra ID được truyền, cách module ánh xạ ID và bản ghi thực tế trong store.
- **Quan hệ không được lưu như mong muốn:** kiểm tra cascade, ownership, reference hoặc relationship mapping của module.
- **PATCH không thay đổi một thuộc tính:** kiểm tra JSON binding, projection, representation, validation và mapping. HTTP method không bỏ qua quy tắc persistence.

Điểm quan trọng là tách lỗi công bố HTTP resource khỏi lỗi thực thi repository và lỗi của database. Mỗi lớp có cách quan sát và cách sửa khác nhau.

## 7. Hướng dẫn thiết kế khi dùng nhiều data store

- Giữ cấu hình resource path, relation name và exposure ở tầng REST để API có quy ước dễ hiểu.
- Mapping domain type theo đúng mô hình của store; không ép entity quan hệ, document và graph dùng chung một bộ annotation.
- Chỉ công bố query method mà Spring Data module hỗ trợ. Kiểm tra truy vấn thực tế trên database mục tiêu.
- Thiết kế index, partition key, association hoặc graph relationship ở tầng data store.
- Không giả định mọi store có cùng transaction boundary, isolation, locking hoặc consistency.
- Dùng test tích hợp với từng store thực tế. Database nhúng hoặc in-memory có thể không tái hiện giới hạn partition, index, transaction và consistency của production.
- Nếu API cần DTO riêng, nhiều bước nghiệp vụ, phân quyền theo nghiệp vụ hoặc response contract độc lập domain model, cân nhắc service/controller tường minh thay vì export trực tiếp repository.
- Khi chuyển store, đánh giá lại dữ liệu, query, ID, quan hệ, paging, transaction và chi phí truy vấn. Giữ nguyên URL chỉ giải quyết một phần của tương thích API.

## 8. Checklist khi chuyển đổi data store

1. Domain type đang dùng annotation mapping nào? Annotation đó có phù hợp với module mới không?
2. Kiểu ID và cơ chế sinh ID có tương thích với item resource không?
3. Mỗi query method có được module mới hỗ trợ không?
4. Query có cần đổi để phù hợp index, partition key hoặc graph pattern không?
5. Association có cần chuyển thành embedded document, reference hoặc graph relationship không?
6. API đang dựa vào thứ tự, paging, sorting hay tổng số phần tử nào? Store mới có cùng semantics không?
7. Transaction và concurrency hiện tại dựa vào guarantee nào? Store mới có cung cấp tương đương không?
8. Các test tích hợp có chạy trên database và cấu hình gần production không?
9. HAL links, representation, status code và lỗi trả về có còn phù hợp với client không?

Nếu một câu trả lời thay đổi, cần đánh giá tác động tới nghiệp vụ và API trước khi chuyển đổi.

## Tài liệu tham khảo

- [Spring Data REST – Getting started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST – Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST – Customizing repository exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data JPA – Reference documentation](https://docs.spring.io/spring-data/jpa/reference/)
- [Spring Data MongoDB – Reference documentation](https://docs.spring.io/spring-data/mongodb/reference/)
- [Spring Data Cassandra – Reference documentation](https://docs.spring.io/spring-data/cassandra/reference/)
- [Spring Data Neo4j – Reference documentation](https://docs.spring.io/spring-data/neo4j/reference/)
